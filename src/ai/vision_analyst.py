"""AI Vision Confirmation & Candlestick Image Analysis.

Provides visual candle confirmation for AI Council setup evaluations:
1. Candlestick Chart Renderer:
   - Generates high-definition dark-mode candlestick images (TradingView style)
   - Overlays Entry, Stop Loss, and Take Profit levels
   - Encodes as PNG bytes, Base64, or saves to disk
2. Visual Pattern Engine:
   - Evaluates Rejection Wicks (pinbars, liquidity sweeps)
   - Evaluates Institutional Displacement (momentum candle sizing)
   - Detects exhaustion traps and false breakouts
   - Outputs VisionVerdict with 0-100 score and narrative
"""

from __future__ import annotations

import base64
import io
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw

from src.core.types import Candle, Direction

logger = logging.getLogger(__name__)


@dataclass
class VisionVerdict:
    """Outcome of visual candlestick chart analysis."""

    verdict: str                  # "APPROVE", "CAUTION", "REJECT"
    vision_score: int             # 0 to 100
    rejection_wick: bool          # Long rejection wick present
    displacement: bool            # Strong institutional displacement body
    trap_risk: bool               # Exhaustion or false breakout trap warning
    confluences: list[str] = field(default_factory=list)
    risks: list[str] = field(default_factory=list)
    summary_th: str = ""
    chart_image_path: str | None = None


class AIVisionAnalyst:
    """Generates charts and analyzes visual candlestick price action."""

    def __init__(self, output_dir: str = "data/charts") -> None:
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def render_candlestick_chart(
        self,
        candles: list[Candle],
        entry_price: float,
        sl: float,
        tp: float,
        symbol: str = "BTCUSDT",
        timeframe: str = "M5",
        width: int = 800,
        height: int = 450,
    ) -> Image.Image:
        """Render a high-contrast dark-mode candlestick chart using Pillow."""
        if not candles:
            # Fallback blank image
            img = Image.new("RGB", (width, height), color="#131722")
            return img

        # Determine price boundaries
        prices = [c.high for c in candles] + [c.low for c in candles] + [entry_price, sl, tp]
        min_price = min(prices)
        max_price = max(prices)
        price_range = max_price - min_price
        if price_range <= 0:
            price_range = 1.0

        # Margin and plot area
        margin_left = 60
        margin_right = 100
        margin_top = 40
        margin_bottom = 40
        plot_w = width - margin_left - margin_right
        plot_h = height - margin_top - margin_bottom

        img = Image.new("RGB", (width, height), color="#131722")
        draw = ImageDraw.Draw(img)

        # Draw grid lines
        grid_lines = 5
        for i in range(grid_lines + 1):
            y = int(margin_top + i * (plot_h / grid_lines))
            p_val = max_price - (i / grid_lines) * price_range
            draw.line([(margin_left, y), (width - margin_right, y)], fill="#20242e", width=1)
            # Price label
            draw.text((width - margin_right + 8, y - 6), f"{p_val:,.1f}", fill="#787b86")

        # Function to map price to Y coordinate
        def to_y(price: float) -> int:
            normalized = (max_price - price) / price_range
            return int(margin_top + normalized * plot_h)

        # Plot candles
        num_candles = len(candles)
        candle_pitch = plot_w / max(1, num_candles)
        candle_w = max(2, int(candle_pitch * 0.7))

        color_bull = "#089981"
        color_bear = "#f23645"

        for idx, c in enumerate(candles):
            center_x = int(margin_left + idx * candle_pitch + candle_pitch / 2)
            left_x = center_x - candle_w // 2
            right_x = left_x + candle_w

            is_bull = c.close >= c.open
            color = color_bull if is_bull else color_bear

            high_y = to_y(c.high)
            low_y = to_y(c.low)
            open_y = to_y(c.open)
            close_y = to_y(c.close)

            # Draw wicks
            draw.line([(center_x, high_y), (center_x, low_y)], fill=color, width=1)

            # Draw body
            top_y = min(open_y, close_y)
            bot_y = max(open_y, close_y)
            if bot_y == top_y:
                bot_y += 1
            draw.rectangle([(left_x, top_y), (right_x, bot_y)], fill=color, outline=color)

        # Overlay Entry, SL, TP reference lines
        y_entry = to_y(entry_price)
        y_sl = to_y(sl)
        y_tp = to_y(tp)

        # Entry Line (Blue)
        draw.line([(margin_left, y_entry), (width - margin_right, y_entry)], fill="#2962ff", width=2)
        draw.text((margin_left + 10, y_entry - 14), f"ENTRY ${entry_price:,.2f}", fill="#2962ff")

        # SL Line (Red)
        draw.line([(margin_left, y_sl), (width - margin_right, y_sl)], fill="#f23645", width=2)
        draw.text((margin_left + 10, y_sl - 14), f"SL ${sl:,.2f}", fill="#f23645")

        # TP Line (Green)
        draw.line([(margin_left, y_tp), (width - margin_right, y_tp)], fill="#089981", width=2)
        draw.text((margin_left + 10, y_tp - 14), f"TP ${tp:,.2f}", fill="#089981")

        # Header Title
        draw.text((margin_left, 12), f"MT5AI VISION • {symbol} • {timeframe}", fill="#d1d4dc")

        return img

    def save_chart_image(
        self,
        img: Image.Image,
        symbol: str,
        timestamp_str: str | None = None,
    ) -> str:
        """Save rendered chart to data/charts and return file path."""
        ts = timestamp_str or datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        filepath = self.output_dir / f"{symbol}_{ts}.png"
        img.save(filepath, format="PNG")
        return str(filepath)

    def chart_to_base64(self, img: Image.Image) -> str:
        """Convert chart to Base64 data string."""
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        return base64.b64encode(buf.getvalue()).decode("utf-8")

    def analyze_candlestick_setup(
        self,
        candles: list[Candle],
        direction: Direction,
        entry_price: float,
        sl: float,
        tp: float,
        symbol: str = "BTCUSDT",
        timeframe: str = "M5",
    ) -> VisionVerdict:
        """
        Analyze candlestick shape, rejection wicks, and displacement bodies.
        Produces deterministic visual confirmation score and verdict.
        """
        if not candles or len(candles) < 5:
            return VisionVerdict(
                verdict="CAUTION",
                vision_score=50,
                rejection_wick=False,
                displacement=False,
                trap_risk=False,
                summary_th="ข้อมูลแท่งเทียนไม่เพียงพอสำหรับการวิเคราะห์เชิงสายตา",
            )

        # Trigger candle (latest closed candle)
        trigger = candles[-1]
        prior_candles = candles[-6:-1]

        # Calculate average body size of prior candles
        avg_body = sum(abs(c.close - c.open) for c in prior_candles) / len(prior_candles)
        if avg_body <= 0:
            avg_body = 0.0001

        candle_range = trigger.high - trigger.low
        if candle_range <= 0:
            candle_range = 0.0001

        body_size = abs(trigger.close - trigger.open)
        upper_wick = trigger.high - max(trigger.open, trigger.close)
        lower_wick = min(trigger.open, trigger.close) - trigger.low

        score = 60  # Base neutral score
        confluences: list[str] = []
        risks: list[str] = []

        rejection_detected = False
        displacement_detected = False
        trap_detected = False

        if direction == Direction.BUY:
            # 1. Rejection Wick from bottom (Lower wick >= 40% of candle range)
            if lower_wick / candle_range >= 0.40:
                rejection_detected = True
                score += 20
                confluences.append(f"มีไส้เทียนปฏิเสธราคาด้านล่างชัดเจน ({lower_wick / candle_range * 100:.0f}% ของแท่ง)")

            # 2. Bullish Displacement body (Body >= 1.5x average body and closed green)
            if trigger.close > trigger.open and body_size >= 1.5 * avg_body:
                displacement_detected = True
                score += 15
                confluences.append("แท่งเทียนโมเมนตัมกลืนกินขาขึ้น (Bullish Displacement)")

            # 3. Exhaustion Trap (Upper wick >= 45% on a Buy signal is dangerous)
            if upper_wick / candle_range >= 0.45:
                trap_detected = True
                score -= 25
                risks.append("ระวังกับดักไส้เทียนบน: มีแรงขายสวนกลับลงมาอย่างมีนัยสำคัญ")

            # 4. Bearish close check
            if trigger.close < trigger.open and not rejection_detected:
                score -= 15
                risks.append("แท่งปิดเป็นแท่งแดง ขัดแย้งกับสัญญาณ Buy")

        else:  # Direction.SELL
            # 1. Rejection Wick from top (Upper wick >= 40% of candle range)
            if upper_wick / candle_range >= 0.40:
                rejection_detected = True
                score += 20
                confluences.append(f"มีไส้เทียนปฏิเสธราคาด้านบนชัดเจน ({upper_wick / candle_range * 100:.0f}% ของแท่ง)")

            # 2. Bearish Displacement body
            if trigger.close < trigger.open and body_size >= 1.5 * avg_body:
                displacement_detected = True
                score += 15
                confluences.append("แท่งเทียนโมเมนตัมทุบลงชัดเจน (Bearish Displacement)")

            # 3. Exhaustion Trap (Lower wick >= 45% on a Sell signal)
            if lower_wick / candle_range >= 0.45:
                trap_detected = True
                score -= 25
                risks.append("ระวังกับดักไส้เทียนล่าง: มีแรงซื้อเด้งสวนขึ้นมาจากแนวรับ")

            # 4. Bullish close check
            if trigger.close > trigger.open and not rejection_detected:
                score -= 15
                risks.append("แท่งปิดเป็นแท่งเขียว ขัดแย้งกับสัญญาณ Sell")

        score = max(10, min(95, score))

        if score >= 70:
            verdict = "APPROVE"
            summary_th = "ทรงแท่งเทียนสวยงาม มีการปฏิเสธราคาหรือมีโมเมนตัมหนุนชัดเจน"
        elif score >= 50:
            verdict = "CAUTION"
            summary_th = "ทรงแท่งเทียนอยู่ในระดับปานกลาง ควรใช้ความระมัดระวัง"
        else:
            verdict = "REJECT"
            summary_th = "ทรงแท่งเทียนมีความขัดแย้ง หรือติดกับดักแรงสวน (Rejection Trap)"

        # Render and save chart image for audit
        img = self.render_candlestick_chart(
            candles=candles[-40:],
            entry_price=entry_price,
            sl=sl,
            tp=tp,
            symbol=symbol,
            timeframe=timeframe,
        )
        img_path = self.save_chart_image(img, symbol)

        return VisionVerdict(
            verdict=verdict,
            vision_score=score,
            rejection_wick=rejection_detected,
            displacement=displacement_detected,
            trap_risk=trap_detected,
            confluences=confluences,
            risks=risks,
            summary_th=summary_th,
            chart_image_path=img_path,
        )
