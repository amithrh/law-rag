from scripts.audit_answer_ownership import audit_failures, audit_rows, markdown_report


class _Args:
    max_unexpected_owners = 0
    max_critical_llm_owners = 0


def test_ownership_audit_flags_unexpected_owner_and_critical_llm_fallback():
    summary = audit_rows([
        {
            "query": "bank deducted money wrongly",
            "route_category": "banking_credit_dispute",
            "workflow_answer_owner": "legacy_grounded_template",
            "expected_answer_owner": "authority_graph",
            "workflow_id": "wrong_bank_debit",
            "product_priority": "medium",
        },
        {
            "query": "police arrested my son without FIR copy",
            "route_category": "arrest_custody_safeguard",
            "workflow_answer_owner": "llm",
            "product_priority": "critical",
        },
    ])

    assert len(summary["unexpected_owners"]) == 1
    assert len(summary["critical_llm_owners"]) == 1
    assert audit_failures(summary, _Args()) == [
        "unexpected answer owners: 1 > 0",
        "critical LLM owners: 1 > 0",
    ]


def test_ownership_audit_records_legacy_shadow_without_calling_it_an_owner_mismatch():
    summary = audit_rows([
        {
            "query": "defective material supplier refusing refund",
            "route_category": "business_contract_partnership",
            "workflow_answer_owner": "legacy_grounded_template",
            "expected_answer_owner": "legacy_grounded_template",
            "workflow_shadowed_by_legacy": True,
            "shadowed_workflow_id": "business_contract_first_action",
            "product_priority": "medium",
        },
    ])

    report = markdown_report(summary, [], "results.jsonl")

    assert len(summary["legacy_shadows"]) == 1
    assert summary["unexpected_owners"] == []
    assert "business_contract_first_action" in report
