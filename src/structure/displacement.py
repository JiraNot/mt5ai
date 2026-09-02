"""Displacement Engine — detects impulsive movements.

Displacement is a strong, impulsive price move that indicates
institutional activity. It's a key concept in Smart Money trading.

Features:
- Body ratio (body / total range)
- Range vs ATR
- Consecutive candles
- Volume confirmation
- Displacement score (0-100)
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

import numpy as np

from src.core.types import Candle, Direction

logger = logging.getLogger(__name__)


@dataclass
class DisplacementResult:
    """Result of displacement detection."""
    detected: bool
    direction: Direction
    score: float  # 0-100
    body_ratio: float  # body / range
    range_atr_ratio: float  # range / ATR
    consecutive_candles: int
    volume_ratio: float  # volume / average volume
    reasons: list[str]


class DisplacementDetector:
    """Detects impulsive price movements (displacement)."""

    def __init__(
        self,
        min_body_ratio: float = 0.6,
        min_range_atr: float = 1.5,
        min_score: float = 60.0,
        lookback: int = 20,
    ):
        self.min_body_ratio = min_body_ratio
        self.min_range_atr = min_range_atr
        self.min_score = min_score
        self.lookback = lookback

    def detect(
        self,
        candles: list[Candle],
        index: int = -1,
    ) -> DisplacementResult:
        """
        Detect displacement at a specific candle.

        Args:
            candles: List of candles
            index: Index of candle to check (-1 for last)

        Returns:
            DisplacementResult with detection details
        """
        if len(candles) < self.lookback + 1:
            return DisplacementResult(
                detected=False,
                direction=Direction.BUY,
                score=0.0,
                body_ratio=0.0,
                range_atr_ratio=0.0,
                consecutive_candles=0,
                volume_ratio=1.0,
                reasons=["Insufficient data"],
            )

        # Get target candle
        target = candles[index]
        body = abs(target.close - target.open)
        total_range = target.high - target.low

        if total_range == 0:
            return DisplacementResult(
                detected=False,
                direction=Direction.BUY,
                score=0.0,
                body_ratio=0.0,
                range_atr_ratio=0.0,
                consecutive_candles=0,
                volume_ratio=1.0,
                reasons=["Zero range candle"],
            )

        # Calculate metrics
        body_ratio = body / total_range

        # Calculate ATR
        atr = self._calculate_atr(candles[:index] if index > 0 else candles[:-1])
        range_atr_ratio = total_range / atr if atr > 0 else 0

        # Calculate consecutive candles in same direction
        consecutive = self._count_consecutive(candles, index)

        # Calculate volume ratio
        avg_volume = np.mean([c.volume for c in candles[-self.lookback:]]) if candles[-self.lookback:] else 1
        volume_ratio = target.volume / avg_volume if avg_volume > 0 else 1.0

        # Determine direction
        is_bullish = target.close > target.open
        direction = Direction.BUY if is_bullish else Direction.SELL

        # Calculate displacement score
        score = self._calculate_score(
            body_ratio=body_ratio,
            range_atr_ratio=range_atr_ratio,
            consecutive=consecutive,
            volume_ratio=volume_ratio,
        )

        # Generate reasons
        reasons = []
        if body_ratio >= self.min_body_ratio:
            reasons.append(f"Strong body ({body_ratio:.0%})")
        if range_atr_ratio >= self.min_range_atr:
            reasons.append(f"Large range ({range_atr_ratio:.1f}x ATR)")
        if consecutive >= 3:
            reasons.append(f"{consecutive} consecutive candles")
        if volume_ratio > 1.5:
            reasons.append(f"High volume ({volume_ratio:.1f}x avg)")

        detected = score >= self.min_score

        return DisplacementResult(
            detected=detected,
            direction=direction,
            score=score,
            body_ratio=body_ratio,
            range_atr_ratio=range_atr_ratio,
            consecutive_candles=consecutive,
            volume_ratio=volume_ratio,
            reasons=reasons,
        )

    def detect_series(
        self,
        candles: list[Candle],
        min_score: float | None = None,
    ) -> list[DisplacementResult]:
        """Detect all displacements in a candle series."""
        min_score = min_score or self.min_score
        results = []

        for i in range(self.lookback, len(candles)):
            result = self.detect(candles, i)
            if result.score >= min_score:
                results.append(result)

        return results

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

    def _count_consecutive(self, candles: list[Candle], index: int) -> int:
        """Count consecutive candles in the same direction."""
        if index < 0:
            index = len(candles) + index

        if index >= len(candles):
            return 0

        target = candles[index]
        is_bullish = target.close > target.open
        count = 1

        # Count backwards
        for i in range(index - 1, max(0, index - 10), -1):
            candle = candles[i]
            if is_bullish and candle.close > candle.open:
                count += 1
            elif not is_bullish and candle.close < candle.open:
                count += 1
            else:
                break

        return count

    def _calculate_score(
        self,
        body_ratio: float,
        range_atr_ratio: float,
        consecutive: int,
        volume_ratio: float,
    ) -> float:
        """Calculate displacement score (0-100)."""
        score = 0.0

        # Body ratio (0-30 points)
        if body_ratio >= 0.8:
            score += 30
        elif body_ratio >= 0.6:
            score += 20
        elif body_ratio >= 0.4:
            score += 10

        # Range vs ATR (0-30 points)
        if range_atr_ratio >= 2.0:
            score += 30
        elif range_atr_ratio >= 1.5:
            score += 20
        elif range_atr_ratio >= 1.0:
            score += 10

        # Consecutive candles (0-20 points)
        if consecutive >= 5:
            score += 20
        elif consecutive >= 3:
            score += 15
        elif consecutive >= 2:
            score += 10

        # Volume (0-20 points)
        if volume_ratio >= 2.0:
            score += 20
        elif volume_ratio >= 1.5:
            score += 15
        elif volume_ratio >= 1.0:
            score += 10

        return min(100.0, score)
