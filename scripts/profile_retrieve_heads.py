#!/usr/bin/env python3
"""Decompose a single hybrid_retrieve call into its 3 SQL heads."""
from __future__ import annotations

import asyncio
import json
import time

from apps.api.config import get_settings
from apps.api.db import get_pool
from apps.api.embeddings import embedding_to_halfvec_literal, get_embedder
from apps.api.retrieval import sparse_retrieve

QUERIES = [
    "my landlord is not returning my deposit money",
    "section 138 NI Act notice 30 days time limit",
    "my husband is beating me what can I do",
]


async def profile(q: str):
    s = get_settings()
    pool = await get_pool()
    embedder = get_embedder()

    # 1. Embed
    t0 = time.monotonic()
    if hasattr(embedder, "encode_with_sparse"):
        d_arr, s_list = embedder.encode_with_sparse([q])
        q_vec = d_arr[0]
        q_sparse = s_list[0]
    else:
        q_vec = embedder.encode_one(q)
        q_sparse = None
    t_embed = time.monotonic() - t0

    q_vec_lit = embedding_to_halfvec_literal(q_vec)
    where_clause = "NOT c.quarantined"

    async with pool.acquire() as conn:
        await conn.execute(f"SET LOCAL hnsw.ef_search = {s.hnsw_ef_search};")

        # Dense
        t0 = time.monotonic()
        dense_rows = await conn.fetch(
            f"""SELECT c.id, 1 - (c.embedding <=> $1::halfvec) AS dense_score
                FROM chunks c JOIN documents d ON d.id = c.document_id
                WHERE {where_clause}
                ORDER BY c.embedding <=> $1::halfvec
                LIMIT $2""",
            q_vec_lit, s.dense_top_k,
        )
        t_dense = time.monotonic() - t0

        # BM25
        t0 = time.monotonic()
        bm25_rows = await conn.fetch(
            f"""SELECT c.id,
                       ts_rank(c.text_tsv, plainto_tsquery('english', $1)) AS bm25_score
                FROM chunks c JOIN documents d ON d.id = c.document_id
                WHERE {where_clause}
                  AND c.text_tsv @@ plainto_tsquery('english', $1)
                ORDER BY bm25_score DESC
                LIMIT $2""",
            q, s.bm25_top_k,
        )
        t_bm25 = time.monotonic() - t0

        # Sparse
        t0 = time.monotonic()
        sparse_rows = await sparse_retrieve(
            conn, q_sparse, top_k=s.sparse_top_k,
            where_clause=where_clause, where_params=[],
        ) if q_sparse else []
        t_sparse = time.monotonic() - t0

    return {
        "query": q,
        "embed": t_embed,
        "dense": t_dense,
        "bm25": t_bm25,
        "sparse": t_sparse,
        "dense_rows": len(dense_rows),
        "bm25_rows": len(bm25_rows),
        "sparse_rows": len(sparse_rows),
    }


async def main():
    print(f"{'query':<55} {'embed':>7} {'dense':>7} {'bm25':>7} {'sparse':>7}")
    for q in QUERIES:
        r = await profile(q)
        print(f"{q[:54]:<55} {r['embed']:>6.2f}s {r['dense']:>6.2f}s {r['bm25']:>6.2f}s {r['sparse']:>6.2f}s")


if __name__ == "__main__":
    asyncio.run(main())
