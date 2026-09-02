"""Risk limit checks — daily loss, max trades, consecutive losses, exposure."""

from __future__ import annotations

import logging
from datetime import datetime, date

from src.core.config import settings
from src.storage.models import DailyRisk
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


class LimitChecker:
    """
    Checks all risk limits before allowing a trade.
    Each method returns (passed: bool, reason: str).
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._consecutive_losses = 0  # In-memory counter, reset on win

    async def check_all(
        self,
        balance: float,
        open_positions_count: int,
        total_exposure: float,
        current_spread: float,
    ) -> tuple[bool, str | None]:
        """
        Run all limit checks. Returns (approved, rejection_reason).
        """
        checks = [
            await self.check_daily_loss(balance),
            await self.check_max_trades_today(),
            self.check_consecutive_losses(),
            self.check_exposure(balance, total_exposure),
            self.check_spread(current_spread),
        ]

        for passed, reason in checks:
            if not passed:
                logger.warning(f"Risk limit breached: {reason}")
                return False, reason

        return True, None

    async def check_daily_loss(self, balance: float) -> tuple[bool, str | None]:
        """Check if daily loss limit is reached."""
        today = date.today()
        daily = await self._get_daily_risk(today)

        if daily is None:
            return True, None

        max_loss = settings.risk.max_daily_loss_pct * balance
        if abs(float(daily.total_pnl)) >= max_loss:
            return False, (
                f"Daily loss limit reached: {abs(float(daily.total_pnl)):.2f} "
                f">= {max_loss:.2f} ({settings.risk.max_daily_loss_pct*100}% of {balance:.2f})"
            )
        return True, None

    async def check_max_trades_today(self) -> tuple[bool, str | None]:
        """Check if max trades per day is reached."""
        today = date.today()
        daily = await self._get_daily_risk(today)

        if daily and daily.total_trades >= settings.risk.max_trades_per_day:
            return False, (
                f"Max trades/day reached: {daily.total_trades} "
                f">= {settings.risk.max_trades_per_day}"
            )
        return True, None

    def check_consecutive_losses(self) -> tuple[bool, str | None]:
        """Check consecutive loss limit."""
        if self._consecutive_losses >= settings.risk.max_consecutive_losses:
            return False, (
                f"Consecutive losses: {self._consecutive_losses} "
                f">= {settings.risk.max_consecutive_losses}"
            )
        return True, None

    def check_exposure(
        self, balance: float, total_exposure: float
    ) -> tuple[bool, str | None]:
        """Check total exposure limit."""
        max_exposure = settings.risk.max_exposure_pct * balance
        if total_exposure >= max_exposure:
            return False, (
                f"Max exposure reached: {total_exposure:.2f} "
                f">= {max_exposure:.2f} ({settings.risk.max_exposure_pct*100}%)"
            )
        return True, None

    def check_spread(self, current_spread: float) -> tuple[bool, str | None]:
        """Check if spread is within limits."""
        if current_spread > settings.risk.max_spread_pips:
            return False, (
                f"Spread too wide: {current_spread:.1f} "
                f"> {settings.risk.max_spread_pips} pips"
            )
        return True, None

    def record_win(self) -> None:
        """Record a winning trade — reset consecutive losses."""
        self._consecutive_losses = 0

    def record_loss(self) -> None:
        """Record a losing trade — increment consecutive losses."""
        self._consecutive_losses += 1

    async def _get_daily_risk(self, d: date) -> DailyRisk | None:
        """Get daily risk record."""
        result = await self._session.execute(
            select(DailyRisk).where(func.date(DailyRisk.trade_date) == d)
        )
        return result.scalar_one_or_none()
