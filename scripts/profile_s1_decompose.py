#!/usr/bin/env python3
"""Decompose S1 (retrieval+expansion stage) into its components.

S1 covers everything between request start and the first 'passages' SSE:
  - LLM expand_query (qwen3:14b on Ollama)
  - 4× hybrid_retrieve (dense + sparse + BM25 against Postgres)
  - dedupe + cap at rerank_input_k
  - 4× rerank pass against rerank_input_k candidates
  - sort + select top_k passages

Run each piece in isolation to attribute the 60+ second observed cost.
"""
from __future__ import annotations

import asyncio
import time

from apps.api.config import get_settings
from apps.api.db import get_pool
from apps.api.query_expand import expand_query
from apps.api.rerank import rerank
from apps.api.retrieval import hybrid_retrieve

QUERIES = [
    "my landlord is not returning my deposit money",
    "section 138 NI Act notice 30 days time limit",
    "my husband is beating me what can I do",
]


async def time_expand(q: str) -> tuple[float, list[str]]:
    t0 = time.monotonic()
    variants = await expand_query(q)
    return time.monotonic() - t0, variants


async def time_one_retrieve(pool, q: str, top_k: int) -> tuple[float, int]:
    t0 = time.monotonic()
    chunks = await hybrid_retrieve(
        pool, q, top_k=top_k, use_reranker=False,
    )
    return time.monotonic() - t0, len(chunks)


def time_one_rerank(q: str, chunks) -> float:
    t0 = time.monotonic()
    rerank(q, list(chunks), keep=None)
    return time.monotonic() - t0


async def profile_one(q: str) -> dict:
    s = get_settings()
    pool = await get_pool()

    # 1. Query expansion (LLM)
    t_expand, variants = await time_expand(q)

    # 2. Hybrid retrieve per variant (sequential, then divide).
    # NOTE the production code calls these in parallel via asyncio.gather,
    # so the wallclock cost should be ~= max(times), not sum. Measure
    # both for clarity.
    seq_total = 0.0
    per_variant = []
    for v in variants:
        elapsed, n = await time_one_retrieve(pool, v, top_k=s.rerank_input_k)
        per_variant.append((v[:50], elapsed, n))
        seq_total += elapsed

    # Parallel version (same as production)
    t_par_start = time.monotonic()
    parallel_results = await asyncio.gather(
        *[
            hybrid_retrieve(pool, v, top_k=s.rerank_input_k, use_reranker=False)
            for v in variants
        ],
    )
    t_par = time.monotonic() - t_par_start

    # 3. Reranker against original (single pass)
    # First union and cap (matching production)
    union: dict[int, object] = {}
    for variant_result in parallel_results:
        for c in variant_result:
            existing = union.get(c.chunk_id)
            if existing is None or (c.combined_score > existing.combined_score):
                union[c.chunk_id] = c
    candidate_list = sorted(union.values(), key=lambda c: c.combined_score, reverse=True)
    candidate_list = candidate_list[: s.rerank_input_k]

    rerank_times = []
    for v in variants:
        rerank_times.append(time_one_rerank(v, candidate_list))

    return {
        "query": q,
        "n_variants": len(variants),
        "variants": variants,
        "t_expand": t_expand,
        "per_variant_retrieve": per_variant,
        "seq_total_retrieve": seq_total,
        "parallel_retrieve_wallclock": t_par,
        "rerank_times_per_variant": rerank_times,
        "rerank_total": sum(rerank_times),
        "union_size": len(union),
        "candidate_list_size": len(candidate_list),
    }


async def main():
    for q in QUERIES:
        print(f"\n=== {q!r} ===")
        r = await profile_one(q)
        print(f"  expand     : {r['t_expand']:>6.2f}s   ({r['n_variants']} variants)")
        for vtxt in r["variants"]:
            print(f"               > {vtxt[:80]}")
        print(f"  retrieve (sequential sum): {r['seq_total_retrieve']:>6.2f}s")
        print(f"  retrieve (parallel wallclock): {r['parallel_retrieve_wallclock']:>6.2f}s")
        for vtxt, t, n in r["per_variant_retrieve"]:
            print(f"               {t:>6.2f}s  ({n} chunks)  {vtxt}")
        print(f"  rerank-each: {r['rerank_total']:>6.2f}s   ({r['rerank_times_per_variant']})")
        print(f"  union={r['union_size']}, candidates={r['candidate_list_size']}")


if __name__ == "__main__":
    asyncio.run(main())
