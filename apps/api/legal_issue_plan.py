"""Canonical legal matter plan shared by retrieval and answer policy."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import asdict, dataclass, field, replace
from typing import Literal

from authority_registry import (
    AuthorityRecord,
    AuthorityWorkflowRecord,
    WorkflowAuthorityRequirement,
    load_authority_registry,
)

from .matter_router import (
    ActionPack,
    MatterRoute,
    _is_workplace_sexual_harassment,
    _is_workplace_harassment_respondent,
    criminal_transition_status,
    has_person_release_context,
    has_positive_criminal_bank_hold_context,
)
from .pmla_asset import (
    is_pmla_ambiguous_restraint_context,
    is_pmla_asset_restraint_context,
    is_pmla_provisional_attachment_context,
    is_pmla_section17_restraint_context,
)

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
    authority_id: str | None = None
    registry_key: str | None = None
    identity_status: Literal["canonical", "provisional"] = "provisional"
    canonical_name: str | None = None
    act: str | None = None
    section: str | None = None
    source_pack_id: str | None = None
    required_anchor_patterns: list[str] = field(default_factory=list)
    claim_type: str = "legal_basis"
    priority: AuthorityPriority = "must_cite"
    must_cite: bool = True
    conditional: bool = False
    note: str | None = None


@dataclass(frozen=True)
class RetrievalSourcePlan:
    source_pack_id: str
    title_patterns: list[str]
    search_query: str
    doc_ids: list[str] = field(default_factory=list)
    anchor_patterns: list[str] = field(default_factory=list)
    source_types: list[str] = field(default_factory=lambda: ["bare_act"])
    authority_ids: list[str] = field(default_factory=list)
    priority: float = 1.0
    selection_terms: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class AnswerPolicy:
    required_primary_owner: str
    fallback_owner: str = "source_gap_handoff"
    allow_freeform_llm: bool = True
    requires_reviewed_contract: bool = False
    fallback_reason: str | None = None
    conflicting_primary_owners: list[str] = field(default_factory=list)
    additional_primary_owners: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class PlanOwnedAnswerRoute:
    """A released scenario whose exact deterministic answer owner is known."""

    scenario_id: str
    owner_provider: str
    owner_contract_id: str
    fallback_owner: str = "source_gap_handoff"

    @property
    def owner_token(self) -> str:
        return f"{self.owner_provider}:{self.owner_contract_id}"


@dataclass(frozen=True)
class PlanAnswerOwnershipResolution:
    owner: PlanOwnedAnswerRoute | None = None
    additional_owners: tuple[PlanOwnedAnswerRoute, ...] = ()
    conflicts: tuple[str, ...] = ()


@dataclass(frozen=True)
class MatterPlan:
    schema_version: int
    plan_id: str
    primary_issue: str
    primary_label: str
    confidence: float
    user_role: str
    jurisdiction: JurisdictionPlan
    incident_date_status: str
    legal_regime: str | None
    case_stage: str
    desired_outcome: str
    urgency: str
    secondary_issues: list[str] = field(default_factory=list)
    required_facts: list[str] = field(default_factory=list)
    authority_ledger: list[AuthorityLedgerEntry] = field(default_factory=list)
    retrieval_sources: list[RetrievalSourcePlan] = field(default_factory=list)
    forums: list[str] = field(default_factory=list)
    remedies: list[str] = field(default_factory=list)
    deadlines: list[str] = field(default_factory=list)
    documents: list[str] = field(default_factory=list)
    action_pack_id: str | None = None
    action_pack_title: str | None = None
    next_steps: list[str] = field(default_factory=list)
    portals: list[str] = field(default_factory=list)
    escalation: list[str] = field(default_factory=list)
    cautions: list[str] = field(default_factory=list)
    safety_flags: list[str] = field(default_factory=list)
    answer_policy: AnswerPolicy = field(
        default_factory=lambda: AnswerPolicy(
            required_primary_owner="server_template_or_verified_llm"
        )
    )

    def to_event(self) -> dict:
        payload = asdict(self)
        answer_policy = payload["answer_policy"]
        if answer_policy.get("fallback_reason") is None:
            answer_policy.pop("fallback_reason", None)
        if not answer_policy.get("conflicting_primary_owners"):
            answer_policy.pop("conflicting_primary_owners", None)
        if not answer_policy.get("additional_primary_owners"):
            answer_policy.pop("additional_primary_owners", None)
        return payload


REVIEWED_CONTRACT_REQUIRED_CATEGORIES = frozenset(
    {
        "arrest_custody_safeguard",
        "bonded_labour_rescue",
        "business_contract_partnership",
        "child_marriage_protection",
        "child_custody_adoption",
        "criminal_procedure_notice",
        "criminal_defence_bail",
        "criminal_general",
        "custody_compensation",
        "cyber_fraud_or_harassment",
        "digital_platform_account",
        "family_domestic",
        "labour_exploitation_discrimination",
        "manual_scavenging_safety",
        "pmla_ed",
        "police_fir",
        "reproductive_rights_mtp",
        "sexual_offence_survivor",
        "tribal_caste_atrocity",
        "workplace_sexual_harassment",
    }
)


# P1C release slice. These are scenario families, not individual benchmark
# prompts. The registry is consumed by MatterPlan before retrieval; serving
# must either render the named source-gated contract or use the fallback.
PLAN_OWNED_ANSWER_ROUTES: tuple[PlanOwnedAnswerRoute, ...] = (
    PlanOwnedAnswerRoute(
        scenario_id="domestic_violence_immediate_safety",
        owner_provider="authority_graph",
        owner_contract_id="domestic_violence_immediate_safety",
    ),
    PlanOwnedAnswerRoute(
        scenario_id="arrest_custody_station_case_not_disclosed",
        owner_provider="authority_graph",
        owner_contract_id="arrest_custody_station_case_not_disclosed",
    ),
    PlanOwnedAnswerRoute(
        scenario_id="lgbtq_identity_arrest_safeguard",
        owner_provider="authority_graph",
        owner_contract_id="lgbtq_identity_arrest_safeguard",
    ),
    PlanOwnedAnswerRoute(
        scenario_id="vehicle_theft_fir_refusal",
        owner_provider="authority_graph",
        owner_contract_id="vehicle_theft_fir_refusal",
    ),
    PlanOwnedAnswerRoute(
        scenario_id="loan_app_harassment",
        owner_provider="common_workflow_contracts",
        owner_contract_id="loan_app_harassment",
    ),
    PlanOwnedAnswerRoute(
        scenario_id="bank_account_freeze_legal_hold",
        owner_provider="authority_graph",
        owner_contract_id="bank_account_freeze_legal_hold",
    ),
    PlanOwnedAnswerRoute(
        scenario_id="pmla_ed_asset_freeze",
        owner_provider="authority_graph",
        owner_contract_id="pmla_ed_asset_freeze",
    ),
    PlanOwnedAnswerRoute(
        scenario_id="uapa_prima_facie_bail",
        owner_provider="authority_graph",
        owner_contract_id="uapa_prima_facie_bail",
    ),
    PlanOwnedAnswerRoute(
        scenario_id="police_seized_device_return",
        owner_provider="common_workflow_contracts",
        owner_contract_id="police_seized_device_return",
    ),
    PlanOwnedAnswerRoute(
        scenario_id="wrong_bank_debit",
        owner_provider="authority_graph",
        owner_contract_id="wrong_bank_debit",
    ),
    PlanOwnedAnswerRoute(
        scenario_id="pan_aadhaar_linking_bank_kyc",
        owner_provider="authority_graph",
        owner_contract_id="pan_aadhaar_linking_bank_kyc",
    ),
    PlanOwnedAnswerRoute(
        scenario_id="insurance_claim_or_misselling",
        owner_provider="authority_graph",
        owner_contract_id="insurance_claim_or_misselling",
    ),
    PlanOwnedAnswerRoute(
        scenario_id="civil_registration_certificate_issuance",
        owner_provider="authority_graph",
        owner_contract_id="civil_registration_certificate_issuance",
    ),
    PlanOwnedAnswerRoute(
        scenario_id="civil_registration_certificate_copy",
        owner_provider="authority_graph",
        owner_contract_id="civil_registration_certificate_copy",
    ),
    PlanOwnedAnswerRoute(
        scenario_id="death_registration_delayed",
        owner_provider="authority_graph",
        owner_contract_id="death_registration_delayed",
    ),
    PlanOwnedAnswerRoute(
        scenario_id="birth_certificate_record_correction",
        owner_provider="authority_graph",
        owner_contract_id="birth_certificate_record_correction",
    ),
    PlanOwnedAnswerRoute(
        scenario_id="death_certificate_record_correction",
        owner_provider="authority_graph",
        owner_contract_id="death_certificate_record_correction",
    ),
    PlanOwnedAnswerRoute(
        scenario_id="consumer_defective_goods",
        owner_provider="authority_graph",
        owner_contract_id="consumer_defective_goods",
    ),
    PlanOwnedAnswerRoute(
        scenario_id="joint_coowner_sold_whole_property",
        owner_provider="authority_graph",
        owner_contract_id="joint_coowner_sold_whole_property",
    ),
    PlanOwnedAnswerRoute(
        scenario_id="marital_intimacy_remedy",
        owner_provider="authority_graph",
        owner_contract_id="marital_intimacy_remedy",
    ),
    PlanOwnedAnswerRoute(
        scenario_id="registered_will_update",
        owner_provider="authority_graph",
        owner_contract_id="registered_will_update",
    ),
    PlanOwnedAnswerRoute(
        scenario_id="caretaker_daughter_will",
        owner_provider="authority_graph",
        owner_contract_id="caretaker_daughter_will",
    ),
    PlanOwnedAnswerRoute(
        scenario_id="unregistered_will_validity",
        owner_provider="authority_graph",
        owner_contract_id="unregistered_will_validity",
    ),
    PlanOwnedAnswerRoute(
        scenario_id="thermal_blasting_house_damage_compensation",
        owner_provider="authority_graph",
        owner_contract_id="thermal_blasting_house_damage_compensation",
    ),
    PlanOwnedAnswerRoute(
        scenario_id="mining_displacement_rehabilitation",
        owner_provider="authority_graph",
        owner_contract_id="mining_displacement_rehabilitation",
    ),
    PlanOwnedAnswerRoute(
        scenario_id="scst_poa_accused_bail_defence",
        owner_provider="authority_graph",
        owner_contract_id="scst_poa_accused_bail_defence",
    ),
    PlanOwnedAnswerRoute(
        scenario_id="scst_targeted_violence_intake",
        owner_provider="authority_graph",
        owner_contract_id="scst_targeted_violence_intake",
    ),
    PlanOwnedAnswerRoute(
        scenario_id="caste_certificate_state_rule_intake",
        owner_provider="authority_graph",
        owner_contract_id="caste_certificate_state_rule_intake",
    ),
    PlanOwnedAnswerRoute(
        scenario_id="workplace_sexual_harassment_respondent",
        owner_provider="common_workflow_contracts",
        owner_contract_id="workplace_sexual_harassment_respondent",
    ),
    PlanOwnedAnswerRoute(
        scenario_id="workplace_sexual_harassment_complainant",
        owner_provider="common_workflow_contracts",
        owner_contract_id="workplace_sexual_harassment_first_action",
    ),
    PlanOwnedAnswerRoute(
        scenario_id="lok_adalat_traffic_settlement",
        owner_provider="common_workflow_contracts",
        owner_contract_id="lok_adalat_traffic_settlement",
    ),
    PlanOwnedAnswerRoute(
        scenario_id="lok_adalat_award_challenge",
        owner_provider="common_workflow_contracts",
        owner_contract_id="lok_adalat_award_challenge",
    ),
    PlanOwnedAnswerRoute(
        scenario_id="mgnrega_fake_muster",
        owner_provider="authority_graph",
        owner_contract_id="mgnrega_fake_muster",
    ),
)

_SOURCE_PACK_ACRONYM_ALIASES = {
    "aadhaar": "aadhaar targeted delivery of financial and other subsidies benefits and services act 2016",
    "bocw": "building and other construction workers act 1996",
    "bns": "bharatiya nyaya sanhita 2023",
    "bnss": "bharatiya nagarik suraksha sanhita 2023",
    "bsa": "bharatiya sakshya adhiniyam 2023",
    "cgst": "central goods and services tax act 2017",
    "crpc": "code of criminal procedure 1973",
    "dpdp": "digital personal data protection act 2023",
    "ibc": "insolvency and bankruptcy code 2016",
    "ipc": "indian penal code 1860",
    "jj": "juvenile justice care and protection of children act 2015",
    "mgnrega": "mahatma gandhi national rural employment guarantee act 2005",
    "mmdr": "mines and minerals development and regulation act 1957",
    "msmed": "micro small and medium enterprises development act 2006",
    "ndps": "narcotic drugs and psychotropic substances act 1985",
    "nfsa": "national food security act 2013",
    "ni": "negotiable instruments act 1881",
    "pesa": "panchayats extension to the scheduled areas act 1996",
    "pocso": "protection of children from sexual offences act 2012",
    "pmla": "prevention of money laundering act 2002",
    "posh": "sexual harassment of women at workplace act 2013",
    "pwdva": "protection of women from domestic violence act 2005",
    "rera": "real estate regulation and development act 2016",
    "rfctlarr": "right to fair compensation and transparency in land acquisition rehabilitation and resettlement act 2013",
    "rte": "right of children to free and compulsory education act 2009",
    "rti": "right to information act 2005",
}


_STATE_TERMS = (
    "andhra pradesh",
    "arunachal pradesh",
    "assam",
    "bihar",
    "chhattisgarh",
    "delhi",
    "goa",
    "gujarat",
    "haryana",
    "himachal pradesh",
    "jharkhand",
    "karnataka",
    "kerala",
    "madhya pradesh",
    "maharashtra",
    "manipur",
    "meghalaya",
    "mizoram",
    "nagaland",
    "odisha",
    "orissa",
    "punjab",
    "rajasthan",
    "sikkim",
    "tamil nadu",
    "telangana",
    "tripura",
    "uttar pradesh",
    "uttarakhand",
    "west bengal",
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
    "high court",
    "supreme court",
    "family court",
    "consumer commission",
    "district commission",
    "nclt",
    "tribunal",
    "labour court",
    "police station",
    "magistrate",
    "dlsa",
    "ombudsman",
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


def plan_owned_answer_route(
    query: str,
    route: MatterRoute,
) -> PlanOwnedAnswerRoute | None:
    """Return the single released answer-owner rule for this scenario."""
    return resolve_plan_answer_ownership(query, route).owner


def resolve_plan_answer_ownership(
    query: str,
    route: MatterRoute,
) -> PlanAnswerOwnershipResolution:
    """Resolve one released owner or an explicit fail-closed conflict."""
    from .authority_graph import authority_graph_contract_query_matches
    from .common_workflow_contracts import common_workflow_contract_query_matches

    q = query.lower()
    matches: list[PlanOwnedAnswerRoute] = []
    for rule in PLAN_OWNED_ANSWER_ROUTES:
        if (
            rule.owner_contract_id == "bank_account_freeze_legal_hold"
            and route.category not in {"banking_credit_dispute", "cyber_fraud_or_harassment"}
        ):
            continue
        if rule.owner_contract_id == "consumer_defective_goods" and route.category != "consumer":
            continue
        if (
            rule.owner_contract_id == "consumer_defective_goods"
            and re.search(r"\b(?:bike|bicycle|scooter|motorcycle|motorbike|car|vehicle)\b", q)
            and not _has_any(q, (
                "online order", "online seller", "marketplace", "seller", "manufacturer",
                "bought online", "ordered online", "online purchase", "purchased online",
            ))
        ):
            continue
        if rule.owner_provider == "authority_graph":
            matched = authority_graph_contract_query_matches(
                query,
                route,
                rule.owner_contract_id,
                route_independent=True,
            )
        elif rule.owner_provider == "common_workflow_contracts":
            matched = common_workflow_contract_query_matches(
                query,
                route,
                rule.owner_contract_id,
                route_independent=True,
            )
        else:
            raise ValueError(f"unknown plan answer owner provider: {rule.owner_provider}")
        if matched:
            matches.append(rule)
    if len(matches) > 1:
        by_scenario = {rule.scenario_id: rule for rule in matches}
        # Identity-only arrest and the immediate custody-information route are
        # compatible parts of one urgent liberty answer. The identity owner is
        # primary and the custody owner is rendered as a cited second track.
        compatible_pair = {
            "lgbtq_identity_arrest_safeguard",
            "arrest_custody_station_case_not_disclosed",
        }
        if set(by_scenario) == compatible_pair:
            return PlanAnswerOwnershipResolution(
                owner=by_scenario["lgbtq_identity_arrest_safeguard"],
                additional_owners=(by_scenario["arrest_custody_station_case_not_disclosed"],),
            )
        # A caretaker-daughter will question can mention both the substantive
        # family fact pattern and the ordinary registration/validity issue.
        # These are two compatible authority tracks for one succession matter,
        # not two unrelated legal problems. Keep the more specific caretaker
        # contract primary and require the validity contract as a second track.
        compatible_pair = {
            "caretaker_daughter_will",
            "unregistered_will_validity",
        }
        if set(by_scenario) == compatible_pair:
            return PlanAnswerOwnershipResolution(
                owner=by_scenario["caretaker_daughter_will"],
                additional_owners=(by_scenario["unregistered_will_validity"],),
            )
        compatible_pair = {
            "scst_targeted_violence_intake",
            "caste_certificate_state_rule_intake",
        }
        if set(by_scenario) == compatible_pair:
            return PlanAnswerOwnershipResolution(
                owner=by_scenario["scst_targeted_violence_intake"],
                additional_owners=(by_scenario["caste_certificate_state_rule_intake"],),
            )
        return PlanAnswerOwnershipResolution(
            conflicts=tuple(rule.owner_token for rule in matches),
        )
    return PlanAnswerOwnershipResolution(owner=matches[0] if matches else None)


def _registry_condition_matches(
    condition_id: str,
    query: str,
    legal_regime: str | None = None,
) -> bool:
    q = _normalize(query)
    if condition_id == "private_image_abuse":
        image_facts = _has_any(q, (
            "morphed", "deepfake", "fake nude", "nude", "private image",
            "intimate image", "private photo", "sexual image",
        ))
        abuse_facts = _has_any(q, (
            "blackmail", "threat", "extort", "publish", "post", "share",
            "send", "upload", "leak", "circulate", "without consent",
        ))
        return image_facts and abuse_facts
    if condition_id == "loan_app_private_image_extortion_current":
        image_facts = _has_any(q, (
            "morphed", "deepfake", "fake nude", "nude", "private image",
            "intimate image", "private photo", "sexual image",
        ))
        payment_threat = _has_any(q, (
            "blackmail", "extort", "demanding money", "demanded money",
            "pay today", "pay tonight", "dont pay", "don't pay",
            "miss payment", "payment tonight",
        ))
        current_incident = _has_any(q, (
            "today", "tonight", "just now", "this morning",
            "this afternoon", "this evening", "after 1 july 2024",
            "after july 2024", "in 2025", "in 2026",
        ))
        return image_facts and payment_threat and current_incident
    if condition_id.startswith("custody_"):
        geographic_exception = _has_any(q, (
            "nagaland", "tribal area", "tribal areas", "sixth schedule area",
        ))
        legacy = (
            not geographic_exception
            and legal_regime == "legacy_ipc_crpc_evidence_for_pre_2024_incident"
        )
        current = (
            not geographic_exception
            and legal_regime == "current_bns_bnss_bsa_for_post_2024_incident"
        )
        if condition_id == "custody_current_bnss":
            return current
        if condition_id == "custody_legacy_crpc":
            return legacy and not geographic_exception
        if condition_id == "custody_legacy_or_unknown":
            return not geographic_exception and (legacy or not current)
        if condition_id == "custody_bnss_geographic_exception":
            return geographic_exception
    if condition_id.startswith("bank_freeze_") or condition_id == "bank_account_freeze_service_or_legal_hold":
        legal_hold = has_positive_criminal_bank_hold_context(q)
        if condition_id == "bank_account_freeze_service_or_legal_hold":
            return True
        legacy = (
            legal_hold
            and legal_regime == "legacy_ipc_crpc_evidence_for_pre_2024_incident"
        )
        current = (
            legal_hold
            and legal_regime == "current_bns_bnss_bsa_for_post_2024_incident"
        )
        if condition_id == "bank_freeze_current_bnss_legal_hold":
            return current
        if condition_id == "bank_freeze_legacy_crpc_legal_hold":
            return legacy
        if condition_id == "bank_freeze_unknown_date_legal_hold":
            return legal_hold and not legacy and not current
        if condition_id == "bank_freeze_bnss_source_needed":
            return legal_hold and not legacy
        if condition_id == "bank_freeze_crpc_source_needed":
            return legal_hold and not current
    if condition_id.startswith("pmla_"):
        if condition_id == "pmla_asset_restraint":
            return is_pmla_asset_restraint_context(q)
        if condition_id == "pmla_provisional_attachment":
            return is_pmla_provisional_attachment_context(
                q
            ) or is_pmla_ambiguous_restraint_context(q)
        if condition_id == "pmla_search_freeze":
            return is_pmla_section17_restraint_context(
                q
            ) or is_pmla_ambiguous_restraint_context(q)
    if condition_id.startswith("device_return_"):
        transition = criminal_transition_status(q)
        legacy = transition in {"saved_crpc", "legacy_incident"}
        current = transition == "current_bnss"
        explicitly_not_produced = _has_any(q, (
            "not produced before court", "not produced in court",
            "not produced before magistrate", "never produced before court",
            "not produced it before court", "not produced the device before court",
            "did not produce before court", "didn't produce before court",
            "did not produce it before court", "didn't produce it before court",
            "did not produce the device before court", "didn't produce the device before court",
            "still with police", "only in police custody", "police still have",
        ))
        explicitly_produced = not explicitly_not_produced and _has_any(q, (
            "produced before court", "produced in court", "produced before magistrate",
            "produced it before court", "produced it before the magistrate",
            "produced the device before court",
            "deposited in court", "in court custody", "court has the device",
            "court has my phone", "court has the phone", "magistrate has the device",
            "magistrate has my phone", "magistrate has the phone", "submitted to court",
        ))
        court_status_unknown = not explicitly_produced and not explicitly_not_produced
        if condition_id == "device_return_bnss_531_needed":
            return transition in {"saved_crpc", "unknown"}
        if condition_id == "device_return_bnss_497_needed":
            return not legacy and (explicitly_produced or court_status_unknown)
        if condition_id == "device_return_bnss_503_needed":
            return not legacy and (explicitly_not_produced or court_status_unknown)
        if condition_id == "device_return_crpc_451_needed":
            return not current and (explicitly_produced or court_status_unknown)
        if condition_id == "device_return_crpc_457_needed":
            return not current and (explicitly_not_produced or court_status_unknown)
    if condition_id == "vehicle_theft_bnss_needed":
        return legal_regime in {
            "current_bns_bnss_bsa_for_post_2024_incident",
            "incident_date_needed_for_bns_bnss_bsa_vs_ipc_crpc",
            None,
        }
    if condition_id == "vehicle_theft_crpc_needed":
        return legal_regime in {
            "legacy_ipc_crpc_evidence_for_pre_2024_incident",
            "incident_date_needed_for_bns_bnss_bsa_vs_ipc_crpc",
            None,
        }
    return False


def _active_registry_requirements(
    workflow: AuthorityWorkflowRecord,
    query: str,
    legal_regime: str | None = None,
) -> tuple[WorkflowAuthorityRequirement, ...]:
    active: list[WorkflowAuthorityRequirement] = []
    for requirement in workflow.authorities:
        if requirement.required:
            active.append(requirement)
            continue
        if requirement.condition_ids and all(
            _registry_condition_matches(condition_id, query, legal_regime)
            for condition_id in requirement.condition_ids
        ):
            active.append(requirement)
    return tuple(active)


def _registry_owner_retrieval_sources(
    owner: PlanOwnedAnswerRoute | None,
    retrieval_sources: list[RetrievalSourcePlan],
    query: str,
    *,
    legal_regime: str | None = None,
    closed_owner_set: bool = True,
) -> list[RetrievalSourcePlan]:
    """Scope registry expansion to the selected answer owner.

    Route-level source packs are shared by many scenarios. Expanding one of
    those packs globally made unrelated banking routes retrieve every RBI
    Ombudsman clause. A registry-owned workflow instead replaces only its own
    MatterPlan sources with the exact authorities declared by that workflow.
    """
    if owner is None:
        return retrieval_sources
    registry = load_authority_registry()
    workflow = registry.workflow_for_scenario(owner.scenario_id)
    if workflow is None:
        return retrieval_sources

    records = []
    for requirement in _active_registry_requirements(workflow, query, legal_regime):
        record = registry.by_key(requirement.registry_key)
        if record is None:
            raise ValueError(f"registry workflow authority missing: {requirement.registry_key}")
        records.append(record)

    by_pack: dict[str, list] = {}
    for record in records:
        by_pack.setdefault(record.retrieval.source_pack_id, []).append(record)

    existing_by_id = {source.source_pack_id: source for source in retrieval_sources}
    replacements: dict[str, RetrievalSourcePlan] = {}
    for pack_id, pack_records in by_pack.items():
        existing = existing_by_id.get(pack_id)
        replacements[pack_id] = RetrievalSourcePlan(
            source_pack_id=pack_id,
            title_patterns=list(dict.fromkeys(
                title for record in pack_records for title in record.retrieval.title_patterns
            )),
            search_query=" ".join(
                dict.fromkeys(record.retrieval.search_query for record in pack_records)
            ),
            doc_ids=list(dict.fromkeys(
                doc_id for record in pack_records for doc_id in record.retrieval.doc_ids
            )),
            anchor_patterns=[
                record.provision.canonical_anchor for record in pack_records
            ],
            source_types=list(dict.fromkeys(
                source_type
                for record in pack_records
                for source_type in record.retrieval.source_types
            )),
            authority_ids=[record.authority_id_expected for record in pack_records],
            priority=max(existing.priority if existing is not None else 0.0, 1.5),
        )

    # A registry-owned answer is a closed authority set. Keeping generic route
    # packs here allowed unrelated statutes to enter the prompt and source list
    # even though they could never support this workflow's reviewed answer.
    if closed_owner_set:
        return list(replacements.values())
    return [
        source for source in retrieval_sources
        if source.source_pack_id not in replacements
    ] + list(replacements.values())


def _pmla_asset_restraint_action_pack() -> ActionPack:
    return ActionPack(
        id="pmla_ed_asset_restraint",
        title="PMLA asset restraint path",
        next_steps=[
            "Identify whether the document is a Section 5 provisional attachment order or a Section 17 seizure/freezing order.",
            "Mark every service and receipt date, then prepare the Section 8 reply with ownership and source-of-funds records.",
            "Have a PMLA lawyer or DLSA check any Section 26 appeal deadline against the exact Adjudicating Authority order.",
        ],
        documents=[
            "freezing, seizure, or provisional attachment order",
            "proof and date of service",
            "affected bank account or property schedule",
            "Section 8 notice and reply",
            "ownership and source-of-funds records",
            "Adjudicating Authority order",
        ],
        escalation=[
            "PMLA Adjudicating Authority",
            "Appellate Tribunal under PMLA",
            "District Legal Services Authority or PMLA lawyer",
        ],
        cautions=[
            "Do not treat a Section 5 attachment and a Section 17 seizure or freezing order as the same statutory path."
        ],
    )


def _uapa_bail_action_pack() -> ActionPack:
    return ActionPack(
        id="uapa_bail_43d",
        title="UAPA Section 43D bail path",
        next_steps=[
            "Identify whether the immediate issue is regular bail under Section 43D(5) or default bail based on the investigation timeline.",
            "For regular bail, compare the FIR sections and prosecution material with the Special Court's prima-facie finding.",
            "For default bail, calculate from the first remand and verify the charge-sheet date, Public Prosecutor report, and any extension order.",
        ],
        documents=[
            "FIR and exact UAPA sections",
            "arrest memo and first-remand order",
            "complete remand and extension orders",
            "charge-sheet or filing-status record",
            "Public Prosecutor extension report if any",
            "prior bail orders and prosecution material relied on",
        ],
        escalation=[
            "jurisdictional Special Court or trial court",
            "High Court for the legally available bail remedy",
            "District Legal Services Authority or UAPA criminal-defence lawyer",
        ],
        cautions=[
            "This statute-only path does not decide a prolonged-incarceration constitutional argument; that requires separately verified current precedent.",
            "Do not calculate a default-bail deadline without the first-remand date, filing status, Public Prosecutor report, and extension order.",
        ],
    )


def build_matter_plan(query: str, route: MatterRoute) -> MatterPlan | None:
    """Build the canonical v2 plan for a routed legal matter."""
    if route.category == "off_topic":
        return None

    from .source_packs import source_packs_for_route

    q = _normalize(query)
    jurisdiction = _extract_jurisdiction(q, route)
    user_role = _extract_user_role(q, route.category)
    incident_status = _incident_date_status(q, route)
    required_facts = _dedupe(route.missing_facts)
    source_packs = source_packs_for_route(route, query)
    ownership_resolution = resolve_plan_answer_ownership(q, route)
    plan_owner = ownership_resolution.owner
    if plan_owner is not None and plan_owner.scenario_id == "pmla_ed_asset_freeze":
        required_facts = [
            "exact order type and section stated",
            "date and proof of service",
            "account, property, or asset restrained and amount/value",
            "Section 8 notice or Adjudicating Authority order if served",
            "ownership and source-of-funds records",
        ]
    if plan_owner is not None and plan_owner.scenario_id == "uapa_prima_facie_bail":
        required_facts = [
            "exact UAPA sections in the FIR",
            "arrest date and first-remand date",
            "charge-sheet or filing status and date",
            "Public Prosecutor extension report and court order if any",
            "prior bail order and prosecution material relied on for the prima-facie finding",
        ]
    plan_owners = (
        (plan_owner, *ownership_resolution.additional_owners) if plan_owner is not None else ()
    )
    registry_workflow = (
        load_authority_registry().workflow_for_scenario(plan_owner.scenario_id)
        if plan_owner is not None
        else None
    )
    registry_active_requirements = (
        _active_registry_requirements(registry_workflow, q, route.legal_regime)
        if registry_workflow is not None
        else ()
    )
    registry_workflow_no_active_authorities = bool(
        registry_workflow is not None and not registry_active_requirements
    )
    retrieval_sources = [
        RetrievalSourcePlan(
            source_pack_id=pack.id,
            title_patterns=list(pack.title_patterns),
            search_query=pack.search_query,
            doc_ids=list(pack.doc_ids),
            anchor_patterns=list(pack.anchor_patterns),
            source_types=list(pack.source_types),
            authority_ids=list(pack.authority_ids),
            priority=pack.priority,
            selection_terms=list(pack.selection_terms),
        )
        for pack in source_packs
    ]
    retrieval_sources = _augment_owner_retrieval_sources(
        plan_owner,
        retrieval_sources,
        route,
        query=q,
    )
    retrieval_sources = _registry_owner_retrieval_sources(
        plan_owner,
        retrieval_sources,
        q,
        legal_regime=route.legal_regime,
        closed_owner_set=(
            plan_owner is None
            or plan_owner.scenario_id != "vehicle_theft_fir_refusal"
        )
        and not (
            plan_owner is not None
            and plan_owner.scenario_id == "arrest_custody_station_case_not_disclosed"
            and route.legal_regime
            == "incident_date_needed_for_bns_bnss_bsa_vs_ipc_crpc"
        ),
    )
    for additional_owner in ownership_resolution.additional_owners:
        retrieval_sources = _registry_owner_retrieval_sources(
            additional_owner,
            retrieval_sources,
            q,
            legal_regime=route.legal_regime,
            closed_owner_set=False,
        )
    if plan_owner is not None:
        route_entries = _authority_entries(q, route)
        route_entries_by_act = {
            _legal_name(entry.act or ""): entry for entry in route_entries if entry.act
        }
        owner_entries = [
            replace(
                entry,
                source=route_entries_by_act[_legal_name(entry.act or "")].source,
            )
            if _legal_name(entry.act or "") in route_entries_by_act
            else entry
            for owner in plan_owners
            for entry in _plan_owner_authority_entries(
                owner,
                retrieval_sources,
                route,
                q,
            )
        ]
        owner_acts = {_act_equivalence_key(entry.act) for entry in owner_entries}
        context_entries = [] if (
            plan_owner.scenario_id == "uapa_prima_facie_bail"
            or registry_workflow_no_active_authorities
        ) else [
            replace(
                entry,
                priority="background",
                must_cite=False,
                conditional=False,
                note="plan_owned_context_authority",
            )
            for entry in route_entries
            if _act_equivalence_key(entry.act) not in owner_acts
        ]
        raw_authority_entries = [*owner_entries, *context_entries]
    else:
        raw_authority_entries = _authority_entries(q, route)
    raw_authority_entries = _attach_query_selected_source_packs(
        raw_authority_entries,
        retrieval_sources,
        q,
    )
    authority_ledger = _bind_authority_policy(
        raw_authority_entries,
        retrieval_sources,
        query=q,
    )
    unresolved_mixed_regime = (
        route.legal_regime is None
        and incident_status == "not_required_or_not_detected"
        and any(
            entry.note == "date_dependent_regime_choose_by_incident_date"
            for entry in authority_ledger
        )
    )
    if unresolved_mixed_regime:
        # A non-criminal route can mention a criminal-law fallback (for
        # example, possible breach of trust in a streedhan dispute) without
        # supplying an incident date. Keep that fallback visible, but do not
        # make it an operative authority until the date and facts select a
        # regime. The safety flag below makes the missing intake fact explicit.
        authority_ledger = [
            replace(
                entry,
                priority="conditional",
                must_cite=False,
                conditional=True,
            )
            if entry.note == "date_dependent_regime_choose_by_incident_date"
            else entry
            for entry in authority_ledger
        ]
    is_pmla_asset_owner = (
        plan_owner is not None and plan_owner.scenario_id == "pmla_ed_asset_freeze"
    )
    is_uapa_bail_owner = (
        plan_owner is not None and plan_owner.scenario_id == "uapa_prima_facie_bail"
    )
    # These workflows are governed by asset restraint or bail posture rather
    # than a criminal incident-date cutover. Keep the public MatterPlan field
    # schema-valid while preserving the absence of a criminal legal regime.
    plan_incident_status = (
        "not_applicable_for_asset_restraint"
        if is_pmla_asset_owner
        else "not_applicable_for_uapa_bail"
        if is_uapa_bail_owner
        else "needed_for_criminal_regime"
        if unresolved_mixed_regime
        else incident_status
    )
    plan_legal_regime = (
        None if is_pmla_asset_owner or is_uapa_bail_owner else route.legal_regime
    )
    safety_flags = _safety_flags(
        q,
        route=route,
        role=user_role,
        jurisdiction=jurisdiction,
        incident_date_status=plan_incident_status,
    )
    action_pack = (
        _pmla_asset_restraint_action_pack()
        if is_pmla_asset_owner
        else _uapa_bail_action_pack()
        if is_uapa_bail_owner
        else route.action_pack
    )
    case_stage = _case_stage(q)
    desired_outcome = _desired_outcome(q, route)
    secondary_issues = _secondary_issues(q, route.category)
    if plan_owner is not None and plan_owner.scenario_id == "police_seized_device_return":
        desired_outcome = "device_return_or_interim_custody"
        if has_person_release_context(q):
            secondary_issues = _dedupe([
                *secondary_issues,
                "person-release language requires a separate bail review",
            ])
    forums = _dedupe(
        registry_workflow.forums
        if (is_pmla_asset_owner or is_uapa_bail_owner) and registry_workflow is not None
        else [*(registry_workflow.forums if registry_workflow else ()), *route.forums]
    )
    documents = _dedupe(
        registry_workflow.documents
        if is_uapa_bail_owner and registry_workflow is not None
        else [
            *(registry_workflow.documents if registry_workflow else ()),
            *(action_pack.documents if action_pack else []),
        ]
    )
    next_steps = _dedupe(action_pack.next_steps if action_pack else [])
    portals = _dedupe(action_pack.portals if action_pack else [])
    escalation = _dedupe(
        [
            *(registry_workflow.escalation if registry_workflow else ()),
            *(action_pack.escalation if action_pack else []),
        ]
    )
    remedies = _dedupe(registry_workflow.remedies if registry_workflow else ())
    deadlines = _dedupe(registry_workflow.deadline_rules if registry_workflow else ())
    cautions = _dedupe(action_pack.cautions if action_pack else [])
    requires_reviewed_contract = (
        plan_owner is not None
        or bool(ownership_resolution.conflicts)
        or route.category in REVIEWED_CONTRACT_REQUIRED_CATEGORIES
    )
    answer_policy = AnswerPolicy(
        required_primary_owner=(
            "source_gap_handoff"
            if registry_workflow_no_active_authorities
            else plan_owner.owner_token
            if plan_owner is not None
            else "source_gap_handoff"
            if ownership_resolution.conflicts
            else "reviewed_workflow"
            if requires_reviewed_contract
            else "server_template_or_verified_llm"
        ),
        fallback_owner=(
            plan_owner.fallback_owner if plan_owner is not None else "source_gap_handoff"
        ),
        allow_freeform_llm=(
            False
            if registry_workflow_no_active_authorities
            else not requires_reviewed_contract
        ),
        requires_reviewed_contract=(
            True
            if registry_workflow_no_active_authorities
            else requires_reviewed_contract
        ),
        fallback_reason=(
            "registry_workflow_no_active_authorities"
            if registry_workflow_no_active_authorities
            else "multiple_plan_owners"
            if ownership_resolution.conflicts
            else None
        ),
        conflicting_primary_owners=list(ownership_resolution.conflicts),
        additional_primary_owners=[
            owner.owner_token for owner in ownership_resolution.additional_owners
        ],
    )
    plan_id = _plan_id(
        query=q,
        identity={
            "issue": route.category,
            "label": route.label,
            "confidence": route.confidence,
            "role": user_role,
            "jurisdiction": asdict(jurisdiction),
            "incident_date_status": plan_incident_status,
            "legal_regime": plan_legal_regime,
            "case_stage": case_stage,
            "desired_outcome": desired_outcome,
            "urgency": route.urgency,
            "secondary_issues": secondary_issues,
            "required_facts": required_facts,
            "authority_ledger": [asdict(entry) for entry in authority_ledger],
            "retrieval_sources": [asdict(source) for source in retrieval_sources],
            "forums": forums,
            "remedies": remedies,
            "deadlines": deadlines,
            "documents": documents,
            "action_pack_id": action_pack.id if action_pack else None,
            "action_pack_title": action_pack.title if action_pack else None,
            "next_steps": next_steps,
            "portals": portals,
            "escalation": escalation,
            "cautions": cautions,
            "safety_flags": safety_flags,
            "answer_policy": asdict(answer_policy),
        },
    )

    return MatterPlan(
        schema_version=2,
        plan_id=plan_id,
        primary_issue=route.category,
        primary_label=route.label,
        confidence=route.confidence,
        user_role=user_role,
        jurisdiction=jurisdiction,
        incident_date_status=plan_incident_status,
        legal_regime=plan_legal_regime,
        case_stage=case_stage,
        desired_outcome=desired_outcome,
        urgency=route.urgency,
        secondary_issues=secondary_issues,
        required_facts=required_facts,
        authority_ledger=authority_ledger,
        retrieval_sources=retrieval_sources,
        forums=forums,
        remedies=remedies,
        deadlines=deadlines,
        documents=documents,
        action_pack_id=action_pack.id if action_pack else None,
        action_pack_title=action_pack.title if action_pack else None,
        next_steps=next_steps,
        portals=portals,
        escalation=escalation,
        cautions=cautions,
        safety_flags=safety_flags,
        answer_policy=answer_policy,
    )


def _plan_id(
    *,
    query: str,
    identity: dict,
) -> str:
    payload = {
        "schema_version": 2,
        "query_facts": re.sub(r"[^a-z0-9]+", " ", query.lower()).strip(),
        **identity,
    }
    digest = hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()[:20]
    return f"matter_plan_v2_{digest}"


def _authority_identity(
    entry: AuthorityLedgerEntry,
    canonical_act: str | None,
    *,
    required_anchor_patterns: list[str] | None = None,
) -> tuple[str, Literal["canonical", "provisional"]]:
    if canonical_act:
        anchors = sorted(
            {
                _legal_name(anchor)
                for anchor in (required_anchor_patterns or entry.required_anchor_patterns)
                if anchor
            }
        )
        scope = _legal_name(entry.section) if entry.section else "|".join(anchors) or "all"
        identity = "|".join((canonical_act, scope))
        # A title-level Act match is not section-level legal identity. Keep it
        # provisional until the registry or an explicit provision narrows the
        # claim to a citable authority.
        status: Literal["canonical", "provisional"] = (
            "canonical" if entry.section else "provisional"
        )
    else:
        identity = _normalize(entry.source)
        status = "provisional"
    digest = hashlib.sha256(identity.encode("utf-8")).hexdigest()[:20]
    prefix = "authority" if status == "canonical" else "authority_provisional"
    return f"{prefix}_{digest}", status


def _legal_name(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", (value or "").lower()).strip()


def _act_equivalence_key(act: str | None) -> str:
    name = _legal_name(act or "")
    aliases = {
        "unlawful act": "unlawful activities prevention act 1967",
        "uapa": "unlawful activities prevention act 1967",
    }
    return aliases.get(name, _canonical_alias(act) or name)


def _canonical_alias(act: str | None) -> str | None:
    aliases = {
        "bns": "bharatiya nyaya sanhita 2023",
        "bnss": "bharatiya nagarik suraksha sanhita 2023",
        "bsa": "bharatiya sakshya adhiniyam 2023",
        "constitution": "constitution of india",
        "constitution of india": "constitution of india",
        "crpc": "code of criminal procedure 1973",
        "ipc": "indian penal code 1860",
        "aadhaar act 2016": (
            "aadhaar targeted delivery of financial and other subsidies benefits and services act 2016"
        ),
        "aadhaar act": (
            "aadhaar targeted delivery of financial and other subsidies benefits and services act 2016"
        ),
        # These are curated route vocabulary aliases, not a general
        # yearless-title guess. They are only used against reviewed source
        # packs and remain subject to exact title and sibling-pack checks.
        "transfer of property act": "transfer of property act 1882",
        "registration act": "registration act 1908",
        "nclt rules": "national company law tribunal rules 2016",
        "fssai licensing and registration regulations": (
            "food safety and standards licensing and registration of food businesses regulations 2011"
        ),
        "fssai licensing regulations": (
            "food safety and standards licensing and registration of food businesses regulations 2011"
        ),
        "insurance ombudsman": "insurance ombudsman rules 2017",
        "rbi integrated ombudsman scheme": "reserve bank integrated ombudsman scheme 2021",
        "rbi integrated ombudsman": "reserve bank integrated ombudsman scheme 2021",
        "sarfaesi act 2002": (
            "securitisation and reconstruction of financial assets and enforcement of security interest act 2002"
        ),
        "companies act": "companies act 2013",
        "forest rights act 2006": (
            "scheduled tribes and other traditional forest dwellers recognition of forest rights act 2006"
        ),
        "building and other construction workers act 1996": (
            "building and other construction workers regulation of employment and conditions of service act 1996"
        ),
    }
    return aliases.get(_legal_name(act or ""))


def _explicit_acronym_source_match(
    source: RetrievalSourcePlan,
    prefix: str,
    act_text: str,
) -> bool:
    """Match an acronym only against its reviewed full title and year."""
    expected = _SOURCE_PACK_ACRONYM_ALIASES.get(prefix)
    if expected is None or not re.search(
        rf"(?<![a-z0-9]){re.escape(prefix)}(?![a-z0-9])",
        _normalize(act_text),
    ):
        return False
    expected_name = _legal_name(expected)
    expected_years = set(re.findall(r"\b(?:18|19|20)\d{2}\b", expected_name))
    named_years = set(re.findall(r"\b(?:18|19|20)\d{2}\b", _normalize(act_text)))
    if not expected_years or not expected_years.intersection(named_years):
        return False
    expected_instrument = _instrument_marker(expected)
    named_instrument = _instrument_marker(act_text)
    if expected_instrument and named_instrument and expected_instrument != named_instrument:
        return False
    if expected_instrument == "act" and named_instrument not in (None, "act"):
        return False
    expected_tokens = _source_title_equivalence_tokens(expected_name)
    for title in source.title_patterns:
        title_name = _legal_name(title)
        title_years = set(re.findall(r"\b(?:18|19|20)\d{2}\b", title_name))
        if not expected_years.intersection(title_years):
            continue
        title_instrument = _instrument_marker(title_name)
        if expected_instrument and title_instrument and expected_instrument != title_instrument:
            continue
        if expected_name == title_name or expected_name in title_name:
            return True
        # Parenthetical official titles do not always contain the short
        # acronym expansion as a contiguous string. Require every substantive
        # token in the curated expansion, not merely a two-token overlap:
        # similar Acts must never become an authority binding by accident.
        title_tokens = _source_title_equivalence_tokens(title_name)
        if (
            "act" in title_name.split()
            and expected_tokens
            and expected_tokens.issubset(title_tokens)
        ):
            return True
    return False


def _instrument_marker(value: str) -> str | None:
    for marker in (
        "rules",
        "regulations",
        "scheme",
        "guidelines",
        "directions",
        "manual",
        "notification",
        "order",
        "sanhita",
        "adhiniyam",
        "act",
        "code",
    ):
        if re.search(rf"\b{marker}\b", _normalize(value)):
            return marker
    return None


def _canonical_act_from_sources(
    entry: AuthorityLedgerEntry,
    retrieval_sources: list[RetrievalSourcePlan],
) -> str | None:
    alias = _canonical_alias(entry.act)
    if alias:
        return alias
    if entry.note == "plan_owned_contract_required_source" and entry.source_pack_id is not None:
        source = next(
            (item for item in retrieval_sources if item.source_pack_id == entry.source_pack_id),
            None,
        )
        if source is not None and source.title_patterns:
            return _legal_name(source.title_patterns[0])
    act_name = _legal_name(entry.act or "")
    if (
        not re.search(r"\b(?:18|19|20)\d{2}\b", act_name)
        and entry.note != "plan_owned_contract_required_source"
    ):
        return None
    candidates: set[str] = set()
    for source in retrieval_sources:
        matched = False
        for title in source.title_patterns:
            title_name = _legal_name(title)
            if act_name and (
                act_name == title_name or act_name in title_name or title_name in act_name
            ):
                candidates.add(title_name)
                matched = True
        if matched:
            continue
        prefix = source.source_pack_id.lower().split("_", 1)[0]
        if (
            _explicit_acronym_source_match(source, prefix, act_name)
            and source.title_patterns
        ):
            candidates.add(_legal_name(source.title_patterns[0]))
    return next(iter(candidates)) if len(candidates) == 1 else None


def _bind_authority_policy(
    entries: list[AuthorityLedgerEntry],
    retrieval_sources: list[RetrievalSourcePlan],
    *,
    query: str = "",
) -> list[AuthorityLedgerEntry]:
    bound: list[AuthorityLedgerEntry] = []
    for entry in entries:
        exact_route_pack_ids = {
            "income-tax act / pan procedure where pan record or pan-aadhaar linking is involved": "income_tax_pan_1961",
            "income-tax act 1961 section 139a pan record/correction provision": "income_tax_pan_1961",
            "income-tax act 1961 section 139aa pan-aadhaar linking provision": "income_tax_pan_1961",
            "juvenile justice act 2015 section 10 production and adult-custody transfer provision": "jj_2015_custody_transfer",
            "juvenile justice act 2015 section 94 age-determination evidence hierarchy": "jj_2015_age_documents",
            "juvenile justice act 2015 section 12 bail provision": "jj_2015_bail_board",
        }
        explicit_route_pack_id = exact_route_pack_ids.get(_normalize(entry.source))
        # An IBC route often carries both the Code and the NCLT application
        # forms. When the ledger explicitly asks for the reviewed NCLT forms
        # pack, preserve that authority identity instead of letting the
        # neighboring IBC pack win by title overlap.
        if explicit_route_pack_id and any(
            source.source_pack_id == explicit_route_pack_id
            for source in retrieval_sources
        ):
            source_pack_id = explicit_route_pack_id
        elif entry.source == "NCLT Rules / IBC application forms" and any(
            source.source_pack_id == "nclt_rules_2016"
            for source in retrieval_sources
        ):
            source_pack_id = "nclt_rules_2016"
        else:
            # The MGNREGA integrity route is an either/or obligation: a
            # reviewed BNS forgery passage or a reviewed PCA passage can
            # satisfy it. Binding the ledger to whichever sibling happens to
            # score first turns a valid sibling into a false source gap.
            source_pack_id = (
                None
                if _is_mgnrega_integrity_composite_requirement(entry.source)
                else (
                    entry.source_pack_id
                    if entry.source_pack_id is not None
                    else _matching_source_pack_id(entry, retrieval_sources)
                )
            )
        derived_source_pack = False
        # Only unstructured requirements may use title-overlap binding. An
        # explicitly named but yearless Act (for example, "Consumer
        # Protection Rules") must remain provisional rather than being
        # silently attached to a neighboring Act pack.
        if source_pack_id is None and (
            entry.act is None
            or entry.source.strip().lower() == "bnss/crpc complaint procedure"
        ):
            source_pack_id = _description_source_pack_id(
                entry.source,
                retrieval_sources,
                query,
            )
            derived_source_pack = source_pack_id is not None
        canonical_act = _canonical_act_from_sources(
            replace(entry, source_pack_id=source_pack_id),
            retrieval_sources,
        )
        registry_record = _registry_record_for_entry(entry, canonical_act)
        if registry_record is not None:
            canonical_act = registry_record.canonical_name
            if source_pack_id is None:
                source_pack_id = registry_record.retrieval.source_pack_id
            if source_pack_id is not None:
                for source in retrieval_sources:
                    if source.source_pack_id == source_pack_id:
                        if registry_record.authority_id_expected not in source.authority_ids:
                            source.authority_ids.append(registry_record.authority_id_expected)
                        break
        matching_sources = _authority_retrieval_sources(
            entry,
            canonical_act=canonical_act,
            source_pack_id=source_pack_id,
            retrieval_sources=retrieval_sources,
        )
        if not matching_sources and entry.note == "date_dependent_regime_choose_by_incident_date":
            matching_sources = _date_dependent_retrieval_sources(entry, retrieval_sources)
        required_anchor_patterns = entry.required_anchor_patterns or _dedupe(
            [anchor for source in matching_sources for anchor in source.anchor_patterns if anchor]
        )
        if entry.note == "date_dependent_regime_choose_by_incident_date" and any(
            not source.anchor_patterns for source in matching_sources
        ):
            # One regime may have a reviewed title-level pack while the other
            # has section anchors. A single shared anchor list must not make
            # the title-level regime impossible to satisfy.
            required_anchor_patterns = []
        if registry_record is not None:
            required_anchor_patterns = list(registry_record.provision.all_anchors)
            authority_id = registry_record.authority_id_expected
            identity_status: Literal["canonical", "provisional"] = "canonical"
        else:
            authority_id, identity_status = _authority_identity(
                entry,
                canonical_act,
                required_anchor_patterns=required_anchor_patterns,
            )
            # A title-overlap binding helps retrieve a manual or article pack,
            # but it is not proof that the route requirement has a canonical
            # legal identity. Keep that identity provisional until the
            # authority registry or an explicit Act/section supplies it.
            if derived_source_pack:
                identity_status = "provisional"
        bound.append(
            replace(
                entry,
                authority_id=authority_id,
                registry_key=registry_record.canonical_key if registry_record else None,
                identity_status=identity_status,
                canonical_name=canonical_act,
                source_pack_id=source_pack_id,
                required_anchor_patterns=required_anchor_patterns,
            )
        )
    return bound


def _registry_record_for_entry(
    entry: AuthorityLedgerEntry,
    canonical_act: str | None,
) -> AuthorityRecord | None:
    if entry.registry_key:
        return load_authority_registry().by_key(entry.registry_key)
    if not canonical_act or not entry.section:
        return None
    match = re.search(
        r"\b(section|article|rule|clause|order|paragraph)\s+([0-9][0-9a-z()./-]*)",
        entry.section,
        flags=re.IGNORECASE,
    )
    if not match:
        return None
    return load_authority_registry().resolve(
        canonical_name=canonical_act,
        provision_kind=match.group(1),
        provision_number=match.group(2),
    )


def _authority_retrieval_sources(
    entry: AuthorityLedgerEntry,
    *,
    canonical_act: str | None,
    source_pack_id: str | None,
    retrieval_sources: list[RetrievalSourcePlan],
) -> list[RetrievalSourcePlan]:
    if source_pack_id is not None:
        exact = [
            source for source in retrieval_sources
            if source.source_pack_id == source_pack_id
        ]
        if exact:
            # A source-pack binding is an exact provenance boundary. Similar
            # titles are not enough to prove that two packs share the same
            # document, jurisdiction, version, or provision scope.
            return exact
        # An explicit pack binding is authoritative even when stale or
        # unknown. Never recover by title-matching a sibling pack.
        return []
    if not canonical_act:
        return []
    title_matches = [
        source
        for source in retrieval_sources
        if any(_legal_name(title) == canonical_act for title in source.title_patterns)
    ]
    # If the Act is represented by multiple route packs, do not infer that
    # each pack is interchangeable. The caller must bind an exact pack (or a
    # future registry equivalence record must make that relationship explicit).
    return title_matches if len(title_matches) == 1 else []


def _date_dependent_retrieval_sources(
    entry: AuthorityLedgerEntry,
    retrieval_sources: list[RetrievalSourcePlan],
) -> list[RetrievalSourcePlan]:
    lower_source = entry.source.lower()
    allowed_acts = {
        _legal_name(act)
        for token, act, _ in _CRIMINAL_REGIME_ACTS
        if re.search(rf"(?<![a-z0-9]){re.escape(token)}(?![a-z0-9])", lower_source)
    }
    return [
        source
        for source in retrieval_sources
        if any(_legal_name(title) in allowed_acts for title in source.title_patterns)
    ]


def _matching_source_pack_id(
    entry: AuthorityLedgerEntry,
    retrieval_sources: list[RetrievalSourcePlan],
) -> str | None:
    act_text = _normalize(entry.act or "")
    canonical_act_text = _canonical_alias(entry.act) or act_text
    section_text = _normalize(entry.section or "")
    context_text = _normalize(f"{entry.source} {entry.section or ''}")
    context_tokens = _source_binding_tokens(context_text)
    act_tokens = _source_binding_tokens(act_text)
    act_years = set(re.findall(r"\b(?:18|19|20)\d{2}\b", act_text))
    section_match = re.search(r"\b(?:section|article|order)\s+([0-9][0-9a-z-]*)", section_text)
    section_token = section_match.group(1) if section_match else None
    specific_act = bool(_canonical_alias(entry.act)) or bool(
        re.search(r"\b(?:18|19|20)\d{2}\b", _normalize(entry.act or ""))
    ) or any(
        re.search(rf"(?<![a-z0-9]){re.escape(acronym)}(?![a-z0-9])", act_text)
        for acronym in _SOURCE_PACK_ACRONYM_ALIASES
    )
    candidates: list[tuple[int, str]] = []
    for source in retrieval_sources:
        score = 0
        if specific_act and any(
            _legal_name(title) == canonical_act_text
            or _legal_name(title) in canonical_act_text
            or canonical_act_text in _legal_name(title)
            for title in source.title_patterns
            if title
        ):
            score += 100

        prefix = source.source_pack_id.lower().split("_", 1)[0]
        if _explicit_acronym_source_match(source, prefix, act_text):
            score += 100

        if specific_act and act_years:
            title_text = " ".join(source.title_patterns)
            title_tokens = _source_binding_tokens(title_text)
            title_years = set(re.findall(r"\b(?:18|19|20)\d{2}\b", title_text.lower()))
            if act_years.intersection(title_years) and len(act_tokens.intersection(title_tokens)) >= 2:
                # Parenthetical title expansions (for example, the full
                # Street Vendors and BOCW titles) are safe to match only
                # when the named year and at least two substantive title
                # tokens agree.
                score += 80

        # Route requirements often use an acronym while the indexed pack
        # carries its full title. The explicit equivalence check above keeps
        # this a provenance match rather than a prefix guess.
        selection_tokens = _source_binding_tokens(" ".join(source.selection_terms))
        if score and context_tokens and selection_tokens:
            score += min(20, 5 * len(context_tokens.intersection(selection_tokens)))

        if (
            score
            and section_token
            and any(
                re.search(
                    rf"(?:sec|article|order)[-_/]?{re.escape(section_token)}(?:\D|$)",
                    anchor.lower(),
                )
                for anchor in source.anchor_patterns
            )
        ):
            score += 40

        if score:
            candidates.append((score, source.source_pack_id))

    if not candidates:
        return _contextual_source_pack_id(entry, retrieval_sources)
    candidates.sort(reverse=True)
    tied = [candidate for candidate in candidates if candidate[0] == candidates[0][0]]
    return tied[0][1] if len(tied) == 1 else None


def _contextual_source_pack_id(
    entry: AuthorityLedgerEntry,
    retrieval_sources: list[RetrievalSourcePlan],
) -> str | None:
    """Bind a named route requirement to a reviewed pack when its Act name is
    abbreviated or embedded in a descriptive requirement.

    Route requirements often say ``Guardians and Wards Act / family law`` or
    ``Code on Wages / Payment of Wages law`` while the reviewed pack carries
    the complete statutory title and year. The ordinary binder deliberately
    rejects yearless title guesses, so this fallback requires meaningful title
    overlap plus contextual text outside the bare Act name. It never runs for
    a bare yearless Act such as ``Consumer Protection Act`` and it never
    resolves ties between sibling packs for the same instrument.
    """
    source_text = _normalize(entry.source)
    if not source_text or not retrieval_sources:
        return None
    act_text = _normalize(entry.act or "")
    # Preserve the existing conservative behavior for a bare, yearless Act.
    if entry.act and source_text == act_text and not re.search(r"\b(?:18|19|20)\d{2}\b", source_text):
        return None

    def contextual_title_tokens(value: str) -> set[str]:
        tokens = _source_title_equivalence_tokens(value)
        # ``code`` is a meaningful instrument marker for Code on Wages and
        # Code of Criminal Procedure, even though it is ignored by the
        # broader title-equivalence helper.
        if re.search(r"\bcode\b", _normalize(value)):
            tokens.add("code")
        return tokens

    reference_tokens = contextual_title_tokens(source_text)
    if len(reference_tokens) < 2:
        return None
    years = set(re.findall(r"\b(?:18|19|20)\d{2}\b", source_text))
    candidates: list[tuple[int, float, str]] = []
    for source in retrieval_sources:
        title_text = " ".join(source.title_patterns)
        title_tokens = contextual_title_tokens(title_text)
        title_years = set(re.findall(r"\b(?:18|19|20)\d{2}\b", title_text))
        if years and not years.intersection(title_years):
            continue
        if not re.search(r"\bact\b", source_text):
            # A route requirement that names Rules, Regulations, a Scheme, or
            # Guidelines must not attach itself to a similarly titled Act.
            # Requirements that explicitly say ``Act / state rules`` are
            # allowed to bind the named Act; the local rules remain a
            # separate, unbound intake requirement.
            if any(
                marker in reference_tokens and marker not in title_tokens
                for marker in ("rules", "regulations", "scheme", "guidelines", "manual")
            ):
                continue
        overlap = reference_tokens.intersection(title_tokens)
        if len(overlap) < 2:
            continue

        # Instrument-specific words are provenance boundaries. A generic
        # BOCW requirement must not silently select the separate Cess Act;
        # a requirement that names Regulations/Rules must name that instrument.
        for marker in ("cess", "regulations", "rules", "scheme", "guidelines", "manual"):
            title_has_marker = marker in title_tokens
            reference_has_marker = marker in reference_tokens
            if title_has_marker and not reference_has_marker:
                break
        else:
            score = len(overlap) * 10
            if years:
                score += 5
            candidates.append((score, source.priority, source.source_pack_id))

    if not candidates:
        return None
    candidates.sort(reverse=True)
    best = candidates[0]
    tied = [candidate for candidate in candidates if candidate[:2] == best[:2]]
    return best[2] if len(tied) == 1 else None


def _source_binding_tokens(value: str | None) -> set[str]:
    return {
        token[:8]
        for token in re.findall(r"[a-z0-9]+", _normalize(value or ""))
        if len(token) > 3 and token not in _SOURCE_BINDING_STOPWORDS
    }


def _source_title_equivalence_tokens(value: str | None) -> set[str]:
    """Return full tokens for reviewed-title identity checks.

    Search/selection heuristics intentionally shorten tokens to absorb minor
    wording variation. Authority equivalence cannot do that: near-spellings
    such as ``panchayats`` and ``panchayati`` must remain distinct.
    """
    return {
        token
        for token in re.findall(r"[a-z0-9]+", _normalize(value or ""))
        if len(token) > 3 and token not in _SOURCE_BINDING_STOPWORDS and not token.isdigit()
    }


def _attach_query_selected_source_packs(
    entries: list[AuthorityLedgerEntry],
    retrieval_sources: list[RetrievalSourcePlan],
    query: str,
) -> list[AuthorityLedgerEntry]:
    """Attach a reviewed route pack before identity binding when query terms
    uniquely select one same-title pack.

    This is a route-selection step, not a provenance-equivalence assertion.
    Once attached, all later passage matching requires that exact pack ID.
    Equal route vocabulary remains ambiguous and is left unbound.
    """
    query_tokens = _source_binding_tokens(query)
    out: list[AuthorityLedgerEntry] = []
    for entry in entries:
        if entry.source_pack_id is not None or not entry.act:
            out.append(entry)
            continue
        canonical_act = _canonical_alias(entry.act)
        title_matches = [
            source
            for source in retrieval_sources
            if any(
                _legal_name(title) == _legal_name(entry.act)
                or (canonical_act is not None and _legal_name(title) == canonical_act)
                for title in source.title_patterns
                if title
            )
        ]
        if len(title_matches) <= 1:
            out.append(entry)
            continue
        # Same-title packs can cover different provisions. Prefer packs whose
        # reviewed anchor scope actually contains this ledger section before
        # applying query-specific selection terms; otherwise a Section 142
        # obligation can be attached to a Section 138-only security pack.
        if entry.section:
            section_match = re.search(
                r"\b(?:section|sec\.?|article|order|clause)\s+"
                r"([0-9][0-9a-z()./-]*)",
                entry.section,
                flags=re.IGNORECASE,
            )
            if section_match:
                section_token = section_match.group(1).lower()
                section_token = section_token.replace("(", "-").replace(")", "")
                section_token = re.sub(r"[^0-9a-z-]+", "-", section_token).strip("-")
                scoped_matches = [
                    source
                    for source in title_matches
                    if any(
                        re.search(
                            rf"/(?:sec|article|order|clause)-{re.escape(section_token)}"
                            rf"(?:-|@|__|$)",
                            anchor.lower(),
                        )
                        for anchor in source.anchor_patterns
                    )
                ]
                if scoped_matches:
                    title_matches = scoped_matches
                else:
                    # A section-specific ledger obligation must never fall
                    # back to a sibling pack whose reviewed anchors cover a
                    # different provision. Leave it unbound so the
                    # fail-closed source-gap gate can hand off safely.
                    out.append(entry)
                    continue
        entry_tokens = _source_binding_tokens(
            " ".join(value for value in (entry.source, entry.section or "") if value)
        )
        scored: list[tuple[int, int, float, str]] = []
        for source in title_matches:
            selection_tokens = _source_binding_tokens(" ".join(source.selection_terms))
            query_score = len(query_tokens.intersection(selection_tokens))
            entry_score = len(entry_tokens.intersection(selection_tokens))
            # The query chooses the scenario; the ledger description chooses
            # the provision within that scenario. This matters when several
            # reviewed packs share an Act title (for example JJ age proof vs
            # JJ bail), where query-only scoring can bind both obligations to
            # the same sibling pack.
            # Priority is a reviewed-pack specificity signal. Use it only
            # after query and ledger vocabulary; equal-vocabulary siblings
            # with equal priority remain ambiguous and fail closed.
            scored.append((query_score, entry_score, source.priority, source.source_pack_id))
        scored.sort(reverse=True)
        # A child-specific succession pack can tie the base pack on a query
        # such as "Christian widow ... children" (widow selects the base,
        # children selects the child pack). Prefer the narrower reviewed pack
        # whenever the query explicitly names a child relationship.
        child_terms = {"child", "children", "stepchild", "stepchildren"}
        child_matches = [
            source
            for source in title_matches
            if query_tokens.intersection(child_terms)
            and query_tokens.intersection(
                _source_binding_tokens(" ".join(source.selection_terms))
            ).intersection(child_terms)
        ]
        if len(child_matches) == 1:
            out.append(replace(entry, source_pack_id=child_matches[0].source_pack_id))
        elif scored[0][:3] > (0, 0, 0.0) and (
            len(scored) == 1 or scored[0][:3] > scored[1][:3]
        ):
            out.append(replace(entry, source_pack_id=scored[0][3]))
        else:
            out.append(entry)
    return out


def _augment_owner_retrieval_sources(
    owner: PlanOwnedAnswerRoute | None,
    retrieval_sources: list[RetrievalSourcePlan],
    route: MatterRoute,
    query: str = "",
) -> list[RetrievalSourcePlan]:
    """Make route retrieval satisfy an owned contract's exact evidence scope.

    A route pack may be useful context for a broad matter, while the released
    answer owner requires narrower provisions from that same Act.  Keep one
    pack identity, but union the owner's reviewed anchors and search terms so
    retrieval cannot silently fetch only the route-context sections.
    """
    if owner is None or owner.owner_provider != "authority_graph":
        return retrieval_sources

    from .authority_graph import authority_graph_contract_required_source_specs

    specs = authority_graph_contract_required_source_specs(
        owner.owner_contract_id,
        route,
        query=query,
    )
    if not specs:
        return retrieval_sources

    required_document_ids_by_pack: dict[str, list[str]] = {}
    for spec in specs:
        if spec.source_pack_id and spec.document_ids:
            required_document_ids_by_pack.setdefault(spec.source_pack_id, [])
            required_document_ids_by_pack[spec.source_pack_id] = _dedupe([
                *required_document_ids_by_pack[spec.source_pack_id],
                *spec.document_ids,
            ])

    augmented = list(retrieval_sources)
    for spec in specs:
        if not spec.source_pack_id:
            continue
        matching_indices = [
            index
            for index, source in enumerate(augmented)
            if source.source_pack_id == spec.source_pack_id
        ]
        if not matching_indices:
            continue
        for index in matching_indices:
            source = augmented[index]
            anchor_patterns = _dedupe([
                *source.anchor_patterns,
                *spec.anchor_terms,
            ])
            search_query = " ".join(_dedupe([
                source.search_query,
                *spec.title_terms,
                *spec.anchor_terms,
            ]))
            doc_ids = required_document_ids_by_pack.get(
                spec.source_pack_id,
                source.doc_ids,
            )
            augmented[index] = replace(
                source,
                search_query=search_query,
                anchor_patterns=anchor_patterns,
                doc_ids=list(doc_ids),
            )
    return augmented


_SOURCE_BINDING_STOPWORDS = frozenset(
    {
        "a", "an", "and", "as", "at", "based", "for", "from", "in", "of",
        "or", "relevant", "source", "state", "the", "to",
        "where", "with", "under", "act", "code", "law", "authority",
    }
)


def _is_mgnrega_integrity_composite_requirement(description: str) -> bool:
    normalized = _normalize(description)
    return (
        "prevention of corruption" in normalized
        and "bns" in normalized
        and "mgnrega" not in normalized
    )


def _description_source_pack_id(
    description: str,
    retrieval_sources: list[RetrievalSourcePlan],
    query: str = "",
) -> str | None:
    """Bind an unstructured route requirement only on strong title overlap.

    Router requirements sometimes name a jurisdictional/manual source rather
    than an Act (for example, ``state prison rules / prison manual``). Leaving
    those entries unbound makes every retrieved manual chunk invisible to the
    MatterPlan authority ledger. This helper is deliberately conservative: it
    requires at least two meaningful title tokens and a unique best match.
    """
    description_tokens = {
        token
        for token in re.findall(r"[a-z0-9]+", _normalize(description))
        if len(token) > 2 and token not in _SOURCE_BINDING_STOPWORDS
    }
    if len(description_tokens) < 2:
        return None

    description_lower = _normalize(description)

    # This route requirement is an either/or criminal evidence obligation.
    # Binding it to the BNS pack would make a valid Prevention of Corruption
    # passage fail the MatterPlan provenance gate before the composite matcher
    # gets a chance to accept it.
    if _is_mgnrega_integrity_composite_requirement(description_lower):
        return None

    # These reviewed route labels are deliberately not document titles. Bind
    # them only to their exact pack IDs; a neighboring judgment or Act must
    # never become a provenance substitute merely because its words overlap.
    exact_route_pack_ids = {
        "supreme court pmla bail/arrest precedents": "pmla_sc_precedents",
        "constitutional reproductive autonomy and privacy precedents": (
            "mtp_reproductive_autonomy_sc_precedents"
        ),
        "aadhaar act / uidai correction procedure": "aadhaar_2016",
        "rbi/banking grievance and ombudsman procedure for education-loan refusal": (
            "rbi_integrated_ombudsman_2021"
        ),
        "nclt rules / ibc application forms": "nclt_rules_2016",
        "nclt/registrar of companies route for restoration": "nclt_rules_2016",
        "juvenile justice act 2015 section 10 production and adult-custody transfer provision": (
            "jj_2015_custody_transfer"
        ),
        "juvenile justice act 2015 section 94 age-determination evidence hierarchy": (
            "jj_2015_age_documents"
        ),
        "juvenile justice act 2015 section 12 bail provision": "jj_2015_bail_board",
    }
    for label, source_pack_id in exact_route_pack_ids.items():
        if label in description_lower:
            exact = [
                source
                for source in retrieval_sources
                if source.source_pack_id == source_pack_id
            ]
            if len(exact) == 1:
                return source_pack_id

    # These route-owned descriptions have an exact reviewed pack already
    # selected by the router. Bind only that pack identity; fuzzy title
    # overlap must not turn a neighboring Act into the controlling source.
    exact_description_pack_ids = (
        ("mgnrega 2005", "mgnrega_2005"),
        ("esi medical-benefit and contribution eligibility procedure", "esi_1948"),
        ("labour authority / esi court procedure", "esi_1948"),
        ("rti/public grievance route for payment status and sanction records", "rti_2005"),
        ("medical board / appropriate authority procedure", "surrogacy_2021"),
    )
    for marker, source_pack_id in exact_description_pack_ids:
        if marker in description_lower:
            exact = [
                source
                for source in retrieval_sources
                if source.source_pack_id == source_pack_id
            ]
            if len(exact) == 1:
                return source_pack_id

    # State-law packs are selected from the query, but a generic label must
    # never attach itself to the default state pack. Bind only when the
    # question names a state or a city that uniquely identifies a reviewed
    # pack.
    if "witch-hunting statute" in description_lower:
        state_pack_id: str | None = None
        query_lower = query.lower()
        if any(term in query_lower for term in ("jharkhand", "ranchi", "chaibasa")):
            state_pack_id = "jharkhand_witch_daain_2001"
        elif any(term in query_lower for term in ("assam", "barpeta", "guwahati", "dibrugarh", "jorhat")):
            state_pack_id = "assam_witch_hunting_2015"
        elif any(term in query_lower for term in ("chhattisgarh", "raipur", "bastar", "tonahi")):
            state_pack_id = "chhattisgarh_tonahi_2005"
        if state_pack_id and any(
            source.source_pack_id == state_pack_id for source in retrieval_sources
        ):
            return state_pack_id

    # The BOCW/Factories requirement is a deliberate two-instrument
    # conditional. Resolve it from the query facts when exactly one reviewed
    # pack is applicable; leave it unbound if both remain plausible.
    if "bocw act 1996" in description_lower and "factories act 1948" in description_lower:
        normalized_query = _normalize(query)
        construction_terms = (
            "construction", "building", "mason", "scaffold", "site", "worksite",
            "thekedar", "contractor", "bocw",
        )
        factory_terms = (
            "factory", "brick kiln", "brick-kiln", "boiler", "plant", "machine",
        )
        preferred_ids = []
        if any(term in normalized_query for term in construction_terms):
            preferred_ids.append("bocw_1996")
        if any(term in normalized_query for term in factory_terms):
            preferred_ids.append("factories_1948")
        preferred = [
            source
            for source in retrieval_sources
            if source.source_pack_id in preferred_ids
        ]
        if len(preferred) == 1:
            return preferred[0].source_pack_id

    # Constitutional route descriptions often say only "Article 21" or
    # "Article 22" even though the reviewed pack is titled simply
    # ``Constitution of India``. Bind a single article to the exact standard
    # pack when it is present; a combined Article 21/22 description is left
    # for passage-level verification because no one pack represents both.
    article_numbers = set(
        re.findall(r"\barticle\s+([0-9]+)\b", description_lower)
    )
    for match in re.finditer(
        r"\barticles\s+([0-9]+)((?:\s*(?:,|and|&)\s*[0-9]+)*)\b",
        description_lower,
    ):
        article_numbers.update(re.findall(r"[0-9]+", match.group(0)))
    if re.search(
        r"\barticles?\s*[0-9]+\s*(?:/|&|,|and)\s*[0-9]+\b",
        description_lower,
    ):
        return None
    if len(article_numbers) == 1:
        article_number = next(iter(article_numbers))
        exact_pack_id = f"constitution_article_{article_number}"
        exact_pack = [
            source
            for source in retrieval_sources
            if source.source_pack_id == exact_pack_id
        ]
        if len(exact_pack) == 1:
            return exact_pack[0].source_pack_id
        article_matches = [
            source
            for source in retrieval_sources
            if "constitution" in " ".join(source.title_patterns).lower()
            and any(
                re.search(
                    rf"(?:^|/)(?:sec|article)[-_/]?{re.escape(article_number)}(?:@|__|$)",
                    anchor.lower(),
                )
                for anchor in source.anchor_patterns
            )
        ]
        if len(article_matches) == 1:
            return article_matches[0].source_pack_id
        return None

    scored: list[tuple[int, float, str]] = []
    for source in retrieval_sources:
        title_tokens = {
            token
            for title in source.title_patterns
            for token in re.findall(r"[a-z0-9]+", _normalize(title))
            if len(token) > 2 and token not in _SOURCE_BINDING_STOPWORDS
            and not token.isdigit()
        }
        overlap = description_tokens.intersection(title_tokens)
        if (
            "constitution" in description_lower
            and "article" in description_lower
            and "constitution" not in " ".join(title_tokens)
        ):
            continue
        if (
            "prison" in description_lower
            and any(term in description_lower for term in ("rule", "rules", "manual"))
            and (
                {"prison", "rule"}.issubset(title_tokens)
                or {"prison", "rules"}.issubset(title_tokens)
                or {"prison", "manual"}.issubset(title_tokens)
            )
        ):
            scored.append((2, 1.0, source.source_pack_id))
            continue
        if (
            "nclat" in description_lower
            and any(term in description_lower for term in ("rule", "rules", "form", "fees"))
            and "appellate tribunal" in " ".join(source.title_patterns).lower()
            and "rule" in " ".join(source.title_patterns).lower()
        ):
            scored.append((2, 1.0, source.source_pack_id))
            continue
        if (
            "constitution" in description_lower
            and "article" in description_lower
            and "constitution" in title_tokens
        ):
            scored.append((2, 1.0, source.source_pack_id))
            continue
        if len(overlap) < 2:
            continue
        ratio = len(overlap) / max(1, len(title_tokens))
        if ratio < 0.5:
            continue
        scored.append((len(overlap), ratio, source.source_pack_id))

    if not scored:
        return None
    scored.sort(reverse=True)
    best = scored[0]
    if len(scored) > 1 and scored[1][:2] == best[:2]:
        return None
    return best[2]


def authority_ids_for_passage(
    plan: MatterPlan,
    *,
    title: str,
    anchor: str,
    text: str | None = None,
    source_pack_id: str | None = None,
    source_type: str | None = None,
) -> list[str]:
    """Return plan authority IDs exactly represented by one passage."""
    title_name = _legal_name(title)
    anchor_lower = (anchor or "").lower()
    matched: list[str] = []
    for entry in plan.authority_ledger:
        if not entry.authority_id:
            continue
        if entry.source_pack_id is not None and source_pack_id != entry.source_pack_id:
            # A plan-owned or route-selected pack is an exact provenance
            # boundary. Missing pack metadata is not identity evidence.
            continue
        matching_sources = _authority_retrieval_sources(
            entry,
            canonical_act=entry.canonical_name,
            source_pack_id=entry.source_pack_id,
            retrieval_sources=plan.retrieval_sources,
        )
        if not matching_sources and entry.note == "date_dependent_regime_choose_by_incident_date":
            matching_sources = _date_dependent_retrieval_sources(entry, plan.retrieval_sources)
        allowed_titles = {
            _legal_name(title_pattern)
            for source in matching_sources
            for title_pattern in source.title_patterns
            if title_pattern
        }
        source_pack_matches = bool(
            source_pack_id is not None
            and matching_sources
            and any(source.source_pack_id == source_pack_id for source in matching_sources)
        )
        title_matches = title_name in allowed_titles or (
            source_pack_matches
            and any(
                allowed_title and allowed_title in title_name for allowed_title in allowed_titles
            )
        )
        if not title_name or not title_matches:
            continue
        if (
            source_pack_id is not None
            and matching_sources
            and all(source.source_pack_id != source_pack_id for source in matching_sources)
        ):
            continue
        if matching_sources and (
            not source_type
            or all(source_type not in source.source_types for source in matching_sources)
        ):
            continue
        if entry.section and not _passage_anchor_matches_section(
            anchor_lower,
            entry.section,
            passage_text=text,
        ):
            # Reviewed source-pack metadata may publish a canonical section
            # under a split-anchor alias such as 436A -> 436-a. When the
            # ledger also carries that exact reviewed anchor, accept the
            # alias without requiring a chunk heading; an unrelated section
            # still cannot satisfy the explicit pattern.
            if text or not entry.required_anchor_patterns:
                continue
            section_match = re.search(
                r"\b(?:section|sec\.?|article|order|clause)\s+([0-9][0-9a-z()./-]*)",
                entry.section,
                flags=re.IGNORECASE,
            )
            anchor_match = re.search(
                r"(?:sec|article|order)[-_/]?([0-9][0-9a-z-]*)",
                anchor_lower,
            )
            if not section_match or not anchor_match:
                continue
            section_token = re.sub(
                r"[^0-9a-z-]+", "-", section_match.group(1).lower()
            ).strip("-")
            anchor_token = anchor_match.group(1).lower().strip("-")
            if anchor_token.replace("-", "") != section_token.replace("-", ""):
                continue
            if not _passage_anchor_matches_patterns(
                anchor_lower,
                entry.required_anchor_patterns,
            ):
                continue
        if (
            not entry.section
            and entry.required_anchor_patterns
            and not _passage_anchor_matches_patterns(anchor_lower, entry.required_anchor_patterns)
        ):
            continue
        matched.append(entry.authority_id)
    return _dedupe(matched)


def _passage_anchor_matches_section(
    anchor: str,
    section: str,
    *,
    passage_text: str | None = None,
) -> bool:
    match = re.search(
        r"\b(?:section|sec\.?|article|order|clause)\s+([0-9][0-9a-z()./-]*)",
        section,
        flags=re.IGNORECASE,
    )
    if not match:
        return True
    token = match.group(1).lower().replace("(", "-").replace(")", "")
    token = re.sub(r"[^0-9a-z-]+", "-", token).strip("-")
    anchor_match = re.search(r"(?:sec|article|order)[-_/]?([0-9][0-9a-z-]*)", anchor)
    if not anchor_match:
        return False
    anchor_token = anchor_match.group(1).lower().strip("-")
    if anchor_token == token:
        return True
    # The BNSS projection uses the stable split anchor `/sec-173-c` for the
    # operative paragraph 173(4). Its legal identity is declared by the
    # canonical heading, not by treating `c` as a statutory suffix.
    if token == "173-4" and anchor_token == "173-c":
        return bool(passage_text) and _passage_heading_matches_section(
            passage_text,
            token,
        )
    if anchor_token.replace("-", "") == token.replace("-", ""):
        # Keep historical aliases such as Section 436A -> sec-436-a, but
        # require the passage heading when a numeric section is split into a
        # suffix that could also denote a neighboring provision (142 vs 142A).
        if "-" in anchor_token and "-" not in token:
            if not passage_text:
                return False
            return _passage_heading_matches_section(passage_text, token)
        return True
    # A reviewed subsection requirement may intentionally use its parent
    # section anchor (for example, PESA Section 4(c) -> sec-4).
    if "-" in token and anchor_token == token.split("-", 1)[0]:
        return bool(passage_text) and _passage_heading_matches_section(passage_text, token)

    # A section may be split across suffixed chunk anchors (for example,
    # Section 142 -> sec-142-a ... sec-142-e). The suffix alone cannot prove
    # identity because Section 142A is a neighboring provision. Accept the
    # split form only when the passage text names the requested section.
    if not anchor_token.startswith(f"{token}-") or not passage_text:
        return False
    return _passage_heading_matches_section(passage_text, token)


def _passage_heading_matches_section(
    passage_text: str,
    expected: str | tuple[str, ...],
) -> bool:
    """Match a provision only from a heading-shaped line, not a cross-reference.

    Split chunks can legitimately use anchors such as ``sec-142-b`` while
    neighboring provisions such as Section 142A share the same numeric root.
    A later sentence saying "see Section 142" is not identity evidence, so
    only the first few heading lines are considered and the section marker
    must begin a line or follow heading punctuation.
    """
    expected_values = (expected,) if isinstance(expected, str) else expected
    wanted = {
        re.sub(r"[^0-9a-z]+", "", str(value or "").lower())
        for value in expected_values
    }
    wanted.discard("")
    if not wanted:
        return False
    lines = [line.strip() for line in str(passage_text or "").splitlines() if line.strip()]
    for line in lines[:3]:
        section_match = re.search(
            r"(?:^|[,:(])\s*(?:section|sec\.?|article|order|clause)\s+"
            r"([0-9][0-9a-z()./-]*)",
            line,
            flags=re.IGNORECASE,
        )
        if section_match:
            raw_found = section_match.group(1).lower()
            found = re.sub(r"[^0-9a-z]+", "", raw_found)
            if found in wanted:
                return True
            # A split chunk for a numeric provision may start with a
            # subsection heading (for example, ``Section 173(1)``).  That is
            # still the parent provision, whereas ``Section 173A`` is a
            # distinct neighbouring provision and must not satisfy it.
            if any(
                re.fullmatch(rf"{re.escape(value)}\([0-9a-z]+\)", raw_found)
                for value in wanted
                if value.isdigit()
            ):
                return True
        numeric_match = re.match(
            r"^\s*([0-9][0-9a-z]*(?:\([a-z0-9]+\))?)(?:\s*[.)-]|\s+)",
            line,
            flags=re.IGNORECASE,
        )
        if numeric_match:
            raw_found = numeric_match.group(1).lower()
            found = re.sub(r"[^0-9a-z]+", "", raw_found)
            if found in wanted:
                return True
            if any(
                re.fullmatch(rf"{re.escape(value)}\([0-9a-z]+\)", raw_found)
                for value in wanted
                if value.isdigit()
            ):
                return True
    return False


def _passage_heading_matches_exact_section(
    passage_text: str,
    expected: str | tuple[str, ...],
) -> bool:
    """Match only the explicitly named heading, including a subsection.

    This is used for corpus-specific split anchors where two chunks share a
    numeric parent but represent different legal subsections, such as BNSS
    ``sec-173-a`` versus ``sec-173-c``.
    """
    expected_values = (expected,) if isinstance(expected, str) else expected
    wanted = {
        re.sub(r"[^0-9a-z]+", "", str(value or "").lower())
        for value in expected_values
    }
    wanted.discard("")
    if not wanted:
        return False
    lines = [line.strip() for line in str(passage_text or "").splitlines() if line.strip()]
    for line in lines[:3]:
        section_match = re.search(
            r"(?:^|[,:(])\s*(?:section|sec\.?|article|order|clause)\s+"
            r"([0-9][0-9a-z()./-]*)",
            line,
            flags=re.IGNORECASE,
        )
        if section_match:
            found = re.sub(r"[^0-9a-z]+", "", section_match.group(1).lower())
            if found in wanted:
                return True
        numeric_match = re.match(
            r"^\s*([0-9][0-9a-z]*(?:\([a-z0-9]+\))?)(?:\s*[.)-]|\s+)",
            line,
            flags=re.IGNORECASE,
        )
        if numeric_match:
            found = re.sub(r"[^0-9a-z]+", "", numeric_match.group(1).lower())
            if found in wanted:
                return True
    return False


def _passage_anchor_matches_patterns(anchor: str, patterns: list[str]) -> bool:
    for pattern in patterns:
        needle = pattern.lower().lstrip("/")
        if not needle:
            continue
        if needle.startswith(("sec-", "article-", "order-", "rule-")):
            if needle.endswith("-"):
                needle = needle.rstrip("-")
            if re.search(rf"(?:^|[/#]){re.escape(needle)}(?=@|-|__|$)", anchor):
                return True
        elif needle in anchor:
            return True
    return False


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


def _certificate_category(query: str) -> str | None:
    """Select SC or ST only when the wording identifies one category."""
    normalized = _normalize(query)
    if re.search(
        r"\bsc\s*/\s*st\b|\bsc\s*-\s*st\b|\bsc\s+st\b|\bsc\s+or\s+st\b|"
        r"\bscheduled\s+caste\s+or\s+scheduled\s+tribe\b",
        normalized,
    ):
        return None
    is_st = _has_any(
        normalized,
        ("st certificate", "st cert", "scheduled tribe", "tribe certificate", "tribal certificate"),
    )
    is_sc = _has_any(
        normalized,
        ("sc certificate", "sc cert", "scheduled caste"),
    )
    if is_st == is_sc:
        return None
    return "st" if is_st else "sc"


def _extract_jurisdiction(q: str, route: MatterRoute) -> JurisdictionPlan:
    state = next((term for term in _STATE_TERMS if _wordish_contains(q, term)), None)
    city = next((term for term in _CITY_TO_STATE if _wordish_contains(q, term)), None)
    if state is None and city:
        state = _CITY_TO_STATE[city]
    forum = next((term for term in _FORUM_TERMS if term in q), None)
    needs_state = any(
        "state" in fact.lower() or "city" in fact.lower() for fact in route.missing_facts
    )
    return JurisdictionPlan(
        state=state,
        city=city,
        forum_mentioned=forum,
        needs_state=needs_state and state is None and city is None,
    )


def _wordish_contains(text: str, term: str) -> bool:
    return re.search(rf"(?<![a-z0-9]){re.escape(term)}(?![a-z0-9])", text) is not None


def _extract_user_role(q: str, category: str) -> str:
    if category == "workplace_sexual_harassment" and _is_workplace_harassment_respondent(q):
        return "accused_or_accused_family"
    if category == "workplace_sexual_harassment":
        return "complainant_or_victim"
    if _is_victim_bail_opposition_context(q):
        if category == "sexual_offence_survivor" or _has_any(
            q, ("survivor", "rape", "sexual offence", "sexual assault")
        ):
            return "sexual_offence_survivor_or_complainant"
        return "complainant_or_victim"
    if _is_victim_or_witness_against_accused(q):
        if _has_any(q, ("witness", "gawah")):
            return "witness_or_complainant"
        return "complainant_or_victim"
    if _has_any(q, ("witness", "gawah")) and _has_any(
        q, ("notice", "summons", "police called", "police call")
    ):
        return "witness_or_notice_recipient"
    if _is_user_accused_context(q) or _has_any(
        q, ("chargesheet", "charge sheet", "arrested", "arrest me")
    ):
        return "accused_or_accused_family"
    if category in {"criminal_defence_bail", "undertrial_review_release"}:
        return "accused_or_accused_family"
    if _has_any(
        q,
        ("undertrial", "in jail", "judicial custody", "police custody", "remand", "nbw", "warrant"),
    ):
        return "accused_or_accused_family"
    medical_family_context = _has_any(
        q, ("my father", "my mother", "my 80", "hospital", "doctor")
    ) and _has_any(
        q,
        (
            "hospital",
            "doctor",
            "clinic",
            "wrong leg",
            "wrong surgery",
            "wrong operation",
            "operated wrong",
            "wrong injection",
            "medical negligence",
            "died",
            "death",
        ),
    )
    if category == "consumer" and medical_family_context:
        return "patient_or_family"
    senior_home_context = (
        category in {"senior_citizen", "senior_citizen_maintenance"}
        or _has_any(
            q,
            (
                "senior citizen",
                "my son threw me",
                "my daughter threw me",
                "threw me out of my own house",
                "old age pension",
                "75 yrs",
                "80 yr",
            ),
        )
        or (
            _has_any(q, ("my father", "my mother"))
            and _has_any(
                q,
                (
                    "75",
                    "80",
                    "senior",
                    "maintenance",
                    "gifted",
                    "transferred",
                    "threw",
                    "not maintaining",
                ),
            )
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
            if _is_active_accusation_context(q) or _has_any(
                q, ("police not filing", "not filing fir", "complaint")
            ):
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
    if category in {"employment_wages", "labour_exploitation_discrimination"} and _has_any(
        q,
        (
            "worker",
            "asha",
            "nrega",
            "mgnrega",
            "job card",
            "not paid",
            "honorarium",
            "construction",
            "factory",
            "labour",
            "labor",
            "employee",
            "contractor",
        ),
    ):
        return "employee_or_worker"
    if category == "consumer" and _has_any(
        q,
        (
            "from customer",
            "customer filed",
            "customer complaint",
            "consumer complaint from customer",
            "against my shop",
            "by my shop",
        ),
    ):
        return "business_or_service_provider_respondent"
    if _has_any(q, ("police not filing", "fir", "complaint", "stolen", "fraud", "harassment")):
        return "complainant_or_victim"
    if category == "cyber_fraud_or_harassment" and _has_any(
        q,
        (
            "data breach",
            "pan",
            "aadhaar leaked",
            "otp",
            "extortion",
            "account hacked",
            "money taken",
            "fraud",
            "leaked",
        ),
    ):
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
    if _has_any(
        q,
        (
            "court ordered",
            "court order",
            "as per court order",
            "tribunal ordered",
            "decree",
            "judgment debtor",
            "order passed",
        ),
    ):
        return "order_or_decree_exists"
    if _has_any(
        q,
        (
            "award passed",
            "award not paid",
            "execution",
            "execute order",
            "order not complied",
            "not complying with order",
        ),
    ):
        return "execution_or_compliance_stage"
    if _has_any(q, ("undertrial", "in jail", "judicial custody", "police custody", "remand")):
        return "custody_or_trial_pending"
    if _has_any(q, ("fir", "crime number")):
        return "fir_or_police_case"
    if _has_any(
        q,
        (
            "legal notice",
            "notice under",
            "notice received",
            "received notice",
            "show cause",
            "sent me notice",
            "got notice",
            "summons",
            "nbw",
            "warrant",
        ),
    ):
        return "notice_stage"
    if _has_any(
        q, ("case filed", "petition filed", "complaint pending", "case pending", "hearings")
    ):
        return "case_filed_or_pending"
    if _has_any(q, ("complained", "complaint filed", "written complaint")):
        return "complaint_made"
    return "pre_complaint_or_unknown"


def _desired_outcome(q: str, route: MatterRoute) -> str:
    if _has_any(
        q,
        (
            "notice under",
            "notice received",
            "show cause",
            "sent me notice",
            "got notice",
            "summons",
        ),
    ):
        if _has_any(q, ("witness", "gawah")):
            return "witness_notice_response"
        if route.category == "tax_gst_compliance":
            return "tax_notice_response"
        if route.category == "banking_credit_dispute" or _has_any(q, ("sarfaesi", "13(2)", "13 2")):
            return "sarfaesi_or_banking_notice_response"
        if route.category == "property_tenancy" or _has_any(
            q, ("rent act", "vacate", "eviction notice")
        ):
            return "tenancy_notice_response"
        if route.category == "consumer":
            return "consumer_notice_response"
        if route.category in _CRIMINAL_CATEGORIES or _has_any(
            q, ("41a", "41 a", "police", "bnss", "bns", "crpc", "ipc")
        ):
            return "defence_or_notice_response"
        return "notice_response"
    if _is_victim_bail_threat_context(q):
        return "victim_protection_or_bail_cancellation"
    if _has_any(q, ("witness", "gawah")) and _has_any(
        q, ("statement", "recording", "not recording", "police not recording")
    ):
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
        (
            "defence_or_notice_response",
            ("notice under", "sent me notice", "got notice", "reply to notice"),
        ),
        ("refund_or_compensation", ("refund", "compensation", "recover money", "hospital bill")),
        ("eviction_or_possession", ("not vacating", "evict", "possession")),
        (
            "maintenance_enforcement",
            ("maintenance", "child support", "stopped paying", "tribunal ordered"),
        ),
        (
            "document_correction_or_certificate",
            ("birth certificate", "ration card", "aadhaar", "certificate"),
        ),
        ("appeal_or_quashing", ("appeal", "quash", "quashing", "482", "528")),
        (
            "order_execution_or_enforcement",
            (
                "execution",
                "execute order",
                "order not complied",
                "not paying child support",
                "as per court order",
            ),
        ),
        (
            "wages_or_benefits_payment",
            ("salary", "wages", "honorarium", "nrega", "mgnrega", "not paid"),
        ),
        (
            "licence_or_compliance_filing",
            ("renew", "permit", "gst", "form 35", "annual return", "form 11", "roc"),
        ),
        (
            "copyright_or_ip_takedown",
            ("copyright", "trademark", "copied", "takedown", "infringement"),
        ),
        (
            "project_approval_or_compensation",
            ("gram sabha", "palli sabha", "noc", "land acquired", "rehabilitation"),
        ),
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
    accused_third_party = _has_any(
        q,
        (
            "the accused",
            "accused person",
            "main accused",
            "co accused",
            "co-accused",
            "he is accused",
            "she is accused",
            "saw accused",
            "witness saw accused",
        ),
    ) or ("accused" in q and not _is_user_accused_context(q))
    victim_or_witness_context = _has_any(
        q,
        (
            "threatening me",
            "threatens me",
            "harassing me",
            "intimidating me",
            "threatened me",
            "threatening",
            "harassing",
            "intimidating",
            "pressuring me",
            "pressurising me",
            "came to my house",
            "after bail",
            "got bail",
            "is on bail",
            "out on bail",
            "released on bail",
            "victim",
            "complainant",
            "witness",
            "statement",
            "not recording",
        ),
    )
    return accused_third_party and victim_or_witness_context and not _is_user_accused_context(q)


def _is_victim_bail_threat_context(q: str) -> bool:
    accused_bail = _has_any(
        q,
        (
            "accused got bail",
            "accused is on bail",
            "accused out on bail",
            "accused released on bail",
            "the accused got bail",
            "the accused is on bail",
            "after bail",
        ),
    )
    threat = _has_any(
        q,
        (
            "threatening me",
            "threatens me",
            "harassing me",
            "intimidating me",
            "threatened me",
            "threatening",
            "harassing",
            "intimidating",
            "pressuring me",
            "pressurising me",
            "came to my house",
        ),
    )
    return accused_bail and threat


def _is_victim_bail_opposition_context(q: str) -> bool:
    victim_side = _is_active_accusation_context(q) or _has_any(
        q,
        (
            "survivor",
            "victim",
            "complainant",
            "the accused",
            "accused person",
            "main accused",
            "co accused",
            "co-accused",
            "accused in my case",
            "threatening me",
            "threatened me",
            "harassing me",
            "intimidating me",
        ),
    )
    bail_opposition = _has_any(
        q,
        (
            "bail cancellation",
            "cancel bail",
            "cancel his bail",
            "cancel her bail",
            "cancellation of bail",
            "oppose bail",
            "opposing bail",
            "object to bail",
            "oppose anticipatory bail",
            "opposing anticipatory bail",
            "anticipatory bail of accused",
            "bail of accused",
        ),
    )
    bail_application = _has_any(
        q,
        (
            "bail application",
            "applying bail",
            "applying for bail",
            "applied for bail",
            "filed bail",
            "filed for bail",
            "filed bail application",
        ),
    )
    opposition_words = _has_any(q, ("oppose", "opposing", "object", "cancel", "cancellation"))
    bail_opposition = bail_opposition or (bail_application and (victim_side or opposition_words))
    return bail_opposition and victim_side and not _is_user_accused_context(q)


def _is_user_accused_context(q: str) -> bool:
    if _has_any(
        q,
        (
            "i am accused",
            "i was accused",
            "i got accused",
            "accused me",
            "made me accused",
            "false case against me",
            "case against me",
            "filed against me",
            "fir against me",
            "named me",
            "named in fir",
            "my son was accused",
            "my daughter was accused",
            "my husband was accused",
            "my wife was accused",
            "my brother was accused",
            "my father was accused",
            "my mother was accused",
        ),
    ):
        return True
    family_member = (
        "son",
        "daughter",
        "brother",
        "sister",
        "husband",
        "wife",
        "father",
        "mother",
        "parent",
        "uncle",
        "aunt",
        "cousin",
    )
    family_pattern = "|".join(re.escape(member) for member in family_member)
    return bool(
        re.search(r"\b(?:i|me|myself)\s+(?:am|was|have been|has been|got)\s+accused\b", q)
        or re.search(
            rf"\bmy\s+(?:{family_pattern})\s+(?:is|was|has been|have been|got)\s+accused\b", q
        )
        or re.search(rf"\bmy\s+(?:{family_pattern})\s+.*\baccused\s+(?:in|of|under|for)\b", q)
    )


def _is_active_accusation_context(q: str) -> bool:
    family_member = (
        "son",
        "daughter",
        "brother",
        "sister",
        "husband",
        "wife",
        "father",
        "mother",
        "parent",
        "uncle",
        "aunt",
        "cousin",
    )
    actor_pattern = (
        r"(?:i|my\s+(?:" + "|".join(re.escape(member) for member in family_member) + r"))"
    )
    object_pattern = (
        r"(?:him|her|them|neighbou?r|shopkeeper|company|builder|dealer|seller|"
        r"landlord|tenant|driver|doctor|hospital|police|contractor|employer|[a-z]+)"
    )
    return bool(re.search(rf"\b{actor_pattern}\s+accused\s+{object_pattern}\s+(?:of|for)\b", q))


def _secondary_issues(q: str, primary: str) -> list[str]:
    issues: list[str] = []
    if _has_any(q, ("hospital", "doctor", "wrong leg", "wrong surgery", "medical negligence")):
        issues.extend(
            ["consumer_compensation", "medical_negligence", "criminal_negligence_possible"]
        )
    if _has_any(
        q,
        (
            "bank",
            "hdfc",
            "sbi",
            "icici",
            "otp",
            "forex transaction",
            "unauthorized debit",
            "unauthorised debit",
        ),
    ):
        issues.extend(["banking_ombudsman", "consumer", "cyber_if_unauthorized_access"])
    # Keep multilabel planning on the same context-aware guard as the primary
    # router; bare "ICC" must not add a POSH issue to an unrelated query.
    posh_context = _is_workplace_sexual_harassment(q)
    retaliation_context = _has_any(
        q,
        (
            "pip",
            "performance improvement",
            "bad rating",
            "retaliation",
            "retaliate",
            "warning",
        ),
    ) and _has_any(
        q,
        (
            "manager",
            "boss",
            "hr",
            "company",
            "employer",
            "workplace",
            "office",
            "supervisor",
            "reporting manager",
        ),
    )
    if posh_context:
        issues.append("workplace_sexual_harassment")
        if retaliation_context:
            issues.append("employment_retaliation")
    elif retaliation_context and _has_any(
        q, ("complained", "complaint", "grievance", "harassment", "harass")
    ):
        issues.append("employment_retaliation")
    if _has_any(q, ("senior citizen", "maintenance tribunal", "son threw me", "old age")):
        issues.extend(["senior_maintenance", "property_or_welfare_support"])
    # Use word boundaries here: substring matching makes "parents" look like
    # "rent", which contaminated domestic-violence plans with tenancy issues.
    if any(
        _wordish_contains(q, term)
        for term in ("tenant", "tenants", "rent", "rents", "not vacating")
    ):
        issues.extend(["rent_arrears", "eviction_or_possession"])
    if _has_any(q, ("police not filing", "fir copy", "picked my son", "thana not")):
        issues.extend(["police_procedure", "senior_police_or_magistrate_escalation"])
    if _has_any(q, ("streedhan", "jewellery", "dowry")):
        issues.extend(["family_property", "domestic_violence_or_dowry_context"])
    if primary != "social_welfare_identity":
        certificate_context = _has_any(
            q,
            (
                "caste certificate", "caste cert", "sc certificate", "sc cert",
                "st certificate", "st cert", "scheduled caste certificate",
                "scheduled tribe certificate", "community certificate",
            ),
        )
        certificate_blockage = _has_any(
            q,
            (
                "rejected", "reject", "refused", "denied", "blocked", "pending",
                "delayed", "delay", "not issuing", "not issued", "not processing",
                "appeal", "tehsildar", "tahsildar", "deadline", "exam form",
            ),
        )
        if certificate_context and certificate_blockage:
            issues.append("caste_certificate_state_rule_intake")
    return [issue for issue in _dedupe(issues) if issue != primary]


def _authority_entry(
    source: str,
    position: int,
    *,
    act_override: str | None = None,
    section_override: str | None = None,
) -> AuthorityLedgerEntry:
    lower = source.lower()
    concrete_statute = bool(
        re.search(
            r"\b(?:act|code|rules|regulations|sanhita|adhiniyam)\s+"
            r"(?:of\s+)?(?:19|20)\d{2}\b",
            lower,
        )
    )
    conditional = bool(
        re.search(
            r"\b(?:where|if|when|only|based on|depending|as applicable)\b",
            lower,
        )
    ) or "family law statute" in lower or ("personal law" in lower and not concrete_statute)
    date_dependent_regime = not act_override and _is_date_dependent_regime_source(lower)
    intake_only = (
        lower.startswith("registration/allotment/agreement documents for proving")
        or lower.startswith("identity-record update rules")
        or lower.startswith("state rera rules and filing procedure")
        or lower.startswith("state labour-department notification/appeal route")
        or lower in {
            "exact offence section and consent/permission status before treating a criminal case as compoundable",
            "court permission and offence-compoundability limits must be checked from the exact section",
            "caste/tribal-status fact check before adding sc/st atrocity route",
            "labour/dlsa grievance route",
            "labour authority / esi court procedure for contesting contribution determinations",
            "medical board / appropriate authority procedure",
        }
        or "only as a separate criminal-negligence track where facts support it" in lower
    )
    if intake_only:
        conditional = True
    return AuthorityLedgerEntry(
        source=source,
        act=act_override or _extract_act_name(source),
        section=section_override if act_override else _extract_section(source),
        claim_type=_claim_type(source),
        priority=(
            "conditional"
            if intake_only
            else (
                "must_cite"
                if date_dependent_regime
                else ("conditional" if conditional and position > 0 else "must_cite")
            )
        ),
        must_cite=False if intake_only else (True if date_dependent_regime else (not conditional or position == 0)),
        conditional=conditional,
        note="date_dependent_regime_choose_by_incident_date"
        if date_dependent_regime
        else ("intake_precondition" if intake_only else "derived_from_route_required_sources"),
    )


def _plan_owner_authority_entries(
    owner: PlanOwnedAnswerRoute | None,
    retrieval_sources: list[RetrievalSourcePlan],
    route: MatterRoute,
    query: str,
) -> list[AuthorityLedgerEntry]:
    if owner is None:
        return []

    registry = load_authority_registry()
    workflow = registry.workflow_for_scenario(owner.scenario_id)
    if workflow is not None:
        if workflow.owner_token != owner.owner_token:
            raise ValueError(f"registry workflow owner mismatch for {owner.scenario_id}")
        entries: list[AuthorityLedgerEntry] = []
        for requirement in _active_registry_requirements(
            workflow,
            query,
            route.legal_regime,
        ):
            record = registry.by_key(requirement.registry_key)
            if record is None:
                raise ValueError(f"registry workflow authority missing: {requirement.registry_key}")
            provision_label = (
                "Section"
                if record.provision.kind in {"section", "paragraph"}
                else record.provision.kind.title()
            )
            candidates = [
                source
                for source in retrieval_sources
                if record.doc_id in source.doc_ids
                and any(
                    anchor in source.anchor_patterns
                    for anchor in record.provision.all_anchors
                )
            ]
            source = max(candidates, key=lambda item: item.priority) if candidates else None
            entries.append(
                AuthorityLedgerEntry(
                    source=(
                        f"{record.canonical_name} "
                        f"{record.provision.kind.title()} {record.provision.number}"
                    ),
                    authority_id=record.authority_id_expected,
                    registry_key=record.canonical_key,
                    identity_status="canonical",
                    canonical_name=_legal_name(record.canonical_name),
                    act=record.canonical_name,
                    section=f"{provision_label} {record.provision.number}",
                    source_pack_id=source.source_pack_id if source is not None else None,
                    required_anchor_patterns=list(record.provision.all_anchors),
                    claim_type=requirement.role,
                    priority=(
                        "must_cite"
                        if requirement.answer_must_cite is not False
                        else "background"
                    ),
                    must_cite=requirement.answer_must_cite is not False,
                    conditional=not requirement.required,
                    note="registry_workflow_authority",
                )
            )
        if owner.scenario_id == "vehicle_theft_fir_refusal":
            from .authority_graph import authority_graph_contract_offence_source_specs

            for spec in authority_graph_contract_offence_source_specs(
                owner.owner_contract_id,
                route,
            ):
                candidates = [
                    source
                    for source in retrieval_sources
                    if any(
                        title_term.lower() in title.lower()
                        for title_term in spec.title_terms
                        for title in source.title_patterns
                    )
                    and any(
                        anchor_term.lower() in source.anchor_patterns
                        for anchor_term in spec.anchor_terms
                    )
                ]
                source = max(candidates, key=lambda item: item.priority) if candidates else None
                if source is None:
                    continue
                section = next(
                    (
                        f"Section {anchor.removeprefix('/sec-')}"
                        for anchor in spec.anchor_terms
                        if anchor.startswith("/sec-")
                    ),
                    None,
                )
                entries.append(
                    AuthorityLedgerEntry(
                        source=source.title_patterns[0],
                        act=source.title_patterns[0],
                        section=section,
                        source_pack_id=source.source_pack_id,
                        required_anchor_patterns=list(spec.anchor_terms),
                        claim_type="legal_basis",
                        priority="must_cite",
                        must_cite=True,
                        conditional=False,
                        note="contract_offence_track",
                    )
                )
        return entries

    if owner.owner_provider == "authority_graph":
        from .authority_graph import authority_graph_contract_required_source_specs

        specs = tuple(
            (
                spec.title_terms,
                spec.anchor_terms,
                spec.source_pack_id,
                spec.document_ids,
            )
            for spec in authority_graph_contract_required_source_specs(
                owner.owner_contract_id,
                route,
                query=query,
            )
        )
    elif owner.owner_provider == "common_workflow_contracts":
        from .common_workflow_contracts import (
            common_workflow_contract_required_source_specs,
            common_workflow_contract_required_source_pack,
        )

        specs = tuple(
            (
                title_terms,
                anchor_terms,
                common_workflow_contract_required_source_pack(owner.owner_contract_id),
                (),
            )
            for title_terms, anchor_terms in common_workflow_contract_required_source_specs(
                owner.owner_contract_id
            )
        )
    else:
        raise ValueError(f"unknown plan answer owner provider: {owner.owner_provider}")

    entries: list[AuthorityLedgerEntry] = []
    required_document_ids_by_pack: dict[str, set[str]] = {}
    for _title_terms, _anchor_terms, source_pack_id, document_ids in specs:
        if source_pack_id and document_ids:
            required_document_ids_by_pack.setdefault(source_pack_id, set()).update(
                document_ids
            )

    for (
        raw_title_terms,
        raw_anchor_terms,
        required_source_pack,
        _required_document_ids,
    ) in specs:
        title_terms = tuple(_legal_name(term) for term in raw_title_terms)
        anchor_terms = tuple(anchor.lower() for anchor in raw_anchor_terms)
        selected_anchor_terms = anchor_terms
        selected_article: str | None = None
        if owner.owner_contract_id == "caste_certificate_state_rule_intake" and any(
            "constitution" in term for term in title_terms
        ):
            category = _certificate_category(query)
            if category == "st":
                selected_article = "342"
            elif category == "sc":
                selected_article = "341"
            if selected_article is not None:
                selected_anchor_terms = tuple(
                    anchor
                    for anchor in anchor_terms
                    if anchor in {f"/sec-{selected_article}", f"sec-{selected_article}"}
                ) or anchor_terms
        candidates = [
            source
            for source in retrieval_sources
            if any(
                term and any(term in _legal_name(title) for title in source.title_patterns)
                for term in title_terms
            )
            and (
                not selected_anchor_terms
                or any(anchor.lower() in selected_anchor_terms for anchor in source.anchor_patterns)
            )
            and (
                not required_source_pack
                or source.source_pack_id == required_source_pack
            )
        ]
        source = max(candidates, key=lambda item: item.priority) if candidates else None
        title = (
            source.title_patterns[0]
            if source is not None and source.title_patterns
            else raw_title_terms[0]
        )
        section = None
        if selected_article is not None:
            section = f"Article {selected_article}"
        elif len(selected_anchor_terms) == 1 and selected_anchor_terms[0].startswith("/sec-"):
            section_token = selected_anchor_terms[0].removeprefix("/sec-")
            # Retrieval anchors are intentionally lowercase, but user-facing
            # statutory labels preserve conventional suffix capitalization
            # (for example, section 139AA).
            section_token = re.sub(
                r"(?<=\d)([a-z]+)",
                lambda match: match.group(1).upper(),
                section_token,
            )
            section = f"Section {section_token}"
        elif owner.owner_contract_id == "vehicle_theft_fir_refusal":
            normalized_title = " ".join(raw_title_terms).lower()
            if "criminal procedure" in normalized_title and "/sec-154" in anchor_terms:
                section = "Section 154"
            elif "nagarik suraksha" in normalized_title:
                if "/sec-173-a" in anchor_terms:
                    section = "Section 173"
                elif "/sec-173-c" in anchor_terms:
                    section = "Section 173(4)"
                elif "/sec-175" in anchor_terms:
                    section = "Section 175"
        elif owner.owner_contract_id == "pan_aadhaar_linking_bank_kyc":
            section = "Section 139AA"
        elif (
            owner.owner_contract_id == "caste_certificate_state_rule_intake"
            and any("right to information" in term for term in title_terms)
            and "/sec-6" in selected_anchor_terms
        ):
            section = "Section 6"
        entries.append(
            AuthorityLedgerEntry(
                source=title,
                act=title,
                section=section,
                source_pack_id=(
                    required_source_pack
                    if required_source_pack
                    else source.source_pack_id if source is not None else None
                ),
                required_anchor_patterns=list(selected_anchor_terms),
                claim_type="legal_basis",
                priority="must_cite",
                must_cite=True,
                conditional=False,
                note="plan_owned_contract_required_source",
            )
        )
    return entries


def _authority_entries(
    q: str,
    route: MatterRoute,
    *,
    extra_sources: list[str] | None = None,
) -> list[AuthorityLedgerEntry]:
    entries: list[AuthorityLedgerEntry] = []
    retained_position = 0
    required_sources = _dedupe([*(route.required_sources or []), *(extra_sources or [])])
    source_families = {
        family
        for source in required_sources
        if (family := _criminal_source_regime_family(source)) is not None
    }
    has_separate_regime_requirements = {"current", "legacy"} <= source_families
    for source in required_sources:
        source_family = _criminal_source_regime_family(source)
        if has_separate_regime_requirements and not _source_family_matches_regime(
            source_family,
            route.legal_regime,
        ):
            continue
        position = retained_position
        retained_position += 1
        normalized_source = source
        lower = source.lower()
        if route.label == "Caste certificate rejection / appeal":
            if "article 341 / 342" in lower:
                category = _certificate_category(q)
                if category == "st":
                    normalized_source = "Constitution of India Article 342 for the relevant State-wise Scheduled Tribe list"
                elif category == "sc":
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
        selected_acts = _selected_criminal_regime_acts(
            normalized_source,
            route.legal_regime,
        )
        if selected_acts:
            entries.extend(
                _authority_entry(
                    normalized_source,
                    position,
                    act_override=act,
                    section_override=section,
                )
                for act in selected_acts
                for section in _selected_criminal_sections(normalized_source, act)
            )
        else:
            if _is_date_dependent_regime_source(normalized_source.lower()):
                entries.append(_authority_entry(normalized_source, position))
                continue
            act = _extract_act_name(normalized_source)
            sections = _extract_sections(normalized_source)
            entries.extend(
                _authority_entry(
                    normalized_source,
                    position,
                    act_override=act,
                    section_override=section,
                )
                for section in sections
            )
    return entries


def _criminal_source_regime_family(source: str) -> str | None:
    lower = source.lower()
    has_current = any(
        re.search(rf"(?<![a-z0-9]){token}(?![a-z0-9])", lower) for token in ("bns", "bnss", "bsa")
    )
    has_legacy = any(
        re.search(rf"(?<![a-z0-9]){re.escape(token)}(?![a-z0-9])", lower)
        for token in ("ipc", "crpc", "evidence act")
    )
    if has_current and has_legacy:
        return "mixed"
    if has_current:
        return "current"
    if has_legacy:
        return "legacy"
    return None


def _source_family_matches_regime(source_family: str | None, legal_regime: str | None) -> bool:
    if source_family in {None, "mixed"}:
        return True
    if legal_regime == "legacy_ipc_crpc_evidence_for_pre_2024_incident":
        return source_family == "legacy"
    if legal_regime == "current_bns_bnss_bsa_for_post_2024_incident":
        return source_family == "current"
    return True


_CRIMINAL_REGIME_ACTS = (
    ("bns", "Bharatiya Nyaya Sanhita 2023", "current"),
    ("bnss", "Bharatiya Nagarik Suraksha Sanhita 2023", "current"),
    ("bsa", "Bharatiya Sakshya Adhiniyam 2023", "current"),
    ("ipc", "Indian Penal Code 1860", "legacy"),
    ("crpc", "Code of Criminal Procedure 1973", "legacy"),
    ("evidence act", "Indian Evidence Act 1872", "legacy"),
)


def _selected_criminal_regime_acts(source: str, legal_regime: str | None) -> list[str]:
    if legal_regime == "legacy_ipc_crpc_evidence_for_pre_2024_incident":
        selected_regime = "legacy"
    elif legal_regime == "current_bns_bnss_bsa_for_post_2024_incident":
        selected_regime = "current"
    else:
        return []
    lower = source.lower()
    present_regimes = {
        regime
        for token, _, regime in _CRIMINAL_REGIME_ACTS
        if re.search(rf"(?<![a-z0-9]){re.escape(token)}(?![a-z0-9])", lower)
    }
    if present_regimes != {"current", "legacy"}:
        return []
    return _dedupe(
        [
            act
            for token, act, regime in _CRIMINAL_REGIME_ACTS
            if regime == selected_regime
            and re.search(rf"(?<![a-z0-9]){re.escape(token)}(?![a-z0-9])", lower)
        ]
    )


def _selected_criminal_sections(source: str, act: str) -> list[str | None]:
    token = {
        "Bharatiya Nyaya Sanhita 2023": "bns",
        "Bharatiya Nagarik Suraksha Sanhita 2023": "bnss",
        "Bharatiya Sakshya Adhiniyam 2023": "bsa",
        "Indian Penal Code 1860": "ipc",
        "Code of Criminal Procedure 1973": "crpc",
        "Indian Evidence Act 1872": "evidence act",
    }.get(act)
    if not token:
        return [None]
    match = re.search(
        rf"(?<![a-z0-9]){re.escape(token)}(?![a-z0-9])(?:\s+(?:18|19|20)\d{{2}})?\s+(?:sections?|sec\.?)\s+"
        r"([0-9][0-9a-z()./-]*(?:(?:\s*[,/&]\s*(?:(?:and|or)\s+)?|\s+(?:and|or)\s+)[0-9][0-9a-z()./-]*)*)",
        source,
        flags=re.IGNORECASE,
    )
    if not match:
        return [None]
    section_tokens = re.findall(
        r"[0-9][0-9a-z]*(?:\([0-9a-z]+\))*",
        match.group(1),
        flags=re.IGNORECASE,
    )
    return [f"Section {token}" for token in section_tokens if token]


def _is_date_dependent_regime_source(lower_source: str) -> bool:
    has_new_code = any(term in lower_source for term in ("bnss", "bns", "bsa"))
    has_old_code = any(term in lower_source for term in ("crpc", "ipc", "evidence act"))
    return has_new_code and has_old_code


def _extract_act_name(source: str) -> str | None:
    lower = source.lower()
    if "bocw act 1996" in lower and "factories act 1948" in lower:
        return None
    if _is_date_dependent_regime_source(lower):
        return "date-dependent criminal regime"
    acronym_acts = (
        ("bnss", "Bharatiya Nagarik Suraksha Sanhita 2023"),
        ("bns", "Bharatiya Nyaya Sanhita 2023"),
        ("bsa", "Bharatiya Sakshya Adhiniyam 2023"),
        ("crpc", "Code of Criminal Procedure 1973"),
        ("ipc", "Indian Penal Code 1860"),
        ("ibc", "Insolvency and Bankruptcy Code 2016"),
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
        r"\b[A-Z][A-Za-z&().,' -]+?(?:Act|Code|Rules|Regulations|Scheme|Guidelines|Sanhita|Adhiniyam)(?:\s+\d{4})?",
        r"\bConstitution(?: of India)?\b",
    )
    for pattern in patterns:
        match = re.search(pattern, source)
        if match:
            return re.sub(r"\s+", " ", match.group(0)).strip(" ,.")
    return None


def _extract_section(source: str) -> str | None:
    return _extract_sections(source)[0]


def _extract_sections(source: str) -> list[str | None]:
    sections: list[str] = []
    for match in re.finditer(
        r"\b(section|sec\.?|article|order)s?\s+"
        r"([0-9][0-9a-z()./-]*(?:(?:\s*[,/&]\s*(?:(?:and|or)\s+)?|\s+(?:and|or)\s+)[0-9][0-9a-z()./-]*)*)",
        source,
        flags=re.IGNORECASE,
    ):
        kind = match.group(1).lower().rstrip(".")
        label = "Article" if kind == "article" else "Order" if kind == "order" else "Section"
        tokens = re.findall(
            r"[0-9][0-9a-z]*(?:\([0-9a-z]+\))*",
            match.group(2),
            flags=re.IGNORECASE,
        )
        sections.extend(f"{label} {token}" for token in tokens if token)
    return _dedupe(sections) or [None]


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
    if incident_date_status in {
        "needed_for_criminal_regime",
        "incident_date_needed_for_bns_bnss_bsa_vs_ipc_crpc",
    }:
        flags.append("incident_date_needed")
    if jurisdiction.needs_state:
        flags.append("state_or_city_needed")
    if role == "unknown":
        flags.append("user_role_unclear")
    if _has_any(q, ("chargesheet", "charge sheet", "accused")) and route.category in {
        "cyber_fraud_or_harassment",
        "police_fir",
    }:
        flags.append("accused_framing_guard")
    return _dedupe(flags)


__all__ = [
    "AnswerPolicy",
    "AuthorityLedgerEntry",
    "JurisdictionPlan",
    "MatterPlan",
    "PLAN_OWNED_ANSWER_ROUTES",
    "PlanOwnedAnswerRoute",
    "PlanAnswerOwnershipResolution",
    "REVIEWED_CONTRACT_REQUIRED_CATEGORIES",
    "RetrievalSourcePlan",
    "authority_ids_for_passage",
    "build_matter_plan",
    "plan_owned_answer_route",
    "resolve_plan_answer_ownership",
]
