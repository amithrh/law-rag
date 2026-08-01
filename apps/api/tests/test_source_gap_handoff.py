from __future__ import annotations

import json

from apps.api.main import _source_gap_handoff_event
from apps.api.matter_router import route_matter
from apps.api.legal_issue_plan import build_matter_plan


def test_source_gap_handoff_is_actionable_but_makes_no_legal_conclusion():
    query = "my shop is sealed by the municipality what can I do"
    route = route_matter(query)
    plan = build_matter_plan(query, route)

    event = _source_gap_handoff_event(route, plan)
    payload = json.loads(event["data"])

    assert event["event"] == "sentence"
    assert payload["status"] == "guidance"
    assert payload["citations"] == []
    assert payload["reason"] == "source-gap intake handoff; no unsupported legal conclusion"
    assert "what you can do next" in payload["text"].lower()
    assert "not a conclusion about your rights or deadline" in payload["text"].lower()


def test_source_gap_handoff_marks_critical_routes_as_non_answer():
    query = "police arrested my son and we need bail help"
    route = route_matter(query)
    plan = build_matter_plan(query, route)
    assert plan is not None

    event = _source_gap_handoff_event(
        route,
        plan,
        {"has_gap": True, "missing_required_sources": [{"required_source": "BNSS 2023"}]},
        reason="low_coverage",
    )
    payload = event["source_gap"]

    assert payload["outcome"] == "source_gap_handoff"
    assert payload["safe_handoff_only"] is True
    assert payload["reason"] == "low_coverage"
def test_source_gap_handoff_allowlists_untrusted_gap_fields():
    query = "online order arrived broken what to do"
    route = route_matter(query)
    plan = build_matter_plan(query, route)

    event = _source_gap_handoff_event(
        route,
        plan,
        {
            "has_gap": False,
            "route_category": "forged_route",
            "gap_kinds": ["missing_required_authority"],
            "missing_required_sources": [{"required_source": "CPA 2019", "kind": "missing", "extra": "drop"}],
            "message": "safe message",
            "handoff": "unsafe forum route",
            "policy": "do_not_substitute_neighboring_authority",
            "deadline": "drop this",
            "remedy": "drop this too",
        },
        reason="test_allowlist",
    )
    payload = event["source_gap"]

    assert payload["has_gap"] is True
    assert payload["route_category"] == route.category
    assert payload["handoff"] == "DLSA/legal aid or a qualified lawyer"
    assert payload["missing_required_sources"] == [{
        "required_source": "CPA 2019",
        "kind": "missing",
    }]
    assert "deadline" not in payload
    assert "remedy" not in payload
    assert payload["safe_handoff_only"] is True


def test_source_gap_handoff_preserves_authority_audit_metadata():
    query = "my customer gave me a cheque and it bounced"
    route = route_matter(query)
    event = _source_gap_handoff_event(
        route,
        build_matter_plan(query, route),
        {
            "has_gap": True,
            "missing_required_sources": [{
                "required_source": "Negotiable Instruments Act 1881",
                "kind": "national_statute_retrieval_gap",
                "authority_id": "authority_123",
                "source_pack_id": "ni_act_1881",
                "identity_status": "canonical",
                "match_mode": "legacy_provisional",
                "required_anchor_patterns": ["/sec-138"],
            }],
        },
        reason="required_source_gap",
    )

    assert event["source_gap"]["missing_required_sources"] == [{
        "required_source": "Negotiable Instruments Act 1881",
        "kind": "national_statute_retrieval_gap",
        "authority_id": "authority_123",
        "source_pack_id": "ni_act_1881",
        "identity_status": "canonical",
        "match_mode": "legacy_provisional",
        "required_anchor_patterns": ["/sec-138"],
    }]
