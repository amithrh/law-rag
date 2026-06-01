from __future__ import annotations

from apps.api.legal_issue_plan import build_legal_issue_plan
from apps.api.matter_router import route_matter


def _plan(query: str):
    route = route_matter(query)
    plan = build_legal_issue_plan(query, route)
    assert plan is not None
    return route, plan.to_event()


def test_legal_issue_plan_none_for_off_topic():
    query = "who will win the cricket match tomorrow"
    route = route_matter(query)

    assert route.category == "off_topic"
    assert build_legal_issue_plan(query, route) is None


def test_legal_issue_plan_consumer_customer_role_and_authorities():
    route, plan = _plan("online order arrived broken what to do")

    assert route.category == "consumer"
    assert plan["schema_version"] == 1
    assert plan["primary_issue"] == "consumer"
    assert plan["user_role"] == "consumer_or_customer"
    assert plan["desired_outcome"] in {"complaint_or_grievance", "refund_or_compensation"}
    assert plan["authority_ledger"][0]["act"] == "Consumer Protection Act 2019"
    assert plan["authority_ledger"][0]["priority"] == "must_cite"


def test_legal_issue_plan_tracks_multilabel_medical_negligence():
    _, plan = _plan("doctor operated wrong leg in hospital what can we do")

    assert plan["user_role"] == "patient_or_family"
    assert "medical_negligence" in plan["secondary_issues"]
    assert "consumer_compensation" in plan["secondary_issues"]


def test_legal_issue_plan_accused_framing_guard_for_cyber_notice():
    _, plan = _plan("police sent me notice in cyber fraud case and i am accused what to do")

    assert plan["user_role"] == "accused_or_accused_family"
    assert plan["case_stage"] == "notice_stage"
    assert plan["desired_outcome"] == "defence_or_notice_response"
    assert "incident_date_needed" in plan["safety_flags"]
    assert "accused_framing_guard" in plan["safety_flags"]
    regime_entries = [
        entry for entry in plan["authority_ledger"]
        if entry["act"] == "date-dependent criminal regime"
    ]
    assert regime_entries
    assert regime_entries[0]["priority"] == "conditional"
    assert regime_entries[0]["must_cite"] is False


def test_legal_issue_plan_jurisdiction_and_date_flags():
    route, plan = _plan("my tenant is not vacating house and not paying rent in Pune")

    assert route.category == "property_tenancy"
    assert plan["user_role"] == "landlord"
    assert plan["jurisdiction"]["city"] == "pune"
    assert plan["jurisdiction"]["state"] == "maharashtra"
    assert plan["desired_outcome"] == "eviction_or_possession"
    assert "state_or_city_needed" not in plan["safety_flags"]


def test_legal_issue_plan_senior_parent_role_not_patient_by_default():
    route, plan = _plan("my senior citizen father gifted flat to daughter now she is not maintaining him")

    assert route.category == "senior_citizen"
    assert plan["user_role"] == "senior_citizen_or_family"


def test_legal_issue_plan_senior_eviction_not_misread_as_generic_parent():
    route, plan = _plan("my son threw me out of my own house i paid for it in 1985 mumbai")

    assert route.category == "senior_citizen"
    assert plan["user_role"] == "senior_citizen_or_family"


def test_legal_issue_plan_hospital_wrong_limb_role_is_patient_family():
    route, plan = _plan("hospital operated wrong leg on my 80 yr old father what can we do")

    assert route.category == "consumer"
    assert plan["user_role"] == "patient_or_family"


def test_legal_issue_plan_generic_hr_pip_does_not_leak_posh_secondary():
    route, plan = _plan("i complained against my manager for harassment to HR and now they are putting me on PIP, is this retaliation")

    assert route.category == "employment_wages"
    assert "employment_retaliation" in plan["secondary_issues"]
    assert "workplace_sexual_harassment" not in plan["secondary_issues"]
    assert plan["user_role"] == "employee_or_worker"


def test_legal_issue_plan_posh_pip_keeps_posh_secondary():
    route, plan = _plan("complained about sexual harassment by my manager to HR and now he gave PIP bad rating")

    assert route.category == "workplace_sexual_harassment"
    assert plan["primary_issue"] == "workplace_sexual_harassment"
    assert "employment_retaliation" in plan["secondary_issues"]


def test_legal_issue_plan_family_property_not_patient_by_default():
    route, plan = _plan("my father sold ancestral land without asking me what can i do")

    assert route.category != "consumer"
    assert plan["user_role"] != "patient_or_family"


def test_legal_issue_plan_common_category_defaults_are_not_unknown():
    cases = {
        "spotify took down my remix song fair use ya legal copyright issue": "creator_or_rights_holder",
        "hi, rule 86B applies to me turnover 55 lakh per month must pay 1% cash mandatory ya choot hai": "taxpayer_or_business",
        "urgent procedure to file insolvency petition against company in NCLT how to complain": "creditor_debtor_or_company_stakeholder",
        "sir ASHA worker not paid honorarium 6 months who can help where to go": "employee_or_worker",
        "can u tell nrega 28 days work done village mukhiya not paid since 6 months gadchiroli maharashtra": "employee_or_worker",
        "data breach at byjus my pan and aadhaar leaked can i claim compensation under DPDP act": "complainant_or_victim",
    }
    for query, expected_role in cases.items():
        _, plan = _plan(query)
        assert plan["user_role"] == expected_role


def test_legal_issue_plan_environment_project_extracts_affected_role_and_district():
    route, plan = _plan("DM gave NOC to bauxite project bastar without gram sabha resolution how to challenge")

    assert route.category == "environment_compensation"
    assert plan["user_role"] == "affected_resident_or_landholder"
    assert plan["jurisdiction"]["city"] == "bastar"
    assert plan["jurisdiction"]["state"] == "chhattisgarh"
    assert plan["desired_outcome"] == "project_approval_or_compensation"


def test_legal_issue_plan_undertrial_and_order_stages_are_explicit():
    _, undertrial = _plan("need help i undertrial 3 yrs in puzhal lawyer not coming hearings when can complain")
    assert undertrial["user_role"] == "accused_or_accused_family"
    assert undertrial["case_stage"] == "custody_or_trial_pending"
    assert undertrial["jurisdiction"]["city"] == "puzhal"
    assert undertrial["jurisdiction"]["state"] == "tamil nadu"

    _, support = _plan("ex husband not paying child support of 25000 per month as per court order 8 months pending")
    assert support["case_stage"] == "order_or_decree_exists"
    assert support["desired_outcome"] == "maintenance_enforcement"


def test_legal_issue_plan_notice_under_is_category_aware_not_accused_by_default():
    cases = [
        (
            "bank sent me notice under sarfaesi section 13(2)",
            "banking_credit_dispute",
            "bank_customer_or_borrower",
            "sarfaesi_or_banking_notice_response",
        ),
        (
            "gst notice under section 73 received",
            "tax_gst_compliance",
            "taxpayer_or_business",
            "tax_notice_response",
        ),
        (
            "landlord sent me notice under rent act to vacate",
            "property_tenancy",
            "tenant",
            "tenancy_notice_response",
        ),
        (
            "notice under consumer complaint from customer received by my shop",
            "consumer",
            "business_or_service_provider_respondent",
            "consumer_notice_response",
        ),
        (
            "police sent me notice under 41a but i am witness",
            "criminal_general",
            "witness_or_notice_recipient",
            "witness_notice_response",
        ),
    ]
    for query, category, role, outcome in cases:
        route, plan = _plan(query)
        assert route.category == category
        assert plan["user_role"] == role
        assert plan["case_stage"] == "notice_stage"
        assert plan["desired_outcome"] == outcome


def test_legal_issue_plan_accused_word_does_not_steal_victim_or_witness_context():
    victim_queries = [
        "the accused got bail and is threatening me what can i do",
        "accused got bail and threatening me what can i do",
        "accused is threatening me after bail what to do",
        "main accused came to my house after bail and threatened me",
    ]
    for query in victim_queries:
        _, victim = _plan(query)
        assert victim["user_role"] == "complainant_or_victim"
        assert victim["desired_outcome"] == "victim_protection_or_bail_cancellation"

    _, witness = _plan("witness saw accused but police not recording statement")
    assert witness["user_role"] == "witness_or_complainant"
    assert witness["desired_outcome"] == "witness_statement_or_police_followup"

    _, witness_threat = _plan("accused in my case is harassing me and witness")
    assert witness_threat["user_role"] == "witness_or_complainant"
    assert witness_threat["desired_outcome"] == "victim_or_witness_protection_followup"

    _, accused = _plan("police sent me notice in cyber fraud case and i am accused what to do")
    assert accused["user_role"] == "accused_or_accused_family"
    assert accused["desired_outcome"] == "defence_or_notice_response"

    _, brother = _plan("my brother is accused and got bail what to do")
    assert brother["user_role"] == "accused_or_accused_family"
    assert brother["desired_outcome"] == "bail_or_release"

    _, son = _plan("my son is accused in FIR what should we do")
    assert son["user_role"] == "accused_or_accused_family"
    assert son["desired_outcome"] == "defence_or_notice_response"

    accused_queries = [
        "my son is accused in FIR what to do",
        "i have been accused in cyber fraud case what to do",
        "my brother was accused falsely in fir what to do",
    ]
    for query in accused_queries:
        _, plan = _plan(query)
        assert plan["user_role"] == "accused_or_accused_family"
        assert plan["desired_outcome"] == "defence_or_notice_response"


def test_legal_issue_plan_active_accused_voice_stays_complainant_side():
    complainant_queries = [
        "i accused him of fraud but police not filing fir what to do",
        "i accused company of cheating consumer what to do next",
        "my son accused neighbour of assault police not filing fir",
        "my daughter accused neighbour of assault police not filing fir",
        "my father accused neighbour of assault police not filing fir",
        "my brother accused shopkeeper of cheating but no fir",
    ]
    for query in complainant_queries:
        _, plan = _plan(query)
        assert plan["user_role"] != "accused_or_accused_family"
        assert plan["desired_outcome"] != "defence_or_notice_response"


def test_legal_issue_plan_victim_bail_opposition_is_not_accused_release():
    cases = [
        ("i accused him of fraud need bail cancellation", "complainant_or_victim"),
        ("my son accused neighbour of assault need bail cancellation", "complainant_or_victim"),
        ("accused in my case applying bail how oppose", "complainant_or_victim"),
        ("the accused filed bail application how to oppose", "complainant_or_victim"),
        (
            "rape survivor wants to oppose anticipatory bail of accused",
            "sexual_offence_survivor_or_complainant",
        ),
    ]
    for query, role in cases:
        _, plan = _plan(query)
        assert plan["user_role"] == role
        assert plan["desired_outcome"] == "victim_protection_or_bail_cancellation"


def test_legal_issue_plan_minor_mineral_pesa_does_not_force_rfctlarr():
    route, plan = _plan("sand mining lease given without gram sabha consent in scheduled area")
    acts = [entry["act"] or "" for entry in plan["authority_ledger"]]

    assert route.label == "Minor mineral / Gram Sabha recommendation"
    assert any("PESA Act 1996" in act for act in acts)
    assert any("Mines and Minerals" in act for act in acts)
    assert not any("RFCTLARR" in act or "Fair Compensation" in act for act in acts)


def test_legal_issue_plan_extracts_pwdva_acronym_as_must_cite_act():
    _, plan = _plan("my husband hit me and took my salary what to do")
    first = plan["authority_ledger"][0]

    assert first["source"].startswith("PWDVA 2005")
    assert first["act"] == "Protection of Women from Domestic Violence Act 2005"
    assert first["must_cite"] is True
