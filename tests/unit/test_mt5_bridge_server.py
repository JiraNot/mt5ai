"""Tests for the Wine/Windows-side bridge startup configuration."""

from __future__ import annotations

from bridge import mt5_bridge


class FakeMT5:
    def __init__(self) -> None:
        self.calls: list[tuple[tuple[object, ...], dict[str, object]]] = []

    def initialize(self, *args: object, **kwargs: object) -> bool:
        self.calls.append((args, kwargs))
        return True

    def account_info(self):
        return None


def test_initialize_passes_path_portable_mode_and_account(monkeypatch):
    fake = FakeMT5()
    monkeypatch.setattr(mt5_bridge, "MT5_AVAILABLE", True)
    monkeypatch.setattr(mt5_bridge, "mt5", fake)
    monkeypatch.setattr(mt5_bridge, "MT5_PATH", r"C:\Program Files\MetaTrader 5\terminal64.exe")
    monkeypatch.setattr(mt5_bridge, "MT5_PORTABLE", True)
    monkeypatch.setattr(mt5_bridge, "MT5_LOGIN", "123456")
    monkeypatch.setattr(mt5_bridge, "MT5_PASSWORD", "secret")
    monkeypatch.setattr(mt5_bridge, "MT5_SERVER", "Demo-Server")

    assert mt5_bridge.initialize_mt5() is True
    assert fake.calls == [
        (
            (r"C:\Program Files\MetaTrader 5\terminal64.exe",),
            {
                "timeout": 10000,
                "portable": True,
                "login": 123456,
                "password": "secret",
                "server": "Demo-Server",
            },
        )
    ]
