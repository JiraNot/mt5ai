"""Equal Highs / Equal Lows (EQH/EQL) Detector.

ตรวจ Liquidity Pools:
- EQH = Buy-Side Liquidity: High ที่ชนซ้ำหลายครั้ง
- EQL = Sell-Side Liquidity: Low ที่ชนซ้ำหลายครั้ง

ไอเดียจาก github.com/joshyattridge/smart-money-concepts
"""
from __future__ import annotations
import logging
from dataclasses import dataclass, field
from src.core.types import Candle

logger = logging.getLogger(__name__)


@dataclass
class EqualLevel:
    price: float
    touch_count: int
    first_touch_index: int
    last_touch_index: int
    level_type: str
    strength: float
    tolerance_pips: float


@dataclass
class EQLResult:
    equal_highs: list[EqualLevel] = field(default_factory=list)
    equal_lows: list[EqualLevel] = field(default_factory=list)
    nearest_high: EqualLevel | None = None
    nearest_low: EqualLevel | None = None
    distance_to_nearest_high_pips: float = 0.0
    distance_to_nearest_low_pips: float = 0.0
    confluence_score: float = 0.0
    summary: str = ""

    @property
    def has_equal_highs(self) -> bool:
        return len(self.equal_highs) > 0

    @property
    def has_equal_lows(self) -> bool:
        return len(self.equal_lows) > 0


class EqualHighsLowsDetector:
    """ตรวจ EQH/EQL (Liquidity Pools) สำหรับ XAUUSD."""

    def __init__(
        self,
        tolerance_pct: float = 0.002,
        min_touches: int = 2,
        lookback: int = 100,
        proximity_pct: float = 0.005,
    ):
        self.tolerance_pct = tolerance_pct
        self.min_touches = min_touches
        self.lookback = lookback
        self.proximity_pct = proximity_pct

    def detect(self, candles: list[Candle]) -> EQLResult:
        if len(candles) < self.min_touches + 1:
            return EQLResult(summary="ข้อมูลไม่เพียงพอ")
        recent = candles[-self.lookback:]
        current_price = recent[-1].close
        equal_highs = self._find_equal_levels(recent, is_high=True)
        equal_lows = self._find_equal_levels(recent, is_high=False)
        result = EQLResult(equal_highs=equal_highs, equal_lows=equal_lows)
        if equal_highs:
            result.nearest_high = min(equal_highs, key=lambda lv: abs(lv.price - current_price))
            result.distance_to_nearest_high_pips = abs(result.nearest_high.price - current_price) / current_price * 10000
        if equal_lows:
            result.nearest_low = min(equal_lows, key=lambda lv: abs(lv.price - current_price))
            result.distance_to_nearest_low_pips = abs(result.nearest_low.price - current_price) / current_price * 10000
        result.confluence_score = self._calculate_confluence(result, current_price)
        result.summary = self._build_summary(result)
        logger.debug("EQL: %d EQH, %d EQL | confluence=%.1f", len(equal_highs), len(equal_lows), result.confluence_score)
        return result

    def _find_equal_levels(self, candles: list[Candle], is_high: bool) -> list[EqualLevel]:
        prices = [c.high for c in candles] if is_high else [c.low for c in candles]
        level_type = "EQH" if is_high else "EQL"
        levels: list[EqualLevel] = []
        used: set[int] = set()
        for i, price in enumerate(prices):
            if i in used:
                continue
            tol = price * self.tolerance_pct
            group = [i]
            for j in range(i + 1, len(prices)):
                if j not in used and abs(prices[j] - price) <= tol:
                    group.append(j)
            if len(group) >= self.min_touches:
                avg = sum(prices[k] for k in group) / len(group)
                levels.append(EqualLevel(price=avg, touch_count=len(group),
                    first_touch_index=min(group), last_touch_index=max(group),
                    level_type=level_type, strength=min(100.0, len(group) * 25.0),
                    tolerance_pips=tol * 10000))
                used.update(group)
        return sorted(levels, key=lambda lv: (-lv.strength, -lv.touch_count))

    def _calculate_confluence(self, result: EQLResult, current_price: float) -> float:
        score = 0.0
        if result.nearest_high and abs(result.nearest_high.price - current_price) / current_price <= self.proximity_pct:
            score += result.nearest_high.strength * 0.3
        if result.nearest_low and abs(result.nearest_low.price - current_price) / current_price <= self.proximity_pct:
            score += result.nearest_low.strength * 0.3
        return min(30.0, score)

    def _build_summary(self, result: EQLResult) -> str:
        parts = []
        if result.equal_highs:
            t = result.equal_highs[0]
            parts.append(f"EQH {t.price:.2f} (ชน {t.touch_count} ครั้ง) = Buy-side Liquidity")
        if result.equal_lows:
            b = result.equal_lows[0]
            parts.append(f"EQL {b.price:.2f} (ชน {b.touch_count} ครั้ง) = Sell-side Liquidity")
        if result.nearest_high and result.distance_to_nearest_high_pips < 50:
            parts.append(f"ระวัง Sweep EQH {result.distance_to_nearest_high_pips:.1f} pips")
        if result.nearest_low and result.distance_to_nearest_low_pips < 50:
            parts.append(f"ระวัง Sweep EQL {result.distance_to_nearest_low_pips:.1f} pips")
        return " | ".join(parts) if parts else "ไม่พบ EQH/EQL ที่มีนัยสำคัญ"
