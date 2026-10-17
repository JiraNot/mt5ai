"""AI Provider Authentication and Status Inspection Service.

Mirrors the lightweight, quota-safe session inspection pattern from MobileIDE
(agent-auth.ts / provider-tester.ts). Inspects local CLI auth states (Codex / ChatGPT,
Gemini / Antigravity, OpenAI direct, OpenRouter) without consuming API tokens or burning quota,
and provides on-demand connection testing with latency measurement.
"""

from __future__ import annotations

import asyncio
import logging
import os
import re
import shutil
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx

from src.core.runtime_settings import get_runtime_settings

logger = logging.getLogger(__name__)


def _mask_secret(val: str) -> str:
    if not val:
        return ""
    if len(val) <= 8:
        return "••••••••"
    return f"{val[:6]}••••{val[-4:]}"


class AIAuthService:
    """Inspects and tests local AI authentication sessions and credentials."""

    def __init__(self) -> None:
        self._cache_expires_at: float = 0.0
        self._cached_response: dict[str, Any] | None = None

    async def inspect(self, force: bool = False) -> dict[str, Any]:
        """Inspect all providers without burning model quota. Uses 15s cache."""
        now = time.time()
        if not force and self._cached_response and self._cache_expires_at > now:
            return self._cached_response

        # Inspect providers concurrently
        codex_task = asyncio.create_task(self.inspect_codex())
        gemini_task = asyncio.create_task(self.inspect_gemini())
        openai_task = asyncio.create_task(self.inspect_openai())
        openrouter_task = asyncio.create_task(self.inspect_openrouter())

        items = await asyncio.gather(codex_task, gemini_task, openai_task, openrouter_task)
        response = {
            "ok": True,
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "items": items,
        }
        self._cached_response = response
        self._cache_expires_at = now + 15.0
        return response

    async def inspect_codex(self) -> dict[str, Any]:
        """Check Codex / ChatGPT CLI login state locally (0 quota consumed)."""
        checked_at = datetime.now(timezone.utc).isoformat()
        codex_bin = shutil.which("codex")
        if not codex_bin:
            # Fallback: check ~/.codex/auth.json
            auth_file = Path.home() / ".codex" / "auth.json"
            if auth_file.is_file():
                return {
                    "id": "codex",
                    "name": "ChatGPT / Codex",
                    "auth_type": "oauth-login",
                    "state": "configured",
                    "checked_at": checked_at,
                    "account_label": "Local auth.json",
                    "note": "Codex session file is present locally in ~/.codex/auth.json.",
                }
            return {
                "id": "codex",
                "name": "ChatGPT / Codex",
                "auth_type": "oauth-login",
                "state": "login_required",
                "checked_at": checked_at,
                "note": "Codex CLI is not installed or not in PATH.",
            }

        try:
            proc = await asyncio.create_subprocess_exec(
                codex_bin, "login", "status",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout_b, stderr_b = await asyncio.wait_for(proc.communicate(), timeout=4.0)
            text = (stdout_b.decode("utf-8", errors="replace") + " " + stderr_b.decode("utf-8", errors="replace")).strip()
            clean_text = re.sub(r"\s+", " ", text)[:240]

            if re.search(r"logged in", clean_text, re.IGNORECASE):
                mode = "ChatGPT account" if re.search(r"chatgpt", clean_text, re.IGNORECASE) else "Codex account"
                return {
                    "id": "codex",
                    "name": "ChatGPT / Codex",
                    "auth_type": "oauth-login",
                    "state": "authenticated",
                    "checked_at": checked_at,
                    "account_label": mode,
                    "note": f"{mode} login is active and ready to evaluate trades.",
                }
            if re.search(r"not logged in|login required|sign in", clean_text, re.IGNORECASE):
                return {
                    "id": "codex",
                    "name": "ChatGPT / Codex",
                    "auth_type": "oauth-login",
                    "state": "login_required",
                    "checked_at": checked_at,
                    "note": "Login required. Click 'Open Terminal' or run `codex login` in terminal.",
                }
            return {
                "id": "codex",
                "name": "ChatGPT / Codex",
                "auth_type": "oauth-login",
                "state": "unknown",
                "checked_at": checked_at,
                "note": clean_text or "Codex did not report a recognizable login state.",
            }
        except asyncio.TimeoutError:
            return {
                "id": "codex",
                "name": "ChatGPT / Codex",
                "auth_type": "oauth-login",
                "state": "unknown",
                "checked_at": checked_at,
                "note": "Codex CLI status check timed out.",
            }
        except Exception as exc:
            return {
                "id": "codex",
                "name": "ChatGPT / Codex",
                "auth_type": "oauth-login",
                "state": "unknown",
                "checked_at": checked_at,
                "note": f"Unable to inspect Codex login state: {exc}",
            }

    async def inspect_gemini(self) -> dict[str, Any]:
        """Check Google Gemini / Antigravity OAuth tokens or API key."""
        checked_at = datetime.now(timezone.utc).isoformat()
        settings = get_runtime_settings(mask_secrets=False)
        gemini_key = settings.get("gemini_api_key") or os.getenv("GEMINI_API_KEY", "")

        # Check OAuth files
        gemini_root = Path.home() / ".gemini"
        has_standalone_token = (gemini_root / "jetski-standalone-oauth-token").is_file()
        has_oauth = (
            has_standalone_token
            or (gemini_root / "oauth_creds.json").is_file()
            or (gemini_root / "google_accounts.json").is_file()
            or (gemini_root / "antigravity" / "antigravity_state.pbtxt").is_file()
        )

        if has_oauth:
            return {
                "id": "gemini",
                "name": "Google Gemini / Antigravity",
                "auth_type": "oauth-login",
                "state": "authenticated",
                "checked_at": checked_at,
                "account_label": "Google OAuth session",
                "note": "Google OAuth credentials active for Antigravity / Gemini CLI.",
            }
        if gemini_key.strip():
            return {
                "id": "gemini",
                "name": "Google Gemini / Antigravity",
                "auth_type": "api-key",
                "state": "configured",
                "checked_at": checked_at,
                "account_label": _mask_secret(gemini_key),
                "note": f"Gemini API key configured ({_mask_secret(gemini_key)}).",
            }
        return {
            "id": "gemini",
            "name": "Google Gemini / Antigravity",
            "auth_type": "oauth-login",
            "state": "login_required",
            "checked_at": checked_at,
            "note": "Antigravity CLI is not logged in. Run `agy` in terminal or provide Gemini API key.",
        }

    async def inspect_openai(self) -> dict[str, Any]:
        """Check direct OpenAI API key configuration."""
        checked_at = datetime.now(timezone.utc).isoformat()
        settings = get_runtime_settings(mask_secrets=False)
        key = (settings.get("openai_api_key") or os.getenv("OPENAI_API_KEY", "")).strip()
        model = settings.get("openai_model", "gpt-4o")

        if key:
            return {
                "id": "openai",
                "name": "OpenAI Direct API",
                "auth_type": "api-key",
                "state": "configured",
                "checked_at": checked_at,
                "account_label": _mask_secret(key),
                "note": f"OpenAI API key configured ({_mask_secret(key)}). Model: {model}.",
            }
        return {
            "id": "openai",
            "name": "OpenAI Direct API",
            "auth_type": "api-key",
            "state": "login_required",
            "checked_at": checked_at,
            "note": "OpenAI API key is not configured. Add your API key in Settings.",
        }

    async def inspect_openrouter(self) -> dict[str, Any]:
        """Check OpenRouter API key configuration."""
        checked_at = datetime.now(timezone.utc).isoformat()
        settings = get_runtime_settings(mask_secrets=False)
        key = (settings.get("openrouter_api_key") or os.getenv("OPENROUTER_API_KEY", "")).strip()
        model = settings.get("openrouter_model", "deepseek/deepseek-chat")

        if key:
            return {
                "id": "openrouter",
                "name": "OpenRouter",
                "auth_type": "api-key",
                "state": "configured",
                "checked_at": checked_at,
                "account_label": _mask_secret(key),
                "note": f"OpenRouter API key configured ({_mask_secret(key)}). Model: {model}.",
            }
        return {
            "id": "openrouter",
            "name": "OpenRouter",
            "auth_type": "api-key",
            "state": "login_required",
            "checked_at": checked_at,
            "note": "OpenRouter API key is not configured. Add your key in Settings.",
        }

    async def test_provider(self, provider_id: str) -> dict[str, Any]:
        """Test connection to an AI provider with latency measurement."""
        pid = provider_id.strip().lower()
        t0 = time.time()

        try:
            if pid in ("codex", "chatgpt"):
                return await self._test_codex(t0)
            if pid in ("gemini", "antigravity", "agy", "google"):
                return await self._test_gemini(t0)
            if pid in ("openai", "gpt"):
                return await self._test_openai(t0)
            if pid in ("openrouter", "deepseek"):
                return await self._test_openrouter(t0)
            return {
                "ok": False,
                "provider": pid,
                "status": "error",
                "latency_ms": int((time.time() - t0) * 1000),
                "message": f"Unknown AI provider '{provider_id}'.",
            }
        except Exception as exc:
            return {
                "ok": False,
                "provider": pid,
                "status": "error",
                "latency_ms": int((time.time() - t0) * 1000),
                "message": f"Connection test failed: {exc}",
            }

    async def _test_codex(self, t0: float) -> dict[str, Any]:
        codex_bin = shutil.which("codex")
        if not codex_bin:
            return {
                "ok": False,
                "provider": "codex",
                "status": "login_required",
                "latency_ms": int((time.time() - t0) * 1000),
                "message": "Codex CLI is not installed on PATH.",
            }

        proc = await asyncio.create_subprocess_exec(
            codex_bin, "login", "status",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout_b, stderr_b = await asyncio.wait_for(proc.communicate(), timeout=5.0)
        text = (stdout_b.decode("utf-8", errors="replace") + " " + stderr_b.decode("utf-8", errors="replace")).strip()
        latency_ms = int((time.time() - t0) * 1000)

        if re.search(r"logged in", text, re.IGNORECASE):
            mode = "ChatGPT" if re.search(r"chatgpt", text, re.IGNORECASE) else "Codex"
            return {
                "ok": True,
                "provider": "codex",
                "status": "ready",
                "latency_ms": latency_ms,
                "message": f"{mode} login is active and ready ({latency_ms}ms).",
                "details": {"raw": text[:160]},
            }
        return {
            "ok": False,
            "provider": "codex",
            "status": "login_required",
            "latency_ms": latency_ms,
            "message": "Codex CLI login required. Run `codex login` in terminal.",
            "details": {"raw": text[:160]},
        }

    async def _test_gemini(self, t0: float) -> dict[str, Any]:
        gemini_root = Path.home() / ".gemini"
        has_oauth = (
            (gemini_root / "jetski-standalone-oauth-token").is_file()
            or (gemini_root / "oauth_creds.json").is_file()
            or (gemini_root / "google_accounts.json").is_file()
            or (gemini_root / "antigravity" / "antigravity_state.pbtxt").is_file()
        )
        settings = get_runtime_settings(mask_secrets=False)
        gemini_key = (settings.get("gemini_api_key") or os.getenv("GEMINI_API_KEY", "")).strip()

        latency_ms = int((time.time() - t0) * 1000)
        if has_oauth:
            return {
                "ok": True,
                "provider": "gemini",
                "status": "ready",
                "latency_ms": latency_ms,
                "message": f"Antigravity CLI / Google OAuth credentials are ready ({latency_ms}ms).",
                "details": {"has_oauth": True},
            }
        if gemini_key:
            # Quick ping to Gemini models endpoint if key is present
            async with httpx.AsyncClient(timeout=5.0) as client:
                res = await client.get(
                    f"https://generativelanguage.googleapis.com/v1beta/models?key={gemini_key}"
                )
                latency_ms = int((time.time() - t0) * 1000)
                if res.is_success:
                    return {
                        "ok": True,
                        "provider": "gemini",
                        "status": "ready",
                        "latency_ms": latency_ms,
                        "message": f"Gemini API key is valid and connected ({latency_ms}ms).",
                    }
                return {
                    "ok": False,
                    "provider": "gemini",
                    "status": "error",
                    "latency_ms": latency_ms,
                    "message": f"Gemini API returned HTTP {res.status_code}.",
                }

        return {
            "ok": False,
            "provider": "gemini",
            "status": "login_required",
            "latency_ms": latency_ms,
            "message": "Google OAuth session or Gemini API key not found. Run `agy` in terminal.",
        }

    async def _test_openai(self, t0: float) -> dict[str, Any]:
        settings = get_runtime_settings(mask_secrets=False)
        key = (settings.get("openai_api_key") or os.getenv("OPENAI_API_KEY", "")).strip()
        if not key:
            return {
                "ok": False,
                "provider": "openai",
                "status": "login_required",
                "latency_ms": int((time.time() - t0) * 1000),
                "message": "OpenAI API Key is not configured.",
            }

        async with httpx.AsyncClient(timeout=5.0) as client:
            res = await client.get(
                "https://api.openai.com/v1/models",
                headers={"Authorization": f"Bearer {key}"},
            )
            latency_ms = int((time.time() - t0) * 1000)
            if res.is_success:
                return {
                    "ok": True,
                    "provider": "openai",
                    "status": "ready",
                    "latency_ms": latency_ms,
                    "message": f"OpenAI API Key is valid and connected ({latency_ms}ms).",
                }
            if res.status_code == 401:
                return {
                    "ok": False,
                    "provider": "openai",
                    "status": "error",
                    "latency_ms": latency_ms,
                    "message": "OpenAI returned 401: Invalid API Key.",
                }
            return {
                "ok": False,
                "provider": "openai",
                "status": "error",
                "latency_ms": latency_ms,
                "message": f"OpenAI returned HTTP {res.status_code}.",
            }

    async def _test_openrouter(self, t0: float) -> dict[str, Any]:
        settings = get_runtime_settings(mask_secrets=False)
        key = (settings.get("openrouter_api_key") or os.getenv("OPENROUTER_API_KEY", "")).strip()
        if not key:
            return {
                "ok": False,
                "provider": "openrouter",
                "status": "login_required",
                "latency_ms": int((time.time() - t0) * 1000),
                "message": "OpenRouter API Key is not configured.",
            }

        async with httpx.AsyncClient(timeout=5.0) as client:
            res = await client.get(
                "https://openrouter.ai/api/v1/auth/key",
                headers={"Authorization": f"Bearer {key}"},
            )
            latency_ms = int((time.time() - t0) * 1000)
            if res.is_success:
                data = res.json().get("data", {})
                label = data.get("label", "Key active")
                usage = data.get("usage", 0.0)
                limit = data.get("limit")
                note_parts = [label]
                if limit is not None:
                    note_parts.append(f"Limit: ${limit}")
                if usage:
                    note_parts.append(f"Usage: ${usage:.3f}")
                return {
                    "ok": True,
                    "provider": "openrouter",
                    "status": "ready",
                    "latency_ms": latency_ms,
                    "message": f"OpenRouter connected ({' · '.join(note_parts)}, {latency_ms}ms).",
                    "details": data,
                }
            return {
                "ok": False,
                "provider": "openrouter",
                "status": "error",
                "latency_ms": latency_ms,
                "message": f"OpenRouter returned HTTP {res.status_code}. Check your API key.",
            }


ai_auth_service = AIAuthService()
