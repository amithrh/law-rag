from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest

from apps.api.config import Settings
from apps.api.matter_router import route_matter
from apps.api.retrieval import _anchor_boundary_regexes, _fetch_source_pack_candidates, _section_numbers_from_anchor_patterns
from apps.api.source_packs import source_packs_for_route


def _pack_ids(query: str) -> list[str]:
    route = route_matter(query)
    return [pack.id for pack in source_packs_for_route(route, query)]


def test_scst_atrocity_route_gets_exact_bare_act_pack():
    assert "scst_poa_1989" in _pack_ids(
        "mob attacked our pahan during sarna puja calling adivasi non hindu"
    )


def test_domestic_violence_route_gets_pwdva_pack():
    assert "pwdva_2005" in _pack_ids(
        "my husband's mother taunts me daily for not bringing more dowry"
    )


def test_cyber_intimate_threat_gets_it_act_pack():
    assert "it_act_2000" in _pack_ids(
        "bf secretly recorded us during sex now threatening to upload"
    )


def test_child_marriage_route_gets_pcma_pack():
    ids = _pack_ids("my brother is 13 they got him married to 20 year old how to stop")
    assert "child_marriage_2006" in ids
    assert "pocso_2012" in ids


def test_bonded_labour_route_gets_verified_fallback_packs():
    ids = _pack_ids("brick kiln owner up keeping family hostage advance 25000 cannot go home")
    assert "bonded_labour_1976" in ids
    assert "bonded_labour_pucl_sc" in ids
    assert "code_on_wages_2019" in ids
    assert "bnss_2023" in ids
    assert "crpc_1973" in ids


def test_disability_certificate_route_gets_rpwd_pack():
    ids = _pack_ids("I am disabled cannot walk officer not making my disability certificate 1 year")
    assert "rpwd_2016" in ids


def test_arrest_production_delay_gets_current_and_legacy_packs_when_date_unclear():
    query = "papa arrest 5 din ho gaya magistrate ke samne kab le jana hota hai"
    route = route_matter(query)
    packs = source_packs_for_route(route, query)
    by_id = {pack.id: pack for pack in packs}
    assert by_id["bnss_2023"].anchor_patterns[:2] == ("/sec-57", "/sec-58")
    assert by_id["crpc_1973"].anchor_patterns == ("/sec-56", "/sec-57")


def test_custody_legal_aid_gets_constitution_and_lsa_packs():
    query = "husband first time arrest jail superintendent not allowing lawyer meeting legal"
    route = route_matter(query)
    assert route.category == "legal_aid"
    by_id = {pack.id: pack for pack in source_packs_for_route(route, query)}
    assert "constitution_legal_aid" in by_id
    assert by_id["constitution_legal_aid"].anchor_patterns == ("/sec-39A", "/sec-22")
    assert "legal_services_authorities_1987" in by_id


def test_street_vendor_gets_bare_act_pack():
    route = route_matter("vegetable cart pune municipal seized everything")
    assert route.category == "street_vendor_municipal"
    assert "street_vendors_2014" in _pack_ids("vegetable cart pune municipal seized everything")


def test_stage33_hard_failure_queries_get_required_source_packs():
    expectations = {
        "iron ore mine displaced our 12 villages no rehabilitation given keonjhar": {"rfctlarr_2013", "rfctlarr_2013_scheduled_area_rr", "mmdr_1957"},
        "non tribal sahukar took my land in mortgage 15 years now refusing return jharkhand": {"chota_nagpur_tenancy_1908_transfer_restriction", "chota_nagpur_tenancy_1908_restoration", "constitution_scheduled_areas"},
        "cab driver mumbai uber deactivated rating low because customer racist hindi speaker": {"motor_vehicle_aggregator_guidelines_2020_contract", "motor_vehicle_aggregator_guidelines_2020_grievance", "motor_vehicle_aggregator_guidelines_2020_nondiscrimination", "constitution_article_14"},
        "I want to change my gender on aadhar and 10th certificate I have not had surgery is it possible": {"transgender_2019", "aadhaar_2016"},
        "construction company retrenched 40 of us bengali workers kept the gujaratis next day same site": {"industrial_disputes_1947", "constitution_article_14"},
        "my neighbor is parking his car blocking my dedicated parking slot in apartment, security guard says he cant do anything": {"consumer_protection_2019", "housing_parking_case_law"},
    }
    for query, expected_ids in expectations.items():
        ids = set(_pack_ids(query))
        assert expected_ids <= ids, query


def test_stage34_final100_gap_prompts_get_required_source_packs():
    expectations = {
        "my father wants to know if registered gift deed to son can be cancelled if son not caring": {"senior_citizens_2007", "transfer_property_1882"},
        "I gave my house to son in gift deed now he wants to throw me out can I cancel": {"senior_citizens_2007", "transfer_property_1882"},
        "mother in delhi son refuses to pay maintenance how much can tribunal order maximum": {"senior_citizens_2007"},
        "cops at delhi airport found my vape with thc oil what is the punishment": {"ndps_1985"},
        "llp partner refusing to sign form 11 annual return 2 years pending strike off threat": {"llp_2008"},
        "telegram channel leaked my onlyfans content without permission what to do": {"copyright_1957", "it_act_2000_intermediary"},
        "got porn video featuring lookalike of me 2 lakh views not me but face same": {"it_act_2000", "dpdp_2023_deepfake", "bns_2023"},
        "company building dam will submerge 4 tribal villages no consent gram sabha odisha": {"pesa_1996", "rfctlarr_2013"},
        "how is court fee calculated for civil suit valuation 25 lakh recovery": {"court_fees_1870"},
        "drug inspector picked up samples from my medical store schedule h sale without prescription jaipur": {"drugs_cosmetics_1940"},
    }
    for query, expected_ids in expectations.items():
        ids = set(_pack_ids(query))
        assert expected_ids <= ids, query


def test_stage33_near_misses_do_not_get_hard_route_source_packs():
    passenger_ids = set(_pack_ids("uber passenger gave low rating but I am customer not driver"))
    assert "motor_vehicle_aggregator_guidelines_2020_contract" not in passenger_ids
    assert "motor_vehicle_aggregator_guidelines_2020_grievance" not in passenger_ids
    assert "motor_vehicle_aggregator_guidelines_2020_nondiscrimination" not in passenger_ids
    assert "motor_vehicles_1988" not in passenger_ids
    customer_account_ids = set(_pack_ids("uber driver gave me low rating and my customer account deactivated, i am a customer"))
    assert "motor_vehicle_aggregator_guidelines_2020_contract" not in customer_account_ids
    assert "motor_vehicle_aggregator_guidelines_2020_grievance" not in customer_account_ids
    assert "motor_vehicle_aggregator_guidelines_2020_nondiscrimination" not in customer_account_ids
    assert "motor_vehicles_1988_aggregator" not in customer_account_ids
    assert "code_on_wages_2019" not in customer_account_ids
    assert "social_security_code_2020" not in customer_account_ids

    campus_ids = set(_pack_ids("my mining engineering college displaced my hostel room no rehabilitation"))
    assert "rfctlarr_2013" not in campus_ids
    assert "rfctlarr_2013_scheduled_area_rr" not in campus_ids
    assert "mmdr_1957" not in campus_ids

    surgery_ids = set(_pack_ids("need aadhaar correction after surgery but not gender change"))
    assert "transgender_2019" not in surgery_ids


def test_child_intimate_image_cyber_route_gets_it_act_and_pocso_packs():
    ids = _pack_ids("my 15 year daughter nude photo leaked on instagram")
    assert "it_act_2000" in ids
    assert "bns_2023" in ids
    assert "pocso_2012" in ids


def test_adult_offspring_intimate_image_does_not_get_pocso_pack():
    ids = _pack_ids("my 22 year old child nude photo leaked on instagram")
    assert "it_act_2000" in ids
    assert "pocso_2012" not in ids


def test_school_caste_violence_gets_scst_pack_not_rte():
    ids = _pack_ids("sarpanch from upper caste beat my son outside school called him untouchable name bastar")
    assert "scst_poa_1989" in ids
    assert "rte_2009" not in ids


def test_munda_land_grab_gets_tribal_atrocity_fallback_pack():
    ids = _pack_ids("munda land grabbed by upper caste in our agency village how to get back chaibasa")
    assert "scst_poa_1989" in ids


def test_retrenchment_gets_industrial_disputes_pack():
    query = "want to retrench 8 workers factory has 120 employees ludhiana garments need permission"
    packs = source_packs_for_route(route_matter(query), query)
    ids = [pack.id for pack in packs]
    assert "industrial_disputes_1947" in ids
    assert any(pack.anchor_patterns == ("/sec-25F", "/sec-25N") for pack in packs)


def test_retrenchment_same_site_gets_25g_25h_pack():
    query = "construction company retrenched 40 of us bengali workers kept the gujaratis next day same site"
    packs = source_packs_for_route(route_matter(query), query)
    ids = {pack.id for pack in packs}
    industrial = next(pack for pack in packs if pack.id == "industrial_disputes_1947")
    assert industrial.anchor_patterns == ("/sec-25F", "/sec-25G", "/sec-25H")
    assert {"industrial_disputes_1947_lifo", "industrial_disputes_1947_reemployment"} <= ids


def test_esi_notice_gets_labour_compliance_esi_pack():
    query = "ESI inspector notice says short contribution for casual workers how to contest"
    route = route_matter(query)
    assert route.category == "labour_compliance"
    packs = source_packs_for_route(route, query)
    esi = next(pack for pack in packs if pack.id == "esi_1948")
    assert esi.anchor_patterns == ("/sec-40", "/sec-43", "/sec-75")


def test_gst_cancellation_gets_exact_cgst_cancellation_pack():
    query = "GST registration cancelled for nil returns can I seek revocation or appeal"
    packs = source_packs_for_route(route_matter(query), query)
    cgst = next(pack for pack in packs if pack.id == "cgst_2017")
    assert cgst.anchor_patterns == ("/sec-29", "/sec-30", "/sec-107")


def test_manual_scavenging_death_gets_manual_and_compensation_packs():
    query = "septic tank cleaner died no safety equipment company refusing compensation"
    route = route_matter(query)
    assert route.category == "manual_scavenging_safety"
    ids = [pack.id for pack in source_packs_for_route(route, query)]
    assert "manual_scavenging_2013" in ids
    assert "employees_compensation_1923" in ids


def test_gig_id_blocked_gets_platform_and_wage_sources():
    query = "Swiggy rider ID blocked full and final pending after customer abused me"
    route = route_matter(query)
    assert route.category == "digital_platform_account"
    ids = [pack.id for pack in source_packs_for_route(route, query)]
    assert "code_on_wages_2019" in ids
    assert "social_security_code_2020" in ids


def test_passenger_account_dispute_does_not_get_worker_source_packs():
    query = "uber passenger account deactivated bad rating no driver"
    ids = [pack.id for pack in source_packs_for_route(route_matter(query), query)]
    assert "code_on_wages_2019" not in ids
    assert "social_security_code_2020" not in ids


def test_stage35_online_gambling_gets_state_and_public_gambling_sources():
    query = "lost 50k on dream11 like app is online rummy legal in tamil nadu"
    route = route_matter(query)
    ids = [pack.id for pack in source_packs_for_route(route, query)]
    assert "tamil_nadu_online_gambling_2022" in ids
    assert "public_gambling_1867" in ids


def test_stage35_gig_termination_gets_social_security_platform_sources():
    query = "urban company beautician 3 strike system unfair termination labour law"
    route = route_matter(query)
    ids = [pack.id for pack in source_packs_for_route(route, query)]
    assert "social_security_code_2020_gig_platform" in ids
    assert "industrial_disputes_1947_platform_status" in ids


def test_stage35_caste_certificate_and_parsi_succession_source_packs():
    caste_query = "my caste certificate rejected by tehsildar I am SC how to appeal"
    caste_ids = [pack.id for pack in source_packs_for_route(route_matter(caste_query), caste_query)]
    assert "constitution_article_341_342" in caste_ids
    assert "rti_2005" in caste_ids

    parsi_query = "parsi mother passed away in mumbai how property divided among us three sisters"
    parsi_ids = [pack.id for pack in source_packs_for_route(route_matter(parsi_query), parsi_query)]
    assert "indian_succession_1925" in parsi_ids


def test_generic_migrant_displacement_query_gets_ismw_and_wage_packs():
    query = "migrant workers brought from odisha never paid displacement allowance what law"
    route = route_matter(query)
    assert route.category == "labour_exploitation_discrimination"
    ids = [pack.id for pack in source_packs_for_route(route, query)]
    assert "ismw_1979" in ids
    assert "code_on_wages_2019" in ids


def test_udyam_payment_delay_gets_msmed_pack_without_invoice_wording():
    query = "udyam registered manufacturer buyer crossed 45 days payment amount outstanding"
    route = route_matter(query)
    assert route.category == "business_contract_partnership"
    ids = [pack.id for pack in source_packs_for_route(route, query)]
    assert "msmed_2006" in ids
    assert "indian_contract_1872" in ids


def test_msme_quality_deduction_gets_sale_of_goods_and_msmed_sources():
    query = "buyer deducting payment saying quality issue but no formal rejection given 9 lakh stuck"
    ids = [pack.id for pack in source_packs_for_route(route_matter(query), query)]
    assert "msmed_2006" in ids
    assert "sale_of_goods_1930" in ids


def test_scst_accused_source_pack_does_not_false_trigger_pmla_on_filed():
    query = "FIR filed on me SC ST POA false case how to get bail"
    route = route_matter(query)
    assert route.category == "criminal_defence_bail"
    ids = [pack.id for pack in source_packs_for_route(route, query)]
    assert "scst_poa_1989" in ids
    assert "pmla_2002" not in ids


def test_shop_act_license_route_gets_rti_status_fallback_pack():
    query = "labour inspector shop act registration renewal pending no status from office"
    route = route_matter(query)
    assert route.category == "business_license_compliance"
    ids = [pack.id for pack in source_packs_for_route(route, query)]
    assert "rti_2005" in ids


def test_rti_pack_orders_request_response_and_appeal_sections():
    query = "papa ki pension 6 month se nahi aayi rti kaise file karein"
    route = route_matter(query)
    packs = source_packs_for_route(route, query)
    rti = next(pack for pack in packs if pack.id == "rti_2005")
    assert rti.anchor_patterns == ("/sec-6", "/sec-7", "/sec-19")


def test_cognizance_challenge_pack_prioritizes_dismissal_and_revision():
    query = "magistrate refused to take cognizance complaint how to challenge"
    route = route_matter(query)
    packs = source_packs_for_route(route, query)
    by_id = {pack.id: pack for pack in packs}
    assert by_id["crpc_1973"].anchor_patterns[:2] == ("/sec-203", "/sec-397")
    assert by_id["bnss_2023"].anchor_patterns[:2] == ("/sec-226", "/sec-442")


def test_private_magistrate_complaint_gets_bnss_and_crpc_procedure_packs():
    query = "how to file private complaint before magistrate when police inaction"
    route = route_matter(query)
    assert route.category == "court_procedure"
    packs = source_packs_for_route(route, query)
    by_id = {pack.id: pack for pack in packs}
    assert "bnss_2023" in by_id
    assert "crpc_1973" in by_id
    assert "/sec-223" in by_id["bnss_2023"].anchor_patterns
    assert "/sec-175" in by_id["bnss_2023"].anchor_patterns
    assert "/sec-200" in by_id["crpc_1973"].anchor_patterns
    assert "/sec-156" in by_id["crpc_1973"].anchor_patterns


def test_identity_police_threat_gets_constitution_and_bns_packs():
    query = "manager threatening to call police saying we are bangladeshi but we are from murshidabad what to do"
    route = route_matter(query)
    packs = source_packs_for_route(route, query)
    by_id = {pack.id: pack for pack in packs}
    assert "constitution_article_21" in by_id
    assert "bns_2023" in by_id
    assert "/sec-351" in by_id["bns_2023"].anchor_patterns


def test_honour_threat_gets_bnss_173_not_bnss_216_fallback_pack():
    query = "my daughter eloped with boy of other religion family threatening her with khap panchayat"
    route = route_matter(query)
    packs = source_packs_for_route(route, query)
    by_id = {pack.id: pack for pack in packs}
    assert "bnss_2023_fir_information" in by_id
    assert by_id["bnss_2023_fir_information"].anchor_patterns == ("/sec-173",)


def test_ed_summons_gets_pmla_pack_not_cpc():
    query = "ED summons from enforcement directorate received what documents to carry"
    route = route_matter(query)
    assert route.category == "pmla_ed"
    packs = source_packs_for_route(route, query)
    by_id = {pack.id: pack for pack in packs}
    assert "pmla_2002" in by_id
    assert "cpc_1908" not in by_id
    assert "/sec-50" in by_id["pmla_2002"].anchor_patterns


def test_handcuff_custody_route_gets_constitution_and_restraint_anchors():
    query = "brother in handcuffs taken to court as high security prisoner without reason"
    route = route_matter(query)
    packs = source_packs_for_route(route, query)
    by_id = {pack.id: pack for pack in packs}
    assert "constitution_article_21" in by_id
    assert "/sec-43" in by_id["bnss_2023"].anchor_patterns
    assert "/sec-49" in by_id["crpc_1973"].anchor_patterns


def test_custodial_beating_gets_liberty_and_bns_sources():
    query = "police beating my brother in lockup and not giving medical help"
    route = route_matter(query)
    assert route.category == "police_fir"
    packs = source_packs_for_route(route, query)
    ids = [pack.id for pack in packs]
    assert "constitution_article_21" in ids
    assert "bns_2023" in ids
    by_id = {pack.id: pack for pack in packs}
    assert by_id["bnss_2023"].anchor_patterns == ("/sec-47", "/sec-48", "/sec-57", "/sec-58")
    assert by_id["crpc_1973"].anchor_patterns == ("/sec-50", "/sec-56", "/sec-57")


def test_after_arrest_beating_gets_custody_source_anchors():
    query = "police beat my brother after arrest and did not release him"
    route = route_matter(query)
    assert route.label == "Custodial violence / police extortion"
    by_id = {pack.id: pack for pack in source_packs_for_route(route, query)}
    assert "constitution_article_21" in by_id
    assert by_id["bnss_2023"].anchor_patterns == ("/sec-47", "/sec-48", "/sec-57", "/sec-58")
    assert by_id["crpc_1973"].anchor_patterns == ("/sec-50", "/sec-56", "/sec-57")

    query = "police hurt my brother during arrest and refused medical help"
    route = route_matter(query)
    assert route.label == "Custodial violence / police extortion"
    by_id = {pack.id: pack for pack in source_packs_for_route(route, query)}
    assert "constitution_article_21" in by_id
    assert by_id["bnss_2023"].anchor_patterns == ("/sec-47", "/sec-48", "/sec-57", "/sec-58")
    assert by_id["crpc_1973"].anchor_patterns == ("/sec-50", "/sec-56", "/sec-57")


def test_project_displacement_gets_rfctlarr_pack_not_migrant_wage_packs():
    query = "migrant workers displaced by dam compensation not paid"
    route = route_matter(query)
    assert route.category == "environment_compensation"
    ids = [pack.id for pack in source_packs_for_route(route, query)]
    assert "rfctlarr_2013" in ids
    assert "ismw_1979" not in ids
    assert "code_on_wages_2019" not in ids
    assert "rfctlarr_2013" in _pack_ids("displacement compensation not paid after highway project")
    assert "rfctlarr_2013" not in _pack_ids("environment damage from blasting")
    assert "rfctlarr_2013" not in _pack_ids("rehabilitation centre project grant not paid by government")


def test_joint_name_property_gets_transfer_of_property_pack():
    query = "father bought house in joint name with son in 2010 son now claims half share Kerala"
    route = route_matter(query)
    assert route.category == "property_tenancy"
    tpa = next(pack for pack in source_packs_for_route(route, query) if pack.id == "transfer_property_1882")
    assert "/sec-45" in tpa.anchor_patterns


def test_scst_poa_delay_gets_special_court_victim_rights_pack():
    query = "SC ST POA case special court pending 5 years what can complainant do"
    route = route_matter(query)
    assert route.category == "tribal_caste_atrocity"
    poa = next(pack for pack in source_packs_for_route(route, query) if pack.id == "scst_poa_1989")
    assert poa.anchor_patterns == ("/sec-13", "/sec-14", "/sec-15A")


def test_late_itr_gets_income_tax_234f_pack():
    query = "i forgot to file ITR for AY 2022-23 can i still file it now what is the penalty"
    packs = source_packs_for_route(route_matter(query), query)
    assert "income_tax_1961" in [pack.id for pack in packs]
    assert any("/sec-234F" in pack.anchor_patterns for pack in packs)


def test_gst_penalty_notice_does_not_get_income_tax_234f_pack():
    ids = _pack_ids("gst penalty notice for late return what to do")
    assert "cgst_2017" in ids
    assert "income_tax_1961" not in ids


def test_gst_search_seal_gets_cgst_67_83_pack():
    query = "gst officer sealed my godown without notice surat textile trader what to do"
    packs = source_packs_for_route(route_matter(query), query)
    assert "cgst_2017" in [pack.id for pack in packs]
    assert any(pack.anchor_patterns == ("/sec-67", "/sec-83") for pack in packs)


def test_parsi_succession_gets_indian_succession_pack():
    query = "parsi mother passed away in mumbai how property divided among us three sisters"
    packs = source_packs_for_route(route_matter(query), query)
    assert "indian_succession_1925" in [pack.id for pack in packs]
    assert any("/sec-50" in pack.anchor_patterns and "/sec-54" in pack.anchor_patterns for pack in packs)


def test_muslim_succession_gets_shariat_not_indian_or_hindu_succession():
    ids = _pack_ids("muslim father died property share between wife son mother")
    assert "shariat_1937" in ids
    assert "indian_succession_1925" not in ids
    assert "hindu_succession_1956" not in ids


def test_family_marriage_status_gets_bigamy_bns_not_generic_muslim_women_pack():
    query = "husband took second wife without divorcing me he says muslim law allows him I am also muslim"
    packs = source_packs_for_route(route_matter(query), query)
    by_id = {pack.id: pack for pack in packs}
    assert "shariat_1937" in by_id
    assert "muslim_women_2019" not in by_id
    assert by_id["bns_2023"].anchor_patterns == ("/sec-82",)


def test_post_dated_security_cheques_get_ni_pack():
    assert "ni_act_1881" in _pack_ids(
        "i issued post dated cheques as security to my landlord and he is misusing them"
    )


def test_voter_route_gets_indexed_rpa_packs():
    query = "voter id name spelt wrong booth officer denied me vote last election"
    route = route_matter(query)
    assert route.category == "election_voter_rights"
    packs = source_packs_for_route(route, query)
    by_id = {pack.id: pack for pack in packs}
    assert "rpa_1950" in by_id
    assert "rpa_1951" in by_id
    assert "/sec-22@" in by_id["rpa_1950"].anchor_patterns
    assert "/sec-23-" in by_id["rpa_1950"].anchor_patterns
    assert "/sec-62@" in by_id["rpa_1951"].anchor_patterns


def test_candidate_election_route_gets_rpa_1951_pack():
    packs = source_packs_for_route(
        route_matter("returning officer rejected my nomination for MLA election what remedy"),
        "returning officer rejected my nomination for MLA election what remedy",
    )
    assert any(pack.id == "rpa_1951" and "/sec-33" in pack.anchor_patterns and "/sec-36" in pack.anchor_patterns for pack in packs)

    conviction = source_packs_for_route(
        route_matter("candidate convicted for two years can he contest Lok Sabha election"),
        "candidate convicted for two years can he contest Lok Sabha election",
    )
    assert any(pack.id == "rpa_1951" and "/sec-8" in pack.anchor_patterns for pack in conviction)

    corrupt = source_packs_for_route(
        route_matter("booth capturing corrupt practice election petition to set aside result"),
        "booth capturing corrupt practice election petition to set aside result",
    )
    assert any(pack.id == "rpa_1951" and "/sec-123" in pack.anchor_patterns and "/sec-100@" in pack.anchor_patterns for pack in corrupt)

    false_affidavit_corrupt = source_packs_for_route(
        route_matter("candidate affidavit false assets corrupt practice election petition"),
        "candidate affidavit false assets corrupt practice election petition",
    )
    assert any(
        pack.id == "rpa_1951" and "/sec-123" in pack.anchor_patterns and "/sec-100@" in pack.anchor_patterns
        for pack in false_affidavit_corrupt
    )

    false_affidavit_petition = source_packs_for_route(
        route_matter("candidate affidavit false assets election petition"),
        "candidate affidavit false assets election petition",
    )
    assert any(
        pack.id == "rpa_1951"
        and "/sec-33A@" in pack.anchor_patterns
        and "/sec-125A@" in pack.anchor_patterns
        and "/sec-100@" in pack.anchor_patterns
        for pack in false_affidavit_petition
    )

    hidden_case_petition = source_packs_for_route(
        route_matter("candidate hid criminal case in affidavit election petition"),
        "candidate hid criminal case in affidavit election petition",
    )
    assert any(
        pack.id == "rpa_1951"
        and "/sec-33A@" in pack.anchor_patterns
        and "/sec-125A@" in pack.anchor_patterns
        and "/sec-100@" in pack.anchor_patterns
        for pack in hidden_case_petition
    )


def test_gratuity_and_pf_employment_get_indexed_source_packs():
    assert "gratuity_1972" in _pack_ids("father epf trust delayed gratuity 18 months")
    ids = _pack_ids("employer deducted PF but EPFO passbook empty")
    assert "epf_1952" in ids
    assert "social_security_code_2020" in ids


def test_eval_general_spillover_routes_get_required_source_packs():
    cases = {
        "domestic worker bangalore madam not paying 3 months said i broke vase wants 8000": ("code_on_wages_2019",),
        "factory deducted 800 every month for shoes uniform never given orissa worker tiruppur knitwear": ("code_on_wages_2019",),
        "muster roll fake entries BDO putting my name without me working khunti how complain": ("mgnrega_2005",),
        "thana refused to file complaint against zamindar who burnt our hut latehar": ("bnss_2023", "bns_2023"),
        "I am hearing impaired my employer is not providing interpreter for HR sessions and now they say I missed important update": ("rpwd_2016",),
        "my startup co founder is trying to dilute my equity using ESOP pool without my consent, i have 30 percent": ("companies_2013", "indian_contract_1872"),
        "ola driver took longer route and charged extra fare, customer support is closing complaint without resolution": ("consumer_protection_2019",),
        "zomato rider here met with accident on bike no insurance from company": ("social_security_code_2020", "motor_vehicles_1988"),
        "swiggy delivery partner accident no insurance from company": ("social_security_code_2020", "motor_vehicles_1988"),
        "agent took my goods worth 7 lakh and absconded gujarat principal agent relationship": ("indian_contract_1872",),
    }
    for query, expected_ids in cases.items():
        ids = _pack_ids(query)
        for expected_id in expected_ids:
            assert expected_id in ids, query
    mgnrega = source_packs_for_route(
        route_matter("muster roll fake entries BDO putting my name without me working khunti how complain"),
        "muster roll fake entries BDO putting my name without me working khunti how complain",
    )
    assert any(pack.id == "mgnrega_2005" and "/sec-17@" in pack.anchor_patterns for pack in mgnrega)
    assert any(pack.id == "mgnrega_2005" and "/sec-3@" in pack.anchor_patterns for pack in mgnrega)
    assert all("/sec-3" not in pack.anchor_patterns for pack in mgnrega if pack.id == "mgnrega_2005")


def test_final_eval_gap_routes_get_required_source_packs():
    cases = {
        "husband in arthur road tb test not done jail doctor 4 months waiting": (
            "constitution_article_21", "bnss_2023", "crpc_1973"
        ),
        "my 14 year old girlfriend's father filed pocso on me I am 17 we were in relationship": (
            "pocso_2012", "jj_2015", "bnss_2023", "crpc_1973"
        ),
        "my wife filed 498A on whole family even my old mother how to defend": (
            "bnss_2023", "bns_2023", "crpc_1973"
        ),
        "private limited mgt 7 aoc 4 not filed 3 years director disqualified can revive": (
            "companies_2013", "ibc_2016"
        ),
        "binance froze my usdt wallet 4 lakh saying suspicious trade is it legal": (
            "it_act_2000", "consumer_protection_2019"
        ),
        "private cooperative bank fd of grandfather not honoured nominee facing harassment": (
            "consumer_protection_2019",
        ),
        "someone leaked my chat with therapist on twitter mental health privacy": (
            "it_act_2000", "dpdp_2023", "mental_healthcare_2017"
        ),
        "I work at a place in malad they call it spa but customers want extra and owner makes us do it if we refuse no salary how": (
            "bnss_2023", "bns_2023", "itpa_1956"
        ),
        "garment unit jharkhand girl 15 working with us factory says she is 18 no proof": (
            "child_labour_1986", "jj_2015", "code_on_wages_2019"
        ),
        "how to get bocw card mumbai i work construction 8 years no card no benefit": (
            "bocw_1996",
        ),
        "fssai notice mismatch in licence category for snack manufacturing renewal due how to upgrade state to central": (
            "food_safety_2006",
        ),
        "my borewell water has come bad neighbours factory throwing chemicals": (
            "water_pollution_1974",
        ),
        "ration card west bengal not working in chennai shop no rice for family one nation one card not happening": (
            "national_food_security_2013",
        ),
        "came from supaul bihar to mumbai 6 months no payment munshi keeps saying next week": (
            "code_on_wages_2019",
        ),
        "my husband died 2024 i am 78 mutation of land in my name jharkhand process": (
            "hindu_succession_1956", "rti_2005"
        ),
    }
    for query, expected_ids in cases.items():
        ids = _pack_ids(query)
        for expected_id in expected_ids:
            assert expected_id in ids, query


def test_stage5_hard_fail_routes_get_required_source_packs():
    cases = {
        "thekedar gave 8 of us same name on register only 2 names real cheating bocw he gets cess": (
            "bocw_1996", "bocw_cess_1996", "bns_2023", "bnss_2023"
        ),
        "ex boyfriend follows my scooty everyday from office to home he doesn't talk just follows what section is this": (
            "bns_2023", "bnss_2023"
        ),
        "stalker on insta sending dm daily even after blocking how to file complaint": (
            "it_act_2000", "bns_2023"
        ),
        "I shared my ex girlfriend's photo angry on whatsapp group not nude just normal selfie now she filed 67 case": (
            "it_act_2000", "bnss_2023"
        ),
        "auto permit chennai expired in lockdown how to renew tamil nadu i came from cuddalore": (
            "motor_vehicles_1988",
        ),
        "received SARFAESI 13(2) notice from bank for home loan default of 14 months, can i still negotiate": (
            "sarfaesi_2002",
        ),
        "buyer deducting payment saying quality issue but no formal rejection given 9 lakh stuck": (
            "msmed_2006", "indian_contract_1872",
        ),
        "ismw registration who does it i never heard about it 15 years in surat textile": (
            "ismw_1979", "code_on_wages_2019",
        ),
        "i undertrial 3 yrs in puzhal lawyer not coming hearings when can complain": (
            "legal_services_authorities_1987", "constitution_article_21", "bnss_2023"
        ),
        "husband took my salary atm card and gives me only 2000 per month for groceries is this legal he says he is breadwinner": (
            "pwdva_2005",
        ),
        "my daughter is 17 she ran away with boy of different religion police is saying it is love jihad and she will come back what is law": (
            "pocso_2012", "bns_2023", "bnss_2023"
        ),
        "sister died at in laws house they say suicide but body had marks dowry case": (
            "bns_2023", "bnss_2023"
        ),
    }
    for query, expected_ids in cases.items():
        ids = _pack_ids(query)
        for expected_id in expected_ids:
            assert expected_id in ids, query

    bocw_packs = source_packs_for_route(
        route_matter("thekedar gave same name on register cheating bocw gets cess"),
        "thekedar gave same name on register cheating bocw gets cess",
    )
    assert any(pack.id == "bocw_1996" and "/sec-13" in pack.anchor_patterns for pack in bocw_packs)
    assert any(pack.id == "bocw_cess_1996" and "/sec-3" in pack.anchor_patterns for pack in bocw_packs)


def test_cyber_dm_substring_does_not_trigger_stalking_source_anchors():
    packs = source_packs_for_route(
        route_matter("college admission scam on whatsapp asking fee refund"),
        "college admission scam on whatsapp asking fee refund",
    )
    it_pack = next(pack for pack in packs if pack.id == "it_act_2000")
    assert "/sec-66E" not in it_pack.anchor_patterns
    assert "/sec-67" not in it_pack.anchor_patterns
    assert "/sec-78" not in it_pack.anchor_patterns

    stalking_packs = source_packs_for_route(
        route_matter("stalker on insta sending dm daily even after blocking how to file complaint"),
        "stalker on insta sending dm daily even after blocking how to file complaint",
    )
    by_id = {pack.id: pack for pack in stalking_packs}
    assert "/sec-78" not in by_id["it_act_2000"].anchor_patterns
    assert "/sec-78" in by_id["bns_2023"].anchor_patterns


def test_senior_gift_transfer_gets_section_23_preference():
    query = "my father gifted flat to my brother but now brother stopped giving food can gift be cancelled"
    route = route_matter(query)
    packs = source_packs_for_route(route, query)
    assert "senior_citizens_2007" in [pack.id for pack in packs]
    assert any("/sec-23" in pack.anchor_patterns for pack in packs)
    tpa_pack = next(pack for pack in packs if pack.id == "transfer_property_1882")
    assert "/sec-122" in tpa_pack.anchor_patterns
    assert "/sec-120" not in tpa_pack.anchor_patterns


def test_wage_query_gets_code_on_wages_pack():
    assert "code_on_wages_2019" in _pack_ids(
        "contractor is paying less than minimum wage and no overtime"
    )


def test_nrega_query_gets_mgnrega_pack():
    assert "mgnrega_2005" in _pack_ids(
        "worked 42 days under nrega but job card mate says payment rejected"
    )


def test_construction_injury_gets_bocw_pack():
    assert "bocw_1996" in _pack_ids(
        "construction site fall broke spine no bocw card contractor says no compensation"
    )


def test_generic_site_injury_does_not_get_bocw_pack():
    assert "bocw_1996" not in _pack_ids(
        "warehouse site accident hand broken company refuses compensation"
    )


def test_rti_route_gets_rti_pack():
    query = "I filed an RTI and it was rejected what is first appeal time limit"
    route = route_matter(query)
    packs = source_packs_for_route(route, query)
    assert "rti_2005" in [pack.id for pack in packs]
    assert any("/sec-19" in pack.anchor_patterns for pack in packs)


def test_police_fir_gets_bnss_and_bns_current_packs():
    query = "police refused to register FIR for theft of my bike"
    route = route_matter(query)
    packs = source_packs_for_route(route, query)
    ids = [pack.id for pack in packs]
    assert "bnss_2023" in ids
    assert "bns_2023" in ids
    assert any("/sec-173" in pack.anchor_patterns for pack in packs)
    assert any("/sec-303" in pack.anchor_patterns for pack in packs)


def test_legacy_default_bail_gets_crpc_167_pack():
    query = "arrested in 2023 and 90 days passed with no chargesheet default bail"
    route = route_matter(query)
    packs = source_packs_for_route(route, query)
    ids = [pack.id for pack in packs]
    assert "crpc_1973" in ids
    assert "bnss_2023" not in ids
    crpc_pack = next(pack for pack in packs if pack.id == "crpc_1973")
    assert "/sec-167" in crpc_pack.anchor_patterns
    assert "/sec-161-j" in crpc_pack.anchor_patterns


def test_unclear_default_bail_gets_both_bnss_and_crpc_packs():
    query = "brother in jail 90 days no chargesheet can he get default bail"
    route = route_matter(query)
    ids = [pack.id for pack in source_packs_for_route(route, query)]
    assert "bnss_2023" in ids
    assert "crpc_1973" in ids


def test_ndps_default_bail_gets_ndps_pack():
    query = "brother in NDPS case arrested 110 days no chargesheet default bail possible"
    route = route_matter(query)
    packs = source_packs_for_route(route, query)
    ids = [pack.id for pack in packs]
    assert "ndps_1985" in ids
    ndps_pack = next(pack for pack in packs if pack.id == "ndps_1985")
    assert "section 36A" in ndps_pack.search_query
    assert {"/sec-35-b", "/sec-35-c", "/sec-35-d"} <= set(ndps_pack.anchor_patterns)


def test_ndps_default_bail_pack_fetches_focused_section_36a_from_runtime_chunks():
    async def check() -> None:
        asyncpg = pytest.importorskip("asyncpg")
        settings = Settings()
        try:
            pool = await asyncpg.create_pool(dsn=settings.resolved_database_url_host_side, min_size=1, max_size=1)
        except Exception as exc:
            pytest.fail(f"runtime DB unavailable for NDPS source-pack validation: {exc}")
        try:
            query = "brother in NDPS case arrested 110 days no chargesheet default bail possible"
            route = route_matter(query)
            ndps_pack = next(pack for pack in source_packs_for_route(route, query) if pack.id == "ndps_1985")
            chunks = await _fetch_source_pack_candidates(
                pool,
                query,
                packs=[ndps_pack],
                limit_per_pack=4,
            )
            assert chunks
            assert all(chunk.anchor == "ndps-1985/sec-36A" for chunk in chunks)
            assert all(chunk.metadata.get("section_no") == "36A" for chunk in chunks)
            assert any(
                chunk.anchor == "ndps-1985/sec-36A"
                and chunk.metadata.get("section_no") == "36A"
                and "one hundred and eighty days" in chunk.text.lower()
                for chunk in chunks
            )
        finally:
            await pool.close()

    asyncio.run(check())


def test_stage34_official_packs_fetch_focused_runtime_chunks_without_sparse_vectors():
    async def check() -> None:
        asyncpg = pytest.importorskip("asyncpg")
        settings = Settings()
        try:
            pool = await asyncpg.create_pool(dsn=settings.resolved_database_url_host_side, min_size=1, max_size=1)
        except Exception as exc:
            pytest.fail(f"runtime DB unavailable for Stage34 source-pack validation: {exc}")
        try:
            court_query = "how is court fee calculated for civil suit valuation 25 lakh recovery"
            court_route = route_matter(court_query)
            court_pack = next(
                pack for pack in source_packs_for_route(court_route, court_query)
                if pack.id == "court_fees_1870"
            )
            court_chunks = await _fetch_source_pack_candidates(
                pool,
                court_query,
                packs=[court_pack],
                limit_per_pack=4,
            )
            assert court_chunks
            assert any(chunk.anchor.startswith("court-fees-1870/sec-7") for chunk in court_chunks)
            assert any("computation of fees payable" in chunk.text.lower() for chunk in court_chunks)

            drugs_query = "drug inspector picked up samples from my medical store schedule h sale without prescription jaipur"
            drugs_route = route_matter(drugs_query)
            drugs_pack = next(
                pack for pack in source_packs_for_route(drugs_route, drugs_query)
                if pack.id == "drugs_cosmetics_1940"
            )
            drugs_chunks = await _fetch_source_pack_candidates(
                pool,
                drugs_query,
                packs=[drugs_pack],
                limit_per_pack=4,
            )
            assert drugs_chunks
            assert any(chunk.anchor.startswith("drugs-cosmetics-1940/sec-18") for chunk in drugs_chunks)
            assert any(chunk.anchor.startswith("drugs-cosmetics-1940/sec-22") for chunk in drugs_chunks)
            assert any(chunk.anchor.startswith("drugs-cosmetics-1940/sec-23") for chunk in drugs_chunks)
            assert any("powers of inspectors" in chunk.text.lower() for chunk in drugs_chunks)
        finally:
            await pool.close()

    asyncio.run(check())


def test_sc_scholarship_pack_fetches_focused_constitution_article_46_from_runtime_chunks():
    async def check() -> None:
        asyncpg = pytest.importorskip("asyncpg")
        settings = Settings()
        try:
            pool = await asyncpg.create_pool(dsn=settings.resolved_database_url_host_side, min_size=1, max_size=1)
        except Exception as exc:
            pytest.fail(f"runtime DB unavailable for Article 46 source-pack validation: {exc}")
        try:
            query = "school principal not giving SC scholarship saying papers wrong since 2 years vidarbha"
            route = route_matter(query)
            pack = next(pack for pack in source_packs_for_route(route, query) if pack.id == "constitution_article_46")
            chunks = await _fetch_source_pack_candidates(
                pool,
                query,
                packs=[pack],
                limit_per_pack=4,
            )
            assert chunks
            assert all(chunk.anchor == "constitution-india/sec-46" for chunk in chunks)
            assert all(chunk.metadata.get("section_no") == "46" for chunk in chunks)
            assert any("scheduled castes" in chunk.text.lower() for chunk in chunks)
        finally:
            await pool.close()

    asyncio.run(check())


def test_jj_adoption_pack_fetches_focused_runtime_adoption_sections():
    async def check() -> None:
        asyncpg = pytest.importorskip("asyncpg")
        settings = Settings()
        try:
            pool = await asyncpg.create_pool(dsn=settings.resolved_database_url_host_side, min_size=1, max_size=1)
        except Exception as exc:
            pytest.fail(f"runtime DB unavailable for JJ source-pack validation: {exc}")
        try:
            query = "we are not a hindu family adopted child from sister no papers now real parents want him back"
            route = route_matter(query)
            jj_pack = next(pack for pack in source_packs_for_route(route, query) if pack.id == "jj_2015")
            chunks = await _fetch_source_pack_candidates(
                pool,
                query,
                packs=[jj_pack],
                limit_per_pack=4,
            )
            assert chunks
            assert {chunk.metadata.get("section_no") for chunk in chunks} <= {"56", "57", "58", "59", "62", "63"}
            assert any(chunk.anchor == "jj-2015/sec-56" for chunk in chunks)
        finally:
            await pool.close()

    asyncio.run(check())


def test_jj_age_pack_fetches_focused_runtime_age_sections():
    async def check() -> None:
        asyncpg = pytest.importorskip("asyncpg")
        settings = Settings()
        try:
            pool = await asyncpg.create_pool(dsn=settings.resolved_database_url_host_side, min_size=1, max_size=1)
        except Exception as exc:
            pytest.fail(f"runtime DB unavailable for JJ age source-pack validation: {exc}")
        try:
            query = "son 17 yrs in adult jail puzhal pocso case age proof school certificate where to file"
            route = route_matter(query)
            packs = source_packs_for_route(route, query)
            by_id = {pack.id: pack for pack in packs}
            assert "jj_2015_age_claim_court" in by_id
            assert "jj_2015_age_documents" in by_id
            chunks = await _fetch_source_pack_candidates(
                pool,
                query,
                packs=[by_id["jj_2015_age_claim_court"], by_id["jj_2015_age_documents"]],
                limit_per_pack=4,
            )
            anchors = {chunk.anchor for chunk in chunks}
            assert "jj-2015/sec-9" in anchors
            assert "jj-2015/sec-94" in anchors
            normalized_texts = [" ".join(chunk.text.lower().split()) for chunk in chunks]
            assert any("claims before a court other than a board" in text for text in normalized_texts)
            assert any("date of birth certificate from the school" in chunk.text.lower() for chunk in chunks)
        finally:
            await pool.close()

    asyncio.run(check())


def test_section_91_notice_gets_bnss_94_and_crpc_91_when_date_unclear():
    query = "police sent section 91 notice asking for my phone and whatsapp chats what to do"
    route = route_matter(query)
    packs = source_packs_for_route(route, query)
    by_id = {pack.id: pack for pack in packs}
    assert by_id["bnss_2023"].anchor_patterns == ("/sec-94",)
    assert by_id["crpc_1973"].anchor_patterns == ("/sec-91",)


def test_section_91_notice_with_fir_still_prioritizes_production_sections():
    query = "police sent section 91 notice in FIR 123 asking for phone"
    route = route_matter(query)
    packs = source_packs_for_route(route, query)
    by_id = {pack.id: pack for pack in packs}
    assert by_id["bnss_2023"].anchor_patterns == ("/sec-94",)
    assert by_id["crpc_1973"].anchor_patterns == ("/sec-91",)


def test_default_bail_with_fir_still_prioritizes_remand_sections():
    query = "FIR 2025 arrested 90 days no chargesheet default bail"
    route = route_matter(query)
    packs = source_packs_for_route(route, query)
    by_id = {pack.id: pack for pack in packs}
    assert by_id["bnss_2023"].anchor_patterns == ("/sec-187",)
    assert "crpc_1973" not in by_id


def test_mixed_date_default_bail_gets_dual_procedure_packs():
    query = "arrested in 2025 for FIR from 2023 90 days no chargesheet default bail"
    route = route_matter(query)
    packs = source_packs_for_route(route, query)
    by_id = {pack.id: pack for pack in packs}
    assert by_id["bnss_2023"].anchor_patterns == ("/sec-187",)
    assert by_id["crpc_1973"].anchor_patterns[:4] == ("/sec-161-j", "/sec-161-k", "/sec-161-l", "/sec-161-m")


def test_legacy_criminal_query_does_not_force_new_codes():
    assert "bnss_2023" not in _pack_ids("false ipc 420 case from 2020 can i get bail")


def test_legal_aid_query_gets_legal_services_pack():
    assert "legal_services_authorities_1987" in _pack_ids(
        "free legal aid for woman domestic violence case how to apply in dlsa"
    )


def test_lok_adalat_award_challenge_gets_section_21_pack():
    query = "lok adalat award passed without my consent can I challenge it"
    route = route_matter(query)
    packs = source_packs_for_route(route, query)
    assert "legal_services_authorities_1987" in [pack.id for pack in packs]
    assert any("/sec-21" in pack.anchor_patterns for pack in packs)


def test_cheque_bounce_pack_prioritizes_138_and_142():
    query = "cheque bounced yesterday when should i send legal notice and file 138 case"
    route = route_matter(query)
    packs = source_packs_for_route(route, query)
    assert "ni_act_1881" in [pack.id for pack in packs]
    assert any(pack.anchor_patterns == ("/sec-138", "/sec-142") for pack in packs)


def test_passport_route_does_not_claim_missing_passports_act_pack():
    query = "passport police verification adverse report because old criminal case what remedy"
    route = route_matter(query)
    assert route.category == "passport_police_verification"
    assert source_packs_for_route(route, query) == []


def test_forest_and_pesa_queries_get_tribal_source_packs():
    forest_ids = _pack_ids(
        "forest officer stopped us collecting tendu leaves in community forest"
    )
    assert "fra_2006" in forest_ids
    assert "scst_poa_1989" not in forest_ids
    ids = _pack_ids("mining company started blasting without gram sabha consent in scheduled area")
    assert "pesa_1996" in ids


def test_fra_bamboo_patta_gets_forest_rights_pack():
    ids = _pack_ids("patta given under FRA but forest guards still cutting our bamboo saying it is reserved bastar")
    assert "fra_2006" in ids


def test_hard_fail_router_repairs_get_required_source_packs():
    assert {"jj_2015_age_claim_court", "jj_2015_age_documents", "jj_2015_bail_board"} <= set(
        _pack_ids("16 yr boy detained adult jail 2 weeks already how to transfer observation home")
    )
    assert {"pwdva_2005", "bns_2023", "bnss_2023"} <= set(
        _pack_ids("my mother in law is threatening to throw acid on me if I don't get more money from my parents")
    )
    education_loan_ids = _pack_ids("bank not giving education loan to my daughter even though we have scholarship paper")
    assert {"rbi_integrated_ombudsman_2021", "consumer_protection_2019"} <= set(education_loan_ids)
    assert "rte_2009" not in education_loan_ids
    assert {"constitution_article_21", "bnss_2023", "bnss_2023_medical_bail"} <= set(
        _pack_ids("paralegal volunteer 4 women undertrials byculla pregnant where rule postpone trial bail")
    )
    security_ids = _pack_ids(
        "i issued post dated cheques as security to my landlord, he is now misusing them after i vacated, what to do"
    )
    assert {"ni_act_138_security_cheque", "ni_act_1881"} <= set(security_ids)
    assert {"senior_citizens_2007", "ni_act_1881"} <= set(
        _pack_ids("son gave me cheque for monthly maintenance it bounced twice can i file case")
    )


def test_undertrial_review_gets_bnss_479_crpc_436a_and_legal_aid_packs():
    query = "i am paralegal volunteer in tihar undertrial 70 yrs ipc 302 how to apply 479 BNSS review"
    packs = source_packs_for_route(route_matter(query), query)
    by_id = {pack.id: pack for pack in packs}
    assert by_id["constitution_article_21"].anchor_patterns == ("/sec-21",)
    assert by_id["bnss_2023"].anchor_patterns == ("/sec-479",)
    assert "/sec-436A" in by_id["crpc_1973"].anchor_patterns
    assert "legal_services_authorities_1987" in by_id


def test_cpc_procedure_queries_get_cpc_pack():
    execution = source_packs_for_route(
        route_matter("decree holder how to file execution petition Order 21 CPC"),
        "decree holder how to file execution petition Order 21 CPC",
    )
    assert "cpc_1908" in [pack.id for pack in execution]
    assert any("/sec-47" in pack.anchor_patterns for pack in execution)

    second_appeal = source_packs_for_route(
        route_matter("second appeal high court substantial question of law procedure"),
        "second appeal high court substantial question of law procedure",
    )
    assert any(pack.id == "cpc_1908" and pack.anchor_patterns == ("/sec-100",) for pack in second_appeal)


def test_customs_and_itat_tax_queries_get_exact_tax_packs():
    customs = source_packs_for_route(
        route_matter("customs ICEGATE bill of entry hold importer what appeal remedy"),
        "customs ICEGATE bill of entry hold importer what appeal remedy",
    )
    assert "customs_1962" in [pack.id for pack in customs]

    itat = source_packs_for_route(
        route_matter("ITAT appeal delay after income tax assessment order what is limitation"),
        "ITAT appeal delay after income tax assessment order what is limitation",
    )
    by_id = {pack.id: pack for pack in itat}
    assert "income_tax_1961" in by_id
    assert by_id["income_tax_1961"].anchor_patterns == ("/sec-253", "/sec-254")


def test_child_return_gets_guardians_and_family_courts_packs():
    ids = _pack_ids(
        "my husband took our 5 year old to delhi during fight and is not letting me meet how do I get her back fast"
    )
    assert "guardians_wards_1890" in ids
    assert "family_courts_1984" in ids


def test_mutual_consent_divorce_gets_hma_and_not_pwdva_by_default():
    ids = _pack_ids(
        "want to file mutual consent divorce, both me and husband agree, what is the process and time in mumbai"
    )
    assert "hindu_marriage_1955" in ids
    assert "family_courts_1984" in ids
    assert "pwdva_2005" not in ids


def test_non_hindu_and_special_marriage_divorce_do_not_get_hma():
    assert "hindu_marriage_1955" not in _pack_ids(
        "we are christian couple want mutual consent divorce both agree"
    )
    assert "indian_divorce_1869" in _pack_ids(
        "we are christian couple want mutual consent divorce both agree"
    )

    special_ids = _pack_ids(
        "special marriage couple mutual consent divorce both agree section 28"
    )
    assert "special_marriage_1954" in special_ids
    assert "hindu_marriage_1955" not in special_ids

    muslim_ids = _pack_ids("mutual consent divorce muslim couple both agree procedure")
    assert "dissolution_muslim_marriages_1939" in muslim_ids
    assert "shariat_1937" in muslim_ids
    assert "hindu_marriage_1955" not in muslim_ids


def test_triple_talaq_whatsapp_gets_muslim_women_pack_not_it_act():
    ids = _pack_ids("husband gave instant triple talaq on whatsapp what remedy muslim")
    assert "muslim_women_2019" in ids
    assert "it_act_2000" not in ids


def test_rti_second_appeal_and_consumer_delay_do_not_get_cpc_pack():
    assert "rti_2005" in _pack_ids("RTI second appeal no reply from PIO for ration records")
    assert "cpc_1908" not in _pack_ids("RTI second appeal no reply from PIO for ration records")
    assert "consumer_protection_2019" in _pack_ids("condonation of delay consumer complaint limitation")
    assert "cpc_1908" not in _pack_ids("condonation of delay consumer complaint limitation")


def test_tax_subissue_packs_use_correct_anchors():
    income_refund = source_packs_for_route(
        route_matter("income tax refund stuck ITR processed no refund"),
        "income tax refund stuck ITR processed no refund",
    )
    assert any(pack.id == "income_tax_1961" and "/sec-237" in pack.anchor_patterns for pack in income_refund)
    assert not any("/sec-234F" in pack.anchor_patterns for pack in income_refund)

    custom_refund = source_packs_for_route(
        route_matter("customs refund rejected drawback appeal importer"),
        "customs refund rejected drawback appeal importer",
    )
    assert any(pack.id == "customs_1962" and "/sec-27" in pack.anchor_patterns and "/sec-75" in pack.anchor_patterns for pack in custom_refund)

    gst_appeal_ids = _pack_ids("company assessment order under GST can appeal")
    assert "cgst_2017" in gst_appeal_ids
    assert "income_tax_1961" not in gst_appeal_ids

    cit_packs = source_packs_for_route(
        route_matter("CIT(A) appeal against 143(3) assessment order limitation"),
        "CIT(A) appeal against 143(3) assessment order limitation",
    )
    assert any(pack.id == "income_tax_1961" and "/sec-249" in pack.anchor_patterns for pack in cit_packs)

    first_appeal = source_packs_for_route(
        route_matter("district court dismissed my civil suit how to file first appeal CPC limitation"),
        "district court dismissed my civil suit how to file first appeal CPC limitation",
    )
    assert any(pack.id == "cpc_1908" and "/sec-96" in pack.anchor_patterns for pack in first_appeal)
    assert "limitation_1963" in [pack.id for pack in first_appeal]


def test_surrogacy_route_gets_indexed_source_pack():
    query = "we want a baby through surrogate my wife had hysterectomy 4 years ago we are both 38 is surrogacy allowed for us"
    route = route_matter(query)
    assert route.category == "surrogacy_parenthood"
    packs = source_packs_for_route(route, query)
    assert any(pack.id == "surrogacy_2021" and "surrogacy-2021/sec-4-" in pack.anchor_patterns for pack in packs)


def test_surrogacy_abortion_gets_surrogacy_section_10_and_mtp_pack():
    query = "surrogacy abortion terminate pregnancy consent surrogate mother clinic forcing"
    route = route_matter(query)
    assert route.category == "surrogacy_parenthood"
    packs = source_packs_for_route(route, query)
    by_id = {pack.id: pack for pack in packs}
    assert "surrogacy_2021" in by_id
    assert "surrogacy-2021/sec-10@" in by_id["surrogacy_2021"].anchor_patterns
    assert "mtp_1971" in by_id


def test_new_source_pack_doc_ids_are_registered_locally():
    registry = Path(__file__).resolve().parents[3] / "data" / "processed" / "acts.jsonl"
    if not registry.exists():
        pytest.skip("local acts.jsonl registry is not present")
    slugs = set()
    with registry.open() as f:
        for line in f:
            line = line.strip()
            if line:
                slugs.add(json.loads(line)["slug"])
    needed = {
        "street-vendors-2014",
        "child-marriage-2006",
        "rpwd-2016",
        "indian-succession-1925",
        "income-tax-1961",
        "customs-1962",
        "cpc-1908",
        "guardians-wards-1890",
        "family-courts-1984",
        "hindu-marriage-1955",
        "special-marriage-1954",
        "indian-divorce-1869",
        "dissolution-muslim-marriages-1939",
        "shariat-1937",
        "muslim-women-2019",
        "limitation-1963",
        "legal-services-authorities-1987",
        "fra-2006",
        "pesa-1996",
        "mgnrega-2005",
        "bocw-1996",
        "bocw-cess-1996",
        "crpc-1973",
        "hindu-marriage-1955",
        "ismw-1979",
        "msmed-2006",
        "sarfaesi-2002",
        "crpc-1973",
        "rpa-1950",
        "rpa-1951",
        "surrogacy-2021",
        "constitution-india",
        "companies-2013",
        "jj-2015",
        "dpdp-2023",
        "consumer-protection-2019",
        "itpa-1956",
        "food-safety-standards-2006",
        "water-pollution-1974",
        "child-labour-1986",
        "bonded-labour-1976",
        "national-food-security-2013",
        "banking-regulation-1949",
        "protection-civil-rights-1955",
        "uapa-1967",
        "prisons-1894",
        "commercial-courts-2015",
        "mmdr-1957",
        "forest-conservation-1980",
        "environment-protection-1986",
        "ngt-2010",
        "cgst-rules-2017",
        "insurance-ombudsman-rules-2017",
        "rbi-integrated-ombudsman-2021",
        "credit-information-companies-2005",
        "protection-human-rights-1993",
        "assam-witch-hunting-2015",
        "chota-nagpur-tenancy-1908",
        "santhal-parganas-tenancy-1949",
        "nhm-asha-incentives-2025",
        "contract-labour-1970",
        "bihar-kanya-vivah-service",
        "sale-of-goods-1930",
        "pension-regulations-army-2008-part-i",
        "pension-regulations-army-2008-part-ii",
        "prevention-of-corruption-1988",
        "bihar-prohibition-excise-2016",
        "nsap-guidelines-2014",
        "court-fees-1870",
        "drugs-cosmetics-1940",
    }
    assert not (needed - slugs)


def test_new_official_law_packs_have_runtime_db_chunks_and_anchors():
    async def check() -> None:
        asyncpg = pytest.importorskip("asyncpg")
        settings = Settings()
        try:
            conn = await asyncpg.connect(dsn=settings.resolved_database_url_host_side, timeout=3)
        except Exception as exc:
            pytest.fail(f"runtime DB unavailable for source-pack validation: {exc}")

        try:
            queries = [
                "voter id name spelt wrong booth officer denied me vote last election",
                "returning officer rejected my nomination for MLA election what remedy",
                "candidate convicted for two years can he contest Lok Sabha election",
                "election petition limitation after result declaration recount set aside",
                "booth capturing corrupt practice election petition to set aside result",
                "surrogacy abortion terminate pregnancy consent surrogate mother clinic forcing",
                "we want a baby through surrogate my wife had hysterectomy 4 years ago we are both 38 is surrogacy allowed for us",
                "fssai notice mismatch in licence category for snack manufacturing renewal due how to upgrade state to central",
                "my borewell water has come bad neighbours factory throwing chemicals",
                "garment unit jharkhand girl 15 working with us factory says she is 18 no proof",
                "brick kiln owner up keeping family hostage advance 25000 cannot go home",
                "ration card west bengal not working in chennai shop no rice for family one nation one card not happening",
                "private cooperative bank fd of grandfather not honoured nominee facing harassment",
                "ESI inspector notice says short contribution for casual workers how to contest",
                "GST registration cancelled for nil returns can I seek revocation or appeal",
                "construction company retrenched 40 of us bengali workers kept the gujaratis next day same site",
                "septic tank cleaner died no safety equipment company refusing compensation",
                "father bought house in joint name with son in 2010 son now claims half share Kerala",
                "SC ST POA case special court pending 5 years what can complainant do",
                "thekedar gave 8 of us same name on register only 2 names real cheating bocw he gets cess",
                "ismw registration who does it i never heard about it 15 years in surat textile",
                "buyer deducting payment saying quality issue but no formal rejection given 9 lakh stuck",
                "received SARFAESI 13(2) notice from bank for home loan default of 14 months, can i still negotiate",
                "we married under Special Marriage Act and need mutual divorce after one year separation",
                "want to file mutual consent divorce, both me and husband agree, what is the process and time in mumbai",
                "false ipc 420 cheating case from 2020 can i get bail",
                "auto driver bangalore traffic police taking 500 every week no challan saying tamil license invalid",
                "police caught me drinking in bihar under prohibition law what punishment",
                "old age pension stopped suddenly bank says aadhaar not linked",
            ]
            required_pack_ids = {
                "rpa_1950",
                "rpa_1951",
                "surrogacy_2021",
                "food_safety_2006",
                "water_pollution_1974",
                "child_labour_1986",
                "bonded_labour_1976",
                "national_food_security_2013",
                "banking_regulation_1949",
                "esi_1948",
                "cgst_2017",
                "industrial_disputes_1947",
                "manual_scavenging_2013",
                "employees_compensation_1923",
                "transfer_property_1882",
                "scst_poa_1989",
                "bocw_1996",
                "bocw_cess_1996",
                "ismw_1979",
                "msmed_2006",
                "sarfaesi_2002",
                "special_marriage_1954",
                "hindu_marriage_1955",
                "crpc_1973",
                "prevention_corruption_1988",
                "bihar_prohibition_excise_2016",
                "nsap_guidelines_2014",
            }
            seen_pack_ids: set[str] = set()
            for query in queries:
                route = route_matter(query)
                for pack in source_packs_for_route(route, query):
                    if pack.id not in required_pack_ids:
                        continue
                    seen_pack_ids.add(pack.id)
                    chunk_count = await conn.fetchval(
                        """
                        SELECT COUNT(*)
                        FROM chunks c
                        JOIN documents d ON d.id = c.document_id
                        WHERE d.doc_id = ANY($1::text[])
                          AND NOT c.quarantined
                        """,
                        list(pack.doc_ids),
                    )
                    assert chunk_count > 0, f"{pack.id} has no runtime DB chunks"
                    sparse_null_count = await conn.fetchval(
                        """
                        SELECT COUNT(*)
                        FROM chunks c
                        JOIN documents d ON d.id = c.document_id
                        WHERE d.doc_id = ANY($1::text[])
                          AND c.embedding_sparse IS NULL
                          AND NOT c.quarantined
                        """,
                        list(pack.doc_ids),
                    )
                    assert sparse_null_count == 0, f"{pack.id} has runtime DB chunks without sparse vectors"
                    section_nos = _section_numbers_from_anchor_patterns(pack.anchor_patterns)
                    anchor_regexes = _anchor_boundary_regexes(section_nos)
                    for section_no, anchor_regex in zip(section_nos, anchor_regexes, strict=True):
                        anchor_count = await conn.fetchval(
                            """
                            SELECT COUNT(*)
                            FROM chunks c
                            JOIN documents d ON d.id = c.document_id
                            WHERE d.doc_id = ANY($1::text[])
                              AND (
                                c.metadata->>'section_no' = $2
                                OR c.anchor ~* $3
                              )
                              AND NOT c.quarantined
                            """,
                            list(pack.doc_ids),
                            section_no,
                            anchor_regex,
                        )
                        assert anchor_count > 0, f"{pack.id} section {section_no} has no exact DB match"
            assert seen_pack_ids == required_pack_ids
        finally:
            await conn.close()

    asyncio.run(check())


def test_source_pack_config_defaults():
    s = Settings(database_url="postgresql://x")
    assert s.required_source_pack_enabled is True
    assert s.required_source_pack_limit_per_pack == 4
    assert s.required_source_pack_min_score == pytest.approx(0.42)
    assert s.required_source_pack_boost == pytest.approx(0.10)


def test_stage24_hard_fail_prompts_get_required_source_packs():
    expected = {
        "thekedar took 18000 advance from me darbhanga not letting leave bangalore site": {"bonded_labour_1976", "ismw_1979"},
        "fell from 5th floor site whitefield bangalore leg broken thekedar saying no insurance no bocw card": {"bocw_1996", "employees_compensation_1923"},
        "how to file complaint before NGT for illegal construction near wetland": {"ngt_2010"},
        "received summons under section 91 bnss for my deleted insta posts is it serious": {"bnss_2023", "it_act_2000"},
        "my company laptop has been seized by police as part of investigation against my colleague, what are my rights": {"bnss_2023", "it_act_2000"},
        "i am poor brother arrested can court give free lawyer nalsa kya hota hai": {"legal_services_authorities_1987", "constitution_legal_aid"},
        "my husband's brother has been making me uncomfortable saying things and now grabbed my hand whom to tell I cant tell husband": {"pwdva_2005", "bns_2023"},
        "vendor at my office sends me whatsapp emojis and asks for date I told him no but he keeps": {"posh_2013"},
        "we adopted child from sister but no papers now real parents want him back": {"hindu_adoptions_maintenance_1956", "jj_2015"},
        "panchayat secretary not giving me birth certificate of my child born at home": {"rti_2005"},
    }
    for query, required_ids in expected.items():
        assert required_ids <= set(_pack_ids(query)), query


def test_stage24_review_fix_source_pack_false_positive_guards():
    ismw_near_miss = "thekedar took advance from me to buy tools and not letting leave bangalore site"
    assert "ismw_1979" not in _pack_ids(ismw_near_miss)

    muslim_adoption_ids = set(_pack_ids("muslim family adopted child from sister no papers now real parents want him back"))
    assert {"guardians_wards_1890", "jj_2015", "family_courts_1984"} <= muslim_adoption_ids
    assert "hindu_adoptions_maintenance_1956" not in muslim_adoption_ids
    assert "hindu_minority_guardianship_1956" not in muslim_adoption_ids

    catholic_adoption_ids = set(_pack_ids("catholic family adopted child from sister no papers now real parents want him back"))
    assert {"guardians_wards_1890", "jj_2015", "family_courts_1984"} <= catholic_adoption_ids
    assert "hindu_adoptions_maintenance_1956" not in catholic_adoption_ids
    assert "hindu_minority_guardianship_1956" not in catholic_adoption_ids

    not_hindu_adoption_ids = set(_pack_ids("we are not hindu adopted child from sister no papers now real parents want him back"))
    assert {"guardians_wards_1890", "jj_2015", "family_courts_1984"} <= not_hindu_adoption_ids
    assert "hindu_adoptions_maintenance_1956" not in not_hindu_adoption_ids
    assert "hindu_minority_guardianship_1956" not in not_hindu_adoption_ids
    assert "hindu_marriage_1955" not in not_hindu_adoption_ids

    not_a_hindu_adoption_ids = set(_pack_ids("we are not a hindu family adopted child from sister no papers now real parents want him back"))
    assert {"guardians_wards_1890", "jj_2015", "family_courts_1984"} <= not_a_hindu_adoption_ids
    assert "hindu_adoptions_maintenance_1956" not in not_a_hindu_adoption_ids
    assert "hindu_minority_guardianship_1956" not in not_a_hindu_adoption_ids
    assert "hindu_marriage_1955" not in not_a_hindu_adoption_ids


def test_stage25_final100_hard_fail_prompts_get_required_source_packs():
    expected = {
        "guy from telegram crypto group rugpulled me 3 lakh whom to complain": {"it_act_2000", "bns_2023", "bnss_2023", "pmla_2002"},
        "telegram channel leaked my onlyfans content without permission what to do": {"it_act_2000", "copyright_1957", "bns_2023", "bnss_2023"},
        "ndps bail rejected 6 times by session court husband 3 yrs in tihar option": {"ndps_1985", "constitution_article_21", "bnss_2023"},
        "my husband lost hand in brick kiln no compensation owner saying he was careless": {"employees_compensation_1923", "factories_1948"},
        "upper caste people beat my husband called us by caste name FIR not registered": {"scst_poa_1989", "bnss_2023"},
        "school principal not giving SC scholarship saying papers wrong since 2 years vidarbha": {"constitution_article_46", "rti_2005"},
        "fake call from sbi pension office took 2 lakh from my account 75 yr father": {"senior_citizens_2007", "it_act_2000", "bns_2023", "bnss_2023"},
        "code on wages applicable to me minimum wage notification gujarat for unskilled worker": {"code_on_wages_2019"},
        "construction site delhi 14 hour work no overtime contractor laughing when i ask": {"code_on_wages_2019"},
        "husband forces me at night even when I say no I am tired or unwell is there any law for this in india now": {"pwdva_2005", "bns_2023", "bnss_2023"},
        "i complained against my manager for harassment to HR and now they are putting me on PIP, is this retaliation": {"industrial_disputes_1947"},
        "fanvue payment frozen 2400 usd indian creator how to release fund": {"fema_1999", "income_tax_1961", "indian_contract_1872"},
        "in-laws not giving back my jewellery streedhan after husband died": {"dowry_prohibition_1961", "hindu_succession_1956", "pwdva_2005"},
    }
    for query, required_ids in expected.items():
        assert required_ids <= set(_pack_ids(query)), query


def test_stage27_final100_hard_fail_prompts_get_required_source_packs():
    expected = {
        "company hiding behind section 43B disallowance threat to delay my msme payment": {"msmed_2006", "income_tax_2025_transition_faq", "income_tax_43b_h", "indian_contract_1872"},
        "data breach at byjus my pan and aadhaar leaked, can i claim compensation under DPDP act": {"dpdp_2023", "it_act_2000"},
        "cooperative bank seized my buffalo for crop loan default can they take livestock": {"cooperative_bank_recovery_case_law", "sarfaesi_2002", "banking_regulation_1949"},
        "false dacoity case lodged on my brother by forest guard for collecting tendu leaves dindori": {"fra_2006", "bns_2023", "bnss_2023"},
        "the spa was raided last week and police took me and other girls to station I just do massage I am scared what will happen now": {"itpa_1956", "bns_2023", "bnss_2023"},
        "site mukadam beat me head injury 8 stitches when i asked for old wages mumbai": {"bns_2023", "employees_compensation_1923", "code_on_wages_2019"},
        "daughter in law took my jewellery worth 12 lakh saying for safe keeping not returning agra": {"bns_2023", "bnss_2023", "pwdva_2005"},
        "my dad signed property to son under pressure when he was in icu can challenge": {"transfer_property_1882", "indian_contract_1872", "specific_relief_1963"},
        "son 17 yrs in adult jail puzhal pocso case age proof school certificate where to file": {"jj_2015", "bnss_2023"},
        "i was undertrial 5 yrs released last week need help to file police torture case": {"constitution_article_21", "protection_human_rights_1993", "bns_2023"},
        "how to legally change my surname after marriage, do i need to publish in gazette": {
            "deptpub_name_change_adult_formalities",
            "deptpub_name_change_adult_required_documents",
            "deptpub_name_change_adult_egazette_download",
            "name_change_case_law",
        },
        "sarpanch giving common village land to his brother no panchayat meeting was held": {"constitution_panchayats_part_ix", "panchayat_common_land_case_law", "rti_2005"},
        "society management has put a fine of 25000 on me for keeping a pet without prior approval, is this legal": {"bmc_pet_guidelines_ban", "bmc_pet_guidelines_bylaws", "cooperative_housing_society_case_law"},
    }
    for query, required_ids in expected.items():
        assert required_ids <= set(_pack_ids(query)), query
    assert "bns_2023" not in _pack_ids("data breach at byjus my pan and aadhaar leaked can i claim compensation under DPDP act")
    assert "bnss_2023" not in _pack_ids("how to legally change my surname after marriage do i need to publish in gazette")
    criminal_data_route = route_matter("pan aadhaar leaked identity misuse fake loan fraud dpdp complaint")
    criminal_data_pack = next(pack for pack in source_packs_for_route(criminal_data_route, "pan aadhaar leaked identity misuse fake loan fraud dpdp complaint") if pack.id == "bns_2023")
    assert {"/sec-318", "/sec-336"} <= set(criminal_data_pack.anchor_patterns)
    assert {"bns_2023", "bnss_2023"} <= set(_pack_ids("pan aadhaar leaked fake loan in my name dpdp complaint"))


def test_stage25_source_pack_false_positive_guards():
    assert "pmla_2002" not in _pack_ids("telegram group discussing crypto tax in india")
    assert "pmla_2002" not in _pack_ids("telegram group discussing crypto tax in india whom to complain to for wrong tax advice")
    assert "pmla_2002" not in _pack_ids("telegram crypto group tax advice about my money where complain")
    assert "pmla_2002" not in _pack_ids("telegram crypto group how much money should i invest for tax planning")
    assert "pmla_2002" not in _pack_ids("telegram crypto investment group says this is not scam only tax discussion")
    assert "pmla_2002" in _pack_ids("telegram crypto group said not scam then took my money")
    assert "pmla_2002" in _pack_ids("telegram crypto admin said not scam asked for otp then vanished with money")
    assert "pmla_2002" in _pack_ids("telegram crypto group said not scam connect wallet and drained my account")
    assert "pmla_2002" in _pack_ids("crypto telegram admin asked seed phrase and stole my crypto")
    assert "copyright_1957" not in _pack_ids("onlyfans creator asking about income tax on payouts")
    assert "copyright_1957" not in _pack_ids("telegram channel for onlyfans creator promotion income tax on payouts")
    assert "employees_compensation_1923" not in _pack_ids("construction site delhi 14 hour work no overtime contractor laughing when i ask")
    assert "senior_citizens_2007" not in _pack_ids("father is 45 fake call from sbi pension office took 2 lakh from my account")
    assert "constitution_article_46" not in _pack_ids("private school merit scholarship not released for sports quota")
    assert "bns_2023" not in _pack_ids("husband does not force sex but we need divorce advice")

    hama_ids = source_packs_for_route(
        route_matter("we adopted child from sister but no papers now real parents want him back"),
        "we adopted child from sister but no papers now real parents want him back",
    )
    hama = next(pack for pack in hama_ids if pack.id == "hindu_adoptions_maintenance_1956")
    assert "/sec-11" not in hama.anchor_patterns

    laptop_packs = source_packs_for_route(
        route_matter("my company laptop has been seized by police as part of investigation against my colleague"),
        "my company laptop has been seized by police as part of investigation against my colleague",
    )
    by_id = {pack.id: pack for pack in laptop_packs}
    assert by_id["bnss_2023"].anchor_patterns == ("/sec-105", "/sec-106", "/sec-185", "/sec-497", "/sec-503")
    assert by_id["crpc_1973"].anchor_patterns == ("/sec-100", "/sec-102", "/sec-165", "/sec-451", "/sec-457")

    release_notice_packs = source_packs_for_route(
        route_matter("police notice for release of seized phone after investigation"),
        "police notice for release of seized phone after investigation",
    )
    release_by_id = {pack.id: pack for pack in release_notice_packs}
    assert release_by_id["bnss_2023"].anchor_patterns == ("/sec-105", "/sec-106", "/sec-185", "/sec-497", "/sec-503")
    assert release_by_id["crpc_1973"].anchor_patterns == ("/sec-100", "/sec-102", "/sec-165", "/sec-451", "/sec-457")


def test_witch_false_case_does_not_trigger_generic_child_pocso_packs():
    ids = set(_pack_ids("they say i am tonhi after child died in village false case filed chhattisgarh"))
    assert "pocso_2012" not in ids
    assert "jj_2015" not in ids
    assert {"bnss_2023", "bns_2023"} <= ids


def test_stage6_failure_prompts_get_required_source_packs():
    expected = {
        "food safety officer collected sample from my kirana said adulteration delhi azadpur": {"food_safety_2006"},
        "contractor said go back home pandemic no return ticket money given 9 of us walked from delhi": {"ismw_1979", "code_on_wages_2019"},
        "how to file habeas corpus petition husband detained illegally by police": {"constitution_article_21", "bnss_2023"},
        "he gets angry and slaps me but says sorry next day my parents say all marriages are like this should I stay": {"pwdva_2005", "bns_2023"},
        "patwari asking 5000 rupees to enter my name in revenue records can I complain": {"prevention_corruption_1988", "rti_2005"},
        "land acquired for coal block without consulting palli sabha angul odisha": {"rfctlarr_2013", "pesa_1996"},
        "16 yr daughter arrested theft put in observation home or jail how to verify age": {"jj_2015", "bnss_2023"},
    }
    for query, required_ids in expected.items():
        assert required_ids <= set(_pack_ids(query)), query


def test_stage7_gate_source_gaps_get_official_source_packs():
    expected = {
        "brother UAPA arrested 3 months chargesheet not filed total custody can be extended 180 days": {"uapa_1967", "bnss_2023"},
        "tihar jail mulaqat only 30 min once a week is this legal can we ask more": {"prisons_1894", "constitution_article_21"},
        "respondent skipped pre litigation mediation can my commercial suit be rejected at threshold": {"commercial_courts_2015", "mediation_2023", "cpc_1908"},
        "rule 86B applies to me turnover 55 lakh per month must pay 1% cash mandatory ya choot hai": {"cgst_rules_2017", "cgst_2017"},
        "agent sold pension money to ulip policy father lost 8 lakh how to complain": {"consumer_protection_2019", "insurance_ombudsman_rules_2017"},
        "how to file PIL in high court regarding pollution from factory nearby": {"constitution_article_226", "environment_protection_1986", "water_pollution_1974", "ngt_2010"},
        "DM gave NOC to bauxite project bastar without gram sabha resolution how to challenge": {"pesa_1996", "mmdr_1957", "forest_conservation_1980"},
        "upper caste people stopped dalit family entering temple and taking water from village well": {"protection_civil_rights_1955", "constitution_article_17"},
        "bank recovery agents are harassing me after complaint bank says fair practices not applicable can i go to rbi ombudsman": {"banking_regulation_1949", "rbi_integrated_ombudsman_2021", "consumer_protection_2019"},
        "CIBIL still shows old closed loan as written off how to correct credit report": {"credit_information_companies_2005", "consumer_protection_2019"},
        "police refusing FIR caste atrocity case sub inspector saying it is small matter jharkhand": {"scst_poa_1989", "bnss_2023"},
        "police beating brother in lockup arthur road how to complain nhrc procedure": {"constitution_article_21", "protection_human_rights_1993", "bnss_2023"},
        "I am gay and my parents are forcing me to marry a girl next month they are not listening I am 26 what is my right": {"constitution_article_21"},
        "freelance designer 18 lakh income should i register gst or no": {"cgst_2017", "income_tax_1961"},
        "binance froze my usdt wallet 4 lakh saying suspicious trade is it legal": {"consumer_protection_2019", "pmla_2002"},
        "tribal land sold to non tribal by uncle without our consent is it legal": {"constitution_scheduled_areas"},
        "my saas labelled daayan and beaten by village people assam barpeta": {"assam_witch_hunting_2015", "bns_2023"},
        "site supervisor saying minimum wage 350 only but karnataka rate is 600 construction unskilled": {"code_on_wages_2019"},
        "I am ASHA worker not paid honorarium 6 months who can help": {"nhm_asha_incentives_2025"},
        "appeal against NCLT order to NCLAT how many days limit": {"ibc_2016"},
        "my mother 81 not allowed in her own kitchen by daughter in law mumbai legal remedy": {"senior_citizens_2007", "pwdva_2005"},
        "principal employer reliance site contractor ran away with 4 months wages 22 workers what to do": {"contract_labour_1970", "code_on_wages_2019"},
        "principal employer reliance site contractor brought workers from bihar to gujarat and wages unpaid": {"contract_labour_1970", "ismw_1979", "code_on_wages_2019"},
        "brother arrested no fir copy given family police saying secret kya rule": {"bnss_2023", "constitution_article_22"},
        "kanya vivah scheme money not given by government after my daughter wedding": {"rti_2005"},
        "bihar kanya vivah scheme money not given by government after my daughter wedding": {"bihar_kanya_vivah_service", "rti_2005"},
        "my husband died in army no service pension widow what papers needed": {"army_pension_regulations_2008_part_i", "army_pension_regulations_2008_part_ii"},
        "old age pension stopped suddenly bank says aadhaar not linked": {"nsap_guidelines_2014", "aadhaar_2016", "rti_2005"},
        "family pension not paid after husband died in bihar rti kaise karein": {"rti_2005"},
        "recovery agents from a NBFC visited my office and shouted in front of colleagues, this is harassment right": {"rbi_integrated_ombudsman_2021", "consumer_protection_2019"},
        "i am 73 christian widow can my stepchildren claim share in husband self acquired property": {"indian_succession_1925"},
        "vendor agreed delivery in 30 days now 4 months over want to cancel and recover advance 8 lakh": {"indian_contract_1872", "sale_of_goods_1930"},
        "my husband had affair I caught them I slapped the woman now she is filing case on me what to do": {"bns_2023", "bnss_2023"},
        "fake call from sbi pension office took 2 lakh from my account 75 yr father": {"it_act_2000", "bns_2023", "bnss_2023"},
        "vendor zone bhopal allotted me 2018 now hawker inspector saying pay 2000 every month otherwise remove": {"street_vendors_2014", "prevention_corruption_1988"},
    }
    for query, required_ids in expected.items():
        assert required_ids <= set(_pack_ids(query)), query


def test_stage10_abort_hard_fail_prompts_get_source_packs():
    expected = {
        "father custodial death lockup byculla police saying suicide what is 196 procedure": {"constitution_article_21", "protection_human_rights_1993", "bnss_2023"},
        "girl child 12 helping mother in our migrant camp domestic work delhi is this illegal she is my niece": {"child_labour_1986", "jj_2015"},
        "passport seized in mumbai airport for vape cartridge cbd legal in goa": {"ndps_1985", "bnss_2023"},
        "papa ki pension 6 month se nahi aayi rti kaise file karein": {"rti_2005"},
        "auto driver bangalore traffic police taking 500 every week no challan saying tamil license invalid": {"motor_vehicles_1988", "prevention_corruption_1988"},
        "bonded labour my chacha working for thakur 12 years no wages just food bihar": {"bonded_labour_1976"},
        "police caught me drinking village they saying case under prohibition law what punishment": {"constitution_article_47", "bnss_2023", "crpc_1973"},
        "police caught me drinking in bihar under prohibition law what punishment": {"bihar_prohibition_excise_2016", "constitution_article_47", "bnss_2023", "crpc_1973"},
    }
    for query, required_ids in expected.items():
        assert required_ids <= set(_pack_ids(query)), query


def test_stage36_blocker_queries_get_required_source_packs():
    expected = {
        "trademark application opposed by a bigger company saying it is similar to their mark, hearing scheduled": {"trade_marks_1999"},
        "my land taken for highway 4 years back compensation still not received who to ask": {"rfctlarr_2013"},
        "how to approach Lok Adalat for pending traffic challan settlement": {"legal_services_authorities_1987"},
        "maharashtra construction site labour department raid kiya overtime register not maintained 11 workers what to do": {
            "maharashtra_shops_establishments_2017",
            "bocw_1996",
        },
        "thakur men forced me to drink dirty water from well saying dalit cannot touch dindori mp": {
            "protection_civil_rights_1955",
            "constitution_article_17",
        },
        "bajaj finserv EMI bounced because of bank error, now they are charging 6000 penalty and threatening CIBIL": {
            "rbi_integrated_ombudsman_2021",
            "credit_information_companies_2005",
        },
    }
    for query, required_ids in expected.items():
        assert required_ids <= set(_pack_ids(query)), query
    non_construction_ids = set(_pack_ids(
        "maharashtra labour department raid kiya overtime register not maintained 11 workers what to do"
    ))
    assert "maharashtra_shops_establishments_2017" in non_construction_ids
    assert "bocw_1996" not in non_construction_ids
    assert "maharashtra_shops_establishments_2017" not in _pack_ids(
        "delhi labour department raid overtime register not maintained 11 workers"
    )


def test_child_custody_and_will_prompts_get_all_core_family_source_packs():
    custody_ids = set(_pack_ids("wife and child living separately I want custody of son aged 6"))
    assert {"guardians_wards_1890", "hindu_minority_guardianship_1956", "family_courts_1984"} <= custody_ids

    will_ids = set(_pack_ids("father made will in 1998 not registered now after death sons fighting is unregistered will valid"))
    assert {"indian_succession_1925", "registration_1908"} <= will_ids


def test_msme_tcs_gst_and_cyber_variants_get_exact_packs():
    msme_ids = set(_pack_ids("psu not paid me since 8 months MSME registered party can i charge interest"))
    assert "msmed_2006" in msme_ids

    assert "income_tax_1961" in _pack_ids("TCS deducted on foreign remittance for my son education abroad how do i claim it back")
    assert "cgst_2017" in _pack_ids("rule 86B applies to me turnover 55 lakh per month must pay 1% cash mandatory ya choot hai")
    assert "cgst_rules_2017" in _pack_ids("rule 86B applies to me turnover 55 lakh per month must pay 1% cash mandatory ya choot hai")

    cyber_ids = set(_pack_ids("delhi police chargesheet for tweet calling cm corrupt is this 356 case"))
    assert {"it_act_2000", "bns_2023", "bnss_2023"} <= cyber_ids


def test_review_blocker_source_pack_near_misses():
    accident_ids = set(_pack_ids("my brother was hurt in a road accident police made station diary but no FIR"))
    assert "constitution_article_21" not in accident_ids

    tribal_school_project_ids = set(_pack_ids("tribal student needs noc for college project but officer is delaying certificate"))
    assert "rfctlarr_2013" not in tribal_school_project_ids

    env_ids = set(_pack_ids("thermal plant blasting cracking our houses no compensation kalahandi"))
    assert env_ids

    invoice_ids = set(_pack_ids("client not paying invoice for website project 2 lakh"))
    assert "msmed_2006" not in invoice_ids


def test_stage10_source_pack_false_positive_guards():
    thakur_only_ids = set(_pack_ids(
        "bonded labour my chacha working for thakur 12 years no wages just food bihar"
    ))
    assert "bonded_labour_1976" in thakur_only_ids
    assert "scst_poa_1989" not in thakur_only_ids

    explicit_dalit_ids = set(_pack_ids(
        "dalit bonded labour working for thakur 12 years no wages just food bihar"
    ))
    assert {"bonded_labour_1976", "scst_poa_1989"} <= explicit_dalit_ids

    for query in (
        "dalit bonded labour working for contractor no wages just food",
        "adivasi bonded labour working for contractor no wages just food",
        "scheduled tribe bonded labour working for contractor no wages just food",
    ):
        assert {"bonded_labour_1976", "scst_poa_1989"} <= set(_pack_ids(query))

    adivasi_labour_ids = set(_pack_ids(
        "adivasi bonded labour working for upper caste landlord no wages just food"
    ))
    assert "scst_poa_1989" in adivasi_labour_ids
    assert "chota_nagpur_tenancy_1908_transfer_restriction" not in adivasi_labour_ids
    assert "chota_nagpur_tenancy_1908_restoration" not in adivasi_labour_ids
    assert "santhal_parganas_tenancy_1949" not in adivasi_labour_ids
    assert "constitution_scheduled_areas" not in adivasi_labour_ids
    assert "chota_nagpur_tenancy_1908_transfer_restriction" not in _pack_ids(
        "non tribal employee transfer order delayed with land records department"
    )
    assert "chota_nagpur_tenancy_1908_restoration" not in _pack_ids(
        "non tribal employee transfer order delayed with land records department"
    )
    assert "chota_nagpur_tenancy_1908_transfer_restriction" not in _pack_ids(
        "tribal welfare land records training workshop cancelled want refund"
    )
    assert "chota_nagpur_tenancy_1908_restoration" not in _pack_ids(
        "tribal welfare land records training workshop cancelled want refund"
    )
    maharashtra_land_ids = set(_pack_ids(
        "adivasi family landlord grabbed our land without consent in maharashtra"
    ))
    assert "constitution_scheduled_areas" in maharashtra_land_ids
    assert "chota_nagpur_tenancy_1908_transfer_restriction" not in maharashtra_land_ids
    assert "chota_nagpur_tenancy_1908_restoration" not in maharashtra_land_ids
    assert "santhal_parganas_tenancy_1949" not in maharashtra_land_ids
    jharkhand_land_ids = set(_pack_ids(
        "munda land grabbed by upper caste in our agency village how to get back chaibasa"
    ))
    assert {
        "chota_nagpur_tenancy_1908_transfer_restriction",
        "chota_nagpur_tenancy_1908_restoration",
        "santhal_parganas_tenancy_1949",
        "constitution_scheduled_areas",
    } <= jharkhand_land_ids

    assert "rpa_1951" not in _pack_ids("politician deepfake video not during election just trolling")
    assert "rpa_1951" not in _pack_ids("candidate deepfake video during election campaign")
    assert "rpa_1951" in _pack_ids("MLA candidate deepfake video during election campaign")
    assert "rpa_1951" in _pack_ids("politician deepfake video during election campaign")
    assert "rpa_1951" not in _pack_ids("job candidate deepfake video shared by HR group")
    assert "rpa_1951" not in _pack_ids("job candidate deepfake video shared before company voting in HR group")
    assert "rpa_1951" not in _pack_ids("housing society election candidate deepfake video on whatsapp")
    assert "rpa_1951" not in _pack_ids("student union candidate deepfake video during campus election campaign")
    assert "rpa_1951" not in _pack_ids("trade union election candidate deepfake video shared by opponent")
    assert "rpa_1951" not in _pack_ids("club election candidate deepfake video on whatsapp during campaign")
    assert "rpa_1951" not in _pack_ids("cooperative bank election candidate deepfake video shared by rival")

    software_delivery_ids = set(_pack_ids(
        "software vendor agreed delivery in 30 days now 4 months over want to cancel and recover advance"
    ))
    assert "indian_contract_1872" in software_delivery_ids
    assert "sale_of_goods_1930" not in software_delivery_ids

    for query in (
        "wedding decoration service vendor agreed delivery in 30 days now 4 months over want to cancel and recover advance",
        "training vendor took advance and did not deliver workshop want recover advance",
        "photography vendor agreed delivery in 30 days now 4 months over want cancel and recover advance",
        "catering vendor agreed delivery in 30 days now 4 months over want cancel and recover advance",
        "architect vendor agreed delivery in 30 days now 4 months over want to cancel and recover advance",
    ):
        ids = set(_pack_ids(query))
        assert "indian_contract_1872" in ids
        assert "sale_of_goods_1930" not in ids

    goods_delivery_ids = set(_pack_ids(
        "vendor agreed delivery in 30 days now 4 months over want to cancel and recover advance 8 lakh"
    ))
    assert "sale_of_goods_1930" in goods_delivery_ids
    machinery_ids = set(_pack_ids("supplier failed to deliver machinery after taking advance 8 lakh"))
    assert {"indian_contract_1872", "sale_of_goods_1930"} <= machinery_ids

    assert "army_pension_regulations_2008_part_i" not in _pack_ids(
        "army civilian contractor widow pension documents delayed"
    )
    assert "army_pension_regulations_2008_part_i" not in _pack_ids(
        "civilian contractor in army died can widow get pension papers"
    )
    assert "army_pension_regulations_2008_part_i" not in _pack_ids(
        "civilian contractor in army can widow get family pension papers"
    )
    assert "army_pension_regulations_2008_part_i" not in _pack_ids(
        "army base canteen contractor family pension not released after death"
    )
    assert "army_pension_regulations_2008_part_i" not in _pack_ids(
        "family pension not paid after husband died in bihar rti kaise karein"
    )
    assert "nsap_guidelines_2014" not in _pack_ids(
        "family pension not paid after husband died in bihar rti kaise karein"
    )
    assert "nsap_guidelines_2014" not in _pack_ids(
        "state government retired teacher family pension not paid in bihar"
    )
    assert "nsap_guidelines_2014" not in _pack_ids(
        "army civilian contractor widow pension documents delayed"
    )
    assert "army_pension_regulations_2008_part_i" in _pack_ids(
        "my husband died in army no service pension widow what papers needed"
    )

    assert "bihar_prohibition_excise_2016" not in _pack_ids(
        "police caught me drinking near bihar border in up under prohibition law what punishment"
    )
    assert "bihar_prohibition_excise_2016" not in _pack_ids(
        "police caught me drinking in bihar colony delhi under prohibition law what punishment"
    )
    assert "bihar_prohibition_excise_2016" not in _pack_ids(
        "bihar police caught me drinking in delhi under prohibition law"
    )
    assert "bihar_prohibition_excise_2016" in _pack_ids(
        "police caught me drinking in bihar under prohibition law what punishment"
    )

    assert "national_food_security_2013" not in _pack_ids(
        "aadhaar registration for widow pension pending no reply"
    )
    assert "national_food_security_2013" in _pack_ids(
        "ration card not working pds no rice for family"
    )
