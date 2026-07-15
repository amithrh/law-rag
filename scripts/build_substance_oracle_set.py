#!/usr/bin/env python3
"""Build a substance-oriented legal QA oracle prompt set.

This set is intentionally stricter than the structural common-user gate. Each
row carries answer-body expectations for the exact user variant: forum, first
step, role framing, and discriminating legal terms. The generated JSONL is an
eval artifact, not corpus data.
"""
from __future__ import annotations

import argparse
import json
import random
import re
from pathlib import Path
from typing import Any


Scenario = dict[str, Any]


STYLE_PREFIXES = (
    "",
    "pls help, ",
    "urgent please tell me, ",
    "can u tell ",
)
STYLE_SUFFIXES = (
    "",
    " what next",
    " what can i do",
    " where to go",
)


SCENARIOS: list[Scenario] = [
    {
        "id": "account_freeze_unknown_police",
        "priority": "critical",
        "harm_bucket": "banking_platform_money",
        "expected_route_any": ["banking_credit_dispute", "cyber_fraud_or_harassment", "police_fir"],
        "expected_act_hint": "Banking Ombudsman + BNSS 2023 + Information Technology Act 2000",
        "queries": [
            "my bank account is frozen and branch says police request but no notice",
            "salary account blocked by lien after cyber complaint i dont know the case",
            "upi account freeze ho gaya bank police bol raha but complaint number nahi",
        ],
        "oracle": {
            "required_groups": [
                {"name": "freeze_variant", "any": ["freeze", "frozen", "lien", "blocked"]},
                {"name": "banking_forum", "any": ["rbi", "ombudsman", "cms"]},
                {"name": "police_cyber_step", "any": ["cyber", "police", "1930", "acknowledgement"]},
                {"name": "documents", "any": ["account statement", "transaction", "freeze order", "complaint number", "lien remark"]},
            ],
            "forbidden_any": ["only consumer court", "not a legal issue"],
        },
    },
    {
        "id": "loan_app_contacts_harassment",
        "priority": "critical",
        "harm_bucket": "banking_platform_money",
        "expected_route_any": ["banking_credit_dispute", "cyber_fraud_or_harassment", "criminal_general"],
        "expected_act_hint": "Banking Ombudsman + Information Technology Act 2000 + BNS 2023 + Digital Personal Data Protection Act",
        "queries": [
            "loan app is harassing my contacts and sending my photo",
            "instant loan app calling relatives abusing me and threatening data leak",
            "online loan recovery app made whatsapp group with my contacts",
        ],
        "oracle": {
            "required_groups": [
                {"name": "loan_app_variant", "any": ["loan app", "recovery app", "contacts", "data leak"]},
                {"name": "platform_safety_step", "any": ["cyber", "1930", "police", "evidence", "screenshots"]},
                {"name": "banking_regulator", "any": ["rbi", "ombudsman", "regulated entity", "nbfc"]},
                {"name": "privacy_data", "any": ["data", "contacts", "privacy", "dpdp"]},
            ],
            "forbidden_any": ["just repay", "nothing can be done"],
        },
    },
    {
        "id": "wrong_bank_debit",
        "priority": "high",
        "harm_bucket": "banking_platform_money",
        "expected_route_any": ["banking_credit_dispute", "consumer"],
        "expected_act_hint": "Banking Ombudsman + Consumer Protection Act 2019",
        "queries": [
            "bank deducted money wrongly and customer care not helping",
            "my bank debited twice for one transaction no refund",
            "wrong debit from savings account branch not giving written answer",
        ],
        "oracle": {
            "required_groups": [
                {"name": "wrong_debit_variant", "any": ["wrong debit", "deducted", "debited", "unauthorised", "unauthorized"]},
                {"name": "rbi_forum", "any": ["rbi", "ombudsman", "cms"]},
                {"name": "first_step", "any": ["written complaint", "complaint number", "raise complaint", "bank grievance"]},
                {"name": "documents", "any": ["statement", "transaction id", "sms", "email"]},
            ],
            "forbidden_any": ["national consumer commission as first step"],
        },
    },
    {
        "id": "bike_theft_fir_refusal",
        "priority": "critical",
        "harm_bucket": "criminal_procedure_high_risk",
        "expected_route_any": ["police_fir", "criminal_general"],
        "expected_act_hint": "BNSS 2023 section 173 + BNS 2023 theft",
        "queries": [
            "my bike is stolen police is not filing fir",
            "mobile stolen and police saying lost report only no fir",
            "scooter stolen station refusing fir saying come tomorrow",
        ],
        "oracle": {
            "required_groups": [
                {"name": "fir_variant", "any": ["fir", "first information", "cognizable"]},
                {"name": "police_escalation", "any": ["sp", "superintendent", "magistrate", "senior police"]},
                {"name": "written_proof", "any": ["written complaint", "acknowledgement", "diary number", "copy"]},
                {"name": "theft_context", "any": ["stolen", "theft", "vehicle", "mobile", "bike", "scooter"]},
            ],
            "forbidden_any": ["only civil court", "wait indefinitely"],
        },
    },
    {
        "id": "midnight_pickup_no_fir",
        "priority": "critical",
        "harm_bucket": "criminal_procedure_high_risk",
        "expected_route_any": ["arrest_custody_safeguard", "police_fir", "legal_aid"],
        "expected_act_hint": "Article 22 Constitution + BNSS 2023 arrest safeguards",
        "queries": [
            "police picked my son at night no fir copy and not telling station",
            "my husband arrested no arrest memo no family information",
            "police took brother 2 days ago and not producing before magistrate",
        ],
        "oracle": {
            "required_groups": [
                {"name": "custody_variant", "any": ["arrest", "detained", "custody", "picked"]},
                {"name": "urgent_forum", "any": ["magistrate", "legal aid", "dlsa", "habeas", "lawyer"]},
                {"name": "family_rights", "any": ["family", "arrest memo", "fir copy", "grounds of arrest"]},
                {"name": "time_sensitivity", "any": ["24 hours", "immediate", "urgent", "produced"]},
            ],
            "forbidden_any": ["wait for chargesheet", "only file consumer complaint"],
        },
    },
    {
        "id": "default_bail_no_chargesheet",
        "priority": "critical",
        "harm_bucket": "criminal_procedure_high_risk",
        "expected_route_any": ["criminal_defence_bail"],
        "expected_act_hint": "BNSS 2023 default bail custody limits + CrPC 1973 section 167 for old cases",
        "queries": [
            "brother in jail 90 days no chargesheet cheating case default bail possible",
            "my son in custody 60 days police not filed charge sheet what bail",
            "undertrial 6 months no chargesheet how to ask statutory bail",
        ],
        "oracle": {
            "required_groups": [
                {"name": "default_bail_variant", "any": ["default bail", "statutory bail", "chargesheet", "charge sheet"]},
                {"name": "custody_days", "any": ["60", "90", "custody period", "days"]},
                {"name": "court_forum", "any": ["magistrate", "sessions court", "trial court"]},
                {"name": "date_regime", "any": ["incident date", "bnss", "crpc", "before 1 july 2024"]},
            ],
            "forbidden_any": ["anticipatory bail is the main remedy"],
        },
    },
    {
        "id": "surety_unaffordable",
        "priority": "critical",
        "harm_bucket": "criminal_procedure_high_risk",
        "expected_route_any": ["criminal_defence_bail"],
        "expected_act_hint": "BNSS 2023 bail bond/surety provisions + Article 21",
        "queries": [
            "bail granted but poor family cannot arrange 50000 surety",
            "uncle got bail order but jail not releasing because surety amount high",
            "court asked two local sureties we are migrants what to do",
        ],
        "oracle": {
            "required_groups": [
                {"name": "surety_variant", "any": ["surety", "bond", "bail condition", "personal bond"]},
                {"name": "modification_step", "any": ["modify", "relax", "reduce", "substitute", "personal bond"]},
                {"name": "court_forum", "any": ["same court", "bail court", "trial court", "magistrate"]},
                {"name": "documents", "any": ["income", "poverty", "order copy", "jail", "address proof"]},
            ],
            "forbidden_any": ["pay the amount somehow", "new anticipatory bail"],
        },
    },
    {
        "id": "ndps_quantity_bail",
        "priority": "critical",
        "harm_bucket": "criminal_procedure_high_risk",
        "expected_route_any": ["criminal_defence_bail"],
        "expected_act_hint": "NDPS Act 1985 quantity classification + Section 37",
        "queries": [
            "brother arrested ndps 50 gram heroin commercial or not bail chances",
            "friend caught with 200mg mdma in goa what punishment and bail",
            "bhang lassi at holi police saying ndps mahabaleshwar what to do",
        ],
        "oracle": {
            "required_groups": [
                {"name": "ndps_variant", "any": ["ndps", "heroin", "mdma", "bhang", "ganja", "quantity"]},
                {"name": "quantity_step", "any": ["small quantity", "commercial quantity", "intermediate", "fsl", "lab report"]},
                {"name": "bail_bar", "any": ["section 37", "special court", "bail"]},
                {"name": "documents", "any": ["seizure memo", "panchnama", "fsl", "lab"]},
            ],
            "forbidden_any": ["consumer complaint", "only pay fine"],
        },
    },
    {
        "id": "medical_custody_care",
        "priority": "critical",
        "harm_bucket": "criminal_procedure_high_risk",
        "expected_route_any": ["criminal_defence_bail", "custody_compensation", "legal_aid"],
        "expected_act_hint": "Article 21 Constitution + BNSS 2023 bail/custody medical care",
        "queries": [
            "husband in arthur road jail tb test not done jail doctor waiting 4 months",
            "pregnant woman undertrial byculla not getting hospital checkup",
            "father 65 in jail serious kidney issue need medical bail",
        ],
        "oracle": {
            "required_groups": [
                {"name": "medical_variant", "any": ["medical", "hospital", "tb", "pregnant", "kidney", "doctor"]},
                {"name": "court_medical_step", "any": ["medical status report", "medical bail", "interim bail", "hospital examination"]},
                {"name": "forum", "any": ["trial court", "sessions court", "magistrate", "dlsa", "jail superintendent"]},
                {"name": "urgency", "any": ["urgent", "immediate", "health", "treatment"]},
            ],
            "forbidden_any": ["wait until regular hearing only"],
        },
    },
    {
        "id": "wife_beating_now",
        "priority": "critical",
        "harm_bucket": "family_child_safety",
        "expected_route_any": ["family_domestic", "police_fir", "criminal_general"],
        "expected_act_hint": "PWDVA 2005 + BNS 2023",
        "queries": [
            "my husband is beating me right now what should i do",
            "husband slapped me and threatening to throw me out tonight",
            "in laws beat me took phone i am unsafe at home",
        ],
        "oracle": {
            "required_groups": [
                {"name": "immediate_safety", "any": ["safe place", "emergency", "police", "112", "shelter"]},
                {"name": "dv_forum", "any": ["protection officer", "magistrate", "pwdva", "domestic violence"]},
                {"name": "evidence", "any": ["medical", "photos", "messages", "evidence", "records"]},
                {"name": "relief", "any": ["protection order", "residence order", "monetary relief", "shelter"]},
            ],
            "forbidden_any": ["first try to adjust", "normal marital dispute"],
        },
    },
    {
        "id": "wife_denying_sex",
        "priority": "high",
        "harm_bucket": "family_child_safety",
        "expected_route_any": ["family_marriage_status", "family_domestic"],
        "expected_act_hint": "Hindu Marriage Act 1955 / Special Marriage Act 1954 + Family Courts Act 1984",
        "queries": [
            "my wife is denying sex since many years what to do",
            "wife refusing physical relation for one year can i file case",
            "no marital relationship after marriage legal remedy husband asking",
        ],
        "oracle": {
            "required_groups": [
                {"name": "marriage_variant", "any": ["marriage", "matrimonial", "conjugal", "cruelty", "counselling"]},
                {"name": "family_forum", "any": ["family court", "counselling", "lawyer"]},
                {"name": "safe_framing", "any": ["consent", "no force", "cannot force", "do not force", "specific facts", "not automatic"]},
                {"name": "relief_options", "any": ["divorce", "restitution", "judicial separation", "mediation"]},
            ],
            "forbidden_any": ["force wife", "force your wife", "force her", "force sex", "criminal case against wife for denying sex", "marital right to sex"],
        },
    },
    {
        "id": "marriage_salary_lie",
        "priority": "high",
        "harm_bucket": "family_child_safety",
        "expected_route_any": ["family_marriage_status", "family_domestic"],
        "expected_act_hint": "Hindu Marriage Act 1955 / Special Marriage Act 1954 + Family Courts Act 1984",
        "queries": [
            "husband told lies about salary and loans before marriage what to do",
            "wife family hid her earlier marriage before wedding remedy",
            "spouse lied about job before marriage can marriage be cancelled",
        ],
        "oracle": {
            "required_groups": [
                {"name": "misrepresentation_variant", "any": ["misrepresentation", "fraud", "consent", "lied", "concealed"]},
                {"name": "family_forum", "any": ["family court", "matrimonial", "lawyer"]},
                {"name": "fact_sensitivity", "any": ["proof", "timeline", "not every lie", "material fact"]},
                {"name": "relief_options", "any": ["annulment", "divorce", "maintenance", "counselling"]},
            ],
            "forbidden_any": ["automatically void", "police fir is first step"],
        },
    },
    {
        "id": "child_school_admission_denied",
        "priority": "high",
        "harm_bucket": "family_child_safety",
        "expected_route_any": ["education_rights", "social_welfare_identity"],
        "expected_act_hint": "Right to Education Act 2009",
        "queries": [
            "my daughter cleared admission exam but school denied admission",
            "private school refusing tc and admission for my child",
            "rte quota admission selected but school asking donation",
        ],
        "oracle": {
            "required_groups": [
                {"name": "education_variant", "any": ["school", "admission", "tc", "rte"]},
                {"name": "education_forum", "any": ["education officer", "rte", "school authority", "district"]},
                {"name": "written_reason", "any": ["written reason", "rejection", "application", "receipt"]},
                {"name": "child_context", "any": ["child", "daughter", "student"]},
            ],
            "forbidden_any": ["labour commissioner"],
        },
    },
    {
        "id": "tenant_not_vacating",
        "priority": "high",
        "harm_bucket": "property_civil_practical",
        "expected_route_any": ["property_tenancy"],
        "expected_act_hint": "Transfer of Property Act 1882 + state rent control law",
        "queries": [
            "my tenant is not vacating house and not paying rent",
            "shop tenant not leaving after agreement expired and rent pending",
            "tenant stopped rent can i lock the house and remove items",
        ],
        "oracle": {
            "required_groups": [
                {"name": "tenancy_variant", "any": ["tenant", "rent", "lease", "eviction", "vacating"]},
                {"name": "lawful_route", "any": ["legal notice", "rent authority", "civil court", "eviction"]},
                {"name": "documents", "any": ["rent agreement", "receipts", "arrears", "notice"]},
                {"name": "anti_self_help", "any": ["do not use locks", "without self-help", "court", "lawful"]},
            ],
            "forbidden_any": ["lock the tenant out", "throw out belongings"],
        },
    },
    {
        "id": "joint_plot_sold",
        "priority": "high",
        "harm_bucket": "property_civil_practical",
        "expected_route_any": ["property_tenancy", "succession_inheritance", "criminal_general"],
        "expected_act_hint": "Transfer of Property Act 1882 + Specific Relief Act 1963",
        "queries": [
            "brother and i bought plot together now he sold it without me",
            "one co owner sold full property without my consent can i cancel sale",
            "joint land in my and brother name but he sold whole land",
        ],
        "oracle": {
            "required_groups": [
                {"name": "coowner_variant", "any": ["co-owner", "co owner", "joint", "share", "title"]},
                {"name": "civil_remedy", "any": ["injunction", "partition", "declaration", "civil court"]},
                {"name": "documents", "any": ["sale deed", "title deed", "land records", "registration"]},
                {"name": "caveat", "any": ["your share", "consent", "facts", "title"]},
            ],
            "forbidden_any": ["criminal fir is always enough"],
        },
    },
    {
        "id": "one_heir_refuses_sale",
        "priority": "high",
        "harm_bucket": "property_civil_practical",
        "expected_route_any": ["succession_inheritance", "property_tenancy"],
        "expected_act_hint": "Hindu Succession Act 1956 + Transfer of Property Act 1882",
        "queries": [
            "can i sell property if one legal heir is not agreeing",
            "father died one sister not signing sale papers can we sell house",
            "all heirs want to sell ancestral land but one brother refuses",
        ],
        "oracle": {
            "required_groups": [
                {"name": "heir_variant", "any": ["legal heir", "heir", "succession", "inherited"]},
                {"name": "consent_partition", "any": ["partition", "share", "consent", "undivided share"]},
                {"name": "forum", "any": ["civil court", "family settlement", "partition suit"]},
                {"name": "documents", "any": ["death certificate", "legal heir", "title", "sale deed"]},
            ],
            "forbidden_any": ["majority heirs can sell entire property"],
        },
    },
    {
        "id": "shop_sealed_municipality",
        "priority": "high",
        "harm_bucket": "business_tax_procedure",
        "expected_route_any": ["business_license_compliance", "street_vendor_municipal", "property_tenancy"],
        "expected_act_hint": "Shops and Establishments Act + municipal licensing procedure + state municipal law",
        "queries": [
            "my shop is in gujarat and municipality sealed it",
            "corporation sealed my restaurant without notice licence issue",
            "local body locked commercial shop saying trade licence pending",
        ],
        "oracle": {
            "required_groups": [
                {"name": "municipal_variant", "any": ["municipal", "municipality", "corporation", "sealed", "sealing", "seal", "licence"]},
                {"name": "immediate_step", "any": ["sealing order", "notice", "written order", "appeal", "reopen", "release"]},
                {"name": "forum", "any": ["municipal authority", "appellate", "high court", "civil court"]},
                {"name": "state_caveat", "any": ["state", "local", "gujarat", "municipal law"]},
            ],
            "forbidden_any": ["consumer court first"],
        },
    },
    {
        "id": "street_vendor_cart_removed",
        "priority": "high",
        "harm_bucket": "street_vendor_local_livelihood",
        "expected_route_any": ["street_vendor_municipal", "business_license_compliance"],
        "expected_act_hint": "Street Vendors Act 2014",
        "queries": [
            "municipality removed my tea cart from footpath without notice",
            "i have street vendor certificate but police took my cart",
            "nagar nigam seized my vending goods and asking fine",
        ],
        "oracle": {
            "required_groups": [
                {"name": "vendor_variant", "any": ["street vendor", "hawker", "vending", "cart"]},
                {"name": "tvc_forum", "any": ["town vending committee", "tvc", "municipal"]},
                {"name": "documents", "any": ["certificate", "seizure memo", "receipt", "notice"]},
                {"name": "remedy", "any": ["return of goods", "appeal", "hearing", "complaint"]},
            ],
            "forbidden_any": ["encroachment only no remedy"],
        },
    },
    {
        "id": "consumer_damaged_phone_return",
        "priority": "high",
        "harm_bucket": "other_user_quality",
        "expected_route_any": ["consumer"],
        "expected_act_hint": "Consumer Protection Act 2019 + e-Daakhil procedure",
        "queries": [
            "damaged phone company not accepting return what to do",
            "online order defective mobile seller refusing refund",
            "service center says warranty not valid for new damaged phone",
        ],
        "oracle": {
            "required_groups": [
                {"name": "consumer_variant", "any": ["consumer", "defective", "damaged", "refund", "replacement"]},
                {"name": "forum", "any": ["district commission", "e-daakhil", "consumer helpline"]},
                {"name": "documents", "any": ["invoice", "order id", "photos", "warranty"]},
                {"name": "first_step", "any": ["written complaint", "seller", "service provider", "grievance"]},
            ],
            "forbidden_any": ["police fir first"],
        },
    },
    {
        "id": "pan_aadhaar_mismatch",
        "priority": "high",
        "harm_bucket": "other_user_quality",
        "expected_route_any": ["social_welfare_identity", "tax_income_gst"],
        "expected_act_hint": "Aadhaar Act 2016 + Income Tax Act PAN-Aadhaar linking procedure",
        "queries": [
            "my pan and aadhaar is mismatch",
            "aadhaar name spelling different from pan income tax linking failed",
            "pan aadhaar dob mismatch portal not accepting what to do",
        ],
        "oracle": {
            "required_groups": [
                {"name": "identity_variant", "any": ["pan", "aadhaar", "aadhar", "mismatch"]},
                {"name": "correction_route", "any": ["uidai", "income tax", "nsdl", "utiitsl", "correction"]},
                {"name": "documents", "any": ["id proof", "date of birth", "name proof", "acknowledgement"]},
                {"name": "not_generic_welfare", "any": ["linking", "pan", "aadhaar"]},
            ],
            "forbidden_any": ["constitution article 341", "caste certificate"],
        },
    },
    {
        "id": "cyber_deepfake_porn",
        "priority": "critical",
        "harm_bucket": "cyber_sexual_privacy_high_risk",
        "expected_route_any": ["cyber_fraud_or_harassment", "police_fir"],
        "expected_act_hint": "Information Technology Act 2000 + BNS 2023 + Digital Personal Data Protection Act",
        "expected_act_keys": ["Information Technology Act"],
        "expected_primary_act_any": ["Information Technology Act 2000", "IT Act 2000", "IT Act"],
        "queries": [
            "ex boyfriend made ai deepfake porn of me uploaded online",
            "morphed nude photo of me circulating in telegram college group",
            "fake porn video with my face on website how to remove and complain",
        ],
        "oracle": {
            "required_groups": [
                {"name": "sexual_privacy_variant", "any": ["deepfake", "morphed", "nude", "porn", "intimate"]},
                {"name": "takedown_step", "any": ["takedown", "remove", "platform", "url", "report"]},
                {"name": "cyber_forum", "any": ["cyber cell", "police", "fir", "1930"]},
                {"name": "evidence", "any": ["screenshots", "urls", "preserve", "hash", "evidence"]},
            ],
            "forbidden_any": ["defamation only", "ignore it"],
        },
    },
    {
        "id": "ai_csam_college",
        "priority": "critical",
        "harm_bucket": "cyber_sexual_privacy_high_risk",
        "expected_route_any": ["cyber_fraud_or_harassment", "police_fir"],
        "expected_act_hint": "POCSO Act 2012 + Information Technology Act 2000 + BNS 2023",
        "queries": [
            "ai csam of my classmate someone made and shared in college telegram",
            "minor girl's morphed sexual image circulating in school whatsapp",
            "student made fake nude of 15 year old classmate what urgent action",
        ],
        "oracle": {
            "required_groups": [
                {"name": "minor_sexual_variant", "any": ["minor", "child", "classmate", "student", "csam", "pocso"]},
                {"name": "urgent_police", "any": ["police", "cyber cell", "fir", "childline", "1098"]},
                {"name": "takedown_evidence", "any": ["takedown", "url", "screenshots", "preserve"]},
                {"name": "safety", "any": ["do not forward", "do not share", "protect identity"]},
            ],
            "forbidden_any": ["handle privately only", "just ask them to delete"],
        },
    },
    {
        "id": "tribal_land_nontribal_sale",
        "priority": "critical",
        "harm_bucket": "caste_tribal_state_harm",
        "expected_route_any": ["tribal_caste_atrocity", "property_tenancy"],
        "expected_act_hint": "Scheduled Areas Land Transfer Regulation + PESA + Constitution Schedule V",
        "queries": [
            "tribal land sold to non tribal by uncle without our consent where to go",
            "munda land grabbed by upper caste in agency village chaibasa",
            "patwari changed mutation giving adivasi land to non tribal buyer",
        ],
        "oracle": {
            "required_groups": [
                {"name": "tribal_land_variant", "any": ["tribal", "adivasi", "scheduled area", "non tribal", "munda"]},
                {"name": "land_forum", "any": ["revenue", "collector", "deputy commissioner", "tribal welfare", "mutation"]},
                {"name": "state_law_caveat", "any": ["state", "scheduled area", "cnt", "spt", "local regulation"]},
                {"name": "documents", "any": ["record of rights", "mutation", "sale deed", "land records"]},
            ],
            "forbidden_any": ["ordinary sale is valid because uncle signed"],
        },
    },
    {
        "id": "witch_branding_tonhi",
        "priority": "critical",
        "harm_bucket": "caste_tribal_state_harm",
        "expected_route_any": ["tribal_caste_atrocity", "police_fir", "criminal_defence_bail"],
        "expected_act_hint": "Witch-Hunting State Acts + BNS 2023 + SC/ST POA Act where caste/tribal context applies",
        "queries": [
            "village people calling my mother daayan stripped her in public ranchi",
            "they say i am tonhi after child died false case chhattisgarh",
            "neighbours branding me witch want to throw me out of village",
        ],
        "oracle": {
            "required_groups": [
                {"name": "witch_variant", "any": ["witch", "daayan", "daain", "tonhi", "ojha"]},
                {"name": "criminal_safety", "any": ["police", "fir", "protection", "shelter"]},
                {"name": "state_law_caveat", "any": ["state law", "jharkhand", "chhattisgarh", "witch", "tonhi"]},
                {"name": "evidence", "any": ["witness", "photos", "medical", "videos", "names"]},
            ],
            "forbidden_any": ["superstition dispute only", "no law"],
        },
    },
    {
        "id": "caste_abuse_fir_refusal",
        "priority": "critical",
        "harm_bucket": "caste_tribal_state_harm",
        "expected_route_any": ["tribal_caste_atrocity", "police_fir"],
        "expected_act_hint": "SC/ST POA Act 1989 + BNS 2023 + BNSS 2023",
        "queries": [
            "upper caste people beat my husband called us chamar fir not registering",
            "teacher beat girl in school using caste name principal not acting",
            "mob attacked our pahan during sarna puja calling adivasi non hindu",
        ],
        "oracle": {
            "required_groups": [
                {"name": "caste_variant", "any": ["caste", "chamar", "adivasi", "sarna", "sc/st", "atrocity"]},
                {"name": "police_route", "any": ["fir", "police", "special court", "dysp", "sp"]},
                {"name": "protection_relief", "any": ["protection", "relief", "compensation", "district magistrate"]},
                {"name": "evidence", "any": ["witness", "medical", "video", "names"]},
            ],
            "forbidden_any": ["defamation notice first"],
        },
    },
    {
        "id": "wage_theft_fake_fir",
        "priority": "critical",
        "harm_bucket": "labour_welfare_survival",
        "expected_route_any": ["employment_wages", "criminal_defence_bail", "police_fir"],
        "expected_act_hint": "Code on Wages 2019 + BNSS 2023 + BNS 2023",
        "queries": [
            "thekedar made fake theft fir after i asked wages police calling",
            "contractor not paid wages now filed false mobile theft case",
            "labour chowk police picking us saying begging not work is this legal",
        ],
        "oracle": {
            "required_groups": [
                {"name": "dual_track_variant", "any": ["wages", "contractor", "thekedar", "labour", "false fir"]},
                {"name": "criminal_track", "any": ["bail", "lawyer", "police", "fir", "legal aid"]},
                {"name": "labour_track", "any": ["labour commissioner", "wage authority", "code on wages", "payment"]},
                {"name": "documents", "any": ["attendance", "messages", "wage", "muster", "id proof"]},
            ],
            "forbidden_any": ["only wage complaint no need to handle fir"],
        },
    },
    {
        "id": "asha_incentive_unpaid",
        "priority": "high",
        "harm_bucket": "labour_welfare_survival",
        "expected_route_any": ["labour_exploitation_discrimination", "employment_wages", "social_welfare_identity"],
        "expected_act_hint": "NHM/ASHA incentive guidelines + Legal Services Authorities Act",
        "expected_act_keys": ["ASHA Incentives"],
        "expected_primary_act_any": ["National Health Mission ASHA", "NHM ASHA", "ASHA Incentives"],
        "queries": [
            "asha worker incentive not paid for 8 months block office ignoring",
            "health department not paying covid duty incentive to asha",
            "asha facilitator says payment file pending for 6 months where to complain",
        ],
        "oracle": {
            "required_groups": [
                {"name": "scheme_worker_variant", "any": ["asha", "incentive", "honorarium"]},
                {"name": "department_forum", "any": ["block", "district", "health department", "mission", "phc"]},
                {"name": "documents", "any": ["attendance", "work records", "bank statement", "sanction"]},
                {"name": "escalation", "any": ["written complaint", "grievance", "dlsa", "rti"]},
            ],
            "forbidden_any": ["epfo first"],
        },
    },
    {
        "id": "anganwadi_honorarium_pending",
        "priority": "high",
        "harm_bucket": "labour_welfare_survival",
        "expected_route_any": ["labour_exploitation_discrimination", "social_welfare_identity"],
        "expected_act_hint": "Anganwadi/ICDS honorarium state order or case law + Legal Services Authorities Act",
        "expected_act_keys": ["Anganwadi Honorarium"],
        "expected_primary_act_any": ["Anganwadi", "ICDS", "Ameerbi", "Maniben"],
        "queries": [
            "anganwadi helper honorarium pending how to complain",
            "anganwadi worker not paid 5 months cdpo ignoring",
            "icds worker payment pending district programme officer not replying",
        ],
        "oracle": {
            "required_groups": [
                {"name": "scheme_worker_variant", "any": ["anganwadi", "icds", "honorarium"]},
                {"name": "department_forum", "any": ["cdpo", "district programme officer", "women and child", "wcd"]},
                {"name": "documents", "any": ["attendance", "work records", "bank statement", "appointment"]},
                {"name": "escalation", "any": ["written complaint", "grievance", "dlsa", "rti"]},
            ],
            "forbidden_any": ["epfo first", "national health mission asha incentives"],
        },
    },
    {
        "id": "epf_not_deposited",
        "priority": "high",
        "harm_bucket": "labour_welfare_survival",
        "expected_route_any": ["employment_wages"],
        "expected_act_hint": "EPF Act 1952 + Code on Social Security 2020",
        "queries": [
            "company deducted pf from salary but not depositing epf",
            "uan passbook shows no pf contribution employer ignoring",
            "employer closed company without paying gratuity and pf",
        ],
        "oracle": {
            "required_groups": [
                {"name": "epf_variant", "any": ["epf", "pf", "uan", "provident fund", "gratuity"]},
                {"name": "forum", "any": ["epfo", "labour commissioner", "grievance portal"]},
                {"name": "documents", "any": ["salary slips", "bank statement", "uan", "appointment"]},
                {"name": "written_demand", "any": ["written complaint", "demand", "grievance"]},
            ],
            "forbidden_any": ["consumer court first"],
        },
    },
    {
        "id": "mgnrega_fake_muster",
        "priority": "high",
        "harm_bucket": "labour_welfare_survival",
        "expected_route_any": ["social_welfare_identity", "employment_wages"],
        "expected_act_hint": "MGNREGA + social audit/grievance procedure",
        "queries": [
            "nrega muster shows i worked but money taken by mate",
            "mgnrega job card work done wages not credited panchayat ignoring",
            "fake attendance in job card and no payment where complain",
        ],
        "oracle": {
            "required_groups": [
                {"name": "mgnrega_variant", "any": ["mgnrega", "nrega", "job card", "muster"]},
                {"name": "forum", "any": ["programme officer", "gram panchayat", "social audit", "ombudsman"]},
                {"name": "documents", "any": ["job card", "muster", "bank", "work demand"]},
                {"name": "grievance", "any": ["written complaint", "grievance", "rti", "social audit"]},
            ],
            "forbidden_any": ["civil suit first"],
        },
    },
]


def main() -> int:
    args = parse_args()
    rows = build_rows(limit=args.limit, seed=args.seed)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
    print(f"wrote {len(rows)} substance-oracle prompts to {args.out}")
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=Path("/tmp/law_rag_substance_oracle/prompts/substance_oracle.jsonl"))
    parser.add_argument("--limit", type=int, default=180)
    parser.add_argument("--seed", type=int, default=2026060501)
    return parser.parse_args()


def build_rows(*, limit: int, seed: int) -> list[dict[str, Any]]:
    rng = random.Random(seed)
    candidates: list[dict[str, Any]] = []
    for scenario in SCENARIOS:
        for variant_index, query in enumerate(scenario["queries"]):
            for style_index, styled in enumerate(styled_queries(query)):
                candidates.append(make_row(scenario, styled, variant_index=variant_index, style_index=style_index))
    rng.shuffle(candidates)

    selected: list[dict[str, Any]] = []
    seen_queries: set[str] = set()
    per_scenario: dict[str, int] = {}
    # First pass keeps breadth: at most four rows per scenario.
    for row in candidates:
        sid = str(row["oracle_id"])
        if per_scenario.get(sid, 0) >= 4:
            continue
        key = normalize_query(row["query"])
        if key in seen_queries:
            continue
        selected.append(row)
        seen_queries.add(key)
        per_scenario[sid] = per_scenario.get(sid, 0) + 1
        if len(selected) >= limit:
            return selected
    # Second pass fills a larger requested set with extra paraphrase wrappers.
    for row in candidates:
        key = normalize_query(row["query"])
        if key in seen_queries:
            continue
        selected.append(row)
        seen_queries.add(key)
        if len(selected) >= limit:
            break
    return selected


def styled_queries(query: str) -> list[str]:
    out: list[str] = []
    for prefix, suffix in zip(STYLE_PREFIXES, STYLE_SUFFIXES, strict=True):
        text = f"{prefix}{query}{suffix}".strip()
        out.append(" ".join(text.split()))
    return out


def make_row(scenario: Scenario, query: str, *, variant_index: int, style_index: int) -> dict[str, Any]:
    oracle = scenario["oracle"]
    row = {
        "id": f"{scenario['id']}__v{variant_index + 1}__s{style_index + 1}",
        "query": query,
        "persona": "substance_oracle",
        "expected_category": scenario["expected_route_any"][0],
        "common_issue": scenario["id"],
        "expected_route_any": scenario["expected_route_any"],
        "expected_act_hint": scenario["expected_act_hint"],
        "expected_act_keys": scenario.get("expected_act_keys") or [],
        "expected_primary_act_any": scenario.get("expected_primary_act_any") or primary_act_candidates(scenario["expected_act_hint"]),
        "product_priority": scenario["priority"],
        "oracle_priority": scenario["priority"],
        "oracle_id": scenario["id"],
        "oracle_harm_bucket": scenario["harm_bucket"],
        "must_include_any": [
            term
            for group in oracle.get("required_groups", [])
            for term in group.get("any", [])[:2]
        ][:8],
        "oracle": oracle,
    }
    return row


def primary_act_candidates(hint: str) -> list[str]:
    """Return controlling-authority candidates without forcing secondary laws."""
    first_clause = re.split(r"\s+\+\s+", hint, maxsplit=1)[0].strip()
    first_clause = first_clause.replace("SC/ST", "SCST").replace("sc/st", "scst")
    candidates = [
        part.strip().replace("SCST", "SC/ST").replace("scst", "sc/st")
        for part in re.split(r"\s*/\s*|\s+\bor\b\s+", first_clause)
        if part.strip()
    ]
    return candidates or [hint]


def normalize_query(query: str) -> str:
    return " ".join(query.lower().split())


if __name__ == "__main__":
    raise SystemExit(main())
