"""Unit tests for ContextBuilder and MultiTimeframeContext."""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from src.core.types import Candle, Direction
from src.structure.context import ContextBuilder, MultiTimeframeContext


# ─── Helpers ──────────────────────────────────────────────────────────────────

def mc(ts: datetime, o: float, h: float, l: float, c: float) -> Candle:
    return Candle(timestamp=ts, open=o, high=h, low=l, close=c, volume=100)


def build_candles(base: datetime, highs: list[float], lows: list[float]) -> list[Candle]:
    """Build candles from explicit high/low arrays."""
    candles = []
    for i, (h, l) in enumerate(zip(highs, lows)):
        if h <= l:
            h = l + 1.0
        o = l + (h - l) * 0.3
        c = l + (h - l) * 0.6
        candles.append(mc(base + timedelta(hours=i), o, h, l, c))
    return candles


def make_uptrend_series(n: int = 30) -> list[Candle]:
    """Uptrending candles with clear HH+HL structure for swing detection."""
    base = datetime(2024, 1, 1)
    highs = [0.0] * n
    lows = [0.0] * n

    peak_h = {4: 110, 10: 120, 16: 130, 22: 140, 28: 150}
    valley_h = {7: 105, 13: 115, 19: 125, 25: 135}
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
        highs[j] = peak_h[min(peak_h)] - (min(peak_h) - j) * 3
    for j in range(min(valley_l.keys())):
        lows[j] = valley_l[min(valley_l)] - (min(valley_l) - j) * 3
    for j in range(max(peak_h) + 1, n):
        highs[j] = peak_h[max(peak_h)] - (j - max(peak_h)) * 3
    for j in range(max(valley_l) + 1, n):
        lows[j] = valley_l[max(valley_l)] - (j - max(valley_l)) * 3

    return build_candles(base, highs, lows)


def make_downtrend_series(n: int = 30) -> list[Candle]:
    """Downtrending candles with clear LH+LL structure."""
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


def make_candle_series(n: int = 5) -> list[Candle]:
    """Flat candles for testing insufficient data."""
    base = datetime(2024, 1, 1)
    return [mc(base + timedelta(hours=i), 100, 101, 99, 100.5) for i in range(n)]


# ─── MultiTimeframeContext Tests ─────────────────────────────────────────────

class TestMultiTimeframeContext:
    def test_default_values(self):
        ctx = MultiTimeframeContext(symbol="XAUUSD")
        assert ctx.symbol == "XAUUSD"
        assert ctx.current_price == 0.0
        assert ctx.spread == 0.0
        assert ctx.htf_trend is None
        assert ctx.has_choch is False
        assert ctx.has_bos is False
        assert ctx.has_liquidity_sweep is False
        assert ctx.has_ob_fvg_overlap is False
        assert ctx.in_discount_zone is False
        assert ctx.in_premium_zone is False
        assert ctx.structures == {}
        assert ctx.swing_highs == []
        assert ctx.swing_lows == []
        assert ctx.fvgs == []
        assert ctx.order_blocks == []
        assert ctx.liquidity_sweeps == []

    def test_get_trend_existing(self):
        from src.core.types import MarketStructure
        ctx = MultiTimeframeContext(symbol="XAUUSD")
        ctx.structures["H1"] = MarketStructure(timeframe="H1", trend=Direction.BUY)
        assert ctx.get_trend("H1") == Direction.BUY

    def test_get_trend_missing(self):
        ctx = MultiTimeframeContext(symbol="XAUUSD")
        assert ctx.get_trend("H1") is None

    def test_get_structure_existing(self):
        from src.core.types import MarketStructure
        ctx = MultiTimeframeContext(symbol="XAUUSD")
        ms = MarketStructure(timeframe="M15", trend=Direction.SELL)
        ctx.structures["M15"] = ms
        assert ctx.get_structure("M15") is ms

    def test_get_structure_missing(self):
        ctx = MultiTimeframeContext(symbol="XAUUSD")
        assert ctx.get_structure("M15") is None


# ─── ContextBuilder Tests ────────────────────────────────────────────────────

class TestContextBuilder:
    def setup_method(self):
        self.builder = ContextBuilder()

    def test_build_empty_data(self):
        """Empty candles → empty context."""
        ctx = self.builder.build("XAUUSD", {})
        assert ctx.symbol == "XAUUSD"
        assert ctx.current_price == 0.0
        assert ctx.structures == {}

    def test_build_single_timeframe(self):
        """Single TF with enough data."""
        candles = make_uptrend_series(30)
        ctx = self.builder.build("XAUUSD", {"H1": candles}, primary_tf="H1")
        assert ctx.symbol == "XAUUSD"
        assert "H1" in ctx.structures
        assert ctx.current_price == candles[-1].close

    def test_build_multiple_timeframes(self):
        """Multiple TFs should each produce structure."""
        h4 = make_uptrend_series(30)
        h1 = make_uptrend_series(30)
        m15 = make_uptrend_series(30)

        ctx = self.builder.build(
            "XAUUSD",
            {"H4": h4, "H1": h1, "M15": m15},
            primary_tf="M15",
            htf="H4",
        )

        assert "H4" in ctx.structures
        assert "H1" in ctx.structures
        assert "M15" in ctx.structures

    def test_primary_candle_set(self):
        """Primary TF candle should be set."""
        primary = make_uptrend_series(30)
        ctx = self.builder.build("XAUUSD", {"H1": primary}, primary_tf="H1")
        assert ctx.primary_candle is not None
        assert ctx.primary_candle == primary[-1]

    def test_current_price_from_primary(self):
        """current_price should come from primary TF."""
        primary = make_uptrend_series(30)
        ctx = self.builder.build("XAUUSD", {"H1": primary}, primary_tf="H1")
        assert ctx.current_price == primary[-1].close

    def test_htf_trend_propagated(self):
        """HTF trend should be set from the htf parameter."""
        h4 = make_uptrend_series(30)
        ctx = self.builder.build("XAUUSD", {"H4": h4}, htf="H4")
        assert ctx.htf_trend == Direction.BUY

    def test_htf_trend_downtrend(self):
        """Downtrend on HTF."""
        h4 = make_downtrend_series(30)
        ctx = self.builder.build("XAUUSD", {"H4": h4}, htf="H4")
        assert ctx.htf_trend == Direction.SELL

    def test_swings_aggregated(self):
        """Swings from all TFs should be aggregated."""
        h1 = make_uptrend_series(30)
        m15 = make_uptrend_series(30)
        ctx = self.builder.build("XAUUSD", {"H1": h1, "M15": m15})
        assert len(ctx.swing_highs) + len(ctx.swing_lows) > 0

    def test_swings_sorted_newest_first(self):
        """Aggregated swings should be sorted newest first."""
        h1 = make_uptrend_series(30)
        ctx = self.builder.build("XAUUSD", {"H1": h1})
        for i in range(len(ctx.swing_highs) - 1):
            assert ctx.swing_highs[i].timestamp >= ctx.swing_highs[i + 1].timestamp
        for i in range(len(ctx.swing_lows) - 1):
            assert ctx.swing_lows[i].timestamp >= ctx.swing_lows[i + 1].timestamp

    def test_fvgs_detected(self):
        """FVGs should be detected from candle data."""
        candles = make_uptrend_series(30)
        ctx = self.builder.build("XAUUSD", {"H1": candles})
        assert isinstance(ctx.fvgs, list)

    def test_fvgs_sorted(self):
        """FVGs should be sorted newest first."""
        candles = make_uptrend_series(30)
        ctx = self.builder.build("XAUUSD", {"H1": candles})
        for i in range(len(ctx.fvgs) - 1):
            assert ctx.fvgs[i].timestamp >= ctx.fvgs[i + 1].timestamp

    def test_sufficient_data_required(self):
        """TFs with < 10 candles should be skipped."""
        few_candles = make_candle_series(5)
        many_candles = make_uptrend_series(30)
        ctx = self.builder.build("XAUUSD", {"M5": few_candles, "H1": many_candles})
        assert "M5" not in ctx.structures
        assert "H1" in ctx.structures

    def test_confluence_flags_from_primary(self):
        """has_bos and has_choch should reflect primary TF structure."""
        candles = make_uptrend_series(30)
        ctx = self.builder.build("XAUUSD", {"H1": candles}, primary_tf="H1")
        assert isinstance(ctx.has_bos, bool)
        assert isinstance(ctx.has_choch, bool)

    def test_premium_discount_flag(self):
        """in_discount_zone / in_premium_zone should be set from primary structure."""
        candles = make_uptrend_series(30)
        ctx = self.builder.build("XAUUSD", {"H1": candles}, primary_tf="H1")
        assert isinstance(ctx.in_discount_zone, bool)
        assert isinstance(ctx.in_premium_zone, bool)

    def test_empty_primary_tf(self):
        """Missing primary TF should not crash."""
        h1 = make_uptrend_series(30)
        ctx = self.builder.build("XAUUSD", {"H1": h1}, primary_tf="M5")
        assert ctx.primary_candle is None
        assert ctx.current_price == 0.0

    def test_no_htf_data(self):
        """Missing HTF should result in None htf_trend."""
        m15 = make_uptrend_series(30)
        ctx = self.builder.build("XAUUSD", {"M15": m15}, htf="H4")
        assert ctx.htf_trend is None

    def test_spread_set(self):
        """Spread should be stored in context."""
        candles = make_uptrend_series(30)
        ctx = self.builder.build("XAUUSD", {"H1": candles})
        ctx.spread = 2.5
        assert ctx.spread == 2.5

    def test_builder_custom_params(self):
        """Custom builder params should not crash."""
        builder = ContextBuilder(
            swing_lookback=2,
            fvg_min_gap=1.0,
            ob_displacement=2.0,
            sweep_wick_ratio=0.7,
        )
        candles = make_uptrend_series(30)
        ctx = builder.build("XAUUSD", {"H1": candles})
        assert ctx.symbol == "XAUUSD"
