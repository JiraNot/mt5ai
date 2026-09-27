"""Persistent runtime controls shared by the worker and dashboard."""

from __future__ import annotations

import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

VALID_TRADING_MODES = {"paper", "demo", "live"}

DEFAULT_CANDIDATE_POLICY = {
    "observe_min_score": 0,
    "batch_min_score": 55,
    "immediate_min_score": 70,
    "max_immediate_per_bar": 3,
    "summary_window": 25,
}


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


def _update(**fields: Any) -> dict[str, Any]:
    control = _read()
    control.update(fields)
    _write(control)
    return control


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
    _update(
        trading_mode=normalized,
        live_armed=normalized == "live" and live_armed,
        updated_at=datetime.now(timezone.utc).isoformat(),
    )
    return normalized


def arm_live_trading() -> None:
    """Arm LIVE only after the dashboard's explicit confirmation step."""
    _update(
        trading_mode="live",
        live_armed=True,
        updated_at=datetime.now(timezone.utc).isoformat(),
    )


def disarm_live_trading() -> None:
    """Return to PAPER and remove the LIVE arm."""
    set_runtime_trading_mode("paper")


def get_candidate_policy() -> dict[str, int]:
    """Return validated candidate triage settings with safe defaults."""
    raw = _read().get("candidate_policy", {})
    if not isinstance(raw, dict):
        raw = {}

    def safe_int(value: Any, default: int) -> int:
        try:
            return int(value)
        except (TypeError, ValueError):
            return default

    policy = {
        key: safe_int(raw.get(key, default), default)
        for key, default in DEFAULT_CANDIDATE_POLICY.items()
    }
    policy["observe_min_score"] = max(0, min(100, policy["observe_min_score"]))
    policy["batch_min_score"] = max(policy["observe_min_score"], min(100, policy["batch_min_score"]))
    policy["immediate_min_score"] = max(policy["batch_min_score"], min(100, policy["immediate_min_score"]))
    policy["max_immediate_per_bar"] = max(0, min(10, policy["max_immediate_per_bar"]))
    policy["summary_window"] = max(5, min(500, policy["summary_window"]))
    return policy


def set_candidate_policy(**changes: int) -> dict[str, int]:
    """Persist only the allow-listed candidate triage settings."""
    unknown = set(changes) - set(DEFAULT_CANDIDATE_POLICY)
    if unknown:
        raise ValueError(f"Unsupported candidate policy fields: {sorted(unknown)}")
    candidate_policy = get_candidate_policy()
    for key, value in changes.items():
        if not isinstance(value, int) or isinstance(value, bool):
            raise ValueError(f"Candidate policy field {key} must be an integer")
        candidate_policy[key] = value
    observe = candidate_policy["observe_min_score"]
    batch = candidate_policy["batch_min_score"]
    immediate = candidate_policy["immediate_min_score"]
    if not 0 <= observe <= batch <= immediate <= 100:
        raise ValueError("Candidate thresholds must satisfy 0 <= observe <= batch <= immediate <= 100")
    if not 0 <= candidate_policy["max_immediate_per_bar"] <= 10:
        raise ValueError("max_immediate_per_bar must be between 0 and 10")
    if not 5 <= candidate_policy["summary_window"] <= 500:
        raise ValueError("summary_window must be between 5 and 500")
    _update(candidate_policy=candidate_policy, updated_at=datetime.now(timezone.utc).isoformat())
    return candidate_policy


def read_runtime_control() -> dict[str, Any]:
    """Return non-secret runtime controls for dashboard/MCP inspection."""
    return {
        "trading_mode": get_runtime_trading_mode(),
        "live_armed": is_live_armed(),
        "candidate_policy": get_candidate_policy(),
        "updated_at": _read().get("updated_at"),
    }
