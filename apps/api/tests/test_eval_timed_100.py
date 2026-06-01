from __future__ import annotations

import json
from pathlib import Path

from scripts.eval_timed_100 import (
    answer_quality_flags,
    expected_act_cited_hit,
    expected_act_hit,
    expected_act_keys,
    expected_procedure_anchor_coverage,
    jsonl_dumps,
    load_eval_rows,
)


def test_expected_act_aliases_cover_eval_corpus_annotations():
    rows = []
    for path in sorted(Path("data/eval_500").glob("*.jsonl")):
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                rows.append(json.loads(line))

    annotated = [row for row in rows if row.get("expected_act_hint")]
    scored = [row for row in annotated if expected_act_keys(row.get("expected_act_hint"))]
    unscored = [row for row in annotated if not expected_act_keys(row.get("expected_act_hint"))]

    assert len(annotated) >= 490
    assert [row["expected_act_hint"] for row in unscored] == [
        "Prem Shankar Shukla v Delhi Admin 1980 + Citizen for Democracy v State of Assam 1995",
    ]
    assert len(scored) / len(rows) >= 0.95


def test_load_eval_rows_keeps_unicode_next_line_inside_json_string(tmp_path):
    queries_dir = tmp_path / "queries"
    queries_dir.mkdir()
    row = {
        "query": "section marker sec-88-\u0085 anchor should stay in one record",
        "expected_category": "court_procedure",
        "expected_act_hint": "CPC",
    }
    (queries_dir / "procedural.jsonl").write_text(
        json.dumps(row, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    rows = load_eval_rows(queries_dir, limit=10, seed=1)

    assert len(rows) == 1
    assert rows[0]["persona"] == "procedural"
    assert rows[0]["query"] == "section marker sec-88-\u0085 anchor should stay in one record"


def test_jsonl_dumps_escapes_unicode_line_separators():
    dumped = jsonl_dumps({
        "query": "section marker sec-88-\u0085 and line\u2028paragraph\u2029",
    })

    assert "\u0085" not in dumped
    assert "\u2028" not in dumped
    assert "\u2029" not in dumped
    assert "\\u0085" in dumped
    assert "\\u2028" in dumped
    assert "\\u2029" in dumped


def test_expected_act_aliases_cover_human_like_mixed_hints():
    hints = {
        "MSMED Act 2006 s.15 s.16 s.17 + MSME Samadhan": "MSMED Act",
        "Water (Prevention and Control of Pollution) Act 1974": "Water Act",
        "ed tech company director received PMLA summons": "PMLA",
        "Rajasthan Shops & Commercial Establishments Act": "Shops and Establishments Act",
        "Article 21 handcuffing safeguards + Prem Shankar Shukla v Delhi Admin 1980": "Article 21",
    }

    for hint, expected in hints.items():
        assert expected in expected_act_keys(hint)


def test_expected_act_hit_requires_all_recognized_required_acts():
    keys = expected_act_keys("POCSO + JJ Act")

    assert expected_act_hit(
        keys,
        [{"title": "Protection of Children from Sexual Offences Act 2012"}],
        [],
    ) is False
    assert expected_act_hit(
        keys,
        [
            {"title": "Protection of Children from Sexual Offences Act 2012"},
            {"title": "Juvenile Justice (Care and Protection of Children) Act 2015"},
        ],
        [],
    ) is True


def test_expected_act_cited_hit_requires_used_citation_not_just_passage_presence():
    keys = expected_act_keys("BNS")
    sources = [
        {"index": 1, "title": "Protection of Women from Domestic Violence Act 2005"},
        {"index": 2, "title": "Bharatiya Nyaya Sanhita 2023"},
    ]

    assert expected_act_hit(keys, sources, []) is True
    assert expected_act_cited_hit(
        keys,
        sources,
        [],
        [{"text": "Use the domestic-violence remedy [1].", "status": "ok"}],
    ) is False
    assert expected_act_cited_hit(
        keys,
        sources,
        [],
        [{"text": "Check the criminal breach-of-trust provision [2].", "status": "ok"}],
    ) is True


def test_expected_procedure_anchor_coverage_requires_all_cited_subparts():
    keys = expected_act_keys("Gazette notification process")
    sources = [
        {
            "index": 1,
            "title": "Department of Publication Guidelines for Change of Name Adult Major",
            "anchor": "deptpub-name-change-adult-guidelines#adult-required-documents",
            "source_type": "circular",
        },
        {
            "index": 2,
            "title": "Department of Publication Guidelines for Change of Name Adult Major",
            "anchor": "deptpub-name-change-adult-guidelines#adult-formalities",
            "source_type": "circular",
        },
        {
            "index": 3,
            "title": "Department of Publication Guidelines for Change of Name Adult Major",
            "anchor": "deptpub-name-change-adult-guidelines#egazette-download-and-submission",
            "source_type": "circular",
        },
    ]

    partial = expected_procedure_anchor_coverage(
        keys,
        sources,
        [],
        [{"text": "Use the Gazette route with formalities [2].", "status": "ok"}],
    )["Gazette Name Change Procedure"]
    assert partial["present_ok"] is True
    assert partial["cited_ok"] is False
    assert partial["missing_cited"] == [
        "deptpub-name-change-adult-guidelines#adult-required-documents",
        "deptpub-name-change-adult-guidelines#egazette-download-and-submission",
    ]

    complete = expected_procedure_anchor_coverage(
        keys,
        sources,
        [],
        [{"text": "Use documents [1], formalities [2], and eGazette download [3].", "status": "ok"}],
    )["Gazette Name Change Procedure"]
    assert complete["present_ok"] is True
    assert complete["cited_ok"] is True

    exact_anchor_wrong_type = expected_procedure_anchor_coverage(
        keys,
        [
            {
                "index": 1,
                "title": "Department of Publication Guidelines for Change of Name Adult Major",
                "anchor": "deptpub-name-change-adult-guidelines#adult-required-documents",
                "source_type": "circular",
            },
            {
                "index": 2,
                "title": "Department of Publication Guidelines for Change of Name Adult Major",
                "anchor": "deptpub-name-change-adult-guidelines#adult-formalities",
                "source_type": "hc_judgment",
            },
            {
                "index": 3,
                "title": "Department of Publication Guidelines for Change of Name Adult Major",
                "anchor": "deptpub-name-change-adult-guidelines#egazette-download-and-submission",
                "source_type": "sc_judgment",
            },
        ],
        [],
        [{"text": "Use all three [1] [2] [3].", "status": "ok"}],
    )["Gazette Name Change Procedure"]
    assert exact_anchor_wrong_type["present_ok"] is False
    assert exact_anchor_wrong_type["cited_ok"] is False
    assert exact_anchor_wrong_type["missing_cited"] == [
        "deptpub-name-change-adult-guidelines#adult-formalities",
        "deptpub-name-change-adult-guidelines#egazette-download-and-submission",
    ]


def test_jj_age_hint_requires_section_9_and_94_citations():
    keys = expected_act_keys("JJ Act 2015 s.9 + s.94 age determination")
    assert "Juvenile Justice Act" in keys
    assert "JJ Age Determination Procedure" in keys

    sources = [
        {
            "index": 1,
            "title": "Juvenile Justice (Care and Protection of Children) Act 2015",
            "anchor": "jj-2015/sec-9",
            "source_type": "bare_act",
        },
        {
            "index": 2,
            "title": "Juvenile Justice (Care and Protection of Children) Act 2015",
            "anchor": "jj-2015/sec-94",
            "source_type": "bare_act",
        },
    ]
    assert expected_act_hit(keys, sources, []) is True
    assert expected_act_cited_hit(
        keys,
        sources,
        [],
        [{"text": "Court inquiry is under JJ Act section 9 [1].", "status": "ok"}],
    ) is False
    assert expected_act_cited_hit(
        keys,
        sources,
        [],
        [{"text": "Use the court inquiry and age-document process [1][2].", "status": "ok"}],
    ) is True

    coverage = expected_procedure_anchor_coverage(
        keys,
        sources,
        [],
        [{"text": "Use both procedure sources [1][2].", "status": "ok"}],
    )["JJ Age Determination Procedure"]
    assert coverage["present_ok"] is True
    assert coverage["cited_ok"] is True

    wrong_type = expected_procedure_anchor_coverage(
        keys,
        [
            {
                "index": 1,
                "title": "Juvenile Justice (Care and Protection of Children) Act 2015",
                "anchor": "jj-2015/sec-9",
                "source_type": "hc_judgment",
            },
            {
                "index": 2,
                "title": "Juvenile Justice (Care and Protection of Children) Act 2015",
                "anchor": "jj-2015/sec-94",
                "source_type": "bare_act",
            },
        ],
        [],
        [{"text": "Use both procedure sources [1][2].", "status": "ok"}],
    )["JJ Age Determination Procedure"]
    assert wrong_type["present_ok"] is False
    assert wrong_type["cited_ok"] is False
    assert wrong_type["missing_cited"] == ["jj-2015/sec-9"]


def test_expected_act_aliases_cover_panchayat_and_cooperative_titles():
    assert expected_act_hit(
        expected_act_keys("Panchayati Raj Act / state Gram Panchayat Act"),
        [{"title": "VILLAGE PANCHAYAT, CALANGUTE versus THE ADDITIONAL DIRECTOR OF PANCHAYAT-II"}],
        [],
    ) is False
    assert expected_act_hit(
        expected_act_keys("Maharashtra Cooperative Societies Act"),
        [{"title": "BOMBAY CATHOLIC CO-OPERATIVE HOUSING SOCIETY LTD."}],
        [],
    ) is False
    assert expected_act_hit(
        expected_act_keys("Maharashtra Cooperative Societies Act"),
        [{"title": "Maharashtra Co-operative Societies Act 1960", "source_type": "bare_act"}],
        [],
    ) is True


def test_answer_quality_flags_catches_dangling_and_non_actionable_next_steps():
    assert "dangling_next_step_header" in answer_quality_flags({
        "answer_text": "**Short answer** This is covered [1]. **What you can do next**",
        "expected_act_cited_hit": True,
    })
    flags = answer_quality_flags({
        "answer_text": "**What you can do next** The provided passages do not state a concrete next step.",
        "expected_act_cited_hit": False,
    })
    assert {"no_concrete_next_step", "expected_act_not_cited"} <= set(flags)
    procedure_flags = answer_quality_flags({
        "answer_text": "**Short answer** Use the Gazette route [1]. **What you can do next** Prepare papers [1].",
        "expected_act_cited_hit": True,
        "expected_procedure_anchor_coverage": {
            "Gazette Name Change Procedure": {"cited_ok": False},
        },
    })
    assert "expected_procedure_anchors_not_cited" in procedure_flags
    richer_flags = answer_quality_flags({
        "answer_text": "**Short answer** This is covered [1].",
        "expected_act_cited_hit": True,
        "suppressed_count": 1,
        "ok_sentences": 0,
    })
    assert {"missing_next_step_section", "suppressed_sentences", "zero_ok_legal_sentences"} <= set(richer_flags)

    regime_flags = answer_quality_flags({
        "answer_text": "**Short answer** Use the BNS hurt route [1]. **What you can do next** File the complaint [1].",
        "expected_act_cited_hit": True,
        "legal_regime": "incident_date_needed_for_bns_bnss_bsa_vs_ipc_crpc",
        "ok_sentences": 2,
    })
    assert "missing_criminal_regime_caveat" in regime_flags

    weak_caveat = answer_quality_flags({
        "answer_text": "**Short answer** Incident date noted. Use the BNS hurt route [1]. **What you can do next** File the complaint [1].",
        "expected_act_cited_hit": True,
        "legal_regime": "incident_date_needed_for_bns_bnss_bsa_vs_ipc_crpc",
        "ok_sentences": 2,
    })
    assert "missing_criminal_regime_caveat" in weak_caveat

    caveated = answer_quality_flags({
        "answer_text": "**Short answer** Use the BNS hurt route, but the incident date decides BNS/BNSS versus IPC/CrPC framing [1]. **What you can do next** File the complaint [1].",
        "expected_act_cited_hit": True,
        "legal_regime": "incident_date_needed_for_bns_bnss_bsa_vs_ipc_crpc",
        "ok_sentences": 2,
    })
    assert "missing_criminal_regime_caveat" not in caveated


def test_expected_act_hit_uses_token_boundaries_for_short_aliases():
    assert expected_act_hit(
        ["Information Technology Act"],
        [{"title": "Maternity Benefit Act 1961"}],
        [],
    ) is False
    assert expected_act_hit(
        ["Companies Act"],
        [{"title": "Credit Information Companies Act 2005"}],
        [],
    ) is False
    assert expected_act_hit(
        ["Companies Act"],
        [{"title": "Companies Act 2013"}],
        [],
    ) is True
    assert expected_act_hit(
        ["Gazette Name Change Procedure"],
        [{"title": "Department of Publication Guidelines for Change of Name Adult Major", "source_type": "circular"}],
        [],
    ) is False
    assert expected_act_hit(
        ["Gazette Name Change Procedure"],
        [{
            "title": "Department of Publication Guidelines for Change of Name Adult Major",
            "anchor": "deptpub-name-change-adult-guidelines#adult-formalities",
            "source_type": "circular",
        }],
        [],
    ) is True
    assert expected_act_hit(
        ["Gazette Name Change Procedure"],
        [{
            "title": "Department of Publication Guidelines for Change of Name Adult Major",
            "anchor": "deptpub-name-change-adult-guidelines#adult-formalities-old",
            "source_type": "circular",
        }],
        [],
    ) is False
    assert expected_act_hit(
        ["Gazette Name Change Procedure"],
        [{
            "title": "Department of Publication Guidelines for Change of Name Adult Major",
            "anchor": "deptpub-name-change-adult-guidelines#adult-formalities",
            "source_type": "hc_judgment",
        }],
        [],
    ) is False
    assert expected_act_hit(
        ["Gazette Name Change Procedure"],
        [{
            "title": "Gazette of India notification about unrelated ministry appointment",
            "anchor": "gazette-of-india#appointment-notice",
            "source_type": "circular",
        }],
        [],
    ) is False


def test_expected_act_keys_do_not_extract_nested_longer_act_names():
    assert expected_act_keys("Credit Information Companies Act") == ["Credit Information Companies Act"]
    assert expected_act_hit(
        expected_act_keys("Credit Information Companies Act"),
        [{"title": "Credit Information Companies Act 2005"}],
        [],
    ) is True


def test_expected_act_keys_disambiguate_it_act_and_prohibition_hints():
    assert expected_act_keys("MSMED Act 2006 s.15 + IT Act s.43B(h)") == ["Income Tax Act", "MSMED Act"]
    assert "Information Technology Act" not in expected_act_keys("MSMED Act 2006 s.15 + IT Act s.43B(h)")
    assert expected_act_keys("Gazette notification process") == ["Gazette Name Change Procedure"]

    keys = expected_act_keys("Section 14 Hindu Succession Act / Dowry Prohibition Act")
    assert "Dowry Prohibition Act" in keys
    assert "Hindu Succession Act" in keys
    assert "State Excise Act" not in keys


def test_expected_act_keys_treat_bns_ipc_as_date_conditional():
    current_or_unknown = expected_act_keys(
        "NHRC Act 1993 s.12 + BNSS 2023 s.196 + BNS/IPC hurt by public servant",
        "i was undertrial 5 yrs released last week need help to file police torture case",
    )
    assert current_or_unknown == ["BNS", "BNSS", "NHRC Act"]

    legacy = expected_act_keys(
        "BNSS/BNS or CrPC/IPC based on event date",
        "police beat me in 2023 fir what ipc remedy",
    )
    assert "IPC" in legacy
    assert "CrPC" in legacy
    assert "BNS" not in legacy
    assert "BNSS" not in legacy


def test_expected_act_keys_respect_conditional_and_missing_jurisdiction_hints():
    assert expected_act_keys(
        "Bonded Labour Act 1976 + SC/ST POA Act if victim is SC/ST",
        "bonded labour my chacha working for thakur 12 years no wages just food bihar",
    ) == ["Bonded Labour Act"]
    assert expected_act_keys(
        "Bonded Labour Act 1976 + SC/ST POA Act if victim is SC/ST",
        "dalit bonded labour working for contractor no wages just food",
    ) == ["Bonded Labour Act", "SC/ST POA Act"]
    assert expected_act_keys(
        "Bonded Labour System (Abolition) Act 1976 s.4 + SC/ST POA s.3(1)(h)",
        "bonded labour my chacha working for thakur 12 years no wages just food bihar",
    ) == ["Bonded Labour Act"]
    assert expected_act_keys(
        "Bonded Labour System (Abolition) Act 1976 s.4 + SC/ST POA s.3(1)(h)",
        "dalit bonded labour working for contractor no wages just food",
    ) == ["Bonded Labour Act", "SC/ST POA Act"]
    assert expected_act_keys(
        "Bonded Labour System (Abolition) Act 1976 s.4 + SC/ST POA s.3(1)(h)",
        "bonded labour worker no wages called caste slur by landlord",
    ) == ["Bonded Labour Act"]

    assert expected_act_keys(
        "RTI Act 2005 + scheme pension rules",
        "papa ki pension 6 month se nahi aayi rti kaise file karein",
    ) == ["RTI Act"]
    assert expected_act_keys(
        "RTI Act 2005 + scheme pension rules",
        "pension scheme money stopped rti kaise file karein",
    ) == ["RTI Act"]
    assert expected_act_keys(
        "RTI Act 2005 + scheme pension rules",
        "old age pension stopped in bihar rti kaise file karein",
    ) == ["RTI Act", "State Pension Scheme"]
    assert expected_act_keys(
        "RTI Act 2005 + scheme pension rules",
        "pension stopped in bihar rti kaise file karein",
    ) == ["RTI Act", "State Pension Scheme"]
    assert expected_act_keys(
        "Indira Gandhi National Old Age Pension Scheme / Aadhaar Act 2016",
        "old age pension stopped suddenly bank says aadhaar not linked",
    ) == ["Aadhaar Act", "State Pension Scheme"]
    assert expected_act_keys(
        "Pension Rules / state widow pension scheme",
        "my husband died in army no service pension widow what papers needed",
    ) == ["Army Pension Regulations"]
    assert expected_act_keys(
        "RTI Act 2005 + scheme pension rules",
        "family pension not paid after husband died in bihar rti kaise karein",
    ) == ["RTI Act"]

    assert expected_act_keys(
        "state Prohibition / Excise Act; punishment depends on state and FIR section",
        "police caught me drinking village they saying case under prohibition law what punishment",
    ) == []
    assert expected_act_keys(
        "state Prohibition / Excise Act; punishment depends on state and FIR section",
        "police caught me under excise act what punishment",
    ) == []
    assert expected_act_keys(
        "state Prohibition / Excise Act; punishment depends on state and FIR section",
        "police caught me under state excise law what punishment",
    ) == []
    assert expected_act_keys(
        "state Prohibition / Excise Act; punishment depends on state and FIR section",
        "police caught me drinking in bihar under prohibition law what punishment",
    ) == ["State Excise Act"]
    assert expected_act_keys(
        "NDPS Act 1985 + bhang exemption state Excise Acts",
        "vit student caught with bhang lassi in mahabaleshwar holi is it ndps",
    ) == ["NDPS Act", "State Excise Act"]
    assert expected_act_keys(
        "RBI guidelines / Right to Education Act 2009",
        "bank not giving education loan to my daughter even though we have scholarship paper",
    ) == ["Banking Ombudsman"]
    assert expected_act_keys(
        "state Prohibition / Excise Act; punishment depends on state and FIR section",
        "police caught me drinking in odisha under excise law what punishment",
    ) == ["State Excise Act"]


def test_expected_act_keys_require_social_security_and_separate_bocw_from_cess():
    keys = expected_act_keys("Code on Social Security 2020 + Motor Vehicles Act 1988")
    assert "Social Security Code" in keys
    assert "Motor Vehicles Act" in keys
    assert expected_act_hit(keys, [{"title": "Motor Vehicles Act 1988"}], []) is False

    keys = expected_act_keys("BOCW Cess Act 1996 s.3 + BOCW Act 1996 s.13 s.14")
    assert "BOCW Act" in keys
    assert "BOCW Cess Act" in keys
    assert expected_act_hit(
        keys,
        [{"title": "Building and Other Construction Workers Welfare Cess Act 1996"}],
        [],
    ) is False
    assert expected_act_hit(
        keys,
        [
            {"title": "Building and Other Construction Workers Welfare Cess Act 1996"},
            {"title": "Building and Other Construction Workers (Regulation of Employment and Conditions of Service) Act 1996"},
        ],
        [],
    ) is True


def test_expected_act_hit_accepts_local_doc_ids_and_hyphenated_titles():
    assert expected_act_hit(
        expected_act_keys("Income Tax Act section 206C"),
        [{"title": "Income-tax Act 1961", "anchor": "income-tax-1961/sec-206C"}],
        [],
    ) is True
    assert expected_act_hit(
        expected_act_keys("CGST Rules 2017 Rule 86B"),
        [{"title": "Central Goods and Services Tax Rules 2017", "anchor": "cgst-rules-2017/rule-86B"}],
        [],
    ) is True
    assert expected_act_hit(
        expected_act_keys("UAPA 1967 s.43D(5)"),
        [{"title": "Unlawful Activities (Prevention) Act 1967", "anchor": "uapa-1967/sec-43D"}],
        [],
    ) is True
    assert expected_act_hit(
        expected_act_keys("Protection of Civil Rights Act 1955 temple entry"),
        [{"title": "Protection of Civil Rights Act 1955", "anchor": "protection-civil-rights-1955/sec-4"}],
        [],
    ) is True
    assert expected_act_hit(
        expected_act_keys("Environment Protection Act 1986 pollution"),
        [{"title": "Environment (Protection) Act 1986", "anchor": "environment-protection-1986/sec-7"}],
        [],
    ) is True
    assert expected_act_hit(
        expected_act_keys("RBI Ombudsman fair practices complaint"),
        [{"title": "Reserve Bank Integrated Ombudsman Scheme 2021", "anchor": "rbi-integrated-ombudsman-2021/clause-9"}],
        [],
    ) is True
    assert expected_act_hit(
        expected_act_keys("Credit Information Companies Act CIBIL correction"),
        [{"title": "Credit Information Companies (Regulation) Act 2005", "anchor": "credit-information-companies-2005/sec-21"}],
        [],
    ) is True
    assert expected_act_hit(
        expected_act_keys("NHRC Act custodial torture complaint"),
        [{"title": "Protection of Human Rights Act 1993", "anchor": "protection-human-rights-1993/sec-12"}],
        [],
    ) is True
    assert expected_act_hit(
        expected_act_keys("Assam Witch Hunting (Prohibition Prevention and Protection) Act 2015"),
        [{"title": "Assam Witch Hunting (Prohibition, Prevention and Protection) Act 2015", "anchor": "assam-witch-hunting-2015/sec-4"}],
        [],
    ) is True
    assert expected_act_hit(
        expected_act_keys("Scheduled Areas Land Transfer Regulation / CNT Act"),
        [{"title": "Chota Nagpur Tenancy Act 1908", "anchor": "chota-nagpur-tenancy-1908/sec-46"}],
        [],
    ) is True
    assert expected_act_hit(
        expected_act_keys("National Rural Health Mission guidelines ASHA incentives"),
        [{"title": "National Health Mission ASHA Incentives Guidelines 2025", "anchor": "nhm-asha-incentives-2025/page-1"}],
        [],
    ) is True
    assert expected_act_hit(
        expected_act_keys("Article 21 prison medical care"),
        [{"title": "Constitution of India", "anchor": "/sec-21"}],
        [],
    ) is True
    assert expected_act_hit(
        expected_act_keys("Article 21 prison medical care"),
        [
            {"title": "Constitution of India", "anchor": "/sec-39A"},
            {"title": "Legal Services Authorities Act 1987", "anchor": "/sec-21"},
        ],
        [],
    ) is False
    assert expected_act_hit(
        expected_act_keys("Public Gambling Act"),
        [{"title": "Tamil Nadu Prohibition of Online Gambling and Regulation of Online Games Act 2022", "anchor": "tamil-nadu-online-gambling-2022/sec-7"}],
        [],
    ) is False
    assert expected_act_hit(
        expected_act_keys("Public Gambling Act"),
        [{"title": "The Public Gambling Act, 1867", "anchor": "public-gambling-1867/sec-12"}],
        [],
    ) is True


def test_expected_act_hit_does_not_count_cases_or_successor_laws_as_acts():
    assert expected_act_keys("Prem Shankar Shukla v Delhi Admin 1980") == []
    assert expected_act_keys("CGST Rules 2017 Rule 86B") == ["CGST Rules"]
    assert expected_act_hit(
        expected_act_keys("CGST Rules 2017 Rule 86B"),
        [{"title": "Central Goods and Services Tax Act 2017", "anchor": "cgst-2017/sec-49"}],
        [],
    ) is False
    assert expected_act_hit(
        expected_act_keys("Central Goods and Services Tax Act 2017"),
        [{"title": "Central Goods and Services Tax Rules 2017", "anchor": "cgst-rules-2017/rule-86B"}],
        [],
    ) is False
    assert expected_act_hit(
        expected_act_keys("Indian Evidence Act 1872"),
        [{"title": "Bharatiya Sakshya Adhiniyam 2023", "anchor": "sakshya-adhiniyam-2023/sec-2"}],
        [],
    ) is False
    assert expected_act_hit(
        expected_act_keys("MV Act 1988 s.74"),
        [{"title": "TheMotorVehiclesAct,1988", "anchor": "motor-vehicles-1988/sec-74-a"}],
        [],
    ) is True
    assert expected_act_hit(
        expected_act_keys("IT Act 2000 s.66C + Telecom Act 2023"),
        [
            {"title": "Information Technology Act 2000", "anchor": "it-2000/sec-66C"},
            {"title": "Telecommunications Act 2023", "anchor": "telecommunications-2023/sec-42"},
        ],
        [],
    ) is True


def test_expected_act_hit_accepts_apostrophe_in_employees_compensation_title():
    assert expected_act_hit(
        expected_act_keys("Employees Compensation Act"),
        [{"title": "Employees' Compensation Act 1923", "anchor": "employees-compensation-1923/sec-3"}],
        [],
    ) is True
