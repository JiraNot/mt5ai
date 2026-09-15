"""Unit tests for the Binance market-data and execution gateway."""

import asyncio
import httpx
import pytest

from src.core.config import load_settings
from src.market.binance_gateway import BinanceGateway
from src.execution.paper_gateway import PaperGateway
from src.market.binance_websocket import parse_kline_event
from src.market.binance_websocket import BinanceWebSocket
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
async def test_rest_klines_exclude_forming_candle():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/fapi/v1/ping":
            return httpx.Response(200, json={})
        return httpx.Response(200, json=[
            [0, "100", "101", "99", "100.5", "1", 0, "0", 0, "0", "0", "0"],
            [9_999_999_999_999, "100", "101", "99", "100.5", "1", 9_999_999_999_999, "0", 0, "0", "0", "0"],
        ])

    gateway = make_gateway(handler)
    await gateway.connect()
    candles = await gateway.get_ohlcv("BTCUSDT", "M5", 10)
    assert len(candles) == 1
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
        if request.method == "GET":
            return httpx.Response(400, json={"code": -2013, "msg": "Order does not exist."})
        if len(calls) == 4:
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
    assert len(calls) == 6
    assert calls[1].url.path == "/fapi/v1/time"
    assert calls[2].headers["X-MBX-APIKEY"] == "key"
    assert calls[2].url.params["timestamp"]
    assert calls[2].url.params["recvWindow"] == "5000"
    assert len(calls[2].url.params["signature"]) == 64
    assert calls[2].url.params["origClientOrderId"] == "candidate-1"
    assert calls[3].url.params["type"] == "MARKET"
    assert calls[4].url.params["type"] == "STOP_MARKET"
    assert calls[5].url.params["type"] == "TAKE_PROFIT_MARKET"
    await gateway.disconnect()


@pytest.mark.asyncio
async def test_partial_primary_fill_returns_partial_status_and_filled_volume(monkeypatch):
    monkeypatch.setattr("src.market.binance_gateway.settings.binance_mode", "testnet")
    monkeypatch.setattr("src.market.binance_gateway.settings.binance_api_key", "key")
    monkeypatch.setattr("src.market.binance_gateway.settings.binance_api_secret", "secret")
    order_calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/fapi/v1/ping":
            return httpx.Response(200, json={})
        if request.url.path == "/fapi/v1/time":
            return httpx.Response(200, json={"serverTime": 0})
        if request.method == "GET":
            return httpx.Response(400, json={"code": -2013, "msg": "Order does not exist."})
        order_calls.append(request)
        if len(order_calls) == 1:
            return httpx.Response(200, json={
                "orderId": 200, "status": "PARTIALLY_FILLED",
                "avgPrice": "100", "executedQty": "0.4",
            })
        return httpx.Response(200, json={"orderId": 200 + len(order_calls), "status": "NEW"})

    gateway = BinanceGateway(base_url="https://binance.test", transport=httpx.MockTransport(handler))
    await gateway.connect()
    result = await gateway.send_order(OrderRequest(
        symbol="BTCUSDT", direction=Direction.BUY, volume=1, sl=99, tp=102,
        execution_key="partial-1", venue="binance",
    ))
    assert result.success is True
    assert result.status.value == "PARTIAL"
    assert result.volume == pytest.approx(0.4)
    assert len(order_calls) == 3
    assert all(call.url.params["closePosition"] == "true" for call in order_calls[1:])
    await gateway.disconnect()


@pytest.mark.asyncio
async def test_testnet_order_is_idempotent_across_gateway_restart(monkeypatch):
    monkeypatch.setattr("src.market.binance_gateway.settings.binance_mode", "testnet")
    monkeypatch.setattr("src.market.binance_gateway.settings.binance_api_key", "key")
    monkeypatch.setattr("src.market.binance_gateway.settings.binance_api_secret", "secret")
    primary = {"orderId": 301, "status": "FILLED", "avgPrice": "100", "executedQty": "1"}
    protective = {
        "restart-key-sl": {"orderId": 302, "status": "NEW"},
        "restart-key-tp": {"orderId": 303, "status": "NEW"},
    }
    post_calls = []
    installed = False

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal installed
        if request.url.path == "/fapi/v1/ping":
            return httpx.Response(200, json={})
        if request.url.path == "/fapi/v1/time":
            return httpx.Response(200, json={"serverTime": 0})
        assert request.url.path == "/fapi/v1/order"
        client_id = request.url.params.get("origClientOrderId")
        if request.method == "GET":
            if installed and client_id == "restart-key":
                return httpx.Response(200, json=primary)
            if installed and client_id in protective:
                return httpx.Response(200, json=protective[client_id])
            return httpx.Response(400, json={"code": -2013, "msg": "Order does not exist."})
        post_calls.append(request)
        if request.url.params["type"] == "MARKET":
            installed = True
            return httpx.Response(200, json=primary)
        suffix = "restart-key-sl" if request.url.params["type"] == "STOP_MARKET" else "restart-key-tp"
        return httpx.Response(200, json=protective[suffix])

    request = OrderRequest(
        symbol="BTCUSDT", direction=Direction.BUY, volume=1, sl=99, tp=102,
        execution_key="restart-key", venue="binance",
    )
    first = BinanceGateway(base_url="https://binance.test", transport=httpx.MockTransport(handler))
    await first.connect()
    first_result = await first.send_order(request)
    await first.disconnect()

    restarted = BinanceGateway(base_url="https://binance.test", transport=httpx.MockTransport(handler))
    await restarted.connect()
    recovered = await restarted.send_order(request)
    assert first_result.success and recovered.success
    assert recovered.external_order_id == "301"
    assert recovered.metadata["duplicate"] is True
    assert len(post_calls) == 3
    await restarted.disconnect()


def test_gateway_selects_testnet_websocket_endpoint():
    gateway = BinanceGateway(base_url="https://testnet.binancefuture.com")
    assert gateway.websocket_base_url == "wss://fstream.binancefuture.com"


def test_gateway_selects_mainnet_websocket_endpoint():
    gateway = BinanceGateway(base_url="https://fapi.binance.com")
    assert gateway.websocket_base_url == "wss://fstream.binance.com"


@pytest.mark.asyncio
async def test_websocket_syncs_server_time_before_connect(monkeypatch):
    calls = []

    class FakeSocket:
        async def __aenter__(self):
            calls.append("connect")
            return self

        async def __aexit__(self, *_):
            return False

        def __aiter__(self):
            return self

        async def __anext__(self):
            raise asyncio.CancelledError

    class FakeWebsockets:
        @staticmethod
        def connect(*_args, **_kwargs):
            return FakeSocket()

    import sys
    monkeypatch.setitem(sys.modules, "websockets", FakeWebsockets)

    async def sync_time():
        calls.append("sync")
        return 123

    stream = BinanceWebSocket("wss://fstream.binance.com", reconnect_delay=0, time_sync=sync_time)
    iterator = stream.stream_klines("BTCUSDT", "M5")
    with pytest.raises(asyncio.CancelledError):
        await iterator.__anext__()
    assert calls == ["sync", "connect"]
    assert stream.server_time_offset_ms == 123


@pytest.mark.asyncio
async def test_position_risk_does_not_expose_liquidation_as_stop(monkeypatch):
    monkeypatch.setattr("src.market.binance_gateway.settings.binance_mode", "testnet")
    monkeypatch.setattr("src.market.binance_gateway.settings.binance_api_key", "key")
    monkeypatch.setattr("src.market.binance_gateway.settings.binance_api_secret", "secret")

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/fapi/v1/ping":
            return httpx.Response(200, json={})
        if request.url.path == "/fapi/v1/time":
            return httpx.Response(200, json={"serverTime": 0})
        return httpx.Response(200, json=[{
            "symbol": "BTCUSDT", "positionAmt": "0.5", "entryPrice": "100",
            "markPrice": "101", "liquidationPrice": "50", "unRealizedProfit": "0.5",
            "updateTime": "0", "positionSide": "BOTH",
        }])

    gateway = BinanceGateway(base_url="https://binance.test", transport=httpx.MockTransport(handler))
    await gateway.connect()
    positions = await gateway.get_positions("BTCUSDT")
    assert positions[0].sl == 0
    await gateway.disconnect()


@pytest.mark.asyncio
async def test_symbol_deals_filter_to_recorded_order_and_map_partial_exit(monkeypatch):
    monkeypatch.setattr("src.market.binance_gateway.settings.binance_mode", "testnet")
    monkeypatch.setattr("src.market.binance_gateway.settings.binance_api_key", "key")
    monkeypatch.setattr("src.market.binance_gateway.settings.binance_api_secret", "secret")

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/fapi/v1/ping":
            return httpx.Response(200, json={})
        if request.url.path == "/fapi/v1/time":
            return httpx.Response(200, json={"serverTime": 0})
        assert request.url.path == "/fapi/v1/userTrades"
        return httpx.Response(200, json=[
            {"id": 1, "orderId": 90, "time": 1_000, "side": "BUY", "qty": "2", "price": "95", "realizedPnl": "0", "commission": "0.1"},
            {"id": 2, "orderId": 100, "time": 2_000, "side": "BUY", "qty": "0.6", "price": "100", "realizedPnl": "0", "commission": "0.1"},
            {"id": 6, "orderId": 100, "time": 2_100, "side": "BUY", "qty": "0.4", "price": "101", "realizedPnl": "0", "commission": "0.1"},
            {"id": 3, "orderId": 101, "time": 3_000, "side": "SELL", "qty": "0.4", "price": "110", "realizedPnl": "4", "commission": "0.02"},
            {"id": 4, "orderId": 102, "time": 4_000, "side": "SELL", "qty": "0.6", "price": "111", "realizedPnl": "5", "commission": "0.02"},
            {"id": 5, "orderId": 103, "time": 5_000, "side": "SELL", "qty": "2", "price": "112", "realizedPnl": "20", "commission": "0.02"},
        ])

    gateway = BinanceGateway(base_url="https://binance.test", transport=httpx.MockTransport(handler))
    await gateway.connect()
    deals = await gateway.get_symbol_deals("btcusdt", opening_order=100, position_id=777)
    assert [deal.order for deal in deals] == [100, 100, 101, 102]
    assert [deal.entry for deal in deals] == [0, 0, 1, 1]
    assert sum(deal.volume for deal in deals if deal.entry == 0) == pytest.approx(1)
    assert sum(deal.volume for deal in deals if deal.entry == 1) == pytest.approx(1)
    assert all(deal.position_id == 777 for deal in deals)
    await gateway.disconnect()
