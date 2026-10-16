"""Paper Trading Full Loop Runner for Binance USDT-M Futures (Phase 09).

Wires together the full deterministic pipeline:
Market Data Ingestion → Structure Context → Strategy Plugins → Candidate/Signal Logging
→ AI Scorer → Risk Engine → Paper Gateway Execution → Position & Outcome Tracking → Report Generation

Adheres to Safety Rules:
- BINANCE_MODE=paper safe default.
- Fail-closed execution.
- Mandatory broker-side protective stop (SL).
- No martingale, no grid, no hidden live mode auto-enable.
- All candidate setups and decisions logged for ML training & audit.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import Any, Sequence

from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from src.ai.scorer import RuleBasedScorer
from src.analytics.report_generator import (
    DailyReport,
    ReportGenerator,
    StrategyComparisonReport,
    WeeklyReport,
)
from src.core.config import settings
from src.core.types import (
    AIDecision,
    Candle,
    Direction,
    OrderRequest,
    OrderResult,
    RiskDecision,
    StrategyCandidate,
    Tick,
)
from src.execution.paper_gateway import PaperGateway
from src.market.binance_gateway import BinanceGateway
from src.risk.manager import RiskEngine
from src.storage.models import Base
from src.storage.trade_journal import (
    CandidateStatus,
    OutcomeStatus,
    TradeCandidate,
    TradeJournal,
)
from src.strategies.meta_engine import MetaDecisionEngine
from src.strategies.registry import auto_discover
from src.structure.context import ContextBuilder, MultiTimeframeContext

logger = logging.getLogger(__name__)


class PaperTradingRunner:
    """
    Deterministic full-loop Paper Trading runner.

    Executes:
    1. Data Ingestion & Multi-timeframe SMC Context Building
    2. Outcome Tracking on open positions (SL/TP hits, fees, PnL, R-multiple)
    3. Hypothetical outcome evaluation on rejected setups
    4. Multi-strategy Candidate Evaluation
    5. Signal & Decision Logging into TradeJournal
    6. AI Scorer Evaluation
    7. Risk Engine Validation & Sizing
    8. Paper Order Execution with mandatory Stop Loss
    9. Real-time Equity & Drawdown Tracking
    10. Daily / Weekly / Strategy Comparison Report Generation
    """

    def __init__(
        self,
        symbol: str = "BTCUSDT",
        initial_balance: float = 10000.0,
        risk_per_trade: float = 0.01,
        taker_fee_pct: float = 0.0005,  # 0.05% Binance taker fee
        gateway: PaperGateway | BinanceGateway | None = None,
        journal: TradeJournal | None = None,
        db_session: AsyncSession | None = None,
        spread_pips: float = 1.0,
    ) -> None:
        self.symbol = symbol.upper()
        self.initial_balance = initial_balance
        self.risk_per_trade = risk_per_trade
        self.taker_fee_pct = taker_fee_pct
        self.spread_pips = spread_pips

        # Venue & Gateway (guaranteed paper execution mode)
        if gateway is None:
            raw = BinanceGateway()
            self.gateway = PaperGateway(raw, initial_balance=initial_balance)
        elif isinstance(gateway, PaperGateway):
            self.gateway = gateway
        else:
            self.gateway = PaperGateway(gateway, initial_balance=initial_balance)

        # Storage & Reporting
        self.journal = journal or TradeJournal()
        self.report_generator = ReportGenerator(journal=self.journal)
        self._db_session = db_session
        self._db_engine = None

        # Core Engines
        auto_discover()
        self.context_builder = ContextBuilder()
        self.meta_engine = MetaDecisionEngine()
        self.ai_scorer = RuleBasedScorer()
        self.risk_engine: RiskEngine | None = None

        # State tracking
        self.balance = initial_balance
        self.equity = initial_balance
        self.peak_equity = initial_balance
        self.max_drawdown_pct = 0.0
        self.open_positions: list[dict[str, Any]] = []
        self.closed_trades: list[dict[str, Any]] = []
        self.equity_curve: list[dict[str, Any]] = []
        self.cycle_count = 0
        self.is_running = False

    async def initialize(self) -> None:
        """Initialize in-memory or database session for RiskEngine if not provided."""
        if self._db_session is None:
            self._db_engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
            async with self._db_engine.begin() as conn:
                await conn.run_sync(Base.metadata.create_all)
            session_factory = sessionmaker(self._db_engine, class_=AsyncSession, expire_on_commit=False)
            self._db_session = session_factory()

        self.risk_engine = RiskEngine(session=self._db_session)
        logger.info("PaperTradingRunner initialized for %s with balance $%.2f", self.symbol, self.balance)

    async def close(self) -> None:
        """Cleanup resources."""
        self.is_running = False
        if self._db_session:
            await self._db_session.close()
        if self._db_engine:
            await self._db_engine.dispose()
        if self.gateway.connected:
            await self.gateway.disconnect()

    def _get_total_exposure(self) -> float:
        """Calculate total USD notional value of open positions."""
        return sum(pos["volume"] * pos["entry_price"] for pos in self.open_positions)

    def _track_open_positions(self, candle: Candle) -> list[dict[str, Any]]:
        """
        TASK 0903: Track open positions against incoming candle.
        Evaluates stop loss and take profit hits, applies Binance fees, and updates TradeJournal.
        """
        closed_this_bar: list[dict[str, Any]] = []

        for pos in list(self.open_positions):
            hit = False
            exit_price = 0.0
            exit_reason = ""
            direction = pos["direction"]
            sl = pos["sl"]
            tp = pos["tp"]
            entry = pos["entry_price"]
            volume = pos["volume"]

            # Update MFE / MAE
            if direction == Direction.BUY:
                current_mfe = max(0.0, candle.high - entry)
                current_mae = max(0.0, entry - candle.low)
                pos["mfe"] = max(pos.get("mfe", 0.0), current_mfe)
                pos["mae"] = max(pos.get("mae", 0.0), current_mae)

                if candle.low <= sl:
                    hit = True
                    exit_price = sl
                    exit_reason = "STOP_LOSS"
                elif candle.high >= tp:
                    hit = True
                    exit_price = tp
                    exit_reason = "TAKE_PROFIT"
            else:
                current_mfe = max(0.0, entry - candle.low)
                current_mae = max(0.0, candle.high - entry)
                pos["mfe"] = max(pos.get("mfe", 0.0), current_mfe)
                pos["mae"] = max(pos.get("mae", 0.0), current_mae)

                if candle.high >= sl:
                    hit = True
                    exit_price = sl
                    exit_reason = "STOP_LOSS"
                elif candle.low <= tp:
                    hit = True
                    exit_price = tp
                    exit_reason = "TAKE_PROFIT"

            if hit:
                # PnL accounting
                if direction == Direction.BUY:
                    gross_pnl = (exit_price - entry) * volume
                else:
                    gross_pnl = (entry - exit_price) * volume

                entry_fee = entry * volume * self.taker_fee_pct
                exit_fee = exit_price * volume * self.taker_fee_pct
                net_pnl = gross_pnl - (entry_fee + exit_fee)

                sl_distance = abs(entry - sl)
                r_multiple = (gross_pnl / (sl_distance * volume)) if (sl_distance * volume) > 0 else 0.0

                self.balance += net_pnl
                self.equity = self.balance

                # Update TradeJournal
                cand_id = pos.get("candidate_id")
                if cand_id:
                    self.journal.update_outcome(
                        candidate_id=cand_id,
                        exit_price=exit_price,
                        exit_reason=exit_reason,
                        profit=round(net_pnl, 2),
                        r_multiple=round(r_multiple, 2),
                        mfe=round(pos.get("mfe", 0.0), 2),
                        mae=round(pos.get("mae", 0.0), 2),
                    )

                pos["status"] = "CLOSED"
                pos["exit_price"] = exit_price
                pos["exit_reason"] = exit_reason
                pos["exit_time"] = candle.timestamp.isoformat()
                pos["net_pnl"] = round(net_pnl, 2)
                pos["r_multiple"] = round(r_multiple, 2)
                pos["outcome"] = "WIN" if net_pnl > 0 else "LOSS"

                self.open_positions.remove(pos)
                self.closed_trades.append(pos)
                closed_this_bar.append(pos)

        # Update drawdown metrics
        unrealized_pnl = 0.0
        for pos in self.open_positions:
            if pos["direction"] == Direction.BUY:
                unrealized_pnl += (candle.close - pos["entry_price"]) * pos["volume"]
            else:
                unrealized_pnl += (pos["entry_price"] - candle.close) * pos["volume"]

        self.equity = self.balance + unrealized_pnl
        if self.equity > self.peak_equity:
            self.peak_equity = self.equity

        dd = (self.peak_equity - self.equity) / self.peak_equity * 100.0 if self.peak_equity > 0 else 0.0
        if dd > self.max_drawdown_pct:
            self.max_drawdown_pct = dd

        self.equity_curve.append({
            "timestamp": candle.timestamp.isoformat(),
            "balance": round(self.balance, 2),
            "equity": round(self.equity, 2),
            "max_drawdown_pct": round(self.max_drawdown_pct, 2),
        })

        return closed_this_bar

    def _track_hypothetical_outcomes(self, candle: Candle) -> None:
        """
        TASK 0903: Evaluate hypothetical performance for rejected candidates.
        Tests whether rejected setups would have achieved TP or hit SL to measure false rejections.
        """
        for candidate in self.journal.get_candidates_by_status(CandidateStatus.REJECTED):
            if candidate.hypothetical_outcome:
                continue  # already resolved

            entry = candidate.entry_price
            sl = candidate.stop_loss
            tp = candidate.take_profit_1
            sl_dist = abs(entry - sl)

            if candidate.direction == "BUY":
                if candle.high >= tp:
                    r_mult = (tp - entry) / sl_dist if sl_dist > 0 else 2.0
                    self.journal.update_hypothetical(candidate.id, round(r_mult, 2), "HYPOTHETICAL_WIN")
                elif candle.low <= sl:
                    self.journal.update_hypothetical(candidate.id, -1.0, "HYPOTHETICAL_LOSS")
            else:
                if candle.low <= tp:
                    r_mult = (entry - tp) / sl_dist if sl_dist > 0 else 2.0
                    self.journal.update_hypothetical(candidate.id, round(r_mult, 2), "HYPOTHETICAL_WIN")
                elif candle.high >= sl:
                    self.journal.update_hypothetical(candidate.id, -1.0, "HYPOTHETICAL_LOSS")

    async def step(
        self,
        current_candle: Candle,
        candles_by_tf: dict[str, list[Candle]],
        session: str = "crypto_continuous",
    ) -> dict[str, Any]:
        """
        Executes one full cycle step of the paper loop.

        Returns a dictionary summarizing candidates, decisions, executions, and closed positions.
        """
        self.cycle_count += 1
        current_price = current_candle.close

        # 1. Track Open Positions & Hypotheticals
        closed = self._track_open_positions(current_candle)
        self._track_hypothetical_outcomes(current_candle)

        # 2. Build Multi-timeframe SMC Context
        ctx = self.context_builder.build(
            symbol=self.symbol,
            candles_by_tf=candles_by_tf,
            primary_tf="M5" if "M5" in candles_by_tf else "H1",
            htf="H1" if "M5" in candles_by_tf else "H4",
        )
        ctx.current_price = current_price
        ctx.spread = self.spread_pips

        # 3. Strategy Evaluation (TASK 0901)
        raw_candidates = await self.meta_engine.evaluate(
            context=ctx,
            current_price=current_price,
            spread=self.spread_pips,
            session=session,
        )

        step_results: dict[str, Any] = {
            "cycle": self.cycle_count,
            "timestamp": current_candle.timestamp.isoformat(),
            "price": current_price,
            "candidates_found": len(raw_candidates),
            "executed_orders": [],
            "closed_trades": closed,
            "equity": round(self.equity, 2),
        }

        if not raw_candidates:
            return step_results

        # 4. Process each Candidate through AI → Risk → Execution (TASK 0901, 0902)
        for cand in raw_candidates:
            # Score candidate with AI Scorer
            ai_decision = self.ai_scorer.score(
                candidate=cand,
                context=ctx,
                spread=self.spread_pips,
                session=session,
            )

            # TASK 0902: Log candidate & signal in TradeJournal
            journal_entry = self.journal.log_candidate(
                candidate=cand,
                ai_decision=ai_decision,
                market_context={
                    "htf_trend": ctx.get_trend("H4").value if ctx.get_trend("H4") else "",
                    "market_regime": getattr(ctx, "market_regime", "TRENDING"),
                    "session": session,
                    "spread": self.spread_pips,
                },
            )

            # AI Skip gate
            if ai_decision.decision == "WAIT" or ai_decision.ai_score < 70:
                self.journal.expire_candidate(journal_entry.id, reason=f"AI Score {ai_decision.ai_score} < 70")
                continue

            # 5. Risk Engine Evaluation (TASK 0901)
            risk_decision: RiskDecision
            if self.risk_engine:
                risk_decision = await self.risk_engine.evaluate(
                    candidate=cand,
                    ai_decision=ai_decision,
                    account_balance=self.balance,
                    account_equity=self.equity,
                    open_positions_count=len(self.open_positions),
                    total_exposure=self._get_total_exposure(),
                    current_spread=self.spread_pips,
                    session=session,
                )
            else:
                # Fallback deterministic risk check
                sl_dist = abs(cand.entry_price - cand.stop_loss)
                if sl_dist <= 0 or len(self.open_positions) >= 3:
                    risk_decision = RiskDecision(approved=False, rejection_reason="Max positions or invalid SL")
                else:
                    risk_amt = self.equity * self.risk_per_trade
                    vol = round(risk_amt / sl_dist, 3)
                    risk_decision = RiskDecision(
                        approved=True,
                        position_size_lots=max(0.001, vol),
                        risk_amount=risk_amt,
                        risk_pct=self.risk_per_trade,
                        adjusted_sl=cand.stop_loss,
                        adjusted_tp1=cand.take_profit_1,
                    )

            if not risk_decision.approved:
                # TASK 0902: Log Rejection
                journal_entry.status = CandidateStatus.REJECTED
                journal_entry.rejection_reason = risk_decision.rejection_reason or "Risk rejection"
                continue

            # 6. Simulated Execution via Paper Gateway (TASK 0901)
            volume = max(0.001, risk_decision.position_size_lots)
            cand_id = getattr(cand, "id", None) or f"{cand.strategy_id}_{int(datetime.now(timezone.utc).timestamp() * 1000)}"
            strat_ver = getattr(cand, "strategy_version", None) or cand.metadata.get("version", "1.0.0")
            order_req = OrderRequest(
                symbol=cand.symbol,
                direction=cand.direction,
                volume=volume,
                price=current_price,
                sl=risk_decision.adjusted_sl or cand.stop_loss,
                tp=risk_decision.adjusted_tp1 or cand.take_profit_1,
                comment=f"Paper_{cand.strategy_id}",
                execution_key=f"{cand_id}:{strat_ver}",
            )

            order_res: OrderResult = await self.gateway.send_order(order_req)

            if order_res.success:
                # Update TradeJournal execution
                self.journal.update_execution(
                    candidate_id=journal_entry.id,
                    executed_price=current_price,
                    executed_volume=volume,
                    slippage=0.0,
                )

                pos_record = {
                    "ticket": order_res.ticket,
                    "candidate_id": journal_entry.id,
                    "strategy": cand.strategy_id,
                    "direction": cand.direction,
                    "entry_price": current_price,
                    "sl": order_req.sl,
                    "tp": order_req.tp,
                    "volume": volume,
                    "open_time": current_candle.timestamp.isoformat(),
                    "status": "OPEN",
                    "mfe": 0.0,
                    "mae": 0.0,
                }
                self.open_positions.append(pos_record)
                step_results["executed_orders"].append(pos_record)
                logger.info(
                    "Paper Order Executed: %s %s @ %.2f (SL: %.2f, TP: %.2f, Vol: %.3f)",
                    cand.direction.value, cand.symbol, current_price, order_req.sl, order_req.tp, volume
                )

        return step_results

    async def run_simulation_on_candles(
        self,
        candles_by_tf: dict[str, list[Candle]],
        primary_tf: str = "H1",
        start_idx: int = 30,
    ) -> dict[str, Any]:
        """
        Runs full deterministic paper trading loop across a historical candle series.
        """
        await self.initialize()
        primary_candles = candles_by_tf.get(primary_tf, [])
        if len(primary_candles) < start_idx + 5:
            return {"error": "Insufficient candle data"}

        for i in range(start_idx, len(primary_candles)):
            current_bar = primary_candles[i]
            # Slice MTF history up to current candle
            sliced_candles: dict[str, list[Candle]] = {}
            for tf, candles in candles_by_tf.items():
                ratio = i / len(primary_candles)
                avail_len = max(25, int(len(candles) * ratio))
                sliced_candles[tf] = candles[:avail_len]

            await self.step(current_bar, sliced_candles)

        # Close any remaining open positions on final bar close
        last_candle = primary_candles[-1]
        for pos in list(self.open_positions):
            entry = pos["entry_price"]
            exit_p = last_candle.close
            vol = pos["volume"]
            if pos["direction"] == Direction.BUY:
                gross = (exit_p - entry) * vol
            else:
                gross = (entry - exit_p) * vol
            fees = (entry + exit_p) * vol * self.taker_fee_pct
            net = gross - fees

            self.balance += net
            self.equity = self.balance
            cand_id = pos.get("candidate_id")
            if cand_id:
                self.journal.update_outcome(
                    candidate_id=cand_id,
                    exit_price=exit_p,
                    exit_reason="SESSION_CLOSE",
                    profit=round(net, 2),
                    r_multiple=1.0 if net > 0 else -1.0,
                )
            pos["status"] = "CLOSED"
            pos["net_pnl"] = round(net, 2)
            pos["outcome"] = "WIN" if net > 0 else "LOSS"
            self.open_positions.remove(pos)
            self.closed_trades.append(pos)

        stats = self.journal.get_statistics()
        return {
            "symbol": self.symbol,
            "initial_balance": self.initial_balance,
            "final_equity": round(self.equity, 2),
            "net_profit": round(self.equity - self.initial_balance, 2),
            "return_pct": round((self.equity - self.initial_balance) / self.initial_balance * 100.0, 2),
            "max_drawdown_pct": round(self.max_drawdown_pct, 2),
            "total_candidates": stats["total_candidates"],
            "approved": stats["approved"],
            "rejected": stats["rejected"],
            "total_trades": stats["total_trades"],
            "win_rate": stats["win_rate"],
            "false_rejects": stats["false_rejects"],
            "equity_curve": self.equity_curve,
        }

    def generate_reports(self) -> dict[str, Any]:
        """
        TASK 0904: Generates Daily, Weekly, and Strategy Comparison reports.
        """
        daily = self.report_generator.generate_daily_report()
        weekly = self.report_generator.generate_weekly_report()
        comparison = self.report_generator.generate_strategy_comparison()

        return {
            "daily_report": daily,
            "weekly_report": weekly,
            "strategy_comparison": comparison,
            "daily_markdown": daily.to_markdown(),
            "weekly_markdown": weekly.to_markdown(),
            "comparison_markdown": comparison.to_markdown(),
        }
