"""Bitcoin Macro Regime Analyzer.

Evaluates Bitcoin (BTCUSDT) higher timeframe structure and funding rate
to determine overall crypto market sentiment and bias for trade setups.
"""

from __future__ import annotations

import logging
from dataclasses import asdict, dataclass
from typing import Any

from src.core.types import Candle, Direction
from src.structure.regime import MarketRegime, MarketRegimeDetector, RegimeResult

logger = logging.getLogger(__name__)


@dataclass
class BTCRegimeReport:
    """Detailed Bitcoin macro analysis report."""

    symbol: str
    regime: MarketRegime
    trend_direction: Direction | None
    trend_strength: float  # -1.0 to 1.0
    confidence: float      # 0.0 to 1.0
    funding_rate: float    # e.g. 0.0001 = 0.01%
    funding_bias: str      # "LONG_CROWDED", "SHORT_CROWDED", "NEUTRAL"
    current_price: float
    h4_high: float
    h4_low: float
    is_tradable: bool
    recommendation_th: str

    def to_context_dict(self) -> dict[str, Any]:
        """Convert report to dict suitable for AI Council prompt context."""
        return {
            "btc_symbol": self.symbol,
            "btc_regime": self.regime.value,
            "btc_trend": self.trend_direction.value if self.trend_direction else "NEUTRAL",
            "btc_confidence": round(self.confidence, 2),
            "btc_funding_rate": f"{self.funding_rate * 100:.4f}%",
            "btc_funding_bias": self.funding_bias,
            "btc_price": self.current_price,
            "btc_recommendation_th": self.recommendation_th,
        }

    def summary(self) -> str:
        trend_str = self.trend_direction.value if self.trend_direction else "NEUTRAL"
        return (
            f"BTC: {trend_str} ({self.regime.value}, Conf: {self.confidence:.0%}) | "
            f"Funding: {self.funding_rate * 100:.4f}% [{self.funding_bias}] | "
            f"{self.recommendation_th}"
        )


class BTCRegimeAnalyzer:
    """Analyzes Bitcoin (BTCUSDT) market structure and funding rate."""

    def __init__(self) -> None:
        self.detector = MarketRegimeDetector()

    def analyze(
        self,
        h4_candles: list[Candle],
        funding_rate: float = 0.0,
        symbol: str = "BTCUSDT",
    ) -> BTCRegimeReport:
        """Run macro analysis on BTC candles and funding rate."""
        if not h4_candles:
            return BTCRegimeReport(
                symbol=symbol,
                regime=MarketRegime.UNKNOWN,
                trend_direction=None,
                trend_strength=0.0,
                confidence=0.0,
                funding_rate=funding_rate,
                funding_bias="NEUTRAL",
                current_price=0.0,
                h4_high=0.0,
                h4_low=0.0,
                is_tradable=False,
                recommendation_th="ไม่มีข้อมูลแท่งเทียน BTC เพียงพอสำหรับการวิเคราะห์",
            )

        regime_result: RegimeResult = self.detector.detect(h4_candles)
        current_price = h4_candles[-1].close
        recent_bars = h4_candles[-20:]
        h4_high = max(c.high for c in recent_bars)
        h4_low = min(c.low for c in recent_bars)

        # Funding rate classification
        if funding_rate >= 0.0003:  # >= +0.03% (8h)
            funding_bias = "LONG_CROWDED"
        elif funding_rate <= -0.0001:  # <= -0.01% (8h)
            funding_bias = "SHORT_CROWDED"
        else:
            funding_bias = "NEUTRAL"

        # Thai recommendation based on market regime and funding
        recommendation = self._generate_recommendation(
            regime_result.regime, regime_result.trend_direction, funding_bias, regime_result.is_tradable
        )

        return BTCRegimeReport(
            symbol=symbol,
            regime=regime_result.regime,
            trend_direction=regime_result.trend_direction,
            trend_strength=regime_result.trend_strength,
            confidence=regime_result.confidence,
            funding_rate=funding_rate,
            funding_bias=funding_bias,
            current_price=current_price,
            h4_high=h4_high,
            h4_low=h4_low,
            is_tradable=regime_result.is_tradable,
            recommendation_th=recommendation,
        )

    def _generate_recommendation(
        self,
        regime: MarketRegime,
        trend: Direction | None,
        funding_bias: str,
        is_tradable: bool,
    ) -> str:
        parts: list[str] = []

        if regime in (MarketRegime.STRONG_UPTREND, MarketRegime.UPTREND):
            parts.append("BTC อยู่ในแนวโน้มขาขึ้น (Bullish Bias) ให้น้ำหนักฝั่ง BUY ในเหรียญที่มี Momentum สอดคล้อง")
            if funding_bias == "LONG_CROWDED":
                parts.append("แต่ Funding Rate ฝั่ง Long หนาแน่น ระวังการทุบกวาด Liquidity (Flush) ก่อนขึ้นต่อ")
        elif regime in (MarketRegime.STRONG_DOWNTREND, MarketRegime.DOWNTREND):
            parts.append("BTC อยู่ในแนวโน้มขาลง (Bearish Bias) หลีกเลี่ยงการเปิด Long สวนเทรนด์ใหญ่ ให้น้ำหนักฝั่ง SELL")
            if funding_bias == "SHORT_CROWDED":
                parts.append("ทั้งนี้ฝั่ง Short ค่อนข้างแออัด ระวัง Short Squeeze ดีดสั้น")
        elif regime == MarketRegime.RANGING:
            parts.append("BTC เคลื่อนไหวในกรอบสะสม (Ranging) เหมาะกับการเล่น Reversal ที่ขอบกรอบ SMC (OB/FVG)")
        elif regime == MarketRegime.CHOPPY:
            parts.append("BTC ตลาดไซด์เวย์ไร้ทิศทาง (Choppy) ควรลดความเสี่ยงหรือรอเบรกกรอบชัดเจน")
        else:
            parts.append("ความผันผวนสูงผิดปกติ ควรระมัดระวังเป็นพิเศษ")

        return " ".join(parts)
