"""Encrypted, dashboard-managed credentials for AI providers.

Provider secrets are never returned by the public status helpers.  They are
encrypted with the dashboard password before being written to the shared
runtime volume, while legacy environment variables remain read-only fallbacks
for a safe migration.
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
import tempfile
from pathlib import Path
from typing import Any

from cryptography.fernet import Fernet, InvalidToken


DEFAULT_OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
DEFAULT_OPENROUTER_SITE_URL = "https://trade.onetapweb.com"
DEFAULT_OPENROUTER_APP_NAME = "Freebuff Trading"
DEFAULT_OPENAI_MODEL = "gpt-4o"
DEFAULT_GEMINI_CLI_BIN = "agy"
_MAX_SECRET_LENGTH = 65_536
_MAX_VALUE_LENGTH = 500
_SECRET_FIELDS = {
    "codex": {"auth_json"},
    "openai": {"api_key"},
    "gemini": {"api_key"},
    "openrouter": {"api_key"},
}
_KNOWN_FIELDS = {
    "codex": {"auth_json"},
    "openai": {"api_key", "model"},
    "gemini": {"api_key", "cli_bin"},
    "openrouter": {"api_key", "base_url", "site_url", "app_name"},
}


def _path() -> Path:
    configured = os.getenv("PROVIDER_SETTINGS_PATH")
    if configured:
        return Path(configured)
    production_dir = Path("/app/data")
    if production_dir.is_dir():
        return production_dir / "provider_settings.json"
    return Path("provider_settings.json")


def _fernet() -> Fernet:
    # This password already protects the dashboard. Keeping provider secrets
    # encrypted with it avoids introducing a second provider-secret ENV value.
    password = os.getenv("DASHBOARD_PASSWORD", "freebuff2026").strip()
    key_material = hashlib.sha256(
        f"freebuff-provider-settings:v1:{password}".encode("utf-8")
    ).digest()
    return Fernet(base64.urlsafe_b64encode(key_material))


def _read_persisted() -> dict[str, dict[str, str]]:
    try:
        encrypted = _path().read_bytes()
        value = json.loads(_fernet().decrypt(encrypted).decode("utf-8"))
    except (FileNotFoundError, OSError, InvalidToken, UnicodeDecodeError, json.JSONDecodeError):
        return {}
    if not isinstance(value, dict):
        return {}
    result: dict[str, dict[str, str]] = {}
    for provider, fields in value.items():
        if provider not in _KNOWN_FIELDS or not isinstance(fields, dict):
            continue
        result[provider] = {
            name: field_value.strip()
            for name, field_value in fields.items()
            if name in _KNOWN_FIELDS[provider] and isinstance(field_value, str)
        }
    return result


def _write_persisted(value: dict[str, dict[str, str]]) -> None:
    path = _path()
    path.parent.mkdir(parents=True, exist_ok=True)
    encrypted = _fernet().encrypt(
        json.dumps(value, ensure_ascii=False, sort_keys=True).encode("utf-8")
    )
    fd, temporary_name = tempfile.mkstemp(prefix="provider_settings.", dir=path.parent)
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "wb") as handle:
            handle.write(encrypted)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_name, path)
        os.chmod(path, 0o600)
    finally:
        try:
            os.unlink(temporary_name)
        except FileNotFoundError:
            pass


def _defaults() -> dict[str, dict[str, str]]:
    return {
        "codex": {"auth_json": os.getenv("CODEX_AUTH_JSON", "").strip()},
        "openai": {
            "api_key": os.getenv("OPENAI_API_KEY", "").strip(),
            "model": os.getenv("OPENAI_MODEL", DEFAULT_OPENAI_MODEL).strip() or DEFAULT_OPENAI_MODEL,
        },
        "gemini": {
            "api_key": os.getenv("GEMINI_API_KEY", "").strip(),
            "cli_bin": os.getenv("AI_CLI_BIN", DEFAULT_GEMINI_CLI_BIN).strip() or DEFAULT_GEMINI_CLI_BIN,
        },
        "openrouter": {
            "api_key": os.getenv("OPENROUTER_API_KEY", "").strip(),
            "base_url": os.getenv("OPENROUTER_BASE_URL", DEFAULT_OPENROUTER_BASE_URL).strip() or DEFAULT_OPENROUTER_BASE_URL,
            "site_url": os.getenv("OPENROUTER_SITE_URL", DEFAULT_OPENROUTER_SITE_URL).strip() or DEFAULT_OPENROUTER_SITE_URL,
            "app_name": os.getenv("OPENROUTER_APP_NAME", DEFAULT_OPENROUTER_APP_NAME).strip() or DEFAULT_OPENROUTER_APP_NAME,
        },
    }


def get_provider_settings() -> dict[str, dict[str, str]]:
    """Return runtime settings, prioritizing dashboard values over legacy ENV."""
    result = _defaults()
    for provider, fields in _read_persisted().items():
        result[provider].update(fields)
    return result


def _validate(provider: str, field: str, value: str) -> str:
    if provider not in _KNOWN_FIELDS or field not in _KNOWN_FIELDS[provider]:
        raise ValueError(f"Unsupported provider setting: {provider}.{field}")
    if not isinstance(value, str):
        raise ValueError(f"{provider}.{field} must be text")
    normalized = value.strip()
    limit = _MAX_SECRET_LENGTH if field in _SECRET_FIELDS.get(provider, set()) else _MAX_VALUE_LENGTH
    if not normalized or len(normalized) > limit:
        raise ValueError(f"{provider}.{field} has an invalid length")
    if field.endswith("url") and not normalized.startswith(("https://", "http://")):
        raise ValueError(f"{provider}.{field} must be an HTTP(S) URL")
    if provider == "codex" and field == "auth_json":
        try:
            parsed = json.loads(normalized)
        except json.JSONDecodeError as exc:
            raise ValueError("codex.auth_json must be valid JSON") from exc
        if not isinstance(parsed, dict):
            raise ValueError("codex.auth_json must be a JSON object")
    return normalized


def save_provider_settings(provider: str, **changes: str | None) -> None:
    """Persist validated provider changes. ``None`` leaves a field untouched."""
    if provider not in _KNOWN_FIELDS:
        raise ValueError(f"Unsupported provider: {provider}")
    unknown = set(changes) - _KNOWN_FIELDS[provider]
    if unknown:
        raise ValueError(f"Unsupported provider fields: {sorted(unknown)}")
    current = _read_persisted()
    provider_values = current.setdefault(provider, {})
    for field, value in changes.items():
        if value is not None:
            provider_values[field] = _validate(provider, field, value)
    _write_persisted(current)


def clear_provider_secret(provider: str, field: str) -> None:
    """Explicitly remove a dashboard-stored secret so the provider is disabled."""
    if field not in _SECRET_FIELDS.get(provider, set()):
        raise ValueError(f"Unsupported provider secret: {provider}.{field}")
    current = _read_persisted()
    # Persist an empty override so a legacy ENV fallback cannot silently revive
    # a credential that an operator deliberately removed in the dashboard.
    current.setdefault(provider, {})[field] = ""
    _write_persisted(current)


def provider_status() -> dict[str, dict[str, str | bool]]:
    """Return display-safe provider state; this function never exposes secrets."""
    persisted = _read_persisted()
    settings = get_provider_settings()

    def source(provider: str, field: str) -> str:
        if persisted.get(provider, {}).get(field):
            return "dashboard"
        return "environment" if settings[provider].get(field) else "not configured"

    return {
        "codex": {"configured": bool(settings["codex"]["auth_json"]), "source": source("codex", "auth_json")},
        "openai": {"configured": bool(settings["openai"]["api_key"]), "source": source("openai", "api_key")},
        "gemini": {"configured": bool(settings["gemini"]["api_key"]), "source": source("gemini", "api_key")},
        "openrouter": {"configured": bool(settings["openrouter"]["api_key"]), "source": source("openrouter", "api_key")},
    }


def sync_codex_auth_file() -> bool:
    """Materialize a dashboard-managed Codex session for the local CLI only."""
    auth_json = get_provider_settings()["codex"]["auth_json"]
    if not auth_json:
        return False
    target = Path.home() / ".codex" / "auth.json"
    target.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    fd, temporary_name = tempfile.mkstemp(prefix="auth.", dir=target.parent)
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(auth_json)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_name, target)
        os.chmod(target, 0o600)
    finally:
        try:
            os.unlink(temporary_name)
        except FileNotFoundError:
            pass
    return True
