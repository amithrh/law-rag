from __future__ import annotations

from apps.api.matter_router import route_matter


def test_routes_fir_and_marks_regime_unknown_without_incident_date():
    route = route_matter("police refused to register FIR for theft of my bike")
    assert route.category == "police_fir"
    assert "police station" in route.forums
    assert route.legal_regime == "incident_date_needed_for_bns_bnss_bsa_vs_ipc_crpc"
    assert any("BNSS" in source for source in route.required_sources)


def test_routes_cyber_money_loss_as_emergency():
    route = route_matter("credit card fraud online transaction unauthorized lost money")
    assert route.category == "cyber_fraud_or_harassment"
    assert route.urgency == "emergency"
    assert route.action_pack is not None
    assert "cybercrime.gov.in" in route.action_pack.portals


def test_routes_consumer_with_action_pack():
    route = route_matter("online order broken refund company not responding")
    assert route.category == "consumer"
    assert route.action_pack is not None
    assert route.action_pack.id == "consumer"
    assert any("Consumer Protection Act" in source for source in route.required_sources)


def test_criminal_legacy_regime_for_old_incident_year():
    route = route_matter("false ipc 420 cheating case from 2020 can i get bail")
    assert route.category == "criminal_defence_bail"
    assert route.legal_regime == "legacy_ipc_crpc_evidence_for_pre_2024_incident"


def test_mixed_criminal_dates_require_regime_clarification():
    for query in (
        "arrested in 2025 for FIR from 2023 90 days no chargesheet default bail",
        "FIR from 2023 arrested in 2025 90 days no chargesheet default bail",
    ):
        route = route_matter(query)
        assert route.category == "criminal_defence_bail"
        assert route.legal_regime == "incident_date_needed_for_bns_bnss_bsa_vs_ipc_crpc"


def test_routes_off_topic():
    route = route_matter("recipe for biryani")
    assert route.category == "off_topic"
    assert route.action_pack is None


def test_routes_obvious_non_legal_recommendations_off_topic():
    for query in (
        "recommend a laptop under 60000 for gaming",
        "who won yesterday cricket match india pakistan",
        "write python code for quicksort in javascript style",
    ):
        route = route_matter(query)
        assert route.category == "off_topic", query
        assert route.action_pack is None


def test_legal_queries_with_off_topic_words_still_route_legally():
    assert route_matter("my laptop under warranty stopped working seller refuses refund").category == "consumer"
    assert route_matter("javascript code copied by competitor what copyright claim can I file").category == "trademark_ip"


def test_first_does_not_trigger_fir_and_routes_trademark():
    route = route_matter("competitor registered my brand name as trademark first what can I do")
    assert route.category == "trademark_ip"
    assert route.action_pack is not None
    assert route.action_pack.id == "trademark_ip"
    assert "Trade Marks Act 1999" in route.required_sources


def test_routes_intimate_recording_threat_as_cyber_emergency():
    route = route_matter("bf secretly recorded us during sex now threatening to upload")
    assert route.category == "cyber_fraud_or_harassment"
    assert route.urgency == "emergency"
    assert route.action_pack is not None


def test_routes_private_photo_parent_threat_as_cyber_emergency():
    route = route_matter("ex boyfriend has private photos and says he will send to my parents")
    assert route.category == "cyber_fraud_or_harassment"
    assert route.urgency == "emergency"
    assert route.action_pack is not None
    assert route.legal_regime == "incident_date_needed_for_bns_bnss_bsa_vs_ipc_crpc"


def test_intimate_image_share_show_forward_variants_route_cyber():
    for query in (
        "ex boyfriend says he will send my nudes to my parents",
        "ex boyfriend says he will share my nudes with my parents",
        "ex boyfriend says he will show my private photos to my parents",
        "ex boyfriend will forward my intimate photos in college group",
        "ex has my nudes what can i do",
        "stranger has my nude photos and found my instagram",
    ):
        route = route_matter(query)
        assert route.category == "cyber_fraud_or_harassment", query
        assert route.urgency == "emergency"


def test_private_photos_without_abuse_context_do_not_become_cyber_emergency():
    route = route_matter("wedding photographer lost my private photos and refuses refund")
    assert route.category == "consumer"
    assert route.urgency != "emergency"


def test_family_photographer_private_photo_refund_stays_consumer():
    route = route_matter("family photographer lost my private photos and refuses refund")
    assert route.category == "consumer"
    assert route.urgency != "emergency"


def test_intimate_image_service_disputes_do_not_become_cyber():
    for query in (
        "wedding photographer lost my intimate photos and refuses refund",
        "wedding photographer lost my nude photos and refuses refund",
        "family photographer lost my intimate video and refuses refund",
        "graphic designer made morphed photos badly and refuses refund",
    ):
        route = route_matter(query)
        assert route.category == "consumer", query
        assert route.urgency != "emergency"


def test_routes_tribal_caste_targeted_violence():
    route = route_matter("mob attacked our pahan during sarna puja calling adivasi non hindu")
    assert route.category == "tribal_caste_atrocity"
    assert route.urgency == "emergency"
    assert any("Atrocities" in source for source in route.required_sources)


def test_routes_land_records_revenue_issue():
    route = route_matter("pattadar passbook lost in flood tehsildar saying come next month")
    assert route.category == "land_revenue_records"
    assert route.action_pack is not None
    assert "tehsildar/taluk/revenue office" in route.forums


def test_routes_court_procedure_question():
    route = route_matter("how do I address the judge in district court your honour or my lord")
    assert route.category == "court_procedure"
    assert route.urgency == "low"


def test_routes_maintenance_cheque_as_cheque_bounce_before_family():
    route = route_matter("son gave me cheque for monthly maintenance it bounced twice can i file")
    assert route.category == "cheque_bounce"
    assert route.action_pack is not None
    assert route.action_pack.id == "cheque_bounce"


def test_routes_construction_site_injury_as_work_compensation():
    route = route_matter("fell from 5th floor construction site leg broken thekedar saying no compensation")
    assert route.category == "workplace_injury_compensation"
    assert route.urgency == "high"
    assert any("Employees Compensation Act" in source for source in route.required_sources)


def test_routes_anticipatory_bail_in_dowry_case_as_criminal_defence():
    route = route_matter("anticipatory bail in dowry case husband family how many days valid")
    assert route.category == "criminal_defence_bail"
    assert route.legal_regime == "incident_date_needed_for_bns_bnss_bsa_vs_ipc_crpc"
    assert route.action_pack is not None


def test_routes_mcoca_custody_limit_as_criminal_defence_not_family():
    route = route_matter("brother in jail 60 days completed maharashtra mcoca what is custody limit chargesheet")
    assert route.category == "criminal_defence_bail"
    assert route.legal_regime == "incident_date_needed_for_bns_bnss_bsa_vs_ipc_crpc"
    assert route.action_pack is not None


def test_routes_ndps_and_uapa_default_bail_as_bail_procedure():
    for query in (
        "brother in NDPS case arrested 110 days no chargesheet default bail possible",
        "brother arrested in UAPA 100 days no chargesheet default bail possible",
    ):
        route = route_matter(query)
        assert route.category == "criminal_defence_bail", query
        assert route.urgency == "high"
        assert route.action_pack is not None


def test_routes_section_91_phone_notice_to_criminal_procedure():
    route = route_matter("police sent section 91 notice asking for my phone and whatsapp chats what to do")
    assert route.category == "criminal_procedure_notice"
    assert route.urgency == "high"
    assert route.action_pack is not None
    assert "BNSS 2023 section 94" in route.required_sources[1]


def test_routes_passport_police_verification_to_passport_procedure():
    route = route_matter("passport police verification adverse report because old criminal case what remedy")
    assert route.category == "passport_police_verification"
    assert route.action_pack is not None
    assert any("Passports Act" in source for source in route.required_sources)


def test_contractor_kept_worker_passports_stays_labour_exploitation():
    route = route_matter("contractor taking us to other state for work keeping our cards passport")
    assert route.category == "labour_exploitation_discrimination"
    assert route.urgency == "high"


def test_routes_lok_adalat_award_challenge():
    route = route_matter("lok adalat award passed without my consent can I challenge it")
    assert route.category == "lok_adalat_award_challenge"
    assert route.action_pack is not None
    assert any("section 21" in source.lower() for source in route.required_sources)


def test_routes_migrant_return_ticket_issue_as_labour_exploitation():
    route = route_matter("contractor said go back home pandemic no return ticket money given we walked from delhi")
    assert route.category == "labour_exploitation_discrimination"
    assert route.action_pack is not None


def test_routes_aadhaar_pension_identity_mismatch():
    route = route_matter("aadhaar number showing someone else photo cannot get pension help")
    assert route.category == "social_welfare_identity"
    assert route.action_pack is not None
    assert any("Aadhaar Act" in source for source in route.required_sources)


def test_routes_sc_scholarship_denial():
    route = route_matter("school principal not giving SC scholarship saying papers wrong since 2 months")
    assert route.category == "social_welfare_identity"
    assert "district social welfare office" in route.forums


def test_routes_rape_survivor_police_response_as_emergency():
    route = route_matter("my visually impaired sister was raped by her caretaker the police said no FIR")
    assert route.category == "sexual_offence_survivor"
    assert route.urgency == "emergency"
    assert route.legal_regime == "incident_date_needed_for_bns_bnss_bsa_vs_ipc_crpc"
    assert route.action_pack is not None


def test_routes_minor_tuition_teacher_pocso_complaint_as_emergency():
    route = route_matter("minor daughter touched by tuition teacher how to file pocso complaint")
    assert route.category == "sexual_offence_survivor"
    assert route.urgency == "emergency"
    assert route.action_pack is not None


def test_tuition_teacher_fee_dispute_is_not_sexual_offence():
    route = route_matter("tuition teacher took advance fees and stopped classes")
    assert route.category != "sexual_offence_survivor"
    assert route.urgency != "emergency"


def test_false_rape_bail_stays_criminal_defence():
    route = route_matter("false rape case against me from 2020 need bail")
    assert route.category == "criminal_defence_bail"
    assert route.legal_regime == "legacy_ipc_crpc_evidence_for_pre_2024_incident"


def test_routes_prison_parole_question():
    route = route_matter("uncle in jail 4 yrs murder case eligible for parole 15 days delhi")
    assert route.category == "prison_parole_furlough"
    assert route.action_pack is not None
    assert "prison superintendent" in route.forums


def test_routes_workplace_sexual_harassment():
    route = route_matter("my boss keeps asking me to come for late night meetings alone and touches me")
    assert route.category == "workplace_sexual_harassment"
    assert route.urgency == "high"
    assert route.action_pack is not None
    assert any("POSH Act" in source for source in route.required_sources)


def test_routes_pregnancy_after_rape_as_reproductive_rights_emergency():
    route = route_matter("I am 6 months pregnant after rape doctor says it is too late for abortion")
    assert route.category == "reproductive_rights_mtp"
    assert route.urgency == "emergency"
    assert route.action_pack is not None
    assert any("Medical Termination" in source for source in route.required_sources)


def test_routes_numeric_age_elder_eviction():
    route = route_matter("my son and daughter in law threw me out of my own house I am 72 widow")
    assert route.category == "senior_citizen"
    assert route.urgency == "high"


def test_routes_parent_gift_transfer_neglect_to_senior_citizen():
    route = route_matter("my father gifted flat to my brother but now brother stopped giving food can gift be cancelled")
    assert route.category == "senior_citizen"
    assert any("Senior Citizens Act" in source for source in route.required_sources)


def test_age_alone_does_not_steal_inheritance_route():
    route = route_matter("father says he is muslim 72 years his sons not giving share from grandfather property")
    assert route.category == "succession_inheritance"


def test_copyright_song_is_not_off_topic():
    route = route_matter("youtube struck my video for copyright but it was my own original song")
    assert route.category == "trademark_ip"


def test_routes_gst_tax_question():
    route = route_matter("freelance designer 18 lakh income should i register gst or no")
    assert route.category == "tax_gst_compliance"
    assert route.action_pack is not None


def test_routes_ibc_nclt_question():
    route = route_matter("operational creditor want to file section 9 ibc against company owing 2.5 cr")
    assert route.category == "ibc_nclt"
    assert "NCLT" in route.forums


def test_routes_business_partnership_contract():
    route = route_matter("want to retire from partnership but firm has 80 lakh loan personal liability")
    assert route.category == "business_contract_partnership"
    assert any("Partnership Act" in source for source in route.required_sources)


def test_routes_labour_exploitation_and_nrega():
    route = route_matter("nrega 28 days work done village mukhiya not paid since 6 months")
    assert route.category == "labour_exploitation_discrimination"
    route2 = route_matter("contractor taking us to other state for work keeping our cards passport")
    assert route2.category == "labour_exploitation_discrimination"
    assert route2.urgency == "high"


def test_routes_education_rights():
    route = route_matter("private school refusing admission under 25 percent RTE quota")
    assert route.category == "education_rights"
    assert any("Right of Children" in source for source in route.required_sources)


def test_routes_child_adoption_and_return():
    route = route_matter("we adopted child from sister but no papers now real parents want him back")
    assert route.category == "child_custody_adoption"
    route2 = route_matter("my ex husband took our son to UK on tourist visa and is not bringing back")
    assert route2.category == "child_custody_adoption"
    assert route2.urgency == "high"


def test_routes_environmental_damage():
    route = route_matter("thermal plant blasting cracking our houses no compensation kalahandi")
    assert route.category == "environment_compensation"
    assert route.action_pack is not None


def test_routes_pmla_ed():
    route = route_matter("pmla case ED filed twin condition kya hai how to argue not guilty")
    assert route.category == "pmla_ed"
    assert route.urgency == "high"


def test_routes_banking_credit_dispute():
    route = route_matter("personal loan tenure ended but bank not giving NOC still active in CIBIL")
    assert route.category == "banking_credit_dispute"
    assert "RBI Ombudsman" in route.forums


def test_routes_mental_health_care_rights():
    route = route_matter("my brother mentally ill family kept him in chains how to admit in hospital legally")
    assert route.category == "mental_health_care_rights"
    assert route.urgency == "high"


def test_routes_platform_account_dispute():
    route = route_matter("blue trunks app froze my account showing kyc pending stuck 80k")
    assert route.category == "digital_platform_account"
    assert route.urgency == "high"


def test_routes_business_license_renewal():
    route = route_matter("tamil nadu shop license renewal pending 2 years coimbatore shopkeeper penalty")
    assert route.category == "business_license_compliance"
    assert route.action_pack is not None


def test_routes_posh_retaliation_after_icc_complaint():
    route = route_matter("after I complained to ICC against my reporting manager he is now giving me bad rating and PIP")
    assert route.category == "workplace_sexual_harassment"


def test_routes_fra_ifr_title_for_gond_widow():
    route = route_matter("i am gond woman my husband died forest officer not giving me IFR title dindori")
    assert route.category == "tribal_caste_atrocity"


def test_routes_forest_minor_produce_to_tribal_rights():
    route = route_matter("forest officer stopped us collecting tendu leaves in community forest")
    assert route.category == "tribal_caste_atrocity"


def test_generic_forest_vehicle_seizure_does_not_route_to_tribal_rights():
    route = route_matter("forest officer seized my truck for timber transport")
    assert route.category != "tribal_caste_atrocity"


def test_routes_dlsa_query_to_legal_aid_before_family():
    route = route_matter("free legal aid for woman domestic violence case how to apply in dlsa")
    assert route.category == "legal_aid"


def test_urgent_domestic_violence_with_dlsa_stays_family_safety():
    route = route_matter("my husband is beating me need free legal aid in dlsa")
    assert route.category == "family_domestic"
    assert route.urgency == "emergency"
    assert route.red_flags


def test_domestic_threats_with_dlsa_stay_family_safety():
    route = route_matter("my husband threatens me need free legal aid in dlsa")
    assert route.category == "family_domestic"
    assert route.urgency == "emergency"
    assert route.red_flags


def test_family_safety_variants_with_dlsa_stay_family_safety():
    for query in (
        "my husband locked me in room need free legal aid in dlsa",
        "my husband hit me need free legal aid in dlsa",
        "my wife is beating me need free legal aid in dlsa",
        "my husband is not giving food need free lawyer dlsa",
        "my husband threw me out need free legal aid in dlsa",
    ):
        route = route_matter(query)
        assert route.category == "family_domestic", query
        assert route.urgency == "emergency"
        assert route.red_flags
