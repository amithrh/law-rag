import json
from datetime import date

import pytest

from apps.api.common_workflow_contracts import (
    WorkflowTemplateResult,
    dpdp_section_13_in_force,
)
from apps.api.legal_issue_plan import (
    PLAN_OWNED_ANSWER_ROUTES,
    build_matter_plan,
    plan_owned_answer_route,
    resolve_plan_answer_ownership,
)
from apps.api.main import (
    _critical_route_needs_reviewed_contract,
    _controlling_source_gap_requires_handoff,
    _grounded_template_lines,
    _promote_reviewed_workflow_contract_line,
    _promote_safe_route_next_step,
    _promote_safe_template_source_bridge,
    _selected_workflow_result,
    _workflow_diagnostics_event,
)
from apps.api.matter_router import route_matter
from apps.api.source_packs import source_packs_for_route
from apps.api.source_gap import missing_plan_authorities
from apps.api.source_gap import build_source_gap_event
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
        "Bank deducted money wrongly and customer care is not helping",
        "wrong_bank_debit",
        "authority_graph:wrong_bank_debit",
    ),
    (
        "The insurer is rejecting my claim",
        "insurance_claim_or_misselling",
        "authority_graph:insurance_claim_or_misselling",
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
)


@pytest.mark.parametrize("query,scenario_id,owner", RELEASED_SCENARIOS)
def test_first_ten_scenarios_have_one_exact_owner_and_explicit_fallback(
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


def test_first_ten_registry_is_unique_and_exactly_ten():
    scenario_ids = [rule.scenario_id for rule in PLAN_OWNED_ANSWER_ROUTES]
    owner_tokens = [rule.owner_token for rule in PLAN_OWNED_ANSWER_ROUTES]

    assert len(PLAN_OWNED_ANSWER_ROUTES) == 10
    assert len(scenario_ids) == len(set(scenario_ids))
    assert len(owner_tokens) == len(set(owner_tokens))
    assert all(rule.fallback_owner for rule in PLAN_OWNED_ANSWER_ROUTES)


@pytest.mark.parametrize(
    "query",
    (
        "My spouse and I disagree about monthly household expenses",
        "My adult son left home voluntarily and police have not detained him",
        "Is a consensual same-sex relationship between two adults illegal?",
        "The bike service centre is refusing a warranty repair",
        "Loan app only sends a normal due date reminder and is not harassing me",
        "Bank says KYC is pending so my account is temporarily on hold",
        "My bank loan EMI is due next week",
        "Enforcement Directorate froze my bank account under PMLA",
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
        "Police took my phone during the arrest of my brother and gave no seizure memo",
        "Police seized my phone and have not produced it before court; they will not tell me the case",
        "The seized hard drive has remained in police custody for five days without production before the Magistrate",
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
def test_first_ten_owner_rules_do_not_capture_negative_neighbors(query: str):
    route = route_matter(query)
    assert plan_owned_answer_route(query, route) is None


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

    bank_query = "Cyber police froze my bank account, but there is no FIR yet"
    bank_route = route_matter(bank_query)
    bank_owner = plan_owned_answer_route(bank_query, bank_route)
    assert bank_owner is not None
    assert bank_owner.owner_contract_id == "bank_account_freeze_legal_hold"

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
        _passage(1, "Reserve Bank Integrated Ombudsman Scheme 2021", "rbi-integrated-ombudsman-2021/sec-2", "rbi_integrated_ombudsman_2021"),
        _passage(2, "Bharatiya Nagarik Suraksha Sanhita 2023", "bnss-2023/sec-106", "bnss_2023_bank_account_legal_hold"),
        _passage(3, "Code of Criminal Procedure 1973", "crpc-1973/sec-102", "crpc_1973_bank_account_legal_hold"),
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
        {"index": 3, "title": "Reserve Bank Integrated Ombudsman Scheme 2021", "anchor": "rbi-integrated-ombudsman-2021/sec-2"},
        {"index": 4, "title": "Code of Criminal Procedure 1973", "anchor": "crpc-1973/sec-102"},
    ]

    result = _selected_workflow_result(query, route, passages, plan)

    assert result is not None
    assert result.source == "authority_graph"
    assert result.id == "bank_account_freeze_legal_hold"


def _passage(index, title, anchor, pack, source_type="bare_act"):
    return {
        "index": index,
        "title": title,
        "anchor": anchor,
        "required_source_pack": pack,
        "source_type": source_type,
    }


@pytest.mark.parametrize(
    "query,passages",
    (
        ("My husband is beating me right now", [
            _passage(1, "Protection of Women from Domestic Violence Act 2005", "pwdva-2005/sec-3", "pwdva_2005"),
        ]),
        ("Police picked my son at night and gave no FIR copy", [
            _passage(1, "Constitution of India", "constitution/sec-22", "constitution_article_22"),
            _passage(2, "Bharatiya Nagarik Suraksha Sanhita 2023", "bnss-2023/sec-47", "bnss_2023"),
            _passage(3, "Bharatiya Nagarik Suraksha Sanhita 2023", "bnss-2023/sec-57", "bnss_2023"),
            _passage(4, "Code of Criminal Procedure 1973", "crpc-1973/sec-50", "crpc_1973"),
        ]),
        ("Police arrested my son for being gay", [
            _passage(1, "NAVTEJ SINGH JOHAR & ORS. versus UNION OF INDIA", "2018-insc-790#header", "navtej_lgbtq_liberty", "sc_judgment"),
            _passage(2, "Bharatiya Nagarik Suraksha Sanhita 2023", "bnss-2023/sec-47", "bnss_2023"),
            _passage(3, "Bharatiya Nagarik Suraksha Sanhita 2023", "bnss-2023/sec-57", "bnss_2023"),
            _passage(4, "Code of Criminal Procedure 1973", "crpc-1973/sec-50", "crpc_1973"),
            _passage(5, "Code of Criminal Procedure 1973", "crpc-1973/sec-57", "crpc_1973"),
        ]),
        ("My bike is stolen and police is not filing FIR", [
            _passage(1, "Bharatiya Nagarik Suraksha Sanhita 2023", "bnss-2023/sec-173-a", "bnss_2023_vehicle_theft_fir"),
            _passage(2, "Bharatiya Nagarik Suraksha Sanhita 2023", "bnss-2023/sec-173-c", "bnss_2023_vehicle_theft_fir"),
            _passage(3, "Code of Criminal Procedure 1973", "crpc-1973/sec-154", "crpc_1973_vehicle_theft_fir"),
        ]),
        ("Loan app is harassing my contacts and sending my photo", [
            _passage(1, "Reserve Bank Integrated Ombudsman Scheme 2021", "rbi-integrated-ombudsman-2021/sec-2", "rbi_integrated_ombudsman_2021_loan_app_cyber"),
            _passage(2, "Reserve Bank Integrated Ombudsman Scheme 2021", "rbi-integrated-ombudsman-2021/sec-9", "rbi_integrated_ombudsman_2021_loan_app_cyber"),
        ]),
        ("Cyber police put a lien on my frozen bank account", [
            _passage(1, "Reserve Bank Integrated Ombudsman Scheme 2021", "rbi-integrated-ombudsman-2021/sec-2", "rbi_integrated_ombudsman_2021"),
            _passage(2, "Bharatiya Nagarik Suraksha Sanhita 2023", "bnss-2023/sec-106", "bnss_2023_bank_account_legal_hold"),
            _passage(3, "Code of Criminal Procedure 1973", "crpc-1973/sec-102", "crpc_1973_bank_account_legal_hold"),
        ]),
        ("Bank deducted money wrongly and customer care is not helping", [
            _passage(1, "Reserve Bank Integrated Ombudsman Scheme 2021", "rbi-integrated-ombudsman-2021/sec-2", "rbi_integrated_ombudsman_2021"),
            _passage(2, "Reserve Bank Integrated Ombudsman Scheme 2021", "rbi-integrated-ombudsman-2021/sec-9", "rbi_integrated_ombudsman_2021"),
        ]),
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
        _passage(
            1,
            "Protection of Women from Domestic Violence Act 2005",
            "domestic-violence-2005/sec-3",
            "pwdva_2005",
        )
    ]
    workflow = _selected_workflow_result(query, route, passages, plan)

    assert workflow is not None
    joined = " ".join(workflow.lines)
    assert "sexual abuse" in joined
    assert "Immediate safety" in joined
    assert missing_plan_authorities(plan=plan, passages=passages, query=query) == []


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
        _passage(2, "Constitution of India", "constitution/sec-22", "constitution_article_22"),
        _passage(3, "Bharatiya Nagarik Suraksha Sanhita 2023", "bnss-2023/sec-47", "bnss_2023"),
        _passage(4, "Bharatiya Nagarik Suraksha Sanhita 2023", "bnss-2023/sec-57", "bnss_2023"),
        _passage(5, "Code of Criminal Procedure 1973", "crpc-1973/sec-50", "crpc_1973"),
        _passage(6, "Code of Criminal Procedure 1973", "crpc-1973/sec-57", "crpc_1973"),
    ]
    result = _selected_workflow_result(query, route, passages, plan)
    assert result is not None
    joined = " ".join(result.lines)
    assert joined.index("Being gay") < joined.index("Related urgent legal track")
    assert "FIR copy" in joined


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
    passages = [
        {"index": 1, "title": "Digital Personal Data Protection Act 2023", "anchor": "dpdp-2023/sec-8"},
        {"index": 2, "title": "Digital Personal Data Protection Act 2023", "anchor": "dpdp-2023/sec-13"},
        {"index": 3, "title": "Reserve Bank Integrated Ombudsman Scheme 2021", "anchor": "rbi-integrated-ombudsman-2021/sec-2"},
        {"index": 4, "title": "Reserve Bank Integrated Ombudsman Scheme 2021", "anchor": "rbi-integrated-ombudsman-2021/sec-9"},
    ]

    workflow = _selected_workflow_result(query, route, passages, plan)

    assert workflow is not None
    assert workflow.required_sources == ("rbi_scope", "rbi_complaint")
    assert workflow.source_indices == {"rbi_scope": 3, "rbi_complaint": 4}
    assert "DPDP Act Section 13" not in " ".join(workflow.lines)


@pytest.mark.parametrize(
    "query,required_acts,required_packs,forbidden_terms",
    (
        (
            "My bike was stolen in May 2023 and police refuse FIR",
            {"Code of Criminal Procedure 1973"},
            {"ipc_1860_vehicle_theft", "crpc_1973_vehicle_theft_fir"},
            ("BNSS", "BNS theft"),
        ),
        (
            "My bike was stolen in August 2025 and police refuse FIR",
            {"Bharatiya Nagarik Suraksha Sanhita 2023"},
            {"bns_2023_vehicle_theft", "bnss_2023_vehicle_theft_fir"},
            ("CrPC", "IPC theft"),
        ),
        (
            "My bike is stolen and police refuse FIR",
            {
                "Bharatiya Nagarik Suraksha Sanhita 2023",
                "Code of Criminal Procedure 1973",
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
            {"index": 1, "title": "Bharatiya Nagarik Suraksha Sanhita 2023", "anchor": "bnss-2023/sec-173-a"},
            {"index": 2, "title": "Bharatiya Nagarik Suraksha Sanhita 2023", "anchor": "bnss-2023/sec-173-c"},
            {"index": 3, "title": "Bharatiya Nyaya Sanhita 2023", "anchor": "bns-2023/sec-303"},
        ])
    if "Code of Criminal Procedure 1973" in required_acts:
        passages.extend([
            {"index": 4, "title": "Code of Criminal Procedure 1973", "anchor": "crpc-1973/sec-154"},
            {"index": 5, "title": "Indian Penal Code 1860", "anchor": "ipc-1860/sec-378"},
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
            "BNSS Section",
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
    procedure_acts = {
        entry.act
        for entry in plan.authority_ledger
        if entry.must_cite
        and entry.act in {
            "Bharatiya Nagarik Suraksha Sanhita 2023",
            "bharatiya nagarik suraksha",
            "Code of Criminal Procedure 1973",
            "code of criminal procedure",
        }
    }
    assert procedure_acts & required_procedure_acts
    passages = [
        {"index": 1, "title": "NAVTEJ SINGH JOHAR & ORS. versus UNION OF INDIA", "anchor": "2018-insc-790#header"},
        {"index": 2, "title": "Constitution of India", "anchor": "constitution/sec-22"},
        {"index": 3, "title": "Bharatiya Nagarik Suraksha Sanhita 2023", "anchor": "bnss-2023/sec-47"},
        {"index": 4, "title": "Bharatiya Nagarik Suraksha Sanhita 2023", "anchor": "bnss-2023/sec-57"},
        {"index": 5, "title": "Code of Criminal Procedure 1973", "anchor": "crpc-1973/sec-50"},
        {"index": 6, "title": "Code of Criminal Procedure 1973", "anchor": "crpc-1973/sec-57"},
    ]
    workflow = _selected_workflow_result(query, route, passages, plan)
    assert workflow is not None
    assert forbidden_text not in " ".join(workflow.lines)


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
    passages = [
        _passage(1, "Constitution of India", "constitution-india/sec-22", "constitution"),
        _passage(2, "Bharatiya Nagarik Suraksha Sanhita 2023", "bnss-2023/sec-47", "bnss_2023"),
        _passage(3, "Bharatiya Nagarik Suraksha Sanhita 2023", "bnss-2023/sec-57", "bnss_2023"),
        _passage(4, "Code of Criminal Procedure 1973", "crpc-1973/sec-57", "crpc_1973"),
    ]

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
        _passage(1, "Reserve Bank Integrated Ombudsman Scheme 2021", "rbi-integrated-ombudsman-2021/sec-2", "rbi_integrated_ombudsman_2021"),
        _passage(2, procedure_title, procedure_anchor, "procedure"),
    ]

    workflow = _selected_workflow_result(query, route, passages, plan)

    assert workflow is not None
    joined = " ".join(workflow.lines)
    assert required_text in joined
    assert forbidden_text not in joined
    assert "Use RBI Scheme clauses 9 and 10" not in joined


def test_bank_freeze_ombudsman_claim_requires_clause_9_or_10_passage():
    query = "Cyber police froze my bank account in August 2025"
    route = route_matter(query)
    plan = build_matter_plan(query, route)
    assert plan is not None
    passages = [
        _passage(1, "Reserve Bank Integrated Ombudsman Scheme 2021", "rbi-integrated-ombudsman-2021/sec-2", "rbi_integrated_ombudsman_2021"),
        _passage(2, "Reserve Bank Integrated Ombudsman Scheme 2021", "rbi-integrated-ombudsman-2021/sec-9", "rbi_integrated_ombudsman_2021"),
        _passage(3, "Bharatiya Nagarik Suraksha Sanhita 2023", "bnss-2023/sec-106", "bnss_2023_bank_account_legal_hold"),
    ]

    workflow = _selected_workflow_result(query, route, passages, plan)

    assert workflow is not None
    assert "Use RBI Scheme clauses 9 and 10" in " ".join(workflow.lines)


def test_unknown_date_bank_freeze_answer_keeps_both_regimes_conditional():
    query = "Cyber police froze my bank account"
    route = route_matter(query)
    plan = build_matter_plan(query, route)
    assert plan is not None
    passages = [
        _passage(1, "Reserve Bank Integrated Ombudsman Scheme 2021", "rbi-integrated-ombudsman-2021/sec-2", "rbi_integrated_ombudsman_2021"),
        _passage(2, "Bharatiya Nagarik Suraksha Sanhita 2023", "bnss-2023/sec-106", "bnss_2023_bank_account_legal_hold"),
        _passage(3, "Code of Criminal Procedure 1973", "crpc-1973/sec-102", "crpc_1973_bank_account_legal_hold"),
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
        _passage(1, "Reserve Bank Integrated Ombudsman Scheme 2021", "rbi-integrated-ombudsman-2021/sec-2", "rbi_integrated_ombudsman_2021"),
        _passage(2, "Bharatiya Nagarik Suraksha Sanhita 2023", "bnss-2023/sec-106", "bnss_2023_bank_account_legal_hold"),
        _passage(3, "Information Technology Act 2000", "it-2000/sec-66C", "it_2000"),
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
        _passage(1, "Reserve Bank Integrated Ombudsman Scheme 2021", "rbi-integrated-ombudsman-2021/sec-2", "rbi_integrated_ombudsman_2021"),
        _passage(2, "Bharatiya Nagarik Suraksha Sanhita 2023", "bnss-2023/sec-106", "bnss_2023_bank_account_legal_hold"),
        _passage(3, "Information Technology Act 2000", "it-2000/sec-66C", "it_2000"),
    ]

    workflow = _selected_workflow_result(query, route, passages, plan)

    assert workflow is not None
    assert "Keep the IT Act source" in " ".join(workflow.lines)


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
