"""Unit tests for FastAPI Web API endpoints."""

from __future__ import annotations

import pytest
from types import SimpleNamespace
from fastapi.testclient import TestClient

from src.web import server as server_module
from src.web.server import app


@pytest.fixture(autouse=True)
def clean_runtime_control():
    from src.core.runtime_control import _path
    yield
    p = _path()
    if p.exists():
        p.unlink()


@pytest.fixture
def client():
    with TestClient(app) as test_client:
        yield test_client


def test_api_status(client):
    response = client.get("/api/status")
    assert response.status_code == 200
    data = response.json()
    assert data["ok"] is True
    assert "mode" in data
    assert "venue" in data
    assert "account" in data
    for field in (
        "execution_mode", "worker_state", "cycle_count", "cycle_errors",
        "candidate_count", "last_candidate", "last_candidate_symbol",
        "last_candidate_score", "last_decision", "last_decision_at",
        "last_reason", "last_error",
    ):
        assert field in data


def test_api_watchlist(client):
    response = client.get("/api/watchlist")
    assert response.status_code == 200
    data = response.json()
    assert data["ok"] is True
    assert "btc_report" in data["data"]
    assert "candidates" in data["data"]


def test_api_readiness(client):
    response = client.get("/api/readiness")
    assert response.status_code == 200
    data = response.json()
    assert data["ok"] is True
    assert "readiness_score" in data
    assert "checks" in data
    assert isinstance(data["checks"], list)


def test_api_positions(client):
    response = client.get("/api/positions")
    assert response.status_code == 200
    data = response.json()
    assert data["ok"] is True
    assert "positions" in data
    assert isinstance(data["positions"], list)


def test_api_candles(client):
    response = client.get("/api/candles/BTCUSDT?timeframe=5m&count=10")
    assert response.status_code == 200
    data = response.json()
    assert data["ok"] is True
    assert data["symbol"] == "BTCUSDT"
    assert "candles" in data


def test_api_council_latest(client):
    response = client.get("/api/council/latest")
    assert response.status_code == 200
    data = response.json()
    assert data["ok"] is True
    assert "latest" in data
    assert "decision" in data["latest"]
    assert "score" in data["latest"]
    assert data["latest"]["vision_verdict"] is None
    assert "timestamp" in data["latest"]


def test_api_history(client):
    response = client.get("/api/history?limit=5")
    assert response.status_code == 200
    data = response.json()
    assert data["ok"] is True
    assert "trades" in data
    assert isinstance(data["trades"], list)


def test_api_actions_mode(client):
    response = client.post("/api/actions/mode", json={"mode": "PAPER", "armed": False})
    assert response.status_code == 200
    data = response.json()
    assert data["ok"] is True
    assert data["mode"] == "PAPER"


def test_api_actions_panic(client):
    response = client.post("/api/actions/panic")
    assert response.status_code == 200
    data = response.json()
    assert data["ok"] is True
    assert "closed_count" in data


def test_api_actions_scan(client):
    response = client.post("/api/actions/scan")
    assert response.status_code == 200
    data = response.json()
    assert data["ok"] is True


def test_api_pro_metrics(client):
    response = client.get("/api/analytics/pro-metrics?symbol=BTCUSDT")
    assert response.status_code == 200
    data = response.json()
    assert data["ok"] is True
    assert data["symbol"] == "BTCUSDT"
    assert "financials" in data
    assert "legs" in data
    assert len(data["legs"]) == 4
    assert "calendar_days" in data
    assert len(data["calendar_days"]) == 31
    assert "execution_quality" in data
    assert data["execution_quality"]["avg_latency_ms"] is None
    assert data["execution_quality"]["slip_over_3_pct"] is None
    assert data["execution_quality"]["total_fills"] is None
    assert all(leg["fills"] is None for leg in data["execution_quality"]["legs"])
    assert data["execution_quality"]["hourly_distribution"] == []
    assert data["equity_summary"]["lost_to_slip"] is None
    assert "equity_summary" in data
    assert "guards" in data


def test_api_trade_markers(client):
    response = client.get("/api/trades/markers?symbol=BTCUSDT")
    assert response.status_code == 200
    data = response.json()
    assert data["ok"] is True
    assert "markers" in data
    assert "trades" in data


def test_api_simulate_trade(client):
    response = client.post(
        "/api/actions/simulate_trade",
        json={"symbol": "BTCUSDT", "direction": "BUY", "strategy": "CHoCH + Order Block"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["ok"] is True
    assert "ticket" in data
    assert data["ticket"] is not None
    assert "sl" in data
    assert "tp" in data


def test_binance_demo_credential_check_uses_current_endpoint(client, monkeypatch):
    instances = []

    class FakeGateway:
        def __init__(self, **kwargs):
            instances.append(kwargs)

        async def test_testnet_account_access(self):
            return SimpleNamespace(balance=5000.0, equity=5000.0, currency="USDT")

        async def disconnect(self):
            pass

    monkeypatch.setattr(server_module, "BinanceGateway", FakeGateway)
    response = client.post("/api/settings/binance/test", json={
        "binance_mode": "testnet",
        "binance_base_url": "https://demo-fapi.binance.com",
        "binance_api_key": "demo-key-value",
        "binance_api_secret": "demo-secret-value",
    })

    assert response.status_code == 200
    assert response.json()["ok"] is True
    assert response.json()["balance"] == 5000.0
    assert instances[0]["base_url"] == "https://demo-fapi.binance.com"
    assert "demo-key-value" not in response.text
    assert "demo-secret-value" not in response.text


def test_binance_demo_credential_check_exposes_safe_exchange_code(client, monkeypatch):
    class FakeGateway:
        def __init__(self, **_kwargs):
            pass

        async def test_testnet_account_access(self):
            import httpx
            response = httpx.Response(
                401,
                json={"code": -2015, "msg": "Invalid API-key, secret must not be exposed."},
                request=httpx.Request("GET", "https://demo-fapi.binance.com/fapi/v2/account"),
            )
            raise httpx.HTTPStatusError("Unauthorized", request=response.request, response=response)

        async def disconnect(self):
            pass

    monkeypatch.setattr(server_module, "BinanceGateway", FakeGateway)
    response = client.post("/api/settings/binance/test", json={
        "binance_mode": "testnet",
        "binance_base_url": "https://demo-fapi.binance.com",
        "binance_api_key": "demo-key-value",
        "binance_api_secret": "demo-secret-value",
    })

    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is False
    assert body["exchange_code"] == -2015
    assert "Futures Demo API Management" in body["message"]
    assert "Invalid API-key" not in response.text
    assert "demo-secret-value" not in response.text


def test_binance_live_credential_check_uses_separate_live_key_read_only(client, monkeypatch):
    instances = []

    class FakeGateway:
        def __init__(self, **kwargs):
            instances.append(kwargs)

        async def test_live_account_access(self):
            return SimpleNamespace(balance=250.0, equity=252.0, currency="USDT")

        async def disconnect(self):
            pass

    monkeypatch.setattr(server_module, "BinanceGateway", FakeGateway)
    response = client.post("/api/settings/binance/test", json={
        "binance_mode": "live",
        "binance_base_url": "https://fapi.binance.com",
        "binance_live_api_key": "live-key-value",
        "binance_live_api_secret": "live-secret-value",
        "binance_demo_api_key": "demo-key-value",
        "binance_demo_api_secret": "demo-secret-value",
    })

    assert response.status_code == 200
    assert response.json()["ok"] is True
    assert "อ่านข้อมูลบัญชีเท่านั้น" in response.json()["message"]
    assert "balance" not in response.json()
    assert "equity" not in response.json()
    assert instances[0] == {
        "base_url": "https://fapi.binance.com",
        "api_key": "live-key-value",
        "api_secret": "live-secret-value",
    }
    assert "live-key-value" not in response.text
    assert "live-secret-value" not in response.text
    assert "demo-secret-value" not in response.text


def test_live_credential_check_never_falls_back_to_demo_key(client, monkeypatch, tmp_path):
    from src.core.runtime_settings import save_runtime_settings

    monkeypatch.setenv("RUNTIME_SETTINGS_PATH", str(tmp_path / "runtime_settings.json"))
    monkeypatch.setenv("RUNTIME_CONTROL_PATH", str(tmp_path / "runtime_control.json"))
    monkeypatch.setenv("BINANCE_LIVE_API_KEY", "")
    monkeypatch.setenv("BINANCE_LIVE_API_SECRET", "")
    save_runtime_settings({
        "binance_mode": "testnet",
        "binance_demo_api_key": "demo-key-value",
        "binance_demo_api_secret": "demo-secret-value",
    })

    class UnexpectedGateway:
        def __init__(self, **_kwargs):
            pytest.fail("a Live gateway must not be created with Demo credentials")

    monkeypatch.setattr(server_module, "BinanceGateway", UnexpectedGateway)
    response = client.post("/api/settings/binance/test", json={
        "binance_mode": "live",
        "binance_base_url": "https://fapi.binance.com",
        "binance_demo_api_key": "demo-key-value",
        "binance_demo_api_secret": "demo-secret-value",
    })

    assert response.status_code == 200
    assert response.json()["ok"] is False
    assert "Live API Key" in response.json()["message"]


def test_live_credential_check_rejects_unapproved_host_before_request(client, monkeypatch):
    class UnexpectedGateway:
        def __init__(self, **_kwargs):
            pytest.fail("unapproved Binance host must be rejected before network access")

    monkeypatch.setattr(server_module, "BinanceGateway", UnexpectedGateway)
    response = client.post("/api/settings/binance/test", json={
        "binance_mode": "live",
        "binance_base_url": "https://fapi.binance.com.evil.example",
        "binance_live_api_key": "live-key-value",
        "binance_live_api_secret": "live-secret-value",
    })
    assert response.status_code == 200
    assert response.json()["ok"] is False
    assert "เฉพาะ https://fapi.binance.com" in response.json()["message"]


