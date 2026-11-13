"""Persistent per-UTC-day spend guard for OpenRouter inference."""

from __future__ import annotations

import json
import math
import os
import tempfile
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

DEFAULT_DAILY_BUDGET_USD = 0.50
_lock = threading.RLock()
_persistence_failed = False


def _daily_limit() -> float:
    try:
        value = float(os.getenv("OPENROUTER_DAILY_BUDGET_USD", str(DEFAULT_DAILY_BUDGET_USD)))
    except (TypeError, ValueError):
        value = DEFAULT_DAILY_BUDGET_USD
    return max(0.0, value) if math.isfinite(value) else DEFAULT_DAILY_BUDGET_USD


def _path() -> Path:
    configured = os.getenv("OPENROUTER_USAGE_PATH")
    if configured:
        return Path(configured)
    production_dir = Path("/app/data")
    if production_dir.is_dir():
        return production_dir / "openrouter_usage.json"
    local_data = Path("data")
    if local_data.is_dir():
        return local_data / "openrouter_usage.json"
    return Path("openrouter_usage.json")


def _empty_state(day: str) -> dict[str, Any]:
    return {
        "date_utc": day,
        "spent_usd": 0.0,
        "requests": 0,
        "prompt_tokens": 0,
        "completion_tokens": 0,
        "blocked": False,
        "block_reason": None,
        "last_model": None,
        "last_request_id": None,
        "updated_at": None,
    }


def _read_state(day: str) -> dict[str, Any]:
    try:
        state = json.loads(_path().read_text(encoding="utf-8"))
    except FileNotFoundError:
        return _empty_state(day)
    except (OSError, json.JSONDecodeError):
        state = _empty_state(day)
        state["blocked"] = True
        state["block_reason"] = "Usage ledger is unreadable; paused for safety"
        return state
    if not isinstance(state, dict) or state.get("date_utc") != day:
        return _empty_state(day)
    result = {**_empty_state(day), **state}
    try:
        spent = float(result["spent_usd"])
        requests = int(result["requests"])
        prompt_tokens = int(result["prompt_tokens"])
        completion_tokens = int(result["completion_tokens"])
    except (TypeError, ValueError):
        result["blocked"] = True
        result["block_reason"] = "Usage ledger is invalid; paused for safety"
        result.update({
            "spent_usd": 0.0,
            "requests": 0,
            "prompt_tokens": 0,
            "completion_tokens": 0,
        })
        return result
    if not math.isfinite(spent) or spent < 0 or min(requests, prompt_tokens, completion_tokens) < 0:
        result["blocked"] = True
        result["block_reason"] = "Usage ledger is invalid; paused for safety"
        result.update({
            "spent_usd": 0.0,
            "requests": 0,
            "prompt_tokens": 0,
            "completion_tokens": 0,
        })
        return result
    result["spent_usd"] = spent
    result["requests"] = requests
    result["prompt_tokens"] = prompt_tokens
    result["completion_tokens"] = completion_tokens
    return result


def _write_state(state: dict[str, Any]) -> None:
    path = _path()
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary_name = tempfile.mkstemp(prefix="openrouter_usage.", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(state, handle, ensure_ascii=False, sort_keys=True)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_name, path)
    finally:
        try:
            os.unlink(temporary_name)
        except FileNotFoundError:
            pass


def get_openrouter_usage_status() -> dict[str, Any]:
    """Return spend totals for today without exposing provider credentials."""
    day = datetime.now(timezone.utc).date().isoformat()
    with _lock:
        state = _read_state(day)
    budget = _daily_limit()
    blocked = bool(state.get("blocked")) or _persistence_failed or float(state.get("spent_usd", 0)) >= budget
    return {
        **state,
        "budget_usd": budget,
        "remaining_usd": max(0.0, budget - float(state.get("spent_usd", 0))),
        "blocked": blocked,
        "block_reason": (
            "Usage ledger could not be saved; paused for safety"
            if _persistence_failed
            else state.get("block_reason")
        ),
    }


def can_make_openrouter_request() -> bool:
    status = get_openrouter_usage_status()
    return not status["blocked"] and status["budget_usd"] > 0


def record_openrouter_usage(
    usage: dict[str, Any] | None,
    *,
    model: str,
    request_id: str | None = None,
) -> dict[str, Any]:
    """Persist provider-reported cost and token counts; fail closed if absent."""
    global _persistence_failed
    day = datetime.now(timezone.utc).date().isoformat()
    usage = usage if isinstance(usage, dict) else {}
    raw_cost = usage.get("cost")
    try:
        cost = float(raw_cost)
    except (TypeError, ValueError):
        cost = math.nan

    prompt_tokens = usage.get("prompt_tokens", usage.get("input_tokens", 0))
    completion_tokens = usage.get("completion_tokens", usage.get("output_tokens", 0))
    try:
        prompt_tokens = max(0, int(prompt_tokens or 0))
    except (TypeError, ValueError):
        prompt_tokens = 0
    try:
        completion_tokens = max(0, int(completion_tokens or 0))
    except (TypeError, ValueError):
        completion_tokens = 0

    with _lock:
        state = _read_state(day)
        state["requests"] = int(state.get("requests", 0)) + 1
        state["prompt_tokens"] = int(state.get("prompt_tokens", 0)) + prompt_tokens
        state["completion_tokens"] = int(state.get("completion_tokens", 0)) + completion_tokens
        state["last_model"] = model
        state["last_request_id"] = request_id
        state["updated_at"] = datetime.now(timezone.utc).isoformat()
        if not math.isfinite(cost) or cost < 0:
            state["blocked"] = True
            state["block_reason"] = "Provider response omitted a valid usage cost"
        else:
            state["spent_usd"] = round(float(state.get("spent_usd", 0)) + cost, 8)
            if state["spent_usd"] >= _daily_limit():
                state["blocked"] = True
                state["block_reason"] = "Daily OpenRouter budget reached"
        try:
            _write_state(state)
            _persistence_failed = False
        except OSError:
            _persistence_failed = True
            state["blocked"] = True
            state["block_reason"] = "Usage ledger could not be saved; paused for safety"
    return get_openrouter_usage_status()


def block_openrouter_for_today(reason: str) -> dict[str, Any]:
    """Pause further requests after an uncertain request outcome."""
    global _persistence_failed
    day = datetime.now(timezone.utc).date().isoformat()
    with _lock:
        state = _read_state(day)
        state["blocked"] = True
        state["block_reason"] = reason
        state["updated_at"] = datetime.now(timezone.utc).isoformat()
        try:
            _write_state(state)
            _persistence_failed = False
        except OSError:
            _persistence_failed = True
    return get_openrouter_usage_status()
