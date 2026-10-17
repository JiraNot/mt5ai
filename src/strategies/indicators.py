"""Technical indicators and momentum filters for SMC strategies.

Provides deterministic mathematical calculations for:
- Relative Strength Index (RSI - Wilder's smoothing)
- Volume Moving Average (SMA) and Volume Spike detection
- Momentum & Institutional Volume confirmation filters
"""

from __future__ import annotations

import logging
from typing import Sequence

import numpy as np

from src.core.types import Candle, Direction

logger = logging.getLogger(__name__)


def calculate_rsi(candles: Sequence[Candle], period: int = 14) -> float:
    """Calculate Relative Strength Index (RSI) using Wilder's smoothed method.

    Returns a float between 0.0 and 100.0.
    Returns 50.0 if there is insufficient candle data.
    """
    if len(candles) < period + 1:
        return 50.0

    closes = np.array([c.close for c in candles], dtype=float)
    deltas = np.diff(closes)

    gains = np.where(deltas > 0, deltas, 0.0)
    losses = np.where(deltas < 0, -deltas, 0.0)

    # Initial average
    avg_gain = np.mean(gains[:period])
    avg_loss = np.mean(losses[:period])

    # Wilder's smoothing
    for i in range(period, len(deltas)):
        avg_gain = (avg_gain * (period - 1) + gains[i]) / period
        avg_loss = (avg_loss * (period - 1) + losses[i]) / period

    if avg_loss == 0.0:
        return 100.0 if avg_gain > 0 else 50.0

    rs = avg_gain / avg_loss
    rsi = 100.0 - (100.0 / (1.0 + rs))
    return float(np.clip(rsi, 0.0, 100.0))


def calculate_volume_sma(candles: Sequence[Candle], period: int = 20) -> float:
    """Calculate Simple Moving Average of candle volume."""
    if not candles:
        return 1.0
    count = min(len(candles), period)
    vols = [c.volume for c in candles[-count:]]
    avg = sum(vols) / len(vols) if vols else 1.0
    return max(avg, 0.0001)


def calculate_volume_ratio(candles: Sequence[Candle], period: int = 20) -> float:
    """Calculate ratio of the latest closed candle volume against its historical average."""
    if not candles:
        return 1.0
    current_vol = candles[-1].volume
    prior_candles = candles[:-1] if len(candles) > 1 else candles
    avg_vol = calculate_volume_sma(prior_candles, period=period)
    return float(round(current_vol / avg_vol, 2))


def is_volume_spike(candles: Sequence[Candle], threshold: float = 1.3, period: int = 20) -> bool:
    """Determine if the latest candle exhibits institutional volume expansion (spike)."""
    return calculate_volume_ratio(candles, period=period) >= threshold


def check_momentum_confirmation(
    candles: Sequence[Candle],
    direction: Direction,
    rsi_period: int = 14,
    min_volume_ratio: float = 1.15,
) -> tuple[bool, float, float, str]:
    """Evaluate RSI momentum and volume confirmation for a trade candidate.

    Returns:
        (is_confirmed, rsi, volume_ratio, explanation_th)
    """
    if len(candles) < rsi_period + 2:
        return True, 50.0, 1.0, "ข้อมูลแท่งเทียนเริ่มต้น ไม่ขัดแย้งกับสัญญาณ"

    rsi = calculate_rsi(candles, period=rsi_period)
    vol_ratio = calculate_volume_ratio(candles, period=20)

    if direction == Direction.BUY:
        # Overbought filter: Avoid buying at extreme tops
        if rsi > 75.0:
            return False, rsi, vol_ratio, f"RSI Overbought ({rsi:.1f} > 75) เสี่ยงติดดอยที่แนวต้าน"
        
        # Bullish momentum check
        is_vol_confirmed = vol_ratio >= min_volume_ratio
        if 40.0 <= rsi <= 72.0:
            if is_vol_confirmed:
                return True, rsi, vol_ratio, f"โมเมนตัมขาขึ้นสมบูรณ์ (RSI {rsi:.1f}) พร้อม Volume ขยายตัว {vol_ratio:.1f}x"
            return True, rsi, vol_ratio, f"RSI ขาขึ้นอยู่ในโซนปลอดภัย ({rsi:.1f})"
        
        # Oversold bounce condition
        if rsi < 35.0 and is_vol_confirmed:
            return True, rsi, vol_ratio, f"RSI Oversold ({rsi:.1f}) เริ่มมีแรงซื้อสวนกลับ Volume {vol_ratio:.1f}x"

        return True, rsi, vol_ratio, f"RSI ปกติ ({rsi:.1f})"

    else:  # Direction.SELL
        # Oversold filter: Avoid selling at extreme bottoms
        if rsi < 25.0:
            return False, rsi, vol_ratio, f"RSI Oversold ({rsi:.1f} < 25) เสี่ยงติดกับดักแนวรับ"

        # Bearish momentum check
        is_vol_confirmed = vol_ratio >= min_volume_ratio
        if 28.0 <= rsi <= 60.0:
            if is_vol_confirmed:
                return True, rsi, vol_ratio, f"โมเมนตัมขาลงชัดเจน (RSI {rsi:.1f}) พร้อม Volume ทุบ {vol_ratio:.1f}x"
            return True, rsi, vol_ratio, f"RSI ขาลงอยู่ในโซนปลอดภัย ({rsi:.1f})"

        # Overbought exhaustion condition
        if rsi > 65.0 and is_vol_confirmed:
            return True, rsi, vol_ratio, f"RSI Overbought ({rsi:.1f}) เริ่มหมดแรง เกิดแรงเทขาย Volume {vol_ratio:.1f}x"

        return True, rsi, vol_ratio, f"RSI ปกติ ({rsi:.1f})"
