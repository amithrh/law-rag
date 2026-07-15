from __future__ import annotations

from apps.api.matter_router import route_matter, route_matter_trace
from apps.api.source_packs import source_packs_for_route


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
        "son took loan against my house i didn't sign told bank to stop ahmedabad": "banking_credit_dispute",
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


def test_fresh500_common_failures_route_to_user_primary_job():
    cases = {
        "friend gave cheque for loan repayment and bank returned it": (
            "cheque_bounce",
            "Cheque dishonour",
        ),
        "need help, i was in jail 7 yrs acquitted now how to get compensation state legal aid what next": (
            "custody_compensation",
            "Wrongful custody / acquittal compensation",
        ),
        "mobile stolen and police refusing FIR saying lost report only": (
            "police_fir",
            "FIR / police inaction",
        ),
        "fake loan in my pan affecting cibil what legal action": (
            "banking_credit_dispute",
            "False loan / credit-report correction",
        ),
        "CIBIL showing loan which i never took": (
            "banking_credit_dispute",
            "False loan / credit-report correction",
        ),
    }

    for query, (category, label) in cases.items():
        route = route_matter(query)
        assert route.category == category, query
        assert route.label == label, query
        assert route.action_pack is not None, query


def test_stage_e8_real_prompt_route_precedence_regressions():
    fake_cbi = route_matter(
        "fake CBI parcel has drugs video call asking send 5 lakh need lawyer or police"
    )
    assert fake_cbi.category == "cyber_fraud_or_harassment"
    assert fake_cbi.label == "Fake authority / digital arrest payment fraud"
    assert any("Information Technology Act" in source for source in fake_cbi.required_sources)

    tinder = route_matter(
        "tinder match wala extortion gang met in bandra hotel took my phone need lawyer or police"
    )
    assert tinder.category == "cyber_fraud_or_harassment"
    assert tinder.label == "Dating-app extortion / phone seizure"
    assert any("Information Technology Act" in source for source in tinder.required_sources)

    mcoca = route_matter(
        "mcoca accused in custody 70 days no chargesheet can i file default bail"
    )
    assert mcoca.category == "criminal_defence_bail"
    assert mcoca.label == "Default bail / no chargesheet"
    assert any("Maharashtra Control of Organised Crime Act" in source for source in mcoca.required_sources)


def test_stage_e8_review_negation_guards_prevent_false_preemption():
    real_drug_parcel = route_matter(
        "police caught my drug parcel at airport no fake call no money demand what punishment"
    )
    assert real_drug_parcel.category == "criminal_defence_bail"
    assert real_drug_parcel.label == "NDPS / alleged drug possession defence"
    assert any("NDPS Act" in source for source in real_drug_parcel.required_sources)


def test_uapa_bail_variants_preempt_generic_undertrial_without_false_place_match():
    uapa_cases = [
        "urgent brother in jail 18 months UAPA bail when prima facie case made out kya hota how to complain",
        "brother in terror case 2 years no trial started can bail be filed 43d",
        "unlawful activities case brother in jail 18 months no trial bail possible",
        "uapa 43D(5) bail rejected prima facie true can high court help",
    ]
    for query in uapa_cases:
        route = route_matter(query)
        assert route.category == "criminal_defence_bail", query
        assert route.label == "UAPA bail / criminal defence", query
        assert any("Unlawful Activities" in source for source in route.required_sources), query

    nuapada_place = route_matter(
        "nuapada district jail 18 months bail when prima facie case made out"
    )
    assert nuapada_place.category == "criminal_defence_bail"
    assert nuapada_place.label != "UAPA bail / criminal defence"
    assert not any("Unlawful Activities" in source for source in nuapada_place.required_sources)

    pension_stopped = route_matter("pension stopped but no fraud call no otp")
    assert pension_stopped.category == "social_welfare_identity"
    assert pension_stopped.label == "Welfare benefit / identity record"

    no_msme = route_matter("buyer not paying invoice 9 lakh stuck no msme registration")
    assert no_msme.category == "business_contract_partnership"
    assert no_msme.label != "MSME delayed-payment / 43B(h) dispute"
    assert no_msme.label != "MSME / business delayed-payment dispute"


def test_family_alimony_and_notice_prompts_route_to_family_court_work():
    alimony = route_matter(
        "after divorce he is saying I cannot ask fr alimony because I was working before marriage too"
    )
    assert alimony.category == "family_marriage_status"
    assert alimony.label == "Matrimonial property / maintenance response"
    assert any("Family Courts" in source for source in alimony.required_sources)

    notice = route_matter(
        "got divorce notice from family court yesterday how do I respond need lawyer or police"
    )
    assert notice.category == "court_procedure"
    assert notice.label == "Family-court summons / appearance preparation"
    assert any("Family Courts" in source for source in notice.required_sources)


def test_common_property_and_employment_required_sources_are_fact_sensitive():
    tenant = route_matter("please help I am transwoman my landlord threw me out and kept my deposit")
    tenant_sources = " ".join(tenant.required_sources)
    assert tenant.category == "property_tenancy"
    assert "Registration Act only if" in tenant_sources
    assert "Transfer of Property Act lease" in tenant_sources

    oral_gift = route_matter("mother gave land to younger son verbally now older son disputing after 20 years")
    oral_sources = " ".join(oral_gift.required_sources)
    assert oral_gift.category == "property_tenancy"
    assert "Registration Act" in oral_sources
    assert "Registration Act only if" not in oral_sources

    overtime = route_matter("construction site delhi 14 hour work no overtime contractor laughing when i ask")
    overtime_sources = " ".join(overtime.required_sources)
    assert overtime.category == "employment_wages"
    assert "Code on Wages" in overtime_sources
    assert "Industrial Disputes Act only if" in overtime_sources

    retrenchment = route_matter("want to retrench 8 workers factory has 120 employees ludhiana garments need permission")
    retrenchment_sources = " ".join(retrenchment.required_sources)
    assert retrenchment.category == "employment_wages"
    assert "Industrial Disputes Act for termination" in retrenchment_sources
    assert "Code on Wages only if" in retrenchment_sources

    epf = route_matter("what to do epf number lost left job hyderabad 2019 want to withdraw money stuck")
    epf_sources = " ".join(epf.required_sources)
    assert epf.category == "employment_wages"
    assert "Employees Provident Funds" in epf_sources
    assert "Code on Wages only if" in epf_sources
    assert "Industrial Disputes Act only if" in epf_sources


def test_paraphrase_stress_routes_pds_and_domestic_safety():
    pds_queries = (
        "ration dealer deleted my mother from card without any written notice what complaint",
        "ration shop says name cancelled in system no notice no order how to complain and get records",
        "dealer stopped giving grain saying mother deleted from family card without notice",
        "ration office cut old mother name from household card how to get file and restore",
    )
    for query in pds_queries:
        route = route_matter(query)
        assert route.category == "social_welfare_identity", query
        joined_sources = " ".join(route.required_sources).lower()
        assert "national food security" in joined_sources
        assert "right to information" in joined_sources

    domestic_queries = (
        "spouse assaulted me today and keeps saying he will evict me from matrimonial home",
        "he slapped me in front of child and said get out today i have no place to stay",
        "my sasural people beat me tonight and not allowing me to call parents urgent help",
        "wife here husband punched me and threatening to remove me from shared house at night",
    )
    for query in domestic_queries:
        route = route_matter(query)
        assert route.category == "family_domestic", query
        joined_sources = " ".join(route.required_sources).lower()
        assert "pwdva" in joined_sources or "domestic" in joined_sources
        assert "bnss" in joined_sources or "crpc" in joined_sources


def test_blocker_paraphrases_route_to_child_access_or_criminal_defence():
    child_queries = (
        "my wife is stopping me from seeing my son after we separated",
        "court order not there but mother not allowing father to see child",
        "wife left matrimonial home with child and not sharing school location",
        "my ex took our child to her parents house and refuses weekend meeting",
        "my husband is hiding our son and not allowing video calls",
        "father wants to meet daughter but mother changed number after separation",
    )
    for query in child_queries:
        route = route_matter(query)
        assert route.category == "child_custody_adoption", query
        assert route.action_pack is not None
        assert "Family Court" in route.forums

    false_case_queries = (
        "business partner put false cheating 420 FIR against me for loan money",
        "relative filed fake 420 case because i could not repay money on time",
        "neighbour gave fake cheating complaint after property payment fight",
        "i got summons in fake 420 FIR from old business debt can police arrest",
        "police calling me in cheque money dispute saying 420 complaint is filed",
        "customer put cheating case on me for refund fight police called tomorrow",
    )
    for query in false_case_queries:
        route = route_matter(query)
        assert route.category == "criminal_defence_bail", query
        assert route.action_pack is not None
        assert route.action_pack.id == "criminal_defence_bail"


def test_heldout_common_safety_families_route_before_general_or_consumer_fallbacks():
    cases = {
        "finance company caller says they will tell my office and neighbours about loan": "banking_credit_dispute",
        "collection people came to my workplace shouting about emi default": "banking_credit_dispute",
        "someone recorded video call and says he will send to my relatives if i dont pay": "cyber_fraud_or_harassment",
        "online friend saved my private video and threatening to share in family group": "cyber_fraud_or_harassment",
        "they say my nani does black magic and want to parade her in village": "police_fir",
        "village panchayat called my mausi daayan and forced her to leave home": "police_fir",
        "bank marked lien on salary account because cyber case but no notice came": "banking_credit_dispute",
        "municipal staff took my fruit cart even though i have vending receipt": "street_vendor_municipal",
    }

    for query, expected in cases.items():
        route = route_matter(query)
        assert route.category == expected, query
        assert route.action_pack is not None, query
        assert route.category != "general_legal", query


def test_stage2_failed_family_routes_stay_specific():
    street_vendor = route_matter(
        "i have street vendor certificate but police took my cart near metro station"
    )
    assert street_vendor.category == "street_vendor_municipal"
    assert street_vendor.action_pack is not None
    assert street_vendor.action_pack.id == "street_vendor_municipal"

    recovery_agent = route_matter(
        "bank recovery agent took photos of my house can i complain"
    )
    assert recovery_agent.category == "banking_credit_dispute"
    assert recovery_agent.label == "Loan-app / recovery harassment"

    arrest = route_matter(
        "police has picked my son from my home in the night, i have not got FIR copy"
    )
    assert arrest.category == "arrest_custody_safeguard"
    assert "nearest Magistrate/criminal court" in arrest.forums

    senior = route_matter(
        "elderly mother is being forced out by children what law in my area"
    )
    assert senior.category == "senior_citizen"
    assert senior.action_pack is not None
    assert senior.action_pack.id == "senior_citizen"


def test_domestic_violence_common_user_prompts_are_high_urgency_safety_routes():
    for query in (
        "sasural waale mujhe ghar se nikal diya raat ko bina kuch diye kya main wapis ja sakti hoon",
        "please help he gets angry and slaps me but says sorry next day my parents say all marriages are like this should I stay",
        "ससुराल वाले मुझे घर से निकाल दिया, पति रोज मारता है",
    ):
        route = route_matter(query)

        assert route.category == "family_domestic"
        assert route.urgency in {"high", "emergency"}
        assert route.action_pack is not None
        assert route.action_pack.id == "family_domestic"
        assert any("PWDVA" in source for source in route.required_sources)
        assert "Protection Officer" in route.forums


def test_school_admission_with_birth_certificate_fact_routes_to_education_rights():
    route = route_matter("school denied admission saying no birth certificate but child passed test")

    assert route.category == "education_rights"
    assert route.action_pack is not None
    assert route.action_pack.id == "education_rights"
    assert any("Right of Children" in source for source in route.required_sources)


def test_safety_hardfail_common_prompts_route_to_specific_legal_workflows():
    school_tc = route_matter("sir school teacher demanding money to give TC to my son who failed where to go")
    assert school_tc.category == "education_rights"
    assert "district education officer" in school_tc.forums

    hindu_uncle = route_matter("pls tell uncle is 80 not married no children who inherits his self acquired prop hindu need lawyer or police")
    assert hindu_uncle.category == "succession_inheritance"
    assert any("Hindu Succession" in source for source in hindu_uncle.required_sources)

    icu_gift = route_matter("pls tell my dad signed prop to son under pressure when he was in icu can challenge need lawyer or police")
    assert icu_gift.category == "property_tenancy"
    assert icu_gift.label == "Property transfer under pressure / undue influence"
    assert "civil court" in icu_gift.forums


def test_self_harm_crisis_routes_before_legal_content():
    route = route_matter("I want to kill myself after the dowry harassment")
    assert route.category == "crisis_self_harm"
    assert route.urgency == "emergency"
    assert route.action_pack is not None
    assert route.action_pack.id == "self_harm_crisis"
    assert any("AASRA" in portal for portal in route.action_pack.portals)
    assert all("verified 2026-06-04" in portal for portal in route.action_pack.portals)

    mixed_route = route_matter("weather is bad and I want to kill myself")
    assert mixed_route.category == "crisis_self_harm"
    assert mixed_route.action_pack is not None
    assert mixed_route.action_pack.id == "self_harm_crisis"

    for query in (
        "मुझे मरने का मन कर रहा है dowry harassment",
        "मैं खुद को मारना चाहता हूं",
        "suicide karne ka mann ho raha hai",
    ):
        route = route_matter(query)
        assert route.category == "crisis_self_harm"
        assert route.action_pack is not None
        assert route.action_pack.id == "self_harm_crisis"


def test_completed_third_party_suicide_routes_to_legal_not_crisis_only():
    route = route_matter("company harassment made worker commit suicide family wants case")
    assert route.category != "crisis_self_harm"
    assert route.category in {"employment_wages", "criminal_general", "police_fir"}


def test_accused_sexual_offence_queries_do_not_route_to_survivor_forum():
    route = route_matter("my employee filed a pocso case against me what bail")
    assert route.category == "criminal_defence_bail"
    assert "accused" in route.label.lower()
    assert route.action_pack is not None
    assert route.action_pack.id == "criminal_defence_bail"
    assert "One Stop Centre" not in " ".join(route.forums)

    partner_route = route_matter("my girlfriend filed rape complaint what should I do")
    assert partner_route.category == "criminal_defence_bail"
    assert partner_route.action_pack is not None
    assert partner_route.action_pack.id == "criminal_defence_bail"

    helper_route = route_matter("student filed POCSO complaint that another teacher abused her")
    assert helper_route.category == "sexual_offence_survivor"
    assert helper_route.action_pack is not None
    assert helper_route.action_pack.id == "sexual_offence_survivor"


def test_will_future_tense_does_not_trigger_succession():
    route = route_matter("he will beat me if I complain")
    assert route.category != "succession_inheritance"
    assert route.category in {"police_fir", "criminal_general", "family_domestic"}

    fir_route = route_matter("will police register fir for stolen property if i have no bill")
    assert fir_route.category != "succession_inheritance"
    assert fir_route.category in {"police_fir", "criminal_general"}

    will_route = route_matter("Can I make a will for my property?")
    assert will_route.category == "succession_inheritance"

    for query in (
        "I want to prepare my will for my house",
        "Can I draft my will and register it?",
        "How do I register my will in Delhi?",
        "father has 4 children 2 daughters wants to make will giving more to caretaker daughter valid",
        "father wrote will but only registered one not latest one which is valid",
        "registered my will in sub registrar pune do i need to update it every year",
    ):
        route = route_matter(query)
        assert route.category == "succession_inheritance", query


def test_mact_and_physical_stalking_route_to_correct_forums():
    accident = route_matter("my bike hit pedestrian he is claiming 8 lakh in mact")
    assert accident.category == "motor_accident_claims"
    assert "Motor Accident Claims Tribunal" in accident.forums

    stalking = route_matter("a man is stalking me near my house every day what complaint")
    assert stalking.category == "police_fir"
    assert "police station" in stalking.forums

    stalks = route_matter("a man stalks me near my house every day what complaint")
    assert stalks.category == "police_fir"
    assert "police station" in stalks.forums

    offline_stalking = route_matter("my neighbour is stalking me physically not online what complaint")
    assert offline_stalking.category == "police_fir"
    assert "police station" in offline_stalking.forums

    online_stalks = route_matter("he stalks me on insta and sends dm daily after blocking")
    assert online_stalks.category == "cyber_fraud_or_harassment"


def test_python_job_title_does_not_make_wage_query_off_topic():
    route = route_matter("I am a Python developer, not paid for 3 months by employer")
    assert route.category != "off_topic"
    assert route.category in {"employment_wages", "labour_exploitation_discrimination"}


def test_wife_as_aggressor_does_not_use_pwdva_woman_protection_route():
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
        route = route_matter(query)

        assert route.category == "criminal_general"
        assert "PWDVA" not in " ".join(route.required_sources)
        assert route.action_pack is not None
        assert route.action_pack.id == "criminal_general"


def test_without_consent_property_phrase_does_not_trigger_marital_sexual_violence():
    property_route = route_matter("my wife sold my house without consent what to do")
    assert property_route.category == "criminal_general"
    assert property_route.label == "Spousal assault / financial-control complaint"

    sexual_route = route_matter("my husband forced sex without consent what to do")
    assert sexual_route.category == "family_domestic"
    assert sexual_route.label == "Marital sexual violence / domestic safety"


def test_wife_civil_property_and_maintenance_queries_are_not_criminalized():
    for query in (
        "my wife wants share in my house during divorce what to do",
        "my wife is asking maintenance and share in my property what to do",
    ):
        route = route_matter(query)

        assert route.category == "family_marriage_status"
        assert route.label == "Matrimonial property / maintenance response"
        assert route.legal_regime is None
        assert "BNS" not in " ".join(route.required_sources)
        assert "BNSS" not in " ".join(route.required_sources)


def test_spouse_household_expense_maintenance_routes_pwdva_as_support_not_criminal():
    route = route_matter(
        "my husband stopped paying household expenses after separation I am 38 can I ask maintenance"
    )

    joined_sources = " ".join(route.required_sources)
    assert route.category == "family_marriage_status"
    assert route.label == "Matrimonial property / maintenance response"
    assert "Family Courts Act" in joined_sources
    assert "Hindu Marriage Act" in joined_sources
    assert "PWDVA 2005 economic-abuse" in joined_sources
    assert "BNS" not in joined_sources
    assert "BNSS" not in joined_sources


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
    assert insurance_route.category == "consumer"
    assert "Companies Act" not in " ".join(insurance_route.required_sources)

    director_fir_route = route_matter("police not filed FIR against company director who cheated me")
    assert director_fir_route.category != "ibc_nclt"
    assert "Companies Act" not in " ".join(director_fir_route.required_sources)

    medical_negligence_route = route_matter("doctor gave antibiotics without prescription what can i do")
    assert medical_negligence_route.category != "business_license_compliance"
    assert "Drugs and Cosmetics Act" not in " ".join(medical_negligence_route.required_sources)


def test_tribal_hut_burning_refusal_is_not_land_transfer_action_pack():
    route = route_matter("adivasi house burned by land grabber thana refusing complaint")

    assert route.category == "tribal_caste_atrocity"
    assert route.label == "Caste / tribal rights / targeted violence"
    assert route.action_pack is not None
    assert route.action_pack.id == "tribal_caste_atrocity"


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
    assert not any("Atrocities" in source or "POA" in source for source in caste.required_sources)

    ration = route_matter("bpl ration card cancelled by panchayat in bihar without notice")
    assert ration.category == "social_welfare_identity"
    assert ration.label == "Ration card / PDS entitlement"
    assert any("National Food Security Act" in source for source in ration.required_sources)
    assert any("Right to Information Act" in source for source in ration.required_sources)

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


def test_milestone_b_routes_common_human_failures_to_actionable_buckets():
    cases = {
        "hospital operated wrong leg on my 80 yr old father now hospital says consent": (
            "consumer",
            "Medical negligence / hospital service deficiency",
        ),
        "complained about sexual harassment by my manager to HR and now he gave PIP bad rating": (
            "workplace_sexual_harassment",
            "Workplace sexual harassment",
        ),
        "PITA case only talking on phone with paying clients not meeting anyone take bookings": (
            "criminal_defence_bail",
            "ITPA call-handling / accused-risk clarification",
        ),
        "HDFC bank wrongly debited forex transaction no response what to do": (
            "banking_credit_dispute",
            "Bank debit / RBI Ombudsman complaint",
        ),
        "vit student caught with bhang lassi in mahabaleshwar holi is it ndps": (
            "criminal_defence_bail",
            "NDPS / alleged drug possession defence",
        ),
        "ration card cancelled due aadhaar mismatch BDO says renew what to do": (
            "social_welfare_identity",
            "Ration card / PDS entitlement",
        ),
    }

    for query, (category, label) in cases.items():
        route = route_matter(query)
        assert route.category == category, query
        assert route.label == label, query
        assert route.action_pack is not None, query
        assert route.required_sources, query
        assert route.forums, query


def test_priority_routes_avoid_surface_keyword_conflicts():
    assert route_matter("client cheque of 2 lakh bounced for my logo work how to send notice").category == "cheque_bounce"
    assert route_matter("my brother beaten in lockup constable took 20000 for bail still not released").category == "police_fir"
    assert route_matter("police beating my brother in lockup and not giving medical help").category == "police_fir"
    assert route_matter("my 14 year old girlfriend's father filed pocso on me I am 17 we were in relationship").category == "criminal_defence_bail"


def test_stage_500_postfix_routes_common_router_miss_variants():
    cases = {
        "boss cut provident fund from payslip but never deposited in EPFO, can I complain online": "employment_wages",
        "boiler blast killed my husband in factory owner paid nothing where should dependants file": "workplace_injury_compensation",
        "thekedar promised return fare from gurgaon to bihar but abandoned 12 workers": "labour_exploitation_discrimination",
        "contractor brought us from odisha to delhi then sent us home without journey allowance": "labour_exploitation_discrimination",
        "factory takes money for safety shoes every month but never gives shoes or receipt": "labour_exploitation_discrimination",
        "mining blast cracked my house walls and company says no compensation what forum": "environment_compensation",
    }
    for query, expected in cases.items():
        route = route_matter(query)
        assert route.category == expected, query
        assert route.action_pack is not None, query
        assert route.required_sources, query
        assert route.forums, query


def test_senior_maintenance_order_enforcement_beats_police_keyword():
    route = route_matter(
        "pls tell tribunal in tamil nadu ordered son to pay 10000 per month he stopped paying enforce kaise need lawyer or police"
    )

    assert route.category == "senior_citizen"
    assert route.label == "Senior citizen maintenance order enforcement"
    assert route.legal_regime is None
    assert any("Maintenance Tribunal" in forum for forum in route.forums)
    assert any("Senior Citizens Act" in source or "Senior Citizens" in source for source in route.required_sources)


def test_routes_handcuff_court_production_to_custody_safeguard():
    route = route_matter("brother in handcuffs taken to court as high security prisoner without reason")
    assert route.category == "arrest_custody_safeguard"
    assert route.urgency == "emergency"
    assert route.action_pack is not None


def test_generic_hr_harassment_pip_routes_to_employment_not_posh():
    route = route_matter(
        "i complained against my manager for harassment to HR and now they are putting me on PIP is this retaliation"
    )

    assert route.category == "employment_wages"
    assert route.action_pack is not None
    assert route.action_pack.id == "employment_wages"


def test_adult_son_violence_is_not_child_assault_route():
    for query in (
        "my son is 30 and beats his mother what complaint can we file",
        "my son beats his mother what complaint can we file",
    ):
        route = route_matter(query)
        assert route.label != "Child assault / household safety complaint"
        assert route.category in {"family_domestic", "criminal_general", "police_fir"}


def test_explicit_posh_retaliation_still_routes_to_workplace_sexual_harassment():
    route = route_matter(
        "i complained to ICC about sexual harassment and now manager put me on PIP"
    )

    assert route.category == "workplace_sexual_harassment"


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
    route = route_matter("upper caste people beat my husband called us chamar FIR not registering thana khunti jharkhand")
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


def test_routes_builder_occupancy_certificate_to_rera_consumer_workflow():
    for query in (
        "developer not giving occupancy certificate after taking full money",
        "builder delayed flat possession for 3 years what can i do",
        "rera registered project missed deadline how to complain",
    ):
        route = route_matter(query)
        assert route.category == "consumer", query
        assert "RERA" in route.label or "Builder" in route.label
        assert any("Real Estate" in source or "RERA" in source for source in route.required_sources)
        assert route.action_pack is not None


def test_negative_neighbor_common_prompts_route_to_user_specific_families():
    cases = {
        "ATM showed transaction failed but 10000 debited, branch says wait": "banking_credit_dispute",
        "IMPS status failed but money cut and beneficiary says not received": "banking_credit_dispute",
        "credit card annual fee charged though card was closed": "banking_credit_dispute",
        "bank says KYC pending so account is on hold": "banking_credit_dispute",
        "bank chargeback for failed online order not processed": "banking_credit_dispute",
        "college is not returning my original marksheets after I discontinued": "education_rights",
        "company kept my original degree certificate after I resigned": "employment_wages",
        "got fake Nike shoes from online seller": "consumer",
        "service centre refused warranty repair for my laptop": "consumer",
        "coaching centre promised refund but stopped replying": "consumer",
    }
    for query, category in cases.items():
        assert route_matter(query).category == category, query


def test_criminal_legacy_regime_for_old_incident_year():
    route = route_matter("false ipc 420 cheating case from 2020 can i get bail")
    assert route.category == "criminal_defence_bail"
    assert route.legal_regime == "legacy_ipc_crpc_evidence_for_pre_2024_incident"


def test_criminal_regime_handles_july_2024_cutover_phrases():
    legacy = "legacy_ipc_crpc_evidence_for_pre_2024_incident"
    current = "current_bns_bnss_bsa_for_post_2024_incident"
    cases = {
        "someone made deepfake video before 1 July 2024 and is blackmailing me": legacy,
        "someone made deepfake video before 01/07/2024 and is blackmailing me": legacy,
        "someone made deepfake video before 1/7/2024 and is blackmailing me": legacy,
        "someone made deepfake video prior to 1 July 2024 and is blackmailing me": legacy,
        "someone made deepfake video until 2024-07-01 and is blackmailing me": legacy,
        "someone made deepfake video pre July 2024 and is blackmailing me": legacy,
        "someone made deepfake video on 30 June 2024 and is blackmailing me": legacy,
        "someone made deepfake video on 1 July 2024 and is blackmailing me": current,
        "someone made deepfake video on 2 July 2024 and is blackmailing me": current,
    }
    for query, expected in cases.items():
        route = route_matter(query)
        assert route.category == "cyber_fraud_or_harassment"
        assert route.legal_regime == expected, query


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
        "fake porn video with my face on website how to remove and complain",
        "morphed group photo of my college girls hostel on reddit who to contact",
    ):
        route = route_matter(query)
        assert route.category == "cyber_fraud_or_harassment", query
        assert route.urgency == "emergency"


def test_routes_creator_paid_video_leak_to_cyber_not_general():
    route = route_matter("telegram channel leaked my onlyfans videos without permission what to do")

    assert route.category == "cyber_fraud_or_harassment"
    assert route.urgency in {"high", "emergency"}
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
    required = " ".join(route.required_sources)
    assert "Andhra Pradesh Rights in Land and Pattadar Pass Books Act 1971" in required
    assert "based on state" in required

    bribe = route_matter("patwari asking 5000 rupees to enter my name in revenue records can I complain")
    bribe_required = " ".join(bribe.required_sources)
    assert "Prevention of Corruption Act 1988" in bribe_required
    assert "state land revenue / record-of-rights law based on state" in bribe_required


def test_routes_fra_bamboo_patta_before_land_records():
    route = route_matter("patta given under FRA but forest guards still cutting our bamboo saying it is reserved bastar")
    assert route.category == "tribal_caste_atrocity"
    assert route.label == "Forest rights / FRA claim or forest produce"
    assert route.action_pack is not None
    assert route.action_pack.id == "forest_rights_fra"
    assert "police station" not in route.action_pack.escalation
    assert not any("Special Court" in forum for forum in route.action_pack.escalation)
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

    route = route_matter(
        "my 17 year nephew accused in pocso is in adult prison, school DOB proof available"
    )
    assert route.category == "criminal_defence_bail"
    assert route.urgency == "emergency"
    assert "Juvenile Justice Board" in route.forums

    route = route_matter(
        "17 year niece in adult jail court ignoring school age certificate what application"
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

    care_route = route_matter("pregnant woman undertrial byculla not getting hospital checkup where to go")
    assert care_route.category == "criminal_defence_bail"
    assert care_route.label == "Custody medical care / interim bail"
    assert any("Article 21" in source for source in care_route.required_sources)


def test_routes_migrant_surety_hardship_to_bail_condition():
    route = route_matter("court asked two local sureties we are migrants what to do")

    assert route.category == "criminal_defence_bail"
    assert route.label == "Bail surety / bond hardship"
    assert route.action_pack is not None
    assert route.action_pack.id == "criminal_defence_bail"

    high_amount_route = route_matter("uncle got bail order but jail not releasing because surety amount high what can i do")
    assert high_amount_route.category == "criminal_defence_bail"
    assert high_amount_route.label == "Bail surety / bond hardship"

    terse_high_amount_route = route_matter("surety amount high")
    assert terse_high_amount_route.category == "criminal_defence_bail"
    assert terse_high_amount_route.label == "Bail surety / bond hardship"


def test_routes_court_procedure_question():
    route = route_matter("how do I address the judge in district court your honour or my lord")
    assert route.category == "court_procedure"
    assert route.urgency == "low"


def test_routes_family_court_summon_paraphrases_to_specialist_procedure():
    cases = [
        "urgent mera family court summon aya hai counselling likha hai kya leke jana hai lawyer nahi hai",
        "summon from family court in divorce matter received today before advocate what first step",
    ]

    for query in cases:
        route = route_matter(query)
        assert route.category in {"court_procedure", "family_domestic"}, query
        assert any("Family Courts Act" in source for source in route.required_sources)


def test_routes_general_mediation_act_query_to_court_procedure():
    route = route_matter("urgent how to initiate mediation under Mediation Act 2023 without going to court how to complain")
    assert route.category == "court_procedure"
    assert route.label == "Mediation procedure / legal-aid route"
    assert any("Mediation Act 2023" in source for source in route.required_sources)
    assert "District Legal Services Authority" in route.forums


def test_without_going_to_court_alone_does_not_trigger_mediation_route():
    examples = {
        "how to get mutual divorce without going to court": "family_marriage_status",
        "company not paying salary how to complain without going to court": "employment_wages",
        "landlord not returning deposit how to settle without going to court": "property_tenancy",
    }
    for query, expected_category in examples.items():
        route = route_matter(query)
        assert route.category == expected_category, query
        assert route.label != "Mediation procedure / legal-aid route"


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
    for query in ("brother in NDPS case arrested 110 days no chargesheet default bail possible",):
        route = route_matter(query)
        assert route.category == "criminal_defence_bail", query
        assert route.urgency == "high"
        assert route.action_pack is not None

    uapa_route = route_matter("brother arrested in UAPA 100 days no chargesheet default bail possible")
    assert uapa_route.category == "criminal_defence_bail"
    assert uapa_route.urgency == "high"
    assert uapa_route.action_pack is not None
    assert any("Unlawful Activities" in source and "43D" in source for source in uapa_route.required_sources)


def test_stage_e6_uapa_prima_facie_bail_requires_uapa_authority():
    route = route_matter("uapa 18 months bail prima facie case made out")

    assert route.category == "criminal_defence_bail"
    assert any("Unlawful Activities" in source and "43D" in source for source in route.required_sources)


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


def test_pf_default_route_uses_epfo_sources_not_generic_wage_sources():
    route = route_matter("factory deducted provident fund but passbook shows zero")
    assert route.category == "employment_wages"
    assert route.label == "PF / EPFO contribution default"
    required = " ".join(route.required_sources)
    assert "Employees Provident Funds" in required
    assert "Code on Social Security" in required
    assert "Industrial Disputes" not in required


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


def test_paid_creator_video_leak_routes_to_copyright_takedown_not_general():
    route = route_matter("telegram channel leaked my paid video content without permission how to take it down")
    assert route.category == "trademark_ip"
    assert route.label == "Copyright / platform takedown"
    assert any("Copyright Act 1957" in source for source in route.required_sources)
    assert not any(source == "Trade Marks Act 1999" for source in route.required_sources)

    remix_route = route_matter("i used 20 seconds of a bollywood song in my review video and got copyright strike what can i do")
    assert remix_route.category == "trademark_ip"
    assert remix_route.label == "Copyright / platform takedown"

    reel_route = route_matter("fake influencer used my reel got 2M views without credit copyright bhai")
    assert reel_route.category == "trademark_ip"
    assert reel_route.label == "Copyright / platform takedown"
    assert any("Copyright Act 1957" in source for source in reel_route.required_sources)
    assert not any(source == "Trade Marks Act 1999" for source in reel_route.required_sources)

    influencer_defamation = route_matter("instagram influencer made false claim about my shop and customers stopped coming")
    assert influencer_defamation.label != "Copyright / platform takedown"

    account_suspension = route_matter("instagram suspended my account after some claim by influencer but no copyright issue")
    assert account_suspension.label != "Copyright / platform takedown"


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
    assert _has_text(route.required_sources, "MGNREGA 2005")
    assert not _has_text(route.required_sources, "Code on Wages")
    widow_job_card = route_matter("odisha nuapada panchayat not issuing job card to widow family")
    assert widow_job_card.category == "labour_exploitation_discrimination"
    assert _has_text(widow_job_card.required_sources, "MGNREGA 2005")
    assert _has_text(widow_job_card.forums, "MGNREGA")
    assert not _has_text(widow_job_card.required_sources, "Code on Wages")
    portal_paid = route_matter("mgnrega portal paid but passbook zero credit what proof need")
    assert portal_paid.category == "labour_exploitation_discrimination"
    assert _has_text(portal_paid.required_sources, "MGNREGA 2005")
    assert _has_text(portal_paid.required_sources, "Right to Information")
    assert not _has_text(portal_paid.required_sources, "Code on Wages")
    route2 = route_matter("contractor taking us to other state for work keeping our cards passport")
    assert route2.category == "bonded_labour_rescue"
    assert route2.urgency == "high"
    assert route_matter("site supervisor saying minimum wage 350 only but karnataka rate is 600 construction unskilled").category == "labour_exploitation_discrimination"
    assert route_matter("I am ASHA worker not paid honorarium 6 months who can help").category == "employment_wages"
    asha = route_matter("health department not paying covid duty incentive to asha what can i do")
    assert asha.category == "employment_wages"
    assert asha.label == "ASHA incentive / NHM payment"
    asha_cross_noise = route_matter("asha worker incentive pending but block office says ask anganwadi cdpo where to complain")
    assert asha_cross_noise.category == "employment_wages"
    assert asha_cross_noise.label == "ASHA incentive / NHM payment"
    anganwadi = route_matter("anganwadi helper honorarium pending how to complain")
    assert anganwadi.category == "employment_wages"
    assert anganwadi.label == "Anganwadi honorarium / ICDS payment"
    anganwadi_cross_noise = route_matter("anganwadi worker payment pending but officer called it asha nhm file where to complain")
    assert anganwadi_cross_noise.category == "employment_wages"
    assert anganwadi_cross_noise.label == "Anganwadi honorarium / ICDS payment"
    assert route_matter("principal employer reliance site contractor ran away with 4 months wages 22 workers what to do").category == "labour_exploitation_discrimination"


def test_stage_failure_families_route_to_specific_workflows():
    passport = route_matter("police not clearing passport verification asking money")
    assert passport.category == "passport_police_verification"
    assert passport.urgency == "high"
    assert _has_text(passport.required_sources, "Passports Act")
    assert _has_text(passport.required_sources, "Prevention of Corruption")

    aadhaar_loan = route_matter("someone used my aadhaar and took loan in my name")
    assert aadhaar_loan.category == "cyber_fraud_or_harassment"
    assert aadhaar_loan.urgency == "high"
    assert _has_text(aadhaar_loan.required_sources, "Aadhaar Act")
    assert _has_text(aadhaar_loan.required_sources, "Credit Information")

    senior_food = route_matter("my father is old and son not giving food or medicine")
    assert senior_food.category == "senior_citizen"
    assert senior_food.urgency == "high"
    assert _has_text(senior_food.required_sources, "Senior Citizens Act")

    tribal_transfer = route_matter("tribal family land transferred by moneylender using blank paper")
    assert tribal_transfer.category == "tribal_caste_atrocity"
    assert _has_text(tribal_transfer.required_sources, "PESA")
    assert _has_text(tribal_transfer.required_sources, "scheduled-area")

    education_deadline = route_matter("student education loan rejected and admission deadline is tomorrow")
    assert education_deadline.category == "education_loan_denial"
    assert education_deadline.urgency == "high"

    certificate_deadline = route_matter("OBC certificate pending and scholarship deadline is tomorrow")
    assert certificate_deadline.category == "social_welfare_identity"
    assert certificate_deadline.urgency == "high"


def test_reviewer_counterexamples_do_not_overroute_or_mix_workflows():
    pan_loan = route_matter("someone used my pan only and took loan in my name")
    assert pan_loan.category == "cyber_fraud_or_harassment"
    assert pan_loan.label == "Aadhaar/PAN identity misuse / fake loan"

    residence = route_matter("husband family threw me from shared house and kept my documents")
    assert residence.category == "family_domestic"
    assert "residence" in residence.label.lower()

    asha_login = route_matter("health department ASHA software login not working")
    assert asha_login.category != "employment_wages"

    supplier_payment = route_matter("ICDS nutrition supplier payment pending")
    assert supplier_payment.category == "business_contract_partnership"


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
    assert route_matter("my bank account is frozen what to do").label == "Bank account freeze / lien / KYC hold"
    for query in (
        "my instagram account is frozen what to do",
        "my zerodha account is frozen what to do",
        "my binance account frozen kyc pending what to do",
        "my youtube account frozen payout held what to do",
        "my google account blocked what legal remedy",
    ):
        assert route_matter(query).label != "Bank account freeze / lien / KYC hold", query
    assert route_matter("Loan app is harassing my contacts").label == "Loan-app / recovery harassment"
    assert route_matter("My shop is in Gujarat and municipality sealed it.").label == "Municipal sealing / shop closure notice"
    assert route_matter("my pan and aadhaar is mismatch").label == "PAN/Aadhaar mismatch / identity linking"
    assert route_matter("death certificate has wrong name hospital says they cannot correct it what is process").category == "social_welfare_identity"
    assert route_matter("kanya vivah scheme money not given by government after my daughter wedding").category == "social_welfare_identity"
    assert route_matter("my husband died in army no service pension widow what papers needed").category == "social_welfare_identity"
    assert route_matter("recovery agents from a NBFC visited my office and shouted in front of colleagues").category == "banking_credit_dispute"
    assert route_matter("i am 73 christian widow can my stepchildren claim share in husband self acquired property").category == "succession_inheritance"
    for query in (
        "pls tell i am christian widow in kerala husband died without will how prop divides among children need lawyer or police",
        "christian widow husband died no will how to divide estate between children should i go police",
        "my christian husband died intestate how property division among children in kerala",
        "christian widow property case after husband death without will what papers to take to dlsa",
        "my late husband was christian no will his children from first wife say i get nothing is this legal",
    ):
        route = route_matter(query)
        assert route.category == "succession_inheritance", query
        assert route.legal_regime is None, query
        assert "criminal" not in route.label.lower(), query
    assert route_matter("my husband had affair I caught them I slapped the woman now she is filing case on me what to do").category == "criminal_defence_bail"
    assert route_matter("fake call from sbi pension office took 2 lakh from my account 75 yr father").category == "cyber_fraud_or_harassment"
    assert route_matter("vendor zone bhopal allotted me 2018 now hawker inspector saying pay 2000 every month otherwise remove").category == "street_vendor_municipal"


def test_stage1_fresh_ui_real_fallback_clusters_route_to_specific_paths():
    cases = {
        "Bajaj recovery man came to my society and shouted about EMI in front of neighbours": (
            "banking_credit_dispute",
            "loan_app_harassment",
        ),
        "bajaj collection agent shouted about my EMI in society lift lobby": (
            "banking_credit_dispute",
            "loan_app_harassment",
        ),
        "my wife refuses physical relationship for 3 years but I do not want to force her": (
            "family_marriage_status",
            "marriage_breakdown",
        ),
        "husband says no physical relationship for years and I will not force anything what legal options": (
            "family_marriage_status",
            "marriage_breakdown",
        ),
        "someone posted my phone number on dating app and strangers are calling me": (
            "cyber_fraud_or_harassment",
            "cyber",
        ),
        "unknown person shared my mobile number on dating app and strangers keep calling": (
            "cyber_fraud_or_harassment",
            "cyber",
        ),
        "IMPS transfer failed beneficiary did not get money but bank deducted amount": (
            "banking_credit_dispute",
            "banking_credit_dispute",
        ),
        "imps failed and beneficiary did not get money but amount deducted from bank": (
            "banking_credit_dispute",
            "banking_credit_dispute",
        ),
        "college is holding my original certificates after I left the course": (
            "education_rights",
            "education_rights",
        ),
        "private college withholding original certificates after course withdrawal": (
            "education_rights",
            "education_rights",
        ),
        "I found my wife living with another man after marriage what case can I file": (
            "family_marriage_status",
            "marriage_breakdown",
        ),
        "husband is staying with another woman after marriage what family court option": (
            "family_marriage_status",
            "marriage_breakdown",
        ),
        "PAN photocopy leaked in Telegram and someone opened bank account using it": (
            "cyber_fraud_or_harassment",
            "cyber",
        ),
        "pan copy leaked on telegram and fake bank account opened in my name": (
            "cyber_fraud_or_harassment",
            "cyber",
        ),
    }

    for query, (category, action_pack) in cases.items():
        route = route_matter(query)
        assert route.category == category, query
        assert route.action_pack is not None, query
        assert route.action_pack.id == action_pack, query


def test_stage1_negative_controls_do_not_overclaim_harassment_or_heir_sale():
    normal_reminder = route_matter(
        "loan app installed but only sends normal due date reminder, no threats or contacts"
    )
    assert normal_reminder.category == "banking_credit_dispute"
    assert normal_reminder.action_pack is not None
    assert normal_reminder.action_pack.id != "loan_app_harassment"
    assert normal_reminder.legal_regime is None

    tenancy = route_matter("tenant not leaving my inherited house but no sale dispute among heirs")
    assert tenancy.category == "property_tenancy"
    assert tenancy.action_pack is not None
    assert tenancy.action_pack.id == "tenancy_eviction_nonpayment"


def test_stage2_money_identity_failures_route_to_deterministic_families():
    cases = {
        "IMPS transfer failed beneficiary did not get money but bank deducted amount": (
            "banking_credit_dispute",
            "banking_credit_dispute",
        ),
        "credit card charged annual fee twice and support closed my complaint": (
            "banking_credit_dispute",
            "banking_credit_dispute",
        ),
        "my salary account has lien after cyber complaint but bank is not giving order copy": (
            "banking_credit_dispute",
            "bank_account_freeze",
        ),
        "CIBIL shows fake loan from NBFC but signature is not mine": (
            "banking_credit_dispute",
            "banking_credit_dispute",
        ),
        "my Aadhaar was used to issue SIM and now fraud calls are linked to me": (
            "cyber_fraud_or_harassment",
            "cyber",
        ),
        "loan app people are calling my boss and saying I am fraud": (
            "banking_credit_dispute",
            "loan_app_harassment",
        ),
        "PAN photocopy leaked in Telegram and someone opened bank account using it": (
            "cyber_fraud_or_harassment",
            "cyber",
        ),
        "someone posted my phone number on dating app and strangers are calling me": (
            "cyber_fraud_or_harassment",
            "cyber",
        ),
    }

    for query, (category, action_pack) in cases.items():
        route = route_matter(query)
        assert route.category == category, query
        assert route.action_pack is not None, query
        assert route.action_pack.id == action_pack, query


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


def test_common_user_smoke_routes_from_ui_screenshots():
    cases = {
        "brother and i bought a plot together 10 years back, now he has sold it, what can i do": ("property_tenancy", "property_tenancy"),
        "my daughter school admission is denied, despite her clearing admission exam": ("education_rights", "education_rights"),
        "police has picked my son from my home in the night, i have not got FIR copy": ("arrest_custody_safeguard", "arrest_custody_safeguard"),
        "My bike is stolen, police is not filing FIR": ("police_fir", "police_fir"),
        "My wife denies sex from last 1 year, what to do": ("family_marriage_status", "marriage_breakdown"),
        "My wife is denying sex since many years, what to do": ("family_marriage_status", "marriage_breakdown"),
        "My husband told lies before marriage about his job and his salary, what to do": ("family_marriage_status", "marriage_misrepresentation"),
        "My tenant is not vacating house and not paying rent": ("property_tenancy", "tenancy_eviction_nonpayment"),
        "i caught my husband with another women having sex": ("family_marriage_status", "marriage_breakdown"),
        "My brother is not returning my money, which he took loan": ("business_contract_partnership", "personal_money_recovery"),
        "Can I sell property if one legal heir is not agreeing?": ("property_tenancy", "property_tenancy"),
        "Bank deducted money wrongly and customer care not helping.": ("banking_credit_dispute", "banking_credit_dispute"),
        "UPI failed but amount debited bank and app blaming each other what to do": ("banking_credit_dispute", "banking_credit_dispute"),
    }

    for query, (category, action_pack) in cases.items():
        route = route_matter(query)
        assert route.category == category, query
        assert route.action_pack is not None, query
        assert route.action_pack.id == action_pack, query


def test_common_user_gate_failure_clusters_route_to_specific_action_packs():
    cases = {
        "bank reversed my balance saying technical error but not giving reason": (
            "banking_credit_dispute",
            "banking_credit_dispute",
        ),
        "salary account blocked by bank saying police request no notice": (
            "banking_credit_dispute",
            "bank_account_freeze",
        ),
        "my upi account frozen and branch not giving complaint number": (
            "banking_credit_dispute",
            "bank_account_freeze",
        ),
        "online loan app calling my relatives and abusing me": (
            "banking_credit_dispute",
            "loan_app_harassment",
        ),
        "instant loan app sending my photo to contacts saying fraud": (
            "banking_credit_dispute",
            "loan_app_harassment",
        ),
        "loan app threatening to make morphed nude photo if I dont pay today": (
            "cyber_fraud_or_harassment",
            "cyber",
        ),
        "private hospital not giving medical records after discharge": (
            "consumer",
            "consumer",
        ),
        "hospital overcharged me and not giving detailed bill": (
            "consumer",
            "consumer",
        ),
        "municipality removed my tea cart from footpath without notice": (
            "street_vendor_municipal",
            "street_vendor_municipal",
        ),
        "local body locked my commercial shop saying licence problem": (
            "business_license_compliance",
            "municipal_shop_sealing",
        ),
        "biometric failed so dealer refused wheat and rice": (
            "social_welfare_identity",
            "social_welfare_identity",
        ),
        "manager sends dirty messages and HR says ignore": (
            "workplace_sexual_harassment",
            "workplace_sexual_harassment",
        ),
        "colleague asking for dinner and promotion favour what complaint": (
            "workplace_sexual_harassment",
            "workplace_sexual_harassment",
        ),
        "elderly mother is being forced out by children what law": (
            "senior_citizen",
            "senior_citizen",
        ),
        "relative took hand loan 2 years back no agreement what can i do": (
            "business_contract_partnership",
            "personal_money_recovery",
        ),
        "my wife is in relationship with another man what legal action": (
            "family_marriage_status",
            "marriage_breakdown",
        ),
        "unknown person posting my number on dating app": (
            "cyber_fraud_or_harassment",
            "cyber",
        ),
        "education loan subsidy not given by bank what complaint": (
            "education_loan_denial",
            "education_loan_denial",
        ),
        "scooter stolen from parking station says give written complaint only": (
            "police_fir",
            "police_fir",
        ),
    }

    for query, (category, action_pack) in cases.items():
        route = route_matter(query)
        assert route.category == category, query
        assert route.action_pack is not None, query
        assert route.action_pack.id == action_pack, query
        assert route.required_sources, query
        assert route.forums, query


def test_common_user_gate_broad_keyword_overroute_guards():
    hostel_fee = route_matter("college deducted hostel fee wrongly and not reversing amount")
    assert hostel_fee.category != "banking_credit_dispute"

    market_shop = route_matter("municipality fined my market shop for signboard licence")
    assert market_shop.category == "business_license_compliance"
    assert market_shop.category != "street_vendor_municipal"

    dating_after_divorce = route_matter("can i use dating app after divorce")
    assert dating_after_divorce.category != "cyber_fraud_or_harassment"

    gift_no_agreement = route_matter("friend gave me money as gift no agreement can he ask back")
    assert gift_no_agreement.action_pack is None or gift_no_agreement.action_pack.id != "personal_money_recovery"


def test_stage5_money_cyber_identity_paraphrase_routes_with_negatives():
    cases = {
        "PhonePe transaction failed but money cut from my SBI account and merchant says ask bank": (
            "banking_credit_dispute",
            "banking_credit_dispute",
        ),
        "UPI transfer failed yesterday money deducted no refund and customer care closed ticket": (
            "banking_credit_dispute",
            "banking_credit_dispute",
        ),
        "bank deducted maintenance charge twice and branch is not giving complaint number": (
            "banking_credit_dispute",
            "banking_credit_dispute",
        ),
        "HDFC wrongly charged forex markup twice on card and support says wait 45 days": (
            "banking_credit_dispute",
            "banking_credit_dispute",
        ),
        "bank says my account frozen for KYC pending, no police case, what complaint can I file": (
            "banking_credit_dispute",
            "bank_account_freeze",
        ),
        "ICICI put lien on savings account saying cyber cell email but not sharing FIR number": (
            "banking_credit_dispute",
            "bank_account_freeze",
        ),
        "ED freeze marked on my current account, bank only says legal hold, how to get order copy": (
            "banking_credit_dispute",
            "bank_account_freeze",
        ),
        "fake CBI video call said my Aadhaar used in drug parcel and made me transfer 2 lakh": (
            "cyber_fraud_or_harassment",
            "cyber",
        ),
        "fake TRAI call says sim will close and asked to join police video call": (
            "cyber_fraud_or_harassment",
            "cyber",
        ),
        "fake video of prime minister outside election is circulating, party workers threatening me": (
            "cyber_fraud_or_harassment",
            "cyber",
        ),
        "Ola deducted cancellation fee twice from wallet, support bot not helping": (
            "consumer",
            "consumer",
        ),
        "PAN card copy leaked online and fake bank account opened in my name": (
            "cyber_fraud_or_harassment",
            "cyber",
        ),
        "friend made fake AI video of minister as joke and now IT cell says FIR": (
            "cyber_fraud_or_harassment",
            "cyber",
        ),
        "customer care says failed UPI refund will come after 30 days, can I complain now": (
            "banking_credit_dispute",
            "banking_credit_dispute",
        ),
    }

    for query, (category, action_pack) in cases.items():
        route = route_matter(query)
        assert route.category == category, query
        assert route.action_pack is not None, query
        assert route.action_pack.id == action_pack, query

    upi_fraud = route_matter("OTP shared by mistake and 50000 gone, bank says customer negligence no refund")
    assert upi_fraud.category == "cyber_fraud_or_harassment"
    assert upi_fraud.action_pack is not None
    assert upi_fraud.action_pack.id == "cyber"

    cab_driver = route_matter("Ola driver account deactivated and payout wallet frozen after low rating")
    assert cab_driver.category == "digital_platform_account"
    assert cab_driver.action_pack is not None
    assert cab_driver.action_pack.id == "digital_platform_account"

    pan_mismatch = route_matter("my PAN name has spelling mistake but Aadhaar is correct, bank KYC failed")
    assert pan_mismatch.category == "social_welfare_identity"
    assert pan_mismatch.action_pack is not None
    assert pan_mismatch.action_pack.id == "social_welfare_identity"


def test_common_user_smoke_route_guards_do_not_overfit_family_words():
    solo_sale_tax = route_matter("my brother sold his own plot what tax applies")
    assert solo_sale_tax.category == "tax_gst_compliance"
    assert solo_sale_tax.label != "Joint property sale / co-owner dispute"

    not_married_yet = route_matter(
        "my fiance lied about salary before marriage but we are not married yet what can i do"
    )
    assert not_married_yet.category != "family_marriage_status" or (
        not_married_yet.action_pack is not None
        and not_married_yet.action_pack.id != "marriage_misrepresentation"
    )

    for query in (
        "I caught my husband stealing my jewellery",
        "I caught my husband with another woman stealing my jewellery",
        "I caught my wife with another man taking drugs",
    ):
        route = route_matter(query)
        assert route.label != "Marriage breakdown / adultery facts", query
        assert route.action_pack is None or route.action_pack.id != "marriage_breakdown", query

    drug_route = route_matter("I caught my husband with drugs")
    assert drug_route.category == "criminal_general"
    assert drug_route.label == "Household drug-possession safety concern"
    assert drug_route.action_pack is not None
    assert drug_route.action_pack.id == "drug_safety_complaint"

    for query in (
        "my husband is addicted to drugs how can I get help",
        "my son is taking drugs and needs treatment what can I do",
    ):
        route = route_matter(query)
        assert route.category == "drug_treatment_support", query
        assert route.label == "Drug addiction / de-addiction support", query
        assert route.action_pack is not None
        assert route.action_pack.id == "drug_treatment_support", query

    child_route = route_matter("I caught my wife beating my child")
    assert child_route.category == "criminal_general"
    assert child_route.label == "Child assault / household safety complaint"
    assert child_route.action_pack is not None
    assert child_route.action_pack.id == "child_safety_assault"


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


def test_routes_factory_smoke_ngt_pil_to_environment_not_general():
    cases = [
        "factory smoke making us sick should i go ngt or high court pil first what proof needed",
        "nearby factory smoke causing cough can residents file NGT or PIL what evidence to keep",
        "industrial air pollution from plant children getting sick proof for pollution board and NGT",
    ]

    for query in cases:
        route = route_matter(query)
        assert route.category == "environment_compensation", query
        assert route.action_pack is not None
        assert "general" not in route.category


def test_routes_market_vendor_license_fine_to_street_vendor():
    route = route_matter("fish market vendor cochin license panchayat only kerala municipal saying pay 5000 fine illegal")
    assert route.category == "street_vendor_municipal"

    challan_bribe = route_matter("street vendor paid challan fine but inspector asking cash bribe every month")
    assert challan_bribe.category == "street_vendor_municipal"
    assert "traffic" not in challan_bribe.label.lower()
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


def test_gratuity_eligibility_route_requires_gratuity_not_generic_wage_sources():
    route = route_matter("section 4 gratuity eligibility 4 years 11 months service where to go")

    assert route.category == "employment_wages"
    assert any("Payment of Gratuity Act 1972" in source for source in route.required_sources)
    assert not any(source == "Payment of Wages Act / Code on Wages" for source in route.required_sources)


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


def test_routes_lgbtq_identity_arrest_to_liberty_safeguard():
    route = route_matter("police arrested my son for being gay")
    assert route.category == "arrest_custody_safeguard"
    assert route.label == "LGBTQ identity arrest / custody safeguard"
    assert route.urgency == "emergency"
    assert any("Navtej" in source for source in route.required_sources)


def test_routes_typo_insurer_rejection_to_consumer_insurance():
    route = route_matter("INSURERER IS REJECTING MY CLAIM")
    assert route.category == "consumer"
    assert route.label == "Insurance claim / service deficiency"
    assert any("Insurance Ombudsman" in source for source in route.required_sources)


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

    tribal = route_matter("tribal woman called witch and beaten in gumla police refused FIR")
    assert tribal.category == "tribal_caste_atrocity"
    assert tribal.action_pack is not None
    assert tribal.action_pack.id == "tribal_caste_atrocity"

    written_threat = route_matter("people wrote witch on our door and threatened my mother at night what complaint can we file")
    assert written_threat.category == "police_fir"

    public_stripping = route_matter("ojha branded my aunt witch and stripped her in public")
    assert public_stripping.category == "police_fir"
    assert public_stripping.urgency == "emergency"


def test_routes_business_license_renewal():
    route = route_matter("tamil nadu shop license renewal pending 2 years coimbatore shopkeeper penalty")
    assert route.category == "business_license_compliance"
    assert route.action_pack is not None


def test_routes_posh_retaliation_after_icc_complaint():
    route = route_matter("after I complained to ICC against my reporting manager he is now giving me bad rating and PIP")
    assert route.category == "workplace_sexual_harassment"

    hr_route = route_matter(
        "i complained against my manager for harassment to HR and now they are putting me on PIP, is this retaliation"
    )
    assert hr_route.category == "employment_wages"


def test_routes_fra_ifr_title_for_gond_widow():
    route = route_matter("i am gond woman my husband died forest officer not giving me IFR title dindori")
    assert route.category == "tribal_caste_atrocity"
    assert route.label == "Forest rights / FRA claim or forest produce"


def test_routes_tribal_land_transfer_with_revenue_forums():
    route = route_matter("tribal land sold to non tribal by uncle without our consent is it legal")
    assert route.category == "tribal_caste_atrocity"
    assert "land transfer" in route.label.lower()
    assert route.action_pack is not None
    assert route.action_pack.id == "tribal_land_transfer_restoration"
    assert "police station" not in route.action_pack.escalation
    assert not any("Special Court" in forum for forum in route.action_pack.escalation)
    assert any("Collector" in forum or "revenue" in forum for forum in route.forums)


def test_routes_tribal_mutation_to_land_transfer_not_generic_scst():
    route = route_matter("can u tell patwari changed mutation record giving my dadaji land to non tribal buyer nuapada odisha what can i do")
    assert route.category == "tribal_caste_atrocity"
    assert route.label == "Tribal land transfer / restoration"
    assert any("Scheduled Area" in source or "Fifth Schedule" in source for source in route.required_sources)


def test_routes_fra_claim_rejection_to_fra_not_generic_scst():
    for query in (
        "i am adivasi woman my IFR claim form rejected because no signature of husband bastar what can i do",
        "gram sabha passed my IFR claim but SDLC rejected without reason what to do gadchiroli",
    ):
        route = route_matter(query)
        assert route.category == "tribal_caste_atrocity"
        assert route.label == "Forest rights / FRA claim or forest produce"
        assert any("Forest Rights Act" in source for source in route.required_sources)


def test_recent_forest_encroachment_notice_routes_to_forest_authority_not_fra():
    route = route_matter(
        "forest guard says I recently encroached forest land last month and gave notice what forum should I approach"
    )
    assert route.category == "environment_compensation"
    assert route.label == "Forest land notice / forest authority"
    assert "Forest Rights Act only if" in " ".join(route.required_sources)


def test_routes_palli_sabha_coal_block_to_tribal_project_consent():
    route = route_matter("land acquired for coal block without consulting palli sabha angul odisha what can i do")
    assert route.category == "environment_compensation"
    assert route.label == "Tribal project displacement / Gram Sabha consent"
    assert any("PESA" in source for source in route.required_sources)


def test_routes_minor_mineral_gram_sabha_without_rfctlarr_rr():
    route = route_matter("sand mining lease given without gram sabha consent in scheduled area")
    assert route.category == "environment_compensation"
    assert route.label == "Minor mineral / Gram Sabha recommendation"
    assert route.action_pack and route.action_pack.id == "minor_mineral_gram_sabha"
    assert any("PESA" in source and "4(c)" in source for source in route.required_sources)
    assert any("Mines and Minerals" in source for source in route.required_sources)
    assert not any("RFCTLARR" in source or "rehabilitation" in source.lower() for source in route.required_sources)


def test_routes_forest_minor_produce_to_tribal_rights():
    route = route_matter("forest officer stopped us collecting tendu leaves in community forest")
    assert route.category == "tribal_caste_atrocity"


def test_generic_forest_vehicle_seizure_does_not_route_to_tribal_rights():
    route = route_matter("forest officer seized my truck for timber transport")
    assert route.category != "tribal_caste_atrocity"


def test_routes_dlsa_query_to_legal_aid_before_family():
    route = route_matter("free legal aid for woman domestic violence case how to apply in dlsa")
    assert route.category == "legal_aid"


def test_bpl_legal_aid_query_is_not_ration_pds():
    route = route_matter("urgent bPL card holder eligibility for free legal aid from DLSA SLSA how to complain")
    assert route.category == "legal_aid"
    assert route.label == "Legal aid eligibility / DLSA support"
    assert any("Legal Services Authorities Act" in source for source in route.required_sources)
    assert not any("National Food Security Act" in source for source in route.required_sources)


def test_ration_cancellation_still_routes_to_nfsa_after_legal_aid_guard():
    route = route_matter("bpl ration card cancelled by panchayat in bihar without notice")
    assert route.category == "social_welfare_identity"
    assert route.label == "Ration card / PDS entitlement"
    assert any("National Food Security Act" in source for source in route.required_sources)


def test_civil_court_summons_beats_police_notice_collision():
    route = route_matter(
        "court sent summons for witness evidence in my civil case and asked to bring documents, is this BNSS 35 police notice"
    )

    assert route.category == "court_procedure"
    assert route.label == "Civil court summons / witness procedure"
    assert any("Code of Civil Procedure" in source for source in route.required_sources)
    assert route.legal_regime is None


def test_already_on_bail_video_link_failure_is_court_status_not_bail_advice():
    route = route_matter(
        "already on bail, video link failed and court adjourned, how to ask next date status"
    )

    assert route.category == "court_procedure"
    assert route.label == "Criminal court date / case-status procedure"
    assert route.legal_regime == "incident_date_needed_for_bns_bnss_bsa_vs_ipc_crpc"


def test_route_trace_exposes_legal_aid_property_collision():
    query = "private lawyer expensive for property partition suit can i get legal aid"
    route = route_matter(query)
    trace = route_matter_trace(query, selected_route=route)

    assert route.category == "legal_aid"
    assert trace["collision"] is True
    assert {candidate["category"] for candidate in trace["candidates"]} >= {
        "legal_aid",
        "property_tenancy",
    }
    assert "private lawyer" in trace["matched_terms"]["legal_aid"]
    assert "partition" in trace["matched_terms"]["property_civil"]


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


def test_custody_status_neighbors_route_to_distinct_safe_paths():
    hidden = route_matter(
        "police took my brother last night not showing station and not allowing lawyer what urgent remedy"
    )
    assert hidden.category == "arrest_custody_safeguard"
    assert hidden.label == "Illegal detention / habeas corpus"
    assert any("Article 226" in source for source in hidden.required_sources)

    missing = route_matter(
        "my adult brother missing since yesterday phone off but no proof police picked him what complaint should i file"
    )
    assert missing.category == "police_fir"
    assert missing.label == "Missing person / police complaint"
    assert not any("IT Act" in source for source in missing.required_sources)

    notice = route_matter(
        "police sent notice to come station for questioning tomorrow but not arrested should i go with lawyer"
    )
    assert notice.category == "criminal_procedure_notice"
    assert notice.label == "Police questioning / appearance notice"
    assert any("section 35" in source.lower() for source in notice.required_sources)

    lawyer_access = route_matter(
        "jail superintendent not allowing lawyer meeting for my brother first time arrest what legal aid route"
    )
    assert lawyer_access.category == "legal_aid"
    assert lawyer_access.label == "Custody legal aid / lawyer access"
    assert any("Legal Services Authorities" in source for source in lawyer_access.required_sources)


def test_generic_advance_contract_does_not_trigger_bonded_labour_rescue():
    route = route_matter("contractor took advance for renovation and cannot leave work unfinished")
    assert route.category != "bonded_labour_rescue"


def test_coercive_aadhaar_advance_wording_triggers_bonded_labour_rescue():
    route = route_matter("contractor took aadhaar card and says cannot leave until advance repaid")
    assert route.category == "bonded_labour_rescue"
    assert route.urgency == "emergency"


def test_customer_contractor_payment_dispute_does_not_trigger_contract_labour():
    route = route_matter("home painting contractor absconded after taking payment no workers involved")
    assert route.category != "labour_exploitation_discrimination"


def test_local_same_city_contractor_salary_stays_employment_wage():
    route = route_matter(
        "contractor at local shop has not paid two months salary but I am from same city what law applies"
    )
    assert route.category == "employment_wages"
    assert route.category != "labour_exploitation_discrimination"


def test_notice_period_only_route_uses_contract_source_requirements():
    route = route_matter(
        "company is asking me to serve 90 day notice but offer letter says 60 days which one applies"
    )

    assert route.category == "employment_wages"
    assert any("Indian Contract Act" in source for source in route.required_sources)
    assert any("only if" in source and "Industrial Disputes Act" in source for source in route.required_sources)
    assert any("only if" in source and "Code on Wages" in source for source in route.required_sources)
    assert "Labour Commissioner" not in route.forums


def test_stage_goal_exact_source_requirements_for_ppirp_and_gratuity():
    ppirp = route_matter(
        "hi, msme pre pack insolvency how to use against my own company 1.4 cr debt avoiding nclt full process can i file case"
    )
    assert ppirp.category == "ibc_nclt"
    ppirp_sources = " ".join(ppirp.required_sources)
    assert "Pre-Packaged Insolvency Resolution Process) Rules 2021" in ppirp_sources
    assert "Form 1" in ppirp_sources
    assert "NCLT Rules / IBC application forms" not in ppirp_sources

    gratuity = route_matter("father epf trust delayed gratuity 18 months no interest paid hsmc bangalore")
    assert gratuity.category == "employment_wages"
    gratuity_sources = " ".join(gratuity.required_sources)
    assert "Payment of Gratuity Act 1972" in gratuity_sources
    assert "Employees Provident Funds" in gratuity_sources
    assert "Payment of Wages Act / Code on Wages" not in gratuity_sources
    assert "Industrial Disputes Act" not in gratuity_sources


def test_software_vendor_license_is_not_street_vendor():
    route = route_matter("software vendor license dispute with client")
    assert route.category != "street_vendor_municipal"

    notice = route_matter("software vendor sent notice saying we are using unlicensed copies 22 cad seats noida can i file case")
    assert notice.category == "trademark_ip"
    assert notice.label == "Software copyright / licence notice"
    assert any("Copyright Act 1957" in source for source in notice.required_sources)
    assert not any(source == "Trade Marks Act 1999" for source in notice.required_sources)
    assert any("seat" in fact for fact in notice.missing_facts)


def test_housing_and_cooperative_recovery_require_local_documents_conditionally():
    pet = route_matter("society management fine 25000 for keeping pet without prior approval")
    assert pet.category == "consumer"
    assert any("based on state/city" in source for source in pet.required_sources)
    assert not any(source.startswith("Consumer/civil remedy only after") for source in pet.required_sources)

    parking = route_matter("neighbor blocking dedicated parking slot in apartment security guard says cant do anything")
    assert parking.category == "consumer"
    assert any("allotment documents" in source for source in parking.required_sources)

    buffalo = route_matter("cooperative bank seized my buffalo for crop loan default can they take livestock")
    assert buffalo.category == "banking_credit_dispute"
    assert any("loan agreement document" in source and "based on state" in source for source in buffalo.required_sources)


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


def test_tax_required_sources_keep_show_cause_notice_contextual():
    customs = route_matter("customs show cause notice for misdeclaration bill of entry mumbai")
    assert customs.category == "tax_gst_compliance"
    assert any("Customs Act 1962" in source for source in customs.required_sources)
    assert not any("CGST Act" in source or "GST registration" in source for source in customs.required_sources)

    customs_sec74 = route_matter("customs show cause notice section 74 drawback rejection shipping bill mismatch")
    assert customs_sec74.category == "tax_gst_compliance"
    assert any("Customs Act 1962" in source for source in customs_sec74.required_sources)
    assert not any("CGST Act" in source or "GST registration" in source for source in customs_sec74.required_sources)

    svb = route_matter("svb opened mumbai import invoice value rejected")
    assert svb.category == "tax_gst_compliance"
    assert any("Customs Act 1962" in source for source in svb.required_sources)

    income_tax = route_matter("income tax show cause notice section 148 what to do")
    assert income_tax.category == "tax_gst_compliance"
    assert any("Income Tax Act 1961" in source for source in income_tax.required_sources)
    assert not any("CGST Act" in source or "GST registration" in source for source in income_tax.required_sources)

    supplier_cancelled = route_matter("supplier gst cancelled retrospectively can i still claim ITC paid him 6 months back")
    assert supplier_cancelled.category == "tax_gst_compliance"
    joined_sources = " ".join(supplier_cancelled.required_sources)
    assert "sections 16 and 29" in joined_sources
    assert "sections 16, 41, and 73" not in joined_sources

    tcs = route_matter("TCS deducted on foreign remittance for my son education abroad how do i claim it back")
    assert tcs.category == "tax_gst_compliance"
    tcs_sources = " ".join(tcs.required_sources)
    assert "section 206C" in tcs_sources
    assert "TCS credit" in tcs_sources

    tcs_no_gst = route_matter("TCS deducted on foreign remittance for education abroad no GST issue how claim refund")
    assert tcs_no_gst.category == "tax_gst_compliance"
    tcs_no_gst_sources = " ".join(tcs_no_gst.required_sources)
    assert "section 206C" in tcs_no_gst_sources
    assert "CGST Act" not in tcs_no_gst_sources

    customs_no_gst = route_matter("customs show cause notice section 74 drawback rejection no GST issue")
    assert customs_no_gst.category == "tax_gst_compliance"
    customs_no_gst_sources = " ".join(customs_no_gst.required_sources)
    assert "Customs Act 1962" in customs_no_gst_sources
    assert "CGST Act" not in customs_no_gst_sources

    income_tax_no_gst = route_matter("income tax show cause notice section 148 no GST issue what to do")
    assert income_tax_no_gst.category == "tax_gst_compliance"
    income_tax_no_gst_sources = " ".join(income_tax_no_gst.required_sources)
    assert "Income Tax Act 1961" in income_tax_no_gst_sources
    assert "CGST Act" not in income_tax_no_gst_sources

    supplier_no_gst_word = route_matter("supplier registration cancelled retrospectively can i still claim ITC paid him 6 months back")
    assert supplier_no_gst_word.category == "tax_gst_compliance"
    no_gst_sources = " ".join(supplier_no_gst_word.required_sources)
    assert "sections 16 and 29" in no_gst_sources

    supplier_contract_cancelled = route_matter("supplier cancelled contract retrospectively after taking advance payment what civil remedy")
    assert supplier_contract_cancelled.category == "business_contract_partnership"

    purchase_order_advance = route_matter("supplier cancelled the purchase order retrospectively and kept my advance can i recover money")
    assert purchase_order_advance.category == "business_contract_partnership"
    purchase_order_sources = " ".join(purchase_order_advance.required_sources)
    assert "Indian Contract Act" in purchase_order_sources
    assert "CGST Act" not in purchase_order_sources

    purchase_order_no_gst = route_matter("supplier cancelled the purchase order retrospectively and kept my advance but no GST issue")
    assert purchase_order_no_gst.category == "business_contract_partnership"
    no_gst_sources = " ".join(purchase_order_no_gst.required_sources)
    assert "Indian Contract Act" in no_gst_sources
    assert "CGST Act" not in no_gst_sources

    coaching_refund = route_matter("coaching company took advance payment for online course and not refunding me consumer complaint")
    assert coaching_refund.category == "consumer"

    b2b_work_order = route_matter("vendor work order equipment delivery failed business dispute")
    assert b2b_work_order.category == "business_contract_partnership"

    b2b_advance_work_order = route_matter("vendor work order cancelled after advance payment and failed to deliver equipment business dispute")
    assert b2b_advance_work_order.category == "business_contract_partnership"


def test_routes_undertrial_bnss_479_review_to_undertrial_release():
    route = route_matter("i am paralegal volunteer in tihar undertrial 70 yrs ipc 302 how to apply 479 BNSS review")
    assert route.category == "undertrial_review_release"
    assert route.urgency == "high"
    assert any("section 479" in source for source in route.required_sources)
    assert route.action_pack is not None


def test_stage_e6_undertrial_review_wins_over_medical_bail_when_bnss479_named():
    route = route_matter("65 year old diabetic undertrial completed half sentence can review committee release under BNSS 479")

    assert route.category == "undertrial_review_release"
    assert route.label == "Undertrial custody review / release eligibility"


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
    assert divorce.category == "family_marriage_status"
    assert divorce.label == "Mutual consent divorce / family-court procedure"
    assert divorce.action_pack is not None
    assert divorce.action_pack.id == "marriage_breakdown"

    surrogacy = route_matter("we want a baby through surrogate my wife had hysterectomy 4 years ago we are both 38 is surrogacy allowed for us")
    assert surrogacy.category == "surrogacy_parenthood"
    assert surrogacy.action_pack is not None


def test_stage3_property_succession_routes_common_user_phrasing():
    mutation = route_matter("mother died and two brothers are blocking mutation of her house")
    assert mutation.category == "land_revenue_records"
    assert mutation.label == "Mutation after death / revenue record correction"

    daughter_share = route_matter("ancestral land brothers saying daughters have no share")
    assert daughter_share.category == "succession_inheritance"

    married_daughter = route_matter("married daughter denied share in ancestral agricultural land after father death")
    assert married_daughter.category == "succession_inheritance"

    society_transfer = route_matter("housing society not transferring flat after father death to legal heirs")
    assert society_transfer.category == "succession_inheritance"

    assert route_matter("tenant not leaving my inherited house but no sale dispute among heirs").category == "property_tenancy"
    assert route_matter("legal heir word in rent agreement tenant not vacating house").category == "property_tenancy"


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

    assert route.category == "social_welfare_identity"
    assert route.label == "Name / gazette / identity-record correction"
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
        "health department sealed my small hotel kitchen without giving inspection report": "business_license_compliance",
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

    benchmark_accused = route_matter(
        "please help my husband had affair I caught them I slapped the woman now she is filing case on me what to do any remedy"
    )
    assert benchmark_accused.category == "criminal_defence_bail"


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
        "fake call from sbi pension office took 2 lakh from my account 75 yr father": "cyber_fraud_or_harassment",
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

    crypto_wallet_transfer = route_matter("crypto wallet transfer fraud 2 lakh telegram group vanished")
    assert crypto_wallet_transfer.category == "cyber_fraud_or_harassment"
    assert "wallet transfer fraud" in crypto_wallet_transfer.label.lower()

    paytm_wallet_service = route_matter("paytm wallet blocked support not replying")
    assert paytm_wallet_service.category == "digital_platform_account"
    assert "crypto" not in paytm_wallet_service.label.lower()

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
        "how to legally change my surname after marriage, do i need to publish in gazette": "social_welfare_identity",
        "the spa was raided last week and police took me and other girls to station I just do massage I am scared what will happen now": "criminal_defence_bail",
        "police came to spa where I work in delhi I ran away am I in trouble do I need lawyer they have my photo from cctv": "criminal_defence_bail",
        "site mukadam beat me head injury 8 stitches when i asked for old wages mumbai": "workplace_injury_compensation",
        "daughter in law took my jewellery worth 12 lakh saying for safe keeping not returning agra": "family_domestic",
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


def test_cattle_transport_accused_route_exposes_state_source_requirement():
    route = route_matter("sir they arrested me for cow transport saying I am smuggling but I was taking my own buffalo to mandi")

    joined_sources = " ".join(route.required_sources).lower()
    joined_facts = " ".join(route.missing_facts).lower()
    assert route.category == "criminal_defence_bail"
    assert route.label == "State cattle / animal-transport accused procedure"
    assert "state cattle preservation" in joined_sources
    assert "prevention of cruelty to animals" in joined_sources
    assert "bnss" in joined_sources and "crpc" in joined_sources
    assert "fir or seizure-memo sections" in joined_facts
    assert "animal species" in joined_facts

    cooperative = route_matter("cooperative bank seized my buffalo for crop loan default can they take livestock")
    assert cooperative.category == "banking_credit_dispute"


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
    assert route_matter("pune cafe got notice for not keeping employee register under shops act what remedy").category == "labour_compliance"
    assert route_matter("bangalore store labour officer demanding maharashtra shops register is that right").category == "labour_compliance"

    assert route_matter("patna thana says section 37 bihar prohibition on me for liquor what can I do").category == "criminal_defence_bail"
    assert route_matter("police caught me with alcohol in noida but source showing bihar law what applies").category == "criminal_defence_bail"

    bank_route = route_matter(
        "bajaj finserv EMI bounced because of bank error, now they are charging 6000 penalty and threatening CIBIL"
    )
    assert bank_route.category == "banking_credit_dispute"
    assert bank_route.action_pack.id == "banking_credit_dispute"
    assert "loan" not in bank_route.action_pack.id


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
    prison = route_matter("tihar jail mulaqat only 30 min once a week is this legal can we ask more")
    assert prison.category == "prison_mulaqat"
    assert prison.label == "Prison mulaqat / interview access"
    assert prison.action_pack and prison.action_pack.id == "prison_mulaqat_access"
    prison_books = route_matter("son in tihar can he get books from family during prison rules")
    assert prison_books.category == "prison_mulaqat"
    assert prison_books.label == "Prison books / mulaqat access"
    assert prison_books.action_pack and prison_books.action_pack.id == "prison_mulaqat_access"
    for query in (
        "brother in rohini jail wants custody parole for mother's funeral what application route",
        "brother in rohini jail wants custody parole for grandmother death",
        "son in tihar wants emergency parole for father's last rites",
    ):
        custody_parole = route_matter(query)
        assert custody_parole.category == "prison_parole_furlough", query
        assert custody_parole.label == "Prison parole / furlough / remission", query
        assert custody_parole.action_pack and custody_parole.action_pack.id == "prison_parole_furlough"
        assert "PWDVA" not in " ".join(custody_parole.required_sources)
    assert route_matter("prisoner was booked into jail yesterday no lawyer yet").category != "prison_parole_furlough"
    assert route_matter(
        "how to file vakalatnama change of advocate during pending suit"
    ).category == "court_procedure"
    assert route_matter(
        "blue trunks app froze my account showing kyc pending pe stuck 80k"
    ).category == "digital_platform_account"
    assert route_matter(
        "DM gave NOC to bauxite project bastar without gram sabha resolution how to challenge"
    ).category == "environment_compensation"


def test_carceral_safety_precedence_routes_beat_broad_prison_and_cyber():
    cases = {
        "family sent money order to jail canteen but prisoner not getting account detail, what record can ask": (
            "prison_records",
            "Prison records / prisoner account request",
            "prison_records_admin",
        ),
        "prisoner wants copy of his bail rejection order and nominal roll, jail says family cannot ask": (
            "prison_records",
            "Prison records / prisoner account request",
            "prison_records_admin",
        ),
        "jail staff not allowing appointed lawyer to meet my brother before remand, legal aid says wait what can we do": (
            "legal_aid",
            "Custody legal aid / lawyer access",
            "legal_aid",
        ),
        "tihar prisoner depression medicine stopped, family wants psychiatrist check, which court or jail authority": (
            "criminal_defence_bail",
            "Custody medical care / interim bail",
            "criminal_defence_bail",
        ),
        "arthur road jail tb medicine missed for 2 weeks, jail doctor not giving report, what urgent legal step": (
            "criminal_defence_bail",
            "Custody medical care / interim bail",
            "criminal_defence_bail",
        ),
        "arthur road prisoner with TB not getting medicines and medical report hidden, what can family file": (
            "criminal_defence_bail",
            "Custody medical care / interim bail",
            "criminal_defence_bail",
        ),
        "puzhal prisoner insulin stopped and cannot walk, jail says wait what urgent court step": (
            "criminal_defence_bail",
            "Custody medical care / interim bail",
            "criminal_defence_bail",
        ),
        "byculla jail pregnant undertrial vomiting and no doctor visit, can we seek medical bail or court order": (
            "criminal_defence_bail",
            "Custody medical care / interim bail",
            "criminal_defence_bail",
        ),
        "undertrial review committee never considered brother though jail custody is 3 years trial not moving": (
            "undertrial_review_release",
            "Undertrial custody review / release eligibility",
            "undertrial_review_release",
        ),
        "chargesheet filed but trial not moving, can half sentence rule still be checked": (
            "undertrial_review_release",
            "Undertrial custody review / release eligibility",
            "undertrial_review_release",
        ),
        "bail order uploaded but jail not releasing because surety verification pending 10 days, what can family file": (
            "criminal_defence_bail",
            "Bail release / surety verification delay",
            "criminal_defence_bail",
        ),
        "high court granted bail but jail e-copy not received and still not releasing": (
            "criminal_defence_bail",
            "Bail release / surety verification delay",
            "criminal_defence_bail",
        ),
        "trial court bail granted but jail says two local sureties impossible for migrant, can court reduce surety": (
            "criminal_defence_bail",
            "Bail surety / bond hardship",
            "criminal_defence_bail",
        ),
        "minor boy picked by police and kept in station with adults, school id says age 16": (
            "criminal_defence_bail",
            "Juvenile age / JJB custody route",
            "criminal_defence_bail",
        ),
        "child accused is in observation home but police still asking parents to bring him to adult court": (
            "criminal_defence_bail",
            "Juvenile age / JJB custody route",
            "criminal_defence_bail",
        ),
        "police says lawyer can meet only after confession statement, accused is inside lockup": (
            "legal_aid",
            "Custody legal aid / lawyer access",
            "legal_aid",
        ),
        "police threatening to keep me in station whole night if i don't sign statement, i am not arrested": (
            "arrest_custody_safeguard",
            "Police station coercion / custody safeguard",
            "arrest_custody_safeguard",
        ),
        "husband picked by crime branch, 24 hours passed no production in court, family not informed": (
            "arrest_custody_safeguard",
            "Arrest / production before Magistrate",
            "arrest_custody_safeguard",
        ),
        "police gave 35(3) notice in new case and asking phone, can they arrest me if i go alone": (
            "criminal_procedure_notice",
            "Police questioning / appearance notice",
            "criminal_procedure_notice",
        ),
        "new BNSS 35 notice says appear tomorrow at cyber cell, should i apply anticipatory bail just because of notice": (
            "criminal_procedure_notice",
            "Police questioning / appearance notice",
            "criminal_procedure_notice",
        ),
        "i received 35 notice but police also says bring all chats and don't tell lawyer": (
            "criminal_procedure_notice",
            "Police questioning / appearance notice",
            "criminal_procedure_notice",
        ),
        "cyber police called me for enquiry tomorrow, no arrest notice, should i apply bail or just go": (
            "criminal_procedure_notice",
            "Police questioning / appearance notice",
            "criminal_procedure_notice",
        ),
        "lockup constable took money for release and beat my cousin, what immediate record to preserve": (
            "police_fir",
            "Custodial violence / police extortion",
            "police_fir",
        ),
        "23 year old son went with friends phone off no proof police picked him should i file habeas or missing complaint": (
            "police_fir",
            "Missing person / police complaint",
            "police_fir",
        ),
        "my 23 year old son went with friends and not reachable 8 hours, no police custody proof, should we file habeas": (
            "police_fir",
            "Missing person / police complaint",
            "police_fir",
        ),
        "up jail parole for daughter's wedding, family has card but no lawyer, can we send application directly": (
            "prison_parole_furlough",
            "Prison parole / furlough / remission",
            "prison_parole_furlough",
        ),
        "visitor list does not include my child, can jail deny family mulaqat": (
            "prison_mulaqat",
            "Prison mulaqat / interview access",
            "prison_mulaqat_access",
        ),
        "prison canteen balance missing after money order, jail clerk says no ledger copy to family": (
            "prison_records",
            "Prison records / prisoner account request",
            "prison_records_admin",
        ),
        "mandoli jail video call slot failed four times and staff says server down, can wife ask written order": (
            "prison_mulaqat",
            "Prison mulaqat / interview access",
            "prison_mulaqat_access",
        ),
        "rohini jail removed my name from visitor list after address check delay, can superintendent give reasons": (
            "prison_mulaqat",
            "Prison mulaqat / interview access",
            "prison_mulaqat_access",
        ),
        "court sent me witness summons in civil property case to bring sale deed, is this police notice": (
            "court_procedure",
            "Civil court summons / witness procedure",
            "court_procedure",
        ),
        "bail order allows personal bond but jail clerk demands cash deposit before release": (
            "criminal_defence_bail",
            "Bail release / surety verification delay",
            "criminal_defence_bail",
        ),
        "jail not giving psychiatric help for suicidal undertrial, can DLSA move court urgently": (
            "criminal_defence_bail",
            "Custody medical care / interim bail",
            "criminal_defence_bail",
        ),
    }

    for query, (category, label, action_pack_id) in cases.items():
        route = route_matter(query)
        assert route.category == category, query
        assert route.label == label, query
        assert route.action_pack is not None, query
        assert route.action_pack.id == action_pack_id, query


def test_civil_legal_aid_negated_arrest_does_not_become_custody_access():
    for query in (
        "private lawyer too expensive for land partition case, can DLSA give lawyer though no arrest",
        "i need free lawyer for consumer complaint against phone company, not criminal case, what papers",
    ):
        route = route_matter(query)
        assert route.category == "legal_aid", query
        assert route.label == "Legal aid eligibility / DLSA support", query


def test_stage_c_repeated_common_failures_route_to_specific_actionable_buckets():
    cases = {
        "supplier delivered defective material now refusing refund 18 lakh contract": (
            "business_contract_partnership",
            "Business contract / partnership",
        ),
        "mother says son took her thumb impression on blank paper now produced as gift deed": (
            "property_tenancy",
            "Property transfer / gift deed dispute",
        ),
        "son took loan against my house i didn't sign told bank to stop ahmedabad": (
            "banking_credit_dispute",
            "Forged loan / bank-property document dispute",
        ),
        "lic agent told my father guaranteed return now policy matured got half amount fraud": (
            "senior_citizen",
            "Senior citizen financial abuse / mis-selling",
        ),
        "tehsildar transferred my baba land to bania without my consent agency area andhra": (
            "tribal_caste_atrocity",
            "Tribal land transfer / restoration",
        ),
        "fake call from sbi pension office took 2 lakh from my account 75 yr father": (
            "cyber_fraud_or_harassment",
            "Bank / pension impersonation fraud",
        ),
        "I had abortion 5 years back husband found out threatening divorce": (
            "reproductive_rights_mtp",
            "Pregnancy termination / reproductive rights",
        ),
    }
    for query, (category, label) in cases.items():
        route = route_matter(query)
        assert route.category == category, query
        assert route.label == label, query
        assert route.action_pack is not None, query
        assert route.required_sources, query
        assert route.forums, query


def test_stage_c_review_regime_and_variant_guards():
    forged_deed = route_matter(
        "mother says son took her thumb impression on blank paper in 2022 now produced as gift deed"
    )
    assert forged_deed.category == "property_tenancy"
    assert forged_deed.legal_regime == "legacy_ipc_crpc_evidence_for_pre_2024_incident"

    forged_bank = route_matter(
        "son took loan against my house in 2022 i did not sign told bank to stop"
    )
    assert forged_bank.category == "banking_credit_dispute"
    assert forged_bank.legal_regime == "legacy_ipc_crpc_evidence_for_pre_2024_incident"

    b2b = route_matter("supplier delivered defective material refusing refund")
    assert b2b.category == "business_contract_partnership"

    forged_signature = route_matter("in 2019 brother forged my signature on gift deed of my house")
    assert forged_signature.category == "property_tenancy"
    assert forged_signature.label == "Property transfer / gift deed dispute"
    assert forged_signature.legal_regime == "legacy_ipc_crpc_evidence_for_pre_2024_incident"


def test_stage_e_hardfail_routes_hit_specific_buckets():
    ancestral = route_matter(
        "pls tell father is hindu 78 yrs ancestral land sold by brother without consent madhya pradesh need lawyer or police"
    )
    assert ancestral.category == "property_tenancy"
    assert ancestral.label == "Ancestral land sale / heir share dispute"

    mandamus = route_matter(
        "urgent what is mandamus writ and when can I file against government officer how to complain"
    )
    assert mandamus.category == "court_procedure"
    assert mandamus.label == "Writ / constitutional remedy procedure"

    article_route = route_matter(
        "urgent difference between Article 32 Supreme Court and Article 226 High Court writ how to complain"
    )
    assert article_route.category == "court_procedure"
    assert article_route.label == "Writ / constitutional remedy procedure"

    pre_marriage = route_matter(
        "please help the man I am supposed to marry next month I found out hides he is HIV positive his family also knows can I cancel without dowry return issue any remedy"
    )
    assert pre_marriage.category == "family_marriage_status"
    assert pre_marriage.label == "Pre-marriage health disclosure / cancelled wedding"
    assert pre_marriage.action_pack and pre_marriage.action_pack.id == "pre_marriage_disclosure"

    post_marriage = route_matter(
        "married last month found wife hid HIV positive can I cancel marriage"
    )
    assert post_marriage.category == "family_marriage_status"
    assert post_marriage.label != "Pre-marriage health disclosure / cancelled wedding"
    assert post_marriage.action_pack and post_marriage.action_pack.id == "marriage_misrepresentation"

    after_marriage = route_matter(
        "after marriage found husband is HIV positive and hid it can I cancel marriage"
    )
    assert after_marriage.category == "family_marriage_status"
    assert after_marriage.label != "Pre-marriage health disclosure / cancelled wedding"

    after_wedding_groom = route_matter(
        "after wedding found groom hid HIV can I cancel marriage"
    )
    assert after_wedding_groom.category == "family_marriage_status"
    assert after_wedding_groom.label == "Marriage misrepresentation / family-law options"

    after_wedding_bride = route_matter(
        "after wedding found bride hid HIV can I cancel without dowry issue"
    )
    assert after_wedding_bride.category == "family_marriage_status"
    assert after_wedding_bride.label == "Marriage misrepresentation / family-law options"

    earlier_marriage = route_matter(
        "wife family hid her earlier marriage before wedding remedy"
    )
    assert earlier_marriage.category == "family_marriage_status"
    assert earlier_marriage.label == "Marriage misrepresentation / family-law options"

    assert route_matter(
        "i have got damaged phone company is not accepting the return what to do"
    ).category == "consumer"


def test_stage_f_safety_blocker_routes_are_not_general_or_wrong_forum():
    csam = route_matter("ai csam of my classmate someone made and shared in college telegram")
    assert csam.category == "cyber_fraud_or_harassment"
    assert any("POCSO" in source for source in csam.required_sources)

    esi = route_matter(
        "i am confused ESI hospital refused to treat my wife for delivery saying my contributions are short"
    )
    assert esi.category == "employment_wages"
    assert esi.label == "ESI benefit / insured-person treatment dispute"

    accused_498a = route_matter(
        "i am confused my wife filed false 498A case against me and my parents can we get anticipatory bail"
    )
    assert accused_498a.category == "criminal_defence_bail"
    assert accused_498a.label == "498A / matrimonial criminal defence"

    online_warning = route_matter("engagement broken because he hid HIV can I post warning online")
    assert online_warning.category == "family_marriage_status"
    assert online_warning.label == "Pre-marriage health disclosure / cancelled wedding"

    mining = route_matter("tribal village land taken for mining without consent gram sabha")
    assert mining.category == "environment_compensation"
    assert mining.label == "Tribal project displacement / Gram Sabha consent"

    ola = route_matter("ola cabs deactivated me after 2 years driving in koramangala no warning")
    assert ola.category == "digital_platform_account"
    assert ola.label == "Cab aggregator driver deactivation / platform account"


def test_custody_no_lawyer_routes_to_legal_aid_not_general():
    route = route_matter("my husband in jail has no lawyer family cannot afford advocate what can we do")

    assert route.category == "legal_aid"
    assert route.label == "Custody legal aid / lawyer access"


def test_stage_500_offtopic_review_routes_specific_failures():
    esi = route_matter(
        "ESI hospital refused to treat my wife for delivery saying my contributions are short, what is the eligibility"
    )
    assert esi.category == "employment_wages"
    assert esi.label == "ESI benefit / insured-person treatment dispute"

    accident = route_matter(
        "i was driving and accidentally hit a pedestrian who is now claiming 8 lakh, my insurance is third party only"
    )
    assert accident.label == "Motor accident / third-party claim"
    assert "Motor Accident Claims Tribunal" in accident.forums

    laptop = route_matter(
        "my company laptop has been seized by police as part of investigation against my colleague, what are my rights"
    )
    assert laptop.category == "police_fir"
    assert laptop.label == "Police seizure of digital device"

    pickup_with_phone_numbers = route_matter(
        "police took my brother at midnight and not telling station or case; screenshots/witness names and phone numbers are with me"
    )
    assert pickup_with_phone_numbers.category == "arrest_custody_safeguard"
    assert pickup_with_phone_numbers.label == "Arrest / production before Magistrate"

    nclat = route_matter("tribunal order against me how to appeal NCLAT format and fees")
    assert nclat.category == "ibc_nclt"
    assert nclat.label == "NCLAT appeal / tribunal-order challenge"


def test_stage3b_common_user_workflows_route_to_specific_forums():
    cases = {
        "HDFC forex card charged markup twice and support says wait 45 days": (
            "banking_credit_dispute",
            "Bank debit / RBI Ombudsman complaint",
        ),
        "ATM cash not dispensed but account debited branch not helping": (
            "banking_credit_dispute",
            "Bank debit / RBI Ombudsman complaint",
        ),
        "friend borrowed cash no written agreement but whatsapp says he will repay": (
            "business_contract_partnership",
            "Personal loan / money recovery",
        ),
        "neighbour took 50000 saying emergency now blocked number can police recover": (
            "business_contract_partnership",
            "Personal loan / money recovery",
        ),
        "father died mutation not updated in patwari record rajasthan where to go": (
            "land_revenue_records",
            "Mutation after death / revenue record correction",
        ),
        "app charged yearly subscription after cancellation support not refunding": (
            "consumer",
            "Consumer complaint / service deficiency",
        ),
        "amazon delivered fake iphone and says third party seller responsible refund denied": (
            "consumer",
            "Consumer complaint / defective goods or warranty service",
        ),
        "personal loan closed but bank not giving NOC and CIBIL still active": (
            "banking_credit_dispute",
            "Banking / credit record dispute",
        ),
        "tamil nadu shop license renewal pending 2 years coimbatore shopkeeper penalty kaise calculate": (
            "business_license_compliance",
            "Business license / shop registration",
        ),
    }

    for prompt, (category, label) in cases.items():
        route = route_matter(prompt)
        assert route.category == category, prompt
        assert route.label == label, prompt


def test_stage3b_negative_controls_do_not_overroute_to_cyber_or_food_safety():
    atm = route_matter("ATM cash not dispensed but account debited branch not helping")
    assert atm.category == "banking_credit_dispute"
    assert atm.category != "cyber_fraud_or_harassment"

    friendly = route_matter("neighbour took 50000 saying emergency now blocked number can police recover")
    assert friendly.category == "business_contract_partnership"
    assert "police only if deception" in " ".join(friendly.forums).lower()

    shop = route_matter("tamil nadu shop license renewal pending 2 years coimbatore shopkeeper penalty")
    assert shop.category == "business_license_compliance"
    assert all("food" not in source.lower() for source in shop.required_sources)


def test_repair8_common_failures_route_before_broad_buckets():
    cases = {
        "hospital doctor injection mistake father passed away bills and papers with me where complain first": (
            "consumer",
            "Medical negligence / hospital service deficiency",
        ),
        "my mother died after wrong injection in private hospital, can we get compensation or file police case": (
            "consumer",
            "Medical negligence / hospital service deficiency",
        ),
        "my husband ex serviceman died, no family pension, ppo and death certificate are there where complain": (
            "social_welfare_identity",
            "Army service/family pension grievance",
        ),
        "army jawan husband passed away family pension not started which office and documents for widow": (
            "social_welfare_identity",
            "Army service/family pension grievance",
        ),
        "amazon seller using my registered brand on fake items, platform takedown not working what court route": (
            "trademark_ip",
            "Trademark / marketplace fake-products takedown",
        ),
        "money decree passed in my favour no payment since months, tell civil court procedure for attachment": (
            "court_procedure",
            "Civil decree execution / attachment",
        ),
        "former sales manager using our confidential customer database after joining rival, what civil court remedy": (
            "business_contract_partnership",
            "Business confidentiality / NDA / customer-list misuse",
        ),
        "nearby chemical factory polluting water, people want public interest litigation what is procedure": (
            "environment_compensation",
            "Pollution PIL / NGT / public environmental complaint",
        ),
    }

    for prompt, (category, label) in cases.items():
        route = route_matter(prompt)
        assert route.category == category, prompt
        assert route.label == label, prompt
        assert route.action_pack is not None, prompt
        assert route.required_sources, prompt
        assert route.forums, prompt


def test_repair8_negative_neighbors_do_not_overroute():
    succession = route_matter("mother died without will and brothers fighting over her house share")
    assert succession.category == "succession_inheritance"

    buyer_refund = route_matter("amazon delivered fake iphone and says third party seller responsible refund denied")
    assert buyer_refund.category == "consumer"
    assert buyer_refund.label == "Consumer complaint / defective goods or warranty service"

    senior = route_matter("elderly mother pension stopped and children not helping what law")
    assert senior.category in {"senior_citizen", "social_welfare_identity"}
    assert senior.label != "Army service/family pension grievance"

    wage = route_matter("contractor not paying wages for two months how to complain")
    assert wage.category in {"labour_exploitation_discrimination", "employment_wages"}
    assert wage.category not in {"court_procedure", "business_contract_partnership", "general_legal"}

    municipal = route_matter("municipality sealed my shop in gujarat without notice")
    assert municipal.category == "business_license_compliance"
    assert municipal.label == "Municipal sealing / shop closure notice"

    death_certificate = route_matter("father died at home panchayat not giving death certificate what can i do")
    assert death_certificate.category == "social_welfare_identity"
    assert death_certificate.label == "Civil registration / identity record"

    not_trademark = route_matter("flipkart seller sent duplicate shoes i want refund not trademark case")
    assert not_trademark.category == "consumer"
    assert not_trademark.label == "Consumer complaint / defective goods or warranty service"

    private_pollution = route_matter("factory smoke damaged only my house wall no public pil just compensation")
    assert private_pollution.category == "environment_compensation"
    assert private_pollution.label == "Environmental damage / compensation"

    noncompete = route_matter("employee joined competitor but no nda only non compete clause is it enforceable")
    assert noncompete.category == "employment_wages"
    assert noncompete.label == "Employment non-compete / contract restraint"

    employment_contract_noncompete = route_matter(
        "i am confused non compete clause in my employment contract for 2 years is it enforceable in india pls guide"
    )
    assert employment_contract_noncompete.category == "employment_wages"
    assert employment_contract_noncompete.label == "Employment non-compete / contract restraint"

    silicosis = route_matter(
        "what to do rajasthan stone quarry silicosis lungs gone 2 friends already died i have cough 6 months is this legal"
    )
    assert silicosis.category == "workplace_injury_compensation"
    assert silicosis.label == "Occupational disease / quarry silicosis compensation"
    silicosis_sources = " ".join(silicosis.required_sources)
    assert "Employees Compensation Act" in silicosis_sources
    assert "state labour welfare and safety rules" not in silicosis_sources

    wage_waiver = route_matter("boss saying i signed paper give up wages but i dont read english kannada")
    waiver_sources = " ".join(wage_waiver.required_sources)
    assert wage_waiver.category == "employment_wages"
    assert "Code on Wages" in waiver_sources
    assert "Industrial Disputes Act only if" in waiver_sources

    mining_consent = route_matter(
        "mining company doing blasting next to village no gram sabha consent jharkhand west singhbhum what can i do"
    )
    assert mining_consent.category == "environment_compensation"
    assert not any("RFCTLARR Act 2013 rehabilitation" in source for source in mining_consent.required_sources)

    specific_performance = route_matter(
        "want specific performance of land purchase deal seller backing out delhi commercial plot"
    )
    assert specific_performance.category == "property_tenancy"
    assert specific_performance.label == "Land agreement / specific performance"
    sp_sources = " ".join(specific_performance.required_sources)
    assert "Specific Relief Act" in sp_sources
    assert "Registration Act only if" in sp_sources


def test_fresh_negative_neighbor_v2_route_ownership_regressions():
    cases = {
        "my 24 year old daughter left with boyfriend and parents want police to bring her home, what can we do": (
            "police_fir",
            "Adult partner-choice / no forced return",
        ),
        "private complaint dismissed without cognizance by magistrate, should i file FIR again or revision": (
            "court_procedure",
            "Private complaint / Magistrate police-inaction procedure",
        ),
        "delhi furlough rejected orally by authority what can family do": (
            "prison_parole_furlough",
            "Prison parole / furlough / remission",
        ),
        "child in observation home is being called to police station again for questioning, should parents send him": (
            "criminal_defence_bail",
            "Juvenile age / JJB custody route",
        ),
        "neighbour hit me outside my shop and police say settle privately, nobody was in police custody": (
            "police_fir",
            "FIR / police inaction",
        ),
        "local boys broke my scooter mirror and police are delaying FIR calling it insurance issue": (
            "police_fir",
            "FIR / police inaction",
        ),
        "contractor filed false theft FIR after workers demanded unpaid wages, should we go labour": (
            "criminal_defence_bail",
            "Criminal quashing / High Court procedure",
        ),
        "tenant not paying rent and not vacating house": (
            "property_tenancy",
            "Tenant not vacating / rent arrears",
        ),
    }

    for query, (category, label) in cases.items():
        route = route_matter(query)
        assert route.category == category, query
        assert route.label == label, query


def test_stage2_workplace_death_required_sources_are_not_impossible_state_rules():
    route = route_matter("worker died at site and owner not giving compensation")
    assert route.category == "workplace_injury_compensation"
    required = " ".join(route.required_sources)
    assert "Employees Compensation Act" in required
    assert "BOCW Act 1996 / Factories Act 1948 where applicable" in required
    assert "state labour welfare and safety rules" not in required


def test_stage2_factory_worksite_harm_preempts_environment_and_general_routes():
    lost_hand = route_matter("worker lost hand in factory owner says careless no compensation")
    assert lost_hand.category == "workplace_injury_compensation"

    killed = route_matter("factory boiler killed worker family got nothing")
    assert killed.category == "workplace_injury_compensation"

    assault = route_matter("mukadam beat worker at site head injury and old wages not paid")
    assert assault.category == "workplace_injury_compensation"
    assert assault.label == "Worksite assault / injury and wage dispute"
    assert any("hurt" in source.lower() for source in assault.required_sources)

    contractor_assault = route_matter("contractor beat me at construction site head injury and not paying old wages")
    assert contractor_assault.category == "workplace_injury_compensation"
    assert contractor_assault.label == "Worksite assault / injury and wage dispute"


def test_stage2_prohibition_accused_route_does_not_capture_liquor_license_admin():
    admin_queries = [
        "liquor shop license cancelled by excise officer without notice",
        "wine shop sealed for licence renewal delay what can i do",
        "bar license notice from excise department renewal delayed",
    ]
    for query in admin_queries:
        route = route_matter(query)
        assert route.category == "business_license_compliance", query
        assert route.label == "Business license / shop registration", query
        pack_ids = [pack.id for pack in source_packs_for_route(route, query)]
        assert "rti_2005" in pack_ids, query

    bihar_admin = "bihar bar license renewal delayed excise department no reply"
    bihar_route = route_matter(bihar_admin)
    assert bihar_route.category == "business_license_compliance"
    bihar_pack_ids = [pack.id for pack in source_packs_for_route(bihar_route, bihar_admin)]
    assert "bihar_prohibition_excise_2016" in bihar_pack_ids
    assert "rti_2005" in bihar_pack_ids

    accused = route_matter("police caught me drinking village they saying case under prohibition law what punishment")
    assert accused.category == "criminal_defence_bail"
    assert accused.label == "State prohibition / excise accused procedure"

    accused_wine = route_matter("wine shop FIR for selling after license expired what bail")
    assert accused_wine.category == "criminal_defence_bail"
    assert accused_wine.label == "State prohibition / excise accused procedure"
    accused_wine_packs = [
        pack.id
        for pack in source_packs_for_route(
            accused_wine,
            "wine shop FIR for selling after license expired what bail",
        )
    ]
    assert "constitution_article_47" in accused_wine_packs

    accused_selling = route_matter("police filed excise FIR for selling alcohol without licence what bail")
    assert accused_selling.category == "criminal_defence_bail"
    assert accused_selling.label == "State prohibition / excise accused procedure"


def test_stage2_generic_portal_software_error_does_not_route_to_ip_license():
    route = route_matter("shop registration portal software error license renewal pending")
    assert route.category == "business_license_compliance"
    assert route.label == "Business license / shop registration"

    municipality = route_matter("municipality software license renewal portal not working for shop registration")
    assert municipality.category == "business_license_compliance"
    assert municipality.label == "Business license / shop registration"


def test_stage3_refusal_probe_routes_named_high_risk_statutes_precisely():
    arms = route_matter("gadchiroli police put arms act because axe was in my farm jeep")
    assert arms.category == "criminal_defence_bail"
    assert arms.label == "Arms Act / farming-tool criminal defence"
    assert any("Arms Act 1959" in source for source in arms.required_sources)

    generic_weapon = route_matter("weapon case in gadchiroli police called me what to do")
    assert generic_weapon.label != "Arms Act / farming-tool criminal defence"
    assert not any("Arms Act 1959 definition/licensing/penalty" in source for source in generic_weapon.required_sources)

    mcoca = route_matter("MCOCA 100 days custody no chargesheet can we file default bail")
    assert mcoca.category == "criminal_defence_bail"
    assert mcoca.label == "Default bail / no chargesheet"
    assert any("Maharashtra Control of Organised Crime Act 1999" in source for source in mcoca.required_sources)

    labour_chowk = route_matter("delhi labour chowk police picked workers saying begging, contractor not paying wages")
    assert labour_chowk.category == "police_fir"
    assert any("arrest and detention" in source for source in labour_chowk.required_sources)
    assert not any("FIR, and police-information" in source for source in labour_chowk.required_sources)


def test_stage_e7_family_common_user_prompts_route_to_specific_remedies():
    dv_notice = route_matter("wife filed false domestic violence case, i have notice what do i reply")
    assert dv_notice.category == "family_domestic"
    assert dv_notice.label == "Domestic violence notice / response"
    assert dv_notice.urgency == "high"
    assert dv_notice.action_pack and dv_notice.action_pack.id == "family_notice_response"

    no_fir_notice = route_matter("wife filed domestic violence case, no FIR just notice reply")
    assert no_fir_notice.category == "family_domestic"
    assert no_fir_notice.label == "Domestic violence notice / response"
    assert no_fir_notice.action_pack and no_fir_notice.action_pack.id == "family_notice_response"

    false_no_fir_notice = route_matter("wife filed false domestic violence case no FIR only notice what do i reply")
    assert false_no_fir_notice.category == "family_domestic"
    assert false_no_fir_notice.label == "Domestic violence notice / response"

    served_notice = route_matter("wife filed domestic violence case and police complaint also sent me notice")
    assert served_notice.category == "family_domestic"
    assert served_notice.label == "Domestic violence notice / response"

    legal_aid_notice = route_matter("wife filed domestic violence case, next date tomorrow and I need legal aid")
    assert legal_aid_notice.category == "family_domestic"
    assert legal_aid_notice.label == "Domestic violence notice / response"

    no_arrest_summons = route_matter("wife filed domestic violence case no arrest notice only summons what do i reply")
    assert no_arrest_summons.category == "family_domestic"
    assert no_arrest_summons.label == "Domestic violence notice / response"

    no_police_court_summons = route_matter("wife filed domestic violence case no police notice only court summons what do i reply")
    assert no_police_court_summons.category == "family_domestic"
    assert no_police_court_summons.label == "Domestic violence notice / response"

    spousal_gold = route_matter("my wife took my gold and left house")
    assert spousal_gold.category == "family_domestic"
    assert spousal_gold.label == "Spousal jewellery / property return"
    assert spousal_gold.action_pack and spousal_gold.action_pack.id == "spousal_property_return"
    assert "police/Magistrate only where breach-of-trust or theft facts fit" in spousal_gold.forums

    residence = route_matter("husband throws me out but house in mother in law name")
    assert residence.category == "family_domestic"
    assert residence.label == "Domestic violence / right to residence"
    assert residence.urgency == "emergency"

    hidden_orientation = route_matter("my husband is gay and hidden before marriage what can i do")
    assert hidden_orientation.category == "family_marriage_status"
    assert hidden_orientation.label == "Marriage misrepresentation / family-law options"

    child = route_matter("my wife left me and took child, no court order")
    assert child.category == "child_custody_adoption"
    assert child.label == "Child custody / adoption / child return"


def test_stage_e9_fra_claim_refusal_routes_to_forest_rights_not_criminal_composite():
    route = route_matter(
        "urgent forest department refusing my claim under FRA 2006 since 4 years "
        "bastar chhattisgarh how to complain"
    )

    assert route.category == "tribal_caste_atrocity"
    assert route.label == "Forest rights / FRA claim or forest produce"
    assert any("Forest Rights Act 2006" in source for source in route.required_sources)
    assert not any("BNS/BNSS" in source or "IPC/CrPC" in source for source in route.required_sources)
