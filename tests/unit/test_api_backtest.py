"""Unit tests for /api/backtest/run endpoint."""

import pytest
from httpx import ASGITransport, AsyncClient
from src.web.server import app


@pytest.mark.asyncio
async def test_api_backtest_run_success():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        res = await client.post(
            "/api/backtest/run",
            json={
                "strategy_id": "choch_orderblock",
                "symbol": "BTCUSDT",
                "timeframe": "5m",
                "candle_count": 150,
                "initial_balance": 10000.0,
                "risk_pct": 0.01,
                "spread_pips": 2.0,
            },
        )
        assert res.status_code == 200
        data = res.json()
        assert data["ok"] is True
        assert "summary" in data
        assert data["summary"]["symbol"] == "BTCUSDT"
        assert "win_rate" in data["summary"]
        assert "equity_curve" in data
        assert isinstance(data["equity_curve"], list)
        assert len(data["equity_curve"]) > 0
