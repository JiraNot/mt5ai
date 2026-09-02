"""AI context analyzer — provides additional context for scoring."""

from __future__ import annotations

import logging

from src.core.types import Direction
from src.market.session_tracker import get_current_session
from src.market.spread_monitor import SpreadMonitor
from src.structure.context import MultiTimeframeContext

logger = logging.getLogger(__name__)


class ContextAnalyzer:
    """
    Analyzes broader context for AI scoring.

    Provides additional signals beyond what individual strategies see:
    - Multi-timeframe confluence strength
    - Session quality
    - Volatility assessment
    - News proximity (future)
    """

    def analyze(
        self,
        context: MultiTimeframeContext,
        spread_monitor: SpreadMonitor | None = None,
    ) -> dict:
        """
        Produce a context analysis dict for the scorer.
        """
        session = get_current_session()
        spread_status = "unknown"
        if spread_monitor:
            spread_status = spread_monitor.get_spread_status()

        # Multi-TF trend alignment
        trends = {}
        for tf in ["H4", "H1", "M15", "M5"]:
            trend = context.get_trend(tf)
            if trend:
                trends[tf] = trend.value

        # Count aligned trends
        h4_trend = context.get_trend("H4")
        aligned_count = sum(
            1 for tf, t in trends.items()
            if Direction(t) == h4_trend
        )

        return {
            "session": session,
            "spread_status": spread_status,
            "htf_trend": context.htf_trend.value if context.htf_trend else None,
            "multi_tf_trends": trends,
            "trend_alignment": aligned_count,
            "has_choch": context.has_choch,
            "has_bos": context.has_bos,
            "has_liquidity_sweep": context.has_liquidity_sweep,
            "has_ob_fvg_overlap": context.has_ob_fvg_overlap,
            "premium_discount": (
                context.get_structure("M15").premium_discount
                if context.get_structure("M15")
                else "neutral"
            ),
        }
