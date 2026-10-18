"""Unit tests for AIAuthService and AI authentication API endpoints."""

import pytest
from httpx import ASGITransport, AsyncClient

from src.core.ai_auth_service import AIAuthService, ai_auth_service
from src.web.server import app


@pytest.mark.asyncio
async def test_ai_auth_service_inspect(monkeypatch):
    """Test AIAuthService.inspect() reports providers deterministically."""
    service = AIAuthService()
    res = await service.inspect(force=True)

    assert res["ok"] is True
    assert "updated_at" in res
    assert len(res["items"]) >= 4

    ids = [item["id"] for item in res["items"]]
    assert "codex" in ids
    assert "gemini" in ids
    assert "openai" in ids
    assert "openrouter" in ids

    # Check that each item has required contract fields
    for item in res["items"]:
        assert "auth_type" in item
        assert "state" in item
        assert item["state"] in ("authenticated", "configured", "login_required", "unknown")
        assert "checked_at" in item
        assert "note" in item


@pytest.mark.asyncio
async def test_ai_auth_service_test_provider_unknown():
    """Test unknown provider handling in AIAuthService."""
    service = AIAuthService()
    res = await service.test_provider("non_existent_provider")
    assert res["ok"] is False
    assert res["status"] == "error"
    assert "Unknown AI provider" in res["message"]


@pytest.mark.asyncio
async def test_ai_auth_service_test_openai_without_key(monkeypatch):
    """Test OpenAI test returns login_required when key is missing."""
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    service = AIAuthService()
    res = await service.test_provider("openai")
    assert res["status"] in ("login_required", "error")


@pytest.mark.asyncio
async def test_api_ai_auth_endpoints():
    """Test GET /api/ai/auth-status and POST /api/ai/test through FastAPI."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. GET /api/ai/auth-status
        res = await client.get("/api/ai/auth-status")
        assert res.status_code == 200
        data = res.json()
        assert data["ok"] is True
        assert len(data["items"]) >= 4

        # 2. GET MobileIDE compatible alias /api/agents/auth
        res_alias = await client.get("/api/agents/auth")
        assert res_alias.status_code == 200
        assert res_alias.json()["ok"] is True

        # 3. POST /api/ai/test with unknown provider
        res_test = await client.post("/api/ai/test", json={"provider": "unknown_ai"})
        assert res_test.status_code == 200
        test_data = res_test.json()
        assert test_data["ok"] is False
        assert test_data["result"]["status"] == "error"


def test_gemini_oauth_discovery_and_email_extraction(tmp_path, monkeypatch):
    """Test discovery of tokens in candidate root and JWT email extraction."""
    import base64
    import json
    from src.core.ai_auth_service import AIAuthService

    fake_gemini = tmp_path / ".gemini"
    fake_gemini.mkdir()

    # Construct mock JWT id_token with email
    header_b64 = base64.urlsafe_b64encode(b'{"alg":"RS256"}').decode("utf-8").rstrip("=")
    payload_b64 = base64.urlsafe_b64encode(b'{"email":"jira34yu@gmail.com","sub":"12345"}').decode("utf-8").rstrip("=")
    fake_jwt = f"{header_b64}.{payload_b64}.fakesig"

    token_file = fake_gemini / "jetski-standalone-oauth-token"
    token_file.write_text(json.dumps({"token": "fake", "id_token": fake_jwt}))

    service = AIAuthService()
    monkeypatch.setattr(service, "_candidate_home_roots", lambda: [tmp_path])

    info = service._find_gemini_oauth()
    assert info["has_oauth"] is True
    assert info["email"] == "jira34yu@gmail.com"
    assert "jira34yu@gmail.com" in info["account_label"]
    assert "Google AI Pro" in info["account_label"]


def test_gemini_evaluator_find_cli(tmp_path, monkeypatch):
    """Test GeminiEvaluator locates CLI candidates."""
    from src.ai.gemini_evaluator import GeminiEvaluator

    fake_bin = tmp_path / "antigravity"
    fake_bin.write_text("#!/bin/sh\necho ok")
    fake_bin.chmod(0o755)

    monkeypatch.setattr("shutil.which", lambda name: str(fake_bin) if "antigravity" in name else None)
    cli = GeminiEvaluator._find_cli()
    assert cli is not None

