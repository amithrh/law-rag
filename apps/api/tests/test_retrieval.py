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
    _preserve_required_source_packs,
    rrf_fuse,
    sparse_retrieve,
)


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


def _retrieved_chunk(
    idx: int,
    *,
    rerank: float,
    metadata: dict | None = None,
) -> RetrievedChunk:
    return RetrievedChunk(
        chunk_id=idx,
        document_id=idx,
        anchor=f"doc/sec-{idx}",
        text=f"chunk {idx}",
        source_type="bare_act",
        subject_area=None,
        as_at=None,
        paragraph_no=None,
        title=f"doc {idx}",
        citation=None,
        court=None,
        statute_short=None,
        rerank_score=rerank,
        metadata=metadata or {},
    )


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
