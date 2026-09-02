"""Market Regime Detector — identifies market conditions.

Detects whether the market is:
- TRENDING (strong directional move)
- RANGING (sideways consolidation)
- CHOPPY (low volatility, no clear direction)
- VOLATILE (high volatility, unpredictable)

Used by strategies to filter out unfavorable conditions.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from enum import Enum

import numpy as np

from src.core.types import Candle, Direction, SwingPoint

logger = logging.getLogger(__name__)


class MarketRegime(str, Enum):
    """Market regime types."""
    STRONG_UPTREND = "strong_uptrend"
    UPTREND = "uptrend"
    DOWNTREND = "downtrend"
    STRONG_DOWNTREND = "strong_downtrend"
    RANGING = "ranging"
    CHOPPY = "choppy"
    VOLATILE = "volatile"
    UNKNOWN = "unknown"


@dataclass
class RegimeResult:
    """Market regime detection result."""
    regime: MarketRegime
    confidence: float  # 0-1
    trend_strength: float  # -1 to 1 (negative = bearish)
    volatility: float  # Normalized volatility
    atr_percentile: float  # Where current ATR is in historical distribution
    adx: float  # Average Directional Index
    is_tradable: bool  # Should we trade in this regime?
    reasons: list[str]

    @property
    def is_trending(self) -> bool:
        return self.regime in (
            MarketRegime.STRONG_UPTREND,
            MarketRegime.UPTREND,
            MarketRegime.DOWNTREND,
            MarketRegime.STRONG_DOWNTREND,
        )

    @property
    def is_ranging(self) -> bool:
        return self.regime in (MarketRegime.RANGING, MarketRegime.CHOPPY)

    @property
    def trend_direction(self) -> Direction | None:
        if self.regime in (MarketRegime.STRONG_UPTREND, MarketRegime.UPTREND):
            return Direction.BUY
        elif self.regime in (MarketRegime.STRONG_DOWNTREND, MarketRegime.DOWNTREND):
            return Direction.SELL
        return None


class MarketRegimeDetector:
    """
    Detects market regime using multiple indicators:

    1. ADX (Average Directional Index) — trend strength
    2. ATR (Average True Range) — volatility
    3. Price position relative to moving averages
    4. Swing analysis — higher highs/lows vs lower highs/lows
    5. Choppiness Index — trending vs ranging
    """

    def __init__(
        self,
        adx_period: int = 14,
        atr_period: int = 14,
        chop_period: int = 14,
        trend_threshold: float = 25.0,
        chop_threshold: float = 61.8,
    ):
        self.adx_period = adx_period
        self.atr_period = atr_period
        self.chop_period = chop_period
        self.trend_threshold = trend_threshold
        self.chop_threshold = chop_threshold

    def detect(self, candles: list[Candle]) -> RegimeResult:
        """Detect current market regime from candle data."""
        if len(candles) < max(self.adx_period, self.atr_period, self.chop_period) + 10:
            return RegimeResult(
                regime=MarketRegime.UNKNOWN,
                confidence=0.0,
                trend_strength=0.0,
                volatility=0.0,
                atr_percentile=0.0,
                adx=0.0,
                is_tradable=False,
                reasons=["Insufficient data for regime detection"],
            )

        # Extract price arrays
        highs = np.array([c.high for c in candles])
        lows = np.array([c.low for c in candles])
        closes = np.array([c.close for c in candles])

        # Calculate indicators
        adx = self._calculate_adx(highs, lows, closes)
        atr = self._calculate_atr(highs, lows, closes)
        atr_percentile = self._calculate_atr_percentile(atr)
        chop = self._calculate_choppiness(highs, lows, closes)
        trend_strength = self._calculate_trend_strength(closes)
        ma_position = self._calculate_ma_position(closes)

        # Determine regime
        reasons = []
        regime = MarketRegime.UNKNOWN
        confidence = 0.0
        is_tradable = True

        # Strong trend: ADX > 40
        if adx > 40:
            if trend_strength > 0.3:
                regime = MarketRegime.STRONG_UPTREND
                confidence = min(1.0, adx / 60)
                reasons.append(f"Strong uptrend (ADX={adx:.1f})")
            elif trend_strength < -0.3:
                regime = MarketRegime.STRONG_DOWNTREND
                confidence = min(1.0, adx / 60)
                reasons.append(f"Strong downtrend (ADX={adx:.1f})")
            else:
                regime = MarketRegime.VOLATILE
                confidence = 0.6
                reasons.append(f"High volatility (ADX={adx:.1f})")

        # Moderate trend: ADX 25-40
        elif adx > self.trend_threshold:
            if trend_strength > 0.15:
                regime = MarketRegime.UPTREND
                confidence = min(1.0, (adx - 20) / 30)
                reasons.append(f"Uptrend (ADX={adx:.1f})")
            elif trend_strength < -0.15:
                regime = MarketRegime.DOWNTREND
                confidence = min(1.0, (adx - 20) / 30)
                reasons.append(f"Downtrend (ADX={adx:.1f})")
            else:
                regime = MarketRegime.RANGING
                confidence = 0.5
                reasons.append(f"Weak trend (ADX={adx:.1f})")

        # No trend: ADX < 25
        else:
            if chop > self.chop_threshold:
                regime = MarketRegime.CHOPPY
                confidence = min(1.0, (chop - 50) / 30)
                reasons.append(f"Choppy market (Chop={chop:.1f})")
                is_tradable = False  # Don't trade in choppy markets
            else:
                regime = MarketRegime.RANGING
                confidence = 0.6
                reasons.append(f"Ranging market (ADX={adx:.1f})")

        # Add additional context
        if atr_percentile > 80:
            reasons.append(f"High volatility (ATR top {100-atr_percentile:.0f}%)")
        elif atr_percentile < 20:
            reasons.append(f"Low volatility (ATR bottom {atr_percentile:.0f}%)")

        if abs(ma_position) > 0.02:
            direction = "above" if ma_position > 0 else "below"
            reasons.append(f"Price {direction} 20-MA by {abs(ma_position)*100:.1f}%")

        return RegimeResult(
            regime=regime,
            confidence=confidence,
            trend_strength=trend_strength,
            volatility=atr[-1] / closes[-1] if closes[-1] > 0 else 0,
            atr_percentile=atr_percentile,
            adx=adx,
            is_tradable=is_tradable,
            reasons=reasons,
        )

    def _calculate_adx(
        self, highs: np.ndarray, lows: np.ndarray, closes: np.ndarray
    ) -> float:
        """Calculate Average Directional Index."""
        n = len(highs)
        if n < self.adx_period + 1:
            return 0.0

        # True Range
        tr = np.maximum(
            highs[1:] - lows[1:],
            np.maximum(
                np.abs(highs[1:] - closes[:-1]),
                np.abs(lows[1:] - closes[:-1])
            )
        )

        # Directional Movement
        up_move = highs[1:] - highs[:-1]
        down_move = lows[:-1] - lows[1:]

        plus_dm = np.where((up_move > down_move) & (up_move > 0), up_move, 0)
        minus_dm = np.where((down_move > up_move) & (down_move > 0), down_move, 0)

        # Smoothed averages
        alpha = 1.0 / self.adx_period
        atr_smooth = self._ema(tr, alpha)
        plus_di = 100 * self._ema(plus_dm, alpha) / atr_smooth
        minus_di = 100 * self._ema(minus_dm, alpha) / atr_smooth

        # DX and ADX
        dx = 100 * np.abs(plus_di - minus_di) / (plus_di + minus_di + 1e-10)
        adx = self._ema(dx, alpha)

        return float(adx[-1]) if len(adx) > 0 else 0.0

    def _calculate_atr(
        self, highs: np.ndarray, lows: np.ndarray, closes: np.ndarray
    ) -> np.ndarray:
        """Calculate Average True Range."""
        tr = np.maximum(
            highs[1:] - lows[1:],
            np.maximum(
                np.abs(highs[1:] - closes[:-1]),
                np.abs(lows[1:] - closes[:-1])
            )
        )

        alpha = 1.0 / self.atr_period
        atr = np.zeros(len(tr))
        atr[0] = tr[0]
        for i in range(1, len(tr)):
            atr[i] = alpha * tr[i] + (1 - alpha) * atr[i-1]

        return atr

    def _calculate_atr_percentile(self, atr: np.ndarray) -> float:
        """Calculate where current ATR is in historical distribution."""
        if len(atr) < 20:
            return 50.0

        current_atr = atr[-1]
        percentile = np.sum(atr <= current_atr) / len(atr) * 100
        return float(percentile)

    def _calculate_choppiness(
        self, highs: np.ndarray, lows: np.ndarray, closes: np.ndarray
    ) -> float:
        """Calculate Choppiness Index (0-100)."""
        n = len(highs)
        if n < self.chop_period + 1:
            return 50.0

        # True Range
        tr = np.maximum(
            highs[1:] - lows[1:],
            np.maximum(
                np.abs(highs[1:] - closes[:-1]),
                np.abs(lows[1:] - closes[:-1])
            )
        )

        # Sum of True Range over period
        atr_sum = np.sum(tr[-self.chop_period:])

        # Highest High and Lowest Low
        highest = np.max(highs[-self.chop_period:])
        lowest = np.min(lows[-self.chop_period:])

        # Choppiness Index
        if highest == lowest:
            return 50.0

        chop = 100 * np.log10(atr_sum / (highest - lowest)) / np.log10(self.chop_period)
        return float(np.clip(chop, 0, 100))

    def _calculate_trend_strength(self, closes: np.ndarray) -> float:
        """Calculate trend strength (-1 to 1)."""
        if len(closes) < 20:
            return 0.0

        # Linear regression slope
        x = np.arange(20)
        y = closes[-20:]

        # Normalize
        y_norm = (y - y[0]) / y[0] if y[0] > 0 else y - y[0]

        # Simple slope
        slope = np.polyfit(x, y_norm, 1)[0]

        # Clamp to -1 to 1
        return float(np.clip(slope * 100, -1, 1))

    def _calculate_ma_position(self, closes: np.ndarray) -> float:
        """Calculate price position relative to 20-MA (-0.05 to 0.05)."""
        if len(closes) < 20:
            return 0.0

        ma20 = np.mean(closes[-20:])
        if ma20 == 0:
            return 0.0

        position = (closes[-1] - ma20) / ma20
        return float(np.clip(position, -0.05, 0.05))

    def _ema(self, data: np.ndarray, alpha: float) -> np.ndarray:
        """Exponential moving average."""
        result = np.zeros_like(data)
        result[0] = data[0]
        for i in range(1, len(data)):
            result[i] = alpha * data[i] + (1 - alpha) * result[i-1]
        return result


def should_trade(regime: RegimeResult, strategy_type: str = "trend") -> bool:
    """
    Determine if we should trade based on market regime.

    Args:
        regime: Current market regime
        strategy_type: "trend" or "mean_reversion"

    Returns:
        True if we should trade, False otherwise
    """
    if regime.regime == MarketRegime.UNKNOWN:
        return False

    if strategy_type == "trend":
        # Trend strategies: only trade in trending markets
        return regime.is_trending and regime.confidence > 0.5

    elif strategy_type == "mean_reversion":
        # Mean reversion: trade in ranging markets, avoid choppy
        return regime.is_ranging and regime.regime != MarketRegime.CHOPPY

    elif strategy_type == "both":
        # Trade in any non-choppy market
        return regime.regime != MarketRegime.CHOPPY and regime.regime != MarketRegime.UNKNOWN

    return False
