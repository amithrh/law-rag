#!/usr/bin/env python3
"""Filter SC-mined triples for reranker training quality.

Why this exists — Stage 3 reranker fine-tune (Task #43) needs clean
(query, positive, hard_negative) triples. The raw mine
(data/training/sc_triples.jsonl, 8,470 rows) is dominated by long
SC-judgment paragraph snippets, occasional same-section hard negs
(leakage), and a heavy arbitration bias (18% of corpus).

Filter rules (Agent 1 subagent review, see plan synthesis):
  1. Drop queries > 120 chars (paragraph dumps, not query-like)
     or < 10 chars (word fragments).
  2. Drop positives > 400 chars (Acts whose full section blows past
     reranker context-window budget at max_len=384).
  3. Drop where hard_negative_anchor's section == positive_anchor's
     section (leakage — same-section "hard neg" is the positive).
  4. Drop confidence='low' (mined with weak section-resolution).
  5. Downsample arbitration-1996 to --arbitration-cap (default 600)
     to prevent the reranker from overfitting to commercial-court
     vocabulary at the expense of other Acts.

Train/eval split:
  Split by document_id (matched_slug + section_no), NOT by triple.
  This prevents the reranker memorising specific section text in
  train and being asked to rank that same section in eval. Agent 5
  flagged this as the integration gotcha — eval-by-triple is
  effectively in-distribution test, not generalisation.

Usage:
  PYTHONPATH=. .venv/bin/python scripts/filter_sc_triples.py
  PYTHONPATH=. .venv/bin/python scripts/filter_sc_triples.py \\
      --max-query-chars 200    # if survival is too low
"""
from __future__ import annotations

import argparse
import json
import random
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).parent.parent


def parse_section(anchor: str) -> str:
    """`arbitration-1996/sec-20` -> `sec-20`."""
    if "/" in anchor:
        return anchor.rsplit("/", 1)[1]
    return anchor


def parse_section_num(section_label: str) -> int | None:
    """`sec-20` -> 20; `sec-1__2-d` -> 1. Returns None if unparseable."""
    if not section_label:
        return None
    # strip 'sec-' prefix, then split on first non-digit
    s = section_label.lstrip("sec-")
    n = ""
    for ch in s:
        if ch.isdigit():
            n += ch
        else:
            break
    try:
        return int(n) if n else None
    except ValueError:
        return None


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--in", dest="inp",
                   default="data/training/sc_triples.jsonl")
    p.add_argument("--out",
                   default="data/training/sc_triples.filtered.jsonl")
    p.add_argument("--max-query-chars", type=int, default=120)
    p.add_argument("--min-query-chars", type=int, default=10)
    p.add_argument("--max-positive-chars", type=int, default=400)
    p.add_argument("--arbitration-cap", type=int, default=600)
    p.add_argument("--max-section-gap", type=int, default=50,
                   help="if both have valid section numbers, "
                        "drop hard_neg whose section is >gap away "
                        "from positive (too unrelated to be 'hard')")
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--train-split", type=float, default=0.9)
    p.add_argument("--splits-dir", default="data/training/splits")
    args = p.parse_args()

    random.seed(args.seed)
    inp = Path(args.inp)
    if not inp.exists():
        raise SystemExit(f"input not found: {inp}")

    rows: list[dict] = []
    drops: Counter = Counter()
    with inp.open() as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                d = json.loads(line)
            except json.JSONDecodeError:
                drops["bad_json"] += 1
                continue

            q = d.get("query", "") or ""
            pos = d.get("positive_text", "") or ""
            pos_anchor = d.get("positive_anchor", "") or ""
            neg_anchor = d.get("hard_negative_anchor", "") or ""
            conf = d.get("confidence", "")

            if len(q) > args.max_query_chars:
                drops["query_too_long"] += 1
                continue
            if len(q) < args.min_query_chars:
                drops["query_too_short"] += 1
                continue
            if len(pos) > args.max_positive_chars:
                drops["positive_too_long"] += 1
                continue
            if conf == "low":
                drops["low_confidence"] += 1
                continue

            pos_sec = parse_section(pos_anchor)
            neg_sec = parse_section(neg_anchor)
            if pos_sec == neg_sec:
                drops["section_leak_exact"] += 1
                continue

            # Section-gap check — drop hard_negs from very different sections
            pos_n = parse_section_num(pos_sec)
            neg_n = parse_section_num(neg_sec)
            if (pos_n is not None and neg_n is not None
                    and abs(pos_n - neg_n) > args.max_section_gap):
                drops["section_too_far"] += 1
                continue

            rows.append(d)

    total_input = sum(drops.values()) + len(rows)
    print(f"=== Pre-cap survival ===")
    print(f"  loaded:   {total_input:,}")
    print(f"  dropped:")
    for k, v in drops.most_common():
        print(f"    {k:<24} {v:,}")
    print(f"  surviving: {len(rows):,} "
          f"({100 * len(rows) / total_input:.1f}%)")

    # Arbitration cap
    arb = [r for r in rows
           if (r.get("matched_slug") or "") == "arbitration-1996"]
    other = [r for r in rows
             if (r.get("matched_slug") or "") != "arbitration-1996"]
    if len(arb) > args.arbitration_cap:
        arb = random.sample(arb, args.arbitration_cap)
    final = arb + other
    random.shuffle(final)

    print(f"\n=== After arbitration cap ===")
    print(f"  arbitration-1996: {len(arb):,} "
          f"(capped at {args.arbitration_cap})")
    print(f"  other:            {len(other):,}")
    print(f"  total:            {len(final):,}")

    # Per-act distribution
    by_act = Counter(r.get("matched_slug", "?") for r in final)
    print(f"\n  top 10 acts by count:")
    for slug, cnt in by_act.most_common(10):
        print(f"    {slug:<30} {cnt:>4}")

    # Write filtered
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w") as f:
        for r in final:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    print(f"\n  wrote -> {out}")

    # Train/eval split BY DOCUMENT
    by_doc = defaultdict(list)
    for r in final:
        slug = r.get("matched_slug", "unk")
        sec = r.get("section_no", "unk")
        doc_id = f"{slug}/{sec}"
        by_doc[doc_id].append(r)

    doc_ids = list(by_doc.keys())
    random.shuffle(doc_ids)
    n_train_docs = int(len(doc_ids) * args.train_split)
    train_doc_ids = set(doc_ids[:n_train_docs])
    eval_doc_ids = set(doc_ids[n_train_docs:])

    train_rows = [r for d in train_doc_ids for r in by_doc[d]]
    eval_rows = [r for d in eval_doc_ids for r in by_doc[d]]

    splits = Path(args.splits_dir)
    splits.mkdir(parents=True, exist_ok=True)
    with (splits / "train.jsonl").open("w") as f:
        for r in train_rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    with (splits / "eval.jsonl").open("w") as f:
        for r in eval_rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    with (splits / "train_doc_ids.json").open("w") as f:
        json.dump(sorted(train_doc_ids), f, indent=2)
    with (splits / "eval_doc_ids.json").open("w") as f:
        json.dump(sorted(eval_doc_ids), f, indent=2)

    print(f"\n=== Train/eval split (by document_id) ===")
    print(f"  unique documents: {len(doc_ids):,}")
    print(f"  train docs:  {len(train_doc_ids):,} "
          f"({len(train_rows):,} triples)")
    print(f"  eval  docs:  {len(eval_doc_ids):,} "
          f"({len(eval_rows):,} triples)")
    print(f"  written to {splits}/")


if __name__ == "__main__":
    main()
