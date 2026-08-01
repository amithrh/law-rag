import json
from datetime import date

import pytest
from apps.api.common_workflow_contracts import (
    WorkflowTemplateResult,
    dpdp_section_13_in_force,
)
from apps.api.authority_graph import authority_graph_contract_template_result
from apps.api.legal_issue_plan import (
    PLAN_OWNED_ANSWER_ROUTES,
    build_matter_plan,
    plan_owned_answer_route,
    resolve_plan_answer_ownership,
)
from apps.api.main import (
    _backfill_registry_required_authorities,
    _controlling_source_gap_requires_handoff,
    _critical_route_needs_reviewed_contract,
    _grounded_template_lines,
    _make_passages,
    _promote_reviewed_workflow_contract_line,
    _promote_safe_route_next_step,
    _promote_safe_template_source_bridge,
    _route_regime_caveat,
    _selected_workflow_result,
    _workflow_diagnostics_event,
)
from apps.api.matter_router import route_matter
from apps.api.retrieval import RetrievedChunk
from apps.api.source_gap import (
    build_source_gap_event,
    matter_plan_integrity_gap,
    missing_plan_authorities,
)
from apps.api.source_packs import source_packs_for_route
from apps.api.verifier import SentenceStatus, SentenceVerification

RELEASED_SCENARIOS = (
    (
        "My husband is beating me right now, what should I do?",
        "domestic_violence_immediate_safety",
        "authority_graph:domestic_violence_immediate_safety",
    ),
    (
        "Police picked my son from home at night and gave no FIR copy",
        "arrest_custody_station_case_not_disclosed",
        "authority_graph:arrest_custody_station_case_not_disclosed",
    ),
    (
        "Police arrested my son for being gay",
        "lgbtq_identity_arrest_safeguard",
        "authority_graph:lgbtq_identity_arrest_safeguard",
    ),
    (
        "My bike is stolen and police is not filing FIR",
        "vehicle_theft_fir_refusal",
        "authority_graph:vehicle_theft_fir_refusal",
    ),
    (
        "MGNREGA wages have not been paid for four months",
        "mgnrega_fake_muster",
        "authority_graph:mgnrega_fake_muster",
    ),
    (
        "Loan app is harassing my contacts",
        "loan_app_harassment",
        "common_workflow_contracts:loan_app_harassment",
    ),
    (
        "Cyber police put a lien on my frozen bank account",
        "bank_account_freeze_legal_hold",
        "authority_graph:bank_account_freeze_legal_hold",
    ),
    (
        "Enforcement Directorate froze my bank account under PMLA",
        "pmla_ed_asset_freeze",
        "authority_graph:pmla_ed_asset_freeze",
    ),
    (
        "Urgent: my brother has been in jail for 18 months under UAPA; what does prima facie true mean for bail?",
        "uapa_prima_facie_bail",
        "authority_graph:uapa_prima_facie_bail",
    ),
    (
        "Police seized my phone and will not return it",
        "police_seized_device_return",
        "common_workflow_contracts:police_seized_device_return",
    ),
    (
        "Bank deducted money wrongly and customer care is not helping",
        "wrong_bank_debit",
        "authority_graph:wrong_bank_debit",
    ),
    (
        "PAN Aadhaar linking failed and bank KYC rejected",
        "pan_aadhaar_linking_bank_kyc",
        "authority_graph:pan_aadhaar_linking_bank_kyc",
    ),
    (
        "The insurer is rejecting my claim",
        "insurance_claim_or_misselling",
        "authority_graph:insurance_claim_or_misselling",
    ),
    (
        "My online order arrived damaged and the seller refuses a refund. What can I do?",
        "consumer_defective_goods",
        "authority_graph:consumer_defective_goods",
    ),
    (
        "My bike was bought online and the seller refuses a warranty repair",
        "consumer_defective_goods",
        "authority_graph:consumer_defective_goods",
    ),
    (
        "My brother and I bought a plot together and he sold it without me",
        "joint_coowner_sold_whole_property",
        "authority_graph:joint_coowner_sold_whole_property",
    ),
    (
        "My wife has refused physical intimacy for one year, what lawful remedy exists?",
        "marital_intimacy_remedy",
        "authority_graph:marital_intimacy_remedy",
    ),
    (
        "I registered my will with the sub registrar; do I need to update it every year?",
        "registered_will_update",
        "authority_graph:registered_will_update",
    ),
    (
        "My father wants to make a will giving more to his caretaker daughter",
        "caretaker_daughter_will",
        "authority_graph:caretaker_daughter_will",
    ),
    (
        "My father died and the heirs are fighting over whether his unregistered will is valid",
        "unregistered_will_validity",
        "authority_graph:unregistered_will_validity",
    ),
    (
        "upper caste people beat me on 2025-01-02 what action can i take",
        "scst_targeted_violence_intake",
        "authority_graph:scst_targeted_violence_intake",
    ),
    (
        "I am accused in a false SC ST case and need anticipatory bail under section 18 18A",
        "scst_poa_accused_bail_defence",
        "authority_graph:scst_poa_accused_bail_defence",
    ),
    (
        "SC/ST Act case filed against me, I was arrested, bail needed",
        "scst_poa_accused_bail_defence",
        "authority_graph:scst_poa_accused_bail_defence",
    ),
    (
        "my ST certificate has been pending at the tehsildar for months, what can I do",
        "caste_certificate_state_rule_intake",
        "authority_graph:caste_certificate_state_rule_intake",
    ),
    (
        "thermal plant blasting cracking our houses no compensation kalahandi",
        "thermal_blasting_house_damage_compensation",
        "authority_graph:thermal_blasting_house_damage_compensation",
    ),
    (
        "iron ore mine displaced 12 villages in Keonjhar with no rehabilitation",
        "mining_displacement_rehabilitation",
        "authority_graph:mining_displacement_rehabilitation",
    ),
    (
        "school asked for birth certificate but panchayat is not issuing it",
        "civil_registration_certificate_issuance",
        "authority_graph:civil_registration_certificate_issuance",
    ),
    (
        "need duplicate death cert from municipality",
        "civil_registration_certificate_copy",
        "authority_graph:civil_registration_certificate_copy",
    ),
    (
        "death registration delayed by panchayat",
        "death_registration_delayed",
        "authority_graph:death_registration_delayed",
    ),
    (
        "birth certificate wrong name municipality correction",
        "birth_certificate_record_correction",
        "authority_graph:birth_certificate_record_correction",
    ),
    (
        "death certificate has wrong name hospital says they cannot correct it what is process",
        "death_certificate_record_correction",
        "authority_graph:death_certificate_record_correction",
    ),
    (
        "I am accused of sexually harassing a colleague and got an ICC notice",
        "workplace_sexual_harassment_respondent",
        "common_workflow_contracts:workplace_sexual_harassment_respondent",
    ),
    (
        "I complained to ICC about sexual harassment by my manager",
        "workplace_sexual_harassment_complainant",
        "common_workflow_contracts:workplace_sexual_harassment_first_action",
    ),
    (
        "Lok Adalat traffic challan settlement",
        "lok_adalat_traffic_settlement",
        "common_workflow_contracts:lok_adalat_traffic_settlement",
    ),
    (
        "Lok Adalat award signed under coercion how to challenge",
        "lok_adalat_award_challenge",
        "common_workflow_contracts:lok_adalat_award_challenge",
    ),
)


@pytest.mark.parametrize("query,scenario_id,owner", RELEASED_SCENARIOS)
def test_released_scenarios_have_one_exact_owner_and_explicit_fallback(
    query: str,
    scenario_id: str,
    owner: str,
):
    route = route_matter(query)
    rule = plan_owned_answer_route(query, route)
    plan = build_matter_plan(query, route)

    assert rule is not None
    assert rule.scenario_id == scenario_id
    assert rule.owner_token == owner
    assert plan is not None
    assert plan.answer_policy.required_primary_owner == owner
    assert plan.answer_policy.fallback_owner == "source_gap_handoff"
    assert plan.answer_policy.requires_reviewed_contract is True
    assert plan.answer_policy.allow_freeform_llm is False


def test_released_registry_is_unique_and_matches_release_inventory():
    scenario_ids = [rule.scenario_id for rule in PLAN_OWNED_ANSWER_ROUTES]
    owner_tokens = [rule.owner_token for rule in PLAN_OWNED_ANSWER_ROUTES]
    released_scenario_ids = {scenario_id for _, scenario_id, _ in RELEASED_SCENARIOS}

    assert len(scenario_ids) == len(set(scenario_ids))
    assert set(scenario_ids) == released_scenario_ids
    assert len(owner_tokens) == len(set(owner_tokens))
    assert all(rule.fallback_owner for rule in PLAN_OWNED_ANSWER_ROUTES)


def test_device_return_owner_is_not_shadowed_by_generic_consumer_return_language():
    query = "Police seized my phone and will not return it"
    route = route_matter(query)

    assert route.category == "police_fir"
    resolution = resolve_plan_answer_ownership(query, route)
    assert resolution.conflicts == ()
    assert resolution.owner is not None
    assert resolution.owner.scenario_id == "police_seized_device_return"


def test_consumer_owner_uses_word_boundaries_for_non_vehicle_products():
    query = "The carpet company is refusing a warranty repair"
    route = route_matter(query)

    assert route.category == "consumer"
    owner = plan_owned_answer_route(query, route)
    assert owner is not None
    assert owner.scenario_id == "consumer_defective_goods"


def test_scst_accused_bail_owner_requires_the_official_poa_bail_pack():
    query = "I am accused in a false SC ST case and need anticipatory bail under section 18 18A"
    route = route_matter(query)
    plan = build_matter_plan(query, route)
    assert route.category == "criminal_defence_bail"
    assert plan is not None
    assert plan.answer_policy.required_primary_owner == (
        "authority_graph:scst_poa_accused_bail_defence"
    )

    wrong_pack = [
        _passage(
            1,
            "Scheduled Castes and Scheduled Tribes (Prevention of Atrocities) Act 1989",
            "sc-st-poa-1989/sec-18",
            "scst_poa_unreviewed",
        ),
    ]
    assert _selected_workflow_result(query, route, wrong_pack, plan) is None

    only_section_18 = [
        _passage(
            1,
            "Scheduled Castes and Scheduled Tribes (Prevention of Atrocities) Act 1989",
            "sc-st-poa-1989/sec-18",
            "scst_poa_1989",
        ),
    ]
    assert _selected_workflow_result(query, route, only_section_18, plan) is None

    official_pack = [
        _passage(
            1,
            "Scheduled Castes and Scheduled Tribes (Prevention of Atrocities) Act 1989",
            "sc-st-poa-1989/sec-18",
            "scst_poa_1989",
        ),
        _passage(
            2,
            "Scheduled Castes and Scheduled Tribes (Prevention of Atrocities) Act 1989",
            "sc-st-poa-1989/sec-18A",
            "scst_poa_1989",
        ),
    ]
    workflow = _selected_workflow_result(query, route, official_pack, plan)
    assert workflow is not None
    assert workflow.id == "scst_poa_accused_bail_defence"
    assert workflow.source == "authority_graph"
    assert workflow.source_indices == {"poa_section_18": 1, "poa_section_18a": 2}
    assert workflow.required_sources == ("poa_section_18", "poa_section_18a")
    rendered = " ".join(workflow.lines)
    assert "Section 18" in rendered
    assert "Section 18A" in rendered


@pytest.mark.parametrize(
    "query",
    (
        "My spouse and I disagree about monthly household expenses",
        "My adult son left home voluntarily and police have not detained him",
        "Is a consensual same-sex relationship between two adults illegal?",
        "The bike service centre is refusing a warranty repair",
        "Loan app only sends a normal due date reminder and is not harassing me",
        "My bank loan EMI is due next week",
        "Police sent me notice in a cyber fraud case and I am accused",
        "I stole a scooter and police registered FIR",
        "Police took my phone from home at night and gave no FIR copy",
        "Police kept my laptop in custody and gave no FIR copy",
        "My laptop is in police custody and I received no FIR copy",
        "Police kept my laptop in their custody and gave no FIR copy",
        "Police have custody of my laptop and gave no FIR copy",
        "The police retain custody of my laptop and gave no FIR copy",
        "Police retain custody of my external hard drive and gave no FIR copy",
        "Police have custody of my passport and gave no FIR copy",
        "Police retained my tablet in custody and gave no FIR copy",
        "Officers took Priya's handbag and will not tell us the case",
        "Police took Samsung Galaxy from my room and will not tell us the case",
        "Police took MacBook from the office and will not tell us the case",
        "Officers held Vivo overnight and will not disclose the station",
        "Officers held GoPro overnight and will not disclose the station",
        "Police took Kindle from the office and will not tell us the case",
        "Officers held Rolex overnight and will not disclose the station",
        "Police held security guard equipment overnight and will not disclose the station",
        "Police took driver documents and will not tell us the case",
        "Officers detained worker ID cards overnight and will not disclose the station",
        "Police held security guard uniforms overnight and will not disclose the station",
        "Police took driver licence and will not tell us the case",
        "Officers kept worker tools overnight and will not disclose the station",
        "Officers held Amazon parcel overnight and will not tell me the case",
        "Police took iPhone from my desk and will not tell me the case",
        "Officers held Aadhaar overnight and will not disclose the station",
        "Police held partner company records overnight and gave no FIR copy",
        "Police held sister company server records overnight and will not tell us where they are",
        "Police held our sister concern server backups overnight and will not tell us where they are",
        "Police took the phone belonging to my son and will not tell me the case",
        "Police took my son's phone and will not tell me the case",
        "Police have custody of my partner's laptop and gave no FIR copy",
        "My husband beat his brother and police arrested him",
        "My husband beat his brother in front of me and police arrested him",
        "My husband beat his brother while I recorded it on my phone",
        "My husband threatened him near me and police arrested him",
        "My husband threatened my cousin near me and police arrested him",
        "My husband threatened my daughter in front of me and police took him away",
        "My husband threatened my cousin next to me and police arrested him",
        "My husband threatened my cousin behind me and police arrested him",
        "My husband threatened my cousin next to my brother and me and police arrested him",
        "My husband threatened my cousin near Ravi and me and police arrested him",
        "My husband threatened to hit my sister beside me and police arrested him",
        "My neighbour threatened to poison me; my husband was away at work",
        "My husband called 112 when our neighbour threatened to burn me",
        "My husband called police because the shop owner threatened to stab me",
        "Mere pati ne police ko bulaya jab landlord ne mujhe jalane ki dhamki di",
        "My husband called police because the shop owner threatened to stab me",
        "Mere pati ne police ko bulaya jab landlord ne mujhe jalane ki dhamki di",
        "My husband spoke to police after the landlord threatened to kill me",
        "My husband called for help when the shopkeeper threatened to stab me",
        "My husband informed police after a stranger threatened to shoot me",
        "My husband reached home while the security guard threatened to burn me",
        "My husband dialled emergency services as the delivery agent threatened to stab me",
        "My husband said the mechanic will stab me",
        "My husband warned me the contractor will shoot me",
        "My husband told me our tenant will poison me",
        "My husband mentioned that our plumber will stab me",
        "My husband heard that the mechanic plans to shoot me",
        "My bike was stolen and the parking society refused my complaint",
        "My bike was stolen and the society officer refused my complaint",
        "My bike was stolen; police say the FIR is registered but refuse to investigate",
        "My bike was stolen; an FIR already exists but police refuse to investigate",
        "My bike was stolen; police registered the FIR but now refuse to investigate",
        "My bike was stolen; police have registered my FIR but will not investigate",
        "My bike was stolen; an FIR was already lodged but police will not investigate",
        "My bike was stolen; the FIR has already been lodged but police will not investigate",
        "My bike was stolen; police gave me the FIR number but will not investigate",
        "My bike was stolen; I already have the FIR copy but police will not investigate",
        "My scooter was stolen; the FIR is on record but police refuse to investigate",
        "My scooter was stolen; police recorded the First Information Report but will not investigate",
        "My scooter was stolen; the FIR is active but police refuse to act on it",
        "Police gave me crime number 48 but refuse to trace my stolen scooter",
        "Police lodged my complaint but refuse to give a status update about my stolen bike",
        "My bike FIR is under investigation but police will not share progress",
        "My stolen scooter case is C.R. 22 and police refuse further action",
        "The investigation into my stolen car is progressing slowly",
        "My stolen scooter FIR is being investigated, but the SHO refuses to disclose what recovery steps were taken",
        "Stolen scooter ka FIR darj hai; police progress batane se refuse kar rahe hain",
        "Police opened an FIR for my stolen car but refuse to search for it or give me updates",
        "The police drew up an FIR for my stolen bike but refuse to look for it",
        "My stolen scooter has an e-FIR acknowledgment, but police refuse to locate it",
        "My stolen bike FIR ki jaanch chal rahi hai, but police refuse to give the case diary update",
        "The stolen-car FIR remains pending investigation; the SHO refuses to tell me the current stage",
        "My stolen bike has an FIR receipt, but police refuse to chase the thieves",
        "The vehicle theft FIR was assigned to an IO, but police refuse to follow up",
        "Court froze my bank account during execution of a civil decree",
        "The civil court froze my account to satisfy a judgment",
        "The court froze my bank account to satisfy its judgment",
        "A court froze my bank account to enforce the money judgment",
        "The bank froze my account under an executing court order in a money suit",
        "Court put a lien on my salary account to recover the decretal amount",
        "A tribunal restricted withdrawals from my account under a recovery order",
        "The executing court blocked my bank account under a garnishee order; no police or cyber case is involved",
        "The executing court froze my account; police and cybercrime have nothing to do with it",
        "An arbitral tribunal blocked my account and police are not involved",
        "Cyber police did not freeze my bank account; the civil court froze it before judgment",
        "It was not the police but an arbitral tribunal that blocked my bank account before judgment",
        "Neither the police nor the cyber cell is involved; the court froze my account pending trial",
        "The bank says the debit freeze is under an arbitral interim order; police are not connected with it",
        "Although police never froze it, the trial court blocked my bank account pending judgment",
        "Police were not the ones who froze my account; a civil court did before trial",
        "Police said the account freeze was not theirs; the civil judge ordered it before trial",
        "Police denied any involvement in the account freeze; the civil court imposed it before judgment",
        "Police denied any role in the freeze; the arbitral tribunal ordered it during the pending arbitration",
        "Police denied being involved in the freeze; the arbitral tribunal imposed it during arbitration",
        "My bank account was frozen by an arbitral tribunal. Police did not request this freeze",
        "A money decree case is pending with no decree yet and the court ordered attachment before judgment",
        "After the money judgment, the court froze my account pending execution of the decree",
        "Pending execution of the decree, the executing court attached my bank account",
        "The money claim is finally resolved and the court froze my account to enforce the judgment",
        "Now that the claim is resolved, the civil court attached my bank account to satisfy the judgment",
        "After judgment was entered, the court froze my account while execution remained pending",
        "The decree has already been passed and the court froze my account to enforce it",
        "The recovery suit is pending adjudication and no decree has been issued, but the court attached my account",
        "The case remains undecided and the court froze my account before entering a decree",
        "The money decree proceeding is yet to be decided; the commercial court ordered a temporary attachment of my salary account",
        "The recovery suit is pending final decision; meanwhile the court put a lien on my savings account",
        "The court put a temporary lien on my account while the recovery suit is still being heard",
        "The court froze my account as security until the money suit is decided",
        "Which insurance policy should I buy?",
        "My brother and I jointly own land and only want mutation",
        "Blue Trunks app froze my account showing KYC pending and 80k stuck",
    ),
)
def test_released_owner_rules_do_not_capture_negative_neighbors(query: str):
    route = route_matter(query)
    assert plan_owned_answer_route(query, route) is None


@pytest.mark.parametrize(
    "query,required_packs,excluded_packs",
    (
        (
            "Enforcement Directorate froze my bank account under PMLA",
            {
                "pmla_2002_search_freeze",
                "pmla_2002_asset_adjudication",
                "pmla_2002_asset_appeal",
            },
            {"pmla_2002_provisional_attachment"},
        ),
        (
            "ED issued a provisional attachment order for my property under PMLA",
            {
                "pmla_2002_provisional_attachment",
                "pmla_2002_asset_adjudication",
                "pmla_2002_asset_appeal",
            },
            {"pmla_2002_search_freeze"},
        ),
        (
            "ED issued a provisional attachment order for my bank account under PMLA",
            {
                "pmla_2002_provisional_attachment",
                "pmla_2002_asset_adjudication",
                "pmla_2002_asset_appeal",
            },
            {"pmla_2002_search_freeze"},
        ),
    ),
)
def test_pmla_asset_restraint_owner_selects_the_exact_statutory_path(
    query: str,
    required_packs: set[str],
    excluded_packs: set[str],
):
    route = route_matter(query)
    owner = plan_owned_answer_route(query, route)
    plan = build_matter_plan(query, route)

    assert route.category == "pmla_ed"
    assert owner is not None
    assert owner.owner_contract_id == "pmla_ed_asset_freeze"
    assert plan is not None
    pack_ids = {source.source_pack_id for source in plan.retrieval_sources}
    assert required_packs <= pack_ids
    assert pack_ids.isdisjoint(excluded_packs)
    assert plan.answer_policy.required_primary_owner == (
        "authority_graph:pmla_ed_asset_freeze"
    )
    assert plan.answer_policy.allow_freeform_llm is False
    assert plan.action_pack_id == "pmla_ed_asset_restraint"
    visible_plan = " ".join([
        *plan.required_facts,
        *plan.next_steps,
        *plan.documents,
        *plan.forums,
    ]).lower()
    assert "bail" not in visible_plan
    assert "custody" not in visible_plan
    assert "special pmla court" not in visible_plan
    assert "pmla adjudicating authority" in visible_plan
    assert "appellate tribunal" in visible_plan
    assert plan.incident_date_status == "not_applicable_for_asset_restraint"
    assert plan.legal_regime is None


@pytest.mark.parametrize(
    "query",
    (
        "ED summoned me under PMLA to record my statement",
        "ED summoned me under PMLA to explain my bank account",
        "ED notice asks me to explain property transactions under PMLA",
        "I was arrested by ED and need bail under the PMLA twin conditions",
        "Cyber police froze my bank account after an online fraud complaint",
        "The bank blocked my account because KYC is pending",
        "I attached my bank statement to the ED response under PMLA",
        "ED sent me an attachment with the notice under PMLA",
        "ED attached the bank account statement to its PMLA reply",
        "ED attached my property papers to the notice under PMLA",
        "ED blocked my lawyer from accessing bank account records under PMLA",
    ),
)
def test_pmla_asset_restraint_owner_rejects_neighboring_workflows(query: str):
    route = route_matter(query)
    owner = plan_owned_answer_route(query, route)

    assert owner is None or owner.owner_contract_id != "pmla_ed_asset_freeze"


@pytest.mark.parametrize(
    "query",
    (
        "ED restrained my fixed deposit under PMLA",
        "Enforcement Directorate seized my jewellery under PMLA",
        "ED prohibited me from dealing with my shares in the PMLA case",
        "ED put a hold on my fixed deposit",
        "ED placed a lien on my bank account",
        "ED has locked my demat account",
        "ED ordered that I must not transfer my shares",
        "ED took possession of my gold under PMLA",
        "ED told me not to transfer my shares under PMLA",
        "ED said do not transfer the property under PMLA",
        "ED took physical custody of my gold under PMLA",
    ),
)
def test_pmla_asset_restraint_owner_understands_common_restraint_language(query: str):
    route = route_matter(query)
    owner = plan_owned_answer_route(query, route)

    assert route.category == "pmla_ed"
    assert owner is not None
    assert owner.owner_contract_id == "pmla_ed_asset_freeze"


@pytest.mark.parametrize(
    "query",
    (
        "ED put a hold on my fixed deposit",
        "ED placed a lien on my bank account",
        "ED has locked my demat account",
        "ED ordered that I must not transfer my shares",
        "ED told me not to transfer my shares under PMLA",
        "ED said do not transfer the property under PMLA",
    ),
)
def test_ambiguous_pmla_restraint_checks_both_statutory_paths(query: str):
    route = route_matter(query)
    plan = build_matter_plan(query, route)
    assert plan is not None
    assert {
        "pmla_2002_provisional_attachment",
        "pmla_2002_search_freeze",
        "pmla_2002_asset_adjudication",
        "pmla_2002_asset_appeal",
    } <= {source.source_pack_id for source in plan.retrieval_sources}

    workflow = _selected_workflow_result(
        query,
        route,
        _pmla_ambiguous_restraint_passages(),
        plan,
    )
    assert workflow is not None
    rendered = " ".join(workflow.lines)
    assert "does not by itself identify" in rendered
    assert "PMLA Section 5" in rendered
    assert "PMLA Section 17(1A)" in rendered


@pytest.mark.parametrize(
    "query",
    (
        "ED took possession of my gold under PMLA",
        "ED took physical custody of my gold under PMLA",
    ),
)
def test_took_possession_uses_the_section_17_seizure_branch(query: str):
    route = route_matter(query)
    plan = build_matter_plan(query, route)
    assert plan is not None
    workflow = _selected_workflow_result(
        query,
        route,
        _pmla_asset_passages(attachment=False),
        plan,
    )
    assert workflow is not None
    rendered = " ".join(workflow.lines)
    assert "For a seizure under PMLA Section 17" in rendered
    assert "seizure was not practicable" not in rendered


def test_direct_user_threat_and_true_fir_refusal_still_keep_their_owners():
    direct_threat = "My husband threatened my brother and me"
    threat_route = route_matter(direct_threat)
    threat_owner = plan_owned_answer_route(direct_threat, threat_route)
    assert threat_owner is not None
    assert threat_owner.owner_contract_id == "domestic_violence_immediate_safety"

    reported_direct_threat = "My husband told my sister that he will stab me tonight"
    reported_route = route_matter(reported_direct_threat)
    reported_owner = plan_owned_answer_route(reported_direct_threat, reported_route)
    reported_pack_ids = {
        pack.id for pack in source_packs_for_route(reported_route, reported_direct_threat)
    }
    assert reported_route.category == "family_domestic"
    assert reported_owner is not None
    assert reported_owner.owner_contract_id == "domestic_violence_immediate_safety"
    assert "pwdva_2005" in reported_pack_ids

    fir_refusal = "My bike was stolen and police have not lodged an FIR"
    fir_route = route_matter(fir_refusal)
    fir_owner = plan_owned_answer_route(fir_refusal, fir_route)
    assert fir_owner is not None
    assert fir_owner.owner_contract_id == "vehicle_theft_fir_refusal"

    written_only = "Scooter stolen from parking; station says give written complaint only"
    written_route = route_matter(written_only)
    written_owner = plan_owned_answer_route(written_only, written_route)
    assert written_owner is not None
    assert written_owner.owner_contract_id == "vehicle_theft_fir_refusal"

    hindi_dv = "Mera husband mujhe abhi maar raha hai, main kya karun?"
    hindi_route = route_matter(hindi_dv)
    hindi_owner = plan_owned_answer_route(hindi_dv, hindi_route)
    assert hindi_route.category == "family_domestic"
    assert hindi_owner is not None
    assert hindi_owner.owner_contract_id == "domestic_violence_immediate_safety"

    for custody_query in (
        "Police took my roommate and will not tell me the station",
        "Police picked my gay son from home at night and gave no FIR copy",
        "Police have custody of my partner and will not tell us the case",
        "Police took away my partner and will not tell me the station",
        "Officers took our roommate and will not tell us the case",
        "Police took Mr Rohan and will not tell me the station",
        "Police mere papa ko utha le gayi and will not tell the station",
        "Police ne Amit ko dhaba se utha ke le gaye, ab station ka naam nahi bata rahe",
        "Police took our driver from home and will not disclose the station",
        "Police detained the watchman and will not tell us the case",
        "Police detained the watchman and will not identify the station",
        "Crime Branch took my cousin away from his shop and the family cannot find which police station he is in",
        "Crime Branch detained our security guard after the raid and will not disclose which station he is in",
        "Crime Branch is holding our security guard at an undisclosed station and won't produce him in court",
        "Crime Branch has kept our security guard at the station for two days and has not produced him before a magistrate",
        "Kal raat police mere jija ko jeep mein le gayi; ghar walon ko thana nahi bata rahe",
    ):
        custody_route = route_matter(custody_query)
        custody_owner = plan_owned_answer_route(custody_query, custody_route)
        assert custody_owner is not None, custody_query
        assert custody_owner.owner_contract_id == "arrest_custody_station_case_not_disclosed"

    repeated_threat = "My husband made repeated threats to kill me"
    repeated_route = route_matter(repeated_threat)
    repeated_owner = plan_owned_answer_route(repeated_threat, repeated_route)
    assert repeated_owner is not None
    assert repeated_owner.owner_contract_id == "domestic_violence_immediate_safety"

    for threat_query in (
        "My husband threatened to poison me",
        "My husband threatened to have me killed",
        "My husband threatened to shoot me",
        "I am his wife. My husband threatened our driver and me",
        "I am his wife. My husband told his brother that he would burn me alive tonight",
        "My husband threatened to murder me",
        "My husband threatened to break my legs",
        "Mere husband ne bola ki aaj raat mujhe jala dega",
        "My husband threatened to slit my throat",
        "Mere husband ne bola mujhe jaan se maar dega",
        "Mere husband ne mujhe jaan se maarne ki dhamki di",
        "Mere husband ne dhamki di ki mujhe jala dega",
        "Mere pati ne mujhe jalane ki dhamki di",
        "Mere pati ne mujhe jaan se marne ki dhamki di",
        "My husband told my sister that he will stab me tonight",
        "I am his wife. My husband threatened the watchman and me outside our home",
    ):
        route = route_matter(threat_query)
        owner = plan_owned_answer_route(threat_query, route)
        assert owner is not None, threat_query
        assert owner.owner_contract_id == "domestic_violence_immediate_safety"


def test_environment_contracts_fail_closed_when_required_authority_is_missing():
    query = "thermal plant blasting cracking our houses no compensation kalahandi"
    route = route_matter(query)
    plan = build_matter_plan(query, route)

    assert plan is not None
    assert plan.answer_policy.required_primary_owner == (
        "authority_graph:thermal_blasting_house_damage_compensation"
    )
    assert plan.answer_policy.allow_freeform_llm is False
    assert _selected_workflow_result(query, route, [], plan) is None


def test_environment_contract_renders_when_both_required_sources_are_present():
    query = "thermal plant blasting cracking our houses no compensation kalahandi"
    route = route_matter(query)
    plan = build_matter_plan(query, route)
    passages = [
        {
            "index": 1,
            "title": "Environment (Protection) Act 1986",
            "anchor": "environment-protection-1986/sec-3-b",
            "required_source_pack": "environment_protection_1986",
        },
        {
            "index": 2,
            "title": "Right to Fair Compensation and Transparency in Land Acquisition, Rehabilitation and Resettlement Act 2013",
            "anchor": "rfctlarr-2013/sec-41-b",
            "required_source_pack": "rfctlarr_2013_project_damage_compensation",
        },
    ]

    workflow = _selected_workflow_result(query, route, passages, plan)

    assert workflow is not None
    assert workflow.id == "thermal_blasting_house_damage_compensation"
    assert workflow.source == "authority_graph"
    assert workflow.source_indices == {"environment": 1, "larr41": 2}


def test_pan_aadhaar_bank_kyc_requires_canonical_linking_source_and_bank_facts():
    query = "PAN Aadhaar linking failed and bank KYC rejected"
    route = route_matter(query)
    plan = build_matter_plan(query, route)

    assert plan is not None
    assert plan.answer_policy.required_primary_owner == (
        "authority_graph:pan_aadhaar_linking_bank_kyc"
    )
    assert plan.answer_policy.allow_freeform_llm is False

    legacy_or_unannotated = [
        {
            "index": 1,
            "title": "Income-tax Act 1961",
            "anchor": "income-tax-1961/sec-139AA-official",
            "required_source_pack": "income_tax_pan_1961",
            "document_id": "income-tax-1961",
        },
    ]
    assert _selected_workflow_result(query, route, legacy_or_unannotated, plan) is None

    canonical = [
        {
            "index": 1,
            "title": "Income-tax Act 1961",
            "anchor": "income-tax-1961-official/sec-139AA-official",
            "required_source_pack": "income_tax_pan_1961",
            "document_id": "income-tax-1961-official",
        },
    ]
    workflow = _selected_workflow_result(query, route, canonical, plan)
    assert workflow is not None
    assert workflow.id == "pan_aadhaar_linking_bank_kyc"
    assert workflow.source_indices == {"income_tax": 1}
    assert "Section 139AA concerns quoting Aadhaar" in " ".join(workflow.lines)
    assert workflow.lines[-1].startswith("- Keep a screenshot of the PAN-Aadhaar link-status")
    assert "[" not in workflow.lines[-1]

    header = SentenceVerification(
        text="**What you can do next**",
        status=SentenceStatus.META,
        citations=[],
        entailment_score=None,
        reason="meta line",
        auto_cited=False,
    )
    guidance = SentenceVerification(
        text=workflow.lines[-1],
        status=SentenceStatus.UNSUPPORTED,
        citations=[],
        entailment_score=None,
        reason="no legal citation for practical guidance",
        auto_cited=False,
    )
    promoted_guidance = _promote_safe_route_next_step(
        guidance,
        route,
        header,
        plan,
    )
    assert promoted_guidance.status == SentenceStatus.GUIDANCE
    assert promoted_guidance.citations == []

    general_linking_query = "PAN Aadhaar link status is failing while filing my return"
    assert plan_owned_answer_route(
        general_linking_query,
        route_matter(general_linking_query),
    ) is None


@pytest.mark.parametrize(
    "query",
    (
        "firecracker blast cracked my home and insurer refuses compensation",
        "thermal plant pollution damaged my house, what compensation can I claim",
        "coal mine land lease compensation dispute no displacement",
        "iron ore mining land acquisition compensation dispute",
        "power plant blasting did not crack our house but compensation is pending",
        "power plant blasting damaged crops but no house was cracked",
        "mine pollution damaged my house, but villagers were displaced years ago",
        "coal mine rehabilitation fund for workers no village displacement",
        "mine resettlement was not required and this is only a lease dispute",
        "I am not an affected family; the mine issue is about a permit",
        "coal mine workers need rehabilitation and compensation",
        "mining company offers employee rehabilitation compensation",
        "mine workers resettlement compensation benefits",
        "mine workers displaced from job not village and compensation",
        "thermal plant blasting no cracks in our house but compensation is pending",
        "thermal power station blasting without any cracks in my house compensation",
        "thermal power station blasting zero cracks in my house compensation",
        "mine villages resettlement is unnecessary",
        "mining project without any displacement of families",
    ),
)
def test_environment_owners_do_not_claim_neighboring_matter_types(query: str):
    route = route_matter(query)
    owner = plan_owned_answer_route(query, route)

    assert owner is None


@pytest.mark.parametrize(
    "query,owner_id",
    (
        (
            "thermal power station blasting cracked my house no compensation",
            "thermal_blasting_house_damage_compensation",
        ),
        (
            "power station blasting cracked my house and no compensation was paid",
            "thermal_blasting_house_damage_compensation",
        ),
        (
            "mining company displaced our family and gave no rehabilitation",
            "mining_displacement_rehabilitation",
        ),
        (
            "coal mine displaced families but no rehabilitation",
            "mining_displacement_rehabilitation",
        ),
        (
            "mine displaced us but no rehabilitation",
            "mining_displacement_rehabilitation",
        ),
        (
            "thermal power station blasting caused fissures in my walls",
            "thermal_blasting_house_damage_compensation",
        ),
        (
            "thermal power plant blasting damaged our home",
            "thermal_blasting_house_damage_compensation",
        ),
        (
            "mining project relocated 12 families",
            "mining_displacement_rehabilitation",
        ),
        (
            "mine shifted our village with no R&R",
            "mining_displacement_rehabilitation",
        ),
        (
            "mine workers displaced from job, the project displaced our village and no rehabilitation",
            "mining_displacement_rehabilitation",
        ),
    ),
)
def test_environment_owners_cover_common_positive_synonyms(query: str, owner_id: str):
    route = route_matter(query)
    owner = plan_owned_answer_route(query, route)

    assert owner is not None
    assert owner.owner_contract_id == owner_id


def test_mining_contract_renders_only_with_exact_reviewed_source_packs():
    query = "iron ore mine displaced 12 villages in Keonjhar with no rehabilitation"
    route = route_matter(query)
    plan = build_matter_plan(query, route)
    passages = [
        {
            "index": 1,
            "title": "Right to Fair Compensation and Transparency in Land Acquisition, Rehabilitation and Resettlement Act 2013",
            "anchor": "rfctlarr-2013/sec-41-b",
            "required_source_pack": "rfctlarr_2013_scheduled_area_rr",
        },
        {
            "index": 2,
            "title": "Panchayats (Extension to the Scheduled Areas) Act 1996",
            "anchor": "pesa-1996/sec-4-b",
            "required_source_pack": "pesa_1996",
        },
    ]

    workflow = _selected_workflow_result(query, route, passages, plan)

    assert workflow is not None
    assert workflow.id == "mining_displacement_rehabilitation"
    assert workflow.source_indices == {"larr": 1, "pesa": 2}


def test_mining_contract_rejects_unannotated_or_wrong_pack_larr_source():
    query = "iron ore mine displaced 12 villages in Keonjhar with no rehabilitation"
    route = route_matter(query)
    plan = build_matter_plan(query, route)
    passages = [
        {
            "index": 1,
            "title": "Right to Fair Compensation and Transparency in Land Acquisition, Rehabilitation and Resettlement Act 2013",
            "anchor": "rfctlarr-2013/sec-41-b",
        },
        {
            "index": 2,
            "title": "Panchayats (Extension to the Scheduled Areas) Act 1996",
            "anchor": "pesa-1996/sec-4-b",
            "required_source_pack": "pesa_1996",
        },
    ]

    assert _selected_workflow_result(query, route, passages, plan) is None


def test_complete_contract_packs_clear_the_source_gap_gate():
    cases = (
        (
            "thermal plant blasting cracking our houses no compensation kalahandi",
            [
                {
                    "index": 1,
                    "title": "Environment (Protection) Act 1986",
                    "anchor": "environment-protection-1986/sec-3-b@2026",
                    "required_source_pack": "environment_protection_1986",
                    "source_type": "bare_act",
                    "document_id": "environment-protection-1986",
                },
                {
                    "index": 2,
                    "title": "Right to Fair Compensation and Transparency in Land Acquisition, Rehabilitation and Resettlement Act 2013",
                    "anchor": "rfctlarr-2013/sec-41-b@2026",
                    "required_source_pack": "rfctlarr_2013_project_damage_compensation",
                    "source_type": "bare_act",
                    "document_id": "rfctlarr-2013",
                },
            ],
        ),
        (
            "iron ore mine displaced 12 villages in Keonjhar with no rehabilitation",
            [
                {
                    "index": 1,
                    "title": "Right to Fair Compensation and Transparency in Land Acquisition, Rehabilitation and Resettlement Act 2013",
                    "anchor": "rfctlarr-2013/sec-41-b@2026",
                    "required_source_pack": "rfctlarr_2013_scheduled_area_rr",
                    "source_type": "bare_act",
                    "document_id": "rfctlarr-2013",
                },
                {
                    "index": 2,
                    "title": "Panchayats (Extension to the Scheduled Areas) Act 1996",
                    "anchor": "pesa-1996/sec-4-b@2026",
                    "required_source_pack": "pesa_1996",
                    "source_type": "bare_act",
                    "document_id": "pesa-1996",
                },
            ],
        ),
    )

    for query, passages in cases:
        route = route_matter(query)
        plan = build_matter_plan(query, route)
        assert plan is not None
        assert build_source_gap_event(
            query=query,
            route_category=route.category,
            required_sources=route.required_sources,
            passages=passages,
            plan=plan,
            legal_regime=route.legal_regime,
        ) is None

    bank_query = "Cyber police froze my bank account, but there is no FIR yet"
    bank_route = route_matter(bank_query)
    bank_owner = plan_owned_answer_route(bank_query, bank_route)
    assert bank_owner is not None
    assert bank_owner.owner_contract_id == "bank_account_freeze_legal_hold"

    for plain_kyc_query in (
        "bank rejected my loan because KYC documents are pending",
        "bank is asking KYC again",
    ):
        plain_route = route_matter(plain_kyc_query)
        plain_owner = plan_owned_answer_route(plain_kyc_query, plain_route)
        assert plain_owner is None or plain_owner.owner_contract_id != "bank_account_freeze_legal_hold"

    kyc_hold_query = "Bank froze my account because KYC is pending"
    kyc_hold_route = route_matter(kyc_hold_query)
    kyc_hold_owner = plan_owned_answer_route(kyc_hold_query, kyc_hold_route)
    assert kyc_hold_owner is not None
    assert kyc_hold_owner.owner_contract_id == "bank_account_freeze_legal_hold"

    for bank_query in (
        "My account was blocked on the investigating officer's request",
        "The freeze is because of a cybercrime unit letter",
        "The investigating officer instructed the bank to freeze my account",
    ):
        bank_route = route_matter(bank_query)
        bank_owner = plan_owned_answer_route(bank_query, bank_route)
        assert bank_owner is not None, bank_query
        assert bank_owner.owner_contract_id == "bank_account_freeze_legal_hold"

    for fir_query in (
        "My bike was stolen and police are unwilling to register an FIR",
        "My scooter was stolen and police declined to lodge the FIR",
        "Police will not accept an FIR for my stolen bike",
        "My stolen bike case not registered; police refused to lodge the FIR",
        "There is no crime number because police will not register my stolen motorcycle FIR",
        "Police refused to register the stolen car case; no crime number has been assigned",
        "No FIR was registered for my stolen car because police refused my complaint",
        "Police said no FIR registered for my stolen bike and turned me away",
        "There is no FIR number because police refused to register my stolen car",
        "An FIR number is yet to be allotted because police refused my stolen-car complaint",
        "The FIR number remains unallotted because police rejected my stolen-bike complaint",
        "Police haven't assigned an FIR number for my stolen scooter and refuse to lodge it",
        "My stolen car FIR number is still pending allotment because the station turned me away",
        "The FIR number has yet to be generated for my stolen motorcycle because police refused registration",
    ):
        fir_route = route_matter(fir_query)
        fir_owner = plan_owned_answer_route(fir_query, fir_route)
        assert fir_owner is not None, fir_query
        assert fir_owner.owner_contract_id == "vehicle_theft_fir_refusal"


def test_civil_decree_account_attachment_routes_to_cpc_not_criminal_seizure():
    query = "Court froze my bank account during execution of a civil decree"
    route = route_matter(query)
    pack_ids = {pack.id for pack in source_packs_for_route(route, query)}

    assert route.category == "court_procedure"
    assert "Civil decree execution" in route.label
    assert "cpc_1908" in pack_ids
    assert "bnss_2023_bank_account_legal_hold" not in pack_ids
    assert "crpc_1973_bank_account_legal_hold" not in pack_ids


@pytest.mark.parametrize(
    "query",
    (
        "Before deciding the money suit, the court imposed an interim lien on my savings account.",
        "The court attached my account while the recovery suit is awaiting decision.",
        "The recovery suit is pending final decision; meanwhile the court put a lien on my savings account.",
    ),
)
def test_prejudgment_account_attachment_uses_order_38_not_decree_execution(query: str):
    route = route_matter(query)
    packs = source_packs_for_route(route, query)
    pack_ids = {pack.id for pack in packs}

    assert route.category == "court_procedure"
    assert route.label == "Pre-judgment civil attachment / security"
    assert any("Order XXXVIII" in source for source in route.required_sources)
    assert "bnss_2023_bank_account_legal_hold" not in pack_ids
    assert "crpc_1973_bank_account_legal_hold" not in pack_ids
    cpc = next(pack for pack in packs if pack.id == "cpc_1908")
    assert cpc.anchor_patterns == ("/sec-5", "/sec-6", "/sec-9")


@pytest.mark.parametrize(
    "query",
    (
        "A money decree case is pending with no decree yet and the court ordered attachment before judgment.",
        "The civil court froze my account until the recovery case is decided.",
        "The court put a lien on my savings account while the money claim remains pending.",
        "The judge temporarily attached my bank account before deciding the recovery claim.",
        "Police disowned the freeze; the civil judge placed a lien on my account while the claim awaits adjudication.",
        "The civil judge placed a lien on my savings account while the claim awaits adjudication.",
        "Before the recovery claim is resolved, the court froze my account.",
        "The court blocked my bank account pending resolution of the damages claim.",
    ),
)
def test_broader_prejudgment_grammar_keeps_order_38_stage(query: str):
    route = route_matter(query)
    packs = source_packs_for_route(route, query)

    assert route.label == "Pre-judgment civil attachment / security"
    cpc = next(pack for pack in packs if pack.id == "cpc_1908")
    assert cpc.anchor_patterns == ("/sec-5", "/sec-6", "/sec-9")


@pytest.mark.parametrize(
    "query",
    (
        "After the money judgment, the court froze my account pending execution of the decree",
        "Pending execution of the decree, the executing court attached my bank account",
        "The money claim is finally resolved and the court froze my account to enforce the judgment",
        "Now that the claim is resolved, the civil court attached my bank account to satisfy the judgment",
        "After judgment was entered, the court froze my account while execution remained pending",
        "The decree has already been passed and the court froze my account to enforce it",
    ),
)
def test_post_decree_account_attachment_keeps_order_21_execution_stage(query: str):
    route = route_matter(query)
    packs = source_packs_for_route(route, query)

    assert route.label == "Civil decree execution / attachment"
    cpc = next(pack for pack in packs if pack.id == "cpc_1908")
    assert cpc.anchor_patterns == ("/sec-51", "/sec-47")


@pytest.mark.parametrize(
    "query",
    (
        "Mere pati ne mujhe jaan se marne ki dhamki di.",
        "Mere husband ne mujhe jaan se maarne ki dhamki di.",
        "Mere husband ne bola ki aaj raat mujhe jala dega.",
    ),
)
def test_hindi_domestic_threat_owner_retrieves_pwdva_pack(query: str):
    route = route_matter(query)
    plan = build_matter_plan(query, route)

    assert route.category == "family_domestic"
    assert plan is not None
    assert plan.answer_policy.required_primary_owner == (
        "authority_graph:domestic_violence_immediate_safety"
    )
    assert any(source.source_pack_id == "pwdva_2005" for source in plan.retrieval_sources)
    must_cite = [entry for entry in plan.authority_ledger if entry.must_cite]
    assert any(entry.source_pack_id == "pwdva_2005" for entry in must_cite)


@pytest.mark.parametrize(
    "query",
    (
        "My husband told me that he will burn me",
        "My husband told me that he would poison me",
        "My husband told my sister that he will stab me tonight",
    ),
)
def test_reported_domestic_threat_owner_retrieves_pwdva_pack(query: str):
    route = route_matter(query)
    plan = build_matter_plan(query, route)

    assert route.category == "family_domestic"
    assert plan is not None
    assert plan.answer_policy.required_primary_owner == (
        "authority_graph:domestic_violence_immediate_safety"
    )
    assert any(source.source_pack_id == "pwdva_2005" for source in plan.retrieval_sources)
    must_cite = [entry for entry in plan.authority_ledger if entry.must_cite]
    assert any(entry.source_pack_id == "pwdva_2005" for entry in must_cite)


@pytest.mark.parametrize(
    "query",
    (
        "My husband said the mechanic will stab me",
        "My husband told me our tenant will poison me",
        "My tenant said he will poison me if I ask for rent",
        "My husband called 112 when our neighbour threatened to burn me",
    ),
)
def test_reported_third_party_threat_does_not_retrieve_pwdva(query: str):
    route = route_matter(query)
    plan = build_matter_plan(query, route)

    assert plan_owned_answer_route(query, route) is None
    assert plan is not None
    assert route.category == "criminal_general"
    assert route.label == "Third-party threat / personal safety"
    assert all(source.source_pack_id != "pwdva_2005" for source in plan.retrieval_sources)


@pytest.mark.parametrize(
    "query",
    (
        "Police denied any role in the freeze; the arbitral tribunal ordered it during the pending arbitration",
        "The bank says the debit freeze is under an arbitral interim order; police are not connected with it",
        "My bank account was frozen by an arbitral tribunal. Police did not request this freeze",
    ),
)
def test_arbitral_account_restraint_fails_closed_without_substitute_law(query: str):
    route = route_matter(query)
    plan = build_matter_plan(query, route)

    assert route.label == "Arbitral interim restraint / account attachment"
    assert plan_owned_answer_route(query, route) is None
    assert plan is not None
    assert plan.retrieval_sources == []
    assert any("Arbitration and Conciliation Act 1996" in source for source in route.required_sources)


def test_controlling_civil_source_gaps_require_handoff_before_answer_sentences():
    gap = {"has_gap": True}
    assert _controlling_source_gap_requires_handoff(
        "The arbitral tribunal froze my account during arbitration",
        gap,
    )
    assert _controlling_source_gap_requires_handoff(
        "The recovery suit is undecided and the court attached my account before judgment",
        gap,
    )
    assert not _controlling_source_gap_requires_handoff(
        "After decree the executing court attached my account",
        gap,
    )
    assert not _controlling_source_gap_requires_handoff(
        "The arbitral tribunal froze my account during arbitration",
        None,
    )


def test_hidden_custody_owner_binds_mandatory_retrieval_sources():
    query = "Crime Branch took my cousin away from his shop and the family cannot find which police station he is in"
    plan = build_matter_plan(query, route_matter(query))

    assert plan is not None
    assert plan.answer_policy.required_primary_owner == (
        "authority_graph:arrest_custody_station_case_not_disclosed"
    )
    must_cite = [entry for entry in plan.authority_ledger if entry.must_cite]
    assert must_cite
    assert all(entry.source_pack_id for entry in must_cite)


def test_unknown_date_bank_hold_binds_current_and_legacy_seizure_sources():
    query = "My account was blocked on the investigating officer's request"
    plan = build_matter_plan(query, route_matter(query))

    assert plan is not None
    assert route_matter(query).category == "banking_credit_dispute"
    pack_ids = {source.source_pack_id for source in plan.retrieval_sources}
    assert "bnss_2023_bank_account_legal_hold" in pack_ids
    assert "crpc_1973_bank_account_legal_hold" in pack_ids
    must_cite = [entry for entry in plan.authority_ledger if entry.must_cite]
    assert all(entry.source_pack_id for entry in must_cite)

    passages = [
        *_rbi_ombudsman_passages(1),
        _passage(6, "Bharatiya Nagarik Suraksha Sanhita 2023", "bnss-2023/sec-106", "bnss_2023_bank_account_legal_hold"),
        _passage(7, "Code of Criminal Procedure 1973", "crpc-1973/sec-102", "crpc_1973_bank_account_legal_hold"),
    ]
    workflow = _selected_workflow_result(query, route_matter(query), passages, plan)
    assert workflow is not None
    assert workflow.id == "bank_account_freeze_legal_hold"


@pytest.mark.parametrize(
    "query",
    (
        "Court froze my bank account during execution of a civil decree",
        "The civil court froze my account to satisfy a judgment",
        "The court froze my bank account to satisfy its judgment",
        "A court froze my bank account to enforce the money judgment",
        "The bank froze my account under an executing court order in a money suit",
        "Court put a lien on my salary account to recover the decretal amount",
    ),
)
def test_civil_judgment_account_attachment_never_adds_criminal_seizure_packs(query: str):
    route = route_matter(query)
    pack_ids = {pack.id for pack in source_packs_for_route(route, query)}

    assert "bnss_2023_bank_account_legal_hold" not in pack_ids
    assert "crpc_1973_bank_account_legal_hold" not in pack_ids


def test_plan_owned_route_can_only_render_its_named_contract(monkeypatch):
    query, _, owner = RELEASED_SCENARIOS[7]
    route = route_matter(query)
    plan = build_matter_plan(query, route)
    assert plan is not None

    provider, contract_id = owner.split(":", 1)
    expected = WorkflowTemplateResult(
        id=contract_id,
        source=provider,
        lines=["Expected owner line [1]."],
        answer_mode="primary",
    )
    monkeypatch.setattr(
        "apps.api.main.common_workflow_contract_result",
        lambda *_args, **_kwargs: expected,
    )
    assert _grounded_template_lines(query, route, [], plan=plan) == expected.lines
    assert _critical_route_needs_reviewed_contract(route, expected, plan=plan) is False

    competing = WorkflowTemplateResult(
        id="builder_rera",
        source="authority_graph",
        lines=["Competing reviewed line [1]."],
        answer_mode="primary",
    )
    monkeypatch.setattr(
        "apps.api.main.common_workflow_contract_result",
        lambda *_args, **_kwargs: competing,
    )
    assert _grounded_template_lines(query, route, [], plan=plan) == []
    assert _critical_route_needs_reviewed_contract(route, competing, plan=plan) is True

    event = _workflow_diagnostics_event(
        query,
        route,
        [],
        template_lines=[],
        plan=plan,
    )
    payload = json.loads(event["data"])
    assert payload["selected"] is False
    assert payload["answer_owner"] == "source_gap_handoff"
    assert payload["expected_plan_owner"] == owner
    assert payload["candidate_owner"] == "authority_graph:builder_rera"
    assert payload["contract_miss_reason"] == "plan_required_owner_not_selected"


def test_plan_owner_preempts_competing_global_contract_after_retrieval():
    query = "Cyber police put a lien on my frozen bank account but gave no notice"
    route = route_matter(query)
    plan = build_matter_plan(query, route)
    assert plan is not None
    passages = [
        {"index": 1, "title": "Information Technology Act 2000", "anchor": "it-act-2000/sec-66D"},
        {"index": 2, "title": "Bharatiya Nagarik Suraksha Sanhita 2023", "anchor": "bnss-2023/sec-106"},
        {"index": 4, "title": "Code of Criminal Procedure 1973", "anchor": "crpc-1973/sec-102"},
        *_rbi_ombudsman_passages(5),
    ]

    result = _selected_workflow_result(query, route, passages, plan)

    assert result is not None
    assert result.source == "authority_graph"
    assert result.id == "bank_account_freeze_legal_hold"


def _passage(index, title, anchor, pack, source_type="bare_act"):
    passage = {
        "index": index,
        "title": title,
        "anchor": anchor,
        "required_source_pack": pack,
        "source_type": source_type,
    }
    # Legacy fixtures model the production metadata for registry-owned
    # authorities so the provenance gate can remain strict about snapshots.
    snapshots = {
        "constitution of india": "2025-11-11",
        "reserve bank integrated ombudsman scheme 2021": "2022-08-05",
        "prevention of money laundering act 2002": "2024-08-30",
    }
    snapshot = snapshots.get(title.lower())
    if snapshot is not None:
        passage["as_at"] = snapshot
    vehicle_registry_ids = {
        ("bnss-2023/sec-173-a", "bnss_2023_vehicle_theft_fir"): "authority_34af1906c7f20fae0947",
        ("bnss-2023/sec-173-c", "bnss_2023_vehicle_theft_fir"): "authority_85fac6e1af26c07fb512",
        ("bnss-2023/sec-175", "bnss_2023_vehicle_theft_fir"): "authority_5b58f83601c4ab714da1",
        ("crpc-1973/sec-154", "crpc_1973_vehicle_theft_fir"): "authority_6358e656222ff6dcdae9",
    }
    authority_id = vehicle_registry_ids.get((anchor, pack))
    if authority_id is not None:
        passage["authority_ids"] = [authority_id]
        passage["text"] = {
            "bnss-2023/sec-173-a": f"{title}, Section 173\n173. Information in cognizable cases.",
            "bnss-2023/sec-173-c": f"{title}, Section 173(4)\n(4) Any person aggrieved by a refusal.",
            "bnss-2023/sec-175": f"{title}, Section 175\n175. Police officer power to investigate cognizable case.",
            "crpc-1973/sec-154": f"{title}, Section 154\n154. Information in cognizable cases.",
        }[anchor]
        if pack == "bnss_2023_vehicle_theft_fir":
            passage["as_at"] = "2024-07-01"
    if anchor.startswith("domestic-violence-2005-official/"):
        passage["document_id"] = "domestic-violence-2005-official"
    if (anchor, pack) == ("crpc-1973/sec-50", "crpc_1973_custody_registry"):
        passage["authority_ids"] = ["authority_dfa4588172eb8b0b41fa"]
        passage["required_source_pack_authority_ids"] = {
            "crpc_1973_custody_registry": ("authority_dfa4588172eb8b0b41fa",),
        }
    return passage


def test_vehicle_plan_owned_renderer_requires_offence_track_with_procedure_track():
    query = "My bike was stolen on 1 August 2024 and police refused to file FIR"
    route = route_matter(query)
    procedure_only = [
        _passage(1, "Bharatiya Nagarik Suraksha Sanhita 2023", "bnss-2023/sec-173-a", "bnss_2023_vehicle_theft_fir"),
        _passage(2, "Bharatiya Nagarik Suraksha Sanhita 2023", "bnss-2023/sec-173-c", "bnss_2023_vehicle_theft_fir"),
        _passage(3, "Bharatiya Nagarik Suraksha Sanhita 2023", "bnss-2023/sec-175", "bnss_2023_vehicle_theft_fir"),
    ]
    assert authority_graph_contract_template_result(
        query, route, procedure_only, "vehicle_theft_fir_refusal"
    ) is None

    complete = [
        *procedure_only,
        _passage(4, "Bharatiya Nyaya Sanhita 2023", "bns-2023/sec-303-a", "bns_2023_vehicle_theft"),
    ]
    workflow = authority_graph_contract_template_result(
        query, route, complete, "vehicle_theft_fir_refusal"
    )
    assert workflow is not None
    assert workflow.source_indices["bns"] == 4
    assert "bns" in workflow.required_sources


def test_caste_certificate_plan_owner_requires_exact_reviewed_source_packs():
    query = "my ST certificate was rejected what appeal"
    route = route_matter(query)
    valid = [
        _passage(
            1,
            "Constitution of India",
            "constitution-india/sec-342",
            "constitution_article_341_342",
        ),
        _passage(
            2,
            "Right to Information Act 2005",
            "rti-2005/sec-6",
            "rti_2005_certificate_record_request",
        ),
    ]
    workflow = authority_graph_contract_template_result(
        query,
        route,
        valid,
        "caste_certificate_state_rule_intake",
    )
    assert workflow is not None
    assert workflow.source_indices == {"constitution": 1, "rti": 2}

    wrong_pack = [
        {**valid[0], "required_source_pack": "constitution_article_22"},
        valid[1],
    ]
    assert authority_graph_contract_template_result(
        query,
        route,
        wrong_pack,
        "caste_certificate_state_rule_intake",
    ) is None

    unannotated = [{key: value for key, value in passage.items() if key != "required_source_pack"} for passage in valid]
    assert authority_graph_contract_template_result(
        query,
        route,
        unannotated,
        "caste_certificate_state_rule_intake",
    ) is None


def test_death_certificate_correction_has_a_dedicated_authority_owner():
    query = "death certificate has wrong name hospital says they cannot correct it what is process"
    route = route_matter(query)
    passages = [
        _passage(
            1,
            "Registration of Births and Deaths Act 1969",
            "registration-births-deaths-1969/sec-15",
            "births_deaths_registration_1969",
        ),
        _passage(2, "Right to Information Act 2005", "rti-2005/sec-6", "rti_2005"),
    ]

    workflow = authority_graph_contract_template_result(
        query,
        route,
        passages,
        "death_certificate_record_correction",
    )

    assert workflow is not None
    assert workflow.id == "death_certificate_record_correction"
    assert workflow.source_indices == {"registration": 1, "rti": 2}
    assert "death certificate" in " ".join(workflow.lines).lower()


def test_civil_record_copy_and_delayed_death_registration_have_distinct_owners():
    copy_query = "need duplicate death cert from municipality"
    copy_route = route_matter(copy_query)
    copy_passages = [
        _passage(
            1,
            "Registration of Births and Deaths Act 1969",
            "registration-births-deaths-1969/sec-17",
            "births_deaths_registration_1969",
        ),
    ]
    copy_workflow = authority_graph_contract_template_result(
        copy_query,
        copy_route,
        copy_passages,
        "civil_registration_certificate_copy",
    )
    assert copy_workflow is not None
    assert copy_workflow.source_indices == {"certificate_record": 1}
    assert "certified-copy" in " ".join(copy_workflow.lines)

    delayed_query = "death registration delayed by panchayat"
    delayed_route = route_matter(delayed_query)
    delayed_passages = [
        _passage(
            2,
            "Registration of Births and Deaths Act 1969",
            "registration-births-deaths-1969/sec-13",
            "births_deaths_registration_1969",
        ),
    ]
    delayed_workflow = authority_graph_contract_template_result(
        delayed_query,
        delayed_route,
        delayed_passages,
        "death_registration_delayed",
    )
    assert delayed_workflow is not None
    assert delayed_workflow.source_indices == {"delayed_registration": 2}
    assert "delayed" in " ".join(delayed_workflow.lines).lower()

    school_query = "school asked for birth cert copy to complete admission"
    school_route = route_matter(school_query)
    school_plan = build_matter_plan(school_query, school_route)
    assert school_plan is not None
    assert school_plan.answer_policy.required_primary_owner != (
        "authority_graph:civil_registration_certificate_copy"
    )

    delayed_conflict_query = "death certificate pending delayed at municipality"
    delayed_conflict_route = route_matter(delayed_conflict_query)
    delayed_resolution = resolve_plan_answer_ownership(
        delayed_conflict_query,
        delayed_conflict_route,
    )
    assert delayed_resolution.conflicts == ()
    assert delayed_resolution.owner is not None
    assert delayed_resolution.owner.scenario_id == "death_registration_delayed"

    school_record_query = "school asked for birth certificate but panchayat is not issuing it"
    school_record_route = route_matter(school_record_query)
    school_record_plan = build_matter_plan(school_record_query, school_record_route)
    assert school_record_plan is not None
    assert school_record_plan.answer_policy.required_primary_owner == (
        "authority_graph:civil_registration_certificate_issuance"
    )


@pytest.mark.parametrize(
    "query,expected_scenario",
    (
        ("school refused my daughter admission because birth certificate is missing", None),
        ("school delayed my daughter admission because birth certificate is not available", None),
        ("school is not giving admission because birth certificate is missing", None),
        ("death registration not done by municipality", "death_registration_delayed"),
        ("death certificate correction municipality wrong name", "death_certificate_record_correction"),
        ("death certificate correction pending at municipality", "death_certificate_record_correction"),
        ("death certificate wrong name pending at municipality", "death_certificate_record_correction"),
        ("death certificate has wrong name and registration is delayed", "death_certificate_record_correction"),
        ("death registration not done and death certificate wrong name", "death_certificate_record_correction"),
        ("birth certificate wrong name municipality correction", "birth_certificate_record_correction"),
        ("school asked for birth certificate but panchayat is not issuing it", "civil_registration_certificate_issuance"),
    ),
)
def test_civil_registration_owners_resolve_adversarial_near_misses(query, expected_scenario):
    route = route_matter(query)
    owner = plan_owned_answer_route(query, route)
    assert (owner.scenario_id if owner is not None else None) == expected_scenario


def test_scst_false_fir_bail_owner_renders_on_police_fir_route():
    query = "false SC/ST FIR police complaint against me"
    route = route_matter(query)
    plan = build_matter_plan(query, route)
    assert route.category == "police_fir"
    assert plan is not None
    assert plan.answer_policy.required_primary_owner == (
        "authority_graph:scst_poa_accused_bail_defence"
    )

    passages = [
        _passage(
            1,
            "Prevention of Scheduled Castes and Scheduled Tribes (Prevention of Atrocities) Act 1989",
            "sc-st-poa-1989/sec-18",
            "scst_poa_1989",
        ),
        _passage(
            2,
            "Prevention of Scheduled Castes and Scheduled Tribes (Prevention of Atrocities) Act 1989",
            "sc-st-poa-1989/sec-18-a",
            "scst_poa_1989",
        ),
    ]
    workflow = authority_graph_contract_template_result(
        query,
        route,
        passages,
        "scst_poa_accused_bail_defence",
    )
    assert workflow is not None
    assert workflow.source_indices == {"poa_section_18": 1, "poa_section_18a": 2}


def test_scst_police_fir_owner_augments_route_pack_with_bail_sections():
    query = "false SC/ST FIR police complaint against me"
    route = route_matter(query)
    plan = build_matter_plan(query, route)

    assert plan is not None
    poa_pack = next(
        source
        for source in plan.retrieval_sources
        if source.source_pack_id == "scst_poa_1989"
    )
    assert {"/sec-18", "/sec-18A"} <= set(poa_pack.anchor_patterns)
    assert "/sec-18" in poa_pack.search_query
    assert "/sec-18a" in poa_pack.search_query.lower()
    assert matter_plan_integrity_gap(plan, query) is None


def test_uapa_bail_is_registry_owned_and_scoped_to_verified_section_43d():
    query = (
        "urgent brother in jail 18 months UAPA bail when prima facie case "
        "made out kya hota how to complain"
    )
    route = route_matter(query)
    plan = build_matter_plan(query, route)

    assert plan is not None
    assert route.category == "criminal_defence_bail"
    assert plan.answer_policy.required_primary_owner == "authority_graph:uapa_prima_facie_bail"
    assert plan.answer_policy.allow_freeform_llm is False
    assert plan.incident_date_status == "not_applicable_for_uapa_bail"
    assert plan.legal_regime is None
    assert [source.source_pack_id for source in plan.retrieval_sources] == ["uapa_1967"]
    assert plan.retrieval_sources[0].authority_ids == ["authority_4a9efaf22e5cf2d3d226"]
    assert plan.retrieval_sources[0].anchor_patterns == ["/sec-43d"]
    assert [entry.registry_key for entry in plan.authority_ledger if entry.must_cite] == [
        "unlawful_activities_prevention_act_1967_section_43d"
    ]
    assert any("regular bail" in remedy for remedy in plan.remedies)
    assert any("default bail" in remedy for remedy in plan.remedies)
    assert all("prolonged" not in remedy for remedy in plan.remedies)
    assert plan.action_pack_id == "uapa_bail_43d"
    assert plan.action_pack_title == "UAPA Section 43D bail path"
    assert any("prima-facie finding" in step for step in plan.next_steps)
    assert any("Public Prosecutor report" in step for step in plan.next_steps)
    assert all("NDPS" not in step for step in plan.next_steps)
    assert any("first-remand date" in fact for fact in plan.required_facts)
    assert len([
        entry for entry in plan.authority_ledger
        if "Unlawful Activities" in (entry.canonical_name or "")
        or entry.act == "Unlawful Act"
    ]) == 1


@pytest.mark.parametrize(
    "query",
    (
        "I received a UAPA notice when should I appear before police",
        "Police searched my house under UAPA when can I get my phone back",
        "Police will not give me a copy of the UAPA FIR",
        "Can I challenge the sanction granted in my UAPA case",
        "Can a UAPA trial be transferred to another court",
        "How can an organisation challenge UAPA designation",
        "My brother arrested under UAPA is being beaten in custody",
        "UAPA prisoner in jail is denied medicine and hospital treatment",
        "My husband is in UAPA custody and family mulaqat is not allowed",
        "Police arrested my son under UAPA but will not tell us which station he is in",
        "Police seized my phone in UAPA case how can I get a release order",
        "How to release my seized car in a UAPA case",
        "UAPA case bank account frozen how to release my funds",
        "Court released my passport in UAPA case but police will not return it",
        "Can they release my seized phone in the UAPA case?",
        "They released my seized car after the UAPA case",
        "The officer told her that the court released her passport in the UAPA case",
        "Police told him they will release the phone seized in his UAPA case",
        "She asked that her phone be released in the UAPA case",
        "She wants her passport to be released in the UAPA case",
        "He requested his seized car be released in the UAPA case",
        "Police should release her seized phone in the UAPA case",
        "Court released her personal passport in the UAPA case",
        "Court released the applicant's passport in the UAPA case",
        "Court released my brother's seized scooter in the UAPA case",
        "The petitioner asked the court to release her seized jewellery in the UAPA case",
        "My brother asked when the seized cash will be released in the UAPA case",
        "My detained brother wants police to release the CCTV footage in the UAPA case",
        "The UAPA petitioner asked to release the organisation from the designation list",
        "The UAPA petitioner requests release of her seized passport",
        "My brother wants release of his seized scooter in the UAPA case",
        "The applicant needs release of frozen bank funds in the UAPA case",
        "The co-accused seeks release of seized cash in the UAPA case",
        "My detained brother requests release of CCTV footage in the UAPA case",
        "Court considered my brother's release of the seized vehicle in the UAPA case",
        "The UAPA petitioner requests release for her seized passport",
        "My brother wants release for his seized scooter in the UAPA case",
        "The co-accused requests release/return of seized cash in the UAPA case",
        "The UAPA applicant wants release order for the seized phone",
        "The petitioner requests release application for her vehicle in the UAPA case",
        "My brother needs urgent release order for his passport in the UAPA case",
        "My brother's release application is for the seized phone in the UAPA case",
        "The UAPA applicant wants release certificate for the seized phone",
        "Release the accused vehicle seized in the UAPA case",
        "Police should release the accused person's phone in the UAPA case",
        "Release the applicant-owned vehicle in the UAPA case",
        "UAPA bail is pending and police will not return my phone",
        "My UAPA 43D hearing is pending; return my seized laptop",
    ),
)
def test_non_bail_uapa_questions_do_not_get_section_43d_bail_ownership(query: str):
    route = route_matter(query)
    owner = plan_owned_answer_route(query, route)

    assert route.label != "UAPA bail / criminal defence"
    assert owner is None or owner.scenario_id != "uapa_prima_facie_bail"


def test_uapa_device_return_uses_specific_action_pack_and_plan():
    query = "UAPA bail is pending and police will not return my phone"
    route = route_matter(query)
    plan = build_matter_plan(query, route)

    assert route.label == "Police seizure of digital device"
    assert route.action_pack is not None
    assert route.action_pack.id == "police_seized_device_return"
    assert route.action_pack.title == "Seized device return path"
    assert "device IMEI, serial number, or asset tag" in route.action_pack.documents
    assert plan is not None
    assert plan.action_pack_id == "police_seized_device_return"
    assert plan.action_pack_title == "Seized device return path"
    assert any("interim custody" in step for step in plan.next_steps)
    owner = plan_owned_answer_route(query, route)
    assert owner is not None
    assert owner.scenario_id == "police_seized_device_return"
    assert {
        entry.authority_id
        for entry in plan.authority_ledger
        if entry.note == "registry_workflow_authority"
    } == {
        "authority_a304a271d59fa95369a8",
        "authority_d988aed56b26c0cd5541",
        "authority_351a65c5e6d8e32eb406",
        "authority_b56a3ee70bc63e048163",
        "authority_316cb0d8a467b1d9a046",
    }


def test_pure_uapa_device_return_does_not_create_person_release_secondary_issue():
    query = "Police seized my phone in a UAPA case and will not return it"
    route = route_matter(query)
    plan = build_matter_plan(query, route)

    assert route.label == "Police seizure of digital device"
    assert plan is not None
    assert plan.action_pack_id == "police_seized_device_return"
    assert "person-release language requires a separate bail review" not in plan.secondary_issues


def test_mixed_uapa_device_and_person_release_keeps_scoped_secondary_issue():
    query = "UAPA bail is pending and police will not return my phone"
    route = route_matter(query)
    plan = build_matter_plan(query, route)

    assert route.label == "Police seizure of digital device"
    assert plan is not None
    assert "person-release language requires a separate bail review" in plan.secondary_issues
    assert {
        authority_id
        for source in plan.retrieval_sources
        for authority_id in source.authority_ids
    } == {
        "authority_a304a271d59fa95369a8",
        "authority_d988aed56b26c0cd5541",
        "authority_351a65c5e6d8e32eb406",
        "authority_b56a3ee70bc63e048163",
        "authority_316cb0d8a467b1d9a046",
    }


@pytest.mark.parametrize(
    "query",
    (
        "UAPA Section 43D(5) bail rejected because accusation is prima facie true",
        "My brother is in UAPA custody and needs regular bail",
        "Brother has been in UAPA jail for 18 months with no trial started; can he get bail",
        "My brother and his phone are in custody under UAPA; can he be released?",
        "Can the UAPA detainee be released?",
        "Can the applicant be released under UAPA?",
        "Can he be released under UAPA?",
        "How to get my brother released under UAPA?",
        "I need my brother released from UAPA custody",
        "Need release for my brother in UAPA case",
        "How can I secure my husband's release under UAPA?",
        "What about release of the accused under UAPA?",
        "My UAPA co-accused seeks release",
        "Please get him released under UAPA",
        "She wants to be released from UAPA custody",
        "The applicant needs to be released under UAPA",
        "The petitioner requests his release under UAPA",
        "My brother seeks immediate release in the UAPA case",
        "Can court release him and release his seized phone in the UAPA case?",
        "Can court release my brother and release his phone in the UAPA case?",
        "Can they release the phone and release the UAPA detainee?",
        "Release my phone after he is released from UAPA custody",
        "I want him to be released under UAPA",
        "We need her to be released from UAPA custody",
        "I want my brother to be released under UAPA",
        "Help secure release for him in the UAPA case",
        "UAPA me brother ko release kaise karaye",
        "mera bhai UAPA me release kaise hoga",
        "UAPA case me husband ko release karwana hai",
        "Can the court release my younger brother under UAPA?",
        "Can the court release the main accused under UAPA?",
        "Please get my elderly father released under UAPA",
        "Can he please be released under UAPA?",
        "Can she also be released from UAPA custody?",
        "The applicant should immediately be released under UAPA",
        "UAPA me bhai ko kab release hoga",
        "UAPA case me bhai ko release chahiye",
        "The UAPA accused seeks release because police returned his phone",
        "My brother needs urgent release, police kept his phone in the UAPA case",
        "The UAPA petitioner requests release; his passport is still seized",
        "The co-accused wants temporary release in the UAPA case because his bank funds are frozen",
        "Please get my arrested brother released under UAPA",
        "The UAPA accused is seeking release",
        "My brother is asking for release in the UAPA case",
        "The applicant applies for release under UAPA",
        "Can the court grant release to the accused under UAPA?",
        "Can court release the second accused under UAPA?",
        "The UAPA accused seeks his release",
        "The UAPA applicant is seeking his release",
        "My brother is asking for his release in the UAPA case",
        "The accused filed an application for release under UAPA",
        "Release application for the accused under UAPA",
        "The accused filed a release application under UAPA",
        "The accused moved an application for release under UAPA",
        "The applicant submitted an application for release under UAPA",
        "Release plea for the second accused under UAPA",
    ),
)
def test_explicit_uapa_bail_custody_and_delay_signals_keep_section_43d_owner(query: str):
    route = route_matter(query)
    owner = plan_owned_answer_route(query, route)

    assert route.label == "UAPA bail / criminal defence"
    assert owner is not None
    assert owner.scenario_id == "uapa_prima_facie_bail"


def _rbi_ombudsman_passages(start=1, *, pack="rbi_integrated_ombudsman_2021"):
    title = "Reserve Bank Integrated Ombudsman Scheme 2021"
    return [
        _passage(start + offset, title, f"rbi-integrated-ombudsman-2021/sec-{clause}", pack)
        for offset, clause in enumerate((1, 3, 6, 9, 10))
    ]


def _pmla_asset_passages(*, attachment: bool, start: int = 1):
    path_section = 5 if attachment else 17
    path_pack = (
        "pmla_2002_provisional_attachment"
        if attachment
        else "pmla_2002_search_freeze"
    )
    passages = [
        _passage(
            start,
            "Prevention of Money Laundering Act 2002",
            f"pmla-2002/sec-{path_section}",
            path_pack,
        ),
        _passage(
            start + 1,
            "Prevention of Money Laundering Act 2002",
            "pmla-2002/sec-8",
            "pmla_2002_asset_adjudication",
        ),
        _passage(
            start + 2,
            "Prevention of Money Laundering Act 2002",
            "pmla-2002/sec-26",
            "pmla_2002_asset_appeal",
        ),
    ]
    for passage in passages:
        passage["as_at"] = "2024-08-30"
    return passages


def _pmla_ambiguous_restraint_passages():
    passages = [
        _passage(1, "Prevention of Money Laundering Act 2002", "pmla-2002/sec-5", "pmla_2002_provisional_attachment"),
        _passage(2, "Prevention of Money Laundering Act 2002", "pmla-2002/sec-17", "pmla_2002_search_freeze"),
        _passage(3, "Prevention of Money Laundering Act 2002", "pmla-2002/sec-8", "pmla_2002_asset_adjudication"),
        _passage(4, "Prevention of Money Laundering Act 2002", "pmla-2002/sec-26", "pmla_2002_asset_appeal"),
    ]
    for passage in passages:
        passage["as_at"] = "2024-08-30"
    return passages


def _loan_app_registry_passages():
    return [
        _passage(1, "Reserve Bank of India (Digital Lending) Directions, 2025", "rbi-digital-lending-directions-2025/para-11", "rbi_digital_lending_directions_2025", "guideline"),
        _passage(2, "Reserve Bank of India (Digital Lending) Directions, 2025", "rbi-digital-lending-directions-2025/para-12", "rbi_digital_lending_directions_2025", "guideline"),
        _passage(3, "Outsourcing of Financial Services - Responsibilities of regulated entities employing Recovery Agents", "rbi-recovery-agents-2022/para-2", "rbi_recovery_agents_2022", "circular"),
        *_rbi_ombudsman_passages(4),
    ]


def _custody_registry_passages(regime="unknown", start=1):
    passages = [
        _passage(start, "Constitution of India", "constitution-india/sec-22", "constitution_article_22"),
        _passage(start + 1, "Constitution of India", "constitution-india/sec-226", "constitution_article_226_habeas"),
    ]
    if regime in {"unknown", "legacy"}:
        passages.append(_passage(
            start + len(passages),
            "Bharatiya Nagarik Suraksha Sanhita 2023",
            "bnss-2023/sec-531",
            "bnss_2023_custody_registry",
        ))
    if regime == "current":
        for section in (36, 37, 47, 48, 57, 58):
            passages.append(_passage(
                start + len(passages),
                "Bharatiya Nagarik Suraksha Sanhita 2023",
                f"bnss-2023/sec-{section}",
                "bnss_2023_custody_registry",
            ))
    if regime == "legacy":
        for section in ("41-b", "41-c", "50", "50-a", "56", "57"):
            passages.append(_passage(
                start + len(passages),
                "Code of Criminal Procedure 1973",
                f"crpc-1973/sec-{section}",
                "crpc_1973_custody_registry",
            ))
    if regime == "geographic_exception":
        passages.append(_passage(
            start + len(passages),
            "Bharatiya Nagarik Suraksha Sanhita 2023",
            "bnss-2023/sec-1",
            "bnss_2023_custody_registry",
        ))
    return passages


@pytest.mark.parametrize(
    "query,passages",
    (
            ("My husband is beating me right now", [
                _passage(1, "Protection of Women from Domestic Violence Act 2005", "domestic-violence-2005-official/sec-3-official", "pwdva_2005"),
        ]),
        ("Police picked my son at night and gave no FIR copy", _custody_registry_passages()),
        ("Police arrested my son for being gay", [
            _passage(1, "NAVTEJ SINGH JOHAR & ORS. versus UNION OF INDIA", "2018-insc-790#header", "navtej_lgbtq_liberty", "sc_judgment"),
            _passage(2, "Bharatiya Nagarik Suraksha Sanhita 2023", "bnss-2023/sec-47", "bnss_2023"),
            _passage(3, "Bharatiya Nagarik Suraksha Sanhita 2023", "bnss-2023/sec-57", "bnss_2023"),
                _passage(4, "Code of Criminal Procedure 1973", "crpc-1973/sec-50", "crpc_1973_custody_registry"),
            _passage(5, "Code of Criminal Procedure 1973", "crpc-1973/sec-57", "crpc_1973"),
        ]),
        ("My bike is stolen and police is not filing FIR", [
            _passage(1, "Bharatiya Nagarik Suraksha Sanhita 2023", "bnss-2023/sec-173-a", "bnss_2023_vehicle_theft_fir"),
            _passage(2, "Bharatiya Nagarik Suraksha Sanhita 2023", "bnss-2023/sec-173-c", "bnss_2023_vehicle_theft_fir"),
            _passage(3, "Bharatiya Nagarik Suraksha Sanhita 2023", "bnss-2023/sec-175", "bnss_2023_vehicle_theft_fir"),
            _passage(4, "Bharatiya Nyaya Sanhita 2023", "bns-2023/sec-303", "bns_2023_vehicle_theft"),
            _passage(5, "Code of Criminal Procedure 1973", "crpc-1973/sec-154", "crpc_1973_vehicle_theft_fir"),
            _passage(6, "Indian Penal Code 1860", "ipc-1860/sec-378", "ipc_1860_vehicle_theft"),
        ]),
        ("Loan app is harassing my contacts and sending my photo", _loan_app_registry_passages()),
        ("Cyber police put a lien on my frozen bank account", [
            *_rbi_ombudsman_passages(1),
            _passage(6, "Bharatiya Nagarik Suraksha Sanhita 2023", "bnss-2023/sec-106", "bnss_2023_bank_account_legal_hold"),
            _passage(7, "Code of Criminal Procedure 1973", "crpc-1973/sec-102", "crpc_1973_bank_account_legal_hold"),
        ]),
        (
            "Enforcement Directorate froze my bank account under PMLA",
            _pmla_asset_passages(attachment=False),
        ),
        ("Bank deducted money wrongly and customer care is not helping", _rbi_ombudsman_passages()),
        ("The insurer is rejecting my claim", [
            _passage(1, "Insurance Ombudsman Rules 2017", "insurance-ombudsman-rules-2017/sec-13", "insurance_ombudsman_rules_2017"),
            _passage(2, "Insurance Ombudsman Rules 2017", "insurance-ombudsman-rules-2017/sec-14", "insurance_ombudsman_rules_2017"),
        ]),
        ("My brother and I bought a plot and he sold the whole plot without me", [
            _passage(1, "Transfer of Property Act 1882", "transfer-of-property-1882/sec-44", "transfer_property_1882"),
        ]),
        ("My wife refuses physical intimacy for one year, what lawful remedy exists", [
            _passage(1, "Family Courts Act 1984", "family-courts-1984/sec-7", "family_courts_1984"),
        ]),
    ),
)
def test_plan_owner_source_activation_does_not_emit_false_gap(query: str, passages: list[dict]):
    route = route_matter(query)
    plan = build_matter_plan(query, route)
    assert plan is not None

    missing = missing_plan_authorities(
        plan=plan,
        passages=passages,
        query=query,
    )

    assert missing == []


@pytest.mark.parametrize(
    "query,attachment,expected_path,unexpected_path",
    (
        (
            "Enforcement Directorate froze my bank account under PMLA",
            False,
            "PMLA Section 17(1A)",
            "PMLA Section 5",
        ),
        (
            "ED issued a provisional attachment order for my property under PMLA",
            True,
            "PMLA Section 5",
            "PMLA Section 17(1A)",
        ),
        (
            "ED issued a provisional attachment order for my bank account under PMLA",
            True,
            "PMLA Section 5",
            "PMLA Section 17(1A)",
        ),
    ),
)
def test_pmla_asset_restraint_renders_only_the_active_legal_path(
    query: str,
    attachment: bool,
    expected_path: str,
    unexpected_path: str,
):
    route = route_matter(query)
    plan = build_matter_plan(query, route)
    assert plan is not None

    passages = _pmla_asset_passages(attachment=attachment)
    workflow = _selected_workflow_result(query, route, passages, plan)

    assert workflow is not None
    assert workflow.id == "pmla_ed_asset_freeze"
    assert workflow.answer_mode == "primary"
    assert not _critical_route_needs_reviewed_contract(route, workflow, plan=plan)
    rendered = " ".join(workflow.lines)
    assert expected_path in rendered
    assert unexpected_path not in rendered
    assert "PMLA Section 8" in rendered
    assert "Section 26" in rendered
    assert "45 days" in rendered
    assert "Get the complete freezing or provisional-attachment order" in rendered
    if attachment:
        assert "180 days" in rendered
        assert "scheduled-offence report or complaint" in rendered
        assert "immediate-attachment exception" in rendered
        assert "whichever is earlier" in rendered
        assert "within 30 days of attachment" in rendered
        assert "not below Deputy Director" in rendered
        assert "immediately after attachment" in rendered
    else:
        assert "authorised officer" in rendered
        assert "reason to believe" in rendered
        assert "continuation within 30 days" in rendered
        assert "immediately after" in rendered
    assert _route_regime_caveat(route, workflow) is None
    assert not missing_plan_authorities(plan=plan, passages=passages, query=query)
    undated_passages = [
        {key: value for key, value in passage.items() if key != "as_at"}
        for passage in passages
    ]
    assert missing_plan_authorities(
        plan=plan,
        passages=undated_passages,
        query=query,
    )


@pytest.mark.parametrize("missing_section", (8, 26))
def test_pmla_asset_restraint_fails_closed_when_controlling_source_is_missing(
    missing_section: int,
):
    query = "Enforcement Directorate froze my bank account under PMLA"
    route = route_matter(query)
    plan = build_matter_plan(query, route)
    assert plan is not None
    passages = [
        passage
        for passage in _pmla_asset_passages(attachment=False)
        if not passage["anchor"].endswith(f"/sec-{missing_section}")
    ]

    assert missing_plan_authorities(plan=plan, passages=passages, query=query)
    assert _selected_workflow_result(query, route, passages, plan) is None


def test_insurance_owner_requires_scope_and_procedure_as_separate_authorities():
    query = "My health insurer rejected my claim even though I disclosed it"
    plan = build_matter_plan(query, route_matter(query))
    assert plan is not None

    must_cite = [entry for entry in plan.authority_ledger if entry.must_cite]
    assert len(must_cite) == 2
    assert {entry.source_pack_id for entry in must_cite} == {"insurance_ombudsman_rules_2017"}
    assert {tuple(entry.required_anchor_patterns) for entry in must_cite} == {
        ("/sec-13",),
        ("/sec-14",),
    }
    assert len({entry.authority_id for entry in must_cite}) == 2


@pytest.mark.parametrize(
    "query",
    (
        "My husband forces sex after I say no",
        "My husband is forcing me for sex and threatening me",
    ),
)
def test_marital_sexual_coercion_uses_pwdva_safety_owner_without_conflict(query: str):
    route = route_matter(query)
    resolution = resolve_plan_answer_ownership(query, route)
    plan = build_matter_plan(query, route)

    assert resolution.owner is not None
    assert resolution.owner.owner_token == "authority_graph:domestic_violence_immediate_safety"
    assert resolution.conflicts == ()
    assert plan is not None
    must_cite = [entry for entry in plan.authority_ledger if entry.must_cite]
    assert len(must_cite) == 1
    assert must_cite[0].required_anchor_patterns == ["/sec-3"]
    assert "domestic violence" in must_cite[0].act.lower()

    passages = [
        {
            **_passage(
            1,
            "Protection of Women from Domestic Violence Act 2005",
            "domestic-violence-2005-official/sec-3-official",
            "pwdva_2005",
            ),
            "document_id": "domestic-violence-2005-official",
        }
    ]
    workflow = _selected_workflow_result(query, route, passages, plan)

    assert workflow is not None
    joined = " ".join(workflow.lines)
    assert "sexual abuse" in joined
    assert "Immediate safety" in joined
    assert missing_plan_authorities(plan=plan, passages=passages, query=query) == []


def test_acid_threat_plan_owner_is_specific_and_does_not_mislabel_bns_section():
    query = "please help my mother in law is threatening to throw acid on me if I do not get more money from my parents"
    route = route_matter(query)
    plan = build_matter_plan(query, route)
    passages = [
        {"index": 1, "title": "Protection of Women from Domestic Violence Act 2005", "anchor": "domestic-violence-2005/sec-18"},
        {"index": 2, "title": "Bharatiya Nyaya Sanhita 2023", "anchor": "bns-2023/sec-125"},
        {"index": 3, "title": "Bharatiya Nagarik Suraksha Sanhita 2023", "anchor": "bnss-2023/sec-173"},
        {"index": 8, "title": "Protection of Women from Domestic Violence Act 2005", "anchor": "domestic-violence-2005/sec-3"},
    ]

    assert plan is not None
    workflow = _selected_workflow_result(query, route, passages, plan)

    assert workflow is not None
    rendered = " ".join(workflow.lines)
    assert "reported acid threat" in rendered
    assert "Preserve the exact threat" in rendered
    assert "because the question does not confirm that role" not in rendered
    assert "Section 115" not in rendered
    assert "Section 125" not in rendered


def test_acid_sign_papers_plan_owner_does_not_add_unstated_money_facts():
    query = "my mother in law is threatening to throw acid if I do not sign papers"
    route = route_matter(query)
    plan = build_matter_plan(query, route)
    passages = [
        {"index": 1, "title": "Protection of Women from Domestic Violence Act 2005", "anchor": "domestic-violence-2005/sec-18"},
        {"index": 2, "title": "Bharatiya Nyaya Sanhita 2023", "anchor": "bns-2023/sec-125"},
        {"index": 4, "title": "Bharatiya Nagarik Suraksha Sanhita 2023", "anchor": "bnss-2023/sec-173-b"},
        {"index": 8, "title": "Protection of Women from Domestic Violence Act 2005", "anchor": "domestic-violence-2005/sec-3"},
    ]

    assert plan is not None
    workflow = _selected_workflow_result(query, route, passages, plan)
    assert workflow is not None
    rendered = " ".join(workflow.lines).lower()
    assert "money or dowry pressure" not in rendered
    assert "money-demand proof" not in rendered


def test_acid_attack_phrase_is_still_treated_as_threat_until_completion_facts_exist():
    query = "my mother in law threatened me with an acid attack"
    route = route_matter(query)
    plan = build_matter_plan(query, route)
    passages = [
        _passage(1, "Protection of Women from Domestic Violence Act 2005", "domestic-violence-2005/sec-18", "pwdva_2005"),
        _passage(2, "Bharatiya Nyaya Sanhita 2023", "bns-2023/sec-124", "bns_2023_acid_attack"),
        _passage(3, "Bharatiya Nagarik Suraksha Sanhita 2023", "bnss-2023/sec-173", "bnss_2023_fir_information_acid"),
        _passage(8, "Protection of Women from Domestic Violence Act 2005", "domestic-violence-2005/sec-3", "pwdva_2005"),
    ]

    assert plan is not None
    workflow = _selected_workflow_result(query, route, passages, plan)
    assert workflow is not None
    rendered = " ".join(workflow.lines).lower()
    assert "threat to throw acid" in rendered
    assert "section 124" not in rendered
    assert "hospital" not in rendered
    assert "money from your parents" not in rendered


def test_acid_plan_owner_rejects_foreign_packs_and_keeps_legacy_track_visible():
    query = "my mother in law threatened to throw acid on me and beats me"
    route = route_matter(query)
    plan = build_matter_plan(query, route)
    passages = [
        _passage(1, "Protection of Women from Domestic Violence Act 2005", "domestic-violence-2005/sec-3", "pwdva_2005"),
        _passage(2, "Bharatiya Nyaya Sanhita 2023", "bns-2023/sec-351", "bns_2023"),
        _passage(3, "Bharatiya Nagarik Suraksha Sanhita 2023", "bnss-2023/sec-173", "bnss_2023"),
        _passage(4, "Indian Penal Code 1860", "ipc-1860/sec-506", "ipc_1860"),
        _passage(5, "Code of Criminal Procedure 1973", "crpc-1973/sec-154", "crpc_1973"),
        _passage(6, "Bharatiya Nyaya Sanhita 2023", "bns-2023/sec-351", "bns_2023_acid_attack"),
        _passage(7, "Bharatiya Nagarik Suraksha Sanhita 2023", "bnss-2023/sec-173", "bnss_2023_fir_information_acid"),
        _passage(8, "Indian Penal Code 1860", "ipc-1860/sec-506", "ipc_1860_acid_attack"),
        _passage(9, "Code of Criminal Procedure 1973", "crpc-1973/sec-154", "crpc_1973_fir_information_acid"),
    ]

    assert plan is not None
    workflow = authority_graph_contract_template_result(
        query,
        route,
        passages,
        "domestic_violence_immediate_safety",
    )

    assert workflow is not None
    assert workflow.source_indices["bns"] == 6
    assert workflow.source_indices["bnss"] == 7
    assert workflow.source_indices["ipc"] == 8
    assert workflow.source_indices["crpc"] == 9
    rendered = " ".join(workflow.lines)
    assert "pre-2024 incident" in rendered
    assert "older CrPC" not in rendered


def test_generic_domestic_kill_threat_keeps_reviewed_safety_owner():
    query = "my husband says he will kill me and I am afraid"
    route = route_matter(query)
    passages = [
        _passage(1, "Protection of Women from Domestic Violence Act 2005", "domestic-violence-2005/sec-3", "pwdva_2005"),
        _passage(2, "Protection of Women from Domestic Violence Act 2005", "domestic-violence-2005/sec-18", "pwdva_2005"),
        _passage(3, "Bharatiya Nyaya Sanhita 2023", "bns-2023/sec-351", "bns_2023"),
        _passage(4, "Bharatiya Nagarik Suraksha Sanhita 2023", "bnss-2023/sec-173", "bnss_2023"),
    ]
    workflow = authority_graph_contract_template_result(
        query,
        route,
        passages,
        "domestic_violence_immediate_safety",
    )
    assert workflow is not None
    assert "Immediate safety" in " ".join(workflow.lines)


def test_legacy_completed_acid_owner_renders_ipc_crpc_only_source_set():
    query = "in 2023 my husband beat me and threw acid on me and I went to hospital"
    route = route_matter(query)
    passages = [
        _passage(1, "Protection of Women from Domestic Violence Act 2005", "domestic-violence-2005/sec-3", "pwdva_2005"),
        _passage(2, "Protection of Women from Domestic Violence Act 2005", "domestic-violence-2005/sec-18", "pwdva_2005"),
        _passage(3, "Indian Penal Code 1860", "ipc-1860/sec-326a", "ipc_1860_acid_attack"),
        _passage(4, "Code of Criminal Procedure 1973", "crpc-1973/sec-154", "crpc_1973_fir_information_acid"),
    ]
    workflow = authority_graph_contract_template_result(
        query,
        route,
        passages,
        "domestic_violence_immediate_safety",
    )
    assert workflow is not None
    assert workflow.source_indices == {"pwdva": 1, "pwdva_protection": 2, "ipc": 3, "crpc": 4}
    rendered = " ".join(workflow.lines)
    assert "pre-2024 incident" in rendered
    assert "pre-2024 police complaint" in rendered


@pytest.mark.parametrize(
    ("query", "bns_anchor", "expected", "unexpected"),
    (
        (
            "my husband beat me and I am unsafe",
            "bns-2023/sec-117",
            "Section 117",
            "Section 115",
        ),
        (
            "my husband threatened to kill me",
            "bns-2023/sec-115",
            None,
            "Section 115",
        ),
        (
            "my husband beat me and I am unsafe",
            "bns-2023/sec-1150",
            None,
            "Section 115",
        ),
    ),
)
def test_domestic_bns_claim_requires_exact_anchor_and_matching_facts(
    query: str,
    bns_anchor: str,
    expected: str | None,
    unexpected: str,
):
    route = route_matter(query)
    plan = build_matter_plan(query, route)
    passages = [
        {"index": 1, "title": "Protection of Women from Domestic Violence Act 2005", "anchor": "domestic-violence-2005/sec-3"},
        {"index": 2, "title": "Bharatiya Nyaya Sanhita 2023", "anchor": bns_anchor},
    ]

    assert plan is not None
    workflow = _selected_workflow_result(query, route, passages, plan)
    assert workflow is not None
    rendered = " ".join(workflow.lines)
    if expected is not None:
        assert expected in rendered
    assert unexpected not in rendered


def test_insurance_rule_5_alone_cannot_activate_plan_owner():
    query = "My insurer rejected my health claim"
    route = route_matter(query)
    plan = build_matter_plan(query, route)
    assert plan is not None
    rule_5_only = [
        {
            "index": 1,
            "title": "Insurance Ombudsman Rules 2017",
            "anchor": "insurance-ombudsman-rules-2017/sec-5-h",
            "source_type": "bare_act",
        }
    ]

    workflow = _selected_workflow_result(query, route, rule_5_only, plan)
    source_gap = build_source_gap_event(
        query=query,
        route_category=route.category,
        required_sources=route.required_sources or [],
        passages=rule_5_only,
        plan=plan,
    )

    assert workflow is None
    assert source_gap is not None
    assert source_gap["has_gap"] is True
    assert {item["required_anchor_patterns"][0] for item in source_gap["missing_required_sources"]} == {
        "/sec-13",
        "/sec-14",
    }


def test_composite_plan_owner_conflict_fails_closed_without_exception():
    query = "Loan app is harassing my contacts and insurer rejected my claim"
    route = route_matter(query)
    resolution = resolve_plan_answer_ownership(query, route)
    plan = build_matter_plan(query, route)

    assert resolution.owner is None
    assert len(resolution.conflicts) >= 2
    assert plan is not None
    assert plan.answer_policy.required_primary_owner == "source_gap_handoff"
    assert plan.answer_policy.fallback_reason == "multiple_plan_owners"
    assert plan.answer_policy.conflicting_primary_owners == list(resolution.conflicts)
    assert plan.answer_policy.allow_freeform_llm is False
    assert _selected_workflow_result(query, route, [], plan) is None
    assert _grounded_template_lines(
        query,
        route,
        [],
        plan=plan,
        workflow_result=None,
    ) == []

    source_gap = build_source_gap_event(
        query=query,
        route_category=route.category,
        required_sources=route.required_sources or [],
        passages=[],
        plan=plan,
    )
    assert source_gap is not None
    assert source_gap["gap_kinds"] == ["answer_owner_ambiguity"]
    assert source_gap["policy"] == "separate_conflicting_answer_owners"


def test_insurance_premium_claim_is_not_hijacked_by_wrong_bank_debit_owner():
    query = "Bank deducted an insurance premium wrongly and insurer rejected my claim"
    resolution = resolve_plan_answer_ownership(query, route_matter(query))

    assert resolution.owner is not None
    assert resolution.owner.owner_token == "authority_graph:insurance_claim_or_misselling"
    assert resolution.conflicts == ()


def test_bank_duplicate_insurance_premium_uses_bank_debit_owner():
    query = "Bank deducted my insurance premium twice"
    resolution = resolve_plan_answer_ownership(query, route_matter(query))

    assert resolution.owner is not None
    assert resolution.owner.owner_token == "authority_graph:wrong_bank_debit"
    assert resolution.conflicts == ()


def test_standalone_lic_claim_uses_insurance_owner_without_matching_police():
    query = "LIC rejected my claim"
    route = route_matter(query)
    resolution = resolve_plan_answer_ownership(query, route)

    assert route.category == "consumer"
    assert resolution.owner is not None
    assert resolution.owner.owner_token == "authority_graph:insurance_claim_or_misselling"
    assert resolution.conflicts == ()

    police_query = "Police sent me notice in a cyber fraud case"
    police_resolution = resolve_plan_answer_ownership(
        police_query,
        route_matter(police_query),
    )
    assert police_resolution.owner is None


def test_compatible_identity_and_custody_tracks_render_urgent_first():
    query = "Police picked my son for being gay from home at night and gave no FIR copy"
    route = route_matter(query)
    resolution = resolve_plan_answer_ownership(query, route)
    plan = build_matter_plan(query, route)

    assert resolution.owner is not None
    assert resolution.owner.owner_token == "authority_graph:lgbtq_identity_arrest_safeguard"
    assert [owner.owner_token for owner in resolution.additional_owners] == [
        "authority_graph:arrest_custody_station_case_not_disclosed"
    ]
    assert plan is not None
    assert plan.answer_policy.additional_primary_owners == [
        "authority_graph:arrest_custody_station_case_not_disclosed"
    ]
    passages = [
        _passage(1, "NAVTEJ SINGH JOHAR & ORS. versus UNION OF INDIA", "2018-insc-790#header", "navtej_lgbtq_liberty", "sc_judgment"),
        _passage(2, "Bharatiya Nagarik Suraksha Sanhita 2023", "bnss-2023/sec-47", "bnss_2023"),
        _passage(3, "Bharatiya Nagarik Suraksha Sanhita 2023", "bnss-2023/sec-57", "bnss_2023"),
        _passage(4, "Code of Criminal Procedure 1973", "crpc-1973/sec-50", "crpc_1973"),
        _passage(5, "Code of Criminal Procedure 1973", "crpc-1973/sec-57", "crpc_1973"),
        *_custody_registry_passages(start=6),
    ]
    result = _selected_workflow_result(query, route, passages, plan)
    assert result is not None
    joined = " ".join(result.lines)
    assert joined.index("Being gay") < joined.index("Related urgent legal track")
    assert "FIR copy" in joined


def test_caretaker_will_drafting_does_not_add_post_death_validity_track():
    query = (
        "what to do father has 4 children 2 daughters wants to make will "
        "giving more to caretaker daughter valid is this legal"
    )
    route = route_matter(query)
    resolution = resolve_plan_answer_ownership(query, route)
    plan = build_matter_plan(query, route)

    assert route.category == "succession_inheritance"
    assert resolution.owner is not None
    assert resolution.owner.owner_token == "authority_graph:caretaker_daughter_will"
    assert resolution.additional_owners == ()
    assert plan is not None
    assert plan.answer_policy.required_primary_owner == (
        "authority_graph:caretaker_daughter_will"
    )
    assert plan.answer_policy.additional_primary_owners == []
    assert plan.answer_policy.fallback_reason is None


def test_caretaker_will_before_death_does_not_add_validity_track():
    query = "father wants to make a will giving more to caretaker daughter valid before death"
    resolution = resolve_plan_answer_ownership(query, route_matter(query))

    assert resolution.owner is not None
    assert resolution.owner.owner_token == "authority_graph:caretaker_daughter_will"
    assert resolution.additional_owners == ()


def test_unrelated_death_evidence_does_not_add_validity_track_to_drafting():
    query = (
        "father wants to make a will giving more to caretaker daughter; "
        "my mother died and I have her death certificate"
    )
    resolution = resolve_plan_answer_ownership(query, route_matter(query))

    assert resolution.owner is not None
    assert resolution.owner.owner_token == "authority_graph:caretaker_daughter_will"
    assert resolution.additional_owners == ()


def test_unrelated_death_evidence_does_not_add_validity_track_to_existing_will():
    query = (
        "father has a will giving more to caretaker daughter; "
        "my mother died and her death certificate is available"
    )
    resolution = resolve_plan_answer_ownership(query, route_matter(query))

    assert resolution.owner is not None
    assert resolution.owner.owner_token == "authority_graph:caretaker_daughter_will"
    assert resolution.additional_owners == ()


def test_reverse_order_unrelated_death_does_not_add_validity_track():
    query = (
        "mother died and father has a will giving more to caretaker daughter; "
        "is the will valid"
    )
    resolution = resolve_plan_answer_ownership(query, route_matter(query))

    assert resolution.owner is not None
    assert resolution.owner.owner_token == "authority_graph:caretaker_daughter_will"
    assert resolution.additional_owners == ()


def test_death_of_another_person_after_will_does_not_add_validity_track():
    query = (
        "father has a will giving more to caretaker daughter; after the death "
        "of his mother, is the will valid"
    )
    resolution = resolve_plan_answer_ownership(query, route_matter(query))

    assert resolution.owner is not None
    assert resolution.owner.owner_token == "authority_graph:caretaker_daughter_will"
    assert resolution.additional_owners == ()


def test_compatible_caretaker_will_and_post_death_validity_tracks_render():
    query = (
        "father died and left an unregistered will giving more to the caretaker "
        "daughter; the heirs ask whether it is valid"
    )
    route = route_matter(query)
    resolution = resolve_plan_answer_ownership(query, route)
    plan = build_matter_plan(query, route)

    assert resolution.owner is not None
    assert resolution.owner.owner_token == "authority_graph:caretaker_daughter_will"
    assert [owner.owner_token for owner in resolution.additional_owners] == [
        "authority_graph:unregistered_will_validity"
    ]
    assert plan is not None
    assert plan.answer_policy.additional_primary_owners == [
        "authority_graph:unregistered_will_validity"
    ]
    passages = [
        _passage(1, "Indian Succession Act 1925", "indian-succession-1925/sec-63", "indian_succession_1925"),
        _passage(2, "Indian Succession Act 1925", "indian-succession-1925/sec-59", "indian_succession_1925"),
        _passage(3, "Registration Act 1908", "registration-1908/sec-18", "registration_1908"),
    ]
    result = _selected_workflow_result(query, route, passages, plan)
    assert result is not None
    joined = " ".join(result.lines)
    assert "Related urgent legal track" in joined
    assert "Because sons/heirs are fighting after death" in joined


def test_dpdp_section_13_is_clocked_and_not_current_law():
    assert dpdp_section_13_in_force(as_of=date(2026, 7, 15)) is False
    assert dpdp_section_13_in_force(as_of=date(2027, 5, 12)) is False
    assert dpdp_section_13_in_force(as_of=date(2027, 5, 13)) is True


def test_plan_owner_missing_must_cite_source_cannot_render():
    query = "Loan app is harassing my contacts and sending my photo"
    route = route_matter(query)
    plan = build_matter_plan(query, route)
    assert plan is not None
    rbi_only = [{
        "index": 1,
        "title": "Reserve Bank Integrated Ombudsman Scheme 2021",
        "anchor": "rbi-integrated-ombudsman-2021/sec-2",
        "source_type": "bare_act",
    }]

    workflow = _selected_workflow_result(query, route, rbi_only, plan)
    source_gap = build_source_gap_event(
        query=query,
        route_category=route.category,
        required_sources=route.required_sources or [],
        passages=rbi_only,
        plan=plan,
    )

    assert workflow is None
    assert source_gap is not None
    assert source_gap["has_gap"] is True
    assert _grounded_template_lines(
        query,
        route,
        rbi_only,
        plan=plan,
        workflow_result=workflow,
    ) == []
    assert _critical_route_needs_reviewed_contract(
        route,
        workflow,
        plan=plan,
        source_gap_event=source_gap,
    ) is True


def test_wrong_bank_debit_does_not_cite_section_35_from_section_2_passage():
    query = "Bank deducted money wrongly and customer care is not helping"
    route = route_matter(query)
    plan = build_matter_plan(query, route)
    assert plan is not None
    passages = [
        {
            "index": 1,
            "title": "Reserve Bank Integrated Ombudsman Scheme 2021",
            "anchor": "rbi-integrated-ombudsman-2021/sec-2",
        },
        {
            "index": 2,
            "title": "Consumer Protection Act 2019",
            "anchor": "consumer-protection-2019/sec-2",
        },
    ]

    workflow = _selected_workflow_result(query, route, passages, plan)

    assert workflow is None


def test_loan_app_owner_reports_the_same_activation_source_it_enforces():
    query = "Loan app is harassing my contacts and sending my photo"
    route = route_matter(query)
    plan = build_matter_plan(query, route)
    assert plan is not None
    passages = _loan_app_registry_passages()

    workflow = _selected_workflow_result(query, route, passages, plan)

    assert workflow is not None
    assert workflow.required_sources == (
        "digital_grievance", "digital_data", "recovery_conduct",
        "rbi_application", "rbi_definitions", "rbi_forum",
        "rbi_grounds", "rbi_maintainability",
    )
    assert workflow.source_indices == {
        "digital_grievance": 1,
        "digital_data": 2,
        "recovery_conduct": 3,
        "rbi_application": 4,
        "rbi_definitions": 5,
        "rbi_forum": 6,
        "rbi_grounds": 7,
        "rbi_maintainability": 8,
    }
    assert "DPDP Act Section 13" not in " ".join(workflow.lines)


def test_wrong_bank_owner_uses_each_clause_and_ignores_decoy_law():
    query = "Bank deducted money wrongly and customer care is not helping"
    route = route_matter(query)
    plan = build_matter_plan(query, route)
    passages = [
        *_rbi_ombudsman_passages(),
        _passage(6, "Banking Regulation Act 1949", "banking-regulation-1949/sec-45ZA", "banking_regulation_1949"),
        _passage(7, "Consumer Protection Act 2019", "consumer-protection-2019/sec-2", "consumer_protection_2019"),
    ]

    workflow = _selected_workflow_result(query, route, passages, plan)

    assert workflow is not None
    assert workflow.source_indices == {
        "rbi_application": 1,
        "rbi_definitions": 2,
        "rbi_forum": 3,
        "rbi_grounds": 4,
        "rbi_maintainability": 5,
    }
    answer = " ".join(workflow.lines)
    assert "Clause 1" in answer
    assert "Clause 3" in answer
    assert "Clause 9" in answer
    assert "Clause 10" in answer
    assert "Clause 6" in answer
    assert "45ZA" not in answer
    assert "Consumer Protection" not in answer


def test_loan_app_police_advice_requires_independent_offence_source():
    generic_query = "Loan app is harassing my contacts and calling relatives"
    generic_route = route_matter(generic_query)
    generic_plan = build_matter_plan(generic_query, generic_route)
    generic = _selected_workflow_result(
        generic_query, generic_route, _loan_app_registry_passages(), generic_plan
    )
    assert generic is not None
    assert "cyber police" not in " ".join(generic.lines).lower()
    assert "1930" not in " ".join(generic.lines)

    image_query = "Loan app is blackmailing me with a morphed nude photo"
    image_route = route_matter(image_query)
    image_plan = build_matter_plan(image_query, image_route)
    without_it = _selected_workflow_result(
        image_query, image_route, _loan_app_registry_passages(), image_plan
    )
    assert without_it is not None
    assert "cyber police" not in " ".join(without_it.lines).lower()

    with_it_passages = [
        *_loan_app_registry_passages(),
        _passage(9, "Information Technology Act 2000", "it-act-2000/sec-66E", "it_act_2000"),
    ]
    with_it = _selected_workflow_result(
        image_query, image_route, with_it_passages, image_plan
    )
    assert with_it is not None
    answer = " ".join(with_it.lines)
    assert "IT Act Section 66E" in answer
    assert "urgent cyber-reporting option" in answer
    assert "cyber police/1930/cybercrime.gov.in [9]" not in answer


@pytest.mark.parametrize(
    "query,required_acts,required_packs,forbidden_terms",
    (
        (
            "My bike was stolen in May 2023 and police refuse FIR",
            {"Code of Criminal Procedure 1973", "Indian Penal Code 1860"},
            {"ipc_1860_vehicle_theft", "crpc_1973_vehicle_theft_fir"},
            ("BNSS", "BNS theft"),
        ),
        (
            "My bike was stolen in August 2025 and police refuse FIR",
            {"Bharatiya Nagarik Suraksha Sanhita 2023", "Bharatiya Nyaya Sanhita 2023"},
            {"bns_2023_vehicle_theft", "bnss_2023_vehicle_theft_fir"},
            ("CrPC", "IPC theft"),
        ),
        (
            "My bike is stolen and police refuse FIR",
            {
                "Bharatiya Nagarik Suraksha Sanhita 2023",
                "Code of Criminal Procedure 1973",
                "Bharatiya Nyaya Sanhita 2023",
                "Indian Penal Code 1860",
            },
            {
                "bns_2023_vehicle_theft",
                "bnss_2023_vehicle_theft_fir",
                "ipc_1860_vehicle_theft",
                "crpc_1973_vehicle_theft_fir",
            },
            (),
        ),
    ),
)
def test_vehicle_theft_owner_and_sources_follow_incident_regime(
    query: str,
    required_acts: set[str],
    required_packs: set[str],
    forbidden_terms: tuple[str, ...],
):
    route = route_matter(query)
    plan = build_matter_plan(query, route)
    assert plan is not None
    assert plan.answer_policy.required_primary_owner == (
        "authority_graph:vehicle_theft_fir_refusal"
    )
    assert {entry.act for entry in plan.authority_ledger if entry.must_cite} == required_acts
    packs = {pack.id for pack in source_packs_for_route(route, query)}
    assert required_packs <= packs
    if route.legal_regime == "legacy_ipc_crpc_evidence_for_pre_2024_incident":
        assert "bns_2023_vehicle_theft" not in packs
        assert "bnss_2023_vehicle_theft_fir" not in packs

    passages = []
    if "Bharatiya Nagarik Suraksha Sanhita 2023" in required_acts:
        passages.extend([
            {"index": 1, "title": "Bharatiya Nagarik Suraksha Sanhita 2023", "anchor": "bnss-2023/sec-173-a", "required_source_pack": "bnss_2023_vehicle_theft_fir"},
            {"index": 2, "title": "Bharatiya Nagarik Suraksha Sanhita 2023", "anchor": "bnss-2023/sec-173-c", "required_source_pack": "bnss_2023_vehicle_theft_fir"},
            {"index": 3, "title": "Bharatiya Nagarik Suraksha Sanhita 2023", "anchor": "bnss-2023/sec-175", "required_source_pack": "bnss_2023_vehicle_theft_fir"},
            {"index": 4, "title": "Bharatiya Nyaya Sanhita 2023", "anchor": "bns-2023/sec-303", "required_source_pack": "bns_2023_vehicle_theft"},
        ])
    if "Code of Criminal Procedure 1973" in required_acts:
        passages.extend([
            {"index": 5, "title": "Code of Criminal Procedure 1973", "anchor": "crpc-1973/sec-154", "required_source_pack": "crpc_1973_vehicle_theft_fir"},
            {"index": 6, "title": "Indian Penal Code 1860", "anchor": "ipc-1860/sec-378", "required_source_pack": "ipc_1860_vehicle_theft"},
        ])
    workflow = _selected_workflow_result(query, route, passages, plan)
    assert workflow is not None
    joined = " ".join(workflow.lines)
    for term in forbidden_terms:
        assert term not in joined


@pytest.mark.parametrize(
    "query,owner,required_procedure_acts,forbidden_text",
    (
        (
            "Police picked my son from home in May 2023 and gave no FIR copy",
            "authority_graph:arrest_custody_station_case_not_disclosed",
            {"Code of Criminal Procedure 1973"},
            "For a current BNSS matter",
        ),
        (
            "Police picked my son from home in August 2025 and gave no FIR copy",
            "authority_graph:arrest_custody_station_case_not_disclosed",
            {"Bharatiya Nagarik Suraksha Sanhita 2023"},
            "older CrPC",
        ),
        (
            "Police arrested my son in May 2023 for being gay",
            "authority_graph:lgbtq_identity_arrest_safeguard",
            {"code of criminal procedure"},
            "Use the BNSS arrest",
        ),
        (
            "Police arrested my son in August 2025 for being gay",
            "authority_graph:lgbtq_identity_arrest_safeguard",
            {"bharatiya nagarik suraksha"},
            "Use the CrPC arrest",
        ),
    ),
)
def test_arrest_owners_filter_procedure_by_incident_regime(
    query: str,
    owner: str,
    required_procedure_acts: set[str],
    forbidden_text: str,
):
    route = route_matter(query)
    plan = build_matter_plan(query, route)
    assert plan is not None
    assert plan.answer_policy.required_primary_owner == owner
    required_procedure_acts = {value.lower() for value in required_procedure_acts}
    procedure_acts = {
        entry.act.lower()
        for entry in plan.authority_ledger
        if entry.must_cite
        and entry.act.lower() in {
            "bharatiya nagarik suraksha sanhita 2023",
            "bharatiya nagarik suraksha",
            "code of criminal procedure 1973",
            "code of criminal procedure",
        }
    }
    assert any(
        any(
            act == required or act.startswith(f"{required} ")
            for required in required_procedure_acts
        )
        for act in procedure_acts
    )
    if owner == "authority_graph:arrest_custody_station_case_not_disclosed":
        custody_regime = (
            "legacy" if route.legal_regime.startswith("legacy_") else "current"
        )
        passages = _custody_registry_passages(custody_regime)
    else:
        passages = [
            _passage(1, "NAVTEJ SINGH JOHAR & ORS. versus UNION OF INDIA", "2018-insc-790#header", "navtej_lgbtq_liberty", "sc_judgment"),
            _passage(2, "Bharatiya Nagarik Suraksha Sanhita 2023", "bnss-2023/sec-47", "bnss_2023"),
            _passage(3, "Bharatiya Nagarik Suraksha Sanhita 2023", "bnss-2023/sec-57", "bnss_2023"),
            _passage(4, "Code of Criminal Procedure 1973", "crpc-1973/sec-50", "crpc_1973"),
            _passage(5, "Code of Criminal Procedure 1973", "crpc-1973/sec-57", "crpc_1973"),
        ]
    workflow = _selected_workflow_result(query, route, passages, plan)
    assert workflow is not None
    assert forbidden_text not in " ".join(workflow.lines)


def test_custody_registry_uses_incident_regime_not_birth_year():
    query = (
        "Police picked my son born in 2008 from home last night "
        "and are hiding the station"
    )

    route = route_matter(query)
    plan = build_matter_plan(query, route)

    assert route.legal_regime == "current_bns_bnss_bsa_for_post_2024_incident"
    assert plan is not None
    registry_keys = {
        entry.registry_key for entry in plan.authority_ledger if entry.registry_key
    }
    assert "bharatiya_nagarik_suraksha_sanhita_2023_section_36" in registry_keys
    assert not any(key.startswith("code_of_criminal_procedure_1973") for key in registry_keys)


def test_custody_birth_year_without_incident_date_keeps_regime_unknown():
    query = "Police picked my son born in 2008 from home and hide the station"

    route = route_matter(query)
    plan = build_matter_plan(query, route)

    assert route.legal_regime == "incident_date_needed_for_bns_bnss_bsa_vs_ipc_crpc"
    assert plan is not None
    registry_keys = {
        entry.registry_key for entry in plan.authority_ledger if entry.registry_key
    }
    assert registry_keys == {
        "constitution_of_india_article_22",
        "constitution_of_india_article_226",
        "bharatiya_nagarik_suraksha_sanhita_2023_section_531",
    }


def test_unknown_date_lgbtq_arrest_names_both_regimes_without_selecting_one():
    query = "Police arrested my son for being gay"
    route = route_matter(query)
    plan = build_matter_plan(query, route)
    assert plan is not None
    passages = [
        _passage(1, "NAVTEJ SINGH JOHAR & ORS. versus UNION OF INDIA", "2018-insc-790#header", "navtej_lgbtq_liberty", "sc_judgment"),
        _passage(2, "Bharatiya Nagarik Suraksha Sanhita 2023", "bnss-2023/sec-47", "bnss_2023"),
        _passage(3, "Bharatiya Nagarik Suraksha Sanhita 2023", "bnss-2023/sec-57", "bnss_2023"),
        _passage(4, "Code of Criminal Procedure 1973", "crpc-1973/sec-50", "crpc_1973"),
        _passage(5, "Code of Criminal Procedure 1973", "crpc-1973/sec-57", "crpc_1973"),
    ]

    workflow = _selected_workflow_result(query, route, passages, plan)

    assert workflow is not None
    joined = " ".join(workflow.lines)
    assert "incident date is still needed" in joined
    assert "do not describe either regime as selected" in joined
    assert "BNSS Section 47" in joined
    assert "CrPC Section 50" in joined


def test_lgbtq_arrest_section_47_alone_cannot_support_production_claim():
    query = "Police arrested my son in August 2025 for being gay"
    route = route_matter(query)
    plan = build_matter_plan(query, route)
    assert plan is not None
    passages = [
        _passage(1, "NAVTEJ SINGH JOHAR & ORS. versus UNION OF INDIA", "2018-insc-790#header", "navtej_lgbtq_liberty", "sc_judgment"),
        _passage(2, "Bharatiya Nagarik Suraksha Sanhita 2023", "bnss-2023/sec-47", "bnss_2023"),
    ]

    assert _selected_workflow_result(query, route, passages, plan) is None


@pytest.mark.parametrize(
    "query",
    (
        "Police picked my son from home and will not tell me the station",
        "Police has picked my son from my home in the night and I have no FIR copy",
        "Officers have taken my daughter and will not tell us the case",
    ),
)
def test_hidden_person_custody_owner_accepts_natural_user_grammar(query: str):
    route = route_matter(query)
    plan = build_matter_plan(query, route)
    assert plan is not None
    passages = _custody_registry_passages()

    workflow = _selected_workflow_result(query, route, passages, plan)

    assert workflow is not None
    assert workflow.id == "arrest_custody_station_case_not_disclosed"


@pytest.mark.parametrize(
    "query,procedure_title,procedure_anchor,required_text,forbidden_text",
    (
        (
            "Cyber police froze my bank account in May 2023",
            "Code of Criminal Procedure 1973",
            "crpc-1973/sec-102",
            "CrPC Section 102",
            "BNSS Section 106 is the property-seizure source",
        ),
        (
            "Cyber police froze my bank account in August 2025",
            "Bharatiya Nagarik Suraksha Sanhita 2023",
            "bnss-2023/sec-106",
            "BNSS Section 106 says a police officer may seize property",
            "verify the police seizure against CrPC Section 102",
        ),
    ),
)
def test_bank_freeze_answer_follows_incident_regime(
    query: str,
    procedure_title: str,
    procedure_anchor: str,
    required_text: str,
    forbidden_text: str,
):
    route = route_matter(query)
    plan = build_matter_plan(query, route)
    assert plan is not None
    passages = [
        *_rbi_ombudsman_passages(1),
        _passage(6, procedure_title, procedure_anchor, "procedure"),
    ]

    workflow = _selected_workflow_result(query, route, passages, plan)

    assert workflow is not None
    joined = " ".join(workflow.lines)
    assert required_text in joined
    assert forbidden_text not in joined
    assert "Use RBI Scheme clauses 9 and 10" in joined


def test_bank_freeze_contract_fails_closed_when_mandatory_rbi_clause_missing():
    query = "Cyber police froze my bank account in August 2025"
    route = route_matter(query)
    plan = build_matter_plan(query, route)
    assert plan is not None
    passages = [
        _passage(1, "Reserve Bank Integrated Ombudsman Scheme 2021", "rbi-integrated-ombudsman-2021/sec-3", "rbi_integrated_ombudsman_2021"),
        _passage(2, "Reserve Bank Integrated Ombudsman Scheme 2021", "rbi-integrated-ombudsman-2021/sec-9", "rbi_integrated_ombudsman_2021"),
        _passage(3, "Reserve Bank Integrated Ombudsman Scheme 2021", "rbi-integrated-ombudsman-2021/sec-10", "rbi_integrated_ombudsman_2021"),
        _passage(4, "Bharatiya Nagarik Suraksha Sanhita 2023", "bnss-2023/sec-106", "bnss_2023_bank_account_legal_hold"),
    ]

    workflow = _selected_workflow_result(query, route, passages, plan)

    assert workflow is None


def test_unknown_date_bank_freeze_answer_keeps_both_regimes_conditional():
    query = "Cyber police froze my bank account"
    route = route_matter(query)
    plan = build_matter_plan(query, route)
    assert plan is not None
    passages = [
        *_rbi_ombudsman_passages(1),
        _passage(6, "Bharatiya Nagarik Suraksha Sanhita 2023", "bnss-2023/sec-106", "bnss_2023_bank_account_legal_hold"),
        _passage(7, "Code of Criminal Procedure 1973", "crpc-1973/sec-102", "crpc_1973_bank_account_legal_hold"),
    ]

    workflow = _selected_workflow_result(query, route, passages, plan)

    assert workflow is not None
    joined = " ".join(workflow.lines)
    assert "date is needed before choosing" in joined
    assert "BNSS Section 106 says a police officer may seize property" in joined
    assert "CrPC Section 102" in joined


def test_bank_freeze_does_not_emit_it_act_without_separate_fraud_facts():
    query = "Cyber police froze my bank account in August 2025 and gave no notice"
    route = route_matter(query)
    plan = build_matter_plan(query, route)
    assert plan is not None
    passages = [
        *_rbi_ombudsman_passages(1),
        _passage(6, "Bharatiya Nagarik Suraksha Sanhita 2023", "bnss-2023/sec-106", "bnss_2023_bank_account_legal_hold"),
        _passage(7, "Information Technology Act 2000", "it-2000/sec-66C", "it_2000"),
    ]

    workflow = _selected_workflow_result(query, route, passages, plan)

    assert workflow is not None
    joined = " ".join(workflow.lines)
    assert "BNSS Section 106 says a police officer may seize property" in joined
    assert "Keep the IT Act source" not in joined


def test_bank_freeze_can_emit_it_act_for_separate_identity_misuse_facts():
    query = "Cyber police froze my bank account after identity theft in August 2025"
    route = route_matter(query)
    plan = build_matter_plan(query, route)
    assert plan is not None
    passages = [
        *_rbi_ombudsman_passages(1),
        _passage(6, "Bharatiya Nagarik Suraksha Sanhita 2023", "bnss-2023/sec-106", "bnss_2023_bank_account_legal_hold"),
        _passage(7, "Information Technology Act 2000", "it-2000/sec-66C", "it_2000"),
    ]

    workflow = _selected_workflow_result(query, route, passages, plan)

    assert workflow is not None
    assert "Keep the IT Act source" in " ".join(workflow.lines)


def test_generic_bank_freeze_is_registry_owned_without_criminal_seizure_sources():
    query = "my bank account is frozen, what do i do"
    route = route_matter(query)
    plan = build_matter_plan(query, route)

    assert route.category == "banking_credit_dispute"
    assert plan is not None
    assert plan.answer_policy.required_primary_owner == "authority_graph:bank_account_freeze_legal_hold"
    pack_ids = {source.source_pack_id for source in plan.retrieval_sources}
    assert "rbi_integrated_ombudsman_2021" in pack_ids
    assert "bnss_2023_bank_account_legal_hold" not in pack_ids
    assert "crpc_1973_bank_account_legal_hold" not in pack_ids

    workflow = _selected_workflow_result(query, route, _rbi_ombudsman_passages(1), plan)

    assert workflow is not None
    joined = " ".join(workflow.lines)
    assert "frozen, blocked, lien-marked, or KYC-held bank account" in joined
    assert "BNSS Section 106" not in joined
    assert "CrPC Section 102" not in joined


def test_salary_account_lien_and_hinglish_freeze_activate_legal_hold_sources():
    queries = (
        "Bank says police put a lien on my salary account but gave no complaint number",
        "UPI account freeze ho gaya, bank says cyber police requested it",
    )
    for query in queries:
        route = route_matter(query)
        plan = build_matter_plan(query, route)

        assert route.category == "banking_credit_dispute"
        assert route.legal_regime == "incident_date_needed_for_bns_bnss_bsa_vs_ipc_crpc"
        assert plan is not None
        pack_ids = {source.source_pack_id for source in plan.retrieval_sources}
        assert "rbi_integrated_ombudsman_2021" in pack_ids
        assert "bnss_2023_bank_account_legal_hold" in pack_ids
        assert "crpc_1973_bank_account_legal_hold" in pack_ids

        passages = [
            *_rbi_ombudsman_passages(1),
            _passage(6, "Bharatiya Nagarik Suraksha Sanhita 2023", "bnss-2023/sec-106", "bnss_2023_bank_account_legal_hold"),
            _passage(7, "Code of Criminal Procedure 1973", "crpc-1973/sec-102", "crpc_1973_bank_account_legal_hold"),
        ]
        workflow = _selected_workflow_result(query, route, passages, plan)
        assert workflow is not None
        joined = " ".join(workflow.lines)
        assert "date is needed before choosing" in joined
        assert "BNSS Section 106" in joined
        assert "CrPC Section 102" in joined


def test_bank_legal_hold_backfills_registry_authorities_when_retrieval_only_returns_rbi():
    query = "Bank says police put a lien on my salary account but gave no complaint number"
    route = route_matter(query)
    plan = build_matter_plan(query, route)
    assert plan is not None

    rbi_only = [
        RetrievedChunk(
            chunk_id=idx,
            document_id=idx,
            anchor=f"rbi-integrated-ombudsman-2021/sec-{clause}",
            text=f"RBI clause {clause}",
            source_type="bare_act",
            subject_area="Banking",
                as_at=date(2022, 8, 5),
            paragraph_no=None,
            title="Reserve Bank Integrated Ombudsman Scheme 2021",
            citation=None,
            court=None,
            statute_short="RBI Integrated Ombudsman Scheme 2021",
            metadata={"_required_source_pack": "rbi_integrated_ombudsman_2021"},
        )
        for idx, clause in enumerate((1, 3, 6, 9, 10), start=1)
    ]

    backfilled = _backfill_registry_required_authorities(rbi_only, plan)
    pack_ids = {chunk.metadata.get("_required_source_pack") for chunk in backfilled}

    assert "bnss_2023_bank_account_legal_hold" in pack_ids
    assert "crpc_1973_bank_account_legal_hold" in pack_ids
    passages, _ = _make_passages(backfilled, len(backfilled), plan=plan)
    assert not missing_plan_authorities(plan=plan, passages=passages, query=query)


def test_bank_legal_hold_backfills_registry_authorities_after_owner_filter_leaves_empty():
    query = "Bank says police put a lien on my salary account but gave no complaint number"
    route = route_matter(query)
    plan = build_matter_plan(query, route)
    assert plan is not None

    backfilled = _backfill_registry_required_authorities([], plan)
    pack_ids = {chunk.metadata.get("_required_source_pack") for chunk in backfilled}

    assert "rbi_integrated_ombudsman_2021" in pack_ids
    assert "bnss_2023_bank_account_legal_hold" in pack_ids
    assert "crpc_1973_bank_account_legal_hold" in pack_ids
    anchors = {chunk.anchor for chunk in backfilled}
    assert "rbi-integrated-ombudsman-2021/sec-1" in anchors
    assert "rbi-integrated-ombudsman-2021/sec-3" in anchors
    passages, _ = _make_passages(backfilled, len(backfilled), plan=plan)
    assert not missing_plan_authorities(plan=plan, passages=passages, query=query)
    workflow = _selected_workflow_result(query, route, passages, plan)
    assert workflow is not None
    assert workflow.id == "bank_account_freeze_legal_hold"


def test_kyc_bank_freeze_stays_bank_service_not_criminal_seizure():
    query = "Bank froze my account because KYC is pending"
    route = route_matter(query)
    plan = build_matter_plan(query, route)

    assert route.category == "banking_credit_dispute"
    assert route.legal_regime is None
    assert plan is not None
    pack_ids = {source.source_pack_id for source in plan.retrieval_sources}
    assert "rbi_integrated_ombudsman_2021" in pack_ids
    assert "bnss_2023_bank_account_legal_hold" not in pack_ids
    assert "crpc_1973_bank_account_legal_hold" not in pack_ids

    workflow = _selected_workflow_result(query, route, _rbi_ombudsman_passages(1), plan)

    assert workflow is not None
    joined = " ".join(workflow.lines)
    assert "KYC or document mismatch" in joined
    assert "criminal seizure" in joined
    assert "BNSS Section 106" not in joined


def test_coowner_section_44_cannot_emit_section_45_joint_purchase_claim():
    query = "My brother and I bought a plot and he sold the whole plot without me"
    route = route_matter(query)
    plan = build_matter_plan(query, route)
    assert plan is not None
    passages = [
        _passage(1, "Transfer of Property Act 1882", "transfer-of-property-1882/sec-44", "transfer_property_1882"),
    ]

    workflow = _selected_workflow_result(query, route, passages, plan)

    assert workflow is not None
    joined = " ".join(workflow.lines)
    assert "co-owner transfer source" in joined
    assert "transfers for consideration to two or more persons" not in joined


def test_coowner_section_45_cannot_emit_section_44_transfer_claim():
    query = "My brother and I bought a plot and he sold the whole plot without me"
    route = route_matter(query)
    plan = build_matter_plan(query, route)
    assert plan is not None
    passages = [
        _passage(1, "Transfer of Property Act 1882", "transfer-of-property-1882/sec-45", "transfer_property_1882"),
    ]

    workflow = _selected_workflow_result(query, route, passages, plan)

    assert workflow is not None
    joined = " ".join(workflow.lines)
    assert "transfers for consideration to two or more persons" in joined
    assert "co-owner transfer source" not in joined


@pytest.mark.parametrize(
    "query",
    (
        "Police arrested two gay 16 year old boys after a complaint",
        "Police arrested my gay 15 year old son after a complaint",
        "Police arrested my teenage gay son after a complaint",
        "Police arrested a gay schoolboy after a complaint",
        "Police arrested my gay son for assaulting a neighbour",
        "Police arrested my gay son for stabbing a neighbour",
        "Police arrested my gay son for robbery",
        "Police arrested my gay son for possession of ganja",
        "Police arrested my gay son for possession of MDMA",
        "Police arrested my gay son for possession of heroin",
        "Police arrested my gay son for drunk driving",
        "Police arrested my gay son for violating a court order",
    ),
)
def test_lgbtq_identity_owner_does_not_suppress_independent_allegations(query: str):
    route = route_matter(query)
    assert plan_owned_answer_route(query, route) is None


@pytest.mark.parametrize(
    "query",
    (
        "Someone broke my scooter mirror and police refused my complaint",
        "My car was damaged in parking and police say wait",
        "Bike service centre damaged my vehicle and police will not help",
    ),
)
def test_vehicle_theft_owner_requires_stolen_vehicle_and_fir_problem(query: str):
    route = route_matter(query)
    resolution = resolve_plan_answer_ownership(query, route)
    assert resolution.owner is None or (
        resolution.owner.owner_token != "authority_graph:vehicle_theft_fir_refusal"
    )


@pytest.mark.parametrize(
    "query",
    (
        "My wife is beating me",
        "My husband is beating me, I am his husband",
        "My spouse is beating me",
    ),
)
def test_pwdva_owner_does_not_reverse_or_assume_victim_role(query: str):
    route = route_matter(query)
    resolution = resolve_plan_answer_ownership(query, route)

    assert "authority_graph:domestic_violence_immediate_safety" not in resolution.conflicts
    assert resolution.owner is None or (
        resolution.owner.owner_token != "authority_graph:domestic_violence_immediate_safety"
    )


@pytest.mark.parametrize(
    "query",
    (
        "Loan app asks for contacts permission during signup",
        "Loan app has not harassed anyone",
        "Loan app did not contact anyone and only sent a normal reminder",
    ),
)
def test_loan_harassment_owner_requires_an_adverse_act(query: str):
    route = route_matter(query)
    resolution = resolve_plan_answer_ownership(query, route)

    assert resolution.owner is None or (
        resolution.owner.owner_token != "common_workflow_contracts:loan_app_harassment"
    )


@pytest.mark.parametrize(
    "query,passages,forbidden",
    (
        (
            "My health insurer rejected my claim as pre-existing",
            [
                {"index": 1, "title": "Insurance Ombudsman Rules 2017", "anchor": "insurance-ombudsman-rules-2017/sec-13"},
                {"index": 2, "title": "Insurance Ombudsman Rules 2017", "anchor": "insurance-ombudsman-rules-2017/sec-14"},
            ],
            ("District Consumer Commission", "e-Daakhil"),
        ),
        (
            "My brother and I bought a plot and he sold the whole plot without me",
            [{"index": 1, "title": "Transfer of Property Act 1882", "anchor": "transfer-property-1882/sec-44"}],
            ("partition", "declaration", "injunction", "cancellation"),
        ),
        (
            "My wife refuses physical intimacy for one year",
            [{"index": 1, "title": "Family Courts Act 1984", "anchor": "family-courts-1984/sec-7"}],
            ("judicial separation", "divorce", "restitution"),
        ),
    ),
)
def test_optional_authority_claims_are_omitted_when_source_is_absent(
    query: str,
    passages: list[dict],
    forbidden: tuple[str, ...],
):
    route = route_matter(query)
    plan = build_matter_plan(query, route)
    assert plan is not None
    workflow = _selected_workflow_result(query, route, passages, plan)
    assert workflow is not None
    joined = " ".join(workflow.lines).lower()
    for term in forbidden:
        assert term.lower() not in joined


def test_plan_owned_contract_does_not_override_weak_verifier_result():
    query, _, _ = RELEASED_SCENARIOS[0]
    route = route_matter(query)
    plan = build_matter_plan(query, route)
    assert plan is not None
    line = "A substantive legal claim [1]."
    workflow = WorkflowTemplateResult(
        id="domestic_violence_immediate_safety",
        source="authority_graph",
        lines=[line],
        answer_mode="safety_primary",
    )
    weak = SentenceVerification(
        text=line,
        status=SentenceStatus.WEAK_SUPPORT,
        citations=[1],
        entailment_score=0.4,
    )

    result = _promote_reviewed_workflow_contract_line(
        weak,
        workflow,
        workflow.lines,
        plan,
    )

    assert result.status == SentenceStatus.WEAK_SUPPORT


def test_mgnrega_plan_owned_reviewed_line_survives_verifier_drift():
    query = "muster roll shows my 20 days but wages not paid"
    route = route_matter(query)
    plan = build_matter_plan(query, route)
    assert plan is not None
    passages = [
        {
            "index": 1,
            "title": "Mahatma Gandhi National Rural Employment Guarantee Act 2005",
            "anchor": "mgnrega-2005/sec-19-official",
            "required_source_pack": "mgnrega_2005",
            "document_id": "mgnrega-2005",
        },
        {
            "index": 2,
            "title": "Mahatma Gandhi National Rural Employment Guarantee Act 2005",
            "anchor": "mgnrega-2005/sec-17-official",
            "required_source_pack": "mgnrega_2005",
            "document_id": "mgnrega-2005",
        },
    ]
    workflow = _selected_workflow_result(query, route, passages, plan)
    assert workflow is not None
    line = next(line for line in workflow.lines if "which is a wage delay" in line)
    weak = SentenceVerification(
        text=line,
        status=SentenceStatus.WEAK_SUPPORT,
        citations=[workflow.source_indices["mgnrega_grievance"]],
        entailment_score=0.4,
    )

    result = _promote_reviewed_workflow_contract_line(
        weak,
        workflow,
        workflow.lines,
        plan,
    )

    assert result.status == SentenceStatus.OK
    assert result.citations == [workflow.source_indices["mgnrega_grievance"]]


def test_plan_owned_next_step_is_uncited_guidance_not_weak_law():
    query, _, _ = RELEASED_SCENARIOS[0]
    route = route_matter(query)
    plan = build_matter_plan(query, route)
    assert plan is not None
    header = SentenceVerification(
        "**What you can do next**",
        SentenceStatus.META,
    )
    line = SentenceVerification(
        "- Keep photos, messages, and medical records [1].",
        SentenceStatus.UNSUPPORTED,
        citations=[1],
    )

    promoted = _promote_safe_route_next_step(line, route, header, plan)

    assert promoted.status == SentenceStatus.GUIDANCE
    assert promoted.citations == []
    assert "[1]" not in promoted.text


def test_plan_owned_immediate_safety_guidance_survives_before_next_steps_header():
    query, _, _ = RELEASED_SCENARIOS[0]
    route = route_matter(query)
    plan = build_matter_plan(query, route)
    assert plan is not None
    line = SentenceVerification(
        "- Move to a safe place or trusted person if you are unsafe right now; treat immediate safety first and contact 112/police or emergency services for immediate danger.",
        SentenceStatus.UNSUPPORTED,
        citations=[],
    )

    promoted = _promote_safe_route_next_step(line, route, None, plan)

    assert promoted.status == SentenceStatus.GUIDANCE
    assert promoted.citations == []


def test_plan_owned_uncited_bank_information_request_is_visible_guidance():
    query = "Cyber police froze my bank account"
    route = route_matter(query)
    plan = build_matter_plan(query, route)
    assert plan is not None
    header = SentenceVerification(
        "**What you can do next**",
        SentenceStatus.META,
    )
    line = SentenceVerification(
        "- Ask the bank in writing for the written freeze/lien reason, the originating request/reference and order copy, the amount and transactions affected, and the nodal officer handling the hold when it says a cyber/police complaint caused the hold.",
        SentenceStatus.UNSUPPORTED,
        citations=[],
    )

    promoted = _promote_safe_route_next_step(line, route, header, plan)

    assert promoted.status == SentenceStatus.GUIDANCE
    assert promoted.citations == []


def test_plan_owned_loan_harassment_steps_are_uncited_guidance():
    query = "Loan app is harassing my contacts and sending my photo"
    route = route_matter(query)
    plan = build_matter_plan(query, route)
    assert plan is not None
    header = SentenceVerification(
        "**What you can do next**",
        SentenceStatus.META,
    )
    line = SentenceVerification(
        "- Keep the lender name, app permissions, call logs, screenshots, and complaint number [2].",
        SentenceStatus.WEAK_SUPPORT,
        citations=[2],
    )

    promoted = _promote_safe_route_next_step(line, route, header, plan)

    assert promoted.status == SentenceStatus.GUIDANCE
    assert promoted.citations == []
    assert "[2]" not in promoted.text


def test_plan_owned_verified_next_step_is_still_marked_as_guidance():
    query, _, _ = RELEASED_SCENARIOS[0]
    route = route_matter(query)
    plan = build_matter_plan(query, route)
    assert plan is not None
    header = SentenceVerification(
        "**What you can do next**",
        SentenceStatus.META,
    )
    line = SentenceVerification(
        "- Keep photos, messages, and medical records [1].",
        SentenceStatus.OK,
        citations=[1],
        entailment_score=0.9,
    )

    promoted = _promote_safe_route_next_step(line, route, header, plan)

    assert promoted.status == SentenceStatus.GUIDANCE
    assert promoted.citations == []


def test_plan_owned_procedural_step_remains_cited_verified_law():
    query = "The insurer is rejecting my claim"
    route = route_matter(query)
    plan = build_matter_plan(query, route)
    assert plan is not None
    header = SentenceVerification(
        "**What you can do next**",
        SentenceStatus.META,
    )
    line = SentenceVerification(
        "- Use the Ombudsman route [3], [2].",
        SentenceStatus.OK,
        citations=[3, 2],
    )

    promoted = _promote_safe_route_next_step(line, route, header, plan)

    assert promoted.status == SentenceStatus.OK
    assert promoted.citations == [3, 2]
    assert promoted.text == "- Use the Ombudsman route [3], [2]."


def test_plan_owned_unsupported_legal_claim_cannot_become_guidance():
    query, _, _ = RELEASED_SCENARIOS[0]
    route = route_matter(query)
    plan = build_matter_plan(query, route)
    header = SentenceVerification("**What you can do next**", SentenceStatus.META)
    line = SentenceVerification(
        "- You have a legal right to an immediate protection order [1].",
        SentenceStatus.UNSUPPORTED,
        citations=[1],
    )

    promoted = _promote_safe_route_next_step(line, route, header, plan)

    assert promoted.status == SentenceStatus.UNSUPPORTED
    assert promoted.citations == [1]


def test_plan_owned_legal_bridge_is_not_promoted_by_phrase_allowlist():
    query, _, _ = RELEASED_SCENARIOS[0]
    route = route_matter(query)
    plan = build_matter_plan(query, route)
    assert plan is not None
    line = SentenceVerification(
        "Keep a separate BNS criminal track [1].",
        SentenceStatus.UNSUPPORTED,
        citations=[1],
    )

    promoted = _promote_safe_template_source_bridge(line, route, plan)

    assert promoted.status == SentenceStatus.UNSUPPORTED
