"""Unit tests for technical indicators and momentum filters."""

from datetime import datetime, timezone
import pytest

from src.core.types import Candle, Direction
from src.strategies.indicators import (
    calculate_rsi,
    calculate_volume_ratio,
    calculate_volume_sma,
    check_momentum_confirmation,
    is_volume_spike,
)


def _make_candles(prices: list[float], volumes: list[float] | None = None) -> list[Candle]:
    candles = []
    for i, p in enumerate(prices):
        vol = volumes[i] if volumes and i < len(volumes) else 100.0
        c = Candle(
            timestamp=datetime.now(timezone.utc),
            open=p - 1.0,
            high=p + 2.0,
            low=p - 2.0,
            close=p,
            volume=vol,
        )
        candles.append(c)
    return candles


def test_calculate_rsi_insufficient_data():
    candles = _make_candles([100.0, 101.0, 102.0])
    rsi = calculate_rsi(candles, period=14)
    assert rsi == 50.0


def test_calculate_rsi_uptrend():
    # Steadily rising prices
    prices = [100.0 + i * 2.0 for i in range(25)]
    candles = _make_candles(prices)
    rsi = calculate_rsi(candles, period=14)
    assert rsi > 70.0


def test_calculate_rsi_downtrend():
    # Steadily falling prices
    prices = [200.0 - i * 2.0 for i in range(25)]
    candles = _make_candles(prices)
    rsi = calculate_rsi(candles, period=14)
    assert rsi < 30.0


def test_volume_calculations_and_spike():
    vols = [100.0] * 19 + [250.0]
    candles = _make_candles([100.0] * 20, vols)
    sma = calculate_volume_sma(candles[:-1], period=20)
    assert sma == 100.0

    ratio = calculate_volume_ratio(candles, period=20)
    assert ratio >= 2.4
    assert is_volume_spike(candles, threshold=1.5, period=20) is True


def test_check_momentum_confirmation_buy_overbought():
    # Sharp uptrend makes RSI overbought
    prices = [100.0 + i * 5.0 for i in range(25)]
    candles = _make_candles(prices)
    confirmed, rsi, vol_ratio, explanation = check_momentum_confirmation(candles, Direction.BUY)
    assert confirmed is False
    assert "Overbought" in explanation


def test_check_momentum_confirmation_sell_oversold():
    # Sharp downtrend makes RSI oversold
    prices = [200.0 - i * 5.0 for i in range(25)]
    candles = _make_candles(prices)
    confirmed, rsi, vol_ratio, explanation = check_momentum_confirmation(candles, Direction.SELL)
    assert confirmed is False
    assert "Oversold" in explanation
