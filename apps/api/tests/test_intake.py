from __future__ import annotations

import json

from apps.api.intake import build_intake_event
from apps.api.legal_issue_plan import build_matter_plan
from apps.api.main import _initial_route_events
from apps.api.matter_router import criminal_transition_status, route_matter
from apps.api.source_gap import build_source_gap_event


def _event(query: str) -> dict:
    route = route_matter(query)
    plan = build_matter_plan(query, route)
    result = build_intake_event(query, route, plan)
    assert result is not None
    return result


def test_intake_is_bounded_private_and_route_specific_for_bank_holds():
    event = _event("my bank account is frozen what to do")

    assert event["schema_version"] == 1
    assert len(event["questions"]) <= 3
    ids = {question["id"] for question in event["questions"]}
    assert "bank_hold_reason" in ids
    assert "document_status" in ids
    assert all("Aadhaar" not in question["prompt"] for question in event["questions"])
    assert "full bank" in event["privacy_note"]
    assert all("FIR" not in question["prompt"] for question in event["questions"])


def test_device_intake_asks_transition_fact_not_seizure_date_shortcut():
    query = "Police seized my phone in May 2023 and will not return it"
    event = _event(query)
    transition = next(question for question in event["questions"] if question["id"] == "criminal_transition")

    assert "pending immediately before 1 July 2024" in transition["prompt"]
    assert not any(question["id"] == "incident_date" for question in event["questions"])


def test_device_year_alone_does_not_answer_the_transition_question():
    for date_phrase in (
        "in 2023",
        "in 2025",
        "before 1 July 2024",
        "after 1 July 2024",
    ):
        query = f"Police seized my phone {date_phrase} and will not return it"
        event = _event(query)

        assert "criminal_transition" in {question["id"] for question in event["questions"]}


def test_emergency_intake_puts_current_safety_first():
    event = _event("my husband is beating me right now")

    assert event["questions"][0]["id"] == "current_safety"
    assert event["questions"][0]["input_type"] == "choice"
    assert event["questions"][0]["options"]


def test_arrest_intake_does_not_treat_the_word_arrested_as_full_case_stage():
    event = _event("police arrested my son for being gay")
    ids = [question["id"] for question in event["questions"]]

    assert "case_stage" in ids
    assert "document_status" in ids
    assert len(ids) == len(set(ids))


def test_transition_and_generic_incident_date_are_not_duplicate_questions():
    query = "Police did not file my FIR. What can I do?"
    event = _event(query)
    ids = [question["id"] for question in event["questions"]]

    assert "criminal_transition" in ids
    assert "incident_date" not in ids


def test_insurance_intake_asks_for_policy_and_rejection_papers():
    event = _event("insurer is rejecting my claim")
    prompts = " ".join(question["prompt"] for question in event["questions"])

    assert "policy" in prompts.lower()
    assert "insurer" in prompts.lower()
    assert "invoice/order" not in prompts


def test_generic_state_question_does_not_count_as_a_jurisdiction_answer():
    event = _event("which state's RERA rules apply to my delayed builder possession?")

    assert "jurisdiction" in {question["id"] for question in event["questions"]}


def test_state_name_without_city_keeps_jurisdiction_intake_question():
    event = _event("employer paying below minimum wage in Gujarat")

    assert "jurisdiction" in {question["id"] for question in event["questions"]}


def test_bank_choice_answer_is_not_asked_again_on_refinement():
    query = "my bank account is frozen what to do\n\nAdditional facts:\nbank_hold_reason: Cyber or police"
    route = route_matter(query)
    plan = build_matter_plan(query, route)
    event = build_intake_event(query, route, plan)

    assert event is not None
    assert "bank_hold_reason" not in {question["id"] for question in event["questions"]}


def test_transition_choice_answers_are_consumed_by_the_router():
    base = "Police seized my phone and will not return it"

    saved = criminal_transition_status(
        f"{base}\n\nAdditional facts:\ncriminal_transition: Pending immediately before 1 July 2024"
    )
    assert saved == "saved_crpc"

    current = criminal_transition_status(
        f"{base}\n\nAdditional facts:\ncriminal_transition: Started on or after 1 July 2024"
    )
    assert current == "current_bnss"

    concluded = criminal_transition_status(
        f"{base}\n\nAdditional facts:\ncriminal_transition: Concluded before 1 July 2024"
    )
    assert concluded == "unknown"

    unknown = criminal_transition_status(
        f"{base}\n\nAdditional facts:\ncriminal_transition: Unknown"
    )
    assert unknown == "unknown"


def test_initial_route_events_emit_intake_after_the_matter_plan():
    query = "my bank account is frozen what to do"
    route = route_matter(query)
    plan = build_matter_plan(query, route)
    events = _initial_route_events(route, plan, query)
    names = [event["event"] for event in events]

    assert names[:3] == ["matter_route", "matter_plan", "intake"]
    intake = json.loads(events[2]["data"])
    assert intake["questions"]


def test_source_gap_route_keeps_safe_intake_logistics_without_authority_claims():
    query = "online order arrived broken what to do"
    route = route_matter(query)
    plan = build_matter_plan(query, route)
    events = _initial_route_events(
        route,
        plan,
        query,
        source_gap_event={
            "has_gap": True,
            "outcome": "source_gap_handoff",
            "safe_handoff_only": True,
            "gap_kinds": ["missing_required_authority"],
        },
    )

    route_event = json.loads(events[0]["data"])
    assert route_event["intake_only"] is True
    assert route_event["forums"] == []
    assert route_event["action_pack"]["id"] == route.action_pack.id
    assert route_event["action_pack"]["next_steps"] == []
    assert route_event["action_pack"]["documents"] == []
    assert route_event["action_pack"]["portals"] == []
    assert route_event["action_pack"]["escalation"] == []
    assert route_event["required_sources"] == []
    assert route_event["legal_regime"] is None
    assert [event["event"] for event in events] == ["matter_route", "source_gap"]


def test_malformed_source_gap_withholds_plan_without_emitting_retry_intake():
    query = "online order arrived broken what to do"
    route = route_matter(query)
    plan = build_matter_plan(query, route)
    events = _initial_route_events(
        route,
        plan,
        query,
        source_gap_event={
            "has_gap": True,
            "outcome": "source_gap_handoff",
            "gap_kinds": "state_or_local_authority_gap",
        },
    )

    assert [event["event"] for event in events] == ["matter_route", "source_gap"]
    route_event = json.loads(events[0]["data"])
    assert route_event["intake_only"] is True
    assert route_event["forums"] == []


def test_non_dict_source_gap_payload_is_canonicalized_and_withholds_plan():
    query = "online order arrived broken what to do"
    route = route_matter(query)
    plan = build_matter_plan(query, route)

    for malformed in ([], "bad", 7):
        events = _initial_route_events(
            route,
            plan,
            query,
            source_gap_event=malformed,
        )
        assert [event["event"] for event in events] == ["matter_route", "source_gap"]
        gap = json.loads(events[1]["data"])
        assert gap["outcome"] == "source_gap_handoff"
        assert gap["safe_handoff_only"] is True
        route_event = json.loads(events[0]["data"])
        assert route_event["intake_only"] is True
        assert route_event["forums"] == []


def test_jurisdictional_source_gap_offers_bounded_retry_intake_without_a_plan():
    query = "auto permit expired in Chennai how to renew Tamil Nadu"
    route = route_matter(query)
    plan = build_matter_plan(query, route)
    events = _initial_route_events(
        route,
        plan,
        query,
        source_gap_event={
            "has_gap": True,
            "outcome": "source_gap_handoff",
            "safe_handoff_only": True,
            "gap_kinds": ["state_or_local_authority_gap"],
        },
    )

    assert [event["event"] for event in events] == ["matter_route", "source_gap", "intake"]
    route_event = json.loads(events[0]["data"])
    assert route_event["intake_only"] is True
    intake = json.loads(events[2]["data"])
    assert intake["schema_version"] == 1
    assert intake["intake_kind"] == "source_gap_facts"
    assert intake["route_category"] == route.category
    assert len(intake["questions"]) <= 3
    assert intake["questions"][0]["id"] == "incident_date"
    assert "jurisdiction" not in {
        question["id"] for question in intake["questions"]
    }
    assert route_event["forums"] == []


def test_integrity_first_local_gap_preserves_bounded_intake():
    query = "my shop is in Gujarat and municipality sealed it"
    route = route_matter(query)
    plan = build_matter_plan(query, route)
    source_gap = build_source_gap_event(
        query=query,
        route_category=route.category,
        required_sources=route.required_sources,
        passages=[],
        plan=plan,
    )
    assert source_gap is not None
    events = _initial_route_events(
        route,
        plan,
        query,
        source_gap_event=source_gap,
        intake_only=True,
    )
    assert [event["event"] for event in events] == ["matter_route", "source_gap", "intake"]
    intake = json.loads(events[2]["data"])
    assert intake["intake_kind"] == "source_gap_facts"
    assert intake["route_category"] == route.category
