import copy
import json
import os

import pytest
from apps.api.legal_issue_plan import PLAN_OWNED_ANSWER_ROUTES
from scripts.audit_release_scope import (
    DEFAULT_SCOPE,
    EVIDENCE_GATES,
    ScopeValidationError,
    _live_projection_blockers,
    _retrieval_hit_matches_authority,
    audit_live_natural_retrieval,
    audit_live_registry_ready_corpus,
    audit_release_scope,
    load_release_scope,
)

from authority_registry import load_authority_registry

REGISTRY_READY = {
    "arrest_custody_station_case_not_disclosed",
    "police_seized_device_return",
    "loan_app_harassment",
    "bank_account_freeze_legal_hold",
    "wrong_bank_debit",
}

REGISTRY_BLOCKED = {
    "lgbtq_identity_arrest_safeguard",
    "vehicle_theft_fir_refusal",
    "domestic_violence_immediate_safety",
    "insurance_claim_or_misselling",
    "consumer_defective_goods",
}


def test_v1_scope_covers_every_plan_owned_scenario_exactly_once():
    scope = load_release_scope()
    candidates = {row["scenario_id"] for row in scope["candidate_scenarios"]}
    excluded = {
        row["scenario_id"] for row in scope["excluded_plan_owned_scenarios"]
    }
    plan_owned = {rule.scenario_id for rule in PLAN_OWNED_ANSWER_ROUTES}

    assert len(scope["lanes"]) == 4
    assert len(candidates) == 10
    assert len(excluded) == 23
    assert candidates.isdisjoint(excluded)
    assert candidates | excluded == plan_owned
    assert all(
        row["fallback_owner"] == "source_gap_handoff"
        for row in scope["excluded_plan_owned_scenarios"]
    )


def test_v1_scope_is_explicitly_no_go_until_evidence_is_attached():
    result = audit_release_scope(load_release_scope())

    assert result["release_decision"] == "no_go"
    assert result["launch_ready"] is False
    assert result["summary"] == {
        "lanes": 4,
        "candidate_scenarios": 10,
        "excluded_plan_owned_scenarios": 23,
        "registry_contract_ready_scenarios": 5,
        "launch_ready_scenarios": 0,
    }
    assert set(result["registry_contract_ready_scenario_ids"]) == REGISTRY_READY
    assert set(result["not_launch_ready_scenario_ids"]) == REGISTRY_READY | REGISTRY_BLOCKED
    assert result["global_blockers"] == [
        "release_decision:no_go",
        "candidate_scenarios_not_ready:10",
    ]


def test_candidate_queries_resolve_to_fail_closed_reviewed_contract_owners():
    result = audit_release_scope(load_release_scope())

    for scenario in result["scenarios"]:
        blockers = scenario["blockers"]
        assert "representative_query_owner_mismatch" not in blockers
        assert "representative_query_owner_token_mismatch" not in blockers
        assert "manifest_owner_token_drift" not in blockers
        assert "owner_fallback_not_fail_closed" not in blockers
        assert "matter_plan_owner_mismatch" not in blockers
        assert "matter_plan_fallback_not_fail_closed" not in blockers
        assert "freeform_llm_allowed" not in blockers
        assert "reviewed_contract_not_required" not in blockers


def test_registry_gaps_are_visible_instead_of_becoming_supported_routes():
    result = audit_release_scope(load_release_scope())
    by_id = {row["scenario_id"]: row for row in result["scenarios"]}

    assert {scenario_id for scenario_id, row in by_id.items() if not row["registry_contract_ready"]} == REGISTRY_BLOCKED
    assert any(
        blocker.endswith(":provisional_authority_id")
        for blocker in by_id["lgbtq_identity_arrest_safeguard"]["blockers"]
    )
    assert any(
        blocker.endswith(":missing_registry_key")
        for blocker in by_id["vehicle_theft_fir_refusal"]["blockers"]
    )
    assert any(
        blocker.endswith(":missing_registry_key")
        for blocker in by_id["domestic_violence_immediate_safety"]["blockers"]
    )
    assert any(
        blocker.endswith(":missing_registry_key")
        for blocker in by_id["insurance_claim_or_misselling"]["blockers"]
    )
    assert any(
        blocker.endswith(":provisional_authority_id")
        for blocker in by_id["consumer_defective_goods"]["blockers"]
    )


def test_passing_evidence_requires_artifact_and_candidate_fingerprint(tmp_path):
    scope = json.loads(DEFAULT_SCOPE.read_text(encoding="utf-8"))
    scope["candidate_scenarios"][0]["evidence"]["natural_retrieval"]["status"] = "passed"
    path = tmp_path / "scope.json"
    path.write_text(json.dumps(scope), encoding="utf-8")

    with pytest.raises(ScopeValidationError, match="passed natural_retrieval needs artifact"):
        load_release_scope(path)


def test_a_go_decision_cannot_promote_scenarios_with_registry_gaps():
    scope = copy.deepcopy(load_release_scope())
    candidate_fingerprint = "a" * 64
    scope["release_decision"] = "go"
    scope["candidate_fingerprint"] = candidate_fingerprint
    for row in scope["candidate_scenarios"]:
        row["support_status"] = "approved"
        for gate_name in EVIDENCE_GATES:
            row["evidence"][gate_name] = {
                "status": "passed",
                "artifact": "README.md",
                "candidate_fingerprint": candidate_fingerprint,
            }

    result = audit_release_scope(scope)

    assert result["release_decision"] == "go"
    assert result["launch_ready"] is False
    assert result["summary"]["launch_ready_scenarios"] == 5
    assert set(result["not_launch_ready_scenario_ids"]) == REGISTRY_BLOCKED
    assert result["global_blockers"] == ["candidate_scenarios_not_ready:5"]


def test_scope_loader_rejects_scenario_inventory_drift(tmp_path):
    scope = json.loads(DEFAULT_SCOPE.read_text(encoding="utf-8"))
    scope["excluded_plan_owned_scenarios"].pop()
    path = tmp_path / "scope.json"
    path.write_text(json.dumps(scope), encoding="utf-8")

    with pytest.raises(ScopeValidationError, match="exactly cover"):
        load_release_scope(path)


def test_live_projection_gate_checks_hash_anchor_and_provenance():
    key = "bharatiya_nagarik_suraksha_sanhita_2023_section_106"
    record = load_authority_registry().by_key(key)
    required = {
        "registry_key": key,
        "authority_id": record.authority_id_expected,
    }
    projection = {
        "authority_id": record.authority_id_expected,
        "record_sha256": record.record_sha256,
        "canonical_anchor": f"{record.provision.canonical_anchor}@2024-07-01",
        "chunk_anchor": f"{record.doc_id}{record.provision.canonical_anchor}@2024-07-01",
        "quarantined": False,
        "provenance_verified": True,
        "provenance_tier": "canonical",
        "raw_sha256": record.provenance.raw_sha256,
        "raw_bytes_size": record.provenance.raw_bytes_size,
    }

    assert _live_projection_blockers(required, projection) == []
    projection["provenance_verified"] = False
    projection["chunk_anchor"] = "bnss-2023/sec-105"
    assert _live_projection_blockers(required, projection) == [
        "canonical_anchor_mismatch",
        "chunk_provenance_unverified",
    ]


def test_natural_retrieval_match_requires_the_exact_document_and_provision():
    required = {
        "registry_key": "rbi_integrated_ombudsman_2021_clause_1",
        "required_anchor_patterns": ["/sec-1", "/clause-1"],
    }

    assert _retrieval_hit_matches_authority(
        {
            "title": "Reserve Bank Integrated Ombudsman Scheme 2021",
            "anchor": "rbi-integrated-ombudsman-2021/sec-1",
        },
        required,
    )
    assert not _retrieval_hit_matches_authority(
        {
            "title": "Consumer Protection Act 2019",
            "anchor": "consumer-protection-act-2019/sec-1",
        },
        required,
    )
    assert not _retrieval_hit_matches_authority(
        {
            "title": "Reserve Bank Integrated Ombudsman Scheme 2021",
            "anchor": "rbi-integrated-ombudsman-2021/sec-3",
        },
        required,
    )


def test_natural_retrieval_gate_reports_missing_authorities_without_injection():
    scope = load_release_scope()
    result = audit_live_natural_retrieval(
        scope,
        audit_release_scope(scope),
        api_base_url="http://unused.invalid",
        search=lambda _query, _top_k: [],
    )

    assert result["ready"] is False
    assert result["summary"] == {
        "registry_contract_ready_scenarios": 5,
        "natural_retrieval_ready_scenarios": 0,
        "required_authority_obligations": 20,
        "found_authority_obligations": 0,
        "micro_recall_at_8": 0.0,
    }
    assert all(row["recall_at_8"] == 0.0 for row in result["scenarios"])


@pytest.mark.needs_stack
@pytest.mark.asyncio
@pytest.mark.skipif(
    os.getenv("LAW_RAG_REAL_DB_TESTS") != "1",
    reason="set LAW_RAG_REAL_DB_TESTS=1 for the live V1 corpus contract",
)
async def test_registry_ready_v1_candidates_have_verified_live_projections():
    result = await audit_live_registry_ready_corpus(
        audit_release_scope(load_release_scope())
    )

    assert result["ready"] is True
    assert result["summary"] == {
        "registry_contract_ready_scenarios": 5,
        "live_corpus_ready_scenarios": 5,
        "required_authorities": 12,
        "live_corpus_ready_authorities": 12,
    }
    assert all(not row["blockers"] for row in result["scenarios"])
    assert all(not row["blockers"] for row in result["authorities"])
