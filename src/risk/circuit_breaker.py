"""Circuit breaker — emergency stop when losses exceed threshold."""

from __future__ import annotations

import logging
from datetime import date

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.core.events import EventType, event_bus
from src.storage.models import DailyRisk

logger = logging.getLogger(__name__)


class CircuitBreaker:
    """
    Emergency stop mechanism.

    Triggers when:
    - Daily loss exceeds emergency_stop_loss_pct
    - Account drawdown exceeds threshold
    - Manual trigger via system event

    When triggered:
    - All new trades blocked
    - Open positions may be force-closed
    - CIRCUIT_BREAKER event published
    """

    def __init__(self) -> None:
        self._triggered = False
        self._trigger_reason: str = ""
        self._triggered_at: str = ""

    @property
    def is_triggered(self) -> bool:
        return self._triggered

    @property
    def trigger_reason(self) -> str:
        return self._trigger_reason

    async def check(
        self,
        balance: float,
        equity: float,
        session: AsyncSession | None = None,
    ) -> bool:
        """
        Check if circuit breaker should trigger.

        Returns True if safe to continue, False if breaker triggered.
        """
        if self._triggered:
            return False

        # Check emergency loss threshold
        drawdown = balance - equity
        dd_pct = drawdown / balance if balance > 0 else 0

        if dd_pct >= settings.risk.emergency_stop_loss_pct:
            await self._trigger(
                f"Account drawdown {dd_pct*100:.1f}% >= "
                f"emergency threshold {settings.risk.emergency_stop_loss_pct*100}%"
            )
            return False

        # Check daily circuit breaker in DB
        if session:
            today = date.today()
            result = await session.execute(
                select(DailyRisk).where(func.date(DailyRisk.trade_date) == today)
            )
            daily = result.scalar_one_or_none()
            if daily and daily.circuit_breaker:
                await self._trigger("Daily circuit breaker active in database")
                return False

        return True

    async def _trigger(self, reason: str) -> None:
        """Activate the circuit breaker."""
        self._triggered = True
        self._trigger_reason = reason

        logger.critical(f"CIRCUIT BREAKER TRIGGERED: {reason}")
        await event_bus.publish(EventType.CIRCUIT_BREAKER, {
            "reason": reason,
        })

    def reset(self) -> None:
        """Manually reset the circuit breaker (requires explicit action)."""
        logger.warning("Circuit breaker manually RESET")
        self._triggered = False
        self._trigger_reason = ""
