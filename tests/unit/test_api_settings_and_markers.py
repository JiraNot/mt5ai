"""Unit tests for /api/settings and /api/trades/markers endpoints."""

import pytest
from httpx import ASGITransport, AsyncClient

from src.web.server import app


@pytest.fixture(autouse=True)
def restore_settings():
    from src.core.config import settings
    orig_risk = settings.risk.risk_per_trade_pct
    orig_sym = settings.primary_symbol
    orig_mode = settings.trading_mode
    yield
    settings.risk.risk_per_trade_pct = orig_risk
    settings.primary_symbol = orig_sym
    settings.trading_mode = orig_mode


@pytest.mark.asyncio
async def test_api_settings_get_and_post(tmp_path, monkeypatch):
    monkeypatch.setenv("RUNTIME_SETTINGS_PATH", str(tmp_path / "runtime_settings.json"))
    monkeypatch.setenv("RUNTIME_CONTROL_PATH", str(tmp_path / "runtime_control.json"))
    monkeypatch.setenv("DASHBOARD_PASSWORD", "test-pass-2026")

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. GET settings
        res = await client.get("/api/settings")
        assert res.status_code == 200
        data = res.json()
        assert data["ok"] is True
        assert "settings" in data

        # 2. POST update settings
        update_payload = {
            "trading_mode": "demo",
            "primary_symbol": "ETHUSDT",
            "risk_per_trade_pct": 0.02,
            "binance_api_key": "new-test-key-12345",
        }
        res_post = await client.post("/api/settings", json=update_payload)
        assert res_post.status_code == 200
        post_data = res_post.json()
        assert post_data["ok"] is True
        assert post_data["settings"]["primary_symbol"] == "ETHUSDT"
        assert post_data["settings"]["risk_per_trade_pct"] == 0.02


@pytest.mark.asyncio
async def test_api_trades_markers(tmp_path, monkeypatch):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        res = await client.get("/api/trades/markers?symbol=BTCUSDT")
        assert res.status_code == 200
        data = res.json()
        assert data["ok"] is True
        assert "markers" in data
        assert "trades" in data
