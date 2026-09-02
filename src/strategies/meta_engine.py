"""Meta Decision Engine — runs all strategies and combines votes."""

from __future__ import annotations

import logging
from datetime import datetime

from src.core.config import settings
from src.core.types import StrategyCandidate
from src.strategies.registry import get_all_strategies
from src.structure.context import MultiTimeframeContext

logger = logging.getLogger(__name__)


class MetaDecisionEngine:
    """
    Orchestrates all strategy plugins and combines their outputs.

    Flow:
    1. Run all registered strategies
    2. Collect candidates
    3. Score and rank by rule_score
    4. Return candidates that pass minimum threshold
    """

    def __init__(self, min_combined_score: int | None = None) -> None:
        self._min_score = min_combined_score or settings.ai.min_combined_score

    async def evaluate(
        self,
        context: MultiTimeframeContext,
        current_price: float,
        spread: float,
        session: str,
    ) -> list[StrategyCandidate]:
        """
        Run all strategies and return valid candidates sorted by score.
        """
        strategies = get_all_strategies()
        candidates: list[StrategyCandidate] = []

        for strategy_id, strategy in strategies.items():
            try:
                candidate = strategy.analyze(
                    context=context,
                    current_candle=context.primary_candle,
                    current_price=current_price,
                    spread=spread,
                    session=session,
                )

                if candidate is None:
                    continue

                # Apply minimum score filter
                if candidate.rule_score < self._min_score:
                    logger.debug(
                        f"{strategy_id}: score {candidate.rule_score} < {self._min_score} — skipped"
                    )
                    continue

                candidates.append(candidate)
                logger.info(
                    f"{strategy_id}: {candidate.direction.value} "
                    f"score={candidate.rule_score} RR=1:{candidate.rr_ratio:.1f}"
                )

            except Exception as e:
                logger.error(f"Strategy {strategy_id} error: {e}", exc_info=True)

        # Sort by rule_score descending
        candidates.sort(key=lambda c: c.rule_score, reverse=True)

        if candidates:
            logger.info(
                f"Meta engine: {len(candidates)} candidates found "
                f"(best: {candidates[0].strategy_id} score={candidates[0].rule_score})"
            )

        return candidates

    def get_candidates_by_strategy(
        self, candidates: list[StrategyCandidate]
    ) -> dict[str, list[StrategyCandidate]]:
        """Group candidates by strategy_id."""
        result: dict[str, list[StrategyCandidate]] = {}
        for c in candidates:
            result.setdefault(c.strategy_id, []).append(c)
        return result
