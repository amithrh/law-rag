"""Canonical legal matter plan shared by retrieval and answer policy."""
from __future__ import annotations

import hashlib
import json
import re
from dataclasses import asdict, dataclass, field, replace
from typing import Literal

from authority_registry import AuthorityRecord, load_authority_registry

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
    priority: float = 1.0


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


REVIEWED_CONTRACT_REQUIRED_CATEGORIES = frozenset({
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
})


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
        scenario_id="wrong_bank_debit",
        owner_provider="authority_graph",
        owner_contract_id="wrong_bank_debit",
    ),
    PlanOwnedAnswerRoute(
        scenario_id="insurance_claim_or_misselling",
        owner_provider="authority_graph",
        owner_contract_id="insurance_claim_or_misselling",
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
)

_SOURCE_PACK_ACRONYMS = frozenset({
    "bns", "bnss", "bsa", "crpc", "dpdp", "gst", "ibc", "ipc", "mmdr",
    "ndps", "pesa", "pmla", "posh", "pwdva", "rfctlarr", "rte", "rti",
})


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

    matches: list[PlanOwnedAnswerRoute] = []
    for rule in PLAN_OWNED_ANSWER_ROUTES:
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
                additional_owners=(
                    by_scenario["arrest_custody_station_case_not_disclosed"],
                ),
            )
        return PlanAnswerOwnershipResolution(
            conflicts=tuple(rule.owner_token for rule in matches),
        )
    return PlanAnswerOwnershipResolution(owner=matches[0] if matches else None)


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
    plan_owners = (
        (plan_owner, *ownership_resolution.additional_owners)
        if plan_owner is not None
        else ()
    )
    retrieval_sources = [
        RetrievalSourcePlan(
            source_pack_id=pack.id,
            title_patterns=list(pack.title_patterns),
            search_query=pack.search_query,
            doc_ids=list(pack.doc_ids),
            anchor_patterns=list(pack.anchor_patterns),
            source_types=list(pack.source_types),
            priority=pack.priority,
        )
        for pack in source_packs
    ]
    if plan_owner is not None:
        route_entries = _authority_entries(q, route)
        route_entries_by_act = {
            _legal_name(entry.act or ""): entry
            for entry in route_entries
            if entry.act
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
            )
        ]
        owner_acts = {_legal_name(entry.act or "") for entry in owner_entries}
        context_entries = [
            replace(
                entry,
                priority="background",
                must_cite=False,
                conditional=False,
                note="plan_owned_context_authority",
            )
            for entry in route_entries
            if _legal_name(entry.act or "") not in owner_acts
        ]
        raw_authority_entries = [*owner_entries, *context_entries]
    else:
        raw_authority_entries = _authority_entries(q, route)
    authority_ledger = _bind_authority_policy(
        raw_authority_entries,
        retrieval_sources,
    )
    safety_flags = _safety_flags(
        q,
        route=route,
        role=user_role,
        jurisdiction=jurisdiction,
        incident_date_status=incident_status,
    )
    action_pack = route.action_pack
    case_stage = _case_stage(q)
    desired_outcome = _desired_outcome(q, route)
    secondary_issues = _secondary_issues(q, route.category)
    forums = _dedupe(route.forums)
    documents = _dedupe(action_pack.documents if action_pack else [])
    next_steps = _dedupe(action_pack.next_steps if action_pack else [])
    portals = _dedupe(action_pack.portals if action_pack else [])
    escalation = _dedupe(action_pack.escalation if action_pack else [])
    cautions = _dedupe(action_pack.cautions if action_pack else [])
    requires_reviewed_contract = (
        plan_owner is not None
        or bool(ownership_resolution.conflicts)
        or route.category in REVIEWED_CONTRACT_REQUIRED_CATEGORIES
    )
    answer_policy = AnswerPolicy(
        required_primary_owner=(
            plan_owner.owner_token
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
        allow_freeform_llm=not requires_reviewed_contract,
        requires_reviewed_contract=requires_reviewed_contract,
        fallback_reason=(
            "multiple_plan_owners" if ownership_resolution.conflicts else None
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
            "incident_date_status": incident_status,
            "legal_regime": route.legal_regime,
            "case_stage": case_stage,
            "desired_outcome": desired_outcome,
            "urgency": route.urgency,
            "secondary_issues": secondary_issues,
            "required_facts": required_facts,
            "authority_ledger": [asdict(entry) for entry in authority_ledger],
            "retrieval_sources": [asdict(source) for source in retrieval_sources],
            "forums": forums,
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
        incident_date_status=incident_status,
        legal_regime=route.legal_regime,
        case_stage=case_stage,
        desired_outcome=desired_outcome,
        urgency=route.urgency,
        secondary_issues=secondary_issues,
        required_facts=required_facts,
        authority_ledger=authority_ledger,
        retrieval_sources=retrieval_sources,
        forums=forums,
        remedies=[],
        deadlines=[],
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
        anchors = sorted({
            _legal_name(anchor)
            for anchor in (required_anchor_patterns or entry.required_anchor_patterns)
            if anchor
        })
        scope = _legal_name(entry.section) if entry.section else "|".join(anchors) or "all"
        identity = "|".join((canonical_act, scope))
        status: Literal["canonical", "provisional"] = "canonical"
    else:
        identity = _normalize(entry.source)
        status = "provisional"
    digest = hashlib.sha256(identity.encode("utf-8")).hexdigest()[:20]
    prefix = "authority" if status == "canonical" else "authority_provisional"
    return f"{prefix}_{digest}", status


def _legal_name(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", (value or "").lower()).strip()


def _canonical_alias(act: str | None) -> str | None:
    aliases = {
        "bns": "bharatiya nyaya sanhita 2023",
        "bnss": "bharatiya nagarik suraksha sanhita 2023",
        "bsa": "bharatiya sakshya adhiniyam 2023",
        "constitution": "constitution of india",
        "constitution of india": "constitution of india",
        "crpc": "code of criminal procedure 1973",
        "ipc": "indian penal code 1860",
    }
    return aliases.get(_legal_name(act or ""))


def _canonical_act_from_sources(
    entry: AuthorityLedgerEntry,
    retrieval_sources: list[RetrievalSourcePlan],
) -> str | None:
    alias = _canonical_alias(entry.act)
    if alias:
        return alias
    if (
        entry.note == "plan_owned_contract_required_source"
        and entry.source_pack_id
    ):
        source = next(
            (
                item
                for item in retrieval_sources
                if item.source_pack_id == entry.source_pack_id
            ),
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
                act_name == title_name
                or act_name in title_name
                or title_name in act_name
            ):
                candidates.add(title_name)
                matched = True
        if matched:
            continue
        prefix = source.source_pack_id.lower().split("_", 1)[0]
        if prefix in _SOURCE_PACK_ACRONYMS and re.search(
            rf"(?<![a-z0-9]){re.escape(prefix)}(?![a-z0-9])",
            act_name,
        ) and source.title_patterns:
            candidates.add(_legal_name(source.title_patterns[0]))
    return next(iter(candidates)) if len(candidates) == 1 else None


def _bind_authority_policy(
    entries: list[AuthorityLedgerEntry],
    retrieval_sources: list[RetrievalSourcePlan],
) -> list[AuthorityLedgerEntry]:
    bound: list[AuthorityLedgerEntry] = []
    for entry in entries:
        source_pack_id = entry.source_pack_id or _matching_source_pack_id(
            entry,
            retrieval_sources,
        )
        canonical_act = _canonical_act_from_sources(entry, retrieval_sources)
        registry_record = _registry_record_for_entry(entry, canonical_act)
        if registry_record is not None:
            canonical_act = registry_record.canonical_name
            source_pack_id = registry_record.retrieval.source_pack_id
        matching_sources = _authority_retrieval_sources(
            entry,
            canonical_act=canonical_act,
            source_pack_id=source_pack_id,
            retrieval_sources=retrieval_sources,
        )
        if not matching_sources and entry.note == "date_dependent_regime_choose_by_incident_date":
            matching_sources = _date_dependent_retrieval_sources(entry, retrieval_sources)
        required_anchor_patterns = entry.required_anchor_patterns or _dedupe([
            anchor
            for source in matching_sources
            for anchor in source.anchor_patterns
            if anchor
        ])
        if (
            entry.note == "date_dependent_regime_choose_by_incident_date"
            and any(not source.anchor_patterns for source in matching_sources)
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
        bound.append(replace(
            entry,
            authority_id=authority_id,
            registry_key=registry_record.canonical_key if registry_record else None,
            identity_status=identity_status,
            canonical_name=canonical_act,
            source_pack_id=source_pack_id,
            required_anchor_patterns=required_anchor_patterns,
        ))
    return bound


def _registry_record_for_entry(
    entry: AuthorityLedgerEntry,
    canonical_act: str | None,
) -> AuthorityRecord | None:
    if not canonical_act or not entry.section:
        return None
    match = re.search(
        r"\b(section|article|rule|order|paragraph)\s+([0-9][0-9a-z()./-]*)",
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
    if source_pack_id:
        return [source for source in retrieval_sources if source.source_pack_id == source_pack_id]
    if not canonical_act:
        return []
    return [
        source
        for source in retrieval_sources
        if any(_legal_name(title) == canonical_act for title in source.title_patterns)
    ]


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
    section_text = _normalize(entry.section or "")
    section_match = re.search(r"\b(?:section|article|order)\s+([0-9][0-9a-z-]*)", section_text)
    section_token = section_match.group(1) if section_match else None
    specific_act = bool(_canonical_alias(entry.act)) or bool(
        re.search(r"\b(?:18|19|20)\d{2}\b", _normalize(entry.act or ""))
    )
    candidates: list[tuple[int, str]] = []
    for source in retrieval_sources:
        score = 0
        if specific_act and any(
            _legal_name(title) == _legal_name(entry.act or "")
            or _legal_name(title) in _legal_name(entry.act or "")
            or _legal_name(entry.act or "") in _legal_name(title)
            for title in source.title_patterns
            if title
        ):
            score += 100

        prefix = source.source_pack_id.lower().split("_", 1)[0]
        if prefix in _SOURCE_PACK_ACRONYMS and re.search(
            rf"(?<![a-z0-9]){re.escape(prefix)}(?![a-z0-9])",
            act_text,
        ):
            score += 60

        if score and section_token and any(
            re.search(rf"(?:sec|article|order)[-_/]?{re.escape(section_token)}(?:\D|$)", anchor.lower())
            for anchor in source.anchor_patterns
        ):
            score += 40

        if score:
            candidates.append((score, source.source_pack_id))

    if not candidates:
        return None
    candidates.sort(reverse=True)
    if len(candidates) > 1 and candidates[0][0] == candidates[1][0]:
        return None
    return candidates[0][1]


def authority_ids_for_passage(
    plan: MatterPlan,
    *,
    title: str,
    anchor: str,
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
        if entry.canonical_name:
            allowed_titles.add(entry.canonical_name)
        source_pack_matches = bool(
            source_pack_id
            and matching_sources
            and any(
                source.source_pack_id == source_pack_id
                for source in matching_sources
            )
        )
        title_matches = title_name in allowed_titles or (
            source_pack_matches
            and any(
                allowed_title and allowed_title in title_name
                for allowed_title in allowed_titles
            )
        )
        if not title_name or not title_matches:
            continue
        if source_pack_id and matching_sources and all(
            source.source_pack_id != source_pack_id for source in matching_sources
        ):
            continue
        if matching_sources and (
            not source_type
            or all(source_type not in source.source_types for source in matching_sources)
        ):
            continue
        if entry.section and not _passage_anchor_matches_section(anchor_lower, entry.section):
            continue
        if (
            not entry.section
            and entry.required_anchor_patterns
            and not _passage_anchor_matches_patterns(anchor_lower, entry.required_anchor_patterns)
        ):
            continue
        matched.append(entry.authority_id)
    return _dedupe(matched)


def _passage_anchor_matches_section(anchor: str, section: str) -> bool:
    match = re.search(
        r"\b(?:section|sec\.?|article|order)\s+([0-9][0-9a-z()./-]*)",
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
    return anchor_token == token or anchor_token.replace("-", "") == token.replace("-", "") or (
        "-" in token and anchor_token == token.split("-", 1)[0]
    )


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


def _authority_entry(
    source: str,
    position: int,
    *,
    act_override: str | None = None,
    section_override: str | None = None,
) -> AuthorityLedgerEntry:
    lower = source.lower()
    conditional = "where" in lower or "if " in lower or "based on" in lower or "depending" in lower
    date_dependent_regime = not act_override and _is_date_dependent_regime_source(lower)
    return AuthorityLedgerEntry(
        source=source,
        act=act_override or _extract_act_name(source),
        section=section_override if act_override else _extract_section(source),
        claim_type=_claim_type(source),
        priority="must_cite" if date_dependent_regime else (
            "conditional" if conditional and position > 0 else "must_cite"
        ),
        must_cite=True if date_dependent_regime else (not conditional or position == 0),
        conditional=conditional,
        note="date_dependent_regime_choose_by_incident_date" if date_dependent_regime else "derived_from_route_required_sources",
    )


def _plan_owner_authority_entries(
    owner: PlanOwnedAnswerRoute | None,
    retrieval_sources: list[RetrievalSourcePlan],
    route: MatterRoute,
) -> list[AuthorityLedgerEntry]:
    if owner is None:
        return []

    if owner.owner_provider == "authority_graph":
        from .authority_graph import authority_graph_contract_required_source_specs

        specs = tuple(
            (spec.title_terms, spec.anchor_terms)
            for spec in authority_graph_contract_required_source_specs(
                owner.owner_contract_id,
                route,
            )
        )
    elif owner.owner_provider == "common_workflow_contracts":
        from .common_workflow_contracts import (
            common_workflow_contract_required_source_specs,
        )

        specs = common_workflow_contract_required_source_specs(
            owner.owner_contract_id
        )
    else:
        raise ValueError(f"unknown plan answer owner provider: {owner.owner_provider}")

    entries: list[AuthorityLedgerEntry] = []
    for raw_title_terms, raw_anchor_terms in specs:
        title_terms = tuple(_legal_name(term) for term in raw_title_terms)
        anchor_terms = tuple(anchor.lower() for anchor in raw_anchor_terms)
        candidates = [
            source
            for source in retrieval_sources
            if any(
                term and any(term in _legal_name(title) for title in source.title_patterns)
                for term in title_terms
            )
            and (
                not anchor_terms
                or any(
                    anchor.lower() in anchor_terms
                    for anchor in source.anchor_patterns
                )
            )
        ]
        source = max(candidates, key=lambda item: item.priority) if candidates else None
        title = (
            source.title_patterns[0]
            if source is not None and source.title_patterns
            else raw_title_terms[0]
        )
        entries.append(AuthorityLedgerEntry(
            source=title,
            act=title,
            section=None,
            source_pack_id=source.source_pack_id if source is not None else None,
            required_anchor_patterns=list(raw_anchor_terms),
            claim_type="legal_basis",
            priority="must_cite",
            must_cite=True,
            conditional=False,
            note="plan_owned_contract_required_source",
        ))
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
        re.search(rf"(?<![a-z0-9]){token}(?![a-z0-9])", lower)
        for token in ("bns", "bnss", "bsa")
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
    return _dedupe([
        act
        for token, act, regime in _CRIMINAL_REGIME_ACTS
        if regime == selected_regime
        and re.search(rf"(?<![a-z0-9]){re.escape(token)}(?![a-z0-9])", lower)
    ])


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
    if _is_date_dependent_regime_source(lower):
        return "date-dependent criminal regime"
    acronym_acts = (
        ("bnss", "Bharatiya Nagarik Suraksha Sanhita 2023"),
        ("bns", "Bharatiya Nyaya Sanhita 2023"),
        ("bsa", "Bharatiya Sakshya Adhiniyam 2023"),
        ("crpc", "Code of Criminal Procedure 1973"),
        ("ipc", "Indian Penal Code 1860"),
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
