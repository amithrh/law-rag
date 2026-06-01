#!/usr/bin/env python3
"""Build a fresh human-style 200 prompt eval pack.

This does not pretend to be real production user logs. It takes the curated
eval inventory with expected Act hints and rewrites a balanced sample into
shorter, messier UI-style questions: fragments, typos, missing punctuation,
and "what can I do" endings. The expected hints are preserved so the timed
eval can still score retrieval/citation quality.
"""
from __future__ import annotations

import argparse
import json
import random
import re
from collections import defaultdict
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]


PREFIXES = (
    "",
    "pls tell ",
    "what to do ",
    "need help, ",
    "urgent ",
    "sir ",
    "hi, ",
    "can u tell ",
    "i am confused ",
    "please help ",
)

SUFFIXES = (
    "",
    " what can i do",
    " how to complain",
    " need lawyer or police",
    " pls guide",
    " where to go",
    " is this legal",
    " any remedy",
    " can i file case",
    " what next",
)

REPLACEMENTS: tuple[tuple[str, str], ...] = (
    (r"\bcannot\b", "cant"),
    (r"\bcan not\b", "cant"),
    (r"\bdoesn't\b", "doesnt"),
    (r"\bdon't\b", "dont"),
    (r"\brefused\b", "not agreeing"),
    (r"\brefusing\b", "not agreeing"),
    (r"\bapplication\b", "appln"),
    (r"\bdocuments\b", "docs"),
    (r"\bdocument\b", "doc"),
    (r"\bcertificate\b", "cert"),
    (r"\bcomplaint\b", "complain"),
    (r"\bregister\b", "file"),
    (r"\bregistration\b", "regn"),
    (r"\bgovernment\b", "govt"),
    (r"\bofficer\b", "offcr"),
    (r"\bcompany\b", "cmpny"),
    (r"\bproperty\b", "prop"),
    (r"\bmonths\b", "mnths"),
    (r"\byears\b", "yrs"),
    (r"\bplease\b", "pls"),
)


def read_rows(source: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for path in sorted(source.glob("*.jsonl")):
        persona = path.stem
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            row = json.loads(line)
            row.setdefault("persona", persona)
            rows.append(row)
    return rows


def balanced_sample(rows: list[dict[str, Any]], *, limit: int, seed: int) -> list[dict[str, Any]]:
    by_persona: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        by_persona[str(row.get("persona") or "unknown")].append(row)
    rng = random.Random(seed)
    for bucket in by_persona.values():
        rng.shuffle(bucket)

    selected: list[dict[str, Any]] = []
    personas = sorted(by_persona)
    cursors = {p: 0 for p in personas}
    while len(selected) < limit:
        progressed = False
        for persona in personas:
            idx = cursors[persona]
            if idx >= len(by_persona[persona]):
                continue
            selected.append(by_persona[persona][idx])
            cursors[persona] += 1
            progressed = True
            if len(selected) >= limit:
                break
        if not progressed:
            break
    return selected


def messy_query(query: str, *, idx: int, rng: random.Random) -> str:
    q = " ".join(query.strip().split())
    q = q.rstrip("?.!")
    if idx % 2 == 0:
        q = q[:1].lower() + q[1:]
    if idx % 5 == 0:
        q = q.replace(",", " ,")
    if idx % 7 == 0:
        q = q.replace(" and ", " n ")
    if idx % 11 == 0:
        q = q.replace(" for ", " fr ")
    if idx % 13 == 0:
        q = q.replace(" is ", " is ")

    for pattern, replacement in REPLACEMENTS:
        if rng.random() < 0.22:
            q = re.sub(pattern, replacement, q, flags=re.IGNORECASE)

    prefix = PREFIXES[idx % len(PREFIXES)]
    suffix = SUFFIXES[(idx * 3) % len(SUFFIXES)]
    q = f"{prefix}{q}{suffix}"
    q = re.sub(r"\s+", " ", q).strip()
    return q


def build(source: Path, out_dir: Path, *, limit: int, seed: int) -> Path:
    rows = balanced_sample(read_rows(source), limit=limit, seed=seed)
    if len(rows) < limit:
        raise SystemExit(f"only found {len(rows)} rows under {source}, need {limit}")

    rng = random.Random(seed + 17)
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "human_messy_200.jsonl"
    with out_path.open("w", encoding="utf-8") as f:
        for idx, row in enumerate(rows, 1):
            out = {
                "query": messy_query(str(row["query"]), idx=idx, rng=rng),
                "persona": f"human_messy_{row.get('persona', 'unknown')}",
                "expected_category": row.get("expected_category"),
                "expected_act_hint": row.get("expected_act_hint"),
                "is_accused_subject": bool(row.get("is_accused_subject")),
                "source_query": row["query"],
                "eval_variant": "human_messy_v1",
                "generated_from": str(source),
                "synthetic_note": "human-like rewrite; not real user log",
            }
            f.write(json.dumps(out, ensure_ascii=False) + "\n")
    return out_path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=ROOT / "data" / "eval_500")
    parser.add_argument("--out-dir", type=Path, default=ROOT / "data" / "eval_human_messy_200")
    parser.add_argument("--limit", type=int, default=200)
    parser.add_argument("--seed", type=int, default=20260531)
    args = parser.parse_args()

    out_path = build(args.source, args.out_dir, limit=args.limit, seed=args.seed)
    print(out_path)


if __name__ == "__main__":
    main()
