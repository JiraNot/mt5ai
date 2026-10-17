"""Unit tests for unified runtime settings manager."""

from __future__ import annotations

import os
import pytest

from src.core.runtime_settings import (
    get_runtime_settings,
    is_masked,
    mask_secret,
    save_runtime_settings,
)


def _configure_path(tmp_path, monkeypatch):
    path = tmp_path / "runtime_settings.json"
    control_path = tmp_path / "runtime_control.json"
    monkeypatch.setenv("RUNTIME_SETTINGS_PATH", str(path))
    monkeypatch.setenv("RUNTIME_CONTROL_PATH", str(control_path))
    monkeypatch.setenv("DASHBOARD_PASSWORD", "test-pass-2026")
    return path


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


def test_mask_secret():
    assert mask_secret("") == ""
    assert mask_secret("short") == "••••••••"
    assert mask_secret("1234567890abcdef") == "1234••••••••cdef"
    assert is_masked("1234••••••••cdef") is True
    assert is_masked("plain_api_key_here") is False


def test_save_and_read_runtime_settings(tmp_path, monkeypatch):
    path = _configure_path(tmp_path, monkeypatch)

    saved = save_runtime_settings({
        "trading_mode": "demo",
        "primary_symbol": "ETHUSDT",
        "risk_per_trade_pct": 0.02,
        "max_daily_loss_pct": 0.05,
        "binance_api_key": "my-secret-key-123456",
        "binance_api_secret": "my-secret-secret-654321",
    })

    assert saved["trading_mode"] == "demo"
    assert saved["primary_symbol"] == "ETHUSDT"
    assert saved["risk_per_trade_pct"] == 0.02
    assert saved["max_daily_loss_pct"] == 0.05
    # Masked in returned display
    assert is_masked(saved["binance_api_key"])
    assert "my-secret-key-123456" not in path.read_text(encoding="utf-8")

    # Read unmasked
    from src.core.runtime_settings import get_runtime_settings
    raw = get_runtime_settings(mask_secrets=False)
    assert raw["binance_api_key"] == "my-secret-key-123456"
    assert raw["binance_api_secret"] == "my-secret-secret-654321"


def test_masked_secret_does_not_overwrite(tmp_path, monkeypatch):
    _configure_path(tmp_path, monkeypatch)

    save_runtime_settings({
        "binance_api_key": "original-key-12345",
    })

    # User submits form with masked value
    save_runtime_settings({
        "binance_api_key": "orig••••••••2345",
        "primary_symbol": "SOLUSDT",
    })

    raw = get_runtime_settings(mask_secrets=False)
    assert raw["binance_api_key"] == "original-key-12345"
    assert raw["primary_symbol"] == "SOLUSDT"


def test_clear_secret_with_empty_string(tmp_path, monkeypatch):
    _configure_path(tmp_path, monkeypatch)

    save_runtime_settings({
        "binance_api_key": "original-key-12345",
    })

    save_runtime_settings({
        "binance_api_key": "",
    })

    raw = get_runtime_settings(mask_secrets=False)
    assert raw["binance_api_key"] == ""
