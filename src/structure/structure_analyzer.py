"""Market structure analysis — BOS (Break of Structure) and CHoCH (Change of Character)."""

from __future__ import annotations

import logging
from datetime import datetime

from src.core.types import Candle, Direction, MarketStructure, SwingPoint
from src.structure.swing_detector import SwingDetector

logger = logging.getLogger(__name__)


class StructureAnalyzer:
    """
    Analyzes market structure using ICT concepts.

    BOS (Break of Structure):
    - Bullish BOS: price breaks above a swing high → continuation up
    - Bearish BOS: price breaks below a swing low → continuation down

    CHoCH (Change of Character):
    - Bullish CHoCH: price breaks above a swing high in a downtrend → trend reversal
    - Bearish CHoCH: price breaks below a swing low in an uptrend → trend reversal
    """

    def __init__(self, swing_lookback: int = 3) -> None:
        self._swing_detector = SwingDetector(lookback=swing_lookback)

    def analyze(
        self,
        candles: list[Candle],
        timeframe: str = "H1",
    ) -> MarketStructure:
        """
        Analyze current market structure from candle data.

        Returns MarketStructure with current trend, BOS, CHoCH, swings.
        """
        if len(candles) < 10:
            return MarketStructure(timeframe=timeframe)

        swings = self._swing_detector.detect_swings(candles, timeframe)

        if len(swings) < 4:
            return MarketStructure(timeframe=timeframe)

        # Determine current trend from recent swing sequence
        trend = self._determine_trend(swings)

        # Detect BOS
        bos = self._detect_bos(candles[-1], swings, trend)

        # Detect CHoCH
        choch = self._detect_choch(candles[-1], swings, trend)

        # Get latest swings
        swing_highs = [s for s in swings if s.direction == Direction.SELL]
        swing_lows = [s for s in swings if s.direction == Direction.BUY]

        last_sh = swing_highs[0] if swing_highs else None
        last_sl = swing_lows[0] if swing_lows else None

        # Premium/Discount zone
        current_price = candles[-1].close
        premium_discount = "neutral"
        if last_sh and last_sl:
            midpoint = (last_sh.price + last_sl.price) / 2
            if current_price > midpoint:
                premium_discount = "premium"
            elif current_price < midpoint:
                premium_discount = "discount"

        return MarketStructure(
            timeframe=timeframe,
            trend=trend,
            bos=bos,
            choch=choch,
            last_swing_high=last_sh,
            last_swing_low=last_sl,
            premium_discount=premium_discount,
        )

    def _determine_trend(self, swings: list[SwingPoint]) -> Direction | None:
        """
        Determine trend from swing sequence.

        Uptrend: Higher Highs + Higher Lows
        Downtrend: Lower Highs + Lower Lows
        """
        if len(swings) < 4:
            return None

        # Get recent swing highs and lows
        swing_highs = [s for s in swings if s.direction == Direction.SELL][:3]
        swing_lows = [s for s in swings if s.direction == Direction.BUY][:3]

        if len(swing_highs) < 2 or len(swing_lows) < 2:
            return None

        # Check for higher highs and higher lows (uptrend)
        hh = swing_highs[0].price > swing_highs[1].price  # Most recent HH
        hl = swing_lows[0].price > swing_lows[1].price    # Most recent HL

        # Check for lower highs and lower lows (downtrend)
        lh = swing_highs[0].price < swing_highs[1].price
        ll = swing_lows[0].price < swing_lows[1].price

        if hh and hl:
            return Direction.BUY
        elif lh and ll:
            return Direction.SELL
        else:
            # Mixed — use the most recent swing as tiebreaker
            return swings[0].direction

    def _detect_bos(
        self, current_candle: Candle, swings: list[SwingPoint], current_trend: Direction | None
    ) -> datetime | None:
        """
        Detect Break of Structure.

        BOS happens when price breaks the most recent swing in the trend direction.
        """
        if current_trend is None:
            return None

        swing_highs = [s for s in swings if s.direction == Direction.SELL]
        swing_lows = [s for s in swings if s.direction == Direction.BUY]

        if current_trend == Direction.BUY:
            # Bullish BOS: close above most recent swing high
            if swing_highs and current_candle.close > swing_highs[0].price:
                return current_candle.timestamp

        elif current_trend == Direction.SELL:
            # Bearish BOS: close below most recent swing low
            if swing_lows and current_candle.close < swing_lows[0].price:
                return current_candle.timestamp

        return None

    def _detect_choch(
        self, current_candle: Candle, swings: list[SwingPoint], current_trend: Direction | None
    ) -> datetime | None:
        """
        Detect Change of Character.

        CHoCH happens when price breaks a swing in the OPPOSITE direction of the trend.
        """
        if current_trend is None:
            return None

        swing_highs = [s for s in swings if s.direction == Direction.SELL]
        swing_lows = [s for s in swings if s.direction == Direction.BUY]

        if current_trend == Direction.SELL:
            # Bullish CHoCH: in downtrend, close above most recent swing high
            if swing_highs and current_candle.close > swing_highs[0].price:
                return current_candle.timestamp

        elif current_trend == Direction.BUY:
            # Bearish CHoCH: in uptrend, close below most recent swing low
            if swing_lows and current_candle.close < swing_lows[0].price:
                return current_candle.timestamp

        return None

    def is_bos_confirmed(
        self,
        candles: list[Candle],
        swing_price: float,
        direction: Direction,
        min_body_ratio: float = 0.5,
    ) -> bool:
        """
        Check if a BOS breakout is confirmed:
        - Candle body must be large enough relative to total range
        - Close must be beyond the breakout level
        """
        if not candles:
            return False

        last = candles[-1]
        body = abs(last.close - last.open)
        total_range = last.high - last.low

        if total_range == 0:
            return False

        body_ratio = body / total_range

        if body_ratio < min_body_ratio:
            return False

        if direction == Direction.BUY:
            return last.close > swing_price
        else:
            return last.close < swing_price
