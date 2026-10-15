"""WebSocket-backed, real PTY terminal for approved CLI login flows only.

The browser sends raw keystrokes and terminal resize events to a PTY, so the
TUI/OAuth flows of Codex, agy, and Cline work as they do over SSH. It doesn't
start a shell and cannot execute arbitrary server commands.
"""

from __future__ import annotations

import asyncio
import json
import os
import pty
import select
import shutil
import signal
import subprocess
import termios
import time
from http import HTTPStatus
from pathlib import Path
from typing import Any

from websockets.asyncio.server import ServerConnection, serve
from websockets.exceptions import ConnectionClosed

from src.dashboard.cli_login_console import (
    DEFAULT_COMMANDS,
    LOGIN_TIMEOUT_SECONDS,
    LoginCommand,
    _write_audit,
    import_codex_login,
)
from src.dashboard.terminal_auth import is_terminal_authorized


TERMINAL_PORT = 7681
MAX_INPUT_BYTES = 16_384
_READ_SIZE = 4_096
_STATIC_PAGE = Path(__file__).with_name("terminal.html")


def _dashboard_password() -> str:
    return os.getenv("DASHBOARD_PASSWORD", "freebuff2026").strip()


def _is_authorized(path: str) -> bool:
    return is_terminal_authorized(path, _dashboard_password())


def _page_response(connection: ServerConnection) -> Any:
    response = connection.respond(HTTPStatus.OK, _STATIC_PAGE.read_text(encoding="utf-8"))
    response.headers["Content-Type"] = "text/html; charset=utf-8"
    response.headers["Cache-Control"] = "no-store"
    return response


def _forbidden_response(connection: ServerConnection) -> Any:
    response = connection.respond(HTTPStatus.FORBIDDEN, "Terminal access denied")
    response.headers["Cache-Control"] = "no-store"
    return response


def process_request(connection: ServerConnection, request: Any) -> Any:
    """Serve the terminal page and leave authorized websocket upgrades alone."""
    path = request.path
    if path.startswith("/terminal") and not _is_authorized(path):
        return _forbidden_response(connection)
    if path.startswith("/terminal/ws"):
        return None
    if path.startswith("/terminal"):
        return _page_response(connection)
    return connection.respond(HTTPStatus.NOT_FOUND, "Not found")


class TerminalProcess:
    """A genuine PTY process, limited to one approved login CLI."""

    def __init__(self, command: LoginCommand) -> None:
        executable = command.command[0]
        if not shutil.which(executable):
            raise RuntimeError(f"{command.label} CLI is not installed in this deployment")

        master_fd, slave_fd = pty.openpty()
        env = os.environ.copy()
        env.update({"TERM": "xterm-256color", "COLORTERM": "truecolor"})
        try:
            self.process = subprocess.Popen(
                command.command,
                stdin=slave_fd,
                stdout=slave_fd,
                stderr=slave_fd,
                close_fds=True,
                start_new_session=True,
                cwd="/app" if Path("/app").is_dir() else None,
                env=env,
            )
        finally:
            os.close(slave_fd)
        self.command = command
        self.master_fd = master_fd
        self.started_at = time.monotonic()
        self._finished = False
        _write_audit(command.agent, "terminal_started")

    def read(self) -> str:
        chunks: list[bytes] = []
        while select.select([self.master_fd], [], [], 0)[0]:
            try:
                chunk = os.read(self.master_fd, _READ_SIZE)
            except OSError:
                break
            if not chunk:
                break
            chunks.append(chunk)
        return b"".join(chunks).decode("utf-8", errors="replace")

    def write(self, value: str) -> None:
        data = value.encode("utf-8")
        if not data or len(data) > MAX_INPUT_BYTES:
            raise ValueError("Terminal input has an invalid length")
        os.write(self.master_fd, data)

    def resize(self, columns: int, rows: int) -> None:
        columns = min(max(columns, 20), 300)
        rows = min(max(rows, 5), 120)
        termios.tcsetwinsize(self.master_fd, (rows, columns))
        os.killpg(self.process.pid, signal.SIGWINCH)

    @property
    def running(self) -> bool:
        return self.process.poll() is None and time.monotonic() - self.started_at < LOGIN_TIMEOUT_SECONDS

    def stop(self, event: str = "terminal_stopped") -> None:
        if self.process.poll() is None:
            try:
                os.killpg(self.process.pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
            try:
                self.process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                os.killpg(self.process.pid, signal.SIGKILL)
                self.process.wait(timeout=2)
        if not self._finished:
            if self.command.agent == "codex" and self.process.returncode == 0:
                import_codex_login()
            _write_audit(self.command.agent, event)
            self._finished = True
        try:
            os.close(self.master_fd)
        except OSError:
            pass


async def _output_pump(connection: ServerConnection, terminal: TerminalProcess) -> None:
    try:
        while terminal.running:
            output = terminal.read()
            if output:
                await connection.send(json.dumps({"type": "output", "data": output}))
            await asyncio.sleep(0.02)
        output = terminal.read()
        if output:
            await connection.send(json.dumps({"type": "output", "data": output}))
        reason = "terminal_timed_out" if terminal.process.poll() is None else "terminal_completed"
        terminal.stop(reason)
        await connection.send(json.dumps({"type": "exit", "code": terminal.process.returncode}))
    except ConnectionClosed:
        terminal.stop("terminal_disconnected")


async def terminal_handler(connection: ServerConnection) -> None:
    terminal: TerminalProcess | None = None
    pump: asyncio.Task[None] | None = None
    try:
        await connection.send(json.dumps({"type": "ready", "agents": list(DEFAULT_COMMANDS)}))
        async for raw_message in connection:
            try:
                message = json.loads(raw_message)
            except (TypeError, json.JSONDecodeError):
                await connection.send(json.dumps({"type": "error", "message": "Invalid terminal message"}))
                continue
            if not isinstance(message, dict):
                continue
            action = message.get("type")
            if action == "start":
                agent = message.get("agent")
                if agent not in DEFAULT_COMMANDS:
                    await connection.send(json.dumps({"type": "error", "message": "Unsupported CLI agent"}))
                    continue
                if terminal:
                    terminal.stop()
                if pump:
                    pump.cancel()
                try:
                    terminal = TerminalProcess(DEFAULT_COMMANDS[agent])
                    terminal.resize(int(message.get("cols", 100)), int(message.get("rows", 28)))
                    pump = asyncio.create_task(_output_pump(connection, terminal))
                except (OSError, RuntimeError, ValueError) as exc:
                    await connection.send(json.dumps({"type": "error", "message": str(exc)}))
            elif action == "input" and terminal and terminal.running:
                data = message.get("data")
                if isinstance(data, str):
                    try:
                        terminal.write(data)
                    except (OSError, ValueError) as exc:
                        await connection.send(json.dumps({"type": "error", "message": str(exc)}))
            elif action == "resize" and terminal and terminal.running:
                try:
                    terminal.resize(int(message.get("cols")), int(message.get("rows")))
                except (TypeError, ValueError, OSError):
                    pass
            elif action == "stop" and terminal:
                terminal.stop()
    except ConnectionClosed:
        pass
    finally:
        if pump:
            pump.cancel()
            try:
                await pump
            except asyncio.CancelledError:
                pass
        if terminal:
            terminal.stop("terminal_disconnected")


async def run_server() -> None:
    async with serve(terminal_handler, "0.0.0.0", TERMINAL_PORT, process_request=process_request):
        await asyncio.Future()


def main() -> None:
    asyncio.run(run_server())


if __name__ == "__main__":
    main()
