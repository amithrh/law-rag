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
from types import SimpleNamespace
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
            # Matter route, issue plan, coverage chip, and passages arrive before prose.
            assert "legal_issue_plan" in event_names
            assert "coverage" in event_names
            assert "passages" in event_names
            assert event_names.index("matter_route") < event_names.index("legal_issue_plan")
            assert event_names.index("legal_issue_plan") < event_names.index("coverage")
            plan = next(d for ev, d in events if ev == "legal_issue_plan")
            assert plan["primary_issue"] == "consumer"
            assert plan["user_role"] == "consumer_or_customer"
            assert plan["authority_ledger"][0]["act"] == "Consumer Protection Act 2019"
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


def test_stage_c_grounded_templates_cover_repeated_common_failures():
    from apps.api.main import _grounded_template_lines
    from apps.api.matter_router import route_matter

    def p(index: int, title: str, anchor: str = "", text: str = "") -> dict:
        return {"index": index, "title": title, "anchor": anchor, "text": text}

    cases = [
        (
            "supplier delivered defective material now refusing refund 18 lakh contract",
            [
                p(1, "Indian Contract Act 1872", "/sec-73"),
                p(2, "Sale of Goods Act 1930", "/sec-31"),
                p(3, "Sale of Goods Act 1930", "/sec-56"),
            ],
            ("Sale of Goods Act", "Indian Contract Act", "What you can do next"),
        ),
        (
            "mother says son took her thumb impression on blank paper now produced as gift deed",
            [
                p(1, "Indian Contract Act 1872", "/sec-16"),
                p(2, "Transfer of Property Act 1882", "/sec-123"),
                p(3, "Registration Act 1908", "/sec-17"),
                p(4, "Specific Relief Act 1963", "/sec-31"),
                p(5, "Bharatiya Nyaya Sanhita 2023", "/sec-336"),
            ],
            ("thumb impression", "Specific Relief Act", "police complaint only"),
        ),
        (
            "son took loan against my house i didn't sign told bank to stop ahmedabad",
            [
                p(1, "Bharatiya Nyaya Sanhita 2023", "/sec-336"),
                p(2, "Bharatiya Nagarik Suraksha Sanhita 2023", "/sec-173"),
                p(3, "Banking Regulation Act 1949", "/sec-5"),
                p(4, "Reserve Bank Integrated Ombudsman Scheme 2021", "/sec-2"),
            ],
            ("forged-loan", "bank-service", "police/cyber complaint"),
        ),
        (
            "lic agent told my father guaranteed return now policy matured got half amount fraud",
            [
                p(1, "Insurance Ombudsman Rules 2017", ""),
                p(2, "Consumer Protection Act 2019", "/sec-2-7"),
                p(3, "Maintenance and Welfare of Parents and Senior Citizens Act 2007", "/sec-4"),
            ],
            ("insurance", "Consumer Protection Act", "policy bond"),
        ),
        (
            "tehsildar transferred my baba land to bania without my consent agency area andhra",
            [
                p(1, "Government of Andhra Pradesh v Pratap Karan", ""),
                p(2, "Constitution of India", "/sec-244"),
            ],
            ("agency-area", "Scheduled Area", "tribal-welfare"),
        ),
        (
            "fake call from sbi pension office took 2 lakh from my account 75 yr father",
            [
                p(1, "Information Technology Act 2000", "/sec-66D"),
                p(2, "Bharatiya Nyaya Sanhita 2023", "/sec-318"),
                p(3, "Bharatiya Nagarik Suraksha Sanhita 2023", "/sec-173"),
            ],
            ("cyber impersonation", "BNS", "transaction IDs"),
        ),
        (
            "I had abortion 5 years back husband found out threatening divorce",
            [
                p(1, "Medical Termination of Pregnancy Act 1971", "/sec-5A"),
                p(2, "Hindu Marriage Act 1955", "/sec-13"),
                p(3, "Family Courts Act 1984", "/sec-7"),
            ],
            ("medical privacy", "Do not assume", "divorce threat"),
        ),
        (
            "in-laws not giving back my jewellery streedhan after husband died",
            [
                p(1, "Hindu Succession Act 1956", "/sec-14"),
                p(2, "Protection of Women from Domestic Violence Act 2005", "/sec-3"),
                p(3, "Protection of Women from Domestic Violence Act 2005", "/sec-12"),
                p(4, "Bharatiya Nyaya Sanhita 2023", "/sec-316"),
            ],
            ("streedhan", "economic abuse", "Protection Officer"),
        ),
    ]

    for query, passages, expected_terms in cases:
        route = route_matter(query)
        lines = _grounded_template_lines(query, route, passages)
        joined = "\n".join(lines)
        assert lines, query
        for term in expected_terms:
            assert term in joined, query


def test_safe_route_next_step_promotion_is_narrow():
    from apps.api.main import _promote_safe_route_next_step
    from apps.api.matter_router import route_matter
    from apps.api.verifier import SentenceStatus, SentenceVerification

    route = route_matter("fake call from sbi pension office took 2 lakh from my account 75 yr father")
    header = SentenceVerification("**What you can do next**", SentenceStatus.META)
    action = SentenceVerification(
        "- Give the police/cyber complaint with transaction IDs, beneficiary details, screenshots, and bank complaint number [3].",
        SentenceStatus.UNSUPPORTED,
        citations=[3],
        reason="forced unsupported route action",
    )

    promoted = _promote_safe_route_next_step(action, route, header)

    assert promoted.status == SentenceStatus.WEAK_SUPPORT
    assert promoted.citations == [3]

    no_header = _promote_safe_route_next_step(action, route, None)
    assert no_header.status == SentenceStatus.UNSUPPORTED

    deadline_action = SentenceVerification(
        "- File within 7 days or you will lose the case [3].",
        SentenceStatus.UNSUPPORTED,
        citations=[3],
    )
    unsafe = _promote_safe_route_next_step(deadline_action, route, header)
    assert unsafe.status == SentenceStatus.UNSUPPORTED


def test_minor_mineral_next_step_promotion_rejects_self_help_and_bribery():
    from apps.api.main import _promote_safe_route_next_step
    from apps.api.matter_router import route_matter
    from apps.api.verifier import SentenceStatus, SentenceVerification

    route = route_matter("sand mining lease given without gram sabha consent in scheduled area")
    header = SentenceVerification("**What you can do next**", SentenceStatus.META)

    safe = SentenceVerification(
        "- Ask for the mining or quarry lease file, Gram Sabha/Palli Sabha recommendation and minutes, mineral-department approval, site map, and any forest or pollution clearance papers; then take the record to the Collector, mining department, tribal-welfare authority, DLSA, or court/NGT route [20].",
        SentenceStatus.UNSUPPORTED,
        citations=[20],
    )
    assert _promote_safe_route_next_step(safe, route, header).status == SentenceStatus.WEAK_SUPPORT

    self_help = SentenceVerification(
        "- Block the quarry road and stop the trucks yourself until the Collector cancels the lease [20].",
        SentenceStatus.UNSUPPORTED,
        citations=[20],
    )
    assert _promote_safe_route_next_step(self_help, route, header).status == SentenceStatus.UNSUPPORTED

    bribery = SentenceVerification(
        "- Pay the mining officer to cancel the lease quickly [20].",
        SentenceStatus.UNSUPPORTED,
        citations=[20],
    )
    assert _promote_safe_route_next_step(bribery, route, header).status == SentenceStatus.UNSUPPORTED

    coercive_variants = [
        "- Gherao the Collector with Gram Sabha minutes and lease records until he cancels the lease [20].",
        "- Occupy the quarry site with Gram Sabha minutes, lease records, and demand the Collector cancel the lease [20].",
        "- Stage a road roko with Gram Sabha minutes and lease records before the Collector acts [20].",
        "- Surround the Collector office with Gram Sabha minutes and lease records until cancellation [20].",
    ]
    for text in coercive_variants:
        v = SentenceVerification(text, SentenceStatus.UNSUPPORTED, citations=[20])
        assert _promote_safe_route_next_step(v, route, header).status == SentenceStatus.UNSUPPORTED


def test_contract_floor_skips_backup_consumer_source_for_banking_primary_route():
    from apps.api.main import _should_skip_contract_source_line
    from apps.api.matter_router import route_matter

    route = route_matter("son took loan against my house in 2022 i did not sign told bank to stop")

    assert _should_skip_contract_source_line(
        route,
        "consumer_protection_2019",
        {"rbi_integrated_ombudsman_2021", "banking_regulation_1949", "crpc_1973"},
    )
    assert not _should_skip_contract_source_line(
        route,
        "consumer_protection_2019",
        set(),
    )


def test_contract_floor_does_not_add_backup_sources_when_route_is_covered():
    from apps.api.main import _answer_contract_lines
    from apps.api.matter_router import route_matter

    route = route_matter("son took loan against my house i didn't sign told bank to stop")
    passages = [
        {"index": 1, "title": "Bharatiya Nagarik Suraksha Sanhita 2023", "anchor": "bnss-2023/sec-173", "source_type": "bare_act", "required_source_pack": "bnss_2023"},
        {"index": 2, "title": "Banking Regulation Act 1949", "anchor": "banking-regulation-1949/sec-20-a", "source_type": "bare_act", "required_source_pack": "banking_regulation_1949"},
        {"index": 3, "title": "Reserve Bank Integrated Ombudsman Scheme 2021", "anchor": "rbi-integrated-ombudsman-2021/sec-2", "source_type": "bare_act", "required_source_pack": "rbi_integrated_ombudsman_2021"},
        {"index": 4, "title": "Code of Criminal Procedure 1973", "anchor": "crpc-1973/sec-200", "source_type": "bare_act", "required_source_pack": "crpc_1973"},
    ]
    state = {
        "emitted_citation_indices": {1, 2, 3},
        "seen_sentences": set(),
        "saw_next_step_header": True,
        "saw_next_step_sentence": True,
        "emitted": 5,
    }

    lines = _answer_contract_lines(route, passages, state)

    assert not any("Additional source to verify" in line for line in lines)


@pytest.mark.needs_stack
def test_answer_emits_unknown_criminal_regime_caveat(monkeypatch):
    """Unknown-date criminal routes get a deterministic user-visible caveat."""
    from apps.api import main as api_main
    from apps.api.main import CRIMINAL_REGIME_CAVEAT

    _patch_high_score_retrieve(monkeypatch)
    _enable_fast_mode(monkeypatch)
    _patch_relevance(monkeypatch, score=0.85)

    fake = _FakeStream(
        f"{CRIMINAL_REGIME_CAVEAT} ",
        "**Short answer**\n",
        "Use the BNSS FIR route for the police complaint [1]. ",
        "**What you can do next**\n",
        "- Take the written complaint to the police station [1].",
    )
    monkeypatch.setattr(api_main, "stream_chat", fake)

    with TestClient(app) as c:
        with c.stream("POST", "/answer", json={
            "q": "police refusing FIR caste atrocity case sub inspector saying it is small matter",
            "top_k": 4,
            "skip_nli": True,
        }) as r:
            events = _collect_events(r)

    route = next(data for ev, data in events if ev == "matter_route")
    assert route["legal_regime"] == "incident_date_needed_for_bns_bnss_bsa_vs_ipc_crpc"

    caveats = [
        data for ev, data in events
        if ev == "sentence" and data.get("text") == CRIMINAL_REGIME_CAVEAT
    ]
    assert len(caveats) == 1
    assert caveats[0]["status"] == "meta"


def test_route_regime_caveat_applies_outside_core_criminal_routes():
    from apps.api.main import CRIMINAL_REGIME_CAVEAT, _route_regime_caveat
    from apps.api.matter_router import MatterRoute, route_matter

    route = route_matter(
        "please help husband's mother taunts me daily for not bringing more dowry and now she doesnt give me food"
    )

    assert route.category == "family_domestic"
    assert route.legal_regime == "incident_date_needed_for_bns_bnss_bsa_vs_ipc_crpc"
    assert _route_regime_caveat(route) == CRIMINAL_REGIME_CAVEAT

    property_forgery_route = route_matter(
        "mother says son took her thumb impression on blank paper now produced as gift deed"
    )
    assert property_forgery_route.category == "property_tenancy"
    assert property_forgery_route.legal_regime == "incident_date_needed_for_bns_bnss_bsa_vs_ipc_crpc"
    assert _route_regime_caveat(property_forgery_route) == CRIMINAL_REGIME_CAVEAT

    non_code_route = MatterRoute(
        category="family_marriage_status",
        label="Marriage breakdown",
        confidence=0.7,
        urgency="medium",
        required_sources=["personal marriage law based on religion and form of marriage"],
        forums=["Family Court"],
        missing_facts=["religion"],
        red_flags=[],
        legal_regime="incident_date_needed_for_bns_bnss_bsa_vs_ipc_crpc",
    )
    assert _route_regime_caveat(non_code_route) is None


@pytest.mark.needs_stack
@pytest.mark.parametrize("query", [
    "i issued post dated cheques as security to my landlord, he is now misusing them after i vacated",
    "i gave blank cheque to landlord as security and he sent notice under 138 what defence",
])
def test_answer_security_cheque_prose_is_drawer_safe(monkeypatch, query):
    from apps.api import main as api_main
    from apps.api import retrieval

    _enable_fast_mode(monkeypatch)
    _patch_relevance(monkeypatch, score=0.85)

    chunks = [
        retrieval.RetrievedChunk(
            chunk_id=138,
            document_id=16226,
            anchor="negotiable-instruments-1881/sec-138",
            text=(
                "Section 138 applies to a cheque drawn for discharge of a debt "
                "or other liability, and the payee or holder in due course gives "
                "notice to the drawer of the cheque."
            ),
            title="Negotiable Instruments Act 1881",
            source_type="bare_act",
            subject_area="finance",
            as_at=None,
            paragraph_no=None,
            citation=None,
            court=None,
            statute_short=None,
            dense_score=0.9,
            bm25_score=0.8,
            rerank_score=0.88,
        )
    ]

    async def fake_multi_query_retrieve(*args, **kwargs):
        return chunks, []

    monkeypatch.setattr(api_main, "multi_query_hybrid_retrieve", fake_multi_query_retrieve)
    monkeypatch.setattr(api_main, "stream_chat", _FakeStream("This should not be used [1]."))

    with TestClient(app) as c:
        with c.stream("POST", "/answer", json={
            "q": query,
            "top_k": 4,
            "skip_nli": True,
        }) as r:
            events = _collect_events(r)

    answer = " ".join(
        data.get("text", "")
        for ev, data in events
        if ev == "sentence" and isinstance(data, dict)
    ).lower()
    assert "drawer-defence" in answer
    assert "file a complaint" not in answer


@pytest.mark.needs_stack
@pytest.mark.parametrize("query", [
    "recipe for biryani",
    "recommend a laptop under 60000 for gaming",
    "who won yesterday cricket match india pakistan",
])
def test_answer_off_topic_short_circuits_before_model_or_retrieval(monkeypatch, query):
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
            "q": query,
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
def test_answer_contract_floor_cites_uncited_official_source_and_next_step(monkeypatch):
    from apps.api import main as api_main

    _patch_high_score_retrieve(monkeypatch)
    _enable_fast_mode(monkeypatch)
    _patch_relevance(monkeypatch, score=0.85)

    fake = _FakeStream(
        "**Short answer**\n",
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

    sentence_texts = [d.get("text", "") for ev, d in events if ev == "sentence"]
    joined = " ".join(sentence_texts)

    assert "Consumer Protection Act 2019" in joined
    assert "[1]" in joined
    assert "**What you can do next**" in joined
    assert any(text.startswith("- ") and "[" in text for text in sentence_texts)


@pytest.mark.needs_stack
def test_answer_template_path_filters_weak_sentences_before_emit(monkeypatch):
    from apps.api import main as api_main
    from apps.api import retrieval
    from apps.api.verifier import SentenceStatus, SentenceVerification

    _enable_fast_mode(monkeypatch)
    _patch_relevance(monkeypatch, score=0.85)

    chunks = [
        retrieval.RetrievedChunk(
            chunk_id=1,
            document_id=20,
            anchor="motor-vehicle-aggregator-guidelines/driver-service-contract",
            text="The aggregator guideline source requires a service provider contract for driver engagement and deactivation terms.",
            title="Motor Vehicle Aggregator Guidelines 2020",
            source_type="guideline",
            subject_area="transport",
            as_at=None,
            paragraph_no=None,
            citation=None,
            court=None,
            statute_short="Aggregator Guidelines",
            dense_score=0.9,
            bm25_score=0.7,
            rerank_score=0.88,
        ),
        retrieval.RetrievedChunk(
            chunk_id=2,
            document_id=20,
            anchor="motor-vehicle-aggregator-guidelines/app-transparency-grievance",
            text="The aggregator guideline source requires transparency in app operations, driver-facing disclosures, rating, trip, incentive, fare share, charges, and grievance handling.",
            title="Motor Vehicle Aggregator Guidelines 2020",
            source_type="guideline",
            subject_area="transport",
            as_at=None,
            paragraph_no=None,
            citation=None,
            court=None,
            statute_short="Aggregator Guidelines",
            dense_score=0.88,
            bm25_score=0.7,
            rerank_score=0.86,
        ),
        retrieval.RetrievedChunk(
            chunk_id=3,
            document_id=20,
            anchor="motor-vehicle-aggregator-guidelines/non-discrimination-driver-fare",
            text="The aggregator guideline source states that aggregators should follow non-discrimination principles for drivers and fare-related practices.",
            title="Motor Vehicle Aggregator Guidelines 2020",
            source_type="guideline",
            subject_area="transport",
            as_at=None,
            paragraph_no=None,
            citation=None,
            court=None,
            statute_short="Aggregator Guidelines",
            dense_score=0.86,
            bm25_score=0.7,
            rerank_score=0.84,
        ),
    ]

    async def fake_multi_query_retrieve(*args, **kwargs):
        return chunks, []

    real_verify = api_main.verify_sentence

    def fake_verify(sentence, idx_map, *, skip_nli=False):
        if "ask the aggregator for rating" in sentence:
            return SentenceVerification(
                text=sentence,
                status=SentenceStatus.WEAK_SUPPORT,
                citations=[2],
                reason="forced weak template sentence",
            )
        return real_verify(sentence, idx_map, skip_nli=skip_nli)

    monkeypatch.setattr(api_main, "multi_query_hybrid_retrieve", fake_multi_query_retrieve)
    monkeypatch.setattr(api_main, "stream_chat", _FakeStream("This should not be used [1]."))
    monkeypatch.setattr(api_main, "verify_sentence", fake_verify)

    with TestClient(app) as c:
        with c.stream("POST", "/answer", json={
            "q": "uber driver deactivated after low ratings app not giving reason racist language comment",
            "top_k": 4,
            "skip_nli": True,
        }) as r:
            events = _collect_events(r)

    sentence_payloads = [d for ev, d in events if ev == "sentence"]
    sentence_texts = [d.get("text", "") for d in sentence_payloads]
    joined = " ".join(sentence_texts)

    assert not any("ask the aggregator for rating" in text for text in sentence_texts)
    assert not any(d.get("status") == "weak_support" for d in sentence_payloads)
    assert "suppressed" not in [ev for ev, _ in events]
    assert not any(text.startswith("This answer is routed as:") for text in sentence_texts)
    assert "**What you can do next**" in joined
    assert any(text.startswith("- ") and "[" in text for text in sentence_texts)


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
def test_answer_composer_drops_unsupported_draft_claims(monkeypatch):
    """Compose-before-emit drops bad draft claims and keeps safe source text."""
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
            events = _collect_events(r)

    event_names = [name for name, _ in events]
    sentence_texts = [data.get("text", "") for name, data in events if name == "sentence"]

    assert "stop" not in event_names
    assert "They will win their case" not in " ".join(sentence_texts)
    assert "The court will award costs" not in " ".join(sentence_texts)
    assert "And the police will help" not in " ".join(sentence_texts)
    assert any("Consumer Protection Act" in text for text in sentence_texts)


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


def test_caste_certificate_template_leads_with_st_source_for_st_query():
    from apps.api.main import _grounded_template_lines
    from apps.api.matter_router import route_matter

    q = "office rejected my ST certificate saying not local resident what appeal"
    passages = [
        {
            "index": 1,
            "title": "Constitution of India",
            "anchor": "constitution-india/sec-341",
            "text": "Scheduled Castes are specified by Presidential notification for each State or Union Territory.",
            "source_type": "bare_act",
        },
        {
            "index": 2,
            "title": "Constitution of India",
            "anchor": "constitution-india/sec-342",
            "text": "Scheduled Tribes are specified by Presidential notification for each State or Union Territory.",
            "source_type": "bare_act",
        },
        {
            "index": 3,
            "title": "Right to Information Act 2005",
            "anchor": "right-to-information-act-2005/sec-6",
            "text": "A person may make a request in writing or through electronic means to the public information officer.",
            "source_type": "bare_act",
        },
    ]

    joined = " ".join(_grounded_template_lines(q, route_matter(q), passages))

    assert "ST certificate delay or rejection" in joined
    assert "Article 342" in joined
    assert "For an SC caste-certificate rejection" not in joined


def test_st_certificate_template_does_not_invent_daughter_for_school_query():
    from apps.api.main import _grounded_template_lines
    from apps.api.matter_router import route_matter

    q = "school asking ST certificate for exam form but tehsildar has not issued it"
    passages = [
        {"index": 2, "title": "Constitution of India", "anchor": "constitution-india/sec-342"},
        {"index": 3, "title": "Right to Information Act 2005", "anchor": "right-to-information-act-2005/sec-19"},
    ]

    joined = " ".join(_grounded_template_lines(q, route_matter(q), passages))

    assert "ST certificate delay or rejection" in joined
    assert "daughter" not in joined.lower()


def test_grounded_template_for_mgnrega_wage_delay_uses_mgnrega_sources():
    from apps.api.main import _grounded_template_lines
    from apps.api.matter_router import route_matter

    q = "nrega 28 days work done village mukhiya not paid since 6 months"
    passages = [
        {
            "index": 1,
            "title": "Mahatma Gandhi National Rural Employment Guarantee Act 2005",
            "anchor": "mgnrega-2005/sec-19@2005-09-05",
        },
        {
            "index": 2,
            "title": "Mahatma Gandhi National Rural Employment Guarantee Act 2005",
            "anchor": "mgnrega-2005/sec-17@2005-09-05",
        },
    ]

    joined = " ".join(_grounded_template_lines(q, route_matter(q), passages))

    assert "28 days of NREGA work" in joined
    assert "grievance-redressal route [1]" in joined
    assert "social-audit source" in joined and "[2]" in joined


def test_mgnrega_template_only_uses_days_when_number_is_a_day_count():
    from apps.api.main import _grounded_template_lines
    from apps.api.matter_router import route_matter

    q = "nrega form 28 record missing mukhiya not paying wages"
    passages = [
        {"index": 1, "title": "Mahatma Gandhi National Rural Employment Guarantee Act 2005", "anchor": "mgnrega-2005/sec-19"},
    ]

    joined = " ".join(_grounded_template_lines(q, route_matter(q), passages))

    assert "28 days" not in joined
    assert "NREGA work with wages pending" in joined


def test_grounded_template_for_senior_domestic_violence_uses_pwdva():
    from apps.api.main import _grounded_template_lines
    from apps.api.matter_router import route_matter

    q = "daughter in law beats my mother in lucknow what protection available 68 years old"
    passages = [
        {
            "index": 1,
            "title": "Maintenance and Welfare of Parents and Senior Citizens Act 2007",
            "anchor": "mwp-2007/sec-4",
        },
        {
            "index": 3,
            "title": "Protection of Women from Domestic Violence Act 2005",
            "anchor": "domestic-violence-2005/sec-19@1974-01-01",
        },
        {
            "index": 7,
            "title": "Protection of Women from Domestic Violence Act 2005",
            "anchor": "domestic-violence-2005/sec-12@1974-01-01",
        },
    ]

    joined = " ".join(_grounded_template_lines(q, route_matter(q), passages))

    assert "domestic violence against your 68-year-old mother" in joined
    assert "Domestic Violence Act" in joined
    assert "application to the Magistrate" in joined


def test_senior_template_does_not_fabricate_transfer_or_violence_facts():
    from apps.api.main import _grounded_template_lines
    from apps.api.matter_router import route_matter

    gift_q = "father gifted flat to daughter now she is not maintaining him can tribunal cancel"
    gift_passages = [
        {"index": 1, "title": "Maintenance and Welfare of Parents and Senior Citizens Act 2007", "anchor": "mwp-2007/sec-23"},
    ]
    gift_joined = " ".join(_grounded_template_lines(gift_q, route_matter(gift_q), gift_passages))

    assert "flat gifted or transferred to a transferee or relative" in gift_joined
    assert "house gifted to your son" not in gift_joined

    no_violence_q = "my bahu refuses to maintain my father after property transfer what senior citizen remedy"
    no_violence_passages = [
        {"index": 1, "title": "Maintenance and Welfare of Parents and Senior Citizens Act 2007", "anchor": "mwp-2007/sec-4"},
        {"index": 3, "title": "Protection of Women from Domestic Violence Act 2005", "anchor": "domestic-violence-2005/sec-19"},
    ]
    no_violence_joined = " ".join(_grounded_template_lines(no_violence_q, route_matter(no_violence_q), no_violence_passages))

    assert "domestic violence against" not in no_violence_joined


def test_grounded_template_for_gst_itc_mismatch_uses_cgst_itc_sources():
    from apps.api.main import _grounded_template_lines
    from apps.api.matter_router import route_matter

    q = "gstr 3b mismatch with gstr 2a officer asking reversal 4.8 lakh ITC reply"
    passages = [
        {"index": 1, "title": "Central Goods and Services Tax Act 2017", "anchor": "cgst-2017/sec-16-b"},
        {"index": 4, "title": "Central Goods and Services Tax Act 2017", "anchor": "cgst-2017/sec-41"},
    ]

    joined = " ".join(_grounded_template_lines(q, route_matter(q), passages))

    assert "GSTR-3B/GSTR-2A ITC mismatch" in joined
    assert "Section 16" in joined and "[1]" in joined
    assert "ITC reversal" in joined and "[4]" in joined


def test_gst_itc_template_does_not_cite_section_16_when_absent():
    from apps.api.main import _grounded_template_lines
    from apps.api.matter_router import route_matter

    q = "gstr 3b mismatch with gstr 2a officer asking reversal 4.8 lakh ITC reply"
    passages = [
        {"index": 4, "title": "Central Goods and Services Tax Act 2017", "anchor": "cgst-2017/sec-41"},
    ]

    joined = " ".join(_grounded_template_lines(q, route_matter(q), passages))

    assert "Section 41" in joined and "[4]" in joined
    assert "Section 16 ITC conditions" not in joined


def test_gst_itc_template_does_not_fabricate_2a_3b_mismatch_for_generic_reversal():
    from apps.api.main import _grounded_template_lines
    from apps.api.matter_router import route_matter

    q = "gst officer asking ITC reversal reply what documents to attach"
    passages = [
        {"index": 1, "title": "Central Goods and Services Tax Act 2017", "anchor": "cgst-2017/sec-16"},
        {"index": 4, "title": "Central Goods and Services Tax Act 2017", "anchor": "cgst-2017/sec-41"},
    ]

    joined = " ".join(_grounded_template_lines(q, route_matter(q), passages))

    assert "ITC reversal or mismatch issue" in joined
    assert "GSTR-3B/GSTR-2A" not in joined
    assert "GSTR-2A/3B reconciliation" not in joined
    assert "invoice and payment reconciliation" in joined


def test_gst_2a_3b_mismatch_template_works_without_itc_acronym():
    from apps.api.main import _grounded_template_lines
    from apps.api.matter_router import route_matter

    q = "GSTR-2A GSTR-3B mismatch officer asking reversal reply"
    passages = [
        {"index": 1, "title": "Central Goods and Services Tax Act 2017", "anchor": "cgst-2017/sec-16"},
        {"index": 4, "title": "Central Goods and Services Tax Act 2017", "anchor": "cgst-2017/sec-41"},
    ]

    joined = " ".join(_grounded_template_lines(q, route_matter(q), passages))

    assert "GSTR-3B/GSTR-2A ITC mismatch" in joined
    assert "GSTR-2A/3B reconciliation" in joined


def test_grounded_template_for_non_compete_uses_contract_act_27():
    from apps.api.main import _grounded_template_lines
    from apps.api.matter_router import route_matter

    q = "non compete clause in my employment contract for 2 years is it enforceable in india"
    passages = [
        {"index": 1, "title": "Indian Contract Act 1872", "anchor": "indian-contract-1872/sec-27"},
    ]

    joined = " ".join(_grounded_template_lines(q, route_matter(q), passages))

    assert "two-year employment non-compete" in joined
    assert "Section 27" in joined
    assert "restraint of trade" in joined


def test_grounded_template_for_subscription_refund_uses_consumer_refund_and_complaint():
    from apps.api.main import _grounded_template_lines
    from apps.api.matter_router import route_matter

    q = "match group froze my hinge premium 6 months paid no refund customer care"
    passages = [
        {"index": 1, "title": "Consumer Protection Act 2019", "anchor": "consumer-protection-2019/sec-39-a@2021-09-17"},
        {"index": 5, "title": "Consumer Protection Act 2019", "anchor": "consumer-protection-2019/sec-35@2021-09-17"},
    ]

    joined = " ".join(_grounded_template_lines(q, route_matter(q), passages))

    assert "Hinge/Match Group six-month paid subscription" in joined
    assert "refund of the amount paid" in joined and "[1]" in joined
    assert "Section 35" in joined and "customer-care record" in joined and "[5]" in joined


def test_subscription_template_requires_refund_or_account_block_context():
    from apps.api.main import _grounded_template_lines
    from apps.api.matter_router import route_matter

    q = "hinge premium customer care not responding how to complain"
    passages = [
        {"index": 1, "title": "Consumer Protection Act 2019", "anchor": "consumer-protection-2019/sec-39-a@2021-09-17"},
        {"index": 5, "title": "Consumer Protection Act 2019", "anchor": "consumer-protection-2019/sec-35@2021-09-17"},
    ]

    assert _grounded_template_lines(q, route_matter(q), passages) == []


def test_answer_contract_still_injects_missing_required_source_family():
    from apps.api.main import _answer_contract_lines
    from apps.api.matter_router import route_matter

    passages = [
        {
            "index": 1,
            "title": "Consumer Protection Act 2019",
            "statute_short": "Consumer Protection Act 2019",
            "anchor": "consumer-protection-2019/sec-35",
            "source_type": "bare_act",
            "required_source_pack": "consumer_protection_2019",
            "required_source_priority": 1.0,
            "text": "A complaint may be filed with a District Commission by a consumer.",
        },
        {
            "index": 2,
            "title": "Information Technology Act 2000",
            "statute_short": "Information Technology Act 2000",
            "anchor": "it-2000/sec-79",
            "source_type": "bare_act",
            "required_source_pack": "it_act_2000",
            "required_source_priority": 0.98,
            "text": "An intermediary must observe due diligence while discharging its duties.",
        },
    ]
    state = {
        "emitted_citation_indices": {1},
        "seen_sentences": set(),
        "saw_next_step_sentence": True,
        "saw_next_step_header": True,
        "emitted": 3,
    }

    lines = _answer_contract_lines(route_matter("consumer platform account grievance"), passages, state)

    assert any("Information Technology Act 2000" in line and "Section 79" in line and "[2]" in line for line in lines)
    assert all("due diligence" not in line for line in lines)


def test_answer_contract_plan_must_cite_overrides_generic_source_budget():
    from apps.api.legal_issue_plan import build_legal_issue_plan
    from apps.api.main import _answer_contract_lines
    from apps.api.matter_router import route_matter

    q = "online order arrived broken what to do"
    route = route_matter(q)
    plan = build_legal_issue_plan(q, route)
    passages = [
        {
            "index": 1,
            "title": "Consumer Protection Act 2019",
            "statute_short": "Consumer Protection Act 2019",
            "anchor": "consumer-protection-2019/sec-35",
            "source_type": "bare_act",
            "text": "A consumer may file a complaint before the District Commission.",
        },
        {
            "index": 2,
            "title": "Information Technology Act 2000",
            "statute_short": "Information Technology Act 2000",
            "anchor": "it-2000/sec-79",
            "source_type": "bare_act",
            "text": "An intermediary must observe due diligence while discharging duties.",
        },
        {
            "index": 3,
            "title": "Constitution of India",
            "statute_short": "Constitution of India",
            "anchor": "constitution-india/sec-226",
            "source_type": "bare_act",
            "text": "High Courts may issue writs.",
        },
        {
            "index": 4,
            "title": "Specific Relief Act 1963",
            "statute_short": "Specific Relief Act 1963",
            "anchor": "specific-relief-1963/sec-34",
            "source_type": "bare_act",
            "text": "A person entitled to a legal character may seek a declaration.",
        },
    ]
    state = {
        "emitted_citation_indices": {2, 3, 4},
        "seen_sentences": set(),
        "saw_next_step_sentence": True,
        "saw_next_step_header": True,
        "emitted": 3,
    }

    lines = _answer_contract_lines(route, passages, state, plan)

    assert any("Consumer Protection Act 2019" in line and "[1]" in line for line in lines)
    assert not any("Information Technology Act 2000" in line for line in lines)


def test_answer_contract_plan_must_cite_matches_pesa_and_rfctlarr_aliases():
    from apps.api.legal_issue_plan import build_legal_issue_plan
    from apps.api.main import _answer_contract_lines
    from apps.api.matter_router import route_matter

    q = "land acquired for coal block without consulting palli sabha angul odisha what can i do"
    route = route_matter(q)
    plan = build_legal_issue_plan(q, route)
    passages = [
        {
            "index": 16,
            "title": "Panchayats (Extension to the Scheduled Areas) Act 1996",
            "statute_short": "Panchayats (Extension to the Scheduled Areas) Act 1996",
            "anchor": "pesa-1996/sec-4-b",
            "source_type": "bare_act",
            "text": "The Gram Sabha shall be consulted before land acquisition in Scheduled Areas.",
        },
        {
            "index": 17,
            "title": "Right to Fair Compensation and Transparency in Land Acquisition, Rehabilitation and Resettlement Act 2013",
            "statute_short": "RFCTLARR Act 2013",
            "anchor": "rfctlarr-2013/sec-41",
            "source_type": "bare_act",
            "text": "Special provisions apply to Scheduled Areas.",
        },
        {"index": 18, "title": "Information Technology Act 2000", "anchor": "it-2000/sec-79", "source_type": "bare_act"},
        {"index": 19, "title": "Constitution of India", "anchor": "constitution-india/sec-226", "source_type": "bare_act"},
        {"index": 20, "title": "Specific Relief Act 1963", "anchor": "specific-relief-1963/sec-34", "source_type": "bare_act"},
    ]
    state = {
        "emitted_citation_indices": {18, 19, 20},
        "seen_sentences": set(),
        "saw_next_step_sentence": True,
        "saw_next_step_header": True,
        "emitted": 3,
    }

    lines = _answer_contract_lines(route, passages, state, plan)

    assert any("Panchayats (Extension to the Scheduled Areas) Act 1996" in line and "[16]" in line for line in lines)
    assert any("Right to Fair Compensation" in line and "[17]" in line for line in lines)


def test_answer_contract_plan_must_cite_matches_sarfaesi_full_title():
    from apps.api.legal_issue_plan import build_legal_issue_plan
    from apps.api.main import _answer_contract_lines
    from apps.api.matter_router import route_matter

    q = "bank sent me sarfaesi notice under 13(2) what to do"
    route = route_matter(q)
    plan = build_legal_issue_plan(q, route)
    passages = [
        {
            "index": 7,
            "title": "Securitisation and Reconstruction of Financial Assets and Enforcement of Security Interest Act 2002",
            "statute_short": "SARFAESI Act 2002",
            "anchor": "sarfaesi-2002/sec-13",
            "source_type": "bare_act",
            "text": "A secured creditor may require the borrower by notice to discharge liabilities.",
        },
        {"index": 8, "title": "Information Technology Act 2000", "anchor": "it-2000/sec-79", "source_type": "bare_act"},
        {"index": 9, "title": "Constitution of India", "anchor": "constitution-india/sec-226", "source_type": "bare_act"},
        {"index": 10, "title": "Specific Relief Act 1963", "anchor": "specific-relief-1963/sec-34", "source_type": "bare_act"},
    ]
    state = {
        "emitted_citation_indices": {8, 9, 10},
        "seen_sentences": set(),
        "saw_next_step_sentence": True,
        "saw_next_step_header": True,
        "emitted": 3,
    }

    lines = _answer_contract_lines(route, passages, state, plan)

    assert any("Securitisation and Reconstruction" in line and "Section 13" in line and "[7]" in line for line in lines)


def test_answer_contract_plan_floor_does_not_add_rfctlarr_to_minor_mineral_pesa():
    from apps.api.legal_issue_plan import build_legal_issue_plan
    from apps.api.main import _answer_contract_lines
    from apps.api.matter_router import route_matter

    q = "sand mining lease given without gram sabha consent in scheduled area"
    route = route_matter(q)
    plan = build_legal_issue_plan(q, route)
    passages = [
        {
            "index": 20,
            "title": "Panchayats (Extension to the Scheduled Areas) Act 1996",
            "statute_short": "Panchayats (Extension to the Scheduled Areas) Act 1996",
            "anchor": "pesa-1996/sec-4-c",
            "source_type": "bare_act",
            "required_source_pack": "pesa_1996",
            "text": "Gram Sabha recommendations are relevant before grant of minor mineral concessions.",
        },
        {
            "index": 21,
            "title": "Mines and Minerals (Development and Regulation) Act 1957",
            "statute_short": "Mines and Minerals (Development and Regulation) Act 1957",
            "anchor": "mmdr-1957/sec-4",
            "source_type": "bare_act",
            "required_source_pack": "mmdr_1957",
            "text": "Mining operations require authority under the Act.",
        },
        {
            "index": 22,
            "title": "Right to Fair Compensation and Transparency in Land Acquisition, Rehabilitation and Resettlement Act 2013",
            "statute_short": "RFCTLARR Act 2013",
            "anchor": "rfctlarr-2013/sec-41",
            "source_type": "bare_act",
            "required_source_pack": "rfctlarr_2013",
            "text": "Special provisions apply in Scheduled Areas for land acquisition.",
        },
    ]
    state = {
        "emitted_citation_indices": {20, 21},
        "seen_sentences": set(),
        "saw_next_step_sentence": True,
        "saw_next_step_header": True,
        "emitted": 3,
    }

    lines = _answer_contract_lines(route, passages, state, plan)

    assert not any("RFCTLARR" in line or "Right to Fair Compensation" in line for line in lines)
    assert not any("[22]" in line for line in lines)


def test_answer_contract_next_step_uses_route_action_not_generic_source_phrase():
    from apps.api.legal_issue_plan import build_legal_issue_plan
    from apps.api.main import _answer_contract_lines
    from apps.api.matter_router import route_matter

    q = "sand mining lease given without gram sabha consent in scheduled area"
    route = route_matter(q)
    plan = build_legal_issue_plan(q, route)
    passages = [
        {
            "index": 20,
            "title": "Panchayats (Extension to the Scheduled Areas) Act 1996",
            "statute_short": "Panchayats (Extension to the Scheduled Areas) Act 1996",
            "anchor": "pesa-1996/sec-4-c",
            "source_type": "bare_act",
            "text": "Gram Sabha recommendations are relevant before grant of minor mineral concessions.",
        },
    ]
    state = {
        "emitted_citation_indices": {20},
        "seen_sentences": set(),
        "saw_next_step_sentence": False,
        "saw_next_step_header": False,
        "emitted": 2,
    }

    lines = _answer_contract_lines(route, passages, state, plan)
    joined = " ".join(lines)

    assert "Collect the mining or quarry lease/NOC file" in joined
    assert "Use Panchayats" not in joined


def test_plan_authority_section_matching_is_exact_not_substring():
    from apps.api.main import _plan_authority_matches_passage

    assert _plan_authority_matches_passage(
        "Constitution of India",
        "Article 22",
        {"title": "Constitution of India", "anchor": "constitution-india/sec-22"},
    )
    assert not _plan_authority_matches_passage(
        "Constitution of India",
        "Article 22",
        {"title": "Constitution of India", "anchor": "constitution-india/sec-226"},
    )
    assert not _plan_authority_matches_passage(
        "Forest Rights Act 2006",
        "section 3",
        {"title": "Forest Rights Act 2006", "anchor": "fra-2006/sec-31"},
    )
    assert not _plan_authority_matches_passage(
        "Consumer Protection Act 2019",
        "section 35",
        {"title": "Consumer Protection Act 2019", "anchor": "consumer-protection-2019/sec-135"},
    )
    assert _plan_authority_matches_passage(
        "PESA Act 1996",
        "section 4(c)",
        {"title": "Panchayats (Extension to the Scheduled Areas) Act 1996", "anchor": "pesa-1996/sec-4-c"},
    )


def test_cab_driver_template_does_not_invent_bias_facts():
    from apps.api.main import _grounded_template_lines
    from apps.api.matter_router import route_matter

    q = "uber driver account deactivated after low rating app not giving written reason"
    passages = [
        {"index": 5, "title": "Motor Vehicle Aggregator Guidelines 2020", "anchor": "motor-vehicle-aggregator-guidelines-2020#driver-service-contract"},
        {"index": 6, "title": "Motor Vehicle Aggregator Guidelines 2020", "anchor": "motor-vehicle-aggregator-guidelines-2020#app-transparency-grievance"},
        {"index": 7, "title": "Constitution of India", "anchor": "constitution-india/sec-14"},
    ]

    joined = " ".join(_grounded_template_lines(q, route_matter(q), passages))

    assert "cab-aggregator driver-account grievance" in joined
    assert "language or regional-bias" not in joined
    assert "racist" not in joined


def test_contract_source_reference_skips_statute_body_noise():
    from apps.api.main import _source_excerpt_line

    passage = {
        "index": 3,
        "title": "Protection of Women from Domestic Violence Act 2005",
        "statute_short": "Protection of Women from Domestic Violence Act 2005",
        "anchor": "domestic-violence-2005/sec-19@1974-01-01",
        "text": (
            "Protection of Women from Domestic Violence Act 2005, Section 19 19. "
            "Residence orders.—(1) While disposing of an application under section 12, "
            "the Magistrate may, on being satisfied that domestic violence has taken "
            "place, pass a residence order."
        ),
    }

    line = _source_excerpt_line(passage)

    assert line is not None
    assert "Section 19 19 [3]" not in line
    assert "Residence orders" not in line
    assert "Magistrate" not in line
    assert "Protection of Women from Domestic Violence Act 2005, Section 19" in line
    assert line.endswith("[3].")


def test_contract_source_reference_does_not_quote_numbered_clause():
    from apps.api.main import _source_excerpt_line

    passage = {
        "index": 4,
        "title": "Consumer Protection Act 2019",
        "statute_short": "Consumer Protection Act 2019",
        "anchor": "consumer-protection-2019/sec-39-a@2021-09-17",
        "text": "(1) The District Commission may order refund of the price paid by the consumer.",
    }

    line = _source_excerpt_line(passage)

    assert line is not None
    assert "(1)" not in line
    assert "The District Commission" not in line
    assert line.startswith("Additional source to verify")
    assert "Consumer Protection Act 2019, Section 39(a)" in line
    assert line.endswith("[4].")


def test_contract_next_step_floor_rejects_non_action_definition():
    from apps.api.main import _source_procedural_line

    passage = {
        "index": 1,
        "title": "Prisons Act 1894",
        "anchor": "prisons-1894/sec-3",
        "text": (
            "Prisons Act 1894, Section 3 3. "
            "In this Act, prison means any jail or place used for detention of prisoners."
        ),
    }

    assert _source_procedural_line([passage]) is None


def test_grounded_template_for_rti_pension_uses_rti_sections():
    from apps.api.main import _grounded_template_lines
    from apps.api.matter_router import route_matter

    q = "papa ki pension 6 month se nahi aayi rti kaise file karein"
    passages = [
        {"index": 1, "title": "Right to Information Act 2005", "anchor": "rti-2005/sec-19-a"},
        {"index": 6, "title": "Right to Information Act 2005", "anchor": "rti-2005/sec-7-a"},
        {"index": 7, "title": "Right to Information Act 2005", "anchor": "rti-2005/sec-6"},
    ]

    lines = _grounded_template_lines(q, route_matter(q), passages)

    assert any("father's delayed pension information" in line and "[7]" in line for line in lines)
    assert any("thirty days" in line and "[6]" in line for line in lines)
    assert any("appeal" in line and "[1]" in line for line in lines)


def test_grounded_template_for_bonded_labour_uses_dm_and_abolition_sections():
    from apps.api.main import _grounded_template_lines
    from apps.api.matter_router import route_matter

    q = "bonded labour my chacha working for thakur 12 years no wages just food bihar"
    passages = [
        {"index": 2, "title": "Bonded Labour System (Abolition) Act 1976", "anchor": "bonded-labour-1976/sec-12"},
        {"index": 3, "title": "Bonded Labour System (Abolition) Act 1976", "anchor": "bonded-labour-1976/sec-4"},
    ]

    lines = _grounded_template_lines(q, route_matter(q), passages)

    assert any("12 years of work without wages" in line and "[3]" in line for line in lines)
    assert any("District Magistrate" in line and "[2]" in line for line in lines)


def test_stage35_grounded_templates_for_final100_safety_hardfails():
    from apps.api.main import _grounded_template_lines
    from apps.api.matter_router import route_matter

    gambling_q = "lost 50k on dream11 like app is online rummy legal in tamil nadu"
    gambling_passages = [
        {"index": 1, "title": "Tamil Nadu Prohibition of Online Gambling and Regulation of Online Games Act 2022", "anchor": "tamil-nadu-online-gambling-2022/sec-7"},
        {"index": 2, "title": "Tamil Nadu Prohibition of Online Gambling and Regulation of Online Games Act 2022", "anchor": "tamil-nadu-online-gambling-2022/sec-14"},
        {"index": 3, "title": "The Public Gambling Act, 1867", "anchor": "public-gambling-1867/sec-12"},
    ]
    gambling = " ".join(_grounded_template_lines(gambling_q, route_matter(gambling_q), gambling_passages))
    assert "consumer refund" in gambling and "Public Gambling Act" in gambling
    assert "victim" not in gambling.lower()

    gig_q = "urban company beautician 3 strike system unfair termination labour law"
    gig_passages = [
        {"index": 1, "title": "Code on Social Security 2020", "anchor": "social-security-code-2020/sec-113"},
        {"index": 2, "title": "Code on Social Security 2020", "anchor": "social-security-code-2020/sec-114-a"},
        {"index": 3, "title": "Industrial Disputes Act 1947", "anchor": "industrial-disputes-1947/sec-25F"},
    ]
    gig = " ".join(_grounded_template_lines(gig_q, route_matter(gig_q), gig_passages))
    assert "Code on Social Security" in gig and "avoid promising reinstatement" in gig

    caste_q = "my caste certificate rejected by tehsildar I am SC how to appeal"
    caste_passages = [
        {"index": 1, "title": "Constitution of India", "anchor": "constitution-india/sec-341"},
        {"index": 2, "title": "Right to Information Act 2005", "anchor": "rti-2005/sec-6"},
        {"index": 3, "title": "Right to Information Act 2005", "anchor": "rti-2005/sec-19-a"},
    ]
    caste = " ".join(_grounded_template_lines(caste_q, route_matter(caste_q), caste_passages))
    assert "Article 341" in caste and "not itself the caste-certificate appeal" in caste

    parsi_q = "parsi mother passed away in mumbai how property divided among us three sisters"
    parsi_passages = [
        {"index": 1, "title": "Indian Succession Act 1925", "anchor": "indian-succession-1925/sec-50"},
        {"index": 2, "title": "Indian Succession Act 1925", "anchor": "indian-succession-1925/sec-51"},
        {"index": 3, "title": "Indian Succession Act 1925", "anchor": "indian-succession-1925/sec-54"},
    ]
    parsi = " ".join(_grounded_template_lines(parsi_q, route_matter(parsi_q), parsi_passages))
    assert "equal one-third shares" in parsi
    assert "Indian Succession" in parsi


def test_stage36_grounded_templates_for_final100_blockers():
    from apps.api.main import _grounded_template_lines
    from apps.api.matter_router import route_matter

    trademark_q = "trademark application opposed by a bigger company saying it is similar to their mark, hearing scheduled"
    trademark_passages = [
        {"index": 1, "title": "Trade Marks Act 1999", "anchor": "trade-marks-1999/sec-21"},
        {"index": 2, "title": "Trade Marks Act 1999", "anchor": "trade-marks-1999/sec-11"},
    ]
    trademark = " ".join(_grounded_template_lines(trademark_q, route_matter(trademark_q), trademark_passages))
    assert "Trade Marks Act" in trademark and "opposition" in trademark and "[1]" in trademark
    assert "relative-grounds" in trademark and "[2]" in trademark
    assert _grounded_template_lines(
        "competitor copied my logo and is using it in market need injunction",
        route_matter("competitor copied my logo and is using it in market need injunction"),
        trademark_passages,
    ) == []

    land_q = "my land taken for highway 4 years back compensation still not received who to ask"
    land_passages = [
        {"index": 1, "title": "Right to Fair Compensation and Transparency in Land Acquisition, Rehabilitation and Resettlement Act 2013", "anchor": "rfctlarr-2013/sec-77"},
        {"index": 2, "title": "Right to Fair Compensation and Transparency in Land Acquisition, Rehabilitation and Resettlement Act 2013", "anchor": "rfctlarr-2013/sec-64"},
    ]
    land = " ".join(_grounded_template_lines(land_q, route_matter(land_q), land_passages))
    assert "RFCTLARR" in land and "property transfer" in land and "[1]" in land
    assert "reference-to-Authority" in land and "[2]" in land

    lok_q = "how to approach Lok Adalat for pending traffic challan settlement"
    lok_passages = [
        {"index": 1, "title": "Legal Services Authorities Act 1987", "anchor": "legal-services-authorities-1987/sec-19"},
        {"index": 2, "title": "Legal Services Authorities Act 1987", "anchor": "legal-services-authorities-1987/sec-20"},
        {"index": 3, "title": "Legal Services Authorities Act 1987", "anchor": "legal-services-authorities-1987/sec-21"},
    ]
    lok = " ".join(_grounded_template_lines(lok_q, route_matter(lok_q), lok_passages))
    assert "Legal Services Authorities Act" in lok and "traffic challan" in lok and "[1]" in lok

    labour_q = "maharashtra labour department raid kiya overtime register not maintained 11 workers what to do"
    labour_passages = [
        {"index": 1, "title": "Maharashtra Shops and Establishments (Regulation of Employment and Conditions of Service) Act 2017", "anchor": "maharashtra-shops-establishments-2017/sec-1"},
        {"index": 2, "title": "Maharashtra Shops and Establishments (Regulation of Employment and Conditions of Service) Act 2017", "anchor": "maharashtra-shops-establishments-2017/sec-15"},
        {"index": 3, "title": "Maharashtra Shops and Establishments (Regulation of Employment and Conditions of Service) Act 2017", "anchor": "maharashtra-shops-establishments-2017/sec-25"},
        {"index": 4, "title": "Building and Other Construction Workers (Regulation of Employment and Conditions of Service) Act 1996", "anchor": "bocw-1996/sec-12"},
    ]
    labour = " ".join(_grounded_template_lines(labour_q, route_matter(labour_q), labour_passages))
    assert "Maharashtra Shops" in labour and "overtime" in labour and "[2]" in labour
    assert "BOCW Act" in labour and "[4]" in labour

    caste_q = "village headman saying my caste cannot enter temple in festival dindori what rights"
    caste_passages = [
        {"index": 1, "title": "Constitution of India", "anchor": "constitution-india/sec-17"},
        {"index": 2, "title": "Protection of Civil Rights Act 1955", "anchor": "protection-civil-rights-1955/sec-3"},
        {"index": 3, "title": "Protection of Civil Rights Act 1955", "anchor": "protection-civil-rights-1955/sec-7"},
    ]
    caste = " ".join(_grounded_template_lines(caste_q, route_matter(caste_q), caste_passages))
    assert "Article 17" in caste and "[1]" in caste
    assert "Protection of Civil Rights Act" in caste and "[2]" in caste

    banking_q = "bajaj finserv EMI bounced because of bank error, now they are charging 6000 penalty and threatening CIBIL"
    banking_passages = [
        {"index": 1, "title": "Reserve Bank Integrated Ombudsman Scheme 2021", "anchor": "rbi-integrated-ombudsman-2021/sec-2"},
        {"index": 2, "title": "Credit Information Companies (Regulation) Act 2005", "anchor": "credit-information-companies-2005/sec-21"},
        {"index": 3, "title": "Consumer Protection Act 2019", "anchor": "consumer-protection-2019/sec-35"},
    ]
    banking = " ".join(_grounded_template_lines(banking_q, route_matter(banking_q), banking_passages))
    assert "RBI Integrated Ombudsman" in banking and "[1]" in banking
    assert "Credit Information Companies Act" in banking and "[2]" in banking


def test_grounded_template_for_pregnant_undertrial_cites_article21_and_bnss():
    from apps.api.main import _grounded_template_lines
    from apps.api.matter_router import route_matter

    q = "paralegal volunteer 4 women undertrials byculla pregnant where rule postpone trial bail"
    passages = [
        {
            "index": 1,
            "title": "Constitution of India",
            "anchor": "constitution-india/sec-21",
            "text": "Article 21 protects life and personal liberty.",
        },
        {
            "index": 5,
            "title": "Bharatiya Nagarik Suraksha Sanhita 2023",
            "anchor": "bnss-2023/sec-480-a",
            "text": "The Court may release an accused person on bail if such person is a woman or is sick or infirm.",
        },
    ]

    lines = _grounded_template_lines(q, route_matter(q), passages)

    assert any("life and personal liberty" in line and "[1]" in line for line in lines)
    assert any("woman, sick, or infirm" in line and "[5]" in line for line in lines)


def test_grounded_template_for_security_cheque_is_drawer_safe():
    from apps.api.main import _grounded_template_lines
    from apps.api.matter_router import route_matter

    passages = [
        {
            "index": 2,
            "title": "Negotiable Instruments Act 1881",
            "anchor": "negotiable-instruments-1881/sec-138",
            "text": "Section 138 applies to a cheque drawn for discharge of a debt or other liability, and the payee or holder in due course gives notice to the drawer.",
        }
    ]

    for q in (
        "i issued post dated cheques as security to my landlord, he is now misusing them after i vacated, what to do",
        "i gave blank cheque to landlord as security and he sent notice under 138 what defence",
        "landlord took my cheque as security and is threatening 138 case",
    ):
        lines = _grounded_template_lines(q, route_matter(q), passages)
        joined = " ".join(lines)

        assert "drawer-defence" in joined
        assert "debt or other liability" in joined
        assert "file a complaint" not in joined.lower()


def test_grounded_template_for_private_magistrate_complaint_cites_bnss_sources():
    from apps.api.main import _grounded_template_lines
    from apps.api.matter_router import route_matter

    q = "how to file private complaint before magistrate when police inaction"
    passages = [
        {
            "index": 1,
            "title": "Bharatiya Nagarik Suraksha Sanhita 2023",
            "anchor": "bnss-2023/sec-223@2024-07-01",
            "text": "A Magistrate taking cognizance of an offence on complaint shall examine upon oath the complainant and witnesses.",
        },
        {
            "index": 2,
            "title": "Bharatiya Nagarik Suraksha Sanhita 2023",
            "anchor": "bnss-2023/sec-175@2024-07-01",
            "text": "The Magistrate may order an investigation by police.",
        },
    ]

    lines = _grounded_template_lines(q, route_matter(q), passages)
    joined = " ".join(lines)

    assert "complainant and witnesses on oath [1]" in joined
    assert "order an investigation" in joined and "[2]" in joined


def test_grounded_template_for_caste_fir_refusal_cites_scst_and_bnss():
    from apps.api.main import _grounded_template_lines
    from apps.api.matter_router import route_matter

    q = "police refusing FIR caste atrocity case sub inspector saying it is small matter jharkhand"
    passages = [
        {
            "index": 1,
            "title": "Scheduled Castes and Scheduled Tribes (Prevention of Atrocities) Act 1989",
            "anchor": "sc-st-poa-1989/sec-3-a@2025-09-21",
            "text": "Whoever, not being a member of a Scheduled Caste or a Scheduled Tribe, commits an offence listed in this section.",
        },
        {
            "index": 2,
            "title": "Bharatiya Nagarik Suraksha Sanhita 2023",
            "anchor": "bnss-2023/sec-173-c@2024-07-01",
            "text": "Information relating to a cognizable offence may be given to police and recorded under this provision.",
        },
        {
            "index": 3,
            "title": "Bharatiya Nagarik Suraksha Sanhita 2023",
            "anchor": "bnss-2023/sec-175@2024-07-01",
            "text": "A Magistrate may order an investigation by police.",
        },
    ]

    lines = _grounded_template_lines(q, route_matter(q), passages)
    joined = " ".join(lines)

    assert "SC/ST POA source" in joined and "[1]" in joined
    assert "FIR/refusal procedure" in joined and "[2]" in joined
    assert "Magistrate-ordered investigation" in joined and "[3]" in joined


def test_grounded_template_for_domestic_acid_threat_cites_pwdva_bns_bnss():
    from apps.api.main import _grounded_template_lines
    from apps.api.matter_router import route_matter

    q = "my mother in law is threatening to throw acid on me if I don't get more money from my parents"
    passages = [
        {
            "index": 1,
            "title": "Protection of Women from Domestic Violence Act 2005",
            "anchor": "domestic-violence-2005/sec-18@1974-01-01",
            "text": "The Magistrate may pass a protection order prohibiting acts of domestic violence.",
        },
        {
            "index": 2,
            "title": "Bharatiya Nyaya Sanhita 2023",
            "anchor": "bns-2023/sec-351@2024-07-01",
            "text": "Whoever threatens another with injury to person, reputation or property commits criminal intimidation.",
        },
        {
            "index": 3,
            "title": "Bharatiya Nagarik Suraksha Sanhita 2023",
            "anchor": "bnss-2023/sec-173-a@2024-07-01",
            "text": "Information relating to a cognizable offence shall be given to the police officer in charge.",
        },
    ]

    lines = _grounded_template_lines(q, route_matter(q), passages)
    joined = " ".join(lines)

    assert "protection-order route" in joined and "[1]" in joined
    assert "criminal intimidation" in joined and "[2]" in joined
    assert "police track" in joined and "[3]" in joined


def test_grounded_template_for_domestic_violence_safety_is_user_shaped():
    from apps.api.main import _grounded_template_lines
    from apps.api.matter_router import route_matter

    passages = [
        {
            "index": 1,
            "title": "Protection of Women from Domestic Violence Act 2005",
            "anchor": "domestic-violence-2005/sec-3@1974-01-01",
            "text": "Domestic violence includes physical, verbal, emotional and economic abuse.",
        },
        {
            "index": 2,
            "title": "Protection of Women from Domestic Violence Act 2005",
            "anchor": "domestic-violence-2005/sec-18@1974-01-01",
            "text": "A Magistrate may pass a protection order.",
        },
        {
            "index": 3,
            "title": "Protection of Women from Domestic Violence Act 2005",
            "anchor": "domestic-violence-2005/sec-19@1974-01-01",
            "text": "A Magistrate may pass a residence order.",
        },
        {
            "index": 4,
            "title": "Protection of Women from Domestic Violence Act 2005",
            "anchor": "domestic-violence-2005/sec-12@1974-01-01",
            "text": "An application may be presented to the Magistrate.",
        },
        {
            "index": 5,
            "title": "Bharatiya Nyaya Sanhita 2023",
            "anchor": "bns-2023/sec-115@2024-07-01",
            "text": "Voluntarily causing hurt is punishable.",
        },
    ]

    slap_q = "please help he gets angry and slaps me but says sorry next day my parents say all marriages are like this should I stay"
    slap_joined = " ".join(_grounded_template_lines(slap_q, route_matter(slap_q), passages))

    assert "do not have to treat being hit, slapped, or beaten as normal" in slap_joined
    assert "protection-order source" in slap_joined and "[2]" in slap_joined
    assert "BNS hurt source" in slap_joined and "[5]" in slap_joined
    assert "asking whether to stay" in slap_joined

    residence_q = "sasural waale mujhe ghar se nikal diya raat ko bina kuch diye kya main wapis ja sakti hoon"
    residence_joined = " ".join(_grounded_template_lines(residence_q, route_matter(residence_q), passages))

    assert "ghar se nikal diya / can I go back" in residence_joined
    assert "residence protection" in residence_joined and "[3]" in residence_joined
    assert "ghar se nikal diya or thrown you out" in residence_joined
    assert "Protection Officer" in residence_joined

    immediate_q = "my husband is beating me right now what should I do"
    immediate_joined = " ".join(_grounded_template_lines(immediate_q, route_matter(immediate_q), passages))

    assert "beating you right now" in immediate_joined
    assert "Because he is beating you right now" in immediate_joined
    assert "move to immediate safety first" in immediate_joined


def test_common_screenshot_templates_for_bank_municipal_pan_and_loan_app():
    from apps.api.main import (
        _grounded_template_lines,
        _is_bank_account_freeze_query,
        _is_safe_template_source_bridge,
        _prompt_retrieval_candidates,
        _should_skip_contract_source_line,
    )
    from apps.api.matter_router import route_matter

    bank_passages = [
        {
            "index": 1,
            "title": "Reserve Bank Integrated Ombudsman Scheme 2021",
            "anchor": "rbi-integrated-ombudsman-2021/sec-2",
            "text": "The Scheme applies to Regulated Entities as defined in it.",
        },
        {
            "index": 2,
            "title": "Banking Regulation Act 1949",
            "anchor": "banking-regulation-1949/sec-5",
            "text": "Banking company records and banking business provisions.",
        },
    ]
    freeze_joined = " ".join(_grounded_template_lines("my bank account is frozen what to do", route_matter("my bank account is frozen what to do"), bank_passages))
    assert "freeze/lien/KYC reason" in freeze_joined
    assert "RBI Ombudsman" in freeze_joined
    assert _is_bank_account_freeze_query("my bank account is frozen what to do")
    assert not _is_bank_account_freeze_query("my instagram account is frozen what to do")
    assert not _is_bank_account_freeze_query("my zerodha account is frozen what to do")

    loan_app_passages = [
        {
            "index": 1,
            "title": "Reserve Bank Integrated Ombudsman Scheme 2021",
            "anchor": "rbi-integrated-ombudsman-2021/sec-2",
            "text": "Regulated Entity includes banks and non-banking financial companies covered by the Scheme.",
        },
        {
            "index": 2,
            "title": "Digital Personal Data Protection Act 2023",
            "anchor": "dpdp-2023/sec-13",
            "text": "A Data Principal may seek grievance redressal.",
        },
    ]
    loan_joined = " ".join(_grounded_template_lines("Loan app is harassing my contacts", route_matter("Loan app is harassing my contacts"), loan_app_passages))
    assert "Loan-app or recovery harassment" in loan_joined
    assert "contact list" in loan_joined
    loan_route = route_matter("Loan app is harassing my contacts")
    assert _is_safe_template_source_bridge(
        "If the app is using your contact list, keep a separate personal-data grievance track [2].",
        loan_route,
    )
    assert _should_skip_contract_source_line(
        loan_route,
        "banking_regulation_1949",
        {"rbi_integrated_ombudsman_2021", "dpdp_2023"},
    )

    municipal_passages = [
        {
            "index": 1,
            "title": "Right to Information Act 2005",
            "anchor": "rti-2005/sec-6",
            "text": "A person may request information from a public authority.",
        }
    ]
    municipal_joined = " ".join(_grounded_template_lines("My shop is in Gujarat and municipality sealed it.", route_matter("My shop is in Gujarat and municipality sealed it."), municipal_passages))
    assert "sealing order" in municipal_joined
    assert "show-cause notice" in municipal_joined
    municipal_route = route_matter("My shop is in Gujarat and municipality sealed it.")
    filtered = _prompt_retrieval_candidates(
        "My shop is in Gujarat and municipality sealed it.",
        municipal_route,
        [
            SimpleNamespace(title="Food Safety and Standards Act 2006", anchor="food-safety-standards-2006/sec-31"),
            SimpleNamespace(title="Right to Information Act 2005", anchor="rti-2005/sec-6"),
        ],
    )
    assert [hit.title for hit in filtered] == ["Right to Information Act 2005"]
    assert _is_safe_template_source_bridge(
        "For a municipality sealing a shop, the safe first step is to get the sealing order [1].",
        municipal_route,
    )

    pan_passages = [
        {
            "index": 1,
            "title": "Income-tax Act 1961",
            "anchor": "income-tax-1961/sec-139-a",
            "text": "Permanent Account Number provisions and return records.",
        },
        {
            "index": 2,
            "title": "Aadhaar (Targeted Delivery of Financial and Other Subsidies, Benefits and Services) Act 2016",
            "anchor": "aadhaar-2016/sec-8",
            "text": "Authentication of Aadhaar number may be performed with consent.",
        },
    ]
    pan_joined = " ".join(_grounded_template_lines("my pan and aadhaar is mismatch", route_matter("my pan and aadhaar is mismatch"), pan_passages))
    assert "PAN/Aadhaar mismatch" in pan_joined
    assert "not treat this as a caste, ration, or generic welfare issue" in pan_joined


def test_domestic_violence_template_is_role_aware_for_wife_as_aggressor():
    from apps.api.main import _grounded_template_lines
    from apps.api.matter_router import route_matter

    passages = [
        {
            "index": 1,
            "title": "Bharatiya Nyaya Sanhita 2023",
            "anchor": "bns-2023/sec-115@2024-07-01",
            "text": "Voluntarily causing hurt is punishable.",
        },
        {
            "index": 2,
            "title": "Bharatiya Nagarik Suraksha Sanhita 2023",
            "anchor": "bnss-2023/sec-173@2024-07-01",
            "text": "Information relating to a cognizable offence shall be given to the officer in charge of a police station.",
        },
        {
            "index": 3,
            "title": "Bharatiya Nyaya Sanhita 2023",
            "anchor": "bns-2023/sec-316@2024-07-01",
            "text": "Criminal breach of trust concerns property entrusted and dishonest misappropriation.",
        },
        {
            "index": 4,
            "title": "Bharatiya Nyaya Sanhita 2023",
            "anchor": "bns-2023/sec-351@2024-07-01",
            "text": "Criminal intimidation concerns threats of injury to person, reputation, or property.",
        },
    ]

    slap_joined = " ".join(_grounded_template_lines("my wife slapped me what to do", route_matter("my wife slapped me what to do"), passages))
    salary_joined = " ".join(_grounded_template_lines("my wife took my salary atm card what to do", route_matter("my wife took my salary atm card what to do"), passages))
    threat_joined = " ".join(_grounded_template_lines("my wife threatens me what to do", route_matter("my wife threatens me what to do"), passages))
    thrown_out_joined = " ".join(_grounded_template_lines("my wife threw me out of house what to do", route_matter("my wife threw me out of house what to do"), passages))
    jewellery_joined = " ".join(_grounded_template_lines("my wife took my jewellery what to do", route_matter("my wife took my jewellery what to do"), passages))
    sexual_joined = " ".join(_grounded_template_lines("my wife forced sex without consent what to do", route_matter("my wife forced sex without consent what to do"), passages))

    assert "PWDVA" not in slap_joined
    assert "BNS hurt" in slap_joined and "[1]" in slap_joined
    assert "information to police" in slap_joined and "[2]" in slap_joined
    assert "wife took my jewellery/salary/ATM card" in salary_joined
    assert "breach-of-trust" in salary_joined and "[3]" in salary_joined
    assert "PWDVA" not in threat_joined
    assert "criminal-intimidation" in threat_joined and "[4]" in threat_joined
    assert "PWDVA" not in thrown_out_joined
    assert "wife threw/kicked/locked me out" in thrown_out_joined and "[4]" in thrown_out_joined
    assert "PWDVA" not in jewellery_joined
    assert "jewellery" in jewellery_joined and "[3]" in jewellery_joined
    assert "PWDVA" not in sexual_joined
    assert "final offence classification" in sexual_joined
    assert "sexual-coercion fact" in sexual_joined


def test_matrimonial_property_maintenance_template_avoids_irrelevant_criminal_or_bigamy_facts():
    from apps.api.main import _grounded_template_lines
    from apps.api.matter_router import route_matter

    passages = [
        {
            "index": 1,
            "title": "Family Courts Act 1984",
            "anchor": "family-courts-1984/sec-7@1984-09-14",
            "text": "A Family Court has jurisdiction over suits and proceedings between parties to a marriage for property disputes, maintenance, and matrimonial relief.",
        },
        {
            "index": 2,
            "title": "Hindu Marriage Act 1955",
            "anchor": "hindu-marriage-1955/sec-24@1955-05-18",
            "text": "The court may order maintenance pendente lite and expenses of proceedings.",
        },
    ]

    q = "my wife is asking maintenance and share in my property what to do"
    joined = " ".join(_grounded_template_lines(q, route_matter(q), passages))

    assert "Family Courts Act source" in joined and "[1]" in joined
    assert "HMA source" in joined and "[2]" in joined
    assert "previous marriage" not in joined
    assert "CrPC" not in joined
    assert "BNS" not in joined
    assert "criminal complaint" in joined


def test_grounded_template_for_cyber_blackmail_cites_bns_and_it_act():
    from apps.api.main import _grounded_template_lines
    from apps.api.matter_router import route_matter

    q = "bumble guy is blackmailing me threatening to send screenshots to my dad"
    passages = [
        {
            "index": 1,
            "title": "Bharatiya Nyaya Sanhita 2023",
            "anchor": "bns-2023/sec-351@2024-07-01",
            "text": "Whoever threatens another with injury to person, reputation or property commits criminal intimidation.",
        },
        {
            "index": 2,
            "title": "Information Technology Act 2000",
            "anchor": "it-2000/sec-66E",
            "text": "Whoever intentionally captures, publishes or transmits the image of a private area of any person without consent violates privacy.",
        },
    ]

    lines = _grounded_template_lines(q, route_matter(q), passages)
    joined = " ".join(lines)

    assert "criminal intimidation" in joined and "[1]" in joined
    assert "IT Act source" in joined and "[2]" in joined


def test_grounded_template_for_senior_maintenance_cheque_cites_senior_and_ni():
    from apps.api.main import _grounded_template_lines
    from apps.api.matter_router import route_matter

    q = "son gave me cheque for monthly maintenance it bounced twice can i file case"
    passages = [
        {
            "index": 1,
            "title": "Maintenance and Welfare of Parents and Senior Citizens Act 2007",
            "anchor": "mwp-2007/sec-4",
            "text": "A senior citizen including parent unable to maintain himself from earnings or property shall be entitled to maintenance from children or relatives.",
        },
        {
            "index": 2,
            "title": "Negotiable Instruments Act 1881",
            "anchor": "negotiable-instruments-1881/sec-138",
            "text": "Section 138 applies to a cheque drawn for discharge of a debt or other liability returned unpaid after demand notice.",
        },
    ]

    lines = _grounded_template_lines(q, route_matter(q), passages)
    joined = " ".join(lines)

    assert "Senior Citizens Act source" in joined and "[1]" in joined
    assert "NI Act source" in joined and "[2]" in joined


def test_grounded_template_for_education_loan_cites_rbi_and_consumer():
    from apps.api.main import _grounded_template_lines
    from apps.api.matter_router import route_matter

    q = "bank not giving education loan to my daughter even though we have scholarship paper"
    passages = [
        {
            "index": 1,
            "title": "Reserve Bank Integrated Ombudsman Scheme 2021",
            "anchor": "rbi-integrated-ombudsman-2021/sec-3",
            "text": "The Scheme applies to regulated entities and complaints about deficiency in service.",
        },
        {
            "index": 2,
            "title": "Consumer Protection Act 2019",
            "anchor": "consumer-protection-2019/sec-2-i@2021-09-17",
            "text": "Deficiency means fault, imperfection, shortcoming or inadequacy in quality, nature or manner of performance.",
        },
    ]

    lines = _grounded_template_lines(q, route_matter(q), passages)
    joined = " ".join(lines)

    assert "Reserve Bank Integrated Ombudsman source" in joined and "[1]" in joined
    assert "Consumer Protection Act source" in joined and "[2]" in joined


def test_single_source_templates_do_not_bundle_missing_forums():
    from apps.api.main import _grounded_template_lines
    from apps.api.matter_router import route_matter

    caste_lines = _grounded_template_lines(
        "police refusing FIR caste atrocity case sub inspector saying it is small matter jharkhand",
        route_matter("police refusing FIR caste atrocity case sub inspector saying it is small matter jharkhand"),
        [{
            "index": 1,
            "title": "Scheduled Castes and Scheduled Tribes (Prevention of Atrocities) Act 1989",
            "anchor": "sc-st-poa-1989/sec-3-a@2025-09-21",
            "text": "Whoever, not being a member of a Scheduled Caste or a Scheduled Tribe, commits an offence listed in this section.",
        }],
    )
    caste_joined = " ".join(caste_lines)
    assert "Magistrate-investigation route" not in caste_joined
    assert "Superintendent of Police" not in caste_joined

    caste_bnss173_lines = _grounded_template_lines(
        "police refusing FIR caste atrocity case sub inspector saying it is small matter jharkhand",
        route_matter("police refusing FIR caste atrocity case sub inspector saying it is small matter jharkhand"),
        [{
            "index": 1,
            "title": "Bharatiya Nagarik Suraksha Sanhita 2023",
            "anchor": "bnss-2023/sec-173-c@2024-07-01",
            "text": "Information relating to a cognizable offence may be given to police and recorded under this provision.",
        }],
    )
    caste_bnss173_joined = " ".join(caste_bnss173_lines)
    assert "Magistrate-ordered investigation" not in caste_bnss173_joined
    assert "investigation-order" not in caste_bnss173_joined

    acid_lines = _grounded_template_lines(
        "my mother in law is threatening to throw acid on me if I don't get more money from my parents",
        route_matter("my mother in law is threatening to throw acid on me if I don't get more money from my parents"),
        [{
            "index": 1,
            "title": "Bharatiya Nyaya Sanhita 2023",
            "anchor": "bns-2023/sec-351@2024-07-01",
            "text": "Whoever threatens another with injury to person, reputation or property commits criminal intimidation.",
        }],
    )
    acid_joined = " ".join(acid_lines)
    assert "Magistrate protection" not in acid_joined
    assert "police track" not in acid_joined

    honour_lines = _grounded_template_lines(
        "my daughter eloped with boy of other religion family threatening her with khap panchayat",
        route_matter("my daughter eloped with boy of other religion family threatening her with khap panchayat"),
        [{
            "index": 1,
            "title": "Bharatiya Nyaya Sanhita 2023",
            "anchor": "bns-2023/sec-351@2024-07-01",
            "text": "Whoever threatens another with injury to person, reputation or property commits criminal intimidation.",
        }],
    )
    honour_joined = " ".join(honour_lines)
    assert "written complaint" not in honour_joined
    assert "acknowledgement" not in honour_joined
    assert "police do not act" not in honour_joined

    honour_bnss216_lines = _grounded_template_lines(
        "my daughter eloped with boy of other religion family threatening her with khap panchayat",
        route_matter("my daughter eloped with boy of other religion family threatening her with khap panchayat"),
        [{
            "index": 1,
            "title": "Bharatiya Nagarik Suraksha Sanhita 2023",
            "anchor": "bnss-2023/sec-216@2024-07-01",
            "text": "This provision concerns threats connected with false evidence or witness-related procedure.",
        }],
    )
    honour_bnss216_joined = " ".join(honour_bnss216_lines)
    assert "criminal-court complaint route" not in honour_bnss216_joined
    assert "complaint-route source" not in honour_bnss216_joined

    education_lines = _grounded_template_lines(
        "bank not giving education loan to my daughter even though we have scholarship paper",
        route_matter("bank not giving education loan to my daughter even though we have scholarship paper"),
        [{
            "index": 1,
            "title": "Consumer Protection Act 2019",
            "anchor": "consumer-protection-2019/sec-2-i@2021-09-17",
            "text": "Deficiency means fault, imperfection, shortcoming or inadequacy in quality, nature or manner of performance.",
        }],
    )
    education_joined = " ".join(education_lines)
    assert "RBI Ombudsman" not in education_joined
    assert "banking-ombudsman track" not in education_joined

    senior_lines = _grounded_template_lines(
        "son gave me cheque for monthly maintenance it bounced twice can i file case",
        route_matter("son gave me cheque for monthly maintenance it bounced twice can i file case"),
        [{
            "index": 1,
            "title": "Negotiable Instruments Act 1881",
            "anchor": "negotiable-instruments-1881/sec-138",
            "text": "Section 138 applies to a cheque drawn for discharge of a debt or other liability returned unpaid after demand notice.",
        }],
    )
    senior_joined = " ".join(senior_lines)
    assert "Maintenance Tribunal" not in senior_joined
    assert "parent-support track" not in senior_joined

    undertrial_lines = _grounded_template_lines(
        "i undertrial 3 yrs in puzhal lawyer not coming hearings when can complain",
        route_matter("i undertrial 3 yrs in puzhal lawyer not coming hearings when can complain"),
        [{
            "index": 1,
            "title": "Bharatiya Nagarik Suraksha Sanhita 2023",
            "anchor": "bnss-2023/sec-479@2024-07-01",
            "text": "An undertrial prisoner detained for the specified period may be released on bail.",
        }],
    )
    undertrial_joined = " ".join(undertrial_lines)
    assert "District Legal Services Authority" not in undertrial_joined
    assert "legal-aid support" not in undertrial_joined


def test_grounded_template_for_undertrial_legal_aid_cites_lsa_and_bnss():
    from apps.api.main import _grounded_template_lines
    from apps.api.matter_router import route_matter

    q = "i undertrial 3 yrs in puzhal lawyer not coming hearings when can complain"
    passages = [
        {
            "index": 1,
            "title": "Legal Services Authorities Act 1987",
            "anchor": "legal-services-authorities-1987/sec-9",
            "text": "The State Government shall constitute a District Legal Services Authority for every District.",
        },
        {
            "index": 2,
            "title": "Bharatiya Nagarik Suraksha Sanhita 2023",
            "anchor": "bnss-2023/sec-479@2024-07-01",
            "text": "An undertrial prisoner detained for the specified period may be released on bail.",
        },
    ]

    lines = _grounded_template_lines(q, route_matter(q), passages)
    joined = " ".join(lines)

    assert "Legal Services Authorities source" in joined and "[1]" in joined
    assert "BNSS source" in joined and "[2]" in joined


def test_grounded_template_for_custody_compensation_uses_timeline_and_liberty_sources():
    from apps.api.main import _grounded_template_lines
    from apps.api.matter_router import route_matter

    q = "i was in yerwada 18 months theft case now released want compensation for delay"
    passages = [
        {
            "index": 1,
            "title": "Constitution of India",
            "anchor": "constitution-india/sec-21",
            "text": "No person shall be deprived of life or personal liberty except according to procedure established by law.",
        },
        {
            "index": 2,
            "title": "Bharatiya Nagarik Suraksha Sanhita 2023",
            "anchor": "bnss-2023/sec-479@2024-07-01",
            "text": "An undertrial prisoner detained for the specified period may be released on bail.",
        },
        {
            "index": 3,
            "title": "Code of Criminal Procedure 1973",
            "anchor": "crpc-1973/sec-436-a",
            "text": "Where a person has undergone detention for the stated period, release on personal bond may apply.",
        },
    ]

    lines = _grounded_template_lines(q, route_matter(q), passages)
    joined = " ".join(lines)

    assert "Article 21 liberty source" in joined and "[1]" in joined
    assert "BNSS Section 479 source" in joined and "[2]" in joined
    assert "dated timeline" in joined
    assert "Human Rights Commission" in joined


def test_grounded_template_for_identity_police_threat_cites_constitution_and_bns():
    from apps.api.main import _grounded_template_lines
    from apps.api.matter_router import route_matter

    q = "manager threatening to call police saying we are bangladeshi but we are from murshidabad what to do"
    passages = [
        {
            "index": 1,
            "title": "Constitution of India",
            "anchor": "constitution-india/sec-21",
            "text": "No person shall be deprived of his life or personal liberty except according to procedure established by law.",
        },
        {
            "index": 2,
            "title": "Bharatiya Nyaya Sanhita 2023",
            "anchor": "bns-2023/sec-351@2024-07-01",
            "text": "Whoever threatens another with injury to person, reputation or property commits criminal intimidation.",
        },
    ]

    lines = _grounded_template_lines(q, route_matter(q), passages)
    joined = " ".join(lines)

    assert "Constitution source" in joined and "[1]" in joined
    assert "criminal intimidation" in joined and "[2]" in joined


def test_grounded_template_for_bonded_labour_does_not_inject_missing_wage_facts():
    from apps.api.main import _grounded_template_lines
    from apps.api.matter_router import route_matter

    q = "brick kiln owner keeping family hostage advance 25000 cannot go home"
    passages = [
        {"index": 2, "title": "Bonded Labour System (Abolition) Act 1976", "anchor": "bonded-labour-1976/sec-12"},
        {"index": 3, "title": "Bonded Labour System (Abolition) Act 1976", "anchor": "bonded-labour-1976/sec-4"},
    ]

    lines = _grounded_template_lines(q, route_matter(q), passages)

    assert lines
    assert not any("years of work without wages" in line for line in lines)


def test_grounded_template_for_bonded_labour_advance_restriction_works_with_dm_section_only():
    from apps.api.main import _grounded_template_lines
    from apps.api.matter_router import route_matter

    q = "thekedar took 18000 advance from me darbhanga not letting leave bangalore site"
    passages = [
        {"index": 2, "title": "Bonded Labour System (Abolition) Act 1976", "anchor": "bonded-labour-1976/sec-12"},
    ]

    lines = _grounded_template_lines(q, route_matter(q), passages)

    assert any("advance to stop you leaving" in line and "[2]" in line for line in lines)
    assert any("Darbhanga-to-Bangalore" in line and "[2]" in line for line in lines)


def test_grounded_template_for_arrest_production_delay_cites_article22_and_bnss():
    from apps.api.main import _grounded_template_lines
    from apps.api.matter_router import route_matter

    q = "papa arrest 5 din ho gaya magistrate ke samne kab le jana hota hai"
    passages = [
        {"index": 1, "title": "Constitution of India", "anchor": "constitution-india/sec-22"},
        {"index": 2, "title": "Bharatiya Nagarik Suraksha Sanhita 2023", "anchor": "bnss-2023/sec-58"},
        {"index": 3, "title": "Bharatiya Nagarik Suraksha Sanhita 2023", "anchor": "bnss-2023/sec-57"},
    ]

    lines = _grounded_template_lines(q, route_matter(q), passages)
    joined = " ".join(lines)

    assert "Article 22" in joined and "[1]" in joined
    assert "24 hours" in joined and "[2]" in joined
    assert "without unnecessary delay" in joined and "[3]" in joined
    assert "'5 din' in police custody" in joined and "[1]" in joined


def test_grounded_template_for_bonded_labour_release_and_aadhaar_followups():
    from apps.api.main import _grounded_template_lines
    from apps.api.matter_router import route_matter

    release_q = "release certificate not given to bonded labour rehab money pending 3 years jharkhand"
    release_passages = [
        {"index": 1, "title": "Bonded Labour System (Abolition) Act 1976", "anchor": "bonded-labour-1976/sec-4"},
        {"index": 2, "title": "Bonded Labour System (Abolition) Act 1976", "anchor": "bonded-labour-1976/sec-12"},
        {"index": 3, "title": "Bonded Labour System (Abolition) Act 1976", "anchor": "bonded-labour-1976/sec-13"},
    ]
    release_joined = " ".join(_grounded_template_lines(release_q, route_matter(release_q), release_passages))

    assert "release-certificate" in release_joined and "[2]" in release_joined
    assert "Vigilance Committee" in release_joined and "[3]" in release_joined

    aadhaar_q = "thekedar took my aadhaar original 6 months back not returning he keeping bihar workers id"
    aadhaar_passages = [
        {"index": 2, "title": "Bonded Labour System (Abolition) Act 1976", "anchor": "bonded-labour-1976/sec-12"},
        {"index": 4, "title": "Aadhaar Act 2016", "anchor": "aadhaar-2016/sec-29"},
    ]
    aadhaar_joined = " ".join(_grounded_template_lines(aadhaar_q, route_matter(aadhaar_q), aadhaar_passages))

    assert "Aadhaar" in aadhaar_joined and "[4]" in aadhaar_joined
    assert "District Magistrate" in aadhaar_joined and "[2]" in aadhaar_joined


def test_grounded_template_for_ration_portability_fd_nominee_and_child_return():
    from apps.api.main import _grounded_template_lines
    from apps.api.matter_router import route_matter

    ration_q = "ration card west bengal not working in chennai shop no rice for family one nation one card not happening"
    ration_passages = [
        {"index": 1, "title": "National Food Security Act 2013", "anchor": "national-food-security-2013/sec-3"},
        {"index": 2, "title": "National Food Security Act 2013", "anchor": "national-food-security-2013/sec-14"},
        {"index": 3, "title": "National Food Security Act 2013", "anchor": "national-food-security-2013/sec-15"},
    ]
    ration_joined = " ".join(_grounded_template_lines(ration_q, route_matter(ration_q), ration_passages))
    assert "Chennai ration shop under portability" in ration_joined and "[1]" in ration_joined
    assert "District Grievance Redressal Officer" in ration_joined and "[3]" in ration_joined

    fd_q = "private cooperative bank fd of grandfather not honoured nominee facing harassment"
    fd_passages = [
        {"index": 4, "title": "Banking Regulation Act 1949", "anchor": "banking-regulation-1949/sec-45ZA-a"},
        {"index": 5, "title": "Consumer Protection Act 2019", "anchor": "consumer-protection-2019/sec-2-42"},
        {"index": 9, "title": "Reserve Bank Integrated Ombudsman Scheme 2021", "anchor": "rbi-integrated-ombudsman-2021/sec-2"},
    ]
    fd_joined = " ".join(_grounded_template_lines(fd_q, route_matter(fd_q), fd_passages))
    assert "section 45ZA" in fd_joined and "[4]" in fd_joined
    assert "service-deficiency" in fd_joined and "[5]" in fd_joined
    assert "RBI Ombudsman" in fd_joined and "[9]" in fd_joined

    custody_q = "my husband took our 5 year old to delhi during fight and is not letting me meet how do I get her back fast"
    custody_passages = [
        {"index": 6, "title": "Guardians and Wards Act 1890", "anchor": "guardians-wards-1890/sec-25"},
        {"index": 7, "title": "Guardians and Wards Act 1890", "anchor": "guardians-wards-1890/sec-17"},
        {"index": 8, "title": "Constitution of India", "anchor": "constitution-india/sec-21"},
    ]
    custody_joined = " ".join(_grounded_template_lines(custody_q, route_matter(custody_q), custody_passages))
    assert "custody-return" in custody_joined and "[6]" in custody_joined
    assert "minor's welfare" in custody_joined and "[7]" in custody_joined
    assert "Article 21" in custody_joined and "[8]" in custody_joined


def test_grounded_template_for_minor_deepfake_cites_pocso_and_it67b():
    from apps.api.main import _grounded_template_lines
    from apps.api.matter_router import route_matter

    q = "my schoolmate is making deepfake nude videos of girls in class using AI and circulating I am one of them I am 15"
    passages = [
        {"index": 1, "title": "Protection of Children from Sexual Offences Act 2012", "anchor": "pocso-2012/sec-14"},
        {"index": 2, "title": "Information Technology Act 2000", "anchor": "it-2000/sec-67B"},
        {"index": 3, "title": "Bharatiya Nyaya Sanhita 2023", "anchor": "bns-2023/sec-77"},
    ]

    lines = _grounded_template_lines(q, route_matter(q), passages)
    joined = " ".join(lines)

    assert "POCSO" in joined and "[1]" in joined
    assert "IT Act child" in joined and "[2]" in joined
    assert "BNS voyeurism" in joined and "[3]" in joined


def test_grounded_template_for_birth_certificate_uses_rti_without_generic_pension_text():
    from apps.api.main import _grounded_template_lines
    from apps.api.matter_router import route_matter

    q = "panchayat secretary not giving me birth certificate of my child born at home"
    passages = [
        {"index": 3, "title": "Right to Information Act 2005", "anchor": "rti-2005/sec-6"},
        {"index": 4, "title": "Right to Information Act 2005", "anchor": "rti-2005/sec-7"},
        {"index": 5, "title": "Right to Information Act 2005", "anchor": "rti-2005/sec-19"},
    ]

    lines = _grounded_template_lines(q, route_matter(q), passages)

    assert any("birth certificate born at home" in line and "[3]" in line for line in lines)
    assert any("panchayat or registrar" in line and "[3]" in line for line in lines)
    assert any("official's refusal" in line and "[3]" in line for line in lines)
    assert not any("pension" in line.lower() for line in lines)


def test_grounded_template_for_witch_accused_false_case_keeps_tonhi_context():
    from apps.api.main import _grounded_template_lines
    from apps.api.matter_router import route_matter

    q = "they say i am tonhi after child died in village false case filed chhattisgarh"
    passages = [
        {"index": 1, "title": "Bharatiya Nagarik Suraksha Sanhita 2023", "anchor": "bnss-2023/sec-483"},
    ]

    lines = _grounded_template_lines(q, route_matter(q), passages)

    assert any("Chhattisgarh tonhi false-case matter" in line and "[1]" in line for line in lines)
    assert any("High Court or Court of Session" in line and "[1]" in line for line in lines)
    assert not any("indexed witch-hunting source" in line for line in lines)


def test_grounded_template_for_construction_injury_covers_bocw_and_compensation():
    from apps.api.main import _grounded_template_lines
    from apps.api.matter_router import route_matter

    q = "fell from 5th floor site whitefield bangalore leg broken thekedar saying no insurance no bocw card"
    passages = [
        {"index": 1, "title": "Employees' Compensation Act 1923", "anchor": "employees-compensation-1923/sec-3"},
        {"index": 2, "title": "Employees' Compensation Act 1923", "anchor": "employees-compensation-1923/sec-22"},
        {"index": 8, "title": "Building and Other Construction Workers (Regulation of Employment and Conditions of Service) Act 1996", "anchor": "bocw-1996/sec-12"},
    ]

    lines = _grounded_template_lines(q, route_matter(q), passages)

    assert any("5th-floor construction-site fall with a leg injury" in line and "[1]" in line for line in lines)
    assert any("no BOCW card" in line and "[8]" in line for line in lines)
    assert any("Commissioner" in line and "[2]" in line for line in lines)


def test_grounded_template_for_non_hindu_relative_adoption_uses_jj_and_guardians():
    from apps.api.main import _grounded_template_lines
    from apps.api.matter_router import route_matter

    q = "we are not a hindu family adopted child from sister no papers now real parents want him back"
    passages = [
        {"index": 1, "title": "Guardians and Wards Act 1890", "anchor": "guardians-wards-1890/sec-17"},
        {"index": 6, "title": "Juvenile Justice (Care and Protection of Children) Act 2015", "anchor": "jj-2015/sec-56"},
        {"index": 7, "title": "Juvenile Justice (Care and Protection of Children) Act 2015", "anchor": "jj-2015/sec-58"},
    ]

    lines = _grounded_template_lines(q, route_matter(q), passages)

    assert any("non-Hindu family relative adoption from a sister" in line and "[6]" in line for line in lines)
    assert any("real parents now want the child back" in line and "[1]" in line for line in lines)
    assert any("Specialised Adoption Agency" in line and "[7]" in line for line in lines)


def test_stage24_templates_do_not_inject_smoke_specific_facts_for_near_misses():
    from apps.api.main import _grounded_template_lines
    from apps.api.matter_router import route_matter

    rti_passages = [{"index": 3, "title": "Right to Information Act 2005", "anchor": "rti-2005/sec-6"}]
    birth = _grounded_template_lines("need duplicate birth certificate from municipal office", route_matter("need duplicate birth certificate from municipal office"), rti_passages)
    assert birth
    assert not any("born at home" in line or "panchayat secretary" in line for line in birth)

    bonded_passages = [{"index": 2, "title": "Bonded Labour System (Abolition) Act 1976", "anchor": "bonded-labour-1976/sec-12"}]
    bonded = _grounded_template_lines("contractor took advance and not letting leave surat site", route_matter("contractor took advance and not letting leave surat site"), bonded_passages)
    assert bonded
    assert not any("Darbhanga-to-Bangalore" in line for line in bonded)

    bail_passages = [{"index": 1, "title": "Bharatiya Nagarik Suraksha Sanhita 2023", "anchor": "bnss-2023/sec-483"}]
    witch = _grounded_template_lines("they call me daayan false case filed assam", route_matter("they call me daayan false case filed assam"), bail_passages)
    assert witch
    assert not any("Chhattisgarh" in line or "child death" in line for line in witch)

    injury_passages = [
        {"index": 1, "title": "Employees' Compensation Act 1923", "anchor": "employees-compensation-1923/sec-3"},
        {"index": 8, "title": "Building and Other Construction Workers (Regulation of Employment and Conditions of Service) Act 1996", "anchor": "bocw-1996/sec-12"},
    ]
    injury = _grounded_template_lines("construction site machine injured my hand no bocw card", route_matter("construction site machine injured my hand no bocw card"), injury_passages)
    assert injury
    assert not any("fall from" in line for line in injury)
    machine_leg = _grounded_template_lines("5th floor construction site machine crushed leg broken no bocw card", route_matter("5th floor construction site machine crushed leg broken no bocw card"), injury_passages)
    assert machine_leg
    assert not any("fall" in line for line in machine_leg)
    has_card = _grounded_template_lines("construction site machine injured my hand bocw card active", route_matter("construction site machine injured my hand bocw card active"), injury_passages)
    assert has_card
    assert not any("no BOCW card" in line for line in has_card)

    adoption_passages = [
        {"index": 1, "title": "Guardians and Wards Act 1890", "anchor": "guardians-wards-1890/sec-17"},
        {"index": 6, "title": "Juvenile Justice (Care and Protection of Children) Act 2015", "anchor": "jj-2015/sec-56"},
        {"index": 7, "title": "Juvenile Justice (Care and Protection of Children) Act 2015", "anchor": "jj-2015/sec-58"},
    ]
    adoption = _grounded_template_lines("hindu family adopted child from cousin no papers", route_matter("hindu family adopted child from cousin no papers"), adoption_passages)
    assert adoption
    assert not any("non-Hindu" in line or "from a sister" in line for line in adoption)
    assert not any("real parents now want the child back" in line for line in adoption)
    signed_papers = _grounded_template_lines("real parents signed adoption papers now need court order", route_matter("real parents signed adoption papers now need court order"), adoption_passages)
    assert signed_papers
    assert not any("relative adoption" in line for line in signed_papers)
    assert not any("real parents now want the child back" in line for line in signed_papers)
    assert not any("without papers" in line for line in signed_papers)
    sister_actor = _grounded_template_lines("my sister wants to adopt and signed adoption papers", route_matter("my sister wants to adopt and signed adoption papers"), adoption_passages)
    assert sister_actor
    assert not any("from a sister" in line for line in sister_actor)


def test_stage33_hard_failure_templates_use_exact_authorities():
    from apps.api.main import _grounded_template_lines
    from apps.api.matter_router import route_matter

    cases = [
        (
            "iron ore mine displaced our 12 villages no rehabilitation given keonjhar",
            [
                {"index": 1, "title": "Right to Fair Compensation and Transparency in Land Acquisition, Rehabilitation and Resettlement Act 2013", "anchor": "rfctlarr-2013/sec-41-a"},
                {"index": 2, "title": "Mines and Minerals (Development and Regulation) Act 1957", "anchor": "mmdr-1957#header"},
            ],
            ("mine displacement", "[1]", "rehabilitation", "Collector/R&R"),
        ),
        (
            "non tribal sahukar took my land in mortgage 15 years now refusing return jharkhand",
            [
                {"index": 3, "title": "Chota Nagpur Tenancy Act 1908", "anchor": "chota-nagpur-tenancy-1908/sec-45-c@1976-01-01"},
                {"index": 4, "title": "Chota Nagpur Tenancy Act 1908", "anchor": "chota-nagpur-tenancy-1908/sec-71-a@1976-01-01"},
            ],
            ("non-tribal mortgage/sahukar", "[3]", "restoration", "[4]"),
        ),
        (
            "cab driver mumbai uber deactivated rating low because customer racist hindi speaker",
            [
                {"index": 5, "title": "Motor Vehicle Aggregator Guidelines 2020", "anchor": "motor-vehicle-aggregator-guidelines-2020#driver-service-contract"},
                {"index": 6, "title": "Motor Vehicle Aggregator Guidelines 2020", "anchor": "motor-vehicle-aggregator-guidelines-2020#app-transparency-grievance"},
                {"index": 7, "title": "Constitution of India", "anchor": "constitution-india/sec-14"},
                {"index": 15, "title": "Motor Vehicle Aggregator Guidelines 2020", "anchor": "motor-vehicle-aggregator-guidelines-2020#non-discrimination-driver-fare"},
            ],
            ("cab-aggregator", "[5]", "rating", "[6]", "regional bias", "[15]"),
        ),
        (
            "I want to change my gender on aadhar and 10th certificate I have not had surgery is it possible",
            [
                {"index": 8, "title": "Transgender Persons (Protection of Rights) Act 2019", "anchor": "transgender-2019/sec-6@2013-01-01"},
                {"index": 9, "title": "Transgender Persons (Protection of Rights) Act 2019", "anchor": "transgender-2019/sec-7@2013-01-01"},
            ],
            ("Surgery should not be treated", "[8]", "revised-certificate", "[9]"),
        ),
        (
            "construction company retrenched 40 of us bengali workers kept the gujaratis next day same site",
            [
                {"index": 12, "title": "Industrial Disputes Act 1947", "anchor": "industrial-disputes-1947/sec-25G"},
                {"index": 13, "title": "Industrial Disputes Act 1947", "anchor": "industrial-disputes-1947/sec-25F-a"},
                {"index": 14, "title": "Constitution of India", "anchor": "constitution-india/sec-14"},
            ],
            ("retrenched while others", "[12]", "notice/compensation", "[13]", "equality fact", "[14]"),
        ),
        (
            "court ordered supervised visitation for my daughter but my ex's lawyer is asking unsupervised now I am scared",
            [
                {"index": 10, "title": "Guardians and Wards Act 1890", "anchor": "guardians-wards-1890/sec-17@1938-01-01"},
                {"index": 11, "title": "Guardians and Wards Act 1890", "anchor": "guardians-wards-1890/sec-25@1938-01-01"},
            ],
            ("unsupervised visitation", "[10]", "return-of-ward", "[11]"),
        ),
        (
            "my neighbor is parking his car blocking my dedicated parking slot in apartment, security guard says he cant do anything",
            [
                {"index": 13, "title": "VELAGACHARLA JAYARAM REDDY & ORS. versus M.VENKATA RAMANA & ORS. ETC", "anchor": "2022-insc-31#para-11"},
                {"index": 14, "title": "Consumer Protection Act 2019", "anchor": "consumer-protection-2019/sec-35-a"},
            ],
            ("parking-enforcement", "[13]", "not frame it only as a consumer case against the neighbour", "[14]"),
        ),
    ]

    for query, passages, expected_parts in cases:
        joined = " ".join(_grounded_template_lines(query, route_matter(query), passages))
        assert joined, query
        for part in expected_parts:
            assert part in joined, (query, part, joined)


def test_tribal_mutation_template_uses_scheduled_area_route_not_generic_scst():
    from apps.api.main import _grounded_template_lines
    from apps.api.matter_router import route_matter

    query = "can u tell patwari changed mutation record giving my dadaji land to non tribal buyer nuapada odisha what can i do"
    lines = _grounded_template_lines(
        query,
        route_matter(query),
        [
            {"index": 4, "title": "Constitution of India", "anchor": "constitution-india/sec-244"},
        ],
    )
    text = " ".join(lines)
    assert "mutation/patwari" in text
    assert "state Scheduled Area" in text
    assert "Collector" in text
    assert "[4]" in text
    assert "SC/ST offence" not in text


def test_fra_claim_template_uses_fra_procedure_route():
    from apps.api.main import _grounded_template_lines
    from apps.api.matter_router import route_matter

    query = "gram sabha passed my IFR claim but SDLC rejected without reason what to do gadchiroli"
    lines = _grounded_template_lines(
        query,
        route_matter(query),
        [
            {"index": 1, "title": "Scheduled Tribes and Other Traditional Forest Dwellers (Recognition of Forest Rights) Act 2006", "anchor": "fra-2006/sec-6"},
            {"index": 2, "title": "Scheduled Tribes and Other Traditional Forest Dwellers (Recognition of Forest Rights) Act 2006", "anchor": "fra-2006/sec-4"},
            {"index": 3, "title": "Panchayats (Extension to the Scheduled Areas) Act 1996", "anchor": "pesa-1996/sec-4"},
        ],
    )
    text = " ".join(lines)
    assert "FRA claim route" in text
    assert "SDLC/DLC" in text
    assert "Gram Sabha/FRC" in text
    assert "[1]" in text
    assert "general caste complaint" in text


def test_fra_template_does_not_emit_none_citations_when_only_section_5_retrieved():
    from apps.api.main import _grounded_template_lines
    from apps.api.matter_router import route_matter

    query = "i am adivasi woman my IFR claim form rejected because no signature of husband bastar what can i do"
    lines = _grounded_template_lines(
        query,
        route_matter(query),
        [
            {"index": 4, "title": "Scheduled Tribes and Other Traditional Forest Dwellers (Recognition of Forest Rights) Act 2006", "anchor": "fra-2006/sec-5-a"},
        ],
    )
    text = " ".join(lines)
    assert "[4]" in text
    assert "[None]" not in text
    assert "Forest Rights Act route" in text


def test_fra_claim_template_uses_arrangement_when_exact_sections_missing():
    from apps.api.main import _grounded_template_lines
    from apps.api.matter_router import route_matter

    query = "i am adivasi woman my IFR claim form rejected because no signature of husband bastar what can i do"
    lines = _grounded_template_lines(
        query,
        route_matter(query),
        [
            {"index": 6, "title": "Scheduled Tribes and Other Traditional Forest Dwellers (Recognition of Forest Rights) Act 2006", "anchor": "fra-2006#header@2007-01-01"},
        ],
    )
    text = " ".join(lines)
    assert "arrangement identifies recognition/vesting" in text
    assert "authorities/procedure" in text
    assert "[6]" in text


def test_fra_template_does_not_call_produce_or_cfr_interference_claim_refusal():
    from apps.api.main import _grounded_template_lines
    from apps.api.matter_router import route_matter

    cases = [
        "patta given under FRA but forest guards still cutting our bamboo saying it is reserved bastar what can i do",
        "company doing illegal mining on community forest land we got CFR title hazaribagh what can i do",
    ]
    passages = [
        {"index": 1, "title": "Scheduled Tribes and Other Traditional Forest Dwellers (Recognition of Forest Rights) Act 2006", "anchor": "fra-2006/sec-3-c"},
        {"index": 2, "title": "Scheduled Tribes and Other Traditional Forest Dwellers (Recognition of Forest Rights) Act 2006", "anchor": "fra-2006/sec-5-a"},
    ]
    for query in cases:
        text = " ".join(_grounded_template_lines(query, route_matter(query), passages))
        assert "claim refusal" not in text
        assert "IFR/FRA claim refusal" not in text
        assert "Forest Rights Act route" in text or "community forest-rights route" in text or "minor forest produce" in text


def test_common_user_smoke_templates_answer_screenshot_failures():
    from apps.api.main import _grounded_template_lines
    from apps.api.matter_router import route_matter

    cases = [
        (
            "brother and i bought a plot together 10 years back, now he has sold it, what can i do",
            [
                {"index": 1, "title": "Transfer of Property Act 1882", "anchor": "transfer-of-property-1882/sec-45"},
                {"index": 2, "title": "Transfer of Property Act 1882", "anchor": "transfer-of-property-1882/sec-44"},
                {"index": 3, "title": "Specific Relief Act 1963", "anchor": "specific-relief-1963/sec-31"},
            ],
            ("joint-purchase", "[1]", "co-owner", "[2]", "sale deed", "[3]"),
        ),
        (
            "my daughter school admission is denied, despite her clearing admission exam",
            [
                {"index": 4, "title": "Right of Children to Free and Compulsory Education Act 2009", "anchor": "rte-2009/sec-13"},
                {"index": 5, "title": "Right of Children to Free and Compulsory Education Act 2009", "anchor": "rte-2009/sec-12"},
                {"index": 6, "title": "Right of Children to Free and Compulsory Education Act 2009", "anchor": "rte-2009/sec-14"},
            ],
            ("school-admission denial", "[4]", "written refusal", "[4]"),
        ),
        (
            "police has picked my son from my home in the night, i have not got FIR copy",
            [
                {"index": 7, "title": "Constitution of India", "anchor": "constitution-india/sec-22"},
                {"index": 8, "title": "Bharatiya Nagarik Suraksha Sanhita 2023", "anchor": "bnss-2023/sec-173"},
            ],
            ("arrest-information", "[7]", "FIR-copy", "[8]"),
        ),
        (
            "My bike is stolen, police is not filing FIR",
            [
                {"index": 9, "title": "Bharatiya Nyaya Sanhita 2023", "anchor": "bns-2023/sec-303"},
                {"index": 10, "title": "Bharatiya Nagarik Suraksha Sanhita 2023", "anchor": "bnss-2023/sec-173"},
                {"index": 11, "title": "Bharatiya Nagarik Suraksha Sanhita 2023", "anchor": "bnss-2023/sec-175"},
            ],
            ("stolen bike", "[9]", "police refusal", "[10]", "written theft complaint", "[11]"),
        ),
        (
            "My husband told lies before marriage about his job and his salary, what to do",
            [
                {"index": 12, "title": "Hindu Marriage Act 1955", "anchor": "hindu-marriage-1955/sec-12"},
                {"index": 13, "title": "Family Courts Act 1984", "anchor": "family-courts-1984/sec-7"},
            ],
            ("Section 12", "[12]", "Family Court", "[13]", "biodata/messages"),
        ),
        (
            "My tenant is not vacating house and not paying rent",
            [
                {"index": 14, "title": "Transfer of Property Act 1882", "anchor": "transfer-of-property-1882/sec-105"},
                {"index": 15, "title": "Transfer of Property Act 1882", "anchor": "transfer-of-property-1882/sec-106"},
                {"index": 16, "title": "Transfer of Property Act 1882", "anchor": "transfer-of-property-1882/sec-111"},
            ],
            ("tenancy/lease dispute", "[14]", "notice source", "[15]", "rent ledger", "[15]"),
        ),
        (
            "My wife is denying sex since many years, what to do",
            [
                {"index": 17, "title": "Family Courts Act 1984", "anchor": "family-courts-1984/sec-7"},
                {"index": 18, "title": "Hindu Marriage Act 1955", "anchor": "hindu-marriage-1955/sec-13"},
            ],
            ("marriage-breakdown", "[17]", "Section 13", "[18]", "Do not use pressure or force", "DLSA"),
        ),
    ]

    for query, passages, expected_parts in cases:
        joined = " ".join(_grounded_template_lines(query, route_matter(query), passages))
        assert joined, query
        assert "Employment / wages" not in joined
        for part in expected_parts:
            assert part in joined, (query, part, joined)


def test_grounded_template_for_custodial_death_uses_section_196():
    from apps.api.main import _grounded_template_lines
    from apps.api.matter_router import route_matter

    q = "father custodial death lockup byculla police saying suicide what is 196 procedure"
    passages = [
        {"index": 4, "title": "Bharatiya Nagarik Suraksha Sanhita 2023", "anchor": "bnss-2023/sec-196"},
    ]

    lines = _grounded_template_lines(q, route_matter(q), passages)

    assert any("father's police lockup death" in line and "[4]" in line for line in lines)
    assert any("nearest Magistrate" in line and "[4]" in line for line in lines)


def test_grounded_template_for_traffic_bribe_covers_licence_and_corruption():
    from apps.api.main import _grounded_template_lines
    from apps.api.matter_router import route_matter

    q = "auto driver bangalore traffic police taking 500 every week no challan saying tamil license invalid"
    passages = [
        {"index": 3, "title": "TheMotorVehiclesAct,1988", "anchor": "motor-vehicles-1988/sec-3"},
        {"index": 7, "title": "Prevention of Corruption Act 1988", "anchor": "prevention-of-corruption-1988/sec-7"},
        {"index": 8, "title": "Prevention of Corruption Act 1988", "anchor": "prevention-of-corruption-1988/sec-8"},
    ]

    lines = _grounded_template_lines(q, route_matter(q), passages)

    assert any("driving licence issue" in line and "[3]" in line for line in lines)
    assert any("traffic police taking money without a challan" in line and "[7]" in line for line in lines)
    assert any("seven days" in line and "[8]" in line for line in lines)


def test_grounded_template_for_generic_prohibition_avoids_state_punishment():
    from apps.api.main import _grounded_template_lines
    from apps.api.matter_router import route_matter

    q = "police caught me drinking village they saying case under prohibition law what punishment"
    passages = [
        {"index": 1, "title": "Code of Criminal Procedure 1973", "anchor": "crpc-1973/sec-50"},
        {"index": 8, "title": "Constitution of India", "anchor": "constitution-india/sec-44"},
    ]

    lines = _grounded_template_lines(q, route_matter(q), passages)

    assert any("prohibition-law case" in line and "[1]" in line for line in lines)
    assert any("right to be released on bail" in line and "[1]" in line for line in lines)
    assert any("do not state a concrete punishment" in line for line in lines)


def test_template_anchor_matching_respects_section_boundaries():
    from apps.api.main import _find_passage_index

    adjacent_section = [
        {"index": 9, "title": "Bharatiya Nagarik Suraksha Sanhita 2023", "anchor": "bnss-2023/sec-478"},
    ]
    suffixed_section = [
        {"index": 6, "title": "Right to Information Act 2005", "anchor": "rti-2005/sec-7-a"},
    ]

    assert _find_passage_index(
        adjacent_section,
        title_terms=("bharatiya nagarik suraksha sanhita",),
        anchor_terms=("/sec-47",),
    ) is None
    assert _find_passage_index(
        suffixed_section,
        title_terms=("right to information act",),
        anchor_terms=("/sec-7",),
    ) == 6


def test_grounded_generic_prohibition_template_does_not_match_adjacent_bnss_section():
    from apps.api.main import _grounded_template_lines
    from apps.api.matter_router import route_matter

    q = "police caught me drinking village they saying case under prohibition law what punishment"
    passages = [
        {"index": 9, "title": "Bharatiya Nagarik Suraksha Sanhita 2023", "anchor": "bnss-2023/sec-478"},
        {"index": 8, "title": "Constitution of India", "anchor": "constitution-india/sec-47"},
    ]

    assert _grounded_template_lines(q, route_matter(q), passages) == []


def test_grounded_rti_template_does_not_use_adjacent_section_70_as_section_7():
    from apps.api.main import _grounded_template_lines
    from apps.api.matter_router import route_matter

    q = "papa ki pension 6 month se nahi aayi rti kaise file karein"
    passages = [
        {"index": 3, "title": "Right to Information Act 2005", "anchor": "rti-2005/sec-6"},
        {"index": 4, "title": "Right to Information Act 2005", "anchor": "rti-2005/sec-70"},
        {"index": 5, "title": "Right to Information Act 2005", "anchor": "rti-2005/sec-19"},
    ]

    lines = _grounded_template_lines(q, route_matter(q), passages)

    assert lines
    assert not any("thirty days" in line for line in lines)
    assert any("appeal" in line and "[5]" in line for line in lines)


def test_grounded_templates_do_not_false_activate_on_adjacent_queries():
    from apps.api.main import _grounded_template_lines
    from apps.api.matter_router import route_matter

    kanya = "bihar kanya vivah scheme kaise file karein daughter wedding money"
    rti_passages = [
        {"index": 1, "title": "Right to Information Act 2005", "anchor": "rti-2005/sec-6"},
    ]
    assert _grounded_template_lines(kanya, route_matter(kanya), rti_passages) == []

    no_licence = "auto driver bangalore traffic police taking 500 every week no challan"
    traffic_passages = [
        {"index": 3, "title": "TheMotorVehiclesAct,1988", "anchor": "motor-vehicles-1988/sec-3"},
        {"index": 7, "title": "Prevention of Corruption Act 1988", "anchor": "prevention-of-corruption-1988/sec-7"},
    ]
    assert _grounded_template_lines(no_licence, route_matter(no_licence), traffic_passages) == []


def test_grounded_stage38_review_blocker_templates_use_required_acts():
    from apps.api.main import _grounded_template_lines
    from apps.api.matter_router import route_matter

    kanya_q = "kanya vivah scheme money not given after my daughter wedding where to complain"
    kanya_lines = _grounded_template_lines(kanya_q, route_matter(kanya_q), [
        {"index": 1, "title": "Right to Information Act 2005", "anchor": "rti-2005/sec-6"},
        {"index": 2, "title": "Right to Information Act 2005", "anchor": "rti-2005/sec-19"},
    ])
    kanya_joined = " ".join(kanya_lines)
    assert "RTI source" in kanya_joined
    assert "request in writing" in kanya_joined
    assert "prescribed fee" in kanya_joined

    wage_q = "boss saying i signed paper give up wages but i dont read english kannada bangalore"
    wage_lines = _grounded_template_lines(wage_q, route_matter(wage_q), [
        {"index": 3, "title": "Code on Wages 2019", "anchor": "code-on-wages-2019/sec-60@2019-08-08"},
        {"index": 4, "title": "Indian Contract Act 1872", "anchor": "indian-contract-1872/sec-19-a"},
        {"index": 5, "title": "Code on Wages 2019", "anchor": "code-on-wages-2019/sec-45@2019-08-08"},
    ])
    wage_joined = " ".join(wage_lines)
    assert "Code on Wages" in wage_joined
    assert "Contract Act" in wage_joined
    assert "hear and determine claims" in wage_joined
    assert "[3]" in wage_joined
    assert "[4]" in wage_joined

    otp_q = "otp fraud 2 lakh lost bank says my fault no refund what can i do"
    otp_lines = _grounded_template_lines(otp_q, route_matter(otp_q), [
        {"index": 6, "title": "Information Technology Act 2000", "anchor": "it-2000/sec-66D"},
        {"index": 7, "title": "Reserve Bank Integrated Ombudsman Scheme 2021", "anchor": "rbi-integrated-ombudsman-2021/sec-2"},
    ])
    otp_joined = " ".join(otp_lines)
    assert "cyber-fraud" in otp_joined
    assert "RBI Ombudsman" in otp_joined
    assert "regulated-entity complaint route" in otp_joined
    non_bank_cyber = _grounded_template_lines(
        "tinder girl threatening to leak chat screenshots unless i pay money",
        route_matter("tinder girl threatening to leak chat screenshots unless i pay money"),
        [
            {"index": 18, "title": "Information Technology Act 2000", "anchor": "it-2000/sec-66D"},
            {"index": 19, "title": "Reserve Bank Integrated Ombudsman Scheme 2021", "anchor": "rbi-integrated-ombudsman-2021/sec-2"},
        ],
    )
    assert "bank account" not in " ".join(non_bank_cyber)
    assert "Ombudsman" not in " ".join(non_bank_cyber)

    private_nudes_q = "ex boyfriend leaked my private nudes on telegram and whatsapp, police saying delete links only, what sections apply"
    private_nudes_lines = _grounded_template_lines(private_nudes_q, route_matter(private_nudes_q), [
        {"index": 20, "title": "Information Technology Act 2000", "anchor": "it-2000/sec-66E"},
        {"index": 21, "title": "Bharatiya Nyaya Sanhita 2023", "anchor": "bns-2023/sec-77@2024-07-01"},
    ])
    private_nudes_joined = " ".join(private_nudes_lines)
    assert "leaked private nudes on Telegram or WhatsApp" in private_nudes_joined
    assert "[20]" in private_nudes_joined
    assert "[21]" in private_nudes_joined

    marital_q = "husband forces me at night even when i say no what law"
    marital_lines = _grounded_template_lines(marital_q, route_matter(marital_q), [
        {"index": 22, "title": "Protection of Women from Domestic Violence Act 2005", "anchor": "domestic-violence-2005/sec-3"},
        {"index": 23, "title": "Bharatiya Nyaya Sanhita 2023", "anchor": "bns-2023/sec-63@2024-07-01"},
        {"index": 24, "title": "Protection of Women from Domestic Violence Act 2005", "anchor": "domestic-violence-2005/sec-18"},
    ])
    marital_joined = " ".join(marital_lines)
    assert "domestic violence and safety" in marital_joined
    assert "marital-exception" in marital_joined
    assert "[22]" in marital_joined
    assert "[23]" in marital_joined

    decree_q = "judgment debtor not paying money decree can court attach property"
    decree_lines = _grounded_template_lines(decree_q, route_matter(decree_q), [
        {"index": 8, "title": "Code of Civil Procedure 1908", "anchor": "cpc-1908/sec-51@2026-01-10"},
        {"index": 9, "title": "Code of Civil Procedure 1908", "anchor": "cpc-1908/sec-47-a@2026-01-10"},
    ])
    decree_joined = " ".join(decree_lines)
    assert "CPC execution" in decree_joined
    assert "attachment and sale" in decree_joined
    assert "court executing the decree" in decree_joined

    quashing_q = "482 CrPC quashing FIR in high court what documents needed"
    quashing_lines = _grounded_template_lines(quashing_q, route_matter(quashing_q), [
        {"index": 10, "title": "Bharatiya Nagarik Suraksha Sanhita 2023", "anchor": "bnss-2023/sec-528@2024-07-01"},
        {"index": 11, "title": "Code of Criminal Procedure 1973", "anchor": "crpc-1973/sec-482"},
    ])
    quashing_joined = " ".join(quashing_lines)
    assert "CrPC section 482" in quashing_joined
    assert "pre-1 July 2024" in quashing_joined

    senior_q = "maintenance tribunal ordered son to pay but he stopped paying how to enforce"
    senior_lines = _grounded_template_lines(senior_q, route_matter(senior_q), [
        {"index": 12, "title": "Maintenance and Welfare of Parents and Senior Citizens Act 2007", "anchor": "mwp-2007/sec-11"},
        {"index": 13, "title": "Maintenance and Welfare of Parents and Senior Citizens Act 2007", "anchor": "mwp-2007/sec-13"},
    ])
    senior_joined = " ".join(senior_lines)
    assert "enforcement" in senior_joined
    assert "Senior Citizens Act" in senior_joined
    assert "deposit" in senior_joined

    ndps_q = "NDPS case 50 gram ganja, first time accused, can I get bail and which court should I approach"
    ndps_lines = _grounded_template_lines(ndps_q, route_matter(ndps_q), [
        {"index": 14, "title": "Narcotic Drugs and Psychotropic Substances Act 1985", "anchor": "ndps-1985/sec-20"},
        {"index": 15, "title": "Bharatiya Nagarik Suraksha Sanhita 2023", "anchor": "bnss-2023/sec-480@2024-07-01"},
    ])
    ndps_joined = " ".join(ndps_lines)
    assert "NDPS cannabis possession source" in ndps_joined
    assert "BNSS bail source says" in ndps_joined
    assert "[14]" in ndps_joined
    assert "[15]" in ndps_joined

    ndps_fallback_lines = _grounded_template_lines(ndps_q, route_matter(ndps_q), [
        {"index": 16, "title": "Narcotic Drugs and Psychotropic Substances Act 1985", "anchor": "ndps-1985/sec-2-a"},
        {"index": 17, "title": "Bharatiya Nagarik Suraksha Sanhita 2023", "anchor": "bnss-2023/sec-483@2024-07-01"},
    ])
    ndps_fallback_joined = " ".join(ndps_fallback_lines)
    assert "NDPS definition source" in ndps_fallback_joined
    assert "BNSS bail source says" in ndps_fallback_joined
    assert "[16]" in ndps_fallback_joined
    assert "[17]" in ndps_fallback_joined


def test_grounded_rti_appeal_template_requires_appeal_source():
    from apps.api.main import _grounded_template_lines
    from apps.api.matter_router import route_matter

    q = "I filed an RTI and it was rejected what is first appeal time limit"
    passages = [
        {"index": 7, "title": "Right to Information Act 2005", "anchor": "rti-2005/sec-6"},
    ]

    assert _grounded_template_lines(q, route_matter(q), passages) == []


def test_grounded_stage_d12_common_prompt_templates_use_user_shape():
    from apps.api.main import _grounded_template_lines
    from apps.api.matter_router import route_matter

    prison_q = "tihar jail mulaqat only 30 min once a week is this legal can we ask more"
    prison_joined = " ".join(_grounded_template_lines(prison_q, route_matter(prison_q), [
        {"index": 1, "title": "Prisons Act 1894", "anchor": "prisons-1894/sec-59"},
        {"index": 2, "title": "Constitution of India", "anchor": "constitution-india/sec-21"},
    ]))
    assert "mulaqat" in prison_joined
    assert "Jail Superintendent" in prison_joined
    assert "[1]" in prison_joined and "[2]" in prison_joined

    vakalat_q = "how to file vakalatnama change of advocate during pending suit"
    vakalat_joined = " ".join(_grounded_template_lines(vakalat_q, route_matter(vakalat_q), [
        {"index": 3, "title": "Code of Civil Procedure 1908", "anchor": "cpc-1908/sec-151"},
        {"index": 4, "title": "Legal Services Authorities Act 1987", "anchor": "legal-services-authorities-1987/sec-12"},
    ]))
    assert "vakalatnama" in vakalat_joined
    assert "same court registry" in vakalat_joined
    assert "[3]" in vakalat_joined and "[4]" in vakalat_joined

    crypto_q = "guy from telegram crypto group rugpulled me 3 lakh whom to complain"
    crypto_joined = " ".join(_grounded_template_lines(crypto_q, route_matter(crypto_q), [
        {"index": 5, "title": "Bharatiya Nyaya Sanhita 2023", "anchor": "bns-2023/sec-318@2024-07-01"},
        {"index": 6, "title": "Information Technology Act 2000", "anchor": "it-2000/sec-66D"},
        {"index": 7, "title": "Bharatiya Nagarik Suraksha Sanhita 2023", "anchor": "bnss-2023/sec-173@2024-07-01"},
        {"index": 8, "title": "Prevention of Money Laundering Act 2002", "anchor": "pmla-2002/sec-2"},
    ]))
    assert "Telegram crypto rug-pull" in crypto_joined
    assert "wallet addresses" in crypto_joined
    assert "[5]" in crypto_joined and "[8]" in crypto_joined

    kyc_q = "blue trunks app froze my account showing kyc pending pe stuck 80k"
    kyc_joined = " ".join(_grounded_template_lines(kyc_q, route_matter(kyc_q), [
        {"index": 14, "title": "Consumer Protection Act 2019", "anchor": "consumer-protection-2019/sec-35"},
        {"index": 15, "title": "Prevention of Money Laundering Act 2002", "anchor": "pmla-2002/sec-5"},
    ]))
    assert "AML/freeze source to check" in kyc_joined
    assert "service-deficiency complaint" in kyc_joined
    assert "[14]" in kyc_joined and "[15]" in kyc_joined

    mining_q = "DM gave NOC to bauxite project bastar without gram sabha resolution how to challenge"
    mining_joined = " ".join(_grounded_template_lines(mining_q, route_matter(mining_q), [
        {"index": 9, "title": "Panchayats (Extension to the Scheduled Areas) Act 1996", "anchor": "pesa-1996/sec-4"},
        {"index": 10, "title": "Forest (Conservation) Act 1980", "anchor": "forest-conservation-1980/sec-2"},
        {"index": 11, "title": "Mines and Minerals (Development and Regulation) Act 1957", "anchor": "mmdr-1957/sec-4"},
    ]))
    assert "Gram Sabha" in mining_joined
    assert "NOC" in mining_joined
    assert "[9]" in mining_joined and "[10]" in mining_joined

    coal_q = "land acquired for coal block without consulting palli sabha angul odisha what can i do"
    coal_joined = " ".join(_grounded_template_lines(coal_q, route_matter(coal_q), [
        {"index": 16, "title": "Panchayats (Extension to the Scheduled Areas) Act 1996", "anchor": "pesa-1996/sec-4-b"},
        {"index": 17, "title": "Right to Fair Compensation and Transparency in Land Acquisition, Rehabilitation and Resettlement Act 2013", "anchor": "rfctlarr-2013/sec-41"},
        {"index": 18, "title": "Mines and Minerals (Development and Regulation) Act 1957", "anchor": "mmdr-1957/sec-4"},
    ]))
    assert "Palli Sabha" in coal_joined
    assert "RFCTLARR section 41" in coal_joined
    assert "verify whether" in coal_joined
    assert "violat" not in coal_joined.lower()
    assert "[16]" in coal_joined and "[17]" in coal_joined

    minor_mineral_q = "sand mining lease given without gram sabha consent in scheduled area"
    minor_mineral_joined = " ".join(_grounded_template_lines(minor_mineral_q, route_matter(minor_mineral_q), [
        {"index": 20, "title": "Panchayats (Extension to the Scheduled Areas) Act 1996", "anchor": "pesa-1996/sec-4-c"},
        {"index": 21, "title": "Mines and Minerals (Development and Regulation) Act 1957", "anchor": "mmdr-1957/sec-4"},
        {"index": 22, "title": "Right to Fair Compensation and Transparency in Land Acquisition, Rehabilitation and Resettlement Act 2013", "anchor": "rfctlarr-2013/sec-41"},
    ]))
    assert "minor-mineral lease" in minor_mineral_joined
    assert "Gram Sabha recommendation" in minor_mineral_joined
    assert "mineral-department approval" in minor_mineral_joined
    assert "[20]" in minor_mineral_joined and "[21]" in minor_mineral_joined
    assert "[22]" not in minor_mineral_joined
    assert "acquisition notices" not in minor_mineral_joined
    assert "affected-family" not in minor_mineral_joined
    assert "R&R" not in minor_mineral_joined
    assert "RFCTLARR" not in minor_mineral_joined

    elder_498a_q = "my mother got named in false 498a fir by son wife she is 71 what to do"
    elder_498a_joined = " ".join(_grounded_template_lines(elder_498a_q, route_matter(elder_498a_q), [
        {"index": 12, "title": "Bharatiya Nyaya Sanhita 2023", "anchor": "bns-2023/sec-85@2024-07-01"},
        {"index": 13, "title": "Bharatiya Nagarik Suraksha Sanhita 2023", "anchor": "bnss-2023/sec-480@2024-07-01"},
    ]))
    assert "71-year-old mother" in elder_498a_joined
    assert "FIR sections" in elder_498a_joined
    assert "[12]" in elder_498a_joined and "[13]" in elder_498a_joined

    unknown_ndps_q = "brother arrested ndps 5 gram personal use how is small quantity proven"
    unknown_ndps_joined = " ".join(_grounded_template_lines(unknown_ndps_q, route_matter(unknown_ndps_q), [
        {"index": 19, "title": "Narcotic Drugs and Psychotropic Substances Act 1985", "anchor": "ndps-1985/sec-14"},
    ]))
    assert "personal use" in unknown_ndps_joined
    assert "seizure memo" in unknown_ndps_joined
    assert "[19]" in unknown_ndps_joined

    ancestral_q = "ancestral land in my dada name now uncle selling without telling us what to do"
    ancestral_joined = " ".join(_grounded_template_lines(ancestral_q, route_matter(ancestral_q), [
        {"index": 16, "title": "Hindu Succession Act 1956", "anchor": "hindu-succession-1956/sec-8"},
        {"index": 17, "title": "Transfer of Property Act 1882", "anchor": "transfer-of-property-1882/sec-44"},
        {"index": 18, "title": "Specific Relief Act 1963", "anchor": "specific-relief-1963/sec-31"},
    ]))
    assert "grandfather/dada land" in ancestral_joined
    assert "uncle's proposed sale" in ancestral_joined
    assert "[16]" in ancestral_joined and "[18]" in ancestral_joined


def test_stage_e_hardfail_templates_are_user_shaped():
    from apps.api.main import _grounded_template_lines
    from apps.api.matter_router import route_matter

    writ_q = "urgent difference between Article 32 Supreme Court and Article 226 High Court writ how to complain"
    writ_joined = " ".join(_grounded_template_lines(writ_q, route_matter(writ_q), [
        {"index": 1, "title": "Constitution of India", "anchor": "constitution-india/sec-226"},
        {"index": 2, "title": "Constitution of India", "anchor": "constitution-india/sec-32"},
        {"index": 3, "title": "Legal Services Authorities Act 1987", "anchor": "legal-services-authorities-1987/sec-12"},
    ]))
    assert "Article 226" in writ_joined
    assert "Article 32" in writ_joined
    assert "High Court" in writ_joined
    assert "[1]" in writ_joined and "[2]" in writ_joined

    health_q = (
        "please help the man I am supposed to marry next month I found out hides he is HIV positive "
        "his family also knows can I cancel without dowry return issue any remedy"
    )
    health_joined = " ".join(_grounded_template_lines(health_q, route_matter(health_q), [
        {"index": 4, "title": "Hindu Marriage Act 1955", "anchor": "hindu-marriage-1955/sec-12"},
        {"index": 5, "title": "Dowry Prohibition Act 1961", "anchor": "dowry-prohibition-1961/sec-3"},
    ]))
    assert "marriage has not happened" in health_joined
    assert "do not treat this as divorce or annulment today" in health_joined
    assert "medical status" in health_joined
    assert "[4]" in health_joined and "[5]" in health_joined

    post_marriage_q = "married last month found wife hid HIV positive can I cancel marriage"
    post_marriage_joined = " ".join(_grounded_template_lines(post_marriage_q, route_matter(post_marriage_q), [
        {"index": 9, "title": "Hindu Marriage Act 1955", "anchor": "hindu-marriage-1955/sec-12"},
        {"index": 10, "title": "Family Courts Act 1984", "anchor": "family-courts-1984/sec-7"},
    ]))
    assert "marriage has not happened" not in post_marriage_joined
    assert "Section 12" in post_marriage_joined
    assert "voidable" in post_marriage_joined
    assert "health or medical-status" in post_marriage_joined

    after_wedding_joined = " ".join(_grounded_template_lines(
        "after wedding found groom hid HIV can I cancel marriage",
        route_matter("after wedding found groom hid HIV can I cancel marriage"),
        [
            {"index": 11, "title": "Hindu Marriage Act 1955", "anchor": "hindu-marriage-1955/sec-12"},
            {"index": 12, "title": "Family Courts Act 1984", "anchor": "family-courts-1984/sec-7"},
        ],
    ))
    assert "marriage has not happened" not in after_wedding_joined
    assert "health or medical-status" in after_wedding_joined
    assert "[11]" in after_wedding_joined

    ancestral_q = (
        "pls tell father is hindu 78 yrs ancestral land sold by brother without consent "
        "madhya pradesh need lawyer or police"
    )
    ancestral_joined = " ".join(_grounded_template_lines(ancestral_q, route_matter(ancestral_q), [
        {"index": 6, "title": "Hindu Succession Act 1956", "anchor": "hindu-succession-1956/sec-6"},
        {"index": 7, "title": "Transfer of Property Act 1882", "anchor": "transfer-of-property-1882/sec-44"},
        {"index": 8, "title": "Specific Relief Act 1963", "anchor": "specific-relief-1963/sec-31"},
    ]))
    assert "ancestral" in ancestral_joined
    assert "Hindu Succession" in ancestral_joined
    assert "civil-court remedy" in ancestral_joined
    assert "[6]" in ancestral_joined and "[8]" in ancestral_joined


def test_stage_f_safety_blocker_templates_are_user_shaped():
    from apps.api.main import _grounded_template_lines, _is_safe_template_source_bridge
    from apps.api.matter_router import route_matter

    csam_q = "ai csam of my classmate someone made and shared in college telegram"
    csam_joined = " ".join(_grounded_template_lines(csam_q, route_matter(csam_q), [
        {"index": 1, "title": "Protection of Children from Sexual Offences Act 2012", "anchor": "pocso-2012/sec-13"},
        {"index": 2, "title": "Information Technology Act 2000", "anchor": "it-2000/sec-67B"},
        {"index": 3, "title": "Bharatiya Nyaya Sanhita 2023", "anchor": "bns-2023/sec-356"},
    ]))
    assert "POCSO" in csam_joined
    assert "CSAM" in csam_joined
    assert "IT Act" in csam_joined
    assert "[1]" in csam_joined and "[2]" in csam_joined

    child_q = "child porn deepfake of 15 year old girl shared on telegram"
    child_joined = " ".join(_grounded_template_lines(child_q, route_matter(child_q), [
        {"index": 1, "title": "Protection of Children from Sexual Offences Act 2012", "anchor": "pocso-2012/sec-13", "text": "Use of child in any form of media for pornographic purposes."},
        {"index": 2, "title": "Information Technology Act 2000", "anchor": "it-2000/sec-67B", "text": "Section 67B material depicting children in sexually explicit act."},
        {"index": 3, "title": "Information Technology Act 2000", "anchor": "it-2000/sec-67A"},
    ]))
    assert "POCSO" in child_joined
    assert "CSAM" in child_joined
    assert "child sexual-image" in child_joined

    child_reporting_joined = " ".join(_grounded_template_lines(child_q, route_matter(child_q), [
        {"index": 4, "title": "Protection of Children from Sexual Offences Act 2012", "anchor": "pocso-2012/sec-19"},
        {"index": 7, "title": "Information Technology Act 2000", "anchor": "it-2000/sec-67B", "text": "Section 67B material depicting children in sexually explicit act."},
    ]))
    assert "POCSO reporting source" in child_reporting_joined
    assert "[4]" in child_reporting_joined
    assert "CSAM/minor-image facts" in child_reporting_joined

    adult_q = "ai porn of my adult classmate someone made and shared in college telegram"
    adult_joined = " ".join(_grounded_template_lines(adult_q, route_matter(adult_q), [
        {"index": 1, "title": "Protection of Children from Sexual Offences Act 2012", "anchor": "pocso-2012/sec-13", "text": "Use of child in any form of media for pornographic purposes."},
        {"index": 2, "title": "Information Technology Act 2000", "anchor": "it-2000/sec-67B", "text": "Section 67B material depicting children in sexually explicit act."},
        {"index": 3, "title": "Information Technology Act 2000", "anchor": "it-2000/sec-67A"},
        {"index": 4, "title": "Information Technology Act 2000", "anchor": "it-2000/sec-66E"},
    ]))
    assert "non-consensual deepfake" in adult_joined
    assert "CSAM" not in adult_joined
    assert "child sexual-image" not in adult_joined
    assert "POCSO" not in adult_joined

    for online_warning_q in (
        "engagement broken because he hid HIV can I post warning online",
        "engagement broken because he hid HIV can I warn people on Instagram",
        "engagement broken because he hid HIV can I put his HIV status on WhatsApp group",
    ):
        online_warning_joined = " ".join(_grounded_template_lines(online_warning_q, route_matter(online_warning_q), [
            {"index": 4, "title": "Hindu Marriage Act 1955", "anchor": "hindu-marriage-1955/sec-12"},
            {"index": 5, "title": "Information Technology Act 2000", "anchor": "it-2000/sec-66E"},
            {"index": 6, "title": "Digital Personal Data Protection Act 2023", "anchor": "dpdp-2023/sec-8"},
        ]))
        assert "marriage has not happened" in online_warning_joined
        assert "Do not post" in online_warning_joined
        assert "medical status online" in online_warning_joined
        assert "[5]" in online_warning_joined
        assert _is_safe_template_source_bridge(
            "Do not post the person's identifiable medical status online as a pressure tactic; keep evidence private and verify any disclosure, takedown, or complaint step against the cited privacy/cyber source first [5].",
            route_matter(online_warning_q),
        )


def test_grounded_juvenile_template_does_not_cite_no_jail_for_age_application():
    from apps.api.main import _grounded_template_lines
    from apps.api.matter_router import route_matter

    q = "son 17 yrs in adult jail puzhal pocso case age proof school certificate where to file"
    passages = [
        {
            "index": 3,
            "title": "Juvenile Justice (Care and Protection of Children) Act 2015",
            "anchor": "jj-2015/sec-2-u",
            "text": (
                "Provided that in no case, a child alleged to be in conflict with law "
                "shall be placed in a police lockup or lodged in a jail."
            ),
        },
    ]

    lines = _grounded_template_lines(q, route_matter(q), passages)

    assert any("removal from jail or lockup" in line and "[3]" in line for line in lines)
    assert not any("age-determination application" in line for line in lines)
    assert not any("school certificate" in line for line in lines)


def test_grounded_juvenile_template_uses_age_sources_for_age_application():
    from apps.api.main import _grounded_template_lines
    from apps.api.matter_router import route_matter

    q = "son 17 yrs in adult jail puzhal pocso case age proof school certificate where to file"
    passages = [
        {
            "index": 1,
            "title": "Juvenile Justice (Care and Protection of Children) Act 2015",
            "anchor": "jj-2015/sec-9",
            "text": (
                "In case a person alleged to have committed an offence claims before a court other  "
                "than a Board that the person is a child, the court shall make an inquiry and "
                "determine the age of such person."
            ),
        },
        {
            "index": 2,
            "title": "Juvenile Justice (Care and Protection of Children) Act 2015",
            "anchor": "jj-2015/sec-94",
            "text": (
                "The Committee or Board shall undertake the process of age determination by "
                "obtaining the date of birth certificate from the school, matriculation certificate, "
                "municipal or panchayat birth certificate, or ossification test."
            ),
        },
        {
            "index": 3,
            "title": "Juvenile Justice (Care and Protection of Children) Act 2015",
            "anchor": "jj-2015/sec-2-u",
            "text": (
                "Provided that in no case, a child alleged to be in conflict with law "
                "shall be placed in a police lockup or lodged in a jail."
            ),
        },
    ]

    joined = " ".join(_grounded_template_lines(q, route_matter(q), passages))

    assert "court other than the Juvenile Justice Board" in joined
    assert "school or matriculation certificate" in joined
    assert "municipal or panchayat birth certificate" in joined
    assert "[1]" in joined
    assert "[2]" in joined


def test_stage31_templates_do_not_hardcode_smoke_prompt_facts():
    from apps.api.main import _grounded_template_lines
    from apps.api.matter_router import route_matter

    juvenile = _grounded_template_lines(
        "minor in jail age proof where to file",
        route_matter("minor in jail age proof where to file"),
        [{
            "index": 3,
            "title": "Juvenile Justice (Care and Protection of Children) Act 2015",
            "anchor": "jj-2015/sec-2-u",
            "text": (
                "the child before the Board within twenty-four hours; in no case "
                "shall a child alleged to be in conflict with law be placed in a police lockup or lodged in a jail"
            ),
        }],
    )
    joined_juvenile = " ".join(juvenile)
    assert "17-year-old" not in joined_juvenile
    assert "POCSO" not in joined_juvenile
    assert "Puzhal" not in joined_juvenile

    workplace = _grounded_template_lines(
        "contractor beat me at site when I asked wages",
        route_matter("contractor beat me at site when I asked wages"),
        [
            {"index": 1, "title": "Bharatiya Nyaya Sanhita 2023", "anchor": "bns-2023/sec-117@2024-07-01"},
            {"index": 2, "title": "Employees' Compensation Act 1923", "anchor": "employees-compensation-1923/sec-3-a@1961-01-01"},
            {"index": 3, "title": "Code on Wages 2019", "anchor": "code-on-wages-2019/sec-17@2019-08-08"},
        ],
    )
    joined_workplace = " ".join(workplace)
    assert "Mumbai" not in joined_workplace
    assert "mukadam" not in joined_workplace
    assert "8-stitch" not in joined_workplace

    panchayat = _grounded_template_lines(
        "panchayat transferred common village land without resolution",
        route_matter("panchayat transferred common village land without resolution"),
        [
            {"index": 1, "title": "Constitution of India", "anchor": "constitution-india/sec-243G"},
            {"index": 2, "title": "VILLAGE PANCHAYAT, CALANGUTE versus THE ADDITIONAL DIRECTOR OF PANCHAYAT-II", "anchor": "2012-insc-258#para-11"},
            {"index": 3, "title": "Right to Information Act 2005", "anchor": "rti-2005/sec-6"},
        ],
    )
    joined_panchayat = " ".join(panchayat)
    assert "brother" not in joined_panchayat
    assert "closest indexed authority for common village land" not in joined_panchayat
    assert "[2]" not in joined_panchayat

    property_transfer = _grounded_template_lines(
        "uncle signed property to cousin under pressure in hospital can challenge",
        route_matter("uncle signed property to cousin under pressure in hospital can challenge"),
        [
            {"index": 1, "title": "Indian Contract Act 1872", "anchor": "indian-contract-1872/sec-16"},
            {"index": 2, "title": "Indian Contract Act 1872", "anchor": "indian-contract-1872/sec-19-a"},
            {"index": 3, "title": "Transfer of Property Act 1882", "anchor": "transfer-of-property-1882/sec-126"},
        ],
    )
    joined_property = " ".join(property_transfer)
    assert "dad" not in joined_property.lower()
    assert "son" not in joined_property.lower()
    assert "ICU" not in joined_property
    assert "uncle" in joined_property
    assert "cousin" in joined_property


def test_grounded_pet_template_marks_bmc_guideline_as_local_not_national():
    from apps.api.main import _grounded_template_lines
    from apps.api.matter_router import route_matter

    q = "society management has put a fine of 25000 on me for keeping a pet without prior approval"
    passages = [
        {
            "index": 2,
            "title": "BMC Guidelines with respect to Pet & Street dogs, Community Animal Feeder/Care giver, RWAs and AOAs",
            "anchor": "bmc-pet-dog-guidelines#pet-dog-residents",
        },
        {
            "index": 4,
            "title": "BMC Guidelines with respect to Pet & Street dogs, Community Animal Feeder/Care giver, RWAs and AOAs",
            "anchor": "bmc-pet-dog-guidelines#housing-society-pet-bylaws",
        },
    ]

    lines = _grounded_template_lines(q, route_matter(q), passages)
    joined = " ".join(lines)

    assert "confirm your city" in joined
    assert "For a Mumbai/BMC society" in joined
    assert "For Mumbai/BMC matters" in joined


def test_stage27_hard_failure_templates_cover_required_sources():
    from apps.api.main import _grounded_template_lines
    from apps.api.matter_router import route_matter

    cases = [
        (
            "company hiding behind section 43B disallowance threat to delay my msme payment",
            [
                {"index": 4, "title": "Income Tax Act 2025 transition FAQ", "anchor": "income-tax-2025-transition-faq#repeal-savings"},
                {"index": 1, "title": "Income-tax Act 1961", "anchor": "income-tax-1961/sec-43B-h@2024-04-01"},
                {"index": 2, "title": "Micro, Small and Medium Enterprises Development Act 2006", "anchor": "msmed-2006/sec-15"},
                {"index": 3, "title": "Micro, Small and Medium Enterprises Development Act 2006", "anchor": "msmed-2006/sec-18"},
            ],
            ("tax year", "[4]", "section 43B(h)", "[1]", "Facilitation Council", "[3]"),
        ),
        (
            "daughter in law took my jewellery worth 12 lakh saying for safe keeping not returning agra",
            [
                {"index": 1, "title": "Protection of Women from Domestic Violence Act 2005", "anchor": "domestic-violence-2005/sec-3"},
                {"index": 2, "title": "Bharatiya Nyaya Sanhita 2023", "anchor": "bns-2023/sec-316-a@2024-07-01"},
            ],
            ("criminal-breach-of-trust", "[2]", "economic abuse", "[1]"),
        ),
        (
            "false dacoity case lodged on my brother by forest guard for collecting tendu leaves dindori",
            [
                {"index": 1, "title": "Scheduled Tribes and Other Traditional Forest Dwellers (Recognition of Forest Rights) Act 2006", "anchor": "fra-2006/sec-3-b", "text": "rights over minor forest produce and community forest rights"},
                {"index": 2, "title": "Bharatiya Nyaya Sanhita 2023", "anchor": "bns-2023/sec-310@2024-07-01"},
            ],
            ("minor forest produce", "[1]", "dacoity", "[2]"),
        ),
        (
            "i was undertrial 5 yrs released last week need help to file police torture case",
            [
                {"index": 1, "title": "Protection of Human Rights Act 1993", "anchor": "protection-human-rights-1993/sec-12@1990-01-01"},
                {"index": 2, "title": "Bharatiya Nagarik Suraksha Sanhita 2023", "anchor": "bnss-2023/sec-173-a@2024-07-01"},
                {"index": 3, "title": "Bharatiya Nyaya Sanhita 2023", "anchor": "bns-2023/sec-117@2024-07-01"},
            ],
            ("Human Rights Act", "[1]", "BNS", "[3]"),
        ),
        (
            "cooperative bank seized my buffalo for crop loan default can they take livestock",
            [
                {"index": 1, "title": "THE PUNJAB STATE COOPERATIVE AGRICULTURAL DEVELOPMENT BANK LTD. versus THE REGISTRAR,COOPERATIVE SOCIETIES AND OTHERS", "anchor": "2022-insc-34#para-12"},
                {"index": 2, "title": "Securitisation and Reconstruction of Financial Assets and Enforcement of Security Interest Act 2002", "anchor": "sarfaesi-2002/sec-13-a@1993-01-01"},
                {"index": 3, "title": "Securitisation and Reconstruction of Financial Assets and Enforcement of Security Interest Act 2002", "anchor": "sarfaesi-2002/sec-17@1993-01-01"},
            ],
            ("cooperative-bank", "[1]", "SARFAESI", "[2]", "Debts Recovery Tribunal", "[3]"),
        ),
        (
            "sarpanch giving common village land to his brother no panchayat meeting was held",
            [
                {"index": 1, "title": "Constitution of India", "anchor": "constitution-india/sec-243G"},
                {"index": 2, "title": "VILLAGE PANCHAYAT, CALANGUTE versus THE ADDITIONAL DIRECTOR OF PANCHAYAT-II", "anchor": "2012-insc-258#header"},
                {"index": 3, "title": "Right to Information Act 2005", "anchor": "rti-2005/sec-6"},
            ],
            ("Panchayats", "[1]", "sarpanch / brother / no Panchayat meeting", "RTI", "[3]"),
        ),
        (
            "site mukadam beat me head injury 8 stitches when i asked for old wages mumbai",
            [
                {"index": 1, "title": "Bharatiya Nagarik Suraksha Sanhita 2023", "anchor": "bnss-2023/sec-216@2024-07-01"},
                {"index": 2, "title": "Code on Wages 2019", "anchor": "code-on-wages-2019/sec-17@2019-08-08"},
                {"index": 3, "title": "Employees' Compensation Act 1923", "anchor": "employees-compensation-1923/sec-3-a@1961-01-01"},
                {"index": 4, "title": "Bharatiya Nyaya Sanhita 2023", "anchor": "bns-2023/sec-117@2024-07-01"},
            ],
            ("BNS", "[4]", "Employees' Compensation", "[3]", "Code on Wages", "[2]"),
        ),
        (
            "how to legally change my surname after marriage, do i need to publish in gazette",
            [
                {"index": 1, "title": "Department of Publication Guidelines for Change of Name Adult Major", "anchor": "deptpub-name-change-adult-guidelines#adult-required-documents"},
                {"index": 2, "title": "Department of Publication Guidelines for Change of Name Adult Major", "anchor": "deptpub-name-change-adult-guidelines#adult-formalities"},
                {"index": 3, "title": "Department of Publication Guidelines for Change of Name Adult Major", "anchor": "deptpub-name-change-adult-guidelines#egazette-download-and-submission"},
            ],
            ("Gazette of India Part-IV", "[1]", "daily local leading newspaper", "[2]", "egazette.gov.in", "[3]"),
        ),
        (
            "my dad signed property to son under pressure when he was in icu can challenge",
            [
                {"index": 1, "title": "Indian Contract Act 1872", "anchor": "indian-contract-1872/sec-16"},
                {"index": 2, "title": "Indian Contract Act 1872", "anchor": "indian-contract-1872/sec-19-a"},
                {"index": 3, "title": "Transfer of Property Act 1882", "anchor": "transfer-of-property-1882/sec-126"},
            ],
            ("undue influence", "[1]", "voidable", "[2]", "Transfer of Property Act", "[3]"),
        ),
    ]

    for query, passages, expected_parts in cases:
        joined = " ".join(_grounded_template_lines(query, route_matter(query), passages))
        assert joined
        for part in expected_parts:
            assert part in joined


def test_milestone_b_common_failure_templates_cover_required_sources():
    from apps.api.main import _grounded_template_lines
    from apps.api.matter_router import route_matter

    cases = [
        (
            "hospital operated wrong leg on my 80 yr old father now hospital says consent",
            [
                {"index": 1, "title": "Consumer Protection Act 2019", "anchor": "consumer-protection-2019/sec-2-a"},
                {"index": 2, "title": "Consumer Protection Act 2019", "anchor": "consumer-protection-2019/sec-35"},
                {"index": 3, "title": "Consumer Protection Act 2019", "anchor": "consumer-protection-2019/sec-39"},
            ],
            ("hospital service-deficiency", "[1]", "consumer-forum", "[2]", "operation notes", "[2]"),
        ),
        (
            "complained about sexual harassment by my manager to HR and now he gave PIP bad rating",
            [
                {"index": 4, "title": "Sexual Harassment of Women at Workplace Act 2013", "anchor": "posh-2013/sec-3"},
                {"index": 5, "title": "Sexual Harassment of Women at Workplace Act 2013", "anchor": "posh-2013/sec-9"},
                {"index": 6, "title": "Sexual Harassment of Women at Workplace Act 2013", "anchor": "posh-2013/sec-19"},
            ],
            ("POSH Act", "[4]", "Internal Committee", "[5]", "PIP", "[5]"),
        ),
        (
            "i complained against my manager for harassment to HR and now they are putting me on PIP, is this retaliation",
            [
                {"index": 18, "title": "Industrial Disputes Act 1947", "anchor": "industrial-disputes-1947/sec-2A"},
                {"index": 19, "title": "Industrial Disputes Act 1947", "anchor": "industrial-disputes-1947/sec-25F"},
            ],
            ("not automatically a labour-court claim", "[18]", "Section 25F", "[19]", "HR complaint", "PIP"),
        ),
        (
            "PITA case only talking on phone with paying clients not meeting anyone take bookings",
            [
                {"index": 7, "title": "Immoral Traffic (Prevention) Act 1956", "anchor": "itpa-1956/sec-5"},
                {"index": 8, "title": "Immoral Traffic (Prevention) Act 1956", "anchor": "itpa-1956/sec-8"},
                {"index": 9, "title": "Bharatiya Nagarik Suraksha Sanhita 2023", "anchor": "bnss-2023/sec-173"},
            ],
            ("Section 5", "[7]", "procuring, inducing or taking", "FIR or notice sections"),
        ),
        (
            "HDFC bank wrongly debited forex transaction no response what to do",
            [
                {"index": 10, "title": "Reserve Bank Integrated Ombudsman Scheme 2021", "anchor": "rbi-integrated-ombudsman-2021/sec-2"},
                {"index": 11, "title": "Consumer Protection Act 2019", "anchor": "consumer-protection-2019/sec-35"},
            ],
            ("RBI Ombudsman Scheme", "[10]", "commercial banks", "statement entry", "[10]"),
        ),
        (
            "vit student caught with bhang lassi in mahabaleshwar holi is it ndps",
            [
                {"index": 12, "title": "Narcotic Drugs and Psychotropic Substances Act 1985", "anchor": "ndps-1985/sec-2-a"},
                {"index": 13, "title": "Narcotic Drugs and Psychotropic Substances Act 1985", "anchor": "ndps-1985/sec-37"},
            ],
            ("bhang-lassi", "[12]", "NDPS definition", "seizure memo", "[12]"),
        ),
        (
            "ration card cancelled due aadhaar mismatch BDO says renew what to do",
            [
                {"index": 14, "title": "National Food Security Act 2013", "anchor": "national-food-security-2013/sec-14"},
                {"index": 15, "title": "National Food Security Act 2013", "anchor": "national-food-security-2013/sec-15"},
                {"index": 16, "title": "Aadhaar (Targeted Delivery of Financial and Other Subsidies, Benefits and Services) Act 2016", "anchor": "aadhaar-2016/sec-7"},
            ],
            ("ration-card cancellation or Aadhaar mismatch", "[14]", "Aadhaar Act", "[16]", "BDO/office reply"),
        ),
        (
            "lost 12 lakh on parimatch betting app can i recover money",
            [
                {"index": 17, "title": "Public Gambling Act 1867", "anchor": "public-gambling-1867/sec-13"},
            ],
            ("game of mere skill", "[17]", "recoverable wallet dispute"),
        ),
    ]

    for query, passages, expected_parts in cases:
        joined = " ".join(_grounded_template_lines(query, route_matter(query), passages))
        assert joined, query
        for part in expected_parts:
            assert part in joined, query


def test_generic_hr_pip_prompt_sources_hide_irrelevant_gig_social_security():
    from types import SimpleNamespace

    from apps.api.main import _prompt_retrieval_candidates
    from apps.api.matter_router import route_matter

    query = "i complained against my manager for harassment to HR and now they are putting me on PIP, is this retaliation"
    route = route_matter(query)
    chunks = [
        SimpleNamespace(title="Code on Social Security 2020", anchor="social-security-code-2020/sec-114-a"),
        SimpleNamespace(title="Occupational Safety, Health and Working Conditions Code 2020", anchor="osh-code-2020/sec-114"),
        SimpleNamespace(title="Industrial Disputes Act 1947", anchor="industrial-disputes-1947/sec-2A"),
        SimpleNamespace(title="Industrial Disputes Act 1947", anchor="industrial-disputes-1947/sec-25F"),
    ]

    filtered = _prompt_retrieval_candidates(query, route, chunks)

    assert [chunk.title for chunk in filtered] == [
        "Industrial Disputes Act 1947",
        "Industrial Disputes Act 1947",
    ]


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
    assert names == ["matter_route", "legal_issue_plan", "error", "timing"]
    route_payload = next(d for ev, d in events if ev == "matter_route")
    assert route_payload["category"] == "police_fir"
    plan_payload = next(d for ev, d in events if ev == "legal_issue_plan")
    assert plan_payload["primary_issue"] == "police_fir"
    assert "incident_date_needed" in plan_payload["safety_flags"]
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
