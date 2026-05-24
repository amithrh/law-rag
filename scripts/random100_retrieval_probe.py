#!/usr/bin/env python3
"""100-query retrieval probe — runs alongside the main eval without
contending on the LLM (uses /search, not /answer).

Why this exists:
  - The main 500-query eval is /answer-based: 57s/query, full pipeline,
    LLM-bound. Contending another /answer load would halve throughput.
  - But retrieval quality is a *separable* concern: does the right
    bare-Act / SC paragraph appear in the top-5 hits BEFORE the LLM
    sees them?
  - This probe samples 100 random queries from data/eval_500/*.jsonl
    and hits /search (retrieval-only, ~2-3s/query, no LLM, minimal GPU
    contention with /answer).

What gets measured per query:
  - Top-1 source_type + anchor
  - Top-5 source_type distribution
  - **act_hint_hit**: if the query row has expected_act_hint, did any
    top-5 hit's title or anchor match the hint (case-insensitive
    substring)? This is the cleanest retrieval-recall signal.
  - Latency

Output:
  data/processed/random100_retrieval_<ts>.jsonl  — per-query rows
  + summary printed to stdout

Usage:
  PYTHONPATH=. .venv/bin/python scripts/random100_retrieval_probe.py
"""
from __future__ import annotations

import argparse
import json
import random
import sys
import time
import urllib.parse
import urllib.request
from collections import Counter
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).parent.parent
API_URL = "http://localhost:8000/search"
SEED = 42


def load_corpus(folder: Path) -> list[dict]:
    rows: list[dict] = []
    for fp in sorted(folder.glob("*.jsonl")):
        persona = fp.stem
        with fp.open() as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                d = json.loads(line)
                d["persona"] = persona
                rows.append(d)
    return rows


def search(q: str, top_k: int = 5, timeout_s: int = 30) -> dict:
    qs = urllib.parse.urlencode({"q": q, "top_k": top_k})
    req = urllib.request.Request(f"{API_URL}?{qs}")
    t0 = time.time()
    try:
        with urllib.request.urlopen(req, timeout=timeout_s) as f:
            data = json.loads(f.read().decode())
        return {**data, "took_s": round(time.time() - t0, 2), "error": None}
    except Exception as e:
        return {"query": q, "hits": [], "took_s": round(time.time() - t0, 2),
                "error": f"{type(e).__name__}: {e}"}


_ACT_TOKEN_RE = __import__("re").compile(
    r"\b(?:CrPC|BNSS|BNS|BSA|IPC|IEA|NI\s+Act|POSH|PWDVA|"
    r"(?:[A-Z][a-z]+\s+){1,5}Act)\b"
)


def _act_tokens(hint: str) -> list[str]:
    """Extract Act / code identifiers from a hint string.

    Hints look like 'Section 154 CrPC / BNSS 173' or
    'Protection of Women from Domestic Violence Act 2005'.
    """
    # First try regex for short acronyms + 'X Y Act' phrases
    out = [m.group(0).strip() for m in _ACT_TOKEN_RE.finditer(hint)]
    # Fallback: any capitalised noun phrase >= 4 chars that isn't 'Section'
    if not out:
        for tok in hint.replace("/", " ").split():
            t = tok.strip(".,;:")
            if len(t) >= 4 and t.lower() not in {"section", "act"}:
                out.append(t)
    return list(dict.fromkeys(out))  # dedup, preserve order


def act_hint_in_hits(hint: str, hits: list[dict]) -> bool:
    """True if any of the Act tokens in the hint appears in any top-K
    hit's title, anchor, or chunk text (case-insensitive substring)."""
    if not hint:
        return False
    toks = [t.lower() for t in _act_tokens(hint)]
    if not toks:
        return False
    for hit in hits:
        haystack = " ".join((
            (hit.get("title") or ""),
            (hit.get("anchor") or ""),
            (hit.get("text") or "")[:600],   # first 600 chars is enough
        )).lower()
        if any(t in haystack for t in toks):
            return True
    return False


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--queries-dir", default=str(ROOT / "data/eval_500"))
    ap.add_argument("--n", type=int, default=100)
    ap.add_argument("--top-k", type=int, default=5)
    ap.add_argument("--out", default=None)
    args = ap.parse_args()

    rows = load_corpus(Path(args.queries_dir))
    rng = random.Random(SEED)
    sample = rng.sample(rows, min(args.n, len(rows)))
    print(f"sampled {len(sample)} of {len(rows)} queries", flush=True)

    out_path = Path(args.out) if args.out else (
        ROOT / "data/processed" /
        f"random100_retrieval_{datetime.now().strftime('%Y%m%d_%H%M%S')}.jsonl"
    )
    out_path.parent.mkdir(parents=True, exist_ok=True)

    persona_act_hit = Counter()
    persona_total = Counter()
    persona_act_total = Counter()
    src_type_top1 = Counter()
    src_type_top5 = Counter()
    n_error = 0
    latencies: list[float] = []

    with out_path.open("w") as f:
        for i, qrow in enumerate(sample, 1):
            q = qrow["query"]
            persona = qrow.get("persona", "?")
            hint = qrow.get("expected_act_hint") or ""
            r = search(q, top_k=args.top_k)
            persona_total[persona] += 1
            if r.get("error"):
                n_error += 1
            hits = r.get("hits", [])
            latencies.append(r["took_s"])
            top1_src = hits[0]["source_type"] if hits else "none"
            top5_src = [h["source_type"] for h in hits[:5]]
            src_type_top1[top1_src] += 1
            for s in top5_src:
                src_type_top5[s] += 1

            hit_hint = False
            if hint:
                persona_act_total[persona] += 1
                hit_hint = act_hint_in_hits(hint, hits)
                if hit_hint:
                    persona_act_hit[persona] += 1

            row = {
                "query": q,
                "persona": persona,
                "expected_act_hint": hint,
                "act_hint_in_top5": hit_hint,
                "top1_anchor": hits[0]["anchor"] if hits else None,
                "top1_source_type": top1_src,
                "top1_title": hits[0]["title"][:80] if hits else None,
                "top5_source_types": top5_src,
                "took_s": r["took_s"],
                "error": r.get("error"),
            }
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
            f.flush()

            mark = "✓" if hit_hint else ("·" if not hint else "✗")
            print(f"  [{i:>3}/{len(sample)}] {persona[:10]:<10} "
                  f"{mark} t={r['took_s']:>4.1f}s top1={top1_src} "
                  f"q={q[:55]!r}", flush=True)

    print("\n=== summary ===")
    print(f"  errors:       {n_error}/{len(sample)}")
    if latencies:
        latencies.sort()
        med = latencies[len(latencies) // 2]
        p95 = latencies[int(len(latencies) * 0.95)]
        print(f"  latency med: {med:.2f}s  p95: {p95:.2f}s")
    print(f"  top-1 source_type: {dict(src_type_top1)}")
    print(f"  top-5 source_type counts: {dict(src_type_top5)}")
    print("\n=== act_hint hit-rate by persona (where hint present) ===")
    for persona in sorted(persona_act_total):
        hit = persona_act_hit[persona]
        tot = persona_act_total[persona]
        print(f"  {persona:<22}  {hit:>3}/{tot:<3}  "
              f"{(100.0 * hit / tot if tot else 0):>5.1f}%")
    total_hint_q = sum(persona_act_total.values())
    total_hits = sum(persona_act_hit.values())
    if total_hint_q:
        print(f"  {'OVERALL':<22}  {total_hits:>3}/{total_hint_q:<3}  "
              f"{100.0 * total_hits / total_hint_q:>5.1f}%")
    print(f"\noutput: {out_path}")


if __name__ == "__main__":
    main()
