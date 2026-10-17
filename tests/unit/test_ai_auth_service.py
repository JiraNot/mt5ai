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
