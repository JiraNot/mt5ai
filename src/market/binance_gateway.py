"""Read-only Binance USDT-M Futures gateway.

The first Binance slice intentionally implements public market data only.
Order methods fail closed until paper execution, testnet signing, and restart
reconciliation have been implemented and tested.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import Any

import httpx

from src.core.config import settings
from src.core.exceptions import FreebuffError
from src.core.types import AccountInfo, Candle, Deal, OrderRequest, OrderResult, Position, Tick

logger = logging.getLogger(__name__)

_INTERVALS = {"M1": "1m", "M5": "5m", "M15": "15m", "H1": "1h", "H4": "4h", "D1": "1d"}


class BinanceConnectionError(FreebuffError):
    """Binance REST connection or response failure."""


class BinanceGateway:
    """Binance USDⓈ-M Futures public REST adapter."""

    venue = "binance"

    def __init__(
        self,
        base_url: str | None = None,
        transport: httpx.AsyncBaseTransport | None = None,
        timeout: float | None = None,
    ) -> None:
        self._base_url = (base_url or settings.binance_base_url).rstrip("/")
        self._transport = transport
        self._timeout = timeout or settings.binance_timeout
        self._client: httpx.AsyncClient | None = None
        self._connected = False

    @property
    def connected(self) -> bool:
        return self._connected

    async def connect(self) -> bool:
        if self._client is None:
            self._client = httpx.AsyncClient(
                base_url=self._base_url,
                timeout=self._timeout,
                transport=self._transport,
                headers={"User-Agent": "freebuff-binance-gateway/0.1"},
            )
        try:
            response = await self._client.get("/fapi/v1/ping")
            response.raise_for_status()
            self._connected = True
            logger.info("Binance connected: %s (%s)", self._base_url, settings.binance_mode)
            return True
        except Exception as exc:
            self._connected = False
            logger.warning("Binance connection failed: %s", exc)
            return False

    async def disconnect(self) -> None:
        if self._client:
            await self._client.aclose()
            self._client = None
        self._connected = False

    async def reconnect(self) -> bool:
        await self.disconnect()
        await asyncio.sleep(0)
        return await self.connect()

    def _ensure_connected(self) -> httpx.AsyncClient:
        if not self._connected or self._client is None:
            raise BinanceConnectionError("Not connected to Binance")
        return self._client

    async def get_ohlcv(
        self, symbol: str, timeframe: str, count: int = 500, start: datetime | None = None
    ) -> list[Candle]:
        if timeframe not in _INTERVALS:
            raise ValueError(f"Unsupported timeframe: {timeframe}")
        client = self._ensure_connected()
        params: dict[str, Any] = {
            "symbol": symbol.upper(), "interval": _INTERVALS[timeframe],
            "limit": min(max(count, 1), 1500),
        }
        if start is not None:
            params["startTime"] = int(start.timestamp() * 1000)
        response = await client.get("/fapi/v1/klines", params=params)
        response.raise_for_status()
        return [
            Candle(
                timestamp=datetime.fromtimestamp(row[0] / 1000, tz=timezone.utc),
                open=float(row[1]), high=float(row[2]), low=float(row[3]),
                close=float(row[4]), volume=float(row[5]),
            )
            for row in response.json()
        ]

    async def get_current_price(self, symbol: str) -> Tick:
        client = self._ensure_connected()
        response = await client.get("/fapi/v1/ticker/bookTicker", params={"symbol": symbol.upper()})
        response.raise_for_status()
        row = response.json()
        bid, ask = float(row["bidPrice"]), float(row["askPrice"])
        return Tick(timestamp=datetime.now(timezone.utc), bid=bid, ask=ask, last=(bid + ask) / 2)

    async def get_symbol_info(self, symbol: str) -> dict[str, Any]:
        client = self._ensure_connected()
        response = await client.get("/fapi/v1/exchangeInfo")
        response.raise_for_status()
        for item in response.json().get("symbols", []):
            if item.get("symbol") == symbol.upper():
                filters = {item["filterType"]: item for item in item.get("filters", [])}
                lot = filters.get("LOT_SIZE", {})
                price = filters.get("PRICE_FILTER", {})
                return {
                    "symbol": item["symbol"], "status": item.get("status"),
                    "base_asset": item.get("baseAsset"), "quote_asset": item.get("quoteAsset"),
                    "contract_type": item.get("contractType"),
                    "price_tick_size": float(price.get("tickSize", 0)),
                    "volume_min": float(lot.get("minQty", 0)),
                    "volume_max": float(lot.get("maxQty", 0)),
                    "volume_step": float(lot.get("stepSize", 0)),
                }
        raise BinanceConnectionError(f"Symbol not found: {symbol}")

    async def get_account_info(self) -> AccountInfo:
        raise BinanceConnectionError("Binance account endpoint is not enabled in the read-only phase")

    async def send_order(self, request: OrderRequest) -> OrderResult:
        return OrderResult(success=False, error_message="Binance order execution is disabled; use PAPER first")

    async def modify_position(self, ticket: int, sl: float | None = None, tp: float | None = None) -> OrderResult:
        return OrderResult(success=False, ticket=ticket, error_message="Binance execution is not enabled")

    async def close_position(self, ticket: int) -> OrderResult:
        return OrderResult(success=False, ticket=ticket, error_message="Binance execution is not enabled")

    async def get_positions(self, symbol: str | None = None) -> list[Position]:
        raise BinanceConnectionError("Binance position endpoint is not enabled in the read-only phase")

    async def get_position_deals(self, position_id: int) -> list[Deal]:
        raise BinanceConnectionError("Binance deal history is not enabled in the read-only phase")
