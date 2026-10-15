"""Unit tests for AIVisionAnalyst (Candlestick chart rendering & visual pattern detection)."""

import pytest
from datetime import datetime, timezone, timedelta
from pathlib import Path

from src.core.types import Candle, Direction
from src.ai.vision_analyst import AIVisionAnalyst, VisionVerdict


def _make_candles(count: int = 10, base_price: float = 60000.0) -> list[Candle]:
    """Helper to generate sequential candles."""
    now = datetime.now(timezone.utc)
    candles = []
    for i in range(count):
        t = now - timedelta(minutes=5 * (count - i))
        p = base_price + i * 10
        candles.append(
            Candle(
                timestamp=t,
                open=p,
                high=p + 15,
                low=p - 15,
                close=p + 5,
                volume=100.0,
            )
        )
    return candles


def test_render_candlestick_chart(tmp_path):
    """Test candlestick chart generation and image saving."""
    analyst = AIVisionAnalyst(output_dir=str(tmp_path))
    candles = _make_candles(20, base_price=65000.0)

    img = analyst.render_candlestick_chart(
        candles=candles,
        entry_price=65100.0,
        sl=64800.0,
        tp=65600.0,
        symbol="BTCUSDT",
        timeframe="M5",
    )
    assert img.size == (800, 450)

    # Convert to base64
    b64 = analyst.chart_to_base64(img)
    assert len(b64) > 100

    # Save to disk
    filepath = analyst.save_chart_image(img, "BTCUSDT")
    assert Path(filepath).exists()


def test_analyze_rejection_wick_buy(tmp_path):
    """Test lower rejection wick detection for BUY setup."""
    analyst = AIVisionAnalyst(output_dir=str(tmp_path))
    candles = _make_candles(10, base_price=65000.0)

    # Append pinbar with long lower wick (sweep of lows)
    # Range = 65100 - 64900 = 200. Open=65050, Close=65080, Low=64900 -> Lower wick = 65050-64900 = 150 (75% of range)
    pinbar = Candle(
        timestamp=datetime.now(timezone.utc),
        open=65050.0,
        high=65100.0,
        low=64900.0,
        close=65080.0,
        volume=250.0,
    )
    candles.append(pinbar)

    verdict = analyst.analyze_candlestick_setup(
        candles=candles,
        direction=Direction.BUY,
        entry_price=65080.0,
        sl=64890.0,
        tp=65400.0,
    )

    assert verdict.rejection_wick is True
    assert verdict.vision_score >= 70
    assert verdict.verdict == "APPROVE"
    assert any("ไส้เทียนปฏิเสธราคา" in c for c in verdict.confluences)


def test_analyze_displacement_candle(tmp_path):
    """Test displacement candle detection (large momentum body)."""
    analyst = AIVisionAnalyst(output_dir=str(tmp_path))
    # Small candles average body = 5.0
    candles = _make_candles(10, base_price=65000.0)

    # Large displacement candle: open=65100, close=65300 (body=200 >> 5.0)
    displacement = Candle(
        timestamp=datetime.now(timezone.utc),
        open=65100.0,
        high=65320.0,
        low=65090.0,
        close=65300.0,
        volume=500.0,
    )
    candles.append(displacement)

    verdict = analyst.analyze_candlestick_setup(
        candles=candles,
        direction=Direction.BUY,
        entry_price=65300.0,
        sl=65050.0,
        tp=65800.0,
    )

    assert verdict.displacement is True
    assert verdict.vision_score >= 70
    assert verdict.verdict == "APPROVE"


def test_analyze_exhaustion_trap(tmp_path):
    """Test exhaustion trap warning when candle has heavy opposing rejection."""
    analyst = AIVisionAnalyst(output_dir=str(tmp_path))
    candles = _make_candles(10, base_price=65000.0)

    # BUY setup, but candle spiked up and got dumped back down (huge upper wick)
    # Range = 65400 - 65000 = 400. Open=65010, Close=65050, High=65400 -> Upper wick = 65400-65050 = 350 (87.5% of range)
    trap_candle = Candle(
        timestamp=datetime.now(timezone.utc),
        open=65010.0,
        high=65400.0,
        low=65000.0,
        close=65050.0,
        volume=300.0,
    )
    candles.append(trap_candle)

    verdict = analyst.analyze_candlestick_setup(
        candles=candles,
        direction=Direction.BUY,
        entry_price=65050.0,
        sl=64950.0,
        tp=65400.0,
    )

    assert verdict.trap_risk is True
    assert any("กับดักไส้เทียน" in r for r in verdict.risks)
    assert verdict.vision_score < 70
