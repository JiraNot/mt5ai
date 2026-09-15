"""Binance Futures kline WebSocket stream with reconnect handling."""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import AsyncIterator
from datetime import datetime, timezone
from typing import Awaitable, Callable

from src.core.types import Candle

logger = logging.getLogger(__name__)


def parse_kline_event(payload: dict) -> tuple[str, Candle, bool]:
    """Convert a Binance kline event to a Candle and closed-bar flag."""
    data = payload.get("data", payload)
    kline = data["k"]
    candle = Candle(
        timestamp=datetime.fromtimestamp(kline["t"] / 1000, tz=timezone.utc),
        open=float(kline["o"]), high=float(kline["h"]), low=float(kline["l"]),
        close=float(kline["c"]), volume=float(kline["v"]),
    )
    return data["s"], candle, bool(kline["x"])


class BinanceWebSocket:
    """Reconnectable Binance Futures stream; emits only parsed venue data."""

    def __init__(
        self,
        base_url: str = "wss://fstream.binance.com",
        reconnect_delay: float = 2.0,
        time_sync: Callable[[], Awaitable[int]] | None = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._reconnect_delay = reconnect_delay
        self._time_sync = time_sync
        self.server_time_offset_ms = 0

    async def stream_klines(self, symbol: str, timeframe: str) -> AsyncIterator[tuple[str, Candle, bool]]:
        """Yield `(symbol, candle, is_closed)` and reconnect until cancelled."""
        try:
            import websockets
        except ImportError as exc:
            raise RuntimeError("websockets package is required for Binance streaming") from exc
        interval = {"M1": "1m", "M5": "5m", "M15": "15m", "H1": "1h", "H4": "4h", "D1": "1d"}.get(timeframe)
        if interval is None:
            raise ValueError(f"Unsupported timeframe: {timeframe}")
        url = f"{self._base_url}/ws/{symbol.lower()}@kline_{interval}"
        delay = self._reconnect_delay
        while True:
            try:
                if self._time_sync is not None:
                    try:
                        self.server_time_offset_ms = await self._time_sync()
                    except Exception as exc:
                        logger.warning("Binance WebSocket server-time sync unavailable: %s", exc)
                async with websockets.connect(url, ping_interval=20, ping_timeout=20) as socket:
                    delay = self._reconnect_delay
                    async for message in socket:
                        yield parse_kline_event(json.loads(message))
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                logger.warning("Binance WebSocket disconnected: %s; retrying in %.1fs", exc, delay)
                await asyncio.sleep(delay)
                delay = min(delay * 2, 60.0)
