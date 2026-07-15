#!/usr/bin/env python3
"""Build a deterministic 200-prompt common-user legal QA suite.

This pack is deliberately different from the broad 500 benchmark. It
overweights the plain, messy, high-volume questions users type in the UI
and carries prompt-specific product expectations for the common-user gate.

Output is generated under /tmp by default so benchmark artifacts do not get
mixed with indexed legal data or committed corpus files.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


Scenario = dict[str, Any]


SCENARIOS: list[Scenario] = [
    {
        "id": "tenant_not_vacating_rent",
        "expected_category": "property_tenancy",
        "expected_route_any": ["property_tenancy"],
        "expected_act_hint": "Transfer of Property Act 1882 + Limitation Act 1963",
        "must_include_any": ["rent authority", "civil court", "legal notice", "lease", "arrears"],
        "variants": [
            "My tenant is not vacating house and not paying rent",
            "tenant not leaving my flat and 5 months rent pending what to do",
            "tenant stopped rent and refusing to vacate after agreement expired",
            "shop tenant is sitting inside and not paying rent can i throw him out",
        ],
    },
    {
        "id": "landlord_deposit_refund",
        "expected_category": "property_tenancy",
        "expected_route_any": ["property_tenancy", "consumer", "business_contract_partnership"],
        "expected_act_hint": "Transfer of Property Act 1882 + Indian Contract Act 1872",
        "must_include_any": ["deposit", "notice", "rent agreement", "civil court", "consumer"],
        "variants": [
            "landlord is not returning my deposit after i vacated room",
            "owner kept my 2 month security deposit saying painting charges no proof",
            "my pg owner not giving deposit back and blocked my number",
            "flat deposit refund pending for 4 months what legal steps",
        ],
    },
    {
        "id": "family_hand_loan_recovery",
        "expected_category": "business_contract_partnership",
        "expected_route_any": ["business_contract_partnership", "cheque_bounce", "criminal_general"],
        "expected_act_hint": "Indian Contract Act 1872 + Limitation Act 1963",
        "must_include_any": ["legal notice", "civil recovery", "summary suit", "limitation", "proof"],
        "variants": [
            "My brother is not returning my money, which he took loan",
            "i gave 3 lakh to cousin by upi now he is avoiding calls",
            "friend borrowed money in cash and whatsapp says he will return but not paying",
            "relative took hand loan 2 years back no agreement what can i do",
        ],
    },
    {
        "id": "joint_plot_sold",
        "expected_category": "property_tenancy",
        "expected_route_any": ["property_tenancy", "succession_inheritance", "criminal_general"],
        "expected_act_hint": "Transfer of Property Act 1882 + Specific Relief Act 1963",
        "must_include_any": ["sale deed", "civil court", "injunction", "partition", "title"],
        "variants": [
            "brother and i bought a plot together 10 years back, now he has sold it, what can i do",
            "joint land was in my and brother name but he sold without asking me",
            "my uncle sold our common plot using old papers what remedy",
            "one co owner sold full property without my consent can i cancel sale",
        ],
    },
    {
        "id": "legal_heir_property_sale",
        "expected_category": "succession_inheritance",
        "expected_route_any": ["succession_inheritance", "property_tenancy"],
        "expected_act_hint": "Hindu Succession Act 1956 + Transfer of Property Act 1882",
        "must_include_any": ["legal heir", "partition", "succession", "sale deed", "civil court"],
        "variants": [
            "Can I sell property if one legal heir is not agreeing?",
            "father died and one sister not signing sale papers can we sell house",
            "all heirs want to sell ancestral land but one brother refuses",
            "can majority legal heirs sell inherited property without one heir consent",
        ],
    },
    {
        "id": "shop_sealed_municipality",
        "expected_category": "business_license_compliance",
        "expected_route_any": ["business_license_compliance", "street_vendor_municipal", "property_tenancy"],
        "expected_act_hint": "Shops and Establishments Act + municipal licensing procedure",
        "must_include_any": ["municipal", "seal", "notice", "licence", "appeal"],
        "variants": [
            "My shop is in Gujarat and municipality sealed it",
            "municipality sealed my shop without giving notice what to do",
            "local body locked my commercial shop saying licence problem",
            "my restaurant was sealed by corporation officers can i reopen",
        ],
    },
    {
        "id": "street_vendor_cart_removed",
        "expected_category": "street_vendor_municipal",
        "expected_route_any": ["street_vendor_municipal", "business_license_compliance"],
        "expected_act_hint": "Street Vendors Act 2014",
        "must_include_any": ["street vendor", "town vending committee", "certificate", "municipal", "appeal"],
        "variants": [
            "municipality removed my tea cart from footpath without notice",
            "i have street vendor certificate but police took my cart",
            "hawker zone people are removing my vegetable stall what to do",
            "nagar nigam seized my street vending goods and asking fine",
        ],
    },
    {
        "id": "bank_wrong_debit",
        "expected_category": "banking_credit_dispute",
        "expected_route_any": ["banking_credit_dispute", "consumer"],
        "expected_act_hint": "Banking Ombudsman + Consumer Protection Act 2019",
        "must_include_any": ["rbi", "ombudsman", "bank", "complaint", "cms"],
        "variants": [
            "Bank deducted money wrongly and customer care not helping",
            "my bank account debited twice for one transaction no refund",
            "bank reversed my balance saying technical error but not giving reason",
            "wrong debit from savings account bank branch not responding",
        ],
    },
    {
        "id": "bank_account_frozen",
        "product_priority": "critical",
        "expected_category": "banking_credit_dispute",
        "expected_route_any": ["banking_credit_dispute", "cyber_fraud_or_harassment", "police_fir"],
        "expected_act_hint": "Banking Ombudsman + BNSS 2023 + IT Act 2000",
        "must_include_any": ["freeze", "lien", "bank", "police", "cyber"],
        "variants": [
            "my bank account is frozen, what to do",
            "bank put lien on my account after cyber complaint i dont know why",
            "salary account blocked by bank saying police request no notice",
            "my upi account frozen and branch not giving complaint number",
        ],
    },
    {
        "id": "loan_app_harassment_contacts",
        "product_priority": "critical",
        "expected_category": "banking_credit_dispute",
        "expected_route_any": ["banking_credit_dispute", "cyber_fraud_or_harassment", "criminal_general"],
        "expected_act_hint": "Banking Ombudsman + Information Technology Act 2000 + BNS 2023",
        "must_include_any": ["rbi", "loan app", "cyber", "contacts", "harassment"],
        "variants": [
            "Loan app is harassing my contacts",
            "online loan app calling my relatives and abusing me",
            "instant loan app sending my photo to contacts saying fraud",
            "loan recovery app threatening to leak my data what can i do",
        ],
    },
    {
        "id": "upi_otp_fraud",
        "product_priority": "critical",
        "expected_category": "cyber_fraud_or_harassment",
        "expected_route_any": ["cyber_fraud_or_harassment", "banking_credit_dispute"],
        "expected_act_hint": "Information Technology Act 2000 + Banking Ombudsman + BNS 2023",
        "must_include_any": ["cyber", "1930", "bank", "freeze", "complaint"],
        "variants": [
            "someone took otp and 50000 gone from my upi what should i do",
            "upi fraud happened yesterday bank says my mistake no refund",
            "fake customer care made me install app and money got transferred",
            "credit card unauthorized transaction bank not reversing amount",
        ],
    },
    {
        "id": "cibil_wrong_loan",
        "expected_category": "banking_credit_dispute",
        "expected_route_any": ["banking_credit_dispute"],
        "expected_act_hint": "Credit Information Companies Act 2005 + Banking Ombudsman",
        "must_include_any": ["cibil", "credit information", "bank", "dispute", "ombudsman"],
        "variants": [
            "CIBIL showing loan which i never took",
            "bank put wrong default in my credit score and not correcting",
            "fake loan in my pan affecting cibil what legal action",
            "nbfc reported overdue loan against me but i never signed",
        ],
    },
    {
        "id": "recovery_agent_threat",
        "expected_category": "banking_credit_dispute",
        "expected_route_any": ["banking_credit_dispute", "criminal_general"],
        "expected_act_hint": "Banking Ombudsman + BNS 2023",
        "must_include_any": ["recovery agent", "bank", "rbi", "complaint", "threat"],
        "variants": [
            "loan recovery agents came home and threatened my mother",
            "nbfc recovery people abusing me on phone and visiting office",
            "bajaj finance agent is threatening to shame me in society",
            "bank recovery agent took photos of my house can i complain",
        ],
    },
    {
        "id": "bike_theft_fir_refusal",
        "product_priority": "critical",
        "expected_category": "police_fir",
        "expected_route_any": ["police_fir", "criminal_general"],
        "expected_act_hint": "BNSS 2023 section 173 + BNS 2023 theft",
        "must_include_any": ["fir", "police", "sp", "magistrate", "complaint"],
        "variants": [
            "My bike is stolen, police is not filing FIR",
            "scooter stolen from parking station says give written complaint only",
            "mobile stolen and police refusing FIR saying lost report only",
            "my car was stolen but police saying wait 2 days before FIR",
        ],
    },
    {
        "id": "arrest_no_fir_copy",
        "product_priority": "critical",
        "expected_category": "arrest_custody_safeguard",
        "expected_route_any": ["arrest_custody_safeguard", "police_fir", "legal_aid"],
        "expected_act_hint": "Article 22 Constitution + BNSS 2023 section 173",
        "must_include_any": ["arrest", "fir copy", "magistrate", "legal aid", "family"],
        "variants": [
            "police has picked my son from my home in the night, i have not got FIR copy",
            "police took my brother at midnight and not telling station or case",
            "my husband arrested no arrest memo no FIR copy what urgent step",
            "police detained my son for 2 days and family not informed",
        ],
    },
    {
        "id": "false_fir_quashing",
        "product_priority": "critical",
        "expected_category": "criminal_defence_bail",
        "expected_route_any": ["criminal_defence_bail", "police_fir", "criminal_general"],
        "expected_act_hint": "BNSS 2023 section 528 + CrPC 1973 section 482",
        "must_include_any": ["quashing", "high court", "bail", "fir", "lawyer"],
        "variants": [
            "false FIR filed against my brother what can we do",
            "neighbour made false 420 case on me because of money dispute",
            "wife filed false 498a and police calling me how to protect",
            "false theft complaint after property fight can i cancel FIR",
        ],
    },
    {
        "id": "domestic_violence_now",
        "product_priority": "critical",
        "expected_category": "family_domestic",
        "expected_route_any": ["family_domestic", "police_fir", "criminal_general"],
        "expected_act_hint": "PWDVA 2005 + BNS 2023",
        "must_include_any": ["protection officer", "magistrate", "shelter", "police", "domestic violence"],
        "variants": [
            "My husband is beating me right now, what should I do?",
            "husband slapped me and threatening to throw me out tonight",
            "in laws beat me and took my phone i am unsafe",
            "my husband drinks and beats me every week where to complain",
        ],
    },
    {
        "id": "maintenance_not_paid",
        "expected_category": "family_domestic",
        "expected_route_any": ["family_domestic", "family_marriage_status"],
        "expected_act_hint": "BNSS 2023 maintenance + Family Courts Act 1984",
        "must_include_any": ["maintenance", "family court", "magistrate", "children", "income"],
        "variants": [
            "my husband left me with two kids and not giving money",
            "court ordered maintenance but husband is not paying for 8 months",
            "wife and child maintenance case where to file",
            "ex husband stopped child support what next legal step",
        ],
    },
    {
        "id": "wife_denies_sex",
        "expected_category": "family_marriage_status",
        "expected_route_any": ["family_marriage_status"],
        "expected_act_hint": "Hindu Marriage Act 1955 + Family Courts Act 1984",
        "must_include_any": ["family court", "counselling", "divorce", "facts", "matrimonial"],
        "variants": [
            "My wife denies sex from last 1 year, what to do",
            "wife is denying physical relation since marriage what is legal remedy",
            "my spouse refuses intimacy for many years can i file divorce",
            "no conjugal relation in marriage for 2 years what legal option",
        ],
    },
    {
        "id": "adultery_spouse",
        "expected_category": "family_marriage_status",
        "expected_route_any": ["family_marriage_status", "family_domestic"],
        "expected_act_hint": "Hindu Marriage Act 1955 + Family Courts Act 1984",
        "must_include_any": ["family court", "divorce", "evidence", "counselling", "matrimonial"],
        "variants": [
            "i caught my husband with another women having sex",
            "my wife is in relationship with another man what legal action",
            "husband admitted affair and wants divorce what should i do",
            "can i file criminal case for adultery by spouse in india",
        ],
    },
    {
        "id": "marriage_misrepresentation",
        "expected_category": "family_marriage_status",
        "expected_route_any": ["family_marriage_status"],
        "expected_act_hint": "Hindu Marriage Act 1955 + Family Courts Act 1984",
        "must_include_any": ["section 12", "voidable", "family court", "proof", "misrepresentation"],
        "variants": [
            "My husband told lies before marriage about his job and his salary, what to do",
            "husband lied before marriage about salary and loans what remedy",
            "wife hid previous job and income before marriage can marriage be cancelled",
            "in biodata groom said govt job but it was false after marriage",
        ],
    },
    {
        "id": "streedhan_not_returned",
        "expected_category": "family_domestic",
        "expected_route_any": ["family_domestic", "criminal_general"],
        "expected_act_hint": "PWDVA 2005 + Dowry Prohibition Act 1961 + BNS 2023",
        "must_include_any": ["stridhan", "streedhan", "gold", "protection officer", "police"],
        "variants": [
            "in laws are not returning my gold and jewellery after separation",
            "husband kept my streedhan locker keys and refusing return",
            "mother in law has my marriage gold what case can i file",
            "after divorce husband family not giving my jewellery back",
        ],
    },
    {
        "id": "child_custody_access",
        "expected_category": "child_custody_adoption",
        "expected_route_any": ["child_custody_adoption", "family_domestic", "family_marriage_status"],
        "expected_act_hint": "Guardians and Wards Act 1890 + Family Courts Act 1984",
        "must_include_any": ["custody", "visitation", "family court", "child welfare", "guardian"],
        "variants": [
            "wife not allowing me to meet my child after separation",
            "husband took child and not letting mother see her",
            "grandparents want visitation rights for grandson what to do",
            "my ex shifted child to another city without telling me",
        ],
    },
    {
        "id": "school_admission_denied",
        "expected_category": "education_rights",
        "expected_route_any": ["education_rights", "social_welfare_identity"],
        "expected_act_hint": "Right to Education Act 2009",
        "must_include_any": ["rte", "education officer", "school", "admission", "written reasons"],
        "variants": [
            "my daughter school admission is denied, despite her clearing admission exam",
            "school denied admission saying no birth certificate but child passed test",
            "private school refusing rte quota admission after selection list",
            "school not taking my son because aadhaar mismatch what to do",
        ],
    },
    {
        "id": "school_tc_refusal",
        "expected_category": "education_rights",
        "expected_route_any": ["education_rights"],
        "expected_act_hint": "Right to Education Act 2009",
        "must_include_any": ["transfer certificate", "tc", "education officer", "school", "written"],
        "variants": [
            "school is not giving TC because fees pending",
            "principal refusing transfer certificate for my child what legal step",
            "school holding marksheet and TC due to transport dues",
            "can school deny leaving certificate to 8 year old child",
        ],
    },
    {
        "id": "pan_aadhaar_mismatch",
        "expected_category": "social_welfare_identity",
        "expected_route_any": ["social_welfare_identity", "tax_gst_compliance"],
        "expected_act_hint": "Aadhaar Act 2016 + Income Tax Act",
        "must_include_any": ["aadhaar", "pan", "uidai", "income tax", "mismatch"],
        "variants": [
            "my pan and aadhar is mismatch",
            "pan aadhaar linking failed because name spelling different",
            "income tax portal says aadhaar dob mismatch how to fix",
            "PAN and Aadhaar not matching and refund stuck what remedy",
        ],
    },
    {
        "id": "ration_biometric_denial",
        "expected_category": "social_welfare_identity",
        "expected_route_any": ["social_welfare_identity"],
        "expected_act_hint": "National Food Security Act + Aadhaar Act 2016",
        "variant_expected_act_hints": {
            2: "National Food Security Act",
            3: "National Food Security Act",
        },
        "must_include_any": ["ration", "nfsa", "dealer", "grievance", "aadhaar"],
        "variants": [
            "ration shop denying food because fingerprint not matching",
            "pds dealer removed my mother name from ration card without notice",
            "ration card cancelled by panchayat and nobody giving reason",
            "biometric failed so dealer refused wheat and rice for family",
        ],
    },
    {
        "id": "pension_stopped",
        "expected_category": "social_welfare_identity",
        "expected_route_any": ["social_welfare_identity", "senior_citizen"],
        "expected_act_hint": "State Pension Scheme + Aadhaar Act 2016 + RTI Act 2005",
        "must_include_any": ["pension", "district social welfare", "aadhaar", "rti", "scheme"],
        "variants": [
            "old age pension stopped suddenly bank says aadhaar not linked",
            "widow pension not coming for 6 months where to complain",
            "disability pension rejected but no reason given by office",
            "my grandmother pension stopped after biometric failure",
        ],
    },
    {
        "id": "caste_certificate_rejected",
        "expected_category": "social_welfare_identity",
        "expected_route_any": ["social_welfare_identity", "tribal_caste_atrocity"],
        "expected_act_hint": "Constitution + RTI Act 2005",
        "must_include_any": ["caste certificate", "appeal", "revenue", "district", "rti"],
        "variants": [
            "caste certificate application rejected without reason",
            "tehsildar not issuing ST certificate even after documents",
            "OBC certificate pending for 8 months scholarship deadline near",
            "SC certificate cancelled by office what appeal is there",
        ],
    },
    {
        "id": "hospital_overcharge_records",
        "expected_category": "consumer",
        "expected_route_any": ["consumer"],
        "expected_act_hint": "Consumer Protection Act 2019 + Clinical Establishments Act",
        "must_include_any": ["hospital", "medical records", "consumer", "bill", "complaint"],
        "variants": [
            "hospital overcharged me and not giving detailed bill",
            "private hospital not giving medical records after discharge",
            "doctor did wrong treatment and hospital refusing case papers",
            "hospital charged extra for emergency and no receipt what to do",
        ],
    },
    {
        "id": "damaged_phone_return",
        "expected_category": "consumer",
        "expected_route_any": ["consumer"],
        "expected_act_hint": "Consumer Protection Act 2019",
        "must_include_any": ["consumer", "district commission", "refund", "replace", "invoice"],
        "variants": [
            "i have got damaged phone, company is not accepting the return, what to do",
            "online seller sent broken mobile and refuses replacement",
            "new laptop dead on arrival customer care closing complaint",
            "warranty service center not repairing my phone after 20 days",
        ],
    },
    {
        "id": "builder_delay",
        "expected_category": "consumer",
        "expected_route_any": ["consumer", "property_tenancy"],
        "expected_act_hint": "RERA + Consumer Protection Act 2019",
        "must_include_any": ["rera", "possession", "builder", "consumer", "agreement"],
        "variants": [
            "builder delayed flat possession for 3 years what can i do",
            "developer not giving occupancy certificate after taking full money",
            "builder changed layout and not refunding booking amount",
            "rera registered project missed deadline how to complain",
        ],
    },
    {
        "id": "cab_aggregator_overcharge",
        "expected_category": "consumer",
        "expected_route_any": ["consumer", "digital_platform_account"],
        "expected_act_hint": "Consumer Protection Act 2019 + Motor Vehicle Aggregator Guidelines",
        "must_include_any": ["consumer", "aggregator", "cab", "refund", "grievance"],
        "variants": [
            "ola driver took longer route and charged extra fare customer care not helping",
            "uber cancelled ride but deducted money and not refunding",
            "cab app driver abused me and platform closed complaint",
            "auto app charged double fare after ride what legal remedy",
        ],
    },
    {
        "id": "salary_unpaid",
        "expected_category": "employment_wages",
        "expected_route_any": ["employment_wages", "labour_exploitation_discrimination"],
        "expected_act_hint": "Code on Wages 2019 + Payment of Wages Act",
        "must_include_any": ["salary", "wages", "labour", "notice", "commissioner"],
        "variants": [
            "company not paying my salary for 3 months what to do",
            "employer fired me and holding last month salary",
            "contractor not paying wages after site work completed",
            "startup founder says no funds and asked us to wait salary pending",
        ],
    },
    {
        "id": "pf_not_deposited",
        "expected_category": "employment_wages",
        "expected_route_any": ["employment_wages"],
        "expected_act_hint": "EPF Act + Code on Social Security",
        "must_include_any": ["epf", "pf", "epfo", "uan", "employer"],
        "variants": [
            "company deducted PF but not depositing in my UAN",
            "employer not approving PF transfer after resignation",
            "pf balance missing and HR not replying what complaint",
            "factory deducted provident fund but passbook shows zero",
        ],
    },
    {
        "id": "maternity_job_loss",
        "expected_category": "employment_wages",
        "expected_route_any": ["employment_wages", "workplace_sexual_harassment"],
        "expected_act_hint": "Maternity Benefit Act 1961",
        "must_include_any": ["maternity", "pregnant", "labour", "employer", "benefit"],
        "variants": [
            "company terminated me after i told them i am pregnant",
            "employer refusing maternity leave saying probation employee",
            "HR asked me to resign because of pregnancy what legal remedy",
            "maternity salary not paid after delivery company not responding",
        ],
    },
    {
        "id": "workplace_posh",
        "expected_category": "workplace_sexual_harassment",
        "expected_route_any": ["workplace_sexual_harassment"],
        "expected_act_hint": "POSH Act 2013",
        "must_include_any": ["posh", "internal committee", "local committee", "workplace", "complaint"],
        "variants": [
            "manager sends dirty messages and HR says ignore",
            "boss touched me in office but company has no POSH committee",
            "colleague asking for dinner and promotion favour what complaint",
            "i complained sexual harassment and now they put me on PIP",
        ],
    },
    {
        "id": "construction_injury",
        "expected_category": "workplace_injury_compensation",
        "expected_route_any": ["workplace_injury_compensation", "employment_wages"],
        "expected_act_hint": "Employees Compensation Act + BOCW Act",
        "variant_expected_act_hints": {
            2: "Employees Compensation Act",
            4: "Employees Compensation Act",
        },
        "must_include_any": ["compensation", "injury", "employer", "labour", "medical"],
        "variants": [
            "fell from construction site and contractor not paying hospital bill",
            "factory machine cut my finger company says no insurance",
            "worker died at site and owner not giving compensation",
            "boiler blast injured my father at factory what claim",
        ],
    },
    {
        "id": "nude_photo_blackmail",
        "product_priority": "critical",
        "expected_category": "cyber_fraud_or_harassment",
        "expected_route_any": ["cyber_fraud_or_harassment", "police_fir"],
        "expected_act_hint": "Information Technology Act 2000 + BNS 2023",
        "must_include_any": ["cyber", "private photo", "blackmail", "police", "report"],
        "variants": [
            "ex boyfriend has my private photos and threatening to post online",
            "someone made my nude photo and blackmailing on instagram",
            "girl on video call recorded me and demanding money",
            "morphed naked photo of me is circulating in college group",
        ],
    },
    {
        "id": "digital_arrest_scam",
        "product_priority": "critical",
        "expected_category": "cyber_fraud_or_harassment",
        "expected_route_any": ["cyber_fraud_or_harassment", "police_fir"],
        "expected_act_hint": "Information Technology Act 2000 + BNS 2023",
        "must_include_any": ["cyber", "1930", "bank", "fraud", "police"],
        "variants": [
            "fake police video call said digital arrest and took my money",
            "parcel has drugs scam made me transfer 2 lakh what to do",
            "fake CBI call kept me on video and asked for bank transfer",
            "digital arrest fraud happened today can money be frozen",
        ],
    },
    {
        "id": "fake_social_account",
        "expected_category": "cyber_fraud_or_harassment",
        "expected_route_any": ["cyber_fraud_or_harassment"],
        "expected_act_hint": "Information Technology Act 2000 + BNS 2023",
        "must_include_any": ["cyber", "fake account", "platform", "police", "complaint"],
        "variants": [
            "someone made fake instagram account using my photos",
            "fake facebook profile abusing my family what legal action",
            "unknown person posting my number on dating app",
            "telegram channel using my photo and calling me fraud",
        ],
    },
    {
        "id": "online_gaming_wallet_stuck",
        "expected_category": "digital_platform_account",
        "expected_route_any": ["digital_platform_account", "consumer", "banking_credit_dispute"],
        "expected_act_hint": "Consumer Protection Act 2019 + IT Act 2000",
        "must_include_any": ["platform", "consumer", "wallet", "refund", "grievance"],
        "variants": [
            "online gaming app not allowing withdrawal of my money",
            "fantasy app blocked my account after winning amount",
            "crypto exchange froze my wallet and support not replying",
            "app wallet money stuck and company says KYC under review",
        ],
    },
    {
        "id": "aadhaar_fake_loan",
        "expected_category": "social_welfare_identity",
        "expected_route_any": ["social_welfare_identity", "banking_credit_dispute", "cyber_fraud_or_harassment"],
        "expected_act_hint": "Aadhaar Act 2016 + Credit Information Companies Act 2005 + IT Act 2000",
        "must_include_any": ["aadhaar", "cibil", "loan", "bank", "cyber"],
        "variants": [
            "someone used my aadhaar and took loan in my name",
            "fake loan opened with my PAN and Aadhaar what can i do",
            "my aadhaar used for sim and fraud case came to me",
            "nbfc loan showing on my documents but signature not mine",
        ],
    },
    {
        "id": "senior_thrown_out",
        "product_priority": "critical",
        "expected_category": "senior_citizen",
        "expected_route_any": ["senior_citizen", "family_domestic"],
        "expected_act_hint": "Senior Citizens Act 2007",
        "must_include_any": ["senior citizen", "maintenance tribunal", "son", "residence", "district"],
        "variants": [
            "my son threw me out of my own house i paid for it",
            "elderly mother is being forced out by children what law",
            "son not taking care of old father and took his pension",
            "senior citizen wants house back from son after gift deed",
        ],
    },
    {
        "id": "parent_maintenance",
        "expected_category": "senior_citizen",
        "expected_route_any": ["senior_citizen"],
        "expected_act_hint": "Senior Citizens Act 2007",
        "must_include_any": ["maintenance", "tribunal", "parents", "senior citizen", "children"],
        "variants": [
            "can parents claim maintenance from son who earns well",
            "daughter not supporting old mother medical expenses",
            "father wants monthly maintenance from children where to file",
            "son stopped paying 10000 ordered by senior citizen tribunal",
        ],
    },
    {
        "id": "tribal_land_transfer",
        "expected_category": "tribal_caste_atrocity",
        "expected_route_any": ["tribal_caste_atrocity", "land_revenue_records", "property_tenancy"],
        "expected_act_hint": "Scheduled Areas Land Transfer Regulation + PESA + Constitution",
        "must_include_any": ["tribal", "scheduled area", "land", "collector", "gram sabha"],
        "variants": [
            "adivasi land sold to non tribal in agency area can it be cancelled",
            "tribal family land transferred by moneylender using blank paper",
            "non tribal bought our scheduled area land and patwari mutated it",
            "my ST land in Jharkhand was sold without permission what remedy",
        ],
    },
    {
        "id": "caste_slur_fir_refusal",
        "product_priority": "critical",
        "expected_category": "tribal_caste_atrocity",
        "expected_route_any": ["tribal_caste_atrocity", "police_fir"],
        "expected_act_hint": "SC/ST POA Act + BNSS 2023",
        "must_include_any": ["sc/st", "atrocity", "special court", "sp", "fir"],
        "variants": [
            "police not taking FIR for caste abuse against my dalit father",
            "neighbour used caste slur and hit me but station refuses case",
            "ST woman abused by caste name in public what sections apply",
            "shop owner denied service saying my caste and police laughing",
        ],
    },
    {
        "id": "witch_branding_attack",
        "product_priority": "critical",
        "expected_category": "police_fir",
        "expected_route_any": ["police_fir", "tribal_caste_atrocity"],
        "expected_act_hint": "Witch-Hunting State Acts + BNS 2023 + BNSS 2023",
        "must_include_any": ["witch", "daayan", "police", "state", "fir"],
        "variants": [
            "village people called my mother daayan and beat her",
            "ojha branded my aunt witch and stripped her in public",
            "neighbours say my mother does black magic and threatening to kill",
            "in Jharkhand they called her dayan and police not helping",
        ],
    },
    {
        "id": "asha_honorarium",
        "expected_category": "social_welfare_identity",
        "expected_route_any": ["social_welfare_identity", "employment_wages"],
        "expected_act_hint": "State Welfare Scheme + RTI Act 2005",
        "must_include_any": ["asha", "honorarium", "health", "district", "rti"],
        "variants": [
            "ASHA worker incentive not paid for 8 months where complaint",
            "NHM office not releasing my ASHA honorarium",
            "health department says no budget for ASHA payments what remedy",
            "asha did vaccination work but block office not paying",
        ],
    },
    {
        "id": "mgnrega_wage",
        "expected_category": "social_welfare_identity",
        "expected_route_any": ["social_welfare_identity", "labour_exploitation_discrimination"],
        "expected_act_hint": "MGNREGA + RTI Act 2005",
        "must_include_any": ["mgnrega", "nrega", "job card", "wages", "grievance"],
        "variants": [
            "MGNREGA wages not paid even though muster roll has my name",
            "job card work done but nrega payment pending for 3 months",
            "muster roll has fake attendance in my name what to do",
            "gram panchayat not giving work under mgnrega after application",
        ],
    },
    {
        "id": "road_accident_claim",
        "expected_category": "motor_accident_claims",
        "expected_route_any": ["motor_accident_claims", "consumer", "criminal_general", "police_fir"],
        "expected_act_hint": "Motor Vehicles Act",
        "must_include_any": ["motor", "accident", "maact", "insurance", "fir"],
        "variants": [
            "bike hit my father and insurance company not paying claim",
            "road accident injury how to claim compensation from vehicle owner",
            "truck accident FIR done but insurer denying hospital bill",
            "hit and run case what compensation can victim family get",
        ],
    },
    {
        "id": "cheque_bounce",
        "expected_category": "cheque_bounce",
        "expected_route_any": ["cheque_bounce", "business_contract_partnership"],
        "expected_act_hint": "NI Act 1881 section 138",
        "must_include_any": ["cheque", "138", "notice", "dishonour", "limitation"],
        "variants": [
            "cheque of 3 lakh bounced stop payment what can i do",
            "client cheque returned funds insufficient legal notice time",
            "friend gave cheque for loan repayment and bank returned it",
            "dishonoured cheque case limitation how many days for notice",
        ],
    },
    {
        "id": "education_loan_denial",
        "expected_category": "education_loan_denial",
        "expected_route_any": ["education_loan_denial", "banking_credit_dispute"],
        "expected_act_hint": "Banking Ombudsman + Consumer Protection Act 2019",
        "must_include_any": ["education loan", "bank", "ombudsman", "student", "complaint"],
        "variants": [
            "bank denied education loan even after college admission",
            "student loan rejected without reason and admission deadline near",
            "education loan subsidy not given by bank what complaint",
            "bank asking collateral for small education loan is it legal",
        ],
    },
    {
        "id": "passport_verification",
        "expected_category": "passport_police_verification",
        "expected_route_any": ["passport_police_verification"],
        "expected_act_hint": "Passports Act 1967",
        "must_include_any": ["passport", "rpo", "police verification", "file number", "grievance"],
        "variants": [
            "passport police verification adverse report without reason",
            "police not clearing passport verification asking money",
            "RPO put passport on hold due to old FIR what to do",
            "passport application pending after police visit for 2 months",
        ],
    },
    {
        "id": "name_change_gazette",
        "expected_category": "social_welfare_identity",
        "expected_route_any": ["social_welfare_identity", "court_procedure"],
        "expected_act_hint": "Gazette Name Change Procedure",
        "must_include_any": ["gazette", "affidavit", "newspaper", "name change", "documents"],
        "variants": [
            "how to legally change my name in all documents",
            "name spelling wrong in certificates need gazette process",
            "can i change surname after marriage in passport and aadhaar",
            "adult name change affidavit newspaper gazette steps please",
        ],
    },
    {
        "id": "birth_certificate_delay",
        "expected_category": "social_welfare_identity",
        "expected_route_any": ["social_welfare_identity"],
        "expected_act_hint": "Births and Deaths Act",
        "must_include_any": ["birth certificate", "registrar", "municipal", "certificate", "appeal"],
        "variants": [
            "panchayat secretary not giving birth certificate of my child",
            "birth certificate has wrong mother name how to correct",
            "late birth registration for home delivery what documents",
            "municipality rejected birth certificate correction without reason",
        ],
    },
    {
        "id": "income_tax_notice",
        "expected_category": "tax_gst_compliance",
        "expected_route_any": ["tax_gst_compliance"],
        "expected_act_hint": "Income Tax Act",
        "must_include_any": ["income tax", "notice", "portal", "reply", "assessment"],
        "variants": [
            "income tax 143(1) notice says demand but I already paid",
            "ITR refund stuck and income tax portal shows defective return",
            "TDS in 26AS not matching salary slip what to do",
            "income tax notice for old cash deposit how to reply",
        ],
    },
    {
        "id": "gst_notice",
        "expected_category": "tax_gst_compliance",
        "expected_route_any": ["tax_gst_compliance"],
        "expected_act_hint": "CGST Act",
        "must_include_any": ["gst", "notice", "reply", "portal", "officer"],
        "variants": [
            "GST department sent notice for mismatch 2A and 3B",
            "gst officer blocked my input credit without hearing",
            "small shop got gst penalty notice and deadline tomorrow",
            "e way bill mistake and goods detained by GST officer",
        ],
    },
]


EXTRA_FOURTH_VARIANT_SCENARIOS = {
    # Real UI pain / highest-volume common-user surfaces.
    "tenant_not_vacating_rent",
    "landlord_deposit_refund",
    "family_hand_loan_recovery",
    "joint_plot_sold",
    "legal_heir_property_sale",
    "shop_sealed_municipality",
    "street_vendor_cart_removed",
    "bank_wrong_debit",
    "bank_account_frozen",
    "loan_app_harassment_contacts",
    "upi_otp_fraud",
    "bike_theft_fir_refusal",
    "arrest_no_fir_copy",
    "domestic_violence_now",
    "wife_denies_sex",
    "adultery_spouse",
    "marriage_misrepresentation",
    "school_admission_denied",
    "pan_aadhaar_mismatch",
    "ration_biometric_denial",
    "hospital_overcharge_records",
    "damaged_phone_return",
    "salary_unpaid",
    "nude_photo_blackmail",
    "digital_arrest_scam",
    "caste_slur_fir_refusal",
}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=Path("/tmp/law_rag_common_user_200_20260603/prompts"),
        help="Directory that will receive common_user_200.jsonl",
    )
    parser.add_argument("--filename", default="common_user_200.jsonl")
    parser.add_argument("--limit", type=int, default=200)
    args = parser.parse_args()

    rows = build_rows(limit=args.limit)
    args.out_dir.mkdir(parents=True, exist_ok=True)
    out = args.out_dir / args.filename
    out.write_text(
        "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows),
        encoding="utf-8",
    )
    print(f"wrote {len(rows)} rows -> {out}")
    return 0


def build_rows(*, limit: int = 200) -> list[dict[str, Any]]:
    for scenario in SCENARIOS:
        variants = scenario.get("variants") or []
        if len(variants) != 4:
            raise ValueError(f"{scenario['id']} must have exactly 4 variants")
    if limit == 200:
        unknown_extra = EXTRA_FOURTH_VARIANT_SCENARIOS - {scenario["id"] for scenario in SCENARIOS}
        if unknown_extra:
            raise ValueError(f"unknown fourth-variant scenario ids: {sorted(unknown_extra)}")
        rows = [
            _row_for_variant(scenario, variant_idx)
            for variant_idx in (1, 2, 3)
            for scenario in SCENARIOS
        ]
        rows.extend(
            _row_for_variant(scenario, 4)
            for scenario in SCENARIOS
            if scenario["id"] in EXTRA_FOURTH_VARIANT_SCENARIOS
        )
    else:
        rows = [
            _row_for_variant(scenario, variant_idx)
            for variant_idx in (1, 2, 3, 4)
            for scenario in SCENARIOS
        ][:limit]

    seen: set[str] = set()
    duplicates: list[str] = []
    for row in rows:
        key = row["query"].strip().lower()
        if key in seen:
            duplicates.append(row["query"])
        seen.add(key)
    if duplicates:
        raise ValueError(f"duplicate queries: {duplicates[:5]}")
    if len(rows) != limit:
        raise ValueError(f"expected exactly {limit} rows, got {len(rows)}")
    return rows


def _row_for_variant(scenario: Scenario, variant_idx: int) -> dict[str, Any]:
    query = scenario["variants"][variant_idx - 1]
    expected_act_hint = (
        scenario.get("variant_expected_act_hints", {}).get(variant_idx)
        or scenario["expected_act_hint"]
    )
    return {
        "query": query,
        "persona": "common_user_200",
        "common_issue": scenario["id"],
        "prompt_variant": variant_idx,
        "product_priority": scenario.get("product_priority", "high"),
        "expected_category": scenario["expected_category"],
        "expected_act_hint": expected_act_hint,
        "expected_route_any": scenario.get("expected_route_any", [scenario["expected_category"]]),
        "must_include_any": scenario.get("must_include_any", []),
        "must_include_all": scenario.get("must_include_all", []),
        "synthetic_note": "curated common-user smoke prompt; not a real user log",
    }


if __name__ == "__main__":
    raise SystemExit(main())
