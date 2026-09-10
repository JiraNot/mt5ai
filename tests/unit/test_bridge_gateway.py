"""Unit tests for BridgeGateway with a fully mocked HTTP transport."""

from __future__ import annotations

import json
from datetime import datetime, timezone

import httpx
import pytest

from src.core.exceptions import MT5ConnectionError
from src.core.types import Direction, OrderRequest
from src.market.bridge_gateway import BridgeGateway


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _iso(dt: datetime) -> str:
    return dt.isoformat()


def make_gateway(handler) -> BridgeGateway:
    """Build a gateway bound to an in-process mock transport."""
    return BridgeGateway(
        base_url="http://bridge.test:8900",
        token="secret-token",
        transport=httpx.MockTransport(handler),
    )


def iso_handler_factory(payload: dict, check_auth: bool = True, health: dict | None = None):
    """Standard request router for most tests. /health always reports healthy."""

    def handler(request: httpx.Request) -> httpx.Response:
        if check_auth and request.headers.get("X-Bridge-Token") != "secret-token":
            return httpx.Response(401, json={"detail": "Invalid bridge token"})

        path = request.url.path

        if request.method == "GET" and path == "/health":
            return httpx.Response(200, json=health or HEALTH_OK)

        if request.method == "GET" and path.startswith("/ohlcv/"):
            return httpx.Response(200, json=payload)

        if request.method == "GET" and path.startswith("/tick/"):
            return httpx.Response(200, json={"tick": payload})

        if request.method == "GET" and path.startswith("/symbol/"):
            return httpx.Response(200, json={"info": payload})

        if request.method == "GET" and path == "/account":
            return httpx.Response(200, json={"account": payload})

        if request.method == "GET" and path == "/positions":
            return httpx.Response(200, json={"positions": payload})

        if request.method == "POST" and path == "/order":
            body = json.loads(request.content)
            return httpx.Response(200, json={"result": {**payload, "echo_symbol": body["symbol"]}})

        if request.method == "POST" and path.endswith("/modify"):
            return httpx.Response(200, json={"result": payload})

        if request.method == "POST" and path.endswith("/close"):
            return httpx.Response(200, json={"result": payload})

        return httpx.Response(404, json={"detail": f"Unhandled: {request.method} {path}"})

    return handler


HEALTH_OK = {
    "status": "ok",
    "mt5_initialized": True,
    "terminal": "MetaTrader 5",
    "build": 6182,
    "account": 5055570761,
    "server": "MetaQuotes-Demo",
    "balance": 100000.0,
}

SAMPLE_CANDLE = {
    "timestamp": _iso(datetime(2026, 9, 4, 12, 0, tzinfo=timezone.utc)),
    "open": 4430.10,
    "high": 4435.80,
    "low": 4428.40,
    "close": 4434.66,
    "volume": 1234.0,
}

SAMPLE_TICK = {
    "timestamp": _iso(datetime(2026, 9, 4, 12, 0, tzinfo=timezone.utc)),
    "bid": 4434.50,
    "ask": 4434.72,
    "last": 0.0,
    "volume": 0.0,
}

SAMPLE_ACCOUNT = {
    "login": 5055570761,
    "name": "Demo",
    "server": "MetaQuotes-Demo",
    "balance": 100000.0,
    "equity": 100250.5,
    "margin": 500.0,
    "free_margin": 99750.5,
    "margin_level": 20050.1,
    "profit": 250.5,
    "currency": "USD",
    "leverage": 100,
}

SAMPLE_POSITION = {
    "ticket": 123456789,
    "symbol": "XAUUSD",
    "direction": "BUY",
    "volume": 0.1,
    "open_price": 4430.00,
    "current_price": 4434.66,
    "sl": 4425.00,
    "tp": 4450.00,
    "profit": 46.60,
    "swap": -0.5,
    "commission": 0.0,
    "magic": 20240101,
    "open_time": _iso(datetime(2026, 9, 4, 10, 0, tzinfo=timezone.utc)),
    "comment": "fvg_final",
}


# ─── Connection ───────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_connect_success():
    gw = make_gateway(iso_handler_factory(HEALTH_OK))
    assert await gw.connect() is True
    assert gw.connected is True
    await gw.disconnect()


@pytest.mark.asyncio
async def test_connect_rejects_when_mt5_not_initialized():
    bad_health = {**HEALTH_OK, "mt5_initialized": False}
    gw = make_gateway(iso_handler_factory(HEALTH_OK, health=bad_health))
    assert await gw.connect() is False
    assert gw.connected is False


@pytest.mark.asyncio
async def test_connect_fails_when_server_down():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused")

    gw = make_gateway(handler)
    assert await gw.connect() is False


@pytest.mark.asyncio
async def test_operations_fail_when_not_connected():
    gw = make_gateway(iso_handler_factory(HEALTH_OK))
    with pytest.raises(MT5ConnectionError):
        await gw.get_current_price("XAUUSD")
    with pytest.raises(MT5ConnectionError):
        await gw.get_account_info()
    with pytest.raises(MT5ConnectionError):
        await gw.get_positions()


# ─── Market Data ──────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_get_ohlcv_returns_candles():
    gw = make_gateway(iso_handler_factory({"candles": [SAMPLE_CANDLE]}))
    await gw.connect()

    candles = await gw.get_ohlcv("XAUUSD", "M5", count=100)
    assert len(candles) == 1
    assert candles[0].open == 4430.10
    assert candles[0].close == 4434.66
    assert candles[0].volume == 1234.0
    await gw.disconnect()


@pytest.mark.asyncio
async def test_get_ohlcv_rejects_bad_timeframe():
    gw = make_gateway(iso_handler_factory({"candles": []}))
    await gw.connect()
    with pytest.raises(ValueError):
        await gw.get_ohlcv("XAUUSD", "W1")
    await gw.disconnect()


@pytest.mark.asyncio
async def test_get_ohlcv_returns_empty_on_bridge_error():
    gw = make_gateway(iso_handler_factory({"error": "No data"}))
    await gw.connect()
    assert await gw.get_ohlcv("XAUUSD", "H1") == []
    await gw.disconnect()


@pytest.mark.asyncio
async def test_get_current_price_returns_tick():
    gw = make_gateway(iso_handler_factory(SAMPLE_TICK))
    await gw.connect()

    tick = await gw.get_current_price("XAUUSD")
    assert tick.bid == 4434.50
    assert tick.ask == 4434.72
    assert tick.spread == pytest.approx(0.22)
    await gw.disconnect()


@pytest.mark.asyncio
async def test_get_symbol_info():
    info_payload = {
        "digits": 2,
        "point": 0.01,
        "spread": 22,
        "volume_min": 0.01,
        "volume_max": 100.0,
        "volume_step": 0.01,
        "trade_contract_size": 100,
        "margin_initial": 0.01,
    }
    gw = make_gateway(iso_handler_factory(info_payload))
    await gw.connect()

    info = await gw.get_symbol_info("XAUUSD")
    assert info["digits"] == 2
    assert info["volume_min"] == 0.01
    await gw.disconnect()


# ─── Account ──────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_get_account_info():
    gw = make_gateway(iso_handler_factory(SAMPLE_ACCOUNT))
    await gw.connect()

    account = await gw.get_account_info()
    assert account.login == 5055570761
    assert account.balance == 100000.0
    assert account.currency == "USD"
    await gw.disconnect()


# ─── Orders ───────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_send_order_success():
    result_payload = {"success": True, "ticket": 987654321, "price": 4434.72, "volume": 0.1}
    gw = make_gateway(iso_handler_factory(result_payload))
    await gw.connect()

    request = OrderRequest(
        symbol="XAUUSD",
        direction=Direction.BUY,
        volume=0.1,
        sl=4425.0,
        tp=4450.0,
        comment="fvg_final",
    )
    result = await gw.send_order(request)
    assert result.success is True
    assert result.ticket == 987654321
    assert result.price == 4434.72
    await gw.disconnect()


@pytest.mark.asyncio
async def test_send_order_broker_rejection():
    result_payload = {"success": False, "error_code": 10030, "error_message": "Invalid fill"}
    gw = make_gateway(iso_handler_factory(result_payload))
    await gw.connect()

    request = OrderRequest(
        symbol="XAUUSD",
        direction=Direction.SELL,
        volume=0.1,
        sl=4445.0,
        tp=4420.0,
    )
    result = await gw.send_order(request)
    assert result.success is False
    assert result.error_code == 10030
    await gw.disconnect()


@pytest.mark.asyncio
async def test_modify_and_close_position():
    gw = make_gateway(iso_handler_factory({"success": True, "ticket": 123456789}))
    await gw.connect()

    mod = await gw.modify_position(123456789, sl=4436.0)
    assert mod.success is True

    close = await gw.close_position(123456789)
    assert close.success is True
    await gw.disconnect()


@pytest.mark.asyncio
async def test_get_positions():
    gw = make_gateway(iso_handler_factory([SAMPLE_POSITION]))
    await gw.connect()

    positions = await gw.get_positions("XAUUSD")
    assert len(positions) == 1
    assert positions[0].ticket == 123456789
    assert positions[0].direction == Direction.BUY
    assert positions[0].profit == 46.60
    await gw.disconnect()


@pytest.mark.asyncio
async def test_auth_header_is_sent():
    """Bridge must reject requests missing the token."""
    gw = BridgeGateway(
        base_url="http://bridge.test:8900",
        token="WRONG_TOKEN",
        transport=httpx.MockTransport(iso_handler_factory(HEALTH_OK)),
    )
    assert await gw.connect() is False
