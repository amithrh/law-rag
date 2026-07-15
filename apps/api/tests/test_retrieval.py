"""Tests for multi-head hybrid retrieval — BGE-M3 dense + sparse + BM25.

These are unit tests over the building blocks (sparse vector shape,
RRF math, sparse-retrieval SQL semantics) and a configuration-override
check. Full end-to-end retrieval (against a populated DB with sparse
vectors backfilled) is tested via the `needs_stack` endpoint tests.

The sparse-vector test that loads the actual BGE-M3 weights is marked
`needs_models` so CI without ML deps skips it; the offline tests are
unmarked and run on every commit.
"""
from __future__ import annotations

import asyncio
import json

import pytest

from apps.api.config import Settings
from apps.api.retrieval import (
    RetrievedChunk,
    _apply_authority_rerank_boosts,
    _anchor_boundary_regexes,
    _anchor_regexes_from_patterns,
    _bm25_retrieve_sql,
    _fetch_source_pack_candidates,
    _filter_query_ineligible_sources,
    _focus_required_source_pack_text,
    _preserve_required_source_packs,
    _rerank_candidate_union,
    _section_numbers_from_anchor_patterns,
    _source_cluster_scores,
    _source_quality_score,
    rrf_fuse,
    sparse_retrieve,
)
from apps.api.source_packs import SourcePack


# ---------------------------------------------------------------------------
# RRF math
# ---------------------------------------------------------------------------


def test_rrf_fusion_combines_three_sources():
    """Verify the RRF math against the canonical Cormack et al. formula.

    Setup: three retrievers each return a ranked list of chunk ids. Chunk
    A appears at rank 1 in all three lists, chunk B at ranks (2, 5, 3),
    chunk C only at rank 1 of list-3, etc. The fused score is
    `Σ 1/(k + rank)` per the original paper.

    With k=60:
      A: 3 * 1/(60+1)                = 0.04918
      B: 1/(60+2) + 1/(60+5) + 1/(60+3) = 0.04746
      C: 1/(60+1)                    = 0.01639
      D: 1/(60+2)                    = 0.01613
      E: 1/(60+4)                    = 0.01562
      F: 1/(60+3)                    = 0.01587
    """
    dense = [1, 2, 3, 4]      # A=1, B=2, D=3, E=4
    sparse = [5, 6, 1, 2]     # C=5, F=6, A=1 at rank 3, B=2 at rank 4
    bm25 = [1, 2]             # A=1, B=2 at rank 2

    # Re-map to chunk_ids: A=1, B=2, D=3, E=4, C=5, F=6
    rankings = [dense, sparse, bm25]
    fused = rrf_fuse(rankings, k=60)

    expected_a = 1 / 61 + 1 / 63 + 1 / 61   # A at ranks 1, 3, 1
    expected_b = 1 / 62 + 1 / 64 + 1 / 62   # B at ranks 2, 4, 2
    expected_c = 1 / 61                      # C only in sparse rank 1
    expected_e = 1 / 64                      # E only in dense rank 4

    assert fused[1] == pytest.approx(expected_a, rel=1e-6)
    assert fused[2] == pytest.approx(expected_b, rel=1e-6)
    assert fused[5] == pytest.approx(expected_c, rel=1e-6)
    assert fused[4] == pytest.approx(expected_e, rel=1e-6)
    # A should rank above B in the fused order: same appearances but
    # better average ranks.
    assert fused[1] > fused[2]
    # A (top of all three lists) should rank above C (top of one).
    assert fused[1] > fused[5]


def test_rrf_k_dampens_top_rank_dominance():
    """Larger k flattens the contribution of rank 1 vs deeper ranks.

    At k=1, rank-1 contributes 1/2 and rank-10 contributes 1/11 — a
    5.5x gap. At k=60, rank-1 is 1/61 and rank-10 is 1/70 — only a
    1.15x gap. This makes RRF treat 'top-1 vs deep' as more
    equivalent at higher k. We use k=60 (Cormack standard).
    """
    rankings = [[1], [2, 3, 4, 5, 6, 7, 8, 9, 10, 11]]
    low = rrf_fuse(rankings, k=1)
    high = rrf_fuse(rankings, k=60)

    # Ratio rank1 / rank10 should be larger at lower k.
    ratio_low = low[1] / low[11]
    ratio_high = high[1] / high[11]
    assert ratio_low > ratio_high, (
        f"expected k=1 to dominate rank-1 more than k=60: "
        f"ratios low={ratio_low:.2f} high={ratio_high:.2f}"
    )


def test_preserve_required_source_pack_keeps_exact_act_in_top_k():
    candidates = [
        _retrieved_chunk(i, rerank=0.99 - i * 0.05)
        for i in range(8)
    ]
    required = _retrieved_chunk(
        99,
        rerank=0.48,
        metadata={"_required_source_pack": "bnss_2023"},
    )
    out = _preserve_required_source_packs(
        [*candidates, required],
        ["bnss_2023"],
        limit=8,
    )
    assert len(out) == 8
    assert any(c.chunk_id == 99 for c in out)
    assert all(c.chunk_id != 7 for c in out)


def test_preserve_required_source_pack_can_promote_exact_act_to_visible_window():
    candidates = [
        _retrieved_chunk(i, rerank=0.99 - i * 0.05)
        for i in range(8)
    ]
    required = _retrieved_chunk(
        99,
        rerank=0.48,
        metadata={"_required_source_pack": "bnss_2023"},
    )

    out = _preserve_required_source_packs(
        [*candidates, required],
        ["bnss_2023"],
        limit=8,
        preferred_top_n=4,
    )

    assert [c.chunk_id for c in out[:3]] == [0, 1, 2]
    assert out[3].chunk_id == 99


def test_preserve_required_source_pack_prefers_distinct_higher_priority_packs():
    def packed(chunk_id: int, pack_id: str, priority: float, rerank: float):
        return _retrieved_chunk(
            chunk_id,
            rerank=rerank,
            metadata={
                "_required_source_pack": pack_id,
                "_required_source_priority": priority,
            },
        )

    candidates = [
        packed(1, "bnss_2023", 1.24, 0.91),
        packed(2, "bns_2023_scst_atrocity_threat_hurt", 1.30, 0.90),
        packed(3, "bns_2023", 1.18, 0.89),
        packed(4, "constitution_article_21", 1.16, 0.88),
        packed(5, "pesa_1996", 1.24, 0.87),
        packed(6, "constitution_scheduled_areas", 1.24, 0.86),
        packed(7, "scst_poa_1989", 1.00, 0.85),
        packed(8, "scst_poa_1989", 1.00, 0.84),
        packed(46, "chota_nagpur_tenancy_1908_transfer_restriction", 1.30, 0.30),
        packed(71, "chota_nagpur_tenancy_1908_restoration", 1.28, 0.29),
    ]

    out = _preserve_required_source_packs(
        candidates,
        [
            "scst_poa_1989",
            "bnss_2023",
            "bns_2023_scst_atrocity_threat_hurt",
            "bns_2023",
            "constitution_article_21",
            "pesa_1996",
            "chota_nagpur_tenancy_1908_transfer_restriction",
            "chota_nagpur_tenancy_1908_restoration",
            "constitution_scheduled_areas",
        ],
        limit=8,
    )

    out_pack_ids = [c.metadata.get("_required_source_pack") for c in out]
    assert "chota_nagpur_tenancy_1908_transfer_restriction" in out_pack_ids
    assert "chota_nagpur_tenancy_1908_restoration" in out_pack_ids
    assert out_pack_ids.count("scst_poa_1989") <= 1


def test_preserve_customs_pack_keeps_issue_critical_sections():
    candidates = [
        _retrieved_chunk(i, rerank=0.99 - i * 0.03)
        for i in range(8)
    ]
    for chunk_id, section_no, rerank in (
        (124, "124", 0.49),
        (112, "112", 0.48),
        (111, "111", 0.47),
    ):
        chunk = _retrieved_chunk(
            chunk_id,
            rerank=rerank,
            title="Customs Act 1962",
            metadata={
                "section_no": section_no,
                "_required_source_pack": "customs_misdeclaration_1962",
            },
        )
        chunk.anchor = f"customs-1962/sec-{section_no}"
        candidates.append(chunk)

    out = _preserve_required_source_packs(
        candidates,
        ["customs_misdeclaration_1962"],
        limit=8,
        preferred_top_n=4,
    )

    kept_sections = {
        c.metadata.get("section_no")
        for c in out
        if c.metadata.get("_required_source_pack") == "customs_misdeclaration_1962"
    }
    assert {"124", "111", "112"} <= kept_sections


def test_source_quality_prefers_bare_act_for_statute_first_routes():
    act = _retrieved_chunk(
        1,
        rerank=0.5,
        source_type="bare_act",
        title="Right to Information Act 2005",
    )
    sc = _retrieved_chunk(
        2,
        rerank=0.5,
        source_type="sc_judgment",
        title="RTI judgment",
    )
    hc = _retrieved_chunk(
        3,
        rerank=0.5,
        source_type="hc_judgment",
        title="RTI writ",
    )

    assert _source_quality_score(act, route_category="rti") > _source_quality_score(
        sc,
        route_category="rti",
    )
    assert _source_quality_score(sc, route_category="rti") > _source_quality_score(
        hc,
        route_category="rti",
    )


def test_authority_boost_nudges_bare_act_above_equal_judgment():
    act = _retrieved_chunk(
        1,
        rerank=0.5,
        source_type="bare_act",
        title="Bharatiya Nagarik Suraksha Sanhita 2023",
    )
    judgment = _retrieved_chunk(
        2,
        rerank=0.5,
        source_type="hc_judgment",
        title="Bail order",
    )

    _apply_authority_rerank_boosts(
        [act, judgment],
        route_category="criminal_defence_bail",
        source_quality_boost=0.06,
        source_cluster_boost=0.0,
    )

    assert act.rerank_score is not None
    assert judgment.rerank_score is not None
    assert act.rerank_score > judgment.rerank_score
    assert act.metadata["_source_quality_score"] > judgment.metadata["_source_quality_score"]


def test_source_cluster_scores_reward_repeated_aligned_document():
    clustered = [
        _retrieved_chunk(1, document_id=10, rerank=0.7, source_type="bare_act"),
        _retrieved_chunk(2, document_id=10, rerank=0.6, source_type="bare_act"),
        _retrieved_chunk(3, document_id=20, rerank=0.7, source_type="bare_act"),
    ]

    scores = _source_cluster_scores(clustered, route_category="rti")

    assert scores[10] > scores[20]


def test_query_expansion_defaults_to_single_folded_retrieval():
    s = Settings(database_url="postgresql://x")

    assert s.query_expansion_enabled is True
    assert s.query_expansion_llm_enabled is False
    assert s.query_expansion_strategy == "single"
    assert s.query_expansion_max_variants == 1
    assert s.legal_hyde_mode == "fallback"


def test_rerank_candidate_union_preserves_required_pack(monkeypatch):
    from apps.api import rerank as rerank_module
    from apps.api.source_packs import SourcePack

    def fake_rerank(query, candidates, keep=None):
        for candidate in candidates:
            candidate.rerank_score = 0.95 if candidate.chunk_id in {1, 2} else 0.05
        return sorted(
            candidates,
            key=lambda c: c.rerank_score if c.rerank_score is not None else -1.0,
            reverse=True,
        )

    monkeypatch.setattr(rerank_module, "rerank", fake_rerank)
    candidates = [
        _retrieved_chunk(1, rerank=0.0),
        _retrieved_chunk(2, rerank=0.0),
        _retrieved_chunk(
            99,
            rerank=0.0,
            metadata={"_required_source_pack": "bnss_2023"},
        ),
    ]
    pack = SourcePack(
        id="bnss_2023",
        title_patterns=("Bharatiya Nagarik Suraksha Sanhita",),
        doc_ids=("bnss-2023",),
        anchor_patterns=("/sec-187",),
        search_query="default bail BNSS section 187",
    )

    out = _rerank_candidate_union(
        "default bail after chargesheet delay",
        candidates,
        variants=["default bail", "BNSS section 187 default bail"],
        route_category="criminal_defence_bail",
        packs=[pack],
        top_k=2,
        timings={},
    )

    assert len(out) == 2
    assert any(c.chunk_id == 99 for c in out)
    required = next(c for c in out if c.chunk_id == 99)
    assert required.rerank_score is not None
    assert required.rerank_score >= 0.42


def _retrieved_chunk(
    idx: int,
    *,
    rerank: float,
    document_id: int | None = None,
    source_type: str = "bare_act",
    title: str | None = None,
    metadata: dict | None = None,
) -> RetrievedChunk:
    return RetrievedChunk(
        chunk_id=idx,
        document_id=document_id if document_id is not None else idx,
        anchor=f"doc/sec-{idx}",
        text=f"chunk {idx}",
        source_type=source_type,
        subject_area=None,
        as_at=None,
        paragraph_no=None,
        title=title or f"doc {idx}",
        citation=None,
        court=None,
        statute_short=None,
        rerank_score=rerank,
        metadata=metadata or {},
    )


def test_focus_required_source_pack_normalizes_misanchored_ndps_section_37():
    chunk = _retrieved_chunk(
        37,
        rerank=0.5,
        title="Narcotic Drugs and Psychotropic Substances Act 1985",
        metadata={"section_no": "36C"},
    )
    chunk.anchor = "ndps-1985/sec-36C"
    chunk.text = (
        "Narcotic Drugs and Psychotropic Substances Act 1985, Section 36C\n\n"
        "36C. Application of Code to proceedings before a Special Court.\n"
        "37. Offences to be cognizable and non-bailable. No person accused "
        "of an offence involving commercial quantity shall be released on bail "
        "unless the court is satisfied that there are reasonable grounds for "
        "believing that he is not guilty of such offence.\n"
        "38. Offences by companies."
    )
    pack = SourcePack(
        id="ndps_1985",
        title_patterns=("Narcotic Drugs and Psychotropic Substances Act 1985",),
        search_query="NDPS Act 1985 section 37 bail section 36A Special Court",
    )

    _focus_required_source_pack_text(chunk, pack)

    assert chunk.anchor == "ndps-1985/sec-37"
    assert chunk.metadata["section_no"] == "37"
    assert chunk.text.startswith(
        "Narcotic Drugs and Psychotropic Substances Act 1985, Section 37"
    )
    assert "Offences to be cognizable and non-bailable" in chunk.text
    assert "38. Offences by companies" not in chunk.text


def test_state_specific_scheme_source_requires_matching_state_context():
    bihar_scheme = _retrieved_chunk(
        1,
        rerank=0.9,
        title="Bihar Mukhyamantri Kanya Vivah Yojana Service Description",
    )
    rti = _retrieved_chunk(2, rerank=0.8, title="Right to Information Act 2005")

    generic = _filter_query_ineligible_sources(
        "kanya vivah scheme money not given after daughter wedding",
        [bihar_scheme, rti],
    )
    assert [c.chunk_id for c in generic] == [1, 2]

    state_specific = _filter_query_ineligible_sources(
        "bihar kanya vivah scheme money not given after daughter wedding",
        [bihar_scheme, rti],
    )
    assert [c.chunk_id for c in state_specific] == [1, 2]

    for other_state_query in (
        "odisha kanya vivah scheme money not given after daughter wedding",
        "kanya vivah scheme payment pending mp",
        "kanya vivah scheme payment pending in MP",
        "kanya vivah yojana payment pending up",
        "kanya vivah yojana payment pending in U.P.",
        "jaipur kanya vivah yojana money not received",
    ):
        other_state = _filter_query_ineligible_sources(
            other_state_query,
            [bihar_scheme, rti],
        )
        assert [c.chunk_id for c in other_state] == [2]


def test_state_prohibition_case_requires_matching_state_context():
    bihar_case = _retrieved_chunk(
        1,
        rerank=0.9,
        source_type="sc_judgment",
        title="SATVINDER SINGH versus THE STATE OF BIHAR",
    )
    bnss = _retrieved_chunk(2, rerank=0.8, title="Bharatiya Nagarik Suraksha Sanhita 2023")

    generic = _filter_query_ineligible_sources(
        "police caught me drinking village they saying case under prohibition law what punishment",
        [bihar_case, bnss],
    )
    assert [c.chunk_id for c in generic] == [2]

    border_context = _filter_query_ineligible_sources(
        "police caught me drinking near bihar border in up under prohibition law",
        [bihar_case, bnss],
    )
    assert [c.chunk_id for c in border_context] == [2]

    delhi_context = _filter_query_ineligible_sources(
        "bihar police caught me drinking in delhi under prohibition law",
        [bihar_case, bnss],
    )
    assert [c.chunk_id for c in delhi_context] == [2]

    state_specific = _filter_query_ineligible_sources(
        "police caught me drinking in bihar village prohibition law punishment",
        [bihar_case, bnss],
    )
    assert [c.chunk_id for c in state_specific] == [1, 2]

    bihar_act = _retrieved_chunk(
        3,
        rerank=0.95,
        title="Bihar Prohibition and Excise Act 2016",
    )
    act_generic = _filter_query_ineligible_sources(
        "police caught me drinking village they saying case under prohibition law what punishment",
        [bihar_act, bnss],
    )
    assert [c.chunk_id for c in act_generic] == [2]


def test_constitution_article_47_source_pack_focuses_packed_chunk_text():
    chunk = _retrieved_chunk(
        1,
        rerank=0.9,
        title="Constitution of India",
        source_type="bare_act",
    )
    chunk.anchor = "constitution-india/sec-44"
    chunk.text = (
        "Constitution of India, Section 44\n\n"
        "44. Uniform civil code for the citizens. Text.\n"
        "46. Promotion of educational and economic interests of Scheduled Castes.\n"
        "47. Duty of the State to raise the level of nutrition and the standard "
        "of living and to improve public health.—The State shall endeavour to "
        "bring about prohibition of intoxicating drinks."
    )
    pack = SourcePack(
        id="constitution_article_47",
        title_patterns=("Constitution of India",),
        search_query="Constitution of India Article 47 prohibition intoxicating drinks",
        doc_ids=("constitution-india",),
        anchor_patterns=("/sec-44",),
    )

    _focus_required_source_pack_text(chunk, pack)

    assert chunk.text.startswith("Constitution of India, Article 47")
    assert "prohibition of intoxicating drinks" in chunk.text
    assert "Uniform civil code" not in chunk.text


class _StubPool:
    def __init__(self, conn):
        self.conn = conn

    def acquire(self):
        conn = self.conn

        class _Ctx:
            async def __aenter__(self):
                return conn

            async def __aexit__(self, exc_type, exc, tb):
                return False

        return _Ctx()


# ---------------------------------------------------------------------------
# Sparse retrieval — SQL + scoring semantics
# ---------------------------------------------------------------------------


class _StubConn:
    """Minimal asyncpg-like connection that records the SQL it was asked
    to run and returns a canned response.

    Tests use this to verify that `sparse_retrieve` issues the right SQL
    shape and parameter layout without needing a real Postgres.
    """

    def __init__(self, fetch_return=None):
        self.fetch_calls: list[tuple[str, tuple]] = []
        self._fetch_return = fetch_return or []

    async def fetch(self, sql, *params):
        self.fetch_calls.append((sql, params))
        return self._fetch_return


def test_required_source_pack_with_anchor_patterns_filters_to_anchors():
    conn = _StubConn(fetch_return=[])
    pack = SourcePack(
        id="rpa_1951",
        title_patterns=("Representation of the People Act 1951",),
        doc_ids=("rpa-1951",),
        anchor_patterns=("/sec-62@",),
        search_query="Representation of the People Act 1951 section 62 right to vote",
    )

    asyncio.run(
        _fetch_source_pack_candidates(
            _StubPool(conn),
            "denied vote",
            packs=[pack],
            limit_per_pack=4,
        )
    )

    assert conn.fetch_calls
    sql, params = conn.fetch_calls[0]
    assert "cardinality($4::text[]) = 0" in sql
    assert "c.metadata->>'section_no' = ANY($4::text[])" in sql
    assert "c.anchor ~* ANY($5::text[])" in sql
    assert "array_position($4::text[], c.metadata->>'section_no')" in sql
    assert "anchor_order ASC" in sql
    assert params[3] == ["62"]
    assert params[4] == [
        r"(^|/)sec-62(@|-|__|$)",
        r"(^|[#/])sec\-62($|@|__)",
    ]


def test_required_source_pack_literal_anchor_patterns_are_exactly_bounded():
    conn = _StubConn(fetch_return=[])
    pack = SourcePack(
        id="deptpub_name_change_adult_formalities",
        title_patterns=("Department of Publication Guidelines for Change of Name",),
        doc_ids=("deptpub-name-change-adult-guidelines",),
        anchor_patterns=("adult-formalities",),
        search_query="Department of Publication name change adult formalities",
        source_types=("circular",),
    )

    asyncio.run(
        _fetch_source_pack_candidates(
            _StubPool(conn),
            "change surname after marriage",
            packs=[pack],
            limit_per_pack=4,
        )
    )

    assert conn.fetch_calls
    _, params = conn.fetch_calls[0]
    assert params[3] == []
    assert params[4] == [r"(^|[#/])adult\-formalities($|@|__)"]


def test_source_pack_anchor_patterns_use_exact_section_boundaries():
    section_nos = _section_numbers_from_anchor_patterns((
        "/sec-3",
        "/sec-33A@",
        "/sec-13-b",
        "sec-71-a",
        "surrogacy-2021/sec-4-",
    ))

    assert section_nos == ["3", "33A", "13B", "71A", "4"]
    assert _anchor_boundary_regexes(["3"]) == [r"(^|/)sec-3(@|-|__|$)"]


def test_source_pack_anchor_patterns_allow_literal_non_section_anchors():
    anchor_regexes = _anchor_regexes_from_patterns((
        "adult-required-documents",
        "/sec-3",
    ))

    assert anchor_regexes == [
        r"(^|/)sec-3(@|-|__|$)",
        r"(^|[#/])adult\-required\-documents($|@|__)",
        r"(^|[#/])sec\-3($|@|__)",
    ]


def test_sparse_retrieve_empty_query_returns_nothing():
    """When the query has no sparse tokens (e.g. all stopwords or OOV
    after BERT tokenization) we MUST NOT issue a full-table scan with a
    zero-product sum. Early-return is the only correct behaviour.
    """
    conn = _StubConn()
    out = asyncio.run(
        sparse_retrieve(
            conn,
            {},
            top_k=100,
            where_clause="NOT c.quarantined",
            where_params=[],
        )
    )
    assert out == []
    assert not conn.fetch_calls, (
        f"empty query must short-circuit; instead issued {len(conn.fetch_calls)} SQL calls"
    )


def test_sparse_retrieve_builds_jsonb_dot_product_sql():
    """A real query should send a SQL that:
      * passes the query sparse vector as a JSONB literal
      * uses the GIN-backed ?| prefilter so only chunks sharing ≥1 token
        with the query are scored
      * does the SPLADE-style dot product via jsonb_each_text + SUM
      * limits to top_k

    We don't run the SQL — we just inspect the shape and the params.
    """
    conn = _StubConn(fetch_return=[])
    q_sparse = {"123": 0.42, "456": 0.13}
    asyncio.run(
        sparse_retrieve(
            conn,
            q_sparse,
            top_k=25,
            where_clause="NOT c.quarantined AND c.subject_area = ANY($1)",
            where_params=[["criminal"]],
        )
    )
    assert len(conn.fetch_calls) == 1
    sql, params = conn.fetch_calls[0]

    # Shape: JSONB dot product over overlapping keys
    assert "jsonb_each_text" in sql
    assert "embedding_sparse->>kv.key" in sql, (
        f"missing the per-token weight lookup expression in sparse SQL:\n{sql}"
    )
    # The GIN prefilter (any-key-in-array)
    assert "?| " in sql, f"missing GIN prefilter (?| operator) in sparse SQL:\n{sql}"
    # The query JSONB itself is passed as a param
    assert json.dumps(q_sparse, separators=(",", ":")) in params, (
        f"query sparse JSONB not in params: {params}"
    )
    # Top-K propagation
    assert 25 in params, f"top_k not in params: {params}"
    # The where_params (subject_area=ANY) are preserved at the front
    assert params[0] == ["criminal"], f"where_params lost position: {params}"


def test_fielded_bm25_sql_scores_legal_structure_fields():
    sql = _bm25_retrieve_sql(
        where_clause="NOT c.quarantined AND c.subject_area = ANY($1)",
        where_param_count=1,
        fielded=True,
    )

    assert "WITH q AS" in sql
    assert "ts_rank_cd" in sql
    assert "full_tsq" in sql
    assert "any_tsq" in sql
    assert "target_secs" in sql
    assert "websearch_to_tsquery" in sql
    assert "regexp_matches" in sql
    assert "setweight(to_tsvector('english', coalesce(d.title" in sql
    assert "setweight(to_tsvector('english', coalesce(d.statute_short" in sql
    assert "setweight(to_tsvector('english', coalesce(d.doc_id" in sql
    assert "setweight(to_tsvector('english', c.anchor" in sql
    assert "setweight(coalesce(c.text_tsv" in sql
    assert "to_tsvector('english', coalesce(d.title" in sql
    assert "to_tsvector('english', c.anchor) @@ q.any_tsq" in sql
    assert "lower(c.anchor) LIKE '%/sec-'" in sql
    assert "c.anchor NOT ILIKE '%#header%'" in sql
    assert "LIMIT $3" in sql


def test_legacy_bm25_sql_keeps_text_tsv_only_path():
    sql = _bm25_retrieve_sql(
        where_clause="NOT c.quarantined",
        where_param_count=0,
        fielded=False,
    )

    assert "ts_rank(c.text_tsv" in sql
    assert "c.text_tsv @@ plainto_tsquery" in sql
    assert "title_tsv" not in sql
    assert "LIMIT $2" in sql


# ---------------------------------------------------------------------------
# Config knobs
# ---------------------------------------------------------------------------


class TestHybridModeConfig:
    """Verify the hybrid_mode and sparse_top_k knobs round-trip through
    Settings (constructor + env var override). These are the levers an
    operator uses to A/B sparse retrieval against the legacy 70/30 mix.
    """

    def test_hybrid_mode_defaults_to_dense_sparse_bm25(self):
        s = Settings(database_url="postgresql://x")
        assert s.hybrid_mode == "dense_sparse_bm25"
        assert s.sparse_top_k == 100
        assert s.rrf_k == 60

    def test_hybrid_mode_env_override(self, monkeypatch):
        """HYBRID_MODE=dense_bm25 must reach the Settings object so an
        operator can ablate the sparse head without code edits."""
        monkeypatch.setenv("HYBRID_MODE", "dense_bm25")
        s = Settings(database_url="postgresql://x")
        assert s.hybrid_mode == "dense_bm25"

    def test_embedding_runtime_defaults_to_flag(self):
        """The multi-head runtime must be the default — that's the
        whole point of architecture-research Task #3. Anyone who needs
        the legacy sentence-transformers-only path sets
        EMBEDDING_RUNTIME=st."""
        s = Settings(database_url="postgresql://x")
        assert s.embedding_runtime == "flag"

    def test_fielded_bm25_defaults_on(self):
        s = Settings(database_url="postgresql://x")
        assert s.fielded_bm25_enabled is True
        assert s.fielded_bm25_top_k == 50


# ---------------------------------------------------------------------------
# Sparse vector shape — real BGE-M3 forward pass
# ---------------------------------------------------------------------------


@pytest.mark.needs_models
def test_sparse_vector_shape():
    """Confirm the embedder returns a dict-shaped sparse vector with
    string keys and finite float values from a single forward pass.

    This is the contract `backfill_sparse_embeddings.py` relies on.
    Marked `needs_models` because it actually loads BGE-M3 (~2 GB
    download on cold cache).
    """
    from apps.api.embeddings import FlagEmbeddingWorker

    worker = FlagEmbeddingWorker("BAAI/bge-m3", max_seq_len=256, device="mps")
    dense, sparse_list = worker.encode_with_sparse(
        ["Section 154(3) Cr.P.C. provides for the registration of FIRs"]
    )
    assert dense.shape == (1, 1024), f"unexpected dense shape: {dense.shape}"
    assert len(sparse_list) == 1
    sparse = sparse_list[0]
    assert isinstance(sparse, dict), f"sparse should be dict, got {type(sparse)}"
    assert sparse, "sparse vector should not be empty for a non-trivial query"
    # All keys must be JSON-serializable strings (token ids)
    for k in sparse:
        assert isinstance(k, str), f"key {k!r} not a string"
    # All values must be positive floats (zero-weight tokens dropped)
    for v in sparse.values():
        assert isinstance(v, float)
        assert v > 0.0, f"unexpected zero-weight value: {v}"
    # Section / 154 / Cr.P.C. should produce a usefully-sized sparse vector
    assert 5 <= len(sparse) <= 200, (
        f"sparse vector size {len(sparse)} outside expected band (5-200)"
    )


@pytest.mark.needs_models
def test_sparse_retrieve_finds_exact_section_reference():
    """End-to-end sanity test of the exact failure mode the audit
    flagged: a query like 'Section 154(3)' MUST surface a chunk that
    contains 'Section 154(3) Cr.P.C.' verbatim via the sparse head,
    even when dense retrieval would not rank it in the top-K.

    This is a contract test for the sparse pipeline itself — the
    embedder's lexical weights must overlap meaningfully between the
    query and the chunk on tokens like '154', 'Cr.P.C.', 'Section'.
    We score (query_sparse · chunk_sparse) in Python (mirroring the
    JSONB SQL) and assert the gold chunk beats two distractor chunks.
    """
    from apps.api.embeddings import FlagEmbeddingWorker

    worker = FlagEmbeddingWorker("BAAI/bge-m3", max_seq_len=256, device="mps")
    query = "Section 154(3) Cr.P.C."
    gold = (
        "Section 154(3) of the Code of Criminal Procedure (Cr.P.C.) "
        "provides that if the officer-in-charge refuses to record a "
        "First Information Report, the aggrieved person may send the "
        "substance of the information in writing and by post to the "
        "Superintendent of Police concerned."
    )
    # Two intentionally off-topic distractors
    d1 = (
        "The Indian Contract Act 1872 codifies obligations between "
        "parties — Sections 2 to 75 define the formation of valid "
        "contracts, consideration, and free consent."
    )
    d2 = (
        "Under the Motor Vehicles Act 1988, claim petitions for "
        "compensation are heard by the Motor Accidents Claims Tribunal "
        "established under Section 165."
    )

    _, sparse = worker.encode_with_sparse([query, gold, d1, d2])
    qs, gs, ds1, ds2 = sparse

    def dot(a: dict[str, float], b: dict[str, float]) -> float:
        return sum(a[k] * b[k] for k in set(a) & set(b))

    score_gold = dot(qs, gs)
    score_d1 = dot(qs, ds1)
    score_d2 = dot(qs, ds2)

    assert score_gold > score_d1, (
        f"sparse retrieval should pick the gold passage over a contract-act "
        f"distractor (gold={score_gold:.4f} vs d1={score_d1:.4f})"
    )
    assert score_gold > score_d2, (
        f"sparse retrieval should pick the gold passage over a motor-vehicles "
        f"distractor (gold={score_gold:.4f} vs d2={score_d2:.4f})"
    )
