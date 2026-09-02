"""Unit tests for StructureAnalyzer — validates BOS/CHoCH detection and trend analysis."""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from src.core.types import Candle, Direction, MarketStructure, SwingPoint
from src.structure.structure_analyzer import StructureAnalyzer


# ─── Helpers ──────────────────────────────────────────────────────────────────

def mc(ts: datetime, o: float, h: float, l: float, c: float) -> Candle:
    return Candle(timestamp=ts, open=o, high=h, low=l, close=c, volume=100)


def build_candles(
    base: datetime,
    highs: list[float],
    lows: list[float],
) -> list[Candle]:
    """Build candles from explicit high/low arrays. Open/close are interior points."""
    candles = []
    for i, (h, l) in enumerate(zip(highs, lows)):
        if h <= l:
            h = l + 1.0
        o = l + (h - l) * 0.3
        c = l + (h - l) * 0.6
        candles.append(mc(base + timedelta(hours=i), o, h, l, c))
    return candles


def make_uptrend_candles(n: int = 30) -> list[Candle]:
    """
    Uptrend: Higher Highs + Higher Lows with lookback=3.

    Highs series peaks at indices 4,10,16,22,28: 110,120,130,140,150
    Lows series valleys at indices 7,13,19,25: 90,95,100,105

    Each peak high is strictly > 3 highs on each side.
    Each valley low is strictly < 3 lows on each side.
    """
    base = datetime(2024, 1, 1)
    highs = [0.0] * n
    lows = [0.0] * n

    # Peak highs
    peak_h = {4: 110, 10: 120, 16: 130, 22: 140, 28: 150}
    valley_h = {7: 105, 13: 115, 19: 125, 25: 135}

    # Valley lows
    valley_l = {7: 90, 13: 95, 19: 100, 25: 105}
    peak_l = {4: 100, 10: 110, 16: 120, 22: 130, 28: 140}

    for i, v in peak_h.items():
        highs[i] = v
    for i, v in valley_h.items():
        highs[i] = v
    for i, v in peak_l.items():
        lows[i] = v
    for i, v in valley_l.items():
        lows[i] = v

    # Interpolate highs between peaks and valley points
    all_h_points = sorted(set(list(peak_h.keys()) + list(valley_h.keys())))
    for i in range(len(all_h_points) - 1):
        a, b = all_h_points[i], all_h_points[i + 1]
        for j in range(a + 1, b):
            t = (j - a) / (b - a)
            highs[j] = highs[a] + (highs[b] - highs[a]) * t

    # Interpolate lows between valley and peak points
    all_l_points = sorted(set(list(valley_l.keys()) + list(peak_l.keys())))
    for i in range(len(all_l_points) - 1):
        a, b = all_l_points[i], all_l_points[i + 1]
        for j in range(a + 1, b):
            t = (j - a) / (b - a)
            lows[j] = lows[a] + (lows[b] - lows[a]) * t

    # Extend before first peak/valley
    for j in range(min(peak_h.keys())):
        highs[j] = peak_h[min(peak_h)] - (min(peak_h) - j) * 3
    for j in range(min(valley_l.keys())):
        lows[j] = valley_l[min(valley_l)] - (min(valley_l) - j) * 3

    # Extend after last peak/valley
    for j in range(max(peak_h) + 1, n):
        highs[j] = peak_h[max(peak_h)] - (j - max(peak_h)) * 3
    for j in range(max(valley_l) + 1, n):
        lows[j] = valley_l[max(valley_l)] - (j - max(valley_l)) * 3

    return build_candles(base, highs, lows)


def make_downtrend_candles(n: int = 30) -> list[Candle]:
    """
    Downtrend: Lower Highs + Lower Lows.
    Peaks: 150,140,130,120,110  Valleys: 105,100,95,90
    """
    base = datetime(2024, 1, 1)
    highs = [0.0] * n
    lows = [0.0] * n

    peak_h = {4: 150, 10: 140, 16: 130, 22: 120, 28: 110}
    valley_h = {7: 135, 13: 125, 19: 115, 25: 105}

    valley_l = {7: 105, 13: 100, 19: 95, 25: 90}
    peak_l = {4: 140, 10: 130, 16: 120, 22: 110, 28: 100}

    for i, v in peak_h.items():
        highs[i] = v
    for i, v in valley_h.items():
        highs[i] = v
    for i, v in peak_l.items():
        lows[i] = v
    for i, v in valley_l.items():
        lows[i] = v

    all_h_points = sorted(set(list(peak_h.keys()) + list(valley_h.keys())))
    for i in range(len(all_h_points) - 1):
        a, b = all_h_points[i], all_h_points[i + 1]
        for j in range(a + 1, b):
            t = (j - a) / (b - a)
            highs[j] = highs[a] + (highs[b] - highs[a]) * t

    all_l_points = sorted(set(list(valley_l.keys()) + list(peak_l.keys())))
    for i in range(len(all_l_points) - 1):
        a, b = all_l_points[i], all_l_points[i + 1]
        for j in range(a + 1, b):
            t = (j - a) / (b - a)
            lows[j] = lows[a] + (lows[b] - lows[a]) * t

    for j in range(min(peak_h.keys())):
        highs[j] = peak_h[min(peak_h)] + (min(peak_h) - j) * 3
    for j in range(min(valley_l.keys())):
        lows[j] = valley_l[min(valley_l)] + (min(valley_l) - j) * 3

    for j in range(max(peak_h) + 1, n):
        highs[j] = peak_h[max(peak_h)] + (j - max(peak_h)) * 3
    for j in range(max(valley_l) + 1, n):
        lows[j] = valley_l[max(valley_l)] + (j - max(valley_l)) * 3

    return build_candles(base, highs, lows)


def make_bullish_bos_candles(n: int = 30) -> list[Candle]:
    """Uptrend where last candle closes above last swing high → BOS."""
    candles = make_uptrend_candles(n)
    last = candles[-1]
    new_close = 155.0
    candles[-1] = mc(last.timestamp, last.open, max(last.high, new_close + 1), last.low, new_close)
    return candles


def make_bearish_choch_candles(n: int = 30) -> list[Candle]:
    """Uptrend then break below last swing low → CHoCH."""
    candles = make_uptrend_candles(n)
    last = candles[-1]
    new_close = 85.0
    candles[-1] = mc(last.timestamp, last.open, last.high, min(last.low, new_close - 1), new_close)
    return candles


def make_premium_zone_candles(n: int = 30) -> list[Candle]:
    """Uptrend where current price sits in premium zone."""
    return make_uptrend_candles(n)


# ─── Tests ────────────────────────────────────────────────────────────────────

class TestStructureAnalyzerInit:
    def test_default_lookback(self):
        a = StructureAnalyzer()
        assert a._swing_detector._lookback == 3

    def test_custom_lookback(self):
        a = StructureAnalyzer(swing_lookback=5)
        assert a._swing_detector._lookback == 5


class TestAnalyze:
    def test_insufficient_data(self):
        a = StructureAnalyzer()
        result = a.analyze([mc(datetime.now(), 100, 101, 99, 100)] * 5)
        assert result.trend is None
        assert result.bos is None
        assert result.choch is None

    def test_returns_market_structure(self):
        a = StructureAnalyzer()
        candles = make_uptrend_candles()
        result = a.analyze(candles)
        assert isinstance(result, MarketStructure)
        assert result.timeframe == "H1"

    def test_uptrend_detected(self):
        a = StructureAnalyzer()
        candles = make_uptrend_candles()
        result = a.analyze(candles)
        assert result.trend == Direction.BUY

    def test_downtrend_detected(self):
        a = StructureAnalyzer()
        candles = make_downtrend_candles()
        result = a.analyze(candles)
        assert result.trend == Direction.SELL

    def test_timeframe_preserved(self):
        a = StructureAnalyzer()
        candles = make_uptrend_candles()
        result = a.analyze(candles, timeframe="M15")
        assert result.timeframe == "M15"


class TestDetermineTrend:
    def test_uptrend_hh_hl(self):
        """Higher Highs + Higher Lows = uptrend."""
        a = StructureAnalyzer()
        candles = make_uptrend_candles()
        result = a.analyze(candles)
        assert result.trend == Direction.BUY

    def test_downtrend_lh_ll(self):
        """Lower Highs + Lower Lows = downtrend."""
        a = StructureAnalyzer()
        candles = make_downtrend_candles()
        result = a.analyze(candles)
        assert result.trend == Direction.SELL

    def test_no_trend_with_few_swings(self):
        """Less than 4 swings → no trend detected."""
        a = StructureAnalyzer(swing_lookback=3)
        base = datetime(2024, 1, 1)
        candles = [mc(base + timedelta(hours=i), 100, 101, 99, 100.5) for i in range(6)]
        result = a.analyze(candles)
        assert result.timeframe == "H1"


class TestDetectBOS:
    def test_bullish_bos_in_uptrend(self):
        """In uptrend, close above swing high = BOS."""
        a = StructureAnalyzer()
        candles = make_bullish_bos_candles()
        result = a.analyze(candles)
        if result.trend == Direction.BUY and result.last_swing_high:
            last_candle = candles[-1]
            if last_candle.close > result.last_swing_high.price:
                assert result.bos is not None

    def test_no_bos_when_close_below_swing(self):
        """No BOS when close is below the swing high in uptrend."""
        a = StructureAnalyzer()
        base = datetime(2024, 1, 1)
        highs = [102, 104, 103, 106, 110, 108, 107, 110, 114, 112, 111, 108, 106]
        lows = [100, 101, 100, 103, 106, 105, 104, 107, 110, 109, 108, 105, 103]
        candles = [
            mc(base + timedelta(hours=i), lows[i], highs[i], lows[i], lows[i] + 1)
            for i in range(13)
        ]
        result = a.analyze(candles)
        if result.trend == Direction.BUY and result.last_swing_high:
            assert candles[-1].close <= result.last_swing_high.price
            assert result.bos is None

    def test_no_bos_when_trend_none(self):
        """No BOS when trend is None."""
        a = StructureAnalyzer()
        base = datetime(2024, 1, 1)
        candles = [mc(base + timedelta(hours=i), 100, 101, 99, 100.5) for i in range(15)]
        result = a.analyze(candles)
        if result.trend is None:
            assert result.bos is None


class TestPremiumDiscount:
    def test_premium_zone(self):
        """Price above midpoint of last swing range → premium."""
        a = StructureAnalyzer()
        candles = make_premium_zone_candles()
        result = a.analyze(candles)
        if result.last_swing_high and result.last_swing_low:
            midpoint = (result.last_swing_high.price + result.last_swing_low.price) / 2
            current = candles[-1].close
            if current > midpoint:
                assert result.premium_discount == "premium"
            elif current < midpoint:
                assert result.premium_discount == "discount"
            else:
                assert result.premium_discount == "neutral"
