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


def _rbi_ombudsman_sources(start_index: int = 1) -> list[dict[str, object]]:
    return [
        {"index": start_index, "title": "Reserve Bank Integrated Ombudsman Scheme 2021", "anchor": "rbi-integrated-ombudsman-2021/sec-1"},
        {"index": start_index + 1, "title": "Reserve Bank Integrated Ombudsman Scheme 2021", "anchor": "rbi-integrated-ombudsman-2021/sec-3"},
        {"index": start_index + 2, "title": "Reserve Bank Integrated Ombudsman Scheme 2021", "anchor": "rbi-integrated-ombudsman-2021/sec-6"},
        {"index": start_index + 3, "title": "Reserve Bank Integrated Ombudsman Scheme 2021", "anchor": "rbi-integrated-ombudsman-2021/sec-9"},
        {"index": start_index + 4, "title": "Reserve Bank Integrated Ombudsman Scheme 2021", "anchor": "rbi-integrated-ombudsman-2021/sec-10"},
    ]


def _loan_app_regulatory_sources(start_index: int = 1) -> list[dict[str, object]]:
    return [
        {"index": start_index, "title": "Reserve Bank of India (Digital Lending) Directions, 2025", "anchor": "rbi-digital-lending-directions-2025/para-11"},
        {"index": start_index + 1, "title": "Reserve Bank of India (Digital Lending) Directions, 2025", "anchor": "rbi-digital-lending-directions-2025/para-12"},
        {"index": start_index + 2, "title": "Outsourcing of Financial Services - Responsibilities of regulated entities employing Recovery Agents", "anchor": "rbi-recovery-agents-2022/para-2"},
        *_rbi_ombudsman_sources(start_index + 3),
    ]


def test_college_certificate_prompt_candidates_filter_rte_bleed():
    from apps.api import main as api_main
    from apps.api.matter_router import route_matter

    query = "college is holding my original marksheets after I discontinued course"
    route = route_matter(query)
    retrieved = [
        SimpleNamespace(
            title="All India Council for Technical Education Approval Process Handbook 2022-23",
            statute_short=None,
            anchor="aicte-approval-process-handbook-2023/refund-original-documents-8.13",
            document_id="aicte-approval-process-handbook-2023",
            source_type="guideline",
        ),
        SimpleNamespace(
            title="Right to Information Act 2005",
            statute_short=None,
            anchor="rti-2005/sec-6",
            document_id="rti-2005",
            source_type="bare_act",
        ),
        SimpleNamespace(
            title="Right of Children to Free and Compulsory Education Act 2009",
            statute_short=None,
            anchor="rte-2009/sec-5",
            document_id="rte-2009",
            source_type="bare_act",
        ),
    ]

    filtered = api_main._prompt_retrieval_candidates(query, route, retrieved)
    assert [hit.title for hit in filtered] == [
        "All India Council for Technical Education Approval Process Handbook 2022-23",
        "Right to Information Act 2005",
    ]


def test_caste_public_access_prompt_candidates_keep_article17_and_pcr():
    from apps.api import main as api_main
    from apps.api.matter_router import route_matter

    query = "pls tell village headman saying my caste cant enter temple in festival dindori what rights need lawyer or police"
    route = route_matter(query)
    retrieved = [
        SimpleNamespace(title="Bharatiya Nagarik Suraksha Sanhita 2023", anchor="bnss-2023/sec-173", metadata={"_required_source_pack": "bnss_2023_scst_atrocity_fir"}, rerank_score=0.9),
        SimpleNamespace(title="Bharatiya Nyaya Sanhita 2023", anchor="bns-2023/sec-298", metadata={"_required_source_pack": "bns_2023_religious_insult"}, rerank_score=0.9),
        SimpleNamespace(title="Code of Criminal Procedure 1973", anchor="crpc-1973/sec-200", metadata={"_required_source_pack": "crpc_1973_scst_atrocity_fir"}, rerank_score=0.9),
        SimpleNamespace(title="Protection of Civil Rights Act 1955", anchor="protection-civil-rights-1955/sec-3", metadata={"_required_source_pack": "protection_civil_rights_1955_religious_access"}, rerank_score=0.52),
        SimpleNamespace(title="Protection of Civil Rights Act 1955", anchor="protection-civil-rights-1955/sec-4", metadata={"_required_source_pack": "protection_civil_rights_1955"}, rerank_score=0.52),
        SimpleNamespace(title="Constitution of India", anchor="constitution-india/sec-17", metadata={"_required_source_pack": "constitution_article_17"}, rerank_score=0.52),
        SimpleNamespace(title="Scheduled Castes and Scheduled Tribes (Prevention of Atrocities) Act 1989", anchor="sc-st-poa-1989/sec-3", metadata={"_required_source_pack": "scst_poa_1989"}, rerank_score=0.96),
    ]

    filtered = api_main._prompt_retrieval_candidates(query, route, retrieved)
    assert [hit.anchor for hit in filtered[:4]] == [
        "constitution-india/sec-17",
        "protection-civil-rights-1955/sec-3",
        "protection-civil-rights-1955/sec-4",
        "sc-st-poa-1989/sec-3",
    ]


def test_sarna_attack_prompt_candidates_keep_poa_before_secondary_criminal_sources():
    from apps.api import main as api_main
    from apps.api.matter_router import route_matter

    query = "mob attacked our pahan during sarna puja calling adivasi non hindu jharkhand"
    route = route_matter(query)
    retrieved = [
        SimpleNamespace(title="Bharatiya Nagarik Suraksha Sanhita 2023", anchor="bnss-2023/sec-173", rerank_score=0.52),
        SimpleNamespace(title="Bharatiya Nyaya Sanhita 2023", anchor="bns-2023/sec-298", rerank_score=0.52),
        SimpleNamespace(title="Constitution of India", anchor="constitution-india/sec-21", rerank_score=0.52),
        SimpleNamespace(title="Scheduled Castes and Scheduled Tribes (Prevention of Atrocities) Act 1989", anchor="sc-st-poa-1989/sec-3-d", rerank_score=0.96),
        SimpleNamespace(title="Code of Criminal Procedure 1973", anchor="crpc-1973/sec-200", rerank_score=0.52),
    ]

    filtered = api_main._prompt_retrieval_candidates(query, route, retrieved)
    assert [hit.anchor for hit in filtered[:4]] == [
        "sc-st-poa-1989/sec-3-d",
        "bnss-2023/sec-173",
        "bns-2023/sec-298",
        "constitution-india/sec-21",
    ]


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
                chunk_id=1, document_id=1, anchor="consumer-protection-2019/sec-35",
                text="Section 35 of the Consumer Protection Act provides for filing a consumer complaint.",
                title="Consumer Protection Act 2019", source_type="bare_act",
                subject_area="consumer", as_at=None, paragraph_no=None,
                citation=None, court=None, statute_short="CPA-2019",
                dense_score=0.85, bm25_score=0.6, rerank_score=0.82,
            ),
            retrieval.RetrievedChunk(
                chunk_id=2, document_id=1, anchor="consumer-protection-2019/sec-39",
                text="Section 39 permits orders including replacement, refund, and compensation.",
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
        "The Commission may order replacement, refund, or compensation [2].",
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
            assert "matter_plan" in event_names
            assert "coverage" in event_names
            assert "passages" in event_names
            assert event_names.index("matter_route") < event_names.index("matter_plan")
            assert event_names.index("matter_plan") < event_names.index("coverage")
            plan = next(d for ev, d in events if ev == "matter_plan")
            assert plan["schema_version"] == 2
            assert plan["plan_id"].startswith("matter_plan_v2_")
            assert plan["primary_issue"] == "consumer"
            assert plan["user_role"] == "consumer_or_customer"
            assert plan["authority_ledger"][0]["act"] == "Consumer Protection Act 2019"
            assert plan["action_pack_id"] == "consumer"
            controlling_authority_id = plan["authority_ledger"][0]["authority_id"]
            assert controlling_authority_id
            passage_payload = next(d for ev, d in events if ev == "passages")
            assert passage_payload
            assert all(
                controlling_authority_id in passage["authority_ids"]
                for passage in passage_payload
            )
            # Each sentence verifier verdict streamed
            assert event_names.count("sentence") >= 1
            source_payload = next(d for ev, d in events if ev == "sources")
            assert source_payload
            cited_indices = {
                citation
                for ev, payload in events
                if ev == "sentence"
                for citation in payload.get("citations", [])
            }
            assert cited_indices
            sources_by_index = {source["index"]: source for source in source_payload}
            assert cited_indices <= sources_by_index.keys()
            assert all(
                controlling_authority_id in sources_by_index[index]["authority_ids"]
                for index in cited_indices
            )
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


def test_actionable_source_intro_precedes_judgment_only_sentence_for_lay_route():
    from apps.api.main import _actionable_source_intro_line_for_sentence
    from apps.api.matter_router import route_matter
    from apps.api.verifier import SentenceStatus, SentenceVerification

    route = route_matter("bank deducted money wrongly and customer care not helping")
    passages = [
        {"index": 1, "title": "CCI CHAMBERS CO-OP. HSG. SOCIETY LTD. versus DEVELOPMENT CREDIT BANK LTD.", "anchor": "2003-insc-1#para-4", "source_type": "sc_judgment"},
        {"index": 2, "title": "Reserve Bank Integrated Ombudsman Scheme 2021", "anchor": "rbi-integrated-ombudsman-2021/sec-2", "source_type": "bare_act", "required_source_pack": "rbi_integrated_ombudsman_2021"},
        {"index": 3, "title": "Consumer Protection Act 2019", "anchor": "consumer-protection-2019/sec-35", "source_type": "bare_act", "required_source_pack": "consumer_protection_2019"},
    ]
    state = {"emitted_citation_indices": set()}
    judgment_sentence = SentenceVerification(
        "The Supreme Court treated a bank-service dispute as consumer service deficiency [1].",
        SentenceStatus.OK,
        citations=[1],
    )

    line = _actionable_source_intro_line_for_sentence(route, passages, state, judgment_sentence)

    assert line is not None
    assert "bank/RBI complaint source" in line
    assert "before relying on judgments" in line
    assert "Reserve Bank Integrated Ombudsman Scheme 2021" in line
    assert "[2]" in line


def test_actionable_source_intro_not_added_after_official_source_is_cited():
    from apps.api.main import _actionable_source_intro_line_for_sentence
    from apps.api.matter_router import route_matter
    from apps.api.verifier import SentenceStatus, SentenceVerification

    route = route_matter("bank deducted money wrongly and customer care not helping")
    passages = [
        {"index": 1, "title": "CCI CHAMBERS CO-OP. HSG. SOCIETY LTD. versus DEVELOPMENT CREDIT BANK LTD.", "anchor": "2003-insc-1#para-4", "source_type": "sc_judgment"},
        {"index": 2, "title": "Reserve Bank Integrated Ombudsman Scheme 2021", "anchor": "rbi-integrated-ombudsman-2021/sec-2", "source_type": "bare_act", "required_source_pack": "rbi_integrated_ombudsman_2021"},
    ]
    state = {"emitted_citation_indices": {2}}
    judgment_sentence = SentenceVerification(
        "The Supreme Court treated a bank-service dispute as consumer service deficiency [1].",
        SentenceStatus.OK,
        citations=[1],
    )

    assert _actionable_source_intro_line_for_sentence(route, passages, state, judgment_sentence) is None


def test_contract_floor_skips_crpc_bail_backup_for_household_safety_routes():
    from apps.api.main import _answer_contract_lines
    from apps.api.matter_router import route_matter

    drug_route = route_matter("i caught my husband with drugs what should i do")
    drug_passages = [
        {"index": 1, "title": "Narcotic Drugs and Psychotropic Substances Act 1985", "anchor": "ndps-1985/sec-20", "source_type": "bare_act", "required_source_pack": "ndps_1985_household_drug_safety"},
        {"index": 2, "title": "Bharatiya Nagarik Suraksha Sanhita 2023", "anchor": "bnss-2023/sec-173", "source_type": "bare_act", "required_source_pack": "bnss_2023"},
        {"index": 3, "title": "Code of Criminal Procedure 1973", "anchor": "crpc-1973/sec-437", "source_type": "bare_act", "required_source_pack": "crpc_1973"},
    ]
    state = {
        "emitted_citation_indices": {1, 2},
        "seen_sentences": set(),
        "saw_next_step_header": True,
        "saw_next_step_sentence": True,
        "emitted": 5,
    }

    drug_lines = _answer_contract_lines(drug_route, drug_passages, state)

    assert not any("Code of Criminal Procedure" in line for line in drug_lines)

    child_route = route_matter("i caught my wife beating my child what should i do")
    child_passages = [
        {"index": 1, "title": "Bharatiya Nyaya Sanhita 2023", "anchor": "bns-2023/sec-115", "source_type": "bare_act", "required_source_pack": "bns_2023"},
        {"index": 2, "title": "Bharatiya Nagarik Suraksha Sanhita 2023", "anchor": "bnss-2023/sec-173", "source_type": "bare_act", "required_source_pack": "bnss_2023"},
        {"index": 3, "title": "Code of Criminal Procedure 1973", "anchor": "crpc-1973/sec-437", "source_type": "bare_act", "required_source_pack": "crpc_1973"},
        {"index": 4, "title": "Juvenile Justice (Care and Protection of Children) Act 2015", "anchor": "jj-2015/sec-30", "source_type": "bare_act", "required_source_pack": "jj_2015_child_safety"},
    ]
    child_lines = _answer_contract_lines(child_route, child_passages, state)

    assert not any("Code of Criminal Procedure" in line for line in child_lines)


def test_contract_floor_skips_criminal_backup_for_drug_treatment_support_route():
    from apps.api.main import _answer_contract_lines
    from apps.api.matter_router import route_matter

    route = route_matter("my son is taking drugs and needs treatment what can I do")
    passages = [
        {"index": 1, "title": "Narcotic Drugs and Psychotropic Substances Act 1985", "anchor": "ndps-1985/sec-71", "source_type": "bare_act", "required_source_pack": "ndps_1985_drug_treatment_support"},
        {"index": 2, "title": "Bharatiya Nyaya Sanhita 2023", "anchor": "bns-2023/sec-115", "source_type": "bare_act", "required_source_pack": "bns_2023"},
        {"index": 3, "title": "Narcotic Drugs and Psychotropic Substances Act 1985", "anchor": "ndps-1985/sec-37", "source_type": "bare_act", "required_source_pack": "ndps_1985"},
    ]
    state = {
        "emitted_citation_indices": {1},
        "seen_sentences": set(),
        "saw_next_step_header": True,
        "saw_next_step_sentence": True,
        "emitted": 5,
    }

    lines = _answer_contract_lines(route, passages, state)

    assert not any("Bharatiya Nyaya Sanhita" in line for line in lines)
    assert not any("Section 37" in line for line in lines)


@pytest.mark.needs_stack
def test_answer_emits_unknown_criminal_regime_caveat(monkeypatch):
    """Unknown-date criminal routes get a deterministic user-visible caveat."""
    from apps.api import main as api_main
    from apps.api import retrieval
    from apps.api.main import CRIMINAL_REGIME_CAVEAT

    def chunk(chunk_id, title, anchor, text, source_pack):
        return retrieval.RetrievedChunk(
            chunk_id=chunk_id,
            document_id=chunk_id,
            anchor=anchor,
            text=text,
            title=title,
            source_type="bare_act",
            subject_area="criminal",
            as_at=None,
            paragraph_no=None,
            citation=None,
            court=None,
            statute_short=title,
            dense_score=0.9,
            bm25_score=0.8,
            rerank_score=0.95,
            metadata={"_required_source_pack": source_pack},
        )

    chunks = [
        chunk(
            1,
            "Bharatiya Nagarik Suraksha Sanhita 2023",
            "bnss-2023/sec-173-a",
            "Information about a cognizable offence may be given orally or electronically.",
            "bnss_2023_vehicle_theft_fir",
        ),
        chunk(
            2,
            "Bharatiya Nagarik Suraksha Sanhita 2023",
            "bnss-2023/sec-173-c",
            "On refusal, the information may be sent to the Superintendent of Police and then the Magistrate.",
            "bnss_2023_vehicle_theft_fir",
        ),
        chunk(
            3,
            "Code of Criminal Procedure 1973",
            "crpc-1973/sec-154",
            "Section 154 provides the cognizable-information and refusal route.",
            "crpc_1973_vehicle_theft_fir",
        ),
    ]

    async def fake_multi_query_retrieve(*args, **kwargs):
        return chunks, []

    async def fake_retrieve(*args, **kwargs):
        return chunks

    monkeypatch.setattr(api_main, "multi_query_hybrid_retrieve", fake_multi_query_retrieve)
    monkeypatch.setattr(api_main, "hybrid_retrieve", fake_retrieve)
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
            "q": "my bike is stolen and police refuse FIR",
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
def test_matter_route_event_includes_collision_trace_for_debugging(monkeypatch):
    from apps.api import main as api_main

    async def fail_model(*args, **kwargs):
        raise AssertionError("off-topic request should not check the LLM")

    monkeypatch.setattr(api_main, "check_model_available", fail_model)

    with TestClient(app) as c:
        with c.stream("POST", "/answer", json={
            "q": "recipe for biryani",
            "top_k": 4,
        }) as r:
            events = _collect_events(r)

    route_payload = next(d for ev, d in events if ev == "matter_route")
    assert route_payload["category"] == "off_topic"
    assert route_payload["route_trace"]["selected"]["category"] == "off_topic"
    assert "candidates" in route_payload["route_trace"]


def test_legal_aid_template_keeps_civil_affordability_out_of_custody_track():
    from apps.api.main import _is_safe_template_source_bridge, _legal_aid_eligibility_template_lines
    from apps.api.matter_router import route_matter

    passages = [
        {
            "index": 1,
            "title": "Legal Services Authorities Act 1987",
            "anchor": "legal-services-authorities-1987/sec-12",
        },
        {
            "index": 2,
            "title": "Legal Services Authorities Act 1987",
            "anchor": "legal-services-authorities-1987/sec-9",
        },
        {
            "index": 3,
            "title": "Constitution of India",
            "anchor": "constitution-india/sec-39a",
        },
        {
            "index": 4,
            "title": "Constitution of India",
            "anchor": "constitution-india/sec-22",
        },
        {
            "index": 5,
            "title": "Bharatiya Nagarik Suraksha Sanhita 2023",
            "anchor": "bnss-2023/sec-47",
        },
    ]

    lines = _legal_aid_eligibility_template_lines(
        "private lawyer expensive for property partition suit can i get legal aid",
        passages,
    )
    text = " ".join(lines).lower()

    assert "property partition suit" in text
    assert "lawyer assignment" in text
    assert "jail superintendent" not in text
    assert "arrest/remand" not in text
    assert "jail/prison" not in text
    assert _is_safe_template_source_bridge(
        "For a property partition suit, legal aid is about getting help with lawyer assignment, filing, reply, or court representation if you qualify; it does not by itself decide the ownership or merits of the case [1].",
        route_matter("private lawyer expensive for property partition suit can i get legal aid"),
    )


def test_legal_aid_template_preserves_custody_lawyer_access_track():
    from apps.api.main import _legal_aid_eligibility_template_lines

    passages = [
        {
            "index": 1,
            "title": "Legal Services Authorities Act 1987",
            "anchor": "legal-services-authorities-1987/sec-12",
        },
        {
            "index": 2,
            "title": "Constitution of India",
            "anchor": "constitution-india/sec-22",
        },
        {
            "index": 3,
            "title": "Bharatiya Nagarik Suraksha Sanhita 2023",
            "anchor": "bnss-2023/sec-47",
        },
    ]

    lines = _legal_aid_eligibility_template_lines(
        "family cannot afford lawyer for first remand tomorrow how to get legal aid at court",
        passages,
    )
    text = " ".join(lines).lower()

    assert "custody legal-aid" in text
    assert "arrest/remand" in text
    assert "bnss arrest-information" in text or "custody-procedure source" in text


def test_adult_age_record_correction_template_does_not_become_juvenile_route():
    from apps.api.main import _grounded_template_lines
    from apps.api.matter_router import route_matter

    q = "police picked my 19 year old cousin and he says old school ID has wrong DOB, can he still ask for bail"
    joined = " ".join(_grounded_template_lines(q, route_matter(q), [
        {"index": 1, "title": "Bharatiya Nagarik Suraksha Sanhita 2023", "anchor": "bnss-2023/sec-480"},
        {"index": 2, "title": "Bharatiya Nagarik Suraksha Sanhita 2023", "anchor": "bnss-2023/sec-173"},
        {"index": 3, "title": "Code of Criminal Procedure 1973", "anchor": "crpc-1973/sec-437"},
        {"index": 4, "title": "Juvenile Justice (Care and Protection of Children) Act 2015", "anchor": "jj-2015/sec-94"},
    ]))

    assert "ordinary bail" in joined
    assert "age-record correction" in joined
    assert "Investigating Officer" in joined
    assert "[1]" in joined and "[2]" in joined
    assert "Juvenile Justice" not in joined
    assert "Juvenile Justice Board" not in joined


def test_adult_fir_minor_by_mistake_template_corrects_record_without_llm():
    from apps.api.main import _grounded_template_lines
    from apps.api.matter_router import route_matter

    q = "my son is 18 plus but police wrote minor by mistake in FIR, how to correct age record in criminal case"
    joined = " ".join(_grounded_template_lines(q, route_matter(q), [
        {"index": 5, "title": "Bharatiya Nagarik Suraksha Sanhita 2023", "anchor": "bnss-2023/sec-173"},
        {"index": 6, "title": "Bharatiya Nagarik Suraksha Sanhita 2023", "anchor": "bnss-2023/sec-480"},
    ]))

    assert "adult criminal-case age-record correction" in joined
    assert "written correction request" in joined
    assert "same criminal court" in joined
    assert "[5]" in joined
    assert "Juvenile Justice Board" not in joined


def test_adult_chargesheet_age_record_correction_beats_juvenile_rescue():
    from apps.api.main import _grounded_template_lines
    from apps.api.matter_router import route_matter

    q = "my daughter is 19 but charge sheet says 17 due to wrong school DOB, what to file in criminal court"
    joined = " ".join(_grounded_template_lines(q, route_matter(q), [
        {"index": 1, "title": "Bharatiya Nagarik Suraksha Sanhita 2023", "anchor": "bnss-2023/sec-480"},
        {"index": 2, "title": "Bharatiya Nagarik Suraksha Sanhita 2023", "anchor": "bnss-2023/sec-173"},
        {"index": 3, "title": "Juvenile Justice (Care and Protection of Children) Act 2015", "anchor": "jj-2015/sec-94"},
    ]))

    assert "your adult daughter" in joined
    assert "adult criminal-case age-record correction" in joined
    assert "Investigating Officer" in joined
    assert "Juvenile Justice Board" not in joined


def test_custodial_abuse_with_medical_words_does_not_become_custody_medical():
    from apps.api.main import _grounded_template_lines
    from apps.api.matter_router import route_matter

    q = "police beat my brother in lockup and refused medical examination, what immediate record to preserve"
    joined = " ".join(_grounded_template_lines(q, route_matter(q), [
        {"index": 1, "title": "Constitution of India", "anchor": "constitution-india/sec-21"},
        {"index": 2, "title": "Protection of Human Rights Act 1993", "anchor": "protection-human-rights-1993/sec-12"},
        {"index": 3, "title": "Bharatiya Nagarik Suraksha Sanhita 2023", "anchor": "bnss-2023/sec-173"},
        {"index": 4, "title": "Prisons Act 1894", "anchor": "prisons-1894/sec-37"},
    ]))

    assert "police torture" in joined.lower() or "lockup beating" in joined.lower()
    assert "custody timeline" in joined
    assert "medical care in jail" not in joined.lower()


def test_cheque_138_with_police_call_keeps_cheque_track():
    from apps.api.main import _grounded_template_lines
    from apps.api.matter_router import route_matter

    q = "cheque 138 court notice came and police are calling me to station, what should I verify first"
    route = route_matter(q)
    joined = " ".join(_grounded_template_lines(q, route, [
        {"index": 1, "title": "Negotiable Instruments Act 1881", "anchor": "negotiable-instruments-1881/sec-138"},
        {"index": 2, "title": "Negotiable Instruments Act 1881", "anchor": "negotiable-instruments-1881/sec-142"},
        {"index": 3, "title": "Bharatiya Nagarik Suraksha Sanhita 2023", "anchor": "bnss-2023/sec-223"},
    ]))

    assert route.category == "cheque_bounce"
    assert "Section 138" in joined
    assert "case number" in joined
    assert "Magistrate complaint route" in joined


def test_lockup_beating_nhrc_question_uses_custodial_violence_template():
    from apps.api.main import _grounded_template_lines
    from apps.api.matter_router import route_matter

    q = "lockup police beat my cousin and refused medical exam, should we go NHRC or magistrate first"
    joined = " ".join(_grounded_template_lines(q, route_matter(q), [
        {"index": 1, "title": "Constitution of India", "anchor": "constitution-india/sec-21"},
        {"index": 2, "title": "Protection of Human Rights Act 1993", "anchor": "protection-human-rights-1993/sec-12"},
        {"index": 3, "title": "Bharatiya Nagarik Suraksha Sanhita 2023", "anchor": "bnss-2023/sec-173"},
        {"index": 4, "title": "Bharatiya Nyaya Sanhita 2023", "anchor": "bns-2023/sec-117"},
    ]))

    assert "police torture" in joined.lower() or "lockup beating" in joined.lower()
    assert "Human Rights Act" in joined
    assert "BNSS" in joined
    assert "BNS" in joined


def test_private_assault_fir_delay_uses_ordinary_fir_template():
    from apps.api.main import _grounded_template_lines
    from apps.api.matter_router import route_matter

    q = "neighbour assaulted me and local police delayed FIR, no police custody involved, which complaint route"
    joined = " ".join(_grounded_template_lines(q, route_matter(q), [
        {"index": 1, "title": "Bharatiya Nagarik Suraksha Sanhita 2023", "anchor": "bnss-2023/sec-173"},
        {"index": 2, "title": "Bharatiya Nyaya Sanhita 2023", "anchor": "bns-2023/sec-117"},
    ]))

    assert "ordinary assault/FIR-refusal track" in joined
    assert "BNS hurt" in joined
    assert "custodial-violence" in joined


def test_contract_floor_adds_bns_for_private_assault_after_generic_sources():
    from apps.api.main import _answer_contract_lines
    from apps.api.legal_issue_plan import build_matter_plan
    from apps.api.matter_router import route_matter

    q = "neighbour assaulted me and local police delayed FIR, no police custody involved, which complaint route"
    route = route_matter(q)
    plan = build_matter_plan(q, route)
    passages = [
        {
            "index": 1,
            "title": "Constitution of India",
            "anchor": "constitution-india/sec-21",
            "source_type": "bare_act",
        },
        {
            "index": 2,
            "title": "Protection of Human Rights Act 1993",
            "anchor": "protection-human-rights-1993/sec-12",
            "source_type": "bare_act",
        },
        {
            "index": 3,
            "title": "Bharatiya Nagarik Suraksha Sanhita 2023",
            "anchor": "bnss-2023/sec-48",
            "source_type": "bare_act",
            "required_source_pack": "bnss_2023",
        },
        {
            "index": 4,
            "title": "Bharatiya Nyaya Sanhita 2023",
            "anchor": "bns-2023/sec-117",
            "source_type": "bare_act",
            "required_source_pack": "bns_2023",
        },
        {
            "index": 5,
            "title": "Code of Criminal Procedure 1973",
            "anchor": "crpc-1973/sec-50",
            "source_type": "bare_act",
        },
        {
            "index": 6,
            "title": "Bharatiya Nagarik Suraksha Sanhita 2023",
            "anchor": "bnss-2023/sec-173-b",
            "source_type": "bare_act",
            "required_source_pack": "bnss_2023",
        },
    ]
    state = {
        "emitted_citation_indices": {6},
        "seen_sentences": set(),
        "saw_next_step_header": True,
        "saw_next_step_sentence": True,
        "emitted": 5,
    }

    joined = " ".join(_answer_contract_lines(route, passages, state, plan, query=q))

    assert "BNS hurt/grievous-hurt source" in joined
    assert "[4]" in joined
    assert "Protection of Human Rights Act" not in joined
    assert "Constitution of India" not in joined
    assert "Code of Criminal Procedure" not in joined
    assert "Section 48" not in joined


def test_prison_mulaqat_video_and_visitor_failures_answer_specific_fact():
    from apps.api.main import _grounded_template_lines
    from apps.api.matter_router import route_matter

    passages = [
        {"index": 1, "title": "Delhi Prison Rules 2018", "anchor": "delhi-prison-rules-2018/rule-595-599"},
        {"index": 2, "title": "Constitution of India", "anchor": "constitution-india/sec-21"},
    ]
    video_q = "mandoli jail video call slot failed four times and staff says server down, can wife ask written order"
    visitor_q = "rohini jail removed my name from visitor list after address check delay, can superintendent give reasons"

    video = " ".join(_grounded_template_lines(video_q, route_matter(video_q), passages))
    visitor = " ".join(_grounded_template_lines(visitor_q, route_matter(visitor_q), passages))

    assert "video-call slot failed" in video
    assert "server is down" in video
    assert "visitor name was removed" in visitor
    assert "address check" in visitor


def test_prison_nominal_roll_for_high_court_bail_mentions_court_direction_route():
    from apps.api.main import _grounded_template_lines
    from apps.api.matter_router import route_matter

    q = "jail refuses nominal roll copy needed for high court bail saying only advocate can apply"
    passages = [
        {"index": 1, "title": "Prisons Act 1894", "anchor": "prisons-1894/sec-59"},
        {"index": 2, "title": "Right to Information Act 2005", "anchor": "rti-2005/sec-19-b"},
        {"index": 3, "title": "Constitution of India", "anchor": "constitution-india/sec-21"},
    ]

    joined = " ".join(_grounded_template_lines(q, route_matter(q), passages))

    assert "High Court bail" in joined
    assert "do not wait only for RTI" in joined
    assert "only an advocate can apply" in joined
    assert "court registry" in joined


def test_age_record_contract_floor_skips_unrelated_child_sources():
    from apps.api.main import _should_skip_unrelated_source_excerpt
    from apps.api.matter_router import route_matter

    adult_q = "my son is 18 plus but police wrote minor by mistake in FIR, how to correct age record in criminal case"
    assert _should_skip_unrelated_source_excerpt(
        route_matter(adult_q),
        {"title": "Protection of Children from Sexual Offences Act 2012", "anchor": "pocso-2012/sec-33-a"},
        query=adult_q,
    )

    juvenile_q = "police picked my 16 year old nephew and kept him overnight with adults, school certificate shows date of birth"
    assert _should_skip_unrelated_source_excerpt(
        route_matter(juvenile_q),
        {"title": "Bharatiya Nagarik Suraksha Sanhita 2023", "anchor": "bnss-2023/sec-48"},
        query=juvenile_q,
    )


def test_civil_witness_summons_template_blocks_bnss35_pmla_bleed():
    from apps.api.main import _grounded_template_lines
    from apps.api.matter_router import route_matter

    query = "court sent summons for witness evidence in my civil case and asked to bring documents, is this BNSS 35 police notice"
    passages = [
        {
            "index": 1,
            "title": "Code of Civil Procedure 1908",
            "anchor": "cpc-1908/order-v-summons",
        },
        {
            "index": 2,
            "title": "Prevention of Money Laundering Act 2002",
            "anchor": "pmla-2002/sec-35",
        },
        {
            "index": 3,
            "title": "Bharatiya Nagarik Suraksha Sanhita 2023",
            "anchor": "bnss-2023/sec-35",
        },
    ]

    lines = _grounded_template_lines(query, route_matter(query), passages)
    text = " ".join(lines).lower()

    assert "civil-court summons" in text
    assert "not treat it as a bnss 35 police notice" in text
    assert "pmla" not in text


def test_criminal_video_link_status_template_uses_criminal_procedure_not_cpc():
    from apps.api.main import _grounded_template_lines
    from apps.api.matter_router import route_matter

    query = "my criminal case was adjourned twice because video link failed but i am already on bail, how to ask next date status"
    passages = [
        {
            "index": 1,
            "title": "Bharatiya Nagarik Suraksha Sanhita 2023",
            "anchor": "bnss-2023/sec-530",
        },
        {
            "index": 2,
            "title": "Code of Criminal Procedure 1973",
            "anchor": "crpc-1973/sec-317",
        },
        {
            "index": 3,
            "title": "Code of Civil Procedure 1908",
            "anchor": "cpc-1908/sec-151",
        },
    ]

    lines = _grounded_template_lines(query, route_matter(query), passages)
    text = " ".join(lines).lower()

    assert "criminal-court case-status" in text
    assert "video-link" in text or "video link" in text
    assert "code of civil procedure" not in text
    assert "order xlii" not in text


def test_simple_assault_fir_delay_template_cites_bns_and_avoids_custodial_bleed():
    from apps.api.main import _grounded_template_lines
    from apps.api.matter_router import route_matter

    query = "neighbour hit me and police are delaying FIR, no police beating involved, should i go to SP or magistrate"
    passages = [
        {
            "index": 1,
            "title": "Bharatiya Nagarik Suraksha Sanhita 2023",
            "anchor": "bnss-2023/sec-173",
        },
        {
            "index": 2,
            "title": "Bharatiya Nagarik Suraksha Sanhita 2023",
            "anchor": "bnss-2023/sec-175",
        },
        {
            "index": 3,
            "title": "Bharatiya Nyaya Sanhita 2023",
            "anchor": "bns-2023/sec-115",
        },
        {
            "index": 4,
            "title": "Protection of Human Rights Act 1993",
            "anchor": "protection-human-rights-1993/sec-12",
        },
    ]

    lines = _grounded_template_lines(query, route_matter(query), passages)
    text = " ".join(lines).lower()

    assert "ordinary assault/fir-refusal" in text
    assert "bns hurt" in text
    assert "custodial-violence answer" in text
    assert "human rights act" not in text


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


@pytest.mark.needs_stack
def test_primary_workflow_template_does_not_append_unrelated_contract_floor(monkeypatch):
    """Reviewed primary workflows own the answer; generic source floors must
    not append nearby-but-wrong sources after the workflow has already emitted
    the user-facing next step.
    """
    from apps.api import main as api_main
    from apps.api import retrieval

    def chunk(
        chunk_id: int,
        title: str,
        anchor: str,
        *,
        source_type: str = "bare_act",
        required_source_pack: str = "",
    ) -> retrieval.RetrievedChunk:
        return retrieval.RetrievedChunk(
            chunk_id=chunk_id,
            document_id=chunk_id,
            anchor=anchor,
            text=(
                f"{title} source for complaint, grievance, application, "
                "appeal, written reasons, documents, and authority route."
            ),
            source_type=source_type,
            subject_area="education",
            as_at=None,
            paragraph_no=None,
            title=title,
            citation=None,
            court=None,
            statute_short=title,
            dense_score=0.95,
            bm25_score=0.95,
            rerank_score=0.95,
            metadata={"_required_source_pack": required_source_pack}
            if required_source_pack
            else {},
        )

    chunks = [
        chunk(
            1,
            "Right to Information Act 2005",
            "rti-2005/sec-19-b",
            required_source_pack="rti_2005",
        ),
        chunk(
            2,
            "Consumer Protection Act 2019",
            "consumer-protection-2019/sec-2",
            required_source_pack="consumer_protection_2019_education_service",
        ),
        chunk(
            3,
            "All India Council for Technical Education Approval Process Handbook 2022-23",
            "aicte-approval-process-handbook-2023/complaint-cases",
            source_type="guideline",
            required_source_pack="aicte_certificate_return_guideline",
        ),
        chunk(
            4,
            "Right of Children to Free and Compulsory Education Act 2009",
            "rte-2009/sec-14",
            required_source_pack="rte_2009",
        ),
    ]

    async def fake_multi_query_retrieve(*args, **kwargs):
        return chunks, []

    async def fake_retrieve(*args, **kwargs):
        return chunks

    monkeypatch.setattr(api_main, "multi_query_hybrid_retrieve", fake_multi_query_retrieve)
    monkeypatch.setattr(api_main, "hybrid_retrieve", fake_retrieve)
    _patch_relevance(monkeypatch, score=0.9)

    with TestClient(app) as c:
        with c.stream("POST", "/answer", json={
            "q": "college is holding my original certificates after I left the course",
            "top_k": 8,
        }) as r:
            events = _collect_events(r)

    workflow = next(data for event, data in events if event == "workflow")
    sentence_texts = [data.get("text", "") for event, data in events if event == "sentence"]
    joined = " ".join(sentence_texts)

    assert workflow["id"] == "college_original_certificate_release"
    assert workflow["answer_mode"] == "primary"
    assert "AICTE/approved-institution certificate-return source" in joined
    assert "Additional source to verify" not in joined
    assert "Right of Children to Free and Compulsory Education Act" not in joined


@pytest.mark.needs_stack
def test_primary_workflow_template_emits_missing_required_source_bridge(monkeypatch):
    """Primary workflow answers must still cite retrieved route-required law.

    This exercises the real /answer SSE path, not only the helper. The fake
    workflow cites the RBI source but omits the retrieved Consumer Protection
    source; source_floor_only should bridge that missing authority.
    """
    from apps.api import main as api_main
    from apps.api import retrieval
    from apps.api.common_workflow_contracts import WorkflowTemplateResult

    def chunk(
        chunk_id: int,
        title: str,
        anchor: str,
        *,
        required_source_pack: str,
        text: str,
    ) -> retrieval.RetrievedChunk:
        return retrieval.RetrievedChunk(
            chunk_id=chunk_id,
            document_id=chunk_id,
            anchor=anchor,
            text=text,
            source_type="bare_act",
            subject_area="banking",
            as_at=None,
            paragraph_no=None,
            title=title,
            citation=None,
            court=None,
            statute_short=title,
            dense_score=0.95,
            bm25_score=0.95,
            rerank_score=0.95,
            metadata={"_required_source_pack": required_source_pack},
        )

    chunks = [
        chunk(
            1,
            "Reserve Bank Integrated Ombudsman Scheme 2021",
            "rbi-integrated-ombudsman-2021/sec-2",
            required_source_pack="rbi_integrated_ombudsman_2021",
            text="The RBI Ombudsman Scheme covers complaints against regulated entities including banks.",
        ),
        chunk(
            2,
            "Reserve Bank Integrated Ombudsman Scheme 2021",
            "rbi-integrated-ombudsman-2021/sec-9",
            required_source_pack="rbi_integrated_ombudsman_2021",
            text="A complaint may be made after the regulated entity rejects it, gives an unsatisfactory reply, or does not reply within the prescribed period.",
        ),
        chunk(
            3,
            "Consumer Protection Act 2019",
            "consumer-protection-2019/sec-35",
            required_source_pack="consumer_protection_2019",
            text="A consumer may file a complaint before the District Commission.",
        ),
    ]

    async def fake_multi_query_retrieve(*args, **kwargs):
        return chunks, []

    async def fake_retrieve(*args, **kwargs):
        return chunks

    def fake_workflow_contract_result(query, route, passages, **kwargs):
        return WorkflowTemplateResult(
            id="wrong_bank_debit",
            source="authority_graph",
            answer_mode="primary",
            lines=[
                "**Short answer**",
                "For a wrong bank debit, first raise a written bank complaint and use the RBI Ombudsman/CMS route if the bank reply or non-reply does not fix it [1] [2].",
                "**What you can do next**",
                "- Keep the bank statement entry, transaction ID, complaint number, and written bank reply [1] [2].",
            ],
            required_sources=("rbi_scope", "rbi_complaint"),
            optional_sources=("consumer",),
            source_indices={"rbi_scope": 1, "rbi_complaint": 2},
        )

    monkeypatch.setattr(api_main, "multi_query_hybrid_retrieve", fake_multi_query_retrieve)
    monkeypatch.setattr(api_main, "hybrid_retrieve", fake_retrieve)
    monkeypatch.setattr(api_main, "plan_owned_workflow_contract_result", fake_workflow_contract_result)
    _patch_relevance(monkeypatch, score=0.9)
    _enable_fast_mode(monkeypatch)

    with TestClient(app) as c:
        with c.stream("POST", "/answer", json={
            "q": "bank deducted money wrongly and customer care not helping",
            "top_k": 8,
            "skip_nli": True,
        }) as r:
            events = _collect_events(r)

    workflow = next(data for event, data in events if event == "workflow")
    sentence_texts = [data.get("text", "") for event, data in events if event == "sentence"]
    joined = " ".join(sentence_texts)

    assert workflow["id"] == "wrong_bank_debit"
    assert workflow["answer_mode"] == "primary"
    assert "RBI Ombudsman/CMS route" in joined
    assert "Consumer Protection Act 2019, Section 35 [3]" in joined
    assert joined.count("Consumer Protection Act 2019, Section 35 [3]") == 1
    assert "District Legal Services Authority" not in joined


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


def test_obc_certificate_template_does_not_use_sc_st_article_wording():
    from apps.api.main import _grounded_template_lines
    from apps.api.matter_router import route_matter

    q = "OBC certificate pending and scholarship deadline is tomorrow"
    passages = [
        {"index": 1, "title": "Constitution of India", "anchor": "constitution-india/sec-44"},
        {"index": 2, "title": "Right to Information Act 2005", "anchor": "right-to-information-act-2005/sec-6"},
        {"index": 3, "title": "Right to Information Act 2005", "anchor": "right-to-information-act-2005/sec-19"},
    ]

    joined = " ".join(_grounded_template_lines(q, route_matter(q), passages))

    assert "OBC certificate" in joined
    assert "state OBC/non-creamy-layer rules" in joined
    assert "Article 341" not in joined
    assert "Article 342" not in joined


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


def test_grounded_template_for_asha_honorarium_has_concrete_next_step():
    from apps.api.main import _grounded_template_lines
    from apps.api.matter_router import route_matter

    q = "I am ASHA worker not paid honorarium 6 months who can help"
    passages = [
        {
            "index": 1,
            "title": "National Health Mission ASHA Incentives Guidelines 2025",
            "anchor": "nhm-asha-incentives-2025/full",
        },
        {
            "index": 2,
            "title": "Code on Wages 2019",
            "anchor": "code-on-wages-2019/sec-17@2019-08-08",
        },
    ]

    joined = " ".join(_grounded_template_lines(q, route_matter(q), passages))

    assert "National Health Mission ASHA Incentives Guidelines 2025" in joined
    assert "ASHA honorarium or incentive record" in joined
    assert "district NHM office" in joined
    assert "activity/incentive ledger" in joined
    assert "only a secondary payment-timing source" in joined
    assert "**What you can do next**" in joined


def test_welfare_worker_source_contract_does_not_cross_leak_asha_and_anganwadi():
    from apps.api.main import _should_skip_contract_source_line, _should_skip_unrelated_source_excerpt
    from apps.api.matter_router import route_matter

    anganwadi_route = route_matter("anganwadi helper honorarium pending how to complain")
    asha_route = route_matter("asha worker incentive not paid for 8 months block office ignoring")

    assert _should_skip_contract_source_line(
        anganwadi_route,
        "nhm_asha_incentives_2025",
        {"anganwadi_honorarium_case_law"},
    )
    assert _should_skip_unrelated_source_excerpt(
        anganwadi_route,
        {"title": "National Health Mission ASHA Incentives Guidelines 2025", "anchor": "nhm-asha-incentives-2025/page-1"},
    )
    assert _should_skip_contract_source_line(
        asha_route,
        "anganwadi_honorarium_case_law",
        {"nhm_asha_incentives_2025"},
    )
    assert _should_skip_unrelated_source_excerpt(
        asha_route,
        {"title": "STATE OF KARNATAKA AND ORS. versus AMEERBI AND ORS.", "anchor": "2006-insc-969#win-9", "source_type": "sc_judgment"},
    )


def test_grounded_template_for_uapa_default_bail_uses_special_statute_frame():
    from apps.api.main import _grounded_template_lines
    from apps.api.matter_router import route_matter

    q = "brother UAPA arrested 3 mnths chargesheet not filed total custody can be extended 180 days what next"
    passages = [
        {
            "index": 1,
            "title": "Unlawful Activities (Prevention) Act 1967",
            "anchor": "uapa-1967/sec-43d",
        },
        {
            "index": 2,
            "title": "Bharatiya Nagarik Suraksha Sanhita 2023",
            "anchor": "bnss-2023/sec-187@2024-07-01",
        },
        {
            "index": 3,
            "title": "Constitution of India",
            "anchor": "constitution-of-india/sec-21",
        },
    ]

    joined = " ".join(_grounded_template_lines(q, route_matter(q), passages))

    assert "special-statute default-bail calculation" in joined
    assert "ordinary 60/90-day rule" in joined
    assert "UAPA extension" in joined
    assert "extension order" in joined
    assert "charge-sheet filing date" in joined
    assert "Special Court or legal-aid lawyer" in joined


def test_grounded_template_for_uapa_header_only_does_not_claim_extension_source():
    from apps.api.main import _grounded_template_lines, _uapa_bail_or_default_bail_template_lines
    from apps.api.matter_router import route_matter

    q = "brother UAPA arrested 3 months chargesheet not filed default bail possible"
    header_only_passages = [
        {
            "index": 1,
            "title": "Unlawful Activities (Prevention) Act 1967",
            "anchor": "uapa-1967#header",
        },
        {
            "index": 2,
            "title": "Bharatiya Nagarik Suraksha Sanhita 2023",
            "anchor": "bnss-2023/sec-187@2024-07-01",
        },
    ]
    no_uapa_passages = [
        {
            "index": 1,
            "title": "Bharatiya Nagarik Suraksha Sanhita 2023",
            "anchor": "bnss-2023/sec-187@2024-07-01",
        },
    ]

    header_joined = " ".join(_grounded_template_lines(q, route_matter(q), header_only_passages))

    assert "special-statute flag" in header_joined
    assert "not enough by itself to calculate extension or default bail" in header_joined
    assert "UAPA extension source" not in header_joined
    assert _uapa_bail_or_default_bail_template_lines(q, no_uapa_passages) == []


def test_grounded_template_for_undertrial_review_gives_custody_chart_route():
    from apps.api.main import _grounded_template_lines
    from apps.api.matter_router import route_matter

    q = "paralegal asking 65 yr old undertrial diabetic eligible review committee BNSS 479 what next"
    passages = [
        {
            "index": 1,
            "title": "Bharatiya Nagarik Suraksha Sanhita 2023",
            "anchor": "bnss-2023/sec-479@2024-07-01",
        },
        {
            "index": 2,
            "title": "Legal Services Authorities Act 1987",
            "anchor": "legal-services-authorities-1987/sec-9",
        },
        {
            "index": 3,
            "title": "Constitution of India",
            "anchor": "constitution-of-india/sec-21",
        },
    ]

    joined = " ".join(_grounded_template_lines(q, route_matter(q), passages))

    assert "BNSS Section 479" in joined
    assert "Article 21 liberty and medical-vulnerability" in joined
    assert "Legal Services Authorities" in joined
    assert "custody chart" in joined
    assert "Under Trial Review Committee" in joined


def test_grounded_template_for_undertrial_lsa_only_does_not_call_lsa_custody_source():
    from apps.api.main import _grounded_template_lines
    from apps.api.matter_router import route_matter

    q = "undertrial 3 yrs in jail review committee old sick what next"
    passages = [
        {
            "index": 1,
            "title": "Legal Services Authorities Act 1987",
            "anchor": "legal-services-authorities-1987/sec-9",
        },
    ]

    joined = " ".join(_grounded_template_lines(q, route_matter(q), passages))

    assert "Legal Services Authorities source" in joined
    assert "legal-aid assistance route" in joined
    assert "cited custody-duration source [1]" not in joined


def test_stage_g_relevance_blocker_templates_are_user_shaped():
    from apps.api.main import _grounded_template_lines
    from apps.api.matter_router import route_matter

    cases = [
        (
            "can u tell special court POA case pending 5 years no judgement aurangabad maharashtra what can i do",
            [
                {"index": 1, "title": "Scheduled Castes and Scheduled Tribes (Prevention of Atrocities) Act 1989", "anchor": "sc-st-poa-1989/sec-14"},
                {"index": 2, "title": "Scheduled Castes and Scheduled Tribes (Prevention of Atrocities) Act 1989", "anchor": "sc-st-poa-1989/sec-15A"},
            ],
            ("Special Court", "5-year delay", "victim-rights source", "[1]", "[2]"),
        ),
        (
            "what to do ismw registration who does it i never heard about it 15 yrs in surat textile is this legal",
            [
                {"index": 3, "title": "Inter-State Migrant Workmen (Regulation of Employment and Conditions of Service) Act 1979", "anchor": "ismw-1979/sec-4"},
                {"index": 4, "title": "Inter-State Migrant Workmen (Regulation of Employment and Conditions of Service) Act 1979", "anchor": "ismw-1979/sec-12"},
            ],
            ("Surat textile work", "registration", "contractor-duty source", "[3]", "[4]"),
        ),
        (
            "can u tell social audit gram sabha showed corruption by sarpanch no action taken nuapada what can i do",
            [
                {"index": 5, "title": "Mahatma Gandhi National Rural Employment Guarantee Act 2005", "anchor": "mgnrega-2005/sec-17"},
                {"index": 6, "title": "Mahatma Gandhi National Rural Employment Guarantee Act 2005", "anchor": "mgnrega-2005/sec-19"},
                {"index": 7, "title": "Right to Information Act 2005", "anchor": "rti-2005/sec-6"},
            ],
            ("social-audit source", "action-taken status", "social-audit report", "[5]", "[6]", "[7]"),
        ),
        (
            "youtube struck my video for copyright but it was my own original song bro",
            [
                {"index": 8, "title": "Copyright Act 1957", "anchor": "copyright-1957/sec-51"},
                {"index": 9, "title": "Copyright Act 1957", "anchor": "copyright-1957/sec-55"},
            ],
            ("YouTube strike", "copyright ownership/takedown", "project files", "[8]", "[9]"),
        ),
        (
            "pls tell i am 73 christian widow can my stepchildren claim share in husband self acquired prop need lawyer or police",
            [
                {"index": 10, "title": "Indian Succession Act 1925", "anchor": "indian-succession-1925/sec-32"},
                {"index": 11, "title": "Indian Succession Act 1925", "anchor": "indian-succession-1925/sec-33A"},
                {"index": 12, "title": "Indian Succession Act 1925", "anchor": "indian-succession-1925/sec-37"},
            ],
            ("Christian widow", "not a police complaint", "Stepchildren", "[10]", "[11]", "[12]"),
        ),
        (
            "pls tell my husband died 2024 i am 78 mutation of land in my name jharkhand process need lawyer or police",
            [
                {"index": 13, "title": "Hindu Succession Act 1956", "anchor": "hindu-succession-1956/sec-8"},
                {"index": 14, "title": "Right to Information Act 2005", "anchor": "rti-2005/sec-6"},
            ],
            ("Jharkhand land mutation", "succession/heirship", "police only for forgery", "[13]", "[14]"),
        ),
        (
            "passport seized in mumbai airport for vape cartridge cbd legal in goa",
            [
                {"index": 15, "title": "Narcotic Drugs and Psychotropic Substances Act 1985", "anchor": "ndps-1985/sec-22"},
                {"index": 16, "title": "Narcotic Drugs and Psychotropic Substances Act 1985", "anchor": "ndps-1985/sec-37"},
            ],
            ("passport seized at Mumbai airport", "CBD/THC vape cartridge", "passport-retention", "[15]"),
        ),
        (
            "need help, husband in arthur road 4 mnths ndps commercial 25 kg ganja no chargesheet bail possible what next",
            [
                {"index": 17, "title": "Narcotic Drugs and Psychotropic Substances Act 1985", "anchor": "ndps-1985/sec-36A"},
                {"index": 18, "title": "Narcotic Drugs and Psychotropic Substances Act 1985", "anchor": "ndps-1985/sec-37"},
            ],
            ("four months in custody", "no chargesheet", "default-bail", "Special NDPS Court", "[17]"),
        ),
        (
            "thakur family stopped us from entering temple we are dalit",
            [
                {"index": 19, "title": "Constitution of India", "anchor": "constitution-india/sec-17"},
                {"index": 20, "title": "Protection of Civil Rights Act 1955", "anchor": "protection-civil-rights-1955/sec-3"},
                {"index": 21, "title": "Scheduled Castes and Scheduled Tribes (Prevention of Atrocities) Act 1989", "anchor": "sc-st-poa-1989/sec-3-d"},
            ],
            ("Thakur family stopped Dalit persons from entering a temple", "temple-entry/untouchability complaint", "ordinary village quarrel", "[20]"),
        ),
    ]

    for query, passages, expected_parts in cases:
        joined = " ".join(_grounded_template_lines(query, route_matter(query), passages))
        assert joined, query
        for part in expected_parts:
            assert part in joined, query


def test_stage_g_temple_entry_user_fact_bridge_survives_template_filter():
    from apps.api.main import _is_safe_template_source_bridge
    from apps.api.matter_router import route_matter

    q = "thakur family stopped us from entering temple we are dalit"
    route = route_matter(q)
    sent = (
        "If a Thakur family stopped Dalit persons from entering a temple, "
        "treat it as a temple-entry/untouchability complaint, not an ordinary "
        "village quarrel; record the caste identity, date, place, and names "
        "in the written police/DLSA complaint [20]."
    )

    assert _is_safe_template_source_bridge(sent, route)


def test_stage4_property_workflow_bridges_survive_template_filter():
    from apps.api.main import _is_safe_template_source_bridge
    from apps.api.matter_router import route_matter

    encroachment_q = "neighbour encroached on my land and police says civil matter"
    encroachment_route = route_matter(encroachment_q)
    assert _is_safe_template_source_bridge(
        "For neighbour land encroachment where police say it is a civil matter, treat the core remedy as a civil-court injunction, declaration, or possession-boundary case under the Specific Relief Act source [2].",
        encroachment_route,
    )

    pressure_q = "my uncle made my old father sign gift deed under pressure"
    pressure_route = route_matter(pressure_q)
    assert _is_safe_template_source_bridge(
        "Treat this as a property document allegedly signed under pressure; preserve that fact for the civil cancellation/declaration or free-consent challenge instead of treating it as only a family maintenance dispute [3].",
        pressure_route,
    )

    voluntary_gift_q = "my father willingly gifted flat to daughter now regrets it can we cancel gift deed"
    voluntary_gift_route = route_matter(voluntary_gift_q)
    assert _is_safe_template_source_bridge(
        "If your father willingly gifted the flat and now only regrets it, do not treat that as signed under pressure; a gift deed cannot be canceled unilaterally merely because the donor changed their mind [1].",
        voluntary_gift_route,
    )

    tenant_q = "tenant changed lock and stopped paying rent can I break lock"
    tenant_route = route_matter(tenant_q)
    assert _is_safe_template_source_bridge(
        "If the tenant changed the lock or stopped paying rent, do not use self-help by breaking the lock; use the notice, rent-arrears, possession, and civil/rent-authority route after checking the lease and state rent law [1].",
        tenant_route,
    )

    landlord_lockout_q = "landlord broke my lock and threw my things out because rent late"
    landlord_lockout_route = route_matter(landlord_lockout_q)
    assert _is_safe_template_source_bridge(
        "If the landlord broke your lock, threw out belongings, or locked you out for late rent, do not treat that as normal rent recovery; preserve possession and belongings proof and use the rent-authority/civil court route for restoration, injunction, damages, or deposit/rent accounting [1].",
        landlord_lockout_route,
    )

    builder_q = "builder delayed flat possession for 3 years and not refunding"
    builder_route = route_matter(builder_q)
    assert _is_safe_template_source_bridge(
        "For a builder/developer possession-delay/refund dispute, treat RERA as the primary real-estate project route [1].",
        builder_route,
    )

    builder_defect_q = "flat possession already given but bathroom tiles defective builder not repairing"
    builder_defect_route = route_matter(builder_defect_q)
    assert _is_safe_template_source_bridge(
        "For a builder/developer completed-flat defect/repair dispute after possession, treat the Consumer Protection Act route as the direct service-deficiency/repair/compensation route after possession [1].",
        builder_defect_route,
    )

    tribal_non_scheduled_q = "tribal family in non scheduled area sold land to moneylender now regrets"
    tribal_non_scheduled_route = route_matter(tribal_non_scheduled_q)
    assert _is_safe_template_source_bridge(
        "Because you say the land is in a non-Scheduled Area, do not apply PESA or Article 244 as if they are the restoration power; keep tribal status, the sale/deed facts, and the state revenue/civil cancellation route separate [2].",
        tribal_non_scheduled_route,
    )

    encroachment_assault_q = "neighbour beat me when I stopped his land encroachment and police refusing FIR"
    encroachment_assault_route = route_matter(encroachment_assault_q)
    assert _is_safe_template_source_bridge(
        "If your neighbour beat you during a land-encroachment dispute and police refuse to record the FIR, keep two tracks separate: the assault/FIR track goes to police-SP/Magistrate procedure, while the boundary/title track can stay civil/revenue [1].",
        encroachment_assault_route,
    )


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

    support_q = "my father is old and son not giving food or medicine"
    support_passages = [
        {"index": 1, "title": "Maintenance and Welfare of Parents and Senior Citizens Act 2007", "anchor": "mwp-2007/sec-4"},
        {"index": 2, "title": "Maintenance and Welfare of Parents and Senior Citizens Act 2007", "anchor": "mwp-2007/sec-9"},
    ]
    support_joined = " ".join(_grounded_template_lines(support_q, route_matter(support_q), support_passages))

    assert "your mother's" not in support_joined
    assert "your father's age proof" in support_joined
    assert "medical needs" in support_joined

    pension_support_q = "elderly mother pension stopped and children not helping what law"
    pension_support_joined = " ".join(
        _grounded_template_lines(pension_support_q, route_matter(pension_support_q), support_passages)
    )
    assert "your mother" in pension_support_joined
    assert "pension-stoppage issue" in pension_support_joined
    assert "children not helping" in pension_support_joined

    pressure_q = "my uncle made my old father sign gift deed under pressure"
    pressure_passages = [
        {"index": 1, "title": "Maintenance and Welfare of Parents and Senior Citizens Act 2007", "anchor": "mwp-2007/sec-23"},
        {"index": 2, "title": "Transfer of Property Act 1882", "anchor": "transfer-of-property-1882/sec-126"},
        {"index": 3, "title": "Specific Relief Act 1963", "anchor": "specific-relief-1963/sec-31"},
    ]
    pressure_joined = " ".join(_grounded_template_lines(pressure_q, route_matter(pressure_q), pressure_passages))
    assert "signed under pressure" in pressure_joined
    assert "civil cancellation/declaration" in pressure_joined
    assert "Specific Relief Act" in pressure_joined and "[3]" in pressure_joined


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
    assert "employer legal notice" in joined


def test_non_compete_next_step_survives_template_verifier():
    from apps.api.main import _is_safe_template_next_step
    from apps.api.matter_router import route_matter
    from apps.api.verifier import SentenceStatus, SentenceVerification

    route = route_matter("non compete clause in my employment contract for 2 years is it enforceable in india")
    header = SentenceVerification("**What you can do next**", SentenceStatus.OK)

    assert _is_safe_template_next_step(
        "- Review whether the clause is a post-employment restraint of trade and preserve the employment contract, offer letter, any employer legal notice, and exit documents [1].",
        route,
        header,
    )


def test_grounded_template_for_trademark_prior_user_uses_registry_rectification():
    from apps.api.main import _grounded_template_lines
    from apps.api.matter_router import route_matter

    q = "competitor registered my brand name as trademark first but i am already using 6 years surat can i file case"
    passages = [
        {"index": 1, "title": "Trade Marks Act 1999", "anchor": "trade-marks-1999/sec-34"},
        {"index": 2, "title": "Trade Marks Act 1999", "anchor": "trade-marks-1999/sec-57"},
        {"index": 3, "title": "Trade Marks Act 1999", "anchor": "trade-marks-1999/sec-134"},
    ]

    joined = " ".join(_grounded_template_lines(q, route_matter(q), passages)).lower()

    assert "prior-user" in joined or "prior-user source" in joined or "prior user" in joined
    assert "rectification" in joined
    assert "registry" in joined
    assert "passing-off" in joined
    assert "police" not in joined


def test_grounded_template_for_marketplace_ip_complaint_uses_counter_record_path():
    from apps.api.main import _grounded_template_lines
    from apps.api.matter_router import route_matter

    q = "amazon delisted my product saying ip complaint how to file counter notice trademark wala"
    passages = [
        {"index": 1, "title": "Trade Marks Act 1999", "anchor": "trade-marks-1999/sec-29"},
        {"index": 2, "title": "Trade Marks Act 1999", "anchor": "trade-marks-1999/sec-134"},
    ]

    joined = " ".join(_grounded_template_lines(q, route_matter(q), passages)).lower()

    assert "delisted" in joined
    assert "platform appeal" in joined or "counter-notice" in joined
    assert "trade marks act" in joined
    assert "consumer complaint" not in joined


def test_grounded_template_for_land_specific_performance_uses_contract_and_specific_relief():
    from apps.api.main import _grounded_template_lines
    from apps.api.matter_router import route_matter

    q = "want specific performance of land purchase deal seller backing out delhi commercial plot can i file case"
    passages = [
        {"index": 1, "title": "Specific Relief Act 1963", "anchor": "specific-relief-1963/sec-16@1925-01-01"},
        {"index": 2, "title": "Indian Contract Act 1872", "anchor": "indian-contract-1872/sec-10"},
        {"index": 3, "title": "Indian Contract Act 1872", "anchor": "indian-contract-1872/sec-37"},
        {"index": 4, "title": "Transfer of Property Act 1882", "anchor": "transfer-of-property-1882/sec-126"},
    ]

    joined = " ".join(_grounded_template_lines(q, route_matter(q), passages)).lower()

    assert "specific performance" in joined
    assert "specific relief act" in joined
    assert "indian contract act" in joined
    assert "agreement" in joined
    assert "section 126" not in joined


def test_grounded_template_for_silicosis_quarry_uses_occupational_disease_path():
    from apps.api.main import _grounded_template_lines
    from apps.api.matter_router import route_matter

    q = "what to do rajasthan stone quarry silicosis lungs gone 2 friends already died i have cough 6 months is this legal"
    passages = [
        {"index": 1, "title": "Employees' Compensation Act 1923", "anchor": "employees-compensation-1923/sec-3-a"},
        {"index": 2, "title": "Employees' Compensation Act 1923", "anchor": "employees-compensation-1923/sec-10-a"},
        {"index": 3, "title": "Factories Act 1948", "anchor": "factories-1948/sec-111"},
    ]

    joined = " ".join(_grounded_template_lines(q, route_matter(q), passages)).lower()

    assert "silicosis" in joined
    assert "stone-quarry" in joined or "stone quarry" in joined
    assert "occupational-disease" in joined or "occupational disease" in joined
    assert "compensation" in joined
    assert "medical-board" in joined or "medical board" in joined
    assert "construction accident" in joined


def test_grounded_template_for_copyright_reel_uses_platform_takedown_path():
    from apps.api.main import _grounded_template_lines
    from apps.api.matter_router import route_matter

    q = "fake influencer used my reel got 2M views without credit copyright bhai"
    passages = [
        {"index": 1, "title": "Trade Marks Act 1999", "anchor": "trade-marks-1999/sec-134"},
        {"index": 2, "title": "Copyright Act 1957", "anchor": "copyright-1957/sec-51"},
        {"index": 3, "title": "Copyright Act 1957", "anchor": "copyright-1957/sec-52-a"},
        {"index": 4, "title": "Copyright Act 1957", "anchor": "copyright-1957/sec-55"},
    ]

    joined = " ".join(_grounded_template_lines(q, route_matter(q), passages)).lower()

    assert "reel" in joined
    assert "influencer" in joined
    assert "without credit" in joined or "without permission" in joined
    assert "copyright" in joined
    assert "takedown" in joined
    assert "trademark opposition" in joined
    assert "[2]" in joined
    assert "[1]" not in joined
    assert "trade marks act" not in joined


def test_grounded_template_for_consumer_value_forum_uses_pecuniary_sources():
    from apps.api.main import _grounded_template_lines
    from apps.api.matter_router import route_matter

    q = "urgent consumer complain value 50 lakh which forum district state or national how to complain"
    passages = [
        {
            "index": 1,
            "title": "Consumer Protection (Jurisdiction of the District Commission, the State Commission and the National Commission) Rules 2021",
            "anchor": "consumer-jurisdiction-rules-2021/rule-2",
        },
        {
            "index": 2,
            "title": "Consumer Protection (Jurisdiction of the District Commission, the State Commission and the National Commission) Rules 2021",
            "anchor": "consumer-jurisdiction-rules-2021/rule-3",
        },
        {
            "index": 3,
            "title": "Consumer Protection (Jurisdiction of the District Commission, the State Commission and the National Commission) Rules 2021",
            "anchor": "consumer-jurisdiction-rules-2021/rule-4",
        },
        {"index": 4, "title": "Consumer Protection Act 2019", "anchor": "consumer-protection-2019/sec-35"},
    ]

    joined = " ".join(_grounded_template_lines(q, route_matter(q), passages)).lower()

    assert "pecuniary" in joined
    assert "district" in joined
    assert "state" in joined
    assert "national" in joined
    assert "50 lakh" in joined
    assert "2 crore" in joined
    assert "[1]" in joined and "[2]" in joined and "[3]" in joined


def test_grounded_template_for_poa_dsp_transfer_uses_investigation_record_path():
    from apps.api.main import _grounded_template_lines
    from apps.api.matter_router import route_matter

    q = "can u tell SP not transferring my atrocity case to DSP though POA Act says so vidarbha what can i do"
    passages = [
        {"index": 1, "title": "Scheduled Castes and Scheduled Tribes (Prevention of Atrocities) Rules 1995", "anchor": "sc-st-poa-rules-1995/rule-7"},
        {"index": 2, "title": "Scheduled Castes and Scheduled Tribes (Prevention of Atrocities) Act 1989", "anchor": "sc-st-poa-1989/sec-15A-a"},
        {"index": 3, "title": "Scheduled Castes and Scheduled Tribes (Prevention of Atrocities) Act 1989", "anchor": "sc-st-poa-1989/sec-14"},
    ]

    joined = " ".join(_grounded_template_lines(q, route_matter(q), passages)).lower()

    assert "dsp" in joined
    assert "rule 7" in joined
    assert "deputy superintendent" in joined
    assert "special court" in joined
    assert "written" in joined
    assert "[1]" in joined
    assert "[2]" in joined


def test_grounded_template_for_poa_dsp_transfer_without_rule7_avoids_uncited_rule_claim():
    from apps.api.main import _grounded_template_lines
    from apps.api.matter_router import route_matter

    q = "can u tell SP not transferring my atrocity case to DSP though POA Act says so vidarbha what can i do"
    passages = [
        {"index": 1, "title": "Scheduled Castes and Scheduled Tribes (Prevention of Atrocities) Act 1989", "anchor": "sc-st-poa-1989/sec-3-d"},
        {"index": 2, "title": "Scheduled Castes and Scheduled Tribes (Prevention of Atrocities) Act 1989", "anchor": "sc-st-poa-1989/sec-15A-a"},
        {"index": 3, "title": "Scheduled Castes and Scheduled Tribes (Prevention of Atrocities) Act 1989", "anchor": "sc-st-poa-1989/sec-14"},
    ]

    joined = " ".join(_grounded_template_lines(q, route_matter(q), passages)).lower()

    assert "dsp" in joined
    assert "rule 7" not in joined
    assert "not below deputy superintendent" not in joined
    assert "rank/order verification" in joined
    assert "sp" in joined
    assert "special court" in joined
    assert "written" in joined
    assert "[2]" in joined


def test_grounded_template_for_disability_termination_uses_rpwd_employment_path():
    from apps.api.main import _grounded_template_lines
    from apps.api.matter_router import route_matter

    q = "please help I have 60 percent disability my company terminated me saying I cannot meet targets but I was doing my work any remedy"
    passages = [
        {"index": 1, "title": "Rights of Persons with Disabilities Act 2016", "anchor": "rpwd-2016/sec-20"},
        {"index": 2, "title": "Rights of Persons with Disabilities Act 2016", "anchor": "rpwd-2016/sec-21"},
        {"index": 3, "title": "Rights of Persons with Disabilities Act 2016", "anchor": "rpwd-2016/sec-58"},
    ]

    joined = " ".join(_grounded_template_lines(q, route_matter(q), passages)).lower()

    assert "60 percent disability" in joined
    assert "employment-discrimination" in joined or "employment discrimination" in joined
    assert "reasonable-accommodation" in joined or "reasonable accommodation" in joined
    assert "termination" in joined
    assert "state commissioner" in joined


def test_stage_goal_exact_failures_get_deterministic_answer_owners():
    from apps.api.main import _grounded_template_lines
    from apps.api.matter_router import route_matter

    capital_gains = "i am confused capital gains on sale of flat held for 2.5 years tax implication and 54F exemption pls guide"
    capital_lines = _grounded_template_lines(capital_gains, route_matter(capital_gains), [
        {"index": 1, "title": "Income-tax Act 1961", "anchor": "income-tax-1961/sec-45"},
        {"index": 2, "title": "Income-tax Act 1961", "anchor": "income-tax-1961/sec-54F"},
    ])
    capital = " ".join(capital_lines)
    assert "Income-tax Act capital-gains" in capital
    assert "Section 54F" in capital
    assert "income-tax return" in capital

    forced_marriage = "please help I am gay and my parents are forcing me to marry a girl next month they are not listening I am 26 what is my right any remedy"
    forced_lines = _grounded_template_lines(forced_marriage, route_matter(forced_marriage), [
        {"index": 1, "title": "Constitution of India", "anchor": "constitution-india/sec-21"},
        {"index": 2, "title": "Protection of Women from Domestic Violence Act 2005", "anchor": "pwdva-2005/sec-18"},
    ])
    forced = " ".join(forced_lines)
    assert "forcing you to marry a girl you do not consent to" in forced
    assert "sexual orientation" in forced
    assert "Protection Officer/Magistrate" in forced

    ibc_prepack = "hi, msme pre pack insolvency how to use against my own company 1.4 cr debt avoiding nclt full process can i file case"
    ibc_lines = _grounded_template_lines(ibc_prepack, route_matter(ibc_prepack), [
        {"index": 1, "title": "Insolvency and Bankruptcy Code 2016", "anchor": "ibc-2016/sec-54A"},
        {"index": 2, "title": "Companies Act 2013", "anchor": "companies-2013/sec-92"},
    ])
    ibc = " ".join(ibc_lines)
    assert "pre-packaged insolvency" in ibc
    assert "pre-pack recovery and restructuring file" in ibc
    assert "MCA/ROC annual-filing default" not in ibc
    assert "Section 9/NCLT form" not in ibc

    builder = "i am confused i bought a flat in 2019, builder still hasnt registered sale deed because of pending property tax dues from his side pls guide"
    builder_lines = _grounded_template_lines(builder, route_matter(builder), [
        {"index": 1, "title": "Real Estate (Regulation and Development) Act 2016", "anchor": "rera-2016/sec-31"},
        {"index": 2, "title": "Consumer Protection Act 2019", "anchor": "consumer-protection-2019/sec-35"},
        {"index": 3, "title": "Registration Act 1908", "anchor": "registration-1908/sec-17"},
    ])
    builder_answer = " ".join(builder_lines)
    assert "sale-deed registration" in builder_answer
    assert "Registration Act source" in builder_answer
    assert "sub-registrar" in builder_answer

    st_certificate = "can u tell ST certificate not issued by tehsildar 8 months daughter exam form rejected jharkhand what can i do"
    st_lines = _grounded_template_lines(st_certificate, route_matter(st_certificate), [
        {"index": 1, "title": "Constitution of India", "anchor": "constitution-india/sec-342"},
        {"index": 2, "title": "Right to Information Act 2005", "anchor": "right-to-information-act-2005/sec-19"},
    ])
    st_answer = " ".join(st_lines)
    assert "reserved education" in st_answer
    assert "exam" in st_answer

    land = "sir my land taken for highway 4 years back compensation still not received who to ask where to go"
    land_lines = _grounded_template_lines(land, route_matter(land), [
        {"index": 1, "title": "Right to Fair Compensation and Transparency in Land Acquisition, Rehabilitation and Resettlement Act 2013", "anchor": "rfctlarr-2013/sec-64"},
        {"index": 2, "title": "Right to Fair Compensation and Transparency in Land Acquisition, Rehabilitation and Resettlement Act 2013", "anchor": "rfctlarr-2013/sec-77"},
    ])
    land_answer = " ".join(land_lines)
    assert "title/record-of-rights" in land_answer
    assert "civil court" in land_answer


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


def test_answer_contract_prioritizes_route_required_source_over_generic_judgment_support():
    from apps.api.main import _answer_contract_lines
    from apps.api.matter_router import route_matter

    route = route_matter("bank deducted money wrongly and customer care not helping")
    passages = [
        {
            "index": 1,
            "title": "CCI CHAMBERS CO-OP. HSG. SOCIETY LTD. versus DEVELOPMENT CREDIT BANK LTD.",
            "anchor": "2003-insc-1#para-4",
            "source_type": "sc_judgment",
        },
        {
            "index": 2,
            "title": "Consumer Protection Act 2019",
            "statute_short": "Consumer Protection Act 2019",
            "anchor": "consumer-protection-2019/sec-35",
            "source_type": "bare_act",
            "required_source_pack": "consumer_protection_2019",
            "text": "A consumer may file a complaint before the District Commission.",
        },
        {
            "index": 3,
            "title": "Reserve Bank Integrated Ombudsman Scheme 2021",
            "statute_short": "Reserve Bank Integrated Ombudsman Scheme 2021",
            "anchor": "rbi-integrated-ombudsman-2021/sec-2",
            "source_type": "bare_act",
            "required_source_pack": "rbi_integrated_ombudsman_2021",
            "text": "The scheme covers complaints against regulated entities.",
        },
    ]
    state = {
        "emitted_citation_indices": {1, 2},
        "seen_sentences": set(),
        "saw_next_step_sentence": True,
        "saw_next_step_header": True,
        "emitted": 3,
    }

    lines = _answer_contract_lines(route, passages, state, query="bank deducted money wrongly and customer care not helping")

    assert lines
    assert "Reserve Bank Integrated Ombudsman Scheme 2021" in lines[0]
    assert "[3]" in lines[0]


def test_answer_contract_cites_all_retrieved_required_route_sources_even_when_secondary():
    from apps.api.main import _answer_contract_lines
    from apps.api.matter_router import route_matter

    route = route_matter("bank deducted money wrongly and customer care not helping")
    passages = [
        {
            "index": 1,
            "title": "Reserve Bank Integrated Ombudsman Scheme 2021",
            "statute_short": "Reserve Bank Integrated Ombudsman Scheme 2021",
            "anchor": "rbi-integrated-ombudsman-2021/sec-2",
            "source_type": "bare_act",
            "required_source_pack": "rbi_integrated_ombudsman_2021",
            "text": "The scheme covers complaints against regulated entities.",
        },
        {
            "index": 2,
            "title": "Consumer Protection Act 2019",
            "statute_short": "Consumer Protection Act 2019",
            "anchor": "consumer-protection-2019/sec-35",
            "source_type": "bare_act",
            "required_source_pack": "consumer_protection_2019",
            "text": "A consumer may file a complaint before the District Commission.",
        },
    ]
    state = {
        "emitted_citation_indices": {1},
        "seen_sentences": set(),
        "saw_next_step_sentence": True,
        "saw_next_step_header": True,
        "emitted": 3,
    }

    lines = _answer_contract_lines(
        route,
        passages,
        state,
        query="bank deducted money wrongly and customer care not helping",
    )

    assert any("Consumer Protection Act 2019" in line and "Section 35" in line and "[2]" in line for line in lines)


def test_answer_contract_cites_required_source_same_act_different_article():
    from apps.api.main import _answer_contract_lines
    from apps.api.matter_router import route_matter

    query = (
        "what to do delhi labour chowk police picking us morning saying "
        "nautanki begging not work how to stop is this legal"
    )
    route = route_matter(query)
    passages = [
        {
            "index": 1,
            "title": "Constitution of India",
            "statute_short": "Constitution of India",
            "anchor": "constitution-india/sec-21",
            "source_type": "bare_act",
            "required_source_pack": "constitution_india",
            "text": "No person shall be deprived of life or personal liberty except according to procedure established by law.",
        },
        {
            "index": 2,
            "title": "Constitution of India",
            "statute_short": "Constitution of India",
            "anchor": "constitution-india/sec-22",
            "source_type": "bare_act",
            "required_source_pack": "constitution_india",
            "text": "No person who is arrested shall be detained without being informed of the grounds for arrest.",
        },
        {
            "index": 3,
            "title": "Bharatiya Nagarik Suraksha Sanhita 2023",
            "statute_short": "BNSS 2023",
            "anchor": "bnss-2023/sec-57",
            "source_type": "bare_act",
            "required_source_pack": "bnss_2023",
            "text": "Arrest and detention safeguards apply after arrest.",
        },
    ]
    state = {
        "emitted_citation_indices": {2},
        "seen_sentences": set(),
        "saw_next_step_sentence": True,
        "saw_next_step_header": True,
        "emitted": 3,
    }

    lines = _answer_contract_lines(route, passages, state, query=query)
    joined = " ".join(lines)

    assert "Constitution of India, Article 21 [1]" in joined


def test_answer_contract_source_floor_only_adds_missing_route_authority():
    from apps.api.main import _answer_contract_lines
    from apps.api.matter_router import route_matter

    query = "bank deducted money wrongly and customer care not helping"
    route = route_matter(query)
    passages = [
        {
            "index": 1,
            "title": "Reserve Bank Integrated Ombudsman Scheme 2021",
            "statute_short": "Reserve Bank Integrated Ombudsman Scheme 2021",
            "anchor": "rbi-integrated-ombudsman-2021/sec-3",
            "source_type": "bare_act",
            "required_source_pack": "rbi_integrated_ombudsman_2021",
            "text": "The Reserve Bank may appoint Ombudsmen.",
        },
        {
            "index": 2,
            "title": "Reserve Bank Integrated Ombudsman Scheme 2021",
            "statute_short": "Reserve Bank Integrated Ombudsman Scheme 2021",
            "anchor": "rbi-integrated-ombudsman-2021/sec-2",
            "source_type": "bare_act",
            "required_source_pack": "rbi_integrated_ombudsman_2021",
            "text": "The scheme defines covered regulated entities and complaint scope.",
        },
        {
            "index": 3,
            "title": "Consumer Protection Act 2019",
            "statute_short": "Consumer Protection Act 2019",
            "anchor": "consumer-protection-2019/sec-35",
            "source_type": "bare_act",
            "required_source_pack": "consumer_protection_2019",
            "text": "A consumer may file a complaint before the District Commission.",
        },
    ]
    state = {
        "emitted_citation_indices": {1},
        "seen_sentences": set(),
        "saw_next_step_sentence": True,
        "saw_next_step_header": True,
        "emitted": 3,
    }

    lines = _answer_contract_lines(
        route,
        passages,
        state,
        query=query,
        source_floor_only=True,
    )
    joined = " ".join(lines)

    assert "Reserve Bank Integrated Ombudsman Scheme 2021, Section 2 [2]" in joined
    assert "Consumer Protection Act 2019, Section 35 [3]" in joined
    assert "**What you can do next**" not in joined


def test_registry_answer_coverage_gate_detects_only_visible_citation_omissions():
    from apps.api.legal_issue_plan import build_matter_plan
    from apps.api.main import _missing_registry_must_cite_authority_ids
    from apps.api.matter_router import route_matter

    query = "Loan app is blackmailing me with a morphed nude photo if I do not pay tonight"
    plan = build_matter_plan(query, route_matter(query))
    required_ids = [
        entry.authority_id
        for entry in plan.authority_ledger
        if entry.note == "registry_workflow_authority" and entry.must_cite
    ]
    passages = [
        {"index": index, "authority_ids": [authority_id]}
        for index, authority_id in enumerate(required_ids, start=1)
    ]

    assert len(required_ids) == 10
    assert _missing_registry_must_cite_authority_ids(
        plan,
        passages,
        set(range(1, 10)),
    ) == (required_ids[-1],)
    assert _missing_registry_must_cite_authority_ids(
        plan,
        passages,
        set(range(1, 11)),
    ) == ()
    # Retrieval/source-gap validation owns an incomplete authority window.
    assert _missing_registry_must_cite_authority_ids(
        plan,
        passages[:-1],
        set(range(1, 10)),
    ) == ()


def test_answer_contract_adds_inherited_property_succession_source_not_specific_relief_noise():
    from apps.api.main import _answer_contract_lines
    from apps.api.matter_router import route_matter

    query = "can i sell property if one legal heir is not agreeing"
    route = route_matter(query)
    passages = [
        {
            "index": 1,
            "title": "Transfer of Property Act 1882",
            "statute_short": "Transfer of Property Act 1882",
            "anchor": "transfer-of-property-1882/sec-44",
            "source_type": "bare_act",
            "required_source_pack": "transfer_property_1882",
            "text": "A co-owner may transfer his share subject to conditions.",
        },
        {
            "index": 2,
            "title": "Hindu Succession Act 1956",
            "statute_short": "Hindu Succession Act 1956",
            "anchor": "hindu-succession-1956/sec-8",
            "source_type": "bare_act",
            "required_source_pack": "hindu_succession_1956",
            "text": "The Act identifies legal heirs and shares.",
        },
        {
            "index": 3,
            "title": "Specific Relief Act 1963",
            "statute_short": "Specific Relief Act 1963",
            "anchor": "specific-relief-1963/sec-31",
            "source_type": "bare_act",
            "required_source_pack": "specific_relief_1963",
            "text": "Cancellation may be ordered for certain instruments.",
        },
    ]
    state = {
        "emitted_citation_indices": {1},
        "seen_sentences": set(),
        "saw_next_step_sentence": True,
        "saw_next_step_header": True,
        "server_template_used": True,
        "emitted": 3,
    }

    lines = _answer_contract_lines(route, passages, state, query=query)

    assert any("Hindu Succession Act 1956" in line and "[2]" in line for line in lines)
    assert not any("Specific Relief Act" in line or "[3]" in line for line in lines)


def test_answer_contract_does_not_add_sale_of_goods_when_quality_dispute_negated():
    from apps.api.main import _answer_contract_lines
    from apps.api.matter_router import route_matter

    query = "supplier not paid invoice 9 lakh no quality issue"
    route = route_matter(query)
    passages = [
        {
            "index": 1,
            "title": "Micro, Small and Medium Enterprises Development Act 2006",
            "statute_short": "MSMED Act 2006",
            "anchor": "msmed-2006/sec-15",
            "source_type": "bare_act",
            "required_source_pack": "msmed_2006",
        },
        {
            "index": 2,
            "title": "Indian Contract Act 1872",
            "statute_short": "Indian Contract Act 1872",
            "anchor": "indian-contract-1872/sec-73",
            "source_type": "bare_act",
            "required_source_pack": "indian_contract_1872",
        },
        {
            "index": 3,
            "title": "Sale of Goods Act 1930",
            "statute_short": "Sale of Goods Act 1930",
            "anchor": "sale-of-goods-1930/sec-42",
            "source_type": "bare_act",
            "required_source_pack": "sale_of_goods_1930",
        },
    ]
    state = {
        "emitted_citation_indices": {1, 2},
        "seen_sentences": set(),
        "saw_next_step_sentence": True,
        "saw_next_step_header": True,
        "server_template_used": True,
        "emitted": 3,
    }

    lines = _answer_contract_lines(route, passages, state, query=query)

    assert not any("Sale of Goods Act" in line or "[3]" in line for line in lines)


def test_answer_contract_expands_composite_criminal_requirement_to_bns_and_bnss_sources():
    from apps.api.main import _answer_contract_lines
    from apps.api.matter_router import route_matter

    query = "someone made deepfake video of me on instagram and blackmailing me"
    route = route_matter(query)
    passages = [
        {
            "index": 1,
            "title": "Information Technology Act 2000",
            "statute_short": "Information Technology Act 2000",
            "anchor": "it-2000/sec-66e",
            "source_type": "bare_act",
            "required_source_pack": "it_act_2000",
        },
        {
            "index": 2,
            "title": "Bharatiya Nyaya Sanhita 2023",
            "statute_short": "BNS 2023",
            "anchor": "bns-2023/sec-308",
            "source_type": "bare_act",
            "required_source_pack": "bns_2023",
        },
        {
            "index": 3,
            "title": "Bharatiya Nagarik Suraksha Sanhita 2023",
            "statute_short": "BNSS 2023",
            "anchor": "bnss-2023/sec-173",
            "source_type": "bare_act",
            "required_source_pack": "bnss_2023",
        },
        {
            "index": 4,
            "title": "Indian Penal Code 1860",
            "statute_short": "IPC 1860",
            "anchor": "ipc-1860/sec-384",
            "source_type": "bare_act",
            "required_source_pack": "ipc_1860",
        },
        {
            "index": 5,
            "title": "Code of Criminal Procedure 1973",
            "statute_short": "CrPC 1973",
            "anchor": "crpc-1973/sec-154",
            "source_type": "bare_act",
            "required_source_pack": "crpc_1973",
        },
    ]
    state = {
        "emitted_citation_indices": {1},
        "seen_sentences": set(),
        "saw_next_step_sentence": True,
        "saw_next_step_header": True,
        "emitted": 3,
    }

    lines = _answer_contract_lines(route, passages, state, query=query)
    joined = " ".join(lines)

    assert "Bharatiya Nyaya Sanhita 2023" in joined and "[2]" in joined
    assert "Bharatiya Nagarik Suraksha Sanhita 2023" in joined and "[3]" in joined
    assert "Indian Penal Code" not in joined
    assert "Code of Criminal Procedure" not in joined


def test_answer_contract_expands_old_regime_composite_from_source_gap_match():
    from apps.api.main import _answer_contract_lines
    from apps.api.matter_router import route_matter

    query = "someone made deepfake video of me on instagram in June 2024 and is extorting me"
    route = route_matter(query)
    passages = [
        {
            "index": 1,
            "title": "Information Technology Act 2000",
            "statute_short": "Information Technology Act 2000",
            "anchor": "it-2000/sec-66e",
            "source_type": "bare_act",
            "required_source_pack": "it_act_2000",
        },
        {
            "index": 2,
            "title": "Bharatiya Nyaya Sanhita 2023",
            "statute_short": "BNS 2023",
            "anchor": "bns-2023/sec-308",
            "source_type": "bare_act",
            "required_source_pack": "bns_2023",
        },
        {
            "index": 3,
            "title": "Bharatiya Nagarik Suraksha Sanhita 2023",
            "statute_short": "BNSS 2023",
            "anchor": "bnss-2023/sec-173",
            "source_type": "bare_act",
            "required_source_pack": "bnss_2023",
        },
        {
            "index": 4,
            "title": "Indian Penal Code 1860",
            "statute_short": "IPC 1860",
            "anchor": "ipc-1860/sec-384",
            "source_type": "bare_act",
            "required_source_pack": "ipc_1860",
        },
        {
            "index": 5,
            "title": "Code of Criminal Procedure 1973",
            "statute_short": "CrPC 1973",
            "anchor": "crpc-1973/sec-154",
            "source_type": "bare_act",
            "required_source_pack": "crpc_1973",
        },
    ]
    state = {
        "emitted_citation_indices": {1},
        "seen_sentences": set(),
        "saw_next_step_sentence": True,
        "saw_next_step_header": True,
        "emitted": 3,
    }

    lines = _answer_contract_lines(route, passages, state, query=query)
    joined = " ".join(lines)

    assert "Indian Penal Code 1860" in joined and "[4]" in joined
    assert "Code of Criminal Procedure 1973" in joined and "[5]" in joined
    assert "Bharatiya Nyaya Sanhita" not in joined
    assert "Bharatiya Nagarik Suraksha" not in joined


def test_answer_contract_composite_expansion_uses_aggregate_anchor_not_first_statute():
    from apps.api.main import _answer_contract_lines
    from apps.api.matter_router import route_matter

    query = "someone made deepfake video of me on instagram in 2025 and is extorting me"
    route = route_matter(query)
    passages = [
        {
            "index": 1,
            "title": "Information Technology Act 2000",
            "statute_short": "Information Technology Act 2000",
            "anchor": "it-2000/sec-66e",
            "source_type": "bare_act",
            "required_source_pack": "it_act_2000",
        },
        {
            "index": 2,
            "title": "Bharatiya Nyaya Sanhita 2023",
            "statute_short": "BNS 2023",
            "anchor": "bns-2023/sec-115",
            "source_type": "bare_act",
            "required_source_pack": "bns_2023_hurt",
        },
        {
            "index": 3,
            "title": "Bharatiya Nyaya Sanhita 2023",
            "statute_short": "BNS 2023",
            "anchor": "bns-2023/sec-308",
            "source_type": "bare_act",
            "required_source_pack": "bns_2023_extortion",
        },
        {
            "index": 4,
            "title": "Bharatiya Nagarik Suraksha Sanhita 2023",
            "statute_short": "BNSS 2023",
            "anchor": "bnss-2023/sec-173",
            "source_type": "bare_act",
            "required_source_pack": "bnss_2023",
        },
    ]
    state = {
        "emitted_citation_indices": {1},
        "seen_sentences": set(),
        "saw_next_step_sentence": True,
        "saw_next_step_header": True,
        "emitted": 3,
    }

    lines = _answer_contract_lines(route, passages, state, query=query)
    joined = " ".join(lines)

    assert "bns-2023/sec-115" not in joined
    assert "[2]" not in joined
    assert "Bharatiya Nyaya Sanhita 2023" in joined and "[3]" in joined
    assert "Bharatiya Nagarik Suraksha Sanhita 2023" in joined and "[4]" in joined


def test_answer_contract_plan_must_cite_overrides_generic_source_budget():
    from apps.api.legal_issue_plan import build_matter_plan
    from apps.api.main import _answer_contract_lines
    from apps.api.matter_router import route_matter

    q = "online order arrived broken what to do"
    route = route_matter(q)
    plan = build_matter_plan(q, route)
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
    from apps.api.legal_issue_plan import build_matter_plan
    from apps.api.main import _answer_contract_lines
    from apps.api.matter_router import route_matter

    q = "land acquired for coal block without consulting palli sabha angul odisha what can i do"
    route = route_matter(q)
    plan = build_matter_plan(q, route)
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
    from apps.api.legal_issue_plan import build_matter_plan
    from apps.api.main import _answer_contract_lines
    from apps.api.matter_router import route_matter

    q = "bank sent me sarfaesi notice under 13(2) what to do"
    route = route_matter(q)
    plan = build_matter_plan(q, route)
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


def test_answer_contract_plan_must_cite_matches_aadhaar_full_title():
    from apps.api.legal_issue_plan import build_matter_plan
    from apps.api.main import _answer_contract_lines
    from apps.api.matter_router import route_matter

    q = "aadhaar number showing someone else photo cannot get pension help"
    route = route_matter(q)
    plan = build_matter_plan(q, route)
    passages = [
        {
            "index": 2,
            "title": "National Social Assistance Programme Guidelines 2014",
            "statute_short": "National Social Assistance Programme Guidelines 2014",
            "anchor": "nsap-guidelines-2014#header",
            "source_type": "bare_act",
            "text": "Grievance redressal and pension scheme administration guidance.",
        },
        {
            "index": 3,
            "title": "Right to Information Act 2005",
            "statute_short": "Right to Information Act 2005",
            "anchor": "rti-2005/sec-19-b@2025-11-18",
            "source_type": "bare_act",
            "text": "Appeals may lie where information or reasons are denied.",
        },
        {
            "index": 4,
            "title": "Aadhaar (Targeted Delivery of Financial and Other Subsidies, Benefits and Services) Act 2016",
            "statute_short": "Aadhaar (Targeted Delivery of Financial and Other Subsidies, Benefits and Services) Act 2016",
            "anchor": "aadhaar-2016/sec-59",
            "source_type": "bare_act",
            "text": "Aadhaar number usage for benefits and services is governed by this Act.",
        },
    ]
    state = {
        "emitted_citation_indices": {2, 3},
        "seen_sentences": set(),
        "saw_next_step_sentence": True,
        "saw_next_step_header": True,
        "emitted": 3,
    }

    lines = _answer_contract_lines(route, passages, state, plan, query=q)

    assert any("Aadhaar" in line and "Section 59" in line and "[4]" in line for line in lines)
    assert any("pension block" in line and "[4][2]" in line for line in lines)


def test_answer_contract_aadhaar_pension_floor_does_not_hallucinate_photo():
    from apps.api.legal_issue_plan import build_matter_plan
    from apps.api.main import _answer_contract_lines
    from apps.api.matter_router import route_matter

    q = "old age pension stopped suddenly bank says aadhaar not linked"
    route = route_matter(q)
    plan = build_matter_plan(q, route)
    passages = [
        {
            "index": 2,
            "title": "National Social Assistance Programme Guidelines 2014",
            "statute_short": "National Social Assistance Programme Guidelines 2014",
            "anchor": "nsap-guidelines-2014#header",
            "source_type": "bare_act",
            "text": "Grievance redressal and pension scheme administration guidance.",
        },
        {
            "index": 4,
            "title": "Aadhaar (Targeted Delivery of Financial and Other Subsidies, Benefits and Services) Act 2016",
            "statute_short": "Aadhaar (Targeted Delivery of Financial and Other Subsidies, Benefits and Services) Act 2016",
            "anchor": "aadhaar-2016/sec-7",
            "source_type": "bare_act",
            "text": "Aadhaar number usage for benefits and services is governed by this Act.",
        },
    ]
    state = {
        "emitted_citation_indices": {2},
        "seen_sentences": set(),
        "saw_next_step_sentence": True,
        "saw_next_step_header": True,
        "emitted": 3,
    }

    lines = _answer_contract_lines(route, passages, state, plan, query=q)
    pension_lines = [line for line in lines if "pension block" in line]

    assert any("Aadhaar-linking rejection" in line and "[4][2]" in line for line in pension_lines)
    assert not any("wrong-photo" in line for line in pension_lines)


def test_answer_contract_plan_floor_does_not_add_rfctlarr_to_minor_mineral_pesa():
    from apps.api.legal_issue_plan import build_matter_plan
    from apps.api.main import _answer_contract_lines
    from apps.api.matter_router import route_matter

    q = "sand mining lease given without gram sabha consent in scheduled area"
    route = route_matter(q)
    plan = build_matter_plan(q, route)
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
    from apps.api.legal_issue_plan import build_matter_plan
    from apps.api.main import _answer_contract_lines
    from apps.api.matter_router import route_matter

    q = "sand mining lease given without gram sabha consent in scheduled area"
    route = route_matter(q)
    plan = build_matter_plan(q, route)
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

    payout_q = "ola driver account deactivated after customer complaint and payout held what legal option"
    payout_joined = " ".join(_grounded_template_lines(payout_q, route_matter(payout_q), [
        {"index": 5, "title": "Motor Vehicle Aggregator Guidelines 2020", "anchor": "motor-vehicle-aggregator-guidelines-2020#driver-service-contract"},
        {"index": 6, "title": "Motor Vehicle Aggregator Guidelines 2020", "anchor": "motor-vehicle-aggregator-guidelines-2020#app-transparency-grievance"},
        {"index": 8, "title": "Consumer Protection Act 2019", "anchor": "consumer-protection-2019/sec-35"},
    ]))
    assert "driver is automatically a consumer" in payout_joined
    assert "Consumer Protection Act" in payout_joined and "[8]" in payout_joined


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

    swiggy_q = "swiggy pe customer abused me 1 star spam now my id blocked appeal kaha"
    swiggy_passages = [
        {"index": 4, "title": "Code on Social Security 2020", "anchor": "social-security-code-2020/sec-113"},
        {"index": 5, "title": "Code on Wages 2019", "anchor": "code-on-wages-2019/sec-17"},
    ]
    swiggy = " ".join(_grounded_template_lines(swiggy_q, route_matter(swiggy_q), swiggy_passages))
    assert "Swiggy worker ID block" in swiggy
    assert "customer-abuse" in swiggy
    assert "earned payout or wages unpaid" in swiggy
    assert "[4]" in swiggy and "[5]" in swiggy
    assert "automatically a consumer" not in swiggy

    local_contractor_q = "contractor at local shop has not paid two months salary but I am from same city what law applies"
    local_contractor_passages = [
        {"index": 2, "title": "Code on Wages 2019", "anchor": "code-on-wages-2019/sec-17"},
        {"index": 3, "title": "Contract Labour (Regulation and Abolition) Act 1970", "anchor": "contract-labour-1970/sec-21"},
        {"index": 9, "title": "Inter-State Migrant Workmen (Regulation of Employment and Conditions of Service) Act 1979", "anchor": "ismw-1979/sec-12"},
    ]
    local_contractor = " ".join(_grounded_template_lines(local_contractor_q, route_matter(local_contractor_q), local_contractor_passages))
    assert "earned-wages claim first" in local_contractor
    assert "Contract Labour Act source only as a conditional check" in local_contractor
    assert "same-city work" in local_contractor
    assert "[2]" in local_contractor and "[3]" in local_contractor
    assert "ISMW" not in local_contractor

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


def test_grounded_template_for_freelance_cheque_bounce_cites_ni_and_bnss():
    from apps.api.main import _grounded_template_lines
    from apps.api.matter_router import route_matter

    q = "freelance writer 5 cheques bounced from one client total 1.4 lakh"
    passages = [
        {
            "index": 1,
            "title": "Negotiable Instruments Act 1881",
            "anchor": "negotiable-instruments-1881/sec-138",
            "text": (
                "Section 138 applies to a cheque drawn for discharge of any debt or other liability "
                "returned unpaid, with written demand notice within thirty days and fifteen days for payment."
            ),
        },
        {
            "index": 2,
            "title": "Negotiable Instruments Act 1881",
            "anchor": "negotiable-instruments-1881/sec-142",
            "text": "Section 142 provides for complaint filing within one month of cause of action before the court.",
        },
        {
            "index": 3,
            "title": "Bharatiya Nagarik Suraksha Sanhita 2023",
            "anchor": "bnss-2023/sec-223",
            "text": "A Magistrate taking cognizance of an offence on complaint shall examine the complainant and witnesses on oath.",
        },
    ]

    joined = " ".join(_grounded_template_lines(q, route_matter(q), passages))

    assert "freelance/client payment" in joined
    assert "multiple bounced cheques" in joined
    assert "thirty days" in joined
    assert "fifteen-day payment window" in joined
    assert "one-month complaint window" in joined
    assert "BNSS Magistrate complaint source" in joined
    assert "[1]" in joined and "[2]" in joined and "[3]" in joined


def test_temple_entry_bridge_only_promotes_caste_route():
    from apps.api.main import _is_safe_template_source_bridge
    from apps.api.matter_router import route_matter

    sent = (
        "If a Thakur family stopped Dalit persons from entering a temple, "
        "treat it as a temple-entry/untouchability complaint, not an ordinary "
        "village quarrel; record the caste identity, date, place, and names "
        "in the written police/DLSA complaint [20]."
    )

    assert _is_safe_template_source_bridge(
        sent,
        route_matter("thakur family stopped us from entering temple we are dalit"),
    )
    assert not _is_safe_template_source_bridge(
        sent,
        route_matter("temple trust cancelled my booking for wedding hall refund"),
    )


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


def test_hut_burning_fir_refusal_template_is_user_shaped():
    from apps.api.main import _grounded_template_lines
    from apps.api.matter_router import route_matter

    q = "can u tell thana refused to file complaint against zamindar who burnt our hut latehar what can i do"
    passages = [
        {"index": 1, "title": "Bharatiya Nagarik Suraksha Sanhita 2023", "anchor": "bnss-2023/sec-173-b"},
        {"index": 2, "title": "Bharatiya Nyaya Sanhita 2023", "anchor": "bns-2023/sec-326-a"},
        {"index": 3, "title": "Code of Criminal Procedure 1973", "anchor": "crpc-1973/sec-156"},
    ]

    joined = " ".join(_grounded_template_lines(q, route_matter(q), passages))

    assert "burnt or damaged the hut by fire" in joined
    assert "BNSS FIR/refusal source" in joined
    assert "burnt-hut/FIR-refusal file" in joined
    assert "[1]" in joined and "[2]" in joined and "[3]" in joined


def test_common_police_fir_and_pickup_templates_are_user_actionable():
    from apps.api.main import _grounded_template_lines
    from apps.api.matter_router import route_matter

    bike_q = "My bike is stolen, police is not filing FIR"
    bike_passages = [
        {"index": 1, "title": "Bharatiya Nyaya Sanhita 2023", "anchor": "bns-2023/sec-303"},
        {"index": 2, "title": "Bharatiya Nagarik Suraksha Sanhita 2023", "anchor": "bnss-2023/sec-173-a"},
        {"index": 3, "title": "Bharatiya Nagarik Suraksha Sanhita 2023", "anchor": "bnss-2023/sec-173-c"},
        {"index": 4, "title": "Code of Criminal Procedure 1973", "anchor": "crpc-1973/sec-154"},
    ]
    bike_joined = " ".join(_grounded_template_lines(bike_q, route_matter(bike_q), bike_passages))

    assert "pre-1-July-2024 incident" in bike_joined
    assert "incident on or after 1 July 2024" in bike_joined
    assert "written-post route to the Superintendent of Police" in bike_joined
    assert "written complaint, acknowledgement, and any refusal" in bike_joined
    assert "[2]" in bike_joined and "[4]" in bike_joined

    pickup_q = "police has picked my son from my home in the night, i have not got FIR copy"
    pickup_passages = [
        {"index": 1, "title": "Constitution of India", "anchor": "constitution-india/sec-22"},
        {"index": 2, "title": "Bharatiya Nagarik Suraksha Sanhita 2023", "anchor": "bnss-2023/sec-47"},
        {"index": 3, "title": "Bharatiya Nagarik Suraksha Sanhita 2023", "anchor": "bnss-2023/sec-58"},
        {"index": 4, "title": "Bharatiya Nagarik Suraksha Sanhita 2023", "anchor": "bnss-2023/sec-173"},
    ]
    pickup_joined = " ".join(_grounded_template_lines(pickup_q, route_matter(pickup_q), pickup_passages))

    assert "arrest-information and liberty safeguard" in pickup_joined
    assert "grounds of arrest" in pickup_joined
    assert "arrest memo" in pickup_joined
    assert "nearest Magistrate within twenty-four hours" in pickup_joined
    assert "pickup time and place" in pickup_joined
    assert "station remains unknown" in pickup_joined
    assert "[1]" in pickup_joined and "[2]" in pickup_joined


def test_hut_burning_bridge_survives_tribal_route():
    from apps.api.main import _is_safe_template_source_bridge
    from apps.api.matter_router import route_matter

    q = "adivasi house burned by land grabber thana refusing complaint"
    route = route_matter(q)
    sent = (
        "Build a burnt-hut/FIR-refusal file with photos, videos, witness names, "
        "property papers if any, medical records if anyone was hurt, and the written "
        "complaint/refusal proof."
    )

    assert route.category == "tribal_caste_atrocity"
    assert _is_safe_template_source_bridge(sent, route)


def test_itpa_receptionist_raid_template_keeps_accused_role_clear():
    from apps.api.main import _grounded_template_lines
    from apps.api.matter_router import route_matter

    q = "please help I was arrested in raid at parlour they said pita act but I was only working as receptionist not doing anything else any remedy"
    passages = [
        {"index": 1, "title": "Immoral Traffic (Prevention) Act 1956", "anchor": "itpa-1956/sec-5"},
        {"index": 2, "title": "Immoral Traffic (Prevention) Act 1956", "anchor": "itpa-1956/sec-8"},
        {"index": 3, "title": "Bharatiya Nagarik Suraksha Sanhita 2023", "anchor": "bnss-2023/sec-483"},
        {"index": 4, "title": "Bharatiya Nagarik Suraksha Sanhita 2023", "anchor": "bnss-2023/sec-216"},
    ]

    joined = " ".join(_grounded_template_lines(q, route_matter(q), passages))

    assert "only a receptionist or employee" in joined
    assert "do not accept a generic ITPA label" in joined
    assert "reception-desk work" in joined
    assert "do not admit involvement beyond facts" in joined
    assert "[1]" in joined and "[3]" in joined


def test_insurance_claim_template_uses_consumer_and_ombudsman_routes():
    from apps.api.main import _grounded_template_lines
    from apps.api.matter_router import route_matter

    q = "my hut caught fire by accident and insurance company is not paying claim what to do"
    passages = [
        {"index": 1, "title": "Insurance Ombudsman Rules 2017", "anchor": "insurance-ombudsman-rules-2017/sec-13"},
        {"index": 2, "title": "Consumer Protection Act 2019", "anchor": "consumer-protection-2019/sec-2"},
        {"index": 3, "title": "Consumer Protection Act 2019", "anchor": "consumer-protection-2019/sec-35"},
        {"index": 4, "title": "Consumer Protection Act 2019", "anchor": "consumer-protection-2019/sec-39"},
    ]

    joined = " ".join(_grounded_template_lines(q, route_matter(q), passages))

    assert "accidental fire-loss claim" in joined
    assert "Insurance Ombudsman source" in joined
    assert "Consumer Protection Act Section 35" in joined
    assert "policy schedule" in joined
    assert "[1]" in joined and "[3]" in joined


def test_state_specific_filter_drops_wrong_state_witch_act():
    from apps.api.main import _filter_state_specific_source_mismatches
    from apps.api.retrieval import RetrievedChunk

    assam = RetrievedChunk(
        chunk_id=1,
        document_id=1,
        anchor="assam-witch-hunting-2015/full",
        text="Assam Witch Hunting Act text",
        source_type="bare_act",
        subject_area="criminal",
        as_at=None,
        paragraph_no=None,
        title="Assam Witch Hunting (Prohibition, Prevention and Protection) Act 2015",
        citation=None,
        court=None,
        statute_short=None,
    )
    chhattisgarh = RetrievedChunk(
        chunk_id=5,
        document_id=5,
        anchor="chhattisgarh-tonahi-pratadna-nivaran-2005/sec-4",
        text="Chhattisgarh Tonahi Act identifying Tonahi text",
        source_type="bare_act",
        subject_area="criminal",
        as_at=None,
        paragraph_no=None,
        title="Chhattisgarh Tonahi Pratadna Nivaran Act 2005",
        citation=None,
        court=None,
        statute_short=None,
    )
    bns = RetrievedChunk(
        chunk_id=2,
        document_id=2,
        anchor="bns-2023/sec-76",
        text="BNS disrobing and assault text",
        source_type="bare_act",
        subject_area="criminal",
        as_at=None,
        paragraph_no=None,
        title="Bharatiya Nyaya Sanhita 2023",
        citation=None,
        court=None,
        statute_short=None,
    )

    filtered = _filter_state_specific_source_mismatches(
        "village ojha branded my mother daayan stripped her in public ranchi area",
        [assam, bns],
    )

    assert filtered == [bns]
    assert _filter_state_specific_source_mismatches(
        "assam village ojha branded my mother daayan",
        [assam, bns],
    ) == [assam, bns]
    assert _filter_state_specific_source_mismatches(
        "village ojha branded my mother daayan stripped her in public ranchi area",
        [chhattisgarh, bns],
    ) == [bns]
    assert _filter_state_specific_source_mismatches(
        "durgapur people say i am tonhi after child died false case what can i do",
        [chhattisgarh, bns],
    ) == [bns]
    assert _filter_state_specific_source_mismatches(
        "bastar art page called my painting witch craft and copied it",
        [chhattisgarh, bns],
    ) == [bns]
    assert _filter_state_specific_source_mismatches(
        "they say i am tonhi after child died in village false case filed chhattisgarh",
        [chhattisgarh, bns],
    ) == [chhattisgarh, bns]
    assert _filter_state_specific_source_mismatches(
        "durg district villagers say i am tonhi after child died false case what can i do",
        [chhattisgarh, bns],
    ) == [chhattisgarh, bns]
    assert _filter_state_specific_source_mismatches(
        "they say i am tonhi after child died in village false case filed chattisgarh",
        [chhattisgarh, bns],
    ) == [chhattisgarh, bns]

    gujarat_shops = RetrievedChunk(
        chunk_id=3,
        document_id=3,
        anchor="gujarat-shops-establishments-2019/sec-8",
        text="Gujarat Shops registration cancellation text",
        source_type="bare_act",
        subject_area="business_license",
        as_at=None,
        paragraph_no=None,
        title="Gujarat Shops and Establishments Act 2019",
        citation=None,
        court=None,
        statute_short=None,
    )
    gujarat_municipal = RetrievedChunk(
        chunk_id=4,
        document_id=4,
        anchor="gujarat-municipalities-1963/sec-221",
        text="Gujarat Municipalities licence closure text",
        source_type="bare_act",
        subject_area="business_license",
        as_at=None,
        paragraph_no=None,
        title="Gujarat Municipalities Act 1963",
        citation=None,
        court=None,
        statute_short=None,
    )

    assert _filter_state_specific_source_mismatches(
        "my shop in delhi municipal corporation sealed it",
        [gujarat_shops, gujarat_municipal, bns],
    ) == [bns]
    assert _filter_state_specific_source_mismatches(
        "my shop is in Ahmedabad and municipality sealed it",
        [gujarat_shops, gujarat_municipal, bns],
    ) == [gujarat_shops, gujarat_municipal, bns]

    ap_transfer = RetrievedChunk(
        chunk_id=6,
        document_id=6,
        anchor="andhra-pradesh-scheduled-areas-land-transfer-regulation-1959/sec-3",
        text="AP Scheduled Areas Land Transfer Regulation text",
        source_type="regulation",
        subject_area="tribal_land",
        as_at=None,
        paragraph_no=None,
        title="Andhra Pradesh Scheduled Areas Land Transfer Regulation 1959",
        citation=None,
        court=None,
        statute_short=None,
    )
    odisha_transfer = RetrievedChunk(
        chunk_id=7,
        document_id=7,
        anchor="orissa-scheduled-areas-transfer-immovable-property-st-1956/sec-3",
        text="Orissa Scheduled Areas Transfer Regulation text",
        source_type="regulation",
        subject_area="tribal_land",
        as_at=None,
        paragraph_no=None,
        title="Orissa Scheduled Areas Transfer of Immovable Property (By Scheduled Tribes) Regulation 1956",
        citation=None,
        court=None,
        statute_short=None,
    )

    assert _filter_state_specific_source_mismatches(
        "tribal land mutation to non tribal buyer in chaibasa jharkhand",
        [ap_transfer, odisha_transfer, bns],
    ) == [bns]
    assert _filter_state_specific_source_mismatches(
        "tribal land mutation to non tribal buyer in nuapada odisha",
        [ap_transfer, odisha_transfer, bns],
    ) == [odisha_transfer, bns]
    assert _filter_state_specific_source_mismatches(
        "agency land transferred to non tribal buyer in andhra pradesh",
        [ap_transfer, odisha_transfer, bns],
    ) == [ap_transfer, bns]


def test_witch_branding_victim_template_does_not_use_wrong_state_act():
    from apps.api.main import _grounded_template_lines
    from apps.api.matter_router import route_matter

    q = "can u tell village ojha branded my mother daayan stripped her in public ranchi area what can i do"
    passages = [
        {"index": 1, "title": "Assam Witch Hunting (Prohibition, Prevention and Protection) Act 2015", "anchor": "assam-witch-hunting-2015/full"},
        {"index": 2, "title": "Bharatiya Nyaya Sanhita 2023", "anchor": "bns-2023/sec-76"},
        {"index": 3, "title": "Bharatiya Nagarik Suraksha Sanhita 2023", "anchor": "bnss-2023/sec-173"},
        {"index": 4, "title": "Bharatiya Nagarik Suraksha Sanhita 2023", "anchor": "bnss-2023/sec-175"},
    ]

    joined = " ".join(_grounded_template_lines(q, route_matter(q), passages))

    assert "Ranchi/Jharkhand" in joined
    assert "state-specific witch-branding law" in joined
    assert "Assam Witch Hunting Act source" not in joined
    assert "[2]" in joined and "[3]" in joined and "[4]" in joined


def test_witch_branding_victim_template_cites_poa_when_tribal_status_present():
    from apps.api.main import _grounded_template_lines
    from apps.api.matter_router import route_matter

    q = "tribal woman called witch and beaten in gumla police refused FIR"
    passages = [
        {"index": 1, "title": "Scheduled Castes and Scheduled Tribes (Prevention of Atrocities) Act 1989", "anchor": "sc-st-poa-1989/sec-3"},
        {"index": 2, "title": "Bharatiya Nyaya Sanhita 2023", "anchor": "bns-2023/sec-115"},
        {"index": 3, "title": "Bharatiya Nagarik Suraksha Sanhita 2023", "anchor": "bnss-2023/sec-173"},
        {"index": 4, "title": "Bharatiya Nagarik Suraksha Sanhita 2023", "anchor": "bnss-2023/sec-175"},
    ]

    joined = " ".join(_grounded_template_lines(q, route_matter(q), passages))

    assert "SC/ST POA source" in joined
    assert "[1]" in joined and "[2]" in joined and "[3]" in joined and "[4]" in joined


def test_witch_branding_victim_template_cites_chhattisgarh_tonahi_source():
    from apps.api.main import _grounded_template_lines
    from apps.api.matter_router import route_matter

    q = "raipur villagers called my aunt tonhi and threatened to beat her after child death"
    passages = [
        {
            "index": 1,
            "title": "Chhattisgarh Tonahi Pratadna Nivaran Act 2005",
            "anchor": "chhattisgarh-tonahi-pratadna-nivaran-2005/sec-5",
        },
        {"index": 2, "title": "Bharatiya Nagarik Suraksha Sanhita 2023", "anchor": "bnss-2023/sec-173"},
        {"index": 3, "title": "Bharatiya Nyaya Sanhita 2023", "anchor": "bns-2023/sec-115"},
        {"index": 4, "title": "Bharatiya Nagarik Suraksha Sanhita 2023", "anchor": "bnss-2023/sec-175"},
    ]

    joined = " ".join(_grounded_template_lines(q, route_matter(q), passages))

    assert "Chhattisgarh Tonahi Act source" in joined
    assert "I do not have the exact" not in joined
    assert "[1]" in joined and "[2]" in joined and "[3]" in joined and "[4]" in joined


def test_witch_accused_template_cites_bns_and_bnss():
    from apps.api.main import _grounded_template_lines
    from apps.api.matter_router import route_matter

    passages = [
        {"index": 1, "title": "Bharatiya Nagarik Suraksha Sanhita 2023", "anchor": "bnss-2023/sec-483"},
        {"index": 2, "title": "Bharatiya Nyaya Sanhita 2023", "anchor": "bns-2023/sec-76"},
    ]

    for q in (
        "false daayan complaint filed against me in raipur I am accused what should I do now",
        "chhattisgarh police filed tonhi case against me after village dispute what bail remedy",
    ):
        joined = " ".join(_grounded_template_lines(q, route_matter(q), passages))

        assert "accused" in joined.lower()
        assert "[1]" in joined and "[2]" in joined


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
    assert "criminal-intimidation" in joined and "[2]" in joined
    assert "written police complaint" in joined and "[3]" in joined


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

    assert "put you out of the matrimonial home" in residence_joined
    assert "PWDVA Section 19" in residence_joined and "[3]" in residence_joined
    assert "return safely" in residence_joined
    assert "Protection Officer" in residence_joined

    immediate_q = "my husband is beating me right now what should I do"
    immediate_joined = " ".join(_grounded_template_lines(immediate_q, route_matter(immediate_q), passages))

    assert "beating you right now" in immediate_joined
    assert "treat immediate safety first" in immediate_joined


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
    salary_freeze_joined = " ".join(_grounded_template_lines(
        "salary account blocked by bank saying police request no notice",
        route_matter("salary account blocked by bank saying police request no notice"),
        [
            {
                "index": 1,
                "title": "Reserve Bank Integrated Ombudsman Scheme 2021",
                "anchor": "rbi-integrated-ombudsman-2021/sec-2",
                "text": "The Scheme applies to Regulated Entities as defined in it.",
            },
            {
                "index": 2,
                "title": "Banking Regulation Act 1949",
                "anchor": "banking-regulation-1949/sec-35A",
                "text": "Reserve Bank directions to banking companies.",
            },
            {
                "index": 3,
                "title": "Bharatiya Nagarik Suraksha Sanhita 2023",
                "anchor": "bnss-2023/sec-106",
                "text": "Police officer may seize property suspected to have been stolen or found under circumstances creating suspicion.",
            },
        ],
    ))
    assert "salary account blocked" in salary_freeze_joined
    assert "police request" in salary_freeze_joined
    assert "no notice" in salary_freeze_joined
    assert "BNSS" in salary_freeze_joined
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
    assert "Loan app or recovery harassment" in loan_joined
    assert "contact-data abuse" in loan_joined
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
    assert "municipal authority" in municipal_joined
    assert "Commissioner/appellate authority" in municipal_joined
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

    fake_loan_passages = [
        {"index": 1, "title": "Information Technology Act 2000", "anchor": "it-2000/sec-66C"},
        {"index": 2, "title": "Credit Information Companies (Regulation) Act 2005", "anchor": "credit-information-companies-2005/sec-21"},
        {"index": 3, "title": "Reserve Bank Integrated Ombudsman Scheme 2021", "anchor": "rbi-integrated-ombudsman-2021/sec-2"},
    ]
    fake_loan_joined = " ".join(_grounded_template_lines("someone used my pan only and took loan in my name", route_matter("someone used my pan only and took loan in my name"), fake_loan_passages))
    assert "false loan" in fake_loan_joined
    assert "credit-report correction" in fake_loan_joined
    assert "RBI Ombudsman" in fake_loan_joined
    assert "[2]" in fake_loan_joined and "[3]" in fake_loan_joined

    fake_loan_police_passages = [
        {"index": 1, "title": "Credit Information Companies (Regulation) Act 2005", "anchor": "credit-information-companies-2005/sec-20"},
        {"index": 2, "title": "Reserve Bank Integrated Ombudsman Scheme 2021", "anchor": "rbi-integrated-ombudsman-2021/sec-2"},
        {"index": 3, "title": "Bharatiya Nagarik Suraksha Sanhita 2023", "anchor": "bnss-2023/sec-175"},
        {"index": 4, "title": "Bharatiya Nyaya Sanhita 2023", "anchor": "bns-2023/sec-336"},
        {"index": 5, "title": "Information Technology Act 2000", "anchor": "it-2000/sec-66C"},
    ]
    fake_loan_police_joined = " ".join(_grounded_template_lines(
        "someone used my pan only and took loan in my name what police complaint",
        route_matter("someone used my pan only and took loan in my name what police complaint"),
        fake_loan_police_passages,
    ))
    assert "police side" in fake_loan_police_joined
    assert "BNS" in fake_loan_police_joined and "[4]" in fake_loan_police_joined
    assert "BNSS" in fake_loan_police_joined and "[3]" in fake_loan_police_joined


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
    assert "Bharatiya Nyaya Sanhita" not in joined
    assert "criminal complaint" in joined


def test_spouse_household_expense_maintenance_template_cites_pwdva_hma_and_family_court():
    from apps.api.main import _grounded_template_lines, _prompt_retrieval_candidates
    from apps.api.matter_router import route_matter

    q = "my husband stopped paying household expenses after separation I am 38 can I ask maintenance"
    passages = [
        {
            "index": 1,
            "title": "Protection of Women from Domestic Violence Act 2005",
            "anchor": "domestic-violence-2005/sec-3@2005-09-13",
            "text": "Domestic violence includes economic abuse.",
        },
        {
            "index": 2,
            "title": "Protection of Women from Domestic Violence Act 2005",
            "anchor": "domestic-violence-2005/sec-20@2005-09-13",
            "text": "The Magistrate may direct monetary relief to meet expenses and losses suffered by the aggrieved person.",
        },
        {
            "index": 3,
            "title": "Family Courts Act 1984",
            "anchor": "family-courts-1984/sec-7@1984-09-14",
            "text": "A Family Court has jurisdiction over suits and proceedings for maintenance and matrimonial relief.",
        },
        {
            "index": 4,
            "title": "Hindu Marriage Act 1955",
            "anchor": "hindu-marriage-1955/sec-24@1955-05-18",
            "text": "The court may order maintenance pendente lite and expenses of proceedings.",
        },
        {
            "index": 5,
            "title": "Bharatiya Nagarik Suraksha Sanhita 2023",
            "anchor": "bnss-2023/sec-144@2024-07-01",
            "text": "A person with sufficient means may be ordered to maintain his wife, child, father or mother.",
        },
        {
            "index": 6,
            "title": "Code of Criminal Procedure 1973",
            "anchor": "crpc-1973/sec-125@1974-04-01",
            "text": "A person with sufficient means may be ordered to maintain his wife, legitimate or illegitimate minor child, father or mother.",
        },
    ]

    joined = " ".join(_grounded_template_lines(q, route_matter(q), passages))

    assert "Family Courts Act source" in joined and "[3]" in joined
    assert "HMA source" in joined and "[4]" in joined
    assert "PWDVA economic-abuse/monetary-relief route" in joined and "[2]" in joined
    assert "maintenance-procedure source" in joined and "[5]" in joined
    assert "legacy CrPC maintenance source" in joined and "[6]" in joined
    assert "Separation by itself does not automatically end maintenance options" in joined
    assert "not an automatic property-ownership claim" in joined
    assert "criminal complaint" in joined
    assert "Bharatiya Nyaya Sanhita" not in joined

    route = route_matter(q)
    filtered = _prompt_retrieval_candidates(q, route, [
        SimpleNamespace(title="RINKU BAHETI versus SANDESH SHARDA", anchor="sc_judgment/para-14"),
        SimpleNamespace(title="Family Courts Act 1984", anchor="family-courts-1984/sec-7"),
        SimpleNamespace(title="Hindu Marriage Act 1955", anchor="hindu-marriage-1955/sec-24"),
        SimpleNamespace(title="Protection of Women from Domestic Violence Act 2005", anchor="domestic-violence-2005/sec-20"),
        SimpleNamespace(title="Bharatiya Nagarik Suraksha Sanhita 2023", anchor="bnss-2023/sec-144"),
        SimpleNamespace(title="Code of Criminal Procedure 1973", anchor="crpc-1973/sec-125"),
    ])
    assert [hit.title for hit in filtered] == [
        "Family Courts Act 1984",
        "Hindu Marriage Act 1955",
        "Protection of Women from Domestic Violence Act 2005",
        "Bharatiya Nagarik Suraksha Sanhita 2023",
        "Code of Criminal Procedure 1973",
    ]


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

    q = "bank not giving education loan to my daughter and admission deadline is tomorrow"
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
    assert "admission, fee-payment, or scholarship deadline is near" in joined
    assert "written refusal/reason and complaint number" in joined


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

    honour_full_lines = _grounded_template_lines(
        "my daughter eloped with boy of other religion family threatening her with khap panchayat",
        route_matter("my daughter eloped with boy of other religion family threatening her with khap panchayat"),
        [
            {"index": 1, "title": "Constitution of India", "anchor": "constitution-india/sec-21"},
            {"index": 2, "title": "Bharatiya Nyaya Sanhita 2023", "anchor": "bns-2023/sec-351@2024-07-01"},
            {"index": 3, "title": "Bharatiya Nagarik Suraksha Sanhita 2023", "anchor": "bnss-2023/sec-173-b@2024-07-01"},
        ],
    )
    honour_full_joined = " ".join(honour_full_lines)
    assert "Article 21" in honour_full_joined
    assert "criminal intimidation" in honour_full_joined
    assert "police protection" in honour_full_joined
    assert "[1]" in honour_full_joined and "[2]" in honour_full_joined and "[3]" in honour_full_joined

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


def test_grounded_template_for_bpl_legal_aid_cites_lsa_not_nfsa():
    from apps.api.main import _grounded_template_lines
    from apps.api.matter_router import route_matter

    q = "urgent bPL card holder eligibility for free legal aid from DLSA SLSA how to complain"
    passages = [
        {
            "index": 1,
            "title": "Legal Services Authorities Act 1987",
            "anchor": "legal-services-authorities-1987/sec-12",
            "text": "Every person who has to file or defend a case shall be entitled to legal services under this Act if that person satisfies the listed criteria.",
        },
        {
            "index": 2,
            "title": "Legal Services Authorities Act 1987",
            "anchor": "legal-services-authorities-1987/sec-9",
            "text": "The State Government shall constitute a District Legal Services Authority for every District.",
        },
        {
            "index": 3,
            "title": "Constitution of India",
            "anchor": "constitution-india/sec-39A",
            "text": "The State shall secure that the operation of the legal system promotes justice on a basis of equal opportunity.",
        },
    ]

    joined = " ".join(_grounded_template_lines(q, route_matter(q), passages))

    assert "Legal Services Authorities Act source" in joined and "[1]" in joined
    assert "District Legal Services Authority route" in joined and "[2]" in joined
    assert "National Food Security" not in joined


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

    assert ("Constitution source" in joined or "Article 21" in joined) and "[1]" in joined
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
    assert any("home place" in line and "worksite location" in line and "[2]" in line for line in lines)


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
    assert "written order/status" in release_joined and "[2]" in release_joined

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


def test_grounded_templates_for_stage_iic3_latency_and_pds_gate_rows():
    from apps.api.main import _cyber_content_abuse_floor_template_lines, _grounded_template_lines
    from apps.api.matter_router import route_matter

    pds_q = "can u tell PDS dealer biometric fail every time we are old not getting our quota odisha what can i do"
    pds_passages = [
        {"index": 1, "title": "National Food Security Act 2013", "anchor": "national-food-security-2013/sec-12"},
        {"index": 2, "title": "National Food Security Act 2013", "anchor": "national-food-security-2013/sec-14"},
        {"index": 3, "title": "National Food Security Act 2013", "anchor": "national-food-security-2013/sec-15"},
        {"index": 4, "title": "Aadhaar (Targeted Delivery of Financial and Other Subsidies, Benefits and Services) Act 2016", "anchor": "aadhaar-2016/sec-7"},
        {"index": 5, "title": "Right to Information Act 2005", "anchor": "rti-2005/sec-6"},
    ]
    pds_joined = " ".join(_grounded_template_lines(pds_q, route_matter(pds_q), pds_passages))
    assert "biometric machine fails" in pds_joined and "not as a generic Aadhaar problem" in pds_joined
    assert "alternate or exception handling" in pds_joined and "[4]" in pds_joined
    assert "RTI only to get records" in pds_joined and "[5]" in pds_joined

    pension_q = "sir old age pension stopped suddenly bank says aadhaar not linked where to go"
    pension_passages = [
        {"index": 1, "title": "National Social Assistance Programme Guidelines 2014", "anchor": "nsap-guidelines-2014#header"},
        {"index": 2, "title": "Aadhaar (Targeted Delivery of Financial and Other Subsidies, Benefits and Services) Act 2016", "anchor": "aadhaar-2016/sec-7"},
        {"index": 3, "title": "Right to Information Act 2005", "anchor": "rti-2005/sec-6"},
    ]
    pension_joined = " ".join(_grounded_template_lines(pension_q, route_matter(pension_q), pension_passages))
    assert "stopped old-age pension" in pension_joined and "[1]" in pension_joined
    assert "do not make RTI the only remedy" in pension_joined and "[3]" in pension_joined

    epf_q = "what to do garment factory tiruppur cuts pf from salary every month epf passbook empty 3 yrs is this legal"
    epf_passages = [
        {"index": 1, "title": "Employees' Provident Funds and Miscellaneous Provisions Act 1952", "anchor": "epf-1952/sec-14-a"},
        {"index": 2, "title": "Code on Social Security 2020", "anchor": "social-security-code-2020#header"},
    ]
    epf_joined = " ".join(_grounded_template_lines(epf_q, route_matter(epf_q), epf_passages))
    assert "EPF default/recovery issue" in epf_joined and "[1]" in epf_joined
    assert "employer contribution-default" in epf_joined
    assert "EPFO grievance/recovery" in epf_joined

    ibc_q = "urgent procedure to file insolvency petition against company in NCLT how to complain"
    ibc_passages = [
        {"index": 1, "title": "Insolvency and Bankruptcy Code 2016", "anchor": "ibc-2016/sec-8"},
        {"index": 2, "title": "Insolvency and Bankruptcy Code 2016", "anchor": "ibc-2016/sec-9"},
    ]
    ibc_joined = " ".join(_grounded_template_lines(ibc_q, route_matter(ibc_q), ibc_passages))
    assert "demand-notice source" in ibc_joined and "[1]" in ibc_joined
    assert "NCLT filing route" in ibc_joined and "[2]" in ibc_joined

    cyber_q = "morphed group photo of my college girls hostel on reddit who to contact"
    cyber_passages = [
        {"index": 1, "title": "Information Technology Act 2000", "anchor": "it-2000/sec-66E"},
        {"index": 2, "title": "Bharatiya Nyaya Sanhita 2023", "anchor": "bns-2023/sec-77"},
    ]
    cyber_joined = " ".join(_grounded_template_lines(cyber_q, route_matter(cyber_q), cyber_passages))
    assert "morphed or non-consensual image" in cyber_joined and "[1]" in cyber_joined
    assert "Reddit links" in cyber_joined

    telegram_q = "morphed nude photo of me circulating in telegram college group"
    telegram_joined = " ".join(_grounded_template_lines(telegram_q, route_matter(telegram_q), cyber_passages))
    assert "morphed nude photo in the Telegram/college group" in telegram_joined
    assert "college/group context" in telegram_joined
    telegram_floor_joined = " ".join(_cyber_content_abuse_floor_template_lines(telegram_q, cyber_passages))
    assert "morphed nude photo in the Telegram/college group" in telegram_floor_joined
    assert "urgent takedown" in telegram_floor_joined

    deepfake_q = "ex boyfriend made ai deepfake porn of me uploaded online"
    deepfake_joined = " ".join(_grounded_template_lines(deepfake_q, route_matter(deepfake_q), cyber_passages))
    assert "AI deepfake porn video uploaded online by an ex-boyfriend" in deepfake_joined
    assert "takedown/removal" in deepfake_joined


def test_grounded_templates_for_stage_iic4_fake_cbi_and_latency_rows():
    from apps.api.main import _grounded_template_lines
    from apps.api.matter_router import route_matter

    cbi_q = "got call from cbi saying parcel has drugs send 5 lakh is this scam"
    cbi_passages = [
        {"index": 1, "title": "Information Technology Act 2000", "anchor": "it-2000/sec-66D"},
        {"index": 2, "title": "Information Technology Act 2000", "anchor": "it-2000/sec-66C"},
        {"index": 3, "title": "Bharatiya Nyaya Sanhita 2023", "anchor": "bns-2023/sec-319"},
        {"index": 4, "title": "Bharatiya Nagarik Suraksha Sanhita 2023", "anchor": "bnss-2023/sec-173"},
    ]
    cbi_joined = " ".join(_grounded_template_lines(cbi_q, route_matter(cbi_q), cbi_passages))
    assert "Source to verify first: Information Technology Act 2000 [1]." in cbi_joined
    assert "fake CBI/police/courier parcel call demanding money" in cbi_joined
    assert "Do not send money" in cbi_joined
    assert "1930/cybercrime.gov.in" in cbi_joined
    assert "Additional source to verify" not in cbi_joined

    pocso_q = "when i was 13 uncle touched me many years back now 19 can I complain"
    pocso_passages = [
        {"index": 1, "title": "Protection of Children from Sexual Offences Act 2012", "anchor": "pocso-2012/sec-7"},
        {"index": 2, "title": "Bharatiya Nagarik Suraksha Sanhita 2023", "anchor": "bnss-2023/sec-173"},
    ]
    pocso_joined = " ".join(_grounded_template_lines(pocso_q, route_matter(pocso_q), pocso_passages))
    assert "child sexual-offence/POCSO track" in pocso_joined and "[1]" in pocso_joined
    assert "do not assume there is no remedy only because time passed" in pocso_joined

    child_labour_q = "my 15 year old boy working in factory how to prove age"
    child_labour_passages = [
        {"index": 1, "title": "Child and Adolescent Labour (Prohibition and Regulation) Act 1986", "anchor": "child-labour-1986/sec-3A"},
        {"index": 2, "title": "Child and Adolescent Labour (Prohibition and Regulation) Act 1986", "anchor": "child-labour-1986/sec-17"},
    ]
    child_labour_joined = " ".join(_grounded_template_lines(child_labour_q, route_matter(child_labour_q), child_labour_passages))
    assert "15-year-old or adolescent worker" in child_labour_joined
    assert "age proof" in child_labour_joined and "[1]" in child_labour_joined

    tds_q = "employer deducted tds but not showing in 26as refund stuck"
    tds_passages = [
        {"index": 1, "title": "Income-tax Act 1961", "anchor": "income-tax-1961/sec-200"},
    ]
    tds_joined = " ".join(_grounded_template_lines(tds_q, route_matter(tds_q), tds_passages))
    assert "Income-tax TDS-credit/deposit proof issue" in tds_joined
    assert "Form 16/TDS certificate" in tds_joined

    deduction_q = "80C and 80CCD deduction can I claim together"
    deduction_passages = [
        {"index": 1, "title": "Income-tax Act 1961", "anchor": "income-tax-1961/sec-80C"},
    ]
    deduction_joined = " ".join(_grounded_template_lines(deduction_q, route_matter(deduction_q), deduction_passages))
    assert "80C/80CCD/NPS deduction" in deduction_joined
    assert "80C and 80CCD(1B) separately" in deduction_joined

    bail_q = "anticipatory bail granted but police threatening arrest"
    bail_passages = [
        {"index": 1, "title": "Code of Criminal Procedure 1973", "anchor": "crpc-1973/sec-438"},
    ]
    bail_joined = " ".join(_grounded_template_lines(bail_q, route_matter(bail_q), bail_passages))
    assert "bail-order compliance/clarification issue" in bail_joined
    assert "extension, regular bail, or clarification" in bail_joined

    summons_q = "received family court summons divorce case what next before lawyer"
    summons_passages = [
        {"index": 1, "title": "Family Courts Act 1984", "anchor": "family-courts-1984/sec-7"},
        {"index": 2, "title": "Code of Civil Procedure 1908", "anchor": "cpc-1908/order-5"},
    ]
    summons_joined = " ".join(_grounded_template_lines(summons_q, route_matter(summons_q), summons_passages))
    assert "family-court summons" in summons_joined
    assert "CPC source" in summons_joined and "[2]" in summons_joined
    assert "before the listed date" in summons_joined

    counselling_q = "urgent mera family court summon aya hai counselling likha hai kya leke jana hai lawyer nahi hai"
    counselling_joined = " ".join(_grounded_template_lines(counselling_q, route_matter(counselling_q), summons_passages))
    assert "counselling or mediation" in counselling_joined
    assert "do not yet have a lawyer" in counselling_joined

    bonded_q = "contractor kept our passports says work until loan finish"
    bonded_passages = [
        {"index": 1, "title": "Bonded Labour System (Abolition) Act 1976", "anchor": "bonded-labour-1976/sec-10"},
    ]
    bonded_joined = " ".join(_grounded_template_lines(bonded_q, route_matter(bonded_q), bonded_passages))
    assert "cards, passport, Aadhaar, or original ID" in bonded_joined
    assert "return of documents" in bonded_joined


def test_grounded_templates_for_stage_iid1_offtopic_recovery_rows():
    from apps.api.main import _grounded_template_lines
    from apps.api.matter_router import route_matter

    cases = [
        (
            "kanya vivah scheme money not given by government after my daughter wedding",
            [
                {"index": 1, "title": "Right to Information Act 2005", "anchor": "rti-2005/sec-6"},
                {"index": 2, "title": "Right to Information Act 2005", "anchor": "rti-2005/sec-19"},
            ],
            (
                "Kanya Vivah payment status",
                "district social welfare or women-child office",
                "payment file number",
                "Use RTI only as a record-status route",
            ),
        ),
        (
            "my husband left me with two children and no money for school fees what to do",
            [
                {"index": 1, "title": "Family Courts Act 1984", "anchor": "family-courts-1984/sec-7"},
                {"index": 2, "title": "Protection of Women from Domestic Violence Act 2005", "anchor": "domestic-violence-2005/sec-20"},
                {"index": 3, "title": "Bharatiya Nagarik Suraksha Sanhita 2023", "anchor": "bnss-2023/sec-144"},
            ],
            (
                "spouse/child maintenance and school-fee support",
                "nonpayment alone should not be criminalized",
                "monthly-expense table",
                "[3]",
            ),
        ),
        (
            "my husband's brother has been making me uncomfortable saying things and now grabbed my hand whom to tell I cant tell husband",
            [
                {"index": 1, "title": "Protection of Women from Domestic Violence Act 2005", "anchor": "domestic-violence-2005/sec-3"},
                {"index": 2, "title": "Protection of Women from Domestic Violence Act 2005", "anchor": "domestic-violence-2005/sec-18"},
                {"index": 3, "title": "Bharatiya Nyaya Sanhita 2023", "anchor": "bns-2023/sec-74"},
            ],
            (
                "domestic-relationship safety/harassment fact",
                "not a generic family dispute",
                "BNS modesty/sexual-harassment check only if",
                "grabbing/touching details",
            ),
        ),
        (
            "my ex husband took our son to UK on tourist visa and is not bringing back he said permanent now what to do",
            [
                {"index": 1, "title": "Guardians and Wards Act 1890", "anchor": "guardians-wards-1890/sec-25"},
                {"index": 2, "title": "Guardians and Wards Act 1890", "anchor": "guardians-wards-1890/sec-17"},
                {"index": 3, "title": "Constitution of India", "anchor": "constitution-india/sec-21"},
                {"index": 4, "title": "Family Courts Act 1984", "anchor": "family-courts-1984/sec-7"},
            ],
            (
                "tourist/foreign-visa route",
                "urgent custody/child-return",
                "do not label it abduction",
                "passport/visa/travel details",
            ),
        ),
        (
            "I am living with my boyfriend for 3 years he promised marriage now he is marrying another girl can I file case",
            [
                {"index": 1, "title": "Bharatiya Nyaya Sanhita 2023", "anchor": "bns-2023/sec-69"},
                {"index": 2, "title": "Bharatiya Nagarik Suraksha Sanhita 2023", "anchor": "bnss-2023/sec-173"},
                {"index": 3, "title": "Protection of Women from Domestic Violence Act 2005", "anchor": "domestic-violence-2005/sec-3"},
            ],
            (
                "not automatically criminal",
                "deception at the start",
                "BNSS FIR/information source",
                "live-in domestic relationship",
            ),
        ),
        (
            "what should I wear to court as litigant in person appearing first time",
            [
                {"index": 1, "title": "Code of Civil Procedure 1908", "anchor": "cpc-1908/order-5"},
            ],
            (
                "court-practice and respect issue",
                "not a separate legal claim",
                "case number",
                "court help desk/reader",
            ),
        ),
        (
            "i forgot to file ITR for AY 2022-23 can i still file it now what is the penalty",
            [
                {"index": 1, "title": "Income-tax Act 1961", "anchor": "income-tax-1961/sec-139"},
                {"index": 2, "title": "Income-tax Act 1961", "anchor": "income-tax-1961/sec-234F"},
            ],
            (
                "old assessment year",
                "late-fee/penalty check",
                "belated/updated filing depends",
                "income-tax portal",
            ),
        ),
        (
            "sarpanch giving common village land to his brother no panchayat meeting was held",
            [
                {"index": 1, "title": "Constitution of India", "anchor": "constitution-india/sec-243G"},
                {"index": 2, "title": "Right to Information Act 2005", "anchor": "rti-2005/sec-6"},
            ],
            (
                "Gram Panchayat/common-land records",
                "valid Gram Sabha or Panchayat resolution",
                "no Panchayat meeting",
                "File RTI",
            ),
        ),
        (
            "the spa was raided last week and police took me and other girls to station I just do massage I am scared what will happen now",
            [
                {"index": 1, "title": "Immoral Traffic (Prevention) Act 1956", "anchor": "itpa-1956/sec-5"},
                {"index": 2, "title": "Immoral Traffic (Prevention) Act 1956", "anchor": "itpa-1956/sec-8"},
                {"index": 3, "title": "Bharatiya Nagarik Suraksha Sanhita 2023", "anchor": "bnss-2023/sec-173"},
            ],
            (
                "do not accept a generic ITPA label",
                "must be matched to the alleged role",
                "not merely reception-desk work",
                "do not admit involvement beyond facts",
            ),
        ),
    ]

    for query, passages, expected_parts in cases:
        joined = " ".join(_grounded_template_lines(query, route_matter(query), passages))
        assert joined
        for part in expected_parts:
            assert part in joined


def test_grounded_templates_for_stage_iid2_production_gate_rows():
    from apps.api.main import _grounded_template_lines
    from apps.api.matter_router import route_matter

    cases = [
        (
            "my landlord is asking me to vacate in 15 days because he wants to sell the flat, my lock in is for 11 months",
            [
                {"index": 1, "title": "Transfer of Property Act 1882", "anchor": "transfer-of-property-1882/sec-105"},
                {"index": 2, "title": "Transfer of Property Act 1882", "anchor": "transfer-of-property-1882/sec-106"},
                {"index": 3, "title": "Transfer of Property Act 1882", "anchor": "transfer-of-property-1882/sec-111"},
            ],
            ("15-day demand", "lock-in clause", "state rent-control/local tenancy law", "sale reason"),
        ),
        (
            "husband took my salary atm card and gives me only 2000 per month for groceries is this legal he says he is breadwinner",
            [
                {"index": 1, "title": "Protection of Women from Domestic Violence Act 2005", "anchor": "domestic-violence-2005/sec-3"},
                {"index": 2, "title": "Protection of Women from Domestic Violence Act 2005", "anchor": "domestic-violence-2005/sec-20"},
                {"index": 3, "title": "Protection of Women from Domestic Violence Act 2005", "anchor": "domestic-violence-2005/sec-12"},
            ],
            ("economic abuse", "salary, ATM card", "monetary-relief", "Protection Officer"),
        ),
        (
            "I am 6 months pregnant after rape doctor says it is too late for abortion but I cannot keep this child help",
            [
                {"index": 1, "title": "Medical Termination of Pregnancy Act 1971", "anchor": "mtp-1971/sec-3"},
                {"index": 2, "title": "Medical Termination of Pregnancy Act 1971", "anchor": "mtp-1971/sec-5"},
                {"index": 3, "title": "Medical Termination of Pregnancy Act 1971", "anchor": "mtp-1971/sec-5A"},
            ],
            ("urgent medical-and-legal help", "medical-board", "government hospital", "Do not wait for a perfect legal answer"),
        ),
        (
            "girl child age 4 my wife died parents in law took her away they refuse to return",
            [
                {"index": 1, "title": "Guardians and Wards Act 1890", "anchor": "guardians-wards-1890/sec-25"},
                {"index": 2, "title": "Guardians and Wards Act 1890", "anchor": "guardians-wards-1890/sec-17"},
                {"index": 3, "title": "Hindu Minority and Guardianship Act 1956", "anchor": "hindu-minority-guardianship-1956/sec-6"},
                {"index": 4, "title": "Hindu Minority and Guardianship Act 1956", "anchor": "hindu-minority-guardianship-1956/sec-13"},
                {"index": 5, "title": "Family Courts Act 1984", "anchor": "family-courts-1984/sec-7"},
            ],
            ("Guardians and Wards Act", "Hindu Minority and Guardianship", "natural-guardian", "child's welfare"),
        ),
        (
            "I left my husband 2 months back I have a baby 1 year old he is not giving any money how much maintenance can I get",
            [
                {"index": 1, "title": "Family Courts Act 1984", "anchor": "family-courts-1984/sec-7"},
                {"index": 2, "title": "Hindu Marriage Act 1955", "anchor": "hindu-marriage-1955/sec-24"},
                {"index": 3, "title": "Protection of Women from Domestic Violence Act 2005", "anchor": "domestic-violence-2005/sec-20"},
                {"index": 4, "title": "Bharatiya Nagarik Suraksha Sanhita 2023", "anchor": "bnss-2023/sec-144"},
                {"index": 5, "title": "Code of Criminal Procedure 1973", "anchor": "crpc-1973/sec-125"},
            ],
            ("spouse/child maintenance", "wife or mother with a baby", "interim maintenance or monetary-relief", "legacy CrPC", "[4]", "[5]"),
        ),
    ]

    for query, passages, expected_parts in cases:
        joined = " ".join(_grounded_template_lines(query, route_matter(query), passages))
        assert joined
        for part in expected_parts:
            assert part in joined


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


def test_grounded_cyber_content_abuse_templates_are_user_actionable():
    from apps.api.main import _grounded_template_lines
    from apps.api.matter_router import route_matter

    creator_q = "telegram channel leaked my onlyfans videos without permission what to do"
    creator_joined = " ".join(_grounded_template_lines(creator_q, route_matter(creator_q), [
        {"index": 1, "title": "Copyright Act 1957", "anchor": "copyright-1957/sec-51"},
        {"index": 2, "title": "Copyright Act 1957", "anchor": "copyright-1957/sec-55"},
        {"index": 3, "title": "Information Technology Act 2000", "anchor": "it-2000/sec-79"},
    ]))
    assert "Leaked paid creator content" in creator_joined
    assert "platform/intermediary" in creator_joined
    assert "channel URL" in creator_joined
    assert "takedown" in creator_joined
    assert "[1]" in creator_joined and "[3]" in creator_joined

    blackmail_q = "my ex made deepfake porn and blackmailing me for money"
    blackmail_joined = " ".join(_grounded_template_lines(blackmail_q, route_matter(blackmail_q), [
        {"index": 4, "title": "Bharatiya Nyaya Sanhita 2023", "anchor": "bns-2023/sec-308"},
        {"index": 5, "title": "Information Technology Act 2000", "anchor": "it-2000/sec-66E"},
    ]))
    assert "Do not pay" in blackmail_joined
    assert "cybercrime.gov.in" in blackmail_joined
    assert "IT Act privacy source" in blackmail_joined
    assert "[4]" in blackmail_joined or "[5]" in blackmail_joined

    election_q = "MLA candidate deepfake video during election campaign shared on whatsapp"
    election_joined = " ".join(_grounded_template_lines(election_q, route_matter(election_q), [
        {"index": 6, "title": "Information Technology Act 2000", "anchor": "it-2000/sec-66E"},
        {"index": 7, "title": "Representation of the People Act 1951", "anchor": "rpa-1951/sec-123"},
    ]))
    assert "Representation of the People Act" in election_joined
    assert "campaign context" in election_joined
    assert "Returning Officer" in election_joined
    assert "[6]" in election_joined and "[7]" in election_joined


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


def test_grounded_template_for_birth_certificate_leads_with_civil_registration_when_sourced():
    from apps.api.main import _grounded_template_lines
    from apps.api.matter_router import route_matter

    q = "panchayat secretary not giving me birth certificate of my child born at home"
    passages = [
        {"index": 1, "title": "Registration of Births and Deaths Act 1969", "anchor": "registration-births-deaths-1969/sec-7"},
        {"index": 2, "title": "Registration of Births and Deaths Act 1969", "anchor": "registration-births-deaths-1969/sec-8"},
        {"index": 3, "title": "Registration of Births and Deaths Act 1969", "anchor": "registration-births-deaths-1969/sec-12"},
        {"index": 4, "title": "Registration of Births and Deaths Act 1969", "anchor": "registration-births-deaths-1969/sec-13"},
        {"index": 5, "title": "Right to Information Act 2005", "anchor": "rti-2005/sec-6"},
    ]

    joined = " ".join(_grounded_template_lines(q, route_matter(q), passages))

    assert "Registration of Births and Deaths" in joined
    assert "generic RTI" in joined
    assert "born at home" in joined and "[2]" in joined
    assert "delayed-registration" in joined and "[4]" in joined
    assert "RTI request" not in joined


def test_grounded_template_for_death_certificate_correction_uses_civil_registration():
    from apps.api.main import _grounded_template_lines
    from apps.api.matter_router import route_matter

    q = "death certificate has wrong name hospital says they cannot correct it what is process"
    passages = [
        {"index": 1, "title": "Registration of Births and Deaths Act 1969", "anchor": "registration-births-deaths-1969/sec-15"},
        {"index": 2, "title": "Right to Information Act 2005", "anchor": "rti-2005/sec-6"},
        {"index": 3, "title": "Right to Information Act 2005", "anchor": "rti-2005/sec-19"},
    ]

    route = route_matter(q)
    joined = " ".join(_grounded_template_lines(q, route, passages))

    assert route.category == "social_welfare_identity"
    assert "death certificate" in joined
    assert "civil-registration" in joined
    assert "[1]" in joined and "[2]" in joined
    assert "hospital-service complaint" in joined


def test_bank_freeze_template_cites_bnss_for_cyber_police_lien():
    from apps.api.main import _grounded_template_lines
    from apps.api.matter_router import route_matter

    q = "my bank account is frozen suddenly cyber police says lien what can I do"
    passages = [
        {"index": 1, "title": "Reserve Bank Integrated Ombudsman Scheme 2021", "anchor": "rbi-integrated-ombudsman-2021/sec-2"},
        {"index": 2, "title": "Banking Regulation Act 1949", "anchor": "banking-regulation-1949/sec-35A"},
        {"index": 3, "title": "Bharatiya Nagarik Suraksha Sanhita 2023", "anchor": "bnss-2023/sec-106"},
    ]

    joined = " ".join(_grounded_template_lines(q, route_matter(q), passages))

    assert "RBI Ombudsman" in joined and "[1]" in joined
    assert "cyber police" in joined and "BNSS" in joined and "[3]" in joined


def test_posh_retaliation_template_cites_industrial_disputes_when_fired():
    from apps.api.main import _grounded_template_lines
    from apps.api.matter_router import route_matter

    q = "my employer fired me after i complained to ICC about sexual harassment at office"
    passages = [
        {"index": 1, "title": "Sexual Harassment of Women at Workplace Act 2013", "anchor": "posh-2013/sec-9"},
        {"index": 2, "title": "Industrial Disputes Act 1947", "anchor": "industrial-disputes-1947/sec-2A"},
    ]

    joined = " ".join(_grounded_template_lines(q, route_matter(q), passages))

    assert "Internal Committee" in joined and "[1]" in joined
    assert "Industrial Disputes Act" in joined and "[2]" in joined


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

    sourced_lines = _grounded_template_lines(
        q,
        route_matter(q),
        [
            {"index": 1, "title": "Bharatiya Nagarik Suraksha Sanhita 2023", "anchor": "bnss-2023/sec-483"},
            {"index": 2, "title": "Bharatiya Nyaya Sanhita 2023", "anchor": "bns-2023/sec-76"},
            {
                "index": 3,
                "title": "Chhattisgarh Tonahi Pratadna Nivaran Act 2005",
                "anchor": "chhattisgarh-tonahi-pratadna-nivaran-2005/sec-4",
            },
        ],
    )
    joined = " ".join(sourced_lines)
    assert "Chhattisgarh Tonahi Act source" in joined
    assert "[3]" in joined
    assert "do not have the exact Chhattisgarh Tonahi" not in joined


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


def test_fra_reserved_farming_template_cites_fra_and_forest_conservation():
    from apps.api.main import _grounded_template_lines
    from apps.api.matter_router import route_matter

    query = "sir forest department saying our land is reserve we have been farming since grandfather time where to go"
    text = " ".join(_grounded_template_lines(query, route_matter(query), [
        {"index": 3, "title": "Scheduled Tribes and Other Traditional Forest Dwellers (Recognition of Forest Rights) Act 2006", "anchor": "fra-2006/sec-5-a"},
        {"index": 4, "title": "Scheduled Tribes and Other Traditional Forest Dwellers (Recognition of Forest Rights) Act 2006", "anchor": "fra-2006/sec-3-c"},
        {"index": 5, "title": "Forest (Conservation) Act 1980", "anchor": "forest-conservation-1980/sec-2"},
    ]))
    assert "FRA institutions" in text
    assert "Forest Conservation Act source is a separate" in text
    assert "[3]" in text or "[4]" in text
    assert "[5]" in text
    assert "Scheduled Castes and Scheduled Tribes" not in text


def test_cfr_mining_template_cites_fra_fca_and_mmdr():
    from apps.api.main import _grounded_template_lines
    from apps.api.matter_router import route_matter

    query = "gram sabha got community forest rights but mining company started digging inside forest can we stop it"
    text = " ".join(_grounded_template_lines(query, route_matter(query), [
        {"index": 1, "title": "Scheduled Tribes and Other Traditional Forest Dwellers (Recognition of Forest Rights) Act 2006", "anchor": "fra-2006/sec-3-c"},
        {"index": 2, "title": "Forest (Conservation) Act 1980", "anchor": "forest-conservation-1980/sec-2"},
        {"index": 3, "title": "Mines and Minerals (Development and Regulation) Act 1957", "anchor": "mmdr-1957#header"},
        {"index": 4, "title": "Panchayats (Extension to the Scheduled Areas) Act 1996", "anchor": "pesa-1996/sec-4-c"},
    ]))
    assert "community forest rights/CFR" in text
    assert "Forest Conservation Act source" in text
    assert "MMDR/mining source" in text
    assert "[1]" in text and "[2]" in text and "[3]" in text


def test_forest_notice_template_keeps_forest_authority_first_not_fra_or_magistrate():
    from apps.api.main import _grounded_template_lines
    from apps.api.matter_router import route_matter

    query = "forest guard says I recently encroached forest land last month and gave notice what forum should I approach"
    text = " ".join(_grounded_template_lines(query, route_matter(query), [
        {"index": 4, "title": "Forest (Conservation) Act 1980", "anchor": "forest-conservation-1980/sec-2"},
        {"index": 5, "title": "Scheduled Tribes and Other Traditional Forest Dwellers (Recognition of Forest Rights) Act 2006", "anchor": "fra-2006/sec-5-a"},
    ]))

    assert "respond to the written notice" in text
    assert "Do not assume the FRA route" in text
    assert "range officer/DFO" in text
    assert "Magistrate/court only if prosecution" in text
    assert "[4]" in text


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
            ("arrest-information", "[7]", "FIR copy", "grounds of arrest"),
        ),
        (
            "My bike is stolen, police is not filing FIR",
                [
                    {"index": 9, "title": "Bharatiya Nyaya Sanhita 2023", "anchor": "bns-2023/sec-303"},
                    {"index": 10, "title": "Bharatiya Nagarik Suraksha Sanhita 2023", "anchor": "bnss-2023/sec-173-a"},
                    {"index": 11, "title": "Bharatiya Nagarik Suraksha Sanhita 2023", "anchor": "bnss-2023/sec-173-c"},
                    {"index": 29, "title": "Code of Criminal Procedure 1973", "anchor": "crpc-1973/sec-154"},
                ],
                ("pre-1-July-2024", "incident on or after 1 July 2024", "Superintendent of Police", "[10]", "[29]"),
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
            "wife family hid her earlier marriage before wedding remedy",
            [
                {"index": 21, "title": "Hindu Marriage Act 1955", "anchor": "hindu-marriage-1955/sec-12"},
                {"index": 22, "title": "Family Courts Act 1984", "anchor": "family-courts-1984/sec-7"},
            ],
            ("earlier or subsisting-marriage fact", "legally subsisting", "divorce/death proof", "annulment/nullity", "[21]"),
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
                ("marriage-breakdown", "[17]", "Section 13", "[18]", "do not force, threaten, or pressure", "DLSA"),
        ),
        (
            "i caught my husband with another women having sex",
            [
                {"index": 19, "title": "Hindu Marriage Act 1955", "anchor": "hindu-marriage-1955/sec-13"},
                {"index": 20, "title": "Family Courts Act 1984", "anchor": "family-courts-1984/sec-7"},
            ],
            ("Section 13", "[19]", "Family Courts Act", "[20]", "not treat catching your husband", "DLSA"),
        ),
        (
            "My brother is not returning my money, which he took loan",
            [
                {"index": 21, "title": "Indian Contract Act 1872", "anchor": "indian-contract-1872/sec-37"},
                {"index": 22, "title": "Limitation Act 1963", "anchor": "limitation-1963/sec-3"},
                {"index": 23, "title": "Code of Civil Procedure 1908", "anchor": "cpc-1908/order-xxxvii"},
            ],
            ("civil money-recovery", "[21]", "Limitation Act", "[22]", "not frame it as cheque bounce", "police cheating case", "bank/UPI"),
        ),
        (
            "Can I sell property if one legal heir is not agreeing?",
            [
                {"index": 24, "title": "Hindu Succession Act 1956", "anchor": "hindu-succession-1956/sec-8"},
                {"index": 25, "title": "Transfer of Property Act 1882", "anchor": "transfer-of-property-1882/sec-44"},
                {"index": 26, "title": "Specific Relief Act 1963", "anchor": "specific-relief-1963/sec-34"},
            ],
            ("legal heirs", "[24]", "applicable succession or personal law", "does not prove that the whole property can be sold", "[25]", "declaration", "[26]"),
        ),
        (
            "Bank deducted money wrongly and customer care not helping.",
            _rbi_ombudsman_sources(27),
            ("RBI Ombudsman/CMS", "[27]", "written complaint", "[31]"),
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


def test_grounded_template_for_bihar_prohibition_avoids_unrelated_section_source():
    from apps.api.main import _answer_contract_lines, _grounded_template_lines
    from apps.api.matter_router import route_matter

    q = "patna thana says section 37 bihar prohibition on me for liquor what can I do"
    route = route_matter(q)
    passages = [
        {"index": 1, "title": "Bihar Prohibition and Excise Act 2016", "anchor": "bihar-prohibition-excise-2016/sec-37", "source_type": "bare_act", "text": "Consumption liquor penalty."},
        {"index": 2, "title": "Bihar Prohibition and Excise Act 2016", "anchor": "bihar-prohibition-excise-2016/sec-76", "source_type": "bare_act", "text": "Cognizable non-bailable handling."},
        {"index": 3, "title": "Bharatiya Nagarik Suraksha Sanhita 2023", "anchor": "bnss-2023/sec-483", "source_type": "bare_act", "text": "High Court or Court of Session bail power."},
        {"index": 4, "title": "Occupational Safety, Health and Working Conditions Code 2020", "anchor": "oshwc-2020/sec-37", "source_type": "bare_act", "text": "Welfare facilities."},
    ]

    lines = _grounded_template_lines(q, route, passages)
    contract_lines = _answer_contract_lines(
        route,
        passages,
        {
            "saw_next_step_header": True,
            "saw_next_step_sentence": True,
            "emitted": len(lines),
            "emitted_citation_indices": {1, 2, 3},
            "seen_sentences": set(),
        },
        None,
    )
    joined = " ".join([*lines, *contract_lines])

    assert "Bihar Prohibition" in joined and "[1]" in joined
    assert "criminal-procedure source" in joined and "[3]" in joined
    assert "Occupational Safety" not in joined


def test_labour_register_template_handles_wrong_state_shop_register_request():
    from apps.api.main import _grounded_template_lines
    from apps.api.matter_router import route_matter

    q = "bangalore store labour officer demanding maharashtra shops register is that right"
    passages = [
        {"index": 6, "title": "Right to Information Act 2005", "anchor": "rti-2005/sec-6"},
    ]

    joined = " ".join(_grounded_template_lines(q, route_matter(q), passages))

    assert "Maharashtra Shops register demand" in joined
    assert "Bangalore/Karnataka" in joined
    assert "[6]" in joined


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


def test_custody_status_templates_answer_from_owned_sources():
    from apps.api.main import _grounded_template_lines
    from apps.api.matter_router import route_matter

    hidden_q = "police took my brother last night not showing station and not allowing lawyer what urgent remedy"
    hidden_passages = [
        {"index": 1, "title": "Constitution of India", "anchor": "constitution-india/sec-21"},
        {"index": 2, "title": "Constitution of India", "anchor": "constitution-india/sec-226"},
        {"index": 3, "title": "Constitution of India", "anchor": "constitution-india/sec-22"},
        {"index": 4, "title": "Bharatiya Nagarik Suraksha Sanhita 2023", "anchor": "bnss-2023/sec-58"},
    ]
    hidden_joined = " ".join(_grounded_template_lines(hidden_q, route_matter(hidden_q), hidden_passages))
    assert "habeas corpus" in hidden_joined
    assert "Article 226" in hidden_joined and "[2]" in hidden_joined
    assert "lawyer access" in hidden_joined and "[3]" in hidden_joined

    missing_q = "my adult brother missing since yesterday phone off but no proof police picked him what complaint should i file"
    missing_passages = [
        {"index": 6, "title": "Bharatiya Nagarik Suraksha Sanhita 2023", "anchor": "bnss-2023/sec-173"},
        {"index": 7, "title": "Bharatiya Nagarik Suraksha Sanhita 2023", "anchor": "bnss-2023/sec-175"},
        {"index": 8, "title": "Information Technology Act 2000", "anchor": "it-2000/sec-2"},
    ]
    missing_joined = " ".join(_grounded_template_lines(missing_q, route_matter(missing_q), missing_passages))
    assert "missing-person police complaint" in missing_joined
    assert "police custody" in missing_joined
    assert "IT Act" not in missing_joined
    assert "kidnapping" not in missing_joined.lower()
    assert "habeas corpus" not in missing_joined.lower()
    assert "[6]" in missing_joined and "[7]" in missing_joined

    notice_q = "police sent notice to come station for questioning tomorrow but not arrested should i go with lawyer"
    notice_passages = [
        {"index": 10, "title": "Bharatiya Nagarik Suraksha Sanhita 2023", "anchor": "bnss-2023/sec-35"},
        {"index": 11, "title": "Code of Criminal Procedure 1973", "anchor": "crpc-1973/sec-160"},
    ]
    notice_joined = " ".join(_grounded_template_lines(notice_q, route_matter(notice_q), notice_passages))
    assert "not the same thing as bail" in notice_joined
    assert "written notice" in notice_joined
    assert "[10]" in notice_joined

    legal_aid_q = "jail superintendent not allowing lawyer meeting for my brother first time arrest what legal aid route"
    legal_aid_passages = [
        {"index": 20, "title": "Legal Services Authorities Act 1987", "anchor": "legal-services-authorities-1987/sec-12"},
        {"index": 21, "title": "Constitution of India", "anchor": "constitution-india/sec-22"},
        {"index": 22, "title": "Bharatiya Nagarik Suraksha Sanhita 2023", "anchor": "bnss-2023/sec-58"},
    ]
    legal_aid_joined = " ".join(_grounded_template_lines(legal_aid_q, route_matter(legal_aid_q), legal_aid_passages))
    assert "custody legal-aid and lawyer-access" in legal_aid_joined
    assert "Article 22" in legal_aid_joined and "[21]" in legal_aid_joined
    assert "arrest/remand" in legal_aid_joined and "[22]" in legal_aid_joined


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
    assert "RTI" in kanya_joined or "prescribed fee" in kanya_joined or "request" in kanya_joined

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


def test_hindu_intestacy_authority_contract_owns_live_succession_variant():
    from apps.api.main import _grounded_template_lines
    from apps.api.matter_router import route_matter

    query = "sir uncle is 80 not married no children who inherits his self acquired prop hindu where to go"
    lines = _grounded_template_lines(query, route_matter(query), [
        {"index": 1, "title": "Hindu Succession Act 1956 (with 2005 amendment)", "anchor": "hindu-succession-1956/sec-10"},
        {"index": 2, "title": "Hindu Succession Act 1956 (with 2005 amendment)", "anchor": "hindu-succession-1956/sec-8"},
    ])
    rendered = " ".join(lines)

    assert "Hindu male's self-acquired property" in rendered
    assert "Section 8" in rendered
    assert "Class I heir" in rendered
    assert "mother dying" not in rendered


def test_civil_summons_service_contract_preserves_party_role_ambiguity():
    from apps.api.main import _grounded_template_lines
    from apps.api.matter_router import route_matter

    query = "sir summons not served through registered post what is next step where to go"
    lines = _grounded_template_lines(query, route_matter(query), [
        {"index": 6, "title": "Code of Civil Procedure 1908", "anchor": "cpc-1908/sec-20__2@2026-01-10"},
    ])
    rendered = " ".join(lines)

    assert "party asking the court to serve another person" in rendered
    assert "substituted service will automatically be ordered" in rendered
    assert "court-directed step" in rendered
    assert "[6]" in rendered


def test_grounded_criminal_defence_floor_handles_accused_subroutes():
    from apps.api.main import _grounded_template_lines
    from apps.api.matter_router import route_matter

    promise_q = "girl I was dating filed rape case after we broke up saying I promised marriage can I get bail"
    promise_joined = " ".join(_grounded_template_lines(promise_q, route_matter(promise_q), [
        {"index": 21, "title": "Bharatiya Nyaya Sanhita 2023", "anchor": "bns-2023/sec-69"},
        {"index": 22, "title": "Bharatiya Nagarik Suraksha Sanhita 2023", "anchor": "bnss-2023/sec-480"},
    ]))
    assert "promise-to-marry rape-accusation defence issue" in promise_joined
    assert "special-statute or offence source" in promise_joined
    assert "BNSS/CrPC procedure source" in promise_joined
    assert "do not" not in promise_joined.lower() or "ordinary bail advice" in promise_joined
    assert "[21]" in promise_joined and "[22]" in promise_joined

    cattle_q = "police filed cow slaughter cattle case against me false what bail route"
    cattle_joined = " ".join(_grounded_template_lines(cattle_q, route_matter(cattle_q), [
        {"index": 23, "title": "Uttar Pradesh Prevention of Cow Slaughter Act 1955", "anchor": "up-cow-slaughter-1955/sec-3"},
        {"index": 24, "title": "Bharatiya Nagarik Suraksha Sanhita 2023", "anchor": "bnss-2023/sec-480"},
    ]))
    assert "state cattle-preservation accused-procedure issue" in cattle_joined
    assert "FIR/complaint" in cattle_joined
    assert "trial court, Special Court, High Court, or legal-aid route" in cattle_joined
    assert "[23]" in cattle_joined and "[24]" in cattle_joined


def test_stage5_criminal_authority_ledger_handles_common_bail_variants():
    from apps.api.main import _grounded_template_lines
    from apps.api.matter_router import route_matter

    cases = [
        (
            "need help, my son 19 yrs first time offender 379 theft how to get bail magistrate court what next",
            [
                {"index": 1, "title": "Bharatiya Nagarik Suraksha Sanhita 2023", "anchor": "bnss-2023/sec-480@2024-07-01"},
                {"index": 2, "title": "Indian Penal Code 1860", "anchor": "ipc-1860/sec-379"},
            ],
            ("Regular bail for first-time accused", "Magistrate/trial court", "first-time accused facts", "[1]"),
        ),
        (
            "need help, uncle bail granted but cant pay surety 50000 what to do poor family what next",
            [
                {"index": 3, "title": "Bharatiya Nagarik Suraksha Sanhita 2023", "anchor": "bnss-2023/sec-483@2024-07-01"},
                {"index": 4, "title": "Moti Ram versus State of Madhya Pradesh", "anchor": "sc-1978-moti-ram"},
            ],
            ("bail-condition modification", "Rs.50,000", "reduced surety", "same bail court", "[3]"),
        ),
        (
            "need help, anticipatory bail rejected can same be filed again same court what next",
            [
                {"index": 5, "title": "Bharatiya Nagarik Suraksha Sanhita 2023", "anchor": "bnss-2023/sec-482@2024-07-01"},
                {"index": 6, "title": "Constitution of India", "anchor": "constitution-of-india/sec-21"},
            ],
            ("Successive anticipatory-bail application", "changed circumstances", "rejection order", "[5]"),
        ),
        (
            "need help, anticipatory bail in dowry case husband family how many days valid after grant what next",
            [
                {"index": 7, "title": "Bharatiya Nagarik Suraksha Sanhita 2023", "anchor": "bnss-2023/sec-482@2024-07-01"},
                {"index": 8, "title": "Bharatiya Nyaya Sanhita 2023", "anchor": "bns-2023/sec-85"},
            ],
            ("Anticipatory-bail duration", "Do not use a generic number of days", "read the bail order", "[7]"),
        ),
        (
            "need help, ed pmla raid summons husband can ask anticipatory bail before arrest what next",
            [
                {"index": 9, "title": "Prevention of Money Laundering Act 2002", "anchor": "pmla-2002/sec-45"},
                {"index": 10, "title": "Bharatiya Nagarik Suraksha Sanhita 2023", "anchor": "bnss-2023/sec-482@2024-07-01"},
            ],
            ("PMLA/ED pre-arrest bail", "PMLA-specific pre-arrest", "ED summons/raid", "[9]"),
        ),
        (
            "need help, brother in jail 60 days completed maharashtra mcoca what is custody limit chargesheet what next",
            [
                {"index": 11, "title": "Bharatiya Nagarik Suraksha Sanhita 2023", "anchor": "bnss-2023/sec-187@2024-07-01"},
                {"index": 12, "title": "Prisons Act 1894", "anchor": "prisons-1894/sec-31"},
            ],
            ("Default-bail / no-charge-sheet custody calculation", "MCOCA extension application/order", "ordinary 60/90-day", "[11]"),
        ),
        (
            "urgent interim bail when can I apply between regular bail hearings how to complain",
            [
                {"index": 13, "title": "Bharatiya Nagarik Suraksha Sanhita 2023", "anchor": "bnss-2023/sec-480@2024-07-01"},
            ],
            ("Interim bail between regular-bail hearings", "short-date relief", "pending bail application", "[13]"),
        ),
        (
            "please help I shared my ex girlfriend's photo angry on whatsapp group not nude just normal selfie now she filed 67 case any remedy",
            [
                {"index": 14, "title": "Information Technology Act 2000", "anchor": "it-act-2000/sec-67"},
                {"index": 15, "title": "Bharatiya Nagarik Suraksha Sanhita 2023", "anchor": "bnss-2023/sec-216@2024-07-01"},
            ],
            ("IT Act 67 complaint over non-nude photo", "obscene/sexual electronic material", "normal selfie", "[14]"),
        ),
    ]

    for query, passages, expected in cases:
        joined = " ".join(_grounded_template_lines(query, route_matter(query), passages))
        for needle in expected:
            assert needle in joined, (query, needle, joined)


def test_stage5_criminal_authority_ledger_requires_controlling_sources():
    from apps.api.main import _grounded_template_lines
    from apps.api.matter_router import route_matter

    pmla_q = "need help, ed pmla raid summons husband can ask anticipatory bail before arrest what next"
    pmla_without_pmla = " ".join(_grounded_template_lines(pmla_q, route_matter(pmla_q), [
        {"index": 1, "title": "Bharatiya Nagarik Suraksha Sanhita 2023", "anchor": "bnss-2023/sec-482@2024-07-01"},
    ]))
    assert "PMLA/ED pre-arrest bail" not in pmla_without_pmla
    assert "PMLA-specific pre-arrest" not in pmla_without_pmla

    regular_q = "need help, my son 19 yrs first time offender 379 theft how to get bail magistrate court what next"
    regular_without_bail_source = " ".join(_grounded_template_lines(regular_q, route_matter(regular_q), [
        {"index": 2, "title": "Indian Penal Code 1860", "anchor": "ipc-1860/sec-379"},
    ]))
    assert "Regular bail for first-time accused" not in regular_without_bail_source

    granted_q = "anticipatory bail granted 30 day bombay HC police still threatening to arrest"
    granted_with_stray_pmla_source = " ".join(_grounded_template_lines(granted_q, route_matter(granted_q), [
        {"index": 3, "title": "Prevention of Money Laundering Act 2002", "anchor": "pmla-2002/sec-45"},
        {"index": 4, "title": "Bharatiya Nagarik Suraksha Sanhita 2023", "anchor": "bnss-2023/sec-482@2024-07-01"},
    ]))
    assert "PMLA/ED pre-arrest bail" not in granted_with_stray_pmla_source
    assert "PMLA-specific pre-arrest" not in granted_with_stray_pmla_source


def test_stage5_authority_repair_templates_do_not_substitute_adjacent_law():
    from apps.api.main import _grounded_template_lines
    from apps.api.matter_router import route_matter

    labour_q = "delhi labour chowk police picking us morning saying nautanki begging not work how to stop"
    labour = " ".join(_grounded_template_lines(labour_q, route_matter(labour_q), [
        {"index": 1, "title": "Bharatiya Nagarik Suraksha Sanhita 2023", "anchor": "bnss-2023/sec-47"},
        {"index": 2, "title": "Constitution of India", "anchor": "constitution-india/sec-22"},
        {"index": 3, "title": "Inter-State Migrant Workmen (Regulation of Employment and Conditions of Service) Act 1979", "anchor": "ismw-1979/sec-12"},
        {"index": 9, "title": "Bharatiya Nyaya Sanhita 2023", "anchor": "bns-2023/sec-351"},
    ]))
    assert "Delhi labour chowk" in labour
    assert "station diary/FIR/DD entry" in labour
    assert "BNS coercion/intimidation" in labour
    assert "exact Delhi begging-law source" in labour
    assert "quashing petition" not in labour.lower()
    assert "high court quashing" not in labour.lower()

    sarna_q = "mob attacked our pahan during sarna puja calling adivasi non hindu jharkhand"
    sarna = " ".join(_grounded_template_lines(sarna_q, route_matter(sarna_q), [
        {"index": 4, "title": "Scheduled Castes and Scheduled Tribes (Prevention of Atrocities) Act 1989", "anchor": "sc-st-poa-1989/sec-3"},
        {"index": 5, "title": "Bharatiya Nyaya Sanhita 2023", "anchor": "bns-2023/sec-298"},
        {"index": 6, "title": "Bharatiya Nagarik Suraksha Sanhita 2023", "anchor": "bnss-2023/sec-173"},
    ]))
    assert "Sarna/pahan/puja" in sarna
    assert "BNS religious-feelings" in sarna
    assert "[5]" in sarna

    school_q = "girl beaten in school by teacher calling caste name principal not acting maharashtra"
    school = " ".join(_grounded_template_lines(school_q, route_matter(school_q), [
        {"index": 7, "title": "Scheduled Castes and Scheduled Tribes (Prevention of Atrocities) Act 1989", "anchor": "sc-st-poa-1989/sec-3"},
        {"index": 8, "title": "Right of Children to Free and Compulsory Education Act 2009", "anchor": "rte-2009/sec-17"},
    ]))
    assert "RTE school physical-punishment/mental-harassment" in school
    assert "RTE plus POA route" in school
    assert "[8]" in school


def test_fake_whatsapp_sim_harassment_template_avoids_cyber_terrorism_drift():
    from apps.api.main import _grounded_template_lines
    from apps.api.matter_router import route_matter

    q = "ex husband created fake whatsapp using my new sim number harassing my family"
    answer = " ".join(_grounded_template_lines(q, route_matter(q), [
        {"index": 1, "title": "Telecommunications Act 2023", "anchor": "telecommunications-2023/sec-42"},
        {"index": 2, "title": "Information Technology Act 2000", "anchor": "it-2000/sec-66C"},
        {"index": 3, "title": "Information Technology Act 2000", "anchor": "it-2000/sec-66D"},
        {"index": 4, "title": "Bharatiya Nyaya Sanhita 2023", "anchor": "bns-2023/sec-78"},
        {"index": 5, "title": "Bharatiya Nagarik Suraksha Sanhita 2023", "anchor": "bnss-2023/sec-173"},
    ]))

    assert "fake WhatsApp account" in answer
    assert "new SIM/mobile number" in answer
    assert "IT Act identity-theft" in answer
    assert "cheating-by-personation" in answer
    assert "BNS track" in answer
    assert "Telecommunications Act" in answer
    assert "cyber terrorism" not in answer.lower()
    assert "66F" not in answer


def test_accused_scst_false_poa_template_is_specific_to_defence_route():
    from apps.api.main import _grounded_template_lines
    from apps.api.matter_router import route_matter

    q = "can u tell they accused me of stealing chickens from upper caste house false POA case put on them godda what can i do"
    answer = " ".join(_grounded_template_lines(q, route_matter(q), [
        {"index": 1, "title": "Scheduled Castes and Scheduled Tribes (Prevention of Atrocities) Act 1989", "anchor": "sc-st-poa-1989/sec-18"},
        {"index": 2, "title": "Bharatiya Nagarik Suraksha Sanhita 2023", "anchor": "bnss-2023/sec-483"},
        {"index": 3, "title": "Bharatiya Nyaya Sanhita 2023", "anchor": "bns-2023/sec-317"},
    ]))

    assert "accused-side SC/ST POA false-case claim" in answer
    assert "stealing chickens" in answer
    assert "POA bar and prima-facie facts" in answer
    assert "do not contact or pressure the complainant" in answer
    assert "Special source to verify first" not in answer


def test_public_political_deepfake_uses_public_authorities_before_private_image_track():
    from apps.api.main import _grounded_template_lines
    from apps.api.matter_router import route_matter

    query = "deepfake of modi pm circulating my friend made it bjp it cell threatening"
    joined = " ".join(_grounded_template_lines(query, route_matter(query), [
        {"index": 1, "title": "Representation of the People Act 1951", "anchor": "rpa-1951/sec-123"},
        {"index": 2, "title": "Bharatiya Nyaya Sanhita 2023", "anchor": "bns-2023/sec-356"},
        {"index": 3, "title": "Information Technology Act 2000", "anchor": "it-2000/sec-66D"},
        {"index": 4, "title": "Bharatiya Nagarik Suraksha Sanhita 2023", "anchor": "bnss-2023/sec-216"},
    ]))
    assert "public-political deepfake" in joined
    assert "Representation of the People Act source" in joined
    assert "not as private-image sextortion" in joined
    assert "[1]" in joined


def test_stage5_scenario_contracts_preserve_real_user_facts():
    from apps.api.main import _grounded_template_lines
    from apps.api.matter_router import route_matter

    esi_q = "what to do esic card not issued even after 2 years cutting from salary went hospital they refused"
    esi = " ".join(_grounded_template_lines(esi_q, route_matter(esi_q), [
        {"index": 1, "title": "Employees' State Insurance Act 1948", "anchor": "esi-1948/sec-56"},
        {"index": 2, "title": "Employees' State Insurance Act 1948", "anchor": "esi-1948/sec-40"},
    ]))
    assert "ESIC card not issued" in esi
    assert "two years of salary deductions" in esi
    assert "not as an ordinary consumer refund case" in esi
    assert "grievance number" in esi

    epf_q = "what to do epf number lost left job hyderabad 2019 want to withdraw money 60000 stuck"
    epf = " ".join(_grounded_template_lines(epf_q, route_matter(epf_q), [
        {"index": 3, "title": "Employees' Provident Funds and Miscellaneous Provisions Act 1952", "anchor": "epf-1952/sec-14"},
    ]))
    assert "Rs. 60000" in epf
    assert "Hyderabad job in 2019" in epf
    assert "provident-fund default/claim-correction" in epf

    retrench_q = "what to do construction company retrenched 40 of us bengali workers kept the gujaratis next day same site"
    retrench = " ".join(_grounded_template_lines(retrench_q, route_matter(retrench_q), [
        {"index": 4, "title": "Industrial Disputes Act 1947", "anchor": "industrial-disputes-1947/sec-25G"},
        {"index": 5, "title": "Constitution of India", "anchor": "constitution-india/sec-14"},
    ]))
    assert "40 Bengali workers" in retrench
    assert "Gujaratis" in retrench
    assert "Labour Commissioner" in retrench

    poa_q = "can u tell special court POA case pending 5 years no judgement aurangabad maharashtra what can i do"
    poa = " ".join(_grounded_template_lines(poa_q, route_matter(poa_q), [
        {"index": 6, "title": "Scheduled Castes and Scheduled Tribes (Prevention of Atrocities) Act 1989", "anchor": "sc-st-poa-1989/sec-14"},
        {"index": 7, "title": "Scheduled Castes and Scheduled Tribes (Prevention of Atrocities) Act 1989", "anchor": "sc-st-poa-1989/sec-15A"},
    ]))
    assert "Aurangabad, Maharashtra Special Court" in poa
    assert "5-year delay with no judgement" in poa
    assert "SC/ST victim papers" in poa


def test_stage5_criminal_scenario_contracts_cover_regional_slur_and_tinder_phone():
    from apps.api.main import _grounded_template_lines
    from apps.api.matter_router import route_matter

    slur_q = "what to do biharee called we are by site engineer pune always after wage complain is this crime"
    slur = " ".join(_grounded_template_lines(slur_q, route_matter(slur_q), [
        {"index": 1, "title": "Bharatiya Nyaya Sanhita 2023", "anchor": "bns-2023/sec-352"},
        {"index": 2, "title": "Code on Wages 2019", "anchor": "code-on-wages-2019/sec-45"},
        {"index": 3, "title": "Bharatiya Nagarik Suraksha Sanhita 2023", "anchor": "bnss-2023/sec-173"},
    ]))
    assert "Being called 'Biharee'" in slur
    assert "wage complaint at the worksite" in slur
    assert "Labour Commissioner/wage authority" in slur

    tinder_q = "tinder match wala extortion gang met in bandra hotel took my phone"
    tinder = " ".join(_grounded_template_lines(tinder_q, route_matter(tinder_q), [
        {"index": 4, "title": "Bharatiya Nyaya Sanhita 2023", "anchor": "bns-2023/sec-308"},
        {"index": 5, "title": "Bharatiya Nyaya Sanhita 2023", "anchor": "bns-2023/sec-309"},
        {"index": 6, "title": "Information Technology Act 2000", "anchor": "it-2000/sec-66D"},
    ]))
    assert "Bandra hotel" in tinder
    assert "took your phone" in tinder
    assert "robbery/theft-force track" in tinder
    assert "phone IMEI/device details" in tinder


def test_medical_custody_template_preserves_urgency_and_forum():
    from apps.api.main import _grounded_template_lines
    from apps.api.matter_router import route_matter

    q = "pregnant woman undertrial byculla not getting hospital checkup"
    joined = " ".join(_grounded_template_lines(q, route_matter(q), [
        {"index": 1, "title": "Constitution of India", "anchor": "constitution-india/sec-21"},
        {"index": 2, "title": "Bharatiya Nagarik Suraksha Sanhita 2023", "anchor": "bnss-2023/sec-480"},
    ]))

    assert "urgent custody medical-care issue" in joined
    assert "pregnancy hospital checkup" in joined
    assert "medical status report" in joined
    assert "trial court" in joined or "Sessions Court" in joined


def test_stage5_criminal_existing_templates_are_variant_specific():
    from apps.api.main import _grounded_template_lines
    from apps.api.matter_router import route_matter

    juvenile_q = "need help, 16 yr boy detained adult jail 2 weeks already how to transfer observation home what next"
    juvenile_joined = " ".join(_grounded_template_lines(juvenile_q, route_matter(juvenile_q), [
        {
            "index": 1,
            "title": "Juvenile Justice (Care and Protection of Children) Act 2015",
            "anchor": "jj-2015/sec-9",
            "text": "claims before a court other than a Board determine the age",
        },
        {
            "index": 2,
            "title": "Juvenile Justice (Care and Protection of Children) Act 2015",
            "anchor": "jj-2015/sec-94",
            "text": "age determination date of birth certificate from the school",
        },
        {
            "index": 3,
            "title": "Juvenile Justice (Care and Protection of Children) Act 2015",
            "anchor": "jj-2015/sec-12",
            "text": "apparently a child released on bail",
        },
        {
            "index": 4,
            "title": "Juvenile Justice (Care and Protection of Children) Act 2015",
            "anchor": "jj-2015/sec-10",
            "text": "police lockup lodged in a jail",
        },
    ]))
    assert "transfer to the Juvenile Justice Board/observation-home route" in juvenile_joined
    assert "observation-home/place-of-safety" in juvenile_joined

    medical_q = "need help, paralegal volunteer 4 women undertrials byculla pregnant where rule postpone trial bail what next"
    medical_joined = " ".join(_grounded_template_lines(medical_q, route_matter(medical_q), [
        {"index": 5, "title": "Constitution of India", "anchor": "constitution-of-india/sec-21"},
        {
            "index": 6,
            "title": "Bharatiya Nagarik Suraksha Sanhita 2023",
            "anchor": "bnss-2023/sec-480@2024-07-01",
            "text": "Court may release an accused person on bail if such person is a woman or is sick or infirm.",
        },
    ]))
    assert "pregnant women undertrials" in medical_joined
    assert "medical status report" in medical_joined
    assert "hospital examination" in medical_joined

    ndps_q = "need help, brother arrested NDPS 50 gram heroin commercial or not bail chances what next"
    ndps_joined = " ".join(_grounded_template_lines(ndps_q, route_matter(ndps_q), [
        {"index": 7, "title": "Narcotic Drugs and Psychotropic Substances Act 1985", "anchor": "ndps-1985/sec-2"},
        {"index": 8, "title": "Narcotic Drugs and Psychotropic Substances Act 1985", "anchor": "ndps-1985/sec-37"},
        {"index": 9, "title": "Narcotic Drugs and Psychotropic Substances Act 1985", "anchor": "ndps-1985/sec-36A"},
        {"index": 10, "title": "Bharatiya Nagarik Suraksha Sanhita 2023", "anchor": "bnss-2023/sec-483@2024-07-01"},
    ]))
    assert "heroin and 50 gram" in ndps_joined
    assert "small, intermediate, or commercial quantity" in ndps_joined
    assert "Section 37 filter" in ndps_joined
    assert "Special NDPS Court" in ndps_joined


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
        {"index": 1, "title": "Delhi Prison Rules 2018", "anchor": "delhi-prison-rules-2018/rule-613-616"},
        {"index": 2, "title": "Prisons Act 1894", "anchor": "prisons-1894/sec-59"},
        {"index": 3, "title": "Constitution of India", "anchor": "constitution-india/sec-21"},
    ]))
    assert "mulaqat" in prison_joined
    assert "Jail Superintendent" in prison_joined
    assert "half-hour" in prison_joined
    assert "[1]" in prison_joined and "[3]" in prison_joined

    prison_books_q = "son in tihar can he get books from family during prison rules"
    prison_books_joined = " ".join(_grounded_template_lines(prison_books_q, route_matter(prison_books_q), [
        {"index": 4, "title": "Delhi Prison Rules 2018", "anchor": "delhi-prison-rules-2018/rule-619-1029-books"},
        {"index": 5, "title": "Prisons Act 1894", "anchor": "prisons-1894/sec-59"},
    ]))
    assert "permitted-item route" in prison_books_joined
    assert "book titles" in prison_books_joined
    assert "[4]" in prison_books_joined

    parole_q = "uncle in tihar jail 4 yrs murder case eligible for parole 15 days delhi"
    parole_joined = " ".join(_grounded_template_lines(parole_q, route_matter(parole_q), [
        {"index": 6, "title": "Delhi Prison Rules 2018", "anchor": "delhi-prison-rules-2018/rule-1210-1217"},
        {"index": 7, "title": "Constitution of India", "anchor": "constitution-india/sec-21"},
    ]))
    assert "Delhi Prison Rules" in parole_joined
    assert "Jail Superintendent" in parole_joined
    assert "written order and reasons" in parole_joined
    assert "[6]" in parole_joined

    custody_parole_q = "brother in rohini jail wants custody parole for mother's funeral what application route"
    custody_parole_joined = " ".join(_grounded_template_lines(custody_parole_q, route_matter(custody_parole_q), [
        {"index": 8, "title": "Delhi Prison Rules 2018", "anchor": "delhi-prison-rules-2018/rule-1210-1217"},
        {"index": 9, "title": "Prisons Act 1894", "anchor": "prisons-1894/sec-59"},
    ]))
    assert "custody parole" in custody_parole_joined
    assert "Jail Superintendent" in custody_parole_joined
    assert "ordinary bail" in custody_parole_joined
    assert "domestic violence" in custody_parole_joined
    assert "[8]" in custody_parole_joined

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

    dpdp_q = "data breach my dpdp rights kya hain after dunzo leaked my address"
    dpdp_joined = " ".join(_grounded_template_lines(dpdp_q, route_matter(dpdp_q), [
        {"index": 1, "title": "Digital Personal Data Protection Act 2023", "anchor": "dpdp-2023/sec-8-a"},
        {"index": 2, "title": "Digital Personal Data Protection Act 2023", "anchor": "dpdp-2023/sec-13"},
        {"index": 3, "title": "Digital Personal Data Protection Act 2023", "anchor": "dpdp-2023/sec-27"},
        {"index": 4, "title": "Information Technology Act 2000", "anchor": "it-2000/sec-66E"},
    ]))
    assert "Dunzo leaking your address" in dpdp_joined
    assert "DPDP personal-data breach/grievance issue" in dpdp_joined
    assert "not as a deepfake" in dpdp_joined
    assert "Data Principal must exhaust" in dpdp_joined
    assert "[1]" in dpdp_joined and "[2]" in dpdp_joined and "[3]" in dpdp_joined

    instagram_defamation_q = "instagram comments calling me randi defamation kya kar sakti hu"
    instagram_defamation_joined = " ".join(_grounded_template_lines(instagram_defamation_q, route_matter(instagram_defamation_q), [
        {"index": 1, "title": "Information Technology Act 2000", "anchor": "it-2000/sec-66E"},
        {"index": 2, "title": "Information Technology Act 2000", "anchor": "it-2000/sec-67"},
        {"index": 3, "title": "Bharatiya Nyaya Sanhita 2023", "anchor": "bns-2023/sec-356-a"},
        {"index": 4, "title": "Bharatiya Nagarik Suraksha Sanhita 2023", "anchor": "bnss-2023/sec-216"},
    ]))
    assert "Instagram comments calling you 'randi'" in instagram_defamation_joined
    assert "online abuse/possible defamation" in instagram_defamation_joined
    assert "not as a deepfake or private-image complaint" in instagram_defamation_joined
    assert "only if the actual post or comment is obscene electronic material" in instagram_defamation_joined
    assert "[3]" in instagram_defamation_joined

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

    csam_no_67b_joined = " ".join(_grounded_template_lines(csam_q, route_matter(csam_q), [
        {"index": 1, "title": "Protection of Children from Sexual Offences Act 2012", "anchor": "pocso-2012/sec-13"},
        {"index": 2, "title": "Information Technology Act 2000", "anchor": "it-2000/sec-67A", "text": "Adjacent material mentions section 67B and children in a later heading."},
        {"index": 3, "title": "Bharatiya Nyaya Sanhita 2023", "anchor": "bns-2023/sec-356"},
    ]))
    assert "POCSO" in csam_no_67b_joined
    assert "IT Act child sexually-explicit material source" not in csam_no_67b_joined
    assert "[2]" not in csam_no_67b_joined

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
    assert "IT Act" in adult_joined or "non-consensual" in adult_joined or "deepfake" in adult_joined.lower()
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


def test_grounded_juvenile_overnight_with_adults_is_urgent_jjb_transfer():
    from apps.api.main import _grounded_template_lines
    from apps.api.matter_router import route_matter

    q = "police picked my 16 year old nephew and kept him overnight with adults, school certificate shows date of birth"
    joined = " ".join(_grounded_template_lines(q, route_matter(q), [
        {
            "index": 1,
            "title": "Juvenile Justice (Care and Protection of Children) Act 2015",
            "anchor": "jj-2015/sec-10",
            "text": "in no case shall a child alleged to be in conflict with law be placed in a police lockup or lodged in a jail",
        },
        {
            "index": 2,
            "title": "Juvenile Justice (Care and Protection of Children) Act 2015",
            "anchor": "jj-2015/sec-94",
            "text": "age determination date of birth certificate from the school",
        },
        {
            "index": 3,
            "title": "Juvenile Justice (Care and Protection of Children) Act 2015",
            "anchor": "jj-2015/sec-9",
            "text": "claims before a court other than a Board determine the age",
        },
        {
            "index": 4,
            "title": "Juvenile Justice (Care and Protection of Children) Act 2015",
            "anchor": "jj-2015/sec-4",
            "text": "deal exclusively children in conflict with law",
        },
    ]))

    assert "your 16-year-old nephew" in joined
    assert "overnight in police custody" in joined
    assert "production before the Juvenile Justice Board" in joined
    assert "observation-home/place-of-safety" in joined
    assert "DLSA" in joined
    assert "same day" in joined
    assert "FIR/remand/custody details" in joined


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
                {"index": 20, "title": "Code on Wages 2019", "anchor": "code-on-wages-2019/sec-17"},
            ],
            ("not automatically a labour-court claim", "[18]", "Section 25F", "[19]", "Code on Wages", "[20]", "HR complaint", "PIP"),
        ),
        (
            "my company put me on performance improvement plan for missing targets no harassment issue what are my rights",
            [
                {"index": 21, "title": "Industrial Disputes Act 1947", "anchor": "industrial-disputes-1947/sec-25F"},
                {"index": 22, "title": "Code on Wages 2019", "anchor": "code-on-wages-2019/sec-45"},
            ],
            ("ordinary PIP", "[21]", "not automatically illegal", "Code on Wages", "[22]", "not use the Code on Wages as the PIP answer"),
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
            _rbi_ombudsman_sources(10),
            ("RBI Ombudsman/CMS", "[10]", "regulated entities", "statement entry", "[14]"),
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
                {"index": 17, "title": "Right to Information Act 2005", "anchor": "rti-2005/sec-6"},
            ],
            ("ration-card cancellation or Aadhaar mismatch", "[14]", "RTI as the record-status support route", "[17]", "Aadhaar Act", "[16]", "BDO/office reply"),
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
        SimpleNamespace(title="Mental Healthcare Act 2017", anchor="mental-healthcare-2017/sec-113"),
        SimpleNamespace(title="Sexual Harassment of Women at Workplace (Prevention, Prohibition and Redressal) Act 2013", anchor="posh-2013/sec-9"),
        SimpleNamespace(title="Industrial Disputes Act 1947", anchor="industrial-disputes-1947/sec-2A"),
        SimpleNamespace(title="Industrial Disputes Act 1947", anchor="industrial-disputes-1947/sec-25F"),
        SimpleNamespace(title="Code on Wages 2019", anchor="code-on-wages-2019/sec-17"),
    ]

    filtered = _prompt_retrieval_candidates(query, route, chunks)

    assert [chunk.title for chunk in filtered] == [
        "Sexual Harassment of Women at Workplace (Prevention, Prohibition and Redressal) Act 2013",
        "Industrial Disputes Act 1947",
        "Industrial Disputes Act 1947",
        "Code on Wages 2019",
    ]


def test_stage_500_real_run_blocker_templates_are_specific():
    from apps.api.main import _grounded_template_lines
    from apps.api.matter_router import route_matter

    cases = [
        (
            "vendor at my office sends me whatsapp emojis and asks for date I told him no but he keeps coming to my floor",
            [
                {"index": 1, "title": "Sexual Harassment of Women at Workplace Act 2013", "anchor": "posh-2013/sec-9"},
                {"index": 2, "title": "Sexual Harassment of Women at Workplace Act 2013", "anchor": "posh-2013/sec-19"},
                {"index": 3, "title": "Sexual Harassment of Women at Workplace Act 2013", "anchor": "posh-2013/sec-3"},
            ],
            ("vendor/third-party", "not as a colleague-only dispute", "Internal Committee or Local Committee", "access restriction"),
        ),
        (
            "father custodial death lockup byculla police saying suicide what is 196 procedure",
            [
                {"index": 4, "title": "Bharatiya Nagarik Suraksha Sanhita 2023", "anchor": "bnss-2023/sec-196"},
                {"index": 5, "title": "Protection of Human Rights Act 1993", "anchor": "protection-human-rights-1993/sec-12"},
            ],
            ("father's police lockup death", "NHRC/State Human Rights Commission", "post-mortem", "[4]", "[5]"),
        ),
        (
            "wrong delivery by Uber Eats gave me food poisoning hospital bill what can I do",
            [
                {"index": 6, "title": "Consumer Protection Act 2019", "anchor": "consumer-protection-2019/sec-35"},
                {"index": 7, "title": "Food Safety and Standards Act 2006", "anchor": "food-safety-standards-2006/sec-26"},
                {"index": 8, "title": "Consumer Protection Act 2019", "anchor": "consumer-protection-2019/sec-39"},
            ],
            ("food poisoning", "Consumer Protection Act", "Food Safety and Standards Act", "hospital bill", "[6]", "[7]"),
        ),
        (
            "factory closed sudden 80 of us tamil migrant no notice 2 months salary pending tiruppur",
            [
                {"index": 9, "title": "Industrial Disputes Act 1947", "anchor": "industrial-disputes-1947/sec-25FFA"},
                {"index": 10, "title": "Industrial Disputes Act 1947", "anchor": "industrial-disputes-1947/sec-25F"},
                {"index": 11, "title": "Code on Wages 2019", "anchor": "code-on-wages-2019/sec-17"},
            ],
            ("sudden factory closure", "Industrial Disputes Act", "notice wages or retrenchment/closure compensation", "Code on Wages", "two-month arrears", "[9]", "[11]"),
        ),
        (
            "contractor took rs 30 daily for food gave gruel only deducted from wages legal or not",
            [
                {"index": 12, "title": "Code on Wages 2019", "anchor": "code-on-wages-2019/sec-18"},
                {"index": 13, "title": "Inter-State Migrant Workmen (Regulation of Employment and Conditions of Service) Act 1979", "anchor": "ismw-1979/sec-12"},
            ],
            ("Daily food money taken from wages", "gruel", "ISMW contractor-duty", "daily deduction amount", "[12]", "[13]"),
        ),
        (
            "urban company beautician 3 strike system unfair termination labour law",
            [
                {"index": 14, "title": "Code on Social Security 2020", "anchor": "social-security-code-2020/sec-113"},
                {"index": 15, "title": "Industrial Disputes Act 1947", "anchor": "industrial-disputes-1947/sec-2-f"},
                {"index": 16, "title": "Industrial Disputes Act 1947", "anchor": "industrial-disputes-1947/sec-25F-b"},
            ],
            ("Urban Company", "Code on Social Security", "Industrial Disputes Act", "employee/workman status", "[14]", "[16]"),
        ),
    ]

    for query, passages, expected_parts in cases:
        joined = " ".join(_grounded_template_lines(query, route_matter(query), passages))
        assert joined, query
        for part in expected_parts:
            assert part in joined, (query, part, joined)


def test_stage_500_generic_hr_harassment_pip_keeps_posh_conditional():
    from apps.api.main import _grounded_template_lines
    from apps.api.matter_router import route_matter

    q = "i complained against my manager for harassment to HR and now they are putting me on PIP, is this retaliation"
    passages = [
        {"index": 1, "title": "Industrial Disputes Act 1947", "anchor": "industrial-disputes-1947/sec-2A"},
        {"index": 2, "title": "Sexual Harassment of Women at Workplace Act 2013", "anchor": "posh-2013/sec-9"},
        {"index": 3, "title": "Code on Wages 2019", "anchor": "code-on-wages-2019/sec-17"},
    ]

    joined = " ".join(_grounded_template_lines(q, route_matter(q), passages))

    assert "not automatically a labour-court claim" in joined
    assert "If the harassment complaint was about sexual or gendered workplace conduct" in joined
    assert "Internal Committee/Local Committee" in joined
    assert "[1]" in joined and "[2]" in joined


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
    assert names == ["matter_route", "matter_plan", "error", "timing"]
    route_payload = next(d for ev, d in events if ev == "matter_route")
    assert route_payload["category"] == "police_fir"
    plan_payload = next(d for ev, d in events if ev == "matter_plan")
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


def test_stage_500_recovery_handcuff_template_is_specific():
    from apps.api.main import _grounded_template_lines
    from apps.api.matter_router import route_matter

    q = "brother in handcuffs taken to court hearing is this legal high security prisoner"
    passages = [
        {"index": 1, "title": "Constitution of India", "anchor": "constitution-india/sec-21"},
        {"index": 2, "title": "Constitution of India", "anchor": "constitution-india/sec-22"},
        {"index": 3, "title": "Bharatiya Nagarik Suraksha Sanhita 2023", "anchor": "bnss-2023/sec-58"},
    ]

    joined = " ".join(_grounded_template_lines(q, route_matter(q), passages))

    assert "handcuff" in joined.lower()
    assert "custody-liberty" in joined
    assert "Magistrate" in joined
    assert "[1]" in joined or "[2]" in joined


def test_habeas_template_cites_article_226_and_production_safeguards():
    from apps.api.main import _grounded_template_lines
    from apps.api.matter_router import route_matter

    q = "urgent how to file habeas corpus petition husband detained illegally by police how to complain"
    passages = [
        {"index": 1, "title": "Constitution of India", "anchor": "constitution-india/sec-21"},
        {"index": 2, "title": "Constitution of India", "anchor": "constitution-india/sec-226"},
        {"index": 3, "title": "Constitution of India", "anchor": "constitution-india/sec-22"},
        {"index": 4, "title": "Bharatiya Nagarik Suraksha Sanhita 2023", "anchor": "bnss-2023/sec-58"},
    ]

    joined = " ".join(_grounded_template_lines(q, route_matter(q), passages))

    assert "Article 226" in joined
    assert "habeas corpus" in joined
    assert "Magistrate" in joined
    assert "[2]" in joined
    assert "[4]" in joined


def test_stage_500_recovery_company_restore_uses_company_template_before_ibc():
    from apps.api.main import _grounded_template_lines
    from apps.api.matter_router import route_matter

    q = "company struck off by roc want to restore for bank operations and gst refund chennai"
    passages = [
        {"index": 1, "title": "Companies Act 2013", "anchor": "companies-2013/sec-92"},
        {"index": 2, "title": "Insolvency and Bankruptcy Code 2016", "anchor": "ibc-2016/sec-8"},
        {"index": 3, "title": "Companies Act 2013", "anchor": "companies-2013/sec-252-d"},
    ]

    joined = " ".join(_grounded_template_lines(q, route_matter(q), passages))

    assert "company struck off by ROC" in joined
    assert "Companies Act restoration" in joined
    assert "operational creditor" not in joined


def test_stage_500_recovery_company_filing_disqualification_not_restoration_first():
    from apps.api.main import _grounded_template_lines
    from apps.api.matter_router import route_matter

    q = "private limited not filed mgt7 aoc4 for 3 years can director be disqualified and company revive"
    passages = [
        {"index": 1, "title": "Companies Act 2013", "anchor": "companies-2013/sec-92"},
        {"index": 2, "title": "Companies Act 2013", "anchor": "companies-2013/sec-137"},
        {"index": 3, "title": "Companies Act 2013", "anchor": "companies-2013/sec-164"},
        {"index": 4, "title": "Companies Act 2013", "anchor": "companies-2013/sec-252-d"},
        {"index": 5, "title": "Insolvency and Bankruptcy Code 2016", "anchor": "ibc-2016/sec-8"},
    ]

    joined = " ".join(_grounded_template_lines(q, route_matter(q), passages))

    assert "MCA/ROC annual-filing default" in joined
    assert "director-disqualification risk" in joined
    assert "restoration source as a second track" in joined
    assert "GST refund or bank operation" not in joined


def test_stage_500_recovery_company_contract_floor_skips_ibc_after_companies_act():
    from apps.api.main import _should_skip_contract_source_line
    from apps.api.matter_router import route_matter

    q = "private limited not filed mgt7 aoc4 for 3 years can director be disqualified and company revive"
    route = route_matter(q)

    assert _should_skip_contract_source_line(route, "ibc_2016", {"companies act 2013"})


def test_stage_500_recovery_labour_wage_template_handles_munshi_migrant_query():
    from apps.api.main import _grounded_template_lines
    from apps.api.matter_router import route_matter

    q = "came from supaul bihar to mumbai 6 months no payment munshi keeps saying next week"
    passages = [
        {"index": 1, "title": "Code on Wages 2019", "anchor": "code-on-wages-2019/sec-17"},
        {"index": 2, "title": "Code on Wages 2019", "anchor": "code-on-wages-2019/sec-45"},
        {"index": 3, "title": "Inter-State Migrant Workmen Act 1979", "anchor": "ismw-1979/sec-12"},
    ]

    joined = " ".join(_grounded_template_lines(q, route_matter(q), passages))

    assert "migrant-worker wage dispute" in joined
    assert "munshi" in joined
    assert "written wage complaint" in joined
    assert "[2]" in joined


def test_stage_500_recovery_legal_aid_template_mentions_arrested_person():
    from apps.api.main import _grounded_template_lines
    from apps.api.matter_router import route_matter

    q = "i am poor brother arrested can court give free lawyer nalsa kya hota hai"
    passages = [
        {"index": 1, "title": "Legal Services Authorities Act 1987", "anchor": "legal-services-authorities-1987/sec-12"},
        {"index": 2, "title": "Legal Services Authorities Act 1987", "anchor": "legal-services-authorities-1987/sec-9"},
        {"index": 3, "title": "Constitution of India", "anchor": "constitution-india/sec-39A"},
    ]

    joined = " ".join(_grounded_template_lines(q, route_matter(q), passages))

    assert "arrested person or prisoner" in joined
    assert "free legal services" in joined
    assert "DLSA" in joined
    assert "arrest, remand, or jail papers" in joined


def test_stage_500_recovery_employment_overtime_uses_wage_template():
    from apps.api.main import _grounded_template_lines
    from apps.api.matter_router import route_matter

    q = "construction site made us work overtime for months and contractor not paying extra wages"
    passages = [
        {"index": 1, "title": "Code on Wages 2019", "anchor": "code-on-wages-2019/sec-17"},
        {"index": 2, "title": "Code on Wages 2019", "anchor": "code-on-wages-2019/sec-45"},
        {"index": 3, "title": "Code on Social Security 2020", "anchor": "social-security-code-2020/sec-114-a"},
    ]

    joined = " ".join(_grounded_template_lines(q, route_matter(q), passages))

    assert "construction-site overtime dispute" in joined
    assert "Code on Wages" in joined
    assert "wage complaint" in joined
    assert "social security" not in joined.lower()


def test_stage_500_recovery_wage_retrieval_filters_social_security_noise():
    from apps.api.main import _prompt_retrieval_candidates
    from apps.api.matter_router import route_matter

    q = "construction site made us work overtime for months and contractor not paying extra wages"
    hits = [
        SimpleNamespace(title="Code on Social Security 2020", anchor="social-security-code-2020/sec-114-a"),
        SimpleNamespace(title="Code on Wages 2019", anchor="code-on-wages-2019/sec-45"),
        SimpleNamespace(title="Industrial Disputes Act 1947", anchor="industrial-disputes-1947/sec-2a"),
    ]

    filtered = _prompt_retrieval_candidates(q, route_matter(q), hits)

    assert [h.title for h in filtered] == ["Code on Wages 2019", "Industrial Disputes Act 1947"]


def test_stage_500_postfix_epf_default_keeps_epf_sources_before_wage_filter():
    from apps.api.main import _grounded_template_lines, _prompt_retrieval_candidates
    from apps.api.matter_router import route_matter

    q = "garment factory tiruppur cuts pf from salary every month epf passbook empty 3 years"
    hits = [
        SimpleNamespace(title="Code on Wages 2019", anchor="code-on-wages-2019/sec-17"),
        SimpleNamespace(title="Employees' Provident Funds and Miscellaneous Provisions Act 1952", anchor="epf-1952/sec-14-a"),
        SimpleNamespace(title="Code on Social Security 2020", anchor="social-security-code-2020/sec-114"),
    ]

    filtered = _prompt_retrieval_candidates(q, route_matter(q), hits)
    assert any("Provident" in h.title for h in filtered)

    passages = [
        {"index": 1, "title": "Code on Wages 2019", "anchor": "code-on-wages-2019/sec-17"},
        {"index": 2, "title": "Employees' Provident Funds and Miscellaneous Provisions Act 1952", "anchor": "epf-1952/sec-14-a"},
        {"index": 3, "title": "Code on Social Security 2020", "anchor": "social-security-code-2020/sec-114"},
    ]
    joined = " ".join(_grounded_template_lines(q, route_matter(q), passages))
    assert "employer contribution-default" in joined
    assert "Regional Provident Fund" in joined


def test_stage_500_postfix_environment_damage_and_migrant_return_templates():
    from apps.api.main import _grounded_template_lines
    from apps.api.matter_router import route_matter

    env_q = "thermal plant blasting cracking our houses no compensation kalahandi"
    env_passages = [
        {"index": 1, "title": "National Green Tribunal Act 2010", "anchor": "ngt-2010/sec-15"},
        {"index": 2, "title": "Environment (Protection) Act 1986", "anchor": "environment-protection-1986/sec-5"},
        {"index": 3, "title": "Water (Prevention and Control of Pollution) Act 1974", "anchor": "water-pollution-1974/sec-17"},
    ]
    env_joined = " ".join(_grounded_template_lines(env_q, route_matter(env_q), env_passages))
    assert "blasting damage to houses" in env_joined
    assert "NGT compensation/restoration" in env_joined
    assert "Pollution Control Board and District Collector" in env_joined

    env_vibration_q = "factory chemicals and vibration damaged our homes no inspection by pollution board"
    env_vibration_passages = [
        {"index": 1, "title": "National Green Tribunal Act 2010", "anchor": "ngt-2010/sec-16"},
        {"index": 2, "title": "Environment (Protection) Act 1986", "anchor": "environment-protection-1986/sec-3"},
        {"index": 3, "title": "Water (Prevention and Control of Pollution) Act 1974", "anchor": "water-pollution-1974/sec-17"},
    ]
    env_vibration_joined = " ".join(
        _grounded_template_lines(env_vibration_q, route_matter(env_vibration_q), env_vibration_passages)
    )
    assert "NGT" in env_vibration_joined or "Water Act" in env_vibration_joined or "pollution" in env_vibration_joined.lower()
    assert "NGT forum source" in env_vibration_joined
    assert "Environment Protection source" in env_vibration_joined

    env_private_smoke_q = "factory smoke damaged only my house wall no public pil just compensation"
    env_private_smoke_joined = " ".join(
        _grounded_template_lines(env_private_smoke_q, route_matter(env_private_smoke_q), env_vibration_passages)
    )
    assert "factory smoke damage to your house wall" in env_private_smoke_joined
    assert "private compensation" in env_private_smoke_joined
    assert "Pollution Control Board" in env_private_smoke_joined
    assert "public PIL" in env_private_smoke_joined

    env_smoke_q = "factory smoke making us sick should i go ngt or high court pil first what proof needed"
    env_smoke_passages = [
        {"index": 1, "title": "Constitution of India", "anchor": "constitution-india/sec-138"},
        {"index": 2, "title": "National Green Tribunal Act 2010", "anchor": "ngt-2010/sec-15"},
        {"index": 3, "title": "Environment (Protection) Act 1986", "anchor": "environment-protection-1986/sec-3"},
        {"index": 4, "title": "Water (Prevention and Control of Pollution) Act 1974", "anchor": "water-pollution-1974/sec-17"},
    ]
    env_smoke_joined = " ".join(
        _grounded_template_lines(env_smoke_q, route_matter(env_smoke_q), env_smoke_passages)
    )
    assert "factory smoke or health-impact facts" in env_smoke_joined
    assert "Environment Protection source" in env_smoke_joined
    assert "Pollution Control Board record" in env_smoke_joined
    assert "High Court PIL/Article 226 route" in env_smoke_joined
    assert "PIL procedure" in env_smoke_joined
    assert "writ-jurisdiction source" not in env_smoke_joined

    env_spcb_q = "industrial smoke allergy ho raha hai kya pehle pollution board complaint ya ngt application karna hai"
    env_spcb_joined = " ".join(
        _grounded_template_lines(env_spcb_q, route_matter(env_spcb_q), env_smoke_passages)
    )
    assert "factory smoke or health-impact facts" in env_spcb_joined
    assert "Pollution Control Board" in env_spcb_joined

    migrant_q = "contractor said go back home pandemic no return ticket money given 9 of us walked from delhi"
    migrant_passages = [
        {"index": 1, "title": "Inter-State Migrant Workmen (Regulation of Employment and Conditions of Service) Act 1979", "anchor": "ismw-1979/sec-15"},
        {"index": 2, "title": "Code on Wages 2019", "anchor": "code-on-wages-2019/sec-45"},
    ]
    migrant_joined = " ".join(_grounded_template_lines(migrant_q, route_matter(migrant_q), migrant_passages))
    assert "return-fare/journey-allowance" in migrant_joined
    assert "walking/return travel" in migrant_joined

    return_fare_q = "thekedar promised return fare from gurgaon to bihar but abandoned 12 workers"
    return_fare_passages = [
        {"index": 1, "title": "Inter-State Migrant Workmen (Regulation of Employment and Conditions of Service) Act 1979", "anchor": "ismw-1979/sec-14"},
        {"index": 2, "title": "Inter-State Migrant Workmen (Regulation of Employment and Conditions of Service) Act 1979", "anchor": "ismw-1979/sec-12"},
    ]
    return_fare_joined = " ".join(
        _grounded_template_lines(return_fare_q, route_matter(return_fare_q), return_fare_passages)
    )
    assert "return-fare/journey-allowance issue" in return_fare_joined
    assert "promised return fare from Gurgaon to Bihar" in return_fare_joined
    assert "abandoned the workers" in return_fare_joined
    assert "[1]" in return_fare_joined

    shoes_q = "factory takes money for safety shoes every month but never gives shoes or receipt"
    shoes_passages = [
        {"index": 1, "title": "Code on Wages 2019", "anchor": "code-on-wages-2019/sec-18"},
        {"index": 2, "title": "Code on Wages 2019", "anchor": "code-on-wages-2019/sec-45"},
        {"index": 3, "title": "Bonded Labour System (Abolition) Act 1976", "anchor": "bonded-labour-1976/sec-18"},
    ]
    shoes_joined = " ".join(_grounded_template_lines(shoes_q, route_matter(shoes_q), shoes_passages))
    assert "Code on Wages deduction source" in shoes_joined
    assert "instead of treating it as bonded labour" in shoes_joined


def test_stage_500_postfix_pregnant_undertrial_uses_medical_bail_template_first():
    from apps.api.main import _grounded_template_lines
    from apps.api.matter_router import route_matter

    q = "paralegal volunteer 4 women undertrials byculla pregnant where rule postpone trial bail"
    passages = [
        {"index": 1, "title": "Constitution of India", "anchor": "constitution-india/sec-21"},
        {"index": 2, "title": "Bharatiya Nagarik Suraksha Sanhita 2023", "anchor": "bnss-2023/sec-480-a", "text": "The Court may release on bail a woman, sick or infirm accused person."},
        {"index": 3, "title": "Prisons Act 1894", "anchor": "prisons-1894#header"},
    ]

    joined = " ".join(_grounded_template_lines(q, route_matter(q), passages))
    assert "pregnancy or medical condition" in joined
    assert "woman, sick, or infirm" in joined
    assert "prisoner waiting for a medical care" not in joined


def test_stage_500_postfix_factory_death_compensation_template_is_dependant_specific():
    from apps.api.main import _grounded_template_lines
    from apps.api.matter_router import route_matter

    q = "morbi ceramic factory boiler burst friend dead his family bihar nothing got 6 months over"
    passages = [
        {"index": 1, "title": "Employees' Compensation Act 1923", "anchor": "employees-compensation-1923/sec-3"},
        {"index": 2, "title": "Employees' Compensation Act 1923", "anchor": "employees-compensation-1923/sec-10"},
        {"index": 3, "title": "Factories Act 1948", "anchor": "factories-1948/sec-88"},
        {"index": 4, "title": "Contract Labour (Regulation and Abolition) Act 1970", "anchor": "contract-labour-1970/sec-21"},
    ]

    joined = " ".join(_grounded_template_lines(q, route_matter(q), passages))
    assert "dependant compensation" in joined
    assert "Commissioner claim route" in joined
    assert "Factory Inspector/safety record" in joined
    assert "death certificate" in joined

    contractor_problem = "worker died in plant accident employer says contractor problem family needs compensation"
    contractor_joined = " ".join(_grounded_template_lines(contractor_problem, route_matter(contractor_problem), passages))
    assert "Contract Labour Act responsibility source" in contractor_joined


def test_stage_500_offtopic_review_templates_are_user_specific():
    from apps.api.main import _grounded_template_lines
    from apps.api.matter_router import route_matter

    esi_q = "ESI hospital refused to treat my wife for delivery saying my contributions are short, what is the eligibility"
    esi_passages = [
        {"index": 1, "title": "Employees' State Insurance Act 1948", "anchor": "esi-1948/sec-56"},
        {"index": 2, "title": "Employees' State Insurance Act 1948", "anchor": "esi-1948/sec-75"},
        {"index": 3, "title": "Employees' State Insurance Act 1948", "anchor": "esi-1948/sec-40"},
    ]
    esi_joined = " ".join(_grounded_template_lines(esi_q, route_matter(esi_q), esi_passages))
    assert "insured-person medical-benefit eligibility/refusal" in esi_joined
    assert "entitled to receive medical benefit" in esi_joined
    assert "hospital medical superintendent" in esi_joined
    assert "employer contribution recovery" in esi_joined
    assert "right to an ESI benefit" in esi_joined

    water_q = "my borewell water has come bad neighbours factory throwing chemicals"
    water_passages = [
        {"index": 1, "title": "Water (Prevention and Control of Pollution) Act 1974", "anchor": "water-pollution-1974/sec-17"},
        {"index": 2, "title": "National Green Tribunal Act 2010", "anchor": "ngt-2010/sec-15"},
        {"index": 3, "title": "Environment (Protection) Act 1986", "anchor": "environment-protection-1986/sec-3"},
    ]
    water_joined = " ".join(_grounded_template_lines(water_q, route_matter(water_q), water_passages))
    assert "borewell water made bad" in water_joined
    assert "water sampling" in water_joined
    assert "Pollution Control Board" in water_joined

    accident_q = "i was driving and accidentally hit a pedestrian who is now claiming 8 lakh, my insurance is third party only"
    accident_passages = [
        {"index": 1, "title": "TheMotorVehiclesAct,1988", "anchor": "motor-vehicles-1988/sec-146"},
        {"index": 2, "title": "TheMotorVehiclesAct,1988", "anchor": "motor-vehicles-1988/sec-147"},
        {"index": 3, "title": "TheMotorVehiclesAct,1988", "anchor": "motor-vehicles-1988/sec-166"},
    ]
    accident_joined = " ".join(_grounded_template_lines(accident_q, route_matter(accident_q), accident_passages))
    assert "MACT" in accident_joined or "Motor Vehicles" in accident_joined or "pedestrian" in accident_joined.lower()
    assert "Motor Accident Claims Tribunal" in accident_joined
    assert "do not privately settle" in accident_joined

    laptop_q = "my company laptop has been seized by police as part of investigation against my colleague, what are my rights"
    laptop_passages = [
        {"index": 1, "title": "Bharatiya Nagarik Suraksha Sanhita 2023", "anchor": "bnss-2023/sec-105"},
        {"index": 2, "title": "Bharatiya Nagarik Suraksha Sanhita 2023", "anchor": "bnss-2023/sec-497"},
        {"index": 3, "title": "Information Technology Act 2000", "anchor": "it-act-2000/sec-2"},
    ]
    laptop_joined = " ".join(_grounded_template_lines(laptop_q, route_matter(laptop_q), laptop_passages))
    assert "search/seizure and property-custody problem" in laptop_joined
    assert "interim custody, release, copying, or preservation" in laptop_joined
    assert "seizure memo, case/FIR number" in laptop_joined

    nclat_q = "tribunal order against me how to appeal NCLAT format and fees"
    nclat_passages = [
        {"index": 1, "title": "Insolvency and Bankruptcy Code 2016", "anchor": "ibc-2016/sec-61"},
        {"index": 2, "title": "Companies Act 2013", "anchor": "companies-2013/sec-421"},
    ]
    nclat_joined = " ".join(_grounded_template_lines(nclat_q, route_matter(nclat_q), nclat_passages))
    assert "NCLAT appeal from an NCLT insolvency order" in nclat_joined
    assert "company-law tribunal order" in nclat_joined
    assert "NCLAT registry/rules" in nclat_joined


def test_stage_500_recovery_safe_promotions_keep_legal_aid_and_wage_steps():
    from apps.api.main import (
        _is_safe_template_next_step,
        _is_safe_template_source_bridge,
    )
    from apps.api.matter_router import route_matter

    header = SimpleNamespace(text="What you can do next")
    legal_route = route_matter("i am poor brother arrested can court give free lawyer nalsa kya hota hai")
    wage_route = route_matter("came from supaul bihar to mumbai 6 months no payment munshi keeps saying next week")

    assert _is_safe_template_next_step(
        "- Take ID proof, arrest, remand, or jail papers to the nearest DLSA/TLSC help desk and ask for an application acknowledgement [1].",
        legal_route,
        header,
    )
    assert _is_safe_template_source_bridge(
        "For this migrant-worker wage dispute, start with the Code on Wages payment and claim-authority source before treating it as only a verbal promise or private fight [1].",
        wage_route,
    )
    assert _is_safe_template_source_bridge(
        "If the thekedar promised return fare from Gurgaon to Bihar and then abandoned the workers, record that promised fare, abandonment, worker count, and travel proof in the ISMW complaint [1].",
        route_matter("thekedar promised return fare from gurgaon to bihar but abandoned 12 workers"),
    )


def test_targeted_recovery_social_welfare_widow_pension_remarriage_template():
    from apps.api.main import _grounded_template_lines
    from apps.api.matter_router import route_matter

    q = "village pradhan removed my widow pension says i remarried but i didnt up"
    passages = [
        {"index": 1, "title": "National Social Assistance Programme Guidelines 2014", "anchor": "nsap-guidelines-2014#header"},
        {"index": 2, "title": "Right to Information Act 2005", "anchor": "rti-2005/sec-19-b"},
    ]

    joined = " ".join(_grounded_template_lines(q, route_matter(q), passages))

    assert "remarriage allegation" in joined
    assert "pradhan or mukhiya" in joined
    assert "written restoration status" in joined


def test_targeted_recovery_mgnrega_fake_job_card_template():
    from apps.api.main import _grounded_template_lines
    from apps.api.matter_router import route_matter

    q = "ngo helping us said mukhiya did fake job cards no action by collector"
    passages = [
        {"index": 1, "title": "Mahatma Gandhi National Rural Employment Guarantee Act 2005", "anchor": "mgnrega-2005/sec-19"},
        {"index": 2, "title": "Mahatma Gandhi National Rural Employment Guarantee Act 2005", "anchor": "mgnrega-2005/sec-17"},
        {"index": 3, "title": "Right to Information Act 2005", "anchor": "rti-2005/sec-6"},
    ]

    joined = " ".join(_grounded_template_lines(q, route_matter(q), passages))

    assert "fake job-card complaint" in joined
    assert "action-taken request" in joined
    assert "MGNREGA" in joined

    ordering_q = "nrega worker wages pending gram sabha social audit no action bdo"
    ordering_joined = " ".join(_grounded_template_lines(ordering_q, route_matter(ordering_q), [
        {"index": 1, "title": "Code on Wages 2019", "anchor": "code-on-wages-2019/sec-45"},
        {"index": 2, "title": "Mahatma Gandhi National Rural Employment Guarantee Act 2005", "anchor": "mgnrega-2005/sec-17"},
        {"index": 3, "title": "Mahatma Gandhi National Rural Employment Guarantee Act 2005", "anchor": "mgnrega-2005/sec-19"},
    ]))
    assert "MGNREGA social-audit source" in ordering_joined
    assert "Code on Wages" not in ordering_joined

    dead_people_q = "MGNREGA fake muster roll names of dead people how complain"
    dead_people_joined = " ".join(_grounded_template_lines(dead_people_q, route_matter(dead_people_q), [
        {"index": 2, "title": "Mahatma Gandhi National Rural Employment Guarantee Act 2005", "anchor": "mgnrega-2005/sec-17"},
        {"index": 3, "title": "Mahatma Gandhi National Rural Employment Guarantee Act 2005", "anchor": "mgnrega-2005/sec-19"},
        {"index": 4, "title": "Right to Information Act 2005", "anchor": "rti-2005/sec-6"},
    ]))
    assert "MGNREGA social-audit source" in dead_people_joined
    assert "muster-roll pages" in dead_people_joined


def test_stage5_common_labour_vendor_templates_handle_real_user_failures():
    from apps.api.main import _grounded_template_lines
    from apps.api.matter_router import route_matter

    minimum_wage_q = "site supervisor saying minimum wage 350 only but karnataka rate is 600 construction unskilled"
    minimum_wage = " ".join(_grounded_template_lines(minimum_wage_q, route_matter(minimum_wage_q), [
        {"index": 1, "title": "Code on Wages 2019", "anchor": "code-on-wages-2019/sec-6"},
        {"index": 2, "title": "Code on Wages 2019", "anchor": "code-on-wages-2019/sec-8"},
        {"index": 3, "title": "Code on Wages 2019", "anchor": "code-on-wages-2019/sec-45"},
    ]))
    assert "minimum-wage dispute" in minimum_wage
    assert "Karnataka" in minimum_wage
    assert "skill level" in minimum_wage
    assert "minimum rate of wages payable" in minimum_wage
    assert "hear and determine claims under the Code" in minimum_wage
    assert "shortfall calculation" in minimum_wage
    assert "[1]" in minimum_wage and "[3]" in minimum_wage

    waiter_q = "hotel waiter minimum wage paid below state rate what can I do"
    waiter_wage = " ".join(_grounded_template_lines(waiter_q, route_matter(waiter_q), [
        {"index": 1, "title": "Code on Wages 2019", "anchor": "code-on-wages-2019/sec-6"},
        {"index": 2, "title": "Code on Wages 2019", "anchor": "code-on-wages-2019/sec-45"},
    ]))
    assert "minimum-wage dispute" in waiter_wage
    assert "skill level" in waiter_wage
    assert "shortfall calculation" in waiter_wage

    thekedar_min_q = "thekedar paying us 300 not Karnataka minimum wage 600 at construction site"
    thekedar_min = " ".join(_grounded_template_lines(thekedar_min_q, route_matter(thekedar_min_q), [
        {"index": 1, "title": "Code on Wages 2019", "anchor": "code-on-wages-2019/sec-6"},
        {"index": 2, "title": "Code on Wages 2019", "anchor": "code-on-wages-2019/sec-45"},
        {"index": 3, "title": "Contract Labour (Regulation and Abolition) Act 1970", "anchor": "contract-labour-1970/sec-21"},
    ]))
    assert "minimum-wage dispute" in thekedar_min
    assert "Contract Labour Act wage-responsibility" not in thekedar_min

    bocw_q = "thekedar gave 8 of us same name on register only 2 names real cheating bocw he gets cess"
    bocw = " ".join(_grounded_template_lines(bocw_q, route_matter(bocw_q), [
        {"index": 1, "title": "Building and Other Construction Workers (Regulation of Employment and Conditions of Service) Act 1996", "anchor": "bocw-1996/sec-13"},
        {"index": 2, "title": "Building and Other Construction Workers Welfare Cess Act 1996", "anchor": "bocw-cess-1996/sec-3"},
        {"index": 3, "title": "Bharatiya Nyaya Sanhita 2023", "anchor": "bns-2023/sec-318"},
        {"index": 4, "title": "Bharatiya Nagarik Suraksha Sanhita 2023", "anchor": "bnss-2023/sec-173"},
    ]))
    assert "BOCW worker register" in bocw
    assert "construction-worker cess" in bocw
    assert "real workers" in bocw
    assert "BOCW Welfare Board" in bocw
    assert "[1]" in bocw and "[2]" in bocw

    welfare_board_q = "contractor put fake names in construction welfare board register and took worker benefit money"
    welfare_board = " ".join(_grounded_template_lines(welfare_board_q, route_matter(welfare_board_q), [
        {"index": 1, "title": "Building and Other Construction Workers (Regulation of Employment and Conditions of Service) Act 1996", "anchor": "bocw-1996/sec-13"},
        {"index": 2, "title": "Building and Other Construction Workers Welfare Cess Act 1996", "anchor": "bocw-cess-1996/sec-3"},
        {"index": 3, "title": "Bharatiya Nyaya Sanhita 2023", "anchor": "bns-2023/sec-318"},
    ]))
    assert "BOCW worker register" in welfare_board
    assert "BOCW Welfare Board" in welfare_board

    vendor_q = "fish market vendor cochin license panchayat only kerala municipal saying pay 5000 fine illegal"
    vendor = " ".join(_grounded_template_lines(vendor_q, route_matter(vendor_q), [
        {"index": 1, "title": "Street Vendors (Protection of Livelihood and Regulation of Street Vending) Act 2014", "anchor": "street-vendors-2014/sec-4"},
        {"index": 2, "title": "Street Vendors (Protection of Livelihood and Regulation of Street Vending) Act 2014", "anchor": "street-vendors-2014/sec-20"},
        {"index": 3, "title": "Street Vendors (Protection of Livelihood and Regulation of Street Vending) Act 2014", "anchor": "street-vendors-2014/sec-28"},
        {"index": 4, "title": "Street Vendors (Protection of Livelihood and Regulation of Street Vending) Act 2014", "anchor": "street-vendors-2014/sec-36"},
    ]))
    assert "licence, zone-allotment, challan, or municipal fine" in vendor
    assert "street vendor municipal dispute in Cochin/Kerala" in vendor
    assert "Town Vending Committee" in vendor
    assert "penalty provision" in vendor
    assert "Rs. 5000" in vendor
    assert "rupees two thousand" in vendor
    assert "grievance/dispute-redressal source" in vendor
    assert "application in writing to the grievance committee" in vendor
    assert "rule/order behind the demand" in vendor
    assert "removing a vending goods" not in vendor
    assert "Prevention of Corruption" not in vendor
    assert "[1]" in vendor and "[2]" in vendor and "[3]" in vendor

    bribe_vendor_q = "vendor zone bhopal allotted me 2018 now hawker inspector saying pay 2000 every month otherwise remove"
    bribe_vendor = " ".join(_grounded_template_lines(bribe_vendor_q, route_matter(bribe_vendor_q), [
        {"index": 1, "title": "Street Vendors (Protection of Livelihood and Regulation of Street Vending) Act 2014", "anchor": "street-vendors-2014/sec-4"},
        {"index": 2, "title": "Street Vendors (Protection of Livelihood and Regulation of Street Vending) Act 2014", "anchor": "street-vendors-2014/sec-20"},
        {"index": 3, "title": "Prevention of Corruption Act 1988", "anchor": "prevention-of-corruption-1988/sec-7"},
    ]))
    assert "Prevention of Corruption Act" in bribe_vendor
    assert "street vendor municipal dispute in Bhopal" in bribe_vendor
    assert "monthly cash" in bribe_vendor or "without challan/receipt" in bribe_vendor
    assert "separate from the vending licence dispute" in bribe_vendor

    pune_vendor_q = "vegetable cart pune municipal seized everything 4500 stock my license is from labour chowk only"
    pune_vendor = " ".join(_grounded_template_lines(pune_vendor_q, route_matter(pune_vendor_q), [
        {"index": 1, "title": "Street Vendors (Protection of Livelihood and Regulation of Street Vending) Act 2014", "anchor": "street-vendors-2014/sec-18"},
        {"index": 2, "title": "Street Vendors (Protection of Livelihood and Regulation of Street Vending) Act 2014", "anchor": "street-vendors-2014/sec-19"},
        {"index": 3, "title": "Street Vendors (Protection of Livelihood and Regulation of Street Vending) Act 2014", "anchor": "street-vendors-2014/sec-4"},
    ]))
    assert "vegetable cart" in pune_vendor
    assert "Pune" in pune_vendor
    assert "seized stock" in pune_vendor or "stock value" in pune_vendor
    assert "list of goods seized" in pune_vendor
    assert "Town Vending Committee" in pune_vendor

    challan_vendor_q = "street vendor paid challan fine but inspector asking cash bribe every month"
    challan_vendor = " ".join(_grounded_template_lines(challan_vendor_q, route_matter(challan_vendor_q), [
        {"index": 1, "title": "Street Vendors (Protection of Livelihood and Regulation of Street Vending) Act 2014", "anchor": "street-vendors-2014/sec-4"},
        {"index": 2, "title": "Street Vendors (Protection of Livelihood and Regulation of Street Vending) Act 2014", "anchor": "street-vendors-2014/sec-20"},
        {"index": 3, "title": "Prevention of Corruption Act 1988", "anchor": "prevention-of-corruption-1988/sec-7"},
    ]))
    assert "Street Vendors Act" in challan_vendor
    assert "Prevention of Corruption Act" in challan_vendor

    no_cart_removal_q = "municipality removed my fish basket from footpath without notice"
    no_cart_removal = " ".join(_grounded_template_lines(no_cart_removal_q, route_matter(no_cart_removal_q), [
        {"index": 1, "title": "Street Vendors (Protection of Livelihood and Regulation of Street Vending) Act 2014", "anchor": "street-vendors-2014/sec-18"},
        {"index": 2, "title": "Street Vendors (Protection of Livelihood and Regulation of Street Vending) Act 2014", "anchor": "street-vendors-2014/sec-20"},
    ]))
    assert "removing your vending goods" in no_cart_removal
    assert "removing a vending goods" not in no_cart_removal


def test_targeted_recovery_senior_gold_and_own_house_templates():
    from apps.api.main import _grounded_template_lines
    from apps.api.matter_router import route_matter

    gold_q = "mother gifted gold to grandson at marriage now wants back because cant pay medical bills"
    house_q = "my son threw me out of my own house i paid for it in 1985 mumbai"
    senior_passages = [
        {"index": 1, "title": "Maintenance and Welfare of Parents and Senior Citizens Act 2007", "anchor": "mwp-2007/sec-4"},
        {"index": 2, "title": "Maintenance and Welfare of Parents and Senior Citizens Act 2007", "anchor": "mwp-2007/sec-23"},
        {"index": 3, "title": "Transfer of Property Act 1882", "anchor": "transfer-of-property-1882/sec-126"},
    ]

    gold = " ".join(_grounded_template_lines(gold_q, route_matter(gold_q), senior_passages))
    house = " ".join(_grounded_template_lines(house_q, route_matter(house_q), senior_passages))

    assert "gold given at a marriage" in gold
    assert "medical bills are now unpaid" in gold
    assert "senior citizen's own house" in house
    assert "property-record problem" in house


def test_targeted_recovery_gratuity_wins_over_epf_template():
    from apps.api.main import _grounded_template_lines
    from apps.api.matter_router import route_matter

    q = "father epf trust delayed gratuity 18 months no interest paid hsmc bangalore"
    passages = [
        {"index": 1, "title": "Employees' Provident Funds and Miscellaneous Provisions Act 1952", "anchor": "epf-1952/sec-22"},
        {"index": 2, "title": "Payment of Gratuity Act 1972", "anchor": "gratuity-1972/sec-7-a"},
    ]

    joined = " ".join(_grounded_template_lines(q, route_matter(q), passages))

    assert "delayed gratuity or gratuity interest" in joined
    assert "separately from EPF/PF" in joined
    assert "EPFO only for the PF side" in joined


def test_targeted_recovery_custody_medical_and_498a_rejection_templates():
    from apps.api.main import _grounded_template_lines
    from apps.api.matter_router import route_matter

    medical_q = "husband in arthur road tb test not done jail doctor 4 months waiting"
    bail_q = "husband arrested 498a anticipatory bail filed sessions court rejected what next high court"
    criminal_passages = [
        {"index": 1, "title": "Constitution of India", "anchor": "constitution-india/sec-21"},
        {"index": 2, "title": "Prisons Act 1894", "anchor": "prisons-1894#header"},
        {"index": 3, "title": "Bharatiya Nagarik Suraksha Sanhita 2023", "anchor": "bnss-2023/sec-480-a"},
        {"index": 4, "title": "Bharatiya Nyaya Sanhita 2023", "anchor": "bns-2023/sec-85"},
    ]

    medical = " ".join(_grounded_template_lines(medical_q, route_matter(medical_q), criminal_passages))
    bail = " ".join(_grounded_template_lines(bail_q, route_matter(bail_q), criminal_passages))

    assert "TB test in Arthur Road jail" in medical
    assert "Jail Superintendent/medical officer" in medical
    assert "Sessions Court bail" in bail
    assert "High Court anticipatory bail" in bail


def test_carceral_fresh_failure_templates_are_user_specific():
    from apps.api.main import _grounded_template_lines
    from apps.api.matter_router import route_matter

    juvenile_q = "minor boy picked by police and kept in station with adults, school id says age 16"
    juvenile_joined = " ".join(_grounded_template_lines(juvenile_q, route_matter(juvenile_q), [
        {"index": 1, "title": "Juvenile Justice (Care and Protection of Children) Act 2015", "anchor": "jj-2015/sec-94"},
        {"index": 2, "title": "Juvenile Justice (Care and Protection of Children) Act 2015", "anchor": "jj-2015/sec-9"},
        {"index": 3, "title": "Juvenile Justice (Care and Protection of Children) Act 2015", "anchor": "jj-2015/sec-12"},
        {"index": 4, "title": "Juvenile Justice (Care and Protection of Children) Act 2015", "anchor": "jj-2015/sec-10"},
    ]))
    assert "age determination" in juvenile_joined
    assert "Juvenile Justice Board" in juvenile_joined
    assert "police lockup or lodged in a jail" in juvenile_joined
    assert "school or matriculation" in juvenile_joined
    assert "[1]" in juvenile_joined and "[4]" in juvenile_joined

    notice_q = "i received 35 notice but police also says bring all chats and don't tell lawyer"
    notice_joined = " ".join(_grounded_template_lines(notice_q, route_matter(notice_q), [
        {"index": 1, "title": "Bharatiya Nagarik Suraksha Sanhita 2023", "anchor": "bnss-2023/sec-35"},
        {"index": 2, "title": "Bharatiya Nagarik Suraksha Sanhita 2023", "anchor": "bnss-2023/sec-94"},
        {"index": 3, "title": "Code of Criminal Procedure 1973", "anchor": "crpc-1973/sec-160"},
    ]))
    assert "notice-to-appear source" in notice_joined
    assert "production-summons issue" in notice_joined
    assert "chats, a phone, or electronic records" in notice_joined
    assert "not the same thing as bail" in notice_joined
    assert "[1]" in notice_joined and "[2]" in notice_joined

    lawyer_q = "police says lawyer can meet only after confession statement, accused is inside lockup"
    lawyer_joined = " ".join(_grounded_template_lines(lawyer_q, route_matter(lawyer_q), [
        {"index": 1, "title": "Legal Services Authorities Act 1987", "anchor": "legal-services-authorities-1987/sec-12"},
        {"index": 2, "title": "Constitution of India", "anchor": "constitution-india/sec-22"},
        {"index": 3, "title": "Bharatiya Nagarik Suraksha Sanhita 2023", "anchor": "bnss-2023/sec-57"},
    ]))
    assert "lawyer only after confession" in lawyer_joined
    assert "lawyer-access blockage" in lawyer_joined
    assert "Article 22" in lawyer_joined

    mulaqat_q = "rohini jail cancelled my video mulaqat twice and says system issue, can family demand written reason"
    mulaqat_joined = " ".join(_grounded_template_lines(mulaqat_q, route_matter(mulaqat_q), [
        {"index": 1, "title": "Delhi Prison Rules 2018", "anchor": "delhi-prison-rules-2018/rule-595-599"},
        {"index": 2, "title": "Prisons Act 1894", "anchor": "prisons-1894/sec-59"},
        {"index": 3, "title": "Constitution of India", "anchor": "constitution-india/sec-21"},
    ]))
    assert "Tihar/Delhi mulaqat" in mulaqat_joined
    assert "recorded reasons for refusal" in mulaqat_joined
    assert "parole is temporary release" not in mulaqat_joined


def test_targeted_recovery_identity_origin_threat_template():
    from apps.api.main import _grounded_template_lines
    from apps.api.matter_router import route_matter

    q = "biharee called we are by site engineer pune always after wage complaint is this crime"
    passages = [
        {"index": 1, "title": "Constitution of India", "anchor": "constitution-india/sec-21"},
        {"index": 2, "title": "Bharatiya Nagarik Suraksha Sanhita 2023", "anchor": "bnss-2023/sec-173-b"},
        {"index": 3, "title": "Bharatiya Nyaya Sanhita 2023", "anchor": "bns-2023/sec-351"},
    ]

    joined = " ".join(_grounded_template_lines(q, route_matter(q), passages))

    assert "Bihari/Biharee" in joined
    assert "wage-dispute file" in joined
    assert "insult alone" in joined


def test_stage_500_post_review_templates_fix_offtopic_and_citation_misses():
    from apps.api.main import _grounded_template_lines
    from apps.api.matter_router import route_matter

    false_fir_q = "thekedar made fake theft fir against me after i asked wages now police calling station"
    false_fir_joined = " ".join(_grounded_template_lines(false_fir_q, route_matter(false_fir_q), [
        {"index": 1, "title": "Bharatiya Nyaya Sanhita 2023", "anchor": "bns-2023/sec-303"},
        {"index": 2, "title": "Bharatiya Nagarik Suraksha Sanhita 2023", "anchor": "bnss-2023/sec-173"},
        {"index": 3, "title": "Bharatiya Nagarik Suraksha Sanhita 2023", "anchor": "bnss-2023/sec-175"},
        {"index": 4, "title": "Code on Wages 2019", "anchor": "code-on-wages-2019/sec-45"},
        {"index": 5, "title": "Contract Labour (Regulation and Abolition) Act 1970", "anchor": "contract-labour-1970/sec-21"},
    ]))
    assert "theft accusation from the wage-retaliation facts" in false_fir_joined
    assert "parallel wage-claim file" in false_fir_joined
    assert "immediate criminal-procedure step" in false_fir_joined
    assert "officer in charge of a police station" in false_fir_joined
    assert "hear and determine wage claims" in false_fir_joined
    assert "written labour complaint" in false_fir_joined
    assert "Do not ignore police calls" in false_fir_joined
    assert "[1]" in false_fir_joined and "[4]" in false_fir_joined

    caste_fir_q = "upper caste people beat my husband called us chamar FIR not registering thana khunti jharkhand"
    caste_fir_joined = " ".join(_grounded_template_lines(caste_fir_q, route_matter(caste_fir_q), [
        {"index": 1, "title": "Scheduled Castes and Scheduled Tribes (Prevention of Atrocities) Act 1989", "anchor": "sc-st-poa-1989/sec-14"},
        {"index": 2, "title": "Bharatiya Nagarik Suraksha Sanhita 2023", "anchor": "bnss-2023/sec-175"},
        {"index": 3, "title": "Bharatiya Nyaya Sanhita 2023", "anchor": "bns-2023/sec-117"},
        {"index": 5, "title": "Bharatiya Nagarik Suraksha Sanhita 2023", "anchor": "bnss-2023/sec-173"},
    ]))
    assert "SC/ST POA Act source" in caste_fir_joined
    assert "not registering the FIR" in caste_fir_joined
    assert "Special Court" in caste_fir_joined
    assert "oral information must be written and read over" in caste_fir_joined
    assert "SP/DySP" in caste_fir_joined

    caste_school_q = "girl beaten in school by teacher calling caste name principal not acting maharashtra"
    caste_school_joined = " ".join(_grounded_template_lines(caste_school_q, route_matter(caste_school_q), [
        {"index": 1, "title": "Scheduled Castes and Scheduled Tribes (Prevention of Atrocities) Act 1989", "anchor": "sc-st-poa-1989/sec-3"},
        {"index": 2, "title": "Scheduled Castes and Scheduled Tribes (Prevention of Atrocities) Act 1989", "anchor": "sc-st-poa-1989/sec-15A"},
        {"index": 3, "title": "Bharatiya Nagarik Suraksha Sanhita 2023", "anchor": "bnss-2023/sec-173"},
    ]))
    assert "SC/ST atrocity complaint" in caste_school_joined
    assert "school/principal" in caste_school_joined
    assert "victim-rights source" in caste_school_joined
    assert "case status, notice of proceedings" in caste_school_joined

    muslim_q = "father says he is muslim 72 years his sons not giving share from grandfather property hyderabad"
    muslim_joined = " ".join(_grounded_template_lines(muslim_q, route_matter(muslim_q), [
        {"index": 1, "title": "Muslim Personal Law (Shariat) Application Act 1937", "anchor": "shariat-1937/sec-2"},
        {"index": 2, "title": "Transfer of Property Act 1882", "anchor": "transfer-of-property-1882/sec-44"},
        {"index": 3, "title": "Specific Relief Act 1963", "anchor": "specific-relief-1963/sec-34"},
        {"index": 4, "title": "Maintenance and Welfare of Parents and Senior Citizens Act 2007", "anchor": "senior-citizens-2007/sec-4"},
    ]))
    assert "father is alive" in muslim_joined
    assert "grandfather has died" in muslim_joined
    assert "partition/declaration" in muslim_joined

    trans_q = "I am transwoman my landlord threw me out after he found out he kept my deposit also where do I complain"
    trans_joined = " ".join(_grounded_template_lines(trans_q, route_matter(trans_q), [
        {"index": 1, "title": "Transgender Persons (Protection of Rights) Act 2019", "anchor": "transgender-2019/sec-3"},
        {"index": 2, "title": "Transfer of Property Act 1882", "anchor": "transfer-of-property-1882/sec-105"},
        {"index": 3, "title": "Transfer of Property Act 1882", "anchor": "transfer-of-property-1882/sec-106"},
        {"index": 4, "title": "Transgender Persons (Protection of Rights) Act 2019", "anchor": "transgender-2019/sec-18"},
    ]))
    assert "transgender discrimination issue" in trans_joined
    assert "deposit or possession relief" in trans_joined
    assert "[1]" in trans_joined and "[3]" in trans_joined

    custody_q = "my brother beaten in lockup constable took 20000 for bail still not released"
    custody_joined = " ".join(_grounded_template_lines(custody_q, route_matter(custody_q), [
        {"index": 1, "title": "Protection of Human Rights Act 1993", "anchor": "protection-human-rights-1993/sec-12"},
        {"index": 2, "title": "Bharatiya Nagarik Suraksha Sanhita 2023", "anchor": "bnss-2023/sec-173"},
        {"index": 3, "title": "Bharatiya Nyaya Sanhita 2023", "anchor": "bns-2023/sec-117"},
        {"index": 4, "title": "Constitution of India", "anchor": "constitution-india/sec-21"},
    ]))
    assert "Human Rights Act source" in custody_joined
    assert "NHRC/SHRC complaint" in custody_joined
    assert "[1]" in custody_joined

    ola_q = "ola driver suspended id no reason 4000 rupees earning gone how to complaint"
    ola_joined = " ".join(_grounded_template_lines(ola_q, route_matter(ola_q), [
        {"index": 5, "title": "Motor Vehicle Aggregator Guidelines 2020", "anchor": "motor-vehicle-aggregator-guidelines-2020#driver-service-contract"},
        {"index": 6, "title": "Motor Vehicle Aggregator Guidelines 2020", "anchor": "motor-vehicle-aggregator-guidelines-2020#app-transparency-grievance"},
        {"index": 7, "title": "Motor Vehicles Act 1988", "anchor": "motor-vehicles-1988/sec-193"},
        {"index": 8, "title": "Code on Wages 2019", "anchor": "code-on-wages-2019/sec-45"},
    ]))
    assert "Motor Vehicles Act aggregator source" in ola_joined
    assert "undisputed earnings or payout" in ola_joined
    assert "[7]" in ola_joined and "[8]" in ola_joined


def test_common_user_answer_templates_cover_ui_failure_prompts():
    from apps.api.main import _grounded_template_lines
    from apps.api.matter_router import route_matter

    hospital = " ".join(_grounded_template_lines(
        "hospital overcharged me and not giving detailed bill",
        route_matter("hospital overcharged me and not giving detailed bill"),
        [
            {"index": 1, "title": "Consumer Protection Act 2019", "anchor": "consumer-protection-2019/sec-2"},
            {"index": 2, "title": "Consumer Protection Act 2019", "anchor": "consumer-protection-2019/sec-35"},
            {"index": 3, "title": "Clinical Establishments Act 2010", "anchor": "clinical-establishments-2010/sec-12"},
        ],
    ))
    assert "hospital records/billing" in hospital
    assert "Clinical Establishments Act" in hospital
    assert "[3]" in hospital

    hospital_records = " ".join(_grounded_template_lines(
        "private hospital not giving medical records after discharge",
        route_matter("private hospital not giving medical records after discharge"),
        [
            {"index": 1, "title": "Code of Medical Ethics Regulations 2002", "anchor": "medical-ethics-regulations-2002/reg-1.3.2"},
            {"index": 2, "title": "Clinical Establishments (Registration and Regulation) Act 2010", "anchor": "clinical-establishments-2010/sec-12"},
            {"index": 3, "title": "Consumer Protection Act 2019", "anchor": "consumer-protection-2019/sec-35"},
        ],
    ))
    assert "Medical Ethics Regulations" in hospital_records
    assert "72 hours" in hospital_records
    assert "Clinical Establishments source for records-maintenance" in hospital_records
    assert "[1]" in hospital_records

    posh = " ".join(_grounded_template_lines(
        "manager sends dirty messages and HR says ignore",
        route_matter("manager sends dirty messages and HR says ignore"),
        [
            {"index": 1, "title": "Sexual Harassment of Women at Workplace Act 2013", "anchor": "posh-2013/sec-3"},
            {"index": 2, "title": "Sexual Harassment of Women at Workplace Act 2013", "anchor": "posh-2013/sec-9"},
            {"index": 3, "title": "Sexual Harassment of Women at Workplace Act 2013", "anchor": "posh-2013/sec-19"},
        ],
    ))
    assert "dirty messages" in posh
    assert "Internal Committee" in posh
    assert "HR says to ignore" in posh

    theft = " ".join(_grounded_template_lines(
        "scooter stolen from parking station says give written complaint only",
        route_matter("scooter stolen from parking station says give written complaint only"),
        [
            {"index": 1, "title": "Bharatiya Nyaya Sanhita 2023", "anchor": "bns-2023/sec-303"},
            {"index": 2, "title": "Bharatiya Nagarik Suraksha Sanhita 2023", "anchor": "bnss-2023/sec-173-a"},
            {"index": 3, "title": "Bharatiya Nagarik Suraksha Sanhita 2023", "anchor": "bnss-2023/sec-173-c"},
            {"index": 4, "title": "Code of Criminal Procedure 1973", "anchor": "crpc-1973/sec-154"},
        ],
    ))
    assert "pre-1-July-2024" in theft
    assert "incident on or after 1 July 2024" in theft
    assert "written complaint, acknowledgement, and any refusal" in theft

    street_vendor = " ".join(_grounded_template_lines(
        "municipality removed my tea cart from footpath without notice",
        route_matter("municipality removed my tea cart from footpath without notice"),
        [
            {"index": 1, "title": "Street Vendors (Protection of Livelihood and Regulation of Street Vending) Act 2014", "anchor": "street-vendors-2014/sec-18"},
            {"index": 2, "title": "Street Vendors (Protection of Livelihood and Regulation of Street Vending) Act 2014", "anchor": "street-vendors-2014/sec-19"},
            {"index": 3, "title": "Street Vendors (Protection of Livelihood and Regulation of Street Vending) Act 2014", "anchor": "street-vendors-2014/sec-4"},
        ],
    ))
    assert "tea cart" in street_vendor
    assert "notice" in street_vendor
    assert "Town Vending Committee" in street_vendor

    shop = " ".join(_grounded_template_lines(
        "local body locked my commercial shop saying licence problem",
        route_matter("local body locked my commercial shop saying licence problem"),
        [
            {"index": 1, "title": "Right to Information Act 2005", "anchor": "right-to-information-act-2005/sec-6"},
            {"index": 2, "title": "Shops and Establishments Act", "anchor": "shops-establishments/sec-1"},
        ],
    ))
    assert "sealing order" in shop
    assert "RTI" in shop
    assert "licence" in shop

    hand_loan = " ".join(_grounded_template_lines(
        "relative took hand loan 2 years back no agreement what can i do",
        route_matter("relative took hand loan 2 years back no agreement what can i do"),
        [
            {"index": 1, "title": "Indian Contract Act 1872", "anchor": "indian-contract-1872/sec-37"},
            {"index": 2, "title": "Limitation Act 1963", "anchor": "limitation-1963/sec-3"},
            {"index": 3, "title": "Code of Civil Procedure 1908", "anchor": "cpc-1908/sec-1"},
        ],
    ))
    assert "civil money-recovery issue" in hand_loan
    assert "Limitation Act" in hand_loan
    assert "no legal obligation" not in hand_loan

    bank = " ".join(_grounded_template_lines(
        "bank reversed my balance saying technical error but not giving reason",
        route_matter("bank reversed my balance saying technical error but not giving reason"),
        _rbi_ombudsman_sources(),
    ))
    assert "RBI Ombudsman" in bank
    assert "Consumer Protection Act" not in bank

    loan_app = " ".join(_grounded_template_lines(
        "online loan app calling my relatives and abusing me",
        route_matter("online loan app calling my relatives and abusing me"),
        _loan_app_regulatory_sources(),
    ))
    assert "RBI Ombudsman" in loan_app
    assert "contact lists or call logs" in loan_app
    assert "intimidation or harassment, public humiliation" in loan_app
    assert "privacy of a debtor's family members, referees, and friends" in loan_app
    assert "cyber police" not in loan_app


def test_common_user_near_miss_guards_do_not_overstate_facts():
    from apps.api.main import (
        _grounded_template_lines,
        _is_municipal_shop_sealing_query,
        _is_theft_fir_refusal_query,
    )
    from apps.api.matter_router import route_matter

    lost_phone = "police station says give written complaint only for lost phone not stolen"
    assert not _is_theft_fir_refusal_query(lost_phone)
    theft_joined = " ".join(_grounded_template_lines(lost_phone, route_matter(lost_phone), [
        {"index": 1, "title": "Bharatiya Nyaya Sanhita 2023", "anchor": "bns-2023/sec-303"},
        {"index": 2, "title": "Bharatiya Nagarik Suraksha Sanhita 2023", "anchor": "bnss-2023/sec-173"},
    ]))
    assert "stolen phone" not in theft_joined

    licence_info = "local body said my shop licence problem what documents needed"
    assert not _is_municipal_shop_sealing_query(licence_info)
    assert _is_municipal_shop_sealing_query("local body locked my commercial shop saying licence problem")


def test_general_legal_template_stays_intake_not_fake_specific_route():
    from apps.api.main import _grounded_template_lines
    from apps.api.matter_router import route_matter

    query = "what legal help can i get for a general documents issue"
    route = route_matter(query)
    assert route.category == "general_legal"

    joined = " ".join(_grounded_template_lines(query, route, [
        {"index": 1, "title": "Legal Services Authorities Act 1987", "anchor": "legal-services-authorities-1987/sec-12"},
        {"index": 2, "title": "Code of Civil Procedure 1908", "anchor": "cpc-1908/sec-1"},
        {"index": 3, "title": "Limitation Act 1963", "anchor": "limitation-1963/sec-3"},
    ]))

    assert "cannot safely classify" in joined
    assert "intake first" in joined
    assert "state/city" in joined
    assert "final issue-specific answer" in joined


def test_fresh_negative_neighbor_v2_answer_contracts_are_specific():
    from apps.api.main import _grounded_template_lines
    from apps.api.matter_router import route_matter

    adult_choice_q = "my 24 year old daughter left with boyfriend and parents want police to bring her home, what can we do"
    adult_choice = " ".join(_grounded_template_lines(adult_choice_q, route_matter(adult_choice_q), [
        {"index": 1, "title": "Constitution of India", "anchor": "constitution-india/sec-21"},
        {"index": 2, "title": "Bharatiya Nagarik Suraksha Sanhita 2023", "anchor": "bnss-2023/sec-173"},
    ]))
    assert "should not be used only to force an adult to return home" in adult_choice
    assert "voluntary statement" in adult_choice
    assert "[1]" in adult_choice

    private_complaint_q = "private complaint dismissed without cognizance by magistrate, should i file FIR again or revision"
    private_complaint = " ".join(_grounded_template_lines(private_complaint_q, route_matter(private_complaint_q), [
        {"index": 3, "title": "Bharatiya Nagarik Suraksha Sanhita 2023", "anchor": "bnss-2023/sec-223"},
        {"index": 4, "title": "Bharatiya Nagarik Suraksha Sanhita 2023", "anchor": "bnss-2023/sec-175"},
    ]))
    assert "dismissed or refused without cognizance" in private_complaint
    assert "revision" in private_complaint

    scooter_q = "local boys broke my scooter mirror and police are delaying FIR calling it insurance issue"
    scooter = " ".join(_grounded_template_lines(scooter_q, route_matter(scooter_q), [
        {"index": 5, "title": "Bharatiya Nagarik Suraksha Sanhita 2023", "anchor": "bnss-2023/sec-173"},
        {"index": 6, "title": "Bharatiya Nyaya Sanhita 2023", "anchor": "bns-2023/sec-324"},
    ]))
    assert "property damage" in scooter
    assert "mischief/property-damage source" in scooter
    assert "insurance issue" in scooter

    mental_q = "jail not giving psychiatric help for suicidal undertrial, can DLSA move court urgently"
    mental = " ".join(_grounded_template_lines(mental_q, route_matter(mental_q), [
        {"index": 7, "title": "Mental Healthcare Act 2017", "anchor": "mental-healthcare-2017/sec-18"},
        {"index": 8, "title": "Constitution of India", "anchor": "constitution-india/sec-21"},
        {"index": 9, "title": "Prisons Act 1894", "anchor": "prisons-1894/sec-59"},
    ]))
    assert "Mental Healthcare Act" in mental
    assert "suicide risk in custody" in mental

    bond_q = "bail order allows personal bond but jail clerk demands cash deposit before release"
    bond = " ".join(_grounded_template_lines(bond_q, route_matter(bond_q), [
        {"index": 10, "title": "Bharatiya Nagarik Suraksha Sanhita 2023", "anchor": "bnss-2023/sec-480"},
        {"index": 11, "title": "Constitution of India", "anchor": "constitution-india/sec-21"},
    ]))
    assert "personal bond" in bond
    assert "cash-deposit demand" in bond
    assert "same court to clarify" in bond

    cheque_q = "section 138 cheque summons came from court but police constable called also, should i fear arrest"
    cheque = " ".join(_grounded_template_lines(cheque_q, route_matter(cheque_q), [
        {"index": 12, "title": "Negotiable Instruments Act 1881", "anchor": "negotiable-instruments-1881/sec-138"},
        {"index": 13, "title": "Negotiable Instruments Act 1881", "anchor": "negotiable-instruments-1881/sec-142"},
        {"index": 14, "title": "Bharatiya Nagarik Suraksha Sanhita 2023", "anchor": "bnss-2023/sec-223"},
    ]))
    assert "does not convert a Section 138 cheque complaint into an arrest case" in cheque
    assert "FIR, warrant, or court summons" in cheque
