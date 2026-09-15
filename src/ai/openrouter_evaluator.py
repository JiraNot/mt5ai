"""OpenRouter DeepSeek evaluator used as the Bull analyst.

The evaluator keeps the same structured verdict contract as Gemini so the
Council, setup journal, and Risk Engine do not need a provider-specific path.
"""

from __future__ import annotations

import logging
import os

import httpx

from src.ai.gemini_evaluator import GeminiEvaluator, GeminiVerdict

logger = logging.getLogger(__name__)


class OpenRouterEvaluator(GeminiEvaluator):
    """DeepSeek Bull Analyst through OpenRouter's OpenAI-compatible API."""

    def __init__(self) -> None:
        # Do not initialize or require the Antigravity CLI in this provider.
        self._api_key = os.getenv("OPENROUTER_API_KEY", "").strip()
        self._model = os.getenv("OPENROUTER_MODEL", "deepseek/deepseek-chat").strip()
        self._base_url = os.getenv(
            "OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1"
        ).rstrip("/")

    async def evaluate(self, setup_context: dict) -> GeminiVerdict:
        """Send a setup to DeepSeek and parse the shared Bull verdict schema."""
        if not self._api_key:
            return self._fallback_verdict("OPENROUTER_API_KEY ไม่พร้อมใช้งาน")

        prompt = self._build_prompt(setup_context)
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": os.getenv("OPENROUTER_SITE_URL", "https://trade.onetapweb.com"),
            "X-Title": os.getenv("OPENROUTER_APP_NAME", "Freebuff Trading"),
        }
        payload = {
            "model": self._model,
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
                    f"{self._base_url}/chat/completions",
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
