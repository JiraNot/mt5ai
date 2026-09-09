"""
Bridge Gateway — MT5Connection-compatible adapter over HTTP.

Talks to the standalone `mt5-bridge` server (separate project, lives at
~/projects/mt5-bridge — deploy its mt5_bridge.py to the Windows machine that
hosts the real MT5 terminal). Server setup: mt5-bridge/README.md.

Select with MT5_MODE=bridge in .env:
    MT5_MODE=bridge
    BRIDGE_URL=http://100.x.y.z:8900     # Tailscale/WireGuard IP recommended
    BRIDGE_TOKEN=your_shared_secret
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

import httpx

from src.core.config import settings
from src.core.exceptions import MT5ConnectionError
from src.core.types import (
    AccountInfo,
    Candle,
    Direction,
    OrderRequest,
    OrderResult,
    Position,
    Tick,
)

logger = logging.getLogger(__name__)

# Must mirror the bridge server's accepted timeframes
_TF_MAP = {"M1": 1, "M5": 5, "M15": 15, "H1": 16385, "H4": 16388, "D1": 16408}


class BridgeGateway:
    """
    Drop-in replacement for MT5Connection when MT5 runs on another machine.

    Implements the same async interface: connect, disconnect, get_ohlcv,
    get_current_price, get_symbol_info, get_account_info, send_order,
    modify_position, close_position, get_positions.
    """

    def __init__(
        self,
        base_url: str | None = None,
        token: str | None = None,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._base_url = (base_url or settings.bridge_url).rstrip("/")
        self._token = token or settings.bridge_token
        self._timeout = settings.bridge_timeout
        self._transport = transport  # injectable for tests (httpx.MockTransport)
        self._connected = False
        self._client: httpx.AsyncClient | None = None

    @property
    def connected(self) -> bool:
        return self._connected

    def _headers(self) -> dict[str, str]:
        return {"X-Bridge-Token": self._token} if self._token else {}

    def _ensure_connected(self) -> None:
        if not self._connected:
            raise MT5ConnectionError("Not connected to bridge")

    async def connect(self) -> bool:
        """Verify the bridge and its MT5 terminal are reachable."""
        try:
            self._client = httpx.AsyncClient(
                base_url=self._base_url,
                headers=self._headers(),
                timeout=self._timeout,
                transport=self._transport,
            )
            resp = await self._client.get("/health")
            resp.raise_for_status()
            health = resp.json()

            if not health.get("mt5_initialized"):
                logger.error(
                    f"Bridge reachable but MT5 not initialized: {health}"
                )
                await self._client.aclose()
                self._client = None
                return False

            self._connected = True
            logger.info(
                f"Bridge connected: {self._base_url} "
                f"(account={health.get('account')}, server={health.get('server')})"
            )
            return True

        except Exception as e:
            logger.error(f"Bridge connection failed ({self._base_url}): {e}")
            if self._client:
                await self._client.aclose()
                self._client = None
            return False

    async def disconnect(self) -> None:
        if self._client:
            await self._client.aclose()
            self._client = None
        self._connected = False
        logger.info("Bridge disconnected")

    async def reconnect(self) -> bool:
        logger.info("Attempting bridge reconnection...")
        await self.disconnect()
        return await self.connect()

    # ─── Market Data ──────────────────────────────────────────────────────────

    async def get_ohlcv(
        self,
        symbol: str,
        timeframe: str,
        count: int = 500,
        start: datetime | None = None,
    ) -> list[Candle]:
        self._ensure_connected()
        if timeframe not in _TF_MAP:
            raise ValueError(f"Unsupported timeframe: {timeframe}")

        resp = await self._client.get(  # type: ignore[union-attr]
            f"/ohlcv/{symbol}",
            params={"timeframe": timeframe, "count": count},
        )
        resp.raise_for_status()
        payload = resp.json()
        if payload.get("error"):
            logger.warning(f"Bridge OHLCV error for {symbol} {timeframe}: {payload['error']}")
            return []

        return [Candle(**row) for row in payload.get("candles", [])]

    async def get_current_price(self, symbol: str) -> Tick:
        self._ensure_connected()
        resp = await self._client.get(f"/tick/{symbol}")  # type: ignore[union-attr]
        resp.raise_for_status()
        payload = resp.json()
        if payload.get("error"):
            raise MT5ConnectionError(f"Tick failed for {symbol}: {payload['error']}")
        return Tick(**payload["tick"])

    async def get_symbol_info(self, symbol: str) -> dict[str, Any]:
        self._ensure_connected()
        resp = await self._client.get(f"/symbol/{symbol}")  # type: ignore[union-attr]
        resp.raise_for_status()
        return resp.json()["info"]

    # ─── Account ──────────────────────────────────────────────────────────────

    async def get_account_info(self) -> AccountInfo:
        self._ensure_connected()
        resp = await self._client.get("/account")  # type: ignore[union-attr]
        resp.raise_for_status()
        return AccountInfo(**resp.json()["account"])

    # ─── Orders ───────────────────────────────────────────────────────────────

    async def send_order(self, request: OrderRequest) -> OrderResult:
        self._ensure_connected()
        resp = await self._client.post(  # type: ignore[union-attr]
            "/order", json=request.model_dump(mode="json")
        )
        resp.raise_for_status()
        return OrderResult(**resp.json()["result"])

    async def modify_position(
        self, ticket: int, sl: float | None = None, tp: float | None = None
    ) -> OrderResult:
        self._ensure_connected()
        resp = await self._client.post(  # type: ignore[union-attr]
            f"/position/{ticket}/modify",
            json={"sl": sl, "tp": tp},
        )
        resp.raise_for_status()
        return OrderResult(**resp.json()["result"])

    async def close_position(self, ticket: int) -> OrderResult:
        self._ensure_connected()
        resp = await self._client.post(f"/position/{ticket}/close")  # type: ignore[union-attr]
        resp.raise_for_status()
        return OrderResult(**resp.json()["result"])

    async def get_positions(self, symbol: str | None = None) -> list[Position]:
        self._ensure_connected()
        resp = await self._client.get(  # type: ignore[union-attr]
            "/positions", params={"symbol": symbol} if symbol else None
        )
        resp.raise_for_status()
        return [Position(**p) for p in resp.json().get("positions", [])]
