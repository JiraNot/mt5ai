"""Setup Logger — logs EVERY candidate setup (traded + skipped + rejected)."""

from __future__ import annotations

import logging

from sqlalchemy.ext.asyncio import AsyncSession

from src.core.types import (
    AIDecision,
    RiskDecision,
    SetupDecision,
    StrategyCandidate,
)
from src.storage.repository import Repository

logger = logging.getLogger(__name__)


class SetupLogger:
    """
    Logs every candidate setup to the database.

    This is critical for:
    1. Measuring AI filter effectiveness
    2. Building ML training dataset
    3. Strategy performance analysis
    4. Post-trade review

    We log:
    - ALL candidates from strategy engine
    - AI score and decision
    - Risk engine decision
    - Outcome (if traded)
    """

    def __init__(self, session: AsyncSession) -> None:
        self._repo = Repository(session)

    async def log_candidate(
        self,
        candidate: StrategyCandidate,
        ai_decision: AIDecision | None = None,
        risk_decision: RiskDecision | None = None,
        decision: SetupDecision = SetupDecision.SKIPPED,
        rejection_reason: str | None = None,
    ) -> int:
        """
        Log a candidate setup.

        Returns the setup ID for linking to trades later.
        """
        ai_score = ai_decision.combined_score if ai_decision else None
        combined_score = ai_decision.combined_score if ai_decision else candidate.rule_score

        if risk_decision and not risk_decision.approved:
            decision = SetupDecision.REJECTED
            rejection_reason = risk_decision.rejection_reason

        setup_id = await self._repo.log_setup(
            candidate=candidate,
            decision=decision,
            ai_score=ai_score,
            combined_score=combined_score,
            rejection_reason=rejection_reason,
        )

        logger.info(
            f"Setup #{setup_id}: {candidate.strategy_id} {candidate.direction.value} "
            f"{candidate.symbol} rule={candidate.rule_score} ai={ai_score} "
            f"decision={decision.value}"
        )

        return setup_id

    async def log_traded(
        self,
        candidate: StrategyCandidate,
        ai_decision: AIDecision,
        risk_decision: RiskDecision,
    ) -> int:
        """Log a setup that was approved and traded."""
        return await self.log_candidate(
            candidate=candidate,
            ai_decision=ai_decision,
            risk_decision=risk_decision,
            decision=SetupDecision.TRADED,
        )

    async def log_skipped(
        self,
        candidate: StrategyCandidate,
        reason: str = "AI score below threshold",
    ) -> int:
        """Log a setup that was skipped by AI."""
        return await self.log_candidate(
            candidate=candidate,
            decision=SetupDecision.SKIPPED,
            rejection_reason=reason,
        )

    async def log_rejected(
        self,
        candidate: StrategyCandidate,
        ai_decision: AIDecision,
        risk_decision: RiskDecision,
    ) -> int:
        """Log a setup that was rejected by risk engine."""
        return await self.log_candidate(
            candidate=candidate,
            ai_decision=ai_decision,
            risk_decision=risk_decision,
            decision=SetupDecision.REJECTED,
        )
