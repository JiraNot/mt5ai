"""Binance USDT-M Futures gateway.

Public market data is available for all configured venues. Execution is paper
or Testnet-only and remains fail-closed for LIVE mode.
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
from decimal import Decimal, ROUND_DOWN, ROUND_UP
from typing import Any
from urllib.parse import urlparse

import httpx

from src.core.config import settings
from src.core.exceptions import FreebuffError
from src.core.runtime_control import get_runtime_trading_mode
from src.core.types import AccountInfo, Candle, Deal, Direction, OrderRequest, OrderResult, OrderStatus, Position, Tick, TradingMode

logger = logging.getLogger(__name__)

_INTERVALS = {"M1": "1m", "M5": "5m", "M15": "15m", "H1": "1h", "H4": "4h", "D1": "1d"}


class BinanceConnectionError(FreebuffError):
    """Binance REST connection or response failure."""


class BinanceGateway:
    """Binance USDⓈ-M Futures public REST adapter."""

    venue = "binance"

    @staticmethod
    def _runtime_is_paper() -> bool:
        """Treat missing runtime controls according to the safe configured PAPER default."""
        return get_runtime_trading_mode(settings.trading_mode) == "paper"

    def __init__(
        self,
        base_url: str | None = None,
        transport: httpx.AsyncBaseTransport | None = None,
        timeout: float | None = None,
        api_key: str | None = None,
        api_secret: str | None = None,
    ) -> None:
        self._configured_base_url = base_url.rstrip("/") if base_url else None
        self._base_url = (base_url or settings.binance_base_url).rstrip("/")
        self._transport = transport
        self._timeout = timeout or settings.binance_timeout
        # Optional per-instance credentials support a read-only credential
        # check without changing the process-wide trading configuration.
        self._api_key_override = api_key
        self._api_secret_override = api_secret
        self._client: httpx.AsyncClient | None = None
        self._connected = False
        self._server_time_offset_ms = 0
        self._position_symbols: dict[int, str] = {}
        self._position_protection: dict[int, dict[str, dict[str, Any]]] = {}
        self._submitted_orders: dict[str, OrderResult] = {}

    @property
    def connected(self) -> bool:
        return self._connected

    @property
    def websocket_base_url(self) -> str:
        """Return the official USDⓈ-M Futures WebSocket host for this venue."""
        effective_base = (self._configured_base_url or settings.binance_base_url).rstrip("/")
        return (
            "wss://fstream.binancefuture.com"
            if "testnet.binancefuture.com" in effective_base
            else "wss://fstream.binance.com"
        )

    def _uses_testnet_endpoint(self) -> bool:
        effective_base = (self._configured_base_url or settings.binance_base_url).rstrip("/")
        return urlparse(effective_base).hostname == "testnet.binancefuture.com"

    async def connect(self) -> bool:
        effective = (self._configured_base_url or settings.binance_base_url).rstrip("/")
        if self._client is None or str(self._client.base_url).rstrip("/") != effective:
            if self._client:
                await self._client.aclose()
            self._client = httpx.AsyncClient(
                base_url=effective,
                timeout=self._timeout,
                transport=self._transport,
                headers={"User-Agent": "freebuff-binance-gateway/0.1"},
            )
            self._base_url = effective
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
        api_secret = (
            self._api_secret_override
            if self._api_secret_override is not None
            else settings.binance_api_secret
        )
        if not api_secret:
            raise BinanceConnectionError("Binance API credentials are not configured")
        signed = {
            **params,
            "timestamp": int(time.time() * 1000) + self._server_time_offset_ms,
            "recvWindow": 5000,
        }
        query = str(httpx.QueryParams(signed))
        signed["signature"] = hmac.new(
            api_secret.encode(), query.encode(), hashlib.sha256
        ).hexdigest()
        return signed

    async def _signed_request(self, method: str, path: str, params: dict[str, Any]) -> dict[str, Any]:
        client = self._ensure_connected()
        api_key = (
            self._api_key_override
            if self._api_key_override is not None
            else settings.binance_api_key
        )
        if not api_key:
            raise BinanceConnectionError("Binance API credentials are not configured")
        response = await client.request(
            method, path, params=self._signed_params(params),
            headers={"X-MBX-APIKEY": api_key},
        )
        response.raise_for_status()
        return response.json()

    async def _find_existing_order(self, symbol: str, client_id: str) -> dict[str, Any] | None:
        """Find an exchange order by client id; only -2013 means "not found"."""
        try:
            return await self._signed_request("GET", "/fapi/v1/order", {
                "symbol": symbol.upper(), "origClientOrderId": client_id,
            })
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code == 400:
                try:
                    if int(exc.response.json().get("code", 0)) == -2013:
                        return None
                except (TypeError, ValueError):
                    pass
            raise

    async def _find_existing_algo_order(self, symbol: str, client_id: str) -> dict[str, Any] | None:
        """Find an existing conditional order by its idempotency key."""
        try:
            return await self._signed_request("GET", "/fapi/v1/algoOrder", {
                "symbol": symbol.upper(), "clientAlgoId": client_id,
            })
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code == 400:
                try:
                    if int(exc.response.json().get("code", 0)) in (-2011, -2013):
                        return None
                except (TypeError, ValueError):
                    pass
            raise

    async def _open_algo_orders(self, symbol: str | None = None) -> list[dict[str, Any]]:
        """List live conditional orders used to reconcile server-side protection."""
        params = {"symbol": symbol.upper()} if symbol else {}
        result = await self._signed_request("GET", "/fapi/v1/openAlgoOrders", params)
        return result if isinstance(result, list) else []

    async def _ensure_one_way_mode(self) -> None:
        """Fail closed when account hedge mode needs positionSide-aware routing."""
        result = await self._signed_request("GET", "/fapi/v1/positionSide/dual", {})
        if bool(result.get("dualSidePosition")):
            raise BinanceConnectionError(
                "Binance Futures Hedge Mode is not supported by this execution adapter; use One-way Mode"
            )

    async def _cancel_algo_order(self, order: dict[str, Any]) -> dict[str, Any]:
        """Cancel one conditional order using Binance's current algo-order API."""
        params: dict[str, Any] = {"symbol": str(order.get("symbol", "")).upper()}
        if order.get("algoId") is not None:
            params["algoId"] = order["algoId"]
        elif order.get("clientAlgoId"):
            params["clientAlgoId"] = order["clientAlgoId"]
        else:
            raise BinanceConnectionError("Cannot cancel Binance algo order without an id")
        return await self._signed_request("DELETE", "/fapi/v1/algoOrder", params)

    @staticmethod
    def _map_exchange_status(status: str) -> OrderStatus:
        return {
            "FILLED": OrderStatus.FILLED,
            "PARTIALLY_FILLED": OrderStatus.PARTIAL,
            "CANCELED": OrderStatus.CANCELLED,
            "REJECTED": OrderStatus.REJECTED,
            "EXPIRED": OrderStatus.EXPIRED,
        }.get(status, OrderStatus.PENDING)

    async def _place_protective_orders(
        self, symbol: str, side: str, client_id: str, sl: float, tp: float,
        lookup_existing: bool,
    ) -> tuple[dict[str, Any], str | None]:
        protective: dict[str, Any] = {}
        opposite = "SELL" if side == "BUY" else "BUY"
        for suffix, order_type, stop_price in (("sl", "STOP_MARKET", sl), ("tp", "TAKE_PROFIT_MARKET", tp)):
            protective_id = f"{client_id}-{suffix}"
            try:
                if lookup_existing:
                    existing = await self._find_existing_algo_order(symbol, protective_id)
                    if existing is not None and existing.get("algoStatus") in {"NEW", "TRIGGERED", "FINISHED"}:
                        protective[suffix] = existing
                        continue
                protective[suffix] = await self._signed_request("POST", "/fapi/v1/algoOrder", {
                    "algoType": "CONDITIONAL", "symbol": symbol.upper(),
                    "side": opposite, "type": order_type,
                    "triggerPrice": stop_price, "closePosition": "true",
                    "workingType": "MARK_PRICE", "clientAlgoId": protective_id,
                })
            except Exception as exc:
                return protective, f"Failed to place server-side {suffix.upper()}: {exc}"
        return protective, None

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
        # Use Binance-adjusted time so a local clock drift cannot make the
        # data feed evaluate a still-forming candle (or skip a closed one).
        now_ms = int(time.time() * 1000) + self._server_time_offset_ms
        return [
            Candle(
                timestamp=datetime.fromtimestamp(row[0] / 1000, tz=timezone.utc),
                open=float(row[1]), high=float(row[2]), low=float(row[3]),
                close=float(row[4]), volume=float(row[5]),
            )
            for row in response.json()
            # Binance includes the currently forming kline in REST results;
            # strategy evaluation must only see closed candles.
            if len(row) > 6 and int(row[6]) <= now_ms
        ]

    async def stream_klines(self, symbol: str, timeframe: str) -> AsyncIterator[tuple[str, Candle, bool]]:
        """Expose the reconnectable WebSocket stream through the venue gateway."""
        from src.market.binance_websocket import BinanceWebSocket

        stream = BinanceWebSocket(self.websocket_base_url, time_sync=self.sync_server_time)
        async for event in stream.stream_klines(symbol, timeframe):
            yield event

    async def get_current_price(self, symbol: str) -> Tick:
        client = self._ensure_connected()
        response = await client.get("/fapi/v1/ticker/bookTicker", params={"symbol": symbol.upper()})
        response.raise_for_status()
        row = response.json()
        bid, ask = float(row["bidPrice"]), float(row["askPrice"])
        return Tick(timestamp=datetime.now(timezone.utc), bid=bid, ask=ask, last=(bid + ask) / 2)

    async def get_funding_rate(self, symbol: str) -> float:
        """Fetch current funding rate from Binance premiumIndex endpoint."""
        client = self._ensure_connected()
        response = await client.get("/fapi/v1/premiumIndex", params={"symbol": symbol.upper()})
        response.raise_for_status()
        row = response.json()
        return float(row.get("lastFundingRate", 0.0))

    async def get_24hr_tickers(self) -> list[dict[str, Any]]:
        """Fetch 24hr ticker price change statistics for all futures symbols."""
        client = self._ensure_connected()
        response = await client.get("/fapi/v1/ticker/24hr")
        response.raise_for_status()
        return response.json()

    async def set_leverage(self, symbol: str, leverage: int = 5) -> dict[str, Any]:
        """Set symbol leverage on Binance Futures (signed request)."""
        if self._runtime_is_paper():
            return {"symbol": symbol.upper(), "leverage": leverage, "mode": "paper"}
        return await self._signed_request("POST", "/fapi/v1/leverage", {
            "symbol": symbol.upper(),
            "leverage": max(1, min(leverage, 125)),
        })

    async def set_margin_type(self, symbol: str, margin_type: str = "ISOLATED") -> dict[str, Any]:
        """Set symbol margin type (ISOLATED or CROSSED) on Binance Futures."""
        if self._runtime_is_paper():
            return {"symbol": symbol.upper(), "marginType": margin_type.upper(), "mode": "paper"}
        try:
            return await self._signed_request("POST", "/fapi/v1/marginType", {
                "symbol": symbol.upper(),
                "marginType": margin_type.upper(),
            })
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code == 400:
                try:
                    if int(exc.response.json().get("code", 0)) == -4046:
                        return {"code": 200, "msg": "already set", "symbol": symbol.upper()}
                except (TypeError, ValueError):
                    pass
            raise

    @staticmethod
    def calculate_estimated_liquidation_price(
        entry_price: float,
        leverage: int,
        direction: Direction,
        maintenance_margin_rate: float = 0.005,
    ) -> float:
        """Estimate liquidation price for isolated position."""
        if leverage <= 0 or entry_price <= 0:
            return 0.0
        if direction == Direction.BUY:
            return entry_price * (1.0 - (1.0 / leverage) + maintenance_margin_rate)
        else:
            return entry_price * (1.0 + (1.0 / leverage) - maintenance_margin_rate)

    @staticmethod
    def is_stop_loss_safe_from_liquidation(
        entry_price: float,
        stop_loss: float,
        leverage: int,
        direction: Direction,
        buffer_ratio: float = 0.7,
    ) -> bool:
        """Verify that stop loss triggers well before liquidation price is reached."""
        liq_price = BinanceGateway.calculate_estimated_liquidation_price(entry_price, leverage, direction)
        if direction == Direction.BUY:
            sl_distance = entry_price - stop_loss
            liq_distance = entry_price - liq_price
            return stop_loss > liq_price and sl_distance <= (liq_distance * buffer_ratio)
        else:
            sl_distance = stop_loss - entry_price
            liq_distance = liq_price - entry_price
            return stop_loss < liq_price and sl_distance <= (liq_distance * buffer_ratio)

    async def get_symbol_info(self, symbol: str) -> dict[str, Any]:
        client = self._ensure_connected()
        response = await client.get("/fapi/v1/exchangeInfo")
        response.raise_for_status()
        for item in response.json().get("symbols", []):
            if item.get("symbol") == symbol.upper():
                filters = {item["filterType"]: item for item in item.get("filters", [])}
                lot = filters.get("MARKET_LOT_SIZE") or filters.get("LOT_SIZE", {})
                price = filters.get("PRICE_FILTER", {})
                notional = filters.get("NOTIONAL") or filters.get("MIN_NOTIONAL", {})
                min_notional = float(notional.get("notional", notional.get("minNotional", 0)))
                applies_to_market = notional.get(
                    "applyMinToMarket", notional.get("applyToMarket", True)
                )
                if isinstance(applies_to_market, str):
                    applies_to_market = applies_to_market.lower() == "true"
                return {
                    "symbol": item["symbol"], "status": item.get("status"),
                    "base_asset": item.get("baseAsset"), "quote_asset": item.get("quoteAsset"),
                    "contract_type": item.get("contractType"),
                    "price_tick_size": float(price.get("tickSize", 0)),
                    "volume_min": float(lot.get("minQty", 0)),
                    "volume_max": float(lot.get("maxQty", 0)),
                    "volume_step": float(lot.get("stepSize", 0)),
                    "min_notional": min_notional if applies_to_market else 0.0,
                }
        raise BinanceConnectionError(f"Symbol not found: {symbol}")

    async def get_account_info(self) -> AccountInfo:
        if self._runtime_is_paper():
            return AccountInfo(
                login=0, name="Binance Market Data", server="paper",
                balance=settings.paper_initial_balance, equity=settings.paper_initial_balance,
                free_margin=settings.paper_initial_balance, currency="USDT", leverage=1,
                mode=TradingMode.PAPER,
            )
        if settings.binance_mode != "testnet" or not self._uses_testnet_endpoint():
            raise BinanceConnectionError("Signed Binance account access is restricted to BINANCE_MODE=testnet")
        row = await self._signed_request("GET", "/fapi/v2/account", {})
        return AccountInfo(
            login=0, name="Binance Futures Testnet", server="binance-testnet",
            balance=float(row.get("totalWalletBalance", 0)),
            equity=float(row.get("totalMarginBalance", 0)),
            margin=float(row.get("totalInitialMargin", 0)),
            free_margin=float(row.get("availableBalance", 0)),
            profit=float(row.get("totalUnrealizedProfit", 0)),
            currency="USDT", leverage=0, mode=TradingMode.DEMO,
        )

    async def test_testnet_account_access(self) -> AccountInfo:
        """Verify credentials with a read-only Testnet account request."""
        if not self._uses_testnet_endpoint():
            raise BinanceConnectionError("Credential checks are restricted to Binance Futures Testnet")
        if not await self.connect():
            raise BinanceConnectionError("Could not connect to Binance Futures Testnet")
        row = await self._signed_request("GET", "/fapi/v2/account", {})
        return AccountInfo(
            login=0,
            name="Binance Futures Testnet",
            server="binance-testnet",
            balance=float(row.get("totalWalletBalance", 0)),
            equity=float(row.get("totalMarginBalance", 0)),
            margin=float(row.get("totalInitialMargin", 0)),
            free_margin=float(row.get("availableBalance", 0)),
            profit=float(row.get("totalUnrealizedProfit", 0)),
            currency="USDT",
            leverage=0,
            mode=TradingMode.DEMO,
        )

    async def send_order(self, request: OrderRequest) -> OrderResult:
        trading_mode = get_runtime_trading_mode(settings.trading_mode)
        if trading_mode == "live":
            return OrderResult(
                success=False,
                venue=self.venue,
                error_message="Binance LIVE execution is disabled; use DEMO with Binance testnet safeguards",
            )
        if trading_mode != "demo":
            return OrderResult(success=False, venue=self.venue, error_message="Broker execution is disabled in PAPER mode")
        if settings.binance_mode != "testnet":
            return OrderResult(success=False, venue=self.venue, error_message="Binance execution requires BINANCE_MODE=testnet")
        if not self._uses_testnet_endpoint():
            return OrderResult(success=False, venue=self.venue, error_message="DEMO execution requires the Binance Futures Testnet endpoint")
        if not settings.binance_api_key or not settings.binance_api_secret:
            return OrderResult(success=False, venue=self.venue, error_message="Binance testnet credentials are not configured")
        if request.symbol.upper() not in settings.symbols:
            return OrderResult(success=False, venue=self.venue, error_message=f"Unsupported Binance symbol: {request.symbol}")
        if request.sl <= 0 or request.tp <= 0:
            return OrderResult(success=False, venue=self.venue, error_message="Server-side SL and TP are required")
        client_id = re.sub(r"[^A-Za-z0-9_-]", "-", request.execution_key or request.comment or "freebuff")[:28]
        if client_id in self._submitted_orders:
            previous = self._submitted_orders[client_id]
            return previous.model_copy(update={"metadata": {**previous.metadata, "duplicate": True}})
        side = "BUY" if request.direction == Direction.BUY else "SELL"
        execution_sl = Decimal(str(request.sl))
        execution_tp = Decimal(str(request.tp))
        await self._ensure_one_way_mode()
        filled = await self._find_existing_order(request.symbol, client_id)
        recovered = filled is not None
        if filled is None:
            existing_positions = await self.get_positions(request.symbol)
            if existing_positions:
                return OrderResult(
                    success=False, venue=self.venue,
                    error_message=f"Binance already has an open {request.symbol} position; refusing to add exposure",
                )
            for stale_order in await self._open_algo_orders(request.symbol):
                if str(stale_order.get("closePosition", "false")).lower() == "true":
                    try:
                        await self._cancel_algo_order(stale_order)
                    except Exception as exc:
                        return OrderResult(
                            success=False, venue=self.venue,
                            error_message=f"Could not clear stale protective order before entry: {exc}",
                        )
            await self.set_margin_type(request.symbol, "ISOLATED")
            await self.set_leverage(request.symbol, settings.risk.leverage)
            try:
                symbol_info = await self.get_symbol_info(request.symbol)
            except Exception as exc:
                return OrderResult(success=False, venue=self.venue, error_message=f"Could not read Binance symbol rules: {exc}")
            if symbol_info.get("status") != "TRADING":
                return OrderResult(success=False, venue=self.venue, error_message=f"Binance symbol is not trading: {request.symbol}")
            step = Decimal(str(symbol_info.get("volume_step", 0)))
            min_volume = Decimal(str(symbol_info.get("volume_min", 0)))
            max_volume = Decimal(str(symbol_info.get("volume_max", 0)))
            if step <= 0:
                return OrderResult(success=False, venue=self.venue, error_message=f"Invalid Binance quantity step for {request.symbol}")
            requested_volume = Decimal(str(request.volume))
            actual_volume = (requested_volume / step).to_integral_value(rounding=ROUND_DOWN) * step
            if actual_volume < min_volume or actual_volume <= 0:
                return OrderResult(success=False, venue=self.venue, error_message="Risk-approved size is below Binance's minimum quantity")
            if max_volume > 0:
                actual_volume = min(actual_volume, max_volume)

            tick_size = Decimal(str(symbol_info.get("price_tick_size", 0)))
            if tick_size <= 0:
                return OrderResult(success=False, venue=self.venue, error_message=f"Invalid Binance price tick for {request.symbol}")
            sl = execution_sl
            tp = execution_tp
            if request.direction == Direction.BUY:
                sl = (sl / tick_size).to_integral_value(rounding=ROUND_UP) * tick_size
                tp = (tp / tick_size).to_integral_value(rounding=ROUND_DOWN) * tick_size
            else:
                sl = (sl / tick_size).to_integral_value(rounding=ROUND_DOWN) * tick_size
                tp = (tp / tick_size).to_integral_value(rounding=ROUND_UP) * tick_size
            market = await self.get_current_price(request.symbol)
            reference_price = request.price or market.last
            valid_bracket = (
                (request.direction == Direction.BUY and sl < Decimal(str(reference_price)) < tp)
                or (request.direction == Direction.SELL and tp < Decimal(str(reference_price)) < sl)
            )
            if not valid_bracket:
                return OrderResult(success=False, venue=self.venue, error_message="Entry price moved outside the proposed SL/TP range")
            execution_sl = sl
            execution_tp = tp
            adjusted_risk = abs(Decimal(str(reference_price)) - sl)
            adjusted_reward = abs(tp - Decimal(str(reference_price)))
            if adjusted_risk <= 0 or adjusted_reward / adjusted_risk < Decimal(str(settings.risk.min_rr)):
                return OrderResult(success=False, venue=self.venue, error_message="Tick-aligned stop and target fall below the minimum risk-reward ratio")
            account = await self._signed_request("GET", "/fapi/v2/account", {})
            free_margin = Decimal(str(account.get("availableBalance", 0)))
            margin_budget = free_margin * Decimal(str(settings.risk.max_margin_utilization_pct))
            max_margin_volume = (margin_budget * Decimal(str(settings.risk.leverage))) / Decimal(str(reference_price))
            margin_volume = (max_margin_volume / step).to_integral_value(rounding=ROUND_DOWN) * step
            actual_volume = min(actual_volume, margin_volume)
            if actual_volume < min_volume:
                return OrderResult(
                    success=False, venue=self.venue,
                    error_message="Available Testnet margin is below the minimum Binance order size",
                )
            min_notional = Decimal(str(symbol_info.get("min_notional", 0)))
            if min_notional > 0 and actual_volume * Decimal(str(reference_price)) < min_notional:
                return OrderResult(
                    success=False, venue=self.venue,
                    error_message=(
                        "Risk-approved size is below Binance's minimum notional; "
                        "raising the quantity would exceed the configured risk budget"
                    ),
                )
            filled = await self._signed_request("POST", "/fapi/v1/order", {
                "symbol": request.symbol.upper(), "side": side, "type": "MARKET",
                "quantity": format(actual_volume.normalize(), "f"),
                "newClientOrderId": client_id, "newOrderRespType": "RESULT",
            })
        order_id = str(filled.get("orderId", ""))
        status = self._map_exchange_status(str(filled.get("status", "")))
        fill_price = float(filled.get("avgPrice") or filled.get("price") or 0) or None
        filled_volume = float(filled.get("executedQty", request.volume))
        protective, protective_error = await self._place_protective_orders(
            request.symbol, side, client_id, float(execution_sl), float(execution_tp),
            lookup_existing=recovered,
        ) if status in (OrderStatus.FILLED, OrderStatus.PARTIAL) else ({}, "Primary order is not filled")
        if recovered and status not in (OrderStatus.FILLED, OrderStatus.PARTIAL):
            protective_error = f"Existing Binance order is {filled.get('status', 'UNKNOWN')}"
        warning = None
        emergency_close = None
        if protective_error and protective.get("sl"):
            # A failed TP must not hide a successfully protected entry. Keep the
            # position journaled with its server-side stop and surface the TP issue.
            warning = protective_error
            logger.error("Binance position %s has its server-side SL but no TP: %s", order_id, warning)
            protective_error = None
        elif protective_error and status in (OrderStatus.FILLED, OrderStatus.PARTIAL):
            # Never leave a filled entry unprotected if the stop order was rejected.
            try:
                emergency_close = await self._signed_request("POST", "/fapi/v1/order", {
                    "symbol": request.symbol.upper(),
                    "side": "SELL" if side == "BUY" else "BUY",
                    "type": "MARKET", "quantity": filled.get("executedQty", request.volume),
                    "reduceOnly": "true", "newClientOrderId": f"fc-{client_id}"[:36],
                    "newOrderRespType": "RESULT",
                })
                protective_error = f"{protective_error}; entry flattened as fail-safe"
                logger.critical("Protective SL failed; flattened Binance entry order %s", order_id)
            except Exception as close_exc:
                protective_error = f"{protective_error}; emergency flatten failed: {close_exc}"
                logger.critical("Unprotected Binance position after failed SL; emergency flatten failed: %s", close_exc)
        result = OrderResult(
            success=protective_error is None, ticket=int(order_id) if order_id.isdigit() else None,
            price=fill_price, volume=filled_volume,
            venue=self.venue, external_order_id=order_id, status=status,
            error_message=protective_error,
            metadata={"primary": filled, "protective": protective, "duplicate": recovered,
                      "warning": warning, "emergency_close": emergency_close,
                      "execution_sl": float(execution_sl), "execution_tp": float(execution_tp)},
        )
        self._submitted_orders[client_id] = result
        return result

    async def modify_position(self, ticket: int, sl: float | None = None, tp: float | None = None) -> OrderResult:
        if get_runtime_trading_mode(settings.trading_mode) != "demo" or settings.binance_mode != "testnet" or not self._uses_testnet_endpoint():
            return OrderResult(success=False, ticket=ticket, error_message="Position modification requires DEMO on Binance Testnet")
        positions = await self.get_positions(self._position_symbols.get(ticket))
        position = next((pos for pos in positions if pos.ticket == ticket), None)
        if position is None:
            return OrderResult(success=False, ticket=ticket, error_message="Binance position not found")
        current = await self._open_algo_orders(position.symbol)
        order_side = "SELL" if position.direction == Direction.BUY else "BUY"
        kind_by_field = {"sl": "STOP_MARKET", "tp": "TAKE_PROFIT_MARKET"}
        replacements: dict[str, dict[str, Any]] = {}
        tick_size = Decimal(str((await self.get_symbol_info(position.symbol)).get("price_tick_size", 0)))
        if tick_size <= 0:
            return OrderResult(success=False, ticket=ticket, error_message="Invalid Binance price tick")
        market_price = Decimal(str(position.current_price))
        for field, price in (("sl", sl), ("tp", tp)):
            if price is None or price <= 0:
                continue
            new_price = Decimal(str(price))
            if new_price <= 0 or new_price % tick_size != 0:
                return OrderResult(success=False, ticket=ticket, error_message=f"New {field.upper()} is not aligned to Binance's price tick")
            old_price = Decimal(str(getattr(position, field)))
            if field == "sl":
                is_valid = (
                    new_price < market_price and (old_price <= 0 or new_price >= old_price)
                    if position.direction == Direction.BUY
                    else new_price > market_price and (old_price <= 0 or new_price <= old_price)
                )
            else:
                is_valid = new_price > market_price if position.direction == Direction.BUY else new_price < market_price
            if not is_valid:
                return OrderResult(success=False, ticket=ticket, error_message=f"New {field.upper()} would trigger immediately or loosen protection")
            client_id = f"pm-{ticket}-{field}-{int(time.time() * 1000)}"[:36]
            try:
                replacements[field] = await self._signed_request("POST", "/fapi/v1/algoOrder", {
                    "algoType": "CONDITIONAL", "symbol": position.symbol, "side": order_side,
                    "type": kind_by_field[field], "triggerPrice": str(new_price),
                    "closePosition": "true", "workingType": "MARK_PRICE", "clientAlgoId": client_id,
                })
            except Exception as exc:
                return OrderResult(success=False, ticket=ticket, error_message=f"Failed to place replacement {field.upper()}: {exc}")

            old_orders = [
                order for order in current
                if order.get("symbol") == position.symbol and order.get("side") == order_side
                and order.get("orderType") == kind_by_field[field]
                and str(order.get("algoStatus", "NEW")) == "NEW"
            ]
            for old_order in old_orders:
                if old_order.get("clientAlgoId") == client_id:
                    continue
                try:
                    await self._cancel_algo_order(old_order)
                except Exception as exc:
                    logger.warning("Replacement %s is active but old algo order could not be canceled: %s", field.upper(), exc)

        self._position_protection[ticket] = replacements or self._position_protection.get(ticket, {})
        return OrderResult(success=True, ticket=ticket, volume=position.volume, metadata={"protective": replacements})

    async def close_position(self, ticket: int, volume: float | None = None) -> OrderResult:
        if get_runtime_trading_mode(settings.trading_mode) != "demo" or settings.binance_mode != "testnet" or not self._uses_testnet_endpoint():
            return OrderResult(success=False, ticket=ticket, error_message="Position close requires DEMO on Binance Testnet")
        try:
            await self._ensure_one_way_mode()
            symbol = self._position_symbols.get(ticket)
            positions = await self.get_positions(symbol)
            position = next((pos for pos in positions if pos.ticket == ticket), None)
            if position is None:
                return OrderResult(success=False, ticket=ticket, error_message="Binance position not found")
            symbol_info = await self.get_symbol_info(position.symbol)
            step = Decimal(str(symbol_info.get("volume_step", 0)))
            min_volume = Decimal(str(symbol_info.get("volume_min", 0)))
            if step <= 0:
                return OrderResult(success=False, ticket=ticket, error_message="Invalid Binance quantity step")
            requested = Decimal(str(position.volume if volume is None else min(volume, position.volume)))
            close_volume = (requested / step).to_integral_value(rounding=ROUND_DOWN) * step
            if close_volume < min_volume or close_volume <= 0:
                return OrderResult(success=False, ticket=ticket, error_message="Close quantity is below Binance's minimum quantity")
            client_id = f"close-{ticket}-{int(time.time() * 1000)}"[:36]
            response = await self._signed_request("POST", "/fapi/v1/order", {
                "symbol": position.symbol, "side": "SELL" if position.direction == Direction.BUY else "BUY",
                "type": "MARKET", "quantity": format(close_volume.normalize(), "f"),
                "reduceOnly": "true", "newClientOrderId": client_id, "newOrderRespType": "RESULT",
            })
            closed_volume = float(response.get("executedQty", 0))
            requested_volume = float(close_volume)
            remaining = await self.get_positions(position.symbol)
            still_open = any(pos.ticket == ticket for pos in remaining)
            fill_confirmed = closed_volume + float(step) / 2 >= requested_volume
            closes_full_position = close_volume >= Decimal(str(position.volume)) - step / 2
            close_confirmed = fill_confirmed and (not closes_full_position or not still_open)
            warnings: list[str] = []
            if not still_open:
                for order in await self._open_algo_orders(position.symbol):
                    if order.get("side") == ("SELL" if position.direction == Direction.BUY else "BUY") and order.get("orderType") in {"STOP_MARKET", "TAKE_PROFIT_MARKET"}:
                        try:
                            await self._cancel_algo_order(order)
                        except Exception as exc:
                            warnings.append(f"Could not cancel stale protective order {order.get('algoId')}: {exc}")
                self._position_protection.pop(ticket, None)
            order_id = str(response.get("orderId", ""))
            return OrderResult(
                success=close_confirmed, ticket=int(order_id) if order_id.isdigit() else ticket,
                price=float(response.get("avgPrice") or response.get("price") or 0) or None,
                volume=closed_volume, venue=self.venue, external_order_id=order_id,
                status=self._map_exchange_status(str(response.get("status", ""))),
                error_message=(
                    None if close_confirmed else
                    f"Binance close incomplete: filled {closed_volume:g}/{requested_volume:g}; "
                    f"position_remaining={still_open}"
                ),
                metadata={
                    "position_ticket": ticket, "requested_volume": requested_volume,
                    "remaining_position": still_open, "warnings": warnings,
                },
            )
        except Exception as exc:
            return OrderResult(success=False, ticket=ticket, venue=self.venue, error_message=f"Binance close failed: {exc}")

    async def get_positions(self, symbol: str | None = None) -> list[Position]:
        if self._runtime_is_paper():
            return []
        if settings.binance_mode != "testnet" or not self._uses_testnet_endpoint():
            raise BinanceConnectionError("Binance positions require BINANCE_MODE=testnet")
        params = {"symbol": symbol.upper()} if symbol else {}
        rows = await self._signed_request("GET", "/fapi/v2/positionRisk", params)
        algo_orders = await self._open_algo_orders(symbol) if rows else []
        positions: list[Position] = []
        for row in rows:
            amount = float(row.get("positionAmt", 0))
            if amount == 0:
                continue
            symbol_name = row["symbol"]
            synthetic_id = zlib.crc32(f"{symbol_name}:{row.get('positionSide', 'BOTH')}".encode())
            self._position_symbols[synthetic_id] = symbol_name
            direction = Direction.BUY if amount > 0 else Direction.SELL
            close_side = "SELL" if direction == Direction.BUY else "BUY"
            protection: dict[str, dict[str, Any]] = {}
            for order in algo_orders:
                if order.get("symbol") != symbol_name or order.get("side") != close_side:
                    continue
                if order.get("algoStatus") != "NEW" or not order.get("closePosition"):
                    continue
                if order.get("orderType") == "STOP_MARKET":
                    protection["sl"] = order
                elif order.get("orderType") == "TAKE_PROFIT_MARKET":
                    protection["tp"] = order
            self._position_protection[synthetic_id] = protection
            positions.append(Position(
                ticket=synthetic_id, identifier=synthetic_id, symbol=symbol_name,
                direction=direction, volume=abs(amount), open_price=float(row.get("entryPrice", 0)),
                current_price=float(row.get("markPrice", 0)),
                # Read strategy protection from conditional orders; liquidation
                # price is never presented as an executable stop.
                sl=float(protection.get("sl", {}).get("triggerPrice", 0) or 0),
                tp=float(protection.get("tp", {}).get("triggerPrice", 0) or 0),
                profit=float(row.get("unRealizedProfit", 0)),
                open_time=datetime.fromtimestamp(float(row.get("updateTime", 0)) / 1000, tz=timezone.utc),
                comment="binance-position-risk",
            ))
        return positions

    async def get_position_deals(self, position_id: int) -> list[Deal]:
        if self._runtime_is_paper():
            return []
        if settings.binance_mode != "testnet":
            raise BinanceConnectionError("Binance deal history requires BINANCE_MODE=testnet")
        symbol = self._position_symbols.get(position_id)
        if not symbol:
            raise BinanceConnectionError(f"Unknown Binance position id: {position_id}")
        return await self.get_symbol_deals(symbol, position_id=position_id)

    async def get_symbol_deals(
        self, symbol: str, opening_order: int | None = None, position_id: int | None = None
    ) -> list[Deal]:
        """Map Binance user trades into deterministic entry/exit deals.

        When ``opening_order`` is supplied (the normal journal/restart path),
        unrelated fills for the same symbol are excluded and entry is derived
        from the recorded Binance order id instead of list position.
        """
        if settings.binance_mode != "testnet":
            raise BinanceConnectionError("Binance deal history requires BINANCE_MODE=testnet")
        symbol = symbol.upper()
        rows = await self._signed_request("GET", "/fapi/v1/userTrades", {"symbol": symbol, "limit": 1000})
        if opening_order is not None:
            try:
                opening_index = next(i for i, row in enumerate(rows) if int(row.get("orderId", -1)) == opening_order)
            except StopIteration:
                return []
            opening_side = rows[opening_index].get("side")
            opening_rows = [
                row for row in rows
                if int(row.get("orderId", -1)) == opening_order
            ]
            relevant = list(opening_rows)
            opening_qty = sum(float(row.get("qty", 0)) for row in opening_rows)
            exit_qty = 0.0
            last_opening_index = max(
                i for i, row in enumerate(rows)
                if int(row.get("orderId", -1)) == opening_order
            )
            for row in rows[last_opening_index + 1 :]:
                if row.get("side") == opening_side:
                    continue
                relevant.append(row)
                exit_qty += float(row.get("qty", 0))
                if exit_qty + 1e-8 >= opening_qty:
                    break
            rows = relevant

        if not rows:
            return []
        resolved_position_id = position_id
        if resolved_position_id is None:
            resolved_position_id = zlib.crc32(f"{symbol}:BOTH".encode())
        opening_order_id = opening_order
        if opening_order_id is None:
            opening_order_id = int(rows[0].get("orderId", 0))
        deals: list[Deal] = []
        for row in rows:
            qty = float(row.get("qty", 0))
            if qty <= 0:
                continue
            row_order = int(row["orderId"])
            entry = 0 if row_order == opening_order_id else 1
            trade_side = 0 if row.get("side") == "BUY" else 1
            deals.append(Deal(
                ticket=int(row["id"]), order=row_order, position_id=resolved_position_id,
                time=datetime.fromtimestamp(int(row["time"]) / 1000, tz=timezone.utc),
                entry=entry, type=trade_side, volume=qty, price=float(row["price"]),
                profit=float(row.get("realizedPnl", 0)),
                commission=-abs(float(row.get("commission", 0))), symbol=symbol,
            ))
        return deals
