"""Structured legal issue planning scaffold.

This module is Milestone A of the plan-first answer architecture. It does not
change answer generation yet; it creates a typed, serializable plan from the
current matter route so evals and logs can expose what the system thinks the
legal task is before retrieval/generation repair work begins.
"""
from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from typing import Literal

from .matter_router import MatterRoute


AuthorityPriority = Literal["must_cite", "conditional", "background"]


@dataclass(frozen=True)
class JurisdictionPlan:
    state: str | None = None
    city: str | None = None
    forum_mentioned: str | None = None
    needs_state: bool = False


@dataclass(frozen=True)
class AuthorityLedgerEntry:
    source: str
    act: str | None = None
    section: str | None = None
    source_pack_id: str | None = None
    claim_type: str = "legal_basis"
    priority: AuthorityPriority = "must_cite"
    must_cite: bool = True
    conditional: bool = False
    note: str | None = None


@dataclass(frozen=True)
class LegalIssuePlan:
    schema_version: int
    primary_issue: str
    primary_label: str
    confidence: float
    user_role: str
    jurisdiction: JurisdictionPlan
    incident_date_status: str
    case_stage: str
    desired_outcome: str
    urgency: str
    secondary_issues: list[str] = field(default_factory=list)
    required_facts: list[str] = field(default_factory=list)
    authority_ledger: list[AuthorityLedgerEntry] = field(default_factory=list)
    forums: list[str] = field(default_factory=list)
    next_steps: list[str] = field(default_factory=list)
    safety_flags: list[str] = field(default_factory=list)

    def to_event(self) -> dict:
        return asdict(self)


_STATE_TERMS = (
    "andhra pradesh", "arunachal pradesh", "assam", "bihar", "chhattisgarh",
    "delhi", "goa", "gujarat", "haryana", "himachal pradesh", "jharkhand",
    "karnataka", "kerala", "madhya pradesh", "maharashtra", "manipur",
    "meghalaya", "mizoram", "nagaland", "odisha", "orissa", "punjab",
    "rajasthan", "sikkim", "tamil nadu", "telangana", "tripura",
    "uttar pradesh", "uttarakhand", "west bengal",
)

_CITY_TO_STATE = {
    "ahmedabad": "gujarat",
    "angul": "odisha",
    "bandra": "maharashtra",
    "bengaluru": "karnataka",
    "bangalore": "karnataka",
    "bastar": "chhattisgarh",
    "bhopal": "madhya pradesh",
    "chennai": "tamil nadu",
    "cuddalore": "tamil nadu",
    "delhi": "delhi",
    "dindori": "madhya pradesh",
    "gadchiroli": "maharashtra",
    "hyderabad": "telangana",
    "hazaribagh": "jharkhand",
    "jaipur": "rajasthan",
    "keonjhar": "odisha",
    "kolkata": "west bengal",
    "lucknow": "uttar pradesh",
    "mahabaleshwar": "maharashtra",
    "morbi": "gujarat",
    "mumbai": "maharashtra",
    "nagpur": "maharashtra",
    "noida": "uttar pradesh",
    "nuapada": "odisha",
    "patna": "bihar",
    "pune": "maharashtra",
    "puzhal": "tamil nadu",
    "ranchi": "jharkhand",
    "surat": "gujarat",
}

_FORUM_TERMS = (
    "high court", "supreme court", "family court", "consumer commission",
    "district commission", "nclt", "tribunal", "labour court",
    "police station", "magistrate", "dlsa", "ombudsman",
)

_CRIMINAL_CATEGORIES = {
    "arrest_custody_safeguard",
    "criminal_defence_bail",
    "criminal_general",
    "criminal_procedure_notice",
    "police_fir",
    "sexual_offence_survivor",
    "undertrial_review_release",
}

_CATEGORY_DEFAULT_ROLES = {
    "banking_credit_dispute": "bank_customer_or_borrower",
    "business_contract_partnership": "business_owner_or_contract_party",
    "business_license_compliance": "business_owner_or_compliance_applicant",
    "consumer": "consumer_or_customer",
    "court_procedure": "litigant_or_case_party",
    "criminal_defence_bail": "accused_or_accused_family",
    "criminal_general": "criminal_case_party",
    "cyber_fraud_or_harassment": "complainant_or_victim",
    "digital_platform_account": "consumer_or_platform_user",
    "election_voter_rights": "voter_or_applicant",
    "environment_compensation": "affected_resident_or_landholder",
    "family_domestic": "spouse_or_family_member",
    "family_marriage_status": "spouse_or_family_member",
    "ibc_nclt": "creditor_debtor_or_company_stakeholder",
    "labour_compliance": "employer_or_manager",
    "labour_exploitation_discrimination": "worker_or_beneficiary",
    "police_fir": "complainant_or_victim",
    "sexual_offence_survivor": "sexual_offence_survivor_or_complainant",
    "social_welfare_identity": "benefit_or_document_applicant",
    "succession_inheritance": "heir_or_family_member",
    "tax_gst_compliance": "taxpayer_or_business",
    "trademark_ip": "creator_or_rights_holder",
    "tribal_caste_atrocity": "tribal_or_forest_rights_claimant",
    "undertrial_review_release": "accused_or_accused_family",
    "workplace_injury_compensation": "injured_worker_or_family",
    "workplace_sexual_harassment": "workplace_harassment_complainant",
}


def build_legal_issue_plan(query: str, route: MatterRoute) -> LegalIssuePlan | None:
    """Build a serializable plan scaffold from the current route.

    Off-topic queries intentionally return None. The plan is diagnostic and
    preparatory in this milestone; later milestones should make retrieval and
    answer rendering consume it directly.
    """
    if route.category == "off_topic":
        return None

    q = _normalize(query)
    jurisdiction = _extract_jurisdiction(q, route)
    user_role = _extract_user_role(q, route.category)
    incident_status = _incident_date_status(q, route)
    required_facts = _dedupe(route.missing_facts)
    authority_ledger = _authority_entries(q, route)
    safety_flags = _safety_flags(
        q,
        route=route,
        role=user_role,
        jurisdiction=jurisdiction,
        incident_date_status=incident_status,
    )

    return LegalIssuePlan(
        schema_version=1,
        primary_issue=route.category,
        primary_label=route.label,
        confidence=route.confidence,
        user_role=user_role,
        jurisdiction=jurisdiction,
        incident_date_status=incident_status,
        case_stage=_case_stage(q),
        desired_outcome=_desired_outcome(q, route),
        urgency=route.urgency,
        secondary_issues=_secondary_issues(q, route.category),
        required_facts=required_facts,
        authority_ledger=authority_ledger,
        forums=_dedupe(route.forums),
        next_steps=_dedupe(route.action_pack.next_steps if route.action_pack else []),
        safety_flags=safety_flags,
    )


def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").lower()).strip()


def _dedupe(values: list[str] | tuple[str, ...]) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for value in values or []:
        clean = re.sub(r"\s+", " ", str(value)).strip()
        key = clean.lower()
        if not clean or key in seen:
            continue
        out.append(clean)
        seen.add(key)
    return out


def _has_any(text: str, terms: tuple[str, ...]) -> bool:
    return any(term in text for term in terms)


def _extract_jurisdiction(q: str, route: MatterRoute) -> JurisdictionPlan:
    state = next((term for term in _STATE_TERMS if _wordish_contains(q, term)), None)
    city = next((term for term in _CITY_TO_STATE if _wordish_contains(q, term)), None)
    if state is None and city:
        state = _CITY_TO_STATE[city]
    forum = next((term for term in _FORUM_TERMS if term in q), None)
    needs_state = any("state" in fact.lower() or "city" in fact.lower() for fact in route.missing_facts)
    return JurisdictionPlan(
        state=state,
        city=city,
        forum_mentioned=forum,
        needs_state=needs_state and state is None and city is None,
    )


def _wordish_contains(text: str, term: str) -> bool:
    return re.search(rf"(?<![a-z0-9]){re.escape(term)}(?![a-z0-9])", text) is not None


def _extract_user_role(q: str, category: str) -> str:
    if _is_victim_bail_opposition_context(q):
        if category == "sexual_offence_survivor" or _has_any(q, ("survivor", "rape", "sexual offence", "sexual assault")):
            return "sexual_offence_survivor_or_complainant"
        return "complainant_or_victim"
    if _is_victim_or_witness_against_accused(q):
        if _has_any(q, ("witness", "gawah")):
            return "witness_or_complainant"
        return "complainant_or_victim"
    if _has_any(q, ("witness", "gawah")) and _has_any(q, ("notice", "summons", "police called", "police call")):
        return "witness_or_notice_recipient"
    if _is_user_accused_context(q) or _has_any(q, ("chargesheet", "charge sheet", "arrested", "arrest me")):
        return "accused_or_accused_family"
    if category in {"criminal_defence_bail", "undertrial_review_release"}:
        return "accused_or_accused_family"
    if _has_any(q, ("undertrial", "in jail", "judicial custody", "police custody", "remand", "nbw", "warrant")):
        return "accused_or_accused_family"
    medical_family_context = _has_any(q, ("my father", "my mother", "my 80", "hospital", "doctor")) and _has_any(q, (
        "hospital", "doctor", "clinic", "wrong leg", "wrong surgery", "wrong operation",
        "operated wrong", "wrong injection", "medical negligence", "died", "death",
    ))
    if category == "consumer" and medical_family_context:
        return "patient_or_family"
    senior_home_context = (
        category in {"senior_citizen", "senior_citizen_maintenance"}
        or _has_any(q, (
            "senior citizen", "my son threw me", "my daughter threw me",
            "threw me out of my own house", "old age pension", "75 yrs", "80 yr",
        ))
        or (
            _has_any(q, ("my father", "my mother"))
            and _has_any(q, ("75", "80", "senior", "maintenance", "gifted", "transferred", "threw", "not maintaining"))
        )
    )
    if senior_home_context:
        return "senior_citizen_or_family"
    if _has_any(q, ("my son", "my daughter", "my child", "school admission")):
        if category in {"police_fir", "arrest_custody_safeguard", "criminal_defence_bail"}:
            if _is_user_accused_context(q) or (
                _has_any(q, ("arrested", "detained", "picked", "custody", "jail", "bail"))
                and not _is_active_accusation_context(q)
            ):
                return "family_of_accused_or_detained_person"
            if _is_active_accusation_context(q) or _has_any(q, ("police not filing", "not filing fir", "complaint")):
                return "complainant_or_victim"
        return "parent_or_guardian"
    if _has_any(q, ("my tenant", "tenant is", "tenant not")):
        return "landlord"
    if _has_any(q, ("my landlord", "landlord not", "landlord sent me notice", "owner not")):
        return "tenant"
    if _has_any(q, ("my wife", "my husband", "spouse")):
        return "spouse"
    if _has_any(q, ("hospital", "doctor", "clinic", "surgery", "operation", "medical", "patient")):
        return "patient_or_family"
    if _has_any(q, ("my employee", "worker under me", "my worker", "working with me on")):
        return "employer_or_manager"
    if _has_any(q, ("my employer", "boss", "manager", "salary", "wages", "terminated", "pip")):
        return "employee_or_worker"
    if category in {"employment_wages", "labour_exploitation_discrimination"} and _has_any(q, (
        "worker", "asha", "nrega", "mgnrega", "job card", "not paid", "honorarium",
        "construction", "factory", "labour", "labor", "employee", "contractor",
    )):
        return "employee_or_worker"
    if category == "consumer" and _has_any(q, (
        "from customer", "customer filed", "customer complaint", "consumer complaint from customer",
        "against my shop", "by my shop",
    )):
        return "business_or_service_provider_respondent"
    if _has_any(q, ("police not filing", "fir", "complaint", "stolen", "fraud", "harassment")):
        return "complainant_or_victim"
    if category == "cyber_fraud_or_harassment" and _has_any(q, (
        "data breach", "pan", "aadhaar leaked", "otp", "extortion", "account hacked",
        "money taken", "fraud", "leaked",
    )):
        return "complainant_or_victim"
    if category == "consumer":
        return "consumer_or_customer"
    if category == "family_marriage_status":
        return "spouse_or_family_member"
    if category == "social_welfare_identity":
        return "benefit_or_document_applicant"
    if category == "property_tenancy":
        return "property_or_tenancy_claimant"
    return _CATEGORY_DEFAULT_ROLES.get(category, "unknown")


def _incident_date_status(q: str, route: MatterRoute) -> str:
    if route.legal_regime:
        return route.legal_regime
    if _has_any(q, ("before 1 july 2024", "before july 2024", "in 2023", "fir from 2023")):
        return "explicit_pre_1_july_2024"
    if _has_any(q, ("after 1 july 2024", "after july 2024", "in 2025", "in 2026")):
        return "explicit_post_1_july_2024"
    if route.category in _CRIMINAL_CATEGORIES:
        return "needed_for_criminal_regime"
    return "not_required_or_not_detected"


def _case_stage(q: str) -> str:
    if _has_any(q, ("chargesheet", "charge sheet")):
        return "chargesheet_filed"
    if _has_any(q, ("appeal filed", "appeal pending", "first appeal", "second appeal")):
        return "appeal_stage"
    if _has_any(q, ("court ordered", "court order", "as per court order", "tribunal ordered", "decree", "judgment debtor", "order passed")):
        return "order_or_decree_exists"
    if _has_any(q, ("award passed", "award not paid", "execution", "execute order", "order not complied", "not complying with order")):
        return "execution_or_compliance_stage"
    if _has_any(q, ("undertrial", "in jail", "judicial custody", "police custody", "remand")):
        return "custody_or_trial_pending"
    if _has_any(q, ("fir", "crime number")):
        return "fir_or_police_case"
    if _has_any(q, ("legal notice", "notice under", "notice received", "received notice", "show cause", "sent me notice", "got notice", "summons", "nbw", "warrant")):
        return "notice_stage"
    if _has_any(q, ("case filed", "petition filed", "complaint pending", "case pending", "hearings")):
        return "case_filed_or_pending"
    if _has_any(q, ("complained", "complaint filed", "written complaint")):
        return "complaint_made"
    return "pre_complaint_or_unknown"


def _desired_outcome(q: str, route: MatterRoute) -> str:
    if _has_any(q, ("notice under", "notice received", "show cause", "sent me notice", "got notice", "summons")):
        if _has_any(q, ("witness", "gawah")):
            return "witness_notice_response"
        if route.category == "tax_gst_compliance":
            return "tax_notice_response"
        if route.category == "banking_credit_dispute" or _has_any(q, ("sarfaesi", "13(2)", "13 2")):
            return "sarfaesi_or_banking_notice_response"
        if route.category == "property_tenancy" or _has_any(q, ("rent act", "vacate", "eviction notice")):
            return "tenancy_notice_response"
        if route.category == "consumer":
            return "consumer_notice_response"
        if route.category in _CRIMINAL_CATEGORIES or _has_any(q, ("41a", "41 a", "police", "bnss", "bns", "crpc", "ipc")):
            return "defence_or_notice_response"
        return "notice_response"
    if _is_victim_bail_threat_context(q):
        return "victim_protection_or_bail_cancellation"
    if _has_any(q, ("witness", "gawah")) and _has_any(q, ("statement", "recording", "not recording", "police not recording")):
        return "witness_statement_or_police_followup"
    if _is_victim_bail_opposition_context(q):
        return "victim_protection_or_bail_cancellation"
    if _is_victim_or_witness_against_accused(q):
        return "victim_or_witness_protection_followup"
    if _is_user_accused_context(q):
        if _has_any(q, ("bail", "release", "arrested", "custody")):
            return "bail_or_release"
        if _has_any(q, ("appeal", "quash", "quashing", "482", "528")):
            return "appeal_or_quashing"
        return "defence_or_notice_response"
    outcome_terms = (
        ("fir_registration", ("file fir", "filing fir", "not filing fir", "fir copy")),
        ("bail_or_release", ("bail", "release", "arrested", "custody")),
        ("defence_or_notice_response", ("notice under", "sent me notice", "got notice", "reply to notice")),
        ("refund_or_compensation", ("refund", "compensation", "recover money", "hospital bill")),
        ("eviction_or_possession", ("not vacating", "evict", "possession")),
        ("maintenance_enforcement", ("maintenance", "child support", "stopped paying", "tribunal ordered")),
        ("document_correction_or_certificate", ("birth certificate", "ration card", "aadhaar", "certificate")),
        ("appeal_or_quashing", ("appeal", "quash", "quashing", "482", "528")),
        ("order_execution_or_enforcement", ("execution", "execute order", "order not complied", "not paying child support", "as per court order")),
        ("wages_or_benefits_payment", ("salary", "wages", "honorarium", "nrega", "mgnrega", "not paid")),
        ("licence_or_compliance_filing", ("renew", "permit", "gst", "form 35", "annual return", "form 11", "roc")),
        ("copyright_or_ip_takedown", ("copyright", "trademark", "copied", "takedown", "infringement")),
        ("project_approval_or_compensation", ("gram sabha", "palli sabha", "noc", "land acquired", "rehabilitation")),
        ("mediation_or_settlement", ("mediation", "settlement", "settle")),
        ("complaint_or_grievance", ("complaint", "where to go", "what to do", "how to complain")),
    )
    for outcome, terms in outcome_terms:
        if _has_any(q, terms):
            return outcome
    if route.action_pack and route.action_pack.next_steps:
        return route.action_pack.id
    return "legal_information"


def _is_victim_or_witness_against_accused(q: str) -> bool:
    accused_third_party = _has_any(q, (
        "the accused", "accused person", "main accused", "co accused", "co-accused",
        "he is accused", "she is accused", "saw accused", "witness saw accused",
    )) or ("accused" in q and not _is_user_accused_context(q))
    victim_or_witness_context = _has_any(q, (
        "threatening me", "threatens me", "harassing me", "intimidating me",
        "threatened me", "threatening", "harassing", "intimidating",
        "pressuring me", "pressurising me", "came to my house", "after bail",
        "got bail", "is on bail", "out on bail", "released on bail", "victim",
        "complainant", "witness", "statement", "not recording",
    ))
    return accused_third_party and victim_or_witness_context and not _is_user_accused_context(q)


def _is_victim_bail_threat_context(q: str) -> bool:
    accused_bail = _has_any(q, (
        "accused got bail", "accused is on bail", "accused out on bail",
        "accused released on bail", "the accused got bail", "the accused is on bail",
        "after bail",
    ))
    threat = _has_any(q, (
        "threatening me", "threatens me", "harassing me", "intimidating me",
        "threatened me", "threatening", "harassing", "intimidating",
        "pressuring me", "pressurising me", "came to my house",
    ))
    return accused_bail and threat


def _is_victim_bail_opposition_context(q: str) -> bool:
    victim_side = (
        _is_active_accusation_context(q)
        or _has_any(q, (
            "survivor", "victim", "complainant", "the accused", "accused person",
            "main accused", "co accused", "co-accused", "accused in my case",
            "threatening me", "threatened me", "harassing me", "intimidating me",
        ))
    )
    bail_opposition = _has_any(q, (
        "bail cancellation", "cancel bail", "cancel his bail", "cancel her bail",
        "cancellation of bail", "oppose bail", "opposing bail", "object to bail",
        "oppose anticipatory bail", "opposing anticipatory bail",
        "anticipatory bail of accused", "bail of accused",
    ))
    bail_application = _has_any(q, (
        "bail application", "applying bail", "applying for bail", "applied for bail",
        "filed bail", "filed for bail", "filed bail application",
    ))
    opposition_words = _has_any(q, ("oppose", "opposing", "object", "cancel", "cancellation"))
    bail_opposition = bail_opposition or (bail_application and (victim_side or opposition_words))
    return bail_opposition and victim_side and not _is_user_accused_context(q)


def _is_user_accused_context(q: str) -> bool:
    if _has_any(q, (
        "i am accused", "i was accused", "i got accused", "accused me",
        "made me accused", "false case against me", "case against me",
        "filed against me", "fir against me", "named me", "named in fir",
        "my son was accused", "my daughter was accused",
        "my husband was accused", "my wife was accused", "my brother was accused",
        "my father was accused", "my mother was accused",
    )):
        return True
    family_member = (
        "son", "daughter", "brother", "sister", "husband", "wife", "father",
        "mother", "parent", "uncle", "aunt", "cousin",
    )
    family_pattern = "|".join(re.escape(member) for member in family_member)
    return bool(
        re.search(r"\b(?:i|me|myself)\s+(?:am|was|have been|has been|got)\s+accused\b", q)
        or re.search(rf"\bmy\s+(?:{family_pattern})\s+(?:is|was|has been|have been|got)\s+accused\b", q)
        or re.search(rf"\bmy\s+(?:{family_pattern})\s+.*\baccused\s+(?:in|of|under|for)\b", q)
    )


def _is_active_accusation_context(q: str) -> bool:
    family_member = (
        "son", "daughter", "brother", "sister", "husband", "wife", "father",
        "mother", "parent", "uncle", "aunt", "cousin",
    )
    actor_pattern = r"(?:i|my\s+(?:" + "|".join(re.escape(member) for member in family_member) + r"))"
    object_pattern = (
        r"(?:him|her|them|neighbou?r|shopkeeper|company|builder|dealer|seller|"
        r"landlord|tenant|driver|doctor|hospital|police|contractor|employer|[a-z]+)"
    )
    return bool(re.search(rf"\b{actor_pattern}\s+accused\s+{object_pattern}\s+(?:of|for)\b", q))


def _secondary_issues(q: str, primary: str) -> list[str]:
    issues: list[str] = []
    if _has_any(q, ("hospital", "doctor", "wrong leg", "wrong surgery", "medical negligence")):
        issues.extend(["consumer_compensation", "medical_negligence", "criminal_negligence_possible"])
    if _has_any(q, ("bank", "hdfc", "sbi", "icici", "otp", "forex transaction", "unauthorized debit", "unauthorised debit")):
        issues.extend(["banking_ombudsman", "consumer", "cyber_if_unauthorized_access"])
    posh_context = _has_any(q, (
        "posh", "sexual harassment", "icc", "internal committee",
        "local committee", "complained about sexual harassment",
        "complaint about sexual harassment",
    ))
    retaliation_context = _has_any(q, (
        "pip", "performance improvement", "bad rating", "retaliation",
        "retaliate", "warning",
    )) and _has_any(q, (
        "manager", "boss", "hr", "company", "employer", "workplace",
        "office", "supervisor", "reporting manager",
    ))
    if posh_context:
        issues.append("workplace_sexual_harassment")
        if retaliation_context:
            issues.append("employment_retaliation")
    elif retaliation_context and _has_any(q, ("complained", "complaint", "grievance", "harassment", "harass")):
        issues.append("employment_retaliation")
    if _has_any(q, ("senior citizen", "maintenance tribunal", "son threw me", "old age")):
        issues.extend(["senior_maintenance", "property_or_welfare_support"])
    if _has_any(q, ("tenant", "rent", "not vacating")):
        issues.extend(["rent_arrears", "eviction_or_possession"])
    if _has_any(q, ("police not filing", "fir copy", "picked my son", "thana not")):
        issues.extend(["police_procedure", "senior_police_or_magistrate_escalation"])
    if _has_any(q, ("streedhan", "jewellery", "dowry")):
        issues.extend(["family_property", "domestic_violence_or_dowry_context"])
    return [issue for issue in _dedupe(issues) if issue != primary]


def _authority_entry(source: str, position: int) -> AuthorityLedgerEntry:
    lower = source.lower()
    conditional = "where" in lower or "if " in lower or "based on" in lower or "depending" in lower
    date_dependent_regime = _is_date_dependent_regime_source(lower)
    return AuthorityLedgerEntry(
        source=source,
        act=_extract_act_name(source),
        section=_extract_section(source),
        claim_type=_claim_type(source),
        priority="conditional" if date_dependent_regime or (conditional and position > 0) else "must_cite",
        must_cite=False if date_dependent_regime else (not conditional or position == 0),
        conditional=conditional,
        note="date_dependent_regime_choose_by_incident_date" if date_dependent_regime else "derived_from_route_required_sources",
    )


def _authority_entries(q: str, route: MatterRoute) -> list[AuthorityLedgerEntry]:
    entries: list[AuthorityLedgerEntry] = []
    for position, source in enumerate(route.required_sources or []):
        normalized_source = source
        lower = source.lower()
        if route.label == "Caste certificate rejection / appeal":
            if "article 341 / 342" in lower:
                if _has_any(q, ("st certificate", "st cert", "scheduled tribe", "tribe certificate", "tribal certificate")):
                    normalized_source = "Constitution of India Article 342 for the relevant State-wise Scheduled Tribe list"
                elif _has_any(q, ("sc certificate", "sc cert", "scheduled caste")):
                    normalized_source = "Constitution of India Article 341 for the relevant State-wise Scheduled Caste list"
                else:
                    entries.append(
                        AuthorityLedgerEntry(
                            source="Constitution Article 341 or 342 after the SC/ST category is confirmed",
                            act="Constitution of India",
                            section=None,
                            claim_type="legal_basis",
                            priority="conditional",
                            must_cite=False,
                            conditional=True,
                            note="category_dependent_sc_article_341_vs_st_article_342",
                        )
                    )
                    continue
            elif lower.startswith("right to information act 2005"):
                normalized_source = "Right to Information Act 2005 Section 6 for the application record and written reasons"
        entries.append(_authority_entry(normalized_source, position))
    return entries


def _is_date_dependent_regime_source(lower_source: str) -> bool:
    has_new_code = any(term in lower_source for term in ("bnss", "bns", "bsa"))
    has_old_code = any(term in lower_source for term in ("crpc", "ipc", "evidence act"))
    has_date_language = "incident date" in lower_source or "based on" in lower_source or "depending" in lower_source
    return has_new_code and has_old_code and has_date_language


def _extract_act_name(source: str) -> str | None:
    lower = source.lower()
    if _is_date_dependent_regime_source(lower):
        return "date-dependent criminal regime"
    acronym_acts = (
        ("pwdva", "Protection of Women from Domestic Violence Act 2005"),
        ("pesa", "PESA Act 1996"),
        ("rfctlarr", "RFCTLARR Act 2013"),
        ("rte", "Right of Children to Free and Compulsory Education Act 2009"),
        ("mmdr", "Mines and Minerals (Development and Regulation) Act 1957"),
        ("posh", "Sexual Harassment of Women at Workplace Act 2013"),
    )
    for term, act in acronym_acts:
        if re.search(rf"(?<![a-z0-9]){re.escape(term)}(?![a-z0-9])", lower):
            return act
    patterns = (
        r"\b(?:BNSS|BNS|BSA|CrPC|IPC)\b",
        r"\b[A-Z][A-Za-z&().,' -]+?(?:Act|Code|Rules|Regulations|Guidelines|Sanhita|Adhiniyam)(?:\s+\d{4})?",
        r"\bConstitution(?: of India)?\b",
    )
    for pattern in patterns:
        match = re.search(pattern, source)
        if match:
            return re.sub(r"\s+", " ", match.group(0)).strip(" ,.")
    return None


def _extract_section(source: str) -> str | None:
    match = re.search(
        r"\b(?:section|sec\.?|article|order)\s+([0-9][0-9A-Za-z()./-]*)",
        source,
        flags=re.IGNORECASE,
    )
    if not match:
        return None
    return match.group(0).strip()


def _claim_type(source: str) -> str:
    lower = source.lower()
    if _has_any(lower, ("forum", "court", "tribunal", "commission", "authority")):
        return "forum"
    if _has_any(lower, ("deadline", "limitation", "within", "notice")):
        return "procedure_or_deadline"
    if _has_any(lower, ("document", "proof", "records", "receipts")):
        return "documents_or_facts"
    return "legal_basis"


def _safety_flags(
    q: str,
    *,
    route: MatterRoute,
    role: str,
    jurisdiction: JurisdictionPlan,
    incident_date_status: str,
) -> list[str]:
    flags: list[str] = []
    flags.extend(route.red_flags or [])
    if incident_date_status in {"needed_for_criminal_regime", "incident_date_needed_for_bns_bnss_bsa_vs_ipc_crpc"}:
        flags.append("incident_date_needed")
    if jurisdiction.needs_state:
        flags.append("state_or_city_needed")
    if role == "unknown":
        flags.append("user_role_unclear")
    if _has_any(q, ("chargesheet", "charge sheet", "accused")) and route.category in {"cyber_fraud_or_harassment", "police_fir"}:
        flags.append("accused_framing_guard")
    return _dedupe(flags)


__all__ = [
    "AuthorityLedgerEntry",
    "JurisdictionPlan",
    "LegalIssuePlan",
    "build_legal_issue_plan",
]
