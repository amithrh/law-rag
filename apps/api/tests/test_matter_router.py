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


def test_routes_off_topic():
    route = route_matter("recipe for biryani")
    assert route.category == "off_topic"
    assert route.action_pack is None


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
