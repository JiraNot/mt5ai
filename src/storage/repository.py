"""Repository pattern for database operations."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.types import (
    Direction,
    PositionStatus,
    SetupDecision,
    StrategyCandidate,
    TradeRecord,
)
from src.storage.models import (
    AccountSnapshot,
    DailyRisk,
    SetupLog,
    Trade,
)

logger = logging.getLogger(__name__)


class Repository:
    """Async repository for database CRUD operations."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    # ─── Setup Log ────────────────────────────────────────────────────────────

    async def log_setup(
        self,
        candidate: StrategyCandidate,
        decision: SetupDecision,
        ai_score: Optional[int] = None,
        combined_score: Optional[int] = None,
        rejection_reason: Optional[str] = None,
    ) -> int:
        """
        Log a candidate setup (traded, skipped, or rejected).

        Returns the setup ID.
        """
        setup = SetupLog(
            symbol=candidate.symbol,
            timeframe=candidate.timeframe,
            strategy_id=candidate.strategy_id,
            direction=candidate.direction.value,
            rule_score=candidate.rule_score,
            ai_score=ai_score,
            combined_score=combined_score,
            decision=decision.value,
            entry_price=candidate.entry_price,
            stop_loss=candidate.stop_loss,
            take_profit_1=candidate.take_profit_1,
            take_profit_2=candidate.take_profit_2,
            rr_ratio=candidate.rr_ratio,
            confluences=json.dumps(candidate.confluences),
            risk_flags=json.dumps(candidate.risk_flags),
            rejection_reason=rejection_reason,
        )

        self._session.add(setup)
        await self._session.flush()
        logger.debug(f"Setup logged: {setup.id} {candidate.strategy_id} {decision.value}")
        return setup.id

    async def get_setup(self, setup_id: int) -> Optional[SetupLog]:
        """Get a setup by ID."""
        result = await self._session.execute(
            select(SetupLog).where(SetupLog.id == setup_id)
        )
        return result.scalar_one_or_none()

    async def get_recent_setups(
        self,
        symbol: Optional[str] = None,
        strategy_id: Optional[str] = None,
        decision: Optional[SetupDecision] = None,
        limit: int = 50,
    ) -> list[SetupLog]:
        """Get recent setups with optional filters."""
        query = select(SetupLog).order_by(SetupLog.created_at.desc())

        if symbol:
            query = query.where(SetupLog.symbol == symbol)
        if strategy_id:
            query = query.where(SetupLog.strategy_id == strategy_id)
        if decision:
            query = query.where(SetupLog.decision == decision.value)

        query = query.limit(limit)
        result = await self._session.execute(query)
        return list(result.scalars().all())

    # ─── Trades ───────────────────────────────────────────────────────────────

    async def log_trade(
        self,
        trade: TradeRecord,
        setup_id: Optional[int] = None,
    ) -> int:
        """Log an executed trade. Returns trade ID."""
        db_trade = Trade(
            setup_id=setup_id,
            symbol=trade.symbol,
            direction=trade.direction.value,
            volume=trade.volume,
            entry_price=trade.entry_price,
            sl=trade.sl,
            tp1=trade.tp1,
            tp2=trade.tp2,
            exit_price=trade.exit_price,
            exit_time=trade.exit_time,
            profit=trade.profit,
            commission=trade.commission,
            swap=trade.swap,
            net_profit=trade.net_profit,
            outcome_r=trade.outcome_r,
            outcome_pips=trade.outcome_pips,
            status=trade.status.value,
            magic=trade.magic,
            comment=trade.comment,
            open_time=trade.open_time,
        )

        self._session.add(db_trade)
        await self._session.flush()
        logger.info(f"Trade logged: {db_trade.id} {trade.direction.value} {trade.symbol}")
        return db_trade.id

    async def get_open_trades(self, symbol: Optional[str] = None) -> list[Trade]:
        """Get all open trades."""
        query = select(Trade).where(Trade.status == "OPEN")
        if symbol:
            query = query.where(Trade.symbol == symbol)
        result = await self._session.execute(query)
        return list(result.scalars().all())

    async def close_trade(
        self,
        trade_id: int,
        exit_price: float,
        profit: float,
        commission: float = 0,
        swap: float = 0,
    ) -> None:
        """Update a trade with exit information."""
        net_profit = profit + commission + swap
        await self._session.execute(
            update(Trade)
            .where(Trade.id == trade_id)
            .values(
                exit_price=exit_price,
                exit_time=datetime.utcnow(),
                profit=profit,
                commission=commission,
                swap=swap,
                net_profit=net_profit,
                status=PositionStatus.CLOSED.value,
            )
        )

    async def get_recent_trades(
        self, symbol: Optional[str] = None, limit: int = 50
    ) -> list[Trade]:
        """Get recent trades."""
        query = select(Trade).order_by(Trade.created_at.desc())
        if symbol:
            query = query.where(Trade.symbol == symbol)
        query = query.limit(limit)
        result = await self._session.execute(query)
        return list(result.scalars().all())

    # ─── Daily Risk ───────────────────────────────────────────────────────────

    async def get_daily_risk(self, date: Optional[datetime] = None) -> Optional[DailyRisk]:
        """Get daily risk record for a date."""
        if date is None:
            date = datetime.utcnow().date()
        elif isinstance(date, datetime):
            date = date.date()

        result = await self._session.execute(
            select(DailyRisk).where(
                func.date(DailyRisk.trade_date) == date
            )
        )
        return result.scalar_one_or_none()

    async def update_daily_risk(
        self,
        pnl: float,
        is_win: bool,
        date: Optional[datetime] = None,
    ) -> None:
        """Update daily risk record with new trade result."""
        if date is None:
            date = datetime.utcnow()
        trade_date = date.date() if isinstance(date, datetime) else date

        existing = await self.get_daily_risk(date)
        if existing:
            existing.total_pnl = float(existing.total_pnl) + pnl
            existing.total_trades += 1
            if is_win:
                existing.winning_trades += 1
            else:
                existing.losing_trades += 1
        else:
            daily = DailyRisk(
                trade_date=datetime.combine(trade_date, datetime.min.time()),
                total_pnl=pnl,
                total_trades=1,
                winning_trades=1 if is_win else 0,
                losing_trades=0 if is_win else 1,
            )
            self._session.add(daily)

    # ─── Account Snapshots ────────────────────────────────────────────────────

    async def save_account_snapshot(
        self,
        balance: float,
        equity: float,
        margin: float = 0,
        free_margin: float = 0,
        open_positions: int = 0,
        daily_pnl: float = 0,
    ) -> None:
        """Save an account snapshot."""
        snapshot = AccountSnapshot(
            balance=balance,
            equity=equity,
            margin=margin,
            free_margin=free_margin,
            open_positions=open_positions,
            daily_pnl=daily_pnl,
        )
        self._session.add(snapshot)

    async def get_equity_curve(self, days: int = 30) -> list[dict]:
        """Get equity curve for the last N days."""
        since = datetime.utcnow() -
