from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

from apps.api import llm


@pytest.mark.asyncio
async def test_model_preflight_is_single_flight_for_concurrent_requests(monkeypatch):
    calls = 0

    async def list_models(timeout_s=2.0):
        nonlocal calls
        calls += 1
        await asyncio.sleep(0.01)
        return ["qwen3:14b"]

    monkeypatch.setattr(
        llm,
        "get_settings",
        lambda: SimpleNamespace(llm_model="qwen3:14b", llm_preflight_cache_sec=30.0),
    )
    monkeypatch.setattr(llm, "list_available_models", list_models)
    llm.clear_model_preflight_cache()

    statuses = await asyncio.gather(
        *(llm.check_model_available("qwen3:14b") for _ in range(25))
    )

    assert calls == 1
    assert all(status["ok"] is True for status in statuses)
    assert all(status["available_models"] == ["qwen3:14b"] for status in statuses)


@pytest.mark.asyncio
async def test_model_preflight_does_not_cache_transient_negative_probe(monkeypatch):
    calls = 0

    async def list_models(timeout_s=2.0):
        nonlocal calls
        calls += 1
        return [] if calls == 1 else ["qwen3:14b"]

    monkeypatch.setattr(
        llm,
        "get_settings",
        lambda: SimpleNamespace(llm_model="qwen3:14b", llm_preflight_cache_sec=30.0),
    )
    monkeypatch.setattr(llm, "list_available_models", list_models)
    llm.clear_model_preflight_cache()

    first = await llm.check_model_available("qwen3:14b")
    second = await llm.check_model_available("qwen3:14b")

    assert first["ok"] is False
    assert second["ok"] is True
    assert calls == 2


@pytest.mark.asyncio
async def test_model_preflight_uses_last_known_good_state_on_refresh_failure(monkeypatch):
    calls = 0

    async def list_models(timeout_s=2.0):
        nonlocal calls
        calls += 1
        if calls == 1:
            return ["qwen3:14b"]
        raise TimeoutError("transient /api/tags timeout")

    monkeypatch.setattr(
        llm,
        "get_settings",
        lambda: SimpleNamespace(llm_model="qwen3:14b", llm_preflight_cache_sec=0.01),
    )
    monkeypatch.setattr(llm, "list_available_models", list_models)
    llm.clear_model_preflight_cache()

    first = await llm.check_model_available("qwen3:14b")
    await asyncio.sleep(0.02)
    second = await llm.check_model_available("qwen3:14b")

    assert first["ok"] is True
    assert second["ok"] is True
    assert second["stale"] is True
    assert calls == 2
