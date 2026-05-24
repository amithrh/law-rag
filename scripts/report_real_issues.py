#!/usr/bin/env python3
"""Generate the eval_500_REAL_ISSUES.md deliverable.

Combines:
  - Heuristic bucket distribution (from analyze_eval_200.py logic)
  - LLM-judge real_issue counts + rationales (from llm_judge_eval.py)
  - Per-persona heatmap
  - Sample queries for each real_issue category
  - Specific fix proposals with file paths

Input: a *.judged.jsonl produced by scripts/llm_judge_eval.py.
       Each row has the original eval fields PLUS a `judgment` field.

Output: a markdown file with bucket tables, heatmaps, and a
        ranked list of "REAL issues" with sample queries and
        specific fix targets.

Usage:
  PYTHONPATH=. .venv/bin/python scripts/report_real_issues.py \\
      --in  data/processed/eval_500_baseline_LATEST.judged.jsonl \\
      --out data/processed/eval_500_REAL_ISSUES.md
"""
from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).parent.parent

FIX_PROPOSALS = {
    "corpus_gap": (
        "Add the missing Act to the corpus. Check scripts/add_p0_batch.py "
        "for the existing handle-based ingest pipeline, or — if Indian "
        "Kanoon / archive.org sourcing — use scripts/ingest_alt_sources.py."
    ),
    "retrieval_miss": (
        "Right Act exists but top-K missed it. Two paths: "
        "(a) re-run lay→legal expander with a more specific Act mapping "
        "in apps/api/query_expand.py; or (b) lower the section-N "
        "structural-anchor boost in apps/api/retrieve.py to admit more "
        "Act candidates."
    ),
    "rerank_misfire": (
        "Reranker scored wrong chunks above bare-act. This is the EXACT "
        "scenario Stage 3 reranker fine-tune (Task #43) is designed to "
        "fix — model weights need to learn 'cite the operative section, "
        "not the case that interpreted it'."
    ),
    "llm_hallucination": (
        "LLM ignored retrieved passages and asserted something wrong. "
        "Tighten apps/api/prompts/answer.md with stricter 'only cite "
        "what is shown' instruction. Lower temperature. Possibly "
        "add a post-generation 'do all cited anchors appear in passages?' "
        "check."
    ),
    "wrong_act_year": (
        "Cited Act exists but is the OLD version (CPA 1986, IPC 1860 "
        "vs BNS 2023 post-effective-date). Three options: "
        "(a) update apps/api/query_expand.py euphemism dictionary to "
        "ALWAYS use the new Act name; "
        "(b) tag old Acts in DB as 'superseded' and downweight in retrieval; "
        "(c) add a post-retrieval filter in apps/api/answer_service.py."
    ),
    "accused_as_victim": (
        "Dangerous framing — fix the expander prompt (apps/api/query_expand.py) "
        "to detect accused-subject and route variants toward rights-of-accused, "
        "and add a guardrail in the answer prompt explicitly checking the "
        "subject framing."
    ),
    "refusal_threshold_tight": (
        "Coverage gate refused but query was legitimate. Tune the gate "
        "threshold in apps/api/answer_service.py — or improve retrieval "
        "for that domain so the gate stops triggering."
    ),
    "answer_too_thin": (
        "Cite is correct but no operational steps. The /answer prompt "
        "ALREADY demands 'What you can do next' — model may not be "
        "following it. Increase prompt emphasis or add a finalizer "
        "pass that re-prompts for procedural guidance."
    ),
    "off_corpus": (
        "Genuinely off-scope. Refused correctly. No fix needed unless "
        "we want to add the domain to the corpus."
    ),
    "none": "No action — passed cleanly.",
}


def get_body(row: dict) -> str:
    return " ".join(s.get("text", "") for s in row.get("sentences", []))


def heuristic_bucket(row: dict) -> str:
    """Slim version of analyze_eval_200's classify_row, used for delta."""
    if row.get("error"):
        return "ERROR"
    if row.get("refused"):
        return "REFUSED"
    sc = row.get("source_counts") or {}
    n_act = sc.get("bare_act", 0)
    n_sc = sc.get("sc_judgment", 0)
    n_hc = sc.get("hc_judgment", 0)
    n_sent = row.get("n_sentences", 0)
    verdict = row.get("relevance_verdict")
    if n_sent == 0:
        return "NO_RELEVANCE"
    if verdict in ("partial", "off_topic"):
        if n_act >= 3:
            return "PARTIAL_low_cosine"
        return "OFF_topic"
    if verdict == "ok":
        if n_act > 0:
            return "OK_grounded"
        if n_hc > 0 and n_sc == 0:
            return "OK_only_hc"
        if n_sc > 0:
            return "OK_only_sc"
    return "UNKNOWN"


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--in", dest="inp", required=True,
                   help="*.judged.jsonl from llm_judge_eval.py")
    p.add_argument("--out", required=True, help="markdown report path")
    p.add_argument("--samples-per-bucket", type=int, default=5)
    args = p.parse_args()

    rows: list[dict] = []
    with open(args.inp) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            rows.append(json.loads(line))
    n = len(rows)
    print(f"loaded {n} rows from {args.inp}")

    # Heuristic distribution (for delta tracking)
    heur = Counter(heuristic_bucket(r) for r in rows)

    # LLM-judge distribution (the honest version)
    judge_issues = Counter()
    judge_dimensions = {
        "correct_act": Counter(),
        "on_topic": Counter(),
        "operationally_actionable": Counter(),
        "dangerous_framing": Counter(),
    }
    by_persona_issue: Counter = Counter()
    samples_by_issue: dict[str, list[dict]] = defaultdict(list)
    parse_errors = 0

    for r in rows:
        j = r.get("judgment", {}) or {}
        if "error" in j:
            parse_errors += 1
            continue
        issue = j.get("real_issue", "none")
        judge_issues[issue] += 1
        by_persona_issue[(r.get("persona", "?"), issue)] += 1
        for dim in judge_dimensions:
            val = j.get(dim)
            if val is not None:
                judge_dimensions[dim][bool(val)] += 1
        if len(samples_by_issue[issue]) < args.samples_per_bucket:
            samples_by_issue[issue].append({
                "query": r.get("query", ""),
                "persona": r.get("persona", "?"),
                "expected_act_hint": r.get("expected_act_hint", "?"),
                "rationale": j.get("rationale", ""),
                "sources": [
                    s.get("anchor", "?") for s in (r.get("sources") or [])[:3]
                ],
            })

    personas = sorted({r.get("persona", "?") for r in rows})
    issues_sorted = [k for k, _ in judge_issues.most_common()]

    # ===== Render =====
    lines: list[str] = []
    lines.append("# 500-query realistic eval — REAL ISSUES")
    lines.append("")
    lines.append(f"_Input: `{args.inp}`_")
    lines.append("")
    lines.append(f"**Total: {n} queries** · "
                 f"**{n - parse_errors} judged**, "
                 f"**{parse_errors} judge-parse errors**")
    lines.append("")

    # ----- Heuristic distribution -----
    lines.append("## Heuristic bucket distribution (for delta tracking)")
    lines.append("")
    lines.append("| Bucket | Count | % |")
    lines.append("|---|---:|---:|")
    for b, c in heur.most_common():
        lines.append(f"| {b} | {c} | {100 * c / n:.0f}% |")
    lines.append("")

    # ----- Pass/fail headline numbers -----
    lines.append("## Quality dimensions (LLM-judge)")
    lines.append("")
    lines.append("| Dimension | True | False | % True |")
    lines.append("|---|---:|---:|---:|")
    for dim, ctr in judge_dimensions.items():
        t = ctr.get(True, 0)
        ft = ctr.get(False, 0)
        tot = t + ft
        pct = (100 * t / tot) if tot else 0
        lines.append(f"| {dim} | {t} | {ft} | {pct:.0f}% |")
    lines.append("")

    # ----- Real issues table -----
    lines.append("## Real issues (ranked by frequency)")
    lines.append("")
    lines.append("| Real issue | Count | % | Fix target |")
    lines.append("|---|---:|---:|---|")
    judged_n = max(1, n - parse_errors)
    for issue, c in judge_issues.most_common():
        fix = FIX_PROPOSALS.get(issue, "—")
        # one-line summary of fix
        fix_short = fix.split(".")[0] + "."
        lines.append(f"| **{issue}** | {c} | {100 * c / judged_n:.0f}% | "
                     f"{fix_short} |")
    lines.append("")

    # ----- Persona × real_issue heatmap -----
    lines.append("## Persona × real_issue heatmap")
    lines.append("")
    lines.append(f"| Issue | " + " | ".join(personas) + " | total |")
    lines.append(f"|---|" + "|".join([":---:"] * (len(personas) + 1)) + "|")
    for issue in issues_sorted:
        counts = [by_persona_issue.get((p, issue), 0) for p in personas]
        lines.append(f"| {issue} | " + " | ".join(str(c) for c in counts)
                     + f" | {sum(counts)} |")
    lines.append("")

    # ----- Detailed per-issue dive -----
    lines.append("## Per-issue deep dive")
    lines.append("")
    for issue, c in judge_issues.most_common():
        if issue == "none":
            continue
        lines.append(f"### `{issue}` — {c} queries ({100*c/judged_n:.0f}%)")
        lines.append("")
        lines.append(f"**Fix proposal:** {FIX_PROPOSALS.get(issue, '—')}")
        lines.append("")
        lines.append(f"**Sample queries (max {args.samples_per_bucket}):**")
        lines.append("")
        for s in samples_by_issue.get(issue, []):
            lines.append(f"- _{s['persona']}_: `{s['query']!r}`")
            lines.append(f"  - expected: {s['expected_act_hint']}")
            lines.append(f"  - cited: {', '.join(s['sources']) or '(none)'}")
            lines.append(f"  - rationale: {s['rationale']}")
            lines.append("")

    # ----- Cross-table: heuristic vs LLM-judge disagreement -----
    lines.append("## Heuristic vs LLM-judge — where they disagree")
    lines.append("")
    lines.append("Surfaces rows where the heuristic bucket says 'fine' "
                 "but the judge flagged a real issue, or vice-versa.")
    lines.append("")
    disagreements = []
    for r in rows:
        j = r.get("judgment", {}) or {}
        if "error" in j:
            continue
        bucket = heuristic_bucket(r)
        issue = j.get("real_issue", "none")
        heur_ok = bucket in ("OK_grounded", "OK_only_sc", "OK_only_hc",
                              "REFUSE_correct")
        judge_ok = issue == "none"
        if heur_ok != judge_ok:
            disagreements.append((bucket, issue, r))
    if disagreements:
        lines.append(f"**{len(disagreements)} disagreements found.** "
                     "Sample of 10:")
        lines.append("")
        lines.append("| Heuristic | LLM-judge | Query |")
        lines.append("|---|---|---|")
        for bucket, issue, r in disagreements[:10]:
            q = r.get("query", "")[:80]
            lines.append(f"| {bucket} | {issue} | `{q}` |")
        lines.append("")
    else:
        lines.append("_(no disagreements — heuristic and judge agree)_")
        lines.append("")

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(lines) + "\n")
    print(f"wrote -> {out}")
    print(f"\nTop 5 real_issues:")
    for k, v in judge_issues.most_common(5):
        print(f"  {k:<28} {v:>4}  ({100*v/judged_n:.0f}%)")


if __name__ == "__main__":
    main()
