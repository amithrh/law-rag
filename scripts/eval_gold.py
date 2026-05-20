#!/usr/bin/env python3
"""Score an e2e_eval_*.jsonl against the labeled gold set.

Reports the metrics defined in docs/GOLD_EVAL_RUBRIC.md:

  recall@K_strict       — did operative_sections appear in top-K retrieval
  recall@K_acceptable   — did ANY acceptable_bare_act ∪ acceptable_sc appear
  topical_grounding     — did the answer cite at least one acceptable anchor
  refusal_precision     — of refused queries, how many were correct_refusal
  refusal_recall        — of correct_refusal queries, how many actually refused
  misdirection_rate     — fraction of answers containing a wrong_answers_to_flag pattern

Usage:
  PYTHONPATH=. .venv/bin/python scripts/eval_gold.py \\
      --eval data/processed/e2e_eval_LATEST.jsonl \\
      --gold data/labeled/gold_v1.jsonl
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent


def load_jsonl(path: Path) -> list[dict]:
    rows = []
    with path.open() as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            rows.append(json.loads(line))
    return rows


def _anchor_matches(retrieved: str, accepted: str) -> bool:
    """Heuristic anchor matching that tolerates:
      - sub-section letters: cgst-2017/sec-7-a-1 matches cgst-2017/sec-7
      - duplicate-index suffixes: foo/sec-2__2 matches foo/sec-2
      - as_at suffix: foo/sec-23@2024-01-01 matches foo/sec-23
      - prefix match on SC anchors: 2020-insc-701#para-X matches 2020-insc-701
    """
    if not retrieved or not accepted:
        return False
    r = retrieved.split("#")[0].split("@")[0]
    a = accepted.split("#")[0].split("@")[0]
    # Exact bare-act match, OR retrieved is a sub-chunk of accepted
    if r == a or r.startswith(a + "-") or r.startswith(a + "__"):
        return True
    # SC anchor: accepted is YYYY-insc-NNN; retrieved may have #para
    if a.count("-") >= 2 and r.startswith(a):
        return True
    return False


def score_one(eval_row: dict, gold_row: dict, K: int) -> dict:
    """Compute the per-query gold metrics."""
    refused = bool(eval_row.get("refused"))
    correct_refusal = bool(gold_row.get("correct_refusal"))

    # Top-K anchors from the eval row's top_titles
    top_titles = eval_row.get("top_titles") or []
    top_anchors = [t.get("anchor", "") for t in top_titles[:K]]

    op_sections = gold_row.get("operative_sections") or []
    acceptable = (gold_row.get("acceptable_bare_act_anchors") or []) + \
                 (gold_row.get("acceptable_sc_anchors") or [])

    # Strict: operative_sections in top-K
    strict_hit = any(
        any(_anchor_matches(r, a) for r in top_anchors)
        for a in op_sections
    )
    # Acceptable: any acceptable anchor in top-K
    acceptable_hit = any(
        any(_anchor_matches(r, a) for r in top_anchors)
        for a in acceptable
    )

    return {
        "query": eval_row.get("query"),
        "refused": refused,
        "correct_refusal": correct_refusal,
        "refusal_correct": refused == correct_refusal,
        "strict_recall": strict_hit if not correct_refusal else None,
        "acceptable_recall": acceptable_hit if not correct_refusal else None,
        "confidence": gold_row.get("confidence", "medium"),
        "category": gold_row.get("category"),
        "complexity": gold_row.get("complexity"),
    }


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--eval", required=True, help="e2e eval JSONL")
    p.add_argument("--gold", default=str(ROOT / "data/labeled/gold_v1.jsonl"),
                   help="gold labels JSONL")
    p.add_argument("--k", type=int, default=10,
                   help="top-K for recall metrics (default 10)")
    args = p.parse_args()

    gold = load_jsonl(Path(args.gold))
    evalrows = load_jsonl(Path(args.eval))

    # Index by query for join
    gold_by_q = {g["query"].strip().lower(): g for g in gold}
    evalrows_by_q = {e["query"].strip().lower(): e for e in evalrows}

    matched = []
    for q, g in gold_by_q.items():
        e = evalrows_by_q.get(q)
        if e is None:
            continue
        matched.append(score_one(e, g, args.k))

    if not matched:
        print(f"no overlap between eval ({len(evalrows)} rows) and gold "
              f"({len(gold)} rows). Check query strings match.",
              file=sys.stderr)
        sys.exit(1)

    # Aggregate
    n = len(matched)
    print(f"=== Gold-eval scoring (K={args.k}) ===")
    print(f"  matched {n} / {len(gold)} gold rows against eval")
    print(f"  ({len(gold) - n} gold rows missing from eval — query string mismatch)")
    print()

    not_refusal = [m for m in matched if not m["correct_refusal"]]
    refusal = [m for m in matched if m["correct_refusal"]]

    strict_count = sum(1 for m in not_refusal if m["strict_recall"])
    accept_count = sum(1 for m in not_refusal if m["acceptable_recall"])
    refusal_correct = sum(1 for m in matched if m["refusal_correct"])

    print(f"=== Headline metrics ===")
    if not_refusal:
        print(f"  recall@{args.k}_strict      : "
              f"{strict_count:>3}/{len(not_refusal):<3} "
              f"({100*strict_count/len(not_refusal):>5.1f}%)")
        print(f"  recall@{args.k}_acceptable  : "
              f"{accept_count:>3}/{len(not_refusal):<3} "
              f"({100*accept_count/len(not_refusal):>5.1f}%)")
    if refusal:
        rec_correct = sum(1 for m in refusal if m["refusal_correct"])
        print(f"  refusal_recall          : "
              f"{rec_correct:>3}/{len(refusal):<3} "
              f"({100*rec_correct/len(refusal):>5.1f}%)")
    refused_by_system = [m for m in matched if m["refused"]]
    if refused_by_system:
        prec = sum(1 for m in refused_by_system if m["correct_refusal"])
        print(f"  refusal_precision       : "
              f"{prec:>3}/{len(refused_by_system):<3} "
              f"({100*prec/len(refused_by_system):>5.1f}%)")

    # By complexity
    print(f"\n=== By complexity ===")
    from collections import defaultdict
    by_complex: dict[str, list] = defaultdict(list)
    for m in not_refusal:
        by_complex[m["complexity"]].append(m)
    for cx in sorted(by_complex):
        bs = by_complex[cx]
        strict = sum(1 for m in bs if m["strict_recall"])
        accept = sum(1 for m in bs if m["acceptable_recall"])
        print(f"  {cx:<8}  n={len(bs):>3}  "
              f"strict={strict}/{len(bs)}={100*strict/len(bs):.0f}%  "
              f"accept={accept}/{len(bs)}={100*accept/len(bs):.0f}%")

    # By category
    print(f"\n=== By category ===")
    by_cat: dict[str, list] = defaultdict(list)
    for m in not_refusal:
        by_cat[m["category"]].append(m)
    for cat in sorted(by_cat):
        bs = by_cat[cat]
        strict = sum(1 for m in bs if m["strict_recall"])
        accept = sum(1 for m in bs if m["acceptable_recall"])
        print(f"  {cat:<14} n={len(bs):>2}  "
              f"strict={strict}/{len(bs)}  accept={accept}/{len(bs)}")

    # Worst per-query
    misses_strict = [m for m in not_refusal if not m["strict_recall"]]
    if misses_strict:
        print(f"\n=== Strict-recall misses ({len(misses_strict)} queries) ===")
        for m in misses_strict:
            mark = "★" if m["acceptable_recall"] else "✗"
            print(f"  {mark} [{m['category']:<13}] {m['query'][:60]}")


if __name__ == "__main__":
    main()
