"""Multi-head hybrid retrieval: BGE-M3 dense + BGE-M3 sparse + Postgres BM25.

Per docs/RETRIEVAL_AUDIT.md (recall@20 = 53%), the production setup —
dense ANN + Postgres `english` tsvector BM25, blended 70/30 — fails on
exact-citation / statute-section queries where the gold passage's text
doesn't share lexical overlap with the user's phrasing (e.g. "punishment
for theft" not finding "Section 379 — Theft"). The architecture-research
roadmap pinpoints learned-sparse retrieval (BGE-M3 lexical-weights head)
as the #1 ROI fix because (a) it's exactly the gap dense embeddings
have and (b) BGE-M3 already emits it from the same forward pass we pay
for today.

Pipeline (`hybrid_mode='dense_sparse_bm25'`):

  Stage 1 — three retrievers in parallel against `chunks`:
    1a. Dense    (HNSW on `embedding`,         top `dense_top_k`)
    1b. Sparse   (JSONB dot product on
                  `embedding_sparse`,           top `sparse_top_k`)
    1c. BM25     (tsvector match on `text_tsv`, top `bm25_top_k`)

  Stage 2 — RRF fusion (Cormack et al., k=60):
    For each chunk, its fused score is
        Σ over heads h:  1 / (rrf_k + rank_h)
    where rank_h is the 1-based rank from head h (or absent if the
    chunk wasn't surfaced by that head).

  Stage 3 — optional cross-encoder rerank (bge-reranker-v2-m3) over
    the top `rerank_input_k` fused candidates, keep top `top_k`.

  Stage 4 — LLM consumes the final top K (K=8 by default).

The legacy mode `hybrid_mode='dense_bm25'` keeps the 70/30 weighted-sum
behavior for A/B comparison and for environments where the sparse
column hasn't been backfilled.
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import date

import asyncpg

from apps.api.config import get_settings
from apps.api.embeddings import embedding_to_halfvec_literal, get_embedder

logger = logging.getLogger(__name__)


@dataclass
class RetrievedChunk:
    chunk_id: int
    document_id: int
    anchor: str
    text: str
    source_type: str
    subject_area: str | None
    as_at: date | None
    paragraph_no: int | None
    title: str
    citation: str | None
    court: str | None
    statute_short: str | None
    dense_score: float = 0.0
    bm25_score: float = 0.0
    sparse_score: float = 0.0
    rerank_score: float | None = None
    # RRF fused score across whichever heads contributed. None if not
    # produced by the RRF path (e.g. legacy `dense_bm25` mode).
    rrf_score: float | None = None
    metadata: dict = field(default_factory=dict)

    @property
    def combined_score(self) -> float:
        """Legacy pre-rerank ordering for `hybrid_mode='dense_bm25'`.

        For `dense_sparse_bm25` use `rrf_score` instead — RRF is the
        correct fusion because dense / sparse / BM25 scores live on
        non-commensurate scales (cosine ≤ 1, BM25 ts_rank unbounded,
        sparse dot-product depends on token frequency).
        """
        return 0.7 * self.dense_score + 0.3 * self.bm25_score


# ---------------------------------------------------------------------------
# RRF helper — exported for tests.
# ---------------------------------------------------------------------------


def rrf_fuse(
    rankings: list[list[int]],
    *,
    k: int = 60,
) -> dict[int, float]:
    """Reciprocal-Rank-Fusion over multiple ranked id lists.

    Each input list is an ordered ranking (rank 1 first). Returns a dict
    mapping id → fused RRF score. Per Cormack et al. (2009) the score is

        score(d) = Σ_h  1 / (k + rank_h(d))

    where the sum is over heads that surfaced `d`. Ranks are 1-based;
    a doc not in a head's ranking contributes 0 for that head.

    `k=60` is the canonical default — it dampens rank-1 dominance enough
    that two heads agreeing weakly (e.g. rank 3 and rank 5) beats one
    head ranking the doc 1st alone. Lower k privileges the top of each
    list; higher k flattens contributions.
    """
    out: dict[int, float] = {}
    for ranking in rankings:
        for rank_idx, chunk_id in enumerate(ranking, start=1):
            out[chunk_id] = out.get(chunk_id, 0.0) + 1.0 / (k + rank_idx)
    return out


# ---------------------------------------------------------------------------
# Sparse retrieval — JSONB dot product
# ---------------------------------------------------------------------------


async def sparse_retrieve(
    pool_or_conn,
    query_sparse: dict[str, float],
    *,
    top_k: int,
    where_clause: str,
    where_params: list,
) -> list:
    """Run sparse retrieval against the `embedding_sparse` JSONB column.

    Scoring: for each chunk whose sparse vector shares ≥1 token with the
    query, compute `Σ_token  query[token] * chunk[token]` (the standard
    SPLADE-style dot product over overlapping tokens). Top-K by score.

    JSONB shape (per `embedding_sparse` column): `{token_id_str: weight}`.

    SQL strategy:
      1. Materialize the query's sparse vector as a small JSONB literal.
      2. For each candidate chunk in the filtered set, unpack the query
         JSONB with `jsonb_each_text`, look up the matching key in the
         chunk's JSONB with `embedding_sparse->>key`, multiply, sum.
      3. The GIN index `idx_chunks_sparse_gin` (jsonb_path_ops) gives us
         a cheap "JSONB ?| array[query keys]" prefilter so we don't scan
         every row.

    The function takes an open connection rather than a pool because the
    caller already holds the pool acquisition (we want all three head
    queries in one acquire) and the dense path needs `SET LOCAL` state.
    """
    if not query_sparse:
        # No tokens in the query (very short / OOV input). Return nothing
        # rather than scanning all chunks for a zero-product sum.
        return []

    query_jsonb = json.dumps(query_sparse, separators=(",", ":"))
    query_keys = list(query_sparse.keys())

    # Param layout:
    #   $1..len(where_params) → existing filter params (subject_area, etc.)
    #   $N+1                  → query_jsonb (JSONB literal)
    #   $N+2                  → query_keys  (text[] for the GIN prefilter)
    #   $N+3                  → top_k
    base = len(where_params)
    params = where_params + [query_jsonb, query_keys, top_k]

    # The CTE `q` materializes the query JSONB once. The main SELECT
    # joins each chunk's sparse vector against q via `jsonb_each_text`
    # and sums the multiplied weights. The GIN-backed `?|` operator
    # restricts the candidate set to chunks that share at least one
    # token with the query.
    sql = f"""
        WITH q AS (SELECT ${base+1}::jsonb AS qs)
        SELECT c.id, c.document_id, c.anchor, c.text, c.source_type,
               c.subject_area, c.as_at, c.paragraph_no, c.metadata,
               d.title, d.citation, d.court, d.statute_short,
               (
                   SELECT COALESCE(SUM(
                       (kv.value)::float8
                       * (c.embedding_sparse->>kv.key)::float8
                   ), 0.0)
                   FROM jsonb_each_text((SELECT qs FROM q)) AS kv
                   WHERE c.embedding_sparse ? kv.key
               ) AS sparse_score
        FROM chunks c
        JOIN documents d ON d.id = c.document_id
        WHERE {where_clause}
          AND c.embedding_sparse IS NOT NULL
          AND c.embedding_sparse ?| ${base+2}::text[]
        ORDER BY sparse_score DESC
        LIMIT ${base+3}
    """
    return await pool_or_conn.fetch(sql, *params)


# ---------------------------------------------------------------------------
# Hybrid retrieval — orchestrator
# ---------------------------------------------------------------------------


async def hybrid_retrieve(
    pool: asyncpg.Pool,
    query: str,
    *,
    source_types: list[str] | None = None,
    subject_areas: list[str] | None = None,
    as_of: date | None = None,
    top_k: int | None = None,
    use_reranker: bool | None = None,
) -> list[RetrievedChunk]:
    """Three-source hybrid retrieval with RRF fusion (or legacy 70/30).

    The mode is set by `settings.hybrid_mode`. `dense_sparse_bm25` (default)
    runs all three heads and fuses via RRF. `dense_bm25` runs only dense +
    BM25 and uses the legacy weighted-sum order.

    `use_reranker=False` disables the cross-encoder rerank stage; useful
    for ablation studies. Falls back to the pre-rerank order if the
    reranker is unavailable.
    """
    s = get_settings()
    if top_k is None:
        top_k = s.rerank_top_k

    embedder = get_embedder()
    use_sparse = s.hybrid_mode == "dense_sparse_bm25"

    # Query embedding(s). On the flag-embedding runtime we can get dense
    # AND sparse from one forward pass; on the sentence-transformers
    # runtime we can only get dense, in which case we silently fall back
    # to dense+bm25 (logged so operators notice).
    q_sparse: dict[str, float] | None = None
    if use_sparse and hasattr(embedder, "encode_with_sparse"):
        try:
            d_arr, s_list = embedder.encode_with_sparse([query])
            q_vec = d_arr[0]
            q_sparse = s_list[0]
        except NotImplementedError:
            logger.warning(
                "hybrid_retrieve: embedder doesn't support sparse; "
                "falling back to dense+bm25 for this query",
            )
            q_vec = embedder.encode_one(query)
            use_sparse = False
    else:
        if use_sparse:
            logger.warning(
                "hybrid_retrieve: embedding_runtime doesn't expose sparse; "
                "running dense+bm25 instead. Set embedding_runtime='flag'.",
            )
            use_sparse = False
        q_vec = embedder.encode_one(query)

    q_vec_lit = embedding_to_halfvec_literal(q_vec)

    # Filters as SQL fragments
    where: list[str] = ["NOT c.quarantined"]
    params: list = []
    if source_types:
        params.append(source_types)
        where.append(f"c.source_type = ANY(${len(params)})")
    if subject_areas:
        params.append(subject_areas)
        where.append(f"c.subject_area = ANY(${len(params)})")
    if as_of:
        # For statute chunks, prefer versions whose as_at <= as_of.
        # Judgment chunks have no as_at (NULL) and pass through.
        params.append(as_of)
        where.append(f"(c.as_at IS NULL OR c.as_at <= ${len(params)})")

    # Provenance gate: in production mode, only return chunks from documents
    # whose source has been verified against the canonical Govt source.
    if s.require_provenance_verified:
        where.append(
            "EXISTS (SELECT 1 FROM documents d2 "
            "WHERE d2.id = c.document_id AND d2.provenance_verified = true)"
        )

    where_clause = " AND ".join(where)

    async with pool.acquire() as conn:
        await conn.execute(f"SET LOCAL hnsw.ef_search = {s.hnsw_ef_search};")

        # --- Dense ANN top N ---
        dense_n = s.dense_top_k
        params_dense = params + [q_vec_lit, dense_n]
        dense_rows = await conn.fetch(
            f"""SELECT c.id, c.document_id, c.anchor, c.text, c.source_type,
                       c.subject_area, c.as_at, c.paragraph_no, c.metadata,
                       d.title, d.citation, d.court, d.statute_short,
                       1 - (c.embedding <=> ${len(params)+1}::halfvec) AS dense_score
                FROM chunks c JOIN documents d ON d.id = c.document_id
                WHERE {where_clause}
                ORDER BY c.embedding <=> ${len(params)+1}::halfvec
                LIMIT ${len(params)+2}""",
            *params_dense,
        )

        # --- BM25 top N ---
        bm25_n = s.bm25_top_k
        params_bm25 = params + [query, bm25_n]
        bm25_rows = await conn.fetch(
            f"""SELECT c.id, c.document_id, c.anchor, c.text, c.source_type,
                       c.subject_area, c.as_at, c.paragraph_no, c.metadata,
                       d.title, d.citation, d.court, d.statute_short,
                       ts_rank(c.text_tsv, plainto_tsquery('english', ${len(params)+1})) AS bm25_score
                FROM chunks c JOIN documents d ON d.id = c.document_id
                WHERE {where_clause}
                  AND c.text_tsv @@ plainto_tsquery('english', ${len(params)+1})
                ORDER BY bm25_score DESC
                LIMIT ${len(params)+2}""",
            *params_bm25,
        )

        # --- Sparse top N (when enabled) ---
        sparse_rows: list = []
        if use_sparse and q_sparse:
            sparse_rows = await sparse_retrieve(
                conn,
                q_sparse,
                top_k=s.sparse_top_k,
                where_clause=where_clause,
                where_params=params,
            )

    # ---- Union + dedupe by chunk.id ----
    merged: dict[int, RetrievedChunk] = {}

    def _hydrate(r) -> RetrievedChunk:
        return RetrievedChunk(
            chunk_id=r["id"], document_id=r["document_id"], anchor=r["anchor"],
            text=r["text"], source_type=r["source_type"], subject_area=r["subject_area"],
            as_at=r["as_at"], paragraph_no=r["paragraph_no"],
            title=r["title"], citation=r["citation"], court=r["court"],
            statute_short=r["statute_short"],
            metadata=r["metadata"] if isinstance(r["metadata"], dict) else {},
        )

    for r in dense_rows:
        if r["id"] not in merged:
            merged[r["id"]] = _hydrate(r)
        merged[r["id"]].dense_score = float(r["dense_score"])
    for r in bm25_rows:
        if r["id"] not in merged:
            merged[r["id"]] = _hydrate(r)
        merged[r["id"]].bm25_score = float(r["bm25_score"])
    for r in sparse_rows:
        if r["id"] not in merged:
            merged[r["id"]] = _hydrate(r)
        merged[r["id"]].sparse_score = float(r["sparse_score"])

    # ---- Stage 1.5 — fuse (RRF when multi-head, weighted-sum otherwise) ----
    if use_sparse:
        # Build per-head rankings (ids in score-descending order).
        dense_ids = [r["id"] for r in dense_rows]
        bm25_ids = [r["id"] for r in bm25_rows]
        sparse_ids = [r["id"] for r in sparse_rows]
        fused = rrf_fuse([dense_ids, sparse_ids, bm25_ids], k=s.rrf_k)
        for cid, score in fused.items():
            if cid in merged:
                merged[cid].rrf_score = score
        # Order by RRF first, then by combined_score as tie-breaker
        # (rare — only when two chunks were never co-ranked).
        out = sorted(
            merged.values(),
            key=lambda c: (
                c.rrf_score if c.rrf_score is not None else 0.0,
                c.combined_score,
            ),
            reverse=True,
        )
    else:
        out = sorted(merged.values(), key=lambda c: c.combined_score, reverse=True)

    # Stage 2: cross-encoder rerank top N candidates
    do_rerank = use_reranker if use_reranker is not None else s.rerank_enabled
    if do_rerank and out:
        from apps.api.rerank import rerank as _rerank
        candidates = out[: s.rerank_input_k]
        reranked = _rerank(query, candidates, keep=top_k)
        logger.info(
            "hybrid_retrieve[%s]: %d dense + %d bm25 + %d sparse → %d merged → "
            "rerank(%d) → top %d",
            s.hybrid_mode,
            len(dense_rows), len(bm25_rows), len(sparse_rows),
            len(merged), len(candidates), len(reranked),
        )
        return reranked

    logger.info(
        "hybrid_retrieve[%s]: %d dense + %d bm25 + %d sparse → %d merged → "
        "top %d (no rerank)",
        s.hybrid_mode,
        len(dense_rows), len(bm25_rows), len(sparse_rows),
        len(merged), min(top_k, len(out)),
    )
    return out[:top_k]


__all__ = ["RetrievedChunk", "hybrid_retrieve", "rrf_fuse", "sparse_retrieve"]
