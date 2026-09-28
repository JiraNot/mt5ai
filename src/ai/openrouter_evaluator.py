"""OpenRouter DeepSeek evaluator used as the Bull analyst.

The evaluator keeps the same structured verdict contract as Gemini so the
Council, setup journal, and Risk Engine do not need a provider-specific path.
"""

from __future__ import annotations

import logging

import httpx

from src.ai.gemini_evaluator import GeminiEvaluator, GeminiVerdict
from src.ai.openrouter_model_catalog import get_selected_model
from src.core.runtime_provider_settings import get_provider_settings

logger = logging.getLogger(__name__)


class OpenRouterEvaluator(GeminiEvaluator):
    """DeepSeek Bull Analyst through OpenRouter's OpenAI-compatible API."""

    def __init__(self) -> None:
        # Do not initialize or require the Antigravity CLI in this provider.
        self._model = get_selected_model()

    async def evaluate(self, setup_context: dict) -> GeminiVerdict:
        """Send a setup to DeepSeek and parse the shared Bull verdict schema."""
        settings = get_provider_settings()["openrouter"]
        api_key = settings["api_key"]
        if not api_key:
            return self._fallback_verdict("OPENROUTER_API_KEY ไม่พร้อมใช้งาน")

        prompt = self._build_prompt(setup_context)
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": settings["site_url"],
            "X-Title": settings["app_name"],
        }
        payload = {
            # Read the dashboard selection for each request so model changes
            # take effect without restarting the trading worker.
            "model": get_selected_model(self._model),
            "messages": [
                {"role": "system", "content": self.SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ],
            "temperature": 0.2,
            "max_tokens": 800,
        }

        try:
            async with httpx.AsyncClient(timeout=60.0) as client:
                response = await client.post(
                    f"{settings['base_url'].rstrip('/')}/chat/completions",
                    headers=headers,
                    json=payload,
                )
                response.raise_for_status()
                data = response.json()
            raw = data["choices"][0]["message"]["content"] or ""
            return self._parse_response(raw)
        except (httpx.HTTPError, KeyError, IndexError, TypeError, ValueError) as exc:
            logger.error("OpenRouter DeepSeek evaluation failed: %s", exc)
            return self._fallback_verdict("OpenRouter DeepSeek เรียกใช้งานไม่สำเร็จ")
