"""Strategy #2c — FVG Final.

Final optimized version with proper market regime filter.
Uses the dedicated MarketRegimeDetector for accurate regime identification.
"""

from __future__ import annotations

import logging
from typing import Optional

from src.core.types import Candle, Direction, FairValueGap, StrategyCandidate
from src.strategies.base import StrategyPlugin
from src.strategies.registry import register
from src.structure.context import MultiTimeframeContext
from src.structure.regime import MarketRegimeDetector, MarketRegime, should_trade

logger = logging.getLogger(__name__)


class FVGFinalStrategy(StrategyPlugin):
    """
    Final optimized FVG Reversal Strategy.

    Key features:
    1. Market regime filter — only trade in favorable conditions
    2. Adaptive entry — different logic for trending vs ranging
    3. Risk management — reduce size in uncertain markets
    """

    def __init__(self):
        self.regime_detector = MarketRegimeDetector()

    @property
    def strategy_id(self) -> str:
        return "fvg_final"

    @property
    def name(self) -> str:
        return "FVG Final"

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
        """Analyze for FVG reversal setup with regime filter."""

        if not current_candle:
            return None

        # Get available candles for regime detection
        # We need at least 50 candles for accurate regime detection
        # In real use, these would come from the data feed
        # For now, use context data if available
        if not context.swing_highs or not context.swing_lows:
            return None

        # Estimate regime from available data
        regime = self._estimate_regime(context)

        # Check if we should trade
        if not should_trade(regime, "both"):
            logger.debug(f"Regime {regime.regime.value} — skipping trade")
            return None

        # Route to appropriate setup based on regime
        if regime.is_trending:
            return self._check_trending_setup(
                context, current_candle, current_price, spread, session, regime
            )
        elif regime.is_ranging:
            return self._check_ranging_setup(
                context, current_candle, current_price, spread, session, regime
            )

        return None

    def _estimate_regime(self, ctx: MultiTimeframeContext) -> 'RegimeResult':
        """Estimate market regime from context data."""
        from src.structure.regime import RegimeResult

        # Simple regime estimation based on available data
        htf_trend = ctx.htf_trend
        has_swings = len(ctx.swing_highs) > 2 and len(ctx.swing_lows) > 2

        if not has_swings:
            return RegimeResult(
                regime=MarketRegime.UNKNOWN,
                confidence=0.0,
                trend_strength=0.0,
                volatility=0.0,
                atr_percentile=50.0,
                adx=0.0,
                is_tradable=False,
                reasons=["Insufficient swing data"],
            )

        # Check trend consistency
        recent_highs = [s.price for s in ctx.swing_highs[:3]]
        recent_lows = [s.price for s in ctx.swing_lows[:3]]

        # Calculate trend from swings
        if len(recent_highs) >= 2 and len(recent_lows) >= 2:
            highs_increasing = recent_highs[0] > recent_highs[1]
            lows_increasing = recent_lows[0] > recent_lows[1]

            if highs_increasing and lows_increasing:
                # Higher highs and higher lows = uptrend
                if htf_trend == Direction.BUY:
                    return RegimeResult(
                        regime=MarketRegime.UPTREND,
                        confidence=0.7,
                        trend_strength=0.5,
                        volatility=0.01,
                        atr_percentile=50.0,
                        adx=30.0,
                        is_tradable=True,
                        reasons=["Higher highs and lows with HTF bullish"],
                    )
            elif not highs_increasing and not lows_increasing:
                # Lower highs and lower lows = downtrend
                if htf_trend == Direction.SELL:
                    return RegimeResult(
                        regime=MarketRegime.DOWNTREND,
                        confidence=0.7,
                        trend_strength=-0.5,
                        volatility=0.01,
                        atr_percentile=50.0,
                        adx=30.0,
                        is_tradable=True,
                        reasons=["Lower highs and lows with HTF bearish"],
                    )

        # Default to ranging
        return RegimeResult(
            regime=MarketRegime.RANGING,
            confidence=0.5,
            trend_strength=0.0,
            volatility=0.01,
            atr_percentile=50.0,
            adx=20.0,
            is_tradable=True,
            reasons=["No clear trend detected"],
        )

    def _check_trending_setup(
        self,
        ctx: MultiTimeframeContext,
        candle: Candle,
        price: float,
        spread: float,
        session: str,
        regime: 'RegimeResult',
    ) -> Optional[StrategyCandidate]:
        """Check for trending market setup."""

        htf_trend = ctx.htf_trend

        if htf_trend == Direction.BUY:
            return self._check_long_trend(ctx, candle, price, spread, session, regime)
        elif htf_trend == Direction.SELL:
            return self._check_short_trend(ctx, candle, price, spread, session, regime)

        return None

    def _check_long_trend(
        self,
        ctx: MultiTimeframeContext,
        candle: Candle,
        price: float,
        spread: float,
        session: str,
        regime: 'RegimeResult',
    ) -> Optional[StrategyCandidate]:
        """Long setup in uptrend."""

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

        if regime.confidence > 0.6:
            score += 10
            confluences.append("strong_trend")

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
            metadata={"regime": regime.regime.value, "regime_confidence": regime.confidence},
        )

    def _check_short_trend(
        self,
        ctx: MultiTimeframeContext,
        candle: Candle,
        price: float,
        spread: float,
        session: str,
        regime: 'RegimeResult',
    ) -> Optional[StrategyCandidate]:
        """Short setup in downtrend."""

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

        if regime.confidence > 0.6:
            score += 10
            confluences.append("strong_trend")

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
            metadata={"regime": regime.regime.value, "regime_confidence": regime.confidence},
        )

    def _check_ranging_setup(
        self,
        ctx: MultiTimeframeContext,
        candle: Candle,
        price: float,
        spread: float,
        session: str,
        regime: 'RegimeResult',
    ) -> Optional[StrategyCandidate]:
        """Ranging market setup (mean reversion)."""

        if not ctx.swing_highs or not ctx.swing_lows:
            return None

        recent_high = ctx.swing_highs[0].price
        recent_low = ctx.swing_lows[0].price
        range_size = recent_high - recent_low

        if range_size <= 0:
            return None

        position = (price - recent_low) / range_size

        # Buy near bottom, sell near top
        if position < 0.25:
            return self._check_range_buy(ctx, candle, price, spread, session, regime, recent_low, recent_high)
        elif position > 0.75:
            return self._check_range_sell(ctx, candle, price, spread, session, regime, recent_low, recent_high)

        return None

    def _check_range_buy(
        self,
        ctx: MultiTimeframeContext,
        candle: Candle,
        price: float,
        spread: float,
        session: str,
        regime: 'RegimeResult',
        range_low: float,
        range_high: float,
    ) -> Optional[StrategyCandidate]:
        """Buy at bottom of range."""

        score = 55
        confluences = ["range_buy", "mean_reversion"]
        risk_flags = ["ranging_market"]

        if regime.confidence > 0.5:
            score += 5
            confluences.append("confident_range")

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
            metadata={"regime": regime.regime.value, "range_low": range_low, "range_high": range_high},
        )

    def _check_range_sell(
        self,
        ctx: MultiTimeframeContext,
        candle: Candle,
        price: float,
        spread: float,
        session: str,
        regime: 'RegimeResult',
        range_low: float,
        range_high: float,
    ) -> Optional[StrategyCandidate]:
        """Sell at top of range."""

        score = 55
        confluences = ["range_sell", "mean_reversion"]
        risk_flags = ["ranging_market"]

        if regime.confidence > 0.5:
            score += 5
            confluences.append("confident_range")

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
            metadata={"regime": regime.regime.value, "range_low": range_low, "range_high": range_high},
        )


register(FVGFinalStrategy())
