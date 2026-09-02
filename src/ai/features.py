"""Feature Engine — extracts structured features for ML training.

Converts market state + trade candidate into feature vector
for ML model training and prediction.

Features are designed to be:
1. Forward-looking (predict future outcome)
2. Explainable (each feature has clear meaning)
3. Stable (don't change with minor price movements)
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime

import numpy as np

from src.core.types import (
    Candle,
    Direction,
    FairValueGap,
    OrderBlock,
    StrategyCandidate,
)
from src.structure.context import MultiTimeframeContext
from src.structure.regime import MarketRegime, RegimeResult

logger = logging.getLogger(__name__)


@dataclass
class TradeFeatures:
    """Feature vector for a single trade candidate."""

    # Identifiers
    symbol: str = ""
    strategy: str = ""
    direction: str = ""
    timestamp: str = ""

    # Market Structure Features
    htf_trend: int = 0  # -1=SELL, 0=NONE, 1=BUY
    m15_trend: int = 0
    has_choch: int = 0
    has_bos: int = 0
    choch_bos_strength: float = 0.0

    # FVG Features
    has_fvg: int = 0
    fvg_direction: int = 0
    fvg_size_atr: float = 0.0
    fvg_mitigation: float = 0.0

    # Order Block Features
    has_ob: int = 0
    ob_direction: int = 0
    ob_strength: float = 0.0
    ob_fvg_overlap: int = 0

    # Liquidity Features
    has_liquidity_sweep: int = 0
    sweep_type: int = 0  # -1=sell_side, 0=none, 1=buy_side
    sweep_strength: float = 0.0

    # Price Position Features
    in_discount_zone: int = 0
    in_premium_zone: int = 0
    price_vs_swing_high: float = 0.0
    price_vs_swing_low: float = 0.0

    # Volatility Features
    atr_percentile: float = 0.0
    spread_percentile: float = 0.0
    volatility_regime: int = 0  # -1=low, 0=normal, 1=high

    # Session Features
    is_london: int = 0
    is_new_york: int = 0
    is_overlap: int = 0
    is_asian: int = 0
    hour_of_day: int = 0
    day_of_week: int = 0

    # Regime Features
    market_regime: int = 0  # 0=trending, 1=ranging, 2=choppy
    regime_confidence: float = 0.0
    adx: float = 0.0
    trend_strength: float = 0.0

    # Trade Setup Features
    rule_score: int = 0
    rr_ratio: float = 0.0
    sl_distance_atr: float = 0.0
    tp_distance_atr: float = 0.0

    # Displacement Features
    displacement_score: float = 0.0
    body_ratio: float = 0.0
    consecutive_candles: int = 0

    # Target (for training)
    outcome: int = 0  # -1=LOSS, 0=BREAKEVEN, 1=WIN
    r_multiple: float = 0.0
    mfe: float = 0.0  # Maximum Favorable Excursion
    mae: float = 0.0  # Maximum Adverse Excursion

    def to_dict(self) -> dict:
        """Convert to dictionary for serialization."""
        return {k: v for k, v in self.__dict__.items()}

    def to_vector(self) -> list[float]:
        """Convert to numeric vector for ML."""
        return [float(v) for v in self.__dict__.values() if isinstance(v, (int, float))]


class FeatureEngine:
    """Extracts features from market state and trade candidates."""

    def __init__(self):
        self._session_hours = {
            "asian": (0, 7),
            "london": (7, 16),
            "new_york": (12, 21),
            "overlap": (12, 16),
        }

    def extract(
        self,
        candidate: StrategyCandidate,
        context: MultiTimeframeContext,
        regime: RegimeResult | None = None,
        candles: list[Candle] | None = None,
    ) -> TradeFeatures:
        """Extract features from a trade candidate and market context."""

        features = TradeFeatures()

        # Identifiers
        features.symbol = candidate.symbol
        features.strategy = candidate.strategy_id
        features.direction = candidate.direction.value
        features.timestamp = candidate.timestamp.isoformat()

        # Market Structure
        features.htf_trend = self._direction_to_int(context.htf_trend)
        m15 = context.get_structure("M15")
        if m15:
            features.m15_trend = self._direction_to_int(m15.trend)
            features.has_choch = 1 if m15.choch else 0
            features.has_bos = 1 if m15.bos else 0

        # FVG
        features.has_fvg = 1 if context.fvgs else 0
        if context.fvgs:
            bullish_fvgs = [f for f in context.fvgs if f.direction == Direction.BUY]
            bearish_fvgs = [f for f in context.fvgs if f.direction == Direction.SELL]
            if bullish_fvgs:
                features.fvg_direction = 1
                features.fvg_size_atr = self._normalize_fvg_size(bullish_fvgs[0], candles)
                features.fvg_mitigation = bullish_fvgs[0].mitigated_percent
            elif bearish_fvgs:
                features.fvg_direction = -1
                features.fvg_size_atr = self._normalize_fvg_size(bearish_fvgs[0], candles)
                features.fvg_mitigation = bearish_fvgs[0].mitigated_percent

        # Order Block
        features.has_ob = 1 if context.order_blocks else 0
        if context.order_blocks:
            bullish_obs = [o for o in context.order_blocks if o.direction == Direction.BUY]
            bearish_obs = [o for o in context.order_blocks if o.direction == Direction.SELL]
            if bullish_obs:
                features.ob_direction = 1
                features.ob_strength = bullish_obs[0].strength / 5.0
            elif bearish_obs:
                features.ob_direction = -1
                features.ob_strength = bearish_obs[0].strength / 5.0
            features.ob_fvg_overlap = 1 if any(o.fvg_overlap for o in context.order_blocks) else 0

        # Liquidity
        features.has_liquidity_sweep = 1 if context.has_liquidity_sweep else 0
        if context.liquidity_sweeps:
            sweep = context.liquidity_sweeps[0]
            if sweep.get("type") == "sell_side":
                features.sweep_type = -1
            elif sweep.get("type") == "buy_side":
                features.sweep_type = 1
            features.sweep_strength = sweep.get("strength", 0) / 5.0

        # Price Position
        features.in_discount_zone = 1 if context.in_discount_zone else 0
        features.in_premium_zone = 1 if context.in_premium_zone else 0

        if context.swing_highs and context.swing_lows:
            recent_high = context.swing_highs[0].price
            recent_low = context.swing_lows[0].price
            range_size = recent_high - recent_low
            if range_size > 0:
                features.price_vs_swing_high = (context.current_price - recent_high) / range_size
                features.price_vs_swing_low = (context.current_price - recent_low) / range_size

        # Volatility
        if candles and len(candles) > 20:
            features.atr_percentile = self._calculate_atr_percentile(candles)

        # Session
        hour = candidate.timestamp.hour
        features.hour_of_day = hour
        features.day_of_week = candidate.timestamp.weekday()
        features.is_london = 1 if 7 <= hour < 16 else 0
        features.is_new_york = 1 if 12 <= hour < 21 else 0
        features.is_overlap = 1 if 12 <= hour < 16 else 0
        features.is_asian = 1 if hour < 7 or hour >= 21 else 0

        # Regime
        if regime:
            features.market_regime = self._regime_to_int(regime.regime)
            features.regime_confidence = regime.confidence
            features.adx = regime.adx
            features.trend_strength = regime.trend_strength

        # Trade Setup
        features.rule_score = candidate.rule_score
        features.rr_ratio = candidate.rr_ratio

        return features

    def extract_batch(
        self,
        candidates: list[StrategyCandidate],
        context: MultiTimeframeContext,
        regime: RegimeResult | None = None,
    ) -> list[TradeFeatures]:
        """Extract features for multiple candidates."""
        return [self.extract(c, context, regime) for c in candidates]

    def _direction_to_int(self, direction: Direction | None) -> int:
        """Convert Direction to integer."""
        if direction == Direction.BUY:
            return 1
        elif direction == Direction.SELL:
            return -1
        return 0

    def _regime_to_int(self, regime: MarketRegime) -> int:
        """Convert regime to integer."""
        if regime in (MarketRegime.STRONG_UPTREND, MarketRegime.UPTREND, MarketRegime.STRONG_DOWNTREND, MarketRegime.DOWNTREND):
            return 0  # Trending
        elif regime in (MarketRegime.RANGING,):
            return 1  # Ranging
        elif regime in (MarketRegime.CHOPPY,):
            return 2  # Choppy
        return 0

    def _normalize_fvg_size(self, fvg: FairValueGap, candles: list[Candle] | None) -> float:
        """Normalize FVG size by ATR."""
        if not candles or len(candles) < 14:
            return fvg.zone_size / 10.0  # Default normalization

        atr = self._calculate_atr(candles, 14)
        if atr > 0:
            return fvg.zone_size / atr
        return 0.0

    def _calculate_atr(self, candles: list[Candle], period: int = 14) -> float:
        """Calculate Average True Range."""
        if len(candles) < period + 1:
            return 0.0

        trs = []
        for i in range(1, len(candles)):
            tr = max(
                candles[i].high - candles[i].low,
                abs(candles[i].high - candles[i-1].close),
                abs(candles[i].low - candles[i-1].close),
            )
            trs.append(tr)

        return np.mean(trs[-period:]) if trs else 0.0

    def _calculate_atr_percentile(self, candles: list[Candle]) -> float:
        """Calculate where current ATR is in historical distribution."""
        if len(candles) < 30:
            return 50.0

        atrs = []
        for i in range(14, len(candles)):
            atr = self._calculate_atr(candles[:i+1], 14)
            atrs.append(atr)

        if not atrs:
            return 50.0

        current_atr = atrs[-1]
        percentile = sum(1 for a in atrs if a <= current_atr) / len(atrs) * 100
        return percentile
