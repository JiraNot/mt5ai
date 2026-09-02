"""Order Block detection algorithm."""

from __future__ import annotations

import logging
from datetime import datetime

from src.core.types import Candle, Direction, FairValueGap, OrderBlock

logger = logging.getLogger(__name__)


class OrderBlockDetector:
    """
    Detects Order Blocks in price data.

    Bullish Order Block:
    - Last bearish (red) candle before a strong bullish displacement
    - The OB zone is that candle's body/range

    Bearish Order Block:
    - Last bullish (green) candle before a strong bearish displacement
    - The OB zone is that candle's body/range

    Displacement criteria:
    - Strong directional move (large body candle)
    - Creates FVG or breaks structure
    """

    def __init__(
        self,
        displacement_threshold: float = 1.5,
        min_body_ratio: float = 0.6,
    ) -> None:
        """
        Args:
            displacement_threshold: Multiplier of average body size to qualify as displacement
            min_body_ratio: Minimum body/range ratio for the displacement candle
        """
        self._displacement_threshold = displacement_threshold
        self._min_body_ratio = min_body_ratio

    def detect(
        self,
        candles: list[Candle],
        fvgs: list[FairValueGap] | None = None,
        timeframe: str = "H1",
    ) -> list[OrderBlock]:
        """
        Detect Order Blocks in candle data.

        Algorithm:
        1. Calculate average body size (rolling 20 candles)
        2. Find displacement candles (body > threshold * average)
        3. Identify the OB candle (last opposite candle before displacement)
        4. Mark OB if there's FVG overlap
        """
        if len(candles) < 25:
            return []

        order_blocks: list[OrderBlock] = []

        # Calculate rolling average body size
        for i in range(20, len(candles)):
            lookback = candles[i - 20:i]
            avg_body = sum(abs(c.close - c.open) for c in lookback) / 20

            current = candles[i]
            body = abs(current.close - current.open)
            total_range = current.high - current.low

            if total_range == 0:
                continue

            body_ratio = body / total_range
            is_displacement = (
                body > avg_body * self._displacement_threshold
                and body_ratio >= self._min_body_ratio
            )

            if not is_displacement:
                continue

            # Find the last opposite candle before displacement
            if current.close > current.open:  # Bullish displacement
                ob = self._find_bullish_ob(candles, i)
                if ob:
                    # Check FVG overlap
                    has_fvg_overlap = False
                    if fvgs:
                        has_fvg_overlap = self._check_fvg_overlap(ob, fvgs)

                    order_blocks.append(
                        OrderBlock(
                            timestamp=ob.timestamp,
                            direction=Direction.BUY,
                            upper_price=ob.high,
                            lower_price=ob.low,
                            timeframe=timeframe,
                            strength=min(5, max(1, int(body / avg_body))),
                            fvg_overlap=has_fvg_overlap,
                        )
                    )

            elif current.close < current.open:  # Bearish displacement
                ob = self._find_bearish_ob(candles, i)
                if ob:
                    has_fvg_overlap = False
                    if fvgs:
                        has_fvg_overlap = self._check_fvg_overlap(ob, fvgs)

                    order_blocks.append(
                        OrderBlock(
                            timestamp=ob.timestamp,
                            direction=Direction.SELL,
                            upper_price=ob.high,
                            lower_price=ob.low,
                            timeframe=timeframe,
                            strength=min(5, max(1, int(body / avg_body))),
                            fvg_overlap=has_fvg_overlap,
                        )
                    )

        order_blocks.sort(key=lambda o: o.timestamp, reverse=True)
        return order_blocks

    def _find_bullish_ob(self, candles: list[Candle], displacement_idx: int) -> Candle | None:
        """Find the last bearish candle before a bullish displacement."""
        for i in range(displacement_idx - 1, max(0, displacement_idx - 5), -1):
            if candles[i].close < candles[i].open:  # Bearish candle
                return candles[i]
        return None

    def _find_bearish_ob(self, candles: list[Candle], displacement_idx: int) -> Candle | None:
        """Find the last bullish candle before a bearish displacement."""
        for i in range(displacement_idx - 1, max(0, displacement_idx - 5), -1):
            if candles[i].close > candles[i].open:  # Bullish candle
                return candles[i]
        return None

    def _check_fvg_overlap(self, ob: Candle, fvgs: list[FairValueGap]) -> bool:
        """Check if an order block overlaps with any FVG."""
        for fvg in fvgs:
            # Overlap exists if OB range intersects FVG range
            if ob.low <= fvg.upper_price and ob.high >= fvg.lower_price:
                return True
        return False

    def find_nearest_ob(
        self,
        order_blocks: list[OrderBlock],
        direction: Direction,
        current_price: float,
        max_distance: float = 50.0,
    ) -> OrderBlock | None:
        """Find the nearest unmitigated Order Block for a given direction."""
        candidates = [
            ob for ob in order_blocks
            if ob.direction == direction
            and not ob.mitigated
        ]

        if not candidates:
            return None

        # Find nearest to current price within max_distance
        nearest = None
        min_dist = float("inf")

        for ob in candidates:
            dist = abs(current_price - ob.midpoint)
            if dist <= max_distance and dist < min_dist:
                min_dist = dist
                nearest = ob

        return nearest
