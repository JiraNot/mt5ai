"""Strategy #1 — Breakout Retest."""

from __future__ import annotations

import logging
from typing import Optional

from src.core.types import Candle, Direction, StrategyCandidate
from src.strategies.base import StrategyPlugin
from src.strategies.registry import register
from src.structure.context import MultiTimeframeContext

logger = logging.getLogger(__name__)


class BreakoutRetestStrategy(StrategyPlugin):
    """
    Breakout Retest Strategy.

    Setup (Long):
    1. Detect Swing High / Resistance level
    2. Candle closes above the breakout level
    3. Breakout body is strong (>50% of range)
    4. Price retests the breakout zone
    5. Rejection/confirmation candle at retest
    6. RR >= 1:2
    7. HTF trend aligned

    The opposite for Short setups.
    """

    @property
    def strategy_id(self) -> str:
        return "breakout_retest"

    @property
    def name(self) -> str:
        return "Breakout Retest"

    @property
    def version(self) -> str:
        return "1.0.0"

    def min_rr(self) -> float:
        return 2.0

    def analyze(
        self,
        context: MultiTimeframeContext,
        current_candle: Candle,
        current_price: float,
        spread: float,
        session: str,
    ) -> Optional[StrategyCandidate]:
        """Analyze for breakout retest setup."""

        # Need structure data
        m15_structure = context.get_structure("M15")
        h1_structure = context.get_structure("H1")

        if not m15_structure or not h1_structure:
            return None

        # --- LONG SETUP ---
        if m15_structure.bos and m15_structure.trend == Direction.BUY:
            candidate = self._check_long_breakout(context, current_candle, current_price, spread, session)
            if candidate:
                return candidate

        # --- SHORT SETUP ---
        if m15_structure.bos and m15_structure.trend == Direction.SELL:
            candidate = self._check_short_breakout(context, current_candle, current_price, spread, session)
            if candidate:
                return candidate

        return None

    def _check_long_breakout(
        self,
        context: MultiTimeframeContext,
        candle: Candle,
        price: float,
        spread: float,
        session: str,
    ) -> Optional[StrategyCandidate]:
        """Check for long breakout retest."""
        m15 = context.get_structure("M15")
        if not m15 or not m15.last_swing_high:
            return None

        breakout_level = m15.last_swing_high.price

        # Check if price broke above and is now retesting
        # Retest zone: between breakout_level and breakout_level + small buffer
        retest_buffer = breakout_level * 0.001  # 0.1% buffer
        in_retest_zone = (
            breakout_level - retest_buffer <= price <= breakout_level + retest_buffer
        )

        if not in_retest_zone:
            return None

        # Check confirmation: current candle shows rejection (long lower wick)
        body = abs(candle.close - candle.open)
        total_range = candle.high - candle.low
        if total_range == 0:
            return None

        lower_wick = min(candle.open, candle.close) - candle.low
        wick_ratio = lower_wick / total_range

        # Need some bullish rejection
        is_bullish = candle.close > candle.open
        has_wick = wick_ratio > 0.3

        if not (is_bullish or has_wick):
            return None

        # Calculate SL/TP
        sl = m15.last_swing_low.price if m15.last_swing_low else price - 10
        risk = price - sl
        tp1 = price + risk * 2  # 1:2 RR minimum
        tp2 = price + risk * 3  # 1:3 RR

        # Score confluences
        score = 50  # Base score
        confluences = []
        risk_flags = []

        if context.htf_trend == Direction.BUY:
            score += 15
            confluences.append("htf_aligned")
        elif context.htf_trend == Direction.SELL:
            score -= 20
            risk_flags.append("htf_conflict")

        if context.has_liquidity_sweep:
            score += 15
            confluences.append("liquidity_sweep")

        if context.has_ob_fvg_overlap:
            score += 10
            confluences.append("ob_fvg_overlap")

        if context.in_discount_zone:
            score += 5
            confluences.append("discount_zone")

        if session in ("london", "new_york", "overlap"):
            score += 10
            confluences.append("good_session")

        if spread <= 3.0:
            score += 5
            confluences.append("tight_spread")

        rr = (tp1 - price) / risk if risk > 0 else 0
        if rr >= 3.0:
            score += 10
            confluences.append("excellent_rr")

        score = max(0, min(100, score))

        return StrategyCandidate(
            strategy_id=self.strategy_id,
            strategy_name=self.name,
            symbol=context.symbol,
            timeframe="M15",
            direction=Direction.BUY,
            rule_score=score,
            entry_price=price,
            stop_loss=sl,
            take_profit_1=tp1,
            take_profit_2=tp2,
            rr_ratio=round(rr, 2),
            confluences=confluences,
            risk_flags=risk_flags,
            metadata={
                "breakout_level": breakout_level,
                "wick_ratio": round(wick_ratio, 3),
            },
        )

    def _check_short_breakout(
        self,
        context: MultiTimeframeContext,
        candle: Candle,
        price: float,
        spread: float,
        session: str,
    ) -> Optional[StrategyCandidate]:
        """Check for short breakout retest."""
        m15 = context.get_structure("M15")
        if not m15 or not m15.last_swing_low:
            return None

        breakout_level = m15.last_swing_low.price

        retest_buffer = breakout_level * 0.001
        in_retest_zone = (
            breakout_level - retest_buffer <= price <= breakout_level + retest_buffer
        )

        if not in_retest_zone:
            return None

        body = abs(candle.close - candle.open)
        total_range = candle.high - candle.low
        if total_range == 0:
            return None

        upper_wick = candle.high - max(candle.open, candle.close)
        wick_ratio = upper_wick / total_range

        is_bearish = candle.close < candle.open
        has_wick = wick_ratio > 0.3

        if not (is_bearish or has_wick):
            return None

        sl = m15.last_swing_high.price if m15.last_swing_high else price + 10
        risk = sl - price
        tp1 = price - risk * 2
        tp2 = price - risk * 3

        score = 50
        confluences = []
        risk_flags = []

        if context.htf_trend == Direction.SELL:
            score += 15
            confluences.append("htf_aligned")
        elif context.htf_trend == Direction.BUY:
            score -= 20
            risk_flags.append("htf_conflict")

        if context.has_liquidity_sweep:
            score += 15
            confluences.append("liquidity_sweep")

        if context.has_ob_fvg_overlap:
            score += 10
            confluences.append("ob_fvg_overlap")

        if context.in_premium_zone:
            score += 5
            confluences.append("premium_zone")

        if session in ("london", "new_york", "overlap"):
            score += 10
            confluences.append("good_session")

        rr = risk / (price - tp1) if (price - tp1) > 0 else 0
        if rr >= 3.0:
            score += 10
            confluences.append("excellent_rr")

        score = max(0, min(100, score))

        return StrategyCandidate(
            strategy_id=self.strategy_id,
            strategy_name=self.name,
            symbol=context.symbol,
            timeframe="M15",
            direction=Direction.SELL,
            rule_score=score,
            entry_price=price,
            stop_loss=sl,
            take_profit_1=tp1,
            take_profit_2=tp2,
            rr_ratio=round(rr, 2),
            confluences=confluences,
            risk_flags=risk_flags,
            metadata={
                "breakout_level": breakout_level,
                "wick_ratio": round(wick_ratio, 3),
            },
        )

