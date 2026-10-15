"""Shared access check for the dashboard and its interactive terminal."""

from __future__ import annotations

import hashlib
import secrets
from urllib.parse import parse_qs, urlsplit


def dashboard_auth_token(password: str) -> str:
    """Derive the existing dashboard URL token without storing the password."""
    return hashlib.sha256(f"freebuff_auth:{password}".encode()).hexdigest()[:20]


def is_terminal_authorized(path: str, password: str) -> bool:
    """Require dashboard authentication even if the dashboard auth is disabled."""
    if not password:
        return False
    token = parse_qs(urlsplit(path).query).get("auth", [""])[0]
    return secrets.compare_digest(token, dashboard_auth_token(password))
