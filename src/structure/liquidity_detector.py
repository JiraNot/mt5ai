"""Liquidity Sweep detection algorithm."""

from __future__ import annotations

import logging
from datetime import datetime

from src.core.types import Candle, Direction, SwingPoint

logger = logging.getLogger(__name__)


class LiquiditySweepDetector:
    """
    Detects Liquidity Sweeps (stop hunts / stop runs).

    A Liquidity Sweep occurs when:
    1. Price breaks beyond a significant swing high/low (sweeping liquidity)
    2. Then reverses back inside the previous range
    3. The break is temporary — price doesn't close beyond the level

    This indicates institutional order flow and is a key setup trigger.
    """

    def __init__(self, wick_ratio_threshold: float = 0.6) -> None:
        """
        Args:
            wick_ratio_threshold: Minimum wick-to-body ratio to qualify as sweep
                                 Higher = more conservative detection
        """
        self._wick_ratio_threshold = wick_ratio_threshold

    def detect(
        self,
        candles: list[Candle],
        swing_highs: list[SwingPoint],
        swing_lows: list[SwingPoint],
        lookback: int = 20,
    ) -> list[dict]:
        """
        Detect liquidity sweeps in recent candles.

        Returns list of sweep events with details:
        {
            "timestamp": datetime,
            "direction": Direction,  # BUY = bearish sweep (swept lows), SELL = bullish sweep (swept highs)
            "swept_level": float,
            "candle": Candle,
            "type": "buy_side" or "sell_side",
        }
        """
        if len(candles) < 5:
            return []

        sweeps = []
        recent_candles = candles[-lookback:] if len(candles) > lookback else candles

        for i, candle in enumerate(recent_candles):
            # Check for sell-side liquidity sweep (swept below swing lows)
            for sl in swing_lows:
                if self._is_sweep_below(candle, sl):
                    sweep_info = self._analyze_sweep(
                        candle, sl.price, Direction.SELL, "sell_side"
                    )
                    if sweep_info:
                        sweeps.append(sweep_info)
                        break  # One sweep per candle

            # Check for buy-side liquidity sweep (swept above swing highs)
            for sh in swing_highs:
                if self._is_sweep_above(candle, sh):
                    sweep_info = self._analyze_sweep(
                        candle, sh.price, Direction.BUY, "buy_side"
                    )
                    if sweep_info:
                        sweeps.append(sweep_info)
                        break

        sweeps.sort(key=lambda s: s["timestamp"], reverse=True)
        return sweeps

    def _is_sweep_below(self, candle: Candle, swing_low: SwingPoint) -> bool:
        """Check if candle swept below a swing low."""
        # Wick goes below the swing low but close is above it
        return candle.low < swing_low.price and candle.close > swing_low.price

    def _is_sweep_above(self, candle: Candle, swing_high: SwingPoint) -> bool:
        """Check if candle swept above a swing high."""
        # Wick goes above the swing high but close is below it
        return candle.high > swing_high.price and candle.close < swing_high.price

    def _analyze_sweep(
        self,
        candle: Candle,
        swept_level: float,
        direction: Direction,
        sweep_type: str,
    ) -> dict | None:
        """
        Analyze a potential sweep candle for quality.

        A good sweep has:
        - Long wick (rejection of the swept level)
        - Small body (indecision / reversal)
        - Close back inside the range
        """
        body = abs(candle.close - candle.open)
        total_range = candle.high - candle.low

        if total_range == 0:
            return None

        # Calculate wick ratio
        if sweep_type == "sell_side":
            wick = candle.close - candle.low  # Lower wick
        else:
            wick = candle.high - candle.close  # Upper wick

        wick_ratio = wick / total_range

        if wick_ratio < self._wick_ratio_threshold:
            return None

        return {
            "timestamp": candle.timestamp,
            "direction": direction,
            "swept_level": swept_level,
            "candle": candle,
            "type": sweep_type,
            "wick_ratio": wick_ratio,
            "strength": min(5, max(1, int(wick_ratio * 5))),
        }

    def has_liquidity_sweep(
        self,
        candles: list[Candle],
        swing_highs: list[SwingPoint],
        swing_lows: list[SwingPoint],
        lookback: int = 5,
    ) -> bool:
        """Quick check: has there been a liquidity sweep in the last N candles?"""
        recent = candles[-lookback:] if len(candles) > lookback else candles
        sweeps = self.detect(recent, swing_highs, swing_lows, lookback=lookback)
        return len(sweeps) > 0
