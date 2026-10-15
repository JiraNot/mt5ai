from datetime import datetime, timedelta, timezone

import pytest

from scripts import download_history
from src.core.types import Candle


@pytest.mark.asyncio
async def test_history_downloader_pages_binance_candles_without_duplicates(monkeypatch):
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    first = Candle(timestamp=start, open=1, high=2, low=1, close=2, volume=10)
    second = Candle(timestamp=start + timedelta(hours=1), open=2, high=3, low=2, close=3, volume=11)
    third = Candle(timestamp=start + timedelta(hours=2), open=3, high=4, low=3, close=4, volume=12)

    class Gateway:
        def __init__(self):
            self.starts = []

        async def get_ohlcv(self, symbol, timeframe, count, page_start):
            self.starts.append(page_start)
            assert (symbol, timeframe, count) == ("BTCUSDT", "H1", download_history.BATCH_SIZE)
            if len(self.starts) == 1:
                return [first, second]
            if len(self.starts) == 2:
                return [second, third]
            return []

    inserted_batches = []

    async def insert(session, candles, symbol, timeframe):
        inserted_batches.append(candles)
        return len(candles)

    monkeypatch.setattr(download_history, "insert_candles", insert)
    gateway = Gateway()

    count = await download_history.download_from_binance(
        gateway, object(), "BTCUSDT", "H1", start, start + timedelta(hours=3)
    )

    assert count == 3
    assert inserted_batches == [[first, second], [third]]
    assert gateway.starts == [start, second.timestamp + timedelta(milliseconds=1), third.timestamp + timedelta(milliseconds=1)]
