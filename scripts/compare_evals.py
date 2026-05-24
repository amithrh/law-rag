#!/usr/bin/env python3
"""Compare two or more eval_500_*.judged.jsonl files.

Produces a delta report showing what changed between runs:
  - Per-bucket count changes
  - Per-real_issue count changes
  - Queries that REGRESSED (better in earlier run, worse in later)
  - Queries that IMPROVED (worse in earlier, better in later)
  - Net pass-rate movement on the 4 quality dimensions

This is the per-stage delta tool. The 4-run sweep is:
  baseline (Day 0)
  +reranker (after Stage 3)
  +student (after Stage 4)
  +HC (after Day 5)

Usage:
  PYTHONPATH=. .venv/bin/python scripts/compare_evals.py \\
      --runs data/processed/eval_500_baseline_LATEST.judged.jsonl \\
             data/processed/eval_500_postrerank_LATEST.judged.jsonl \\
      --out  data/processed/eval_500_DELTA_baseline_vs_postrerank.md
"""
from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).parent.parent


def load_judged(path: Path) -> dict[str, dict]:
    """Return {query: judgment_row}."""
    out: dict[str, dict] = {}
    with path.open() as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            d = json.loads(line)
            out[d["query"]] = d
    return out


def is_pass(j: dict) -> bool:
    """Whole-row pass criterion: correct_act AND on_topic AND actionable
    AND NOT dangerous AND real_issue == 'none'."""
    if not j:
        return False
    if "error" in j:
        return False
    return (
        j.get("correct_act", False)
        and j.get("on_topic", False)
        and j.get("operationally_actionable", False)
        and not j.get("dangerous_framing", False)
        and j.get("real_issue", "?") == "none"
    )


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--runs", nargs="+", required=True,
                   help="Two or more *.judged.jsonl files in chronological order")
    p.add_argument("--labels", nargs="+", default=None,
                   help="Short label per run (default: filename stem)")
    p.add_argument("--out", required=True, help="markdown report path")
    args = p.parse_args()

    if len(args.runs) < 2:
        raise SystemExit("need at least 2 runs to compare")
    labels = args.labels or [Path(r).stem.split(".")[0] for r in args.runs]
    if len(labels) != len(args.runs):
        raise SystemExit("label count must match run count")

    runs = [load_judged(Path(r)) for r in args.runs]
    common = set(runs[0].keys())
    for r in runs[1:]:
        common &= set(r.keys())
    print(f"loaded runs: {[len(r) for r in runs]}; "
          f"common queries: {len(common)}")

    # Per-run summary
    summary_rows = []
    for label, run in zip(labels, runs):
        n = len(run)
        passes = sum(1 for d in run.values()
                     if is_pass(d.get("judgment", {})))
        issues = Counter(d.get("judgment", {}).get("real_issue", "?")
                         for d in run.values())
        summary_rows.append({
            "label": label,
            "n": n,
            "pass": passes,
            "pass_pct": 100 * passes / n if n else 0,
            "issues": issues,
        })

    # Movement on the common set
    moves = []
    for q in common:
        path = []
        for run in runs:
            j = run[q].get("judgment", {})
            path.append({
                "pass": is_pass(j),
                "issue": j.get("real_issue", "?"),
            })
        moves.append({"query": q, "path": path, "row": runs[0][q]})

    # Regressions = pass at run i, fail at run j>i
    regressions = [m for m in moves
                   if m["path"][0]["pass"] and not m["path"][-1]["pass"]]
    improvements = [m for m in moves
                    if not m["path"][0]["pass"] and m["path"][-1]["pass"]]

    # ----- Render -----
    lines: list[str] = []
    lines.append(f"# Eval delta: {' → '.join(labels)}")
    lines.append("")
    lines.append(f"Common queries across all runs: **{len(common)}**")
    lines.append("")

    lines.append("## Pass-rate summary")
    lines.append("")
    lines.append("| Run | n | pass | pass-rate |")
    lines.append("|---|---:|---:|---:|")
    for s in summary_rows:
        lines.append(f"| {s['label']} | {s['n']} | {s['pass']} | "
                     f"{s['pass_pct']:.1f}% |")
    lines.append("")

    # Deltas in pass-rate
    if len(summary_rows) >= 2:
        lines.append("**Delta:** "
                     + " · ".join(
                         f"`{a['label']}` → `{b['label']}`: "
                         f"{b['pass_pct'] - a['pass_pct']:+.1f}pp"
                         for a, b in zip(summary_rows, summary_rows[1:])
                     ))
        lines.append("")

    # Per-issue table (one column per run)
    lines.append("## real_issue counts per run")
    lines.append("")
    all_issues = set()
    for s in summary_rows:
        all_issues |= set(s["issues"].keys())
    lines.append("| Issue | " + " | ".join(labels) + " |")
    lines.append("|---|" + "|".join([":---:"] * len(labels)) + "|")
    for issue in sorted(all_issues):
        counts = [s["issues"].get(issue, 0) for s in summary_rows]
        lines.append(f"| {issue} | " + " | ".join(str(c) for c in counts)
                     + " |")
    lines.append("")

    # Regressions
    lines.append(f"## Regressions ({labels[0]} → {labels[-1]}) — "
                 f"{len(regressions)} queries")
    lines.append("")
    if regressions:
        lines.append("Queries that passed at baseline but failed in the latest run. "
                     "These need investigation — something we shipped made them worse.")
        lines.append("")
        lines.append("| Persona | Query | Latest issue |")
        lines.append("|---|---|---|")
        for m in regressions[:20]:
            r = m["row"]
            q = m["query"][:80]
            issue = m["path"][-1]["issue"]
            lines.append(f"| {r.get('persona', '?')} | `{q}` | {issue} |")
        lines.append("")
    else:
        lines.append("_(none — no queries regressed)_")
        lines.append("")

    # Improvements
    lines.append(f"## Improvements ({labels[0]} → {labels[-1]}) — "
                 f"{len(improvements)} queries")
    lines.append("")
    if improvements:
        lines.append("Queries that failed at baseline but pass in the latest run. "
                     "Shows what the training/ingest actually fixed.")
        lines.append("")
        lines.append("| Persona | Query | Original issue → none |")
        lines.append("|---|---|---|")
        for m in improvements[:20]:
            r = m["row"]
            q = m["query"][:80]
            orig = m["path"][0]["issue"]
            lines.append(f"| {r.get('persona', '?')} | `{q}` | {orig} → none |")
        lines.append("")
    else:
        lines.append("_(none — no queries improved)_")
        lines.append("")

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(lines) + "\n")
    print(f"wrote -> {out}")
    print(f"  regressions: {len(regressions)}")
    print(f"  improvements: {len(improvements)}")


if __name__ == "__main__":
    main()
