"""Strategy #2 — FVG Reversal."""

from __future__ import annotations

import logging
from typing import Optional

from src.core.types import Candle, Direction, FairValueGap, StrategyCandidate
from src.strategies.base import StrategyPlugin
from src.strategies.registry import register
from src.structure.context import MultiTimeframeContext

logger = logging.getLogger(__name__)


class FVGReversalStrategy(StrategyPlugin):
    """
    FVG Reversal Strategy.

    Setup (Long):
    1. HTF = Bullish trend
    2. Liquidity Sweep of recent lows
    3. Bullish CHoCH/BOS on M15
    4. Bullish FVG detected
    5. Price retraces into FVG zone
    6. Price in Discount zone
    7. AI Score >= 75
    → BUY

    FVG is ONE evidence, not the only trigger.
    """

    @property
    def strategy_id(self) -> str:
        return "fvg_reversal"

    @property
    def name(self) -> str:
        return "FVG Reversal"

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
        """Analyze for FVG reversal setup."""

        if not current_candle:
            return None

        # --- LONG SETUP ---
        long_candidate = self._check_long_fvg(
            context, current_candle, current_price, spread, session
        )
        if long_candidate:
            return long_candidate

        # --- SHORT SETUP ---
        short_candidate = self._check_short_fvg(
            context, current_candle, current_price, spread, session
        )
        if short_candidate:
            return short_candidate

        return None

    def _check_long_fvg(
        self,
        ctx: MultiTimeframeContext,
        candle: Candle,
        price: float,
        spread: float,
        session: str,
    ) -> Optional[StrategyCandidate]:
        """Check for bullish FVG reversal."""

        # Need HTF bullish
        if ctx.htf_trend != Direction.BUY:
            return None

        # Need M15 bullish structure
        m15 = ctx.get_structure("M15")
        if not m15 or m15.trend != Direction.BUY:
            return None

        # Need a valid bullish FVG
        bullish_fvgs = [
            f for f in ctx.fvgs
            if f.direction == Direction.BUY and f.valid
        ]
        if not bullish_fvgs:
            return None

        # Check if price is retracing into the nearest FVG
        nearest_fvg = None
        for fvg in bullish_fvgs:
            if fvg.lower_price <= price <= fvg.upper_price:
                nearest_fvg = fvg
                break

        if not nearest_fvg:
            # Check if price is approaching FVG (within 1.5x zone size)
            for fvg in bullish_fvgs:
                distance = price - fvg.midpoint
                if 0 <= distance <= fvg.zone_size * 1.5:
                    nearest_fvg = fvg
                    break

        if not nearest_fvg:
            return None

        # Score confluences
        score = 50
        confluences = ["fvg_present"]
        risk_flags = []

        # HTF alignment
        if ctx.htf_trend == Direction.BUY:
            score += 15
            confluences.append("htf_aligned")

        # Liquidity sweep
        if ctx.has_liquidity_sweep:
            score += 15
            confluences.append("liquidity_sweep")

        # Discount zone
        if ctx.in_discount_zone:
            score += 10
            confluences.append("discount_zone")

        # CHoCH present
        if ctx.has_choch:
            score += 10
            confluences.append("choch_present")

        # Session
        if session in ("london", "new_york", "overlap"):
            score += 10
            confluences.append("good_session")

        # Spread
        if spread <= 3.0:
            score += 5
            confluences.append("tight_spread")

        # Calculate SL/TP
        sl = nearest_fvg.lower_price - 2  # Below FVG zone
        risk = price - sl
        tp1 = price + risk * 2
        tp2 = price + risk * 3

        rr = tp1 / risk if risk > 0 else 0
        if rr >= 3.0:
            score += 10
            confluences.append("excellent_rr")

        score = max(0, min(100, score))

        return StrategyCandidate(
            strategy_id=self.strategy_id,
            strategy_name=self.name,
            symbol=ctx.symbol,
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
                "fvg_upper": nearest_fvg.upper_price,
                "fvg_lower": nearest_fvg.lower_price,
                "fvg_tf": nearest_fvg.timeframe,
            },
        )

    def _check_short_fvg(
        self,
        ctx: MultiTimeframeContext,
        candle: Candle,
        price: float,
        spread: float,
        session: str,
    ) -> Optional[StrategyCandidate]:
        """Check for bearish FVG reversal."""

        if ctx.htf_trend != Direction.SELL:
            return None

        m15 = ctx.get_structure("M15")
        if not m15 or m15.trend != Direction.SELL:
            return None

        bearish_fvgs = [
            f for f in ctx.fvgs
            if f.direction == Direction.SELL and f.valid
        ]
        if not bearish_fvgs:
            return None

        nearest_fvg = None
        for fvg in bearish_fvgs:
            if fvg.lower_price <= price <= fvg.upper_price:
                nearest_fvg = fvg
                break

        if not nearest_fvg:
            for fvg in bearish_fvgs:
                distance = fvg.midpoint - price
                if 0 <= distance <= fvg.zone_size * 1.5:
                    nearest_fvg = fvg
                    break

        if not nearest_fvg:
            return None

        score = 50
        confluences = ["fvg_present"]
        risk_flags = []

        if ctx.htf_trend == Direction.SELL:
            score += 15
            confluences.append("htf_aligned")

        if ctx.has_liquidity_sweep:
            score += 15
            confluences.append("liquidity_sweep")

        if ctx.in_premium_zone:
            score += 10
            confluences.append("premium_zone")

        if ctx.has_choch:
            score += 10
            confluences.append("choch_present")

        if session in ("london", "new_york", "overlap"):
            score += 10
            confluences.append("good_session")

        sl = nearest_fvg.upper_price + 2
        risk = sl - price
        tp1 = price - risk * 2
        tp2 = price - risk * 3

        rr = risk / (price - tp1) if (price - tp1) > 0 else 0
        if rr >= 3.0:
            score += 10
            confluences.append("excellent_rr")

        score = max(0, min(100, score))

        return StrategyCandidate(
            strategy_id=self.strategy_id,
            strategy_name=self.name,
            symbol=ctx.symbol,
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
                "fvg_upper": nearest_fvg.upper_price,
                "fvg_lower": nearest_fvg.lower_price,
            },
        )


register(FVGReversalStrategy())
