#!/usr/bin/env python3
"""Compare two timed /answer eval JSONLs and write a markdown report.

Inputs are produced by scripts/eval_timed_100.py. The comparator also
backfills legal_safety for older rows, so final Codex-vs-Claude reports
use the same safety gate even if one branch did not emit route metadata.

Usage:
  PYTHONPATH=. .venv/bin/python scripts/compare_timed_evals.py \
      --left data/processed/codex.jsonl --left-label Codex \
      --right data/processed/claude.jsonl --right-label Claude \
      --out reports/codex_vs_claude.md
"""
from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any

from scripts.legal_safety_eval import analyze_safety_row, summarize_safety


GATE_EXPECTED_ACT_HIT = 0.85
GATE_MEDIAN_LATENCY_MS = 20_000


def load_rows(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            row = json.loads(line)
            row["legal_safety"] = analyze_safety_row(row)
            rows.append(row)
    return rows


def summarize_run(rows: list[dict[str, Any]]) -> dict[str, Any]:
    scored = [row for row in rows if row.get("expected_act_hit") is not None]
    act_hits = sum(1 for row in scored if row.get("expected_act_hit") is True)
    verdicts = Counter(
        row.get("relevance_verdict") or ("refused" if row.get("refused") else "no_relevance")
        for row in rows
    )
    route_events = sum(1 for row in rows if row.get("route_category"))
    timing_events = sum(1 for row in rows if isinstance(row.get("timing"), dict) and row["timing"])
    action_packs = sum(1 for row in rows if row.get("action_pack_id"))
    safety = summarize_safety(rows)

    wall_vals = [_latency_ms(row, prefer_wall=True) for row in rows]
    total_vals = [_stage_ms(row, "total_ms") or _latency_ms(row) for row in rows]
    return {
        "rows": len(rows),
        "errors": sum(1 for row in rows if row.get("error")),
        "refused": sum(1 for row in rows if row.get("refused")),
        "verdicts": verdicts,
        "act_hits": act_hits,
        "act_scored": len(scored),
        "act_hit_rate": (act_hits / len(scored)) if scored else None,
        "route_events": route_events,
        "timing_events": timing_events,
        "action_packs": action_packs,
        "safety": safety,
        "wall_p50": percentile(wall_vals, 0.50),
        "wall_p90": percentile(wall_vals, 0.90),
        "wall_max": max([v for v in wall_vals if v is not None], default=None),
        "total_p50": percentile(total_vals, 0.50),
        "total_p90": percentile(total_vals, 0.90),
        "total_max": max([v for v in total_vals if v is not None], default=None),
    }


def write_report(
    *,
    left_rows: list[dict[str, Any]],
    right_rows: list[dict[str, Any]],
    left_label: str,
    right_label: str,
    left_path: Path,
    right_path: Path,
    out: Path,
    title: str,
) -> None:
    left_summary = summarize_run(left_rows)
    right_summary = summarize_run(right_rows)
    pairs = paired_rows(left_rows, right_rows)
    left_by_query = {str(row.get("query") or ""): row for row in left_rows}
    right_by_query = {str(row.get("query") or ""): row for row in right_rows}

    lines: list[str] = [
        f"# {title}",
        "",
        f"Left: **{left_label}** (`{left_path}`)",
        f"Right: **{right_label}** (`{right_path}`)",
        f"Common prompts: **{len(pairs)}**",
        "",
        "## Scorecard",
        "",
        "| metric | " + left_label + " | " + right_label + " | readout |",
        "| --- | ---: | ---: | --- |",
    ]
    for metric, left_value, right_value, readout in _scorecard_rows(left_summary, right_summary, left_label, right_label):
        lines.append(f"| {metric} | {left_value} | {right_value} | {readout} |")

    lines.extend([
        "",
        "## Gate Check",
        "",
        "| gate | target | " + left_label + " | " + right_label + " |",
        "| --- | ---: | ---: | ---: |",
        _gate_row("Expected Act hit", ">=85%", _fmt_rate(left_summary["act_hits"], left_summary["act_scored"]), _fmt_rate(right_summary["act_hits"], right_summary["act_scored"])),
        _gate_row("Median wall latency", "<20s", fmt_ms(left_summary["wall_p50"]), fmt_ms(right_summary["wall_p50"])),
        _gate_row("Legal-safety hard fails", "0", str(left_summary["safety"]["hard_fails"]), str(right_summary["safety"]["hard_fails"])),
        _gate_row("Route telemetry", "required", f"{left_summary['route_events']}/{left_summary['rows']}", f"{right_summary['route_events']}/{right_summary['rows']}"),
        _gate_row("Timing telemetry", "required", f"{left_summary['timing_events']}/{left_summary['rows']}", f"{right_summary['timing_events']}/{right_summary['rows']}"),
    ])

    lines.extend([
        "",
        "## Legal Safety Labels",
        "",
        "| label | " + left_label + " | " + right_label + " |",
        "| --- | ---: | ---: |",
    ])
    all_labels = sorted(
        set(left_summary["safety"]["label_counts"])
        | set(right_summary["safety"]["label_counts"])
        | {
            "wrong_forum",
            "wrong_deadline",
            "wrong_regime",
            "dangerous_off_topic",
            "unsafe_refusal",
            "dangerous_framing",
        }
    )
    for label in all_labels:
        left_count = left_summary["safety"]["label_counts"].get(label, 0)
        right_count = right_summary["safety"]["label_counts"].get(label, 0)
        lines.append(f"| {label} | {left_count} | {right_count} |")

    lines.extend(_latency_section(left_rows, right_rows, left_label, right_label))
    lines.extend(_expected_act_head_to_head(pairs, left_label, right_label))
    lines.extend(_safety_failures_section(left_rows, right_rows, left_label, right_label))
    lines.extend(_unmatched_prompts_section(left_rows, right_rows, left_label, right_label))
    lines.extend(_full_prompt_table(pairs, left_by_query, right_by_query, left_label, right_label))

    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")


def paired_rows(left_rows: list[dict[str, Any]], right_rows: list[dict[str, Any]]) -> list[tuple[int, dict[str, Any], dict[str, Any]]]:
    right_by_query = {_query_key(row): row for row in right_rows}
    pairs: list[tuple[int, dict[str, Any], dict[str, Any]]] = []
    for idx, left in enumerate(left_rows, 1):
        key = _query_key(left)
        right = right_by_query.get(key)
        if right is not None:
            pairs.append((idx, left, right))
    return pairs


def percentile(values: list[float | None], pct: float) -> float | None:
    vals = sorted(v for v in values if v is not None)
    if not vals:
        return None
    if len(vals) == 1:
        return vals[0]
    idx = (len(vals) - 1) * pct
    lo = int(idx)
    hi = min(lo + 1, len(vals) - 1)
    frac = idx - lo
    return vals[lo] * (1 - frac) + vals[hi] * frac


def fmt_ms(value: float | None) -> str:
    if value is None:
        return "n/a"
    return f"{value / 1000:.1f}s"


def _latency_ms(row: dict[str, Any], *, prefer_wall: bool = False) -> float | None:
    if prefer_wall and isinstance(row.get("wall_ms"), int | float):
        return float(row["wall_ms"])
    timing = row.get("timing")
    if isinstance(timing, dict) and isinstance(timing.get("total_ms"), int | float):
        return float(timing["total_ms"])
    if isinstance(row.get("wall_ms"), int | float):
        return float(row["wall_ms"])
    return None


def _stage_ms(row: dict[str, Any], stage: str) -> float | None:
    timing = row.get("timing")
    if isinstance(timing, dict) and isinstance(timing.get(stage), int | float):
        return float(timing[stage])
    return None


def _scorecard_rows(left: dict[str, Any], right: dict[str, Any], left_label: str, right_label: str) -> list[tuple[str, str, str, str]]:
    return [
        ("Rows completed", str(left["rows"]), str(right["rows"]), "tie" if left["rows"] == right["rows"] else "different row counts"),
        ("Errors", str(left["errors"]), str(right["errors"]), _lower_is_better(left["errors"], right["errors"], left_label, right_label)),
        ("Refused", str(left["refused"]), str(right["refused"]), _lower_is_better(left["refused"], right["refused"], left_label, right_label)),
        ("Relevance ok", str(left["verdicts"].get("ok", 0)), str(right["verdicts"].get("ok", 0)), _higher_is_better(left["verdicts"].get("ok", 0), right["verdicts"].get("ok", 0), left_label, right_label)),
        ("Expected Act hit", _fmt_rate(left["act_hits"], left["act_scored"]), _fmt_rate(right["act_hits"], right["act_scored"]), _higher_is_better(left["act_hit_rate"], right["act_hit_rate"], left_label, right_label)),
        ("Legal-safety hard fails", str(left["safety"]["hard_fails"]), str(right["safety"]["hard_fails"]), _lower_is_better(left["safety"]["hard_fails"], right["safety"]["hard_fails"], left_label, right_label)),
        ("Wall latency p50", fmt_ms(left["wall_p50"]), fmt_ms(right["wall_p50"]), _lower_is_better(left["wall_p50"], right["wall_p50"], left_label, right_label)),
        ("Wall latency p90", fmt_ms(left["wall_p90"]), fmt_ms(right["wall_p90"]), _lower_is_better(left["wall_p90"], right["wall_p90"], left_label, right_label)),
        ("Route events", f"{left['route_events']}/{left['rows']}", f"{right['route_events']}/{right['rows']}", _higher_is_better(left["route_events"], right["route_events"], left_label, right_label)),
        ("Timing events", f"{left['timing_events']}/{left['rows']}", f"{right['timing_events']}/{right['rows']}", _higher_is_better(left["timing_events"], right["timing_events"], left_label, right_label)),
        ("Action packs", f"{left['action_packs']}/{left['rows']}", f"{right['action_packs']}/{right['rows']}", _higher_is_better(left["action_packs"], right["action_packs"], left_label, right_label)),
    ]


def _latency_section(left_rows: list[dict[str, Any]], right_rows: list[dict[str, Any]], left_label: str, right_label: str) -> list[str]:
    stages = [
        ("wall_ms", None),
        ("total_ms", "total_ms"),
        ("retrieval_ms", "retrieval_ms"),
        ("llm_stream_ms", "llm_stream_ms"),
        ("verification_ms", "verification_ms"),
    ]
    lines = [
        "",
        "## Latency Detail",
        "",
        "| stage | " + left_label + " p50 | " + left_label + " p90 | " + right_label + " p50 | " + right_label + " p90 |",
        "| --- | ---: | ---: | ---: | ---: |",
    ]
    for label, stage in stages:
        left_vals = [_latency_ms(row, prefer_wall=True) if stage is None else _stage_ms(row, stage) for row in left_rows]
        right_vals = [_latency_ms(row, prefer_wall=True) if stage is None else _stage_ms(row, stage) for row in right_rows]
        lines.append(
            f"| {label} | {fmt_ms(percentile(left_vals, 0.50))} | "
            f"{fmt_ms(percentile(left_vals, 0.90))} | "
            f"{fmt_ms(percentile(right_vals, 0.50))} | "
            f"{fmt_ms(percentile(right_vals, 0.90))} |"
        )
    return lines


def _expected_act_head_to_head(pairs: list[tuple[int, dict[str, Any], dict[str, Any]]], left_label: str, right_label: str) -> list[str]:
    buckets: dict[str, list[int]] = {
        "Both hit": [],
        f"{left_label} hit, {right_label} missed": [],
        f"{right_label} hit, {left_label} missed": [],
        "Both missed": [],
    }
    for idx, left, right in pairs:
        if left.get("expected_act_hit") is None and right.get("expected_act_hit") is None:
            continue
        l_hit = left.get("expected_act_hit") is True
        r_hit = right.get("expected_act_hit") is True
        if l_hit and r_hit:
            buckets["Both hit"].append(idx)
        elif l_hit and not r_hit:
            buckets[f"{left_label} hit, {right_label} missed"].append(idx)
        elif r_hit and not l_hit:
            buckets[f"{right_label} hit, {left_label} missed"].append(idx)
        else:
            buckets["Both missed"].append(idx)

    lines = [
        "",
        "## Expected Act Head-to-Head",
        "",
        "| bucket | count | rows |",
        "| --- | ---: | --- |",
    ]
    for bucket, rows in buckets.items():
        lines.append(f"| {bucket} | {len(rows)} | {', '.join(str(i) for i in rows[:80])} |")
    return lines


def _safety_failures_section(left_rows: list[dict[str, Any]], right_rows: list[dict[str, Any]], left_label: str, right_label: str) -> list[str]:
    lines = [
        "",
        "## Legal-Safety Failures To Inspect",
        "",
        "| system | row | labels | route | prompt | reasons |",
        "| --- | ---: | --- | --- | --- | --- |",
    ]
    for label, rows in ((left_label, left_rows), (right_label, right_rows)):
        for idx, row in enumerate(rows, 1):
            safety = row.get("legal_safety") or {}
            if not safety.get("hard_fail"):
                continue
            labels = ", ".join(k for k, v in (safety.get("labels") or {}).items() if v)
            prompt = _md_cell(str(row.get("query") or "")[:120])
            reasons = _md_cell("; ".join(safety.get("reasons") or [])[:160])
            lines.append(f"| {label} | {idx} | {labels} | {row.get('route_category') or ''} | {prompt} | {reasons} |")
            if sum(1 for line in lines if line.startswith(f"| {label} |")) >= 30:
                break
    return lines


def _unmatched_prompts_section(left_rows: list[dict[str, Any]], right_rows: list[dict[str, Any]], left_label: str, right_label: str) -> list[str]:
    left_keys = {_query_key(row) for row in left_rows}
    right_keys = {_query_key(row) for row in right_rows}
    left_only = [row for row in left_rows if _query_key(row) not in right_keys]
    right_only = [row for row in right_rows if _query_key(row) not in left_keys]
    lines = [
        "",
        "## Unmatched Prompts",
        "",
        f"- {left_label} only: {len(left_only)}",
        f"- {right_label} only: {len(right_only)}",
        "",
    ]
    if not left_only and not right_only:
        lines.append("All prompts are paired.")
        return lines
    lines.extend([
        "| system | persona | prompt |",
        "| --- | --- | --- |",
    ])
    for label, rows in ((left_label, left_only), (right_label, right_only)):
        for row in rows[:50]:
            lines.append(
                f"| {label} | {row.get('persona') or ''} | "
                f"{_md_cell(str(row.get('query') or '')[:140])} |"
            )
    return lines


def _full_prompt_table(
    pairs: list[tuple[int, dict[str, Any], dict[str, Any]]],
    left_by_query: dict[str, dict[str, Any]],
    right_by_query: dict[str, dict[str, Any]],
    left_label: str,
    right_label: str,
) -> list[str]:
    lines = [
        "",
        "## Full Prompt Comparison",
        "",
        "| # | persona | prompt | expected Acts | "
        + left_label + " outcome | " + left_label + " act | " + left_label + " safety | " + left_label + " time | " + left_label + " route | "
        + right_label + " outcome | " + right_label + " act | " + right_label + " safety | " + right_label + " time | " + right_label + " route |",
        "| ---: | --- | --- | --- | --- | ---: | --- | ---: | --- | --- | ---: | --- | ---: | --- |",
    ]
    for display_idx, (_, left, right) in enumerate(pairs, 1):
        query = str(left.get("query") or right.get("query") or "")
        left_row = left_by_query.get(query, left)
        right_row = right_by_query.get(query, right)
        lines.append(
            f"| {display_idx} | {left.get('persona') or right.get('persona') or ''} | "
            f"{_md_cell(query[:110])} | {_md_cell(_expected_acts(left_row))} | "
            f"{_outcome(left_row)} | {_hit_cell(left_row)} | {_safety_cell(left_row)} | {fmt_ms(_latency_ms(left_row))} | {_md_cell(str(left_row.get('route_category') or ''))} | "
            f"{_outcome(right_row)} | {_hit_cell(right_row)} | {_safety_cell(right_row)} | {fmt_ms(_latency_ms(right_row))} | {_md_cell(str(right_row.get('route_category') or ''))} |"
        )
    return lines


def _outcome(row: dict[str, Any]) -> str:
    if row.get("error"):
        return "ERR"
    if row.get("refused"):
        return "REF"
    return str(row.get("relevance_verdict") or "NO_REL")


def _hit_cell(row: dict[str, Any]) -> str:
    hit = row.get("expected_act_hit")
    if hit is True:
        return "Y"
    if hit is False:
        return "N"
    return "-"


def _safety_cell(row: dict[str, Any]) -> str:
    safety = row.get("legal_safety") or {}
    if not safety.get("hard_fail"):
        return "pass"
    labels = [k for k, v in (safety.get("labels") or {}).items() if v]
    return ", ".join(labels) or "fail"


def _expected_acts(row: dict[str, Any]) -> str:
    keys = row.get("expected_act_keys")
    if isinstance(keys, list) and keys:
        return ", ".join(str(item) for item in keys)
    return str(row.get("expected_act_hint") or "")


def _fmt_rate(hits: int, total: int) -> str:
    if not total:
        return "n/a"
    return f"{hits}/{total} ({hits / total * 100:.1f}%)"


def _gate_row(name: str, target: str, left_value: str, right_value: str) -> str:
    return f"| {name} | {target} | {left_value} | {right_value} |"


def _higher_is_better(left: float | int | None, right: float | int | None, left_label: str, right_label: str) -> str:
    if left is None or right is None:
        return "n/a"
    if left == right:
        return "tie"
    return f"{left_label} better" if left > right else f"{right_label} better"


def _lower_is_better(left: float | int | None, right: float | int | None, left_label: str, right_label: str) -> str:
    if left is None or right is None:
        return "n/a"
    if left == right:
        return "tie"
    return f"{left_label} better" if left < right else f"{right_label} better"


def _md_cell(text: str) -> str:
    return text.replace("|", " ").replace("\n", " ")


def _query_key(row: dict[str, Any]) -> str:
    return str(row.get("query") or "").strip().lower()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--left", type=Path, required=True)
    parser.add_argument("--right", type=Path, required=True)
    parser.add_argument("--left-label", default="Left")
    parser.add_argument("--right-label", default="Right")
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--title", default="Timed Eval Comparison")
    args = parser.parse_args()

    left_rows = load_rows(args.left)
    right_rows = load_rows(args.right)
    write_report(
        left_rows=left_rows,
        right_rows=right_rows,
        left_label=args.left_label,
        right_label=args.right_label,
        left_path=args.left,
        right_path=args.right,
        out=args.out,
        title=args.title,
    )
    print(f"wrote -> {args.out}")


if __name__ == "__main__":
    main()
