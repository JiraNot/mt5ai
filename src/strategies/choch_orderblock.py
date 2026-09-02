"""Strategy #3 — CHoCH + Order Block."""

from __future__ import annotations

import logging
from typing import Optional

from src.core.types import Candle, Direction, OrderBlock, StrategyCandidate
from src.strategies.base import StrategyPlugin
from src.strategies.registry import register
from src.structure.context import MultiTimeframeContext

logger = logging.getLogger(__name__)


class CHOCHOrderBlockStrategy(StrategyPlugin):
    """
    CHoCH + Order Block Strategy — PRIMARY STRATEGY.

    Setup (Long):
    1. Downtrend (Lower Lows, Lower Highs)
    2. Liquidity Sweep of recent low
    3. Strong displacement upward
    4. Bullish CHoCH confirmed
    5. Bullish FVG created during displacement
    6. Find Last Bearish Candle before displacement = Bullish OB
    7. Wait for price retracement into OB zone
    8. OB + FVG overlap = best confluence
    9. HTF bullish alignment
    10. RR >= 1:2
    → BUY

    This is the highest-probability strategy in the system.
    """

    @property
    def strategy_id(self) -> str:
        return "choch_orderblock"

    @property
    def name(self) -> str:
        return "CHoCH + Order Block"

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
        """Analyze for CHoCH + Order Block setup."""

        if not current_candle:
            return None

        # --- LONG SETUP ---
        long = self._check_long_choch_ob(
            context, current_candle, current_price, spread, session
        )
        if long:
            return long

        # --- SHORT SETUP ---
        short = self._check_short_choch_ob(
            context, current_candle, current_price, spread, session
        )
        if short:
            return short

        return None

    def _check_long_choch_ob(
        self,
        ctx: MultiTimeframeContext,
        candle: Candle,
        price: float,
        spread: float,
        session: str,
    ) -> Optional[StrategyCandidate]:
        """Check for bullish CHoCH + OB setup."""

        # Need M15 bullish CHoCH
        m15 = ctx.get_structure("M15")
        if not m15:
            return None

        has_choch = m15.choch is not None and m15.trend == Direction.BUY
        has_bos = m15.bos is not None and m15.trend == Direction.BUY

        if not (has_choch or has_bos):
            return None

        # Need bullish Order Block
        bullish_obs = [
            ob for ob in ctx.order_blocks
            if ob.direction == Direction.BUY and not ob.mitigated
        ]
        if not bullish_obs:
            return None

        # Find nearest OB to current price (price should be retracing into it)
        nearest_ob = None
        for ob in bullish_obs:
            # Price should be approaching or inside the OB zone
            if ob.lower_price - 3 <= price <= ob.upper_price + 3:
                nearest_ob = ob
                break

        if not nearest_ob:
            return None

        # Score confluences (ICT-based scoring)
        score = 55  # Base (higher for this premium strategy)
        confluences = []
        risk_flags = []

        # CHoCH confirmed
        if has_choch:
            score += 15
            confluences.append("choch_confirmed")
        elif has_bos:
            score += 10
            confluences.append("bos_confirmed")

        # Liquidity sweep
        if ctx.has_liquidity_sweep:
            score += 15
            confluences.append("liquidity_sweep")

        # OB/FVG overlap (highest confluence)
        if nearest_ob.fvg_overlap:
            score += 20
            confluences.append("ob_fvg_overlap")
        elif ctx.has_ob_fvg_overlap:
            score += 10
            confluences.append("fvg_near_ob")

        # HTF alignment
        if ctx.htf_trend == Direction.BUY:
            score += 15
            confluences.append("htf_aligned")
        elif ctx.htf_trend == Direction.SELL:
            score -= 20
            risk_flags.append("htf_conflict")

        # Discount zone
        if ctx.in_discount_zone:
            score += 10
            confluences.append("discount_zone")

        # Session quality
        if session in ("london", "new_york", "overlap"):
            score += 10
            confluences.append("good_session")
        elif session == "asian":
            score -= 5

        # Spread
        if spread <= 3.0:
            score += 5
            confluences.append("tight_spread")

        # Calculate SL/TP
        sl = nearest_ob.lower_price - 2  # Below OB zone
        risk = price - sl
        tp1 = price + risk * 2  # 1:2 RR
        tp2 = price + risk * 3  # 1:3 RR

        rr = tp1 / risk if risk > 0 else 0
        if rr >= 3.0:
            score += 10
            confluences.append("excellent_rr")
        elif rr < 2.0:
            score -= 10
            risk_flags.append("low_rr")

        # OB strength
        if nearest_ob.strength >= 4:
            score += 5
            confluences.append("strong_ob")

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
                "ob_upper": nearest_ob.upper_price,
                "ob_lower": nearest_ob.lower_price,
                "ob_strength": nearest_ob.strength,
                "ob_fvg_overlap": nearest_ob.fvg_overlap,
            },
        )

    def _check_short_choch_ob(
        self,
        ctx: MultiTimeframeContext,
        candle: Candle,
        price: float,
        spread: float,
        session: str,
    ) -> Optional[StrategyCandidate]:
        """Check for bearish CHoCH + OB setup."""

        m15 = ctx.get_structure("M15")
        if not m15:
            return None

        has_choch = m15.choch is not None and m15.trend == Direction.SELL
        has_bos = m15.bos is not None and m15.trend == Direction.SELL

        if not (has_choch or has_bos):
            return None

        bearish_obs = [
            ob for ob in ctx.order_blocks
            if ob.direction == Direction.SELL and not ob.mitigated
        ]
        if not bearish_obs:
            return None

        nearest_ob = None
        for ob in bearish_obs:
            if ob.lower_price - 3 <= price <= ob.upper_price + 3:
                nearest_ob = ob
                break

        if not nearest_ob:
            return None

        score = 55
        confluences = []
        risk_flags = []

        if has_choch:
            score += 15
            confluences.append("choch_confirmed")
        elif has_bos:
            score += 10
            confluences.append("bos_confirmed")

        if ctx.has_liquidity_sweep:
            score += 15
            confluences.append("liquidity_sweep")

        if nearest_ob.fvg_overlap:
            score += 20
            confluences.append("ob_fvg_overlap")

        if ctx.htf_trend == Direction.SELL:
            score += 15
            confluences.append("htf_aligned")
        elif ctx.htf_trend == Direction.BUY:
            score -= 20
            risk_flags.append("htf_conflict")

        if ctx.in_premium_zone:
            score += 10
            confluences.append("premium_zone")

        if session in ("london", "new_york", "overlap"):
            score += 10
            confluences.append("good_session")

        sl = nearest_ob.upper_price + 2
        risk = sl - price
        tp1 = price - risk * 2
        tp2 = price - risk * 3

        rr = risk / (price - tp1) if (price - tp1) > 0 else 0
        if rr >= 3.0:
            sc
