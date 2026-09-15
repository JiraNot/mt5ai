from __future__ import annotations

import json

from src.ai.openrouter_model_catalog import (
    OpenRouterModel,
    fetch_models,
    get_selected_model,
    group_models,
    save_selected_model,
)


def test_model_catalog_classifies_free_and_paid_models():
    current = OpenRouterModel("current/model", "Current", 0, 0)
    free = OpenRouterModel("free/model", "Free", 0, 0)
    paid = OpenRouterModel("paid/model", "Paid", 0.000001, 0.000002)

    groups = group_models([current, free, paid], "current/model")

    assert [item.model_id for item in groups["current"]] == ["current/model"]
    assert [item.model_id for item in groups["free"]] == ["free/model"]
    assert [item.model_id for item in groups["paid"]] == ["paid/model"]
    assert paid.price_label == "$1.00/M in · $2.00/M out"


def test_fetch_models_ignores_non_text_modalities(monkeypatch):
    class Response:
        def raise_for_status(self):
            return None

        def json(self):
            return {
                "data": [
                    {"id": "z/text", "name": "Text", "pricing": {"prompt": "0", "completion": "0"}},
                    {
                        "id": "a/image",
                        "name": "Image",
                        "architecture": {"input_modalities": ["image"]},
                        "pricing": {"prompt": "0", "completion": "0"},
                    },
                ]
            }

    monkeypatch.setattr("src.ai.openrouter_model_catalog.httpx.get", lambda *args, **kwargs: Response())
    models = fetch_models("https://openrouter.ai/api/v1")

    assert [model.model_id for model in models] == ["z/text"]


def test_selected_model_is_persisted_atomically(monkeypatch, tmp_path):
    path = tmp_path / "selection.json"
    monkeypatch.setenv("OPENROUTER_MODEL_CONFIG_PATH", str(path))
    monkeypatch.setenv("OPENROUTER_MODEL", "fallback/model")

    assert get_selected_model() == "fallback/model"
    save_selected_model("free/model")

    assert json.loads(path.read_text()) == {"model": "free/model"}
    assert get_selected_model() == "free/model"
