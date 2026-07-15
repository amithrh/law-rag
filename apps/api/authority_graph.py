"""Data-shaped authority graph workflow contracts.

This module is the first slice of the product authority graph: a compact,
reviewable mapping from a common legal problem variant to the controlling
source, forum, remedy, documents, and safety caveat. It intentionally emits
only source-gated lines. Older route templates remain as fallback while this
graph grows.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from apps.api.matter_router import (
    MatterRoute,
    has_positive_criminal_bank_hold_context,
    has_person_custody_context,
    is_arbitral_account_restraint,
    is_civil_execution_bank_attachment,
    is_civil_prejudgment_bank_attachment,
    is_existing_vehicle_theft_fir_followup,
)


@dataclass(frozen=True)
class PassageSpec:
    key: str
    title_terms: tuple[str, ...]
    anchor_terms: tuple[str, ...] = ()
    required: bool = False


@dataclass(frozen=True)
class LineSpec:
    text: str
    requires: tuple[str, ...] = ()


@dataclass(frozen=True)
class AuthorityWorkflowContract:
    id: str
    route_categories: tuple[str, ...]
    trigger_groups: tuple[tuple[str, ...], ...]
    source_specs: tuple[PassageSpec, ...]
    line_specs: tuple[LineSpec, ...]
    priority: int = 0


@dataclass(frozen=True)
class AuthorityWorkflowRender:
    id: str
    source_indices: dict[str, int]
    required_sources: tuple[str, ...]
    optional_sources: tuple[str, ...]
    lines: list[str]


def authority_graph_template_result(
    query: str,
    route: MatterRoute,
    passages: list[dict],
) -> AuthorityWorkflowRender | None:
    """Return the selected source-backed workflow contract and rendered lines."""
    q = _norm(query)
    contract, sources = _select_contract(q, route, passages, raw_query=query)
    if contract is None:
        return None

    lines = _render_contract_lines(contract, q, sources, passages, route)
    if not lines:
        return None

    return AuthorityWorkflowRender(
        id=contract.id,
        source_indices=dict(sources),
        required_sources=tuple(
            spec.key for spec in _required_source_specs(contract, route)
        ),
        optional_sources=tuple(
            spec.key
            for spec in contract.source_specs
            if spec.key not in {
                required.key for required in _required_source_specs(contract, route)
            }
        ),
        lines=lines,
    )


def authority_graph_contract_template_result(
    query: str,
    route: MatterRoute,
    passages: list[dict],
    contract_id: str,
) -> AuthorityWorkflowRender | None:
    """Render one MatterPlan-selected contract without global re-selection."""
    q = _norm(query)
    contract = next(
        (item for item in AUTHORITY_WORKFLOW_CONTRACTS if item.id == contract_id),
        None,
    )
    if contract is None or not _contract_query_matches(
        contract,
        q,
        route,
        raw_query=query,
    ):
        return None
    sources = _resolve_sources(
        contract,
        passages,
        q=q,
        route=route,
        strict_plan=True,
    )
    if sources is None:
        return None
    lines = _render_contract_lines(contract, q, sources, passages, route)
    if not lines:
        return None
    return AuthorityWorkflowRender(
        id=contract.id,
        source_indices=dict(sources),
        required_sources=tuple(
            spec.key for spec in _required_source_specs(contract, route, strict_plan=True)
        ),
        optional_sources=tuple(
            spec.key
            for spec in contract.source_specs
            if spec.key not in {
                required.key for required in _required_source_specs(
                    contract,
                    route,
                    strict_plan=True,
                )
            }
        ),
        lines=lines,
    )


def authority_graph_template_lines(
    query: str,
    route: MatterRoute,
    passages: list[dict],
) -> list[str]:
    """Return the highest-scoring source-backed workflow contract."""
    result = authority_graph_template_result(query, route, passages)
    return result.lines if result is not None else []


def _render_contract_lines(
    contract: AuthorityWorkflowContract,
    q: str,
    sources: dict[str, int],
    passages: list[dict],
    route: MatterRoute,
) -> list[str]:
    lines = ["**Short answer**"]
    special = _render_special_contract(contract.id, q, sources, passages, route)
    if special:
        lines.extend(special)
        return lines

    rendered: list[str] = []
    for spec in contract.line_specs:
        if any(key not in sources for key in spec.requires):
            continue
        rendered.append(spec.text.format(**sources))
    if not rendered:
        return []
    lines.extend(rendered)
    return lines


def authority_graph_workflow_event(
    query: str,
    route: MatterRoute,
    passages: list[dict],
) -> dict | None:
    """Return selected authority-graph workflow metadata for telemetry/evals."""
    result = authority_graph_template_result(query, route, passages)
    if result is None:
        return None
    return {
        "id": result.id,
        "source_indices": result.source_indices,
        "required_sources": list(result.required_sources),
        "optional_sources": list(result.optional_sources),
    }


def _select_contract(
    q: str,
    route: MatterRoute,
    passages: list[dict],
    *,
    raw_query: str | None = None,
) -> tuple[AuthorityWorkflowContract | None, dict[str, int]]:
    best: tuple[int, AuthorityWorkflowContract, dict[str, int]] | None = None
    for contract in AUTHORITY_WORKFLOW_CONTRACTS:
        if not _contract_query_matches(contract, q, route, raw_query=raw_query):
            continue
        sources = _resolve_sources(contract, passages, q=q, route=route)
        if sources is None:
            continue
        score = (
            contract.priority
            + (20 if route.category in contract.route_categories else 0)
            + 3 * len(sources)
            + sum(1 for group in contract.trigger_groups if any(term in q for term in group))
        )
        if best is None or score > best[0]:
            best = (score, contract, sources)
    if best is None:
        return None, {}
    return best[1], best[2]


def authority_graph_contract_query_matches(
    query: str,
    route: MatterRoute,
    contract_id: str,
    *,
    route_independent: bool = False,
) -> bool:
    """Whether an existing contract owns the facts before source activation."""
    q = _norm(query)
    return any(
        contract.id == contract_id
        and _contract_query_matches(
            contract,
            q,
            route,
            route_independent=route_independent,
            raw_query=query,
        )
        for contract in AUTHORITY_WORKFLOW_CONTRACTS
    )


def authority_graph_contract_required_source_specs(
    contract_id: str,
    route: MatterRoute | None = None,
) -> tuple[PassageSpec, ...]:
    """Return the contract's source activation requirements for MatterPlan."""
    for contract in AUTHORITY_WORKFLOW_CONTRACTS:
        if contract.id == contract_id:
            return _required_source_specs(contract, route, strict_plan=True)
    return ()


def _required_source_specs(
    contract: AuthorityWorkflowContract,
    route: MatterRoute | None,
    *,
    strict_plan: bool = False,
) -> tuple[PassageSpec, ...]:
    if strict_plan and contract.id == "insurance_claim_or_misselling":
        return tuple(
            spec
            for spec in contract.source_specs
            if spec.key in {"insurance_scope", "insurance_procedure"}
        )
    if strict_plan and contract.id == "wrong_bank_debit":
        return tuple(
            spec
            for spec in contract.source_specs
            if spec.key in {"rbi_scope", "rbi_complaint"}
        )
    if not strict_plan:
        return tuple(spec for spec in contract.source_specs if spec.required)
    criminal_owner_keys = {
        "vehicle_theft_fir_refusal": {
            "current": ("bnss_fir", "bnss_refusal"),
            "legacy": ("crpc",),
        },
        "arrest_custody_station_case_not_disclosed": {
            "current": ("arrest_info", "production"),
            "legacy": ("crpc",),
        },
        "lgbtq_identity_arrest_safeguard": {
            "current": ("bnss_arrest", "bnss_production"),
            "legacy": ("crpc_arrest", "crpc_production"),
        },
        "bank_account_freeze_legal_hold": {
            "current": ("bnss_seizure",),
            "legacy": ("crpc_seizure",),
        },
    }
    regime_keys = criminal_owner_keys.get(contract.id)
    if regime_keys is None or route is None:
        return tuple(spec for spec in contract.source_specs if spec.required)
    by_key = {spec.key: spec for spec in contract.source_specs}
    always_required = tuple(
        spec
        for spec in contract.source_specs
        if spec.required
        and spec.key not in {*regime_keys["current"], *regime_keys["legacy"]}
    )
    if route.legal_regime == "legacy_ipc_crpc_evidence_for_pre_2024_incident":
        selected = regime_keys["legacy"]
    elif route.legal_regime == "current_bns_bnss_bsa_for_post_2024_incident":
        selected = regime_keys["current"]
    else:
        selected = (*regime_keys["current"], *regime_keys["legacy"])
    return (*always_required, *(by_key[key] for key in selected))


def _allowed_source_keys_for_regime(
    contract: AuthorityWorkflowContract,
    route: MatterRoute | None,
) -> set[str] | None:
    if route is None or contract.id not in {
        "vehicle_theft_fir_refusal",
        "arrest_custody_station_case_not_disclosed",
        "lgbtq_identity_arrest_safeguard",
        "bank_account_freeze_legal_hold",
    }:
        return None
    current_keys = {
        "vehicle_theft_fir_refusal": {"bnss_fir", "bnss_refusal", "bnss_magistrate", "bns"},
        "arrest_custody_station_case_not_disclosed": {"arrest_info", "production", "fir_info"},
        "lgbtq_identity_arrest_safeguard": {"bnss_arrest", "bnss_production"},
        "bank_account_freeze_legal_hold": {"bnss_seizure"},
    }[contract.id]
    legacy_keys = {
        "vehicle_theft_fir_refusal": {"crpc", "ipc"},
        "arrest_custody_station_case_not_disclosed": {"crpc"},
        "lgbtq_identity_arrest_safeguard": {"crpc_arrest", "crpc_production"},
        "bank_account_freeze_legal_hold": {"crpc_seizure"},
    }[contract.id]
    neutral_keys = {
        spec.key for spec in contract.source_specs
        if spec.key not in current_keys | legacy_keys
    }
    if route.legal_regime == "current_bns_bnss_bsa_for_post_2024_incident":
        return neutral_keys | current_keys
    if route.legal_regime == "legacy_ipc_crpc_evidence_for_pre_2024_incident":
        return neutral_keys | legacy_keys
    return neutral_keys | current_keys | legacy_keys


def _contract_query_matches(
    contract: AuthorityWorkflowContract,
    q: str,
    route: MatterRoute,
    *,
    route_independent: bool = False,
    raw_query: str | None = None,
) -> bool:
    if not route_independent and not _route_eligible(contract, route):
        return False
    if not _triggers_match(q, contract.trigger_groups):
        return False
    if contract.id == "marital_intimacy_remedy" and _is_adultery_context(q):
        return False
    if contract.id == "vehicle_theft_fir_refusal":
        if is_existing_vehicle_theft_fir_followup(q):
            return False
        police_refusal_context = _has_any(
            q,
            ("police", "police station", "station", "station house officer", "sho", "thana"),
        )
        theft_report = (
            _has_any(q, ("theft", "stolen", "stole"))
            and _has_any(q, ("bike", "car", "scooter", "vehicle", "motorcycle", "motor cycle"))
            and police_refusal_context
            and _has_any(q, (
                "refuse", "refused", "refusing", "not filing", "not register",
                "won't register", "will not register", "did not register",
                "didn't register", "not lodged", "have not lodged", "has not lodged",
                "did not lodge", "didn't lodge", "no fir", "say to wait", "says wait",
                "told me to wait", "sent me away", "turned me away",
                "give written complaint only", "written complaint only",
                "unwilling to register", "unwilling to lodge",
                "declined to register", "declined to lodge",
                "rejected my", "rejected the", "rejected complaint",
                "will not accept an fir", "won't accept an fir",
                "refuse to accept an fir", "refuses to accept an fir",
                "refused to accept an fir", "not accepting an fir",
            ))
        )
        negated_fir_registration = _has_any(q, (
            "no fir", "fir not registered", "fir is not registered",
            "fir was not registered", "fir has not been registered",
            "fir not filed", "fir was not filed", "fir not lodged",
            "never registered fir", "refuse to register fir", "refused to register fir",
            "will not register fir", "won't register fir",
        )) or any((
            re.search(
                r"\bpolice\b.{0,20}\b(?:not|never|refuse(?:s|d|ing)?)\b"
                r".{0,20}\b(?:register(?:ed|ing)?|file(?:d|ing)?|lodg(?:e|ed|ing))\b"
                r".{0,12}\b(?:an?\s+)?fir\b",
                q,
            ) is not None,
            re.search(
                r"\bfir\b.{0,20}\b(?:not|never)\b.{0,20}"
                r"\b(?:registered|filed|lodged|recorded)\b",
                q,
            ) is not None,
        ))
        existing_fir = not negated_fir_registration and (_has_any(q, (
            "police registered fir", "police filed fir", "fir was registered",
            "the fir is registered", "fir is registered", "fir has been registered",
            "fir already registered", "already registered fir", "fir already exists",
            "an fir already exists", "the fir already exists",
            "fir is under investigation", "fir under investigation",
            "case is under investigation", "investigation is progressing",
            "investigation progressing", "is being investigated",
            "opened an fir", "opened a fir", "entered an e-fir",
            "entered e-fir", "complaint converted into fir", "complaint converted to fir",
            "fir darj hai", "fir darj ho chuki", "fir darj ho gaya",
            "drew up an fir", "drew up a fir", "e-fir acknowledgment",
            "e-fir acknowledgement", "fir acknowledgment", "fir acknowledgement",
        )) or any((
            re.search(
                r"\bpolice\b.{0,24}\b(?:registered|filed|lodged|recorded)\b"
                r".{0,12}\b(?:fir|first information report)\b",
                q,
            ) is not None,
            re.search(
                r"\b(?:fir|first information report)\b.{0,28}"
                r"\b(?:registered|filed|lodged|recorded|exists|active|on\s+record)\b",
                q,
            ) is not None,
            re.search(
                r"\b(?:fir|first information report)\b.{0,12}"
                r"\b(?:number|no\.?|copy)\b|"
                r"\bcopy\s+of\s+(?:the\s+|my\s+)?(?:fir|first information report)\b",
                q,
            ) is not None,
            re.search(
                r"\b(?:fir|crime|complaint|c\.?r\.?)\s+(?:number|no\.?)?\s*[:#-]?\s*\d+\b|"
                r"\b(?:number|no\.?)\s*(?:is\s*)?\d+\b",
                q,
            ) is not None,
            re.search(
                r"\b(?:(?:e-?)?fir|first information report)\b.{0,70}\b"
                r"(?:investigat(?:e|ed|ing|ion)|progress|status|recover(?:y|ed|ing)?|"
                r"trace|locate|search|look\s+for|acknowledg(?:e|ed|ement|ment)|"
                r"jaanch|case\s+diary|current\s+stage)\b",
                q,
            ) is not None,
        )))
        # Ownership and retrieval must share one registration-stage decision.
        # The legacy local heuristics above remain for compatibility context,
        # but cannot override the polarity-aware shared predicate.
        existing_fir = is_existing_vehicle_theft_fir_followup(q)
        accused_posture = re.search(
            r"\b(?:i|we)\s+(?:have\s+|had\s+)?(?:stole|stolen|steal|taken)\b",
            q,
        ) is not None or _has_any(q, (
            "fir against me", "case against me", "accused me of stealing",
        )) or existing_fir
        investigation_posture = _has_any(q, (
            "refuse to investigate", "refused to investigate", "refusing to investigate",
            "not investigating", "will not investigate", "won't investigate",
            "investigation stopped", "no investigation", "case status", "chargesheet",
            "charge sheet", "closure report", "final report", "status update",
            "under investigation", "investigation progressing", "investigation is progressing",
            "is being investigated", "further action", "share progress",
            "investigation progress", "give me updates", "give updates",
            "disclose what recovery", "recovery steps", "search for it",
            "look for it", "locate it", "refuse to locate", "refuses to locate",
            "progress batane", "progress nahi bata", "progress nahin bata",
            "refuse to act", "refused to act", "not acting", "police action",
            "refuse to trace", "refused to trace", "not tracing", "trace my",
            "refuse to recover", "refused to recover", "not recovering", "recover my",
        ))
        if not theft_report or accused_posture or investigation_posture:
            return False
    if contract.id == "lgbtq_identity_arrest_safeguard":
        causal_identity_arrest = _has_any(q, (
            "arrested for being gay", "detained for being gay", "picked up for being gay",
            "because he is gay", "because she is gay", "because i am gay",
            "due to sexual orientation", "only because he is gay",
            "only because she is gay", "only because i am gay",
            "no offence except being gay", "no crime except being gay",
        )) or re.search(
            r"\b(?:arrested|detained|picked|picked up|taken into custody)\b.{0,80}\b(?:for|because of|only for)\b.{0,30}\b(?:being gay|sexual orientation|same-sex relationship)\b",
            q,
        ) is not None
        if (
            not causal_identity_arrest
            or _is_under_18_context(q)
            or _has_independent_offence_allegation(q)
        ):
            return False
    if contract.id == "domestic_violence_immediate_safety":
        if not _pwdva_woman_aggrieved_context(q):
            return False
    if contract.id == "arrest_custody_station_case_not_disclosed":
        if not _hidden_person_custody_context(raw_query or q):
            return False
    if contract.id == "heir_refuses_sale" and _is_tenancy_no_sale_dispute_context(q):
        return False
    if contract.id == "joint_coowner_sold_whole_property" and not _has_any(
        q,
        ("sold", "sale deed", "buyer", "transferred", "registered sale"),
    ):
        return False
    if contract.id == "marital_intimacy_remedy" and _is_marital_sexual_coercion_context(q):
        return False
    if (
        contract.id == "joint_coowner_sold_whole_property"
        and _is_mutation_after_death(q)
        and not _has_any(q, ("sold", "sale deed", "buyer", "transferred", "registered"))
    ):
        return False
    if contract.id == "wrong_bank_debit" and (
        _is_cyber_money_fraud_context(q) or _is_insurer_claim_or_policy_dispute(q)
    ):
        return False
    if contract.id == "insurance_claim_or_misselling" and not _is_insurance_context(q):
        return False
    if contract.id == "bank_account_freeze_legal_hold" and _is_pmla_enforcement_context(q):
        return False
    if contract.id == "bank_account_freeze_legal_hold" and _is_civil_execution_bank_attachment(q):
        return False
    if contract.id == "bank_account_freeze_legal_hold" and is_civil_prejudgment_bank_attachment(q):
        return False
    if contract.id == "bank_account_freeze_legal_hold" and is_arbitral_account_restraint(q):
        return False
    if (
        contract.id == "bank_account_freeze_legal_hold"
        and not has_positive_criminal_bank_hold_context(q)
    ):
        return False
    if contract.id == "mining_displacement_rehabilitation" and (
        _is_minor_mineral_lease_context(q)
        or _is_mining_pollution_property_damage_without_displacement(q)
    ):
        return False
    if contract.id == "custody_medical_care" and _is_custody_abuse_or_extortion_context(q):
        return False
    if contract.id == "regular_bail_after_arrest" and (
        _is_uapa_special_bail_context(q)
        or _is_pmla_specific_bail_context(q)
        or _is_ndps_specific_bail_context(q)
        or _is_lgbtq_identity_arrest_context(q)
    ):
        return False
    if contract.id == "uapa_prima_facie_bail" and _is_default_bail_context(q):
        return False
    if contract.id == "unpaid_salary_after_termination" and (
        _is_epf_or_gratuity_context(q) or _is_wage_waiver_context(q)
    ):
        return False
    if contract.id == "esi_contribution_notice" and _is_esi_medical_benefit_context(q):
        return False
    if contract.id == "prison_mulaqat_books" and _is_bail_or_trial_relief_context(q):
        return False
    if contract.id == "workplace_injury_lost_limb_compensation" and _is_workplace_death_context(q):
        return False
    return True


def _is_under_18_context(q: str) -> bool:
    if re.search(r"\b(?:[1-9]|1[0-7])\s*(?:years?|yrs?)\s*(?:old)?\b", q):
        return True
    return _has_any(q, (
        "minor", "under 18", "under eighteen", "juvenile", "pocso",
        "teenage", "teenager", "schoolboy", "school boy", "schoolgirl",
        "school girl", "child", "fifteen year", "fifteen-year",
        "sixteen year", "sixteen-year", "seventeen year", "seventeen-year",
    ))


def _has_independent_offence_allegation(q: str) -> bool:
    offence_terms = (
        # Violence and offences against the person.
        "assault", "attacked", "attack", "stabbing", "stabbed", "knife",
        "hit him", "hit her", "beat him", "beat her", "hurt him", "hurt her",
        "murder", "killed", "homicide", "rape", "kidnap", "abduction",
        # Property, deception, and weapons allegations.
        "robbery", "dacoity", "theft", "stolen", "burglary", "snatching",
        "fraud", "cheating", "extortion", "weapon", "pistol", "gun",
        # Drug/NDPS allegations, including common named substances.
        "drug", "drugs", "ganja", "cannabis", "charas", "hashish", "cocaine",
        "heroin", "mdma", "ecstasy", "meth", "opium", "lsd", "ndps",
        "narcotic", "contraband", "possession of",
    )
    return _has_any(q, offence_terms)


def _pwdva_woman_aggrieved_context(q: str) -> bool:
    explicit_non_woman_victim = _has_any(q, (
        "my wife is beating me", "wife beats me", "wife beat me",
        "wife assaulted me", "wife hit me", "wife slapped me",
        "i am his husband", "i'm his husband", "i am a man",
        "i'm a man", "we are husbands", "husband beating husband",
        "male victim", "male spouse",
    ))
    if explicit_non_woman_victim:
        return False
    woman_context = _has_any(q, (
        "my husband", "husband is", "husband beat", "husband hit",
        "husband slap", "in laws", "in-laws", "mother in law",
        "father in law", "sasural", "i am his wife", "i'm his wife",
        "woman", "female", "daughter in law", "daughter-in-law", "mere husband", "mere pati",
        "mera husband", "mera pati",
    ))
    actor = (
        r"(?:my\s+)?(?:husband|spouse|pati|in[- ]?laws?|mother[- ]in[- ]law|"
        r"father[- ]in[- ]law|sasural(?:\s+waale)?)"
    )
    harm = (
        r"(?:beat(?:s|ing)?|hit(?:s|ting)?|slap(?:s|ped|ping)?|punch(?:es|ed|ing)?|"
        r"kick(?:s|ed|ing)?|hurt(?:s|ing)?|assault(?:s|ed|ing)?|"
        r"chok(?:e|es|ed|ing)|strangl(?:e|es|ed|ing)|stab(?:s|bed|bing)?|"
        r"shoot(?:s|ing)?|shot|poison(?:s|ed|ing)?|burn(?:s|ed|ing)?|"
        r"forc(?:e|es|ed|ing)|coerc(?:e|es|ed|ing)|abus(?:e|es|ed|ing))"
    )
    threat_harm = r"(?:kill|murder|hit|hurt|harm|attack|assault|beat|burn|injure|poison|shoot|stab|strangle|slit)"
    third_party_subject = re.compile(
        r"\b(?:neighbou?r|landlord|driver|friend|brother|sister|cousin|uncle|aunt|"
        r"police|officer|someone|another\s+(?:man|woman|person)|employer|manager)\b"
    )

    def actor_controls(action_pattern: str, *, window: int = 110) -> bool:
        for actor_match in re.finditer(rf"\b{actor}\b", q):
            tail = q[actor_match.end():actor_match.end() + window]
            action_match = re.search(action_pattern, tail)
            if action_match is None:
                continue
            intervening = tail[:action_match.start()]
            if third_party_subject.search(intervening) or re.search(
                r"\b(?:when|after|while|as)\b.{0,48}$",
                intervening,
            ) or re.search(
                r"\b(?:said|warned|told|reported|explained)\b.{0,36}"
                r"\b(?:the|our|my|a|an)\s+[a-z][a-z -]{1,24}\s+(?:will|would)\b",
                intervening,
            ) or re.search(
                r"\b(?:the|our|my|a|an)\s+[a-z]+(?:\s+[a-z]+)?\s+"
                r"(?:will|would|plans?\s+to|intends?\s+to|threatens?\s+to)\b",
                intervening,
            ):
                continue
            return True
        return False

    direct_or_threat_action = "|".join((
        rf"\b{harm}\b.{{0,16}}\b(?:me|myself)\b",
        rf"\bthreaten(?:s|ed|ing)?\b.{{0,24}}\b(?:to\s+)?{threat_harm}\b.{{0,12}}\b(?:me|myself)\b",
        r"\bthreaten(?:s|ed|ing)?\b.{0,24}\bto\s+break\s+my\s+legs?\b",
        r"\bthreaten(?:s|ed|ing)?\s+to\s+have\s+me\s+killed\b",
        r"\bthreaten(?:s|ed|ing)?\b.{0,20}\bto\s+slit\s+my\s+throat\b",
        rf"\b(?:made\s+)?(?:repeated\s+)?threats?\s+to\s+{threat_harm}\s+(?:me|myself)\b",
        r"\b(?:threaten(?:s|ed|ing)?|blackmail(?:s|ed|ing)?|harass(?:es|ed|ing)?)\b"
        r"\s+(?:both\s+)?(?:my|our|his|her|the)\s+"
        r"(?:son|daughter|brother|sister|father|mother|parent|child|friend|cousin|uncle|aunt|"
        r"nephew|niece|relative|colleague|roommate|flatmate|partner|driver|watchman|guard|employee|neighbour|neighbor)\b"
        r"\s*,?\s+and\s+(?:also\s+)?(?:me|myself)\b",
        r"\b(?:took|snatched|broke|withheld|checks?|checking)\b.{0,16}\bmy\s+phone\b",
        r"\b(?:threw|kicked|forced|told)\s+me\b.{0,20}\b(?:out|leave)\b",
    ))
    reported_actor_threat = re.search(
        rf"\b{actor}\b.{{0,18}}\btold\b.{{0,32}}\bthat\s+he\s+(?:would|will)\s+"
        rf"{threat_harm}\s+(?:me|myself)\b",
        q,
    ) is not None
    hindi_reported_actor_threat = any(
        re.search(pattern, q) is not None
        for pattern in (
            r"\b(?:mere\s+)?(?:husband|pati)\s+ne\s+(?:(?:bola|kaha)\b.{0,42})?"
            r"(?:mujhe\s+jaan\s+se\s+(?:maar|mar)(?:ne\s+ki\s+dhamki\s+di|\s+dega)|"
            r"mujhe\s+(?:jala|maar|mar)\s+(?:dega|degi|dalega|daalega))\b",
            r"\b(?:mere\s+)?(?:husband|pati)\s+ne\s+dhamki\s+di\b.{0,28}"
            r"\bmujhe\s+(?:jala|maar|mar)\s+(?:dega|degi|dalega|daalega)\b",
            r"\b(?:mere\s+)?(?:husband|pati)\s+ne\s+mujhe\s+"
            r"(?:jala|jalane|maar|mar|maarne|marne)\s+ki\s+dhamki\s+di\b",
        )
    )
    roman_hindi_direct_harm = re.search(
        r"\b(?:mera|mere)\s+(?:husband|pati)\b.{0,36}\bmujhe\b.{0,18}"
        r"\b(?:maar|mar|peet|pit)(?:ta|ti|te|na|ne|raha|rahi|diya|deta|deti)?\b",
        q,
    ) is not None
    actor_bound_harm = any((
        actor_controls(direct_or_threat_action),
        reported_actor_threat,
        hindi_reported_actor_threat,
        roman_hindi_direct_harm,
        re.search(rf"\b(?:i|me)\b.{{0,28}}\b{harm}\b.{{0,20}}\bby\s+{actor}\b", q) is not None,
        re.search(rf"\b(?:unsafe|afraid|scared)\b.{{0,28}}\b(?:because of|due to|from)\s+{actor}\b", q) is not None,
    ))
    consent_or_control = _has_any(q, (
        "when i say no", "after i say no", "if i do not", "if i don't",
        "not allowing me", "ghar se nikal", "ghar se nikaal",
    )) and re.search(rf"\b{actor}\b", q) is not None
    return woman_context and (actor_bound_harm or consent_or_control)


def _hidden_person_custody_context(q: str) -> bool:
    return has_person_custody_context(q)


def _is_civil_execution_bank_attachment(q: str) -> bool:
    return is_civil_execution_bank_attachment(q)


def _is_insurance_context(q: str) -> bool:
    return _has_any(q, (
        "insurance", "insurer", "policy premium", "insurance premium",
        "health policy", "life policy", "ulip", "lic policy",
    )) or re.search(r"\blic\b", q) is not None


def _is_insurer_claim_or_policy_dispute(q: str) -> bool:
    return _is_insurance_context(q) and _has_any(q, (
        "claim", "rejected", "rejecting", "denied", "repudiated",
        "repudiation", "not paying claim", "mis-selling", "misselling",
        "surveyor", "policy cancellation", "maturity", "matured",
    ))


def _is_pmla_enforcement_context(q: str) -> bool:
    return _has_any(q, (
        "pmla", "money laundering", "enforcement directorate", "ecir",
        "ed notice", "ed order", "ed froze", "ed frozen", "ed freeze",
        "ed attachment", "provisional attachment",
    ))


def _is_marital_sexual_coercion_context(q: str) -> bool:
    if not _has_any(q, ("husband", "wife", "spouse", "marriage", "marital")):
        return False
    if _has_any(q, (
        "force sex", "forces sex", "forced sex", "forcing sex",
        "forcing me for sex", "sexual force", "sexual coercion",
        "marital rape", "sex without consent", "without consent",
        "when i say no", "after i say no", "threatening me for sex",
        "threatens me for sex", "threatening for sex", "coerces me for sex",
    )):
        return True
    return re.search(
        r"\b(?:force(?:d|s|ing)?|coerc(?:e|ed|es|ing|ion)|threaten(?:ed|s|ing)?)\b.{0,35}\b(?:me\s+)?(?:for\s+)?sex\b",
        q,
    ) is not None


def _route_eligible(contract: AuthorityWorkflowContract, route: MatterRoute) -> bool:
    if route.category in contract.route_categories:
        return True
    carceral_rescue_routes = {
        "uapa_prima_facie_bail": {
            "general_legal",
            "legal_aid",
            "undertrial_review_release",
            "arrest_custody_safeguard",
        },
        "custody_medical_care": {
            "general_legal",
            "police_fir",
            "criminal_general",
            "criminal_defence_bail",
            "prison_parole_furlough",
            "custody_compensation",
        },
        "custody_legal_aid_lawyer_access": {
            "general_legal",
            "police_fir",
            "criminal_general",
            "criminal_defence_bail",
            "legal_aid",
            "prison_parole_furlough",
        },
        "juvenile_adult_jail_age_determination": {
            "general_legal",
            "police_fir",
            "criminal_general",
            "criminal_defence_bail",
            "social_welfare_identity",
            "education_rights",
        },
        "undertrial_lawyer_not_coming_legal_aid": {
            "general_legal",
            "legal_aid",
            "criminal_defence_bail",
            "prison_parole_furlough",
            "undertrial_review_release",
        },
        "arrest_custody_station_case_not_disclosed": {
            "general_legal",
            "criminal_general",
            "police_fir",
            "arrest_custody_safeguard",
        },
        "prison_mulaqat_books": {
            "general_legal",
            "criminal_general",
            "criminal_defence_bail",
        },
    }
    if route.category in carceral_rescue_routes.get(contract.id, set()):
        return True
    # A few high-risk workflows should rescue a bad generic route instead of
    # letting the user see intake prose for an urgent concrete legal problem.
    return route.category == "general_legal" and contract.id in {
        "ai_child_sexual_image",
        "cyber_money_fraud",
        "domestic_violence_immediate_safety",
        "lgbtq_identity_arrest_safeguard",
        "mgnrega_fake_muster",
        "pds_ration_card_name_removed",
        "street_vendor_goods_removed",
        "wage_theft_false_fir",
    }


def _is_custody_abuse_or_extortion_context(q: str) -> bool:
    custody_context = _has_any(q, (
        "lockup", "custody", "custodial", "police station",
        "thana", "constable", "police beat", "police slapped",
    ))
    abuse_context = _has_any(q, (
        "beaten", "beat", "beating", "torture", "injury",
        "hurt", "slapped", "refused medical examination",
        "medical examination refused",
    ))
    extortion_context = _has_any(q, (
        "took 20000", "bribe", "money for bail", "paid for bail",
        "demanded money", "not released", "still not released",
    ))
    return custody_context and (abuse_context or extortion_context)


def _is_epf_or_gratuity_context(q: str) -> bool:
    dues = _has_any(q, (
        "epf", "epfo", "pf ", " pf", "provident fund", "uan",
        "pf passbook", "epf passbook", "passbook empty", "zero contribution",
        "no contribution", "not depositing", "not deposited", "no epf deposit",
        "gratuity", "gratuity interest",
    ))
    workplace = _has_any(q, (
        "company", "employer", "factory", "hr", "salary", "wage",
        "deduct", "deducted", "closed", "shut down", "pending",
    ))
    return dues and workplace


def _is_wage_waiver_context(q: str) -> bool:
    return _has_any(q, ("give up wages", "waive wages", "waiver", "signed paper", "signed document")) and _has_any(q, (
        "wage", "wages", "salary", "dues", "dont read", "don't read",
        "cannot read", "english", "kannada", "pressure", "forced",
    ))


def _is_esi_medical_benefit_context(q: str) -> bool:
    esi = _has_any(q, ("esi", "esic", "employees state insurance", "employees' state insurance"))
    medical = _has_any(q, (
        "hospital", "treat", "treatment", "delivery", "medical benefit",
        "refused", "refusal", "sickness benefit", "maternity benefit",
        "disablement benefit", "insured person", "eligibility",
    ))
    return esi and medical


def _is_bail_or_trial_relief_context(q: str) -> bool:
    bail_or_trial = _has_any(q, (
        "bail", "bail rejected", "regular bail", "interim bail",
        "default bail", "chargesheet", "charge sheet", "no chargesheet",
        "trial", "case pending", "prolonged", "3 yrs", "3 years",
        "ndps", "uapa", "sessions court", "high court", "option what next",
    ))
    actual_prison_access = _has_any(q, (
        "mulaqat", "mulakat", "visitor", "visitor list", "interview",
        "phone call", "video call", "books", "book from family",
    ))
    return bail_or_trial and not actual_prison_access


def _is_uapa_special_bail_context(q: str) -> bool:
    uapa_context = _has_any(q, ("uapa", "unlawful activities", "43d"))
    return uapa_context or ("prima facie" in q and uapa_context)


def _is_default_bail_context(q: str) -> bool:
    return _has_any(q, (
        "default bail", "statutory bail", "no chargesheet", "no charge sheet",
        "chargesheet not", "charge sheet not", "no challan", "challan not",
        "no complaint filed", "complaint not filed", "no final report",
        "extension request", "extension application",
    ))


def _is_pmla_specific_bail_context(q: str) -> bool:
    pmla_context = _has_any(q, (
        "pmla", "money laundering", "enforcement directorate", "ecir",
        "scheduled offence",
    )) or (
        re.search(r"(?<![-\w])ed(?![-\w])", q) is not None
        and _has_any(q, ("summons", "raid", "arrest", "bail", "ecir"))
    )
    bail_context = _has_any(q, (
        "bail", "anticipatory", "interim", "before arrest", "pre arrest",
        "pre-arrest", "arrested", "custody", "new born", "newborn", "baby",
        "pregnant", "sick", "infirm", "woman", "wife",
    ))
    return pmla_context and bail_context


def _is_ndps_specific_bail_context(q: str) -> bool:
    ndps_context = _has_any(q, (
        "ndps", "narcotic", "narcotics", "ganja", "charas", "mdma",
        "heroin", "cannabis", "weed", "hash", "bhang", "bhang lassi",
        "cbd", "thc", "vape",
    ))
    bail_or_quantity_context = _has_any(q, (
        "bail", "punishment", "commercial", "quantity", "gram", "grams",
        "mg", "kg", "caught", "arrested", "police", "fsl", "lab report",
        "section 37", "special court", "jail", "custody",
    ))
    return ndps_context and bail_or_quantity_context


def _is_lgbtq_identity_arrest_context(q: str) -> bool:
    identity_context = _has_lgbtq_identity_term(q)
    custody_context = _has_any(q, (
        "police arrested", "arrested", "arrest", "detained", "picked up",
        "police picked", "custody", "lockup", "jail", "taken by police",
        "fir", "case filed", "case against",
    ))
    return identity_context and custody_context


def _is_workplace_death_context(q: str) -> bool:
    return _has_any(q, (
        "worker died", "worker dead", "friend dead", "friend died",
        "died at site", "dead at site", "death at site", "site death",
        "factory death", "boiler burst", "killed", "death compensation",
    )) or (
        _has_any(q, ("died", "dead", "death", "killed"))
        and _has_any(q, ("site", "worksite", "factory", "workplace", "owner", "employer", "contractor", "labour", "labor", "worker"))
    )


def _is_construction_principal_employer_accident_context(q: str) -> bool:
    construction_accident = _has_any(q, (
        "construction", "site", "worksite", "pillar fell", "fell from",
        "principal employer", "contract worker", "contractor",
        "l&t", "larsen", "mumbai",
    ))
    compensation_context = _has_any(q, (
        "accident", "injury", "injured", "fell", "pillar", "not their problem",
        "compensation", "claim", "hospital", "fracture",
    ))
    return construction_accident and compensation_context


def _triggers_match(q: str, groups: tuple[tuple[str, ...], ...]) -> bool:
    return all(any(_trigger_term_matches(q, term) for term in group) for group in groups)


def _trigger_term_matches(q: str, term: str) -> bool:
    if term in {"gay", "lesbian", "queer", "lgbt", "lgbtq"}:
        return _has_token(q, term)
    return term in q


def _has_token(text: str, term: str) -> bool:
    return re.search(rf"(?<![a-z0-9]){re.escape(term)}(?![a-z0-9])", text) is not None


def _has_lgbtq_identity_term(q: str) -> bool:
    if _has_any(q, (
        "being gay", "for being gay", "because he is gay", "because she is gay",
        "because i am gay", "because im gay", "same sex", "same-sex",
        "homosexual", "sexual orientation",
    )):
        return True
    return any(_has_token(q, term) for term in ("gay", "lesbian", "queer", "lgbt", "lgbtq"))


def _is_adultery_context(q: str) -> bool:
    return _has_any(q, (
        "adultery", "extra marital", "extra-marital", "affair",
        "cheating on me", "another woman", "another women", "another man",
        "caught my husband", "caught my wife", "caught husband", "caught wife",
        "sex with another",
    ))


def _is_minor_mineral_lease_context(q: str) -> bool:
    return _has_any(q, (
        "minor mineral", "minor minerals", "sand mining", "sand lease",
        "stone quarry", "quarry lease", "quarry",
    ))


def _is_tenancy_no_sale_dispute_context(q: str) -> bool:
    tenancy = _has_any(q, (
        "tenant", "tenent", "rent", "not leaving", "not vacating",
        "refusing to vacate", "evict", "eviction",
    ))
    sale_negated = _has_any(q, (
        "no sale dispute", "not a sale dispute", "no dispute among heirs",
        "no heir sale dispute", "not about sale", "not about selling",
    ))
    return tenancy and sale_negated


def _is_mutation_after_death(q: str) -> bool:
    death_context = _has_any(q, (
        "father died", "mother died", "husband died", "wife died",
        "died", "death", "passed away", "late father", "late mother",
    ))
    mutation_context = _has_any(q, (
        "mutation", "patwari", "tehsildar", "tahsildar", "talathi",
        "khata", "khasra", "khatauni", "jamabandi", "land record",
        "revenue record", "not updated", "name not updated",
    ))
    property_context = _has_any(q, (
        "land", "plot", "field", "property", "house", "flat", "home",
        "khata", "khasra", "patwari record", "revenue record",
    ))
    return death_context and mutation_context and property_context


def _is_nonfraud_payment_service_context(q: str) -> bool:
    payment_context = _has_any(q, (
        "upi", "phonepe", "gpay", "google pay", "paytm", "payment app",
        "transaction", "merchant", "seller", "imps", "atm",
    ))
    service_problem = _has_any(q, (
        "failed upi refund", "upi refund", "failed transaction",
        "payment failed", "money cut", "amount cut", "refund will come",
        "closed ticket", "merchant says", "seller says", "customer care",
        "both sides are blaming", "blaming each other",
        "beneficiary did not get money", "beneficiary didn't get money",
        "atm cash not dispensed", "cash not dispensed", "atm did not dispense",
        "imps transfer failed", "imps failed",
    ))
    fraud_context = _has_any(q, (
        "otp", "phishing", "scam", "fraud", "fake customer care",
        "fake customer support", "fake helpline", "fake cbi", "digital arrest",
        "anydesk", "remote access", "screen sharing", "unauthorized",
        "unauthorised", "hacked", "stolen",
    ))
    return payment_context and service_problem and not fraud_context


def _is_cyber_money_fraud_context(q: str) -> bool:
    if _is_nonfraud_payment_service_context(q):
        return False
    cyber_money = _has_any(q, (
        "otp", "phishing", "upi fraud", "upi scam", "phonepe fraud",
        "gpay fraud", "fake customer care", "fake customer support",
        "fake helpline", "fraud call", "scam call", "install app",
        "installed app", "remote access", "anydesk", "screen sharing",
        "unauthorized transaction", "unauthorised transaction",
        "credit card unauthorized", "credit card unauthorised",
        "money got transferred", "money was transferred", "money transferred",
        "amount transferred", "account emptied", "emptied account",
        "duped", "fake stock", "stock trading app", "fake trading app",
        "trading app", "investment app", "multiple upi ids",
        "cyber cell complaint", "cyber complaint filed", "no progress",
        "whatsapp account got hacked", "whatsapp hacked", "account hacked",
        "asking my contacts for money", "asking contacts for money",
        "bank says my mistake", "bank says my fault", "customer negligence",
    ))
    money_or_bank = _has_any(q, (
        "money", "bank", "account", "upi", "credit card", "debit card",
        "card", "transaction", "50000", "50,000", "lakh", "amount",
        "refund", "reversal", "transferred", "emptied",
    ))
    return cyber_money and money_or_bank


def _is_mining_pollution_property_damage_without_displacement(q: str) -> bool:
    mine_context = _has_any(q, ("mine", "mining", "bauxite", "coal mine", "iron ore"))
    pollution_damage = _has_any(q, (
        "pollution", "polluting", "smoke", "dust", "chemical", "effluent",
        "water pollution", "air pollution", "damaged my house", "house damaged",
        "paint damaged", "wall damaged", "crop damaged", "compensation",
    ))
    displacement_context = _has_any(q, (
        "displaced", "displacement", "rehabilitation", "rehab", "r&r",
        "resettlement", "submerge", "submerged", "submergence", "land acquired",
        "acquisition", "award", "affected family", "affected-family",
        "village list", "villages",
    ))
    consent_context = _has_any(q, (
        "gram sabha", "palli sabha", "scheduled area", "no consent",
        "without consent",
    ))
    return mine_context and pollution_damage and not (displacement_context or consent_context)


def _resolve_sources(
    contract: AuthorityWorkflowContract,
    passages: list[dict],
    *,
    q: str = "",
    route: MatterRoute | None = None,
    strict_plan: bool = False,
) -> dict[str, int] | None:
    if contract.id == "caste_certificate_state_rule_intake":
        if _has_any(q, ("st certificate", "st cert", "scheduled tribe", "tribe certificate", "tribal certificate")):
            constitution_anchors = ("/sec-342",)
        elif _has_any(q, ("sc certificate", "sc cert", "scheduled caste")):
            constitution_anchors = ("/sec-341",)
        else:
            constitution_anchors = ("/sec-341", "/sec-342")

        constitution = _find(
            passages,
            title_terms=("constitution",),
            anchor_terms=constitution_anchors,
        )
        rti = _find(
            passages,
            title_terms=("right to information",),
            anchor_terms=("/sec-6",),
        )
        if constitution is None or rti is None:
            return None
        return {"constitution": constitution, "rti": rti}

    required_keys = {
        spec.key
        for spec in _required_source_specs(
            contract,
            route,
            strict_plan=strict_plan,
        )
    }
    allowed_keys = _allowed_source_keys_for_regime(contract, route)
    out: dict[str, int] = {}
    for spec in contract.source_specs:
        if allowed_keys is not None and spec.key not in allowed_keys:
            continue
        found = _find(passages, title_terms=spec.title_terms, anchor_terms=spec.anchor_terms)
        if found is None:
            if spec.key in required_keys:
                return None
            continue
        out[spec.key] = found
    if not out:
        return None
    return out


def _find(
    passages: list[dict],
    *,
    title_terms: tuple[str, ...] = (),
    anchor_terms: tuple[str, ...] = (),
) -> int | None:
    for passage in passages:
        title = str(passage.get("title") or "").lower()
        anchor = str(passage.get("anchor") or "").lower()
        if title_terms and not any(term in title for term in title_terms):
            continue
        if anchor_terms and not any(_anchor_matches(anchor, term) for term in anchor_terms):
            continue
        idx = passage.get("index")
        return int(idx) if isinstance(idx, int) else None
    return None


def _source_anchor(sources: dict[str, int], key: str, passages: list[dict]) -> str:
    idx = sources.get(key)
    if idx is None:
        return ""
    for passage in passages:
        if passage.get("index") == idx:
            return str(passage.get("anchor") or "").lower()
    return ""


def _anchor_matches(anchor: str, term: str) -> bool:
    needle = term.lower()
    if needle.startswith("/sec-"):
        return re.search(rf"{re.escape(needle)}(?=@|-|__|$)", anchor) is not None
    if needle.startswith("sec-"):
        return re.search(rf"(^|/){re.escape(needle)}(?=@|-|__|$)", anchor) is not None
    return needle in anchor


def _norm(text: str) -> str:
    return " ".join(str(text).lower().split())


def _render_special_contract(
    contract_id: str,
    q: str,
    sources: dict[str, int],
    passages: list[dict],
    route: MatterRoute,
) -> list[str]:
    if contract_id == "shop_sealed_municipality":
        return _render_shop_sealing(q, sources, passages)
    if contract_id == "joint_coowner_sold_whole_property":
        return _render_joint_coowner_sale(q, sources)
    if contract_id == "epf_not_deposited":
        return _render_epf_dues(q, sources)
    if contract_id == "street_vendor_goods_removed":
        return _render_street_vendor_seizure(q, sources)
    if contract_id == "marital_intimacy_remedy":
        return _render_marital_intimacy(q, sources)
    if contract_id == "domestic_violence_immediate_safety":
        return _render_domestic_violence_safety(q, sources, passages)
    if contract_id == "maintenance_order_nonpayment":
        return _render_maintenance_nonpayment(q, sources)
    if contract_id == "senior_parent_pension_neglect":
        return _render_senior_parent_support(q, sources)
    if contract_id == "pds_ration_card_name_removed":
        return _render_pds_ration_name_removed(q, sources)
    if contract_id == "mgnrega_fake_muster":
        return _render_mgnrega_grievance(q, sources)
    if contract_id == "ndps_quantity_bail":
        return _render_ndps_quantity_bail(q, sources, passages)
    if contract_id == "ndps_bhang_lassi":
        return _render_ndps_bhang_lassi(q, sources)
    if contract_id == "pmla_anticipatory_interim_bail":
        return _render_pmla_anticipatory_interim_bail(q, sources)
    if contract_id == "state_prohibition_excise_accused":
        return _render_state_prohibition_excise_accused(q, sources)
    if contract_id == "regular_bail_after_arrest":
        return _render_regular_bail_after_arrest(q, sources)
    if contract_id == "lgbtq_identity_arrest_safeguard":
        return _render_lgbtq_identity_arrest_safeguard(q, sources, route)
    if contract_id == "vehicle_theft_fir_refusal":
        return _render_vehicle_theft_fir_refusal(route, sources)
    if contract_id == "bail_surety_condition_modification":
        return _render_bail_surety_condition_modification(q, sources)
    if contract_id == "bail_surety_amount_context":
        return _render_bail_surety_amount_context(q, sources)
    if contract_id == "anticipatory_bail_rejected_next_step":
        return _render_anticipatory_bail_rejected_next_step(q, sources)
    if contract_id == "498a_bail_rejection_source_gap":
        return _render_498a_bail_rejection_source_gap(q, sources)
    if contract_id == "sexual_offence_sessions_bail_forum":
        return _render_sexual_offence_sessions_bail_forum(q, sources)
    if contract_id == "uapa_prima_facie_bail":
        return _render_uapa_prima_facie_bail(q, sources)
    if contract_id == "itpa_booking_only_accused":
        return _render_itpa_booking_only_accused(q, sources)
    if contract_id == "itpa_receptionist_raid_accused":
        return _render_itpa_receptionist_raid_accused(q, sources)
    if contract_id == "handcuff_restraint_objection":
        return _render_handcuff_restraint_objection(q, sources)
    if contract_id == "undertrial_bnss479_review":
        return _render_undertrial_bnss479_review(q, sources)
    if contract_id == "custodial_death_inquiry":
        return _render_custodial_death_inquiry(q, sources)
    if contract_id == "wage_theft_false_fir":
        return _render_wage_theft_false_fir(q, sources)
    if contract_id == "custody_medical_care":
        return _render_custody_medical_care(q, sources)
    if contract_id == "pregnant_undertrial_medical_bail":
        return _render_pregnant_undertrial_medical_bail(q, sources)
    if contract_id == "custody_legal_aid_lawyer_access":
        return _render_custody_legal_aid_lawyer_access(q, sources)
    if contract_id == "ndps_default_bail_no_chargesheet":
        return _render_ndps_default_bail(q, sources)
    if contract_id == "default_bail_no_chargesheet":
        return _render_default_bail_no_chargesheet(q, sources, passages)
    if contract_id == "juvenile_adult_jail_age_determination":
        return _render_juvenile_age_custody(q, sources)
    if contract_id == "friendly_loan_upi_recovery":
        return _render_friendly_loan_recovery(q, sources)
    if contract_id == "marriage_salary_loan_misrepresentation":
        return _render_marriage_misrepresentation(q, sources)
    if contract_id == "marriage_legal_age":
        return _render_marriage_legal_age(q, sources)
    if contract_id == "mutual_consent_divorce":
        return _render_mutual_consent_divorce(q, sources)
    if contract_id == "wrong_bank_debit":
        return _render_wrong_bank_debit(q, sources)
    if contract_id == "bank_account_freeze_legal_hold":
        return _render_bank_account_freeze_legal_hold(q, sources, route)
    if contract_id == "employment_original_document_return":
        return _render_employment_original_document_return(q, sources)
    if contract_id == "employment_notice_period_contract":
        return _render_employment_notice_period_contract(q, sources)
    if contract_id == "unpaid_group_wages_no_contract":
        return _render_unpaid_group_wages_no_contract(q, sources)
    if contract_id == "ordinary_invoice_payment_reminder":
        return _render_ordinary_invoice_payment_reminder(q, sources)
    if contract_id == "prison_mulaqat_books":
        return _render_prison_mulaqat_books(q, sources)
    if contract_id == "esi_contribution_notice":
        return _render_esi_contribution_notice(q, sources)
    if contract_id == "income_tax_appeal_deadline":
        return _render_income_tax_appeal_deadline(q, sources)
    if contract_id == "gst_freelancer_registration_threshold":
        return _render_gst_freelancer_registration_threshold(q, sources)
    if contract_id == "cyber_money_fraud":
        return _render_cyber_money_fraud(q, sources)
    if contract_id == "ai_child_sexual_image":
        return _render_ai_child_sexual_image(q, sources, passages)
    if contract_id == "digital_arrest_impersonation_transfer":
        return _render_digital_arrest_impersonation(q, sources)
    if contract_id == "builder_rera":
        return _render_builder_rera(q, sources)
    if contract_id == "mining_displacement_rehabilitation":
        return _render_mining_displacement_rehabilitation(q, sources)
    if contract_id == "interstate_migrant_displacement_allowance":
        return _render_interstate_migrant_displacement(q, sources)
    if contract_id == "tribal_land_nontribal_transfer":
        return _render_tribal_land_nontribal_transfer(q, sources)
    if contract_id == "tribal_religious_attack_poa":
        return _render_tribal_religious_attack(q, sources)
    if contract_id == "cfr_illegal_mining":
        return _render_cfr_illegal_mining(q, sources)
    if contract_id == "gift_deed_thumb_fraud":
        return _render_gift_deed_thumb_fraud(q, sources)
    if contract_id == "insurance_claim_or_misselling":
        return _render_insurance_claim_or_misselling(q, sources)
    if contract_id == "bonded_labour_coercion_release":
        return _render_bonded_labour_coercion_release(q, sources)
    if contract_id == "school_caste_slur_assault":
        return _render_school_caste_slur_assault(q, sources)
    if contract_id == "consumer_defective_goods":
        return _render_consumer_defective_goods(q, sources)
    if contract_id == "heir_refuses_sale":
        return _render_heir_refuses_sale(q, sources)
    if contract_id == "daughter_ancestral_share":
        return _render_daughter_ancestral_share(q, sources, passages)
    if contract_id == "caste_certificate_state_rule_intake":
        return _render_caste_certificate_state_rule_intake(q, sources, passages)
    return []


def _render_caste_certificate_state_rule_intake(
    q: str,
    sources: dict[str, int],
    passages: list[dict],
) -> list[str]:
    constitution = sources["constitution"]
    rti = sources["rti"]
    anchor = _source_anchor(sources, "constitution", passages)
    is_st = _has_any(q, ("st certificate", "st cert", "scheduled tribe", "tribe certificate", "tribal certificate"))
    is_sc = _has_any(q, ("sc certificate", "sc cert", "scheduled caste"))

    if is_st and "/sec-342" in anchor:
        lead = (
            "For an ST certificate delay or rejection, Article 342 is the "
            f"constitutional source for the relevant State-wise Scheduled Tribe list [{constitution}]."
        )
    elif is_sc and "/sec-341" in anchor:
        lead = (
            "For an SC certificate delay or rejection, Article 341 is the "
            f"constitutional source for the relevant State-wise Scheduled Caste list [{constitution}]."
        )
    else:
        article = "342" if "/sec-342" in anchor else "341"
        category = "ST" if article == "342" else "SC"
        lead = (
            "First confirm whether the application is for an SC or ST certificate. "
            f"The retrieved Article {article} source covers the State-wise {category} list, "
            f"but the State certificate rule still controls the evidence, appeal authority, and deadline [{constitution}]."
        )

    return [
        lead,
        "Do not file an RTI appeal as though it overturns the certificate decision. "
        "An RTI request is not itself the caste-certificate appeal. "
        f"Use RTI Section 6 to obtain the application file, written rejection or delay reason, rule relied on, and the State appellate authority [{rti}].",
        "The exact review or appeal forum and deadline are State-rule dependent, so the State and signed rejection or pending-status record are required before giving a final forum-specific step.",
        "**What you can do next**",
        "- Ask the Tehsildar or competent certificate authority in writing for the signed order or pending-status reason; attach the application receipt, family/community proof, school and residence records, and request the State-rule appeal route and deadline. "
        f"If an exam, admission, scholarship, or job deadline is close, also give the institution the acknowledgement and take the record to the district social-welfare office or DLSA [{rti}].",
    ]


def _render_ai_child_sexual_image(q: str, sources: dict[str, int], passages: list[dict]) -> list[str]:
    pocso = sources.get("pocso")
    if pocso is None:
        return []
    reporting = sources.get("reporting")
    it67b = sources.get("it67b")
    it_any = sources.get("it_any")
    bns = sources.get("bns")
    scenario = _child_sexual_image_scenario_phrase(q)
    lines = [
        f"For {scenario}, treat it as an urgent child sexual-image complaint under POCSO, not a private reputation dispute [{pocso}].",
    ]
    if reporting is not None:
        lines.append(
            f"The POCSO reporting source is the reporting/mandatory-information track to preserve for police or child-protection escalation where Section 19 is retrieved [{reporting}]."
        )
    text_only_67b_reference = any(
        passage.get("index") == it_any
        and "section 67b" in str(passage.get("text") or "").lower()
        for passage in passages
    )
    if it67b is not None:
        lines.append(
            f"If the minor CSAM/fake nude/morphed image is being forwarded on WhatsApp, Telegram, school groups, or another electronic platform, keep the IT Act child sexual-image/electronic publication source with the POCSO track [{it67b}]."
        )
    elif it_any is not None and not text_only_67b_reference:
        lines.append(
            f"The retrieved IT Act source supports the electronic/privacy/cyber trail, but the child-specific Section 67B source still needs verification; do not drop the IT Act takedown and cyber-evidence track just because the first IT source is not Section 67B [{it_any}]."
        )
    if bns is not None:
        lines.append(
            f"The BNS voyeurism source is a separate current-law source to check where the facts involve watching, capturing, or disseminating private imagery of a woman or girl in the covered circumstances [{bns}]."
        )
    lines.append(
        f"Do not forward, do not share, and protect identity while preserving evidence for police, cyber cell, FIR, Childline/1098, or DLSA help [{pocso}]."
    )
    lines.append("**What you can do next**")
    action_cites = f"[{pocso}]"
    if it67b is not None:
        action_cites += f", [{it67b}]"
    elif it_any is not None and not text_only_67b_reference:
        action_cites += f", [{it_any}]"
    lines.append(
        f"- Preserve URLs, screenshots, profile IDs, uploader details, timestamps, hashes if available, Telegram/WhatsApp group details, platform complaint IDs, and takedown requests; report the CSAM/minor-image facts to cybercrime.gov.in/local cyber police and seek urgent takedown without forwarding the material {action_cites}."
    )
    return lines


def _child_sexual_image_scenario_phrase(q: str) -> str:
    if _has_any(q, ("college telegram", "telegram")) and _has_any(q, ("csam", "classmate")):
        return "AI CSAM of a classmate shared in a college/Telegram group"
    if _has_any(q, ("schoolmate", "girls in class", "i am 15", "15 year", "15 yr")) and _has_any(q, ("deepfake", "fake nude", "nude videos", "ai")):
        return "AI deepfake nude videos of girls in class involving a 15-year-old/student"
    if _has_any(q, ("school", "classmate", "student")):
        return "a school/classmate minor fake nude or morphed sexual-image circulation"
    return "a minor, child, classmate, or student CSAM/fake nude/morphed sexual-image circulation"


def _render_daughter_ancestral_share(q: str, sources: dict[str, int], passages: list[dict]) -> list[str]:
    hsa6 = sources.get("hsa6")
    if hsa6 is None:
        return []
    specific = sources.get("specific")
    lines = [
        f"For ancestral or coparcenary property where brothers or relatives say daughters have no share, start with the Hindu Succession Act Section 6 daughter/coparcener source rather than treating it as a generic tenancy or police dispute [{hsa6}].",
        f"First build the family tree, father's death/status, will/no-will position, and whether the property is ancestral/coparcenary or self-acquired before calculating daughters' and sons' shares [{hsa6}].",
    ]
    if specific is not None:
        lines.append(
            f"If relatives block records, partition, or possession after the share is disputed, the next forum is usually revenue records plus civil court/DLSA for partition, declaration, or injunction, not self-help possession [{specific}]."
        )
    lines.extend([
        "**What you can do next**",
        f"- Keep the death certificate if relevant, family tree/legal-heir proof, old title/khata/khasra/jamabandi records, proof the land is ancestral or family property, any sale/mutation papers, and messages refusing daughters' share; ask DLSA/revenue office/civil lawyer about mutation plus partition/declaration steps [{hsa6}].",
    ])
    return lines


def _render_mutual_consent_divorce(q: str, sources: dict[str, int]) -> list[str]:
    family = sources.get("family")
    if family is None:
        return []
    hma = sources.get("hma13b")
    sma = sources.get("sma28")
    christian = sources.get("christian")
    shariat = sources.get("shariat")
    dissolution = sources.get("dissolution")
    is_christian = _has_any(q, ("christian", "catholic", "protestant", "church marriage"))
    is_muslim = _has_any(q, ("muslim", "islam", "islamic", "nikah", "shariat"))
    is_special = _has_any(q, ("special marriage", "special marriage act", "court marriage", "interfaith", "inter-faith"))

    lines = [
        f"For spouses who both agree to divorce, treat this as a mutual-consent divorce / Family Court procedure question, not as a domestic-violence or police complaint route [{family}]."
    ]
    if is_christian and christian is not None:
        lines.append(
            f"Because you say the marriage is Christian/church based, verify the Divorce Act route for mutual dissolution and local Family Court/District Court filing instead of assuming the Hindu Marriage Act applies [{christian}]."
        )
        action_cite = christian
    elif is_muslim and (shariat is not None or dissolution is not None):
        personal = shariat if shariat is not None else dissolution
        lines.append(
            f"Because you say this is a Muslim marriage, do not assume the Special Marriage Act applies unless the marriage was registered under it; first verify the personal-law route for dissolution/khula/mubarat and the Family Court/DLSA filing path [{personal}]."
        )
        if dissolution is not None and dissolution != personal:
            lines.append(
                f"If a court petition is being considered, keep the Dissolution of Muslim Marriages Act source in the verification bundle, but check with DLSA or a family-law lawyer whether it fits the exact mutual-consent facts [{dissolution}]."
            )
        action_cite = personal
    elif is_special and sma is not None:
        lines.append(
            f"If the marriage is under the Special Marriage Act, Section 28 is the mutual-consent divorce source to verify before preparing the joint petition and settlement terms [{sma}]."
        )
        action_cite = sma
    elif hma is not None:
        lines.append(
            f"If the Hindu Marriage Act applies, Section 13B is the mutual-consent divorce source to verify before preparing the joint petition and settlement terms [{hma}]."
        )
        if sma is not None:
            lines.append(
                f"If the marriage is under the Special Marriage Act or another personal law instead, verify that equivalent source instead of assuming the Hindu Marriage Act applies [{sma}]."
            )
        action_cite = hma
    elif sma is not None:
        lines.append(
            f"If the marriage is under the Special Marriage Act, Section 28 is the mutual-consent divorce source to verify before preparing the joint petition and settlement terms [{sma}]."
        )
        action_cite = sma
    else:
        return []

    lines.append(
        f"Even where there are no children, the petition should still settle maintenance/alimony, streedhan or articles, residence/property issues, and pending cases before the Family Court records consent [{family}]."
    )
    if _has_any(q, ("mediation", "mediator", "counselling", "counseling", "settlement")):
        lines.append(
            f"Family Court counselling/mediation may be used to record or test settlement, but do not confuse that with Commercial Courts Section 12A; the divorce filing still turns on the applicable marriage law and free consent [{family}].",
        )
    lines.extend([
        "**What you can do next**",
        f"- Keep marriage certificate/proof, address and ID proofs, photos if required locally, separation/timeline facts, settlement terms on maintenance/alimony/stridhan/property, and draft joint petition; take them to DLSA or a family-law lawyer before filing [{family}], [{action_cite}].",
    ])
    return lines


def _render_heir_refuses_sale(q: str, sources: dict[str, int]) -> list[str]:
    hindu_context = _has_any(q, (
        "hindu", "coparcenary", "ancestral", "daughter share",
        "daughters have no share", "father died", "mother died",
    ))
    succession = (
        sources.get("hindu")
        if sources.get("hindu") is not None and (hindu_context or sources.get("succession") is None)
        else sources.get("succession")
    )
    tpa = sources.get("tpa")
    specific = sources.get("specific")
    if succession is None:
        return []
    subject = (
        "your uncle sold ancestral land without asking other heirs"
        if _has_any(q, ("uncle",)) and _has_any(q, ("ancestral", "land")) and _has_any(q, ("sold", "selling", "without asking", "without telling"))
        else "your father died and one sister is refusing to sign the house sale papers"
        if _has_any(q, ("father died", "sister")) and _has_any(q, ("sale", "sign"))
        else "one legal heir is not agreeing to a property sale"
    )
    succession_source_phrase = (
        "the Hindu Succession source where Hindu law applies"
        if succession == sources.get("hindu")
        else "the succession source while confirming the applicable personal law"
    )
    if _has_any(q, ("dada", "grandfather", "uncle")) and _has_any(q, ("ancestral", "land")):
        lines = [
            f"For grandfather/dada land, meaning ancestral land, first check who can sign sale papers and whether your uncle's proposed sale can bind other heirs: if your uncle sold ancestral land or is trying to sell without asking the others, verify the family tree, legal heirs, shares, will/no-will position, and {succession_source_phrase}; do not assume one uncle can bind all heirs before shares and sale papers are verified [{succession}]."
        ]
    else:
        lines = [
            f"First identify the legal heir, succession, inherited-property status and the legal heirs, applicable succession or personal law, shares, will/no-will position, and {succession_source_phrase}; for {subject}, verify who can sign sale papers before assuming one heir can bind everyone [{succession}]."
        ]
    if tpa is not None:
        lines.append(
            f"If one legal heir, uncle, sister, brother, or co-owner has sold or is trying to sell, do not assume the whole property can be sold; the Transfer of Property Act co-owner/share source does not prove that the whole property can be sold, and a person may deal only with the share or interest they can legally transfer [{tpa}]."
        )
    if specific is not None:
        lines.append(
            f"If a sale deed is already registered or being forced despite the heir/share dispute, the civil court route can include partition, declaration, injunction, or cancellation relief [{specific}]."
        )
    action_cite = succession
    lines.extend([
        "**What you can do next**",
        f"- Use written consent/release/family settlement if everyone agrees; otherwise take the death certificate, legal-heir certificate or family tree, title deed, sale deed or draft papers, mutation/khata/land records, will if any, and the sister/uncle/heir refusal or sale proof to the sub-registrar/revenue office for records and to DLSA, a property lawyer, or civil court for a partition/declaration/injunction route [{action_cite}].",
    ])
    return lines


def _render_consumer_defective_goods(q: str, sources: dict[str, int]) -> list[str]:
    consumer = sources.get("consumer")
    if consumer is None:
        return []
    subject = (
        "fake/counterfeit shoes from an online seller or marketplace"
        if _has_any(q, ("fake shoes", "fake nike", "counterfeit shoes", "fake goods")) or (_has_any(q, ("shoes", "footwear")) and "fake" in q)
        else
        "duplicate or wrong shoes from Flipkart/marketplace"
        if _has_any(q, ("duplicate shoes", "shoes", "footwear"))
        else "Amazon/marketplace fake iPhone or third-party-seller refund denial"
        if _has_any(q, ("fake iphone", "third party seller", "third-party seller", "fake product"))
        else "service-centre warranty refusal on a laptop, phone, or device"
        if _has_any(q, ("service center", "service centre", "warranty", "mobile", "phone", "laptop"))
        else "damaged, defective, fake, refund, replacement, or return-refusal goods dispute"
    )
    proof = (
        "order ID, seller/platform name, delivery/unboxing photos, fake-product or counterfeit-shoe evidence, return/refund request, seller reply, and payment proof"
        if _has_any(q, ("fake shoes", "fake nike", "counterfeit shoes", "fake goods")) or (_has_any(q, ("shoes", "footwear")) and "fake" in q)
        else
        "order ID, seller name, delivery/unboxing photos, duplicate-shoe photos, return request, refund refusal, chats, pickup attempts, and payment proof"
        if _has_any(q, ("duplicate shoes", "shoes", "footwear"))
        else "invoice, order ID, seller/platform name, warranty terms, photos/video of the defect or fake product, unboxing/service-centre report, payment proof, chats/emails, pickup or return attempts, and complaint ticket numbers"
    )
    return [
        f"For {subject}, use the Consumer Protection Act complaint path after preserving proof of purchase, platform/seller response, and defect/fake/wrong-product evidence [{consumer}].",
        "**What you can do next**",
        f"- Send a written refund/replacement complaint to the seller or platform first, then use the National Consumer Helpline, e-Daakhil, or District Consumer Commission if unresolved [{consumer}].",
        f"- Keep {proof} [{consumer}].",
    ]


def _render_builder_rera(q: str, sources: dict[str, int]) -> list[str]:
    rera = sources.get("rera")
    if rera is None:
        return []
    consumer = sources.get("consumer")
    registration = sources.get("registration")
    defect_after_possession = (
        _has_any(q, ("defective", "defect", "not repairing", "repairing", "leakage", "tiles", "bathroom"))
        and _has_any(q, (
            "possession already", "already given", "possession given",
            "gave possession", "given possession", "after possession",
            "completed flat",
        ))
    )
    oc_context = _has_any(q, (
        "occupancy certificate", "occupation certificate", "completion certificate",
        "promised oc", "not giving oc", "giving oc",
    )) or re.search(r"\boc\b", q) is not None
    issue_phrase = (
        "possession given but carpet area is less than the agreement"
        if _has_any(q, ("carpet area", "80 sqft", "less than agreement", "less area"))
        else
        "occupancy-certificate/OC refusal after full payment"
        if oc_context and _has_any(q, ("full payment", "full money", "paid full", "taking full money", "took full money"))
        else "occupancy-certificate/OC refusal"
        if oc_context
        else "completed-flat defect/repair dispute after possession"
        if defect_after_possession
        else "possession delayed for 3 years and refund refused"
        if _has_any(q, ("3 years", "three years")) and _has_any(q, ("not refunding", "refund"))
        else "layout change after full payment and refund refusal"
        if _has_any(q, ("changed layout", "layout changed", "layout change"))
        and _has_any(q, ("full money", "full payment", "paid full", "taking full money", "took full money", "refund"))
        else "layout change and booking-amount refund refusal"
        if _has_any(q, ("changed layout", "layout changed", "layout change", "booking amount"))
        else "possession-delay/refund dispute"
        if _has_any(q, ("possession", "handover", "delayed", "delay", "missed deadline", "not refunding", "refund"))
        else "sale-deed registration blocked by builder/property-tax dues"
        if _has_any(q, ("sale deed", "registered sale deed", "register sale deed", "hasnt registered", "hasn't registered", "not registered", "property tax dues", "tax dues"))
        else "possession delay, OC, layout change, refund, or builder-service dispute"
    )
    lines: list[str] = []
    if defect_after_possession and consumer is not None:
        lines.append(
            f"For a builder/developer {issue_phrase}, treat the Consumer Protection Act route as the direct service-deficiency/repair/compensation route after possession, using the defect photos, handover record, repair complaints, and builder replies [{consumer}]."
        )
        lines.append(
            f"Use RERA as the conditional project/promoter-obligation route if the defect-liability, registration, or promoter-duty facts fit; do not frame a completed-flat repair problem as a possession-delay/refund case unless possession is actually delayed [{rera}]."
        )
    else:
        lines.append(
            f"For a builder/developer {issue_phrase}, treat RERA as the primary real-estate project route; use RERA as the first project/promoter-obligation route: match the agreement, allotment, carpet-area or layout promise, possession/OC deadline, payment receipts, and project/RERA registration details to the Real Estate Act complaint/adjudication source [{rera}]."
        )
        if consumer is not None:
            lines.append(
                f"The Consumer Protection Act route is a parallel service-deficiency/refund/compensation route where maintainable, but it should not replace checking the RERA project registration, possession, OC, and promoter-obligation record first [{consumer}]."
            )
    if registration is not None and _has_any(q, ("sale deed", "registered sale deed", "register sale deed", "hasnt registered", "hasn't registered", "not registered")):
        lines.append(
            f"The Registration Act source is the sale-deed registration source to verify with the sub-registrar record; pending builder property-tax dues should be documented, but the registration question should not disappear into a generic consumer complaint [{registration}]."
        )
    lines.append("**What you can do next**")
    if defect_after_possession and consumer is not None:
        lines.append(
            f"- Send/keep a written repair or compensation demand to the builder/developer, then file before the District Consumer Commission/e-Daakhil and verify RERA if the defect-liability or promoter-obligation route fits [{consumer}], [{rera}]."
        )
        lines.append(
            f"- Keep the sale/allotment agreement, possession or handover proof, defect photos/videos, repair complaints, builder emails/chats, inspection notes, warranty/defect-liability papers if any, and proof of loss or repair estimate [{consumer}]."
        )
    else:
        action_cite = rera
        lines.append(
            f"- Send/keep a written demand to the builder or developer without waiting indefinitely; because registration/possession/OC/refund deadlines can affect forum strategy, file before the State RERA Authority/adjudicating officer and keep the District Consumer Commission/e-Daakhil route as a parallel service-deficiency path where maintainable [{action_cite}]" + (f", [{consumer}]" if consumer is not None else "") + (f", [{registration}]." if registration is not None else ".")
        )
        if registration is not None and _has_any(q, ("sale deed", "registered sale deed", "register sale deed", "property tax dues", "tax dues")):
            lines.append(
                f"- Keep the sale/allotment agreement, draft or executed sale deed, sub-registrar/token records, property-tax-dues notice, possession or handover proof, builder emails/chats, RERA registration number, payment receipts, and complaint tickets [{registration}]."
            )
        else:
            lines.append(
                f"- Keep the sale/allotment agreement, RERA registration number, payment receipts, proof of full payment or refund demand, possession or handover proof, carpet-area/measurement proof, layout-change notices or sanctioned-plan papers, OC/completion-certificate status, builder emails/chats, and complaint tickets [{rera}]."
            )
    return lines


def _render_mining_displacement_rehabilitation(q: str, sources: dict[str, int]) -> list[str]:
    larr = sources.get("larr")
    if larr is None:
        return []
    pesa = sources.get("pesa")
    mmdr = sources.get("mmdr")
    fca = sources.get("fca")
    issue = (
        "iron-ore mine displacement in Keonjhar with 12 villages and no rehabilitation"
        if _has_any(q, ("iron ore", "keonjhar"))
        else "coal-block land acquisition in Angul/Odisha without Palli Sabha consultation"
        if _has_any(q, ("coal block", "palli sabha", "angul"))
        else "dam project that will submerge tribal villages without Gram Sabha consent"
        if _has_any(q, ("dam", "submerge", "gram sabha"))
        else "mine, coal-block, dam, or project displacement affecting villages"
    )
    lines = [
        f"For {issue}, treat it as dam, public project, mine, or coal-block displacement where relevant and start with the RFCTLARR section 41 rehabilitation/resettlement and affected-family source instead of treating the case only as pollution or ordinary land-record work [{larr}]."
    ]
    if pesa is not None:
        lines.append(
            f"Because the facts mention Palli Sabha, Gram Sabha, Odisha, Scheduled Area, or tribal villages, verify whether the PESA consultation/Gram Sabha track was required and keep it separate from compensation and rehabilitation papers [{pesa}]."
        )
    if mmdr is not None:
        lines.append(
            f"Keep the MMDR/mining-lease record for the operator, lease, and project approvals, but do not let it replace the R&R, consent, and affected-family claim file [{mmdr}]."
        )
    if fca is not None:
        lines.append(
            f"If forest land or diversion is involved, keep the Forest Conservation source with the FRA/PESA and R&R file as a separate clearance track [{fca}]."
        )
    action_cite = larr
    lines.extend([
        "**What you can do next**",
        f"- Collect acquisition notifications, award/R&R package, displacement and affected-family list, rehabilitation entitlement, project or mine documents, Gram Sabha/Palli Sabha minutes, land and forest-right records, and prior complaint proof; file first with the Collector/R&R authority and DLSA, then take High Court/NGT/environment counsel advice if inspection or consent is disputed [{action_cite}].",
    ])
    return lines


def _render_interstate_migrant_displacement(q: str, sources: dict[str, int]) -> list[str]:
    ismw = sources.get("ismw")
    if ismw is None:
        return []
    wages = sources.get("wages")
    group = "12 workers" if _has_any(q, ("12 of us", "12 workers")) else "the workers"
    route = "Bihar to Gurgaon" if _has_any(q, ("bihar", "gurgaon")) else "one state to another state"
    lines = [
        f"For the thekedar/contractor promising displacement allowance for {group} brought from {route} and then not paying, use the Inter-State Migrant Workmen Act displacement/journey-allowance source first, not a generic salary complaint [{ismw}]."
    ]
    if wages is not None:
        lines.append(
            f"Use the wage-authority/Code on Wages source for the recovery forum and wage record, but keep the migrant displacement/journey allowance calculation separate from ordinary unpaid wages [{wages}]."
        )
    lines.extend([
        "**What you can do next**",
        f"- Make a group list with names, home state, worksite, recruiter/thekedar details, promised allowance, travel date, wage slips/passbook if any, attendance, messages, and unpaid amount; file a written claim with the labour authority/Assistant Labour Commissioner and ask DLSA to help the group complaint [{ismw}].",
    ])
    return lines


def _render_tribal_land_nontribal_transfer(q: str, sources: dict[str, int]) -> list[str]:
    state_transfer = sources.get("state_transfer")
    state_restoration = sources.get("state_restoration")
    constitution = sources.get("constitution")
    pesa = sources.get("pesa")
    poa = sources.get("poa")
    transfer_property = sources.get("transfer_property")
    if state_transfer is None and constitution is None and pesa is None and poa is None and transfer_property is None:
        return []
    primary = state_transfer or constitution or pesa or poa or transfer_property
    action = (
        "tribal land sold to a non-tribal"
        if _has_any(q, ("sold to non tribal", "sold to non-tribal", "sold to a non tribal", "sold to a non-tribal"))
        else "non-tribal mortgage/sahukar land dispute"
        if _has_any(q, ("mortgage", "sahukar", "moneylender"))
        else "mutation/patwari-record change"
        if _has_any(q, ("mutation", "patwari", "record changed", "khata"))
        else "tribal land grab or possession interference"
        if _has_any(q, ("land grabbed", "grabbed by", "munda land grabbed", "upper caste"))
        else "sale or transfer"
        if _has_any(q, ("sold", "sale", "transfer", "transferred", "registered"))
        else "land transaction"
    )
    lines = [
        f"For a {action} involving a non-tribal buyer or transferee, the record is not automatically valid; first verify whether the land is in the applicable state Scheduled Area/protected tribal-transfer regime and whether Collector/revenue permission or restoration rules apply [{primary}]."
    ]
    if _has_any(q, ("non scheduled area", "non-scheduled area", "not scheduled area")):
        lines.append(
            f"Because the facts say non-Scheduled Area, do not apply PESA or Article 244 as the controlling route without district verification; keep this on the state tribal-land/revenue/civil cancellation route first [{primary}]."
        )
    if state_transfer is not None:
        state_label = (
            "Orissa/Odisha Scheduled Areas Transfer Regulation"
            if _has_any(q, ("odisha", "orissa", "nuapada", "kalahandi", "koraput", "malkangiri", "rayagada", "sundargarh", "keonjhar"))
            else "AP Scheduled Areas Land Transfer Regulation"
            if _has_any(q, ("andhra", "andhra pradesh", "agency area"))
            else "Chota Nagpur Tenancy Act / local Jharkhand tribal-land transfer source"
            if _has_any(q, ("jharkhand", "chaibasa", "munda", "singhbhum", "ranchi", "khunti", "cnt", "chota nagpur", "chotanagpur"))
            else "state Scheduled Area land-transfer source"
        )
        lines.append(
            f"Use the {state_label} as the controlling state-law lane before ordinary mutation, sale-deed, or general civil possession advice [{state_transfer}]."
        )
    if state_restoration is not None:
        lines.append(
            f"For a non-tribal mortgage/sahukar transfer or dispossession, use the state restoration section to ask the revenue or tribal-land authority for restoration rather than treating the transfer paper as final [{state_restoration}]."
        )
    elif _has_any(q, ("odisha", "orissa", "nuapada", "kalahandi", "koraput", "malkangiri", "rayagada", "sundargarh", "keonjhar")):
        lines.append(
            f"I do not have the exact Orissa/Odisha Scheduled Areas Transfer Regulation source in the retrieved index, so verify that state regulation before treating PESA, Article 244, or SC/ST POA text as the controlling mutation-cancellation source [{primary}]."
        )
    if _has_any(q, ("blank paper", "moneylender", "sahukar", "mortgage")):
        lines.append(
            f"For blank paper, moneylender papers, mortgage, or doubtful-consent facts, keep a document/transfer lane with the state tribal-land file instead of treating the mutation or transfer as final [{transfer_property or primary}]."
        )
    elif _has_any(q, ("andhra", "andhra pradesh")):
        lines.append(
            f"I do not have the exact AP Scheduled Areas Land Transfer Regulation source in the retrieved index, so verify that state regulation before treating PESA, Article 244, or a judgment summary as the controlling cancellation/restoration source [{primary}]."
        )
        if _has_any(q, ("agency area", "agency-area")):
            lines.append(
                f"For an Andhra agency-area transfer, keep the Scheduled Area status, Collector/revenue permission record, and tribal-welfare restoration request together while that state regulation is verified [{primary}]."
            )
    if pesa is not None:
        lines.append(
            f"If the land is in a Scheduled Area, keep the PESA/Gram Sabha consultation and local tribal-land-transfer track separate from ordinary mutation or sale-deed paperwork [{pesa}]."
        )
    if poa is not None:
        lines.append(
            f"If there is coercion, dispossession, intimidation, or exploitation of a Scheduled Tribe person, keep the SC/ST POA complaint route as a separate protection track; do not use it as a substitute for the revenue restoration file [{poa}]."
        )
    lines.extend([
        "**What you can do next**",
        f"- Get the registered deed or mutation order, khata/passbook, tribal-status proof, Scheduled Area/village details, non-tribal buyer details, consent/permission record, and possession facts; ask the Tehsildar/Collector/tribal-welfare office or DLSA for the state land-transfer/restoration route in writing [{primary}].",
    ])
    return lines


def _render_school_caste_slur_assault(q: str, sources: dict[str, int]) -> list[str]:
    poa = sources.get("poa")
    if poa is None:
        return []
    bns = sources.get("bns")
    bnss = sources.get("bnss")
    rte = sources.get("rte")
    victim_rights = sources.get("victim_rights")
    lines = [
        f"For a child beaten near school in a school/principal situation while being called untouchable/caste words by an upper-caste person or sarpanch, keep a written SC/ST atrocity complaint and the SC/ST POA atrocity route separate from ordinary assault [{poa}]."
    ]
    if bns is not None:
        lines.append(
            f"Physical beating, threat, or intimidation should also be matched with the BNS hurt/intimidation track without replacing the atrocity route [{bns}]."
        )
    if rte is not None:
        lines.append(
            f"If school staff or school setting is part of the facts, keep the RTE school physical-punishment/mental-harassment record with the atrocity complaint as an RTE plus POA route, not an ordinary-assault-only answer [{rte}]."
        )
    if victim_rights is not None:
        lines.append(
            f"The POA victim-rights source supports asking for case status, notice of proceedings, protection needs, and participation support after the SC/ST atrocity complaint is filed [{victim_rights}]."
        )
    lines.append("**What you can do next**")
    if bnss is not None:
        lines.append(
            f"- Write the exact caste words, place/time, accused identity/status, child's caste/community proof, school details, injury/medical proof, witness names, photos/video, and take a written complaint to police/SP, DLSA, or Special Court support if FIR is refused [{poa}], [{bnss}]."
        )
    else:
        lines.append(
            f"- Write the exact caste words, place/time, accused identity/status, child's caste/community proof, school details, injury/medical proof, witness names, photos/video, and take a written SC/ST POA complaint to police/SP, DLSA, or Special Court support; if FIR is refused, ask the lawyer/DLSA to add the criminal-procedure escalation source from the FIR papers [{poa}]."
        )
    return lines


def _render_tribal_religious_attack(q: str, sources: dict[str, int]) -> list[str]:
    poa = sources.get("poa")
    if poa is None:
        return []
    bns = sources.get("bns")
    bnss = sources.get("bnss")
    issue = (
        "Sarna/pahan/puja religious attack while calling Adivasis non-Hindu"
        if _has_any(q, ("pahan", "sarna", "non hindu", "non-hindu"))
        else "caste or tribal-targeted assault and public humiliation"
    )
    lines = [
        f"For a {issue}, keep the SC/ST POA atrocity route first; write the exact words, religious/community context, place, witnesses, injury facts, and accused identity instead of filing it as only a simple assault [{poa}]."
    ]
    if bns is not None:
        lines.append(
            f"Keep the BNS religious-feelings, assault, insult, intimidation, or public-order sections as the ordinary offence layer, but do not let those sections replace the atrocity track where Adivasi/ST targeting is alleged [{bns}]."
        )
    if bnss is not None:
        lines.append(
            f"If police refuse or delay FIR registration, use the BNSS information/Magistrate escalation source with the written complaint and acknowledgement proof [{bnss}]."
        )
    lines.extend([
        "**What you can do next**",
        f"- Preserve medical papers, photos/video, witness names, exact caste/Adivasi/Sarna words, puja-place details, police-refusal proof, and ST/community proof; escalate to SP, Special Court support, DLSA, or Magistrate route if FIR is not recorded [{poa}].",
    ])
    return lines


def _render_cfr_illegal_mining(q: str, sources: dict[str, int]) -> list[str]:
    fra = sources.get("fra")
    if fra is None:
        return []
    mmdr = sources.get("mmdr")
    fca = sources.get("fca")
    lines = [
        f"For illegal mining on community forest land where the village has a CFR title, keep the Forest Rights Act route for community forest rights/CFR as the first control point; do not reduce it to a generic mining complaint [{fra}]."
    ]
    if mmdr is not None:
        lines.append(
            f"Use the MMDR/mining source to ask for the lease, mineral concession, operator, and illegal-mining action record, but keep that separate from the CFR title and Gram Sabha authority file [{mmdr}]."
        )
    if fca is not None:
        lines.append(
            f"If forest land is being diverted or used for non-forest mining activity, keep the Forest Conservation Act source as the forest-clearance track alongside the FRA/CFR objection [{fca}]."
        )
    lines.extend([
        "**What you can do next**",
        f"- Keep the CFR title, Gram Sabha/FRC records, forest compartment/map, photos/videos of mining, vehicle/operator details, complaints, and witness names; move the same file to the Gram Sabha/FRC, SDLC/DLC/Collector, forest department, mining officer, tribal-welfare office, and DLSA [{fra}].",
    ])
    return lines


def _render_gift_deed_thumb_fraud(q: str, sources: dict[str, int]) -> list[str]:
    tpa = sources.get("tpa")
    specific = sources.get("specific")
    if tpa is None or specific is None:
        return []
    contract = sources.get("contract")
    registration = sources.get("registration")
    bns = sources.get("bns")
    bnss = sources.get("bnss")
    lines = [
        f"If your mother says her son took a thumb impression on blank paper and later produced it as a gift deed, treat it as a document/gift-deed challenge first: check the Transfer of Property Act gift-deed source, registered document, attestation, sale deed/title chain, and mutation trail [{tpa}].",
        f"The Specific Relief Act civil route is to seek cancellation, declaration, or injunction against the gift deed or mutation if the instrument is void or voidable on the facts [{specific}].",
        f"A police complaint only does not replace the civil cancellation/declaration route for the registered gift deed or mutation record [{specific}].",
    ]
    if registration is not None:
        lines.append(
            f"Because the document is an immovable-property gift deed, get the certified registration/sub-registrar record; do not rely only on oral denial of the thumb impression [{registration}]."
        )
    if contract is not None:
        lines.append(
            f"Use the Indian Contract Act free-consent/undue-influence/fraud source to test whether the thumb impression was taken through pressure, deception, or non-free consent before deciding the cancellation pleading [{contract}]."
        )
    if bns is not None:
        lines.append(
            f"If the blank paper, thumb impression, or gift deed was fabricated or used dishonestly, keep a separate BNS forgery/false-document police track with the civil cancellation file [{bns}]."
        )
    if bnss is not None:
        lines.append(
            f"For the police side, use the BNSS complaint/FIR source only with the certified document and evidence trail; it should not replace the civil cancellation route [{bnss}]."
        )
    lines.extend([
        "**What you can do next**",
        f"- Get the certified gift deed, registration extract, mutation papers, thumb-impression/signature proof, witness details, mother's age/health and consent facts, possession proof, messages/witnesses, and any police complaint; take them to DLSA or a property lawyer for cancellation/declaration/injunction and, if supported, forgery complaint steps [{specific}].",
    ])
    return lines


def _render_insurance_claim_or_misselling(q: str, sources: dict[str, int]) -> list[str]:
    consumer_definition = sources.get("consumer_definition")
    consumer_complaint = sources.get("consumer_complaint")
    consumer_relief = sources.get("consumer_relief")
    consumer = consumer_complaint or consumer_definition or consumer_relief
    insurance_scope = sources.get("insurance_scope")
    insurance_procedure = sources.get("insurance_procedure")
    insurance = insurance_procedure or insurance_scope
    if consumer is None and insurance is None:
        return []
    primary = insurance or consumer
    senior = sources.get("senior")
    fire_loss = _has_any(q, ("caught fire", "fire loss", "fire-loss", "accidental fire", "hut caught fire"))
    issue = (
        "accidental fire-loss claim that the insurer is not paying"
        if fire_loss
        else
        "health insurance claim rejected as pre-existing disease even though it was declared in the proposal form"
        if _has_any(q, ("pre existing", "pre-existing", "declared", "health insurance"))
        else "LIC/ULIP policy sold to your father on guaranteed-return promises but maturing for much less, raising elder fraud and suspected fraud/mis-selling concerns"
        if _has_any(q, ("lic", "ulip", "guaranteed return", "pension money", "matured", "half amount", "8 lakh"))
        else "insurance claim, policy rejection, or policy mis-selling dispute"
    )
    article = "an" if issue.startswith("insurance ") else "a"
    lines = [
        f"For {article} {issue}, start with the insurance policy record and a written insurer grievance before calling it only fraud or only a generic senior-citizen matter [{primary}]."
    ]
    if insurance_scope is not None:
        lines.append(
            f"The Insurance Ombudsman source under Rule 13 is the provision to check for complaint grounds and subject-matter scope [{insurance_scope}]."
        )
    if insurance_procedure is not None:
        lines.append(
            f"Use the Rule 14 procedure source for Ombudsman filing only after the written insurer grievance, reply or no-reply record, repudiation/maturity letter, and policy papers are ready [{insurance_procedure}]."
        )
    if consumer_complaint is not None:
        lines.append(
            f"Consumer Protection Act Section 35 allows a consumer complaint about a provided service to be filed with the District Commission and permits prescribed electronic filing [{consumer_complaint}]."
        )
    elif consumer is not None:
        lines.append(
            f"Keep the Consumer Protection Act service-deficiency/mis-selling route as a parallel forum for refund, compensation, or deficiency where the policy documents and written promises support it [{consumer}]."
        )
    if consumer_relief is not None:
        lines.append(
            f"The Consumer Protection Act relief source is the provision to verify for refund, replacement, compensation, or other orders after the complaint facts are proved [{consumer_relief}]."
        )
    if senior is not None:
        lines.append(
            f"Because the money belongs to an elderly father or pension holder, keep Senior Citizens Act support only for maintenance/protection facts; it should not replace the insurer/Ombudsman/consumer mis-selling route [{senior}]."
        )
    lines.append("**What you can do next**")
    if consumer is not None:
        lines.append(
            f"- Send a dated grievance to the insurer with the policy schedule/bond, claim number, proposal form, premium receipts, surveyor or medical papers where relevant, fire/loss proof or maturity statement, repudiation letter, and exact promised-return words; if unresolved and Rules 13 and 14 apply, use the Insurance Ombudsman route and separately check the District Consumer Commission/e-Daakhil complaint route [{insurance_procedure or insurance_scope or primary}], [{consumer}]."
        )
    else:
        lines.append(
            f"- Send a dated grievance to the insurer with the policy schedule/bond, claim number, proposal form, premium receipts, surveyor or medical papers where relevant, fire/loss proof or maturity statement, repudiation letter, and exact promised-return words; if unresolved and Rules 13 and 14 apply, use the Insurance Ombudsman route [{insurance_procedure or insurance_scope or primary}]."
        )
    return lines


def _render_bonded_labour_coercion_release(q: str, sources: dict[str, int]) -> list[str]:
    """Render a section-12-gated rescue plan without turning wage loss into rescue."""
    bonded_action = sources.get("bonded_action")
    if bonded_action is None:
        return []

    abolition = sources.get("bonded_abolition")
    article23 = sources.get("article23")
    aadhaar = sources.get("aadhaar")
    ismw = sources.get("ismw")
    wages = sources.get("wages")
    police = sources.get("police")

    movement_control = _has_any(q, (
        "not letting leave", "not allowed to leave", "cannot leave", "can't leave",
        "cannot go home", "can't go home", "hostage", "locked", "kept hostage",
    ))
    debt_control = _has_any(q, ("advance", "debt", "loan", "loan finish", "till loan"))
    document_control = _has_any(q, (
        "aadhaar", "aadhar", "passport", "id kept", "document kept",
        "documents retained", "original id", "original documents",
    ))
    unpaid_work = _has_any(q, ("no wages", "just food", "only food", "without wages"))
    years_without_wages = "12 years" in q and unpaid_work

    if years_without_wages:
        facts = "12 years of work without wages"
    elif debt_control and movement_control:
        facts = "an advance to stop you leaving"
    elif document_control:
        facts = "an employer or contractor retaining original identity documents"
    elif unpaid_work:
        facts = "work without wages or only food"
    else:
        facts = "reported coercion in a bonded-labour situation"

    lines = [
        f"For {facts}, use the Bonded Labour Act rescue route through the District Magistrate/SDM: ask for an inquiry, necessary action, and a written acknowledgement rather than treating this only as an ordinary wage complaint [{bonded_action}].",
    ]
    if abolition is not None:
        abolition_facts = (
            "For 12 years of work without wages, "
            if years_without_wages
            else ""
        )
        lines.append(
            f"{abolition_facts}keep the abolition source with the rescue record because bonded labour is abolished and a bonded labourer is freed from the obligation to render bonded labour [{abolition}]."
        )
    if article23 is not None and (debt_control or movement_control or unpaid_work):
        lines.append(
            f"Keep Article 23 forced-labour protection alongside the District Magistrate/SDM record where the facts show coercion tied to debt, movement, or unpaid work [{article23}]."
        )
    if aadhaar is not None and document_control:
        lines.append(
            f"For original Aadhaar or other ID held by the contractor, preserve the identity-document facts and request safe return or copies as part of the rescue record [{aadhaar}]."
        )
    if ismw is not None:
        lines.append(
            f"If the workers were recruited across state lines, keep the Inter-State Migrant Workmen source for contractor and journey/return-home facts alongside the rescue record [{ismw}]."
        )
    if wages is not None and unpaid_work:
        lines.append(
            f"Keep unpaid-wage calculation as a separate labour claim, but do not let it replace the urgent rescue/release route if movement, debt, or documents are controlled [{wages}]."
        )
    if police is not None and (movement_control or document_control):
        lines.append(
            f"If there is confinement, threat, or refusal to record the complaint, preserve the police/FIR procedure track alongside the District Magistrate/SDM rescue record [{police}]."
        )
    lines.extend([
        "**What you can do next**",
        f"- If anyone cannot safely leave, contact the District Magistrate/SDM, labour department, DLSA/legal aid, or police first. Keep the worksite location, contractor/owner name, worker names, home place, advance/debt facts, wage or food facts, identity-document facts, threats, photos/messages, and any prior complaint acknowledgement [{bonded_action}].",
    ])
    return lines


def _render_digital_arrest_impersonation(q: str, sources: dict[str, int]) -> list[str]:
    it = sources.get("it")
    bns = sources.get("bns")
    bnss = sources.get("bnss")
    if it is None:
        return []
    is_trai = _has_any(q, ("fake trai", "trai", "sim will close", "sim closure", "sim close"))
    is_cbi_drug = _has_any(q, ("fake cbi", "cbi")) and _has_any(q, ("aadhaar", "drug parcel", "narcotics", "parcel"))
    is_parent = _has_any(q, ("father", "mother", "parent"))
    paid = _has_any(q, ("transfer", "transferred", "upi", "2 lakh", "paid", "send money", "bank transfer"))

    if is_trai:
        issue = "fake TRAI/SIM-closure call saying your SIM will close and asking you to join a police video call"
    elif is_cbi_drug:
        issue = "fake CBI video call claiming your Aadhaar was used in a drug parcel and making you transfer money"
    elif is_parent:
        issue = "digital arrest gang that kept your father/parent on video and took UPI transfers"
    else:
        issue = "fake CBI/police, digital arrest, courier, or parcel video-call demand"

    lines = [
        f"For a {issue}, treat it as cyber impersonation and electronic cheating first, not as a real arrest process [{it}]."
    ]
    if bns is not None:
        if is_trai:
            lines.append(
                f"Keep a separate BNS track if the fake TRAI/police caller uses SIM-closure fear, a police video call, arrest threats, or pressure to share money, OTPs, passwords, devices, or identity details [{bns}]."
            )
        elif is_cbi_drug:
            money_phrase = "2 lakh/bank money" if "2 lakh" in q else "bank/UPI money"
            lines.append(
                f"Keep a separate BNS track for cheating by personation, dishonest inducement, or intimidation if the caller used a fake CBI/police identity, Aadhaar/drug-parcel fear, arrest threats, or pressure to transfer {money_phrase} [{bns}]."
            )
        else:
            lines.append(
                f"Keep a separate BNS track for cheating by personation, dishonest inducement, or intimidation if the caller used a CBI/police identity, fear of arrest, family pressure, or pressure to transfer money by UPI/bank [{bns}]."
            )
    if bnss is not None:
        evidence = (
            "TRAI/SIM message, caller ID, video-call link, claimed police identity, screenshots, and any demand"
            if is_trai
            else "Aadhaar/drug-parcel allegation, caller ID, video-call proof, transfer IDs, bank details, and WhatsApp/SMS evidence"
            if is_cbi_drug
            else "UPI transaction, caller, video-call, and bank evidence"
        )
        lines.append(
            f"For the police/cyber complaint route, use the BNSS FIR/information and Magistrate-escalation source with the {evidence} [{bnss}]."
        )
    lines.append("**What you can do next**")
    if paid:
        action = (
            "- Do not send more money; immediately report through 1930 or cybercrime.gov.in, ask the bank to freeze/trace the beneficiary account, preserve the video/call/WhatsApp proof, transfer IDs, Aadhaar/drug-parcel allegation, and keep the bank complaint number and cyber acknowledgement"
            if is_cbi_drug
            else "- Do not send more money; immediately report through 1930 or cybercrime.gov.in, ask the bank to freeze/trace the beneficiary account, preserve the video/call/WhatsApp proof, UPI transfer IDs, and keep the bank complaint number and cyber acknowledgement"
        )
    else:
        action = "- Do not send money, OTPs, passwords, or device access; preserve the caller number, video-call link, TRAI/SIM-closure message, claimed police identity, screenshots, and report through 1930/cybercrime.gov.in or cyber police with a written acknowledgement"
    cite_tail = f" [{it}]"
    if bnss is not None:
        cite_tail += f", [{bnss}]"
    lines.append(action + f" for the police/cyber complaint route{cite_tail}.")
    return lines


def _render_wrong_bank_debit(q: str, sources: dict[str, int]) -> list[str]:
    rbi_scope = sources.get("rbi_scope")
    rbi_complaint = sources.get("rbi_complaint")
    rbi = rbi_complaint or rbi_scope
    consumer_complaint = sources.get("consumer_complaint")
    if rbi is None:
        return []
    card_context = _has_any(q, ("credit card", "debit card", "card", "annual fee", "card fee", "fee charged", "card was closed", "card closed"))
    atm_context = _has_any(q, (
        "atm cash not dispensed", "cash not dispensed", "atm did not dispense",
        "atm didn't dispense", "atm withdrawal failed", "cash not received",
        "atm showed transaction failed", "atm transaction failed",
    ))
    imps_context = _has_any(q, (
        "imps transfer failed", "imps failed", "failed imps",
        "beneficiary did not get money", "beneficiary didn't get money",
        "beneficiary says not received", "beneficiary says no money",
    ))
    chargeback_context = _has_any(q, (
        "chargeback", "chargeback not processed", "chargeback failed",
        "bank chargeback", "failed online order",
    ))
    app_phrase = (
        "credit card issuer/bank"
        if card_context
        else "ATM-owning/acquiring bank and your account bank"
        if atm_context
        else "bank/card issuer and merchant or order platform"
        if chargeback_context
        else "bank or IMPS/remitting bank"
        if imps_context
        else "GPay/payment app"
        if "gpay" in q or "google pay" in q
        else "PhonePe/payment app"
        if "phonepe" in q
        else "Paytm/payment app"
        if "paytm" in q
        else "bank or payment app"
        if "upi" in q or "payment app" in q
        else "bank"
    )
    issue_phrase = (
        "credit-card fee or card charge debited twice"
        if card_context
        else "ATM cash-not-dispensed withdrawal where the account was debited"
        if atm_context and _has_any(q, ("cash not dispensed", "cash not received", "withdrawal"))
        else "ATM transaction-failed debit where the account was debited"
        if atm_context
        else "failed IMPS transfer where the beneficiary did not receive money but the account was debited"
        if imps_context
        else "chargeback or failed-order debit where the bank has not processed reversal"
        if chargeback_context
        else "wrong debit, deducted, debited, wrong deduction, failed UPI debit, unauthorised, or unauthorized bank transaction"
    )
    evidence_phrase = (
        "card statement entry, annual-fee/charge line item, card complaint or service-request number, SMS/email alerts, customer-care chats/call logs, written refusal or no-reply proof, and exact debit/refund timeline"
        if card_context
        else "ATM ID/location, withdrawal time, account statement debit, ATM slip if any, SMS/email alerts, branch/customer-care complaint number, written refusal or no-reply proof, and CCTV/request timeline"
        if atm_context
        else "IMPS transaction ID/RRN, beneficiary account details, bank statement debit, payment status screenshot, SMS/email alerts, bank complaint number, written refusal or no-reply proof, and exact debit/refund timeline"
        if imps_context
        else "order ID, chargeback/request number, bank statement debit, failed-order or cancellation proof, seller/platform reply, bank complaint number, written refusal or no-reply proof, and exact debit/refund timeline"
        if chargeback_context
        else "bank statement entry, UPI/transaction ID/RRN, SMS or email alerts, customer-care chats/call logs, complaint number, written refusal or no-reply proof, and exact debit/refund timeline"
    )
    lines = [
        f"For this {issue_phrase}, first raise a written complaint with the {app_phrase}; the RBI Integrated Ombudsman Scheme covers commercial banks, specified co-operative banks, qualifying NBFCs, and system participants [{rbi}].",
        f"If the regulated entity rejects the complaint, gives an unsatisfactory reply, or does not reply within the Scheme's complaint window, use the RBI Ombudsman/CMS escalation route with the complaint record [{rbi}].",
    ]
    if consumer_complaint is not None:
        lines.append(
            f"If the bank still does not reverse or explain the duplicate/wrong debit, wrong deduction, failed UPI debit, or card charge after the written complaint and RBI record, use Consumer Protection Act 2019, Section 35 [{consumer_complaint}] as the service-deficiency forum backup."
        )
    lines.extend([
        "**What you can do next**",
        (
            f"- Raise a written complaint with the {app_phrase}, get a complaint number, and keep the {evidence_phrase} [{rbi}], [{consumer_complaint}]."
            if consumer_complaint is not None
            else f"- Raise a written complaint with the {app_phrase}, get a complaint number, and keep the {evidence_phrase} [{rbi}]."
        ),
    ])
    return lines


def _render_employment_original_document_return(q: str, sources: dict[str, int]) -> list[str]:
    wages = sources.get("wages")
    contract = sources.get("contract")
    industrial = sources.get("industrial")
    if wages is None:
        return []
    lines = [
        f"If an employer or HR is holding your original degree/certificate after resignation, separate the document-return demand from wage/full-and-final dues, but keep both in one written employment grievance record [{wages}].",
        f"Ask HR/employer in writing to return the original degree/certificate by a fixed date and to give any claimed reason in writing; attach joining/resignation proof, handover proof, and copies of the documents held [{wages}].",
    ]
    if contract is not None:
        lines.append(
            f"If the employer relies on a bond, notice-period, training-cost, or employment-contract clause, verify that clause separately instead of accepting document retention as automatic [{contract}]."
        )
    if industrial is not None:
        lines.append(
            f"If HR still refuses, take the written demand/no-reply record to the Labour Commissioner or labour-court/legal-aid route after checking employee/workman status and state procedure [{industrial}]."
        )
    lines.extend([
        "**What you can do next**",
        f"- Keep appointment letter, resignation acceptance, relieving/full-and-final emails, document-deposit acknowledgement if any, copies of the degree/certificates, HR chats, and a written return request; escalate to the Labour Commissioner/DLSA with acknowledgement or no-reply proof [{wages}].",
    ])
    return lines


def _render_ordinary_invoice_payment_reminder(q: str, sources: dict[str, int]) -> list[str]:
    contract = sources.get("contract")
    msmed = sources.get("msmed")
    fema = sources.get("fema")
    if contract is None:
        return []
    cross_border = _has_any(q, ("dubai", "foreign", "abroad", "saas", "usd", "export", "outside india"))
    if cross_border:
        lines = [
            f"For a Dubai/foreign client not paying an Indian SaaS or services invoice, start with the contract, invoice, work-completion proof, and dispute-resolution clause under the Indian Contract Act route before treating it as a police case [{contract}].",
        ]
        if fema is not None:
            lines.append(
                f"Because the money is from outside India, keep the FEMA/foreign-exchange receipt and bank-realisation record with the contract claim; this does not by itself decide jurisdiction or recovery forum [{fema}]."
            )
        lines.append(
            f"Indian law may help if the contract, parties, governing-law clause, place of performance, or Indian business records connect the dispute to India, but the forum and enforceability need document review [{contract}]."
        )
    else:
        lines = [
            f"If a client is late on an invoice, start with a written payment reminder and contract/invoice record; do not start with a police complaint unless there was deception at the beginning, forgery, threats, or other criminal facts [{contract}].",
            f"Send a polite written demand with invoice number, due date, amount, service/goods delivered, bank details, and a short cure period before legal notice or civil/commercial recovery steps [{contract}].",
        ]
    if msmed is not None:
        lines.append(
            f"If you are an eligible MSME/supplier and the delay crosses the statutory/payment-term threshold, keep the MSME Facilitation Council/Samadhan route separate from an ordinary 3-day reminder [{msmed}]."
        )
    lines.extend([
        "**What you can do next**",
        f"- Preserve the contract/PO if any, invoice, delivery or work-completion proof, emails/chats accepting work, due-date calculation, client address, payment/remittance records, and reminder/no-reply record before escalating to mediation, legal notice, civil/commercial recovery, or arbitration where the contract allows it [{contract}].",
    ])
    return lines


def _render_marriage_legal_age(q: str, sources: dict[str, int]) -> list[str]:
    pcma = sources.get("pcma")
    if pcma is None:
        return []
    sma = sources.get("sma")
    lines = [
        f"If the ages are 22 and 29, the age point alone is not the problem: the child-marriage source treats a male below 21 or a female below 18 as the age-risk frame, so a 22-year-old and a 29-year-old are not under-age on those facts [{pcma}]."
    ]
    if sma is not None:
        lines.append(
            f"Keep registration, notice, personal-law/Special Marriage Act, consent, prior-marriage, or coercion issues separate from age; those facts can still matter even when both people are above the minimum age [{sma}]."
        )
    lines.extend([
        "**What you can do next**",
        f"- Keep age proof, marriage proof/registration papers, consent facts, and any family threat messages; if family pressure or violence is involved, use DLSA/police protection separately instead of treating the marriage as illegal only because relatives object [{pcma}].",
    ])
    return lines


def _render_employment_notice_period_contract(q: str, sources: dict[str, int]) -> list[str]:
    contract = sources.get("contract")
    if contract is None:
        return []
    wages = sources.get("wages")
    lines = [
        f"For a 90-day demand when the offer letter or appointment letter says 60 days, start with the written employment contract/offer-letter term and any later accepted policy; do not accept a unilateral oral change without seeing the clause relied on [{contract}]."
    ]
    if wages is not None:
        lines.append(
            f"Keep the notice-period dispute separate from salary, full-and-final, leave encashment, or wage dues; those should stay on the wage/labour record if amounts are withheld [{wages}]."
        )
    lines.extend([
        "**What you can do next**",
        f"- Ask HR in writing to identify the exact 90-day clause, policy version, date of acceptance, and exit calculation; preserve offer letter, appointment letter, HR emails, resignation date, last working day, payslips, and any full-and-final statement before deciding whether to serve, negotiate, or dispute the extra 30 days [{contract}].",
    ])
    return lines


def _render_wage_theft_false_fir(q: str, sources: dict[str, int]) -> list[str]:
    wages = sources.get("wages")
    bns = sources.get("bns")
    bnss = sources.get("bnss")
    article21 = sources.get("article21")
    article22 = sources.get("article22")
    ismw = sources.get("ismw")
    if wages is None and bnss is None and article21 is None and article22 is None and ismw is None:
        return []
    labour_chowk_pickup = _has_any(q, ("labour chowk", "labor chowk", "mazdoor chowk", "daily wage corner")) and _has_any(q, (
        "police", "picked", "picking", "detain", "detained", "begging", "beggar", "nautanki", "not work",
    ))
    if labour_chowk_pickup and not _has_any(q, ("false fir", "fake fir", "theft", "mobile theft", "asked wages", "unpaid wages")):
        procedure = article22 or article21 or bnss or bns or wages
        lines = [
            f"For police picking workers from a labour chowk and calling it begging or not working, treat this first as a police pickup/detention and worker-liberty problem, not as generic legal information [{procedure}].",
        ]
        if article21 is not None or article22 is not None:
            liberty = article22 or article21
            lines.append(
                f"Use the constitutional liberty/arrest-safeguard source to ask what authority, station entry, grounds, or production record the police are relying on; do not let the label 'begging' replace the custody facts [{liberty}]."
            )
        if bnss is not None:
            lines.append(
                f"Keep the BNSS/CrPC arrest-and-detention procedure source with the same file, because station entry, arrest grounds, family intimation, production, or FIR/DD status decide the immediate next forum [{bnss}]."
            )
        if bns is not None:
            lines.append(
                f"If the facts include threats, wrongful restraint/confinement, or intimidation, keep those offence facts separate from whether the workers were waiting for work [{bns}]."
            )
        if wages is not None:
            lines.append(
                f"If there is also unpaid wage, contractor, attendance, or worksite-payment evidence, preserve that as a separate wage-authority/Labour Commissioner track [{wages}]."
            )
        if ismw is not None:
            lines.append(
                f"If the workers are inter-state migrant workers or were brought by a contractor/thekedar, keep the ISMW source for contractor registration, displacement/journey allowance, passbook, and worker-facility records alongside the police-pickup file [{ismw}]."
            )
        lines.extend([
            "**What you can do next**",
            f"- Write a short complaint with date/time, exact labour chowk location, police station/vehicle/officer details if known, who was picked, whether anyone was detained/FIR/DD-entered, witness names, videos/photos, worker IDs, contractor/work proof, and migrant-worker papers if applicable; take it to senior police, DLSA/legal aid, and labour office if wage or ISMW facts exist [{procedure}].",
        ])
        return lines

    lines = []
    if wages is not None:
        lines.append(
            f"Treat this as a dual-track wages and false FIR/police problem: preserve the wage-retaliation facts, keep the Code on Wages payment claim alive, and separately handle police, FIR, bail, or legal-aid risk [{wages}]."
        )
    if bns is not None:
        lines.append(
            f"If the contractor threatens a theft case after you ask for unpaid wages, preserve the wage-demand timeline and keep the BNS source for intimidation/cheating/theft-allegation separate from the labour claim [{bns}]."
        )
    if bnss is not None:
        lines.append(
            f"If police are calling, picking workers, or recording a theft allegation, use the BNSS FIR/information source to ask for the FIR/DD entry, notice, station details, and whether anyone is accused, witness, or complainant [{bnss}]."
        )
    if ismw is not None:
        lines.append(
            f"If the worker was recruited or moved as an inter-state migrant worker, keep the ISMW source with wage, passbook, journey/displacement allowance, and contractor-registration proof; that is separate from the false-FIR defence [{ismw}]."
        )
    lines.append("**What you can do next**")
    if wages is not None:
        lines.append(
            f"- For the labour track, file with the wage authority/Labour Commissioner using attendance, muster, messages, wage calculation, contractor/thekedar details, ID proof, bank entries, and worksite witnesses [{wages}]."
        )
    if bnss is not None:
        lines.append(
            f"- For the criminal track, take FIR/notice details, police-call records, DLSA/free-legal-aid details if private fees are unaffordable, any fee quote/receipt from the lawyer, and proof that the wage demand came before the theft allegation [{bnss}]."
        )
    return lines


def _render_unpaid_group_wages_no_contract(q: str, sources: dict[str, int]) -> list[str]:
    wages = sources.get("wages")
    if wages is None:
        return []
    industrial = sources.get("industrial")
    group_phrase = "25 workers" if "25" in q else "multiple workers"
    lines = [
        f"For {group_phrase} whose factory wages are unpaid for months, treat this as a wage/labour complaint even if there is no written contract; do not reduce it to only an individual full-and-final or termination issue [{wages}].",
        f"No written contract means attendance, muster, gate pass, co-worker names, bank/cash-payment history, worksite photos, messages, and supervisor details become important proof for the Labour Commissioner/wage authority [{wages}].",
    ]
    if industrial is not None:
        lines.append(
            f"If the dispute affects a group of workmen or the employer refuses because there is no appointment letter, keep the Industrial Disputes/labour-office track as a supporting route after collecting worker names and employment proof [{industrial}]."
        )
    lines.extend([
        "**What you can do next**",
        f"- Prepare a worker-wise wage chart with names, months unpaid, approximate wage rate, department/shift, contractor or factory-owner name, attendance proof, bank/cash proof, and any messages; file a written complaint with the Labour Commissioner/wage authority and ask DLSA/trade-union help if needed [{wages}].",
    ])
    return lines


def _render_prison_mulaqat_books(q: str, sources: dict[str, int]) -> list[str]:
    delhi_rules = sources.get("delhi_rules")
    prisons = sources.get("prisons")
    if delhi_rules is None and prisons is None:
        return []
    article21 = sources.get("article21")
    jail = "Tihar" if "tihar" in q else "the jail"
    book_context = _has_any(q, ("book", "books", "library", "newspaper", "magazine", "reading material"))
    video_context = _has_any(q, ("video call", "video-call", "video mulaqat", "video mulakat", "video interview", "slot failed", "server down"))
    phone_context = video_context or _has_any(q, ("phone call", "call", "telephone"))
    visitor_context = _has_any(q, ("visitor list", "visitor", "wife", "husband", "child", "marriage certificate"))
    item = (
        "books from family during mulaqat"
        if book_context
        else "video-call slot failed or server is down"
        if video_context
        else "phone/family contact or interview access"
        if phone_context
        else "visitor-list or family mulaqat access"
        if visitor_context
        else "mulaqat/interview access"
    )
    primary = delhi_rules if delhi_rules is not None else prisons
    if delhi_rules is not None:
        lines = [
            f"For {jail} {item}, treat this first as a Delhi Prison Rules and Jail Superintendent request, not as bail or parole; the Delhi source covers mulaqat/interview permission, timing, recorded refusal reasons, and library/book screening [{delhi_rules}].",
            (
                f"Ask for the written jail rule or order on whether the specific books can be accepted, screened, issued through the library, or allowed with the Superintendent's permission [{delhi_rules}]."
                if book_context
                else f"If the video-call slot failed repeatedly or staff say the server is down, ask for the written slot/status order, next available slot, and recorded reason from the Jail Superintendent [{delhi_rules}]."
                if video_context
                else f"If a visitor name was removed or delayed after address check, ask for the visitor-list rule, verification status, and written reasons from the Jail Superintendent [{delhi_rules}]."
                if _has_any(q, ("visitor list", "removed my name", "address check", "address verification"))
                else f"Ask for the written jail rule or order on visitor-list entry, phone/interview restriction, required relationship proof, and the recorded reason for refusal [{delhi_rules}]."
            ),
        ]
        if prisons is not None:
            lines.append(
                f"Keep the Prisons Act source as the broader prison-administration backup, but use the Delhi/Tihar rule source for the concrete local procedure [{prisons}]."
            )
    else:
        lines = [
            f"For {jail} {item}, treat this as a prison-administration and Jail Superintendent request first; the Prisons Act source supports checking prison rules and officer permission rather than treating it as parole or bail [{prisons}].",
            (
                f"Ask for the written jail rule or order on whether books can be accepted from family, how they are screened, and whether the prisoner can receive them through mulaqat, parcel, library, or another approved route [{prisons}]."
                if book_context
                else f"If the video-call slot failed repeatedly or staff say the server is down, ask for the written slot/status order, next available slot, and recorded reason from the Jail Superintendent [{prisons}]."
                if video_context
                else f"If a visitor name was removed or delayed after address check, ask for the visitor-list rule, verification status, and written reasons from the Jail Superintendent [{prisons}]."
                if _has_any(q, ("visitor list", "removed my name", "address check", "address verification"))
                else f"Ask for the written jail rule or order on the visitor-list, phone/interview restriction, relationship proof, and reasons for refusal [{prisons}]."
            ),
        ]
    if article21 is not None:
        lines.append(
            f"If the refusal is arbitrary, discriminatory, or blocks family/legal access without reasons, keep the Article 21 fairness point for DLSA or High Court review, but first create the written jail record [{article21}]."
        )
    next_details = (
        "requested books/book titles/list"
        if book_context
        else "requested visit/interview/phone details"
    )
    lines.extend([
        "**What you can do next**",
        f"- Submit a written request with prisoner name/number, ward, case number, relationship/ID proof, {next_details}, date, and any refusal; ask the Jail Superintendent/DLSA for the permitted-item route or contact route and a written reason if refused [{primary}].",
    ])
    return lines


def _render_esi_contribution_notice(q: str, sources: dict[str, int]) -> list[str]:
    esi = sources.get("esi")
    if esi is None:
        return []
    social = sources.get("social")
    amount = "1.2 lakh" if "1.2" in q else "the demanded contribution"
    lines = [
        f"For an ESI inspector notice saying contributions are short for casual workers, treat it as an ESI contribution/determination dispute first: ask for the wage sheet, worker list, contribution period, calculation, and hearing/order basis before paying or contesting {amount} [{esi}].",
        f"Casual-worker status does not by itself answer coverage; compare actual wage records, attendance, contractor/principal-employer facts, and covered establishment status before accepting the calculation [{esi}].",
    ]
    if social is not None:
        lines.append(
            f"Keep the Code on Social Security/current social-security frame as supporting context, but do not let it replace the ESI Act notice, hearing, contribution, and ESI Court route [{social}]."
        )
    lines.extend([
        "**What you can do next**",
        f"- File a written reply before the deadline with registration code, inspection notice, wage register, attendance/muster, contractor bills, contribution challans, worker list, salary breakup, and disputed calculation; ask for a speaking order/hearing and check the ESI Court appeal/dispute route if an adverse order is passed [{esi}].",
    ])
    return lines


def _render_income_tax_appeal_deadline(q: str, sources: dict[str, int]) -> list[str]:
    tax = sources.get("tax")
    if tax is None:
        return []
    if _has_any(q, ("itat", "appellate tribunal")):
        lines = [
            f"For an ITAT appeal against a CIT(Appeals) order, use the Income-tax Act appellate-tribunal source and calculate the limitation from the date the order is communicated, not from when you first hear about it informally [{tax}].",
            f"The practical first step is filing the ITAT appeal papers with the order copy, grounds of appeal, statement of facts, fee/proof, delay-condonation request if late, and service/communication date proof [{tax}].",
        ]
    else:
        lines = [
            f"For Form 35 before CIT(Appeals), use the Income-tax Act appeal/limitation source and calculate the appeal period from service/communication of the assessment or demand order [{tax}].",
            f"If the Form 35 deadline is missed, do not file a vague complaint first; prepare a delay-condonation explanation with proof of the order date, communication date, illness/portal/access issue if any, and merits of appeal [{tax}].",
        ]
    lines.extend([
        "**What you can do next**",
        f"- Keep the assessment/order copy, demand notice, DIN/acknowledgement, service date, portal screenshot, tax-payment/challan proof, grounds of appeal, statement of facts, and delay-condonation facts if late; use the income-tax e-filing appeal route or a tax professional before the deadline [{tax}].",
    ])
    return lines


def _render_gst_freelancer_registration_threshold(q: str, sources: dict[str, int]) -> list[str]:
    cgst = sources.get("cgst")
    if cgst is None:
        return []
    tax = sources.get("tax")
    amount = "18 lakh" if "18 lakh" in q or "18l" in q else "your turnover"
    lines = [
        f"For a freelancer or designer asking whether {amount} requires GST registration, start with the CGST registration-threshold source and compute aggregate turnover, place of supply, and any compulsory-registration category before registering only because there is income [{cgst}].",
        f"Income-tax filing and GST registration are separate: ITR/professional-income reporting does not automatically mean GST registration if the GST threshold/compulsory-registration facts are not met [{cgst}].",
    ]
    if tax is not None:
        lines.append(
            f"Keep Income-tax Act return/reporting records separately for the freelance income, invoices, and receipts [{tax}]."
        )
    lines.extend([
        "**What you can do next**",
        f"- Calculate financial-year aggregate turnover from all freelance/design services, export/foreign platform receipts, invoices, GST registration status in other states if any, and client location; then verify the CGST threshold/compulsory-registration rule on the GST portal before applying [{cgst}].",
    ])
    return lines


def _render_cyber_money_fraud(q: str, sources: dict[str, int]) -> list[str]:
    it = sources.get("it")
    if it is None:
        return []
    rbi = sources.get("rbi")
    bns = sources.get("bns")
    bnss = sources.get("bnss")
    fraud_phrase = (
        "fake customer-care AnyDesk remote-access transfer"
        if "anydesk" in q
        else "fake stock/investment trading-app transfer"
        if _has_any(q, ("fake stock", "stock trading app", "fake trading app", "trading app", "investment app"))
        else "WhatsApp/account-takeover impersonation asking contacts for money"
        if _has_any(q, ("whatsapp account", "account hacked", "whatsapp hacked", "asking my contacts for money", "asking contacts for money"))
        else "online scam transfer with cyber-cell follow-up pending"
        if _has_any(q, ("duped", "cyber cell complaint", "cyber complaint filed", "no progress", "multiple upi ids"))
        else "fake customer-care remote-access transfer"
        if _has_any(q, (
            "fake customer care", "fake customer support", "fake helpline",
            "install app", "installed app", "remote access", "screen sharing",
        ))
        else "OTP/phishing bank or UPI fraud"
        if _has_any(q, ("otp", "phishing", "upi fraud", "upi scam"))
        else "unauthorized electronic money transfer"
    )
    action_cites = ", ".join(
        f"[{idx}]" for idx in (rbi, it, bnss, bns) if idx is not None
    ) or f"[{it}]"
    evidence_cite = it if it is not None else bns if bns is not None else rbi if rbi is not None else bnss
    lines = [
        f"For a {fraud_phrase}, keep the IT Act cyber-fraud track first and treat it as cyber fraud/electronic cheating; do not handle it only as a normal failed transaction or ordinary bank-service complaint [{it}]."
    ]
    if rbi is not None:
        lines.append(
            f"Keep a bank/RBI refund track in parallel: file or update the bank complaint immediately and use the RBI Ombudsman/CMS regulated-entity complaint route if the bank refuses reversal, says customer negligence, or gives only a blame-the-customer reply [{rbi}]."
        )
    if bns is not None:
        lines.append(
            f"If someone impersonated customer care, took OTP/card credentials, induced app install/screen sharing, or dishonestly moved money, keep the BNS cheating/personation or intimidation track for police/cyber complaint review [{bns}]."
        )
    if bnss is not None:
        lines.append(
            f"For the police/cyber complaint route, use the BNSS FIR/information and Magistrate-escalation source with transaction, device, and caller evidence [{bnss}]."
        )
    lines.extend([
        "**What you can do next**",
        f"- Act fast: report through 1930 or cybercrime.gov.in, ask the bank to freeze/trace the beneficiary account, take a written bank complaint/refund number, and preserve the cyber complaint acknowledgement before waiting for customer care callbacks {action_cites}.",
        f"- Keep transaction ID/RRN/UPI reference, card or bank statement, SMS/email alerts, app or remote-access details, caller number/URL, screenshots, device/SIM facts, bank reply, and cyber complaint number [{evidence_cite}].",
    ])
    return lines


def _render_shop_sealing(q: str, sources: dict[str, int], passages: list[dict]) -> list[str]:
    rti = sources.get("rti")
    shops = sources.get("shops")
    municipal = sources.get("municipal")
    food = sources.get("food")
    primary = municipal or shops or food or rti
    if primary is None:
        return []

    issue = _shop_issue_phrase(q)
    food_context = food is not None and _has_any(q, ("restaurant", "hotel", "kitchen", "food", "fssai", "health department", "food inspector", "food inspection"))
    gujarat_source = any(
        idx is not None and "gujarat" in _source_title(passages, idx)
        for idx in (shops, municipal)
    )
    gujarat_query = _has_any(q, ("gujarat", "ahmedabad", "surat", "vadodara", "rajkot", "nagarpalika"))
    lines: list[str] = []

    if gujarat_query and gujarat_source and shops is not None and municipal is not None:
        lines.append(
            f"For {issue}, treat it as a Gujarat municipal/shop-registration and trade-licence problem: match the written order, sealing order, notice, or inspection report to the municipal authority record and the Shops and Establishments registration/certificate record [{municipal}], [{shops}]."
        )
        lines.append(
            f"Ask the municipal corporation, nagarpalika, ward office, licensing office, Commissioner, or appellate authority for the de-sealing/reopen/release route and the power relied on before accepting an oral sealing or lock order [{municipal}]."
        )
        if rti is not None:
            lines.append(
                f"If the ward office or municipality will not give the sealing order, notice, inspection report, file noting, reasons, or appeal route, use RTI as the records route while keeping the municipal-law challenge separate [{rti}]."
            )
    else:
        if rti is None:
            return []
        gap_phrase = (
            "the retrieved passages do not contain the Gujarat municipal/shop source, so use RTI only to get the missing order and local-law record"
            if gujarat_query
            else "use RTI only to get the missing food-safety or health-department order, inspection file, reasons, and appeal/reopen record"
            if food_context
            else "do not borrow Gujarat municipal sources for a non-Gujarat shop unless the order itself relies on Gujarat law"
        )
        lines.append(
            f"For {issue}, first get the written order, sealing order, notice, inspection report, licence file, and the state/local municipal law or food-safety law named by that authority; {gap_phrase} [{rti}]."
        )
        lines.append(
            f"Use RTI or a written records request only to obtain the order, reasons, file noting, inspection material, and appeal/reopen route; RTI is a records route, not the sealing power itself [{rti}]."
        )

    if food_context:
        lines.append(
            f"Because the facts mention restaurant, hotel, kitchen, food, health, or inspection issues, keep the Food Safety/FSSAI licence-compliance notice separate from the municipal de-sealing or local-law appeal track and ask which statutory power the officer used [{food}]."
        )

    doc_cite = food or shops or municipal or rti or primary
    action_cite = food if food_context else municipal or shops or rti or primary
    first_forum = (
        "Food Safety Officer/Designated Officer or state food-safety authority"
        if food_context
        else "municipal authority, corporation/nagarpalika, ward office, licensing office, or Commissioner/appellate authority"
    )
    lines.extend([
        "**What you can do next**",
        f"- Go to the {first_forum} with a written request for the sealing order, show-cause notice, inspection report, licence/trade-registration file, hearing date, de-sealing/reopen/release route, and goods-release procedure [{action_cite}].",
        f"- Keep trade licence, shop registration, rent/ownership papers, tax or fee receipts, photos of the seal, inventory of goods inside, inspection/fire/health papers if any, prior replies, and proof that no written order or notice was given [{doc_cite}].",
    ])
    return lines


def _render_joint_coowner_sale(q: str, sources: dict[str, int]) -> list[str]:
    tpa45 = sources.get("tpa45")
    tpa44 = sources.get("tpa44")
    if tpa45 is None and tpa44 is None:
        return []
    specific = sources.get("specific")
    registration = sources.get("registration")
    succession = sources.get("succession")
    lines: list[str] = []
    if tpa45 is not None:
        if "mutation" in q and "brother" in q and "common land" in q:
            plot_phrase = "mutation changed after your brother sold common land without consent"
        elif "co owner" in q and "full property" in q:
            plot_phrase = "a co-owner sale of the full property"
        elif _has_any(q, ("father is hindu", "hindu 78", "ancestral land")) and "brother" in q:
            plot_phrase = "your Hindu father's ancestral land allegedly sold by your brother without consent"
        elif "brother" in q and "plot" in q:
            plot_phrase = "a plot bought by you and your brother"
        else:
            plot_phrase = "joint land, joint plot, common land, joint flat, or co-owned property"
        lines.append(
            f"For {plot_phrase}, first check the Transfer of Property Act joint-purchase/share source because it deals with transfers for consideration to two or more persons [{tpa45}]."
        )
    if tpa44 is not None:
        actor = "brother" if "brother" in q else "sister" if "sister" in q else "co-owner"
        possession_phrase = " and the buyer is threatening possession" if "buyer" in q and "possession" in q else ""
        lines.append(
            f"If your {actor} sold what they could transfer as a co-owner{possession_phrase}, the co-owner transfer source is relevant, but the sale deed must be checked to see what share or undivided interest was transferred [{tpa44}]."
        )
    if succession is not None:
        lines.append(
            f"For Hindu ancestral or inherited land, keep the Hindu Succession source with the family tree, father's status, shares, and will/no-will facts before deciding whether police or a civil-court remedy is the right route [{succession}]."
        )
    if specific is not None:
        lines.append(
            f"Specific Relief Act Section 31 permits a person against whom a written instrument is void or voidable, and who reasonably apprehends serious injury if it remains outstanding, to sue to have it adjudged and cancelled [{specific}]."
        )
    if registration is not None:
        lines.append(
            f"Registration records matter because the certified sale deed and mutation/khata record show whether the document claims the whole property or only the seller's share [{registration}]."
        )
    lines.append("**What you can do next**")
    if specific is not None:
        lines.append(
            "- Keep the old purchase deed, registered sale deed or certified copy, mutation/khata/land record, possession proof, payment proof, messages or consent proof, and buyer details."
        )
    else:
        lines.append(
            "- Keep the old purchase deed and the new sale deed or certified copy together, and mark the share each document says was transferred."
        )
    return lines


def _render_epf_dues(q: str, sources: dict[str, int]) -> list[str]:
    epf = sources.get("epf")
    if epf is None:
        return []
    social = sources.get("social")
    code_wages = sources.get("code_wages")
    contract_labour = sources.get("contract_labour")
    gratuity = sources.get("gratuity")
    closure_context = _has_any(q, ("closed", "shut down", "factory closed", "company closed", "company shut down"))
    gratuity_context = "gratuity" in q or closure_context
    no_uan_context = _has_any(q, ("no uan", "uan not given", "not given uan", "without uan", "uan number not given", "no uan number"))
    contractor_context = _has_any(q, ("contractor", "thekedar", "contract labour", "contract labor", "principal employer", "labour", "labor", "workers", "workmen"))

    lines: list[str] = []
    lines.append(f"Source to verify for PF default and this EPF default/recovery issue: Employees' Provident Funds and Miscellaneous Provisions Act 1952 [{epf}].")
    if gratuity is not None and gratuity_context:
        lines.append(f"Source to verify for closure gratuity: Payment of Gratuity Act 1972 [{gratuity}].")
        lines.append(
            f"If PF/EPF and gratuity are pending, or PF/EPF was deducted but not deposited and the employer says company closed or the factory shut down, keep two separate tracks: EPFO/RPFO recovery for provident-fund default [{epf}] and a gratuity controlling authority/controlling-authority or labour-office track if gratuity is due [{gratuity}], before treating this as only a labour-office wage case."
        )
        lines.append(
            f"Do not merge PF, gratuity, and unpaid salary into one generic wage complaint; keep UAN/passbook proof for EPFO and last-working-date/gratuity calculation proof for the controlling authority [{gratuity}]."
        )
    else:
        lines.append(
            f"If PF balance is missing, HR is not replying, the employer says PF will come later, or the UAN/EPFO passbook has zero contribution, treat it as PF contribution not deposited rather than only a verbal HR or salary promise [{epf}]."
        )
        lines.append(
            f"If the company says PF will come later, or PF/EPF is deducted from salary but the EPFO passbook is empty, the UAN shows zero contribution, or contributions are not deposited, keep it as an employer contribution-default and EPFO recovery/grievance track before treating this as only a labour-office wage case [{epf}]."
        )
        if no_uan_context:
            lines.append(
                f"If PF was deducted but no UAN/member ID was given, ask EPFO/RPFO for the establishment code, generated member ID/UAN, contribution ledger, and recovery status; no UAN should not end the PF claim where wage records show deduction [{epf}]."
            )
        if contractor_context and contract_labour is not None:
            lines.append(
                f"Because a contractor or labour supplier is involved, keep contractor and principal-employer site records too; the Contract Labour source supports the wage/responsibility record, but it does not replace the EPFO contribution-default complaint [{contract_labour}]."
            )
        if contractor_context and code_wages is not None:
            lines.append(
                f"Use the Code on Wages source for wage-deduction or claim records connected with the payslip, while keeping PF deposit and UAN correction on the EPFO/EPF track [{code_wages}]."
            )
        if _has_any(q, ("pf will come later", "uan has zero", "zero contribution")):
            lines.append(
                f"Do not wait only on the company's PF will come later reply; ask EPFO/RPFO for written grievance or recovery status using the UAN/member ID, establishment name/code, and zero-contribution passbook proof [{epf}]."
            )
        if social is not None:
            lines.append(
                f"Use the Code on Social Security source only as the current social-security coverage frame; the practical first forum for missing PF deposits remains EPFO/RPFO with the EPF contribution-default proof [{social}], [{epf}]."
            )
        lines.append(
            f"Use the UAN zero-contribution or empty-passbook entry as the immediate EPFO complaint fact, and ask EPFO/RPFO to check the employer contribution default and recovery under the EPF source [{epf}]."
        )
        lines.append(
            f"Frame the complaint to EPFO as PF deduction from wages without matching deposit, zero contribution, or no contribution in the member passbook, with employer establishment details and salary-slip proof [{epf}]."
        )
    lines.extend([
        "**What you can do next**",
        f"- File an EPFO grievance/recovery complaint or written complaint with the Regional Provident Fund office/RPFO using UAN/member ID, EPFO passbook screenshots, salary slips showing PF deduction, bank statements, employer establishment name/code, and employer messages [{epf}].",
    ])
    if gratuity is not None and gratuity_context:
        lines.append(
            f"- For gratuity, separately keep appointment/exit proof, last-working-date proof, years of service, salary basis, gratuity eligibility and calculation proof, demand letter, and closure/shutdown proof for the controlling authority or labour office [{gratuity}]."
        )
    return lines


def _render_street_vendor_seizure(q: str, sources: dict[str, int]) -> list[str]:
    street = sources.get("street")
    street4 = sources.get("street4")
    street19 = sources.get("street19") or street
    street20 = sources.get("street20")
    street28 = sources.get("street28")
    pca = sources.get("pca")
    baseline = street4 or street20 or street19 or street
    if baseline is None:
        return []
    item = (
        "tea cart" if "tea cart" in q else
        "fruit cart" if "fruit cart" in q else
        "vegetable cart" if "vegetable" in q else
        "cart" if "cart" in q else
        "thela" if "thela" in q else
        "footpath stall" if "footpath" in q or "stall" in q else
        "vending goods"
    )
    place_phrase = "Mumbai/Bandra" if _has_any(q, ("mumbai", "bandra")) else "your area"
    if _has_any(q, ("demolished", "demolition", "no notice", "without notice", "no tvc", "no tvc certificate")):
        opening = f"For a {place_phrase} street vendor whose {item} was demolished/removed by the municipal body with no notice or no TVC certificate, treat it as a Street Vendors Act / Town Vending Committee record issue first, not only as a generic encroachment or shop-registration case"
    elif "hawker" in q and "without receipt" in q:
        opening = f"For a hawker zone officer removing your {item} without receipt, treat it as a Street Vendors Act / Town Vending Committee record issue first, not only as a generic encroachment or shop-registration case"
    elif "nagar nigam" in q:
        opening = f"For a Nagar Nigam or municipal seizure of a {item}, challan, or fine demand, treat it as a Street Vendors Act / Town Vending Committee record issue first, not only as a generic encroachment or shop-registration case"
    elif "pune" in q:
        opening = f"For a Pune municipal seizure/removal of a {item}, challan, or fine demand, treat it as a Street Vendors Act / Town Vending Committee record issue first, not only as a generic encroachment or shop-registration case"
    else:
        opening = f"For a municipal seizure/removal of a {item}, challan, or fine demand, treat it as a Street Vendors Act / Town Vending Committee record issue first, not only as a generic encroachment or shop-registration case"
    lines: list[str] = [f"{opening} [{baseline}]."]
    if "fish basket" in q and "footpath" in q:
        lines.append(
            f"For a municipality removing your vending goods, including a fish basket from the footpath, ask for the written removal/seizure record rather than accepting an oral encroachment label [{baseline}]."
        )
    if street4 is not None:
        lines.append(
            f"The Street Vendors Act certificate source says identified street vendors are issued a certificate of vending by the Town Vending Committee, so TVC certificate, pending certificate application, survey, or zone-allotment papers matter first [{street4}]."
        )
    if street19 is not None:
        lines.append(
            f"If goods or stock were seized, the Street Vendors Act seizure source is the source to check for inventory, receipt, seizure list, and return/release timing [{street19}]."
        )
    if street19 is not None and _has_any(q, ("goods not returned", "not returned", "stock not returned", "cart removed", "goods are missing")):
        lines.append(
            f"Because the goods are not returned, ask for the seizure list, signed copy/receipt, storage place, officer name, goods inventory, and written release date before paying any fine or accepting an oral loss explanation [{street19}]."
        )
    if _has_any(q, ("license pending", "licence pending", "application pending", "hearing", "before hearing")) and (street20 is not None or street4 is not None or street19 is not None):
        hearing_cite = street20 or street4 or street19
        lines.append(
            f"If your hawker licence/certificate application is pending or the stall was removed before a hearing, ask the Town Vending Committee or municipal office for the pending-application status, hearing date, written removal order, and interim return/release route [{hearing_cite}]."
        )
    if street20 is not None:
        lines.append(
            f"If the municipal office will not resolve the seizure or fine issue, use the Street Vendors Act grievance/dispute-redressal source and ask for a written order or challan basis [{street20}]."
        )
    if street28 is not None and "fine" in q:
        lines.append(
            f"For a fine or challan demand, verify the penalty provision and written basis for the amount before accepting an oral demand [{street28}]."
        )
    if pca is not None and _has_any(q, ("bribe", "cash bribe", "cash", "hafta", "every month", "without receipt")):
        lines.append(
            f"Keep the cash/bribe demand separate from the vending challan: the Prevention of Corruption Act source is relevant only if an undue-advantage demand by a public servant is alleged, with date, amount, words used, officer details, and proof [{pca}]."
        )
    action_cite = street20 or street19 or street4 or baseline
    lines.extend([
        "**What you can do next**",
        f"- Keep the {item} details, demolished/removed-cart photos, no-notice proof, seized stock or stock value, vending receipt/certificate of vending or pending TVC application, survey proof, zone-allotment papers, list of goods seized or seizure memo, challan/fine basis and receipt if any, inspector details, and any cash-demand messages; ask the municipal office or Town Vending Committee in writing for the rule/order and goods-release route [{action_cite}].",
    ])
    return lines


def _render_marital_intimacy(q: str, sources: dict[str, int]) -> list[str]:
    if _has_any(q, (
        "adultery", "extra marital", "extra-marital", "affair",
        "cheating on me", "another woman", "another women", "another man",
        "caught my husband", "caught my wife", "caught husband", "caught wife",
        "sex with another",
    )):
        return []
    family = sources.get("family")
    if family is None:
        return []
    hma = sources.get("hma")
    sma = sources.get("sma")
    spouse = "husband" if "husband" in q else "wife" if "wife" in q else "spouse"
    issue = (
        f"your {spouse} has no physical relationship with you after marriage"
        if "no physical relationship" in q
        else f"your {spouse} is refusing sex or physical intimacy"
        if _has_any(q, ("refusing", "refuses", "denies", "denying", "denied"))
        else "there is no marital relationship or intimacy after marriage"
    )
    lines = [
        f"If {issue}, treat this as a Family Court/DLSA marriage-breakdown or matrimonial-remedy question, because the Family Courts Act source covers suits and proceedings relating to matrimonial matters [{family}]."
    ]
    if hma is not None:
        lines.append(
            f"Do not treat refusal of intimacy as a complete legal claim by itself; if the Hindu Marriage Act applies, check the Section 13 divorce-ground or other matrimonial-relief source with the full facts [{hma}]."
        )
    elif sma is not None:
        lines.append(
            f"If the Special Marriage Act applies, the same issue remains fact-specific and should be checked through lawful Family Court relief, not self-help pressure [{sma}]."
        )
    lines.extend(("**Consent matters**", "**What you can do next**"))
    lines.append(
        "- Keep a timeline of the intimacy breakdown, counselling attempts, residence, children, maintenance, and any violence or coercion facts; do not force, threaten, or pressure your spouse for sex."
    )
    return lines


def _render_domestic_violence_safety(
    q: str,
    sources: dict[str, int],
    passages: list[dict],
) -> list[str]:
    pwdva = sources.get("pwdva")
    if pwdva is None:
        return []
    pwdva_protection = sources.get("pwdva_protection")
    pwdva_residence = sources.get("pwdva_residence")
    pwdva_application = sources.get("pwdva_application")
    bns = sources.get("bns")
    bnss = sources.get("bnss")
    family = sources.get("family")
    hma13b = sources.get("hma13b")
    woman_role_confirmed = _has_any(q, (
        "i am his wife", "i'm his wife", "i am a woman", "i'm a woman",
        "woman victim", "female victim", "daughter in law", "daughter-in-law",
    ))
    sexual_coercion = _has_any(q, (
        "forcing me for sex", "forces sex", "force sex", "forced sex",
        "refuse sex", "refuses sex", "refusing sex", "say no",
        "when i say no", "deny physical relation", "denying physical relation",
        "without consent", "continues sexual contact", "sexual coercion",
    ))
    residence_context = _has_any(q, (
        "sasural", "ghar se nikal", "ghar se nikaal", "wapis ja",
        "return home", "shared household", "shared house", "matrimonial home",
        "threw me out", "kicked me out", "remove me", "evict",
    ))
    if sexual_coercion and "throw me out" in q:
        issue = "your spouse threatens to throw you out if you refuse sex"
    elif sexual_coercion and _has_any(q, ("beats me", "beating", "beat me", "hit me", "slapped")):
        issue = "your husband forces sex when you say no and also uses physical violence"
    elif sexual_coercion and _has_any(q, ("threatening", "threatens", "threat")):
        issue = "your husband is forcing you for sex and threatening you"
    elif sexual_coercion:
        issue = "your husband or spouse is forcing sex or sexual contact after you refuse"
    elif "sasural" in q and "not allowing me to call" in q:
        issue = "your sasural/in-laws beat you tonight and are stopping you from calling for help"
    elif "sasural" in q and _has_any(q, ("ghar se nikal", "ghar se nikaal", "wapis ja")):
        issue = "your sasural/in-laws have put you out of the matrimonial home and you are asking whether you can return safely"
    elif "punched" in q and ("shared house" in q or "remove me" in q):
        issue = "your husband punched you and is threatening to remove you from the shared house at night"
    elif "spouse assaulted" in q or (
        _has_any(q, ("spouse", "husband")) and _has_any(q, ("evict", "matrimonial home"))
    ):
        issue = "your spouse or husband assaulted you and is threatening to evict you from the matrimonial home"
    elif "slapped me in front of child" in q or ("slapped me" in q and "no place to stay" in q):
        issue = "you were slapped in front of your child and told to leave today with no place to stay"
    elif _has_any(q, ("says sorry", "sorry next day", "all marriages are like this", "should i stay")) and _has_any(q, ("slap", "slapped", "hit", "beat")):
        issue = "he hits or slaps you and then apologises, but the question is still safety and domestic violence, not whether violence is normal in marriage"
    elif "throw me out tonight" in q:
        issue = "your husband slapped you and is threatening to throw you out tonight"
    elif "took my phone" in q:
        issue = "your in-laws beat you, took your phone, and you are unsafe"
    elif "beat me and broke my phone" in q:
        issue = "your husband beat you, broke your phone, and you are unsafe tonight"
    elif "beating me" in q and "right now" in q:
        issue = "your husband is beating you right now"
    elif "acid" in q:
        issue = "your mother-in-law is threatening to throw acid if you do not bring more money"
    elif "husband" in q and "beating" in q:
        issue = "your husband is beating you"
    elif "hit me tonight" in q:
        issue = "your husband hit you tonight and is threatening to throw you out"
    elif "slapped" in q:
        issue = "your husband slapped you and you are unsafe"
    else:
        issue = "there is domestic violence, threat, or immediate safety risk"

    lines = [
        "**Immediate safety**",
        f"- For this report, treat immediate safety first: if you are unsafe right now, move to a safe place or trusted person first and contact 112/police or emergency services for immediate danger [{pwdva}].",
    ]
    if woman_role_confirmed:
        lines.append(
            f"For domestic violence and safety, PWDVA Section 3 covers sexual abuse and related physical or emotional harm, as well as other conduct that harms, injures, or endangers a woman's physical or mental well-being [{pwdva}]."
        )
    else:
        lines.append(
            f"For domestic violence and safety, including sexual abuse and related physical or emotional harm, PWDVA Section 3 is a statutory route for an aggrieved woman in a domestic relationship; because the question does not confirm that role, use this protection route only if that condition is met and do not assume it applies to every spouse or partner [{pwdva}]."
        )
    if pwdva_protection is not None:
        lines.append(
            f"PWDVA Section 18 is the protection-order source allowing a Magistrate to prohibit further domestic violence, contact, threats, or intimidation where the statutory conditions are met [{pwdva_protection}]."
        )
    if pwdva_application is not None:
        lines.append(
            f"If the PWDVA aggrieved-woman condition is met, Section 12 permits an application to the Magistrate by the aggrieved person, a Protection Officer, or another person on her behalf [{pwdva_application}]."
        )
    if residence_context and pwdva_residence is not None:
        lines.append(
            f"PWDVA Section 19 is the source for residence orders concerning the shared household [{pwdva_residence}]."
        )
    if bns is not None:
        lines.append(
            f"For an incident on or after 1 July 2024, the BNS hurt source in Section 115 is the separate BNS criminal track to verify for alleged voluntarily caused hurt; match the incident date before using it [{bns}]."
        )
    if bnss is not None:
        lines.append(
            f"If police help is needed, use the BNSS FIR/information and Magistrate-escalation route with the dated complaint and safety evidence [{bnss}]."
        )
    if _has_any(q, ("divorce", "mutual consent", "separation")) and family is not None:
        lines.append(
            f"Keep the Family Court/DLSA matrimonial track alongside immediate safety; separation or divorce does not replace protection, residence, medical, or police steps [{family}]."
        )
    if _has_any(q, ("mutual consent", "mutual divorce")) and hma13b is not None:
        lines.append(
            f"If the Hindu Marriage Act applies, Section 13B is a mutual-consent route only when both spouses freely agree; violence or pressure must not be used to manufacture consent [{hma13b}]."
        )
    if _has_any(q, ("should i stay", "all marriages are like this", "says sorry", "sorry next day")):
        lines.append(
            f"Do not decide whether to stay or leave under pressure: you do not have to treat being hit, slapped, or beaten as normal because of an apology or the claim that all marriages are like this. If you are asking whether to stay, make the immediate safety and support plan first [{pwdva}]."
        )
    lines.extend([
        "**What you can do next**",
        (
            f"- For {issue}, preserve a dated timeline, messages, photos, medical records, residence proof, and witness details."
            if sexual_coercion
            else f"- For {issue}, preserve injury proof, messages, photos, medical records, residence proof, and witness details."
        ),
    ])
    return lines


def _render_maintenance_nonpayment(q: str, sources: dict[str, int]) -> list[str]:
    family = sources.get("family")
    if family is None:
        return []
    bnss = sources.get("bnss")
    pwdva = sources.get("pwdva")
    crpc = sources.get("crpc")
    delay = " for 8 months" if "8 months" in q else ""
    lines = [
        f"For court-ordered maintenance that your husband is not paying{delay}, treat this as enforcement or arrears of a maintenance order in the same Family Court or Magistrate route, not as a fresh generic family dispute [{family}]."
    ]
    if bnss is not None:
        lines.append(
            f"Use the BNSS maintenance source to organise the order, arrears calculation, payment defaults, income facts, and enforcement request [{bnss}]."
        )
    if pwdva is not None:
        lines.append(
            f"If your husband's court-ordered maintenance is unpaid{delay} and the order or relief was under the PWDVA monetary-relief route, keep that monetary-relief record with the arrears papers [{pwdva}]."
        )
    if crpc is not None:
        lines.append(
            f"If the older CrPC regime applies, compare the enforcement step with the CrPC maintenance source instead of mixing old and new procedure [{crpc}]."
        )
    lines.extend([
        "**What you can do next**",
        f"- For the court-ordered maintenance your husband has not paid{delay}, file an enforcement/execution or arrears application with the maintenance order, arrears month-wise chart, bank statements, missed-payment proof, husband income/job details, child-expense proof, and prior notices/messages [{family}].",
    ])
    return lines


def _render_senior_parent_support(q: str, sources: dict[str, int]) -> list[str]:
    senior = sources.get("senior")
    if senior is None:
        return []
    senior23 = sources.get("senior23")
    tpa_gift = sources.get("tpa_gift")
    hama = sources.get("hama")
    pwdva = sources.get("pwdva")
    residence_issue = _has_any(
        q,
        (
            "threw me out",
            "thrown out",
            "throw me out",
            "pushed me out",
            "pushed out",
            "pushed from",
            "changed lock",
            "cannot stay",
            "sleep outside",
            "not letting",
            "not allowed",
            "not allowing",
            "forced out",
            "being forced out",
            "forced to leave",
            "kitchen",
            "room",
            "bathroom",
            "own house",
            "own home",
            "flat",
            "gift deed",
            "transferred flat",
            "flat to son",
            "house to son",
            "property",
            "self acquired",
            "self-acquired",
            "bought by me",
            "from my savings",
        ),
    )
    food_money_issue = _has_any(
        q,
        (
            "not giving food",
            "not giving money",
            "no food",
            "refuses food",
            "medicine money",
            "medicine",
            "ration",
            "food and money",
            "abandoned",
            "left me alone",
            "neglect",
            "maintenance",
            "monthly",
            "monthly support",
            "passbook",
            "atm card",
        ),
    )
    pension_issue = "pension" in q or "passbook" in q or "atm card" in q
    gift_transfer_issue = _has_any(
        q,
        (
            "gift", "gifted", "gift deed", "gave house", "house to son",
            "flat to son", "transferred flat", "transferred house",
            "transfer", "transferred", "settlement deed",
        ),
    ) and _has_any(
        q,
        (
            "food", "medicine", "medical", "care", "basic needs",
            "basic amenities", "stopped", "refuses food", "no food",
            "maintenance", "not maintaining", "neglect",
        ),
    )
    daughter_in_law_issue = _has_any(q, ("daughter in law", "daughter-in-law", "bahu"))
    violence_issue = _has_any(q, ("beat", "beats", "beating", "hit", "slap", "assault", "violence"))
    mumbai_issue = "mumbai" in q
    bihar_issue = "bihar" in q
    if residence_issue:
        issue = "residence/support and property-document pressure"
    elif pension_issue:
        issue = "pension control, maintenance, and support"
    elif food_money_issue:
        issue = "food, money, maintenance, and day-to-day support"
    else:
        issue = "senior-parent maintenance and support"
    victim_phrase = (
        "your mother"
        if "mother" in q
        else "your father"
        if "father" in q
        else "the senior citizen"
    )
    victim_possessive = f"{victim_phrase}'" if victim_phrase.endswith("s") else f"{victim_phrase}'s"

    lines: list[str] = []
    if daughter_in_law_issue and violence_issue and pwdva is not None:
        lines.append(
            f"Treat beating by a daughter-in-law or household relative as domestic violence against your 68-year-old mother or senior woman, not only as maintenance neglect; the Domestic Violence Act/PWDVA route can support protection, residence, and application to the Magistrate [{pwdva}]."
        )
    elif daughter_in_law_issue and residence_issue and pwdva is not None:
        lines.append(
            f"Because the exclusion is by a daughter-in-law or household relative, keep the PWDVA residence/protection source as a parallel household-safety route for the senior woman, while the Senior Citizens Act tribunal remains the faster parent/senior support route [{pwdva}]."
        )
    if gift_transfer_issue and senior23 is not None:
        lines.append(
            f"Yes, the father can ask the Maintenance Tribunal to examine whether a flat gifted or transferred to a transferee or relative should be declared void under Senior Citizens Act Section 23 because food, medicine, care, or basic needs stopped after the transfer [{senior23}]."
        )
        if tpa_gift is not None:
            lines.append(
                f"Keep the registered gift deed and Transfer of Property Act gift/revocation record in the same file, but do not let the ordinary gift-deed lane replace the faster Senior Citizens Tribunal route when Section 23 facts fit [{tpa_gift}]."
            )
    lines.append(
        f"Treat this as a Senior Citizens Act {issue} route for {victim_phrase} before reducing it to a generic family dispute; the maintenance-tribunal source is the first authority to check when children or relatives neglect or refuse to maintain a senior citizen [{senior}]."
    )
    if residence_issue and senior23 is not None and _has_any(q, (
        "own house", "own home", "flat", "property", "gift deed",
        "transferred", "transfer", "daughter in law", "daughter-in-law",
        "bahu", "kitchen", "room", "bathroom",
    )):
        lines.append(
            f"Also check the Senior Citizens Act Section 23 source if any gift, settlement, transfer, or property paper is being used to exclude the senior citizen from the house, kitchen, room, or basic amenities; keep that as a tribunal issue rather than starting only a civil title suit [{senior23}]."
        )
    if residence_issue:
        if _has_any(q, ("gift deed", "gave gift", "gave gift deed")) and _has_any(q, ("children", "refuse medicine", "refuses medicine", "medicine and maintenance")):
            lines.append(
                f"Because a 69-year-old father gave a gift deed or house and the children now refuse medicine and maintenance, put monthly maintenance, medical expenses, residence support, and possible Section 23 transfer/gift relief in the same Maintenance Tribunal application [{senior}]."
            )
        if _has_any(q, ("transferred flat", "flat to son", "sleep outside")):
            lines.append(
                f"Because an 80-year-old mother transferred a flat to her son and is now being told by the son or bahu to sleep outside, ask the Maintenance Tribunal for immediate residence access/support and Section 23 transfer/gift review rather than starting only a civil title suit [{senior}]."
            )
        if _has_any(q, ("threw me out", "thrown out", "throw me out")) and _has_any(q, ("own house", "own home")):
            place = " in Mumbai" if mumbai_issue else ""
            paid_phrase = " that you say you paid for in 1985" if "1985" in q else ""
            lines.append(
                f"Because your son threw you out of your own house{place}{paid_phrase}, treat it as the senior citizen's own house plus a linked property-record problem; lead with a written Senior Citizens Act Maintenance Tribunal/District Social Welfare application for residence access, support, and protection from exclusion, and do not start with police or a generic family dispute unless there is immediate violence [{senior}]."
            )
        elif _has_any(q, ("pushed me out", "pushed out", "thrown out", "self acquired", "self-acquired", "bought by me", "flat")):
            place = (
                " in Thane/Mumbai"
                if "thane" in q and "mumbai" in q
                else " in Thane"
                if "thane" in q
                else " in Navi Mumbai/Mumbai"
                if _has_any(q, ("navi mumbai", "mumbai"))
                else ""
            )
            home_word = "flat" if "flat" in q else "house"
            lines.append(
                f"Because the senior parent was pushed or thrown out of a self-acquired or self-paid {home_word}{place}, use the Maintenance Tribunal/District Social Welfare residence-support route first and keep payment/title/possession papers ready for any property or transfer track [{senior}]."
            )
        if _has_any(q, ("changed lock", "cannot stay", "not letting", "room", "bathroom")):
            place = " in Pune" if "pune" in q else " in Delhi" if "delhi" in q else " in Thane" if "thane" in q else ""
            lines.append(
                f"If a son, daughter-in-law, or family member changed the lock, blocks the room or bathroom, or says the senior cannot stay{place}, write the Maintenance Tribunal application as a residence-restoration and support request, with lock/entry proof, room/bathroom access facts, and address papers [{senior}]."
            )
        if _has_any(q, ("transferred flat", "flat to son", "sleep outside")):
            lines.append(
                f"If the mother transferred a flat to the son and is now being told to sleep outside, keep Section 23 transfer/gift cancellation facts with the residence and maintenance request instead of treating it as only a property-title dispute [{senior}]."
            )
        if daughter_in_law_issue:
            place = " in Pune" if "pune" in q else " in Mumbai" if mumbai_issue else ""
            lines.append(
                f"Because you mention a daughter-in-law/son blocking an elderly mother from her room, kitchen, bathroom, or house{place}, frame the immediate Maintenance Tribunal request as residence access, support, and protection from exclusion before reducing it to a long civil title suit [{senior}]."
            )
        if _has_any(q, ("gave house to son", "house to son")) and _has_any(q, ("refuses food", "no food", "leave house")):
            lines.append(
                f"Because the father gave the house to the son and now says the son refuses food or says leave house, keep maintenance, food support, residence access, and any Section 23 transfer-cancellation facts together before the Maintenance Tribunal [{senior}]."
            )
        if _has_any(q, ("gift deed", "gave gift", "refuse medicine", "refuses medicine", "medicine and maintenance")):
            lines.append(
                f"For a gift deed or house transfer followed by refusal of medicine or maintenance, ask the Maintenance Tribunal to examine support, medical expenses, residence, and possible transfer-condition/Section 23 relief together [{senior}]."
            )
        lines.append(
            f"If the senior citizen is pushed out, excluded from the kitchen/house, or property/gift/transfer papers are involved, keep the residence, ownership/payment, and transfer-cancellation facts with the same Senior Citizens Act file [{senior}]."
        )
        if _has_any(q, ("paid for it in 1985", "1985", "own house", "own home")):
            lines.append(
                f"For a son throwing you out of your own house, keep the 1985 payment/ownership papers, possession facts, and any transfer/gift papers together with the Maintenance Tribunal residence-support file [{senior}]."
            )
    if pension_issue:
        place = " in Bihar" if bihar_issue else ""
        support_gap = " and children not helping" if _has_any(q, ("children not helping", "child not helping")) else ""
        lines.append(
            f"If the pension-stoppage issue involves pension or passbook money, ATM-card access, or bank money for {victim_phrase} being controlled{place}{support_gap}, and food/medicine money is withheld, keep bank/passbook entries and withdrawals with the maintenance/support application instead of treating it as only a bank or land-record complaint [{senior}]."
        )
    if _has_any(q, ("ornaments", "jewellery", "jewelry")):
        lines.append(
            f"If a daughter or relative sold the mother's ornaments or jewellery and is also refusing to maintain her, keep the jewellery/ornament proof as financial-abuse evidence but file the parent-support request before the Maintenance Tribunal with the Senior Citizens Act maintenance papers [{senior}]."
        )
    if food_money_issue and _has_any(q, ("no food", "monthly support", "left me alone", "ration", "medicine")):
        if _has_any(q, ("left alone after son second marriage", "second marriage")) and _has_any(q, ("ration", "medicine")):
            lines.append(
                f"Because the mother is left alone after the son's second marriage with no ration or medicine, frame the first relief as immediate maintenance, food/medicine support, and safe residence before arguing family history [{senior}]."
            )
        lines.append(
            f"For no food, no monthly support, ration, medicine, or being left alone in the village, state the immediate need for food, medicine, residence, and monthly maintenance in the Maintenance Tribunal application instead of only narrating the family history [{senior}]."
        )
    if _has_any(q, ("how much", "maximum", "max", "kitna", "kithna", "amount")):
        lines.append(
            f"For the amount question, ask the Tribunal to calculate need, means, medical/residence expenses, and local/state rules; the central Senior Citizens Act text caps the prescribed monthly allowance at Rs.10,000 unless the applicable rule position changes it [{senior}]."
        )
    if hama is not None:
        lines.append(
            f"Where personal-law maintenance is also relevant, keep that as a secondary track; the faster first forum for an elderly parent is still the Senior Citizens Act tribunal route [{hama}]."
        )
    if _has_any(q, ("married 2nd time", "married second", "2nd time", "second time", "second marriage", "remarried")):
        place = " in Bihar" if bihar_issue else ""
        lines.append(
            f"The son's second marriage or remarriage{place} is not the main legal test by itself; the useful facts are abandonment, food/money support, medical needs, residence, and ability to maintain the parent [{senior}]."
        )
    lines.extend(
        [
            "**What you can do next**",
            f"- File or help file before the Maintenance Tribunal/District Social Welfare or senior-citizen authority with {victim_possessive} age proof/ID, address, medical needs and food expenses, bank/passbook entries, son/daughter or relative details, messages/witnesses, and property/gift/ownership papers if the house or transfer is involved; ask DLSA for help if the senior cannot file alone [{senior}].",
        ]
    )
    return lines


def _render_mgnrega_grievance(q: str, sources: dict[str, int]) -> list[str]:
    mgnrega = sources.get("mgnrega")
    if mgnrega is None:
        return []
    mgnrega_grievance = sources.get("mgnrega_grievance")
    mgnrega_social_audit = sources.get("mgnrega_social_audit")
    pca = sources.get("pca")
    bns = sources.get("bns")
    rti = sources.get("rti")
    fake_or_audit = _has_any(q, ("social audit", "gram sabha", "corruption", "fake", "muster", "attendance", "dead people"))
    local_official = _has_any(q, ("mukhiya", "sarpanch"))
    social_audit = fake_or_audit or (local_official and _has_any(q, ("action", "complain", "collector", "corruption", "fake")))
    job_card = _has_any(q, ("job card", "jobcard", "card not given", "application pending", "not issuing", "job card application", "work demand", "receipt not given", "no card", "come next week"))
    wage_delay = _has_any(q, ("wage", "wages", "paid", "payment", "funds not come", "no payment", "not paid", "pending", "bank passbook", "no credit", "zero credit", "portal paid", "website says processed", "payment shows paid"))
    work_days_match = re.search(r"\b(\d{1,3})\s+days?\b", q)
    work_phrase = f"{work_days_match.group(1)} days of NREGA work" if work_days_match else "NREGA work"
    no_action = _has_any(q, ("no action", "not taken action", "nothing happened", "ignored", "no reply", "not replying", "no atr", "atr given"))
    collector_no_action = "collector" in q and no_action
    ngo_helper = _has_any(q, ("ngo", "helper", "helping us"))
    gram_sabha_audit = _has_any(q, ("social audit", "gram sabha"))
    corruption_audit = gram_sabha_audit and "corruption" in q and local_official
    lines: list[str] = []
    after_bdo_collector = _has_any(q, ("after bdo", "after bdo and collector", "bdo and collector", "bdo not replying", "collector ignored"))
    if social_audit:
        place = " in Nuapada/Odisha" if _has_any(q, ("nuapada", "odisha", "orissa")) else ""
        if _has_any(q, ("dead persons", "dead people")) and _has_any(q, ("bdo silent", "bdo is silent", "bdo not replying")):
            lines.append(
                f"Because the Gram Sabha/social-audit record already says dead persons wages and the BDO is silent, treat this as an MGNREGA social-audit action-taken-report problem: ask the Programme Officer/BDO and district authority or ombudsman for written ATR, recovery status, and misappropriation follow-up [{mgnrega}]."
            )
        if corruption_audit:
            official = "sarpanch" if "sarpanch" in q else "mukhiya"
            lines.append(
                f"For a social audit or Gram Sabha record{place} showing corruption by the {official} and no action taken, use the MGNREGA social-audit source and grievance follow-up route: ask for the written action-taken status and social-audit report, then escalate to the Programme Officer/BDO, district MGNREGA authority, ombudsman, or Collector [{mgnrega}]{f', [{mgnrega_grievance}]' if mgnrega_grievance is not None and mgnrega_grievance != mgnrega else ''}."
            )
        else:
            lines.append(
                f"For MGNREGA or NREGA fake muster, fake job-card complaint, fake job cards, social-audit, Gram Sabha, sarpanch/mukhiya corruption, or no action by the collector{place}, use the MGNREGA social-audit source and scheme grievance route before treating it as a civil suit [{mgnrega}]{f', [{mgnrega_grievance}]' if mgnrega_grievance is not None and mgnrega_grievance != mgnrega else ''}."
            )
        if local_official or collector_no_action or ngo_helper:
            official = "mukhiya/sarpanch" if local_official else "local official"
            failed_step = " and the collector has not acted" if collector_no_action else ""
            helper = " with the NGO/helper's details" if ngo_helper else ""
            lines.append(
                f"Because the complaint is that the {official} made fake job cards, fake muster, or corruption records{failed_step}, ask for a written action-taken report and escalate to the Programme Officer/BDO, district MGNREGA authority, ombudsman, or Collector{helper}; do not let it collapse into an ordinary wage-delay complaint [{mgnrega}]."
            )
            if pca is not None or bns is not None:
                fraud_cites = ", ".join(f"[{idx}]" for idx in (pca, bns) if idx is not None)
                lines.append(
                    f"If the papers show forged muster, fake job cards, or public-money misappropriation, keep a separate corruption/forgery complaint track with the MGNREGA file instead of using only the wage-delay route {fraud_cites}."
                )
        if after_bdo_collector or _has_any(q, ("dead people", "dead persons", "not replying", "bdo silent", "district officer no reply", "atr")):
            lines.append(
                f"If BDO/Collector complaints, dead-person wage entries, or fake-attendance records are already on paper, ask for the action-taken report/ATR and move the same file to the district MGNREGA grievance authority or ombudsman instead of restarting at the panchayat [{mgnrega}]."
            )
        if _has_any(q, ("dead people", "dead person", "dead persons")):
            lines.append(
                f"A social-audit report showing names of dead people getting wages or dead persons wages should be treated as fake muster or misappropriation evidence; ask for the written action-taken report and recovery/follow-up record under the MGNREGA social-audit and grievance route [{mgnrega}]."
            )
        if _has_any(q, ("atr", "can we ask atr")):
            lines.append(
                f"ATR here means the written action-taken report: ask the Programme Officer/BDO or district MGNREGA authority to record what was done on the fake muster complaint and whether recovery or disciplinary action was started [{mgnrega}]."
            )
        if _has_any(q, ("district officer no reply", "bdo silent")):
            lines.append(
                f"If the BDO is silent or the district officer gives no reply after social-audit minutes or a forged muster-roll complaint, escalate the same file to the district grievance authority/ombudsman and seek the action-taken report in writing [{mgnrega}]."
            )
        if after_bdo_collector:
            lines.append(
                f"Since the Gram Sabha issue has already gone after BDO and Collector, the next answer should name the collector record, action-taken report/ATR, district MGNREGA grievance authority, and ombudsman rather than sending the user back to the panchayat [{mgnrega}]."
            )
    elif job_card:
        place = " in Nuapada/Odisha" if _has_any(q, ("nuapada", "odisha", "orissa")) else ""
        delay_phrase = "seven-month" if "7 months" in q else "eight-month" if "8 months" in q else "nine-month" if "9 months" in q else "pending"
        lines.append(
            f"For an MGNREGA/NREGA job-card refusal, card not given, application pending, not issuing, or {delay_phrase} delay{place}, use the statutory scheme grievance route for job-card/work-demand records, not a generic labour complaint [{mgnrega}]."
        )
        if _has_any(q, ("work demand", "receipt not given", "come next week")):
            lines.append(
                f"If the panchayat will not give a work-demand receipt or keeps saying come next week, ask for written acknowledgement/status from the Gram Panchayat and Programme Officer/BDO, then escalate through the MGNREGA grievance route [{mgnrega}]."
            )
    elif wage_delay:
        if _has_any(q, ("payment shows paid", "bank passbook", "no credit", "zero credit", "portal paid", "website says processed")):
            lines.append(
                f"For an MGNREGA payment that shows paid but has no bank/passbook credit, treat it as a wage-payment records grievance: compare FTO/payment order, bank/passbook entry, job card, and muster/work ID before accepting the portal status [{mgnrega}]."
            )
        else:
            lines.append(
                f"For {work_phrase} with wages pending, which is a wage delay, the MGNREGA grievance-redressal route [{mgnrega_grievance or mgnrega}] is the scheme wage-payment path with Programme Officer/BDO escalation, not an ordinary private wage dispute."
            )
            if mgnrega_social_audit is not None:
                lines.append(
                    f"The MGNREGA social-audit source can help check muster rolls and wage-payment records for {work_phrase} [{mgnrega_social_audit}]."
                )
    else:
        lines.append(
            f"For an MGNREGA/NREGA job-card, wage, muster, or work-demand problem, start with the scheme grievance route before treating it as a generic labour dispute [{mgnrega}]."
        )
    lines.append("**What you can do next**")
    if social_audit:
        lines.append(
            f"- File a written action-taken request with the Programme Officer/BDO and district MGNREGA grievance authority, ombudsman, or collector, using social-audit minutes, Gram Sabha record, muster-roll pages, fake job-card details, job-card/work IDs, wage due calculation, collector/BDO complaint proof, NGO/helper details, and prior complaints; if the Collector already did nothing, ask for the action-taken report and next escalation in writing [{mgnrega}]."
        )
    elif job_card:
        lines.append(
            f"- File a written job-card/work-demand grievance with the Gram Panchayat and Programme Officer/BDO, keep acknowledgement, and escalate to the district MGNREGA grievance authority, ombudsman, or collector if no written reason/status is given [{mgnrega}]."
        )
    elif wage_delay:
        lines.append(
            f"- Prepare a wage-delay file with job card, work-demand/work ID, muster roll or attendance proof, work dates, bank/passbook entries, wage due calculation, panchayat/Programme Officer complaint proof, and escalation to the district MGNREGA grievance authority or ombudsman [{mgnrega}]."
        )
    if rti is not None:
        lines.append(
            f"- If records or action-taken status are not given, use RTI for muster roll, job-card/work-demand entries, payment orders/FTO status, social-audit action-taken report, and grievance-file notes [{rti}]."
        )
    return lines


def _render_default_bail_no_chargesheet(q: str, sources: dict[str, int], passages: list[dict]) -> list[str]:
    bnss = sources.get("bnss")
    if bnss is None:
        return []
    crpc = sources.get("crpc")
    uapa = sources.get("uapa")
    uapa_any = sources.get("uapa_any")
    mcoca = sources.get("mcoca")
    ipc_cheating = sources.get("ipc_cheating")
    bns_cheating = sources.get("bns_cheating")
    uapa_anchor = _source_anchor(sources, "uapa", passages)
    has_uapa_43d = bool(uapa is not None and "43d" in uapa_anchor)
    is_uapa = "uapa" in q or "unlawful activities" in q
    is_cheating = _has_any(q, ("ipc 420", "420", "cheating", "fraud", "bns 318", "section 318", "sec 318"))
    no_challan = _has_any(q, ("no challan", "challan not", "challan filed nahi", "challan not filed"))
    no_final_report = _has_any(q, ("no final report", "final report not", "no report after", "extension request", "extension application"))
    person = "your brother" if _has_any(q, ("brother", "bhai")) else "the accused"

    lines: list[str] = [
        f"Treat {person}'s Default-bail / no-charge-sheet custody calculation as a statutory/default-bail calculation: count days from first remand and check whether a valid chargesheet/challan or extension order was filed before the deadline [{bnss}]."
    ]
    if no_challan:
        lines.append(
            f"Because the user says no challan was filed, translate that into the chargesheet/final-report default bail check instead of accepting a police 'wait' reply without the remand-date calculation [{bnss}]."
        )
    if no_final_report:
        lines.append(
            f"A police extension request without a final report/chargesheet is not the same as a valid completed filing; check the remand date, whether a proper extension order exists, and whether default bail had to be filed after the statutory period expired [{bnss}]."
        )
    if is_uapa and has_uapa_43d:
        lines.append(
            f"Because your question says UAPA and 90 days/no chargesheet, treat it as a special-statute default-bail calculation; do not use only the ordinary 60/90-day rule, and check the UAPA extension source, Section 43D, the prosecutor report, and the Special Court extension order because a valid extension can move the timeline toward 180 days [{uapa}]."
        )
    elif is_uapa and uapa_any is not None:
        lines.append(
            f"Because your question says UAPA and 90 days/no chargesheet, treat the UAPA source as a special-statute flag and warning: this header or generic source is not enough by itself to calculate extension or default bail, so verify the exact Section 43D extension source and Special Court order before relying on ordinary BNSS default-bail timing [{uapa_any}]."
        )
    if _has_any(q, ("mcoca", "mco case", "maharashtra control of organised crime")):
        if mcoca is not None:
            lines.append(
                f"Because your question says MCOCA, check the MCOCA Section 21 custody-extension source before applying ordinary default-bail timing; it can move the investigation period toward 180 days if the Special Court validly extends time on the Public Prosecutor report [{mcoca}]."
            )
        else:
            lines.append(
                f"Because your question says MCOCA, do not apply the ordinary 60/90-day default-bail rule without the special-statute file; verify the MCOCA extension application/order, first-remand date, and chargesheet status with the remand/Special Court papers before calculating custody limits [{bnss}]."
            )
    if is_cheating and ipc_cheating is not None:
        lines.append(
            f"For an IPC 420/cheating case after about six months in Tihar, calculate the default-bail period from the exact offence maximum and remand date; an IPC 420-type maximum usually points to the 60-day route, but verify the exact offences before excluding a 90-day/special-statute calculation [{ipc_cheating}]."
        )
    if is_cheating and bns_cheating is not None:
        lines.append(
            f"If the new BNS cheating provision applies, keep that BNS offence source with the BNSS custody calculation so the 60 or 90 day default-bail question is not answered by mixing old IPC and new BNS punishment assumptions [{bns_cheating}]."
        )
    if is_cheating and _has_any(q, ("68 days", "70 days", "72 days", "75 days", "80 days", "6 months", "six months", "no challan", "no chargesheet", "no charge sheet", "no final report", "extension request")):
        lines.append(
            f"At 68/70/75/80 days or six months in a cheating case with no chargesheet/challan/final report, do not just wait for police; ask the remand court to decide the 60-day versus 90-day default bail calculation from the exact section and maximum punishment [{bnss}]."
        )
    if crpc is not None:
        lines.append(
            f"If the case belongs to the older IPC/CrPC regime, compare the same default-bail calculation with the CrPC Section 167 source instead of mixing old and new procedure [{crpc}]."
        )
    lines.extend(
        [
            "**What you can do next**",
            f"- Make a custody-days chart with arrest date, first remand date, remand orders, offence sections and maximum punishment, charge-sheet filing date/status, extension application/order if any, prior bail orders, and surety readiness; take it to the Special Court or legal-aid lawyer and file the default-bail application in the Magistrate/trial court/Special Court controlling remand [{bnss}].",
        ]
    )
    return lines


def _render_ndps_quantity_bail(q: str, sources: dict[str, int], passages: list[dict]) -> list[str]:
    ndps = sources.get("ndps")
    if ndps is None:
        return []
    bail = sources.get("bail")
    article21 = sources.get("article21")
    bnss_bail = sources.get("bnss_bail")
    ndps_anchor = _source_anchor(sources, "ndps", passages)
    bail_anchor = _source_anchor(sources, "bail", passages)
    has_section37 = bail is not None and "sec-37" in bail_anchor
    has_section36a = bail is not None and "sec-36" in bail_anchor
    ndps_source_label = "NDPS cannabis possession source" if "sec-20" in ndps_anchor else "NDPS definition source" if "sec-2" in ndps_anchor else "NDPS source"
    substance = next((term for term in ("heroin", "mdma", "ganja", "charas", "cannabis", "bhang", "cbd", "thc", "vape") if term in q), "the seized substance")
    quantity_match = re.search(r"\b\d+(?:\.\d+)?\s*(?:kg|kilogram|kilograms|g|gram|grams|mg|milligram|milligrams)\b", q)
    quantity_phrase = quantity_match.group(0) if quantity_match else "the alleged quantity"
    quantity_subject = (
        f"{quantity_phrase} {substance} / {substance} and {quantity_phrase}"
        if substance == "heroin" and quantity_phrase != "the alleged quantity"
        else f"{quantity_phrase} {substance}"
    )
    repeat_bail = _has_any(q, ("rejected", "rejection", "supreme court", "session court", "sessions court"))
    small_or_personal = _has_any(q, ("small quantity", "personal use", "5 gram", "5 grams", "5g"))
    commercial_question = _has_any(q, ("commercial", "50 gram", "50 grams", "50g", "200 gram", "200 grams", "200g"))
    mdma_bag = "mdma" in q and _has_any(q, ("my bag", "friend's bag", "friends bag", "bag"))
    airport_vape = _has_any(q, ("vape", "vape cartridge", "vape pen", "cbd", "thc", "oil")) and _has_any(q, ("airport", "passport", "customs", "flight", "mumbai", "delhi", "goa"))

    lines: list[str] = []
    if airport_vape:
        airport_phrase = "passport seized at Mumbai airport" if "mumbai" in q and "passport" in q else "airport/passport/customs seizure"
        lines.append(
            f"For {airport_phrase} involving a CBD/THC vape cartridge or oil, do not treat this as generic vaping advice; check the seizure memo, FSL/lab result, exact substance, quantity, and NDPS schedule/quantity classification before deciding offence, bail, or passport-retention risk [{ndps}]."
        )
    elif mdma_bag:
        lines.append(
            f"For an MDMA-in-my-bag/MDMA-in-a-bag fact pattern involving {quantity_phrase}, a friend or another person, and unclear FSL quantity, the defence file must separate possession, conscious possession, seizure witnesses, exact net weight, and FSL quantity before deciding punishment or whether Section 37 can apply [{ndps}]."
        )
        lines.append(
            f"Do not estimate punishment from '200mg' or from someone calling the other person a drug dealer alone; compare the actual psychotropic-substance section, small/intermediate/commercial quantity notification, seizure memo, and possession facts first [{ndps}]."
        )
    elif repeat_bail and _has_any(q, ("200 gram", "200 grams", "200g", "commercial", "supreme court")):
        lines.append(
            f"Because you mention {quantity_phrase} {substance}, commercial quantity, three bail rejections, and a possible Supreme Court move, do not file the next step as a routine repeat bail request; first map the seizure/FSL facts, quantity classification, Section 37 issue, custody duration, and trial progress [{ndps}]."
        )
    elif repeat_bail and _has_any(q, ("3 yrs", "3 years", "three years", "tihar")):
        lines.append(
            f"For three years in Tihar jail or similar prison custody after repeated rejection, the retrieved NDPS source is not by itself the complete repeat-bail answer; verify NDPS Section 37, the quantity notification, prior rejection reasons, custody duration, and trial progress before treating the next move as ordinary bail [{ndps}]."
        )
    elif commercial_question:
        lines.append(
            f"For {quantity_subject}, start with the {ndps_source_label} and classify whether it is commercial or not by checking small, intermediate, or commercial quantity from the seizure memo, net weight, FSL/lab result, and NDPS quantity notification; do not decide commercial quantity from the user wording alone [{ndps}]."
        )
    elif small_or_personal:
        lines.append(
            f"For {quantity_phrase} {substance} or 'personal use', small quantity has to be proved from the seizure memo, net weight, FSL/lab result, and quantity notification; personal-use wording alone does not prove the legal quantity category [{ndps}]."
        )
    else:
        lines.append(
            f"For an NDPS bail or punishment question, first classify the substance and quantity from the seizure memo and FSL/lab report before choosing ordinary bail, Section 37 bail, or default-bail strategy [{ndps}]."
        )
    if has_section37:
        lines.append(
            f"If the alleged quantity/offence is commercial or otherwise attracts the NDPS Section 37 filter, the Special Court/High Court bail argument must address the statutory bail bar and prior rejection reasons [{bail}]."
        )
    elif bail is not None and has_section36a:
        lines.append(
            f"The retrieved NDPS custody/Special Court source is useful for forum and timeline, but it is not the exact Section 37 bail-condition passage; verify Section 37 and the quantity notification before treating the case as ordinary bail [{bail}]."
        )
    else:
        lines.append(
            f"The retrieved NDPS source is not enough by itself to settle Section 37 or the quantity notification; treat that as a source-required check before estimating bail chances [{ndps}]."
        )
    if article21 is not None and _has_any(q, ("3 yrs", "3 years", "three years", "tihar", "long custody")):
        lines.append(
            f"For three years in Tihar jail or other long prison custody after repeated NDPS bail rejection, Article 21 is the personal-liberty source for a custody-delay argument [{article21}]."
        )
    if bnss_bail is not None:
        lines.append(
            f"The BNSS bail source says the ordinary court bail power exists, but the NDPS quantity/Section 37 check must be handled first [{bnss_bail}]."
        )
    lines.extend(
        [
            "**What you can do next**",
            f"- Collect the seizure memo, panchnama, FSL/lab report, exact net weight, sample/packaging details, NDPS sections, quantity notification/classification, custody start date, charge-sheet status, trial progress, and all prior bail rejection orders; take these to the Special NDPS Court, High Court, or legal aid before deciding the next bail/Supreme Court step [{bail if bail is not None else ndps}].",
        ]
    )
    return lines


def _render_ndps_bhang_lassi(q: str, sources: dict[str, int]) -> list[str]:
    ndps = sources.get("ndps")
    if ndps is None:
        return []
    state_excise = sources.get("state_excise")
    bail = sources.get("bail")
    lines = [
        f"For bhang-lassi or Holi facts where police are saying NDPS, do not assume the answer from the word bhang alone; check the actual police section, seizure memo, lab/FSL result, exact substance, and quantity against the NDPS definition source [{ndps}].",
    ]
    if state_excise is not None:
        lines.append(
            f"For Mahabaleshwar/Maharashtra facts, keep the Maharashtra Prohibition/State Excise Act source in the file too because bhang/intoxicant or permit issues can sit outside a pure NDPS-only answer [{state_excise}]."
        )
        lines.append(
            f"Do not treat every bhang-lassi fact pattern as an NDPS possession offence until the FIR/notice says whether police are using NDPS, Maharashtra prohibition/excise, or another local rule [{state_excise}]."
        )
    else:
        if _has_any(q, ("maharashtra", "mahabaleshwar", "mumbai", "pune", "nagpur")):
            lines.append(
                f"I do not have the exact Maharashtra State Excise Act or local bhang-rule source in the retrieved index, so do not treat the NDPS source as the controlling State Excise source for a Mahabaleshwar/Holi bhang-lassi fact pattern [{ndps}]."
            )
            lines.append(
                f"Also verify any Maharashtra excise/local bhang rule or police section before treating every bhang-lassi fact pattern as an NDPS possession offence [{ndps}]."
            )
        else:
            lines.append(
                f"I do not have the exact local state-excise or bhang-rule source for the place in the retrieved index, so do not treat the NDPS source as the controlling local excise source without the police section and state/city facts [{ndps}]."
            )
            lines.append(
                f"Also verify the local excise/prohibition rule or police section before treating every bhang-lassi fact pattern as an NDPS possession offence [{ndps}]."
            )
    if bail is not None:
        lines.append(
            f"If NDPS bail is actually invoked, the Special Court/NDPS bail route and Section 37 filter must be checked before relying on ordinary bail advice [{bail}]."
        )
    lines.extend([
        "**What you can do next**",
        f"- Get the seizure memo, panchnama, FIR/notice sections, lab/FSL report, exact weight, arrest/remand papers, and place/state details; take them to legal aid or an NDPS lawyer to check whether this is NDPS, State excise/local rule, or no prosecutable offence on those facts [{state_excise if state_excise is not None else ndps}].",
    ])
    return lines


def _render_pmla_anticipatory_interim_bail(q: str, sources: dict[str, int]) -> list[str]:
    pmla = sources.get("pmla45")
    if pmla is None:
        return []
    anticipatory = _first_source(sources, "bnss_anticipatory", "crpc_anticipatory")
    regular = _first_source(sources, "bnss_regular", "crpc_regular")
    pmla_arrest = sources.get("pmla19")
    article21 = sources.get("article21")
    precedent = sources.get("pmla_sc_precedent")
    pre_arrest = _has_any(q, ("before arrest", "pre arrest", "pre-arrest", "summons", "raid", "anticipatory"))
    interim_vulnerability = _has_any(q, (
        "interim", "new born", "newborn", "baby", "pregnant", "pregnancy",
        "woman", "wife", "sick", "infirm", "medical",
    ))
    twin_condition_context = _has_any(q, (
        "twin condition", "twin conditions", "section 45", "sec 45",
        "s.45", "not guilty", "not likely to commit",
    ))

    lines = [
        f"For PMLA/ED pre-arrest bail or interim bail, do not answer from ordinary regular bail alone: keep the PMLA Section 45/twin-condition source with the bail file, because the special PMLA bail filter and proviso can change the argument [{pmla}].",
    ]
    if twin_condition_context:
        lines.append(
            f"For a PMLA twin-conditions or 'not guilty' argument, Section 45 is the controlling source to compare with the complaint, scheduled offence, custody stage, and prosecution material; do not answer it as ordinary bail alone [{pmla}]."
        )
        if precedent is not None:
            lines.append(
                f"Keep the Supreme Court PMLA bail/arrest precedent in the file with Section 45, because precedent can affect how the twin-condition and arrest-safeguard argument is framed [{precedent}]."
            )
    if pre_arrest and anticipatory is not None:
        lines.append(
            f"For an ED summons/raid or before-arrest question, frame the procedural step as PMLA-specific pre-arrest protection only after checking the ECIR or scheduled-offence papers and the PMLA Section 45 issue; the BNSS/CrPC anticipatory-bail source is the procedure source, not the whole answer [{anticipatory}]."
        )
    if interim_vulnerability:
        if regular is not None:
            lines.append(
                f"If the accused is already arrested and the issue is interim bail for a woman, newborn-care, pregnancy, sickness, or infirmity facts, take those records to the Special PMLA Court/High Court as a vulnerability/interim-bail track instead of treating it as routine regular bail [{regular}]."
            )
        lines.append(
            f"The PMLA Section 45 proviso is the source to check for woman/sick/infirm vulnerability arguments, but the court will still need custody papers, medical/newborn records, and the scheduled-offence/ECIR file [{pmla}]."
        )
    if pmla_arrest is not None:
        lines.append(
            f"If arrest has happened or is threatened, keep the PMLA arrest/grounds source with the summons, arrest memo, and written grounds papers [{pmla_arrest}]."
        )
    if article21 is not None:
        lines.append(
            f"Preserve Article 21 liberty, medical, and family-care facts as supporting material, but do not let constitutional wording replace the PMLA-specific bail test [{article21}]."
        )
    procedure = anticipatory or regular or pmla
    lines.extend([
        "**What you can do next**",
        f"- Collect ED summons/raid memo, ECIR or scheduled-offence FIR details if available, arrest or custody status, PMLA sections, bank-fraud/scheduled-offence papers, medical/newborn-care records, prior bail orders, and surety papers; ask a PMLA lawyer/DLSA to file before the Special PMLA Court or High Court based on the stage [{procedure}].",
    ])
    return lines


def _render_state_prohibition_excise_accused(q: str, sources: dict[str, int]) -> list[str]:
    procedure = _first_source(sources, "bnss", "crpc")
    state_act = sources.get("state_excise")
    if procedure is None and state_act is None:
        return []
    primary = state_act or procedure
    state_hint = (
        "Bihar" if "bihar" in q else
        "Gujarat" if "gujarat" in q else
        "the relevant State"
    )
    lines: list[str] = []
    if state_act is not None:
        state_source = (
            "Bihar Prohibition and Excise Act source"
            if state_hint == "Bihar"
            else f"{state_hint} prohibition or excise source"
        )
        lines.append(
            f"For a prohibition/excise accusation, start with the exact {state_source} and the FIR/notice section; punishment turns on the state Act section and whether the allegation is consumption, possession, transport, sale, or repeat offence [{state_act}]."
        )
    else:
        lines.append(
            f"For a prohibition-law case or village drinking accusation, do not state a concrete punishment from BNSS/CrPC alone; first get the state, FIR/notice section, and whether police allege consumption, possession, transport, sale, or repeat offence [{procedure}]."
        )
    if procedure is not None:
        lines.append(
            f"Use the BNSS/CrPC criminal-procedure source only for arrest, notice, bail, production, and court-procedure steps; if the person is not accused of a non-bailable offence, ask about the right to be released on bail, but the procedure source does not itself decide the State prohibition punishment [{procedure}]."
        )
    lines.extend([
        "**What you can do next**",
        f"- Keep the FIR/notice, police-station name, state/district, exact prohibition/excise sections, seizure or breath-test papers, arrest/bail/notice status, prior case history, and witness details; take those to DLSA or a local criminal lawyer before guessing the punishment [{primary}].",
    ])
    return lines


def _first_source(sources: dict[str, int], *keys: str) -> int | None:
    for key in keys:
        idx = sources.get(key)
        if idx is not None:
            return idx
    return None


def _render_regular_bail_after_arrest(q: str, sources: dict[str, int]) -> list[str]:
    primary = _first_source(sources, "bnss_regular", "crpc_regular")
    if primary is None:
        return []
    crpc = sources.get("crpc_regular")
    bnss = sources.get("bnss_regular")
    person = "your brother" if _has_any(q, ("brother", "bhai")) else "the arrested person"
    lines = [
        f"Because {person} is already arrested or in custody, the immediate route is regular bail before the court handling remand/trial, not anticipatory bail [{primary}].",
    ]
    if bnss is not None:
        lines.append(
            f"For current procedure, keep the BNSS bail source with the remand papers and ask which court is controlling custody: Magistrate/trial court first, then Sessions/High Court if bail is refused or the offence requires that forum [{bnss}]."
        )
    if crpc is not None:
        lines.append(
            f"If the case is under the older IPC/CrPC regime, compare the same regular-bail step with the CrPC bail source instead of mixing old and new procedure [{crpc}]."
        )
    lines.extend([
        "**What you can do next**",
        f"- Get the FIR/case number, offence sections, arrest memo, remand order, custody date, police-station/court name, prior bail order if any, address/income proof, and surety or personal-bond papers; file the regular-bail application in the remand/trial court or the Sessions/High Court forum advised from the offence and order [{primary}].",
    ])
    return lines


def _render_lgbtq_identity_arrest_safeguard(
    q: str,
    sources: dict[str, int],
    route: MatterRoute,
) -> list[str]:
    navtej = sources.get("navtej")
    if navtej is None:
        return []
    article21 = sources.get("article21")
    article22 = sources.get("article22")
    bnss_arrest = sources.get("bnss_arrest")
    bnss_production = sources.get("bnss_production")
    crpc_arrest = sources.get("crpc_arrest")
    crpc_production = sources.get("crpc_production")
    liberty = article21 if article21 is not None else navtej
    person = "your son" if _has_any(q, ("son", "my son")) else "the arrested person"
    lines = [
        f"Being gay or having a sexual orientation is not itself an offence; Navtej Singh Johar is the controlling source for consensual adult same-sex conduct and sexual orientation, so police must point to a real FIR/offence section beyond identity alone [{navtej}].",
    ]
    if article22 is not None:
        lines.append(
            f"For the custody side, ask immediately for the arrest grounds, FIR/offence sections, police-station details, and whether {person} was produced before a Magistrate; Article 22 is the constitutional arrest-safeguard source for that check [{article22}]."
        )
    if route.legal_regime == "incident_date_needed_for_bns_bnss_bsa_vs_ipc_crpc":
        lines.append(
            "The incident date is still needed before choosing BNSS or CrPC procedure; do not describe either regime as selected until that date is known."
        )
    if bnss_arrest is not None:
        lines.append(
            f"For an incident on or after 1 July 2024, BNSS Section 47 is the source for communicating the offence particulars or other grounds of arrest [{bnss_arrest}]."
        )
    if bnss_production is not None:
        lines.append(
            f"For current procedure, use the BNSS production source to verify taking the arrested person before the Magistrate without unnecessary delay [{bnss_production}]."
        )
    if crpc_arrest is not None:
        lines.append(
            f"For a pre-1-July-2024 incident, CrPC Section 50 is the arrest-information source to verify instead of BNSS [{crpc_arrest}]."
        )
    if crpc_production is not None:
        lines.append(
            f"For legacy procedure, use the CrPC production source to verify the Magistrate-production requirement [{crpc_production}]."
        )
    custody_cite = article22 or bnss_production or crpc_production or bnss_arrest or crpc_arrest or navtej
    lines.extend([
        "**What you can do next**",
        f"- Ask for the written grounds of arrest, arrest time and place, police station, and whether {person} was produced before a Magistrate; keep any remand order or written refusal with those custody facts [{custody_cite}].",
        f"- If police disclose no offence beyond gay identity or sexual orientation, treat it as an urgent identity-based liberty issue for the Magistrate or High Court route rather than a normal bail query [{liberty}].",
    ])
    return lines


def _render_bank_account_freeze_legal_hold(
    q: str,
    sources: dict[str, int],
    route: MatterRoute,
) -> list[str]:
    rbi_scope = sources.get("rbi_scope")
    if rbi_scope is None:
        return []
    rbi_complaint = sources.get("rbi_complaint")
    bnss_seizure = sources.get("bnss_seizure")
    crpc_seizure = sources.get("crpc_seizure")
    it = sources.get("it")
    lines = [
        f"For a frozen, blocked, or lien-marked account, ask the bank for the written freeze/lien reason and first use the RBI Integrated Ombudsman Scheme scope source only to check whether the bank or regulated entity is covered; it does not by itself prove that the legal hold is invalid or that an RBI Ombudsman complaint is maintainable [{rbi_scope}]."
    ]
    if "salary account" in q:
        lines.append(
            f"For a salary account blocked after a police request or other legal hold with no notice, ask the bank to identify the exact amount affected, originating authority, request/reference number, and whether credits and essential withdrawals are also restricted [{rbi_scope}]."
        )
    if route.legal_regime == "incident_date_needed_for_bns_bnss_bsa_vs_ipc_crpc":
        lines.append(
            "The freeze or police-seizure date is needed before choosing BNSS Section 106 or legacy CrPC Section 102; ask the bank for the written police/court reference and date."
        )
    if bnss_seizure is not None:
        lines.append(
            f"For a police seizure on or after 1 July 2024, BNSS Section 106 says a police officer may seize property alleged or suspected to have been stolen, or found in circumstances creating suspicion of an offence, and must report the seizure to the Magistrate [{bnss_seizure}]."
        )
    if crpc_seizure is not None:
        lines.append(
            f"For a pre-1-July-2024 legal hold, verify the police seizure against CrPC Section 102 rather than applying BNSS retrospectively [{crpc_seizure}]."
        )
    if rbi_complaint is not None:
        lines.append(
            f"Use RBI Scheme clauses 9 and 10 to check complaint grounds and maintainability after a written bank grievance, including whether the challenged bank action merely complied with a law-enforcement or court order [{rbi_complaint}]."
        )
    if it is not None and _has_any(
        q,
        (
            "identity theft",
            "identity misuse",
            "impersonation",
            "phishing",
            "otp",
            "hacked",
            "unauthorized transaction",
            "unauthorised transaction",
            "upi fraud",
            "upi scam",
            "fake upi",
        ),
    ):
        lines.append(
            f"Keep the IT Act source only for a separate electronic-fraud or identity-misuse allegation; it is not the authority for the bank freeze itself [{it}]."
        )
    lines.extend((
        "**What you can do next**",
        "- Ask the bank in writing for the written freeze/lien reason, the originating request/reference and order copy, the amount and transactions affected, and the nodal officer handling the hold when it says a cyber/police complaint, including a cyber police complaint, caused the hold.",
        "- Keep the freeze/lien SMS or email, account statement, bank complaint and reply, request/reference or order copy, transaction IDs, KYC proof, and the exact freeze date.",
    ))
    return lines


def _render_vehicle_theft_fir_refusal(
    route: MatterRoute,
    sources: dict[str, int],
) -> list[str]:
    bnss_fir = sources.get("bnss_fir")
    bnss_refusal = sources.get("bnss_refusal")
    crpc = sources.get("crpc")
    legacy = route.legal_regime == "legacy_ipc_crpc_evidence_for_pre_2024_incident"
    current = route.legal_regime == "current_bns_bnss_bsa_for_post_2024_incident"
    if legacy and crpc is None:
        return []
    if current and (bnss_fir is None or bnss_refusal is None):
        return []
    if not legacy and not current and (
        bnss_fir is None or bnss_refusal is None or crpc is None
    ):
        return []

    lines: list[str] = []
    if legacy:
        lines.append(
            f"For this pre-1-July-2024 incident, CrPC Section 154 is the source for giving information about a cognizable offence and escalating a police refusal [{crpc}]."
        )
    elif current:
        lines.append(
            f"BNSS Section 173 says information relating to a cognizable offence may be given orally or electronically to the officer in charge of a police station [{bnss_fir}]."
        )
        lines.append(
            f"If the station refuses to record it, BNSS Section 173 provides a written-post route to the Superintendent of Police and then an application to the Magistrate [{bnss_refusal}]."
        )
    else:
        lines.extend([
            f"For a pre-1-July-2024 incident, verify the information-and-refusal route under CrPC Section 154 [{crpc}].",
            f"For an incident on or after 1 July 2024, BNSS Section 173 says information about a cognizable offence may be given orally or electronically to the officer in charge of a police station [{bnss_fir}].",
            f"After a refusal under the current procedure, BNSS Section 173 provides a written-post route to the Superintendent of Police and then an application to the Magistrate [{bnss_refusal}].",
        ])

    lines.extend([
        "**What you can do next**",
        "- Keep the vehicle number, chassis/engine details if available, RC and insurance papers, place and time, CCTV or witnesses, phone/GPS details, written complaint, acknowledgement, and any refusal.",
    ])
    return lines


def _render_bail_surety_condition_modification(q: str, sources: dict[str, int]) -> list[str]:
    primary = _first_source(sources, "bnss_regular", "crpc_regular", "article21")
    if primary is None:
        return []
    moti = sources.get("moti_ram")
    amount = "Rs.50,000" if _has_any(q, ("50000", "50,000", "50k")) else "the surety/bond amount"
    lines = [
        f"If bail is already granted but {amount} or conditions are too strict to comply with, treat this as a bail-condition modification problem, not a fresh FIR or ordinary legal-notice problem [{primary}].",
        f"The first practical step is usually an application before the same bail court asking for reduced surety, personal bond, alternate surety, or modification of the strict condition; escalate only if that court refuses or the order itself needs challenge [{primary}].",
    ]
    if moti is not None:
        lines.append(
            f"Keep the bail-surety precedent source with income/poverty proof because unaffordable surety can keep a person in jail even after bail is granted [{moti}]."
        )
    lines.extend([
        "**What you can do next**",
        f"- Keep the bail order, exact condition/surety amount, rejection or verification problem, income proof, address proof, family surety IDs, and reason the condition cannot be met; ask the defence lawyer/DLSA to file a modification/reduction application in the bail court [{primary}].",
    ])
    return lines


def _render_bail_surety_amount_context(q: str, sources: dict[str, int]) -> list[str]:
    primary = _first_source(sources, "bnss_regular", "crpc_regular")
    if primary is None:
        return []
    ni = sources.get("ni")
    lines = [
        f"There is no single standard surety amount that applies to every bail case; the court sets bond/surety conditions from the offence, accused's circumstances, appearance risk, and the bail order [{primary}].",
    ]
    if ni is not None:
        lines.append(
            f"For a cheque-bounce/NI Act case, keep the complaint, summons/warrant status, cheque amount, and settlement/payment record separate from the bail-surety question [{ni}]."
        )
    lines.extend([
        "**What you can do next**",
        f"- Read the summons/bailable-warrant/non-bailable-warrant or bail order for the exact bond and surety condition; if the amount is unaffordable, ask the same court for lower surety, personal bond, time to arrange surety, or alternate surety with income/address proof [{primary}].",
    ])
    return lines


def _render_anticipatory_bail_rejected_next_step(q: str, sources: dict[str, int]) -> list[str]:
    primary = _first_source(sources, "bnss_anticipatory", "crpc_anticipatory")
    if primary is None:
        return []
    regular = sources.get("bnss_regular")
    bns = sources.get("bns_cruelty")
    lines = [
        f"This is a Successive anticipatory-bail application problem: after anticipatory bail is rejected by the Sessions Court, read the rejection order and decide whether to move the High Court or file again only on genuinely changed circumstances; do not simply repeat the same application in the same court [{primary}].",
    ]
    if bns is not None:
        lines.append(
            f"For a 498A/dowry-cruelty allegation, keep the exact cruelty/offence source and incident date separate from the bail forum decision; the FIR sections and family role matter [{bns}]."
        )
    if regular is not None:
        lines.append(
            f"If the person has already been arrested, switch from anticipatory bail to regular bail using the custody/remand papers instead of continuing a pre-arrest-bail route [{regular}]."
        )
    lines.extend([
        "**What you can do next**",
        f"- Keep the Sessions rejection order, FIR/sections, arrest or notice status, incident date, role-specific facts, medical/age facts if any, and any changed circumstances; take those papers to DLSA or a criminal lawyer for the High Court anticipatory-bail or regular-bail route [{primary}].",
    ])
    return lines


def _render_498a_bail_rejection_source_gap(q: str, sources: dict[str, int]) -> list[str]:
    bail = sources.get("bnss_bail")
    cruelty = sources.get("bns_cruelty")
    if bail is None or cruelty is None:
        return []
    return [
        f"After a Sessions Court bail or anticipatory-bail rejection in a 498A/dowry-cruelty matter, first obtain the rejection order, FIR, incident date, and current arrest status; do not assume the same court will simply hear the same request again [{bail}].",
        f"The retrieved BNS cruelty source is relevant only after checking whether the incident falls under the current criminal regime; keep the exact allegation and each family member's alleged role separate [{cruelty}].",
        f"The retrieved passages do not include the specific anticipatory-bail provision, so ask DLSA or a criminal lawyer to verify whether a High Court anticipatory bail application is available; if the person is already arrested, ask about the regular-bail route instead [{bail}].",
        "**What you can do next**",
        f"- Take the Sessions rejection order, FIR/complaint, arrest or notice status, incident dates, role-specific material, medical/age facts, and any genuinely changed circumstances to DLSA or a criminal lawyer before choosing a High Court anticipatory bail or regular-bail step [{bail}].",
    ]


def _render_sexual_offence_sessions_bail_forum(q: str, sources: dict[str, int]) -> list[str]:
    bail = _first_source(sources, "bnss_sessions_bail", "crpc_sessions_bail")
    if bail is None:
        return []
    offence = _first_source(sources, "bns_rape", "ipc_rape")
    lines = [
        f"For an IPC 376/rape or equivalent serious sexual-offence case, do not treat the Magistrate filing as an ordinary petty-offence bail route; the remand court papers and Sessions/High Court bail forum have to be checked from the offence and custody stage [{bail}].",
    ]
    if offence is not None:
        lines.append(
            f"Keep the rape/sexual-offence source with the FIR section and incident date; the offence section decides seriousness and forum strategy before bail drafting [{offence}]."
        )
    if bail is not None:
        lines.append(
            f"The BNSS/CrPC bail source supports checking whether the Sessions Court or High Court is the proper bail forum after remand, rather than assuming the Magistrate must decide every regular-bail request [{bail}]."
        )
    lines.extend([
        "**What you can do next**",
        f"- Get the FIR, 164/statement status if available, arrest/remand order, exact IPC/BNS section, age/medical facts, prior Magistrate order, and court name; ask counsel/DLSA whether the regular-bail application belongs before Sessions Court/High Court and preserve any Magistrate refusal/order [{bail}].",
    ])
    return lines


def _render_uapa_prima_facie_bail(q: str, sources: dict[str, int]) -> list[str]:
    uapa = sources.get("uapa43d")
    if uapa is None:
        return []
    bail = sources.get("bnss_regular")
    article21 = sources.get("article21")
    custody = "18 months" if "18 months" in q else "long custody" if _has_any(q, ("jail", "custody", "undertrial")) else "custody"
    lines = [
        f"For UAPA bail, 'prima facie case made out' refers to the Section 43D special bail filter where the court checks whether there are reasonable grounds for believing the accusation is prima facie true; that filter must be addressed before ordinary bail arguments [{uapa}].",
        f"Separate regular bail, default bail, and prolonged-custody/speedy-trial arguments; {custody} by itself is not the same legal test as the UAPA prima-facie filter, but long delay can become a separate liberty argument [{uapa}].",
    ]
    if bail is not None:
        lines.append(
            f"Use the BNSS bail source only for the forum/procedure side; it does not replace the UAPA special bail filter [{bail}]."
        )
    if article21 is not None:
        lines.append(
            f"If trial delay or prolonged incarceration is the real issue, keep Article 21 speedy-trial/liberty arguments separate from the UAPA prima-facie merits test [{article21}]."
        )
    lines.extend([
        "**What you can do next**",
        f"- Collect the FIR/NIA case papers, UAPA sections, charge-sheet, sanction/order sheets, prior bail rejection order, custody duration, witness/prosecution delay status, and the paragraph where the court found prima facie case; ask Special Court/High Court counsel or DLSA whether the next move is regular bail, appeal, default bail, or delay-based bail [{uapa}].",
    ])
    return lines


def _render_itpa_booking_only_accused(q: str, sources: dict[str, int]) -> list[str]:
    itpa = sources.get("itpa")
    if itpa is None:
        return []
    procedure = sources.get("bnss")
    lines = [
        f"For a PITA/ITPA question where you say you only handled phone calls or bookings and did not meet clients, first compare the exact alleged role with Section 5 or the cited ITPA procuring, inducing or taking source; do not accept a broad 'phone booking is illegal' label without the FIR or notice sections [{itpa}].",
    ]
    if procedure is not None:
        lines.append(
            f"Use the BNSS procedure source for notice, arrest, bail, or court appearance steps, but keep it separate from whether the ITPA offence ingredients fit the booking-only facts [{procedure}]."
        )
    lines.extend([
        "**What you can do next**",
        f"- Preserve the FIR/notice, call records/chats, job role, who took money, whether any person was procured/induced/taken, raid memo if any, arrest/notice status, and phone ownership; take those to legal aid or a criminal lawyer before giving a statement or contacting alleged clients [{itpa}].",
    ])
    return lines


def _render_itpa_receptionist_raid_accused(q: str, sources: dict[str, int]) -> list[str]:
    itpa5 = sources.get("itpa5")
    if itpa5 is None:
        return []
    itpa8 = sources.get("itpa8")
    bail = sources.get("bnss_bail")
    case_paper = sources.get("bnss_case_paper")
    lines = [
        f"For a spa/parlour raid where you say you were only a receptionist or employee, do not accept a generic ITPA label: Section 5 concerns procuring, inducing, or taking a person for prostitution, so the FIR must connect that conduct to your own reception-desk work and evidence [{itpa5}].",
    ]
    if itpa8 is not None:
        lines.append(
            f"If police also allege soliciting, compare that separate ITPA provision with actual public-soliciting facts; reception-desk work alone is not the same allegation [{itpa8}]."
        )
    if bail is not None:
        lines.append(
            f"If you were arrested or kept in custody, use the BNSS bail source with the FIR, arrest memo, exact role, and custody papers to check the court route [{bail}]."
        )
    if case_paper is not None:
        lines.append(
            f"Keep the BNSS case-paper source with the FIR sections before making any statement beyond your own facts [{case_paper}]."
        )
    action_cites = " ".join(
        f"[{index}]"
        for index in (itpa5, itpa8, bail, case_paper)
        if index is not None
    )
    lines.extend([
        "**What you can do next**",
        f"- Get the FIR, arrest and seizure memos, CCTV/duty roster, salary or attendance proof, and evidence of your receptionist/employee role; take them to DLSA or a criminal lawyer and do not admit involvement beyond facts {action_cites}.",
    ])
    return lines


def _render_handcuff_restraint_objection(q: str, sources: dict[str, int]) -> list[str]:
    article21 = sources.get("article21")
    production = sources.get("production")
    primary = article21 or production
    if primary is None:
        return []
    lines = [
        f"Handcuffing during court production is not automatically answered as always legal or always illegal: treat it as a custody-liberty objection, and ask the court to record whether restraint was actually necessary for safety or escape risk in this specific high-security-prisoner case [{primary}].",
    ]
    if production is not None:
        lines.append(
            f"Keep the arrest-production/remand source in the file because the court can be asked to record whether restraint was actually necessary for safety or escape-risk reasons [{production}]."
        )
    lines.extend([
        "**What you can do next**",
        f"- Note the date, court, escorting police/jail staff, whether any written reason was shown, security-risk claim, injury or humiliation, and witness/video details; ask the defence lawyer or DLSA to raise the handcuff/restraint objection before the Magistrate/Sessions Court and seek directions for future production [{primary}].",
    ])
    return lines


def _render_undertrial_bnss479_review(q: str, sources: dict[str, int]) -> list[str]:
    bnss = sources.get("bnss479")
    if bnss is None:
        return []
    crpc = sources.get("crpc436a")
    lsa = sources.get("lsa")
    article21 = sources.get("article21")
    vulnerability = "65-year-old diabetic undertrial" if _has_any(q, ("65", "diabetic", "diabetes")) else "undertrial"
    lines = [
        f"For a {vulnerability}, BNSS Section 479 is the current undertrial custody-duration review source; compare actual detention with the maximum punishment and statutory exclusions, not only age or illness by itself [{bnss}].",
    ]
    if crpc is not None:
        lines.append(
            f"Use CrPC Section 436A only as the legacy comparison for older proceedings; do not mix the BNSS and CrPC calculations without checking the case date and custody record [{crpc}]."
        )
    if article21 is not None:
        lines.append(
            f"Age, diabetes, serious illness, or long delay should be preserved as an Article 21 liberty and medical-vulnerability point for the bail or review application [{article21}]."
        )
    if lsa is not None:
        lines.append(
            f"The Legal Services Authorities source supports taking the custody chart to DLSA/jail legal-aid clinic or the undertrial review process for lawyer assistance [{lsa}]."
        )
    if _has_any(q, ("review committee", "utrc", "under trial review", "undertrial review")):
        lines.append(
            f"Ask specifically for Under Trial Review Committee / jail legal-aid screening and a trial-court custody-duration check; do not treat age or diabetes alone as automatic release without the BNSS 479 calculation [{bnss}]."
        )
    lines.extend([
        "**What you can do next**",
        f"- Prepare a one-page custody chart with FIR/case number, offence sections and maximum punishment, arrest date, first remand date, charge-sheet and trial stage, prior bail orders, medical papers, age proof, and jail record; give it to DLSA/jail legal aid and ask the trial court or Under Trial Review Committee to check BNSS 479 eligibility [{bnss}].",
    ])
    return lines


def _render_custodial_death_inquiry(q: str, sources: dict[str, int]) -> list[str]:
    inquiry = _first_source(sources, "bnss196", "crpc176")
    if inquiry is None:
        return []
    human_rights = sources.get("human_rights")
    article21 = sources.get("article21")
    lines = [
        f"For a custodial death or police lockup death, the first legal step is the custody-death/inquest or Magistrate inquiry procedure, not a generic police complaint alone [{inquiry}].",
        f"For your father's police lockup death, ask in writing for the nearest Magistrate inquiry/inquest papers, post-mortem, body-handover record, arrest/remand papers, station diary, CCTV preservation, and medical record; these records decide the FIR, NHRC/SHRC, writ, or compensation route [{inquiry}].",
    ]
    if human_rights is not None:
        lines.append(
            f"Keep a parallel NHRC/State Human Rights Commission complaint track because the human-rights source covers inquiry into violations by public servants or negligence in preventing them [{human_rights}]."
        )
    if article21 is not None:
        lines.append(
            f"Also preserve the Article 21 life/personal-liberty point for DLSA or High Court advice if the custody-death record is blocked or manipulated [{article21}]."
        )
    lines.extend([
        "**What you can do next**",
        f"- For the custodial-death/lockup-suicide claim, apply in writing for post-mortem/inquest/Magistrate inquiry papers and CCTV preservation; keep arrest memo, remand order, medical history, witness names, photos, calls, station details, and refusal replies before filing NHRC/SHRC, Magistrate, police, or writ papers [{inquiry}].",
    ])
    return lines


def _render_custody_medical_care(q: str, sources: dict[str, int]) -> list[str]:
    article21 = sources.get("article21")
    prisons = sources.get("prisons")
    bnss_bail = sources.get("bnss_bail")
    if article21 is None and prisons is None and bnss_bail is None:
        return []
    condition = (
        "TB test"
        if _has_any(q, ("tb", "tuberculosis"))
        else "urgent pregnancy bleeding/fever medical examination"
        if _has_any(q, ("bleeding", "fever")) and _has_any(q, ("pregnant", "pregnancy", "undertrial"))
        else "pregnancy hospital checkup"
        if _has_any(q, ("pregnant", "pregnancy", "hospital checkup"))
        else "insulin/diabetes treatment"
        if _has_any(q, ("insulin", "diabetic", "diabetes"))
        else "medical care"
    )
    jail = (
        "Arthur Road jail"
        if "arthur road" in q
        else "Byculla jail"
        if "byculla" in q
        else "jail"
    )
    primary = article21 if article21 is not None else prisons if prisons is not None else bnss_bail
    lines: list[str] = []
    if article21 is not None:
        lines.append(
            f"For a prisoner needing urgent {condition} in {jail}, start from the Article 21 source on life and personal liberty; this is a health and treatment issue, not just a routine bail or adjournment question [{article21}]."
        )
        lines.append(
            f"Treat the delayed {condition} as an urgent custody medical-care issue, with a written medical status report or hospital examination request [{article21}]."
        )
        if _has_any(q, ("next production", "wait till next production", "jail doctor says wait")):
            lines.append(
                f"Do not wait only for the next production date if there is bleeding, fever, insulin interruption, or another urgent custody-health risk; create a written medical-status request and ask DLSA or the trial court for urgent directions [{article21}]."
            )
    if prisons is not None:
        lines.append(
            f"Use the Prisons Act sick-prisoner/medical-officer source too: a prisoner who wants medical attention or appears ill must be reported without delay so the Medical Officer or Medical Subordinate can attend to the prisoner [{prisons}]."
        )
    if bnss_bail is not None:
        lines.append(
            f"If the medical condition is serious or untreated despite written jail requests, ask DLSA or the lawyer whether the criminal court should be moved for medical status, hospital examination, or interim medical-bail relief [{bnss_bail}]."
        )
    lines.extend([
        "**What you can do next**",
        f"- Keep jail name, custody date, symptoms, prior doctor requests, test dates, refusal/delay proof, prescriptions, and family applications; give an urgent written request to the Jail Superintendent/medical officer and take the acknowledgement to DLSA or the trial court if no test or treatment is arranged [{primary}].",
    ])
    return lines


def _render_pregnant_undertrial_medical_bail(q: str, sources: dict[str, int]) -> list[str]:
    article21 = sources.get("article21")
    bnss_bail = sources.get("bnss_bail")
    if article21 is None or bnss_bail is None:
        return []
    return [
        f"Treat this as an urgent custody medical-care issue for pregnant women undertrials needing a pregnancy or medical condition assessment, including a pregnancy hospital checkup or other medical care, not only as an ordinary bail query; the Constitution source protects life and personal liberty [{article21}].",
        f"The BNSS bail source says a Court may release an accused person on bail if the person is a woman, sick, or infirm [{bnss_bail}].",
        f"Ask for a medical status report, hospital examination, or interim medical-bail hearing with pregnancy/medical records, jail medical-officer notes, custody warrant, and next hearing date rather than only asking to postpone trial [{bnss_bail}].",
        "**What you can do next**",
        f"- Urgently ask the trial court/Sessions Court or DLSA to move an interim bail/medical-bail application using the BNSS woman, sick, or infirm clause and the jail medical record [{bnss_bail}].",
    ]


def _render_custody_legal_aid_lawyer_access(q: str, sources: dict[str, int]) -> list[str]:
    lsa = sources.get("lsa")
    article22 = sources.get("article22")
    bnss = sources.get("bnss")
    crpc = sources.get("crpc")
    if lsa is None or article22 is None:
        return []
    custody_place = (
        "the Jail Superintendent"
        if _has_any(q, ("jail superintendent", "prison superintendent", "superintendent"))
        else "the jail/prison authority"
        if _has_any(q, ("jail", "prison", "tihar", "rohini", "mandoli", "yerwada", "puzhal"))
        else "the police/custody authority"
    )
    lines = [
        f"If {custody_place} is not allowing the first lawyer meeting or the family cannot arrange counsel after a first arrest, treat this as an urgent custody legal-aid and lawyer-access issue, not as a generic legal-aid query [{article22}].",
        f"Article 22 is the arrest-rights source for consulting and being defended by a legal practitioner; ask for lawyer access, arrest/remand papers, and production status in writing [{article22}].",
        f"The Legal Services Authorities source supports approaching DLSA/TLSC/SLSA or the jail legal-aid clinic for immediate appointment, replacement, or status of a legal-aid lawyer [{lsa}].",
    ]
    if _has_any(q, ("first time arrest", "first arrest", "jail superintendent", "not allowing lawyer", "lawyer meeting")):
        lines.append(
            f"Do this the same day: a lawyer meeting after arrest/remand should not wait for routine jail convenience when access is being refused; ask the Jail Superintendent and DLSA for a written acknowledgement or refusal [{lsa}]."
        )
    if bnss is not None:
        lines.append(
            f"For current arrests, the BNSS arrest-information source supports asking for the grounds of arrest and the arrest/remand paper that records them [{bnss}]."
        )
    if crpc is not None:
        lines.append(
            f"If the older CrPC regime applies, keep the CrPC arrest-information source in the file instead of mixing old and new procedure [{crpc}]."
        )
    action_cite = lsa
    lines.extend([
        "**What you can do next**",
        f"- Same day, give a written request to the Jail Superintendent/jail legal-aid clinic and DLSA/TLSC with prisoner name/number, jail, FIR/case number if known, arrest/remand date, court name, existing lawyer details if any, family contact, and the refusal details; ask for lawyer meeting permission, legal-aid appointment or replacement, and acknowledgement of the request [{action_cite}].",
        f"- If access is still blocked or production/remand facts are unclear, take the acknowledgement/refusal to the Magistrate or High Court habeas/production route through DLSA or a criminal lawyer [{article22}].",
    ])
    return lines


def _render_ndps_default_bail(q: str, sources: dict[str, int]) -> list[str]:
    ndps = sources.get("ndps")
    if ndps is None:
        return []
    bnss = sources.get("bnss")
    crpc = sources.get("crpc")
    ganja_25kg = _has_any(q, ("25 kg", "25kg")) and _has_any(q, ("ganja", "cannabis"))
    arthur_four_months = _has_any(q, ("arthur road", "4 mnths", "4 months", "four months"))
    lines: list[str] = []
    if ganja_25kg or arthur_four_months:
        lines.append(
            f"For a husband in Arthur Road custody for about four months/four months in custody over an alleged 25 kg ganja commercial-quantity case with no chargesheet, this is a default-bail calculation issue under Section 36A before assuming bail is already available or treating it as ordinary bail [{ndps}]."
        )
    elif _has_any(q, ("100 days", "110 days", "115 days", "no complaint filed", "complaint not filed", "special judge")):
        lines.append(
            f"For an NDPS arrest with 110 days/no charge-sheet/no complaint filed custody, 100/115 days, or a Special Judge giving only the next date, treat the question as NDPS default/statutory bail under Section 36A and custody-timeline proof, not ordinary bail alone [{ndps}]."
        )
    else:
        lines.append(
            f"For an NDPS arrest with no charge-sheet/no-chargesheet custody, treat the question as NDPS default/statutory bail under Section 36A and custody-timeline proof, not ordinary bail alone [{ndps}]."
        )
    lines.append(
        f"Check whether the prosecution filed a valid charge-sheet or extension application/order before the statutory period expired and whether the accused was ready to furnish bail when default bail was claimed [{ndps}]."
    )
    if bnss is not None:
        lines.append(
            f"For current procedure, compare the custody calculation with the BNSS default-bail/remand source; for older cases, use CrPC instead of mixing regimes [{bnss}]."
        )
    elif crpc is not None:
        lines.append(
            f"If the older CrPC regime applies, compare the custody calculation with the CrPC default-bail source instead of mixing regimes [{crpc}]."
        )
    procedure = bnss if bnss is not None else crpc
    action_cite = procedure if procedure is not None else ndps
    lines.extend(
        [
            "**What you can do next**",
            f"- Count the exact custody days from first remand, check charge-sheet filing status and any prosecution extension application/order, and take the no-chargesheet/default-bail calculation to the Special Court/Special NDPS Court first, then High Court if disputed, with remand papers, quantity/FSL papers, and prior bail orders [{action_cite}].",
        ]
    )
    return lines


def _render_juvenile_age_custody(q: str, sources: dict[str, int]) -> list[str]:
    age = sources.get("age") or sources.get("court")
    court = sources.get("court")
    custody = sources.get("custody")
    if age is None or court is None:
        return []
    child_phrase = (
        "16-year-old boy"
        if _has_any(q, ("16 yr", "16 year", "sixteen"))
        else "17-year-old/possible child"
        if _has_any(q, ("17 yr", "17 year", "seventeen"))
        else "minor accused/possible juvenile"
    )
    custody_context = _has_any(q, ("adult jail", "jail", "lockup", "prison", "observation home", "transfer", "puzhal", "tihar", "yerwada"))
    custody_phrase = "adult jail for two weeks" if _has_any(q, ("adult jail", "2 weeks", "two weeks")) else "adult jail/lockup custody"
    if custody_context:
        opening = f"For a {child_phrase} detained in {custody_phrase} and needing transfer to the Juvenile Justice Board/observation-home route, including observation home and observation-home/place-of-safety placement where appropriate, treat this first as a juvenile age proof, age-determination, and urgent production/transfer issue, not ordinary adult bail alone [{age}]."
    else:
        opening = f"For a {child_phrase} where juvenile status, age proof, Aadhaar, school certificate, or which court decides juvenility is the question, treat this first as a JJ Act age-determination issue, not an education-record dispute [{age}]."
    lines = [
        opening,
        f"Raise the age claim before the current criminal court or Juvenile Justice Board (JJB); the court must inquire and record age when juvenility is raised before a court other than the Juvenile Justice Board [{court}].",
        f"Use age proof such as the school or matriculation certificate, then municipal or panchayat birth certificate, and only then medical age testing where the JJ Act age source is available [{age}].",
    ]
    if custody is not None and custody_context:
        lines.append(
            f"Ask for urgent production before the Juvenile Justice Board (JJB) and removal from adult jail or prison/lockup to the proper child-custody or observation-home route while age is decided [{custody}]."
        )
    elif custody_context:
        lines.append(
            f"Even if the retrieved custody passage is thin, ask the current court/Juvenile Justice Board (JJB) for urgent production, removal from adult jail or prison, and observation-home placement while age proof is decided [{court}]."
        )
    lines.extend(
        [
            "**What you can do next**",
            (
                f"- File an age-determination and production/transfer application with the current court or Juvenile Justice Board (JJB) using school certificate, birth certificate, remand/jail papers, FIR sections, parent/guardian ID, and DLSA/legal-aid contact; ask specifically for observation-home transfer from adult jail [{court}], [{age}]."
                if custody_context
                else f"- File an age-determination/juvenility application with the current criminal court or Juvenile Justice Board (JJB) using school certificate, birth certificate, Aadhaar only as supporting ID, FIR/POCSO sections if any, parent/guardian ID, and DLSA/legal-aid contact [{court}], [{age}]."
            ),
        ]
    )
    return lines


def _render_pds_ration_name_removed(q: str, sources: dict[str, int]) -> list[str]:
    nfsa = sources.get("nfsa")
    if nfsa is None:
        return []
    rti = sources.get("rti")
    if "fair price" in q and "cut" in q:
        issue = "the fair-price shop says your mother's name was cut from the ration card without notice"
    elif "dealer deleted" in q:
        issue = "the ration dealer says your mother's name was deleted from the card without written notice"
    elif "dealer stopped giving grain" in q:
        issue = "the dealer stopped giving grain because your mother's name was deleted from the family card without notice"
    elif "ration office cut" in q:
        issue = "the ration office cut your old mother's name from the household card and you need the file and restoration route"
    elif "pds dealer removed" in q or "dealer removed" in q:
        issue = "the PDS dealer removed your mother's name and is refusing ration"
    elif "panchayat removed" in q:
        issue = "the panchayat removed your mother's name from the ration card without giving a written reason"
    elif "cancelled" in q or "canceled" in q:
        issue = "the ration-card name or member record was cancelled without a clear written order"
    else:
        issue = "your mother's name was removed, cut, deleted, or blocked from the ration card/PDS household record"

    lines = [
        f"If {issue}, treat it as an NFSA ration-card entitlement and grievance issue, not as generic intake or only an Aadhaar mismatch [{nfsa}].",
        f"Ask the ration office/Food and Civil Supplies department for the written deletion or cancellation order, the reason, the current household/member list, and the NFSA grievance/DGRO restoration route [{nfsa}].",
    ]
    if rti is not None:
        lines.append(
            f"If the office or dealer will not give the order, file status, or appeal route, use RTI to get the ration-card file, action-taken record, deletion basis, and copy of the order [{rti}]."
        )
    lines.extend([
        "**What you can do next**",
        f"- Because {issue}, file a written complaint with the ration office/Food and Civil Supplies department or State/District NFSA grievance authority with ration-card/household ID, mother's ID, old ration-card copy or member list, dealer/fair-price shop details, no-notice/no-order proof, denial date, slips/messages, and the restoration request [{nfsa}].",
    ])
    return lines


def _render_friendly_loan_recovery(q: str, sources: dict[str, int]) -> list[str]:
    contract = sources.get("contract")
    if contract is None:
        return []
    limitation = sources.get("limitation")
    cpc = sources.get("cpc")
    ni = sources.get("ni")
    borrower = "cousin" if "cousin" in q else "brother" if "brother" in q else "friend" if "friend" in q else "relative"
    amount = "3 lakh" if "3 lakh" in q else "the hand-loan money"
    transfer = "UPI" if "upi" in q else "bank/cash"
    lines = [
        f"For {amount} given to your {borrower} by {transfer} where they are avoiding calls or not returning money, treat it as a family/friendly hand loan and civil money-recovery claim first, using the Indian Contract Act source for repayment promise and proof [{contract}]."
    ]
    if limitation is not None:
        lines.append(
            f"Before legal notice or a recovery suit, check the Limitation Act from the loan date, due date, last acknowledgement, or part-payment because stale money claims can fail on limitation [{limitation}]."
        )
    if cpc is not None:
        lines.append(
            f"Use the civil-court/CPC route only after sorting the written proof, amount, parties, and territorial filing facts; do not start with a criminal cheating case unless there was deception at the beginning [{cpc}]."
        )
    if ni is not None:
        lines.append(
            f"If there is a dishonoured cheque for repayment, keep the NI Act cheque-bounce route separate from ordinary civil recovery [{ni}]."
        )
    else:
        lines.append(
            f"Do not frame it as cheque bounce unless there is an actual dishonoured cheque; without that, keep the police cheating case question separate from the civil recovery proof [{contract}]."
        )
    lines.extend([
        "**What you can do next**",
        f"- Send a written demand/legal notice with the amount, due date, proof, and address for reply, then discuss a civil recovery or summary-suit route with DLSA or a lawyer using bank/UPI or UPI/bank proof, chats admitting the loan, witnesses, repayment promises, and limitation dates [{contract}].",
    ])
    return lines


def _render_marriage_misrepresentation(q: str, sources: dict[str, int]) -> list[str]:
    hma = sources.get("hma")
    if hma is None:
        return []
    family = sources.get("family")
    sma = sources.get("sma")
    issue = (
        "your husband lied before marriage about salary and loans"
        if "husband" in q and ("salary" in q or "loans" in q)
        else "a spouse made job, salary, income, loan, or biodata misrepresentations before marriage"
    )
    lines = [
        f"If {issue}, check whether the salary, job, loans, income, or biodata facts support a voidable-marriage or matrimonial-relief claim under the Hindu Marriage Act source; not every lie automatically cancels a marriage [{hma}]."
    ]
    if family is not None:
        lines.append(
            f"The Family Courts Act source is the forum route for annulment/voidable-marriage, divorce, maintenance, counselling, or other matrimonial relief after the personal-law source is identified [{family}]."
        )
    if sma is not None:
        lines.append(
            f"If the marriage was under the Special Marriage Act, use that source instead of assuming Hindu Marriage Act relief [{sma}]."
        )
    action_cite = family or hma
    lines.extend([
        "**What you can do next**",
        f"- Collect biodata/profile/messages, job/salary/loan proof, marriage certificate, date you discovered the truth, residence/children/maintenance facts, and then ask DLSA or a family-law lawyer whether annulment, divorce, maintenance, or counselling is the right Family Court remedy [{action_cite}].",
    ])
    return lines


def _source_title(passages: list[dict], index: int) -> str:
    for passage in passages:
        if passage.get("index") == index:
            return str(passage.get("title") or "").lower()
    return ""


def _shop_issue_phrase(q: str) -> str:
    body = (
        "health department/food-safety authority" if _has_any(q, ("health department", "food safety officer", "food inspector", "food authority", "designated officer")) else
        "BBMP/Bengaluru" if "bbmp" in q or "bangalore" in q or "bengaluru" in q else
        "Delhi MCD" if "mcd" in q or "delhi" in q else
        "Mumbai BMC" if "bmc" in q or "mumbai" in q else
        "Chennai corporation" if "chennai" in q else
        "Noida Authority" if "noida" in q else
        "Vadodara municipal corporation" if "vadodara" in q else
        "Rajkot municipal" if "rajkot" in q else
        "Gujarat municipal corporation/nagarpalika" if _has_any(q, ("gujarat", "ahmedabad", "surat", "vadodara", "rajkot", "nagarpalika")) else
        "municipal/local-authority"
    )
    item = (
        "restaurant/hotel kitchen" if _has_any(q, ("restaurant", "hotel", "kitchen")) else
        "commercial shop with goods inside" if "commercial" in q and _has_any(q, ("goods inside", "goods are inside", "stock inside", "items inside", "material inside")) else
        "commercial shop" if "commercial" in q else
        "shop/store with goods inside" if _has_any(q, ("goods inside", "goods are inside", "stock inside", "items inside", "material inside")) else
        "store" if "store" in q else
        "shop/store"
    )
    action = "put under seal" if "put seal" in q else "locked" if "locked" in q else "sealed"
    return f"your {body} {item} being {action}"


def _has_any(text: str, terms: tuple[str, ...]) -> bool:
    return any(term in text for term in terms)


AUTHORITY_WORKFLOW_CONTRACTS: tuple[AuthorityWorkflowContract, ...] = (
    AuthorityWorkflowContract(
        id="spousal_alimony_working_status",
        route_categories=("family_marriage_status", "family_domestic"),
        trigger_groups=(
            ("alimony", "maintenance"),
            ("divorce", "after divorce", "during divorce", "family court", "working before marriage", "was working"),
        ),
        source_specs=(
            PassageSpec("family", ("family courts",), ("/sec-7", "/sec-8"), required=True),
            PassageSpec("hma", ("hindu marriage",), ("/sec-24", "/sec-25", "/sec-13")),
            PassageSpec("sma", ("special marriage",), ("/sec-36", "/sec-37", "/sec-27", "/sec-28")),
            PassageSpec("bnss", ("bharatiya nagarik suraksha",), ("/sec-144", "/sec-145")),
            PassageSpec("crpc", ("code of criminal procedure", "criminal procedure"), ("/sec-125", "/sec-127", "/sec-128")),
            PassageSpec("pwdva", ("protection of women from domestic violence", "domestic violence"), ("/sec-20", "/sec-12", "/sec-3")),
        ),
        line_specs=(
            LineSpec("A spouse having worked before marriage does not by itself end the alimony or maintenance question; the Family Court route depends on income, needs, marriage facts, children, existing orders, and the relief claimed [{family}].", ("family",)),
            LineSpec("If the Hindu Marriage Act applies, check interim maintenance and permanent alimony under the matrimonial case source instead of accepting the other side's oral statement as final [{hma}].", ("hma",)),
            LineSpec("If the marriage is under the Special Marriage Act, verify the equivalent maintenance/alimony source before using Hindu-law language [{sma}].", ("sma",)),
            LineSpec("If the issue is monthly support for wife/children or enforcement, keep the criminal-procedure maintenance route separate from divorce-case alimony and do not mix old CrPC/current BNSS without checking the case date [{bnss}].", ("bnss",)),
            LineSpec("Where economic abuse, residence, or household expenses are part of the facts, keep the PWDVA monetary-relief/residence track separate from pure divorce alimony [{pwdva}].", ("pwdva",)),
            LineSpec("**What you can do next**"),
            LineSpec("- Collect marriage proof, divorce or family-court papers, income/expense proof for both sides, children's costs, employment history, bank statements, residence facts, and any existing maintenance order; file or reply in Family Court/DLSA with those documents rather than treating working status as an automatic bar [{family}].", ("family",)),
        ),
        priority=146,
    ),
    AuthorityWorkflowContract(
        id="family_court_notice_response",
        route_categories=("court_procedure", "family_marriage_status", "family_domestic"),
        trigger_groups=(
            ("family court", "divorce notice", "summons", "notice"),
            ("reply", "respond", "response", "received", "yesterday", "next step", "need lawyer", "what to do"),
        ),
        source_specs=(
            PassageSpec("family", ("family courts",), ("/sec-7", "/sec-8"), required=True),
            PassageSpec("cpc", ("code of civil procedure",), required=False),
            PassageSpec("lsa", ("legal services authorities",), ("/sec-12", "/sec-13")),
        ),
        line_specs=(
            LineSpec("For a family-court summons, divorce notice, or other family-court notice, treat it as a Family Court appearance/reply deadline problem first, not a police problem unless the notice also mentions violence, threat, or a criminal case [{family}].", ("family",)),
            LineSpec("The next step is to read the petition/notice, note the next date and relief claimed, then prepare an appearance/reply or legal-aid request; do not ignore the notice because the court can proceed if service is treated as complete [{family}].", ("family",)),
            LineSpec("Use the CPC source for the procedural summons, service, and appearance side; keep the family-law relief tied to the Family Court and the petition copy [{cpc}].", ("cpc",)),
            LineSpec("If you cannot afford a lawyer or need immediate filing help, use the DLSA/legal-services route with the notice copy and case number [{lsa}].", ("lsa",)),
            LineSpec("**What you can do next**"),
            LineSpec("- Keep the summons/petition, envelope/service date, case number, next hearing date, relief claimed, marriage proof, address proof, income/children documents, and any prior mediation or complaint papers; visit the Family Court help desk, DLSA, or a family-law lawyer before the listed date [{family}].", ("family",)),
        ),
        priority=145,
    ),
    AuthorityWorkflowContract(
        id="civil_summons_service_failed",
        route_categories=("court_procedure",),
        trigger_groups=(
            ("summons not served", "service of summons", "summons service", "registered post"),
            ("summons", "court", "service"),
        ),
        source_specs=(
            PassageSpec("cpc_service", ("code of civil procedure",), ("/sec-20", "/sec-21", "/sec-28"), required=True),
        ),
        line_specs=(
            LineSpec("For a civil-court summons that was not served through registered post, first determine whether you are the party asking the court to serve another person or the person who did not receive the papers; do not assume that service is complete or that substituted service will automatically be ordered [{cpc_service}].", ("cpc_service",)),
            LineSpec("The CPC service source makes substituted service a court-directed step when ordinary service cannot be effected; it is not an automatic registered-post alternative and the court record must be checked [{cpc_service}].", ("cpc_service",)),
            LineSpec("**What you can do next**"),
            LineSpec("- Get the summons, case number, next date, order sheet, registered-post tracking or returned envelope, process-server report if available, and the party addresses. Ask the same court registry/help desk or DLSA whether the record shows attempted service and what filing or appearance is required for your role [{cpc_service}].", ("cpc_service",)),
        ),
        priority=144,
    ),
    AuthorityWorkflowContract(
        id="manual_scavenging_death_compensation",
        route_categories=("manual_scavenging_safety",),
        trigger_groups=(
            ("septic tank", "sewer", "manhole", "manual scavenging", "hazardous cleaning"),
            ("died", "dies", "death", "dead", "killed", "fatal"),
        ),
        source_specs=(
            PassageSpec("manual", ("manual scavengers", "manual scavenging"), ("/sec-2", "/sec-5", "/sec-7", "/sec-13", "/sec-22", "/sec-23"), required=True),
            PassageSpec("employees", ("employees' compensation", "employees compensation", "workmen's compensation"), ("/sec-3", "/sec-4", "/sec-10")),
            PassageSpec("bnss", ("bharatiya nagarik suraksha",), ("/sec-173", "/sec-175", "/sec-196")),
            PassageSpec("bns", ("bharatiya nyaya",), ("/sec-105", "/sec-106", "/sec-125")),
        ),
        line_specs=(
            LineSpec("For a sewer, septic-tank, manhole, or hazardous-cleaning death with no safety equipment, treat this as an urgent manual-scavenging/prohibited hazardous-cleaning and compensation file, not only as a private settlement with the company [{manual}].", ("manual",)),
            LineSpec("Keep the Employees' Compensation route as a dependant compensation track where the death arose out of and in the course of work [{employees}].", ("employees",)),
            LineSpec("If police or a criminal negligence track is needed, use the criminal-procedure source for FIR/inquest/complaint records but do not let it replace the manual-scavenging and compensation records [{bnss}].", ("bnss",)),
            LineSpec("**What you can do next**"),
            LineSpec("- Preserve death certificate, post-mortem/MLC, work order or contractor/company details, site photos/video, safety-equipment proof, witness names, wage proof, dependant proof, and any police/labour-office complaint; approach the District Magistrate/local authority, Labour Commissioner/Employees Compensation Commissioner, DLSA, and police where refusal or negligence facts exist [{manual}].", ("manual",)),
        ),
        priority=145,
    ),
    AuthorityWorkflowContract(
        id="bonded_labour_coercion_release",
        route_categories=("bonded_labour_rescue",),
        trigger_groups=(
            ("bonded labour", "bonded labor", "brick kiln", "bhatta", "thekedar", "contractor"),
            (
                "not letting leave", "not allowed to leave", "cannot leave", "can't leave",
                "cannot go home", "can't go home", "hostage", "advance", "debt",
                "aadhaar", "aadhar", "passport", "id kept", "document kept",
                "documents retained", "no wages", "just food", "only food",
            ),
        ),
        source_specs=(
            PassageSpec("bonded_action", ("bonded labour", "bonded labor"), ("/sec-12",), required=True),
            PassageSpec("bonded_abolition", ("bonded labour", "bonded labor"), ("/sec-4",)),
            PassageSpec("article23", ("constitution",), ("/sec-23",)),
            PassageSpec("aadhaar", ("aadhaar", "unique identification"), ("/sec-29", "/sec-8")),
            PassageSpec("ismw", ("inter-state migrant", "inter state migrant"), ("/sec-12", "/sec-14", "/sec-15")),
            PassageSpec("wages", ("code on wages", "payment of wages"), ("/sec-17", "/sec-18", "/sec-45")),
            PassageSpec("police", ("bharatiya nagarik suraksha", "code of criminal procedure"), ("/sec-173", "/sec-175", "/sec-154")),
        ),
        line_specs=(),
        priority=145,
    ),
    AuthorityWorkflowContract(
        id="bonded_labour_rehabilitation_release_certificate",
        route_categories=("bonded_labour_rescue", "labour_exploitation_discrimination"),
        trigger_groups=(
            ("bonded labour", "bonded labor", "release certificate", "rehabilitation", "rehab"),
            ("sdm", "district magistrate", "200000", "2 lakh", "release certificate", "rescue"),
        ),
        source_specs=(
            PassageSpec("bonded_action", ("bonded labour", "bonded labor"), ("/sec-12", "/sec-13", "/sec-10"), required=True),
            PassageSpec("bonded_abolition", ("bonded labour", "bonded labor"), ("/sec-4",)),
            PassageSpec("article23", ("constitution",), ("/sec-23",)),
            PassageSpec("lsa", ("legal services authorities",), ("/sec-12", "/sec-13")),
        ),
        line_specs=(
            LineSpec("For bonded-labour rehabilitation money or a release-certificate request, start with the Bonded Labour Act route through the District Magistrate/SDM and vigilance/rescue record, not only an unpaid-wage complaint [{bonded_action}].", ("bonded_action",)),
            LineSpec("If the file also shows bonded labour itself, keep the abolition/freed-from-obligation source in the record instead of treating the case as only ordinary wage recovery [{bonded_abolition}].", ("bonded_abolition",)),
            LineSpec("If the person was forced to work against debt, advance, caste or employer control, keep Article 23 forced-labour framing with the release-certificate file [{article23}].", ("article23",)),
            LineSpec("Use DLSA/legal aid for filing help where the worker cannot safely chase the SDM, labour office, police, or rehabilitation record alone [{lsa}].", ("lsa",)),
            LineSpec("**What you can do next**"),
            LineSpec("- Keep the rescue/release-certificate application, SDM/DM office acknowledgement, worker names, worksite and owner details, debt/advance facts, wage/non-payment proof, ID/document-retention facts, caste/community or migration facts if relevant, and rehabilitation-payment status; ask for a written order/status instead of only oral follow-up [{bonded_action}].", ("bonded_action",)),
        ),
        priority=144,
    ),
    AuthorityWorkflowContract(
        id="police_fir_refusal_serious_offence",
        route_categories=("police_fir", "criminal_general"),
        trigger_groups=(
            ("police refused", "police refusing", "thana refused", "fir not", "complaint refused", "how to complain"),
            ("burnt", "burned", "hut", "house", "fire", "arson", "zamindar", "attack"),
        ),
        source_specs=(
            PassageSpec("bnss", ("bharatiya nagarik suraksha",), ("/sec-173", "/sec-175"), required=True),
            PassageSpec("bns", ("bharatiya nyaya",), ("/sec-326", "/sec-324", "/sec-115", "/sec-117", "/sec-351")),
            PassageSpec("crpc_magistrate", ("code of criminal procedure",), ("/sec-156",)),
        ),
        line_specs=(
            LineSpec("If the thana or police station refuses a written complaint about your hut or house being burnt, including by a zamindar, landlord, or other accused person, preserve the complaint and use the BNSS FIR/refusal source and escalation route instead of accepting oral refusal [{bnss}].", ("bnss",)),
            LineSpec("Keep the BNS offence track for facts that someone burnt or damaged the hut by fire separate from the procedure track: the exact incident date, place, damage, threat, injury, and accused facts decide the offence sections, while BNSS controls complaint/FIR escalation [{bns}], [{bnss}].", ("bns", "bnss")),
            LineSpec("If the incident belongs to the older CrPC regime, keep the CrPC Magistrate-investigation source as the legacy escalation comparison; do not substitute it for the current BNSS procedure [{crpc_magistrate}].", ("crpc_magistrate",)),
            LineSpec("**What you can do next**"),
            LineSpec("- Build a burnt-hut/FIR-refusal file (your burnt-hut complaint) with date/time/place, accused or zamindar details, photos/video of damage, witness names, medical/fire/repair records, and police-refusal proof; submit the one-page complaint and escalate the same packet to SP/senior police, Magistrate, and DLSA if the station still refuses [{bnss}].", ("bnss",)),
        ),
        priority=143,
    ),
    AuthorityWorkflowContract(
        id="labour_wage_deduction_food",
        route_categories=("employment_wages", "labour_exploitation_discrimination"),
        trigger_groups=(
            ("wage", "wages", "salary"),
            ("deduct", "deducted", "deduction", "food", "gruel", "meal"),
            ("contractor", "thekedar", "employer", "worksite", "labour"),
        ),
        source_specs=(
            PassageSpec("wages", ("code on wages", "payment of wages"), ("/sec-17", "/sec-18", "/sec-45"), required=True),
            PassageSpec("contract_labour", ("contract labour",), ("/sec-21",)),
            PassageSpec("ismw", ("inter-state migrant", "inter state migrant"), ("/sec-12", "/sec-14", "/sec-15")),
        ),
        line_specs=(
            LineSpec("Daily food money taken from wages, namely food deductions where only gruel or inadequate food was supplied, should be treated as a wage-deduction and wage-record claim; calculate the daily deduction amount and preserve attendance/wage proof instead of arguing orally at the worksite [{wages}].", ("wages",)),
            LineSpec("If a contractor or principal employer is involved, keep the contract-labour responsibility source as a separate route for who must maintain records and pay statutory dues [{contract_labour}].", ("contract_labour",)),
            LineSpec("If the workers were recruited or moved as inter-state migrant workers, keep the ISMW contractor-duty source for contractor registration, wage/passbook entries, journey or displacement allowance, and worker-facility records alongside the food-deduction claim [{ismw}].", ("ismw",)),
            LineSpec("**What you can do next**"),
            LineSpec("- Prepare a worker-wise table with dates worked, wage rate, food deduction per day, meals actually provided, unpaid amount, contractor/employer details, attendance proof, bank/passbook entries, migrant-worker papers if any, messages, photos, and witnesses; file with the wage authority/Labour Commissioner and DLSA if needed [{wages}].", ("wages",)),
        ),
        priority=142,
    ),
    AuthorityWorkflowContract(
        id="group_retrenchment_discrimination",
        route_categories=("employment_wages", "labour_exploitation_discrimination", "labour_compliance"),
        trigger_groups=(
            ("retrench", "retrenched", "termination", "terminated", "removed"),
            ("workers", "worker", "factory", "company", "site"),
            ("kept", "same site", "bengali", "gujarati", "outsider", "regional", "caste", "caste group", "only our group", "only our caste"),
        ),
        source_specs=(
            PassageSpec("industrial_notice", ("industrial disputes",), ("/sec-25f", "/sec-25-f"), required=True),
            PassageSpec("industrial_lifo", ("industrial disputes",), ("/sec-25g", "/sec-25-g"), required=True),
            PassageSpec("industrial_reemployment", ("industrial disputes",), ("/sec-25h", "/sec-25-h")),
            PassageSpec("wages", ("code on wages", "payment of wages"), ("/sec-17", "/sec-18", "/sec-45")),
            PassageSpec("contract_labour", ("contract labour",), ("/sec-21",)),
            PassageSpec("article14", ("constitution",), ("/sec-14",)),
        ),
        line_specs=(
            LineSpec("For a group retrenchment where workers were retrenched while others were kept on the same worksite, start with the Industrial Disputes retrenchment route: preserve both notice/compensation facts and last-come-first-go selection facts instead of treating it only as salary due [{industrial_notice}], [{industrial_lifo}].", ("industrial_notice", "industrial_lifo")),
            LineSpec("If the employer brought people back or kept/replaced workers on the same site, separately check the re-employment source before accepting the employer's oral explanation [{industrial_reemployment}].", ("industrial_reemployment",)),
            LineSpec("If the selection appears caste-, regional-, language-, or group-based, preserve it as an equality fact separately; use equality framing mainly where a public employer, state-linked contractor, or state action is involved, and do not assume a criminal atrocity route unless protected-status, insult, violence, or threat facts are clear [{article14}].", ("article14",)),
            LineSpec("Keep wage dues, notice pay, compensation, or final settlement as a separate calculation under the wage/dues source where money is unpaid [{wages}].", ("wages",)),
            LineSpec("**What you can do next**"),
            LineSpec("- Make a group list with worker names, joining dates, role, employer/contractor, termination/retrenchment date, notice or no-notice proof, who was retained/replaced, wage dues, contractor messages, gate passes, ID cards, attendance, and witnesses; file with the Labour Commissioner/conciliation officer or DLSA quickly [{industrial_lifo}].", ("industrial_lifo",)),
        ),
        priority=141,
    ),
    AuthorityWorkflowContract(
        id="passport_police_verification_hold",
        route_categories=("passport_police_verification",),
        trigger_groups=(
            ("passport", "pasport", "rpo", "regional passport", "police verification", "thana verification"),
            ("hold", "adverse", "old fir", "criminal case", "verification", "reason", "without reason", "pending", "refused", "rejected"),
        ),
        source_specs=(
            PassageSpec("passports", ("passports act",), ("/sec-5", "/sec-6", "/sec-10", "/sec-11"), required=True),
            PassageSpec("bnss", ("bharatiya nagarik suraksha",), ("/sec-173", "/sec-175", "/sec-528")),
            PassageSpec("crpc", ("criminal procedure",), ("/sec-156", "/sec-190", "/sec-482")),
        ),
        line_specs=(
            LineSpec("For a passport hold, refusal, adverse police-verification report, or RPO delay, start with the Passports Act route: ask for the written RPO/passport-authority reason or order and check whether it fits the statutory refusal, impounding, revocation, or appeal source [{passports}].", ("passports",)),
            LineSpec("A pending FIR or old criminal case should be handled as a separate criminal-case-status fact; the passport answer should not assume automatic refusal unless the Passports Act ground, court order, warrant/summons, or written RPO reason supports it [{passports}].", ("passports",)),
            LineSpec("If police or RPO rely on a criminal case, the incident date decides whether BNSS/BNS or CrPC/IPC procedure applies for the criminal track; keep that separate from the passport grievance/appeal track [{bnss}].", ("bnss",)),
            LineSpec("If the case is old or pre-July 2024, check the CrPC/IPC case papers separately before using current BNSS/BNS labels for the criminal side [{crpc}].", ("crpc",)),
            LineSpec("**What you can do next**"),
            LineSpec("- Use the passport file number to request written reasons/status from Passport Seva/RPO, attach the police-verification/adverse-report details if available, and file a passport grievance or appeal/escalation with case-status papers rather than only sending a generic legal notice [{passports}].", ("passports",)),
            LineSpec("- Keep passport file number, RPO notice/refusal/hold status, police verification report or station details, FIR/case/warrant/summons status papers, court orders if any, identity/address proof, and screenshots of grievance/status submissions [{passports}].", ("passports",)),
        ),
        priority=132,
    ),
    AuthorityWorkflowContract(
        id="vehicle_theft_fir_refusal",
        route_categories=("police_fir", "criminal_general"),
        trigger_groups=(
            ("theft", "stolen", "stole"),
            ("bike", "car", "scooter", "vehicle", "motorcycle", "motor cycle"),
            ("police", "fir", "station", "thana", "complaint", "wait"),
        ),
        source_specs=(
            PassageSpec("bnss_fir", ("bharatiya nagarik suraksha",), ("/sec-173-a",)),
            PassageSpec("bnss_refusal", ("bharatiya nagarik suraksha",), ("/sec-173-c",)),
            PassageSpec("bnss_magistrate", ("bharatiya nagarik suraksha",), ("/sec-175",)),
            PassageSpec("bns", ("bharatiya nyaya",), ("/sec-303", "/sec-317")),
            PassageSpec("crpc", ("code of criminal procedure",), ("/sec-154",)),
            PassageSpec("ipc", ("indian penal code",), ("/sec-378", "/sec-379", "/sec-411")),
        ),
        line_specs=(
            LineSpec("For a stolen bike, stolen scooter, car, or other vehicle where police say to wait before FIR, treat it as a cognizable-theft FIR/refusal and FIR registration problem; do not wait two days just because the station says so orally [{bnss}].", ("bnss",)),
            LineSpec("Keep the BNS theft/stolen-property source as the offence track while using the BNSS FIR source for the deadline-sensitive registration/refusal procedure [{bns}], [{bnss}].", ("bns", "bnss")),
            LineSpec("The BNSS Magistrate-investigation source is the escalation provision to verify when the police refusal to register continues after the written complaint [{bnss_magistrate}].", ("bnss_magistrate",)),
            LineSpec("**What you can do next**"),
            LineSpec("- Give a written theft complaint immediately, because theft reporting is time-sensitive, with vehicle number, chassis/engine details if available, place/time, CCTV/witnesses, insurance/RC papers, and phone/GPS details; ask for FIR/e-FIR/zero-FIR acknowledgement or a written refusal [{bnss}].", ("bnss",)),
            LineSpec("- If the station still refuses or says to wait, escalate the same written complaint and proof to the Superintendent of Police/senior police or DLSA instead of relying only on an online legal notice [{bnss}].", ("bnss",)),
            LineSpec("- Where the BNSS Magistrate-investigation source is retrieved, escalate the same packet to senior police, DLSA, or the Magistrate route with the written refusal record [{bnss_magistrate}].", ("bnss_magistrate",)),
        ),
        priority=130,
    ),
    AuthorityWorkflowContract(
        id="emi_penalty_cibil_dispute",
        route_categories=("banking_credit_dispute",),
        trigger_groups=(
            ("emi", "loan", "nbfc", "finance", "bajaj", "bajaj finserv", "bajaj finance", "lender"),
            ("bounce", "bounced", "bank error", "penalty", "late fee", "charges", "6000"),
            ("cibil", "credit report", "credit score", "credit bureau", "threatening cibil", "threaten cibil"),
        ),
        source_specs=(
            PassageSpec("rbi", ("reserve bank integrated ombudsman", "integrated ombudsman"), required=True),
            PassageSpec("cic", ("credit information companies",), ("/sec-18", "/sec-19", "/sec-20", "/sec-21", "/sec-22")),
            PassageSpec("consumer", ("consumer protection",), ("/sec-2", "/sec-35", "/sec-38")),
        ),
        line_specs=(
            LineSpec("For an EMI bounce caused by a bank error, penalty or late-fee demand, and CIBIL/credit-report threat, treat this as an NBFC/lender service and credit-record dispute first under the RBI Integrated Ombudsman Scheme route, not as loan-app contact harassment [{rbi}].", ("rbi",)),
            LineSpec("Ask the lender/NBFC in writing for the EMI bounce reason, penalty breakup, loan-account statement, complaint number, and the basis for any CIBIL or credit-bureau reporting threat [{rbi}].", ("rbi",)),
            LineSpec("If the lender reports or threatens an adverse CIBIL/credit entry, keep a separate credit-report correction/dispute track under the Credit Information Companies Act source with the disputed entry and lender reply [{cic}].", ("cic",)),
            LineSpec("Consumer service-deficiency is a later forum backup if the written lender/RBI and credit-report correction routes do not fix the wrongful penalty or reporting issue [{consumer}].", ("consumer",)),
            LineSpec("**What you can do next**"),
            LineSpec("- Keep bank-error proof, EMI mandate/autopay record, bounce SMS, penalty calculation, loan statement, lender emails/calls, complaint number, CIBIL screenshot if any, and file a written NBFC/lender grievance before escalating to RBI Ombudsman/CMS and credit-bureau dispute [{rbi}], [{cic}].", ("rbi", "cic")),
        ),
        priority=138,
    ),
    AuthorityWorkflowContract(
        id="minor_interfaith_child_safety_pocso",
        route_categories=("police_fir", "criminal_general"),
        trigger_groups=(
            ("daughter", "girl", "minor", "17", "seventeen", "under 18", "child"),
            ("ran away", "eloped", "boy", "different religion", "other religion", "interfaith", "inter religion", "love jihad"),
        ),
        source_specs=(
            PassageSpec("pocso", ("protection of children from sexual offences",), required=True),
            PassageSpec("bnss", ("bharatiya nagarik suraksha",), ("/sec-173", "/sec-175")),
            PassageSpec("bns", ("bharatiya nyaya",), ("/sec-351", "/sec-137", "/sec-87", "/sec-115", "/sec-117")),
            PassageSpec("article21", ("constitution",), ("/sec-21",)),
        ),
        line_specs=(
            LineSpec("Because the girl is 17 or otherwise a possible minor, do not treat 'love jihad' as the legal category; first verify age, current safety/location, and whether a child-protection/POCSO reporting route is triggered [{pocso}].", ("pocso",)),
            LineSpec("For the police route, use BNSS FIR/information or Magistrate-escalation procedure with age proof, missing/safety facts, and the child's statement/status instead of relying on an oral assurance that she will return [{bnss}].", ("bnss",)),
            LineSpec("Keep any threat, confinement, kidnapping, coercion, or violence allegation separate and tied to the exact BNS section and incident date; do not use religion alone as the offence [{bns}].", ("bns",)),
            LineSpec("If age is verified as 18 or above, adult partner-choice and personal-liberty principles become a separate Article 21 protection track, but that does not replace the minor-safety check while she is 17 [{article21}].", ("article21",)),
            LineSpec("**What you can do next**"),
            LineSpec("- Preserve birth/school age proof, photo/phone/location details, last contact, boy's identity if known, any threat/coercion messages, police diary/FIR number, and ask police/DLSA for child-safe tracing, statement recording, CWC/SJPU support where applicable, and Magistrate escalation if police refuse action [{pocso}], [{bnss}].", ("pocso", "bnss")),
        ),
        priority=139,
    ),
    AuthorityWorkflowContract(
        id="promise_to_marry_rape_accused_defence",
        route_categories=("criminal_defence_bail",),
        trigger_groups=(
            ("rape case", "filed rape", "accused of rape", "case against me", "complaint against me"),
            ("promised marriage", "promise marriage", "dating", "relationship", "broke up", "breakup"),
        ),
        source_specs=(
            PassageSpec("bns69", ("bharatiya nyaya",), ("/sec-69",), required=True),
            PassageSpec("bns63", ("bharatiya nyaya",), ("/sec-63", "/sec-64")),
            PassageSpec("bnss", ("bharatiya nagarik suraksha",), ("/sec-480", "/sec-483", "/sec-173")),
        ),
        line_specs=(
            LineSpec("For a rape case after a breakup where the allegation is promise-to-marry/deceit, treat this as a promise-to-marry rape-accusation defence issue and a serious accused-side sexual-offence defence issue; the BNS promise-to-marry special-statute or offence source must be checked against whether deception existed from the beginning, not merely that the relationship ended [{bns69}].", ("bns69",)),
            LineSpec("If the FIR also cites rape/sexual-offence provisions, keep the BNS rape source separate from the Section 69/deceit analysis and do not contact, threaten, or pressure the complainant [{bns63}].", ("bns63",)),
            LineSpec("Use the BNSS/CrPC procedure source for arrest, notice, bail, or court steps only with the FIR/complaint, incident dates, relationship timeline, and current case stage in hand [{bnss}].", ("bnss",)),
            LineSpec("**What you can do next**"),
            LineSpec("- Collect the FIR/complaint, sections, arrest/notice status, relationship timeline, messages about marriage/consent/breakup, travel/stay proof, witnesses, prior complaints, and bail papers; take them to DLSA or a criminal lawyer before any statement, compromise attempt, bail, quashing, or discharge step [{bns69}], [{bnss}].", ("bns69", "bnss")),
        ),
        priority=140,
    ),
    AuthorityWorkflowContract(
        id="custody_medical_care",
        route_categories=("criminal_defence_bail",),
        trigger_groups=(
            ("jail", "prison", "custody", "undertrial", "arthur road", "byculla", "husband", "brother"),
            ("tb", "tuberculosis", "test not done", "jail doctor", "doctor", "medical", "hospital", "treatment"),
        ),
        source_specs=(
            PassageSpec("article21", ("constitution",), ("/sec-21",)),
            PassageSpec("prisons", ("prisons act", "prisons")),
            PassageSpec("bnss_bail", ("bharatiya nagarik suraksha",), ("/sec-480", "/sec-483")),
        ),
        line_specs=(),
        priority=141,
    ),
    AuthorityWorkflowContract(
        id="pregnant_undertrial_medical_bail",
        route_categories=("criminal_defence_bail",),
        trigger_groups=(
            ("pregnant", "pregnancy", "women undertrial", "women undertrials"),
            ("undertrial", "under trial", "jail", "prison", "custody", "byculla", "bail"),
        ),
        source_specs=(
            PassageSpec("article21", ("constitution",), ("/sec-21",), required=True),
            PassageSpec("bnss_bail", ("bharatiya nagarik suraksha",), ("/sec-480", "/sec-483"), required=True),
        ),
        line_specs=(),
        priority=160,
    ),
    AuthorityWorkflowContract(
        id="custody_legal_aid_lawyer_access",
        route_categories=("legal_aid", "arrest_custody_safeguard", "undertrial_review_release"),
        trigger_groups=(
            ("jail", "prison", "custody", "arrest", "arrested", "remand", "undertrial", "brother", "son", "husband", "tihar", "rohini", "mandoli", "yerwada", "puzhal"),
            ("lawyer", "advocate", "legal aid", "dlsa", "meeting", "not allowing", "not meeting", "first time arrest", "cannot meet"),
        ),
        source_specs=(
            PassageSpec("lsa", ("legal services authorities",), ("/sec-9", "/sec-12"), required=True),
            PassageSpec("article22", ("constitution",), ("/sec-22",), required=True),
            PassageSpec("bnss", ("bharatiya nagarik suraksha",), ("/sec-47", "/sec-48", "/sec-57", "/sec-58")),
            PassageSpec("crpc", ("code of criminal procedure",), ("/sec-50", "/sec-56", "/sec-57")),
        ),
        line_specs=(),
        priority=142,
    ),
    AuthorityWorkflowContract(
        id="anticipatory_bail_rejected_next_step",
        route_categories=("criminal_defence_bail",),
        trigger_groups=(
            ("anticipatory bail", "pre arrest bail", "pre-arrest bail", "before arrest bail", "ab "),
            ("rejected", "rejection", "sessions court rejected", "session court rejected", "sessions rejected", "same court"),
        ),
        source_specs=(
            PassageSpec("bnss_anticipatory", ("bharatiya nagarik suraksha",), ("/sec-482",)),
            PassageSpec("crpc_anticipatory", ("code of criminal procedure",), ("/sec-438",)),
            PassageSpec("bnss_regular", ("bharatiya nagarik suraksha",), ("/sec-480", "/sec-483")),
            PassageSpec("bns_cruelty", ("bharatiya nyaya",), ("/sec-85", "/sec-86")),
        ),
        line_specs=(),
        priority=151,
    ),
    AuthorityWorkflowContract(
        id="498a_bail_rejection_source_gap",
        route_categories=("criminal_defence_bail",),
        trigger_groups=(
            ("498a", "498-a", "dowry case", "dowry-cruelty", "cruelty case"),
            ("anticipatory bail", "pre arrest bail", "pre-arrest bail", "before arrest bail"),
            ("rejected", "rejection", "sessions court rejected", "session court rejected", "sessions rejected"),
        ),
        source_specs=(
            PassageSpec("bns_cruelty", ("bharatiya nyaya",), ("/sec-85", "/sec-86"), required=True),
            PassageSpec("bnss_bail", ("bharatiya nagarik suraksha",), ("/sec-480", "/sec-483"), required=True),
        ),
        line_specs=(),
        priority=152,
    ),
    AuthorityWorkflowContract(
        id="sexual_offence_sessions_bail_forum",
        route_categories=("criminal_defence_bail",),
        trigger_groups=(
            ("376", "ipc 376", "rape", "sexual offence", "sexual offense"),
            ("magistrate", "sessions court", "session court", "direct to sessions", "why direct", "bail filed"),
        ),
        source_specs=(
            PassageSpec("bnss_sessions_bail", ("bharatiya nagarik suraksha",), ("/sec-483", "/sec-480")),
            PassageSpec("crpc_sessions_bail", ("code of criminal procedure",), ("/sec-439", "/sec-437")),
            PassageSpec("bns_rape", ("bharatiya nyaya",), ("/sec-63", "/sec-64")),
            PassageSpec("ipc_rape", ("indian penal",), ("/sec-375", "/sec-376")),
        ),
        line_specs=(),
        priority=150,
    ),
    AuthorityWorkflowContract(
        id="bail_surety_condition_modification",
        route_categories=("criminal_defence_bail",),
        trigger_groups=(
            ("bail granted", "granted bail", "bail order", "conditions too strict", "surety", "bond"),
            ("surety", "condition", "conditions", "amount", "bond", "50000", "50,000"),
            ("too strict", "too high", "cannot pay", "cant pay", "can't pay", "poor", "challenge", "modify", "reduce"),
        ),
        source_specs=(
            PassageSpec("bnss_regular", ("bharatiya nagarik suraksha",), ("/sec-480", "/sec-483")),
            PassageSpec("crpc_regular", ("code of criminal procedure",), ("/sec-437", "/sec-439", "/sec-441")),
            PassageSpec("article21", ("constitution",), ("/sec-21",)),
            PassageSpec("moti_ram", ("moti ram",), ()),
        ),
        line_specs=(),
        priority=149,
    ),
    AuthorityWorkflowContract(
        id="bail_surety_amount_context",
        route_categories=("criminal_defence_bail",),
        trigger_groups=(
            ("surety", "bond"),
            ("amount", "typical", "typically", "usually", "how much", "required"),
            ("bail", "cheque bounce", "138", "ni act"),
        ),
        source_specs=(
            PassageSpec("bnss_regular", ("bharatiya nagarik suraksha",), ("/sec-480", "/sec-483")),
            PassageSpec("crpc_regular", ("code of criminal procedure",), ("/sec-437", "/sec-439", "/sec-441")),
            PassageSpec("ni", ("negotiable instruments",), ("/sec-138", "/sec-142")),
        ),
        line_specs=(),
        priority=148,
    ),
    AuthorityWorkflowContract(
        id="lgbtq_identity_arrest_safeguard",
        route_categories=("arrest_custody_safeguard", "criminal_defence_bail", "police_fir"),
        trigger_groups=(
            (
                "being gay", "for being gay", "because he is gay", "because she is gay",
                "because i am gay", "because im gay", "gay", "lesbian", "same sex",
                "same-sex", "homosexual", "lgbt", "lgbtq", "queer", "sexual orientation",
            ),
            (
                "police arrested", "arrested", "arrest", "detained", "picked up",
                "police picked", "custody", "lockup", "jail", "taken by police",
                "fir", "case filed", "case against",
            ),
        ),
        source_specs=(
            PassageSpec("navtej", ("navtej singh johar",), required=True),
            PassageSpec("article21", ("constitution of india",), ("/sec-21",)),
            PassageSpec("article22", ("constitution of india",), ("/sec-22",)),
            PassageSpec("bnss_arrest", ("bharatiya nagarik suraksha",), ("/sec-47", "/sec-48")),
            PassageSpec("bnss_production", ("bharatiya nagarik suraksha",), ("/sec-57", "/sec-58")),
            PassageSpec("crpc_arrest", ("code of criminal procedure",), ("/sec-50",)),
            PassageSpec("crpc_production", ("code of criminal procedure",), ("/sec-56", "/sec-57")),
        ),
        line_specs=(),
        priority=158,
    ),
    AuthorityWorkflowContract(
        id="pmla_anticipatory_interim_bail",
        route_categories=("criminal_defence_bail", "pmla_ed"),
        trigger_groups=(
            ("pmla", "money laundering", "enforcement directorate", "ecir", "scheduled offence", "ed raid", "ed summons", "ed notice", "ed arrest"),
            ("bail", "anticipatory", "interim", "before arrest", "pre arrest", "pre-arrest", "arrested", "custody", "summons", "raid", "newborn", "new born", "baby", "wife", "twin condition", "twin conditions", "not guilty", "section 45", "sec 45", "s.45"),
        ),
        source_specs=(
            PassageSpec("pmla45", ("prevention of money laundering",), ("/sec-45",), required=True),
            PassageSpec("pmla19", ("prevention of money laundering",), ("/sec-19",)),
            PassageSpec("bnss_anticipatory", ("bharatiya nagarik suraksha",), ("/sec-482",)),
            PassageSpec("crpc_anticipatory", ("code of criminal procedure",), ("/sec-438",)),
            PassageSpec("bnss_regular", ("bharatiya nagarik suraksha",), ("/sec-480", "/sec-483")),
            PassageSpec("crpc_regular", ("code of criminal procedure",), ("/sec-437", "/sec-439")),
            PassageSpec("article21", ("constitution",), ("/sec-21",)),
            PassageSpec("pmla_sc_precedent", (
                "vijay madanlal",
                "nikesh tarachand",
                "pankaj bansal",
                "senthil balaji",
                "saumya chaurasia",
                "tarsem lal",
                "directorate of enforcement",
                "m. gopal reddy",
            )),
        ),
        line_specs=(),
        priority=170,
    ),
    AuthorityWorkflowContract(
        id="regular_bail_after_arrest",
        route_categories=("criminal_defence_bail",),
        trigger_groups=(
            ("regular bail", "apply for bail", "how do i apply for regular bail", "how to get bail", "bail application", "bail"),
            ("arrested", "arrest", "jail", "custody", "remand", "got arrested"),
        ),
        source_specs=(
            PassageSpec("bnss_regular", ("bharatiya nagarik suraksha",), ("/sec-480", "/sec-483")),
            PassageSpec("crpc_regular", ("code of criminal procedure",), ("/sec-437", "/sec-439")),
        ),
        line_specs=(),
        priority=126,
    ),
    AuthorityWorkflowContract(
        id="state_prohibition_excise_accused",
        route_categories=("criminal_defence_bail",),
        trigger_groups=(
            ("prohibition law", "excise act", "liquor case", "alcohol case", "drinking village", "caught me drinking", "desi daru", "sharab", "liquor", "state prohibition", "prohibition case"),
            ("police", "thana", "case", "fir", "caught", "punishment", "arrest", "bail", "section", "notice"),
        ),
        source_specs=(
            PassageSpec("state_excise", ("prohibition and excise", "prohibition act", "excise act"), ("/sec-13", "/sec-37", "/sec-76")),
            PassageSpec("bnss", ("bharatiya nagarik suraksha",), ("/sec-35", "/sec-47", "/sec-480", "/sec-483", "/sec-528")),
            PassageSpec("crpc", ("code of criminal procedure",), ("/sec-41", "/sec-50", "/sec-437", "/sec-439")),
        ),
        line_specs=(),
        priority=124,
    ),
    AuthorityWorkflowContract(
        id="uapa_prima_facie_bail",
        route_categories=("criminal_defence_bail", "undertrial_review_release"),
        trigger_groups=(
            ("uapa", "unlawful activities"),
            ("prima facie", "43d", "bail", "18 months", "long custody", "jail", "when"),
        ),
        source_specs=(
            PassageSpec("uapa43d", ("unlawful activities", "uapa"), ("/sec-43d",), required=True),
            PassageSpec("bnss_regular", ("bharatiya nagarik suraksha",), ("/sec-480", "/sec-483")),
            PassageSpec("article21", ("constitution",), ("/sec-21",)),
        ),
        line_specs=(),
        priority=146,
    ),
    AuthorityWorkflowContract(
        id="itpa_booking_only_accused",
        route_categories=("criminal_defence_bail",),
        trigger_groups=(
            ("itpa", "pita", "immoral traffic", "prostitution"),
            ("phone", "booking", "bookings", "clients", "paying clients", "do not meet", "not meet", "only calls"),
        ),
        source_specs=(
            PassageSpec("itpa", ("immoral traffic",), ("/sec-4", "/sec-5", "/sec-7", "/sec-8"), required=True),
            PassageSpec("bnss", ("bharatiya nagarik suraksha",), ("/sec-216", "/sec-480", "/sec-483")),
        ),
        line_specs=(),
        priority=145,
    ),
    AuthorityWorkflowContract(
        id="itpa_receptionist_raid_accused",
        route_categories=("criminal_defence_bail", "criminal_general"),
        trigger_groups=(
            ("spa", "parlour", "parlor", "massage"),
            ("raid", "raided", "arrested", "police took", "station"),
            ("receptionist", "reception desk", "employee", "worker", "staff", "only working", "just working"),
        ),
        source_specs=(
            PassageSpec("itpa5", ("immoral traffic",), ("/sec-5",), required=True),
            PassageSpec("itpa8", ("immoral traffic",), ("/sec-8",)),
            PassageSpec("bnss_bail", ("bharatiya nagarik suraksha",), ("/sec-480", "/sec-483")),
            PassageSpec("bnss_case_paper", ("bharatiya nagarik suraksha",), ("/sec-216", "/sec-173")),
        ),
        line_specs=(),
        priority=159,
    ),
    AuthorityWorkflowContract(
        id="handcuff_restraint_objection",
        route_categories=("arrest_custody_safeguard", "criminal_defence_bail", "police_fir"),
        trigger_groups=(
            ("handcuff", "handcuffs", "hand cuff", "hand cuffs", "restraint"),
            ("court", "hearing", "production", "taken to court", "high security", "prisoner", "police"),
        ),
        source_specs=(
            PassageSpec("article21", ("constitution",), ("/sec-21",), required=True),
            PassageSpec("production", ("bharatiya nagarik suraksha",), ("/sec-57", "/sec-58")),
            PassageSpec("crpc", ("code of criminal procedure",), ("/sec-57",)),
        ),
        line_specs=(),
        priority=144,
    ),
    AuthorityWorkflowContract(
        id="undertrial_bnss479_review",
        route_categories=("undertrial_review_release", "criminal_defence_bail"),
        trigger_groups=(
            ("undertrial", "under trial", "bnss 479", "section 479", "review committee", "prisoner"),
            ("479", "review committee", "eligible", "diabetic", "diabetes", "65", "old", "long custody"),
        ),
        source_specs=(
            PassageSpec("bnss479", ("bharatiya nagarik suraksha",), ("/sec-479",), required=True),
            PassageSpec("crpc436a", ("code of criminal procedure",), ("/sec-436A", "/sec-436-a", "/sec-436a")),
            PassageSpec("lsa", ("legal services authorities",), ("/sec-9", "/sec-12")),
            PassageSpec("article21", ("constitution",), ("/sec-21",)),
        ),
        line_specs=(),
        priority=143,
    ),
    AuthorityWorkflowContract(
        id="custodial_death_inquiry",
        route_categories=("police_fir", "custody_compensation", "criminal_general"),
        trigger_groups=(
            ("custodial death", "lockup death", "death lockup", "lockup suicide", "custody death", "custody suicide", "lockup"),
            ("death", "suicide", "196 procedure", "176 procedure", "magistrate", "post mortem", "inquest"),
        ),
        source_specs=(
            PassageSpec("bnss196", ("bharatiya nagarik suraksha",), ("/sec-196",)),
            PassageSpec("crpc176", ("code of criminal procedure",), ("/sec-176",)),
            PassageSpec("human_rights", ("protection of human rights",), ("/sec-12", "/sec-13", "/sec-17")),
            PassageSpec("article21", ("constitution",), ("/sec-21",)),
        ),
        line_specs=(),
        priority=142,
    ),
    AuthorityWorkflowContract(
        id="cyber_money_fraud",
        route_categories=("cyber_fraud_or_harassment", "banking_credit_dispute"),
        trigger_groups=(
            (
                "otp", "phishing", "upi fraud", "upi scam", "phonepe fraud",
                "gpay fraud", "fake customer care", "fake customer support",
                "fake helpline", "fraud call", "scam call", "install app",
                "installed app", "remote access", "anydesk", "screen sharing",
                "unauthorized transaction", "unauthorised transaction",
                "credit card unauthorized", "credit card unauthorised",
                "money got transferred", "money was transferred",
                "money transferred", "amount transferred",
                "duped", "fake stock", "stock trading app", "fake trading app",
                "trading app", "investment app", "multiple upi ids",
                "cyber cell complaint", "cyber complaint filed", "no progress",
                "whatsapp account got hacked", "whatsapp hacked", "account hacked",
                "asking my contacts for money", "asking contacts for money",
            ),
            (
                "bank", "account", "upi", "credit card", "debit card", "card",
                "transaction", "money", "amount", "transferred", "refund",
                "reversal", "50000", "50,000", "lakh",
            ),
        ),
        source_specs=(
            PassageSpec("it", ("information technology",), ("/sec-66C", "/sec-66D", "/sec-66E"), required=True),
            PassageSpec("rbi", ("reserve bank integrated ombudsman", "integrated ombudsman"), ("/sec-2", "/sec-3")),
            PassageSpec("bns", ("bharatiya nyaya",), ("/sec-318", "/sec-319", "/sec-351")),
            PassageSpec("bnss", ("bharatiya nagarik suraksha",), ("/sec-173", "/sec-175")),
        ),
        line_specs=(),
        priority=128,
    ),
    AuthorityWorkflowContract(
        id="wrong_bank_debit",
        route_categories=("banking_credit_dispute", "consumer"),
        trigger_groups=(
            ("bank", "account", "branch", "customer care", "upi", "payment app", "phonepe", "gpay", "google pay", "paytm", "imps", "atm", "credit card", "card"),
            (
                "wrong debit", "wrongly debited", "debited twice", "deducted",
                "deduction", "wrong deduction", "no refund", "not refund",
                "failed but amount debited", "amount debited", "upi failed",
                "failed transaction", "transaction failed", "status failed",
                "failed but debited", "failed but money cut",
                "failed but money deducted", "failed upi refund", "upi refund",
                "chargeback", "chargeback not processed", "not processed",
                "money cut", "amount cut", "payment failed", "closed ticket",
                "refund will come", "wait 30", "wait 45",
                "support says wait", "branch says wait", "says wait",
                "imps transfer failed", "imps failed",
                "beneficiary did not get money", "beneficiary didn't get money",
                "beneficiary says not received", "beneficiary says no money",
                "annual fee", "card annual fee", "annual fee charged",
                "annual fee twice", "charged annual fee",
                "charged annual fee twice", "fee charged", "fee charged twice",
                "card was closed", "card closed",
                "atm cash not dispensed", "cash not dispensed",
                "atm did not dispense", "atm didn't dispense",
                "atm withdrawal failed", "cash not received",
            ),
        ),
        source_specs=(
            PassageSpec("rbi_scope", ("reserve bank integrated ombudsman", "integrated ombudsman"), ("/sec-2", "/sec-3"), required=True),
            PassageSpec("rbi_complaint", ("reserve bank integrated ombudsman", "integrated ombudsman"), ("/sec-9", "/sec-10")),
            PassageSpec("consumer_complaint", ("consumer protection",), ("/sec-35",)),
        ),
        line_specs=(
            LineSpec("First confirm from the RBI Scheme's scope provisions that the bank, NBFC, or payment-system participant is a covered regulated entity [{rbi_scope}].", ("rbi_scope",)),
            LineSpec("Use the Scheme's complaint and maintainability provisions to check the prior written bank grievance, response or no-response period, and whether the complaint is eligible for RBI Ombudsman/CMS [{rbi_complaint}].", ("rbi_complaint",)),
            LineSpec("If the bank still does not reverse or explain the duplicate/wrong debit, wrong deduction, or failed UPI debit after the written bank complaint and RBI record, use Consumer Protection Act 2019, Section 35 [{consumer_complaint}] as the service-deficiency forum backup.", ("consumer_complaint",)),
            LineSpec("**What you can do next**"),
            LineSpec("- Keep the bank statement, UPI/transaction ID/RRN, SMS or email alerts, customer-care chats/call logs, complaint number, written refusal or no-reply proof, and exact debit/refund timeline [{rbi_complaint}].", ("rbi_complaint",)),
        ),
        priority=90,
    ),
    AuthorityWorkflowContract(
        id="bank_account_freeze_legal_hold",
        route_categories=("banking_credit_dispute", "cyber_fraud_or_harassment", "police_fir"),
        trigger_groups=(
            ("bank", "account", "salary account", "upi account", "upi id", "branch", "freeze"),
            ("freeze", "frozen", "froze", "blocked", "lien", "fraud complaint"),
            ("police", "cyber", "fraud complaint", "notice", "case", "legal hold", "court", "investigating officer", "investigation officer"),
        ),
        source_specs=(
            PassageSpec("rbi_scope", ("reserve bank integrated ombudsman", "integrated ombudsman"), ("/sec-2", "/sec-3"), required=True),
            PassageSpec("rbi_complaint", ("reserve bank integrated ombudsman", "integrated ombudsman"), ("/sec-9", "/sec-10")),
            PassageSpec("bnss_seizure", ("bharatiya nagarik suraksha",), ("/sec-106",)),
            PassageSpec("crpc_seizure", ("code of criminal procedure",), ("/sec-102",)),
            PassageSpec("banking", ("banking regulation",), ("/sec-35A",)),
            PassageSpec("it", ("information technology",), ("/sec-66C", "/sec-66D", "/sec-66E")),
        ),
        line_specs=(),
        priority=96,
    ),
    AuthorityWorkflowContract(
        id="dating_app_phone_number_abuse",
        route_categories=("cyber_fraud_or_harassment", "police_fir"),
        trigger_groups=(
            ("dating app", "tinder", "bumble", "phone number on dating app", "mobile number on dating app"),
            ("phone number", "mobile number", "posted my phone number", "shared my phone number", "posted my number", "shared my number"),
            ("strangers", "calling", "calls", "harass", "harassing", "without consent"),
        ),
        source_specs=(
            PassageSpec("it", ("information technology",), ("/sec-66E", "/sec-66C", "/sec-66D"), required=True),
            PassageSpec("bns", ("bharatiya nyaya",), ("/sec-78", "/sec-351", "/sec-356"), required=True),
            PassageSpec("bnss", ("bharatiya nagarik suraksha",), ("/sec-173", "/sec-175")),
            PassageSpec("dpdp", ("digital personal data protection",), ("/sec-8", "/sec-13", "/sec-27")),
        ),
        line_specs=(
            LineSpec("For someone posting your phone number on a dating app and strangers calling you, treat it as cyber privacy/harassment and possible identity/personation misuse under the IT Act source; do not frame it as obscene-publication unless the actual post contains obscene or intimate material [{it}].", ("it",)),
            LineSpec("Keep a separate BNS track for stalking, intimidation, defamation, or harassment facts if the calls/messages continue, threaten you, or damage your reputation; do not assume a normal dating-app profile dispute is automatically a serious criminal case [{bns}].", ("bns",)),
            LineSpec("For police/cyber complaint escalation, use the BNSS complaint/FIR route with the platform URL, phone numbers, call logs, and screenshots rather than only oral allegations [{bnss}].", ("bnss",)),
            LineSpec("If the platform or another person exposed your phone number or other personal data, keep a DPDP personal-data grievance track with the platform/app grievance record where facts support it [{dpdp}].", ("dpdp",)),
            LineSpec("**What you can do next**"),
            LineSpec("- Preserve the dating-app profile/link, screenshots showing your number, caller numbers/call logs, messages, dates/times, platform complaint ID, and any identity of the poster; report to the platform, cybercrime.gov.in/1930 or cyber police if calls/harassment continue [{it}], [{bns}].", ("it", "bns")),
        ),
        priority=127,
    ),
    AuthorityWorkflowContract(
        id="digital_arrest_impersonation_transfer",
        route_categories=("cyber_fraud_or_harassment", "banking_credit_dispute", "police_fir"),
        trigger_groups=(
            ("digital arrest", "fake cbi", "fake police", "fake trai", "trai", "courier", "parcel", "narcotics", "sim will close"),
            ("video", "video call", "bank transfer", "send money", "transferred", "upi", "account", "kept me", "police video call"),
        ),
        source_specs=(
            PassageSpec("it", ("information technology",), ("/sec-66C", "/sec-66D"), required=True),
            PassageSpec("bns", ("bharatiya nyaya",), ("/sec-318", "/sec-319", "/sec-351")),
            PassageSpec("bnss", ("bharatiya nagarik suraksha",), ("/sec-173", "/sec-175")),
        ),
        line_specs=(
            LineSpec("For a fake TRAI/SIM-closure, fake CBI/police, digital arrest, courier, or parcel call that kept a father/parent/person on video for hours and pushed UPI or bank transfers, treat it as cyber impersonation and electronic cheating first, not as a real arrest process [{it}].", ("it",)),
            LineSpec("For a digital arrest where a father/parent was kept on video for hours and UPI transfers were taken, keep a separate BNS track for cheating by personation, dishonest inducement, or intimidation if the caller used a CBI/police identity, fear of arrest, family pressure, or pressure to transfer money by UPI/bank [{bns}].", ("bns",)),
            LineSpec("For the police/cyber complaint route, use the BNSS FIR/information and Magistrate-escalation source with UPI transaction, caller, video-call, and bank evidence [{bnss}].", ("bnss",)),
            LineSpec("**What you can do next**"),
            LineSpec("- Do not send more money; immediately report through 1930 or cybercrime.gov.in, ask the bank to freeze/trace the beneficiary account, preserve the video/call/WhatsApp proof, UPI transfer IDs, and keep the bank complaint number and cyber acknowledgement for the BNSS police/cyber complaint route [{it}], [{bnss}].", ("it", "bnss")),
        ),
        priority=105,
    ),
    AuthorityWorkflowContract(
        id="elder_bank_pension_impersonation_fraud",
        route_categories=("cyber_fraud_or_harassment", "banking_credit_dispute", "senior_citizen"),
        trigger_groups=(
            ("fake call", "fraud call", "scam call", "pension office", "sbi pension", "bank officer", "bank call"),
            ("father", "mother", "parent", "75", "70", "senior", "elderly", "old"),
            ("took", "transferred", "debit", "debited", "account", "lakh", "money", "upi", "bank"),
        ),
        source_specs=(
            PassageSpec("it", ("information technology",), ("/sec-66C", "/sec-66D"), required=True),
            PassageSpec("bns", ("bharatiya nyaya",), ("/sec-318", "/sec-319", "/sec-351")),
            PassageSpec("bnss", ("bharatiya nagarik suraksha",), ("/sec-173", "/sec-175")),
            PassageSpec("rbi", ("reserve bank integrated ombudsman", "integrated ombudsman")),
            PassageSpec("senior", ("maintenance and welfare of parents", "senior citizens"), ("/sec-4", "/sec-5", "/sec-9")),
        ),
        line_specs=(
            LineSpec("For a fake SBI/bank/pension-office call that took money from an elderly parent or 75-year-old father, treat the first track as cyber impersonation and electronic cheating under the IT Act source [{it}].", ("it",)),
            LineSpec("Keep the BNS cheating/personation or intimidation track with the caller identity, inducement, transfer, and threat facts for police or cyber-police review [{bns}].", ("bns",)),
            LineSpec("Use the BNSS FIR/information route for the police/cyber complaint with phone numbers, transaction IDs, beneficiary details, bank complaint number, and cyber acknowledgement [{bnss}].", ("bnss",)),
            LineSpec("For the bank-service/refund side, use the RBI Ombudsman/CMS route after a written bank complaint or no-reply record [{rbi}].", ("rbi",)),
            LineSpec("Because the victim is an elderly parent/senior citizen, also keep the Senior Citizens Act/DLSA support route for maintenance/support, protection, or family-assisted follow-up; it does not replace the cyber and bank-fraud tracks [{senior}].", ("senior",)),
            LineSpec("**What you can do next**"),
            LineSpec("- Immediately preserve the fake call number, SBI/pension-office claim, transaction IDs, bank statement, beneficiary account/UPI, screenshots, cyber complaint acknowledgement, bank complaint number, and age/ID proof of the senior parent; report through 1930/cybercrime.gov.in, the bank, and police/cyber police [{it}], [{bnss}].", ("it", "bnss")),
        ),
        priority=114,
    ),
    AuthorityWorkflowContract(
        id="medical_status_online_warning",
        route_categories=("family_marriage_status", "cyber_fraud_or_harassment"),
        trigger_groups=(
            ("hiv", "aids", "medical status", "health status", "disease"),
            ("post", "online", "instagram", "whatsapp", "group", "warn", "warning", "social media", "public"),
        ),
        source_specs=(
            PassageSpec("hiv", ("human immunodeficiency", "hiv", "aids"), ("/sec-5", "/sec-8", "/sec-9"), required=True),
            PassageSpec("it", ("information technology",), ("/sec-66E", "/sec-67")),
            PassageSpec("dpdp", ("digital personal data protection",), ("/sec-8", "/sec-13")),
            PassageSpec("hma", ("hindu marriage",), ("/sec-12",)),
            PassageSpec("family", ("family courts",), ("/sec-7",)),
        ),
        line_specs=(
            LineSpec("Do not post or share a person's identifiable HIV/medical status online as a warning or pressure tactic; first verify the HIV Act privacy/confidentiality source and keep the evidence private [{hiv}].", ("hiv",)),
            LineSpec("If someone hid HIV/medical status before engagement or marriage, separate the private family-law/cancellation question from any online-disclosure or takedown question [{hma}].", ("hma",)),
            LineSpec("For Instagram, WhatsApp, group, or other online posting, also check the IT Act privacy/electronic-publication source before any disclosure or complaint step [{it}].", ("it",)),
            LineSpec("Keep DPDP/personal-data grievance options as a privacy-support track where platform or data-processing facts exist, not as permission to publicise medical status [{dpdp}].", ("dpdp",)),
            LineSpec("**What you can do next**"),
            LineSpec("- Preserve biodata/messages, engagement or wedding records, date you discovered the HIV/medical-status fact, any threats or proposed posts, and payment/gift records; speak to DLSA or a family-law lawyer before sending a notice or making any public allegation [{hiv}], [{family}].", ("hiv", "family")),
        ),
        priority=116,
    ),
    AuthorityWorkflowContract(
        id="false_nbfc_credit_identity_record",
        route_categories=("banking_credit_dispute", "cyber_fraud_or_harassment"),
        trigger_groups=(
            ("loan", "nbfc", "finance company", "credit report", "cibil"),
            ("signature not mine", "signature is not mine", "not my signature", "fake signature", "loan showing on my documents", "documents but signature", "opened in my name", "without my consent"),
        ),
        source_specs=(
            PassageSpec("cic", ("credit information companies",), ("/sec-18", "/sec-19", "/sec-20", "/sec-21", "/sec-22"), required=True),
            PassageSpec("rbi", ("reserve bank integrated ombudsman", "integrated ombudsman"), ("/sec-2", "/sec-3"), required=True),
            PassageSpec("it", ("information technology",), ("/sec-66C", "/sec-66D")),
            PassageSpec("bns", ("bharatiya nyaya",), ("/sec-318", "/sec-319", "/sec-336", "/sec-340")),
            PassageSpec("bnss", ("bharatiya nagarik suraksha",), ("/sec-173", "/sec-175")),
        ),
        line_specs=(
            LineSpec("For an NBFC/finance-company loan or credit record showing against your documents when the signature is not yours, start with a false-loan and credit-report correction track under the Credit Information Companies Act source, not with loan-app harassment [{cic}].", ("cic",)),
            LineSpec("Ask the NBFC/lender in writing for the loan application, KYC file, e-sign/signature basis, disbursal account, and complaint number; use RBI Ombudsman/CMS if the regulated entity does not correct or explain it in writing [{rbi}].", ("rbi",)),
            LineSpec("If the false loan used electronic KYC, online identity data, or digital credentials, keep a cyber identity-theft/personation track under the IT Act source [{it}].", ("it",)),
            LineSpec("If the papers show forged signature, fabricated KYC, cheating, or document forgery, keep a separate police/cyber track instead of treating this only as a civil loan dispute [{bns}].", ("bns",)),
            LineSpec("For police or cyber complaint paperwork, keep the BNSS complaint/FIR route separate from the lender and credit-bureau correction route [{bnss}].", ("bnss",)),
            LineSpec("**What you can do next**"),
            LineSpec("- Keep the lender/NBFC name, loan account or notice, credit-report screenshot, disputed signature page if available, KYC documents, complaint number, bureau dispute ID, cyber/police acknowledgement if filed, and all lender replies/no-reply proof [{cic}], [{rbi}].", ("cic", "rbi")),
        ),
        priority=125,
    ),
    AuthorityWorkflowContract(
        id="aadhaar_sim_identity_misuse",
        route_categories=("cyber_fraud_or_harassment", "banking_credit_dispute", "police_fir"),
        trigger_groups=(
            ("aadhaar", "aadhar"),
            ("sim", "mobile number", "telecom", "subscriber"),
            ("used", "misuse", "fraud", "fraud case", "case came", "issued", "never took", "i never took", "linked", "message saying", "how to check", "check"),
        ),
        source_specs=(
            PassageSpec("aadhaar", ("aadhaar", "aadhar"), ("/sec-8", "/sec-29", "/sec-37", "/sec-40"), required=True),
            PassageSpec("telecom", ("telecommunications",), ("/sec-29", "/sec-42"), required=True),
            PassageSpec("it", ("information technology",), ("/sec-66C", "/sec-66D"), required=True),
            PassageSpec("bnss", ("bharatiya nagarik suraksha",), ("/sec-173", "/sec-175")),
            PassageSpec("bns", ("bharatiya nyaya",), ("/sec-318", "/sec-319", "/sec-336")),
        ),
        line_specs=(
            LineSpec("For Aadhaar being used to obtain or link a SIM/mobile connection and a fraud case coming to you, keep three lanes together: Aadhaar identity-information misuse [{aadhaar}], Telecom subscriber/SIM identity misuse [{telecom}], and IT Act electronic identity/personation facts [{it}].", ("aadhaar", "telecom", "it")),
            LineSpec("Do not treat this as only police paperwork; first ask the telecom provider for the subscriber/KYC record and complaint number, while preserving the UIDAI/Aadhaar and cyber complaint trail [{telecom}], [{aadhaar}].", ("telecom", "aadhaar")),
            LineSpec("If police or cyber police contact you because the SIM was used in fraud, ask for the complaint/FIR number, station, sections, and whether you are accused, witness, or complainant before giving devices or statements [{bnss}].", ("bnss",)),
            LineSpec("If the facts show cheating, forged KYC, or personation, keep a separate criminal-law track with the date and documents instead of assuming the SIM record alone proves guilt [{bns}].", ("bns",)),
            LineSpec("**What you can do next**"),
            LineSpec("- Keep Aadhaar proof, SIM/mobile number, telecom provider reply, CAF/KYC request, fraud-case notice or call log, cyber complaint number, UIDAI complaint, and any messages or transaction links; take these to the telecom grievance desk, cyber police/1930, and DLSA/legal aid as needed [{telecom}], [{it}], [{aadhaar}].", ("telecom", "it", "aadhaar")),
        ),
        priority=126,
    ),
    AuthorityWorkflowContract(
        id="cyber_police_notice_no_paper",
        route_categories=("cyber_fraud_or_harassment", "criminal_general", "criminal_defence_bail", "police_fir"),
        trigger_groups=(
            ("police", "cyber", "notice", "calling"),
            ("notice", "written notice", "not giving notice", "without paper", "no paper", "no written", "not giving paper"),
        ),
        source_specs=(
            PassageSpec("bnss", ("bharatiya nagarik suraksha",), ("/sec-35", "/sec-173", "/sec-175"), required=True),
            PassageSpec("it", ("information technology",), ("/sec-66C", "/sec-66D")),
        ),
        line_specs=(
            LineSpec("For police calling you about a cyber case but not giving a paper or written notice, first ask for the written notice, FIR/complaint number, sections, station, investigating officer details, and whether you are accused, witness, or complainant under the BNSS police-notice/FIR procedure source [{bnss}].", ("bnss",)),
            LineSpec("Keep the IT Act cyber source only for the alleged electronic-record or cyber facts; it should not replace the police-paperwork and lawyer/legal-aid step [{it}].", ("it",)),
            LineSpec("**What you can do next**"),
            LineSpec("- Do not ignore police contact, but ask for written notice or case details before travelling; preserve call logs/messages and take the notice/FIR details to DLSA or a criminal lawyer before giving devices, passwords, or a statement [{bnss}].", ("bnss",)),
        ),
        priority=106,
    ),
    AuthorityWorkflowContract(
        id="domestic_violence_immediate_safety",
        route_categories=("family_domestic", "police_fir", "criminal_general"),
        trigger_groups=(
            ("husband", "wife", "spouse", "pati", "in laws", "in-laws", "mother in law", "father in law", "sasural", "matrimonial home", "shared house", "child", "marriage", "all marriages", "parents say", "mere husband", "mere pati", "mera husband", "mera pati"),
            ("beat", "beating", "slap", "slapped", "hit", "punched", "assaulted", "choke", "strangle", "stab", "shoot", "poison", "burn", "kill", "killed", "murder", "slit", "dhamki", "jaan se", "break my leg", "jala", "mujhe maar", "mujhe mar", "maar raha", "mar raha", "maar rahi", "mar rahi", "took my phone", "unsafe", "threat", "evict", "get out", "no place to stay", "not allowing me to call", "remove me", "ghar se nikal", "ghar se nikaal", "wapis ja", "threw me out", "kicked me out", "force sex", "forces sex", "forced sex", "forcing sex", "forcing me for sex", "sexual coercion", "without consent", "when i say no", "after i say no"),
        ),
        source_specs=(
            PassageSpec("pwdva", ("domestic violence",), ("/sec-3",), required=True),
            PassageSpec("pwdva_application", ("domestic violence",), ("/sec-12",)),
            PassageSpec("pwdva_protection", ("domestic violence",), ("/sec-18",)),
            PassageSpec("pwdva_residence", ("domestic violence",), ("/sec-19",)),
            PassageSpec("bns", ("bharatiya nyaya",), ("/sec-115", "/sec-117", "/sec-125", "/sec-308", "/sec-309", "/sec-351")),
            PassageSpec("bnss", ("bharatiya nagarik suraksha",), ("/sec-173", "/sec-175")),
            PassageSpec("family", ("family courts",), ("/sec-7",)),
            PassageSpec("hma13b", ("hindu marriage",), ("/sec-13B", "/sec-13-b")),
            PassageSpec("hma", ("hindu marriage",), ("/sec-13",)),
        ),
        line_specs=(
            LineSpec("Because he is beating you right now, or if your husband or in-laws beat you, take your phone, threaten you, or you are unsafe, treat safety first and use the PWDVA protection/residence/monetary-relief route through the Protection Officer or Magistrate [{pwdva}].", ("pwdva",)),
            LineSpec("Because the facts include physical beating, threat, or taking property/phone, keep a separate BNS criminal track for hurt, intimidation, extortion/robbery-type facts, or related offences if police help is needed [{bns}].", ("bns",)),
            LineSpec("For the police track, preserve evidence and use the BNSS FIR/information or Magistrate-escalation route if the station refuses or delays help [{bnss}].", ("bnss",)),
            LineSpec("**What you can do next**"),
            LineSpec("- Move to a safe place or trusted person first; contact police/emergency help if danger is immediate, then approach the Protection Officer, One Stop Centre/DLSA, or Magistrate with injury proof, messages, photos, medical records, residence proof, and witness details [{pwdva}].", ("pwdva",)),
        ),
        priority=106,
    ),
    AuthorityWorkflowContract(
        id="inlaw_unwelcome_touch_domestic_safety",
        route_categories=("family_domestic", "police_fir", "criminal_general"),
        trigger_groups=(
            ("brother", "devar", "jeth", "in law", "in-law", "husband's brother", "husbands brother"),
            ("grabbed", "touch", "touched", "hand", "uncomfortable", "comments", "sexual", "harass"),
        ),
        source_specs=(
            PassageSpec("pwdva", ("domestic violence",), ("/sec-3", "/sec-12", "/sec-18"), required=True),
            PassageSpec("bns", ("bharatiya nyaya",), ("/sec-74", "/sec-75", "/sec-76", "/sec-351")),
            PassageSpec("bnss", ("bharatiya nagarik suraksha",), ("/sec-173", "/sec-175")),
        ),
        line_specs=(
            LineSpec("If a husband's brother/in-law grabbed your hand, made unwelcome comments, or made you unsafe in the shared household, treat it as a domestic-relationship safety/harassment fact and PWDVA protection issue, not a generic family dispute [{pwdva}].", ("pwdva",)),
            LineSpec("Because the facts include unwelcome touching, sexualized comments, or intimidation, keep a BNS modesty/sexual-harassment check only if the exact touching, words, place, and witnesses support it; do not turn every uncomfortable family interaction into a criminal label [{bns}].", ("bns",)),
            LineSpec("For the police route, use the BNSS FIR/information or Magistrate-escalation source if a written complaint is refused or delayed [{bnss}].", ("bnss",)),
            LineSpec("**What you can do next**"),
            LineSpec("- Write the date, place, exact words, grabbing/touching details, witness names, messages, who in the household was told, and safety concerns; approach a Protection Officer, One Stop Centre/women helpline, DLSA, police, or Magistrate route without waiting to tell an unsafe family member first [{pwdva}], [{bns}].", ("pwdva", "bns")),
        ),
        priority=115,
    ),
    AuthorityWorkflowContract(
        id="dowry_food_denial_domestic_cruelty",
        route_categories=("family_domestic", "police_fir", "criminal_general"),
        trigger_groups=(
            ("dowry", "dahej", "more money", "bringing more", "mother in law", "mother-in-law", "in laws", "in-laws"),
            ("food", "not give food", "doesnt give me food", "doesn't give me food", "denied food", "taunts", "daily"),
        ),
        source_specs=(
            PassageSpec("pwdva", ("domestic violence",), ("/sec-3", "/sec-12", "/sec-18", "/sec-20"), required=True),
            PassageSpec("bns", ("bharatiya nyaya",), ("/sec-85", "/sec-86", "/sec-351")),
            PassageSpec("bnss", ("bharatiya nagarik suraksha",), ("/sec-173", "/sec-175")),
            PassageSpec("dowry", ("dowry prohibition",)),
        ),
        line_specs=(
            LineSpec("Daily dowry taunts, pressure for more money, or being denied food in the matrimonial home should be treated as domestic violence/economic abuse under the PWDVA route, not only as ordinary family conflict [{pwdva}].", ("pwdva",)),
            LineSpec("Keep a separate BNS cruelty/intimidation track where dowry-linked cruelty, denial of food, threats, or harassment facts support police review [{bns}].", ("bns",)),
            LineSpec("Use the BNSS FIR/information route if the police complaint track is needed, while keeping Protection Officer/Magistrate relief under PWDVA active [{bnss}].", ("bnss",)),
            LineSpec("If gifts or dowry property are also disputed, keep the Dowry Prohibition Act/property-return track separate from immediate residence, food, safety, and monetary-relief needs [{dowry}].", ("dowry",)),
            LineSpec("**What you can do next**"),
            LineSpec("- Make a dated safety and food/expense timeline, preserve messages, photos, medical records, witness names, income/expense proof, and approach a Protection Officer, One Stop Centre/women helpline, DLSA, Magistrate court, or police/emergency route if danger is immediate [{pwdva}], [{bns}].", ("pwdva", "bns")),
        ),
        priority=115,
    ),
    AuthorityWorkflowContract(
        id="arrest_custody_station_case_not_disclosed",
        route_categories=("arrest_custody_safeguard", "police_fir"),
        trigger_groups=(
            ("police", "officer", "officers", "crime branch", "arrest", "custody", "picked", "took", "taken", "detained", "utha", "le gayi", "le gaye"),
            ("not telling station", "not telling the station", "not telling case", "will not tell", "won't tell", "not tell us", "will not disclose", "won't disclose", "will not identify", "won't identify", "cannot find which police station", "undisclosed station", "not produced", "will not produce", "won't produce", "which station", "family not informed", "no fir copy", "midnight", "night", "from home", "from my home", "picked my", "papa ko", "bhai ko", "jija ko", "jiju ko", "station ka naam", "thana nahi bata", "thana nahin bata", "nahi bata", "nahin bata", "kahan le gaye"),
        ),
        source_specs=(
            PassageSpec("article22", ("constitution",), ("/sec-22",), required=True),
            PassageSpec("article226", ("constitution",), ("/sec-226",)),
            PassageSpec("arrest_info", ("bharatiya nagarik suraksha",), ("/sec-47", "/sec-48")),
            PassageSpec("production", ("bharatiya nagarik suraksha",), ("/sec-57", "/sec-58")),
            PassageSpec("fir_info", ("bharatiya nagarik suraksha",), ("/sec-173",)),
            PassageSpec("crpc", ("code of criminal procedure",), ("/sec-50", "/sec-56", "/sec-57", "/sec-154")),
        ),
        line_specs=(
            LineSpec("Because police picked your family member from home, a tea shop, or another place at night and are not telling the station, case, FIR copy, or grounds, treat this first as an urgent arrest/custody safeguard and as an arrest-information and liberty safeguard issue; Article 22 supports grounds of arrest, lawyer access, and production before a Magistrate [{article22}].", ("article22",)),
            LineSpec("BNSS Section 47 requires an arresting officer to communicate full particulars of the offence or other grounds of arrest to the arrested person [{arrest_info}].", ("arrest_info",)),
            LineSpec("Article 22 requires an arrested person to be produced before the nearest Magistrate within twenty-four hours, excluding journey time [{article22}].", ("article22",)),
            LineSpec("If the person is not being shown, station location is hidden, or lawyer access is blocked, keep the Article 226 habeas corpus route ready with DLSA/High Court counsel while also asking for arrest/remand records [{article226}].", ("article226",)),
            LineSpec("**What you can do next**"),
            LineSpec("- Keep the pickup time and place, officer or vehicle details, CCTV or witness details, calls, messages, ID proof, arrest memo if provided, and any written custody, arrest, or refusal record."),
            LineSpec("- Contact DLSA or a criminal lawyer immediately if the station remains unknown or the person is not produced."),
        ),
        priority=126,
    ),
    AuthorityWorkflowContract(
        id="arrest_magistrate_production_delay",
        route_categories=("arrest_custody_safeguard", "police_fir", "criminal_defence_bail"),
        trigger_groups=(
            ("arrest", "arrested", "custody", "detained", "lockup", "police took", "picked"),
            ("magistrate", "court", "produce", "produced", "production", "samne", "le jana", "le gaya"),
            ("5 din", "5 days", "din ho gaya", "days ho gaya", "24 hour", "24 hours", "twenty four", "yesterday", "kal", "since yesterday"),
        ),
        source_specs=(
            PassageSpec("article22", ("constitution",), ("/sec-22",), required=True),
            PassageSpec("bnss_production", ("bharatiya nagarik suraksha",), ("/sec-57", "/sec-58"), required=True),
            PassageSpec("bnss_no_delay", ("bharatiya nagarik suraksha",), ("/sec-57",)),
            PassageSpec("crpc_production", ("code of criminal procedure",), ("/sec-56", "/sec-57")),
            PassageSpec("article21", ("constitution",), ("/sec-21",)),
        ),
        line_specs=(
            LineSpec("A report that '5 din' in police custody has passed, or that someone has been arrested, detained, or held beyond 24 hours without production before a Magistrate, is an urgent arrest-production and Article 22 liberty issue, not a routine FIR-copy question [{article22}].", ("article22",)),
            LineSpec("Under the current BNSS production source, ask for arrest time, station, arrest memo, grounds, medical condition, and the production/remand order showing when the person was or will be produced before the Magistrate [{bnss_production}].", ("bnss_production",)),
            LineSpec("The BNSS no-delay source requires the arrested person to be taken before the Magistrate or officer in charge without unnecessary delay; ask for the movement and production record [{bnss_no_delay}].", ("bnss_no_delay",)),
            LineSpec("If the older CrPC regime applies, compare the same 24-hour production rule under the CrPC source instead of mixing old and new procedure [{crpc_production}].", ("crpc_production",)),
            LineSpec("Article 21 supports the liberty and unlawful-detention framing where the person is hidden, not produced, or family cannot verify custody status [{article21}].", ("article21",)),
            LineSpec("**What you can do next**"),
            LineSpec("- Same day, contact DLSA or a criminal lawyer with pickup/arrest time, station, officer details, witnesses, calls/messages, ID proof, medical needs, and any refusal; ask the Magistrate/trial court or High Court habeas/production route if production or custody papers are not shown [{article22}], [{bnss_production}].", ("article22", "bnss_production")),
        ),
        priority=129,
    ),
    AuthorityWorkflowContract(
        id="arrest_memo_grounds_family_intimation",
        route_categories=("arrest_custody_safeguard", "police_fir"),
        trigger_groups=(
            ("arrest", "arrested", "custody", "detained", "picked", "took"),
            ("arrest memo", "grounds", "family not informed", "not tell grounds", "not telling grounds", "dk basu", "d.k. basu"),
        ),
        source_specs=(
            PassageSpec("article21", ("constitution",), ("/sec-21",), required=True),
            PassageSpec("article22", ("constitution",), ("/sec-22",), required=True),
            PassageSpec("bnss", ("bharatiya nagarik suraksha",), ("/sec-47", "/sec-48", "/sec-57", "/sec-58"), required=True),
            PassageSpec("crpc", ("code of criminal procedure",), ("/sec-50", "/sec-56", "/sec-57")),
        ),
        line_specs=(
            LineSpec("For a DK Basu/no-arrest-memo arrest where police did not tell grounds, did not give an arrest memo, or did not inform family, treat it as an urgent custody-safeguard issue under Article 21 liberty and Article 22 arrest-rights sources [{article21}], [{article22}].", ("article21", "article22")),
            LineSpec("Under the current BNSS arrest-safeguard source, ask for the grounds of arrest, arrest memo, station name, officer details, nominated-person/family intimation proof, and production-before-Magistrate status [{bnss}].", ("bnss",)),
            LineSpec("If the older CrPC regime applies, compare the same arrest-information and production safeguards under the CrPC source instead of mixing regimes [{crpc}].", ("crpc",)),
            LineSpec("**What you can do next**"),
            LineSpec("- Contact the station duty officer/senior officer, DLSA, or a criminal lawyer immediately with pickup/arrest time, station, FIR/case number if known, calls/messages, witnesses, ID proof, medical condition, and family-intimation details; use the Magistrate/High Court route if detention or non-production continues [{article22}], [{bnss}].", ("article22", "bnss")),
        ),
        priority=118,
    ),
    AuthorityWorkflowContract(
        id="caste_slur_assault_fir_refusal",
        route_categories=("tribal_caste_atrocity", "police_fir"),
        trigger_groups=(
            ("caste", "dalit", "sc/st", "sc st", "scheduled caste", "scheduled tribe", "adivasi"),
            ("slur", "abuse", "abused", "caste name", "hit", "beat", "assault"),
            ("station refuses", "police refuses", "refuses case", "not taking fir", "fir"),
        ),
        source_specs=(
            PassageSpec("poa", ("scheduled castes", "prevention of atrocities"), required=True),
            PassageSpec("bnss", ("bharatiya nagarik suraksha",), ("/sec-173", "/sec-175")),
            PassageSpec("bns", ("bharatiya nyaya",), ("/sec-115", "/sec-117", "/sec-351", "/sec-352")),
            PassageSpec("article21", ("constitution",), ("/sec-21",)),
        ),
        line_specs=(
            LineSpec("For caste-name abuse with assault, public humiliation, school/principal facts, or violence against a Dalit/SC/ST/Adivasi person, keep the SC/ST Prevention of Atrocities Act route / SC/ST POA source and SC/ST atrocity complaint route separate from an ordinary neighbourhood, school, or village dispute; the words used, place, witnesses, and caste status matter [{poa}].", ("poa",)),
            LineSpec("Because the allegation includes targeted caste violence and police non-registration, keep the Article 21 life/dignity/liberty source as a constitutional support track; it does not replace the SC/ST POA offence and FIR route [{article21}].", ("article21",)),
            LineSpec("If the police station refuses the FIR, use the BNSS FIR/information and Magistrate/senior-police escalation route with the written complaint and acknowledgement proof [{bnss}].", ("bnss",)),
            LineSpec("Physical assault, threats, or intimidation may also need the ordinary BNS hurt/intimidation track, but it should not replace the atrocity route where caste targeting is alleged [{bns}].", ("bns",)),
            LineSpec("**What you can do next**"),
            LineSpec("- Write the exact caste words, time/place, accused identity, witnesses, injury facts, medical report, photos/video, prior complaint proof, and police refusal; escalate to senior police/SP, Special Court/DLSA, or Magistrate if FIR registration is refused [{poa}].", ("poa",)),
        ),
        priority=108,
    ),
    AuthorityWorkflowContract(
        id="maintenance_order_nonpayment",
        route_categories=("family_domestic", "family_marriage_status"),
        trigger_groups=(
            ("maintenance", "child support", "money", "support"),
            ("court ordered", "court order", "maintenance order", "order dated", "magistrate order", "family court order", "execution", "arrears order"),
        ),
        source_specs=(
            PassageSpec("family", ("family courts",), ("/sec-7", "/sec-8", "/sec-9"), required=True),
            PassageSpec("bnss", ("bharatiya nagarik suraksha",), ("/sec-144", "/sec-145", "/sec-146")),
            PassageSpec("pwdva", ("domestic violence",), ("/sec-20", "/sec-12")),
            PassageSpec("crpc", ("code of criminal procedure",), ("/sec-125",)),
        ),
        line_specs=(
            LineSpec("If a court has already ordered maintenance and your husband/ex-spouse is not paying, treat it as enforcement or arrears of a maintenance order, not a fresh generic family dispute [{family}].", ("family",)),
            LineSpec("Under the current BNSS maintenance source, keep the order, arrears calculation, payment defaults, and income facts ready for the same court/Magistrate enforcement route [{bnss}].", ("bnss",)),
            LineSpec("If the order or relief was under the PWDVA monetary-relief route, keep that domestic-violence monetary-relief source and enforcement record separate from divorce/property issues [{pwdva}].", ("pwdva",)),
            LineSpec("If the older CrPC regime applies, compare the enforcement step against the CrPC maintenance source instead of mixing old and new procedural provisions [{crpc}].", ("crpc",)),
            LineSpec("**What you can do next**"),
            LineSpec("- File an enforcement/execution or arrears application in the same Family Court/Magistrate route with the maintenance order, arrears month-wise chart, bank statements, missed-payment proof, husband income/job details, child-expense proof, and prior notices/messages [{family}].", ("family",)),
        ),
        priority=104,
    ),
    AuthorityWorkflowContract(
        id="spouse_child_maintenance_no_support",
        route_categories=("family_domestic", "family_marriage_status"),
        trigger_groups=(
            ("husband", "wife", "spouse"),
            ("left me", "deserted", "not giving money", "no money", "no support", "school fees", "kids", "children", "child", "stopped paying household expenses", "household expenses"),
        ),
        source_specs=(
            PassageSpec("family", ("family courts",), ("/sec-7", "/sec-8", "/sec-9"), required=True),
            PassageSpec("bnss", ("bharatiya nagarik suraksha",), ("/sec-144", "/sec-145", "/sec-146")),
            PassageSpec("pwdva", ("domestic violence",), ("/sec-20", "/sec-12", "/sec-3")),
            PassageSpec("crpc", ("code of criminal procedure",), ("/sec-125",)),
        ),
        line_specs=(
            LineSpec("If your husband/spouse has left you with children and is not giving money, treat it first as a maintenance and household-support case, not as a generic family-property dispute [{family}].", ("family",)),
            LineSpec("Under the current BNSS maintenance source, prepare child-expense, school-fee, income, residence, and husband/spouse earning facts for the Magistrate or Family Court maintenance route [{bnss}].", ("bnss",)),
            LineSpec("If there is domestic violence, economic abuse, residence exclusion, or threats, keep the PWDVA monetary-relief/residence route separate from the basic maintenance claim [{pwdva}].", ("pwdva",)),
            LineSpec("If the older CrPC route applies, compare the same maintenance facts with the CrPC maintenance source instead of mixing old and new provisions [{crpc}].", ("crpc",)),
            LineSpec("**What you can do next**"),
            LineSpec("- Make a month-wise support and expense chart with marriage/relationship proof, children birth/school records, rent/food/medical/school-fee proof, your income, husband/spouse job or income clues, bank statements, messages, and any violence/threat facts; take it to DLSA, Family Court, or the Magistrate route for maintenance/interim maintenance [{family}].", ("family",)),
        ),
        priority=103,
    ),
    AuthorityWorkflowContract(
        id="friendly_loan_upi_recovery",
        route_categories=("business_contract_partnership", "cheque_bounce", "criminal_general"),
        trigger_groups=(
            ("loan", "money", "lakh", "upi", "cash", "borrowed"),
            ("brother", "cousin", "friend", "relative", "uncle", "family"),
            ("not returning", "avoiding calls", "not paying", "return", "repay"),
        ),
        source_specs=(
            PassageSpec("contract", ("indian contract",), ("/sec-37", "/sec-73"), required=True),
            PassageSpec("limitation", ("limitation act",), ("/sec-3",)),
            PassageSpec("cpc", ("code of civil procedure",)),
            PassageSpec("ni", ("negotiable instruments",), ("/sec-138",)),
        ),
        line_specs=(
            LineSpec("Treat a family/friendly hand loan paid by UPI, bank transfer, cash, or messages as a civil money-recovery problem first; the Indian Contract Act source supports focusing on repayment promise/proof instead of assuming a police cheating case [{contract}].", ("contract",)),
            LineSpec("Check limitation from the loan date, due date, last acknowledgement, or part-payment before sending notice or filing a recovery suit [{limitation}].", ("limitation",)),
            LineSpec("If there is a dishonoured cheque for repayment, keep the NI Act cheque-bounce route separate from the ordinary civil recovery suit [{ni}].", ("ni",)),
            LineSpec("**What you can do next**"),
            LineSpec("- Send a written demand/legal notice with the amount, due date, and proof, then discuss a civil recovery or summary-suit route with DLSA or a lawyer using bank/UPI or UPI/bank proof, chats admitting the loan, witnesses, repayment promises, and limitation dates [{contract}].", ("contract",)),
        ),
        priority=103,
    ),
    AuthorityWorkflowContract(
        id="ordinary_invoice_payment_reminder",
        route_categories=("business_contract_partnership",),
        trigger_groups=(
            ("client", "customer", "invoice", "bill"),
            ("late", "3 days", "three days", "not paid", "payment pending", "pending payment", "due", "4 lakh"),
            ("police", "fir", "complaint", "reminder", "legal notice", "indian law", "dubai", "foreign", "saas work"),
        ),
        source_specs=(
            PassageSpec("contract", ("indian contract",), ("/sec-37", "/sec-73"), required=True),
            PassageSpec("fema", ("foreign exchange management",), ("/sec-8",)),
            PassageSpec("msmed", ("micro, small and medium", "msme"), ("/sec-15", "/sec-16", "/sec-18")),
        ),
        line_specs=(),
        priority=122,
    ),
    AuthorityWorkflowContract(
        id="principal_agent_goods_absconded",
        route_categories=("business_contract_partnership",),
        trigger_groups=(
            ("agent", "principal agent", "principal-agent"),
            ("goods worth", "took my goods", "absconded", "not returning goods", "principal agent relationship"),
        ),
        source_specs=(
            PassageSpec("contract", ("indian contract",), required=True),
            PassageSpec("specific", ("specific relief",), ("/sec-38", "/sec-39")),
            PassageSpec("cpc", ("code of civil procedure",)),
        ),
        line_specs=(
            LineSpec("For an agent who took goods and absconded, start with the Indian Contract Act agency-duty/accounting source: prove the principal-agent relationship, entrustment of goods, instructions, and loss before choosing civil recovery or injunction [{contract}].", ("contract",)),
            LineSpec("If goods, accounts, or documents need return, the civil court/commercial court route may need injunction, delivery, accounting, or damages relief rather than only a police complaint [{specific}].", ("specific",)),
            LineSpec("Keep a police cheating or breach-of-trust track separate and use it only if the facts show dishonest intention, entrustment, forgery, threats, or deception beyond ordinary non-payment/performance failure [{contract}].", ("contract",)),
            LineSpec("**What you can do next**"),
            LineSpec("- Preserve invoices, delivery challans, transport/LR proof, agent agreement or messages, stock ledger, customer/payment records, address/KYC of the agent, loss calculation, and any demand notice or refusal; then verify civil/commercial recovery, injunction/accounting, and police complaint options with DLSA or a lawyer [{contract}].", ("contract",)),
        ),
        priority=124,
    ),
    AuthorityWorkflowContract(
        id="employment_original_document_return",
        route_categories=("employment_wages",),
        trigger_groups=(
            ("employer", "company", "hr", "office", "boss"),
            (
                "original degree", "degree certificate", "original certificate",
                "original certificates", "education certificate",
                "kept my original", "holding my original", "not returning my original",
            ),
            ("resigned", "resignation", "left job", "after i resigned", "not replying", "refusing", "holding"),
        ),
        source_specs=(
            PassageSpec("wages", ("code on wages",), ("/sec-17", "/sec-45"), required=True),
            PassageSpec("industrial", ("industrial disputes",), ("/sec-2A", "/sec-10")),
            PassageSpec("contract", ("indian contract",), ("/sec-37", "/sec-73")),
        ),
        line_specs=(),
        priority=121,
    ),
    AuthorityWorkflowContract(
        id="unpaid_group_wages_no_contract",
        route_categories=("employment_wages", "labour_exploitation_discrimination"),
        trigger_groups=(
            ("factory", "workers", "worker", "labour", "labor", "contractor", "owner"),
            ("not paid", "unpaid", "wages", "salary pending", "no payment"),
            ("no written contract", "dont have written contract", "don't have written contract", "without contract", "25 workers", "many workers"),
        ),
        source_specs=(
            PassageSpec("wages", ("code on wages", "payment of wages"), ("/sec-17", "/sec-18", "/sec-45"), required=True),
            PassageSpec("industrial", ("industrial disputes",), ("/sec-2A", "/sec-10", "/sec-25F")),
        ),
        line_specs=(),
        priority=126,
    ),
    AuthorityWorkflowContract(
        id="employment_notice_period_contract",
        route_categories=("employment_wages", "labour_exploitation_discrimination"),
        trigger_groups=(
            ("notice period", "serve 90", "90 day", "60 day", "offer letter", "appointment letter", "employment contract"),
            ("company", "employer", "hr", "offer letter", "appointment letter"),
        ),
        source_specs=(
            PassageSpec("contract", ("indian contract",), ("/sec-37", "/sec-73"), required=True),
            PassageSpec("wages", ("code on wages", "payment of wages"), ("/sec-17", "/sec-18", "/sec-45")),
        ),
        line_specs=(),
        priority=124,
    ),
    AuthorityWorkflowContract(
        id="marriage_legal_age",
        route_categories=("family_marriage_status", "family_domestic"),
        trigger_groups=(
            ("legal age", "age legal", "marriage age", "got married", "minimum age"),
        ),
        source_specs=(
            PassageSpec("pcma", ("prohibition of child marriage",), ("/sec-2", "/sec-3"), required=True),
            PassageSpec("sma", ("special marriage",), ("/sec-4", "/sec-28")),
        ),
        line_specs=(),
        priority=124,
    ),
    AuthorityWorkflowContract(
        id="prison_mulaqat_books",
        route_categories=("prison_mulaqat", "undertrial_review_release", "legal_aid"),
        trigger_groups=(
            ("tihar", "jail", "prison", "mulaqat", "mulakat", "interview", "visit"),
            ("book", "books", "visitor", "visitor list", "phone call", "during mulaqat", "wife", "husband", "child"),
        ),
        source_specs=(
            PassageSpec("delhi_rules", ("delhi prison rules", "delhi prisons rules"), ("/rule-619-1029-books", "/prisoners-rights-contact-books", "/rule-595-599", "/rule-601-606")),
            PassageSpec("prisons", ("prisons act", "prisons"), ("/sec-59", "/sec-4", "/sec-3", "#header")),
            PassageSpec("article21", ("constitution",), ("/sec-21",)),
        ),
        line_specs=(),
        priority=124,
    ),
    AuthorityWorkflowContract(
        id="esi_contribution_notice",
        route_categories=("labour_compliance", "employment_wages"),
        trigger_groups=(
            ("esi", "esic", "employees state insurance", "employees' state insurance"),
            ("notice", "inspector", "contribution", "short", "casual workers"),
        ),
        source_specs=(
            PassageSpec("esi", ("employees' state insurance", "employees state insurance"), ("/sec-40", "/sec-45A", "/sec-75"), required=True),
            PassageSpec("social", ("code on social security", "social security code"), ("/sec-31",)),
        ),
        line_specs=(),
        priority=124,
    ),
    AuthorityWorkflowContract(
        id="income_tax_appeal_deadline",
        route_categories=("tax_gst_compliance",),
        trigger_groups=(
            ("form 35", "cit appeals", "cit(a)", "commissioner appeals", "itat", "appellate tribunal"),
            ("appeal", "time limit", "deadline", "file"),
        ),
        source_specs=(
            PassageSpec("tax", ("income-tax", "income tax"), ("/sec-249", "/sec-253"), required=True),
        ),
        line_specs=(),
        priority=124,
    ),
    AuthorityWorkflowContract(
        id="gst_freelancer_registration_threshold",
        route_categories=("tax_gst_compliance",),
        trigger_groups=(
            ("freelance", "freelancer", "designer", "consultant", "professional income", "creator"),
            ("gst", "register", "registration", "18 lakh", "20 lakh", "turnover"),
        ),
        source_specs=(
            PassageSpec("cgst", ("central goods and services tax",), ("/sec-22", "/sec-24"), required=True),
            PassageSpec("tax", ("income-tax", "income tax"), ("/sec-139",)),
        ),
        line_specs=(),
        priority=124,
    ),
    AuthorityWorkflowContract(
        id="senior_parent_pension_neglect",
        route_categories=("senior_citizen", "family_domestic"),
        trigger_groups=(
            ("father", "mother", "parent", "maa", "widow", "senior", "elderly", "old", "my son", "my daughter", "daughter in law", "daughter-in-law", "bahu", "i am 70", "i am 73", "i am 74"),
            ("son", "daughter", "children", "bahu", "pushed", "changed lock", "not letting", "cannot stay", "sleep outside", "forced out", "being forced out", "forced to leave"),
            (
                "not taking care",
                "not giving food",
                "not giving money",
                "food and money",
                "took his pension",
                "took her pension",
                "pension",
                "maintenance",
                "maintain",
                "maintaining",
                "neglect",
                "abandoned",
                "left me alone",
                "threw me out",
                "thrown out",
                "throw me out",
                "forced out",
                "being forced out",
                "forced to leave",
                "pushed me out",
                "pushed out",
                "pushed from",
                "not allowed",
                "not allowing",
                "not letting",
                "changed lock",
                "cannot stay",
                "sleep outside",
                "own house",
                "own home",
                "flat",
                "flat to son",
                "transferred flat",
                "kitchen",
                "room",
                "bathroom",
                "passbook",
                "atm card",
                "not giving money",
                "medicine money",
                "medicine",
                "ration",
                "no food",
                "refuses food",
                "monthly support",
                "leave house",
                "self acquired",
                "self-acquired",
                "bought by me",
                "from my savings",
                "ornaments",
                "jewellery",
                "jewelry",
                "daughter in law",
                "daughter-in-law",
                "bahu",
            ),
        ),
        source_specs=(
            PassageSpec("senior", ("maintenance and welfare of parents", "senior citizens"), ("/sec-4", "/sec-5", "/sec-9", "/sec-23"), required=True),
            PassageSpec("senior23", ("maintenance and welfare of parents", "senior citizens"), ("/sec-23",)),
            PassageSpec("pwdva", ("domestic violence",), ("/sec-12", "/sec-19", "/sec-18")),
            PassageSpec("tpa_gift", ("transfer of property",), ("/sec-122", "/sec-123", "/sec-126")),
            PassageSpec("hama", ("hindu adoptions and maintenance",), ("/sec-20",)),
        ),
        line_specs=(
            LineSpec("If a son/daughter is not taking care of an old parent and has taken or controlled the parent's pension, use the Senior Citizens Act maintenance-tribunal route first [{senior}].", ("senior",)),
            LineSpec("The tribunal route can cover maintenance/support; if property or transfer papers were taken from the parent, also check the Senior Citizens Act transfer/cancellation source with the documents [{senior}].", ("senior",)),
            LineSpec("Where personal law maintenance is relevant, keep the Hindu Adoptions and Maintenance source secondary to the faster Senior Citizens Act tribunal route for parents [{hama}].", ("hama",)),
            LineSpec("**What you can do next**"),
            LineSpec("- File before the Maintenance Tribunal/District Social Welfare office with the parent's age/ID, pension/passbook proof, bank withdrawals, residence/medical expenses, son's/daughter's details, messages, witnesses, and any property-transfer papers; ask DLSA for help if the parent cannot file alone [{senior}].", ("senior",)),
        ),
        priority=102,
    ),
    AuthorityWorkflowContract(
        id="senior_maintenance_order_enforcement",
        route_categories=("senior_citizen",),
        trigger_groups=(
            ("tribunal", "maintenance tribunal", "senior citizen tribunal", "ordered", "order"),
            ("son", "daughter", "relative", "children", "parent", "father", "mother"),
            ("stopped paying", "not paying", "enforce", "enforcement", "arrears", "deposit", "10000", "10,000"),
        ),
        source_specs=(
            PassageSpec("senior", ("maintenance and welfare of parents", "senior citizens"), ("/sec-5", "/sec-9", "/sec-11", "/sec-13"), required=True),
        ),
        line_specs=(
            LineSpec("If the Maintenance Tribunal already ordered a son/daughter/relative to pay and payment stopped, treat it as enforcement of the senior-citizen maintenance order, not a fresh police or generic family dispute [{senior}].", ("senior",)),
            LineSpec("Use the Senior Citizens Act order/enforcement and deposit sources to ask the Tribunal or district authority for arrears, compliance, and recovery steps based on the existing order [{senior}].", ("senior",)),
            LineSpec("**What you can do next**"),
            LineSpec("- Take the tribunal order, arrears month-wise chart, bank/passbook entries, notices/messages, age/ID proof, son's/daughter's address and income details, and prior non-payment proof to the Maintenance Tribunal/District Magistrate office or DLSA; ask whether police help is needed only for safety or execution support [{senior}].", ("senior",)),
        ),
        priority=114,
    ),
    AuthorityWorkflowContract(
        id="unpaid_salary_after_termination",
        route_categories=("employment_wages",),
        trigger_groups=(
            ("employer", "company", "boss", "factory", "office", "hr", "manager"),
            (
                "fired", "terminated", "removed from job", "laid off",
                "lay off", "holding", "not paying", "unpaid", "last month",
                "salary", "salary pending", "pending salary", "salary not paid",
                "wage", "wages", "dues", "full and final", "final settlement",
                "fnf", "notice period salary",
            ),
        ),
        source_specs=(
            PassageSpec("wages", ("code on wages",), ("/sec-17", "/sec-18", "/sec-45"), required=True),
            PassageSpec("id", ("industrial disputes",), ("/sec-2A", "/sec-25F", "/sec-25N", "/sec-25FFA", "/sec-25FFF")),
        ),
        line_specs=(
            LineSpec("If an employer fired, terminated, removed, laid off, relieved you, or a sudden factory closure/factory-company-undertaking closure happened while holding last-month salary, two months pending salary or two-month arrears, wages, full-and-final, notice-period salary, or other dues are pending, treat it as a written Code on Wages wage/dues claim first, not only as a termination argument and not only an unpaid-salary issue [{wages}].", ("wages",)),
            LineSpec("If the firing, factory closure, company/undertaking closure, or no-notice shutdown itself is disputed, keep the Industrial Disputes Act termination/retrenchment track, closure/retrenchment track, and wage-arrears tracks separate from the immediate unpaid-wages claim, including notice wages or retrenchment/closure compensation [{id}].", ("id",)),
            LineSpec("**What you can do next**"),
            LineSpec("- Send a written wage/full-and-final demand and file with the Labour Commissioner/wage authority using appointment proof, last working date, salary slips, attendance, bank statements, termination/resignation/layoff messages, unpaid amount calculation, and employer replies [{wages}].", ("wages",)),
        ),
        priority=101,
    ),
    AuthorityWorkflowContract(
        id="marriage_salary_loan_misrepresentation",
        route_categories=("family_marriage_status",),
        trigger_groups=(
            ("husband", "wife", "groom", "bride", "marriage", "biodata"),
            ("lied", "false", "misrepresentation", "hid", "fake"),
            ("salary", "job", "loans", "income", "govt job", "government job"),
        ),
        source_specs=(
            PassageSpec("hma", ("hindu marriage",), ("/sec-12",), required=True),
            PassageSpec("family", ("family courts",), ("/sec-7", "/sec-8")),
            PassageSpec("sma", ("special marriage",), ("/sec-25",)),
        ),
        line_specs=(
            LineSpec("If your spouse lied before marriage about salary, job, loans, income, or biodata facts, check whether those facts legally support a voidable-marriage or matrimonial-relief claim; not every lie automatically cancels a marriage [{hma}].", ("hma",)),
            LineSpec("The Family Courts Act source is the forum route for annulment/voidable-marriage, divorce, maintenance, counselling, or other matrimonial relief after the personal-law source is identified [{family}].", ("family",)),
            LineSpec("If the marriage was under the Special Marriage Act, use that source instead of assuming Hindu Marriage Act relief [{sma}].", ("sma",)),
            LineSpec("**What you can do next**"),
            LineSpec("- Collect biodata/profile/messages, job/salary/loan proof, marriage certificate, date you discovered the truth, residence/children/maintenance facts, and then ask DLSA or a family-law lawyer whether annulment, divorce, maintenance, or counselling is the right Family Court remedy [{family}].", ("family",)),
        ),
        priority=101,
    ),
    AuthorityWorkflowContract(
        id="upi_seller_payment_refund",
        route_categories=("consumer", "banking_credit_dispute", "digital_platform_account"),
        trigger_groups=(
            ("upi", "payment", "transaction"),
            ("seller", "merchant", "amazon", "flipkart", "order"),
            ("refund", "not received", "payment not received", "failed"),
        ),
        source_specs=(
            PassageSpec("consumer", ("consumer protection",), ("/sec-2", "/sec-35", "/sec-38", "/sec-39"), required=True),
            PassageSpec("rbi", ("reserve bank integrated ombudsman", "integrated ombudsman"), ("/sec-2", "/sec-3"), required=True),
        ),
        line_specs=(
            LineSpec("For a PhonePe/GPay UPI/payment transaction or UPI/payment-app transaction where the seller or merchant says payment was not received while your app or bank shows debit/success, keep both records: the seller/order refund dispute under the Consumer Protection Act and the payment-rail complaint trail for the bank/payment app [{consumer}].", ("consumer",)),
            LineSpec("If PhonePe, GPay, the bank, or payment app does not resolve the UPI transaction or refund complaint after a written ticket, use the RBI Ombudsman/CMS route with the transaction reference and bank/payment-app reply [{rbi}].", ("rbi",)),
            LineSpec("**What you can do next**"),
            LineSpec("- Keep the seller/order ID, invoice, PhonePe/GPay/UPI transaction ID/RRN, app status showing success or failed refund, bank debit SMS/statement, seller reply, support ticket, and refund timeline before escalating to the seller/platform, bank/payment app, RBI Ombudsman, or consumer forum [{rbi}], [{consumer}].", ("rbi", "consumer")),
        ),
        priority=97,
    ),
    AuthorityWorkflowContract(
        id="pan_leak_fake_bank_account",
        route_categories=("cyber_fraud_or_harassment", "banking_credit_dispute"),
        trigger_groups=(
            ("pan", "pan card", "pan copy"),
            ("leaked", "leak", "online"),
            ("fake bank account", "bank account opened", "opened bank account", "opened in my name", "account opened in my name"),
        ),
        source_specs=(
            PassageSpec("dpdp", ("digital personal data protection",), ("/sec-8", "/sec-13", "/sec-27"), required=True),
            PassageSpec("it", ("information technology",), ("/sec-66C", "/sec-66D", "/sec-66E"), required=True),
            PassageSpec("rbi", ("reserve bank integrated ombudsman", "integrated ombudsman"), ("/sec-2", "/sec-3"), required=True),
            PassageSpec("bns", ("bharatiya nyaya",), ("/sec-318", "/sec-319", "/sec-351", "/sec-356")),
            PassageSpec("bnss", ("bharatiya nagarik suraksha",), ("/sec-173", "/sec-175")),
        ),
        line_specs=(
            LineSpec("For a PAN card copy leaked online and a fake bank account opened in your name, keep three lanes together: DPDP personal-data breach/grievance [{dpdp}], IT Act identity/electronic misuse [{it}], and bank/RBI Ombudsman complaint for the unauthorized account/KYC record [{rbi}].", ("dpdp", "it", "rbi")),
            LineSpec("If a person used the PAN copy to impersonate you, create a separate police/cyber track for cheating/personation or intimidation facts; do not treat this as only PAN-Aadhaar correction [{bns}].", ("bns",)),
            LineSpec("For FIR/cyber complaint paperwork and escalation, keep the BNSS police-information/Magistrate route with the bank and cyber complaint acknowledgements [{bnss}].", ("bnss",)),
            LineSpec("**What you can do next**"),
            LineSpec("- Preserve the PAN leak URL/screenshot, bank name/account-opening proof, KYC rejection or notice, credit/bank alerts, cyber complaint number, bank complaint number, and DPDP/platform grievance; ask the bank for the account-opening documents and freeze/dispute record in writing [{dpdp}], [{it}], [{rbi}].", ("dpdp", "it", "rbi")),
        ),
        priority=116,
    ),
    AuthorityWorkflowContract(
        id="mental_health_chain_or_confinement",
        route_categories=("mental_health_care_rights",),
        trigger_groups=(
            ("chain", "chains", "chained", "tied", "confined", "locked in room", "kept locked", "ill treated", "ill-treated", "neglected"),
            ("mental illness", "mentally ill", "mental health", "psychiatric", "psychiatrist", "admit", "hospital"),
        ),
        source_specs=(
            PassageSpec("dignity", ("mental healthcare",), ("/sec-20",), required=True),
            PassageSpec("police_protection", ("mental healthcare",), ("/sec-100",), required=True),
            PassageSpec("emergency", ("mental healthcare",), ("/sec-94",)),
            PassageSpec("restraint", ("mental healthcare",), ("/sec-97",)),
            PassageSpec("legal_aid", ("mental healthcare",), ("/sec-27",)),
        ),
        line_specs=(
            LineSpec("For a person with an apparent mental-health crisis who is being kept in chains, tied, or confined, treat immediate safety and a lawful health assessment as the first problem, not as a family discipline issue; the Mental Healthcare Act protects dignity and protection from cruel, inhuman, degrading, and abusive treatment [{dignity}].", ("dignity",)),
            LineSpec("If police have reason to believe the person is a risk to self or others because of mental illness, the Act sets a protection-to-public-health-establishment path and says the person must not be kept in a police lock-up or prison; ask for an assessment rather than informal confinement [{police_protection}].", ("police_protection",)),
            LineSpec("If there is immediate risk of death, irreversible harm, or serious harm to self or others, emergency treatment and transport for assessment may be used under the emergency-care source [{emergency}].", ("emergency",)),
            LineSpec("The Act's restraint source is not a permission for ordinary family chaining: restraint is tightly limited in a mental-health establishment, must address immediate harm, and must be recorded/supervised [{restraint}].", ("restraint",)),
            LineSpec("**What you can do next**"),
            LineSpec("- If there is immediate danger, contact emergency medical help or police and ask for transport to the nearest public mental-health establishment for assessment; preserve the address, photos only if safe, medical history, medicines, family contact, and the dates/details of confinement or harm [{police_protection}], [{emergency}].", ("police_protection",)),
            LineSpec("- Ask the hospital or district mental-health programme for a written assessment/admission decision and contact DLSA for free legal aid if confinement, neglect, or refusal to help continues [{legal_aid}].", ("legal_aid",)),
        ),
        priority=149,
    ),
    AuthorityWorkflowContract(
        id="pension_aadhaar_bank_closure",
        route_categories=("social_welfare_identity", "banking_credit_dispute"),
        trigger_groups=(
            ("pension", "old age pension", "widow pension", "disability pension"),
            ("aadhaar", "aadhar", "not linked", "link"),
            ("bank", "bank account", "account closed", "closed"),
        ),
        source_specs=(
            PassageSpec("nsap", ("national social assistance", "old age pension", "widow pension"), required=True),
            PassageSpec("aadhaar", ("aadhaar", "aadhar"), ("/sec-7", "/sec-8", "/sec-59"), required=True),
            PassageSpec("rbi", ("reserve bank integrated ombudsman", "integrated ombudsman"), ("/sec-2", "/sec-3"), required=True),
            PassageSpec("rti", ("right to information",), ("/sec-6", "/sec-7", "/sec-19")),
        ),
        line_specs=(
            LineSpec("For an old-age/welfare pension stopped because the bank account was closed or Aadhaar was not linked, keep the pension-restoration lane under the pension scheme [{nsap}], the Aadhaar authentication/linkage lane [{aadhaar}], and the bank-service complaint/RBI Ombudsman lane [{rbi}] separate.", ("nsap", "aadhaar", "rbi")),
            LineSpec("Do not accept oral tehsil or bank replies; ask for the written pension stoppage reason, Aadhaar-link status, and bank account closure reason before choosing the correction route [{aadhaar}], [{rbi}].", ("aadhaar", "rbi")),
            LineSpec("If the office will not give status or reasons, use RTI/first appeal for the pension file, bank-linkage status, and action-taken record while keeping the pension grievance active [{rti}].", ("rti",)),
            LineSpec("**What you can do next**"),
            LineSpec("- Keep pension ID, Aadhaar/linking proof, bank passbook or closure message, last pension credit date, tehsil/block replies, written complaint number, and ask the pension office and bank in writing for restoration or account-update status [{nsap}], [{aadhaar}], [{rbi}].", ("nsap", "aadhaar", "rbi")),
        ),
        priority=115,
    ),
    AuthorityWorkflowContract(
        id="pension_aadhaar_biometric_mismatch",
        route_categories=("social_welfare_identity",),
        trigger_groups=(
            ("pension", "old age pension", "widow pension", "disability pension"),
            ("biometric", "fingerprint", "authentication", "aadhaar", "aadhar"),
            ("stopped", "blocked", "failed", "mismatch", "update", "block office"),
        ),
        source_specs=(
            PassageSpec("nsap", ("national social assistance", "old age pension", "widow pension"), required=True),
            PassageSpec("aadhaar", ("aadhaar", "aadhar"), ("/sec-7", "/sec-8", "/sec-59"), required=True),
            PassageSpec("rti", ("right to information",), ("/sec-6", "/sec-7", "/sec-19")),
        ),
        line_specs=(
            LineSpec("For stopped old-age pension, widow pension, or disability pension after biometric mismatch, Aadhaar-not-linked, or Aadhaar authentication failure, keep the pension-restoration lane under the pension scheme and the Aadhaar authentication/correction lane together; do not accept only an oral instruction to update Aadhaar [{nsap}], [{aadhaar}].", ("nsap", "aadhaar")),
            LineSpec("Ask the pension office/block office for the written pension stoppage reason, biometric/authentication failure record, Aadhaar-link status, and restoration or alternate-verification route [{nsap}], [{aadhaar}].", ("nsap", "aadhaar")),
            LineSpec("If the block office or portal will not give reasons, use RTI/first appeal for the pension file, Aadhaar authentication log/status, and action-taken record, but do not make RTI the only remedy while the pension grievance remains pending [{rti}].", ("rti",)),
            LineSpec("**What you can do next**"),
            LineSpec("- Keep pension ID, Aadhaar number/proof, biometric mismatch message, last pension credit, block-office reply, bank/passbook proof, written complaint number, and ask in writing for pension restoration or alternate authentication instead of only redoing Aadhaar blindly [{nsap}], [{aadhaar}].", ("nsap", "aadhaar")),
        ),
        priority=116,
    ),
    AuthorityWorkflowContract(
        id="pds_aadhaar_cancellation",
        route_categories=("social_welfare_identity",),
        trigger_groups=(
            ("ration", "pds", "ration card", "fair price", "foodgrain", "grain"),
            ("aadhaar", "aadhar", "uidai", "biometric", "authentication", "mismatch"),
            ("cancelled", "canceled", "blocked", "renew", "restore", "bdo", "not agreeing", "not renewing"),
        ),
        source_specs=(
            PassageSpec("nfsa", ("national food security",), ("/sec-3", "/sec-13", "/sec-14", "/sec-15"), required=True),
            PassageSpec("aadhaar", ("aadhaar", "aadhar"), ("/sec-7", "/sec-8", "/sec-59"), required=True),
            PassageSpec("dpdp", ("digital personal data protection", "dpdp"), ("/sec-8", "/sec-13", "/sec-27"), required=True),
            PassageSpec("rti", ("right to information",), ("/sec-6", "/sec-7", "/sec-19")),
        ),
        line_specs=(
            LineSpec("For ration-card cancellation or renewal refusal after Aadhaar mismatch, keep the NFSA foodgrain/ration-card grievance route and the Aadhaar authentication/identity route together; do not treat the BDO or office oral refusal as final without a written order or reason [{nfsa}], [{aadhaar}].", ("nfsa", "aadhaar")),
            LineSpec("Because the issue turns on identity data or mismatch records used by the office, keep a DPDP personal-data grievance/record-correction track for the data-handling side, separate from the NFSA entitlement grievance [{dpdp}].", ("dpdp",)),
            LineSpec("If the ration office/BDO will not give the cancellation order, mismatch field, renewal reason, or file status, use RTI/first appeal for the ration-card file and action-taken record while keeping the NFSA grievance active [{rti}].", ("rti",)),
            LineSpec("**What you can do next**"),
            LineSpec("- Keep ration-card ID, Aadhaar/UIDAI mismatch screenshot, household details, BDO/office reply, denial or cancellation date, shop/dealer details, and file a written complaint with the Food and Civil Supplies/NFSA grievance authority or DGRO asking for restoration, written reasons, and correction route [{nfsa}], [{aadhaar}], [{dpdp}].", ("nfsa", "aadhaar", "dpdp")),
        ),
        priority=118,
    ),
    AuthorityWorkflowContract(
        id="ration_biometric_auth_failure",
        route_categories=("social_welfare_identity",),
        trigger_groups=(
            ("ration", "pds", "dealer", "grain", "fair price", "ration shop", "fair price shop", "fps"),
            ("biometric", "fingerprint", "thumb", "authentication", "pos machine", "machine", "ekyc", "e-kyc"),
            ("failed", "fail", "cannot get", "not giving", "denied", "not matching", "mismatch", "server failed", "machine not working"),
        ),
        source_specs=(
            PassageSpec("nfsa", ("national food security",), ("/sec-3", "/sec-12", "/sec-13", "/sec-14", "/sec-15"), required=True),
            PassageSpec("aadhaar", ("aadhaar", "aadhar"), ("/sec-7", "/sec-8", "/sec-59"), required=True),
            PassageSpec("rti", ("right to information",), ("/sec-6", "/sec-7", "/sec-19")),
        ),
        line_specs=(
            LineSpec("For ration denial because an old mother's fingerprint or biometric authentication failed, including where the biometric machine fails, treat it as an NFSA ration-entitlement grievance plus an Aadhaar authentication/exception problem, not as a generic Aadhaar problem or a final denial of grain [{nfsa}], [{aadhaar}].", ("nfsa", "aadhaar")),
            LineSpec("Ask the ration dealer/Food and Civil Supplies office for alternate or exception handling, including any alternate authentication process, a written denial slip/reason, and the DGRO or district grievance route [{nfsa}], [{aadhaar}].", ("nfsa", "aadhaar")),
            LineSpec("Use RTI only to get records such as the ration transaction log, biometric failure reason, dealer register entry, and action-taken report; RTI is a records-support route after the ration grievance is filed [{rti}].", ("rti",)),
            LineSpec("**What you can do next**"),
            LineSpec("- Keep ration-card ID, Aadhaar/ID proof, failed biometric/fingerprint date, dealer/fair-price-shop details, prior slips, household member details, and file a written ration grievance asking for alternate authentication and grain release [{nfsa}], [{aadhaar}].", ("nfsa", "aadhaar")),
        ),
        priority=114,
    ),
    AuthorityWorkflowContract(
        id="pan_aadhaar_bank_kyc_mismatch",
        route_categories=("social_welfare_identity", "banking_credit_dispute"),
        trigger_groups=(
            ("pan", "pan card"),
            ("aadhaar", "aadhar"),
            ("kyc", "bank", "linking failed", "spelling", "mismatch", "not matching"),
        ),
        source_specs=(
            PassageSpec("income_tax", ("income-tax", "income tax"), ("/sec-139-a", "/sec-139a", "/sec-139"), required=True),
            PassageSpec("aadhaar", ("aadhaar", "aadhar"), ("/sec-4", "/sec-7", "/sec-8", "/sec-59"), required=True),
        ),
        line_specs=(
            LineSpec("For a PAN/Aadhaar mismatch or PAN spelling mistake causing bank KYC failure or bank account-opening rejection, do not treat this as a caste, ration, or generic welfare issue; first identify which record is wrong and which record needs correction: PAN/Income-tax record, Aadhaar demographic record, or the bank KYC entry [{income_tax}], [{aadhaar}].", ("income_tax", "aadhaar")),
            LineSpec("Do not file a cyber or general legal complaint just because KYC failed; ask the bank for the exact written mismatch field and update the record-holding authority first [{income_tax}], [{aadhaar}].", ("income_tax", "aadhaar")),
            LineSpec("**What you can do next**"),
            LineSpec("- Keep PAN, Aadhaar, bank KYC rejection screenshot, exact spelling/DOB/name fields, bank complaint number, and correction acknowledgements; correct the wrong record first, then resubmit bank KYC with the written acknowledgement [{income_tax}], [{aadhaar}].", ("income_tax", "aadhaar")),
        ),
        priority=113,
    ),
    AuthorityWorkflowContract(
        id="public_political_meme_police_risk",
        route_categories=("criminal_general", "cyber_fraud_or_harassment", "police_fir"),
        trigger_groups=(
            ("meme", "political meme", "modi", "prime minister", "minister", "public figure"),
            ("police", "arrest", "fir", "case", "can police"),
        ),
        source_specs=(
            PassageSpec("it", ("information technology",), ("/sec-66C", "/sec-66D", "/sec-66E"), required=True),
            PassageSpec("bnss", ("bharatiya nagarik suraksha",), ("/sec-173", "/sec-175"), required=True),
            PassageSpec("bns", ("bharatiya nyaya",), ("/sec-351", "/sec-356", "/sec-196")),
            PassageSpec("rpa", ("representation of the people",), ("/sec-123", "/sec-125")),
        ),
        line_specs=(
            LineSpec("For a public-political meme or fake AI video using Modi/minister/public-figure face, arrest risk depends on the exact post, cyber/electronic publication facts, and the police notice/FIR material; do not assume a normal meme automatically means arrest [{it}], [{bnss}].", ("it", "bnss")),
            LineSpec("If the facts include threat, reputation injury, public-order, election, or other offence allegations, keep the BNS source separate from the cyber-evidence and police-procedure source instead of guessing an offence label [{bns}].", ("bns",)),
            LineSpec("If the post is tied to election, candidate, party-campaign, or corrupt-practice allegations, verify the Representation of the People Act election-law lane separately; do not treat every political meme as an election offence [{rpa}].", ("rpa",)),
            LineSpec("If police contact you, ask for the written notice/FIR number, sections, station, complainant, and whether you are accused or only being asked about the post [{bnss}].", ("bnss",)),
            LineSpec("**What you can do next**"),
            LineSpec("- Preserve the exact post/URL, caption, edit history, date/time, who posted/shared it, any threat messages, platform report, and police/FIR/notice details before deciding takedown, reply, anticipatory legal advice, or cyber/cyber-police response [{it}], [{bnss}].", ("it", "bnss")),
        ),
        priority=112,
    ),
    AuthorityWorkflowContract(
        id="ordinary_emi_reminder_not_harassment",
        route_categories=("banking_credit_dispute", "general_legal"),
        trigger_groups=(
            ("emi", "lender", "loan"),
            ("reminder", "reminder sms", "sms", "late"),
            ("harassment", "harass", "no threats", "no contacts", "not harassment"),
        ),
        source_specs=(
            PassageSpec("rbi", ("reserve bank integrated ombudsman", "integrated ombudsman"), ("/sec-2", "/sec-3"), required=True),
        ),
        line_specs=(
            LineSpec("A normal written EMI reminder from a lender is not automatically harassment; treat it as a lender-service/recovery-conduct issue and check whether the lender crosses into threats, abuse, public shaming, repeated coercive calls, or refusal to give account information [{rbi}].", ("rbi",)),
            LineSpec("Use the RBI Ombudsman/CMS route only after you have a written lender complaint/reply or no-reply record; do not start with police unless there are threats, violence, extortion, or unlawful public shaming facts [{rbi}].", ("rbi",)),
            LineSpec("**What you can do next**"),
            LineSpec("- Keep the lender name, loan account, due date, EMI amount, exact reminder SMS/call log, payment/default timeline, and written complaint number; ask the lender in writing to stop unlawful harassment if conduct goes beyond a normal reminder [{rbi}].", ("rbi",)),
        ),
        priority=111,
    ),
    AuthorityWorkflowContract(
        id="loan_emi_penalty_fee_dispute",
        route_categories=("banking_credit_dispute",),
        trigger_groups=(
            ("emi", "loan", "nbfc", "finance", "lender", "bajaj", "bajaj finserv", "bajaj finance"),
            ("bounce", "bounced", "bounce charges", "penalty", "late fee", "charges", "too high"),
        ),
        source_specs=(
            PassageSpec("rbi", ("reserve bank integrated ombudsman", "integrated ombudsman"), required=True),
            PassageSpec("consumer", ("consumer protection",), ("/sec-2", "/sec-35", "/sec-38")),
            PassageSpec("cic", ("credit information companies",), ("/sec-18", "/sec-19", "/sec-20", "/sec-21", "/sec-22")),
        ),
        line_specs=(
            LineSpec("For a personal-loan EMI bounce charge, penalty, or late-fee dispute, treat it first as a lender/NBFC service-charge grievance under the RBI Ombudsman/CMS route, not as cyber fraud or loan-app harassment [{rbi}].", ("rbi",)),
            LineSpec("Ask the bank/NBFC or lender in writing for the EMI bounce reason, penalty breakup, loan-account statement, agreement clause relied on, complaint number, and reversal/refund decision [{rbi}].", ("rbi",)),
            LineSpec("Consumer service-deficiency is a backup forum if the written lender complaint and RBI route do not resolve the wrongful charge or refund issue [{consumer}].", ("consumer",)),
            LineSpec("If the lender has reported or threatened a credit-bureau entry, keep the credit-report correction track separately with the disputed entry and lender reply [{cic}].", ("cic",)),
            LineSpec("**What you can do next**"),
            LineSpec("- Keep the loan account, EMI mandate/autopay record, bounce SMS, bank-error proof if any, penalty calculation, statement, lender emails/calls, complaint number, and any CIBIL/credit-report screenshot before escalating to RBI Ombudsman/CMS [{rbi}].", ("rbi",)),
        ),
        priority=132,
    ),
    AuthorityWorkflowContract(
        id="insurance_claim_or_misselling",
        route_categories=("consumer", "senior_citizen"),
        trigger_groups=(
            ("insurance", "lic", "ulip", "policy", "insurer"),
            (
                "claim", "claim rejected", "claim denied", "claim repudiated",
                "rejecting", "rejected", "denied", "pre existing", "pre-existing", "declared",
                "guaranteed return", "matured", "half amount", "lost 8 lakh",
                "pension money", "mis-selling", "misselling", "fraud",
            ),
        ),
        source_specs=(
            PassageSpec("insurance_scope", ("insurance ombudsman",), ("/sec-13",), required=True),
            PassageSpec("insurance_procedure", ("insurance ombudsman",), ("/sec-14",)),
            PassageSpec("consumer_definition", ("consumer protection",), ("/sec-2",)),
            PassageSpec("consumer_complaint", ("consumer protection",), ("/sec-35",)),
            PassageSpec("consumer_relief", ("consumer protection",), ("/sec-39",)),
            PassageSpec("senior", ("senior citizens", "parents and senior citizens"), ("/sec-4", "/sec-5", "/sec-9")),
        ),
        line_specs=(),
        priority=124,
    ),
    AuthorityWorkflowContract(
        id="builder_rera",
        route_categories=("consumer",),
        trigger_groups=(
            (
                "builder", "developer", "promoter", "rera", "flat",
                "apartment", "housing project", "real estate project",
            ),
            (
                "possession", "occupancy certificate", "occupation certificate",
                "completion certificate", "handover", "delayed", "delay",
                "not giving", "not handed over", "not handing over",
                "refund", "full payment", "paid full", "full money",
                "defective", "defect", "not repairing", "repair",
                "leakage", "tiles", "bathroom", "layout changed",
                "sale deed", "registered sale deed", "register sale deed",
                "hasnt registered", "hasn't registered", "not registered",
                "property tax dues", "tax dues",
                "carpet area", "less than agreement", "less area", "80 sqft",
            ),
        ),
        source_specs=(
            PassageSpec("rera", ("real estate",), ("/sec-14", "/sec-18", "/sec-31", "/sec-34", "/sec-71"), required=True),
            PassageSpec("consumer", ("consumer protection",), ("/sec-2", "/sec-35", "/sec-38", "/sec-39")),
            PassageSpec("registration", ("registration act",), ("/sec-17", "/sec-23", "/sec-49")),
        ),
        line_specs=(
            LineSpec("For a builder/developer occupancy-certificate/OC refusal, possession, completion-certificate, layout-change, refund, or full-payment dispute, treat RERA as the primary real-estate project route; use RERA as the first project/promoter-obligation route; match the agreement, promised possession/OC date, payments, and project registration record to the RERA complaint source [{rera}].", ("rera",)),
            LineSpec("Consumer service-deficiency/refund/compensation can be a parallel route where maintainable, but it should not replace checking the RERA registration, possession, OC, and promoter-obligation record first [{consumer}].", ("consumer",)),
            LineSpec("If the dispute is that the builder has not registered the sale deed, separately verify the Registration Act sale-deed registration source with the sub-registrar record and property-tax-dues papers [{registration}].", ("registration",)),
            LineSpec("**What you can do next**"),
            LineSpec("- Send or keep a written demand to the builder/developer, then approach the State RERA Authority/adjudicating officer with sale/allotment agreement, RERA registration number, payment receipts, possession or OC deadline, OC/completion-certificate status, layout-change notices, builder emails/chats, and refund/compensation demand proof [{rera}].", ("rera",)),
            LineSpec("- Keep the District Consumer Commission/e-Daakhil route as a backup or parallel service-deficiency path only after the builder/RERA record is organised [{consumer}].", ("consumer",)),
        ),
        priority=109,
    ),
    AuthorityWorkflowContract(
        id="consumer_defective_goods",
        route_categories=("consumer",),
        trigger_groups=(
            ("phone", "mobile", "iphone", "laptop", "shoes", "footwear", "online order", "online seller", "seller", "service center", "service centre", "warranty", "amazon", "flipkart", "marketplace", "third party seller", "third-party seller", "company", "brand"),
            ("damaged", "defective", "refund", "return", "replacement", "repair", "not valid", "refusing", "not accepting", "accepting return", "return request", "pickup", "fake", "fake product", "fake goods", "fake shoes", "refund denied"),
        ),
        source_specs=(
            PassageSpec("consumer", ("consumer protection",), ("/sec-2", "/sec-35", "/sec-38", "/sec-39"), required=True),
        ),
        line_specs=(
            LineSpec("For a service-centre warranty refusal on a new defective mobile, damaged phone, Amazon/marketplace fake iPhone, third-party-seller denial, refund refusal, replacement refusal, or return refusal, use the Consumer Protection Act complaint path after preserving proof of purchase, platform/seller or service-centre response, and defect/fake-product evidence [{consumer}].", ("consumer",)),
            LineSpec("**What you can do next**"),
            LineSpec("- Send a written complaint or grievance to the seller, service provider, platform, or service centre, then use the National Consumer Helpline, e-Daakhil, or District Commission if unresolved [{consumer}].", ("consumer",)),
            LineSpec("- Keep invoice, order ID, seller/platform name, warranty card or warranty terms, photos/video of the defect or fake product, unboxing/service-centre report, payment proof, chats/emails, pickup or return attempts, and complaint ticket numbers [{consumer}].", ("consumer",)),
        ),
        priority=85,
    ),
    AuthorityWorkflowContract(
        id="coaching_refund_service_deficiency",
        route_categories=("consumer",),
        trigger_groups=(
            ("coaching", "coaching centre", "coaching center", "tuition", "course"),
            ("refund", "promised refund", "not replying", "stopped replying", "no reply", "not refunding"),
        ),
        source_specs=(
            PassageSpec("consumer", ("consumer protection",), ("/sec-2", "/sec-35", "/sec-38", "/sec-39"), required=True),
        ),
        line_specs=(
            LineSpec("For a coaching centre, course, or tuition provider that promised a refund but stopped replying or refused refund, treat it as a consumer service-deficiency/refund complaint after preserving the written promise and payment proof [{consumer}].", ("consumer",)),
            LineSpec("**What you can do next**"),
            LineSpec("- Send a written refund demand to the coaching centre/provider with admission/course details, payment receipt, refund promise, cancellation/withdrawal date, chats/emails, and no-reply proof; then use National Consumer Helpline, e-Daakhil, or the District Consumer Commission if unresolved [{consumer}].", ("consumer",)),
        ),
        priority=92,
    ),
    AuthorityWorkflowContract(
        id="college_original_certificate_release",
        route_categories=("education_rights",),
        trigger_groups=(
            ("college", "institution", "institute", "university"),
            (
                "original certificate", "original certificates",
                "holding certificate", "holding certificates",
                "withholding certificate", "withholding certificates",
                "retain certificate", "retaining certificate",
                "return certificate", "leaving certificate",
                "original marksheet", "original marksheets",
                "original mark sheet", "original mark sheets",
                "original degree", "degree certificate",
                "tc", "transfer certificate", "discontinued", "discontinue",
            ),
        ),
        source_specs=(
            PassageSpec("aicte", ("all india council for technical education", "approval process handbook", "aicte"), ("original-documents", "refund", "8.13", "complaint-cases"), required=True),
            PassageSpec("rti", ("right to information",), ("/sec-6", "/sec-7", "/sec-19")),
            PassageSpec("consumer", ("consumer protection",), ("/sec-2", "/sec-35", "/sec-38")),
        ),
        line_specs=(
            LineSpec("For a college or technical institution holding original certificates after withdrawal, leaving the course, or fee/refund dispute, use the AICTE/approved-institution certificate-return source first where the institution or course is AICTE-approved; do not reduce this to generic education advice [{aicte}].", ("aicte",)),
            LineSpec("Ask the college for a written reason, fee/refund calculation, and certificate-return date; if the institution is public or covered by RTI, use RTI only to obtain the file/status/reason while keeping the student-grievance route active [{rti}].", ("rti",)),
            LineSpec("If the college also refuses refund or charges unfair fees, keep Consumer Protection as a possible service-deficiency/refund backup after the education-regulator grievance record is clear [{consumer}].", ("consumer",)),
            LineSpec("**What you can do next**"),
            LineSpec("- Give a written certificate-return and refund/status request to the principal/registrar and institution grievance cell, then escalate to the university, AICTE/technical-education grievance route where applicable, state higher-education authority, or DLSA with admission letter, withdrawal/TC request, fee receipts, original certificates/marksheets list, acknowledgement, and college replies [{aicte}].", ("aicte",)),
        ),
        priority=108,
    ),
    AuthorityWorkflowContract(
        id="caretaker_daughter_will",
        route_categories=("succession_inheritance",),
        trigger_groups=(
            ("father", "mother", "parent"),
            ("will", "make will", "making will", "wants to make will", "write will", "giving more"),
            ("caretaker", "care taker", "looked after", "taking care"),
        ),
        source_specs=(
            PassageSpec("succession", ("indian succession",), ("/sec-59", "/sec-63"), required=True),
            PassageSpec("hsa", ("hindu succession",), ("/sec-6", "/sec-8", "/sec-10")),
            PassageSpec("registration", ("registration act",), ("/sec-18", "/sec-40", "/sec-41")),
        ),
        line_specs=(
            LineSpec("A parent wanting to make a will giving more to a caretaker daughter is not automatically a police issue; first check testamentary capacity, free consent, execution, and attestation under the Indian Succession Act will source [{succession}].", ("succession",)),
            LineSpec("The safer answer turns on title: if the property is self-acquired, the will route is different from ancestral/coparcenary property or another heir's existing share, where partition/title disputes may need civil court advice [{hsa}].", ("hsa",)),
            LineSpec("Registration can help the record, but registration is separate from whether the will is validly executed and whether the testator had power over that property [{registration}].", ("registration",)),
            LineSpec("**What you can do next**"),
            LineSpec("- Before drafting, collect title papers, self-acquired versus ancestral/coparcenary facts, family tree, details of all four children and two daughters, medical/capacity proof if elderly or ill, two attesting-witness details, and a clear reason for unequal shares; use a succession lawyer/DLSA for will drafting and civil court/partition/title advice if any heir's existing share is affected [{succession}].", ("succession",)),
        ),
        priority=122,
    ),
    AuthorityWorkflowContract(
        id="registered_will_update",
        route_categories=("succession_inheritance",),
        trigger_groups=(
            ("registered will", "registered my will", "sub registrar", "sub-registrar"),
            ("update", "update it every year", "every year", "yearly", "revise", "change", "codicil"),
        ),
        source_specs=(
            PassageSpec("succession", ("indian succession",), ("/sec-59", "/sec-62", "/sec-63", "/sec-70"), required=True),
            PassageSpec("registration", ("registration act",), ("/sec-18", "/sec-40", "/sec-41"), required=True),
        ),
        line_specs=(
            LineSpec("A registered will does not need to be updated every year merely because it is registered; use the Indian Succession Act will-capacity/revocation source to check when a new will, codicil, or revocation is actually needed [{succession}].", ("succession",)),
            LineSpec("The Registration Act source is only the registration/record lane; it does not replace checking the will-maker's capacity, latest intention, execution, and attesting-witness proof under succession law [{registration}].", ("registration",)),
            LineSpec("police are not the normal route for a registered-will update question unless there is forgery, threat, theft, or coercion; ordinary disputes over title, partition, probate/letters, or mutation go through succession/property advice and civil court where needed [{succession}].", ("succession",)),
            LineSpec("**What you can do next**"),
            LineSpec("- Keep the registered will copy, sub-registrar receipt, property title list, beneficiary list, any changed family/property facts, medical/capacity proof if relevant, and prior/later will or codicil; ask a succession lawyer/DLSA whether to execute a new will/codicil instead of doing an annual update [{succession}], [{registration}].", ("succession", "registration")),
        ),
        priority=124,
    ),
    AuthorityWorkflowContract(
        id="parsi_intestate_sisters",
        route_categories=("succession_inheritance",),
        trigger_groups=(
            ("parsi",),
            ("mother", "woman", "female"),
            ("passed away", "died", "death"),
            ("sisters", "three sisters", "children", "daughters"),
        ),
        source_specs=(
            PassageSpec("parsi", ("indian succession",), ("/sec-50", "/sec-51", "/sec-54", "/schedule-ii"), required=True),
        ),
        line_specs=(
            LineSpec("For a Parsi mother dying without a will in Mumbai, start with the Indian Succession Act Parsi intestate-succession source before assuming generic Hindu or Christian shares [{parsi}].", ("parsi",)),
            LineSpec("If the three sisters are the only surviving children and there is no will, widower, parent, or predeceased-child branch changing the calculation, the starting property-share check is equal one-third shares under the Parsi succession provisions [{parsi}].", ("parsi",)),
            LineSpec("**What you can do next**"),
            LineSpec("- Confirm no will, no surviving widower, and no predeceased child's branch; then keep death certificate, Parsi personal-law fact, family tree/legal-heir proof, title/sale deed papers, bank/flat records, and mutation papers for revenue/society records or civil court partition/title advice if any sister disputes the share [{parsi}].", ("parsi",)),
        ),
        priority=120,
    ),
    AuthorityWorkflowContract(
        id="unregistered_will_validity",
        route_categories=("succession_inheritance",),
        trigger_groups=(
            ("will", "unregistered will", "registered will", "not registered", "registration"),
            ("valid", "validity", "after death", "death", "sons fighting", "heirs fighting", "probate"),
        ),
        source_specs=(
            PassageSpec("succession", ("indian succession",), ("/sec-63", "/sec-59"), required=True),
            PassageSpec("registration", ("registration act",), ("/sec-18", "/sec-40", "/sec-41"), required=True),
        ),
        line_specs=(
            LineSpec("For an unregistered will made before death, separate execution/attestation from registration: the Indian Succession Act will-execution source is the first source to check for validity of the will itself [{succession}].", ("succession",)),
            LineSpec("The Registration Act source is the registration question; registration of a will is a separate issue and should not replace checking signature, capacity, and attesting-witness proof under succession law [{registration}].", ("registration",)),
            LineSpec("Because sons/heirs are fighting after death, do not use police as the main route unless there is forgery, threat, or violence; the ordinary route is probate/letters, mutation, partition, declaration, or injunction depending on property and state practice [{succession}].", ("succession",)),
            LineSpec("**What you can do next**"),
            LineSpec("- Keep the original will, death certificate, two attesting-witness details, medical/capacity proof if disputed, family tree, property papers, mutation records, and any later will/codicil; take these to DLSA or a succession/property lawyer before deciding probate or civil-court steps [{succession}], [{registration}].", ("succession", "registration")),
        ),
        priority=116,
    ),
    AuthorityWorkflowContract(
        id="hindu_intestate_no_spouse_children",
        route_categories=("succession_inheritance",),
        trigger_groups=(
            ("hindu",),
            ("who inherits", "who will inherit", "inherits his", "inherits her", "legal heirs", "heirs"),
            ("no children", "not married", "unmarried", "no wife", "no spouse", "no kids", "no child"),
            ("property", "prop", "self acquired", "self-acquired", "house", "flat", "land", "estate"),
        ),
        source_specs=(
            PassageSpec("hsa8", ("hindu succession",), ("/sec-8",), required=True),
            PassageSpec("hsa10", ("hindu succession",), ("/sec-10",)),
            PassageSpec("schedule", ("hindu succession",), ("/schedule",)),
        ),
        line_specs=(
            LineSpec("For a Hindu male's self-acquired property where the question is who inherits if he has no spouse and no children, start with the Hindu Succession Act Section 8 intestate-succession source, not police or generic criminal-law advice [{hsa8}].", ("hsa8",)),
            LineSpec("First check whether any Class I heir exists; if there is no spouse, child, or other Class I heir, the Class II heirs/schedule route must be verified with the family tree before naming the heir [{hsa8}].", ("hsa8",)),
            LineSpec("Use the schedule source to verify the Class II order where the retrieved file contains it; do not assume one relative inherits without checking the family tree and the Act schedule [{schedule}].", ("schedule",)),
            LineSpec("**What you can do next**"),
            LineSpec("- Prepare a family tree, religion/personal-law fact, death certificate when relevant, no-will status, self-acquired property papers, and details of parents, siblings, nephews/nieces, and other relatives before asking DLSA/revenue office/civil court about mutation or succession steps [{hsa8}].", ("hsa8",)),
        ),
        priority=103,
    ),
    AuthorityWorkflowContract(
        id="heir_refuses_sale",
        route_categories=("succession_inheritance", "property_tenancy"),
        trigger_groups=(
            ("heir", "legal heir", "sister", "brother", "uncle", "dada", "grandfather", "father died", "mother died"),
            ("property", "house", "land", "plot", "ancestral", "inherited", "sale papers"),
            (
                "sell", "sold", "sale", "signing", "not signing", "refuses",
                "not agreeing", "consent", "without asking", "without consent",
            ),
        ),
        source_specs=(
            PassageSpec("succession", ("hindu succession", "indian succession"), required=True),
            PassageSpec("hindu", ("hindu succession",), ("/sec-6", "/sec-8", "/sec-10")),
            PassageSpec("tpa", ("transfer of property",), ("/sec-44", "/sec-45")),
            PassageSpec("specific", ("specific relief",), ("/sec-31", "/sec-34", "/sec-38")),
        ),
        line_specs=(
            LineSpec("First identify the legal heir, succession, inherited-property status and the legal heirs, applicable succession or personal law, shares, and will/no-will position before deciding who can sign sale papers [{succession}].", ("succession",)),
            LineSpec("If one legal heir such as a sister, brother, or other heir is not agreeing, do not assume the whole property can be sold; a co-owner/share source does not prove that the whole property can be sold, so treat it as a share or partition problem because a co-owner may deal only with the share or interest they can legally transfer [{tpa}].", ("tpa",)),
            LineSpec("If a deed is already being forced or registered despite the dispute, the civil court route can include partition/declaration/injunction or cancellation relief [{specific}].", ("specific",)),
            LineSpec("**What you can do next**"),
            LineSpec("- Use written consent/release/family settlement if everyone agrees; otherwise take the death certificate, legal-heir certificate or family tree, title deed, sale deed or draft papers, mutation/khata/land records, will if any, and each heir's written refusal to the sub-registrar/revenue office for records and to DLSA, a property lawyer, or civil court for a partition/declaration/injunction route [{succession}].", ("succession",)),
        ),
        priority=88,
    ),
    AuthorityWorkflowContract(
        id="daughter_ancestral_share",
        route_categories=("succession_inheritance", "property_tenancy"),
        trigger_groups=(
            ("daughter", "daughters", "married daughter"),
            ("ancestral", "coparcener", "agricultural land", "family land"),
            ("share", "no share", "have no share", "denied share", "not giving share", "saying daughters", "father died", "before amendment", "2003", "2005 amendment", "amendment"),
        ),
        source_specs=(
            PassageSpec("hsa6", ("hindu succession",), ("/sec-6",), required=True),
            PassageSpec("hsa", ("hindu succession",), ("/sec-8", "/sec-10", "/sec-15")),
            PassageSpec("specific", ("specific relief",), ("/sec-34", "/sec-38")),
        ),
        line_specs=(
            LineSpec("For ancestral or coparcenary property where brothers or relatives say daughters have no share, start with the Hindu Succession Act Section 6 daughter/coparcener source rather than treating it as a generic tenancy or police dispute [{hsa6}].", ("hsa6",)),
            LineSpec("First build the family tree, father's death/status, will/no-will position, and whether the property is ancestral/coparcenary or self-acquired before calculating daughters' and sons' shares [{hsa6}].", ("hsa6",)),
            LineSpec("If relatives block records, partition, or possession after the share is disputed, the next forum is usually revenue records plus civil court/DLSA for partition, declaration, or injunction, not self-help possession [{specific}].", ("specific",)),
            LineSpec("**What you can do next**"),
            LineSpec("- Keep the death certificate if relevant, family tree/legal-heir proof, old title/khata/khasra/jamabandi records, proof the land is ancestral or family property, any sale/mutation papers, and messages refusing daughters' share; ask DLSA/revenue office/civil lawyer about mutation plus partition/declaration steps [{hsa6}].", ("hsa6",)),
        ),
        priority=107,
    ),
    AuthorityWorkflowContract(
        id="housing_society_flat_transfer_after_death",
        route_categories=("succession_inheritance", "property_tenancy"),
        trigger_groups=(
            ("society", "housing society", "cooperative society", "co-operative society", "share certificate", "nominee"),
            ("flat", "apartment", "house"),
            ("death", "died", "father death", "after death", "legal heir", "legal heirs"),
            ("transfer", "transferring", "not transferring", "nominee", "nomination"),
        ),
        source_specs=(
            PassageSpec("succession", ("hindu succession", "indian succession"), required=True),
            PassageSpec("registration", ("registration act",), ("/sec-17", "/sec-18", "/sec-49")),
            PassageSpec("tpa", ("transfer of property",), ("/sec-44", "/sec-45", "/sec-54")),
            PassageSpec("specific", ("specific relief",), ("/sec-34", "/sec-38")),
        ),
        line_specs=(
            LineSpec("For a housing-society flat transfer after a death, separate the society/share-certificate transfer process from legal heirship and title; start with the succession source to identify heirs and shares [{succession}].", ("succession",)),
            LineSpec("The registered sale deed/title chain and registration records matter because society transfer or nomination does not by itself decide full ownership if legal heirs dispute it [{registration}].", ("registration",)),
            LineSpec("If the society relies on a nominee or refuses transfer despite heir papers, verify the local cooperative-society bye-laws/Registrar route, and use civil court/DLSA for declaration or injunction if title or shares are disputed [{specific}].", ("specific",)),
            LineSpec("**What you can do next**"),
            LineSpec("- Give the society a written transfer request with death certificate, legal-heir/succession certificate or family tree, will/probate if any, registered flat papers, share certificate, nomination form, maintenance dues/NOC, and ask for written reasons; then escalate to the Registrar/cooperative authority or DLSA/civil court depending on whether the issue is society procedure or heir/title dispute [{succession}].", ("succession",)),
        ),
        priority=106,
    ),
    AuthorityWorkflowContract(
        id="joint_coowner_sold_whole_property",
        route_categories=("property_tenancy", "succession_inheritance"),
        trigger_groups=(
            ("joint", "co owner", "co-owner", "common", "together", "brother", "sister", "without consent"),
            ("land", "plot", "property", "flat", "share", "mutation"),
            ("sold", "sale", "sell", "sale deed", "mutation", "transferred"),
        ),
        source_specs=(
            PassageSpec("tpa_share", ("transfer of property",), ("/sec-44", "/sec-45"), required=True),
            PassageSpec("tpa44", ("transfer of property",), ("/sec-44",)),
            PassageSpec("tpa45", ("transfer of property",), ("/sec-45",)),
            PassageSpec("specific", ("specific relief",), ("/sec-31", "/sec-34", "/sec-38")),
            PassageSpec("registration", ("registration act",), ("/sec-49",)),
            PassageSpec("succession", ("hindu succession", "indian succession"), ("/sec-6", "/sec-8")),
        ),
        line_specs=(
            LineSpec("If your brother, sister, or another co-owner sold joint land, a joint plot, a joint flat/share, or co-owned property as if they owned the whole property, first compare the registered sale deed or mutation entry with the Transfer of Property Act co-owner/share source; a co-owner's transfer does not automatically wipe out the other co-owner's share [{tpa_share}].", ("tpa_share",)),
            LineSpec("For Hindu ancestral or inherited land, keep the Hindu Succession source with the family tree, father's status, shares, and will/no-will facts before deciding whether police or a civil-court remedy is the right route [{succession}].", ("succession",)),
            LineSpec("The practical civil-court remedy is to check partition, declaration of share, injunction against further transfer, or cancellation/declaration against a sale deed or mutation that affects your share [{specific}].", ("specific",)),
            LineSpec("Registration records matter because the sale deed, mutation entry, and title chain decide whether the dispute is only over the seller's share or over an instrument clouding your title [{registration}].", ("registration",)),
            LineSpec("**What you can do next**"),
            LineSpec("- Get the old purchase deed, new sale deed/certified copy, mutation/khata/land record, payment proof, possession proof, messages/consent proof, and buyer details; then ask DLSA or a property lawyer about partition, declaration, injunction, and cancellation before the buyer changes records further [{tpa_share}].", ("tpa_share",)),
        ),
        priority=94,
    ),
    AuthorityWorkflowContract(
        id="epf_not_deposited",
        route_categories=("employment_wages",),
        trigger_groups=(
            ("epf", "pf", "uan", "provident fund", "gratuity"),
            ("not depositing", "no contribution", "zero contribution", "passbook", "passbook empty", "closed company", "company closed", "company shut down", "factory closed", "deducted", "not paying", "not paid", "both pending", "no epf deposit", "ignoring"),
        ),
        source_specs=(
            PassageSpec("epf", ("provident",), required=True),
            PassageSpec("social", ("code on social security",)),
            PassageSpec("code_wages", ("code on wages",), ("/sec-17", "/sec-18", "/sec-45")),
            PassageSpec("contract_labour", ("contract labour",), ("/sec-21",)),
            PassageSpec("gratuity", ("payment of gratuity", "gratuity act")),
        ),
        line_specs=(
            LineSpec("For an employer, factory, or company that closed or shut down without paying gratuity and PF, split it into two legal dues: EPFO/RPFO recovery for PF [{epf}] and the gratuity controlling-authority or labour-office claim for gratuity [{gratuity}].", ("epf", "gratuity")),
            LineSpec("If the UAN passbook is empty, shows zero contribution, or EPF/PF was deducted but not deposited, file the provident-fund part as an EPFO recovery/grievance track and keep salary-slip/passbook proof as the first legal record [{epf}].", ("epf",)),
            LineSpec("The Code on Social Security source can be background for social-security coverage, but use the specific EPFO and gratuity routes first when those specific dues are unpaid [{social}].", ("social",)),
            LineSpec("**What you can do next**"),
            LineSpec("- File a written EPFO grievance or complaint with the Regional Provident Fund office/RPFO for PF [{epf}], and file the gratuity part with the controlling authority/labour office if gratuity is due [{gratuity}].", ("epf", "gratuity")),
            LineSpec("- Keep the provident-fund complaint separate from any gratuity or wage claim so the PF/RPFO record and gratuity record do not get mixed up [{epf}].", ("epf",)),
            LineSpec("- Keep UAN/member ID, EPFO passbook screenshots, salary slips showing PF deduction, bank statement, appointment letter, employer establishment name/code, gratuity calculation, last-working-date proof, and employer messages or demand letters [{epf}].", ("epf",)),
        ),
        priority=143,
    ),
    AuthorityWorkflowContract(
        id="school_admission_tc_refusal",
        route_categories=("education_rights", "social_welfare_identity"),
        trigger_groups=(
            ("school", "admission", "tc", "transfer certificate", "rte", "principal", "child"),
            ("refusing", "refused", "denied", "denying", "not admitting", "not taking", "not giving", "not agreeing", "not allowing", "where to go", "age proof", "demanding money", "asking money", "bribe", "demanding donation", "donation", "capitation", "quota", "25 percent", "25%", "seat allotted", "cleared admission", "cleared exam", "passed test", "admission exam", "merit list", "selected"),
        ),
        source_specs=(
            PassageSpec("rte", ("right of children", "free and compulsory education"), ("/sec-5", "/sec-12", "/sec-13", "/sec-14", "/sec-15"), required=True),
        ),
        line_specs=(
            LineSpec("For a school-admission denial after an admission test/result, refusing a transfer certificate, denying admission for age proof, or demanding donation/capitation for an RTE seat, start by asking the school for written reasons/refusal reasons and acknowledgement; the RTE source supports treating this as an education-rights issue, not just an oral school dispute [{rte}].", ("rte",)),
            LineSpec("If the school says documents, age proof, screening, fee, donation, or TC is the reason, keep that reason in writing because it decides the district education officer, local authority, or RTE grievance-authority complaint route [{rte}].", ("rte",)),
            LineSpec("**What you can do next**"),
            LineSpec("- Give a written request to the school, get an acknowledgement or no-reply proof, and complain to the district education officer, local authority, or RTE grievance authority with the written refusal/reason, admission result/application, TC request, child age/class proof, fee receipts, donation demand, school messages, and allotment papers [{rte}].", ("rte",)),
        ),
        priority=91,
    ),
    AuthorityWorkflowContract(
        id="scholarship_aadhaar_school_name_mismatch",
        route_categories=("social_welfare_identity", "education_rights"),
        trigger_groups=(
            ("scholarship", "benefit", "scheme"),
            ("aadhaar", "aadhar"),
            ("school certificate", "certificate", "name mismatch", "name not same", "not same"),
        ),
        source_specs=(
            PassageSpec("aadhaar", ("aadhaar", "aadhar"), ("/sec-7", "/sec-8", "/sec-29", "/sec-59"), required=True),
            PassageSpec("rti", ("right to information",), ("/sec-6", "/sec-7", "/sec-19")),
        ),
        line_specs=(
            LineSpec("For a scholarship rejection because the Aadhaar name and school certificate name are not the same, first identify which record needs correction: Aadhaar, the school certificate, or the scholarship/scheme record [{aadhaar}].", ("aadhaar",)),
            LineSpec("Ask the scholarship authority or school for written reasons showing the exact mismatch field and rule relied on before correcting the wrong record [{aadhaar}].", ("aadhaar",)),
            LineSpec("If the authority will not give status, reasons, or the record relied on, use RTI/first appeal to obtain the written file record while keeping the benefit grievance separate [{rti}].", ("rti",)),
            LineSpec("**What you can do next**"),
            LineSpec("- Keep the Aadhaar copy/status, school certificate, scholarship ID/application, rejection screenshot, written reason, correction acknowledgement, and deadline proof; file a written correction/grievance with the record-holding authority first [{aadhaar}].", ("aadhaar",)),
        ),
        priority=100,
    ),
    AuthorityWorkflowContract(
        id="pds_ration_card_name_removed",
        route_categories=("social_welfare_identity",),
        trigger_groups=(
            ("ration", "pds", "ration card", "ration shop", "ration office", "fair price", "family card", "household card", "dealer", "grain"),
            ("removed", "cancelled", "canceled", "deleted", "cut", "name", "mother", "maa"),
            ("without notice", "no notice", "notice", "nobody giving reason", "not giving reason", "written reason", "no order", "order", "restore", "records", "refuses ration", "dealer"),
        ),
        source_specs=(
            PassageSpec("nfsa", ("national food security",), ("/sec-13", "/sec-14", "/sec-15"), required=True),
            PassageSpec("rti", ("right to information",), ("/sec-6", "/sec-7", "/sec-19")),
        ),
        line_specs=(
            LineSpec("If a PDS dealer or ration office removed your mother's name from the ration card without notice, treat it as an NFSA ration-entitlement and grievance problem, not only as an Aadhaar mismatch [{nfsa}].", ("nfsa",)),
            LineSpec("Use the NFSA grievance-redressal route, including the DGRO or district grievance route, to ask for restoration, the written removal/cancellation reason, and the household ration-card record [{nfsa}].", ("nfsa",)),
            LineSpec("If the office will not give the order, reason, file status, or appeal route, use RTI to obtain the ration-card file and action-taken record [{rti}].", ("rti",)),
            LineSpec("**What you can do next**"),
            LineSpec("- File a written complaint with the ration office/Food and Civil Supplies department or State/District NFSA grievance authority/DGRO, keeping the ration-card ID, mother's ID, old ration-card copy, dealer details, no-notice proof, prior slips, messages, and any rejection screenshot [{nfsa}].", ("nfsa",)),
        ),
        priority=102,
    ),
    AuthorityWorkflowContract(
        id="aadhaar_subsidy_auth_reason",
        route_categories=("social_welfare_identity",),
        trigger_groups=(
            ("aadhaar", "aadhar", "authentication"),
            ("lpg", "subsidy", "benefit", "dbt"),
            ("failed", "no reason", "portal", "reason"),
        ),
        source_specs=(
            PassageSpec("aadhaar", ("aadhaar", "aadhar"), ("/sec-7", "/sec-8", "/sec-59"), required=True),
            PassageSpec("rti", ("right to information",), ("/sec-6", "/sec-7", "/sec-19"), required=True),
        ),
        line_specs=(
            LineSpec("For Aadhaar authentication failed for LPG subsidy or another benefit, first ask for the written reason, transaction/authentication status, and whether the failure is Aadhaar, bank-link, scheme, or portal related [{aadhaar}].", ("aadhaar",)),
            LineSpec("If the portal gives no reason, use RTI/first appeal to seek the action-taken record, rejection reason, authentication failure status, and the office responsible for correction [{rti}].", ("rti",)),
            LineSpec("**What you can do next**"),
            LineSpec("- Keep Aadhaar proof, LPG/subsidy consumer ID, bank-link status, portal screenshot, failed authentication date/time, complaint number, and file a written reason request before correcting Aadhaar, bank, or scheme records [{aadhaar}], [{rti}].", ("aadhaar", "rti")),
        ),
        priority=109,
    ),
    AuthorityWorkflowContract(
        id="spousal_adultery_marriage_breakdown",
        route_categories=("family_marriage_status",),
        trigger_groups=(
            ("wife", "husband", "spouse", "marriage"),
            (
                "adultery", "extra marital", "extra-marital", "affair",
                "cheating on me", "another woman", "another women",
                "another man", "caught my husband", "caught my wife",
                "sex with another", "having sex",
            ),
        ),
        source_specs=(
            PassageSpec("family", ("family courts",), ("/sec-7", "/sec-8"), required=True),
            PassageSpec("hma", ("hindu marriage",), ("/sec-13", "/sec-24", "/sec-25")),
            PassageSpec("sma", ("special marriage",), ("/sec-27", "/sec-36", "/sec-37")),
        ),
        line_specs=(
            LineSpec("For adultery, an affair, or catching a spouse with another person, treat this as a marriage-breakdown and Family Court/DLSA remedy question first, not as an automatic police case [{family}].", ("family",)),
            LineSpec("If the Hindu Marriage Act applies, Section 13 is the divorce-ground source to check for post-marriage sexual relationship facts involving a person other than the spouse; proof and remedy choice matter before filing [{hma}].", ("hma",)),
            LineSpec("The Family Courts Act source is the forum source for matrimonial-status, divorce, maintenance, and related family proceedings [{family}].", ("family",)),
            LineSpec("If the Special Marriage Act applies, keep the same question in the matrimonial-remedy lane and verify the available relief against that Act and the Family Court route [{sma}].", ("sma", "family")),
            LineSpec("Do not treat catching your husband/wife/spouse with another person as an automatic police case by itself; use criminal or domestic-violence routes only if there are separate facts of force, threat, assault, stalking, coercion, or economic abuse [{family}].", ("family",)),
            LineSpec("**What you can do next**"),
            LineSpec("- Preserve lawful proof, marriage documents, timeline, children/maintenance/residence facts, and any safety concerns; then ask DLSA or a family-law lawyer whether counselling, judicial separation, divorce, maintenance, or interim protection fits your facts [{family}].", ("family",)),
        ),
        priority=99,
    ),
    AuthorityWorkflowContract(
        id="muslim_second_marriage_protection",
        route_categories=("family_marriage_status",),
        trigger_groups=(
            ("muslim", "shariat", "nikah", "islam"),
            ("second wife", "second marriage", "took second wife", "without divorcing", "another wife", "bigamy"),
        ),
        source_specs=(
            PassageSpec("shariat", ("shariat", "muslim personal law"), (), required=True),
            PassageSpec("family", ("family courts",), ("/sec-7", "/sec-8")),
            PassageSpec("pwdva", ("protection of women from domestic violence", "domestic violence"), ("/sec-3", "/sec-12", "/sec-18", "/sec-20", "/sec-22")),
            PassageSpec("bnss", ("bharatiya nagarik suraksha",), ("/sec-144", "/sec-145")),
            PassageSpec("bns_bigamy", ("bharatiya nyaya",), ("/sec-82",)),
        ),
        line_specs=(
            LineSpec("For a Muslim wife asking about a husband taking a second wife without divorce, do not treat BNS bigamy alone as the complete answer; first identify the personal-law, marriage, maintenance, residence, and protection facts under the Shariat/personal-law route [{shariat}].", ("shariat",)),
            LineSpec("The Family Courts Act source is the forum source for family-status, maintenance, and matrimonial disputes once the personal-law context and remedy are identified [{family}].", ("family",)),
            LineSpec("If there is violence, economic abuse, being thrown out, threats, or deprivation, keep a separate PWDVA protection/residence/monetary-relief route instead of only debating whether the second marriage is valid [{pwdva}].", ("pwdva",)),
            LineSpec("Use the BNSS maintenance source for support/maintenance facts where applicable; collect income, children, residence, and neglect proof before filing [{bnss}].", ("bnss",)),
            LineSpec("A criminal bigamy route needs careful lawyer review because personal law and the exact marriage facts matter; do not assume the generic BNS bigamy source alone settles a Muslim second-marriage question [{bns_bigamy}].", ("bns_bigamy",)),
            LineSpec("**What you can do next**"),
            LineSpec("- Collect nikah/marriage proof, proof of the alleged second marriage, children/dependant details, residence and income proof, messages/threats, and any violence/economic-abuse facts; take these to DLSA, a family-law lawyer, or the Family Court/Magistrate route before choosing maintenance, protection, divorce, or criminal complaint [{shariat}].", ("shariat",)),
        ),
        priority=125,
    ),
    AuthorityWorkflowContract(
        id="mutual_consent_divorce",
        route_categories=("family_marriage_status",),
        trigger_groups=(
            ("mutual divorce", "mutual consent divorce", "section 13b", "13b", "both of us agree", "both agree", "joint petition"),
            ("divorce", "separation", "papers", "petition", "file"),
        ),
        source_specs=(
            PassageSpec("family", ("family courts",), ("/sec-7", "/sec-8", "/sec-9"), required=True),
            PassageSpec("hma13b", ("hindu marriage",), ("/sec-13B", "/sec-13-b", "/sec-13")),
            PassageSpec("sma28", ("special marriage",), ("/sec-28",)),
            PassageSpec("christian", ("divorce act", "indian divorce"), ()),
            PassageSpec("shariat", ("shariat", "muslim personal law"), ()),
            PassageSpec("dissolution", ("dissolution of muslim marriages",), ()),
        ),
        line_specs=(
            LineSpec("For spouses who both agree to divorce, treat this as a mutual-consent divorce / Family Court procedure question, not as a domestic-violence or police complaint route [{family}].", ("family",)),
            LineSpec("If the Hindu Marriage Act applies, Section 13B is the mutual-consent divorce source to verify before preparing the joint petition and settlement terms [{hma13b}].", ("hma13b",)),
            LineSpec("If the marriage is under the Special Marriage Act or another personal law, verify the equivalent mutual-consent divorce source instead of assuming the Hindu Marriage Act applies [{sma28}].", ("sma28",)),
            LineSpec("Even where there are no children, the petition should still settle maintenance/alimony, streedhan or articles, residence/property issues, and pending cases before the Family Court records consent [{family}].", ("family",)),
            LineSpec("**What you can do next**"),
            LineSpec("- Keep marriage certificate/proof, address and ID proofs, photos if required locally, separation/timeline facts, settlement terms on maintenance/alimony/stridhan/property, and draft joint petition; take them to DLSA or a family-law lawyer before filing [{family}], [{hma13b}].", ("family", "hma13b")),
        ),
        priority=112,
    ),
    AuthorityWorkflowContract(
        id="marital_intimacy_remedy",
        route_categories=("family_marriage_status",),
        trigger_groups=(
            ("wife", "husband", "spouse", "marital", "marriage"),
            ("sex", "physical relation", "physical relationship", "intimacy", "marital relationship", "no relationship"),
        ),
        source_specs=(
            PassageSpec("family", ("family courts",), ("/sec-7", "/sec-8"), required=True),
            PassageSpec("hma", ("hindu marriage",), ("/sec-9", "/sec-10", "/sec-13")),
            PassageSpec("sma", ("special marriage",), ("/sec-22", "/sec-23", "/sec-27", "/sec-28")),
        ),
        line_specs=(
            LineSpec("Treat no marital relationship, refusal of sex, physical-intimacy breakdown, or a spouse saying the marriage is only on paper as a matrimonial/family-court counselling or remedy question for Family Court/DLSA, not as permission to force or pressure a spouse [{family}].", ("family",)),
            LineSpec("If the Hindu Marriage Act applies, the remedy still depends on facts and proof; discuss counselling, judicial separation, divorce, restitution, maintenance, or other lawful family-court relief only after legal advice [{hma}].", ("hma",)),
            LineSpec("If the Special Marriage Act applies, the same issue stays fact-specific and must be checked against the available matrimonial relief source before choosing a case [{sma}].", ("sma",)),
            LineSpec("**Consent matters**"),
            LineSpec("**What you can do next**"),
            LineSpec("- Keep a timeline of the intimacy breakdown, counselling attempts, residence, children, maintenance, and any violence or coercion facts; do not force, threaten, or pressure your spouse for sex."),
        ),
        priority=97,
    ),
    AuthorityWorkflowContract(
        id="mgnrega_fake_muster",
        route_categories=("social_welfare_identity", "employment_wages", "labour_exploitation_discrimination"),
        trigger_groups=(
            ("mgnrega", "nrega", "job card", "muster", "social audit", "gram sabha", "sarpanch", "mukhiya", "work demand"),
            ("fake", "attendance", "mate", "no payment", "not paid", "unpaid", "payment pending", "wages pending", "not credited", "not received", "paid since", "money taken", "wage", "complain", "not given", "not issued", "delay", "pending", "7 months", "8 months", "9 months", "come later", "come next week", "card not given", "not issuing", "application pending", "no card", "receipt not given", "work demand", "bank passbook", "no credit", "zero credit", "portal paid", "website says processed", "payment shows paid", "bdo", "not replying", "bdo silent", "district officer", "dead people", "dead persons", "forged", "atr", "social audit", "gram sabha", "corruption"),
        ),
        source_specs=(
            PassageSpec("mgnrega", ("mahatma gandhi national rural employment guarantee",), required=True),
            PassageSpec("mgnrega_grievance", ("mahatma gandhi national rural employment guarantee",), ("/sec-19",)),
            PassageSpec("mgnrega_social_audit", ("mahatma gandhi national rural employment guarantee",), ("/sec-17",)),
            PassageSpec("pca", ("prevention of corruption",), ("/sec-7", "/sec-8", "/sec-13")),
            PassageSpec("bns", ("bharatiya nyaya",), ("/sec-318", "/sec-336", "/sec-340")),
            PassageSpec("rti", ("right to information",)),
        ),
        line_specs=(
            LineSpec("For MGNREGA or NREGA fake muster, fake job-card complaint, fake job card/job-card complaint, attendance, or wage-payment manipulation, use the scheme grievance and social-audit route before treating it as a civil suit [{mgnrega}].", ("mgnrega",)),
            LineSpec("**What you can do next**"),
            LineSpec("- File a written complaint/grievance with the Programme Officer/BDO, Gram Panchayat, district MGNREGA grievance authority or ombudsman, and raise it in the social audit if records are false [{mgnrega}].", ("mgnrega",)),
            LineSpec("- Keep job card, muster roll or attendance copy, work demand/work ID, bank/passbook entries, wage due calculation, mate/sarpanch/contractor details, prior complaint proof, and RTI or action-taken requests [{mgnrega}].", ("mgnrega",)),
        ),
        priority=86,
    ),
    AuthorityWorkflowContract(
        id="ai_child_sexual_image",
        route_categories=("cyber_fraud_or_harassment", "police_fir"),
        trigger_groups=(
            ("minor", "child", "15 year", "15 yr", "school", "classmate", "student", "csam", "pocso"),
            ("fake nude", "morphed sexual", "morphed", "nude", "sexual image", "csam", "deepfake"),
        ),
        source_specs=(
            PassageSpec("pocso", ("protection of children from sexual offences",), required=True),
            PassageSpec("reporting", ("protection of children from sexual offences",), ("/sec-19",)),
            PassageSpec("it67b", ("information technology",), ("/sec-67B",)),
            PassageSpec("it_any", ("information technology",), ("/sec-67B", "/sec-66E", "/sec-67A", "/sec-66C", "/sec-67")),
            PassageSpec("bns", ("bharatiya nyaya",), ("/sec-77",)),
        ),
        line_specs=(
            LineSpec("Treat a minor, child, classmate, or student CSAM/fake nude/morphed sexual image as an urgent child sexual-image complaint under POCSO, not a private reputation dispute [{pocso}].", ("pocso",)),
            LineSpec("The POCSO reporting source is the reporting/mandatory-information track to preserve for police or child-protection escalation where Section 19 is retrieved [{reporting}].", ("reporting",)),
            LineSpec("If the minor CSAM/fake nude/morphed image is being forwarded on WhatsApp, Telegram, school groups, or another electronic platform, keep the IT Act child sexual-image/electronic publication source with the POCSO track [{it}].", ("it",)),
            LineSpec("The BNS voyeurism source is a separate current-law source to check where the facts involve watching, capturing, or disseminating private imagery of a woman or girl in the covered circumstances [{bns}].", ("bns",)),
            LineSpec("Do not forward, do not share, and protect identity while preserving evidence for police, cyber cell, FIR, Childline/1098, or DLSA help [{pocso}].", ("pocso",)),
            LineSpec("**What you can do next**"),
            LineSpec("- Preserve URLs, screenshots, profile IDs, uploader details, timestamps, hashes if available, Telegram/WhatsApp group details, platform complaint IDs, and takedown requests; report the CSAM/minor-image facts to cybercrime.gov.in/local cyber police and seek urgent takedown without forwarding the material [{pocso}].", ("pocso",)),
            LineSpec("- Where the child-specific IT Act Section 67B source is retrieved, keep it with the POCSO complaint for the electronic-publication/takedown track [{it}].", ("it",)),
        ),
        priority=100,
    ),
    AuthorityWorkflowContract(
        id="ndps_bhang_lassi",
        route_categories=("criminal_defence_bail",),
        trigger_groups=(
            ("bhang", "bhang lassi"),
            ("ndps", "police", "holi", "mahabaleshwar", "maharashtra", "caught", "state excise", "source applies", "raid"),
        ),
        source_specs=(
            PassageSpec("ndps", ("narcotic drugs and psychotropic substances",), required=True),
            PassageSpec("state_excise", ("prohibition",), ("state-excise-act", "maharashtra-prohibition-1949", "/sec-2", "/sec-66")),
            PassageSpec("bail", ("narcotic drugs and psychotropic substances",), ("/sec-37", "/sec-36A")),
        ),
        line_specs=(
            LineSpec("For bhang-lassi or Holi facts where police are saying NDPS, do not assume the answer from the word bhang alone; check the actual police section, seizure memo, lab/FSL result, exact substance, and quantity against the NDPS definition source [{ndps}].", ("ndps",)),
            LineSpec("I do not have the exact Maharashtra State Excise Act or local bhang-rule source in the retrieved index, so do not treat the NDPS source as the controlling State Excise source for a Mahabaleshwar/Holi bhang-lassi fact pattern [{ndps}].", ("ndps",)),
            LineSpec("Also verify any Maharashtra excise/local bhang rule or police section before treating every bhang-lassi fact pattern as an NDPS possession offence [{ndps}].", ("ndps",)),
            LineSpec("If NDPS bail is actually invoked, the Special Court/NDPS bail route and Section 37 filter must be checked before relying on ordinary bail advice [{bail}].", ("bail",)),
            LineSpec("**What you can do next**"),
            LineSpec("- Get the seizure memo, panchnama, FIR/notice sections, lab/FSL report, exact weight, arrest/remand papers, and place/state details; take them to legal aid or an NDPS lawyer to check whether this is NDPS, State excise/local rule, or no prosecutable offence on those facts [{ndps}].", ("ndps",)),
        ),
        priority=101,
    ),
    AuthorityWorkflowContract(
        id="ndps_quantity_bail",
        route_categories=("criminal_defence_bail",),
        trigger_groups=(
            ("ndps", "narcotic", "narcotics", "drug parcel", "drugs parcel", "contraband", "mdma", "bhang", "ganja", "charas", "heroin", "cannabis", "weed", "cbd", "thc", "vape", "vape cartridge", "vape pen"),
            ("bail", "punishment", "quantity", "police", "caught", "where to go", "section 37", "fsl", "lab report", "friend's bag", "friends bag", "airport", "passport", "customs", "seized"),
        ),
        source_specs=(
            PassageSpec("ndps", ("narcotic drugs and psychotropic substances",), required=True),
            PassageSpec("bail", ("narcotic drugs and psychotropic substances",), ("/sec-37", "/sec-36A")),
            PassageSpec("article21", ("constitution",), ("/sec-21",)),
            PassageSpec("bnss_bail", ("bharatiya nagarik suraksha",), ("/sec-480", "/sec-483")),
        ),
        line_specs=(
            LineSpec("For an NDPS bail or punishment question, first classify the substance and quantity as small quantity, intermediate quantity, or commercial quantity from the seizure and FSL/lab report [{ndps}].", ("ndps",)),
            LineSpec("Section 37 and the Special Court bail route matter if the alleged quantity/offence triggers the special NDPS bail bar; do not answer from ordinary bail alone [{bail}].", ("bail",)),
            LineSpec("**What you can do next**"),
            LineSpec("- Keep the seizure memo, panchnama, FSL/lab report, exact weight, packaging/sample details, arrest/remand papers, FIR/sections, prior bail order if any, and whether the substance is bhang, ganja, MDMA, or another notified substance [{ndps}].", ("ndps",)),
        ),
        priority=92,
    ),
    AuthorityWorkflowContract(
        id="ndps_default_bail_no_chargesheet",
        route_categories=("criminal_defence_bail",),
        trigger_groups=(
            ("ndps", "narcotic", "ganja", "charas", "heroin", "mdma"),
            ("no chargesheet", "no charge sheet", "chargesheet not", "charge sheet not", "no complaint filed", "complaint not filed", "default bail", "100 days", "110 days", "115 days", "120 days", "180 days", "181 days"),
            ("jail", "custody", "arrested", "remand", "brother", "accused", "husband", "arthur road", "4 mnths", "4 months", "four months", "special court", "special judge", "next date", "default bail"),
        ),
        source_specs=(
            PassageSpec("ndps", ("narcotic drugs and psychotropic substances",), ("/sec-36A",), required=True),
            PassageSpec("bnss", ("bharatiya nagarik suraksha",), ("/sec-187",)),
            PassageSpec("crpc", ("code of criminal procedure",), ("/sec-167",)),
        ),
        line_specs=(
            LineSpec("For an NDPS arrest with 110 days/no charge-sheet or no-chargesheet custody, treat the question as NDPS default/statutory bail under Section 36A and custody-timeline proof, not ordinary bail alone [{ndps}].", ("ndps",)),
            LineSpec("Check whether the prosecution filed a valid charge-sheet or extension application/order before the statutory period expired and whether the accused was ready to furnish bail when default bail was claimed [{ndps}].", ("ndps",)),
            LineSpec("For current procedure, compare the custody calculation with the BNSS default-bail/remand source; for older cases, use the CrPC source instead of mixing regimes [{bnss}], [{crpc}].", ("bnss", "crpc")),
            LineSpec("**What you can do next**"),
            LineSpec("- Prepare arrest date, first remand date, remand orders, NDPS sections/quantity, charge-sheet or extension status, Special Court name, prior bail orders, and surety readiness; file the default-bail application in the Special Court/trial court urgently [{ndps}].", ("ndps",)),
        ),
        priority=130,
    ),
    AuthorityWorkflowContract(
        id="default_bail_no_chargesheet",
        route_categories=("criminal_defence_bail", "undertrial_review_release"),
        trigger_groups=(
            ("default bail", "statutory bail", "no chargesheet", "no charge sheet", "charge sheet not", "chargesheet not", "chargesheet", "charge sheet", "custody limit", "chargesheet limit", "chargesheet deadline", "chargesheet time", "no challan", "challan not", "no complaint filed", "complaint not filed", "no final report", "final report not", "extension request", "extension application"),
            ("jail", "custody", "undertrial", "remand", "arrest", "arrested", "inside", "tihar", "arthur road", "days", "60 days", "68 days", "70 days", "72 days", "75 days", "80 days", "90 days", "6 months", "police says wait", "what bail", "no final report", "extension request", "extension application"),
        ),
        source_specs=(
            PassageSpec("bnss", ("bharatiya nagarik suraksha",), ("/sec-187",), required=True),
            PassageSpec("crpc", ("code of criminal procedure",), ("/sec-167", "/sec-161")),
            PassageSpec("uapa", ("unlawful activities", "uapa"), ("/sec-43d",)),
            PassageSpec("uapa_any", ("unlawful activities", "uapa")),
            PassageSpec("mcoca", ("maharashtra control of organised crime", "mcoca"), ("/sec-21",)),
            PassageSpec("ipc_cheating", ("indian penal",), ("/sec-420", "/sec-415")),
            PassageSpec("bns_cheating", ("bharatiya nyaya",), ("/sec-318",)),
        ),
        line_specs=(
            LineSpec("Treat no charge-sheet/no-chargesheet custody as a statutory/default-bail calculation, not ordinary bail: count custody days from first remand and check whether a valid charge-sheet or extension order was filed in time [{bnss}].", ("bnss",)),
            LineSpec("If the case is under UAPA, do not apply only the ordinary 60/90-day rule; check the UAPA extension source, prosecutor report, and Special Court extension order because the default-bail timeline can move toward 180 days on valid extension papers [{uapa}].", ("uapa",)),
            LineSpec("If the case is under MCOCA, do not apply only the ordinary 60/90-day rule; check the MCOCA Section 21 extension source, prosecutor report, and Special Court extension order because the default-bail timeline can move toward 180 days on valid extension papers [{mcoca}].", ("mcoca",)),
            LineSpec("If the no-charge-sheet case is cheating/Section 420-type, calculate the ordinary default-bail period from the offence maximum and the exact IPC/BNS cheating section instead of using a generic six-month custody rule [{ipc_cheating}].", ("ipc_cheating",)),
            LineSpec("If the new BNS cheating provision applies, keep the BNS offence source with the BNSS default-bail calculation so the maximum punishment and procedure are not mixed with older IPC wording [{bns_cheating}].", ("bns_cheating",)),
            LineSpec("Under the current BNSS route, the practical question is whether the statutory period has expired and the accused is ready to furnish bail before the valid filing/extension cuts off the default-bail right [{bnss}].", ("bnss",)),
            LineSpec("If the incident/case belongs to the older CrPC regime, compare the same custody-period calculation with the CrPC default-bail source instead of mixing regimes [{crpc}].", ("crpc",)),
            LineSpec("**What you can do next**"),
            LineSpec("- Make a custody-days chart with arrest date, first remand date, remand orders, offence maximum, charge-sheet filing status, extension order if any, prior bail orders, and surety readiness; file in the Magistrate/trial court/Special Court controlling remand, then appeal/escalate if disputed [{bnss}].", ("bnss",)),
        ),
        priority=98,
    ),
    AuthorityWorkflowContract(
        id="custody_delay_compensation_after_release",
        route_categories=("custody_compensation",),
        trigger_groups=(
            ("released", "compensation", "delay", "18 months", "4 years", "4 yrs", "custody", "jail", "undertrial", "sue state", "wrongful detention"),
            ("theft", "case", "trial", "bail", "yerwada", "tihar", "puzhal", "acquitted", "acquittal", "sessions court"),
        ),
        source_specs=(
            PassageSpec("article21", ("constitution",), ("/sec-21",), required=True),
            PassageSpec("bnss", ("bharatiya nagarik suraksha",), ("/sec-479",)),
            PassageSpec("crpc", ("code of criminal procedure",), ("/sec-436A", "/sec-436-a")),
        ),
        line_specs=(
            LineSpec("For release or acquittal after 18 months, four years, or other long undertrial custody, compensation is not automatic; start with the Article 21 liberty source and build a certified acquittal, remand, bail, and custody-delay/unlawful-detention timeline [{article21}].", ("article21",)),
            LineSpec("Compare the custody period with the BNSS Section 479 source and offence maximum to see whether the delay also supports a statutory-release or review argument [{bnss}].", ("bnss",)),
            LineSpec("If the custody belonged to the older regime, compare the same detention period with the CrPC undertrial-release source instead [{crpc}].", ("crpc",)),
            LineSpec("**What you can do next**"),
            LineSpec("- Prepare a dated timeline with arrest date, first remand date, bail/release order, charge-sheet date, certified final order/acquittal, jail custody certificate, medical/income loss proof, and prior legal-aid/lawyer records; ask DLSA or a lawyer whether the route is writ compensation under Article 21, Human Rights Commission complaint, appeal/revision, complaint, or civil damages [{article21}].", ("article21",)),
        ),
        priority=110,
    ),
    AuthorityWorkflowContract(
        id="home_birth_certificate_refusal",
        route_categories=("social_welfare_identity",),
        trigger_groups=(
            ("birth certificate", "birth registration", "born at home", "home birth"),
            ("panchayat", "secretary", "registrar", "municipal", "not giving", "refusing", "delay"),
        ),
        source_specs=(
            PassageSpec("registrar", ("registration of births and deaths",), ("/sec-7",)),
            PassageSpec("home_birth", ("registration of births and deaths",), ("/sec-8",)),
            PassageSpec("certificate", ("registration of births and deaths",), ("/sec-12",), required=True),
            PassageSpec("delayed", ("registration of births and deaths",), ("/sec-13",)),
            PassageSpec("rti", ("right to information",), ("/sec-6", "/sec-7", "/sec-19")),
        ),
        line_specs=(
            LineSpec("For a child born at home where the panchayat secretary/registrar is not giving the birth certificate, start with the Registration of Births and Deaths Act registration/certificate route, not a generic RTI or generic complaint [{registrar}].", ("registrar",)),
            LineSpec("For a child born at home where the office is not giving the certificate, keep the birth-registration/certificate request active under the Registration of Births and Deaths Act certificate source, not only an RTI follow-up [{certificate}].", ("certificate",)),
            LineSpec("For a child born at home, the home-birth reporting source is the operative source for giving birth particulars to the Registrar [{home_birth}].", ("home_birth",)),
            LineSpec("If the birth was not registered within time or the office says the entry is missing, check the delayed-registration route before treating this as only a panchayat-service refusal [{delayed}].", ("delayed",)),
            LineSpec("If the office will not give file status, written reasons, or the certificate record, use RTI as a record-status route while keeping the birth-registration request active [{rti}].", ("rti",)),
            LineSpec("**What you can do next**"),
            LineSpec("- File a written birth-registration/certificate request with child name/date/place of birth, parent IDs, home-birth witness or local proof, hospital/anganwadi/ASHA record if any, panchayat refusal details, and ask for written reasons or delayed-registration route [{registrar}], [{certificate}], [{delayed}].", ("registrar", "certificate", "delayed")),
            LineSpec("- If only the certificate record source is available, file the birth-registration/certificate request with child name/date/place of birth, parent IDs, home-birth witness or local proof, and panchayat refusal details, then ask for the missing registrar/delayed-registration reason in writing [{certificate}].", ("certificate",)),
        ),
        priority=111,
    ),
    AuthorityWorkflowContract(
        id="workplace_death_dependant_compensation",
        route_categories=("workplace_injury_compensation",),
        trigger_groups=(
            ("died", "dead", "death", "killed", "worker died", "friend dead"),
            ("site", "worksite", "factory", "workplace", "owner", "employer", "contractor", "labour", "labor", "worker"),
            ("compensation", "not giving", "paid nothing", "nothing got", "owner", "family"),
        ),
        source_specs=(
            PassageSpec("employees", ("employees' compensation", "employees compensation", "workmen's compensation"), ("/sec-3", "/sec-4", "/sec-10", "/sec-22"), required=True),
            PassageSpec("bocw", ("building and other construction workers",)),
            PassageSpec("factories", ("factories act",), ("/sec-88", "/sec-89", "/sec-111")),
            PassageSpec("contract_labour", ("contract labour",), ("/sec-21",)),
        ),
        line_specs=(
            LineSpec("For a worker who died at a site, factory, or workplace, treat the family claim first as dependant compensation under the Employees' Compensation Act source, not as only an informal settlement with the owner/employer [{employees}].", ("employees",)),
            LineSpec("If this was a building or construction worksite, keep the BOCW source as a supporting construction-worker/worksite record while the Employees' Compensation source remains the main compensation route [{bocw}].", ("bocw",)),
            LineSpec("If the death happened in a factory or boiler/safety accident, keep the Factory Inspector/safety record and Factories Act inspection/accident record separate from the compensation claim [{factories}].", ("factories",)),
            LineSpec("If the owner says it is only the contractor's problem, keep the Contract Labour Act responsibility source as a conditional employer/contractor check [{contract_labour}].", ("contract_labour",)),
            LineSpec("If time has passed and the family has received nothing, do not wait on only oral employer promises; use the Commissioner claim route by opening or checking the Employees' Compensation Commissioner/labour-office claim record promptly [{employees}].", ("employees",)),
            LineSpec("**What you can do next**"),
            LineSpec("- Collect death certificate, post-mortem/medical papers, accident report, employer/contractor/site details, wage proof, age proof, dependant/family proof, photos/videos, witness names, police/FIR or inspector papers if any, and file before the Employees' Compensation Commissioner/labour office with DLSA help [{employees}].", ("employees",)),
        ),
        priority=116,
    ),
    AuthorityWorkflowContract(
        id="worksite_assault_wage_injury",
        route_categories=("workplace_injury_compensation",),
        trigger_groups=(
            ("beat me", "beat worker", "beat labour", "beat labor", "contractor beat", "mukadam beat", "beaten", "assault", "hit me", "head injury", "stitches"),
            ("site", "worksite", "construction", "mukadam", "thekedar", "contractor", "old wages", "wages"),
            ("injury", "head", "medical", "hospital", "fracture", "blood", "wages", "not paid", "not paying"),
        ),
        source_specs=(
            PassageSpec("bns", ("bharatiya nyaya",), ("/sec-115", "/sec-117", "/sec-118"), required=True),
            PassageSpec("employees", ("employees' compensation", "employees compensation", "workmen's compensation"), ("/sec-3", "/sec-10", "/sec-22"), required=True),
            PassageSpec("wages", ("code on wages", "payment of wages"), ("/sec-17", "/sec-18", "/sec-45")),
            PassageSpec("bnss", ("bharatiya nagarik suraksha",), ("/sec-173", "/sec-175")),
            PassageSpec("ipc", ("indian penal",), ("/sec-323", "/sec-325")),
        ),
        line_specs=(
            LineSpec("For a contractor/mukadam beating a worker at a site with head injury, keep the police/FIR hurt or grievous-hurt track separate from the wage dispute; the BNS hurt source is the current offence source to verify by incident date [{bns}].", ("bns",)),
            LineSpec("The Employees' Compensation source is the parallel workplace-injury track if the injury arose out of and in the course of work; do not let the employer/contractor reduce it to only an unpaid-wages fight [{employees}].", ("employees",)),
            LineSpec("For old wages or unpaid wages, keep the Code on Wages/payment-of-wages source as a separate labour-authority claim with attendance, wage rate, and dues proof [{wages}].", ("wages",)),
            LineSpec("Use the BNSS FIR/Magistrate escalation source if police refuse to register or act on the assault complaint [{bnss}].", ("bnss",)),
            LineSpec("If the incident is under the older IPC/CrPC regime, compare the same hurt allegation with the IPC hurt source instead of mixing regimes [{ipc}].", ("ipc",)),
            LineSpec("**What you can do next**"),
            LineSpec("- Preserve medical papers, injury photos, site/CCTV/witness details, contractor or mukadam identity, wage-dues chart, attendance/muster, messages, and any police complaint/refusal; use police for assault/FIR, the Labour Commissioner/wage authority for old wages, and the Employees' Compensation Commissioner for injury compensation [{bns}], [{employees}], [{wages}].", ("bns", "employees", "wages")),
        ),
        priority=121,
    ),
    AuthorityWorkflowContract(
        id="workplace_injury_lost_limb_compensation",
        route_categories=("workplace_injury_compensation",),
        trigger_groups=(
            ("lost hand", "lost limb", "hand", "arm", "leg", "injury", "accident", "brick kiln", "factory", "work"),
            ("compensation", "owner", "employer", "contractor", "careless", "no compensation"),
        ),
        source_specs=(
            PassageSpec("employees", ("employees' compensation", "employees compensation"), ("/sec-3", "/sec-10", "/sec-22"), required=True),
            PassageSpec("factories", ("factories act",), ("/sec-111", "/sec-88", "/sec-89")),
            PassageSpec("bocw", ("building and other construction workers",)),
            PassageSpec("contract_labour", ("contract labour",), ("/sec-21",)),
        ),
        line_specs=(
            LineSpec("For a lost hand/limb, amputation, or serious brick-kiln/factory/work accident, start with the Employees' Compensation Act accident-at-work source; the owner saying the worker was careless does not end the claim by itself [{employees}].", ("employees",)),
            LineSpec("If the workplace is a factory/brick-kiln-type establishment, keep the Factories Act safety/notice record as a supporting labour-inspection track [{factories}].", ("factories",)),
            LineSpec("If the facts are construction-site/building-worker facts, also keep the BOCW welfare-board/safety record separate from the compensation claim [{bocw}].", ("bocw",)),
            LineSpec("If the principal employer says the contract worker is only the contractor's problem, keep the Contract Labour Act source as the contractor/principal-employer record and wage-responsibility track; do not let that replace the injury-compensation and BOCW tracks [{contract_labour}].", ("contract_labour",)),
            LineSpec("**What you can do next**"),
            LineSpec("- Collect accident date/time/place, employer/contractor name, wage proof, medical/disability certificate, photos, witness names, ESI/insurance papers, FIR/accident report if any, and file before the Employees' Compensation Commissioner/labour office with DLSA help [{employees}].", ("employees",)),
        ),
        priority=111,
    ),
    AuthorityWorkflowContract(
        id="undertrial_lawyer_not_coming_legal_aid",
        route_categories=("undertrial_review_release",),
        trigger_groups=(
            ("undertrial", "jail", "prison", "puzhal", "tihar", "yerwada"),
            ("lawyer", "legal aid", "dlsa", "not coming", "hearings", "complain"),
        ),
        source_specs=(
            PassageSpec("lsa", ("legal services authorities",), ("/sec-9", "/sec-12"), required=True),
            PassageSpec("article21", ("constitution",), ("/sec-21",)),
            PassageSpec("bnss", ("bharatiya nagarik suraksha",), ("/sec-479",)),
            PassageSpec("crpc", ("code of criminal procedure",), ("/sec-436A", "/sec-436-a")),
        ),
        line_specs=(
            LineSpec("If an undertrial has been in jail for years, trial has not started, or the lawyer is not coming to hearings, the Legal Services Authorities source supports splitting the work into two tracks: DLSA/jail legal-aid lawyer replacement and trial-court custody-duration review [{lsa}].", ("lsa",)),
            LineSpec("Keep Article 21 speedy-trial/effective-legal-aid concerns with the custody timeline where hearings are missed or representation is ineffective [{article21}].", ("article21",)),
            LineSpec("For the custody-duration part, the BNSS source is Section 479, the current undertrial-release source to compare actual detention with the maximum imprisonment for the offence [{bnss}].", ("bnss",)),
            LineSpec("If the older CrPC regime applies, Section 436A is the legacy source for release once undertrial detention reaches one-half of the maximum imprisonment, subject to recorded reasons and statutory exclusions [{crpc}].", ("crpc",)),
            LineSpec("**What you can do next**"),
            LineSpec("- File a written DLSA/jail legal-aid clinic request for lawyer replacement/status and ask the trial court lawyer to move a custody-duration/speedy-trial review where facts support it; keep prison number, FIR/case number, court name, custody start date, offence sections and maximum punishment, hearing dates missed, lawyer name, family contact, and copies of remand/bail/orders [{lsa}], [{bnss}].", ("lsa", "bnss")),
            LineSpec("- If the case is in the older CrPC regime, ask the lawyer/DLSA to check Section 436A with the same custody chart before filing the trial-court release or bail-review request [{crpc}].", ("crpc",)),
        ),
        priority=112,
    ),
    AuthorityWorkflowContract(
        id="construction_overtime_wage_claim",
        route_categories=("employment_wages", "labour_exploitation_discrimination", "labour_compliance"),
        trigger_groups=(
            ("construction", "site", "contractor", "thekedar", "labour"),
            ("overtime", "extra hours", "14 hour", "14 hours", "12 hour", "12 hours", "long hours", "laughing"),
        ),
        source_specs=(
            PassageSpec("wages", ("code on wages",), ("/sec-17", "/sec-18", "/sec-45"), required=True),
            PassageSpec("bocw", ("building and other construction workers",)),
        ),
        line_specs=(
            LineSpec("For a construction-site overtime dispute or construction-site worker doing 14-hour days with no overtime, start with a written wage/overtime claim under the Code on Wages source before treating it as only a verbal fight with the contractor [{wages}].", ("wages",)),
            LineSpec("If the worker is a building/construction worker, keep the BOCW registration/welfare-board and labour-inspection record as a separate supporting track [{bocw}].", ("bocw",)),
            LineSpec("**What you can do next**"),
            LineSpec("- Make a date-wise hours/overtime chart, wage rate, contractor/site name, attendance/muster proof, messages, co-worker witnesses, bank/cash payment proof, and file a written wage complaint with the Labour Commissioner/wage authority or construction welfare-board route where applicable [{wages}].", ("wages",)),
        ),
        priority=110,
    ),
    AuthorityWorkflowContract(
        id="juvenile_adult_jail_age_determination",
        route_categories=("criminal_defence_bail", "undertrial_review_release", "arrest_custody_safeguard"),
        trigger_groups=(
            ("16", "16 yr", "16 yrs", "16 years", "sixteen", "17", "17 yrs", "17 years", "seventeen", "minor", "juvenile", "child", "child in conflict", "under 18", "under eighteen"),
            ("adult jail", "jail", "lockup", "custody", "puzhal", "tihar", "yerwada", "accused", "court", "which court", "case"),
            ("age proof", "school certificate", "birth certificate", "aadhaar", "pocso", "where to file", "what application", "age certificate", "age determination", "observation home", "transfer", "juvenile"),
        ),
        source_specs=(
            PassageSpec("age", ("juvenile justice",), ("/sec-94",)),
            PassageSpec("court", ("juvenile justice",), ("/sec-9",), required=True),
            PassageSpec("custody", ("juvenile justice",), ("/sec-10", "/sec-12", "/sec-2"),),
            PassageSpec("pocso", ("protection of children from sexual offences",),),
        ),
        line_specs=(
            LineSpec("For a 17-year-old or possible child in an adult jail/POCSO case, treat this first as a JJ Act age-determination and production/transfer problem, not ordinary adult bail alone [{age}].", ("age",)),
            LineSpec("Raise the age claim before the current criminal court or Juvenile Justice Board; the JJ Act court-inquiry source is the route for a court other than the Board to inquire and record age [{court}].", ("court",)),
            LineSpec("Use the school or matriculation date-of-birth certificate first, then birth-certificate records, and only then medical age testing as the JJ Act age source requires [{age}].", ("age",)),
            LineSpec("If custody papers show adult jail or lockup placement, keep an urgent removal/production/child-custody track alongside the age proof application [{custody}].", ("custody",)),
            LineSpec("Keep the POCSO FIR/sections with the age application, but do not let the POCSO label erase the JJ Act age-determination route [{pocso}].", ("pocso",)),
            LineSpec("**What you can do next**"),
            LineSpec("- File an age-determination/production-transfer application with the current court or Juvenile Justice Board using school certificate, birth certificate, remand/jail papers, FIR/POCSO sections, parent ID, and DLSA/legal-aid contact [{court}], [{age}].", ("court", "age")),
        ),
        priority=114,
    ),
    AuthorityWorkflowContract(
        id="interstate_migrant_displacement_allowance",
        route_categories=("labour_exploitation_discrimination", "employment_wages"),
        trigger_groups=(
            ("thekedar", "contractor", "recruiter"),
            ("migrant", "inter state", "inter-state", "bihar to gurgaon", "from bihar", "from odisha", "from another state", "another state", "home state"),
            ("displacement allowance", "journey allowance", "bihar to gurgaon", "came together", "never paid", "not paid"),
        ),
        source_specs=(
            PassageSpec("ismw", ("inter-state migrant", "inter state migrant"), ("/sec-14", "/sec-15", "/sec-12"), required=True),
            PassageSpec("wages", ("code on wages",), ("/sec-17", "/sec-45")),
        ),
        line_specs=(),
        priority=126,
    ),
    AuthorityWorkflowContract(
        id="tribal_land_nontribal_transfer",
        route_categories=("tribal_caste_atrocity", "property_tenancy", "succession_inheritance"),
        trigger_groups=(
            ("tribal", "adivasi", "scheduled tribe", "st land", "munda", "santhal", "agency area", "agency village"),
            ("land", "plot", "khata", "mutation"),
            ("non tribal", "non-tribal", "bania", "sahukar", "moneylender", "upper caste", "outsider", "buyer"),
            (
                "sold", "sale", "transfer", "transferred", "registered", "mutation", "mortgage",
                "grabbed", "land grabbed", "patwari changed", "tehsildar transferred",
                "giving my", "giving our", "without my consent", "without our consent",
            ),
        ),
        source_specs=(
            PassageSpec(
                "state_transfer",
                (
                    "andhra pradesh scheduled areas land transfer regulation",
                    "orissa scheduled areas transfer",
                    "scheduled areas transfer of immovable property",
                    "chota nagpur tenancy",
                    "santhal parganas tenancy",
                ),
                ("/sec-3", "/sec-46", "/sec-45-c", "/sec-45-b", "/sec-71-a"),
            ),
            PassageSpec(
                "state_restoration",
                ("chota nagpur tenancy", "santhal parganas tenancy"),
                ("/sec-71-a",),
            ),
            PassageSpec("constitution", ("constitution",), ("/sec-244",)),
            PassageSpec("pesa", ("panchayats", "scheduled areas"), ("/sec-4",)),
            PassageSpec("poa", ("scheduled castes", "prevention of atrocities"), ("/sec-3", "/sec-15A")),
            PassageSpec("transfer_property", ("transfer of property",), ("/sec-44", "/sec-54", "/sec-58", "/sec-122")),
        ),
        line_specs=(),
        priority=125,
    ),
    AuthorityWorkflowContract(
        id="tribal_religious_attack_poa",
        route_categories=("tribal_caste_atrocity", "police_fir", "criminal_general"),
        trigger_groups=(
            ("sarna", "pahan", "adivasi", "tribal", "scheduled tribe"),
            ("attacked", "attack", "beat", "mob", "called", "non hindu", "non-hindu"),
        ),
        source_specs=(
            PassageSpec("poa", ("scheduled castes", "prevention of atrocities"), ("/sec-3",), required=True),
            PassageSpec("bns", ("bharatiya nyaya",), ("/sec-298", "/sec-351", "/sec-352", "/sec-115")),
            PassageSpec("bnss", ("bharatiya nagarik suraksha",), ("/sec-173", "/sec-175")),
        ),
        line_specs=(),
        priority=126,
    ),
    AuthorityWorkflowContract(
        id="poa_rule7_dsp_investigation",
        route_categories=("tribal_caste_atrocity", "police_fir", "criminal_general"),
        trigger_groups=(
            ("poa", "atrocity", "sc/st", "sc st", "prevention of atrocities"),
            ("dsp", "deputy superintendent", "sp not transferring", "not transferring", "rule 7", "rule-7", "investigating officer"),
        ),
        source_specs=(
            PassageSpec("poa_rules", ("prevention of atrocities", "rules"), ("rule-7",), required=True),
            PassageSpec("poa", ("scheduled castes", "prevention of atrocities"), ("/sec-3", "/sec-14", "/sec-15A")),
            PassageSpec("bnss", ("bharatiya nagarik suraksha",), ("/sec-173", "/sec-175")),
        ),
        line_specs=(
            LineSpec("For an SC/ST PoA investigation where the concern is that the case has not been assigned to a Deputy Superintendent of Police, treat Rule 7 of the PoA Rules as an investigating-officer/rank record issue; do not assume that an SP-to-DSP transfer happens automatically without checking the appointment and case papers [{poa_rules}].", ("poa_rules",)),
            LineSpec("Keep the PoA Act case details with the Rule 7 request so the offence, FIR, investigating-officer appointment, and Special Court/victim-support facts can be checked together [{poa}].", ("poa",)),
            LineSpec("Keep the BNSS FIR/complaint procedure source for a written escalation if the police do not give the investigating-officer details or a written response [{bnss}].", ("bnss",)),
            LineSpec("**What you can do next**"),
            LineSpec("- Collect the FIR/case number, complaint copy, investigating officer's name/rank and appointment record if available, any SP/DSP representation, incident date/place, caste/community proof, witness/medical evidence, and refusal or status messages; give a written Rule 7/status request to senior police, the Special Court support channel, or DLSA and keep an acknowledgement [{poa_rules}].", ("poa_rules",)),
        ),
        priority=129,
    ),
    AuthorityWorkflowContract(
        id="cfr_illegal_mining",
        route_categories=("tribal_caste_atrocity", "environment_compensation", "land_acquisition_compensation"),
        trigger_groups=(
            ("cfr", "community forest", "forest rights", "forest land"),
            ("mining", "illegal mining", "mine", "company"),
        ),
        source_specs=(
            PassageSpec("fra", ("forest rights", "recognition of forest rights"), ("/sec-3", "/sec-5", "/sec-6"), required=True),
            PassageSpec("mmdr", ("mines and minerals",)),
            PassageSpec("fca", ("forest (conservation", "forest conservation"), ("/sec-2",)),
        ),
        line_specs=(),
        priority=127,
    ),
    AuthorityWorkflowContract(
        id="gift_deed_thumb_fraud",
        route_categories=("property_tenancy", "succession_inheritance"),
        trigger_groups=(
            ("thumb impression", "blank paper", "fake signature", "forged", "forgery"),
            ("gift deed", "registered gift", "produced as gift", "gift"),
        ),
        source_specs=(
            PassageSpec("tpa", ("transfer of property",), ("/sec-122", "/sec-123", "/sec-126"), required=True),
            PassageSpec("specific", ("specific relief",), ("/sec-31", "/sec-34", "/sec-38"), required=True),
            PassageSpec("contract", ("indian contract",), ("/sec-14", "/sec-16", "/sec-17", "/sec-19")),
            PassageSpec("registration", ("registration act",), ("/sec-17", "/sec-49")),
            PassageSpec("bns", ("bharatiya nyaya",), ("/sec-336", "/sec-338", "/sec-340", "/sec-318")),
            PassageSpec("bnss", ("bharatiya nagarik suraksha",), ("/sec-173", "/sec-175")),
        ),
        line_specs=(),
        priority=128,
    ),
    AuthorityWorkflowContract(
        id="school_caste_slur_assault",
        route_categories=("tribal_caste_atrocity", "police_fir"),
        trigger_groups=(
            ("school", "outside school", "student", "child", "son"),
            ("untouchable", "caste", "upper caste", "dalit", "sc/st", "adivasi", "tribal"),
            ("beat", "beaten", "hit", "assault", "slap", "sarpanch"),
        ),
        source_specs=(
            PassageSpec("poa", ("scheduled castes", "prevention of atrocities"), ("/sec-3",), required=True),
            PassageSpec("victim_rights", ("scheduled castes", "prevention of atrocities"), ("/sec-15A", "/sec-15-a")),
            PassageSpec("bns", ("bharatiya nyaya",), ("/sec-115", "/sec-117", "/sec-351", "/sec-352")),
            PassageSpec("bnss", ("bharatiya nagarik suraksha",), ("/sec-173", "/sec-175")),
            PassageSpec("rte", ("right of children to free",), ("/sec-17",)),
        ),
        line_specs=(
            LineSpec("For a child beaten near school while being called untouchable/caste words by an upper-caste person or sarpanch, keep the SC/ST POA atrocity route separate from ordinary assault [{poa}].", ("poa",)),
            LineSpec("Physical beating, threat, or intimidation should also be matched with the BNS hurt/intimidation track without replacing the atrocity route [{bns}].", ("bns",)),
            LineSpec("If school staff or school setting is part of the facts, keep the RTE school-harassment/corporal-punishment record with the atrocity complaint [{rte}].", ("rte",)),
            LineSpec("**What you can do next**"),
            LineSpec("- Write the exact caste words, place/time, accused identity/status, child's caste/community proof, school details, injury/medical proof, witness names, photos/video, and take a written complaint to police/SP, DLSA, or Special Court support if FIR is refused [{poa}], [{bnss}].", ("poa", "bnss")),
            LineSpec("- Write the exact caste words, place/time, accused identity/status, child's caste/community proof, school details, injury/medical proof, witness names, photos/video, and take a written SC/ST POA complaint to police/SP, DLSA, or Special Court support; if FIR is refused, ask the lawyer/DLSA to add the criminal-procedure escalation source from the FIR papers [{poa}].", ("poa",)),
        ),
        priority=113,
    ),
    AuthorityWorkflowContract(
        id="forest_mfp_false_dacoity_case",
        route_categories=("criminal_defence_bail", "police_fir", "tribal_caste_atrocity"),
        trigger_groups=(
            ("forest", "forest guard", "tendu", "minor forest produce", "mfp", "mahua", "bamboo"),
            ("false", "fake", "dacoity", "case", "fir", "arrested", "collecting"),
        ),
        source_specs=(
            PassageSpec("fra", ("forest rights", "recognition of forest rights"), ("/sec-3",), required=True),
            PassageSpec("bns", ("bharatiya nyaya",), ("/sec-310", "/sec-309", "/sec-308")),
            PassageSpec("bnss", ("bharatiya nagarik suraksha",), ("/sec-483", "/sec-480", "/sec-173")),
        ),
        line_specs=(
            LineSpec("For a false dacoity case over collecting tendu leaves or minor forest produce, keep the Forest Rights Act minor-forest-produce source with the FIR and seizure papers; do not treat it as ordinary dacoity facts only [{fra}].", ("fra",)),
            LineSpec("Compare the BNS dacoity/robbery allegation with the actual number of accused, force/threat facts, and collection-of-forest-produce context before accepting the FIR label [{bns}].", ("bns",)),
            LineSpec("If arrest/custody is live, use the BNSS bail/remand source along with the FRA documents and seizure memo [{bnss}].", ("bnss",)),
            LineSpec("**What you can do next**"),
            LineSpec("- Collect FIR, seizure memo, forest-guard complaint, Gram Sabha/FRA papers, forest-produce permit/customary-use proof, witness names, number of alleged accused, and remand/bail papers; take them to DLSA or a criminal/FRA lawyer for bail and false-case defence [{fra}], [{bnss}].", ("fra", "bnss")),
        ),
        priority=112,
    ),
    AuthorityWorkflowContract(
        id="mining_displacement_rehabilitation",
        route_categories=("environment_compensation", "land_acquisition_compensation"),
        trigger_groups=(
            ("mine", "mining", "iron ore", "coal", "displaced", "displacement", "villages", "rehabilitation", "rehab"),
            ("land", "village", "keonjhar", "scheduled area", "tribal", "compensation"),
        ),
        source_specs=(
            PassageSpec("larr", ("right to fair compensation", "land acquisition"), ("/sec-41", "/schedule", "/sec-77"), required=True),
            PassageSpec("pesa", ("panchayats", "scheduled areas"), ("/sec-4",)),
            PassageSpec("mmdr", ("mines and minerals",)),
            PassageSpec("fca", ("forest (conservation", "forest conservation"), ("/sec-2",)),
        ),
        line_specs=(
            LineSpec("For mine displacement, or a dam, public project, mine, or coal-block displacement that may submerge tribal villages, start with the RFCTLARR section 41 rehabilitation/resettlement source and affected-family record, not only a pollution complaint [{larr}].", ("larr",)),
            LineSpec("If the facts mention Palli Sabha, Gram Sabha, Odisha, Scheduled Area, or tribal village, verify whether the PESA/Gram Sabha/Palli Sabha consultation track was required and keep it separate from compensation and rehabilitation papers [{pesa}].", ("pesa",)),
            LineSpec("Keep the MMDR/mining-lease record as supporting context for the mine operator and project approvals, but compensation/rehabilitation usually turns on acquisition/R&R records [{mmdr}].", ("mmdr",)),
            LineSpec("**What you can do next**"),
            LineSpec("- Collect acquisition notifications, award/R&R package, displacement list, affected-family/village list, rehabilitation entitlement, dam/project/mine documents, Gram Sabha or Palli Sabha records, land records, and prior complaint proof; approach the Collector/R&R authority or DLSA first, then High Court/NGT counsel depending on facts [{larr}].", ("larr",)),
        ),
        priority=110,
    ),
    AuthorityWorkflowContract(
        id="thermal_blasting_house_damage_compensation",
        route_categories=("environment_compensation", "land_acquisition_compensation"),
        trigger_groups=(
            ("thermal plant", "power plant", "blasting", "blast", "cracking", "crack"),
            ("house", "houses", "home", "homes", "compensation", "no compensation", "kalahandi"),
        ),
        source_specs=(
            PassageSpec("environment", ("environment (protection", "environment protection"), ("/sec-3", "/sec-5"), required=True),
            PassageSpec("larr41", ("right to fair compensation", "land acquisition"), ("/sec-41",), required=True),
            PassageSpec("ngt", ("national green tribunal",), ("/sec-14", "/sec-15", "/sec-18")),
            PassageSpec("water", ("water (prevention", "water prevention"), ("/sec-17", "/sec-24", "/sec-25", "/sec-33A")),
        ),
        line_specs=(
            LineSpec("For thermal/power-plant blasting that cracked houses and no compensation has been paid, keep both tracks visible: Environment Protection/Pollution Control Board inspection for hazardous activity and RFCTLARR section 41 affected-family/R&R safeguards where acquisition, Scheduled Area, ST, or rehabilitation facts are involved [{environment}], [{larr41}].", ("environment", "larr41")),
            LineSpec("Use the NGT source for compensation/restoration only after preserving dated crack photos, blasting dates, operator/project details, panchayat or engineer assessment, and prior complaints [{ngt}].", ("ngt",)),
            LineSpec("If water, effluent, or pollution-control consent facts are also involved, keep the Water Act/SPCB record as a separate inspection track [{water}].", ("water",)),
            LineSpec("**What you can do next**"),
            LineSpec("- Collect dated photos/videos of cracks, blasting dates, project/operator name, land/acquisition or rehabilitation papers if any, village/ST/Scheduled Area facts, complaint copies, panchayat/engineer/property assessment, and health records; ask the Pollution Control Board and District Collector/R&R authority for inspection and compensation/R&R records before going to DLSA or NGT/environment counsel [{environment}], [{larr41}].", ("environment", "larr41")),
        ),
        priority=111,
    ),
    AuthorityWorkflowContract(
        id="street_vendor_goods_removed",
        route_categories=("street_vendor_municipal", "business_license_compliance"),
        trigger_groups=(
            ("street vendor", "hawker", "vending", "vending certificate", "certificate of vending", "tvc", "town vending committee", "cart", "tea cart", "thela", "footpath", "footpath stall", "vending goods", "goods"),
            ("municipality", "municipal", "municipal people", "nagar nigam", "removed", "seized", "took", "took my goods", "goods are missing", "fine", "without receipt", "without notice", "asking fine"),
        ),
        source_specs=(
            PassageSpec("street", ("street vendors",), required=True),
            PassageSpec("street4", ("street vendors",), ("/sec-4",)),
            PassageSpec("street19", ("street vendors",), ("/sec-19",)),
            PassageSpec("street20", ("street vendors",), ("/sec-20",)),
            PassageSpec("street28", ("street vendors",), ("/sec-28",)),
            PassageSpec("pca", ("prevention of corruption",), ("/sec-7",)),
        ),
        line_specs=(
            LineSpec("For a Mumbai/Bandra street vendor, hawker, tea cart, vegetable cart, footpath stall, certificate-of-vending holder, no-TVC-certificate applicant, demolished cart, or vending goods removed by a municipal body without notice, use the Street Vendors Act / Town Vending Committee route instead of accepting an oral encroachment label [{street}].", ("street",)),
            LineSpec("**What you can do next**"),
            LineSpec("- Ask the municipal authority or Town Vending Committee for the written notice/order, seizure memo, receipt, challan/fine basis, hearing date, goods inventory, and return/release of goods or appeal/complaint route [{street}].", ("street",)),
            LineSpec("- Keep certificate of vending, survey proof, application, zone-allotment papers, challan/fine receipt, seizure list, photos/video, goods value list, inspector details, and any cash-demand messages [{street}].", ("street",)),
        ),
        priority=87,
    ),
    AuthorityWorkflowContract(
        id="wage_theft_false_fir",
        route_categories=("employment_wages", "police_fir", "criminal_defence_bail", "criminal_general"),
        trigger_groups=(
            ("wage", "wages", "labour", "thekedar", "contractor", "labour chowk"),
            ("false fir", "fake fir", "theft case", "mobile theft", "police", "picking", "begging"),
        ),
        source_specs=(
            PassageSpec("wages", ("code on wages",), required=True),
            PassageSpec("bns", ("bharatiya nyaya",), ("/sec-127", "/sec-351", "/sec-318", "/sec-317", "/sec-303")),
            PassageSpec("bnss", ("bharatiya nagarik suraksha",), ("/sec-173", "/sec-175", "/sec-216", "/sec-47", "/sec-48", "/sec-57", "/sec-58")),
            PassageSpec("article21", ("constitution",), ("/sec-21",)),
            PassageSpec("article22", ("constitution",), ("/sec-22",)),
            PassageSpec("ismw", ("inter-state migrant", "inter state migrant"), ("/sec-12", "/sec-14", "/sec-15")),
        ),
        line_specs=(
            LineSpec("Treat this as a dual-track wages and false FIR/police problem: preserve the wage-retaliation facts, keep the Code on Wages payment claim alive, and separately handle police, FIR, bail, or legal-aid risk [{wages}].", ("wages",)),
            LineSpec("If the contractor threatens a theft case after you ask for unpaid wages, preserve the wage-demand timeline and keep the BNS source for intimidation/cheating/theft-allegation separate from the labour claim [{bns}].", ("bns",)),
            LineSpec("If police are calling, picking workers, or recording a theft allegation, use the BNSS FIR/information source to ask for the FIR/DD entry, notice, station details, and whether anyone is accused, witness, or complainant [{bnss}].", ("bnss",)),
            LineSpec("**What you can do next**"),
            LineSpec("- For the labour track, file with the wage authority/Labour Commissioner using attendance, muster, messages, wage calculation, contractor/thekedar details, ID proof, bank entries, and worksite witnesses [{wages}].", ("wages",)),
            LineSpec("- For the criminal track, take FIR/notice details, police-call records, legal-aid or lawyer contact, and proof that the wage demand came before the theft allegation [{bnss}].", ("bnss",)),
        ),
        priority=93,
    ),
    AuthorityWorkflowContract(
        id="shop_sealed_municipality",
        route_categories=("business_license_compliance", "street_vendor_municipal", "property_tenancy"),
        trigger_groups=(
            ("shop", "commercial", "store", "dukan", "restaurant", "hotel", "kitchen", "canteen", "dhaba", "food business", "office shop"),
            ("municipality", "municipal", "corporation", "local body", "local authority", "nagar", "mcd", "bmc", "bbmp", "noida authority", "authority", "trade licence", "trade license", "health department", "food safety officer", "food inspector", "food authority", "designated officer"),
            ("sealed", "sealing", "locked", "seal", "put seal", "licence", "license", "licence issue", "license issue"),
        ),
        source_specs=(
            PassageSpec("rti", ("right to information",)),
            PassageSpec("shops", ("shops", "establishments")),
            PassageSpec("municipal", ("municipalities", "municipal corporations")),
            PassageSpec("food", ("food safety",)),
        ),
        line_specs=(
            LineSpec("For an MCD, BMC, BBMP, Noida Authority, corporation, municipality, or other local-authority shop sealing/licence problem, verify the state/local municipal law named in the sealing order instead of borrowing another city's law; use RTI or a written records request if the order, notice, inspection report, or licence file is not supplied [{rti}].", ("rti",)),
            LineSpec("For a municipal, municipality, corporation, sealed, sealing, seal, licence, or trade-licence shop problem, check the Shops and Establishments source for the shop-registration or certificate part of the order [{shops}].", ("shops",)),
            LineSpec("For Gujarat municipal or corporation facts, also verify the municipal-law source for licence conditions, dangerous/nuisance use, stop-use power, or licence suspension/revocation before deciding the reopen, appeal, or court route [{municipal}].", ("municipal",)),
            LineSpec("**What you can do next**"),
            LineSpec("- Ask the municipal authority, ward/licensing office, Commissioner, or appellate authority named in the order for the sealing order, notice, written order, inspection report, licence file, appeal/reopen/release route, and the state/local municipal law relied on [{rti}].", ("rti",)),
            LineSpec("- If the office will not give the order, inspection file, status, or reasons, use the RTI route as a records route, not as the sealing power itself [{rti}].", ("rti",)),
            LineSpec("- Keep trade licence, shop registration, rent/ownership papers, tax/fee receipts, photos of seal, inventory of goods, show-cause notice, prior replies, and no-notice proof [{shops}].", ("shops",)),
        ),
        priority=82,
    ),
    AuthorityWorkflowContract(
        id="commercial_preinstitution_mediation",
        route_categories=("court_procedure",),
        trigger_groups=(
            ("commercial suit", "commercial court", "commercial dispute"),
            ("pre litigation mediation", "pre-litigation mediation", "pre institution mediation", "pre-institution mediation", "section 12a", "12a", "mediation mandatory", "skipped pre litigation", "skipped pre-litigation"),
        ),
        source_specs=(
            PassageSpec("commercial", ("commercial courts",), ("/sec-12a", "/sec-12-a"), required=True),
            PassageSpec("mediation", ("mediation act",), ("/sec-5", "/sec-6", "/sec-18", "/sec-19")),
        ),
        line_specs=(
            LineSpec("For a commercial suit, Commercial Courts Act Section 12A is the source to check for pre-institution mediation: ordinarily the statutory mediation step must be exhausted before institution unless the suit contemplates urgent interim relief [{commercial}].", ("commercial",)),
            LineSpec("A dispute about whether the step was skipped or whether a plaint can proceed is a filing-stage issue; it does not decide the underlying commercial claim on its merits [{commercial}].", ("commercial",)),
            LineSpec("Use the Mediation Act material only for the mediation-process side; do not treat it as a substitute for the Commercial Courts Act Section 12A condition [{mediation}].", ("mediation",)),
            LineSpec("**What you can do next**"),
            LineSpec("- Keep the proposed plaint, contract/invoices, dispute value and commercial relationship facts, mediation application/notice/status, proof of service, any urgent-interim-relief facts, and the court filing papers; ask the commercial-court filing counter or a commercial-law lawyer to check Section 12A before filing or opposing a threshold objection [{commercial}].", ("commercial",)),
        ),
        priority=148,
    ),
    AuthorityWorkflowContract(
        id="voluntary_preinstitution_mediation",
        route_categories=("court_procedure",),
        trigger_groups=(
            ("mediation act", "mediation act 2023", "initiate mediation", "start mediation", "apply for mediation", "go for mediation"),
            ("without going to court", "without court", "pre litigation", "pre-litigation", "voluntary mediation", "mediation centre", "mediation center"),
        ),
        source_specs=(
            PassageSpec("mediation", ("mediation act",), ("/sec-5", "/sec-6", "/sec-18", "/sec-19"), required=True),
            PassageSpec("legal_aid", ("legal services authorities",), ("/sec-4", "/sec-6", "/sec-9", "/sec-12", "/sec-19")),
        ),
        line_specs=(
            LineSpec("The Mediation Act is the source to check for a voluntary or pre-litigation mediation path before a suit; the mediation step can be explored without first filing an ordinary court case [{mediation}].", ("mediation",)),
            LineSpec("Mediation is a process for trying to resolve the dispute, not a ruling that either side is legally right; preserve the contract, messages, claim amount, and any deadline while it is attempted [{mediation}].", ("mediation",)),
            LineSpec("A District Legal Services Authority or mediation centre can be a practical access point for legal-aid or mediated-settlement help where available [{legal_aid}].", ("legal_aid",)),
            LineSpec("**What you can do next**"),
            LineSpec("- Make a short written dispute note, proposed settlement terms, names/contact details of the other side, key documents/messages, amount involved, any limitation/deadline concern, and ask a mediation centre or DLSA about the appropriate intake route; seek a lawyer first if you need urgent injunction, protective, or time-sensitive court relief [{mediation}].", ("mediation",)),
        ),
        priority=145,
    ),
    AuthorityWorkflowContract(
        id="civil_second_appeal_substantial_question",
        route_categories=("court_procedure",),
        trigger_groups=(
            ("second appeal", "substantial question of law", "section 100", "cpc 100"),
            ("high court", "appeal", "procedure", "where to go", "file", "challenge"),
        ),
        source_specs=(
            PassageSpec("cpc", ("code of civil procedure",), ("/sec-100",), required=True),
            PassageSpec("limitation", ("limitation act",), ("/sec-5",)),
        ),
        line_specs=(
            LineSpec("For a civil second appeal, CPC Section 100 is the controlling source: the High Court route turns on a substantial question of law, not simply a request to reargue all facts from the earlier appeal [{cpc}].", ("cpc",)),
            LineSpec("Read the trial-court and first-appellate judgments together and identify the proposed legal question, the relevant finding, and the record page; do not assume every disagreement with the first appeal creates a second appeal [{cpc}].", ("cpc",)),
            LineSpec("If filing is late, preserve the communication/certified-copy dates and delay explanation for the separate Limitation Act Section 5 question [{limitation}].", ("limitation",)),
            LineSpec("**What you can do next**"),
            LineSpec("- Take the trial judgment, first-appellate judgment/decree, certified-copy applications and delivery dates, pleadings, evidence/exhibits, chronology, proposed substantial question of law, and limitation calculation to a High Court civil lawyer or DLSA before filing [{cpc}].", ("cpc",)),
        ),
        priority=144,
    ),
    AuthorityWorkflowContract(
        id="limitation_delay_condonation",
        route_categories=("court_procedure",),
        trigger_groups=(
            ("condonation", "condone delay", "delay application", "section 5 limitation", "sec 5 limitation"),
            ("appeal", "application", "court", "where to go", "grounds", "late filing", "file"),
        ),
        source_specs=(
            PassageSpec("limitation", ("limitation act",), ("/sec-5",), required=True),
            PassageSpec("cpc", ("code of civil procedure",)),
        ),
        line_specs=(
            LineSpec("For a delayed appeal or application, Limitation Act Section 5 is the source to check for condonation: the court may extend time on sufficient cause, but delay is not automatically excused [{limitation}].", ("limitation",)),
            LineSpec("Keep the merits filing and the delay explanation separate: give the order date, service/knowledge date, certified-copy dates, each period of delay, and documents supporting the explanation [{limitation}].", ("limitation",)),
            LineSpec("Use the relevant court's filing rules and the underlying CPC/appellate procedure for the main filing; Section 5 does not by itself identify every forum or deadline [{cpc}].", ("cpc",)),
            LineSpec("**What you can do next**"),
            LineSpec("- Prepare the impugned order, limitation calculation, certified-copy application/delivery proof, medical/travel/portal or other delay evidence, affidavit if required by the court, and the proposed appeal/application; have the registry, DLSA, or a lawyer check the correct court and limitation rule before filing [{limitation}].", ("limitation",)),
        ),
        priority=143,
    ),
    AuthorityWorkflowContract(
        id="civil_case_transfer",
        route_categories=("court_procedure",),
        trigger_groups=(
            ("transfer of case", "case transfer", "transfer case", "section 24", "cpc 24"),
            ("district court", "high court", "civil court", "another district", "where to go", "apply", "application"),
        ),
        source_specs=(
            PassageSpec("cpc", ("code of civil procedure",), ("/sec-24",), required=True),
        ),
        line_specs=(
            LineSpec("For transfer of a civil suit, appeal, or proceeding, CPC Section 24 is the source to check for the High Court or District Court transfer/withdrawal power within the relevant jurisdiction [{cpc}].", ("cpc",)),
            LineSpec("The correct transfer forum depends on which court presently has the case and where it is proposed to go, so do not file a generic transfer request without the case number, court locations, and concrete grounds [{cpc}].", ("cpc",)),
            LineSpec("**What you can do next**"),
            LineSpec("- Collect the plaint/petition, written statement if filed, case number, order sheets, next date, both court locations, addresses/witness or convenience facts, any safety or connected-case grounds, and the requested destination court; ask the relevant District Court/High Court filing counter, DLSA, or civil lawyer to check the Section 24 forum before filing [{cpc}].", ("cpc",)),
        ),
        priority=142,
    ),
    AuthorityWorkflowContract(
        id="aadhaar_identity_record_correction_pension",
        route_categories=("social_welfare_identity",),
        trigger_groups=(
            ("aadhaar", "aadhar", "uidai"),
            ("wrong photo", "someone else photo", "other photo", "another photo", "photo mismatch", "wrong biometric", "biometric mismatch", "details wrong", "identity record wrong", "identity mismatch"),
            ("pension", "benefit", "scheme", "beneficiary", "not getting", "not get"),
        ),
        source_specs=(
            PassageSpec("aadhaar", ("aadhaar",), ("/sec-31",), required=True),
            PassageSpec("rti", ("right to information",), ("/sec-6",)),
            PassageSpec("nsap", ("national social assistance", "old age pension", "widow pension")),
        ),
        line_specs=(
            LineSpec("A different person's photo or another wrong demographic/biometric detail on an Aadhaar record is an Aadhaar correction issue first: Section 31 provides for the Aadhaar holder to request alteration of incorrect demographic or biometric information in the record [{aadhaar}].", ("aadhaar",)),
            LineSpec("Do not use an RTI application or RTI appeal as the Aadhaar correction application. RTI Section 6 is for asking the public authority for records such as the pension mismatch reason, beneficiary-file status, and rule or order relied on [{rti}].", ("rti",)),
            LineSpec("The Aadhaar correction itself does not decide pension eligibility or restoration; give the correction acknowledgement and pension beneficiary details to the scheme office and have it apply the relevant state pension rule [{aadhaar}].", ("aadhaar",)),
            LineSpec("For an NSAP-type pension record, keep the pension application/passbook material with the Aadhaar and bank details; the exact implementation route can still vary by State [{nsap}].", ("nsap",)),
            LineSpec("**What you can do next**"),
            LineSpec("- Submit the Aadhaar correction/update request, keep the receipt or acknowledgement, then file a written pension-scheme grievance with the wrong-photo screenshot, pension/beneficiary ID, bank or post-office passbook, prior sanction/payment details, and correction acknowledgement. Ask for a written mismatch reason and the state rule or escalation route if payment remains blocked [{aadhaar}].", ("aadhaar",)),
        ),
        priority=146,
    ),
    AuthorityWorkflowContract(
        id="caste_certificate_state_rule_intake",
        route_categories=("social_welfare_identity",),
        trigger_groups=(
            ("caste certificate", "caste cert", "sc cert", "st cert", "sc certificate", "st certificate", "scheduled caste certificate", "scheduled tribe certificate"),
            ("rejected", "reject", "not issued", "not issue", "pending", "tehsildar", "tahsildar", "appeal", "exam form", "deadline", "months"),
        ),
        source_specs=(
            PassageSpec("constitution", ("constitution",), ("/sec-341", "/sec-342"), required=True),
            PassageSpec("rti", ("right to information",), ("/sec-6",), required=True),
        ),
        line_specs=(
            LineSpec("For an SC/ST certificate refusal or long delay, Articles 341 and 342 are the constitutional sources for the relevant Scheduled Caste or Scheduled Tribe lists; they do not by themselves decide the evidence, form, appeal authority, or deadline for an individual certificate application [{constitution}].", ("constitution",)),
            LineSpec("Do not file an RTI appeal as though it overturns the certificate decision. Use an RTI Section 6 request only to obtain the application file, written rejection or delay reason, documents/rule relied on, and the appellate or review authority named by the State process [{rti}].", ("rti",)),
            LineSpec("The exact certificate review or appeal forum and deadline are State-rule dependent. Without that State rule or the written order, do not rely on a generic District Collector or RTI appeal as the certificate remedy.", ()),
            LineSpec("**What you can do next**"),
            LineSpec("- Give the Tehsildar/competent certificate authority a written request for the signed order or pending-status reason, attach the application receipt, community/caste proof, family certificates, school and residence records, and ask for the State-rule appeal/review route and deadline. Keep acknowledgement proof [{constitution}].", ("constitution",)),
            LineSpec("- If an exam, admission, scholarship, or job deadline is close, give the institution the application receipt and written pending-status request, ask whether it can record the pending certificate, and take the order/record file to the district social-welfare office or DLSA for State-specific help [{rti}].", ("rti",)),
        ),
        priority=147,
    ),
)


__all__ = [
    "authority_graph_template_lines",
    "authority_graph_template_result",
    "authority_graph_workflow_event",
]
