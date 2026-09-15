"""OpenRouter model catalog and runtime model selection.

The dashboard uses the public Models API to show current model pricing.  The
selected model is persisted in a small JSON file so the running trading worker
can pick it up without storing an API key in the database or requiring a
redeploy for every model change.
"""

from __future__ import annotations

import json
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx


DEFAULT_BASE_URL = "https://openrouter.ai/api/v1"
DEFAULT_MODEL = "deepseek/deepseek-chat"
DEFAULT_SELECTION_PATH = "/app/data/openrouter_model.json"


@dataclass(frozen=True)
class OpenRouterModel:
    """Small, dashboard-friendly representation of an OpenRouter model."""

    model_id: str
    name: str
    prompt_price: float
    completion_price: float
    context_length: int = 0
    created: int = 0

    @property
    def is_free(self) -> bool:
        return self.prompt_price == 0 and self.completion_price == 0

    @property
    def price_label(self) -> str:
        if self.is_free:
            return "ฟรี"
        return (
            f"${self.prompt_price * 1_000_000:.2f}/M in · "
            f"${self.completion_price * 1_000_000:.2f}/M out"
        )

    @classmethod
    def from_api(cls, payload: dict[str, Any]) -> "OpenRouterModel":
        pricing = payload.get("pricing") or {}
        return cls(
            model_id=str(payload.get("id") or "").strip(),
            name=str(payload.get("name") or payload.get("id") or "Unknown").strip(),
            prompt_price=float(pricing.get("prompt") or 0),
            completion_price=float(pricing.get("completion") or 0),
            context_length=int(payload.get("context_length") or 0),
            created=int(payload.get("created") or 0),
        )


def fetch_models(
    base_url: str | None = None,
    api_key: str | None = None,
    timeout: float = 10.0,
) -> list[OpenRouterModel]:
    """Fetch text-capable models and return valid entries sorted by name."""
    url = f"{(base_url or os.getenv('OPENROUTER_BASE_URL', DEFAULT_BASE_URL)).rstrip('/')}/models"
    headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
    response = httpx.get(url, headers=headers, timeout=timeout)
    response.raise_for_status()
    rows = response.json().get("data", [])
    models = []
    for row in rows:
        modalities = (row.get("architecture") or {}).get("input_modalities") or []
        if modalities and "text" not in modalities:
            continue
        try:
            model = OpenRouterModel.from_api(row)
        except (TypeError, ValueError):
            continue
        if model.model_id:
            models.append(model)
    return sorted(models, key=lambda item: item.name.lower())


def selection_path() -> Path:
    return Path(os.getenv("OPENROUTER_MODEL_CONFIG_PATH", DEFAULT_SELECTION_PATH))


def get_selected_model(default: str | None = None) -> str:
    """Read the runtime selection, falling back to OPENROUTER_MODEL."""
    fallback = (default or os.getenv("OPENROUTER_MODEL", DEFAULT_MODEL)).strip() or DEFAULT_MODEL
    path = selection_path()
    try:
        value = json.loads(path.read_text(encoding="utf-8")).get("model")
        if isinstance(value, str) and value.strip():
            return value.strip()
    except (FileNotFoundError, OSError, json.JSONDecodeError, AttributeError):
        pass
    return fallback


def save_selected_model(model_id: str) -> Path:
    """Atomically persist a validated model identifier for the worker."""
    model_id = model_id.strip()
    if not model_id or len(model_id) > 200:
        raise ValueError("A valid OpenRouter model id is required")
    path = selection_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump({"model": model_id}, handle)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_name, path)
    finally:
        try:
            os.unlink(temp_name)
        except FileNotFoundError:
            pass
    return path


def group_models(models: list[OpenRouterModel], current_model: str) -> dict[str, list[OpenRouterModel]]:
    """Group models as requested by the dashboard: current, free, paid."""
    current = [model for model in models if model.model_id == current_model]
    free = [model for model in models if model.is_free and model.model_id != current_model]
    paid = [model for model in models if not model.is_free and model.model_id != current_model]
    return {"current": current, "free": free, "paid": paid}
