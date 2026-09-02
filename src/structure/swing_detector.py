"""Swing High/Low detection algorithm."""

from __future__ import annotations

import logging
from datetime import datetime

from src.core.types import Candle, Direction, SwingPoint

logger = logging.getLogger(__name__)


class SwingDetector:
    """
    Detects Swing High and Swing Low points in price data.

    Algorithm:
    - A Swing High is a candle whose high is higher than N candles on each side.
    - A Swing Low is a candle whose low is lower than N candles on each side.
    - Strength (1-5) = how many candles on each side confirm the swing.
    """

    def __init__(self, lookback: int = 3) -> None:
        """
        Args:
            lookback: Number of candles on each side to confirm swing.
                      lookback=3 means we need 3 lower highs on each side for a swing high.
        """
        self._lookback = lookback

    def detect_swings(self, candles: list[Candle], timeframe: str = "H1") -> list[SwingPoint]:
        """
        Detect all swing points in a list of candles.

        Returns swings sorted by timestamp (newest first).
        """
        if len(candles) < self._lookback * 2 + 1:
            return []

        swings: list[SwingPoint] = []

        for i in range(self._lookback, len(candles) - self._lookback):
            center = candles[i]

            # Check for Swing High
            is_swing_high = True
            strength = 0
            for j in range(1, self._lookback + 1):
                left = candles[i - j]
                right = candles[i + j]
                if center.high >= left.high and center.high >= right.high:
                    strength += 1
                else:
                    is_swing_high = False
                    break

            if is_swing_high:
                swings.append(
                    SwingPoint(
                        timestamp=center.timestamp,
                        price=center.high,
                        direction=Direction.SELL,  # Swing high = resistance
                        strength=max(1, min(5, strength)),
                        timeframe=timeframe,
                    )
                )
                continue

            # Check for Swing Low
            is_swing_low = True
            strength = 0
            for j in range(1, self._lookback + 1):
                left = candles[i - j]
                right = candles[i + j]
                if center.low <= left.low and center.low <= right.low:
                    strength += 1
                else:
                    is_swing_low = False
                    break

            if is_swing_low:
                swings.append(
                    SwingPoint(
                        timestamp=center.timestamp,
                        price=center.low,
                        direction=Direction.BUY,  # Swing low = support
                        strength=max(1, min(5, strength)),
                        timeframe=timeframe,
                    )
                )

        # Sort newest first
        swings.sort(key=lambda s: s.timestamp, reverse=True)
        return swings

    def find_nearest_support(self, price: float, swings: list[SwingPoint]) -> SwingPoint | None:
        """Find the nearest swing low (support) below current price."""
        supports = [s for s in swings if s.direction == Direction.BUY and s.price < price]
        if not supports:
            return None
        return min(supports, key=lambda s: price - s.price)

    def find_nearest_resistance(self, price: float, swings: list[SwingPoint]) -> SwingPoint | None:
        """Find the nearest swing high (resistance) above current price."""
        resistances = [s for s in swings if s.direction == Direction.SELL and s.price > price]
        if not resistances:
            return None
        return min(resistances, key=lambda s: s.price - price)
