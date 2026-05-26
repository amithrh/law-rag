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


@pytest.fixture(autouse=True)
def _patch_llm_preflight(monkeypatch):
    """Keep endpoint tests from reaching out to a live Ollama daemon."""
    from apps.api import main as api_main
    from apps.api import config as cfg

    async def ok_model(model: str | None = None):
        target = model or cfg.get_settings().llm_model
        return {
            "ok": True,
            "model": target,
            "available_models": [target],
            "error": None,
            "message": None,
        }

    monkeypatch.setattr(api_main, "check_model_available", ok_model)


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


def _enable_fast_mode(monkeypatch):
    """Per round-3 review (security #4): skip_nli is a client hint that
    only takes effect when settings.answer_fast_enabled=True server-side.
    Endpoint tests that pass skip_nli=True must also enable fast mode."""
    from apps.api import config as cfg
    # Bypass the lru_cache by clearing it after patching the env-derived
    # default. Simpler: monkeypatch the cached settings instance.
    s = cfg.get_settings()
    monkeypatch.setattr(s, "answer_fast_enabled", True)


def _patch_high_score_retrieve(monkeypatch):
    """Stub answer retrieval to return chunks that score ABOVE the coverage
    gate threshold (0.3). Without this, /answer tests refuse before
    reaching the LLM stream we're trying to exercise."""
    from apps.api import main as api_main
    from apps.api import retrieval

    def chunks():
        return [
            retrieval.RetrievedChunk(
                chunk_id=1, document_id=1, anchor="cpa-2019#sec-2",
                text="Section 12 of the Consumer Protection Act provides for District Forums.",
                title="Consumer Protection Act 2019", source_type="bare_act",
                subject_area="consumer", as_at=None, paragraph_no=None,
                citation=None, court=None, statute_short="CPA-2019",
                dense_score=0.85, bm25_score=0.6, rerank_score=0.82,
            ),
            retrieval.RetrievedChunk(
                chunk_id=2, document_id=1, anchor="cpa-2019#sec-34",
                text="The District Forum has jurisdiction up to twenty lakh rupees in value.",
                title="Consumer Protection Act 2019", source_type="bare_act",
                subject_area="consumer", as_at=None, paragraph_no=None,
                citation=None, court=None, statute_short="CPA-2019",
                dense_score=0.78, bm25_score=0.55, rerank_score=0.71,
            ),
        ]

    async def fake_retrieve(*args, **kwargs):
        return chunks()

    async def fake_multi_query_retrieve(*args, **kwargs):
        return chunks(), []

    monkeypatch.setattr(api_main, "multi_query_hybrid_retrieve", fake_multi_query_retrieve)
    monkeypatch.setattr(api_main, "hybrid_retrieve", fake_retrieve)


@pytest.mark.needs_stack
def test_answer_emits_coverage_passages_and_sentences(monkeypatch):
    """A well-cited LLM answer should reach the user."""
    from apps.api import main as api_main

    _patch_high_score_retrieve(monkeypatch)
    _enable_fast_mode(monkeypatch)

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
            assert event_names[0] == "matter_route"
            # Matter route, coverage chip, and passages arrive before prose.
            assert "coverage" in event_names
            assert "passages" in event_names
            # Each sentence verifier verdict streamed
            assert event_names.count("sentence") >= 1
            assert "timing" in event_names
            assert event_names.index("timing") < event_names.index("disclaimer")
            timing = next(d for ev, d in events if ev == "timing")
            assert timing["llm_model_available"] is True
            assert timing["retrieval_ms"] >= 0
            assert timing["llm_stream_ms"] >= 0
            # Disclaimer footer always closes the answer
            assert event_names[-1] == "disclaimer"


@pytest.mark.needs_stack
def test_answer_off_topic_short_circuits_before_model_or_retrieval(monkeypatch):
    """Off-topic routing should refuse immediately.

    A final live sanity check caught this taking the full retrieval path,
    which made a non-legal query spend ~36s before refusing.
    """
    from apps.api import main as api_main

    async def fail_model(*args, **kwargs):
        raise AssertionError("off-topic request should not check the LLM")

    async def fail_retrieve(*args, **kwargs):
        raise AssertionError("off-topic request should not retrieve")

    monkeypatch.setattr(api_main, "check_model_available", fail_model)
    monkeypatch.setattr(api_main, "multi_query_hybrid_retrieve", fail_retrieve)
    monkeypatch.setattr(api_main, "hybrid_retrieve", fail_retrieve)

    with TestClient(app) as c:
        with c.stream("POST", "/answer", json={
            "q": "recipe for biryani",
            "top_k": 4,
        }) as r:
            events = _collect_events(r)

    names = [e[0] for e in events]
    assert names == ["matter_route", "refused", "timing"]
    route_payload = next(d for ev, d in events if ev == "matter_route")
    assert route_payload["category"] == "off_topic"
    refused_payload = next(d for ev, d in events if ev == "refused")
    assert refused_payload["reason"] == "off_topic"
    timing = next(d for ev, d in events if ev == "timing")
    assert "llm_preflight_ms" not in timing
    assert "retrieval_ms" not in timing


@pytest.mark.needs_stack
def test_answer_suppresses_single_uncited_sentence(monkeypatch):
    """Per Codex review #1: uncited sentences must NOT be emitted to the
    user stream. They get suppressed (event=None) while still counting
    against the stop budget. The user sees a clean answer without the
    bad sentence; no red-strikethrough display."""
    from apps.api import main as api_main

    _patch_high_score_retrieve(monkeypatch)
    _enable_fast_mode(monkeypatch)
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
def test_answer_refuses_when_rerank_scores_absent(monkeypatch):
    """Codex round-2 #3: coverage gate must fail CLOSED when all rerank
    scores are None (reranker disabled / unavailable / predict failure).
    Otherwise out-of-slice queries slip through exactly during a degraded
    dependency state — which is the failure the gate is meant to prevent."""
    from apps.api import main as api_main
    from apps.api import retrieval

    async def no_rerank_retrieve(*args, **kwargs):
        return [
            retrieval.RetrievedChunk(
                chunk_id=1, document_id=1, anchor="x",
                text="some passage",
                title="Some case", source_type="sc_judgment",
                subject_area="criminal", as_at=None, paragraph_no=None,
                citation="[2020] 1 SCR 1", court="SC", statute_short=None,
                dense_score=0.5, bm25_score=0.1, rerank_score=None,
            ),
        ]

    async def no_rerank_multi_query_retrieve(*args, **kwargs):
        return await no_rerank_retrieve(*args, **kwargs), []

    monkeypatch.setattr(api_main, "multi_query_hybrid_retrieve", no_rerank_multi_query_retrieve)
    monkeypatch.setattr(api_main, "hybrid_retrieve", no_rerank_retrieve)

    with TestClient(app) as c:
        with c.stream("POST", "/answer", json={
            "q": "any query",
            "top_k": 4,
            "skip_nli": True,
        }) as r:
            assert r.status_code == 200
            event_names = []
            refused_data = None
            current = None
            for line in r.iter_lines():
                if not line:
                    current = None
                    continue
                if line.startswith("event:"):
                    current = line.split(":", 1)[1].strip()
                    event_names.append(current)
                elif line.startswith("data:") and current == "refused":
                    refused_data = json.loads(line.split(":", 1)[1].strip())

            assert "refused" in event_names, f"expected refused, got {event_names}"
            assert refused_data is not None
            assert refused_data.get("reason") == "rerank_unavailable"


@pytest.mark.needs_stack
def test_answer_emits_server_authored_sources_event(monkeypatch):
    """Codex round-2 #4: the LLM no longer authors the Sources section.
    The server emits an authoritative `sources` event from retrieved
    metadata at the end of the stream. Even if the LLM tries to write
    its own '**Sources**' section, those lines must be suppressed."""
    from apps.api import main as api_main

    _patch_high_score_retrieve(monkeypatch)
    _enable_fast_mode(monkeypatch)

    # Model tries to write its own Sources with a fabricated case name.
    fake = _FakeStream(
        "**Short answer**\n",
        "The District Forum has jurisdiction up to twenty lakh rupees [2]. ",
        "**Sources**\n",
        "[2] SC — INVENTED CASE v MADE UP, 2099, fake-anchor.\n",
        "**Disclaimer**\nThis is general legal information.",
    )
    monkeypatch.setattr(api_main, "stream_chat", fake)

    with TestClient(app) as c:
        with c.stream("POST", "/answer", json={
            "q": "consumer complaint forum",
            "top_k": 4,
            "skip_nli": True,
        }) as r:
            assert r.status_code == 200
            event_names = []
            sentence_texts = []
            sources_data = None
            current = None
            for line in r.iter_lines():
                if not line:
                    current = None
                    continue
                if line.startswith("event:"):
                    current = line.split(":", 1)[1].strip()
                    event_names.append(current)
                elif line.startswith("data:") and current == "sources":
                    sources_data = json.loads(line.split(":", 1)[1].strip())
                elif line.startswith("data:") and current == "sentence":
                    d = json.loads(line.split(":", 1)[1].strip())
                    sentence_texts.append(d.get("text", ""))

            # Server-authored sources event present
            assert "sources" in event_names, (
                f"expected server-authored 'sources' event, got: {event_names}"
            )
            assert sources_data is not None
            assert len(sources_data) == 2  # two passages from the fake retrieve
            # The fabricated source line MUST NOT have leaked through
            assert not any("INVENTED CASE" in t for t in sentence_texts), (
                f"fabricated source line leaked: {sentence_texts}"
            )
            # The "**Sources**" header itself also dropped
            assert not any("**Sources" in t for t in sentence_texts), (
                f"Sources header should be suppressed: {sentence_texts}"
            )


@pytest.mark.needs_stack
def test_answer_drops_duplicate_bullets(monkeypatch):
    """Real user output (wages query, 2026-05-18) showed gemma4 emitting
    the same bullet 5 times in 'What you can do next'. The verifier
    passed each one because it's properly cited; the UX was broken.
    Server-side dedupe must drop verbatim repeats."""
    from apps.api import main as api_main

    _patch_high_score_retrieve(monkeypatch)
    _enable_fast_mode(monkeypatch)

    # Model emits the same bullet five times — classic small-model loop.
    fake = _FakeStream(
        "**Short answer**\n",
        "You can recover unpaid wages by applying to the authority [1]. ",
        "**What you can do next**\n",
        "- Apply to the State authority within twelve months [1]. ",
        "- Apply to the State authority within twelve months [1]. ",
        "- Apply to the State authority within twelve months [1]. ",
        "- Apply to the State authority within twelve months [1]. ",
        "- Apply to the State authority within twelve months [1].",
    )
    monkeypatch.setattr(api_main, "stream_chat", fake)

    with TestClient(app) as c:
        with c.stream("POST", "/answer", json={
            "q": "wages recovery", "top_k": 4, "skip_nli": True,
        }) as r:
            sentence_texts = []
            current = None
            for line in r.iter_lines():
                if not line:
                    current = None
                    continue
                if line.startswith("event:"):
                    current = line.split(":", 1)[1].strip()
                elif line.startswith("data:") and current == "sentence":
                    d = json.loads(line.split(":", 1)[1].strip())
                    sentence_texts.append(d.get("text", ""))

            # The bullet should appear ONCE (first instance), not five times
            bullet_count = sum(
                1 for t in sentence_texts
                if "Apply to the State authority within twelve months" in t
            )
            assert bullet_count == 1, (
                f"expected 1 emission of looped bullet, got {bullet_count}: {sentence_texts}"
            )


@pytest.mark.needs_stack
def test_answer_strips_model_disclaimer_section(monkeypatch):
    """The server emits a canonical disclaimer event at end-of-stream.
    Anything the model writes under '**Disclaimer**' is a duplicate and
    must be suppressed — verified live UI showed two disclaimers."""
    from apps.api import main as api_main

    _patch_high_score_retrieve(monkeypatch)
    _enable_fast_mode(monkeypatch)

    fake = _FakeStream(
        "**Short answer**\n",
        "The District Forum has jurisdiction up to twenty lakh rupees [2]. ",
        "**Disclaimer**\n",
        "This is the model's own disclaimer text that we want suppressed. ",
        "And another disclaimer sentence the model wrote. ",
    )
    monkeypatch.setattr(api_main, "stream_chat", fake)

    with TestClient(app) as c:
        with c.stream("POST", "/answer", json={
            "q": "consumer forum", "top_k": 4, "skip_nli": True,
        }) as r:
            sentence_texts = []
            current = None
            for line in r.iter_lines():
                if not line:
                    current = None
                    continue
                if line.startswith("event:"):
                    current = line.split(":", 1)[1].strip()
                elif line.startswith("data:") and current == "sentence":
                    d = json.loads(line.split(":", 1)[1].strip())
                    sentence_texts.append(d.get("text", ""))

            # Neither the model's "**Disclaimer**" header nor the
            # subsequent prose may reach the user.
            assert not any("**Disclaimer" in t for t in sentence_texts), (
                f"Disclaimer header leaked: {sentence_texts}"
            )
            assert not any("model's own disclaimer" in t for t in sentence_texts), (
                f"Model disclaimer prose leaked: {sentence_texts}"
            )
            assert not any("another disclaimer sentence" in t for t in sentence_texts), (
                f"Second model disclaimer line leaked: {sentence_texts}"
            )


@pytest.mark.needs_stack
def test_answer_strips_variant_sources_headers(monkeypatch):
    """Round-3 review (security #1): the model can write 'Sources' under
    many markdown forms ('## Sources', 'sources:', 'References:',
    'SOURCES'). Each one followed by '[N] FAKE CASE v MADE UP, 2099' would
    otherwise ship as OK. The widened _SOURCES_HEADER_RE must strip them
    all."""
    from apps.api import main as api_main

    _patch_high_score_retrieve(monkeypatch)
    _enable_fast_mode(monkeypatch)

    fake = _FakeStream(
        "**Short answer**\n",
        "The District Forum has jurisdiction up to twenty lakh rupees [2]. ",
        "## Sources\n",
        "[2] SC — FABRICATED CASE A v INVENTED B, 2099, fake-anchor.\n",
        "**Disclaimer**\nGeneral legal information.",
    )
    monkeypatch.setattr(api_main, "stream_chat", fake)

    with TestClient(app) as c:
        with c.stream("POST", "/answer", json={
            "q": "consumer complaint forum", "top_k": 4, "skip_nli": True,
        }) as r:
            sentence_texts = []
            current = None
            for line in r.iter_lines():
                if not line:
                    current = None
                    continue
                if line.startswith("event:"):
                    current = line.split(":", 1)[1].strip()
                elif line.startswith("data:") and current == "sentence":
                    d = json.loads(line.split(":", 1)[1].strip())
                    sentence_texts.append(d.get("text", ""))

            # Even with '## Sources' (markdown H2) the fabricated line must
            # NOT reach the user.
            assert not any("FABRICATED CASE" in t for t in sentence_texts), (
                f"## Sources variant leaked: {sentence_texts}"
            )


@pytest.mark.needs_stack
def test_answer_skip_nli_ignored_when_fast_mode_disabled(monkeypatch):
    """Round-3 review (security #4): public callers passing
    {"skip_nli": true} must not be able to bypass NLI in production. Only
    the server-side settings.answer_fast_enabled flag enables fast mode."""
    from apps.api import main as api_main
    from apps.api import verifier as verifier_mod
    from apps.api import config as cfg

    _patch_high_score_retrieve(monkeypatch)
    # NOTE: do NOT call _enable_fast_mode — production-like state.
    s = cfg.get_settings()
    monkeypatch.setattr(s, "answer_fast_enabled", False)

    # Spy on verify_sentence to confirm it's called with skip_nli=False
    # even though the request body asked for True.
    seen_skip_nli: list[bool] = []
    real_verify = verifier_mod.verify_sentence

    def spy(sent, idx_map, *, skip_nli=False, nli_threshold=None):
        seen_skip_nli.append(skip_nli)
        return real_verify(sent, idx_map, skip_nli=skip_nli, nli_threshold=nli_threshold)

    monkeypatch.setattr(api_main, "verify_sentence", spy)

    fake = _FakeStream(
        "**Short answer**\n",
        "Section 12 of the CPA covers District Forums [1].",
    )
    monkeypatch.setattr(api_main, "stream_chat", fake)

    with TestClient(app) as c:
        with c.stream("POST", "/answer", json={
            "q": "consumer", "top_k": 4, "skip_nli": True,
        }) as r:
            for _ in r.iter_lines():
                pass

    assert seen_skip_nli, "verify_sentence was never called"
    assert all(s is False for s in seen_skip_nli), (
        f"server honoured client skip_nli even though fast mode is off: {seen_skip_nli}"
    )


@pytest.mark.needs_stack
def test_answer_refuses_when_rerank_disabled_and_dense_low(monkeypatch):
    """Round-3 review (security #5): when rerank_enabled=False (operator
    ablation), the rerank-gate can't fire. The combined-score fallback
    must refuse low-coverage queries instead of letting them through to
    the LLM."""
    from apps.api import main as api_main
    from apps.api import retrieval
    from apps.api import config as cfg

    s = cfg.get_settings()
    monkeypatch.setattr(s, "rerank_enabled", False)

    async def low_combined_retrieve(*args, **kwargs):
        return [
            retrieval.RetrievedChunk(
                chunk_id=1, document_id=1, anchor="x",
                text="a tangentially related passage",
                title="Some case", source_type="sc_judgment",
                subject_area="criminal", as_at=None, paragraph_no=None,
                citation=None, court="SC", statute_short=None,
                # combined_score property = dense*0.5 + bm25*0.5 = 0.15
                dense_score=0.2, bm25_score=0.1, rerank_score=None,
            ),
        ]

    async def low_combined_multi_query_retrieve(*args, **kwargs):
        return await low_combined_retrieve(*args, **kwargs), []

    monkeypatch.setattr(api_main, "multi_query_hybrid_retrieve", low_combined_multi_query_retrieve)
    monkeypatch.setattr(api_main, "hybrid_retrieve", low_combined_retrieve)

    with TestClient(app) as c:
        with c.stream("POST", "/answer", json={
            "q": "any tangent",
            "top_k": 4,
            "skip_nli": True,
        }) as r:
            event_names = []
            refused = None
            current = None
            for line in r.iter_lines():
                if not line:
                    current = None
                    continue
                if line.startswith("event:"):
                    current = line.split(":", 1)[1].strip()
                    event_names.append(current)
                elif line.startswith("data:") and current == "refused":
                    refused = json.loads(line.split(":", 1)[1].strip())

            assert "refused" in event_names
            assert refused is not None
            assert refused.get("reason") == "low_coverage_dense_fallback"


@pytest.mark.needs_stack
def test_answer_refuses_on_low_coverage(monkeypatch):
    """Coverage gate: when no retrieved passage exceeds refuse_below_rerank,
    /answer must refuse honestly instead of asking the LLM to synthesise
    from tangentially-related judgments. Saves ~30s of LLM time and gives
    the user an honest signal."""
    from apps.api import main as api_main
    from apps.api import retrieval

    # All passages score below the 0.3 threshold (mimics out-of-slice
    # query like "tenant not vacating" with our SC-judgment corpus).
    async def low_score_retrieve(*args, **kwargs):
        return [
            retrieval.RetrievedChunk(
                chunk_id=1, document_id=1, anchor="x",
                text="customs refund procedure",
                title="Customs case", source_type="sc_judgment",
                subject_area="criminal", as_at=None, paragraph_no=None,
                citation="[2020] 1 SCR 1", court="SC", statute_short=None,
                dense_score=0.5, bm25_score=0.1, rerank_score=0.10,
            ),
        ]

    async def low_score_multi_query_retrieve(*args, **kwargs):
        return await low_score_retrieve(*args, **kwargs), []

    monkeypatch.setattr(api_main, "multi_query_hybrid_retrieve", low_score_multi_query_retrieve)
    monkeypatch.setattr(api_main, "hybrid_retrieve", low_score_retrieve)

    with TestClient(app) as c:
        with c.stream("POST", "/answer", json={
            "q": "my tenant is not vacating after notice period",
            "top_k": 4,
            "skip_nli": True,
        }) as r:
            assert r.status_code == 200
            event_names = []
            refused_data = None
            current = None
            for line in r.iter_lines():
                if not line:
                    current = None
                    continue
                if line.startswith("event:"):
                    current = line.split(":", 1)[1].strip()
                    event_names.append(current)
                elif line.startswith("data:") and current == "refused":
                    refused_data = json.loads(line.split(":", 1)[1].strip())

            assert "refused" in event_names, f"expected refused, got {event_names}"
            assert refused_data is not None
            # Per round-4 UX cleanup: top_rerank_score is logged server-side
            # but kept OUT of the user-visible refused payload (engineering
            # number, no value to a lay user). The `reason` tag is the
            # public signal.
            assert refused_data.get("reason") == "low_coverage"
            assert "top_rerank_score" not in refused_data, (
                f"top_rerank_score should not leak to UI: {refused_data}"
            )


@pytest.mark.needs_stack
def test_answer_stops_when_unsupported_dominate(monkeypatch):
    """Stop still fires when ≥2 unsupported AND ratio > skip_threshold."""
    from apps.api import main as api_main

    _patch_high_score_retrieve(monkeypatch)
    _enable_fast_mode(monkeypatch)
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

    async def empty_multi_query_retrieve(*args, **kwargs):
        return [], []

    monkeypatch.setattr(retrieval, "hybrid_retrieve", empty_retrieve)
    monkeypatch.setattr(api_main, "multi_query_hybrid_retrieve", empty_multi_query_retrieve)
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


# --- Task #10: answer-vs-query relevance event ------------------------------

def _patch_relevance(monkeypatch, score: float):
    """Stub apps.api.main.compute_relevance so the test doesn't load
    bge-m3 to score a (query, body) pair. The patched function still
    runs the verdict band logic — only the embedding is bypassed —
    so the test exercises the real classification code path.

    The threshold + band come from the live Settings, so the verdict
    transitions match the production calibration.
    """
    from apps.api import main as api_main
    from apps.api.relevance import RelevanceResult, RelevanceVerdict

    def fake_compute(query: str, body: str, *, threshold: float, band: float):
        if not body.strip():
            return None
        half = band / 2.0
        if score >= threshold + half:
            verdict = RelevanceVerdict.OK
        elif score <= threshold - half:
            verdict = RelevanceVerdict.OFF_TOPIC
        else:
            verdict = RelevanceVerdict.PARTIAL
        return RelevanceResult(
            score=score, verdict=verdict, threshold=threshold, band=band,
        )

    monkeypatch.setattr(api_main, "compute_relevance", fake_compute)


def _collect_events(response) -> list[tuple[str, Any]]:
    """Parse an SSE response body into a list of (event, data-dict) tuples.
    Helper for the relevance tests."""
    events: list[tuple[str, Any]] = []
    current: str | None = None
    for line in response.iter_lines():
        if not line:
            current = None
            continue
        if line.startswith("event:"):
            current = line.split(":", 1)[1].strip()
        elif line.startswith("data:") and current:
            payload = line.split(":", 1)[1].strip()
            try:
                events.append((current, json.loads(payload)))
            except json.JSONDecodeError:
                events.append((current, payload))
    return events


@pytest.mark.needs_stack
def test_answer_errors_before_retrieval_when_llm_model_missing(monkeypatch):
    """A missing configured Ollama model should fail before retrieval work."""
    from apps.api import main as api_main

    async def missing_model(model: str | None = None):
        return {
            "ok": False,
            "model": model or "missing-model",
            "available_models": ["qwen3:14b"],
            "error": "model_not_found",
            "message": "Configured Ollama model is not available.",
        }

    retrieval_calls: list[tuple[tuple, dict]] = []

    async def should_not_retrieve(*args, **kwargs):
        retrieval_calls.append((args, kwargs))
        return [], []

    monkeypatch.setattr(api_main, "check_model_available", missing_model)
    monkeypatch.setattr(api_main, "multi_query_hybrid_retrieve", should_not_retrieve)

    with TestClient(app) as c:
        with c.stream("POST", "/answer", json={
            "q": "Police did not file my FIR. What can I do?",
            "top_k": 4,
        }) as r:
            events = _collect_events(r)

    names = [e[0] for e in events]
    assert names == ["matter_route", "error", "timing"]
    route_payload = next(d for ev, d in events if ev == "matter_route")
    assert route_payload["category"] == "police_fir"
    error_payload = next(d for ev, d in events if ev == "error")
    assert error_payload["reason"] == "llm_model_unavailable"
    timing_payload = next(d for ev, d in events if ev == "timing")
    assert timing_payload["llm_model_available"] is False
    assert "llm_preflight_ms" in timing_payload
    assert retrieval_calls == []


@pytest.mark.needs_stack
def test_answer_emits_relevance_event_when_aligned(monkeypatch):
    """Task #10 Part A: a well-aligned answer (cosine well above
    threshold) emits a `relevance` event with verdict=ok.

    Event ordering: relevance must come AFTER `sources` and BEFORE
    `disclaimer` — that's the contract documented in apps/api/main.py
    and consumed by apps/web/app/components/answer-view.tsx."""
    from apps.api import main as api_main

    _patch_high_score_retrieve(monkeypatch)
    _enable_fast_mode(monkeypatch)
    _patch_relevance(monkeypatch, score=0.85)  # well above the 0.69 threshold

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
            "skip_nli": True,
        }) as r:
            events = _collect_events(r)

    names = [e[0] for e in events]
    assert "relevance" in names, f"expected relevance event, got {names}"

    # Ordering invariant: relevance between sources and disclaimer.
    src_idx = names.index("sources")
    rel_idx = names.index("relevance")
    disc_idx = names.index("disclaimer")
    assert src_idx < rel_idx < disc_idx, (
        f"relevance event out of order: sources={src_idx} "
        f"relevance={rel_idx} disclaimer={disc_idx}"
    )

    rel_payload = next(d for ev, d in events if ev == "relevance")
    assert rel_payload["verdict"] == "ok"
    assert rel_payload["score"] == pytest.approx(0.85, abs=1e-4)
    assert "threshold" in rel_payload
    assert "band" in rel_payload


@pytest.mark.needs_stack
def test_answer_emits_relevance_event_when_off_topic(monkeypatch):
    """Task #10 Part A: the deposit-question failure case. The model
    writes a citation-correct answer that's about the wrong scenario
    — the relevance check must detect the mismatch and emit
    verdict=off_topic.

    The cited prose itself is unchanged (we don't refuse on relevance
    alone). The signal lets the UI render a warning."""
    from apps.api import main as api_main

    _patch_high_score_retrieve(monkeypatch)
    _enable_fast_mode(monkeypatch)
    # Cosine below the current off-topic boundary
    # (threshold=0.50, band=0.08 -> off_topic <= 0.46).
    _patch_relevance(monkeypatch, score=0.45)

    fake = _FakeStream(
        "**Short answer**\n",
        "Under Section 30 of the UP Rent Act, the tenant must deposit "
        "monthly rent with the prescribed authority [1]. ",
        "The court holds the rent in deposit until the dispute is "
        "resolved [2].",
    )
    monkeypatch.setattr(api_main, "stream_chat", fake)

    with TestClient(app) as c:
        with c.stream("POST", "/answer", json={
            "q": "my landlord is not returning my deposit money",
            "top_k": 4,
            "skip_nli": True,
        }) as r:
            events = _collect_events(r)

    names = [e[0] for e in events]
    assert "relevance" in names, f"expected relevance event, got {names}"
    rel_payload = next(d for ev, d in events if ev == "relevance")
    assert rel_payload["verdict"] == "off_topic", (
        f"expected off_topic verdict, got {rel_payload}"
    )


@pytest.mark.needs_stack
def test_answer_no_relevance_event_when_refused(monkeypatch):
    """Task #10 Part A: refused answers MUST NOT emit a relevance event.
    There's no answer body to score, and a verdict on the refusal text
    would be meaningless. The same applies to empty-body / stopped
    paths."""
    from apps.api import main as api_main
    from apps.api import retrieval

    # Stub relevance so if it's ever called, the test would notice
    # (we'd see the side-effect score). A counter on the spy would
    # catch a regression where main accidentally calls it.
    calls: list[tuple[str, str]] = []

    def spy_compute(query, body, *, threshold, band):
        calls.append((query, body))
        return None

    monkeypatch.setattr(api_main, "compute_relevance", spy_compute)

    async def empty_retrieve(*args, **kwargs):
        return []

    async def empty_multi_query_retrieve(*args, **kwargs):
        return [], []

    monkeypatch.setattr(retrieval, "hybrid_retrieve", empty_retrieve)
    monkeypatch.setattr(api_main, "multi_query_hybrid_retrieve", empty_multi_query_retrieve)
    monkeypatch.setattr(api_main, "hybrid_retrieve", empty_retrieve)

    with TestClient(app) as c:
        with c.stream("POST", "/answer", json={
            "q": "what is the airspeed velocity of an unladen swallow under indian law",
            "top_k": 4,
            "skip_nli": True,
        }) as r:
            events = _collect_events(r)

    names = [e[0] for e in events]
    assert "refused" in names, f"expected refused, got {names}"
    assert "relevance" not in names, (
        f"refused answers must not emit relevance, got {names}"
    )
    # Defense in depth: compute_relevance was never even invoked.
    assert calls == [], (
        f"compute_relevance must not be called on refused path, got {calls}"
    )


def test_relevance_threshold_env_override(monkeypatch):
    """Task #10 Part A: ANSWER_RELEVANCE_THRESHOLD=0.7 must reach the
    Settings object so an operator can recalibrate without code edits.

    Same env-var pattern as VERIFIER_BACKEND, NLI_HARD_FLOOR, etc.
    pydantic-settings is case-insensitive so the test sets the upper-
    snake-case name."""
    from apps.api.config import Settings

    monkeypatch.setenv("ANSWER_RELEVANCE_THRESHOLD", "0.7")
    s = Settings(database_url="postgresql://x")
    assert s.answer_relevance_threshold == pytest.approx(0.7)

    # Default sanity check — without the env var, the current calibrated
    # value in Settings applies.
    monkeypatch.delenv("ANSWER_RELEVANCE_THRESHOLD", raising=False)
    s2 = Settings(database_url="postgresql://x")
    assert s2.answer_relevance_threshold == pytest.approx(0.50, abs=1e-4)
