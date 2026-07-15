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


def _packs_by_id(query: str):
    route = route_matter(query)
    return {pack.id: pack for pack in source_packs_for_route(route, query)}


def test_scst_atrocity_route_gets_exact_bare_act_pack():
    assert "scst_poa_1989" in _pack_ids(
        "mob attacked our pahan during sarna puja calling adivasi non hindu"
    )


def test_mental_health_confinement_gets_protection_and_emergency_sections():
    packs = _packs_by_id("my brother mentally ill family kept him in chains how to admit in hospital legally")

    expected = {
        "mental_healthcare_2017_confinement_dignity": "/sec-20",
        "mental_healthcare_2017_confinement_police_protection": "/sec-100",
        "mental_healthcare_2017_confinement_emergency": "/sec-94",
        "mental_healthcare_2017_confinement_restraint": "/sec-97",
    }
    for pack_id, anchor in expected.items():
        assert pack_id in packs
        assert anchor in packs[pack_id].anchor_patterns


def test_gratuity_eligibility_gets_section4_source_pack():
    packs = _packs_by_id("section 4 gratuity eligibility 4 years 11 months service where to go")

    assert "gratuity_1972_eligibility" in packs
    assert "/sec-4" in packs["gratuity_1972_eligibility"].anchor_patterns


def test_welfare_identity_correction_and_certificate_packs_preserve_controlling_sources():
    aadhaar = _packs_by_id("aadhaar number showing someone else photo cannot get pension help")
    assert "/sec-31" in aadhaar["aadhaar_2016_identity_record_correction"].anchor_patterns
    assert "/sec-6" in aadhaar["rti_2005_identity_record_request"].anchor_patterns
    assert "nsap_2014_pension_identity_record" in aadhaar

    certificate = _packs_by_id("my caste cert rejected by tehsildar I am SC how to appeal")
    assert "/sec-6" in certificate["rti_2005_certificate_record_request"].anchor_patterns


def test_regional_slur_wage_retaliation_gets_bnss_complaint_pack():
    packs = _packs_by_id("biharee called me by site engineer after wage complaint is this crime")

    assert "bnss_2023_regional_slur_wage_retaliation" in packs
    assert "/sec-173" in packs["bnss_2023_regional_slur_wage_retaliation"].anchor_patterns


def test_forest_produce_dacoity_route_gets_fra_bns_bnss_packs():
    packs = _packs_by_id(
        "urgent gaon people took tendu leaves by force 8 men with lathi forest produce dacoity or theft what to do"
    )

    assert "fra_2006_mfp_dacoity_context" in packs
    assert "bns_2023_dacoity_robbery_mfp" in packs
    assert "bnss_2023_fir_mfp_dacoity" in packs
    assert "/sec-3" in packs["fra_2006_mfp_dacoity_context"].anchor_patterns
    assert "/sec-310" in packs["bns_2023_dacoity_robbery_mfp"].anchor_patterns
    assert "/sec-173" in packs["bnss_2023_fir_mfp_dacoity"].anchor_patterns


def test_domestic_violence_route_gets_pwdva_pack():
    assert "pwdva_2005" in _pack_ids(
        "my husband's mother taunts me daily for not bringing more dowry"
    )


def test_spousal_property_return_uses_neutral_packs_not_pwdva_streedhan_by_default():
    packs = _pack_ids("my wife took my gold and left house")

    assert "family_courts_1984" in packs
    assert "bns_2023" in packs
    assert "pwdva_2005" not in packs
    assert "dowry_prohibition_1961" not in packs
    assert "hindu_succession_1956" not in packs


def test_family_domestic_threat_without_date_preserves_crpc_companion_source():
    packs = _pack_ids("husband locked me out of shared house and threatens me if I come back")

    assert "pwdva_2005" in packs
    assert "bnss_2023_domestic_violence_fir" in packs
    assert "crpc_1973_domestic_violence_fir" in packs


def test_fake_whatsapp_sim_harassment_gets_it_bns_and_telecom_packs():
    packs = {
        pack.id: pack
        for pack in source_packs_for_route(
            route_matter("ex husband created fake whatsapp using my new sim number harassing my family"),
            "ex husband created fake whatsapp using my new sim number harassing my family",
        )
    }

    assert "it_act_2000" in packs
    assert {"/sec-66C", "/sec-66D"} <= set(packs["it_act_2000"].anchor_patterns)
    assert "bns_2023_sim_harassment" in packs
    assert {"/sec-78", "/sec-351", "/sec-319"} <= set(packs["bns_2023_sim_harassment"].anchor_patterns)
    assert "telecommunications_2023" in packs


def test_bumble_unsolicited_sexual_image_gets_bns75_not_rape_pack():
    packs = {
        pack.id: pack
        for pack in source_packs_for_route(
            route_matter("bumble match sent me unsolicited sexual image after i said no what can i do"),
            "bumble match sent me unsolicited sexual image after i said no what can i do",
        )
    }

    assert "it_act_2000" in packs
    assert "bns_2023" in packs
    assert "/sec-75" in packs["bns_2023"].anchor_patterns
    assert "/sec-63" not in packs["bns_2023"].anchor_patterns


def test_therapist_chat_privacy_gets_it72_pack():
    packs = {
        pack.id: pack
        for pack in source_packs_for_route(
            route_matter("someone leaked my chat with therapist on twitter mental health privacy"),
            "someone leaked my chat with therapist on twitter mental health privacy",
        )
    }

    assert "it_act_2000" in packs
    assert {"/sec-72", "/sec-72A"} <= set(packs["it_act_2000"].anchor_patterns)
    assert packs["it_act_2000"].priority >= 1.24
    assert "mental_healthcare_2017" in packs
    assert {"/sec-23", "/sec-24", "/sec-25", "/sec-43"} <= set(packs["mental_healthcare_2017"].anchor_patterns)


def test_criminal_bail_cheque_bounce_gets_ni_act_pack():
    query = "how much surety amount typically required for bail in cheque bounce case"
    route = route_matter(query)
    packs = {
        pack.id: pack
        for pack in source_packs_for_route(route, query)
    }

    assert route.category == "criminal_defence_bail"
    assert "ni_act_1881" in packs
    assert {"/sec-138", "/sec-141", "/sec-142"} <= set(packs["ni_act_1881"].anchor_patterns)


def test_false_nbfc_loan_signature_gets_credit_and_rbi_packs():
    query = "nbfc loan showing on my documents but signature not mine; family says ignore but i am scared, safe legal route?"
    packs = {
        pack.id: pack
        for pack in source_packs_for_route(route_matter(query), query)
    }

    assert "credit_information_companies_2005" in packs
    assert "rbi_integrated_ombudsman_2021" in packs
    assert {"/sec-18", "/sec-19", "/sec-20", "/sec-21", "/sec-22"} <= set(
        packs["credit_information_companies_2005"].anchor_patterns
    )
    assert packs["credit_information_companies_2005"].priority >= 1.4
    assert packs["rbi_integrated_ombudsman_2021"].priority >= 1.3


def test_target_failure_source_packs_retrieve_procedural_and_state_authorities():
    cyber = {
        pack.id: pack
        for pack in source_packs_for_route(
            route_matter("stalker on insta sending dm daily even after blocking how to file complaint"),
            "stalker on insta sending dm daily even after blocking how to file complaint",
        )
    }
    assert "bnss_2023_cyber_harassment_fir" in cyber
    assert {"/sec-173", "/sec-175"} <= set(cyber["bnss_2023_cyber_harassment_fir"].anchor_patterns)
    assert "it_act_2000" in cyber
    assert "/sec-66E" in cyber["it_act_2000"].anchor_patterns

    shop = {
        pack.id: pack
        for pack in source_packs_for_route(
            route_matter("labour inspector said register under shop act in jaipur i have 4 staff"),
            "labour inspector said register under shop act in jaipur i have 4 staff",
        )
    }
    assert "rajasthan_shops_establishments_1958" in shop
    assert "/sec-4" in shop["rajasthan_shops_establishments_1958"].anchor_patterns
    assert "rajasthan_shops_fee_checklist_2026" in shop

    maternity = {
        pack.id: pack
        for pack in source_packs_for_route(
            route_matter("after maternity leave my role was given to someone else"),
            "after maternity leave my role was given to someone else",
        )
    }
    assert "maternity_benefit_1961" in maternity
    assert {"/sec-5", "/sec-12"} <= set(maternity["maternity_benefit_1961"].anchor_patterns)

    gig = {
        pack.id: pack
        for pack in source_packs_for_route(
            route_matter("zomato rider met with accident on bike no insurance from company"),
            "zomato rider met with accident on bike no insurance from company",
        )
    }
    assert "employees_compensation_1923_gig_check" in gig
    assert "motor_vehicles_1988" in gig

    survivor = {
        pack.id: pack
        for pack in source_packs_for_route(
            route_matter("visually impaired sister was raped by caretaker police says case is weak"),
            "visually impaired sister was raped by caretaker police says case is weak",
        )
    }
    assert "bnss_2023_sexual_offence_survivor_procedure" in survivor
    assert {"/sec-173", "/sec-183", "/sec-184"} <= set(
        survivor["bnss_2023_sexual_offence_survivor_procedure"].anchor_patterns
    )

    dowry = {
        pack.id: pack
        for pack in source_packs_for_route(
            route_matter("sister died at in laws house body had marks dowry case where to go"),
            "sister died at in laws house body had marks dowry case where to go",
        )
    }
    assert "bnss_2023_dowry_death_inquest" in dowry
    assert {"/sec-173", "/sec-175", "/sec-194", "/sec-196"} <= set(
        dowry["bnss_2023_dowry_death_inquest"].anchor_patterns
    )

    mtp = {
        pack.id: pack
        for pack in source_packs_for_route(
            route_matter("6 months pregnant after rape doctor says too late for abortion"),
            "6 months pregnant after rape doctor says too late for abortion",
        )
    }
    assert "constitution_article_21_mtp_privacy" in mtp
    assert "/sec-21" in mtp["constitution_article_21_mtp_privacy"].anchor_patterns

    pmla = {
        pack.id: pack
        for pack in source_packs_for_route(
            route_matter("ed pmla raid summons husband can ask anticipatory bail before arrest"),
            "ed pmla raid summons husband can ask anticipatory bail before arrest",
        )
    }
    assert "pmla_2002" in pmla
    assert "constitution_article_21" in pmla

    minor_interfaith = {
        pack.id: pack
        for pack in source_packs_for_route(
            route_matter("daughter is 17 ran away with boy of different religion police saying love jihad"),
            "daughter is 17 ran away with boy of different religion police saying love jihad",
        )
    }
    assert "bnss_2023_minor_interfaith_fir_escalation" in minor_interfaith
    assert {"/sec-173", "/sec-175"} <= set(
        minor_interfaith["bnss_2023_minor_interfaith_fir_escalation"].anchor_patterns
    )
    assert "constitution_article_21" in minor_interfaith

    caste = {
        pack.id: pack
        for pack in source_packs_for_route(
            route_matter("upper caste people beat my husband called us chamar FIR not registering"),
            "upper caste people beat my husband called us chamar FIR not registering",
        )
    }
    assert "scst_poa_1989" in caste
    assert "constitution_article_21" in caste


def test_carceral_safety_precedence_source_packs_are_official_and_specific():
    prison_records = {
        pack.id: pack
        for pack in source_packs_for_route(
            route_matter("family sent money order to jail canteen but prisoner not getting account detail, what record can ask"),
            "family sent money order to jail canteen but prisoner not getting account detail, what record can ask",
        )
    }
    assert "prisons_1894" in prison_records
    assert "/sec-59" in prison_records["prisons_1894"].anchor_patterns
    assert "rti_2005" in prison_records

    custody_medical = {
        pack.id: pack
        for pack in source_packs_for_route(
            route_matter("arthur road jail tb medicine missed for 2 weeks, jail doctor not giving report, what urgent legal step"),
            "arthur road jail tb medicine missed for 2 weeks, jail doctor not giving report, what urgent legal step",
        )
    }
    assert {"constitution_article_21", "bnss_2023_medical_bail", "prisons_1894"} <= set(custody_medical)
    assert {"/sec-13", "/sec-37", "/sec-38"} & set(custody_medical["prisons_1894"].anchor_patterns)

    insulin_medical = {
        pack.id: pack
        for pack in source_packs_for_route(
            route_matter("puzhal prisoner insulin stopped and cannot walk, jail says wait what urgent court step"),
            "puzhal prisoner insulin stopped and cannot walk, jail says wait what urgent court step",
        )
    }
    assert {"bnss_2023_medical_bail", "prisons_1894"} <= set(insulin_medical)

    juvenile = {
        pack.id: pack
        for pack in source_packs_for_route(
            route_matter("minor boy picked by police and kept in station with adults, school id says age 16"),
            "minor boy picked by police and kept in station with adults, school id says age 16",
        )
    }
    assert {"jj_2015", "jj_2015_age_claim_court", "jj_2015_age_documents", "jj_2015_bail_board"} <= set(juvenile)
    assert "pocso_2012" not in juvenile

    undertrial = {
        pack.id: pack
        for pack in source_packs_for_route(
            route_matter("undertrial review committee never considered brother though jail custody is 3 years trial not moving"),
            "undertrial review committee never considered brother though jail custody is 3 years trial not moving",
        )
    }
    assert {"constitution_article_21", "bnss_2023", "crpc_1973", "legal_services_authorities_1987"} <= set(undertrial)
    assert "/sec-479" in undertrial["bnss_2023"].anchor_patterns
    assert {"/sec-436A", "/sec-436-a", "/sec-436a"} & set(undertrial["crpc_1973"].anchor_patterns)

    notice = {
        pack.id: pack
        for pack in source_packs_for_route(
            route_matter("police gave 35(3) notice in new case and asking phone, can they arrest me if i go alone"),
            "police gave 35(3) notice in new case and asking phone, can they arrest me if i go alone",
        )
    }
    assert "bnss_2023" in notice
    assert "/sec-35" in notice["bnss_2023"].anchor_patterns
    assert "crpc_1973" in notice
    assert "/sec-160" in notice["crpc_1973"].anchor_patterns

    hybrid_notice = {
        pack.id: pack
        for pack in source_packs_for_route(
            route_matter("i received 35 notice but police also says bring all chats and don't tell lawyer"),
            "i received 35 notice but police also says bring all chats and don't tell lawyer",
        )
    }
    assert "/sec-35" in hybrid_notice["bnss_2023"].anchor_patterns
    assert "/sec-94" in hybrid_notice["bnss_2023_production_summons"].anchor_patterns
    assert "constitution_article_22" in hybrid_notice

    bail_release = {
        pack.id: pack
        for pack in source_packs_for_route(
            route_matter("high court granted bail but jail e-copy not received and still not releasing"),
            "high court granted bail but jail e-copy not received and still not releasing",
        )
    }
    assert {"constitution_article_21", "bnss_2023_bail_release", "crpc_1973_bail_release"} <= set(bail_release)
    assert "/sec-480" in bail_release["bnss_2023_bail_release"].anchor_patterns
    assert "/sec-439" in bail_release["crpc_1973_bail_release"].anchor_patterns

    arrest = {
        pack.id: pack
        for pack in source_packs_for_route(
            route_matter("husband picked by crime branch, 24 hours passed no production in court, family not informed"),
            "husband picked by crime branch, 24 hours passed no production in court, family not informed",
        )
    }
    assert {"constitution_article_21", "constitution_article_22", "bnss_2023"} <= set(arrest)
    assert {"/sec-57", "/sec-58"} & set(arrest["bnss_2023"].anchor_patterns)


def test_safety_regression_source_packs_cover_real_authority_gaps():
    elderly_fraud_ids = set(_pack_ids(
        "fake call from sbi pension office took 2 lakh from my account 75 yr father"
    ))
    assert {
        "it_act_2000",
        "senior_citizens_2007_cyber_support",
    } <= elderly_fraud_ids

    will_packs = {
        pack.id: pack
        for pack in source_packs_for_route(
            route_matter("father made will in 1998 not registered now after death sons fighting is unregistered will valid"),
            "father made will in 1998 not registered now after death sons fighting is unregistered will valid",
        )
    }
    assert "/sec-63" in will_packs["indian_succession_1925"].anchor_patterns
    assert "/sec-18" in will_packs["registration_1908"].anchor_patterns
    assert will_packs["indian_succession_1925"].priority > 1.1

    ndps_packs = {
        pack.id: pack
        for pack in source_packs_for_route(
            route_matter("brother in NDPS case arrested 110 days no chargesheet default bail possible"),
            "brother in NDPS case arrested 110 days no chargesheet default bail possible",
        )
    }
    assert "/sec-36A" in ndps_packs["ndps_1985"].anchor_patterns


def test_domestic_safety_prompts_pin_pwdva_safety_anchors():
    physical_query = "please help he gets angry and slaps me but says sorry next day my parents say all marriages are like this should I stay"
    physical_packs = {
        pack.id: pack
        for pack in source_packs_for_route(route_matter(physical_query), physical_query)
    }

    assert "pwdva_2005" in physical_packs
    assert {"/sec-3", "/sec-18", "/sec-12"} <= set(physical_packs["pwdva_2005"].anchor_patterns)
    assert "bns_2023" in physical_packs
    assert "bnss_2023_domestic_violence_fir" in physical_packs
    assert {"/sec-173", "/sec-175"} <= set(physical_packs["bnss_2023_domestic_violence_fir"].anchor_patterns)

    residence_query = "sasural waale mujhe ghar se nikal diya raat ko bina kuch diye kya main wapis ja sakti hoon"
    residence_packs = {
        pack.id: pack
        for pack in source_packs_for_route(route_matter(residence_query), residence_query)
    }

    assert "pwdva_2005" in residence_packs
    assert {"/sec-17", "/sec-19", "/sec-12"} <= set(residence_packs["pwdva_2005"].anchor_patterns)

    assault_residence_query = "spouse assaulted me today and keeps saying he will evict me from matrimonial home"
    assault_residence_ids = set(_pack_ids(assault_residence_query))
    assert {"pwdva_2005", "bns_2023", "bnss_2023", "bnss_2023_domestic_violence_fir"} <= assault_residence_ids


def test_wife_as_aggressor_prompts_do_not_pin_pwdva_pack():
    for query in (
        "my wife slapped me what to do",
        "my wife took my salary atm card what to do",
        "my wife threw me out of house what to do",
        "my wife kicked me out at night what to do",
        "my wife threatens me what to do",
        "my wife took my jewellery what to do",
        "my wife sold my house without consent what to do",
        "my wife forced sex without consent what to do",
        "my wife sexually assaulted me what to do",
    ):
        packs = {
            pack.id: pack
            for pack in source_packs_for_route(route_matter(query), query)
        }

        assert "pwdva_2005" not in packs
        assert "bnss_2023" in packs
        assert "bns_2023" in packs


def test_household_drug_and_child_assault_guards_get_criminal_safety_sources():
    drug_ids = set(_pack_ids("I caught my husband with drugs"))
    assert {"ndps_1985_household_drug_safety", "bnss_2023"} <= drug_ids

    for query in (
        "my husband is addicted to drugs how can I get help",
        "my son is taking drugs and needs treatment what can I do",
    ):
        ids = set(_pack_ids(query))
        assert "ndps_1985_drug_treatment_support" in ids
        assert "ndps_1985_household_drug_safety" not in ids

    child_ids = set(_pack_ids("I caught my wife beating my child"))
    assert {"jj_2015_child_safety", "bnss_2023", "bns_2023"} <= child_ids
    assert "pwdva_2005" not in child_ids


def test_wife_civil_property_and_maintenance_queries_get_family_sources_not_criminal_packs():
    for query in (
        "my wife wants share in my house during divorce what to do",
        "my wife is asking maintenance and share in my property what to do",
    ):
        ids = set(_pack_ids(query))

        assert "family_courts_1984" in ids
        assert "hindu_marriage_1955" in ids
        assert "bns_2023" not in ids
        assert "bnss_2023" not in ids
        assert "pwdva_2005" not in ids


def test_general_legal_gets_conservative_fallback_source_packs():
    query = "what legal help can i get for a general documents issue"
    route = route_matter(query)
    assert route.category == "general_legal"

    ids = _pack_ids(query)
    assert "legal_services_authorities_1987" in ids
    assert "cpc_1908" in ids
    assert "limitation_1963" in ids
    assert "crpc_1973" in ids


def test_motor_accident_claims_get_mva_source_pack():
    query = "my bike hit pedestrian he is claiming 8 lakh in mact"
    route = route_matter(query)
    assert route.category == "motor_accident_claims"

    packs = {pack.id: pack for pack in source_packs_for_route(route, query)}
    assert "motor_vehicles_1988" in packs
    assert {"/sec-146", "/sec-147", "/sec-165", "/sec-166"} <= set(
        packs["motor_vehicles_1988"].anchor_patterns
    )


def test_builder_occupancy_certificate_gets_rera_source_pack():
    query = "developer not giving occupancy certificate after taking full money"
    route = route_matter(query)
    assert route.category == "consumer"

    packs = {pack.id: pack for pack in source_packs_for_route(route, query)}
    assert "rera_2016" in packs
    assert {"/sec-18", "/sec-31", "/sec-34", "/sec-71"} <= set(
        packs["rera_2016"].anchor_patterns
    )
    assert "consumer_protection_2019" in packs


def test_common_composite_failures_get_required_source_packs():
    intimate_query = "girl on video call recorded me and demanding money"
    intimate_packs = {
        pack.id: pack
        for pack in source_packs_for_route(route_matter(intimate_query), intimate_query)
    }
    assert "it_act_2000" in intimate_packs
    assert {"/sec-66E", "/sec-67", "/sec-67A"} <= set(
        intimate_packs["it_act_2000"].anchor_patterns
    )
    assert "bns_2023_intimate_image_blackmail" in intimate_packs
    assert intimate_packs["bns_2023_intimate_image_blackmail"].anchor_patterns == ("/sec-308",)

    intimate_threat_query = "morphed nude photo of my sister is being shared in college telegram group"
    intimate_threat_packs = {
        pack.id: pack
        for pack in source_packs_for_route(route_matter(intimate_threat_query), intimate_threat_query)
    }
    assert "bns_2023_intimate_image_blackmail" in intimate_threat_packs
    assert {"/sec-77", "/sec-351", "/sec-356"} <= set(
        intimate_threat_packs["bns_2023_intimate_image_blackmail"].anchor_patterns
    )

    cab_query = "uber cancelled ride but deducted money and not refunding"
    cab_packs = {
        pack.id: pack
        for pack in source_packs_for_route(route_matter(cab_query), cab_query)
    }
    assert route_matter(cab_query).category == "consumer"
    assert "consumer_protection_2019" in cab_packs
    assert "motor_vehicle_aggregator_guidelines_2020_passenger_grievance" in cab_packs
    assert cab_packs["motor_vehicle_aggregator_guidelines_2020_passenger_grievance"].source_types == ("guideline",)

    recovery_query = "nbfc recovery people abusing me on phone and visiting office"
    recovery_packs = {
        pack.id: pack
        for pack in source_packs_for_route(route_matter(recovery_query), recovery_query)
    }
    assert "rbi_integrated_ombudsman_2021" in recovery_packs
    assert "bns_2023_recovery_harassment" in recovery_packs
    assert "/sec-351" in recovery_packs["bns_2023_recovery_harassment"].anchor_patterns

    workplace_recovery_query = "finance company caller says they will tell my office and neighbours about loan"
    workplace_recovery_packs = {
        pack.id: pack
        for pack in source_packs_for_route(route_matter(workplace_recovery_query), workplace_recovery_query)
    }
    assert route_matter(workplace_recovery_query).category == "banking_credit_dispute"
    assert "rbi_integrated_ombudsman_2021" in workplace_recovery_packs
    assert "bns_2023_recovery_harassment" in workplace_recovery_packs

    boss_recovery_query = "loan app people are calling my boss and saying I am fraud"
    boss_recovery_packs = {
        pack.id: pack
        for pack in source_packs_for_route(route_matter(boss_recovery_query), boss_recovery_query)
    }
    assert route_matter(boss_recovery_query).category == "banking_credit_dispute"
    assert "rbi_integrated_ombudsman_2021" in boss_recovery_packs
    assert "dpdp_2023_loan_app_contacts" not in boss_recovery_packs
    assert "it_act_2000" not in boss_recovery_packs
    assert "it_act_2000_loan_app_private_image" not in boss_recovery_packs
    assert "bns_2023_recovery_harassment" in boss_recovery_packs

    private_image_recovery_query = "loan app is blackmailing me with a morphed nude"
    private_image_recovery_packs = {
        pack.id: pack
        for pack in source_packs_for_route(
            route_matter(private_image_recovery_query), private_image_recovery_query
        )
    }
    assert private_image_recovery_packs["it_act_2000_loan_app_private_image"].anchor_patterns == ("/sec-66E",)

    video_blackmail_query = "someone recorded video call and says he will send to my relatives if i dont pay"
    video_blackmail_packs = {
        pack.id: pack
        for pack in source_packs_for_route(route_matter(video_blackmail_query), video_blackmail_query)
    }
    assert route_matter(video_blackmail_query).category == "cyber_fraud_or_harassment"
    assert "it_act_2000" in video_blackmail_packs
    assert {"/sec-66E", "/sec-67", "/sec-67A"} <= set(
        video_blackmail_packs["it_act_2000"].anchor_patterns
    )
    assert "bns_2023_intimate_image_blackmail" in video_blackmail_packs

    bank_lien_query = "bank marked lien on salary account because cyber case but no notice came"
    bank_lien_packs = {
        pack.id: pack
        for pack in source_packs_for_route(route_matter(bank_lien_query), bank_lien_query)
    }
    assert route_matter(bank_lien_query).category == "banking_credit_dispute"
    assert "bnss_2023_bank_account_legal_hold" in bank_lien_packs
    assert "rbi_integrated_ombudsman_2021" in bank_lien_packs

    cyber_routed_lien_query = "cyber police put a lien on my frozen bank account"
    cyber_routed_lien_packs = {
        pack.id: pack
        for pack in source_packs_for_route(
            route_matter(cyber_routed_lien_query),
            cyber_routed_lien_query,
        )
    }
    assert route_matter(cyber_routed_lien_query).category == "cyber_fraud_or_harassment"
    assert "rbi_integrated_ombudsman_2021" in cyber_routed_lien_packs
    assert "bnss_2023_bank_account_legal_hold" in cyber_routed_lien_packs
    assert "it_act_2000_bank_freeze_cyber_hold" in cyber_routed_lien_packs

    order_copy_lien_query = "my salary account has lien after cyber complaint but bank is not giving order copy"
    order_copy_lien_packs = {
        pack.id: pack
        for pack in source_packs_for_route(route_matter(order_copy_lien_query), order_copy_lien_query)
    }
    assert route_matter(order_copy_lien_query).category == "banking_credit_dispute"
    assert "bnss_2023_bank_account_legal_hold" in order_copy_lien_packs
    assert "banking_regulation_1949" in order_copy_lien_packs
    assert "rbi_integrated_ombudsman_2021" in order_copy_lien_packs


def test_stage2_failed_family_source_packs_cover_operational_authorities():
    mgnrega_ids = set(_pack_ids(
        "gram panchayat not giving work under mgnrega after application"
    ))
    assert {"mgnrega_2005", "rti_2005"} <= mgnrega_ids

    false_nbfc_loan_ids = set(_pack_ids(
        "nbfc loan showing on my documents but signature not mine"
    ))
    assert {
        "credit_information_companies_2005",
        "it_act_2000_identity_loan_documents",
        "rbi_integrated_ombudsman_2021",
    } <= false_nbfc_loan_ids

    upi_freeze_ids = set(_pack_ids(
        "my upi account frozen and branch not giving complaint number"
    ))
    assert {
        "rbi_integrated_ombudsman_2021",
        "banking_regulation_1949",
    } <= upi_freeze_ids
    assert "bnss_2023" not in upi_freeze_ids

    recovery_photo_ids = set(_pack_ids(
        "bank recovery agent took photos of my house can i complain"
    ))
    assert {
        "rbi_integrated_ombudsman_2021",
        "bns_2023_recovery_harassment",
    } <= recovery_photo_ids
    assert "it_act_2000" not in recovery_photo_ids
    assert "it_act_2000_loan_app_private_image" not in recovery_photo_ids


def test_stage11_remaining_common_prompts_get_workflow_sources():
    streedhan_query = "husband kept my streedhan locker keys and refusing return"
    streedhan_packs = {
        pack.id: pack
        for pack in source_packs_for_route(route_matter(streedhan_query), streedhan_query)
    }
    assert "pwdva_2005" in streedhan_packs
    assert "bns_2023" in streedhan_packs
    assert "/sec-316" in streedhan_packs["bns_2023"].anchor_patterns

    crypto_query = "crypto exchange froze my wallet and support not replying"
    crypto_packs = {
        pack.id: pack
        for pack in source_packs_for_route(route_matter(crypto_query), crypto_query)
    }
    assert route_matter(crypto_query).category == "digital_platform_account"
    assert "consumer_protection_2019" in crypto_packs
    assert "it_act_2000_platform_wallet" in crypto_packs
    assert "/sec-79" in crypto_packs["it_act_2000_platform_wallet"].anchor_patterns


def test_false_cheating_paraphrases_preserve_criminal_procedure_sources():
    for query in (
        "business partner put false cheating 420 FIR against me for loan money",
        "relative filed fake 420 case because i could not repay money on time",
        "neighbour gave fake cheating complaint after property payment fight",
        "police calling me in cheque money dispute saying 420 complaint is filed",
    ):
        route = route_matter(query)
        packs = {pack.id: pack for pack in source_packs_for_route(route, query)}

        assert route.category == "criminal_defence_bail"
        assert "bnss_2023" in packs
        assert "bns_2023" in packs
        assert "/sec-528" in packs["bnss_2023"].anchor_patterns
        assert "/sec-318" in packs["bns_2023"].anchor_patterns


def test_spouse_household_expense_maintenance_gets_pwdva_and_maintenance_procedure_without_bns_pack():
    query = "my husband stopped paying household expenses after separation I am 38 can I ask maintenance"
    packs = {pack.id: pack for pack in source_packs_for_route(route_matter(query), query)}
    ids = set(packs)

    assert "family_courts_1984" in ids
    assert "hindu_marriage_1955" in ids
    assert "pwdva_2005" in ids
    assert "bnss_2023" in ids
    assert "/sec-144" in packs["bnss_2023"].anchor_patterns
    assert "crpc_1973" in ids
    assert "/sec-125" in packs["crpc_1973"].anchor_patterns
    assert "bns_2023" not in ids


def test_cyber_intimate_threat_gets_it_act_pack():
    assert "it_act_2000" in _pack_ids(
        "bf secretly recorded us during sex now threatening to upload"
    )


def test_stage_e9_repeated_criminal_source_gap_prompts_get_exact_packs():
    intimate = _packs_by_id(
        "pls tell bf secretly recorded us during sex now threatening to upload bro help need lawyer or police"
    )
    assert "bns_2023_intimate_image_blackmail" in intimate
    assert {"/sec-77", "/sec-351", "/sec-356"} <= set(
        intimate["bns_2023_intimate_image_blackmail"].anchor_patterns
    )
    assert "bnss_2023_intimate_image_fir" in intimate
    assert "crpc_1973_intimate_image_fir" in intimate

    child_csam = _packs_by_id(
        "can u tell ai csam of my classmate someone made n shared in college telegram what can i do"
    )
    assert "bnss_2023_child_intimate_image_fir" in child_csam
    assert "crpc_1973_child_intimate_image_fir" in child_csam

    scst_attack = _packs_by_id(
        "urgent mob attacked our pahan during sarna puja calling adivasi non hindu jharkhand how to complain"
    )
    assert "scst_poa_1989" in scst_attack
    assert "bnss_2023_scst_atrocity_fir" in scst_attack
    assert "crpc_1973_scst_atrocity_fir" in scst_attack
    assert "bns_2023_scst_atrocity_threat_hurt" in scst_attack
    assert "/sec-115" in scst_attack["bns_2023_scst_atrocity_threat_hurt"].anchor_patterns
    assert "ipc_1860_scst_atrocity_threat_hurt" in scst_attack

    itpa = _packs_by_id(
        "hi, the spa was raided last week and police took me and other girls to station I just do massage I am scared what will happen now can i file case"
    )
    assert "itpa_1956" in itpa
    assert "bns_2023_itpa_trafficking" in itpa
    assert "/sec-143" in itpa["bns_2023_itpa_trafficking"].anchor_patterns
    assert "bnss_2023_itpa_arrest_bail" in itpa
    assert "crpc_1973_itpa_arrest_bail" in itpa


def test_fake_bank_call_gets_bnss_information_not_generic_bail_pack():
    query = "fake call from sbi pension office took 2 lakh from my account 75 yr father"
    packs = {
        pack.id: pack
        for pack in source_packs_for_route(route_matter(query), query)
    }

    assert "bnss_2023" in packs
    assert packs["bnss_2023"].anchor_patterns == ("/sec-173", "/sec-175")


def test_fake_cbi_parcel_scam_gets_impersonation_and_fir_packs():
    query = "got call from cbi saying parcel has drugs send 5 lakh is this scam"
    packs = {
        pack.id: pack
        for pack in source_packs_for_route(route_matter(query), query)
    }

    assert packs["it_act_2000"].anchor_patterns[:2] == ("/sec-66D", "/sec-66C")
    assert packs["bnss_2023"].anchor_patterns == ("/sec-173", "/sec-175")
    assert "/sec-318" in packs["bns_2023"].anchor_patterns
    assert "/sec-319" in packs["bns_2023"].anchor_patterns


def test_dating_app_blackmail_gets_bnss_fir_pack():
    query = "tinder match is blackmailing with screenshots and asking money"
    packs = {
        pack.id: pack
        for pack in source_packs_for_route(route_matter(query), query)
    }

    assert "it_act_2000" in packs
    assert "bnss_2023_cyber_blackmail_fir" in packs
    assert packs["bnss_2023_cyber_blackmail_fir"].anchor_patterns == ("/sec-173", "/sec-175")


def test_family_court_summons_gets_family_court_and_cpc_packs():
    query = "received family court summons divorce case what next before lawyer"
    packs = {
        pack.id: pack
        for pack in source_packs_for_route(route_matter(query), query)
    }

    assert "family_courts_1984" in packs
    assert "cpc_1908" in packs
    assert "summons" in packs["cpc_1908"].search_query.lower()


def test_messy_family_court_summons_gets_specialist_authority_before_cpc():
    queries = [
        "urgent family court summons received what is the next step before lawyer how to complain",
        "urgent mera family court summon aya hai counselling likha hai kya leke jana hai lawyer nahi hai",
        "summon from family court in divorce matter received today before advocate what first step",
    ]
    for query in queries:
        route = route_matter(query)
        packs = source_packs_for_route(route, query)
        ids = [pack.id for pack in packs]

        assert route.category in {"court_procedure", "family_domestic"}, query
        assert ids[:2] == ["family_courts_1984", "cpc_1908"]
        assert packs[0].priority > packs[1].priority


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


def test_gst_itc_mismatch_gets_cgst_itc_pack():
    query = "gstr 3b mismatch with gstr 2a officer asking reversal 4.8 lakh ITC reply"
    packs = {pack.id: pack for pack in source_packs_for_route(route_matter(query), query)}
    assert "cgst_2017" in packs
    assert "/sec-16" in packs["cgst_2017"].anchor_patterns
    assert "/sec-41" in packs["cgst_2017"].anchor_patterns

    no_acronym_query = "GSTR-2A GSTR-3B mismatch officer asking reversal reply"
    no_acronym_packs = {
        pack.id: pack
        for pack in source_packs_for_route(route_matter(no_acronym_query), no_acronym_query)
    }
    assert "cgst_2017" in no_acronym_packs
    assert "/sec-16" in no_acronym_packs["cgst_2017"].anchor_patterns
    assert "/sec-41" in no_acronym_packs["cgst_2017"].anchor_patterns


def test_non_compete_gets_contract_act_restraint_pack():
    query = "non compete clause in my employment contract for 2 years enforceable"
    ids = _pack_ids(query)
    assert "indian_contract_act_1872_restraint_trade" in ids


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
    assert by_id["constitution_legal_aid"].anchor_patterns == ("/sec-39A", "/sec-21", "/sec-22")
    assert "legal_services_authorities_1987" in by_id


def test_criminal_video_link_court_status_gets_bnss_and_crpc_not_cpc_pack():
    query = "my criminal case was adjourned twice because video link failed but i am already on bail, how to ask next date status"
    route = route_matter(query)
    assert route.category == "court_procedure"
    by_id = {pack.id: pack for pack in source_packs_for_route(route, query)}

    assert "bnss_2023_criminal_court_status" in by_id
    assert "/sec-530" in by_id["bnss_2023_criminal_court_status"].anchor_patterns
    assert "crpc_1973_criminal_court_status" in by_id
    assert "cpc_1908" not in by_id


def test_civil_witness_document_summons_gets_cpc_pack_not_criminal_notice_pack():
    query = "court sent summons for witness evidence in my civil case and asked to bring documents, is this BNSS 35 police notice"
    route = route_matter(query)
    assert route.category == "court_procedure"
    by_id = {pack.id: pack for pack in source_packs_for_route(route, query)}

    assert "cpc_1908_civil_witness_document_summons" in by_id
    assert "bnss_2023_criminal_court_status" not in by_id
    assert "bnss_2023_production_summons" not in by_id


def test_civil_summons_service_failure_gets_order_v_cpc_pack():
    query = "sir summons not served through registered post what is next step where to go"
    route = route_matter(query)
    assert route.category == "court_procedure"
    by_id = {pack.id: pack for pack in source_packs_for_route(route, query)}

    assert "cpc_1908" in by_id
    assert {"/sec-20", "/sec-21", "/sec-28"} <= set(by_id["cpc_1908"].anchor_patterns)
    assert "bnss_2023_production_summons" not in by_id


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
        "fake porn video with my face on website how to remove and complain": {"it_act_2000", "dpdp_2023_deepfake", "bns_2023"},
        "company building dam will submerge 4 tribal villages no consent gram sabha odisha": {"pesa_1996", "rfctlarr_2013"},
        "how is court fee calculated for civil suit valuation 25 lakh recovery": {"court_fees_1870"},
        "drug inspector picked up samples from my medical store schedule h sale without prescription jaipur": {"drugs_cosmetics_1940"},
    }
    for query, expected_ids in expectations.items():
        ids = set(_pack_ids(query))
        assert expected_ids <= ids, query


def test_oracle_failure_cluster_prompts_get_required_source_packs():
    expectations = {
        "pregnant woman undertrial byculla not getting hospital checkup where to go": {"constitution_article_21", "bnss_2023", "bnss_2023_medical_bail", "prisons_1894"},
        "court asked two local sureties we are migrants what to do": {"constitution_article_21", "bnss_2023"},
        "health department not paying covid duty incentive to asha what can i do": {"nhm_asha_incentives_2025"},
        "anganwadi helper honorarium pending how to complain": {"anganwadi_honorarium_case_law"},
        "wife family hid her earlier marriage before wedding remedy": {"hindu_marriage_1955_voidable", "family_courts_1984"},
    }
    for query, expected_ids in expectations.items():
        ids = set(_pack_ids(query))
        assert expected_ids <= ids, query

    asha_ids = set(_pack_ids("health department not paying covid duty incentive to asha what can i do"))
    assert "anganwadi_honorarium_case_law" not in asha_ids
    assert "code_on_wages_2019" not in asha_ids

    anganwadi_ids = set(_pack_ids("anganwadi helper honorarium pending how to complain"))
    assert "nhm_asha_incentives_2025" not in anganwadi_ids
    assert "code_on_wages_2019" not in anganwadi_ids


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

    cab_refund_ids = set(_pack_ids("cab app cancelled ride but money deducted refund not coming"))
    assert "consumer_protection_2019" in cab_refund_ids
    assert "motor_vehicle_aggregator_guidelines_2020_contract" not in cab_refund_ids
    assert "social_security_code_2020" not in cab_refund_ids

    cab_double_charge_ids = set(_pack_ids("cab app charged me twice and refund denied"))
    assert "consumer_protection_2019" in cab_double_charge_ids
    assert "motor_vehicle_aggregator_guidelines_2020_contract" not in cab_double_charge_ids
    assert "code_on_wages_2019" not in cab_double_charge_ids

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


def test_retrenchment_caste_group_gets_lifo_and_equality_not_poa_by_default():
    query = "company retrenched only our caste group without notice what can we do"
    packs = source_packs_for_route(route_matter(query), query)
    ids = {pack.id for pack in packs}
    industrial = next(pack for pack in packs if pack.id == "industrial_disputes_1947")
    assert industrial.anchor_patterns == ("/sec-25F", "/sec-25G", "/sec-25H")
    assert {"industrial_disputes_1947_lifo", "industrial_disputes_1947_reemployment", "constitution_article_14"} <= ids
    assert "scst_poa_1989" not in ids


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


def test_supplier_gst_retrospective_cancellation_itc_gets_section16_and_29_pack():
    query = "supplier gst cancelled retrospectively can i still claim ITC paid him 6 months back"
    packs = source_packs_for_route(route_matter(query), query)
    cgst = next(pack for pack in packs if pack.id == "cgst_2017")
    assert cgst.anchor_patterns == ("/sec-16", "/sec-29")


def test_supplier_registration_itc_without_gst_word_gets_cgst_pack():
    query = "supplier registration cancelled retrospectively can i still claim ITC paid him 6 months back"
    packs = source_packs_for_route(route_matter(query), query)
    cgst = next(pack for pack in packs if pack.id == "cgst_2017")
    assert cgst.anchor_patterns == ("/sec-16", "/sec-29")


def test_non_road_workplace_injury_does_not_get_mact_pollution():
    for query in (
        "my husband lost hand in brick kiln no compensation owner saying he was careless",
        "site mukadam beat me head injury 8 stitches when i asked for old wages mumbai",
        "site mukadam hit me head injury when i asked for old wages mumbai",
    ):
        packs = source_packs_for_route(route_matter(query), query)
        ids = {pack.id for pack in packs}
        assert "motor_vehicles_1988_mact" not in ids
        assert "motor_vehicles_1988" not in ids


def test_manual_scavenging_death_gets_manual_and_compensation_packs():
    query = "septic tank cleaner died no safety equipment company refusing compensation"
    route = route_matter(query)
    assert route.category == "manual_scavenging_safety"
    packs = {pack.id: pack for pack in source_packs_for_route(route, query)}
    ids = set(packs)
    assert "manual_scavenging_2013" in ids
    assert "employees_compensation_1923" in ids
    assert "bnss_2023_manual_scavenging_death_fir" in ids
    assert "crpc_1973_manual_scavenging_death_fir" in ids
    assert "bns_2023_manual_scavenging_death_negligence" in ids
    assert "ipc_1860_manual_scavenging_death_negligence" in ids
    assert "/sec-173" in packs["bnss_2023_manual_scavenging_death_fir"].anchor_patterns
    assert "/sec-154" in packs["crpc_1973_manual_scavenging_death_fir"].anchor_patterns


def test_manual_scavenging_no_safety_without_death_does_not_get_death_packs():
    query = "septic tank cleaner no safety equipment company refusing mask what to do"
    route = route_matter(query)
    assert route.category == "manual_scavenging_safety"
    ids = {pack.id for pack in source_packs_for_route(route, query)}
    assert "manual_scavenging_2013" in ids
    assert "employees_compensation_1923" in ids
    assert "bnss_2023_manual_scavenging_death_fir" not in ids
    assert "crpc_1973_manual_scavenging_death_fir" not in ids
    assert "bns_2023_manual_scavenging_death_negligence" not in ids
    assert "ipc_1860_manual_scavenging_death_negligence" not in ids


def test_manual_scavenging_with_dalit_coercion_gets_poa_pack():
    query = "dry latrine still in our basti panchayat forcing dalit women to clean dindori"
    route = route_matter(query)
    assert route.category == "manual_scavenging_safety"
    packs = {pack.id: pack for pack in source_packs_for_route(route, query)}
    assert "manual_scavenging_2013" in packs
    assert "scst_poa_manual_scavenging" in packs
    assert "/sec-3" in packs["scst_poa_manual_scavenging"].anchor_patterns


def test_child_cross_border_return_gets_article_226_pack():
    query = "my ex husband took our son to UK on tourist visa and is not bringing back he said permanent now"
    route = route_matter(query)
    assert route.category == "child_custody_adoption"
    packs = {pack.id: pack for pack in source_packs_for_route(route, query)}
    assert "guardians_wards_1890" in packs
    assert "constitution_article_226_habeas" in packs
    assert "/sec-226" in packs["constitution_article_226_habeas"].anchor_patterns


def test_traffic_license_no_bribe_does_not_get_corruption_pack():
    query = "my driving license invalid on portal no bribe no challan how fix"
    route = route_matter(query)
    assert route.category == "business_license_compliance"
    ids = {pack.id for pack in source_packs_for_route(route, query)}
    assert "motor_vehicles_1988" in ids
    assert "prevention_corruption_1988" not in ids


def test_second_appeal_gets_limitation_pack():
    query = "urgent second appeal high court substantial question of law procedure how to complain"
    route = route_matter(query)
    assert route.category == "court_procedure"
    packs = {pack.id: pack for pack in source_packs_for_route(route, query)}
    assert "cpc_1908" in packs
    assert "limitation_1963" in packs
    assert "/sec-5" in packs["limitation_1963"].anchor_patterns


def test_school_caste_assault_gets_bnss_complaint_pack():
    query = "girl beaten in school by teacher calling caste name principal not acting maharashtra"
    route = route_matter(query)
    assert route.category == "tribal_caste_atrocity"
    packs = {pack.id: pack for pack in source_packs_for_route(route, query)}
    assert "scst_poa_1989" in packs
    assert "bnss_2023" in packs
    assert {"/sec-173", "/sec-175"} <= set(packs["bnss_2023"].anchor_patterns)
    assert "crpc_1973" in packs
    assert {"/sec-154", "/sec-156", "/sec-200"} <= set(packs["crpc_1973"].anchor_patterns)


def test_child_papers_without_adoption_do_not_get_jj_adoption_pack():
    child_passport_query = "child passport papers are stuck with father for travel"
    child_passport_ids = {pack.id for pack in source_packs_for_route(route_matter(child_passport_query), child_passport_query)}
    assert "jj_2015" not in child_passport_ids

    school_papers_query = "school papers for my son are not released by principal"
    school_papers_ids = {pack.id for pack in source_packs_for_route(route_matter(school_papers_query), school_papers_query)}
    assert "jj_2015" not in school_papers_ids


def test_adopting_child_from_relative_gets_jj_adoption_pack():
    query = "we are adopting child from sister no papers now real parents object custody"
    route = route_matter(query)
    assert route.category == "child_custody_adoption"
    packs = {pack.id: pack for pack in source_packs_for_route(route, query)}
    assert "jj_2015" in packs
    assert "/sec-56" in packs["jj_2015"].anchor_patterns


def test_gig_id_blocked_gets_platform_and_wage_sources():
    query = "Swiggy rider ID blocked full and final pending after customer abused me"
    route = route_matter(query)
    assert route.category == "digital_platform_account"
    ids = [pack.id for pack in source_packs_for_route(route, query)]
    assert "code_on_wages_2019" in ids
    assert "social_security_code_2020" in ids


def test_ola_driving_deactivation_gets_driver_platform_and_wage_sources():
    query = "ola cabs deactivated me after 2 years driving in koramangala no warning"
    route = route_matter(query)
    assert route.label == "Cab aggregator driver deactivation / platform account"
    ids = set(_pack_ids(query))
    assert {
        "motor_vehicle_aggregator_guidelines_2020_contract",
        "motor_vehicle_aggregator_guidelines_2020_grievance",
        "code_on_wages_2019",
        "social_security_code_2020",
    } <= ids


def test_food_delivery_rating_block_gets_conditional_gig_sources():
    query = "swiggy pe customer abused me 1 star spam now my id blocked appeal kaha"
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


def test_mutation_order_passed_does_not_trigger_succession_source_pack():
    query = "mutation order passed by tehsildar but patwari not updating record rajasthan"
    ids = [pack.id for pack in source_packs_for_route(route_matter(query), query)]
    assert "hindu_succession_1956" not in ids
    assert "rti_2005" in ids


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


def test_msme_negation_does_not_force_msmed_pack():
    query = "buyer not paying invoice 9 lakh stuck no msme registration"
    ids = [pack.id for pack in source_packs_for_route(route_matter(query), query)]
    assert "msmed_2006" not in ids
    assert "indian_contract_1872" in ids


def test_actual_drug_parcel_gets_ndps_not_cyber_pack():
    query = "police caught my drug parcel at airport no fake call no money demand what punishment"
    packs = source_packs_for_route(route_matter(query), query)
    ids = [pack.id for pack in packs]
    assert "ndps_1985" in ids
    assert "it_act_2000" not in ids
    by_id = {pack.id: pack for pack in packs}
    assert "/sec-144" not in by_id["bnss_2023"].anchor_patterns
    assert "/sec-125" not in by_id["crpc_1973"].anchor_patterns
    assert {"/sec-173", "/sec-480"} <= set(by_id["bnss_2023"].anchor_patterns)
    assert {"/sec-100", "/sec-102", "/sec-167"} <= set(by_id["crpc_1973"].anchor_patterns)


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


def test_tamil_nadu_coimbatore_shop_license_route_gets_official_local_sources():
    query = "tamil nadu shop license renewal pending 2 years coimbatore shopkeeper penalty kaise calculate"
    route = route_matter(query)
    assert route.category == "business_license_compliance"
    packs = source_packs_for_route(route, query)
    by_id = {pack.id: pack for pack in packs}

    assert {
        "tamil_nadu_shops_establishments_1947",
        "coimbatore_trade_license_2026",
        "rti_2005",
    } <= set(by_id)
    assert by_id["tamil_nadu_shops_establishments_1947"].doc_ids == (
        "tamil-nadu-shops-establishments-1947",
    )
    assert {"/sec-42", "/sec-43", "/sec-45", "/sec-46A"} <= set(
        by_id["tamil_nadu_shops_establishments_1947"].anchor_patterns
    )
    assert by_id["coimbatore_trade_license_2026"].doc_ids == (
        "coimbatore-trade-license-2026",
    )
    assert by_id["coimbatore_trade_license_2026"].anchor_patterns == (
        "/d-and-o-renewal-penalty",
    )
    assert "guideline" in by_id["coimbatore_trade_license_2026"].source_types


def test_tamil_nadu_coimbatore_shop_sources_do_not_pollute_other_states():
    for query in (
        "bangalore shop license renewal pending penalty what to do",
        "delhi trade license renewal pending shopkeeper penalty how to calculate",
        "mumbai shop act renewal delayed penalty how to complain",
        "jaipur shop license renewal pending municipality penalty",
    ):
        ids = set(_pack_ids(query))
        assert "tamil_nadu_shops_establishments_1947" not in ids, query
        assert "coimbatore_trade_license_2026" not in ids, query


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

    typo_query = "police not acting can i file private complain before magistrate"
    typo_route = route_matter(typo_query)
    typo_by_id = {pack.id: pack for pack in source_packs_for_route(typo_route, typo_query)}
    assert typo_route.category == "court_procedure"
    assert "bnss_2023" in typo_by_id
    assert "crpc_1973" in typo_by_id
    assert "/sec-223" in typo_by_id["bnss_2023"].anchor_patterns
    assert "/sec-200" in typo_by_id["crpc_1973"].anchor_patterns


def test_general_mediation_act_query_gets_mediation_and_legal_aid_packs():
    query = "urgent how to initiate mediation under Mediation Act 2023 without going to court how to complain"
    route = route_matter(query)
    assert route.category == "court_procedure"
    packs = source_packs_for_route(route, query)
    by_id = {pack.id: pack for pack in packs}
    assert "mediation_2023" in by_id
    assert "legal_services_authorities_1987" in by_id
    assert "commercial_courts_2015" not in by_id
    assert "cpc_1908" in by_id


def test_completed_suicide_legal_issue_gets_substantive_criminal_packs():
    query = "company harassment made worker commit suicide family wants case"
    route = route_matter(query)
    assert route.category == "criminal_general"
    packs = source_packs_for_route(route, query)
    ids = {pack.id for pack in packs}
    assert "bnss_2023" in ids
    assert "bns_2023" in ids


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
    assert "constitution_article_21" in by_id
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


def test_common_user_smoke_prompts_get_precise_source_packs():
    coowner_query = "brother and i bought a plot together 10 years back, now he has sold it, what can i do"
    coowner_packs = source_packs_for_route(route_matter(coowner_query), coowner_query)
    coowner_by_id = {pack.id: pack for pack in coowner_packs}
    assert coowner_by_id["transfer_property_1882"].anchor_patterns == ("/sec-44", "/sec-45")
    assert "specific_relief_1963" in coowner_by_id
    assert "hindu_succession_1956" not in coowner_by_id

    tenant_query = "My tenant is not vacating house and not paying rent"
    tenant_packs = source_packs_for_route(route_matter(tenant_query), tenant_query)
    tenant_by_id = {pack.id: pack for pack in tenant_packs}
    tenant_tpa = next(pack for pack in tenant_packs if pack.id == "transfer_property_1882")
    assert tenant_tpa.anchor_patterns == ("/sec-106", "/sec-111", "/sec-105", "/sec-108")
    assert "/sec-122" not in tenant_tpa.anchor_patterns
    assert "specific_relief_1963" not in tenant_by_id

    oral_gift_query = "mother gave land to younger son verbally now older son disputing after 20 years"
    oral_gift_by_id = {
        pack.id: pack
        for pack in source_packs_for_route(route_matter(oral_gift_query), oral_gift_query)
    }
    assert "registration_1908" in oral_gift_by_id
    assert {"/sec-17", "/sec-49"} <= set(oral_gift_by_id["registration_1908"].anchor_patterns)
    assert oral_gift_by_id["registration_1908"].priority >= 1.14

    engagement_query = "my fiance lied about salary before marriage but we are not married yet what can i do"
    engagement_ids = _pack_ids(engagement_query)
    assert "hindu_marriage_1955_voidable" not in engagement_ids
    assert "family_courts_1984" not in engagement_ids

    solo_sale_tax_ids = _pack_ids("my brother sold his own plot what tax applies")
    assert "income_tax_1961" in solo_sale_tax_ids
    assert "specific_relief_1963" not in solo_sale_tax_ids

    school_query = "my daughter school admission is denied, despite her clearing admission exam"
    rte = next(pack for pack in source_packs_for_route(route_matter(school_query), school_query) if pack.id == "rte_2009")
    assert "/sec-13" in rte.anchor_patterns
    assert "/sec-12" in rte.anchor_patterns

    college_query = "engineering college is holding my original certificates after I left the course"
    college_by_id = {
        pack.id: pack
        for pack in source_packs_for_route(route_matter(college_query), college_query)
    }
    assert college_by_id["aicte_certificate_return_guideline"].source_types == ("guideline",)
    assert "original-documents" in college_by_id["aicte_certificate_return_guideline"].anchor_patterns
    assert "rti_2005" in college_by_id
    assert "consumer_protection_2019_education_service" in college_by_id

    college_marksheets_query = "polytechnic college is not returning my original marksheets after I discontinued"
    college_marksheets_ids = _pack_ids(college_marksheets_query)
    assert "aicte_certificate_return_guideline" in college_marksheets_ids
    assert "consumer_protection_2019_education_service" in college_marksheets_ids
    assert "rte_2009" not in college_marksheets_ids
    assert "aicte_certificate_return_guideline" not in _pack_ids(
        "law college is not returning my original marksheets after I discontinued"
    )

    employment_doc_ids = _pack_ids(
        "company kept my original degree certificate after I resigned and HR not replying"
    )
    assert "code_on_wages_2019_employment_records_dues" in employment_doc_ids
    assert "industrial_disputes_1947_service_dispute" in employment_doc_ids
    assert "indian_contract_1872_employment_document_return" in employment_doc_ids

    for banking_query in (
        "ATM showed transaction failed but 10000 debited, branch says wait",
        "IMPS status failed but money cut and beneficiary says not received",
        "credit card annual fee charged though card was closed",
        "bank says KYC pending so account is on hold",
        "bank chargeback for failed online order not processed",
        "personal loan EMI bounce charges look too high",
    ):
        assert "rbi_integrated_ombudsman_2021" in _pack_ids(banking_query)

    for consumer_query in (
        "got fake Nike shoes from online seller",
        "service centre refused warranty repair for my laptop",
        "coaching centre promised refund but stopped replying",
    ):
        assert "consumer_protection_2019" in _pack_ids(consumer_query)

    bike_query = "My bike is stolen, police is not filing FIR"
    bike_by_id = {pack.id: pack for pack in source_packs_for_route(route_matter(bike_query), bike_query)}
    assert "/sec-173" in bike_by_id["bnss_2023"].anchor_patterns
    assert "/sec-303" in bike_by_id["bns_2023"].anchor_patterns

    arrest_query = "police has picked my son from my home in the night, i have not got FIR copy"
    arrest_by_id = {pack.id: pack for pack in source_packs_for_route(route_matter(arrest_query), arrest_query)}
    assert arrest_by_id["constitution_article_22"].anchor_patterns == ("/sec-22",)
    assert arrest_by_id["bnss_2023"].anchor_patterns == ("/sec-47", "/sec-48", "/sec-57", "/sec-58", "/sec-173")
    pickup_query = "police took my brother at midnight and not telling station or case; screenshots/witness names and phone numbers are with me"
    pickup_by_id = {pack.id: pack for pack in source_packs_for_route(route_matter(pickup_query), pickup_query)}
    assert pickup_by_id["constitution_article_22"].anchor_patterns == ("/sec-22",)
    assert pickup_by_id["bnss_2023"].anchor_patterns == ("/sec-47", "/sec-48", "/sec-57", "/sec-58", "/sec-173")

    misrep_query = "My husband told lies before marriage about his job and his salary, what to do"
    misrep_ids = {pack.id for pack in source_packs_for_route(route_matter(misrep_query), misrep_query)}
    assert {"hindu_marriage_1955_voidable", "family_courts_1984"} <= misrep_ids
    assert "bnss_2023" not in misrep_ids

    breakdown_query = "My wife is denying sex since many years, what to do"
    breakdown_ids = {pack.id for pack in source_packs_for_route(route_matter(breakdown_query), breakdown_query)}
    assert {"family_courts_1984", "hindu_marriage_1955_divorce"} <= breakdown_ids
    assert "bnss_2023" not in breakdown_ids


def test_scst_poa_delay_gets_special_court_victim_rights_pack():
    query = "SC ST POA case special court pending 5 years what can complainant do"
    route = route_matter(query)
    assert route.category == "tribal_caste_atrocity"
    assert not any("Rule 7" in source for source in route.required_sources)
    poa = next(pack for pack in source_packs_for_route(route, query) if pack.id == "scst_poa_1989")
    assert poa.anchor_patterns == ("/sec-13", "/sec-14", "/sec-15A")
    assert "scst_poa_rules_1995_rule_7" not in {
        pack.id for pack in source_packs_for_route(route, query)
    }


def test_scst_poa_dsp_transfer_gets_rule7_pack():
    query = "can u tell SP not transferring my atrocity case to DSP though POA Act says so vidarbha what can i do"
    route = route_matter(query)
    assert route.category == "tribal_caste_atrocity"
    assert any("Rule 7" in source for source in route.required_sources)
    packs = {pack.id: pack for pack in source_packs_for_route(route, query)}

    assert "scst_poa_rules_1995_rule_7" in packs
    assert "/rule-7" in packs["scst_poa_rules_1995_rule_7"].anchor_patterns
    assert packs["scst_poa_rules_1995_rule_7"].priority > packs["scst_poa_1989"].priority


def test_late_itr_gets_income_tax_234f_pack():
    query = "i forgot to file ITR for AY 2022-23 can i still file it now what is the penalty"
    packs = source_packs_for_route(route_matter(query), query)
    assert "income_tax_1961" in [pack.id for pack in packs]
    assert any("/sec-234F" in pack.anchor_patterns for pack in packs)


def test_gst_penalty_notice_does_not_get_income_tax_234f_pack():
    query = "GSTR-3B late return penalty notice what to do"
    packs = source_packs_for_route(route_matter(query), query)
    by_id = {pack.id: pack for pack in packs}

    assert "cgst_2017" in by_id
    assert "income_tax_1961" not in by_id
    assert by_id["cgst_2017"].anchor_patterns == ("/sec-47", "/sec-73", "/sec-74")


def test_gst_search_seal_gets_cgst_67_83_pack():
    query = "gst officer sealed my godown without notice surat textile trader what to do"
    packs = source_packs_for_route(route_matter(query), query)
    assert "cgst_2017" in [pack.id for pack in packs]
    assert any(pack.anchor_patterns == ("/sec-67", "/sec-83") for pack in packs)


def test_food_sealing_and_supplier_payment_get_records_and_primary_packs():
    hotel_query = "health department sealed my small hotel kitchen without giving inspection report"
    hotel_ids = _pack_ids(hotel_query)
    assert "food_safety_2006" in hotel_ids
    assert "rti_2005" in hotel_ids

    supplier_query = "ICDS nutrition supplier payment pending"
    supplier_ids = _pack_ids(supplier_query)
    assert "indian_contract_1872" in supplier_ids
    assert "rti_2005" in supplier_ids


def test_parsi_succession_gets_indian_succession_pack():
    query = "parsi mother passed away in mumbai how property divided among us three sisters"
    packs = source_packs_for_route(route_matter(query), query)
    assert "indian_succession_1925" in [pack.id for pack in packs]
    assert any("/sec-50" in pack.anchor_patterns and "/sec-54" in pack.anchor_patterns for pack in packs)


def test_testamentary_will_queries_get_succession_and_registration_packs():
    queries = (
        "father has 4 children 2 daughters wants to make will giving more to caretaker daughter valid",
        "father wrote will but only registered one not latest one which is valid",
        "registered my will in sub registrar pune do i need to update it every year",
    )
    for query in queries:
        route = route_matter(query)
        assert route.category == "succession_inheritance", query
        packs = source_packs_for_route(route, query)
        by_id = {pack.id: pack for pack in packs}
        assert "indian_succession_1925" in by_id, query
        assert "registration_1908" in by_id, query
        assert "/sec-63" in by_id["indian_succession_1925"].anchor_patterns
        assert "/sec-18" in by_id["registration_1908"].anchor_patterns


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

    protection_query = f"{query} what protection do I have"
    protection_packs = source_packs_for_route(route_matter(protection_query), protection_query)
    protection_by_id = {pack.id: pack for pack in protection_packs}
    assert {"shariat_1937", "family_courts_1984", "pwdva_2005"} <= set(protection_by_id)
    assert {"/sec-3", "/sec-12", "/sec-18"} <= set(protection_by_id["pwdva_2005"].anchor_patterns)


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

    epfo_ids = _pack_ids("company deducted PF from salary but not depositing in EPFO")
    assert "epf_1952" in epfo_ids
    assert "social_security_code_2020" in epfo_ids


def test_stage3_employment_survival_money_source_packs():
    factory_ids = _pack_ids("factory closed suddenly and salary two months pending")
    assert "industrial_disputes_1947_closure" in factory_ids
    assert "code_on_wages_2019_closure_arrears" in factory_ids

    for query in (
        "unit locked gate salary pending after plant shutdown",
        "mill shut suddenly salary pending without notice",
        "company closed without notice and my salary pending",
    ):
        ids = _pack_ids(query)
        assert "industrial_disputes_1947_closure" in ids
        assert "code_on_wages_2019_closure_arrears" in ids

    for query in (
        "company deducted pf but epfo passbook empty",
        "uan shows no pf deposit but salary slip has deduction",
    ):
        ids = _pack_ids(query)
        assert "epf_1952" in ids

    cab_query = "cab app deactivated my driver account without reason and payment pending"
    cab_route = route_matter(cab_query)
    assert cab_route.category == "digital_platform_account"
    assert cab_route.label == "Cab aggregator driver deactivation / platform account"
    cab_ids = _pack_ids(cab_query)
    assert "motor_vehicle_aggregator_guidelines_2020_contract" in cab_ids
    assert "motor_vehicle_aggregator_guidelines_2020_grievance" in cab_ids
    assert "social_security_code_2020" in cab_ids
    assert "code_on_wages_2019" in cab_ids


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
    assert any(pack.id == "mgnrega_2005" and "/sec-19@" in pack.anchor_patterns for pack in mgnrega)
    assert all("/sec-3" not in pack.anchor_patterns for pack in mgnrega if pack.id == "mgnrega_2005")

    street_fine_ids = set(_pack_ids("fish market vendor cochin license panchayat only kerala municipal saying pay 5000 fine illegal"))
    assert "street_vendors_2014" in street_fine_ids
    assert "prevention_corruption_1988" not in street_fine_ids
    street_fine_packs = source_packs_for_route(
        route_matter("fish market vendor cochin license panchayat only kerala municipal saying pay 5000 fine illegal"),
        "fish market vendor cochin license panchayat only kerala municipal saying pay 5000 fine illegal",
    )
    street_pack = next(pack for pack in street_fine_packs if pack.id == "street_vendors_2014")
    assert "/sec-18" in street_pack.anchor_patterns
    assert "/sec-19" in street_pack.anchor_patterns
    assert "/sec-20" in street_pack.anchor_patterns
    assert "/sec-28" in street_pack.anchor_patterns
    assert "/sec-11" in street_pack.anchor_patterns
    assert "/sec-31" not in street_pack.anchor_patterns
    assert "/sec-39" not in street_pack.anchor_patterns

    street_bribe_ids = set(_pack_ids("vendor zone bhopal allotted me 2018 now hawker inspector saying pay 2000 every month otherwise remove"))
    assert {"street_vendors_2014", "prevention_corruption_1988"} <= street_bribe_ids

    assert "code_on_wages_2019" in _pack_ids("hotel waiter minimum wage paid below state rate what can I do")
    welfare_ids = set(_pack_ids("contractor put fake names in construction welfare board register and took worker benefit money"))
    assert {"bocw_1996", "bocw_cess_1996"} <= welfare_ids
    dead_people_ids = set(_pack_ids("MGNREGA fake muster roll names of dead people how complain"))
    assert {"mgnrega_2005", "rti_2005"} <= dead_people_ids

    challan_vendor_ids = set(_pack_ids("street vendor paid challan fine but inspector asking cash bribe every month"))
    assert {"street_vendors_2014", "prevention_corruption_1988"} <= challan_vendor_ids

    pending_hearing_packs = {
        pack.id: pack
        for pack in source_packs_for_route(
            route_matter("hawker license pending but corporation removed my stall before hearing"),
            "hawker license pending but corporation removed my stall before hearing",
        )
    }
    assert "street_vendors_2014" in pending_hearing_packs
    assert {"/sec-18", "/sec-19", "/sec-20"} <= set(pending_hearing_packs["street_vendors_2014"].anchor_patterns)


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
            "banking_regulation_1949", "consumer_protection_2019", "rbi_integrated_ombudsman_2021",
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

    fd_ids = _pack_ids("private cooperative bank fd of grandfather not honoured nominee facing harassment")
    assert "cooperative_bank_recovery_case_law" not in fd_ids
    assert "sarfaesi_2002" not in fd_ids
    nbfc_recovery_ids = _pack_ids("bajaj finserv recovery agent calling my office for emi dues")
    assert "cooperative_bank_recovery_case_law" not in nbfc_recovery_ids
    assert "sarfaesi_2002" not in nbfc_recovery_ids
    fd_packs = source_packs_for_route(
        route_matter("private cooperative bank fd of grandfather not honoured nominee facing harassment"),
        "private cooperative bank fd of grandfather not honoured nominee facing harassment",
    )
    fd_banking = next(pack for pack in fd_packs if pack.id == "banking_regulation_1949")
    assert "/sec-45ZA" in fd_banking.anchor_patterns


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
        "he stalks me on insta and sends dm daily after blocking": (
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


def test_milestone_b_common_failures_get_required_source_packs():
    cases = {
        "hospital operated wrong leg on my 80 yr old father now hospital says consent": (
            "consumer_protection_2019",
        ),
        "complained about sexual harassment by my manager to HR and now he gave PIP bad rating": (
            "posh_2013",
        ),
        "PITA case only talking on phone with paying clients not meeting anyone take bookings": (
            "itpa_1956", "bnss_2023", "crpc_1973",
        ),
        "HDFC bank wrongly debited forex transaction no response what to do": (
            "rbi_integrated_ombudsman_2021", "consumer_protection_2019",
        ),
        "vit student caught with bhang lassi in mahabaleshwar holi is it ndps": (
            "ndps_1985", "bnss_2023", "crpc_1973",
        ),
        "ration card cancelled due aadhaar mismatch BDO says renew what to do": (
            "national_food_security_2013", "aadhaar_2016",
        ),
    }
    for query, expected_ids in cases.items():
        ids = _pack_ids(query)
        for expected_id in expected_ids:
            assert expected_id in ids, query

    itpa_packs = source_packs_for_route(
        route_matter("PITA case only talking on phone with paying clients not meeting anyone take bookings"),
        "PITA case only talking on phone with paying clients not meeting anyone take bookings",
    )
    itpa = next(pack for pack in itpa_packs if pack.id == "itpa_1956")
    assert {"/sec-4", "/sec-5", "/sec-7", "/sec-8"} <= set(itpa.anchor_patterns)

    posh_packs = source_packs_for_route(
        route_matter("complained about sexual harassment by my manager to HR and now he gave PIP bad rating"),
        "complained about sexual harassment by my manager to HR and now he gave PIP bad rating",
    )
    posh = next(pack for pack in posh_packs if pack.id == "posh_2013")
    assert "/sec-19" in posh.anchor_patterns


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

    pressure_query = "my uncle made my old father sign gift deed under pressure"
    pressure_ids = set(_pack_ids(pressure_query))
    assert {"senior_citizens_2007", "transfer_property_1882", "specific_relief_1963"} <= pressure_ids


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


def test_uapa_prima_facie_bail_routes_to_criminal_defence_and_gets_uapa_pack():
    query = "urgent brother in jail 18 months UAPA bail when prima facie case made out kya hota how to complain"
    route = route_matter(query)
    assert route.category == "criminal_defence_bail"
    assert any("Unlawful Activities" in source for source in route.required_sources)
    packs = source_packs_for_route(route, query)
    ids = [pack.id for pack in packs]
    assert "uapa_1967" in ids
    assert "bnss_2023_uapa_bail_custody" in ids
    assert "crpc_1973_uapa_bail_custody" in ids
    uapa_pack = next(pack for pack in packs if pack.id == "uapa_1967")
    assert "/sec-43d" in uapa_pack.anchor_patterns
    crpc_pack = next(pack for pack in packs if pack.id == "crpc_1973_uapa_bail_custody")
    assert "/sec-439" in crpc_pack.anchor_patterns


def test_regular_bail_query_with_complain_words_gets_crpc_bail_pack():
    query = "urgent my son 19 yrs first time offender 379 theft how to get bail magistrate court how to complain"
    route = route_matter(query)
    packs = source_packs_for_route(route, query)
    by_id = {pack.id: pack for pack in packs}
    assert route.category == "criminal_defence_bail"
    assert route.label == "Bail / criminal defence"
    assert "crpc_1973" in by_id
    assert {"/sec-437", "/sec-439"} <= set(by_id["crpc_1973"].anchor_patterns)
    assert "/sec-154" not in by_id["crpc_1973"].anchor_patterns


def test_temple_entry_caste_access_prioritizes_article17_and_pcr_sources():
    query = "pls tell village headman saying my caste cant enter temple in festival dindori what rights need lawyer or police"
    route = route_matter(query)
    packs = source_packs_for_route(route, query)
    by_id = {pack.id: pack for pack in packs}
    assert route.category == "tribal_caste_atrocity"
    assert route.label == "Untouchability / temple or water access"
    assert "constitution_article_17" in by_id
    assert "protection_civil_rights_1955_religious_access" in by_id
    assert "protection_civil_rights_1955" in by_id
    assert by_id["constitution_article_17"].priority > by_id["bns_2023_religious_insult"].priority
    assert by_id["protection_civil_rights_1955_religious_access"].priority > by_id["bns_2023_religious_insult"].priority


def test_ndps_default_bail_gets_ndps_pack():
    query = "brother in NDPS case arrested 110 days no chargesheet default bail possible"
    route = route_matter(query)
    packs = source_packs_for_route(route, query)
    ids = [pack.id for pack in packs]
    assert "ndps_1985" in ids
    ndps_pack = next(pack for pack in packs if pack.id == "ndps_1985")
    assert "section 36A" in ndps_pack.search_query
    assert {"/sec-35-b", "/sec-35-c", "/sec-35-d"} <= set(ndps_pack.anchor_patterns)


def test_stage_goal_ppirp_gets_rules_and_regulations_source_packs():
    query = "msme pre pack insolvency how to use against my own company 1.4 cr debt avoiding nclt full process"
    packs = {
        pack.id: pack
        for pack in source_packs_for_route(route_matter(query), query)
    }

    assert "ibc_2016" in packs
    assert "ibc_ppirp_rules_2021" in packs
    assert "ibbi_ppirp_regulations_2021" in packs
    assert "/form-1" in packs["ibc_ppirp_rules_2021"].anchor_patterns
    assert "official_summary" in packs["ibc_ppirp_rules_2021"].source_types


@pytest.mark.needs_stack
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


@pytest.mark.needs_stack
def test_stage3_nonverbatim_state_gap_chunks_stay_quarantined():
    async def check() -> None:
        asyncpg = pytest.importorskip("asyncpg")
        settings = Settings()
        try:
            pool = await asyncpg.create_pool(dsn=settings.resolved_database_url_host_side, min_size=1, max_size=1)
        except Exception as exc:
            pytest.fail(f"runtime DB unavailable for Stage 3 state-law source-pack validation: {exc}")
        try:
            async with pool.acquire() as conn:
                rows = await conn.fetch(
                    """
                    SELECT d.doc_id, c.source_type, c.quarantined, c.metadata
                    FROM chunks c
                    JOIN documents d ON d.id = c.document_id
                    WHERE d.doc_id = ANY($1::text[])
                      AND c.metadata->>'text_is_verbatim' = 'false'
                    """,
                    [
                        "maharashtra-state-excise-act-prohibition-1949",
                        "orissa-scheduled-areas-transfer-immovable-property-st-1956",
                        "andhra-pradesh-scheduled-areas-land-transfer-regulation-1959",
                        "jharkhand-prevention-witch-daain-practices-2001",
                    ],
                )
            assert rows
            by_doc: dict[str, list] = {}
            for row in rows:
                by_doc.setdefault(row["doc_id"], []).append(row)
            for doc_id in [
                "maharashtra-state-excise-act-prohibition-1949",
                "orissa-scheduled-areas-transfer-immovable-property-st-1956",
                "andhra-pradesh-scheduled-areas-land-transfer-regulation-1959",
            ]:
                assert doc_id in by_doc
                assert all(row["quarantined"] for row in by_doc[doc_id])
                assert all(row["source_type"] in {"official_summary", "secondary_reference"} for row in by_doc[doc_id])
            jharkhand_rows = by_doc.get("jharkhand-prevention-witch-daain-practices-2001", [])
            assert jharkhand_rows
            assert any(
                row["source_type"] == "official_summary" and not row["quarantined"]
                for row in jharkhand_rows
            )

            cases = [
                (
                    "tehsildar transferred my baba land to bania without my consent agency area andhra",
                    "ap_scheduled_areas_land_transfer_regulation_1959",
                    "andhra-pradesh-scheduled-areas-land-transfer-regulation-1959/sec-3",
                ),
                (
                    "patwari changed mutation record giving my dadaji land to non tribal buyer nuapada odisha",
                    "orissa_scheduled_areas_transfer_1956",
                    "orissa-scheduled-areas-transfer-immovable-property-st-1956/sec-3",
                ),
            ]
            for query, pack_id, expected_anchor in cases:
                route = route_matter(query)
                all_packs = source_packs_for_route(route, query)
                pack = next(pack for pack in all_packs if pack.id == pack_id)
                chunks = await _fetch_source_pack_candidates(
                    pool,
                    query,
                    packs=[pack],
                    limit_per_pack=4,
                )
                assert not any(
                    chunk.anchor == expected_anchor
                    and chunk.metadata.get("text_is_verbatim") is False
                    for chunk in chunks
                )
                all_chunks = await _fetch_source_pack_candidates(
                    pool,
                    query,
                    packs=all_packs,
                    limit_per_pack=4,
                )
                mis_tagged = [
                    chunk for chunk in all_chunks
                    if chunk.metadata.get("_required_source_pack") == pack_id
                    and chunk.anchor != expected_anchor
                ]
                assert not mis_tagged
        finally:
            await pool.close()

    asyncio.run(check())


@pytest.mark.needs_stack
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


@pytest.mark.needs_stack
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


@pytest.mark.needs_stack
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


@pytest.mark.needs_stack
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


def test_default_bail_variants_pin_remand_and_offence_sources():
    no_final_report = "police filed only extension request no final report after 75 days ipc cheating"
    no_final_packs = {
        pack.id: pack
        for pack in source_packs_for_route(route_matter(no_final_report), no_final_report)
    }
    assert no_final_packs["bnss_2023"].anchor_patterns == ("/sec-187",)
    assert "/sec-167" in no_final_packs["crpc_1973"].anchor_patterns
    assert no_final_packs["ipc_1860_cheating"].anchor_patterns == ("/sec-420", "/sec-415")

    bns_318 = "bns 318 remand 72 days no chargesheet should it be 60 or 90"
    bns_packs = {
        pack.id: pack
        for pack in source_packs_for_route(route_matter(bns_318), bns_318)
    }
    assert bns_packs["bnss_2023"].anchor_patterns == ("/sec-187",)
    assert bns_packs["bns_2023"].anchor_patterns == ("/sec-318",)
    assert "/sec-167" in bns_packs["crpc_1973"].anchor_patterns


def test_legacy_criminal_query_does_not_force_new_codes():
    assert "bnss_2023" not in _pack_ids("false ipc 420 case from 2020 can i get bail")


def test_legal_aid_query_gets_legal_services_pack():
    assert "legal_services_authorities_1987" in _pack_ids(
        "free legal aid for woman domestic violence case how to apply in dlsa"
    )


def test_bpl_legal_aid_query_gets_lsa_not_nfsa():
    ids = _pack_ids("urgent bPL card holder eligibility for free legal aid from DLSA SLSA how to complain")
    assert "legal_services_authorities_1987" in ids
    assert "national_food_security_2013" not in ids


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
    ids = [pack.id for pack in packs]
    assert "ni_act_1881" in ids
    assert "bnss_cheque_complaint" in ids
    assert any(pack.anchor_patterns == ("/sec-138", "/sec-141", "/sec-142") for pack in packs)
    assert any("/sec-223" in pack.anchor_patterns for pack in packs)


def test_itpa_receptionist_raid_gets_itpa_and_bnss_anchors():
    query = "spa raided police put ITPA on me but I only worked reception desk what should I do"
    route = route_matter(query)
    packs = source_packs_for_route(route, query)
    by_id = {pack.id: pack for pack in packs}

    assert route.category == "criminal_defence_bail"
    assert by_id["itpa_1956"].anchor_patterns == ("/sec-4", "/sec-5", "/sec-7", "/sec-8")
    assert "bnss_2023" in by_id
    assert "/sec-173" in by_id["bnss_2023"].anchor_patterns
    assert "/sec-483" in by_id["bnss_2023"].anchor_patterns


def test_insurance_claim_gets_consumer_and_ombudsman_packs():
    query = "my hut caught fire by accident and insurance company is not paying claim what to do"
    route = route_matter(query)
    packs = source_packs_for_route(route, query)
    by_id = {pack.id: pack for pack in packs}

    assert route.category == "consumer"
    assert "consumer_protection_2019" in by_id
    assert "insurance_ombudsman_rules_2017" in by_id
    assert "/sec-35" in by_id["consumer_protection_2019"].anchor_patterns


def test_typo_insurer_rejecting_claim_gets_consumer_and_ombudsman_packs():
    ids = set(_pack_ids("INSURERER IS REJECTING MY CLAIM"))
    assert {"consumer_protection_2019", "insurance_ombudsman_rules_2017"} <= ids


def test_lgbtq_identity_arrest_gets_navtej_and_custody_packs():
    ids = set(_pack_ids("police arrested my son for being gay"))
    assert {"navtej_lgbtq_liberty", "constitution_article_21", "constitution_article_22"} <= ids
    assert {"bnss_2023", "crpc_1973"} <= ids


@pytest.mark.parametrize(
    "query,required_pack,forbidden_pack",
    (
        (
            "Cyber police froze my bank account in May 2023",
            "crpc_1973_bank_account_legal_hold",
            "bnss_2023_bank_account_legal_hold",
        ),
        (
            "Cyber police froze my bank account in August 2025",
            "bnss_2023_bank_account_legal_hold",
            "crpc_1973_bank_account_legal_hold",
        ),
    ),
)
def test_bank_legal_hold_source_pack_follows_incident_regime(
    query: str,
    required_pack: str,
    forbidden_pack: str,
):
    packs = {
        pack.id: pack
        for pack in source_packs_for_route(route_matter(query), query)
    }

    assert required_pack in packs
    assert forbidden_pack not in packs
    assert packs["rbi_integrated_ombudsman_2021"].anchor_patterns == (
        "/sec-2", "/sec-3", "/sec-9", "/sec-10",
    )


def test_unknown_date_bank_legal_hold_retrieves_both_procedure_regimes():
    query = "Cyber police froze my bank account"
    packs = {
        pack.id: pack
        for pack in source_packs_for_route(route_matter(query), query)
    }

    assert packs["bnss_2023_bank_account_legal_hold"].anchor_patterns == ("/sec-106",)
    assert packs["crpc_1973_bank_account_legal_hold"].anchor_patterns == ("/sec-102",)


def test_witch_branding_ranchi_uses_jharkhand_state_reference_and_criminal_sources():
    query = "can u tell village ojha branded my mother daayan stripped her in public ranchi area what can i do"
    route = route_matter(query)
    packs = source_packs_for_route(route, query)
    by_id = {pack.id: pack for pack in packs}

    assert route.category == "police_fir"
    assert "jharkhand_witch_daain_2001" in by_id
    assert by_id["jharkhand_witch_daain_2001"].source_types == ("bare_act", "official_guidance")
    assert {"/sec-3", "/sec-4"} <= set(by_id["jharkhand_witch_daain_2001"].anchor_patterns)
    assert "jharkhand_witch_official_source_missing" not in by_id
    assert "assam_witch_hunting_2015" not in by_id
    assert "chhattisgarh_tonahi_2005" not in by_id
    assert "bnss_2023" in by_id
    assert "/sec-173" in by_id["bnss_2023"].anchor_patterns
    assert "bns_2023" in by_id
    assert "/sec-76" in by_id["bns_2023"].anchor_patterns


def test_tribal_witch_branding_gets_poa_and_criminal_sources():
    query = "tribal woman called witch and beaten in gumla police refused FIR"
    route = route_matter(query)
    packs = source_packs_for_route(route, query)
    by_id = {pack.id: pack for pack in packs}

    assert route.category == "tribal_caste_atrocity"
    assert "scst_poa_1989" in by_id
    assert "jharkhand_witch_daain_2001" in by_id
    assert by_id["jharkhand_witch_daain_2001"].source_types == ("bare_act", "official_guidance")
    assert "jharkhand_witch_official_source_missing" not in by_id
    assert "bnss_2023" in by_id
    assert "bns_2023" in by_id
    assert "assam_witch_hunting_2015" not in by_id
    assert "chhattisgarh_tonahi_2005" not in by_id


def test_tribal_religious_and_school_caste_prompts_get_required_authority_packs():
    sarna_ids = set(_pack_ids("mob attacked our pahan during sarna puja calling adivasi non hindu jharkhand"))
    assert {"scst_poa_1989", "bns_2023_religious_insult"} <= sarna_ids

    school_ids = set(_pack_ids("girl beaten in school by teacher calling caste name principal not acting maharashtra"))
    assert {"scst_poa_1989", "rte_2009_school_punishment"} <= school_ids


def test_labour_chowk_police_begging_prompt_gets_detention_and_labour_packs():
    ids = set(_pack_ids("delhi labour chowk police picking us morning saying nautanki begging not work how to stop"))
    assert {"bnss_2023_labour_chowk_detention", "ismw_1979_labour_chowk", "code_on_wages_2019_labour_chowk", "constitution_article_21", "constitution_article_22"} <= ids


def test_wage_theft_false_fir_prompt_gets_wage_and_criminal_packs():
    ids = set(_pack_ids("contractor not paid wages now filed false mobile theft case"))
    assert {"code_on_wages_2019", "bnss_2023_wage_false_fir", "bns_2023_wage_false_theft"} <= ids


def test_digital_arrest_and_cyber_notice_get_bnss_workflow_packs():
    digital_packs = {
        pack.id: pack
        for pack in source_packs_for_route(
            route_matter("digital arrest people made me transfer 5 lakh on video call"),
            "digital arrest people made me transfer 5 lakh on video call",
        )
    }
    assert {"it_act_2000", "bns_2023_digital_arrest_impersonation", "bnss_2023_digital_arrest"} <= set(digital_packs)
    assert "/sec-173" in digital_packs["bnss_2023_digital_arrest"].anchor_patterns

    notice_packs = {
        pack.id: pack
        for pack in source_packs_for_route(
            route_matter("police calling me for notice in cyber case but not giving paper"),
            "police calling me for notice in cyber case but not giving paper",
        )
    }
    assert "bnss_2023_cyber_notice" in notice_packs
    assert {"/sec-35", "/sec-173", "/sec-175"} <= set(notice_packs["bnss_2023_cyber_notice"].anchor_patterns)


def test_stage5_money_cyber_identity_source_packs_cover_exact_variants():
    fake_cbi_packs = {
        pack.id: pack
        for pack in source_packs_for_route(
            route_matter("courier says parcel has drugs fake cbi made me pay money what to do"),
            "courier says parcel has drugs fake cbi made me pay money what to do",
        )
    }
    assert {"it_act_2000", "bns_2023_digital_arrest_impersonation", "bnss_2023_digital_arrest"} <= set(fake_cbi_packs)

    loan_app_packs = {
        pack.id: pack
        for pack in source_packs_for_route(
            route_matter("loan app threatening to make morphed nude photo if I dont pay today"),
            "loan app threatening to make morphed nude photo if I dont pay today",
        )
    }
    assert {
        "rbi_integrated_ombudsman_2021_loan_app_cyber",
        "it_act_2000",
        "bns_2023_intimate_image_blackmail",
    } <= set(loan_app_packs)

    upi_packs = {
        pack.id: pack
        for pack in source_packs_for_route(
            route_matter("UPI failed but amount debited bank and app blaming each other what to do"),
            "UPI failed but amount debited bank and app blaming each other what to do",
        )
    }
    assert "rbi_integrated_ombudsman_2021" in upi_packs
    assert "consumer_protection_2019" in upi_packs

    maintenance_charge_packs = {
        pack.id: pack
        for pack in source_packs_for_route(
            route_matter("bank deducted maintenance charge twice and branch is not giving complaint number"),
            "bank deducted maintenance charge twice and branch is not giving complaint number",
        )
    }
    assert "rbi_integrated_ombudsman_2021" in maintenance_charge_packs
    assert "consumer_protection_2019" in maintenance_charge_packs

    merchant_upi_packs = {
        pack.id: pack
        for pack in source_packs_for_route(
            route_matter("Amazon refund failed, UPI shows success but seller says payment not received"),
            "Amazon refund failed, UPI shows success but seller says payment not received",
        )
    }
    assert "rbi_integrated_ombudsman_2021_payment_refund" in merchant_upi_packs
    assert "consumer_protection_2019" in merchant_upi_packs

    legal_hold_packs = {
        pack.id: pack
        for pack in source_packs_for_route(
            route_matter("ED freeze marked on my current account, bank only says legal hold"),
            "ED freeze marked on my current account, bank only says legal hold",
        )
    }
    assert "rbi_integrated_ombudsman_2021" in legal_hold_packs
    assert "bnss_2023_bank_account_legal_hold" in legal_hold_packs

    political_packs = {
        pack.id: pack
        for pack in source_packs_for_route(
            route_matter("deepfake of modi pm circulating my friend made it bjp it cell threatening"),
            "deepfake of modi pm circulating my friend made it bjp it cell threatening",
        )
    }
    assert {"it_act_2000_political_deepfake_personation", "bns_2023_public_political_deepfake", "rpa_1951"} <= set(political_packs)
    assert political_packs["rpa_1951"].priority >= 1.2

    political_notice_packs = {
        pack.id: pack
        for pack in source_packs_for_route(
            route_matter("police notice for political meme/deepfake of MLA on whatsapp"),
            "police notice for political meme/deepfake of MLA on whatsapp",
        )
    }
    assert {
        "it_act_2000_political_deepfake_personation",
        "bns_2023_public_political_deepfake",
    } <= set(political_notice_packs)


def test_bank_freeze_cyber_complaint_gets_legal_hold_pack():
    packs = {
        pack.id: pack
        for pack in source_packs_for_route(
            route_matter("salary account blocked by lien after cyber complaint i dont know the case"),
            "salary account blocked by lien after cyber complaint i dont know the case",
        )
    }

    assert "bnss_2023_bank_account_legal_hold" in packs
    assert "/sec-106" in packs["bnss_2023_bank_account_legal_hold"].anchor_patterns
    assert "rbi_integrated_ombudsman_2021" in packs


def test_shops_register_and_prohibition_variants_get_route_packs():
    pune_ids = _pack_ids("pune cafe got notice for not keeping employee register under shops act what remedy")
    assert "maharashtra_shops_establishments_2017" in pune_ids

    bangalore_ids = _pack_ids("bangalore store labour officer demanding maharashtra shops register is that right")
    assert "maharashtra_shops_establishments_2017" not in bangalore_ids
    assert "rti_2005" in bangalore_ids

    patna_ids = _pack_ids("patna thana says section 37 bihar prohibition on me for liquor what can I do")
    assert "bihar_prohibition_excise_2016" in patna_ids
    assert "bnss_2023" in patna_ids

    noida_ids = _pack_ids("police caught me with alcohol in noida but source showing bihar law what applies")
    assert "bihar_prohibition_excise_2016" not in noida_ids
    assert "bnss_2023" in noida_ids


def test_gst_registration_threshold_pack_uses_registration_sections():
    query = "freelance designer 18 lakh income should i register gst or no"
    packs = {
        pack.id: pack
        for pack in source_packs_for_route(route_matter(query), query)
    }

    assert "cgst_2017" in packs
    assert {"/sec-22", "/sec-24"} <= set(packs["cgst_2017"].anchor_patterns)


def test_passport_route_gets_passports_act_pack():
    query = "passport police verification adverse report because old criminal case what remedy"
    route = route_matter(query)
    assert route.category == "passport_police_verification"
    packs = {pack.id: pack for pack in source_packs_for_route(route, query)}
    assert "passports_1967" in packs
    assert packs["passports_1967"].doc_ids == ("passports-1967",)
    assert "/sec-5" in packs["passports_1967"].anchor_patterns
    assert "official_summary" in packs["passports_1967"].source_types

    bribe_query = "police not clearing passport verification asking money"
    bribe_ids = {pack.id for pack in source_packs_for_route(route_matter(bribe_query), bribe_query)}
    assert {"passports_1967", "prevention_corruption_1988_passport_bribe"} <= bribe_ids


def test_caste_public_service_denial_gets_article17_and_pcr_packs():
    query = "shop owner denied service saying my caste and police laughing"
    route = route_matter(query)
    packs = {pack.id: pack for pack in source_packs_for_route(route, query)}
    ids = set(packs)
    assert "constitution_article_17" in ids
    assert "protection_civil_rights_1955" in ids
    assert "bnss_2023" in ids
    assert "/sec-173" in packs["bnss_2023"].anchor_patterns


def test_forest_and_pesa_queries_get_tribal_source_packs():
    forest_ids = _pack_ids(
        "forest officer stopped us collecting tendu leaves in community forest"
    )
    assert "fra_2006" in forest_ids
    assert "scst_poa_1989" not in forest_ids
    ids = _pack_ids("mining company started blasting without gram sabha consent in scheduled area")
    assert "pesa_1996" in ids

    tribal_mining_ids = set(_pack_ids("tribal village land taken for mining without consent gram sabha"))
    assert {"fra_2006_cfr", "pesa_1996", "rfctlarr_2013_scheduled_area_rr"} <= tribal_mining_ids


def test_fra_bamboo_patta_gets_forest_rights_pack():
    ids = _pack_ids("patta given under FRA but forest guards still cutting our bamboo saying it is reserved bastar")
    assert "fra_2006" in ids


def test_reserved_forest_long_occupation_gets_fra_source_pack():
    ids = _pack_ids("sir forest department saying our land is reserve we have been farming since grandfather time where to go")
    assert "fra_2006" in ids
    assert "scst_poa_1989" not in ids


def test_cfr_mining_gets_fra_mmdr_and_forest_conservation_packs():
    ids = set(_pack_ids("gram sabha got community forest rights but mining company started digging inside forest can we stop it"))
    assert {"fra_2006_cfr", "mmdr_1957", "forest_conservation_1980"} <= ids


def test_recent_forest_encroachment_notice_gets_fca_not_fra_pack():
    ids = set(_pack_ids("forest guard says I recently encroached forest land last month and gave notice what forum should I approach"))
    assert "forest_conservation_1980" in ids
    assert "fra_2006_cfr" not in ids


def test_fra_claim_rejection_gets_fra_not_poa_by_default():
    ids = _pack_ids("i am adivasi woman my IFR claim form rejected because no signature of husband bastar what can i do")
    assert "fra_2006" in ids
    assert "fra_2006_arrangement_procedure" in ids
    assert "scst_poa_1989" not in ids


def test_tribal_mutation_land_transfer_gets_scheduled_area_sources():
    ids = _pack_ids("can u tell patwari changed mutation record giving my dadaji land to non tribal buyer nuapada odisha what can i do")
    assert "constitution_scheduled_areas" in ids
    assert "odisha_scheduled_area_framework_sc" in ids


def test_palli_sabha_coal_block_gets_pesa_larr_mining_sources():
    query = "land acquired for coal block without consulting palli sabha angul odisha what can i do"
    ids = _pack_ids(query)
    assert {"rfctlarr_2013", "pesa_1996", "mmdr_1957"} <= set(ids)
    packs = source_packs_for_route(route_matter(query), query)
    pesa = next(pack for pack in packs if pack.id == "pesa_1996")
    assert "/sec-4-b" in pesa.anchor_patterns
    assert "/sec-4-c" not in pesa.anchor_patterns
    larr = next(pack for pack in packs if pack.id == "rfctlarr_2013_scheduled_area_rr")
    assert "/sec-41" in larr.anchor_patterns


@pytest.mark.parametrize("query", [
    "sand mining lease given without gram sabha consent in scheduled area",
    "stone quarry lease without palli sabha recommendation scheduled area",
])
def test_minor_mineral_pesa_queries_prefer_section_4c_not_land_acquisition(query):
    packs = source_packs_for_route(route_matter(query), query)
    pesa = next(pack for pack in packs if pack.id == "pesa_1996")
    assert "/sec-4-c" in pesa.anchor_patterns
    assert "/sec-4-b" not in pesa.anchor_patterns


def test_silicosis_quarry_gets_occupational_disease_source_packs():
    ids = set(_pack_ids(
        "rajasthan stone quarry silicosis lungs gone cough compensation what to do"
    ))
    assert "employees_compensation_1923_occupational_disease" in ids
    assert "factories_1948_silicosis_safety" in ids


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

    customs_no_gst = source_packs_for_route(
        route_matter("customs show cause notice section 74 drawback rejection no GST issue"),
        "customs show cause notice section 74 drawback rejection no GST issue",
    )
    customs_no_gst_ids = [pack.id for pack in customs_no_gst]
    assert "customs_1962" in customs_no_gst_ids
    assert "cgst_2017" not in customs_no_gst_ids

    tcs_no_gst = source_packs_for_route(
        route_matter("TCS deducted on foreign remittance for education abroad no GST issue how claim refund"),
        "TCS deducted on foreign remittance for education abroad no GST issue how claim refund",
    )
    tcs_no_gst_ids = [pack.id for pack in tcs_no_gst]
    assert "income_tax_1961" in tcs_no_gst_ids
    assert "cgst_2017" not in tcs_no_gst_ids

    income_tax_no_gst = source_packs_for_route(
        route_matter("income tax show cause notice section 148 no GST issue what to do"),
        "income tax show cause notice section 148 no GST issue what to do",
    )
    income_tax_no_gst_ids = [pack.id for pack in income_tax_no_gst]
    assert "income_tax_1961" in income_tax_no_gst_ids
    assert "cgst_2017" not in income_tax_no_gst_ids
    income_tax_no_gst_by_id = {pack.id: pack for pack in income_tax_no_gst}
    assert {"/sec-147", "/sec-148"} <= set(income_tax_no_gst_by_id["income_tax_1961"].anchor_patterns)

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
    assert "special_marriage_1954" in ids
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


def test_consumer_subscription_refund_pack_includes_refund_order_anchor():
    packs = source_packs_for_route(
        route_matter("match group froze my hinge premium 6 months paid no refund customer care"),
        "match group froze my hinge premium 6 months paid no refund customer care",
    )

    assert any(
        pack.id == "consumer_protection_2019" and "/sec-39" in pack.anchor_patterns
        for pack in packs
    )


def test_gst_rule_86b_pack_wins_over_generic_itc_mismatch():
    packs = source_packs_for_route(
        route_matter("rule 86B GSTR-3B ITC one percent cash payment restriction"),
        "rule 86B GSTR-3B ITC one percent cash payment restriction",
    )
    by_id = {pack.id: pack for pack in packs}

    assert "cgst_rules_2017" in by_id
    assert by_id["cgst_2017"].anchor_patterns == ("/sec-49", "/sec-49A", "/sec-49B")


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


def test_stage_e7_family_source_packs_cover_common_user_failures():
    adultery = _packs_by_id("i caught my husband with another woman having sex")
    assert "family_courts_1984" in adultery
    assert "hindu_marriage_1955_divorce" in adultery
    assert "/sec-13" in adultery["hindu_marriage_1955_divorce"].anchor_patterns

    hidden_orientation = _packs_by_id("my husband is gay and hidden before marriage what can i do")
    assert "family_courts_1984" in hidden_orientation
    assert "hindu_marriage_1955_voidable" in hidden_orientation
    assert "/sec-12" in hidden_orientation["hindu_marriage_1955_voidable"].anchor_patterns

    residence = _packs_by_id("husband throws me out but house in mother in law name")
    assert "pwdva_2005" in residence
    assert {"/sec-17", "/sec-19"} <= set(residence["pwdva_2005"].anchor_patterns)

    forced_sex = _packs_by_id("husband forced sex even when i say no")
    assert "pwdva_2005" in forced_sex
    assert {"/sec-3", "/sec-18", "/sec-12"} <= set(forced_sex["pwdva_2005"].anchor_patterns)
    assert "bns_2023" in forced_sex
    assert {"/sec-63", "/sec-67"} & set(forced_sex["bns_2023"].anchor_patterns)


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


@pytest.mark.needs_stack
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
        "panchayat secretary not giving me birth certificate of my child born at home": {"births_deaths_registration_1969", "rti_2005"},
    }
    for query, required_ids in expected.items():
        assert required_ids <= set(_pack_ids(query)), query
    assert "delhi_prison_rules_2018_parole_furlough" not in _pack_ids(
        "65 yrs heart patient husband in jail furlough application uttar pradesh how to file"
    )


def test_civil_registration_and_ration_source_packs_have_stage_iic1_anchors():
    birth_packs = {
        pack.id: pack
        for pack in source_packs_for_route(
            route_matter("panchayat secretary not giving me birth certificate of my child born at home"),
            "panchayat secretary not giving me birth certificate of my child born at home",
        )
    }
    assert {"births_deaths_registration_1969", "rti_2005"} <= set(birth_packs)
    assert {"/sec-7", "/sec-8", "/sec-12", "/sec-13", "/sec-15"} <= set(
        birth_packs["births_deaths_registration_1969"].anchor_patterns
    )

    ration_packs = {
        pack.id: pack
        for pack in source_packs_for_route(
            route_matter("bpl ration card cancelled by panchayat in bihar without notice"),
            "bpl ration card cancelled by panchayat in bihar without notice",
        )
    }
    assert {"national_food_security_2013", "rti_2005"} <= set(ration_packs)
    assert {"/sec-14", "/sec-15", "/sec-24"} <= set(
        ration_packs["national_food_security_2013"].anchor_patterns
    )


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
        "upper caste people beat my husband called us by caste name FIR not registered": {"scst_poa_1989", "bnss_2023", "constitution_article_21"},
        "school principal not giving SC scholarship saying papers wrong since 2 years vidarbha": {"constitution_article_46", "rti_2005"},
        "fake call from sbi pension office took 2 lakh from my account 75 yr father": {"it_act_2000", "bns_2023", "bnss_2023"},
        "code on wages applicable to me minimum wage notification gujarat for unskilled worker": {"code_on_wages_2019"},
        "construction site delhi 14 hour work no overtime contractor laughing when i ask": {"code_on_wages_2019"},
        "husband forces me at night even when I say no I am tired or unwell is there any law for this in india now": {"pwdva_2005", "bns_2023", "bnss_2023"},
        "i complained against my manager for harassment to HR and now they are putting me on PIP, is this retaliation": {"industrial_disputes_1947", "code_on_wages_2019", "posh_2013"},
        "fanvue payment frozen 2400 usd indian creator how to release fund": {"fema_1999", "income_tax_1961", "indian_contract_1872"},
        "in-laws not giving back my jewellery streedhan after husband died": {"dowry_prohibition_1961", "hindu_succession_1956", "pwdva_2005"},
    }
    for query, required_ids in expected.items():
        assert required_ids <= set(_pack_ids(query)), query


def test_generic_hr_pip_retaliation_pack_keeps_conditional_posh_and_not_gig():
    query = "i complained against my manager for harassment to HR and now they are putting me on PIP, is this retaliation"
    route = route_matter(query)
    packs = source_packs_for_route(route, query)
    ids = {pack.id for pack in packs}
    assert route.category == "employment_wages"
    assert "posh_2013" in ids
    assert "industrial_disputes_1947" in ids
    assert "social_security_code_2020_gig_platform" not in ids


def test_explicit_posh_pip_retaliation_pack_keeps_posh_source():
    query = "i complained to ICC about sexual harassment and now manager put me on PIP"
    route = route_matter(query)
    packs = source_packs_for_route(route, query)
    ids = {pack.id for pack in packs}
    assert route.category == "workplace_sexual_harassment"
    assert "posh_2013" in ids


def test_ordinary_pip_pack_gets_id_and_wage_boundary_not_posh():
    query = "my company put me on performance improvement plan for missing targets no harassment issue what are my rights"
    ids = {pack.id for pack in source_packs_for_route(route_matter(query), query)}
    assert {"industrial_disputes_1947", "code_on_wages_2019"} <= ids
    assert "posh_2013" not in ids


def test_ration_aadhaar_cancellation_gets_nfsa_aadhaar_dpdp_sources():
    query = "can u tell ration card cancelled because aadhaar mismatch BDO not agreeing renew bastar what can i do"
    ids = {pack.id for pack in source_packs_for_route(route_matter(query), query)}
    assert route_matter(query).category == "social_welfare_identity"
    assert "national_food_security_2013" in ids
    assert "aadhaar_2016_ration_authentication" in ids
    assert "dpdp_2023_ration_aadhaar_mismatch" in ids


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


def test_adult_age_record_correction_does_not_inject_jj_source_packs():
    ids = set(_pack_ids(
        "police picked my 20 year old brother but FIR says minor because old school certificate wrong, how to correct age and bail"
    ))

    assert "bnss_2023" in ids
    assert "jj_2015" not in ids
    assert "jj_2015_age_claim_court" not in ids
    assert "pocso_2012" not in ids


def test_diabetic_prisoner_medical_pack_includes_article21():
    ids = set(_pack_ids(
        "diabetic prisoner insulin stopped after transfer, family needs urgent hospital direction"
    ))

    assert "constitution_article_21" in ids
    assert "prisons_1894" in ids
    assert "bnss_2023_medical_bail" in ids


def test_cattle_transport_accused_gets_judgment_context_without_hiding_state_gap():
    query = "sir they arrested me for cow transport saying I am smuggling but I was taking my own buffalo to mandi"
    route = route_matter(query)
    packs = source_packs_for_route(route, query)
    ids = {pack.id for pack in packs}
    cattle_pack = next(pack for pack in packs if pack.id == "cattle_animal_transport_judgment_context")

    assert route.label == "State cattle / animal-transport accused procedure"
    assert "cattle_animal_transport_judgment_context" in ids
    assert "prevention_cruelty_animals_1960_transport" in ids
    assert "transport_animals_rules_1978_cattle" in ids
    assert cattle_pack.source_types == ("sc_judgment",)
    assert "bnss_2023" in ids
    assert "crpc_1973" in ids


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
    for query in (
        "they say i am tonhi after child died in village false case filed chhattisgarh",
        "they say i am tonhi after child died in village false case filed chattisgarh",
    ):
        ids = set(_pack_ids(query))
        assert "pocso_2012" not in ids
        assert "jj_2015" not in ids
        assert {"bnss_2023", "bns_2023", "chhattisgarh_tonahi_2005"} <= ids

    for query in (
        "durgapur people say i am tonhi after child died false case what can i do",
        "bastar art page called my painting witch craft and copied it",
    ):
        ids = set(_pack_ids(query))
        assert "chhattisgarh_tonahi_2005" not in ids

    durg_ids = set(_pack_ids("durg district villagers say i am tonhi after child died false case what can i do"))
    assert "chhattisgarh_tonahi_2005" in durg_ids


def test_stage6_failure_prompts_get_required_source_packs():
    expected = {
        "food safety officer collected sample from my kirana said adulteration delhi azadpur": {"food_safety_2006"},
        "contractor said go back home pandemic no return ticket money given 9 of us walked from delhi": {"ismw_1979", "code_on_wages_2019"},
        "how to file habeas corpus petition husband detained illegally by police": {"constitution_article_21", "constitution_article_226_habeas", "bnss_2023"},
        "he gets angry and slaps me but says sorry next day my parents say all marriages are like this should I stay": {"pwdva_2005", "bns_2023"},
        "patwari asking 5000 rupees to enter my name in revenue records can I complain": {"prevention_corruption_1988", "rti_2005"},
        "pattadar passbook lost in flood tehsildar saying come next month": {"ap_rights_land_pattadar_passbooks_1971", "rti_2005"},
        "sir my husband died in army no service pension widow what papers needed where to go": {"army_pension_regulations_2008_part_i", "army_pension_regulations_2008_part_ii", "rti_2005"},
        "what to do lost aadhaar in morbi tile factory raid how to get new one no original village papers gone": {"aadhaar_2016", "rti_2005"},
        "sir I am ASHA worker not paid honorarium 6 months who can help where to go": {"nhm_asha_incentives_2025", "rti_2005", "legal_services_authorities_1987"},
        "my company forced me to resign n now they are not giving me full n final settlement": {"code_on_wages_2019", "industrial_disputes_1947"},
        "software vendor sent notice saying we are using unlicensed copies 22 cad seats noida": {"copyright_1957", "copyright_1957_remedies"},
        "land acquired for coal block without consulting palli sabha angul odisha": {"rfctlarr_2013", "pesa_1996"},
        "16 yr daughter arrested theft put in observation home or jail how to verify age": {"jj_2015", "bnss_2023"},
    }
    for query, required_ids in expected.items():
        assert required_ids <= set(_pack_ids(query)), query


def test_custody_status_neighbors_get_owned_source_packs():
    hidden_packs = {
        pack.id: pack
        for pack in source_packs_for_route(
            route_matter("police took my brother last night not showing station and not allowing lawyer what urgent remedy"),
            "police took my brother last night not showing station and not allowing lawyer what urgent remedy",
        )
    }
    assert {"constitution_article_21", "constitution_article_226_habeas", "bnss_2023"} <= set(hidden_packs)
    assert {"/sec-47", "/sec-48", "/sec-57", "/sec-58"} & set(hidden_packs["bnss_2023"].anchor_patterns)

    missing_packs = {
        pack.id: pack
        for pack in source_packs_for_route(
            route_matter("my adult brother missing since yesterday phone off but no proof police picked him what complaint should i file"),
            "my adult brother missing since yesterday phone off but no proof police picked him what complaint should i file",
        )
    }
    assert "bnss_2023" in missing_packs
    assert {"/sec-173", "/sec-175"} <= set(missing_packs["bnss_2023"].anchor_patterns)
    assert "it_act_2000" not in missing_packs

    notice_packs = {
        pack.id: pack
        for pack in source_packs_for_route(
            route_matter("police sent notice to come station for questioning tomorrow but not arrested should i go with lawyer"),
            "police sent notice to come station for questioning tomorrow but not arrested should i go with lawyer",
        )
    }
    assert "bnss_2023" in notice_packs
    assert {"/sec-35", "/sec-173", "/sec-175"} <= set(notice_packs["bnss_2023"].anchor_patterns)
    assert "crpc_1973" in notice_packs
    assert notice_packs["crpc_1973"].anchor_patterns == ("/sec-160",)

    lawyer_packs = {
        pack.id: pack
        for pack in source_packs_for_route(
            route_matter("jail superintendent not allowing lawyer meeting for my brother first time arrest what legal aid route"),
            "jail superintendent not allowing lawyer meeting for my brother first time arrest what legal aid route",
        )
    }
    assert {"legal_services_authorities_1987", "constitution_legal_aid", "bnss_2023"} <= set(lawyer_packs)
    assert {"/sec-47", "/sec-57", "/sec-58"} <= set(lawyer_packs["bnss_2023"].anchor_patterns)


def test_stage7_gate_source_gaps_get_official_source_packs():
    expected = {
        "brother UAPA arrested 3 months chargesheet not filed total custody can be extended 180 days": {"uapa_1967", "bnss_2023"},
        "tihar jail mulaqat only 30 min once a week is this legal can we ask more": {"delhi_prison_rules_2018_mulaqat_books", "prisons_1894", "constitution_article_21"},
        "son in tihar can he get books from family during prison rules": {"delhi_prison_rules_2018_mulaqat_books", "prisons_1894"},
        "brother in rohini jail wants custody parole for mother's funeral what application route": {"delhi_prison_rules_2018_parole_furlough", "prisons_1894"},
        "65 yrs heart patient husband in jail furlough application uttar pradesh how to file": {"prisons_1894"},
        "respondent skipped pre litigation mediation can my commercial suit be rejected at threshold": {"commercial_courts_2015", "mediation_2023", "cpc_1908"},
        "rule 86B applies to me turnover 55 lakh per month must pay 1% cash mandatory ya choot hai": {"cgst_rules_2017", "cgst_2017"},
        "agent sold pension money to ulip policy father lost 8 lakh how to complain": {"consumer_protection_2019", "insurance_ombudsman_rules_2017"},
        "how to file PIL in high court regarding pollution from factory nearby": {"constitution_article_226", "environment_protection_1986", "water_pollution_1974", "ngt_2010"},
        "factory smoke making us sick should i go ngt or high court pil first what proof needed": {"constitution_article_226", "environment_protection_1986", "water_pollution_1974", "ngt_2010"},
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
        "contractor at local shop has not paid two months salary but I am from same city what law applies": {"code_on_wages_2019", "contract_labour_1970"},
        "principal employer reliance site contractor ran away with 4 months wages 22 workers what to do": {"contract_labour_1970", "code_on_wages_2019"},
        "principal employer reliance site contractor brought workers from bihar to gujarat and wages unpaid": {"contract_labour_1970", "ismw_1979", "code_on_wages_2019"},
        "brother arrested no fir copy given family police saying secret kya rule": {"bnss_2023", "constitution_article_22"},
        "kanya vivah scheme money not given by government after my daughter wedding": {"bihar_kanya_vivah_service", "rti_2005"},
        "bihar kanya vivah scheme money not given by government after my daughter wedding": {"bihar_kanya_vivah_service", "rti_2005"},
        "my husband died in army no service pension widow what papers needed": {"army_pension_regulations_2008_part_i", "army_pension_regulations_2008_part_ii"},
        "old age pension stopped suddenly bank says aadhaar not linked": {"nsap_guidelines_2014", "aadhaar_2016", "rti_2005"},
        "family pension not paid after husband died in bihar rti kaise karein": {"rti_2005"},
        "recovery agents from a NBFC visited my office and shouted in front of colleagues, this is harassment right": {"rbi_integrated_ombudsman_2021", "consumer_protection_2019"},
        "i am 73 christian widow can my stepchildren claim share in husband self acquired property": {"indian_succession_1925"},
        "pls tell i am christian widow in kerala husband died without will how prop divides among children need lawyer or police": {"indian_succession_1925"},
        "vendor agreed delivery in 30 days now 4 months over want to cancel and recover advance 8 lakh": {"indian_contract_1872", "sale_of_goods_1930"},
        "my husband had affair I caught them I slapped the woman now she is filing case on me what to do": {"bns_2023", "bnss_2023"},
        "fake call from sbi pension office took 2 lakh from my account 75 yr father": {"it_act_2000", "bns_2023", "bnss_2023"},
        "vendor zone bhopal allotted me 2018 now hawker inspector saying pay 2000 every month otherwise remove": {"street_vendors_2014", "prevention_corruption_1988"},
    }
    for query, required_ids in expected.items():
        assert required_ids <= set(_pack_ids(query)), query


def test_atm_cash_not_dispensed_gets_rbi_ombudsman_source_pack():
    ids = set(_pack_ids("ATM cash not dispensed but account debited branch not helping"))

    assert "rbi_integrated_ombudsman_2021" in ids
    assert "consumer_protection_2019" in ids
    assert "ismw_1979" not in _pack_ids(
        "contractor at local shop has not paid two months salary but I am from same city what law applies"
    )


def test_uapa_pack_does_not_match_place_names_like_nuapada():
    packs = set(_pack_ids("brother arrested in nuapada odisha theft case bail no chargesheet possible"))

    assert "uapa_1967" not in packs


def test_arms_farming_tool_pack_needs_actual_tool_context_not_place_name():
    generic = set(_pack_ids("weapon case in gadchiroli police called me what to do"))
    pistol_arms = set(_pack_ids("police booked me under arms act for pistol in gadchiroli what bail"))
    actual_tool = set(_pack_ids(
        "urgent police booked us under arms act for axe we use in farming gadchiroli how to complain"
    ))

    assert "arms_1959_farming_tool" not in generic
    assert "arms_1959_farming_tool" not in pistol_arms
    assert "arms_1959_general_weapon_case" in pistol_arms
    assert "arms_1959_farming_tool" in actual_tool


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


def test_stage_e9_remaining_gap_prompts_get_focused_source_packs():
    whatsapp_packs = source_packs_for_route(
        route_matter("sir my whatsapp account got hacked and someone is asking my contacts fr money in my name where to go"),
        "sir my whatsapp account got hacked and someone is asking my contacts fr money in my name where to go",
    )
    whatsapp_by_id = {pack.id: pack for pack in whatsapp_packs}
    assert {"it_act_2000", "bns_2023", "bnss_2023"} <= set(whatsapp_by_id)
    assert "/sec-319" in whatsapp_by_id["bns_2023"].anchor_patterns
    assert "/sec-173" in whatsapp_by_id["bnss_2023"].anchor_patterns

    airport_packs = source_packs_for_route(
        route_matter("passport seized in mumbai airport for vape cartridge cbd legal in goa"),
        "passport seized in mumbai airport for vape cartridge cbd legal in goa",
    )
    airport_by_id = {pack.id: pack for pack in airport_packs}
    assert {"ndps_1985", "bnss_2023"} <= set(airport_by_id)
    assert "/sec-105" in airport_by_id["bnss_2023"].anchor_patterns

    scst_packs = source_packs_for_route(
        route_matter("SP not transferring my atrocity case to DSP though POA Act says so vidarbha"),
        "SP not transferring my atrocity case to DSP though POA Act says so vidarbha",
    )
    assert {"scst_poa_rules_1995_rule_7", "bnss_2023_scst_atrocity_investigation_transfer"} <= {
        pack.id for pack in scst_packs
    }


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

    prospective_will_ids = set(_pack_ids("Can I make a will for my property?"))
    assert {"indian_succession_1925", "registration_1908"} <= prospective_will_ids

    possessive_will_ids = set(_pack_ids("I want to draft my will and register it"))
    assert {"indian_succession_1925", "registration_1908"} <= possessive_will_ids


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
    public_political_ids = set(_pack_ids("deepfake of modi pm circulating my friend made it bjp it cell threatening"))
    assert {"rpa_1951", "bns_2023_public_political_deepfake", "it_act_2000_political_deepfake_personation"} <= public_political_ids
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


def test_stage37_source_pack_precision_for_child_cyber_arrest_and_custody():
    child_deepfake_query = (
        "my schoolmate is making deepfake nude videos of girls in class using AI "
        "and circulating I am one of them I am 15"
    )
    child_deepfake_ids = _pack_ids(child_deepfake_query)
    assert {"it_act_2000", "pocso_2012", "bns_2023"} <= set(child_deepfake_ids)
    child_deepfake_packs = {
        pack.id: pack
        for pack in source_packs_for_route(route_matter(child_deepfake_query), child_deepfake_query)
    }
    assert "/sec-67B" in child_deepfake_packs["it_act_2000"].anchor_patterns
    assert "bns_2023_child_sexual_image" in child_deepfake_packs
    assert child_deepfake_packs["bns_2023_child_sexual_image"].anchor_patterns[0] == "/sec-77"


def test_creator_paid_video_leak_gets_copyright_and_intermediary_packs():
    ids = set(_pack_ids("telegram channel leaked my onlyfans videos without permission what to do"))

    assert {"it_act_2000", "copyright_1957", "it_act_2000_intermediary", "bns_2023"} <= ids

    adult_private_ids = _pack_ids(
        "he took my private pictures during video call now threatening to put on telegram"
    )
    assert {"it_act_2000", "bns_2023"} <= set(adult_private_ids)
    adult_private_packs = source_packs_for_route(
        route_matter("he took my private pictures during video call now threatening to put on telegram"),
        "he took my private pictures during video call now threatening to put on telegram",
    )
    bns_pack = next(pack for pack in adult_private_packs if pack.id == "bns_2023")
    assert "/sec-351" in bns_pack.anchor_patterns

    minor_deepfake_packs = source_packs_for_route(
        route_matter("my schoolmate is making deepfake nude videos of girls in class using AI and circulating I am one of them I am 15"),
        "my schoolmate is making deepfake nude videos of girls in class using AI and circulating I am one of them I am 15",
    )
    minor_bns = next(pack for pack in minor_deepfake_packs if pack.id == "bns_2023")
    assert minor_bns.anchor_patterns[0] == "/sec-77"

    child_saw_ids = _pack_ids(
        "my child saw a leaked nude video on telegram and is scared can I complain online"
    )
    assert "pocso_2012" not in child_saw_ids

    arrest_ids = _pack_ids("papa arrest 5 din ho gaya magistrate ke samne kab le jana hota hai")
    assert {"constitution_article_21", "constitution_article_22", "bnss_2023"} <= set(arrest_ids)

    custody_ids = _pack_ids(
        "my husband took our 5 year old to delhi during fight and is not letting me meet how do I get her back fast"
    )
    assert {"guardians_wards_1890", "constitution_article_21"} <= set(custody_ids)

    spa_ids = _pack_ids(
        "police came to spa where I work in delhi I ran away am I in trouble do I need lawyer they have my photo from cctv"
    )
    assert {"itpa_1956", "bnss_2023"} <= set(spa_ids)


def test_false_498a_accused_source_packs_include_ipc_498a_when_explicit():
    query = "i am confused my wife filed false 498A case against me n my parents, can we get anticipatory bail pls guide"
    packs = {
        pack.id: pack
        for pack in source_packs_for_route(route_matter(query), query)
    }

    assert "bns_2023_498a_accused_cruelty" in packs
    assert "pwdva_2005_accused_context" in packs
    assert "ipc_1860_498a_accused_cruelty" in packs
    assert "/sec-498A" in packs["ipc_1860_498a_accused_cruelty"].anchor_patterns


def test_stage_iid1_recovery_prompts_get_required_source_packs():
    support_packs = source_packs_for_route(
        route_matter("my husband left me with two children and no money for school fees what to do"),
        "my husband left me with two children and no money for school fees what to do",
    )
    support_by_id = {pack.id: pack for pack in support_packs}
    assert "pwdva_2005" in support_by_id
    assert "bnss_2023" in support_by_id
    assert "/sec-144" in support_by_id["bnss_2023"].anchor_patterns
    assert "crpc_1973" in support_by_id
    assert "/sec-125" in support_by_id["crpc_1973"].anchor_patterns

    inlaw_packs = source_packs_for_route(
        route_matter("my husband's brother has been making me uncomfortable saying things and now grabbed my hand whom to tell I cant tell husband"),
        "my husband's brother has been making me uncomfortable saying things and now grabbed my hand whom to tell I cant tell husband",
    )
    inlaw_by_id = {pack.id: pack for pack in inlaw_packs}
    assert {"/sec-3", "/sec-18", "/sec-12"} <= set(inlaw_by_id["pwdva_2005"].anchor_patterns)
    assert {"/sec-74", "/sec-75", "/sec-79"} <= set(inlaw_by_id["bns_2023"].anchor_patterns)

    abroad_ids = _pack_ids(
        "my ex husband took our son to UK on tourist visa and is not bringing back he said permanent now what to do"
    )
    assert {"guardians_wards_1890", "constitution_article_21", "family_courts_1984"} <= set(abroad_ids)

    promise_packs = source_packs_for_route(
        route_matter("I am living with my boyfriend for 3 years he promised marriage now he is marrying another girl can I file case"),
        "I am living with my boyfriend for 3 years he promised marriage now he is marrying another girl can I file case",
    )
    promise_by_id = {pack.id: pack for pack in promise_packs}
    assert {"/sec-69", "/sec-63", "/sec-64"} <= set(promise_by_id["bns_2023"].anchor_patterns)
    assert {"/sec-173", "/sec-175"} <= set(promise_by_id["bnss_2023"].anchor_patterns)

    assert "cpc_1908" in _pack_ids(
        "what should I wear to court as litigant in person appearing first time"
    )
    assert "income_tax_1961" in _pack_ids(
        "i forgot to file ITR for AY 2022-23 can i still file it now what is the penalty"
    )

    common_land_ids = _pack_ids(
        "sarpanch giving common village land to his brother no panchayat meeting was held"
    )
    assert {"constitution_panchayats_part_ix", "rti_2005"} <= set(common_land_ids)

    spa_packs = source_packs_for_route(
        route_matter("the spa was raided last week and police took me and other girls to station I just do massage I am scared what will happen now"),
        "the spa was raided last week and police took me and other girls to station I just do massage I am scared what will happen now",
    )
    spa_by_id = {pack.id: pack for pack in spa_packs}
    assert {"/sec-4", "/sec-5", "/sec-7", "/sec-8"} <= set(spa_by_id["itpa_1956"].anchor_patterns)
    assert {"/sec-173", "/sec-216", "/sec-480", "/sec-483"} <= set(spa_by_id["bnss_2023"].anchor_patterns)


def test_stage_iid2_production_gate_prompts_get_required_source_packs():
    tenancy_packs = source_packs_for_route(
        route_matter("my landlord is asking me to vacate in 15 days because he wants to sell the flat, my lock in is for 11 months"),
        "my landlord is asking me to vacate in 15 days because he wants to sell the flat, my lock in is for 11 months",
    )
    tenancy_by_id = {pack.id: pack for pack in tenancy_packs}
    assert "transfer_property_1882" in tenancy_by_id
    assert {"/sec-105", "/sec-106", "/sec-111"} <= set(tenancy_by_id["transfer_property_1882"].anchor_patterns)

    salary_packs = source_packs_for_route(
        route_matter("husband took my salary atm card and gives me only 2000 per month for groceries is this legal he says he is breadwinner"),
        "husband took my salary atm card and gives me only 2000 per month for groceries is this legal he says he is breadwinner",
    )
    salary_by_id = {pack.id: pack for pack in salary_packs}
    assert "pwdva_2005" in salary_by_id
    assert {"/sec-3", "/sec-20", "/sec-12"} <= set(salary_by_id["pwdva_2005"].anchor_patterns)

    mtp_packs = source_packs_for_route(
        route_matter("I am 6 months pregnant after rape doctor says it is too late for abortion but I cannot keep this child help"),
        "I am 6 months pregnant after rape doctor says it is too late for abortion but I cannot keep this child help",
    )
    mtp_by_id = {pack.id: pack for pack in mtp_packs}
    assert "mtp_1971" in mtp_by_id
    assert {"/sec-3", "/sec-5"} <= set(mtp_by_id["mtp_1971"].anchor_patterns)
    assert "rape survivor" in mtp_by_id["mtp_1971"].search_query

    baby_support_packs = source_packs_for_route(
        route_matter("I left my husband 2 months back I have a baby 1 year old he is not giving any money how much maintenance can I get"),
        "I left my husband 2 months back I have a baby 1 year old he is not giving any money how much maintenance can I get",
    )
    baby_support_by_id = {pack.id: pack for pack in baby_support_packs}
    assert "pwdva_2005" in baby_support_by_id
    assert "bnss_2023" in baby_support_by_id
    assert "/sec-144" in baby_support_by_id["bnss_2023"].anchor_patterns
    assert "crpc_1973" in baby_support_by_id
    assert "/sec-125" in baby_support_by_id["crpc_1973"].anchor_patterns

    custody_packs = source_packs_for_route(
        route_matter("girl child age 4 my wife died parents in law took her away they refuse to return"),
        "girl child age 4 my wife died parents in law took her away they refuse to return",
    )
    custody_by_id = {pack.id: pack for pack in custody_packs}
    assert "guardians_wards_1890" in custody_by_id
    assert "hindu_minority_guardianship_1956" in custody_by_id
    assert {"/sec-6", "/sec-13"} <= set(custody_by_id["hindu_minority_guardianship_1956"].anchor_patterns)


def test_stage38_review_blocker_queries_get_precise_source_packs():
    generic_kanya_ids = _pack_ids(
        "kanya vivah scheme money not given after my daughter wedding where to complain"
    )
    assert "rti_2005" in generic_kanya_ids
    assert "bihar_kanya_vivah_service" in generic_kanya_ids

    bihar_kanya_ids = _pack_ids(
        "bihar kanya vivah scheme money not given by government after my daughter wedding"
    )
    assert {"bihar_kanya_vivah_service", "rti_2005"} <= set(bihar_kanya_ids)

    for state_query in (
        "madhya pradesh kanya vivah scheme money not received after daughter wedding",
        "rajasthan kanya vivah yojana money not received after daughter wedding",
        "kanya vivah scheme payment pending mp",
        "kanya vivah scheme payment pending in MP",
        "kanya vivah yojana payment pending up",
    ):
        state_ids = set(_pack_ids(state_query))
        assert "rti_2005" in state_ids
        assert "bihar_kanya_vivah_service" not in state_ids

    honour_ids = set(_pack_ids("my parents threatening to kill me if i marry inter caste need protection"))
    assert {"bns_2023_honour_threat_intimidation", "bnss_2023_fir_information"} <= honour_ids

    wage_ids = _pack_ids(
        "boss saying i signed paper give up wages but i dont read english kannada bangalore"
    )
    assert {"code_on_wages_2019_contracting_out", "indian_contract_1872_free_consent"} <= set(wage_ids)

    otp_ids = _pack_ids("otp fraud 2 lakh lost bank says my fault no refund what can i do")
    assert {"it_act_2000", "rbi_integrated_ombudsman_2021"} <= set(otp_ids)

    quashing_ids = _pack_ids("482 CrPC quashing FIR in high court what documents needed")
    assert {"bnss_2023_quashing", "crpc_1973_quashing"} <= set(quashing_ids)
    legacy_quashing_ids = _pack_ids("482 CrPC quashing FIR in high court what documents needed, FIR is from 2023")
    assert "crpc_1973_quashing" in legacy_quashing_ids
    assert "bnss_2023_quashing" not in legacy_quashing_ids
    bnss_named_quashing_ids = _pack_ids("BNSS 2023 section 528 quashing FIR in high court what documents needed")
    assert "bnss_2023_quashing" in bnss_named_quashing_ids
    assert "crpc_1973_quashing" in bnss_named_quashing_ids
    assert "bnss_2023_quashing" not in _pack_ids(
        "can high court quash consumer forum order in my refund case"
    )
    assert "crpc_1973_quashing" not in _pack_ids(
        "can high court quash civil execution order under CPC"
    )

    execution_packs = source_packs_for_route(
        route_matter("judgment debtor not paying money decree can court attach property"),
        "judgment debtor not paying money decree can court attach property",
    )
    cpc = next(pack for pack in execution_packs if pack.id == "cpc_1908")
    assert "/sec-51" in cpc.anchor_patterns
    assert "/sec-47" in cpc.anchor_patterns

    senior_packs = source_packs_for_route(
        route_matter("maintenance tribunal ordered son to pay but he stopped paying how to enforce"),
        "maintenance tribunal ordered son to pay but he stopped paying how to enforce",
    )
    senior = next(pack for pack in senior_packs if pack.id == "senior_citizens_2007")
    assert "/sec-11" in senior.anchor_patterns
    assert "/sec-13" in senior.anchor_patterns
    senior_police_keyword_packs = source_packs_for_route(
        route_matter("tribunal in tamil nadu ordered son to pay 10000 he stopped paying enforce need lawyer or police"),
        "tribunal in tamil nadu ordered son to pay 10000 he stopped paying enforce need lawyer or police",
    )
    senior_police_keyword = next(pack for pack in senior_police_keyword_packs if pack.id == "senior_citizens_2007")
    assert "/sec-11" in senior_police_keyword.anchor_patterns
    assert "/sec-13" in senior_police_keyword.anchor_patterns
    senior_police_ids = {pack.id for pack in senior_police_keyword_packs}
    assert "consumer_protection_2019" not in senior_police_ids
    assert "insurance_ombudsman_rules_2017" not in senior_police_ids
    marital_sexual_packs = source_packs_for_route(
        route_matter("husband forces me at night even when i say no what law"),
        "husband forces me at night even when i say no what law",
    )
    marital_bns = next(pack for pack in marital_sexual_packs if pack.id == "bns_2023")
    assert "/sec-63" in marital_bns.anchor_patterns
    senior_gift_packs = source_packs_for_route(
        route_matter("father gifted flat to son but son not paying maintenance can tribunal cancel gift deed"),
        "father gifted flat to son but son not paying maintenance can tribunal cancel gift deed",
    )
    senior_gift = next(pack for pack in senior_gift_packs if pack.id == "senior_citizens_2007")
    assert "/sec-23" in senior_gift.anchor_patterns

    senior_transfer_ids = {
        pack.id
        for pack in source_packs_for_route(
            route_matter("mother 80 transferred flat to son now bahu telling her to sleep outside"),
            "mother 80 transferred flat to son now bahu telling her to sleep outside",
        )
    }
    assert {"senior_citizens_2007", "transfer_property_1882"} <= senior_transfer_ids
    assert "it_act_2000" not in senior_transfer_ids
    assert "bns_2023" not in senior_transfer_ids

    mgnrega_social_ids = {
        pack.id
        for pack in source_packs_for_route(
            route_matter("gram sabha social audit found dead persons wages, bdo silent"),
            "gram sabha social audit found dead persons wages, bdo silent",
        )
    }
    assert {"mgnrega_2005", "rti_2005"} <= mgnrega_social_ids
    assert "code_on_wages_2019" not in mgnrega_social_ids

    juvenile_packs = source_packs_for_route(
        route_matter("son 17 yrs in adult jail puzhal pocso case age proof school certificate where to file"),
        "son 17 yrs in adult jail puzhal pocso case age proof school certificate where to file",
    )
    jj_pack = next(pack for pack in juvenile_packs if pack.id == "jj_2015")
    assert "/sec-2-t" in jj_pack.anchor_patterns

    nephew_packs = {
        pack.id: pack
        for pack in source_packs_for_route(
            route_matter("my 17 year nephew accused in pocso is in adult prison, school DOB proof available"),
            "my 17 year nephew accused in pocso is in adult prison, school DOB proof available",
        )
    }
    assert "pocso_2012" in nephew_packs
    assert "jj_2015" in nephew_packs
    assert {"/sec-94", "/sec-9"} <= set(nephew_packs["jj_2015"].anchor_patterns)

    ndps_packs = source_packs_for_route(
        route_matter("NDPS case 50 gram ganja, first time accused, can I get bail and which court should I approach"),
        "NDPS case 50 gram ganja, first time accused, can I get bail and which court should I approach",
    )
    bnss = next(pack for pack in ndps_packs if pack.id == "bnss_2023")
    assert "/sec-480" in bnss.anchor_patterns
    assert "/sec-483" in bnss.anchor_patterns
    ndps = next(pack for pack in ndps_packs if pack.id == "ndps_1985")
    assert "/sec-2-a" in ndps.anchor_patterns
    assert "/sec-14" in ndps.anchor_patterns
    assert "/sec-37" in ndps.anchor_patterns

    unknown_ndps_packs = source_packs_for_route(
        route_matter("brother arrested ndps 5 gram personal use how is small quantity proven"),
        "brother arrested ndps 5 gram personal use how is small quantity proven",
    )
    unknown_ndps = next(pack for pack in unknown_ndps_packs if pack.id == "ndps_1985")
    assert "/sec-2" in unknown_ndps.anchor_patterns
    assert "/sec-22" in unknown_ndps.anchor_patterns

    bhang_ndps_packs = source_packs_for_route(
        route_matter("bhang lassi at holi police saying ndps mahabaleshwar what to do"),
        "bhang lassi at holi police saying ndps mahabaleshwar what to do",
    )
    bhang_ndps = next(pack for pack in bhang_ndps_packs if pack.id == "ndps_1985")
    assert "/sec-2" in bhang_ndps.anchor_patterns
    assert "/sec-37" in bhang_ndps.anchor_patterns
    assert "/sec-36C" in bhang_ndps.anchor_patterns
    assert "/sec-22-b" in bhang_ndps.anchor_patterns
    assert bhang_ndps.priority > 1.3

    prison_packs = source_packs_for_route(
        route_matter("tihar jail mulaqat only 30 min once a week is this legal can we ask more"),
        "tihar jail mulaqat only 30 min once a week is this legal can we ask more",
    )
    assert {"delhi_prison_rules_2018_mulaqat_books", "prisons_1894", "constitution_article_21"} <= {pack.id for pack in prison_packs}

    vakalat_packs = source_packs_for_route(
        route_matter("how to file vakalatnama change of advocate during pending suit"),
        "how to file vakalatnama change of advocate during pending suit",
    )
    vakalat_cpc = next(pack for pack in vakalat_packs if pack.id == "cpc_1908")
    assert "/sec-151" in vakalat_cpc.anchor_patterns
    assert "legal_services_authorities_1987" in {pack.id for pack in vakalat_packs}

    crypto_packs = source_packs_for_route(
        route_matter("guy from telegram crypto group rugpulled me 3 lakh whom to complain"),
        "guy from telegram crypto group rugpulled me 3 lakh whom to complain",
    )
    crypto_bns = next(pack for pack in crypto_packs if pack.id == "bns_2023")
    assert "/sec-318" in crypto_bns.anchor_patterns
    assert "pmla_2002" in {pack.id for pack in crypto_packs}

    kyc_packs = source_packs_for_route(
        route_matter("blue trunks app froze my account showing kyc pending pe stuck 80k"),
        "blue trunks app froze my account showing kyc pending pe stuck 80k",
    )
    kyc_ids = {pack.id for pack in kyc_packs}
    assert {"consumer_protection_2019", "it_act_2000_platform_wallet"} <= kyc_ids
    assert "pmla_2002" not in kyc_ids

    paytm_ids = set(_pack_ids("paytm wallet blocked support not replying"))
    assert "consumer_protection_2019" in paytm_ids
    assert "pmla_2002" not in paytm_ids

    bank_kyc_ids = set(_pack_ids("bank refused to open account because kyc pending"))
    assert "bnss_2023_bank_account_legal_hold" not in bank_kyc_ids
    assert "it_act_2000_bank_freeze_cyber_hold" not in bank_kyc_ids

    ed_freeze_ids = set(_pack_ids("bank account frozen after ED notice what order copy can I ask"))
    assert "bnss_2023_bank_account_legal_hold" in ed_freeze_ids

    mining_noc_ids = _pack_ids(
        "DM gave NOC to bauxite project bastar without gram sabha resolution how to challenge"
    )
    assert {"pesa_1996", "mmdr_1957", "forest_conservation_1980"} <= set(mining_noc_ids)

    bauxite_pollution_ids = set(_pack_ids("bauxite mine pollution damaged my house in bastar what compensation"))
    assert {"environment_protection_1986", "water_pollution_1974", "ngt_2010"} <= bauxite_pollution_ids
    assert "pesa_1996" not in bauxite_pollution_ids
    assert "rfctlarr_2013" not in bauxite_pollution_ids
    assert "forest_conservation_1980" not in bauxite_pollution_ids

    ancestral_ids = _pack_ids(
        "ancestral land in my dada name now uncle selling without telling us what to do"
    )
    assert {"hindu_succession_1956", "transfer_property_1882", "specific_relief_1963"} <= set(ancestral_ids)

    encroachment_ids = set(_pack_ids("neighbour encroached on my land and police says civil matter"))
    assert {"specific_relief_1963_land_encroachment", "transfer_property_1882_land_title"} <= encroachment_ids

    tenant_lock_ids = set(_pack_ids("tenant changed lock and stopped paying rent can I break lock"))
    assert "transfer_property_1882" in tenant_lock_ids

    landlord_lockout_ids = set(_pack_ids("landlord broke my lock and threw my things out because rent late"))
    assert "transfer_property_1882" in landlord_lockout_ids

    builder_defect_ids = set(_pack_ids("flat possession already given but bathroom tiles defective builder not repairing"))
    assert "rera_2016" in builder_defect_ids
    builder_gave_possession_ids = set(_pack_ids("builder gave possession but bathroom tiles are broken and leakage started"))
    assert "rera_2016" in builder_gave_possession_ids
    defective_phone_ids = set(_pack_ids("defective phone seller not repairing refund denied"))
    assert "rera_2016" not in defective_phone_ids
    washing_machine_ids = set(_pack_ids("washing machine leakage shop not repairing refund"))
    assert "rera_2016" not in washing_machine_ids
    doctor_refund_ids = set(_pack_ids("doctor appointment cancelled but clinic denied refund"))
    assert "clinical_establishments_2010" not in doctor_refund_ids

    tribal_blank_ids = set(_pack_ids("tribal family land transferred by moneylender using blank paper"))
    assert {"pesa_1996", "constitution_scheduled_areas", "transfer_property_1882_tribal_document_lane"} <= tribal_blank_ids

    voluntary_gift_ids = set(_pack_ids("my father willingly gifted flat to daughter now regrets it can we cancel gift deed"))
    assert {"transfer_property_1882_gift_revocation", "registration_1908_gift_deed_records"} <= voluntary_gift_ids


def test_stage_c_repeated_blockers_get_required_source_packs():
    expectations = {
        "supplier delivered defective material now refusing refund 18 lakh contract": {
            "indian_contract_1872",
            "sale_of_goods_1930",
        },
        "mother says son took her thumb impression on blank paper now produced as gift deed": {
            "transfer_property_1882",
            "registration_1908",
            "specific_relief_1963",
            "indian_contract_1872",
            "bns_2023",
        },
        "son took loan against my house i didn't sign told bank to stop ahmedabad": {
            "bns_2023",
            "bnss_2023",
            "banking_regulation_1949",
            "rbi_integrated_ombudsman_2021",
        },
        "got message saying my aadhaar issued 4 sims i never took how to check": {
            "aadhaar_2016",
            "telecommunications_2023",
            "it_act_2000",
            "bnss_2023_cyber_identity_fir",
        },
        "thermal plant blasting cracking our houses no compensation kalahandi": {
            "ngt_2010",
            "environment_protection_1986",
            "rfctlarr_2013_project_damage_compensation",
        },
        "i was duped of 3.5 lakh in fake stock trading app, transferred to multiple UPI ids, cyber cell complaint filed but no progress": {
            "it_act_2000",
            "bns_2023",
            "bnss_2023",
        },
        "someone made fake instagram account using my photos and dms girls": {
            "it_act_2000",
            "bns_2023_social_impersonation",
        },
        "lic agent told my father guaranteed return now policy matured got half amount fraud": {
            "senior_citizens_2007",
            "consumer_protection_2019",
            "insurance_ombudsman_rules_2017",
        },
        "tehsildar transferred my baba land to bania without my consent agency area andhra": {
            "ap_scheduled_areas_land_transfer_case",
            "constitution_scheduled_areas",
        },
        "fake call from sbi pension office took 2 lakh from my account 75 yr father": {
            "it_act_2000",
            "bns_2023",
            "bnss_2023",
            "rbi_integrated_ombudsman_2021",
        },
        "I had abortion 5 years back husband found out threatening divorce": {
            "mtp_1971",
            "hindu_marriage_1955",
            "family_courts_1984",
        },
        "in-laws not giving back my jewellery streedhan after husband died": {
            "pwdva_2005",
            "dowry_prohibition_1961",
            "hindu_succession_1956",
            "bns_2023",
        },
    }
    for query, expected_ids in expectations.items():
        ids = set(_pack_ids(query))
        assert expected_ids <= ids, query


def test_stage_c_review_source_pack_regime_and_variant_guards():
    b2b_ids = set(_pack_ids("supplier delivered defective material refusing refund"))
    assert {"indian_contract_1872", "sale_of_goods_1930"} <= b2b_ids
    dealer_ids = set(_pack_ids("dealer supplied poor quality goods refusing refund"))
    assert {"indian_contract_1872", "sale_of_goods_1930"} <= dealer_ids

    lic_ids = set(_pack_ids("LIC agent told my father guaranteed return now matured got half amount fraud"))
    assert {"consumer_protection_2019", "insurance_ombudsman_rules_2017"} <= lic_ids

    mtp_packs = source_packs_for_route(
        route_matter("I had abortion 5 years back husband found out threatening divorce"),
        "I had abortion 5 years back husband found out threatening divorce",
    )
    hma = next(pack for pack in mtp_packs if pack.id == "hindu_marriage_1955")
    assert "/sec-13" in hma.anchor_patterns
    assert "hindu_marriage_1955_divorce" in {pack.id for pack in mtp_packs}

    legacy_property_ids = set(_pack_ids(
        "mother says son took her thumb impression on blank paper in 2022 now produced as gift deed"
    ))
    assert "crpc_1973" in legacy_property_ids
    assert "bns_2023" not in legacy_property_ids
    assert "bnss_2023" not in legacy_property_ids

    legacy_bank_ids = set(_pack_ids(
        "son took loan against my house in 2022 i did not sign told bank to stop"
    ))
    assert "crpc_1973" in legacy_bank_ids
    assert "bns_2023" not in legacy_bank_ids
    assert "bnss_2023" not in legacy_bank_ids

    forged_signature_packs = source_packs_for_route(
        route_matter("in 2019 brother forged my signature on gift deed of my house"),
        "in 2019 brother forged my signature on gift deed of my house",
    )
    forged_signature_ids = {pack.id for pack in forged_signature_packs}
    assert {"transfer_property_1882", "registration_1908", "specific_relief_1963", "crpc_1973"} <= forged_signature_ids
    assert "bns_2023" not in forged_signature_ids
    crpc = next(pack for pack in forged_signature_packs if pack.id == "crpc_1973")
    assert crpc.anchor_patterns == ("/sec-154", "/sec-156", "/sec-200")


def test_common_screenshot_source_packs_are_available():
    assert {"rbi_integrated_ombudsman_2021", "banking_regulation_1949"} <= set(
        _pack_ids("my bank account is frozen what to do")
    )
    assert {
        "rbi_integrated_ombudsman_2021",
        "banking_regulation_1949",
        "bnss_2023_bank_account_legal_hold",
        "crpc_1973_bank_account_legal_hold",
    } <= set(
        _pack_ids("my bank account is frozen suddenly cyber police says lien what can I do")
    )

    loan_ids = set(_pack_ids("Loan app is harassing my contacts"))
    assert {
        "rbi_integrated_ombudsman_2021",
    } <= loan_ids
    assert "dpdp_2023_loan_app_contacts" not in loan_ids
    assert "it_act_2000" not in loan_ids
    loan_relatives_ids = set(_pack_ids("online loan app calling my relatives and abusing me"))
    assert {
        "rbi_integrated_ombudsman_2021",
        "bns_2023",
    } <= loan_relatives_ids
    assert "it_act_2000" not in loan_relatives_ids

    bank_debit_ids = set(_pack_ids("Bank deducted money wrongly and customer care not helping."))
    assert {"rbi_integrated_ombudsman_2021", "consumer_protection_2019"} <= bank_debit_ids

    fake_customer_care_ids = set(_pack_ids("fake customer care made me install app and money got transferred"))
    assert {"it_act_2000", "rbi_integrated_ombudsman_2021", "bns_2023", "bnss_2023"} <= fake_customer_care_ids

    credit_card_ids = set(_pack_ids("credit card unauthorized transaction bank not reversing amount"))
    assert {"it_act_2000", "rbi_integrated_ombudsman_2021", "bns_2023"} <= credit_card_ids

    recovery_agent_ids = set(_pack_ids("loan recovery agents came home and threatened my mother"))
    assert {"rbi_integrated_ombudsman_2021", "bns_2023", "bnss_2023"} <= recovery_agent_ids

    personal_loan_ids = set(_pack_ids("My brother is not returning my money, which he took loan"))
    assert {"indian_contract_1872", "limitation_1963", "cpc_1908"} <= personal_loan_ids
    assert "ni_act_1881" not in personal_loan_ids


def test_common_user_gate_failure_cluster_source_packs_are_available():
    expected = {
        "bank reversed my balance saying technical error but not giving reason": {
            "rbi_integrated_ombudsman_2021",
            "consumer_protection_2019",
        },
        "upi fraud happened bank says it is my mistake what to do": {
            "rbi_integrated_ombudsman_2021",
            "it_act_2000",
            "bns_2023",
            "bnss_2023",
        },
        "salary account blocked by bank saying police request no notice": {
            "rbi_integrated_ombudsman_2021",
            "banking_regulation_1949",
            "bnss_2023_bank_account_legal_hold",
            "crpc_1973_bank_account_legal_hold",
        },
            "online loan app calling my relatives and abusing me": {
                "rbi_integrated_ombudsman_2021",
                "bns_2023",
                "bnss_2023",
            },
        "private hospital not giving medical records after discharge": {
            "consumer_protection_2019",
            "clinical_establishments_2010",
            "medical_ethics_2002",
        },
        "hospital overcharged me and not giving detailed bill": {
            "consumer_protection_2019",
            "clinical_establishments_2010",
        },
        "municipality removed my tea cart from footpath without notice": {
            "street_vendors_2014",
        },
        "biometric failed so dealer refused wheat and rice": {
            "national_food_security_2013",
            "aadhaar_2016",
            "rti_2005",
        },
        "manager sends dirty messages and HR says ignore": {
            "posh_2013",
        },
        "unknown person posting my number on dating app": {
            "it_act_2000",
        },
        "mother in law has my marriage gold what case can i file": {
            "pwdva_2005",
            "dowry_prohibition_1961",
            "hindu_succession_1956",
            "bns_2023",
        },
        "education loan subsidy not given by bank what complaint": {
            "rbi_integrated_ombudsman_2021",
            "consumer_protection_2019",
        },
        "local body locked my commercial shop saying licence problem": {
            "rti_2005",
        },
        "relative took hand loan 2 years back no agreement what can i do": {
            "indian_contract_1872",
            "limitation_1963",
            "cpc_1908",
        },
    }

    for query, expected_ids in expected.items():
        assert expected_ids <= set(_pack_ids(query)), query

    salary_freeze_query = "salary account blocked by bank saying police request no notice"
    salary_freeze_packs = {
        pack.id: pack
        for pack in source_packs_for_route(route_matter(salary_freeze_query), salary_freeze_query)
    }
    upi_freeze_query = "my upi account frozen and branch not giving complaint number"
    upi_freeze_ids = set(_pack_ids(upi_freeze_query))
    assert {"rbi_integrated_ombudsman_2021", "banking_regulation_1949"} <= upi_freeze_ids
    assert "bnss_2023" not in upi_freeze_ids
    assert salary_freeze_packs["bnss_2023_bank_account_legal_hold"].anchor_patterns == ("/sec-106",)
    assert salary_freeze_packs["crpc_1973_bank_account_legal_hold"].anchor_patterns == ("/sec-102",)
    assert "/sec-35A" in salary_freeze_packs["banking_regulation_1949"].anchor_patterns

    heir_sale_ids = set(_pack_ids("Can I sell property if one legal heir is not agreeing?"))
    assert {"transfer_property_1882", "hindu_succession_1956", "specific_relief_1963"} <= heir_sale_ids
    inherited_sale_packs = {
        pack.id: pack
        for pack in source_packs_for_route(
            route_matter("father died one sister refuses to sign sale of house what to do"),
            "father died one sister refuses to sign sale of house what to do",
        )
    }
    assert "specific_relief_1963_inherited_sale" in inherited_sale_packs
    assert {"/sec-31", "/sec-34", "/sec-38"} <= set(
        inherited_sale_packs["specific_relief_1963_inherited_sale"].anchor_patterns
    )
    sold_ancestral_ids = set(_pack_ids("uncle sold ancestral land without asking other heirs where to go"))
    assert {"specific_relief_1963", "transfer_property_1882", "hindu_succession_1956"} <= sold_ancestral_ids

    adultery_ids = set(_pack_ids("i caught my husband with another women having sex"))
    assert {"family_courts_1984", "hindu_marriage_1955_divorce"} <= adultery_ids
    assert "bns_2023" not in adultery_ids
    assert "bnss_2023" not in adultery_ids
    living_with_another_ids = set(_pack_ids("I found my wife living with another man after marriage what case can I file"))
    assert {"family_courts_1984", "hindu_marriage_1955_divorce"} <= living_with_another_ids
    assert "bns_2023" not in living_with_another_ids
    assert "bnss_2023" not in living_with_another_ids


def test_stage3_property_succession_source_packs_are_available():
    mutation_ids = set(_pack_ids("mother died and two brothers are blocking mutation of her house"))
    assert {"hindu_succession_1956", "rti_2005"} <= mutation_ids

    daughter_packs = {
        pack.id: pack
        for pack in source_packs_for_route(
            route_matter("ancestral land brothers saying daughters have no share"),
            "ancestral land brothers saying daughters have no share",
        )
    }
    assert "hindu_succession_1956" in daughter_packs
    assert "/sec-6" in daughter_packs["hindu_succession_1956"].anchor_patterns
    assert set(daughter_packs["hindu_succession_1956"].anchor_patterns) == {"/sec-6"}
    assert daughter_packs["hindu_succession_1956"].priority >= 1.18

    society_ids = set(_pack_ids("housing society not transferring flat after father death to legal heirs"))
    assert {
        "hindu_succession_1956",
        "registration_1908_flat_transfer",
        "transfer_property_1882_flat_transfer",
    } <= society_ids


def test_stage_failure_family_source_packs_are_available():
    aadhaar_loan_ids = set(_pack_ids("someone used my aadhaar and took loan in my name"))
    assert {
        "it_act_2000",
        "aadhaar_2016_identity_misuse",
        "credit_information_companies_2005",
        "rbi_integrated_ombudsman_2021",
    } <= aadhaar_loan_ids

    fake_sim_ids = set(_pack_ids("my aadhaar used for sim and fraud case came to me"))
    assert {
        "it_act_2000",
        "aadhaar_2016_identity_misuse",
        "telecommunications_2023",
        "bns_2023",
    } <= fake_sim_ids

    asha_ids = set(_pack_ids("ASHA worker incentive not paid for 6 months who can help"))
    assert {"nhm_asha_incentives_2025", "rti_2005"} <= asha_ids

    passport_ids = set(_pack_ids("police not clearing passport verification asking money"))
    assert {"passports_1967", "prevention_corruption_1988_passport_bribe"} <= passport_ids

    tribal_ids = set(_pack_ids("tribal family land transferred by moneylender using blank paper"))
    assert {"pesa_1996", "constitution_scheduled_areas"} <= tribal_ids

    education_deadline_ids = set(
        _pack_ids("student education loan rejected and admission deadline is tomorrow")
    )
    assert {"rbi_integrated_ombudsman_2021", "consumer_protection_2019"} <= education_deadline_ids


def test_stage5_money_cyber_identity_source_packs_cover_contract_authorities():
    expected = {
        "customer care says failed UPI refund will come after 30 days can I complain now": {
            "rbi_integrated_ombudsman_2021",
            "consumer_protection_2019",
        },
        "PhonePe failed payment but amount cut and support closed ticket": {
            "rbi_integrated_ombudsman_2021",
            "consumer_protection_2019",
        },
        "police froze my bank account after fraud complaint but I am victim not accused": {
            "rbi_integrated_ombudsman_2021",
            "banking_regulation_1949",
            "bnss_2023_bank_account_legal_hold",
            "crpc_1973_bank_account_legal_hold",
            "it_act_2000_bank_freeze_cyber_hold",
        },
        "fraud complaint against my UPI ID and bank froze account no order": {
            "rbi_integrated_ombudsman_2021",
            "banking_regulation_1949",
            "bnss_2023_bank_account_legal_hold",
            "crpc_1973_bank_account_legal_hold",
            "it_act_2000_bank_freeze_cyber_hold",
        },
        "PAN card copy leaked online and fake bank account opened in my name": {
            "dpdp_2023_pan_fake_bank_account",
            "rbi_integrated_ombudsman_2021_fake_bank_account",
            "it_act_2000",
        },
        "old age pension stopped because bank account closed and Aadhaar not linked": {
            "nsap_guidelines_2014",
            "aadhaar_2016",
            "rbi_integrated_ombudsman_2021_pension_bank_account",
        },
        "pension stopped after biometric mismatch, block office says update Aadhaar only": {
            "nsap_guidelines_2014",
            "aadhaar_2016",
            "rti_2005",
        },
        "ration dealer denied grain because old mother fingerprint failed": {
            "national_food_security_2013",
            "aadhaar_2016",
            "rti_2005",
        },
        "ration shop machine says thumb not matching and dealer denied wheat": {
            "national_food_security_2013",
            "aadhaar_2016_ration_authentication",
            "rti_2005",
        },
        "PAN name spelling mistake and Aadhaar mismatch bank KYC failed": {
            "income_tax_pan_1961",
            "aadhaar_2016",
        },
        "my PAN name has spelling mistake but Aadhaar is correct, bank KYC failed": {
            "income_tax_pan_1961",
            "aadhaar_2016",
        },
        "Aadhaar authentication failed for LPG subsidy and portal gives no reason": {
            "aadhaar_2016_benefit_authentication",
            "rti_2005",
        },
        "political meme with Modi face went viral can police file FIR": {
            "it_act_2000_public_post",
            "bns_2023_public_post_reputation_threat",
            "bnss_2023",
        },
        "normal EMI is late and lender sent reminder SMS is that harassment": {
            "rbi_integrated_ombudsman_2021",
        },
        "fake TRAI video call said my SIM will close but I have not paid money": {
            "it_act_2000",
            "bnss_2023_digital_arrest",
            "bns_2023_digital_arrest_impersonation",
        },
    }

    for query, expected_ids in expected.items():
        assert expected_ids <= set(_pack_ids(query)), query


def test_reviewer_counterexample_source_packs_stay_specific():
    pan_loan_ids = set(_pack_ids("someone used my pan only and took loan in my name"))
    assert {"it_act_2000", "credit_information_companies_2005", "rbi_integrated_ombudsman_2021"} <= pan_loan_ids
    assert "aadhaar_2016_identity_misuse" not in pan_loan_ids

    pan_police_ids = set(_pack_ids("someone used my pan only and took loan in my name what police complaint"))
    assert {
        "it_act_2000",
        "credit_information_companies_2005",
        "rbi_integrated_ombudsman_2021",
        "bnss_2023",
        "bns_2023",
    } <= pan_police_ids
    assert "aadhaar_2016_identity_misuse" not in pan_police_ids

    asha_cross_noise_ids = set(_pack_ids("asha worker incentive pending but block office says ask anganwadi cdpo where to complain"))
    assert {"nhm_asha_incentives_2025", "rti_2005"} <= asha_cross_noise_ids
    assert "anganwadi_honorarium_case_law" not in asha_cross_noise_ids

    anganwadi_cross_noise_ids = set(_pack_ids("anganwadi worker payment pending but officer called it asha nhm file where to complain"))
    assert {"anganwadi_honorarium_case_law", "rti_2005"} <= anganwadi_cross_noise_ids
    assert "nhm_asha_incentives_2025" not in anganwadi_cross_noise_ids

    assert "nhm_asha_incentives_2025" not in set(_pack_ids("health department ASHA software login not working"))
    icds_supplier_ids = set(_pack_ids("ICDS nutrition supplier payment pending"))
    assert "anganwadi_honorarium_case_law" not in icds_supplier_ids
    assert "indian_contract_1872" in icds_supplier_ids

    obc_ids = set(_pack_ids("OBC certificate pending and scholarship deadline is tomorrow"))
    assert {"constitution_article_46", "rti_2005"} <= obc_ids
    assert "constitution_article_341_342" not in obc_ids

    restaurant_ids = set(_pack_ids("restaurant sealed by corporation no notice"))
    assert {"food_safety_2006", "rti_2005"} <= restaurant_ids

    hotel_kitchen_ids = set(_pack_ids("health department sealed my small hotel kitchen without giving inspection report"))
    assert "food_safety_2006" in hotel_kitchen_ids

    gujarat_shop_ids = set(_pack_ids("My shop is in Gujarat and municipality sealed it."))
    assert {
        "gujarat_shops_establishments_2019",
        "gujarat_municipalities_1963",
        "gujarat_provincial_municipal_corporations_1949",
        "rti_2005",
    } <= gujarat_shop_ids

    pan_ids = set(_pack_ids("my pan and aadhaar is mismatch"))
    assert {"income_tax_pan_1961", "aadhaar_2016", "rti_2005"} <= pan_ids

    death_ids = set(_pack_ids("death certificate has wrong name hospital says they cannot correct it what is process"))
    assert {"births_deaths_registration_1969", "rti_2005"} <= death_ids

    posh_ids = set(_pack_ids("my employer fired me after i complained to ICC about sexual harassment at office"))
    assert {"posh_2013", "industrial_disputes_1947"} <= posh_ids

    marriage_ids = set(_pack_ids("husband lied about salary and loans before marriage what can I do now"))
    assert {"hindu_marriage_1955_voidable", "special_marriage_1954_voidable", "family_courts_1984"} <= marriage_ids


def test_stage_e_hardfail_source_packs_are_available():
    ancestral_ids = set(_pack_ids(
        "pls tell father is hindu 78 yrs ancestral land sold by brother without consent madhya pradesh need lawyer or police"
    ))
    assert {"hindu_succession_1956", "hindu_succession_1956_section6_cases", "transfer_property_1882", "specific_relief_1963"} <= ancestral_ids

    writ_ids = set(_pack_ids(
        "urgent difference between Article 32 Supreme Court and Article 226 High Court writ how to complain"
    ))
    assert {"constitution_writ_32_226", "writ_mandamus_article226_cases", "legal_services_authorities_1987"} <= writ_ids

    health_ids = set(_pack_ids(
        "please help the man I am supposed to marry next month I found out hides he is HIV positive his family also knows can I cancel without dowry return issue any remedy"
    ))
    assert {"hiv_aids_2017", "hindu_marriage_1955_voidable", "family_courts_1984", "dowry_prohibition_1961"} <= health_ids


def test_stage_f_safety_blocker_source_packs_are_available():
    csam_query = "ai csam of my classmate someone made and shared in college telegram"
    csam_ids = set(_pack_ids(csam_query))
    assert {"it_act_2000", "pocso_2012", "bns_2023"} <= csam_ids
    csam_packs = {
        pack.id: pack
        for pack in source_packs_for_route(route_matter(csam_query), csam_query)
    }
    assert "/sec-67B" in csam_packs["it_act_2000"].anchor_patterns
    assert "bns_2023_child_sexual_image" in csam_packs
    assert "/sec-77" in csam_packs["bns_2023_child_sexual_image"].anchor_patterns

    for online_warning_q in (
        "engagement broken because he hid HIV can I post warning online",
        "engagement broken because he hid HIV can I warn people on Instagram",
        "engagement broken because he hid HIV can I put his HIV status on WhatsApp group",
    ):
        online_warning_ids = set(_pack_ids(online_warning_q))
        assert {
            "hiv_aids_2017",
            "hindu_marriage_1955_voidable",
            "it_act_2000_medical_privacy_online",
            "dpdp_2023_medical_privacy",
        } <= online_warning_ids

    mining_ids = set(_pack_ids("tribal village land taken for mining without consent gram sabha"))
    assert {"pesa_1996", "rfctlarr_2013_scheduled_area_rr", "mmdr_1957"} <= mining_ids


def test_stage_500_offtopic_review_source_packs_are_specific():
    esi_packs = source_packs_for_route(
        route_matter("ESI hospital refused to treat my wife for delivery saying my contributions are short"),
        "ESI hospital refused to treat my wife for delivery saying my contributions are short",
    )
    esi = next(pack for pack in esi_packs if pack.id == "esi_1948")
    assert {"/sec-46", "/sec-56", "/sec-58", "/sec-59", "/sec-75"} <= set(esi.anchor_patterns)

    accident_ids = set(_pack_ids(
        "i was driving and accidentally hit a pedestrian who is now claiming 8 lakh, my insurance is third party only"
    ))
    assert "motor_vehicles_1988" in accident_ids
    assert "food_safety_2006" not in accident_ids

    laptop_ids = set(_pack_ids(
        "my company laptop has been seized by police as part of investigation against my colleague"
    ))
    assert {"bnss_2023", "crpc_1973", "it_act_2000"} <= laptop_ids

    nclat_ids = set(_pack_ids("tribunal order against me how to appeal NCLAT format and fees"))
    assert {"ibc_2016", "companies_2013", "nclat_rules_2016"} <= nclat_ids

    nclt_ids = set(_pack_ids("operational creditor want to file section 9 ibc against company owing 2.5 cr"))
    assert {"ibc_2016", "nclt_rules_2016"} <= nclt_ids

    water_ids = set(_pack_ids("my borewell water has come bad neighbours factory throwing chemicals"))
    assert {"water_pollution_1974", "environment_protection_1986", "ngt_2010"} <= water_ids

    food_ids = set(_pack_ids("wrong delivery by Uber Eats gave me food poisoning hospital bill what can I do"))
    assert {"consumer_protection_2019", "food_safety_2006"} <= food_ids
    assert "clinical_establishments_2010" not in food_ids

    closure_ids = set(_pack_ids("factory closed sudden 80 of us tamil migrant no notice 2 months salary pending tiruppur"))
    assert {"industrial_disputes_1947_closure", "code_on_wages_2019_closure_arrears"} <= closure_ids

    food_deduction_ids = set(_pack_ids("contractor took rs 30 daily for food gave gruel only deducted from wages legal or not"))
    assert {"code_on_wages_2019_food_deduction", "ismw_1979_food_deduction"} <= food_deduction_ids

    conditional_posh_ids = set(_pack_ids(
        "i complained against my manager for harassment to HR and now they are putting me on PIP, is this retaliation"
    ))
    assert "industrial_disputes_1947" in conditional_posh_ids
    assert "posh_2013" in conditional_posh_ids


def test_stage3_state_gap_source_packs_cover_critical_ledger_rows():
    bhang_packs = _packs_by_id("vit student caught with bhang lassi in mahabaleshwar holi is it ndps")
    assert "ndps_1985" in bhang_packs
    assert "maharashtra_state_excise_prohibition_1949" in bhang_packs
    assert "official_summary" in bhang_packs["maharashtra_state_excise_prohibition_1949"].source_types
    assert bhang_packs["maharashtra_state_excise_prohibition_1949"].priority >= 1.35
    goa_bhang_packs = _packs_by_id("bhang lassi holi goa police caught is it ndps")
    assert "ndps_1985" in goa_bhang_packs
    assert "maharashtra_state_excise_prohibition_1949" not in goa_bhang_packs

    arrest_delay_ids = set(_pack_ids("papa arrest 5 din ho gaya magistrate ke samne kab le jana hota hai"))
    assert "navtej_lgbtq_liberty" not in arrest_delay_ids
    assert "constitution_article_22" in arrest_delay_ids

    lawyer_access_ids = set(_pack_ids("husband first time arrest jail superintendent not allowing lawyer meeting legal"))
    assert "constitution_article_22" in lawyer_access_ids
    assert "legal_services_authorities_1987" in lawyer_access_ids

    ap_packs = _packs_by_id("tehsildar transferred my baba land to bania without my consent agency area andhra")
    ap_ids = set(ap_packs)
    assert "ap_scheduled_areas_land_transfer_regulation_1959" in ap_ids
    assert "ap_scheduled_areas_land_transfer_case" in ap_ids
    assert "regulation" in ap_packs["ap_scheduled_areas_land_transfer_regulation_1959"].source_types

    odisha_packs = _packs_by_id("patwari changed mutation record giving my dadaji land to non tribal buyer nuapada odisha")
    odisha_ids = set(odisha_packs)
    assert "orissa_scheduled_areas_transfer_1956" in odisha_ids
    assert "odisha_scheduled_area_framework_sc" in odisha_ids
    assert "regulation" in odisha_packs["orissa_scheduled_areas_transfer_1956"].source_types

    witch_ids = set(_pack_ids("neighbours calling me witch want to throw me out of village chaibasa what law"))
    assert "jharkhand_witch_daain_2001" in witch_ids
    assert "jharkhand_witch_official_source_missing" not in witch_ids

    customs_packs = _packs_by_id("icegate showing bill of entry on hold misdeclaration alleged chinese led lights")
    assert "customs_1962" in customs_packs
    assert "customs_misdeclaration_1962" in customs_packs
    assert {"/sec-111", "/sec-112", "/sec-124"} <= set(customs_packs["customs_1962"].anchor_patterns)
    assert {"/sec-111", "/sec-112", "/sec-124"} <= set(customs_packs["customs_misdeclaration_1962"].anchor_patterns)

    svb_packs = _packs_by_id("customs reclassified my import wire harness higher duty 18% instead of 10% svb opened mumbai")
    assert "customs_1962" in svb_packs
    assert "customs_valuation_svb_1962" in svb_packs
    assert "/sec-14" in svb_packs["customs_1962"].anchor_patterns
    assert {"/sec-14", "/sec-17", "/sec-28", "/sec-128"} <= set(svb_packs["customs_valuation_svb_1962"].anchor_patterns)

    drawback_packs = _packs_by_id("drawback claim rejected by customs ngu shipping bill mismatched export incentive 9 lakh")
    assert "customs_1962" in drawback_packs
    assert "customs_drawback_1962" in drawback_packs
    assert {"/sec-75", "/sec-74", "/sec-27", "/sec-128"} <= set(drawback_packs["customs_drawback_1962"].anchor_patterns)


def test_customs_issue_packs_require_issue_terms_not_document_terms_only():
    bill_of_entry_packs = _packs_by_id("bill of entry assessment query no misdeclaration no penalty")
    assert "customs_1962" in bill_of_entry_packs
    assert "customs_misdeclaration_1962" not in bill_of_entry_packs

    shipping_bill_packs = _packs_by_id("shipping bill amendment wrong port code no drawback claim")
    assert "customs_1962" in shipping_bill_packs
    assert "customs_drawback_1962" not in shipping_bill_packs

    not_drawback_packs = _packs_by_id("shipping bill amendment not a drawback claim only port code correction")
    assert "customs_1962" in not_drawback_packs
    assert "customs_drawback_1962" not in not_drawback_packs

    not_penalty_packs = _packs_by_id("icegate bill of entry on hold not a penalty issue only assessment query")
    assert "customs_1962" in not_penalty_packs
    assert "customs_misdeclaration_1962" not in not_penalty_packs

    no_svb_packs = _packs_by_id("customs reclassified imported wire harness higher duty no svb opened")
    assert "customs_1962" in no_svb_packs
    assert "customs_valuation_svb_1962" not in no_svb_packs

    svb_no_customs_word = _packs_by_id("svb opened mumbai import invoice value rejected")
    assert "customs_1962" in svb_no_customs_word
    assert "customs_valuation_svb_1962" in svb_no_customs_word

    svb_not_related_party = _packs_by_id("svb opened but we are not related party declared value rejected by customs")
    assert "customs_valuation_svb_1962" in svb_not_related_party


def test_stage_500_post_review_source_packs_cover_quality_blockers():
    false_fir_ids = set(_pack_ids(
        "thekedar made fake theft fir against me after i asked wages now police calling station"
    ))
    assert {
        "code_on_wages_2019_false_fir_retaliation",
        "contract_labour_1970",
    } <= false_fir_ids
    assert "bnss_2023" in false_fir_ids and "bns_2023" in false_fir_ids

    muslim_ids = set(_pack_ids(
        "father says he is muslim 72 years his sons not giving share from grandfather property hyderabad"
    ))
    assert {
        "shariat_1937",
        "transfer_property_1882_coowner",
        "specific_relief_1963_declaration",
        "senior_citizens_2007",
    } <= muslim_ids

    trans_ids = set(_pack_ids(
        "I am transwoman my landlord threw me out after he found out he kept my deposit also where do I complain"
    ))
    assert {"transfer_property_1882", "transgender_2019_tenancy_discrimination"} <= trans_ids

    custody_ids = set(_pack_ids(
        "my brother beaten in lockup constable took 20000 for bail still not released"
    ))
    assert {"protection_human_rights_1993", "bnss_2023", "bns_2023"} <= custody_ids

    ola_ids = set(_pack_ids(
        "ola driver suspended id no reason 4000 rupees earning gone how to complaint"
    ))
    assert {
        "motor_vehicle_aggregator_guidelines_2020_contract",
        "motor_vehicle_aggregator_guidelines_2020_grievance",
        "motor_vehicles_1988_aggregator",
        "code_on_wages_2019",
    } <= ola_ids


def test_stage_e9c_source_gap_blockers_get_precise_source_pack_anchors():
    commercial = _packs_by_id(
        "urgent is pre-litigation mediation mandatory before filing commercial suit how to complain"
    )
    assert "commercial_courts_2015" in commercial
    assert {"/sec-12A", "/sec-12-a"} & set(commercial["commercial_courts_2015"].anchor_patterns)
    assert "mediation_2023" in commercial
    assert {"/sec-5", "/sec-6", "/sec-18", "/sec-19"} & set(commercial["mediation_2023"].anchor_patterns)

    ip_commercial = _packs_by_id(
        "amazon seller using my registered brand on fake items need commercial court injunction"
    )
    assert "commercial_courts_2015_ip_injunction" in ip_commercial
    assert {"/sec-12A", "/sec-12-a"} & set(
        ip_commercial["commercial_courts_2015_ip_injunction"].anchor_patterns
    )

    assessment = _packs_by_id(
        "sir got income tax notice under section 143(2) for AY 2023-24 how much time to respond"
    )
    assert "income_tax_1961" in assessment
    assert "/sec-143" in assessment["income_tax_1961"].anchor_patterns

    itat = _packs_by_id("urgent how to file appeal before ITAT against CIT Appeals order time limit")
    assert "income_tax_1961" in itat
    assert {"/sec-253", "/sec-254"} <= set(itat["income_tax_1961"].anchor_patterns)

    medical = _packs_by_id(
        "pls tell doctor gave wrong injection to my 82 year old mother she died compensation possible"
    )
    assert "clinical_establishments_2010" in medical
    assert "/sec-12" in medical["clinical_establishments_2010"].anchor_patterns

    mining = _packs_by_id(
        "can u tell mining company doing blasting next to village no gram sabha consent jharkhand west singhbhum"
    )
    assert "mmdr_1957" in mining
    assert {"/sec-4", "/sec-10A", "/sec-10-a", "/sec-11", "/sec-13"} & set(
        mining["mmdr_1957"].anchor_patterns
    )


def test_repair8_source_packs_cover_precise_common_routes():
    medical_ids = set(_pack_ids(
        "my mother died after wrong injection in private hospital, can we get compensation or file police case"
    ))
    assert "consumer_protection_2019" in medical_ids

    army_ids = set(_pack_ids(
        "army jawan husband passed away family pension not started which office and documents for widow"
    ))
    assert {
        "army_pension_regulations_2008_part_i",
        "army_pension_regulations_2008_part_ii",
    } <= army_ids

    trademark_ids = set(_pack_ids(
        "amazon seller using my registered brand on fake items, platform takedown not working what court route"
    ))
    assert {
        "trade_marks_1999",
        "trade_marks_1999_marketplace_infringement_forum",
    } <= trademark_ids

    prior_user_ids = set(_pack_ids(
        "competitor registered my brand name as trademark first but i am already using 6 years surat can i file case"
    ))
    assert {
        "trade_marks_1999_prior_user",
        "trade_marks_1999_forum_passing_off",
    } <= prior_user_ids

    marketplace_ip_ids = set(_pack_ids(
        "amazon delisted my product saying ip complaint how to file counter notice trademark wala"
    ))
    assert {
        "trade_marks_1999",
        "trade_marks_1999_marketplace_infringement_forum",
    } <= marketplace_ip_ids

    specific_performance_ids = set(_pack_ids(
        "want specific performance of land purchase deal seller backing out delhi commercial plot"
    ))
    assert {
        "specific_relief_1963_specific_performance",
        "indian_contract_1872_specific_performance",
    } <= specific_performance_ids
    assert "registration_1908_specific_performance" not in specific_performance_ids

    consumer_forum_packs = {
        pack.id: pack
        for pack in source_packs_for_route(
            route_matter("urgent consumer complain value 50 lakh which forum district state or national how to complain"),
            "urgent consumer complain value 50 lakh which forum district state or national how to complain",
        )
    }
    assert "consumer_protection_2019" in consumer_forum_packs
    assert "consumer_jurisdiction_rules_2021_district" in consumer_forum_packs
    assert "consumer_jurisdiction_rules_2021_state" in consumer_forum_packs
    assert "consumer_jurisdiction_rules_2021_national" in consumer_forum_packs
    assert {"/sec-34", "/sec-47", "/sec-58", "/sec-35"} <= set(
        consumer_forum_packs["consumer_protection_2019"].anchor_patterns
    )
    assert consumer_forum_packs["consumer_jurisdiction_rules_2021_district"].anchor_patterns == ("/rule-2",)
    assert consumer_forum_packs["consumer_jurisdiction_rules_2021_state"].anchor_patterns == ("/rule-3",)
    assert consumer_forum_packs["consumer_jurisdiction_rules_2021_national"].anchor_patterns == ("/rule-4",)

    ordinary_value_packs = {
        pack.id
        for pack in source_packs_for_route(
            route_matter("amazon order value 3000 phone damaged seller not refunding"),
            "amazon order value 3000 phone damaged seller not refunding",
        )
    }
    assert "consumer_jurisdiction_rules_2021_district" not in ordinary_value_packs
    assert "consumer_jurisdiction_rules_2021_state" not in ordinary_value_packs
    assert "consumer_jurisdiction_rules_2021_national" not in ordinary_value_packs

    copyright_ids = set(_pack_ids(
        "youtube struck my video for copyright but it was my own original song"
    ))
    assert "copyright_1957" in copyright_ids
    assert "copyright_1957_exceptions" in copyright_ids
    assert "copyright_1957_remedies" in copyright_ids
    assert "trade_marks_1999" not in copyright_ids
    assert "trade_marks_1999_marketplace_infringement_forum" not in copyright_ids

    copyright_reel_ids = set(_pack_ids(
        "fake influencer used my reel got 2M views without credit copyright bhai"
    ))
    assert {
        "copyright_1957",
        "copyright_1957_remedies",
    } <= copyright_reel_ids
    assert "trade_marks_1999" not in copyright_reel_ids

    paid_video_ids = set(_pack_ids(
        "telegram channel leaked my paid video content without permission how to take it down"
    ))
    assert {
        "copyright_1957",
        "copyright_1957_exceptions",
        "copyright_1957_remedies",
        "it_act_2000_intermediary",
    } <= paid_video_ids
    assert "trade_marks_1999" not in paid_video_ids

    remix_ids = set(_pack_ids(
        "i used 20 seconds of a bollywood song in my review video and got copyright strike what can i do"
    ))
    assert {
        "copyright_1957",
        "copyright_1957_exceptions",
        "copyright_1957_remedies",
    } <= remix_ids
    assert "trade_marks_1999" not in remix_ids

    execution_ids = set(_pack_ids(
        "money decree passed in my favour no payment since months, tell civil court procedure for attachment"
    ))
    assert "cpc_1908" in execution_ids

    confidentiality_ids = set(_pack_ids(
        "former sales manager using our confidential customer database after joining rival, what civil court remedy"
    ))
    assert {
        "indian_contract_1872_confidentiality",
        "specific_relief_1963_confidentiality_injunction",
    } <= confidentiality_ids

    noncompete_packs = {
        pack.id: pack
        for pack in source_packs_for_route(
            route_matter("employee joined competitor but no nda only non compete clause is it enforceable"),
            "employee joined competitor but no nda only non compete clause is it enforceable",
        )
    }
    assert "indian_contract_act_1872_restraint_trade" in noncompete_packs
    assert "/sec-27" in noncompete_packs["indian_contract_act_1872_restraint_trade"].anchor_patterns

    pollution_ids = set(_pack_ids(
        "nearby chemical factory polluting water, people want public interest litigation what is procedure"
    ))
    assert {"water_pollution_1974", "environment_protection_1986", "ngt_2010"} <= pollution_ids


def test_fresh_negative_neighbor_v2_source_slots_cover_controlling_law():
    expected = {
        "my 24 year old daughter left with boyfriend and parents want police to bring her home, what can we do": {
            "constitution_article_21",
            "bnss_2023_adult_choice_safety",
        },
        "i need free lawyer for consumer complaint against phone company, not criminal case, what papers": {
            "legal_services_authorities_1987",
            "constitution_legal_aid",
            "consumer_protection_2019_legal_aid",
        },
        "local boys broke my scooter mirror and police are delaying FIR calling it insurance issue": {
            "bnss_2023",
            "bns_2023",
            "crpc_1973",
        },
        "jail not giving psychiatric help for suicidal undertrial, can DLSA move court urgently": {
            "mental_healthcare_2017_custody_care",
            "constitution_article_21",
            "prisons_1894",
        },
        "contractor filed false theft FIR after workers demanded unpaid wages, should we go labour": {
            "bnss_2023_quashing",
            "crpc_1973_quashing",
            "code_on_wages_2019_false_fir_retaliation",
        },
        "delhi furlough rejected orally by authority what can family do": {
            "delhi_prison_rules_2018_parole_furlough",
            "prisons_1894",
        },
        "mandoli jail video mulaqat shows server error every week can wife ask written reason": {
            "delhi_prison_rules_2018_mulaqat_books",
            "prisons_1894",
        },
    }

    for query, required_ids in expected.items():
        ids = set(_pack_ids(query))
        assert required_ids <= ids, query

    damage_packs = {
        pack.id: pack
        for pack in source_packs_for_route(
            route_matter("local boys broke my scooter mirror and police are delaying FIR calling it insurance issue"),
            "local boys broke my scooter mirror and police are delaying FIR calling it insurance issue",
        )
    }
    assert {"/sec-324", "/sec-326"} & set(damage_packs["bns_2023"].anchor_patterns)


def test_stage2_worksite_death_retrieves_bocw_as_conditional_support():
    ids = set(_pack_ids("worker died at site and owner not giving compensation"))
    assert "employees_compensation_1923" in ids
    assert "bocw_1996" in ids


def test_patch15_succession_source_packs_prioritize_will_update_and_pre2005_coparcenary():
    will_query = "pls tell i registered my will in sub registrar pune do i need to update it every year need lawyer or police"
    will_packs = {
        pack.id: pack
        for pack in source_packs_for_route(route_matter(will_query), will_query)
    }
    assert "indian_succession_1925_will_update_revocation" in will_packs
    assert {"/sec-62", "/sec-70"} <= set(will_packs["indian_succession_1925_will_update_revocation"].anchor_patterns)

    daughter_query = "pls tell as a daughter am i coparcener in ancestral prop father died 2003 before amendment need lawyer or police"
    daughter_packs = {
        pack.id: pack
        for pack in source_packs_for_route(route_matter(daughter_query), daughter_query)
    }
    assert "hindu_succession_1956" in daughter_packs
    assert "/sec-6" in daughter_packs["hindu_succession_1956"].anchor_patterns
    assert daughter_packs["hindu_succession_1956"].priority >= 1.18


def test_stage3_refusal_probe_source_packs_cover_named_criminal_statutes():
    arms_query = "gadchiroli police put arms act because axe was in my farm jeep, what bail"
    arms_packs = _packs_by_id(arms_query)
    assert route_matter(arms_query).label == "Arms Act / farming-tool criminal defence"
    assert "arms_1959_farming_tool" in arms_packs
    assert "crpc_1973_arms_act_arrest_notice" in arms_packs
    assert {"/sec-2", "/sec-4", "/sec-25"} <= set(arms_packs["arms_1959_farming_tool"].anchor_patterns)

    moneylender_query = "moneylender took my thumb impression on blank paper now showing 5 lakh loan i never took"
    moneylender_packs = _packs_by_id(moneylender_query)
    assert "indian_contract_1872_free_consent_blank_paper" in moneylender_packs
    assert {"/sec-14", "/sec-17", "/sec-19"} <= set(moneylender_packs["indian_contract_1872_free_consent_blank_paper"].anchor_patterns)

    mcoca_query = "my brother is in MCOCA case 100 days custody no chargesheet can we file default bail"
    mcoca_packs = _packs_by_id(mcoca_query)
    assert route_matter(mcoca_query).label == "Default bail / no chargesheet"
    assert "mcoca_1999_default_bail" in mcoca_packs
    assert "/sec-21" in mcoca_packs["mcoca_1999_default_bail"].anchor_patterns

    chowk_query = "delhi labour chowk police picked workers saying begging, contractor also not paying wages"
    chowk_packs = _packs_by_id(chowk_query)
    assert "bnss_2023_labour_chowk_detention" in chowk_packs
    assert "crpc_1973_labour_chowk_detention" in chowk_packs

    false_498a_query = "wife filed false 498A and named my 70 years old mother and whole family"
    false_498a_packs = _packs_by_id(false_498a_query)
    assert "crpc_1973_498a_accused_bail_quashing" in false_498a_packs
    assert {"/sec-438", "/sec-482"} <= set(false_498a_packs["crpc_1973_498a_accused_bail_quashing"].anchor_patterns)


def test_source_packs_cover_stage4_source_gap_repair_prompts():
    legal_aid_query = "need help, i am poor brother arrested can court give free lawyer nalsa kya hota hai what next"
    legal_aid_packs = _packs_by_id(legal_aid_query)
    assert "constitution_legal_aid" in legal_aid_packs
    assert {"/sec-21", "/sec-22"} <= set(legal_aid_packs["constitution_legal_aid"].anchor_patterns)

    caste_school_query = (
        "urgent sarpanch from upper caste beat my son outside school called him "
        "untouchable name bastar how to complain"
    )
    caste_school_packs = _packs_by_id(caste_school_query)
    assert "bnss_2023" in caste_school_packs
    assert {"/sec-173", "/sec-175"} <= set(caste_school_packs["bnss_2023"].anchor_patterns)
    assert "rte_2009_school_punishment" in caste_school_packs

    old_deepfake_query = "someone made deepfake video of me on instagram in June 2024 and is extorting me"
    old_deepfake_packs = _packs_by_id(old_deepfake_query)
    assert "ipc_1860_intimate_image_blackmail" in old_deepfake_packs
    assert old_deepfake_packs["ipc_1860_intimate_image_blackmail"].anchor_patterns == ("/sec-384",)
    assert "crpc_1973_cyber_blackmail_fir" in old_deepfake_packs
    assert {"/sec-154", "/sec-156", "/sec-200"} <= set(old_deepfake_packs["crpc_1973_cyber_blackmail_fir"].anchor_patterns)
    assert "bns_2023_intimate_image_blackmail" not in old_deepfake_packs

    pre_cutover_packs = _packs_by_id(
        "someone made deepfake video of me on instagram before 1 July 2024 and is extorting me"
    )
    assert "ipc_1860_intimate_image_blackmail" in pre_cutover_packs
    assert "crpc_1973_cyber_blackmail_fir" in pre_cutover_packs
    assert "bns_2023_intimate_image_blackmail" not in pre_cutover_packs

    numeric_pre_cutover_packs = _packs_by_id(
        "someone made deepfake video of me on instagram before 01/07/2024 and is extorting me"
    )
    assert "ipc_1860_intimate_image_blackmail" in numeric_pre_cutover_packs
    assert "crpc_1973_cyber_blackmail_fir" in numeric_pre_cutover_packs
    assert "bns_2023_intimate_image_blackmail" not in numeric_pre_cutover_packs

    current_deepfake_query = "someone made deepfake video of me on instagram in 2025 and is extorting me"
    current_deepfake_packs = _packs_by_id(current_deepfake_query)
    assert "bns_2023_intimate_image_blackmail" in current_deepfake_packs
    assert current_deepfake_packs["bns_2023_intimate_image_blackmail"].anchor_patterns == ("/sec-308",)
    assert "bnss_2023" in current_deepfake_packs
    assert "ipc_1860_intimate_image_blackmail" not in current_deepfake_packs

    negated_extortion_query = (
        "someone made deepfake video of me on instagram in 2025 no extortion just threatening to share"
    )
    negated_extortion_packs = _packs_by_id(negated_extortion_query)
    assert "bns_2023_intimate_image_blackmail" in negated_extortion_packs
    assert "/sec-308" not in negated_extortion_packs["bns_2023_intimate_image_blackmail"].anchor_patterns
    assert {"/sec-77", "/sec-351", "/sec-356"} <= set(
        negated_extortion_packs["bns_2023_intimate_image_blackmail"].anchor_patterns
    )

    hospital_query = "i am confused hospital in chennai operated wrong leg on my 80 yr old father how to file case pls guide"
    hospital_packs = _packs_by_id(hospital_query)
    assert "medical_ethics_2002" in hospital_packs
    assert "clinical_establishments_2010" not in hospital_packs

    bail_query = "need help, father bail filed magistrate court ipc 376 rape case why direct to sessions court what next"
    bail_packs = _packs_by_id(bail_query)
    assert "crpc_1973" in bail_packs
    assert {"/sec-437", "/sec-439"} <= set(bail_packs["crpc_1973"].anchor_patterns)
    assert "/sec-57" not in bail_packs["crpc_1973"].anchor_patterns

    pmla_query = "pmla case ED filed twin condition kya hai how to argue not guilty"
    pmla_packs = _packs_by_id(pmla_query)
    assert "pmla_2002" in pmla_packs
    assert "bnss_2023_pmla_bail" in pmla_packs
    assert "pmla_sc_precedents" in pmla_packs
    assert {"/sec-480", "/sec-483"} <= set(pmla_packs["bnss_2023_pmla_bail"].anchor_patterns)

    fra_query = "urgent i am gond woman my husband died forest officer not giving me IFR title dindori how to complain"
    fra_packs = _packs_by_id(fra_query)
    assert "fra_2006" in fra_packs
    assert "pesa_1996" in fra_packs


def test_source_packs_do_not_inject_new_criminal_law_for_legacy_dates():
    dated_cyber_ids = set(_pack_ids("in 2020 otp fraud took 2 lakh from my bank account police not helping"))
    assert not any(pack_id.startswith("bns_2023") or pack_id.startswith("bnss_2023") for pack_id in dated_cyber_ids)
    assert "crpc_1973" in dated_cyber_ids

    dated_domestic_ids = set(_pack_ids("in 2020 husband forced sex and beat me what case can file"))
    assert not any(pack_id.startswith("bns_2023") or pack_id.startswith("bnss_2023") for pack_id in dated_domestic_ids)
    assert "crpc_1973" in dated_domestic_ids


def test_source_packs_do_not_trigger_mgnrega_from_bare_panchayat_wage_words():
    assert "mgnrega_2005" not in _pack_ids("panchayat secretary not paying my salary")
    assert "mgnrega_2005" not in _pack_ids("gram panchayat contractor not paying construction workers wages")
    assert "mgnrega_2005" in _pack_ids("gram panchayat not giving work under mgnrega after application")


def test_jharkhand_tribal_land_pack_targets_cnt_section_46():
    packs = _packs_by_id("munda land grabbed by upper caste in our agency village how to get back chaibasa")
    assert "chota_nagpur_tenancy_1908_transfer_restriction" in packs
    assert "sec-46" in packs["chota_nagpur_tenancy_1908_transfer_restriction"].anchor_patterns

    ap_packs = _packs_by_id(
        "tehsildar transferred my baba land to bania without my consent agency area andhra"
    )
    assert "ap_scheduled_areas_land_transfer_regulation_1959" in ap_packs
    assert "secondary_reference" in ap_packs["ap_scheduled_areas_land_transfer_regulation_1959"].source_types
    assert ap_packs["ap_scheduled_areas_land_transfer_regulation_1959"].priority >= 1.35

    odisha_packs = _packs_by_id(
        "patwari changed mutation record giving my dadaji land to non tribal buyer nuapada odisha"
    )
    assert "orissa_scheduled_areas_transfer_1956" in odisha_packs
    assert "official_summary" in odisha_packs["orissa_scheduled_areas_transfer_1956"].source_types
    assert odisha_packs["orissa_scheduled_areas_transfer_1956"].priority >= 1.35


def test_stage_e9e_source_packs_cover_common_source_gap_repairs():
    gst_packs = _packs_by_id(
        "rule 86B applies to me turnover 55 lakh per month must pay 1 percent cash mandatory"
    )
    assert "cgst_rules_2017" in gst_packs
    assert "/rule-86B" in gst_packs["cgst_rules_2017"].anchor_patterns
    assert "/sec-85" in gst_packs["cgst_rules_2017"].anchor_patterns
    assert gst_packs["cgst_rules_2017"].priority >= 1.28

    esi_packs = _packs_by_id(
        "esi inspector sent notice contribution short by 1.2 lakh for casual workers can i contest"
    )
    assert "social_security_code_2020" in esi_packs
    assert "/sec-31" in esi_packs["social_security_code_2020"].anchor_patterns

    workplace_packs = _packs_by_id(
        "my boss keeps asking late night meetings alone and touched my back twice should i file POSH"
    )
    assert "posh_2013" in workplace_packs
    assert "bns_2023_workplace_sexual_contact_threat" in workplace_packs
    assert {"/sec-74", "/sec-75", "/sec-78", "/sec-351"} <= set(
        workplace_packs["bns_2023_workplace_sexual_contact_threat"].anchor_patterns
    )

    logo_packs = _packs_by_id(
        "got cease and desist notice from big company saying my logo similar to theirs delhi exporter"
    )
    assert "trade_marks_1999" in logo_packs
    assert "copyright_1957_logo_creative_work" in logo_packs

    hospital_packs = _packs_by_id(
        "hospital operated wrong leg on my 80 yr old father how to file case"
    )
    assert "clinical_establishments_2010" in hospital_packs
    assert hospital_packs["clinical_establishments_2010"].priority >= 1.48
    assert "bns_2023_medical_negligence_track" in hospital_packs
    assert "bnss_2023_medical_negligence_complaint" in hospital_packs

    mining_packs = _packs_by_id(
        "iron ore mine displaced our 12 villages no rehabilitation given keonjhar"
    )
    assert "pesa_1996" in mining_packs

    bonded_packs = _packs_by_id(
        "bonded labour my chacha working for thakur 12 years no wages just food bihar"
    )
    assert "code_on_wages_2019" in bonded_packs
    assert {"/sec-17", "/sec-45"} <= set(bonded_packs["code_on_wages_2019"].anchor_patterns)


def test_stage_e9f_source_packs_cover_remaining_source_gap_repairs():
    ndps_packs = _packs_by_id(
        "ndps bail rejected 6 times by session court husband 3 yrs in tihar option what next"
    )
    assert "bnss_2023_ndps_bail_custody" in ndps_packs
    assert "crpc_1973_ndps_bail_custody" in ndps_packs
    assert {"/sec-480", "/sec-483"} <= set(
        ndps_packs["bnss_2023_ndps_bail_custody"].anchor_patterns
    )
    assert {"/sec-437", "/sec-439"} <= set(
        ndps_packs["crpc_1973_ndps_bail_custody"].anchor_patterns
    )

    personal_ndps_packs = _packs_by_id(
        "brother arrested ndps 5 gram personal use how is small quantity proven what next"
    )
    assert "bnss_2023_ndps_bail_custody" in personal_ndps_packs
    assert "crpc_1973_ndps_bail_custody" in personal_ndps_packs

    spa_packs = _packs_by_id(
        "I work at a place in malad they call it spa but customers want extra and owner makes us do it if we refuse no salary how do I get out"
    )
    assert "itpa_1956_forced_sexual_exploitation_victim" in spa_packs
    assert "bns_2023_forced_sexual_exploitation_victim" in spa_packs
    assert "bnss_2023_forced_sexual_exploitation_complaint" in spa_packs

    passing_off_packs = _packs_by_id(
        "urgent interim injunction needed competitor passing off my product packaging can i skip 12A can i file case"
    )
    assert "commercial_courts_2015_ip_injunction" in passing_off_packs
    assert "specific_relief_1963_ip_injunction" in passing_off_packs
    assert passing_off_packs["commercial_courts_2015_ip_injunction"].priority >= 1.34
    assert {"/sec-12A", "/sec-12-a"} & set(
        passing_off_packs["commercial_courts_2015_ip_injunction"].anchor_patterns
    )
    assert {"/sec-38", "/sec-39"} <= set(
        passing_off_packs["specific_relief_1963_ip_injunction"].anchor_patterns
    )

    mtp_packs = _packs_by_id(
        "had abortion 5 yrs back husband found out and is threatening divorce can he use this against me in court"
    )
    assert "mtp_reproductive_autonomy_sc_precedents" in mtp_packs

    bonded_escape_packs = _packs_by_id(
        "thekedar took 18000 advance from me darbhanga not letting leave bangalore site is this legal"
    )
    assert "bns_2023_bonded_labour_confinement" in bonded_escape_packs
    assert "bnss_2023_bonded_labour_fir_protection" in bonded_escape_packs

    writ_packs = _packs_by_id(
        "urgent difference between Article 32 Supreme Court and Article 226 High Court writ how to complain"
    )
    assert "constitution_article_32_writ" in writ_packs
    assert "/sec-32" in writ_packs["constitution_article_32_writ"].anchor_patterns


@pytest.mark.parametrize(
    "query",
    (
        "My stolen bike FIR ki jaanch chal rahi hai, but police refuse to give the case diary update",
        "The stolen-car FIR remains pending investigation; the SHO refuses to tell me the current stage",
        "My stolen bike has an FIR receipt, but police refuse to chase the thieves",
        "The vehicle theft FIR was assigned to an IO, but police refuse to follow up",
        "Police gave me crime number 48 but refuse to trace my stolen scooter",
        "My stolen scooter case is C.R. 22 and police refuse further action",
        "The theft case for my scooter is under Crime No 22; police refuse to search for it",
    ),
)
def test_existing_vehicle_theft_fir_uses_investigation_not_registration_packs(query: str):
    route = route_matter(query)
    packs = source_packs_for_route(route, query)
    pack_ids = {pack.id for pack in packs}

    assert "bnss_2023_vehicle_theft_fir" not in pack_ids
    assert "crpc_1973_vehicle_theft_fir" not in pack_ids
    assert "bnss_2023_vehicle_theft_investigation" in pack_ids
    assert "crpc_1973_vehicle_theft_investigation" in pack_ids

    current = next(pack for pack in packs if pack.id == "bnss_2023_vehicle_theft_investigation")
    legacy = next(pack for pack in packs if pack.id == "crpc_1973_vehicle_theft_investigation")
    assert current.anchor_patterns == ("/sec-175",)
    assert legacy.anchor_patterns == ("/sec-156",)
    generic_current = next(pack for pack in packs if pack.id == "bnss_2023")
    generic_legacy = next(pack for pack in packs if pack.id == "crpc_1973")
    assert generic_current.anchor_patterns == ("/sec-175",)
    assert generic_legacy.anchor_patterns == ("/sec-156",)


@pytest.mark.parametrize(
    "query",
    (
        "My stolen bike case not registered; police refused to lodge the FIR",
        "There is no crime number because police will not register my stolen motorcycle FIR",
        "Police refused to register the stolen car case; no crime number has been assigned",
        "No FIR was registered for my stolen car because police refused my complaint",
        "Police said no FIR registered for my stolen bike and turned me away",
        "There is no FIR number because police refused to register my stolen car",
        "An FIR number is yet to be allotted because police refused my stolen-car complaint",
        "Police have not assigned any FIR number for my stolen motorcycle and refuse to register it",
        "The FIR number remains unallotted because police rejected my stolen-bike complaint",
        "Police haven't assigned an FIR number for my stolen scooter and refuse to lodge it",
        "My stolen car FIR number is still pending allotment because the station turned me away",
        "The FIR number has yet to be generated for my stolen motorcycle because police refused registration",
    ),
)
def test_negated_vehicle_case_identifiers_keep_fir_registration_packs(query: str):
    route = route_matter(query)
    pack_ids = {pack.id for pack in source_packs_for_route(route, query)}

    assert "bnss_2023_vehicle_theft_fir" in pack_ids
    assert "crpc_1973_vehicle_theft_fir" in pack_ids
    assert "bnss_2023_vehicle_theft_investigation" not in pack_ids
    assert "crpc_1973_vehicle_theft_investigation" not in pack_ids
