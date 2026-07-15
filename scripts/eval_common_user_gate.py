#!/usr/bin/env python3
"""Prompt-specific product gate for the common-user legal QA suite.

The timed eval already measures broad retrieval and latency. This gate asks a
stricter product question: did the answer help the kind of user who typed this
prompt? It joins timed eval rows to prompt metadata and checks route, cited
authority, actionability, next steps, and scenario-specific must-mention terms.
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

from scripts.eval_source_gaps import (
    expected_authority_gap_kind,
    has_unclassified_route_source_gap,
    route_required_source_gap_classifications,
)
from scripts.legal_safety_eval import analyze_safety_row


BAD_ROUTE_CATEGORIES = {"", "unknown", "general_legal", "off_topic"}
LLM_PATH_THRESHOLD_MS = 1_000.0


@dataclass(frozen=True)
class GateConfig:
    min_rows: int = 200
    min_product_pass_pct: float = 95.0
    min_high_priority_pass_pct: float = 95.0
    min_critical_rows: int = 30
    min_critical_priority_pass_pct: float = 100.0
    min_route_match_pct: float = 95.0
    min_expected_act_cited_pct: float = 93.5
    min_first_actionable_pct: float = 95.0
    min_must_terms_pct: float = 95.0
    min_wall_latency_coverage_pct: float = 100.0
    min_timing_telemetry_pct: float = 95.0
    max_errors: int = 0
    max_refusals: int = 0
    max_bad_route_fallbacks: int = 0
    max_safety_hard_fails: int = 0
    max_p50_ms: float = 10_000.0
    max_p90_ms: float = 20_000.0
    max_llm_path_p90_ms: float = 20_000.0
    max_safe_source_gaps: int = 0
    max_route_source_gap_rows: int = 0
    max_unclassified_route_source_gap_rows: int = 0


def main() -> int:
    args = parse_args()
    config = GateConfig(
        min_rows=args.min_rows,
        min_product_pass_pct=args.min_product_pass_pct,
        min_high_priority_pass_pct=args.min_high_priority_pass_pct,
        min_critical_rows=args.min_critical_rows,
        min_critical_priority_pass_pct=args.min_critical_priority_pass_pct,
        min_route_match_pct=args.min_route_match_pct,
        min_expected_act_cited_pct=args.min_expected_act_cited_pct,
        min_first_actionable_pct=args.min_first_actionable_pct,
        min_must_terms_pct=args.min_must_terms_pct,
        min_wall_latency_coverage_pct=args.min_wall_latency_coverage_pct,
        min_timing_telemetry_pct=args.min_timing_telemetry_pct,
        max_errors=args.max_errors,
        max_refusals=args.max_refusals,
        max_bad_route_fallbacks=args.max_bad_route_fallbacks,
        max_safety_hard_fails=args.max_safety_hard_fails,
        max_p50_ms=args.max_p50_ms,
        max_p90_ms=args.max_p90_ms,
        max_llm_path_p90_ms=args.max_llm_path_p90_ms,
        max_safe_source_gaps=args.max_safe_source_gaps,
        max_route_source_gap_rows=args.max_route_source_gap_rows,
        max_unclassified_route_source_gap_rows=args.max_unclassified_route_source_gap_rows,
    )
    prompt_rows = load_prompt_rows(args.prompts)
    eval_rows = load_eval_rows(args.eval_jsonl)
    scored = score_rows(eval_rows, prompt_rows)
    metrics = summarize(scored)
    failures = evaluate_gate(metrics, config)
    if args.failures_jsonl:
        write_failures_jsonl(args.failures_jsonl, scored)
    if args.report:
        write_report(args.report, scored, metrics, failures, config, args.eval_jsonl, args.prompts)

    print(f"Common-user gate: {'PASS' if not failures else 'FAIL'}")
    print(f"Rows: {metrics['rows']} product_pass={metrics['product_pass_count']}/{metrics['rows']} ({metrics['product_pass_pct']:.1f}%)")
    print(f"Route match: {metrics['route_match_count']}/{metrics['rows']} ({metrics['route_match_pct']:.1f}%)")
    print(f"Expected Act cited: {metrics['expected_act_cited_hits']}/{metrics['expected_act_cited_scored']} ({metrics['expected_act_cited_pct']:.1f}%)")
    print(
        f"Telemetry: wall={metrics['wall_latency_count']}/{metrics['rows']} "
        f"timing={metrics['timing_telemetry_count']}/{metrics['rows']}"
    )
    print(
        f"p50={fmt_ms(metrics['p50_ms'])} p90={fmt_ms(metrics['p90_ms'])} "
        f"llm_path_p90={fmt_ms(metrics['llm_path_p90_ms'])}"
    )
    print(
        f"Source gaps: safe={metrics['safe_source_gaps']} "
        f"visible={metrics['visible_source_gap_rows']} "
        f"route_rows={metrics['route_source_gap_rows']} "
        f"unclassified_route_rows={metrics['unclassified_route_source_gap_rows']}"
    )
    for failure in failures:
        print(f"- {failure}")
    return 0 if args.allow_fail or not failures else 1


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("eval_jsonl", type=Path, help="Timed eval JSONL from scripts/eval_timed_100.py")
    parser.add_argument(
        "--prompts",
        type=Path,
        required=True,
        help="Prompt JSONL file or directory used to run the common-user eval",
    )
    parser.add_argument("--report", type=Path)
    parser.add_argument("--failures-jsonl", type=Path)
    parser.add_argument("--allow-fail", action="store_true")
    parser.add_argument("--min-rows", type=int, default=GateConfig.min_rows)
    parser.add_argument("--min-product-pass-pct", type=float, default=GateConfig.min_product_pass_pct)
    parser.add_argument("--min-high-priority-pass-pct", type=float, default=GateConfig.min_high_priority_pass_pct)
    parser.add_argument("--min-critical-rows", type=int, default=GateConfig.min_critical_rows)
    parser.add_argument("--min-critical-priority-pass-pct", type=float, default=GateConfig.min_critical_priority_pass_pct)
    parser.add_argument("--min-route-match-pct", type=float, default=GateConfig.min_route_match_pct)
    parser.add_argument("--min-expected-act-cited-pct", type=float, default=GateConfig.min_expected_act_cited_pct)
    parser.add_argument("--min-first-actionable-pct", type=float, default=GateConfig.min_first_actionable_pct)
    parser.add_argument("--min-must-terms-pct", type=float, default=GateConfig.min_must_terms_pct)
    parser.add_argument("--min-wall-latency-coverage-pct", type=float, default=GateConfig.min_wall_latency_coverage_pct)
    parser.add_argument("--min-timing-telemetry-pct", type=float, default=GateConfig.min_timing_telemetry_pct)
    parser.add_argument("--max-errors", type=int, default=GateConfig.max_errors)
    parser.add_argument("--max-refusals", type=int, default=GateConfig.max_refusals)
    parser.add_argument("--max-bad-route-fallbacks", type=int, default=GateConfig.max_bad_route_fallbacks)
    parser.add_argument("--max-safety-hard-fails", type=int, default=GateConfig.max_safety_hard_fails)
    parser.add_argument("--max-p50-ms", type=float, default=GateConfig.max_p50_ms)
    parser.add_argument("--max-p90-ms", type=float, default=GateConfig.max_p90_ms)
    parser.add_argument("--max-llm-path-p90-ms", type=float, default=GateConfig.max_llm_path_p90_ms)
    parser.add_argument("--max-safe-source-gaps", type=int, default=GateConfig.max_safe_source_gaps)
    parser.add_argument("--max-route-source-gap-rows", type=int, default=GateConfig.max_route_source_gap_rows)
    parser.add_argument(
        "--max-unclassified-route-source-gap-rows",
        type=int,
        default=GateConfig.max_unclassified_route_source_gap_rows,
    )
    return parser.parse_args()


def load_prompt_rows(path: Path) -> dict[str, dict[str, Any]]:
    files = sorted(path.glob("*.jsonl")) if path.is_dir() else [path]
    by_query: dict[str, dict[str, Any]] = {}
    for file in files:
        for line_no, line in enumerate(file.read_text(encoding="utf-8").split("\n"), start=1):
            if not line.strip():
                continue
            row = json.loads(line)
            query = str(row.get("query") or "").strip()
            if not query:
                raise ValueError(f"{file}:{line_no}: missing query")
            key = normalize_query(query)
            if key in by_query:
                raise ValueError(f"{file}:{line_no}: duplicate prompt query: {query}")
            by_query[key] = row
    if not by_query:
        raise ValueError(f"no prompt rows found under {path}")
    return by_query


def load_eval_rows(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for line_no, line in enumerate(path.read_text(encoding="utf-8").split("\n"), start=1):
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ValueError(f"{path}:{line_no}: invalid JSON: {exc}") from exc
        rows.append(row)
    if not rows:
        raise ValueError(f"no eval rows found in {path}")
    return rows


def score_rows(eval_rows: list[dict[str, Any]], prompt_rows: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    unmatched: list[str] = []
    for row in eval_rows:
        query = str(row.get("query") or "")
        prompt = prompt_rows.get(normalize_query(query))
        if prompt is None:
            unmatched.append(query)
            prompt = {}
        safety = analyze_safety_row(row)
        source_gap_ok = safe_source_gap_ok(row, prompt)
        source_gap_kind = expected_authority_gap_kind(row, prompt) if source_gap_ok else None
        route_gap_classes = route_required_source_gap_classifications(row)
        failures = product_failures(row, prompt, safety)
        route_category = str(row.get("route_category") or "").strip()
        expected_routes = [str(item) for item in prompt.get("expected_route_any") or []]
        scored = {
            **row,
            "common_issue": prompt.get("common_issue"),
            "product_priority": prompt.get("product_priority"),
            "expected_route_any": expected_routes,
            "forbidden_route_any": prompt.get("forbidden_route_any") or [],
            "required_workflow_id_any": prompt.get("required_workflow_id_any") or [],
            "forbidden_workflow_id_any": prompt.get("forbidden_workflow_id_any") or [],
            "required_answer_owner_any": prompt.get("required_answer_owner_any") or [],
            "forbidden_answer_any": prompt.get("forbidden_answer_any") or [],
            "forbidden_first_cited_source_type_any": prompt.get("forbidden_first_cited_source_type_any") or [],
            "forbidden_first_cited_title_any": prompt.get("forbidden_first_cited_title_any") or [],
            "must_include_any": prompt.get("must_include_any") or [],
            "must_include_all": prompt.get("must_include_all") or [],
            "route_match": route_matches(route_category, expected_routes),
            "bad_route_fallback": route_category.lower() in BAD_ROUTE_CATEGORIES,
            "must_terms_ok": must_terms_ok(row, prompt),
            "safe_source_gap": source_gap_ok,
            "safe_source_gap_kind": source_gap_kind,
            "route_required_source_gap_classifications": route_gap_classes,
            "route_required_source_gap_kinds": [item["kind"] for item in route_gap_classes],
            "has_unclassified_route_source_gap": has_unclassified_route_source_gap({
                **row,
                "route_required_source_gap_classifications": route_gap_classes,
            }),
            "product_failures": failures,
            "product_pass": not failures,
            "legal_safety": safety,
        }
        out.append(scored)
    if unmatched:
        sample = "; ".join(unmatched[:5])
        raise ValueError(f"{len(unmatched)} eval rows did not match prompt metadata; sample: {sample}")
    return out


def product_failures(row: dict[str, Any], prompt: dict[str, Any], safety: dict[str, Any]) -> list[str]:
    failures: list[str] = []
    route_category = str(row.get("route_category") or "").strip()
    expected_routes = [str(item) for item in prompt.get("expected_route_any") or []]
    source_gap_ok = safe_source_gap_ok(row, prompt)

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
    forbidden_routes = normalized_prompt_terms(prompt, "forbidden_route_any")
    if forbidden_routes and route_category.strip().lower() in forbidden_routes:
        failures.append("forbidden_route")
    if str(row.get("relevance_verdict") or "").lower() != "ok":
        failures.append("relevance_not_ok")
    if _int(row.get("source_count")) <= 0:
        failures.append("no_sources")
    if row.get("expected_act_hit") is False and not source_gap_ok:
        failures.append("expected_act_missing")
    if row.get("expected_act_cited_hit") is False and not source_gap_ok:
        failures.append("expected_act_not_cited")
    if row.get("route_required_sources_missing"):
        failures.append("route_required_source_gap")
    if row.get("source_gap_visible"):
        failures.append("visible_source_gap")
    if row.get("first_cited_is_actionable") is False:
        failures.append("first_cited_not_actionable")
    if row.get("judgment_before_actionable_source") is True:
        failures.append("judgment_before_actionable_source")
    if not _has_meaningful_action_pack(row):
        failures.append("missing_action_pack")
    if "missing_next_step_section" in (row.get("answer_quality_flags") or []):
        failures.append("missing_next_step_section")
    if "zero_ok_legal_sentences" in (row.get("answer_quality_flags") or []):
        failures.append("zero_ok_legal_sentences")
    if _int(row.get("unknown_citation_count")) > 0 or "unknown_citation_indices" in (row.get("answer_quality_flags") or []):
        failures.append("unknown_citation_indices")
    if _int(row.get("suppressed_count")) > 0:
        failures.append("suppressed_sentences")
    if not must_terms_ok(row, prompt):
        failures.append("missing_scenario_terms")
    required_workflows = normalized_prompt_terms(prompt, "required_workflow_id_any")
    workflow_id = str(row.get("workflow_id") or "").strip().lower()
    if required_workflows and workflow_id not in required_workflows:
        failures.append("wrong_workflow")
    forbidden_workflows = normalized_prompt_terms(prompt, "forbidden_workflow_id_any")
    if workflow_id and workflow_id in forbidden_workflows:
        failures.append("forbidden_workflow")
    required_owners = normalized_prompt_terms(prompt, "required_answer_owner_any")
    answer_owner = str(row.get("workflow_answer_owner") or "").strip().lower()
    if required_owners and answer_owner not in required_owners:
        failures.append("wrong_answer_owner")
    forbidden_answer_terms = normalized_prompt_terms(prompt, "forbidden_answer_any")
    answer_blob = answer_searchable_blob(row)
    if forbidden_answer_terms and any(term in answer_blob for term in forbidden_answer_terms):
        failures.append("forbidden_answer_term")
    forbidden_first_source_types = normalized_prompt_terms(prompt, "forbidden_first_cited_source_type_any")
    first_type = str(row.get("first_cited_source_type") or "").strip().lower()
    if first_type and first_type in forbidden_first_source_types:
        failures.append("forbidden_first_cited_source_type")
    forbidden_first_titles = normalized_prompt_terms(prompt, "forbidden_first_cited_title_any")
    first_title = str(row.get("first_cited_source_title") or "").strip().lower()
    if first_title and any(term in first_title for term in forbidden_first_titles):
        failures.append("forbidden_first_cited_title")
    return list(dict.fromkeys(failures))


def safe_source_gap_ok(row: dict[str, Any], prompt: dict[str, Any]) -> bool:
    """Accept an explicit source-gap answer when the exact authority is absent.

    This is deliberately narrow: the answer must name the missing source class,
    say it is absent from the retrieved index/sources, and refuse to substitute
    adjacent law. It still needs real citations for the safe procedural/offence
    track, actionable first source behavior, and no judgment-first shortcut.
    """
    if row.get("expected_act_hit") is not False and row.get("expected_act_cited_hit") is not False:
        return False
    if _int(row.get("source_count")) <= 0:
        return False
    if row.get("first_cited_is_actionable") is False:
        return False
    if row.get("judgment_before_actionable_source") is True:
        return False

    answer = answer_searchable_blob(row)
    expected_hint = str(row.get("expected_act_hint") or prompt.get("expected_act_hint") or "").lower()
    query = str(row.get("query") or "").lower()

    has_gap_language = (
        "source in the retrieved index" in answer
        or "source in the retrieved sources" in answer
        or "not in the retrieved index" in answer
        or "not in the retrieved sources" in answer
    )
    refuses_substitution = (
        "will not cite an adjacent" in answer
        or "do not treat" in answer and "controlling state act" in answer
        or "does not replace the missing" in answer
        or "not treat" in answer and "as controlling" in answer
    )
    if not (has_gap_language and refuses_substitution):
        return False

    constitutional_article_gap = (
        ("article 226" in expected_hint or "art.226" in expected_hint or "article 226" in answer)
        and str(row.get("route_category") or "").lower() in {"environment_compensation", "court_procedure"}
        and "article 226" in answer
        and ("constitution passage" in answer or "high court pil source" in answer)
    )
    if constitutional_article_gap:
        return True

    state_or_local_gap = (
        "witch-hunting state acts" in expected_hint
        or "tonahi" in expected_hint
        or "tonhi" in expected_hint
        or "witch practices" in expected_hint
        or "witch (daain)" in expected_hint
        or "cattle preservation" in expected_hint
        or "animal preservation" in expected_hint
        or "state cattle" in expected_hint
        or "scheduled areas land transfer" in expected_hint
        or "state scheduled areas" in expected_hint
        or "scheduled area land-transfer" in answer
        or "begging act" in expected_hint
        or "begging-law" in answer
        or "chhattisgarh tonahi" in answer
        or "jharkhand witch" in answer
        or "ap scheduled areas land transfer" in answer
        or "state cattle preservation" in answer
        or "state excise act" in expected_hint
        or "state excise" in answer
        or "maharashtra state excise" in answer
        or "local bhang-rule" in answer
        or "delhi begging-law" in answer
    )
    if not state_or_local_gap:
        return False

    high_risk_route = str(row.get("route_category") or "").lower() in {
        "criminal_defence_bail",
        "criminal_general",
        "police_fir",
        "tribal_caste_atrocity",
    }
    high_risk_query = any(term in query for term in (
        "tonhi", "witch", "daayan", "dayan", "labour chowk", "begging",
        "cow", "cattle", "buffalo", "smuggling", "mandi",
        "tribal land", "agency area", "non tribal", "non adivasi", "patwari",
        "bhang", "bhang lassi",
    ))
    return high_risk_route and high_risk_query


def route_matches(route_category: str, expected_routes: list[str]) -> bool:
    if not expected_routes:
        return route_category.lower() not in BAD_ROUTE_CATEGORIES
    route = route_category.strip().lower()
    return route in {item.strip().lower() for item in expected_routes}


def must_terms_ok(row: dict[str, Any], prompt: dict[str, Any]) -> bool:
    blob = answer_searchable_blob(row)
    must_all = sorted(normalized_must_terms(prompt, "must_include_all"))
    must_any = sorted(normalized_must_terms(prompt, "must_include_any"))
    if any(term not in blob for term in must_all):
        return False
    if must_any and not any(term in blob for term in must_any):
        return False
    return True


def normalized_prompt_terms(prompt: dict[str, Any], key: str) -> set[str]:
    return {
        str(term).strip().lower()
        for term in (prompt.get(key) or [])
        if str(term).strip()
    }


def normalized_must_terms(prompt: dict[str, Any], key: str) -> set[str]:
    return {
        _term_search_text(str(term))
        for term in (prompt.get(key) or [])
        if str(term).strip()
    }


def answer_searchable_blob(row: dict[str, Any]) -> str:
    """Answer-body text used for scenario-specific must-term checks.

    Route cards are visible in the UI, but using them for must-terms can let a
    weak answer pass because the classifier happened to name the right issue.
    Keep this strict: if a prompt says the answer must mention "UPI" or
    "medical records", the answer body itself should carry that context.
    """
    return _term_search_text(str(row.get("answer_text") or ""))


def _term_search_text(text: str) -> str:
    value = str(text).lower()
    value = re.sub(r"[-_/]+", " ", value)
    return re.sub(r"\s+", " ", value).strip()


def searchable_blob(row: dict[str, Any]) -> str:
    """Visible text-ish fields that a user can inspect in the UI.

    Do not include hidden evaluator metadata such as expected_act_keys or
    source titles here. Those have their own grounding metrics and should not
    make a weak answer pass scenario-specific usefulness checks.
    """
    parts: list[str] = [
        str(row.get("answer_text") or ""),
        str(row.get("route_category") or ""),
        str(row.get("route_label") or ""),
        str(row.get("action_pack_id") or ""),
    ]
    for key in (
        "route_required_sources",
        "route_forums",
        "route_missing_facts",
        "action_pack_cautions",
        "action_pack_next_steps",
        "red_flags",
    ):
        value = row.get(key)
        if isinstance(value, list):
            parts.extend(str(item) for item in value)
    return re.sub(r"\s+", " ", " ".join(parts).lower())


def summarize(rows: list[dict[str, Any]]) -> dict[str, Any]:
    total = len(rows)
    product_pass = [row for row in rows if row.get("product_pass")]
    high = [row for row in rows if str(row.get("product_priority") or "").lower() == "high"]
    critical = [row for row in rows if str(row.get("product_priority") or "").lower() == "critical"]
    expected_cited_scored = [row for row in rows if row.get("expected_act_cited_hit") is not None]
    expected_cited_hits = [
        row
        for row in expected_cited_scored
        if row.get("expected_act_cited_hit") is True or row.get("safe_source_gap") is True
    ]
    expected_cited_strict_hits = [
        row for row in expected_cited_scored if row.get("expected_act_cited_hit") is True
    ]
    first_actionable_scored = [row for row in rows if row.get("first_cited_is_actionable") is not None]
    first_actionable = [row for row in first_actionable_scored if row.get("first_cited_is_actionable") is True]
    route_matches_count = sum(1 for row in rows if row.get("route_match"))
    must_terms_count = sum(1 for row in rows if row.get("must_terms_ok"))
    bad_route_count = sum(1 for row in rows if row.get("bad_route_fallback"))
    safe_source_gap_count = sum(1 for row in rows if row.get("safe_source_gap"))
    visible_source_gap_count = sum(1 for row in rows if row.get("source_gap_visible"))
    route_gap_rows = [row for row in rows if row.get("route_required_sources_missing")]
    route_gap_total = sum(len(row.get("route_required_sources_missing") or []) for row in route_gap_rows)
    unclassified_route_gap_rows = [
        row for row in route_gap_rows if row.get("has_unclassified_route_source_gap") is True
    ]
    safety_hard = sum(1 for row in rows if (row.get("legal_safety") or {}).get("hard_fail"))
    wall = [float(row["wall_ms"]) for row in rows if _is_number(row.get("wall_ms"))]
    llm_path_rows = [row for row in rows if _is_llm_path(row)]
    llm_path_wall = [_row_total_ms(row) for row in llm_path_rows]
    llm_path_wall = [float(v) for v in llm_path_wall if v is not None]
    template_path_rows = [row for row in rows if _has_required_timing(row) and not _is_llm_path(row)]
    template_path_wall = [_row_total_ms(row) for row in template_path_rows]
    template_path_wall = [float(v) for v in template_path_wall if v is not None]
    wall_latency_count = len(wall)
    timing_telemetry_count = sum(1 for row in rows if _has_required_timing(row))
    failure_counter: Counter[str] = Counter()
    route_counter: Counter[str] = Counter(str(row.get("route_category") or "unknown") for row in rows)
    issue_fail_counter: Counter[str] = Counter()
    owner_counter: Counter[str] = Counter(str(row.get("workflow_answer_owner") or "unknown") for row in rows)
    owner_pass_counter: Counter[str] = Counter()
    owner_fail_counter: Counter[str] = Counter()
    mode_counter: Counter[str] = Counter(str(row.get("workflow_answer_mode") or "unknown") for row in rows)
    safe_source_gap_kind_counter: Counter[str] = Counter(
        str(row.get("safe_source_gap_kind") or "unknown")
        for row in rows
        if row.get("safe_source_gap")
    )
    route_gap_kind_counter: Counter[str] = Counter(
        str(item.get("kind") or "unknown")
        for row in rows
        for item in (row.get("route_required_source_gap_classifications") or [])
        if isinstance(item, dict)
    )
    for row in rows:
        owner = str(row.get("workflow_answer_owner") or "unknown")
        if row.get("product_pass"):
            owner_pass_counter[owner] += 1
        else:
            owner_fail_counter[owner] += 1
        for failure in row.get("product_failures") or []:
            failure_counter[failure] += 1
        if row.get("product_failures"):
            issue_fail_counter[str(row.get("common_issue") or "unknown")] += 1
    owner_metrics = {
        owner: {
            "rows": count,
            "product_pass": owner_pass_counter[owner],
            "product_fail": owner_fail_counter[owner],
            "product_pass_pct": pct(owner_pass_counter[owner], count),
        }
        for owner, count in owner_counter.items()
    }

    return {
        "rows": total,
        "product_pass_count": len(product_pass),
        "product_pass_pct": pct(len(product_pass), total),
        "high_priority_count": len(high),
        "high_priority_pass_count": sum(1 for row in high if row.get("product_pass")),
        "high_priority_pass_pct": pct(sum(1 for row in high if row.get("product_pass")), len(high)) if high else 100.0,
        "critical_priority_count": len(critical),
        "critical_priority_pass_count": sum(1 for row in critical if row.get("product_pass")),
        "critical_priority_pass_pct": pct(sum(1 for row in critical if row.get("product_pass")), len(critical)) if critical else 100.0,
        "route_match_count": route_matches_count,
        "route_match_pct": pct(route_matches_count, total),
        "expected_act_cited_scored": len(expected_cited_scored),
        "expected_act_cited_hits": len(expected_cited_hits),
        "expected_act_cited_pct": pct(len(expected_cited_hits), len(expected_cited_scored)),
        "expected_act_cited_strict_hits": len(expected_cited_strict_hits),
        "expected_act_cited_strict_pct": pct(len(expected_cited_strict_hits), len(expected_cited_scored)),
        "first_actionable_scored": len(first_actionable_scored),
        "first_actionable_count": len(first_actionable),
        "first_actionable_pct": pct(len(first_actionable), len(first_actionable_scored)),
        "must_terms_count": must_terms_count,
        "must_terms_pct": pct(must_terms_count, total),
        "errors": sum(1 for row in rows if row.get("error")),
        "refusals": sum(1 for row in rows if row.get("refused")),
        "bad_route_fallbacks": bad_route_count,
        "safe_source_gaps": safe_source_gap_count,
        "visible_source_gap_rows": visible_source_gap_count,
        "safe_source_gap_kinds": dict(safe_source_gap_kind_counter),
        "route_source_gap_rows": len(route_gap_rows),
        "route_source_gap_total": route_gap_total,
        "route_source_gap_kinds": dict(route_gap_kind_counter),
        "unclassified_route_source_gap_rows": len(unclassified_route_gap_rows),
        "safety_hard_fails": safety_hard,
        "wall_latency_count": wall_latency_count,
        "wall_latency_coverage_pct": pct(wall_latency_count, total),
        "timing_telemetry_count": timing_telemetry_count,
        "timing_telemetry_pct": pct(timing_telemetry_count, total),
        "p50_ms": percentile(wall, 0.50),
        "p90_ms": percentile(wall, 0.90),
        "llm_path_rows": len(llm_path_rows),
        "llm_path_p50_ms": percentile(llm_path_wall, 0.50),
        "llm_path_p90_ms": percentile(llm_path_wall, 0.90),
        "template_path_rows": len(template_path_rows),
        "template_path_p50_ms": percentile(template_path_wall, 0.50),
        "template_path_p90_ms": percentile(template_path_wall, 0.90),
        "routes": dict(route_counter),
        "failure_counts": dict(failure_counter),
        "issue_failure_counts": dict(issue_fail_counter),
        "answer_owner_counts": dict(owner_counter),
        "answer_mode_counts": dict(mode_counter),
        "answer_owner_metrics": owner_metrics,
        "workflow_shadowed_by_legacy": sum(1 for row in rows if row.get("workflow_shadowed_by_legacy") is True),
    }


def evaluate_gate(metrics: dict[str, Any], config: GateConfig) -> list[str]:
    failures: list[str] = []
    check_min(failures, "rows", metrics["rows"], config.min_rows)
    check_min(failures, "product_pass_pct", metrics["product_pass_pct"], config.min_product_pass_pct)
    check_min(failures, "high_priority_pass_pct", metrics["high_priority_pass_pct"], config.min_high_priority_pass_pct)
    check_min(failures, "critical_priority_count", metrics["critical_priority_count"], config.min_critical_rows)
    check_min(failures, "critical_priority_pass_pct", metrics["critical_priority_pass_pct"], config.min_critical_priority_pass_pct)
    check_min(failures, "route_match_pct", metrics["route_match_pct"], config.min_route_match_pct)
    check_min(failures, "expected_act_cited_pct", metrics["expected_act_cited_pct"], config.min_expected_act_cited_pct)
    check_min(failures, "first_actionable_pct", metrics["first_actionable_pct"], config.min_first_actionable_pct)
    check_min(failures, "must_terms_pct", metrics["must_terms_pct"], config.min_must_terms_pct)
    check_min(failures, "wall_latency_coverage_pct", metrics["wall_latency_coverage_pct"], config.min_wall_latency_coverage_pct)
    check_min(failures, "timing_telemetry_pct", metrics["timing_telemetry_pct"], config.min_timing_telemetry_pct)
    check_max(failures, "errors", metrics["errors"], config.max_errors)
    check_max(failures, "refusals", metrics["refusals"], config.max_refusals)
    check_max(failures, "bad_route_fallbacks", metrics["bad_route_fallbacks"], config.max_bad_route_fallbacks)
    check_max(failures, "safety_hard_fails", metrics["safety_hard_fails"], config.max_safety_hard_fails)
    check_max(failures, "p50_ms", metrics["p50_ms"], config.max_p50_ms)
    check_max(failures, "p90_ms", metrics["p90_ms"], config.max_p90_ms)
    check_max(failures, "llm_path_p90_ms", metrics["llm_path_p90_ms"], config.max_llm_path_p90_ms)
    check_max(failures, "safe_source_gaps", metrics["safe_source_gaps"], config.max_safe_source_gaps)
    check_max(failures, "visible_source_gap_rows", metrics.get("visible_source_gap_rows", 0), 0)
    check_max(
        failures,
        "route_source_gap_rows",
        metrics["route_source_gap_rows"],
        config.max_route_source_gap_rows,
    )
    check_max(
        failures,
        "unclassified_route_source_gap_rows",
        metrics["unclassified_route_source_gap_rows"],
        config.max_unclassified_route_source_gap_rows,
    )
    return failures


def write_failures_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for row in rows:
            if row.get("product_failures"):
                slim = {
                    "query": row.get("query"),
                    "common_issue": row.get("common_issue"),
                    "product_priority": row.get("product_priority"),
                    "expected_category": row.get("expected_category"),
                    "route": row.get("route") or row.get("route_category"),
                    "route_category": row.get("route_category"),
                    "expected_route_any": row.get("expected_route_any"),
                    "expected_act_hint": row.get("expected_act_hint"),
                    "expected_act_hit": row.get("expected_act_hit"),
                    "expected_act_cited_hit": row.get("expected_act_cited_hit"),
                    "safe_source_gap": row.get("safe_source_gap"),
                    "workflow_id": row.get("workflow_id"),
                    "workflow_answer_owner": row.get("workflow_answer_owner"),
                    "workflow_answer_mode": row.get("workflow_answer_mode"),
                    "workflow_contract_miss_reason": row.get("workflow_contract_miss_reason"),
                    "workflow_shadowed_by_legacy": row.get("workflow_shadowed_by_legacy"),
                    "shadowed_workflow_id": row.get("shadowed_workflow_id"),
                    "route_required_sources_missing": row.get("route_required_sources_missing"),
                    "unknown_citation_indices": row.get("unknown_citation_indices"),
                    "relevance_verdict": row.get("relevance_verdict"),
                    "answer_quality_flags": row.get("answer_quality_flags"),
                    "product_failures": row.get("product_failures"),
                    "answer_text": row.get("answer_text"),
                    "top_sources": row.get("top_sources"),
                    "wall_ms": row.get("wall_ms"),
                }
                # JSONL must remain one physical line per record. Keep
                # non-ASCII escaped so line/paragraph separators from source
                # text cannot split a product-failure record.
                f.write(json.dumps(slim, ensure_ascii=True) + "\n")


def write_report(
    path: Path,
    rows: list[dict[str, Any]],
    metrics: dict[str, Any],
    failures: list[str],
    config: GateConfig,
    eval_path: Path,
    prompts_path: Path,
) -> None:
    failed_rows = [row for row in rows if row.get("product_failures")]
    lines = [
        "# Common User Product Gate",
        "",
        f"Eval: `{eval_path}`",
        f"Prompts: `{prompts_path}`",
        f"Gate: **{'PASS' if not failures else 'FAIL'}**",
        "",
        "## Gate Metrics",
        "",
        "| metric | value | target |",
        "| --- | ---: | ---: |",
        f"| rows | {metrics['rows']} | >= {config.min_rows} |",
        f"| product_pass | {metrics['product_pass_count']}/{metrics['rows']} ({metrics['product_pass_pct']:.1f}%) | >= {config.min_product_pass_pct:.1f}% |",
        f"| high_priority_pass | {metrics['high_priority_pass_count']}/{metrics['high_priority_count']} ({metrics['high_priority_pass_pct']:.1f}%) | >= {config.min_high_priority_pass_pct:.1f}% |",
        f"| critical_rows | {metrics['critical_priority_count']} | >= {config.min_critical_rows} |",
        f"| critical_priority_pass | {metrics['critical_priority_pass_count']}/{metrics['critical_priority_count']} ({metrics['critical_priority_pass_pct']:.1f}%) | >= {config.min_critical_priority_pass_pct:.1f}% |",
        f"| route_match | {metrics['route_match_count']}/{metrics['rows']} ({metrics['route_match_pct']:.1f}%) | >= {config.min_route_match_pct:.1f}% |",
        f"| expected_act_cited | {metrics['expected_act_cited_hits']}/{metrics['expected_act_cited_scored']} ({metrics['expected_act_cited_pct']:.1f}%) | >= {config.min_expected_act_cited_pct:.1f}% |",
        f"| expected_act_cited_strict | {metrics['expected_act_cited_strict_hits']}/{metrics['expected_act_cited_scored']} ({metrics['expected_act_cited_strict_pct']:.1f}%) | informational; excludes safe source gaps |",
        f"| first_cited_actionable | {metrics['first_actionable_count']}/{metrics['first_actionable_scored']} ({metrics['first_actionable_pct']:.1f}%) | >= {config.min_first_actionable_pct:.1f}% |",
        f"| must_terms | {metrics['must_terms_count']}/{metrics['rows']} ({metrics['must_terms_pct']:.1f}%) | >= {config.min_must_terms_pct:.1f}% |",
        f"| wall_latency_coverage | {metrics['wall_latency_count']}/{metrics['rows']} ({metrics['wall_latency_coverage_pct']:.1f}%) | >= {config.min_wall_latency_coverage_pct:.1f}% |",
        f"| timing_telemetry | {metrics['timing_telemetry_count']}/{metrics['rows']} ({metrics['timing_telemetry_pct']:.1f}%) | >= {config.min_timing_telemetry_pct:.1f}% |",
        f"| errors | {metrics['errors']} | <= {config.max_errors} |",
        f"| refusals | {metrics['refusals']} | <= {config.max_refusals} |",
        f"| bad_route_fallbacks | {metrics['bad_route_fallbacks']} | <= {config.max_bad_route_fallbacks} |",
        f"| safe_source_gaps | {metrics['safe_source_gaps']} | <= {config.max_safe_source_gaps} |",
        f"| visible_source_gap_rows | {metrics['visible_source_gap_rows']} | = 0 |",
        f"| route_source_gap_rows | {metrics['route_source_gap_rows']} | <= {config.max_route_source_gap_rows} |",
        f"| unclassified_route_source_gap_rows | {metrics['unclassified_route_source_gap_rows']} | <= {config.max_unclassified_route_source_gap_rows} |",
        f"| safety_hard_fails | {metrics['safety_hard_fails']} | <= {config.max_safety_hard_fails} |",
        f"| p50_latency | {fmt_ms(metrics['p50_ms'])} | <= {fmt_ms(config.max_p50_ms)} |",
        f"| p90_latency | {fmt_ms(metrics['p90_ms'])} | <= {fmt_ms(config.max_p90_ms)} |",
        f"| llm_path_p90_latency | {fmt_ms(metrics['llm_path_p90_ms'])} ({metrics['llm_path_rows']} rows) | <= {fmt_ms(config.max_llm_path_p90_ms)} |",
        f"| template_path_p90_latency | {fmt_ms(metrics['template_path_p90_ms'])} ({metrics['template_path_rows']} rows) | informational |",
        "",
        "## Failure Counts",
        "",
        "| failure | count |",
        "| --- | ---: |",
    ]
    failure_counts = Counter(metrics["failure_counts"])
    if failure_counts:
        for failure, count in failure_counts.most_common():
            lines.append(f"| {failure} | {count} |")
    else:
        lines.append("| none | 0 |")

    lines.extend(["", "## Failed Common Issues", "", "| issue | failures |", "| --- | ---: |"])
    issue_counts = Counter(metrics["issue_failure_counts"])
    if issue_counts:
        for issue, count in issue_counts.most_common(30):
            lines.append(f"| {issue} | {count} |")
    else:
        lines.append("| none | 0 |")

    lines.extend(["", "## Routes", "", "| route | count |", "| --- | ---: |"])
    for route, count in Counter(metrics["routes"]).most_common():
        lines.append(f"| {route} | {count} |")

    lines.extend([
        "",
        "## Answer Ownership",
        "",
        f"Workflow contracts shadowed by legacy templates: {metrics['workflow_shadowed_by_legacy']}/{metrics['rows']}",
        "",
        "| owner | rows | product pass | product fail | pass rate |",
        "| --- | ---: | ---: | ---: | ---: |",
    ])
    owner_metrics = metrics.get("answer_owner_metrics") or {}
    for owner, data in sorted(
        owner_metrics.items(),
        key=lambda item: (-int(item[1].get("rows") or 0), item[0]),
    ):
        rows_count = int(data.get("rows") or 0)
        passed = int(data.get("product_pass") or 0)
        failed = int(data.get("product_fail") or 0)
        pass_pct = float(data.get("product_pass_pct") or 0.0)
        lines.append(f"| {md(owner)} | {rows_count} | {passed} | {failed} | {pass_pct:.1f}% |")

    lines.extend(["", "| answer_mode | count |", "| --- | ---: |"])
    for mode, count in Counter(metrics.get("answer_mode_counts") or {}).most_common():
        lines.append(f"| {md(str(mode))} | {count} |")

    lines.extend(["", "## Source Gap Diagnostics", ""])
    lines.extend(["| safe source gap kind | count |", "| --- | ---: |"])
    safe_gap_kinds = Counter(metrics.get("safe_source_gap_kinds") or {})
    if safe_gap_kinds:
        for kind, count in safe_gap_kinds.most_common():
            lines.append(f"| {md(str(kind))} | {count} |")
    else:
        lines.append("| none | 0 |")

    lines.extend(["", "| route source gap kind | count |", "| --- | ---: |"])
    route_gap_kinds = Counter(metrics.get("route_source_gap_kinds") or {})
    if route_gap_kinds:
        for kind, count in route_gap_kinds.most_common():
            lines.append(f"| {md(str(kind))} | {count} |")
    else:
        lines.append("| none | 0 |")

    route_gap_rows = [row for row in rows if row.get("route_required_sources_missing")]
    lines.extend([
        "",
        "| route | kind | query | missing source |",
        "| --- | --- | --- | --- |",
    ])
    for row in route_gap_rows[:80]:
        classes = row.get("route_required_source_gap_classifications") or []
        if not classes:
            lines.append(
                f"| {md(str(row.get('route_category') or ''))} | unclassified_route_source_gap | "
                f"{md(str(row.get('query') or ''), 100)} | {md('; '.join(str(s) for s in row.get('route_required_sources_missing') or []), 160)} |"
            )
            continue
        for item in classes:
            if not isinstance(item, dict):
                continue
            lines.append(
                f"| {md(str(row.get('route_category') or ''))} | {md(str(item.get('kind') or ''))} | "
                f"{md(str(row.get('query') or ''), 100)} | {md(str(item.get('required_source') or ''), 160)} |"
            )
    if not route_gap_rows:
        lines.append("| none | n/a | n/a | n/a |")

    if failures:
        lines.extend(["", "## Gate Failures", ""])
        lines.extend(f"- {failure}" for failure in failures)

    lines.extend([
        "",
        "## Product Failure Samples",
        "",
        "| issue | route | failures | query | owner | answer excerpt |",
        "| --- | --- | --- | --- | --- | --- |",
    ])
    for row in failed_rows[:80]:
        lines.append(
            "| "
            + " | ".join([
                md(str(row.get("common_issue") or "")),
                md(str(row.get("route_category") or "")),
                md(", ".join(row.get("product_failures") or [])),
                md(str(row.get("query") or ""), 100),
                md(str(row.get("workflow_answer_owner") or "unknown")),
                md(str(row.get("answer_text") or ""), 160),
            ])
            + " |"
        )
    if not failed_rows:
        lines.append("| none | n/a | n/a | n/a | n/a |")

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def check_min(failures: list[str], name: str, actual: Any, expected: float) -> None:
    if actual is None or float(actual) < expected:
        failures.append(f"{name} {actual} < {expected}")


def check_max(failures: list[str], name: str, actual: Any, expected: float) -> None:
    if actual is None:
        return
    if float(actual) > expected:
        failures.append(f"{name} {actual} > {expected}")


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


def fmt_ms(value: float | None) -> str:
    if value is None:
        return "n/a"
    return f"{value / 1000:.1f}s"


def md(value: str, limit: int = 80) -> str:
    text = value.replace("|", " ").replace("\n", " ").strip()
    if len(text) > limit:
        text = text[: limit - 1] + "..."
    return text


def normalize_query(query: str) -> str:
    return re.sub(r"\s+", " ", query.strip().lower())


def _int(value: Any) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        return 0
    return value if value >= 0 else 0


def _is_number(value: Any) -> bool:
    return isinstance(value, int | float) and not isinstance(value, bool) and math.isfinite(float(value))


def _has_required_timing(row: dict[str, Any]) -> bool:
    timing = row.get("timing")
    if not isinstance(timing, dict):
        return False
    required = ("total_ms", "retrieval_ms", "llm_stream_ms", "verification_ms")
    return all(_is_number(timing.get(key)) and float(timing[key]) >= 0 for key in required)


def _is_llm_path(row: dict[str, Any]) -> bool:
    timing = row.get("timing")
    if not isinstance(timing, dict):
        return False
    value = timing.get("llm_stream_ms")
    return _is_number(value) and float(value) > LLM_PATH_THRESHOLD_MS


def _row_total_ms(row: dict[str, Any]) -> float | None:
    timing = row.get("timing")
    if isinstance(timing, dict) and _is_number(timing.get("total_ms")):
        return float(timing["total_ms"])
    if _is_number(row.get("wall_ms")):
        return float(row["wall_ms"])
    return None


def _has_nonempty_string_list(row: dict[str, Any], key: str) -> bool:
    value = row.get(key)
    return isinstance(value, list) and any(isinstance(item, str) and item.strip() for item in value)


def _has_meaningful_action_pack(row: dict[str, Any]) -> bool:
    pack_id = str(row.get("action_pack_id") or "").strip().lower()
    if not pack_id or pack_id == "none":
        return False
    return (
        _has_nonempty_string_list(row, "action_pack_next_steps")
        and _has_nonempty_string_list(row, "route_forums")
        and _has_nonempty_string_list(row, "route_missing_facts")
        and _has_nonempty_string_list(row, "route_required_sources")
    )


if __name__ == "__main__":
    raise SystemExit(main())
