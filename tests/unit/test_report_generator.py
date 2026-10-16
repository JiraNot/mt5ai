"""Unit tests for ReportGenerator (Phase 09 - TASK 0904)."""

from __future__ import annotations

from datetime import datetime, timezone, timedelta
from pathlib import Path
import pytest

from src.analytics.report_generator import (
    DailyReport,
    ReportGenerator,
    StrategyComparisonReport,
    WeeklyReport,
)
from src.storage.trade_journal import (
    CandidateStatus,
    OutcomeStatus,
    TradeCandidate,
    TradeJournal,
)


@pytest.fixture
def sample_candidates() -> list[TradeCandidate]:
    """Create sample candidates with known outcomes across multiple strategies and dates."""
    now = datetime.now(timezone.utc)
    today_str = now.strftime("%Y-%m-%d")
    yesterday = now - timedelta(days=1)

    c1 = TradeCandidate(
        id="CAND_01",
        symbol="BTCUSDT",
        strategy="fvg_reversal",
        direction="BUY",
        entry_price=60000.0,
        stop_loss=59500.0,
        take_profit_1=61000.0,
        status=CandidateStatus.EXECUTED,
        outcome=OutcomeStatus.WIN,
        profit=300.0,
        r_multiple=2.0,
        executed_price=60000.0,
        executed_volume=0.2,
        exit_price=61000.0,
        created_at=now,
        exit_time=now,
    )

    c2 = TradeCandidate(
        id="CAND_02",
        symbol="BTCUSDT",
        strategy="fvg_reversal",
        direction="SELL",
        entry_price=60500.0,
        stop_loss=61000.0,
        take_profit_1=59500.0,
        status=CandidateStatus.EXECUTED,
        outcome=OutcomeStatus.LOSS,
        profit=-100.0,
        r_multiple=-1.0,
        executed_price=60500.0,
        executed_volume=0.2,
        exit_price=61000.0,
        created_at=now,
        exit_time=now,
    )

    c3 = TradeCandidate(
        id="CAND_03",
        symbol="ETHUSDT",
        strategy="choch_order_block",
        direction="BUY",
        entry_price=3000.0,
        stop_loss=2950.0,
        take_profit_1=3100.0,
        status=CandidateStatus.REJECTED,
        rejection_reason="Risk limit reached",
        hypothetical_r=2.0,
        hypothetical_outcome="HYPOTHETICAL_WIN",
        created_at=now,
    )

    c4 = TradeCandidate(
        id="CAND_04",
        symbol="SOLUSDT",
        strategy="breakout_retest",
        direction="BUY",
        entry_price=150.0,
        stop_loss=145.0,
        take_profit_1=160.0,
        status=CandidateStatus.EXECUTED,
        outcome=OutcomeStatus.WIN,
        profit=150.0,
        r_multiple=2.0,
        executed_price=150.0,
        executed_volume=1.0,
        exit_price=160.0,
        created_at=yesterday,
        exit_time=yesterday,
    )

    return [c1, c2, c3, c4]


def test_daily_report_generation(sample_candidates: list[TradeCandidate]):
    """Test generating daily report with candidate metrics, win rate, PnL and markdown."""
    gen = ReportGenerator()
    today_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    report: DailyReport = gen.generate_daily_report(
        target_date=today_str,
        candidates=sample_candidates,
    )

    assert report.report_date == today_str
    assert report.total_candidates == 3  # CAND_01, 02, 03 are from today
    assert report.total_trades == 2  # CAND_01, CAND_02
    assert report.wins == 1
    assert report.losses == 1
    assert report.win_rate_pct == 50.0
    assert report.net_pnl == 200.0
    assert report.gross_profit == 300.0
    assert report.gross_loss == 100.0
    assert report.profit_factor == 3.0
    assert report.avg_r_multiple == 0.5  # (2.0 - 1.0) / 2
    assert report.false_rejects == 1  # CAND_03 had hypothetical_r > 0
    assert report.false_reject_rate_pct == 100.0

    # Markdown format verification
    md = report.to_markdown()
    assert "# 📊 Daily Paper Trading Report" in md
    assert "**Win Rate:** 50.0%" in md
    assert "**Net PnL:** $+200.00" in md
    assert "`fvg_reversal`" in md


def test_weekly_report_generation(sample_candidates: list[TradeCandidate]):
    """Test weekly aggregation across 7 days."""
    gen = ReportGenerator()
    today = datetime.now(timezone.utc).date()

    weekly: WeeklyReport = gen.generate_weekly_report(
        end_date=today,
        days_count=7,
        candidates=sample_candidates,
    )

    assert weekly.total_candidates == 4
    assert weekly.total_trades == 3  # 2 today, 1 yesterday
    assert weekly.wins == 2
    assert weekly.losses == 1
    assert round(weekly.win_rate_pct, 1) == 66.7
    assert weekly.net_pnl == 350.0
    assert len(weekly.daily_summaries) == 7

    md = weekly.to_markdown()
    assert "# 📅 Weekly Paper Trading Report" in md
    assert "Weekly Executive Summary" in md
    assert "`fvg_reversal`" in md
    assert "`breakout_retest`" in md


def test_strategy_comparison(sample_candidates: list[TradeCandidate]):
    """Test comparative matrix, rankings, and composite scoring."""
    gen = ReportGenerator()
    comp: StrategyComparisonReport = gen.generate_strategy_comparison(candidates=sample_candidates)

    assert comp.total_strategies == 3
    assert comp.top_strategy in ("breakout_retest", "fvg_reversal")

    md = comp.to_markdown()
    assert "# ⚔️ Strategy Comparison Report" in md
    assert "Comparative Matrix" in md
    assert "`fvg_reversal`" in md
    assert "`choch_order_block`" in md
    assert "`breakout_retest`" in md


def test_save_report_to_file(tmp_path: Path):
    """Test exporting report to file."""
    gen = ReportGenerator()
    target_file = tmp_path / "reports" / "test_report.md"
    content = "# Test Daily Report Content"
    saved = gen.save_report_to_file(content, target_file)

    assert saved.exists()
    assert saved.read_text(encoding="utf-8") == content
