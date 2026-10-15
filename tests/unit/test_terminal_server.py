"""Tests for the real PTY login terminal's safety boundaries."""

from __future__ import annotations

import sys
import time

import httpx
import pytest
from websockets.asyncio.client import connect
from websockets.asyncio.server import serve

from src.dashboard.cli_login_console import LoginCommand
from src.dashboard.terminal_auth import dashboard_auth_token, is_terminal_authorized
from src.dashboard.terminal_server import DEFAULT_COMMANDS, TerminalProcess, process_request, terminal_handler


def test_terminal_access_requires_dashboard_auth_token():
    password = "strong-test-password"
    token = dashboard_auth_token(password)

    assert is_terminal_authorized(f"/terminal?auth={token}", password)
    assert is_terminal_authorized(f"/terminal/ws?auth={token}", password)
    assert not is_terminal_authorized("/terminal?auth=wrong", password)
    assert not is_terminal_authorized(f"/terminal?auth={token}", "")


def test_terminal_process_preserves_raw_terminal_input_and_resize(tmp_path, monkeypatch):
    monkeypatch.setenv("CLI_LOGIN_AUDIT_PATH", str(tmp_path / "audit.jsonl"))
    command = LoginCommand(
        "test",
        "Test CLI",
        (
            sys.executable,
            "-u",
            "-c",
            "import os, sys; print(os.get_terminal_size().columns, flush=True); "
            "sys.stdout.buffer.write(sys.stdin.buffer.read(4)); sys.stdout.flush()",
        ),
    )
    terminal = TerminalProcess(command)
    try:
        terminal.resize(132, 31)
        terminal.write("\x1b[A\n")
        output = ""
        for _ in range(100):
            output += terminal.read()
            if terminal.process.poll() is not None:
                break
            time.sleep(0.01)

        assert "132" in output
        assert "\x1b[A" in output
    finally:
        terminal.stop()


@pytest.mark.asyncio
async def test_websocket_terminal_starts_only_approved_command(tmp_path, monkeypatch):
    monkeypatch.setenv("DASHBOARD_PASSWORD", "strong-test-password")
    monkeypatch.setenv("CLI_LOGIN_AUDIT_PATH", str(tmp_path / "audit.jsonl"))
    monkeypatch.setitem(
        DEFAULT_COMMANDS,
        "test",
        LoginCommand(
            "test",
            "Test CLI",
            (sys.executable, "-u", "-c", "import sys; print('ready', flush=True); sys.stdin.buffer.read(1)"),
        ),
    )
    token = dashboard_auth_token("strong-test-password")
    async with serve(terminal_handler, "127.0.0.1", 0, process_request=process_request) as server:
        port = server.sockets[0].getsockname()[1]
        async with httpx.AsyncClient(trust_env=False) as client:
            page = await client.get(f"http://127.0.0.1:{port}/terminal?auth={token}")
            denied = await client.get(f"http://127.0.0.1:{port}/terminal")
        assert page.status_code == 200
        assert "new WebSocket" in page.text
        assert denied.status_code == 403
        async with connect(f"ws://127.0.0.1:{port}/terminal/ws?auth={token}") as socket:
            assert '"type": "ready"' in await socket.recv()
            await socket.send('{"type":"start","agent":"test","cols":100,"rows":28}')
            received = ""
            for _ in range(20):
                message = await socket.recv()
                received += message
                if "ready" in message:
                    break
            assert "ready" in received
            await socket.send('{"type":"input","data":"x"}')
