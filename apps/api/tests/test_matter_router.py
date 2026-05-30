from __future__ import annotations

from apps.api.matter_router import route_matter


def _has_text(values: list[str], needle: str) -> bool:
    return any(needle.lower() in value.lower() for value in values)


def test_routes_fir_and_marks_regime_unknown_without_incident_date():
    route = route_matter("police refused to register FIR for theft of my bike")
    assert route.category == "police_fir"
    assert "police station" in route.forums
    assert route.legal_regime == "incident_date_needed_for_bns_bnss_bsa_vs_ipc_crpc"
    assert any("BNSS" in source for source in route.required_sources)


def test_priority_routes_final_eval_hard_fail_prompts():
    cases = {
        "husband in arthur road tb test not done jail doctor 4 months waiting": "criminal_defence_bail",
        "sasural waale mujhe ghar se nikal diya raat ko bina kuch diye kya main wapis ja sakti hoon": "family_domestic",
        "binance froze my usdt wallet 4 lakh saying suspicious trade is it legal": "digital_platform_account",
        "my wife filed 498A on whole family even my old mother how to defend": "criminal_defence_bail",
        "stranger on bumble sent me dick pic without consent is there any law for this in india": "cyber_fraud_or_harassment",
        "client cheque of 2 lakh bounced for my logo work how to send notice": "cheque_bounce",
        "son took loan against my house i didn't sign told bank to stop ahmedabad": "criminal_general",
        "private limited mgt 7 aoc 4 not filed 3 years director disqualified can revive": "ibc_nclt",
        "ngo helping us said mukhiya did fake job cards no action by collector": "labour_exploitation_discrimination",
        "I work at a place in malad they call it spa but customers want extra and owner makes us do it if we refuse no salary how": "criminal_general",
        "garment unit jharkhand girl 15 working with us factory says she is 18 no proof": "labour_exploitation_discrimination",
        "lost 50k on dream11 like app is online rummy legal in tamil nadu": "digital_platform_account",
        "private cooperative bank fd of grandfather not honoured nominee facing harassment": "banking_credit_dispute",
        "moneylender took my thumb impression on blank paper now showing 5 lakh loan I never took": "criminal_general",
        "fssai notice mismatch in licence category for snack manufacturing renewal due how to upgrade state to central": "business_license_compliance",
        "neighbours calling me witch want to throw me out of village chaibasa what law": "police_fir",
        "former employee joined competitor and is using our customer list, NDA was signed how to enforce": "business_contract_partnership",
        "my 14 year old girlfriend's father filed pocso on me I am 17 we were in relationship she came on her own": "criminal_defence_bail",
        "my husband died 2024 i am 78 mutation of land in my name jharkhand process": "land_revenue_records",
        "section 80C limit 1.5 lakh can i also claim 80CCD(1B) additional 50000 for NPS together": "tax_gst_compliance",
        "someone leaked my chat with therapist on twitter mental health privacy": "cyber_fraud_or_harassment",
        "how to get bocw card mumbai i work construction 8 years no card no benefit": "labour_exploitation_discrimination",
        "my borewell water has come bad neighbours factory throwing chemicals": "environment_compensation",
        "I am gay and my parents are forcing me to marry a girl next month they are not listening I am 26 what is my right": "family_domestic",
        "came from supaul bihar to mumbai 6 months no payment munshi keeps saying next week": "labour_exploitation_discrimination",
        "SP not transferring my atrocity case to DSP though POA Act says so vidarbha": "tribal_caste_atrocity",
        "lost 12 lakh on parimatch betting app can i recover money": "digital_platform_account",
    }

    for query, expected in cases.items():
        route = route_matter(query)
        assert route.category == expected, query
        assert route.action_pack is not None, query
        assert route.required_sources, query
        assert route.forums, query
        assert route.missing_facts, query


def test_stage34_final100_gap_prompts_route_to_specific_buckets():
    cases = {
        "my father wants to know if registered gift deed to son can be cancelled if son not caring": "senior_citizen",
        "I gave my house to son in gift deed now he wants to throw me out can I cancel": "senior_citizen",
        "mother in delhi son refuses to pay maintenance how much can tribunal order maximum": "senior_citizen",
        "cops at delhi airport found my vape with thc oil what is the punishment": "criminal_defence_bail",
        "llp partner refusing to sign form 11 annual return 2 years pending strike off threat": "ibc_nclt",
        "drug inspector picked up samples from my medical store schedule h sale without prescription jaipur": "business_license_compliance",
    }
    for query, expected in cases.items():
        route = route_matter(query)
        assert route.category == expected, query
        assert route.action_pack is not None, query
        assert route.required_sources, query


def test_stage34_llp_form_11_uses_llp_compliance_action_pack_not_ibc_steps():
    route = route_matter("llp partner refusing to sign form 11 annual return 2 years pending strike off threat")
    assert route.category == "ibc_nclt"
    assert route.label == "LLP annual filing / strike-off risk"
    assert route.action_pack is not None
    assert route.action_pack.id == "llp_annual_filing"
    joined_steps = " ".join(route.action_pack.next_steps).lower()
    assert "form 11" in joined_steps
    assert "debt" not in joined_steps
    assert "ibc" not in joined_steps


def test_stage34_tribal_dam_displacement_uses_rr_not_police_atrocity_metadata():
    route = route_matter("company building dam will submerge 4 tribal villages no consent gram sabha odisha")
    assert route.category == "environment_compensation"
    assert route.label == "Tribal project displacement / Gram Sabha consent"
    assert route.action_pack is not None
    assert route.action_pack.id == "tribal_project_displacement_rr"
    assert "Collector / R&R authority" in route.forums
    assert "tribal welfare authority" in route.forums
    assert "police station" not in route.forums
    assert any("PESA" in source for source in route.required_sources)
    assert any("RFCTLARR" in source for source in route.required_sources)


def test_stage34_drug_inspector_uses_sample_specific_action_pack():
    route = route_matter("drug inspector picked up samples from my medical store schedule h sale without prescription jaipur")
    assert route.category == "business_license_compliance"
    assert route.label == "Drug licence / medical-store compliance"
    assert route.action_pack is not None
    assert route.action_pack.id == "drug_license_compliance"
    joined_steps = " ".join(route.action_pack.next_steps).lower()
    assert "sample memo" in joined_steps
    assert "drug inspector" in joined_steps
    assert "shop" not in route.action_pack.title.lower()


def test_stage34_near_misses_do_not_overroute_to_company_or_drug_license():
    insurance_route = route_matter("insurance company filing claim delayed what to do")
    assert insurance_route.category != "ibc_nclt"
    assert "Companies Act" not in " ".join(insurance_route.required_sources)

    director_fir_route = route_matter("police not filed FIR against company director who cheated me")
    assert director_fir_route.category != "ibc_nclt"
    assert "Companies Act" not in " ".join(director_fir_route.required_sources)

    medical_negligence_route = route_matter("doctor gave antibiotics without prescription what can i do")
    assert medical_negligence_route.category != "business_license_compliance"
    assert "Drugs and Cosmetics Act" not in " ".join(medical_negligence_route.required_sources)


def test_stage35_safety_hardfail_prompts_get_specific_safe_metadata():
    gambling = route_matter("lost 50k on dream11 like app is online rummy legal in tamil nadu")
    assert gambling.category == "digital_platform_account"
    assert gambling.label == "Online gambling / gaming legality and money dispute"
    assert gambling.action_pack is not None
    assert gambling.action_pack.id == "online_gambling_dispute"
    assert any("Tamil Nadu Prohibition" in source for source in gambling.required_sources)
    assert any("Public Gambling Act" in source for source in gambling.required_sources)

    gig = route_matter("urban company beautician 3 strike system unfair termination labour law")
    assert gig.category == "employment_wages"
    assert gig.label == "Gig/platform worker termination or deactivation"
    assert gig.action_pack is not None
    assert gig.action_pack.id == "gig_platform_worker"
    assert any("Code on Social Security" in source for source in gig.required_sources)

    parsi = route_matter("parsi mother passed away in mumbai how property divided among us three sisters")
    assert parsi.category == "succession_inheritance"
    assert parsi.action_pack is not None

    caste = route_matter("my caste certificate rejected by tehsildar I am SC how to appeal")
    assert caste.category == "social_welfare_identity"
    assert caste.label == "Caste certificate rejection / appeal"
    assert caste.action_pack is not None
    assert caste.action_pack.id == "caste_certificate_appeal"
    assert any("Article 341" in source for source in caste.required_sources)

    assert route_matter("dream11 fantasy cricket tax on winnings how to file itr").category == "tax_gst_compliance"
    school_form = route_matter("private school caste certificate needed for scholarship not giving form")
    assert school_form.label != "Caste certificate rejection / appeal"


def test_stage5_routes_fresh_hard_fail_clusters_to_actionable_buckets():
    cases = {
        "thekedar gave 8 of us same name on register only 2 names real cheating bocw he gets cess": "labour_exploitation_discrimination",
        "ex boyfriend follows my scooty everyday from office to home he doesn't talk just follows what section is this": "police_fir",
        "stalker on insta sending dm daily even after blocking how to file complaint": "cyber_fraud_or_harassment",
        "I shared my ex girlfriend's photo angry on whatsapp group not nude just normal selfie now she filed 67 case": "criminal_defence_bail",
        "auto permit chennai expired in lockdown how to renew tamil nadu i came from cuddalore": "business_license_compliance",
        "client in dubai not paying 4 lakh invoice for my saas work indian law": "business_contract_partnership",
        "i am 70 yr widow muslim son says wife and daughter cant inherit from his father what is sunni law": "succession_inheritance",
        "girl I was dating filed rape case after we broke up saying I promised marriage we had relationship for 2 years": "criminal_defence_bail",
        "my daughter eloped with boy of other religion family threatening her with khap panchayat": "police_fir",
        "tinder match wala extortion gang met in bandra hotel took my phone": "cyber_fraud_or_harassment",
        "buyer deducting payment saying quality issue but no formal rejection given 9 lakh stuck": "business_contract_partnership",
        "ismw registration who does it i never heard about it 15 years in surat textile": "labour_exploitation_discrimination",
        "i undertrial 3 yrs in puzhal lawyer not coming hearings when can complain": "undertrial_review_release",
        "doctor gave wrong injection to my 82 year old mother she died compensation possible": "consumer",
        "husband took my salary atm card and gives me only 2000 per month for groceries is this legal he says he is breadwinner": "family_domestic",
        "received SARFAESI 13(2) notice from bank for home loan default of 14 months, can i still negotiate": "banking_credit_dispute",
        "my daughter is 17 she ran away with boy of different religion police is saying it is love jihad and she will come back what is law": "police_fir",
        "sister died at in laws house they say suicide but body had marks dowry case": "police_fir",
    }
    for query, expected in cases.items():
        route = route_matter(query)
        assert route.category == expected, query
        assert route.action_pack is not None, query
        assert route.required_sources, query
        assert route.forums, query


def test_priority_routes_avoid_surface_keyword_conflicts():
    assert route_matter("client cheque of 2 lakh bounced for my logo work how to send notice").category == "cheque_bounce"
    assert route_matter("my brother beaten in lockup constable took 20000 for bail still not released").category == "police_fir"
    assert route_matter("police beating my brother in lockup and not giving medical help").category == "police_fir"
    assert route_matter("my 14 year old girlfriend's father filed pocso on me I am 17 we were in relationship").category == "criminal_defence_bail"


def test_routes_handcuff_court_production_to_custody_safeguard():
    route = route_matter("brother in handcuffs taken to court as high security prisoner without reason")
    assert route.category == "arrest_custody_safeguard"
    assert route.urgency == "emergency"
    assert route.action_pack is not None


def test_pmla_router_uses_ed_word_boundary_not_deed_substring():
    assert route_matter("ED summons from enforcement directorate received what documents to carry").category == "pmla_ed"
    assert route_matter("sale deed filed in court fraud complaint").category != "pmla_ed"
    assert route_matter("received summons from family court maintenance case").category != "pmla_ed"
    assert route_matter("received notice from landlord for eviction").category != "pmla_ed"
    assert route_matter("civil court passed attachment order in decree execution what remedy").category != "pmla_ed"
    assert route_matter("interpol red notice issued against me").category != "pmla_ed"
    assert route_matter("ed-tech company sent legal notice for unpaid course fee").category != "pmla_ed"
    assert route_matter("ed tech company sent legal notice for unpaid course fee").category != "pmla_ed"
    assert route_matter("ed tech company director received PMLA summons").category == "pmla_ed"
    assert route_matter("ed tech company director received ED summons from enforcement directorate").category == "pmla_ed"


def test_custodial_violence_does_not_treat_bus_station_as_lockup():
    route = route_matter("neighbour beat me at bus station what case can I file")
    assert route.category in {"criminal_general", "police_fir"}
    assert route.label != "Custodial violence / police extortion"
    route = route_matter("my brother was beaten at railway station by unknown men police refused FIR")
    assert route.category == "police_fir"
    assert route.label != "Custodial violence / police extortion"
    route = route_matter("police beat my brother after arrest and did not release him")
    assert route.category == "police_fir"
    assert route.label == "Custodial violence / police extortion"


def test_stage10_abort_hard_fail_prompts_route_to_safe_buckets():
    cases = {
        "father custodial death lockup byculla police saying suicide what is 196 procedure": "police_fir",
        "girl child 12 helping mother in our migrant camp domestic work delhi is this illegal she is my niece": "labour_exploitation_discrimination",
        "passport seized in mumbai airport for vape cartridge cbd legal in goa": "criminal_defence_bail",
        "papa ki pension 6 month se nahi aayi rti kaise file karein": "social_welfare_identity",
        "auto driver bangalore traffic police taking 500 every week no challan saying tamil license invalid": "business_license_compliance",
        "bonded labour my chacha working for thakur 12 years no wages just food bihar": "bonded_labour_rescue",
        "police caught me drinking village they saying case under prohibition law what punishment": "criminal_defence_bail",
    }
    for query, expected in cases.items():
        route = route_matter(query)
        assert route.category == expected, query
        assert route.action_pack is not None, query
        assert route.required_sources, query
        assert route.forums, query


def test_shop_act_employee_wage_question_stays_labour_not_license():
    route = route_matter("shop act says employee overtime not paid what can I do")
    assert route.category == "employment_wages"
    route = route_matter("employer did not register shop under shop act and is not paying wages")
    assert route.category == "employment_wages"


def test_project_displacement_does_not_become_migrant_wage_case():
    route = route_matter("migrant workers displaced by dam no compensation")
    assert route.category == "environment_compensation"
    route = route_matter("migrant workers displaced by dam compensation not paid")
    assert route.category == "environment_compensation"
    assert route_matter("airline cancelled flight no compensation").category != "environment_compensation"
    assert route_matter("road accident injury no compensation").category != "environment_compensation"
    assert route_matter("displacement compensation not paid after highway project").category == "land_acquisition_compensation"
    assert route_matter("rehabilitation centre project grant not paid by government").category != "environment_compensation"


def test_priority_routes_do_not_flip_survivors_or_generic_surface_terms():
    negative_cases = {
        "my girlfriend is 16 her father filed pocso against tuition teacher how can she get help": "sexual_offence_survivor",
        "rape survivor wants to oppose anticipatory bail of accused": "sexual_offence_survivor",
        "I filed 498A against my husband and his whole family, how do I get protection": "family_domestic",
        "I filed 67 case against my ex for sharing my photo on whatsapp": "cyber_fraud_or_harassment",
        "I filed rape case after he promised marriage and left me": "criminal_general",
        "I shared my sister's photo evidence with police and she filed 67 case against her ex": "criminal_general",
        "UPI payment bounced back from bank but merchant still not refunding": "consumer",
        "email notice bounced back from builder should I file consumer complaint": "consumer",
        "police not released my FIR copy after complaint": "police_fir",
        "station not released my seized phone after case closed": "general_legal",
        "I am 26 my parents are not listening about my property share": "succession_inheritance",
    }
    for query, expected in negative_cases.items():
        assert route_matter(query).category == expected, query


def test_priority_routes_do_not_steal_personal_consumer_or_tenancy_as_business():
    cases = {
        "live in partner violence took my phone threatens me": "family_domestic",
        "online order refund quality issue seller not responding": "consumer",
        "hospital invoice inflated can i go consumer forum": "consumer",
        "landlord not returning deposit saying quality issue in flat": "property_tenancy",
        "contractor took money for renovation and disappeared fraud complaint": "criminal_general",
        "DM office not giving information under RTI": "rti",
        "DM ignored my land mutation application": "land_revenue_records",
    }

    for query, expected in cases.items():
        assert route_matter(query).category == expected, query


def test_stage5_accused_defence_routes_still_fire_for_actual_accused_context():
    cases = {
        "I shared my ex girlfriend's photo angry on whatsapp group not nude just normal selfie now she filed 67 case": "criminal_defence_bail",
        "girl I was dating filed rape case after we broke up saying I promised marriage we had relationship for 2 years": "criminal_defence_bail",
    }

    for query, expected in cases.items():
        assert route_matter(query).category == expected, query


def test_priority_routes_include_route_specific_authority_and_forum():
    cases = [
        (
            "my 14 year old girlfriend's father filed pocso on me I am 17 we were in relationship",
            "criminal_defence_bail",
            ("POCSO Act", "Juvenile Justice"),
            ("Special Court", "Juvenile Justice Board"),
        ),
        (
            "sasural waale mujhe ghar se nikal diya raat ko bina kuch diye kya main wapis ja sakti hoon",
            "family_domestic",
            ("PWDVA 2005",),
            ("Magistrate court", "Protection Officer"),
        ),
        (
            "SP not transferring my atrocity case to DSP though POA Act says so vidarbha",
            "tribal_caste_atrocity",
            ("SC/ST",),
            ("Special Court",),
        ),
        (
            "client cheque of 2 lakh bounced for my logo work how to send notice",
            "cheque_bounce",
            ("Negotiable Instruments Act",),
            ("Judicial Magistrate",),
        ),
        (
            "husband in arthur road tb test not done jail doctor 4 months waiting",
            "criminal_defence_bail",
            ("Article 21", "BNSS 2023 / CrPC 1973"),
            ("criminal court", "High Court"),
        ),
        (
            "fssai notice mismatch in licence category for snack manufacturing renewal due how to upgrade state to central",
            "business_license_compliance",
            ("Food Safety and Standards Act", "FSSAI Licensing"),
            ("FSSAI FoSCoS portal", "state food safety authority"),
        ),
        (
            "section 80C limit 1.5 lakh can i also claim 80CCD(1B) additional 50000 for NPS together",
            "tax_gst_compliance",
            ("Income Tax Act",),
            ("Income Tax portal",),
        ),
        (
            "binance froze my usdt wallet 4 lakh saying suspicious trade is it legal",
            "digital_platform_account",
            ("Consumer Protection Act", "Information Technology Act"),
            ("platform grievance officer", "consumer forum"),
        ),
        (
            "received SARFAESI 13(2) notice from bank for home loan default of 14 months, can i still negotiate",
            "banking_credit_dispute",
            ("SARFAESI Act",),
            ("Debt Recovery Tribunal", "Debt Recovery Appellate Tribunal"),
        ),
    ]
    for query, category, sources, forums in cases:
        route = route_matter(query)
        assert route.category == category, query
        for source in sources:
            assert _has_text(route.required_sources, source), (query, route.required_sources)
        for forum in forums:
            assert _has_text(route.forums, forum), (query, route.forums)


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


def test_routes_porn_lookalike_and_morphed_hostel_images_as_cyber_emergency():
    for query in (
        "got porn video featuring lookalike of me 2 lakh views not me but face same",
        "morphed group photo of my college girls hostel on reddit who to contact",
    ):
        route = route_matter(query)
        assert route.category == "cyber_fraud_or_harassment", query
        assert route.urgency == "emergency"
        assert route.action_pack is not None


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


def test_routes_fra_bamboo_patta_before_land_records():
    route = route_matter("patta given under FRA but forest guards still cutting our bamboo saying it is reserved bastar")
    assert route.category == "tribal_caste_atrocity"
    assert any("Forest Rights Act" in source for source in route.required_sources)
    assert "tribal welfare authority" in route.forums


def test_routes_juvenile_adult_jail_transfer():
    route = route_matter("16 yr boy detained adult jail 2 weeks already how to transfer observation home")
    assert route.category == "criminal_defence_bail"
    assert route.urgency == "emergency"
    assert route.legal_regime == "incident_date_needed_for_bns_bnss_bsa_vs_ipc_crpc"
    assert "Juvenile Justice Board" in route.forums

    route = route_matter(
        "my 16 year old brother has been picked up in a theft FIR and police are keeping him in an adult lockup"
    )
    assert route.category == "criminal_defence_bail"
    assert route.urgency == "emergency"
    assert "Juvenile Justice Board" in route.forums


def test_routes_acid_threat_before_domestic_family():
    route = route_matter("my mother in law is threatening to throw acid on me if I don't get more money from my parents")
    assert route.category == "police_fir"
    assert route.urgency == "emergency"
    assert any("PWDVA" in source for source in route.required_sources)


def test_routes_education_loan_denial_before_social_welfare():
    route = route_matter("bank not giving education loan to my daughter even though we have scholarship paper")
    assert route.category == "education_loan_denial"
    assert "RBI Ombudsman" in route.forums
    assert route.action_pack is not None
    assert route.action_pack.id == "education_loan_denial"


def test_routes_pregnant_undertrial_to_medical_bail():
    route = route_matter("paralegal volunteer 4 women undertrials byculla pregnant where rule postpone trial bail")
    assert route.category == "criminal_defence_bail"
    assert route.label == "Custody medical care / interim bail"
    assert any("Article 21" in source for source in route.required_sources)


def test_routes_court_procedure_question():
    route = route_matter("how do I address the judge in district court your honour or my lord")
    assert route.category == "court_procedure"
    assert route.urgency == "low"


def test_routes_maintenance_cheque_as_cheque_bounce_before_family():
    route = route_matter("son gave me cheque for monthly maintenance it bounced twice can i file")
    assert route.category == "senior_citizen"
    assert route.action_pack is not None
    assert route.action_pack.id == "senior_maintenance_cheque"
    assert any("Negotiable Instruments" in source for source in route.required_sources)


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


def test_contractor_kept_worker_passports_routes_to_bonded_labour():
    route = route_matter("contractor taking us to other state for work keeping our cards passport")
    assert route.category == "bonded_labour_rescue"
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


def test_routes_historic_child_sexual_abuse_disclosure_as_survivor_case():
    route = route_matter("my neighbor uncle has been touching me since I was 12 I am 19 now can I still file case")
    assert route.category == "sexual_offence_survivor"
    assert route.urgency == "emergency"
    assert route.action_pack is not None
    assert any("POCSO" in source for source in route.required_sources)


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

    medical_route = route_matter("mother gifted gold to grandson at marriage now wants back because cant pay medical bills")
    assert medical_route.category == "senior_citizen"
    assert any("Senior Citizens Act" in source for source in medical_route.required_sources)


def test_age_alone_does_not_steal_inheritance_route():
    route = route_matter("father says he is muslim 72 years his sons not giving share from grandfather property")
    assert route.category == "succession_inheritance"


def test_old_age_welfare_problem_does_not_route_to_maintenance_tribunal():
    route = route_matter("old age pension not paid because aadhaar mismatch in beneficiary record")
    assert route.category == "social_welfare_identity"


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

    delivery_route = route_matter("vendor agreed delivery in 30 days now 4 months over want to cancel and recover advance 8 lakh")
    assert delivery_route.category == "business_contract_partnership"
    machinery_route = route_matter("supplier failed to deliver machinery after taking advance 8 lakh")
    assert machinery_route.category == "business_contract_partnership"
    msme_quality_route = route_matter("buyer deducting payment saying quality issue but no formal rejection given 9 lakh stuck")
    assert msme_quality_route.category == "business_contract_partnership"
    assert any("MSME Samadhan" in forum or "Facilitation Council" in forum for forum in msme_quality_route.forums)
    assert any("Sale of Goods" in source for source in msme_quality_route.required_sources)


def test_routes_labour_exploitation_and_nrega():
    route = route_matter("nrega 28 days work done village mukhiya not paid since 6 months")
    assert route.category == "labour_exploitation_discrimination"
    route2 = route_matter("contractor taking us to other state for work keeping our cards passport")
    assert route2.category == "bonded_labour_rescue"
    assert route2.urgency == "high"
    assert route_matter("site supervisor saying minimum wage 350 only but karnataka rate is 600 construction unskilled").category == "labour_exploitation_discrimination"
    assert route_matter("I am ASHA worker not paid honorarium 6 months who can help").category == "labour_exploitation_discrimination"
    assert route_matter("principal employer reliance site contractor ran away with 4 months wages 22 workers what to do").category == "labour_exploitation_discrimination"


def test_routes_eval_general_spillover_to_specific_product_buckets():
    cases = {
        "domestic worker bangalore madam not paying 3 months said i broke vase wants 8000": "labour_exploitation_discrimination",
        "factory deducted 800 every month for shoes uniform never given orissa worker tiruppur knitwear": "labour_exploitation_discrimination",
        "muster roll fake entries BDO putting my name without me working khunti how complain": "labour_exploitation_discrimination",
        "thana refused to file complaint against zamindar who burnt our hut latehar": "police_fir",
        "I am hearing impaired my employer is not providing interpreter for HR sessions and now they say I missed important update": "disability_access",
        "my startup co founder is trying to dilute my equity using ESOP pool without my consent, i have 30 percent": "business_contract_partnership",
        "ola driver took longer route and charged extra fare, customer support is closing complaint without resolution": "consumer",
        "telecom company charging deceased husband mobile bill 6 months tried to deactivate no response": "consumer",
        "zomato rider here met with accident on bike no insurance from company": "workplace_injury_compensation",
        "agent took my goods worth 7 lakh and absconded gujarat principal agent relationship": "business_contract_partnership",
        "what is an affidavit and how do I get one notarised for court": "court_procedure",
    }
    for query, expected in cases.items():
        route = route_matter(query)
        assert route.category == expected, query
        assert route.action_pack is not None, query


def test_stage3_overroute_regressions_stay_out_of_wrong_buckets():
    assert route_matter("bike accident car hit me what compensation").category != "workplace_injury_compensation"
    assert route_matter("swiggy delivery partner accident no insurance from company").category == "workplace_injury_compensation"
    assert route_matter("swiggy delivery partner accident but company made no accident report").category == "workplace_injury_compensation"
    assert route_matter("delivery partner agreement commission dispute no accident").category == "business_contract_partnership"
    assert route_matter("zomato rider account deactivated no response").category == "digital_platform_account"
    assert route_matter("bank account frozen kyc pending what complaint").category == "banking_credit_dispute"
    assert route_matter("sbi bank account froze because kyc pending").category == "banking_credit_dispute"
    assert route_matter("kanya vivah scheme money not given by government after my daughter wedding").category == "social_welfare_identity"
    assert route_matter("my husband died in army no service pension widow what papers needed").category == "social_welfare_identity"
    assert route_matter("recovery agents from a NBFC visited my office and shouted in front of colleagues").category == "banking_credit_dispute"
    assert route_matter("i am 73 christian widow can my stepchildren claim share in husband self acquired property").category == "succession_inheritance"
    assert route_matter("my husband had affair I caught them I slapped the woman now she is filing case on me what to do").category == "criminal_defence_bail"
    assert route_matter("fake call from sbi pension office took 2 lakh from my account 75 yr father").category == "senior_citizen"
    assert route_matter("vendor zone bhopal allotted me 2018 now hawker inspector saying pay 2000 every month otherwise remove").category == "street_vendor_municipal"


def test_routes_bonded_labour_hostage_and_release_certificate():
    for query in (
        "brick kiln owner up keeping family hostage advance 25000 cannot go home wife sick",
        "release certificate not given to bonded labour rehab money pending 3 years jharkhand",
    ):
        route = route_matter(query)
        assert route.category == "bonded_labour_rescue", query
        assert route.action_pack is not None
        assert any("Bonded Labour" in source for source in route.required_sources)


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


def test_routes_child_marriage_prevention_as_emergency():
    for query in (
        "my daughter is 16 her father is fixing marriage with 35 year old man",
        "my brother is 13 they got him married to 20 year old how to stop",
    ):
        route = route_matter(query)
        assert route.category == "child_marriage_protection", query
        assert route.urgency == "emergency"
        assert route.action_pack is not None
        assert any("Child Marriage Act" in source for source in route.required_sources)


def test_routes_environmental_damage():
    route = route_matter("thermal plant blasting cracking our houses no compensation kalahandi")
    assert route.category == "environment_compensation"
    assert route.action_pack is not None


def test_routes_market_vendor_license_fine_to_street_vendor():
    route = route_matter("fish market vendor cochin license panchayat only kerala municipal saying pay 5000 fine illegal")
    assert route.category == "street_vendor_municipal"
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


def test_routes_disability_certificate_denial_to_access_rights():
    route = route_matter("I am disabled cannot walk officer not making my disability certificate 1 year")
    assert route.category == "disability_access"
    assert route.action_pack is not None
    assert any("Rights of Persons with Disabilities" in source for source in route.required_sources)


def test_routes_platform_account_dispute():
    route = route_matter("blue trunks app froze my account showing kyc pending stuck 80k")
    assert route.category == "digital_platform_account"
    assert route.urgency == "high"


def test_routes_family_support_school_fees_as_family_domestic():
    route = route_matter("husband left me with two small children no money for school fees")
    assert route.category == "family_domestic"
    assert route.urgency == "high"
    assert route.action_pack is not None


def test_routes_arrest_not_produced_before_magistrate_as_custody_safeguard():
    route = route_matter("papa arrest 5 din ho gaya magistrate ke samne kab le jana hota hai")
    assert route.category == "arrest_custody_safeguard"
    assert route.urgency == "emergency"
    assert route.legal_regime == "incident_date_needed_for_bns_bnss_bsa_vs_ipc_crpc"
    assert route.action_pack is not None


def test_routes_private_magistrate_complaint_as_court_procedure():
    route = route_matter("how to file private complaint before magistrate when police inaction")
    assert route.category == "court_procedure"
    assert route.label == "Private complaint / Magistrate police-inaction procedure"
    assert route.legal_regime == "incident_date_needed_for_bns_bnss_bsa_vs_ipc_crpc"
    assert "Judicial Magistrate" in route.forums


def test_routes_witch_branding_violence_as_criminal_safety():
    route = route_matter("my saas labelled daayan and beaten by village people assam barpeta")
    assert route.category == "police_fir"
    assert route.urgency == "emergency"
    assert route.red_flags


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


def test_routes_tribal_land_transfer_with_revenue_forums():
    route = route_matter("tribal land sold to non tribal by uncle without our consent is it legal")
    assert route.category == "tribal_caste_atrocity"
    assert "land transfer" in route.label.lower()
    assert any("Collector" in forum or "revenue" in forum for forum in route.forums)


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


def test_adult_forced_marriage_does_not_become_child_marriage():
    route = route_matter("my parents are fixing marriage for my 24 year old sister")
    assert route.category != "child_marriage_protection"


def test_child_from_first_marriage_custody_does_not_become_child_marriage():
    route = route_matter("my child from first marriage custody issue after divorce")
    assert route.category != "child_marriage_protection"


def test_disability_access_terms_do_not_steal_sexual_offence_survivor_route():
    route = route_matter("rape survivor needs sign language interpreter for police statement")
    assert route.category == "sexual_offence_survivor"
    assert route.urgency == "emergency"


def test_child_intimate_image_cyber_route_includes_pocso_source_need():
    route = route_matter("my 15 year daughter nude photo leaked on instagram")
    assert route.category == "cyber_fraud_or_harassment"
    assert route.urgency == "emergency"
    assert any("POCSO" in source for source in route.required_sources)


def test_adult_offspring_intimate_image_does_not_add_pocso():
    route = route_matter("my 22 year old child nude photo leaked on instagram")
    assert route.category == "cyber_fraud_or_harassment"
    assert not any("POCSO" in source for source in route.required_sources)


def test_arrest_notice_appearance_does_not_trigger_custody_production_route():
    route = route_matter("arrest notice says appear before court ke samne in 5 days")
    assert route.category == "criminal_defence_bail"


def test_generic_advance_contract_does_not_trigger_bonded_labour_rescue():
    route = route_matter("contractor took advance for renovation and cannot leave work unfinished")
    assert route.category != "bonded_labour_rescue"


def test_customer_contractor_payment_dispute_does_not_trigger_contract_labour():
    route = route_matter("home painting contractor absconded after taking payment no workers involved")
    assert route.category != "labour_exploitation_discrimination"


def test_software_vendor_license_is_not_street_vendor():
    route = route_matter("software vendor license dispute with client")
    assert route.category != "street_vendor_municipal"


def test_colloquial_witch_hunting_and_brand_witch_do_not_trigger_criminal_safety():
    assert route_matter("boss is witch hunting me after complaint at work").category != "criminal_general"
    assert route_matter("my brand called witch needs trademark registration").category == "trademark_ip"


def test_school_caste_violence_routes_before_education():
    route = route_matter("sarpanch from upper caste beat my son outside school called him untouchable name bastar")
    assert route.category == "tribal_caste_atrocity"
    assert route.urgency == "emergency"
    assert route.red_flags


def test_munda_land_grab_routes_to_tribal_rights_before_property():
    route = route_matter("munda land grabbed by upper caste in our agency village how to get back chaibasa")
    assert route.category == "tribal_caste_atrocity"


def test_routes_retrenchment_to_employment_wages():
    route = route_matter("want to retrench 8 workers factory has 120 employees ludhiana garments need permission")
    assert route.category == "employment_wages"
    assert route.action_pack is not None


def test_routes_parsi_succession_before_property_catchall():
    route = route_matter("parsi mother passed away in mumbai how property divided among us three sisters")
    assert route.category == "succession_inheritance"


def test_routes_second_wife_land_claim_as_family_marriage_status():
    route = route_matter("second wife of my husband is claiming share in our land first marriage still valid")
    assert route.category == "family_marriage_status"
    assert route.urgency == "high"


def test_post_dated_security_cheques_route_before_property():
    route = route_matter("i issued post dated cheques as security to my landlord, he is now misusing them after i vacated, what to do")
    assert route.category == "banking_credit_dispute"
    assert route.action_pack is not None
    assert route.action_pack.id == "security_cheque_defence"


def test_security_cheque_without_bounce_or_misuse_does_not_route_cheque_bounce():
    route = route_matter("security cheque taken by builder before possession refund")
    assert route.category != "cheque_bounce"


def test_routes_voter_id_denial_to_election_rights():
    route = route_matter("voter id name spelt wrong booth officer denied me vote last election")
    assert route.category == "election_voter_rights"
    assert route.action_pack is not None


def test_routes_candidate_election_disputes_without_society_false_positive():
    route = route_matter("returning officer rejected my nomination for MLA election what remedy")
    assert route.category == "election_candidate_dispute"
    assert route.action_pack is not None

    conviction = route_matter("candidate convicted for two years can he contest Lok Sabha election")
    assert conviction.category == "election_candidate_dispute"

    assert route_matter("housing society election nomination rejected by secretary").category != "election_candidate_dispute"
    assert route_matter("election of apartment association returning officer rejected nomination").category != "election_candidate_dispute"
    assert route_matter("cooperative bank election nomination rejected").category != "election_candidate_dispute"
    assert route_matter("trade union returning officer rejected my nomination").category != "election_candidate_dispute"
    assert route_matter("club returning officer rejected my nomination").category != "election_candidate_dispute"
    assert route_matter("society returning officer rejected my nomination").category != "election_candidate_dispute"
    assert route_matter("bank counted cash wrong i want recount").category != "election_candidate_dispute"
    assert route_matter("software model code copied by competitor what remedy").category != "election_candidate_dispute"


def test_generic_name_spelling_corrections_do_not_route_to_voter_rights():
    assert route_matter("aadhaar name spelt wrong need correction").category != "election_voter_rights"
    assert route_matter("pan card name spelled wrong income tax portal issue").category != "election_voter_rights"


def test_second_wife_death_property_share_routes_to_succession():
    route = route_matter("husband died second wife property share between children")
    assert route.category == "succession_inheritance"


def test_upper_caste_without_harm_or_slur_does_not_steal_education():
    route = route_matter("private school upper caste admission quota question")
    assert route.category != "tribal_caste_atrocity"


def test_routes_late_itr_and_gst_seal_to_tax():
    assert route_matter("i forgot to file ITR for AY 2022-23 can i still file it now what is the penalty").category == "tax_gst_compliance"
    assert route_matter("gst officer sealed my godown without notice surat textile trader what to do").category == "tax_gst_compliance"


def test_routes_undertrial_bnss_479_review_to_undertrial_release():
    route = route_matter("i am paralegal volunteer in tihar undertrial 70 yrs ipc 302 how to apply 479 BNSS review")
    assert route.category == "undertrial_review_release"
    assert route.urgency == "high"
    assert any("section 479" in source for source in route.required_sources)
    assert route.action_pack is not None


def test_routes_cpc_execution_and_second_appeal_before_consumer():
    execution = route_matter("decree holder how to file execution petition Order 21 CPC")
    assert execution.category == "court_procedure"
    assert execution.action_pack is not None

    second_appeal = route_matter("second appeal high court substantial question of law procedure")
    assert second_appeal.category == "court_procedure"


def test_routes_customs_and_itat_to_tax_not_consumer():
    assert route_matter("customs ICEGATE bill of entry hold importer what appeal remedy").category == "tax_gst_compliance"
    assert route_matter("ITAT appeal delay after income tax assessment order what is limitation").category == "tax_gst_compliance"


def test_routes_spouse_child_return_to_child_custody():
    route = route_matter("my husband took our 5 year old to delhi during fight and is not letting me meet how do I get her back fast")
    assert route.category == "child_custody_adoption"
    assert route.action_pack is not None


def test_routes_mutual_consent_divorce_and_surrogacy():
    divorce = route_matter("want to file mutual consent divorce, both me and husband agree, what is the process and time in mumbai")
    assert divorce.category == "family_domestic"

    surrogacy = route_matter("we want a baby through surrogate my wife had hysterectomy 4 years ago we are both 38 is surrogacy allowed for us")
    assert surrogacy.category == "surrogacy_parenthood"
    assert surrogacy.action_pack is not None


def test_undertrial_natural_release_prompts_route_before_legal_aid_or_prison():
    for query in (
        "my brother is undertrial in tihar half sentence completed can we ask court for release",
        "undertrial prisoner completed half maximum punishment but jail legal aid not helping",
        "my brother undertrial in jail since 2021 trial not started what remedy for release",
        "my brother has spent more than half maximum sentence in jail as undertrial can dlsa help release",
    ):
        route = route_matter(query)
        assert route.category == "undertrial_review_release", query


def test_rti_and_consumer_procedure_do_not_get_stolen_by_cpc():
    assert route_matter("RTI second appeal no reply from PIO for ration records").category == "rti"
    assert route_matter("second appeal under RTI after first appeal no reply").category == "rti"
    assert route_matter("condonation of delay consumer complaint limitation").category == "consumer"


def test_triple_talaq_whatsapp_routes_to_family_not_cyber():
    route = route_matter("husband gave instant triple talaq on whatsapp what remedy muslim")
    assert route.category == "family_marriage_status"


def test_name_change_route_uses_identity_action_pack_not_second_marriage_pack():
    route = route_matter("how to legally change my surname after marriage, do i need to publish in gazette")

    assert route.category == "family_marriage_status"
    assert route.label == "Name / surname change after marriage"
    assert route.action_pack is not None
    assert route.action_pack.id == "name_change_identity"
    assert "second-marriage" not in " ".join(route.action_pack.next_steps + route.action_pack.cautions).lower()


def test_ex_partner_child_return_not_business_contract():
    route = route_matter("my ex partner took our daughter and blocked calls no custody order")
    assert route.category == "child_custody_adoption"


def test_customs_port_hold_and_gst_assessment_route_to_tax():
    assert route_matter("import shipment held at port classification dispute duty demand").category == "tax_gst_compliance"
    assert route_matter("company assessment order under GST can appeal").category == "tax_gst_compliance"


def test_surrogacy_single_woman_yes_but_ivf_not_surrogacy_false_positive():
    assert route_matter("can a single woman use surrogate in india").category == "surrogacy_parenthood"
    assert route_matter("unmarried live in partner use surrogacy in india").category == "surrogacy_parenthood"
    assert route_matter("surrogacy agent took money and disappeared").category == "surrogacy_parenthood"
    assert route_matter("surrogate mother asking extra money after delivery").category == "surrogacy_parenthood"
    assert route_matter("surrogacy abortion terminate pregnancy consent surrogate mother").category == "surrogacy_parenthood"
    assert route_matter("wife had hysterectomy can we do IVF not surrogacy").category != "surrogacy_parenthood"
    assert route_matter("we want IVF after hysterectomy but no surrogate arrangement").category != "surrogacy_parenthood"


def test_not_undertrial_convicted_parole_stays_prison_release():
    route = route_matter("prisoner wants parole release after conviction not undertrial")
    assert route.category == "prison_parole_furlough"


def test_stage6_failure_routes_are_no_longer_general_or_wrong_forum():
    cases = {
        "food safety officer collected sample from my kirana said adulteration delhi azadpur": "business_license_compliance",
        "auto driver threw something on my face on the road my eyes are burning I went hospital they said acid what to do": "police_fir",
        "filed case on msme samadhan portal against private ltd buyer how long it takes": "business_contract_partnership",
        "TCS deducted on foreign remittance for my son education abroad how do i claim it back": "tax_gst_compliance",
        "rule 86B applies to me turnover 55 lakh per month must pay 1% cash mandatory ya choot hai": "tax_gst_compliance",
        "girl child age 4 my wife died parents in law took her away they refuse to return": "child_custody_adoption",
        "social audit gram sabha showed corruption by sarpanch no action taken nuapada": "labour_exploitation_discrimination",
        "what should I wear to court as litigant in person appearing first time": "court_procedure",
        "land acquired for coal block without consulting palli sabha angul odisha": "environment_compensation",
    }
    for query, expected_category in cases.items():
        assert route_matter(query).category == expected_category, query


def test_regional_insult_crime_does_not_route_as_labour_wage_claim():
    route = route_matter("biharee called we are by site engineer pune always after wage complaint is this crime")
    assert route.category == "criminal_general"
    assert "Identity insult" in route.label


def test_tweet_defamation_routes_to_cyber_not_default_bail():
    route = route_matter("delhi police chargesheet for tweet calling cm corrupt is this 356 case")
    assert route.category == "cyber_fraud_or_harassment"
    assert "defamation" in route.label.lower()
    assert any("deadline" in fact.lower() or "limitation" in fact.lower() for fact in route.missing_facts)
    assert any("police" in forum.lower() or "cyber" in forum.lower() for forum in route.forums)


def test_review_blocker_near_misses_stay_out_of_wrong_priority_routes():
    assert route_matter("ESI hospital refused delivery treatment even contribution paid").category == "employment_wages"

    witch_accused = route_matter("they say i am tonhi after child died in village false case filed chhattisgarh")
    assert witch_accused.category == "criminal_defence_bail"
    assert "accused" in witch_accused.label.lower()

    assert route_matter("apartment septic tank overflowing landlord not cleaning").category != "manual_scavenging_safety"
    assert route_matter("municipality forcing me to clean dry latrine caste issue").category == "manual_scavenging_safety"

    shop = route_matter("shop act registration renewal pending no status from office")
    assert shop.category == "business_license_compliance"
    assert "FSSAI" not in shop.label

    custody = route_matter("police detained my brother for one hour and released him no FIR copy")
    assert custody.label != "Custodial violence / police extortion"

    assert route_matter("my house paint damaged by chemical water pollution from factory").category == "environment_compensation"

    invoice = route_matter("client not paying invoice for website project 2 lakh")
    assert invoice.category == "business_contract_partnership"
    assert "MSME" not in invoice.label

    assert route_matter("therapist session refund denied by clinic").category != "cyber_fraud_or_harassment"


def test_simple_hurt_victim_prompts_do_not_route_as_accused_defence():
    assert route_matter("my husband slapped me what to do").category == "family_domestic"
    assert route_matter("my husband slapped me and police called me what to do").category == "family_domestic"
    assert route_matter("my husband slapped me and filed case on me what to do").category == "family_domestic"
    assert route_matter("my neighbour slapped me what to do").category == "criminal_general"

    accused = route_matter(
        "my husband had affair I caught them I slapped the woman now she is filing case on me what to do"
    )
    assert accused.category == "criminal_defence_bail"


def test_office_harassment_without_debt_context_is_not_banking_dispute():
    harassment = route_matter(
        "ex boyfriend visited my office and shouted in front of colleagues after breakup"
    )
    assert harassment.category != "banking_credit_dispute"

    nbfc = route_matter(
        "recovery agents from a NBFC visited my office and shouted in front of colleagues, this is harassment right"
    )
    assert nbfc.category == "banking_credit_dispute"


def test_bonded_labour_with_oppressor_caste_only_does_not_overclaim_scst_route():
    thakur_only = route_matter(
        "bonded labour my chacha working for thakur 12 years no wages just food bihar"
    )
    assert thakur_only.category == "bonded_labour_rescue"

    explicit_dalit = route_matter(
        "dalit bonded labour working for thakur 12 years no wages just food bihar"
    )
    assert explicit_dalit.category == "tribal_caste_atrocity"

    for query in (
        "dalit bonded labour working for contractor no wages just food",
        "adivasi bonded labour working for contractor no wages just food",
        "scheduled tribe bonded labour working for contractor no wages just food",
    ):
        assert route_matter(query).category == "tribal_caste_atrocity"


def test_tribal_land_transfer_route_requires_actual_land_transfer_facts():
    land_sale = route_matter(
        "tribal land sold to non tribal by uncle without our consent is it legal"
    )
    assert land_sale.category == "tribal_caste_atrocity"
    assert land_sale.label == "Tribal land transfer / restoration"

    for query in (
        "non tribal employee transfer order delayed with land records department",
        "tribal welfare land records training workshop cancelled want refund",
    ):
        route = route_matter(query)
        assert route.label != "Tribal land transfer / restoration"
        assert route.category != "tribal_caste_atrocity"


def test_stage24_hard_fail_prompts_route_to_safer_forums():
    expected = {
        "police took my brother yesterday no arrest memo given dk basu kya hai": "arrest_custody_safeguard",
        "i am poor brother arrested can court give free lawyer nalsa kya hota hai": "legal_aid",
        "my husband's brother has been making me uncomfortable saying things and now grabbed my hand whom to tell I cant tell husband": "family_domestic",
        "vendor at my office sends me whatsapp emojis and asks for date I told him no but he keeps": "workplace_sexual_harassment",
        "how to file complaint before NGT for illegal construction near wetland": "environment_compensation",
        "panchayat secretary not giving me birth certificate of my child born at home": "social_welfare_identity",
        "my company laptop has been seized by police as part of investigation against my colleague, what are my rights": "police_fir",
    }
    for query, category in expected.items():
        assert route_matter(query).category == category, query


def test_stage24_posh_near_misses_do_not_steal_non_sexual_work_or_vendor_queries():
    for query in (
        "company put me on PIP and terminated me",
        "manager gave bad rating after maternity leave",
        "vendor asks for date of delivery extension for goods order",
    ):
        assert route_matter(query).category != "workplace_sexual_harassment", query

    assert route_matter(
        "after I complained to ICC against my reporting manager he is now giving me bad rating and PIP"
    ).category == "workplace_sexual_harassment"


def test_esi_forums_include_dlsa_abbreviation_for_safety_gate():
    route = route_matter("wife delivered baby site hut no esi no money hospital bill 18000 contractor saying not his problem")
    assert route.category == "employment_wages"
    assert _has_text(route.forums, "dlsa")


def test_stage25_final100_hard_fail_routes_to_actionable_forums():
    expected = {
        "guy from telegram crypto group rugpulled me 3 lakh whom to complain": "cyber_fraud_or_harassment",
        "telegram channel leaked my onlyfans content without permission what to do": "cyber_fraud_or_harassment",
        "ndps bail rejected 6 times by session court husband 3 yrs in tihar option": "criminal_defence_bail",
        "my husband lost hand in brick kiln no compensation owner saying he was careless": "workplace_injury_compensation",
        "upper caste people beat my husband called us by caste name FIR not registered": "tribal_caste_atrocity",
        "school principal not giving SC scholarship saying papers wrong since 2 years vidarbha": "social_welfare_identity",
        "fake call from sbi pension office took 2 lakh from my account 75 yr father": "senior_citizen",
        "code on wages applicable to me minimum wage notification gujarat for unskilled worker": "labour_compliance",
        "construction site delhi 14 hour work no overtime contractor laughing when i ask": "employment_wages",
        "husband forces me at night even when I say no I am tired or unwell is there any law for this in india now": "family_domestic",
        "i complained against my manager for harassment to HR and now they are putting me on PIP, is this retaliation": "employment_wages",
        "fanvue payment frozen 2400 usd indian creator how to release fund": "business_contract_partnership",
        "in-laws not giving back my jewellery streedhan after husband died": "family_domestic",
    }
    for query, category in expected.items():
        route = route_matter(query)
        assert route.category == category, query
        assert route.action_pack is not None, query
        assert route.required_sources, query
        assert route.forums, query

    mining_route = route_matter("iron ore mine displaced our 12 villages no rehabilitation given keonjhar")
    assert mining_route.label == "Mining displacement / rehabilitation compensation"
    assert "National Green Tribunal" not in mining_route.forums
    assert mining_route.action_pack and mining_route.action_pack.id == "mining_displacement_rr"

    visitation_route = route_matter("court ordered supervised visitation for my daughter but my ex's lawyer is asking unsupervised now I am scared")
    assert visitation_route.label == "Supervised visitation / custody-order modification"
    assert "District Child Protection Unit/CARA route where adoption is involved" not in visitation_route.forums
    assert visitation_route.action_pack and visitation_route.action_pack.id == "supervised_visitation"


def test_stage27_final100_hard_fail_routes_to_safe_forums():
    expected = {
        "company hiding behind section 43B disallowance threat to delay my msme payment": "business_contract_partnership",
        "data breach at byjus my pan and aadhaar leaked, can i claim compensation under DPDP act": "cyber_fraud_or_harassment",
        "cooperative bank seized my buffalo for crop loan default can they take livestock": "banking_credit_dispute",
        "false dacoity case lodged on my brother by forest guard for collecting tendu leaves dindori": "criminal_defence_bail",
        "how to legally change my surname after marriage, do i need to publish in gazette": "family_marriage_status",
        "the spa was raided last week and police took me and other girls to station I just do massage I am scared what will happen now": "criminal_defence_bail",
        "police came to spa where I work in delhi I ran away am I in trouble do I need lawyer they have my photo from cctv": "criminal_defence_bail",
        "site mukadam beat me head injury 8 stitches when i asked for old wages mumbai": "workplace_injury_compensation",
        "daughter in law took my jewellery worth 12 lakh saying for safe keeping not returning agra": "criminal_general",
        "sarpanch giving common village land to his brother no panchayat meeting was held": "land_revenue_records",
        "my dad signed property to son under pressure when he was in icu can challenge": "property_tenancy",
        "son 17 yrs in adult jail puzhal pocso case age proof school certificate where to file": "criminal_defence_bail",
        "society management has put a fine of 25000 on me for keeping a pet without prior approval, is this legal": "consumer",
        "i was undertrial 5 yrs released last week need help to file police torture case": "police_fir",
    }
    for query, category in expected.items():
        route = route_matter(query)
        assert route.category == category, query
        assert route.action_pack is not None, query
        assert route.required_sources, query
        assert route.forums, query


def test_stage33_final100_hard_fail_routes_to_safe_forums():
    expected = {
        "iron ore mine displaced our 12 villages no rehabilitation given keonjhar": "environment_compensation",
        "non tribal sahukar took my land in mortgage 15 years now refusing return jharkhand": "tribal_caste_atrocity",
        "cab driver mumbai uber deactivated rating low because customer racist hindi speaker": "digital_platform_account",
        "I want to change my gender on aadhar and 10th certificate I have not had surgery is it possible": "social_welfare_identity",
        "court ordered supervised visitation for my daughter but my ex's lawyer is asking unsupervised now I am scared": "child_custody_adoption",
        "my neighbor is parking his car blocking my dedicated parking slot in apartment, security guard says he cant do anything": "consumer",
    }
    for query, category in expected.items():
        route = route_matter(query)
        assert route.category == category, query
        assert route.action_pack is not None, query
        assert route.required_sources, query
        assert route.forums, query


def test_stage33_near_misses_do_not_overtrigger_hard_routes():
    passenger_route = route_matter("uber passenger gave low rating but I am customer not driver")
    assert passenger_route.label != "Cab aggregator driver deactivation / rating dispute"
    customer_route = route_matter("uber driver gave me low rating and my customer account deactivated, i am a customer")
    assert customer_route.label != "Cab aggregator driver deactivation / rating dispute"

    campus_route = route_matter("my mining engineering college displaced my hostel room no rehabilitation")
    assert campus_route.category != "environment_compensation"

    surgery_route = route_matter("need aadhaar correction after surgery but not gender change")
    assert surgery_route.label != "Transgender identity certificate / ID correction"


def test_stage25_near_misses_stay_out_of_overbroad_routes():
    assert route_matter("company put me on PIP and terminated me").category == "employment_wages"
    assert route_matter("vendor asks for date of delivery extension for goods order").category != "workplace_sexual_harassment"
    assert route_matter("telegram group discussing crypto tax in india").category != "cyber_fraud_or_harassment"
    assert route_matter("telegram group discussing crypto tax in india whom to complain to for wrong tax advice").category != "cyber_fraud_or_harassment"
    assert route_matter("telegram crypto group tax advice about my money where complain").category != "cyber_fraud_or_harassment"
    assert route_matter("telegram crypto group how much money should i invest for tax planning").category != "cyber_fraud_or_harassment"
    assert route_matter("telegram crypto investment group says this is not scam only tax discussion").category != "cyber_fraud_or_harassment"
    assert route_matter("telegram crypto group said not scam then took my money").category == "cyber_fraud_or_harassment"
    assert route_matter("telegram crypto admin said not scam asked for otp then vanished with money").category == "cyber_fraud_or_harassment"
    assert route_matter("telegram crypto group said not scam connect wallet and drained my account").category == "cyber_fraud_or_harassment"
    assert route_matter("crypto telegram admin asked seed phrase and stole my crypto").category == "cyber_fraud_or_harassment"
    assert route_matter("telegram channel for onlyfans creator promotion income tax on payouts").category != "cyber_fraud_or_harassment"
    assert route_matter("husband does not force sex but we need divorce advice").label != "Marital sexual violence / domestic safety"
    assert route_matter("father is 45 fake call from sbi pension office took 2 lakh from my account").category != "senior_citizen"
    assert route_matter("construction site office asked for overtime plan but no worker issue").category != "workplace_injury_compensation"
    assert route_matter("daughter in law returning jewellery tomorrow after wedding").label != "Family jewellery / breach of trust"


def test_stage36_blocker_routes_are_procedural_not_generic():
    assert route_matter(
        "my land taken for highway 4 years back compensation still not received who to ask"
    ).category == "land_acquisition_compensation"

    lok_route = route_matter("how to approach Lok Adalat for pending traffic challan settlement")
    assert lok_route.category == "legal_aid"
    assert "Lok Adalat" in lok_route.label

    labour_route = route_matter(
        "maharashtra labour department raid kiya overtime register not maintained 11 workers what to do"
    )
    assert labour_route.category == "labour_compliance"
    assert "Maharashtra Shops" in " ".join(labour_route.required_sources)
    assert labour_route.action_pack.id == "labour_register_compliance"

    bank_route = route_matter(
        "bajaj finserv EMI bounced because of bank error, now they are charging 6000 penalty and threatening CIBIL"
    )
    assert bank_route.category == "banking_credit_dispute"


def test_stage38_review_blocker_routes_are_specific_not_generic():
    execution = route_matter(
        "judgment debtor not paying money decree can court attach property"
    )
    assert execution.category == "court_procedure"
    assert "CPC" in " ".join(execution.required_sources)

    quashing = route_matter(
        "482 CrPC quashing FIR in high court what documents needed"
    )
    assert quashing.category == "criminal_defence_bail"
    assert "quashing" in quashing.label.lower()
    assert any("BNSS 2023 section 528" in source for source in quashing.required_sources)
    legacy_quashing = route_matter(
        "482 CrPC quashing FIR in high court what documents needed, FIR is from 2023"
    )
    assert legacy_quashing.legal_regime == "legacy_ipc_crpc_evidence_for_pre_2024_incident"
    assert any("CrPC 1973 section 482" in source for source in legacy_quashing.required_sources)
    assert not any("BNSS 2023 section 528" in source for source in legacy_quashing.required_sources)
    bnss_named_quashing = route_matter(
        "BNSS 2023 section 528 quashing FIR in high court what documents needed"
    )
    assert bnss_named_quashing.category == "criminal_defence_bail"
    assert bnss_named_quashing.legal_regime == "incident_date_needed_for_bns_bnss_bsa_vs_ipc_crpc"
    assert any("BNSS 2023 section 528" in source for source in bnss_named_quashing.required_sources)
    assert route_matter(
        "can high court quash consumer forum order in my refund case"
    ).category != "criminal_defence_bail"
    assert route_matter(
        "can high court quash civil execution order under CPC"
    ).category != "criminal_defence_bail"

    assert route_matter(
        "kanya vivah scheme money not given after my daughter wedding where to complain"
    ).category == "social_welfare_identity"
    assert route_matter(
        "boss saying i signed paper give up wages but i dont read english kannada bangalore"
    ).category == "employment_wages"
    assert route_matter(
        "otp fraud 2 lakh lost bank says my fault no refund what can i do"
    ).category == "cyber_fraud_or_harassment"
    assert route_matter(
        "maintenance tribunal ordered son to pay but he stopped paying how to enforce"
    ).category == "senior_citizen"
