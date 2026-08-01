from __future__ import annotations

from dataclasses import replace

import pytest

from apps.api.legal_issue_plan import build_matter_plan
from apps.api.source_gap import (
    build_source_gap_event,
    is_active_plan_authority_entry,
    matter_plan_integrity_gap,
    missing_plan_authorities,
    missing_required_authorities,
    should_enforce_required_source,
    _passage_satisfies_plan_entry,
    _plan_anchor_matches,
    _section_anchor_matches,
    _source_pack_anchor_matches,
    _source_pack_title_matches,
    best_source_match,
)
from apps.api.common_workflow_contracts import WorkflowTemplateResult
from apps.api.main import _critical_route_needs_reviewed_contract, _source_gap_event_for_retrieved
from apps.api.matter_router import MatterRoute, route_matter


def _acid_passage(title: str, anchor: str) -> dict:
    lower_title = title.lower()
    if "bharatiya nyaya" in lower_title:
        source_pack = "bns_2023_acid_attack"
    elif "bharatiya nagarik" in lower_title:
        source_pack = "bnss_2023_fir_information_acid"
    elif "indian penal" in lower_title:
        source_pack = "ipc_1860_acid_attack"
    elif "criminal procedure" in lower_title:
        source_pack = "crpc_1973_fir_information_acid"
    else:
        source_pack = "pwdva_2005"
    return {
        "index": 1,
        "title": title,
        "anchor": anchor,
        "source_type": "bare_act",
        "document_id": anchor.split("/", 1)[0],
        "required_source_pack": source_pack,
        "text": f"Section {anchor.rsplit('sec-', 1)[-1]} authority heading.",
    }


def test_mgnrega_route_source_requires_verified_scheme_identity_and_reviewed_anchor():
    required = "MGNREGA 2005 wage, job-card, grievance and social-audit provisions"
    social_audit = {
        "index": 1,
        "title": "Mahatma Gandhi National Rural Employment Guarantee Act 2005",
        "anchor": "mgnrega-2005/sec-19@2005-09-07",
    }
    unrelated = {
        "index": 2,
        "title": "Bharatiya Nyaya Sanhita 2023",
        "anchor": "bns-2023/sec-340@2024-07-01",
    }

    assert best_source_match(required, [social_audit], query="fake muster roll social audit") == social_audit
    assert best_source_match(required, [unrelated], query="fake muster roll social audit") is None


def test_mgnrega_job_card_requirement_accepts_job_and_wage_sections():
    required = "MGNREGA 2005 wage, job-card, grievance and social-audit provisions"
    passage = {
        "index": 1,
        "title": "Mahatma Gandhi National Rural Employment Guarantee Act 2005",
        "anchor": "mgnrega-2005/sec-7@2005-09-07",
    }

    assert best_source_match(required, [passage], query="job demand ignored no unemployment allowance") == passage


def test_mgnrega_attendance_wage_query_does_not_require_social_audit_section():
    required = "MGNREGA 2005 wage, job-card, grievance and social-audit provisions"
    passage = {
        "index": 1,
        "title": "Mahatma Gandhi National Rural Employment Guarantee Act 2005",
        "anchor": "mgnrega-2005/sec-7@2005-09-07",
    }

    assert best_source_match(required, [passage], query="attendance shown but wages not paid") == passage


def test_mgnrega_composite_criminal_source_accepts_reviewed_bns_or_pca_only():
    required = "BNS/Prevention of Corruption Act where forged muster, fake job cards, bribe, or misappropriation facts exist"
    bns = {
        "index": 1,
        "title": "Bharatiya Nyaya Sanhita 2023",
        "anchor": "bns-2023/sec-340@2024-07-01",
    }
    unrelated_bns = {
        "index": 2,
        "title": "Bharatiya Nyaya Sanhita 2023",
        "anchor": "bns-2023/sec-351@2024-07-01",
    }
    pca = {
        "index": 3,
        "title": "Prevention of Corruption Act 1988",
        "anchor": "prevention-of-corruption-1988/sec-13@2018-07-26",
    }

    assert best_source_match(required, [bns], query="fake muster entries") == bns
    assert best_source_match(required, [pca], query="bribe for muster correction") == pca
    assert best_source_match(required, [unrelated_bns], query="fake muster entries") is None


def test_mgnrega_plan_accepts_pca_sibling_without_false_bns_gap():
    query = "muster roll fake entries BDO putting my name without me working khunti how complain"
    route = route_matter(query)
    plan = build_matter_plan(query, route)
    passages = [
        {
            "index": 1,
            "title": "Mahatma Gandhi National Rural Employment Guarantee Act 2005",
            "anchor": "mgnrega-2005/sec-19@2005-09-07",
            "document_id": "mgnrega-2005",
            "source_type": "bare_act",
            "required_source_pack": "mgnrega_2005",
        },
        {
            "index": 4,
            "title": "Mahatma Gandhi National Rural Employment Guarantee Act 2005",
            "anchor": "mgnrega-2005/sec-17@2005-09-07",
            "document_id": "mgnrega-2005",
            "source_type": "bare_act",
            "required_source_pack": "mgnrega_2005",
        },
        {
            "index": 2,
            "title": "Right to Information Act 2005",
            "anchor": "rti-2005/sec-19@2005-06-15",
            "document_id": "rti-2005",
            "source_type": "bare_act",
            "required_source_pack": "rti_2005",
        },
        {
            "index": 3,
            "title": "Prevention of Corruption Act 1988",
            "anchor": "prevention-of-corruption-1988/sec-13@2018-07-26",
            "document_id": "prevention-of-corruption-1988",
            "source_type": "bare_act",
            "required_source_pack": "prevention_corruption_1988_mgnrega_records",
        },
    ]

    assert plan is not None
    assert build_source_gap_event(
        query=query,
        route_category=route.category,
        required_sources=route.required_sources,
        passages=passages,
        plan=plan,
        legal_regime=route.legal_regime,
    ) is None


def test_mgnrega_plan_rejects_title_only_pca_for_composite_integrity_source():
    query = "muster roll fake entries BDO putting my name without me working khunti how complain"
    route = route_matter(query)
    plan = build_matter_plan(query, route)
    assert plan is not None
    passages = [
        {
            "index": 1,
            "title": "Mahatma Gandhi National Rural Employment Guarantee Act 2005",
            "anchor": "mgnrega-2005/sec-19@2005-09-07",
            "document_id": "mgnrega-2005",
            "source_type": "bare_act",
            "required_source_pack": "mgnrega_2005",
        },
        {
            "index": 2,
            "title": "Prevention of Corruption Act 1988",
            "anchor": "prevention-of-corruption-1988/sec-13@2018-07-26",
            "document_id": "prevention-of-corruption-1988",
            "source_type": "bare_act",
        },
    ]

    event = build_source_gap_event(
        query=query,
        route_category=route.category,
        required_sources=route.required_sources,
        passages=passages,
        plan=plan,
        legal_regime=route.legal_regime,
    )

    assert event is not None
    assert any(
        "BNS/Prevention of Corruption" in item["required_source"]
        for item in event["missing_required_sources"]
    )


def test_mgnrega_plan_rejects_case_law_for_composite_integrity_source():
    query = "muster roll fake entries BDO putting my name without me working khunti how complain"
    route = route_matter(query)
    plan = build_matter_plan(query, route)
    assert plan is not None
    passages = [
        {
            "index": 1,
            "title": "Mahatma Gandhi National Rural Employment Guarantee Act 2005",
            "anchor": "mgnrega-2005/sec-19@2005-09-07",
            "document_id": "mgnrega-2005",
            "source_type": "bare_act",
            "required_source_pack": "mgnrega_2005",
        },
        {
            "index": 2,
            "title": "Prevention of Corruption Act 1988",
            "anchor": "prevention-of-corruption-1988/sec-13@2018-07-26",
            "document_id": "prevention-of-corruption-1988",
            "source_type": "sc_judgment",
            "required_source_pack": "prevention_corruption_1988_mgnrega_records",
        },
    ]

    event = build_source_gap_event(
        query=query,
        route_category=route.category,
        required_sources=route.required_sources,
        passages=passages,
        plan=plan,
        legal_regime=route.legal_regime,
    )

    assert event is not None


def test_acid_route_fails_closed_on_empty_or_partial_incident_authority():
    query = "he poured acid on my face"
    route = route_matter(query)

    empty = build_source_gap_event(
        query=query,
        route_category=route.category,
        required_sources=route.required_sources,
        passages=[],
        legal_regime=route.legal_regime,
    )
    assert empty is not None
    assert empty["reason"] == "acid_incident_authority_gap"

    current_only = [
        _acid_passage("Bharatiya Nyaya Sanhita 2023", "bns-2023/sec-124"),
        _acid_passage("Bharatiya Nagarik Suraksha Sanhita 2023", "bnss-2023/sec-173"),
    ]
    partial = build_source_gap_event(
        query=query,
        route_category=route.category,
        required_sources=route.required_sources,
        passages=current_only,
        legal_regime=route.legal_regime,
    )
    assert partial is not None
    assert partial["reason"] == "acid_incident_authority_gap"


def test_acid_route_accepts_exact_current_and_legacy_pairs_when_date_unknown():
    query = "he poured acid on my face"
    route = route_matter(query)
    passages = [
        _acid_passage("Bharatiya Nyaya Sanhita 2023", "bns-2023/sec-124"),
        _acid_passage("Bharatiya Nagarik Suraksha Sanhita 2023", "bnss-2023/sec-173"),
        _acid_passage("Indian Penal Code 1860", "ipc-1860/sec-326a"),
        _acid_passage("Code of Criminal Procedure 1973", "crpc-1973/sec-154"),
    ]

    assert build_source_gap_event(
        query=query,
        route_category=route.category,
        required_sources=route.required_sources,
        passages=passages,
        legal_regime=route.legal_regime,
    ) is None


def test_shared_juvenile_section_can_satisfy_its_custody_transfer_pack():
    query = "16 yr boy detained adult jail 2 weeks already how to transfer observation home"
    route = route_matter(query)
    plan = build_matter_plan(query, route)
    assert plan is not None
    passages = [
        {
            "index": 1,
            "title": "Juvenile Justice (Care and Protection of Children) Act 2015",
            "anchor": "jj-2015/sec-9-official",
            "source_type": "bare_act",
            "document_id": "jj-2015",
            "required_source_pack": "jj_2015",
            "required_source_packs": ["jj_2015", "jj_2015_age_claim_court"],
            "authority_ids": [],
        },
        {
            "index": 2,
            "title": "Juvenile Justice (Care and Protection of Children) Act 2015",
            "anchor": "jj-2015/sec-94-official",
            "source_type": "bare_act",
            "document_id": "jj-2015",
            "required_source_pack": "jj_2015",
            "required_source_packs": ["jj_2015", "jj_2015_age_documents"],
            "authority_ids": [],
        },
        {
            "index": 3,
            "title": "Juvenile Justice (Care and Protection of Children) Act 2015",
            "anchor": "jj-2015/sec-10-official",
            "source_type": "bare_act",
            "document_id": "jj-2015",
            "required_source_pack": "jj_2015",
            "required_source_packs": ["jj_2015", "jj_2015_custody_transfer"],
            "authority_ids": [],
        },
    ]

    assert build_source_gap_event(
        query=query,
        route_category=route.category,
        required_sources=route.required_sources,
        passages=passages,
        plan=plan,
        legal_regime=route.legal_regime,
    ) is None


def test_juvenile_transfer_gate_requires_section_94_for_age_evidence_guidance():
    query = "16 yr boy detained adult jail 2 weeks already how to transfer observation home"
    route = route_matter(query)
    plan = build_matter_plan(query, route)
    assert plan is not None
    passages = [
        {
            "index": 1,
            "title": "Juvenile Justice (Care and Protection of Children) Act 2015",
            "anchor": "jj-2015/sec-9-official",
            "source_type": "bare_act",
            "document_id": "jj-2015",
            "required_source_pack": "jj_2015_age_claim_court",
            "required_source_packs": ["jj_2015", "jj_2015_age_claim_court"],
            "authority_ids": [],
        },
        {
            "index": 2,
            "title": "Juvenile Justice (Care and Protection of Children) Act 2015",
            "anchor": "jj-2015/sec-10-official",
            "source_type": "bare_act",
            "document_id": "jj-2015",
            "required_source_pack": "jj_2015_custody_transfer",
            "required_source_packs": ["jj_2015", "jj_2015_custody_transfer"],
            "authority_ids": [],
        },
    ]

    gap = build_source_gap_event(
        query=query,
        route_category=route.category,
        required_sources=route.required_sources,
        passages=passages,
        plan=plan,
        legal_regime=route.legal_regime,
    )

    assert gap is not None
    assert any(
        item.get("source_pack_id") == "jj_2015_age_documents"
        for item in gap["missing_required_sources"]
    )


@pytest.mark.parametrize("definition_anchor", ["/sec-2-t", "/sec-2-u", "/sec-4"])
def test_juvenile_transfer_gate_rejects_definition_as_custody_authority(definition_anchor: str):
    query = "16 yr boy detained adult jail 2 weeks already how to transfer observation home"
    route = route_matter(query)
    plan = build_matter_plan(query, route)
    assert plan is not None
    passages = [
        {
            "index": 1,
            "title": "Juvenile Justice (Care and Protection of Children) Act 2015",
            "anchor": "jj-2015/sec-9-official",
            "source_type": "bare_act",
            "document_id": "jj-2015",
            "required_source_pack": "jj_2015_age_claim_court",
            "required_source_packs": ["jj_2015", "jj_2015_age_claim_court"],
            "authority_ids": [],
        },
        {
            "index": 2,
            "title": "Juvenile Justice (Care and Protection of Children) Act 2015",
            "anchor": "jj-2015/sec-94-official",
            "source_type": "bare_act",
            "document_id": "jj-2015",
            "required_source_pack": "jj_2015_age_documents",
            "required_source_packs": ["jj_2015", "jj_2015_age_documents"],
            "authority_ids": [],
        },
        {
            "index": 3,
            "title": "Juvenile Justice (Care and Protection of Children) Act 2015",
            "anchor": f"jj-2015{definition_anchor}-official",
            "source_type": "bare_act",
            "document_id": "jj-2015",
            "required_source_pack": "jj_2015",
            "required_source_packs": ["jj_2015", "jj_2015_custody_transfer"],
            "authority_ids": [],
        },
    ]

    gap = build_source_gap_event(
        query=query,
        route_category=route.category,
        required_sources=route.required_sources,
        passages=passages,
        plan=plan,
        legal_regime=route.legal_regime,
    )

    assert gap is not None
    assert any(
        item.get("source_pack_id") == "jj_2015_custody_transfer"
        for item in gap["missing_required_sources"]
    )


def test_inlaw_acid_route_requires_pwdva_and_rejects_wrong_provenance():
    query = "my mother in law threatened acid attack but acid was later thrown"
    route = route_matter(query)
    base = [
        _acid_passage("Bharatiya Nyaya Sanhita 2023", "bns-2023/sec-124"),
        _acid_passage("Bharatiya Nagarik Suraksha Sanhita 2023", "bnss-2023/sec-173"),
        _acid_passage("Indian Penal Code 1860", "ipc-1860/sec-326a"),
        _acid_passage("Code of Criminal Procedure 1973", "crpc-1973/sec-154"),
    ]
    assert build_source_gap_event(
        query=query,
        route_category=route.category,
        required_sources=route.required_sources,
        passages=base,
        legal_regime=route.legal_regime,
    ) is not None

    complete = [
        *base,
        {
            "index": 5,
            "title": "Protection of Women from Domestic Violence Act 2005",
            "anchor": "domestic-violence-2005-official/sec-3-official",
            "source_type": "bare_act",
            "document_id": "domestic-violence-2005-official",
            "required_source_pack": "pwdva_2005",
            "text": "Section 3. Definition of domestic violence.",
        },
        {
            "index": 6,
            "title": "Protection of Women from Domestic Violence Act 2005",
            "anchor": "domestic-violence-2005-official/sec-18-official",
            "source_type": "bare_act",
            "document_id": "domestic-violence-2005-official",
            "required_source_pack": "pwdva_2005",
            "text": "Section 18. Protection orders.",
        },
    ]
    assert build_source_gap_event(
        query=query,
        route_category=route.category,
        required_sources=route.required_sources,
        passages=complete,
        legal_regime=route.legal_regime,
    ) is None

def test_husband_acid_route_rejects_legacy_pwdva_chunks():
    query = "my husband threatened acid attack on me"
    route = route_matter(query)
    base = [
        _acid_passage("Bharatiya Nyaya Sanhita 2023", "bns-2023/sec-351"),
        _acid_passage("Bharatiya Nagarik Suraksha Sanhita 2023", "bnss-2023/sec-173"),
        _acid_passage("Indian Penal Code 1860", "ipc-1860/sec-506"),
        _acid_passage("Code of Criminal Procedure 1973", "crpc-1973/sec-154"),
    ]
    missing = build_source_gap_event(
        query=query,
        route_category=route.category,
        required_sources=route.required_sources,
        passages=base,
        legal_regime=route.legal_regime,
    )
    assert missing is not None
    assert any(
        item["kind"] == "national_family_source_gap"
        for item in missing["missing_required_sources"]
    )

    complete = [
        *base,
        _acid_passage("Protection of Women from Domestic Violence Act 2005", "domestic-violence-2005/sec-3"),
        _acid_passage("Protection of Women from Domestic Violence Act 2005", "domestic-violence-2005/sec-18"),
    ]
    assert build_source_gap_event(
        query=query,
        route_category=route.category,
        required_sources=route.required_sources,
        passages=complete,
        legal_regime=route.legal_regime,
    ) is not None

    wrong_provenance = [
        {
            **passage,
            "required_source_pack": "unrelated_judgment_pack",
            "source_type": "sc_judgment",
        }
        for passage in complete
    ]
    assert build_source_gap_event(
        query=query,
        route_category=route.category,
        required_sources=route.required_sources,
        passages=wrong_provenance,
        legal_regime=route.legal_regime,
    ) is not None


def test_husband_acid_route_accepts_official_pwdva_supplement_chunks():
    query = "my husband threatened acid attack on me"
    route = route_matter(query)
    base = [
        _acid_passage("Bharatiya Nyaya Sanhita 2023", "bns-2023/sec-351"),
        _acid_passage("Bharatiya Nagarik Suraksha Sanhita 2023", "bnss-2023/sec-173"),
        _acid_passage("Indian Penal Code 1860", "ipc-1860/sec-506"),
        _acid_passage("Code of Criminal Procedure 1973", "crpc-1973/sec-154"),
    ]
    official = [
        {
            "index": 5,
            "title": "Protection of Women from Domestic Violence Act 2005",
            "anchor": "domestic-violence-2005-official/sec-3-official",
            "source_type": "bare_act",
            "document_id": "domestic-violence-2005-official",
            "required_source_pack": "pwdva_2005",
            "text": "Section 3. Definition of domestic violence.",
        },
        {
            "index": 6,
            "title": "Protection of Women from Domestic Violence Act 2005",
            "anchor": "domestic-violence-2005-official/sec-18-official",
            "source_type": "bare_act",
            "document_id": "domestic-violence-2005-official",
            "required_source_pack": "pwdva_2005",
            "text": "Section 18. Protection orders.",
        },
    ]

    assert build_source_gap_event(
        query=query,
        route_category=route.category,
        required_sources=route.required_sources,
        passages=[*base, *official],
        legal_regime=route.legal_regime,
    ) is None


def test_chemical_only_completed_route_has_a_canonical_source_gap_not_a_crash():
    query = "my husband beat me and chemical was thrown on me"
    route = route_matter(query)
    event = build_source_gap_event(
        query=query,
        route_category=route.category,
        required_sources=route.required_sources,
        passages=[],
        legal_regime=route.legal_regime,
    )
    assert event is not None
    assert event["reason"] == "acid_incident_authority_gap"
    assert any("chemical-exposure/hurt authority" in item["required_source"] for item in event["missing_required_sources"])


def test_acid_authority_gate_rejects_missing_or_foreign_identity_metadata():
    query = "he poured acid on my face"
    route = route_matter(query)
    complete = [
        _acid_passage("Bharatiya Nyaya Sanhita 2023", "bns-2023/sec-124"),
        _acid_passage("Bharatiya Nagarik Suraksha Sanhita 2023", "bnss-2023/sec-173"),
        _acid_passage("Indian Penal Code 1860", "ipc-1860/sec-326a"),
        _acid_passage("Code of Criminal Procedure 1973", "crpc-1973/sec-154"),
    ]
    missing_metadata = [
        {key: value for key, value in passage.items()
         if key not in {"document_id", "required_source_pack"}}
        for passage in complete
    ]
    assert build_source_gap_event(
        query=query,
        route_category=route.category,
        required_sources=route.required_sources,
        passages=missing_metadata,
        legal_regime=route.legal_regime,
    ) is not None

    wrong_document = [
        {**passage, "document_id": "999999"}
        if passage["title"].startswith("Bharatiya Nyaya")
        else passage
        for passage in complete
    ]
    assert build_source_gap_event(
        query=query,
        route_category=route.category,
        required_sources=route.required_sources,
        passages=wrong_document,
        legal_regime=route.legal_regime,
    ) is not None


def test_attempted_acid_attack_requires_attempt_and_underlying_offence_authorities():
    query = "he tried to throw acid at me but missed"
    route = route_matter(query)
    passages = [
        _acid_passage("Bharatiya Nyaya Sanhita 2023", "bns-2023/sec-124"),
        _acid_passage("Bharatiya Nagarik Suraksha Sanhita 2023", "bnss-2023/sec-173"),
        _acid_passage("Indian Penal Code 1860", "ipc-1860/sec-326a"),
        _acid_passage("Code of Criminal Procedure 1973", "crpc-1973/sec-154"),
    ]
    assert build_source_gap_event(
        query=query,
        route_category=route.category,
        required_sources=route.required_sources,
        passages=passages,
        legal_regime=route.legal_regime,
    ) is not None

    complete = [
        *passages,
        _acid_passage("Bharatiya Nyaya Sanhita 2023", "bns-2023/sec-62"),
        _acid_passage("Indian Penal Code 1860", "ipc-1860/sec-511"),
    ]
    assert build_source_gap_event(
        query=query,
        route_category=route.category,
        required_sources=route.required_sources,
        passages=complete,
        legal_regime=route.legal_regime,
    ) is None


def test_legacy_attempt_accepts_canonical_ipc_326b_with_ipc_511_and_crpc():
    query = "he tried to throw acid at me but missed"
    route = route_matter(query)
    passages = [
        _acid_passage("Indian Penal Code 1860", "ipc-1860/sec-511"),
        _acid_passage("Indian Penal Code 1860", "ipc-1860/sec-326b"),
        _acid_passage("Code of Criminal Procedure 1973", "crpc-1973/sec-154"),
    ]
    assert build_source_gap_event(
        query=query,
        route_category=route.category,
        required_sources=route.required_sources,
        passages=passages,
        legal_regime="legacy_ipc_crpc_evidence_for_pre_2024_incident",
    ) is None


def test_acid_dowry_word_alone_does_not_trigger_pwdva_authority_pair():
    query = "someone threatened acid attack over dowry"
    route = route_matter(query)
    passages = [
        _acid_passage("Bharatiya Nyaya Sanhita 2023", "bns-2023/sec-351"),
        _acid_passage("Bharatiya Nagarik Suraksha Sanhita 2023", "bnss-2023/sec-173"),
        _acid_passage("Indian Penal Code 1860", "ipc-1860/sec-506"),
        _acid_passage("Code of Criminal Procedure 1973", "crpc-1973/sec-154"),
    ]
    gap = build_source_gap_event(
        query=query,
        route_category=route.category,
        required_sources=route.required_sources,
        passages=passages,
        legal_regime=route.legal_regime,
    )
    assert gap is None or all(
        "PWDVA" not in str(item.get("required_source", ""))
        for item in gap.get("missing_required_sources", [])
    )

def test_matter_plan_integrity_rejects_empty_ledger():
    query = "my landlord is refusing to return my deposit"
    route = route_matter(query)
    plan = build_matter_plan(query, route)
    assert plan is not None

    broken = replace(plan, authority_ledger=[])
    gap = matter_plan_integrity_gap(broken, query)

    assert gap is not None
    assert gap["gap_kinds"] == ["empty_authority_ledger"]


def test_matter_plan_integrity_rejects_unbound_enforceable_entry():
    query = "I registered my will with the sub registrar; do I need to update it every year?"
    route = route_matter(query)
    plan = build_matter_plan(query, route)
    assert plan is not None

    entry = replace(plan.authority_ledger[0], source_pack_id=None)
    broken = replace(plan, authority_ledger=[entry, *plan.authority_ledger[1:]])
    gap = matter_plan_integrity_gap(broken, query)

    assert gap is not None
    assert "missing_source_pack_binding" in gap["gap_kinds"]


def test_matter_plan_integrity_accepts_exact_will_source_bindings():
    query = "I registered my will with the sub registrar; do I need to update it every year?"
    route = route_matter(query)
    plan = build_matter_plan(query, route)

    assert plan is not None
    assert matter_plan_integrity_gap(plan, query) is None


def test_matter_plan_integrity_ignores_procedural_and_document_guidance():
    query = "my landlord is refusing to return my deposit"
    plan = build_matter_plan(query, route_matter(query))
    assert plan is not None
    assert plan.authority_ledger

    guidance_only = replace(
        plan.authority_ledger[0],
        source=(
            "Court rules and practice directions for filing, plus the rent "
            "agreement, receipts, and possession documents"
        ),
        authority_id="authority_guidance_only",
        registry_key=None,
        identity_status="provisional",
        canonical_name=None,
        act=None,
        section=None,
        source_pack_id=None,
        required_anchor_patterns=[],
        must_cite=True,
        conditional=False,
    )
    guidance_plan = replace(plan, authority_ledger=[guidance_only])

    assert matter_plan_integrity_gap(guidance_plan, query) is None


@pytest.mark.parametrize(
    "guidance_source",
    [
        "Consumer Protection Rules / e-Daakhil procedure",
        "court rules/practice directions for the court named in the summons",
        "state maintenance tribunal rules",
        "state pension/scholarship/ration scheme rules",
        "municipal corporation / Town Vending Committee procedure",
        "state disability certificate / UDID procedure",
        "NALSA/SLSA/DLSA legal-aid procedure for application and assignment",
    ],
)
def test_matter_plan_integrity_ignores_explicit_generic_route_procedures(
    guidance_source: str,
):
    query = "my landlord is refusing to return my deposit"
    plan = build_matter_plan(query, route_matter(query))
    assert plan is not None

    guidance_only = replace(
        plan.authority_ledger[0],
        source=guidance_source,
        authority_id="generic_route_guidance",
        registry_key=None,
        identity_status="provisional",
        canonical_name=None,
        act=None,
        section=None,
        source_pack_id=None,
        required_anchor_patterns=[],
        must_cite=True,
        conditional=False,
    )
    guidance_plan = replace(plan, authority_ledger=[guidance_only])

    assert matter_plan_integrity_gap(guidance_plan, query) is None


def test_generic_local_pointer_is_active_when_it_is_the_only_legal_basis():
    entry = {
        "authority_id": "generic_only",
        "source": "state education rules",
        "must_cite": True,
        "conditional": False,
        "priority": "must_cite",
    }
    plan = {"authority_ledger": [entry]}

    assert is_active_plan_authority_entry(entry, plan=plan, query="school admission denied") is True


@pytest.mark.parametrize(
    ("required_source", "query"),
    [
        ("state education rules", "school admission denied despite passing exam"),
        ("state drug-control authority procedure", "drug inspector seized samples from my medical store"),
        ("state motor vehicle rules / traffic police e-challan procedure", "traffic police issued a challan to my auto"),
    ],
)
def test_legacy_route_only_state_procedure_is_fail_closed_when_material(
    required_source: str,
    query: str,
):
    missing = missing_required_authorities(
        required_sources=[required_source],
        passages=[],
        query=query,
    )

    assert [item["required_source"] for item in missing] == [required_source]


def test_state_context_terms_use_word_boundaries():
    assert missing_required_authorities(
        required_sources=["state motor vehicle rules / traffic police e-challan procedure"],
        passages=[],
        query="automatic transmission problem in my car",
    ) == []
    assert missing_required_authorities(
        required_sources=["state education rules"],
        passages=[],
        query="my etc. notice has a typo",
    ) == []


@pytest.mark.parametrize(
    "concrete_source",
    [
        "Mediation Act 2023 / rules where notified procedure applies",
        "Consumer Protection Act 2019 / Consumer Protection Rules / e-Daakhil procedure",
        "Street Vendors Act 2014 / municipal corporation / Town Vending Committee procedure",
        "Maintenance and Welfare of Parents and Senior Citizens Act 2007 / state maintenance tribunal rules",
    ],
)
def test_matter_plan_integrity_keeps_concrete_procedural_authority_blocking(
    concrete_source: str,
):
    query = "my landlord is refusing to return my deposit"
    plan = build_matter_plan(query, route_matter(query))
    assert plan is not None

    concrete = replace(
        plan.authority_ledger[0],
        source=concrete_source,
        authority_id="mediation_act_procedure",
        registry_key=None,
        identity_status="provisional",
        canonical_name=None,
        act=None,
        section=None,
        source_pack_id=None,
        required_anchor_patterns=[],
        must_cite=True,
        conditional=False,
    )
    concrete_plan = replace(plan, authority_ledger=[concrete])

    gap = matter_plan_integrity_gap(concrete_plan, query)
    assert gap is not None
    assert "missing_source_pack_binding" in gap["gap_kinds"]


@pytest.mark.parametrize(
    "concrete_context_source",
    [
        "Hindu Marriage Act 1955 / personal law and local filing rules",
        "Hindu Marriage Act / personal law and local filing rules",
        "Hindu Marriage Act Section 13 / personal law and local filing rules",
        "Hindu Marriage Act, 1955 / personal law and local filing rules",
        "victim-compensation and DLSA procedure / SC-ST Act 1989",
    ],
)
def test_matter_plan_integrity_does_not_hide_concrete_authority_in_context_label(
    concrete_context_source: str,
):
    query = "my landlord is refusing to return my deposit"
    plan = build_matter_plan(query, route_matter(query))
    assert plan is not None

    concrete_context = replace(
        plan.authority_ledger[0],
        source=concrete_context_source,
        authority_id="composite_concrete_context",
        registry_key=None,
        identity_status="provisional",
        canonical_name=None,
        act=None,
        section=None,
        source_pack_id=None,
        required_anchor_patterns=[],
        must_cite=True,
        conditional=False,
    )
    concrete_plan = replace(plan, authority_ledger=[concrete_context])

    gap = matter_plan_integrity_gap(concrete_plan, query)
    assert gap is not None
    assert "missing_source_pack_binding" in gap["gap_kinds"]


def test_conditional_concrete_victim_compensation_authority_stays_blocking():
    query = "acid attack survivor needs compensation and SC-ST Act remedy"
    plan = build_matter_plan(query, route_matter(query))
    assert plan is not None

    concrete = replace(
        plan.authority_ledger[0],
        source="victim-compensation and DLSA procedure / SC-ST Act 1989",
        authority_id="conditional_concrete_victim_compensation",
        registry_key=None,
        identity_status="provisional",
        canonical_name=None,
        act=None,
        section=None,
        source_pack_id=None,
        required_anchor_patterns=[],
        must_cite=False,
        conditional=True,
    )
    concrete_plan = replace(plan, authority_ledger=[concrete])

    gap = matter_plan_integrity_gap(concrete_plan, query)
    assert gap is not None
    assert "missing_source_pack_binding" in gap["gap_kinds"]


@pytest.mark.parametrize(
    "concrete_context_source",
    [
        "Right to Education Act 2009 / state education rules",
        "RTE / state education rules",
        "BSA / state education rules",
        "RERA / state education rules",
        "IBC / state education rules",
        "PESA / state education rules",
        "BOCW / state education rules",
        "RTI / state education rules",
        "NDPS / state education rules",
        "NFSA / state pension/scholarship/ration scheme rules",
        "RFCTLARR / state pension/scholarship/ration scheme rules",
        "MMDR / state pension/scholarship/ration scheme rules",
        "DPDP / state pension/scholarship/ration scheme rules",
        "JJ / state pension/scholarship/ration scheme rules",
        "NI / state pension/scholarship/ration scheme rules",
        "SC/ST / state caste-certificate issuance and appeal rules",
        "SC/ST Act 1989 / state caste-certificate issuance and appeal rules",
    ],
)
def test_conditional_concrete_education_or_caste_authority_stays_blocking(
    concrete_context_source: str,
):
    query = "child school admission denied and caste certificate appeal is needed"
    plan = build_matter_plan(query, route_matter(query))
    assert plan is not None

    concrete = replace(
        plan.authority_ledger[0],
        source=concrete_context_source,
        authority_id="conditional_concrete_education_or_caste",
        registry_key=None,
        identity_status="provisional",
        canonical_name=None,
        act=None,
        section=None,
        source_pack_id=None,
        required_anchor_patterns=[],
        must_cite=False,
        conditional=True,
    )
    concrete_plan = replace(plan, authority_ledger=[concrete])

    gap = matter_plan_integrity_gap(concrete_plan, query)
    assert gap is not None
    assert "missing_source_pack_binding" in gap["gap_kinds"]


@pytest.mark.parametrize(
    "fact_context_source",
    [
        "religion/personal-law and family-tree facts / Hindu Marriage Act 1955",
        "records only after the route is identified / BOCW Act 1996",
    ],
)
def test_fact_context_label_does_not_hide_concrete_authority(
    fact_context_source: str,
):
    query = "my landlord is refusing to return my deposit"
    plan = build_matter_plan(query, route_matter(query))
    assert plan is not None

    concrete = replace(
        plan.authority_ledger[0],
        source=fact_context_source,
        authority_id="fact_context_with_concrete_authority",
        registry_key=None,
        identity_status="provisional",
        canonical_name=None,
        act=None,
        section=None,
        source_pack_id=None,
        required_anchor_patterns=[],
        must_cite=True,
        conditional=False,
    )
    concrete_plan = replace(plan, authority_ledger=[concrete])

    gap = matter_plan_integrity_gap(concrete_plan, query)
    assert gap is not None
    assert "missing_source_pack_binding" in gap["gap_kinds"]


@pytest.mark.parametrize(
    "fact_context_source",
    [
        "NFSA / records only after the route is identified",
        "RFCTLARR / records only to identify the claim",
        "DPDP / religion/personal-law and family-tree facts",
        "JJ / labour/DLSA grievance route",
    ],
)
def test_alias_only_fact_context_label_does_not_hide_concrete_authority(
    fact_context_source: str,
):
    query = "my landlord is refusing to return my deposit"
    plan = build_matter_plan(query, route_matter(query))
    assert plan is not None

    concrete = replace(
        plan.authority_ledger[0],
        source=fact_context_source,
        authority_id="alias_only_fact_context_with_concrete_authority",
        registry_key=None,
        identity_status="provisional",
        canonical_name=None,
        act=None,
        section=None,
        source_pack_id=None,
        required_anchor_patterns=[],
        must_cite=True,
        conditional=False,
    )
    concrete_plan = replace(plan, authority_ledger=[concrete])

    gap = matter_plan_integrity_gap(concrete_plan, query)
    assert gap is not None
    assert "missing_source_pack_binding" in gap["gap_kinds"]


@pytest.mark.parametrize(
    "fact_context_source",
    [
        "NFSA / records only after the route is identified",
        "DPDP / religion/personal-law and family-tree facts",
    ],
)
def test_conditional_alias_composites_are_enforced_by_both_source_gates(
    fact_context_source: str,
):
    """Plan integrity and post-retrieval checks must share one classifier."""
    query = "my landlord is refusing to return my deposit"
    plan = build_matter_plan(query, route_matter(query))
    assert plan is not None

    concrete = replace(
        plan.authority_ledger[0],
        source=fact_context_source,
        authority_id="conditional_alias_composite",
        registry_key=None,
        identity_status="provisional",
        canonical_name=None,
        act=None,
        section=None,
        source_pack_id=None,
        required_anchor_patterns=[],
        must_cite=True,
        conditional=True,
    )
    concrete_plan = replace(plan, authority_ledger=[concrete])

    integrity_gap = matter_plan_integrity_gap(concrete_plan, query)
    assert integrity_gap is not None
    assert "missing_source_pack_binding" in integrity_gap["gap_kinds"]

    missing = missing_plan_authorities(
        plan=concrete_plan,
        passages=[],
        query=query,
    )
    assert [item["required_source"] for item in missing] == [fact_context_source]


def test_matter_plan_integrity_keeps_unknown_criminal_regime_as_intake_not_gap():
    query = "police refused to register FIR for theft of my bike where do I go next"
    plan = build_matter_plan(query, route_matter(query))
    assert plan is not None
    assert plan.incident_date_status in {
        "needed_for_criminal_regime",
        "incident_date_needed_for_bns_bnss_bsa_vs_ipc_crpc",
    }

    assert matter_plan_integrity_gap(plan, query) is None


def test_matter_plan_integrity_does_not_block_mixed_regime_family_context():
    query = "in-laws not giving back my jewellery streedhan after husband died"
    plan = build_matter_plan(query, route_matter(query))
    assert plan is not None
    mixed = next(
        entry for entry in plan.authority_ledger
        if entry.note == "date_dependent_regime_choose_by_incident_date"
    )
    assert mixed.source_pack_id is None
    assert matter_plan_integrity_gap(plan, query) is None

    deferred_plan = replace(plan, authority_ledger=[mixed])
    assert missing_plan_authorities(
        plan=deferred_plan,
        passages=[],
        query=query,
    ) == []
    assert build_source_gap_event(
        query=query,
        route_category=route_matter(query).category,
        required_sources=[],
        passages=[],
        plan=deferred_plan,
    ) is None


def test_matter_plan_integrity_does_not_force_compound_constitution_into_one_pack():
    query = "police took my brother yesterday no arrest memo given dk basu kya hai"
    plan = build_matter_plan(query, route_matter(query))
    assert plan is not None
    assert any("Articles 21 and 22" in entry.source for entry in plan.authority_ledger)
    assert matter_plan_integrity_gap(plan, query) is None


def test_matter_plan_integrity_does_not_bypass_nonconstitutional_composite():
    query = "my customer gave me a cheque and it bounced, what is the deadline to send notice"
    plan = build_matter_plan(query, route_matter(query))
    assert plan is not None
    for number_pair in ("138 and 139", "21 and 22"):
        composite = replace(
            plan.authority_ledger[0],
            source=f"Negotiable Instruments Act 1881 Articles {number_pair}",
            authority_id="authority_nonconstitutional_composite",
            registry_key=None,
            identity_status="provisional",
            canonical_name="negotiable instruments act 1881",
            act="Negotiable Instruments Act 1881",
            section=None,
            source_pack_id=None,
            required_anchor_patterns=[],
            must_cite=True,
            conditional=False,
        )
        broken = replace(plan, authority_ledger=[composite], retrieval_sources=[])

        gap = matter_plan_integrity_gap(broken, query)
        assert gap is not None
        assert gap["gap_kinds"] == ["missing_source_pack_binding"]


def test_matter_plan_integrity_requires_regime_packs_before_date_bypass():
    query = "ndps bail rejected 6 times by session court husband 3 yrs in tihar option"
    plan = build_matter_plan(query, route_matter(query))
    assert plan is not None
    date_entry = next(
        entry for entry in plan.authority_ledger
        if entry.note == "date_dependent_regime_choose_by_incident_date"
    )
    broken = replace(plan, authority_ledger=[date_entry], retrieval_sources=[])

    gap = matter_plan_integrity_gap(broken, query)
    assert gap is not None
    assert gap["gap_kinds"] == ["missing_source_pack_binding"]

    assert missing_plan_authorities(
        plan=broken,
        passages=[],
        query=query,
    )
    source_gap = build_source_gap_event(
        query=query,
        route_category=route_matter(query).category,
        required_sources=[],
        passages=[],
        plan=broken,
    )
    assert source_gap is not None
    assert source_gap["outcome"] == "source_gap_handoff"


@pytest.mark.parametrize(
    "composite_source",
    [
        "Constitution Articles 21 and 22 arrest and custody safeguards",
        "Constitution Articles 21 & 22 arrest and custody safeguards",
        "Constitution Articles 21, 22 arrest and custody safeguards",
        "Constitution Article 21 & 22 arrest and custody safeguards",
        "Constitution Article 21/22 arrest and custody safeguards",
    ],
)
def test_split_constitution_articles_satisfy_post_retrieval_and_final_gap_gates(
    composite_source: str,
):
    query = "police took my brother yesterday no arrest memo given dk basu kya hai"
    route = route_matter(query)
    plan = build_matter_plan(query, route)
    assert plan is not None
    entry = replace(
        plan.authority_ledger[0],
        source=composite_source,
        authority_id="constitution_articles_21_22_composite",
        registry_key=None,
        identity_status="provisional",
        canonical_name="constitution of india",
        act="Constitution of India",
        section=None,
        source_pack_id=None,
        required_anchor_patterns=[],
        must_cite=True,
        conditional=False,
    )
    composite_plan = replace(plan, authority_ledger=[entry])
    passages = [
        {
            "index": 1,
            "title": "Constitution of India",
            "anchor": "constitution-india/sec-21",
            "source_type": "bare_act",
            "required_source_pack": "constitution_article_21",
            "text": "Constitution of India Article 21 protection of life and personal liberty.",
        },
        {
            "index": 2,
            "title": "Constitution of India",
            "anchor": "constitution-india/sec-22",
            "source_type": "bare_act",
            "required_source_pack": "constitution_article_22",
            "text": "Constitution of India Article 22 safeguards against arrest and detention.",
        },
    ]

    assert matter_plan_integrity_gap(composite_plan, query) is None
    assert missing_plan_authorities(
        plan=composite_plan,
        passages=passages,
        query=query,
    ) == []
    assert build_source_gap_event(
        query=query,
        route_category=route.category,
        required_sources=[],
        passages=passages,
        plan=composite_plan,
    ) is None

    assert build_source_gap_event(
        query=query,
        route_category=route.category,
        required_sources=[composite_source],
        passages=passages,
        plan=None,
    ) is None
    assert build_source_gap_event(
        query=query,
        route_category=route.category,
        required_sources=[composite_source],
        passages=passages[:1],
        plan=None,
    ) is not None

    lawyer_access_entry = replace(
        entry,
        source="Constitution Articles 21 and 22 lawyer-access safeguards",
    )
    lawyer_access_plan = replace(composite_plan, authority_ledger=[lawyer_access_entry])
    assert missing_plan_authorities(
        plan=lawyer_access_plan,
        passages=[passages[1]],
        query=query,
    )
    assert build_source_gap_event(
        query=query,
        route_category=route.category,
        required_sources=[],
        passages=[passages[1]],
        plan=lawyer_access_plan,
    ) is not None

    assert missing_plan_authorities(
        plan=composite_plan,
        passages=passages[:1],
        query=query,
    )
    wrong_provenance = [
        {
            **passage,
            "required_source_pack": "unrelated_constitution_pack",
            "source_type": "sc_judgment",
        }
        for passage in passages
    ]
    assert missing_plan_authorities(
        plan=composite_plan,
        passages=wrong_provenance,
        query=query,
    )

    swapped_pack = [
        {**passages[0], "required_source_pack": "constitution_article_22"},
        {**passages[1], "required_source_pack": "constitution_article_21"},
    ]
    assert missing_plan_authorities(
        plan=composite_plan,
        passages=swapped_pack,
        query=query,
    )

    legacy_wrong_provenance = [
        {
            **passage,
            "required_source_pack": "unrelated_pack",
            "source_type": "sc_judgment",
            "anchor": "unrelated-document/sec-21" if index == 0 else "unrelated-document/sec-22",
        }
        for index, passage in enumerate(passages)
    ]
    assert build_source_gap_event(
        query=query,
        route_category=route.category,
        required_sources=[composite_source],
        passages=legacy_wrong_provenance,
        plan=None,
    ) is not None

    legacy_swapped_pack = [
        {**passages[0], "required_source_pack": "constitution_article_22"},
        {**passages[1], "required_source_pack": "constitution_article_21"},
    ]
    assert build_source_gap_event(
        query=query,
        route_category=route.category,
        required_sources=[composite_source],
        passages=legacy_swapped_pack,
        plan=None,
    ) is not None

    generic_legal_aid_pack = [
        {**passage, "required_source_pack": "constitution_legal_aid"}
        for passage in passages
    ]
    assert build_source_gap_event(
        query=query,
        route_category=route.category,
        required_sources=[composite_source],
        passages=generic_legal_aid_pack,
        plan=None,
    ) is None


def test_explicit_article_pack_anchor_is_not_rewritten_to_an_unstored_article_anchor():
    query = "father in jail heart disease medicine stopped need interim medical bail"
    route = route_matter(query)
    plan = build_matter_plan(query, route)
    assert plan is not None
    article_21 = next(
        entry
        for entry in plan.authority_ledger
        if entry.source_pack_id == "constitution_article_21"
    )
    article_only_plan = replace(plan, authority_ledger=[article_21])
    passage = {
        "index": 1,
        "title": "Constitution of India",
        "anchor": "constitution-india/sec-21-official",
        "document_id": "constitution-india",
        "source_type": "bare_act",
        "required_source_pack": "constitution_article_21",
        "required_source_packs": ["constitution_article_21"],
        "authority_ids": [article_21.authority_id],
        "text": "Constitution of India, Article 21. Protection of life and personal liberty.",
    }

    assert missing_plan_authorities(
        plan=article_only_plan,
        passages=[passage],
        query=query,
    ) == []
    assert build_source_gap_event(
        query=query,
        route_category=route.category,
        required_sources=[],
        passages=[passage],
        plan=article_only_plan,
    ) is None


def test_legacy_oxford_comma_constitution_list_requires_all_articles():
    query = "police took my brother yesterday no arrest memo given dk basu kya hai"
    route = route_matter(query)
    source = "Constitution Articles 21, 22, and 23 arrest and custody safeguards"
    passages = [
        {
            "title": "Constitution of India",
            "anchor": f"constitution-india/sec-{number}",
            "source_type": "bare_act",
        }
        for number in (21, 22, 23)
    ]

    assert build_source_gap_event(
        query=query,
        route_category=route.category,
        required_sources=[source],
        passages=passages,
        plan=None,
    ) is None
    assert build_source_gap_event(
        query=query,
        route_category=route.category,
        required_sources=[source],
        passages=passages[:2],
        plan=None,
    ) is not None


def test_matter_plan_integrity_rejects_one_mixed_regime_pack_as_both_regimes():
    query = "ndps bail rejected 6 times by session court husband 3 yrs in tihar option"
    plan = build_matter_plan(query, route_matter(query))
    assert plan is not None
    date_entry = next(
        entry for entry in plan.authority_ledger
        if entry.note == "date_dependent_regime_choose_by_incident_date"
    )
    mixed_pack = replace(
        plan.retrieval_sources[0],
        source_pack_id="bnss_crpc_mixed_comparison",
        title_patterns=["BNSS 2023 / CrPC 1973 comparison"],
        doc_ids=["mixed-comparison"],
        source_types=["bare_act"],
    )
    broken = replace(
        plan,
        authority_ledger=[date_entry],
        retrieval_sources=[mixed_pack],
    )

    gap = matter_plan_integrity_gap(broken, query)
    assert gap is not None
    assert gap["gap_kinds"] == ["missing_source_pack_binding"]


def test_source_gap_detects_missing_route_authority():
    missing = missing_required_authorities(
        required_sources=["CGST Act 2017 Section 67 inspection/search/seizure source"],
        passages=[
            {
                "index": 1,
                "title": "Consumer Protection Act 2019",
                "anchor": "consumer-protection-2019/sec-35",
                "source_type": "bare_act",
            }
        ],
        query="gst officer searched my shop without order",
    )

    assert missing == [
        {
            "required_source": "CGST Act 2017 Section 67 inspection/search/seizure source",
            "kind": "national_tax_source_gap",
        }
    ]


def test_source_gap_does_not_fire_when_matching_source_present():
    missing = missing_required_authorities(
        required_sources=["CGST Act 2017 Section 67 inspection/search/seizure source"],
        passages=[
            {
                "index": 1,
                "title": "Central Goods and Services Tax Act 2017",
                "anchor": "cgst-2017/sec-67",
                "source_type": "bare_act",
            }
        ],
        query="gst officer searched my shop without order",
    )

    assert missing == []


def test_environment_water_route_fails_closed_without_exact_water_act_passage():
    query = "my borewell water has come bad neighbours factory throwing chemicals"
    route = route_matter(query)
    plan = build_matter_plan(query, route)
    assert plan is not None

    unrelated = [{
        "index": 1,
        "title": "Registration Act 1908",
        "anchor": "registration-1908/sec-17",
        "source_type": "bare_act",
        "text": "Section 17 concerns registration of documents.",
    }]
    missing = missing_plan_authorities(plan=plan, passages=unrelated, query=query)

    assert any(
        item["required_source"].startswith(
            "Water (Prevention and Control of Pollution) Act 1974"
        )
        for item in missing
    )
    gap = build_source_gap_event(
        query=query,
        route_category=route.category,
        required_sources=route.required_sources,
        passages=unrelated,
        plan=plan,
    )
    assert gap is not None
    assert gap["outcome"] == "source_gap_handoff"


def test_environment_water_route_accepts_exact_water_act_passage():
    query = "my borewell water has come bad neighbours factory throwing chemicals"
    route = route_matter(query)
    plan = build_matter_plan(query, route)
    assert plan is not None

    exact_water_act = {
        "index": 1,
        "title": "Water (Prevention and Control of Pollution) Act 1974",
        "anchor": "water-pollution-1974/sec-25",
        "source_type": "bare_act",
        "required_source_pack": "water_pollution_1974",
        "text": "Section 25 restrictions on new outlets and new discharges.",
    }
    missing = missing_plan_authorities(
        plan=plan,
        passages=[exact_water_act],
        query=query,
    )

    assert not any(
        item["required_source"].startswith(
            "Water (Prevention and Control of Pollution) Act 1974"
        )
        for item in missing
    )


def test_housing_pet_route_does_not_use_generic_consumer_source_as_substitute():
    query = "society management has put a fine of 25000 on me for keeping a pet without prior approval"
    route = route_matter(query)
    plan = build_matter_plan(query, route)
    assert plan is not None

    gap = build_source_gap_event(
        query=query,
        route_category=route.category,
        required_sources=route.required_sources,
        passages=[{
            "index": 1,
            "title": "Consumer Protection Act 2019",
            "anchor": "consumer-protection-2019/sec-39",
            "source_type": "bare_act",
            "text": "Section 39 concerns relief in a consumer complaint.",
        }],
        plan=plan,
    )

    assert gap is not None
    assert gap["reason"] == "housing_pet_source_gap"
    assert gap["gap_kinds"] == ["state_or_local_authority_gap"]
    assert gap["safe_handoff_only"] is True


def test_housing_pet_route_does_not_treat_cooperative_judgment_as_controlling_authority():
    query = "society management has put a fine of 25000 on me for keeping a pet without prior approval"
    route = route_matter(query)
    plan = build_matter_plan(query, route)
    assert plan is not None

    gap = build_source_gap_event(
        query=query,
        route_category=route.category,
        required_sources=route.required_sources,
        passages=[{
            "index": 1,
            "title": "CO-OPERATIVE HOUSING SOCIETY",
            "anchor": "2022-insc-33#header",
            "source_type": "sc_judgment",
            "required_source_pack": "cooperative_housing_society_case_law",
            "text": "The cooperative housing society dispute concerns the society's governing documents.",
        }],
        plan=plan,
    )

    assert gap is not None
    assert gap["reason"] == "housing_pet_source_gap"
    assert gap["safe_handoff_only"] is True


def test_housing_pet_route_accepts_exact_reviewed_bmc_authority():
    query = "society management has put a fine of 25000 on me for keeping a pet without prior approval in Mumbai"
    route = route_matter(query)
    plan = build_matter_plan(query, route)
    assert plan is not None

    gap = build_source_gap_event(
        query=query,
        route_category=route.category,
        required_sources=route.required_sources,
        passages=[{
            "index": 1,
            "title": "BMC Guidelines with respect to Pet & Street dogs, RWAs and AOAs",
            "anchor": "bmc-pet-dog-guidelines#pet-dog-residents",
            "source_type": "circular",
            "document_id": "bmc-pet-dog-guidelines",
            "required_source_pack": "bmc_pet_guidelines_ban",
            "text": "BMC pet guidance for residents and housing societies.",
        }],
        plan=plan,
    )

    assert gap is None


def test_housing_pet_route_rejects_bmc_authority_for_explicit_non_mumbai_query():
    query = "society management has put a fine of 25000 on me for keeping a pet without prior approval in Delhi"
    route = route_matter(query)
    plan = build_matter_plan(query, route)
    assert plan is not None

    gap = build_source_gap_event(
        query=query,
        route_category=route.category,
        required_sources=route.required_sources,
        passages=[{
            "index": 1,
            "title": "BMC Guidelines with respect to Pet & Street dogs, RWAs and AOAs",
            "anchor": "bmc-pet-dog-guidelines#pet-dog-residents",
            "source_type": "circular",
            "document_id": "bmc-pet-dog-guidelines",
            "required_source_pack": "bmc_pet_guidelines_ban",
            "text": "BMC pet guidance for residents and housing societies.",
        }],
        plan=plan,
    )

    assert gap is not None
    assert gap["reason"] == "housing_pet_source_gap"


def test_constitution_rti_and_hma_split_neighbors_do_not_clear_exact_requirements():
    cases = [
        (
            "Constitution of India Article 22",
            "Constitution of India",
            "constitution-india/sec-22-a",
            "Constitution of India, Article 22A\n22A. Neighbouring provision.",
            "constitutional_authority_gap",
            "police detained me and I want to check Article 22",
        ),
        (
            "Right to Information Act 2005 Section 6",
            "Right to Information Act 2005",
            "rti-2005/sec-6-a",
            "Right to Information Act 2005, Section 6A\n6A. Neighbouring provision.",
            "national_statute_retrieval_gap",
            "the public office rejected my RTI application and I want Section 6",
        ),
        (
            "Hindu Marriage Act 1955 Section 13A",
            "Hindu Marriage Act 1955",
            "hindu-marriage-1955/sec-13-a",
            "Hindu Marriage Act 1955, Section 13\n13. Divorce.",
            "national_statute_retrieval_gap",
            "my wife wants divorce under Hindu Marriage Act Section 13A",
        ),
    ]
    for required_source, title, anchor, text, kind, query in cases:
        assert missing_required_authorities(
            required_sources=[required_source],
            passages=[{
                "index": 1,
                "title": title,
                "anchor": anchor,
                "text": text,
                "source_type": "bare_act",
            }],
            query=query,
        ) == [{"required_source": required_source, "kind": kind}]


def test_constitution_article_22_does_not_accept_article_22a_split_fragment():
    assert missing_required_authorities(
        required_sources=["Constitution of India Article 22"],
        passages=[{
            "index": 1,
            "title": "Constitution of India",
            "anchor": "constitution-india/sec-22-a",
            "text": "Constitution of India, Article 22A\n22A. Neighbouring provision.",
            "source_type": "bare_act",
        }],
        query="police detained me and I want to check Article 22",
    ) == [{
        "required_source": "Constitution of India Article 22",
        "kind": "constitutional_authority_gap",
    }]


def test_rti_section_6_does_not_accept_section_6a_split_fragment():
    assert missing_required_authorities(
        required_sources=["Right to Information Act 2005 Section 6"],
        passages=[{
            "index": 1,
            "title": "Right to Information Act 2005",
            "anchor": "rti-2005/sec-6-a",
            "text": "Right to Information Act 2005, Section 6A\n6A. Neighbouring provision.",
            "source_type": "bare_act",
        }],
        query="the public office rejected my RTI application and I want Section 6",
    ) == [{
        "required_source": "Right to Information Act 2005 Section 6",
        "kind": "national_statute_retrieval_gap",
    }]


def test_hma_section_13a_does_not_accept_section_13_fragment():
    assert missing_required_authorities(
        required_sources=["Hindu Marriage Act 1955 Section 13A"],
        passages=[{
            "index": 1,
            "title": "Hindu Marriage Act 1955",
            "anchor": "hindu-marriage-1955/sec-13-a",
            "text": "Hindu Marriage Act 1955, Section 13\n13. Divorce.",
            "source_type": "bare_act",
        }],
        query="my wife wants divorce under Hindu Marriage Act Section 13A",
    ) == [{
        "required_source": "Hindu Marriage Act 1955 Section 13A",
        "kind": "national_statute_retrieval_gap",
    }]


def test_generic_platform_kyc_hold_does_not_require_financial_or_gaming_authority():
    query = "Blue Trunks app froze my account showing KYC pending and 80k stuck"
    route = route_matter(query)
    passages = [
        {
            "index": 1,
            "title": "Information Technology Act 2000",
            "anchor": "it-2000/sec-79",
            "source_type": "bare_act",
        },
        {
            "index": 2,
            "title": "Consumer Protection Act 2019",
            "anchor": "consumer-protection-2019/sec-35",
            "source_type": "bare_act",
        },
    ]

    assert missing_required_authorities(
        required_sources=route.required_sources,
        passages=passages,
        query=query,
    ) == []


def test_plan_source_gap_uses_authority_ids_as_primary_key():
    query = "online order arrived broken what to do"
    route = route_matter(query)
    plan = build_matter_plan(query, route)
    assert plan is not None
    controlling = next(
        entry for entry in plan.authority_ledger
        if entry.act == "Consumer Protection Act 2019"
    )
    plan = replace(plan, authority_ledger=[controlling])

    assert missing_plan_authorities(
        plan=plan,
        passages=[{
            "index": 1,
            "title": "Consumer Protection Act 2019",
            "anchor": "consumer-protection-2019/sec-35",
            "source_type": "bare_act",
            "required_source_pack": "consumer_protection_2019",
            "authority_ids": [controlling.authority_id],
        }],
        query=query,
    ) == []

    forged = missing_plan_authorities(
        plan=plan,
        passages=[{
            "index": 1,
            "title": "Unrelated consumer judgment",
            "anchor": "judgment/para-10",
            "source_type": "sc_judgment",
            "required_source_pack": "consumer_protection_2019",
            "authority_ids": [controlling.authority_id],
        }],
        query=query,
    )
    assert forged[0]["authority_id"] == controlling.authority_id

    missing = missing_plan_authorities(
        plan=plan,
        passages=[{
            "index": 1,
            "title": "Consumer Protection Act 2019",
            "anchor": "consumer-protection-2019/sec-34",
            "authority_ids": [],
        }],
        query=query,
    )
    assert missing[0]["authority_id"] == controlling.authority_id
    assert missing[0]["match_mode"] == "legacy_provisional"


def test_plan_authority_uses_server_heading_for_alphanumeric_section_anchor():
    query = "65 year old diabetic undertrial completed half sentence can review committee release under BNSS 479"
    route = route_matter(query)
    plan = build_matter_plan(query, route)
    assert plan is not None
    crpc = next(
        entry for entry in plan.authority_ledger
        if entry.registry_key == "crpc_1973_section_436a"
    )
    plan = replace(plan, authority_ledger=[crpc])

    assert missing_plan_authorities(
        plan=plan,
        passages=[{
            "index": 4,
            "title": "Code of Criminal Procedure 1973",
            "anchor": "crpc-1973/sec-436-a",
            "heading": "Code of Criminal Procedure 1973, Section 436A",
            "source_type": "bare_act",
            "document_id": "crpc-1973",
            "required_source_pack": "crpc_1973",
            "authority_ids": [crpc.authority_id],
        }],
        query=query,
    ) == []


def test_rbi_workflow_fails_closed_when_one_mandatory_clause_is_missing():
    query = "Bank deducted money wrongly and customer care is not helping"
    route = route_matter(query)
    plan = build_matter_plan(query, route)
    assert plan is not None

    def passage(clause: str) -> dict:
        from authority_registry import load_authority_registry

        record = load_authority_registry().by_key(
            f"rbi_integrated_ombudsman_2021_clause_{clause}"
        )
        return {
            "index": int(clause),
            "title": "Reserve Bank - Integrated Ombudsman Scheme, 2021",
            "anchor": f"rbi-integrated-ombudsman-2021/sec-{clause}",
            "source_type": "bare_act",
            "required_source_pack": "rbi_integrated_ombudsman_2021",
            "as_at": record.consolidation_as_at.isoformat() if record and record.consolidation_as_at else None,
        }

    incomplete = [passage(clause) for clause in ("1", "3", "6", "10")]
    missing = missing_plan_authorities(plan=plan, passages=incomplete, query=query)
    assert [item["required_source"] for item in missing] == [
        "Reserve Bank - Integrated Ombudsman Scheme, 2021 Clause 9"
    ]
    assert missing[0]["authority_id"] == "authority_46d05174f2cefb7daa20"

    complete = [*incomplete, passage("9")]
    assert missing_plan_authorities(plan=plan, passages=complete, query=query) == []


def test_plan_source_gap_respects_plan_must_cite_policy_and_state_gap():
    query = "office rejected my caste certificate what appeal"
    plan = build_matter_plan(query, route_matter(query))
    assert plan is not None

    missing = missing_plan_authorities(plan=plan, passages=[], query=query)
    missing_sources = {item["required_source"] for item in missing}

    assert "Constitution Article 341 or 342 after the SC/ST category is confirmed" in missing_sources
    assert "Right to Information Act 2005 Section 6 for the application record and written reasons" in missing_sources
    route_missing = missing_required_authorities(
        required_sources=route_matter(query).required_sources,
        passages=[],
        query=query,
    )
    assert any(
        item["required_source"] == "state caste-certificate issuance and appeal rules"
        and item["kind"] == "state_or_local_authority_gap"
        for item in route_missing
    )
    state_gap = next(
        item for item in route_missing
        if item["required_source"] == "state caste-certificate issuance and appeal rules"
    )
    assert state_gap["kind"] == "state_or_local_authority_gap"

    weak_metadata = missing_plan_authorities(
        plan=plan,
        passages=[{
            "index": 1,
            "title": "state caste-certificate issuance and appeal rules",
            "anchor": "",
            "source_type": "",
            "text": "application record and rejection details",
        }],
        query=query,
    )
    weak_route_missing = missing_required_authorities(
        required_sources=route_matter(query).required_sources,
        passages=[{
            "index": 1,
            "title": "state caste-certificate issuance and appeal rules",
            "anchor": "",
            "source_type": "",
            "text": "application record and rejection details",
        }],
        query=query,
    )
    assert any(
        item["required_source"] == "state caste-certificate issuance and appeal rules"
        for item in weak_route_missing
    )


@pytest.mark.parametrize(
    "query",
    (
        "my SC certificate was rejected in Gujarat, which appeal forum and deadline applies",
        "my ST certificate was refused in Maharashtra, where can I challenge it",
    ),
)
def test_sc_st_certificate_aliases_require_state_rule_for_appeal_queries(query: str):
    route = route_matter(query)
    missing = missing_required_authorities(
        required_sources=route.required_sources,
        passages=[],
        query=query,
    )
    assert any(
        item["required_source"] == "state caste-certificate issuance and appeal rules"
        and item["kind"] == "state_or_local_authority_gap"
        for item in missing
    )


def test_st_certificate_pending_status_stays_intake_until_appeal_is_requested():
    query = "my ST certificate has been pending at the tehsildar for months what can I do"
    route = route_matter(query)
    missing = missing_required_authorities(
        required_sources=route.required_sources,
        passages=[],
        query=query,
    )
    assert not any(
        item["required_source"] == "state caste-certificate issuance and appeal rules"
        for item in missing
    )


def test_plan_source_gap_recomputes_wrong_section_authority_tags():
    query = "ICEGATE says imported goods were misdeclared and may be confiscated"
    plan = build_matter_plan(query, route_matter(query))
    assert plan is not None
    customs = next(entry for entry in plan.authority_ledger if entry.act == "Customs Act 1962")
    plan = replace(plan, authority_ledger=[customs])

    missing = missing_plan_authorities(
        plan=plan,
        passages=[{
            "index": 1,
            "title": "Customs Act 1962",
            "anchor": "customs-1962/sec-75",
            "source_type": "bare_act",
            "authority_ids": [customs.authority_id],
        }],
        query=query,
    )

    assert missing[0]["authority_id"] == customs.authority_id


def test_plan_source_gap_uses_legacy_criminal_authority_for_2023_incident():
    query = "in 2023 police arrested me for bike theft what bail can I get"
    plan = build_matter_plan(query, route_matter(query))
    assert plan is not None
    crpc = next(
        entry for entry in plan.authority_ledger
        if entry.act == "Code of Criminal Procedure 1973" and entry.must_cite
    )
    plan = replace(plan, authority_ledger=[crpc])

    valid_passage = {
        "index": 1,
        "title": "Code of Criminal Procedure 1973",
        "anchor": "crpc-1973/sec-437",
        "source_type": "bare_act",
        "required_source_pack": "crpc_1973",
        "authority_ids": [crpc.authority_id],
    }
    assert missing_plan_authorities(plan=plan, passages=[valid_passage], query=query) == []

    wrong_regime = missing_plan_authorities(
        plan=plan,
        passages=[{
            "index": 1,
            "title": "Bharatiya Nagarik Suraksha Sanhita 2023",
            "anchor": "bnss-2023/sec-480",
            "source_type": "bare_act",
            "authority_ids": [crpc.authority_id],
        }],
        query=query,
    )
    assert wrong_regime[0]["authority_id"] == crpc.authority_id


def test_plan_source_gap_requires_mixed_regime_authority_when_incident_date_is_unknown():
    query = "police refused to register FIR for theft of my bike where do I go next"
    plan = build_matter_plan(query, route_matter(query))
    assert plan is not None
    regime_entries = [
        entry for entry in plan.authority_ledger if entry.must_cite
    ]
    assert {entry.act for entry in regime_entries} == {
        "Bharatiya Nagarik Suraksha Sanhita 2023",
        "Code of Criminal Procedure 1973",
        "Bharatiya Nyaya Sanhita 2023",
        "Indian Penal Code 1860",
    }
    missing = missing_plan_authorities(plan=plan, passages=[], query=query)
    # The plan may contain duplicate provisional rows for the same regime
    # pack. The serving gate reports one missing obligation per source pack.
    assert {
        (item["required_source"], item["source_pack_id"])
        for item in missing
    } == {
        (entry.source, entry.source_pack_id)
        for entry in regime_entries
    }

    assert missing_plan_authorities(
        plan=plan,
        passages=[
                {
                    "index": 1,
                    "title": "Bharatiya Nagarik Suraksha Sanhita 2023",
                    "anchor": "bnss-2023/sec-173-a",
                    "required_source_pack": "bnss_2023_vehicle_theft_fir",
                    "source_type": "bare_act",
                    "authority_ids": ["authority_34af1906c7f20fae0947"],
                    "as_at": "2024-07-01",
                    "text": "Bharatiya Nagarik Suraksha Sanhita 2023, Section 173\n173. Information in cognizable cases.",
                },
                {
                    "index": 2,
                    "title": "Bharatiya Nagarik Suraksha Sanhita 2023",
                    "anchor": "bnss-2023/sec-173-c",
                        "required_source_pack": "bnss_2023_vehicle_theft_fir",
                        "source_type": "bare_act",
                        "authority_ids": ["authority_85fac6e1af26c07fb512"],
                        "as_at": "2024-07-01",
                        "text": "Bharatiya Nagarik Suraksha Sanhita 2023, Section 173(4)\n(4) Any person aggrieved by a refusal.",
                },
                {
                    "index": 3,
                    "title": "Bharatiya Nagarik Suraksha Sanhita 2023",
                    "anchor": "bnss-2023/sec-175",
                    "required_source_pack": "bnss_2023_vehicle_theft_fir",
                    "source_type": "bare_act",
                    "authority_ids": ["authority_5b58f83601c4ab714da1"],
                    "as_at": "2024-07-01",
                    "text": "Bharatiya Nagarik Suraksha Sanhita 2023, Section 175\n175. Police officer power to investigate cognizable case.",
                },
                {
                    "index": 4,
                    "title": "Code of Criminal Procedure 1973",
                    "anchor": "crpc-1973/sec-154",
                    "required_source_pack": "crpc_1973_vehicle_theft_fir",
                        "source_type": "bare_act",
                        "authority_ids": ["authority_6358e656222ff6dcdae9"],
                        "text": "Code of Criminal Procedure 1973, Section 154\n154. Information in cognizable cases.",
                    },
                    {
                        "index": 5,
                        "title": "Bharatiya Nyaya Sanhita 2023",
                        "anchor": "bns-2023/sec-303",
                        "required_source_pack": "bns_2023_vehicle_theft",
                        "source_type": "bare_act",
                    },
                    {
                        "index": 6,
                        "title": "Indian Penal Code 1860",
                        "anchor": "ipc-1860/sec-378",
                        "required_source_pack": "ipc_1860_vehicle_theft",
                        "source_type": "bare_act",
                    },
        ],
        query=query,
    ) == []


def test_plan_source_gap_requires_every_explicit_composite_criminal_section():
    query = (
        "in 2025 girl I was dating filed rape case after we broke up saying I promised "
        "marriage we had relationship for 2 years"
    )
    plan = build_matter_plan(query, route_matter(query))
    assert plan is not None
    bns_entries = [
        entry for entry in plan.authority_ledger
        if entry.act == "Bharatiya Nyaya Sanhita 2023"
    ]
    assert [entry.section for entry in bns_entries] == ["Section 63", "Section 69"]
    plan = replace(plan, authority_ledger=bns_entries)

    missing = missing_plan_authorities(
        plan=plan,
        passages=[{
            "index": 1,
                "title": "Bharatiya Nyaya Sanhita 2023",
                "anchor": "bns-2023/sec-63",
                "required_source_pack": bns_entries[0].source_pack_id,
                "source_type": "bare_act",
        }],
        query=query,
    )

    assert [item["authority_id"] for item in missing] == [bns_entries[1].authority_id]


def test_plan_source_gap_does_not_turn_company_gst_records_into_missing_law():
    query = "my company was struck off and GST refund is blocked how do I restore it"
    plan = build_matter_plan(query, route_matter(query))
    assert plan is not None

    missing_sources = {
        item["required_source"]
        for item in missing_plan_authorities(plan=plan, passages=[], query=query)
    }

    assert "GST refund/bank operation records only after company status is addressed" not in missing_sources


def test_plan_source_gap_enforces_activated_conditional_authority():
    query = "sand mine in scheduled area on forest land without gram sabha recommendation"
    plan = build_matter_plan(query, route_matter(query))
    assert plan is not None

    missing = missing_plan_authorities(plan=plan, passages=[], query=query)
    missing_sources = {item["required_source"] for item in missing}

    assert "Forest Conservation Act 1980 where forest land or forest clearance is involved" in missing_sources
    assert not any("RFCTLARR" in source for source in missing_sources)


def test_plan_source_gap_does_not_report_factual_intake_as_missing_law():
    query = "my son is in jail and charge sheet not filed after 90 days what can we do"
    plan = build_matter_plan(query, route_matter(query))
    assert plan is not None

    missing = missing_plan_authorities(plan=plan, passages=[], query=query)
    missing_sources = {item["required_source"] for item in missing}

    assert (
        "charge-sheet filing status, extension application/order, and first remand date"
        not in missing_sources
    )


def test_provisional_reviewed_source_pack_satisfies_plan_without_registry_mapping():
    query = "my customer gave me a cheque and it bounced, what is the deadline to send notice"
    plan = build_matter_plan(query, route_matter(query))
    assert plan is not None

    passages = [
        {
            "index": 1,
            "title": "Negotiable Instruments Act 1881",
            "anchor": "negotiable-instruments-1881/sec-138",
            "source_type": "bare_act",
            "required_source_pack": "ni_act_1881",
            # The document is verified, but this legacy reviewed pack has not
            # yet been projected into document_authorities.
            "authority_ids": [],
        },
        {
            "index": 2,
            "title": "Negotiable Instruments Act 1881",
            "anchor": "negotiable-instruments-1881/sec-142",
            "source_type": "bare_act",
            "required_source_pack": "ni_act_1881",
            "authority_ids": [],
        },
    ]

    missing = missing_plan_authorities(plan=plan, passages=passages, query=query)
    assert not any(
        item["required_source"].startswith("Negotiable Instruments Act 1881")
        for item in missing
    )


def test_provisional_source_pack_still_requires_exact_pack_and_anchor():
    query = "my customer gave me a cheque and it bounced, what is the deadline to send notice"
    plan = build_matter_plan(query, route_matter(query))
    assert plan is not None

    wrong_pack = [{
        "title": "Negotiable Instruments Act 1881",
        "anchor": "negotiable-instruments-1881/sec-138",
        "required_source_pack": "unrelated_pack",
        "authority_ids": [],
    }]
    wrong_anchor = [{
        "title": "Negotiable Instruments Act 1881",
        "anchor": "negotiable-instruments-1881/sec-1",
        "required_source_pack": "ni_act_1881",
        "authority_ids": [],
    }]
    official_anchor = [
        {
            "title": "Negotiable Instruments Act 1881",
            "anchor": "negotiable-instruments-1881/sec-138-official",
            "source_type": "bare_act",
            "required_source_pack": "ni_act_1881",
            "authority_ids": [],
        },
        {
            "title": "Negotiable Instruments Act 1881",
            "anchor": "negotiable-instruments-1881/sec-142-official",
            "source_type": "bare_act",
            "required_source_pack": "ni_act_1881",
            "authority_ids": [],
        },
    ]

    assert missing_plan_authorities(plan=plan, passages=wrong_pack, query=query)
    assert missing_plan_authorities(plan=plan, passages=wrong_anchor, query=query)
    assert not any(
        item["required_source"].startswith("Negotiable Instruments Act 1881")
        for item in missing_plan_authorities(
            plan=plan,
            passages=official_anchor,
            query=query,
        )
    )


def test_provisional_source_pack_rejects_wrong_source_type_and_document():
    query = "my customer gave me a cheque and it bounced, what is the deadline to send notice"
    plan = build_matter_plan(query, route_matter(query))
    assert plan is not None
    entry = next(
        item for item in plan.authority_ledger
        if item.source_pack_id == "ni_act_1881"
    )

    wrong_type = {
        "title": "Negotiable Instruments Act 1881",
        "anchor": "negotiable-instruments-1881/sec-138",
        "source_type": "sc_judgment",
        "required_source_pack": "ni_act_1881",
        "authority_ids": [],
    }
    wrong_document = {
        "title": "Negotiable Instruments Act 1881",
        "anchor": "other-act/sec-138",
        "source_type": "bare_act",
        "required_source_pack": "ni_act_1881",
        "authority_ids": [],
    }

    assert not _passage_satisfies_plan_entry(plan, entry, wrong_type)
    assert not _passage_satisfies_plan_entry(plan, entry, wrong_document)

    spoofed_title = {
        "title": "Negotiable Instruments Act 1881 fake",
        "anchor": "negotiable-instruments-1881/sec-138",
        "source_type": "bare_act",
        "required_source_pack": "ni_act_1881",
        "authority_ids": [],
    }
    assert not _passage_satisfies_plan_entry(plan, entry, spoofed_title)


def test_provisional_source_pack_fails_closed_when_identity_metadata_is_missing():
    query = "my customer gave me a cheque and it bounced, what is the deadline to send notice"
    plan = build_matter_plan(query, route_matter(query))
    assert plan is not None
    entry = next(
        item for item in plan.authority_ledger
        if item.source_pack_id == "ni_act_1881"
    )

    missing_type = {
        "title": "Negotiable Instruments Act 1881",
        "anchor": "negotiable-instruments-1881/sec-138",
        "required_source_pack": "ni_act_1881",
        "authority_ids": [],
    }
    assert not _passage_satisfies_plan_entry(plan, entry, missing_type)

    no_document_identity = replace(
        plan,
        retrieval_sources=[
            replace(
                source,
                doc_ids=[],
            )
            if source.source_pack_id == "ni_act_1881"
            else source
            for source in plan.retrieval_sources
        ],
    )
    complete_passage = {
        "title": "Negotiable Instruments Act 1881",
        "anchor": "negotiable-instruments-1881/sec-138",
        "source_type": "bare_act",
        "required_source_pack": "ni_act_1881",
        "authority_ids": [],
    }
    assert not _passage_satisfies_plan_entry(no_document_identity, entry, complete_passage)


def test_registry_owned_obligation_does_not_use_legacy_pack_fallback():
    from types import SimpleNamespace

    plan = SimpleNamespace(retrieval_sources=[SimpleNamespace(
        source_pack_id="registry_pack",
        title_patterns=("Verified Act",),
        source_types=("bare_act",),
        doc_ids=("verified-act",),
    )])
    entry = SimpleNamespace(
        source_pack_id="registry_pack",
        registry_key="registry_authority",
        note="registry_workflow_authority",
        required_anchor_patterns=["/sec-1"],
        authority_id="authority_00000000000000000000",
    )
    passage = {
        "title": "Verified Act",
        "anchor": "verified-act/sec-1",
        "source_type": "bare_act",
        "required_source_pack": "registry_pack",
        "authority_ids": [],
    }

    assert not _passage_satisfies_plan_entry(plan, entry, passage)


def test_registry_owned_obligation_accepts_verified_official_anchor():
    from types import SimpleNamespace

    plan = SimpleNamespace(retrieval_sources=[SimpleNamespace(
        source_pack_id="registry_pack",
        title_patterns=("Verified Act",),
        source_types=("bare_act",),
        doc_ids=("verified-act",),
    )])
    entry = SimpleNamespace(
        source_pack_id="registry_pack",
        registry_key="registry_authority",
        note="registry_workflow_authority",
        required_anchor_patterns=["/sec-1"],
        authority_id="authority_00000000000000000000",
    )
    passage = {
        "title": "Verified Act",
        "anchor": "verified-act/sec-1-official",
        "source_type": "bare_act",
        "required_source_pack": "registry_pack",
        "authority_ids": ["authority_00000000000000000000"],
    }

    assert _passage_satisfies_plan_entry(plan, entry, passage)


@pytest.mark.parametrize(
    "field_mutation",
    [
        {"required_source_pack": "wrong_pack"},
        {"source_type": "sc_judgment"},
        {"anchor": "other-act/sec-1"},
    ],
)
def test_registry_owned_obligation_rejects_wrong_provenance(
    field_mutation: dict[str, str],
):
    from types import SimpleNamespace

    plan = SimpleNamespace(retrieval_sources=[SimpleNamespace(
        source_pack_id="registry_pack",
        title_patterns=("Verified Act",),
        source_types=("bare_act",),
        doc_ids=("verified-act",),
    )])
    entry = SimpleNamespace(
        source_pack_id="registry_pack",
        registry_key="registry_authority",
        note="registry_workflow_authority",
        required_anchor_patterns=["/sec-1"],
        authority_id="authority_00000000000000000000",
    )
    passage = {
        "title": "Verified Act",
        "anchor": "verified-act/sec-1-official",
        "source_type": "bare_act",
        "required_source_pack": "registry_pack",
        "authority_ids": ["authority_00000000000000000000"],
    }
    passage.update(field_mutation)

    assert not _passage_satisfies_plan_entry(plan, entry, passage)


def test_structured_plan_anchor_matching_rejects_numeric_suffix_spoofs():
    for kind in ("sec", "article", "clause", "order", "rule"):
        pattern = f"/{kind}-21"
        assert _plan_anchor_matches(f"doc{pattern}", pattern)
        assert _plan_anchor_matches(f"doc{pattern}@2024-01-01", pattern)
        assert not _plan_anchor_matches(f"doc{pattern}0", pattern)


def test_official_anchor_suffix_is_allowed_only_once_across_plan_consumers():
    assert _plan_anchor_matches("doc/sec-21-official", "/sec-21")
    assert _plan_anchor_matches("doc/sec-21-official@2024-01-01", "/sec-21")
    assert _plan_anchor_matches("doc/sec-21-official", "/sec-21-official")
    assert not _plan_anchor_matches("doc/sec-21-official-official", "/sec-21")
    assert not _plan_anchor_matches("doc/sec-21-official-official", "/sec-21-official")
    assert not _plan_anchor_matches("doc/sec-210-official", "/sec-21")

    assert _source_pack_anchor_matches("doc/sec-21-official", "/sec-21")
    assert _source_pack_anchor_matches("doc/sec-21-official", "/sec-21-official")
    assert _source_pack_anchor_matches("doc/sec-21-official", "/sec-21@")
    assert _source_pack_anchor_matches("doc/sec-21-official@2024-01-01", "/sec-21@")
    assert _source_pack_anchor_matches("doc/sec-21-a-official", "/sec-21")
    assert not _source_pack_anchor_matches("doc/sec-21-official-official", "/sec-21")
    assert not _source_pack_anchor_matches("doc/sec-21-official-official", "/sec-21-official")
    assert not _source_pack_anchor_matches("doc/sec-21-22-official", "/sec-21")

    assert _section_anchor_matches(
        "constitution-india/sec-21-official",
        "21",
        passage_text="Constitution of India, Article 21\n21. Protection of life and personal liberty.",
    )
    assert not _section_anchor_matches(
        "constitution-india/sec-21-official-official",
        "21",
        passage_text="Constitution of India, Article 21\n21. Protection of life and personal liberty.",
    )
    assert not _section_anchor_matches(
        "constitution-india/sec-210-official",
        "21",
        passage_text="Constitution of India, Article 21\n21. Protection of life and personal liberty.",
    )


def test_reviewed_source_title_accepts_known_document_edition_suffix():
    assert _source_pack_title_matches(
        "Hindu Succession Act 1956 (with 2005 amendment)",
        ("Hindu Succession Act 1956",),
        allow_known_document_suffix=True,
    )
    assert not _source_pack_title_matches(
        "Hindu Succession Act 1956 (with 2005 amendment)",
        ("Hindu Succession Act 1956",),
        allow_known_document_suffix=False,
    )


def test_constitutional_official_anchors_pass_final_source_gap_gate():
    query = "police took my brother yesterday no arrest memo given dk basu kya hai"
    route = route_matter(query)
    source = "Constitution Articles 21 and 22 arrest and custody safeguards"
    passages = [
        {
            "title": "Constitution of India",
            "anchor": "constitution-india/sec-21-official",
            "source_type": "bare_act",
            "required_source_pack": "constitution_article_21",
            "text": "Constitution of India, Article 21\n21. Protection of life and personal liberty.",
        },
        {
            "title": "Constitution of India",
            "anchor": "constitution-india/sec-22-official",
            "source_type": "bare_act",
            "required_source_pack": "constitution_article_22",
            "text": "Constitution of India, Article 22\n22. Protection against arrest and detention.",
        },
    ]

    assert build_source_gap_event(
        query=query,
        route_category=route.category,
        required_sources=[source],
        passages=passages,
        plan=None,
    ) is None


def test_split_section_anchor_requires_matching_passage_heading():
    assert _plan_anchor_matches(
        "negotiable-instruments-1881/sec-142-a",
        "/sec-142",
        passage_text="Negotiable Instruments Act 1881, Section 142\n142. Cognizance of offences.",
    )
    assert not _plan_anchor_matches(
        "negotiable-instruments-1881/sec-142-a",
        "/sec-142",
        passage_text="Negotiable Instruments Act 1881, Section 142A\n142A. Validation for transfer.",
    )
    assert not _plan_anchor_matches(
        "negotiable-instruments-1881/sec-142-a",
        "/sec-142",
    )


def test_canonical_section_gap_accepts_split_numeric_section_only_with_heading():
    required = ["Negotiable Instruments Act 1881 Section 142 complaint limitation"]
    matching = [{
        "title": "Negotiable Instruments Act 1881",
        "anchor": "negotiable-instruments-1881/sec-142-a",
        "source_type": "bare_act",
        "text": "Negotiable Instruments Act 1881, Section 142\n142. Cognizance of offences.",
    }]
    neighboring = [{
        **matching[0],
        "text": "Negotiable Instruments Act 1881, Section 142A\n142A. Validation for transfer.",
    }]

    assert missing_required_authorities(
        required_sources=required,
        passages=matching,
        query="cheque dishonour complaint deadline",
    ) == []
    assert missing_required_authorities(
        required_sources=required,
        passages=neighboring,
        query="cheque dishonour complaint deadline",
    )


def test_section_gap_does_not_fuzzy_fallback_to_wrong_section():
    required = ["Code on Wages 2019 Section 15 wage payment rule"]
    wrong_section = [{
        "title": "Code on Wages 2019",
        "anchor": "code-on-wages-2019/sec-15-a",
        "source_type": "bare_act",
        "text": "Code on Wages 2019, Section 15A\n15A. Different provision.",
    }]
    assert missing_required_authorities(
        required_sources=required,
        passages=wrong_section,
        query="employer has not paid my wages",
    )

    income_tax_wrong_section = [{
        "title": "Income Tax Act 1961",
        "anchor": "income-tax-1961/sec-143-a",
        "source_type": "bare_act",
        "text": "Income Tax Act 1961, Section 143A\n143A. Different provision.",
    }]
    assert missing_required_authorities(
        required_sources=["Income-tax Act 1961 Section 143 assessment"],
        passages=income_tax_wrong_section,
        query="income tax assessment order",
    )


def test_parenthesized_bnss_subsection_cannot_match_neighboring_split_chunk():
    required = [
        "Bharatiya Nagarik Suraksha Sanhita 2023 Section 173(4) "
        "written-post police refusal route"
    ]
    matching = [{
        "title": "Bharatiya Nagarik Suraksha Sanhita 2023",
        "anchor": "bnss-2023/sec-173-c@2024-07-01",
        "source_type": "bare_act",
        "text": (
            "Bharatiya Nagarik Suraksha Sanhita 2023, Section 173(4)\n"
            "If the officer in charge refuses to record the information, "
            "the substance may be sent in writing by post to the "
            "Superintendent of Police."
        ),
    }]
    wrong_neighbor = [{
        **matching[0],
        "anchor": "bnss-2023/sec-173-a@2024-07-01",
    }]
    wrong_heading = [{
        **matching[0],
        "text": (
            "Bharatiya Nagarik Suraksha Sanhita 2023, Section 173(1)\n"
            "Information relating to a cognizable offence may be given."
        ),
    }]
    wrong_a_subsection = [{
        **matching[0],
        "anchor": "bnss-2023/sec-173-a@2024-07-01",
        "text": (
            "Bharatiya Nagarik Suraksha Sanhita 2023, Section 173(4)\n"
            "The substance may be sent in writing by post to the Superintendent of Police."
        ),
    }]

    assert missing_required_authorities(
        required_sources=required,
        passages=matching,
        query="police refused to file my theft FIR",
    ) == []
    assert missing_required_authorities(
        required_sources=required,
        passages=wrong_neighbor,
        query="police refused to file my theft FIR",
    )
    assert missing_required_authorities(
        required_sources=required,
        passages=wrong_heading,
        query="police refused to file my theft FIR",
    )
    assert not _plan_anchor_matches(
        wrong_a_subsection[0]["anchor"],
        "/sec-173-a",
        passage_text=wrong_a_subsection[0]["text"],
    )


def test_explicit_split_anchor_requires_heading_and_does_not_assume_142a():
    assert not _plan_anchor_matches(
        "negotiable-instruments-1881/sec-142-a",
        "/sec-142-a",
    )
    assert _plan_anchor_matches(
        "negotiable-instruments-1881/sec-142-a",
        "/sec-142-a",
        passage_text="Negotiable Instruments Act 1881, Section 142A\n142A. Validation for transfer.",
    )


def test_canonical_explicit_alphanumeric_section_requires_heading():
    required = ["Negotiable Instruments Act 1881 Section 142A validation"]
    metadata_only = [{
        "title": "Negotiable Instruments Act 1881",
        "anchor": "negotiable-instruments-1881/sec-142-a",
        "source_type": "bare_act",
    }]
    matching = [{
        **metadata_only[0],
        "text": "Negotiable Instruments Act 1881, Section 142A\n142A. Validation for transfer.",
    }]

    assert missing_required_authorities(
        required_sources=required,
        passages=metadata_only,
        query="cheque dishonour validation",
    )
    assert missing_required_authorities(
        required_sources=required,
        passages=matching,
        query="cheque dishonour validation",
    ) == []


def test_statute_specific_branch_cannot_bypass_explicit_section_heading():
    required = ["Consumer Protection Act 2019 Section 35 complaint"]
    wrong_neighbor = [{
        "title": "Consumer Protection Act 2019",
        "anchor": "consumer-protection-2019/sec-35-a",
        "source_type": "bare_act",
        "text": "Consumer Protection Act 2019, Section 35A\n35A. Different provision.",
    }]
    matching_split = [{
        **wrong_neighbor[0],
        "text": "Consumer Protection Act 2019, Section 35\n35. Jurisdiction.",
    }]

    assert missing_required_authorities(
        required_sources=required,
        passages=wrong_neighbor,
        query="consumer complaint",
    )
    assert missing_required_authorities(
        required_sources=required,
        passages=matching_split,
        query="consumer complaint",
    ) == []


def test_customs_source_gap_matching_is_query_aware():
    required = "Customs Act 1962 for import/export, ICEGATE, duty, valuation, SVB, drawback, or classification issues"

    icegate_query = "icegate showing bill of entry on hold misdeclaration alleged chinese led lights"
    assert missing_required_authorities(
        required_sources=[required],
        passages=[{"index": 1, "title": "Customs Act 1962", "anchor": "customs-1962/sec-75", "source_type": "bare_act"}],
        query=icegate_query,
    )
    assert missing_required_authorities(
        required_sources=[required],
        passages=[{"index": 1, "title": "Customs Act 1962", "anchor": "customs-1962/sec-124", "source_type": "bare_act"}],
        query=icegate_query,
    ) == []

    drawback_query = "drawback claim rejected by customs shipping bill mismatched export incentive"
    assert missing_required_authorities(
        required_sources=[required],
        passages=[{"index": 1, "title": "Customs Act 1962", "anchor": "customs-1962/sec-124", "source_type": "bare_act"}],
        query=drawback_query,
    )
    assert missing_required_authorities(
        required_sources=[required],
        passages=[{"index": 1, "title": "Customs Act 1962", "anchor": "customs-1962/sec-75", "source_type": "bare_act"}],
        query=drawback_query,
    ) == []

    svb_query = "customs reclassified my import wire harness higher duty svb opened mumbai"
    assert missing_required_authorities(
        required_sources=[required],
        passages=[{"index": 1, "title": "Customs Act 1962", "anchor": "customs-1962/sec-75", "source_type": "bare_act"}],
        query=svb_query,
    )
    assert missing_required_authorities(
        required_sources=[required],
        passages=[{"index": 1, "title": "Customs Act 1962", "anchor": "customs-1962/sec-14", "source_type": "bare_act"}],
        query=svb_query,
    ) == []

    plain_classification_query = "customs reclassified imported scanner under wrong tariff heading higher duty"
    assert missing_required_authorities(
        required_sources=[required],
        passages=[{"index": 1, "title": "Customs Act 1962", "anchor": "customs-1962/sec-14", "source_type": "bare_act"}],
        query=plain_classification_query,
    )
    assert missing_required_authorities(
        required_sources=[required],
        passages=[{"index": 1, "title": "Customs Act 1962", "anchor": "customs-1962/sec-17", "source_type": "bare_act"}],
        query=plain_classification_query,
    ) == []

    no_svb_query = "customs reclassified imported wire harness higher duty no svb opened"
    assert missing_required_authorities(
        required_sources=[required],
        passages=[{"index": 1, "title": "Customs Act 1962", "anchor": "customs-1962/sec-14", "source_type": "bare_act"}],
        query=no_svb_query,
    )

    svb_not_related_query = "svb opened but we are not related party declared value rejected by customs"
    assert missing_required_authorities(
        required_sources=[required],
        passages=[{"index": 1, "title": "Customs Act 1962", "anchor": "customs-1962/sec-14", "source_type": "bare_act"}],
        query=svb_not_related_query,
    ) == []


def test_manual_scavenging_death_dual_regime_sources_satisfy_gap_policy():
    query = "village man dies cleaning septic tank no safety equipment company not agreeing compensation"
    route = route_matter(query)

    event = build_source_gap_event(
        query=query,
        route_category=route.category,
        required_sources=route.required_sources,
        passages=[
            {
                "index": 1,
                "title": "Prohibition of Employment as Manual Scavengers and their Rehabilitation Act 2013",
                "anchor": "manual-scavenging-2013/sec-7",
                "source_type": "bare_act",
            },
            {
                "index": 2,
                "title": "Employees' Compensation Act 1923",
                "anchor": "employees-compensation-1923/sec-3",
                "source_type": "bare_act",
            },
            {
                "index": 3,
                "title": "Bharatiya Nyaya Sanhita 2023",
                "anchor": "bns-2023/sec-106",
                "source_type": "bare_act",
            },
            {
                "index": 4,
                "title": "Bharatiya Nagarik Suraksha Sanhita 2023",
                "anchor": "bnss-2023/sec-173",
                "source_type": "bare_act",
            },
            {
                "index": 5,
                "title": "Code of Criminal Procedure 1973",
                "anchor": "crpc-1973/sec-154",
                "source_type": "bare_act",
            },
        ],
    )

    assert event is None


def test_source_gap_accepts_broad_gift_deed_and_free_consent_authorities():
    passages = [
        {
            "index": 1,
            "title": "Transfer of Property Act 1882",
            "anchor": "transfer-of-property-1882/sec-122",
            "source_type": "bare_act",
        },
        {
            "index": 2,
            "title": "Registration Act 1908",
            "anchor": "registration-1908/sec-49",
            "source_type": "bare_act",
        },
        {
            "index": 3,
            "title": "Specific Relief Act 1963",
            "anchor": "specific-relief-1963/sec-31",
            "source_type": "bare_act",
        },
        {
            "index": 4,
            "title": "Indian Contract Act 1872",
            "anchor": "indian-contract-1872/sec-19-a",
            "source_type": "bare_act",
        },
        {
            "index": 5,
            "title": "Bharatiya Nyaya Sanhita 2023",
            "anchor": "bns-2023/sec-336",
            "source_type": "bare_act",
        },
        {
            "index": 6,
            "title": "Bharatiya Nagarik Suraksha Sanhita 2023",
            "anchor": "bnss-2023/sec-173-a",
            "source_type": "bare_act",
        },
        {
            "index": 7,
            "title": "Code of Criminal Procedure 1973",
            "anchor": "crpc-1973/sec-200",
            "source_type": "bare_act",
        },
    ]

    missing = missing_required_authorities(
        required_sources=[
            "Transfer of Property Act 1882 where gift or property-transfer cancellation is involved",
            "Indian Contract Act 1872 where consent, coercion, undue influence, or authority is disputed",
            "Registration Act / civil court procedure where document validity is disputed",
            "Specific Relief Act 1963 where cancellation/declaration/injunction is needed",
            "BNS 2023 / IPC 1860 cheating, forgery, or false-document provisions based on incident date",
            "BNSS 2023 / CrPC 1973 complaint and investigation procedure based on incident date",
        ],
        passages=passages,
        query="mother thumb impression blank paper produced as gift deed",
    )

    assert missing == []


def test_source_gap_skips_untriggered_conditional_authorities():
    missing = missing_required_authorities(
        required_sources=[
            "Maternity Benefit Act / EPF Act only where maternity or PF/EPF facts are involved",
            "court rules and practice directions for the relevant court",
            "BNSS 2023 / CrPC 1973 only if the case-status issue is in a criminal case",
            "Constitution of India Article 32 for Supreme Court fundamental-right enforcement where applicable",
            "Legal Services Authorities Act 1987 where help is needed",
            "BOCW Act 1996 / Factories Act 1948 where applicable",
        ],
        passages=[],
        query="civil suit court fee 25 lakh recovery fixed or ad valorem",
    )

    assert missing == []


def test_source_gap_enforces_triggered_conditional_labour_and_legal_aid_authorities():
    missing = missing_required_authorities(
        required_sources=[
            "Code on Wages only if salary, full-and-final, leave encashment, or wage dues are withheld",
            "Legal Services Authorities Act 1987 where help is needed",
        ],
        passages=[],
        query="salary deducted and I cannot afford lawyer need DLSA legal aid",
    )

    assert missing == [
        {
            "required_source": "Code on Wages only if salary, full-and-final, leave encashment, or wage dues are withheld",
            "kind": "national_statute_retrieval_gap",
        },
        {
            "required_source": "Legal Services Authorities Act 1987 where help is needed",
            "kind": "national_statute_retrieval_gap",
        },
    ]


def test_national_ombudsman_scheme_is_not_mislabeled_as_state_or_local():
    missing = missing_required_authorities(
        required_sources=["Reserve Bank Integrated Ombudsman Scheme 2021"],
        passages=[],
        query="bank deducted money wrongly and customer care is not helping",
    )

    assert missing == [{
        "required_source": "Reserve Bank Integrated Ombudsman Scheme 2021",
        "kind": "national_statute_retrieval_gap",
    }]


def test_source_gap_does_not_trigger_family_personal_law_for_spouse_violence_only():
    missing = missing_required_authorities(
        required_sources=[
            "family law statute by religion",
            "BNSS/CrPC maintenance provisions where applicable",
        ],
        passages=[],
        query="my husband is slapping me and his parents threw me out",
    )

    assert missing == []


def test_source_gap_triggers_family_and_maintenance_only_on_matching_relief():
    family_missing = missing_required_authorities(
        required_sources=["family law statute by religion"],
        passages=[],
        query="my husband lied before marriage about job can I annul marriage",
    )
    maintenance_missing = missing_required_authorities(
        required_sources=["BNSS/CrPC maintenance provisions where applicable"],
        passages=[],
        query="wife and child maintenance case husband not paying monthly support",
    )

    assert family_missing == [
        {
            "required_source": "family law statute by religion",
            "kind": "national_statute_retrieval_gap",
        }
    ]
    assert maintenance_missing == [
        {
            "required_source": "BNSS/CrPC maintenance provisions where applicable",
            "kind": "national_criminal_source_gap",
        }
    ]


def test_source_gap_treats_conditional_criminal_regime_as_authority():
    missing = missing_required_authorities(
        required_sources=[
            "BNSS 2023 / CrPC 1973 bail provisions based on incident date",
            "BNS 2023 / IPC 1860 offence provisions where relevant",
        ],
        passages=[],
        query="brother arrested six months no chargesheet can bail be filed",
    )

    assert missing == [
        {
            "required_source": "BNSS 2023 / CrPC 1973 bail provisions based on incident date",
            "kind": "national_criminal_source_gap",
        },
    ]


def test_source_gap_requires_matching_criminal_procedure_section_family():
    wrong_section = missing_required_authorities(
        required_sources=["BNSS 2023 / CrPC 1973 bail provisions based on incident date"],
        passages=[
            {
                "index": 1,
                "title": "Bharatiya Nagarik Suraksha Sanhita 2023",
                "anchor": "bnss-2023/sec-173",
                "source_type": "bare_act",
            }
        ],
        query="brother arrested six months no chargesheet can bail be filed",
    )
    covered_by_both_regimes = missing_required_authorities(
        required_sources=["BNSS 2023 / CrPC 1973 bail provisions based on incident date"],
        passages=[
            {
                "index": 1,
                "title": "Bharatiya Nagarik Suraksha Sanhita 2023",
                "anchor": "bnss-2023/sec-480",
                "source_type": "bare_act",
            },
            {
                "index": 2,
                "title": "Code of Criminal Procedure 1973",
                "anchor": "crpc-1973/sec-439",
                "source_type": "bare_act",
            },
        ],
        query="brother arrested six months no chargesheet can bail be filed",
    )

    assert wrong_section[0]["required_source"] == "BNSS 2023 / CrPC 1973 bail provisions based on incident date"
    assert covered_by_both_regimes == []


def test_source_gap_accepts_coherent_bns_bnss_or_ipc_crpc_pair():
    required = ["BNS/BNSS or IPC/CrPC based on incident date"]
    current_sources = [
        {
            "index": 1,
            "title": "Bharatiya Nyaya Sanhita 2023",
            "anchor": "bns-2023/sec-318",
            "source_type": "bare_act",
        },
        {
            "index": 2,
            "title": "Bharatiya Nagarik Suraksha Sanhita 2023",
            "anchor": "bnss-2023/sec-173",
            "source_type": "bare_act",
        },
    ]
    old_sources = [
        {
            "index": 1,
            "title": "Indian Penal Code 1860",
            "anchor": "ipc-1860/sec-420",
            "source_type": "bare_act",
        },
        {
            "index": 2,
            "title": "Code of Criminal Procedure 1973",
            "anchor": "crpc-1973/sec-154",
            "source_type": "bare_act",
        },
    ]

    assert missing_required_authorities(
        required_sources=required,
        passages=current_sources,
        query="got 8 lakh phonepe fraud police not filing fir",
    ) == []
    assert missing_required_authorities(
        required_sources=required,
        passages=old_sources,
        query="incident in 2023 phonepe fraud police not filing fir",
    ) == []
    assert missing_required_authorities(
        required_sources=required,
        passages=current_sources,
        query="incident in 2023 phonepe fraud police not filing fir",
    ) == [
        {
            "required_source": "BNS/BNSS or IPC/CrPC based on incident date",
            "kind": "national_criminal_source_gap",
        }
    ]


def test_source_gap_rejects_partial_bns_bnss_or_ipc_crpc_pair():
    missing = missing_required_authorities(
        required_sources=["BNS/BNSS or IPC/CrPC based on incident date"],
        passages=[
            {
                "index": 1,
                "title": "Bharatiya Nyaya Sanhita 2023",
                "anchor": "bns-2023/sec-318",
                "source_type": "bare_act",
            }
        ],
        query="got 8 lakh phonepe fraud police not filing fir",
    )

    assert missing[0]["required_source"] == "BNS/BNSS or IPC/CrPC based on incident date"


def test_source_gap_does_not_treat_bnss_as_bns_or_new_law_as_old_regime():
    required = ["BNS/BNSS or IPC/CrPC based on incident date"]

    only_bnss = missing_required_authorities(
        required_sources=required,
        passages=[
            {
                "index": 1,
                "title": "Bharatiya Nagarik Suraksha Sanhita 2023",
                "anchor": "bnss-2023/sec-173",
                "source_type": "bare_act",
            }
        ],
        query="phonepe fraud police not filing fir",
    )
    old_fact_with_new_sources = missing_required_authorities(
        required_sources=required,
        passages=[
            {
                "index": 1,
                "title": "Bharatiya Nyaya Sanhita 2023",
                "anchor": "bns-2023/sec-318",
                "source_type": "bare_act",
            },
            {
                "index": 2,
                "title": "Bharatiya Nagarik Suraksha Sanhita 2023",
                "anchor": "bnss-2023/sec-173",
                "source_type": "bare_act",
            },
        ],
        query="incident in 2022 phonepe fraud police not filing fir",
    )

    assert only_bnss[0]["required_source"] == required[0]
    assert old_fact_with_new_sources[0]["required_source"] == required[0]


def test_source_gap_enforces_single_regime_crpc_conditional_source():
    missing = missing_required_authorities(
        required_sources=["CrPC 1973 section 160 witness attendance safeguards where applicable"],
        passages=[],
        query="police gave section 160 notice asking woman to come station as witness",
    )

    assert missing == [
        {
            "required_source": "CrPC 1973 section 160 witness attendance safeguards where applicable",
            "kind": "national_criminal_source_gap",
        }
    ]


def test_source_gap_does_not_accept_delhi_prison_rules_for_non_delhi_prison():
    missing = missing_required_authorities(
        required_sources=["state prison rules / prison manual for interviews, visits, and permitted books"],
        passages=[
            {
                "index": 1,
                "title": "Delhi Prison Rules 2018",
                "anchor": "delhi-prison-rules-2018/rule-613-616",
                "source_type": "bare_act",
            }
        ],
        query="pune yerwada jail mulaqat denied wife wants to meet husband",
    )

    assert missing


def test_source_gap_requires_pmla_sc_precedent_when_route_names_precedents():
    required = ["Supreme Court PMLA bail/arrest precedents"]
    statute_only = missing_required_authorities(
        required_sources=required,
        passages=[
            {
                "index": 1,
                "title": "Prevention of Money Laundering Act 2002",
                "anchor": "pmla-2002/sec-45",
                "source_type": "bare_act",
            }
        ],
        query="pmla twin condition bail how to argue not guilty",
    )
    precedent_present = missing_required_authorities(
        required_sources=required,
        passages=[
            {
                "index": 2,
                "title": "VIJAY MADANLAL CHOUDHARY versus UNION OF INDIA PMLA",
                "anchor": "2022-insc-757#para-401",
                "source_type": "sc_judgment",
            }
        ],
        query="pmla twin condition bail how to argue not guilty",
    )

    assert statute_only
    assert precedent_present == []


def test_source_gap_requires_both_pesa_fra_and_80c_80ccd_when_named_together():
    pesa_fra_missing = missing_required_authorities(
        required_sources=["PESA Act / Forest Rights Act where Gram Sabha or forest-rights facts apply"],
        passages=[
            {
                "index": 1,
                "title": "Scheduled Tribes and Other Traditional Forest Dwellers (Recognition of Forest Rights) Act 2006",
                "anchor": "fra-2006/sec-5",
                "source_type": "bare_act",
            }
        ],
        query="gond woman forest officer not giving IFR title dindori gram sabha",
    )
    income_missing = missing_required_authorities(
        required_sources=["Income Tax Act 1961 sections 80C and 80CCD deduction sources"],
        passages=[
            {
                "index": 1,
                "title": "Income-tax Act 1961",
                "anchor": "income-tax-1961/sec-80C",
                "source_type": "bare_act",
            }
        ],
        query="can i claim 80c and 80ccd nps together",
    )

    assert pesa_fra_missing
    assert income_missing


def test_source_gap_accepts_stage3_named_statute_sources():
    assert missing_required_authorities(
        required_sources=["Arms Act 1959 definition/licensing/penalty source for alleged weapon or farming tool"],
        passages=[
            {
                "index": 1,
                "title": "Arms Act 1959",
                "anchor": "arms-1959/sec-2",
                "source_type": "bare_act",
            }
        ],
        query="police put arms act because axe was in farm jeep",
    ) == []

    assert missing_required_authorities(
        required_sources=["Maharashtra Control of Organised Crime Act 1999 Section 21 extension rules where MCOCA is alleged"],
        passages=[
            {
                "index": 1,
                "title": "Maharashtra Control of Organised Crime Act 1999",
                "anchor": "maharashtra-control-organised-crime-1999/sec-21",
                "source_type": "bare_act",
            }
        ],
        query="mcoca case 100 days no chargesheet default bail",
    ) == []


def test_source_gap_accepts_hyphenated_income_tax_pan_requirement():
    assert missing_required_authorities(
        required_sources=[
            "Income-tax Act / PAN procedure where PAN record or PAN-Aadhaar linking is involved",
            "Aadhaar Act 2016 where Aadhaar authentication or demographic data is involved",
        ],
        passages=[
            {
                "index": 1,
                "title": "Income-tax Act 1961",
                "anchor": "income-tax-1961/sec-139-i",
                "source_type": "bare_act",
            },
            {
                "index": 2,
                "title": "Aadhaar (Targeted Delivery of Financial and Other Subsidies, Benefits and Services) Act 2016",
                "anchor": "aadhaar-2016/sec-8-a",
                "source_type": "bare_act",
            },
        ],
        query="my pan and aadhar is mismatch",
    ) == []


def test_source_gap_recognizes_common_runtime_route_authorities():
    cases = [
        (
            "Motor Vehicles Act 1988 aggregator licensing provisions",
            "uber driver account deactivated rating low mumbai aggregator",
            {
                "title": "Motor Vehicle Aggregator Guidelines 2020",
                "anchor": "motor-vehicle-aggregator-guidelines-2020#app-transparency-grievance",
                "source_type": "guideline",
            },
        ),
        (
            "Guardians and Wards Act / family law custody principles",
            "father took child abroad custody",
            {
                "title": "Guardians and Wards Act 1890",
                "anchor": "guardians-wards-1890/sec-25",
                "source_type": "bare_act",
            },
        ),
        (
            "state Shops and Establishments Act / rules",
            "shop act jaipur registration staff",
            {
                "title": "Rajasthan Shops and Commercial Establishments Act 1958",
                "anchor": "rajasthan-shops-establishments-1958/sec-4",
                "source_type": "bare_act",
            },
        ),
        (
            "National Food Security Act 2013 for TPDS/ration entitlement and grievance redressal",
            "ration biometric fail not getting quota",
            {
                "title": "National Food Security Act 2013",
                "anchor": "national-food-security-2013/sec-12",
                "source_type": "bare_act",
            },
        ),
        (
            "Protection of Civil Rights Act 1955 for temple, well/water, and public-access disabilities",
            "dalit stopped from entering temple",
            {
                "title": "Protection of Civil Rights Act 1955",
                "anchor": "protection-civil-rights-1955/sec-3",
                "source_type": "bare_act",
            },
        ),
        (
            "Customs Act 1962 for import/export, ICEGATE, duty, valuation, SVB, drawback, or classification issues",
            "customs drawback claim rejected shipping bill mismatch",
            {
                "title": "Customs Act 1962",
                "anchor": "customs-1962/sec-75",
                "source_type": "bare_act",
            },
        ),
        (
            "Customs Act 1962 for import/export, ICEGATE, duty, valuation, SVB, drawback, or classification issues",
            "icegate bill of entry hold misdeclaration chinese led lights",
            {
                "title": "Customs Act 1962",
                "anchor": "customs-1962/sec-124",
                "source_type": "bare_act",
            },
        ),
        (
            "Customs Act 1962 for import/export, ICEGATE, duty, valuation, SVB, drawback, or classification issues",
            "customs reclassified wire harness higher duty svb valuation",
            {
                "title": "Customs Act 1962",
                "anchor": "customs-1962/sec-14",
                "source_type": "bare_act",
            },
        ),
        (
            "Banking Regulation Act 1949 and RBI grievance route for the bank-service dispute",
            "bank loan against my house without signature",
            {
                "title": "Reserve Bank Integrated Ombudsman Scheme 2021",
                "anchor": "rbi-integrated-ombudsman-2021/sec-2",
                "source_type": "bare_act",
            },
        ),
        (
            "RBI Integrated Ombudsman Scheme for regulated-entity complaint route",
            "bank deducted money wrongly and customer care not helping",
            {
                "title": "Reserve Bank Integrated Ombudsman Scheme 2021",
                "anchor": "rbi-integrated-ombudsman-2021/sec-2",
                "source_type": "bare_act",
            },
        ),
        (
            "Clinical Establishments Act / state clinical-establishment rules where hospital records, billing, or standards are involved",
            "private hospital overcharged icu bill",
            {
                "title": "Clinical Establishments (Registration and Regulation) Act 2010",
                "anchor": "clinical-establishments-2010/sec-12",
                "source_type": "bare_act",
            },
        ),
        (
            "National Green Tribunal Act 2010 for environmental relief/compensation route",
            "factory pollution nearby file PIL high court",
            {
                "title": "National Green Tribunal Act 2010",
                "anchor": "ngt-2010/sec-16",
                "source_type": "bare_act",
            },
        ),
        (
            "Companies Act 2013 annual filing, director disqualification, and restoration provisions",
            "aoc 4 not filed director disqualified revive company",
            {
                "title": "Companies Act 2013",
                "anchor": "companies-2013/sec-164",
                "source_type": "bare_act",
            },
        ),
        (
            "RFCTLARR Act 2013 compensation award, payment/deposit, and reference-to-Authority provisions",
            "highway land compensation not paid",
            {
                "title": "Right to Fair Compensation and Transparency in Land Acquisition, Rehabilitation and Resettlement Act 2013",
                "anchor": "rfctlarr-2013/sec-77-a",
                "source_type": "bare_act",
            },
        ),
        (
            "Real Estate (Regulation and Development) Act 2016 for project registration, possession delay, promoter obligations, and RERA complaint",
            "builder flat carpet area less than agreement rera complaint",
            {
                "title": "Real Estate (Regulation and Development) Act 2016",
                "anchor": "rera-2016/sec-14-c",
                "source_type": "bare_act",
            },
        ),
        (
            "Aadhaar Act 2016 where Aadhaar authentication or identity information is misused",
            "got message saying my aadhaar issued 4 sims i never took how to check",
            {
                "title": "Aadhaar (Targeted Delivery of Financial and Other Subsidies, Benefits and Services) Act 2016",
                "anchor": "aadhaar-2016/sec-29",
                "source_type": "bare_act",
            },
        ),
        (
            "Specific Relief Act 1963 where injunction/performance is sought",
            "signed mou with dealer he is selling to competitor exclusivity clause",
            {
                "title": "Specific Relief Act 1963",
                "anchor": "specific-relief-1963/sec-42",
                "source_type": "bare_act",
            },
        ),
        (
            "Drugs and Cosmetics Act 1940 inspection, sampling, and sale-compliance provisions",
            "drug inspector picked up samples from my medical store schedule h sale without prescription jaipur",
            {
                "title": "Drugs and Cosmetics Act 1940",
                "anchor": "drugs-cosmetics-1940/sec-22-act",
                "source_type": "bare_act",
            },
        ),
        (
            "Employees Compensation Act 1923 occupational-disease and claim provisions",
            "stone quarry silicosis lungs damaged compensation rajasthan",
            {
                "title": "Employees' Compensation Act 1923",
                "anchor": "employees-compensation-1923/sec-3-a@1961-01-01",
                "source_type": "bare_act",
            },
        ),
        (
            "Trade Marks Act 1999 infringement, passing-off, and forum/remedy provisions",
            "amazon seller using my registered brand on fake items",
            {
                "title": "Trade Marks Act 1999",
                "anchor": "trade-marks-1999/sec-134",
                "source_type": "bare_act",
            },
        ),
        (
            "Income Tax Act 1961 for TDS, return, assessment, and appeal issues",
            "appeal before ITAT against CIT Appeals order time limit",
            {
                "title": "Income-tax Act 1961",
                "anchor": "income-tax-1961/sec-253-a",
                "source_type": "bare_act",
            },
        ),
        (
            "Income Tax Act 1961 for Indian taxability of creator/freelance income",
            "fanvue payment frozen 2400 usd indian creator how to release fund",
            {
                "title": "Income-tax Act 1961",
                "anchor": "income-tax-1961/sec-5",
                "source_type": "bare_act",
            },
        ),
        (
            "RBI/KYC or online-gaming rules where financial account facts apply",
            "bank says KYC pending so account is on hold",
            {
                "title": "Reserve Bank Integrated Ombudsman Scheme 2021",
                "anchor": "rbi-integrated-ombudsman-2021/sec-2",
                "source_type": "bare_act",
            },
        ),
        (
            "Mines and Minerals (Development and Regulation) Act 1957 mining lease and mineral-concession approval record",
            "mining company doing blasting next to village no gram sabha consent",
            {
                "title": "Mines and Minerals (Development and Regulation) Act 1957",
                "anchor": "mmdr-1957/sec-4",
                "source_type": "bare_act",
            },
        ),
        (
            "Mediation Act 2023 / rules where notified procedure applies",
            "urgent is pre-litigation mediation mandatory before filing commercial suit",
            {
                "title": "Mediation Act 2023",
                "anchor": "mediation-2023/sec-5",
                "source_type": "bare_act",
            },
        ),
        (
            "constitutional reproductive autonomy and privacy precedents",
            "six months pregnant after rape doctor says abortion too late",
            {
                "title": "X versus THE PRINCIPAL SECRETARY HEALTH AND FAMILY WELFARE DEPARTMENT & ANR.",
                "anchor": "2022-insc-740#para-11",
                "source_type": "sc_judgment",
            },
        ),
    ]

    for required_source, query, passage in cases:
        assert missing_required_authorities(
            required_sources=[required_source],
            passages=[passage],
            query=query,
        ) == []


def test_source_gap_enforces_bank_service_deficiency_consumer_source():
    required_source = "Consumer Protection Act 2019 where bank service deficiency is alleged"
    query = "bank deducted money wrongly and customer care not helping"

    assert should_enforce_required_source(required_source, query=query) is True
    assert missing_required_authorities(
        required_sources=[required_source],
        passages=[
            {
                "title": "Consumer Protection Act 2019",
                "anchor": "consumer-protection-2019/sec-35",
                "source_type": "bare_act",
            }
        ],
        query=query,
    ) == []


def test_source_gap_enforces_birth_registration_for_birth_cert_abbreviation():
    required_source = "Registration of Births and Deaths Act 1969 or state civil-registration rules where locally available"
    query = "panchayat secretary not giving me birth cert of my child born at home where to go"

    assert should_enforce_required_source(required_source, query=query) is True

    unrelated = [
        {
            "title": "Constitution of India",
            "anchor": "constitution-india/sec-342",
            "source_type": "bare_act",
        },
        {
            "title": "Right to Information Act 2005",
            "anchor": "rti-2005/sec-6",
            "source_type": "bare_act",
        },
    ]
    missing = missing_required_authorities(
        required_sources=[required_source],
        passages=unrelated,
        query=query,
    )
    assert missing and missing[0]["kind"] == "state_or_local_authority_gap"

    valid = [
        {
            "title": "Registration of Births and Deaths Act 1969",
            "anchor": "registration-births-deaths-1969/sec-12",
            "source_type": "bare_act",
        }
    ]
    assert missing_required_authorities(
        required_sources=[required_source],
        passages=valid,
        query=query,
    ) == []


def test_source_gap_accepts_rbi_ombudsman_family_as_one_reviewed_route():
    required = (
        "RBI Integrated Ombudsman Scheme / RBI recovery-agent and digital-lending "
        "grievance route for regulated lenders"
    )
    query = "NBFC recovery agents shouted at me in front of my colleagues"
    passages = [
        {
            "index": 1,
            "title": "Reserve Bank Integrated Ombudsman Scheme 2021",
            "anchor": "rbi-integrated-ombudsman-2021/sec-9",
            "source_type": "bare_act",
        },
        {
            "index": 2,
            "title": "Outsourcing of Financial Services - Responsibilities of regulated entities employing Recovery Agents",
            "anchor": "rbi-recovery-agents-2022/para-2",
            "source_type": "circular",
        },
        {
            "index": 3,
            "title": "Reserve Bank of India (Digital Lending) Directions, 2025",
            "anchor": "rbi-digital-lending-directions-2025/para-12",
            "source_type": "guideline",
        },
    ]

    matched = best_source_match(required, passages, query=query)

    assert matched is not None
    assert matched["source_type"] == "bare_act"
    assert matched["anchor"] == "rbi-integrated-ombudsman-2021/sec-9"


def test_source_gap_accepts_conditional_sale_of_goods_quality_authority():
    required = "Sale of Goods Act 1930 where quality rejection, acceptance, or price deduction is disputed"
    query = "buyer accepted my parts but is deducting payment saying quality issue"
    sale = {
        "index": 1,
        "title": "Sale of Goods Act 1930",
        "anchor": "sale-of-goods-1930/sec-55@1930-07-01",
        "source_type": "bare_act",
    }

    assert best_source_match(required, [sale], query=query) == sale


def test_source_gap_does_not_activate_conditional_sale_of_goods_for_plain_arrears():
    required = "Sale of Goods Act 1930 where quality rejection, acceptance, or price deduction is disputed"
    query = "buyer accepted delivery and has not paid the invoice for 60 days"
    sale = {
        "index": 1,
        "title": "Sale of Goods Act 1930",
        "anchor": "sale-of-goods-1930/sec-55@1930-07-01",
        "source_type": "bare_act",
    }

    assert best_source_match(required, [sale], query=query) is None
    assert should_enforce_required_source(required, query=query) is False
    assert missing_required_authorities(
        required_sources=[required],
        passages=[sale],
        query=query,
    ) == []

    legacy_fallback = {**sale, "anchor": "sale-of-goods-1930/sec-42@1930-07-01"}
    assert best_source_match(required, [legacy_fallback], query=query) is None


def test_source_gap_enforces_conditional_sale_of_goods_for_quality_dispute():
    required = "Sale of Goods Act 1930 where quality rejection, acceptance, or price deduction is disputed"
    query = "buyer accepted my parts but deducted payment saying there is a quality defect"

    assert should_enforce_required_source(required, query=query) is True


def test_source_gap_does_not_activate_sale_of_goods_for_unrelated_quality_language():
    required = "Sale of Goods Act 1930 where quality rejection, acceptance, or price deduction is disputed"
    passage = {
        "index": 1,
        "title": "Sale of Goods Act 1930",
        "anchor": "sale-of-goods-1930/sec-55@1930-07-01",
        "source_type": "bare_act",
    }

    for query in (
        "buyer rejected my payment request and is not responding",
        "the quality of customer service is poor and my invoice is unpaid",
        "the quality of the delivery service was poor",
        "the customer rejected the delivery date",
        "my payment request was rejected and shipment is delayed",
        "the stock quality report was rejected",
        "my product manager rejected the quality report",
        "the quality of our software product is poor",
        "the quality of our service product is poor",
        "the buyer rejected my proposal and product roadmap",
        "the model specification document was rejected",
        "I supplied documents to the department but they rejected them",
        "my application was rejected after I supplied all the documents",
        "the quality of the electricity supply is poor",
        "the quality of the water supply is poor",
        "the quality of our training material was rejected",
    ):
        assert should_enforce_required_source(required, query=query) is False
        assert best_source_match(required, [passage], query=query) is None


def test_source_gap_accepts_natural_quality_dispute_phrasing():
    required = "Sale of Goods Act 1930 where quality rejection, acceptance, or price deduction is disputed"

    for query in (
        "buyer says the supplied goods are substandard",
        "buyer rejected the non-conforming material shipment",
        "buyer says the delivered batch was bad and deducted payment",
        "the goods arrived damaged",
        "the items are not as described",
        "the material does not match the agreed specification",
        "buyer received the wrong model",
        "buyer will not accept the consignment",
        "buyer refused to accept the goods because they were late",
        "the component batch failed inspection",
        "wrong quantity was delivered and buyer withheld payment",
        "the shipment was short by 20 units",
        "buyer refused these goods",
        "buyer claimed the goods were nonconforming",
        "the goods failed testing",
        "short shipment of 20 units",
        "only 80 of 100 pieces arrived",
        "received the wrong colour",
    ):
        assert should_enforce_required_source(required, query=query) is True


def test_source_gap_does_not_treat_tax_deduction_as_quality_rejection():
    required = "Sale of Goods Act 1930 where quality rejection, acceptance, or price deduction is disputed"
    query = "buyer deducted TDS from my goods invoice but there is no quality dispute"
    sale = {
        "index": 1,
        "title": "Sale of Goods Act 1930",
        "anchor": "sale-of-goods-1930/sec-55@1930-07-01",
        "source_type": "bare_act",
    }

    assert best_source_match(required, [sale], query=query) is None


def test_source_gap_does_not_treat_acceptance_record_as_quality_dispute():
    required = "Sale of Goods Act 1930 where quality rejection, acceptance, or price deduction is disputed"
    query = "acceptance was recorded and payment is overdue"
    sale = {
        "index": 1,
        "title": "Sale of Goods Act 1930",
        "anchor": "sale-of-goods-1930/sec-55@1930-07-01",
        "source_type": "bare_act",
    }

    assert best_source_match(required, [sale], query=query) is None


def test_source_gap_uses_the_actual_sale_of_goods_anchor_not_text_mentions():
    required = "Sale of Goods Act 1930 where quality rejection, acceptance, or price deduction is disputed"
    query = "buyer says quality issue and rejected the supplied goods"
    wrong_anchor = {
        "index": 1,
        "title": "Sale of Goods Act 1930",
        "anchor": "sale-of-goods-1930/sec-999@1930-07-01",
        "text": "This passage mentions Sale of Goods Act 1930 Section 55, but is anchored elsewhere.",
        "source_type": "bare_act",
    }

    assert best_source_match(required, [wrong_anchor], query=query) is None


def test_source_gap_rejects_malformed_sale_of_goods_split_anchor():
    required = "Sale of Goods Act 1930 where quality rejection, acceptance, or price deduction is disputed"
    query = "buyer says quality issue and rejected the supplied goods"
    malformed = {
        "index": 1,
        "title": "Sale of Goods Act 1930",
        "anchor": "sale-of-goods-1930/sec-55__bad@1930-07-01",
        "source_type": "bare_act",
    }

    assert best_source_match(required, [malformed], query=query) is None


def test_source_gap_accepts_legacy_436a_split_anchor_from_numbered_heading():
    required = "CrPC 1973 section 436A for legacy / transitional comparison"
    passage = {
        "index": 1,
        "title": "Code of Criminal Procedure 1973",
        "anchor": "crpc-1973/sec-436-a",
        "source_type": "bare_act",
        "heading": "436A. Maximum period for which an undertrial prisoner can be detained.",
    }

    assert best_source_match(
        required,
        [passage],
        query="65 year old undertrial in a case pending since 2023",
    ) == passage


def test_source_gap_does_not_cross_satisfy_explicit_bnss_and_crpc_arrest_sources():
    query = "brother was arrested and family was not told where he is"
    bnss_required = "BNSS 2023 arrest and 24-hour production safeguards"
    crpc_required = "CrPC 1973 arrest and 24-hour production safeguards"
    bnss_passage = {
        "index": 1,
        "title": "Bharatiya Nagarik Suraksha Sanhita 2023",
        "anchor": "bnss-2023/sec-57",
        "source_type": "bare_act",
    }
    crpc_passage = {
        "index": 2,
        "title": "Code of Criminal Procedure 1973",
        "anchor": "crpc-1973/sec-57",
        "source_type": "bare_act",
    }

    assert best_source_match(bnss_required, [crpc_passage], query=query) is None
    assert best_source_match(crpc_required, [bnss_passage], query=query) is None
    assert best_source_match(bnss_required, [bnss_passage], query=query) == bnss_passage
    assert best_source_match(crpc_required, [crpc_passage], query=query) == crpc_passage


def test_source_gap_does_not_enforce_bank_service_deficiency_source_for_non_bank_consumer_query():
    required_source = "Consumer Protection Act 2019 where bank service deficiency is alleged"

    assert should_enforce_required_source(
        required_source,
        query="phone arrived damaged and seller is refusing return",
    ) is False


def test_source_gap_cyber_old_regime_composite_requires_complaint_procedure_not_bail():
    from apps.api.source_gap import best_source_match

    required = "BNS/BNSS or IPC/CrPC based on incident date"
    query = "someone made deepfake video of me on instagram in June 2024 and is extorting me"
    passages = [
        {
            "index": 1,
            "title": "Indian Penal Code 1860",
            "anchor": "ipc-1860/sec-384",
            "source_type": "bare_act",
        },
        {
            "index": 2,
            "title": "Code of Criminal Procedure 1973",
            "anchor": "crpc-1973/sec-437-a",
            "source_type": "bare_act",
        },
    ]

    assert best_source_match(required, passages, query=query) is None

    passages.append({
        "index": 3,
        "title": "Code of Criminal Procedure 1973",
        "anchor": "crpc-1973/sec-200",
        "source_type": "bare_act",
    })

    matched = best_source_match(required, passages, query=query)

    assert matched is not None
    assert matched["source_type"] == "aggregate"
    assert "ipc-1860/sec-384" in matched["anchor"]
    assert "crpc-1973/sec-200" in matched["anchor"]

    numeric_pre_cutover_query = "someone made deepfake video of me before 01/07/2024 and is extorting me"
    current_regime_sources = [
        {
            "index": 1,
            "title": "Bharatiya Nyaya Sanhita 2023",
            "anchor": "bns-2023/sec-308-a",
            "source_type": "bare_act",
        },
        {
            "index": 2,
            "title": "Bharatiya Nagarik Suraksha Sanhita 2023",
            "anchor": "bnss-2023/sec-173-b",
            "source_type": "bare_act",
        },
    ]
    assert best_source_match(required, current_regime_sources, query=numeric_pre_cutover_query) is None
    assert best_source_match(required, passages, query=numeric_pre_cutover_query) is not None


def test_source_gap_cyber_negated_extortion_accepts_threat_sources():
    missing = missing_required_authorities(
        required_sources=["BNS/BNSS or IPC/CrPC based on incident date"],
        passages=[
            {
                "index": 1,
                "title": "Bharatiya Nyaya Sanhita 2023",
                "anchor": "bns-2023/sec-351",
                "source_type": "bare_act",
            },
            {
                "index": 2,
                "title": "Bharatiya Nagarik Suraksha Sanhita 2023",
                "anchor": "bnss-2023/sec-173",
                "source_type": "bare_act",
            },
        ],
        query="someone made deepfake video in 2025 no extortion just threatening to share it",
    )

    assert missing == []


def test_source_gap_cyber_notice_no_paper_accepts_bnss_notice_procedure():
    event = build_source_gap_event(
        required_sources=["BNS/BNSS or IPC/CrPC based on incident date"],
        passages=[
            {
                "index": 1,
                "title": "Bharatiya Nagarik Suraksha Sanhita 2023",
                "anchor": "bnss-2023/sec-35",
                "source_type": "bare_act",
            },
            {
                "index": 2,
                "title": "Information Technology Act 2000",
                "anchor": "it-act-2000/sec-66D",
                "source_type": "bare_act",
            },
        ],
        query="police calling me for notice in cyber case but not giving paper",
        route_category="cyber_fraud_or_harassment",
    )

    assert event is None


def test_source_gap_recognizes_copyright_composite_and_hyphenated_section_anchor():
    assert missing_required_authorities(
        required_sources=["Copyright Act 1957 infringement, exceptions/fair dealing, and civil remedies"],
        passages=[
            {
                "title": "Copyright Act 1957",
                "anchor": "copyright-1957/sec-51",
                "source_type": "bare_act",
            },
            {
                "title": "Copyright Act 1957",
                "anchor": "copyright-1957/sec-52-a",
                "source_type": "bare_act",
            },
            {
                "title": "Copyright Act 1957",
                "anchor": "copyright-1957/sec-55",
                "source_type": "bare_act",
            },
        ],
        query="spotify took down remix fair use copyright",
    ) == []

    assert missing_required_authorities(
        required_sources=["CrPC 1973 section 436A for legacy / transitional comparison"],
        passages=[
            {
                "title": "Code of Criminal Procedure 1973",
                "anchor": "crpc-1973/sec-436-a",
                "source_type": "bare_act",
                "text": "Code of Criminal Procedure 1973, Section 436A\n436A. Maximum period for detention.",
            }
        ],
        query="undertrial 70 years old crpc 436a",
    ) == []


def test_source_gap_skips_medical_ethics_for_billing_only_but_requires_for_wrong_surgery():
    billing_only = missing_required_authorities(
        required_sources=[
            "Medical Council / medical ethics record and professional-conduct rules where records or negligence are disputed",
        ],
        passages=[],
        query="private hospital overcharged 4 lakh icu bill denying refund",
    )
    wrong_surgery = missing_required_authorities(
        required_sources=[
            "Medical Council / medical ethics record and professional-conduct rules where records or negligence are disputed",
        ],
        passages=[],
        query="hospital operated wrong leg on my father",
    )

    assert billing_only == []
    assert wrong_surgery[0]["required_source"].startswith("Medical Council")


def test_source_gap_skips_false_positive_route_labels_from_casual_police_or_marriage_words():
    assert missing_required_authorities(
        required_sources=["BNS/BNSS or IPC/CrPC only as a separate criminal-negligence track where facts support it"],
        passages=[],
        query="private hospital overcharged 4 lakh icu bill denying refund need lawyer or police",
    ) == []

    assert missing_required_authorities(
        required_sources=["family law statute by religion"],
        passages=[],
        query="he slaps me but says sorry next day my parents say all marriages are like this should I stay",
    ) == []

    assert missing_required_authorities(
        required_sources=["BNSS 2023 / CrPC 1973 only if the case-status issue is in a criminal case"],
        passages=[],
        query="how to file vakalatnama change of advocate during pending suit need lawyer or police",
    ) == []

    assert missing_required_authorities(
        required_sources=["BNSS 2023 / CrPC 1973 only if the case-status issue is in a criminal case"],
        passages=[],
        query="urgent summons not served through registered post what is next step",
    ) == []

    assert missing_required_authorities(
        required_sources=["labour/DLSA grievance route"],
        passages=[],
        query="wife delivered baby at construction site hut no esi contractor says not his problem",
    ) == []

    assert missing_required_authorities(
        required_sources=["victim-compensation and DLSA procedure for urgent treatment/support"],
        passages=[],
        query="mother in law is threatening to throw acid if I do not bring money",
    ) == []


def test_source_gap_arms_farming_tool_requires_definition_anchor():
    missing = missing_required_authorities(
        required_sources=["Arms Act 1959 definition/licensing/penalty source for alleged weapon or farming tool"],
        passages=[
            {
                "index": 1,
                "title": "Arms Act 1959",
                "anchor": "arms-1959/sec-25",
                "source_type": "bare_act",
            }
        ],
        query="arms act for axe used in farming",
    )
    covered = missing_required_authorities(
        required_sources=["Arms Act 1959 definition/licensing/penalty source for alleged weapon or farming tool"],
        passages=[
            {
                "index": 1,
                "title": "Arms Act 1959",
                "anchor": "arms-1959/sec-2",
                "source_type": "bare_act",
            }
        ],
        query="arms act for axe used in farming",
    )

    assert missing[0]["required_source"].startswith("Arms Act 1959")
    assert covered == []


def test_source_gap_accepts_default_bail_remand_sections():
    assert missing_required_authorities(
        required_sources=["BNSS 2023 / CrPC 1973 default bail provisions based on incident date"],
        passages=[
            {
                "index": 1,
                "title": "Bharatiya Nagarik Suraksha Sanhita 2023",
                "anchor": "bnss-2023/sec-187",
                "source_type": "bare_act",
            },
            {
                "index": 2,
                "title": "Code of Criminal Procedure 1973",
                "anchor": "crpc-1973/sec-167",
                "source_type": "bare_act",
            },
        ],
        query="brother in jail 60 days no chargesheet what is default bail",
    ) == []


def test_source_gap_accepts_ndps_search_seizure_procedure_sections():
    required = [
        "BNSS 2023 / CrPC 1973 search, seizure, arrest, bail, and complaint procedure based on incident date"
    ]
    query = "police caught my drug parcel at airport no fake call no money demand what punishment"

    assert missing_required_authorities(
        required_sources=required,
        passages=[
            {
                "index": 1,
                "title": "Bharatiya Nagarik Suraksha Sanhita 2023",
                "anchor": "bnss-2023/sec-483@2024-07-01",
                "source_type": "bare_act",
            },
            {
                "index": 3,
                "title": "Code of Criminal Procedure 1973",
                "anchor": "crpc-1973/sec-165",
                "source_type": "bare_act",
            },
            {
                "index": 4,
                "title": "Narcotic Drugs and Psychotropic Substances Act 1985",
                "anchor": "ndps-1985/sec-22-a",
                "source_type": "bare_act",
            },
        ],
        query=query,
    ) == []

    wrong_family = missing_required_authorities(
        required_sources=required,
        passages=[
            {
                "index": 1,
                "title": "Bharatiya Nagarik Suraksha Sanhita 2023",
                "anchor": "bnss-2023/sec-144",
                "source_type": "bare_act",
            },
            {
                "index": 2,
                "title": "Code of Criminal Procedure 1973",
                "anchor": "crpc-1973/sec-125",
                "source_type": "bare_act",
            },
        ],
        query=query,
    )
    assert wrong_family == [
        {
            "required_source": required[0],
            "kind": "national_criminal_source_gap",
        }
    ]


def test_stage_e6_source_gap_accepts_undertrial_and_special_bail_authorities():
    assert missing_required_authorities(
        required_sources=["Legal Services Authorities Act 1987 and Under Trial Review Committee procedure"],
        passages=[
            {
                "index": 1,
                "title": "Legal Services Authorities Act 1987",
                "anchor": "legal-services-authorities-1987/sec-9",
                "source_type": "bare_act",
            },
        ],
        query="undertrial in jail 6 years trial not started legal aid what can we do",
    ) == []

    assert missing_required_authorities(
        required_sources=["BNS 2023 / IPC 1860 offence provisions where relevant"],
        passages=[],
        query="uapa 18 months bail prima facie case made out",
    ) == []

    medical_with_wrong_section = missing_required_authorities(
        required_sources=["constitutional liberty and medical/vulnerability bail principles"],
        passages=[
            {
                "index": 1,
                "title": "Code of Criminal Procedure 1973",
                "anchor": "crpc-1973/sec-437-a",
                "source_type": "bare_act",
            },
        ],
        query="wife arrested pmla bank fraud interim bail newborn",
    )
    assert medical_with_wrong_section

    assert missing_required_authorities(
        required_sources=["constitutional liberty and medical/vulnerability bail principles"],
        passages=[
            {
                "index": 1,
                "title": "Code of Criminal Procedure 1973",
                "anchor": "crpc-1973/sec-437",
                "source_type": "bare_act",
            },
        ],
        query="wife arrested pmla bank fraud interim bail newborn",
    ) == []

    article_21a_education_not_liberty = missing_required_authorities(
        required_sources=["constitutional liberty and medical/vulnerability bail principles"],
        passages=[
            {
                "index": 1,
                "title": "Constitution of India",
                "anchor": "constitution-india/sec-21-a",
                "source_type": "bare_act",
            },
        ],
        query="wife arrested pmla bank fraud interim bail newborn",
    )
    assert article_21a_education_not_liberty

    assert missing_required_authorities(
        required_sources=["constitutional liberty and medical/vulnerability bail principles"],
        passages=[
            {
                "index": 1,
                "title": "Constitution of India",
                "anchor": "constitution-india/sec-21",
                "source_type": "bare_act",
            },
        ],
        query="wife arrested pmla bank fraud interim bail newborn",
    ) == []

    assert missing_required_authorities(
        required_sources=["BNSS 2023 / CrPC 1973 bail and custody procedure based on incident date"],
        passages=[
            {
                "index": 1,
                "title": "Bharatiya Nagarik Suraksha Sanhita 2023",
                "anchor": "bnss-2023/sec-187-b@2024-07-01",
                "source_type": "bare_act",
            },
            {
                "index": 2,
                "title": "Code of Criminal Procedure 1973",
                "anchor": "crpc-1973/sec-167-b",
                "source_type": "bare_act",
            },
        ],
        query="ndps 110 days no complaint filed special court default bail possible",
    ) == []

    assert missing_required_authorities(
        required_sources=["BNSS 2023 / CrPC 1973 arrest, FIR, remand, and bail procedure based on incident date"],
        passages=[
            {
                "index": 1,
                "title": "Bharatiya Nagarik Suraksha Sanhita 2023",
                "anchor": "bnss-2023/sec-35@2024-07-01",
                "source_type": "bare_act",
            },
            {
                "index": 2,
                "title": "Code of Criminal Procedure 1973",
                "anchor": "crpc-1973/sec-167-a",
                "source_type": "bare_act",
            },
        ],
        query="police arrested my son for being gay",
    ) == []

    arrest_with_wrong_bnss_section = missing_required_authorities(
        required_sources=["BNSS 2023 / CrPC 1973 arrest, FIR, remand, and bail procedure based on incident date"],
        passages=[
            {
                "index": 1,
                "title": "Bharatiya Nagarik Suraksha Sanhita 2023",
                "anchor": "bnss-2023/sec-216@2024-07-01",
                "source_type": "bare_act",
            },
        ],
        query="in 2025 police arrested my son for being gay",
    )
    assert arrest_with_wrong_bnss_section

    assert missing_required_authorities(
        required_sources=["Unlawful Activities (Prevention) Act 1967 section 43D / 43D(5) bail restrictions and prolonged-incarceration/default-bail rules"],
        passages=[
            {
                "index": 1,
                "title": "Unlawful Activities (Prevention) Act 1967",
                "anchor": "uapa-1967/sec-43d",
                "source_type": "bare_act",
            },
        ],
        query="uapa 18 months bail prima facie case made out",
    ) == []

    uapa_missing = missing_required_authorities(
        required_sources=["Unlawful Activities (Prevention) Act 1967 section 43D / 43D(5) bail restrictions and prolonged-incarceration/default-bail rules"],
        passages=[
            {
                "index": 1,
                "title": "Bharatiya Nagarik Suraksha Sanhita 2023",
                "anchor": "bnss-2023/sec-480",
                "source_type": "bare_act",
            },
        ],
        query="uapa 18 months bail prima facie case made out",
    )
    assert uapa_missing


def test_source_gap_accepts_subsection_anchors_and_combined_constitution_sources():
    assert missing_required_authorities(
        required_sources=[
            "BNSS 2023 section 528 for current High Court inherent-powers/quashing framing",
            "CrPC 1973 section 482 for pre-1 July 2024 or legacy CrPC framing",
        ],
        passages=[
            {
                "index": 1,
                "title": "Bharatiya Nagarik Suraksha Sanhita 2023",
                "anchor": "bnss-2023/sec-528@2024-07-01",
                "source_type": "bare_act",
            },
            {
                "index": 2,
                "title": "Code of Criminal Procedure 1973",
                "anchor": "crpc-1973/sec-482",
                "source_type": "bare_act",
            },
        ],
        query="fake fir quashing after wages",
    ) == []

    assert missing_required_authorities(
        required_sources=[
            "Article 21 and Article 22 liberty and arrest safeguards",
            "Code on Wages 2019 where the same facts include unpaid wage, attendance, or contractor payment dispute",
        ],
        passages=[
            {
                "index": 1,
                "title": "Constitution of India",
                "anchor": "constitution-india/sec-21",
                "source_type": "bare_act",
            },
            {
                "index": 2,
                "title": "Constitution of India",
                "anchor": "constitution-india/sec-22",
                "source_type": "bare_act",
            },
            {
                "index": 3,
                "title": "Code on Wages 2019",
                "anchor": "code-on-wages-2019/sec-45@2019-08-08",
                "source_type": "bare_act",
            },
        ],
        query="labour chowk police picking workers saying begging",
    ) == []


def test_source_gap_does_not_mix_regime_and_section_across_unrelated_passages():
    mixed_wrong_sources = missing_required_authorities(
        required_sources=["BNSS 2023 / CrPC 1973 bail provisions based on incident date"],
        passages=[
            {
                "index": 1,
                "title": "Bharatiya Nagarik Suraksha Sanhita 2023",
                "anchor": "bnss-2023/sec-173",
                "source_type": "bare_act",
            },
            {
                "index": 2,
                "title": "Negotiable Instruments Act 1881",
                "anchor": "negotiable-instruments-1881/sec-480",
                "source_type": "bare_act",
            },
            {
                "index": 3,
                "title": "Code of Criminal Procedure 1973",
                "anchor": "crpc-1973/sec-154",
                "source_type": "bare_act",
            },
        ],
        query="brother arrested six months no chargesheet can bail be filed",
    )

    assert mixed_wrong_sources == [
        {
            "required_source": "BNSS 2023 / CrPC 1973 bail provisions based on incident date",
            "kind": "national_criminal_source_gap",
        }
    ]


def test_source_gap_anchor_matching_does_not_treat_sec_359_as_sec_35():
    missing = missing_required_authorities(
        required_sources=["BNSS 2023 / CrPC 1973 arrest, notice, bail, and complaint procedure based on incident date"],
        passages=[
            {
                "index": 1,
                "title": "Bharatiya Nagarik Suraksha Sanhita 2023",
                "anchor": "bnss-2023/sec-359",
                "source_type": "bare_act",
            },
            {
                "index": 2,
                "title": "Code of Criminal Procedure 1973",
                "anchor": "crpc-1973/sec-160",
                "source_type": "bare_act",
            },
        ],
        query="police notice came after arrest threat",
    )

    assert missing


def test_source_gap_kind_uses_required_source_before_query_terms():
    missing = missing_required_authorities(
        required_sources=["BNSS 2023 / CrPC 1973 bail provisions based on incident date"],
        passages=[],
        query="village called my mother witch and police arrested my brother",
    )

    assert missing == [
        {
            "required_source": "BNSS 2023 / CrPC 1973 bail provisions based on incident date",
            "kind": "national_criminal_source_gap",
        }
    ]


def test_source_gap_event_has_user_handoff_policy_for_state_gap():
    event = build_source_gap_event(
        query="ranchi village calling mother daain",
        route_category="police_fir",
        required_sources=["Jharkhand witch-hunting state Act source"],
        passages=[
            {
                "index": 1,
                "title": "Bharatiya Nyaya Sanhita 2023",
                "anchor": "bns-2023/sec-115",
                "source_type": "bare_act",
            }
        ],
    )

    assert event is not None
    assert event["has_gap"] is True
    assert event["outcome"] == "source_gap_handoff"
    assert event["safe_handoff_only"] is True
    assert event["policy"] == "do_not_substitute_neighboring_authority"
    assert event["handoff"] == "DLSA/legal aid or a qualified lawyer"
    assert set(event) == {
        "has_gap", "route_category", "gap_kinds", "missing_required_sources",
        "message", "handoff", "policy", "outcome", "reason", "safe_handoff_only",
    }
    assert event["gap_kinds"] == ["state_or_local_authority_gap"]


def test_material_local_route_gap_is_canonical_handoff_with_a_matter_plan():
    query = "auto permit expired in Chennai how to renew Tamil Nadu"
    route = route_matter(query)
    plan = build_matter_plan(query, route)

    event = build_source_gap_event(
        query=query,
        route_category=route.category,
        required_sources=route.required_sources,
        passages=[],
        plan=plan,
    )

    assert event is not None
    assert event["outcome"] == "source_gap_handoff"
    assert event["safe_handoff_only"] is True
    assert any(
        item["kind"] == "state_or_local_authority_gap"
        and "motor vehicle rules" in item["required_source"]
        for item in event["missing_required_sources"]
    )


def test_material_municipal_sealing_gap_cannot_bypass_source_gate():
    query = "my shop is in Gujarat and municipality sealed it"
    route = route_matter(query)
    plan = build_matter_plan(query, route)

    event = build_source_gap_event(
        query=query,
        route_category=route.category,
        required_sources=route.required_sources,
        passages=[],
        plan=plan,
    )

    assert route.category == "business_license_compliance"
    assert event is not None
    assert event["outcome"] == "source_gap_handoff"
    assert event["safe_handoff_only"] is True
    assert any(
        item["kind"] == "state_or_local_authority_gap"
        and "municipal corporation" in item["required_source"]
        for item in event["missing_required_sources"]
    )


def _exact_food_authority_passages():
    return [
        {
            "index": 1,
            "title": "Food Safety and Standards Act 2006",
            "anchor": "food-safety-standards-2006/sec-26",
            "source_type": "bare_act",
            "document_id": "food-safety-and-standards-2006",
            "required_source_pack": "food_safety_2006",
        },
        {
            "index": 2,
            "title": "Food Safety and Standards (Licensing and Registration of Food Businesses) Regulations 2011",
            "anchor": "fssai-licensing-2011/reg-2-1",
            "source_type": "regulation",
            "document_id": "fssai-licensing-2011",
            "required_source_pack": "fssai_licensing_2011",
        },
    ]


def test_mixed_food_authority_passages_still_handoff_for_municipal_source():
    query = "BMC sealed my restaurant after FSSAI inspection"
    route = route_matter(query)
    plan = build_matter_plan(query, route)

    event = build_source_gap_event(
        query=query,
        route_category=route.category,
        required_sources=route.required_sources,
        passages=_exact_food_authority_passages(),
        plan=plan,
    )

    assert route.label == "Municipal sealing / shop closure notice"
    assert event is not None
    assert event["outcome"] == "source_gap_handoff"
    assert event["safe_handoff_only"] is True
    assert "state_or_local_authority_gap" in event["gap_kinds"]
    assert any(
        item["kind"] == "state_or_local_authority_gap"
        and "municipal corporation" in item["required_source"]
        for item in event["missing_required_sources"]
    )


def test_local_health_department_gap_cannot_be_satisfied_by_food_passages():
    query = "local health department closed my hotel"
    route = route_matter(query)
    plan = build_matter_plan(query, route)

    event = build_source_gap_event(
        query=query,
        route_category=route.category,
        required_sources=route.required_sources,
        passages=_exact_food_authority_passages(),
        plan=plan,
    )

    assert route.label == "Municipal sealing / shop closure notice"
    assert event is not None
    assert event["outcome"] == "source_gap_handoff"
    assert event["safe_handoff_only"] is True
    assert any(
        item["kind"] == "state_or_local_authority_gap"
        and "municipal corporation" in item["required_source"]
        for item in event["missing_required_sources"]
    )


def test_local_health_inspector_and_officer_gap_requires_local_authority_source():
    for query in (
        "local health inspector closed my hotel after hygiene inspection",
        "local health officer closed my hotel after inspection",
    ):
        route = route_matter(query)
        plan = build_matter_plan(query, route)
        event = build_source_gap_event(
            query=query,
            route_category=route.category,
            required_sources=route.required_sources,
            passages=[],
            plan=plan,
        )
        assert route.label == "Municipal sealing / shop closure notice", query
        assert event is not None, query
        assert event["outcome"] == "source_gap_handoff", query
        assert "state_or_local_authority_gap" in event["gap_kinds"], query


def test_private_city_corporation_does_not_create_municipal_source_gap():
    query = "private Vadodara corporation closed my hotel"
    route = route_matter(query)
    plan = build_matter_plan(query, route)
    event = build_source_gap_event(
        query=query,
        route_category=route.category,
        required_sources=route.required_sources,
        passages=[],
        plan=plan,
    )

    assert route.label != "Municipal sealing / shop closure notice"
    assert not event or "state_or_local_authority_gap" not in event["gap_kinds"]

    private_city_query = "private city corporation sealed my shop"
    private_city_route = route_matter(private_city_query)
    private_city_plan = build_matter_plan(private_city_query, private_city_route)
    private_city_event = build_source_gap_event(
        query=private_city_query,
        route_category=private_city_route.category,
        required_sources=[
            "state municipal corporation/municipality law and trade-licence by-laws for sealing or closure power",
        ],
        passages=[],
        plan=private_city_plan,
    )
    assert not private_city_event or "state_or_local_authority_gap" not in private_city_event["gap_kinds"]

    street_query = "private corporation removed my street cart"
    street_route = route_matter(street_query)
    street_plan = build_matter_plan(street_query, street_route)
    street_event = build_source_gap_event(
        query=street_query,
        route_category=street_route.category,
        required_sources=[
            "municipal corporation / town vending committee procedure",
        ],
        passages=[],
        plan=street_plan,
    )
    assert not street_event or "state_or_local_authority_gap" not in street_event["gap_kinds"]

    separate_authority_query = "landlord removed my street cart and municipality refused to help"
    separate_route = route_matter(separate_authority_query)
    separate_plan = build_matter_plan(separate_authority_query, separate_route)
    separate_event = build_source_gap_event(
        query=separate_authority_query,
        route_category=separate_route.category,
        required_sources=[
            "municipal corporation / town vending committee procedure",
        ],
        passages=[],
        plan=separate_plan,
    )
    assert not separate_event or "state_or_local_authority_gap" not in separate_event["gap_kinds"]

    security_query = "security guard seized my vendor goods and BMC said it is private"
    security_route = route_matter(security_query)
    security_plan = build_matter_plan(security_query, security_route)
    security_event = build_source_gap_event(
        query=security_query,
        route_category=security_route.category,
        required_sources=["municipal corporation / town vending committee procedure"],
        passages=[],
        plan=security_plan,
    )
    assert not security_event or "state_or_local_authority_gap" not in security_event["gap_kinds"]

    for public_vendor_query in (
        "hawker license pending but corporation removed my stall before hearing",
        "vending certificate pending but corporation took my goods",
        "hawker licence pending but corporation seized my stall",
    ):
        public_vendor_route = route_matter(public_vendor_query)
        public_vendor_plan = build_matter_plan(public_vendor_query, public_vendor_route)
        public_vendor_event = build_source_gap_event(
            query=public_vendor_query,
            route_category=public_vendor_route.category,
            required_sources=public_vendor_route.required_sources,
            passages=[],
            plan=public_vendor_plan,
        )
        assert public_vendor_route.category == "street_vendor_municipal", public_vendor_query
        assert public_vendor_event is not None, public_vendor_query
        assert "state_or_local_authority_gap" in public_vendor_event["gap_kinds"], public_vendor_query


def test_local_body_premises_closure_wording_also_requires_local_authority():
    query = "local body locked my commercial premises for licence issue"
    route = route_matter(query)
    plan = build_matter_plan(query, route)
    event = build_source_gap_event(
        query=query,
        route_category=route.category,
        required_sources=route.required_sources,
        passages=[],
        plan=plan,
    )

    assert event is not None
    assert event["outcome"] == "source_gap_handoff"
    assert "state_or_local_authority_gap" in event["gap_kinds"]


def test_jharkhand_witch_reference_marker_does_not_satisfy_state_gap():
    missing = missing_required_authorities(
        required_sources=[
            "state-specific witch-hunting statute must be verified for the user's state before state-law offence details are given"
        ],
        passages=[
            {
                "index": 1,
                "title": "Jharkhand Prevention of Witch (Daain) Practices Act 2001",
                "anchor": "jharkhand-prevention-witch-daain-practices-2001/sec-3",
                "source_type": "official_summary",
            }
        ],
        query="neighbours calling me witch want to throw me out of village chaibasa",
    )

    assert missing
    assert missing[0]["kind"] == "state_or_local_authority_gap"


def test_jharkhand_witch_bare_act_satisfies_state_gap_for_districts():
    missing = missing_required_authorities(
        required_sources=[
            "state-specific witch-hunting statute must be verified for the user's state before state-law offence details are given"
        ],
        passages=[
            {
                "index": 1,
                "title": "Jharkhand Prevention of Witch (Daain) Practices Act 2001",
                "anchor": "jharkhand-prevention-witch-daain-practices-2001/sec-3",
                "source_type": "bare_act",
            }
        ],
        query="tribal woman called witch and beaten in gumla police refused FIR",
    )

    assert missing == []


def test_jhalsa_witch_official_guidance_satisfies_jharkhand_state_gap():
    missing = missing_required_authorities(
        required_sources=[
            "state-specific witch-hunting statute must be verified for the user's state before state-law offence details are given"
        ],
        passages=[
            {
                "index": 1,
                "title": "Jharkhand State Legal Services Authority Dayan Pratha Pratishedh Adhiniyam 2001",
                "anchor": "jhalsa-dayan-pratha-pratishedh-2001/sec-4",
                "source_type": "official_guidance",
            }
        ],
        query="village ojha branded my mother daayan stripped her in public ranchi",
    )

    assert missing == []


def test_jharkhand_witch_judgment_does_not_satisfy_state_gap():
    missing = missing_required_authorities(
        required_sources=[
            "state-specific witch-hunting statute must be verified for the user's state before state-law offence details are given"
        ],
        passages=[
            {
                "index": 1,
                "title": "Jharkhand witch daain criminal case",
                "anchor": "2024-jharkhand-witch-case#para-7",
                "source_type": "hc_judgment",
            }
        ],
        query="neighbours calling me witch want to throw me out of village chaibasa",
    )

    assert missing
    assert missing[0]["kind"] == "state_or_local_authority_gap"


def test_income_tax_1432_gap_requires_section_143_not_adjacent_assessment_sections():
    missing = missing_required_authorities(
        required_sources=["Income Tax Act 1961 section 143(2) scrutiny-assessment notice source"],
        passages=[
            {
                "index": 1,
                "title": "Income-tax Act 1961",
                "anchor": "income-tax-1961/sec-142",
                "source_type": "bare_act",
            },
            {
                "index": 2,
                "title": "Income-tax Act 1961",
                "anchor": "income-tax-1961/sec-144",
                "source_type": "bare_act",
            },
        ],
        query="got income tax notice under section 143(2) how much time to respond",
    )

    assert missing
    assert missing[0]["kind"] == "national_tax_source_gap"


def test_stage_b_source_gap_false_negatives_accept_present_sources():
    assert missing_required_authorities(
        required_sources=["Dowry Prohibition Act 1961 or civil recovery route where gifts, dowry, or wedding expenses are disputed"],
        passages=[{"index": 1, "title": "Dowry Prohibition Act 1961", "anchor": "dowry-prohibition-1961/sec-2"}],
        query="fiance hid HIV status can I cancel wedding without dowry return issue",
    ) == []

    assert missing_required_authorities(
        required_sources=["Clinical Establishments Act / state clinical-establishment rules where hospital records, billing, or standards are involved"],
        passages=[{"index": 1, "title": "Clinical Establishments (Registration and Regulation) Act 2010", "anchor": "clinical-establishments-2010/sec-12"}],
        query="private hospital in noida overcharged ICU bill",
    ) == []

    assert missing_required_authorities(
        required_sources=["Representation of the People Act 1950 / election rules where voter-list correction or denial of vote is involved"],
        passages=[{"index": 1, "title": "Representation of the People Act 1950", "anchor": "rpa-1950/sec-23-a@2021-01-01"}],
        query="voter id name spelt wrong booth officer denied me vote",
    ) == []

    assert missing_required_authorities(
        required_sources=["BNSS/CrPC bail and arrest safeguards where relevant"],
        passages=[{"index": 1, "title": "Bharatiya Nagarik Suraksha Sanhita 2023", "anchor": "bnss-2023/sec-483@2024-07-01"}],
        query="pmla case ED filed twin condition how to argue not guilty",
    ) == []

    assert missing_required_authorities(
        required_sources=["Insurance Ombudsman Rules / insurer grievance procedure"],
        passages=[{"index": 3, "title": "Insurance Ombudsman Rules 2017", "anchor": "insurance-ombudsman-rules-2017/sec-5-h"}],
        query="insurer is rejecting my claim",
    ) == []


def test_stage_b_source_gap_skips_non_applicable_conditionals():
    assert missing_required_authorities(
        required_sources=["Information Technology Act 2000 where platform messages, DMs, or online accounts are involved"],
        passages=[],
        query="ex boyfriend follows my scooty everyday from office to home he does not talk just follows",
    ) == []

    assert missing_required_authorities(
        required_sources=["Indian Succession Act 1925 where applicable"],
        passages=[],
        query="i am 70 yr widow muslim son says wife and daughter cant inherit from his father what is sunni law",
    ) == []

    assert missing_required_authorities(
        required_sources=["Juvenile Justice Act 2015 and adoption regulations where adoption papers are missing"],
        passages=[],
        query="ex husband took our son to UK on tourist visa and is not bringing back",
    ) == []

    assert missing_required_authorities(
        required_sources=["Juvenile Justice Act 2015 and adoption regulations where adoption papers are missing"],
        passages=[],
        query="child passport papers are stuck with father for travel",
    ) == []

    assert missing_required_authorities(
        required_sources=["Juvenile Justice Act 2015 and adoption regulations where adoption papers are missing"],
        passages=[],
        query="school papers for my son are not released by principal",
    ) == []


def test_stage_b_source_gap_accepts_jj_adoption_sections_but_not_bail_for_arrest():
    assert missing_required_authorities(
        required_sources=["Juvenile Justice Act 2015 and adoption regulations where adoption papers are missing"],
        passages=[{"index": 1, "title": "Juvenile Justice (Care and Protection of Children) Act 2015", "anchor": "jj-2015/sec-56"}],
        query="we adopted child from sister but no papers now real parents want him back",
    ) == []

    assert missing_required_authorities(
        required_sources=["Juvenile Justice Act 2015 and adoption regulations where adoption papers are missing"],
        passages=[{"index": 1, "title": "Juvenile Justice (Care and Protection of Children) Act 2015", "anchor": "jj-2015/sec-56"}],
        query="we are adopting child from sister no papers now real parents object custody",
    ) == []

    assert missing_required_authorities(
        required_sources=["Juvenile Justice Act 2015 and adoption regulations where adoption papers are missing"],
        passages=[],
        query="we are adopting child from sister no papers now real parents object custody",
    ) == [
        {
            "required_source": "Juvenile Justice Act 2015 and adoption regulations where adoption papers are missing",
            "kind": "national_statute_retrieval_gap",
        }
    ]

    arrest_gap = missing_required_authorities(
        required_sources=["BNSS/CrPC bail and arrest safeguards where relevant"],
        passages=[{"index": 1, "title": "Bharatiya Nagarik Suraksha Sanhita 2023", "anchor": "bnss-2023/sec-480"}],
        query="police arrested my son last night and did not produce him in 24 hours",
    )
    assert arrest_gap == [
        {
            "required_source": "BNSS/CrPC bail and arrest safeguards where relevant",
            "kind": "national_criminal_source_gap",
        }
    ]


def test_early_refusal_source_gap_event_can_be_built_without_retrieved_passages():
    route = MatterRoute(
        category="criminal_defence_bail",
        label="Bail / criminal defence",
        confidence=0.8,
        urgency="high",
        required_sources=["BNSS 2023 / CrPC 1973 bail provisions based on incident date"],
        forums=["criminal court"],
        missing_facts=["incident date"],
        red_flags=[],
    )

    event = _source_gap_event_for_retrieved(
        query="brother arrested six months no chargesheet can bail be filed",
        route=route,
        retrieved=[],
        top_k=8,
    )

    assert event is not None
    assert event["has_gap"] is True
    assert event["gap_kinds"] == ["national_criminal_source_gap"]


def test_critical_route_guard_requires_reviewed_primary_contract():
    route = MatterRoute(
        category="police_fir",
        label="FIR / police inaction",
        confidence=0.8,
        urgency="high",
        required_sources=[],
        forums=["police station"],
        missing_facts=[],
        red_flags=[],
    )

    assert _critical_route_needs_reviewed_contract(route, None) is True
    assert _critical_route_needs_reviewed_contract(
        route,
        WorkflowTemplateResult(
            id="legacy_like_merge",
            source="common_workflow_contracts",
            lines=["line [1]"],
            answer_mode="merge",
        ),
    ) is True
    assert _critical_route_needs_reviewed_contract(
        route,
        WorkflowTemplateResult(
            id="reviewed_police_path",
            source="common_workflow_contracts",
            lines=["line [1]"],
            answer_mode="safety_primary",
        ),
    ) is False


def test_bonded_labour_rescue_is_launch_critical():
    route = MatterRoute(
        category="bonded_labour_rescue",
        label="Bonded labour / forced labour rescue",
        confidence=0.84,
        urgency="emergency",
        required_sources=[],
        forums=["District Magistrate"],
        missing_facts=[],
        red_flags=[],
    )

    assert _critical_route_needs_reviewed_contract(route, None) is True


def test_stage_c_conditional_criminal_sources_do_not_overfire_for_procedure_only_queries():
    required = [
        "BNSS 2023 / CrPC 1973 bail provisions based on incident date",
        "BNS 2023 / IPC 1860 offence provisions where relevant",
    ]

    procedure_only = missing_required_authorities(
        required_sources=required,
        passages=[],
        query="urgent what documents needed for anticipatory bail application in sessions court",
    )
    procedure_only_texts = {item["required_source"] for item in procedure_only}
    assert "BNSS 2023 / CrPC 1973 bail provisions based on incident date" in procedure_only_texts
    assert "BNS 2023 / IPC 1860 offence provisions where relevant" not in procedure_only_texts

    offence_facts = missing_required_authorities(
        required_sources=required,
        passages=[],
        query="my son 19 first time offender 379 theft how to get bail magistrate court",
    )
    offence_texts = {item["required_source"] for item in offence_facts}
    assert "BNSS 2023 / CrPC 1973 bail provisions based on incident date" in offence_texts
    assert "BNS 2023 / IPC 1860 offence provisions where relevant" in offence_texts


def test_stage_c_conditional_posh_bns_and_limitation_only_fire_on_matching_facts():
    posh_required = [
        "Sexual Harassment of Women at Workplace Act 2013",
        "BNS 2023 / IPC 1860 provisions where physical assault, stalking, or threats are involved",
    ]

    pip_only = missing_required_authorities(
        required_sources=posh_required,
        passages=[],
        query="after I complained to ICC against manager he gave bad rating and PIP",
    )
    pip_texts = {item["required_source"] for item in pip_only}
    assert "Sexual Harassment of Women at Workplace Act 2013" in pip_texts
    assert "BNS 2023 / IPC 1860 provisions where physical assault, stalking, or threats are involved" not in pip_texts

    touched = missing_required_authorities(
        required_sources=posh_required,
        passages=[],
        query="boss touched my back in office and now threatening me after complaint",
    )
    touched_texts = {item["required_source"] for item in touched}
    assert "BNS 2023 / IPC 1860 provisions where physical assault, stalking, or threats are involved" in touched_texts

    assert missing_required_authorities(
        required_sources=["Limitation Act 1963 where needed"],
        passages=[],
        query="father made gift deed before death now daughter wants share is gift valid",
    ) == []
    limitation = missing_required_authorities(
        required_sources=["Limitation Act 1963 where needed"],
        passages=[],
        query="tribunal order came 120 days ago can I still appeal delay condonation",
    )
    assert {item["required_source"] for item in limitation} == {"Limitation Act 1963 where needed"}


def test_stage_c_pesa_fra_requirement_is_fact_triggered():
    required = ["PESA Act / Forest Rights Act where Scheduled Area or forest-rights facts apply"]

    assert missing_required_authorities(
        required_sources=required,
        passages=[],
        query="ordinary property boundary dispute in city apartment",
    ) == []
    assert missing_required_authorities(
        required_sources=required,
        passages=[],
        query="mob attacked our pahan during sarna puja calling adivasi non hindu jharkhand",
    ) == []
    forest_gap = missing_required_authorities(
        required_sources=required,
        passages=[],
        query="forest guard stopped us collecting bamboo and tendu leaves from our village forest",
    )
    assert {item["required_source"] for item in forest_gap} == set(required)
    gram_sabha_gap = missing_required_authorities(
        required_sources=required,
        passages=[],
        query="bauxite mining NOC given without gram sabha resolution in scheduled area",
    )
    assert {item["required_source"] for item in gram_sabha_gap} == set(required)


def test_stage_c_expands_launch_critical_guard_routes():
    for category in (
        "cyber_fraud_or_harassment",
        "workplace_sexual_harassment",
        "child_custody_adoption",
        "sexual_offence_survivor",
        "reproductive_rights_mtp",
        "child_marriage_protection",
        "criminal_procedure_notice",
        "manual_scavenging_safety",
        "custody_compensation",
        "pmla_ed",
        "business_contract_partnership",
        "digital_platform_account",
    ):
        route = MatterRoute(
            category=category,
            label=category,
            confidence=0.8,
            urgency="high",
            required_sources=[],
            forums=[],
            missing_facts=[],
            red_flags=[],
        )
        assert _critical_route_needs_reviewed_contract(route, None) is True


def test_stage_c_bns_ipc_source_matching_is_section_family_aware():
    wrong_bns = [
        {
            "index": 1,
            "title": "Bharatiya Nyaya Sanhita 2023",
            "anchor": "bns-2023/sec-356",
            "source_type": "bare_act",
        }
    ]
    hurt_required = ["BNS 2023 / IPC 1860 provisions where physical assault, stalking, or threats are involved"]
    hurt_gap = missing_required_authorities(
        required_sources=hurt_required,
        passages=wrong_bns,
        query="boss touched my back and threatened me after complaint",
    )
    assert {item["required_source"] for item in hurt_gap} == set(hurt_required)

    hurt_found = missing_required_authorities(
        required_sources=hurt_required,
        passages=[
            {
                "index": 1,
                "title": "Bharatiya Nyaya Sanhita 2023",
                "anchor": "bns-2023/sec-74",
                "source_type": "bare_act",
            }
        ],
        query="boss touched my back and threatened me after complaint",
    )
    assert hurt_found == []

    acid_required = ["BNS 2023 / IPC 1860 acid attack offence source based on incident date"]
    acid_gap = missing_required_authorities(
        required_sources=acid_required,
        passages=wrong_bns,
        query="auto driver threw acid on my face what FIR section applies",
    )
    assert {item["required_source"] for item in acid_gap} == set(acid_required)


def test_stage_c_composite_dual_regime_requires_matching_offence_section_family():
    required = ["BNS/BNSS or IPC/CrPC based on incident date"]
    wrong_bns_with_procedure = [
        {
            "index": 1,
            "title": "Bharatiya Nyaya Sanhita 2023",
            "anchor": "bns-2023/sec-356",
            "source_type": "bare_act",
        },
        {
            "index": 2,
            "title": "Bharatiya Nagarik Suraksha Sanhita 2023",
            "anchor": "bnss-2023/sec-173",
            "source_type": "bare_act",
        },
    ]

    missing = missing_required_authorities(
        required_sources=required,
        passages=wrong_bns_with_procedure,
        query="auto driver threw acid on my face what FIR section applies",
    )
    assert {item["required_source"] for item in missing} == set(required)

    found = missing_required_authorities(
        required_sources=required,
        passages=[
            {
                "index": 1,
                "title": "Bharatiya Nyaya Sanhita 2023",
                "anchor": "bns-2023/sec-124",
                "source_type": "bare_act",
            },
            {
                "index": 2,
                "title": "Bharatiya Nagarik Suraksha Sanhita 2023",
                "anchor": "bnss-2023/sec-173",
                "source_type": "bare_act",
            },
        ],
        query="auto driver threw acid on my face what FIR section applies",
    )
    assert found == []


def test_stage_e7_family_conditional_criminal_sources_require_separate_criminal_lane():
    dv_notice_required = [
        "BNSS/CrPC and BNS/IPC only where a separate FIR, arrest notice, or criminal complaint exists"
    ]

    no_criminal_lane = missing_required_authorities(
        required_sources=dv_notice_required,
        passages=[],
        query="wife filed false domestic violence case, i have notice what do i reply",
    )
    assert no_criminal_lane == []

    explicit_no_fir_notice = missing_required_authorities(
        required_sources=dv_notice_required,
        passages=[],
        query="wife filed domestic violence case, no FIR just notice reply",
    )
    assert explicit_no_fir_notice == []

    separate_fir = missing_required_authorities(
        required_sources=dv_notice_required,
        passages=[],
        query="wife filed domestic violence case and separate FIR under 498A, police sent arrest notice",
    )
    assert {item["required_source"] for item in separate_fir} == set(dv_notice_required)

    forced_sex_safety_required = [
        "BNS 2023 / IPC 1860 sexual-offence provisions and marital-exception limits only where a separate FIR, arrest notice, or criminal complaint exists"
    ]
    safety_first = missing_required_authorities(
        required_sources=forced_sex_safety_required,
        passages=[],
        query="husband forced sex even when i say no",
    )
    assert safety_first == []

    fir_lane = missing_required_authorities(
        required_sources=forced_sex_safety_required,
        passages=[],
        query="husband forced sex even when i say no and police filed FIR",
    )
    assert {item["required_source"] for item in fir_lane} == set(forced_sex_safety_required)


def test_stage_e7_hindu_marriage_section_13_match_is_exact_not_13b():
    required = [
        "Hindu Marriage Act 1955 section 13 or applicable personal/Special Marriage Act divorce ground"
    ]
    mutual_consent_only = missing_required_authorities(
        required_sources=required,
        passages=[
            {
                "index": 1,
                "title": "Hindu Marriage Act 1955",
                "anchor": "hindu-marriage-1955/sec-13-b",
                "source_type": "bare_act",
            }
        ],
        query="i caught my husband with another woman having sex",
    )
    assert {item["required_source"] for item in mutual_consent_only} == set(required)

    divorce_ground_fragment = missing_required_authorities(
        required_sources=required,
        passages=[
            {
                "index": 1,
                "title": "Hindu Marriage Act 1955",
                "anchor": "hindu-marriage-1955/sec-13-a",
                "source_type": "bare_act",
            }
        ],
        query="i caught my husband with another woman having sex",
    )
    assert divorce_ground_fragment == []

    divorce_ground = missing_required_authorities(
        required_sources=required,
        passages=[
            {
                "index": 1,
                "title": "Hindu Marriage Act 1955",
                "anchor": "hindu-marriage-1955/sec-13",
                "source_type": "bare_act",
            }
        ],
        query="i caught my husband with another woman having sex",
    )
    assert divorce_ground == []


def test_stage_e7_marriage_misrepresentation_enforces_voidable_and_family_court_sources():
    query = "i am hindu my husband is gay and hidden before marriage what can i do"
    route = route_matter(query)
    assert route.category == "family_marriage_status"

    missing = missing_required_authorities(
        required_sources=route.required_sources,
        passages=[],
        query=query,
    )
    missing_sources = {item["required_source"] for item in missing}
    assert any("Hindu Marriage Act" in source and "Special Marriage Act" in source for source in missing_sources)
    assert any("Family Courts Act" in source for source in missing_sources)

    covered = missing_required_authorities(
        required_sources=route.required_sources,
        passages=[
            {
                "index": 1,
                "title": "Hindu Marriage Act 1955",
                "anchor": "hindu-marriage-1955/sec-12",
                "source_type": "bare_act",
            },
            {
                "index": 2,
                "title": "Family Courts Act 1984",
                "anchor": "family-courts-1984/sec-7",
                "source_type": "bare_act",
            },
        ],
        query=query,
    )
    assert not any("Hindu Marriage Act" in item["required_source"] for item in covered)
    assert not any("Family Courts Act" in item["required_source"] for item in covered)


def test_stage_e7_domestic_residence_negated_assault_does_not_force_criminal_sources():
    query = "husband throws me out but house in mother in law name no assault no threat"
    route = route_matter(query)
    assert route.label == "Domestic violence / right to residence"

    missing = missing_required_authorities(
        required_sources=route.required_sources,
        passages=[],
        query=query,
    )
    missing_sources = {item["required_source"] for item in missing}
    assert any("PWDVA 2005" in source for source in missing_sources)
    assert not any("BNS 2023" in source or "IPC 1860" in source for source in missing_sources)
    assert not any("BNSS 2023" in source or "CrPC 1973" in source for source in missing_sources)


def test_stage_e7_spousal_property_return_requires_neutral_family_court_source():
    query = "my wife took my gold and left house"
    route = route_matter(query)
    assert route.label == "Spousal jewellery / property return"

    missing = missing_required_authorities(
        required_sources=route.required_sources,
        passages=[],
        query=query,
    )
    missing_sources = {item["required_source"] for item in missing}
    assert any("Family Courts Act 1984" in source for source in missing_sources)

    covered = missing_required_authorities(
        required_sources=route.required_sources,
        passages=[
            {
                "index": 1,
                "title": "Family Courts Act 1984",
                "anchor": "family-courts-1984/sec-7",
                "source_type": "bare_act",
            },
        ],
        query=query,
    )
    assert not any("Family Courts Act 1984" in item["required_source"] for item in covered)


def test_stage_e7_bns67_satisfies_marital_sexual_offence_conditional_gap():
    required = [
        "BNS 2023 / IPC 1860 sexual-offence provisions and marital-exception limits only where a separate FIR, arrest notice, or criminal complaint exists"
    ]

    missing = missing_required_authorities(
        required_sources=required,
        passages=[
            {
                "index": 1,
                "title": "Bharatiya Nyaya Sanhita 2023",
                "anchor": "bns-2023/sec-67@2024-07-01",
                "source_type": "bare_act",
            },
        ],
        query="my husband forced sex even when i say no and police filed FIR",
    )

    assert missing == []


def test_stage_e7_domestic_threat_dual_procedure_source_is_satisfied_by_bnss_and_crpc():
    query = "husband locked me out of shared house and threatens me if I come back"
    route = route_matter(query)
    assert route.label == "Domestic violence / right to residence"

    missing = missing_required_authorities(
        required_sources=route.required_sources,
        passages=[
            {
                "index": 1,
                "title": "Bharatiya Nyaya Sanhita 2023",
                "anchor": "bns-2023/sec-351@2024-07-01",
                "source_type": "bare_act",
            },
            {
                "index": 2,
                "title": "Bharatiya Nagarik Suraksha Sanhita 2023",
                "anchor": "bnss-2023/sec-173-b@2024-07-01",
                "source_type": "bare_act",
            },
            {
                "index": 3,
                "title": "Code of Criminal Procedure 1973",
                "anchor": "crpc-1973/sec-154",
                "source_type": "bare_act",
            },
            {
                "index": 4,
                "title": "Protection of Women from Domestic Violence Act 2005",
                "anchor": "domestic-violence-2005/sec-19",
                "source_type": "bare_act",
            },
        ],
        query=query,
    )

    assert not any(
        "BNSS 2023" in item["required_source"] and "CrPC 1973" in item["required_source"]
        for item in missing
    )


def test_stage_e7_family_police_refusal_enforces_bnss_crpc_but_no_police_does_not():
    query = "husband forced sex even when i say no and police refused complaint"
    route = route_matter(query)
    assert route.label == "Marital sexual violence / domestic safety"

    missing = missing_required_authorities(
        required_sources=route.required_sources,
        passages=[],
        query=query,
    )
    missing_sources = {item["required_source"] for item in missing}
    assert any("PWDVA 2005" in source for source in missing_sources)
    assert any("BNSS 2023" in source and "CrPC 1973" in source for source in missing_sources)

    safety_only = "husband forced sex even when i say no no police no FIR"
    safety_route = route_matter(safety_only)
    safety_missing = missing_required_authorities(
        required_sources=safety_route.required_sources,
        passages=[],
        query=safety_only,
    )
    safety_sources = {item["required_source"] for item in safety_missing}
    assert any("PWDVA 2005" in source for source in safety_sources)
    assert not any("BNSS 2023" in source or "CrPC 1973" in source for source in safety_sources)


def test_stage_e7_bns_breach_of_trust_subanchors_satisfy_streedhan_source():
    required = [
        "BNS 2023 / IPC 1860 criminal breach of trust, cheating, or theft provisions based on incident date"
    ]

    found = missing_required_authorities(
        required_sources=required,
        passages=[
            {
                "index": 1,
                "title": "Bharatiya Nyaya Sanhita 2023",
                "anchor": "bns-2023/sec-316-c",
                "source_type": "bare_act",
            }
        ],
        query="in laws not returning my jewellery",
    )
    assert found == []

    wrong_offence = missing_required_authorities(
        required_sources=required,
        passages=[
            {
                "index": 1,
                "title": "Bharatiya Nyaya Sanhita 2023",
                "anchor": "bns-2023/sec-356",
                "source_type": "bare_act",
            }
        ],
        query="in laws not returning my jewellery",
    )
    assert {item["required_source"] for item in wrong_offence} == set(required)


def test_stage_e9_itpa_raid_accepts_bns_exploitation_subanchors():
    required = [
        "BNS 2023 / IPC 1860 trafficking or exploitation provisions based on incident date"
    ]

    missing = missing_required_authorities(
        required_sources=required,
        passages=[
            {
                "index": 1,
                "title": "Bharatiya Nyaya Sanhita 2023",
                "anchor": "bns-2023/sec-144@2024-07-01",
                "source_type": "bare_act",
            },
            {
                "index": 2,
                "title": "Bharatiya Nyaya Sanhita 2023",
                "anchor": "bns-2023/sec-146@2024-07-01",
                "source_type": "bare_act",
            },
        ],
        query=(
            "hi, the spa was raided last week and police took me and other girls "
            "to station I just do massage I am scared what will happen now can i file case"
        ),
    )

    assert missing == []


def test_stage_e9_child_deepfake_accepts_pocso_and_it_privacy_sources():
    required = [
        "POCSO Act 2012 where a child or minor is shown in sexual content",
        "Information Technology Act 2000 section 67B / 66E / 67A where electronic sexual-image publication or privacy misuse is alleged",
    ]

    missing = missing_required_authorities(
        required_sources=required,
        passages=[
            {
                "index": 1,
                "title": "Protection of Children from Sexual Offences Act 2012",
                "anchor": "pocso-2012/sec-13-a",
                "source_type": "bare_act",
            },
            {
                "index": 2,
                "title": "Information Technology Act 2000",
                "anchor": "it-2000/sec-66E",
                "source_type": "bare_act",
            },
        ],
        query=(
            "hi, my schoolmate is making deepfake nude videos of girls in class "
            "using AI n circulating I am one of them I am 15 can i file case"
        ),
    )

    assert missing == []


def test_stage_e9_scst_rule7_source_satisfies_runtime_gap():
    missing = missing_required_authorities(
        required_sources=[
            "SC/ST (Prevention of Atrocities) Rules 1995 Rule 7 DSP-rank investigating-officer requirement"
        ],
        passages=[
            {
                "index": 1,
                "title": "Scheduled Castes and Scheduled Tribes (Prevention of Atrocities) Rules 1995",
                "anchor": "sc-st-poa-rules-1995/rule-7",
                "source_type": "bare_act",
            }
        ],
        query=(
            "pls tell SP not transferring my atrocity case to DSP though POA Act "
            "says so vidarbha need lawyer or police"
        ),
    )

    assert missing == []


def test_stage_e9_whatsapp_hack_requires_matching_bns_bnss_pair():
    required = ["BNS/BNSS or IPC/CrPC based on incident date"]
    query = "sir my whatsapp account got hacked and someone is asking my contacts fr money in my name where to go"

    missing = missing_required_authorities(
        required_sources=required,
        passages=[
            {
                "index": 1,
                "title": "Bharatiya Nyaya Sanhita 2023",
                "anchor": "bns-2023/sec-319@2024-07-01",
                "source_type": "bare_act",
            },
            {
                "index": 2,
                "title": "Bharatiya Nagarik Suraksha Sanhita 2023",
                "anchor": "bnss-2023/sec-173-b@2024-07-01",
                "source_type": "bare_act",
            },
        ],
        query=query,
    )

    assert missing == []


def test_stage_e9b_false_dacoity_accepts_bns_dacoity_anchor():
    missing = missing_required_authorities(
        required_sources=[
            "BNS 2023 / IPC 1860 dacoity, theft, and false-case provisions based on incident date"
        ],
        passages=[
            {
                "index": 1,
                "title": "Bharatiya Nyaya Sanhita 2023",
                "anchor": "bns-2023/sec-310@2024-07-01",
                "source_type": "bare_act",
            }
        ],
        query=(
            "pls tell false dacoity case lodged on my brother by forest guard "
            "for collecting tendu leaves dindori need lawyer or police"
        ),
    )

    assert missing == []


def test_stage_e9b_forest_produce_dacoity_accepts_live_fra_bns_bnss_sources():
    missing = missing_required_authorities(
        required_sources=[
            "PESA Act / Forest Rights Act where Scheduled Area or forest-rights facts apply",
            "BNS/BNSS or IPC/CrPC based on incident date",
        ],
        passages=[
            {
                "index": 1,
                "title": "Bharatiya Nyaya Sanhita 2023",
                "anchor": "bns-2023/sec-309@2024-07-01",
                "source_type": "bare_act",
            },
            {
                "index": 2,
                "title": "Bharatiya Nagarik Suraksha Sanhita 2023",
                "anchor": "bnss-2023/sec-173-b@2024-07-01",
                "source_type": "bare_act",
            },
            {
                "index": 3,
                "title": "Scheduled Tribes and Other Traditional Forest Dwellers (Recognition of Forest Rights) Act 2006",
                "anchor": "fra-2006/sec-5-a@2007-01-01",
                "source_type": "bare_act",
            },
        ],
        query="urgent gaon people took tendu leaves by force 8 men with lathi forest produce dacoity or theft what to do",
    )

    assert missing == []


def test_stage_e9b_chargesheet_tweet_accepts_bnss_police_report_anchor():
    missing = missing_required_authorities(
        required_sources=[
            "BNSS 2023 / CrPC 1973 charge-sheet, summons, bail, discharge, and court procedure based on incident date"
        ],
        passages=[
            {
                "index": 1,
                "title": "Bharatiya Nagarik Suraksha Sanhita 2023",
                "anchor": "bnss-2023/sec-193-a@2024-07-01",
                "source_type": "bare_act",
            }
        ],
        query="can u tell delhi police chargesheet fr tweet calling cm corrupt is this 356 case what can i do",
    )

    assert missing == []


def test_stage_e9b_bocw_factories_requirement_accepts_worksite_safety_sources():
    required = ["BOCW Act 1996 / Factories Act 1948 where applicable"]

    assert missing_required_authorities(
        required_sources=required,
        passages=[
            {
                "index": 1,
                "title": "Building and Other Construction Workers (Regulation of Employment and Conditions of Service) Act 1996",
                "anchor": "bocw-1996/sec-39__2@1996-01-01",
                "source_type": "bare_act",
            }
        ],
        query="hi, fell from 5th floor site whitefield bangalore leg broken thekedar saying no insurance no bocw card can i file case",
    ) == []

    assert missing_required_authorities(
        required_sources=required,
        passages=[
            {
                "index": 1,
                "title": "Factories Act 1948",
                "anchor": "factories-1948/sec-111",
                "source_type": "bare_act",
            }
        ],
        query="please help morbi ceramic factory boiler burst friend dead his family bihar nothing got 6 mnths over any remedy",
    ) == []


def test_stage_e9b_bocw_card_does_not_force_unalleged_cess_or_criminal_sources():
    missing = missing_required_authorities(
        required_sources=[
            "BOCW Cess Act / state welfare-board cess records where cess collection or fake registers are alleged",
            "BNS/BNSS or IPC/CrPC where cheating, forgery, or false registers are alleged",
        ],
        passages=[],
        query="please help how to get bocw card mumbai i work construction 8 years no card no benefit any remedy",
    )

    assert missing == []


def test_stage_e9b_assam_witch_hunting_full_source_satisfies_state_gap():
    missing = missing_required_authorities(
        required_sources=[
            "state-specific witch-hunting statute must be verified for the user's state before state-law offence details are given"
        ],
        passages=[
            {
                "index": 1,
                "title": "Assam Witch Hunting (Prohibition, Prevention and Protection) Act 2015",
                "anchor": "assam-witch-hunting-2015/full",
                "source_type": "bare_act",
            }
        ],
        query="can u tell my saas labelled daayan and beaten by village people assam barpeta what can i do",
    )

    assert missing == []


def test_assam_witch_hunting_hc_judgment_does_not_substitute_for_state_act():
    missing = missing_required_authorities(
        required_sources=[
            "state-specific witch-hunting statute must be verified for the user's state before state-law offence details are given"
        ],
        passages=[
            {
                "index": 1,
                "title": "Gauhati High Court judgment on witch-hunting",
                "anchor": "assam-witch-hunting-2015/sec-4@2020-01-01",
                "source_type": "hc_judgment",
            }
        ],
        query="can u tell my saas labelled daayan and beaten by village people assam barpeta what can i do",
    )

    assert missing and missing[0]["kind"] == "state_or_local_authority_gap"


def test_cheque_procedure_is_not_cleared_by_ni_act_passage_alone():
    query = "cheque bounced today insufficient funds"
    route = route_matter(query)

    missing = missing_required_authorities(
        required_sources=route.required_sources,
        passages=[
            {
                "index": 1,
                "title": "Negotiable Instruments Act 1881",
                "anchor": "negotiable-instruments-1881/sec-138",
                "source_type": "bare_act",
            }
        ],
        query=query,
    )

    assert any("BNSS 2023 / CrPC 1973" in item["required_source"] for item in missing)


def test_unknown_date_cheque_does_not_pass_with_complete_ni_act_only():
    query = "my customer gave me a cheque and it bounced, what is the deadline to send notice"
    route = route_matter(query)
    plan = build_matter_plan(query, route)
    assert plan is not None
    assert matter_plan_integrity_gap(plan, query) is None
    passages = [
        {
            "index": 1,
            "title": "Negotiable Instruments Act 1881",
            "anchor": "negotiable-instruments-1881/sec-138",
            "source_type": "bare_act",
            "required_source_pack": "ni_act_1881",
            "document_id": "negotiable-instruments-1881",
            "authority_ids": ["authority_c328bcf9ab7294324780"],
        },
        {
            "index": 2,
            "title": "Negotiable Instruments Act 1881",
            "anchor": "negotiable-instruments-1881/sec-142",
            "source_type": "bare_act",
            "required_source_pack": "ni_act_1881",
            "document_id": "negotiable-instruments-1881",
            "authority_ids": ["authority_5bcd6df2cde8aab018df2"],
        },
    ]

    event = build_source_gap_event(
        query=query,
        route_category=route.category,
        required_sources=route.required_sources,
        passages=passages,
        plan=plan,
        legal_regime=route.legal_regime,
    )

    assert event is not None
    assert event["safe_handoff_only"] is True
    assert any("complaint procedure" in item["required_source"].lower() for item in event["missing_required_sources"])


def test_stage_state_witch_accused_route_fails_closed_without_named_state_authority():
    query = "police filed a witch case against me in Jharkhand"
    route = route_matter(query)
    plan = build_matter_plan(query, route)
    assert plan is not None
    event = build_source_gap_event(
        query=query,
        route_category=route.category,
        required_sources=route.required_sources,
        passages=[],
        legal_regime=route.legal_regime,
        plan=plan,
    )
    assert event is not None
    assert "state_or_local_authority_gap" in event["gap_kinds"]


def test_stage_material_state_rera_and_wage_routes_do_not_hide_local_source_gaps():
    assert should_enforce_required_source(
        "state RERA rules and filing procedure once the state and project are identified",
        query="builder delayed possession in Gujarat and I want to file RERA complaint",
    )
    assert not should_enforce_required_source(
        "state RERA rules and filing procedure once the state and project are identified",
        query="builder delayed possession and I have not told you the state yet",
    )
    assert should_enforce_required_source(
        "state labour-department notification/appeal route for wage rates",
        query="minimum wage notification for unskilled workers in Gujarat",
    )


def test_stage_national_passages_cannot_clear_named_state_rera_gap():
    query = "builder delayed possession in Gujarat and I want to file RERA complaint"
    route = route_matter(query)
    plan = build_matter_plan(query, route)
    assert plan is not None
    event = build_source_gap_event(
        query=query,
        route_category=route.category,
        required_sources=route.required_sources,
        passages=[
            {
                "index": 1,
                "title": "Real Estate (Regulation and Development) Act 2016",
                "anchor": "rera-2016/sec-31",
                "source_type": "bare_act",
                "required_source_pack": "rera_2016",
                "document_id": "rera-2016",
                "text": "Section 31 complaint.",
            },
            {
                "index": 2,
                "title": "Consumer Protection Act 2019",
                "anchor": "consumer-protection-2019/sec-35",
                "source_type": "bare_act",
                "required_source_pack": "consumer_protection_2019",
                "document_id": "consumer-protection-2019",
                "text": "Section 35 complaint.",
            },
        ],
        legal_regime=route.legal_regime,
        plan=plan,
    )
    assert event is not None
    assert any(
        item["required_source"].startswith("state RERA rules")
        for item in event["missing_required_sources"]
    )


def test_common_kochi_location_activates_named_state_rera_gap():
    query = "builder delayed possession in Kochi and I want to file RERA complaint"

    assert should_enforce_required_source(
        "state RERA rules and filing procedure once the state and project are identified",
        query=query,
    )


def test_named_state_minimum_wage_claim_needs_state_rate_source():
    query = "employer paying below minimum wage in Kerala"
    route = route_matter(query)
    assert any("state labour-department notification" in source for source in route.required_sources)

    missing = missing_required_authorities(
        required_sources=route.required_sources,
        passages=[
            {
                "index": 1,
                "title": "Code on Wages 2019",
                "anchor": "code-on-wages-2019/sec-17@2019-01-01",
                "source_type": "bare_act",
            }
        ],
        query=query,
    )

    assert any("state labour-department notification" in item["required_source"] for item in missing)


def test_stage_intake_precondition_is_not_a_citable_esi_authority():
    query = "ESI inspector notice says short contribution for casual workers how to contest"
    route = route_matter(query)
    plan = build_matter_plan(query, route)
    assert plan is not None
    entry = next(
        entry for entry in plan.authority_ledger
        if entry.source.startswith("labour authority / ESI Court procedure")
    )
    assert entry.note == "intake_precondition"
    assert not is_active_plan_authority_entry(entry, plan=plan, query=query)


def test_surrogacy_section_passage_clears_provisional_plan_identity_gate():
    query = "clinic says my wife had hysterectomy but can we use surrogacy in Gujarat"
    route = route_matter(query)
    plan = build_matter_plan(query, route)
    assert plan is not None
    entry = next(entry for entry in plan.authority_ledger if entry.source == "Surrogacy (Regulation) Act 2021")

    passage = {
        "index": 1,
        "title": "Surrogacy (Regulation) Act 2021",
        "anchor": "surrogacy-2021/sec-4@2021-01-01",
        "source_type": "bare_act",
        "required_source_pack": "surrogacy_2021",
        "document_id": "surrogacy-2021",
        "text": "Section 4 eligibility for an intending couple where the wife has no uterus.",
    }

    assert _passage_satisfies_plan_entry(plan, entry, passage)


def test_stage_e9b_assam_witch_violence_accepts_bns_hurt_and_bnss_fir_pair():
    missing = missing_required_authorities(
        required_sources=["BNS/BNSS or IPC/CrPC based on incident date"],
        passages=[
            {
                "index": 1,
                "title": "Bharatiya Nagarik Suraksha Sanhita 2023",
                "anchor": "bnss-2023/sec-173-b@2024-07-01",
                "source_type": "bare_act",
            },
            {
                "index": 2,
                "title": "Bharatiya Nyaya Sanhita 2023",
                "anchor": "bns-2023/sec-117@2024-07-01",
                "source_type": "bare_act",
            },
        ],
        query="barpeta assam village called my aunt daayan beat her and threatened witch hunting what case can file",
    )

    assert missing == []


def test_stage_e9e_source_gap_enforces_indexed_tribunal_procedure_requirements():
    required_sources = [
        "NCLAT rules, forms, fees, certified-copy and limitation facts",
        "NCLT Rules / IBC application forms",
        "state education rules",
        "state caste-certificate issuance and appeal rules",
        "school board or education-record correction rules for marksheet/certificate changes",
        "loan documents and RBI restructuring/settlement guidance where negotiation is requested",
        "GST refund/bank operation records only after company status is addressed",
        "victim-compensation and DLSA procedure for urgent treatment/support",
    ]

    missing = missing_required_authorities(
        required_sources=required_sources,
        passages=[],
        query="urgent tribunal order against me how to appeal NCLAT format and fees",
    )
    assert [item["required_source"] for item in missing] == [
        "NCLAT rules, forms, fees, certified-copy and limitation facts",
        "NCLT Rules / IBC application forms",
    ]
    assert missing_required_authorities(
        required_sources=["NCLT Rules / IBC application forms"],
        passages=[
            {
                "index": 1,
                "title": "National Company Law Tribunal Rules 2016",
                "anchor": "nclt-rules-2016/rule-23",
                "source_type": "rule",
            }
        ],
        query="operational creditor want to file section 9 ibc against company owing money",
    ) == []


def test_stage_e9e_cgst_rule_86b_requires_rules_and_act_ledger_sources():
    required = ["CGST Rules 2017 Rule 86B and CGST Act 2017 electronic-credit-ledger provisions"]
    rule_only = [
        {
            "index": 1,
            "title": "Central Goods and Services Tax Rules 2017",
            "anchor": "cgst-rules-2017/sec-85-e",
            "text": "Rule 86B restricts use of amount available in electronic credit ledger.",
            "source_type": "bare_act",
        }
    ]
    composite = rule_only + [
        {
            "index": 2,
            "title": "Central Goods and Services Tax Act 2017",
            "anchor": "cgst-2017/sec-49-a",
            "source_type": "bare_act",
        }
    ]

    assert missing_required_authorities(
        required_sources=required,
        passages=rule_only,
        query="rule 86B applies to me turnover 55 lakh per month must pay 1 percent cash",
    )
    assert missing_required_authorities(
        required_sources=required,
        passages=composite,
        query="rule 86B applies to me turnover 55 lakh per month must pay 1 percent cash",
    ) == []


def test_stage_e9e_source_gap_accepts_contribution_pesa_and_online_freeze_sources():
    assert missing_required_authorities(
        required_sources=["Code on Social Security 2020 where contribution/social-security classification applies"],
        passages=[
            {
                "index": 1,
                "title": "Code on Social Security 2020",
                "anchor": "social-security-code-2020/sec-31@2025-11-21",
                "source_type": "bare_act",
            }
        ],
        query="esi inspector sent notice contribution short by 1.2 lakh for casual workers",
    ) == []

    assert missing_required_authorities(
        required_sources=["PESA / Gram Sabha consultation where Scheduled Area facts apply"],
        passages=[
            {
                "index": 1,
                "title": "Panchayats (Extension to the Scheduled Areas) Act 1996",
                "anchor": "pesa-1996/sec-4-b@1996-12-24",
                "source_type": "bare_act",
            }
        ],
        query="iron ore mine displaced our 12 villages no rehabilitation given",
    ) == []

    assert missing_required_authorities(
        required_sources=["RBI/KYC or online-gaming rules where financial account facts apply"],
        passages=[
            {
                "index": 1,
                "title": "Prevention of Money Laundering Act 2002",
                "anchor": "pmla-2002/sec-17-a",
                "source_type": "bare_act",
            }
        ],
        query="binance froze my usdt wallet saying suspicious trade and kyc pending",
    ) == []


def test_stage_e9e_source_gap_tightens_overbroad_conditional_triggers():
    assert missing_required_authorities(
        required_sources=[
            "Building and Other Construction Workers Act 1996 where the workplace is a construction/building worksite",
            "Code on Wages 2019 where unpaid overtime wages are also claimed",
            "Specific Relief Act 1963 where injunction/performance is sought",
            "BNSS 2023 / CrPC 1973 only if the case-status issue is in a criminal case",
            "BNS 2023 / IPC 1860 offence provisions where relevant",
        ],
        passages=[],
        query="urgent what should I wear to court as litigant in person appearing first time how to complain",
    ) == []
    assert missing_required_authorities(
        required_sources=["Code on Wages 2019 where unpaid overtime wages are also claimed"],
        passages=[],
        query="maharashtra labour department raid kiya overtime register not maintained 11 workers",
    ) == []
    assert missing_required_authorities(
        required_sources=["Specific Relief Act 1963 where injunction/performance is sought"],
        passages=[],
        query="vendor agreed delivery in 30 days now 4 months over want to cancel and recover advance",
    ) == []


def test_route_bound_labour_source_pack_cannot_fall_through_to_llm():
    query = "maharashtra labour department raid kiya overtime register not maintained 11 workers"
    route = route_matter(query)
    plan = build_matter_plan(query, route)

    gap = build_source_gap_event(
        query=query,
        route_category=route.category,
        required_sources=route.required_sources,
        passages=[],
        plan=plan,
        legal_regime=route.legal_regime,
    )

    assert gap is not None
    assert gap["reason"] == "required_source_gap"
    assert any(
        item.get("source_pack_id") == "maharashtra_shops_establishments_2017"
        for item in gap["missing_required_sources"]
    )


def test_stage_e9e_source_gap_accepts_bns_section_69_promise_to_marry_source():
    assert missing_required_authorities(
        required_sources=["BNS 2023 sections 63 and 69 / IPC legacy sexual-offence provisions based on incident date"],
        passages=[
            {
                "index": 1,
                "title": "Bharatiya Nyaya Sanhita 2023",
                "anchor": "bns-2023/sec-69@2024-07-01",
                "source_type": "bare_act",
            }
        ],
        query="girl filed rape case after breakup saying I promised marriage relationship for 2 years",
    ) == []


def test_stage_e9f_source_gap_skips_non_direct_aadhaar_and_unalleged_offence_requirements():
    assert missing_required_authorities(
        required_sources=["Aadhaar Act 2016 only where Aadhaar authentication or UIDAI records are directly involved"],
        passages=[],
        query="data breach at byjus my pan and aadhaar leaked can i claim compensation under DPDP act",
    ) == []

    assert missing_required_authorities(
        required_sources=["BNS 2023 / IPC 1860 offence provisions where relevant"],
        passages=[],
        query="anticipatory bail granted 30 day bombay HC police still threatening to arrest what next",
    ) == []

    assert missing_required_authorities(
        required_sources=["BNSS 2023 / CrPC 1973 only for the adult criminal-procedure wrapper after age is checked"],
        passages=[],
        query="16 yr boy detained adult jail 2 weeks already how to transfer observation home",
    ) == []


def test_stage_e9f_source_gap_accepts_bail_trafficking_and_privacy_authorities():
    assert missing_required_authorities(
        required_sources=["BNSS 2023 / CrPC 1973 bail and custody procedure based on incident date"],
        passages=[
            {
                "index": 1,
                "title": "Bharatiya Nagarik Suraksha Sanhita 2023",
                "anchor": "bnss-2023/sec-480@2024-07-01",
                "source_type": "bare_act",
            },
            {
                "index": 2,
                "title": "Code of Criminal Procedure 1973",
                "anchor": "crpc-1973/sec-439",
                "source_type": "bare_act",
            },
        ],
        query="ndps bail rejected 6 times by session court husband 3 yrs in tihar option",
    ) == []

    assert missing_required_authorities(
        required_sources=["BNSS 2023 / CrPC 1973 bail and custody procedure based on incident date"],
        passages=[
            {
                "index": 1,
                "title": "Bharatiya Nagarik Suraksha Sanhita 2023",
                "anchor": "bnss-2023/sec-483@2024-07-01",
                "source_type": "bare_act",
            },
            {
                "index": 2,
                "title": "Code of Criminal Procedure 1973",
                "anchor": "crpc-1973/sec-439",
                "source_type": "bare_act",
            },
            {
                "index": 3,
                "title": "Unlawful Activities (Prevention) Act 1967",
                "anchor": "uapa-1967/sec-43d",
                "source_type": "bare_act",
            },
        ],
        query="urgent brother in jail 18 months UAPA bail when prima facie case made out kya hota",
    ) == []

    assert missing_required_authorities(
        required_sources=["BNSS/CrPC complaint and protection procedure"],
        passages=[
            {
                "index": 1,
                "title": "Bharatiya Nagarik Suraksha Sanhita 2023",
                "anchor": "bnss-2023/sec-173-b@2024-07-01",
                "source_type": "bare_act",
            }
        ],
        query="spa customers want extra owner makes us do it if we refuse no salary how do I get out",
    ) == []

    assert missing_required_authorities(
        required_sources=["constitutional reproductive autonomy and privacy precedents"],
        passages=[
            {
                "index": 1,
                "title": "X versus THE PRINCIPAL SECRETARY HEALTH AND FAMILY WELFARE DEPARTMENT & ANR.",
                "anchor": "2022-insc-740#para-11",
                "source_type": "sc_judgment",
            }
        ],
        query="had abortion 5 yrs back husband found out and is threatening divorce can he use this in court",
    ) == []


def test_stage_e9g_source_gap_requires_mental_healthcare_for_therapist_privacy():
    required = [
        "Mental Healthcare Act 2017 for confidentiality/privacy of mental-health records or therapist communications"
    ]
    query = "someone leaked my chat with therapist on twitter mental health privacy"

    missing = missing_required_authorities(
        required_sources=required,
        passages=[
            {
                "index": 1,
                "title": "Digital Personal Data Protection Act 2023",
                "anchor": "dpdp-2023/sec-13",
                "source_type": "bare_act",
            }
        ],
        query=query,
    )
    assert missing == [
        {
            "required_source": required[0],
            "kind": "national_statute_retrieval_gap",
        }
    ]

    assert missing_required_authorities(
        required_sources=required,
        passages=[
            {
                "index": 1,
                "title": "Mental Healthcare Act 2017",
                "anchor": "mental-healthcare-2017/sec-43",
                "source_type": "bare_act",
            }
        ],
        query=query,
    ) == []


def test_mental_healthcare_confinement_accepts_confinement_safeguards():
    required = ["Mental Healthcare Act 2017"]
    query = "my brother is mentally ill and family kept him in chains how can we admit him legally"

    assert missing_required_authorities(
        required_sources=required,
        passages=[
            {
                "index": 1,
                "title": "Mental Healthcare Act 2017",
                "anchor": "mental-healthcare-2017/sec-20",
                "source_type": "bare_act",
            }
        ],
        query=query,
    ) == []


def test_stage2_source_gap_accepts_epfo_pension_composite_authority():
    required = [
        "Employees Provident Funds and Miscellaneous Provisions Act 1952 or Code on Social Security 2020 for EPFO/EPS pension scheme basis"
    ]
    query = "what to do epfo wala bol raha aadhaar mismatch pension nahi milega 4 saal se is this legal"

    assert missing_required_authorities(
        required_sources=required,
        passages=[
            {
                "index": 1,
                "title": "Employees Provident Funds and Miscellaneous Provisions Act 1952",
                "anchor": "epf-1952/sec-6A",
                "source_type": "bare_act",
            },
        ],
        query=query,
    ) == []

    for passage in [
        {
            "index": 1,
            "title": "Employees Provident Funds and Miscellaneous Provisions Act 1952",
            "anchor": "epf-1952/sec-6",
            "source_type": "bare_act",
        },
        {
            "index": 1,
            "title": "Employees Provident Funds and Miscellaneous Provisions Act 1952",
            "anchor": "epf-1952/sec-7A",
            "source_type": "bare_act",
        },
        {
            "index": 1,
            "title": "Employees Provident Funds and Miscellaneous Provisions Act 1952",
            "anchor": "epf-1952/sec-14",
            "source_type": "bare_act",
        },
        {
            "index": 1,
            "title": "Code on Social Security 2020",
            "anchor": "social-security-code-2020/sec-120",
            "source_type": "bare_act",
        },
        {
            "index": 1,
            "title": "Code on Social Security 2020",
            "anchor": "social-security-code-2020#header",
            "source_type": "bare_act",
        },
    ]:
        assert missing_required_authorities(
            required_sources=required,
            passages=[passage],
            query=query,
        ) == [{"required_source": required[0], "kind": "national_labor_source_gap"}]

    assert missing_required_authorities(
        required_sources=required,
        passages=[
            {
                "index": 1,
                "title": "Code on Social Security 2020",
                "anchor": "social-security-code-2020/sec-15",
                "source_type": "bare_act",
            },
        ],
        query=query,
    ) == []


def test_stage_e9g_source_gap_accepts_precise_repair_authorities_without_over_enforcing():
    assert missing_required_authorities(
        required_sources=["BNSS/CrPC complaint procedure"],
        passages=[],
        query="biharee called by site engineer pune always after wage complaint is this crime is this legal",
    ) == []

    assert missing_required_authorities(
        required_sources=["BNS/BNSS or IPC/CrPC based on incident date where confinement, assault, threats, or document retention are involved"],
        passages=[
            {
                "index": 1,
                "title": "Bharatiya Nyaya Sanhita 2023",
                "anchor": "bns-2023/sec-146@2024-07-01",
                "source_type": "bare_act",
            },
            {
                "index": 2,
                "title": "Bharatiya Nagarik Suraksha Sanhita 2023",
                "anchor": "bnss-2023/sec-173-b@2024-07-01",
                "source_type": "bare_act",
            },
        ],
        query="thekedar took 18000 advance from me darbhanga not letting leave bangalore site is this legal",
    ) == []

    assert missing_required_authorities(
        required_sources=["Copyright Act 1957 where creative work/logo is involved"],
        passages=[
            {
                "index": 3,
                "title": "Copyright Act 1957",
                "anchor": "copyright-1957/sec-55",
                "source_type": "bare_act",
            }
        ],
        query="got cease and desist notice from big company saying my logo similar to theirs delhi exporter",
    ) == []
