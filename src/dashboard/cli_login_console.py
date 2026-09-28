"""Bounded pseudo-terminal sessions for CLI authentication only.

This is intentionally not a general web shell.  Each session can run one
allow-listed login command, accepts only its interactive login input, expires
quickly, and keeps transcript data in process memory only.
"""

from __future__ import annotations

import json
import os
import pty
import secrets
import select
import shutil
import signal
import subprocess
import termios
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from src.core.runtime_provider_settings import save_provider_settings


LOGIN_TIMEOUT_SECONDS = 10 * 60
MAX_TRANSCRIPT_CHARS = 32_000
_READ_SIZE = 4_096


@dataclass(frozen=True)
class LoginCommand:
    agent: str
    label: str
    command: tuple[str, ...]


DEFAULT_COMMANDS = {
    "codex": LoginCommand("codex", "Codex / ChatGPT", ("codex", "login")),
    # The fixed prompt lets agy complete its remote OAuth flow and exit without
    # presenting a general-purpose, tool-capable agent shell to the dashboard.
    "agy": LoginCommand(
        "agy",
        "Antigravity / Gemini",
        ("agy", "--print", "Reply only LOGIN_OK", "--mode", "plan", "--sandbox"),
    ),
    # `cline auth` presents the ClinePass option in its supported auth TUI.
    "clinepass": LoginCommand("clinepass", "ClinePass", ("cline", "auth")),
}


@dataclass
class LoginSession:
    session_id: str
    owner_id: str
    agent: str
    process: subprocess.Popen[bytes]
    master_fd: int
    started_at: float
    transcript: str = ""
    finished_at: float | None = None
    exit_code: int | None = None
    audit_events: list[str] = field(default_factory=list)


def _audit_path() -> Path:
    configured = os.getenv("CLI_LOGIN_AUDIT_PATH")
    if configured:
        return Path(configured)
    production_dir = Path("/app/data")
    if production_dir.is_dir():
        return production_dir / "cli_login_audit.jsonl"
    return Path("cli_login_audit.jsonl")


def _write_audit(agent: str, event: str) -> None:
    """Persist metadata only; terminal output and login input are never logged."""
    path = _audit_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    record = {
        "at": datetime.now(timezone.utc).isoformat(),
        "agent": agent,
        "event": event,
    }
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, sort_keys=True) + "\n")


def _sanitize_output(output: bytes) -> str:
    """Keep printable output and normal line controls without persisting secrets."""
    return output.decode("utf-8", errors="replace").replace("\r\n", "\n").replace("\r", "\n")


class CLILoginManager:
    """Own short-lived, per-dashboard-session CLI auth processes."""

    def __init__(self, commands: dict[str, LoginCommand] | None = None) -> None:
        self._commands = commands or DEFAULT_COMMANDS
        self._sessions: dict[str, LoginSession] = {}

    def start(self, agent: str, owner_id: str) -> LoginSession:
        if agent not in self._commands:
            raise ValueError("Unsupported CLI agent")
        command = self._commands[agent]
        executable = command.command[0]
        if not shutil.which(executable):
            raise RuntimeError(f"{command.label} CLI is not installed in this deployment")

        master_fd, slave_fd = pty.openpty()
        attributes = termios.tcgetattr(slave_fd)
        attributes[3] &= ~termios.ECHO
        termios.tcsetattr(slave_fd, termios.TCSANOW, attributes)
        child_env = os.environ.copy()
        child_env.update({
            "TERM": "xterm-256color",
            "NO_COLOR": "1",
            "BROWSER": "false",
            # This makes agy print its remote authorization URL instead of
            # trying to open a browser inside the server container.
            "SSH_CONNECTION": "dashboard-login-console",
        })
        process = subprocess.Popen(
            command.command,
            stdin=slave_fd,
            stdout=slave_fd,
            stderr=slave_fd,
            close_fds=True,
            start_new_session=True,
            cwd="/app" if Path("/app").is_dir() else None,
            env=child_env,
        )
        os.close(slave_fd)
        session = LoginSession(
            session_id=secrets.token_urlsafe(24),
            owner_id=owner_id,
            agent=agent,
            process=process,
            master_fd=master_fd,
            started_at=time.monotonic(),
        )
        self._sessions[session.session_id] = session
        _write_audit(agent, "started")
        self._drain(session)
        return session

    def status(self, session_id: str, owner_id: str) -> dict[str, object]:
        session = self._get(session_id, owner_id)
        self._drain(session)
        return {
            "agent": session.agent,
            "running": session.process.poll() is None,
            "expired": time.monotonic() - session.started_at >= LOGIN_TIMEOUT_SECONDS,
            "exit_code": session.exit_code,
            "transcript": session.transcript,
        }

    def send(self, session_id: str, owner_id: str, value: str) -> None:
        session = self._get(session_id, owner_id)
        self._drain(session)
        if session.process.poll() is not None:
            raise RuntimeError("CLI login session has ended")
        if not isinstance(value, str) or not value or len(value) > 4_096:
            raise ValueError("Login input must be between 1 and 4096 characters")
        os.write(session.master_fd, value.encode("utf-8") + b"\n")
        _write_audit(session.agent, "input_submitted")

    def stop(self, session_id: str, owner_id: str) -> None:
        session = self._get(session_id, owner_id)
        if session.process.poll() is None:
            try:
                os.killpg(session.process.pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
            try:
                session.process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                os.killpg(session.process.pid, signal.SIGKILL)
        self._drain(session)
        _write_audit(session.agent, "stopped")

    def _get(self, session_id: str, owner_id: str) -> LoginSession:
        session = self._sessions.get(session_id)
        if session is None or not secrets.compare_digest(session.owner_id, owner_id):
            raise ValueError("CLI login session not found")
        return session

    def _drain(self, session: LoginSession) -> None:
        if session.process.poll() is None and time.monotonic() - session.started_at >= LOGIN_TIMEOUT_SECONDS:
            try:
                os.killpg(session.process.pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
            _write_audit(session.agent, "timed_out")

        while select.select([session.master_fd], [], [], 0)[0]:
            try:
                chunk = os.read(session.master_fd, _READ_SIZE)
            except OSError:
                break
            if not chunk:
                break
            session.transcript = (session.transcript + _sanitize_output(chunk))[-MAX_TRANSCRIPT_CHARS:]

        exit_code = session.process.poll()
        if exit_code is not None and session.finished_at is None:
            session.finished_at = time.monotonic()
            session.exit_code = exit_code
            if session.agent == "codex" and exit_code == 0:
                self._import_codex_login()
            _write_audit(session.agent, "completed" if exit_code == 0 else "failed")

    @staticmethod
    def _import_codex_login() -> None:
        """Copy a successful CLI login into the encrypted provider store."""
        path = Path.home() / ".codex" / "auth.json"
        try:
            auth_json = path.read_text(encoding="utf-8")
            save_provider_settings("codex", auth_json=auth_json)
        except (OSError, ValueError):
            _write_audit("codex", "credential_import_failed")
