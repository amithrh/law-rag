from __future__ import annotations

import asyncio

import pytest

from apps.api import model_warmup
from apps.api.config import Settings


def test_prewarm_disabled_does_not_load_models(monkeypatch):
    def fail_embedder():
        raise AssertionError("embedder should not load when prewarm is disabled")

    monkeypatch.setattr(model_warmup, "_prewarm_embedder", fail_embedder)

    settings = Settings(
        database_url="postgresql://x",
        prewarm_models_on_startup=False,
    )
    state = asyncio.run(model_warmup.prewarm_models(settings))

    assert state["enabled"] is False
    assert state["status"] == "disabled"
    assert state["ready"] is False


def test_prewarm_marks_local_components_ready(monkeypatch):
    monkeypatch.setattr(
        model_warmup,
        "_prewarm_embedder",
        lambda: {"name": "embedder", "status": "ready", "dim": 1024},
    )
    monkeypatch.setattr(
        model_warmup,
        "_prewarm_reranker",
        lambda: {"name": "reranker", "status": "ready", "score": 0.9},
    )

    settings = Settings(
        database_url="postgresql://x",
        prewarm_models_on_startup=True,
    )
    state = asyncio.run(model_warmup.prewarm_models(settings))

    assert state["enabled"] is True
    assert state["status"] == "ready"
    assert state["ready"] is True
    assert [c["name"] for c in state["components"]] == ["embedder", "reranker"]


def test_required_prewarm_failure_raises(monkeypatch):
    def boom():
        raise RuntimeError("model missing")

    monkeypatch.setattr(model_warmup, "_prewarm_embedder", boom)

    settings = Settings(
        database_url="postgresql://x",
        prewarm_models_on_startup=True,
        prewarm_models_required=True,
    )

    with pytest.raises(RuntimeError, match="model warmup failed"):
        asyncio.run(model_warmup.prewarm_models(settings))

    assert model_warmup.get_model_warmup_state()["status"] == "failed"
