#!/usr/bin/env python3
"""Fail closed if a Legal-HyDE experiment regresses the frozen baseline.

This is stricter than a normal comparator. Legal-HyDE-lite is a retrieval
experiment, not a production default. It can only move forward if the exact
same prompt set ties or improves the current baseline on quality, safety,
answer citations, and latency.

Usage:
  PYTHONPATH=. uv run python scripts/legal_hyde_regression_gate.py \
    --baseline data/processed/eval_off.jsonl \
    --experiment data/processed/eval_hyde_fallback.jsonl \
    --out reports/legal_hyde_gate.md
"""
from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from scripts.compare_timed_evals import fmt_ms, load_rows, summarize_run


@dataclass(frozen=True)
class GateConfig:
    max_act_regression_pp: float = 0.0
    max_act_cited_regression_pp: float = 0.0
    max_relevance_ok_regression: int = 0
    max_refusal_increase: int = 0
    max_p50_regression_ms: float = 0.0
    max_p90_regression_ms: float = 0.0


def summarize_gate_rows(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Summarize eval rows with row-aware fields needed for enablement gating."""
    summary = summarize_run(rows)
    cited_scored = [row for row in rows if row.get("expected_act_cited_hit") is not None]
    cited_hits = sum(1 for row in cited_scored if row.get("expected_act_cited_hit") is True)
    summary.update(
        {
            "prompt_signatures": [_prompt_signature(row) for row in rows],
            "act_cited_hits": cited_hits,
            "act_cited_scored": len(cited_scored),
            "act_cited_hit_rate": (cited_hits / len(cited_scored)) if cited_scored else None,
            "wall_latency_count": sum(1 for row in rows if _row_latency_ms(row) is not None),
        }
    )
    return summary


def evaluate_gate(
    baseline: dict[str, Any],
    experiment: dict[str, Any],
    *,
    config: GateConfig = GateConfig(),
) -> list[str]:
    """Return human-readable failure reasons for a HyDE experiment."""
    failures: list[str] = []

    _check_prompt_identity(failures, baseline, experiment)

    if experiment["rows"] != baseline["rows"]:
        failures.append(
            f"row count changed: baseline={baseline['rows']} experiment={experiment['rows']}"
        )
    if experiment["errors"] > baseline["errors"]:
        failures.append(
            f"errors increased: baseline={baseline['errors']} experiment={experiment['errors']}"
        )
    if experiment["safety"]["hard_fails"] > baseline["safety"]["hard_fails"]:
        failures.append(
            "legal-safety hard fails increased: "
            f"baseline={baseline['safety']['hard_fails']} "
            f"experiment={experiment['safety']['hard_fails']}"
        )

    _check_rate(
        failures,
        label="expected Act hit",
        baseline_rate=baseline.get("act_hit_rate"),
        experiment_rate=experiment.get("act_hit_rate"),
        max_regression_pp=config.max_act_regression_pp,
    )
    _check_rate(
        failures,
        label="expected Act cited hit",
        baseline_rate=baseline.get("act_cited_hit_rate"),
        experiment_rate=experiment.get("act_cited_hit_rate"),
        max_regression_pp=config.max_act_cited_regression_pp,
    )
    if baseline.get("act_cited_scored") != experiment.get("act_cited_scored"):
        failures.append(
            "expected Act cited scored count changed: "
            f"baseline={baseline.get('act_cited_scored', 0)} "
            f"experiment={experiment.get('act_cited_scored', 0)}"
        )

    base_ok = int(baseline["verdicts"].get("ok", 0))
    exp_ok = int(experiment["verdicts"].get("ok", 0))
    if exp_ok < base_ok - config.max_relevance_ok_regression:
        failures.append(f"relevance ok decreased: baseline={base_ok} experiment={exp_ok}")

    if experiment["refused"] > baseline["refused"] + config.max_refusal_increase:
        failures.append(
            f"refusals increased: baseline={baseline['refused']} "
            f"experiment={experiment['refused']}"
        )

    for label, summary in (("baseline", baseline), ("experiment", experiment)):
        if summary.get("wall_latency_count") != summary["rows"]:
            failures.append(
                f"{label} wall latency telemetry incomplete: "
                f"{summary.get('wall_latency_count', 0)}/{summary['rows']}"
            )

    _check_latency(
        failures,
        baseline,
        experiment,
        key="wall_p50",
        budget_ms=config.max_p50_regression_ms,
        label="wall p50",
    )
    _check_latency(
        failures,
        baseline,
        experiment,
        key="wall_p90",
        budget_ms=config.max_p90_regression_ms,
        label="wall p90",
    )
    return failures


def write_gate_report(
    *,
    baseline: dict[str, Any],
    experiment: dict[str, Any],
    baseline_path: Path,
    experiment_path: Path,
    out: Path,
    failures: list[str],
) -> None:
    status = "FAIL" if failures else "PASS"
    lines = [
        "# Legal-HyDE Regression Gate",
        "",
        f"Status: **{status}**",
        f"Baseline: `{baseline_path}`",
        f"Experiment: `{experiment_path}`",
        "",
        "## Scorecard",
        "",
        "| metric | baseline | experiment |",
        "| --- | ---: | ---: |",
        f"| rows | {baseline['rows']} | {experiment['rows']} |",
        f"| errors | {baseline['errors']} | {experiment['errors']} |",
        f"| refused | {baseline['refused']} | {experiment['refused']} |",
        "| relevance ok | "
        f"{baseline['verdicts'].get('ok', 0)} | {experiment['verdicts'].get('ok', 0)} |",
        "| expected Act hit | "
        f"{_fmt_rate(baseline)} | {_fmt_rate(experiment)} |",
        "| expected Act cited hit | "
        f"{_fmt_cited_rate(baseline)} | {_fmt_cited_rate(experiment)} |",
        "| legal-safety hard fails | "
        f"{baseline['safety']['hard_fails']} | {experiment['safety']['hard_fails']} |",
        "| wall latency coverage | "
        f"{baseline.get('wall_latency_count', 0)}/{baseline['rows']} | "
        f"{experiment.get('wall_latency_count', 0)}/{experiment['rows']} |",
        f"| wall latency p50 | {fmt_ms(baseline['wall_p50'])} | {fmt_ms(experiment['wall_p50'])} |",
        f"| wall latency p90 | {fmt_ms(baseline['wall_p90'])} | {fmt_ms(experiment['wall_p90'])} |",
        "",
        "## Failures",
        "",
    ]
    lines.extend([f"- {failure}" for failure in failures] or ["- None"])
    lines.extend(
        [
            "",
            "## Rule",
            "",
            "Legal-HyDE-lite may only proceed when the same prompt set ties or improves "
            "quality, safety, answer citations, and latency. Keep "
            "`LEGAL_HYDE_MODE=off` until this report passes on the product eval set.",
        ]
    )
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--baseline", type=Path, required=True)
    parser.add_argument("--experiment", type=Path, required=True)
    parser.add_argument("--out", type=Path)
    parser.add_argument("--max-act-regression-pp", type=float, default=0.0)
    parser.add_argument("--max-act-cited-regression-pp", type=float, default=0.0)
    parser.add_argument("--max-relevance-ok-regression", type=int, default=0)
    parser.add_argument("--max-refusal-increase", type=int, default=0)
    parser.add_argument("--max-p50-regression-ms", type=float, default=0.0)
    parser.add_argument("--max-p90-regression-ms", type=float, default=0.0)
    args = parser.parse_args()

    baseline = summarize_gate_rows(load_rows(args.baseline))
    experiment = summarize_gate_rows(load_rows(args.experiment))
    config = GateConfig(
        max_act_regression_pp=args.max_act_regression_pp,
        max_act_cited_regression_pp=args.max_act_cited_regression_pp,
        max_relevance_ok_regression=args.max_relevance_ok_regression,
        max_refusal_increase=args.max_refusal_increase,
        max_p50_regression_ms=args.max_p50_regression_ms,
        max_p90_regression_ms=args.max_p90_regression_ms,
    )
    failures = evaluate_gate(baseline, experiment, config=config)

    if args.out:
        write_gate_report(
            baseline=baseline,
            experiment=experiment,
            baseline_path=args.baseline,
            experiment_path=args.experiment,
            out=args.out,
            failures=failures,
        )

    if failures:
        print("Legal-HyDE gate: FAIL")
        for failure in failures:
            print(f"- {failure}")
        raise SystemExit(1)
    print("Legal-HyDE gate: PASS")


def _check_prompt_identity(
    failures: list[str],
    baseline: dict[str, Any],
    experiment: dict[str, Any],
) -> None:
    base_prompts = baseline.get("prompt_signatures")
    exp_prompts = experiment.get("prompt_signatures")
    if not isinstance(base_prompts, list) or not isinstance(exp_prompts, list):
        failures.append("prompt signatures missing; cannot prove same prompt set")
        return
    if base_prompts == exp_prompts:
        return
    mismatch_at = next(
        (
            idx
            for idx, (base, exp) in enumerate(zip(base_prompts, exp_prompts), start=1)
            if base != exp
        ),
        min(len(base_prompts), len(exp_prompts)) + 1,
    )
    baseline_value = (
        base_prompts[mismatch_at - 1] if mismatch_at <= len(base_prompts) else "<missing>"
    )
    experiment_value = (
        exp_prompts[mismatch_at - 1] if mismatch_at <= len(exp_prompts) else "<missing>"
    )
    failures.append(
        "prompt set/order changed: "
        f"first_mismatch_row={mismatch_at} "
        f"baseline={_short_prompt(baseline_value)} "
        f"experiment={_short_prompt(experiment_value)}"
    )


def _check_rate(
    failures: list[str],
    *,
    label: str,
    baseline_rate: float | None,
    experiment_rate: float | None,
    max_regression_pp: float,
) -> None:
    if baseline_rate is None and experiment_rate is None:
        return
    if baseline_rate is None or experiment_rate is None:
        failures.append(
            f"{label} telemetry missing: baseline={baseline_rate} experiment={experiment_rate}"
        )
        return
    allowed = baseline_rate - (max_regression_pp / 100.0)
    if experiment_rate < allowed:
        failures.append(
            f"{label} regressed: baseline={_pct(baseline_rate)} "
            f"experiment={_pct(experiment_rate)}"
        )


def _check_latency(
    failures: list[str],
    baseline: dict[str, Any],
    experiment: dict[str, Any],
    *,
    key: str,
    budget_ms: float,
    label: str,
) -> None:
    base_value = baseline.get(key)
    exp_value = experiment.get(key)
    if base_value is None or exp_value is None:
        failures.append(
            f"{label} latency telemetry missing: baseline={fmt_ms(base_value)} "
            f"experiment={fmt_ms(exp_value)}"
        )
        return
    if exp_value > base_value + budget_ms:
        failures.append(
            f"{label} latency regressed: baseline={fmt_ms(base_value)} "
            f"experiment={fmt_ms(exp_value)} budget=+{budget_ms / 1000:.1f}s"
        )


def _row_latency_ms(row: dict[str, Any]) -> float | None:
    timing = row.get("timing")
    if isinstance(row.get("wall_ms"), int | float):
        return float(row["wall_ms"])
    if isinstance(timing, dict) and isinstance(timing.get("total_ms"), int | float):
        return float(timing["total_ms"])
    return None


def _prompt_signature(row: dict[str, Any]) -> str:
    parts = [
        str(row.get("base_id") or row.get("id") or "").strip(),
        _norm_prompt(row.get("query")),
        _norm_prompt(row.get("expected_act_hint")),
        _norm_prompt(row.get("expected_category")),
        _norm_prompt(row.get("product_priority")),
    ]
    return " | ".join(parts)


def _norm_prompt(value: Any) -> str:
    return " ".join(str(value or "").strip().lower().split())


def _short_prompt(value: Any) -> str:
    text = str(value)
    return text if len(text) <= 120 else text[:117] + "..."


def _fmt_rate(summary: dict[str, Any]) -> str:
    if summary.get("act_hit_rate") is None:
        return "n/a"
    return (
        f"{summary['act_hits']}/{summary['act_scored']} "
        f"({_pct(float(summary['act_hit_rate']))})"
    )


def _fmt_cited_rate(summary: dict[str, Any]) -> str:
    if summary.get("act_cited_hit_rate") is None:
        return "n/a"
    return (
        f"{summary['act_cited_hits']}/{summary['act_cited_scored']} "
        f"({_pct(float(summary['act_cited_hit_rate']))})"
    )


def _pct(value: float) -> str:
    return f"{value * 100:.1f}%"


if __name__ == "__main__":
    main()
