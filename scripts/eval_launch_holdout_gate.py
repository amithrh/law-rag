#!/usr/bin/env python3
"""Production launch gate for a true holdout set.

This wraps the common-user gate with launch-only checks:

- prompt rows must carry hard product metadata;
- critical/high-risk rows cannot be owned by the LLM;
- any missing route-required authority must be surfaced to the user through the
  `source_gap` event;
- safe source-gap answers are still not production-clean.

It is intentionally stricter than the broad synthetic 500 gate.
"""
from __future__ import annotations

import argparse
import json
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from scripts.eval_common_user_gate import (
    GateConfig,
    evaluate_gate,
    load_eval_rows,
    load_prompt_rows,
    md,
    score_rows,
    summarize,
    write_failures_jsonl,
)


PRIORITIES = {"critical", "high", "medium", "low"}
CRITICAL_LAUNCH_ROUTES = {
    "arrest_custody_safeguard",
    "bonded_labour_rescue",
    "criminal_defence_bail",
    "criminal_general",
    "family_domestic",
    "labour_exploitation_discrimination",
    "police_fir",
    "tribal_caste_atrocity",
}


@dataclass(frozen=True)
class LaunchGateConfig:
    min_rows: int = 100
    min_true_holdout_rows: int = 50
    min_critical_rows: int = 30
    min_product_pass_pct: float = 95.0
    min_high_priority_pass_pct: float = 95.0
    min_critical_pass_pct: float = 100.0
    max_metadata_errors: int = 0
    max_llm_owned_critical_rows: int = 0
    max_non_reviewed_critical_rows: int = 0
    max_missing_visible_source_gap_rows: int = 0


def main() -> int:
    args = parse_args()
    config = LaunchGateConfig(
        min_rows=args.min_rows,
        min_true_holdout_rows=args.min_true_holdout_rows,
        min_critical_rows=args.min_critical_rows,
        min_product_pass_pct=args.min_product_pass_pct,
        min_high_priority_pass_pct=args.min_high_priority_pass_pct,
        min_critical_pass_pct=args.min_critical_pass_pct,
        max_metadata_errors=args.max_metadata_errors,
        max_llm_owned_critical_rows=args.max_llm_owned_critical_rows,
        max_non_reviewed_critical_rows=args.max_non_reviewed_critical_rows,
        max_missing_visible_source_gap_rows=args.max_missing_visible_source_gap_rows,
    )
    prompt_rows = load_prompt_rows(args.prompts)
    eval_rows = load_eval_rows(args.eval_jsonl)
    scored = score_rows(eval_rows, prompt_rows)
    prompt_by_query = {normalize_query(row["query"]): row for row in prompt_rows.values()}
    metadata_errors = validate_prompt_metadata(prompt_rows.values())
    launch_failures = add_launch_failures(scored, prompt_by_query)
    metrics = summarize(scored)
    launch_metrics = summarize_launch(scored, prompt_rows.values(), metadata_errors)
    common_config = GateConfig(
        min_rows=config.min_rows,
        min_product_pass_pct=config.min_product_pass_pct,
        min_high_priority_pass_pct=config.min_high_priority_pass_pct,
        min_critical_rows=config.min_critical_rows,
        min_critical_priority_pass_pct=config.min_critical_pass_pct,
    )
    failures = evaluate_gate(metrics, common_config)
    failures.extend(evaluate_launch_gate(launch_metrics, config))
    if args.failures_jsonl:
        write_failures_jsonl(args.failures_jsonl, scored)
    if args.report:
        write_report(args.report, scored, metrics, launch_metrics, failures, args.eval_jsonl, args.prompts, config)

    print(f"Launch holdout gate: {'PASS' if not failures else 'FAIL'}")
    print(
        f"Rows: {metrics['rows']} product_pass={metrics['product_pass_count']}/{metrics['rows']} "
        f"({metrics['product_pass_pct']:.1f}%)"
    )
    print(
        f"Metadata errors: {launch_metrics['metadata_error_count']} "
        f"true_holdout_rows={launch_metrics['true_holdout_rows']}"
    )
    print(
        f"LLM-owned critical rows: {launch_metrics['llm_owned_critical_rows']} "
        f"non-reviewed critical rows={launch_metrics['non_reviewed_critical_rows']} "
        f"missing_visible_source_gap_rows={launch_metrics['missing_visible_source_gap_rows']} "
        f"visible_source_gap_rows={launch_metrics['visible_source_gap_rows']}"
    )
    for failure in failures:
        print(f"- {failure}")
    return 0 if args.allow_fail or not failures else 1


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("eval_jsonl", type=Path)
    parser.add_argument("--prompts", type=Path, required=True)
    parser.add_argument("--report", type=Path)
    parser.add_argument("--failures-jsonl", type=Path)
    parser.add_argument("--allow-fail", action="store_true")
    parser.add_argument("--min-rows", type=int, default=LaunchGateConfig.min_rows)
    parser.add_argument("--min-true-holdout-rows", type=int, default=LaunchGateConfig.min_true_holdout_rows)
    parser.add_argument("--min-critical-rows", type=int, default=LaunchGateConfig.min_critical_rows)
    parser.add_argument("--min-product-pass-pct", type=float, default=LaunchGateConfig.min_product_pass_pct)
    parser.add_argument("--min-high-priority-pass-pct", type=float, default=LaunchGateConfig.min_high_priority_pass_pct)
    parser.add_argument("--min-critical-pass-pct", type=float, default=LaunchGateConfig.min_critical_pass_pct)
    parser.add_argument("--max-metadata-errors", type=int, default=LaunchGateConfig.max_metadata_errors)
    parser.add_argument("--max-llm-owned-critical-rows", type=int, default=LaunchGateConfig.max_llm_owned_critical_rows)
    parser.add_argument(
        "--max-non-reviewed-critical-rows",
        type=int,
        default=LaunchGateConfig.max_non_reviewed_critical_rows,
    )
    parser.add_argument(
        "--max-missing-visible-source-gap-rows",
        type=int,
        default=LaunchGateConfig.max_missing_visible_source_gap_rows,
    )
    return parser.parse_args()


def validate_prompt_metadata(rows: Any) -> list[dict[str, str]]:
    errors: list[dict[str, str]] = []
    for row in rows:
        query = str(row.get("query") or "")
        row_id = str(row.get("id") or row.get("row_id") or row.get("base_id") or "").strip()
        _require(errors, query, row_id, "id_or_row_id", bool(row_id))
        _require(errors, query, row_id, "eval_split", bool(str(row.get("eval_split") or "").strip()))
        _require(errors, query, row_id, "label_source", bool(str(row.get("label_source") or "").strip()))
        priority = str(row.get("product_priority") or "").strip().lower()
        _require(errors, query, row_id, "product_priority", priority in PRIORITIES)
        _require(errors, query, row_id, "expected_route_any", bool(row.get("expected_route_any")))
        has_authority = bool(row.get("expected_controlling_source_any") or row.get("expected_act_hint"))
        has_gap_policy = str(row.get("expected_source_gap_policy") or row.get("source_gap_policy") or "").strip()
        _require(errors, query, row_id, "authority_or_source_gap_policy", has_authority or bool(has_gap_policy))
        has_must_terms = bool(row.get("must_include_any") or row.get("must_include_all"))
        _require(errors, query, row_id, "must_cover_terms", has_must_terms)
        if priority == "critical":
            _require(errors, query, row_id, "forbidden_framing_metadata", bool(row.get("forbidden_answer_any") or row.get("forbidden_route_any") or row.get("forbidden_workflow_id_any")))
    return errors


def add_launch_failures(rows: list[dict[str, Any]], prompts_by_query: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    failed: list[dict[str, Any]] = []
    for row in rows:
        failures = list(row.get("product_failures") or [])
        prompt = prompts_by_query.get(normalize_query(str(row.get("query") or ""))) or {}
        priority = str(row.get("product_priority") or "").lower()
        route = str(row.get("route_category") or "").lower()
        owner = str(row.get("workflow_answer_owner") or "").lower()
        mode = str(row.get("workflow_answer_mode") or "").lower()
        is_critical_route = priority == "critical" or route in CRITICAL_LAUNCH_ROUTES
        if is_critical_route and owner == "llm":
            failures.append("llm_owned_critical_route")
        if is_critical_route and not _is_reviewed_contract_owner(owner, mode):
            failures.append("non_reviewed_critical_route_owner")
        route_source_gap = bool(row.get("route_required_sources_missing"))
        safe_gap = bool(row.get("safe_source_gap"))
        if (route_source_gap or safe_gap or prompt_requires_source_gap(prompt)) and not row.get("source_gap_visible"):
            failures.append("source_gap_not_visible_to_user")
        if row.get("source_gap_visible"):
            failures.append("visible_source_gap")
        row["product_failures"] = list(dict.fromkeys(failures))
        row["product_pass"] = not row["product_failures"]
        failed.append(row)
    return failed


def summarize_launch(
    rows: list[dict[str, Any]],
    prompt_rows: Any,
    metadata_errors: list[dict[str, str]],
) -> dict[str, Any]:
    true_holdout_rows = [row for row in prompt_rows if is_true_holdout_prompt(row)]
    llm_owned_critical = [
        row for row in rows
        if "llm_owned_critical_route" in (row.get("product_failures") or [])
    ]
    non_reviewed_critical = [
        row for row in rows
        if "non_reviewed_critical_route_owner" in (row.get("product_failures") or [])
    ]
    missing_visible_gap = [
        row for row in rows
        if "source_gap_not_visible_to_user" in (row.get("product_failures") or [])
    ]
    visible_source_gap = [
        row for row in rows
        if "visible_source_gap" in (row.get("product_failures") or [])
    ]
    return {
        "metadata_error_count": len(metadata_errors),
        "metadata_errors": metadata_errors,
        "true_holdout_rows": len(true_holdout_rows),
        "llm_owned_critical_rows": len(llm_owned_critical),
        "non_reviewed_critical_rows": len(non_reviewed_critical),
        "missing_visible_source_gap_rows": len(missing_visible_gap),
        "visible_source_gap_rows": len(visible_source_gap),
        "launch_failure_counts": dict(Counter(
            failure
            for row in rows
            for failure in (row.get("product_failures") or [])
            if failure in {
                "llm_owned_critical_route",
                "non_reviewed_critical_route_owner",
                "source_gap_not_visible_to_user",
                "visible_source_gap",
            }
        )),
    }


def evaluate_launch_gate(metrics: dict[str, Any], config: LaunchGateConfig) -> list[str]:
    failures: list[str] = []
    if metrics["metadata_error_count"] > config.max_metadata_errors:
        failures.append(f"metadata_errors {metrics['metadata_error_count']} > {config.max_metadata_errors}")
    if metrics["true_holdout_rows"] < config.min_true_holdout_rows:
        failures.append(f"true_holdout_rows {metrics['true_holdout_rows']} < {config.min_true_holdout_rows}")
    if metrics["llm_owned_critical_rows"] > config.max_llm_owned_critical_rows:
        failures.append(f"llm_owned_critical_rows {metrics['llm_owned_critical_rows']} > {config.max_llm_owned_critical_rows}")
    if metrics["non_reviewed_critical_rows"] > config.max_non_reviewed_critical_rows:
        failures.append(
            f"non_reviewed_critical_rows {metrics['non_reviewed_critical_rows']} > "
            f"{config.max_non_reviewed_critical_rows}"
        )
    if metrics["missing_visible_source_gap_rows"] > config.max_missing_visible_source_gap_rows:
        failures.append(
            f"missing_visible_source_gap_rows {metrics['missing_visible_source_gap_rows']} > "
            f"{config.max_missing_visible_source_gap_rows}"
        )
    if metrics["visible_source_gap_rows"] > 0:
        failures.append(f"visible_source_gap_rows {metrics['visible_source_gap_rows']} > 0")
    return failures


def write_report(
    path: Path,
    rows: list[dict[str, Any]],
    metrics: dict[str, Any],
    launch_metrics: dict[str, Any],
    failures: list[str],
    eval_path: Path,
    prompts_path: Path,
    config: LaunchGateConfig,
) -> None:
    failed_rows = [row for row in rows if row.get("product_failures")]
    lines = [
        "# Launch Holdout Gate",
        "",
        f"Eval: `{eval_path}`",
        f"Prompts: `{prompts_path}`",
        f"Gate: **{'PASS' if not failures else 'FAIL'}**",
        "",
        "## Thresholds",
        "",
        "| threshold | value |",
        "| --- | ---: |",
        f"| min_rows | {config.min_rows} |",
        f"| min_true_holdout_rows | {config.min_true_holdout_rows} |",
        f"| min_critical_rows | {config.min_critical_rows} |",
        f"| min_product_pass_pct | {config.min_product_pass_pct:.1f}% |",
        f"| min_critical_pass_pct | {config.min_critical_pass_pct:.1f}% |",
        f"| max_visible_source_gap_rows | 0 |",
        "",
        "> If `true_holdout_rows` is 0, treat this as a diagnostic regression probe, not production launch-readiness evidence.",
        "",
        "## Metrics",
        "",
        "| metric | value |",
        "| --- | ---: |",
        f"| rows | {metrics['rows']} |",
        f"| product_pass | {metrics['product_pass_count']}/{metrics['rows']} ({metrics['product_pass_pct']:.1f}%) |",
        f"| high_priority_pass | {metrics['high_priority_pass_count']}/{metrics['high_priority_count']} ({metrics['high_priority_pass_pct']:.1f}%) |",
        f"| critical_priority_pass | {metrics['critical_priority_pass_count']}/{metrics['critical_priority_count']} ({metrics['critical_priority_pass_pct']:.1f}%) |",
        f"| expected_act_cited | {metrics['expected_act_cited_hits']}/{metrics['expected_act_cited_scored']} ({metrics['expected_act_cited_pct']:.1f}%) |",
        f"| safe_source_gaps | {metrics['safe_source_gaps']} |",
        f"| route_source_gap_rows | {metrics['route_source_gap_rows']} |",
        f"| metadata_errors | {launch_metrics['metadata_error_count']} |",
        f"| true_holdout_rows | {launch_metrics['true_holdout_rows']} |",
        f"| llm_owned_critical_rows | {launch_metrics['llm_owned_critical_rows']} |",
        f"| non_reviewed_critical_rows | {launch_metrics['non_reviewed_critical_rows']} |",
        f"| missing_visible_source_gap_rows | {launch_metrics['missing_visible_source_gap_rows']} |",
        f"| visible_source_gap_rows | {launch_metrics['visible_source_gap_rows']} |",
        "",
        "## Gate Failures",
        "",
    ]
    lines.extend(f"- {failure}" for failure in failures) if failures else lines.append("- none")
    lines.extend(["", "## Metadata Errors", "", "| row | field | query |", "| --- | --- | --- |"])
    for error in launch_metrics["metadata_errors"][:100]:
        lines.append(f"| {md(error['row_id'] or 'unknown')} | {md(error['field'])} | {md(error['query'], 120)} |")
    if not launch_metrics["metadata_errors"]:
        lines.append("| none | none | none |")
    lines.extend(["", "## Product Failure Samples", "", "| priority | route | failures | query | owner |", "| --- | --- | --- | --- | --- |"])
    for row in failed_rows[:100]:
        lines.append(
            "| "
            + " | ".join([
                md(str(row.get("product_priority") or "")),
                md(str(row.get("route_category") or "")),
                md(", ".join(row.get("product_failures") or []), 120),
                md(str(row.get("query") or ""), 120),
                md(str(row.get("workflow_answer_owner") or "")),
            ])
            + " |"
        )
    if not failed_rows:
        lines.append("| none | none | none | none | none |")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def prompt_requires_source_gap(prompt: dict[str, Any]) -> bool:
    policy = str(prompt.get("expected_source_gap_policy") or prompt.get("source_gap_policy") or "").lower()
    return policy in {
        "must_disclose_gap",
        "source_gap_required",
        "do_not_substitute_neighboring_authority",
    }


def is_true_holdout_prompt(prompt: dict[str, Any]) -> bool:
    split = str(prompt.get("eval_split") or "").lower()
    label_source = str(prompt.get("label_source") or "").lower()
    synthetic_note = str(prompt.get("synthetic_note") or "").lower()
    if "holdout" not in split:
        return False
    if label_source not in {"lawyer", "manual_independent", "human_legal_review"}:
        return False
    if "not a real user log" in synthetic_note or "synthetic" in synthetic_note:
        return False
    return True


def _is_reviewed_contract_owner(owner: str, mode: str) -> bool:
    return owner in {"authority_graph", "common_workflow_contracts"} and mode in {
        "primary",
        "safety_primary",
    }


def _require(errors: list[dict[str, str]], query: str, row_id: str, field: str, ok: bool) -> None:
    if ok:
        return
    errors.append({"query": query, "row_id": row_id, "field": field})


def normalize_query(query: str) -> str:
    import re

    return re.sub(r"\s+", " ", query.strip().lower())


if __name__ == "__main__":
    raise SystemExit(main())
