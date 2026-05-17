"""Hybrid retrieval: BM25 (Postgres tsvector) ∪ dense (pgvector HNSW) → rerank.

Per PLAN §2.3:
- Stage 1a: BM25 top 100 (caveat: english tsvector misses lay-vocabulary;
            confirmed weak in our acts demo; dense head carries most queries
            on this slice's data — see Q3-bench notes).
- Stage 1b: Dense bge-m3 cosine top 100.
- Stage 2: Union, dedupe by chunk id, rerank with bge-reranker-v2-m3 → top 20.
- Stage 3: LLM consumes top K (K=8 by default; configurable).
"""
from __future__ import annotations

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
    rerank_score: float | None = None
    metadata: dict = field(default_factory=dict)

    @property
    def combined_score(self) -> float:
        """For pre-rerank ordering. Reciprocal-rank-fusion would be cleaner;
        for now we use a simple weighted sum (dense gets more weight given
        the BM25-weak-on-lay-vocab finding on the acts corpus)."""
        return 0.7 * self.dense_score + 0.3 * self.bm25_score


async def hybrid_retrieve(
    pool: asyncpg.Pool,
    query: str,
    *,
    source_types: list[str] | None = None,
    subject_areas: list[str] | None = None,
    as_of: date | None = None,
    top_k: int | None = None,
) -> list[RetrievedChunk]:
    """Run BM25 + dense in parallel against `chunks`, union + dedupe.

    Returns up to `top_k` (config default `rerank_top_k`) chunks ordered by
    `combined_score`. Caller is responsible for reranking + LLM hand-off.
    """
    s = get_settings()
    if top_k is None:
        top_k = s.rerank_top_k

    embedder = get_embedder()
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
    where_clause = " AND ".join(where)

    async with pool.acquire() as conn:
        await conn.execute(f"SET LOCAL hnsw.ef_search = {s.hnsw_ef_search};")

        # Dense ANN top N
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

        # BM25 top N
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

    # Union + dedupe by chunk.id
    merged: dict[int, RetrievedChunk] = {}
    for r in dense_rows:
        merged[r["id"]] = RetrievedChunk(
            chunk_id=r["id"], document_id=r["document_id"], anchor=r["anchor"],
            text=r["text"], source_type=r["source_type"], subject_area=r["subject_area"],
            as_at=r["as_at"], paragraph_no=r["paragraph_no"],
            title=r["title"], citation=r["citation"], court=r["court"],
            statute_short=r["statute_short"],
            dense_score=float(r["dense_score"]),
            metadata=r["metadata"] if isinstance(r["metadata"], dict) else {},
        )
    for r in bm25_rows:
        if r["id"] in merged:
            merged[r["id"]].bm25_score = float(r["bm25_score"])
        else:
            merged[r["id"]] = RetrievedChunk(
                chunk_id=r["id"], document_id=r["document_id"], anchor=r["anchor"],
                text=r["text"], source_type=r["source_type"], subject_area=r["subject_area"],
                as_at=r["as_at"], paragraph_no=r["paragraph_no"],
                title=r["title"], citation=r["citation"], court=r["court"],
                statute_short=r["statute_short"],
                bm25_score=float(r["bm25_score"]),
                metadata=r["metadata"] if isinstance(r["metadata"], dict) else {},
            )

    out = sorted(merged.values(), key=lambda c: c.combined_score, reverse=True)
    logger.info("hybrid_retrieve: %d dense + %d bm25 → %d merged → top %d",
                len(dense_rows), len(bm25_rows), len(merged), min(top_k, len(out)))
    return out[:top_k]


__all__ = ["RetrievedChunk", "hybrid_retrieve"]
