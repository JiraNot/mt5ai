"""Persistent runtime controls shared by the worker and dashboard."""

from __future__ import annotations

import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

VALID_TRADING_MODES = {"paper", "demo", "live"}


def _path() -> Path:
    configured = os.getenv("RUNTIME_CONTROL_PATH")
    if configured:
        return Path(configured)
    production_dir = Path("/app/data")
    if production_dir.is_dir():
        return production_dir / "runtime_control.json"
    return Path("runtime_control.json")


def _read() -> dict[str, Any]:
    try:
        value = json.loads(_path().read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else {}
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return {}


def has_runtime_control() -> bool:
    """Whether a dashboard setting has explicitly been persisted."""
    return _path().is_file()


def _write(value: dict[str, Any]) -> None:
    path = _path()
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary_name = tempfile.mkstemp(prefix="runtime_control.", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(value, handle, ensure_ascii=False, sort_keys=True)
        os.replace(temporary_name, path)
    finally:
        try:
            os.unlink(temporary_name)
        except FileNotFoundError:
            pass


def normalize_trading_mode(mode: str | None, default: str = "paper") -> str:
    candidate = (mode or default).strip().lower()
    return candidate if candidate in VALID_TRADING_MODES else default.strip().lower()


def get_runtime_trading_mode(default: str = "paper") -> str:
    """Return the persisted mode, falling back to the deployment setting."""
    return normalize_trading_mode(_read().get("trading_mode"), default)


def is_live_armed() -> bool:
    """LIVE requires a separate explicit arm action in the dashboard."""
    control = _read()
    return control.get("trading_mode") == "live" and control.get("live_armed") is True


def set_runtime_trading_mode(mode: str, *, live_armed: bool = False) -> str:
    """Persist a runtime mode and disarm LIVE unless explicitly requested."""
    normalized = normalize_trading_mode(mode)
    _write({
        "trading_mode": normalized,
        "live_armed": normalized == "live" and live_armed,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    })
    return normalized


def arm_live_trading() -> None:
    """Arm LIVE only after the dashboard's explicit confirmation step."""
    control = _read()
    control.update({
        "trading_mode": "live",
        "live_armed": True,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    })
    _write(control)


def disarm_live_trading() -> None:
    """Return to PAPER and remove the LIVE arm."""
    set_runtime_trading_mode("paper")
