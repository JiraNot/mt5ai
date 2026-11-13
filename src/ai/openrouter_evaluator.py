"""OpenRouter evaluator used as the Bull analyst.

The evaluator keeps the same structured verdict contract as Gemini so the
Council, setup journal, and Risk Engine do not need a provider-specific path.
"""

from __future__ import annotations

import logging

import httpx

from src.ai.gemini_evaluator import GeminiEvaluator, GeminiVerdict
from src.ai.openrouter_model_catalog import get_selected_model
from src.ai.openrouter_budget import (
    block_openrouter_for_today,
    can_make_openrouter_request,
    get_openrouter_usage_status,
    record_openrouter_usage,
)
from src.core.runtime_provider_settings import get_provider_settings

logger = logging.getLogger(__name__)


class OpenRouterEvaluator(GeminiEvaluator):
    """Bull Analyst through OpenRouter's OpenAI-compatible API."""

    def __init__(self) -> None:
        # Do not initialize or require the Antigravity CLI in this provider.
        self._model = get_selected_model()

    async def evaluate(self, setup_context: dict) -> GeminiVerdict:
        """Send a setup to DeepSeek and parse the shared Bull verdict schema."""
        settings = get_provider_settings()["openrouter"]
        api_key = settings["api_key"]
        if not api_key:
            return self._fallback_verdict("OPENROUTER_API_KEY ไม่พร้อมใช้งาน")

        budget = get_openrouter_usage_status()
        if not can_make_openrouter_request():
            logger.warning(
                "OpenRouter paused: daily spend $%.4f / $%.2f (%s)",
                budget["spent_usd"], budget["budget_usd"], budget.get("block_reason") or "budget reached",
            )
            return self._fallback_verdict("พัก OpenRouter เพราะถึงงบรายวันหรืออ่าน usage ไม่ได้")

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
            "max_tokens": 256,
            "usage": {"include": True},
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
            if not isinstance(data, dict):
                raise ValueError("OpenRouter response must be a JSON object")
            usage_data = data.get("usage")
            if not isinstance(usage_data, dict):
                usage_data = None
            usage_status = record_openrouter_usage(
                usage_data,
                model=str(data.get("model") or payload["model"]),
                request_id=str(data.get("id") or response.headers.get("X-Generation-Id") or "") or None,
            )
            try:
                reported_cost = float((usage_data or {}).get("cost") or 0)
            except (TypeError, ValueError):
                reported_cost = 0.0
            logger.info(
                "OpenRouter usage model=%s cost=$%.6f input=%s output=%s daily=$%.4f/$%.2f",
                usage_status.get("last_model"),
                reported_cost,
                usage_status.get("prompt_tokens"),
                usage_status.get("completion_tokens"),
                usage_status.get("spent_usd"),
                usage_status.get("budget_usd"),
            )
            if usage_status.get("block_reason") == "Provider response omitted a valid usage cost":
                logger.error("OpenRouter response did not include billable usage cost; pausing requests for today")
            raw = data["choices"][0]["message"]["content"] or ""
            return self._parse_response(raw)
        except (httpx.HTTPError, AttributeError, KeyError, IndexError, TypeError, ValueError) as exc:
            block_openrouter_for_today("OpenRouter request outcome is uncertain; paused for safety")
            logger.error("OpenRouter evaluation failed: %s", exc)
            return self._fallback_verdict("OpenRouter เรียกใช้งานไม่สำเร็จ")
