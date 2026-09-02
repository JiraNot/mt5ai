"""Rule-based AI scorer for strategy candidates."""

from __future__ import annotations

import logging

from src.core.config import settings
from src.core.types import AIDecision, StrategyCandidate
from src.structure.context import MultiTimeframeContext

logger = logging.getLogger(__name__)


class RuleBasedScorer:
    """
    Scores a StrategyCandidate based on confluences and context.

    Phase 1-4: Rule-based (explainable, tuneable)
    Phase 5+: ML model replaces/augments this
    """

    def __init__(self, weights: dict[str, int] | None = None) -> None:
        self._weights = weights or settings.ai.scoring_weights

    def score(
        self,
        candidate: StrategyCandidate,
        context: MultiTimeframeContext,
        spread: float = 0.0,
        session: str = "",
        news_nearby: bool = False,
    ) -> AIDecision:
        """
        Score a candidate and return an AIDecision.

        Starts with the strategy's rule_score and adds/subtracts
        context-based adjustments.
        """
        score = candidate.rule_score  # Start with strategy base score
        reasons = []
        risk_flags = list(candidate.risk_flags)  # Carry over strategy risk flags

        # ─── HTF Alignment ────────────────────────────────────────────────
        if context.htf_trend == candidate.direction:
            score += self._weights.get("htf_aligned", 15)
            reasons.append(f"HTF ({context.htf_trend.value}) aligned with trade")
        elif context.htf_trend is not None:
            score += self._weights.get("htf_conflict", -20)
            risk_flags.append(f"HTF ({context.htf_trend.value}) conflicts with trade")

        # ─── Session Quality ──────────────────────────────────────────────
        if session in ("london", "new_york", "overlap"):
            score += self._weights.get("session_london_ny", 10)
            reasons.append(f"{session.replace('_', ' ').title()} session active")
        elif session == "asian":
            score += self._weights.get("asian_session", -5)

        # ─── Spread Health ────────────────────────────────────────────────
        symbol_config = settings.symbols.get(candidate.symbol)
        normal_spread = symbol_config.normal_spread if symbol_config else 3.0
        max_spread = symbol_config.max_spread if symbol_config else 8.0

        if spread <= normal_spread:
            score += self._weights.get("spread_normal", 5)
        elif spread > max_spread:
            score += self._weights.get("spread_high", -30)
            risk_flags.append(f"Spread {spread:.1f} pips (abnormal)")

        # ─── Risk-Reward Quality ──────────────────────────────────────────
        if candidate.rr_ratio >= 3.0:
            score += self._weights.get("rr_excellent", 10)
            reasons.append(f"Excellent RR: 1:{candidate.rr_ratio:.1f}")
        elif candidate.rr_ratio < 2.0:
            risk_flags.append(f"Low RR: 1:{candidate.rr_ratio:.1f}")

        # ─── Confluence Bonuses ───────────────────────────────────────────
        if "liquidity_sweep" in candidate.confluences:
            score += self._weights.get("liquidity_sweep", 15)
            reasons.append("Sell-side liquidity swept")

        if "fvg_present" in candidate.confluences or "fvg_near_ob" in candidate.confluences:
            score += self._weights.get("fvg_confluence", 15)
            reasons.append("FVG confluence present")

        if "ob_fvg_overlap" in candidate.confluences:
            score += self._weights.get("ob_fvg_overlap", 20)
            reasons.append("OB/FVG overlap zone")

        if "choch_confirmed" in candidate.confluences:
            score += 10
            reasons.append("CHoCH confirmed")

        # ─── News Penalty ─────────────────────────────────────────────────
        if news_nearby:
            score += self._weights.get("near_news", -25)
            risk_flags.append("High-impact news within 30 min")

        # ─── Clamp Score ──────────────────────────────────────────────────
        score = max(0, min(100, score))

        # ─── Decision ─────────────────────────────────────────────────────
        min_threshold = settings.ai.min_combined_score
        if score >= min_threshold:
            decision = candidate.direction.value  # BUY or SELL
            reasons.append(f"Score {score} >= threshold {min_threshold}")
        else:
            decision = "WAIT"
            reasons.append(f"Score {score} < threshold {min_threshold}")

        confidence = score / 100.0

        logger.info(
            f"AI Score: {candidate.strategy_id} {candidate.direction.value} "
            f"score={score} decision={decision} confidence={confidence:.2f}"
        )

        return AIDecision(
            candidate=candidate,
            ai_score=score,
            combined_score=score,
            decision=decision,
            confidence=confidence,
            reasons=reasons,
            risk_flags=risk_flags,
        )
