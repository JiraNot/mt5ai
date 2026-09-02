"""Multi-Timeframe context builder — aggregates structure across timeframes."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from src.core.types import (
    Candle,
    Direction,
    FairValueGap,
    MarketStructure,
    OrderBlock,
    SwingPoint,
)
from src.structure.fvg_detector import FVGDetector
from src.structure.liquidity_detector import LiquiditySweepDetector
from src.structure.order_block_detector import OrderBlockDetector
from src.structure.structure_analyzer import StructureAnalyzer
from src.structure.swing_detector import SwingDetector

logger = logging.getLogger(__name__)


@dataclass
class MultiTimeframeContext:
    """
    Aggregated context from multiple timeframes.
    This is the input to all strategy plugins.
    """

    symbol: str
    current_price: float = 0.0
    spread: float = 0.0

    # Per-timeframe structure
    structures: dict[str, MarketStructure] = field(default_factory=dict)

    # Aggregated data
    swing_highs: list[SwingPoint] = field(default_factory=list)
    swing_lows: list[SwingPoint] = field(default_factory=list)
    fvgs: list[FairValueGap] = field(default_factory=list)
    order_blocks: list[OrderBlock] = field(default_factory=list)
    liquidity_sweeps: list[dict] = field(default_factory=list)

    # Primary timeframe candle
    primary_candle: Candle | None = None

    # HTF trend (H4 or D1)
    htf_trend: Direction | None = None

    # Key confluences
    has_choch: bool = False
    has_bos: bool = False
    has_liquidity_sweep: bool = False
    has_ob_fvg_overlap: bool = False
    in_discount_zone: bool = False
    in_premium_zone: bool = False

    def get_trend(self, timeframe: str) -> Direction | None:
        """Get trend for a specific timeframe."""
        structure = self.structures.get(timeframe)
        return structure.trend if structure else None

    def get_structure(self, timeframe: str) -> MarketStructure | None:
        """Get full structure for a timeframe."""
        return self.structures.get(timeframe)


class ContextBuilder:
    """
    Builds MultiTimeframeContext from candle data across timeframes.
    """

    def __init__(
        self,
        swing_lookback: int = 3,
        fvg_min_gap: float = 0.5,
        ob_displacement: float = 1.5,
        sweep_wick_ratio: float = 0.6,
    ) -> None:
        self._structure_analyzer = StructureAnalyzer(swing_lookback)
        self._swing_detector = SwingDetector(swing_lookback)
        self._fvg_detector = FVGDetector(fvg_min_gap)
        self._ob_detector = OrderBlockDetector(ob_displacement)
        self._liquidity_detector = LiquiditySweepDetector(sweep_wick_ratio)

    def build(
        self,
        symbol: str,
        candles_by_tf: dict[str, list[Candle]],
        primary_tf: str = "M5",
        htf: str = "H4",
    ) -> MultiTimeframeContext:
        """
        Build full context from candles across all timeframes.

        Args:
            symbol: Trading symbol
            candles_by_tf: Dict of timeframe -> list of candles
            primary_tf: Primary execution timeframe
            htf: Higher timeframe for trend
        """
        ctx = MultiTimeframeContext(symbol=symbol)

        # Get current price from primary timeframe
        primary_candles = candles_by_tf.get(primary_tf, [])
        if primary_candles:
            ctx.primary_candle = primary_candles[-1]
            ctx.current_price = primary_candles[-1].close

        # Analyze each timeframe
        for tf, candles in candles_by_tf.items():
            if len(candles) < 10:
                continue

            structure = self._structure_analyzer.analyze(candles, tf)
            ctx.structures[tf] = structure

            # Collect swings from all timeframes
            swings = self._swing_detector.detect_swings(candles, tf)
            for s in swings:
                if s.direction == Direction.SELL:
                    ctx.swing_highs.append(s)
                else:
                    ctx.swing_lows.append(s)

            # Detect FVGs
            fvgs = self._fvg_detector.detect(candles, tf)
            ctx.fvgs.extend(fvgs)

            # Detect Order Blocks
            obs = self._ob_detector.detect(candles, fvgs, tf)
            ctx.order_blocks.extend(obs)

            # Detect Liquidity Sweeps
            swing_highs = [s for s in swings if s.direction == Direction.SELL]
            swing_lows = [s for s in swings if s.direction == Direction.BUY]
            sweeps = self._liquidity_detector.detect(candles, swing_highs, swing_lows)
            ctx.liquidity_sweeps.extend(sweeps)

        # Sort aggregated data
        ctx.swing_highs.sort(key=lambda s: s.timestamp, reverse=True)
        ctx.swing_lows.sort(key=lambda s: s.timestamp, reverse=True)
        ctx.fvgs.sort(key=lambda f: f.timestamp, reverse=True)
        ctx.order_blocks.sort(key=lambda o: o.timestamp, reverse=True)
        ctx.liquidity_sweeps.sort(key=lambda s: s["timestamp"], reverse=True)

        # Set HTF trend
        ctx.htf_trend = ctx.get_trend(htf)

        # Set confluence flags
        primary_structure = ctx.structures.get(primary_tf)
        if primary_structure:
            ctx.has_choch = primary_structure.choch is not None
            ctx.has_bos = primary_structure.bos is not None
            ctx.in_discount_zone = primary_structure.premium_discount == "discount"
            ctx.in_premium_zone = primary_structure.premium_discount == "premium"

        if ctx.liquidity_sweeps:
            ctx.has_liquidity_sweep = True

        # Check OB/FVG overlap
        for ob in ctx.order_blocks:
            if ob.fvg_overlap:
                ctx.has_ob_fvg_overlap = True
                break

        return ctx
