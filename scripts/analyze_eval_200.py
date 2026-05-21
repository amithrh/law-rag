#!/usr/bin/env python3
"""Programmatic failure-mode analysis for the 200-query eval.

Reads eval_200_*.jsonl produced by eval_200_runner.py and classifies
each row into one of these buckets:

  REFUSE_correct        — system refused; query genuinely off-corpus
  REFUSE_wrong          — system refused; query was answerable
                          (corpus gap or threshold too tight)
  OK_grounded           — cosine OK; cited bare-act; on-topic
  OK_only_sc            — cosine OK; cited only SC caselaw
                          (would be cosmetic-OK in strict eval)
  OK_only_hc            — cosine OK; cited only HC judgments
  OK_wrong_act_year     — cited Act with wrong year (e.g. CPA 1986
                          instead of 2019)
  PARTIAL_low_cosine    — bare-acts surfaced but cosine threshold flagged
  OFF_real_failure      — off-topic AND wrong direction (subagent verifies)
  OFF_false_alarm       — off-topic but answer is actually fine
  NO_RELEVANCE          — answer produced 0 cited sentences

Per bucket: count, % of total, persona breakdown, sample queries.

Also flags **dangerous** failures (accused-vs-victim frame mismatch).

Usage:
  PYTHONPATH=. .venv/bin/python scripts/analyze_eval_200.py \\
      --eval data/processed/eval_200_LATEST.jsonl

  # With LLM-judge classification of body texts (slow but more accurate):
  PYTHONPATH=. .venv/bin/python scripts/analyze_eval_200.py \\
      --eval data/processed/eval_200_LATEST.jsonl --llm-judge
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).parent.parent

# Map common Act-year mistakes to flag
WRONG_YEAR_PATTERNS = [
    (r"\bConsumer Protection Act,?\s*1986\b", "CPA 1986 (repealed); current is 2019"),
    (r"\bDomestic Violence Act,?\s*\b", "missing 'Protection of Women from'"),
    (r"\bSection 66A\b.*IT Act", "Section 66A struck down by Shreya Singhal 2015"),
    (r"\bSection 377\b", "after Navtej Singh Johar 2018 — context check needed"),
]

# Lay phrases that strongly imply the user is the SUBJECT of state action
# (accused), so the answer should focus on rights of the accused, not victim
# framing.
ACCUSED_FRAMING_HINTS = [
    "i am caught", "i was caught", "i was arrested", "i am arrested",
    "police took me", "ed took me", "police caught me",
    "i am accused", "case filed against me", "fir against me",
    "police filed", "raided my house", "took my phone",
]


def is_accused_subject(query: str) -> bool:
    """Heuristic: is the user phrasing themselves as the SUBJECT of state action?"""
    qlower = query.lower()
    return any(h in qlower for h in ACCUSED_FRAMING_HINTS)


def get_body_text(row: dict) -> str:
    """Concatenate all sentence texts into the answer body."""
    return " ".join(s.get("text", "") for s in row.get("sentences", []))


def classify_row(row: dict) -> dict:
    """Return {bucket, flags, notes}."""
    out = {"bucket": "UNKNOWN", "flags": [], "notes": []}
    if row.get("error"):
        out["bucket"] = "ERROR"
        out["notes"].append(row["error"][:80])
        return out

    refused = bool(row.get("refused"))
    verdict = row.get("relevance_verdict")
    src = row.get("source_counts") or {}
    n_act = src.get("bare_act", 0)
    n_sc = src.get("sc_judgment", 0)
    n_hc = src.get("hc_judgment", 0)
    n_sent_total = row.get("n_sentences", 0)
    n_ok_sent = row.get("n_ok", 0)
    body = get_body_text(row)

    # Refused branch
    if refused:
        # Were they SUPPOSED to refuse? Heuristic: queries that don't
        # mention any legal concept might be genuinely off-corpus.
        legal_hints = ("act", "section", "article", "law", "court",
                       "fir", "bail", "arrest", "police", "judge",
                       "marriage", "divorce", "tax", "GST", "company",
                       "deposit", "rent", "fired", "boss", "salary",
                       "complaint", "consumer", "child", "father",
                       "mother", "son", "wife", "husband", "land",
                       "property", "neighbour", "cheque", "credit")
        qlower = row["query"].lower()
        has_legal_hint = any(h in qlower for h in legal_hints)
        if has_legal_hint:
            out["bucket"] = "REFUSE_wrong"  # corpus gap or threshold
            out["notes"].append("query has legal hints but was refused")
        else:
            out["bucket"] = "REFUSE_correct"
        return out

    # Not refused — classify by sources + cosine
    if n_sent_total == 0:
        out["bucket"] = "NO_RELEVANCE"
        return out

    # Wrong-year patterns
    for pat, msg in WRONG_YEAR_PATTERNS:
        if re.search(pat, body, re.IGNORECASE):
            out["flags"].append(f"WRONG_REF: {msg}")

    # Accused-as-subject + victim-framing answer = dangerous failure
    if is_accused_subject(row["query"]):
        victim_signals = ["victim", "complainant", "presumption of lack of consent",
                           "rape", "prosecutrix"]
        if any(v in body.lower() for v in victim_signals):
            out["flags"].append("DANGEROUS: accused asked, answer framed as victim/complainant")

    # Source-based bucket
    if verdict in ("partial", "off_topic"):
        if n_act >= 3:
            out["bucket"] = "PARTIAL_low_cosine"  # retrieval got it, cosine flagged
        elif verdict == "off_topic":
            out["bucket"] = "OFF_real_failure"
        else:
            out["bucket"] = "PARTIAL_low_cosine"
    elif verdict == "ok":
        if n_act > 0:
            out["bucket"] = "OK_grounded"
        elif n_hc > 0 and n_sc == 0:
            out["bucket"] = "OK_only_hc"
        elif n_sc > 0:
            out["bucket"] = "OK_only_sc"
        else:
            out["bucket"] = "OK_no_sources"  # weird state
    else:
        out["bucket"] = "UNKNOWN"

    return out


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--eval", required=True, help="eval_200 JSONL path")
    p.add_argument("--out-md", default=None,
                   help="write a markdown report to this path "
                        "(default: stdout only)")
    args = p.parse_args()

    rows: list[dict] = []
    with open(args.eval) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            rows.append(json.loads(line))

    print(f"loaded {len(rows)} eval rows\n")

    # Per-row classify
    classifications = []
    for r in rows:
        c = classify_row(r)
        classifications.append({**c, "query": r["query"],
                                "persona": r.get("persona"),
                                "took_s": r.get("took_s")})

    # Aggregate by bucket
    by_bucket: dict[str, list] = defaultdict(list)
    for c in classifications:
        by_bucket[c["bucket"]].append(c)

    # Per-persona breakdown
    by_persona_bucket: dict[tuple, int] = Counter()
    for c in classifications:
        by_persona_bucket[(c["persona"], c["bucket"])] += 1

    flag_counter = Counter()
    for c in classifications:
        for fl in c["flags"]:
            flag_counter[fl.split(":")[0]] += 1

    n = len(rows)

    # ---- Report ----
    lines = []
    lines.append(f"# 200-query realistic eval — failure analysis")
    lines.append(f"")
    lines.append(f"**Total: {n} queries** · "
                 f"avg latency: {sum(r.get('took_s', 0) or 0 for r in rows)/n:.1f}s")
    lines.append(f"")
    lines.append(f"## Bucket distribution")
    lines.append(f"")
    lines.append(f"| Bucket | Count | % | Interpretation |")
    lines.append(f"|---|---:|---:|---|")
    interp = {
        "OK_grounded":      "✓ on-topic, cited bare-Act",
        "OK_only_sc":       "✓ topical but only SC cites",
        "OK_only_hc":       "✓ topical but only HC cites",
        "OK_no_sources":    "⚠ OK verdict with no sources?!",
        "PARTIAL_low_cosine": "⚠ bare-act there, cosine misfire",
        "OFF_real_failure": "✗ off-topic, real failure",
        "OFF_false_alarm":  "○ off-topic but actually fine (LLM judge needed)",
        "REFUSE_correct":   "✓ refused, genuinely off-corpus",
        "REFUSE_wrong":     "✗ refused but answerable (corpus gap)",
        "NO_RELEVANCE":     "⚠ 0 cited sentences",
        "ERROR":            "✗ HTTP/transport error",
        "UNKNOWN":          "?",
    }
    for bucket, items in sorted(by_bucket.items(), key=lambda kv: -len(kv[1])):
        lines.append(f"| {bucket} | {len(items)} | "
                     f"{100*len(items)/n:.0f}% | {interp.get(bucket, '')} |")
    lines.append(f"")

    lines.append(f"## Persona x bucket")
    lines.append(f"")
    personas = sorted({c["persona"] for c in classifications})
    buckets = sorted({c["bucket"] for c in classifications})
    lines.append(f"| Bucket | " + " | ".join(personas) + " | total |")
    lines.append(f"|---|" + "|".join([":---:"] * (len(personas) + 1)) + "|")
    for b in buckets:
        row_counts = [by_persona_bucket.get((p, b), 0) for p in personas]
        lines.append(f"| {b} | " + " | ".join(str(c) for c in row_counts)
                     + f" | {sum(row_counts)} |")
    lines.append(f"")

    lines.append(f"## Critical flags")
    lines.append(f"")
    if flag_counter:
        for flag_kind, cnt in flag_counter.most_common():
            lines.append(f"- **{flag_kind}**: {cnt} queries")
    else:
        lines.append("- no critical flags raised")
    lines.append(f"")

    # Dangerous samples
    dangerous = [c for c in classifications
                 if any(f.startswith("DANGEROUS") for f in c["flags"])]
    if dangerous:
        lines.append(f"## 🚨 Dangerous: accused-as-victim framing ({len(dangerous)})")
        for c in dangerous[:10]:
            lines.append(f"- _{c['persona']}_: {c['query']!r}")
        lines.append(f"")

    wrong_ref = [c for c in classifications
                 if any(f.startswith("WRONG_REF") for f in c["flags"])]
    if wrong_ref:
        lines.append(f"## ⚠ Wrong Act-year / overruled-section references ({len(wrong_ref)})")
        for c in wrong_ref[:10]:
            flag_msg = next(f for f in c["flags"] if f.startswith("WRONG_REF"))
            lines.append(f"- _{c['persona']}_: {c['query'][:60]!r}  ({flag_msg})")
        lines.append(f"")

    # Refused sample
    if by_bucket.get("REFUSE_wrong"):
        lines.append(f"## Sample wrongly-refused queries (corpus gap?)")
        for c in by_bucket["REFUSE_wrong"][:10]:
            lines.append(f"- _{c['persona']}_: {c['query']!r}")
        lines.append(f"")

    # OK_only_sc sample
    if by_bucket.get("OK_only_sc"):
        lines.append(f"## Sample OK_only_sc — caselaw-only answers ({len(by_bucket['OK_only_sc'])})")
        for c in by_bucket["OK_only_sc"][:6]:
            lines.append(f"- _{c['persona']}_: {c['query']!r}")
        lines.append(f"")

    report = "\n".join(lines)
    print(report)
    if args.out_md:
        Path(args.out_md).write_text(report + "\n")
        print(f"\nReport saved to {args.out_md}")


if __name__ == "__main__":
    main()
