"""Read-only Binance USDT-M Futures gateway.

The first Binance slice intentionally implements public market data only.
Order methods fail closed until paper execution, testnet signing, and restart
reconciliation have been implemented and tested.
"""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import logging
import re
import time
import zlib
from collections.abc import AsyncIterator
from datetime import datetime, timezone
from typing import Any

import httpx

from src.core.config import settings
from src.core.exceptions import FreebuffError
from src.core.types import AccountInfo, Candle, Deal, Direction, OrderRequest, OrderResult, OrderStatus, Position, Tick

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
        self._server_time_offset_ms = 0
        self._position_symbols: dict[int, str] = {}
        self._submitted_orders: dict[str, OrderResult] = {}

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
            try:
                await self.sync_server_time()
            except Exception as exc:
                # Public market data remains usable if the optional clock
                # endpoint is temporarily unavailable; signed calls retry it.
                logger.warning("Binance server-time sync unavailable: %s", exc)
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

    async def sync_server_time(self) -> int:
        """Refresh local/server clock offset required for signed requests."""
        client = self._ensure_connected()
        response = await client.get("/fapi/v1/time")
        response.raise_for_status()
        server_time = int(response.json()["serverTime"])
        self._server_time_offset_ms = server_time - int(time.time() * 1000)
        return self._server_time_offset_ms

    def _signed_params(self, params: dict[str, Any]) -> dict[str, Any]:
        if not settings.binance_api_key or not settings.binance_api_secret:
            raise BinanceConnectionError("Binance API credentials are not configured")
        signed = {
            **params,
            "timestamp": int(time.time() * 1000) + self._server_time_offset_ms,
            "recvWindow": 5000,
        }
        query = str(httpx.QueryParams(signed))
        signed["signature"] = hmac.new(
            settings.binance_api_secret.encode(), query.encode(), hashlib.sha256
        ).hexdigest()
        return signed

    async def _signed_request(self, method: str, path: str, params: dict[str, Any]) -> dict[str, Any]:
        client = self._ensure_connected()
        response = await client.request(
            method, path, params=self._signed_params(params),
            headers={"X-MBX-APIKEY": settings.binance_api_key},
        )
        response.raise_for_status()
        return response.json()

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

    async def stream_klines(self, symbol: str, timeframe: str) -> AsyncIterator[tuple[str, Candle, bool]]:
        """Expose the reconnectable WebSocket stream through the venue gateway."""
        from src.market.binance_websocket import BinanceWebSocket

        websocket_base = (
            "wss://stream.binancefuture.com"
            if "testnet.binancefuture.com" in self._base_url
            else "wss://fstream.binance.com"
        )
        stream = BinanceWebSocket(websocket_base)
        async for event in stream.stream_klines(symbol, timeframe):
            yield event

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
        if settings.binance_mode != "testnet":
            raise BinanceConnectionError("Signed Binance account access is restricted to BINANCE_MODE=testnet")
        row = await self._signed_request("GET", "/fapi/v2/account", {})
        return AccountInfo(
            login=0, name="Binance Futures", server="binance-testnet",
            balance=float(row.get("totalWalletBalance", 0)),
            equity=float(row.get("totalMarginBalance", 0)),
            margin=float(row.get("totalInitialMargin", 0)),
            free_margin=float(row.get("availableBalance", 0)),
            profit=float(row.get("totalUnrealizedProfit", 0)),
            currency="USDT", leverage=0,
        )

    async def send_order(self, request: OrderRequest) -> OrderResult:
        if settings.binance_mode != "testnet":
            return OrderResult(success=False, venue=self.venue, error_message="Binance execution requires BINANCE_MODE=testnet")
        if not settings.binance_api_key or not settings.binance_api_secret:
            return OrderResult(success=False, venue=self.venue, error_message="Binance testnet credentials are not configured")
        if request.sl <= 0 or request.tp <= 0:
            return OrderResult(success=False, venue=self.venue, error_message="Server-side SL and TP are required")
        client_id = re.sub(r"[^A-Za-z0-9_-]", "-", request.execution_key or request.comment or "freebuff")[:28]
        if client_id in self._submitted_orders:
            previous = self._submitted_orders[client_id]
            return previous.model_copy(update={"metadata": {**previous.metadata, "duplicate": True}})
        side = "BUY" if request.direction == Direction.BUY else "SELL"
        filled = await self._signed_request("POST", "/fapi/v1/order", {
            "symbol": request.symbol.upper(), "side": side, "type": "MARKET",
            "quantity": request.volume, "newClientOrderId": client_id,
        })
        order_id = str(filled.get("orderId", ""))
        status = OrderStatus.PARTIAL if filled.get("status") == "PARTIALLY_FILLED" else OrderStatus.FILLED
        fill_price = float(filled.get("avgPrice") or filled.get("price") or 0) or None
        protective: dict[str, Any] = {}
        protective_error: str | None = None
        opposite = "SELL" if side == "BUY" else "BUY"
        for suffix, order_type, stop_price in (("sl", "STOP_MARKET", request.sl), ("tp", "TAKE_PROFIT_MARKET", request.tp)):
            try:
                protective[suffix] = await self._signed_request("POST", "/fapi/v1/order", {
                    "symbol": request.symbol.upper(), "side": opposite, "type": order_type,
                    "stopPrice": stop_price, "closePosition": "true",
                    "workingType": "MARK_PRICE", "newClientOrderId": f"{client_id}-{suffix}",
                })
            except Exception as exc:
                protective_error = f"Failed to place server-side {suffix.upper()}: {exc}"
                break
        result = OrderResult(
            success=protective_error is None, ticket=int(order_id) if order_id.isdigit() else None,
            price=fill_price, volume=float(filled.get("executedQty", request.volume)),
            venue=self.venue, external_order_id=order_id, status=status,
            error_message=protective_error, metadata={"primary": filled, "protective": protective},
        )
        self._submitted_orders[client_id] = result
        return result

    async def modify_position(self, ticket: int, sl: float | None = None, tp: float | None = None) -> OrderResult:
        return OrderResult(success=False, ticket=ticket, error_message="Binance execution is not enabled")

    async def close_position(self, ticket: int) -> OrderResult:
        return OrderResult(success=False, ticket=ticket, error_message="Binance execution is not enabled")

    async def get_positions(self, symbol: str | None = None) -> list[Position]:
        if settings.binance_mode != "testnet":
            raise BinanceConnectionError("Binance positions require BINANCE_MODE=testnet")
        params = {"symbol": symbol.upper()} if symbol else {}
        rows = await self._signed_request("GET", "/fapi/v2/positionRisk", params)
        positions: list[Position] = []
        for row in rows:
            amount = float(row.get("positionAmt", 0))
            if amount == 0:
                continue
            symbol_name = row["symbol"]
            synthetic_id = zlib.crc32(f"{symbol_name}:{row.get('positionSide', 'BOTH')}".encode())
            self._position_symbols[synthetic_id] = symbol_name
            direction = Direction.BUY if amount > 0 else Direction.SELL
            positions.append(Position(
                ticket=synthetic_id, identifier=synthetic_id, symbol=symbol_name,
                direction=direction, volume=abs(amount), open_price=float(row.get("entryPrice", 0)),
                current_price=float(row.get("markPrice", 0)),
                sl=float(row.get("liquidationPrice", 0) or 0),
                profit=float(row.get("unRealizedProfit", 0)),
                open_time=datetime.fromtimestamp(float(row.get("updateTime", 0)) / 1000, tz=timezone.utc),
                comment="binance-position-risk",
            ))
        return positions

    async def get_position_deals(self, position_id: int) -> list[Deal]:
        if settings.binance_mode != "testnet":
            raise BinanceConnectionError("Binance deal history requires BINANCE_MODE=testnet")
        symbol = self._position_symbols.get(position_id)
        if not symbol:
            raise BinanceConnectionError(f"Unknown Binance position id: {position_id}")
        rows = await self._signed_request("GET", "/fapi/v1/userTrades", {"symbol": symbol, "limit": 1000})
        deals: list[Deal] = []
        for index, row in enumerate(rows):
            qty = float(row.get("qty", 0))
            if qty <= 0:
                continue
            entry = 0 if index == 0 else 1
            trade_side = 0 if row.get("side") == "BUY" else 1
            deals.append(Deal(
                ticket=int(row["id"]), order=int(row["orderId"]), position_id=position_id,
                time=datetime.fromtimestamp(int(row["time"]) / 1000, tz=timezone.utc),
                entry=entry, type=trade_side, volume=qty, price=float(row["price"]),
                profit=float(row.get("realizedPnl", 0)),
                commission=-abs(float(row.get("commission", 0))), symbol=symbol,
            ))
        return deals
