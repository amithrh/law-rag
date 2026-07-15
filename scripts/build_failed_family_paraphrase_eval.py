#!/usr/bin/env python3
"""Build a fresh failed-family paraphrase slice before broad 200/500 evals."""
from __future__ import annotations

import argparse
import re
from pathlib import Path
from typing import Any

from scripts.build_common_user_200 import SCENARIOS
from scripts.eval_timed_100 import jsonl_dumps


SCENARIO_IDS = (
    "bank_account_frozen",
    "loan_app_harassment_contacts",
    "upi_otp_fraud",
    "bike_theft_fir_refusal",
    "arrest_no_fir_copy",
    "false_fir_quashing",
    "domestic_violence_now",
    "nude_photo_blackmail",
    "digital_arrest_scam",
    "caste_slur_fir_refusal",
    "senior_thrown_out",
    "aadhaar_fake_loan",
    "asha_honorarium",
    "anganwadi_honorarium",
    "pf_not_deposited",
    "passport_verification",
    "builder_delay",
    "shop_sealed_municipality",
    "street_vendor_cart_removed",
    "ration_biometric_denial",
    "pension_stopped",
    "school_admission_denied",
    "tribal_land_transfer",
    "recovery_agent_threat",
    "mgnrega_wage",
)


EXTRA_SCENARIOS: list[dict[str, Any]] = [
    {
        "id": "anganwadi_honorarium",
        "expected_category": "employment_wages",
        "expected_route_any": ["employment_wages", "social_welfare_identity"],
        "expected_act_hint": "ICDS/Anganwadi honorarium order + RTI Act 2005",
        "must_include_any": ["anganwadi", "honorarium", "cdpo", "district", "rti"],
        "variants": [
            "anganwadi helper honorarium pending for 7 months cdpo not replying",
            "mini anganwadi worker payment stopped after app attendance issue",
            "anganwadi did nutrition duty but district office says no sanction",
            "icds worker salary not credited and supervisor says wait",
        ],
    }
]


TYPO_REPLACEMENTS = (
    (r"\bcomplaint\b", "complain"),
    (r"\bverification\b", "verificaton"),
    (r"\bpassport\b", "pasport"),
    (r"\bmunicipality\b", "municiple office"),
    (r"\baadhaar\b", "aadhar"),
    (r"\bharassing\b", "harrasing"),
    (r"\bdeducted\b", "dedcted"),
    (r"\bmonths\b", "mnths"),
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=Path("/tmp/law_rag_regression_20260607/failed_family_paraphrase_prompts"),
    )
    parser.add_argument("--filename", default="failed_family_paraphrase_100.jsonl")
    args = parser.parse_args()

    rows = build_rows()
    args.out_dir.mkdir(parents=True, exist_ok=True)
    out = args.out_dir / args.filename
    out.write_text("".join(jsonl_dumps(row) + "\n" for row in rows), encoding="utf-8")
    print(f"wrote {len(rows)} rows -> {out}")
    return 0


def build_rows() -> list[dict[str, Any]]:
    by_id = {str(s["id"]): s for s in [*SCENARIOS, *EXTRA_SCENARIOS]}
    missing = [scenario_id for scenario_id in SCENARIO_IDS if scenario_id not in by_id]
    if missing:
        raise ValueError(f"unknown scenario ids: {missing}")

    rows: list[dict[str, Any]] = []
    seen: set[str] = set()
    for scenario_id in SCENARIO_IDS:
        scenario = by_id[scenario_id]
        variants = scenario.get("variants") or []
        if len(variants) != 4:
            raise ValueError(f"{scenario_id} must have exactly 4 variants")
        for variant_idx, base_query in enumerate(variants, start=1):
            query = make_variant(str(base_query), scenario_id=scenario_id, variant_idx=variant_idx)
            key = normalize_query(query)
            if key in seen:
                raise ValueError(f"duplicate generated query: {query}")
            seen.add(key)
            rows.append({
                "query": query,
                "persona": "failed_family_paraphrase_20260607",
                "common_issue": scenario_id,
                "source_query": base_query,
                "prompt_variant": variant_idx,
                "product_priority": scenario.get("product_priority", "high"),
                "expected_category": scenario["expected_category"],
                "expected_act_hint": scenario["expected_act_hint"],
                "expected_route_any": scenario.get("expected_route_any", [scenario["expected_category"]]),
                "must_include_any": scenario.get("must_include_any", []),
                "must_include_all": scenario.get("must_include_all", []),
                "eval_variant": "failed_family_paraphrase_v1",
                "synthetic_note": "fresh messy failed-family paraphrase; not a real user log",
            })
    if len(rows) != 100:
        raise ValueError(f"expected 100 rows, got {len(rows)}")
    return rows


def make_variant(query: str, *, scenario_id: str, variant_idx: int) -> str:
    q = " ".join(query.strip().strip("\"'").split())
    q = q.rstrip("?.!")
    if variant_idx == 1:
        return mobile_style(q, scenario_id=scenario_id)
    if variant_idx == 2:
        return proof_context(q, scenario_id=scenario_id)
    if variant_idx == 3:
        return typo_style(q)
    return distractor_style(q)


def mobile_style(query: str, *, scenario_id: str) -> str:
    q = query.lower()
    q = q.replace("what to do", "ab kya karu")
    q = q.replace("not ", "nahi ")
    q = q.replace("police", "police/thana")
    q = q.replace("money", "paisa")
    return f"pls tell {q} need exact next step"


def proof_context(query: str, *, scenario_id: str) -> str:
    return f"urgent {query}; {proof_phrase(scenario_id)}; which office or court first"


def typo_style(query: str) -> str:
    q = query
    for pattern, replacement in TYPO_REPLACEMENTS:
        q = re.sub(pattern, replacement, q, flags=re.IGNORECASE)
    q = q.replace(",", " ,")
    q = re.sub(r"\s+", " ", q).strip()
    return f"{q} pls tell forum and papers"


def distractor_style(query: str) -> str:
    q = query
    q = re.sub(r"\bFIR\b", "FIR or online complaint", q, flags=re.IGNORECASE)
    q = re.sub(r"\bcourt\b", "court or govt office", q, flags=re.IGNORECASE)
    q = re.sub(r"\bcomplaint\b", "legal notice/complaint", q, flags=re.IGNORECASE)
    return f"{q}; family says ignore but i am scared, safe legal route?"


def proof_phrase(scenario_id: str) -> str:
    if any(term in scenario_id for term in ("bank", "loan", "upi", "aadhaar", "pf")):
        return "screenshots, bank sms and account statement are with me"
    if any(term in scenario_id for term in ("fir", "arrest", "violence", "blackmail", "digital", "caste")):
        return "screenshots/witness names and phone numbers are with me"
    if any(term in scenario_id for term in ("asha", "anganwadi", "mgnrega", "salary")):
        return "attendance proof and passbook entries are with me"
    if any(term in scenario_id for term in ("passport", "shop", "vendor", "builder", "school")):
        return "application number, notice or messages are with me"
    if "tribal" in scenario_id:
        return "land papers and village witness names are with me"
    return "some papers are with me but no written reply"


def normalize_query(query: str) -> str:
    return re.sub(r"\s+", " ", query.strip().lower())


if __name__ == "__main__":
    raise SystemExit(main())
