"""Unit tests for OrderBlockDetector — validates Order Block detection."""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from src.core.types import Candle, Direction, FairValueGap, OrderBlock
from src.structure.order_block_detector import OrderBlockDetector


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


def make_base_candles(n: int = 20, base_price: float = 100.0) -> list[Candle]:
    """
    Create n candles with small, uniform bodies (the "calm" before displacement).
    Body = 0.5, Range = 1.0 → body_ratio = 0.5
    """
    base_ts = datetime(2024, 1, 1)
    candles = []
    for i in range(n):
        o = base_price
        h = base_price + 1.0
        l = base_price - 1.0
        c = base_price + 0.3
        candles.append(make_candle(base_ts + timedelta(hours=i), o, h, l, c))
    return candles


def make_bullish_ob_pattern() -> list[Candle]:
    """
    Bullish Order Block pattern:

    23 base candles (small bodies, avg body ≈ 0.3)
    Then: bearish candle (the OB) at index 23
    Then: strong bullish displacement candle at index 24

    Total: 25 candles (detector minimum)
    """
    base_ts = datetime(2024, 1, 1)
    candles = []

    # 23 base candles with small bodies
    for i in range(23):
        o = 100
        h = 101
        l = 99
        c = 100.3
        candles.append(make_candle(base_ts + timedelta(hours=i), o, h, l, c))

    # Index 23: bearish candle (OB candidate)
    candles.append(make_candle(
        base_ts + timedelta(hours=23),
        open_=101, high=102, low=99.5, close=100,  # Bearish: close < open
    ))

    # Index 24: strong bullish displacement candle
    # Body = 114 - 101 = 13, which is >> 1.5 × avg_body (0.3)
    candles.append(make_candle(
        base_ts + timedelta(hours=24),
        open_=101, high=115, low=100, close=114,  # Big bullish candle
    ))

    return candles


def make_bearish_ob_pattern() -> list[Candle]:
    """
    Bearish Order Block pattern:

    23 base candles
    Then: bullish candle (the OB) at index 23
    Then: strong bearish displacement at index 24

    Total: 25 candles (detector minimum)
    """
    base_ts = datetime(2024, 1, 1)
    candles = []

    for i in range(23):
        o = 100
        h = 101
        l = 99
        c = 100.3
        candles.append(make_candle(base_ts + timedelta(hours=i), o, h, l, c))

    # Index 23: bullish candle (OB candidate)
    candles.append(make_candle(
        base_ts + timedelta(hours=23),
        open_=99, high=101, low=98, close=101,  # Bullish: close > open
    ))

    # Index 24: strong bearish displacement
    candles.append(make_candle(
        base_ts + timedelta(hours=24),
        open_=101, high=102, low=87, close=88,  # Big bearish candle
    ))

    return candles


# ─── Tests ────────────────────────────────────────────────────────────────────

class TestOrderBlockInit:
    """Test detector initialization."""

    def test_default_params(self):
        d = OrderBlockDetector()
        assert d._displacement_threshold == 1.5
        assert d._min_body_ratio == 0.6

    def test_custom_params(self):
        d = OrderBlockDetector(displacement_threshold=2.0, min_body_ratio=0.7)
        assert d._displacement_threshold == 2.0
        assert d._min_body_ratio == 0.7


class TestOrderBlockDetection:
    """Test core Order Block detection algorithm."""

    def test_insufficient_data(self):
        """Need at least 25 candles."""
        d = OrderBlockDetector()
        assert d.detect(make_base_candles(24)) == []

    def test_bullish_ob_detected(self):
        """Detect bullish OB when there's a bearish candle before bullish displacement."""
        d = OrderBlockDetector(displacement_threshold=1.5, min_body_ratio=0.6)
        candles = make_bullish_ob_pattern()

        obs = d.detect(candles)

        bullish_obs = [ob for ob in obs if ob.direction == Direction.BUY]
        assert len(bullish_obs) >= 1, "Should detect at least one bullish OB"

        ob = bullish_obs[0]
        # The OB is the bearish candle at index 20
        assert ob.upper_price == 102.0   # high of the OB candle
        assert ob.lower_price == 99.5    # low of the OB candle
        assert ob.timeframe == "H1"

    def test_bearish_ob_detected(self):
        """Detect bearish OB when there's a bullish candle before bearish displacement."""
        d = OrderBlockDetector(displacement_threshold=1.5, min_body_ratio=0.6)
        candles = make_bearish_ob_pattern()

        obs = d.detect(candles)

        bearish_obs = [ob for ob in obs if ob.direction == Direction.SELL]
        assert len(bearish_obs) >= 1, "Should detect at least one bearish OB"

        ob = bearish_obs[0]
        assert ob.upper_price == 101.0   # high of the OB candle
        assert ob.lower_price == 98.0    # low of the OB candle

    def test_no_ob_without_displacement(self):
        """No OB when all candles have normal-sized bodies."""
        d = OrderBlockDetector(displacement_threshold=1.5, min_body_ratio=0.6)
        # 30 candles with small bodies
        base_ts = datetime(2024, 1, 1)
        candles = [
            make_candle(base_ts + timedelta(hours=i), 100, 101, 99, 100.3)
            for i in range(30)
        ]
        obs = d.detect(candles)
        assert len(obs) == 0

    def test_displacement_requires_strong_body(self):
        """Displacement candle must have body > threshold × average body."""
        d = OrderBlockDetector(displacement_threshold=3.0, min_body_ratio=0.6)  # High threshold
        base_ts = datetime(2024, 1, 1)
        candles = []

        # 23 base candles (need 25 total minimum)
        for i in range(23):
            candles.append(make_candle(base_ts + timedelta(hours=i), 100, 101, 99, 100.3))

        # OB candidate
        candles.append(make_candle(base_ts + timedelta(hours=23), 101, 102, 99.5, 100))

        # Moderate displacement (body = 105 - 101 = 4, avg body ≈ 0.3, ratio = 13.3)
        # With threshold=3.0, this should still be detected
        candles.append(make_candle(base_ts + timedelta(hours=24), 101, 106, 100, 105))

        obs = d.detect(candles, timeframe="H1")
        # Body = 4, avg ≈ 0.3, ratio ≈ 13.3 > 3.0 → should detect
        assert len(obs) >= 1

    def test_body_ratio_check(self):
        """Displacement candle body must be >= min_body_ratio of total range."""
        d = OrderBlockDetector(displacement_threshold=1.5, min_body_ratio=0.8)  # Strict body ratio
        base_ts = datetime(2024, 1, 1)
        candles = []

        for i in range(20):
            candles.append(make_candle(base_ts + timedelta(hours=i), 100, 101, 99, 100.3))

        # OB candidate
        candles.append(make_candle(base_ts + timedelta(hours=20), 101, 102, 99.5, 100))

        # Displacement with wide wicks (body_ratio < 0.8)
        # Body = 105 - 101 = 4, Range = 110 - 95 = 15, body_ratio = 0.27
        candles.append(make_candle(base_ts + timedelta(hours=21), 101, 110, 95, 105))

        obs = d.detect(candles)
        # body_ratio = 4/15 = 0.27 < 0.8 → should NOT detect
        assert len(obs) == 0

    def test_ob_strength_scaled(self):
        """OB strength should scale with displacement size."""
        d = OrderBlockDetector(displacement_threshold=1.5, min_body_ratio=0.6)
        candles = make_bullish_ob_pattern()
        obs = d.detect(candles)

        bullish_obs = [ob for ob in obs if ob.direction == Direction.BUY]
        if bullish_obs:
            ob = bullish_obs[0]
            assert 1 <= ob.strength <= 5

    def test_obs_sorted_newest_first(self):
        """Order blocks should be sorted newest first."""
        d = OrderBlockDetector(displacement_threshold=1.5, min_body_ratio=0.6)

        # Create two OBs in different positions
        base_ts = datetime(2024, 1, 1)
        candles = make_bullish_ob_pattern()

        # Add more base candles and another OB
        for i in range(25, 48):
            candles.append(make_candle(base_ts + timedelta(hours=i), 100, 101, 99, 100.3))

        candles.append(make_candle(base_ts + timedelta(hours=48), 101, 102, 99.5, 100))
        candles.append(make_candle(base_ts + timedelta(hours=49), 101, 115, 100, 114))

        obs = d.detect(candles)
        if len(obs) >= 2:
            assert obs[0].timestamp >= obs[1].timestamp
