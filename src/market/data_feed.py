"""Market data feed — fetches and caches OHLCV data across timeframes."""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime
from typing import Optional

from src.core.config import settings
from src.core.events import EventType, event_bus
from src.core.types import Candle, Tick
from src.market.mt5_connection import MT5Connection

logger = logging.getLogger(__name__)


class DataFeed:
    """
    Manages market data acquisition from MT5.

    Responsibilities:
    - Fetch OHLCV across multiple timeframes
    - Cache recent candles in memory
    - Publish NEW_CANDLE events
    - Track current price via ticks
    """

    def __init__(self, mt5: MT5Connection) -> None:
        self._mt5 = mt5
        self._cache: dict[str, dict[str, list[Candle]]] = {}  # symbol -> tf -> candles
        self._running = False
        self._poll_interval = 5  # seconds between polls

    async def initialize(self, symbol: str) -> None:
        """Load initial candle data for a symbol across all timeframes."""
        timeframes = settings.data.timeframes.get("structure", ["H4", "H1", "M15", "M5"])
        count = settings.data.candle_count

        self._cache.setdefault(symbol, {})

        for tf in timeframes:
            candles = await self._mt5.get_ohlcv(symbol, tf, count)
            self._cache[symbol][tf] = candles
            logger.info(f"Loaded {len(candles)} candles for {symbol} {tf}")

    async def start_polling(self, symbol: str) -> None:
        """Start polling for new candles. Runs until stopped."""
        self._running = True
        logger.info(f"Data feed polling started for {symbol}")

        while self._running:
            try:
                await self._update_candles(symbol)
                await asyncio.sleep(self._poll_interval)
            except Exception as e:
                logger.error(f"Data feed error: {e}")
                await asyncio.sleep(10)  # Back off on error

    async def stop_polling(self) -> None:
        """Stop polling."""
        self._running = False
        logger.info("Data feed polling stopped")

    async def _update_candles(self, symbol: str) -> None:
        """Fetch latest candle for each timeframe and publish events."""
        timeframes = settings.data.timeframes.get("structure", ["H4", "H1", "M15", "M5"])

        for tf in timeframes:
            candles = await self._mt5.get_ohlcv(symbol, tf, count=3)

            if not candles:
                continue

            latest = candles[-1]
            cached = self._cache.get(symbol, {}).get(tf, [])

            # Check if we have a new candle (different timestamp from last cached)
            if cached and cached[-1].timestamp == latest.timestamp:
                # Same candle — update close/volume
                cached[-1] = latest
            elif cached:
                # New candle!
                cached.append(latest)
                # Keep cache bounded
                if len(cached) > settings.data.candle_count:
                    cached.pop(0)

                await event_bus.publish(EventType.NEW_CANDLE, {
                    "symbol": symbol,
                    "timeframe": tf,
                    "candle": latest,
                })
                logger.debug(f"New {tf} candle for {symbol}: {latest.close:.2f}")
            else:
                # First candle
                self._cache.setdefault(symbol, {})[tf] = [latest]

    def get_candles(
        self, symbol: str, timeframe: str, count: Optional[int] = None
    ) -> list[Candle]:
        """Get cached candles for a symbol/timeframe."""
        candles = self._cache.get(symbol, {}).get(timeframe, [])
        if count:
            return candles[-count:]
        return candles

    def get_latest_candle(self, symbol: str, timeframe: str) -> Optional[Candle]:
        """Get the most recent cached candle."""
        candles = self._cache.get(symbol, {}).get(timeframe, [])
        return candles[-1] if candles else None

    def get_current_tick(self) -> Optional[Tick]:
        """Synchronous tick getter (for risk engine etc.)."""
        return self._current_tick

    @property
    def _current_tick(self) -> Optional[Tick]:
        """Internal tick cache — updated by tick streaming."""
        # In Phase 2+, this will be updated by tick streaming
        return None
