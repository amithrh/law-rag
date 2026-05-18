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
    """Stub hybrid_retrieve to return chunks that score ABOVE the coverage
    gate threshold (0.3). Without this, /answer tests refuse before
    reaching the LLM stream we're trying to exercise."""
    from apps.api import main as api_main
    from apps.api import retrieval

    async def fake_retrieve(*args, **kwargs):
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
