"""Security and behavior tests for the bounded CLI login console."""

from __future__ import annotations

import sys
import time

import pytest

from src.dashboard.cli_login_console import CLILoginManager, LoginCommand


def _manager() -> CLILoginManager:
    return CLILoginManager({
        "test": LoginCommand(
            "test",
            "Test CLI",
            (sys.executable, "-c", "import sys; print('prompt', flush=True); sys.stdin.readline(); print('done', flush=True)"),
        ),
    })


def test_console_runs_only_allowlisted_command_and_keeps_input_out_of_transcript(tmp_path, monkeypatch):
    monkeypatch.setenv("CLI_LOGIN_AUDIT_PATH", str(tmp_path / "audit.jsonl"))
    manager = _manager()
    session = manager.start("test", "owner-a")
    manager.send(session.session_id, "owner-a", "one-time-code")

    for _ in range(20):
        status = manager.status(session.session_id, "owner-a")
        if not status["running"]:
            break
        time.sleep(0.01)

    assert status["exit_code"] == 0
    assert "prompt" in str(status["transcript"])
    assert "done" in str(status["transcript"])
    assert "one-time-code" not in str(status["transcript"])
    audit = (tmp_path / "audit.jsonl").read_text(encoding="utf-8")
    assert "one-time-code" not in audit
    assert '"started"' in audit and '"completed"' in audit


def test_console_rejects_unknown_agents_and_other_session_owners():
    manager = _manager()
    with pytest.raises(ValueError, match="Unsupported CLI agent"):
        manager.start("bash", "owner-a")

    session = manager.start("test", "owner-a")
    with pytest.raises(ValueError, match="session not found"):
        manager.status(session.session_id, "owner-b")
    manager.stop(session.session_id, "owner-a")
