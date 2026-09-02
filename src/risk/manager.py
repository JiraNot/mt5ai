"""Risk Engine — the supreme authority over all trade decisions."""

from __future__ import annotations

import logging

from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.core.types import (
    AIDecision,
    Direction,
    RiskDecision,
    StrategyCandidate,
)
from src.risk.circuit_breaker import CircuitBreaker
from src.risk.filters import TradeFilter
from src.risk.limits import LimitChecker
from src.market.spread_monitor import SpreadMonitor

logger = logging.getLogger(__name__)


class RiskEngine:
    """
    THE SUPREME AUTHORITY.

    AI cannot override this layer. Every trade must pass through here.
    Checks: filters → limits → position sizing → circuit breaker.

    Decision flow:
        Candidate → AI Decision → Risk Engine → APPROVED / REJECTED
    """

    def __init__(
        self,
        session: AsyncSession,
        spread_monitor: SpreadMonitor | None = None,
    ) -> None:
        self._session = session
        self._filters = TradeFilter(spread_monitor)
        self._limits = LimitChecker(session)
        self._circuit_breaker = CircuitBreaker()

    @property
    def circuit_breaker(self) -> CircuitBreaker:
        return self._circuit_breaker

    async def evaluate(
        self,
        candidate: StrategyCandidate,
        ai_decision: AIDecision,
        account_balance: float,
        account_equity: float,
        open_positions_count: int = 0,
        total_exposure: float = 0.0,
        current_spread: float = 0.0,
        session: str | None = None,
    ) -> RiskDecision:
        """
        Full risk evaluation pipeline.

        1. Circuit breaker check
        2. Trade filters (RR, session, spread, AI confidence)
        3. Risk limits (daily DD, max trades, consecutive losses, exposure)
        4. Position sizing
        5. Return RiskDecision
        """

        # Step 1: Circuit breaker
        cb_safe = await self._circuit_breaker.check(
            balance=account_balance,
            equity=account_equity,
            session=self._session,
        )
        if not cb_safe:
            return self._reject(
                candidate,
                f"Circuit breaker active: {self._circuit_breaker.trigger_reason}",
                account_balance,
                open_positions_count,
                total_exposure,
            )

        # Step 2: Trade filters
        filter_pass, filter_reason = self._filters.check_all(
            candidate=candidate,
            decision=ai_decision,
            current_spread=current_spread,
            session=session,
        )
        if not filter_pass:
            return self._reject(
                candidate,
                filter_reason or "Filter rejected",
                account_balance,
                open_positions_count,
                total_exposure,
            )

        # Step 3: Risk limits
        limit_pass, limit_reason = await self._limits.check_all(
            balance=account_balance,
            open_positions_count=open_positions_count,
            total_exposure=total_exposure,
            current_spread=current_spread,
        )
        if not limit_pass:
            return self._reject(
                candidate,
                limit_reason or "Limit rejected",
                account_balance,
                open_positions_count,
                total_exposure,
            )

        # Step 4: Position sizing
        position_size = self._calculate_position_size(
            candidate=candidate,
            balance=account_balance,
        )

        risk_amount = account_balance * settings.risk.risk_per_trade_pct
        risk_pct = settings.risk.risk_per_trade_pct

        logger.info(
            f"RISK APPROVED: {candidate.direction.value} {candidate.symbol} "
            f"size={position_size:.2f} lots, risk=${risk_amount:.2f} ({risk_pct*100}%)"
        )

        return RiskDecision(
            approved=True,
            position_size_lots=position_size,
            risk_amount=risk_amount,
            risk_pct=risk_pct,
            adjusted_sl=candidate.stop_loss,
            adjusted_tp1=candidate.take_profit_1,
            adjusted_tp2=candidate.take_profit_2,
            daily_loss_remaining=(
                settings.risk.max_daily_loss_pct * account_balance
            ),
            trades_today=open_positions_count,
            exposure_current=total_exposure,
        )

    def _calculate_position_size(
        self,
        candidate: StrategyCandidate,
        balance: float,
    ) -> float:
        """
        Calculate position size based on fixed risk %.

        Formula:
            risk_amount = balance * risk_per_trade_pct
            sl_distance = abs(entry - sl)
            volume = risk_amount / (sl_distance * contract_size)

        For XAUUSD: contract_size = 100, pip_value = 0.1
        """
        risk_amount = balance * settings.risk.risk_per_trade_pct
        sl_distance = abs(candidate.entry_price - candidate.stop_loss)

        if sl_distance <= 0:
            return 0.0

        # For XAUUSD: 1 lot = 100 oz, each $1 move = $100
        # volume (lots) = risk_amount / (sl_distance * contract_size)
        symbol_config = settings.symbols.get(candidate.symbol)
        contract_size = symbol_config.contract_size if symbol_config else 100

        volume = risk_amount / (sl_distance * contract_size)

        # Round to volume step
        volume_step = symbol_config.volume_step if symbol_config else 0.01
        volume = round(volume / volume_step) * volume_step

        # Clamp to min/max
        min_vol = symbol_config.min_volume if symbol_config else 0.01
        max_vol = symbol_config.max_volume if symbol_config else 100.0
        volume = max(min_vol, min(max_vol, volume))

        return round(volume, 2)

    def _reject(
        self,
        candidate: StrategyCandidate,
        reason: str,
        balance: float,
        open_positions: int,
        exposure: float,
    ) -> RiskDecision:
        """Create a rejection RiskDecision."""
        logger.warning(
            f"RISK REJECTED: {candidate.strategy_id} {candidate.direction.value} "
            f"{candidate.symbol} — {reason}"
        )
        return RiskDecision(
            approved=False,
            rejection_reason=reason,
            daily_loss_remaining=(
                settings.risk.max_daily_loss_pct * balance
            ),
            trades_today=open_positions,
            exposure_current=exposure,
        )

    def on_trade_result(self, profit: float) -> None:
        """Update internal state after a trade closes."""
        if profit >= 0:
            self._limits.record_win()
        else:
            self._limits.record_loss()
