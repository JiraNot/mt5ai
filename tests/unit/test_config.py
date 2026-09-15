import os

from src.core.config import load_settings


def test_normalizes_legacy_absolute_sqlite_worker_url(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "sqlite+aiosqlite:///app/data/freebuff.db")
    settings = load_settings()
    assert settings.database_url == "sqlite+aiosqlite:////app/data/freebuff.db"


def test_preserves_correct_absolute_sqlite_worker_url(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "sqlite+aiosqlite:////app/data/freebuff.db")
    settings = load_settings()
    assert settings.database_url == "sqlite+aiosqlite:////app/data/freebuff.db"
