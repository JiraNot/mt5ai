"""Unit tests for the read-only Binance gateway."""

import httpx
import pytest

from src.core.config import load_settings
from src.market.binance_gateway import BinanceGateway
from src.execution.paper_gateway import PaperGateway
from src.market.binance_websocket import parse_kline_event
from src.core.types import Direction, OrderRequest


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
    assert "testnet" in (result.error_message or "")


def test_binance_settings_are_env_overridable(monkeypatch):
    monkeypatch.setenv("BINANCE_MODE", "testnet")
    monkeypatch.setenv("BINANCE_SYMBOL", "ethusdt")
    configured = load_settings()
    assert configured.binance_mode == "testnet"
    assert configured.binance_symbol == "ETHUSDT"


@pytest.mark.asyncio
async def test_paper_gateway_fills_and_deduplicates():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/fapi/v1/ping":
            return httpx.Response(200, json={})
        return httpx.Response(200, json={"bidPrice": "100.0", "askPrice": "100.2"})

    market = make_gateway(handler)
    paper = PaperGateway(market, initial_balance=1000)
    assert await paper.connect()
    request = OrderRequest(symbol="BTCUSDT", direction=Direction.BUY, volume=1, sl=99, tp=102, execution_key="k1", venue="binance")
    first = await paper.send_order(request)
    duplicate = await paper.send_order(request)
    assert first.success and duplicate.success
    assert duplicate.ticket == first.ticket
    assert duplicate.metadata["duplicate"] is True
    assert len(await paper.get_positions("BTCUSDT")) == 1
    closed = await paper.close_position(first.ticket)
    assert closed.success
    assert not await paper.get_positions("BTCUSDT")
    await paper.disconnect()


def test_parse_kline_event_preserves_closed_flag():
    symbol, candle, closed = parse_kline_event({
        "e": "kline", "s": "BTCUSDT", "k": {
            "t": 0, "o": "100", "h": "105", "l": "99", "c": "103", "v": "12.5", "x": True,
        },
    })
    assert symbol == "BTCUSDT"
    assert candle.close == 103
    assert closed is True


@pytest.mark.asyncio
async def test_testnet_order_places_market_and_protective_orders(monkeypatch):
    monkeypatch.setattr("src.market.binance_gateway.settings.binance_mode", "testnet")
    monkeypatch.setattr("src.market.binance_gateway.settings.binance_api_key", "key")
    monkeypatch.setattr("src.market.binance_gateway.settings.binance_api_secret", "secret")
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        if request.url.path == "/fapi/v1/ping":
            return httpx.Response(200, json={})
        if request.url.path == "/fapi/v1/time":
            return httpx.Response(200, json={"serverTime": 0})
        assert request.url.path == "/fapi/v1/order"
        if len(calls) == 3:
            return httpx.Response(200, json={"orderId": 123, "status": "FILLED", "avgPrice": "100", "executedQty": "1"})
        return httpx.Response(200, json={"orderId": 124 + len(calls), "status": "NEW"})

    gateway = make_gateway(handler)
    assert await gateway.connect()
    result = await gateway.send_order(OrderRequest(
        symbol="BTCUSDT", direction=Direction.BUY, volume=1, sl=99, tp=102,
        execution_key="candidate-1", venue="binance",
    ))
    assert result.success is True
    assert result.external_order_id == "123"
    assert len(calls) == 5
    assert calls[1].url.path == "/fapi/v1/time"
    assert calls[2].headers["X-MBX-APIKEY"] == "key"
    assert calls[3].url.params["type"] == "STOP_MARKET"
    assert calls[4].url.params["type"] == "TAKE_PROFIT_MARKET"
    await gateway.disconnect()
