#!/usr/bin/env python3
"""Validate the query expander against the 102-query eval's failures.

Strategy:
  1. Load the most-recent e2e_eval_*.jsonl.
  2. Pick the 30 lowest-relevance non-off-corpus rows (the worst
     OFF_TOPIC + REFUSED queries — these were the system's failures).
  3. For each, call `expand_query()` and run `/search?q=<variant>` for
     both the ORIGINAL and each expanded variant.
  4. Compare: did expanded retrieval surface the right bare-Act chunk?
     (Heuristic: a bare-Act chunk in the top-K, ideally with rerank
     score > 0.6.)
  5. Per-query verdict — improved / same / worse — and aggregate.

Run:
  PYTHONPATH=. .venv/bin/python scripts/eval_query_expand.py
  PYTHONPATH=. .venv/bin/python scripts/eval_query_expand.py --limit 10
"""
from __future__ import annotations

import argparse
import asyncio
import json
import re
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from apps.api.query_expand import expand_query  # noqa: E402

SC_ANCHOR_RE = re.compile(r"^\d{4}-(insc|\d+-\d+)")


def is_bare_act(anchor: str) -> bool:
    """Heuristic: anchors without YYYY-insc-N prefix are bare-act chunks."""
    if not anchor:
        return False
    if SC_ANCHOR_RE.match(anchor):
        return False
    return "/" in anchor or anchor.endswith(("#header",))


def hit_search(query: str, k: int = 8) -> list[dict]:
    """One /search call; returns the hits list."""
    url = (f"http://localhost:8000/search?q={urllib.parse.quote(query)}&k={k}")
    try:
        with urllib.request.urlopen(url, timeout=60) as f:
            return json.load(f).get("hits", [])
    except Exception as e:
        print(f"  ERR /search failed: {e}", flush=True)
        return []


def summarize_hits(hits: list[dict]) -> dict:
    """Per-query summary: top rerank, bare-act count in top-5, top-3 titles."""
    top_5 = hits[:5]
    bare = [h for h in top_5 if is_bare_act(h.get("anchor", ""))]
    top_titles = [
        {
            "title": (h.get("title") or "")[:55],
            "anchor": h.get("anchor", "")[:46],
            "rerank": h.get("rerank_score", 0.0),
            "is_act": is_bare_act(h.get("anchor", "")),
        }
        for h in top_5
    ]
    return {
        "top_rerank": top_5[0].get("rerank_score", 0.0) if top_5 else 0.0,
        "bare_act_in_top5": len(bare),
        "top_bare_act_rerank": max((h.get("rerank_score", 0.0) for h in bare), default=0.0),
        "titles": top_titles,
    }


async def evaluate_one(row: dict) -> dict:
    """For one failing query, compare original vs expanded retrieval."""
    q = row["query"]
    print(f"\n--- q={q!r} (orig: {row.get('relevance_verdict') or 'REFUSE'})", flush=True)

    # Original
    t0 = time.time()
    orig_hits = hit_search(q)
    orig_summary = summarize_hits(orig_hits)
    orig_t = time.time() - t0

    # Expand
    t0 = time.time()
    variants = await expand_query(q)
    expand_t = time.time() - t0
    print(f"  expanded ({expand_t:.2f}s):", flush=True)
    for v in variants[1:]:
        print(f"    → {v!r}", flush=True)

    # Variants — search each, gather all hits, take best per-anchor
    variant_summaries: list[dict] = [orig_summary]
    for v in variants[1:]:
        h = hit_search(v)
        variant_summaries.append(summarize_hits(h))

    # Best across all variants by per-metric max
    best = {
        "top_rerank": max(s["top_rerank"] for s in variant_summaries),
        "bare_act_in_top5": max(s["bare_act_in_top5"] for s in variant_summaries),
        "top_bare_act_rerank": max(s["top_bare_act_rerank"] for s in variant_summaries),
    }

    # Verdict: improvement if expanded surfaces a bare-Act that original missed
    improved = (
        best["bare_act_in_top5"] > orig_summary["bare_act_in_top5"]
        or (best["bare_act_in_top5"] > 0
            and best["top_bare_act_rerank"] > orig_summary["top_bare_act_rerank"] + 0.05)
    )
    same = (
        best["bare_act_in_top5"] == orig_summary["bare_act_in_top5"]
        and abs(best["top_bare_act_rerank"] - orig_summary["top_bare_act_rerank"]) < 0.05
    )

    verdict = "IMPROVED" if improved else ("SAME" if same else "WORSE")

    print(f"  orig: top_rerank={orig_summary['top_rerank']:.2f} "
          f"bare_in_top5={orig_summary['bare_act_in_top5']} "
          f"top_bare_rerank={orig_summary['top_bare_act_rerank']:.2f}", flush=True)
    print(f"  best: top_rerank={best['top_rerank']:.2f} "
          f"bare_in_top5={best['bare_act_in_top5']} "
          f"top_bare_rerank={best['top_bare_act_rerank']:.2f}  → {verdict}", flush=True)

    # Show the top-3 from the BEST variant
    best_idx = max(range(len(variant_summaries)),
                   key=lambda i: variant_summaries[i]["bare_act_in_top5"] * 100
                   + variant_summaries[i]["top_bare_act_rerank"])
    print(f"  best variant: {('ORIGINAL' if best_idx == 0 else variants[best_idx])!r}", flush=True)
    for h in variant_summaries[best_idx]["titles"][:3]:
        marker = "★" if h["is_act"] else " "
        print(f"    {marker} rerank={h['rerank']:.2f}  {h['title']:55s}  [{h['anchor']}]", flush=True)

    return {
        "query": q,
        "original_verdict": row.get("relevance_verdict"),
        "original_refused": row.get("refused", False),
        "expand_took_s": expand_t,
        "variants": variants[1:],
        "orig": orig_summary,
        "best": best,
        "best_variant_idx": best_idx,
        "best_variant": (variants[best_idx] if best_idx > 0 else "ORIGINAL"),
        "verdict": verdict,
    }


async def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--limit", type=int, default=30,
                    help="evaluate the N lowest-relevance non-off-corpus queries")
    ap.add_argument("--input", type=str, default=None,
                    help="specific e2e_eval JSONL (default: latest)")
    args = ap.parse_args()

    eval_dir = ROOT / "data" / "processed"
    files = sorted(eval_dir.glob("e2e_eval_*.jsonl"))
    if args.input:
        eval_file = Path(args.input)
    elif files:
        eval_file = files[-1]
    else:
        print("no e2e_eval_*.jsonl found", file=sys.stderr)
        sys.exit(1)

    rows: list[dict] = []
    with eval_file.open() as f:
        for line in f:
            rows.append(json.loads(line))

    # Filter to failing rows (OFF_TOPIC + REFUSED, exclude off_corpus correct refusals)
    failing = [r for r in rows
               if r.get("category") != "off_corpus"
               and (r.get("relevance_verdict") in ("off_topic", "partial")
                    or r.get("refused"))]
    failing.sort(key=lambda r: (r.get("relevance_score") or 0.0))

    print(f"=== query expansion eval on {min(args.limit, len(failing))} "
          f"failing queries from {eval_file.name} ===", flush=True)

    results = []
    for r in failing[: args.limit]:
        try:
            res = await evaluate_one(r)
        except Exception as e:
            print(f"  ERR: {e}", flush=True)
            continue
        results.append(res)

    # ---- Aggregate ----
    n = len(results)
    if not n:
        print("no results", file=sys.stderr)
        return
    improved = sum(1 for r in results if r["verdict"] == "IMPROVED")
    same = sum(1 for r in results if r["verdict"] == "SAME")
    worse = sum(1 for r in results if r["verdict"] == "WORSE")

    avg_expand_t = sum(r["expand_took_s"] for r in results) / n

    print(f"\n=== Aggregate ({n} queries) ===")
    print(f"  IMPROVED: {improved}  ({100 * improved / n:.0f}%)")
    print(f"  SAME    : {same}  ({100 * same / n:.0f}%)")
    print(f"  WORSE   : {worse}  ({100 * worse / n:.0f}%)")
    print(f"  expansion latency avg: {avg_expand_t:.2f}s")

    # Bare-act surface rate improvement
    orig_with_act = sum(1 for r in results if r["orig"]["bare_act_in_top5"] > 0)
    best_with_act = sum(1 for r in results if r["best"]["bare_act_in_top5"] > 0)
    print(f"  bare-act in top-5: {orig_with_act}/{n} (original) → "
          f"{best_with_act}/{n} (with expansion)")


if __name__ == "__main__":
    asyncio.run(main())
