"""Unit tests for Two-Way Interactive TelegramBotListener."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime, timezone

from src.core.types import AccountInfo, Direction, Position as CorePosition, OrderResult, TradingMode
from src.notification.telegram_bot import TelegramBotListener
from src.market.crypto_screener import CryptoCandidate, CryptoWatchlist
from src.market.btc_regime import BTCRegimeReport
from src.structure.regime import MarketRegime
from src.risk.promotion_gate import PromotionEvaluation, GateCheck


@pytest.fixture
def mock_gateway():
    gw = AsyncMock()
    gw.get_account_info = AsyncMock(
        return_value=AccountInfo(
            login=1001, balance=10500.0, equity=10800.0,
            currency="USDT", mode=TradingMode.PAPER,
        )
    )
    gw.get_positions = AsyncMock(
        return_value=[
            CorePosition(
                ticket=501,
                symbol="BTCUSDT",
                direction=Direction.BUY,
                volume=0.1,
                open_price=64000.0,
                current_price=65000.0,
                sl=63000.0,
                tp=67000.0,
                profit=100.0,
            )
        ]
    )
    gw.close_position = AsyncMock(return_value=OrderResult(success=True, ticket=501))
    return gw


@pytest.mark.asyncio
async def test_handle_status_command(mock_gateway):
    """Test /status command returns balance and active positions."""
    bot = TelegramBotListener(bot_token="test_token", chat_id="12345", gateway=mock_gateway)
    res = await bot.process_command("/status")

    assert "BINANCE AI PLATFORM STATUS" in res
    assert "$10,500.00" in res
    assert "$10,800.00" in res
    assert "BTCUSDT" in res
    assert "+$100.00" in res


@pytest.mark.asyncio
async def test_handle_homework_command():
    """Test /homework command triggers screener and returns picks."""
    mock_screener = AsyncMock()
    btc_report = BTCRegimeReport(
        symbol="BTCUSDT",
        regime=MarketRegime.UPTREND,
        trend_direction=Direction.BUY,
        trend_strength=0.9,
        confidence=0.85,
        funding_rate=0.0001,
        funding_bias="NEUTRAL",
        current_price=65000.0,
        h4_high=66000.0,
        h4_low=64000.0,
        is_tradable=True,
        recommendation_th="Buy on dips",
    )
    watchlist = CryptoWatchlist(
        timestamp="2026-10-15 12:00 UTC",
        btc_report=btc_report,
        candidates=[
            CryptoCandidate(
                symbol="ETHUSDT", price=3400.0, price_change_pct=4.2,
                quote_volume_24h=800_000_000.0, high_low_spread_pct=6.5,
                score=88.0, tags=["Major", "High Volatility"],
            )
        ],
    )
    mock_screener.run_homework = AsyncMock(return_value=watchlist)

    bot = TelegramBotListener(bot_token="test_token", chat_id="12345", screener=mock_screener)
    res = await bot.process_command("/homework")

    assert "CRYPTO HOMEWORK & WATCHLIST" in res
    assert "UPTREND" in res
    assert "ETHUSDT" in res
    assert "88.0" in res


@pytest.mark.asyncio
async def test_handle_panic_command(mock_gateway):
    """Test /panic command closes all open positions and triggers circuit breaker."""
    stop_callback = AsyncMock()
    bot = TelegramBotListener(
        bot_token="test_token", chat_id="12345",
        gateway=mock_gateway, platform_stop_callback=stop_callback,
    )

    with patch("src.notification.telegram_bot.event_bus.publish", new_callable=AsyncMock) as mock_pub:
        res = await bot.process_command("/panic")
        assert "EMERGENCY PANIC ACTIVATED" in res
        assert "ปิดสถานะออเดอร์ทั้งหมดสำเร็จ: <b>1</b> ไม้" in res
        mock_gateway.close_position.assert_called_once_with(501)
        mock_pub.assert_called_once()
        stop_callback.assert_called_once()


@pytest.mark.asyncio
async def test_handle_readiness_and_help():
    """Test /readiness and /help commands."""
    mock_gate = MagicMock()
    mock_eval = PromotionEvaluation(
        is_promotable=False,
        current_stage="DEMO",
        total_trades=10,
        wins=6,
        losses=4,
        win_rate_pct=60.0,
        profit_factor=1.6,
        net_pnl=200.0,
        max_drawdown_pct=3.0,
        sl_compliance_pct=100.0,
        gate_checks=[GateCheck("Sample Size", ">=30", "10", False, "Trades")],
        summary_th="Demo stats",
    )
    mock_gate.evaluate_trades.return_value = mock_eval

    bot = TelegramBotListener(bot_token="test_token", chat_id="12345", promotion_gate=mock_gate)
    res_readiness = await bot.process_command("/readiness")
    assert "PROMOTION GATE READINESS" in res_readiness
    assert "DEMO" in res_readiness

    res_help = await bot.process_command("/help")
    assert "/status" in res_help
    assert "/panic" in res_help
    assert "/homework" in res_help


@pytest.mark.asyncio
async def test_check_updates_security():
    """Test that unauthorized messages from other chat IDs are ignored."""
    bot = TelegramBotListener(bot_token="test_token", chat_id="12345")
    bot.send_response = AsyncMock()

    mock_client = AsyncMock()
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "result": [
            # Message 1 from unauthorized chat: 99999
            {
                "update_id": 1,
                "message": {"chat": {"id": 99999}, "text": "/panic"},
            },
            # Message 2 from authorized chat: 12345
            {
                "update_id": 2,
                "message": {"chat": {"id": 12345}, "text": "/help"},
            },
        ]
    }
    mock_client.get.return_value = mock_resp

    await bot.check_updates(mock_client)

    # Must only respond once (for authorized update 2)
    assert bot.send_response.call_count == 1
    assert bot._last_update_id == 2
