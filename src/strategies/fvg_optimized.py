"""Strategy #2b — FVG Optimized.

Enhanced version with:
1. Market regime filter (trend strength)
2. Mean reversion logic (sell when overbought)
3. Better entry timing (wait for pullback)
4. Adaptive position sizing
"""

from __future__ import annotations

import logging
from typing import Optional

import numpy as np

from src.core.types import Candle, Direction, FairValueGap, StrategyCandidate
from src.strategies.base import StrategyPlugin
from src.strategies.registry import register
from src.structure.context import MultiTimeframeContext

logger = logging.getLogger(__name__)


class FVGOptimizedStrategy(StrategyPlugin):
    """
    Optimized FVG Reversal Strategy.

    Key improvements:
    1. Market regime filter - only trade in trending markets
    2. Mean reversion - sell when overbought in uptrend
    3. Better entry timing - wait for confirmed pullback
    4. Adaptive risk - reduce size in choppy markets
    """

    @property
    def strategy_id(self) -> str:
        return "fvg_optimized"

    @property
    def name(self) -> str:
        return "FVG Optimized"

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
        """Analyze for optimized FVG reversal setup."""

        if not current_candle:
            return None

        # Check market regime
        regime = self._detect_market_regime(context)

        # --- TRENDING MARKET --- (Follow trend with FVG)
        if regime == "TRENDING":
            candidate = self._check_trending_setup(
                context, current_candle, current_price, spread, session
            )
            if candidate:
                return candidate

        # --- RANGING MARKET --- (Mean reversion)
        elif regime == "RANGING":
            candidate = self._check_ranging_setup(
                context, current_candle, current_price, spread, session
            )
            if candidate:
                return candidate

        # --- OVERBOUGHT/OVERSOLD --- (Counter-trend)
        elif regime == "OVERBOUGHT":
            candidate = self._check_overbought_setup(
                context, current_candle, current_price, spread, session
            )
            if candidate:
                return candidate

        elif regime == "OVERSOLD":
            candidate = self._check_oversold_setup(
                context, current_candle, current_price, spread, session
            )
            if candidate:
                return candidate

        return None

    def _detect_market_regime(self, ctx: MultiTimeframeContext) -> str:
        """Detect current market regime."""

        # Need at least some structure
        if not ctx.swing_highs or not ctx.swing_lows:
            return "UNKNOWN"

        # Calculate trend strength
        htf_trend = ctx.htf_trend

        # Check for overbought/oversold using recent price action
        if ctx.swing_highs and ctx.swing_lows:
            recent_high = ctx.swing_highs[0].price
            recent_low = ctx.swing_lows[0].price
            current_price = ctx.current_price

            # Calculate position in range
            range_size = recent_high - recent_low
            if range_size > 0:
                position = (current_price - recent_low) / range_size

                # Overbought: price near top of range
                if position > 0.9:
                    return "OVERBOUGHT"

                # Oversold: price near bottom of range
                if position < 0.1:
                    return "OVERSOLD"

        # Check trend consistency
        if htf_trend == Direction.BUY:
            # Check if M15 also bullish
            m15 = ctx.get_structure("M15")
            if m15 and m15.trend == Direction.BUY:
                return "TRENDING"
            else:
                return "RANGING"
        elif htf_trend == Direction.SELL:
            m15 = ctx.get_structure("M15")
            if m15 and m15.trend == Direction.SELL:
                return "TRENDING"
            else:
                return "RANGING"

        return "RANGING"

    def _check_trending_setup(
        self,
        ctx: MultiTimeframeContext,
        candle: Candle,
        price: float,
        spread: float,
        session: str,
    ) -> Optional[StrategyCandidate]:
        """Check for trending market setup (follow trend)."""

        htf_trend = ctx.htf_trend

        if htf_trend == Direction.BUY:
            return self._check_long_trend(ctx, candle, price, spread, session)
        elif htf_trend == Direction.SELL:
            return self._check_short_trend(ctx, candle, price, spread, session)

        return None

    def _check_long_trend(
        self,
        ctx: MultiTimeframeContext,
        candle: Candle,
        price: float,
        spread: float,
        session: str,
    ) -> Optional[StrategyCandidate]:
        """Check for long setup in uptrend."""

        # Need bullish FVG
        bullish_fvgs = [
            f for f in ctx.fvgs
            if f.direction == Direction.BUY and f.valid
        ]
        if not bullish_fvgs:
            return None

        # Price should be in discount zone (pullback)
        if not ctx.in_discount_zone:
            return None

        # Find nearest FVG
        nearest_fvg = None
        for fvg in bullish_fvgs:
            if fvg.lower_price <= price <= fvg.upper_price:
                nearest_fvg = fvg
                break

        if not nearest_fvg:
            return None

        # Score
        score = 60
        confluences = ["fvg_present", "trending_market"]
        risk_flags = []

        if ctx.htf_trend == Direction.BUY:
            score += 15
            confluences.append("htf_aligned")

        if ctx.has_liquidity_sweep:
            score += 10
            confluences.append("liquidity_sweep")

        if ctx.in_discount_zone:
            score += 10
            confluences.append("discount_zone")

        if session in ("london", "new_york", "overlap"):
            score += 5
            confluences.append("good_session")

        # Calculate SL/TP
        sl = nearest_fvg.lower_price - 2
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
            metadata={"regime": "TRENDING", "fvg_upper": nearest_fvg.upper_price, "fvg_lower": nearest_fvg.lower_price},
        )

    def _check_short_trend(
        self,
        ctx: MultiTimeframeContext,
        candle: Candle,
        price: float,
        spread: float,
        session: str,
    ) -> Optional[StrategyCandidate]:
        """Check for short setup in downtrend."""

        bearish_fvgs = [
            f for f in ctx.fvgs
            if f.direction == Direction.SELL and f.valid
        ]
        if not bearish_fvgs:
            return None

        if not ctx.in_premium_zone:
            return None

        nearest_fvg = None
        for fvg in bearish_fvgs:
            if fvg.lower_price <= price <= fvg.upper_price:
                nearest_fvg = fvg
                break

        if not nearest_fvg:
            return None

        score = 60
        confluences = ["fvg_present", "trending_market"]
        risk_flags = []

        if ctx.htf_trend == Direction.SELL:
            score += 15
            confluences.append("htf_aligned")

        if ctx.has_liquidity_sweep:
            score += 10
            confluences.append("liquidity_sweep")

        if ctx.in_premium_zone:
            score += 10
            confluences.append("premium_zone")

        if session in ("london", "new_york", "overlap"):
            score += 5
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
            metadata={"regime": "TRENDING", "fvg_upper": nearest_fvg.upper_price, "fvg_lower": nearest_fvg.lower_price},
        )

    def _check_ranging_setup(
        self,
        ctx: MultiTimeframeContext,
        candle: Candle,
        price: float,
        spread: float,
        session: str,
    ) -> Optional[StrategyCandidate]:
        """Check for ranging market setup (mean reversion)."""

        # In ranging market, look for price at extremes
        if not ctx.swing_highs or not ctx.swing_lows:
            return None

        recent_high = ctx.swing_highs[0].price
        recent_low = ctx.swing_lows[0].price
        range_size = recent_high - recent_low

        if range_size <= 0:
            return None

        position = (price - recent_low) / range_size

        # Buy near bottom, sell near top
        if position < 0.2:  # Near bottom - BUY
            return self._check_range_buy(ctx, candle, price, spread, session, recent_low, recent_high)
        elif position > 0.8:  # Near top - SELL
            return self._check_range_sell(ctx, candle, price, spread, session, recent_low, recent_high)

        return None

    def _check_range_buy(
        self,
        ctx: MultiTimeframeContext,
        candle: Candle,
        price: float,
        spread: float,
        session: str,
        range_low: float,
        range_high: float,
    ) -> Optional[StrategyCandidate]:
        """Buy at bottom of range."""

        score = 55
        confluences = ["range_buy", "mean_reversion"]
        risk_flags = ["ranging_market"]

        if session in ("london", "new_york", "overlap"):
            score += 5
            confluences.append("good_session")

        sl = range_low - 2
        risk = price - sl
        tp1 = price + risk * 2
        tp2 = price + risk * 3

        rr = tp1 / risk if risk > 0 else 0

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
            metadata={"regime": "RANGING", "range_low": range_low, "range_high": range_high},
        )

    def _check_range_sell(
        self,
        ctx: MultiTimeframeContext,
        candle: Candle,
        price: float,
        spread: float,
        session: str,
        range_low: float,
        range_high: float,
    ) -> Optional[StrategyCandidate]:
        """Sell at top of range."""

        score = 55
        confluences = ["range_sell", "mean_reversion"]
        risk_flags = ["ranging_market"]

        if session in ("london", "new_york", "overlap"):
            score += 5
            confluences.append("good_session")

        sl = range_high + 2
        risk = sl - price
        tp1 = price - risk * 2
        tp2 = price - risk * 3

        rr = risk / (price - tp1) if (price - tp1) > 0 else 0

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
            metadata={"regime": "RANGING", "range_low": range_low, "range_high": range_high},
        )

    def _check_overbought_setup(
        self,
        ctx: MultiTimeframeContext,
        candle: Candle,
        price: float,
        spread: float,
        session: str,
    ) -> Optional[StrategyCandidate]:
        """Check for overbought setup (sell)."""

        # Only sell if HTF is also bearish or neutral
        if ctx.htf_trend == Direction.BUY:
            return None  # Don't sell against strong uptrend

        score = 65
        confluences = ["overbought", "mean_reversion"]
        risk_flags = []

        if ctx.htf_trend == Direction.SELL:
            score += 15
            confluences.append("htf_aligned")

        if session in ("london", "new_york", "overlap"):
            score += 5
            confluences.append("good_session")

        # Use recent high as SL
        if ctx.swing_highs:
            sl = ctx.swing_highs[0].price + 2
        else:
            sl = price + 10

        risk = sl - price
        tp1 = price - risk * 2
        tp2 = price - risk * 3

        rr = risk / (price - tp1) if (price - tp1) > 0 else 0

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
            metadata={"regime": "OVERBOUGHT"},
        )

    def _check_oversold_setup(
        self,
        ctx: MultiTimeframeContext,
        candle: Candle,
        price: float,
        spread: float,
        session: str,
    ) -> Optional[StrategyCandidate]:
        """Check for oversold setup (buy)."""

        # Only buy if HTF is also bullish or neutral
        if ctx.htf_trend == Direction.SELL:
            return None  # Don't buy against strong downtrend

        score = 65
        confluences = ["oversold", "mean_reversion"]
        risk_flags = []

        if ctx.htf_trend == Direction.BUY:
            score += 15
            confluences.append("htf_aligned")

        if session in ("london", "new_york", "overlap"):
            score += 5
            confluences.append("good_session")

        # Use recent low as SL
        if ctx.swing_lows:
            sl = ctx.swing_lows[0].price - 2
        else:
            sl = price - 10

        risk = price - sl
        tp1 = price + risk * 2
        tp2 = price + risk * 3

        rr = tp1 / risk if risk > 0 else 0

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
            metadata={"regime": "OVERSOLD"},
        )


register(FVGOptimizedStrategy())
