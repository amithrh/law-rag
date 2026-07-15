from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

from scripts.build_common_user_200 import (
    EXTRA_FOURTH_VARIANT_SCENARIOS,
    SCENARIOS,
    build_rows,
)
from scripts.build_human_messy_eval import build as build_human_messy_eval
from scripts.build_human_messy_eval import load_excluded_exact_queries, load_excluded_source_queries
from scripts.eval_common_user_gate import (
    GateConfig,
    _has_meaningful_action_pack,
    evaluate_gate,
    must_terms_ok,
    product_failures,
    safe_source_gap_ok,
    summarize,
    write_failures_jsonl,
)
from scripts.eval_source_gaps import (
    expected_authority_gap_kind,
    route_required_source_gap_classifications,
)
from scripts.legal_safety_eval import analyze_safety_row


def test_common_user_200_sampling_is_intentional_and_marks_critical_rows():
    rows = build_rows(limit=200)

    assert len(rows) == 200
    assert {row["common_issue"] for row in rows} == {scenario["id"] for scenario in SCENARIOS}
    assert Counter(row["prompt_variant"] for row in rows) == {
        1: len(SCENARIOS),
        2: len(SCENARIOS),
        3: len(SCENARIOS),
        4: len(EXTRA_FOURTH_VARIANT_SCENARIOS),
    }
    assert sum(1 for row in rows if row["product_priority"] == "critical") >= 30


def test_must_terms_do_not_pass_from_hidden_source_metadata():
    prompt = {"must_include_any": ["rbi"], "must_include_all": []}
    row = {
        "answer_text": "File a written complaint and keep proof.",
        "route_label": "General legal information",
        "route_required_sources": [],
        "route_forums": [],
        "route_missing_facts": [],
        "action_pack_next_steps": [],
        "top_sources": [{"title": "Reserve Bank Integrated Ombudsman Scheme 2021"}],
        "expected_act_keys": ["Banking Ombudsman"],
    }

    assert must_terms_ok(row, prompt) is False

    row["route_required_sources"] = ["RBI Ombudsman route"]
    assert must_terms_ok(row, prompt) is False

    row["answer_text"] = "File a written RBI Ombudsman complaint and keep proof."
    assert must_terms_ok(row, prompt) is True


def test_must_terms_normalize_hyphenated_statute_names():
    prompt = {"must_include_any": ["income tax"], "must_include_all": []}
    row = {"answer_text": "Keep Income-tax Act records and file the appeal in time."}

    assert must_terms_ok(row, prompt) is True


def test_human_messy_must_terms_use_specific_issue_not_broad_family_bucket():
    from scripts.build_human_messy_eval import must_include_terms

    assert must_include_terms(
        category="family",
        query="got married 22 he is 29 family says illegal what is age legal in india",
        act_hint="Prohibition of Child Marriage Act 2006 + Special Marriage Act 1954",
    ) == ["legal age", "21", "18", "child marriage", "consent"]
    assert must_include_terms(
        category="mulaqat_visit",
        query="son in tihar can he get books from family during mulaqat prison rules",
        act_hint="Delhi Prison Rules 2018 + Prison Act 1894",
    ) == ["prison", "jail", "mulaqat", "books", "superintendent"]
    assert "succession" in must_include_terms(
        category="inheritance",
        query="christian widow can my stepchildren claim share in husband self acquired property",
        act_hint="Indian Succession Act 1925 s.33A",
    )
    assert must_include_terms(
        category="employment",
        query="company is asking me to serve 90 day notice but offer letter says 60 days",
        act_hint="Indian Contract Act",
    ) == ["notice period", "offer letter", "60 days", "90 days", "hr", "contract"]


def test_legal_safety_allows_inlaw_jewellery_as_family_domestic_route():
    row = {
        "query": "pls tell daughter in law took my jewellery worth 12 lakh saying for safe keeping not returning agra need lawyer or police",
        "expected_category": "elder_fraud",
        "expected_act_hint": "BNS 2023 s.316 criminal breach of trust + DV Act 2005",
        "route_category": "family_domestic",
        "route_forums": [
            "Protection Officer or Magistrate under PWDVA",
            "police station for breach of trust/threat facts",
            "District Legal Services Authority",
        ],
        "answer_text": (
            "The PWDVA economic-abuse source and BNS criminal-breach-of-trust "
            "source are separate tracks. Preserve entrustment messages and "
            "written demands before choosing PWDVA or police complaint route."
        ),
        "sentence_count": 2,
    }

    safety = analyze_safety_row(row)
    assert safety["hard_fail"] is False


def test_legal_safety_allows_marriage_surname_identity_route():
    row = {
        "query": "i am confused how to legally change my surname after marriage do i need to publish in gazette pls guide",
        "expected_category": "family",
        "expected_act_hint": "Gazette name change publication process after marriage",
        "route_category": "social_welfare_identity",
        "route_forums": [
            "state gazette or government press office",
            "Aadhaar/PAN/passport record office where relevant",
            "District Legal Services Authority",
        ],
        "answer_text": (
            "The Department of Publication source is the Gazette route for "
            "identity-record name change. It is not by itself a marriage-law "
            "rule saying court permission is required."
        ),
        "sentence_count": 2,
    }

    safety = analyze_safety_row(row)
    assert safety["hard_fail"] is False


def test_common_user_action_pack_requires_visible_route_completeness():
    shallow = {
        "action_pack_id": "banking_dispute",
        "action_pack_next_steps": ["Raise a written complaint."],
        "route_forums": [],
        "route_missing_facts": [],
        "route_required_sources": [],
    }
    complete = {
        **shallow,
        "route_forums": ["bank branch", "RBI Ombudsman"],
        "route_missing_facts": ["transaction date", "complaint number"],
        "route_required_sources": ["RBI Ombudsman Scheme"],
    }

    assert _has_meaningful_action_pack(shallow) is False
    assert _has_meaningful_action_pack(complete) is True


def test_product_gate_rejects_unknown_citation_indices():
    row = {
        "query": "bank deducted money wrongly",
        "route_category": "banking_credit_dispute",
        "relevance_verdict": "ok",
        "source_count": 1,
        "expected_act_hit": True,
        "expected_act_cited_hit": True,
        "first_cited_is_actionable": True,
        "judgment_before_actionable_source": False,
        "action_pack_id": "banking_dispute",
        "action_pack_next_steps": ["Raise a written complaint."],
        "route_forums": ["bank", "RBI Ombudsman"],
        "route_missing_facts": ["transaction ID"],
        "route_required_sources": ["RBI Ombudsman Scheme"],
        "answer_quality_flags": ["unknown_citation_indices"],
        "unknown_citation_count": 1,
        "suppressed_count": 0,
    }

    failures = product_failures(row, {}, {"hard_fail": False})

    assert "unknown_citation_indices" in failures


def test_product_gate_rejects_missing_route_required_sources():
    row = {
        "query": "cheque bounced how to file complaint",
        "route_category": "cheque_bounce",
        "relevance_verdict": "ok",
        "source_count": 2,
        "expected_act_hit": True,
        "expected_act_cited_hit": True,
        "first_cited_is_actionable": True,
        "judgment_before_actionable_source": False,
        "action_pack_id": "cheque_bounce",
        "action_pack_next_steps": ["Send notice and prepare complaint papers."],
        "route_forums": ["Magistrate"],
        "route_missing_facts": ["cheque return memo date"],
        "route_required_sources": ["NI Act", "BNSS/CrPC complaint procedure"],
        "route_required_sources_missing": ["BNSS/CrPC complaint procedure"],
        "answer_quality_flags": [],
        "unknown_citation_count": 0,
        "suppressed_count": 0,
        "answer_text": "Send the cheque notice and keep the return memo.",
    }

    failures = product_failures(row, {}, {"hard_fail": False})

    assert "route_required_source_gap" in failures


def test_failure_jsonl_includes_priority_category_and_route(tmp_path: Path):
    out = tmp_path / "failures.jsonl"
    write_failures_jsonl(
        out,
        [
            {
                "query": "minor deepfake nude video shared",
                "common_issue": "deepfake_minor",
                "product_priority": "critical",
                "expected_category": "deepfake_minor",
                "route_category": "cyber_fraud_or_harassment",
                "product_failures": ["expected_act_not_cited"],
                "answer_text": "Use the cyber route.",
            }
        ],
    )

    row = json.loads(out.read_text(encoding="utf-8"))
    assert row["product_priority"] == "critical"
    assert row["expected_category"] == "deepfake_minor"
    assert row["route"] == "cyber_fraud_or_harassment"


def test_product_gate_rejects_wrong_workflow_and_judgment_first_canary_failures():
    row = {
        "query": "Bank deducted money wrongly and customer care not helping.",
        "route_category": "banking_credit_dispute",
        "relevance_verdict": "ok",
        "source_count": 2,
        "expected_act_hit": True,
        "expected_act_cited_hit": True,
        "first_cited_is_actionable": True,
        "first_cited_source_type": "sc_judgment",
        "first_cited_source_title": "HEMIBEN LADHABHAI BHANDERI versus SAURASHTA GRAMIN BANK & ANR",
        "judgment_before_actionable_source": False,
        "workflow_id": None,
        "workflow_answer_owner": "llm",
        "action_pack_id": "banking_credit_dispute",
        "action_pack_next_steps": ["Raise a written complaint."],
        "route_forums": ["bank", "RBI Ombudsman"],
        "route_missing_facts": ["transaction ID"],
        "route_required_sources": ["RBI Ombudsman Scheme"],
        "answer_quality_flags": [],
        "suppressed_count": 0,
        "answer_text": "File a consumer complaint in court for service deficiency.",
    }
    prompt = {
        "expected_route_any": ["banking_credit_dispute"],
        "required_workflow_id_any": ["wrong_bank_debit", "bank_wrong_debit"],
        "required_answer_owner_any": ["authority_graph", "common_workflow_contracts"],
        "forbidden_first_cited_source_type_any": ["sc_judgment", "hc_judgment"],
        "forbidden_first_cited_title_any": ["hemiben"],
        "forbidden_answer_any": ["file a consumer complaint in court"],
        "must_include_all": ["rbi"],
    }

    failures = product_failures(row, prompt, {"hard_fail": False})

    assert "wrong_workflow" in failures
    assert "wrong_answer_owner" in failures
    assert "forbidden_first_cited_source_type" in failures
    assert "forbidden_first_cited_title" in failures
    assert "forbidden_answer_term" in failures
    assert "missing_scenario_terms" in failures


def test_product_gate_rejects_forbidden_route_and_workflow_negative_control():
    row = {
        "query": "My EMI is late and lender sent normal reminder SMS is that harassment?",
        "route_category": "banking_credit_dispute",
        "relevance_verdict": "ok",
        "source_count": 1,
        "expected_act_hit": True,
        "expected_act_cited_hit": True,
        "first_cited_is_actionable": True,
        "judgment_before_actionable_source": False,
        "workflow_id": "loan_app_harassment",
        "workflow_answer_owner": "common_workflow_contracts",
        "action_pack_id": "banking_credit_dispute",
        "action_pack_next_steps": ["Raise a written complaint."],
        "route_forums": ["bank", "RBI Ombudsman"],
        "route_missing_facts": ["loan account"],
        "route_required_sources": ["RBI Ombudsman Scheme"],
        "answer_quality_flags": [],
        "suppressed_count": 0,
        "answer_text": "Treat this as loan app cyber blackmail and go to 1930 first.",
    }
    prompt = {
        "expected_route_any": ["banking_credit_dispute"],
        "forbidden_workflow_id_any": ["loan_app_harassment"],
        "forbidden_answer_any": ["cyber blackmail", "1930 first"],
        "must_include_any": ["emi", "lender", "rbi"],
    }

    failures = product_failures(row, prompt, {"hard_fail": False})

    assert "forbidden_workflow" in failures
    assert "forbidden_answer_term" in failures


def test_locked_real_user_canary_has_independent_labels():
    fixture = (
        Path(__file__).resolve().parents[3]
        / "data/eval_canary_real_user_20260607/canary_real_user_20260607.jsonl"
    )
    rows = [
        json.loads(line)
        for line in fixture.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]

    assert len(rows) >= 20
    assert {row["eval_split"] for row in rows} == {"locked_real_user_canary"}
    assert {row["label_source"] for row in rows} == {"manual_independent"}
    assert all(row.get("expected_route_any") for row in rows)
    assert all(row.get("product_priority") in {"critical", "high", "medium", "low"} for row in rows)
    assert {
        "bank_wrong_debit",
        "loan_app_harassment",
        "pan_aadhaar_mismatch",
        "heir_property_sale",
        "marital_intimacy",
    }.issubset({row.get("common_issue") for row in rows})


def test_safe_source_gap_is_narrow_and_does_not_fail_expected_act_when_explicit():
    row = {
        "query": "can u tell they say i am tonhi after child died in village false case filed chhattisgarh what can i do",
        "route_category": "criminal_defence_bail",
        "answer_text": (
            "I do not have the exact Chhattisgarh Tonahi Pratadna Nivaran Act source "
            "in the retrieved index, so do not treat Assam witch-law text as the "
            "controlling State Act [1]. Use BNSS only for arrest or bail steps [1]."
        ),
        "expected_act_hint": "Chhattisgarh Tonahi Pratadna Nivaran Act 2005",
        "expected_act_hit": False,
        "expected_act_cited_hit": False,
        "source_count": 1,
        "first_cited_is_actionable": True,
        "judgment_before_actionable_source": False,
        "relevance_verdict": "ok",
        "action_pack_id": "criminal_defence_bail",
        "action_pack_next_steps": ["Collect FIR and bail papers."],
        "route_forums": ["Special Court", "DLSA"],
        "route_missing_facts": ["FIR sections"],
        "route_required_sources": ["State witch-hunting law"],
        "answer_quality_flags": [],
        "suppressed_count": 0,
    }

    assert safe_source_gap_ok(row, {}) is True
    failures = product_failures(row, {}, {"hard_fail": False})
    assert "expected_act_missing" not in failures
    assert "expected_act_not_cited" not in failures

    vague = {**row, "answer_text": "I could not find good sources, ask a lawyer."}
    assert safe_source_gap_ok(vague, {}) is False


def test_safe_source_gap_blocks_production_clean_gate_even_when_product_safe():
    row = {
        "query": "sir they arrested me for cow transport saying I am smuggling but I was taking my own buffalo to mandi",
        "route_category": "criminal_defence_bail",
        "answer_text": (
            "I do not have the exact state Cattle Preservation Act source in the retrieved index, "
            "so do not treat generic bail text as the controlling State Act [1]."
        ),
        "expected_act_hint": "state Cattle Preservation Act",
        "expected_act_hit": False,
        "expected_act_cited_hit": False,
        "source_count": 1,
        "first_cited_is_actionable": True,
        "judgment_before_actionable_source": False,
        "relevance_verdict": "ok",
        "action_pack_id": "criminal_defence_bail",
        "action_pack_next_steps": ["Collect FIR and seized animal papers."],
        "route_forums": ["criminal court", "DLSA"],
        "route_missing_facts": ["FIR sections"],
        "route_required_sources": ["state cattle preservation source"],
        "route_required_sources_missing": ["state cattle preservation source"],
        "answer_quality_flags": [],
        "suppressed_count": 0,
        "product_pass": True,
        "product_failures": [],
        "product_priority": "critical",
        "safe_source_gap": True,
        "safe_source_gap_kind": "state_or_local_authority_gap",
        "route_match": True,
        "must_terms_ok": True,
        "bad_route_fallback": False,
        "legal_safety": {"hard_fail": False},
        "wall_ms": 1000,
        "timing": {"total_ms": 1000, "retrieval_ms": 100, "llm_stream_ms": 0, "verification_ms": 50},
        "workflow_answer_owner": "legacy_grounded_template",
        "workflow_answer_mode": "legacy",
        "workflow_shadowed_by_legacy": False,
    }

    metrics = summarize([row])
    failures = evaluate_gate(metrics, GateConfig(min_rows=1, min_critical_rows=1))

    assert expected_authority_gap_kind(row, {}) == "state_or_local_authority_gap"
    assert metrics["product_pass_pct"] == 100.0
    assert metrics["expected_act_cited_pct"] == 100.0
    assert metrics["expected_act_cited_strict_pct"] == 0.0
    assert "safe_source_gaps 1 > 0" in failures
    assert "route_source_gap_rows 1 > 0" in failures


def test_common_user_gate_fails_visible_source_gap_metric_even_if_product_pass_precomputed():
    row = {
        "product_pass": True,
        "product_failures": [],
        "product_priority": "critical",
        "expected_act_cited_hit": True,
        "first_cited_is_actionable": True,
        "must_terms_ok": True,
        "bad_route_fallback": False,
        "legal_safety": {"hard_fail": False},
        "route_category": "police_fir",
        "route_match": True,
        "safe_source_gap": False,
        "source_gap_visible": True,
        "route_required_sources_missing": [],
        "wall_ms": 1000,
        "timing": {"total_ms": 1000, "retrieval_ms": 100, "llm_stream_ms": 0, "verification_ms": 50},
        "workflow_answer_owner": "common_workflow_contracts",
        "workflow_answer_mode": "primary",
        "workflow_shadowed_by_legacy": False,
    }

    metrics = summarize([row])
    failures = evaluate_gate(metrics, GateConfig(min_rows=1, min_critical_rows=1))

    assert metrics["visible_source_gap_rows"] == 1
    assert "visible_source_gap_rows 1 > 0" in failures


def test_common_user_gate_checks_llm_path_latency_separately():
    row = {
        "product_pass": True,
        "product_failures": [],
        "product_priority": "critical",
        "expected_act_cited_hit": True,
        "first_cited_is_actionable": True,
        "must_terms_ok": True,
        "bad_route_fallback": False,
        "legal_safety": {"hard_fail": False},
        "route_category": "tax_gst_compliance",
        "route_match": True,
        "safe_source_gap": False,
        "route_required_sources_missing": [],
        "wall_ms": 21_000,
        "timing": {
            "total_ms": 21_000,
            "retrieval_ms": 5_000,
            "llm_stream_ms": 15_000,
            "verification_ms": 100,
        },
        "workflow_answer_owner": "llm",
        "workflow_answer_mode": "llm",
        "workflow_shadowed_by_legacy": False,
    }

    metrics = summarize([row])
    failures = evaluate_gate(metrics, GateConfig(min_rows=1, min_critical_rows=1, max_p90_ms=30_000))

    assert metrics["llm_path_rows"] == 1
    assert metrics["llm_path_p90_ms"] == 21_000
    assert "llm_path_p90_ms 21000.0 > 20000.0" in failures


def test_route_source_gap_classification_covers_common_gap_families():
    row = {
        "query": "customs reclassified my import wire harness higher duty svb opened",
        "route_category": "tax_gst_compliance",
        "route_required_sources_missing": [
            "Customs Act 1962 for import/export, ICEGATE, duty, valuation, SVB, drawback, or classification issues",
            "Constitution of India Article 226 for High Court writ jurisdiction",
            "Right to Information Act 2005 for written cancellation/status reasons and first appeal",
        ],
    }

    kinds = [item["kind"] for item in route_required_source_gap_classifications(row)]

    assert kinds == [
        "national_tax_source_gap",
        "constitutional_authority_gap",
        "supporting_records_gap",
    ]


def test_route_source_gap_classification_keeps_criminal_dual_regime_visible():
    row = {
        "query": "brother arrested six months no chargesheet can bail be filed",
        "route_category": "criminal_defence_bail",
        "route_required_sources_missing": [
            "BNSS 2023 / CrPC 1973 bail provisions based on incident date",
        ],
    }

    kinds = [item["kind"] for item in route_required_source_gap_classifications(row)]

    assert kinds == ["national_criminal_source_gap"]


def test_common_user_summary_tracks_missing_latency_and_timing():
    row = {
        "product_pass": True,
        "product_priority": "critical",
        "workflow_answer_owner": "common_workflow_contracts",
        "workflow_answer_mode": "primary",
        "workflow_shadowed_by_legacy": False,
        "expected_act_cited_hit": True,
        "first_cited_is_actionable": True,
        "must_terms_ok": True,
        "bad_route_fallback": False,
        "legal_safety": {"hard_fail": False},
        "route_category": "banking_credit_dispute",
        "product_failures": [],
        "wall_ms": None,
        "timing": {},
    }

    metrics = summarize([row])

    assert metrics["wall_latency_coverage_pct"] == 0.0
    assert metrics["timing_telemetry_pct"] == 0.0
    assert metrics["answer_owner_counts"] == {"common_workflow_contracts": 1}
    assert metrics["answer_mode_counts"] == {"primary": 1}
    assert metrics["workflow_shadowed_by_legacy"] == 0
    assert metrics["answer_owner_metrics"]["common_workflow_contracts"]["product_pass_pct"] == 100.0


def test_common_user_summary_breaks_failures_down_by_answer_owner():
    rows = [
        {
            "product_pass": False,
            "product_failures": ["missing_scenario_terms"],
            "product_priority": "high",
            "expected_act_cited_hit": True,
            "first_cited_is_actionable": True,
            "must_terms_ok": False,
            "bad_route_fallback": False,
            "legal_safety": {"hard_fail": False},
            "route_category": "banking_credit_dispute",
            "wall_ms": 1000,
            "timing": {"total_ms": 1000, "retrieval_ms": 100, "llm_stream_ms": 0, "verification_ms": 50},
            "workflow_answer_owner": "legacy_grounded_template",
            "workflow_answer_mode": "legacy",
            "workflow_shadowed_by_legacy": True,
        },
        {
            "product_pass": True,
            "product_failures": [],
            "product_priority": "high",
            "expected_act_cited_hit": True,
            "first_cited_is_actionable": True,
            "must_terms_ok": True,
            "bad_route_fallback": False,
            "legal_safety": {"hard_fail": False},
            "route_category": "banking_credit_dispute",
            "wall_ms": 900,
            "timing": {"total_ms": 900, "retrieval_ms": 100, "llm_stream_ms": 0, "verification_ms": 50},
            "workflow_answer_owner": "common_workflow_contracts",
            "workflow_answer_mode": "primary",
            "workflow_shadowed_by_legacy": False,
        },
    ]

    metrics = summarize(rows)

    assert metrics["answer_owner_counts"] == {
        "legacy_grounded_template": 1,
        "common_workflow_contracts": 1,
    }
    assert metrics["answer_mode_counts"] == {"legacy": 1, "primary": 1}
    assert metrics["workflow_shadowed_by_legacy"] == 1
    assert metrics["answer_owner_metrics"]["legacy_grounded_template"]["product_pass_pct"] == 0.0
    assert metrics["answer_owner_metrics"]["common_workflow_contracts"]["product_pass_pct"] == 100.0


def test_human_messy_eval_carries_product_gate_metadata(tmp_path):
    source = tmp_path / "source"
    source.mkdir()
    (source / "procedural.jsonl").write_text(
        "\n".join([
            json.dumps({
                "query": "police picked my son at night and no FIR copy was given",
                "expected_category": "arrest_custody_safeguard",
                "expected_act_hint": "Article 22 Constitution + BNSS 2023 section 173",
            }),
            json.dumps({
                "query": "Bank deducted money wrongly and customer care is not helping",
                "expected_category": "finance",
                "expected_act_hint": "Banking Ombudsman + Consumer Protection Act 2019",
            }),
        ])
        + "\n",
        encoding="utf-8",
    )

    out_path = build_human_messy_eval(source, tmp_path / "out", limit=2, seed=7)
    rows = [json.loads(line) for line in out_path.read_text(encoding="utf-8").splitlines()]

    assert out_path.name == "human_messy_2.jsonl"
    assert all(row["base_id"].startswith("hm2-procedural-") for row in rows)
    assert all(row["common_issue"] for row in rows)
    assert all(row["expected_route_any"] for row in rows)
    assert all(row["must_include_any"] for row in rows)
    assert rows[0]["product_priority"] == "critical"
    assert "arrest_custody_safeguard" in rows[0]["expected_route_any"]
    assert {"rbi", "ombudsman", "bank"} & set(rows[1]["must_include_any"])


def test_human_messy_eval_can_exclude_burned_prompt_source_queries(tmp_path):
    source = tmp_path / "source"
    source.mkdir()
    (source / "procedural.jsonl").write_text(
        "\n".join([
            json.dumps({
                "query": "bank deducted money wrongly and customer care is not helping",
                "expected_category": "finance",
                "expected_act_hint": "Banking Ombudsman + Consumer Protection Act 2019",
            }),
            json.dumps({
                "query": "tenant not vacating house and not paying rent",
                "expected_category": "property",
                "expected_act_hint": "Transfer of Property Act",
            }),
        ])
        + "\n",
        encoding="utf-8",
    )
    burned = tmp_path / "burned"
    burned.mkdir()
    (burned / "old.jsonl").write_text(
        json.dumps({
            "query": "messy rewrite not relevant for exclusion",
            "source_query": "bank deducted money wrongly and customer care is not helping",
        })
        + "\n",
        encoding="utf-8",
    )

    out_path = build_human_messy_eval(
        source,
        tmp_path / "out",
        limit=1,
        seed=11,
        exclude_prompts=[burned],
    )
    rows = [json.loads(line) for line in out_path.read_text(encoding="utf-8").splitlines()]

    assert rows[0]["source_query"] == "tenant not vacating house and not paying rent"
    assert rows[0]["excluded_prompt_sources"] == [str(burned)]
    assert load_excluded_source_queries([burned]) == {
        "bank deducted money wrongly and customer care is not helping"
    }


def test_human_messy_eval_can_exclude_exact_generated_prompt_text(tmp_path):
    source = tmp_path / "source"
    source.mkdir()
    source_query = "bank deducted money wrongly and customer care is not helping"
    (source / "procedural.jsonl").write_text(
        json.dumps({
            "query": source_query,
            "expected_category": "finance",
            "expected_act_hint": "Banking Ombudsman + Consumer Protection Act 2019",
        })
        + "\n",
        encoding="utf-8",
    )

    first = build_human_messy_eval(source, tmp_path / "first", limit=1, seed=19)
    first_query = json.loads(first.read_text(encoding="utf-8").splitlines()[0])["query"]

    second = build_human_messy_eval(
        source,
        tmp_path / "second",
        limit=1,
        seed=19,
        exclude_exact_prompts=[first],
    )
    second_row = json.loads(second.read_text(encoding="utf-8").splitlines()[0])

    assert second_row["source_query"] == source_query
    assert second_row["query"] != first_query
    assert second_row["excluded_exact_prompt_sources"] == [str(first)]
    assert load_excluded_exact_queries([first]) == {first_query.lower()}
