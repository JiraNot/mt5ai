"""Report Generator for Paper Trading & Live Performance (Phase 09 - TASK 0904).

Generates:
1. Daily Reports: Performance summary, trade statistics, risk adherence, candidate counts.
2. Weekly Reports: Multi-day aggregation, day-by-day breakdown, weekly win rate & profit factor.
3. Strategy Comparison: Side-by-side performance comparison, win rates, PnL, false rejection rates.
"""

from __future__ import annotations

import logging
from dataclasses import asdict, dataclass, field
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Sequence

from src.storage.trade_journal import CandidateStatus, OutcomeStatus, TradeCandidate, TradeJournal

logger = logging.getLogger(__name__)


@dataclass
class DailyReport:
    """Summary report for a single trading day."""

    report_date: str
    generated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    # Candidate triage & decisions
    total_candidates: int = 0
    approved_candidates: int = 0
    rejected_candidates: int = 0
    executed_candidates: int = 0
    expired_candidates: int = 0

    # Trades & Outcomes
    total_trades: int = 0
    wins: int = 0
    losses: int = 0
    breakeven: int = 0
    win_rate_pct: float = 0.0

    # Financial & Risk Metrics
    gross_profit: float = 0.0
    gross_loss: float = 0.0
    net_pnl: float = 0.0
    profit_factor: float = 0.0
    avg_r_multiple: float = 0.0
    max_drawdown_pct: float = 0.0
    total_fees: float = 0.0

    # AI & Filter Quality
    false_rejects: int = 0
    false_reject_rate_pct: float = 0.0

    # Strategy breakdown
    strategy_breakdown: dict[str, dict[str, Any]] = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def to_markdown(self) -> str:
        lines = [
            f"# 📊 Daily Paper Trading Report ({self.report_date})",
            f"*Generated at: {self.generated_at}*",
            "",
            "## 1. Candidate & Decision Summary",
            f"- **Total Candidates Evaluated:** {self.total_candidates}",
            f"- **Approved by Risk & AI:** {self.approved_candidates}",
            f"- **Rejected by Risk / Filter:** {self.rejected_candidates}",
            f"- **Executed Trades:** {self.executed_candidates}",
            f"- **Expired / Timed Out:** {self.expired_candidates}",
            "",
            "## 2. Trading Outcomes & Metrics",
            f"- **Total Closed Trades:** {self.total_trades}",
            f"- **Wins / Losses / Breakeven:** {self.wins}W / {self.losses}L / {self.breakeven}BE",
            f"- **Win Rate:** {self.win_rate_pct:.1f}%",
            f"- **Net PnL:** ${self.net_pnl:+,.2f}",
            f"- **Profit Factor:** {self.profit_factor:.2f}",
            f"- **Average R-Multiple:** {self.avg_r_multiple:.2f}R",
            f"- **Max Drawdown:** {self.max_drawdown_pct:.2f}%",
            f"- **Estimated Fees:** ${self.total_fees:.2f}",
            "",
            "## 3. Filter Effectiveness & False Rejections",
            f"- **False Rejections (Rejected setups that would have won):** {self.false_rejects}",
            f"- **False Rejection Rate:** {self.false_reject_rate_pct:.1f}%",
            "",
            "## 4. Strategy Breakdown",
            "| Strategy | Candidates | Trades | Wins | Losses | Win Rate | Net PnL | Avg R |",
            "|---|---|---|---|---|---|---|---|",
        ]
        if not self.strategy_breakdown:
            lines.append("| No strategies active | 0 | 0 | 0 | 0 | 0.0% | $0.00 | 0.0R |")
        else:
            for strat_id, s in sorted(self.strategy_breakdown.items()):
                lines.append(
                    f"| `{strat_id}` | {s.get('candidates', 0)} | {s.get('trades', 0)} | "
                    f"{s.get('wins', 0)} | {s.get('losses', 0)} | {s.get('win_rate', 0.0):.1f}% | "
                    f"${s.get('net_pnl', 0.0):+,.2f} | {s.get('avg_r', 0.0):.2f}R |"
                )

        if self.notes:
            lines.extend(["", "## 5. Notes & Observations"])
            for note in self.notes:
                lines.append(f"- {note}")

        return "\n".join(lines)


@dataclass
class WeeklyReport:
    """Summary report for a trading week (7 days)."""

    week_start: str
    week_end: str
    generated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    # Aggregated metrics
    total_candidates: int = 0
    total_executed: int = 0
    total_trades: int = 0
    wins: int = 0
    losses: int = 0
    win_rate_pct: float = 0.0
    net_pnl: float = 0.0
    profit_factor: float = 0.0
    max_drawdown_pct: float = 0.0
    avg_r_multiple: float = 0.0
    false_rejects: int = 0

    # Breakdowns
    daily_summaries: list[dict[str, Any]] = field(default_factory=list)
    strategy_summaries: dict[str, dict[str, Any]] = field(default_factory=dict)
    risk_adherence: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def to_markdown(self) -> str:
        lines = [
            f"# 📅 Weekly Paper Trading Report ({self.week_start} to {self.week_end})",
            f"*Generated at: {self.generated_at}*",
            "",
            "## 1. Weekly Executive Summary",
            f"- **Total Candidates Processed:** {self.total_candidates}",
            f"- **Executed Trades:** {self.total_executed}",
            f"- **Win Rate:** {self.win_rate_pct:.1f}% ({self.wins}W / {self.losses}L)",
            f"- **Net PnL:** ${self.net_pnl:+,.2f}",
            f"- **Profit Factor:** {self.profit_factor:.2f}",
            f"- **Max Drawdown:** {self.max_drawdown_pct:.2f}%",
            f"- **Average R-Multiple:** {self.avg_r_multiple:.2f}R",
            f"- **False Rejections:** {self.false_rejects}",
            "",
            "## 2. Daily Performance Breakdown",
            "| Date | Candidates | Trades | Win Rate | Net PnL | Max DD |",
            "|---|---|---|---|---|---|",
        ]
        if not self.daily_summaries:
            lines.append("| No daily activity | 0 | 0 | 0.0% | $0.00 | 0.0% |")
        else:
            for day in self.daily_summaries:
                lines.append(
                    f"| {day.get('date')} | {day.get('candidates', 0)} | {day.get('trades', 0)} | "
                    f"{day.get('win_rate', 0.0):.1f}% | ${day.get('net_pnl', 0.0):+,.2f} | "
                    f"{day.get('max_drawdown', 0.0):.2f}% |"
                )

        lines.extend([
            "",
            "## 3. Strategy Contribution",
            "| Strategy | Trades | Win Rate | Net PnL | Profit Factor |",
            "|---|---|---|---|---|",
        ])
        if not self.strategy_summaries:
            lines.append("| None | 0 | 0.0% | $0.00 | 0.00 |")
        else:
            for strat_id, perf in sorted(self.strategy_summaries.items()):
                lines.append(
                    f"| `{strat_id}` | {perf.get('trades', 0)} | {perf.get('win_rate', 0.0):.1f}% | "
                    f"${perf.get('net_pnl', 0.0):+,.2f} | {perf.get('profit_factor', 0.0):.2f} |"
                )

        if self.risk_adherence:
            lines.extend([
                "",
                "## 4. Risk Engine & Discipline Audit",
                f"- **Circuit Breaker Triggers:** {self.risk_adherence.get('circuit_breaker_triggers', 0)}",
                f"- **Daily Loss Limit Breaches:** {self.risk_adherence.get('daily_loss_breaches', 0)}",
                f"- **Max Exposure Violations:** {self.risk_adherence.get('max_exposure_violations', 0)}",
            ])

        return "\n".join(lines)


@dataclass
class StrategyComparisonReport:
    """Side-by-side performance comparison of multiple strategies."""

    generated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    period_description: str = "Full History"
    total_strategies: int = 0
    top_strategy: str = "None"
    underperforming_strategies: list[str] = field(default_factory=list)
    strategies: list[dict[str, Any]] = field(default_factory=list)
    recommendation: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def to_markdown(self) -> str:
        lines = [
            "# ⚔️ Strategy Comparison Report",
            f"*Generated at: {self.generated_at} | Scope: {self.period_description}*",
            "",
            f"- **Active Strategies Evaluated:** {self.total_strategies}",
            f"- **Top Performer:** `{self.top_strategy}`",
            f"- **Flagged / Underperforming:** {', '.join(f'`{s}`' for s in self.underperforming_strategies) if self.underperforming_strategies else 'None'}",
            "",
            "## Comparative Matrix",
            "| Strategy | Version | Candidates | Executed | Win Rate | Net PnL | Profit Factor | Avg R | False Reject % | Score |",
            "|---|---|---|---|---|---|---|---|---|---|",
        ]
        for row in self.strategies:
            lines.append(
                f"| `{row.get('strategy_id')}` | {row.get('version', '1.0.0')} | "
                f"{row.get('candidates', 0)} | {row.get('executed', 0)} | "
                f"{row.get('win_rate', 0.0):.1f}% | ${row.get('net_pnl', 0.0):+,.2f} | "
                f"{row.get('profit_factor', 0.0):.2f} | {row.get('avg_r', 0.0):.2f}R | "
                f"{row.get('false_reject_pct', 0.0):.1f}% | **{row.get('composite_score', 0):.1f}** |"
            )

        if self.recommendation:
            lines.extend([
                "",
                "## Recommendations",
                f"{self.recommendation}",
            ])

        return "\n".join(lines)


class ReportGenerator:
    """Generates standardized performance reports from TradeJournal or Candidate collections."""

    def __init__(self, journal: TradeJournal | None = None) -> None:
        self.journal = journal

    def _resolve_candidates(
        self,
        candidates: Sequence[TradeCandidate] | None = None,
        journal: TradeJournal | None = None,
    ) -> list[TradeCandidate]:
        """Resolve candidates from parameters or internal journal."""
        if candidates is not None:
            return list(candidates)
        target_journal = journal or self.journal
        if target_journal:
            return list(target_journal._candidates.values())
        return []

    def generate_daily_report(
        self,
        target_date: str | date | datetime | None = None,
        candidates: Sequence[TradeCandidate] | None = None,
        journal: TradeJournal | None = None,
    ) -> DailyReport:
        """Generate daily summary report for a given date (defaults to today UTC)."""
        all_candidates = self._resolve_candidates(candidates, journal)

        if target_date is None:
            target_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        elif isinstance(target_date, (datetime, date)):
            target_str = target_date.strftime("%Y-%m-%d")
        else:
            target_str = str(target_date)

        # Filter candidates created or closed on target_date
        day_candidates: list[TradeCandidate] = []
        for c in all_candidates:
            c_date = c.created_at.strftime("%Y-%m-%d") if c.created_at else ""
            exit_date = c.exit_time.strftime("%Y-%m-%d") if c.exit_time else ""
            if c_date == target_str or exit_date == target_str:
                day_candidates.append(c)

        report = DailyReport(report_date=target_str)
        report.total_candidates = len(day_candidates)

        strategy_map: dict[str, dict[str, Any]] = {}

        for c in day_candidates:
            strat = c.strategy or "unknown"
            if strat not in strategy_map:
                strategy_map[strat] = {
                    "candidates": 0,
                    "trades": 0,
                    "wins": 0,
                    "losses": 0,
                    "net_pnl": 0.0,
                    "r_sum": 0.0,
                    "win_rate": 0.0,
                    "avg_r": 0.0,
                }
            strategy_map[strat]["candidates"] += 1

            if c.status == CandidateStatus.APPROVED:
                report.approved_candidates += 1
            elif c.status == CandidateStatus.REJECTED:
                report.rejected_candidates += 1
                if c.hypothetical_r and c.hypothetical_r > 0:
                    report.false_rejects += 1
            elif c.status == CandidateStatus.EXPIRED:
                report.expired_candidates += 1

            if c.status == CandidateStatus.EXECUTED:
                report.executed_candidates += 1

            # Closed outcome evaluation
            if c.outcome in (OutcomeStatus.WIN, OutcomeStatus.LOSS, OutcomeStatus.BREAKEVEN):
                report.total_trades += 1
                strategy_map[strat]["trades"] += 1
                strategy_map[strat]["net_pnl"] += c.profit
                strategy_map[strat]["r_sum"] += c.r_multiple

                if c.outcome == OutcomeStatus.WIN:
                    report.wins += 1
                    report.gross_profit += max(0.0, c.profit)
                    strategy_map[strat]["wins"] += 1
                elif c.outcome == OutcomeStatus.LOSS:
                    report.losses += 1
                    report.gross_loss += abs(min(0.0, c.profit))
                    strategy_map[strat]["losses"] += 1
                else:
                    report.breakeven += 1

                report.net_pnl += c.profit
                report.avg_r_multiple += c.r_multiple

                # Binance taker fees calculation: default 0.05% entry and exit if volume exists
                if c.executed_volume and c.executed_price:
                    exit_p = c.exit_price or c.executed_price
                    fees = (c.executed_price + exit_p) * c.executed_volume * 0.0005
                    report.total_fees += fees

        # Finalize metrics
        if report.total_trades > 0:
            report.win_rate_pct = (report.wins / report.total_trades) * 100.0
            report.avg_r_multiple = report.avg_r_multiple / report.total_trades
            if report.gross_loss > 0:
                report.profit_factor = report.gross_profit / report.gross_loss
            elif report.gross_profit > 0:
                report.profit_factor = 99.0
            else:
                report.profit_factor = 0.0

        if report.rejected_candidates > 0:
            report.false_reject_rate_pct = (report.false_rejects / report.rejected_candidates) * 100.0

        for s_data in strategy_map.values():
            if s_data["trades"] > 0:
                s_data["win_rate"] = (s_data["wins"] / s_data["trades"]) * 100.0
                s_data["avg_r"] = s_data["r_sum"] / s_data["trades"]

        report.strategy_breakdown = strategy_map
        return report

    def generate_weekly_report(
        self,
        end_date: str | date | datetime | None = None,
        days_count: int = 7,
        candidates: Sequence[TradeCandidate] | None = None,
        journal: TradeJournal | None = None,
    ) -> WeeklyReport:
        """Generate weekly summary spanning previous `days_count` days."""
        all_candidates = self._resolve_candidates(candidates, journal)

        if end_date is None:
            end_dt = datetime.now(timezone.utc).date()
        elif isinstance(end_date, datetime):
            end_dt = end_date.date()
        elif isinstance(end_date, date):
            end_dt = end_date
        else:
            end_dt = datetime.strptime(str(end_date), "%Y-%m-%d").date()

        start_dt = end_dt - timedelta(days=days_count - 1)
        start_str = start_dt.strftime("%Y-%m-%d")
        end_str = end_dt.strftime("%Y-%m-%d")

        daily_reports: list[DailyReport] = []
        current_dt = start_dt
        while current_dt <= end_dt:
            daily_reports.append(
                self.generate_daily_report(
                    target_date=current_dt,
                    candidates=all_candidates,
                )
            )
            current_dt += timedelta(days=1)

        weekly = WeeklyReport(week_start=start_str, week_end=end_str)
        gross_profit = 0.0
        gross_loss = 0.0
        r_sum = 0.0

        for dr in daily_reports:
            weekly.total_candidates += dr.total_candidates
            weekly.total_executed += dr.executed_candidates
            weekly.total_trades += dr.total_trades
            weekly.wins += dr.wins
            weekly.losses += dr.losses
            weekly.net_pnl += dr.net_pnl
            weekly.false_rejects += dr.false_rejects
            gross_profit += dr.gross_profit
            gross_loss += dr.gross_loss
            r_sum += dr.avg_r_multiple * dr.total_trades

            weekly.daily_summaries.append({
                "date": dr.report_date,
                "candidates": dr.total_candidates,
                "trades": dr.total_trades,
                "win_rate": dr.win_rate_pct,
                "net_pnl": dr.net_pnl,
                "max_drawdown": dr.max_drawdown_pct,
            })

            # Merge strategy performance
            for strat_id, s_data in dr.strategy_breakdown.items():
                if strat_id not in weekly.strategy_summaries:
                    weekly.strategy_summaries[strat_id] = {
                        "trades": 0,
                        "wins": 0,
                        "losses": 0,
                        "net_pnl": 0.0,
                        "win_rate": 0.0,
                        "profit_factor": 0.0,
                        "gross_profit": 0.0,
                        "gross_loss": 0.0,
                    }
                st = weekly.strategy_summaries[strat_id]
                st["trades"] += s_data.get("trades", 0)
                st["wins"] += s_data.get("wins", 0)
                st["losses"] += s_data.get("losses", 0)
                st["net_pnl"] += s_data.get("net_pnl", 0.0)

        if weekly.total_trades > 0:
            weekly.win_rate_pct = (weekly.wins / weekly.total_trades) * 100.0
            weekly.avg_r_multiple = r_sum / weekly.total_trades
            if gross_loss > 0:
                weekly.profit_factor = gross_profit / gross_loss
            elif gross_profit > 0:
                weekly.profit_factor = 99.0

        for st in weekly.strategy_summaries.values():
            if st["trades"] > 0:
                st["win_rate"] = (st["wins"] / st["trades"]) * 100.0
                st["profit_factor"] = round(
                    st["net_pnl"] / max(1.0, abs(st["losses"])) if st["losses"] > 0 else 99.0, 2
                )

        return weekly

    def generate_strategy_comparison(
        self,
        candidates: Sequence[TradeCandidate] | None = None,
        journal: TradeJournal | None = None,
        period_description: str = "All Available History",
    ) -> StrategyComparisonReport:
        """Compare all strategies head-to-head based on recorded candidates and outcomes."""
        all_candidates = self._resolve_candidates(candidates, journal)

        strat_stats: dict[str, dict[str, Any]] = {}
        for c in all_candidates:
            strat_id = c.strategy or "unknown"
            if strat_id not in strat_stats:
                strat_stats[strat_id] = {
                    "strategy_id": strat_id,
                    "version": c.strategy_version,
                    "candidates": 0,
                    "executed": 0,
                    "rejected": 0,
                    "trades": 0,
                    "wins": 0,
                    "losses": 0,
                    "net_pnl": 0.0,
                    "gross_profit": 0.0,
                    "gross_loss": 0.0,
                    "r_sum": 0.0,
                    "false_rejects": 0,
                }
            s = strat_stats[strat_id]
            s["candidates"] += 1
            if c.status == CandidateStatus.EXECUTED:
                s["executed"] += 1
            elif c.status == CandidateStatus.REJECTED:
                s["rejected"] += 1
                if c.hypothetical_r and c.hypothetical_r > 0:
                    s["false_rejects"] += 1

            if c.outcome in (OutcomeStatus.WIN, OutcomeStatus.LOSS, OutcomeStatus.BREAKEVEN):
                s["trades"] += 1
                s["net_pnl"] += c.profit
                s["r_sum"] += c.r_multiple
                if c.outcome == OutcomeStatus.WIN:
                    s["wins"] += 1
                    s["gross_profit"] += max(0.0, c.profit)
                elif c.outcome == OutcomeStatus.LOSS:
                    s["losses"] += 1
                    s["gross_loss"] += abs(min(0.0, c.profit))

        rows: list[dict[str, Any]] = []
        underperforming: list[str] = []
        top_strat = "None"
        best_score = -9999.0

        for strat_id, s in strat_stats.items():
            trades = s["trades"]
            win_rate = (s["wins"] / trades * 100.0) if trades > 0 else 0.0
            avg_r = (s["r_sum"] / trades) if trades > 0 else 0.0
            if s["gross_loss"] > 0:
                pf = s["gross_profit"] / s["gross_loss"]
            elif s["gross_profit"] > 0:
                pf = 99.0
            else:
                pf = 0.0

            false_reject_pct = (s["false_rejects"] / s["rejected"] * 100.0) if s["rejected"] > 0 else 0.0

            # Composite Score: weights win_rate (40%), profit_factor (30%), avg_r (20%), and penalizes false rejects (10%)
            comp_score = (win_rate * 0.4) + (min(pf, 5.0) * 10.0 * 0.3) + (max(0.0, avg_r) * 15.0 * 0.2) - (false_reject_pct * 0.1)

            row = {
                "strategy_id": strat_id,
                "version": s["version"],
                "candidates": s["candidates"],
                "executed": s["executed"],
                "trades": trades,
                "wins": s["wins"],
                "losses": s["losses"],
                "win_rate": round(win_rate, 1),
                "net_pnl": round(s["net_pnl"], 2),
                "profit_factor": round(pf, 2),
                "avg_r": round(avg_r, 2),
                "false_reject_pct": round(false_reject_pct, 1),
                "composite_score": round(comp_score, 1),
            }
            rows.append(row)

            if comp_score > best_score and trades > 0:
                best_score = comp_score
                top_strat = strat_id

            if trades >= 5 and (win_rate < 40.0 or pf < 1.0):
                underperforming.append(strat_id)

        rows.sort(key=lambda x: x["composite_score"], reverse=True)

        rec = (
            f"Strategy `{top_strat}` is currently leading with composite score {best_score:.1f}. "
            if top_strat != "None"
            else "Insufficient trade history to declare top strategy. Continue paper trading."
        )
        if underperforming:
            rec += f" Strategies {', '.join(underperforming)} show sub-1.0 profit factor or low win rate; review risk filters."

        return StrategyComparisonReport(
            period_description=period_description,
            total_strategies=len(rows),
            top_strategy=top_strat,
            underperforming_strategies=underperforming,
            strategies=rows,
            recommendation=rec,
        )

    def save_report_to_file(self, content: str, file_path: str | Path) -> Path:
        """Save report string (markdown or text) to specified path."""
        p = Path(file_path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")
        logger.info("Report saved to %s", p.resolve())
        return p
