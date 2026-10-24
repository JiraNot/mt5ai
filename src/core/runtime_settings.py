"""Unified runtime settings manager.

Persists configuration to the shared runtime volume (/app/data or local runtime_settings.json)
so operators can configure all trading parameters, risk limits, exchange credentials, AI providers,
and notification settings dynamically from the web terminal without editing .env files or restarting containers.
"""

from __future__ import annotations

import base64
import hashlib
import json
import logging
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from cryptography.fernet import Fernet, InvalidToken

logger = logging.getLogger(__name__)

_SECRET_FIELDS = {
    "binance_api_key",
    "binance_api_secret",
    "openai_api_key",
    "gemini_api_key",
    "openrouter_api_key",
    "telegram_bot_token",
}

DEFAULT_RUNTIME_SETTINGS: dict[str, Any] = {
    # Trading & Execution
    "trading_mode": "paper",
    "primary_symbol": "BTCUSDT",
    "active_symbols": ["BTCUSDT", "ETHUSDT", "SOLUSDT"],
    "paper_initial_balance": 100000.0,
    # Risk Management
    "risk_per_trade_pct": 0.01,
    "max_daily_loss_pct": 0.03,
    "max_open_positions": 3,
    "min_rr": 2.0,
    "entry_min_score": 70,
    "max_consecutive_losses": 3,
    "emergency_stop_loss_pct": 0.05,
    "news_filter_enabled": True,
    # Binance Exchange
    "binance_mode": "paper",
    "binance_base_url": "https://testnet.binancefuture.com",
    "binance_api_key": "",
    "binance_api_secret": "",
    # AI Providers & Vision
    "ai_provider": "codex",
    "openai_api_key": "",
    "openai_model": "gpt-4o",
    "gemini_api_key": "",
    "openrouter_api_key": "",
    "openrouter_model": "deepseek/deepseek-chat",
    "vision_provider": "deterministic",
    "vision_min_score": 65,
    "volume_filter_enabled": True,
    "rsi_filter_enabled": True,
    # Telegram
    "telegram_enabled": False,
    "telegram_bot_token": "",
    "telegram_chat_id": "",
}


def _path() -> Path:
    configured = os.getenv("RUNTIME_SETTINGS_PATH")
    if configured:
        return Path(configured)
    production_dir = Path("/app/data")
    if production_dir.is_dir():
        return production_dir / "runtime_settings.json"
    local_data = Path("data")
    if local_data.is_dir():
        return local_data / "runtime_settings.json"
    return Path("runtime_settings.json")


def _fernet() -> Fernet:
    password = os.getenv("DASHBOARD_PASSWORD", "freebuff2026").strip()
    key_material = hashlib.sha256(
        f"freebuff-app-settings:v1:{password}".encode("utf-8")
    ).digest()
    return Fernet(base64.urlsafe_b64encode(key_material))


def _read_raw_file() -> dict[str, Any]:
    path = _path()
    if not path.is_file():
        return {}
    try:
        raw_text = path.read_text(encoding="utf-8")
        data = json.loads(raw_text)
        if not isinstance(data, dict):
            return {}
        # Decrypt secrets
        fernet = _fernet()
        secrets = data.get("_secrets", {})
        for field_name in _SECRET_FIELDS:
            encrypted_val = secrets.get(field_name)
            if encrypted_val:
                try:
                    decrypted = fernet.decrypt(encrypted_val.encode("utf-8")).decode("utf-8")
                    data[field_name] = decrypted
                except (InvalidToken, Exception):
                    data[field_name] = ""
        return data
    except Exception as exc:
        logger.debug("Failed reading runtime settings from %s: %s", path, exc)
        return {}


def _write_raw_file(data: dict[str, Any]) -> None:
    path = _path()
    path.parent.mkdir(parents=True, exist_ok=True)
    fernet = _fernet()

    payload = dict(data)
    secrets: dict[str, str] = {}
    for field_name in _SECRET_FIELDS:
        val = payload.pop(field_name, None)
        if val and isinstance(val, str) and val.strip():
            encrypted_bytes = fernet.encrypt(val.strip().encode("utf-8"))
            secrets[field_name] = encrypted_bytes.decode("utf-8")
    payload["_secrets"] = secrets
    payload["updated_at"] = datetime.now(timezone.utc).isoformat()

    fd, temporary_name = tempfile.mkstemp(prefix="runtime_settings.", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2, sort_keys=True)
        os.replace(temporary_name, path)
    finally:
        try:
            os.unlink(temporary_name)
        except FileNotFoundError:
            pass


def mask_secret(secret: str | None) -> str:
    """Mask a secret key for display in UI (e.g. sk-****4f21)."""
    if not secret or not isinstance(secret, str):
        return ""
    s = secret.strip()
    if not s:
        return ""
    if len(s) <= 8:
        return "••••••••"
    return f"{s[:4]}••••••••{s[-4:]}"


def is_masked(value: str | None) -> bool:
    """Check if value is a masked placeholder from the UI."""
    if not value or not isinstance(value, str):
        return False
    return "••••" in value or "****" in value


def get_runtime_settings(mask_secrets: bool = True) -> dict[str, Any]:
    """Return effective runtime settings, falling back to defaults/env."""
    persisted = _read_raw_file()
    result = dict(DEFAULT_RUNTIME_SETTINGS)

    # Fallback to existing config / environment variables if not explicitly saved
    from src.core.config import settings

    result["trading_mode"] = persisted.get("trading_mode", os.getenv("TRADING_MODE", settings.trading_mode).lower())
    result["primary_symbol"] = persisted.get("primary_symbol", os.getenv("PRIMARY_SYMBOL", settings.primary_symbol)).upper()
    result["active_symbols"] = persisted.get("active_symbols", ["BTCUSDT", "ETHUSDT", "SOLUSDT"])
    result["paper_initial_balance"] = float(persisted.get("paper_initial_balance", settings.paper_initial_balance))

    result["risk_per_trade_pct"] = float(persisted.get("risk_per_trade_pct", settings.risk.risk_per_trade_pct))
    result["max_daily_loss_pct"] = float(persisted.get("max_daily_loss_pct", settings.risk.max_daily_loss_pct))
    result["max_open_positions"] = int(persisted.get("max_open_positions", settings.risk.max_concurrent_positions))
    result["min_rr"] = float(persisted.get("min_rr", settings.risk.min_rr))
    if "entry_min_score" in persisted:
        result["entry_min_score"] = int(persisted["entry_min_score"])
    else:
        from src.core.runtime_control import get_candidate_policy
        result["entry_min_score"] = int(get_candidate_policy()["immediate_min_score"])
    result["max_consecutive_losses"] = int(persisted.get("max_consecutive_losses", settings.risk.max_consecutive_losses))
    result["emergency_stop_loss_pct"] = float(persisted.get("emergency_stop_loss_pct", settings.risk.emergency_stop_loss_pct))
    result["news_filter_enabled"] = bool(persisted.get("news_filter_enabled", settings.risk.news_filter_enabled))

    result["binance_mode"] = persisted.get("binance_mode", os.getenv("BINANCE_MODE", settings.binance_mode)).lower()
    result["binance_base_url"] = persisted.get("binance_base_url", os.getenv("BINANCE_BASE_URL", settings.binance_base_url))
    result["binance_api_key"] = persisted.get("binance_api_key", os.getenv("BINANCE_API_KEY", settings.binance_api_key))
    result["binance_api_secret"] = persisted.get("binance_api_secret", os.getenv("BINANCE_API_SECRET", settings.binance_api_secret))

    result["ai_provider"] = persisted.get("ai_provider", "codex")
    result["openai_api_key"] = persisted.get("openai_api_key", os.getenv("OPENAI_API_KEY", ""))
    result["openai_model"] = persisted.get("openai_model", "gpt-4o")
    result["gemini_api_key"] = persisted.get("gemini_api_key", os.getenv("GEMINI_API_KEY", ""))
    result["openrouter_api_key"] = persisted.get("openrouter_api_key", os.getenv("OPENROUTER_API_KEY", ""))
    result["openrouter_model"] = persisted.get("openrouter_model", "deepseek/deepseek-chat")
    result["vision_provider"] = persisted.get("vision_provider", "deterministic")
    result["vision_min_score"] = int(persisted.get("vision_min_score", 65))
    result["volume_filter_enabled"] = bool(persisted.get("volume_filter_enabled", True))
    result["rsi_filter_enabled"] = bool(persisted.get("rsi_filter_enabled", True))

    result["telegram_enabled"] = bool(persisted.get("telegram_enabled", bool(os.getenv("TELEGRAM_BOT_TOKEN"))))
    result["telegram_bot_token"] = persisted.get("telegram_bot_token", os.getenv("TELEGRAM_BOT_TOKEN", ""))
    result["telegram_chat_id"] = persisted.get("telegram_chat_id", os.getenv("TELEGRAM_CHAT_ID", ""))
    result["updated_at"] = persisted.get("updated_at")

    if mask_secrets:
        for secret_key in _SECRET_FIELDS:
            result[secret_key] = mask_secret(result.get(secret_key))

    return result


def save_runtime_settings(changes: dict[str, Any]) -> dict[str, Any]:
    """Validate and persist runtime settings changes."""
    current = get_runtime_settings(mask_secrets=False)
    updated = dict(current)

    # Validate and apply non-secret changes
    if "trading_mode" in changes:
        mode = str(changes["trading_mode"]).lower().strip()
        if mode in ("paper", "demo", "live"):
            updated["trading_mode"] = mode
            # Also keep runtime_control in sync
            from src.core.runtime_control import set_runtime_trading_mode
            set_runtime_trading_mode(mode)

    if "primary_symbol" in changes:
        sym = str(changes["primary_symbol"]).upper().strip()
        if sym:
            updated["primary_symbol"] = sym

    if "active_symbols" in changes:
        symbols_raw = changes["active_symbols"]
        if isinstance(symbols_raw, list):
            updated["active_symbols"] = [str(s).upper().strip() for s in symbols_raw if str(s).strip()]
        elif isinstance(symbols_raw, str):
            updated["active_symbols"] = [s.strip().upper() for s in symbols_raw.split(",") if s.strip()]

    if "paper_initial_balance" in changes:
        try:
            val = float(changes["paper_initial_balance"])
            if val > 0:
                updated["paper_initial_balance"] = val
        except (ValueError, TypeError):
            pass

    if "risk_per_trade_pct" in changes:
        try:
            val = float(changes["risk_per_trade_pct"])
            if 0.001 <= val <= 0.10:
                updated["risk_per_trade_pct"] = val
        except (ValueError, TypeError):
            pass

    if "max_daily_loss_pct" in changes:
        try:
            val = float(changes["max_daily_loss_pct"])
            if 0.005 <= val <= 0.20:
                updated["max_daily_loss_pct"] = val
        except (ValueError, TypeError):
            pass

    if "max_open_positions" in changes:
        try:
            val = int(changes["max_open_positions"])
            if 1 <= val <= 10:
                updated["max_open_positions"] = val
        except (ValueError, TypeError):
            pass

    if "max_consecutive_losses" in changes:
        try:
            val = int(changes["max_consecutive_losses"])
            if 1 <= val <= 10:
                updated["max_consecutive_losses"] = val
        except (ValueError, TypeError):
            pass

    if "emergency_stop_loss_pct" in changes:
        try:
            val = float(changes["emergency_stop_loss_pct"])
            if 0.01 <= val <= 0.20:
                updated["emergency_stop_loss_pct"] = val
        except (ValueError, TypeError):
            pass

    if "news_filter_enabled" in changes:
        updated["news_filter_enabled"] = bool(changes["news_filter_enabled"])

    if "min_rr" in changes:
        try:
            val = float(changes["min_rr"])
            if 1.0 <= val <= 10.0:
                updated["min_rr"] = val
        except (ValueError, TypeError):
            pass

    if "entry_min_score" in changes:
        try:
            val = int(changes["entry_min_score"])
            if 50 <= val <= 90:
                updated["entry_min_score"] = val
                from src.core.runtime_control import get_candidate_policy, set_candidate_policy
                policy = get_candidate_policy()
                set_candidate_policy(
                    observe_min_score=min(policy["observe_min_score"], val),
                    batch_min_score=val,
                    immediate_min_score=val,
                )
        except (ValueError, TypeError):
            pass

    if "binance_mode" in changes:
        mode = str(changes["binance_mode"]).lower().strip()
        if mode in ("paper", "testnet", "live"):
            updated["binance_mode"] = mode

    if "binance_base_url" in changes:
        url = str(changes["binance_base_url"]).strip()
        if url.startswith(("http://", "https://")):
            updated["binance_base_url"] = url

    if "ai_provider" in changes:
        prov = str(changes["ai_provider"]).lower().strip()
        if prov in ("codex", "openai", "gemini", "openrouter"):
            updated["ai_provider"] = prov

    if "openai_model" in changes:
        updated["openai_model"] = str(changes["openai_model"]).strip()

    if "openrouter_model" in changes:
        updated["openrouter_model"] = str(changes["openrouter_model"]).strip()

    if "vision_provider" in changes:
        vp = str(changes["vision_provider"]).lower().strip()
        if vp in ("deterministic", "gpt-4o", "claude-3-5", "deepseek-vision"):
            updated["vision_provider"] = vp

    if "vision_min_score" in changes:
        try:
            val = int(changes["vision_min_score"])
            if 0 <= val <= 100:
                updated["vision_min_score"] = val
        except (ValueError, TypeError):
            pass

    if "volume_filter_enabled" in changes:
        updated["volume_filter_enabled"] = bool(changes["volume_filter_enabled"])

    if "rsi_filter_enabled" in changes:
        updated["rsi_filter_enabled"] = bool(changes["rsi_filter_enabled"])

    if "telegram_enabled" in changes:
        updated["telegram_enabled"] = bool(changes["telegram_enabled"])

    if "telegram_chat_id" in changes:
        updated["telegram_chat_id"] = str(changes["telegram_chat_id"]).strip()

    # Handle secret fields: only update if provided and not masked
    for secret_key in _SECRET_FIELDS:
        if secret_key in changes:
            val = changes[secret_key]
            if val is not None:
                val_str = str(val).strip()
                if val_str == "":
                    # Empty string explicitly clears the secret
                    updated[secret_key] = ""
                elif not is_masked(val_str):
                    # Real new secret
                    updated[secret_key] = val_str

    # Write to storage
    _write_raw_file(updated)

    # Immediately apply to in-memory settings
    _sync_to_global_settings(updated)

    return get_runtime_settings(mask_secrets=True)


def _sync_to_global_settings(cfg: dict[str, Any]) -> None:
    """Keep in-memory config.settings synchronized with runtime changes."""
    try:
        from src.core.config import settings
        if "binance_mode" in cfg:
            settings.binance_mode = cfg["binance_mode"]
        if "binance_base_url" in cfg:
            settings.binance_base_url = cfg["binance_base_url"]
        if "binance_api_key" in cfg:
            settings.binance_api_key = cfg["binance_api_key"]
        if "binance_api_secret" in cfg:
            settings.binance_api_secret = cfg["binance_api_secret"]
        if "trading_mode" in cfg:
            settings.trading_mode = cfg["trading_mode"]
        if "primary_symbol" in cfg:
            settings.primary_symbol = cfg["primary_symbol"]
            settings.binance_symbol = cfg["primary_symbol"]
        if "risk_per_trade_pct" in cfg:
            settings.risk.risk_per_trade_pct = cfg["risk_per_trade_pct"]
        if "max_daily_loss_pct" in cfg:
            settings.risk.max_daily_loss_pct = cfg["max_daily_loss_pct"]
        if "max_open_positions" in cfg:
            settings.risk.max_concurrent_positions = cfg["max_open_positions"]
        if "max_consecutive_losses" in cfg:
            settings.risk.max_consecutive_losses = cfg["max_consecutive_losses"]
        if "emergency_stop_loss_pct" in cfg:
            settings.risk.emergency_stop_loss_pct = cfg["emergency_stop_loss_pct"]
        if "news_filter_enabled" in cfg:
            settings.risk.news_filter_enabled = cfg["news_filter_enabled"]
        if "min_rr" in cfg:
            settings.risk.min_rr = cfg["min_rr"]
        if "entry_min_score" in cfg:
            settings.ai.min_combined_score = cfg["entry_min_score"]
        if "paper_initial_balance" in cfg:
            settings.paper_initial_balance = cfg["paper_initial_balance"]
    except Exception as exc:
        logger.debug("Failed syncing settings to in-memory config: %s", exc)
