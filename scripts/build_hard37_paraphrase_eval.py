#!/usr/bin/env python3
"""Build paraphrase/adversarial variants for the hard-37 product gate.

This pack is meant to test whether blocker fixes generalize beyond the exact
prompt strings. It preserves product-gate metadata and the expected Act keys
from each source row, then emits deterministic user-style variants.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path
from typing import Any

from scripts.eval_timed_100 import expected_act_keys, jsonl_dumps


VARIANT_COUNT = 4

HINDI_REPLACEMENTS: tuple[tuple[str, str], ...] = (
    (r"\bwhat to do\b", "ab kya karu"),
    (r"\bcan u tell\b", "pls batao"),
    (r"\bplease help\b", "pls help"),
    (r"\bis this legal\b", "ye legal hai kya"),
    (r"\bpolice\b", "police/thane"),
    (r"\bfir\b", "FIR"),
    (r"\bwages\b", "salary/wages"),
    (r"\bsalary\b", "salary/wages"),
    (r"\bcomplaint\b", "complaint"),
    (r"\btenant\b", "tenant/kirayedar"),
    (r"\bbank\b", "bank"),
)

TYPO_REPLACEMENTS: tuple[tuple[str, str], ...] = (
    (r"\bcomplaint\b", "complain"),
    (r"\bharassing\b", "harrasing"),
    (r"\bdeducted\b", "dedcted"),
    (r"\bmunicipal\b", "municiple"),
    (r"\bprincipal\b", "principle"),
    (r"\bcontractor\b", "thekedar"),
    (r"\bcompany\b", "cmpny"),
    (r"\bdocuments\b", "docs"),
    (r"\bmonths\b", "mnths"),
)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path, help="Source hard-gate JSONL file")
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--filename", default="hard37_paraphrase.jsonl")
    parser.add_argument("--variants", type=int, default=VARIANT_COUNT)
    args = parser.parse_args()

    rows = read_jsonl(args.source)
    out_rows = build(rows, variants=args.variants, source=args.source)
    args.out_dir.mkdir(parents=True, exist_ok=True)
    out_path = args.out_dir / args.filename
    with out_path.open("w", encoding="utf-8") as handle:
        for row in out_rows:
            handle.write(jsonl_dumps(row) + "\n")
    print(out_path)
    print(f"rows={len(out_rows)} variants_per_source={args.variants}")


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for line_no, line in enumerate(path.read_text(encoding="utf-8").split("\n"), start=1):
        if not line.strip():
            continue
        row = json.loads(line)
        if not str(row.get("query") or "").strip():
            raise ValueError(f"{path}:{line_no}: missing query")
        rows.append(row)
    if not rows:
        raise ValueError(f"no rows in {path}")
    return rows


def build(rows: list[dict[str, Any]], *, variants: int, source: Path) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    for idx, row in enumerate(rows, start=1):
        query = str(row["query"]).strip()
        act_keys = row.get("expected_act_keys") or expected_act_keys(row.get("expected_act_hint"), query)
        for variant_idx in range(1, variants + 1):
            variant_query = make_variant(query, variant_idx=variant_idx)
            key = normalize_query(variant_query)
            if key in seen:
                variant_query = f"{variant_query} {idx}-{variant_idx}"
                key = normalize_query(variant_query)
            seen.add(key)
            variant = {
                **row,
                "query": variant_query,
                "base_id": f"{row.get('base_id') or stable_id(query)}-adv{variant_idx}",
                "source_query": row.get("source_query") or query,
                "expected_act_keys": act_keys,
                "eval_variant": "hard37_paraphrase_adversarial_v1",
                "generated_from": str(source),
                "paraphrase_variant": variant_idx,
                "synthetic_note": "hard-37 paraphrase/adversarial rewrite; not real user log",
            }
            out.append(variant)
    return out


def make_variant(query: str, *, variant_idx: int) -> str:
    q = " ".join(query.strip().strip("\"'“”").split())
    q = q.rstrip("?.!")
    if variant_idx == 1:
        return mobile_hinglish(q)
    if variant_idx == 2:
        return typo_short(q)
    if variant_idx == 3:
        return urgent_with_proof(q)
    if variant_idx == 4:
        return wrong_words_distractor(q)
    return f"pls guide {q} what next"


def mobile_hinglish(query: str) -> str:
    q = query.lower()
    for pattern, replacement in HINDI_REPLACEMENTS:
        q = re.sub(pattern, replacement, q, flags=re.IGNORECASE)
    q = q.replace(" and ", " aur ").replace(" not ", " nahi ")
    q = re.sub(r"\s+", " ", q).strip()
    return f"{q} kya step lu"


def typo_short(query: str) -> str:
    q = query
    for pattern, replacement in TYPO_REPLACEMENTS:
        q = re.sub(pattern, replacement, q, flags=re.IGNORECASE)
    q = re.sub(r"\bwhat to do\b", "help", q, flags=re.IGNORECASE)
    q = re.sub(r"\bcan u tell\b", "tell fast", q, flags=re.IGNORECASE)
    q = q.replace(",", " ,")
    q = re.sub(r"\s+", " ", q).strip()
    return f"{q} pls tell forum"


def urgent_with_proof(query: str) -> str:
    q = query
    proof = proof_phrase(query)
    q = re.sub(r"\bwhat to do\b", "", q, flags=re.IGNORECASE).strip()
    q = re.sub(r"\s+", " ", q).strip()
    return f"urgent scared {q}; {proof}; where complain first"


def wrong_words_distractor(query: str) -> str:
    q = query
    q = re.sub(r"\bcase\b", "online complaint/case", q, flags=re.IGNORECASE)
    q = re.sub(r"\bcomplaint\b", "legal notice or complaint", q, flags=re.IGNORECASE)
    q = re.sub(r"\bfir\b", "FIR/complaint", q, flags=re.IGNORECASE)
    q = re.sub(r"\bcourt\b", "court or authority", q, flags=re.IGNORECASE)
    q = re.sub(r"\s+", " ", q).strip()
    return f"{q}; no lawyer yet, family saying ignore, what is safe next"


def proof_phrase(query: str) -> str:
    blob = query.lower()
    if any(term in blob for term in ("police", "fir", "arrest", "picked", "station")):
        return "i have call recording and names but no FIR copy"
    if any(term in blob for term in ("wage", "salary", "factory", "contractor", "thekedar", "epf", "esi")):
        return "i have attendance photo and bank passbook"
    if any(term in blob for term in ("cyber", "instagram", "whatsapp", "deepfake", "telegram", "loan app", "data breach")):
        return "screenshots and phone number are with me"
    if any(term in blob for term in ("tenant", "rent", "property", "legal heir", "cart", "vendor")):
        return "papers and messages are with me"
    if any(term in blob for term in ("caste", "chamar", "adivasi", "tribal", "pahan", "sarna")):
        return "witness names and photos are there"
    return "some proof is there but no written reply"


def stable_id(query: str) -> str:
    digest = hashlib.sha1(query.encode("utf-8")).hexdigest()[:12]
    return f"hard37-{digest}"


def normalize_query(query: str) -> str:
    return re.sub(r"\s+", " ", query.strip().lower())


if __name__ == "__main__":
    main()
