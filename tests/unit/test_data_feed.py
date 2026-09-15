from datetime import datetime

import pytest

from src.core.config import DataConfig, settings
from src.core.events import EventType, event_bus
from src.core.types import Candle
from src.market.data_feed import DataFeed


class FakeBinanceGateway:
    venue = "binance"

    async def get_ohlcv(self, symbol, timeframe, count=500, start=None):
        return [
            Candle(timestamp=datetime(2026, 9, 15, 0, 0), open=99, high=101, low=98, close=100, volume=1),
            Candle(timestamp=datetime(2026, 9, 15, 0, 5), open=100, high=102, low=99, close=101, volume=2),
        ]


@pytest.mark.asyncio
async def test_rest_polling_publishes_selected_venue(monkeypatch):
    monkeypatch.setattr(settings, "data", DataConfig(timeframes={"structure": ["M5"]}, candle_count=10))
    feed = DataFeed(FakeBinanceGateway())
    feed._cache = {"BTCUSDT": {"M5": [
        Candle(timestamp=datetime(2026, 9, 14, 23, 55), open=98, high=99, low=97, close=98, volume=1),
    ]}}
    received = []

    async def handler(data):
        received.append(data)

    event_bus.subscribe(EventType.NEW_CANDLE, handler)
    try:
        await feed._update_candles("BTCUSDT")
    finally:
        event_bus.unsubscribe(EventType.NEW_CANDLE, handler)
    assert received[-1]["venue"] == "binance"
    assert received[-1]["symbol"] == "BTCUSDT"
