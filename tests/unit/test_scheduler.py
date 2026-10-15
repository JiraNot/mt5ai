"""Unit tests for Automated BackgroundScheduler."""

import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from datetime import datetime, timezone, timedelta

from src.live.scheduler import BackgroundScheduler, TZ_BANGKOK
from src.market.crypto_screener import CryptoCandidate, CryptoWatchlist
from src.market.btc_regime import BTCRegimeReport
from src.structure.regime import MarketRegime
from src.core.types import Direction
from src.risk.promotion_gate import PromotionEvaluation, GateCheck


@pytest.fixture
def mock_screener():
    screener = AsyncMock()
    btc_report = BTCRegimeReport(
        symbol="BTCUSDT",
        regime=MarketRegime.UPTREND,
        trend_direction=Direction.BUY,
        trend_strength=0.8,
        confidence=0.85,
        funding_rate=0.0001,
        funding_bias="NEUTRAL",
        current_price=65000.0,
        h4_high=66000.0,
        h4_low=64000.0,
        is_tradable=True,
        recommendation_th="มองหาจังหวะ Buy ตามแนวโน้ม",
    )
    candidates = [
        CryptoCandidate(
            symbol="SOLUSDT", price=150.0, price_change_pct=5.5,
            quote_volume_24h=100_000_000.0, high_low_spread_pct=8.0,
            score=85.0, tags=["High Momentum"],
        )
    ]
    watchlist = CryptoWatchlist(
        timestamp="2026-10-15 08:00 UTC",
        btc_report=btc_report,
        candidates=candidates,
    )
    screener.run_homework = AsyncMock(return_value=watchlist)
    return screener


@pytest.fixture
def mock_promotion_gate():
    gate = MagicMock()
    eval_result = PromotionEvaluation(
        is_promotable=False,
        current_stage="DEMO",
        total_trades=15,
        wins=9,
        losses=6,
        win_rate_pct=60.0,
        profit_factor=1.8,
        net_pnl=450.0,
        max_drawdown_pct=2.1,
        sl_compliance_pct=100.0,
        gate_checks=[
            GateCheck("Sample Size", ">=30", "15", False, "Minimum trades"),
            GateCheck("Server SL Compliance", "100%", "100%", True, "Stop Loss"),
        ],
        summary_th="กำลังเก็บข้อมูล",
        recommendations_th=["เทรดเพิ่มอีก 15 ไม้ในเดโม"],
    )
    gate.evaluate_trades = MagicMock(return_value=eval_result)
    gate.evaluate_database = AsyncMock(return_value=eval_result)
    return gate


@pytest.mark.asyncio
async def test_scheduler_morning_brief_execution(mock_screener):
    """Test manual and triggered morning brief execution."""
    scheduler = BackgroundScheduler(screener=mock_screener)

    with patch("src.live.scheduler.alert_morning_brief", new_callable=AsyncMock) as mock_alert:
        res = await scheduler.run_morning_brief()
        assert res["success"] is True
        assert res["candidates_count"] == 1
        assert res["btc_bias"] == "UPTREND"
        mock_screener.run_homework.assert_called_once()
        mock_alert.assert_called_once()


@pytest.mark.asyncio
async def test_scheduler_evening_reflection_execution(mock_promotion_gate):
    """Test evening reflection execution and telegram dispatch."""
    scheduler = BackgroundScheduler(promotion_gate=mock_promotion_gate)

    with patch("src.live.scheduler.alert_evening_reflection", new_callable=AsyncMock) as mock_alert:
        res = await scheduler.run_evening_reflection()
        assert res["success"] is True
        assert res["total_trades"] == 15
        assert res["win_rate_pct"] == 60.0
        assert res["is_promotable"] is False
        mock_alert.assert_called_once()


@pytest.mark.asyncio
async def test_scheduler_macro_refresh_execution():
    """Test 4H macro refresh fetches candles and updates context."""
    mock_gw = AsyncMock()
    mock_gw.connected = True
    mock_gw.get_ohlcv.return_value = []
    mock_gw.get_funding_rate.return_value = 0.0001

    mock_btc_analyzer = MagicMock()
    mock_report = MagicMock()
    mock_report.macro_bias.value = "BULLISH"
    mock_report.crowd_bias.value = "NEUTRAL"
    mock_report.to_context_dict.return_value = {"bias": "BULLISH", "crowd": "NEUTRAL"}
    mock_btc_analyzer.analyze.return_value = mock_report

    scheduler = BackgroundScheduler(gateway=mock_gw, btc_analyzer=mock_btc_analyzer)
    res = await scheduler.run_macro_refresh()
    assert res["success"] is True
    assert scheduler._latest_btc_macro == {"bias": "BULLISH", "crowd": "NEUTRAL"}


@pytest.mark.asyncio
async def test_check_and_execute_schedules_timings(mock_screener, mock_promotion_gate):
    """Test schedule triggers at 08:00 and 20:00 Bangkok time and 4H UTC."""
    scheduler = BackgroundScheduler(screener=mock_screener, promotion_gate=mock_promotion_gate)

    # 1. Test at 08:30 Bangkok time (01:30 UTC - not a 4h UTC mark)
    dt_morning = datetime(2026, 10, 15, 8, 30, tzinfo=TZ_BANGKOK)
    with patch("src.live.scheduler.alert_morning_brief", new_callable=AsyncMock):
        executed = await scheduler.check_and_execute_schedules(dt_morning)
        assert "morning_brief" in executed

    # Repeating on same day should not run again
    executed_again = await scheduler.check_and_execute_schedules(dt_morning + timedelta(minutes=10))
    assert "morning_brief" not in executed_again

    # 2. Test at 20:15 Bangkok time (13:15 UTC)
    dt_evening = datetime(2026, 10, 15, 20, 15, tzinfo=TZ_BANGKOK)
    with patch("src.live.scheduler.alert_evening_reflection", new_callable=AsyncMock):
        executed_evening = await scheduler.check_and_execute_schedules(dt_evening)
        assert "evening_reflection" in executed_evening


@pytest.mark.asyncio
async def test_scheduler_lifecycle():
    """Test start and stop lifecycle of BackgroundScheduler."""
    scheduler = BackgroundScheduler(check_interval_seconds=0.1)
    await scheduler.start()
    assert scheduler._running is True
    assert scheduler._loop_task is not None

    await scheduler.stop()
    assert scheduler._running is False
