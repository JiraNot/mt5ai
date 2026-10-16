"""Integration tests for Paper Trading Full Loop (Phase 09).

Tests the complete deterministic loop:
Market Data Ingestion → Structure Context → Strategy Plugins → Candidate/Signal Logging
→ AI Scorer → Risk Engine → Paper Gateway Execution → Position & Outcome Tracking → Report Generation
"""

from __future__ import annotations

from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock, MagicMock
import pytest
import pytest_asyncio

from src.core.types import (
    Candle,
    Direction,
    OrderRequest,
    StrategyCandidate,
    Tick,
)
from src.execution.paper_gateway import PaperGateway
from src.live.paper_loop import PaperTradingRunner
from src.market.binance_gateway import BinanceGateway
from src.storage.trade_journal import CandidateStatus, OutcomeStatus, TradeJournal


def generate_candle_series(count: int = 50, start_price: float = 60000.0) -> list[Candle]:
    """Generate deterministic series of candles for testing."""
    now = datetime.now(timezone.utc) - timedelta(hours=count)
    candles: list[Candle] = []
    p = start_price

    for i in range(count):
        # Create mild trend waves
        if i % 10 < 5:
            delta = 100.0
        else:
            delta = -80.0

        o = p
        c = p + delta
        h = max(o, c) + 30.0
        l = min(o, c) - 30.0
        p = c

        candles.append(
            Candle(
                timestamp=now + timedelta(hours=i),
                open=round(o, 2),
                high=round(h, 2),
                low=round(l, 2),
                close=round(c, 2),
                volume=150.0,
            )
        )
    return candles


@pytest.mark.asyncio
async def test_paper_trading_runner_initialization_and_risk_engine():
    """Verify PaperTradingRunner initializes cleanly with in-memory SQLite RiskEngine."""
    runner = PaperTradingRunner(symbol="BTCUSDT", initial_balance=10000.0)
    await runner.initialize()

    assert runner.balance == 10000.0
    assert runner.equity == 10000.0
    assert runner.risk_engine is not None
    assert runner.gateway.venue == "binance"

    await runner.close()


@pytest.mark.asyncio
async def test_paper_trading_outcome_tracking_and_fee_deduction():
    """TASK 0903: Test position tracking, TP/SL hit, taker fee calculation, and journal update."""
    runner = PaperTradingRunner(symbol="BTCUSDT", initial_balance=10000.0, taker_fee_pct=0.0005)
    await runner.initialize()

    now = datetime.now(timezone.utc)

    # 1. Log a candidate in journal
    cand = StrategyCandidate(
        id="CAND_PAPER_01",
        symbol="BTCUSDT",
        strategy_id="fvg_reversal",
        strategy_name="FVG Reversal",
        timeframe="M5",
        direction=Direction.BUY,
        entry_price=60000.0,
        stop_loss=59000.0,
        take_profit_1=62000.0,
        rule_score=85,
    )
    j_entry = runner.journal.log_candidate(cand)
    runner.journal.update_execution(
        candidate_id=j_entry.id,
        executed_price=60000.0,
        executed_volume=0.1,
    )

    # Add open position
    runner.open_positions.append({
        "ticket": 101,
        "candidate_id": j_entry.id,
        "strategy": "fvg_reversal",
        "direction": Direction.BUY,
        "entry_price": 60000.0,
        "sl": 59000.0,
        "tp": 62000.0,
        "volume": 0.1,
        "open_time": now.isoformat(),
        "status": "OPEN",
    })

    # 2. Simulate candle hitting TP (62000)
    tp_candle = Candle(
        timestamp=now + timedelta(minutes=15),
        open=61000.0,
        high=62500.0,  # exceeds TP 62000
        low=60800.0,
        close=62200.0,
        volume=100.0,
    )

    closed = runner._track_open_positions(tp_candle)

    assert len(closed) == 1
    assert len(runner.open_positions) == 0
    assert len(runner.closed_trades) == 1

    closed_trade = closed[0]
    assert closed_trade["outcome"] == "WIN"
    assert closed_trade["exit_price"] == 62000.0

    # Gross PnL = (62000 - 60000) * 0.1 = +200.00
    # Fees = (60000 + 62000) * 0.1 * 0.0005 = 6.10
    # Net PnL = 200.00 - 6.10 = 193.90
    expected_net = round(200.0 - 6.10, 2)
    assert closed_trade["net_pnl"] == expected_net
    assert runner.balance == 10000.0 + expected_net

    # Verify TradeJournal is updated
    recorded = runner.journal.get_candidate(j_entry.id)
    assert recorded is not None
    assert recorded.outcome == OutcomeStatus.WIN
    assert recorded.profit == expected_net
    assert recorded.r_multiple == 2.0  # (62000 - 60000) / (60000 - 59000) = 2.0R

    await runner.close()


@pytest.mark.asyncio
async def test_paper_trading_hypothetical_outcome_tracking():
    """TASK 0903: Test hypothetical outcome evaluation for rejected candidates."""
    runner = PaperTradingRunner(symbol="BTCUSDT")
    await runner.initialize()

    now = datetime.now(timezone.utc)

    # Log a rejected candidate
    cand = StrategyCandidate(
        id="CAND_REJECT_01",
        symbol="BTCUSDT",
        strategy_id="breakout_retest",
        strategy_name="Breakout Retest",
        timeframe="M5",
        direction=Direction.BUY,
        entry_price=50000.0,
        stop_loss=49000.0,
        take_profit_1=52000.0,
        rule_score=60,
    )
    j_entry = runner.journal.log_candidate(cand)
    j_entry.status = CandidateStatus.REJECTED
    j_entry.rejection_reason = "Rule score too low"

    # Candle that reaches hypothetical TP
    high_candle = Candle(
        timestamp=now + timedelta(hours=1),
        open=50500.0,
        high=52500.0,
        low=50200.0,
        close=52100.0,
        volume=50.0,
    )

    runner._track_hypothetical_outcomes(high_candle)

    resolved = runner.journal.get_candidate(j_entry.id)
    assert resolved.hypothetical_outcome == "HYPOTHETICAL_WIN"
    assert resolved.hypothetical_r == 2.0

    # Ensure false rejects count increments in report
    report = runner.report_generator.generate_daily_report(journal=runner.journal)
    assert report.false_rejects == 1

    await runner.close()


@pytest.mark.asyncio
async def test_paper_trading_full_step_and_report_generation():
    """TASK 0901, 0902, 0904: Test full step, signal logging, paper execution, and report generation."""
    mock_binance = AsyncMock(spec=BinanceGateway)
    mock_binance.connected = True
    mock_binance.get_current_price = AsyncMock(return_value=Tick(
        symbol="BTCUSDT", bid=60000.0, ask=60002.0, last=60001.0, volume=10.0, timestamp=datetime.now(timezone.utc)
    ))

    paper_gw = PaperGateway(mock_binance, initial_balance=10000.0)
    runner = PaperTradingRunner(symbol="BTCUSDT", gateway=paper_gw, initial_balance=10000.0)
    await runner.initialize()

    # Generate multi-timeframe candles
    h1_candles = generate_candle_series(count=40, start_price=60000.0)
    m15_candles = generate_candle_series(count=40, start_price=60000.0)
    m5_candles = generate_candle_series(count=40, start_price=60000.0)

    candles_by_tf = {
        "H1": h1_candles,
        "M15": m15_candles,
        "M5": m5_candles,
    }

    # Execute a step
    current_candle = m5_candles[-1]
    res = await runner.step(current_candle, candles_by_tf)

    assert "cycle" in res
    assert res["cycle"] == 1
    assert "price" in res
    assert "equity" in res

    # Generate all reports
    reports = runner.generate_reports()
    assert "daily_report" in reports
    assert "weekly_report" in reports
    assert "strategy_comparison" in reports
    assert "daily_markdown" in reports
    assert "# 📊 Daily Paper Trading Report" in reports["daily_markdown"]
    assert "# 📅 Weekly Paper Trading Report" in reports["weekly_markdown"]
    assert "# ⚔️ Strategy Comparison Report" in reports["comparison_markdown"]

    await runner.close()
