"""Low-cost candidate triage and persistent research summary.

This module deliberately does not call an LLM. It records every strategy
candidate, classifies its review priority, and prepares a compact summary that
can be attached to a later AI decision or inspected through the dashboard/MCP.
"""

from __future__ import annotations

import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from src.core.runtime_control import get_candidate_policy


def _path() -> Path:
    configured = os.getenv("CANDIDATE_TRIAGE_PATH")
    if configured:
        return Path(configured)
    production_dir = Path("/app/data")
    if production_dir.is_dir():
        return production_dir / "candidate_triage.json"
    return Path("candidate_triage.json")


def _empty_state() -> dict[str, Any]:
    return {
        "total": 0,
        "by_priority": {"observe": 0, "batch": 0, "immediate": 0},
        "by_strategy": {},
        "by_session": {},
        "recent": [],
        "updated_at": None,
    }


class CandidateTriage:
    """Persist cheap candidate observations without making an AI call."""

    def __init__(self, path: Path | None = None) -> None:
        self._path = path or _path()

    def classify(self, score: int) -> str:
        policy = get_candidate_policy()
        if score >= policy["immediate_min_score"]:
            return "immediate"
        if score >= policy["batch_min_score"]:
            return "batch"
        return "observe"

    def observe(self, candidate: Any, score: int, session: str) -> str:
        """Record one candidate and return observe/batch/immediate priority."""
        priority = self.classify(score)
        state = self._read()
        strategy = str(getattr(candidate, "strategy_id", "unknown"))
        session_name = str(session or "unknown")
        state["total"] = int(state.get("total", 0)) + 1
        state.setdefault("by_priority", {}).setdefault(priority, 0)
        state["by_priority"][priority] += 1
        state.setdefault("by_strategy", {}).setdefault(strategy, {"total": 0})
        state["by_strategy"][strategy]["total"] += 1
        state["by_strategy"][strategy][priority] = state["by_strategy"][strategy].get(priority, 0) + 1
        state.setdefault("by_session", {}).setdefault(session_name, {"total": 0})
        state["by_session"][session_name]["total"] += 1
        state["by_session"][session_name][priority] = state["by_session"][session_name].get(priority, 0) + 1
        state.setdefault("recent", []).append({
            "timestamp": getattr(candidate, "timestamp", datetime.now(timezone.utc)).isoformat(),
            "symbol": getattr(candidate, "symbol", ""),
            "strategy_id": strategy,
            "direction": getattr(getattr(candidate, "direction", None), "value", ""),
            "score": int(score),
            "priority": priority,
            "session": session_name,
            "rr": float(getattr(candidate, "rr_ratio", 0) or 0),
            "confluences": list(getattr(candidate, "confluences", []) or []),
        })
        window = get_candidate_policy()["summary_window"]
        state["recent"] = state["recent"][-window:]
        state["updated_at"] = datetime.now(timezone.utc).isoformat()
        self._write(state)
        return priority

    def summary(self) -> dict[str, Any]:
        state = self._read()
        state["policy"] = get_candidate_policy()
        return state

    def _read(self) -> dict[str, Any]:
        try:
            value = json.loads(self._path.read_text(encoding="utf-8"))
            return value if isinstance(value, dict) else _empty_state()
        except (FileNotFoundError, json.JSONDecodeError, OSError):
            return _empty_state()

    def _write(self, value: dict[str, Any]) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        fd, temporary_name = tempfile.mkstemp(prefix="candidate_triage.", dir=self._path.parent)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump(value, handle, ensure_ascii=False, sort_keys=True)
            os.replace(temporary_name, self._path)
        finally:
            try:
                os.unlink(temporary_name)
            except FileNotFoundError:
                pass
