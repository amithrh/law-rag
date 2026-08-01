from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.eval_timed_100 import (
    answer_quality_flags,
    classify_required_source_requirement,
    citation_integrity_metrics,
    cited_source_order_metrics,
    expected_act_cited_hit,
    expected_act_hit,
    expected_act_keys,
    expected_procedure_anchor_coverage,
    flatten_row,
    internal_service_error_reason,
    jsonl_dumps,
    load_eval_rows,
    matter_plan_authority_coverage,
    matter_plan_contract_status,
    matter_plan_required_for_eval,
    product_pass,
    required_source_coverage,
    safe_source_gap_handoff_for_eval,
    stream_answer,
    _rows_summary,
    write_report,
)


def matter_plan_payload(*, authority_id: str = "authority_consumer_section_35") -> dict:
    return {
        "schema_version": 2,
        "plan_id": "matter_plan_v2_consumer_test",
        "primary_issue": "consumer",
        "primary_label": "Consumer complaint / service deficiency",
        "confidence": 0.91,
        "user_role": "consumer",
        "jurisdiction": {
            "state": None,
            "city": None,
            "forum_mentioned": None,
            "needs_state": False,
        },
        "incident_date_status": "not_required",
        "legal_regime": None,
        "case_stage": "pre_filing",
        "desired_outcome": "refund",
        "urgency": "medium",
        "secondary_issues": [],
        "required_facts": ["invoice/order ID"],
        "authority_ledger": [{
            "source": "Consumer Protection Act 2019 Section 35",
            "authority_id": authority_id,
            "identity_status": "canonical",
            "canonical_name": "Consumer Protection Act 2019 Section 35",
            "act": "Consumer Protection Act 2019",
            "section": "35",
            "source_pack_id": "consumer_protection_section_35",
            "required_anchor_patterns": ["sec-35"],
            "claim_type": "legal_basis",
            "priority": "must_cite",
            "must_cite": True,
            "conditional": False,
            "note": None,
        }],
        "retrieval_sources": [{
            "source_pack_id": "consumer_protection_section_35",
            "title_patterns": ["Consumer Protection Act 2019"],
            "search_query": "consumer complaint section 35",
            "doc_ids": [],
            "anchor_patterns": ["sec-35"],
            "source_types": ["bare_act"],
            "priority": 1.0,
        }],
        "forums": ["District Consumer Commission"],
        "remedies": ["refund"],
        "deadlines": [],
        "documents": ["invoice"],
        "action_pack_id": "consumer_complaint",
        "action_pack_title": "Consumer complaint",
        "next_steps": ["Send a written complaint."],
        "portals": [],
        "escalation": [],
        "cautions": [],
        "safety_flags": [],
        "answer_policy": {
            "required_primary_owner": "server_template_or_verified_llm",
            "fallback_owner": "source_gap_handoff",
            "allow_freeform_llm": True,
            "requires_reviewed_contract": False,
        },
    }


@pytest.mark.needs_eval_data
def test_expected_act_aliases_cover_eval_corpus_annotations():
    rows = []
    for path in sorted(Path("data/eval_500").glob("*.jsonl")):
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                rows.append(json.loads(line))

    annotated = [row for row in rows if row.get("expected_act_hint")]
    scored = [row for row in annotated if expected_act_keys(row.get("expected_act_hint"))]
    unscored = [row for row in annotated if not expected_act_keys(row.get("expected_act_hint"))]

    assert len(annotated) >= 490
    assert [row["expected_act_hint"] for row in unscored] == [
        "Prem Shankar Shukla v Delhi Admin 1980 + Citizen for Democracy v State of Assam 1995",
    ]
    assert len(scored) / len(rows) >= 0.95


def test_load_eval_rows_keeps_unicode_next_line_inside_json_string(tmp_path):
    queries_dir = tmp_path / "queries"
    queries_dir.mkdir()
    row = {
        "query": "section marker sec-88-\u0085 anchor should stay in one record",
        "expected_category": "court_procedure",
        "expected_act_hint": "CPC",
    }
    (queries_dir / "procedural.jsonl").write_text(
        json.dumps(row, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    rows = load_eval_rows(queries_dir, limit=10, seed=1)

    assert len(rows) == 1
    assert rows[0]["persona"] == "procedural"
    assert rows[0]["query"] == "section marker sec-88-\u0085 anchor should stay in one record"


def test_jsonl_dumps_escapes_unicode_line_separators():
    dumped = jsonl_dumps({
        "query": "section marker sec-88-\u0085 and line\u2028paragraph\u2029",
    })

    assert "\u0085" not in dumped
    assert "\u2028" not in dumped
    assert "\u2029" not in dumped
    assert "\\u0085" in dumped
    assert "\\u2028" in dumped
    assert "\\u2029" in dumped


def test_stream_answer_records_canonical_matter_plan_event(monkeypatch):
    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def __iter__(self):
            return iter([
                b"event: matter_plan\n",
                b'data: {"schema_version": 2, "plan_id": "matter_plan_v2_test"}\n',
                b"\n",
            ])

    monkeypatch.setattr(
        "scripts.eval_timed_100.urllib.request.urlopen",
        lambda *args, **kwargs: FakeResponse(),
    )

    observed = stream_answer("http://127.0.0.1:1", "test legal query", timeout_s=1)

    assert observed["events"]["matter_plan"] == 1
    assert observed["matter_plan"] == {
        "schema_version": 2,
        "plan_id": "matter_plan_v2_test",
    }


def test_expected_act_aliases_cover_human_like_mixed_hints():
    hints = {
        "MSMED Act 2006 s.15 s.16 s.17 + MSME Samadhan": "MSMED Act",
        "Water (Prevention and Control of Pollution) Act 1974": "Water Act",
        "ed tech company director received PMLA summons": "PMLA",
        "Rajasthan Shops & Commercial Establishments Act": "Shops and Establishments Act",
        "Article 21 handcuffing safeguards + Prem Shankar Shukla v Delhi Admin 1980": "Article 21",
        "AP Rights in Land and Pattadar Pass Books Act 1971 / state Record of Rights Act": "AP Rights in Land and Pattadar Pass Books Act",
    }

    for hint, expected in hints.items():
        assert expected in expected_act_keys(hint)


def test_generic_tribal_land_hint_does_not_require_unknown_state_transfer_act():
    hint = "Scheduled Areas Land Transfer Regulation + PESA + Constitution"

    generic = expected_act_keys(
        hint,
        "urgent tribal family land transferred by moneylender using blank paper; land papers and village witness names are with me; which office or court first",
    )
    assert generic == ["Constitution"]

    jharkhand = expected_act_keys(
        hint,
        "tribal land in Jharkhand transferred to moneylender using blank paper which office first",
    )
    assert "Scheduled Areas Land Transfer Regulation" in jharkhand
    assert "PESA" not in jharkhand

    scheduled_area = expected_act_keys(
        hint,
        "agency area tribal land transferred using blank paper without gram sabha what forum first",
    )
    assert scheduled_area == ["Constitution", "PESA"]

    ui_hint = "Schedule V Constitution / state Scheduled Areas Land Transfer Regulation"
    ui_generic = expected_act_keys(
        ui_hint,
        "sir tribal land sold to non tribal by uncle without our consent is it legal where to go",
    )
    assert ui_generic == ["Constitution"]


def test_expected_act_hit_requires_all_recognized_required_acts():
    keys = expected_act_keys("POCSO + JJ Act")

    assert expected_act_hit(
        keys,
        [{"title": "Protection of Children from Sexual Offences Act 2012"}],
        [],
    ) is False
    assert expected_act_hit(
        keys,
        [
            {"title": "Protection of Children from Sexual Offences Act 2012"},
            {"title": "Juvenile Justice (Care and Protection of Children) Act 2015"},
        ],
        [],
    ) is True


def test_expected_act_cited_hit_requires_used_citation_not_just_passage_presence():
    keys = expected_act_keys("BNS")
    sources = [
        {"index": 1, "title": "Protection of Women from Domestic Violence Act 2005"},
        {"index": 2, "title": "Bharatiya Nyaya Sanhita 2023"},
    ]

    assert expected_act_hit(keys, sources, []) is True
    assert expected_act_cited_hit(
        keys,
        sources,
        [],
        [{"text": "Use the domestic-violence remedy [1].", "status": "ok"}],
    ) is False
    assert expected_act_cited_hit(
        keys,
        sources,
        [],
        [{"text": "Check the criminal breach-of-trust provision [2].", "status": "ok"}],
    ) is True


def test_citation_integrity_flags_unknown_indices():
    metrics = citation_integrity_metrics(
        [{"index": 1, "title": "Consumer Protection Act 2019"}],
        [],
        [{"text": "Use the consumer route [1]. Do not cite a missing source [9]."}],
    )

    assert metrics["cited_indices"] == [1, 9]
    assert metrics["known_source_indices"] == [1]
    assert metrics["unknown_citation_indices"] == [9]
    assert metrics["citation_integrity_ok"] is False


def test_visible_source_gap_is_quality_flag_and_product_failure():
    row = {
        "answer_text": "**What you can do next**\n- Ask for the exact source [1].",
        "source_gap_visible": True,
        "refused": False,
        "error": None,
        "relevance_verdict": "ok",
        "legal_safety": {"hard_fail": False},
        "expected_act_cited_hit": True,
        "unknown_citation_count": 0,
        "route_required_sources_missing": [],
        "ok_sentences": 1,
    }

    assert "visible_source_gap" in answer_quality_flags(row)
    assert product_pass(row) is False


def test_source_gap_handoff_is_always_a_non_answer():
    row = {
        "answer_text": "**What you can do next** Keep records and seek legal aid.",
        "source_gap_outcome": "source_gap_handoff",
        "source_gap_visible": False,
        "refused": False,
        "error": None,
        "relevance_verdict": "ok",
        "legal_safety": {"hard_fail": False},
        "expected_act_cited_hit": True,
        "unknown_citation_count": 0,
        "route_required_sources_missing": [],
        "ok_sentences": 1,
    }

    assert "source_gap_handoff" in answer_quality_flags(row)
    assert product_pass(row) is False


def test_internal_retrieval_failure_is_counted_even_when_public_handoff_is_safe():
    row = flatten_row(
        {"query": "bank account answer during service outage", "expected_act_hint": None},
        {
            "matter_route": {
                "category": "banking_credit_dispute",
                "required_sources": [],
            },
            "matter_plan": {},
            "workflow": {},
            "source_gap": {
                "has_gap": True,
                "reason": "answer_retrieval_error",
                "outcome": "source_gap_handoff",
                "safe_handoff_only": True,
            },
            "sentences": [],
            "sources": [],
            "passages": [],
            "relevance": {},
            "timing": {"total_ms": 1000},
            "wall_ms": 1000,
            "events": {},
        },
    )

    assert internal_service_error_reason(row) == "answer_retrieval_error"
    assert _rows_summary([row])["errors"] == 1
    assert _rows_summary([row])["internal_service_errors"] == 1
    assert product_pass(row) is False


def test_corpus_source_gap_is_not_mislabeled_as_service_failure():
    assert internal_service_error_reason({"source_gap_reason": "required_source_gap"}) is None


def test_matter_plan_authority_coverage_excludes_nonbinding_context_pointers():
    plan = {
        "authority_ledger": [
            {
                "authority_id": "authority_constitution_342",
                "identity_status": "canonical",
                "must_cite": True,
                "source": "Constitution of India Article 342",
            },
            {
                "authority_id": "authority_provisional_state_rule",
                "identity_status": "provisional",
                "must_cite": True,
                "source": "state caste certificate rules",
            },
            {
                "authority_id": "authority_background",
                "identity_status": "canonical",
                "must_cite": False,
                "source": "background authority",
            },
        ]
    }

    coverage = matter_plan_authority_coverage(
        plan,
        [{
            "authority_ids": [
                "authority_constitution_342",
                "authority_provisional_state_rule",
                "authority_background",
            ],
        }],
    )

    assert coverage == {
        "required_ids": [
            "authority_constitution_342",
        ],
        "found_ids": [
            "authority_constitution_342",
        ],
        "missing_ids": [],
        "missing_sources": [],
        "coverage": 1.0,
        "invalid_entry_indices": [],
        "ok": True,
        "applicable": True,
    }


def test_matter_plan_authority_coverage_keeps_activated_conditional_authority():
    plan = matter_plan_payload(authority_id="authority_provisional_fir")
    plan["authority_ledger"][0].update({
        "source": "BNSS 2023 / CrPC 1973 FIR procedure based on incident date",
        "identity_status": "provisional",
        "canonical_name": None,
        "source_pack_id": "bnss_crpc_fir_procedure",
        "required_anchor_patterns": ["/sec-173"],
        "priority": "conditional",
        "must_cite": False,
        "conditional": True,
    })
    plan["retrieval_sources"][0].update({
        "source_pack_id": "bnss_crpc_fir_procedure",
        "title_patterns": ["Bharatiya Nagarik Suraksha Sanhita 2023"],
        "doc_ids": ["bnss-2023"],
        "anchor_patterns": ["/sec-173"],
        "source_types": ["bare_act"],
    })

    coverage = matter_plan_authority_coverage(
        plan,
        [{
            "authority_ids": ["authority_provisional_fir"],
            "required_source_pack": "bnss_crpc_fir_procedure",
            "title": "Bharatiya Nagarik Suraksha Sanhita 2023",
            "anchor": "bnss-2023/sec-173",
            "source_type": "bare_act",
        }],
        query="police refused to file FIR for my stolen bike",
    )

    assert coverage["applicable"] is True
    assert coverage["ok"] is True
    assert coverage["found_ids"] == ["authority_provisional_fir"]


def test_matter_plan_authority_coverage_fails_closed_on_malformed_ledger_metadata():
    plan = {
        "incident_date_status": "not_required",
        "authority_ledger": [{
            "source": "Consumer Protection Act 2019 Section 35",
            "priority": "must_cite",
            "must_cite": True,
            "conditional": False,
            # identity_status, source_pack_id, and anchors intentionally omitted
        }],
        "retrieval_sources": [],
    }

    coverage = matter_plan_authority_coverage(plan, [])

    assert coverage["required_ids"] == []
    assert coverage["ok"] is False
    assert coverage["missing_ids"] == []
    assert coverage["invalid_entry_indices"] == [0]
    assert coverage["applicable"] is True


def test_flatten_row_keeps_legacy_metrics_and_fails_when_plan_authority_is_uncited():
    authority_id = "authority_consumer_section_35"
    row = flatten_row(
        {"query": "damaged phone return refused", "expected_act_hint": None},
        {
            "matter_route": {
                "category": "general_legal",
                "label": "Legacy fallback",
                "required_sources": [],
            },
            "matter_plan": matter_plan_payload(authority_id=authority_id),
            "workflow": {},
            "sentences": [{"text": "Use the consumer route [2].", "status": "ok"}],
            "sources": [
                {
                    "index": 1,
                    "title": "Consumer Protection Act 2019",
                    "anchor": "consumer-protection-2019/sec-35",
                    "source_type": "bare_act",
                    "authority_ids": [authority_id],
                },
                {
                    "index": 2,
                    "title": "Unrelated consumer judgment",
                    "source_type": "sc_judgment",
                    "authority_ids": [],
                },
            ],
            "passages": [],
            "relevance": {"verdict": "ok", "score": 0.9},
            "timing": {"total_ms": 1000},
            "wall_ms": 1000,
            "events": {},
        },
    )

    assert row["route_category"] == "general_legal"
    assert row["route_label"] == "Legacy fallback"
    assert row["action_pack_id"] is None
    assert row["plan_primary_issue"] == "consumer"
    assert row["plan_primary_label"] == "Consumer complaint / service deficiency"
    assert row["plan_action_pack_id"] == "consumer_complaint"
    assert row["matter_plan_contract"] == {"valid": True, "errors": []}
    assert row["plan_authority_ids_missing"] == []
    assert row["plan_authority_ids_uncited"] == [authority_id]
    assert product_pass(row) is False


def test_final_sources_event_is_required_for_cited_authority_credit():
    authority_id = "authority_consumer_section_35"
    row = flatten_row(
        {
            "query": "damaged phone return refused",
            "expected_category": "consumer",
            "expected_act_hint": "Consumer Protection Act",
        },
        {
            "matter_route": {
                "category": "consumer",
                "label": "Consumer",
                "required_sources": [],
            },
            "matter_plan": matter_plan_payload(authority_id=authority_id),
            "workflow": {},
            "sentences": [{"text": "File a consumer complaint [2].", "status": "ok"}],
            "sources": [],
            "passages": [{
                "index": 2,
                "title": "Consumer Protection Act 2019",
                "anchor": "consumer-protection-2019/sec-35",
                "source_type": "bare_act",
                "authority_ids": [authority_id],
            }],
            "relevance": {"verdict": "ok", "score": 0.9},
            "timing": {"total_ms": 1000},
            "wall_ms": 1000,
            "events": {},
        },
    )

    assert row["plan_authority_ids_missing"] == []
    assert row["plan_authority_ids_uncited"] == [authority_id]
    assert row["expected_act_cited_hit"] is False
    assert row["unknown_citation_indices"] == [2]
    assert product_pass(row) is False


def test_product_pass_fails_closed_when_required_matter_plan_is_missing():
    row = {
        "matter_plan_required": True,
        "matter_plan_contract": {
            "valid": False,
            "errors": ["schema_version_not_2", "invalid_plan_id"],
        },
        "refused": False,
        "error": None,
        "relevance_verdict": "ok",
        "legal_safety": {"hard_fail": False},
        "expected_act_cited_hit": True,
        "unknown_citation_count": 0,
        "route_required_sources_missing": [],
        "route_required_sources_cited_missing": [],
        "plan_authority_ids_missing": [],
        "plan_authority_ids_uncited": [],
        "source_gap_visible": False,
    }

    assert "missing_or_invalid_matter_plan" in answer_quality_flags(row)
    assert product_pass(row) is False


def test_safe_source_gap_handoff_is_not_reported_as_malformed_matter_plan():
    row = {
        "matter_plan_required": True,
        "matter_plan_contract": {"valid": False, "errors": ["invalid_plan_id"]},
        "source_gap_outcome": "source_gap_handoff",
        "source_gap_safe_handoff_only": True,
        "source_count": 0,
        "source_gap_visible": True,
        "refused": False,
        "error": None,
        "relevance_verdict": "ok",
        "legal_safety": {"hard_fail": False},
        "expected_act_cited_hit": False,
        "route_required_sources_missing": [],
        "route_required_sources_cited_missing": [],
        "plan_authority_ids_missing": [],
        "plan_authority_ids_uncited": [],
    }

    assert safe_source_gap_handoff_for_eval(row) is True
    assert "missing_or_invalid_matter_plan" not in answer_quality_flags(row)
    assert product_pass(row) is False


def test_matter_plan_contract_rejects_shallow_placeholder_payload():
    status = matter_plan_contract_status({
        "schema_version": 2,
        "plan_id": "matter_plan_v2_fake",
        "primary_issue": "consumer",
        "authority_ledger": [],
        "answer_policy": {},
    })

    assert status["valid"] is False
    assert "invalid_primary_label" in status["errors"]
    assert "invalid_retrieval_sources" in status["errors"]
    assert "invalid_answer_policy_required_primary_owner" in status["errors"]


def test_matter_plan_contract_rejects_authority_free_or_contradictory_full_plan():
    empty = matter_plan_payload()
    empty["authority_ledger"] = []
    empty["retrieval_sources"] = []
    empty_status = matter_plan_contract_status(empty)

    contradictory = matter_plan_payload()
    contradictory["authority_ledger"][0]["must_cite"] = False
    contradictory_status = matter_plan_contract_status(contradictory)

    assert empty_status["valid"] is False
    assert "empty_authority_ledger" in empty_status["errors"]
    assert "missing_enforceable_authority_obligation" in empty_status["errors"]
    assert "empty_retrieval_sources" in empty_status["errors"]
    assert contradictory_status["valid"] is False
    assert "invalid_authority_ledger_entry_0" in contradictory_status["errors"]


def test_matter_plan_authority_coverage_measures_activated_provisional_obligation():
    plan = matter_plan_payload(authority_id="authority_provisional_fir")
    plan["authority_ledger"][0].update({
        "source": "BNSS 2023 / CrPC 1973 FIR procedure based on incident date",
        "identity_status": "provisional",
        "canonical_name": None,
        "source_pack_id": "bnss_crpc_fir_procedure",
        "required_anchor_patterns": ["/sec-173"],
        "priority": "conditional",
        "must_cite": False,
        "conditional": True,
    })
    plan["retrieval_sources"][0].update({
        "source_pack_id": "bnss_crpc_fir_procedure",
        "title_patterns": ["Bharatiya Nagarik Suraksha Sanhita 2023"],
        "doc_ids": ["bnss-2023"],
        "anchor_patterns": ["/sec-173"],
        "source_types": ["bare_act"],
    })

    coverage = matter_plan_authority_coverage(
        plan,
        [{
            "authority_ids": ["authority_provisional_fir"],
            "required_source_pack": "bnss_crpc_fir_procedure",
            "title": "Bharatiya Nagarik Suraksha Sanhita 2023",
            "anchor": "bnss-2023/sec-173",
            "source_type": "bare_act",
        }],
        query="police refused to file FIR for my stolen bike",
    )

    assert coverage["applicable"] is True
    assert coverage["ok"] is True
    assert coverage["found_ids"] == ["authority_provisional_fir"]


def test_write_report_uses_required_legal_denominator_and_keeps_all_plan_failures(tmp_path):
    rows = []
    for index in range(101):
        row = flatten_row(
            {"query": f"failure-{index}", "expected_act_hint": None},
            {
                "matter_route": {
                    "category": "consumer",
                    "label": "Consumer",
                    "required_sources": [],
                },
                "workflow": {},
                "sentences": [],
                "sources": [],
                "passages": [],
                "relevance": {"verdict": "ok", "score": 0.9},
                "timing": {"total_ms": 1000},
                "wall_ms": 1000,
                "events": {},
            },
        )
        rows.append(row)

    output_path = tmp_path / "rows.jsonl"
    report_path = tmp_path / "report.md"
    write_report(rows, output_path, report_path)
    report = report_path.read_text(encoding="utf-8")

    assert "MatterPlan contract valid: 0/101 applicable answer rows" in report
    assert "failure-100" in report
    assert "MatterPlan authority-obligation retrieval" in report
    assert "MatterPlan canonical-authority" not in report


def test_expected_legal_category_requires_plan_even_when_observed_route_is_off_topic(tmp_path):
    eval_row = {
        "query": "bank deducted money wrongly",
        "expected_category": "banking_complaint",
    }
    route = {"category": "off_topic", "label": "Off topic", "required_sources": []}
    assert matter_plan_required_for_eval(eval_row, route) is True

    row = flatten_row(
        eval_row,
        {
            "matter_route": route,
            "workflow": {},
            "sentences": [],
            "sources": [],
            "passages": [],
            "relevance": {"verdict": "off_topic", "score": 0.1},
            "timing": {"total_ms": 1000},
            "wall_ms": 1000,
            "events": {},
        },
    )
    report_path = tmp_path / "report.md"
    write_report([row], tmp_path / "rows.jsonl", report_path)
    report = report_path.read_text(encoding="utf-8")

    assert row["matter_plan_required"] is True
    assert "MatterPlan contract valid: 0/1 applicable answer rows" in report
    assert "bank deducted money wrongly" in report


def test_required_source_coverage_separates_found_and_missing_route_sources():
    coverage = required_source_coverage(
        [
            "Reserve Bank Integrated Ombudsman Scheme",
            "Street Vendors Act 2014",
            "Transfer of Property Act 1882 where gift or property-transfer cancellation is involved",
            "state maintenance tribunal rules",
            "bank statement, transaction reference, and written bank grievance",
        ],
        [{"index": 1, "title": "Reserve Bank Integrated Ombudsman Scheme 2021", "source_type": "bare_act"}],
        [],
        query="in 2023 police gave section 160 notice asking woman to come station as witness",
    )

    assert coverage[0]["found"] is True
    assert coverage[0]["requirement_type"] == "must_cite_authority"
    assert coverage[0]["matched_source"]["index"] == 1
    assert coverage[1]["found"] is False
    assert coverage[1]["requirement_type"] == "must_cite_authority"
    assert coverage[2]["found"] is None
    assert coverage[2]["skipped"] is True
    assert coverage[2]["requirement_type"] == "conditional_authority"
    assert coverage[2]["skip_reason"] == "conditional_authority_not_triggered_by_query"
    assert coverage[3]["found"] is None
    assert coverage[3]["skipped"] is True
    assert coverage[3]["requirement_type"] == "procedural_or_local_source"
    assert coverage[3]["skip_reason"] == "procedural_or_local_requirement"
    assert coverage[4]["found"] is None
    assert coverage[4]["skipped"] is True
    assert coverage[4]["skip_reason"] == "evidence_or_fact_requirement"

    triggered_tpa = required_source_coverage(
        ["Transfer of Property Act 1882 where gift or property-transfer cancellation is involved"],
        [],
        [],
        query="mother gave land by gift deed and older son wants cancellation",
    )
    assert triggered_tpa[0]["found"] is False
    assert triggered_tpa[0]["requirement_type"] == "conditional_authority"

    coowner_coverage = required_source_coverage(
        ["Transfer of Property Act 1882 for co-owner transfer and joint purchase/share framing"],
        [
            {
                "index": 1,
                "title": "Transfer of Property Act 1882",
                "anchor": "transfer-of-property-1882/sec-45",
                "source_type": "bare_act",
            }
        ],
        [],
        query="in 2023 police gave section 160 notice asking woman to come station as witness",
    )
    assert coowner_coverage[0]["found"] is True
    assert coowner_coverage[0]["matched_source"]["index"] == 1


def test_required_source_coverage_requires_it_act_67b_for_child_csam():
    missing = required_source_coverage(
        ["Information Technology Act 2000 section 67B for child sexual-image electronic publication"],
        [
            {
                "index": 1,
                "title": "Information Technology Act 2000",
                "anchor": "it-2000/sec-66E",
                "source_type": "bare_act",
            }
        ],
        [],
        query="in 2023 police gave section 160 notice asking woman to come station as witness",
    )
    found = required_source_coverage(
        ["Information Technology Act 2000 section 67B for child sexual-image electronic publication"],
        [
            {
                "index": 2,
                "title": "Information Technology Act 2000",
                "anchor": "it-2000/sec-67B",
                "source_type": "bare_act",
            }
        ],
        [],
    )

    assert missing[0]["found"] is False
    assert found[0]["found"] is True
    assert found[0]["matched_source"]["index"] == 2


def test_required_source_coverage_recognizes_cited_route_source_aliases():
    coverage = required_source_coverage(
        [
            "CGST Act 2017 / GST registration rules for GST registration, ITC, notice, and show-cause issues",
            "Code on Wages / Payment of Wages law",
            "Right to Information Act 2005 for written cancellation/status reasons and first appeal",
            "Aadhaar Act 2016 only for the identity/authentication part",
            "Article 21 and Article 22 lawyer-access safeguards",
            "exact offence section and consent/permission status before treating a criminal case as compoundable",
            "Indian Contract Act 1872 / appointment letter or service-rule clause for notice-period term",
            "Copyright Act 1957 infringement, exceptions/fair dealing, and civil remedies",
        ],
        [
            {
                "index": 1,
                "title": "Central Goods and Services Tax Act 2017",
                "anchor": "cgst-2017/sec-16",
                "source_type": "bare_act",
            },
            {
                "index": 2,
                "title": "Code on Wages 2019",
                "anchor": "code-on-wages-2019/sec-45",
                "source_type": "bare_act",
            },
            {
                "index": 3,
                "title": "Right to Information Act 2005",
                "anchor": "rti-2005/sec-19-b",
                "source_type": "bare_act",
            },
            {
                "index": 4,
                "title": "Aadhaar (Targeted Delivery of Financial and Other Subsidies, Benefits and Services) Act 2016",
                "anchor": "aadhaar-2016/sec-59",
                "source_type": "bare_act",
            },
            {
                "index": 5,
                "title": "Constitution of India",
                "anchor": "constitution-india/sec-22",
                "source_type": "bare_act",
            },
            {
                "index": 6,
                "title": "Bharatiya Nagarik Suraksha Sanhita 2023",
                "anchor": "bnss-2023/sec-359-a",
                "source_type": "bare_act",
            },
            {
                "index": 7,
                "title": "Indian Contract Act 1872",
                "anchor": "indian-contract-1872/sec-37",
                "source_type": "bare_act",
            },
            {
                "index": 8,
                "title": "Copyright Act 1957",
                "anchor": "copyright-1957/sec-51",
                "source_type": "bare_act",
            },
            {
                "index": 9,
                "title": "Constitution of India",
                "anchor": "constitution-india/sec-21",
                "source_type": "bare_act",
            },
        ],
        [],
    )

    assert [item["found"] for item in coverage[:7]] == [True, True, True, True, True, True, True]
    assert coverage[7]["found"] is False

    copyright_coverage = required_source_coverage(
        ["Copyright Act 1957 infringement, exceptions/fair dealing, and civil remedies"],
        [
            {
                "index": 8,
                "title": "Copyright Act 1957",
                "anchor": "copyright-1957/sec-51",
                "source_type": "bare_act",
            },
            {
                "index": 9,
                "title": "Copyright Act 1957",
                "anchor": "copyright-1957/sec-52-k",
                "source_type": "bare_act",
            },
            {
                "index": 10,
                "title": "Copyright Act 1957",
                "anchor": "copyright-1957/sec-55",
                "source_type": "bare_act",
            },
        ],
        [],
    )
    assert copyright_coverage[0]["found"] is True
    assert copyright_coverage[0]["matched_source"]["title"] == "Copyright Act 1957 composite route source"

    habeas_coverage = required_source_coverage(
        ["Article 21 and Article 226 constitutional liberty / habeas corpus route"],
        [
            {
                "index": 11,
                "title": "Constitution of India",
                "anchor": "constitution-india/sec-21",
                "source_type": "bare_act",
            },
            {
                "index": 12,
                "title": "Constitution of India",
                "anchor": "constitution-india/sec-226",
                "source_type": "bare_act",
            },
        ],
        [],
    )
    assert habeas_coverage[0]["found"] is True
    assert habeas_coverage[0]["matched_source"]["title"] == "Constitution composite article source"


def test_required_source_coverage_recognizes_common_user_route_authorities():
    coverage = required_source_coverage(
        [
            "BNSS/CrPC complaint procedure",
            "BNSS 2023 / CrPC 1973 complaint/FIR procedure",
            "Consumer Protection Act 2019 for product defect, warranty, repair, return, refund, or service deficiency",
            "Industrial Disputes Act",
            "Customs Act 1962 for import/export, ICEGATE, duty, valuation, SVB, drawback, or classification issues",
            "NCLT Rules / IBC application forms",
            "NCLAT rules, forms, fees, certified-copy and limitation facts",
            "FSSAI Licensing and Registration Regulations",
            "Motor Vehicles Act 1988 for driving licence, challan, permit, and traffic enforcement",
            "Public Gambling Act 1867 for common gaming-house / game-of-skill framing",
            "Legal Services Authorities Act for DLSA assistance",
            "Hindu Succession Act / applicable personal succession law for heirship and shares",
            "constitutional liberty and medical/vulnerability bail principles",
            "constitutional reproductive autonomy and privacy precedents",
            "court permission and offence-compoundability limits must be checked from the exact section",
            "BNSS 2023 / CrPC 1973 FIR, statement, and medical-examination procedure",
        ],
        [
            {
                "index": 1,
                "title": "Bharatiya Nagarik Suraksha Sanhita 2023",
                "anchor": "bnss-2023/sec-223@2024-07-01",
                "source_type": "bare_act",
            },
            {
                "index": 2,
                "title": "Bharatiya Nagarik Suraksha Sanhita 2023",
                "anchor": "bnss-2023/sec-173-b@2024-07-01",
                "source_type": "bare_act",
            },
            {
                "index": 3,
                "title": "Consumer Protection Act 2019",
                "anchor": "consumer-protection-2019/sec-35@2021-09-17",
                "source_type": "bare_act",
            },
            {
                "index": 4,
                "title": "Industrial Disputes Act 1947",
                "anchor": "industrial-disputes-1947/sec-25F",
                "source_type": "bare_act",
            },
            {
                "index": 5,
                "title": "Customs Act 1962",
                "anchor": "customs-1962/sec-128",
                "source_type": "bare_act",
            },
            {
                "index": 6,
                "title": "National Company Law Tribunal Rules 2016",
                "anchor": "nclt-rules-2016/rule-6",
                "source_type": "rule",
            },
            {
                "index": 7,
                "title": "National Company Law Appellate Tribunal Rules 2016",
                "anchor": "nclat-rules-2016/rule-22",
                "source_type": "rule",
            },
            {
                "index": 8,
                "title": "Food Safety and Standards (Licensing and Registration of Food Businesses) Regulations 2011",
                "anchor": "fssai-licensing-2011/reg-2-1",
                "source_type": "regulation",
            },
            {
                "index": 9,
                "title": "Motor Vehicles Act 1988",
                "anchor": "motor-vehicles-1988/sec-3",
                "source_type": "bare_act",
            },
            {
                "index": 10,
                "title": "Public Gambling Act 1867",
                "anchor": "public-gambling-1867/sec-12",
                "source_type": "bare_act",
            },
            {
                "index": 11,
                "title": "Legal Services Authorities Act 1987",
                "anchor": "legal-services-authorities-1987/sec-12",
                "source_type": "bare_act",
            },
            {
                "index": 12,
                "title": "Hindu Succession Act 1956 (with 2005 amendment)",
                "anchor": "hindu-succession-1956/sec-15",
                "source_type": "bare_act",
            },
            {
                "index": 13,
                "title": "Constitution of India",
                "anchor": "constitution-india/sec-21",
                "source_type": "bare_act",
            },
            {
                "index": 14,
                "title": "Bharatiya Nagarik Suraksha Sanhita 2023",
                "anchor": "bnss-2023/sec-183",
                "source_type": "bare_act",
            },
            {
                "index": 15,
                "title": "Bharatiya Nagarik Suraksha Sanhita 2023",
                "anchor": "bnss-2023/sec-359",
                "source_type": "bare_act",
            },
        ],
        [],
    )

    assert [item["found"] for item in coverage] == [
        True, True, True, True, True, True, True, True,
        True, True, True, True, True, False, True, True,
    ]

    bnss_quashing = required_source_coverage(
        ["BNSS 2023 section 528 for current High Court inherent-powers/quashing framing"],
        [
            {
                "index": 13,
                "title": "Bharatiya Nagarik Suraksha Sanhita 2023",
                "anchor": "bnss-2023/sec-528@2024-07-01",
                "source_type": "bare_act",
            },
        ],
        [],
    )
    assert bnss_quashing[0]["found"] is True
    assert bnss_quashing[0]["matched_source"]["index"] == 13

    notice_coverage = required_source_coverage(
        [
            "BNSS 2023 section 35 police notice/appearance safeguards for current matters",
            "CrPC 1973 section 160 witness-attendance route for pre-1 July 2024 matters where applicable",
        ],
        [
            {
                "index": 13,
                "title": "Bharatiya Nagarik Suraksha Sanhita 2023",
                "anchor": "bnss-2023/sec-35-a@2024-07-01",
                "heading": "Bharatiya Nagarik Suraksha Sanhita 2023, Section 35",
                "source_type": "bare_act",
            },
            {
                "index": 14,
                "title": "Code of Criminal Procedure 1973",
                "anchor": "crpc-1973/sec-160",
                "source_type": "bare_act",
            },
        ],
        [],
        query="in 2023 police gave section 160 notice asking woman to come station as witness",
    )
    assert notice_coverage[0]["found"] is True
    assert notice_coverage[0]["matched_source"]["index"] == 13
    assert notice_coverage[1]["found"] is True
    assert notice_coverage[1]["matched_source"]["index"] == 14

    arrest_coverage = required_source_coverage(
        [
            "constitutional liberty safeguards under Articles 21 and 22",
            "BNSS 2023 arrest and 24-hour production safeguards for current matters",
        ],
        [
            {
                "index": 15,
                "title": "Constitution of India",
                "anchor": "constitution-india/sec-21",
                "source_type": "bare_act",
            },
            {
                "index": 16,
                "title": "Constitution of India",
                "anchor": "constitution-india/sec-22",
                "source_type": "bare_act",
            },
            {
                "index": 17,
                "title": "Bharatiya Nagarik Suraksha Sanhita 2023",
                "anchor": "bnss-2023/sec-58@2024-07-01",
                "source_type": "bare_act",
            },
        ],
        [],
    )
    assert arrest_coverage[0]["found"] is True
    assert arrest_coverage[0]["matched_source"]["title"] == "Constitution composite article source"
    assert arrest_coverage[1]["found"] is True
    assert arrest_coverage[1]["matched_source"]["index"] == 17

    delhi_prison_coverage = required_source_coverage(
        ["state prison rules / prison manual for interviews, visits, and permitted books"],
        [
            {
                "index": 18,
                "title": "Delhi Prison Rules 2018",
                "anchor": "delhi-prison-rules-2018/rule-613-616",
                "source_type": "bare_act",
            }
        ],
        [],
        query="tihar jail mulaqat only 30 min once a week",
    )
    assert delhi_prison_coverage[0]["found"] is True
    assert delhi_prison_coverage[0]["matched_source"]["index"] == 18

    non_delhi_prison_coverage = required_source_coverage(
        ["state prison rules / prison manual for interviews, visits, and permitted books"],
        [
            {
                "index": 18,
                "title": "Delhi Prison Rules 2018",
                "anchor": "delhi-prison-rules-2018/rule-613-616",
                "source_type": "bare_act",
            }
        ],
        [],
        query="pune yerwada jail mulaqat denied wife wants to meet husband",
    )
    assert non_delhi_prison_coverage[0]["found"] is False


def test_required_source_requirement_classification_keeps_diagnostics_actionable():
    assert classify_required_source_requirement("Consumer Protection Act 2019") == (
        "must_cite_authority",
        None,
    )
    assert classify_required_source_requirement(
        "POCSO Act 2012 only where the offence alleged is POCSO"
    ) == ("must_cite_authority", None)
    assert classify_required_source_requirement(
        "BNSS 2023 / CrPC 1973 bail provisions based on incident date"
    ) == ("must_cite_authority", None)
    assert classify_required_source_requirement(
        "state maintenance tribunal rules"
    ) == ("procedural_or_local_source", "procedural_or_local_requirement")
    assert classify_required_source_requirement(
        "state education rules"
    ) == ("procedural_or_local_source", "procedural_or_local_requirement")
    assert classify_required_source_requirement(
        "Consumer Protection Act 2019 for medical service deficiency and consumer-forum complaint"
    ) == ("must_cite_authority", None)
    assert classify_required_source_requirement(
        "Reserve Bank Integrated Ombudsman Scheme for RBI Ombudsman/CMS forum complaint"
    ) == ("must_cite_authority", None)
    assert classify_required_source_requirement(
        "bank statement and transaction reference"
    ) == ("fact_or_document_requirement", "evidence_or_fact_requirement")


def test_required_source_coverage_accepts_broad_gift_deed_and_free_consent_sources():
    coverage = required_source_coverage(
        [
            "Transfer of Property Act 1882 where gift or property-transfer cancellation is involved",
            "Indian Contract Act 1872 where consent, coercion, undue influence, or authority is disputed",
            "Registration Act / civil court procedure where document validity is disputed",
            "Specific Relief Act 1963 where cancellation/declaration/injunction is needed",
            "BNS 2023 / IPC 1860 cheating, forgery, or false-document provisions based on incident date",
            "BNSS 2023 / CrPC 1973 complaint and investigation procedure based on incident date",
        ],
        [
            {
                "index": 1,
                "title": "Transfer of Property Act 1882",
                "anchor": "transfer-of-property-1882/sec-122",
                "source_type": "bare_act",
            },
            {
                "index": 2,
                "title": "Registration Act 1908",
                "anchor": "registration-1908/sec-49",
                "source_type": "bare_act",
            },
            {
                "index": 3,
                "title": "Specific Relief Act 1963",
                "anchor": "specific-relief-1963/sec-31",
                "source_type": "bare_act",
            },
            {
                "index": 4,
                "title": "Indian Contract Act 1872",
                "anchor": "indian-contract-1872/sec-19-a",
                "source_type": "bare_act",
            },
            {
                "index": 5,
                "title": "Bharatiya Nyaya Sanhita 2023",
                "anchor": "bns-2023/sec-336",
                "source_type": "bare_act",
            },
            {
                "index": 6,
                "title": "Bharatiya Nagarik Suraksha Sanhita 2023",
                "anchor": "bnss-2023/sec-173-a",
                "source_type": "bare_act",
            },
            {
                "index": 7,
                "title": "Code of Criminal Procedure 1973",
                "anchor": "crpc-1973/sec-200",
                "source_type": "bare_act",
            },
        ],
        [],
        query="mother thumb impression blank paper produced as gift deed",
    )

    assert [item["found"] for item in coverage] == [True, True, True, True, True, True]


def test_required_source_coverage_skips_untriggered_conditional_authorities():
    coverage = required_source_coverage(
        [
            "BNSS 2023 / CrPC 1973 only if the case-status issue is in a criminal case",
            "Legal Services Authorities Act 1987 where help is needed",
            "Constitution of India Article 32 for Supreme Court fundamental-right enforcement where applicable",
            "BOCW Act 1996 / Factories Act 1948 where applicable",
            "Registration Act only if document registration or admissibility is disputed",
            "Code on Wages only if salary, full-and-final, leave encashment, or wage dues are withheld",
        ],
        [],
        [],
        query="civil suit court fee 25 lakh recovery fixed or ad valorem",
    )

    assert [item["skipped"] for item in coverage] == [True, True, True, True, True, True]
    assert [item["skip_reason"] for item in coverage] == [
        "conditional_authority_not_triggered_by_query",
    ] * 6


def test_required_source_coverage_does_not_trigger_family_personal_law_for_spouse_violence_only():
    coverage = required_source_coverage(
        [
            "family law statute by religion",
            "BNSS/CrPC maintenance provisions where applicable",
        ],
        [],
        [],
        query="my husband is slapping me and his parents threw me out",
    )

    assert [item["skipped"] for item in coverage] == [True, True]


def test_required_source_coverage_triggers_family_and_maintenance_only_on_matching_relief():
    family = required_source_coverage(
        ["family law statute by religion"],
        [],
        [],
        query="my husband lied before marriage about job can I annul marriage",
    )
    maintenance = required_source_coverage(
        ["BNSS/CrPC maintenance provisions where applicable"],
        [],
        [],
        query="wife and child maintenance case husband not paying monthly support",
    )

    assert family[0].get("skipped") is not True
    assert family[0]["found"] is False
    assert maintenance[0].get("skipped") is not True
    assert maintenance[0]["found"] is False


def test_required_source_coverage_skips_untriggered_offence_source_for_procedure_only_bail():
    missing = required_source_coverage(
        [
            "BNSS 2023 / CrPC 1973 bail provisions based on incident date",
            "BNS 2023 / IPC 1860 offence provisions where relevant",
            "Legal Services Authorities Act 1987 where help is needed",
        ],
        [],
        [],
        query="brother arrested six months no chargesheet legal aid can bail be filed",
    )

    assert [item["requirement_type"] for item in missing] == [
        "conditional_authority",
        "conditional_authority",
        "conditional_authority",
    ]
    assert [item["found"] for item in missing] == [False, None, False]
    assert [item.get("skipped") for item in missing] == [None, True, None]


def test_required_source_coverage_is_bns_section_family_aware():
    required = ["BNS 2023 / IPC 1860 provisions where physical assault, stalking, or threats are involved"]

    wrong = required_source_coverage(
        required,
        [
            {
                "index": 1,
                "title": "Bharatiya Nyaya Sanhita 2023",
                "anchor": "bns-2023/sec-356",
                "source_type": "bare_act",
            }
        ],
        [],
        query="boss touched my back in office and threatened me",
    )
    assert wrong[0]["found"] is False

    right = required_source_coverage(
        required,
        [
            {
                "index": 1,
                "title": "Bharatiya Nyaya Sanhita 2023",
                "anchor": "bns-2023/sec-74",
                "source_type": "bare_act",
            }
        ],
        [],
        query="boss touched my back in office and threatened me",
    )
    assert right[0]["found"] is True


def test_required_source_coverage_requires_matching_bnss_crpc_section_family():
    wrong_section = required_source_coverage(
        ["BNSS 2023 / CrPC 1973 bail provisions based on incident date"],
        [
            {
                "index": 1,
                "title": "Bharatiya Nagarik Suraksha Sanhita 2023",
                "anchor": "bnss-2023/sec-173",
                "source_type": "bare_act",
            }
        ],
        [],
        query="brother arrested six months no chargesheet can bail be filed",
    )
    both_regimes = required_source_coverage(
        ["BNSS 2023 / CrPC 1973 bail provisions based on incident date"],
        [
            {
                "index": 1,
                "title": "Bharatiya Nagarik Suraksha Sanhita 2023",
                "anchor": "bnss-2023/sec-480",
                "source_type": "bare_act",
            },
            {
                "index": 2,
                "title": "Code of Criminal Procedure 1973",
                "anchor": "crpc-1973/sec-439",
                "source_type": "bare_act",
            },
        ],
        [],
        query="brother arrested six months no chargesheet can bail be filed",
    )

    assert wrong_section[0]["found"] is False
    assert both_regimes[0]["found"] is True
    assert both_regimes[0]["matched_source"]["source_type"] == "aggregate"

    search_seizure = required_source_coverage(
        ["BNSS 2023 / CrPC 1973 search, seizure, arrest, bail, and complaint procedure based on incident date"],
        [
            {
                "index": 1,
                "title": "Bharatiya Nagarik Suraksha Sanhita 2023",
                "anchor": "bnss-2023/sec-483@2024-07-01",
                "source_type": "bare_act",
            },
            {
                "index": 2,
                "title": "Code of Criminal Procedure 1973",
                "anchor": "crpc-1973/sec-165",
                "source_type": "bare_act",
            },
        ],
        [],
        query="pls tell drug dealer in goa caught with mdma in my bag he gave 200mg punishment need lawyer or police",
    )
    assert search_seizure[0]["found"] is True

    arrest_only = required_source_coverage(
        ["BNSS/CrPC bail and arrest safeguards where relevant"],
        [
            {
                "index": 1,
                "title": "Bharatiya Nagarik Suraksha Sanhita 2023",
                "anchor": "bnss-2023/sec-480",
                "source_type": "bare_act",
            }
        ],
        [],
        query="police arrested my son last night and did not produce him in 24 hours",
    )
    assert arrest_only[0]["found"] is False


def test_required_source_coverage_accepts_jj_adoption_sections_without_bare_papers_trigger():
    skipped = required_source_coverage(
        ["Juvenile Justice Act 2015 and adoption regulations where adoption papers are missing"],
        [],
        [],
        query="child passport papers are stuck with father for travel",
    )
    assert skipped[0]["skipped"] is True
    assert skipped[0]["found"] is None

    found = required_source_coverage(
        ["Juvenile Justice Act 2015 and adoption regulations where adoption papers are missing"],
        [
            {
                "index": 1,
                "title": "Juvenile Justice (Care and Protection of Children) Act 2015",
                "anchor": "jj-2015/sec-56",
                "source_type": "bare_act",
            }
        ],
        [],
        query="we adopted child from sister but no papers now real parents want him back",
    )
    assert found[0]["found"] is True

    adopting_missing = required_source_coverage(
        ["Juvenile Justice Act 2015 and adoption regulations where adoption papers are missing"],
        [],
        [],
        query="we are adopting child from sister no papers now real parents object custody",
    )
    assert adopting_missing[0].get("skipped") is not True
    assert adopting_missing[0]["found"] is False


def test_required_source_coverage_does_not_use_token_fallback_for_dual_regime_source():
    coverage = required_source_coverage(
        ["BNSS 2023 / CrPC 1973 bail provisions based on incident date"],
        [
            {
                "index": 1,
                "title": "Bharatiya Nagarik Suraksha Sanhita 2023",
                "anchor": "bnss-2023/sec-173",
                "source_type": "bare_act",
            },
            {
                "index": 2,
                "title": "Code of Criminal Procedure 1973",
                "anchor": "crpc-1973/sec-154",
                "source_type": "bare_act",
            },
        ],
        [],
        query="brother arrested six months no chargesheet can bail be filed",
    )

    assert coverage[0]["found"] is False
    assert coverage[0]["match_score"] == 0.0


def test_stage_e9b_eval_accepts_chargesheet_procedure_source_without_event_date():
    coverage = required_source_coverage(
        [
            "BNSS 2023 / CrPC 1973 charge-sheet, summons, bail, discharge, and court procedure based on incident date"
        ],
        [
            {
                "index": 1,
                "title": "Bharatiya Nagarik Suraksha Sanhita 2023",
                "anchor": "bnss-2023/sec-193-a@2024-07-01",
                "source_type": "bare_act",
            }
        ],
        [],
        query="can u tell delhi police chargesheet fr tweet calling cm corrupt is this 356 case what can i do",
    )

    assert coverage[0]["found"] is True


def test_stage_e9b_eval_skips_untriggered_bocw_cess_and_criminal_fraud_sources():
    coverage = required_source_coverage(
        [
            "BOCW Cess Act / state welfare-board cess records where cess collection or fake registers are alleged",
            "BNS/BNSS or IPC/CrPC where cheating, forgery, or false registers are alleged",
        ],
        [],
        [],
        query="please help how to get bocw card mumbai i work construction 8 years no card no benefit any remedy",
    )

    assert [item.get("skipped") for item in coverage] == [True, True]


def test_required_source_coverage_accepts_coherent_bns_bnss_or_ipc_crpc_pair():
    required = ["BNS/BNSS or IPC/CrPC based on incident date"]
    current_sources = [
        {
            "index": 1,
            "title": "Bharatiya Nyaya Sanhita 2023",
            "anchor": "bns-2023/sec-318",
            "source_type": "bare_act",
        },
        {
            "index": 2,
            "title": "Bharatiya Nagarik Suraksha Sanhita 2023",
            "anchor": "bnss-2023/sec-173",
            "source_type": "bare_act",
        },
    ]
    old_sources = [
        {
            "index": 1,
            "title": "Indian Penal Code 1860",
            "anchor": "ipc-1860/sec-420",
            "source_type": "bare_act",
        },
        {
            "index": 2,
            "title": "Code of Criminal Procedure 1973",
            "anchor": "crpc-1973/sec-154",
            "source_type": "bare_act",
        },
    ]

    current = required_source_coverage(
        required,
        current_sources,
        [],
        query="got 8 lakh phonepe fraud police not filing fir",
    )
    old = required_source_coverage(
        required,
        old_sources,
        [],
        query="incident in 2023 phonepe fraud police not filing fir",
    )
    wrong_regime = required_source_coverage(
        required,
        current_sources,
        [],
        query="incident in 2023 phonepe fraud police not filing fir",
    )

    assert current[0]["found"] is True
    assert current[0]["matched_source"]["source_type"] == "aggregate"
    assert old[0]["found"] is True
    assert old[0]["matched_source"]["source_type"] == "aggregate"
    assert wrong_regime[0]["found"] is False


def test_required_source_coverage_rejects_partial_bns_bnss_or_ipc_crpc_pair():
    coverage = required_source_coverage(
        ["BNS/BNSS or IPC/CrPC based on incident date"],
        [
            {
                "index": 1,
                "title": "Bharatiya Nyaya Sanhita 2023",
                "anchor": "bns-2023/sec-318",
                "source_type": "bare_act",
            }
        ],
        [],
        query="got 8 lakh phonepe fraud police not filing fir",
    )

    assert coverage[0]["found"] is False


def test_required_source_coverage_rejects_composite_pair_with_wrong_offence_section_family():
    required = ["BNS/BNSS or IPC/CrPC based on incident date"]

    wrong_offence = required_source_coverage(
        required,
        [
            {
                "index": 1,
                "title": "Bharatiya Nyaya Sanhita 2023",
                "anchor": "bns-2023/sec-356",
                "source_type": "bare_act",
            },
            {
                "index": 2,
                "title": "Bharatiya Nagarik Suraksha Sanhita 2023",
                "anchor": "bnss-2023/sec-173",
                "source_type": "bare_act",
            },
        ],
        [],
        query="auto driver threw acid on my face what FIR section applies",
    )
    matching_offence = required_source_coverage(
        required,
        [
            {
                "index": 1,
                "title": "Bharatiya Nyaya Sanhita 2023",
                "anchor": "bns-2023/sec-124",
                "source_type": "bare_act",
            },
            {
                "index": 2,
                "title": "Bharatiya Nagarik Suraksha Sanhita 2023",
                "anchor": "bnss-2023/sec-173",
                "source_type": "bare_act",
            },
        ],
        [],
        query="auto driver threw acid on my face what FIR section applies",
    )

    assert wrong_offence[0]["found"] is False
    assert matching_offence[0]["found"] is True
    assert matching_offence[0]["matched_source"]["source_type"] == "aggregate"


def test_required_source_coverage_does_not_treat_bnss_as_bns_or_new_law_as_old_regime():
    required = ["BNS/BNSS or IPC/CrPC based on incident date"]

    only_bnss = required_source_coverage(
        required,
        [
            {
                "index": 1,
                "title": "Bharatiya Nagarik Suraksha Sanhita 2023",
                "anchor": "bnss-2023/sec-173",
                "source_type": "bare_act",
            }
        ],
        [],
        query="phonepe fraud police not filing fir",
    )
    old_fact_with_new_sources = required_source_coverage(
        required,
        [
            {
                "index": 1,
                "title": "Bharatiya Nyaya Sanhita 2023",
                "anchor": "bns-2023/sec-318",
                "source_type": "bare_act",
            },
            {
                "index": 2,
                "title": "Bharatiya Nagarik Suraksha Sanhita 2023",
                "anchor": "bnss-2023/sec-173",
                "source_type": "bare_act",
            },
        ],
        [],
        query="incident in 2022 phonepe fraud police not filing fir",
    )

    assert only_bnss[0]["found"] is False
    assert old_fact_with_new_sources[0]["found"] is False


def test_required_source_coverage_enforces_single_regime_crpc_conditional_source():
    coverage = required_source_coverage(
        ["CrPC 1973 section 160 witness attendance safeguards where applicable"],
        [],
        [],
        query="police gave section 160 notice asking woman to come station as witness",
    )

    assert coverage[0]["requirement_type"] == "conditional_authority"
    assert coverage[0]["found"] is False


def test_required_source_coverage_requires_pmla_sc_precedent_when_named():
    required = ["Supreme Court PMLA bail/arrest precedents"]
    statute_only = required_source_coverage(
        required,
        [
            {
                "index": 1,
                "title": "Prevention of Money Laundering Act 2002",
                "anchor": "pmla-2002/sec-45",
                "source_type": "bare_act",
            }
        ],
        [],
        query="pmla twin condition bail how to argue not guilty",
    )
    precedent_present = required_source_coverage(
        required,
        [
            {
                "index": 2,
                "title": "VIJAY MADANLAL CHOUDHARY versus UNION OF INDIA PMLA",
                "anchor": "2022-insc-757#para-401",
                "source_type": "sc_judgment",
            }
        ],
        [],
        query="pmla twin condition bail how to argue not guilty",
    )

    assert statute_only[0]["found"] is False
    assert precedent_present[0]["found"] is True


def test_required_source_coverage_requires_both_pesa_fra_and_80c_80ccd():
    pesa_fra = required_source_coverage(
        ["PESA Act / Forest Rights Act where Gram Sabha or forest-rights facts apply"],
        [
            {
                "index": 1,
                "title": "Scheduled Tribes and Other Traditional Forest Dwellers (Recognition of Forest Rights) Act 2006",
                "anchor": "fra-2006/sec-5",
                "source_type": "bare_act",
            }
        ],
        [],
        query="gond woman forest officer not giving IFR title dindori gram sabha",
    )
    income = required_source_coverage(
        ["Income Tax Act 1961 sections 80C and 80CCD deduction sources"],
        [
            {
                "index": 1,
                "title": "Income-tax Act 1961",
                "anchor": "income-tax-1961/sec-80C",
                "source_type": "bare_act",
            }
        ],
        [],
        query="can i claim 80c and 80ccd nps together",
    )

    assert pesa_fra[0]["found"] is False
    assert income[0]["found"] is False


def test_required_source_coverage_anchor_matching_does_not_prefix_match():
    coverage = required_source_coverage(
        ["BNSS 2023 / CrPC 1973 arrest, notice, bail, and complaint procedure based on incident date"],
        [
            {
                "index": 1,
                "title": "Bharatiya Nagarik Suraksha Sanhita 2023",
                "anchor": "bnss-2023/sec-359",
                "source_type": "bare_act",
            },
            {
                "index": 2,
                "title": "Code of Criminal Procedure 1973",
                "anchor": "crpc-1973/sec-160",
                "source_type": "bare_act",
            },
        ],
        [],
        query="police notice came after arrest threat",
    )

    assert coverage[0]["found"] is False


def test_flatten_row_preserves_workflow_source_gaps_and_suppressed_details():
    row = flatten_row(
        {
            "query": "UPI failed but amount debited",
            "expected_act_hint": "Banking Ombudsman",
        },
        {
            "matter_route": {
                "category": "banking_credit_dispute",
                "label": "Bank debit / RBI Ombudsman complaint",
                "required_sources": ["Reserve Bank Integrated Ombudsman Scheme", "Consumer Protection Act 2019"],
            },
            "workflow": {
                "id": "bank_wrong_debit",
                "source": "common_workflow_contracts",
                "selected": True,
                "answer_owner": "common_workflow_contracts",
                "answer_mode": "primary",
                "required_sources": ["rbi_ombudsman"],
                "optional_sources": ["consumer_forum"],
                "source_indices": {"rbi_ombudsman": 1},
                "contract_miss_reason": None,
                "line_count": 3,
                "workflow_shadowed_by_legacy": False,
            },
            "sentences": [{"text": "Use RBI Ombudsman first [1].", "status": "ok"}],
            "suppressed_count": 1,
            "suppressed": [{"status": "unsupported", "reason": "unsupported_or_unknown_citation"}],
            "sources": [{"index": 1, "title": "Reserve Bank Integrated Ombudsman Scheme 2021", "source_type": "bare_act"}],
            "passages": [],
            "relevance": {"verdict": "ok", "score": 0.8},
            "timing": {"total_ms": 1000},
            "wall_ms": 1000,
            "events": {},
        },
    )

    assert row["workflow_id"] == "bank_wrong_debit"
    assert row["workflow_source"] == "common_workflow_contracts"
    assert row["workflow_selected"] is True
    assert row["workflow_answer_owner"] == "common_workflow_contracts"
    assert row["workflow_answer_mode"] == "primary"
    assert row["workflow_required_sources"] == ["rbi_ombudsman"]
    assert row["workflow_source_indices"] == {"rbi_ombudsman": 1}
    assert row["workflow_shadowed_by_legacy"] is False
    assert row["suppressed_status_counts"] == {"unsupported": 1}
    assert row["unknown_citation_count"] == 0
    assert "Reserve Bank Integrated Ombudsman Scheme" in row["route_required_sources_found"]
    assert "Consumer Protection Act 2019" in row["route_required_sources_missing"]


def test_flatten_row_fails_product_gate_when_required_source_is_retrieved_but_not_cited():
    row = flatten_row(
        {
            "query": "bank deducted money wrongly and customer care is not helping",
            "expected_act_hint": None,
        },
        {
            "matter_route": {
                "category": "banking_credit_dispute",
                "label": "Bank debit / RBI Ombudsman complaint",
                "required_sources": ["Reserve Bank Integrated Ombudsman Scheme", "Consumer Protection Act 2019"],
            },
            "workflow": {},
            "sentences": [{"text": "Start with the RBI Ombudsman complaint route [1].", "status": "ok"}],
            "sources": [
                {
                    "index": 1,
                    "title": "Reserve Bank Integrated Ombudsman Scheme 2021",
                    "anchor": "rbi-integrated-ombudsman-2021/sec-2",
                    "source_type": "bare_act",
                },
                {
                    "index": 2,
                    "title": "Consumer Protection Act 2019",
                    "anchor": "consumer-protection-2019/sec-35",
                    "source_type": "bare_act",
                },
            ],
            "passages": [],
            "relevance": {"verdict": "ok", "score": 0.9},
            "timing": {"total_ms": 1000},
            "wall_ms": 1000,
            "events": {},
        },
    )

    assert row["route_required_sources_missing"] == []
    assert "Consumer Protection Act 2019" in row["route_required_sources_cited_missing"]
    assert "route_required_source_not_cited" in answer_quality_flags(row)
    assert product_pass(row) is False


def test_flatten_row_keeps_triggered_conditional_source_gap_in_product_gate():
    row = flatten_row(
        {
            "query": "mother gave land by gift deed and older son wants cancellation",
            "expected_act_hint": None,
        },
        {
            "matter_route": {
                "category": "property_tenancy",
                "label": "Gift deed cancellation",
                "required_sources": [
                    "Transfer of Property Act 1882 where gift or property-transfer cancellation is involved",
                ],
            },
            "workflow": {},
            "sentences": [{"text": "Use a civil route [1].", "status": "ok"}],
            "sources": [{"index": 1, "title": "Specific Relief Act 1963", "source_type": "bare_act"}],
            "passages": [],
            "relevance": {"verdict": "ok", "score": 0.9},
            "timing": {"total_ms": 1000},
            "wall_ms": 1000,
            "events": {},
        },
    )

    assert row["route_required_source_coverage"][0]["requirement_type"] == "conditional_authority"
    assert row["route_required_source_coverage"][0]["found"] is False
    assert row["route_required_sources_missing"] == [
        "Transfer of Property Act 1882 where gift or property-transfer cancellation is involved",
    ]
    assert product_pass(row) is False


def test_cited_source_order_metrics_flags_judgment_before_actionable_source():
    sources = [
        {"index": 1, "title": "BANK CASE versus CUSTOMER", "source_type": "sc_judgment", "anchor": "2020-insc-1#para-5"},
        {"index": 2, "title": "Reserve Bank Integrated Ombudsman Scheme 2021", "source_type": "bare_act", "anchor": "rbi-integrated-ombudsman-2021/sec-2"},
    ]

    metrics = cited_source_order_metrics(
        sources,
        [],
        [{"text": "A judgment discusses bank service deficiency [1]. Later use RBI Ombudsman [2]."}],
    )

    assert metrics["first_cited_source_type"] == "sc_judgment"
    assert metrics["first_cited_is_actionable"] is False
    assert metrics["judgment_before_actionable_source"] is True


def test_cited_source_order_metrics_passes_when_actionable_source_leads():
    sources = [
        {"index": 1, "title": "BANK CASE versus CUSTOMER", "source_type": "sc_judgment", "anchor": "2020-insc-1#para-5"},
        {"index": 2, "title": "Reserve Bank Integrated Ombudsman Scheme 2021", "source_type": "bare_act", "anchor": "rbi-integrated-ombudsman-2021/sec-2"},
    ]

    metrics = cited_source_order_metrics(
        sources,
        [],
        [{"text": "Use RBI Ombudsman first [2]. A judgment may support deficiency [1]."}],
    )

    assert metrics["first_cited_source_type"] == "bare_act"
    assert metrics["first_cited_is_actionable"] is True
    assert metrics["judgment_before_actionable_source"] is False


def test_expected_procedure_anchor_coverage_requires_all_cited_subparts():
    keys = expected_act_keys("Gazette notification process")
    sources = [
        {
            "index": 1,
            "title": "Department of Publication Guidelines for Change of Name Adult Major",
            "anchor": "deptpub-name-change-adult-guidelines#adult-required-documents",
            "source_type": "circular",
        },
        {
            "index": 2,
            "title": "Department of Publication Guidelines for Change of Name Adult Major",
            "anchor": "deptpub-name-change-adult-guidelines#adult-formalities",
            "source_type": "circular",
        },
        {
            "index": 3,
            "title": "Department of Publication Guidelines for Change of Name Adult Major",
            "anchor": "deptpub-name-change-adult-guidelines#egazette-download-and-submission",
            "source_type": "circular",
        },
    ]

    partial = expected_procedure_anchor_coverage(
        keys,
        sources,
        [],
        [{"text": "Use the Gazette route with formalities [2].", "status": "ok"}],
    )["Gazette Name Change Procedure"]
    assert partial["present_ok"] is True
    assert partial["cited_ok"] is False
    assert partial["missing_cited"] == [
        "deptpub-name-change-adult-guidelines#adult-required-documents",
        "deptpub-name-change-adult-guidelines#egazette-download-and-submission",
    ]

    complete = expected_procedure_anchor_coverage(
        keys,
        sources,
        [],
        [{"text": "Use documents [1], formalities [2], and eGazette download [3].", "status": "ok"}],
    )["Gazette Name Change Procedure"]
    assert complete["present_ok"] is True
    assert complete["cited_ok"] is True

    exact_anchor_wrong_type = expected_procedure_anchor_coverage(
        keys,
        [
            {
                "index": 1,
                "title": "Department of Publication Guidelines for Change of Name Adult Major",
                "anchor": "deptpub-name-change-adult-guidelines#adult-required-documents",
                "source_type": "circular",
            },
            {
                "index": 2,
                "title": "Department of Publication Guidelines for Change of Name Adult Major",
                "anchor": "deptpub-name-change-adult-guidelines#adult-formalities",
                "source_type": "hc_judgment",
            },
            {
                "index": 3,
                "title": "Department of Publication Guidelines for Change of Name Adult Major",
                "anchor": "deptpub-name-change-adult-guidelines#egazette-download-and-submission",
                "source_type": "sc_judgment",
            },
        ],
        [],
        [{"text": "Use all three [1] [2] [3].", "status": "ok"}],
    )["Gazette Name Change Procedure"]
    assert exact_anchor_wrong_type["present_ok"] is False
    assert exact_anchor_wrong_type["cited_ok"] is False
    assert exact_anchor_wrong_type["missing_cited"] == [
        "deptpub-name-change-adult-guidelines#adult-formalities",
        "deptpub-name-change-adult-guidelines#egazette-download-and-submission",
    ]


def test_jj_age_hint_requires_section_9_and_94_citations():
    keys = expected_act_keys("JJ Act 2015 s.9 + s.94 age determination")
    assert "Juvenile Justice Act" in keys
    assert "JJ Age Determination Procedure" in keys

    sources = [
        {
            "index": 1,
            "title": "Juvenile Justice (Care and Protection of Children) Act 2015",
            "anchor": "jj-2015/sec-9",
            "source_type": "bare_act",
        },
        {
            "index": 2,
            "title": "Juvenile Justice (Care and Protection of Children) Act 2015",
            "anchor": "jj-2015/sec-94",
            "source_type": "bare_act",
        },
    ]
    assert expected_act_hit(keys, sources, []) is True
    assert expected_act_cited_hit(
        keys,
        sources,
        [],
        [{"text": "Court inquiry is under JJ Act section 9 [1].", "status": "ok"}],
    ) is False
    assert expected_act_cited_hit(
        keys,
        sources,
        [],
        [{"text": "Use the court inquiry and age-document process [1][2].", "status": "ok"}],
    ) is True

    coverage = expected_procedure_anchor_coverage(
        keys,
        sources,
        [],
        [{"text": "Use both procedure sources [1][2].", "status": "ok"}],
    )["JJ Age Determination Procedure"]
    assert coverage["present_ok"] is True
    assert coverage["cited_ok"] is True

    wrong_type = expected_procedure_anchor_coverage(
        keys,
        [
            {
                "index": 1,
                "title": "Juvenile Justice (Care and Protection of Children) Act 2015",
                "anchor": "jj-2015/sec-9",
                "source_type": "hc_judgment",
            },
            {
                "index": 2,
                "title": "Juvenile Justice (Care and Protection of Children) Act 2015",
                "anchor": "jj-2015/sec-94",
                "source_type": "bare_act",
            },
        ],
        [],
        [{"text": "Use both procedure sources [1][2].", "status": "ok"}],
    )["JJ Age Determination Procedure"]
    assert wrong_type["present_ok"] is False
    assert wrong_type["cited_ok"] is False
    assert wrong_type["missing_cited"] == ["jj-2015/sec-9"]


def test_expected_act_aliases_cover_panchayat_and_cooperative_titles():
    assert expected_act_hit(
        expected_act_keys("Panchayati Raj Act / state Gram Panchayat Act"),
        [{"title": "VILLAGE PANCHAYAT, CALANGUTE versus THE ADDITIONAL DIRECTOR OF PANCHAYAT-II"}],
        [],
    ) is False
    assert expected_act_hit(
        expected_act_keys("Maharashtra Cooperative Societies Act"),
        [{"title": "BOMBAY CATHOLIC CO-OPERATIVE HOUSING SOCIETY LTD."}],
        [],
    ) is False
    assert expected_act_hit(
        expected_act_keys("Maharashtra Cooperative Societies Act"),
        [{"title": "Maharashtra Co-operative Societies Act 1960", "source_type": "bare_act"}],
        [],
    ) is True


def test_answer_quality_flags_catches_dangling_and_non_actionable_next_steps():
    assert "dangling_next_step_header" in answer_quality_flags({
        "answer_text": "**Short answer** This is covered [1]. **What you can do next**",
        "expected_act_cited_hit": True,
    })
    flags = answer_quality_flags({
        "answer_text": "**What you can do next** The provided passages do not state a concrete next step.",
        "expected_act_cited_hit": False,
    })
    assert {"no_concrete_next_step", "expected_act_not_cited"} <= set(flags)
    procedure_flags = answer_quality_flags({
        "answer_text": "**Short answer** Use the Gazette route [1]. **What you can do next** Prepare papers [1].",
        "expected_act_cited_hit": True,
        "expected_procedure_anchor_coverage": {
            "Gazette Name Change Procedure": {"cited_ok": False},
        },
    })
    assert "expected_procedure_anchors_not_cited" in procedure_flags
    richer_flags = answer_quality_flags({
        "answer_text": "**Short answer** This is covered [1].",
        "expected_act_cited_hit": True,
        "suppressed_count": 1,
        "ok_sentences": 0,
    })
    assert {"missing_next_step_section", "suppressed_sentences", "zero_ok_legal_sentences"} <= set(richer_flags)

    weak_but_usable = answer_quality_flags({
        "answer_text": "**Short answer** Use the cited wage route [1]. **What you can do next** File with the wage authority [1].",
        "expected_act_cited_hit": True,
        "first_cited_is_actionable": True,
        "relevance_verdict": "ok",
        "suppressed_count": 0,
        "ok_sentences": 0,
        "weak_sentences": 2,
    })
    assert "zero_ok_legal_sentences" not in weak_but_usable

    regime_flags = answer_quality_flags({
        "answer_text": "**Short answer** Use the BNS hurt route [1]. **What you can do next** File the complaint [1].",
        "expected_act_cited_hit": True,
        "legal_regime": "incident_date_needed_for_bns_bnss_bsa_vs_ipc_crpc",
        "ok_sentences": 2,
    })
    assert "missing_criminal_regime_caveat" in regime_flags

    weak_caveat = answer_quality_flags({
        "answer_text": "**Short answer** Incident date noted. Use the BNS hurt route [1]. **What you can do next** File the complaint [1].",
        "expected_act_cited_hit": True,
        "legal_regime": "incident_date_needed_for_bns_bnss_bsa_vs_ipc_crpc",
        "ok_sentences": 2,
    })
    assert "missing_criminal_regime_caveat" in weak_caveat

    caveated = answer_quality_flags({
        "answer_text": "**Short answer** Use the BNS hurt route, but the incident date decides BNS/BNSS versus IPC/CrPC framing [1]. **What you can do next** File the complaint [1].",
        "expected_act_cited_hit": True,
        "legal_regime": "incident_date_needed_for_bns_bnss_bsa_vs_ipc_crpc",
        "ok_sentences": 2,
    })
    assert "missing_criminal_regime_caveat" not in caveated


def test_expected_act_hit_uses_token_boundaries_for_short_aliases():
    assert expected_act_hit(
        ["Information Technology Act"],
        [{"title": "Maternity Benefit Act 1961"}],
        [],
    ) is False
    assert expected_act_hit(
        ["Companies Act"],
        [{"title": "Credit Information Companies Act 2005"}],
        [],
    ) is False
    assert expected_act_hit(
        ["Companies Act"],
        [{"title": "Companies Act 2013"}],
        [],
    ) is True
    assert expected_act_hit(
        ["Gazette Name Change Procedure"],
        [{"title": "Department of Publication Guidelines for Change of Name Adult Major", "source_type": "circular"}],
        [],
    ) is False
    assert expected_act_hit(
        ["Gazette Name Change Procedure"],
        [{
            "title": "Department of Publication Guidelines for Change of Name Adult Major",
            "anchor": "deptpub-name-change-adult-guidelines#adult-formalities",
            "source_type": "circular",
        }],
        [],
    ) is True
    assert expected_act_hit(
        ["Gazette Name Change Procedure"],
        [{
            "title": "Department of Publication Guidelines for Change of Name Adult Major",
            "anchor": "deptpub-name-change-adult-guidelines#adult-formalities-old",
            "source_type": "circular",
        }],
        [],
    ) is False
    assert expected_act_hit(
        ["Gazette Name Change Procedure"],
        [{
            "title": "Department of Publication Guidelines for Change of Name Adult Major",
            "anchor": "deptpub-name-change-adult-guidelines#adult-formalities",
            "source_type": "hc_judgment",
        }],
        [],
    ) is False
    assert expected_act_hit(
        ["Gazette Name Change Procedure"],
        [{
            "title": "Gazette of India notification about unrelated ministry appointment",
            "anchor": "gazette-of-india#appointment-notice",
            "source_type": "circular",
        }],
        [],
    ) is False


def test_expected_act_keys_do_not_extract_nested_longer_act_names():
    assert expected_act_keys("Credit Information Companies Act") == ["Credit Information Companies Act"]
    assert expected_act_hit(
        expected_act_keys("Credit Information Companies Act"),
        [{"title": "Credit Information Companies Act 2005"}],
        [],
    ) is True


def test_expected_act_keys_disambiguate_it_act_and_prohibition_hints():
    assert expected_act_keys("MSMED Act 2006 s.15 + IT Act s.43B(h)") == ["Income Tax Act", "MSMED Act"]
    assert "Information Technology Act" not in expected_act_keys("MSMED Act 2006 s.15 + IT Act s.43B(h)")
    assert expected_act_keys("Gazette notification process") == ["Gazette Name Change Procedure"]

    keys = expected_act_keys("Section 14 Hindu Succession Act / Dowry Prohibition Act")
    assert "Dowry Prohibition Act" in keys
    assert "Hindu Succession Act" in keys
    assert "State Excise Act" not in keys


def test_expected_act_keys_treat_bns_ipc_as_date_conditional():
    current_or_unknown = expected_act_keys(
        "NHRC Act 1993 s.12 + BNSS 2023 s.196 + BNS/IPC hurt by public servant",
        "i was undertrial 5 yrs released last week need help to file police torture case",
    )
    assert current_or_unknown == ["BNS", "BNSS", "NHRC Act"]

    legacy = expected_act_keys(
        "BNSS/BNS or CrPC/IPC based on event date",
        "police beat me in 2023 fir what ipc remedy",
    )
    assert "IPC" in legacy
    assert "CrPC" in legacy
    assert "BNS" not in legacy
    assert "BNSS" not in legacy


def test_expected_act_keys_respect_conditional_and_missing_jurisdiction_hints():
    assert expected_act_keys(
        "Bonded Labour Act 1976 + SC/ST POA Act if victim is SC/ST",
        "bonded labour my chacha working for thakur 12 years no wages just food bihar",
    ) == ["Bonded Labour Act"]
    assert expected_act_keys(
        "Bonded Labour Act 1976 + SC/ST POA Act if victim is SC/ST",
        "dalit bonded labour working for contractor no wages just food",
    ) == ["Bonded Labour Act", "SC/ST POA Act"]
    assert expected_act_keys(
        "Bonded Labour System (Abolition) Act 1976 s.4 + SC/ST POA s.3(1)(h)",
        "bonded labour my chacha working for thakur 12 years no wages just food bihar",
    ) == ["Bonded Labour Act"]
    assert expected_act_keys(
        "Bonded Labour System (Abolition) Act 1976 s.4 + SC/ST POA s.3(1)(h)",
        "dalit bonded labour working for contractor no wages just food",
    ) == ["Bonded Labour Act", "SC/ST POA Act"]
    assert expected_act_keys(
        "Bonded Labour System (Abolition) Act 1976 s.4 + SC/ST POA s.3(1)(h)",
        "bonded labour worker no wages called caste slur by landlord",
    ) == ["Bonded Labour Act"]
    assert expected_act_keys(
        "BNSS 2023 s.173 + s.175 magistrate complaint + SC/ST POA s.4",
        "can u tell thana refused to file complaint against zamindar who burnt our hut latehar what can i do",
    ) == ["BNSS"]
    assert expected_act_keys(
        "BNS 2023 mischief by fire + BNSS 2023 s.173 + s.175 magistrate complaint + SC/ST POA s.4",
        "upper caste men burnt our dalit family hut police refusing FIR what can we do",
    ) == ["BNS", "BNSS", "SC/ST POA Act"]
    assert expected_act_keys(
        "SC/ST POA Act special court delay",
        "SC ST POA case special court pending 5 years no judgement",
    ) == ["SC/ST POA Act"]

    assert expected_act_keys(
        "RTI Act 2005 + scheme pension rules",
        "papa ki pension 6 month se nahi aayi rti kaise file karein",
    ) == ["RTI Act"]
    assert expected_act_keys(
        "RTI Act 2005 + scheme pension rules",
        "pension scheme money stopped rti kaise file karein",
    ) == ["RTI Act"]
    assert expected_act_keys(
        "RTI Act 2005 + scheme pension rules",
        "old age pension stopped in bihar rti kaise file karein",
    ) == ["RTI Act", "State Pension Scheme"]
    assert expected_act_keys(
        "RTI Act 2005 + scheme pension rules",
        "pension stopped in bihar rti kaise file karein",
    ) == ["RTI Act", "State Pension Scheme"]
    assert expected_act_keys(
        "Indira Gandhi National Old Age Pension Scheme / Aadhaar Act 2016",
        "old age pension stopped suddenly bank says aadhaar not linked",
    ) == ["Aadhaar Act", "State Pension Scheme"]
    assert expected_act_keys(
        "Pension Rules / state widow pension scheme",
        "my husband died in army no service pension widow what papers needed",
    ) == ["Army Pension Regulations"]
    assert expected_act_keys(
        "RTI Act 2005 + scheme pension rules",
        "family pension not paid after husband died in bihar rti kaise karein",
    ) == ["RTI Act"]
    assert expected_act_keys(
        "state municipal law; Shops and Establishments Act; RTI Act",
        "local body locked my commercial shop saying licence problem",
    ) == ["RTI Act"]
    assert expected_act_keys(
        "Maharashtra Shops and Establishments Act; RTI Act",
        "mumbai local body locked my commercial shop saying licence problem",
    ) == ["RTI Act", "Shops and Establishments Act"]

    assert expected_act_keys(
        "state Prohibition / Excise Act; punishment depends on state and FIR section",
        "police caught me drinking village they saying case under prohibition law what punishment",
    ) == []
    assert expected_act_keys(
        "state Prohibition / Excise Act; punishment depends on state and FIR section",
        "police caught me under excise act what punishment",
    ) == []
    assert expected_act_keys(
        "state Prohibition / Excise Act; punishment depends on state and FIR section",
        "police caught me under state excise law what punishment",
    ) == []
    assert expected_act_keys(
        "state Prohibition / Excise Act; punishment depends on state and FIR section",
        "police caught me drinking in bihar under prohibition law what punishment",
    ) == ["State Excise Act"]
    assert expected_act_keys(
        "NDPS Act 1985 + bhang exemption state Excise Acts",
        "vit student caught with bhang lassi in mahabaleshwar holi is it ndps",
    ) == ["NDPS Act", "State Excise Act"]
    assert expected_act_keys(
        "RBI guidelines / Right to Education Act 2009",
        "bank not giving education loan to my daughter even though we have scholarship paper",
    ) == ["Banking Ombudsman"]
    assert expected_act_keys(
        "state Prohibition / Excise Act; punishment depends on state and FIR section",
        "police caught me drinking in odisha under excise law what punishment",
    ) == ["State Excise Act"]


def test_expected_act_keys_require_social_security_and_separate_bocw_from_cess():
    keys = expected_act_keys("Code on Social Security 2020 + Motor Vehicles Act 1988")
    assert "Social Security Code" in keys
    assert "Motor Vehicles Act" in keys
    assert expected_act_hit(keys, [{"title": "Motor Vehicles Act 1988"}], []) is False

    keys = expected_act_keys("BOCW Cess Act 1996 s.3 + BOCW Act 1996 s.13 s.14")
    assert "BOCW Act" in keys
    assert "BOCW Cess Act" in keys
    assert expected_act_hit(
        keys,
        [{"title": "Building and Other Construction Workers Welfare Cess Act 1996"}],
        [],
    ) is False
    assert expected_act_hit(
        keys,
        [
            {"title": "Building and Other Construction Workers Welfare Cess Act 1996"},
            {"title": "Building and Other Construction Workers (Regulation of Employment and Conditions of Service) Act 1996"},
        ],
        [],
    ) is True


def test_expected_act_hit_accepts_local_doc_ids_and_hyphenated_titles():
    assert expected_act_hit(
        expected_act_keys("Income Tax Act section 206C"),
        [{"title": "Income-tax Act 1961", "anchor": "income-tax-1961/sec-206C"}],
        [],
    ) is True
    assert expected_act_hit(
        expected_act_keys("CGST Rules 2017 Rule 86B"),
        [{"title": "Central Goods and Services Tax Rules 2017", "anchor": "cgst-rules-2017/rule-86B"}],
        [],
    ) is True
    assert expected_act_hit(
        expected_act_keys("UAPA 1967 s.43D(5)"),
        [{"title": "Unlawful Activities (Prevention) Act 1967", "anchor": "uapa-1967/sec-43D"}],
        [],
    ) is True
    assert expected_act_hit(
        expected_act_keys("Arms Act 1959 s.2 agricultural tool defence"),
        [{"title": "Arms Act 1959", "anchor": "arms-1959/sec-2"}],
        [],
    ) is True
    assert expected_act_hit(
        expected_act_keys("MCOCA default bail section 21"),
        [{"title": "Maharashtra Control of Organised Crime Act 1999", "anchor": "maharashtra-control-organised-crime-1999/sec-21"}],
        [],
    ) is True
    assert expected_act_keys(
        "Arms Act 1959 definition/licence source + BNSS 2023 bail/FIR procedure + BNS 2023 threat or hurt where alleged",
        "urgent police booked us under arms act for axe we use in farming gadchiroli how to complain",
    ) == ["Arms Act", "BNSS"]
    assert expected_act_hit(
        expected_act_keys("Protection of Civil Rights Act 1955 temple entry"),
        [{"title": "Protection of Civil Rights Act 1955", "anchor": "protection-civil-rights-1955/sec-4"}],
        [],
    ) is True
    assert expected_act_hit(
        expected_act_keys("Environment Protection Act 1986 pollution"),
        [{"title": "Environment (Protection) Act 1986", "anchor": "environment-protection-1986/sec-7"}],
        [],
    ) is True
    assert expected_act_hit(
        expected_act_keys("RBI Ombudsman fair practices complaint"),
        [{"title": "Reserve Bank Integrated Ombudsman Scheme 2021", "anchor": "rbi-integrated-ombudsman-2021/clause-9"}],
        [],
    ) is True
    assert expected_act_keys(
        "RBI Ombudsman + BNSS/Cyber hold where applicable",
        "my bank account is frozen what to do",
    ) == ["Banking Ombudsman", "Banking Regulation Act"]
    assert expected_act_keys(
        "Indian Contract Act + Limitation Act + CPC / NI Act if cheque",
        "my brother is not returning my money which he took as loan",
    ) == ["Code of Civil Procedure", "Indian Contract Act", "Limitation Act"]
    assert expected_act_keys(
        "municipal law + shops and establishments / Article 226",
        "my shop is in Gujarat and municipality sealed it what should i do",
    ) == ["Municipal Law", "Shops and Establishments Act"]
    assert expected_act_hit(
        expected_act_keys(
            "RBI customer liability + IT Act cyber fraud",
            "upi fraud happened bank says it is my mistake what to do",
        ),
        [
            {"title": "Information Technology Act 2000", "anchor": "it-2000/sec-66C"},
            {"title": "Reserve Bank Integrated Ombudsman Scheme 2021", "anchor": "rbi-integrated-ombudsman-2021/sec-2"},
        ],
        [],
    ) is True
    assert expected_act_hit(
        expected_act_keys(
            "municipal law + shops and establishments / Article 226",
            "my shop is in Gujarat and municipality sealed it what should i do",
        ),
        [
            {"title": "Gujarat Municipalities Act 1963", "anchor": "gujarat-municipalities-1963/sec-221"},
            {"title": "Gujarat Shops and Establishments (Regulation of Employment and Conditions of Service) Act 2019", "anchor": "gujarat-shops-establishments-2019/sec-8"},
        ],
        [],
    ) is True
    coverage = required_source_coverage(
        ["Banking Regulation Act / regulated-entity records for bank account service issues"],
        [
            {"title": "Banking Regulation Act 1949", "anchor": "banking-regulation-1949/sec-35A@2025-12-20"},
        ],
        [],
    )
    assert coverage[0]["found"] is True
    coverage = required_source_coverage(
        ["Insurance Ombudsman Rules / insurer grievance procedure"],
        [
            {"title": "Insurance Ombudsman Rules 2017", "anchor": "insurance-ombudsman-rules-2017/sec-5-h"},
        ],
        [],
        query="insurer is rejecting my claim",
    )
    assert coverage[0]["found"] is True
    assert expected_act_hit(
        expected_act_keys("Credit Information Companies Act CIBIL correction"),
        [{"title": "Credit Information Companies (Regulation) Act 2005", "anchor": "credit-information-companies-2005/sec-21"}],
        [],
    ) is True
    assert expected_act_hit(
        expected_act_keys("NHRC Act custodial torture complaint"),
        [{"title": "Protection of Human Rights Act 1993", "anchor": "protection-human-rights-1993/sec-12"}],
        [],
    ) is True
    assert expected_act_hit(
        expected_act_keys("Assam Witch Hunting (Prohibition Prevention and Protection) Act 2015"),
        [{"title": "Assam Witch Hunting (Prohibition, Prevention and Protection) Act 2015", "anchor": "assam-witch-hunting-2015/sec-4", "source_type": "bare_act"}],
        [],
    ) is True
    assert expected_act_hit(
        expected_act_keys("Jharkhand Prevention of Witch (Daain) Practices Act 2001 s.3, s.4"),
        [
            {
                "title": "Jharkhand State Legal Services Authority Dayan Pratha Pratishedh Adhiniyam 2001",
                "anchor": "jhalsa-dayan-pratha-pratishedh-2001/sec-3",
                "source_type": "official_guidance",
            }
        ],
        [],
    ) is True
    assert expected_act_hit(
        expected_act_keys("Jharkhand Prevention of Witch (Daain) Practices Act 2001 s.3, s.4"),
        [
            {
                "title": "Jharkhand Prevention of Witch (Daain) Practices Act 2001",
                "anchor": "jharkhand-prevention-witch-daain-practices-2001/sec-3",
                "source_type": "official_summary",
            }
        ],
        [],
    ) is False
    assert expected_act_hit(
        expected_act_keys("Jharkhand Prevention of Witch (Daain) Practices Act 2001 s.3, s.4"),
        [
            {
                "title": "Private blog Dayan Pratha in Jharkhand",
                "anchor": "blog/dayan-pratha",
                "source_type": "web",
            }
        ],
        [],
    ) is False
    assert expected_act_hit(
        expected_act_keys("Scheduled Areas Land Transfer Regulation / CNT Act"),
        [{"title": "Chota Nagpur Tenancy Act 1908", "anchor": "chota-nagpur-tenancy-1908/sec-46"}],
        [],
    ) is True
    assert expected_act_hit(
        expected_act_keys("National Rural Health Mission guidelines ASHA incentives"),
        [{"title": "National Health Mission ASHA Incentives Guidelines 2025", "anchor": "nhm-asha-incentives-2025/page-1"}],
        [],
    ) is True
    assert expected_act_keys("National Rural Health Mission guidelines ASHA incentives") == ["ASHA Incentives"]
    assert expected_act_hit(
        ["Anganwadi Honorarium"],
        [{"title": "STATE OF KARNATAKA AND ORS. versus AMEERBI AND ORS.", "anchor": "2006-insc-969#win-9", "source_type": "sc_judgment"}],
        [],
    ) is True
    assert expected_act_hit(
        expected_act_keys("Article 21 prison medical care"),
        [{"title": "Constitution of India", "anchor": "/sec-21"}],
        [],
    ) is True
    assert expected_act_hit(
        expected_act_keys("Article 21 prison medical care"),
        [
            {"title": "Constitution of India", "anchor": "/sec-39A"},
            {"title": "Legal Services Authorities Act 1987", "anchor": "/sec-21"},
        ],
        [],
    ) is False
    assert expected_act_hit(
        expected_act_keys("Public Gambling Act"),
        [{"title": "Tamil Nadu Prohibition of Online Gambling and Regulation of Online Games Act 2022", "anchor": "tamil-nadu-online-gambling-2022/sec-7"}],
        [],
    ) is False
    assert expected_act_hit(
        expected_act_keys("Public Gambling Act"),
        [{"title": "The Public Gambling Act, 1867", "anchor": "public-gambling-1867/sec-12"}],
        [],
    ) is True

    cattle_keys = expected_act_keys(
        "state Cattle Preservation Act / Prevention of Cruelty to Animals Act",
        "sir they arrested me for cow transport saying I am smuggling but I was taking my own buffalo to mandi",
    )
    assert cattle_keys == ["Prevention of Cruelty to Animals Act"]
    assert expected_act_hit(
        cattle_keys,
        [{"title": "Prevention of Cruelty to Animals Act 1960", "anchor": "prevention-cruelty-animals-1960/sec-11"}],
        [],
    ) is True


def test_expected_act_hit_does_not_count_cases_or_successor_laws_as_acts():
    assert expected_act_keys("Prem Shankar Shukla v Delhi Admin 1980") == []
    assert expected_act_keys("CGST Rules 2017 Rule 86B") == ["CGST Rules"]
    assert expected_act_hit(
        expected_act_keys("CGST Rules 2017 Rule 86B"),
        [{"title": "Central Goods and Services Tax Act 2017", "anchor": "cgst-2017/sec-49"}],
        [],
    ) is False
    assert expected_act_hit(
        expected_act_keys("Central Goods and Services Tax Act 2017"),
        [{"title": "Central Goods and Services Tax Rules 2017", "anchor": "cgst-rules-2017/rule-86B"}],
        [],
    ) is False
    assert expected_act_hit(
        expected_act_keys("Indian Evidence Act 1872"),
        [{"title": "Bharatiya Sakshya Adhiniyam 2023", "anchor": "sakshya-adhiniyam-2023/sec-2"}],
        [],
    ) is False
    assert expected_act_hit(
        expected_act_keys("MV Act 1988 s.74"),
        [{"title": "TheMotorVehiclesAct,1988", "anchor": "motor-vehicles-1988/sec-74-a"}],
        [],
    ) is True
    assert expected_act_hit(
        expected_act_keys("IT Act 2000 s.66C + Telecom Act 2023"),
        [
            {"title": "Information Technology Act 2000", "anchor": "it-2000/sec-66C"},
            {"title": "Telecommunications Act 2023", "anchor": "telecommunications-2023/sec-42"},
        ],
        [],
    ) is True


def test_expected_act_hit_accepts_apostrophe_in_employees_compensation_title():
    assert expected_act_hit(
        expected_act_keys("Employees Compensation Act"),
        [{"title": "Employees' Compensation Act 1923", "anchor": "employees-compensation-1923/sec-3"}],
        [],
    ) is True


def test_conditional_posh_expected_act_requires_sexual_harassment_facts():
    hint = "Industrial Disputes Act 1947 / POSH Act where sexual harassment facts exist"

    generic_hr_keys = expected_act_keys(
        hint,
        "i complained against my manager for harassment to HR and now they are putting me on PIP, is this retaliation",
    )
    assert "Industrial Disputes Act" in generic_hr_keys
    assert "POSH Act" not in generic_hr_keys

    sexual_hr_keys = expected_act_keys(
        hint,
        "i complained to ICC about sexual harassment by my manager and now they put me on PIP",
    )
    assert "Industrial Disputes Act" in sexual_hr_keys
    assert "POSH Act" in sexual_hr_keys


def test_stage_e9_eval_accepts_bns_exploitation_subanchors_for_itpa_raid():
    coverage = required_source_coverage(
        ["BNS 2023 / IPC 1860 trafficking or exploitation provisions based on incident date"],
        [
            {
                "title": "Bharatiya Nyaya Sanhita 2023",
                "anchor": "bns-2023/sec-144@2024-07-01",
            },
            {
                "title": "Bharatiya Nyaya Sanhita 2023",
                "anchor": "bns-2023/sec-146@2024-07-01",
            },
        ],
        [],
        query=(
            "hi, the spa was raided last week and police took me and other girls "
            "to station I just do massage I am scared what will happen now can i file case"
        ),
    )

    assert coverage[0]["found"] is True


def test_stage_e9_eval_accepts_child_deepfake_pocso_and_it_privacy_sources():
    coverage = required_source_coverage(
        [
            "POCSO Act 2012 where a child or minor is shown in sexual content",
            "Information Technology Act 2000 section 67B / 66E / 67A where electronic sexual-image publication or privacy misuse is alleged",
        ],
        [
            {
                "title": "Protection of Children from Sexual Offences Act 2012",
                "anchor": "pocso-2012/sec-13-a",
            },
            {
                "title": "Information Technology Act 2000",
                "anchor": "it-2000/sec-66E",
            },
        ],
        [],
        query=(
            "hi, my schoolmate is making deepfake nude videos of girls in class "
            "using AI n circulating I am one of them I am 15 can i file case"
        ),
    )

    assert [item["found"] for item in coverage] == [True, True]
