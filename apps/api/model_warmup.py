"""Startup warmup for in-process retrieval/verifier models.

The app lazy-loads BGE-M3 and the cross-encoder reranker so ordinary imports
and most tests stay lightweight. For production, that laziness must sit behind
readiness: the first user request should not be the warmup request.
"""
from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

from apps.api.config import Settings, get_settings

logger = logging.getLogger(__name__)

_STATE: dict[str, Any] = {
    "enabled": False,
    "status": "not_started",
    "ready": False,
    "components": [],
    "took_ms": 0.0,
    "error": None,
}


def get_model_warmup_state() -> dict[str, Any]:
    """Return a shallow copy suitable for JSON health output."""
    state = dict(_STATE)
    state["components"] = [dict(c) for c in _STATE.get("components", [])]
    return state


def _set_state(state: dict[str, Any]) -> None:
    _STATE.clear()
    _STATE.update(state)


async def prewarm_models(settings: Settings | None = None) -> dict[str, Any]:
    """Warm configured local models and record readiness state."""
    settings = settings or get_settings()
    t0 = time.perf_counter()
    state: dict[str, Any] = {
        "enabled": bool(settings.prewarm_models_on_startup),
        "status": "disabled",
        "ready": False,
        "components": [],
        "took_ms": 0.0,
        "error": None,
    }
    if not settings.prewarm_models_on_startup:
        _set_state(state)
        return get_model_warmup_state()

    state["status"] = "warming"
    _set_state(state)

    try:
        components: list[dict[str, Any]] = []
        if settings.embedding_backend == "tei":
            components.append({
                "name": "embedder",
                "status": "skipped_external",
                "detail": "EMBEDDING_BACKEND=tei is covered by the TEI service healthcheck",
            })
        else:
            components.append(await asyncio.to_thread(_prewarm_embedder))

        if settings.rerank_enabled:
            components.append(await asyncio.to_thread(_prewarm_reranker))
        else:
            components.append({
                "name": "reranker",
                "status": "skipped_disabled",
                "detail": "RERANK_ENABLED=false",
            })

        state.update({
            "status": "ready",
            "ready": True,
            "components": components,
            "took_ms": round((time.perf_counter() - t0) * 1000.0, 1),
        })
        _set_state(state)
        logger.info("model warmup ready in %.1fms", state["took_ms"])
        return get_model_warmup_state()
    except Exception as exc:
        state.update({
            "status": "failed",
            "ready": False,
            "took_ms": round((time.perf_counter() - t0) * 1000.0, 1),
            "error": str(exc),
        })
        _set_state(state)
        logger.exception("model warmup failed")
        if settings.prewarm_models_required:
            raise RuntimeError(f"model warmup failed: {exc}") from exc
        return get_model_warmup_state()


def _prewarm_embedder() -> dict[str, Any]:
    from apps.api.embeddings import get_embedder

    t0 = time.perf_counter()
    vec = get_embedder().encode_one("consumer complaint legal remedy")
    return {
        "name": "embedder",
        "status": "ready",
        "dim": int(len(vec)),
        "took_ms": round((time.perf_counter() - t0) * 1000.0, 1),
    }


def _prewarm_reranker() -> dict[str, Any]:
    from apps.api.rerank import get_reranker

    t0 = time.perf_counter()
    worker = get_reranker()
    if not worker.is_available():
        raise RuntimeError("reranker unavailable")
    scores = worker.score_pairs(
        "consumer complaint legal remedy",
        ["Consumer Protection Act District Commission complaint remedy"],
    )
    if scores is None:
        raise RuntimeError("reranker warmup returned no score")
    return {
        "name": "reranker",
        "status": "ready",
        "score": float(scores[0]),
        "took_ms": round((time.perf_counter() - t0) * 1000.0, 1),
    }


__all__ = ["get_model_warmup_state", "prewarm_models"]
