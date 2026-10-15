"""Unit tests for FastAPI Web API endpoints."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

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
