"""Unit tests for TradingPlatform multi-symbol watchlist execution."""

import json
from unittest.mock import AsyncMock, MagicMock, patch
import pytest

from src.app import TradingPlatform
from src.core.types import Candle, Direction, MarketStructure, StrategyCandidate, Tick


@pytest.mark.asyncio
async def test_get_active_trading_symbols_from_watchlist(tmp_path, monkeypatch):
    platform = TradingPlatform()
    platform._trading_symbol = "BTCUSDT"

    # Mock watchlist file
    mock_watchlist = tmp_path / "crypto_watchlist.json"
    data = {
        "timestamp": "2026-10-14 12:00 UTC",
        "candidates": [
            {"symbol": "SOLUSDT", "score": 80.0},
            {"symbol": "ETHUSDT", "score": 75.0},
            {"symbol": "BTCUSDT", "score": 90.0},
        ],
    }
    mock_watchlist.write_text(json.dumps(data))

    with patch("pathlib.Path.exists", return_value=True), \
         patch("builtins.open", patch("builtins.open", MagicMock(return_value=MagicMock(__enter__=MagicMock(return_value=MagicMock(read=MagicMock(return_value=json.dumps(data)))))))):
        symbols = platform._get_active_trading_symbols()
        assert "BTCUSDT" in symbols
        assert "SOLUSDT" in symbols
        assert "ETHUSDT" in symbols


@pytest.mark.asyncio
async def test_multi_symbol_main_loop_evaluates_all_symbols(monkeypatch):
    platform = TradingPlatform(max_cycles=1)
    platform._running = True

    from datetime import datetime, timezone

    symbols = ["BTCUSDT", "ETHUSDT"]
    now = datetime.now(timezone.utc)
    mock_tick = Tick(timestamp=now, bid=100.0, ask=100.1)

    platform._gateway.get_current_price = AsyncMock(return_value=mock_tick)
    candle = Candle(timestamp=now, open=100, high=101, low=99, close=100)
    platform._data_feed.get_cached_candles = MagicMock(return_value=[candle, candle])
    platform._process_strategies = AsyncMock()
    platform._position_tracker.sync_positions = AsyncMock(return_value=[])
    monkeypatch.setattr("src.app.asyncio.sleep", AsyncMock())

    await platform._main_loop(symbols)

    # _process_strategies should be called for each symbol
    assert platform._process_strategies.call_count == len(symbols)
    called_symbols = [call.args[0].symbol for call in platform._process_strategies.call_args_list]
    assert "BTCUSDT" in called_symbols
    assert "ETHUSDT" in called_symbols


@pytest.mark.asyncio
async def test_risk_evaluation_uses_total_positions_count():
    from src.core.types import AIDecision, RiskDecision, Position
    from src.structure.context import MultiTimeframeContext

    platform = TradingPlatform()
    candidate = StrategyCandidate(
        strategy_id="fvg_final",
        strategy_name="FVG",
        symbol="SOLUSDT",
        timeframe="M5",
        direction=Direction.BUY,
        entry_price=150.0,
        stop_loss=145.0,
        take_profit_1=160.0,
        rule_score=85,
    )
    context = MultiTimeframeContext(
        symbol="SOLUSDT",
        structures={"H1": MarketStructure(timeframe="H1", trend=Direction.BUY)},
    )

    platform._ai_scorer.score = MagicMock(return_value=AIDecision(candidate=candidate, decision="BUY"))
    platform._ai_council.evaluate = AsyncMock(return_value=MagicMock(should_execute=True))
    platform._gateway.get_account_info = AsyncMock(return_value=MagicMock(balance=10000, equity=10000))

    # Mock 3 open positions total across portfolio
    platform._position_tracker.sync_positions = AsyncMock(return_value=[])
    mock_positions = [
        MagicMock(spec=Position, symbol="BTCUSDT"),
        MagicMock(spec=Position, symbol="ETHUSDT"),
        MagicMock(spec=Position, symbol="SOLUSDT"),
    ]
    platform._position_tracker.get_all_positions = MagicMock(return_value=mock_positions)

    platform._risk_engine = MagicMock(evaluate=AsyncMock(return_value=RiskDecision(approved=False)))
    platform._order_manager.send_market_order = AsyncMock()

    await platform._process_candidate(candidate, context, 150.0, 0.5, "london")

    platform._risk_engine.evaluate.assert_awaited_once()
    kwargs = platform._risk_engine.evaluate.call_args.kwargs
    assert kwargs["open_positions_count"] == 3
