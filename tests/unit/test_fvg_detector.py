"""Unit tests for FVGDetector — validates Fair Value Gap detection."""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from src.core.types import Candle, Direction, FairValueGap
from src.structure.fvg_detector import FVGDetector


# ─── Helpers ──────────────────────────────────────────────────────────────────

def make_candle(
    ts: datetime,
    open_: float,
    high: float,
    low: float,
    close: float,
    volume: float = 100.0,
) -> Candle:
    return Candle(timestamp=ts, open=open_, high=high, low=low, close=close, volume=volume)


def make_bullish_fvg_pattern() -> list[Candle]:
    """
    Classic Bullish FVG: 3-candle pattern where c1.low > c3.high

    c1: Open=100, High=102, Low=99,  Close=101  (bullish)
    c2: Open=101, High=108, Low=100, Close=107  (strong bullish displacement)
    c3: Open=107, High=99.5, Low=98, Close=100  (pullback — note high < c1.low)

    Gap: c1.low (99) > c3.high (99.5)? No — 99 < 99.5.
    Let me fix this.

    Bullish FVG requires: c1.low > c3.high
    So c1 must have a higher low than c3's high.
    """
    base = datetime(2024, 1, 1)
    return [
        make_candle(base, 100, 102, 99, 101),       # c1: bullish, low=99
        make_candle(base + timedelta(hours=1), 101, 110, 100, 109),  # c2: big bullish displacement
        make_candle(base + timedelta(hours=2), 108, 100, 97, 98),    # c3: bearish pullback, high=100
    ]
    # Gap check: c1.low (99) > c3.high (100)? No! 99 < 100 → no FVG
    # I need to swap: c1 should have higher low than c3 high


def make_bullish_fvg_data() -> list[Candle]:
    """
    Correct Bullish FVG: c1.low > c3.high

    c1: low=102  (price was at 102-108 range)
    c2: big bullish candle, low=101, high=112
    c3: high=101  (pullback only reached 101)

    Gap: c1.low (102) > c3.high (101) → gap of $1.00
    """
    base = datetime(2024, 1, 1)
    return [
        make_candle(base, 103, 108, 102, 107),                    # c1: low=102
        make_candle(base + timedelta(hours=1), 107, 115, 101, 114), # c2: displacement up
        make_candle(base + timedelta(hours=2), 113, 101, 98, 99),   # c3: high=101
    ]
    # Gap: c1.low=102 > c3.high=101 → gap_size = 1.00 ✓


def make_bearish_fvg_data() -> list[Candle]:
    """
    Bearish FVG: c1.high < c3.low

    c1: high=100  (was at 95-100 range)
    c2: big bearish candle, high=101, low=90
    c3: low=101  (bounce only reached 101)

    Gap: c1.high (100) < c3.low (101) → gap of $1.00
    """
    base = datetime(2024, 1, 1)
    return [
        make_candle(base, 97, 100, 95, 96),                       # c1: high=100
        make_candle(base + timedelta(hours=1), 96, 101, 88, 89),   # c2: displacement down
        make_candle(base + timedelta(hours=2), 90, 105, 101, 104), # c3: low=101
    ]
    # Gap: c1.high=100 < c3.low=101 → gap_size = 1.00 ✓


def make_no_fvg_data() -> list[Candle]:
    """
    No FVG: candles overlap, no gap.
    """
    base = datetime(2024, 1, 1)
    return [
        make_candle(base, 100, 103, 99, 102),
        make_candle(base + timedelta(hours=1), 102, 105, 101, 104),
        make_candle(base + timedelta(hours=2), 103, 104, 100, 101),
    ]


def make_small_gap_data() -> list[Candle]:
    """
    Bullish FVG with very small gap (below min_gap_size).
    c1.low = 100.2, c3.high = 100.0 → gap = 0.2 (below 0.5 default)
    """
    base = datetime(2024, 1, 1)
    return [
        make_candle(base, 100, 101, 100.2, 100.8),
        make_candle(base + timedelta(hours=1), 100.8, 103, 100, 102.5),
        make_candle(base + timedelta(hours=2), 102, 100, 99, 99.5),
    ]


# ─── Tests ────────────────────────────────────────────────────────────────────

class TestFVGDetection:
    """Test core FVG detection algorithm."""

    def test_insufficient_data(self):
        """Need at least 3 candles."""
        d = FVGDetector()
        assert d.detect([]) == []
        assert d.detect([make_candle(datetime.now(), 100, 101, 99, 100)]) == []
        assert d.detect([
            make_candle(datetime.now(), 100, 101, 99, 100),
            make_candle(datetime.now(), 100, 101, 99, 100),
        ]) == []

    def test_bullish_fvg_detected(self):
        """Detect a bullish FVG when c1.low > c3.high."""
        d = FVGDetector(min_gap_size=0.5)
        candles = make_bullish_fvg_data()
        fvgs = d.detect(candles)

        assert len(fvgs) == 1
        fvg = fvgs[0]
        assert fvg.direction == Direction.BUY
        assert fvg.upper_price == 102.0   # c1.low
        assert fvg.lower_price == 101.0   # c3.high
        assert fvg.timeframe == "H1"

    def test_bearish_fvg_detected(self):
        """Detect a bearish FVG when c1.high < c3.low."""
        d = FVGDetector(min_gap_size=0.5)
        candles = make_bearish_fvg_data()
        fvgs = d.detect(candles)

        assert len(fvgs) == 1
        fvg = fvgs[0]
        assert fvg.direction == Direction.SELL
        assert fvg.upper_price == 101.0   # c3.low
        assert fvg.lower_price == 100.0   # c1.high

    def test_no_fvg_when_overlapping(self):
        """No FVG when candles overlap (no gap)."""
        d = FVGDetector(min_gap_size=0.5)
        candles = make_no_fvg_data()
        fvgs = d.detect(candles)
        assert len(fvgs) == 0

    def test_small_gap_below_threshold(self):
        """Gap smaller than min_gap_size is ignored."""
        d = FVGDetector(min_gap_size=0.5)
        candles = make_small_gap_data()
        fvgs = d.detect(candles)
        # Gap is 0.2, threshold is 0.5 → no FVG
        assert len(fvgs) == 0

    def test_multiple_fvgs_in_series(self):
        """Multiple FVGs can appear in a longer series."""
        d = FVGDetector(min_gap_size=0.5)
        base = datetime(2024, 1, 1)

        # Two bullish FVGs separated by some candles
        candles = [
            # First FVG: c1.low=102, c3.high=101 → gap 1.0
            make_candle(base, 100, 103, 102, 102.5),
            make_candle(base + timedelta(hours=1), 102.5, 108, 101, 107),
            make_candle(base + timedelta(hours=2), 106, 101, 99, 100),
            # Filler candles
            make_candle(base + timedelta(hours=3), 100, 102, 99, 101),
            make_candle(base + timedelta(hours=4), 101, 103, 100, 102),
            # Second FVG: c1.low=103, c3.high=102 → gap 1.0
            make_candle(base + timedelta(hours=5), 102, 104, 103, 103.5),
            make_candle(base + timedelta(hours=6), 103.5, 110, 102, 109),
            make_candle(base + timedelta(hours=7), 108, 102, 100, 101),
        ]
        fvgs = d.detect(candles)
        assert len(fvgs) >= 2

    def test_fvgs_sorted_newest_first(self):
        """FVGs should be sorted with most recent first."""
        d = FVGDetector(min_gap_size=0.5)
        base = datetime(2024, 1, 1)

        # Create two FVGs
        candles = [
            make_candle(base, 100, 103, 102, 102.5),
            make_candle(base + timedelta(hours=1), 102.5, 108, 101, 107),
            make_candle(base + timedelta(hours=2), 106, 101, 99, 100),
            make_candle(base + timedelta(hours=3), 100, 102, 99, 101),
            make_candle(base + timedelta(hours=4), 101, 103, 100, 102),
            make_candle(base + timedelta(hours=5), 102, 104, 103, 103.5),
            make_candle(base + timedelta(hours=6), 103.5, 110, 102, 109),
            make_candle(base + timedelta(hours=7), 108, 102, 100, 101),
        ]
        fvgs = d.detect(candles)
        if len(fvgs) >= 2:
            assert fvgs[0].timestamp >= fvgs[1].timestamp

    def test_timeframe_preserved(self):
        """FVG should carry the specified timeframe."""
        d = FVGDetector(min_gap_size=0.5)
        candles = make_bullish_fvg_data()
        fvgs = d.detect(candles, timeframe="M15")
        assert fvgs[0].timeframe == "M15"

    def test_fvg_properties(self):
        """Test FVG computed properties."""
        d = FVGDetector(min_gap_size=0.5)
        candles = make_bullish_fvg_data()
        fvgs = d.detect(candles)
        fvg = fvgs[0]

        assert fvg.midpoint == pytest.approx(101.5, abs=0.01)
        assert fvg.zone_size == pytest.approx(1.0, abs=0.01)


class TestFVGValidity:
    """Test FVG validity filtering."""

    def test_valid_fvg_near_price(self):
        """A bullish FVG is valid when price is above its lower_price."""
        d = FVGDetector(min_gap_size=0.5)
        candles = make_bullish_fvg_data()
        fvgs = d.detect(candles)
        fvg = fvgs[0]

        valid = d.find_valid_fvgs(fvgs, current_price=105.0)
        assert fvg in valid

    def test_valid_fvg_at_price(self):
        """Price inside the FVG zone is valid."""
        d = FVGDetector(min_gap_size=0.5)
        candles = make_bullish_fvg_data()
        fvgs = d.detect(candles)
        fvg = fvgs[0]

        valid = d.find_valid_fvgs(fvgs, current_price=101.5)
        assert fvg in valid

    def test_invalid_fvg_below_price(self):
        """Bearish FVG is invalid when price is above its upper_price."""
        d = FVGDetector(min_gap_size=0.5)
        candles = make_bearish_fvg_data()
        fvgs = d.detect(candles)
        fvg = fvgs[0]

        valid = d.find_valid_fvgs(fvgs, current_price=105.0)
        assert fvg not in valid


class TestFVGPriceCheck:
    """Test is_price_in_fvg helper."""

    def test_price_inside_fvg(self):
        d = FVGDetector()
        fvg = FairValueGap(
            timestamp=datetime.now(),
            direction=Direction.BUY,
            upper_price=102,
            lower_price=100,
            timeframe="H1",
        )
        assert d.is_price_in_fvg(101, fvg) is True
        assert d.is_price_in_fvg(100, fvg) is True
        assert d.is_price_in_fvg(102, fvg) is True

    def test_price_outside_fvg(self):
        d = FVGDetector()
        fvg = FairValueGap(
            timestamp=datetime.now(),
            direction=Direction.BUY,
            upper_price=102,
            lower_price=100,
            timeframe="H1",
        )
        assert d.is_price_in_fvg(99, fvg) is False
        assert d.is_price_in_fvg(103, fvg) is False
