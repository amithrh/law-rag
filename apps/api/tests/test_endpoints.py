"""End-to-end API tests via FastAPI TestClient.

Marked `needs_stack` — require the docker compose stack to be up with the
postgres schema initialized and at least some chunks loaded. Run with:

    PYTHONPATH=. .venv/bin/python -m pytest apps/api/tests/ -m needs_stack -v

The LLM is mocked (we never call Ollama in tests — too slow, too flaky).
The embedding model loads naturally (cached after first run).
"""
from __future__ import annotations

import json
from collections.abc import AsyncIterator
from typing import Any

import pytest
from fastapi.testclient import TestClient

# We rely on the FastAPI app's startup hook to set up the pool. The TestClient
# triggers lifespan correctly.
from apps.api.main import app


# --- /healthz ---------------------------------------------------------------

@pytest.mark.needs_stack
def test_healthz_returns_ok_with_counts():
    with TestClient(app) as c:
        r = c.get("/healthz")
        assert r.status_code == 200
        body = r.json()
        assert body["status"] == "ok"
        assert isinstance(body["chunks"], int)
        assert isinstance(body["documents"], int)
        # We've ingested at least the acts (>1000 chunks); a healthy slice
        # should have far more once SC is loaded.
        assert body["chunks"] > 0, "no chunks in DB — re-ingest"


# --- /search ---------------------------------------------------------------

@pytest.mark.needs_stack
def test_search_returns_hits_with_required_shape():
    """A query that should match the consumer-protection corpus."""
    with TestClient(app) as c:
        r = c.get("/search", params={"q": "consumer dispute defective product", "top_k": 5})
        assert r.status_code == 200
        body = r.json()
        assert body["query"] == "consumer dispute defective product"
        assert isinstance(body["took_ms"], (int, float))
        assert body["took_ms"] > 0
        assert isinstance(body["hits"], list)
        assert 0 < len(body["hits"]) <= 5
        for h in body["hits"]:
            for required_field in (
                "chunk_id", "anchor", "text", "title", "source_type",
                "dense_score", "bm25_score", "combined_score",
            ):
                assert required_field in h, f"missing field {required_field} in hit"
            assert isinstance(h["dense_score"], (int, float))
            # combined = 0.7*dense + 0.3*bm25 (see retrieval.py)
            expected = 0.7 * h["dense_score"] + 0.3 * h["bm25_score"]
            assert abs(h["combined_score"] - expected) < 1e-6


@pytest.mark.needs_stack
def test_search_rejects_too_short_query():
    with TestClient(app) as c:
        r = c.get("/search", params={"q": "x"})
        assert r.status_code == 422  # validation error from Query(min_length=2)


@pytest.mark.needs_stack
def test_search_respects_source_filter():
    """When sources=bare_act, no SC chunks should leak through."""
    with TestClient(app) as c:
        r = c.get("/search", params={
            "q": "right to information", "sources": "bare_act", "top_k": 10,
        })
        assert r.status_code == 200
        for h in r.json()["hits"]:
            assert h["source_type"] == "bare_act", (
                f"source_type filter leaked: got {h['source_type']} for {h['anchor']}"
            )


@pytest.mark.needs_stack
def test_search_top_k_cap_enforced():
    with TestClient(app) as c:
        r = c.get("/search", params={"q": "evidence", "top_k": 101})
        assert r.status_code == 422  # le=100


@pytest.mark.needs_stack
def test_search_results_are_rerank_or_combined_score_descending():
    """When reranker is enabled (default), hits are ordered by rerank_score.
    Otherwise, ordered by combined_score. Test handles both.
    """
    with TestClient(app) as c:
        r = c.get("/search", params={"q": "bail rights arrest", "top_k": 10})
        hits = r.json()["hits"]
        if hits and hits[0]["rerank_score"] is not None:
            # Reranker active
            scores = [h["rerank_score"] for h in hits]
            assert scores == sorted(scores, reverse=True), (
                f"hits not sorted by rerank_score desc: {scores}"
            )
        else:
            scores = [h["combined_score"] for h in hits]
            assert scores == sorted(scores, reverse=True), (
                f"hits not sorted by combined_score desc: {scores}"
            )


@pytest.mark.needs_stack
def test_search_includes_rerank_score_when_reranker_enabled():
    with TestClient(app) as c:
        r = c.get("/search", params={"q": "consumer dispute defective product", "top_k": 3})
        hits = r.json()["hits"]
        # Either all have rerank_score (reranker enabled + model available)
        # or none have rerank_score (disabled / unavailable). Mixed is a bug.
        scores = [h["rerank_score"] for h in hits]
        if scores[0] is not None:
            assert all(s is not None for s in scores), (
                f"mixed rerank_score: {scores}"
            )
            assert all(isinstance(s, (int, float)) for s in scores)


# --- /answer (SSE stream + verifier) ----------------------------------------

class _FakeStream:
    """A mock for apps.api.llm.stream_chat that yields a scripted answer."""

    def __init__(self, *deltas: str):
        self.deltas = list(deltas)

    async def __call__(
        self,
        messages: list[dict],
        *,
        model: str | None = None,
        temperature: float = 0.2,
        max_tokens: int | None = None,
    ) -> AsyncIterator[str]:
        for d in self.deltas:
            yield d


@pytest.mark.needs_stack
def test_answer_emits_coverage_passages_and_sentences(monkeypatch):
    """A well-cited LLM answer should reach the user."""
    from apps.api import main as api_main

    # Script a clean 2-sentence answer where each sentence cites a real passage.
    fake = _FakeStream(
        "**Short answer**\n",
        "Filing a consumer complaint is the right next step [1]. ",
        "The District Forum has jurisdiction up to twenty lakh rupees [2].",
    )
    monkeypatch.setattr(api_main, "stream_chat", fake)

    with TestClient(app) as c:
        with c.stream("POST", "/answer", json={
            "q": "online order arrived broken what to do",
            "top_k": 4,
            "skip_nli": True,  # don't depend on DeBERTa model in this test
        }) as r:
            assert r.status_code == 200
            events: list[tuple[str, Any]] = []
            current_event = None
            for line in r.iter_lines():
                if not line:
                    current_event = None
                    continue
                if line.startswith("event:"):
                    current_event = line.split(":", 1)[1].strip()
                elif line.startswith("data:") and current_event:
                    data = line.split(":", 1)[1].strip()
                    try:
                        events.append((current_event, json.loads(data)))
                    except json.JSONDecodeError:
                        events.append((current_event, data))

            event_names = [e[0] for e in events]
            # Coverage chip and passages always emitted first
            assert "coverage" in event_names
            assert "passages" in event_names
            # Each sentence verifier verdict streamed
            assert event_names.count("sentence") >= 1
            # Disclaimer footer always closes the answer
            assert event_names[-1] == "disclaimer"


@pytest.mark.needs_stack
def test_answer_suppresses_single_uncited_sentence(monkeypatch):
    """Per Codex review #1: uncited sentences must NOT be emitted to the
    user stream. They get suppressed (event=None) while still counting
    against the stop budget. The user sees a clean answer without the
    bad sentence; no red-strikethrough display."""
    from apps.api import main as api_main

    fake = _FakeStream(
        "**Short answer**\n",
        "The consumer can file a complaint [1]. ",
        "They will probably win their case.",  # no citation — SUPPRESSED
    )
    monkeypatch.setattr(api_main, "stream_chat", fake)

    with TestClient(app) as c:
        with c.stream("POST", "/answer", json={
            "q": "online order broken refund",
            "top_k": 4,
            "skip_nli": True,
        }) as r:
            assert r.status_code == 200
            event_names: list[str] = []
            sentence_texts: list[str] = []
            current: str | None = None
            for line in r.iter_lines():
                if not line:
                    current = None
                    continue
                if line.startswith("event:"):
                    current = line.split(":", 1)[1].strip()
                    event_names.append(current)
                elif line.startswith("data:") and current == "sentence":
                    try:
                        d = json.loads(line.split(":", 1)[1].strip())
                        sentence_texts.append(d.get("text", ""))
                    except json.JSONDecodeError:
                        pass

            # The uncited sentence MUST NOT appear in the user-visible stream.
            assert not any("probably win" in s for s in sentence_texts), (
                f"uncited sentence leaked to user: {sentence_texts}"
            )
            # And with min_unsupported_before_stop=2, a single drop must not
            # trigger the stop banner.
            assert "stop" not in event_names, (
                f"single uncited sentence should not stop the stream, got: {event_names}"
            )


@pytest.mark.needs_stack
def test_answer_stops_when_unsupported_dominate(monkeypatch):
    """Stop still fires when ≥2 unsupported AND ratio > skip_threshold."""
    from apps.api import main as api_main

    fake = _FakeStream(
        "**Short answer**\n",
        "The consumer can file a complaint [1]. ",
        "They will win their case. ",         # uncited #1
        "The court will award costs. ",        # uncited #2
        "And the police will help.",            # uncited #3
    )
    monkeypatch.setattr(api_main, "stream_chat", fake)

    with TestClient(app) as c:
        with c.stream("POST", "/answer", json={
            "q": "online order broken refund",
            "top_k": 4,
            "skip_nli": True,
        }) as r:
            assert r.status_code == 200
            event_names = [
                line.split(":", 1)[1].strip()
                for line in r.iter_lines()
                if line.startswith("event:")
            ]
            assert "stop" in event_names, f"expected stop, got {event_names}"


@pytest.mark.needs_stack
def test_answer_refused_when_no_passages(monkeypatch):
    """If retrieval returns nothing, /answer should emit a `refused` event."""
    from apps.api import main as api_main
    from apps.api import retrieval

    async def empty_retrieve(*args, **kwargs):
        return []

    monkeypatch.setattr(retrieval, "hybrid_retrieve", empty_retrieve)
    monkeypatch.setattr(api_main, "hybrid_retrieve", empty_retrieve)

    with TestClient(app) as c:
        with c.stream("POST", "/answer", json={
            "q": "what is the airspeed velocity of an unladen swallow under indian law",
            "top_k": 4,
            "skip_nli": True,
        }) as r:
            assert r.status_code == 200
            event_names = []
            for line in r.iter_lines():
                if line.startswith("event:"):
                    event_names.append(line.split(":", 1)[1].strip())
            assert "refused" in event_names, f"expected refused event, got: {event_names}"
