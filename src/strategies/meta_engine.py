"""Meta Decision Engine — runs all strategies and combines votes with adaptive weighting."""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

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
    3. Apply dynamic learning adjustments (+/- score based on past outcomes)
    4. Score and rank by rule_score
    5. Return candidates that pass minimum threshold
    """

    def __init__(self, min_combined_score: int | None = None) -> None:
        self._min_score = min_combined_score or settings.ai.min_combined_score
        # strategy_id -> {"score_delta": int, "wins": int, "losses": int, "last_reason": str}
        self._strategy_health: dict[str, dict[str, Any]] = {}

    def adjust_strategy(self, strategy_id: str, outcome: str, reason: str = "") -> None:
        """ปรับน้ำหนักความเชื่อมั่นของกลยุทธ์ตามผลการเทรดจริง (Continuous Adaptation)."""
        if strategy_id not in self._strategy_health:
            self._strategy_health[strategy_id] = {
                "score_delta": 0,
                "wins": 0,
                "losses": 0,
                "consecutive_losses": 0,
                "last_reason": "",
            }

        health = self._strategy_health[strategy_id]

        if outcome == "WIN":
            health["wins"] += 1
            health["consecutive_losses"] = 0
            health["score_delta"] = min(15, health["score_delta"] + 3)  # Bonus up to +15
            health["last_reason"] = f"Win reward (+3): {reason}"
            logger.info(f"📈 Strategy {strategy_id} rewarded: delta={health['score_delta']}")
        elif outcome == "LOSS":
            health["losses"] += 1
            health["consecutive_losses"] += 1
            # Penalty increases with consecutive losses
            penalty = -5 if health["consecutive_losses"] == 1 else -10
            health["score_delta"] = max(-25, health["score_delta"] + penalty)  # Penalty down to -25
            health["last_reason"] = f"Loss penalty ({penalty}): {reason}"
            logger.info(f"📉 Strategy {strategy_id} penalized: delta={health['score_delta']} (Consecutive: {health['consecutive_losses']})")

    def get_strategy_health(self) -> dict[str, dict[str, Any]]:
        """ดึงข้อมูลสุขภาพของแต่ละกลยุทธ์สำหรับ Dashboard."""
        return dict(self._strategy_health)

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

                # Apply continuous learning adaptive score adjustment
                if strategy_id in self._strategy_health:
                    delta = self._strategy_health[strategy_id].get("score_delta", 0)
                    if delta != 0:
                        original_score = candidate.rule_score
                        candidate.rule_score = max(0, min(100, candidate.rule_score + delta))
                        logger.debug(
                            f"Adaptive adjustment for {strategy_id}: "
                            f"{original_score} -> {candidate.rule_score} (delta={delta:+d})"
                        )

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
