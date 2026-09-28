"""Contract tests for dashboard-managed AI provider settings."""

from __future__ import annotations

import pytest

from src.core.runtime_provider_settings import (
    clear_provider_secret,
    get_provider_settings,
    provider_status,
    save_provider_settings,
)


def _configure_path(tmp_path, monkeypatch):
    path = tmp_path / "provider_settings.json"
    monkeypatch.setenv("PROVIDER_SETTINGS_PATH", str(path))
    monkeypatch.setenv("DASHBOARD_PASSWORD", "test-dashboard-password")
    return path


def test_dashboard_provider_secret_overrides_env_and_is_encrypted(tmp_path, monkeypatch):
    path = _configure_path(tmp_path, monkeypatch)
    monkeypatch.setenv("OPENROUTER_API_KEY", "legacy-env-key")

    save_provider_settings(
        "openrouter",
        api_key="dashboard-key",
        base_url="https://router.example/v1",
        site_url="https://trade.example",
        app_name="Test Trader",
    )

    settings = get_provider_settings()["openrouter"]
    assert settings["api_key"] == "dashboard-key"
    assert settings["base_url"] == "https://router.example/v1"
    assert "dashboard-key" not in path.read_text(encoding="utf-8")
    assert provider_status()["openrouter"] == {"configured": True, "source": "dashboard"}


def test_blank_secret_is_not_an_accidental_overwrite_and_clear_disables_env_fallback(tmp_path, monkeypatch):
    _configure_path(tmp_path, monkeypatch)
    monkeypatch.setenv("GEMINI_API_KEY", "legacy-env-key")

    save_provider_settings("gemini", api_key="dashboard-key", cli_bin="agy")
    save_provider_settings("gemini", api_key=None, cli_bin="custom-agy")
    assert get_provider_settings()["gemini"]["api_key"] == "dashboard-key"

    clear_provider_secret("gemini", "api_key")
    assert get_provider_settings()["gemini"]["api_key"] == ""
    assert provider_status()["gemini"] == {"configured": False, "source": "not configured"}


@pytest.mark.parametrize(
    ("provider", "changes"),
    [
        ("openrouter", {"base_url": "ftp://invalid"}),
        ("codex", {"auth_json": "not-json"}),
        ("openai", {"unknown": "value"}),
    ],
)
def test_provider_settings_reject_invalid_contract_values(tmp_path, monkeypatch, provider, changes):
    _configure_path(tmp_path, monkeypatch)

    with pytest.raises(ValueError):
        save_provider_settings(provider, **changes)
