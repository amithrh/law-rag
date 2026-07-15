from __future__ import annotations

from apps.api.source_gap import build_source_gap_event, missing_required_authorities, should_enforce_required_source
from apps.api.common_workflow_contracts import WorkflowTemplateResult
from apps.api.main import _critical_route_needs_reviewed_contract, _source_gap_event_for_retrieved
from apps.api.matter_router import MatterRoute, route_matter


def test_source_gap_detects_missing_route_authority():
    missing = missing_required_authorities(
        required_sources=["CGST Act 2017 Section 67 inspection/search/seizure source"],
        passages=[
            {
                "index": 1,
                "title": "Consumer Protection Act 2019",
                "anchor": "consumer-protection-2019/sec-35",
                "source_type": "bare_act",
            }
        ],
        query="gst officer searched my shop without order",
    )

    assert missing == [
        {
            "required_source": "CGST Act 2017 Section 67 inspection/search/seizure source",
            "kind": "national_tax_source_gap",
        }
    ]


def test_source_gap_does_not_fire_when_matching_source_present():
    missing = missing_required_authorities(
        required_sources=["CGST Act 2017 Section 67 inspection/search/seizure source"],
        passages=[
            {
                "index": 1,
                "title": "Central Goods and Services Tax Act 2017",
                "anchor": "cgst-2017/sec-67",
                "source_type": "bare_act",
            }
        ],
        query="gst officer searched my shop without order",
    )

    assert missing == []


def test_customs_source_gap_matching_is_query_aware():
    required = "Customs Act 1962 for import/export, ICEGATE, duty, valuation, SVB, drawback, or classification issues"

    icegate_query = "icegate showing bill of entry on hold misdeclaration alleged chinese led lights"
    assert missing_required_authorities(
        required_sources=[required],
        passages=[{"index": 1, "title": "Customs Act 1962", "anchor": "customs-1962/sec-75", "source_type": "bare_act"}],
        query=icegate_query,
    )
    assert missing_required_authorities(
        required_sources=[required],
        passages=[{"index": 1, "title": "Customs Act 1962", "anchor": "customs-1962/sec-124", "source_type": "bare_act"}],
        query=icegate_query,
    ) == []

    drawback_query = "drawback claim rejected by customs shipping bill mismatched export incentive"
    assert missing_required_authorities(
        required_sources=[required],
        passages=[{"index": 1, "title": "Customs Act 1962", "anchor": "customs-1962/sec-124", "source_type": "bare_act"}],
        query=drawback_query,
    )
    assert missing_required_authorities(
        required_sources=[required],
        passages=[{"index": 1, "title": "Customs Act 1962", "anchor": "customs-1962/sec-75", "source_type": "bare_act"}],
        query=drawback_query,
    ) == []

    svb_query = "customs reclassified my import wire harness higher duty svb opened mumbai"
    assert missing_required_authorities(
        required_sources=[required],
        passages=[{"index": 1, "title": "Customs Act 1962", "anchor": "customs-1962/sec-75", "source_type": "bare_act"}],
        query=svb_query,
    )
    assert missing_required_authorities(
        required_sources=[required],
        passages=[{"index": 1, "title": "Customs Act 1962", "anchor": "customs-1962/sec-14", "source_type": "bare_act"}],
        query=svb_query,
    ) == []

    plain_classification_query = "customs reclassified imported scanner under wrong tariff heading higher duty"
    assert missing_required_authorities(
        required_sources=[required],
        passages=[{"index": 1, "title": "Customs Act 1962", "anchor": "customs-1962/sec-14", "source_type": "bare_act"}],
        query=plain_classification_query,
    )
    assert missing_required_authorities(
        required_sources=[required],
        passages=[{"index": 1, "title": "Customs Act 1962", "anchor": "customs-1962/sec-17", "source_type": "bare_act"}],
        query=plain_classification_query,
    ) == []

    no_svb_query = "customs reclassified imported wire harness higher duty no svb opened"
    assert missing_required_authorities(
        required_sources=[required],
        passages=[{"index": 1, "title": "Customs Act 1962", "anchor": "customs-1962/sec-14", "source_type": "bare_act"}],
        query=no_svb_query,
    )

    svb_not_related_query = "svb opened but we are not related party declared value rejected by customs"
    assert missing_required_authorities(
        required_sources=[required],
        passages=[{"index": 1, "title": "Customs Act 1962", "anchor": "customs-1962/sec-14", "source_type": "bare_act"}],
        query=svb_not_related_query,
    ) == []


def test_manual_scavenging_death_dual_regime_sources_satisfy_gap_policy():
    query = "village man dies cleaning septic tank no safety equipment company not agreeing compensation"
    route = route_matter(query)

    event = build_source_gap_event(
        query=query,
        route_category=route.category,
        required_sources=route.required_sources,
        passages=[
            {
                "index": 1,
                "title": "Prohibition of Employment as Manual Scavengers and their Rehabilitation Act 2013",
                "anchor": "manual-scavenging-2013/sec-7",
                "source_type": "bare_act",
            },
            {
                "index": 2,
                "title": "Employees' Compensation Act 1923",
                "anchor": "employees-compensation-1923/sec-3",
                "source_type": "bare_act",
            },
            {
                "index": 3,
                "title": "Bharatiya Nyaya Sanhita 2023",
                "anchor": "bns-2023/sec-106",
                "source_type": "bare_act",
            },
            {
                "index": 4,
                "title": "Bharatiya Nagarik Suraksha Sanhita 2023",
                "anchor": "bnss-2023/sec-173",
                "source_type": "bare_act",
            },
            {
                "index": 5,
                "title": "Code of Criminal Procedure 1973",
                "anchor": "crpc-1973/sec-154",
                "source_type": "bare_act",
            },
        ],
    )

    assert event is None


def test_source_gap_accepts_broad_gift_deed_and_free_consent_authorities():
    passages = [
        {
            "index": 1,
            "title": "Transfer of Property Act 1882",
            "anchor": "transfer-of-property-1882/sec-122",
            "source_type": "bare_act",
        },
        {
            "index": 2,
            "title": "Registration Act 1908",
            "anchor": "registration-1908/sec-49",
            "source_type": "bare_act",
        },
        {
            "index": 3,
            "title": "Specific Relief Act 1963",
            "anchor": "specific-relief-1963/sec-31",
            "source_type": "bare_act",
        },
        {
            "index": 4,
            "title": "Indian Contract Act 1872",
            "anchor": "indian-contract-1872/sec-19-a",
            "source_type": "bare_act",
        },
        {
            "index": 5,
            "title": "Bharatiya Nyaya Sanhita 2023",
            "anchor": "bns-2023/sec-336",
            "source_type": "bare_act",
        },
        {
            "index": 6,
            "title": "Bharatiya Nagarik Suraksha Sanhita 2023",
            "anchor": "bnss-2023/sec-173-a",
            "source_type": "bare_act",
        },
        {
            "index": 7,
            "title": "Code of Criminal Procedure 1973",
            "anchor": "crpc-1973/sec-200",
            "source_type": "bare_act",
        },
    ]

    missing = missing_required_authorities(
        required_sources=[
            "Transfer of Property Act 1882 where gift or property-transfer cancellation is involved",
            "Indian Contract Act 1872 where consent, coercion, undue influence, or authority is disputed",
            "Registration Act / civil court procedure where document validity is disputed",
            "Specific Relief Act 1963 where cancellation/declaration/injunction is needed",
            "BNS 2023 / IPC 1860 cheating, forgery, or false-document provisions based on incident date",
            "BNSS 2023 / CrPC 1973 complaint and investigation procedure based on incident date",
        ],
        passages=passages,
        query="mother thumb impression blank paper produced as gift deed",
    )

    assert missing == []


def test_source_gap_skips_untriggered_conditional_authorities():
    missing = missing_required_authorities(
        required_sources=[
            "Maternity Benefit Act / EPF Act only where maternity or PF/EPF facts are involved",
            "court rules and practice directions for the relevant court",
            "BNSS 2023 / CrPC 1973 only if the case-status issue is in a criminal case",
            "Constitution of India Article 32 for Supreme Court fundamental-right enforcement where applicable",
            "Legal Services Authorities Act 1987 where help is needed",
            "BOCW Act 1996 / Factories Act 1948 where applicable",
        ],
        passages=[],
        query="civil suit court fee 25 lakh recovery fixed or ad valorem",
    )

    assert missing == []


def test_source_gap_enforces_triggered_conditional_labour_and_legal_aid_authorities():
    missing = missing_required_authorities(
        required_sources=[
            "Code on Wages only if salary, full-and-final, leave encashment, or wage dues are withheld",
            "Legal Services Authorities Act 1987 where help is needed",
        ],
        passages=[],
        query="salary deducted and I cannot afford lawyer need DLSA legal aid",
    )

    assert missing == [
        {
            "required_source": "Code on Wages only if salary, full-and-final, leave encashment, or wage dues are withheld",
            "kind": "national_statute_retrieval_gap",
        },
        {
            "required_source": "Legal Services Authorities Act 1987 where help is needed",
            "kind": "national_statute_retrieval_gap",
        },
    ]


def test_source_gap_does_not_trigger_family_personal_law_for_spouse_violence_only():
    missing = missing_required_authorities(
        required_sources=[
            "family law statute by religion",
            "BNSS/CrPC maintenance provisions where applicable",
        ],
        passages=[],
        query="my husband is slapping me and his parents threw me out",
    )

    assert missing == []


def test_source_gap_triggers_family_and_maintenance_only_on_matching_relief():
    family_missing = missing_required_authorities(
        required_sources=["family law statute by religion"],
        passages=[],
        query="my husband lied before marriage about job can I annul marriage",
    )
    maintenance_missing = missing_required_authorities(
        required_sources=["BNSS/CrPC maintenance provisions where applicable"],
        passages=[],
        query="wife and child maintenance case husband not paying monthly support",
    )

    assert family_missing == [
        {
            "required_source": "family law statute by religion",
            "kind": "national_statute_retrieval_gap",
        }
    ]
    assert maintenance_missing == [
        {
            "required_source": "BNSS/CrPC maintenance provisions where applicable",
            "kind": "national_criminal_source_gap",
        }
    ]


def test_source_gap_treats_conditional_criminal_regime_as_authority():
    missing = missing_required_authorities(
        required_sources=[
            "BNSS 2023 / CrPC 1973 bail provisions based on incident date",
            "BNS 2023 / IPC 1860 offence provisions where relevant",
        ],
        passages=[],
        query="brother arrested six months no chargesheet can bail be filed",
    )

    assert missing == [
        {
            "required_source": "BNSS 2023 / CrPC 1973 bail provisions based on incident date",
            "kind": "national_criminal_source_gap",
        },
    ]


def test_source_gap_requires_matching_criminal_procedure_section_family():
    wrong_section = missing_required_authorities(
        required_sources=["BNSS 2023 / CrPC 1973 bail provisions based on incident date"],
        passages=[
            {
                "index": 1,
                "title": "Bharatiya Nagarik Suraksha Sanhita 2023",
                "anchor": "bnss-2023/sec-173",
                "source_type": "bare_act",
            }
        ],
        query="brother arrested six months no chargesheet can bail be filed",
    )
    covered_by_both_regimes = missing_required_authorities(
        required_sources=["BNSS 2023 / CrPC 1973 bail provisions based on incident date"],
        passages=[
            {
                "index": 1,
                "title": "Bharatiya Nagarik Suraksha Sanhita 2023",
                "anchor": "bnss-2023/sec-480",
                "source_type": "bare_act",
            },
            {
                "index": 2,
                "title": "Code of Criminal Procedure 1973",
                "anchor": "crpc-1973/sec-439",
                "source_type": "bare_act",
            },
        ],
        query="brother arrested six months no chargesheet can bail be filed",
    )

    assert wrong_section[0]["required_source"] == "BNSS 2023 / CrPC 1973 bail provisions based on incident date"
    assert covered_by_both_regimes == []


def test_source_gap_accepts_coherent_bns_bnss_or_ipc_crpc_pair():
    required = ["BNS/BNSS or IPC/CrPC based on incident date"]
    current_sources = [
        {
            "index": 1,
            "title": "Bharatiya Nyaya Sanhita 2023",
            "anchor": "bns-2023/sec-318",
            "source_type": "bare_act",
        },
        {
            "index": 2,
            "title": "Bharatiya Nagarik Suraksha Sanhita 2023",
            "anchor": "bnss-2023/sec-173",
            "source_type": "bare_act",
        },
    ]
    old_sources = [
        {
            "index": 1,
            "title": "Indian Penal Code 1860",
            "anchor": "ipc-1860/sec-420",
            "source_type": "bare_act",
        },
        {
            "index": 2,
            "title": "Code of Criminal Procedure 1973",
            "anchor": "crpc-1973/sec-154",
            "source_type": "bare_act",
        },
    ]

    assert missing_required_authorities(
        required_sources=required,
        passages=current_sources,
        query="got 8 lakh phonepe fraud police not filing fir",
    ) == []
    assert missing_required_authorities(
        required_sources=required,
        passages=old_sources,
        query="incident in 2023 phonepe fraud police not filing fir",
    ) == []
    assert missing_required_authorities(
        required_sources=required,
        passages=current_sources,
        query="incident in 2023 phonepe fraud police not filing fir",
    ) == [
        {
            "required_source": "BNS/BNSS or IPC/CrPC based on incident date",
            "kind": "national_criminal_source_gap",
        }
    ]


def test_source_gap_rejects_partial_bns_bnss_or_ipc_crpc_pair():
    missing = missing_required_authorities(
        required_sources=["BNS/BNSS or IPC/CrPC based on incident date"],
        passages=[
            {
                "index": 1,
                "title": "Bharatiya Nyaya Sanhita 2023",
                "anchor": "bns-2023/sec-318",
                "source_type": "bare_act",
            }
        ],
        query="got 8 lakh phonepe fraud police not filing fir",
    )

    assert missing[0]["required_source"] == "BNS/BNSS or IPC/CrPC based on incident date"


def test_source_gap_does_not_treat_bnss_as_bns_or_new_law_as_old_regime():
    required = ["BNS/BNSS or IPC/CrPC based on incident date"]

    only_bnss = missing_required_authorities(
        required_sources=required,
        passages=[
            {
                "index": 1,
                "title": "Bharatiya Nagarik Suraksha Sanhita 2023",
                "anchor": "bnss-2023/sec-173",
                "source_type": "bare_act",
            }
        ],
        query="phonepe fraud police not filing fir",
    )
    old_fact_with_new_sources = missing_required_authorities(
        required_sources=required,
        passages=[
            {
                "index": 1,
                "title": "Bharatiya Nyaya Sanhita 2023",
                "anchor": "bns-2023/sec-318",
                "source_type": "bare_act",
            },
            {
                "index": 2,
                "title": "Bharatiya Nagarik Suraksha Sanhita 2023",
                "anchor": "bnss-2023/sec-173",
                "source_type": "bare_act",
            },
        ],
        query="incident in 2022 phonepe fraud police not filing fir",
    )

    assert only_bnss[0]["required_source"] == required[0]
    assert old_fact_with_new_sources[0]["required_source"] == required[0]


def test_source_gap_enforces_single_regime_crpc_conditional_source():
    missing = missing_required_authorities(
        required_sources=["CrPC 1973 section 160 witness attendance safeguards where applicable"],
        passages=[],
        query="police gave section 160 notice asking woman to come station as witness",
    )

    assert missing == [
        {
            "required_source": "CrPC 1973 section 160 witness attendance safeguards where applicable",
            "kind": "national_criminal_source_gap",
        }
    ]


def test_source_gap_does_not_accept_delhi_prison_rules_for_non_delhi_prison():
    missing = missing_required_authorities(
        required_sources=["state prison rules / prison manual for interviews, visits, and permitted books"],
        passages=[
            {
                "index": 1,
                "title": "Delhi Prison Rules 2018",
                "anchor": "delhi-prison-rules-2018/rule-613-616",
                "source_type": "bare_act",
            }
        ],
        query="pune yerwada jail mulaqat denied wife wants to meet husband",
    )

    assert missing


def test_source_gap_requires_pmla_sc_precedent_when_route_names_precedents():
    required = ["Supreme Court PMLA bail/arrest precedents"]
    statute_only = missing_required_authorities(
        required_sources=required,
        passages=[
            {
                "index": 1,
                "title": "Prevention of Money Laundering Act 2002",
                "anchor": "pmla-2002/sec-45",
                "source_type": "bare_act",
            }
        ],
        query="pmla twin condition bail how to argue not guilty",
    )
    precedent_present = missing_required_authorities(
        required_sources=required,
        passages=[
            {
                "index": 2,
                "title": "VIJAY MADANLAL CHOUDHARY versus UNION OF INDIA PMLA",
                "anchor": "2022-insc-757#para-401",
                "source_type": "sc_judgment",
            }
        ],
        query="pmla twin condition bail how to argue not guilty",
    )

    assert statute_only
    assert precedent_present == []


def test_source_gap_requires_both_pesa_fra_and_80c_80ccd_when_named_together():
    pesa_fra_missing = missing_required_authorities(
        required_sources=["PESA Act / Forest Rights Act where Gram Sabha or forest-rights facts apply"],
        passages=[
            {
                "index": 1,
                "title": "Scheduled Tribes and Other Traditional Forest Dwellers (Recognition of Forest Rights) Act 2006",
                "anchor": "fra-2006/sec-5",
                "source_type": "bare_act",
            }
        ],
        query="gond woman forest officer not giving IFR title dindori gram sabha",
    )
    income_missing = missing_required_authorities(
        required_sources=["Income Tax Act 1961 sections 80C and 80CCD deduction sources"],
        passages=[
            {
                "index": 1,
                "title": "Income-tax Act 1961",
                "anchor": "income-tax-1961/sec-80C",
                "source_type": "bare_act",
            }
        ],
        query="can i claim 80c and 80ccd nps together",
    )

    assert pesa_fra_missing
    assert income_missing


def test_source_gap_accepts_stage3_named_statute_sources():
    assert missing_required_authorities(
        required_sources=["Arms Act 1959 definition/licensing/penalty source for alleged weapon or farming tool"],
        passages=[
            {
                "index": 1,
                "title": "Arms Act 1959",
                "anchor": "arms-1959/sec-2",
                "source_type": "bare_act",
            }
        ],
        query="police put arms act because axe was in farm jeep",
    ) == []

    assert missing_required_authorities(
        required_sources=["Maharashtra Control of Organised Crime Act 1999 Section 21 extension rules where MCOCA is alleged"],
        passages=[
            {
                "index": 1,
                "title": "Maharashtra Control of Organised Crime Act 1999",
                "anchor": "maharashtra-control-organised-crime-1999/sec-21",
                "source_type": "bare_act",
            }
        ],
        query="mcoca case 100 days no chargesheet default bail",
    ) == []


def test_source_gap_accepts_hyphenated_income_tax_pan_requirement():
    assert missing_required_authorities(
        required_sources=[
            "Income-tax Act / PAN procedure where PAN record or PAN-Aadhaar linking is involved",
            "Aadhaar Act 2016 where Aadhaar authentication or demographic data is involved",
        ],
        passages=[
            {
                "index": 1,
                "title": "Income-tax Act 1961",
                "anchor": "income-tax-1961/sec-139-i",
                "source_type": "bare_act",
            },
            {
                "index": 2,
                "title": "Aadhaar (Targeted Delivery of Financial and Other Subsidies, Benefits and Services) Act 2016",
                "anchor": "aadhaar-2016/sec-8-a",
                "source_type": "bare_act",
            },
        ],
        query="my pan and aadhar is mismatch",
    ) == []


def test_source_gap_recognizes_common_runtime_route_authorities():
    cases = [
        (
            "Motor Vehicles Act 1988 aggregator licensing provisions",
            "uber driver account deactivated rating low mumbai aggregator",
            {
                "title": "Motor Vehicle Aggregator Guidelines 2020",
                "anchor": "motor-vehicle-aggregator-guidelines-2020#app-transparency-grievance",
                "source_type": "guideline",
            },
        ),
        (
            "Guardians and Wards Act / family law custody principles",
            "father took child abroad custody",
            {
                "title": "Guardians and Wards Act 1890",
                "anchor": "guardians-wards-1890/sec-25",
                "source_type": "bare_act",
            },
        ),
        (
            "state Shops and Establishments Act / rules",
            "shop act jaipur registration staff",
            {
                "title": "Rajasthan Shops and Commercial Establishments Act 1958",
                "anchor": "rajasthan-shops-establishments-1958/sec-4",
                "source_type": "bare_act",
            },
        ),
        (
            "National Food Security Act 2013 for TPDS/ration entitlement and grievance redressal",
            "ration biometric fail not getting quota",
            {
                "title": "National Food Security Act 2013",
                "anchor": "national-food-security-2013/sec-12",
                "source_type": "bare_act",
            },
        ),
        (
            "Protection of Civil Rights Act 1955 for temple, well/water, and public-access disabilities",
            "dalit stopped from entering temple",
            {
                "title": "Protection of Civil Rights Act 1955",
                "anchor": "protection-civil-rights-1955/sec-3",
                "source_type": "bare_act",
            },
        ),
        (
            "Customs Act 1962 for import/export, ICEGATE, duty, valuation, SVB, drawback, or classification issues",
            "customs drawback claim rejected shipping bill mismatch",
            {
                "title": "Customs Act 1962",
                "anchor": "customs-1962/sec-75",
                "source_type": "bare_act",
            },
        ),
        (
            "Customs Act 1962 for import/export, ICEGATE, duty, valuation, SVB, drawback, or classification issues",
            "icegate bill of entry hold misdeclaration chinese led lights",
            {
                "title": "Customs Act 1962",
                "anchor": "customs-1962/sec-124",
                "source_type": "bare_act",
            },
        ),
        (
            "Customs Act 1962 for import/export, ICEGATE, duty, valuation, SVB, drawback, or classification issues",
            "customs reclassified wire harness higher duty svb valuation",
            {
                "title": "Customs Act 1962",
                "anchor": "customs-1962/sec-14",
                "source_type": "bare_act",
            },
        ),
        (
            "Banking Regulation Act 1949 and RBI grievance route for the bank-service dispute",
            "bank loan against my house without signature",
            {
                "title": "Reserve Bank Integrated Ombudsman Scheme 2021",
                "anchor": "rbi-integrated-ombudsman-2021/sec-2",
                "source_type": "bare_act",
            },
        ),
        (
            "RBI Integrated Ombudsman Scheme for regulated-entity complaint route",
            "bank deducted money wrongly and customer care not helping",
            {
                "title": "Reserve Bank Integrated Ombudsman Scheme 2021",
                "anchor": "rbi-integrated-ombudsman-2021/sec-2",
                "source_type": "bare_act",
            },
        ),
        (
            "Clinical Establishments Act / state clinical-establishment rules where hospital records, billing, or standards are involved",
            "private hospital overcharged icu bill",
            {
                "title": "Clinical Establishments (Registration and Regulation) Act 2010",
                "anchor": "clinical-establishments-2010/sec-12",
                "source_type": "bare_act",
            },
        ),
        (
            "National Green Tribunal Act 2010 for environmental relief/compensation route",
            "factory pollution nearby file PIL high court",
            {
                "title": "National Green Tribunal Act 2010",
                "anchor": "ngt-2010/sec-16",
                "source_type": "bare_act",
            },
        ),
        (
            "Companies Act 2013 annual filing, director disqualification, and restoration provisions",
            "aoc 4 not filed director disqualified revive company",
            {
                "title": "Companies Act 2013",
                "anchor": "companies-2013/sec-164",
                "source_type": "bare_act",
            },
        ),
        (
            "RFCTLARR Act 2013 compensation award, payment/deposit, and reference-to-Authority provisions",
            "highway land compensation not paid",
            {
                "title": "Right to Fair Compensation and Transparency in Land Acquisition, Rehabilitation and Resettlement Act 2013",
                "anchor": "rfctlarr-2013/sec-77-a",
                "source_type": "bare_act",
            },
        ),
        (
            "Real Estate (Regulation and Development) Act 2016 for project registration, possession delay, promoter obligations, and RERA complaint",
            "builder flat carpet area less than agreement rera complaint",
            {
                "title": "Real Estate (Regulation and Development) Act 2016",
                "anchor": "rera-2016/sec-14-c",
                "source_type": "bare_act",
            },
        ),
        (
            "Aadhaar Act 2016 where Aadhaar authentication or identity information is misused",
            "got message saying my aadhaar issued 4 sims i never took how to check",
            {
                "title": "Aadhaar (Targeted Delivery of Financial and Other Subsidies, Benefits and Services) Act 2016",
                "anchor": "aadhaar-2016/sec-29",
                "source_type": "bare_act",
            },
        ),
        (
            "Specific Relief Act 1963 where injunction/performance is sought",
            "signed mou with dealer he is selling to competitor exclusivity clause",
            {
                "title": "Specific Relief Act 1963",
                "anchor": "specific-relief-1963/sec-42",
                "source_type": "bare_act",
            },
        ),
        (
            "Drugs and Cosmetics Act 1940 inspection, sampling, and sale-compliance provisions",
            "drug inspector picked up samples from my medical store schedule h sale without prescription jaipur",
            {
                "title": "Drugs and Cosmetics Act 1940",
                "anchor": "drugs-cosmetics-1940/sec-22-act",
                "source_type": "bare_act",
            },
        ),
        (
            "Employees Compensation Act 1923 occupational-disease and claim provisions",
            "stone quarry silicosis lungs damaged compensation rajasthan",
            {
                "title": "Employees' Compensation Act 1923",
                "anchor": "employees-compensation-1923/sec-3-a@1961-01-01",
                "source_type": "bare_act",
            },
        ),
        (
            "Trade Marks Act 1999 infringement, passing-off, and forum/remedy provisions",
            "amazon seller using my registered brand on fake items",
            {
                "title": "Trade Marks Act 1999",
                "anchor": "trade-marks-1999/sec-134",
                "source_type": "bare_act",
            },
        ),
        (
            "Income Tax Act 1961 for TDS, return, assessment, and appeal issues",
            "appeal before ITAT against CIT Appeals order time limit",
            {
                "title": "Income-tax Act 1961",
                "anchor": "income-tax-1961/sec-253-a",
                "source_type": "bare_act",
            },
        ),
        (
            "Income Tax Act 1961 for Indian taxability of creator/freelance income",
            "fanvue payment frozen 2400 usd indian creator how to release fund",
            {
                "title": "Income-tax Act 1961",
                "anchor": "income-tax-1961/sec-5",
                "source_type": "bare_act",
            },
        ),
        (
            "RBI/KYC or online-gaming rules where financial account facts apply",
            "bank says KYC pending so account is on hold",
            {
                "title": "Reserve Bank Integrated Ombudsman Scheme 2021",
                "anchor": "rbi-integrated-ombudsman-2021/sec-2",
                "source_type": "bare_act",
            },
        ),
        (
            "Mines and Minerals (Development and Regulation) Act 1957 mining lease and mineral-concession approval record",
            "mining company doing blasting next to village no gram sabha consent",
            {
                "title": "Mines and Minerals (Development and Regulation) Act 1957",
                "anchor": "mmdr-1957/sec-4",
                "source_type": "bare_act",
            },
        ),
        (
            "Mediation Act 2023 / rules where notified procedure applies",
            "urgent is pre-litigation mediation mandatory before filing commercial suit",
            {
                "title": "Mediation Act 2023",
                "anchor": "mediation-2023/sec-5",
                "source_type": "bare_act",
            },
        ),
        (
            "constitutional reproductive autonomy and privacy precedents",
            "six months pregnant after rape doctor says abortion too late",
            {
                "title": "X versus THE PRINCIPAL SECRETARY HEALTH AND FAMILY WELFARE DEPARTMENT & ANR.",
                "anchor": "2022-insc-740#para-11",
                "source_type": "sc_judgment",
            },
        ),
    ]

    for required_source, query, passage in cases:
        assert missing_required_authorities(
            required_sources=[required_source],
            passages=[passage],
            query=query,
        ) == []


def test_source_gap_enforces_bank_service_deficiency_consumer_source():
    required_source = "Consumer Protection Act 2019 where bank service deficiency is alleged"
    query = "bank deducted money wrongly and customer care not helping"

    assert should_enforce_required_source(required_source, query=query) is True
    assert missing_required_authorities(
        required_sources=[required_source],
        passages=[
            {
                "title": "Consumer Protection Act 2019",
                "anchor": "consumer-protection-2019/sec-35",
                "source_type": "bare_act",
            }
        ],
        query=query,
    ) == []


def test_source_gap_does_not_enforce_bank_service_deficiency_source_for_non_bank_consumer_query():
    required_source = "Consumer Protection Act 2019 where bank service deficiency is alleged"

    assert should_enforce_required_source(
        required_source,
        query="phone arrived damaged and seller is refusing return",
    ) is False


def test_source_gap_cyber_old_regime_composite_requires_complaint_procedure_not_bail():
    from apps.api.source_gap import best_source_match

    required = "BNS/BNSS or IPC/CrPC based on incident date"
    query = "someone made deepfake video of me on instagram in June 2024 and is extorting me"
    passages = [
        {
            "index": 1,
            "title": "Indian Penal Code 1860",
            "anchor": "ipc-1860/sec-384",
            "source_type": "bare_act",
        },
        {
            "index": 2,
            "title": "Code of Criminal Procedure 1973",
            "anchor": "crpc-1973/sec-437-a",
            "source_type": "bare_act",
        },
    ]

    assert best_source_match(required, passages, query=query) is None

    passages.append({
        "index": 3,
        "title": "Code of Criminal Procedure 1973",
        "anchor": "crpc-1973/sec-200",
        "source_type": "bare_act",
    })

    matched = best_source_match(required, passages, query=query)

    assert matched is not None
    assert matched["source_type"] == "aggregate"
    assert "ipc-1860/sec-384" in matched["anchor"]
    assert "crpc-1973/sec-200" in matched["anchor"]

    numeric_pre_cutover_query = "someone made deepfake video of me before 01/07/2024 and is extorting me"
    current_regime_sources = [
        {
            "index": 1,
            "title": "Bharatiya Nyaya Sanhita 2023",
            "anchor": "bns-2023/sec-308-a",
            "source_type": "bare_act",
        },
        {
            "index": 2,
            "title": "Bharatiya Nagarik Suraksha Sanhita 2023",
            "anchor": "bnss-2023/sec-173-b",
            "source_type": "bare_act",
        },
    ]
    assert best_source_match(required, current_regime_sources, query=numeric_pre_cutover_query) is None
    assert best_source_match(required, passages, query=numeric_pre_cutover_query) is not None


def test_source_gap_cyber_negated_extortion_accepts_threat_sources():
    missing = missing_required_authorities(
        required_sources=["BNS/BNSS or IPC/CrPC based on incident date"],
        passages=[
            {
                "index": 1,
                "title": "Bharatiya Nyaya Sanhita 2023",
                "anchor": "bns-2023/sec-351",
                "source_type": "bare_act",
            },
            {
                "index": 2,
                "title": "Bharatiya Nagarik Suraksha Sanhita 2023",
                "anchor": "bnss-2023/sec-173",
                "source_type": "bare_act",
            },
        ],
        query="someone made deepfake video in 2025 no extortion just threatening to share it",
    )

    assert missing == []


def test_source_gap_cyber_notice_no_paper_accepts_bnss_notice_procedure():
    event = build_source_gap_event(
        required_sources=["BNS/BNSS or IPC/CrPC based on incident date"],
        passages=[
            {
                "index": 1,
                "title": "Bharatiya Nagarik Suraksha Sanhita 2023",
                "anchor": "bnss-2023/sec-35",
                "source_type": "bare_act",
            },
            {
                "index": 2,
                "title": "Information Technology Act 2000",
                "anchor": "it-act-2000/sec-66D",
                "source_type": "bare_act",
            },
        ],
        query="police calling me for notice in cyber case but not giving paper",
        route_category="cyber_fraud_or_harassment",
    )

    assert event is None


def test_source_gap_recognizes_copyright_composite_and_hyphenated_section_anchor():
    assert missing_required_authorities(
        required_sources=["Copyright Act 1957 infringement, exceptions/fair dealing, and civil remedies"],
        passages=[
            {
                "title": "Copyright Act 1957",
                "anchor": "copyright-1957/sec-51",
                "source_type": "bare_act",
            },
            {
                "title": "Copyright Act 1957",
                "anchor": "copyright-1957/sec-52-a",
                "source_type": "bare_act",
            },
            {
                "title": "Copyright Act 1957",
                "anchor": "copyright-1957/sec-55",
                "source_type": "bare_act",
            },
        ],
        query="spotify took down remix fair use copyright",
    ) == []

    assert missing_required_authorities(
        required_sources=["CrPC 1973 section 436A for legacy / transitional comparison"],
        passages=[
            {
                "title": "Code of Criminal Procedure 1973",
                "anchor": "crpc-1973/sec-436-a",
                "source_type": "bare_act",
            }
        ],
        query="undertrial 70 years old crpc 436a",
    ) == []


def test_source_gap_skips_medical_ethics_for_billing_only_but_requires_for_wrong_surgery():
    billing_only = missing_required_authorities(
        required_sources=[
            "Medical Council / medical ethics record and professional-conduct rules where records or negligence are disputed",
        ],
        passages=[],
        query="private hospital overcharged 4 lakh icu bill denying refund",
    )
    wrong_surgery = missing_required_authorities(
        required_sources=[
            "Medical Council / medical ethics record and professional-conduct rules where records or negligence are disputed",
        ],
        passages=[],
        query="hospital operated wrong leg on my father",
    )

    assert billing_only == []
    assert wrong_surgery[0]["required_source"].startswith("Medical Council")


def test_source_gap_skips_false_positive_route_labels_from_casual_police_or_marriage_words():
    assert missing_required_authorities(
        required_sources=["BNS/BNSS or IPC/CrPC only as a separate criminal-negligence track where facts support it"],
        passages=[],
        query="private hospital overcharged 4 lakh icu bill denying refund need lawyer or police",
    ) == []

    assert missing_required_authorities(
        required_sources=["family law statute by religion"],
        passages=[],
        query="he slaps me but says sorry next day my parents say all marriages are like this should I stay",
    ) == []

    assert missing_required_authorities(
        required_sources=["BNSS 2023 / CrPC 1973 only if the case-status issue is in a criminal case"],
        passages=[],
        query="how to file vakalatnama change of advocate during pending suit need lawyer or police",
    ) == []

    assert missing_required_authorities(
        required_sources=["BNSS 2023 / CrPC 1973 only if the case-status issue is in a criminal case"],
        passages=[],
        query="urgent summons not served through registered post what is next step",
    ) == []

    assert missing_required_authorities(
        required_sources=["labour/DLSA grievance route"],
        passages=[],
        query="wife delivered baby at construction site hut no esi contractor says not his problem",
    ) == []

    assert missing_required_authorities(
        required_sources=["victim-compensation and DLSA procedure for urgent treatment/support"],
        passages=[],
        query="mother in law is threatening to throw acid if I do not bring money",
    ) == []


def test_source_gap_arms_farming_tool_requires_definition_anchor():
    missing = missing_required_authorities(
        required_sources=["Arms Act 1959 definition/licensing/penalty source for alleged weapon or farming tool"],
        passages=[
            {
                "index": 1,
                "title": "Arms Act 1959",
                "anchor": "arms-1959/sec-25",
                "source_type": "bare_act",
            }
        ],
        query="arms act for axe used in farming",
    )
    covered = missing_required_authorities(
        required_sources=["Arms Act 1959 definition/licensing/penalty source for alleged weapon or farming tool"],
        passages=[
            {
                "index": 1,
                "title": "Arms Act 1959",
                "anchor": "arms-1959/sec-2",
                "source_type": "bare_act",
            }
        ],
        query="arms act for axe used in farming",
    )

    assert missing[0]["required_source"].startswith("Arms Act 1959")
    assert covered == []


def test_source_gap_accepts_default_bail_remand_sections():
    assert missing_required_authorities(
        required_sources=["BNSS 2023 / CrPC 1973 default bail provisions based on incident date"],
        passages=[
            {
                "index": 1,
                "title": "Bharatiya Nagarik Suraksha Sanhita 2023",
                "anchor": "bnss-2023/sec-187",
                "source_type": "bare_act",
            },
            {
                "index": 2,
                "title": "Code of Criminal Procedure 1973",
                "anchor": "crpc-1973/sec-167",
                "source_type": "bare_act",
            },
        ],
        query="brother in jail 60 days no chargesheet what is default bail",
    ) == []


def test_source_gap_accepts_ndps_search_seizure_procedure_sections():
    required = [
        "BNSS 2023 / CrPC 1973 search, seizure, arrest, bail, and complaint procedure based on incident date"
    ]
    query = "police caught my drug parcel at airport no fake call no money demand what punishment"

    assert missing_required_authorities(
        required_sources=required,
        passages=[
            {
                "index": 1,
                "title": "Bharatiya Nagarik Suraksha Sanhita 2023",
                "anchor": "bnss-2023/sec-483@2024-07-01",
                "source_type": "bare_act",
            },
            {
                "index": 3,
                "title": "Code of Criminal Procedure 1973",
                "anchor": "crpc-1973/sec-165",
                "source_type": "bare_act",
            },
            {
                "index": 4,
                "title": "Narcotic Drugs and Psychotropic Substances Act 1985",
                "anchor": "ndps-1985/sec-22-a",
                "source_type": "bare_act",
            },
        ],
        query=query,
    ) == []

    wrong_family = missing_required_authorities(
        required_sources=required,
        passages=[
            {
                "index": 1,
                "title": "Bharatiya Nagarik Suraksha Sanhita 2023",
                "anchor": "bnss-2023/sec-144",
                "source_type": "bare_act",
            },
            {
                "index": 2,
                "title": "Code of Criminal Procedure 1973",
                "anchor": "crpc-1973/sec-125",
                "source_type": "bare_act",
            },
        ],
        query=query,
    )
    assert wrong_family == [
        {
            "required_source": required[0],
            "kind": "national_criminal_source_gap",
        }
    ]


def test_stage_e6_source_gap_accepts_undertrial_and_special_bail_authorities():
    assert missing_required_authorities(
        required_sources=["Legal Services Authorities Act 1987 and Under Trial Review Committee procedure"],
        passages=[
            {
                "index": 1,
                "title": "Legal Services Authorities Act 1987",
                "anchor": "legal-services-authorities-1987/sec-9",
                "source_type": "bare_act",
            },
        ],
        query="undertrial in jail 6 years trial not started legal aid what can we do",
    ) == []

    assert missing_required_authorities(
        required_sources=["BNS 2023 / IPC 1860 offence provisions where relevant"],
        passages=[],
        query="uapa 18 months bail prima facie case made out",
    ) == []

    medical_with_wrong_section = missing_required_authorities(
        required_sources=["constitutional liberty and medical/vulnerability bail principles"],
        passages=[
            {
                "index": 1,
                "title": "Code of Criminal Procedure 1973",
                "anchor": "crpc-1973/sec-437-a",
                "source_type": "bare_act",
            },
        ],
        query="wife arrested pmla bank fraud interim bail newborn",
    )
    assert medical_with_wrong_section

    assert missing_required_authorities(
        required_sources=["constitutional liberty and medical/vulnerability bail principles"],
        passages=[
            {
                "index": 1,
                "title": "Code of Criminal Procedure 1973",
                "anchor": "crpc-1973/sec-437",
                "source_type": "bare_act",
            },
        ],
        query="wife arrested pmla bank fraud interim bail newborn",
    ) == []

    article_21a_education_not_liberty = missing_required_authorities(
        required_sources=["constitutional liberty and medical/vulnerability bail principles"],
        passages=[
            {
                "index": 1,
                "title": "Constitution of India",
                "anchor": "constitution-india/sec-21-a",
                "source_type": "bare_act",
            },
        ],
        query="wife arrested pmla bank fraud interim bail newborn",
    )
    assert article_21a_education_not_liberty

    assert missing_required_authorities(
        required_sources=["constitutional liberty and medical/vulnerability bail principles"],
        passages=[
            {
                "index": 1,
                "title": "Constitution of India",
                "anchor": "constitution-india/sec-21",
                "source_type": "bare_act",
            },
        ],
        query="wife arrested pmla bank fraud interim bail newborn",
    ) == []

    assert missing_required_authorities(
        required_sources=["BNSS 2023 / CrPC 1973 bail and custody procedure based on incident date"],
        passages=[
            {
                "index": 1,
                "title": "Bharatiya Nagarik Suraksha Sanhita 2023",
                "anchor": "bnss-2023/sec-187-b@2024-07-01",
                "source_type": "bare_act",
            },
            {
                "index": 2,
                "title": "Code of Criminal Procedure 1973",
                "anchor": "crpc-1973/sec-167-b",
                "source_type": "bare_act",
            },
        ],
        query="ndps 110 days no complaint filed special court default bail possible",
    ) == []

    assert missing_required_authorities(
        required_sources=["BNSS 2023 / CrPC 1973 arrest, FIR, remand, and bail procedure based on incident date"],
        passages=[
            {
                "index": 1,
                "title": "Bharatiya Nagarik Suraksha Sanhita 2023",
                "anchor": "bnss-2023/sec-35@2024-07-01",
                "source_type": "bare_act",
            },
            {
                "index": 2,
                "title": "Code of Criminal Procedure 1973",
                "anchor": "crpc-1973/sec-167-a",
                "source_type": "bare_act",
            },
        ],
        query="police arrested my son for being gay",
    ) == []

    arrest_with_wrong_bnss_section = missing_required_authorities(
        required_sources=["BNSS 2023 / CrPC 1973 arrest, FIR, remand, and bail procedure based on incident date"],
        passages=[
            {
                "index": 1,
                "title": "Bharatiya Nagarik Suraksha Sanhita 2023",
                "anchor": "bnss-2023/sec-216@2024-07-01",
                "source_type": "bare_act",
            },
        ],
        query="in 2025 police arrested my son for being gay",
    )
    assert arrest_with_wrong_bnss_section

    assert missing_required_authorities(
        required_sources=["Unlawful Activities (Prevention) Act 1967 section 43D / 43D(5) bail restrictions and prolonged-incarceration/default-bail rules"],
        passages=[
            {
                "index": 1,
                "title": "Unlawful Activities (Prevention) Act 1967",
                "anchor": "uapa-1967/sec-43d",
                "source_type": "bare_act",
            },
        ],
        query="uapa 18 months bail prima facie case made out",
    ) == []

    uapa_missing = missing_required_authorities(
        required_sources=["Unlawful Activities (Prevention) Act 1967 section 43D / 43D(5) bail restrictions and prolonged-incarceration/default-bail rules"],
        passages=[
            {
                "index": 1,
                "title": "Bharatiya Nagarik Suraksha Sanhita 2023",
                "anchor": "bnss-2023/sec-480",
                "source_type": "bare_act",
            },
        ],
        query="uapa 18 months bail prima facie case made out",
    )
    assert uapa_missing


def test_source_gap_accepts_subsection_anchors_and_combined_constitution_sources():
    assert missing_required_authorities(
        required_sources=[
            "BNSS 2023 section 528 for current High Court inherent-powers/quashing framing",
            "CrPC 1973 section 482 for pre-1 July 2024 or legacy CrPC framing",
        ],
        passages=[
            {
                "index": 1,
                "title": "Bharatiya Nagarik Suraksha Sanhita 2023",
                "anchor": "bnss-2023/sec-528@2024-07-01",
                "source_type": "bare_act",
            },
            {
                "index": 2,
                "title": "Code of Criminal Procedure 1973",
                "anchor": "crpc-1973/sec-482",
                "source_type": "bare_act",
            },
        ],
        query="fake fir quashing after wages",
    ) == []

    assert missing_required_authorities(
        required_sources=[
            "Article 21 and Article 22 liberty and arrest safeguards",
            "Code on Wages 2019 where the same facts include unpaid wage, attendance, or contractor payment dispute",
        ],
        passages=[
            {
                "index": 1,
                "title": "Constitution of India",
                "anchor": "constitution-india/sec-21",
                "source_type": "bare_act",
            },
            {
                "index": 2,
                "title": "Constitution of India",
                "anchor": "constitution-india/sec-22",
                "source_type": "bare_act",
            },
            {
                "index": 3,
                "title": "Code on Wages 2019",
                "anchor": "code-on-wages-2019/sec-45@2019-08-08",
                "source_type": "bare_act",
            },
        ],
        query="labour chowk police picking workers saying begging",
    ) == []


def test_source_gap_does_not_mix_regime_and_section_across_unrelated_passages():
    mixed_wrong_sources = missing_required_authorities(
        required_sources=["BNSS 2023 / CrPC 1973 bail provisions based on incident date"],
        passages=[
            {
                "index": 1,
                "title": "Bharatiya Nagarik Suraksha Sanhita 2023",
                "anchor": "bnss-2023/sec-173",
                "source_type": "bare_act",
            },
            {
                "index": 2,
                "title": "Negotiable Instruments Act 1881",
                "anchor": "negotiable-instruments-1881/sec-480",
                "source_type": "bare_act",
            },
            {
                "index": 3,
                "title": "Code of Criminal Procedure 1973",
                "anchor": "crpc-1973/sec-154",
                "source_type": "bare_act",
            },
        ],
        query="brother arrested six months no chargesheet can bail be filed",
    )

    assert mixed_wrong_sources == [
        {
            "required_source": "BNSS 2023 / CrPC 1973 bail provisions based on incident date",
            "kind": "national_criminal_source_gap",
        }
    ]


def test_source_gap_anchor_matching_does_not_treat_sec_359_as_sec_35():
    missing = missing_required_authorities(
        required_sources=["BNSS 2023 / CrPC 1973 arrest, notice, bail, and complaint procedure based on incident date"],
        passages=[
            {
                "index": 1,
                "title": "Bharatiya Nagarik Suraksha Sanhita 2023",
                "anchor": "bnss-2023/sec-359",
                "source_type": "bare_act",
            },
            {
                "index": 2,
                "title": "Code of Criminal Procedure 1973",
                "anchor": "crpc-1973/sec-160",
                "source_type": "bare_act",
            },
        ],
        query="police notice came after arrest threat",
    )

    assert missing


def test_source_gap_kind_uses_required_source_before_query_terms():
    missing = missing_required_authorities(
        required_sources=["BNSS 2023 / CrPC 1973 bail provisions based on incident date"],
        passages=[],
        query="village called my mother witch and police arrested my brother",
    )

    assert missing == [
        {
            "required_source": "BNSS 2023 / CrPC 1973 bail provisions based on incident date",
            "kind": "national_criminal_source_gap",
        }
    ]


def test_source_gap_event_has_user_handoff_policy_for_state_gap():
    event = build_source_gap_event(
        query="ranchi village calling mother daain",
        route_category="police_fir",
        required_sources=["Jharkhand witch-hunting state Act source"],
        passages=[
            {
                "index": 1,
                "title": "Bharatiya Nyaya Sanhita 2023",
                "anchor": "bns-2023/sec-115",
                "source_type": "bare_act",
            }
        ],
    )

    assert event is not None
    assert event["has_gap"] is True
    assert event["policy"] == "do_not_substitute_neighboring_authority"
    assert event["handoff"]
    assert event["gap_kinds"] == ["state_or_local_authority_gap"]


def test_jharkhand_witch_reference_marker_does_not_satisfy_state_gap():
    missing = missing_required_authorities(
        required_sources=[
            "state-specific witch-hunting statute must be verified for the user's state before state-law offence details are given"
        ],
        passages=[
            {
                "index": 1,
                "title": "Jharkhand Prevention of Witch (Daain) Practices Act 2001",
                "anchor": "jharkhand-prevention-witch-daain-practices-2001/sec-3",
                "source_type": "official_summary",
            }
        ],
        query="neighbours calling me witch want to throw me out of village chaibasa",
    )

    assert missing
    assert missing[0]["kind"] == "state_or_local_authority_gap"


def test_jharkhand_witch_bare_act_satisfies_state_gap_for_districts():
    missing = missing_required_authorities(
        required_sources=[
            "state-specific witch-hunting statute must be verified for the user's state before state-law offence details are given"
        ],
        passages=[
            {
                "index": 1,
                "title": "Jharkhand Prevention of Witch (Daain) Practices Act 2001",
                "anchor": "jharkhand-prevention-witch-daain-practices-2001/sec-3",
                "source_type": "bare_act",
            }
        ],
        query="tribal woman called witch and beaten in gumla police refused FIR",
    )

    assert missing == []


def test_jhalsa_witch_official_guidance_satisfies_jharkhand_state_gap():
    missing = missing_required_authorities(
        required_sources=[
            "state-specific witch-hunting statute must be verified for the user's state before state-law offence details are given"
        ],
        passages=[
            {
                "index": 1,
                "title": "Jharkhand State Legal Services Authority Dayan Pratha Pratishedh Adhiniyam 2001",
                "anchor": "jhalsa-dayan-pratha-pratishedh-2001/sec-4",
                "source_type": "official_guidance",
            }
        ],
        query="village ojha branded my mother daayan stripped her in public ranchi",
    )

    assert missing == []


def test_jharkhand_witch_judgment_does_not_satisfy_state_gap():
    missing = missing_required_authorities(
        required_sources=[
            "state-specific witch-hunting statute must be verified for the user's state before state-law offence details are given"
        ],
        passages=[
            {
                "index": 1,
                "title": "Jharkhand witch daain criminal case",
                "anchor": "2024-jharkhand-witch-case#para-7",
                "source_type": "hc_judgment",
            }
        ],
        query="neighbours calling me witch want to throw me out of village chaibasa",
    )

    assert missing
    assert missing[0]["kind"] == "state_or_local_authority_gap"


def test_income_tax_1432_gap_requires_section_143_not_adjacent_assessment_sections():
    missing = missing_required_authorities(
        required_sources=["Income Tax Act 1961 section 143(2) scrutiny-assessment notice source"],
        passages=[
            {
                "index": 1,
                "title": "Income-tax Act 1961",
                "anchor": "income-tax-1961/sec-142",
                "source_type": "bare_act",
            },
            {
                "index": 2,
                "title": "Income-tax Act 1961",
                "anchor": "income-tax-1961/sec-144",
                "source_type": "bare_act",
            },
        ],
        query="got income tax notice under section 143(2) how much time to respond",
    )

    assert missing
    assert missing[0]["kind"] == "national_tax_source_gap"


def test_stage_b_source_gap_false_negatives_accept_present_sources():
    assert missing_required_authorities(
        required_sources=["Dowry Prohibition Act 1961 or civil recovery route where gifts, dowry, or wedding expenses are disputed"],
        passages=[{"index": 1, "title": "Dowry Prohibition Act 1961", "anchor": "dowry-prohibition-1961/sec-2"}],
        query="fiance hid HIV status can I cancel wedding without dowry return issue",
    ) == []

    assert missing_required_authorities(
        required_sources=["Clinical Establishments Act / state clinical-establishment rules where hospital records, billing, or standards are involved"],
        passages=[{"index": 1, "title": "Clinical Establishments (Registration and Regulation) Act 2010", "anchor": "clinical-establishments-2010/sec-12"}],
        query="private hospital in noida overcharged ICU bill",
    ) == []

    assert missing_required_authorities(
        required_sources=["Representation of the People Act 1950 / election rules where voter-list correction or denial of vote is involved"],
        passages=[{"index": 1, "title": "Representation of the People Act 1950", "anchor": "rpa-1950/sec-23-a@2021-01-01"}],
        query="voter id name spelt wrong booth officer denied me vote",
    ) == []

    assert missing_required_authorities(
        required_sources=["BNSS/CrPC bail and arrest safeguards where relevant"],
        passages=[{"index": 1, "title": "Bharatiya Nagarik Suraksha Sanhita 2023", "anchor": "bnss-2023/sec-483@2024-07-01"}],
        query="pmla case ED filed twin condition how to argue not guilty",
    ) == []

    assert missing_required_authorities(
        required_sources=["Insurance Ombudsman Rules / insurer grievance procedure"],
        passages=[{"index": 3, "title": "Insurance Ombudsman Rules 2017", "anchor": "insurance-ombudsman-rules-2017/sec-5-h"}],
        query="insurer is rejecting my claim",
    ) == []


def test_stage_b_source_gap_skips_non_applicable_conditionals():
    assert missing_required_authorities(
        required_sources=["Information Technology Act 2000 where platform messages, DMs, or online accounts are involved"],
        passages=[],
        query="ex boyfriend follows my scooty everyday from office to home he does not talk just follows",
    ) == []

    assert missing_required_authorities(
        required_sources=["Indian Succession Act 1925 where applicable"],
        passages=[],
        query="i am 70 yr widow muslim son says wife and daughter cant inherit from his father what is sunni law",
    ) == []

    assert missing_required_authorities(
        required_sources=["Juvenile Justice Act 2015 and adoption regulations where adoption papers are missing"],
        passages=[],
        query="ex husband took our son to UK on tourist visa and is not bringing back",
    ) == []

    assert missing_required_authorities(
        required_sources=["Juvenile Justice Act 2015 and adoption regulations where adoption papers are missing"],
        passages=[],
        query="child passport papers are stuck with father for travel",
    ) == []

    assert missing_required_authorities(
        required_sources=["Juvenile Justice Act 2015 and adoption regulations where adoption papers are missing"],
        passages=[],
        query="school papers for my son are not released by principal",
    ) == []


def test_stage_b_source_gap_accepts_jj_adoption_sections_but_not_bail_for_arrest():
    assert missing_required_authorities(
        required_sources=["Juvenile Justice Act 2015 and adoption regulations where adoption papers are missing"],
        passages=[{"index": 1, "title": "Juvenile Justice (Care and Protection of Children) Act 2015", "anchor": "jj-2015/sec-56"}],
        query="we adopted child from sister but no papers now real parents want him back",
    ) == []

    assert missing_required_authorities(
        required_sources=["Juvenile Justice Act 2015 and adoption regulations where adoption papers are missing"],
        passages=[{"index": 1, "title": "Juvenile Justice (Care and Protection of Children) Act 2015", "anchor": "jj-2015/sec-56"}],
        query="we are adopting child from sister no papers now real parents object custody",
    ) == []

    assert missing_required_authorities(
        required_sources=["Juvenile Justice Act 2015 and adoption regulations where adoption papers are missing"],
        passages=[],
        query="we are adopting child from sister no papers now real parents object custody",
    ) == [
        {
            "required_source": "Juvenile Justice Act 2015 and adoption regulations where adoption papers are missing",
            "kind": "national_statute_retrieval_gap",
        }
    ]

    arrest_gap = missing_required_authorities(
        required_sources=["BNSS/CrPC bail and arrest safeguards where relevant"],
        passages=[{"index": 1, "title": "Bharatiya Nagarik Suraksha Sanhita 2023", "anchor": "bnss-2023/sec-480"}],
        query="police arrested my son last night and did not produce him in 24 hours",
    )
    assert arrest_gap == [
        {
            "required_source": "BNSS/CrPC bail and arrest safeguards where relevant",
            "kind": "national_criminal_source_gap",
        }
    ]


def test_early_refusal_source_gap_event_can_be_built_without_retrieved_passages():
    route = MatterRoute(
        category="criminal_defence_bail",
        label="Bail / criminal defence",
        confidence=0.8,
        urgency="high",
        required_sources=["BNSS 2023 / CrPC 1973 bail provisions based on incident date"],
        forums=["criminal court"],
        missing_facts=["incident date"],
        red_flags=[],
    )

    event = _source_gap_event_for_retrieved(
        query="brother arrested six months no chargesheet can bail be filed",
        route=route,
        retrieved=[],
        top_k=8,
    )

    assert event is not None
    assert event["has_gap"] is True
    assert event["gap_kinds"] == ["national_criminal_source_gap"]


def test_critical_route_guard_requires_reviewed_primary_contract():
    route = MatterRoute(
        category="police_fir",
        label="FIR / police inaction",
        confidence=0.8,
        urgency="high",
        required_sources=[],
        forums=["police station"],
        missing_facts=[],
        red_flags=[],
    )

    assert _critical_route_needs_reviewed_contract(route, None) is True
    assert _critical_route_needs_reviewed_contract(
        route,
        WorkflowTemplateResult(
            id="legacy_like_merge",
            source="common_workflow_contracts",
            lines=["line [1]"],
            answer_mode="merge",
        ),
    ) is True
    assert _critical_route_needs_reviewed_contract(
        route,
        WorkflowTemplateResult(
            id="reviewed_police_path",
            source="common_workflow_contracts",
            lines=["line [1]"],
            answer_mode="safety_primary",
        ),
    ) is False


def test_bonded_labour_rescue_is_launch_critical():
    route = MatterRoute(
        category="bonded_labour_rescue",
        label="Bonded labour / forced labour rescue",
        confidence=0.84,
        urgency="emergency",
        required_sources=[],
        forums=["District Magistrate"],
        missing_facts=[],
        red_flags=[],
    )

    assert _critical_route_needs_reviewed_contract(route, None) is True


def test_stage_c_conditional_criminal_sources_do_not_overfire_for_procedure_only_queries():
    required = [
        "BNSS 2023 / CrPC 1973 bail provisions based on incident date",
        "BNS 2023 / IPC 1860 offence provisions where relevant",
    ]

    procedure_only = missing_required_authorities(
        required_sources=required,
        passages=[],
        query="urgent what documents needed for anticipatory bail application in sessions court",
    )
    procedure_only_texts = {item["required_source"] for item in procedure_only}
    assert "BNSS 2023 / CrPC 1973 bail provisions based on incident date" in procedure_only_texts
    assert "BNS 2023 / IPC 1860 offence provisions where relevant" not in procedure_only_texts

    offence_facts = missing_required_authorities(
        required_sources=required,
        passages=[],
        query="my son 19 first time offender 379 theft how to get bail magistrate court",
    )
    offence_texts = {item["required_source"] for item in offence_facts}
    assert "BNSS 2023 / CrPC 1973 bail provisions based on incident date" in offence_texts
    assert "BNS 2023 / IPC 1860 offence provisions where relevant" in offence_texts


def test_stage_c_conditional_posh_bns_and_limitation_only_fire_on_matching_facts():
    posh_required = [
        "Sexual Harassment of Women at Workplace Act 2013",
        "BNS 2023 / IPC 1860 provisions where physical assault, stalking, or threats are involved",
    ]

    pip_only = missing_required_authorities(
        required_sources=posh_required,
        passages=[],
        query="after I complained to ICC against manager he gave bad rating and PIP",
    )
    pip_texts = {item["required_source"] for item in pip_only}
    assert "Sexual Harassment of Women at Workplace Act 2013" in pip_texts
    assert "BNS 2023 / IPC 1860 provisions where physical assault, stalking, or threats are involved" not in pip_texts

    touched = missing_required_authorities(
        required_sources=posh_required,
        passages=[],
        query="boss touched my back in office and now threatening me after complaint",
    )
    touched_texts = {item["required_source"] for item in touched}
    assert "BNS 2023 / IPC 1860 provisions where physical assault, stalking, or threats are involved" in touched_texts

    assert missing_required_authorities(
        required_sources=["Limitation Act 1963 where needed"],
        passages=[],
        query="father made gift deed before death now daughter wants share is gift valid",
    ) == []
    limitation = missing_required_authorities(
        required_sources=["Limitation Act 1963 where needed"],
        passages=[],
        query="tribunal order came 120 days ago can I still appeal delay condonation",
    )
    assert {item["required_source"] for item in limitation} == {"Limitation Act 1963 where needed"}


def test_stage_c_pesa_fra_requirement_is_fact_triggered():
    required = ["PESA Act / Forest Rights Act where Scheduled Area or forest-rights facts apply"]

    assert missing_required_authorities(
        required_sources=required,
        passages=[],
        query="ordinary property boundary dispute in city apartment",
    ) == []
    assert missing_required_authorities(
        required_sources=required,
        passages=[],
        query="mob attacked our pahan during sarna puja calling adivasi non hindu jharkhand",
    ) == []
    forest_gap = missing_required_authorities(
        required_sources=required,
        passages=[],
        query="forest guard stopped us collecting bamboo and tendu leaves from our village forest",
    )
    assert {item["required_source"] for item in forest_gap} == set(required)
    gram_sabha_gap = missing_required_authorities(
        required_sources=required,
        passages=[],
        query="bauxite mining NOC given without gram sabha resolution in scheduled area",
    )
    assert {item["required_source"] for item in gram_sabha_gap} == set(required)


def test_stage_c_expands_launch_critical_guard_routes():
    for category in (
        "cyber_fraud_or_harassment",
        "workplace_sexual_harassment",
        "child_custody_adoption",
        "sexual_offence_survivor",
        "reproductive_rights_mtp",
        "child_marriage_protection",
        "criminal_procedure_notice",
        "manual_scavenging_safety",
        "custody_compensation",
        "pmla_ed",
        "business_contract_partnership",
        "digital_platform_account",
    ):
        route = MatterRoute(
            category=category,
            label=category,
            confidence=0.8,
            urgency="high",
            required_sources=[],
            forums=[],
            missing_facts=[],
            red_flags=[],
        )
        assert _critical_route_needs_reviewed_contract(route, None) is True


def test_stage_c_bns_ipc_source_matching_is_section_family_aware():
    wrong_bns = [
        {
            "index": 1,
            "title": "Bharatiya Nyaya Sanhita 2023",
            "anchor": "bns-2023/sec-356",
            "source_type": "bare_act",
        }
    ]
    hurt_required = ["BNS 2023 / IPC 1860 provisions where physical assault, stalking, or threats are involved"]
    hurt_gap = missing_required_authorities(
        required_sources=hurt_required,
        passages=wrong_bns,
        query="boss touched my back and threatened me after complaint",
    )
    assert {item["required_source"] for item in hurt_gap} == set(hurt_required)

    hurt_found = missing_required_authorities(
        required_sources=hurt_required,
        passages=[
            {
                "index": 1,
                "title": "Bharatiya Nyaya Sanhita 2023",
                "anchor": "bns-2023/sec-74",
                "source_type": "bare_act",
            }
        ],
        query="boss touched my back and threatened me after complaint",
    )
    assert hurt_found == []

    acid_required = ["BNS 2023 / IPC 1860 acid attack offence source based on incident date"]
    acid_gap = missing_required_authorities(
        required_sources=acid_required,
        passages=wrong_bns,
        query="auto driver threw acid on my face what FIR section applies",
    )
    assert {item["required_source"] for item in acid_gap} == set(acid_required)


def test_stage_c_composite_dual_regime_requires_matching_offence_section_family():
    required = ["BNS/BNSS or IPC/CrPC based on incident date"]
    wrong_bns_with_procedure = [
        {
            "index": 1,
            "title": "Bharatiya Nyaya Sanhita 2023",
            "anchor": "bns-2023/sec-356",
            "source_type": "bare_act",
        },
        {
            "index": 2,
            "title": "Bharatiya Nagarik Suraksha Sanhita 2023",
            "anchor": "bnss-2023/sec-173",
            "source_type": "bare_act",
        },
    ]

    missing = missing_required_authorities(
        required_sources=required,
        passages=wrong_bns_with_procedure,
        query="auto driver threw acid on my face what FIR section applies",
    )
    assert {item["required_source"] for item in missing} == set(required)

    found = missing_required_authorities(
        required_sources=required,
        passages=[
            {
                "index": 1,
                "title": "Bharatiya Nyaya Sanhita 2023",
                "anchor": "bns-2023/sec-124",
                "source_type": "bare_act",
            },
            {
                "index": 2,
                "title": "Bharatiya Nagarik Suraksha Sanhita 2023",
                "anchor": "bnss-2023/sec-173",
                "source_type": "bare_act",
            },
        ],
        query="auto driver threw acid on my face what FIR section applies",
    )
    assert found == []


def test_stage_e7_family_conditional_criminal_sources_require_separate_criminal_lane():
    dv_notice_required = [
        "BNSS/CrPC and BNS/IPC only where a separate FIR, arrest notice, or criminal complaint exists"
    ]

    no_criminal_lane = missing_required_authorities(
        required_sources=dv_notice_required,
        passages=[],
        query="wife filed false domestic violence case, i have notice what do i reply",
    )
    assert no_criminal_lane == []

    explicit_no_fir_notice = missing_required_authorities(
        required_sources=dv_notice_required,
        passages=[],
        query="wife filed domestic violence case, no FIR just notice reply",
    )
    assert explicit_no_fir_notice == []

    separate_fir = missing_required_authorities(
        required_sources=dv_notice_required,
        passages=[],
        query="wife filed domestic violence case and separate FIR under 498A, police sent arrest notice",
    )
    assert {item["required_source"] for item in separate_fir} == set(dv_notice_required)

    forced_sex_safety_required = [
        "BNS 2023 / IPC 1860 sexual-offence provisions and marital-exception limits only where a separate FIR, arrest notice, or criminal complaint exists"
    ]
    safety_first = missing_required_authorities(
        required_sources=forced_sex_safety_required,
        passages=[],
        query="husband forced sex even when i say no",
    )
    assert safety_first == []

    fir_lane = missing_required_authorities(
        required_sources=forced_sex_safety_required,
        passages=[],
        query="husband forced sex even when i say no and police filed FIR",
    )
    assert {item["required_source"] for item in fir_lane} == set(forced_sex_safety_required)


def test_stage_e7_hindu_marriage_section_13_match_is_exact_not_13b():
    required = [
        "Hindu Marriage Act 1955 section 13 or applicable personal/Special Marriage Act divorce ground"
    ]
    mutual_consent_only = missing_required_authorities(
        required_sources=required,
        passages=[
            {
                "index": 1,
                "title": "Hindu Marriage Act 1955",
                "anchor": "hindu-marriage-1955/sec-13-b",
                "source_type": "bare_act",
            }
        ],
        query="i caught my husband with another woman having sex",
    )
    assert {item["required_source"] for item in mutual_consent_only} == set(required)

    divorce_ground_fragment = missing_required_authorities(
        required_sources=required,
        passages=[
            {
                "index": 1,
                "title": "Hindu Marriage Act 1955",
                "anchor": "hindu-marriage-1955/sec-13-a",
                "source_type": "bare_act",
            }
        ],
        query="i caught my husband with another woman having sex",
    )
    assert divorce_ground_fragment == []

    divorce_ground = missing_required_authorities(
        required_sources=required,
        passages=[
            {
                "index": 1,
                "title": "Hindu Marriage Act 1955",
                "anchor": "hindu-marriage-1955/sec-13",
                "source_type": "bare_act",
            }
        ],
        query="i caught my husband with another woman having sex",
    )
    assert divorce_ground == []


def test_stage_e7_marriage_misrepresentation_enforces_voidable_and_family_court_sources():
    query = "i am hindu my husband is gay and hidden before marriage what can i do"
    route = route_matter(query)
    assert route.category == "family_marriage_status"

    missing = missing_required_authorities(
        required_sources=route.required_sources,
        passages=[],
        query=query,
    )
    missing_sources = {item["required_source"] for item in missing}
    assert any("Hindu Marriage Act" in source and "Special Marriage Act" in source for source in missing_sources)
    assert any("Family Courts Act" in source for source in missing_sources)

    covered = missing_required_authorities(
        required_sources=route.required_sources,
        passages=[
            {
                "index": 1,
                "title": "Hindu Marriage Act 1955",
                "anchor": "hindu-marriage-1955/sec-12",
                "source_type": "bare_act",
            },
            {
                "index": 2,
                "title": "Family Courts Act 1984",
                "anchor": "family-courts-1984/sec-7",
                "source_type": "bare_act",
            },
        ],
        query=query,
    )
    assert not any("Hindu Marriage Act" in item["required_source"] for item in covered)
    assert not any("Family Courts Act" in item["required_source"] for item in covered)


def test_stage_e7_domestic_residence_negated_assault_does_not_force_criminal_sources():
    query = "husband throws me out but house in mother in law name no assault no threat"
    route = route_matter(query)
    assert route.label == "Domestic violence / right to residence"

    missing = missing_required_authorities(
        required_sources=route.required_sources,
        passages=[],
        query=query,
    )
    missing_sources = {item["required_source"] for item in missing}
    assert any("PWDVA 2005" in source for source in missing_sources)
    assert not any("BNS 2023" in source or "IPC 1860" in source for source in missing_sources)
    assert not any("BNSS 2023" in source or "CrPC 1973" in source for source in missing_sources)


def test_stage_e7_spousal_property_return_requires_neutral_family_court_source():
    query = "my wife took my gold and left house"
    route = route_matter(query)
    assert route.label == "Spousal jewellery / property return"

    missing = missing_required_authorities(
        required_sources=route.required_sources,
        passages=[],
        query=query,
    )
    missing_sources = {item["required_source"] for item in missing}
    assert any("Family Courts Act 1984" in source for source in missing_sources)

    covered = missing_required_authorities(
        required_sources=route.required_sources,
        passages=[
            {
                "index": 1,
                "title": "Family Courts Act 1984",
                "anchor": "family-courts-1984/sec-7",
                "source_type": "bare_act",
            },
        ],
        query=query,
    )
    assert not any("Family Courts Act 1984" in item["required_source"] for item in covered)


def test_stage_e7_bns67_satisfies_marital_sexual_offence_conditional_gap():
    required = [
        "BNS 2023 / IPC 1860 sexual-offence provisions and marital-exception limits only where a separate FIR, arrest notice, or criminal complaint exists"
    ]

    missing = missing_required_authorities(
        required_sources=required,
        passages=[
            {
                "index": 1,
                "title": "Bharatiya Nyaya Sanhita 2023",
                "anchor": "bns-2023/sec-67@2024-07-01",
                "source_type": "bare_act",
            },
        ],
        query="my husband forced sex even when i say no and police filed FIR",
    )

    assert missing == []


def test_stage_e7_domestic_threat_dual_procedure_source_is_satisfied_by_bnss_and_crpc():
    query = "husband locked me out of shared house and threatens me if I come back"
    route = route_matter(query)
    assert route.label == "Domestic violence / right to residence"

    missing = missing_required_authorities(
        required_sources=route.required_sources,
        passages=[
            {
                "index": 1,
                "title": "Bharatiya Nyaya Sanhita 2023",
                "anchor": "bns-2023/sec-351@2024-07-01",
                "source_type": "bare_act",
            },
            {
                "index": 2,
                "title": "Bharatiya Nagarik Suraksha Sanhita 2023",
                "anchor": "bnss-2023/sec-173-b@2024-07-01",
                "source_type": "bare_act",
            },
            {
                "index": 3,
                "title": "Code of Criminal Procedure 1973",
                "anchor": "crpc-1973/sec-154",
                "source_type": "bare_act",
            },
            {
                "index": 4,
                "title": "Protection of Women from Domestic Violence Act 2005",
                "anchor": "domestic-violence-2005/sec-19",
                "source_type": "bare_act",
            },
        ],
        query=query,
    )

    assert not any(
        "BNSS 2023" in item["required_source"] and "CrPC 1973" in item["required_source"]
        for item in missing
    )


def test_stage_e7_family_police_refusal_enforces_bnss_crpc_but_no_police_does_not():
    query = "husband forced sex even when i say no and police refused complaint"
    route = route_matter(query)
    assert route.label == "Marital sexual violence / domestic safety"

    missing = missing_required_authorities(
        required_sources=route.required_sources,
        passages=[],
        query=query,
    )
    missing_sources = {item["required_source"] for item in missing}
    assert any("PWDVA 2005" in source for source in missing_sources)
    assert any("BNSS 2023" in source and "CrPC 1973" in source for source in missing_sources)

    safety_only = "husband forced sex even when i say no no police no FIR"
    safety_route = route_matter(safety_only)
    safety_missing = missing_required_authorities(
        required_sources=safety_route.required_sources,
        passages=[],
        query=safety_only,
    )
    safety_sources = {item["required_source"] for item in safety_missing}
    assert any("PWDVA 2005" in source for source in safety_sources)
    assert not any("BNSS 2023" in source or "CrPC 1973" in source for source in safety_sources)


def test_stage_e7_bns_breach_of_trust_subanchors_satisfy_streedhan_source():
    required = [
        "BNS 2023 / IPC 1860 criminal breach of trust, cheating, or theft provisions based on incident date"
    ]

    found = missing_required_authorities(
        required_sources=required,
        passages=[
            {
                "index": 1,
                "title": "Bharatiya Nyaya Sanhita 2023",
                "anchor": "bns-2023/sec-316-c",
                "source_type": "bare_act",
            }
        ],
        query="in laws not returning my jewellery",
    )
    assert found == []

    wrong_offence = missing_required_authorities(
        required_sources=required,
        passages=[
            {
                "index": 1,
                "title": "Bharatiya Nyaya Sanhita 2023",
                "anchor": "bns-2023/sec-356",
                "source_type": "bare_act",
            }
        ],
        query="in laws not returning my jewellery",
    )
    assert {item["required_source"] for item in wrong_offence} == set(required)


def test_stage_e9_itpa_raid_accepts_bns_exploitation_subanchors():
    required = [
        "BNS 2023 / IPC 1860 trafficking or exploitation provisions based on incident date"
    ]

    missing = missing_required_authorities(
        required_sources=required,
        passages=[
            {
                "index": 1,
                "title": "Bharatiya Nyaya Sanhita 2023",
                "anchor": "bns-2023/sec-144@2024-07-01",
                "source_type": "bare_act",
            },
            {
                "index": 2,
                "title": "Bharatiya Nyaya Sanhita 2023",
                "anchor": "bns-2023/sec-146@2024-07-01",
                "source_type": "bare_act",
            },
        ],
        query=(
            "hi, the spa was raided last week and police took me and other girls "
            "to station I just do massage I am scared what will happen now can i file case"
        ),
    )

    assert missing == []


def test_stage_e9_child_deepfake_accepts_pocso_and_it_privacy_sources():
    required = [
        "POCSO Act 2012 where a child or minor is shown in sexual content",
        "Information Technology Act 2000 section 67B / 66E / 67A where electronic sexual-image publication or privacy misuse is alleged",
    ]

    missing = missing_required_authorities(
        required_sources=required,
        passages=[
            {
                "index": 1,
                "title": "Protection of Children from Sexual Offences Act 2012",
                "anchor": "pocso-2012/sec-13-a",
                "source_type": "bare_act",
            },
            {
                "index": 2,
                "title": "Information Technology Act 2000",
                "anchor": "it-2000/sec-66E",
                "source_type": "bare_act",
            },
        ],
        query=(
            "hi, my schoolmate is making deepfake nude videos of girls in class "
            "using AI n circulating I am one of them I am 15 can i file case"
        ),
    )

    assert missing == []


def test_stage_e9_scst_rule7_source_satisfies_runtime_gap():
    missing = missing_required_authorities(
        required_sources=[
            "SC/ST (Prevention of Atrocities) Rules 1995 Rule 7 DSP-rank investigating-officer requirement"
        ],
        passages=[
            {
                "index": 1,
                "title": "Scheduled Castes and Scheduled Tribes (Prevention of Atrocities) Rules 1995",
                "anchor": "sc-st-poa-rules-1995/rule-7",
                "source_type": "bare_act",
            }
        ],
        query=(
            "pls tell SP not transferring my atrocity case to DSP though POA Act "
            "says so vidarbha need lawyer or police"
        ),
    )

    assert missing == []


def test_stage_e9_whatsapp_hack_requires_matching_bns_bnss_pair():
    required = ["BNS/BNSS or IPC/CrPC based on incident date"]
    query = "sir my whatsapp account got hacked and someone is asking my contacts fr money in my name where to go"

    missing = missing_required_authorities(
        required_sources=required,
        passages=[
            {
                "index": 1,
                "title": "Bharatiya Nyaya Sanhita 2023",
                "anchor": "bns-2023/sec-319@2024-07-01",
                "source_type": "bare_act",
            },
            {
                "index": 2,
                "title": "Bharatiya Nagarik Suraksha Sanhita 2023",
                "anchor": "bnss-2023/sec-173-b@2024-07-01",
                "source_type": "bare_act",
            },
        ],
        query=query,
    )

    assert missing == []


def test_stage_e9b_false_dacoity_accepts_bns_dacoity_anchor():
    missing = missing_required_authorities(
        required_sources=[
            "BNS 2023 / IPC 1860 dacoity, theft, and false-case provisions based on incident date"
        ],
        passages=[
            {
                "index": 1,
                "title": "Bharatiya Nyaya Sanhita 2023",
                "anchor": "bns-2023/sec-310@2024-07-01",
                "source_type": "bare_act",
            }
        ],
        query=(
            "pls tell false dacoity case lodged on my brother by forest guard "
            "for collecting tendu leaves dindori need lawyer or police"
        ),
    )

    assert missing == []


def test_stage_e9b_forest_produce_dacoity_accepts_live_fra_bns_bnss_sources():
    missing = missing_required_authorities(
        required_sources=[
            "PESA Act / Forest Rights Act where Scheduled Area or forest-rights facts apply",
            "BNS/BNSS or IPC/CrPC based on incident date",
        ],
        passages=[
            {
                "index": 1,
                "title": "Bharatiya Nyaya Sanhita 2023",
                "anchor": "bns-2023/sec-309@2024-07-01",
                "source_type": "bare_act",
            },
            {
                "index": 2,
                "title": "Bharatiya Nagarik Suraksha Sanhita 2023",
                "anchor": "bnss-2023/sec-173-b@2024-07-01",
                "source_type": "bare_act",
            },
            {
                "index": 3,
                "title": "Scheduled Tribes and Other Traditional Forest Dwellers (Recognition of Forest Rights) Act 2006",
                "anchor": "fra-2006/sec-5-a@2007-01-01",
                "source_type": "bare_act",
            },
        ],
        query="urgent gaon people took tendu leaves by force 8 men with lathi forest produce dacoity or theft what to do",
    )

    assert missing == []


def test_stage_e9b_chargesheet_tweet_accepts_bnss_police_report_anchor():
    missing = missing_required_authorities(
        required_sources=[
            "BNSS 2023 / CrPC 1973 charge-sheet, summons, bail, discharge, and court procedure based on incident date"
        ],
        passages=[
            {
                "index": 1,
                "title": "Bharatiya Nagarik Suraksha Sanhita 2023",
                "anchor": "bnss-2023/sec-193-a@2024-07-01",
                "source_type": "bare_act",
            }
        ],
        query="can u tell delhi police chargesheet fr tweet calling cm corrupt is this 356 case what can i do",
    )

    assert missing == []


def test_stage_e9b_bocw_factories_requirement_accepts_worksite_safety_sources():
    required = ["BOCW Act 1996 / Factories Act 1948 where applicable"]

    assert missing_required_authorities(
        required_sources=required,
        passages=[
            {
                "index": 1,
                "title": "Building and Other Construction Workers (Regulation of Employment and Conditions of Service) Act 1996",
                "anchor": "bocw-1996/sec-39__2@1996-01-01",
                "source_type": "bare_act",
            }
        ],
        query="hi, fell from 5th floor site whitefield bangalore leg broken thekedar saying no insurance no bocw card can i file case",
    ) == []

    assert missing_required_authorities(
        required_sources=required,
        passages=[
            {
                "index": 1,
                "title": "Factories Act 1948",
                "anchor": "factories-1948/sec-111",
                "source_type": "bare_act",
            }
        ],
        query="please help morbi ceramic factory boiler burst friend dead his family bihar nothing got 6 mnths over any remedy",
    ) == []


def test_stage_e9b_bocw_card_does_not_force_unalleged_cess_or_criminal_sources():
    missing = missing_required_authorities(
        required_sources=[
            "BOCW Cess Act / state welfare-board cess records where cess collection or fake registers are alleged",
            "BNS/BNSS or IPC/CrPC where cheating, forgery, or false registers are alleged",
        ],
        passages=[],
        query="please help how to get bocw card mumbai i work construction 8 years no card no benefit any remedy",
    )

    assert missing == []


def test_stage_e9b_assam_witch_hunting_full_source_satisfies_state_gap():
    missing = missing_required_authorities(
        required_sources=[
            "state-specific witch-hunting statute must be verified for the user's state before state-law offence details are given"
        ],
        passages=[
            {
                "index": 1,
                "title": "Assam Witch Hunting (Prohibition, Prevention and Protection) Act 2015",
                "anchor": "assam-witch-hunting-2015/full",
                "source_type": "bare_act",
            }
        ],
        query="can u tell my saas labelled daayan and beaten by village people assam barpeta what can i do",
    )

    assert missing == []


def test_stage_e9b_assam_witch_violence_accepts_bns_hurt_and_bnss_fir_pair():
    missing = missing_required_authorities(
        required_sources=["BNS/BNSS or IPC/CrPC based on incident date"],
        passages=[
            {
                "index": 1,
                "title": "Bharatiya Nagarik Suraksha Sanhita 2023",
                "anchor": "bnss-2023/sec-173-b@2024-07-01",
                "source_type": "bare_act",
            },
            {
                "index": 2,
                "title": "Bharatiya Nyaya Sanhita 2023",
                "anchor": "bns-2023/sec-117@2024-07-01",
                "source_type": "bare_act",
            },
        ],
        query="barpeta assam village called my aunt daayan beat her and threatened witch hunting what case can file",
    )

    assert missing == []


def test_stage_e9e_source_gap_enforces_indexed_tribunal_procedure_requirements():
    required_sources = [
        "NCLAT rules, forms, fees, certified-copy and limitation facts",
        "NCLT Rules / IBC application forms",
        "state education rules",
        "state caste-certificate issuance and appeal rules",
        "school board or education-record correction rules for marksheet/certificate changes",
        "loan documents and RBI restructuring/settlement guidance where negotiation is requested",
        "GST refund/bank operation records only after company status is addressed",
        "victim-compensation and DLSA procedure for urgent treatment/support",
    ]

    missing = missing_required_authorities(
        required_sources=required_sources,
        passages=[],
        query="urgent tribunal order against me how to appeal NCLAT format and fees",
    )
    assert [item["required_source"] for item in missing] == [
        "NCLAT rules, forms, fees, certified-copy and limitation facts",
        "NCLT Rules / IBC application forms",
    ]
    assert missing_required_authorities(
        required_sources=["NCLT Rules / IBC application forms"],
        passages=[
            {
                "index": 1,
                "title": "National Company Law Tribunal Rules 2016",
                "anchor": "nclt-rules-2016/rule-23",
                "source_type": "rule",
            }
        ],
        query="operational creditor want to file section 9 ibc against company owing money",
    ) == []


def test_stage_e9e_cgst_rule_86b_requires_rules_and_act_ledger_sources():
    required = ["CGST Rules 2017 Rule 86B and CGST Act 2017 electronic-credit-ledger provisions"]
    rule_only = [
        {
            "index": 1,
            "title": "Central Goods and Services Tax Rules 2017",
            "anchor": "cgst-rules-2017/sec-85-e",
            "text": "Rule 86B restricts use of amount available in electronic credit ledger.",
            "source_type": "bare_act",
        }
    ]
    composite = rule_only + [
        {
            "index": 2,
            "title": "Central Goods and Services Tax Act 2017",
            "anchor": "cgst-2017/sec-49-a",
            "source_type": "bare_act",
        }
    ]

    assert missing_required_authorities(
        required_sources=required,
        passages=rule_only,
        query="rule 86B applies to me turnover 55 lakh per month must pay 1 percent cash",
    )
    assert missing_required_authorities(
        required_sources=required,
        passages=composite,
        query="rule 86B applies to me turnover 55 lakh per month must pay 1 percent cash",
    ) == []


def test_stage_e9e_source_gap_accepts_contribution_pesa_and_online_freeze_sources():
    assert missing_required_authorities(
        required_sources=["Code on Social Security 2020 where contribution/social-security classification applies"],
        passages=[
            {
                "index": 1,
                "title": "Code on Social Security 2020",
                "anchor": "social-security-code-2020/sec-31@2025-11-21",
                "source_type": "bare_act",
            }
        ],
        query="esi inspector sent notice contribution short by 1.2 lakh for casual workers",
    ) == []

    assert missing_required_authorities(
        required_sources=["PESA / Gram Sabha consultation where Scheduled Area facts apply"],
        passages=[
            {
                "index": 1,
                "title": "Panchayats (Extension to the Scheduled Areas) Act 1996",
                "anchor": "pesa-1996/sec-4-b@1996-12-24",
                "source_type": "bare_act",
            }
        ],
        query="iron ore mine displaced our 12 villages no rehabilitation given",
    ) == []

    assert missing_required_authorities(
        required_sources=["RBI/KYC or online-gaming rules where financial account facts apply"],
        passages=[
            {
                "index": 1,
                "title": "Prevention of Money Laundering Act 2002",
                "anchor": "pmla-2002/sec-17-a",
                "source_type": "bare_act",
            }
        ],
        query="binance froze my usdt wallet saying suspicious trade and kyc pending",
    ) == []


def test_stage_e9e_source_gap_tightens_overbroad_conditional_triggers():
    assert missing_required_authorities(
        required_sources=[
            "Building and Other Construction Workers Act 1996 where the workplace is a construction/building worksite",
            "Code on Wages 2019 where unpaid overtime wages are also claimed",
            "Specific Relief Act 1963 where injunction/performance is sought",
            "BNSS 2023 / CrPC 1973 only if the case-status issue is in a criminal case",
            "BNS 2023 / IPC 1860 offence provisions where relevant",
        ],
        passages=[],
        query="urgent what should I wear to court as litigant in person appearing first time how to complain",
    ) == []
    assert missing_required_authorities(
        required_sources=["Code on Wages 2019 where unpaid overtime wages are also claimed"],
        passages=[],
        query="maharashtra labour department raid kiya overtime register not maintained 11 workers",
    ) == []
    assert missing_required_authorities(
        required_sources=["Specific Relief Act 1963 where injunction/performance is sought"],
        passages=[],
        query="vendor agreed delivery in 30 days now 4 months over want to cancel and recover advance",
    ) == []


def test_stage_e9e_source_gap_accepts_bns_section_69_promise_to_marry_source():
    assert missing_required_authorities(
        required_sources=["BNS 2023 sections 63 and 69 / IPC legacy sexual-offence provisions based on incident date"],
        passages=[
            {
                "index": 1,
                "title": "Bharatiya Nyaya Sanhita 2023",
                "anchor": "bns-2023/sec-69@2024-07-01",
                "source_type": "bare_act",
            }
        ],
        query="girl filed rape case after breakup saying I promised marriage relationship for 2 years",
    ) == []


def test_stage_e9f_source_gap_skips_non_direct_aadhaar_and_unalleged_offence_requirements():
    assert missing_required_authorities(
        required_sources=["Aadhaar Act 2016 only where Aadhaar authentication or UIDAI records are directly involved"],
        passages=[],
        query="data breach at byjus my pan and aadhaar leaked can i claim compensation under DPDP act",
    ) == []

    assert missing_required_authorities(
        required_sources=["BNS 2023 / IPC 1860 offence provisions where relevant"],
        passages=[],
        query="anticipatory bail granted 30 day bombay HC police still threatening to arrest what next",
    ) == []

    assert missing_required_authorities(
        required_sources=["BNSS 2023 / CrPC 1973 only for the adult criminal-procedure wrapper after age is checked"],
        passages=[],
        query="16 yr boy detained adult jail 2 weeks already how to transfer observation home",
    ) == []


def test_stage_e9f_source_gap_accepts_bail_trafficking_and_privacy_authorities():
    assert missing_required_authorities(
        required_sources=["BNSS 2023 / CrPC 1973 bail and custody procedure based on incident date"],
        passages=[
            {
                "index": 1,
                "title": "Bharatiya Nagarik Suraksha Sanhita 2023",
                "anchor": "bnss-2023/sec-480@2024-07-01",
                "source_type": "bare_act",
            },
            {
                "index": 2,
                "title": "Code of Criminal Procedure 1973",
                "anchor": "crpc-1973/sec-439",
                "source_type": "bare_act",
            },
        ],
        query="ndps bail rejected 6 times by session court husband 3 yrs in tihar option",
    ) == []

    assert missing_required_authorities(
        required_sources=["BNSS 2023 / CrPC 1973 bail and custody procedure based on incident date"],
        passages=[
            {
                "index": 1,
                "title": "Bharatiya Nagarik Suraksha Sanhita 2023",
                "anchor": "bnss-2023/sec-483@2024-07-01",
                "source_type": "bare_act",
            },
            {
                "index": 2,
                "title": "Code of Criminal Procedure 1973",
                "anchor": "crpc-1973/sec-439",
                "source_type": "bare_act",
            },
            {
                "index": 3,
                "title": "Unlawful Activities (Prevention) Act 1967",
                "anchor": "uapa-1967/sec-43d",
                "source_type": "bare_act",
            },
        ],
        query="urgent brother in jail 18 months UAPA bail when prima facie case made out kya hota",
    ) == []

    assert missing_required_authorities(
        required_sources=["BNSS/CrPC complaint and protection procedure"],
        passages=[
            {
                "index": 1,
                "title": "Bharatiya Nagarik Suraksha Sanhita 2023",
                "anchor": "bnss-2023/sec-173-b@2024-07-01",
                "source_type": "bare_act",
            }
        ],
        query="spa customers want extra owner makes us do it if we refuse no salary how do I get out",
    ) == []

    assert missing_required_authorities(
        required_sources=["constitutional reproductive autonomy and privacy precedents"],
        passages=[
            {
                "index": 1,
                "title": "X versus THE PRINCIPAL SECRETARY HEALTH AND FAMILY WELFARE DEPARTMENT & ANR.",
                "anchor": "2022-insc-740#para-11",
                "source_type": "sc_judgment",
            }
        ],
        query="had abortion 5 yrs back husband found out and is threatening divorce can he use this in court",
    ) == []


def test_stage_e9g_source_gap_requires_mental_healthcare_for_therapist_privacy():
    required = [
        "Mental Healthcare Act 2017 for confidentiality/privacy of mental-health records or therapist communications"
    ]
    query = "someone leaked my chat with therapist on twitter mental health privacy"

    missing = missing_required_authorities(
        required_sources=required,
        passages=[
            {
                "index": 1,
                "title": "Digital Personal Data Protection Act 2023",
                "anchor": "dpdp-2023/sec-13",
                "source_type": "bare_act",
            }
        ],
        query=query,
    )
    assert missing == [
        {
            "required_source": required[0],
            "kind": "national_statute_retrieval_gap",
        }
    ]

    assert missing_required_authorities(
        required_sources=required,
        passages=[
            {
                "index": 1,
                "title": "Mental Healthcare Act 2017",
                "anchor": "mental-healthcare-2017/sec-43",
                "source_type": "bare_act",
            }
        ],
        query=query,
    ) == []


def test_mental_healthcare_confinement_accepts_confinement_safeguards():
    required = ["Mental Healthcare Act 2017"]
    query = "my brother is mentally ill and family kept him in chains how can we admit him legally"

    assert missing_required_authorities(
        required_sources=required,
        passages=[
            {
                "index": 1,
                "title": "Mental Healthcare Act 2017",
                "anchor": "mental-healthcare-2017/sec-20",
                "source_type": "bare_act",
            }
        ],
        query=query,
    ) == []


def test_stage2_source_gap_accepts_epfo_pension_composite_authority():
    required = [
        "Employees Provident Funds and Miscellaneous Provisions Act 1952 or Code on Social Security 2020 for EPFO/EPS pension scheme basis"
    ]
    query = "what to do epfo wala bol raha aadhaar mismatch pension nahi milega 4 saal se is this legal"

    assert missing_required_authorities(
        required_sources=required,
        passages=[
            {
                "index": 1,
                "title": "Employees Provident Funds and Miscellaneous Provisions Act 1952",
                "anchor": "epf-1952/sec-6A",
                "source_type": "bare_act",
            },
        ],
        query=query,
    ) == []

    for passage in [
        {
            "index": 1,
            "title": "Employees Provident Funds and Miscellaneous Provisions Act 1952",
            "anchor": "epf-1952/sec-6",
            "source_type": "bare_act",
        },
        {
            "index": 1,
            "title": "Employees Provident Funds and Miscellaneous Provisions Act 1952",
            "anchor": "epf-1952/sec-7A",
            "source_type": "bare_act",
        },
        {
            "index": 1,
            "title": "Employees Provident Funds and Miscellaneous Provisions Act 1952",
            "anchor": "epf-1952/sec-14",
            "source_type": "bare_act",
        },
        {
            "index": 1,
            "title": "Code on Social Security 2020",
            "anchor": "social-security-code-2020/sec-120",
            "source_type": "bare_act",
        },
        {
            "index": 1,
            "title": "Code on Social Security 2020",
            "anchor": "social-security-code-2020#header",
            "source_type": "bare_act",
        },
    ]:
        assert missing_required_authorities(
            required_sources=required,
            passages=[passage],
            query=query,
        ) == [{"required_source": required[0], "kind": "national_labor_source_gap"}]

    assert missing_required_authorities(
        required_sources=required,
        passages=[
            {
                "index": 1,
                "title": "Code on Social Security 2020",
                "anchor": "social-security-code-2020/sec-15",
                "source_type": "bare_act",
            },
        ],
        query=query,
    ) == []


def test_stage_e9g_source_gap_accepts_precise_repair_authorities_without_over_enforcing():
    assert missing_required_authorities(
        required_sources=["BNSS/CrPC complaint procedure"],
        passages=[],
        query="biharee called by site engineer pune always after wage complaint is this crime is this legal",
    ) == []

    assert missing_required_authorities(
        required_sources=["BNS/BNSS or IPC/CrPC based on incident date where confinement, assault, threats, or document retention are involved"],
        passages=[
            {
                "index": 1,
                "title": "Bharatiya Nyaya Sanhita 2023",
                "anchor": "bns-2023/sec-146@2024-07-01",
                "source_type": "bare_act",
            },
            {
                "index": 2,
                "title": "Bharatiya Nagarik Suraksha Sanhita 2023",
                "anchor": "bnss-2023/sec-173-b@2024-07-01",
                "source_type": "bare_act",
            },
        ],
        query="thekedar took 18000 advance from me darbhanga not letting leave bangalore site is this legal",
    ) == []

    assert missing_required_authorities(
        required_sources=["Copyright Act 1957 where creative work/logo is involved"],
        passages=[
            {
                "index": 3,
                "title": "Copyright Act 1957",
                "anchor": "copyright-1957/sec-55",
                "source_type": "bare_act",
            }
        ],
        query="got cease and desist notice from big company saying my logo similar to theirs delhi exporter",
    ) == []
