#!/usr/bin/env python3
"""Score timed eval output against the substance oracle.

This gate asks whether the answer body handles the exact user variant: the
controlling authority, forum, first step, discriminating facts, and safety
framing. It is designed to fail answers that look structurally polished but do
not solve the user's concrete legal problem.
"""
from __future__ import annotations

import argparse
import json
import math
import re
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from scripts.eval_common_user_gate import (
    load_eval_rows,
    load_prompt_rows,
    product_failures,
    route_matches,
)
from scripts.eval_timed_100 import expected_act_hit, expected_act_keys
from scripts.legal_safety_eval import analyze_safety_row


BAD_ROUTE_CATEGORIES = {"", "unknown", "general_legal", "off_topic"}


@dataclass(frozen=True)
class OracleConfig:
    min_rows: int = 150
    min_oracle_pass_pct: float = 95.0
    min_critical_pass_pct: float = 100.0
    max_safety_hard_fails: int = 0
    max_refusals: int = 0
    max_errors: int = 0
    max_p90_ms: float = 20_000.0


def main() -> int:
    args = parse_args()
    config = OracleConfig(
        min_rows=args.min_rows,
        min_oracle_pass_pct=args.min_oracle_pass_pct,
        min_critical_pass_pct=args.min_critical_pass_pct,
        max_p90_ms=args.max_p90_ms,
    )
    prompt_rows = load_prompt_rows(args.prompts)
    scored = score_rows(load_eval_rows(args.eval_jsonl), prompt_rows)
    metrics = summarize(scored)
    failures = evaluate_gate(metrics, config)
    if args.failures_jsonl:
        write_failures_jsonl(args.failures_jsonl, scored)
    if args.report:
        write_report(args.report, scored, metrics, failures, config, args.eval_jsonl, args.prompts)

    print(f"Substance oracle: {'PASS' if not failures else 'FAIL'}")
    print(f"Rows: {metrics['rows']} oracle_pass={metrics['oracle_pass_count']}/{metrics['rows']} ({metrics['oracle_pass_pct']:.1f}%)")
    print(
        f"Critical: {metrics['critical_pass_count']}/{metrics['critical_count']} "
        f"({metrics['critical_pass_pct']:.1f}%)"
    )
    print(f"Safety/errors/refusals: {metrics['safety_hard_fails']}/{metrics['errors']}/{metrics['refusals']}")
    print(f"p90={fmt_ms(metrics['p90_ms'])}")
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
    parser.add_argument("--min-rows", type=int, default=OracleConfig.min_rows)
    parser.add_argument("--min-oracle-pass-pct", type=float, default=OracleConfig.min_oracle_pass_pct)
    parser.add_argument("--min-critical-pass-pct", type=float, default=OracleConfig.min_critical_pass_pct)
    parser.add_argument("--max-p90-ms", type=float, default=OracleConfig.max_p90_ms)
    return parser.parse_args()


def score_rows(eval_rows: list[dict[str, Any]], prompt_rows: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    unmatched: list[str] = []
    for row in eval_rows:
        query = str(row.get("query") or "")
        prompt = prompt_rows.get(normalize_query(query))
        if prompt is None:
            unmatched.append(query)
            continue
        safety = analyze_safety_row(row)
        structural = product_failures(row, prompt, safety)
        oracle_failures = substance_failures(row, prompt, safety)
        route_category = str(row.get("route_category") or "").strip()
        expected_routes = adjusted_expected_routes(row, prompt)
        scored = {
            **row,
            "oracle_id": prompt.get("oracle_id"),
            "oracle_priority": prompt.get("oracle_priority") or prompt.get("product_priority"),
            "oracle_harm_bucket": prompt.get("oracle_harm_bucket"),
            "expected_route_any": expected_routes,
            "expected_primary_act_any": prompt.get("expected_primary_act_any") or row.get("expected_primary_act_any") or [],
            "route_match": route_matches(route_category, expected_routes),
            "structural_product_failures": structural,
            "oracle_failures": oracle_failures,
            "authority_key_status": authority_key_status(row),
            "primary_authority_status": primary_authority_status(row, prompt),
            "source_diagnoses": source_diagnoses(row, prompt, oracle_failures),
            "source_diagnosis": source_diagnosis(row, prompt, oracle_failures),
            "oracle_pass": not oracle_failures,
            "legal_safety": safety,
        }
        out.append(scored)
    if unmatched:
        sample = "; ".join(unmatched[:5])
        raise ValueError(f"{len(unmatched)} eval rows did not match prompt metadata; sample: {sample}")
    return out


def substance_failures(row: dict[str, Any], prompt: dict[str, Any], safety: dict[str, Any]) -> list[str]:
    failures: list[str] = []
    route_category = str(row.get("route_category") or "").strip()
    expected_routes = adjusted_expected_routes(row, prompt)
    oracle = prompt.get("oracle") or {}
    answer = answer_blob(row)

    if row.get("error"):
        failures.append("error")
    if row.get("refused"):
        failures.append("refused")
    if safety.get("hard_fail"):
        failures.append("legal_safety_hard_fail")
    if route_category.lower() in BAD_ROUTE_CATEGORIES:
        failures.append("bad_route_fallback")
    if expected_routes and not route_matches(route_category, expected_routes):
        failures.append("wrong_route")
    if str(row.get("relevance_verdict") or "").lower() != "ok":
        failures.append("relevance_not_ok")
    primary_status = primary_authority_status(row, prompt)
    if primary_status.get("cited_hit") is False:
        failures.append("primary_authority_not_cited")
    if row.get("first_cited_is_actionable") is False:
        failures.append("first_cited_not_actionable")
    if "zero_ok_legal_sentences" in (row.get("answer_quality_flags") or []):
        failures.append("zero_ok_legal_sentences")
    if "missing_next_step_section" in (row.get("answer_quality_flags") or []):
        failures.append("missing_next_step_section")

    for group in oracle.get("required_groups") or []:
        name = slug(str(group.get("name") or "required_group"))
        terms = [str(term) for term in group.get("any") or [] if str(term).strip()]
        if terms and not any(term_in_text(term, answer) for term in terms):
            failures.append(f"missing_{name}")

    for term in oracle.get("required_all") or []:
        if not term_in_text(str(term), answer):
            failures.append(f"missing_required_{slug(str(term))}")

    forbidden_hits = [str(term) for term in oracle.get("forbidden_any") or [] if forbidden_term_in_text(str(term), answer)]
    if forbidden_hits:
        failures.append("forbidden_framing")

    return list(dict.fromkeys(failures))


def adjusted_expected_routes(row: dict[str, Any], prompt: dict[str, Any]) -> list[str]:
    """Return expected routes with narrow variant-specific corrections.

    The witch-branding oracle scenario includes both victim-protection prompts
    and accused-side false-case prompts. Accused-side tonhi/witch false-case
    questions are safely routed through criminal-defence/bail, while victim
    violence remains police/tribal-caste.
    """
    routes = [str(item) for item in prompt.get("expected_route_any") or []]
    oracle_id = str(prompt.get("oracle_id") or row.get("oracle_id") or "")
    query = str(row.get("query") or "").lower()
    accused_false_case = (
        oracle_id == "witch_branding_tonhi"
        and any(term in query for term in ("false case", "accused", "against me", "they say i am", "police called me"))
    )
    if accused_false_case and "criminal_defence_bail" not in routes:
        routes.append("criminal_defence_bail")
    return routes


def source_diagnosis(row: dict[str, Any], prompt: dict[str, Any] | list[str] | None = None, oracle_failures: list[str] | None = None) -> str:
    if isinstance(prompt, list) and oracle_failures is None:
        oracle_failures = prompt
        prompt = None
    diagnoses = source_diagnoses(row, prompt if isinstance(prompt, dict) else {}, oracle_failures or [])
    return diagnoses[0] if diagnoses else "ok"


def source_diagnoses(row: dict[str, Any], prompt: dict[str, Any], oracle_failures: list[str]) -> list[str]:
    diagnoses: list[str] = []
    primary = primary_authority_status(row, prompt)
    if primary.get("retrieved_hit") is False:
        key_statuses = authority_key_status(row)
        if any(status.get("present_in_retrieved_sources") for status in key_statuses.values()):
            diagnoses.append("partial_retrieval_or_corpus_gap")
        else:
            diagnoses.append("retrieval_or_corpus_gap")
    if primary.get("retrieved_hit") is True and primary.get("cited_hit") is False:
        diagnoses.append("retrieved_not_cited")
    if any(failure.startswith("missing_") for failure in oracle_failures):
        diagnoses.append("answer_contract_gap")
    if "first_cited_not_actionable" in oracle_failures:
        diagnoses.append("wrong_anchor_or_actionability_gap")
    quality_failures = {
        "error",
        "refused",
        "legal_safety_hard_fail",
        "bad_route_fallback",
        "wrong_route",
        "relevance_not_ok",
        "zero_ok_legal_sentences",
        "forbidden_framing",
    }
    if quality_failures.intersection(oracle_failures):
        diagnoses.append("quality_or_safety_gap")
    return list(dict.fromkeys(diagnoses)) or ["ok"]


def primary_authority_status(row: dict[str, Any], prompt: dict[str, Any]) -> dict[str, Any]:
    candidates = primary_authority_candidates(row, prompt)
    if not candidates:
        return {"candidates": [], "retrieved_hit": row.get("expected_act_hit"), "cited_hit": row.get("expected_act_cited_hit")}

    retrieved_sources = authority_source_items(row)
    cited_sources = cited_authority_source_items(row)
    candidate_statuses: list[dict[str, Any]] = []
    for hint, keys in candidates:
        candidate_statuses.append({
            "hint": hint,
            "keys": keys,
            "retrieved_hit": expected_act_hit(keys, retrieved_sources, []) if keys else None,
            "cited_hit": expected_act_hit(keys, cited_sources, []) if keys else None,
        })
    retrieved_values = [item["retrieved_hit"] for item in candidate_statuses if item["retrieved_hit"] is not None]
    cited_values = [item["cited_hit"] for item in candidate_statuses if item["cited_hit"] is not None]
    return {
        "candidates": candidate_statuses,
        "retrieved_hit": any(retrieved_values) if retrieved_values else row.get("expected_act_hit"),
        "cited_hit": any(cited_values) if cited_values else row.get("expected_act_cited_hit"),
    }


def primary_authority_candidates(row: dict[str, Any], prompt: dict[str, Any]) -> list[tuple[str, list[str]]]:
    raw_hints = prompt.get("expected_primary_act_any") or row.get("expected_primary_act_any") or []
    if isinstance(raw_hints, str):
        raw_hints = [raw_hints]
    query = str(row.get("query") or "")
    candidates: list[tuple[str, list[str]]] = []
    for hint in raw_hints:
        hint_text = str(hint).strip()
        if not hint_text:
            continue
        keys = expected_act_keys(hint_text, query)
        if keys:
            candidates.append((hint_text, keys))
    return candidates


def authority_key_status(row: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Best-effort per-authority visibility from flattened timed rows.

    The timed JSONL currently preserves only the top source metadata, not the
    full passage list or sentence-to-source map. This status is still useful:
    it tells us whether an aggregate `expected_act_hit=False` row had at least
    some expected authority family in the visible source set.
    """
    keys = [str(key) for key in row.get("expected_act_keys") or [] if str(key).strip()]
    sources = authority_source_items(row)
    out: dict[str, dict[str, Any]] = {}
    for key in keys:
        out[key] = {
            "present_in_top_sources": expected_act_hit([key], [source for source in row.get("top_sources") or [] if isinstance(source, dict)], []) is True,
            "present_in_retrieved_sources": expected_act_hit([key], sources, []) is True,
        }
    return out


def authority_source_items(row: dict[str, Any]) -> list[dict[str, Any]]:
    sources = row.get("retrieved_sources") or row.get("top_sources") or []
    return [source for source in sources if isinstance(source, dict)]


def cited_authority_source_items(row: dict[str, Any]) -> list[dict[str, Any]]:
    sources = row.get("cited_sources") or []
    if not sources:
        if row.get("expected_act_cited_hit") is True:
            return authority_source_items(row)
        return []
    return [source for source in sources if isinstance(source, dict)]


def summarize(rows: list[dict[str, Any]]) -> dict[str, Any]:
    total = len(rows)
    critical = [row for row in rows if str(row.get("oracle_priority") or "").lower() == "critical"]
    wall = [float(row["wall_ms"]) for row in rows if is_number(row.get("wall_ms"))]
    failure_counts: Counter[str] = Counter()
    issue_counts: Counter[str] = Counter()
    harm_counts: Counter[str] = Counter()
    source_counts: Counter[str] = Counter()
    for row in rows:
        for failure in row.get("oracle_failures") or []:
            failure_counts[failure] += 1
        if row.get("oracle_failures"):
            issue_counts[str(row.get("oracle_id") or "unknown")] += 1
        harm_counts[str(row.get("oracle_harm_bucket") or "unknown")] += 1
        for diagnosis in row.get("source_diagnoses") or [row.get("source_diagnosis") or "unknown"]:
            source_counts[str(diagnosis)] += 1
    return {
        "rows": total,
        "oracle_pass_count": sum(1 for row in rows if row.get("oracle_pass")),
        "oracle_pass_pct": pct(sum(1 for row in rows if row.get("oracle_pass")), total),
        "critical_count": len(critical),
        "critical_pass_count": sum(1 for row in critical if row.get("oracle_pass")),
        "critical_pass_pct": pct(sum(1 for row in critical if row.get("oracle_pass")), len(critical)) if critical else 100.0,
        "errors": sum(1 for row in rows if row.get("error")),
        "refusals": sum(1 for row in rows if row.get("refused")),
        "safety_hard_fails": sum(1 for row in rows if (row.get("legal_safety") or {}).get("hard_fail")),
        "p50_ms": percentile(wall, 0.50),
        "p90_ms": percentile(wall, 0.90),
        "failure_counts": dict(failure_counts),
        "issue_failure_counts": dict(issue_counts),
        "harm_counts": dict(harm_counts),
        "source_diagnosis_counts": dict(source_counts),
    }


def evaluate_gate(metrics: dict[str, Any], config: OracleConfig) -> list[str]:
    failures: list[str] = []
    check_min(failures, "rows", metrics["rows"], config.min_rows)
    check_min(failures, "oracle_pass_pct", metrics["oracle_pass_pct"], config.min_oracle_pass_pct)
    check_min(failures, "critical_pass_pct", metrics["critical_pass_pct"], config.min_critical_pass_pct)
    check_max(failures, "safety_hard_fails", metrics["safety_hard_fails"], config.max_safety_hard_fails)
    check_max(failures, "errors", metrics["errors"], config.max_errors)
    check_max(failures, "refusals", metrics["refusals"], config.max_refusals)
    check_max(failures, "p90_ms", metrics["p90_ms"], config.max_p90_ms)
    return failures


def write_failures_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for row in rows:
            if not row.get("oracle_failures"):
                continue
            slim = {
                "query": row.get("query"),
                "oracle_id": row.get("oracle_id"),
                "oracle_priority": row.get("oracle_priority"),
                "oracle_harm_bucket": row.get("oracle_harm_bucket"),
                "route_category": row.get("route_category"),
                "expected_route_any": row.get("expected_route_any"),
                "expected_act_hint": row.get("expected_act_hint"),
                "expected_primary_act_any": row.get("expected_primary_act_any"),
                "expected_act_hit": row.get("expected_act_hit"),
                "expected_act_cited_hit": row.get("expected_act_cited_hit"),
                "primary_authority_status": row.get("primary_authority_status"),
                "source_diagnosis": row.get("source_diagnosis"),
                "source_diagnoses": row.get("source_diagnoses"),
                "authority_key_status": row.get("authority_key_status"),
                "oracle_failures": row.get("oracle_failures"),
                "structural_product_failures": row.get("structural_product_failures"),
                "answer_quality_flags": row.get("answer_quality_flags"),
                "answer_text": row.get("answer_text"),
                "top_sources": row.get("top_sources"),
                "cited_sources": row.get("cited_sources"),
                "wall_ms": row.get("wall_ms"),
            }
            f.write(json.dumps(slim, ensure_ascii=False) + "\n")


def write_report(
    path: Path,
    rows: list[dict[str, Any]],
    metrics: dict[str, Any],
    gate_failures: list[str],
    config: OracleConfig,
    eval_path: Path,
    prompts_path: Path,
) -> None:
    failed = [row for row in rows if row.get("oracle_failures")]
    lines = [
        "# Substance Oracle Gate",
        "",
        f"Eval: `{eval_path}`",
        f"Prompts: `{prompts_path}`",
        f"Gate: **{'PASS' if not gate_failures else 'FAIL'}**",
        "",
        "## Gate Metrics",
        "",
        "| metric | value | target |",
        "| --- | ---: | ---: |",
        f"| rows | {metrics['rows']} | >= {config.min_rows} |",
        f"| oracle_pass | {metrics['oracle_pass_count']}/{metrics['rows']} ({metrics['oracle_pass_pct']:.1f}%) | >= {config.min_oracle_pass_pct:.1f}% |",
        f"| critical_pass | {metrics['critical_pass_count']}/{metrics['critical_count']} ({metrics['critical_pass_pct']:.1f}%) | >= {config.min_critical_pass_pct:.1f}% |",
        f"| safety_hard_fails | {metrics['safety_hard_fails']} | <= {config.max_safety_hard_fails} |",
        f"| errors | {metrics['errors']} | <= {config.max_errors} |",
        f"| refusals | {metrics['refusals']} | <= {config.max_refusals} |",
        f"| p50_latency | {fmt_ms(metrics['p50_ms'])} | n/a |",
        f"| p90_latency | {fmt_ms(metrics['p90_ms'])} | <= {fmt_ms(config.max_p90_ms)} |",
        "",
        "## Failure Counts",
        "",
        "| failure | count |",
        "| --- | ---: |",
    ]
    append_counts(lines, metrics["failure_counts"])
    lines.extend(["", "## Source Diagnosis", "", "| diagnosis | count |", "| --- | ---: |"])
    append_counts(lines, metrics["source_diagnosis_counts"])
    lines.extend(["", "## Failed Oracle Issues", "", "| issue | failures |", "| --- | ---: |"])
    append_counts(lines, metrics["issue_failure_counts"], limit=40)
    lines.extend(["", "## Harm Buckets", "", "| bucket | rows |", "| --- | ---: |"])
    append_counts(lines, metrics["harm_counts"], limit=20)
    if gate_failures:
        lines.extend(["", "## Gate Failures", ""])
        lines.extend(f"- {failure}" for failure in gate_failures)
    lines.extend([
        "",
        "## Failure Samples",
        "",
        "| issue | route | diagnosis | failures | query | answer excerpt |",
        "| --- | --- | --- | --- | --- | --- |",
    ])
    for row in failed[:100]:
        lines.append(
            "| "
            + " | ".join(
                [
                    md(row.get("oracle_id")),
                    md(row.get("route_category")),
                    md(", ".join(row.get("source_diagnoses") or [row.get("source_diagnosis") or "unknown"])),
                    md(", ".join(row.get("oracle_failures") or []), 120),
                    md(row.get("query"), 100),
                    md(row.get("answer_text"), 180),
                ]
            )
            + " |"
        )
    if not failed:
        lines.append("| none | n/a | n/a | n/a | n/a | n/a |")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def append_counts(lines: list[str], counts: dict[str, Any], *, limit: int | None = None) -> None:
    counter = Counter(counts)
    items = counter.most_common(limit)
    if items:
        for key, count in items:
            lines.append(f"| {md(key)} | {count} |")
    else:
        lines.append("| none | 0 |")


def answer_blob(row: dict[str, Any]) -> str:
    return normalize_text(str(row.get("answer_text") or ""))


def normalize_text(text: str) -> str:
    text = text.lower()
    text = text.replace("–", "-").replace("—", "-")
    return re.sub(r"\s+", " ", text)


def term_in_text(term: str, text: str) -> bool:
    term = normalize_text(term).strip()
    if not term:
        return False
    pattern = re.escape(term)
    pattern = pattern.replace(r"\ ", r"[\W_]+")
    pattern = pattern.replace(r"\-", r"[-\W_]*")
    return re.search(rf"(?<![a-z0-9]){pattern}(?![a-z0-9])", text) is not None


def forbidden_term_in_text(term: str, text: str) -> bool:
    term = normalize_text(term).strip()
    if not term:
        return False
    pattern = re.escape(term)
    pattern = pattern.replace(r"\ ", r"[\W_]+")
    pattern = pattern.replace(r"\-", r"[-\W_]*")
    for match in re.finditer(rf"(?<![a-z0-9]){pattern}(?![a-z0-9])", text):
        before = text[max(0, match.start() - 64):match.start()]
        if re.search(
            r"(?:cannot|can not|can't|cant|do not|don't|dont|must not|should not|not|never|no)\W+(?:\w+\W+){0,4}$",
            before,
        ):
            continue
        return True
    return False


def normalize_query(query: str) -> str:
    return " ".join(str(query).lower().split())


def slug(value: str) -> str:
    value = re.sub(r"[^a-z0-9]+", "_", value.lower()).strip("_")
    return value or "term"


def is_number(value: object) -> bool:
    return isinstance(value, int | float) and not math.isnan(float(value))


def percentile(values: list[float], pct_value: float) -> float | None:
    vals = sorted(values)
    if not vals:
        return None
    if len(vals) == 1:
        return vals[0]
    idx = (len(vals) - 1) * pct_value
    lo = int(idx)
    hi = min(lo + 1, len(vals) - 1)
    frac = idx - lo
    return vals[lo] * (1 - frac) + vals[hi] * frac


def pct(num: int, den: int) -> float:
    return (num / den * 100.0) if den else 0.0


def check_min(failures: list[str], name: str, actual: Any, expected: float) -> None:
    if actual is None or float(actual) < expected:
        failures.append(f"{name} {actual} < {expected}")


def check_max(failures: list[str], name: str, actual: Any, expected: float) -> None:
    if actual is None:
        return
    if float(actual) > expected:
        failures.append(f"{name} {actual} > {expected}")


def fmt_ms(value: float | None) -> str:
    if value is None:
        return "n/a"
    return f"{value / 1000:.1f}s"


def md(value: object, limit: int = 80) -> str:
    text = "" if value is None else str(value)
    text = re.sub(r"\s+", " ", text).replace("|", " ").strip()
    if len(text) > limit:
        text = text[: limit - 1].rstrip() + "…"
    return text


if __name__ == "__main__":
    raise SystemExit(main())
