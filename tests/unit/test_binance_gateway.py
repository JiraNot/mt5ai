"""Unit tests for the read-only Binance gateway."""

import httpx
import pytest

from src.core.config import load_settings
from src.market.binance_gateway import BinanceGateway


def make_gateway(handler) -> BinanceGateway:
    return BinanceGateway(
        base_url="https://binance.test",
        transport=httpx.MockTransport(handler),
    )


@pytest.mark.asyncio
async def test_connect_and_read_klines():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/fapi/v1/ping":
            return httpx.Response(200, json={})
        assert request.url.path == "/fapi/v1/klines"
        assert request.url.params["interval"] == "5m"
        return httpx.Response(200, json=[[
            0, "100.0", "105.0", "99.0", "103.0", "12.5", 0, "0", 0, "0", "0", "0"
        ]])

    gateway = make_gateway(handler)
    assert await gateway.connect()
    candles = await gateway.get_ohlcv("BTCUSDT", "M5", 10)
    assert candles[0].close == 103.0
    assert candles[0].volume == 12.5
    await gateway.disconnect()


@pytest.mark.asyncio
async def test_read_current_price():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/fapi/v1/ping":
            return httpx.Response(200, json={})
        return httpx.Response(200, json={"bidPrice": "100.0", "askPrice": "100.2"})

    gateway = make_gateway(handler)
    await gateway.connect()
    tick = await gateway.get_current_price("BTCUSDT")
    assert tick.mid == pytest.approx(100.1)
    await gateway.disconnect()


@pytest.mark.asyncio
async def test_order_execution_is_fail_closed():
    gateway = BinanceGateway()
    result = await gateway.send_order(None)  # type: ignore[arg-type]
    assert result.success is False
    assert "disabled" in (result.error_message or "")


def test_binance_settings_are_env_overridable(monkeypatch):
    monkeypatch.setenv("BINANCE_MODE", "testnet")
    monkeypatch.setenv("BINANCE_SYMBOL", "ethusdt")
    configured = load_settings()
    assert configured.binance_mode == "testnet"
    assert configured.binance_symbol == "ETHUSDT"
