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
    orig_binance = (
        settings.binance_mode,
        settings.binance_base_url,
        settings.binance_api_key,
        settings.binance_api_secret,
    )
    yield
    settings.risk.risk_per_trade_pct = orig_risk
    settings.primary_symbol = orig_sym
    settings.trading_mode = orig_mode
    (
        settings.binance_mode,
        settings.binance_base_url,
        settings.binance_api_key,
        settings.binance_api_secret,
    ) = orig_binance


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


def test_demo_and_live_binance_keys_remain_separate(tmp_path, monkeypatch):
    path = _configure_path(tmp_path, monkeypatch)
    demo_key = "demo-api-key-12345"
    demo_secret = "demo-secret-12345"
    live_key = "live-api-key-67890"
    live_secret = "live-secret-67890"

    saved = save_runtime_settings({
        "binance_mode": "testnet",
        "binance_demo_api_key": demo_key,
        "binance_demo_api_secret": demo_secret,
        "binance_live_api_key": live_key,
        "binance_live_api_secret": live_secret,
    })
    assert is_masked(saved["binance_demo_api_key"])
    assert is_masked(saved["binance_live_api_key"])
    assert demo_secret not in path.read_text(encoding="utf-8")
    assert live_secret not in path.read_text(encoding="utf-8")

    raw = get_runtime_settings(mask_secrets=False)
    assert raw["binance_demo_api_key"] == demo_key
    assert raw["binance_demo_api_secret"] == demo_secret
    assert raw["binance_live_api_key"] == live_key
    assert raw["binance_live_api_secret"] == live_secret
    assert raw["binance_api_key"] == demo_key
    assert raw["binance_api_secret"] == demo_secret

    save_runtime_settings({"binance_mode": "live"})
    raw_live = get_runtime_settings(mask_secrets=False)
    assert raw_live["binance_api_key"] == live_key
    assert raw_live["binance_api_secret"] == live_secret
    from src.core.config import settings
    assert settings.binance_api_key == live_key
    assert settings.binance_api_secret == live_secret

    save_runtime_settings({"binance_mode": "testnet"})
    raw_demo = get_runtime_settings(mask_secrets=False)
    assert raw_demo["binance_api_key"] == demo_key
    assert raw_demo["binance_api_secret"] == demo_secret
    assert settings.binance_api_key == demo_key
    assert settings.binance_api_secret == demo_secret


def test_legacy_binance_credentials_migrate_to_demo_only(tmp_path, monkeypatch):
    _configure_path(tmp_path, monkeypatch)
    save_runtime_settings({
        "binance_api_key": "legacy-demo-key-12345",
        "binance_api_secret": "legacy-demo-secret-12345",
    })

    settings = get_runtime_settings(mask_secrets=False)
    assert settings["binance_demo_api_key"] == "legacy-demo-key-12345"
    assert settings["binance_demo_api_secret"] == "legacy-demo-secret-12345"
    assert settings["binance_live_api_key"] == ""
    assert settings["binance_live_api_secret"] == ""


def test_live_environment_credentials_never_fall_back_to_demo_or_selected_global_key(tmp_path, monkeypatch):
    _configure_path(tmp_path, monkeypatch)
    for name in ("BINANCE_DEMO_API_KEY", "BINANCE_DEMO_API_SECRET", "BINANCE_API_KEY", "BINANCE_API_SECRET"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("BINANCE_MODE", "live")
    monkeypatch.setenv("BINANCE_LIVE_API_KEY", "live-env-key-12345")
    monkeypatch.setenv("BINANCE_LIVE_API_SECRET", "live-env-secret-12345")

    result = get_runtime_settings(mask_secrets=False)
    assert result["binance_live_api_key"] == "live-env-key-12345"
    assert result["binance_live_api_secret"] == "live-env-secret-12345"
    assert result["binance_demo_api_key"] == ""
    assert result["binance_demo_api_secret"] == ""
    assert result["binance_api_key"] == "live-env-key-12345"
