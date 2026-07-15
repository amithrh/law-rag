from __future__ import annotations

from scripts.eval_launch_holdout_gate import (
    add_launch_failures,
    is_true_holdout_prompt,
    summarize_launch,
    validate_prompt_metadata,
)


def test_launch_holdout_metadata_requires_hard_labels():
    rows = [
        {
            "query": "police kept my brother five days no magistrate",
            "id": "lh-001",
            "eval_split": "lawyer_holdout_v1",
            "label_source": "manual_independent",
            "product_priority": "critical",
            "expected_route_any": ["arrest_custody_safeguard"],
            "expected_controlling_source_any": ["Article 22", "BNSS 24-hour production"],
            "must_include_any": ["24 hours", "magistrate"],
            "forbidden_answer_any": ["wait and see"],
        },
        {
            "query": "bank deducted money wrongly",
            "id": "bad-row",
            "product_priority": "urgent",
        },
    ]

    errors = validate_prompt_metadata(rows)

    fields = {(item["row_id"], item["field"]) for item in errors}
    assert ("lh-001", "product_priority") not in fields
    assert ("bad-row", "eval_split") in fields
    assert ("bad-row", "label_source") in fields
    assert ("bad-row", "product_priority") in fields
    assert ("bad-row", "expected_route_any") in fields
    assert ("bad-row", "authority_or_source_gap_policy") in fields
    assert ("bad-row", "must_cover_terms") in fields


def test_launch_gate_blocks_llm_owned_critical_answers():
    rows = [
        {
            "query": "my 14 year old girlfriend father filed pocso on me",
            "product_priority": "critical",
            "route_category": "criminal_defence_bail",
            "workflow_answer_owner": "llm",
            "route_required_sources_missing": [],
            "product_failures": [],
            "product_pass": True,
        }
    ]

    add_launch_failures(rows, {})

    assert rows[0]["product_pass"] is False
    assert "llm_owned_critical_route" in rows[0]["product_failures"]
    assert "non_reviewed_critical_route_owner" in rows[0]["product_failures"]


def test_launch_gate_blocks_legacy_template_owned_critical_answers():
    rows = [
        {
            "query": "police not taking FIR after assault",
            "product_priority": "critical",
            "route_category": "police_fir",
            "workflow_answer_owner": "legacy_grounded_template",
            "workflow_answer_mode": "legacy",
            "route_required_sources_missing": [],
            "product_failures": [],
            "product_pass": True,
        }
    ]

    add_launch_failures(rows, {})

    assert rows[0]["product_pass"] is False
    assert "llm_owned_critical_route" not in rows[0]["product_failures"]
    assert "non_reviewed_critical_route_owner" in rows[0]["product_failures"]


def test_launch_gate_allows_reviewed_primary_critical_contract():
    rows = [
        {
            "query": "police arrested adult for being gay",
            "product_priority": "critical",
            "route_category": "arrest_custody_safeguard",
            "workflow_answer_owner": "authority_graph",
            "workflow_answer_mode": "safety_primary",
            "route_required_sources_missing": [],
            "source_gap_visible": False,
            "product_failures": [],
            "product_pass": True,
        }
    ]

    add_launch_failures(rows, {})

    assert rows[0]["product_pass"] is True
    assert rows[0]["product_failures"] == []


def test_launch_gate_treats_bonded_labour_as_critical_route():
    rows = [
        {
            "query": "contractor locked workers and not allowing them to leave",
            "product_priority": "high",
            "route_category": "bonded_labour_rescue",
            "workflow_answer_owner": "llm",
            "workflow_answer_mode": "llm",
            "route_required_sources_missing": [],
            "product_failures": [],
            "product_pass": True,
        }
    ]

    add_launch_failures(rows, {})

    assert rows[0]["product_pass"] is False
    assert "llm_owned_critical_route" in rows[0]["product_failures"]
    assert "non_reviewed_critical_route_owner" in rows[0]["product_failures"]


def test_launch_gate_requires_visible_source_gap_for_missing_authority():
    rows = [
        {
            "query": "tribal land transferred to non tribal buyer odisha",
            "product_priority": "critical",
            "route_category": "tribal_caste_atrocity",
            "workflow_answer_owner": "common_workflow_contracts",
            "route_required_sources_missing": ["Odisha scheduled-area land-transfer source"],
            "source_gap_visible": False,
            "product_failures": [],
            "product_pass": True,
        }
    ]

    add_launch_failures(rows, {})

    assert rows[0]["product_pass"] is False
    assert "source_gap_not_visible_to_user" in rows[0]["product_failures"]


def test_launch_gate_fails_visible_source_gap_even_when_disclosed():
    rows = [
        {
            "query": "tribal land transferred to non tribal buyer odisha",
            "product_priority": "critical",
            "route_category": "tribal_caste_atrocity",
            "workflow_answer_owner": "common_workflow_contracts",
            "workflow_answer_mode": "primary",
            "route_required_sources_missing": ["Odisha scheduled-area land-transfer source"],
            "source_gap_visible": True,
            "product_failures": [],
            "product_pass": True,
        }
    ]

    add_launch_failures(rows, {})

    assert rows[0]["product_pass"] is False
    assert "visible_source_gap" in rows[0]["product_failures"]
    assert "source_gap_not_visible_to_user" not in rows[0]["product_failures"]


def test_launch_summary_counts_true_holdout_rows():
    prompts = [
        {"query": "a", "eval_split": "lawyer_holdout_v1", "label_source": "manual_independent"},
        {"query": "b", "eval_split": "generated_fresh", "label_source": "synthetic"},
    ]
    rows = [
        {"product_failures": ["llm_owned_critical_route"]},
        {"product_failures": ["source_gap_not_visible_to_user"]},
    ]

    metrics = summarize_launch(rows, prompts, metadata_errors=[{"field": "x", "query": "b", "row_id": "b"}])

    assert metrics["true_holdout_rows"] == 1
    assert metrics["metadata_error_count"] == 1
    assert metrics["llm_owned_critical_rows"] == 1
    assert metrics["non_reviewed_critical_rows"] == 0
    assert metrics["missing_visible_source_gap_rows"] == 1


def test_synthetic_regression_probe_is_not_true_holdout():
    assert is_true_holdout_prompt({
        "query": "real reviewed row",
        "eval_split": "lawyer_holdout_v1",
        "label_source": "manual_independent",
    }) is True
    assert is_true_holdout_prompt({
        "query": "synthetic regression row",
        "eval_split": "stage3_refusal_probe_holdout",
        "label_source": "manual_independent",
        "synthetic_note": "regression prompt copied from Stage 2 live refusal set; not a real user log",
    }) is False
