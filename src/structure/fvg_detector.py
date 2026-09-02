"""Fair Value Gap (FVG) detection algorithm."""

from __future__ import annotations

import logging
from datetime import datetime

from src.core.types import Candle, Direction, FairValueGap

logger = logging.getLogger(__name__)


class FVGDetector:
    """
    Detects Fair Value Gaps in price data.

    Bullish FVG:
    - Candle 1 low > Candle 3 high (gap up)
    - The gap between Candle1.low and Candle3.high is the FVG zone

    Bearish FVG:
    - Candle 1 high < Candle 3 low (gap down)
    - The gap between Candle1.high and Candle3.low is the FVG zone
    """

    def __init__(self, min_gap_size: float = 0.5) -> None:
        """
        Args:
            min_gap_size: Minimum gap size in price to qualify as FVG.
                         For XAUUSD, 0.5 = $0.50 minimum gap.
        """
        self._min_gap_size = min_gap_size

    def detect(self, candles: list[Candle], timeframe: str = "H1") -> list[FairValueGap]:
        """
        Detect all FVGs in a list of candles.

        Scans 3-candle patterns: [c1, c2 (displacement), c3]
        """
        if len(candles) < 3:
            return []

        fvgs: list[FairValueGap] = []

        for i in range(2, len(candles)):
            c1 = candles[i - 2]
            c2 = candles[i - 1]  # Displacement candle
            c3 = candles[i]

            # Bullish FVG: gap between c1.low and c3.high
            if c1.low > c3.high:
                gap_size = c1.low - c3.high
                if gap_size >= self._min_gap_size:
                    fvgs.append(
                        FairValueGap(
                            timestamp=c2.timestamp,
                            direction=Direction.BUY,
                            upper_price=c1.low,
                            lower_price=c3.high,
                            timeframe=timeframe,
                        )
                    )

            # Bearish FVG: gap between c1.high and c3.low
            elif c1.high < c3.low:
                gap_size = c3.low - c1.high
                if gap_size >= self._min_gap_size:
                    fvgs.append(
                        FairValueGap(
                            timestamp=c2.timestamp,
                            direction=Direction.SELL,
                            upper_price=c3.low,
                            lower_price=c1.high,
                            timeframe=timeframe,
                        )
                    )

        # Sort newest first
        fvgs.sort(key=lambda f: f.timestamp, reverse=True)
        return fvgs

    def find_valid_fvgs(
        self,
        fvgs: list[FairValueGap],
        current_price: float,
        max_mitigation_pct: float = 50.0,
    ) -> list[FairValueGap]:
        """
        Filter FVGs to find valid (unmitigated) ones near current price.

        A valid FVG:
        - Not fully mitigated (price hasn't returned to fill the gap)
        - Within reasonable distance from current price
        """
        valid = []
        for fvg in fvgs:
            if not fvg.valid:
                continue

            # Check if price is near the FVG zone
            if fvg.direction == Direction.BUY:
                # Bullish FVG: valid if price hasn't dropped below midpoint
                if current_price >= fvg.lower_price:
                    valid.append(fvg)
            else:
                # Bearish FVG: valid if price hasn't risen above midpoint
                if current_price <= fvg.upper_price:
                    valid.append(fvg)

        return valid

    def is_price_in_fvg(
        self,
        price: float,
        fvg: FairValueGap,
    ) -> bool:
        """Check if a price is within an FVG zone."""
        return fvg.lower_price <= price <= fvg.upper_price
