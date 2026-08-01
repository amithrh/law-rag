"""User-visible source-gap helpers for the answer API.

The eval stack can diagnose missing route-required authority after the fact.
This module exposes the same product idea at runtime: if a route says a
controlling source is required but the answer source window does not contain
it, the API can tell the user instead of quietly letting a neighboring source
stand in for it.
"""
from __future__ import annotations

import re
from datetime import date
from typing import Any

from authority_registry import load_authority_registry

from apps.api.legal_issue_plan import (
    MatterPlan,
    _SOURCE_PACK_ACRONYM_ALIASES,
    _is_mgnrega_integrity_composite_requirement,
    _passage_heading_matches_exact_section,
    _passage_heading_matches_section,
    authority_ids_for_passage,
)
from apps.api.customs_logic import (
    customs_assessment_issue,
    customs_classification_issue,
    customs_drawback_issue,
    customs_misdeclaration_issue,
    customs_svb_issue,
)
from apps.api.local_authority import (
    has_explicit_municipal_authority_context,
    has_qualified_city_corporation,
    has_private_business_actor_context,
    has_private_vendor_actor_context,
    has_specific_hawker_corporation_context,
)
from apps.api.incident_facts import (
    is_acid_attempt_query,
    is_acid_threat_only_query,
    is_completed_acid_attack_query,
    is_positive_acid_chemical_context,
)


_STOPWORDS = {
    "a", "an", "and", "as", "based", "be", "for", "in", "is", "of", "on",
    "or", "procedure", "relevant", "route", "section", "sections", "source",
    "sources", "state", "the", "to", "where", "with",
}


def _passage_identity_text(passage: dict[str, Any]) -> str:
    """Use full text internally, or the server-emitted heading in evals."""
    return str(passage.get("text") or passage.get("heading") or "")


def _source_pack_title_matches(
    passage_title: object,
    title_patterns: object,
    *,
    allow_known_document_suffix: bool = False,
) -> bool:
    """Match a reviewed title without rejecting its corpus display suffix.

    India Code documents are often titled with a parenthetical edition marker
    such as ``(with 2005 amendment)``. The document id and source type are
    checked by the caller first, so a suffix is safe only when the pack has a
    known document identity. Packs without document ids retain exact-title
    matching and cannot use a title suffix as provenance.
    """
    raw_actual = re.sub(r"\s+", " ", str(passage_title or "").lower()).strip()
    for pattern in title_patterns or ():
        raw_expected = re.sub(r"\s+", " ", str(pattern or "").lower()).strip()
        actual = re.sub(r"[^a-z0-9]+", " ", raw_actual).strip()
        expected = re.sub(r"[^a-z0-9]+", " ", raw_expected).strip()
        if not expected:
            continue
        if actual == expected:
            return True
        if allow_known_document_suffix and actual.startswith(f"{expected} "):
            suffix_match = re.match(
                rf"^{re.escape(raw_expected)}\s+(\([^()\n]{{1,160}}\))$",
                raw_actual,
            )
            if suffix_match:
                return True
    return False


_FAMILY_PERSONAL_LAW_TRIGGER_TERMS = (
    "matrimonial", "annulment", "annul", "void marriage",
    "voidable", "divorce", "separation", "restitution", "conjugal",
    "second wife", "second husband", "second marriage", "bigamy", "maintenance",
    "alimony", "streedhan", "stridhan", "custody", "child custody",
    "guardianship", "personal law", "hindu marriage", "special marriage",
    "muslim marriage", "before marriage", "lied before marriage",
)

_MAINTENANCE_TRIGGER_TERMS = (
    "maintenance", "alimony", "child support", "interim maintenance",
    "monthly support", "support order", "section 125", "sec 125",
    "125 crpc", "144 bnss", "not paying maintenance", "maintenance case",
)

_CRIMINAL_PROCESS_TRIGGER_TERMS = (
    "fir", "f.i.r", "arrest", "arrested", "detain", "detained",
    "custody", "lockup", "lock-up", "picked", "station",
    "police station", "police notice", "police called", "police calling",
    "police came", "police visit", "police asked", "police took",
    "police picked", "police arrested", "police refusing",
    "police refused", "police not filing", "police filed",
    "police case", "police complaint",
    "bail", "anticipatory", "regular bail", "interim bail",
    "default bail", "surety", "remand", "chargesheet", "charge sheet",
    "notice", "summons", "warrant", "magistrate", "complaint",
    "criminal court", "accused", "case against me", "case on me",
)

_CRIMINAL_OFFENCE_TRIGGER_TERMS = (
    "acid", "assault", "attack", "beat", "beaten", "blackmail",
    "cheating", "cruelty", "dacoity", "dowry", "extortion", "forgery",
    "forged", "fraud", "harass", "harassment", "hurt", "intimidation",
    "kidnap", "murder", "ndps", "pocso", "rape", "sexual assault",
    "stalk", "stalking", "threat", "threaten", "threatening", "theft",
    "stolen", "trafficking", "uapa", "violence", "witch", "wrongful",
    "confine", "confinement", "locked", "not letting leave", "forced",
    "fake register", "false register", "fake case", "false fir",
    "blank paper", "thumb impression", "false document", "fake document",
    "drug parcel", "drug dealer", "mdma", "ganja", "charas", "cocaine",
    "heroin", "narcotic", "contraband", "psychotropic",
)

_GENERAL_CRIMINAL_OFFENCE_TRIGGER_TERMS = tuple(
    term for term in _CRIMINAL_OFFENCE_TRIGGER_TERMS
    if term not in {"ndps", "uapa", "pocso"}
)

_PHYSICAL_STALKING_THREAT_TRIGGER_TERMS = (
    "assault", "attack", "beat", "beaten", "hit", "hurt", "injury",
    "injured", "slap", "slapped", "touch", "touched", "grop", "molest",
    "stalk", "stalking", "follow", "following", "threat", "threaten",
    "threatening", "intimidat", "force", "forced", "coercion", "confine",
    "locked", "not letting", "acid", "knife", "weapon",
)

_LIMITATION_TRIGGER_TERMS = (
    "delay", "delayed", "late", "limitation", "time limit", "deadline",
    "appeal period", "appeal deadline", "after 30 days", "after 60 days",
    "after 90 days", "after 120 days", "condonation", "time barred",
    "time-barred", "years back", "months late", "execution delay",
)

_PESA_TRIGGER_TERMS = (
    "pesa", "gram sabha", "scheduled area", "fifth schedule",
    "tribal village", "mining", "bauxite", "displacement", "noc",
    "land acquisition", "rehabilitation",
)

_FRA_TRIGGER_TERMS = (
    "forest", "forest right", "forest rights", "fra", "ifr", "cfr",
    "patta", "tendu", "bamboo", "minor forest produce", "mfp",
    "forest guard", "van adhikar",
)

def _has_adoption_source_context(q: str) -> bool:
    return (
        _has(q, ("adoption", "adopted", "adoptive", "cara", "relative adoption"))
        or re.search(r"(?<![a-z0-9])adopt(?:s|ing|er|ers)?(?![a-z0-9])", q) is not None
    )


def _has_criminal_process_context(q: str) -> bool:
    return _has_trigger_term(q, _CRIMINAL_PROCESS_TRIGGER_TERMS)


def _has_criminal_offence_context(q: str) -> bool:
    if _has(q, _GENERAL_CRIMINAL_OFFENCE_TRIGGER_TERMS):
        return True
    return (
        re.search(r"\b(?:sec(?:tion)?\.?\s*)\d{2,3}[a-z]?\b", q) is not None
        and _has(q, ("bns", "ipc"))
    ) or re.search(r"\b(?:bns|ipc)\s*\d{2,3}[a-z]?\b|\b\d{2,3}[a-z]?\s*(?:bns|ipc)\b", q) is not None


def _has_streedhan_or_entrustment_context(q: str) -> bool:
    return _has(q, (
        "streedhan", "stridhan", "jewellery", "jewelry", "gold",
        "wedding jewellery", "wedding jewelry", "in laws not returning",
        "in-laws not returning", "not returning my jewellery",
        "not returning my jewelry", "not returning my gold",
        "refusing to return", "refused to return", "kept my jewellery",
        "kept my jewelry", "entrusted jewellery", "entrusted jewelry",
    ))


def _has_trafficking_exploitation_context(q: str) -> bool:
    return _has(q, (
        "trafficking", "exploitation", "sex work", "sex worker",
        "brothel", "spa raid", "spa was raided", "spa raided",
        "massage parlour", "massage parlor", "massage centre",
        "massage center", "massage girls", "police took me and other girls",
        "girls to station", "women to station", "rescued from spa",
        "itpa raid", "raid at spa", "raided last week",
        "customers want extra", "owner makes us", "if we refuse no salary",
        "forced sexual exploitation",
    ))


def _has_police_threatening_arrest_without_offence_context(q: str) -> bool:
    police_threat = _has(q, (
        "police still threatening to arrest",
        "police threatening to arrest",
        "police threatened arrest",
        "threatening to arrest",
    ))
    bail_order = _has(q, (
        "anticipatory bail granted", "bail granted", "granted bail",
        "bail order", "high court granted bail", "hc granted bail",
    ))
    explicit_offence = _has(q, (
        "rape", "murder", "theft", "stolen", "cheating", "fraud",
        "forgery", "dowry", "cruelty", "assault", "hit", "beat",
        "ndps", "pocso", "uapa", "extortion", "blackmail",
        "section ", "sec ", "bns ", "ipc ",
    ))
    return police_threat and bail_order and not explicit_offence


def _has_physical_stalking_threat_context(q: str) -> bool:
    if _has_negated_family_criminal_force_context(q):
        return False
    return _has(q, _PHYSICAL_STALKING_THREAT_TRIGGER_TERMS)


def _has_limitation_trigger_context(q: str) -> bool:
    return _has(q, _LIMITATION_TRIGGER_TERMS) or re.search(r"\b\d+\s+(?:year|years|month|months|day|days)\s+(?:late|delay|after)\b", q) is not None


def _has_pesa_trigger_context(q: str) -> bool:
    non_scheduled = _has(q, ("non scheduled", "non-scheduled"))
    return _has(q, _PESA_TRIGGER_TERMS) and not non_scheduled


def _has_fra_trigger_context(q: str) -> bool:
    return _has(q, _FRA_TRIGGER_TERMS)


def _is_housing_pet_query(query: str) -> bool:
    q = str(query or "").lower()
    housing = _has(q, (
        "society management", "housing society", "apartment association",
        "rwa", "cooperative society", "co-operative society",
    ))
    pet = re.search(r"\b(?:pet|pets|dog|dogs|cat|cats)\b", q) is not None
    fine = _has(q, ("fine", "penalty", "approval", "prior approval"))
    return housing and pet and fine


_HOUSING_PET_REVIEWED_PACKS = frozenset({
    "bmc_pet_guidelines_ban",
    "bmc_pet_guidelines_bylaws",
    "bmc_pet_guidelines_license",
})
_BMC_PET_DOCUMENT_ID = "bmc-pet-dog-guidelines"
_BMC_PET_ANCHOR_PREFIX = "bmc-pet-dog-guidelines#"
_NON_BMC_LOCATION_TERMS = (
    "delhi", "new delhi", "kolkata", "calcutta", "chennai", "madras",
    "bengaluru", "bangalore", "hyderabad", "pune", "ahmedabad", "surat",
    "jaipur", "lucknow", "patna", "ranchi", "gujarat", "delhi ncr",
    "karnataka", "tamil nadu", "telangana", "west bengal", "rajasthan",
    "uttar pradesh", "bihar", "jharkhand", "kerala", "assam", "odisha",
    "orissa", "punjab", "haryana", "madhya pradesh", "chhattisgarh",
)


def _bmc_pet_query_is_jurisdiction_compatible(query: str) -> bool:
    q = str(query or "").lower()
    if _has(q, ("mumbai", "bombay", "bmc", "maharashtra")):
        return True
    return not _has(q, _NON_BMC_LOCATION_TERMS)


def has_housing_pet_authority(
    passages: list[dict[str, Any]],
    *,
    query: str = "",
) -> bool:
    """Return whether reviewed, jurisdiction-compatible pet authority exists.

    Cooperative judgments are contextual and cannot satisfy this gate. The
    exact source-pack/document/anchor tuple prevents a title-only or forged
    metadata match from unlocking an operative pet-law answer.
    """
    for passage in passages:
        if not isinstance(passage, dict):
            continue
        pack = str(passage.get("required_source_pack") or "").strip().lower()
        title = str(passage.get("title") or "").lower()
        anchor = str(passage.get("anchor") or "").strip().lower()
        if (
            pack in _HOUSING_PET_REVIEWED_PACKS
            and str(passage.get("document_id") or "").strip() == _BMC_PET_DOCUMENT_ID
            and str(passage.get("source_type") or "").strip().lower() == "circular"
            and anchor.startswith(_BMC_PET_ANCHOR_PREFIX)
            and "bmc" in title
            and _bmc_pet_query_is_jurisdiction_compatible(query)
        ):
            return True
    return False


def canonical_source_gap_handoff(
    source_gap_event: dict[str, Any] | None,
    *,
    route_category: str,
    reason: str,
) -> dict[str, Any]:
    """Return the single safe schema used for every user-visible source gap."""
    # ``None`` is the intentional no-payload sentinel for callers that need
    # to construct a safe handoff from a known runtime condition such as a
    # reranker outage. Any supplied object, however, must satisfy the schema.
    payload_valid = source_gap_event is None or _is_valid_source_gap_payload(source_gap_event)
    raw = source_gap_event if isinstance(source_gap_event, dict) and payload_valid else {}
    if source_gap_event is not None and not payload_valid:
        # A malformed internal signal must remain observable in diagnostics;
        # treating it as an ordinary coverage gap hides a contract breach.
        reason = "invalid_source_gap_payload"
    gap_kinds = [
        item.strip()
        for item in raw.get("gap_kinds", [])
        if isinstance(item, str) and item.strip()
    ][:8]
    if not gap_kinds:
        gap_kinds = ["retrieval_coverage_gap"]
    missing_required_sources = []
    for item in raw.get("missing_required_sources", []):
        if not isinstance(item, dict):
            continue
        required_source = item.get("required_source")
        kind = item.get("kind")
        if isinstance(required_source, str) and required_source.strip():
            normalized = {
                "required_source": required_source.strip(),
                "kind": kind.strip() if isinstance(kind, str) and kind.strip() else "missing",
            }
            for field in ("authority_id", "source_pack_id", "identity_status", "match_mode"):
                value = item.get(field)
                if isinstance(value, str) and value.strip():
                    normalized[field] = value.strip()
            anchors = item.get("required_anchor_patterns")
            if isinstance(anchors, list):
                normalized["required_anchor_patterns"] = [
                    value.strip()
                    for value in anchors[:8]
                    if isinstance(value, str) and value.strip()
                ]
            missing_required_sources.append(normalized)
    policy = raw.get("policy")
    if policy not in {
        "do_not_substitute_neighboring_authority",
        "separate_conflicting_answer_owners",
    }:
        policy = "do_not_substitute_neighboring_authority"
    return {
        "has_gap": True,
        "route_category": route_category,
        "gap_kinds": gap_kinds,
        "missing_required_sources": missing_required_sources,
        "message": (
            "The required source coverage for this question could not be verified. "
            "I will not substitute a neighboring law or judgment."
        ),
        "handoff": "DLSA/legal aid or a qualified lawyer",
        "policy": policy,
        "outcome": "source_gap_handoff",
        "reason": reason,
        "safe_handoff_only": True,
    }


def _is_valid_source_gap_payload(payload: Any) -> bool:
    """Validate the internal source-gap boundary before canonicalization.

    Canonicalization intentionally strips untrusted fields, but it must not
    erase the fact that an internal producer violated the contract. A valid
    source-gap signal carries an explicit boolean marker and at least one
    complete diagnostic: either a gap kind or a concrete required-source
    record. The caller may already have decided to hand off even when an
    upstream producer supplied ``has_gap=False``; canonicalization still
    forces a safe handoff in that case.
    """
    if not isinstance(payload, dict) or not isinstance(payload.get("has_gap"), bool):
        return False
    gap_kinds = payload.get("gap_kinds", [])
    if not isinstance(gap_kinds, list):
        return False
    if any(not isinstance(kind, str) or not kind.strip() for kind in gap_kinds):
        return False
    has_gap_kind_diagnostics = bool(gap_kinds)
    has_missing_source_diagnostics = False
    if "missing_required_sources" in payload:
        missing = payload["missing_required_sources"]
        if not isinstance(missing, list):
            return False
        for item in missing:
            if not isinstance(item, dict):
                return False
            if not isinstance(item.get("required_source"), str) or not item["required_source"].strip():
                return False
            if "kind" in item and (not isinstance(item["kind"], str) or not item["kind"].strip()):
                return False
            if "required_anchor_patterns" in item:
                anchors = item["required_anchor_patterns"]
                if not isinstance(anchors, list):
                    return False
                if any(not isinstance(anchor, str) or not anchor.strip() for anchor in anchors):
                    return False
        has_missing_source_diagnostics = bool(missing)
    if not (has_gap_kind_diagnostics or has_missing_source_diagnostics):
        return False
    for field in ("route_category", "policy", "reason"):
        if field in payload and not isinstance(payload[field], str):
            return False
    return True


def _constitution_article_numbers(source: str) -> set[str]:
    lower = str(source or "").lower()
    numbers: set[str] = set()
    for match in re.finditer(
        r"\barticles?\s+[0-9]+[a-z]?"
        r"(?:\s*(?:,|and|&|/)\s*(?:and\s+)?[0-9]+[a-z]?)*\b",
        lower,
    ):
        numbers.update(re.findall(r"[0-9]+[a-z]?", match.group(0)))
    return numbers


def _is_split_constitutional_descriptor(
    source: str,
    *,
    source_pack_id: str | None = None,
) -> bool:
    lower = str(source or "").lower()
    return len(_constitution_article_numbers(lower)) > 1 and (
        bool(re.search(r"\bconstitut(?:ion|ional)\b", lower))
        or bool(source_pack_id and source_pack_id.startswith("constitution_"))
    )


def _is_deferred_date_regime_entry(plan: MatterPlan, entry: Any) -> bool:
    return (
        _plan_field(entry, "note") == "date_dependent_regime_choose_by_incident_date"
        and _plan_field(plan, "incident_date_status") in {
            "needed_for_criminal_regime",
            "incident_date_needed_for_bns_bnss_bsa_vs_ipc_crpc",
        }
        and _date_dependent_regime_packs_ready(
            str(_plan_field(entry, "source", "") or ""),
            _plan_field(plan, "retrieval_sources", ()) or (),
        )
    )


def matter_plan_integrity_gap(
    plan: MatterPlan | None,
    query: str,
) -> dict[str, Any] | None:
    """Reject plans that cannot prove where an operative authority comes from.

    A ledger entry is not evidence by itself. Every enforceable entry must be
    bound to a named source pack with document identity, source type, and any
    required provision anchors. This check runs before the answer layer so a
    generic template or LLM cannot turn an incomplete plan into advice.
    """
    if plan is None or plan.answer_policy.fallback_reason == "multiple_plan_owners":
        return None

    if not plan.authority_ledger:
        return {
            "has_gap": True,
            "gap_kinds": ["empty_authority_ledger"],
            "missing_required_sources": [{
                "required_source": plan.primary_label or plan.primary_issue,
                "kind": "empty_authority_ledger",
                "match_mode": "matter_plan_integrity",
            }],
            "message": "The matter plan has no authority obligations.",
            "handoff": "DLSA/legal aid or a qualified lawyer",
            "policy": "do_not_substitute_neighboring_authority",
        }

    active_entries = []
    for entry in plan.authority_ledger:
        if not is_active_plan_authority_entry(entry, plan=plan, query=query):
            continue
        active_entries.append(entry)

    if not active_entries:
        # A plan may legitimately contain only facts, documents, local route
        # guidance, or a date-dependent regime wrapper. Later source-gap and
        # reviewed-workflow gates still decide whether an answer is safe.
        return None

    packs = {source.source_pack_id: source for source in plan.retrieval_sources}
    missing: list[dict[str, Any]] = []
    for entry in active_entries:
        # A combined constitutional descriptor can be satisfied by multiple
        # exact Constitution packs (for example Article 21 plus Article 22).
        # It must be checked against retrieved passages, not forced into one
        # source-pack identity at plan-build time.
        if entry.source_pack_id is None and _is_split_constitutional_descriptor(
            entry.source,
            source_pack_id=entry.source_pack_id,
        ):
            continue
        if (
            entry.source_pack_id is None
            and "prevention of corruption" in str(entry.source or "").lower()
            and "bns" in str(entry.source or "").lower()
        ):
            # This route obligation is deliberately either/or. Its reviewed
            # PCA/BNS pack identity is checked against the retrieved passages
            # by missing_plan_authorities below rather than guessed at plan
            # construction time.
            continue
        # An unknown criminal incident date intentionally keeps both regime
        # candidates in the retrieval plan. The entry is a composite
        # obligation, so it has no single source_pack_id by design. Require
        # both reviewed packs here, then let missing_plan_authorities enforce
        # the date-sensitive evidence gate against the retrieved passages.
        if _is_deferred_date_regime_entry(plan, entry):
            continue
        pack = packs.get(entry.source_pack_id) if entry.source_pack_id else None
        failure: str | None = None
        if pack is None:
            failure = "missing_source_pack_binding"
        elif not pack.doc_ids:
            failure = "missing_document_identity"
        elif not pack.source_types:
            failure = "missing_source_type_binding"
        elif entry.required_anchor_patterns and not any(
            _source_pack_anchor_matches(str(anchor), str(pattern))
            for pattern in entry.required_anchor_patterns
            for anchor in pack.anchor_patterns
        ):
            failure = "missing_required_anchor_binding"
        elif entry.registry_key and entry.authority_id not in pack.authority_ids:
            failure = "missing_registry_authority_binding"
        if failure:
            missing.append({
                "required_source": entry.source,
                "authority_id": entry.authority_id,
                "source_pack_id": entry.source_pack_id,
                "identity_status": entry.identity_status,
                "required_anchor_patterns": list(entry.required_anchor_patterns),
                "kind": failure,
                "match_mode": "matter_plan_integrity",
            })

    if not missing:
        return None
    return {
        "has_gap": True,
        "gap_kinds": sorted({str(item["kind"]) for item in missing}),
        "missing_required_sources": missing,
        "message": "One or more enforceable authorities are not bound to exact retrievable source evidence.",
        "handoff": "DLSA/legal aid or a qualified lawyer",
        "policy": "do_not_substitute_neighboring_authority",
    }


def _incident_authority_passage_matches(
    passage: dict[str, Any],
    *,
    title_terms: tuple[str, ...],
    section_terms: tuple[str, ...],
    source_pack_terms: tuple[str, ...],
    document_ids: tuple[str, ...],
) -> bool:
    """Match an incident authority only with complete reviewed provenance.

    Incident safety gates cannot infer that a neighboring chunk is the right
    statute.  Production passages carry a numeric database document id and a
    canonical anchor; fixtures may use the canonical document slug instead.
    Both forms are accepted, but an absent or clearly wrong identity is not.
    """
    title = str(passage.get("title") or "").lower()
    if not any(term in title for term in title_terms):
        return False
    source_type = str(passage.get("source_type") or "").strip().lower()
    if source_type != "bare_act":
        return False
    source_pack = str(
        passage.get("required_source_pack")
        or passage.get("_required_source_pack")
        or ""
    ).strip().lower()
    if not source_pack or source_pack not in source_pack_terms:
        return False
    raw_document_id = passage.get("document_id")
    if raw_document_id is None or not str(raw_document_id).strip():
        return False
    anchor = str(passage.get("anchor") or "").strip().lower()
    expected_documents = {str(item).strip().lower() for item in document_ids if item}
    if not expected_documents:
        return False
    anchor_document = anchor.split("/", 1)[0]
    if anchor_document not in expected_documents:
        return False
    document_id = str(raw_document_id).strip().lower()
    # Retrieved rows expose an integer DB id. Unit/eval fixtures sometimes
    # expose the stable document slug; reject non-numeric foreign identities.
    if document_id not in expected_documents:
        return False
    text = _passage_identity_text(passage)
    blob = " ".join(
        str(passage.get(field) or "").lower()
        for field in ("anchor", "heading", "required_source_pack")
    )
    return any(
        _section_anchor_matches(blob, section, passage_text=text)
        for section in section_terms
    )


def _missing_acid_chemical_authorities(
    *,
    query: str,
    route_category: str,
    passages: list[dict[str, Any]],
    legal_regime: str | None,
) -> list[dict[str, Any]]:
    """Require both the offence and FIR authority for emergency acid routes.

    Matter-plan date deferral is useful for intake, but it must not turn a
    retrieved BNS-only or procedure-only passage into a completed emergency
    answer. When the incident date is unknown, both current and legacy
    candidates must be available so the answer can state the regime choice
    without silently choosing one.
    """
    if (
        route_category not in {"police_fir", "criminal_general"}
        or not is_positive_acid_chemical_context(query)
    ):
        return []
    threat_only = is_acid_threat_only_query(query)
    attempted = is_acid_attempt_query(query)
    completed = is_completed_acid_attack_query(query)

    current = "current_bns_bnss_bsa_for_post_2024_incident"
    legacy = "legacy_ipc_crpc_evidence_for_pre_2024_incident"
    regimes = (
        ("current",)
        if legal_regime == current
        else ("legacy",)
        if legal_regime == legacy
        else ("current", "legacy")
    )
    lower = query.lower()
    if threat_only:
        offence_specs = {
            "current": (("bharatiya nyaya", "bns"), ("351",), ("bns_2023_acid_attack",)),
            "legacy": (("indian penal", "ipc"), ("506",), ("ipc_1860_acid_attack",)),
        }
        offence_label = "criminal-intimidation authority for the acid/chemical threat"
    elif attempted and not completed:
        offence_specs = {
            "current": (("bharatiya nyaya", "bns"), ("62", "124"), ("bns_2023_acid_attack",)),
            "legacy": (("indian penal", "ipc"), ("511", "326a", "326b"), ("ipc_1860_acid_attack",)),
        }
        offence_label = "attempted acid/chemical offence authority"
    elif "acid" in lower:
        offence_specs = {
            "current": (("bharatiya nyaya", "bns"), ("124",), ("bns_2023_acid_attack",)),
            "legacy": (("indian penal", "ipc"), ("326a",), ("ipc_1860_acid_attack",)),
        }
        offence_label = "acid-attack offence authority"
    else:
        offence_specs = {
            "current": (("bharatiya nyaya", "bns"), ("115", "117", "118", "124"), ("bns_2023_acid_attack",)),
            "legacy": (("indian penal", "ipc"), ("323", "324", "325", "326", "326a"), ("ipc_1860_acid_attack",)),
        }
        offence_label = "chemical-exposure/hurt authority"
    procedure_specs = {
        "current": (("bharatiya nagarik suraksha", "bnss"), ("173", "184", "193"), ("bnss_2023_fir_information_acid",)),
        "legacy": (("code of criminal procedure", "crpc"), ("154", "156", "164a"), ("crpc_1973_fir_information_acid",)),
    }

    missing: list[dict[str, Any]] = []
    for regime in regimes:
        title_terms, sections, source_pack_terms = offence_specs[regime]
        expected_documents = ("bns-2023",) if regime == "current" else ("ipc-1860",)
        if attempted and regime == "legacy":
            # IPC Section 511 supplies the attempt rule; Section 326A/326B
            # supplies the underlying acid/hurt authority. Either canonical
            # underlying section is acceptable when the pack contains it.
            required_section_groups = (("511",), ("326a", "326b"))
        else:
            required_section_groups = (
                tuple((section,) for section in sections)
                if attempted
                else (sections,)
            )
        offence_present = all(
            any(
                _incident_authority_passage_matches(
                    passage,
                    title_terms=title_terms,
                    section_terms=section_group,
                    source_pack_terms=source_pack_terms,
                    document_ids=expected_documents,
                )
                for passage in passages
                if isinstance(passage, dict)
            )
            for section_group in required_section_groups
        )
        if not offence_present:
            missing.append({
                "required_source": f"{regime} {offence_label}",
                "kind": "national_criminal_source_gap",
                "match_mode": "acid_incident_authority_pair",
                "required_anchor_patterns": [f"/sec-{section}" for section in sections],
            })
        title_terms, sections, source_pack_terms = procedure_specs[regime]
        if not any(
            _incident_authority_passage_matches(
                passage,
                title_terms=title_terms,
                section_terms=sections,
                source_pack_terms=source_pack_terms,
                document_ids=("bnss-2023",) if regime == "current" else ("crpc-1973",),
            )
            for passage in passages
            if isinstance(passage, dict)
        ):
            missing.append({
                "required_source": f"{regime} FIR/medical-care procedure authority",
                "kind": "national_criminal_source_gap",
                "match_mode": "acid_incident_authority_pair",
                "required_anchor_patterns": [f"/sec-{section}" for section in sections],
            })
    wife_aggressor_context = (
        any(term in lower for term in (
            "my wife", "wife slapped", "wife hit", "wife beat", "wife beats",
            "wife beating", "wife is beating", "wife took", "wife threw",
            "wife kicked", "wife threatens", "wife threatened", "wife punched",
            "wife assaulted", "wife attacked",
        ))
        and any(term in lower for term in (
            "slapped me", "hit me", "beat me", "beats me", "hitting me",
            "threatens me", "threatened me", "threatening me", "abuses me",
            "punched me", "punching me", "assaulted me", "assault me",
            "attacked me", "attacking me", "threatened to kill me",
            "threatens to kill me", "threatened to murder me", "tried to kill me",
            "forces sex", "forcing sex", "force sex", "forced sex",
            "sex without consent", "sexual assault", "assaulted me sexually",
            "my salary", "my atm", "atm card", "threatened me with acid",
        ))
        and "my husband" not in lower
        and "husband beat" not in lower
        and "husband hit" not in lower
    )
    inlaw_context = any(term in lower for term in (
        "mother in law", "mother-in-law", "father in law", "father-in-law",
        "in law", "in-law", "sasural", "husband", "wife", "spouse",
        "pati", "patni", "domestic", "domestic relationship", "matrimonial",
        "shared household",
    )) and not wife_aggressor_context
    if inlaw_context:
        for section in ("3", "18"):
            if not any(
                _incident_authority_passage_matches(
                    passage,
                    title_terms=("domestic violence", "protection of women"),
                    section_terms=(section,),
                    source_pack_terms=("pwdva_2005",),
                    document_ids=("domestic-violence-2005-official",),
                )
                for passage in passages
                if isinstance(passage, dict)
            ):
                missing.append({
                    "required_source": f"PWDVA 2005 Section {section} domestic-safety authority",
                    "kind": "national_family_source_gap",
                    "match_mode": "acid_domestic_authority_pair",
                    "required_anchor_patterns": [f"/sec-{section}"],
                })
    return missing


def build_source_gap_event(
    *,
    query: str,
    route_category: str,
    required_sources: list[str],
    passages: list[dict[str, Any]],
    plan: MatterPlan | None = None,
    legal_regime: str | None = None,
) -> dict[str, Any] | None:
    if (
        plan is not None
        and plan.answer_policy.fallback_reason == "multiple_plan_owners"
    ):
        return canonical_source_gap_handoff({
            "has_gap": True,
            "route_category": route_category,
            "gap_kinds": ["answer_owner_ambiguity"],
            "missing_required_sources": [],
            "message": (
                "Your question contains more than one legal problem that needs a "
                "different reviewed answer path. I will not combine them into one "
                "possibly misleading answer. Ask one issue at a time or use legal-aid "
                "intake to separate the immediate problem and next step."
            ),
            "handoff": "DLSA/legal aid, a qualified lawyer, or the relevant court/forum",
            "policy": "separate_conflicting_answer_owners",
            "conflicting_primary_owners": list(
                plan.answer_policy.conflicting_primary_owners
            ),
        }, route_category=route_category, reason="answer_owner_ambiguity")
    integrity_gap = matter_plan_integrity_gap(plan, query)
    if integrity_gap is not None:
        # Preserve the route's material local-authority classification when a
        # plan-integrity failure happens first. Without this enrichment the
        # handoff remains fail-closed, but the UI cannot offer the bounded
        # jurisdiction intake that is safe for a local gap.
        local_route_missing = [
            item for item in missing_required_authorities(
                required_sources=required_sources,
                passages=passages,
                query=query,
            )
            if item.get("kind") == "state_or_local_authority_gap"
        ]
        if local_route_missing:
            by_source = {
                str(item.get("required_source") or ""): item
                for item in local_route_missing
            }
            enriched_missing: list[dict[str, Any]] = []
            consumed: set[str] = set()
            for item in integrity_gap.get("missing_required_sources", []):
                source = str(item.get("required_source") or "")
                local_item = by_source.get(source)
                if local_item is not None:
                    enriched_missing.append({**item, "kind": local_item["kind"]})
                    consumed.add(source)
                else:
                    enriched_missing.append(item)
            enriched_missing.extend(
                item for source, item in by_source.items() if source not in consumed
            )
            integrity_gap = {
                **integrity_gap,
                "gap_kinds": sorted({
                    *integrity_gap.get("gap_kinds", []),
                    "state_or_local_authority_gap",
                }),
                "missing_required_sources": enriched_missing,
            }
        return canonical_source_gap_handoff(
            integrity_gap,
            route_category=route_category,
            reason="matter_plan_integrity_gap",
        )

    incident_missing = _missing_acid_chemical_authorities(
        query=query,
        route_category=route_category,
        passages=passages,
        legal_regime=legal_regime,
    )
    if incident_missing:
        return canonical_source_gap_handoff({
            "has_gap": True,
            "route_category": route_category,
            "gap_kinds": ["national_criminal_source_gap"],
            "missing_required_sources": incident_missing,
            "message": (
                "The incident-date offence and FIR authorities were not both verified. "
                "I will not choose the BNS/BNSS or IPC/CrPC route from a partial source window."
            ),
            "handoff": "DLSA/legal aid or a qualified criminal lawyer",
            "policy": "do_not_substitute_neighboring_authority",
        }, route_category=route_category, reason="acid_incident_authority_gap")

    # A housing-society pet fine is controlled by the society's bye-laws and
    # state/city authority, not by a generic consumer statute or a contextual
    # cooperative judgment. If the source window does not contain the exact
    # reviewed pet authority, fail closed before a neighboring source can
    # become the answer's legal basis.
    if (
        route_category == "consumer"
        and _is_housing_pet_query(query)
        and not has_housing_pet_authority(passages, query=query)
    ):
        return canonical_source_gap_handoff(
            {
                "has_gap": True,
                "route_category": route_category,
                "gap_kinds": ["state_or_local_authority_gap"],
                "missing_required_sources": [{
                    "required_source": (
                        "state/city cooperative-housing bye-laws or pet-specific authority"
                    ),
                    "kind": "state_or_local_authority_gap",
                    "match_mode": "housing_pet_source_guard",
                }],
                "message": (
                    "The state or city housing rule for this pet fine was not found. "
                    "I will not use a generic consumer statute as a substitute."
                ),
                "handoff": "Registrar of Cooperative Societies, local housing authority, or DLSA/legal aid",
                "policy": "do_not_substitute_neighboring_authority",
            },
            route_category=route_category,
            reason="housing_pet_source_gap",
        )
    if plan is not None:
        missing = missing_plan_authorities(plan=plan, passages=passages, query=query)
        # A plan may intentionally keep generic local-process labels out of
        # the legal-authority ledger. They are still a material route
        # requirement when the query needs a state/city procedure. Add only
        # those local gaps here so a national statute cannot silently turn
        # unverified forms, forums, or deadlines into an operative answer.
        route_missing = missing_required_authorities(
            required_sources=required_sources,
            passages=passages,
            query=query,
        )
        known_sources = {str(item.get("required_source") or "") for item in missing}
        missing.extend(
            item for item in route_missing
            if (
                item.get("kind") == "state_or_local_authority_gap"
                or _is_mgnrega_integrity_composite_requirement(
                    str(item.get("required_source") or "")
                )
            )
            and str(item.get("required_source") or "") not in known_sources
        )
    else:
        missing = missing_required_authorities(
            required_sources=required_sources,
            passages=passages,
            query=query,
        )
    if not missing:
        return None

    kinds = sorted({item["kind"] for item in missing})
    state_or_local = any(kind == "state_or_local_authority_gap" for kind in kinds)
    high_risk = (
        plan.answer_policy.requires_reviewed_contract
        if plan is not None
        else route_category in {
            "arrest_custody_safeguard",
            "business_contract_partnership",
            "criminal_defence_bail",
            "criminal_general",
            "cyber_fraud_or_harassment",
            "child_marriage_protection",
            "child_custody_adoption",
            "criminal_procedure_notice",
            "custody_compensation",
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
    if state_or_local:
        message = (
            "I do not have every controlling state or local source needed for this route. "
            "I will not treat a neighboring law or judgment as the final authority; verify "
            "the local rule with DLSA/legal aid or the relevant department before acting."
        )
    elif high_risk:
        message = (
            "A required authority for this high-risk route is missing from the retrieved "
            "source window. Treat this as intake and legal-aid handoff first, not a final "
            "legal answer."
        )
    else:
        message = (
            "One or more route-required authorities were not found in the retrieved source "
            "window. Read any answer as preliminary and verify the missing source before "
            "taking action."
        )

    return canonical_source_gap_handoff({
        "has_gap": True,
        "route_category": route_category,
        "gap_kinds": kinds,
        "missing_required_sources": missing,
        "message": message,
        "handoff": "DLSA/legal aid, a qualified lawyer, or the relevant court/forum",
        "policy": "do_not_substitute_neighboring_authority",
    }, route_category=route_category, reason="required_source_gap")


_MGNREGA_INTEGRITY_PACK_DOCUMENTS = {
    "prevention_corruption_1988_mgnrega_records": "prevention-of-corruption-1988",
    "bns_2023_mgnrega_forgery_cheating": "bns-2023",
}


def _verified_mgnrega_integrity_source_match(
    required_source: str,
    passages: list[dict[str, Any]],
    *,
    query: str,
) -> dict[str, Any] | None:
    """Match the MGNREGA BNS/PCA either-or source with pack identity.

    The route requirement has no single legal owner. It must therefore be
    checked outside the normal one-ledger-entry binding path, but accepting a
    title/anchor-only match here would recreate the provenance hole that the
    MatterPlan is meant to prevent.
    """
    for passage in passages or []:
        if not isinstance(passage, dict):
            continue
        pack_ids = set(_passage_source_pack_ids(passage))
        matching_pack_ids = pack_ids.intersection(_MGNREGA_INTEGRITY_PACK_DOCUMENTS)
        if len(matching_pack_ids) != 1:
            continue
        pack_id = next(iter(matching_pack_ids))
        document_id = str(passage.get("document_id") or "").strip().lower()
        source_type = str(passage.get("source_type") or "").strip()
        anchor = str(passage.get("anchor") or "").strip()
        if (
            not document_id
            or document_id != _MGNREGA_INTEGRITY_PACK_DOCUMENTS[pack_id]
            or source_type.lower() != "bare_act"
            or not anchor
        ):
            continue
        if _canonical_match(
            required_source,
            _item_blob(passage),
            query=query,
            passage_text=_passage_identity_text(passage),
        ):
            return passage
    return None


def missing_plan_authorities(
    *,
    plan: MatterPlan,
    passages: list[dict[str, Any]],
    query: str,
) -> list[dict[str, Any]]:
    """Find missing authorities using MatterPlan IDs as the primary key."""
    missing: list[dict[str, Any]] = []
    for entry in plan.authority_ledger:
        if (
            _plan_field(entry, "note") == "category_dependent_sc_article_341_vs_st_article_342"
            and not _contains_concrete_authority_name(
                str(_plan_field(entry, "source", "") or "")
            )
        ):
            continue
        if not is_active_plan_authority_entry(entry, plan=plan, query=query):
            continue
        if (
            _is_split_constitutional_descriptor(
                entry.source,
                source_pack_id=entry.source_pack_id,
            )
            and _constitution_article_requirement_match(
                entry.source,
                passages,
                retrieval_sources=plan.retrieval_sources,
            )
            is not None
        ):
            # Constitutional composite obligations may be satisfied by exact
            # Article passages from separate reviewed packs. The aggregate
            # matcher is the same rule used by best_source_match().
            continue
        if (
            "prevention of corruption" in str(entry.source or "").lower()
            and "bns" in str(entry.source or "").lower()
            and _verified_mgnrega_integrity_source_match(
                entry.source,
                passages,
                query=query,
            )
            is not None
        ):
            # This route obligation is deliberately either/or. The route may
            # retrieve the reviewed PCA pack without the BNS sibling, so a
            # plan entry must not reject a valid PCA passage before the
            # composite matcher runs. The helper above still requires pack,
            # document, source type, and exact section identity.
            continue
        if any(
            _passage_satisfies_plan_entry(plan, entry, passage)
            for passage in passages
            if isinstance(passage, dict)
        ):
            continue
        match_mode = (
            "legacy_provisional"
            if entry.source_pack_id
            and not entry.registry_key
            and entry.identity_status == "provisional"
            else "authority_id"
        )
        missing.append({
            "required_source": entry.source,
            "authority_id": entry.authority_id,
            "source_pack_id": entry.source_pack_id,
            "identity_status": entry.identity_status,
            "required_anchor_patterns": list(entry.required_anchor_patterns),
            "match_mode": match_mode,
            "kind": source_gap_kind(entry.source, query=query),
        })
    deduped: list[dict[str, Any]] = []
    # Keep distinct section obligations visible even when they share one
    # reviewed source pack. Only identical source/pack/kind/anchor rows are
    # duplicates; collapsing by source pack alone can hide a missing section
    # from the caller and weaken the fail-closed gate.
    seen: set[tuple[str, str, str, tuple[str, ...], str]] = set()
    for item in missing:
        key = (
            str(item.get("required_source") or ""),
            str(item.get("source_pack_id") or ""),
            str(item.get("kind") or ""),
            tuple(str(anchor) for anchor in (item.get("required_anchor_patterns") or ())),
            str(item.get("authority_id") or ""),
        )
        if key in seen:
            continue
        seen.add(key)
        deduped.append(item)
    return deduped


def _anchor_provision_token(anchor: object) -> str | None:
    """Return the normalized provision token encoded in a reviewed anchor."""
    match = re.search(
        r"/(?:sec(?:tion)?|article|order|clause)-([0-9][0-9a-z()./-]*)",
        str(anchor or "").lower(),
    )
    if match is None:
        return None
    token = re.sub(r"[^0-9a-z]+", "", match.group(1))
    return token or None


def _passage_satisfies_plan_entry(
    plan: MatterPlan,
    entry: Any,
    passage: dict[str, Any],
) -> bool:
    # Some high-volume Acts are covered by reviewed route source packs before
    # they receive an immutable authority-registry row.  Those packs still
    # carry an exact document identity and section anchors.  Treating their
    # empty DB authority mapping as an automatic miss creates a false source
    # gap even when the exact reviewed pack is present.  Keep registry-owned
    # obligations on the stricter explicit-ID path below.
    if (
        entry.source_pack_id
        and not entry.registry_key
        and entry.note != "registry_workflow_authority"
        and entry.source_pack_id in _passage_source_pack_ids(passage)
    ):
        source = next(
            (
                candidate
                for candidate in plan.retrieval_sources
                if candidate.source_pack_id == entry.source_pack_id
            ),
            None,
        )
        if source is None or not _source_pack_title_matches(
            passage.get("title"),
            source.title_patterns,
            allow_known_document_suffix=bool(source.doc_ids),
        ):
            return False
        passage_document_id = passage.get("document_id")
        if (
            passage_document_id is not None
            and str(passage_document_id).strip()
            and str(passage_document_id).strip().lower()
            not in {str(doc_id).strip().lower() for doc_id in source.doc_ids if doc_id}
        ):
            return False
        if (
            entry.source_pack_id == "pwdva_2005"
            and "domestic-violence-2005-official" in {
                str(doc_id).strip().lower() for doc_id in source.doc_ids if doc_id
            }
            and str(passage_document_id or "").strip().lower()
            != "domestic-violence-2005-official"
        ):
            return False
        # The provisional bypass is still an identity proof, not a title
        # heuristic. Missing pack metadata or passage type must fail closed.
        passage_source_type = str(passage.get("source_type") or "")
        if (
            not source.source_types
            or not passage_source_type
            or passage_source_type not in source.source_types
        ):
            return False
        anchor = str(passage.get("anchor") or "").lower()
        display_anchor = str(passage.get("display_anchor") or "").lower()
        if not source.doc_ids or not anchor:
            return False
        document_prefix = re.split(r"[/#]", anchor, maxsplit=1)[0]
        if not document_prefix or document_prefix not in source.doc_ids:
            return False
        required_anchors = tuple(entry.required_anchor_patterns or ())
        # A reviewed source pack may deliberately use a corpus anchor that
        # differs from the human label (for example Constitution Article 21
        # is stored under ``/sec-21``). Keep only the reviewed anchor with
        # the same provision token. A multi-section pack must not let one
        # provision satisfy another ledger entry from that pack.
        if entry.section:
            section_match = re.search(
                r"\b(?:section|sec\.?|article|order|clause)\s+"
                r"([0-9][0-9a-z()./-]*)",
                entry.section,
                flags=re.IGNORECASE,
            )
            if section_match:
                token = section_match.group(1).lower()
                token = token.replace("(", "-").replace(")", "")
                token = re.sub(r"[^0-9a-z-]+", "-", token).strip("-")
                kind = entry.section.split(None, 1)[0].lower().rstrip(".")
                prefix = {
                    "section": "sec",
                    "sec": "sec",
                    "article": "article",
                    "order": "order",
                    "clause": "clause",
                }.get(kind, "sec")
                normalized_token = re.sub(r"[^0-9a-z]+", "", token)
                matching_reviewed_anchors = tuple(
                    pattern
                    for pattern in required_anchors
                    if _anchor_provision_token(pattern) == normalized_token
                )
                required_anchors = matching_reviewed_anchors or (f"/{prefix}-{token}",)
        if not required_anchors:
            return True
        # The pack itself is reviewed metadata. For a non-registry pack its
        # exact pack anchor is sufficient identity evidence; requiring a
        # passage heading here would turn split/legacy corpus anchors into a
        # false gap. Registry-owned entries still use the stricter ID path
        # below.
        return any(
            _source_pack_anchor_matches(anchor, pattern)
            or _source_pack_anchor_matches(display_anchor, pattern)
            or _plan_anchor_matches(
                    anchor,
                    pattern,
                    passage_text=_passage_identity_text(passage),
                )
            or _plan_anchor_matches(
                    display_anchor,
                    pattern,
                    passage_text=_passage_identity_text(passage),
                )
            for pattern in required_anchors
        )

    source_pack_authority_ids = _passage_source_pack_authority_ids(passage)
    if entry.source_pack_id and entry.source_pack_id in source_pack_authority_ids:
        authority_ids = list(source_pack_authority_ids[entry.source_pack_id])
    elif entry.source_pack_id and source_pack_authority_ids and (
        entry.source_pack_id in _passage_source_pack_ids(passage)
    ):
        # A merged chunk is annotated for this reviewed pack but has no
        # authority evidence for it. Do not borrow a registry ID from another
        # alias on the same physical chunk.
        authority_ids = []
    elif "authority_ids" in passage:
        # Production passages are emitted by _make_passages and always carry
        # this key. An empty list means the database did not attach the
        # registry mapping; title/anchor resemblance is not identity proof.
        authority_ids = [str(value) for value in (passage.get("authority_ids") or [])]
    else:
        # Legacy unit fixtures may omit metadata entirely; retain inference
        # there without allowing it into the serving path above.
        authority_ids = authority_ids_for_passage(
            plan,
            title=str(passage.get("title") or ""),
            anchor=str(passage.get("anchor") or ""),
            text=_passage_identity_text(passage),
            source_pack_id=passage.get("required_source_pack"),
            source_type=passage.get("source_type"),
        )
    if entry.authority_id not in authority_ids:
        return False
    if entry.registry_key:
        if not entry.source_pack_id:
            return False
        if str(entry.source_pack_id) not in _passage_source_pack_ids(passage):
            return False
        registry_source = next(
            (
                candidate
                for candidate in getattr(plan, "retrieval_sources", ())
                if str(getattr(candidate, "source_pack_id", "")) == str(entry.source_pack_id)
            ),
            None,
        )
        if registry_source is None:
            return False
        passage_document_id = passage.get("document_id")
        if (
            passage_document_id is not None
            and str(passage_document_id).strip()
            and str(passage_document_id).strip().lower()
            not in {
                str(doc_id).strip().lower()
                for doc_id in (getattr(registry_source, "doc_ids", ()) or ())
                if doc_id
            }
        ):
            return False
        passage_source_type = str(passage.get("source_type") or "")
        if (
            not passage_source_type
            or passage_source_type not in tuple(getattr(registry_source, "source_types", ()) or ())
        ):
            return False
        anchor = str(passage.get("anchor") or "")
        document_prefix = re.split(r"[/#]", anchor, maxsplit=1)[0]
        if (
            not document_prefix
            or document_prefix not in {
                str(doc_id) for doc_id in (getattr(registry_source, "doc_ids", ()) or ())
            }
        ):
            return False
        if not _source_pack_title_matches(
            passage.get("title"),
            getattr(registry_source, "title_patterns", ()) or (),
            allow_known_document_suffix=bool(getattr(registry_source, "doc_ids", ()) or ()),
        ):
            return False
        record = next(
            (
                candidate
                for candidate in load_authority_registry().records
                if candidate.canonical_key == entry.registry_key
            ),
            None,
        )
        if record is not None:
            expected_snapshot = getattr(record, "consolidation_as_at", None)
            if expected_snapshot is not None and str(passage.get("as_at") or "") != str(
                expected_snapshot
            ):
                return False
    required_anchors = tuple(entry.required_anchor_patterns or ())
    if not required_anchors:
        return True
    anchor = str(passage.get("anchor") or "").lower()
    return any(
        _plan_anchor_matches(
            anchor,
            pattern,
            passage_text=_passage_identity_text(passage),
        )
        for pattern in required_anchors
    )


def _passage_source_pack_ids(passage: dict[str, Any]) -> tuple[str, ...]:
    """Read the primary reviewed pack and any aliases from a passage."""
    values: list[object] = [
        passage.get("required_source_pack"),
        passage.get("_required_source_pack"),
    ]
    for key in ("required_source_packs", "_required_source_packs"):
        aliases = passage.get(key)
        if isinstance(aliases, (list, tuple, set)):
            values.extend(aliases)
        elif aliases is not None:
            values.append(aliases)
    return tuple(dict.fromkeys(
        str(value).strip()
        for value in values
        if str(value or "").strip()
    ))


def _passage_source_pack_authority_ids(passage: dict[str, Any]) -> dict[str, tuple[str, ...]]:
    raw_mapping = passage.get("required_source_pack_authority_ids") or passage.get(
        "_required_source_pack_authority_ids"
    )
    if not isinstance(raw_mapping, dict):
        return {}
    out: dict[str, tuple[str, ...]] = {}
    for raw_pack_id, raw_ids in raw_mapping.items():
        pack_id = str(raw_pack_id or "").strip()
        if not pack_id:
            continue
        values = raw_ids if isinstance(raw_ids, (list, tuple, set)) else (raw_ids,)
        authority_ids = tuple(dict.fromkeys(
            str(value).strip()
            for value in values
            if str(value or "").strip()
        ))
        if authority_ids:
            out[pack_id] = authority_ids
    return out


def _plan_anchor_matches(
    anchor: str,
    pattern: str,
    *,
    passage_text: str | None = None,
) -> bool:
    needle = str(pattern or "").lower()
    if not _valid_anchor_snapshot(anchor):
        return False
    if needle.startswith(("/sec-", "/article-", "/clause-", "/order-", "/rule-")):
        official_suffix = "" if needle.endswith("-official") else "(?:-official)?"
        suffix_boundary = r"(?:@[0-9]{4}-[0-9]{2}-[0-9]{2}(?:__[0-9]+(?:-[a-z])?)?|__[0-9]+(?:-[a-z])?(?:@[0-9]{4}-[0-9]{2}-[0-9]{2})?|)"
        exact = re.search(
            rf"{re.escape(needle)}{official_suffix}{suffix_boundary}$",
            anchor,
        ) is not None
        split_needle = (
            needle[:-len("-official")]
            if needle.endswith("-official")
            else needle
        )
        split_token = re.search(
            rf"(?:/(?:sec|article|clause|order|rule))-([0-9]+)-([a-z0-9]+)"
            rf"(?:-official)?{suffix_boundary}$",
            split_needle,
        )
        if exact:
            # A suffixed anchor may be a split numeric provision or a distinct
            # alphanumeric provision. Require its heading in serving paths;
            # metadata alone is not enough to identify 142 vs 142A.
            if split_token:
                if not passage_text:
                    return False
                root = split_token.group(1)
                suffix = split_token.group(2)
                if root == "173" and suffix == "a":
                    return _passage_heading_matches_exact_section(
                        passage_text,
                        ("173", "173(1)"),
                    )
                if root == "173" and suffix == "c":
                    return _passage_heading_matches_exact_section(passage_text, "173(4)")
                return _passage_heading_matches_section(
                    passage_text,
                    (root, f"{root}{suffix}"),
                )
            return True
        split = re.search(
            rf"{re.escape(needle)}-([a-z0-9]+)(?:-official)?{suffix_boundary}$",
            anchor,
        )
        if not split or not passage_text:
            return False
        token = needle.rsplit("-", 1)[-1]
        return _passage_heading_matches_section(passage_text, token)
    return needle in anchor


def _source_pack_anchor_matches(anchor: str, pattern: str) -> bool:
    """Match two reviewed-pack anchors without fuzzy substring promotion.

    Unlike passage matching, both values here are trusted pack metadata, so a
    split anchor such as ``/sec-173-a`` is valid without a passage heading.
    The boundary still prevents ``/sec-59`` from matching ``/sec-591``.
    """
    needle = str(pattern or "").lower()
    value = str(anchor or "").lower()
    if not needle or not value:
        return False
    # Reviewed pack metadata sometimes uses a section prefix (for example
    # ``sec-4-``) while indexed passages use the publication boundary marker
    # ``@``. Treat the trailing hyphen as a section-prefix boundary, without
    # allowing a neighbouring section such as sec-40 to match.
    if needle.endswith("-"):
        stem = needle[:-1]
        return re.search(
            rf"{re.escape(stem)}(?:-|@|__|$)",
            value,
        ) is not None
    # ``@`` in a reviewed pack is a snapshot/publication boundary. Verified
    # supplements use ``-official`` before that boundary, so compare the
    # provision token first and retain the same strict boundary checks.
    snapshot_marker = needle.endswith("@")
    base_needle = needle[:-1] if snapshot_marker else needle
    official_suffix = "" if base_needle.endswith("-official") else "(?:-official)?"
    split_suffix = r"(?:-[a-z]{1,2})?"
    if not re.search(r"(?:^|/)sec-[0-9]+[a-z]?$", base_needle):
        split_suffix = ""
    return re.search(
        rf"{re.escape(base_needle)}{split_suffix}{official_suffix}(?=@|__|$)",
        value,
    ) is not None


def _date_dependent_regime_packs_ready(
    requirement: str,
    retrieval_sources: list[Any],
) -> bool:
    """Require both concrete regime candidates before deferring by date."""
    lower_requirement = str(requirement or "").lower()
    current_terms = (
        "bns", "bnss", "bsa", "bharatiya nyaya", "bharatiya nagarik",
        "bharatiya sakshya",
    )
    legacy_terms = (
        "ipc", "crpc", "evidence act", "indian penal code",
        "code of criminal procedure",
    )
    required_families = {
        "current" if any(term in lower_requirement for term in current_terms) else None,
        "legacy" if any(term in lower_requirement for term in legacy_terms) else None,
    } - {None}
    if required_families != {"current", "legacy"}:
        return False

    family_pack_ids: dict[str, set[str]] = {"current": set(), "legacy": set()}
    for source in retrieval_sources:
        if not _plan_field(source, "doc_ids", None) or not _plan_field(source, "source_types", None):
            continue
        source_pack_id = str(_plan_field(source, "source_pack_id", "") or "")
        if not source_pack_id:
            continue
        source_blob = " ".join(
            [
                source_pack_id,
                *[str(title) for title in (_plan_field(source, "title_patterns", ()) or ())],
            ]
        ).lower()
        if any(term in source_blob for term in current_terms):
            family_pack_ids["current"].add(source_pack_id)
        if any(term in source_blob for term in legacy_terms):
            family_pack_ids["legacy"].add(source_pack_id)
    current_ids = family_pack_ids["current"]
    legacy_ids = family_pack_ids["legacy"]
    return bool(current_ids and legacy_ids and current_ids.isdisjoint(legacy_ids))


def missing_required_authorities(
    *,
    required_sources: list[str],
    passages: list[dict[str, Any]],
    query: str,
) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for required in required_sources or []:
        text = str(required or "").strip()
        if not text:
            continue
        requirement_type = classify_required_source_requirement(text)
        if not _should_enforce_requirement(text, requirement_type, query):
            continue
        if _is_mgnrega_integrity_composite_requirement(text):
            matched = _verified_mgnrega_integrity_source_match(
                text,
                passages,
                query=query,
            )
        else:
            matched = best_source_match(text, passages, query=query)
        if matched is not None:
            continue
        out.append({
            "required_source": text,
            "kind": source_gap_kind(text, query=query),
        })
    return out


def classify_required_source_requirement(text: str) -> str:
    lower = str(text or "").strip().lower()
    if not lower:
        return "fact_or_document_requirement"
    # These are service/triage destinations, not legal authorities. Keep the
    # explicit route labels out of the statutory provenance gate even though
    # their names contain NALSA/DLSA tokens used for authority detection.
    if (
        "labour/dlsa grievance route" in lower
        or "labour dlsa grievance route" in lower
        or "nalsa/slsa/dlsa legal-aid procedure" in lower
        or "nalsa/slsa/dlsa legal aid procedure" in lower
    ) and not _contains_concrete_authority_name(lower):
        return "procedural_or_local_source"
    if (
        "religion/personal-law and family-tree facts" in lower
        and not _contains_concrete_authority_name(lower)
    ):
        return "fact_or_document_requirement"
    if any(term in lower for term in (
        "records only after",
        "records only to identify",
        "documents only after",
        "documents only to identify",
    )) and not _contains_concrete_authority_name(lower):
        return "fact_or_document_requirement"
    names_concrete_authority = (
        _contains_concrete_authority_name(lower)
        or bool(re.search(r"\bregulations?\b", lower))
        or _has(lower, (
            "bns", "bnss", "bharatiya nyaya sanhita",
            "bharatiya nagarik suraksha sanhita",
            "bharatiya sakshya adhiniyam", "crpc", "ipc", "constitution", "ombudsman",
            "rbi", "cgst", "gst", "income tax", "customs", "pmla", "pocso",
            "pwdva", "nalsa", "dlsa", "statute", "nclt", "nclat",
            "medical council", "medical ethics",
            "compoundability", "compoundable", "compounding",
        ))
    )
    if any(term in lower for term in (
        "bank statement", "complaint number", "date", "details", "document",
        "documents", "evidence", "proof", "record", "records",
        "transaction reference",
    )) and not names_concrete_authority:
        return "fact_or_document_requirement"
    procedural_terms = (
        "court rules", "practice directions", "state rules",
        "state maintenance tribunal rules", "scheme rules", "portal",
        "procedure", "grievance route", "complaint route", "forum",
        "forms", "fees", "certified-copy", "certified copy",
        "help desk", "identity-record update rules",
        "school board", "state caste-certificate",
        "state caste certificate", "state education rules",
        # Local licensing and closure powers are operative procedural
        # authorities even when the route deliberately avoids naming a
        # specific municipal Act or by-law.
        "municipal corporation", "municipality law", "trade-licence by-laws",
        "trade license by-laws", "local municipal law", "sealing order",
        "municipal sealing", "shop closure power", "local body", "local authority",
        "municipal authority", "ward office", "commercial premises", "licence issue",
        "license issue", "locked premises", "premises locked", "premises sealed",
        "closure notice", "trade licence", "trade license",
    )
    if any(term in lower for term in procedural_terms) and not names_concrete_authority:
        return "procedural_or_local_source"
    conditional_terms = (
        " only if ", " only where ", " where applicable", " where relevant",
        " where needed", " where ", " if ", " based on ", " depending on ",
        " when ",
    )
    if any(term in f" {lower} " for term in conditional_terms):
        return "conditional_authority"
    if _looks_like_authority(lower):
        return "must_cite_authority"
    if any(term in f" {lower} " for term in (
        " based on ", " depending on ", " if ", " only where ", " when ",
        " where ", " where applicable", " where needed", " where relevant",
    )):
        return "conditional_authority"
    return "fact_or_document_requirement"


def _contains_concrete_authority_name(text: str) -> bool:
    lower = str(text or "").strip().lower()
    canonical_aliases = tuple(_SOURCE_PACK_ACRONYM_ALIASES)
    return bool(
        re.search(
            r"\b(?:act|code)\b|\bconstitution\b|\barticle\s+\d+[a-z]?\b",
            lower,
        )
        or any(
            re.search(rf"(?<![a-z0-9]){re.escape(alias)}(?![a-z0-9])", lower)
            for alias in (
                *canonical_aliases,
                "bns", "bnss", "bsa", "ipc", "crpc", "pocso", "pwdva",
                "pmla", "cgst", "gst", "income tax", "customs", "nclt", "nclat",
                "rte", "rera", "ibc", "pesa", "bocw", "rti", "ndps",
                "mgnrega", "msmed", "posh", "mact", "esi", "epf",
                "sc/st", "sc-st", "sc st",
            )
        )
    )


def _is_nonblocking_plan_context_requirement(text: str) -> bool:
    """Identify generic intake/context labels that are not authorities.

    These labels may be useful in the user-facing plan, but they do not name
    a source that can prove an operative legal proposition. Keep this list
    deliberately explicit: state-specific statutes, exact forms, and concrete
    procedural authorities must still participate in the source gate.
    """
    lower = str(text or "").strip().lower()
    context_only_markers = (
        "personal law and local filing rules",
        "personal law / local filing rules",
        "family law statute by religion",
        "religion/personal-law and family-tree facts",
        "victim-compensation and dlsa procedure",
        "victim compensation and dlsa procedure",
        "identity-record update rules",
        "state rera rules and filing procedure",
        "labour/dlsa grievance route",
        "labour authority / esi court procedure",
        "state labour-department notification/appeal route",
    )
    if any(
        lower.startswith("state rera rules and filing procedure")
        or lower == marker
        for marker in (
            "labour/dlsa grievance route",
            "labour authority / esi court procedure",
            "state labour-department notification/appeal route",
        )
    ):
        return True
    if any(marker in lower for marker in context_only_markers):
        # The marker can be embedded in a route label. Preserve the old
        # context-only behavior for the generic label, but never let it hide a
        # concrete named authority such as "Hindu Marriage Act 1955" or
        # "SC-ST Act 1989" in the same requirement.
        if not _contains_concrete_authority_name(lower):
            return True
        return False

    # Do not let a generic suffix hide a concrete Act, Code, Article, or
    # named authority in a composite requirement. The classifier is the
    # single source of truth for this concrete-authority check.
    if classify_required_source_requirement(lower) != "procedural_or_local_source":
        return False
    if _contains_concrete_authority_name(lower):
        return False
    return any(
        marker in lower
        for marker in (
            # Generic destination/process labels from action packs. These
            # should become an intake caveat, not a false statutory gap.
            "state drug-control authority procedure",
            "state motor vehicle rules / traffic police e-challan procedure",
            "state motor vehicle rules and transport-department renewal procedure",
            "state/central licence upgrade procedure",
            "consumer protection rules / e-daakhil procedure",
            "court rules and practice directions for the relevant court",
            "court rules/practice directions for the court named in the summons",
            "human-rights commission procedure",
            "state disability certificate / udid procedure",
            "state education rules",
            "election commission voter-services procedure",
            "family court procedure and existing order enforcement route",
            "registrar of companies / mca procedure for llp filings",
            "nalsa/slsa/dlsa legal-aid procedure for application and assignment",
            "state maintenance tribunal rules",
            "panchayat/municipal registrar procedure",
            "state pension/scholarship/ration scheme rules",
            "state caste certificate rules",
            "state caste-certificate rules",
            "municipal corporation / town vending committee procedure",
            "state municipal corporation/municipality law and trade-licence by-laws",
            "state municipal corporation/municipality law",
            "trade-licence by-laws",
            "trade license by-laws",
        )
    )


def _material_state_context_requirement(text: str, query: str) -> bool:
    """Whether a generic local-process label is material to this query."""
    lower_source = str(text or "").lower()
    lower_query = str(query or "").lower()
    if "state rera rules and filing procedure" in lower_source:
        return (
            _has_named_state_or_city_context(lower_query)
            and _has(lower_query, (
                "rera", "real estate", "builder", "promoter", "project",
                "possession", "occupancy", "complaint", "filing", "registration",
            ))
        )
    if "state labour-department notification/appeal route" in lower_source:
        return (
            _has_named_state_or_city_context(lower_query)
            and _has(lower_query, (
                "minimum wage", "minimum wages", "wage rate", "wages rate",
                "notification", "unskilled", "skilled", "labour rate", "labor rate",
                "wage complaint", "appeal",
            ))
        )
    if (
        has_private_business_actor_context(lower_query)
        or has_private_vendor_actor_context(lower_query)
    ):
        # A municipality mentioned elsewhere in a query does not convert a
        # private landlord/company/security action into public enforcement.
        # Keep the local-authority requirement conditional on the actor.
        return False
    if any(
        marker in lower_source
        for marker in (
            "state municipal corporation/municipality law",
            "municipal trade-license rules where applicable",
            "municipal trade-licence rules where applicable",
            "municipal corporation / town vending committee procedure",
        )
    ) and not (
        has_explicit_municipal_authority_context(lower_query)
        or has_specific_hawker_corporation_context(lower_query)
    ):
        # Generic business closure language does not establish that a local
        # authority acted. Keep this state/local source conditional until the
        # intake identifies the municipality or local public body.
        return False

    def query_has_term(term: str) -> bool:
        normalized = str(term or "").strip().lower()
        if not normalized:
            return False
        if normalized.endswith(" corporation"):
            return has_qualified_city_corporation(
                lower_query,
                city=normalized.rsplit(" ", 1)[0],
            )
        if " " in normalized:
            return normalized in lower_query
        return re.search(rf"\b{re.escape(normalized)}\b", lower_query) is not None

    context_terms = {
        "state education rules": ("school", "admission", "teacher", "tc", "education"),
        "state caste certificate rules": ("caste", "sc", "st", "scheduled caste", "scheduled tribe"),
        "state caste-certificate rules": ("caste", "sc", "st", "scheduled caste", "scheduled tribe"),
        "state pension/scholarship/ration scheme rules": (
            "pension", "scholarship", "ration", "widow", "scheme", "benefit",
        ),
        "state maintenance tribunal rules": (
            "maintenance", "senior citizen", "old age", "parent", "father", "mother",
        ),
        "state disability certificate / udid procedure": (
            "disability", "udid", "pwd", "disabled",
        ),
        "state drug-control authority procedure": (
            "drug", "medical store", "pharmacy", "chemist", "schedule h", "inspector",
        ),
        "state motor vehicle rules / traffic police e-challan procedure": (
            "traffic", "challan", "license", "licence", "rto", "vehicle", "auto",
        ),
        "state motor vehicle rules and transport-department renewal procedure": (
            "permit", "transport", "renew", "vehicle", "rto", "auto",
        ),
        "municipal corporation / town vending committee procedure": (
            "municipal", "vendor", "cart", "street", "hawker", "seized",
            "hawker license", "hawker licence", "vending license", "vending licence",
            "vending certificate", "certificate of vending", "corporation removed",
            "corporation seized", "corporation took", "corporation demolished",
            "corporation evicted", "goods",
        ),
        "state municipal corporation/municipality law and trade-licence by-laws": (
            "municipal", "municipality", "sealed", "sealing", "closure",
            "shop", "trade licence", "trade license", "business premises",
            "local body", "local authority", "municipal authority", "ward office",
            "local health authority", "local health department",
            "local health inspector", "local health officer",
            "municipal health department", "municipal health inspector",
            "municipal health officer", "city health department", "health department",
            "hawker license", "hawker licence", "vending license", "vending licence",
            "vending certificate", "certificate of vending", "corporation removed",
            "corporation seized", "corporation took", "corporation demolished",
            "corporation evicted", "goods",
            "vadodara corporation", "ahmedabad corporation", "surat corporation",
            "rajkot corporation", "baroda corporation", "pune corporation",
            "nagpur corporation", "nashik corporation", "thane corporation",
            "indore corporation", "bhopal corporation", "jaipur corporation",
            "jodhpur corporation", "lucknow corporation", "kanpur corporation",
            "patna corporation", "coimbatore corporation", "madurai corporation",
            "chennai corporation", "hyderabad corporation", "bengaluru corporation",
            "bangalore corporation", "mumbai corporation",
            "commercial premises", "licence issue", "license issue", "locked",
            "premises locked", "premises sealed", "closure notice",
        ),
        "state municipal corporation/municipality law": (
            "municipal", "municipality", "sealed", "sealing", "closure",
            "shop", "trade licence", "trade license", "business premises",
            "local body", "local authority", "municipal authority", "ward office",
            "local health authority", "local health department",
            "local health inspector", "local health officer",
            "municipal health department", "municipal health inspector",
            "municipal health officer", "city health department", "health department",
            "hawker license", "hawker licence", "vending license", "vending licence",
            "vending certificate", "certificate of vending", "corporation removed",
            "corporation seized", "corporation took", "corporation demolished",
            "corporation evicted", "goods",
            "vadodara corporation", "ahmedabad corporation", "surat corporation",
            "rajkot corporation", "baroda corporation", "pune corporation",
            "nagpur corporation", "nashik corporation", "thane corporation",
            "indore corporation", "bhopal corporation", "jaipur corporation",
            "jodhpur corporation", "lucknow corporation", "kanpur corporation",
            "patna corporation", "coimbatore corporation", "madurai corporation",
            "chennai corporation", "hyderabad corporation", "bengaluru corporation",
            "bangalore corporation", "mumbai corporation",
            "commercial premises", "licence issue", "license issue", "locked",
            "premises locked", "premises sealed", "closure notice",
        ),
        "trade-licence by-laws": (
            "trade licence", "trade license", "shop", "business", "municipal",
            "municipality", "sealed", "sealing",
        ),
        "trade license by-laws": (
            "trade licence", "trade license", "shop", "business", "municipal",
            "municipality", "sealed", "sealing",
        ),
    }
    return any(
        marker in lower_source and any(query_has_term(term) for term in terms)
        for marker, terms in context_terms.items()
    )


def _strict_local_source_requirement(text: str, query: str) -> bool:
    """Mark only reviewed state-specific obligations as hard source gates."""
    lower = str(text or "").lower()
    if not any(
        marker in lower
        for marker in (
            "state rera rules and filing procedure",
            "state labour-department notification/appeal route",
        )
    ):
        return False
    return _material_state_context_requirement(lower, query)


def _has_named_state_or_city_context(query: str) -> bool:
    terms = (
        "andhra pradesh", "arunachal pradesh", "assam", "bihar", "chhattisgarh",
        "delhi", "goa", "gujarat", "haryana", "himachal pradesh", "jharkhand",
        "karnataka", "kerala", "madhya pradesh", "maharashtra", "manipur",
        "meghalaya", "mizoram", "nagaland", "odisha", "orissa", "punjab",
        "rajasthan", "sikkim", "tamil nadu", "telangana", "tripura",
        "uttar pradesh", "uttarakhand", "west bengal", "ahmedabad", "bengaluru",
        "bangalore", "bhopal", "chennai", "hyderabad", "jaipur", "kolkata",
        "lucknow", "mumbai", "nagpur", "noida", "patna", "pune", "ranchi",
        "surat", "vadodara", "baroda", "thane", "indore", "rajkot",
        "kochi", "cochin", "ernakulam", "thiruvananthapuram", "trivandrum",
        "coimbatore", "madurai", "salem", "tiruchirappalli", "trichy",
        "tirunelveli", "vellore", "mysuru", "mysore", "mangalore", "kozhikode",
        "calicut", "thrissur", "faridabad", "gurugram", "gurgaon", "chandigarh",
        "jammu", "srinagar", "puducherry", "pondicherry", "port blair", "shimla",
        "dehradun", "amritsar", "kanpur", "agra", "varanasi", "meerut",
        "visakhapatnam", "vizag", "vijayawada", "tirupati", "nashik", "pimpri",
    )
    return any(re.search(rf"\b{re.escape(term)}\b", query) for term in terms)


def _plan_field(value: Any, name: str, default: Any = None) -> Any:
    """Read a MatterPlan field from either a dataclass or an eval payload."""
    if isinstance(value, dict):
        return value.get(name, default)
    return getattr(value, name, default)


def is_active_plan_authority_entry(
    entry: Any,
    *,
    plan: Any = None,
    query: str = "",
) -> bool:
    """Return whether an authority-ledger entry is an operative obligation.

    MatterPlan carries both citable legal authorities and useful intake
    pointers such as state rules, court practice directions, and document
    requirements. Serving and evaluation must apply the same distinction or a
    harmless context pointer becomes a false missing-citation failure.
    """
    source = str(_plan_field(entry, "source", "") or "")
    lower_source = source.strip().lower()
    if _plan_field(entry, "note") == "intake_precondition" and not _strict_local_source_requirement(source, query):
        return False
    # These are intake/safety preconditions, not authorities that can be
    # cited by themselves. The serving source gate validates the actual
    # statute or dual-regime passage separately; counting the precondition as
    # a citable authority creates a false missing-pack failure before
    # retrieval can prove the route.
    if lower_source in {
        "exact offence section and consent/permission status before treating a criminal case as compoundable",
        "court permission and offence-compoundability limits must be checked from the exact section",
        "caste/tribal-status fact check before adding sc/st atrocity route",
    } or lower_source.startswith("identity-record update rules") or "only as a separate criminal-negligence track where facts support it" in lower_source:
        return False
    if lower_source.startswith("registration/allotment/agreement documents for proving"):
        return False
    requirement_type = classify_required_source_requirement(source)
    strict_local_context = _strict_local_source_requirement(source, query)
    generic_context = (
        _is_nonblocking_plan_context_requirement(source)
        and not strict_local_context
    )
    # Route-derived requirements can intentionally use a descriptive label
    # such as "state Shops law" while still being bound to an exact reviewed
    # source pack, document identity, and provision anchors.  Treating that
    # label as ordinary intake context lets unrelated retrieved Acts unlock a
    # free-form answer.  The pack-scoped passage check below is the authority
    # proof for this path; until it is present, the answer must hand off.
    route_bound_required = (
        bool(_plan_field(entry, "source_pack_id"))
        and _plan_field(entry, "note") == "derived_from_route_required_sources"
        and _plan_field(entry, "must_cite") is True
        and plan is not None
    )
    if (
        (
            requirement_type == "fact_or_document_requirement"
            and not _contains_concrete_authority_name(source)
            and not strict_local_context
            and not route_bound_required
        )
    ):
        return False
    if generic_context:
        # A generic local-process label is normally an intake pointer, but a
        # plan containing no other concrete authority would otherwise pass
        # through with no source-backed legal basis at all. Keep that case
        # fail-closed; when a named controlling authority is present, retain
        # the local pointer as context rather than turning it into a false
        # statutory citation obligation.
        if plan is None:
            return False
        concrete_ledger = _plan_field(plan, "authority_ledger", ()) or ()
        has_concrete_authority = any(
            candidate is not entry
            and _plan_field(candidate, "must_cite") is True
            and _contains_concrete_authority_name(
                str(_plan_field(candidate, "source", "") or "")
            )
            and not _is_nonblocking_plan_context_requirement(
                str(_plan_field(candidate, "source", "") or "")
            )
            for candidate in concrete_ledger
        )
        if not has_concrete_authority:
            return bool(_plan_field(entry, "must_cite")) if _material_state_context_requirement(source, query) else False
        return False
    if (
        _plan_field(entry, "note") == "category_dependent_sc_article_341_vs_st_article_342"
        and source.strip().lower()
        == "constitution article 341 or 342 after the sc/st category is confirmed"
    ):
        return False
    if plan is not None and _is_deferred_date_regime_entry(plan, entry):
        # A cheque query still needs the complaint procedure before any
        # deadline or regime-sensitive answer is shown. Do not let the
        # unknown-date wrapper turn an NI Act-only retrieval into a pass.
        if _has(query, (
            "cheque", "cheques", "dishonour", "dishonored", "bounced",
            "negotiable instruments", "section 138", "138 notice",
        )) and _has(lower_source, ("bnss", "crpc", "complaint procedure")):
            return True
        return False
    if _plan_field(entry, "conditional"):
        return _should_enforce_requirement(source, requirement_type, query)
    return bool(_plan_field(entry, "must_cite"))


def should_enforce_required_source(required_source: str, *, query: str) -> bool:
    """Return whether a route-required source should be enforced for this query."""
    text = str(required_source or "").strip()
    if not text:
        return False
    requirement_type = classify_required_source_requirement(text)
    return _should_enforce_requirement(text, requirement_type, query)


def _sale_of_goods_quality_dispute_context(query: str) -> bool:
    """Activate the Sale of Goods lane only for a stated quality dispute."""
    query_lower = str(query or "").lower()
    if any(term in query_lower for term in (
        "no quality", "no quality dispute", "no defect", "no defects",
        "not defective", "not damaged", "not a defect", "no rejection",
        "not rejected", "without rejection", "no acceptance dispute",
        "delivery service", "customer service", "service quality",
        "delivery date", "payment request", "shipment delayed",
        "stock quality report",
        "product manager", "software product", "digital product", "saas product",
        "service product", "product roadmap", "proposal", "roadmap",
        "specification document", "software component", "training material",
        "documents to the department", "application", "electricity supply",
        "water supply", "power supply", "internet supply",
    )):
        return False
    has_quality_or_rejection_fact = any(term in query_lower for term in (
        "quality", "defect", "defective", "reject", "rejection",
        "price deduction", "quality deduction", "short supply",
        "substandard", "non-conforming", "non conforming", "bad batch",
        "batch was bad",
        "damaged", "not as described", "does not match",
        "doesn't match", "wrong model", "wrong item", "wrong goods",
        "specification", "specifications", "will not accept",
        "refused to accept", "refuse to accept", "did not accept",
        "not accept", "rejected delivery", "refused delivery", "refused",
        "failed inspection", "failed testing", "wrong quantity", "short by",
        "shortage", "short shipment", "quantity shortage", "pieces arrived",
        "units arrived", "wrong colour", "wrong color", "nonconforming",
    ))
    has_core_goods_context = any(term in query_lower for term in (
        "goods", "parts", "items", "consignment", "merchandise",
        "purchase order", "equipment",
    ))
    has_product_context = (
        any(term in query_lower for term in ("product", "products"))
        and not any(term in query_lower for term in (
            "product manager", "software product", "digital product", "saas product",
            "service product", "product roadmap", "proposal", "roadmap",
        ))
        and any(term in query_lower for term in (
            "physical product", "finished product", "manufactured product",
            "product shipment", "product batch", "product delivered",
            "product received", "product defect", "defective product",
            "damaged product", "product quality",
        ))
    )
    has_batch_context = (
        "batch" in query_lower
        and any(term in query_lower for term in (
            "bad", "failed", "inspection", "quality", "defect", "substandard",
            "damaged", "rejected",
        ))
    )
    has_component_context = (
        any(term in query_lower for term in ("component", "components"))
        and any(term in query_lower for term in (
            "batch", "inspection", "units", "parts", "equipment", "physical",
        ))
    )
    has_shipment_context = (
        "shipment" in query_lower
        and any(term in query_lower for term in (
            "short by", "wrong quantity", "units", "damaged", "goods",
            "material", "parts", "consignment",
        ))
    )
    has_delivery_context = (
        "delivery" in query_lower
        and any(term in query_lower for term in (
            "refused delivery", "rejected delivery", "delivery of goods",
            "delivered goods", "goods delivered", "wrong quantity", "short by",
        ))
    )
    has_model_context = "wrong model" in query_lower
    has_received_variant_context = (
        "received" in query_lower
        and any(term in query_lower for term in (
            "wrong model", "wrong item", "wrong colour", "wrong color", "wrong goods",
        ))
    )
    has_quantity_context = any(term in query_lower for term in (
        "wrong quantity", "short by", "shortage", "short shipment",
        "quantity shortage", "pieces arrived", "units arrived",
    ))
    has_material_context = (
        "material" in query_lower
        and any(term in query_lower for term in (
            "batch", "shipment", "parts", "goods", "specification",
            "specifications", "delivered", "units", "quantity", "purchase order",
            "buyer", "seller", "vendor", "supplier", "manufacturer",
        ))
    )
    has_goods_context = (
        has_core_goods_context
        or has_product_context
        or has_material_context
        or has_batch_context
        or has_component_context
        or has_shipment_context
        or has_delivery_context
        or has_model_context
        or has_received_variant_context
        or has_quantity_context
    )
    return has_quality_or_rejection_fact and has_goods_context


def _should_enforce_requirement(text: str, requirement_type: str, query: str) -> bool:
    lower = text.lower()
    q = query.lower()
    if "registration of births and deaths" in lower:
        # Lay users often shorten "birth certificate" to "birth cert". Keep
        # the controlling civil-registration authority active instead of
        # falling through to a generic identity/RTI answer.
        return _has(q, (
            "birth certificate", "birth cert", "birth registration",
            "born at home", "home birth", "death certificate", "death cert",
            "death registration",
        ))
    if (
        "sale of goods" in lower
        and any(term in lower for term in ("quality", "rejection", "acceptance", "price deduction"))
    ):
        return _sale_of_goods_quality_dispute_context(q)
    if "state rera rules and filing procedure" in lower:
        return _material_state_context_requirement(lower, q)
    if "state labour-department notification/appeal route" in lower:
        return _material_state_context_requirement(lower, q)
    if _has(lower, (
        "state-specific witch-hunting statute",
        "state witch-hunting law",
        "witch-hunting state act",
    )):
        # A named state changes the offence and source pack. Do not let a
        # generic Assam/default pack satisfy a Jharkhand, Bihar, or other
        # state-specific question; the exact state source must be present.
        witch_context = _has(q, (
            "witch", "witch-hunting", "witch hunting", "daain", "daayan",
            "dayan", "daini", "tonhi", "tonahi",
        ))
        named_state = _has(q, (
            "andhra pradesh", "arunachal pradesh", "assam", "bihar",
            "chhattisgarh", "goa", "gujarat", "haryana", "himachal pradesh",
            "jharkhand", "karnataka", "kerala", "madhya pradesh", "maharashtra",
            "manipur", "meghalaya", "mizoram", "nagaland", "odisha", "orissa",
            "punjab", "rajasthan", "sikkim", "tamil nadu", "telangana",
            "tripura", "uttar pradesh", "uttarakhand", "west bengal",
            "delhi", "jammu and kashmir", "ladakh", "ranchi", "chaibasa",
            "gumla", "khunti", "simdega", "singhbhum", "barpeta", "guwahati",
            "dibrugarh", "jorhat", "raipur", "bastar",
        ))
        return witch_context and named_state
    if "state caste-certificate issuance and appeal rules" in lower:
        # A pending/status question can safely receive constitutional and
        # record-request intake. An appeal, forum, or deadline question cannot
        # be answered from national sources because the State rule/order
        # controls the authority and time limit.
        return (
            _has(q, (
                "caste certificate", "caste cert", "sc certificate", "st certificate",
                "sc cert", "st cert", "community certificate",
                "scheduled caste", "scheduled tribe", "sc/st", "sc st",
            ))
            and _has(q, (
                "appeal", "appeal forum", "which authority", "what authority",
                "where do i appeal", "where can i appeal", "deadline", "time limit",
                "how many days", "challenge", "review", "rejected", "refused",
                "denied", "rejection order", "refusal order",
            ))
        )
    if _has(lower, (
        "state education rules",
        "school board or education-record correction rules",
        "school board",
        "education-record correction rules",
        "state caste certificate",
        "state caste-certificate",
    )):
        return _contains_concrete_authority_name(lower) or _material_state_context_requirement(lower, q)
    contextual_exception = _has(lower, (
        "loan documents and rbi restructuring/settlement guidance",
        "gst refund/bank operation records",
        "cooperative-bank grievance route and state cooperative-society forum",
        "victim-compensation and dlsa procedure",
        "victim compensation and dlsa procedure",
    ))
    if contextual_exception:
        concrete_blob = lower.replace("gst refund/bank operation records", "")
        if not _contains_concrete_authority_name(concrete_blob):
            return False
    if "juvenile justice" in lower and "adoption" in lower:
        return _has_adoption_source_context(q)
    if "indian succession act" in lower and _has(q, ("muslim", "sunni", "shariat")):
        return False
    if "information technology act" in lower and _has(lower, ("platform", "dms", "online accounts")):
        return _has(q, (
            "cyber", "online", "instagram", "insta", "whatsapp", "telegram",
            "facebook", "dm", "dms", "message", "account", "profile",
            "deepfake", "otp", "upi", "data",
        ))
    if _has_statute_alias(lower, ("bnss", "crpc")) and _has(lower, (
        "protection, complaint", "complaint, and maintenance procedure",
        "complaint and maintenance procedure",
    )):
        return _has_family_police_help_needed_context(q)
    if (
        _has_statute_alias(lower, ("bnss", "crpc"))
        and "complaint procedure" in lower
        and "wage complaint" in q
        and not _has(q, (
            "police", "fir", "thana", "station", "magistrate",
            "criminal complaint", "police complaint", "refused fir",
            "not registering", "arrest", "case filed", "file case",
        ))
    ):
        return False
    if "family law statute" in lower or "personal law" in lower:
        return _has(q, _FAMILY_PERSONAL_LAW_TRIGGER_TERMS)
    if "maintenance" in lower and _has(lower, ("bnss", "crpc")):
        return _has(q, _MAINTENANCE_TRIGGER_TERMS)
    if (
        ("hindu marriage act" in lower or "special marriage act" in lower)
        and _has(lower, ("voidable", "matrimonial relief", "marriage", "section 12", "sec 12"))
    ):
        return _has_marriage_validity_source_context(q)
    if "only where a separate fir" in lower or "criminal complaint exists" in lower:
        return _has_separate_criminal_case_context(q)
    if _has_statute_alias(lower, ("bns", "ipc")) and _has(lower, (
        "marital-exception", "marital exception", "sexual-offence", "sexual offence",
    )):
        return _has_separate_criminal_case_context(q)
    if "labour/dlsa grievance route" in lower or "labour dlsa grievance route" in lower:
        return _has(q, (
            "dlsa", "legal aid", "free lawyer", "cannot afford lawyer",
            "no lawyer", "legal help", "nalsa", "slsa",
        ))
    if "victim-compensation" in lower or "victim compensation" in lower:
        return _has(q, (
            "acid attack", "acid thrown", "burn", "burns", "injury", "injured",
            "hospital", "treatment", "compensation", "medical bill",
        ))
    if "adult criminal-procedure wrapper" in lower and _has(q, (
        "juvenile", "minor", "16 yr", "16 year", "17 yr", "17 year",
        "observation home", "school id", "age proof",
    )):
        return False
    if requirement_type == "fact_or_document_requirement":
        return _contains_concrete_authority_name(lower)
    if requirement_type == "procedural_or_local_source":
        if _material_state_context_requirement(lower, q):
            return True
        return _contains_concrete_authority_name(lower)
    if requirement_type != "conditional_authority":
        return True
    if "limitation act" in lower:
        return _has_limitation_trigger_context(q)
    if "commercial courts" in lower and _has(lower, ("where", "if", "when", "12a", "pre-institution", "pre institution")):
        return _has(q, (
            "commercial suit", "commercial dispute", "commercial court",
            "commercial division", "pre institution", "pre-institution",
            "section 12a", "sec 12a", "mediation", "injunction",
            "interim relief", "damages", "court route",
        ))
    if "mediation act" in lower:
        return _has(q, (
            "mediation", "pre litigation", "pre-litigation",
            "pre institution", "pre-institution", "section 12a",
            "sec 12a", "commercial suit", "commercial dispute",
        ))
    if "copyright" in lower and _has(lower, ("where", "if", "when", "copyright", "counter-notice", "counter notice")):
        trademark_only = _has(q, ("trademark", "trade mark", "brand name", "brand", "passing off")) and not _has(q, (
            "copyright", "copying", "piracy", "software license", "unlicensed",
            "dmca", "creative", "artwork", "logo", "photo", "image", "video",
            "content",
        ))
        if trademark_only:
            return False
        return _has(q, (
            "copyright", "copying", "piracy", "software license", "unlicensed",
            "dmca", "counter notice", "counter-notice", "creative", "artwork",
            "logo", "photo", "image", "video", "content",
        ))
    if "pesa" in lower and "forest rights" in lower:
        return _has_pesa_trigger_context(q) or _has_fra_trigger_context(q)
    if "pesa" in lower:
        return _has_pesa_trigger_context(q)
    if "forest conservation act" in lower:
        return _has(q, (
            "forest land", "forest clearance", "forest diversion",
            "reserved forest", "protected forest", "non-forest use",
        ))
    if "forest rights" in lower:
        return _has_fra_trigger_context(q)
    if _has_statute_alias(lower, ("bns", "ipc")) and _has(lower, (
        "physical assault", "stalking", "threat", "threats", "hurt",
        "intimidation", "confinement", "coercion", "where assault",
        "where physical", "where threats",
    )):
        if _has_negated_family_criminal_force_context(q):
            return False
        return _has_physical_stalking_threat_context(q)
    if _has_statute_alias(lower, ("bnss", "crpc")) and "where police help is needed" in lower:
        return _has_family_police_help_needed_context(q)
    if _has_statute_alias(lower, ("bns", "ipc")) and _has(lower, (
        "offence provisions where relevant",
        "offence provisions where applicable",
        "provisions where relevant",
        "provisions where applicable",
        "where relevant",
        "where applicable",
    )):
        if _has_police_threatening_arrest_without_offence_context(q):
            return False
        return _has_criminal_offence_context(q)
    if "based on incident date" in lower and _has(lower, ("bns", "bnss", "ipc", "crpc")):
        has_procedure_code = _has_statute_alias(lower, ("bnss", "crpc"))
        has_offence_code = _has_statute_alias(lower, ("bns", "ipc"))
        if has_procedure_code and not has_offence_code:
            # A cheque-bounce route needs the complaint/notice procedure even
            # when the user has not mentioned police, FIR, or arrest. Without
            # this branch a bare NI Act passage could incorrectly clear the
            # date-dependent BNSS/CrPC obligation.
            if _has(q, (
                "cheque", "cheques", "dishonour", "dishonored", "bounced",
                "negotiable instruments", "section 138", "138 notice",
            )):
                return True
            return _has_criminal_process_context(q) or _has_criminal_offence_context(q)
        if has_offence_code and not has_procedure_code:
            if _has_police_threatening_arrest_without_offence_context(q):
                return False
            if _has(lower, ("breach of trust", "criminal breach of trust")):
                return _has_criminal_offence_context(q) or _has_streedhan_or_entrustment_context(q)
            if _has(lower, ("trafficking", "exploitation")):
                return _has_criminal_offence_context(q) or _has_trafficking_exploitation_context(q)
            return _has_criminal_offence_context(q)
        return _has_criminal_process_context(q) or _has_criminal_offence_context(q)
    if "pocso" in lower or "protection of children from sexual offences" in lower:
        return _has(q, ("pocso", "minor", "child", "girl", "boy", "under 18", "17 year", "16 year", "15 year", "14 year"))
    if _has(lower, ("maternity benefit", "maternity")):
        return _has(q, ("maternity", "pregnan", "delivery", "delivered", "baby", "leave"))
    if _has(lower, ("epf", "provident")):
        return _has(q, ("epf", "pf", "provident", "uan", "pension"))
    if "industrial disputes" in lower:
        return _has(q, ("termination", "terminated", "retrench", "fired", "labour court", "factory closed", "no notice"))
    if "indian partnership" in lower:
        return _has(q, ("partner", "partnership", "firm", "llp"))
    if "aadhaar" in lower:
        if _has(lower, ("only where", "uidai records are directly involved", "authentication")):
            return _has(q, (
                "uidai", "aadhaar authentication", "aadhar authentication",
                "authentication failed", "authentication", "biometric",
                "ekyc", "e-kyc", "kyc", "identity mismatch",
                "aadhaar used", "aadhar used", "aadhaar issued",
                "aadhar issued", "aadhaar linked", "aadhar linked",
            ))
        return _has(q, ("aadhaar", "aadhar", "uidai", "kyc", "biometric", "identity mismatch"))
    if "consumer protection" in lower:
        if _has(lower, ("bank", "service deficiency", "service-deficiency")):
            return _has(q, (
                "bank", "atm", "upi", "card", "account", "debit", "deducted",
                "wrongly deducted", "failed transaction", "money not credited",
                "chargeback", "refund", "customer care", "complaint", "grievance",
                "service deficiency", "service-deficiency",
            ))
        return _has(q, (
            "consumer", "refund", "replace", "replacement", "defect", "defective",
            "damaged", "warranty", "service deficiency", "service-deficiency",
            "company not accepting", "seller", "shop", "invoice",
        ))
    if "sale of goods" in lower:
        return _sale_of_goods_quality_dispute_context(q)
    if "indian contract" in lower:
        return _has(q, (
            "consent", "coercion", "undue influence", "authority",
            "blank paper", "thumb impression", "misrepresentation",
            "fraud", "contract", "agreement", "signed", "signature",
        ))
    if "specific relief" in lower:
        if "injunction/performance is sought" in lower:
            return _has(q, (
                "injunction", "specific performance", "performance of contract",
                "perform the contract", "restrain", "stay order",
                "interim relief", "negative covenant", "exclusive",
                "exclusivity", "declaration",
            ))
        return _has(q, ("injunction", "specific performance", "exclusivity", "exclusive", "cancel", "cancellation", "declaration", "restrain", "gift deed", "blank paper", "thumb impression", "sale deed"))
    if "transfer of property" in lower:
        return _has(q, (
            "gift", "gift deed", "settlement", "transfer paper", "property transfer",
            "transferred property", "sale deed", "lease deed", "oral gift",
            "verbally", "cancel", "cancellation", "revoke", "revocation",
        ))
    if "registration act" in lower:
        return _has(q, (
            "registration", "registered", "unregistered", "sub registrar",
            "sub-registrar", "sale deed", "gift deed", "lease deed",
            "document validity", "admissibility", "blank paper",
            "thumb impression", "property paper",
        ))
    if "inter-state migrant" in lower or "inter state migrant" in lower:
        return _has(q, (
            "inter-state", "inter state", "migrant", "came from", "brought from",
            "recruited from", "return ticket", "journey allowance", "go back home",
            "walked from", "home state", "native place",
        ))
    if "forest rights" in lower or "pesa" in lower:
        return _has_fra_trigger_context(q) or _has_pesa_trigger_context(q)
    if (
        "water (prevention and control of pollution) act" in lower
        or "water act / pollution-control" in lower
    ):
        # Environmental routes are broad, but the Water Act obligation is
        # operative only when the facts actually describe water or effluent
        # pollution. Mining, land, and blasting matters must not inherit it.
        return _has(q, (
            "water", "borewell", "effluent", "chemical", "chemicals",
            "pollution", "polluting", "factory", "discharge", "sewage",
            "waste", "contamination", "contaminated",
        ))
    if "code on social security" in lower:
        return _has(q, ("pf", "epf", "esi", "gig", "platform", "social security", "provident"))
    if "rbi" in lower or "kyc" in lower or "online-gaming" in lower:
        return _has(q, ("bank", "rbi", "kyc", "gaming", "rummy", "dream11", "account", "wallet", "upi"))
    if "medical ethics" in lower or "medical council" in lower:
        return _has(q, (
            "medical records", "case papers", "hospital records", "not giving records",
            "wrong treatment", "wrong injection", "wrong surgery", "wrong leg",
            "negligence", "medical negligence", "died", "death", "dead",
            "injury", "misconduct", "operated wrong",
        ))
    if "clinical establishments" in lower:
        if _has(q, ("tamil nadu", "tamilnadu", "chennai", "coimbatore", "madurai")):
            return False
        return _has(q, ("hospital", "doctor", "medical", "icu", "billing", "bill", "records", "negligence", "wrong surgery", "wrong leg"))
    if "prevention of corruption" in lower:
        if _has(q, (
            "no bribe", "not bribe", "not a bribe", "without bribe",
            "no cash demand", "no money demand", "no money demanded",
            "not asking money", "not asked money", "did not ask money",
            "didn't ask money", "no payment demand",
        )):
            return False
        return _has(q, (
            "bribe", "corruption", "cash", "demanding money",
            "fake job card", "fake job cards", "fake muster", "muster",
            "forged", "misappropriation", "dead people", "dead persons",
            "fake entries", "action taken report", "atr",
        ))
    if "bnss/crpc custody" in lower or ("bnss" in lower and "crpc" in lower and "custody" in lower):
        return _has(q, (
            "custody", "jail", "remand", "undertrial", "acquitted",
            "acquittal", "released", "compensation", "appeal", "bail",
        ))
    if "state prison rules" in lower or "prison manual" in lower:
        return _has(q, ("prison", "jail", "tihar", "mulaqat", "books", "furlough", "parole"))
    if "real estate" in lower or "rera" in lower:
        return _has(q, ("rera", "builder", "flat", "possession", "carpet", "project", "allotment"))
    if "bonded labour" in lower:
        return _has(q, (
            "bonded", "advance", "debt", "loan", "release certificate",
            "rehabilitation", "hostage", "not letting", "cannot leave",
            "forced to work", "document kept", "id kept", "aadhaar kept",
        ))
    if (
        "bocw cess" in lower
        or "welfare-board cess" in lower
        or "welfare board cess" in lower
        or "construction workers welfare cess" in lower
    ):
        return _has(q, (
            "cess", "fake register", "false register", "fake registers",
            "same name", "fake entry", "fake entries", "muster roll",
            "register fraud", "welfare board record", "welfare-board record",
            "cess record", "cess records",
        ))
    if "criminal-negligence" in lower or "criminal negligence" in lower:
        return _has(q, (
            "negligence", "wrong treatment", "death", "died", "dead", "injury",
            "assault", "medical negligence", "wrong injection", "wrong surgery",
        ))
    if "building and other construction" in lower or "bocw" in lower or "factories act" in lower:
        if _has(lower, ("where the workplace is a construction", "construction/building worksite")):
            return _has(q, (
                "construction", "building work", "worksite", "construction site",
                "site worker", "bocw", "builder site", "thekedar",
            ))
        return _has(q, (
            "construction", "building work", "site", "worksite", "factory",
            "plant", "boiler", "machine", "accident at work", "worker died",
            "fell from", "lost hand", "lost limb", "bocw", "cess",
            "register", "fake register", "false register", "same name",
            "welfare board", "benefit claim", "thekedar",
        ))
    if "code on wages" in lower or "minimum wage" in lower:
        if "where unpaid overtime wages are also claimed" in lower:
            return _has(q, (
                "unpaid overtime", "overtime wages", "overtime payment",
                "not paid overtime", "wages unpaid", "salary unpaid",
                "payment withheld", "wage claim", "wage dues",
            ))
        if "only if" in lower:
            return _has(q, (
                "wage", "wages", "salary", "overtime", "deduct", "deducted",
                "minimum", "full and final", "leave encash", "payment withheld",
                "unpaid dues", "not paid salary", "food deducted",
            ))
        return _has(q, ("wage", "salary", "overtime", "deduct", "minimum", "full and final", "payment"))
    if "legal services authorities" in lower or "legal aid" in lower or "dlsa" in lower:
        return _has(q, (
            "dlsa", "legal aid", "free lawyer", "legal services", "nalsa",
            "slsa", "legal help", "cannot afford lawyer", "no lawyer",
            "lawyer not coming", "jail legal aid",
        ))
    if "compound" in lower or "compoundability" in lower:
        return _has_criminal_process_context(q) or _has_criminal_offence_context(q) or _has(q, (
            "settlement", "settle", "compromise", "compound",
            "quash", "quashing", "permission",
        ))
    if "article 32" in lower:
        return _has(q, ("supreme court", "article 32", "fundamental right"))
    if "registration act only if" in lower:
        return _has(q, (
            "registration", "registered", "unregistered", "sub registrar",
            "sub-registrar", "sale deed", "gift deed", "lease deed",
            "admissibility", "document validity",
        ))
    if "bnss" in lower and "crpc" in lower and "only if" in lower:
        return _has_criminal_offence_context(q) or _has_trigger_term(q, (
            "criminal case", "criminal court", "summons in criminal",
            "warrant in criminal", "accused", "fir", "f.i.r",
            "police notice", "arrest", "arrested", "bns", "ipc",
            "bnss", "crpc",
        ))
    if _is_bns_bnss_or_ipc_crpc_requirement(lower) and _has(lower, ("cheating", "forgery", "false register", "fake register")):
        return _has(q, (
            "cheating", "forgery", "forged", "fake register", "false register",
            "fake registers", "same name", "fake entry", "false entry",
            "muster roll fraud", "fake muster", "false muster", "cess fraud",
            "fake benefit claim", "false benefit claim", "benefit fraud",
            "thekedar cheated", "contractor cheated",
        ))
    if _has_statute_alias(lower, ("bnss", "crpc")):
        return _has_criminal_process_context(q) or _has_criminal_offence_context(q)
    if _has_statute_alias(lower, ("bns", "ipc")):
        return _has_criminal_offence_context(q) or _has_physical_stalking_threat_context(q)
    if "information technology" in lower:
        return _has(q, ("cyber", "online", "instagram", "whatsapp", "telegram", "account", "deepfake", "otp", "upi", "data"))
    return False


def best_source_match(required_source: str, passages: list[dict[str, Any]], *, query: str) -> dict[str, Any] | None:
    if str(required_source or "").strip().lower() == (
        "state caste-certificate issuance and appeal rules"
    ):
        # This is an explicit production boundary, not a title-similarity
        # requirement. Until a State-specific rule/order is supplied, a
        # passage that merely repeats the label cannot prove an appeal forum
        # or deadline.
        return None
    constitution_match = _constitution_article_requirement_match(required_source, passages)
    if constitution_match is not None:
        return constitution_match
    required_lower = str(required_source or "").lower()
    query_lower = str(query or "").lower()
    is_conditional_sale_of_goods = (
        "sale of goods" in required_lower
        and any(term in required_lower for term in ("quality", "rejection", "acceptance", "price deduction"))
    )
    if is_conditional_sale_of_goods and not _sale_of_goods_quality_dispute_context(query_lower):
        # Do not let the generic Sale-of-Goods matcher below satisfy a
        # conditional quality/rejection authority for plain arrears or an
        # unrelated use of words such as "quality" or "rejected".
        return None
    if is_conditional_sale_of_goods:
        # This conditional source is intentionally query-aware.  A Sale of
        # Goods passage can satisfy a quality/rejection obligation when the
        # user raised that fact, but must not turn an unrelated overdue-payment
        # answer into a falsely complete route.
        for item in passages or []:
            if not isinstance(item, dict):
                continue
            title_blob = _blob(
                item.get("title"), item.get("document_id"), item.get("statute_short"),
            )
            anchor = str(item.get("anchor") or "").lower()
            if "sale of goods" not in title_blob and "sale-of-goods-1930" not in anchor:
                continue
            if any(
                _plan_anchor_matches(anchor, section)
                for section in ("/sec-31", "/sec-32", "/sec-55", "/sec-56")
            ):
                return item
        # A triggered conditional requirement still needs one of its reviewed
        # Sale-of-Goods sections; a different Act section is not equivalent.
        return None
    if _is_hard_composite_requirement(required_source):
        return _composite_route_source_match(required_source, passages, query=query)
    composite_match = _composite_route_source_match(required_source, passages, query=query)
    if composite_match is not None:
        return composite_match
    if _is_dual_regime_requirement(required_source):
        return _dual_regime_source_match(required_source, passages, query=query)
    tokens = _source_tokens(required_source)
    best: tuple[float, dict[str, Any] | None] = (0.0, None)
    for item in passages or []:
        if not isinstance(item, dict):
            continue
        blob = _item_blob(item)
        if _canonical_match(
            required_source,
            blob,
            query=query,
            passage_text=_passage_identity_text(item),
        ):
            return item
        if not tokens:
            continue
        score = _coverage_score(tokens, blob)
        if score > best[0]:
            best = (score, item)
    if _is_hard_canonical_requirement(required_source):
        return None
    if not tokens:
        return None
    return best[1] if best[0] >= _threshold(tokens) else None


def source_gap_kind(required_source: str, *, query: str = "") -> str:
    source_blob = _blob(required_source)
    if _has(source_blob, ("employees provident", "epf", "provident fund", "code on social security")):
        return "national_labor_source_gap"
    if _has(source_blob, ("bns", "bnss", "ipc", "crpc", "pocso", "ndps", "uapa", "criminal")):
        return "national_criminal_source_gap"
    if _has(source_blob, ("gst", "cgst", "customs", "income tax", "tds", "tcs", "icegate")):
        return "national_tax_source_gap"
    if _has(source_blob, ("constitution", "article 14", "article 21", "article 22", "article 226")):
        return "constitutional_authority_gap"
    if _has(source_blob, (
        "state", "local", "municipal", "municipality", "panchayat",
        "scheduled area", "scheduled areas", "tribal land", "witch",
        "daain", "dayan", "tonahi", "tonhi", "cattle preservation",
        "excise", "bhang", "shops and establishments",
        "prison rules", "rent-control", "tenancy law",
    )):
        return "state_or_local_authority_gap"
    blob = _blob(required_source, query)
    if _has(blob, ("gst", "cgst", "customs", "income tax", "tds", "tcs", "icegate")):
        return "national_tax_source_gap"
    if _has(blob, ("bns", "bnss", "ipc", "crpc", "pocso", "ndps", "uapa", "criminal")):
        return "national_criminal_source_gap"
    if _has(blob, ("constitution", "article 14", "article 21", "article 22", "article 226")):
        return "constitutional_authority_gap"
    return "national_statute_retrieval_gap"


def _canonical_match(
    required_source: str,
    item_blob: str,
    *,
    query: str,
    passage_text: str | None = None,
) -> bool:
    lower = required_source.lower()
    q = query.lower()
    # Enforce explicit Act/Code section requirements before the legacy
    # statute-specific branches below. Those branches intentionally support
    # title-level requirements, but their broad anchor lists must not let a
    # neighboring section (for example 35A for Section 35) clear a concrete
    # section obligation.
    explicit_sections = re.findall(
        r"\b(?:section|sec|s)\.?\s*"
        r"([0-9]+(?:\([0-9a-z]+\))?[a-z]?)(?![0-9a-z])",
        lower,
    )
    # HMA has a broad legacy matcher for Section 13 divorce grounds. Keep an
    # explicitly alphanumeric requirement such as Section 13A on the strict
    # identity path so that a Section 13 fragment cannot satisfy it later.
    if (
        "hindu marriage act" in lower
        and any(section[-1:].isalpha() for section in explicit_sections)
        and _required_title_matches_item(lower, item_blob)
    ):
        return any(
            _section_anchor_matches(item_blob, section, passage_text=passage_text)
            for section in explicit_sections
        )
    if (
        explicit_sections
        and not (
            "hindu marriage act" in lower
            and any(section == "13" for section in explicit_sections)
        )
        # Composite alternatives such as "Section 67B / 66E / 67A" have
        # their own query-aware matcher below; do not truncate them to the
        # first section token here.
        and not re.search(
            r"\b(?:section|sec|s)\.?\s*[0-9]+[a-z]?\b[^.]{0,80}/\s*[0-9]",
            lower,
        )
        and _required_title_matches_item(lower, item_blob)
    ):
        return any(
            _section_anchor_matches(item_blob, section, passage_text=passage_text)
            for section in explicit_sections
        )
    if (
        ("employees' provident" in lower or "employees provident" in lower or "epf" in lower)
        and "code on social security" in lower
    ):
        epf_match = ("provident" in item_blob or "epf" in item_blob) and _has_any_exact_anchor(
            item_blob,
            ("sec-6a", "/sec-6a"),
        )
        social_security_match = ("social security" in item_blob or "social-security" in item_blob) and _has_any_exact_anchor(
            item_blob,
            ("sec-15", "/sec-15"),
        )
        return epf_match or social_security_match
    if "code on social security" in lower:
        if _has(lower, ("contribution", "classification")):
            return ("social security" in item_blob or "social-security" in item_blob) and (
                _has_any_anchor(item_blob, (
                    "sec-15", "sec-31", "sec-125", "sec-126",
                    "sec-128", "sec-129", "/sec-15", "/sec-31",
                    "/sec-125", "/sec-126", "/sec-128", "/sec-129",
                ))
                or "#header" in item_blob
            )
        return ("social security" in item_blob or "social-security" in item_blob) and (
            _has_any_anchor(item_blob, (
                "sec-109", "sec-112", "sec-113",
                "/sec-109", "/sec-112", "/sec-113",
            ))
            or "#header" in item_blob
        )
    if _is_pmla_sc_precedent_requirement(lower):
        return _pmla_sc_precedent_item_matches(item_blob)
    if "bnss/crpc custody" in lower or ("bnss" in lower and "crpc" in lower and "custody" in lower):
        return _has(item_blob, (
            "bnss", "bharatiya nagarik", "crpc", "code of criminal procedure",
            "criminal procedure",
        )) and _has_any_anchor(item_blob, (
            "sec-167", "sec-187", "sec-436a", "sec-436-a", "sec-479",
            "sec-50", "sec-57", "sec-397", "sec-374", "/sec-167",
            "/sec-187", "/sec-436a", "/sec-436-a", "/sec-479",
            "/sec-50", "/sec-57", "/sec-397", "/sec-374",
        ))
    if "dowry prohibition" in lower:
        return "dowry prohibition" in item_blob and _has_any_anchor(item_blob, ("sec-2", "sec-3", "sec-4", "sec-6", "sec-10", "/sec-2", "/sec-3", "/sec-4", "/sec-6", "/sec-10"))
    if "clinical establishments" in lower or "clinical-establishment" in lower:
        return ("clinical establishments" in item_blob or "clinical-establishments" in item_blob) and _has_any_anchor(item_blob, ("sec-12", "sec-42", "/sec-12", "/sec-42"))
    if "mental healthcare act" in lower or "mental-healthcare" in lower:
        if "mental healthcare" not in item_blob and "mental-healthcare" not in item_blob:
            return False
        privacy_context = _has(lower, ("confidential", "privacy", "therapist", "records", "communication"))
        confinement_context = _has(q, (
            "chain", "chains", "chained", "tied", "confined", "locked in room",
            "kept locked", "ill treated", "ill-treated", "neglected",
        ))
        if privacy_context:
            return _has_any_anchor(item_blob, (
                "sec-23", "sec-24", "sec-25", "sec-43",
                "/sec-23", "/sec-24", "/sec-25", "/sec-43",
            ))
        if confinement_context:
            return _has_any_anchor(item_blob, (
                "sec-20", "sec-94", "sec-97", "sec-100",
                "/sec-20", "/sec-94", "/sec-97", "/sec-100",
            ))
        return True
    if "representation of the people" in lower or "voter-list" in lower or "voter list" in lower:
        return (
            "representation of the people" in item_blob
            or "rpa-1950" in item_blob
            or "rpa-1951" in item_blob
        ) and _has_any_anchor(item_blob, (
            "sec-19", "sec-22", "sec-23", "sec-24", "sec-62",
            "/sec-19", "/sec-22", "/sec-23", "/sec-24", "/sec-62",
        ))
    if "limitation act" in lower:
        return "limitation" in item_blob and _has_any_anchor(item_blob, ("sec-3", "sec-5", "sec-14", "/sec-3", "/sec-5", "/sec-14"))
    charge_sheet_or_discharge_context = _has(
        lower,
        (
            "charge-sheet", "chargesheet", "charge sheet", "police report",
            "summons", "discharge",
        ),
    )
    requires_bnss = _has_statute_alias(lower, ("bnss", "bharatiya nagarik"))
    requires_crpc = _has_statute_alias(lower, ("crpc", "criminal procedure"))
    if (
        (requires_bnss or requires_crpc)
        and _has(lower, ("bail", "arrest"))
        and not charge_sheet_or_discharge_context
    ):
        anchors = _bail_arrest_safeguard_anchor_terms(q, lower)
        matches_required_regime = (
            (requires_bnss and _has_statute_alias(item_blob, ("bnss", "bharatiya nagarik")))
            or (requires_crpc and _has_statute_alias(item_blob, ("crpc", "code of criminal procedure", "criminal procedure")))
        )
        return matches_required_regime and _has_any_anchor(item_blob, anchors)
    if "negotiable instruments act" in lower or "negotiable instrument" in lower:
        if "negotiable instruments" not in item_blob:
            return False
        sections = re.findall(r"\b(?:section|sec|s)\.?\s*([0-9]+[a-z]?)\b", lower)
        if sections:
            return any(
                _section_anchor_matches(item_blob, section, passage_text=passage_text)
                for section in sections
            )
        return _has_any_anchor(
            item_blob,
            ("sec-138", "sec-141", "sec-142", "/sec-138", "/sec-141", "/sec-142"),
        )
    if _single_statute_section_match(lower, item_blob, passage_text=passage_text):
        return True
    if "indian contract act" in lower or "contract act" in lower:
        if "indian contract" not in item_blob and "contract act" not in item_blob:
            return False
        if _has(lower, ("consent", "coercion", "undue", "fraud", "void", "authority")):
            return _has_any_anchor(item_blob, (
                "sec-14", "sec-15", "sec-16", "sec-17", "sec-18", "sec-19",
                "sec-19-a", "sec-19-b", "/sec-14", "/sec-15", "/sec-16",
                "/sec-17", "/sec-18", "/sec-19", "/sec-19-a", "/sec-19-b",
            ))
        return _has_any_anchor(item_blob, ("sec-37", "sec-73", "sec-74", "/sec-37", "/sec-73", "/sec-74"))
    if "registration act" in lower:
        return "registration" in item_blob and _has_any_anchor(item_blob, ("sec-17", "sec-23", "sec-49", "/sec-17", "/sec-23", "/sec-49"))
    if "specific relief act" in lower:
        return "specific relief" in item_blob and _has_any_anchor(item_blob, (
            "sec-10", "sec-14", "sec-16", "sec-20", "sec-21",
            "sec-31", "sec-34", "sec-38", "sec-42",
            "/sec-10", "/sec-14", "/sec-16", "/sec-20", "/sec-21",
            "/sec-31", "/sec-34", "/sec-38", "/sec-42",
        ))
    if "transfer of property act" in lower:
        return "transfer of property" in item_blob and _has_any_anchor(item_blob, (
            "sec-44", "sec-45", "sec-54", "sec-105", "sec-106", "sec-111",
            "sec-122", "sec-126", "/sec-44", "/sec-45", "/sec-54", "/sec-105",
            "/sec-106", "/sec-111", "/sec-122", "/sec-126",
        ))
    if "consumer protection" in lower:
        return "consumer protection" in item_blob and _has_any_anchor(item_blob, ("sec-2", "sec-35", "sec-38", "sec-39", "/sec-2", "/sec-35", "/sec-38", "/sec-39"))
    if "mgnrega" in lower or "mahatma gandhi national rural employment guarantee" in lower:
        if not (
            "mgnrega" in item_blob
            or "mahatma gandhi national rural employment guarantee" in item_blob
            or "mgnrega-2005" in item_blob
        ):
            return False
        social_audit_context = _has(q, (
            "social audit", "social-audit", "gram sabha", "fake muster",
            "fake job card", "fake job cards", "fake attendance",
            "false entry", "false entries", "fake entry", "fake entries",
            "dead people", "dead persons",
            "misappropriation", "forged muster",
        ))
        if social_audit_context:
            anchors = (
                "sec-17", "sec-19", "sec-23", "sec-27",
                "/sec-17", "/sec-19", "/sec-23", "/sec-27",
            )
        else:
            anchors = (
                "sec-3", "sec-6", "sec-7", "sec-15", "sec-17",
                "sec-19", "sec-23", "sec-35", "/sec-3", "/sec-6",
                "/sec-7", "/sec-15", "/sec-17", "/sec-19", "/sec-23",
                "/sec-35",
            )
        return _has_any_anchor(item_blob, anchors)
    if (
        "prevention of corruption" in lower
        and "bns" in lower
    ):
        bns_match = (
            _has_statute_alias(item_blob, ("bns", "bharatiya nyaya"))
            and _has_any_anchor(item_blob, (
                "sec-318", "sec-336", "sec-340", "/sec-318", "/sec-336", "/sec-340",
            ))
        )
        pca_match = (
            "prevention of corruption" in item_blob
            and _has_any_anchor(item_blob, (
                "sec-7", "sec-8", "sec-13", "/sec-7", "/sec-8", "/sec-13",
            ))
        )
        return bns_match or pca_match
    if "prevention of corruption" in lower:
        return "prevention of corruption" in item_blob and _has_any_anchor(item_blob, ("sec-7", "sec-8", "sec-13", "/sec-7", "/sec-8", "/sec-13"))
    if "bnss 2023 arrest" in lower or "bnss arrest" in lower:
        return _has(item_blob, ("bnss", "bharatiya nagarik")) and _has_any_anchor(item_blob, (
            "sec-35", "sec-47", "sec-48", "sec-57", "sec-58", "sec-187",
            "/sec-35", "/sec-47", "/sec-48", "/sec-57", "/sec-58", "/sec-187",
        ))
    if "crpc 1973 arrest" in lower or "crpc arrest" in lower:
        return _has(item_blob, ("crpc", "code of criminal procedure", "criminal procedure")) and _has_any_anchor(item_blob, (
            "sec-41", "sec-50", "sec-56", "sec-57", "sec-160", "sec-167",
            "/sec-41", "/sec-50", "/sec-56", "/sec-57", "/sec-160", "/sec-167",
        ))
    if "cgst" in lower or "goods and services tax" in lower or "gst" in lower:
        if "rule 86b" in lower or "86b" in lower:
            return _cgst_rule_86b_item_matches(item_blob)
        return ("cgst" in item_blob or "goods and services tax" in item_blob) and _has_any_anchor(item_blob, (
            "sec-16", "sec-22", "sec-24", "sec-29", "sec-47", "sec-73",
            "sec-67", "sec-74", "sec-75", "sec-49", "sec-49a", "sec-49b",
            "/sec-16", "/sec-22", "/sec-24", "/sec-29", "/sec-47",
            "/sec-49", "/sec-49a", "/sec-49b", "/sec-67", "/sec-73",
            "/sec-74", "/sec-75",
        ))
    if "customs act" in lower or _has(lower, ("icegate", "import/export", "drawback", "classification", "valuation", "svb")):
        return _customs_requirement_matches(lower, item_blob, q)
    if "unlawful activities" in lower or "uapa" in lower:
        return (
            ("unlawful activities" in item_blob or "uapa" in item_blob)
            and _has_any_anchor(item_blob, ("sec-43d", "/sec-43d"))
        )
    if "hindu marriage act" in lower and "special marriage act" in lower:
        if re.search(r"\b(?:section|sec|s)\.?\s*13\b", lower):
            hma_section_13 = (
                ("hindu marriage" in item_blob or "hindu-marriage" in item_blob)
                and _has_hindu_marriage_section_13_ground_anchor(item_blob)
            )
            sma_divorce = (
                ("special marriage" in item_blob or "special-marriage" in item_blob)
                and _has_any_exact_anchor(item_blob, ("sec-27", "/sec-27"))
            )
            return hma_section_13 or sma_divorce
        if re.search(r"\b(?:section|sec|s)\.?\s*12\b", lower) or "voidable" in lower:
            hma_voidable = (
                ("hindu marriage" in item_blob or "hindu-marriage" in item_blob)
                and _has_any_exact_anchor(item_blob, ("sec-12", "/sec-12"))
            )
            sma_voidable = (
                ("special marriage" in item_blob or "special-marriage" in item_blob)
                and _has_any_exact_anchor(item_blob, ("sec-24", "sec-25", "/sec-24", "/sec-25"))
            )
            return hma_voidable or sma_voidable
        hma_match = (
            ("hindu marriage" in item_blob or "hindu-marriage" in item_blob)
            and (
                _has_any_exact_anchor(item_blob, ("sec-12", "/sec-12"))
                or _has_any_anchor(item_blob, (
                    "sec-9", "sec-13", "sec-13b", "sec-13-b", "sec-24",
                    "sec-25", "sec-26", "/sec-9", "/sec-13", "/sec-13b",
                    "/sec-13-b", "/sec-24", "/sec-25", "/sec-26",
                ))
            )
        )
        sma_match = (
            ("special marriage" in item_blob or "special-marriage" in item_blob)
            and _has_any_anchor(item_blob, (
                "sec-24", "sec-25", "sec-27", "/sec-24", "/sec-25", "/sec-27",
            ))
        )
        return hma_match or sma_match
    if "hindu marriage act" in lower or "hindu marriage" in lower:
        if "hindu marriage" not in item_blob and "hindu-marriage" not in item_blob:
            return False
        if "section 13b" in lower or "sec 13b" in lower or "13b" in lower:
            return _has_any_exact_anchor(item_blob, ("sec-13b", "sec-13-b", "/sec-13b", "/sec-13-b"))
        if re.search(r"\b(?:section|sec|s)\.?\s*13\b", lower):
            return _has_hindu_marriage_section_13_ground_anchor(item_blob)
        if re.search(r"\b(?:section|sec|s)\.?\s*12\b", lower):
            return _has_any_exact_anchor(item_blob, ("sec-12", "/sec-12"))
        return _has_any_anchor(item_blob, (
            "sec-9", "sec-12", "sec-13", "sec-13b", "sec-13-b",
            "sec-24", "sec-25", "sec-26", "/sec-9", "/sec-12",
            "/sec-13", "/sec-13b", "/sec-13-b", "/sec-24",
            "/sec-25", "/sec-26",
        ))
    if "family courts act" in lower or "family court" in lower:
        return (
            "family courts" in item_blob or "family-courts" in item_blob
        ) and _has_any_anchor(item_blob, ("sec-7", "sec-8", "/sec-7", "/sec-8"))
    if "medical/vulnerability bail" in lower or ("vulnerability" in lower and "bail" in lower):
        return (
            (_has(item_blob, ("constitution",)) and _has_any_exact_anchor(item_blob, ("sec-21", "/sec-21")))
            or (
                _has(item_blob, ("bnss", "bharatiya nagarik", "crpc", "code of criminal procedure", "criminal procedure"))
                and _has_any_exact_anchor(item_blob, (
                    "sec-437", "sec-480", "sec-483",
                    "/sec-437", "/sec-480", "/sec-483",
                ))
            )
        )
    if "legal services authorities act" in lower or "legal aid" in lower or "dlsa" in lower:
        return "legal services authorities" in item_blob and _has_any_anchor(item_blob, ("sec-9", "sec-12", "sec-13", "sec-21", "/sec-9", "/sec-12", "/sec-13", "/sec-21"))
    if "aadhaar act" in lower:
        return ("aadhaar" in item_blob or "unique identification" in item_blob) and _has_any_anchor(item_blob, (
            "sec-7", "sec-8", "sec-29", "sec-59",
            "/sec-7", "/sec-8", "/sec-29", "/sec-59",
        ))
    if "right to information" in lower or re.search(r"\brti\b", lower):
        if not ("right to information" in item_blob or re.search(r"\brti\b", item_blob)):
            return False
        sections = re.findall(r"\b(?:section|sec|s)\.?\s*([0-9]+[a-z]?)\b", lower)
        if sections:
            return any(
                _section_anchor_matches(item_blob, section, passage_text=passage_text)
                for section in sections
            )
        return _has_any_anchor(item_blob, ("sec-6", "sec-7", "sec-19", "/sec-6", "/sec-7", "/sec-19"))
    if "national food security" in lower or re.search(r"\bration\b", lower):
        return "national food security" in item_blob and _has_any_anchor(item_blob, ("sec-3", "sec-12", "sec-14", "sec-15", "/sec-3", "/sec-12", "/sec-14", "/sec-15"))
    if "forest rights act" in lower:
        return ("forest rights" in item_blob or "scheduled tribes and other traditional forest dwellers" in item_blob or "fra-2006" in item_blob) and (
            "#header" in item_blob
            or _has_any_anchor(item_blob, ("sec-3", "sec-4", "sec-5", "sec-6", "/sec-3", "/sec-4", "/sec-5", "/sec-6"))
        )
    if "pesa act" in lower or ("pesa" in lower and "gram sabha" in lower):
        return ("pesa" in item_blob or "panchayats" in item_blob) and _has_any_anchor(item_blob, ("sec-4", "/sec-4"))
    if "bonded labour" in lower:
        return "bonded labour" in item_blob and _has_any_anchor(item_blob, ("sec-4", "sec-10", "sec-12", "/sec-4", "/sec-10", "/sec-12"))
    if "inter-state migrant" in lower or "inter state migrant" in lower:
        return ("inter-state migrant" in item_blob or "inter state migrant" in item_blob) and _has_any_anchor(item_blob, ("sec-6", "sec-12", "sec-14", "/sec-6", "/sec-12", "/sec-14"))
    if "industrial disputes" in lower:
        return "industrial disputes" in item_blob and _has_any_anchor(item_blob, ("sec-2a", "sec-2-a", "sec-10", "sec-25f", "sec-25-f", "/sec-2a", "/sec-2-a", "/sec-10", "/sec-25f", "/sec-25-f"))
    if (
        (
            "bocw act" in lower
            and "factories act" in lower
        )
        or "bocw act 1996 / factories act" in lower
    ):
        return (
            (
                "building and other construction workers" in item_blob
                or "bocw-1996" in item_blob
            )
            and _has_any_anchor(item_blob, (
                "sec-12", "sec-13", "sec-14", "sec-39", "sec-40", "sec-44",
                "/sec-12", "/sec-13", "/sec-14", "/sec-39", "/sec-40", "/sec-44",
            ))
        ) or (
            ("factories act" in item_blob or "factories-1948" in item_blob)
            and _has_any_anchor(item_blob, (
                "sec-7a", "sec-40", "sec-41", "sec-41b", "sec-41c",
                "sec-87", "sec-88", "sec-92", "sec-111",
                "/sec-7a", "/sec-40", "/sec-41", "/sec-41b", "/sec-41c",
                "/sec-87", "/sec-88", "/sec-92", "/sec-111",
            ))
        )
    if (
        "building and other construction workers act" in lower
        or "bocw act" in lower
        or "bocw registration" in lower
        or "welfare-board provisions" in lower
    ):
        return (
            "building and other construction workers" in item_blob
            or "bocw-1996" in item_blob
        ) and _has_any_anchor(item_blob, ("sec-12", "sec-13", "sec-14", "/sec-12", "/sec-13", "/sec-14"))
    if "bocw cess" in lower or "welfare-board cess" in lower or "welfare board cess" in lower or "construction workers welfare cess" in lower:
        return (
            "building and other construction workers welfare cess" in item_blob
            or "bocw cess" in item_blob
            or "bocw-cess" in item_blob
        ) and _has_any_anchor(item_blob, ("sec-3", "sec-4", "/sec-3", "/sec-4"))
    if "maternity benefit" in lower:
        return "maternity benefit" in item_blob and _has_any_anchor(item_blob, ("sec-5", "sec-12", "/sec-5", "/sec-12"))
    if "employees' provident" in lower or "employees provident" in lower or "epf" in lower:
        return ("provident" in item_blob or "epf" in item_blob) and _has_any_anchor(item_blob, ("sec-6", "sec-7a", "sec-14", "/sec-6", "/sec-7a", "/sec-14"))
    if "employees state insurance" in lower or re.search(r"\besi\b", lower):
        return ("employees state insurance" in item_blob or "esi" in item_blob) and _has_any_anchor(item_blob, ("sec-38", "sec-39", "sec-46", "/sec-38", "/sec-39", "/sec-46"))
    if "indian partnership act" in lower:
        return "partnership" in item_blob and _has_any_anchor(item_blob, ("sec-9", "sec-12", "sec-32", "sec-44", "/sec-9", "/sec-12", "/sec-32", "/sec-44"))
    if "sale of goods act" in lower:
        return "sale of goods" in item_blob and _has_any_anchor(item_blob, ("sec-11", "sec-12", "sec-31", "sec-42", "/sec-11", "/sec-12", "/sec-31", "/sec-42"))
    if "msmed act" in lower or "micro, small" in lower:
        return ("msmed" in item_blob or "micro, small" in item_blob) and _has_any_anchor(item_blob, ("sec-15", "sec-16", "sec-18", "/sec-15", "/sec-16", "/sec-18"))
    if "pwdva" in lower or "domestic violence" in lower:
        return ("domestic violence" in item_blob or "pwdva" in item_blob) and _has_any_anchor(item_blob, ("sec-3", "sec-12", "sec-18", "sec-19", "sec-20", "/sec-3", "/sec-12", "/sec-18", "/sec-19", "/sec-20"))
    if "hindu succession act" in lower:
        return "hindu succession" in item_blob and _has_any_anchor(item_blob, ("sec-6", "sec-8", "sec-10", "sec-14", "sec-15", "/sec-6", "/sec-8", "/sec-10", "/sec-14", "/sec-15"))
    if "income tax act" in lower or "income-tax act" in lower:
        if _has(lower, ("143(2)", "section 143")) or _has(q, ("143(2)", "section 143", "sec 143")):
            title_match = (
                "income tax" in item_blob
                or "income-tax" in item_blob
            ) and (
                _has(item_blob, ("section 143", "sub-section (2) of section 143"))
            )
            if title_match:
                return True
            return (
                ("income tax" in item_blob or "income-tax" in item_blob)
                and _section_anchor_matches(
                    item_blob,
                    "143",
                    passage_text=passage_text,
                )
            )
        return ("income tax" in item_blob or "income-tax" in item_blob) and _has_any_anchor(item_blob, ("sec-5", "sec-9", "sec-45", "sec-54", "sec-54f", "sec-139", "sec-143", "sec-154", "sec-195", "sec-214", "sec-234e", "sec-246a", "sec-249", "sec-250", "sec-253", "sec-254", "sec-255", "sec-80", "sec-80a", "sec-80c", "sec-80ccd", "sec-80cce", "sec-194", "sec-206c", "/sec-5", "/sec-9", "/sec-45", "/sec-54", "/sec-54f", "/sec-139", "/sec-143", "/sec-154", "/sec-195", "/sec-214", "/sec-234e", "/sec-246a", "/sec-249", "/sec-250", "/sec-253", "/sec-254", "/sec-255", "/sec-80", "/sec-80a", "/sec-80c", "/sec-80ccd", "/sec-80cce", "/sec-194", "/sec-206c"))
    if "employees compensation" in lower or "employees' compensation" in lower:
        return (
            "employees' compensation" in item_blob
            or "employees compensation" in item_blob
            or "employees-compensation" in item_blob
        ) and _has_any_anchor(item_blob, (
            "sec-3", "sec-4", "sec-4a", "sec-4-a", "sec-10", "sec-11",
            "/sec-3", "/sec-4", "/sec-4a", "/sec-4-a", "/sec-10", "/sec-11",
        ))
    if "drugs and cosmetics" in lower:
        return (
            "drugs and cosmetics" in item_blob
            or "drugs-cosmetics" in item_blob
        ) and _has_any_anchor(item_blob, (
            "sec-18", "sec-22", "sec-23", "sec-27",
            "/sec-18", "/sec-22", "/sec-23", "/sec-27",
        ))
    if "trade marks act" in lower or "trademark" in lower or "trade mark" in lower:
        return (
            "trade marks" in item_blob
            or "trade-marks" in item_blob
            or "trademark" in item_blob
        ) and _has_any_anchor(item_blob, (
            "sec-11", "sec-28", "sec-29", "sec-34", "sec-124",
            "sec-134", "sec-135", "/sec-11", "/sec-28", "/sec-29",
            "/sec-34", "/sec-124", "/sec-134", "/sec-135",
        ))
    if "rbi/kyc" in lower or ("rbi" in lower and "kyc" in lower):
        if "online-gaming" in lower or "online gaming" in lower:
            return (
                (
                    "reserve bank integrated ombudsman" in item_blob
                    or "rbi-integrated-ombudsman" in item_blob
                    or "banking regulation" in item_blob
                )
                and _has_any_anchor(item_blob, (
                    "#header", "sec-2", "sec-3", "sec-35a", "sec-35-a",
                    "/sec-2", "/sec-3", "/sec-35a", "/sec-35-a",
                ))
            ) or (
                ("prevention of money laundering" in item_blob or "pmla" in item_blob)
                and _has_any_anchor(item_blob, (
                    "sec-5", "sec-8", "sec-17", "sec-50",
                    "/sec-5", "/sec-8", "/sec-17", "/sec-50",
                ))
            ) or (
                ("public gambling" in item_blob or "online gambling" in item_blob)
                and _has_any_anchor(item_blob, (
                    "sec-3", "sec-12", "sec-13",
                    "/sec-3", "/sec-12", "/sec-13",
                ))
            ) or (
                ("information technology" in item_blob or "it-2000" in item_blob)
                and _has_any_anchor(item_blob, ("sec-79", "/sec-79"))
            )
        return (
            "reserve bank integrated ombudsman" in item_blob
            or "rbi-integrated-ombudsman" in item_blob
            or "banking regulation" in item_blob
        ) and _has_any_anchor(item_blob, (
            "#header", "sec-2", "sec-3", "sec-35a", "sec-35-a",
            "/sec-2", "/sec-3", "/sec-35a", "/sec-35-a",
        ))
    if "mines and minerals" in lower or "mmdr" in lower or "mining lease" in lower or "mineral-concession" in lower or "mineral concession" in lower:
        return (
            "mines and minerals" in item_blob
            or "mmdr" in item_blob
            or "mmdr-1957" in item_blob
        ) and _has_any_anchor(item_blob, (
            "sec-4", "sec-10", "sec-10a", "sec-10-a", "sec-10b",
            "sec-10-b", "sec-11", "sec-13", "/sec-4", "/sec-10",
            "/sec-10a", "/sec-10-a", "/sec-10b", "/sec-10-b",
            "/sec-11", "/sec-13",
        ))
    if "real estate" in lower or "rera" in lower:
        return ("real estate" in item_blob or "rera" in item_blob) and _has_any_anchor(item_blob, ("sec-11", "sec-14", "sec-18", "sec-31", "sec-34", "/sec-11", "/sec-14", "/sec-18", "/sec-31", "/sec-34"))
    if "prison rules" in lower or "prison manual" in lower:
        if _is_delhi_prison_rules_blob(item_blob) and not _has_delhi_prison_query_context(q):
            return False
        return (
            ("prison rules" in item_blob or "prison manual" in item_blob)
            or ("prisons act" in item_blob and _has_any_anchor(item_blob, ("sec-59", "/sec-59")))
        )
    if "juvenile justice" in lower:
        return ("juvenile justice" in item_blob or "jj-2015" in item_blob) and _has_any_anchor(item_blob, (
            "sec-9", "sec-12", "sec-56", "sec-57", "sec-58", "sec-59",
            "sec-62", "sec-63", "sec-94",
            "/sec-9", "/sec-12", "/sec-56", "/sec-57", "/sec-58",
            "/sec-59", "/sec-62", "/sec-63", "/sec-94",
        ))
    if "immoral traffic" in lower:
        return ("immoral traffic" in item_blob or "itpa" in item_blob) and _has_any_anchor(item_blob, ("sec-5", "sec-6", "sec-17", "/sec-5", "/sec-6", "/sec-17"))
    if (
        "prevention of atrocities" in lower
        and "rule 7" in lower
    ) or (
        "sc/st" in lower
        and "rule 7" in lower
    ):
        return (
            "prevention of atrocities" in item_blob
            or "sc-st-poa-rules" in item_blob
        ) and _has_any_anchor(item_blob, ("rule-7", "/rule-7"))
    if "public gambling" in lower:
        return "public gambling" in item_blob and _has_any_anchor(item_blob, ("sec-3", "sec-4", "sec-12", "/sec-3", "/sec-4", "/sec-12"))
    if "registration of births and deaths" in lower:
        return "registration of births" in item_blob and _has_any_anchor(item_blob, ("sec-8", "sec-12", "sec-13", "/sec-8", "/sec-12", "/sec-13"))
    if "code on social security" in lower:
        if _has(lower, ("contribution", "classification")):
            return ("social security" in item_blob or "social-security" in item_blob) and (
                _has_any_anchor(item_blob, (
                    "sec-15", "sec-31", "sec-125", "sec-126",
                    "sec-128", "sec-129", "/sec-15", "/sec-31",
                    "/sec-125", "/sec-126", "/sec-128", "/sec-129",
                ))
                or "#header" in item_blob
            )
        return ("social security" in item_blob or "social-security" in item_blob) and (_has_any_anchor(item_blob, ("sec-109", "sec-112", "sec-113", "/sec-109", "/sec-112", "/sec-113")) or "#header" in item_blob)
    if (
        ("information technology act" in lower or "it act" in lower)
        and "67b" in lower
        and not _has(lower, ("66e", "67a"))
    ):
        return (
            "information technology" in item_blob
            or "it-2000" in item_blob
        ) and _has_any_anchor(item_blob, ("sec-67b", "/sec-67b"))
    if "information technology act" in lower or "it act" in lower or "it rules" in lower:
        return ("information technology" in item_blob or "it-2000" in item_blob) and _has_any_anchor(item_blob, (
            "sec-66c", "sec-66d", "sec-66e", "sec-67", "sec-67a", "sec-67b",
            "sec-69", "sec-69a", "sec-79", "sec-90", "/sec-66c",
            "/sec-66d", "/sec-66e", "/sec-67", "/sec-67a", "/sec-67b",
            "/sec-69", "/sec-69a", "/sec-79", "/sec-90",
        ))
    if "pocso" in lower or "protection of children from sexual offences" in lower:
        return (
            "pocso" in item_blob
            or "protection of children from sexual offences" in item_blob
        ) and _has_any_anchor(item_blob, (
            "sec-13", "sec-13-a", "sec-13-b", "sec-15", "sec-19",
            "/sec-13", "/sec-13-a", "/sec-13-b", "/sec-15", "/sec-19",
        ))
    if "bns/modified" in lower:
        return False
    if lower.strip() == "bns/bnss or ipc/crpc based on incident date" or "bns/bnss or ipc/crpc based on incident date" in lower:
        return False
    if "code on wages" in lower:
        return "code on wages" in item_blob and _has_any_anchor(item_blob, (
            "sec-17", "sec-45", "sec-53", "sec-54",
            "/sec-17", "/sec-45", "/sec-53", "/sec-54",
        ))
    if "information technology act" in lower and "67b" in lower and not _has(lower, ("66e", "67a")):
        return (
            "information technology" in item_blob
            or "it-2000" in item_blob
        ) and _has_any_anchor(item_blob, ("sec-67b", "/sec-67b"))
    if "cgst" in lower and "section 67" in lower:
        return ("cgst" in item_blob or "central goods and services tax" in item_blob) and "sec-67" in item_blob
    if "income" in lower and ("206c" in lower or "tcs" in lower):
        return "income" in item_blob and ("sec-206c" in item_blob or "206c" in item_blob)
    if "commercial courts" in lower and "12a" in lower:
        return "commercial courts" in item_blob and ("sec-12a" in item_blob or "12a" in item_blob)
    if "commercial courts" in lower and _has(lower, ("pre-institution", "pre institution", "pre-litigation", "pre litigation", "mediation")):
        return "commercial courts" in item_blob and ("sec-12a" in item_blob or "12a" in item_blob)
    if "commercial courts" in lower:
        return "commercial courts" in item_blob and _has_any_anchor(item_blob, (
            "sec-2", "sec-6", "sec-7", "sec-12a", "sec-12-a",
            "/sec-2", "/sec-6", "/sec-7", "/sec-12a", "/sec-12-a",
        ))
    if "mediation act" in lower:
        return (
            "mediation act" in item_blob
            or "mediation-2023" in item_blob
        ) and _has_any_anchor(item_blob, (
            "sec-3", "sec-5", "sec-6", "sec-18", "sec-19",
            "sec-43", "/sec-3", "/sec-5", "/sec-6",
            "/sec-18", "/sec-19", "/sec-43",
        ))
    if _has(lower, ("witch", "witch-hunting", "witch hunting", "daain", "daayan", "tonhi", "tonahi")):
        if _has(q, ("assam", "barpeta")):
            return (
                ("bare_act" in item_blob or "official_guidance" in item_blob)
                and "assam-witch-hunting-2015" in item_blob
                and ("witch" in item_blob or "daain" in item_blob or "daayan" in item_blob)
            )
        if _has(q, ("jharkhand", "ranchi", "chaibasa", "gumla", "khunti", "simdega", "singhbhum")):
            return (
                ("bare_act" in item_blob or "official_guidance" in item_blob)
                and "jharkhand" in item_blob
                and ("witch" in item_blob or "daain" in item_blob or "daayan" in item_blob or "dayan" in item_blob)
            )
        if _has(q, ("chhattisgarh", "raipur", "bastar", "tonahi", "tonhi")):
            return (
                ("bare_act" in item_blob or "official_guidance" in item_blob)
                and ("chhattisgarh" in item_blob or "tonahi" in item_blob or "tonhi" in item_blob)
            )
    if "witch" in lower and "jharkhand" in q:
        return (
            ("bare_act" in item_blob or "official_guidance" in item_blob)
            and "jharkhand" in item_blob
            and ("witch" in item_blob or "daain" in item_blob or "dayan" in item_blob)
        )
    if "arms act" in lower:
        if "definition" in lower or "farming tool" in lower or "agricultural" in lower:
            return (
                ("arms act" in item_blob or "arms-1959" in item_blob)
                and _has_any_anchor(item_blob, ("sec-2", "/sec-2"))
            )
        return (
            ("arms act" in item_blob or "arms-1959" in item_blob)
            and _has_any_anchor(item_blob, ("sec-2", "sec-4", "sec-25", "/sec-2", "/sec-4", "/sec-25"))
        )
    if "maharashtra control of organised crime" in lower or "mcoca" in lower:
        return (
            ("maharashtra control of organised crime" in item_blob or "mcoca" in item_blob)
            and ("sec-21" in item_blob or "/sec-21" in item_blob)
        )
    if _canonical_alias_match(lower, item_blob):
        return True
    if _constitutional_reproductive_precedent_match(lower, item_blob):
        return True
    if _has_statute_alias(lower, ("bnss", "crpc")):
        return _bnss_crpc_requirement_matches(lower, item_blob, q)
    if _has_statute_alias(lower, ("bns", "ipc")):
        return _bns_ipc_requirement_matches(lower, item_blob, q)
    return False


def _customs_requirement_matches(required_lower: str, item_blob: str, query_lower: str) -> bool:
    if "customs act" not in item_blob and "customs-1962" not in item_blob:
        return False

    # The route-required source label is intentionally broad ("ICEGATE,
    # duty, valuation, SVB, drawback, classification"). Issue type must
    # therefore come from the user's facts, not from the label itself.
    context = query_lower
    drawback_context = customs_drawback_issue(context)
    misdeclaration_context = customs_misdeclaration_issue(context)
    valuation_context = customs_svb_issue(context)
    classification_context = customs_classification_issue(context) or customs_assessment_issue(context)

    if drawback_context:
        core = ("sec-75", "sec-74", "sec-27", "/sec-75", "/sec-74", "/sec-27")
        if _has(context, ("appeal", "order", "rejection order", "commissioner")):
            return _has_any_anchor(item_blob, (*core, "sec-128", "/sec-128"))
        return _has_any_anchor(item_blob, core)
    if misdeclaration_context:
        return _has_any_anchor(item_blob, (
            "sec-124", "sec-111", "sec-112",
            "/sec-124", "/sec-111", "/sec-112",
        ))
    if valuation_context:
        return _has_any_anchor(item_blob, (
            "sec-14", "sec-17", "sec-28", "sec-128",
            "/sec-14", "/sec-17", "/sec-28", "/sec-128",
        ))
    if classification_context:
        return _has_any_anchor(item_blob, (
            "sec-17", "sec-28", "sec-128",
            "/sec-17", "/sec-28", "/sec-128",
        ))
    return _has_any_anchor(item_blob, (
        "sec-17", "sec-27", "sec-28", "sec-74", "sec-75",
        "sec-111", "sec-112", "sec-124", "sec-128",
        "/sec-17", "/sec-27", "/sec-28", "/sec-74", "/sec-75",
        "/sec-111", "/sec-112", "/sec-124", "/sec-128",
    ))


def _cgst_rule_86b_item_matches(item_blob: str) -> bool:
    return (
        (
            "cgst rules" in item_blob
            or "goods and services tax rules" in item_blob
            or "central goods and services tax rules" in item_blob
        )
        and _has(item_blob, (
            "86b", "86-b", "rule 86b", "rule 86-b",
            "electronic credit ledger", "ninety-nine per cent",
            "ninety nine per cent", "99 per cent",
            "cgst-rules-2017/sec-85", "cgst-rules-2017/sec-85-e",
        ))
    )


def _composite_route_source_match(
    required_source: str,
    passages: list[dict[str, Any]],
    *,
    query: str,
) -> dict[str, Any] | None:
    lower = required_source.lower()
    q = query.lower()
    if (
        "rbi integrated ombudsman" in lower
        and "recovery-agent" in lower
        and "digital-lending" in lower
    ):
        ombudsman_item: dict[str, Any] | None = None
        recovery_item: dict[str, Any] | None = None
        digital_lending_item: dict[str, Any] | None = None
        for item in passages or []:
            if not isinstance(item, dict):
                continue
            blob = _item_blob(item)
            if ombudsman_item is None and _has(blob, (
                "rbi integrated ombudsman",
                "rbi-integrated-ombudsman",
                "reserve bank integrated ombudsman",
            )):
                ombudsman_item = item
            if recovery_item is None and _has(blob, (
                "recovery agents", "recovery-agent",
                "outsourcing of financial services",
            )):
                recovery_item = item
            if digital_lending_item is None and _has(blob, (
                "digital lending", "digital-lending",
            )):
                digital_lending_item = item
        # The route wording intentionally allows either the Ombudsman route
        # or the recovery-agent/digital-lending authority family. Preserve
        # that alternative while still requiring both items for the latter
        # family instead of accepting a loose RBI title match.
        if ombudsman_item is not None:
            return ombudsman_item
        if recovery_item is not None and digital_lending_item is not None:
            return {
                "title": "RBI recovery-agent and digital-lending authority composite",
                "anchor": f"{recovery_item.get('anchor')}; {digital_lending_item.get('anchor')}",
                "source_type": "aggregate",
            }
        return None
    if "cgst rules" in lower and "86b" in lower and "cgst act" in lower:
        matched: dict[str, dict[str, Any]] = {}
        for item in passages or []:
            if not isinstance(item, dict):
                continue
            blob = _item_blob(item)
            if "rule_86b" not in matched and _cgst_rule_86b_item_matches(blob):
                matched["rule_86b"] = item
            if "cgst_act_49" not in matched and (
                ("cgst" in blob or "goods and services tax" in blob)
                and "rules" not in blob
                and _has_any_anchor(blob, (
                    "sec-49", "sec-49a", "sec-49b",
                    "/sec-49", "/sec-49a", "/sec-49b",
                ))
            ):
                matched["cgst_act_49"] = item
        if len(matched) == 2:
            return {
                "title": "CGST Rule 86B and electronic-credit-ledger composite source",
                "anchor": f"{matched['rule_86b'].get('anchor')}; {matched['cgst_act_49'].get('anchor')}",
                "source_type": "aggregate",
            }
        return None
    if "pesa act" in lower and "forest rights" in lower:
        matched: dict[str, dict[str, Any]] = {}
        for item in passages or []:
            if not isinstance(item, dict):
                continue
            blob = _item_blob(item)
            if "pesa" not in matched and (
                ("pesa" in blob or "panchayats" in blob)
                and _has_any_anchor(blob, ("sec-4", "/sec-4"))
            ):
                matched["pesa"] = item
            if "forest_rights" not in matched and (
                (
                    "forest rights" in blob
                    or "scheduled tribes and other traditional forest dwellers" in blob
                    or "fra-2006" in blob
                )
                and (
                    "#header" in blob
                    or _has_any_anchor(blob, (
                        "sec-3", "sec-4", "sec-5", "sec-6",
                        "/sec-3", "/sec-4", "/sec-5", "/sec-6",
                    ))
                )
            ):
                matched["forest_rights"] = item
        if "forest_rights" in matched and not _has_pesa_trigger_context(q):
            return matched["forest_rights"]
        if len(matched) == 2:
            return {
                "title": "PESA/FRA composite route source",
                "anchor": f"{matched['pesa'].get('anchor')}; {matched['forest_rights'].get('anchor')}",
                "source_type": "aggregate",
        }
        return None
    if _is_bns_bnss_or_ipc_crpc_requirement(lower) and _has(lower, ("cheating", "forgery", "false register", "fake register")):
        bns_item = _find_regime_item(
            passages,
            title_terms=("bns", "bharatiya nyaya"),
            anchors=("sec-318", "sec-336", "sec-340", "/sec-318", "/sec-336", "/sec-340"),
        )
        bnss_item = _find_regime_item(
            passages,
            title_terms=("bnss", "bharatiya nagarik"),
            anchors=("sec-173", "sec-175", "/sec-173", "/sec-175"),
        )
        ipc_item = _find_regime_item(
            passages,
            title_terms=("ipc", "indian penal"),
            anchors=("sec-420", "sec-468", "sec-471", "/sec-420", "/sec-468", "/sec-471"),
        )
        crpc_item = _find_regime_item(
            passages,
            title_terms=("crpc", "criminal procedure"),
            anchors=("sec-154", "sec-156", "/sec-154", "/sec-156"),
        )
        current_pair = _criminal_regime_pair_item(
            "BNS/BNSS fake-register route source",
            bns_item,
            bnss_item,
        )
        if current_pair is not None:
            return current_pair
        return _criminal_regime_pair_item(
            "IPC/CrPC fake-register route source",
            ipc_item,
            crpc_item,
        )
    if "income tax" in lower and "80c" in lower and "80ccd" in lower:
        found: dict[str, dict[str, Any]] = {}
        for item in passages or []:
            if not isinstance(item, dict):
                continue
            blob = _item_blob(item)
            if "income tax" not in blob and "income-tax" not in blob:
                continue
            if "80c" not in found and _has_any_anchor(blob, ("sec-80c", "/sec-80c")):
                found["80c"] = item
            if "80ccd" not in found and _has_any_anchor(blob, ("sec-80ccd", "/sec-80ccd")):
                found["80ccd"] = item
        if len(found) == 2:
            return {
                "title": "Income-tax Act 1961 composite deduction source",
                "anchor": f"{found['80c'].get('anchor')}; {found['80ccd'].get('anchor')}",
                "source_type": "aggregate",
            }
        return None
    if "copyright act" in lower and _has(lower, ("infringement", "exception", "fair dealing", "civil remedies", "civil remedy")):
        needed = {
            "infringement": ("/sec-51", "sec-51"),
            "exceptions": ("/sec-52", "sec-52"),
            "remedies": ("/sec-55", "sec-55"),
        }
        matched: dict[str, dict[str, Any]] = {}
        for item in passages or []:
            if not isinstance(item, dict):
                continue
            blob = _item_blob(item)
            if "copyright" not in blob:
                continue
            for role, anchors in needed.items():
                if role in matched:
                    continue
                if _has_any_anchor(blob, anchors):
                    matched[role] = item
        if len(matched) == len(needed):
            return {
                "title": "Copyright Act 1957 composite route source",
                "anchor": "; ".join(str(matched[role].get("anchor") or "") for role in needed),
                "source_type": "aggregate",
            }
    return None


def _is_hard_composite_requirement(required_source: str) -> bool:
    lower = required_source.lower()
    return (
        ("pesa act" in lower and "forest rights" in lower)
        or ("cgst rules" in lower and "86b" in lower and "cgst act" in lower)
        or ("income tax" in lower and "80c" in lower and "80ccd" in lower)
        or (
            "copyright act" in lower
            and _has(lower, ("infringement", "exception", "fair dealing", "civil remedies", "civil remedy"))
        )
        or (
            _is_bns_bnss_or_ipc_crpc_requirement(lower)
            and _has(lower, ("cheating", "forgery", "false register", "fake register"))
        )
    )


def _is_hard_canonical_requirement(required_source: str) -> bool:
    lower = required_source.lower()
    return (
        _is_pmla_sc_precedent_requirement(lower)
        or _has_statute_alias(lower, ("bns", "ipc"))
        or (
            _has_statute_alias(lower, ("bnss", "crpc"))
            and re.search(r"\b(?:section|sec)\.?\s*\d+", lower) is not None
        )
        or (_has_statute_alias(lower, ("bnss", "crpc")) and "based on incident date" in lower)
        or "bocw cess" in lower
        or "welfare-board cess" in lower
        or "welfare board cess" in lower
        or "construction workers welfare cess" in lower
        or "building and other construction workers act" in lower
        or "bocw act" in lower
        or "bocw registration" in lower
        or "welfare-board provisions" in lower
        or (
            "negotiable instruments act" in lower
            and re.search(r"\b(?:section|sec)\.?\s*\d+", lower) is not None
        )
        or (
            re.search(r"\b(?:act|code)\b", lower) is not None
            and re.search(r"\b(?:section|sec)\.?\s*\d+", lower) is not None
        )
        or "mental healthcare act" in lower
        or "mental-healthcare" in lower
        or (
            ("hindu marriage act" in lower or "special marriage act" in lower)
            and _has(lower, ("section 12", "sec 12", "section 13", "sec 13", "voidable", "divorce ground", "matrimonial relief"))
        )
    )


def _constitutional_reproductive_precedent_match(required_lower: str, item_blob: str) -> bool:
    if not _has(required_lower, (
        "reproductive autonomy", "privacy precedents", "reproductive privacy",
        "constitutional reproductive",
    )):
        return False
    return _has(item_blob, (
        "x versus the principal secretary",
        "principal secretary health and family welfare",
        "ms. z  versus the state of bihar",
        "ms. z versus the state of bihar",
        "suchita srivastava",
        "puttaswamy",
        "justice k.s. puttaswamy",
        "2017-insc-756",
        "2022-insc-740",
    ))


def _canonical_alias_match(required_lower: str, item_blob: str) -> bool:
    canonical_aliases: tuple[tuple[tuple[str, ...], tuple[str, ...], tuple[str, ...]], ...] = (
        (
            ("motor vehicles act", "driving licence", "traffic enforcement", "traffic challan", "permit"),
            ("motor vehicles act", "themotorvehiclesact"),
            ("sec-3", "sec-4", "sec-19", "sec-74", "sec-130", "sec-177", "sec-182", "sec-183", "sec-200", "sec-206", "/sec-3", "/sec-4", "/sec-19", "/sec-74", "/sec-130", "/sec-177", "/sec-182", "/sec-183", "/sec-200", "/sec-206"),
        ),
        (
            ("motor vehicles act", "aggregator licensing", "aggregator licence", "aggregator"),
            ("motor vehicle aggregator guidelines", "motor vehicles act", "themotorvehiclesact"),
            ("driver-service-contract", "app-transparency-grievance", "non-discrimination-driver-fare", "sec-93", "sec-193", "/sec-93", "/sec-193"),
        ),
        (
            ("guardians and wards", "custody principles", "child custody"),
            ("guardians and wards", "guardian and wards", "guardians-wards"),
            ("sec-7", "sec-17", "sec-25", "/sec-7", "/sec-17", "/sec-25"),
        ),
        (
            ("shops and establishments", "shop act", "shops establishment"),
            ("shops and commercial establishments", "shops establishments", "shop establishment"),
            ("sec-2", "sec-4", "sec-5", "registration-fee-checklist", "/sec-2", "/sec-4", "/sec-5"),
        ),
        (
            ("national food security", "tpds", "ration entitlement"),
            ("national food security",),
            ("sec-3", "sec-12", "sec-14", "sec-15", "/sec-3", "/sec-12", "/sec-14", "/sec-15"),
        ),
        (
            ("protection of civil rights", "temple", "well/water", "public-access"),
            ("protection of civil rights",),
            ("sec-3", "sec-4", "sec-7", "/sec-3", "/sec-4", "/sec-7"),
        ),
        (
            ("customs act", "icegate", "import/export", "drawback", "classification", "valuation", "svb"),
            ("customs act",),
            (
                "sec-14", "sec-17", "sec-18", "sec-27", "sec-28",
                "sec-74", "sec-75", "sec-111", "sec-112", "sec-124",
                "sec-128", "sec-129a", "/sec-14", "/sec-17", "/sec-18",
                "/sec-27", "/sec-28", "/sec-74", "/sec-75", "/sec-111",
                "/sec-112", "/sec-124", "/sec-128", "/sec-129a",
            ),
        ),
        (
            ("banking regulation act", "bank-service dispute", "banking grievance", "education-loan refusal", "education loan refusal", "rbi/banking grievance", "rbi integrated ombudsman", "rbi integrated ombudsman scheme"),
            ("banking regulation", "reserve bank integrated ombudsman", "rbi integrated ombudsman"),
            ("#header", "sec-2", "sec-20", "sec-35a", "sec-35-a", "/sec-2", "/sec-20", "/sec-35a", "/sec-35-a"),
        ),
        (
            ("negotiable instruments act", "negotiable instrument", "ni act", "cheque dishonour"),
            ("negotiable instruments",),
            ("sec-138", "sec-141", "sec-142", "/sec-138", "/sec-141", "/sec-142"),
        ),
        (
            ("code of civil procedure", "cpc", "order xxi", "order 21", "execution procedure", "execution petition", "decree", "summons", "plaint rejection", "threshold objections"),
            ("code of civil procedure", "cpc"),
            ("sec-51", "sec-47", "sec-108", "sec-151", "sec-96", "sec-100", "sec-24", "sec-33", "sec-65", "sec-89", "/sec-51", "/sec-47", "/sec-108", "/sec-151", "/sec-96", "/sec-100", "/sec-24", "/sec-33", "/sec-65", "/sec-89"),
        ),
        (
            ("nclt", "ibc application", "application forms"),
            ("national company law tribunal", "nclt"),
            ("rule-6", "rule-10", "rule-11", "rule-23", "rule-34", "rule-35", "/rule-6", "/rule-10", "/rule-11", "/rule-23", "/rule-34", "/rule-35"),
        ),
        (
            ("nclat", "certified-copy", "certified copy", "limitation facts", "forms, fees"),
            ("national company law appellate tribunal", "nclat"),
            ("rule-22", "rule-23", "rule-26", "rule-48", "rule-50", "/rule-22", "/rule-23", "/rule-26", "/rule-48", "/rule-50"),
        ),
        (
            ("food safety", "fssai", "food business", "misbranding", "improvement notice"),
            ("food safety", "fssai"),
            ("sec-26", "sec-31", "sec-32", "sec-42", "sec-50", "sec-59", "sec-63", "/sec-26", "/sec-31", "/sec-32", "/sec-42", "/sec-50", "/sec-59", "/sec-63"),
        ),
        (
            ("limited liability partnership", "llp"),
            ("limited liability partnership", "llp"),
            ("sec-35", "sec-75", "sec-75-a", "sec-75-b", "sec-75-c", "/sec-35", "/sec-75", "/sec-75-a", "/sec-75-b", "/sec-75-c"),
        ),
        (
            ("sarfaesi", "securitisation", "security interest"),
            ("sarfaesi", "securitisation", "security interest"),
            ("sec-13", "sec-17", "/sec-13", "/sec-17"),
        ),
        (
            ("state land revenue", "mutation", "pattadar", "land record", "land revenue"),
            ("pattadar", "rights in land", "land revenue", "mutation", "chota nagpur tenancy", "santhal parganas tenancy"),
            ("sec-3", "sec-4", "sec-5", "sec-6", "sec-9", "sec-10", "sec-46", "sec-71-a", "/sec-3", "/sec-4", "/sec-5", "/sec-6", "/sec-9", "/sec-10", "/sec-46", "/sec-71-a"),
        ),
        (
            ("family law statute", "personal law by religion", "personal law", "marriage statute"),
            ("hindu marriage", "special marriage", "muslim personal", "dissolution of muslim", "family courts"),
            ("sec-5", "sec-7", "sec-9", "sec-12", "sec-13", "sec-13b", "sec-13-b", "sec-24", "sec-25", "sec-27", "/sec-5", "/sec-7", "/sec-9", "/sec-12", "/sec-13", "/sec-13b", "/sec-13-b", "/sec-24", "/sec-25", "/sec-27"),
        ),
        (
            ("aadhaar act", "aadhaar authentication", "identity information", "uidai"),
            ("aadhaar", "unique identification"),
            ("sec-7", "sec-8", "sec-29", "sec-59", "/sec-7", "/sec-8", "/sec-29", "/sec-59"),
        ),
        (
            ("copyright act", "creative work", "logo"),
            ("copyright",),
            ("sec-51", "sec-55", "/sec-51", "/sec-55"),
        ),
        (
            ("protection of human rights", "human rights act", "nhrc", "shrc"),
            ("protection of human rights", "human-rights"),
            ("sec-12", "sec-13", "sec-17", "sec-30", "/sec-12", "/sec-13", "/sec-17", "/sec-30"),
        ),
        (
            ("motor vehicles act", "insurance", "claims tribunal", "mact", "third party"),
            ("motor vehicles act", "themotorvehiclesact"),
            ("sec-134", "sec-146", "sec-147", "sec-149", "sec-164", "sec-165", "sec-166", "/sec-134", "/sec-146", "/sec-147", "/sec-149", "/sec-164", "/sec-165", "/sec-166"),
        ),
        (
            ("insurance ombudsman", "insurer grievance", "insurance grievance", "claim repudiation", "claim rejection"),
            ("insurance ombudsman rules", "insurance ombudsman"),
            ("sec-3", "sec-4", "sec-5", "sec-6", "sec-13", "sec-14", "sec-15", "sec-16", "sec-17", "/sec-3", "/sec-4", "/sec-5", "/sec-6", "/sec-13", "/sec-14", "/sec-15", "/sec-16", "/sec-17"),
        ),
        (
            ("clinical establishments", "clinical-establishment", "hospital records", "hospital billing", "hospital records, billing"),
            ("clinical establishments", "clinical establishment"),
            ("sec-11", "sec-12", "sec-33", "sec-42", "/sec-11", "/sec-12", "/sec-33", "/sec-42"),
        ),
        (
            ("medical council", "medical ethics", "professional-conduct", "professional conduct"),
            ("medical ethics", "professional conduct", "medical council"),
            ("reg-1.3.1", "reg-1.3.2", "reg-7.2"),
        ),
        (
            ("national green tribunal", "environmental relief", "environmental compensation"),
            ("national green tribunal", "ngt"),
            ("sec-14", "sec-15", "sec-16", "sec-18", "/sec-14", "/sec-15", "/sec-16", "/sec-18"),
        ),
        (
            ("companies act", "annual filing", "director disqualification", "restoration"),
            ("companies act",),
            ("sec-92", "sec-137", "sec-164", "sec-167", "sec-248", "sec-252", "/sec-92", "/sec-137", "/sec-164", "/sec-167", "/sec-248", "/sec-252"),
        ),
        (
            ("rfctlarr", "land acquisition", "compensation award", "reference-to-authority", "reference to authority"),
            ("right to fair compensation", "rfctlarr", "land acquisition"),
            ("sec-31", "sec-38", "sec-41", "sec-64", "sec-77", "/sec-31", "/sec-38", "/sec-41", "/sec-64", "/sec-77"),
        ),
        (
            ("legal services authorities", "under trial review committee", "under-trial review committee", "utrc"),
            ("legal services authorities",),
            ("sec-9", "sec-12", "sec-13", "sec-21", "/sec-9", "/sec-12", "/sec-13", "/sec-21"),
        ),
        (
            ("real estate", "rera"),
            ("real estate", "rera"),
            ("sec-11", "sec-14", "sec-18", "sec-31", "sec-34", "/sec-11", "/sec-14", "/sec-18", "/sec-31", "/sec-34"),
        ),
        (
            ("prevention of money laundering", "pmla", "twin condition", "money laundering"),
            ("prevention of money laundering", "pmla"),
            ("sec-19", "sec-45", "/sec-19", "/sec-45"),
        ),
        (
            ("compoundability", "compoundable", "offence-compoundability", "court permission"),
            ("bnss", "bharatiya nagarik", "crpc", "criminal procedure"),
            ("sec-359", "sec-320", "/sec-359", "/sec-320"),
        ),
        (
            ("specific relief act", "injunction", "specific performance", "negative covenant", "exclusivity"),
            ("specific relief",),
            ("sec-31", "sec-34", "sec-38", "sec-42", "/sec-31", "/sec-34", "/sec-38", "/sec-42"),
        ),
    )
    for required_aliases, title_aliases, anchor_aliases in canonical_aliases:
        if not _has(required_lower, required_aliases):
            continue
        if not _has(item_blob, title_aliases):
            continue
        if anchor_aliases and not _has_any_anchor(item_blob, anchor_aliases):
            continue
        return True
    return False


def _is_dual_regime_requirement(required_source: str) -> bool:
    lower = required_source.lower()
    return (
        "bnss" in lower
        and "crpc" in lower
        and (
            "based on incident date" in lower
            or "based on incident/procedure date" in lower
            or "based on procedure date" in lower
        )
    )


def _dual_regime_source_match(
    required_source: str,
    passages: list[dict[str, Any]],
    *,
    query: str,
) -> dict[str, Any] | None:
    lower = required_source.lower()
    q = query.lower()
    anchors = _bnss_crpc_anchor_terms(lower)
    if _has_default_bail_query_context(q) and _has(lower, (
        "default bail", "default-bail", "no chargesheet", "no charge sheet",
        "undertrial", "under-trial", "custody",
    )):
        anchors = {
            "bnss": ("sec-187", "/sec-187"),
            "crpc": ("sec-167", "/sec-167"),
        }
    is_offence_plus_procedure = _is_bns_bnss_or_ipc_crpc_requirement(lower)
    if is_offence_plus_procedure and _has(q, (
        "cyber", "online", "instagram", "insta", "whatsapp", "telegram",
        "deepfake", "morphed", "intimate", "private video", "private photo",
        "blackmail", "extort", "extorting", "threat", "threatening",
        "fake account", "fake profile", "otp", "upi",
    )) and not _has(q, ("bail", "arrest", "arrested", "custody", "remand", "anticipatory")):
        anchors = {
            "bnss": ("sec-173", "sec-175", "/sec-173", "/sec-175"),
            "crpc": ("sec-154", "sec-156", "sec-200", "/sec-154", "/sec-156", "/sec-200"),
        }
    if is_offence_plus_procedure and _has_cyber_notice_no_paper_context(q):
        anchors = {
            "bnss": ("sec-35", "sec-173", "sec-175", "/sec-35", "/sec-173", "/sec-175"),
            "crpc": (
                "sec-41a", "sec-41-a", "sec-154", "sec-156", "sec-200",
                "/sec-41a", "/sec-41-a", "/sec-154", "/sec-156", "/sec-200",
            ),
        }
    offence_anchors = _bns_ipc_anchor_terms(lower, q) if is_offence_plus_procedure else ()
    bns_item = _find_regime_item(
        passages,
        title_terms=("bns", "bharatiya nyaya"),
        anchors=offence_anchors,
    )
    bnss_item = _find_regime_item(
        passages,
        title_terms=("bnss", "bharatiya nagarik"),
        anchors=anchors["bnss"],
    )
    ipc_item = _find_regime_item(
        passages,
        title_terms=("ipc", "indian penal"),
        anchors=offence_anchors,
    )
    crpc_item = _find_regime_item(
        passages,
        title_terms=("crpc", "criminal procedure"),
        anchors=anchors["crpc"],
    )
    if is_offence_plus_procedure and _has_cyber_notice_no_paper_context(q):
        if _query_points_to_old_criminal_regime(q):
            return crpc_item
        if _query_points_to_new_criminal_regime(q):
            return bnss_item
        return bnss_item or crpc_item
    if is_offence_plus_procedure:
        if _query_points_to_old_criminal_regime(q):
            return _criminal_regime_pair_item(
                "IPC/CrPC composite route source",
                ipc_item,
                crpc_item,
            )
        if _query_points_to_new_criminal_regime(q):
            return _criminal_regime_pair_item(
                "BNS/BNSS composite route source",
                bns_item,
                bnss_item,
            )
        current_pair = _criminal_regime_pair_item(
            "BNS/BNSS composite route source",
            bns_item,
            bnss_item,
        )
        if current_pair is not None:
            return current_pair
        return _criminal_regime_pair_item(
            "IPC/CrPC composite route source",
            ipc_item,
            crpc_item,
        )
    if _query_points_to_old_criminal_regime(q):
        return crpc_item
    if _query_points_to_new_criminal_regime(q):
        return bnss_item
    if _has(lower, ("chargesheet", "charge sheet", "charge-sheet", "police report", "summons", "discharge")):
        return bnss_item or crpc_item
    if not _requires_dual_procedure_counterpart(q, lower):
        return bnss_item or crpc_item
    if bnss_item is not None and crpc_item is not None:
        return {
            "title": "BNSS/CrPC composite route source",
            "anchor": f"{bnss_item.get('anchor')}; {crpc_item.get('anchor')}",
            "source_type": "aggregate",
        }
    return None


def _is_bns_bnss_or_ipc_crpc_requirement(required_lower: str) -> bool:
    return (
        _has_statute_alias(required_lower, ("bns", "bharatiya nyaya"))
        and _has_statute_alias(required_lower, ("bnss", "bharatiya nagarik"))
        and _has_statute_alias(required_lower, ("ipc", "indian penal"))
        and _has_statute_alias(required_lower, ("crpc", "criminal procedure"))
    )


def _has_cyber_notice_no_paper_context(q: str) -> bool:
    cyber_notice = _has(q, (
        "cyber case", "cyber police", "cyber cell", "notice in cyber",
        "cyber notice", "police calling", "police called", "calling me",
    ))
    no_paper = _has(q, (
        "not giving paper", "without paper", "no paper", "no written",
        "no written notice", "not giving notice", "written notice",
    ))
    return cyber_notice and no_paper


def _criminal_regime_pair_item(
    title: str,
    offence_item: dict[str, Any] | None,
    procedure_item: dict[str, Any] | None,
) -> dict[str, Any] | None:
    if offence_item is None or procedure_item is None:
        return None
    return {
        "title": title,
        "anchor": f"{offence_item.get('anchor')}; {procedure_item.get('anchor')}",
        "source_type": "aggregate",
    }


def _requires_dual_procedure_counterpart(query_lower: str, required_lower: str) -> bool:
    """Require both old/new procedure only when the facts make that risk real."""
    if _query_points_to_old_criminal_regime(query_lower) or _query_points_to_new_criminal_regime(query_lower):
        return True
    if _has_default_bail_query_context(query_lower):
        return True
    if _has(required_lower, (
        "default bail", "default-bail", "undertrial", "under-trial",
        "no chargesheet", "no charge sheet",
    )):
        return True
    if re.search(r"\b(?:[2-9]|1[0-9])\s*(?:month|months|yr|yrs|year|years)\b", query_lower):
        return True
    return _has(query_lower, (
        "long custody", "prolonged custody", "trial pending for",
        "pending 5 years", "pending five years",
    ))


def _find_regime_item(
    passages: list[dict[str, Any]],
    *,
    title_terms: tuple[str, ...],
    anchors: tuple[str, ...],
) -> dict[str, Any] | None:
    for item in passages or []:
        if not isinstance(item, dict):
            continue
        blob = _item_blob(item)
        if not _has_statute_alias(blob, title_terms):
            continue
        if anchors and not any(_anchor_term_matches(blob, anchor) for anchor in anchors):
            continue
        return item
    return None


def _bnss_crpc_requirement_matches(required_lower: str, item_blob: str, query_lower: str) -> bool:
    anchors = _bnss_crpc_anchor_terms(required_lower)
    if _has_default_bail_query_context(query_lower) and _has(required_lower, (
        "default bail", "default-bail", "no chargesheet", "no charge sheet",
        "undertrial", "under-trial", "custody",
    )):
        anchors = {
            "bnss": ("sec-187", "/sec-187"),
            "crpc": ("sec-167", "/sec-167"),
        }
    has_bnss = _has_statute_alias(item_blob, ("bnss", "bharatiya nagarik")) and _has_any_anchor(item_blob, anchors["bnss"])
    has_crpc = _has_statute_alias(item_blob, ("crpc", "criminal procedure")) and _has_any_anchor(item_blob, anchors["crpc"])
    requires_bnss = _has_statute_alias(required_lower, ("bnss", "bharatiya nagarik"))
    requires_crpc = _has_statute_alias(required_lower, ("crpc", "criminal procedure"))
    if requires_bnss and not requires_crpc:
        return has_bnss
    if requires_crpc and not requires_bnss:
        return has_crpc
    if "based on incident date" in required_lower:
        if _query_points_to_old_criminal_regime(query_lower):
            return has_crpc
        if _query_points_to_new_criminal_regime(query_lower):
            return has_bnss
        return has_bnss and has_crpc
    return has_bnss or has_crpc


def _bns_ipc_requirement_matches(required_lower: str, item_blob: str, query_lower: str) -> bool:
    has_bns = _has_statute_alias(item_blob, ("bns", "bharatiya nyaya"))
    has_ipc = _has_statute_alias(item_blob, ("ipc", "indian penal"))
    anchors = _bns_ipc_anchor_terms(required_lower, query_lower)
    if anchors and not _has_any_anchor(item_blob, anchors):
        return False
    if _query_points_to_old_criminal_regime(query_lower):
        return has_ipc
    if _query_points_to_new_criminal_regime(query_lower):
        return has_bns
    return has_bns or has_ipc


def _bns_ipc_anchor_terms(required_lower: str, query_lower: str) -> tuple[str, ...]:
    blob = f"{required_lower} {query_lower}"
    negated_extortion = _has_negated_extortion_money_context(query_lower)
    groups: list[tuple[str, tuple[str, ...]]] = [
        ("acid", ("sec-124", "sec-326a", "sec-326b", "/sec-124", "/sec-326a", "/sec-326b")),
        ("sexual", ("sec-63", "sec-64", "sec-65", "sec-67", "sec-69", "sec-70", "sec-74", "sec-75", "sec-76", "sec-77", "sec-78", "sec-79", "sec-354", "sec-354a", "sec-354b", "sec-354c", "sec-354d", "sec-376", "/sec-63", "/sec-64", "/sec-65", "/sec-67", "/sec-69", "/sec-70", "/sec-74", "/sec-75", "/sec-76", "/sec-77", "/sec-78", "/sec-79", "/sec-354", "/sec-354a", "/sec-354b", "/sec-354c", "/sec-354d", "/sec-376")),
        ("rape", ("sec-63", "sec-64", "sec-65", "sec-69", "sec-70", "sec-376", "/sec-63", "/sec-64", "/sec-65", "/sec-69", "/sec-70", "/sec-376")),
        ("promise", ("sec-69", "/sec-69")),
        ("stalk", ("sec-78", "sec-354d", "/sec-78", "/sec-354d")),
        ("threat", ("sec-351", "sec-503", "sec-506", "/sec-351", "/sec-503", "/sec-506")),
        ("intimidation", ("sec-351", "sec-503", "sec-506", "/sec-351", "/sec-503", "/sec-506")),
        ("defamation", ("sec-356", "sec-499", "sec-500", "/sec-356", "/sec-499", "/sec-500")),
        ("reputation", ("sec-356", "sec-499", "sec-500", "/sec-356", "/sec-499", "/sec-500")),
        ("dacoity", ("sec-309", "sec-310", "sec-311", "sec-391", "sec-395", "sec-398", "/sec-309", "/sec-310", "/sec-311", "/sec-391", "/sec-395", "/sec-398")),
        ("robbery", ("sec-309", "sec-310", "sec-390", "sec-392", "sec-394", "/sec-309", "/sec-310", "/sec-390", "/sec-392", "/sec-394")),
        ("cheating", ("sec-318", "sec-319", "sec-415", "sec-416", "sec-420", "/sec-318", "/sec-319", "/sec-415", "/sec-416", "/sec-420")),
        ("personation", ("sec-319", "sec-416", "/sec-319", "/sec-416")),
        ("hacked", ("sec-318", "sec-319", "sec-415", "sec-416", "sec-420", "/sec-318", "/sec-319", "/sec-415", "/sec-416", "/sec-420")),
        ("account hacked", ("sec-318", "sec-319", "sec-415", "sec-416", "sec-420", "/sec-318", "/sec-319", "/sec-415", "/sec-416", "/sec-420")),
        ("breach of trust", ("sec-316", "sec-316-a", "sec-316-b", "sec-316-c", "sec-405", "sec-406", "/sec-316", "/sec-316-a", "/sec-316-b", "/sec-316-c", "/sec-405", "/sec-406")),
        ("entrust", ("sec-316", "sec-316-a", "sec-316-b", "sec-316-c", "sec-405", "sec-406", "/sec-316", "/sec-316-a", "/sec-316-b", "/sec-316-c", "/sec-405", "/sec-406")),
        ("forgery", ("sec-336", "sec-337", "sec-338", "sec-340", "sec-463", "sec-464", "sec-465", "sec-468", "sec-471", "/sec-336", "/sec-337", "/sec-338", "/sec-340", "/sec-463", "/sec-464", "/sec-465", "/sec-468", "/sec-471")),
        ("false document", ("sec-336", "sec-337", "sec-338", "sec-340", "sec-463", "sec-464", "sec-465", "sec-468", "sec-471", "/sec-336", "/sec-337", "/sec-338", "/sec-340", "/sec-463", "/sec-464", "/sec-465", "/sec-468", "/sec-471")),
        ("blank paper", ("sec-336", "sec-337", "sec-338", "sec-340", "sec-463", "sec-464", "sec-465", "sec-468", "sec-471", "/sec-336", "/sec-337", "/sec-338", "/sec-340", "/sec-463", "/sec-464", "/sec-465", "/sec-468", "/sec-471")),
        ("thumb impression", ("sec-336", "sec-337", "sec-338", "sec-340", "sec-463", "sec-464", "sec-465", "sec-468", "sec-471", "/sec-336", "/sec-337", "/sec-338", "/sec-340", "/sec-463", "/sec-464", "/sec-465", "/sec-468", "/sec-471")),
        ("theft", ("sec-303", "sec-305", "sec-317", "sec-378", "sec-379", "sec-411", "/sec-303", "/sec-305", "/sec-317", "/sec-378", "/sec-379", "/sec-411")),
        ("stolen", ("sec-303", "sec-305", "sec-317", "sec-378", "sec-379", "sec-411", "/sec-303", "/sec-305", "/sec-317", "/sec-378", "/sec-379", "/sec-411")),
        ("cruelty", ("sec-85", "sec-86", "sec-498a", "sec-498-a", "/sec-85", "/sec-86", "/sec-498a", "/sec-498-a")),
        ("dowry", ("sec-80", "sec-85", "sec-86", "sec-304b", "sec-304-b", "sec-498a", "sec-498-a", "/sec-80", "/sec-85", "/sec-86", "/sec-304b", "/sec-304-b", "/sec-498a", "/sec-498-a")),
        ("extort", ("sec-308", "sec-383", "sec-384", "/sec-308", "/sec-383", "/sec-384")),
        ("confinement", ("sec-126", "sec-127", "sec-146", "sec-339", "sec-340", "sec-341", "sec-342", "sec-374", "/sec-126", "/sec-127", "/sec-146", "/sec-339", "/sec-340", "/sec-341", "/sec-342", "/sec-374")),
        ("trafficking", (
            "sec-143", "sec-144", "sec-145", "sec-146",
            "sec-370", "sec-370a", "sec-371", "sec-372", "sec-373", "sec-374",
            "/sec-143", "/sec-144", "/sec-145", "/sec-146",
            "/sec-370", "/sec-370a", "/sec-371", "/sec-372", "/sec-373", "/sec-374",
        )),
        ("exploitation", (
            "sec-143", "sec-144", "sec-145", "sec-146",
            "sec-370", "sec-370a", "sec-371", "sec-372", "sec-373", "sec-374",
            "/sec-143", "/sec-144", "/sec-145", "/sec-146",
            "/sec-370", "/sec-370a", "/sec-371", "/sec-372", "/sec-373", "/sec-374",
        )),
        ("beat", ("sec-115", "sec-117", "sec-118", "sec-323", "sec-325", "sec-326", "/sec-115", "/sec-117", "/sec-118", "/sec-323", "/sec-325", "/sec-326")),
        ("beaten", ("sec-115", "sec-117", "sec-118", "sec-323", "sec-325", "sec-326", "/sec-115", "/sec-117", "/sec-118", "/sec-323", "/sec-325", "/sec-326")),
        ("hit", ("sec-115", "sec-117", "sec-118", "sec-323", "sec-325", "sec-326", "/sec-115", "/sec-117", "/sec-118", "/sec-323", "/sec-325", "/sec-326")),
        ("slap", ("sec-115", "sec-117", "sec-118", "sec-323", "sec-325", "sec-326", "/sec-115", "/sec-117", "/sec-118", "/sec-323", "/sec-325", "/sec-326")),
        ("hurt", ("sec-115", "sec-117", "sec-118", "sec-323", "sec-325", "sec-326", "/sec-115", "/sec-117", "/sec-118", "/sec-323", "/sec-325", "/sec-326")),
        ("injury", ("sec-115", "sec-117", "sec-118", "sec-323", "sec-325", "sec-326", "/sec-115", "/sec-117", "/sec-118", "/sec-323", "/sec-325", "/sec-326")),
        ("assault", ("sec-115", "sec-117", "sec-118", "sec-74", "sec-75", "sec-323", "sec-325", "sec-326", "sec-354", "sec-354a", "/sec-115", "/sec-117", "/sec-118", "/sec-74", "/sec-75", "/sec-323", "/sec-325", "/sec-326", "/sec-354", "/sec-354a")),
    ]
    anchors: list[str] = []
    for term, term_anchors in groups:
        if term == "extort" and negated_extortion:
            continue
        if term in blob:
            anchors.extend(anchor for anchor in term_anchors if anchor not in anchors)
    return tuple(anchors)


def _has_negated_extortion_money_context(q: str) -> bool:
    return _has(q, (
        "not extorting", "not extort", "not extortion",
        "no extortion", "without extortion", "no money demand",
        "no money demanded", "not demanding money", "not demanded money",
        "did not demand money", "didn't demand money",
        "just threatening to share", "only threatening to share",
    ))


def _bnss_crpc_anchor_terms(required_lower: str) -> dict[str, tuple[str, ...]]:
    if _has(required_lower, ("search", "seizure", "seize")):
        return {
            "bnss": (
                "sec-105", "sec-173", "sec-175", "sec-187", "sec-480", "sec-483",
                "/sec-105", "/sec-173", "/sec-175", "/sec-187", "/sec-480", "/sec-483",
            ),
            "crpc": (
                "sec-100", "sec-102", "sec-154", "sec-156", "sec-165", "sec-167",
                "sec-437", "sec-438", "sec-439",
                "/sec-100", "/sec-102", "/sec-154", "/sec-156", "/sec-165", "/sec-167",
                "/sec-437", "/sec-438", "/sec-439",
            ),
        }
    if _has(required_lower, ("arrest",)) and _has(required_lower, ("fir", "remand", "bail")):
        return {
            "bnss": (
                "sec-35", "sec-47", "sec-48", "sec-57", "sec-58", "sec-173",
                "sec-175", "sec-187", "sec-480", "sec-483",
                "/sec-35", "/sec-47", "/sec-48", "/sec-57", "/sec-58",
                "/sec-173", "/sec-175", "/sec-187", "/sec-480", "/sec-483",
            ),
            "crpc": (
                "sec-41", "sec-50", "sec-56", "sec-57", "sec-154", "sec-156",
                "sec-167", "sec-437", "sec-438", "sec-439",
                "/sec-41", "/sec-50", "/sec-56", "/sec-57", "/sec-154",
                "/sec-156", "/sec-167", "/sec-437", "/sec-438", "/sec-439",
            ),
        }
    if _has(required_lower, ("default bail", "default-bail", "no chargesheet", "no charge sheet", "undertrial")):
        return {
            "bnss": ("sec-187", "sec-479", "/sec-187", "/sec-479"),
            "crpc": ("sec-167", "sec-436a", "sec-436-a", "/sec-167", "/sec-436a", "/sec-436-a", "/sec-436A"),
        }
    if _has(required_lower, ("chargesheet", "charge sheet", "charge-sheet", "police report", "discharge")):
        return {
            "bnss": (
                "sec-193", "sec-250", "sec-251", "sec-262", "sec-263",
                "sec-268", "sec-269", "sec-480", "sec-483",
                "/sec-193", "/sec-250", "/sec-251", "/sec-262", "/sec-263",
                "/sec-268", "/sec-269", "/sec-480", "/sec-483",
            ),
            "crpc": (
                "sec-173", "sec-227", "sec-239", "sec-245", "sec-437",
                "sec-438", "sec-439",
                "/sec-173", "/sec-227", "/sec-239", "/sec-245", "/sec-437",
                "/sec-438", "/sec-439",
            ),
        }
    if "bail" in required_lower:
        return {
            "bnss": ("sec-479", "sec-480", "sec-482", "sec-483", "/sec-479", "/sec-480", "/sec-482", "/sec-483"),
            "crpc": ("sec-436", "sec-436a", "sec-436-a", "sec-437", "sec-438", "sec-439", "/sec-436", "/sec-436a", "/sec-436-a", "/sec-437", "/sec-438", "/sec-439"),
        }
    if _has(required_lower, ("fir", "complaint", "investigation", "medical", "statement", "inquest")):
        return {
            "bnss": ("sec-173", "sec-175", "sec-176", "sec-180", "sec-183", "sec-184", "sec-223", "/sec-173", "/sec-175", "/sec-176", "/sec-180", "/sec-183", "/sec-184", "/sec-223"),
            "crpc": ("sec-154", "sec-156", "sec-157", "sec-174", "sec-176", "sec-190", "sec-200", "sec-202", "/sec-154", "/sec-156", "/sec-157", "/sec-174", "/sec-176", "/sec-190", "/sec-200", "/sec-202"),
        }
    if _has(required_lower, ("arrest", "detention", "production", "remand", "notice")):
        return {
            "bnss": ("sec-35", "sec-47", "sec-48", "sec-57", "sec-58", "sec-187", "/sec-35", "/sec-47", "/sec-48", "/sec-57", "/sec-58", "/sec-187"),
            "crpc": ("sec-41", "sec-50", "sec-56", "sec-57", "sec-160", "sec-167", "/sec-41", "/sec-50", "/sec-56", "/sec-57", "/sec-160", "/sec-167"),
        }
    return {
        "bnss": ("bnss", "bharatiya nagarik"),
        "crpc": ("crpc", "criminal procedure"),
    }


def _bail_arrest_safeguard_anchor_terms(query_lower: str, required_lower: str = "") -> tuple[str, ...]:
    if _has_default_bail_query_context(query_lower) and _has(required_lower, (
        "default bail", "default-bail", "no chargesheet", "no charge sheet",
        "undertrial", "under-trial",
    )):
        return (
            "sec-167", "sec-187", "/sec-167", "/sec-187",
        )
    arrest_procedure_context = _has(query_lower, (
        "arrest", "arrested", "detain", "detained", "custody", "picked",
        "pickup", "police took", "not produced", "24 hours",
        "twenty four hours", "arrest memo", "grounds of arrest",
        "lawyer during interrogation",
    ))
    bail_context = _has(query_lower, (
        "bail", "anticipatory", "default bail", "regular bail",
        "twin condition", "pmla", "surety",
    ))
    arrest_anchors = (
        "sec-35", "sec-41", "sec-47", "sec-48", "sec-50", "sec-56",
        "sec-57", "sec-58", "sec-160", "sec-167", "sec-187",
        "/sec-35", "/sec-41", "/sec-47", "/sec-48", "/sec-50",
        "/sec-56", "/sec-57", "/sec-58", "/sec-160", "/sec-167",
        "/sec-187",
    )
    bail_anchors = (
        "sec-436", "sec-436a", "sec-436-a", "sec-437", "sec-438",
        "sec-439", "sec-479", "sec-480", "sec-482", "sec-483",
        "/sec-436", "/sec-436a", "/sec-436-a", "/sec-437", "/sec-438",
        "/sec-439", "/sec-479", "/sec-480", "/sec-482", "/sec-483",
    )
    if arrest_procedure_context and not bail_context:
        return arrest_anchors
    if bail_context and not arrest_procedure_context:
        return bail_anchors
    return arrest_anchors + bail_anchors


def _has_default_bail_query_context(query_lower: str) -> bool:
    return _has(query_lower, (
        "default bail", "default-bail", "statutory bail",
        "no chargesheet", "no charge sheet", "no charge-sheet",
        "chargesheet not", "charge sheet not", "charge-sheet not",
        "no challan", "challan not", "no complaint filed",
        "complaint not filed", "no final report", "final report not",
    )) or re.search(r"\b(?:6[0-9]|[7-9][0-9]|1[0-9]{2})\s*days?\b", query_lower) is not None


def _has_any_anchor(blob: str, anchors: tuple[str, ...]) -> bool:
    return any(_anchor_term_matches(blob, anchor) for anchor in anchors)


def _has_separate_criminal_case_context(query_lower: str) -> bool:
    if _has_no_separate_criminal_case_context(query_lower):
        return False
    return _has(query_lower, (
        "fir", "police case", "criminal case", "criminal complaint",
        "arrest notice", "police notice", "station notice", "arrested",
        "arrest", "police called", "police station", "criminal court",
        "bns", "ipc", "bnss", "crpc", "498a", "rape case",
        "sexual offence", "section 85", "sec 85", "section 86", "sec 86",
    ))


def _has_no_separate_criminal_case_context(query_lower: str) -> bool:
    return _has(query_lower, (
        "no fir", "without fir", "no police case", "no criminal case",
        "no criminal complaint", "only notice", "just notice",
        "no arrest notice", "no police notice",
    )) and not _has(query_lower, (
        "separate fir", "fir under", "police sent arrest notice",
        "arrest notice under", "criminal complaint filed", "case registered",
        "arrested", "summoned in criminal court",
    ))


def _has_negated_family_criminal_force_context(query_lower: str) -> bool:
    return _has(query_lower, (
        "no assault", "no physical assault", "without assault",
        "no threat", "no threats", "without threat", "without threats",
        "no violence", "without violence", "no beating", "not beaten",
        "no injury", "no hurt", "no coercion", "not threatened",
        "not threatening", "no confinement", "not confined",
    ))


def _has_family_police_help_needed_context(query_lower: str) -> bool:
    if _has_no_separate_criminal_case_context(query_lower) or _has(query_lower, (
        "no police help", "police help not needed", "no police needed",
        "not going to police", "do not want police",
    )):
        return False
    return _has(query_lower, (
        "police", "fir", "emergency", "112", "100", "assault", "attack",
        "beat", "beaten", "hit", "hurt", "injury", "threat", "threaten",
        "threatening", "locked", "confinement", "forced", "coercion",
        "criminal complaint", "arrest", "arrested",
    )) and not _has_negated_family_criminal_force_context(query_lower)


def _has_marriage_validity_source_context(query_lower: str) -> bool:
    return _has(query_lower, (
        "hindu", "special marriage", "sma", "registered marriage",
        "court marriage", "voidable", "annulment", "annul", "fraud",
        "lied before marriage", "before marriage", "hidden", "concealed",
        "hid", "misrepresented", "misrepresentation", "gay", "lesbian",
        "same sex", "same-sex", "sexual orientation", "already married",
        "previous marriage", "prior marriage", "job", "salary", "health",
        "disease", "hiv", "adultery", "affair", "another woman",
        "another man", "caught", "having sex", "extra marital",
        "extramarital",
    ))


def _has_hindu_marriage_section_13_ground_anchor(item_blob: str) -> bool:
    if _has_any_exact_anchor(item_blob, ("sec-13", "/sec-13")):
        return True
    # The indexed HMA corpus splits some Section 13 grounds as sec-13-a/c/d,
    # while true neighboring sections appear as sec-13A/sec-13B. Accept only
    # the ground fragments we have verified from the corpus, not 13A/13B.
    return _has_any_exact_anchor(item_blob, (
        "sec-13-a", "sec-13-c", "sec-13-d",
        "/sec-13-a", "/sec-13-c", "/sec-13-d",
    ))


def _has_any_exact_anchor(blob: str, anchors: tuple[str, ...]) -> bool:
    return any(_exact_anchor_term_matches(blob, anchor) for anchor in anchors)


def _valid_anchor_snapshot(anchor: str) -> bool:
    """Reject malformed or impossible @YYYY-MM-DD corpus snapshots."""
    raw_parts = re.findall(r"@([^/]+)", str(anchor or ""))
    if not raw_parts:
        return True
    if str(anchor or "").count("@") != len(raw_parts):
        return False
    for raw in raw_parts:
        token = raw.split("__", 1)[0]
        try:
            date.fromisoformat(token)
        except ValueError:
            return False
    return True


def _anchor_term_matches(blob: str, anchor: str) -> bool:
    normalized = anchor.lower().lstrip("/")
    if normalized.startswith("#"):
        return normalized in blob
    return bool(re.search(rf"(?<![a-z0-9])/?{re.escape(normalized)}(?![a-z0-9])", blob))


def _exact_anchor_term_matches(blob: str, anchor: str) -> bool:
    normalized = anchor.lower().lstrip("/")
    if normalized.startswith("#"):
        return normalized in blob
    official_suffix = "" if normalized.endswith("-official") else "(?:-official)?"
    return bool(
        re.search(
            rf"(?<![a-z0-9])/?{re.escape(normalized)}{official_suffix}(?![-a-z0-9])",
            blob,
        )
    )


def _single_statute_section_match(
    required_lower: str,
    item_blob: str,
    *,
    passage_text: str | None = None,
) -> bool:
    section_numbers = re.findall(r"\b(?:section|sec|s)\.?\s*([0-9]+[a-z]?)\b", required_lower)
    if not section_numbers:
        return False
    statute_terms = (
        (("bnss", "bharatiya nagarik"), ("bnss", "bharatiya nagarik")),
        (("crpc", "code of criminal procedure", "criminal procedure"), ("crpc", "code of criminal procedure", "criminal procedure")),
        (("bns", "bharatiya nyaya"), ("bns", "bharatiya nyaya")),
        (("ipc", "indian penal"), ("ipc", "indian penal")),
        (("code on wages",), ("code on wages",)),
        (("industrial disputes",), ("industrial disputes",)),
        (("indian contract", "contract act"), ("indian contract", "contract act")),
        (("constitution",), ("constitution",)),
        (("maharashtra control of organised crime", "mcoca"), ("maharashtra control of organised crime", "mcoca")),
    )
    if not any(
        _has_statute_alias(required_lower, required_terms)
        and _has_statute_alias(item_blob, item_terms)
        for required_terms, item_terms in statute_terms
    ):
        return False
    return any(
        _section_anchor_matches(item_blob, section, passage_text=passage_text)
        for section in section_numbers
    )


def _section_anchor_matches(
    item_blob: str,
    section: str,
    *,
    passage_text: str | None = None,
) -> bool:
    normalized = section.lower()
    subsection_match = re.fullmatch(r"([0-9]+)\(([0-9a-z]+)\)", normalized)
    if subsection_match is not None:
        numeric, subsection = subsection_match.groups()
        candidates = (
            f"sec-{numeric}-{subsection}",
            f"/sec-{numeric}-{subsection}",
            f"sec-{numeric}({subsection})",
            f"/sec-{numeric}({subsection})",
        )
        # BNSS Section 173(4) is published by this corpus under the stable
        # split anchor sec-173-c. The heading remains mandatory identity
        # evidence so neighbouring 173-a/173-b chunks cannot satisfy it.
        if numeric == "173" and subsection == "4":
            candidates += ("sec-173-c", "/sec-173-c")
        if not _has_any_exact_anchor(item_blob, candidates):
            return False
        return bool(passage_text) and _passage_heading_matches_section(
            passage_text,
            normalized,
        )
    section_match = re.fullmatch(r"([0-9]+)([a-z])?", normalized)
    if section_match is None:
        return _has_any_exact_anchor(item_blob, (f"sec-{normalized}", f"/sec-{normalized}"))
    numeric, suffix = section_match.groups()
    exact_anchor = _has_any_exact_anchor(
        item_blob,
        (f"sec-{normalized}", f"/sec-{normalized}"),
    )
    if exact_anchor:
        if not suffix:
            return True
        # A native alphanumeric anchor such as sec-66e is already distinct
        # from a split alias such as sec-142-a. Only the split representation
        # needs the passage-heading check below.
        if _has_any_exact_anchor(
            item_blob,
            (f"sec-{numeric}{suffix}", f"/sec-{numeric}{suffix}"),
        ):
            return True
        # An explicit alphanumeric provision such as Section 142A may be
        # represented by the normalized split anchor sec-142-a. Require the
        # passage heading so a metadata alias cannot prove identity alone.
        if not passage_text:
            return False
        headings = re.finditer(
            r"\b(?:section|sec\.?|article|order|clause)\s+([0-9][0-9a-z()./-]*)",
            passage_text[:600],
            flags=re.IGNORECASE,
        )
        expected = re.sub(r"[^0-9a-z]+", "", normalized)
        return any(
            re.sub(r"[^0-9a-z]+", "", match.group(1).lower()) == expected
            for match in headings
        )
    if suffix:
        split_anchor = _has_any_exact_anchor(
            item_blob,
            (f"sec-{numeric}-{suffix}", f"/sec-{numeric}-{suffix}"),
        )
    else:
        # Some official Act PDFs are chunked as sec-142-a ... sec-142-e even
        # though the legal provision is Section 142. Do not accept a suffix
        # from metadata alone: Section 142A is a neighboring provision.
        split_anchor = re.search(
            rf"(?<![a-z0-9])/?sec-{re.escape(numeric)}-[a-z]"
            rf"(?:-official)?(?![a-z0-9])",
            item_blob,
            flags=re.IGNORECASE,
        ) is not None
    if not split_anchor:
        return False
    # A suffix may represent a split chunk of the requested numeric section,
    # or a distinct alphanumeric provision such as Section 142A. Metadata
    # alone cannot distinguish them, so the serving path requires the
    # passage heading.
    if not passage_text:
        return False
    return _passage_heading_matches_section(passage_text, normalized)


def _required_title_matches_item(required_lower: str, item_blob: str) -> bool:
    """Return true when an explicit Act/Code title is present in a passage.

    This is deliberately a conservative token check. It is only used when a
    requirement names a concrete section; a title match activates the strict
    section matcher and prevents a later broad fallback from accepting a
    neighboring provision.
    """
    section_match = re.search(
        r"\b(?:section|sec|s)\.?\s*[0-9]+[a-z]?\b",
        required_lower,
    )
    if section_match is None:
        return False
    prefix = required_lower[: section_match.start()]
    # Route prose after the authority title should not become part of the
    # identity check ("for limitation", "where relevant", and similar).
    prefix = re.split(
        r"\b(?:for|where|based|only|under|as|with|from|relevant|source|provision)\b",
        prefix,
        maxsplit=1,
    )[0]
    stopwords = {
        "a", "an", "and", "as", "act", "application", "authority", "based",
        "code", "of", "on", "or", "section", "s", "the", "to", "under",
        "where", "with",
    }
    tokens = [
        token
        for token in re.findall(r"[a-z0-9]+", prefix)
        if token not in stopwords and not token.isdigit() and len(token) > 1
    ]
    if not tokens:
        return False
    return all(
        re.search(rf"(?<![a-z0-9]){re.escape(token)}(?![a-z0-9])", item_blob)
        is not None
        for token in tokens
    )


def _constitutional_passage_matches_reviewed_plan(
    passage: dict[str, Any],
    retrieval_sources: list[Any] | None,
    article_number: str | None = None,
) -> bool:
    """Require pack identity when a MatterPlan provenance contract exists."""
    if retrieval_sources is None:
        title = re.sub(r"[^a-z0-9]+", " ", str(passage.get("title") or "").lower()).strip()
        source_type = str(passage.get("source_type") or "").strip().lower()
        anchor = str(passage.get("anchor") or "").strip()
        document_prefix = re.split(r"[/#]", anchor, maxsplit=1)[0]
        required_source_pack = str(passage.get("required_source_pack") or "").strip()
        if title != "constitution of india" or source_type != "bare_act":
            return False
        if document_prefix not in {"constitution-india", "constitution-of-india"}:
            return False
        if required_source_pack:
            if not required_source_pack.startswith("constitution_"):
                return False
            scope_match = re.match(
                r"^constitution_article_(?P<scope>[0-9a-z_]+)$",
                required_source_pack,
            )
            if scope_match is not None:
                scope_numbers = set(
                    re.findall(r"(?<![a-z])[0-9]+[a-z]?", scope_match.group("scope"))
                )
                if article_number and article_number not in scope_numbers:
                    return False
        if article_number and not _has_any_exact_anchor(
            str(passage.get("anchor") or "").lower(),
            (
                f"sec-{article_number}",
                f"/sec-{article_number}",
                f"article-{article_number}",
                f"/article-{article_number}",
            ),
        ):
            return False
        return True
    source_pack_id = str(passage.get("required_source_pack") or "").strip()
    source = next(
        (
            candidate
            for candidate in retrieval_sources
            if str(getattr(candidate, "source_pack_id", "")) == source_pack_id
        ),
        None,
    )
    if source is None:
        return False
    if not _source_pack_title_matches(
        passage.get("title"),
        getattr(source, "title_patterns", ()) or (),
        allow_known_document_suffix=bool(getattr(source, "doc_ids", ()) or ()),
    ):
        return False
    passage_source_type = str(passage.get("source_type") or "").strip()
    if not passage_source_type or passage_source_type not in getattr(source, "source_types", ()):
        return False
    anchor = str(passage.get("anchor") or "").strip()
    if not anchor or not getattr(source, "doc_ids", None):
        return False
    document_prefix = re.split(r"[/#]", anchor, maxsplit=1)[0]
    if document_prefix not in {str(doc_id) for doc_id in source.doc_ids}:
        return False
    if not article_number:
        return True
    anchor_patterns = tuple(getattr(source, "anchor_patterns", ()) or ())
    return bool(anchor_patterns) and any(
        _source_pack_anchor_matches(anchor, pattern)
        for pattern in anchor_patterns
    )


def _constitution_article_requirement_match(
    required_source: str,
    passages: list[dict[str, Any]],
    *,
    retrieval_sources: list[Any] | None = None,
) -> dict[str, Any] | None:
    def article_anchor_matches(item: dict[str, Any], number: str) -> bool:
        if not _constitutional_passage_matches_reviewed_plan(
            item,
            retrieval_sources,
            article_number=number,
        ):
            return False
        blob = _item_blob(item)
        return _section_anchor_matches(
            blob,
            number,
            passage_text=_passage_identity_text(item),
        ) or _has_any_exact_anchor(
            blob,
            (f"article-{number}", f"/article-{number}"),
        )

    lower = required_source.lower()
    article_numbers = sorted(_constitution_article_numbers(lower))
    if (
        ("lawyer-access" in lower or "lawyer access" in lower)
        and article_numbers == ["22"]
    ):
        for item in passages or []:
            if not isinstance(item, dict):
                continue
            blob = _item_blob(item)
            if _has(blob, ("constitution",)) and article_anchor_matches(item, "22"):
                return item
    if not article_numbers:
        return None
    if len(article_numbers) == 1:
        number = article_numbers[0]
        for item in passages or []:
            if not isinstance(item, dict):
                continue
            blob = _item_blob(item)
            if _has(blob, ("constitution",)) and article_anchor_matches(item, number):
                return item
        return None
    found: dict[str, dict[str, Any]] = {}
    for item in passages or []:
        if not isinstance(item, dict):
            continue
        blob = _item_blob(item)
        if not _has(blob, ("constitution",)):
            continue
        for number in article_numbers:
            if article_anchor_matches(item, number):
                found[number] = item
    if all(number in found for number in article_numbers):
        return {
            "title": "Constitution composite article source",
            "anchor": "; ".join(str(found[number].get("anchor") or "") for number in article_numbers),
            "source_type": "aggregate",
        }
    return None


def _query_points_to_old_criminal_regime(query_lower: str) -> bool:
    if _has(query_lower, (
        "before 1 july 2024", "before 01 july 2024", "before july 2024",
        "pre july 2024", "pre-july 2024", "pre-2024",
        "prior to 1 july 2024", "prior to 01 july 2024",
        "until 1 july 2024", "until 01 july 2024",
        "till 1 july 2024", "till 01 july 2024",
    )):
        return True
    if re.search(r"\b(?:before|pre|prior to|until|till)\s+0?1[-/]0?7[-/]2024\b", query_lower) is not None:
        return True
    if re.search(r"\b(?:before|pre|prior to|until|till)\s+2024[-/]0?7[-/]0?1\b", query_lower) is not None:
        return True
    if (
        re.search(r"\bjuly\s+1(?:st)?\s*,?\s*2024\b", query_lower) is not None
        and _has(query_lower, ("before", "pre", "prior to", "until", "till"))
    ):
        return True
    return any(marker < (2024, 7, 1) for marker in _criminal_regime_date_markers(query_lower))


def _query_points_to_new_criminal_regime(query_lower: str) -> bool:
    if _query_points_to_old_criminal_regime(query_lower):
        return False
    if _has(query_lower, ("after 1 july 2024", "after july 2024", "from 1 july 2024", "new bnss")):
        return True
    return any(marker >= (2024, 7, 1) for marker in _criminal_regime_date_markers(query_lower))


def _criminal_regime_date_markers(query_lower: str) -> list[tuple[int, int, int]]:
    markers: list[tuple[int, int, int]] = []
    month_names = {
        "jan": 1, "january": 1,
        "feb": 2, "february": 2,
        "mar": 3, "march": 3,
        "apr": 4, "april": 4,
        "may": 5,
        "jun": 6, "june": 6,
        "jul": 7, "july": 7,
        "aug": 8, "august": 8,
        "sep": 9, "sept": 9, "september": 9,
        "oct": 10, "october": 10,
        "nov": 11, "november": 11,
        "dec": 12, "december": 12,
    }
    for match in re.finditer(
        r"\b(?:(?P<day>\d{1,2})(?:st|nd|rd|th)?\s+)?(?P<month>jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|jul(?:y)?|aug(?:ust)?|sep(?:t|tember)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)\s*,?\s*(?P<year>20\d{2})\b",
        query_lower,
    ):
        year = int(match.group("year"))
        month = month_names[match.group("month")]
        day = int(match.group("day") or 1)
        markers.append((year, month, day))
    for match in re.finditer(r"\b(?P<year>20\d{2})[-/](?P<month>\d{1,2})(?:[-/](?P<day>\d{1,2}))?\b", query_lower):
        year = int(match.group("year"))
        month = int(match.group("month"))
        day = int(match.group("day") or 1)
        if 1 <= month <= 12 and 1 <= day <= 31:
            markers.append((year, month, day))
    for match in re.finditer(r"\b(?P<day>\d{1,2})[-/](?P<month>\d{1,2})[-/](?P<year>20\d{2})\b", query_lower):
        year = int(match.group("year"))
        month = int(match.group("month"))
        day = int(match.group("day"))
        if 1 <= month <= 12 and 1 <= day <= 31:
            markers.append((year, month, day))
    if markers:
        return markers
    for match in re.finditer(r"\b(?:fir from|fir|incident in|incident|arrested in|case from|from|in)\s+(?P<year>20\d{2})\b", query_lower):
        year = int(match.group("year"))
        if year <= 2023:
            markers.append((year, 1, 1))
        elif year >= 2025:
            markers.append((year, 1, 1))
    return markers


def _looks_like_authority(lower: str) -> bool:
    return (
        bool(re.search(r"\bact\b|\bcode\b|\bregulations?\b|\brules?\b|\barticle\s+\d+", lower))
        or _has(lower, (
            "bns", "bnss", "bharatiya nyaya sanhita",
            "bharatiya nagarik suraksha sanhita",
            "bharatiya sakshya adhiniyam", "crpc", "ipc", "constitution", "ombudsman",
            "rbi", "cgst", "gst", "income tax", "customs", "pmla", "pocso",
            "pwdva", "nalsa", "dlsa", "statute", "nclt", "nclat",
            "compoundability", "compoundable", "compounding",
        ))
    )


def _source_tokens(text: str) -> set[str]:
    raw = re.findall(r"[a-z0-9]+", text.lower())
    return {token for token in raw if len(token) >= 3 and token not in _STOPWORDS}


def _coverage_score(tokens: set[str], blob: str) -> float:
    if not tokens:
        return 0.0
    hits = sum(1 for token in tokens if token in blob)
    return hits / len(tokens)


def _threshold(tokens: set[str]) -> float:
    if len(tokens) <= 2:
        return 1.0
    if len(tokens) <= 5:
        return 0.8
    return 0.65


def _item_blob(item: dict[str, Any]) -> str:
    return _blob(
        item.get("title"),
        item.get("anchor"),
        item.get("citation"),
        item.get("court"),
        item.get("source_type"),
        item.get("document_id"),
        item.get("statute_short"),
    )


def _blob(*parts: Any) -> str:
    values: list[str] = []
    for part in parts:
        if part is None:
            continue
        if isinstance(part, list):
            values.extend(str(item) for item in part)
        else:
            values.append(str(part))
    text = re.sub(r"\s+", " ", " ".join(values).lower())
    dehyphenated = text.replace("-", " ")
    return f"{text} {dehyphenated}" if dehyphenated != text else text


def _has(blob: str, terms: tuple[str, ...]) -> bool:
    return any(term in blob for term in terms)


def _has_trigger_term(blob: str, terms: tuple[str, ...]) -> bool:
    for term in terms:
        normalized = term.lower()
        if re.fullmatch(r"[a-z0-9]+", normalized):
            if re.search(rf"(?<![a-z0-9]){re.escape(normalized)}(?![a-z0-9])", blob):
                return True
            continue
        if normalized in blob:
            return True
    return False


def _has_statute_alias(blob: str, terms: tuple[str, ...]) -> bool:
    for term in terms:
        normalized = term.lower()
        if normalized in {"bns", "bnss", "ipc", "crpc"}:
            if re.search(rf"(?<![a-z0-9]){re.escape(normalized)}(?![a-z0-9])", blob):
                return True
            continue
        if normalized in blob:
            return True
    return False


def _is_delhi_prison_rules_blob(blob: str) -> bool:
    return "delhi prison rules" in blob or "delhi-prison-rules-2018" in blob


def _has_delhi_prison_query_context(query: str) -> bool:
    if _has(query, (
        "tihar", "mandoli", "rohini jail", "rohini prison",
        "delhi jail", "delhi prison", "central jail delhi",
    )):
        return True
    return "delhi" in query and _has(query, (
        "jail", "prison", "prisoner", "mulaqat", "mulakat",
        "parole", "furlough", "superintendent",
    ))


def _is_pmla_sc_precedent_requirement(required_lower: str) -> bool:
    return (
        "pmla" in required_lower
        and ("supreme court" in required_lower or "precedent" in required_lower)
    )


def _pmla_sc_precedent_item_matches(item_blob: str) -> bool:
    return (
        (
            "sc_judgment" in item_blob
            or "supreme court" in item_blob
            or re.search(r"(?<![a-z0-9])20\d{2}-insc", item_blob) is not None
        )
        and _has(item_blob, (
            "pmla", "money laundering", "prevention of money laundering",
            "vijay madanlal", "nikesh tarachand", "pankaj bansal",
            "senthil balaji", "saumya chaurasia", "tarsem lal",
        ))
    )
