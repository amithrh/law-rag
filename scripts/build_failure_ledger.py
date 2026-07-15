#!/usr/bin/env python3
"""Build a harm-ranked product-failure ledger from a timed eval.

The common-user gate tells us whether a row passed. This ledger is for deciding
what to fix next without metric hacking: it tags each failed row with a primary
root cause, harm bucket, and likely implementation stage.
"""
from __future__ import annotations

import argparse
import csv
import json
import re
from collections import Counter
from pathlib import Path
from typing import Any

from scripts.eval_common_user_gate import load_eval_rows, load_prompt_rows, score_rows


ROOT_CAUSE_ORDER = (
    "legal_safety_hard_fail",
    "error",
    "refused",
    "safe_source_gap_not_production_ready",
    "route_required_source_gap",
    "expected_act_missing",
    "zero_ok_legal_sentences",
    "relevance_not_ok",
    "expected_act_not_cited",
    "unknown_citation_indices",
    "first_cited_not_actionable",
    "judgment_before_actionable_source",
    "missing_scenario_terms",
    "suppressed_sentences",
)


def main() -> int:
    args = parse_args()
    prompt_rows = load_prompt_rows(args.prompts)
    scored = score_rows(load_eval_rows(args.eval_jsonl), prompt_rows)
    failed = [
        classify(row, index=i + 1)
        for i, row in enumerate(scored)
        if row.get("product_failures") or strict_product_failures(row)
    ]
    failed.sort(key=sort_key)

    if args.jsonl:
        write_jsonl(args.jsonl, failed)
    if args.csv:
        write_csv(args.csv, failed)
    if args.report:
        write_report(args.report, failed, args.eval_jsonl, args.prompts)

    print(f"failure ledger rows: {len(failed)}")
    for title, key in (
        ("priority", "product_priority"),
        ("root_cause", "root_cause"),
        ("harm_bucket", "harm_bucket"),
        ("route", "route_category"),
        ("issue", "common_issue"),
    ):
        counts = Counter(str(row.get(key) or "unknown") for row in failed)
        print(f"\n{title}")
        for value, count in counts.most_common(15):
            print(f"{count:3} {value}")
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("eval_jsonl", type=Path)
    parser.add_argument("--prompts", type=Path, required=True)
    parser.add_argument("--jsonl", type=Path)
    parser.add_argument("--csv", type=Path)
    parser.add_argument("--report", type=Path)
    return parser.parse_args()


def classify(row: dict[str, Any], *, index: int) -> dict[str, Any]:
    common_failures = [str(item) for item in row.get("product_failures") or []]
    strict_failures = strict_product_failures(row)
    failures = list(dict.fromkeys(common_failures + strict_failures))
    root_cause = primary_root_cause(failures)
    route = str(row.get("route_category") or "")
    issue = str(row.get("common_issue") or row.get("expected_category") or "")
    query = str(row.get("query") or "")
    bucket = harm_bucket(route=route, issue=issue, query=query)
    priority = infer_priority(
        configured=row.get("product_priority"),
        harm=bucket,
        route=route,
        issue=issue,
        query=query,
    )
    subtype = variant_subtype(route=route, issue=issue, query=query)
    gaps = completeness_gaps(row=row, subtype=subtype, root_cause=root_cause)
    return {
        "eval_index": index,
        "product_priority": priority,
        "severity_rank": 0 if priority == "critical" else 1 if priority == "high" else 2 if priority == "medium" else 3,
        "root_cause": root_cause,
        "variant_subtype": subtype,
        "completeness_gaps": gaps,
        "harm_bucket": bucket,
        "recommended_stage": recommended_stage(root_cause=root_cause, route=route, issue=issue, query=query),
        "first_patch_target": first_patch_target(
            root_cause=root_cause,
            route=route,
            issue=issue,
            query=query,
        ),
        "needs_manual_adjudication": needs_manual_adjudication(
            root_cause=root_cause,
            route=route,
            issue=issue,
            query=query,
        ),
        "route_category": route,
        "common_issue": issue,
        "expected_category": row.get("expected_category"),
        "relevance_verdict": row.get("relevance_verdict"),
        "expected_act_hint": row.get("expected_act_hint"),
        "expected_act_hit": row.get("expected_act_hit"),
        "expected_act_cited_hit": row.get("expected_act_cited_hit"),
        "common_gate_failures": common_failures,
        "strict_gate_failures": strict_failures,
        "product_failures": failures,
        "answer_quality_flags": row.get("answer_quality_flags") or [],
        "must_include_any": row.get("must_include_any") or [],
        "must_include_all": row.get("must_include_all") or [],
        "wall_ms": row.get("wall_ms"),
        "query": query,
        "answer_excerpt": clip(row.get("answer_text")),
        "top_sources": [
            {
                "title": source.get("title"),
                "anchor": source.get("anchor"),
                "source_type": source.get("source_type"),
                "statute_short": source.get("statute_short"),
            }
            for source in (row.get("top_sources") or [])[:5]
            if isinstance(source, dict)
        ],
        "fix_hint": fix_hint(route=route, issue=issue, root_cause=root_cause, query=query),
    }


def strict_product_failures(row: dict[str, Any]) -> list[str]:
    """Mirror the timed-eval strict product pass rule for ledger completeness."""
    failures: list[str] = []
    if row.get("error"):
        failures.append("error")
    if row.get("refused"):
        failures.append("refused")
    if str(row.get("relevance_verdict") or "").lower() != "ok":
        failures.append("relevance_not_ok")
    if (row.get("legal_safety") or {}).get("hard_fail"):
        failures.append("legal_safety_hard_fail")
    if row.get("safe_source_gap") is True and (
        row.get("expected_act_hit") is False or row.get("expected_act_cited_hit") is False
    ):
        failures.append("safe_source_gap_not_production_ready")
    elif row.get("expected_act_cited_hit") is False:
        failures.append("expected_act_not_cited")
    if int(row.get("unknown_citation_count") or 0) > 0:
        failures.append("unknown_citation_indices")
    if row.get("route_required_sources_missing"):
        failures.append("route_required_source_gap")
    return list(dict.fromkeys(failures))


def primary_root_cause(failures: list[str]) -> str:
    for item in ROOT_CAUSE_ORDER:
        if item in failures:
            if item == "safe_source_gap_not_production_ready":
                return "source_or_retrieval_gap"
            if item == "route_required_source_gap":
                return "route_required_source_gap"
            if item == "expected_act_missing":
                return "source_or_retrieval_gap"
            if item == "expected_act_not_cited":
                return "citation_discipline_gap"
            if item == "relevance_not_ok":
                return "variant_answer_gap"
            if item == "missing_scenario_terms":
                return "scenario_specificity_gap"
            if item == "zero_ok_legal_sentences":
                return "answer_support_floor"
            return item
    return failures[0] if failures else "unknown"


def infer_priority(*, configured: object, harm: str, route: str, issue: str, query: str) -> str:
    value = str(configured or "").strip().lower()
    if value in {"critical", "high", "medium", "low"}:
        return value
    blob = f"{harm} {route} {issue} {query}".lower()
    if has_any_term(blob, (
        "custody", "bail", "undertrial", "arrest", "uapa", "pmla", "ndps",
        "juvenile", "lockup", "torture", "rape", "pocso", "domestic violence",
        "deepfake", "nude", "csam", "suicide", "self harm",
    )):
        return "critical"
    if harm in {
        "criminal_procedure_high_risk",
        "cyber_sexual_privacy_high_risk",
        "caste_tribal_state_harm",
        "family_child_safety",
        "labour_welfare_survival",
    }:
        return "high"
    if harm in {"property_civil_practical", "banking_platform_money", "business_tax_procedure"}:
        return "medium"
    return "medium"


def normalized_search_text(value: object) -> str:
    text = str(value or "").lower()
    text = re.sub(r"[_\-/]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def has_term(blob: str, term: str) -> bool:
    text = normalized_search_text(blob)
    needle = normalized_search_text(term)
    if not needle:
        return False
    pattern = r"(?<![a-z0-9])" + re.escape(needle).replace(r"\ ", r"\s+") + r"(?![a-z0-9])"
    return re.search(pattern, text) is not None


def has_any_term(blob: str, terms: tuple[str, ...]) -> bool:
    return any(has_term(blob, term) for term in terms)


def harm_bucket(*, route: str, issue: str, query: str) -> str:
    blob = f"{route} {issue} {query}".lower()
    if has_any_term(blob, ("bail", "custody", "undertrial", "arrest", "false charge", "false fir", "pmla", "ndps", "uapa", "mcoca")):
        return "criminal_procedure_high_risk"
    if has_any_term(blob, ("deepfake", "csam", "morphed", "porn", "nude", "extort", "stalk", "blackmail", "cyber privacy", "dpdp")):
        return "cyber_sexual_privacy_high_risk"
    if has_any_term(blob, ("caste", "atrocity", "tribal", "adivasi", "witch", "daayan", "tonhi", "ojha", "sarna", "ifr", "palli sabha", "land alienation")):
        return "caste_tribal_state_harm"
    if has_any_term(blob, ("wage", "epf", "esi", "asha", "scholarship", "pension", "ration", "minimum wage", "contract labour", "mgnrega")):
        return "labour_welfare_survival"
    if has_any_term(blob, ("child", "minor", "domestic", "violence", "marriage", "custody", "maintenance")):
        return "family_child_safety"
    if has_any_term(blob, ("street vendor", "vendor", "hawker", "tvc", "cart", "municipal")):
        return "street_vendor_local_livelihood"
    if has_any_term(blob, ("property", "will", "mutation", "gift", "succession", "inheritance", "passbook", "land revenue")):
        return "property_civil_practical"
    if has_any_term(blob, ("bank", "loan", "freeze", "frozen", "sarfaesi", "cibil", "platform", "driver", "account")):
        return "banking_platform_money"
    if has_any_term(blob, ("ibc", "nclt", "business", "tax", "gst", "customs", "trademark", "copyright", "msme")):
        return "business_tax_procedure"
    return "other_user_quality"


def variant_subtype(*, route: str, issue: str, query: str) -> str:
    """Label the concrete user-task variant behind a product failure."""
    blob = f"{route} {issue} {query}".lower()
    if has_any_term(blob, ("senior", "old", "72", "73", "81")):
        if has_any_term(blob, ("how much", "maximum", "max", "amount", "kitna")):
            return "senior_maintenance_amount_cap"
        if has_any_term(blob, ("threw", "thrown", "own house", "own home", "kitchen", "not allowed", "daughter in law")):
            return "senior_eviction_residence_property_pressure"
        if has_any_term(blob, ("food", "money", "abandoned", "neglect", "maintenance")):
            return "senior_food_money_support"
        return "senior_parent_support_general"
    if has_any_term(blob, ("mgnrega", "nrega", "job card", "muster", "gram sabha", "social audit")):
        if has_any_term(blob, ("wage", "wages", "not paid", "no payment", "funds not come")):
            return "mgnrega_wage_delay_unpaid"
        if has_any_term(blob, ("job card", "jobcard", "not given", "not issued", "9 months", "delay")):
            return "mgnrega_job_card_refusal"
        if has_any_term(blob, ("fake", "muster", "social audit", "gram sabha", "corruption", "mukhiya", "sarpanch")):
            return "mgnrega_fake_muster_social_audit"
        return "mgnrega_scheme_grievance_general"
    if has_term(blob, "uapa") and has_any_term(blob, ("no chargesheet", "no charge sheet", "90 days", "default bail", "extension")):
        return "uapa_default_bail_extension_180"
    if has_any_term(blob, ("ipc 420", "420", "cheating")) and has_any_term(blob, ("no chargesheet", "no charge sheet", "default bail", "6 months")):
        return "default_bail_ipc420_bns318_punishment_period"
    if has_any_term(blob, ("ndps", "heroin", "mdma", "ganja", "charas", "bhang", "cannabis")):
        if has_any_term(blob, ("rejected", "supreme court", "long custody", "3 yrs", "3 years")):
            return "ndps_repeat_bail_section37_delay"
        if has_any_term(blob, ("small quantity", "commercial", "quantity", "gram", "grams", "50g", "200g", "personal use")):
            return "ndps_quantity_bail_small_intermediate_commercial"
        if has_any_term(blob, ("no chargesheet", "no charge sheet", "default bail", "180 days", "181 days")):
            return "ndps_default_bail_36a"
        return "ndps_bail_general"
    if has_any_term(blob, ("juvenile", "minor", "under 18", "adult jail", "observation home", "16 yr", "17 yr", "16 year", "17 year")):
        return "juvenile_adult_jail_age_proof"
    fallback = normalized_search_text(issue or route).replace(" ", "_")
    return fallback or "unclassified_variant"


def completeness_gaps(*, row: dict[str, Any], subtype: str, root_cause: str) -> list[str]:
    answer = str(row.get("answer_text") or "").lower()
    failures = {str(item) for item in row.get("product_failures") or []}
    gaps: list[str] = []
    if root_cause == "source_or_retrieval_gap" or "expected_act_missing" in failures:
        gaps.append("controlling_source_missing")
    if root_cause == "citation_discipline_gap" or "expected_act_not_cited" in failures:
        gaps.append("controlling_source_not_cited")
    if "missing_next_step_section" in failures or "**what you can do next**" not in answer:
        gaps.append("procedure_steps_missing")

    def missing_any(terms: tuple[str, ...]) -> bool:
        return not any(term in answer for term in terms)

    if subtype.startswith("senior_"):
        if missing_any(("maintenance tribunal", "district social welfare", "senior-citizen authority", "senior citizen authority")):
            gaps.append("forum_authority_missing")
        if subtype == "senior_maintenance_amount_cap" and missing_any(("rs.10,000", "10,000", "tribunal")):
            gaps.append("threshold_amount_missing")
        if subtype == "senior_eviction_residence_property_pressure" and missing_any(("residence", "house", "kitchen", "property", "transfer")):
            gaps.append("scenario_facts_missing")
    elif subtype.startswith("mgnrega_"):
        if missing_any(("programme officer", "bdo", "ombudsman", "district mgnrega")):
            gaps.append("forum_authority_missing")
        if subtype == "mgnrega_job_card_refusal" and missing_any(("job-card", "job card", "work-demand", "work demand")):
            gaps.append("scenario_facts_missing")
        if subtype == "mgnrega_fake_muster_social_audit" and missing_any(("social audit", "gram sabha", "muster", "action-taken", "action taken")):
            gaps.append("scenario_facts_missing")
    elif subtype.startswith("uapa_"):
        if missing_any(("43d", "180", "extension", "special court")):
            gaps.append("special_statute_threshold_missing")
    elif subtype.startswith("default_bail_"):
        if missing_any(("custody-days", "custody days", "remand", "charge-sheet", "chargesheet")):
            gaps.append("deadline_calculation_missing")
    elif subtype.startswith("ndps_"):
        if missing_any(("section 37", "quantity", "fsl", "seizure", "special court")):
            gaps.append("threshold_or_forum_missing")
    elif subtype.startswith("juvenile_"):
        if missing_any(("juvenile justice board", "observation home", "age-determination", "age determination", "school certificate", "birth certificate")):
            gaps.append("age_custody_transfer_missing")
    if not gaps and "relevance_not_ok" in failures:
        gaps.append("relevance_judge_or_language_alignment")
    return gaps


def recommended_stage(*, root_cause: str, route: str, issue: str, query: str) -> str:
    if root_cause == "route_required_source_gap":
        return "route_source_contract"
    if root_cause == "source_or_retrieval_gap":
        return "source_pack_or_corpus_patch"
    if root_cause == "citation_discipline_gap":
        return "citation_discipline"
    if root_cause == "answer_support_floor":
        return "claim_support_and_template_rewrite"
    if root_cause == "variant_answer_gap":
        return "variant_answer_contract"
    if root_cause == "scenario_specificity_gap":
        return "colloquial_variant_resolver"
    if root_cause in {"legal_safety_hard_fail", "refused"}:
        return "safety_gate_fix"
    return "manual_review"


def first_patch_target(*, root_cause: str, route: str, issue: str, query: str) -> str:
    if root_cause == "route_required_source_gap":
        return "route_source_contract"
    if root_cause == "source_or_retrieval_gap":
        return "source_pack_or_corpus_patch"
    if root_cause == "citation_discipline_gap":
        return "citation_gate"
    if needs_manual_adjudication(root_cause=root_cause, route=route, issue=issue, query=query):
        return "manual_adjudication"
    if root_cause == "variant_answer_gap":
        return "answer_contract"
    return recommended_stage(root_cause=root_cause, route=route, issue=issue, query=query)


def needs_manual_adjudication(*, root_cause: str, route: str, issue: str, query: str) -> bool:
    hint = fix_hint(route=route, issue=issue, root_cause=root_cause, query=query)
    return hint.startswith("Manual review")


def fix_hint(*, route: str, issue: str, root_cause: str, query: str) -> str:
    blob = f"{route} {issue} {query}".lower()
    if root_cause == "route_required_source_gap":
        return "Patch the route-required source contract or source pack so the known required authority is grounded before answer generation."
    if route == "criminal_defence_bail" or has_any_term(blob, ("bail", "surety", "adult jail", "ndps", "pmla", "mcoca")):
        return "Add criminal-procedure variant contract: subtype, forum, document checklist, date-regime, and cited authority for the exact bail/custody problem."
    if has_any_term(blob, ("deepfake", "csam", "morphed", "nude", "porn", "dpdp")):
        return "Add cyber-harm victim-first contract: takedown, cyber cell/FIR, evidence preservation, IT/BNS/POCSO/DPDP authority slots."
    if has_any_term(blob, ("daayan", "tonhi", "ojha", "tribal", "adivasi", "bania", "sarna", "ifr", "palli sabha", "land alienation")):
        return "Add colloquial caste/tribal/state-law resolver and source pack; state law must be verified when not indexed."
    if has_any_term(blob, ("wage", "epf", "esi", "asha", "scholarship", "pension", "ration", "minimum wage")):
        return "Add labour/welfare procedural ledger: authority, forum, documents, state/scheme caveat, escalation."
    if has_any_term(blob, ("vendor", "hawker", "cart", "tvc")):
        return "Add street-vendor local-action contract for seizure, demolition, licence/fine, TVC and local authority steps."
    if root_cause == "citation_discipline_gap":
        return "Require the retrieved controlling authority to be cited in the sentence that gives the legal step."
    if root_cause == "source_or_retrieval_gap":
        return "Confirm whether the source is absent from corpus or present-but-unreachable; patch source pack before answer prose."
    return "Manual review: decide whether this is a real answer gap or evaluator must-term calibration issue."


def sort_key(row: dict[str, Any]) -> tuple[int, int, str, str]:
    root_rank = {
        "legal_safety_hard_fail": 0,
        "error": 1,
        "refused": 2,
        "source_or_retrieval_gap": 3,
        "answer_support_floor": 4,
        "variant_answer_gap": 5,
        "citation_discipline_gap": 6,
        "scenario_specificity_gap": 7,
    }.get(str(row.get("root_cause")), 9)
    return (int(row.get("severity_rank") or 9), root_rank, str(row.get("harm_bucket")), str(row.get("common_issue")))


def clip(value: object, limit: int = 520) -> str:
    text = re.sub(r"\s+", " ", str(value or "")).strip()
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for row in rows:
            # JSONL requires one physical line per record. Keep non-ASCII
            # escaped so Unicode line/paragraph separators in source metadata
            # cannot split a record.
            f.write(json.dumps(row, ensure_ascii=True) + "\n")


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = [
        "eval_index",
        "product_priority",
        "root_cause",
        "variant_subtype",
        "completeness_gaps",
        "harm_bucket",
        "recommended_stage",
        "first_patch_target",
        "needs_manual_adjudication",
        "route_category",
        "common_issue",
        "relevance_verdict",
        "expected_act_hint",
        "expected_act_hit",
        "expected_act_cited_hit",
        "common_gate_failures",
        "strict_gate_failures",
        "product_failures",
        "wall_ms",
        "query",
        "fix_hint",
    ]
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            item = {field: row.get(field) for field in fields}
            item["common_gate_failures"] = ",".join(row.get("common_gate_failures") or [])
            item["strict_gate_failures"] = ",".join(row.get("strict_gate_failures") or [])
            item["product_failures"] = ",".join(row.get("product_failures") or [])
            item["completeness_gaps"] = ",".join(row.get("completeness_gaps") or [])
            writer.writerow(item)


def write_report(path: Path, rows: list[dict[str, Any]], eval_path: Path, prompts_path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    bucket_counts = Counter(row["harm_bucket"] for row in rows)
    criminal_rows = bucket_counts.get("criminal_procedure_high_risk", 0)
    family_welfare_rows = (
        bucket_counts.get("family_child_safety", 0)
        + bucket_counts.get("labour_welfare_survival", 0)
        + bucket_counts.get("cyber_sexual_privacy_high_risk", 0)
        + bucket_counts.get("caste_tribal_state_harm", 0)
    )
    business_civil_rows = (
        bucket_counts.get("business_tax_procedure", 0)
        + bucket_counts.get("property_civil_practical", 0)
        + bucket_counts.get("banking_platform_money", 0)
    )
    other_rows = len(rows) - criminal_rows - family_welfare_rows - business_civil_rows
    source_gap_rows = sum(1 for row in rows if row["root_cause"] == "source_or_retrieval_gap")
    route_gap_rows = sum(
        1 for row in rows if "route_required_source_gap" in (row.get("strict_gate_failures") or [])
    )
    common_failure_rows = sum(1 for row in rows if row.get("common_gate_failures"))
    strict_only_rows = sum(
        1 for row in rows if row.get("strict_gate_failures") and not row.get("common_gate_failures")
    )

    lines: list[str] = [
        "# Stage 1 Failure Ledger",
        "",
        f"Eval: `{eval_path}`",
        f"Prompts: `{prompts_path}`",
        f"Strict failed rows: `{len(rows)}`",
        "",
        "This ledger combines the common-user gate failures with the stricter timed-eval",
        "product-pass rule. The stricter rule also counts safe source gaps and missing",
        "route-required sources as not production-ready, even when the answer failed safely.",
        "",
        "## Executive Fix Order",
        "",
        "| order | fix bucket | why first | rows |",
        "| ---: | --- | --- | ---: |",
        f"| 1 | criminal/custody/bail procedure | highest harm if wrong, largest bucket | `{criminal_rows}` |",
        f"| 2 | family, welfare, caste/tribal, cyber harm | survival/safety issues users ask in plain language | `{family_welfare_rows}` |",
        f"| 3 | business, tax, property, money routes | source/citation precision and forum specificity | `{business_civil_rows}` |",
        f"| 4 | answer-layer polish and remaining quality gaps | convert partial/off-topic rows into useful grounded responses | `{other_rows}` |",
        "",
        "## Gate Gap Summary",
        "",
        "| gap | rows | meaning |",
        "| --- | ---: | --- |",
        f"| source or retrieval gap | `{source_gap_rows}` | controlling authority absent, unreachable, or only accepted as a safe source-gap answer |",
        f"| route-required source gap | `{route_gap_rows}` | route knew required law/source but answer could not ground it |",
        f"| common-user gate rows | `{common_failure_rows}` | rows failing actionability/relevance/scenario checks |",
        f"| strict-only rows | `{strict_only_rows}` | rows that failed safely but are still not production-ready |",
        "",
        "## Inferred Priority Counts",
        "",
        "The 500 prompt rows do not carry explicit `product_priority` metadata. These",
        "counts are inferred triage labels from route, issue, and harm terms; use them",
        "for fix ordering, not as measured eval metadata.",
        "",
        "| priority | rows |",
        "| --- | ---: |",
    ]
    for key, count in Counter(row["product_priority"] for row in rows).most_common():
        lines.append(f"| {key} | `{count}` |")

    signal_counter: Counter[str] = Counter()
    for row in rows:
        signal_counter.update(str(item) for item in (row.get("product_failures") or []))
    lines.extend(
        [
            "",
            "## Failure Signal Counts",
            "",
            "These counts are derived from each row's combined common-gate and strict-gate",
            "`product_failures`; one row can contribute multiple signals.",
            "",
            "| signal | rows |",
            "| --- | ---: |",
        ]
    )
    for key, count in signal_counter.most_common():
        lines.append(f"| {key} | `{count}` |")

    lines.extend(
        [
            "",
            "## Primary Root-Cause Counts",
            "",
            "Rows can have multiple failure signals. This table collapses each row to the",
            "highest-priority primary cause for sequencing; use Failure Signal Counts for",
            "full repair accounting.",
            "",
            "| root cause | rows | critical |",
            "| --- | ---: | ---: |",
        ]
    )
    for key, count in Counter(row["root_cause"] for row in rows).most_common():
        critical = sum(1 for row in rows if row["root_cause"] == key and row["product_priority"] == "critical")
        lines.append(f"| {key} | `{count}` | `{critical}` |")

    lines.extend(["", "## Variant Subtypes", "", "| subtype | rows | critical |", "| --- | ---: | ---: |"])
    for key, count in Counter(row["variant_subtype"] for row in rows).most_common(30):
        critical = sum(1 for row in rows if row["variant_subtype"] == key and row["product_priority"] == "critical")
        lines.append(f"| {key} | `{count}` | `{critical}` |")

    gap_counter: Counter[str] = Counter()
    for row in rows:
        gap_counter.update(str(gap) for gap in (row.get("completeness_gaps") or []))
    lines.extend(["", "## Completeness Gaps", "", "| gap | rows |", "| --- | ---: |"])
    for key, count in gap_counter.most_common(30):
        lines.append(f"| {key} | `{count}` |")

    lines.extend(["", "## Harm Buckets", "", "| harm bucket | rows | critical |", "| --- | ---: | ---: |"])
    for key, count in Counter(row["harm_bucket"] for row in rows).most_common():
        critical = sum(1 for row in rows if row["harm_bucket"] == key and row["product_priority"] == "critical")
        lines.append(f"| {key} | `{count}` | `{critical}` |")

    lines.extend(["", "## Recommended Stages", "", "| stage | rows | critical |", "| --- | ---: | ---: |"])
    for key, count in Counter(row["recommended_stage"] for row in rows).most_common():
        critical = sum(1 for row in rows if row["recommended_stage"] == key and row["product_priority"] == "critical")
        lines.append(f"| {key} | `{count}` | `{critical}` |")

    lines.extend(["", "## First Patch Targets", "", "| target | rows | critical |", "| --- | ---: | ---: |"])
    for key, count in Counter(row["first_patch_target"] for row in rows).most_common():
        critical = sum(1 for row in rows if row["first_patch_target"] == key and row["product_priority"] == "critical")
        lines.append(f"| {key} | `{count}` | `{critical}` |")

    manual_rows = [row for row in rows if row.get("needs_manual_adjudication")]
    lines.extend(["", "## Manual Adjudication Queue", "", f"Rows needing manual product/evaluator adjudication before patching: `{len(manual_rows)}`", ""])
    if manual_rows:
        lines.extend(["| issue | route | root cause | query |", "| --- | --- | --- | --- |"])
        for row in manual_rows[:30]:
            lines.append(
                "| "
                + " | ".join(md(row[key]) for key in ("common_issue", "route_category", "root_cause", "query"))
                + " |"
            )

    lines.extend(["", "## Route x Issue Clusters", "", "| route | issue | first patch target | rows | critical |", "| --- | --- | --- | ---: | ---: |"])
    cluster_counts = Counter(
        (row["route_category"], row["common_issue"], row["first_patch_target"])
        for row in rows
    )
    for (route, issue, target), count in cluster_counts.most_common(40):
        critical = sum(
            1
            for row in rows
            if row["route_category"] == route
            and row["common_issue"] == issue
            and row["first_patch_target"] == target
            and row["product_priority"] == "critical"
        )
        lines.append(f"| {md(route)} | {md(issue)} | {md(target)} | `{count}` | `{critical}` |")

    lines.extend(["", "## Top Issue x Root Cause", "", "| issue | root cause | rows | critical |", "| --- | --- | ---: | ---: |"])
    pair_counts = Counter((row["common_issue"], row["root_cause"]) for row in rows)
    for (issue, cause), count in pair_counts.most_common(35):
        critical = sum(1 for row in rows if row["common_issue"] == issue and row["root_cause"] == cause and row["product_priority"] == "critical")
        lines.append(f"| {issue} | {cause} | `{count}` | `{critical}` |")

    lines.extend(["", "## Critical Failure Samples", "", "| root cause | bucket | issue | route | query | fix hint |", "| --- | --- | --- | --- | --- | --- |"])
    for row in [item for item in rows if item["product_priority"] == "critical"][:45]:
        lines.append(
            "| "
            + " | ".join(
                md(row[key])
                for key in ("root_cause", "harm_bucket", "common_issue", "route_category", "query", "fix_hint")
            )
            + " |"
        )

    lines.extend(
        [
            "",
            "## Next Use",
            "",
            "Use this ledger as the Stage 1 source of truth before patching. A row should move from this ledger only when a focused test or eval slice proves the root cause is fixed without worsening safety, citation discipline, or latency.",
        ]
    )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def md(value: object) -> str:
    text = str(value or "").replace("|", "\\|")
    return re.sub(r"\s+", " ", text).strip()


if __name__ == "__main__":
    raise SystemExit(main())
