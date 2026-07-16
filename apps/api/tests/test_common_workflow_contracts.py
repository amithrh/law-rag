import json
from types import SimpleNamespace

from apps.api.authority_graph import authority_graph_workflow_event
from apps.api.common_workflow_contracts import (
    WorkflowTemplateResult,
    common_workflow_contract_diagnostics,
    common_workflow_contract_result,
    common_workflow_contract_template_lines,
    workflow_contract_preempts_legacy,
    workflow_contract_promotes_verifier,
)
from apps.api.main import (
    _actionable_source_intro_line_for_sentence,
    _answer_contract_lines,
    _first_actionable_source_for_route,
    _grounded_template_lines,
    _is_safe_template_next_step,
    _is_safe_template_source_bridge,
    _legacy_template_preempts_workflow,
    _promote_reviewed_workflow_contract_line,
    _prompt_retrieval_candidates,
    _promote_safe_route_next_step,
    _reviewed_workflow_relevance_result,
    _workflow_diagnostics_event,
)
from apps.api.matter_router import route_matter
from apps.api.legal_issue_plan import build_matter_plan
from apps.api.relevance import RelevanceResult, RelevanceVerdict
from apps.api.verifier import SentenceStatus, SentenceVerification


def _joined(query: str, passages: list[dict]) -> str:
    return " ".join(common_workflow_contract_template_lines(query, route_matter(query), passages))


def _grounded_joined(query: str, passages: list[dict]) -> str:
    return " ".join(_grounded_template_lines(query, route_matter(query), passages))


def _workflow_id(query: str, passages: list[dict]) -> str | None:
    event = authority_graph_workflow_event(query, route_matter(query), passages)
    return event["id"] if event else None


RBI_OMBUDSMAN_SOURCES = [
    {"index": 1, "title": "Reserve Bank Integrated Ombudsman Scheme 2021", "anchor": "rbi-integrated-ombudsman-2021/sec-1"},
    {"index": 2, "title": "Reserve Bank Integrated Ombudsman Scheme 2021", "anchor": "rbi-integrated-ombudsman-2021/sec-3"},
    {"index": 3, "title": "Reserve Bank Integrated Ombudsman Scheme 2021", "anchor": "rbi-integrated-ombudsman-2021/sec-6"},
    {"index": 4, "title": "Reserve Bank Integrated Ombudsman Scheme 2021", "anchor": "rbi-integrated-ombudsman-2021/sec-9"},
    {"index": 5, "title": "Reserve Bank Integrated Ombudsman Scheme 2021", "anchor": "rbi-integrated-ombudsman-2021/sec-10"},
]
LOAN_APP_REGULATORY_SOURCES = [
    {"index": 6, "title": "Reserve Bank of India (Digital Lending) Directions, 2025", "anchor": "rbi-digital-lending-directions-2025/para-11"},
    {"index": 7, "title": "Reserve Bank of India (Digital Lending) Directions, 2025", "anchor": "rbi-digital-lending-directions-2025/para-12"},
    {"index": 8, "title": "Outsourcing of Financial Services - Responsibilities of regulated entities employing Recovery Agents", "anchor": "rbi-recovery-agents-2022/para-2"},
    *RBI_OMBUDSMAN_SOURCES,
]


def test_stage_goal_exact_answer_contracts_cover_ndps_and_user_terms():
    ndps = _grounded_joined(
        "need help, husband in arthur road 4 mnths ndps commercial 25 kg ganja no chargesheet bail possible what next",
        [
            {"index": 1, "title": "Code of Criminal Procedure 1973", "anchor": "crpc-1973/sec-167-b"},
            {"index": 2, "title": "Narcotic Drugs and Psychotropic Substances Act 1985", "anchor": "ndps-1985/sec-36A"},
        ],
    )
    assert "Section 36A" in ndps
    assert "CrPC default-bail source" in ndps
    assert "prior bail orders [1]" in ndps

    lic = _grounded_joined(
        "pls tell lic agent told my father guaranteed return now policy matured got half amount fraud need lawyer or police",
        [
            {"index": 1, "title": "Insurance Ombudsman Rules 2017", "anchor": "insurance-ombudsman-rules-2017/sec-5-h"},
            {"index": 2, "title": "Consumer Protection Act 2019", "anchor": "consumer-protection-2019/sec-2"},
        ],
    )
    assert "elder fraud" in lic
    assert "suspected fraud/mis-selling" in lic

    noncompete = _grounded_joined(
        "i am confused non compete clause in my employment contract for 2 years is it enforceable in india pls guide",
        [{"index": 3, "title": "Indian Contract Act 1872", "anchor": "indian-contract-1872/sec-27"}],
    )
    assert "employer legal notice" in noncompete

    ppirp = _grounded_joined(
        "hi, msme pre pack insolvency how to use against my own company 1.4 cr debt avoiding nclt full process can i file case",
        [{"index": 3, "title": "Insolvency and Bankruptcy Code 2016", "anchor": "ibc-2016/sec-54A-a"}],
    )
    assert "recovery question" in ppirp
    assert "pre-pack recovery and restructuring file" in ppirp


def _workflow_event_payload(query: str, passages: list[dict], lines: list[str]) -> dict:
    event = _workflow_diagnostics_event(
        query,
        route_matter(query),
        passages,
        template_lines=lines,
    )
    return json.loads(event["data"])


def test_common_workflow_contract_handles_bank_debit_and_freeze():
    debit = _joined(
        "bank deducted money wrongly and customer care not helping",
        RBI_OMBUDSMAN_SOURCES,
    )
    assert "wrong debit" in debit
    assert "RBI Ombudsman/CMS" in debit
    assert "transaction ID/RRN" in debit
    assert "Clause 10" in debit
    assert "Consumer Protection Act" not in debit

    freeze = _joined(
        "salary account blocked by lien after cyber complaint no notice",
        [
            {"index": 1, "title": "Reserve Bank Integrated Ombudsman Scheme 2021", "anchor": "rbi-integrated-ombudsman-2021/sec-2"},
            {"index": 2, "title": "Banking Regulation Act 1949", "anchor": "banking-regulation-1949/sec-35A"},
            {"index": 3, "title": "Bharatiya Nagarik Suraksha Sanhita 2023", "anchor": "bnss-2023/sec-106"},
            {"index": 4, "title": "Information Technology Act 2000", "anchor": "it-2000/sec-66D"},
        ],
    )
    assert "frozen, blocked, or lien-marked" in freeze
    assert "cyber/police complaint" in freeze
    assert "originating request/reference and order copy" in freeze
    assert "Keep the IT Act source only" not in freeze

    freeze_after_identity_theft = _joined(
        "salary account blocked by lien after identity theft and cyber complaint",
        [
            {"index": 1, "title": "Reserve Bank Integrated Ombudsman Scheme 2021", "anchor": "rbi-integrated-ombudsman-2021/sec-2"},
            {"index": 2, "title": "Bharatiya Nagarik Suraksha Sanhita 2023", "anchor": "bnss-2023/sec-106"},
            {"index": 3, "title": "Information Technology Act 2000", "anchor": "it-2000/sec-66D"},
        ],
    )
    assert "Keep the IT Act source only" in freeze_after_identity_theft

    cyber_freeze = _joined(
        "salary account blocked by lien after cyber complaint i dont know the case",
        [
            {"index": 1, "title": "Reserve Bank Integrated Ombudsman Scheme 2021", "anchor": "rbi-integrated-ombudsman-2021/sec-2"},
            {"index": 2, "title": "Bharatiya Nagarik Suraksha Sanhita 2023", "anchor": "bnss-2023/sec-106"},
            {"index": 3, "title": "Banking Regulation Act 1949", "anchor": "banking-regulation-1949/sec-35A"},
        ],
    )
    assert "written freeze/lien reason" in cyber_freeze
    assert "request/reference or order copy" in cyber_freeze
    assert "exact freeze date" in cyber_freeze
    assert "does not by itself prove" in cyber_freeze
    assert "Use RBI Scheme clauses 9 and 10" not in cyber_freeze

    maintenance_charge = _joined(
        "bank deducted maintenance charge twice and branch is not giving complaint number",
        RBI_OMBUDSMAN_SOURCES,
    )
    assert "wrong deduction" in maintenance_charge
    assert "RBI Ombudsman/CMS" in maintenance_charge
    assert "complaint number" in maintenance_charge

    gpay = _joined(
        "GPay showed payment failed but amount debited from bank, both sides are blaming each other",
        RBI_OMBUDSMAN_SOURCES,
    )
    assert "GPay" in gpay
    assert "RBI Ombudsman/CMS" in gpay
    assert "transaction" in gpay

    ed_hold = _joined(
        "ED freeze marked on my current account, bank only says legal hold, how to get order copy",
        [
            {"index": 1, "title": "Reserve Bank Integrated Ombudsman Scheme 2021", "anchor": "rbi-integrated-ombudsman-2021/sec-2"},
            {"index": 2, "title": "Bharatiya Nagarik Suraksha Sanhita 2023", "anchor": "bnss-2023/sec-106"},
            {"index": 3, "title": "Information Technology Act 2000", "anchor": "it-2000/sec-66D"},
        ],
    )
    assert "legal hold" in ed_hold
    assert "written freeze/lien reason" in ed_hold
    assert "police or court reference" in ed_hold


def test_common_workflow_contract_diagnostics_explain_selection_and_miss():
    debit_passages = RBI_OMBUDSMAN_SOURCES

    selected = common_workflow_contract_diagnostics(
        "ATM cash not dispensed but account debited branch not helping",
        route_matter("ATM cash not dispensed but account debited branch not helping"),
        debit_passages,
    )
    assert selected["id"] == "wrong_bank_debit"
    assert selected["selected"] is True
    assert selected["contract_miss_reason"] is None

    missed = common_workflow_contract_diagnostics(
        "what is limitation act",
        route_matter("what is limitation act"),
        [],
    )
    assert missed["selected"] is False
    assert missed["contract_miss_reason"] in {"no_passages", "generic_route_no_contract"}


def test_stage_e8_failure_workflows_preempt_blank_or_legacy_answers():
    political = common_workflow_contract_result(
        "deepfake of modi pm posted by public account bjp it cell threatening police case what to do",
        route_matter("deepfake of modi pm posted by public account bjp it cell threatening police case what to do"),
        [
            {"index": 1, "title": "Information Technology Act 2000", "anchor": "it-2000/sec-66D"},
            {"index": 2, "title": "Bharatiya Nyaya Sanhita 2023", "anchor": "bns-2023/sec-356"},
            {"index": 3, "title": "Bharatiya Nagarik Suraksha Sanhita 2023", "anchor": "bnss-2023/sec-173"},
            {"index": 4, "title": "Representation of the People Act 1951", "anchor": "rpa-1951/sec-123-d"},
        ],
    )
    assert political is not None
    assert political.id == "public_political_meme_police_risk"
    assert political.answer_mode == "primary"
    assert "public-political" in " ".join(political.lines)
    assert "Representation of the People Act election-law lane" in " ".join(political.lines)

    political_without_bns = common_workflow_contract_result(
        "police notice for political meme/deepfake of MLA on whatsapp",
        route_matter("police notice for political meme/deepfake of MLA on whatsapp"),
        [
            {"index": 1, "title": "Information Technology Act 2000", "anchor": "it-2000/sec-66E"},
            {"index": 2, "title": "Bharatiya Nagarik Suraksha Sanhita 2023", "anchor": "bnss-2023/sec-175"},
        ],
    )
    assert political_without_bns is not None
    assert political_without_bns.id == "public_political_meme_police_risk"
    assert political_without_bns.answer_mode == "primary"
    assert "do not assume a normal meme automatically means arrest" in " ".join(political_without_bns.lines)

    ndps_parcel = common_workflow_contract_result(
        "police caught my drug parcel at airport no fake call no money demand what punishment",
        route_matter("police caught my drug parcel at airport no fake call no money demand what punishment"),
        [
            {"index": 1, "title": "Bharatiya Nagarik Suraksha Sanhita 2023", "anchor": "bnss-2023/sec-483"},
            {"index": 2, "title": "Narcotic Drugs and Psychotropic Substances Act 1985", "anchor": "ndps-1985/sec-22-a"},
        ],
    )
    assert ndps_parcel is not None
    assert ndps_parcel.id == "ndps_quantity_bail"
    assert ndps_parcel.answer_mode == "primary"
    assert "classify the substance and quantity" in " ".join(ndps_parcel.lines)

    nrega = common_workflow_contract_result(
        "nrega 28 days work done village mukhiya not paid since 6 months gadchiroli maharashtra pls guide",
        route_matter("nrega 28 days work done village mukhiya not paid since 6 months gadchiroli maharashtra pls guide"),
        [
            {"index": 1, "title": "Mahatma Gandhi National Rural Employment Guarantee Act 2005", "anchor": "mgnrega-2005/sec-19"},
            {"index": 2, "title": "Right to Information Act 2005", "anchor": "rti-2005/sec-6"},
        ],
    )
    assert nrega is not None
    assert nrega.id == "mgnrega_fake_muster"
    assert nrega.answer_mode == "primary"
    assert "wage-payment" in " ".join(nrega.lines)

    msme = common_workflow_contract_result(
        "buyer deducting payment saying quality issue but no formal rejection given 9 lakh stuck",
        route_matter("buyer deducting payment saying quality issue but no formal rejection given 9 lakh stuck"),
        [
            {"index": 1, "title": "Micro, Small and Medium Enterprises Development Act 2006", "anchor": "msmed-2006/sec-18"},
            {"index": 2, "title": "Sale of Goods Act 1930", "anchor": "sale-of-goods-1930/sec-55"},
            {"index": 3, "title": "Indian Contract Act 1872", "anchor": "indian-contract-1872/sec-37"},
        ],
    )
    assert msme is not None
    assert msme.id == "msme_delayed_payment"
    assert msme.answer_mode == "primary"
    assert "quality issue" in " ".join(msme.lines)

    pocso = common_workflow_contract_result(
        "my 14 year old girlfriend's father filed pocso on me I am 17 we were in relationship she came on her own",
        route_matter("my 14 year old girlfriend's father filed pocso on me I am 17 we were in relationship she came on her own"),
        [
            {"index": 1, "title": "Protection of Children from Sexual Offences Act 2012", "anchor": "pocso-2012/sec-33-b"},
            {"index": 2, "title": "Juvenile Justice (Care and Protection of Children) Act 2015", "anchor": "jj-2015/sec-94"},
            {"index": 3, "title": "Bharatiya Nagarik Suraksha Sanhita 2023", "anchor": "bnss-2023/sec-480"},
        ],
    )
    assert pocso is not None
    assert pocso.id == "pocso_minor_romantic_accused"
    assert pocso.answer_mode == "safety_primary"
    pocso_text = " ".join(pocso.lines)
    assert "do not rely on 'relationship'" in pocso_text
    assert "DLSA" in pocso_text


def test_target_failure_workflows_own_user_shaped_answers():
    cyber = common_workflow_contract_result(
        "stalker on insta sending dm daily even after blocking how to file complaint",
        route_matter("stalker on insta sending dm daily even after blocking how to file complaint"),
        [
            {"index": 1, "title": "Bharatiya Nyaya Sanhita 2023", "anchor": "bns-2023/sec-78"},
            {"index": 2, "title": "Information Technology Act 2000", "anchor": "it-2000/sec-66E"},
            {"index": 3, "title": "Bharatiya Nagarik Suraksha Sanhita 2023", "anchor": "bnss-2023/sec-173"},
        ],
    )
    assert cyber is not None
    assert cyber.id == "cyber_stalking_online_harassment"
    assert cyber.answer_mode == "primary"
    cyber_text = " ".join(cyber.lines)
    assert "do not say BNSS defines stalking" in cyber_text
    assert "cybercrime.gov.in" in cyber_text

    abuse = common_workflow_contract_result(
        "instagram comments calling me randi defamation kya kar sakti hu",
        route_matter("instagram comments calling me randi defamation kya kar sakti hu"),
        [
            {"index": 1, "title": "Bharatiya Nyaya Sanhita 2023", "anchor": "bns-2023/sec-356-a"},
            {"index": 2, "title": "Information Technology Act 2000", "anchor": "it-2000/sec-66E"},
            {"index": 3, "title": "Bharatiya Nagarik Suraksha Sanhita 2023", "anchor": "bnss-2023/sec-173"},
        ],
    )
    assert abuse is not None
    assert abuse.id == "online_defamation_abuse"
    assert abuse.answer_mode == "primary"
    abuse_text = " ".join(abuse.lines)
    assert "abusive Instagram comments" in abuse_text
    assert "exact words" in abuse_text

    adoption = common_workflow_contract_result(
        "what to do we adopted child from sister but no papers now real parents want him back is this legal",
        route_matter("what to do we adopted child from sister but no papers now real parents want him back is this legal"),
        [
            {"index": 1, "title": "Hindu Adoptions and Maintenance Act 1956", "anchor": "hindu-adoptions-maintenance-1956/sec-6-a"},
            {"index": 2, "title": "Juvenile Justice (Care and Protection of Children) Act 2015", "anchor": "jj-2015/sec-56"},
            {"index": 3, "title": "Guardians and Wards Act 1890", "anchor": "guardians-wards-1890/sec-17"},
        ],
    )
    assert adoption is not None
    assert adoption.id == "relative_adoption_no_papers"
    assert adoption.answer_mode == "primary"
    adoption_text = " ".join(adoption.lines)
    assert "no papers" in adoption_text
    assert "biological/real parents" in adoption_text

    traffic = common_workflow_contract_result(
        "please help auto driver bangalore traffic police taking 500 every week no challan saying tamil license invalid any remedy",
        route_matter("please help auto driver bangalore traffic police taking 500 every week no challan saying tamil license invalid any remedy"),
        [
            {"index": 1, "title": "TheMotorVehiclesAct,1988", "anchor": "motor-vehicles-1988/sec-3"},
            {"index": 2, "title": "Prevention of Corruption Act 1988", "anchor": "prevention-of-corruption-1988/sec-7"},
            {"index": 3, "title": "Bharatiya Nagarik Suraksha Sanhita 2023", "anchor": "bnss-2023/sec-173"},
        ],
    )
    assert traffic is not None
    assert traffic.id == "traffic_police_challan_bribe"
    assert traffic.answer_mode == "primary"
    traffic_text = " ".join(traffic.lines)
    assert "Rs.500 or weekly cash" in traffic_text
    assert "Prevention of Corruption Act" in traffic_text

    traffic_near_miss = common_workflow_contract_result(
        "traffic police saying my tamil license invalid and issued challan what should i do",
        route_matter("traffic police saying my tamil license invalid and issued challan what should i do"),
        [
            {"index": 1, "title": "TheMotorVehiclesAct,1988", "anchor": "motor-vehicles-1988/sec-3"},
            {"index": 2, "title": "Prevention of Corruption Act 1988", "anchor": "prevention-of-corruption-1988/sec-7"},
        ],
    )
    assert traffic_near_miss is None or traffic_near_miss.id != "traffic_police_challan_bribe"


def test_critical_failure_workflows_preempt_legacy_after_review():
    cases = (
        (
            "urgent someone made fake instagram account using my photos n dms girls how to complain",
            [
                {"index": 1, "title": "Information Technology Act 2000", "anchor": "it-2000/sec-66D"},
                {"index": 2, "title": "Bharatiya Nyaya Sanhita 2023", "anchor": "bns-2023/sec-319"},
                {"index": 3, "title": "Bharatiya Nagarik Suraksha Sanhita 2023", "anchor": "bnss-2023/sec-173"},
            ],
            "cyber_stalking_online_harassment",
        ),
        (
            "instagram comments calling me randi defamation kya kar sakti hu",
            [
                {"index": 1, "title": "Bharatiya Nyaya Sanhita 2023", "anchor": "bns-2023/sec-356"},
                {"index": 2, "title": "Information Technology Act 2000", "anchor": "it-2000/sec-66E"},
                {"index": 3, "title": "Bharatiya Nagarik Suraksha Sanhita 2023", "anchor": "bnss-2023/sec-173"},
            ],
            "online_defamation_abuse",
        ),
        (
            "we adopted child from sister but no papers now real parents want him back what next",
            [
                {"index": 1, "title": "Juvenile Justice (Care and Protection of Children) Act 2015", "anchor": "jj-2015/sec-56"},
                {"index": 2, "title": "Guardians and Wards Act 1890", "anchor": "guardians-wards-1890/sec-17"},
            ],
            "relative_adoption_no_papers",
        ),
        (
            "binance froze my usdt wallet saying suspicious trade what can I do",
            [
                {"index": 1, "title": "Prevention of Money-laundering Act 2002", "anchor": "pmla-2002/sec-12"},
                {"index": 2, "title": "Consumer Protection Act 2019", "anchor": "consumer-protection-2019/sec-35"},
            ],
            "crypto_exchange_wallet",
        ),
        (
            "police not agreeing FIR for caste atrocity case saying small matter",
            [
                {"index": 1, "title": "Scheduled Castes and Scheduled Tribes (Prevention of Atrocities) Act 1989", "anchor": "sc-st-poa-1989/sec-3"},
                {"index": 2, "title": "Bharatiya Nagarik Suraksha Sanhita 2023", "anchor": "bnss-2023/sec-173"},
            ],
            "caste_access_police_refusal",
        ),
    )

    for query, passages, expected_id in cases:
        result = common_workflow_contract_result(query, route_matter(query), passages)
        assert result is not None, query
        assert result.id == expected_id, query
        assert workflow_contract_preempts_legacy(result), query


def test_poa_rule7_dsp_investigation_contract_requires_the_rules_source():
    query = "SP not transferring my atrocity case to DSP though POA Act says so where to go"
    passages = [
        {"index": 1, "title": "Scheduled Castes and Scheduled Tribes (Prevention of Atrocities) Rules 1995", "anchor": "sc-st-poa-rules-1995/rule-7"},
        {"index": 2, "title": "Scheduled Castes and Scheduled Tribes (Prevention of Atrocities) Act 1989", "anchor": "sc-st-poa-1989/sec-15A"},
        {"index": 3, "title": "Bharatiya Nagarik Suraksha Sanhita 2023", "anchor": "bnss-2023/sec-173"},
    ]

    result = common_workflow_contract_result(query, route_matter(query), passages)
    assert result is not None
    assert result.id == "poa_rule7_dsp_investigation"
    assert workflow_contract_preempts_legacy(result)
    rendered = " ".join(result.lines)
    assert "Rule 7" in rendered
    assert "do not assume" in rendered

    without_rules = common_workflow_contract_result(query, route_matter(query), passages[1:])
    assert without_rules is None or without_rules.id != "poa_rule7_dsp_investigation"


def test_mental_health_confinement_contract_requires_protection_sources():
    query = "my brother mentally ill family kept him in chains how to admit in hospital legally"
    passages = [
        {"index": 1, "title": "Mental Healthcare Act 2017", "anchor": "mental-healthcare-2017/sec-20"},
        {"index": 2, "title": "Mental Healthcare Act 2017", "anchor": "mental-healthcare-2017/sec-100-a"},
        {"index": 3, "title": "Mental Healthcare Act 2017", "anchor": "mental-healthcare-2017/sec-94"},
        {"index": 4, "title": "Mental Healthcare Act 2017", "anchor": "mental-healthcare-2017/sec-97"},
        {"index": 5, "title": "Mental Healthcare Act 2017", "anchor": "mental-healthcare-2017/sec-27"},
    ]

    result = common_workflow_contract_result(query, route_matter(query), passages)
    assert result is not None
    assert result.id == "mental_health_chain_or_confinement"
    assert result.answer_mode == "safety_primary"
    rendered = " ".join(result.lines)
    assert "must not be kept in a police lock-up or prison" in rendered
    assert "not a permission for ordinary family chaining" in rendered

    without_police = common_workflow_contract_result(query, route_matter(query), passages[:1])
    assert without_police is None or without_police.id != "mental_health_chain_or_confinement"

    negated_bribe = common_workflow_contract_result(
        "my driving license invalid on portal no bribe no challan how fix",
        route_matter("my driving license invalid on portal no bribe no challan how fix"),
        [
            {"index": 1, "title": "TheMotorVehiclesAct,1988", "anchor": "motor-vehicles-1988/sec-3"},
            {"index": 2, "title": "Prevention of Corruption Act 1988", "anchor": "prevention-of-corruption-1988/sec-7"},
        ],
    )
    assert negated_bribe is None or negated_bribe.id != "traffic_police_challan_bribe"

    manual = common_workflow_contract_result(
        "can u tell dry latrine still in our basti panchayat forcing dalit women to clean dindori what can i do",
        route_matter("can u tell dry latrine still in our basti panchayat forcing dalit women to clean dindori what can i do"),
        [
            {"index": 1, "title": "Prohibition of Employment as Manual Scavengers and their Rehabilitation Act 2013", "anchor": "manual-scavenging-2013/sec-5"},
            {"index": 2, "title": "Scheduled Castes and Scheduled Tribes (Prevention of Atrocities) Act 1989", "anchor": "sc-st-poa-1989/sec-3"},
            {"index": 3, "title": "Bharatiya Nagarik Suraksha Sanhita 2023", "anchor": "bnss-2023/sec-173"},
        ],
    )
    assert manual is not None
    assert manual.id == "manual_scavenging_forced_cleaning"
    assert manual.answer_mode == "safety_primary"
    manual_text = " ".join(manual.lines)
    assert "dry latrine" in manual_text
    assert "caste-atrocity track" in manual_text

    cross_border = common_workflow_contract_result(
        "hi, my ex husband took our son to UK on tourist visa and is not bringing back he said permanent now what to do can i file case",
        route_matter("hi, my ex husband took our son to UK on tourist visa and is not bringing back he said permanent now what to do can i file case"),
        [
            {"index": 1, "title": "Guardians and Wards Act 1890", "anchor": "guardians-wards-1890/sec-25"},
            {"index": 2, "title": "Family Courts Act 1984", "anchor": "family-courts-1984/sec-7"},
            {"index": 3, "title": "Constitution of India", "anchor": "constitution-india/sec-226"},
        ],
    )
    assert cross_border is not None
    assert cross_border.id == "child_cross_border_return"
    assert cross_border.answer_mode == "safety_primary"
    cross_border_text = " ".join(cross_border.lines)
    assert "tourist visa" in cross_border_text
    assert "child-return/custody" in cross_border_text

    shop = common_workflow_contract_result(
        "hi, labour inspector said i have to register under shop act in jaipur i have 4 staff can i file case",
        route_matter("hi, labour inspector said i have to register under shop act in jaipur i have 4 staff can i file case"),
        [
            {"index": 1, "title": "Rajasthan Shops and Commercial Establishments Act 1958", "anchor": "rajasthan-shops-establishments-1958/sec-4"},
            {"index": 2, "title": "Rajasthan Shops and Commercial Establishments Act 1958 Fee Structure and Checklist", "anchor": "rajasthan-shops-fee-checklist-2026/registration-fee-checklist"},
            {"index": 3, "title": "Food Safety and Standards Act 2006", "anchor": "food-safety-standards-2006/sec-31"},
        ],
    )
    assert shop is not None
    assert shop.id == "rajasthan_shop_act_registration"
    shop_text = " ".join(shop.lines)
    assert "start with the Rajasthan Shops" in shop_text
    assert "not FSSAI" in shop_text

    maternity = common_workflow_contract_result(
        "i was on maternity leave n when i came back my role was given to someone else",
        route_matter("i was on maternity leave n when i came back my role was given to someone else"),
        [
            {"index": 1, "title": "Maternity Benefit Act 1961", "anchor": "maternity-benefit-1961/sec-12"},
            {"index": 2, "title": "Industrial Disputes Act 1947", "anchor": "industrial-disputes-1947/sec-2A"},
        ],
    )
    assert maternity is not None
    assert maternity.id == "maternity_return_role_change"
    assert "not answer it as MGNREGA" in " ".join(maternity.lines)

    gig = common_workflow_contract_result(
        "zomato rider here met with accident on bike no insurance from company",
        route_matter("zomato rider here met with accident on bike no insurance from company"),
        [
            {"index": 1, "title": "Code on Social Security 2020", "anchor": "social-security-code-2020/sec-114-a"},
            {"index": 2, "title": "TheMotorVehiclesAct,1988", "anchor": "motor-vehicles-1988/sec-165"},
            {"index": 3, "title": "Employees' Compensation Act 1923", "anchor": "employees-compensation-1923/sec-3-a"},
        ],
    )
    assert gig is not None
    assert gig.id == "gig_delivery_accident_compensation"
    gig_text = " ".join(gig.lines)
    assert "Zomato rider accident" in gig_text
    assert "Zomato company/platform" in gig_text
    assert "MACT" in gig_text
    assert "insurance does not end the claim" in gig_text


def test_stage2_critical_refusal_families_have_reviewed_contracts():
    cases = [
        (
            "pls tell how to file zero FIR if incident happened in another state need lawyer or police",
            [
                {"index": 1, "title": "Bharatiya Nagarik Suraksha Sanhita 2023", "anchor": "bnss-2023/sec-173-b@2024-07-01"},
                {"index": 2, "title": "Code of Criminal Procedure 1973", "anchor": "crpc-1973/sec-154"},
            ],
            "police_fir_first_response",
            "safety_primary",
            ("zero-FIR", "written complaint", "SP"),
        ),
        (
            "what to do my brother beaten in lockup constable took 20000 for bail still not released is this legal",
            [
                {"index": 1, "title": "Constitution of India", "anchor": "constitution-india/sec-21"},
                {"index": 2, "title": "Protection of Human Rights Act 1993", "anchor": "protection-human-rights-1993/sec-12@1990-01-01"},
                {"index": 3, "title": "Bharatiya Nagarik Suraksha Sanhita 2023", "anchor": "bnss-2023/sec-48@2024-07-01"},
            ],
            "custody_habeas_lockup_abuse",
            "safety_primary",
            ("lockup beating", "medical evidence", "DLSA"),
        ),
        (
            "can u tell bonded labour my chacha working for thakur 12 yrs no wages just food bihar what can i do",
            [
                {"index": 1, "title": "Bonded Labour System (Abolition) Act 1976", "anchor": "bonded-labour-1976/sec-12"},
                {"index": 2, "title": "Code on Wages 2019", "anchor": "code-on-wages-2019/sec-17"},
            ],
            "bonded_labour_coercion_release",
            "safety_primary",
            ("Bonded Labour Act rescue route", "District Magistrate/SDM", "written acknowledgement"),
        ),
        (
            "urgent community forest resource claim CFR rejected by DLC how appeal odisha kandhamal how to complain",
            [
                {"index": 1, "title": "Scheduled Tribes and Other Traditional Forest Dwellers (Recognition of Forest Rights) Act 2006", "anchor": "forest-rights-act-2006/sec-6"},
                {"index": 2, "title": "Panchayats (Extension to Scheduled Areas) Act 1996", "anchor": "pesa-1996/sec-4"},
            ],
            "tribal_forest_land_access",
            "safety_primary",
            ("IFR/CFR", "SDLC/DLC", "Gram Sabha"),
        ),
        (
            "hi, husband forces me at night even when I say no I am tired or unwell is there any law fr this in india now can i file case",
            [
                {"index": 1, "title": "Protection of Women from Domestic Violence Act 2005", "anchor": "pwdva-2005/sec-3"},
                {"index": 2, "title": "Family Courts Act 1984", "anchor": "family-courts-act-1984/sec-7"},
            ],
            "family_forced_sex_safety",
            "safety_primary",
            ("sexual coercion", "domestic-violence", "immediate safety"),
        ),
        (
            "hi, i shared my ex girlfriend's photo angry on whatsapp group not nude just normal selfie now she filed 67 case can i file case",
            [
                {"index": 1, "title": "Information Technology Act 2000", "anchor": "it-2000/sec-67"},
                {"index": 2, "title": "Bharatiya Nagarik Suraksha Sanhita 2023", "anchor": "bnss-2023/sec-483@2024-07-01"},
            ],
            "criminal_defence_first_action",
            "primary",
            ("IT Act 67", "FIR/notice", "bail"),
        ),
    ]

    for query, passages, expected_id, expected_mode, expected_terms in cases:
        result = common_workflow_contract_result(query, route_matter(query), passages)
        assert result is not None, query
        assert result.id == expected_id
        assert result.answer_mode == expected_mode
        text = " ".join(result.lines)
        for term in expected_terms:
            assert term in text


def test_patch18_hard_cluster_variants_get_specific_answer_contracts():
    cases = [
        (
            "thekedar promised displacement allowance bihar to gurgaon never paid 12 of us came together",
            [
                {"index": 1, "title": "Inter-State Migrant Workmen (Regulation of Employment and Conditions of Service) Act 1979", "anchor": "ismw-1979/sec-14"},
                {"index": 2, "title": "Code on Wages 2019", "anchor": "code-on-wages-2019/sec-17"},
            ],
            "interstate_migrant_displacement_allowance",
            ("Bihar to Gurgaon", "12 workers", "not a generic salary complaint"),
        ),
        (
            "ancestral land in my dada name now uncle selling without telling us what to do",
            [
                {"index": 1, "title": "Hindu Succession Act 1956 (with 2005 amendment)", "anchor": "hindu-succession-1956/sec-8"},
                {"index": 2, "title": "Transfer of Property Act 1882", "anchor": "transfer-of-property-1882/sec-44"},
                {"index": 3, "title": "Specific Relief Act 1963", "anchor": "specific-relief-1963/sec-31"},
            ],
            "heir_refuses_sale",
            ("uncle", "ancestral land", "who can sign sale papers"),
        ),
        (
            "tribal land sold to non tribal by uncle without our consent is it legal",
            [
                {"index": 1, "title": "Constitution of India", "anchor": "constitution-india/sec-244"},
                {"index": 2, "title": "Panchayats (Extension to the Scheduled Areas) Act 1996", "anchor": "pesa-1996/sec-4-c"},
                {"index": 3, "title": "Scheduled Castes and Scheduled Tribes (Prevention of Atrocities) Act 1989", "anchor": "sc-st-poa-1989/sec-3-d"},
            ],
            "tribal_land_nontribal_transfer",
            ("tribal land sold to a non-tribal", "not automatically valid", "Collector"),
        ),
        (
            "mother says son took her thumb impression on blank paper now produced as gift deed",
            [
                {"index": 1, "title": "Transfer of Property Act 1882", "anchor": "transfer-of-property-1882/sec-122"},
                {"index": 2, "title": "Specific Relief Act 1963", "anchor": "specific-relief-1963/sec-31"},
                {"index": 3, "title": "Registration Act 1908", "anchor": "registration-1908/sec-49"},
                {"index": 4, "title": "Bharatiya Nyaya Sanhita 2023", "anchor": "bns-2023/sec-336"},
                {"index": 5, "title": "Indian Contract Act 1872", "anchor": "indian-contract-1872/sec-16"},
            ],
            "gift_deed_thumb_fraud",
            ("thumb impression on blank paper", "gift deed", "Indian Contract Act", "cancellation/declaration"),
        ),
        (
            "my health insurance claim rejected saying pre existing disease but i declared everything in form, what to do",
            [
                {"index": 1, "title": "Insurance Ombudsman Rules 2017", "anchor": "insurance-ombudsman-rules-2017/sec-13"},
                {"index": 2, "title": "Insurance Ombudsman Rules 2017", "anchor": "insurance-ombudsman-rules-2017/sec-14"},
                {"index": 3, "title": "Consumer Protection Act 2019", "anchor": "consumer-protection-2019/sec-35"},
            ],
            "insurance_claim_or_misselling",
            ("pre-existing disease", "declared", "Insurance Ombudsman"),
        ),
        (
            "company doing illegal mining on community forest land we got CFR title hazaribagh",
            [
                {"index": 1, "title": "Scheduled Tribes and Other Traditional Forest Dwellers (Recognition of Forest Rights) Act 2006", "anchor": "fra-2006/sec-3-a"},
                {"index": 2, "title": "Mines and Minerals (Development and Regulation) Act 1957", "anchor": "mmdr-1957#header"},
                {"index": 3, "title": "Forest (Conservation) Act 1980", "anchor": "forest-conservation-1980/sec-2"},
            ],
            "cfr_illegal_mining",
            ("community forest land", "CFR title", "illegal mining"),
        ),
    ]

    for query, passages, workflow_id, expected_terms in cases:
        result = common_workflow_contract_result(query, route_matter(query), passages)
        assert result is not None, query
        assert result.id == workflow_id
        assert result.answer_mode == "primary"
        text = " ".join(result.lines)
        for term in expected_terms:
            assert term in text

    lgbtq_arrest = common_workflow_contract_result(
        "police arrested my son for being gay",
        route_matter("police arrested my son for being gay"),
        [
            {"index": 1, "title": "NAVTEJ SINGH JOHAR & ORS. versus UNION OF INDIA", "anchor": "2018-insc-790#header"},
            {"index": 2, "title": "Constitution of India", "anchor": "constitution-india/sec-22"},
            {"index": 3, "title": "Bharatiya Nagarik Suraksha Sanhita 2023", "anchor": "bnss-2023/sec-47"},
        ],
    )
    assert lgbtq_arrest is not None
    assert lgbtq_arrest.id == "lgbtq_identity_arrest_safeguard"
    assert lgbtq_arrest.answer_mode == "safety_primary"
    lgbtq_text = " ".join(lgbtq_arrest.lines)
    assert "not itself an offence" in lgbtq_text
    assert "FIR/offence sections" in lgbtq_text
    assert "identity-based liberty" in lgbtq_text

    forest = common_workflow_contract_result(
        "false dacoity case lodged on my brother by forest guard for collecting tendu leaves dindori",
        route_matter("false dacoity case lodged on my brother by forest guard for collecting tendu leaves dindori"),
        [
            {"index": 1, "title": "Scheduled Tribes and Other Traditional Forest Dwellers (Recognition of Forest Rights) Act 2006", "anchor": "fra-2006/sec-3-d"},
            {"index": 2, "title": "Bharatiya Nyaya Sanhita 2023", "anchor": "bns-2023/sec-310"},
            {"index": 3, "title": "Bharatiya Nagarik Suraksha Sanhita 2023", "anchor": "bnss-2023/sec-483"},
        ],
    )
    assert forest is not None
    assert forest.id == "forest_mfp_false_dacoity_case"
    assert forest.answer_mode == "primary"
    assert "false dacoity case over collecting tendu leaves" in " ".join(forest.lines)

    school = common_workflow_contract_result(
        "sarpanch from upper caste beat my son outside school called him untouchable name bastar",
        route_matter("sarpanch from upper caste beat my son outside school called him untouchable name bastar"),
        [
            {"index": 1, "title": "Scheduled Castes and Scheduled Tribes (Prevention of Atrocities) Act 1989", "anchor": "sc-st-poa-1989/sec-3-d"},
            {"index": 2, "title": "Bharatiya Nyaya Sanhita 2023", "anchor": "bns-2023/sec-117"},
            {"index": 3, "title": "Right of Children to Free and Compulsory Education Act 2009", "anchor": "rte-2009/sec-17"},
            {"index": 4, "title": "Bharatiya Nagarik Suraksha Sanhita 2023", "anchor": "bnss-2023/sec-173"},
        ],
    )
    assert school is not None
    assert school.id == "school_caste_slur_assault"
    assert school.answer_mode == "primary"
    assert "child beaten near school" in " ".join(school.lines)


def test_patch18d_screenshot_regressions_get_specific_source_gated_workflows():
    insurance = common_workflow_contract_result(
        "INSURERER IS REJECTING MY CLAIM",
        route_matter("INSURERER IS REJECTING MY CLAIM"),
        [
            {"index": 1, "title": "Insurance Ombudsman Rules 2017", "anchor": "insurance-ombudsman-rules-2017/sec-13"},
            {"index": 2, "title": "Insurance Ombudsman Rules 2017", "anchor": "insurance-ombudsman-rules-2017/sec-14"},
            {"index": 3, "title": "Consumer Protection Act 2019", "anchor": "consumer-protection-2019/sec-35"},
        ],
    )
    assert insurance is not None
    assert insurance.id == "insurance_claim_or_misselling"
    assert insurance.answer_mode == "primary"
    insurance_text = " ".join(insurance.lines)
    assert "insurance claim" in insurance_text
    assert "Insurance Ombudsman" in insurance_text
    assert "Consumer Protection Act" in insurance_text

    lgbtq_arrest = common_workflow_contract_result(
        "police arrested my son for being gay",
        route_matter("police arrested my son for being gay"),
        [
            {"index": 1, "title": "NAVTEJ SINGH JOHAR & ORS. versus UNION OF INDIA", "anchor": "2018-insc-790#header"},
            {"index": 2, "title": "Constitution of India", "anchor": "constitution-india/sec-22"},
            {"index": 3, "title": "Bharatiya Nagarik Suraksha Sanhita 2023", "anchor": "bnss-2023/sec-47"},
        ],
    )
    assert lgbtq_arrest is not None
    assert lgbtq_arrest.id == "lgbtq_identity_arrest_safeguard"
    assert lgbtq_arrest.answer_mode == "safety_primary"
    lgbtq_text = " ".join(lgbtq_arrest.lines)
    assert "not itself an offence" in lgbtq_text
    assert "FIR/offence sections" in lgbtq_text
    assert "identity-based liberty" in lgbtq_text


def test_stage3_real_user_gaps_get_reviewed_source_gated_workflows():
    alimony = common_workflow_contract_result(
        "after divorce he is saying I cannot ask fr alimony because I was working before marriage too",
        route_matter("after divorce he is saying I cannot ask fr alimony because I was working before marriage too"),
        [
            {"index": 1, "title": "Family Courts Act 1984", "anchor": "family-courts-act-1984/sec-7"},
            {"index": 2, "title": "Hindu Marriage Act 1955", "anchor": "hindu-marriage-1955/sec-25"},
        ],
    )
    assert alimony is not None
    assert alimony.id == "spousal_alimony_working_status"
    assert alimony.answer_mode == "primary"
    assert "does not by itself end the alimony" in " ".join(alimony.lines)

    notice = common_workflow_contract_result(
        "got divorce notice from family court yesterday how do I respond need lawyer or police",
        route_matter("got divorce notice from family court yesterday how do I respond need lawyer or police"),
        [
            {"index": 1, "title": "Family Courts Act 1984", "anchor": "family-courts-act-1984/sec-7"},
            {"index": 2, "title": "Legal Services Authorities Act 1987", "anchor": "legal-services-authorities-1987/sec-12"},
        ],
    )
    assert notice is not None
    assert notice.id == "family_court_notice_response"
    assert notice.answer_mode == "primary"
    assert "notice" in " ".join(notice.lines)

    manual = common_workflow_contract_result(
        "village man dies cleaning septic tank no safety equipment company not agreeing compensation",
        route_matter("village man dies cleaning septic tank no safety equipment company not agreeing compensation"),
        [
            {"index": 1, "title": "Prohibition of Employment as Manual Scavengers and their Rehabilitation Act 2013", "anchor": "manual-scavenging-2013/sec-7"},
            {"index": 2, "title": "Employees' Compensation Act 1923", "anchor": "employees-compensation-1923/sec-3"},
        ],
    )
    assert manual is not None
    assert manual.id == "manual_scavenging_death_compensation"
    assert manual.answer_mode == "safety_primary"
    assert "septic-tank" in " ".join(manual.lines)

    manual_no_death = common_workflow_contract_result(
        "septic tank cleaner no safety equipment company refusing mask what to do",
        route_matter("septic tank cleaner no safety equipment company refusing mask what to do"),
        [
            {"index": 1, "title": "Prohibition of Employment as Manual Scavengers and their Rehabilitation Act 2013", "anchor": "manual-scavenging-2013/sec-7"},
            {"index": 2, "title": "Employees' Compensation Act 1923", "anchor": "employees-compensation-1923/sec-3"},
        ],
    )
    assert manual_no_death is None or manual_no_death.id != "manual_scavenging_death_compensation"

    bonded = common_workflow_contract_result(
        "bonded labour rehabilitation 200000 release certificate how to get jharkhand sdm office",
        route_matter("bonded labour rehabilitation 200000 release certificate how to get jharkhand sdm office"),
        [
            {"index": 1, "title": "Bonded Labour System (Abolition) Act 1976", "anchor": "bonded-labour-1976/sec-12"},
            {"index": 2, "title": "Constitution of India", "anchor": "constitution-india/sec-23"},
        ],
    )
    assert bonded is not None
    assert bonded.id == "bonded_labour_rehabilitation_release_certificate"
    assert bonded.answer_mode == "safety_primary"
    assert "release-certificate" in " ".join(bonded.lines)

    fir = common_workflow_contract_result(
        "thana refused to file complaint against zamindar who burnt our hut latehar how to complain",
        route_matter("thana refused to file complaint against zamindar who burnt our hut latehar how to complain"),
        [
            {"index": 1, "title": "Bharatiya Nagarik Suraksha Sanhita 2023", "anchor": "bnss-2023/sec-173"},
            {"index": 2, "title": "Bharatiya Nyaya Sanhita 2023", "anchor": "bns-2023/sec-326"},
        ],
    )
    assert fir is not None
    assert fir.id == "police_fir_refusal_serious_offence"
    assert fir.answer_mode == "safety_primary"
    assert workflow_contract_promotes_verifier(fir)
    assert "thana or police station refuses" in " ".join(fir.lines)
    assert "burnt-hut complaint" in " ".join(fir.lines)

    deduction = common_workflow_contract_result(
        "contractor took rs 30 daily for food gave gruel only deducted from wages legal or not",
        route_matter("contractor took rs 30 daily for food gave gruel only deducted from wages legal or not"),
        [
            {"index": 1, "title": "Code on Wages 2019", "anchor": "code-on-wages-2019/sec-18"},
            {"index": 2, "title": "Contract Labour (Regulation and Abolition) Act 1970", "anchor": "contract-labour-1970/sec-21"},
            {"index": 3, "title": "Inter-State Migrant Workmen Act 1979", "anchor": "inter-state-migrant-workmen-1979/sec-14"},
        ],
    )
    assert deduction is not None
    assert deduction.id == "labour_wage_deduction_food"
    assert deduction.answer_mode == "primary"
    deduction_text = " ".join(deduction.lines)
    assert "food deductions" in deduction_text
    assert "inter-state migrant workers" in deduction_text

    retrenchment = common_workflow_contract_result(
        "construction company retrenched 40 of us bengali workers kept the gujaratis next day same site",
        route_matter("construction company retrenched 40 of us bengali workers kept the gujaratis next day same site"),
        [
            {"index": 1, "title": "Industrial Disputes Act 1947", "anchor": "industrial-disputes-1947/sec-25F"},
            {"index": 2, "title": "Industrial Disputes Act 1947", "anchor": "industrial-disputes-1947/sec-25G"},
            {"index": 3, "title": "Industrial Disputes Act 1947", "anchor": "industrial-disputes-1947/sec-25H"},
            {"index": 4, "title": "Code on Wages 2019", "anchor": "code-on-wages-2019/sec-17"},
        ],
    )
    assert retrenchment is not None
    assert retrenchment.id == "group_retrenchment_discrimination"
    assert retrenchment.answer_mode == "primary"
    assert "group retrenchment" in " ".join(retrenchment.lines)
    assert "last-come-first-go" in " ".join(retrenchment.lines)

    caste_retrenchment = common_workflow_contract_result(
        "company retrenched only our caste group without notice what can we do",
        route_matter("company retrenched only our caste group without notice what can we do"),
        [
            {"index": 1, "title": "Industrial Disputes Act 1947", "anchor": "industrial-disputes-1947/sec-25F"},
            {"index": 2, "title": "Industrial Disputes Act 1947", "anchor": "industrial-disputes-1947/sec-25G"},
            {"index": 3, "title": "Constitution of India", "anchor": "constitution-india/sec-14"},
        ],
    )
    assert caste_retrenchment is not None
    assert caste_retrenchment.id == "group_retrenchment_discrimination"
    assert "do not assume a criminal atrocity route" in " ".join(caste_retrenchment.lines)
    assert "public employer" in " ".join(caste_retrenchment.lines)

    weak_retrenchment = common_workflow_contract_result(
        "company retrenched only our caste group without notice what can we do",
        route_matter("company retrenched only our caste group without notice what can we do"),
        [
            {"index": 1, "title": "Industrial Disputes Act 1947", "anchor": "industrial-disputes-1947/sec-25F"},
        ],
    )
    assert weak_retrenchment is None or weak_retrenchment.id != "group_retrenchment_discrimination"


def test_patch18_review_p1_triggers_do_not_steal_adjacent_queries():
    travel_agent = common_workflow_contract_result(
        "travel agent took money for visa and ticket now says no refund fraud what to do",
        route_matter("travel agent took money for visa and ticket now says no refund fraud what to do"),
        [
            {"index": 1, "title": "Consumer Protection Act 2019", "anchor": "consumer-protection-2019/sec-35"},
        ],
    )
    assert travel_agent is None or travel_agent.id != "insurance_claim_or_misselling"

    tribal_family = common_workflow_contract_result(
        "tribal family land uncle selling without consent what to do",
        route_matter("tribal family land uncle selling without consent what to do"),
        [
            {"index": 1, "title": "Constitution of India", "anchor": "constitution-india/sec-244"},
            {"index": 2, "title": "Panchayats (Extension to the Scheduled Areas) Act 1996", "anchor": "pesa-1996/sec-4-c"},
            {"index": 3, "title": "Scheduled Castes and Scheduled Tribes (Prevention of Atrocities) Act 1989", "anchor": "sc-st-poa-1989/sec-3-d"},
        ],
    )
    assert tribal_family is None or tribal_family.id != "tribal_land_nontribal_transfer"

    survivor = common_workflow_contract_result(
        "please help my visually impaired sister was raped by her caretaker the police said she cannot identify so case is weak any remedy",
        route_matter("please help my visually impaired sister was raped by her caretaker the police said she cannot identify so case is weak any remedy"),
        [
            {"index": 1, "title": "Rights of Persons with Disabilities Act 2016", "anchor": "rpwd-2016/sec-7"},
            {"index": 2, "title": "Bharatiya Nyaya Sanhita 2023", "anchor": "bns-2023/sec-64-b"},
            {"index": 3, "title": "Bharatiya Nagarik Suraksha Sanhita 2023", "anchor": "bnss-2023/sec-173"},
        ],
    )
    assert survivor is not None
    assert survivor.id == "sexual_offence_survivor_procedure"
    assert survivor.answer_mode == "safety_primary"
    survivor_text = " ".join(survivor.lines)
    assert "survivor-sensitive statement" in survivor_text
    assert "making the case weak by itself" in survivor_text
    survivor_line = next(line for line in survivor.lines if "making the case weak by itself" in line)
    promoted_survivor = _promote_reviewed_workflow_contract_line(
        SentenceVerification(
            text=survivor_line,
            status=SentenceStatus.UNSUPPORTED,
            citations=[1],
            reason="simulated NLI drift",
        ),
        survivor,
        survivor.lines,
    )
    assert promoted_survivor.status == SentenceStatus.OK

    dowry = common_workflow_contract_result(
        "sir sister died at in laws house they say suicide but body had marks dowry case where to go",
        route_matter("sir sister died at in laws house they say suicide but body had marks dowry case where to go"),
        [
            {"index": 1, "title": "Bharatiya Nyaya Sanhita 2023", "anchor": "bns-2023/sec-80"},
            {"index": 2, "title": "Bharatiya Nagarik Suraksha Sanhita 2023", "anchor": "bnss-2023/sec-173"},
            {"index": 3, "title": "Bharatiya Nagarik Suraksha Sanhita 2023", "anchor": "bnss-2023/sec-194"},
        ],
    )
    assert dowry is not None
    assert dowry.id == "dowry_death_inquest_fir"
    assert dowry.answer_mode == "safety_primary"
    dowry_text = " ".join(dowry.lines)
    assert "FIR/complaint" in dowry_text
    assert "post-mortem" in dowry_text
    assert "inquest papers" in dowry_text
    dowry_line = next(line for line in dowry.lines if "inquest papers" in line)
    promoted_dowry = _promote_reviewed_workflow_contract_line(
        SentenceVerification(
            text=dowry_line,
            status=SentenceStatus.WEAK_SUPPORT,
            citations=[3],
            reason="simulated NLI drift",
        ),
        dowry,
        dowry.lines,
    )
    assert promoted_dowry.status == SentenceStatus.OK


def test_hospital_records_and_billing_contract_owns_common_user_answer():
    passages = [
        {"index": 1, "title": "Consumer Protection Act 2019", "anchor": "consumer-protection-2019/sec-39"},
        {"index": 2, "title": "Code of Medical Ethics Regulations 2002", "anchor": "medical-ethics-regulations-2002/reg-1.3.2"},
        {"index": 3, "title": "Clinical Establishments (Registration and Regulation) Act 2010", "anchor": "clinical-establishments-2010/sec-12"},
    ]

    records = common_workflow_contract_result(
        "hospital is not giving my medical records and case papers",
        route_matter("hospital is not giving my medical records and case papers"),
        passages,
    )
    assert records is not None
    assert records.id == "hospital_records_billing"
    assert records.answer_mode == "primary"
    joined_records = " ".join(records.lines)
    assert "medical records or case papers" in joined_records
    assert "Medical Ethics Regulations" in joined_records
    assert "Clinical Establishments Act" in joined_records
    assert "District Consumer Commission" in joined_records

    billing = common_workflow_contract_result(
        "hospital overcharged me and is not giving breakup bill what can i do",
        route_matter("hospital overcharged me and is not giving breakup bill what can i do"),
        passages,
    )
    assert billing is not None
    assert billing.id == "hospital_records_billing"
    joined_billing = " ".join(billing.lines)
    assert "breakup-bill" in joined_billing
    assert "itemised-bill" in joined_billing
    assert "Clinical Establishments Act" in joined_billing
    assert "hospital-registration/conditions support" in joined_billing
    assert "hospital charges/records authority" not in joined_billing
    assert "Consumer Protection Act" in joined_billing


def test_stage5_bank_wrong_debit_bridge_allows_user_delay_without_deadline_hole():
    hdfc_route = route_matter("HDFC wrongly charged forex markup twice on card and support says wait 45 days")
    assert hdfc_route.category == "banking_credit_dispute"
    assert _is_safe_template_source_bridge(
        "For HDFC card forex markup charged twice with support saying wait 45 days where customer care is not helping, first create a written bank complaint with the card/transaction details and complaint number, then use the RBI Ombudsman/CMS route if the bank reply or non-reply does not fix it [3].",
        hdfc_route,
    )

    assert not _is_safe_template_source_bridge(
        "For HDFC card forex markup charged twice, file within 45 days or you will lose the case [3].",
        hdfc_route,
    )
    assert not _is_safe_template_source_bridge(
        "For loan app or recovery harassment, wait 45 days before making a police/cyber complaint [1].",
        route_matter("loan app people calling my mother and contacts every hour for repayment"),
    )
    assert not _is_safe_template_source_bridge(
        "For a credit score dispute after a fake loan, wait 45 days and it will improve automatically [1].",
        route_matter("someone used my Aadhaar to take instant loan, CIBIL shows default"),
    )
    assert not _is_safe_template_source_bridge(
        "For a bank account, salary account, or UPI account frozen after police request, file within 7 days for release [1].",
        route_matter("bank marked lien on salary account because cyber case but no notice came"),
    )


def test_tenant_arrears_limitation_bridge_allows_source_without_invented_deadline():
    route = route_matter("My tenant is not vacating house and not paying rent")
    assert route.category == "property_tenancy"
    assert _is_safe_template_source_bridge(
        "For unpaid-rent arrears, keep the Limitation Act source with the rent ledger, due dates, last payment, and acknowledgement dates before filing the arrears claim [4].",
        route,
    )
    assert not _is_safe_template_source_bridge(
        "For unpaid-rent arrears, file within 30 days or you will lose the case [4].",
        route,
    )


def test_repair8_negative_neighbor_answer_contracts_are_query_shaped():
    duplicate_shoes_q = "flipkart seller sent duplicate shoes i want refund not trademark case"
    consumer_sources = [
        {"index": 1, "title": "Consumer Protection Act 2019", "anchor": "consumer-protection-2019/sec-35"},
    ]
    duplicate_shoes = _grounded_joined(duplicate_shoes_q, consumer_sources)
    assert "duplicate or wrong shoes" in duplicate_shoes
    assert "fake iPhone" not in duplicate_shoes
    assert "defective mobile" not in duplicate_shoes

    fake_iphone_q = "amazon delivered fake iphone and says third party seller responsible refund denied"
    fake_iphone = _grounded_joined(fake_iphone_q, consumer_sources)
    assert "fake iPhone or third-party-seller refund denial" in fake_iphone
    assert "service-centre warranty refusal" not in fake_iphone

    no_nda_q = "company laptop data copied by employee but we have no nda just employment contract"
    business_sources = [
        {"index": 1, "title": "Specific Relief Act 1963", "anchor": "specific-relief-1963/sec-42"},
        {"index": 3, "title": "Indian Contract Act 1872", "anchor": "indian-contract-1872/sec-27"},
    ]
    no_nda = _grounded_joined(no_nda_q, business_sources)
    assert "no NDA or weak customer-database proof" in no_nda
    assert "data access or copying" in no_nda
    assert _is_safe_template_source_bridge(
        "Because the facts mention no NDA or weak customer-database proof, first verify the employment/contract duty, data access or copying, client contact, and misuse facts before sending a notice or filing [3].",
        route_matter(no_nda_q),
    )

    dismissed_q = "magistrate complaint dismissed for non appearance how to restore or appeal"
    court_sources = [
        {"index": 1, "title": "Bharatiya Nagarik Suraksha Sanhita 2023", "anchor": "bnss-2023/sec-223"},
        {"index": 2, "title": "Bharatiya Nagarik Suraksha Sanhita 2023", "anchor": "bnss-2023/sec-175"},
    ]
    dismissed = _grounded_joined(dismissed_q, court_sources)
    assert "dismissed for non-appearance" in dismissed
    assert "restoration/recall" in dismissed
    assert "revision, or appeal" in dismissed
    route = route_matter(dismissed_q)
    assert _is_safe_template_source_bridge(
        "For a Magistrate complaint dismissed for non-appearance, first get the dismissal order and order-sheet copy; then ask whether restoration/recall, fresh complaint, revision, or appeal is the correct procedural route, instead of refiling blindly [1].",
        route,
    )
    assert _is_safe_template_next_step(
        "- Keep the complaint copy, dismissal order, order-sheet copy, hearing date, reason for absence, medical/travel proof if any, and vakalatnama/counsel communication; take these to DLSA or a criminal-procedure lawyer for restoration, revision, appeal, or fresh-filing advice [1].",
        route,
        SentenceVerification("**What you can do next**", SentenceStatus.META),
    )


def test_ui_real_50_v2_failure_families_have_route_specific_answers():
    undertrial_q = "need help, brother in tihar 2 yrs murder trial not started speedy trial right kya hai what next"
    undertrial = _grounded_joined(undertrial_q, [
        {"index": 1, "title": "Bharatiya Nagarik Suraksha Sanhita 2023", "anchor": "bnss-2023/sec-479"},
        {"index": 2, "title": "Constitution of India", "anchor": "constitution-india/sec-21"},
        {"index": 3, "title": "Legal Services Authorities Act 1987", "anchor": "legal-services-authorities-1987/sec-9"},
    ])
    assert "your brother" in undertrial
    assert "speedy-trial delay" in undertrial
    assert "whether the trial has started" in undertrial

    writ_q = "urgent difference between Article 32 Supreme Court and Article 226 High Court writ how to complain"
    writ = _grounded_joined(writ_q, [
        {"index": 1, "title": "W.P.(C)/7962/2023 of PUNE BUILDTECH PVT LTD Vs BANK OF INDIA", "anchor": "hc/dlhc010225222023#para-66", "text": "Article 226 writ mandamus public duty"},
        {"index": 2, "title": "Constitution of India", "anchor": "constitution-india/sec-32"},
        {"index": 3, "title": "Legal Services Authorities Act 1987", "anchor": "legal-services-authorities-1987/sec-12"},
    ])
    assert "Article 32 is the Supreme Court procedure" in writ
    assert "bare Article 226 provision" in writ
    assert "writ procedure" in writ
    assert "[2]" in writ
    assert "[1]" not in writ

    dam_q = "company building dam will submerge 4 tribal villages no consent gram sabha odisha"
    dam = _grounded_joined(dam_q, [
        {"index": 1, "title": "Right to Fair Compensation and Transparency in Land Acquisition, Rehabilitation and Resettlement Act 2013", "anchor": "rfctlarr-2013/sec-41-b"},
        {"index": 2, "title": "Panchayats (Extension to the Scheduled Areas) Act 1996", "anchor": "pesa-1996/sec-4-b"},
    ])
    assert "dam, public project, mine, or coal-block displacement" in dam
    assert "submerge tribal villages" in dam
    assert "Gram Sabha" in dam

    gift_q = "mother says son took her thumb impression on blank paper now produced as gift deed"
    gift = _grounded_joined(gift_q, [
        {"index": 1, "title": "Transfer of Property Act 1882", "anchor": "transfer-of-property-1882/sec-122"},
        {"index": 2, "title": "Registration Act 1908", "anchor": "registration-1908/sec-49"},
        {"index": 3, "title": "Specific Relief Act 1963", "anchor": "specific-relief-1963/sec-31"},
        {"index": 7, "title": "Indian Contract Act 1872", "anchor": "indian-contract-1872/sec-16"},
    ])
    assert "title chain" in gift
    assert "sale deed" in gift
    assert "thumb-impression/signature proof" in gift

    customs_q = "customs reclassified my import wire harness higher duty 18% instead of 10% svb opened mumbai"
    customs = _grounded_joined(customs_q, [
        {"index": 1, "title": "Customs Act 1962", "anchor": "customs-1962/sec-14"},
        {"index": 2, "title": "Customs Act 1962", "anchor": "customs-1962/sec-17"},
        {"index": 3, "title": "Customs Act 1962", "anchor": "customs-1962/sec-28"},
        {"index": 4, "title": "Customs Act 1962", "anchor": "customs-1962/sec-128"},
    ])
    customs_workflow = common_workflow_contract_result(customs_q, route_matter(customs_q), [
        {"index": 1, "title": "Customs Act 1962", "anchor": "customs-1962/sec-17"},
        {"index": 2, "title": "Customs Act 1962", "anchor": "customs-1962/sec-28"},
        {"index": 4, "title": "Customs Act 1962", "anchor": "customs-1962/sec-128"},
    ])
    assert customs_workflow is not None
    assert customs_workflow.id == "customs_reclassification_svb"
    assert customs_workflow.answer_mode == "primary"
    assert "customs reclassification" in customs
    assert "SVB/valuation" in customs
    assert "bill of entry" in customs
    assert "customs appeal" in customs

    plain_customs_q = "customs reclassified imported scanner under wrong tariff heading higher duty"
    plain_customs = _grounded_joined(plain_customs_q, [
        {"index": 1, "title": "Customs Act 1962", "anchor": "customs-1962/sec-17"},
        {"index": 2, "title": "Customs Act 1962", "anchor": "customs-1962/sec-28"},
        {"index": 3, "title": "Customs Act 1962", "anchor": "customs-1962/sec-128"},
    ])
    assert "customs classification file" in plain_customs
    assert "SVB" not in plain_customs
    assert "related-party" not in plain_customs
    assert "declared-value" not in plain_customs

    no_svb_q = "customs reclassified imported wire harness higher duty no svb opened"
    no_svb = _grounded_joined(no_svb_q, [
        {"index": 1, "title": "Customs Act 1962", "anchor": "customs-1962/sec-14"},
        {"index": 2, "title": "Customs Act 1962", "anchor": "customs-1962/sec-17"},
        {"index": 3, "title": "Customs Act 1962", "anchor": "customs-1962/sec-28"},
        {"index": 4, "title": "Customs Act 1962", "anchor": "customs-1962/sec-128"},
    ])
    assert "customs classification file" in no_svb
    assert "SVB/valuation facts" not in no_svb
    assert "related-party" not in no_svb
    assert "declared-value" not in no_svb

    svb_not_related_q = "svb opened but we are not related party declared value rejected by customs"
    svb_not_related = _grounded_joined(svb_not_related_q, [
        {"index": 1, "title": "Customs Act 1962", "anchor": "customs-1962/sec-14"},
        {"index": 2, "title": "Customs Act 1962", "anchor": "customs-1962/sec-17"},
        {"index": 3, "title": "Customs Act 1962", "anchor": "customs-1962/sec-28"},
        {"index": 4, "title": "Customs Act 1962", "anchor": "customs-1962/sec-128"},
    ])
    assert "SVB/valuation facts" in svb_not_related
    assert "declared-value papers" in svb_not_related
    assert "related-party material" not in svb_not_related
    assert "related-party/declared-value papers" not in svb_not_related

    bill_of_entry_only_q = "bill of entry assessment query no misdeclaration no penalty"
    bill_of_entry_only = common_workflow_contract_result(
        bill_of_entry_only_q,
        route_matter(bill_of_entry_only_q),
        [
            {"index": 1, "title": "Customs Act 1962", "anchor": "customs-1962/sec-17"},
            {"index": 2, "title": "Customs Act 1962", "anchor": "customs-1962/sec-124"},
        ],
    )
    assert bill_of_entry_only is None or bill_of_entry_only.id != "customs_icegate_misdeclaration_hold"
    bill_of_entry_grounded = _grounded_joined(bill_of_entry_only_q, [
        {"index": 1, "title": "Customs Act 1962", "anchor": "customs-1962/sec-17"},
        {"index": 2, "title": "Customs Act 1962", "anchor": "customs-1962/sec-128"},
    ])
    assert "no misdeclaration or penalty facts" in bill_of_entry_grounded
    assert "where misdeclaration is alleged" not in bill_of_entry_grounded

    shipping_bill_only_q = "shipping bill amendment wrong port code no drawback claim"
    shipping_bill_only = common_workflow_contract_result(
        shipping_bill_only_q,
        route_matter(shipping_bill_only_q),
        [
            {"index": 1, "title": "Customs Act 1962", "anchor": "customs-1962/sec-75"},
            {"index": 2, "title": "Customs Act 1962", "anchor": "customs-1962/sec-128"},
        ],
    )
    assert shipping_bill_only is None or shipping_bill_only.id != "customs_drawback_export_mismatch"
    shipping_bill_grounded = _grounded_joined(shipping_bill_only_q, [
        {"index": 1, "title": "Customs Act 1962", "anchor": "customs-1962/sec-17"},
        {"index": 2, "title": "Customs Act 1962", "anchor": "customs-1962/sec-128"},
    ])
    assert "shipping-bill amendment" in shipping_bill_grounded
    assert "drawback claim rejected" not in shipping_bill_grounded
    assert "drawback/export-incentive file" not in shipping_bill_grounded

    not_drawback_q = "shipping bill amendment not a drawback claim only port code correction"
    not_drawback = common_workflow_contract_result(
        not_drawback_q,
        route_matter(not_drawback_q),
        [
            {"index": 1, "title": "Customs Act 1962", "anchor": "customs-1962/sec-75"},
            {"index": 2, "title": "Customs Act 1962", "anchor": "customs-1962/sec-128"},
        ],
    )
    assert not_drawback is None or not_drawback.id != "customs_drawback_export_mismatch"

    not_penalty_q = "icegate bill of entry on hold not a penalty issue only assessment query"
    not_penalty = common_workflow_contract_result(
        not_penalty_q,
        route_matter(not_penalty_q),
        [
            {"index": 1, "title": "Customs Act 1962", "anchor": "customs-1962/sec-17"},
            {"index": 2, "title": "Customs Act 1962", "anchor": "customs-1962/sec-124"},
        ],
    )
    assert not_penalty is None or not_penalty.id != "customs_icegate_misdeclaration_hold"

    msme_quality_q = "hi, buyer deducting payment saying quality issue but no formal rejection given 9 lakh stuck can i file case"
    msme_quality = _grounded_joined(msme_quality_q, [
        {"index": 1, "title": "Micro, Small and Medium Enterprises Development Act 2006", "anchor": "msmed-2006/sec-18"},
        {"index": 2, "title": "Indian Contract Act 1872", "anchor": "indian-contract-1872/sec-37"},
        {"index": 3, "title": "Sale of Goods Act 1930", "anchor": "sale-of-goods-1930/sec-55"},
        {"index": 4, "title": "Micro, Small and Medium Enterprises Development Act 2006", "anchor": "msmed-2006/sec-16"},
        {"index": 5, "title": "Micro, Small and Medium Enterprises Development Act 2006", "anchor": "msmed-2006/sec-15"},
        {"index": 6, "title": "Sale of Goods Act 1930", "anchor": "sale-of-goods-1930/sec-56"},
    ])
    assert "quality issue" in msme_quality
    assert "accepted or rejected in writing" in msme_quality
    assert "MSME" in msme_quality
    assert "payment" in msme_quality


def test_stabilization_epf_gratuity_keeps_separate_tracks():
    sources = [
        {"index": 1, "title": "Employees' Provident Funds and Miscellaneous Provisions Act 1952", "anchor": "epf-1952/sec-14B"},
        {"index": 2, "title": "Payment of Gratuity Act 1972", "anchor": "gratuity-1972/sec-7"},
        {"index": 3, "title": "Code on Social Security 2020", "anchor": "social-security-code-2020/sec-15"},
    ]

    closure = _grounded_joined("factory closed no epf deposit and gratuity not paid", sources)
    assert "two separate tracks" in closure
    assert "EPFO/RPFO recovery" in closure
    assert "gratuity controlling authority" in closure
    assert "UAN/passbook" in closure
    assert "generic wage complaint" in closure

    pending = _grounded_joined("company shut down and my pf plus gratuity both pending", sources)
    assert "PF/EPF and gratuity are pending" in pending
    assert "controlling authority or labour office" in pending
    assert "Regional Provident Fund" in pending


def test_stabilization_epf_zero_contribution_is_not_lost_withdrawal():
    answer = _grounded_joined(
        "company says pf will come later but uan has zero contribution",
        [
            {"index": 1, "title": "Employees' Provident Funds and Miscellaneous Provisions Act 1952", "anchor": "epf-1952/sec-14B"},
            {"index": 2, "title": "Code on Social Security 2020", "anchor": "social-security-code-2020/sec-15"},
        ],
    )
    assert "company says PF will come later" in answer
    assert "UAN/EPFO passbook has zero contribution" in answer
    assert "Do not wait only on the company's PF will come later reply" in answer
    assert "written grievance or recovery status" in answer
    assert "employer contribution-default" in answer
    assert "PF deduction from wages without matching deposit, zero contribution, or no contribution" in answer
    assert "UAN/member ID" in answer
    assert "Regional Provident Fund" in answer
    assert "EPF number/UAN is lost" not in answer
    assert "withdrawal" not in answer


def test_common_workflow_contract_handles_loan_app_harassment():
    answer = _joined(
        "loan app is harassing my contacts and sending my photo",
        LOAN_APP_REGULATORY_SOURCES,
    )
    assert "instant loan app sending your photo to contacts" in answer
    assert "RBI Ombudsman" in answer
    assert "Clause 1 applies the Scheme to services provided by a Regulated Entity" in answer
    assert "Clause 3 defines a Regulated Entity" in answer
    assert "contact lists or call logs" in answer
    assert "family members, referees, and friends" in answer
    assert "cyber police/1930" not in answer
    assert "messages sent to contacts" in answer
    assert "morphed nude/non-consensual image threat" not in answer

    workplace = _joined(
        "collection people came to my workplace shouting about emi default",
        LOAN_APP_REGULATORY_SOURCES,
    )
    assert "collection/recovery people threatening workplace" in workplace
    assert "RBI Ombudsman" in workplace
    assert "recovery-agent circular prohibits" in workplace
    assert "dated record" in workplace

    boss_contact = _joined(
        "loan app people are calling my boss and saying I am fraud",
        LOAN_APP_REGULATORY_SOURCES,
    )
    assert "calling your boss or employer" in boss_contact
    assert "cybercrime.gov.in" not in boss_contact
    assert "dated record" in boss_contact

    generic_route = route_matter("loan app is harassing my contacts and calling my boss")
    generic_route_text = json.dumps(generic_route.to_event()).lower()
    assert "cyber police" not in generic_route_text
    assert "cybercrime.gov.in" not in generic_route_text

    threat_route = route_matter(
        "Unregistered loan app is blackmailing me with a morphed nude photo if I do not pay tonight."
    )
    threat_route_text = json.dumps(threat_route.to_event()).lower()
    assert "cyber police" in threat_route_text
    assert "cybercrime.gov.in" in threat_route_text


def test_stage2_false_nbfc_loan_uses_credit_identity_workflow_not_loan_app():
    query = "nbfc loan showing on my documents but signature not mine; family says ignore but i am scared, safe legal route?"
    sources = [
        {"index": 1, "title": "Credit Information Companies (Regulation) Act 2005", "anchor": "credit-information-companies-2005/sec-21"},
        {"index": 2, "title": "Reserve Bank Integrated Ombudsman Scheme 2021", "anchor": "rbi-integrated-ombudsman-2021/sec-2"},
        {"index": 3, "title": "Information Technology Act 2000", "anchor": "it-2000/sec-66C"},
        {"index": 4, "title": "Bharatiya Nyaya Sanhita 2023", "anchor": "bns-2023/sec-336"},
    ]

    assert _workflow_id(query, sources) == "false_nbfc_credit_identity_record"
    answer = _grounded_joined(query, sources)

    assert "false-loan and credit-report correction track" in answer
    assert "RBI Ombudsman/CMS" in answer
    assert "signature is not yours" in answer
    assert "loan-app harassment" in answer
    assert "contact list" not in answer


def test_stage2_aadhaar_sim_identity_misuse_cites_telecom_it_aadhaar():
    query = "my aadhar used for sim and fraud case came to me pls tell forum and papers"
    sources = [
        {"index": 1, "title": "Telecommunications Act 2023", "anchor": "telecommunications-2023/sec-42-b"},
        {"index": 2, "title": "Information Technology Act 2000", "anchor": "it-2000/sec-66C"},
        {"index": 3, "title": "Aadhaar (Targeted Delivery of Financial and Other Subsidies, Benefits and Services) Act 2016", "anchor": "aadhaar-2016/sec-29"},
        {"index": 4, "title": "Bharatiya Nagarik Suraksha Sanhita 2023", "anchor": "bnss-2023/sec-173"},
    ]

    assert _workflow_id(query, sources) == "aadhaar_sim_identity_misuse"
    answer = _grounded_joined(query, sources)

    assert "Aadhaar identity-information misuse" in answer
    assert "Telecom subscriber/SIM identity misuse" in answer
    assert "IT Act electronic identity/personation" in answer
    assert "subscriber/KYC record" in answer
    assert "CAF/KYC request" in answer
    assert "[1]" in answer


def test_cyber_fake_whatsapp_sim_harassment_cites_telecom_source():
    query = "ex husband created fake whatsapp using my new sim number harassing my family"
    sources = [
        {"index": 1, "title": "Information Technology Act 2000", "anchor": "it-2000/sec-66C"},
        {"index": 2, "title": "Telecommunications Act 2023", "anchor": "telecommunications-2023/sec-29"},
        {"index": 3, "title": "Bharatiya Nyaya Sanhita 2023", "anchor": "bns-2023/sec-78"},
        {"index": 4, "title": "Bharatiya Nagarik Suraksha Sanhita 2023", "anchor": "bnss-2023/sec-173"},
    ]

    workflow = common_workflow_contract_result(query, route_matter(query), sources)
    assert workflow is not None
    assert workflow.id == "cyber_harassment_first_action"
    answer = _grounded_joined(query, sources)

    assert "Telecommunications Act subscriber/identifier misuse" in answer
    assert "SIM/KYC/number-ownership proof" in answer
    assert "[2]" in answer
    assert "[2]" in answer
    assert "[3]" in answer


def test_stage2_failed_family_workflows_use_specific_user_frame():
    upi_freeze = _joined(
        "my upi account frozen and branch not giving complaint number",
        [
            {"index": 1, "title": "Reserve Bank Integrated Ombudsman Scheme 2021", "anchor": "rbi-integrated-ombudsman-2021/sec-2"},
            {"index": 2, "title": "Banking Regulation Act 1949", "anchor": "banking-regulation-1949/sec-35A"},
            {"index": 3, "title": "Bharatiya Nagarik Suraksha Sanhita 2023", "anchor": "bnss-2023/sec-106"},
            {"index": 4, "title": "Information Technology Act 2000", "anchor": "it-2000/sec-66D"},
        ],
    )
    assert "UPI account blocked/frozen" in upi_freeze
    assert "written freeze/lien reason" in upi_freeze
    assert "RBI Ombudsman/CMS" in upi_freeze
    assert "bank-service failure" in upi_freeze
    assert "BNSS seizure/legal-hold track" not in upi_freeze
    assert "IT Act cyber/electronic-record source" not in upi_freeze

    arrest_sources = [
        {"index": 1, "title": "Constitution of India", "anchor": "constitution-india/sec-22"},
        {"index": 2, "title": "Constitution of India", "anchor": "constitution-india/sec-226"},
        {"index": 3, "title": "Bharatiya Nagarik Suraksha Sanhita 2023", "anchor": "bnss-2023/sec-531"},
    ]
    arrest_query = "police has picked my son from my home in the night, i have not got FIR copy"
    assert _workflow_id(arrest_query, arrest_sources) == "arrest_custody_station_case_not_disclosed"
    arrest_answer = _grounded_joined(arrest_query, arrest_sources)
    assert "hidden police pickup as an urgent liberty issue" in arrest_answer
    assert "within twenty-four hours" in arrest_answer
    assert "DLSA or High Court counsel immediately" in arrest_answer

    legal_aid_sources = [
        {"index": 1, "title": "Constitution of India", "anchor": "constitution-india/sec-22"},
        {"index": 2, "title": "Bharatiya Nagarik Suraksha Sanhita 2023", "anchor": "bnss-2023/sec-47"},
        {"index": 3, "title": "Code of Criminal Procedure 1973", "anchor": "crpc-1973/sec-50"},
        {"index": 4, "title": "Legal Services Authorities Act 1987", "anchor": "legal-services-authorities-1987/sec-12"},
    ]
    legal_aid_query = "jail superintendent not allowing lawyer meeting for my brother first time arrest what legal aid route"
    assert _workflow_id(legal_aid_query, legal_aid_sources) == "custody_legal_aid_lawyer_access"
    legal_aid_answer = _grounded_joined(legal_aid_query, legal_aid_sources)
    assert "custody legal-aid and lawyer-access issue" in legal_aid_answer
    assert "DLSA/TLSC/SLSA or the jail legal-aid clinic" in legal_aid_answer
    assert "lawyer meeting permission" in legal_aid_answer
    assert "Magistrate or High Court habeas/production route" in legal_aid_answer

    senior_sources = [
        {"index": 1, "title": "Maintenance and Welfare of Parents and Senior Citizens Act 2007", "anchor": "mwp-2007/sec-5"},
        {"index": 2, "title": "Hindu Adoptions and Maintenance Act 1956", "anchor": "hama-1956/sec-20"},
    ]
    senior_query = "elderly mother is being forced out by children what law in my area"
    assert _workflow_id(senior_query, senior_sources) == "senior_parent_pension_neglect"
    senior_answer = _grounded_joined(senior_query, senior_sources)
    assert "residence/support" in senior_answer
    assert "Maintenance Tribunal/District Social Welfare" in senior_answer

    tribal_answer = _grounded_joined(
        "my ST land in Jharkhand was sold without permission what remedy",
        [
            {"index": 1, "title": "Chota Nagpur Tenancy Act 1908", "anchor": "chota-nagpur-tenancy-1908/sec-45-c"},
            {"index": 2, "title": "Chota Nagpur Tenancy Act 1908", "anchor": "chota-nagpur-tenancy-1908/sec-71-a"},
            {"index": 3, "title": "Constitution of India", "anchor": "constitution-india/sec-244"},
            {"index": 4, "title": "Panchayats (Extension to the Scheduled Areas) Act 1996", "anchor": "pesa-1996/sec-4"},
        ],
    )
    assert "Article 244/Fifth Schedule" not in tribal_answer
    assert "Deputy Commissioner/SAR restoration" in tribal_answer
    assert "[2]" in tribal_answer


def test_property_custody_phrasing_never_selects_habeas_workflow():
    passages = [
        {"index": 1, "title": "Constitution of India", "anchor": "constitution-india/sec-22"},
        {"index": 2, "title": "Bharatiya Nagarik Suraksha Sanhita 2023", "anchor": "bnss-2023/sec-497"},
        {"index": 3, "title": "Bharatiya Nagarik Suraksha Sanhita 2023", "anchor": "bnss-2023/sec-173"},
    ]
    queries = (
        "Police kept my laptop in custody and gave no FIR copy",
        "My laptop is in police custody and I received no FIR copy",
        "Police kept my laptop in their custody and gave no FIR copy",
        "Police have custody of my laptop and gave no FIR copy",
        "The police retain custody of my laptop and gave no FIR copy",
        "Police retain custody of my external hard drive and gave no FIR copy",
        "Police have custody of my passport and gave no FIR copy",
        "Police retained my tablet in custody and gave no FIR copy",
        "Police took the phone belonging to my son and will not tell me the case",
        "Police took my son's phone and will not tell me the case",
        "Police have custody of my partner's laptop and gave no FIR copy",
        "Police took my phone during the arrest of my brother and gave no seizure memo",
        "Police seized my phone and have not produced it before court; they will not tell me the case",
        "The seized hard drive has remained in police custody for five days without production before the Magistrate",
    )

    for query in queries:
        result = common_workflow_contract_result(query, route_matter(query), passages)
        assert result is None or result.id != "custody_habeas_lockup_abuse", query


def test_stage5_money_cyber_identity_rendered_contracts_hit_user_variant_terms():
    bank_sources = RBI_OMBUDSMAN_SOURCES
    bank = _grounded_joined("Bank deducted money wrongly and customer care not helping.", bank_sources)
    assert "wrong deduction" in bank
    assert "RBI Ombudsman" in bank
    assert "complaint number" in bank

    upi = _grounded_joined(
        "UPI failed but amount debited bank and app blaming each other what to do",
        bank_sources,
    )
    assert "failed UPI debit" in upi
    assert "RBI Ombudsman" in upi
    assert "transaction ID/RRN" in upi or "UPI/transaction ID/RRN" in upi

    freeze = _grounded_joined(
        "my bank account is frozen bank says cyber police request but no notice",
        [
            {"index": 1, "title": "Reserve Bank Integrated Ombudsman Scheme 2021", "anchor": "rbi-integrated-ombudsman-2021/sec-2"},
            {"index": 2, "title": "Bharatiya Nagarik Suraksha Sanhita 2023", "anchor": "bnss-2023/sec-106"},
            {"index": 3, "title": "Information Technology Act 2000", "anchor": "it-2000/sec-66D"},
            {"index": 4, "title": "Banking Regulation Act 1949", "anchor": "banking-regulation-1949/sec-35A"},
        ],
    )
    assert "written freeze/lien reason" in freeze
    assert "originating request/reference" in freeze
    assert "does not by itself prove" in freeze
    assert "Use RBI Scheme clauses 9 and 10" not in freeze

    loan_app = _grounded_joined(
        "loan app threatening to make morphed nude photo if I dont pay today",
        [
            *LOAN_APP_REGULATORY_SOURCES,
            {"index": 9, "title": "Information Technology Act 2000", "anchor": "it-2000/sec-66E"},
            {"index": 10, "title": "Bharatiya Nyaya Sanhita 2023", "anchor": "bns-2023/sec-308"},
        ],
    )
    assert "RBI Ombudsman" in loan_app
    assert "IT Act Section 66E is narrower" in loan_app
    assert "BNS Section 308" in loan_app
    assert "do not pay" in loan_app.lower()
    assert "urgent cyber-reporting" in loan_app
    assert "threat" in loan_app.lower()

    exact_loan_app_morph = _grounded_joined(
        "unregistered loan app blackmailing with morphed nude if I miss payment tonight",
        [
            *LOAN_APP_REGULATORY_SOURCES,
            {"index": 9, "title": "Information Technology Act 2000", "anchor": "it-2000/sec-66E"},
            {"index": 10, "title": "Bharatiya Nyaya Sanhita 2023", "anchor": "bns-2023/sec-308"},
        ],
    )
    assert "BNS Section 308" in exact_loan_app_morph
    assert "do not pay or forward the threatened image" in exact_loan_app_morph
    assert "urgent cyber-reporting" in exact_loan_app_morph
    assert "RBI Ombudsman/CMS" in exact_loan_app_morph

    fake_cbi = _grounded_joined(
        "fake CBI video call said my Aadhaar used in drug parcel and made me transfer 2 lakh",
        [
            {"index": 1, "title": "Bharatiya Nagarik Suraksha Sanhita 2023", "anchor": "bnss-2023/sec-173-b"},
            {"index": 2, "title": "Aadhaar Act 2016", "anchor": "aadhaar-2016/sec-29"},
            {"index": 3, "title": "Bharatiya Nyaya Sanhita 2023", "anchor": "bns-2023/sec-319"},
            {"index": 4, "title": "Information Technology Act 2000", "anchor": "it-2000/sec-66D"},
        ],
    )
    assert "fake CBI video call" in fake_cbi
    assert "Aadhaar was used in a drug parcel" in fake_cbi
    assert "bank complaint number" in fake_cbi
    assert "cyber acknowledgement" in fake_cbi

    fake_trai = _grounded_joined(
        "fake TRAI call says sim will close and asked to join police video call",
        [
            {"index": 1, "title": "Bharatiya Nagarik Suraksha Sanhita 2023", "anchor": "bnss-2023/sec-173-b"},
            {"index": 2, "title": "Bharatiya Nyaya Sanhita 2023", "anchor": "bns-2023/sec-319"},
            {"index": 3, "title": "Telecommunications Act 2023", "anchor": "telecommunications-2023/sec-42-b"},
            {"index": 4, "title": "Information Technology Act 2000", "anchor": "it-2000/sec-66D"},
        ],
    )
    assert "fake TRAI/SIM-closure call" in fake_trai
    assert "SIM will close" in fake_trai
    assert "police video call" in fake_trai
    assert "Do not send money" in fake_trai
    assert "cyber police" in fake_trai
    assert "freeze/trace the beneficiary account" not in fake_trai

    parent_upi = _grounded_joined(
        "digital arrest gang kept father on video for 6 hours and took UPI transfers",
        [
            {"index": 1, "title": "Information Technology Act 2000", "anchor": "it-2000/sec-66D"},
            {"index": 2, "title": "Bharatiya Nagarik Suraksha Sanhita 2023", "anchor": "bnss-2023/sec-173-b"},
            {"index": 3, "title": "Bharatiya Nyaya Sanhita 2023", "anchor": "bns-2023/sec-319"},
        ],
    )
    assert "digital arrest gang" in parent_upi
    assert "father/parent on video" in parent_upi
    assert "UPI transfers" in parent_upi
    assert "bank complaint number" in parent_upi
    assert "cyber acknowledgement" in parent_upi

    public_deepfake = _grounded_joined(
        "deepfake of modi pm circulating my friend made it bjp it cell threatening",
        [
            {"index": 1, "title": "Representation of the People Act 1951", "anchor": "rpa-1951/sec-123-d"},
            {"index": 2, "title": "Information Technology Act 2000", "anchor": "it-2000/sec-66D"},
            {"index": 3, "title": "Bharatiya Nyaya Sanhita 2023", "anchor": "bns-2023/sec-356"},
        ],
    )
    assert "public-political deepfake" in public_deepfake
    assert "not as private-image sextortion" in public_deepfake
    assert "cyber" in public_deepfake

    private_deepfake = _grounded_joined(
        "ex boyfriend made ai deepfake porn of me uploaded to xvideos",
        [
            {"index": 1, "title": "Information Technology Act 2000", "anchor": "it-2000/sec-66E"},
            {"index": 2, "title": "Information Technology Act 2000", "anchor": "it-2000/sec-67A"},
            {"index": 3, "title": "Bharatiya Nyaya Sanhita 2023", "anchor": "bns-2023/sec-356"},
        ],
    )
    assert "deepfake" in private_deepfake
    assert "Xvideos" in private_deepfake
    assert "ex-boyfriend" in private_deepfake
    assert "takedown" in private_deepfake
    assert "cyber" in private_deepfake

    legacy_deepfake_extortion = _grounded_joined(
        "someone made deepfake video of me on instagram in June 2024 and is extorting me",
        [
            {"index": 1, "title": "Information Technology Act 2000", "anchor": "it-2000/sec-66e"},
            {"index": 2, "title": "Indian Penal Code 1860", "anchor": "ipc-1860/sec-384"},
            {"index": 3, "title": "Code of Criminal Procedure 1973", "anchor": "crpc-1973/sec-200"},
            {"index": 4, "title": "Bharatiya Nyaya Sanhita 2023", "anchor": "bns-2023/sec-308"},
            {"index": 5, "title": "Bharatiya Nagarik Suraksha Sanhita 2023", "anchor": "bnss-2023/sec-173"},
        ],
    )
    assert "deepfake" in legacy_deepfake_extortion
    assert "IPC extortion/intimidation/sexual-image track" in legacy_deepfake_extortion
    assert "CrPC FIR/complaint source" in legacy_deepfake_extortion
    assert "[2]" in legacy_deepfake_extortion
    assert "[3]" in legacy_deepfake_extortion

    legacy_wrong_regime_only = _grounded_joined(
        "someone made deepfake video of me on instagram before 1 July 2024 and is extorting me",
        [
            {"index": 1, "title": "Information Technology Act 2000", "anchor": "it-2000/sec-66e"},
            {"index": 2, "title": "Bharatiya Nyaya Sanhita 2023", "anchor": "bns-2023/sec-308"},
            {"index": 3, "title": "Bharatiya Nagarik Suraksha Sanhita 2023", "anchor": "bnss-2023/sec-173"},
        ],
    )
    assert "IT Act privacy source" in legacy_wrong_regime_only
    assert "BNS extortion/intimidation/sexual-image track" not in legacy_wrong_regime_only
    assert "BNSS FIR/complaint source" not in legacy_wrong_regime_only

    legacy_numeric_wrong_regime_only = _grounded_joined(
        "someone made deepfake video of me on instagram before 01/07/2024 and is extorting me",
        [
            {"index": 1, "title": "Information Technology Act 2000", "anchor": "it-2000/sec-66e"},
            {"index": 2, "title": "Bharatiya Nyaya Sanhita 2023", "anchor": "bns-2023/sec-308"},
            {"index": 3, "title": "Bharatiya Nagarik Suraksha Sanhita 2023", "anchor": "bnss-2023/sec-173"},
        ],
    )
    assert "IT Act privacy source" in legacy_numeric_wrong_regime_only
    assert "BNS extortion/intimidation/sexual-image track" not in legacy_numeric_wrong_regime_only
    assert "BNSS FIR/complaint source" not in legacy_numeric_wrong_regime_only

    current_deepfake_extortion = _grounded_joined(
        "someone made deepfake video of me on instagram in August 2025 and is extorting me",
        [
            {"index": 1, "title": "Information Technology Act 2000", "anchor": "it-2000/sec-66e"},
            {"index": 2, "title": "Indian Penal Code 1860", "anchor": "ipc-1860/sec-384"},
            {"index": 3, "title": "Code of Criminal Procedure 1973", "anchor": "crpc-1973/sec-200"},
            {"index": 4, "title": "Bharatiya Nyaya Sanhita 2023", "anchor": "bns-2023/sec-308"},
            {"index": 5, "title": "Bharatiya Nagarik Suraksha Sanhita 2023", "anchor": "bnss-2023/sec-173"},
        ],
    )
    assert "BNS extortion/intimidation/sexual-image track" in current_deepfake_extortion
    assert "BNSS FIR/complaint source" in current_deepfake_extortion
    assert "[4]" in current_deepfake_extortion
    assert "[5]" in current_deepfake_extortion

    negated_extortion = _grounded_joined(
        "someone made deepfake video of me on instagram in 2025 no extortion just threatening to share it",
        [
            {"index": 1, "title": "Information Technology Act 2000", "anchor": "it-2000/sec-67a"},
            {"index": 2, "title": "Bharatiya Nyaya Sanhita 2023", "anchor": "bns-2023/sec-351"},
            {"index": 3, "title": "Bharatiya Nagarik Suraksha Sanhita 2023", "anchor": "bnss-2023/sec-173"},
        ],
    )
    assert "circulation/takedown" in negated_extortion
    assert "BNS intimidation/sexual-image track" in negated_extortion
    assert "blackmailer" not in negated_extortion
    assert "extortion/intimidation" not in negated_extortion

    pan = _grounded_joined(
        "my PAN and Aadhaar mismatch bank rejected account opening",
        [
            {"index": 1, "title": "Income-tax Act 1961", "anchor": "income-tax-1961/sec-139-a"},
            {"index": 2, "title": "Aadhaar Act 2016", "anchor": "aadhaar-2016/sec-4"},
        ],
    )
    assert "PAN/Aadhaar mismatch" in pan
    assert "which record needs correction" in pan
    assert "bank account-opening rejection" in pan


def test_stage3_money_property_workflows_emit_full_user_paths():
    bank_sources = RBI_OMBUDSMAN_SOURCES
    debit = _grounded_joined("Bank deducted money wrongly and customer care not helping.", bank_sources)
    assert "written complaint" in debit
    assert "RBI Ombudsman/CMS" in debit
    assert "Clause 10" in debit
    assert "Consumer Protection Act" not in debit
    assert "UPI/transaction ID/RRN" in debit

    loan_app = _grounded_joined(
        "Loan app is harassing my contacts.",
        LOAN_APP_REGULATORY_SOURCES,
    )
    assert "Clause 1 applies the Scheme to services provided by a Regulated Entity" in loan_app
    assert "contact lists or call logs" in loan_app
    assert "cyber police" not in loan_app

    tenant = _grounded_joined(
        "My tenant is not vacating house and not paying rent",
        [
            {"index": 1, "title": "Transfer of Property Act 1882", "anchor": "transfer-of-property-1882/sec-105"},
            {"index": 2, "title": "Transfer of Property Act 1882", "anchor": "transfer-of-property-1882/sec-106"},
            {"index": 3, "title": "Transfer of Property Act 1882", "anchor": "transfer-of-property-1882/sec-111"},
        ],
    )
    assert "tenant is not vacating or not paying rent" in tenant
    assert "do not remove them by force" in tenant
    assert "rent-authority/civil court" in tenant
    assert "instead of self-help eviction" in tenant

    heir = _grounded_joined(
        "Can I sell property if one legal heir is not agreeing?",
        [
            {"index": 1, "title": "Hindu Succession Act 1956", "anchor": "hindu-succession-1956/sec-8"},
            {"index": 2, "title": "Transfer of Property Act 1882", "anchor": "transfer-of-property-1882/sec-44"},
            {"index": 3, "title": "Specific Relief Act 1963", "anchor": "specific-relief-1963/sec-34"},
        ],
    )
    assert "do not assume the whole property can be sold" in heir
    assert "share or interest" in heir
    assert "partition/declaration/injunction" in heir
    assert "legal-heir certificate" in heir


def test_stage3_banking_mixed_routes_do_not_emit_generic_criminal_regime_caveat():
    from apps.api.main import _route_regime_caveat

    loan_app_route = route_matter("Loan app is harassing my contacts.")
    assert loan_app_route.category == "banking_credit_dispute"
    assert loan_app_route.legal_regime == "incident_date_needed_for_bns_bnss_bsa_vs_ipc_crpc"
    assert _route_regime_caveat(loan_app_route) is None

    recovery_route = route_matter("recovery agents from a NBFC visited my office and shouted in front of colleagues")
    assert recovery_route.category == "banking_credit_dispute"
    assert _route_regime_caveat(recovery_route) is None


def test_stage5_high_volume_contracts_select_expected_workflows():
    bank_sources = RBI_OMBUDSMAN_SOURCES
    upi_refund = _grounded_joined(
        "customer care says failed UPI refund will come after 30 days, can I complain now",
        bank_sources,
    )
    assert _workflow_id(
        "customer care says failed UPI refund will come after 30 days, can I complain now",
        bank_sources,
    ) == "wrong_bank_debit"
    assert "failed UPI debit" in upi_refund
    assert "RBI Ombudsman/CMS" in upi_refund
    assert "Consumer Protection Act" not in upi_refund
    assert "transaction ID/RRN" in upi_refund
    assert "1930" not in upi_refund

    phonepe = _grounded_joined(
        "PhonePe failed payment but amount cut and support closed ticket",
        bank_sources,
    )
    assert "PhonePe/payment app" in phonepe
    assert "Consumer Protection Act" not in phonepe
    assert "complaint number" in phonepe

    freeze_sources = [
        {"index": 1, "title": "Reserve Bank Integrated Ombudsman Scheme 2021", "anchor": "rbi-integrated-ombudsman-2021/sec-2"},
        {"index": 2, "title": "Bharatiya Nagarik Suraksha Sanhita 2023", "anchor": "bnss-2023/sec-106"},
        {"index": 3, "title": "Information Technology Act 2000", "anchor": "it-2000/sec-66D"},
        {"index": 4, "title": "Banking Regulation Act 1949", "anchor": "banking-regulation-1949/sec-35A"},
    ]
    victim_freeze_query = "police froze my bank account after fraud complaint but I am victim not accused"
    victim_freeze = _joined(victim_freeze_query, freeze_sources)
    assert _workflow_id(victim_freeze_query, freeze_sources) == "bank_account_freeze_legal_hold"
    assert "written freeze/lien reason" in victim_freeze
    assert "originating request/reference" in victim_freeze
    assert "does not by itself prove" in victim_freeze
    assert "Use RBI Scheme clauses 9 and 10" not in victim_freeze
    assert "exact freeze date" in victim_freeze

    pan_leak_sources = [
        {"index": 1, "title": "Digital Personal Data Protection Act 2023", "anchor": "dpdp-2023/sec-8"},
        {"index": 2, "title": "Information Technology Act 2000", "anchor": "it-2000/sec-66C"},
        {"index": 3, "title": "Reserve Bank Integrated Ombudsman Scheme 2021", "anchor": "rbi-integrated-ombudsman-2021/sec-2"},
        {"index": 4, "title": "Bharatiya Nyaya Sanhita 2023", "anchor": "bns-2023/sec-319"},
        {"index": 5, "title": "Bharatiya Nagarik Suraksha Sanhita 2023", "anchor": "bnss-2023/sec-173"},
    ]
    pan_leak_query = "PAN card copy leaked online and fake bank account opened in my name"
    pan_leak = _joined(pan_leak_query, pan_leak_sources)
    assert _workflow_id(pan_leak_query, pan_leak_sources) == "pan_leak_fake_bank_account"
    assert "DPDP personal-data breach" in pan_leak
    assert "IT Act identity/electronic misuse" in pan_leak
    assert "bank/RBI Ombudsman complaint" in pan_leak
    assert "not treat this as only PAN-Aadhaar correction" in pan_leak

    pension_sources = [
        {"index": 1, "title": "National Social Assistance Programme Old Age Pension", "anchor": "nsap-old-age-pension"},
        {"index": 2, "title": "Aadhaar Act 2016", "anchor": "aadhaar-2016/sec-7"},
        {"index": 3, "title": "Reserve Bank Integrated Ombudsman Scheme 2021", "anchor": "rbi-integrated-ombudsman-2021/sec-2"},
        {"index": 4, "title": "Right to Information Act 2005", "anchor": "rti-2005/sec-6"},
    ]
    pension_query = "old age pension stopped because bank account closed and Aadhaar not linked"
    pension = _joined(pension_query, pension_sources)
    assert _workflow_id(pension_query, pension_sources) == "pension_aadhaar_bank_closure"
    assert "pension-restoration lane" in pension
    assert "Aadhaar authentication/linkage lane" in pension
    assert "RBI Ombudsman lane" in pension
    assert "written pension stoppage reason" in pension

    pension_biometric_query = "pension stopped after biometric mismatch, block office says update Aadhaar only"
    pension_biometric = _grounded_joined(pension_biometric_query, pension_sources)
    assert _workflow_id(pension_biometric_query, pension_sources) == "pension_aadhaar_biometric_mismatch"
    assert "biometric mismatch" in pension_biometric
    assert "written pension stoppage reason" in pension_biometric
    assert "alternate authentication" in pension_biometric

    epfo_pension_sources = [
        {"index": 1, "title": "Right to Information Act 2005", "anchor": "rti-2005/sec-19"},
        {"index": 2, "title": "Employees' Provident Funds and Miscellaneous Provisions Act 1952", "anchor": "epf-1952/sec-6-b"},
        {"index": 3, "title": "Aadhaar Act 2016", "anchor": "aadhaar-2016/sec-59"},
        {"index": 4, "title": "Code on Social Security 2020", "anchor": "social-security-code-2020/sec-15"},
    ]
    epfo_pension_query = "epfo wala bol raha aadhaar mismatch pension nahi milega 4 saal se"
    epfo_pension = _grounded_joined(epfo_pension_query, epfo_pension_sources)
    assert route_matter(epfo_pension_query).label == "EPFO pension / Aadhaar mismatch"

    assert "EPFO/EPS pension" in epfo_pension
    assert "EPFO pension/grievance lane first" in epfo_pension
    assert "Aadhaar source only for the identity/authentication" in epfo_pension
    assert "RTI or first appeal as a records-support step" in epfo_pension
    assert "RTI appeal as the main remedy" in epfo_pension

    ration_sources = [
        {"index": 1, "title": "National Food Security Act 2013", "anchor": "national-food-security-2013/sec-14"},
        {"index": 2, "title": "Aadhaar Act 2016", "anchor": "aadhaar-2016/sec-7"},
        {"index": 3, "title": "Right to Information Act 2005", "anchor": "rti-2005/sec-6"},
    ]
    ration_query = "ration dealer denied grain because old mother fingerprint failed"
    ration = _joined(ration_query, ration_sources)
    assert _workflow_id(ration_query, ration_sources) == "ration_biometric_auth_failure"
    assert "fingerprint or biometric authentication failed" in ration
    assert "alternate authentication" in ration
    assert "DGRO or district grievance route" in ration

    pan_kyc_sources = [
        {"index": 1, "title": "Income-tax Act 1961", "anchor": "income-tax-1961/sec-139-a"},
        {"index": 2, "title": "Aadhaar Act 2016", "anchor": "aadhaar-2016/sec-4"},
    ]
    pan_kyc_query = "PAN name spelling mistake and Aadhaar mismatch bank KYC failed"
    pan_kyc = _joined(pan_kyc_query, pan_kyc_sources)
    assert _workflow_id(pan_kyc_query, pan_kyc_sources) == "pan_aadhaar_bank_kyc_mismatch"
    assert "PAN/Aadhaar mismatch" in pan_kyc
    assert "which record is wrong" in pan_kyc
    assert "Do not file a cyber or general legal complaint" in pan_kyc

    pan_link_query = "bank refuses account opening because PAN Aadhaar link status mismatch on portal"
    pan_link = _grounded_joined(pan_link_query, pan_kyc_sources)
    assert _workflow_id(pan_link_query, pan_kyc_sources) == "pan_aadhaar_bank_kyc_mismatch"
    assert "bank account-opening rejection" in pan_link
    assert "which record needs correction" in pan_link
    assert "record-holding authority" in pan_link

    meme_sources = [
        {"index": 1, "title": "Information Technology Act 2000", "anchor": "it-2000/sec-66D"},
        {"index": 2, "title": "Bharatiya Nyaya Sanhita 2023", "anchor": "bns-2023/sec-356"},
        {"index": 3, "title": "Bharatiya Nagarik Suraksha Sanhita 2023", "anchor": "bnss-2023/sec-173"},
        {"index": 4, "title": "Representation of the People Act 1951", "anchor": "rpa-1951/sec-123-d"},
    ]
    meme_query = "political meme with Modi face went viral can police file FIR"
    meme = _joined(meme_query, meme_sources)
    assert _workflow_id(meme_query, meme_sources) == "public_political_meme_police_risk"
    assert "public-political" in meme
    assert "exact post" in meme
    assert "do not assume a normal meme automatically means arrest" in meme
    assert "written notice/FIR number" in meme
    assert "Representation of the People Act election-law lane" in meme

    emi_sources = [
        {"index": 1, "title": "Reserve Bank Integrated Ombudsman Scheme 2021", "anchor": "rbi-integrated-ombudsman-2021/sec-2"},
    ]
    emi_query = "normal EMI is late and lender sent reminder SMS is that harassment"
    emi = _joined(emi_query, emi_sources)
    assert _workflow_id(emi_query, emi_sources) == "ordinary_emi_reminder_not_harassment"
    assert "not automatically harassment" in emi
    assert "do not start with police" in emi
    assert "written lender complaint" in emi

    normal_loan_app_query = "loan app installed but only sends normal due date reminder, no threats or contacts"
    normal_loan_app = _grounded_joined(normal_loan_app_query, emi_sources)
    assert route_matter(normal_loan_app_query).action_pack.id != "loan_app_harassment"
    assert _workflow_id(normal_loan_app_query, emi_sources) == "ordinary_emi_reminder_not_harassment"
    assert "not automatically harassment" in normal_loan_app
    assert "threats, abuse, public shaming" in normal_loan_app

    trai_sources = [
        {"index": 1, "title": "Information Technology Act 2000", "anchor": "it-2000/sec-66D"},
        {"index": 2, "title": "Bharatiya Nyaya Sanhita 2023", "anchor": "bns-2023/sec-318"},
        {"index": 3, "title": "Bharatiya Nagarik Suraksha Sanhita 2023", "anchor": "bnss-2023/sec-173"},
    ]
    trai_query = "fake TRAI video call said my SIM will close but I have not paid money"
    trai = _joined(trai_query, trai_sources)
    assert _workflow_id(trai_query, trai_sources) == "digital_arrest_impersonation_transfer"
    assert "fake TRAI/SIM-closure" in trai
    assert "not as a real arrest process" in trai
    assert "Do not send more money" in trai

    lpg_sources = [
        {"index": 1, "title": "Aadhaar Act 2016", "anchor": "aadhaar-2016/sec-7"},
        {"index": 2, "title": "Right to Information Act 2005", "anchor": "rti-2005/sec-6"},
    ]
    lpg_query = "Aadhaar authentication failed for LPG subsidy and portal gives no reason"
    lpg = _grounded_joined(lpg_query, lpg_sources)
    assert _workflow_id(lpg_query, lpg_sources) == "aadhaar_subsidy_auth_reason"
    assert "LPG subsidy" in lpg
    assert "written reason" in lpg
    assert "portal gives no reason" in lpg

    csam_sources = [
        {"index": 1, "title": "Protection of Children from Sexual Offences Act 2012", "anchor": "pocso-2012/sec-19"},
        {"index": 2, "title": "Information Technology Act 2000", "anchor": "it-2000/sec-67B"},
        {"index": 3, "title": "Bharatiya Nyaya Sanhita 2023", "anchor": "bns-2023/sec-77@2024-07-01"},
    ]
    csam_query = "minor girl's morphed nude is in school whatsapp group, teacher wants us to delete it"
    csam = _grounded_joined(csam_query, csam_sources)
    assert _workflow_id(csam_query, csam_sources) == "ai_child_sexual_image"
    assert "minor CSAM" in csam or "minor fake nude" in csam or "minor, child" in csam
    assert "IT Act child sexual-image" in csam
    assert "BNS voyeurism source" in csam
    assert "without forwarding the material" in csam

    lookalike = _joined(
        "my face put on porn video on reddit but body is not mine, can I remove it",
        [
            {"index": 1, "title": "Information Technology Act 2000", "anchor": "it-2000/sec-66E"},
            {"index": 2, "title": "Bharatiya Nyaya Sanhita 2023", "anchor": "bns-2023/sec-77"},
        ],
    )
    assert "lookalike" in lookalike
    assert "Reddit" in lookalike
    assert "takedown/removal" in lookalike


def test_canary_family_identity_and_heir_workflows_own_rendered_answers():
    cases = [
        (
            "I found my wife living with another man after marriage what case can I file",
            "spousal_adultery_marriage_breakdown",
            "authority_graph",
            [
                {"index": 1, "title": "Family Courts Act 1984", "anchor": "family-courts-1984/sec-7"},
                {"index": 2, "title": "Hindu Marriage Act 1955", "anchor": "hindu-marriage-1955/sec-13"},
            ],
            ("marriage-breakdown", "Family Court/DLSA", "not as an automatic police case"),
        ),
        (
            "both of us agree for mutual divorce no children how many papers needed",
            "mutual_consent_divorce",
            "authority_graph",
            [
                {"index": 1, "title": "Family Courts Act 1984", "anchor": "family-courts-1984/sec-7"},
                {"index": 2, "title": "Hindu Marriage Act 1955", "anchor": "hindu-marriage-1955/sec-13-b"},
                {"index": 3, "title": "Special Marriage Act 1954", "anchor": "special-marriage-1954/sec-28"},
            ],
            ("mutual-consent divorce", "Section 13B", "no children", "joint petition"),
        ),
        (
            "we are christian couple want mutual consent divorce both agree",
            "mutual_consent_divorce",
            "authority_graph",
            [
                {"index": 1, "title": "Family Courts Act 1984", "anchor": "family-courts-1984/sec-7"},
                {"index": 2, "title": "Divorce Act 1869 (Indian Divorce Act - Christian marriages)", "anchor": "indian-divorce-1869/sec-2__2"},
                {"index": 3, "title": "Special Marriage Act 1954", "anchor": "special-marriage-1954/sec-28"},
            ],
            ("Christian/church", "Divorce Act route", "instead of assuming the Hindu Marriage Act"),
        ),
        (
            "mutual consent divorce muslim couple both agree procedure",
            "mutual_consent_divorce",
            "authority_graph",
            [
                {"index": 1, "title": "Family Courts Act 1984", "anchor": "family-courts-1984/sec-7"},
                {"index": 2, "title": "Dissolution of Muslim Marriages Act 1939", "anchor": "dissolution-muslim-marriages-1939/sec-5"},
                {"index": 3, "title": "Muslim Personal Law (Shariat) Application Act 1937", "anchor": "shariat-1937/sec-2"},
                {"index": 4, "title": "Special Marriage Act 1954", "anchor": "special-marriage-1954/sec-28"},
            ],
            ("Muslim marriage", "do not assume the Special Marriage Act", "personal-law route"),
        ),
        (
            "PAN card copy leaked online and fake bank account opened in my name",
            "pan_leak_fake_bank_account",
            "authority_graph",
            [
                {"index": 1, "title": "Digital Personal Data Protection Act 2023", "anchor": "dpdp-2023/sec-8"},
                {"index": 2, "title": "Information Technology Act 2000", "anchor": "it-2000/sec-66C"},
                {"index": 3, "title": "Reserve Bank Integrated Ombudsman Scheme 2021", "anchor": "rbi-integrated-ombudsman-2021/sec-2"},
                {"index": 4, "title": "Bharatiya Nyaya Sanhita 2023", "anchor": "bns-2023/sec-319"},
                {"index": 5, "title": "Bharatiya Nagarik Suraksha Sanhita 2023", "anchor": "bnss-2023/sec-173"},
            ],
            ("DPDP personal-data breach", "IT Act identity/electronic misuse", "bank/RBI Ombudsman"),
        ),
        (
            "father died one sister refuses to sign sale of house what to do",
            "heir_refuses_sale",
            "authority_graph",
            [
                {"index": 1, "title": "Indian Succession Act 1925", "anchor": "indian-succession-1925/sec-48"},
                {"index": 2, "title": "Hindu Succession Act 1956 (with 2005 amendment)", "anchor": "hindu-succession-1956/sec-10"},
                {"index": 3, "title": "Transfer of Property Act 1882", "anchor": "transfer-of-property-1882/sec-44"},
                {"index": 4, "title": "Specific Relief Act 1963", "anchor": "specific-relief-1963/sec-31"},
            ],
            ("sister", "Hindu Succession", "partition, declaration, injunction", "sale proof"),
        ),
        (
            "uncle sold ancestral land without asking other heirs where to go",
            "heir_refuses_sale",
            "authority_graph",
            [
                {"index": 1, "title": "Specific Relief Act 1963", "anchor": "specific-relief-1963/sec-31"},
                {"index": 2, "title": "Hindu Succession Act 1956 (with 2005 amendment)", "anchor": "hindu-succession-1956/sec-10"},
                {"index": 3, "title": "Transfer of Property Act 1882", "anchor": "transfer-of-property-1882/sec-45"},
            ],
            ("uncle sold ancestral land", "heirs", "civil court", "sale proof"),
        ),
    ]

    for query, expected_id, expected_owner, passages, required_terms in cases:
        route = route_matter(query)
        workflow = common_workflow_contract_result(query, route, passages)
        rendered = _grounded_template_lines(query, route, passages)
        payload = _workflow_event_payload(query, passages, rendered)
        rendered_text = " ".join(rendered)

        assert workflow is not None
        assert workflow.id == expected_id
        assert workflow.source == expected_owner
        assert workflow.answer_mode == "primary"
        assert rendered == workflow.lines
        assert payload["id"] == expected_id
        assert payload["answer_owner"] == expected_owner
        assert payload["workflow_shadowed_by_legacy"] is False
        for term in required_terms:
            assert term in rendered_text


def test_stage3_property_workflows_own_common_user_answers():
    cases = [
        (
            "mother died and two brothers are blocking mutation of her house",
            "mutation_after_death",
            "common_workflow_contracts",
            [
                {"index": 1, "title": "Hindu Succession Act 1956", "anchor": "hindu-succession-1956/sec-8"},
                {"index": 2, "title": "Right to Information Act 2005", "anchor": "rti-2005/sec-6"},
            ],
            ("mutation after a parent's death", "brothers", "written objection", "does not by itself prove marketable title"),
        ),
        (
            "ancestral land brothers saying daughters have no share",
            "daughter_ancestral_share",
            "authority_graph",
            [
                {"index": 1, "title": "Hindu Succession Act 1956", "anchor": "hindu-succession-1956/sec-6"},
                {"index": 2, "title": "Specific Relief Act 1963", "anchor": "specific-relief-1963/sec-34"},
            ],
            ("daughters have no share", "Section 6", "family tree", "partition"),
        ),
        (
            "housing society not transferring flat after father death to legal heirs",
            "housing_society_flat_transfer_after_death",
            "authority_graph",
            [
                {"index": 1, "title": "Hindu Succession Act 1956", "anchor": "hindu-succession-1956/sec-8"},
                {"index": 2, "title": "Registration Act 1908", "anchor": "registration-1908/sec-17"},
                {"index": 3, "title": "Transfer of Property Act 1882", "anchor": "transfer-of-property-1882/sec-44"},
                {"index": 4, "title": "Specific Relief Act 1963", "anchor": "specific-relief-1963/sec-34"},
            ],
            ("housing-society flat transfer", "legal heirship and title", "nominee", "Registrar/cooperative authority"),
        ),
    ]

    for query, expected_id, expected_owner, passages, required_terms in cases:
        route = route_matter(query)
        workflow = common_workflow_contract_result(query, route, passages)
        rendered = _grounded_template_lines(query, route, passages)
        payload = _workflow_event_payload(query, passages, rendered)
        rendered_text = " ".join(rendered)

        assert workflow is not None
        assert workflow.id == expected_id
        assert workflow.source == expected_owner
        assert workflow.answer_mode == "primary"
        assert rendered == workflow.lines
        assert payload["id"] == expected_id
        assert payload["answer_owner"] == expected_owner
        assert payload["workflow_shadowed_by_legacy"] is False
        for term in required_terms:
            assert term in rendered_text


def test_common_workflow_contract_handles_recovery_agent_and_cyber_money_lanes():
    recovery = _joined(
        "loan recovery agents came home and threatened my mother",
        LOAN_APP_REGULATORY_SOURCES,
    )
    assert "recovery-agent circular prohibits" in recovery
    assert "RBI Ombudsman" in recovery
    assert "family members, referees, and friends" in recovery
    assert "threat recordings" in recovery or "call logs" in recovery

    office_recovery = _joined(
        "recovery agent came to my office shouting EMI default in front of staff",
        LOAN_APP_REGULATORY_SOURCES,
    )
    assert "recovery agent came to office" in office_recovery
    assert "EMI default in front of staff" in office_recovery
    assert "RBI Ombudsman/CMS" in office_recovery

    cyber_money = _joined(
        "fake customer care made me install app and money got transferred",
        [
            {"index": 1, "title": "Information Technology Act 2000", "anchor": "it-2000/sec-66D"},
            {"index": 2, "title": "Reserve Bank Integrated Ombudsman Scheme 2021", "anchor": "rbi-integrated-ombudsman-2021/sec-2"},
            {"index": 3, "title": "Bharatiya Nyaya Sanhita 2023", "anchor": "bns-2023/sec-318"},
        ],
    )
    assert "fake customer-care remote-access transfer" in cyber_money
    assert "IT Act cyber-fraud track" in cyber_money
    assert "RBI Ombudsman/CMS" in cyber_money
    assert "1930 or cybercrime.gov.in" in cyber_money
    assert "transaction ID/RRN" in cyber_money

    anydesk = _joined(
        "fake customer care made me install AnyDesk and emptied account what to do first",
        [
            {"index": 1, "title": "Information Technology Act 2000", "anchor": "it-2000/sec-66D"},
            {"index": 2, "title": "Reserve Bank Integrated Ombudsman Scheme 2021", "anchor": "rbi-integrated-ombudsman-2021/sec-2"},
            {"index": 3, "title": "Bharatiya Nyaya Sanhita 2023", "anchor": "bns-2023/sec-318"},
        ],
    )
    assert "AnyDesk" in anydesk
    assert "bank" in anydesk
    assert "cyber" in anydesk


def test_common_workflow_contract_handles_upi_seller_payment_refund():
    answer = _joined(
        "Amazon refund failed, UPI shows success but seller says payment not received",
        [
            {"index": 1, "title": "Consumer Protection Act 2019", "anchor": "consumer-protection-2019/sec-35"},
            {"index": 2, "title": "Reserve Bank Integrated Ombudsman Scheme 2021", "anchor": "rbi-integrated-ombudsman-2021/sec-2"},
        ],
    )
    assert "seller" in answer
    assert "UPI/payment transaction" in answer
    assert "RBI Ombudsman/CMS" in answer
    assert "UPI transaction ID/RRN" in answer


def test_common_workflow_contract_handles_scholarship_aadhaar_name_mismatch():
    answer = _joined(
        "scholarship rejected because Aadhaar name and school certificate name not same",
        [
            {"index": 1, "title": "Aadhaar (Targeted Delivery of Financial and Other Subsidies, Benefits and Services) Act 2016", "anchor": "aadhaar-2016/sec-29"},
            {"index": 2, "title": "Right to Information Act 2005", "anchor": "rti-2005/sec-19"},
        ],
    )
    assert "Aadhaar" in answer
    assert "written reasons" in answer
    assert "which record needs correction" in answer


def test_common_workflow_contract_handles_fresh50_critical_families():
    digital_arrest = _joined(
        "fake CBI call kept me on video and asked for bank transfer",
        [
            {"index": 1, "title": "Information Technology Act 2000", "anchor": "it-2000/sec-66D"},
            {"index": 2, "title": "Bharatiya Nyaya Sanhita 2023", "anchor": "bns-2023/sec-318"},
            {"index": 3, "title": "Bharatiya Nagarik Suraksha Sanhita 2023", "anchor": "bnss-2023/sec-173"},
        ],
    )
    assert "fake CBI" in digital_arrest
    assert "BNS track" in digital_arrest
    assert "BNSS FIR/information" in digital_arrest
    assert "Do not send more money" in digital_arrest

    cyber_notice = _joined(
        "police calling me for notice in cyber case but not giving paper",
        [
            {"index": 1, "title": "Bharatiya Nagarik Suraksha Sanhita 2023", "anchor": "bnss-2023/sec-35"},
            {"index": 2, "title": "Information Technology Act 2000", "anchor": "it-2000/sec-66D"},
        ],
    )
    assert "written notice, FIR/complaint number" in cyber_notice
    assert "accused, witness, or complainant" in cyber_notice
    assert "before giving devices, passwords, or a statement" in cyber_notice

    domestic = _joined(
        "in laws beat me and took my phone i am unsafe",
            [
                {"index": 1, "title": "Protection of Women from Domestic Violence Act 2005", "anchor": "domestic-violence-2005/sec-3"},
                {"index": 2, "title": "Bharatiya Nyaya Sanhita 2023", "anchor": "bns-2023/sec-115"},
                {"index": 3, "title": "Bharatiya Nagarik Suraksha Sanhita 2023", "anchor": "bnss-2023/sec-173"},
                {"index": 4, "title": "Protection of Women from Domestic Violence Act 2005", "anchor": "domestic-violence-2005/sec-12"},
            ],
    )
    assert "treat immediate safety first" in domestic
    assert "contact 112/police" in domestic
    assert "separate BNS criminal track" in domestic
    assert "Protection Officer" in domestic
    assert "BNSS FIR/information and Magistrate-escalation route" in domestic

    arrest = _grounded_joined(
        "police took my brother at midnight and not telling station or case",
        [
            {"index": 1, "title": "Constitution of India", "anchor": "constitution-india/sec-22"},
            {"index": 2, "title": "Constitution of India", "anchor": "constitution-india/sec-226"},
            {"index": 3, "title": "Bharatiya Nagarik Suraksha Sanhita 2023", "anchor": "bnss-2023/sec-531"},
        ],
    )
    assert "hidden police pickup as an urgent liberty issue" in arrest
    assert "FIR copy" in arrest
    assert "habeas corpus" in arrest

    caste = _joined(
        "neighbour used caste slur and hit me but station refuses case",
        [
            {"index": 1, "title": "Scheduled Castes and Scheduled Tribes (Prevention of Atrocities) Act 1989", "anchor": "sc-st-poa-1989/sec-3-d"},
            {"index": 2, "title": "Bharatiya Nagarik Suraksha Sanhita 2023", "anchor": "bnss-2023/sec-173"},
            {"index": 3, "title": "Bharatiya Nyaya Sanhita 2023", "anchor": "bns-2023/sec-115"},
        ],
    )
    assert "SC/ST Prevention of Atrocities Act route" in caste
    assert "station refuses the FIR" in caste
    assert "Special Court/DLSA" in caste


def test_common_workflow_contract_handles_fresh50_common_relevance_families():
    maintenance = _joined(
        "court ordered maintenance but husband is not paying for 8 months",
        [
            {"index": 1, "title": "Family Courts Act 1984", "anchor": "family-courts-1984/sec-7"},
            {"index": 2, "title": "Bharatiya Nagarik Suraksha Sanhita 2023", "anchor": "bnss-2023/sec-144"},
            {"index": 3, "title": "Protection of Women from Domestic Violence Act 2005", "anchor": "domestic-violence-2005/sec-20"},
        ],
    )
    assert "enforcement or arrears of a maintenance order" in maintenance
    assert "arrears month-wise chart" in maintenance

    hand_loan = _joined(
        "i gave 3 lakh to cousin by upi now he is avoiding calls",
        [
            {"index": 1, "title": "Indian Contract Act 1872", "anchor": "indian-contract-1872/sec-37"},
            {"index": 2, "title": "Limitation Act 1963", "anchor": "limitation-1963/sec-3"},
            {"index": 3, "title": "Code of Civil Procedure 1908", "anchor": "cpc-1908#header"},
        ],
    )
    assert "family/friendly hand loan" in hand_loan
    assert "UPI/bank proof" in hand_loan
    assert "limitation" in hand_loan.lower()

    senior = _joined(
        "son not taking care of old father and took his pension",
        [
            {"index": 1, "title": "Maintenance and Welfare of Parents and Senior Citizens Act 2007", "anchor": "mwp-2007/sec-4"},
            {"index": 2, "title": "Hindu Adoptions and Maintenance Act 1956", "anchor": "hindu-adoptions-maintenance-1956/sec-20"},
        ],
    )
    assert "pension control, maintenance, and support" in senior
    assert "pension or passbook money" in senior
    assert "Maintenance Tribunal" in senior

    salary = _joined(
        "employer fired me and holding last month salary",
        [
            {"index": 1, "title": "Code on Wages 2019", "anchor": "code-on-wages-2019/sec-45"},
            {"index": 2, "title": "Industrial Disputes Act 1947", "anchor": "industrial-disputes-1947/sec-25F-b"},
        ],
    )
    assert "holding last-month salary" in salary
    assert "Labour Commissioner/wage authority" in salary

    marriage = _joined(
        "husband lied before marriage about salary and loans what remedy",
        [
            {"index": 1, "title": "Hindu Marriage Act 1955", "anchor": "hindu-marriage-1955/sec-12"},
            {"index": 2, "title": "Family Courts Act 1984", "anchor": "family-courts-1984/sec-7"},
        ],
    )
    assert "salary, job, loans" in marriage
    assert "not every lie automatically cancels a marriage" in marriage


def test_common_workflow_contract_handles_composite_critical_user_failures():
    intimate = _joined(
        "girl on video call recorded me and demanding money",
        [
            {"index": 1, "title": "Information Technology Act 2000", "anchor": "it-2000/sec-66E"},
            {"index": 2, "title": "Bharatiya Nyaya Sanhita 2023", "anchor": "bns-2023/sec-351"},
            {"index": 3, "title": "Bharatiya Nagarik Suraksha Sanhita 2023", "anchor": "bnss-2023/sec-173"},
        ],
    )
    assert "non-consensual intimate-image problem" in intimate
    assert "BNS extortion/intimidation/sexual-image track" in intimate
    assert "Do not pay or forward" in intimate
    assert "cybercrime.gov.in/1930" in intimate

    intimate_paraphrase = _joined(
        "someone recorded video call and says he will send to my relatives if i dont pay",
        [
            {"index": 1, "title": "Information Technology Act 2000", "anchor": "it-2000/sec-66E"},
            {"index": 2, "title": "Bharatiya Nyaya Sanhita 2023", "anchor": "bns-2023/sec-351"},
            {"index": 3, "title": "Bharatiya Nagarik Suraksha Sanhita 2023", "anchor": "bnss-2023/sec-173"},
        ],
    )
    assert "recorded private video/image" in intimate_paraphrase
    assert "blackmail" in intimate_paraphrase
    assert "Do not pay or forward" in intimate_paraphrase

    witch = _joined(
        "ojha branded my aunt witch and stripped her in public",
        [
            {"index": 1, "title": "Bharatiya Nyaya Sanhita 2023", "anchor": "bns-2023/sec-76"},
            {"index": 2, "title": "Bharatiya Nagarik Suraksha Sanhita 2023", "anchor": "bnss-2023/sec-173"},
        ],
    )
    assert "urgent police-protection and criminal-violence issue" in witch
    assert "public stripping/disrobing" in witch
    assert "exact witch/black-magic words" in witch
    assert "police, SP, DLSA" in witch

    false_fir = _joined(
        "neighbour made false 420 case on me because of money dispute",
        [
            {"index": 1, "title": "Bharatiya Nagarik Suraksha Sanhita 2023", "anchor": "bnss-2023/sec-483"},
            {"index": 2, "title": "Bharatiya Nagarik Suraksha Sanhita 2023", "anchor": "bnss-2023/sec-173"},
        ],
    )
    assert "false FIR or false 420 case" in false_fir
    assert "do not start with a final quashing claim" in false_fir
    assert "arrest or notice status" in false_fir
    assert "bail/appearance risk" in false_fir

    cab = _joined(
        "ola driver took longer route and charged extra fare customer care not helping",
        [
            {"index": 1, "title": "Consumer Protection Act 2019", "anchor": "consumer-protection-2019/sec-35"},
            {"index": 2, "title": "Motor Vehicle Aggregator Guidelines 2020", "anchor": "motor-vehicle-aggregator-guidelines-2020/app-transparency-grievance"},
        ],
    )
    assert "Ola longer-route extra-fare dispute" in cab
    assert "passenger" in cab
    assert "Motor Vehicle Aggregator Guidelines source" in cab
    assert "trip ID" in cab
    assert "transport/RTO aggregator authority" in cab


def test_common_workflow_contract_handles_stage11_remaining_workflow_frames():
    custody = _joined(
        "wife not allowing me to meet my child after separation",
        [
            {"index": 1, "title": "Guardians and Wards Act 1890", "anchor": "guardians-wards-1890/sec-17"},
            {"index": 2, "title": "Family Courts Act 1984", "anchor": "family-courts-1984/sec-7"},
        ],
    )
    assert "not allowing you to meet your child after separation" in custody
    assert "custody/access and child-welfare issue" in custody
    assert "interim visitation or access directions" in custody

    streedhan = _joined(
        "husband kept my streedhan locker keys and refusing return",
        [
            {"index": 1, "title": "Protection of Women from Domestic Violence Act 2005", "anchor": "domestic-violence-2005/sec-3"},
            {"index": 2, "title": "Bharatiya Nyaya Sanhita 2023", "anchor": "bns-2023/sec-316"},
            {"index": 3, "title": "Dowry Prohibition Act 1961", "anchor": "dowry-prohibition-1961/sec-10"},
        ],
    )
    assert "streedhan locker keys" in streedhan
    assert "economic-abuse" in streedhan
    assert "criminal-breach-of-trust track" in streedhan
    assert "item-wise streedhan list" in streedhan

    street = _joined(
        "hawker zone people are removing my vegetable stall what to do",
        [
            {"index": 1, "title": "Street Vendors (Protection of Livelihood and Regulation of Street Vending) Act 2014", "anchor": "street-vendors-2014/sec-18"},
            {"index": 2, "title": "Street Vendors (Protection of Livelihood and Regulation of Street Vending) Act 2014", "anchor": "street-vendors-2014/sec-19"},
        ],
    )
    assert "removing your vegetable stall" in street
    assert "Street Vendors Act/Town Vending Committee" in street
    assert "seizure list/inventory" in street

    goods_not_returned = _joined(
        "street vendor cart removed by municipal staff and goods not returned",
        [
            {"index": 1, "title": "Street Vendors (Protection of Livelihood and Regulation of Street Vending) Act 2014", "anchor": "street-vendors-2014/sec-19"},
            {"index": 2, "title": "Street Vendors (Protection of Livelihood and Regulation of Street Vending) Act 2014", "anchor": "street-vendors-2014/sec-20"},
            {"index": 3, "title": "Street Vendors (Protection of Livelihood and Regulation of Street Vending) Act 2014", "anchor": "street-vendors-2014/sec-4"},
        ],
    )
    assert "goods are not returned" in goods_not_returned
    assert "signed copy/receipt" in goods_not_returned
    assert "written release date" in goods_not_returned
    assert "Town Vending Committee" in goods_not_returned

    before_hearing = _joined(
        "hawker license pending but corporation removed my stall before hearing",
        [
            {"index": 1, "title": "Street Vendors (Protection of Livelihood and Regulation of Street Vending) Act 2014", "anchor": "street-vendors-2014/sec-19"},
            {"index": 2, "title": "Street Vendors (Protection of Livelihood and Regulation of Street Vending) Act 2014", "anchor": "street-vendors-2014/sec-20"},
            {"index": 3, "title": "Street Vendors (Protection of Livelihood and Regulation of Street Vending) Act 2014", "anchor": "street-vendors-2014/sec-4"},
        ],
    )
    assert "licence/certificate application is pending" in before_hearing
    assert "removed before a hearing" in before_hearing
    assert "pending-application status" in before_hearing

    crypto = _joined(
        "crypto exchange froze my wallet and support not replying",
        [
            {"index": 1, "title": "Consumer Protection Act 2019", "anchor": "consumer-protection-2019/sec-35"},
            {"index": 2, "title": "Information Technology Act 2000", "anchor": "it-2000/sec-79"},
            {"index": 3, "title": "Prevention of Money Laundering Act 2002", "anchor": "pmla-2002/sec-8"},
        ],
    )
    assert "crypto exchange froze your wallet" in crypto
    assert "consumer/platform-service grievance track" in crypto
    assert "IT Act/electronic-record track" in crypto
    assert "wallet ID" in crypto


def test_common_workflow_contract_handles_blocker_paraphrase_variants():
    custody = _joined(
        "court order not there but mother not allowing father to see child",
        [
            {"index": 1, "title": "Guardians and Wards Act 1890", "anchor": "guardians-wards-1890/sec-17"},
            {"index": 2, "title": "Family Courts Act 1984", "anchor": "family-courts-1984/sec-7"},
        ],
    )
    assert "custody/access and child-welfare issue" in custody
    assert "parent-child access, visitation, calls" in custody
    assert "Family Court" in custody

    child_return = _joined(
        "husband took child and not letting mother see her",
        [
            {"index": 1, "title": "Guardians and Wards Act 1890", "anchor": "guardians-wards-1890/sec-17"},
            {"index": 2, "title": "Family Courts Act 1984", "anchor": "family-courts-1984/sec-7"},
        ],
    )
    assert "custody/access and child-welfare issue" in child_return
    assert "Family Courts Act source" in child_return
    assert "interim visitation or access directions" in child_return

    child_video_calls = _joined(
        "my husband is hiding our son and not allowing video calls",
        [
            {"index": 1, "title": "Guardians and Wards Act 1890", "anchor": "guardians-wards-1890/sec-17"},
            {"index": 2, "title": "Family Courts Act 1984", "anchor": "family-courts-1984/sec-7"},
        ],
    )
    assert "custody/access and child-welfare issue" in child_video_calls
    assert "video" in child_video_calls or "hiding your son" in child_video_calls
    assert "interim visitation or access directions" in child_video_calls

    false_case = _joined(
        "business partner put false cheating 420 FIR against me for loan money",
        [
            {"index": 1, "title": "Bharatiya Nagarik Suraksha Sanhita 2023", "anchor": "bnss-2023/sec-528"},
            {"index": 2, "title": "Bharatiya Nyaya Sanhita 2023", "anchor": "bns-2023/sec-318"},
            {"index": 3, "title": "Bharatiya Nagarik Suraksha Sanhita 2023", "anchor": "bnss-2023/sec-483"},
        ],
    )
    assert "business partner over loan money" in false_case
    assert "arrest or notice status" in false_case
    assert "criminal lawyer/DLSA" in false_case

    witch = _joined(
        "village ojha called my chachi dayan and tore her clothes in public",
        [
            {"index": 1, "title": "Bharatiya Nyaya Sanhita 2023", "anchor": "bns-2023/sec-76"},
            {"index": 2, "title": "Bharatiya Nagarik Suraksha Sanhita 2023", "anchor": "bnss-2023/sec-173"},
        ],
    )
    assert "your chachi/aunt" in witch
    assert "dayan/daayan" in witch
    assert "public stripping/disrobing" in witch
    assert "urgent police-protection" in witch

    mausi = _joined(
        "village panchayat called my mausi daayan and forced her to leave home",
        [
            {"index": 1, "title": "Bharatiya Nyaya Sanhita 2023", "anchor": "bns-2023/sec-351"},
            {"index": 2, "title": "Bharatiya Nagarik Suraksha Sanhita 2023", "anchor": "bnss-2023/sec-173"},
        ],
    )
    assert "your mausi/aunt" in mausi
    assert "threatened village removal/expulsion" in mausi
    assert "urgent police-protection" in mausi


def test_wage_false_fir_prompt_window_preserves_criminal_sources():
    query = "contractor not paid wages now filed false mobile theft case"
    route = route_matter(query)
    retrieved = [
        SimpleNamespace(title="Code on Wages 2019", anchor="code-on-wages-2019/sec-45"),
        SimpleNamespace(title="Code on Social Security 2020", anchor="social-security-code-2020/sec-114-a"),
        SimpleNamespace(title="Bharatiya Nagarik Suraksha Sanhita 2023", anchor="bnss-2023/sec-173"),
        SimpleNamespace(title="Bharatiya Nyaya Sanhita 2023", anchor="bns-2023/sec-303"),
        SimpleNamespace(title="Occupational Safety Code 2020", anchor="osh-code-2020/sec-114"),
    ]

    filtered = _prompt_retrieval_candidates(query, route, retrieved)
    titles = " ".join(item.title for item in filtered)

    assert "Code on Wages" in titles
    assert "Bharatiya Nagarik Suraksha" in titles
    assert "Bharatiya Nyaya" in titles
    assert all("Social Security" not in item.title for item in filtered)


def test_loan_app_prompt_window_preserves_all_registry_sources_and_drops_decoy():
    query = "Loan app is harassing my contacts and calling my boss. What can I do?"
    route = route_matter(query)
    retrieved = [
        SimpleNamespace(index=source["index"], title=source["title"], anchor=source["anchor"])
        for source in LOAN_APP_REGULATORY_SOURCES
    ] + [
        SimpleNamespace(
            index=99,
            title="Banking Regulation Act 1949",
            anchor="banking-regulation-1949/sec-45za",
        )
    ]

    filtered = _prompt_retrieval_candidates(query, route, retrieved)
    anchors = {item.anchor for item in filtered}

    assert len(filtered) == 8
    assert "rbi-digital-lending-directions-2025/para-11" in anchors
    assert "rbi-digital-lending-directions-2025/para-12" in anchors
    assert "rbi-recovery-agents-2022/para-2" in anchors
    assert "banking-regulation-1949/sec-45za" not in anchors


def test_common_workflow_contract_handles_family_intimacy_safely():
    answer = _joined(
        "my wife is denying sex since many years what to do",
        [
            {"index": 1, "title": "Family Courts Act 1984", "anchor": "family-courts-1984/sec-7"},
            {"index": 2, "title": "Hindu Marriage Act 1955", "anchor": "hindu-marriage-1955/sec-13"},
        ],
    )
    assert "marriage-breakdown or matrimonial-remedy" in answer
    assert "Consent matters" in answer
    assert "do not force, threaten, or pressure" in answer
    assert "Section 13 divorce-ground" in answer
    assert "matrimonial-relief source with the full facts" in answer


def test_common_workflow_contract_handles_paraphrase_stress_families():
    pds = _joined(
        "dealer stopped giving grain saying mother deleted from family card without notice",
        [
            {"index": 1, "title": "National Food Security Act 2013", "anchor": "national-food-security-2013/sec-14"},
            {"index": 2, "title": "Right to Information Act 2005", "anchor": "rti-2005/sec-6"},
        ],
    )
    assert "dealer stopped giving grain" in pds
    assert "NFSA ration-card entitlement" in pds
    assert "written deletion or cancellation order" in pds
    assert "ration-card file" in pds

    domestic = _joined(
        "my husband assaulted me today and keeps saying he will evict me from matrimonial home",
        [
            {"index": 1, "title": "Protection of Women from Domestic Violence Act 2005", "anchor": "domestic-violence-2005/sec-3"},
            {"index": 4, "title": "Protection of Women from Domestic Violence Act 2005", "anchor": "domestic-violence-2005/sec-18"},
            {"index": 2, "title": "Bharatiya Nyaya Sanhita 2023", "anchor": "bns-2023/sec-117"},
            {"index": 3, "title": "Bharatiya Nagarik Suraksha Sanhita 2023", "anchor": "bnss-2023/sec-173"},
            {"index": 5, "title": "Protection of Women from Domestic Violence Act 2005", "anchor": "domestic-violence-2005/sec-12"},
        ],
    )
    assert "domestic violence" in domestic
    assert "matrimonial home" in domestic
    assert "BNSS FIR/information and Magistrate-escalation route" in domestic
    assert "Protection Officer" in domestic

    coercion = _grounded_joined(
        "husband forcing me for sex and threatening me what should i do",
        [
            {"index": 1, "title": "Protection of Women from Domestic Violence Act 2005", "anchor": "domestic-violence-2005/sec-3"},
            {"index": 2, "title": "Bharatiya Nyaya Sanhita 2023", "anchor": "bns-2023/sec-115"},
            {"index": 3, "title": "Bharatiya Nagarik Suraksha Sanhita 2023", "anchor": "bnss-2023/sec-173"},
            {"index": 4, "title": "Protection of Women from Domestic Violence Act 2005", "anchor": "domestic-violence-2005/sec-12"},
        ],
    )
    assert "forcing you for sex" in coercion
    assert "threatening you" in coercion
    assert "domestic violence and safety" in coercion
    assert "sexual abuse and related physical or emotional harm" in coercion
    assert "Protection Officer" in coercion
    assert "move to a safe place or trusted person first" in coercion
    assert "Protection Officer" in coercion

    thrown_out = _grounded_joined(
        "spouse threatens to throw me out if i refuse sex",
        [
            {"index": 1, "title": "Protection of Women from Domestic Violence Act 2005", "anchor": "domestic-violence-2005/sec-18"},
            {"index": 2, "title": "Bharatiya Nyaya Sanhita 2023", "anchor": "bns-2023/sec-351"},
        ],
    )
    assert "domestic violence and safety" in thrown_out
    assert "move to a safe place or trusted person first" in thrown_out

    maintenance = _joined(
        "magistrate maintenance order is there but husband not depositing amount for many months",
        [
            {"index": 1, "title": "Family Courts Act 1984", "anchor": "family-courts-1984/sec-7"},
            {"index": 2, "title": "Bharatiya Nagarik Suraksha Sanhita 2023", "anchor": "bnss-2023/sec-144-a"},
            {"index": 3, "title": "Protection of Women from Domestic Violence Act 2005", "anchor": "domestic-violence-2005/sec-20"},
            {"index": 4, "title": "Code of Criminal Procedure 1973", "anchor": "crpc-1973/sec-125-b"},
        ],
    )
    assert "court-ordered maintenance" in maintenance
    assert "enforcement/execution or arrears application" in maintenance
    assert "Magistrate" in maintenance or "Family Court" in maintenance


def test_common_workflow_contract_handles_heir_sale_and_municipal_sealing():
    heir = _joined(
        "can i sell property if one legal heir is not agreeing",
        [
            {"index": 1, "title": "Hindu Succession Act 1956", "anchor": "hindu-succession-1956/sec-8"},
            {"index": 2, "title": "Transfer of Property Act 1882", "anchor": "transfer-of-property-1882/sec-44"},
            {"index": 3, "title": "Specific Relief Act 1963", "anchor": "specific-relief-1963/sec-34"},
        ],
    )
    assert "legal heir, succession, inherited-property status" in heir
    assert "majority heirs can sell the entire property" not in heir
    assert "partition" in heir
    assert "death certificate" in heir

    tenancy_negative_query = "tenant not leaving my inherited house but no sale dispute among heirs"
    tenancy_sources = [
        {"index": 1, "title": "Hindu Succession Act 1956", "anchor": "hindu-succession-1956/sec-8"},
        {"index": 2, "title": "Transfer of Property Act 1882", "anchor": "transfer-of-property-1882/sec-44"},
        {"index": 3, "title": "Specific Relief Act 1963", "anchor": "specific-relief-1963/sec-34"},
        {"index": 4, "title": "Transfer of Property Act 1882", "anchor": "transfer-of-property-1882/sec-106"},
    ]
    tenancy_negative = _grounded_joined(tenancy_negative_query, tenancy_sources)
    assert route_matter(tenancy_negative_query).action_pack.id == "tenancy_eviction_nonpayment"
    assert _workflow_id(tenancy_negative_query, tenancy_sources) != "heir_refuses_sale"
    assert "tenant" in tenancy_negative.lower()
    assert "rent" in tenancy_negative.lower() or "vacat" in tenancy_negative.lower()

    sealing = _joined(
        "my shop is in gujarat and municipality sealed it",
        [
            {"index": 1, "title": "Right to Information Act 2005", "anchor": "rti-2005/sec-6"},
        ],
    )
    assert "retrieved passages do not contain the Gujarat municipal/shop source" in sealing
    assert "RTI is a records route, not the sealing power" in sealing

    sourced_sealing = _joined(
        "my shop is in gujarat and municipality sealed it",
        [
            {"index": 1, "title": "Gujarat Shops and Establishments Act", "anchor": "gujarat-shops-establishments-2019/sec-8"},
            {"index": 2, "title": "Gujarat Municipalities Act 1963", "anchor": "gujarat-municipalities-1963/sec-221"},
            {"index": 3, "title": "Right to Information Act 2005", "anchor": "rti-2005/sec-6"},
        ],
    )
    assert "Gujarat municipal/shop-registration" in sourced_sealing
    assert "sealing order" in sourced_sealing
    assert "de-sealing/reopen/release route" in sourced_sealing
    assert "use RTI as the records route" in sourced_sealing
    assert "[2]" in sourced_sealing

    vadodara_goods = _joined(
        "vadodara corporation sealed our commercial shop and goods are inside",
        [
            {"index": 1, "title": "Gujarat Shops and Establishments Act", "anchor": "gujarat-shops-establishments-2019/sec-8"},
            {"index": 2, "title": "Gujarat Municipalities Act 1963", "anchor": "gujarat-municipalities-1963/sec-221"},
            {"index": 3, "title": "Right to Information Act 2005", "anchor": "rti-2005/sec-6"},
        ],
    )
    assert "Vadodara municipal corporation commercial shop with goods inside being sealed" in vadodara_goods
    assert "goods-release procedure" in vadodara_goods
    assert "inventory of goods inside" in vadodara_goods

    hotel_sealing = _joined(
        "health department sealed my small hotel kitchen without giving inspection report",
        [
            {"index": 1, "title": "Food Safety and Standards Act 2006", "anchor": "food-safety-standards-2006/sec-32"},
            {"index": 2, "title": "Right to Information Act 2005", "anchor": "rti-2005/sec-6"},
        ],
    )
    assert "restaurant/hotel kitchen" in hotel_sealing
    assert "Food Safety/FSSAI licence-compliance notice" in hotel_sealing
    assert "inspection report" in hotel_sealing
    assert "RTI is a records route" in hotel_sealing


def test_heir_sale_prefers_generic_succession_source_without_hindu_context():
    heir = _grounded_joined(
        "can i sell inherited property if one legal heir is not agreeing",
        [
            {"index": 11, "title": "Indian Succession Act 1925", "anchor": "indian-succession-1925/sec-32"},
            {"index": 12, "title": "Hindu Succession Act 1956", "anchor": "hindu-succession-1956/sec-8"},
            {"index": 13, "title": "Transfer of Property Act 1882", "anchor": "transfer-of-property-1882/sec-44"},
            {"index": 14, "title": "Specific Relief Act 1963", "anchor": "specific-relief-1963/sec-34"},
        ],
    )

    assert "confirming the applicable personal law" in heir
    assert "[11]" in heir
    assert "Hindu Succession source where Hindu law applies" not in heir
    assert "does not prove that the whole property can be sold" in heir


def test_stage3b_workflow_contracts_cover_banking_revenue_consumer_and_license_misses():
    atm = _joined(
        "ATM cash not dispensed but account debited branch not helping",
        [
            {"index": 1, "title": "Reserve Bank Integrated Ombudsman Scheme 2021", "anchor": "rbi-integrated-ombudsman-2021/sec-2"},
            {"index": 2, "title": "Consumer Protection Act 2019", "anchor": "consumer-protection-2019/sec-35"},
        ],
    )
    assert "ATM cash-not-dispensed" in atm
    assert "RBI Ombudsman/CMS" in atm
    assert "ATM ID/location" in atm
    assert "forex markup/charge slip" not in atm

    cibil = _joined(
        "personal loan closed but bank not giving NOC and CIBIL still active",
        [
            {"index": 1, "title": "Credit Information Companies Act 2005", "anchor": "credit-information-companies-2005/sec-21"},
            {"index": 2, "title": "Reserve Bank Integrated Ombudsman Scheme 2021", "anchor": "rbi-integrated-ombudsman-2021/sec-2"},
        ],
    )
    assert "loan-closure statement" in cibil
    assert "NOC/no-dues certificate" in cibil
    assert "credit-bureau dispute" in cibil

    mutation = _joined(
        "father died mutation not updated in patwari record rajasthan where to go",
        [
            {"index": 1, "title": "Hindu Succession Act 1956", "anchor": "hindu-succession-1956/sec-8"},
            {"index": 2, "title": "Right to Information Act 2005", "anchor": "rti-2005/sec-6"},
        ],
    )
    assert "Rajasthan patwari/revenue record mutation" in mutation
    assert "death certificate" in mutation
    assert "does not by itself prove marketable title" in mutation

    bribe = _joined(
        "patwari asking 5000 rupees to enter my name in revenue records can I complain where to go",
        [
            {"index": 1, "title": "Andhra Pradesh Rights in Land and Pattadar Pass Books Act 1971", "anchor": "andhra-pradesh-rights-land-pattadar-passbooks-1971/sec-4"},
            {"index": 2, "title": "Prevention of Corruption Act 1988", "anchor": "prevention-of-corruption-1988/sec-7"},
            {"index": 3, "title": "Right to Information Act 2005", "anchor": "rti-2005/sec-6"},
        ],
    )
    assert "separate the bribe demand from the land-record correction" in bribe
    assert "official fee/challan" in bribe
    assert "Anti-Corruption Bureau/Lokayukta/vigilance" in bribe
    assert "[1]" not in bribe

    passbook = _joined(
        "pattadar passbook lost in flood tehsildar saying come next month where to go",
        [
            {"index": 1, "title": "Andhra Pradesh Rights in Land and Pattadar Pass Books Act 1971", "anchor": "andhra-pradesh-rights-land-pattadar-passbooks-1971/sec-6F-7"},
            {"index": 2, "title": "Right to Information Act 2005", "anchor": "rti-2005/sec-6"},
        ],
    )
    assert "certified-copy / passbook-status problem" in passbook
    assert "oral 'come next month' answer" in passbook
    assert "flood/loss proof" in passbook

    subscription = _joined(
        "app charged yearly subscription after cancellation support not refunding",
        [
            {"index": 1, "title": "Consumer Protection Act 2019", "anchor": "consumer-protection-2019/sec-35"},
        ],
    )
    assert "yearly app subscription charged after cancellation" in subscription
    assert "cancellation proof" in subscription
    assert "National Consumer Helpline/e-Daakhil/District Commission" in subscription

    shop = _joined(
        "tamil nadu shop license renewal pending 2 years coimbatore shopkeeper penalty kaise calculate",
        [
            {"index": 1, "title": "Tamil Nadu Shops and Establishments Act 1947", "anchor": "tamil-nadu-shops-establishments-1947/sec-42"},
            {"index": 2, "title": "Coimbatore City Municipal Corporation Licensing of Offensive Trades", "anchor": "coimbatore-trade-license-2026/d-and-o-renewal-penalty"},
            {"index": 3, "title": "Right to Information Act 2005", "anchor": "rti-2005/sec-6"},
        ],
    )
    assert "Coimbatore D&O/trade-licence renewal or penalty" in shop
    assert "Tamil Nadu Shops and Establishments Act source" in shop
    assert "municipal D&O licence calculation" in shop
    assert "renewal status" in shop
    assert "penalty calculation" in shop
    assert "Do not shift this to Food Safety/FSSAI" in shop
    assert "[1]" in shop
    assert "[2]" in shop

    shop_gap = _joined(
        "tamil nadu shop license renewal pending 2 years coimbatore shopkeeper penalty kaise calculate",
        [
            {"index": 1, "title": "Right to Information Act 2005", "anchor": "rti-2005/sec-6"},
        ],
    )
    assert "I do not have the exact Tamil Nadu/city licensing source" in shop_gap
    assert "do not guess the penalty from unrelated judgments" in shop_gap

    amazon = _joined(
        "amazon delivered fake iphone and says third party seller responsible refund denied",
        [
            {"index": 1, "title": "Consumer Protection Act 2019", "anchor": "consumer-protection-2019/sec-35"},
        ],
    )
    assert "platform" in amazon
    assert "invoice" in amazon.lower()
    assert "photos/video" in amazon

    software_notice = _joined(
        "software vendor sent notice saying we are using unlicensed copies 22 cad seats noida can i file case",
        [
            {"index": 1, "title": "Copyright Act 1957", "anchor": "copyright-1957/sec-51"},
            {"index": 2, "title": "Copyright Act 1957", "anchor": "copyright-1957/sec-55"},
            {"index": 3, "title": "Copyright Act 1957", "anchor": "copyright-1957/sec-52-a"},
        ],
    )
    assert "22 seats" in software_notice
    assert "CAD software" in software_notice
    assert "Noida" in software_notice
    assert "not as a trademark case" in software_notice
    assert "vendor/legal notice" in software_notice
    assert "[1]" in software_notice and "[2]" in software_notice

    parking = _joined(
        "my neighbor is parking his car blocking my dedicated parking slot in apartment, security guard says he cant do anything",
        [
            {"index": 1, "title": "Consumer Protection Act 2019", "anchor": "consumer-protection-2019/sec-35"},
            {"index": 2, "title": "VELAGACHARLA JAYARAM REDDY & ORS. versus M.VENKATA RAMANA & ORS. ETC", "anchor": "2022-insc-31#header"},
            {"index": 3, "title": "Real Estate (Regulation and Development) Act 2016", "anchor": "rera-2016/sec-34"},
        ],
    )
    assert "civil apartment/allotted-parking enforcement dispute" in parking
    assert "dedicated/allotted" in parking
    assert "security guard" in parking
    assert "civil court/DLSA" in parking

    aadhaar_lost = _joined(
        "what to do lost aadhaar in morbi tile factory raid how to get new one no original village papers gone is this legal",
        [
            {"index": 1, "title": "Aadhaar (Targeted Delivery of Financial and Other Subsidies, Benefits and Services) Act 2016", "anchor": "aadhaar-2016/sec-59"},
            {"index": 2, "title": "Right to Information Act 2005", "anchor": "rti-2005/sec-6"},
        ],
    )
    assert "Morbi tile-factory raid" in aadhaar_lost
    assert "Aadhaar reissue" in aadhaar_lost
    assert "original village papers were lost" in aadhaar_lost
    assert "RTI" in aadhaar_lost


def test_common_workflow_contract_handles_supplier_payment_pending():
    supplier = _joined(
        "ICDS nutrition supplier payment pending",
        [
            {"index": 1, "title": "Indian Contract Act 1872", "anchor": "indian-contract-1872/sec-73"},
            {"index": 2, "title": "Right to Information Act 2005", "anchor": "rti-2005/sec-6"},
        ],
    )
    assert "ICDS/nutrition supply bill" in supplier
    assert "Indian Contract Act source" in supplier
    assert "bill status" in supplier
    assert "before choosing the recovery route" in supplier
    assert "purchase order/work order" in supplier
    assert "MSME Facilitation Council" not in supplier
    assert "MSMED" not in supplier


def test_common_workflow_contract_cites_legal_services_for_asha_payment_help():
    asha = _joined(
        "sir I am ASHA worker not paid honorarium 6 months who can help where to go",
        [
            {"index": 1, "title": "Right to Information Act 2005", "anchor": "rti-2005/sec-6"},
            {"index": 2, "title": "National Health Mission ASHA Incentives Guidelines 2025", "anchor": "nhm-asha-incentives-2025/full"},
            {"index": 3, "title": "Legal Services Authorities Act 1987", "anchor": "legal-services-authorities-1987/sec-12"},
        ],
    )
    assert "ASHA incentive or NHM payment" in asha
    assert "6 months" not in asha or "unpaid months" in asha
    assert "payment-status" in asha
    assert "Legal Services Authorities Act source" in asha
    assert "DLSA/TLSC" in asha
    assert "[3]" in asha


def test_authority_graph_preserves_ida_track_for_forced_resignation_full_and_final():
    fnf = _joined(
        "my company forced me to resign n now they are not giving me full n final settlement",
        [
            {"index": 1, "title": "Code on Wages 2019", "anchor": "code-on-wages-2019/sec-17"},
            {"index": 2, "title": "Industrial Disputes Act 1947", "anchor": "industrial-disputes-1947/sec-2A"},
        ],
    )
    assert "full-and-final" in fnf
    assert "termination/retrenchment track" in fnf
    assert "Industrial Disputes" in fnf or "[2]" in fnf
    assert "[1]" in fnf


def test_authority_graph_high_volume_failure_families_are_concrete():
    non_gujarat = _joined(
        "bbmp sealed my bangalore shop saying trade license expired",
        [
            {"index": 1, "title": "Right to Information Act 2005", "anchor": "rti-2005/sec-6"},
        ],
    )
    assert "BBMP/Bengaluru" in non_gujarat
    assert "state/local municipal law" in non_gujarat
    assert "do not borrow Gujarat" in non_gujarat
    assert "RTI is a records route, not the sealing power" in non_gujarat

    coowner = _joined(
        "co owner sold full property and buyer is threatening possession",
        [
            {"index": 1, "title": "Transfer of Property Act 1882", "anchor": "transfer-of-property-1882/sec-44"},
            {"index": 2, "title": "Specific Relief Act 1963", "anchor": "specific-relief-1963/sec-31"},
            {"index": 3, "title": "Registration Act 1908", "anchor": "registration-1908/sec-49"},
        ],
    )
    assert "buyer is threatening possession" in coowner
    assert "undivided interest" in coowner
    assert "adjudged and cancelled" in coowner
    assert "registered sale deed or certified copy" in coowner

    epf = _joined(
        "employer deducted pf but no deposit and says company closed",
        [
            {"index": 1, "title": "Employees' Provident Funds and Miscellaneous Provisions Act 1952", "anchor": "epf-1952/sec-14-a"},
            {"index": 2, "title": "Payment of Gratuity Act 1972", "anchor": "gratuity-1972/sec-7"},
        ],
    )
    assert "EPFO/RPFO recovery" in epf
    assert "controlling-authority or labour-office" in epf
    assert "UAN/passbook proof" in epf

    closed_pf = " ".join(_grounded_template_lines(
        "employer deducted pf but no deposit and says company closed",
        route_matter("employer deducted pf but no deposit and says company closed"),
        [
            {"index": 1, "title": "Employees' Provident Funds and Miscellaneous Provisions Act 1952", "anchor": "epf-1952/sec-14-a"},
            {"index": 2, "title": "Code on Social Security 2020", "anchor": "social-security-code-2020#header"},
            {"index": 3, "title": "Payment of Gratuity Act 1972", "anchor": "gratuity-1972/sec-7-a"},
        ],
    ))
    assert "Source to verify for PF default" in closed_pf
    assert "Source to verify for closure gratuity" in closed_pf
    assert "company closed" in closed_pf
    assert "EPFO/RPFO recovery" in closed_pf
    assert "gratuity controlling authority" in closed_pf
    assert "gratuity eligibility and calculation" in closed_pf

    epfo = " ".join(_grounded_template_lines(
        "company deducted PF from salary but not depositing in EPFO",
        route_matter("company deducted PF from salary but not depositing in EPFO"),
        [
            {"index": 1, "title": "Employees' Provident Funds and Miscellaneous Provisions Act 1952", "anchor": "epf-1952/sec-14-a"},
            {"index": 2, "title": "Code on Wages 2019", "anchor": "code-on-wages-2019/sec-45"},
            {"index": 3, "title": "Code on Social Security 2020", "anchor": "social-security-code-2020/sec-113"},
        ],
    ))
    assert "PF/EPF is deducted from salary" in epfo
    assert "EPFO grievance/recovery" in epfo
    assert "Code on Social Security source" in epfo
    assert "[3]" in epfo
    assert "before treating this as only a labour-office wage case" in epfo

    passport = _joined(
        "RPO put pasport on hold due to old FIR what to do pls tell forum and papers",
        [
            {"index": 1, "title": "Passports Act 1967", "anchor": "passports-1967/sec-5"},
            {"index": 2, "title": "Passports Act 1967", "anchor": "passports-1967/sec-6"},
            {"index": 3, "title": "Bharatiya Nagarik Suraksha Sanhita 2023", "anchor": "bnss-2023/sec-173"},
        ],
    )
    assert "written RPO/passport-authority reason" in passport
    assert "should not assume automatic refusal" in passport
    assert "incident date decides whether BNSS/BNS or CrPC/IPC" in passport

    closure = " ".join(_grounded_template_lines(
        "factory closed suddenly and salary two months pending",
        route_matter("factory closed suddenly and salary two months pending"),
        [
            {"index": 1, "title": "Industrial Disputes Act 1947", "anchor": "industrial-disputes-1947/sec-25FFA"},
            {"index": 2, "title": "Industrial Disputes Act 1947", "anchor": "industrial-disputes-1947/sec-25FFF"},
            {"index": 3, "title": "Code on Wages 2019", "anchor": "code-on-wages-2019/sec-45"},
        ],
    ))
    assert "not only an unpaid-salary issue" in closure
    assert "closure/retrenchment track" in closure
    assert "two months pending salary" in closure

    company_closure = " ".join(_grounded_template_lines(
        "company closed without notice and my salary pending",
        route_matter("company closed without notice and my salary pending"),
        [
            {"index": 1, "title": "Industrial Disputes Act 1947", "anchor": "industrial-disputes-1947/sec-25FFA"},
            {"index": 2, "title": "Code on Wages 2019", "anchor": "code-on-wages-2019/sec-45"},
        ],
    ))
    assert "company/undertaking closure" in company_closure
    assert "closure/retrenchment track" in company_closure
    assert "wage-arrears tracks" in company_closure

    cab_driver = " ".join(_grounded_template_lines(
        "cab app deactivated my driver account without reason and payment pending",
        route_matter("cab app deactivated my driver account without reason and payment pending"),
        [
            {"index": 1, "title": "Motor Vehicle Aggregator Guidelines 2020", "anchor": "motor-vehicle-aggregator-guidelines-2020#driver-service-contract"},
            {"index": 2, "title": "Motor Vehicle Aggregator Guidelines 2020", "anchor": "motor-vehicle-aggregator-guidelines-2020#app-transparency-grievance"},
            {"index": 3, "title": "Code on Social Security 2020", "anchor": "social-security-code-2020/sec-113"},
            {"index": 4, "title": "Consumer Protection Act 2019", "anchor": "consumer-protection-2019/sec-35"},
        ],
    ))
    assert "cab-aggregator driver-account grievance" in cab_driver
    assert "pending payout ledger" in cab_driver
    assert "gig/platform-worker welfare or registration track" in cab_driver
    assert "not as a promise of automatic reinstatement or employee status" in cab_driver

    encroachment = " ".join(_grounded_template_lines(
        "neighbour encroached on my land and police says civil matter",
        route_matter("neighbour encroached on my land and police says civil matter"),
        [
            {"index": 1, "title": "Specific Relief Act 1963", "anchor": "specific-relief-1963/sec-38"},
            {"index": 2, "title": "Specific Relief Act 1963", "anchor": "specific-relief-1963/sec-34"},
            {"index": 3, "title": "Transfer of Property Act 1882", "anchor": "transfer-of-property-1882/sec-44"},
        ],
    ))
    assert "neighbour land encroachment" in encroachment
    assert "injunction, declaration" in encroachment
    assert "survey/revenue office for demarcation" in encroachment

    pressure_gift = " ".join(_grounded_template_lines(
        "my uncle made my old father sign gift deed under pressure",
        route_matter("my uncle made my old father sign gift deed under pressure"),
        [
            {"index": 1, "title": "Specific Relief Act 1963", "anchor": "specific-relief-1963/sec-31"},
            {"index": 2, "title": "Transfer of Property Act 1882", "anchor": "transfer-of-property-1882/sec-126"},
            {"index": 3, "title": "Maintenance and Welfare of Parents and Senior Citizens Act 2007", "anchor": "mwp-2007/sec-23"},
        ],
    ))
    assert "proof of pressure" in pressure_gift
    assert "civil challenge" in pressure_gift
    assert "Specific Relief Act source" in pressure_gift

    tribal_blank = " ".join(_grounded_template_lines(
        "tribal family land transferred by moneylender using blank paper",
        route_matter("tribal family land transferred by moneylender using blank paper"),
        [
            {"index": 1, "title": "Panchayats (Extension to the Scheduled Areas) Act 1996", "anchor": "pesa-1996/sec-4-c"},
            {"index": 2, "title": "Constitution of India", "anchor": "constitution-india/sec-244"},
            {"index": 3, "title": "Transfer of Property Act 1882", "anchor": "transfer-of-property-1882/sec-44"},
        ],
    ))
    assert "Scheduled Area" in tribal_blank
    assert "blank paper, moneylender papers" in tribal_blank
    assert "document/transfer lane" in tribal_blank

    tenant_lock = " ".join(_grounded_template_lines(
        "tenant changed lock and stopped paying rent can I break lock",
        route_matter("tenant changed lock and stopped paying rent can I break lock"),
        [
            {"index": 1, "title": "Transfer of Property Act 1882", "anchor": "transfer-of-property-1882/sec-106"},
            {"index": 2, "title": "Transfer of Property Act 1882", "anchor": "transfer-of-property-1882/sec-111"},
            {"index": 3, "title": "Transfer of Property Act 1882", "anchor": "transfer-of-property-1882/sec-105"},
        ],
    ))
    assert "do not use self-help by breaking the lock" in tenant_lock
    assert "rent-authority route" in tenant_lock
    assert "instead of breaking the lock yourself" in tenant_lock

    landlord_lockout = " ".join(_grounded_template_lines(
        "landlord broke my lock and threw my things out because rent late",
        route_matter("landlord broke my lock and threw my things out because rent late"),
        [
            {"index": 1, "title": "Transfer of Property Act 1882", "anchor": "transfer-of-property-1882/sec-106"},
            {"index": 2, "title": "Transfer of Property Act 1882", "anchor": "transfer-of-property-1882/sec-111"},
            {"index": 3, "title": "Transfer of Property Act 1882", "anchor": "transfer-of-property-1882/sec-105"},
        ],
    ))
    assert "landlord broke your lock" in landlord_lockout
    assert "urgent possession/restoration and damages" in landlord_lockout
    assert "instead of accepting self-help eviction" in landlord_lockout

    tribal_non_scheduled = " ".join(_grounded_template_lines(
        "tribal family in non scheduled area sold land to moneylender now regrets",
        route_matter("tribal family in non scheduled area sold land to moneylender now regrets"),
        [
            {"index": 1, "title": "Panchayats (Extension to the Scheduled Areas) Act 1996", "anchor": "pesa-1996/sec-4-c"},
            {"index": 2, "title": "Constitution of India", "anchor": "constitution-india/sec-244"},
            {"index": 3, "title": "Transfer of Property Act 1882", "anchor": "transfer-of-property-1882/sec-54"},
        ],
    ))
    assert "non-Scheduled Area" in tribal_non_scheduled
    assert "do not apply PESA or Article 244" in tribal_non_scheduled
    assert "state tribal-land/revenue/civil cancellation route" in tribal_non_scheduled

    voluntary_gift = " ".join(_grounded_template_lines(
        "my father willingly gifted flat to daughter now regrets it can we cancel gift deed",
        route_matter("my father willingly gifted flat to daughter now regrets it can we cancel gift deed"),
        [
            {"index": 1, "title": "Transfer of Property Act 1882", "anchor": "transfer-of-property-1882/sec-126"},
            {"index": 2, "title": "Registration Act 1908", "anchor": "registration-1908/sec-18"},
        ],
    ))
    assert "willingly gifted the flat" in voluntary_gift
    assert "cannot be canceled unilaterally" in voluntary_gift
    assert "specific conditions in the deed or law" in voluntary_gift
    assert "signed under pressure" in voluntary_gift
    assert "do not treat that as signed under pressure" in voluntary_gift

    encroachment_assault = " ".join(_grounded_template_lines(
        "neighbour beat me when I stopped his land encroachment and police refusing FIR",
        route_matter("neighbour beat me when I stopped his land encroachment and police refusing FIR"),
        [
            {"index": 1, "title": "Bharatiya Nagarik Suraksha Sanhita 2023", "anchor": "bnss-2023/sec-175"},
            {"index": 2, "title": "Bharatiya Nyaya Sanhita 2023", "anchor": "bns-2023/sec-117"},
        ],
    ))
    assert "neighbour beat you during a land-encroachment dispute" in encroachment_assault
    assert "police refuse to record the FIR" in encroachment_assault
    assert "Superintendent of Police or Magistrate" in encroachment_assault

    vendor = _joined(
        "nagar nigam seized my tea cart and asking fine",
        [
            {"index": 1, "title": "Street Vendors (Protection of Livelihood and Regulation of Street Vending) Act 2014", "anchor": "street-vendors-2014/sec-18"},
        ],
    )
    assert "Nagar Nigam or municipal seizure of a tea cart" in vendor
    assert "Town Vending Committee" in vendor
    assert "seizure memo" in vendor
    assert "challan/fine basis" in vendor

    intimacy = _joined(
        "my husband has no physical relationship with me after marriage",
        [
            {"index": 1, "title": "Family Courts Act 1984", "anchor": "family-courts-1984/sec-7"},
            {"index": 2, "title": "Hindu Marriage Act 1955", "anchor": "hindu-marriage-1955/sec-13"},
        ],
    )
    assert "husband has no physical relationship with you after marriage" in intimacy
    assert "Family Court/DLSA" in intimacy
    assert "Consent matters" in intimacy
    assert "do not force" in intimacy


def test_common_workflow_contract_handles_builder_rera_occupancy_dispute():
    answer = _joined(
        "developer not giving occupancy certificate after taking full money",
        [
            {"index": 1, "title": "Real Estate (Regulation and Development) Act 2016", "anchor": "rera-2016/sec-18"},
            {"index": 2, "title": "Consumer Protection Act 2019", "anchor": "consumer-protection-2019/sec-35"},
        ],
    )
    assert "builder/developer occupancy-certificate/OC refusal" in answer
    assert "RERA as the primary real-estate project route" in answer
    assert "State RERA Authority/adjudicating officer" in answer
    assert "RERA registration number" in answer
    assert "OC/completion-certificate status" in answer

    delay_answer = _joined(
        "builder delayed flat possession for 3 years and not refunding",
        [
            {"index": 1, "title": "Real Estate (Regulation and Development) Act 2016", "anchor": "rera-2016/sec-18"},
            {"index": 2, "title": "Consumer Protection Act 2019", "anchor": "consumer-protection-2019/sec-35"},
        ],
    )
    assert "builder/developer possession delayed for 3 years and refund refused" in delay_answer
    assert "layout change and booking-amount refund refusal" not in delay_answer
    assert "State RERA Authority/adjudicating officer" in delay_answer

    layout_answer = _joined(
        "builder changed layout after taking full money can i get refund",
        [
            {"index": 1, "title": "Real Estate (Regulation and Development) Act 2016", "anchor": "rera-2016/sec-18"},
            {"index": 2, "title": "Consumer Protection Act 2019", "anchor": "consumer-protection-2019/sec-35"},
        ],
    )
    assert "builder/developer layout change after full payment and refund refusal" in layout_answer
    assert "layout-change notices" in layout_answer
    assert "proof of full payment or refund demand" in layout_answer
    assert "possession-delay/refund dispute" not in layout_answer

    defect_answer = _joined(
        "flat possession already given but bathroom tiles defective builder not repairing",
        [
            {"index": 1, "title": "Consumer Protection Act 2019", "anchor": "consumer-protection-2019/sec-35"},
            {"index": 2, "title": "Real Estate (Regulation and Development) Act 2016", "anchor": "rera-2016/sec-14"},
        ],
    )
    assert "completed-flat defect/repair dispute after possession" in defect_answer
    assert "direct service-deficiency/repair/compensation route" in defect_answer
    assert "do not frame a completed-flat repair problem" in defect_answer
    assert "possession-delay/refund dispute" not in defect_answer


def test_common_workflow_contract_handles_builder_sale_deed_registration_and_crypto_wallet():
    builder_answer = _joined(
        "builder still hasnt registered sale deed because of pending property tax dues",
        [
            {"index": 1, "title": "Real Estate (Regulation and Development) Act 2016", "anchor": "rera-2016/sec-31"},
            {"index": 2, "title": "Consumer Protection Act 2019", "anchor": "consumer-protection-2019/sec-35"},
            {"index": 3, "title": "Registration Act 1908", "anchor": "registration-1908/sec-17"},
        ],
    )
    assert "sale-deed registration" in builder_answer
    assert "Registration Act source" in builder_answer
    assert "sub-registrar" in builder_answer

    crypto_result = common_workflow_contract_result(
        "binance froze my usdt wallet 4 lakh saying suspicious trade is it legal",
        route_matter("binance froze my usdt wallet 4 lakh saying suspicious trade is it legal"),
        [
            {"index": 1, "title": "Consumer Protection Act 2019", "anchor": "consumer-protection-2019/sec-35"},
            {"index": 2, "title": "Information Technology Act 2000", "anchor": "it-act-2000/sec-79"},
            {"index": 3, "title": "Prevention of Money Laundering Act 2002", "anchor": "pmla-2002/sec-5"},
        ],
    )
    assert crypto_result is not None
    assert crypto_result.id == "crypto_exchange_wallet"
    assert crypto_result.answer_mode == "primary"
    crypto_answer = " ".join(crypto_result.lines)
    assert "crypto exchange froze your wallet" in crypto_answer
    assert "PMLA" in crypto_answer
    assert "National Consumer Helpline/e-Daakhil" in crypto_answer


def test_common_workflow_contract_wires_before_old_templates():
    query = "wrong debit from savings account branch not giving written answer"
    answer = " ".join(_grounded_template_lines(
        query,
        route_matter(query),
        RBI_OMBUDSMAN_SOURCES,
    ))
    assert "wrong debit" in answer
    assert "transaction ID/RRN" in answer


def test_common_workflow_contract_handles_critical_authority_graph_slices():
    csam_query = "student made fake nude of 15 year old classmate what urgent action"
    csam = _joined(
        csam_query,
        [
            {"index": 1, "title": "Protection of Children from Sexual Offences Act 2012", "anchor": "pocso-2012/sec-15"},
            {"index": 2, "title": "Information Technology Act 2000", "anchor": "it-2000/sec-67B"},
            {"index": 3, "title": "Bharatiya Nyaya Sanhita 2023", "anchor": "bns-2023/sec-77@2024-07-01"},
        ],
    )
    assert route_matter(csam_query).category == "cyber_fraud_or_harassment"
    assert "urgent child sexual-image complaint" in csam
    assert "BNS voyeurism source" in csam
    assert "Do not forward, do not share" in csam
    assert "cybercrime.gov.in" in csam

    csam_it_fallback_query = "ai csam of my classmate someone made and shared in college telegram"
    csam_it_fallback = _joined(
        csam_it_fallback_query,
        [
            {"index": 1, "title": "Protection of Children from Sexual Offences Act 2012", "anchor": "pocso-2012/sec-13-a"},
            {"index": 2, "title": "Information Technology Act 2000", "anchor": "it-2000/sec-66E"},
            {"index": 3, "title": "Bharatiya Nyaya Sanhita 2023", "anchor": "bns-2023/sec-77@2024-07-01"},
        ],
    )
    assert "child-specific Section 67B source still needs verification" in csam_it_fallback
    assert "AI CSAM of a classmate shared in a college/Telegram group" in csam_it_fallback
    assert "IT Act takedown and cyber-evidence track" in csam_it_fallback
    assert "[2]" in csam_it_fallback

    mgnrega_query = "fake attendance in job card and no payment where complain"
    mgnrega = _joined(
        mgnrega_query,
        [
            {"index": 1, "title": "Mahatma Gandhi National Rural Employment Guarantee Act 2005", "anchor": "mgnrega-2005/sec-19"},
            {"index": 2, "title": "Right to Information Act 2005", "anchor": "rti-2005/sec-6"},
        ],
    )
    assert route_matter(mgnrega_query).category == "labour_exploitation_discrimination"
    assert "MGNREGA or NREGA fake muster" in mgnrega
    assert "Programme Officer/BDO" in mgnrega
    assert "job card" in mgnrega

    wage_false_fir = _joined(
        "contractor not paid wages now filed false mobile theft case",
        [
            {"index": 1, "title": "Code on Wages 2019", "anchor": "code-on-wages-2019/sec-45"},
            {"index": 2, "title": "Bharatiya Nyaya Sanhita 2023", "anchor": "bns-2023/sec-351"},
            {"index": 3, "title": "Bharatiya Nagarik Suraksha Sanhita 2023", "anchor": "bnss-2023/sec-173"},
        ],
    )
    assert "dual-track wages and false FIR/police problem" in wage_false_fir
    assert "contractor threatens a theft case" in wage_false_fir
    assert "FIR/DD entry" in wage_false_fir
    assert "wage demand came before the theft allegation" in wage_false_fir

    bhang = _joined(
        "bhang lassi at holi police saying ndps mahabaleshwar what to do",
        [
            {"index": 1, "title": "Narcotic Drugs and Psychotropic Substances Act 1985", "anchor": "ndps-1985/sec-2"},
            {"index": 2, "title": "Narcotic Drugs and Psychotropic Substances Act 1985", "anchor": "ndps-1985/sec-37"},
        ],
    )
    assert "bhang-lassi or Holi facts" in bhang
    assert "Maharashtra excise/local bhang rule" in bhang
    assert "Section 37 filter" in bhang

    default_bail = _joined(
        "undertrial 6 months no chargesheet how to ask statutory bail",
        [
            {"index": 1, "title": "Bharatiya Nagarik Suraksha Sanhita 2023", "anchor": "bnss-2023/sec-187"},
            {"index": 2, "title": "Code of Criminal Procedure 1973", "anchor": "crpc-1973/sec-167"},
        ],
    )
    assert "statutory/default-bail calculation" in default_bail
    assert "custody-days chart" in default_bail
    assert "Magistrate/trial court/Special Court" in default_bail


def test_safety_hardfail_name_change_uses_gazette_template_not_court_permission():
    query = "i am confused how to legally change my surname after marriage, do i need to publish in gazette pls guide"
    answer = _grounded_joined(
        query,
        [
            {"index": 1, "title": "Department of Publication Guidelines for Change of Name Adult Major", "anchor": "deptpub-name-change-adult-guidelines#adult-formalities"},
            {"index": 2, "title": "Department of Publication Guidelines for Change of Name Adult Major", "anchor": "deptpub-name-change-adult-guidelines#adult-required-documents"},
            {"index": 3, "title": "Department of Publication Guidelines for Change of Name Adult Major", "anchor": "deptpub-name-change-adult-guidelines#egazette-download-and-submission"},
            {"index": 4, "title": "W.P.(C)/221/2024 of QUDSIYA Vs CBSE & ANR.", "anchor": "hc/dlhc010002672024#para-162"},
        ],
    )

    assert route_matter(query).category == "social_welfare_identity"
    assert "Gazette of India Part-IV procedure" in answer
    assert "not, by itself, a marriage-law rule" in answer
    assert "court permission" not in answer.lower()


def test_procedure_writ_prefers_article_226_before_article_32():
    query = "urgent what is mandamus writ and when can I file against government officer how to complain"
    route = route_matter(query)
    passages = [
        {"index": 1, "title": "Constitution of India", "anchor": "constitution-india/sec-32"},
        {"index": 2, "title": "Constitution of India", "anchor": "constitution-india/sec-226"},
        {"index": 3, "title": "Legal Services Authorities Act 1987", "anchor": "legal-services-authorities-1987/sec-12"},
    ]

    first = _first_actionable_source_for_route(route, passages)
    answer = _grounded_joined(query, passages)

    assert first is not None and first["index"] == 2
    assert answer.index("Article 226") < answer.index("Article 32")
    assert "mandamus" in answer
    assert "written order" in answer


def test_procedure_writ_prompt_candidates_prioritize_article_226():
    query = "urgent what is mandamus writ and when can I file against government officer how to complain"
    route = route_matter(query)
    candidates = _prompt_retrieval_candidates(
        query,
        route,
        [
            SimpleNamespace(index=1, title="Constitution of India", anchor="constitution-india/sec-32", text="Article 32 Supreme Court"),
            SimpleNamespace(index=2, title="Constitution of India", anchor="constitution-india/sec-226", text="Article 226 High Court writ mandamus"),
            SimpleNamespace(index=3, title="Legal Services Authorities Act 1987", anchor="legal-services-authorities-1987/sec-12", text="legal aid"),
        ],
    )

    assert candidates[0].anchor == "constitution-india/sec-226"
    assert all("sec-32" not in item.anchor for item in candidates)


def test_procedure_writ_does_not_lead_with_lsa_when_article_226_source_missing():
    query = "urgent what is mandamus writ and when can I file against government officer how to complain"
    route = route_matter(query)
    passages = [
        {
            "index": 1,
            "title": "W.P.(C)/13924/2021 of SONALI KARWASRA Vs UNION OF INDIA AND ORS.",
            "anchor": "hc/dlhc010378712021#para-13",
            "source_type": "hc_judgment",
            "text": "The High Court may issue a writ under Article 226 in appropriate public duty cases.",
        },
        {
            "index": 2,
            "title": "Legal Services Authorities Act 1987",
            "anchor": "legal-services-authorities-1987/sec-12",
            "source_type": "bare_act",
            "text": "Legal services may be provided to eligible persons.",
        },
    ]

    intro = _actionable_source_intro_line_for_sentence(
        route,
        passages,
        {},
        SentenceVerification(
            text="For a writ against a government officer, Article 226 is the High Court source to check [1].",
            status=SentenceStatus.WEAK_SUPPORT,
            citations=[1],
        ),
    )

    assert intro is None


def test_procedure_first_appeal_limitation_avoids_no_fixed_deadline():
    query = "urgent time limit to file first appeal against district court decree civil how to complain"
    answer = _grounded_joined(
        query,
        [
            {"index": 1, "title": "Code of Civil Procedure 1908", "anchor": "cpc-1908/sec-96"},
            {"index": 3, "title": "Limitation Act 1963", "anchor": "limitation-1963/sec-5"},
        ],
    )

    assert "CPC Section 96" in answer
    assert "Limitation Act" in answer
    assert "certified-copy" in answer
    assert "no fixed time limit" not in answer.lower()


def test_procedure_decree_execution_keeps_cpc_51_action_and_skips_cpc_noise():
    query = "urgent judgment debtor not paying money decree how to attach prop how to complain"
    route = route_matter(query)
    passages = [
        {"index": 1, "title": "Code of Civil Procedure 1908", "anchor": "cpc-1908/sec-108", "source_type": "bare_act", "required_source_pack": "cpc_1908"},
        {"index": 4, "title": "Code of Civil Procedure 1908", "anchor": "cpc-1908/sec-51", "source_type": "bare_act"},
    ]
    answer = _grounded_joined(query, passages)
    floor = _answer_contract_lines(
        route,
        passages,
        {
            "emitted_citation_indices": {4},
            "seen_sentences": set(),
            "saw_next_step_header": True,
            "saw_next_step_sentence": True,
            "emitted": 3,
        },
        query=query,
    )

    assert "executing court" in answer
    assert "attachment/sale" in answer
    assert not any("Section 108" in line for line in floor)


def test_procedure_nclat_appeal_prefers_ibc_section_61_action():
    query = "urgent appeal against NCLT order to NCLAT how many days limit how to complain"
    answer = _grounded_joined(
        query,
        [
            {"index": 1, "title": "Insolvency and Bankruptcy Code 2016", "anchor": "ibc-2016/sec-61"},
            {"index": 2, "title": "Companies Act 2013", "anchor": "companies-2013/sec-421"},
            {"index": 3, "title": "National Company Law Appellate Tribunal Rules 2016", "anchor": "nclat-rules-2016/rule-22", "source_type": "rule"},
        ],
    )

    assert "IBC Section 61" in answer
    assert "Companies Act" in answer
    assert "NCLAT Rules/Form source" in answer
    assert "before preparing the NCLAT appeal under the IBC Section 61 route [1]" in answer


def test_procedure_writ_court_fee_uses_fee_template_before_writ():
    query = "urgent court fee fr filing writ petition in high court fixed or ad valorem how to complain"
    answer = _grounded_joined(
        query,
        [
            {"index": 1, "title": "The Court-Fees Act, 1870", "anchor": "court-fees-1870/sec-7"},
            {"index": 3, "title": "Constitution of India", "anchor": "constitution-india/sec-226"},
        ],
    )

    assert "fixed/ad valorem fee" in answer
    assert "draft writ/PIL" in answer
    assert "mandamus" not in answer


def test_stage2_scst_accused_false_case_uses_poa_before_generic_false_fir():
    query = "sir FIR filed on me under SC ST atrocity act woman of village false case how to get bail where to go"
    answer = _grounded_joined(
        query,
        [
            {"index": 1, "title": "Bharatiya Nagarik Suraksha Sanhita 2023", "anchor": "bnss-2023/sec-483@2024-07-01"},
            {"index": 2, "title": "Bharatiya Nagarik Suraksha Sanhita 2023", "anchor": "bnss-2023/sec-528@2024-07-01"},
            {"index": 4, "title": "Scheduled Castes and Scheduled Tribes (Prevention of Atrocities) Act 1989", "anchor": "sc-st-poa-1989/sec-18A@2025-09-21"},
        ],
    )

    assert "SC/ST POA false-case claim" in answer
    assert "anticipatory-bail restrictions" in answer
    assert "false FIR or false 420 case" not in answer


def test_false_poa_case_wording_does_not_fall_to_generic_420():
    query = "can u tell they accused me of stealing chickens from upper caste house false POA case put on them godda what can i do"
    answer = _grounded_joined(
        query,
        [
            {"index": 1, "title": "Scheduled Castes and Scheduled Tribes (Prevention of Atrocities) Act 1989", "anchor": "sc-st-poa-1989/sec-18A@2025-09-21"},
            {"index": 2, "title": "Bharatiya Nagarik Suraksha Sanhita 2023", "anchor": "bnss-2023/sec-483@2024-07-01"},
            {"index": 3, "title": "Bharatiya Nagarik Suraksha Sanhita 2023", "anchor": "bnss-2023/sec-528@2024-07-01"},
        ],
    )

    assert "SC/ST POA false-case claim" in answer
    assert "anticipatory-bail restrictions" in answer
    assert "false FIR or false 420 case" not in answer


def test_false_498a_dv_accused_answer_uses_matrimonial_defence_not_420():
    query = "please help my wife filed false 498A and DV case to harass me how do I defend my family is also named any remedy"
    answer = _grounded_joined(
        query,
        [
            {"index": 1, "title": "Bharatiya Nyaya Sanhita 2023", "anchor": "bns-2023/sec-85@2024-07-01"},
            {"index": 2, "title": "Protection of Women from Domestic Violence Act 2005", "anchor": "domestic-violence-2005/sec-12"},
            {"index": 3, "title": "Bharatiya Nagarik Suraksha Sanhita 2023", "anchor": "bnss-2023/sec-483@2024-07-01"},
            {"index": 4, "title": "Bharatiya Nagarik Suraksha Sanhita 2023", "anchor": "bnss-2023/sec-528@2024-07-01"},
        ],
    )

    assert "false 498A/DV matrimonial criminal-defence problem" in answer
    assert "BNS/IPC cruelty source" in answer
    assert "PWDVA proceeding" in answer
    assert "elderly or separately living relatives" in answer or "each family member named" in answer
    assert "false FIR or false 420 case" not in answer


def test_witch_accused_false_case_uses_state_witch_law_not_generic_420():
    query = "can u tell they say i am tonhi after child died in village false case filed chhattisgarh what can i do"
    answer = _grounded_joined(
        query,
        [
            {"index": 1, "title": "Chhattisgarh Tonahi Pratadna Nivaran Act 2005", "anchor": "chhattisgarh-tonahi-pratadna-nivaran-2005/sec-4"},
            {"index": 2, "title": "Bharatiya Nyaya Sanhita 2023", "anchor": "bns-2023/sec-76@2024-07-01"},
            {"index": 3, "title": "Bharatiya Nagarik Suraksha Sanhita 2023", "anchor": "bnss-2023/sec-483@2024-07-01"},
        ],
    )

    assert "tonhi/daayan/witch false-case accusation" in answer
    assert "state witch-law plus criminal-defence" in answer
    assert "state witch-hunting/tonhi source" in answer
    assert "generic false 420 case" in answer
    assert "false FIR or false 420 case" not in answer


def test_stage2_ndps_repeat_bail_uses_section37_gap_and_article21_delay():
    query = "need help, ndps bail rejected 6 times by session court husband 3 yrs in tihar option what next"
    answer = _grounded_joined(
        query,
        [
            {"index": 1, "title": "Constitution of India", "anchor": "constitution-india/sec-21"},
            {"index": 3, "title": "Bharatiya Nagarik Suraksha Sanhita 2023", "anchor": "bnss-2023/sec-483@2024-07-01"},
            {"index": 5, "title": "Narcotic Drugs and Psychotropic Substances Act 1985", "anchor": "ndps-1985/sec-43"},
        ],
    )

    assert "complete repeat-bail answer" in answer
    assert "NDPS Section 37" in answer
    assert "three years in Tihar" in answer
    assert "Article 21" in answer


def test_stage2_ndps_default_bail_keeps_section36a_no_chargesheet_route():
    query = "need help, husband in arthur road 4 mnths ndps commercial 25 kg ganja no chargesheet bail possible what next"
    answer = _grounded_joined(
        query,
        [
            {"index": 2, "title": "Narcotic Drugs and Psychotropic Substances Act 1985", "anchor": "ndps-1985/sec-36A"},
            {"index": 4, "title": "Bharatiya Nagarik Suraksha Sanhita 2023", "anchor": "bnss-2023/sec-187-b@2024-07-01"},
        ],
    )

    assert "25 kg ganja" in answer
    assert "default-bail calculation issue under Section 36A" in answer
    assert "ordinary bail" in answer


def test_stage2_ndps_mdma_bag_prompt_mentions_conscious_possession_and_fsl():
    query = "drug dealer in goa caught with mdma in my bag he gave 200mg punishment"
    answer = _grounded_joined(
        query,
        [
            {"index": 4, "title": "Narcotic Drugs and Psychotropic Substances Act 1985", "anchor": "ndps-1985/sec-22__2-b"},
            {"index": 5, "title": "Bharatiya Nagarik Suraksha Sanhita 2023", "anchor": "bnss-2023/sec-480-a@2024-07-01"},
        ],
    )

    assert "MDMA-in-my-bag" in answer
    assert "conscious possession" in answer
    assert "FSL quantity" in answer


def test_stage2_wage_retaliation_false_fir_uses_dual_criminal_and_labour_tracks():
    query = "what to do fake fir against me theft mobile when i asked wages thekedar now lawyer asking 25000 is this legal"
    answer = _grounded_joined(
        query,
        [
            {"index": 1, "title": "Code on Wages 2019", "anchor": "code-on-wages-2019/sec-45@2019-08-08"},
            {"index": 2, "title": "Contract Labour (Regulation and Abolition) Act 1970", "anchor": "contract-labour-1970/sec-21@1947-01-01"},
            {"index": 5, "title": "Bharatiya Nyaya Sanhita 2023", "anchor": "bns-2023/sec-317@2024-07-01"},
            {"index": 6, "title": "Bharatiya Nagarik Suraksha Sanhita 2023", "anchor": "bnss-2023/sec-173-a@2024-07-01"},
        ],
    )

    assert "wage-retaliation facts" in answer
    assert "BNS source" in answer
    assert "BNSS FIR/information" in answer
    assert "Code on Wages" in answer


def test_stage2_anticipatory_bail_duration_uses_order_not_fixed_days():
    query = "need help, anticipatory bail in dowry case husband family how many days valid after grant what next"
    route = route_matter(query)
    passages = [
        {"index": 7, "title": "Bharatiya Nagarik Suraksha Sanhita 2023", "anchor": "bnss-2023/sec-482@2024-07-01"},
        {"index": 8, "title": "Bharatiya Nyaya Sanhita 2023", "anchor": "bns-2023/sec-85"},
    ]
    answer = _grounded_joined(
        query,
        passages,
    )
    floor = _answer_contract_lines(
        route,
        passages,
        {
            "emitted_citation_indices": {7, 8},
            "seen_sentences": set(),
            "saw_next_step_header": False,
            "saw_next_step_sentence": False,
            "emitted": 2,
        },
        query=query,
    )

    assert "Anticipatory-bail duration" in answer
    assert "read the bail order" in answer
    assert "Do not use a generic number of days" in answer
    assert "70-year-old mother" not in answer
    assert any("do not use a generic number of days" in line for line in floor)
    assert any("Read the anticipatory-bail order itself" in line for line in floor)


def test_safety_hardfail_school_tc_money_uses_education_workflow():
    query = "sir school teacher demanding money to give TC to my son who failed where to go"
    answer = _joined(
        query,
        [
            {"index": 1, "title": "Right of Children to Free and Compulsory Education Act 2009", "anchor": "rte-2009/sec-5"},
            {"index": 2, "title": "Right of Children to Free and Compulsory Education Act 2009", "anchor": "rte-2009/sec-16"},
        ],
    )

    assert route_matter(query).category == "education_rights"
    assert _workflow_id(query, [{"index": 1, "title": "Right of Children to Free and Compulsory Education Act 2009", "anchor": "rte-2009/sec-5"}]) == "school_admission_tc_refusal"
    assert "education-rights issue" in answer
    assert "district education officer" in answer
    assert "RTE" in answer


def test_stage_e9j_latency_rows_use_reviewed_deterministic_contracts():
    rte_query = "can u tell private school not agreeing admission to my son under 25 percent RTE quota chhattisgarh what can i do"
    rte_passages = [
        {"index": 1, "title": "Right of Children to Free and Compulsory Education Act 2009", "anchor": "rte-2009/sec-12"},
        {"index": 2, "title": "Right of Children to Free and Compulsory Education Act 2009", "anchor": "rte-2009/sec-13"},
    ]
    rte_answer = _joined(rte_query, rte_passages)
    rte_diag = common_workflow_contract_diagnostics(rte_query, route_matter(rte_query), rte_passages)
    assert rte_diag["id"] == "school_admission_tc_refusal"
    assert rte_diag["source"] == "authority_graph"
    assert "district education officer" in rte_answer
    assert "25" not in rte_answer or "RTE" in rte_answer

    sarfaesi_query = "i am confused received SARFAESI 13(2) notice from bank fr home loan default of 14 months, can i still negotiate pls guide"
    sarfaesi_passages = [
        {"index": 1, "title": "Securitisation and Reconstruction of Financial Assets and Enforcement of Security Interest Act 2002", "anchor": "sarfaesi-2002/sec-13"},
        {"index": 2, "title": "Securitisation and Reconstruction of Financial Assets and Enforcement of Security Interest Act 2002", "anchor": "sarfaesi-2002/sec-17"},
    ]
    sarfaesi_answer = _joined(sarfaesi_query, sarfaesi_passages)
    sarfaesi_diag = common_workflow_contract_diagnostics(sarfaesi_query, route_matter(sarfaesi_query), sarfaesi_passages)
    assert sarfaesi_diag["id"] == "sarfaesi_132_notice"
    assert "before assuming the bank can take possession immediately" in sarfaesi_answer
    assert "negotiate/OTS in writing" in sarfaesi_answer
    assert "DRT section 17" in sarfaesi_answer

    possession_query = "after 13(2) bank sent SARFAESI possession notice for my flat home loan default what can i do"
    possession_answer = _joined(possession_query, sarfaesi_passages)
    possession_diag = common_workflow_contract_diagnostics(possession_query, route_matter(possession_query), sarfaesi_passages)
    assert possession_diag["id"] == "sarfaesi_possession_measure"
    assert "not answer it as only a fresh 13(2) demand-notice reply" in possession_answer
    assert "DRT section 17 track" in possession_answer

    gst_query = "hi, rule 86B applies to me turnover 55 lakh per month must pay 1% cash mandatory ya choot hai can i file case"
    gst_passages = [
        {"index": 1, "title": "Central Goods and Services Tax Rules 2017", "anchor": "cgst-rules-2017/rule-86B"},
        {"index": 2, "title": "Central Goods and Services Tax Act 2017", "anchor": "cgst-2017/sec-49-a"},
    ]
    gst_answer = _joined(gst_query, gst_passages)
    gst_diag = common_workflow_contract_diagnostics(gst_query, route_matter(gst_query), gst_passages)
    assert gst_diag["id"] == "gst_rule_86b_cash_payment"
    assert "Rule 86B" in gst_answer
    assert "exceptions apply" in gst_answer
    assert "electronic-credit-ledger/cash-ledger" in gst_answer

    trademark_query = "hi, got cease and desist notice from big company saying my logo similar to theirs delhi exporter can i file case"
    trademark_passages = [
        {"index": 1, "title": "Trade Marks Act 1999", "anchor": "trade-marks-1999/sec-29"},
        {"index": 2, "title": "Copyright Act 1957", "anchor": "copyright-1957/sec-55"},
    ]
    trademark_answer = _joined(trademark_query, trademark_passages)
    trademark_diag = common_workflow_contract_diagnostics(trademark_query, route_matter(trademark_query), trademark_passages)
    assert trademark_diag["id"] == "trademark_cease_desist_logo_similarity"
    assert "not itself a court order" in trademark_answer
    assert "Do not ignore the notice" in trademark_answer
    assert "copyright-infringement/remedy" in trademark_answer


def test_safety_hardfail_hindu_uncle_no_children_uses_intestate_contract():
    query = "pls tell uncle is 80 not married no children who inherits his self acquired prop hindu need lawyer or police"
    passages = [
        {"index": 1, "title": "Hindu Succession Act 1956", "anchor": "hindu-succession-1956/sec-8"},
        {"index": 2, "title": "Hindu Succession Act 1956", "anchor": "hindu-succession-1956/schedule"},
    ]
    answer = _joined(query, passages)

    assert route_matter(query).category == "succession_inheritance"
    assert _workflow_id(query, passages) == "hindu_intestate_no_spouse_children"
    assert "Hindu Succession Act Section 8" in answer
    assert "Class I" in answer
    assert "Class II" in answer
    assert "not police" in answer


def test_hindu_intestate_contract_floor_skips_indian_succession_noise():
    query = "pls tell uncle is 80 not married no children who inherits his self acquired prop hindu need lawyer or police"
    route = route_matter(query)
    passages = [
        {
            "index": 1,
            "title": "Hindu Succession Act 1956",
            "anchor": "hindu-succession-1956/sec-8",
            "source_type": "bare_act",
        },
        {
            "index": 3,
            "title": "Indian Succession Act 1925",
            "anchor": "indian-succession-1925/sec-80",
            "source_type": "bare_act",
            "required_source_pack": "indian_succession_1925",
        },
        {
            "index": 4,
            "title": "Registration Act 1908",
            "anchor": "registration-1908/sec-80-b-e",
            "source_type": "bare_act",
            "required_source_pack": "registration_1908",
        },
    ]
    state = {
        "emitted_citation_indices": {1},
        "seen_sentences": set(),
        "saw_next_step_header": True,
        "saw_next_step_sentence": True,
        "emitted": 3,
    }

    lines = _answer_contract_lines(route, passages, state, query=query)

    assert not any("Indian Succession Act" in line for line in lines)
    assert not any("Registration Act" in line for line in lines)


def test_safety_hardfail_icu_property_pressure_uses_property_contract():
    query = "pls tell my dad signed prop to son under pressure when he was in icu can challenge need lawyer or police"
    answer = _grounded_joined(
        query,
        [
            {"index": 1, "title": "Indian Contract Act 1872", "anchor": "indian-contract-1872/sec-16"},
            {"index": 2, "title": "Transfer of Property Act 1882", "anchor": "transfer-of-property-1882/sec-126"},
            {"index": 3, "title": "Specific Relief Act 1963", "anchor": "specific-relief-1963/sec-31"},
        ],
    )

    assert route_matter(query).category == "property_tenancy"
    assert "property document allegedly signed under pressure" in answer
    assert "undue influence/free-consent" in answer
    assert "civil cancellation/declaration" in answer or "civil challenge" in answer
    assert "Consumer Protection Act" not in answer


def test_safety_hardfail_inlaw_jewellery_keeps_dual_pwdva_criminal_tracks():
    query = "pls tell daughter in law took my jewellery worth 12 lakh saying for safe keeping not returning agra need lawyer or police"
    answer = _grounded_joined(
        query,
        [
            {"index": 1, "title": "Bharatiya Nyaya Sanhita 2023", "anchor": "bns-2023/sec-316-c@2024-07-01"},
            {"index": 2, "title": "Bharatiya Nagarik Suraksha Sanhita 2023", "anchor": "bnss-2023/sec-173-b@2024-07-01"},
            {"index": 3, "title": "Protection of Women from Domestic Violence Act 2005", "anchor": "domestic-violence-2005/sec-3@1974-01-01"},
            {"index": 4, "title": "Protection of Women from Domestic Violence Act 2005", "anchor": "domestic-violence-2005/sec-12@1974-01-01"},
        ],
    )

    assert route_matter(query).category == "family_domestic"
    workflow = common_workflow_contract_result(query, route_matter(query), [
        {"index": 1, "title": "Bharatiya Nyaya Sanhita 2023", "anchor": "bns-2023/sec-316-c@2024-07-01"},
        {"index": 2, "title": "Bharatiya Nagarik Suraksha Sanhita 2023", "anchor": "bnss-2023/sec-173-b@2024-07-01"},
        {"index": 3, "title": "Protection of Women from Domestic Violence Act 2005", "anchor": "domestic-violence-2005/sec-3@1974-01-01"},
        {"index": 4, "title": "Protection of Women from Domestic Violence Act 2005", "anchor": "domestic-violence-2005/sec-12@1974-01-01"},
    ])
    assert workflow is not None
    assert workflow.id == "streedhan_return"
    assert "police/criminal-breach-of-trust track" in answer
    assert "Protection of Women from Domestic Violence" in answer or "Domestic Violence Act" in answer
    assert "entrustment" in answer
    assert "police" in answer


def test_safety_regression_authority_graph_contracts_cover_real_gaps():
    elder_q = "fake call from sbi pension office took 2 lakh from my account 75 yr father"
    elder_sources = [
        {"index": 1, "title": "Information Technology Act 2000", "anchor": "it-2000/sec-66D"},
        {"index": 2, "title": "Bharatiya Nyaya Sanhita 2023", "anchor": "bns-2023/sec-318-a@2024-07-01"},
        {"index": 3, "title": "Bharatiya Nagarik Suraksha Sanhita 2023", "anchor": "bnss-2023/sec-173-b@2024-07-01"},
        {"index": 4, "title": "Reserve Bank Integrated Ombudsman Scheme 2021", "anchor": "rbi-integrated-ombudsman-2021/sec-2"},
        {"index": 5, "title": "Maintenance and Welfare of Parents and Senior Citizens Act 2007", "anchor": "mwp-2007/sec-4"},
    ]
    elder = _grounded_joined(elder_q, elder_sources)
    assert _workflow_id(elder_q, elder_sources) == "elder_bank_pension_impersonation_fraud"
    assert "fake SBI/bank/pension-office call" in elder
    assert "Senior Citizens Act" in elder
    assert "[1]" in elder and "[5]" in elder

    hiv_q = "engagement broken because he hid HIV can I post warning online"
    hiv_sources = [
        {"index": 1, "title": "Human Immunodeficiency Virus and Acquired Immune Deficiency Syndrome (Prevention and Control) Act 2017", "anchor": "hiv-aids-2017/sec-5"},
        {"index": 2, "title": "Hindu Marriage Act 1955", "anchor": "hindu-marriage-1955/sec-12"},
        {"index": 3, "title": "Information Technology Act 2000", "anchor": "it-2000/sec-66E"},
        {"index": 4, "title": "Digital Personal Data Protection Act 2023", "anchor": "dpdp-2023/sec-8"},
        {"index": 5, "title": "Family Courts Act 1984", "anchor": "family-courts-1984/sec-7"},
    ]
    hiv = _grounded_joined(hiv_q, hiv_sources)
    assert _workflow_id(hiv_q, hiv_sources) == "medical_status_online_warning"
    assert "Do not post" in hiv
    assert "HIV Act" in hiv or "HIV/medical status" in hiv
    assert "[1]" in hiv and "[3]" in hiv

    will_q = "father made will in 1998 not registered now after death sons fighting is unregistered will valid"
    will_sources = [
        {"index": 1, "title": "Indian Succession Act 1925", "anchor": "indian-succession-1925/sec-63"},
        {"index": 2, "title": "Registration Act 1908", "anchor": "registration-1908/sec-18"},
    ]
    will = _grounded_joined(will_q, will_sources)
    assert _workflow_id(will_q, will_sources) == "unregistered_will_validity"
    assert "execution/attestation" in will
    assert "Registration Act source is the registration question" in will
    assert "[1]" in will and "[2]" in will


def test_safety_regression_authority_graph_contracts_reduce_legacy_relevance_failures():
    arrest_q = "police arrested my brother but did not tell grounds or give arrest memo DK Basu kya rule hai"
    arrest_sources = [
        {"index": 1, "title": "Constitution of India", "anchor": "constitution-india/sec-21"},
        {"index": 2, "title": "Constitution of India", "anchor": "constitution-india/sec-22"},
        {"index": 3, "title": "Bharatiya Nagarik Suraksha Sanhita 2023", "anchor": "bnss-2023/sec-58@2024-07-01"},
    ]
    arrest = _grounded_joined(arrest_q, arrest_sources)
    assert _workflow_id(arrest_q, arrest_sources) == "arrest_memo_grounds_family_intimation"
    assert "Article 21 liberty and Article 22" in arrest
    assert "arrest memo" in arrest

    senior_q = "tribunal ordered son to pay 10000 per month he stopped paying enforce kaise"
    senior_sources = [
        {"index": 1, "title": "Maintenance and Welfare of Parents and Senior Citizens Act 2007", "anchor": "mwp-2007/sec-11"},
        {"index": 2, "title": "Maintenance and Welfare of Parents and Senior Citizens Act 2007", "anchor": "mwp-2007/sec-13"},
    ]
    senior = _grounded_joined(senior_q, senior_sources)
    assert _workflow_id(senior_q, senior_sources) == "senior_maintenance_order_enforcement"
    assert "enforcement of the senior-citizen maintenance order" in senior
    assert "arrears month-wise chart" in senior

    ndps_q = "brother in NDPS case arrested 110 days no chargesheet default bail possible"
    ndps_sources = [
        {"index": 1, "title": "Narcotic Drugs and Psychotropic Substances Act 1985", "anchor": "ndps-1985/sec-36A"},
        {"index": 2, "title": "Bharatiya Nagarik Suraksha Sanhita 2023", "anchor": "bnss-2023/sec-187-b@2024-07-01"},
    ]
    ndps = _grounded_joined(ndps_q, ndps_sources)
    assert _workflow_id(ndps_q, ndps_sources) == "ndps_default_bail_no_chargesheet"
    assert "110 days/no charge-sheet" in ndps
    assert "Special Court" in ndps

    birth_q = "panchayat secretary not giving me birth certificate of my child born at home"
    birth_sources = [
        {"index": 1, "title": "Registration of Births and Deaths Act 1969", "anchor": "registration-births-deaths-1969/sec-12"},
        {"index": 2, "title": "Right to Information Act 2005", "anchor": "rti-2005/sec-7-c@2025-11-18"},
    ]
    birth = _grounded_joined(birth_q, birth_sources)
    assert _workflow_id(birth_q, birth_sources) == "home_birth_certificate_refusal"
    assert "child born at home" in birth
    assert "birth-registration/certificate request" in birth


def test_selected_workflow_contract_is_the_rendered_answer_for_legacy_shadow_risks():
    cases = [
        (
            "brother in NDPS case arrested 110 days no chargesheet default bail possible",
            "ndps_default_bail_no_chargesheet",
            [
                {"index": 1, "title": "Narcotic Drugs and Psychotropic Substances Act 1985", "anchor": "ndps-1985/sec-36A"},
                {"index": 2, "title": "Bharatiya Nagarik Suraksha Sanhita 2023", "anchor": "bnss-2023/sec-187-b@2024-07-01"},
            ],
        ),
        (
            "police arrested my brother but did not tell grounds or give arrest memo DK Basu kya rule hai",
            "arrest_memo_grounds_family_intimation",
            [
                {"index": 1, "title": "Constitution of India", "anchor": "constitution-india/sec-21"},
                {"index": 2, "title": "Constitution of India", "anchor": "constitution-india/sec-22"},
                {"index": 3, "title": "Bharatiya Nagarik Suraksha Sanhita 2023", "anchor": "bnss-2023/sec-58@2024-07-01"},
            ],
        ),
        (
            "tribunal ordered son to pay 10000 per month he stopped paying enforce kaise",
            "senior_maintenance_order_enforcement",
            [
                {"index": 1, "title": "Maintenance and Welfare of Parents and Senior Citizens Act 2007", "anchor": "mwp-2007/sec-11"},
                {"index": 2, "title": "Maintenance and Welfare of Parents and Senior Citizens Act 2007", "anchor": "mwp-2007/sec-13"},
            ],
        ),
        (
            "my son not giving food and money I am 72 year old where to complain",
            "senior_parent_pension_neglect",
            [
                {"index": 1, "title": "Maintenance and Welfare of Parents and Senior Citizens Act 2007", "anchor": "mwp-2007/sec-4"},
                {"index": 2, "title": "Maintenance and Welfare of Parents and Senior Citizens Act 2007", "anchor": "mwp-2007/sec-5"},
            ],
        ),
        (
            "my son threw me out of my own house i paid for it in 1985 mumbai",
            "senior_parent_pension_neglect",
            [
                {"index": 1, "title": "Maintenance and Welfare of Parents and Senior Citizens Act 2007", "anchor": "mwp-2007/sec-4"},
                {"index": 2, "title": "Maintenance and Welfare of Parents and Senior Citizens Act 2007", "anchor": "mwp-2007/sec-23"},
            ],
        ),
        (
            "mother in delhi son refuses to pay maintenance how much can tribunal order maximum",
            "senior_parent_pension_neglect",
            [
                {"index": 1, "title": "Maintenance and Welfare of Parents and Senior Citizens Act 2007", "anchor": "mwp-2007/sec-9"},
                {"index": 2, "title": "Maintenance and Welfare of Parents and Senior Citizens Act 2007", "anchor": "mwp-2007/sec-5"},
            ],
        ),
        (
            "MGNREGA wages of 4 months not paid sarpanch saying funds not come",
            "mgnrega_fake_muster",
            [
                {"index": 1, "title": "Mahatma Gandhi National Rural Employment Guarantee Act 2005", "anchor": "mgnrega-2005/sec-3"},
                {"index": 2, "title": "Right to Information Act 2005", "anchor": "rti-2005/sec-6"},
            ],
        ),
        (
            "nrega job card not given by panchayat 9 months pls help nuapada odisha",
            "mgnrega_fake_muster",
            [
                {"index": 1, "title": "Mahatma Gandhi National Rural Employment Guarantee Act 2005", "anchor": "mgnrega-2005/sec-19"},
                {"index": 2, "title": "Mahatma Gandhi National Rural Employment Guarantee Act 2005", "anchor": "mgnrega-2005/sec-3"},
            ],
        ),
        (
            "social audit gram sabha showed corruption by sarpanch no action taken nuapada",
            "mgnrega_fake_muster",
            [
                {"index": 1, "title": "Mahatma Gandhi National Rural Employment Guarantee Act 2005", "anchor": "mgnrega-2005/sec-19"},
                {"index": 2, "title": "Right to Information Act 2005", "anchor": "rti-2005/sec-6"},
            ],
        ),
        (
            "ngo helping us said mukhiya did fake job cards no action by collector",
            "mgnrega_fake_muster",
            [
                {"index": 1, "title": "Mahatma Gandhi National Rural Employment Guarantee Act 2005", "anchor": "mgnrega-2005/sec-19"},
                {"index": 2, "title": "Right to Information Act 2005", "anchor": "rti-2005/sec-6"},
            ],
        ),
        (
            "brother arrested uapa 90 days over no chargesheet default bail possible",
            "default_bail_no_chargesheet",
            [
                {"index": 1, "title": "Bharatiya Nagarik Suraksha Sanhita 2023", "anchor": "bnss-2023/sec-187-b@2024-07-01"},
                {"index": 2, "title": "Unlawful Activities (Prevention) Act 1967", "anchor": "uapa-1967/sec-43d"},
                {"index": 3, "title": "Code of Criminal Procedure 1973", "anchor": "crpc-1973/sec-167"},
            ],
        ),
        (
            "brother arrested NDPS 50 gram heroin commercial or not bail chances",
            "ndps_quantity_bail",
            [
                {"index": 1, "title": "Narcotic Drugs and Psychotropic Substances Act 1985", "anchor": "ndps-1985/sec-2"},
                {"index": 2, "title": "Narcotic Drugs and Psychotropic Substances Act 1985", "anchor": "ndps-1985/sec-37"},
            ],
        ),
        (
            "brother arrested ndps 5 gram personal use how is small quantity proven",
            "ndps_quantity_bail",
            [
                {"index": 1, "title": "Narcotic Drugs and Psychotropic Substances Act 1985", "anchor": "ndps-1985/sec-2"},
                {"index": 2, "title": "Narcotic Drugs and Psychotropic Substances Act 1985", "anchor": "ndps-1985/sec-37"},
            ],
        ),
        (
            "father made will in 1998 not registered now after death sons fighting is unregistered will valid",
            "unregistered_will_validity",
            [
                {"index": 1, "title": "Indian Succession Act 1925", "anchor": "indian-succession-1925/sec-63"},
                {"index": 2, "title": "Registration Act 1908", "anchor": "registration-1908/sec-18"},
            ],
        ),
        (
            "i was in yerwada 18 months theft case now released want compensation for delay",
            "custody_delay_compensation_after_release",
            [
                {"index": 1, "title": "Bharatiya Nagarik Suraksha Sanhita 2023", "anchor": "bnss-2023/sec-479@2024-07-01"},
                {"index": 2, "title": "Constitution of India", "anchor": "constitution-india/sec-21"},
                {"index": 3, "title": "Code of Criminal Procedure 1973", "anchor": "crpc-1973/sec-436-a"},
            ],
        ),
        (
            "construction site delhi 14 hour work no overtime contractor laughing when i ask",
            "construction_overtime_wage_claim",
            [
                {"index": 1, "title": "Code on Wages 2019", "anchor": "code-on-wages-2019/sec-17@2019-08-08"},
                {"index": 2, "title": "Building and Other Construction Workers Act 1996", "anchor": "bocw-1996/sec-12"},
            ],
        ),
        (
            "iron ore mine displaced our 12 villages no rehabilitation given keonjhar",
            "mining_displacement_rehabilitation",
            [
                {"index": 1, "title": "Right to Fair Compensation and Transparency in Land Acquisition, Rehabilitation and Resettlement Act 2013", "anchor": "rfctlarr-2013/sec-41-b"},
                {"index": 2, "title": "Mines and Minerals (Development and Regulation) Act 1957", "anchor": "mmdr-1957#header"},
            ],
        ),
        (
            "son 17 yrs in adult jail puzhal pocso case age proof school certificate where to file",
            "juvenile_adult_jail_age_determination",
            [
                {"index": 1, "title": "Juvenile Justice (Care and Protection of Children) Act 2015", "anchor": "jj-2015/sec-9"},
                {"index": 2, "title": "Juvenile Justice (Care and Protection of Children) Act 2015", "anchor": "jj-2015/sec-94"},
                {"index": 3, "title": "Juvenile Justice (Care and Protection of Children) Act 2015", "anchor": "jj-2015/sec-2-w"},
            ],
        ),
        (
            "16 yr boy detained adult jail 2 weeks already how to transfer observation home",
            "juvenile_adult_jail_age_determination",
            [
                {"index": 1, "title": "Juvenile Justice (Care and Protection of Children) Act 2015", "anchor": "jj-2015/sec-9"},
                {"index": 2, "title": "Juvenile Justice (Care and Protection of Children) Act 2015", "anchor": "jj-2015/sec-94"},
                {"index": 3, "title": "Juvenile Justice (Care and Protection of Children) Act 2015", "anchor": "jj-2015/sec-10"},
            ],
        ),
    ]

    for query, expected_id, passages in cases:
        route = route_matter(query)
        workflow = common_workflow_contract_result(query, route, passages)
        rendered = _grounded_template_lines(query, route, passages)
        payload = _workflow_event_payload(query, passages, rendered)

        assert workflow is not None
        assert workflow.id == expected_id
        assert rendered == workflow.lines
        assert payload["id"] == expected_id
        assert payload["source"] == workflow.source
        assert payload["contract_miss_reason"] is None

    senior_food = _grounded_joined(
        "my son not giving food and money I am 72 year old where to complain",
        [
            {"index": 1, "title": "Maintenance and Welfare of Parents and Senior Citizens Act 2007", "anchor": "mwp-2007/sec-4"},
            {"index": 2, "title": "Maintenance and Welfare of Parents and Senior Citizens Act 2007", "anchor": "mwp-2007/sec-5"},
        ],
    )
    assert "food, money, maintenance" in senior_food
    assert "pension" not in senior_food.lower()

    senior_max = _grounded_joined(
        "mother in delhi son refuses to pay maintenance how much can tribunal order maximum",
        [
            {"index": 1, "title": "Maintenance and Welfare of Parents and Senior Citizens Act 2007", "anchor": "mwp-2007/sec-9"},
            {"index": 2, "title": "Maintenance and Welfare of Parents and Senior Citizens Act 2007", "anchor": "mwp-2007/sec-5"},
        ],
    )
    assert "Rs.10,000" in senior_max

    senior_house = _grounded_joined(
        "my son threw me out of my own house i paid for it in 1985 mumbai",
        [
            {"index": 1, "title": "Maintenance and Welfare of Parents and Senior Citizens Act 2007", "anchor": "mwp-2007/sec-4"},
            {"index": 2, "title": "Maintenance and Welfare of Parents and Senior Citizens Act 2007", "anchor": "mwp-2007/sec-23"},
        ],
    )
    assert "1985 payment/ownership papers" in senior_house
    assert "Maintenance Tribunal" in senior_house
    assert "threw you out of your own house in Mumbai" in senior_house
    assert "residence access, support, and protection from exclusion" in senior_house
    assert "pension" not in senior_house.lower()

    mgnrega_wage = _grounded_joined(
        "MGNREGA wages of 4 months not paid sarpanch saying funds not come",
        [
            {"index": 1, "title": "Mahatma Gandhi National Rural Employment Guarantee Act 2005", "anchor": "mgnrega-2005/sec-3"},
            {"index": 2, "title": "Right to Information Act 2005", "anchor": "rti-2005/sec-6"},
        ],
    )
    assert "wage delay" in mgnrega_wage
    assert "ordinary private wage dispute" in mgnrega_wage

    mgnrega_job_card = _grounded_joined(
        "nrega job card not given by panchayat 9 months pls help nuapada odisha",
        [
            {"index": 1, "title": "Mahatma Gandhi National Rural Employment Guarantee Act 2005", "anchor": "mgnrega-2005/sec-19"},
            {"index": 2, "title": "Mahatma Gandhi National Rural Employment Guarantee Act 2005", "anchor": "mgnrega-2005/sec-3"},
        ],
    )
    assert "job-card refusal" in mgnrega_job_card
    assert "Nuapada/Odisha" in mgnrega_job_card
    assert "generic labour complaint" in mgnrega_job_card

    mgnrega_social_audit = _grounded_joined(
        "social audit gram sabha showed corruption by sarpanch no action taken nuapada",
        [
            {"index": 1, "title": "Mahatma Gandhi National Rural Employment Guarantee Act 2005", "anchor": "mgnrega-2005/sec-19"},
            {"index": 2, "title": "Right to Information Act 2005", "anchor": "rti-2005/sec-6"},
        ],
    )
    assert "social-audit" in mgnrega_social_audit
    assert "Gram Sabha" in mgnrega_social_audit
    assert "corruption by the sarpanch and no action taken" in mgnrega_social_audit
    assert "action-taken report" in mgnrega_social_audit
    assert "ordinary wage-delay complaint" in mgnrega_social_audit

    mgnrega_fake_cards = _grounded_joined(
        "ngo helping us said mukhiya did fake job cards no action by collector",
        [
            {"index": 1, "title": "Mahatma Gandhi National Rural Employment Guarantee Act 2005", "anchor": "mgnrega-2005/sec-19"},
            {"index": 2, "title": "Right to Information Act 2005", "anchor": "rti-2005/sec-6"},
        ],
    )
    assert "mukhiya/sarpanch" in mgnrega_fake_cards
    assert "fake job cards" in mgnrega_fake_cards
    assert "collector has not acted" in mgnrega_fake_cards
    assert "NGO/helper" in mgnrega_fake_cards
    assert "job-card refusal" not in mgnrega_fake_cards

    uapa_default = _grounded_joined(
        "brother arrested uapa 90 days over no chargesheet default bail possible",
        [
            {"index": 1, "title": "Bharatiya Nagarik Suraksha Sanhita 2023", "anchor": "bnss-2023/sec-187-b@2024-07-01"},
            {"index": 2, "title": "Unlawful Activities (Prevention) Act 1967", "anchor": "uapa-1967/sec-43d"},
            {"index": 3, "title": "Code of Criminal Procedure 1973", "anchor": "crpc-1973/sec-167"},
        ],
    )
    assert "180 days" in uapa_default
    assert "Special Court extension order" in uapa_default

    ndps_quantity = _grounded_joined(
        "brother arrested NDPS 50 gram heroin commercial or not bail chances",
        [
            {"index": 1, "title": "Narcotic Drugs and Psychotropic Substances Act 1985", "anchor": "ndps-1985/sec-2"},
            {"index": 2, "title": "Narcotic Drugs and Psychotropic Substances Act 1985", "anchor": "ndps-1985/sec-37"},
        ],
    )
    assert "50 gram heroin" in ndps_quantity
    assert "commercial or not" in ndps_quantity
    assert "do not decide commercial quantity from the user wording alone" in ndps_quantity
    assert "Section 37" in ndps_quantity

    juvenile_transfer = _grounded_joined(
        "16 yr boy detained adult jail 2 weeks already how to transfer observation home",
        [
            {"index": 1, "title": "Juvenile Justice (Care and Protection of Children) Act 2015", "anchor": "jj-2015/sec-9"},
            {"index": 2, "title": "Juvenile Justice (Care and Protection of Children) Act 2015", "anchor": "jj-2015/sec-94"},
            {"index": 3, "title": "Juvenile Justice (Care and Protection of Children) Act 2015", "anchor": "jj-2015/sec-10"},
        ],
    )
    assert "16-year-old boy" in juvenile_transfer
    assert "observation home" in juvenile_transfer
    assert "adult jail" in juvenile_transfer


def test_variant40_regressions_route_to_specific_contracts():
    senior_sources = [
        {"index": 1, "title": "Maintenance and Welfare of Parents and Senior Citizens Act 2007", "anchor": "mwp-2007/sec-4"},
        {"index": 2, "title": "Maintenance and Welfare of Parents and Senior Citizens Act 2007", "anchor": "mwp-2007/sec-23"},
    ]
    senior_house_q = "senior mother thrown out by son from self acquired house in navi mumbai"
    senior_house = _grounded_joined(senior_house_q, senior_sources)
    assert route_matter(senior_house_q).category == "senior_citizen"
    assert _workflow_id(senior_house_q, senior_sources) == "senior_parent_pension_neglect"
    assert "self-acquired or self-paid house in Navi Mumbai/Mumbai" in senior_house
    assert "Maintenance Tribunal" in senior_house

    senior_thane_q = "old parent pushed from thane flat bought from my savings"
    senior_thane = _grounded_joined(senior_thane_q, senior_sources)
    assert "self-acquired or self-paid flat in Thane" in senior_thane
    assert "Maintenance Tribunal" in senior_thane

    senior_thane_mumbai_q = "i am 74 my son pushed me out from flat bought by me in 1990 thane mumbai no rent money"
    senior_thane_mumbai = _grounded_joined(senior_thane_mumbai_q, senior_sources)
    assert "self-acquired or self-paid flat in Thane/Mumbai" in senior_thane_mumbai
    assert "residence" in senior_thane_mumbai
    assert "Maintenance Tribunal" in senior_thane_mumbai

    senior_passbook_q = "i am 70 son keeps my passbook and atm card not giving money for food"
    senior_passbook = _grounded_joined(senior_passbook_q, senior_sources)
    assert route_matter(senior_passbook_q).category == "senior_citizen"
    assert "pension or passbook money, ATM-card access, or bank money" in senior_passbook
    assert "food/medicine money" in senior_passbook

    senior_passbook_bihar_q = "father 83 no food and son keeps bank passbook in bihar"
    senior_passbook_bihar = _grounded_joined(senior_passbook_bihar_q, senior_sources)
    assert "being controlled in Bihar" in senior_passbook_bihar
    assert "food/medicine money" in senior_passbook_bihar

    senior_room_q = "bahu and son are not allowing my mother to enter her room in pune she is 80"
    senior_room = _grounded_joined(senior_room_q, senior_sources)
    assert _workflow_id(senior_room_q, senior_sources) == "senior_parent_pension_neglect"
    assert "room, kitchen, bathroom, or house in Pune" in senior_room
    assert "Maintenance Tribunal request as residence access" in senior_room

    senior_abandon_q = "i am 73 mother, son remarried and left me alone in village bihar no food no monthly support"
    senior_abandon = _grounded_joined(senior_abandon_q, senior_sources)
    assert "second marriage or remarriage in Bihar" in senior_abandon
    assert "no food, no monthly support" in senior_abandon

    senior_second_marriage_q = "mother 79 left alone after son second marriage no ration medicine"
    senior_second_marriage = _grounded_joined(senior_second_marriage_q, senior_sources)
    assert "left alone after the son's second marriage with no ration or medicine" in senior_second_marriage
    assert "second marriage or remarriage" in senior_second_marriage
    assert "ration, medicine" in senior_second_marriage

    senior_gift_children_q = "my 69 father gave gift deed house now children refuse medicine and maintenance"
    senior_gift_children = _grounded_joined(senior_gift_children_q, senior_sources)
    assert "children now refuse medicine and maintenance" in senior_gift_children
    assert "Section 23 transfer/gift relief" in senior_gift_children

    senior_sleep_outside_q = "mother 80 transferred flat to son now bahu telling her to sleep outside"
    senior_sleep_outside = _grounded_joined(senior_sleep_outside_q, senior_sources)
    assert "mother transferred a flat to her son" in senior_sleep_outside
    assert "sleep outside" in senior_sleep_outside
    assert "immediate residence access/support" in senior_sleep_outside

    mgnrega_sources = [
        {"index": 1, "title": "Mahatma Gandhi National Rural Employment Guarantee Act 2005", "anchor": "mgnrega-2005/sec-19"},
        {"index": 2, "title": "Right to Information Act 2005", "anchor": "rti-2005/sec-6"},
    ]
    job_card_q = "nrega job card application pending 8 months panchayat says come later"
    job_card = _grounded_joined(job_card_q, mgnrega_sources)
    assert _workflow_id(job_card_q, mgnrega_sources) == "mgnrega_fake_muster"
    assert "application pending" in job_card
    assert "eight-month delay" in job_card
    assert "Programme Officer/BDO" in job_card

    widow_job_card_q = "odisha nuapada panchayat not issuing job card to widow family"
    widow_job_card = _grounded_joined(widow_job_card_q, mgnrega_sources)
    assert route_matter(widow_job_card_q).category == "labour_exploitation_discrimination"
    assert _workflow_id(widow_job_card_q, mgnrega_sources) == "mgnrega_fake_muster"
    assert "job-card refusal" in widow_job_card
    assert "Nuapada/Odisha" in widow_job_card
    assert "senior" not in widow_job_card.lower()

    payment_q = "mgnrega payment shows paid but bank passbook has no credit"
    payment = _grounded_joined(payment_q, mgnrega_sources)
    assert "shows paid but has no bank/passbook credit" in payment
    assert "FTO/payment order" in payment

    social_audit_q = "social audit report has names of dead people getting wages sarpanch protected"
    social_audit = _grounded_joined(social_audit_q, mgnrega_sources)
    assert "social-audit report showing names of dead people" in social_audit
    assert "written action-taken report" in social_audit

    dead_persons_q = "gram sabha social audit found dead persons wages, bdo silent"
    dead_persons = _grounded_joined(dead_persons_q, mgnrega_sources)
    assert "dead persons wages and the BDO is silent" in dead_persons
    assert "dead persons wages" in dead_persons
    assert "BDO is silent" in dead_persons
    assert "action-taken report" in dead_persons

    juvenile_child_conflict_sources = [
        {"index": 1, "title": "Juvenile Justice (Care and Protection of Children) Act 2015", "anchor": "jj-2015/sec-9"},
        {"index": 2, "title": "Juvenile Justice (Care and Protection of Children) Act 2015", "anchor": "jj-2015/sec-94"},
        {"index": 3, "title": "Juvenile Justice (Care and Protection of Children) Act 2015", "anchor": "jj-2015/sec-2-u"},
    ]
    juvenile_child_conflict_q = "child in conflict court ignoring age certificate what application to file"
    juvenile_child_conflict = _grounded_joined(juvenile_child_conflict_q, juvenile_child_conflict_sources)
    assert route_matter(juvenile_child_conflict_q).category == "criminal_defence_bail"
    assert _workflow_id(juvenile_child_conflict_q, juvenile_child_conflict_sources) == "juvenile_adult_jail_age_determination"
    assert "age-determination/juvenility application" in juvenile_child_conflict
    assert "current criminal court or Juvenile Justice Board" in juvenile_child_conflict

    after_collector_q = "gram sabha raised fake muster corruption, who after bdo and collector"
    after_collector = _grounded_joined(after_collector_q, mgnrega_sources)
    assert "Gram Sabha issue has already gone after BDO and Collector" in after_collector
    assert "collector record" in after_collector

    juvenile_sources = [
        {"index": 1, "title": "Juvenile Justice (Care and Protection of Children) Act 2015", "anchor": "jj-2015/sec-94"},
        {"index": 2, "title": "Juvenile Justice (Care and Protection of Children) Act 2015", "anchor": "jj-2015/sec-9"},
        {"index": 3, "title": "Juvenile Justice (Care and Protection of Children) Act 2015", "anchor": "jj-2015/sec-10"},
    ]
    juvenile_q = "minor accused age proof aadhaar school certificate which court decides juvenile"
    juvenile = _grounded_joined(juvenile_q, juvenile_sources)
    assert route_matter(juvenile_q).category == "criminal_defence_bail"
    assert _workflow_id(juvenile_q, juvenile_sources) == "juvenile_adult_jail_age_determination"
    assert "not an education-record dispute" in juvenile
    assert "Aadhaar only as supporting ID" in juvenile

    juvenile_without_sec94_sources = [
        {"index": 1, "title": "Juvenile Justice (Care and Protection of Children) Act 2015", "anchor": "jj-2015/sec-2-u"},
        {"index": 2, "title": "Juvenile Justice (Care and Protection of Children) Act 2015", "anchor": "jj-2015/sec-9"},
        {"index": 3, "title": "Juvenile Justice (Care and Protection of Children) Act 2015", "anchor": "jj-2015/sec-2-w"},
    ]
    juvenile_puzhal_q = "17 yrs son in pocso case puzhal adult prison school certificate proof"
    juvenile_puzhal = _grounded_joined(juvenile_puzhal_q, juvenile_without_sec94_sources)
    assert _workflow_id(juvenile_puzhal_q, juvenile_without_sec94_sources) == "juvenile_adult_jail_age_determination"
    assert "juvenile age proof" in juvenile_puzhal
    assert "school certificate" in juvenile_puzhal
    assert "adult jail or prison" in juvenile_puzhal

    juvenile_nephew_q = "my 17 year nephew accused in pocso is in adult prison, school DOB proof available"
    juvenile_nephew = _grounded_joined(juvenile_nephew_q, juvenile_sources)
    assert route_matter(juvenile_nephew_q).category == "criminal_defence_bail"
    assert _workflow_id(juvenile_nephew_q, juvenile_sources) == "juvenile_adult_jail_age_determination"
    assert "not ordinary adult bail alone" in juvenile_nephew
    assert "Juvenile Justice Board (JJB)" in juvenile_nephew
    assert "school certificate" in juvenile_nephew
    assert "observation-home transfer from adult jail" in juvenile_nephew

    default_bail_sources = [
        {"index": 1, "title": "Bharatiya Nagarik Suraksha Sanhita 2023", "anchor": "bnss-2023/sec-187-d"},
        {"index": 2, "title": "Bharatiya Nyaya Sanhita 2023", "anchor": "bns-2023/sec-318-b"},
        {"index": 3, "title": "Code of Criminal Procedure 1973", "anchor": "crpc-1973/sec-167-b"},
        {"index": 4, "title": "Indian Penal Code 1860", "anchor": "ipc-1860/sec-420"},
    ]
    no_challan_q = "ipc cheating arrest 75 days no challan filed police says wait what bail"
    no_challan = _grounded_joined(no_challan_q, default_bail_sources)
    assert _workflow_id(no_challan_q, default_bail_sources) == "default_bail_no_chargesheet"
    assert "default bail check" in no_challan
    assert "chargesheet/final-report" in no_challan

    bns_default_q = "bns 318 cheating arrest 70 days no chargesheet how to calculate 60 or 90"
    bns_default = _grounded_joined(bns_default_q, default_bail_sources)
    assert _workflow_id(bns_default_q, default_bail_sources) == "default_bail_no_chargesheet"
    assert "BNS offence source" in bns_default
    assert "60 or 90 day default-bail question" in bns_default

    bns_318_remand_q = "bns 318 remand 72 days no chargesheet should it be 60 or 90"
    bns_318_remand = _grounded_joined(bns_318_remand_q, default_bail_sources)
    assert _workflow_id(bns_318_remand_q, default_bail_sources) == "default_bail_no_chargesheet"
    assert "BNS offence source" in bns_318_remand
    assert "60 or 90 day default-bail question" in bns_318_remand

    extension_q = "police filed only extension request no final report after 75 days ipc cheating"
    extension_default = _grounded_joined(extension_q, default_bail_sources)
    assert _workflow_id(extension_q, default_bail_sources) == "default_bail_no_chargesheet"
    assert "extension request without a final report/chargesheet" in extension_default
    assert "CrPC Section 167" in extension_default

    ndps_sources = [
        {"index": 1, "title": "Narcotic Drugs and Psychotropic Substances Act 1985", "anchor": "ndps-1985/sec-2"},
        {"index": 2, "title": "Narcotic Drugs and Psychotropic Substances Act 1985", "anchor": "ndps-1985/sec-37"},
        {"index": 3, "title": "Narcotic Drugs and Psychotropic Substances Act 1985", "anchor": "ndps-1985/sec-36A"},
    ]
    mdma_q = "mdma found in my friend's bag fsl quantity not clear can section 37 apply"
    mdma = _grounded_joined(mdma_q, ndps_sources)
    assert route_matter(mdma_q).category == "criminal_defence_bail"
    assert _workflow_id(mdma_q, ndps_sources) == "ndps_quantity_bail"
    assert "friend or another person" in mdma
    assert "FSL quantity" in mdma

    ndps_default_q = "ndps 110 days no complaint filed special court default bail possible"
    ndps_default = _grounded_joined(ndps_default_q, ndps_sources)
    assert _workflow_id(ndps_default_q, ndps_sources) == "ndps_default_bail_no_chargesheet"
    assert "110 days/no charge-sheet/no complaint filed custody" in ndps_default
    assert "Special Court/Special NDPS Court" in ndps_default


def test_reviewed_workflow_contract_promotion_keeps_selected_template_from_filler():
    query = "construction site delhi 14 hour work no overtime contractor laughing when i ask"
    passages = [
        {"index": 1, "title": "Code on Wages 2019", "anchor": "code-on-wages-2019/sec-17@2019-08-08"},
        {"index": 2, "title": "Building and Other Construction Workers Act 1996", "anchor": "bocw-1996/sec-12"},
    ]
    route = route_matter(query)
    workflow = common_workflow_contract_result(query, route, passages)
    rendered = _grounded_template_lines(query, route, passages)

    assert workflow is not None
    assert workflow.id == "construction_overtime_wage_claim"
    sentence = next(line for line in workflow.lines if "14-hour days" in line)
    promoted = _promote_reviewed_workflow_contract_line(
        SentenceVerification(
            text=sentence,
            status=SentenceStatus.UNSUPPORTED,
            citations=[1],
            reason="mnli low score",
        ),
        workflow,
        rendered,
    )

    assert promoted.status == SentenceStatus.OK
    assert promoted.reason == "reviewed workflow contract line"

    unrelated = _promote_reviewed_workflow_contract_line(
        SentenceVerification(
            text="File within 7 days or you lose the wage claim [1].",
            status=SentenceStatus.UNSUPPORTED,
            citations=[1],
        ),
        workflow,
        rendered,
    )
    assert unrelated.status == SentenceStatus.UNSUPPORTED


def test_domestic_safety_primary_workflow_contract_lines_are_not_auto_promoted():
    query = "my husband is beating me right now what should i do"
    passages = [
        {"index": 1, "title": "Protection of Women from Domestic Violence Act 2005", "anchor": "pwdva-2005/sec-3"},
        {"index": 2, "title": "Protection of Women from Domestic Violence Act 2005", "anchor": "pwdva-2005/sec-18"},
        {"index": 3, "title": "Bharatiya Nyaya Sanhita 2023", "anchor": "bns-2023/sec-115"},
    ]
    route = route_matter(query)
    workflow = common_workflow_contract_result(query, route, passages)
    rendered = _grounded_template_lines(query, route, passages)

    assert workflow is not None
    assert workflow.answer_mode == "safety_primary"
    sentence = next(line for line in workflow.lines if "[" in line and not line.startswith("**"))
    promoted = _promote_reviewed_workflow_contract_line(
        SentenceVerification(
            text=sentence,
            status=SentenceStatus.UNSUPPORTED,
            citations=[1],
            reason="mnli low score",
        ),
        workflow,
        rendered,
    )

    assert promoted.status == SentenceStatus.UNSUPPORTED


def test_custody_compensation_safety_workflow_contract_lines_are_promoted():
    query = "need help, i was in jail 7 yrs acquitted now how to get compensation state legal aid what next"
    passages = [
        {"index": 1, "title": "Constitution of India", "anchor": "constitution-india/sec-21"},
        {"index": 2, "title": "Bharatiya Nagarik Suraksha Sanhita 2023", "anchor": "bnss-2023/sec-479@2024-07-01"},
        {"index": 3, "title": "Code of Criminal Procedure 1973", "anchor": "crpc-1973/sec-436-a"},
    ]
    route = route_matter(query)
    workflow = common_workflow_contract_result(query, route, passages)
    rendered = _grounded_template_lines(query, route, passages)

    assert workflow is not None
    assert workflow.id == "custody_delay_compensation_after_release"
    assert workflow.answer_mode == "safety_primary"
    sentence = next(line for line in workflow.lines if "Article 21 liberty source" in line)
    promoted = _promote_reviewed_workflow_contract_line(
        SentenceVerification(
            text=sentence,
            status=SentenceStatus.UNSUPPORTED,
            citations=[1],
            reason="mnli low score",
        ),
        workflow,
        rendered,
    )

    assert promoted.status == SentenceStatus.OK
    assert promoted.reason == "reviewed workflow contract line"


def test_stage2_failed_cluster_reviewed_workflows_own_answers():
    cases = [
        (
            "neighbour used caste slur and hit me but station refuses case",
            [
                {"index": 1, "title": "Bharatiya Nagarik Suraksha Sanhita 2023", "anchor": "bnss-2023/sec-175@2024-07-01"},
                {"index": 2, "title": "Bharatiya Nyaya Sanhita 2023", "anchor": "bns-2023/sec-351@2024-07-01"},
                {"index": 3, "title": "Scheduled Castes and Scheduled Tribes (Prevention of Atrocities) Act 1989", "anchor": "sc-st-poa-1989/sec-3-d@2025-09-21"},
                {"index": 4, "title": "Constitution of India", "anchor": "constitution-india/sec-21"},
            ],
            "caste_slur_assault_fir_refusal",
        ),
        (
            "village people called my mother daayan and beat her",
            [
                {"index": 1, "title": "Bharatiya Nyaya Sanhita 2023", "anchor": "bns-2023/sec-117@2024-07-01"},
                {"index": 2, "title": "Bharatiya Nagarik Suraksha Sanhita 2023", "anchor": "bnss-2023/sec-173-b@2024-07-01"},
                {"index": 3, "title": "Bharatiya Nagarik Suraksha Sanhita 2023", "anchor": "bnss-2023/sec-175@2024-07-01"},
            ],
            "witch_branding_violence",
        ),
        (
            "neighbour made false 420 case on me because of money dispute",
            [
                {"index": 1, "title": "Bharatiya Nagarik Suraksha Sanhita 2023", "anchor": "bnss-2023/sec-528@2024-07-01"},
                {"index": 2, "title": "Code of Criminal Procedure 1973", "anchor": "crpc-1973/sec-482"},
                {"index": 3, "title": "Bharatiya Nyaya Sanhita 2023", "anchor": "bns-2023/sec-318-a@2024-07-01"},
            ],
            "false_fir_defence",
        ),
        (
            "hawker zone people are removing my vegetable stall what to do",
            [
                {"index": 1, "title": "Street Vendors (Protection of Livelihood and Regulation of Street Vending) Act 2014", "anchor": "street-vendors-2014/sec-18"},
                {"index": 2, "title": "Street Vendors (Protection of Livelihood and Regulation of Street Vending) Act 2014", "anchor": "street-vendors-2014/sec-19"},
                {"index": 3, "title": "Street Vendors (Protection of Livelihood and Regulation of Street Vending) Act 2014", "anchor": "street-vendors-2014/sec-4"},
            ],
            "street_vendor_removal",
        ),
        (
            "court ordered maintenance but husband is not paying for 8 months",
            [
                {"index": 1, "title": "Family Courts Act 1984", "anchor": "family-courts-1984/sec-7"},
                {"index": 2, "title": "Bharatiya Nagarik Suraksha Sanhita 2023", "anchor": "bnss-2023/sec-144@2024-07-01"},
                {"index": 3, "title": "Protection of Women from Domestic Violence Act 2005", "anchor": "domestic-violence-2005/sec-20@1974-01-01"},
            ],
            "maintenance_order_nonpayment",
        ),
    ]

    for query, passages, expected_id in cases:
        route = route_matter(query)
        workflow = common_workflow_contract_result(query, route, passages)
        rendered = _grounded_template_lines(query, route, passages)
        assert workflow is not None, query
        assert workflow.id == expected_id, query
        assert workflow.answer_mode == "primary", query
        assert rendered == workflow.lines, query
        if expected_id == "caste_slur_assault_fir_refusal":
            assert any("Article 21 life/dignity/liberty source" in line for line in workflow.lines)


def test_ndps_bail_tihar_does_not_get_prison_mulaqat_workflow():
    query = "need help, ndps bail rejected 6 times by session court husband 3 yrs in tihar option what next"
    passages = [
        {"index": 1, "title": "Constitution of India", "anchor": "constitution-india/sec-21"},
        {"index": 2, "title": "Prisons Act 1894", "anchor": "prisons-1894#header"},
        {"index": 3, "title": "Bharatiya Nagarik Suraksha Sanhita 2023", "anchor": "bnss-2023/sec-483@2024-07-01"},
        {"index": 4, "title": "Narcotic Drugs and Psychotropic Substances Act 1985", "anchor": "ndps-1985/sec-36A"},
        {"index": 5, "title": "Narcotic Drugs and Psychotropic Substances Act 1985", "anchor": "ndps-1985/sec-37"},
    ]
    route = route_matter(query)
    workflow = common_workflow_contract_result(query, route, passages)

    assert workflow is not None
    assert workflow.id != "prison_mulaqat_books"
    assert workflow.id in {"ndps_quantity_bail", "ndps_default_bail_no_chargesheet"}


def test_critical_otp_bank_refund_keeps_rbi_ombudsman_track():
    query = "OTP shared by mistake and 50000 gone, bank says customer negligence no refund"
    passages = [
        {"index": 1, "title": "Reserve Bank Integrated Ombudsman Scheme 2021", "anchor": "rbi-integrated-ombudsman-2021/sec-2@2007-01-01"},
        {"index": 2, "title": "Bharatiya Nyaya Sanhita 2023", "anchor": "bns-2023/sec-318-a@2024-07-01"},
        {"index": 3, "title": "Bharatiya Nagarik Suraksha Sanhita 2023", "anchor": "bnss-2023/sec-173-b@2024-07-01"},
        {"index": 4, "title": "Information Technology Act 2000", "anchor": "it-2000/sec-66C"},
    ]
    route = route_matter(query)
    workflow = common_workflow_contract_result(query, route, passages)
    rendered = _grounded_template_lines(query, route, passages)

    assert workflow is not None
    assert workflow.id == "cyber_money_fraud"
    assert rendered == workflow.lines
    rbi_line = next(line for line in workflow.lines if "RBI Ombudsman/CMS" in line)
    promoted = _promote_reviewed_workflow_contract_line(
        SentenceVerification(
            text=rbi_line,
            status=SentenceStatus.UNSUPPORTED,
            citations=[1],
            reason="mnli low score",
        ),
        workflow,
        rendered,
    )

    assert promoted.status == SentenceStatus.OK
    assert "bank/RBI refund track" in " ".join(rendered)


def test_stage1_critical_repairs_select_real_user_workflow_contracts():
    emi_q = "bajaj finserv EMI bounced because of bank error, now they are charging 6000 penalty and threatening CIBIL"
    emi_passages = [
        {"index": 1, "title": "Reserve Bank Integrated Ombudsman Scheme 2021", "anchor": "rbi-integrated-ombudsman-2021/sec-2"},
        {"index": 2, "title": "Credit Information Companies Regulation Act 2005", "anchor": "credit-information-companies-2005/sec-18"},
        {"index": 3, "title": "Consumer Protection Act 2019", "anchor": "consumer-protection-2019/sec-35"},
    ]
    emi = _grounded_joined(emi_q, emi_passages)
    assert route_matter(emi_q).category == "banking_credit_dispute"
    assert _workflow_id(emi_q, emi_passages) == "emi_penalty_cibil_dispute"
    assert "not as loan-app contact harassment" in emi
    assert "penalty breakup" in emi
    assert "CIBIL screenshot" in emi

    minor_q = "my 17 year daughter ran away with boy from different religion police saying love jihad what should I do"
    minor_passages = [
        {"index": 1, "title": "Protection of Children from Sexual Offences Act 2012", "anchor": "pocso-2012/sec-19"},
        {"index": 2, "title": "Bharatiya Nagarik Suraksha Sanhita 2023", "anchor": "bnss-2023/sec-173"},
        {"index": 3, "title": "Bharatiya Nyaya Sanhita 2023", "anchor": "bns-2023/sec-137"},
        {"index": 4, "title": "Constitution of India", "anchor": "constitution-india/sec-21"},
    ]
    minor = _grounded_joined(minor_q, minor_passages)
    assert route_matter(minor_q).category == "police_fir"
    assert _workflow_id(minor_q, minor_passages) == "minor_interfaith_child_safety_pocso"
    assert "do not treat 'love jihad' as the legal category" in minor
    assert "CWC/SJPU" in minor
    assert "Article 21" in minor

    accused_q = "my girlfriend filed rape case against me saying I promised marriage but relationship broke up what to do"
    accused_passages = [
        {"index": 1, "title": "Bharatiya Nyaya Sanhita 2023", "anchor": "bns-2023/sec-69"},
        {"index": 2, "title": "Bharatiya Nyaya Sanhita 2023", "anchor": "bns-2023/sec-63"},
        {"index": 3, "title": "Bharatiya Nagarik Suraksha Sanhita 2023", "anchor": "bnss-2023/sec-480"},
    ]
    accused = _grounded_joined(accused_q, accused_passages)
    assert route_matter(accused_q).category == "criminal_defence_bail"
    assert _workflow_id(accused_q, accused_passages) == "promise_to_marry_rape_accused_defence"
    assert "serious accused-side sexual-offence defence issue" in accused
    assert "do not contact, threaten, or pressure the complainant" in accused

    vape_q = "passport seized in mumbai airport for vape cartridge cbd legal in goa"
    vape_passages = [
        {"index": 1, "title": "Narcotic Drugs and Psychotropic Substances Act 1985", "anchor": "ndps-1985/sec-2"},
        {"index": 2, "title": "Narcotic Drugs and Psychotropic Substances Act 1985", "anchor": "ndps-1985/sec-37"},
    ]
    vape = _grounded_joined(vape_q, vape_passages)
    assert route_matter(vape_q).category == "criminal_defence_bail"
    assert _workflow_id(vape_q, vape_passages) == "ndps_quantity_bail"
    assert "CBD/THC vape cartridge" in vape
    assert "passport-retention risk" in vape

    custody_q = "acquitted after 4 years in jail can I sue state for compensation"
    custody_passages = [
        {"index": 1, "title": "Constitution of India", "anchor": "constitution-india/sec-21"},
        {"index": 2, "title": "Bharatiya Nagarik Suraksha Sanhita 2023", "anchor": "bnss-2023/sec-479"},
        {"index": 3, "title": "Code of Criminal Procedure 1973", "anchor": "crpc-1973/sec-436-a"},
    ]
    custody = _grounded_joined(custody_q, custody_passages)
    assert route_matter(custody_q).category == "custody_compensation"
    assert _workflow_id(custody_q, custody_passages) == "custody_delay_compensation_after_release"
    assert "compensation is not automatic" in custody
    assert "acquittal" in custody


def test_stage2_money_identity_failures_have_deterministic_workflow_owners():
    sources = [
        {"index": 1, "title": "Reserve Bank Integrated Ombudsman Scheme 2021", "anchor": "rbi-integrated-ombudsman-2021/sec-2"},
        {"index": 2, "title": "Information Technology Act 2000", "anchor": "it-2000/sec-66C"},
        {"index": 3, "title": "Bharatiya Nyaya Sanhita 2023", "anchor": "bns-2023/sec-351"},
        {"index": 4, "title": "Digital Personal Data Protection Act 2023", "anchor": "dpdp-2023/sec-8"},
        {"index": 5, "title": "Aadhaar Act 2016", "anchor": "aadhaar-2016/sec-29"},
        {"index": 6, "title": "Telecommunications Act 2023", "anchor": "telecommunications-2023/sec-29"},
        {"index": 7, "title": "Credit Information Companies (Regulation) Act 2005", "anchor": "credit-information-companies-2005/sec-18"},
        {"index": 8, "title": "Banking Regulation Act 1949", "anchor": "banking-regulation-1949/sec-35A"},
            {"index": 9, "title": "Bharatiya Nagarik Suraksha Sanhita 2023", "anchor": "bnss-2023/sec-173"},
            {"index": 10, "title": "Consumer Protection Act 2019", "anchor": "consumer-protection-2019/sec-35"},
            {"index": 11, "title": "Bharatiya Nagarik Suraksha Sanhita 2023", "anchor": "bnss-2023/sec-106"},
        ]
    sources.extend(
        {**source, "index": 20 + offset}
        for offset, source in enumerate(LOAN_APP_REGULATORY_SOURCES)
    )
    cases = {
        "someone posted my phone number on dating app and strangers are calling me": (
            "dating_app_phone_number_abuse",
            ("do not frame it as obscene-publication", "dating-app profile/link"),
        ),
        "IMPS transfer failed beneficiary did not get money but bank deducted amount": (
            "wrong_bank_debit",
            ("RBI Ombudsman/CMS", "transaction ID/RRN"),
        ),
        "PAN photocopy leaked in Telegram and someone opened bank account using it": (
            "pan_leak_fake_bank_account",
            ("DPDP personal-data breach", "IT Act identity"),
        ),
        "CIBIL shows fake loan from NBFC but signature is not mine": (
            "false_nbfc_credit_identity_record",
            ("Credit Information Companies", "signature"),
        ),
        "my Aadhaar was used to issue SIM and now fraud calls are linked to me": (
            "aadhaar_sim_identity_misuse",
            ("Telecom subscriber/SIM", "Aadhaar identity"),
        ),
        "loan app people are calling my boss and saying I am fraud": (
            "loan_app_harassment",
            ("RBI Ombudsman/CMS", "boss or employer"),
        ),
        "credit card charged annual fee twice and support closed my complaint": (
            "wrong_bank_debit",
            ("RBI Ombudsman/CMS", "card"),
        ),
        "my salary account has lien after cyber complaint but bank is not giving order copy": (
            "bank_account_freeze_legal_hold",
            ("written freeze/lien reason", "BNSS Section 106 says a police officer may seize property"),
        ),
    }

    for query, (workflow_id, expected_terms) in cases.items():
        route = route_matter(query)
        result = common_workflow_contract_result(query, route, sources)
        assert result is not None, query
        assert result.id == workflow_id, query
        assert result.answer_mode == "primary", query
        rendered = " ".join(result.lines)
        for term in expected_terms:
            assert term in rendered, query


def test_fresh_ui_real_50_stage_contracts_cover_answer_and_latency_clusters():
    cases = {
        "got married 22 he is 29 family says illegal what is age legal in india": (
            [
                {"index": 1, "title": "Prohibition of Child Marriage Act 2006", "anchor": "child-marriage-2006/sec-2"},
                {"index": 2, "title": "Special Marriage Act 1954", "anchor": "special-marriage-1954/sec-4"},
            ],
            "marriage_legal_age",
            ("22-year-old and a 29-year-old are not under-age", "family threat"),
        ),
        "sir factory owner not paid wages 3 months 25 workers we dont have written contract where to go": (
            [
                {"index": 1, "title": "Code on Wages 2019", "anchor": "code-on-wages-2019/sec-45"},
                {"index": 2, "title": "Industrial Disputes Act 1947", "anchor": "industrial-disputes-1947/sec-10"},
            ],
            "unpaid_group_wages_no_contract",
            ("25 workers", "no written contract", "Labour Commissioner/wage authority"),
        ),
        "i am confused company is asking me to serve 90 day notice but offer letter says 60 days, which one applies pls guide": (
            [
                {"index": 1, "title": "Indian Contract Act 1872", "anchor": "indian-contract-1872/sec-37"},
                {"index": 2, "title": "Code on Wages 2019", "anchor": "code-on-wages-2019/sec-18"},
            ],
            "employment_notice_period_contract",
            ("90-day demand", "60 days", "exact 90-day clause"),
        ),
        "need help, son in tihar can he get books from family during mulaqat prison rules what next": (
            [
                {"index": 1, "title": "Delhi Prison Rules 2018", "anchor": "delhi-prison-rules-2018/rule-619-1029-books"},
                {"index": 2, "title": "Prisons Act 1894", "anchor": "prisons-1894/sec-59"},
                {"index": 3, "title": "Constitution of India", "anchor": "constitution-india/sec-21"},
            ],
            "prison_mulaqat_books",
            ("books from family during mulaqat", "Delhi Prison Rules", "book titles/list"),
        ),
        "hi, esi inspector sent notice contribution short by 1.2 lakh for casual workers can i contest can i file case": (
            [
                {"index": 1, "title": "Employees' State Insurance Act 1948", "anchor": "esi-1948/sec-40"},
                {"index": 2, "title": "Code on Social Security 2020", "anchor": "social-security-code-2020/sec-31"},
            ],
            "esi_contribution_notice",
            ("ESI contribution/determination dispute", "Casual-worker status", "ESI Court"),
        ),
        "urgent time limit n Form 35 for filing appeal to CIT Appeals income tax how to complain": (
            [
                {"index": 1, "title": "Income-tax Act 1961", "anchor": "income-tax-1961/sec-249-a"},
            ],
            "income_tax_appeal_deadline",
            ("Form 35", "CIT(Appeals)", "delay-condonation"),
        ),
        "urgent how to file appeal before ITAT against CIT Appeals order time limit how to complain": (
            [
                {"index": 1, "title": "Income-tax Act 1961", "anchor": "income-tax-1961/sec-253-d"},
            ],
            "income_tax_appeal_deadline",
            ("ITAT appeal", "appellate-tribunal", "communication date"),
        ),
        "freelance designer 18 lakh income should i register gst or no": (
            [
                {"index": 1, "title": "Central Goods and Services Tax Act 2017", "anchor": "cgst-2017/sec-22"},
                {"index": 2, "title": "Income-tax Act 1961", "anchor": "income-tax-1961/sec-139-i"},
            ],
            "gst_freelancer_registration_threshold",
            ("18 lakh", "CGST registration-threshold", "Income-tax filing and GST registration are separate"),
        ),
    }

    for query, (passages, workflow_id, expected_terms) in cases.items():
        result = common_workflow_contract_result(query, route_matter(query), passages)
        assert result is not None, query
        assert result.id == workflow_id, query
        assert result.answer_mode == "primary", query
        rendered = " ".join(result.lines)
        for term in expected_terms:
            assert term in rendered, query


def test_domestic_violence_divorce_prompt_keeps_safety_and_family_court_tracks():
    query = "sir I want divorce from my husband he is alcoholic and beats me mutual consent possible where to go"
    passages = [
        {"index": 1, "title": "Family Courts Act 1984", "anchor": "family-courts-1984/sec-7"},
        {"index": 2, "title": "Protection of Women from Domestic Violence Act 2005", "anchor": "domestic-violence-2005/sec-3"},
        {"index": 3, "title": "Bharatiya Nyaya Sanhita 2023", "anchor": "bns-2023/sec-117"},
        {"index": 4, "title": "Bharatiya Nagarik Suraksha Sanhita 2023", "anchor": "bnss-2023/sec-173"},
        {"index": 6, "title": "Hindu Marriage Act 1955", "anchor": "hindu-marriage-1955/sec-13B"},
    ]

    result = common_workflow_contract_result(query, route_matter(query), passages)
    assert result is not None
    assert result.id == "domestic_violence_immediate_safety"
    assert result.answer_mode == "safety_primary"
    rendered = " ".join(result.lines)
    assert "immediate safety first" in rendered
    assert "Section 13B" in rendered
    assert "mutual-consent route only when both spouses freely agree" in rendered
    assert "Family Court/DLSA" in rendered
    assert "[6]" in rendered


def test_plain_domestic_violence_where_to_go_does_not_add_divorce_track():
    query = "my husband beats me where to go"
    passages = [
        {"index": 1, "title": "Family Courts Act 1984", "anchor": "family-courts-1984/sec-7"},
        {"index": 2, "title": "Protection of Women from Domestic Violence Act 2005", "anchor": "domestic-violence-2005/sec-3"},
        {"index": 3, "title": "Bharatiya Nyaya Sanhita 2023", "anchor": "bns-2023/sec-117"},
        {"index": 4, "title": "Bharatiya Nagarik Suraksha Sanhita 2023", "anchor": "bnss-2023/sec-173"},
        {"index": 6, "title": "Hindu Marriage Act 1955", "anchor": "hindu-marriage-1955/sec-13B"},
    ]

    result = common_workflow_contract_result(query, route_matter(query), passages)
    assert result is not None
    assert result.id == "domestic_violence_immediate_safety"
    rendered = " ".join(result.lines)
    assert "immediate safety first" in rendered
    assert "Section 13B" not in rendered
    assert "mutual-consent route" not in rendered


def test_domestic_acid_threat_uses_specific_safety_frame():
    query = "please help my mother in law is threatening to throw acid on me if I dont get more money from my parents"
    passages = [
        {"index": 1, "title": "Protection of Women from Domestic Violence Act 2005", "anchor": "domestic-violence-2005/sec-18"},
        {"index": 2, "title": "Bharatiya Nyaya Sanhita 2023", "anchor": "bns-2023/sec-125"},
        {"index": 3, "title": "Bharatiya Nagarik Suraksha Sanhita 2023", "anchor": "bnss-2023/sec-173"},
    ]
    result = common_workflow_contract_result(query, route_matter(query), passages)
    assert result is not None
    assert result.id == "acid_chemical_attack_first_response"
    assert result.answer_mode == "safety_primary"
    rendered = " ".join(result.lines)
    assert "threat to throw acid" in rendered
    assert "completed acid injury" in rendered
    assert "PWDVA protection-order route" in rendered
    assert "Protection Officer" in rendered
    assert _is_safe_template_source_bridge(
        "For the police/BNS side, ask police or legal aid to verify the BNS Section 125 source only if the facts show an act so rashly or negligently as to endanger human life or personal safety; keep the exact acid-threat words, date, witnesses, and any follow-up act separate for the complaint [2].",
        route_matter(query),
    )


def test_stage4_public_service_and_consumer_prompts_have_authority_owners():
    sources = [
        {"index": 1, "title": "Reserve Bank Integrated Ombudsman Scheme 2021", "anchor": "rbi-integrated-ombudsman-2021/sec-2"},
        {"index": 2, "title": "Consumer Protection Act 2019", "anchor": "consumer-protection-2019/sec-35"},
        {"index": 3, "title": "Information Technology Act 2000", "anchor": "it-2000/sec-66C"},
        {"index": 4, "title": "Bharatiya Nyaya Sanhita 2023", "anchor": "bns-2023/sec-318"},
        {"index": 5, "title": "Bharatiya Nagarik Suraksha Sanhita 2023", "anchor": "bnss-2023/sec-173"},
        {"index": 6, "title": "Code on Wages 2019", "anchor": "code-on-wages-2019/sec-17"},
        {"index": 7, "title": "Industrial Disputes Act 1947", "anchor": "industrial-disputes-1947/sec-25F"},
        {"index": 8, "title": "National Food Security Act 2013", "anchor": "national-food-security-2013/sec-14"},
        {"index": 9, "title": "Aadhaar Act 2016", "anchor": "aadhaar-2016/sec-7"},
        {"index": 10, "title": "Right to Information Act 2005", "anchor": "rti-2005/sec-6"},
        {"index": 11, "title": "Right of Children to Free and Compulsory Education Act 2009", "anchor": "rte-2009/sec-5"},
        {"index": 12, "title": "Real Estate (Regulation and Development) Act 2016", "anchor": "rera-2016/sec-31"},
        {"index": 13, "title": "All India Council for Technical Education Approval Process Handbook 2022-23", "anchor": "aicte-approval-process-handbook-2023/refund-original-documents-8.13"},
        {"index": 14, "title": "Indian Contract Act 1872", "anchor": "indian-contract-1872/sec-37"},
        {"index": 15, "title": "Micro, Small and Medium Enterprises Development Act 2006", "anchor": "msmed-2006/sec-18"},
    ]
    sources.extend(
        {**source, "index": 20 + offset}
        for offset, source in enumerate(RBI_OMBUDSMAN_SOURCES)
    )
    cases = {
        "fake customer support made me install AnyDesk and money got transferred from my bank account": (
            "cyber_money_fraud",
            ("1930", "bank/RBI refund track", "cyber fraud/electronic cheating"),
            (),
        ),
        "IMPS transfer failed beneficiary did not get money but bank deducted amount": (
            "wrong_bank_debit",
            ("RBI Ombudsman/CMS", "transaction ID/RRN"),
            ("1930", "cybercrime.gov.in"),
        ),
        "ATM cash not dispensed but account debited and branch not helping": (
            "wrong_bank_debit",
            ("ATM", "CCTV/request timeline", "RBI Ombudsman/CMS"),
            ("1930", "cybercrime.gov.in"),
        ),
        "ATM showed transaction failed but 10000 debited, branch says wait": (
            "wrong_bank_debit",
            ("ATM transaction-failed debit", "RBI Ombudsman/CMS"),
            ("1930", "cybercrime.gov.in"),
        ),
        "IMPS status failed but money cut and beneficiary says not received": (
            "wrong_bank_debit",
            ("failed IMPS transfer", "transaction ID/RRN", "RBI Ombudsman/CMS"),
            ("1930", "cybercrime.gov.in"),
        ),
        "credit card annual fee charged though card was closed": (
            "wrong_bank_debit",
            ("credit-card fee", "RBI Ombudsman/CMS"),
            ("1930", "cybercrime.gov.in"),
        ),
        "bank says KYC pending so account is on hold": (
            "bank_account_freeze",
            ("KYC reason", "RBI Ombudsman/CMS"),
            ("1930", "cybercrime.gov.in"),
        ),
        "personal loan EMI bounce charges look too high": (
            "loan_emi_penalty_fee_dispute",
            ("EMI bounce charge", "penalty breakup", "RBI Ombudsman/CMS"),
            ("cybercrime.gov.in", "1930"),
        ),
        "bank chargeback for failed online order not processed": (
            "wrong_bank_debit",
            ("chargeback", "failed-order debit", "RBI Ombudsman/CMS", "written complaint"),
            ("1930", "cybercrime.gov.in"),
        ),
        "company kept my original degree certificate after I resigned and HR not replying": (
            "employment_original_document_return",
            ("original degree/certificate", "written employment grievance", "Labour Commissioner"),
            ("I won't guess", "Factories Act"),
        ),
        "client is late by 3 days on invoice, should I send police complaint?": (
            "ordinary_invoice_payment_reminder",
            ("written payment reminder", "do not start with a police complaint", "civil/commercial recovery"),
            (),
        ),
        "company laid off me and FNF salary pending after last working day": (
            "unpaid_salary_after_termination",
            ("full-and-final", "Labour Commissioner/wage authority", "termination/retrenchment"),
            (),
        ),
        "ration shop machine says thumb not matching and dealer denied wheat": (
            "ration_biometric_auth_failure",
            ("alternate authentication", "DGRO", "ration-card ID"),
            (),
        ),
        "damaged phone delivered and company is not accepting return pickup": (
            "consumer_defective_goods",
            ("National Consumer Helpline", "pickup or return attempts", "District Consumer Commission"),
            (),
        ),
        "got fake Nike shoes from online seller": (
            "consumer_defective_goods",
            ("Consumer Protection Act", "counterfeit-shoe evidence", "District Consumer Commission"),
            (),
        ),
        "service centre refused warranty repair for my laptop": (
            "consumer_defective_goods",
            ("warranty", "service-centre", "District Consumer Commission"),
            (),
        ),
        "coaching centre promised refund but stopped replying": (
            "coaching_refund_service_deficiency",
            ("coaching centre", "written refund demand", "District Consumer Commission"),
            (),
        ),
        "my daughter cleared admission exam but school is not admitting her": (
            "school_admission_tc_refusal",
            ("written refusal", "district education officer", "admission result/application"),
            (),
        ),
        "builder took full payment but not giving OC for my flat": (
            "builder_rera",
            ("RERA as the first", "State RERA Authority", "OC/completion-certificate status"),
            (),
        ),
        "builder gave possession but bathroom tiles are broken and leakage started": (
            "builder_rera",
            ("completed-flat defect/repair dispute after possession", "direct service-deficiency/repair/compensation", "do not frame a completed-flat repair problem as a possession-delay/refund case"),
            (),
        ),
        "college is holding my original certificates after I left the course": (
            "college_original_certificate_release",
            ("AICTE/approved-institution certificate-return", "written reason", "original certificates/marksheets list"),
            (),
        ),
        "college is not returning my original marksheets after I discontinued": (
            "college_original_certificate_release",
            ("AICTE/approved-institution certificate-return", "principal/registrar", "original certificates/marksheets list"),
            ("Right of Children", "RTE"),
        ),
    }

    for query, (workflow_id, expected_terms, forbidden_terms) in cases.items():
        result = common_workflow_contract_result(query, route_matter(query), sources)
        assert result is not None, query
        assert result.source in {"authority_graph", "common_workflow_contracts"}, query
        assert result.id == workflow_id, query
        assert result.answer_mode == "primary", query
        rendered = " ".join(result.lines)
        for term in expected_terms:
            assert term in rendered, query
        for term in forbidden_terms:
            assert term not in rendered, query


def test_stage1_source_gap_contracts_are_honest_when_local_act_missing():
    bhang_q = "bhang lassi at holi police saying ndps mahabaleshwar what to do"
    bhang_passages = [
        {"index": 1, "title": "Narcotic Drugs and Psychotropic Substances Act 1985", "anchor": "ndps-1985/sec-2"},
        {"index": 2, "title": "Narcotic Drugs and Psychotropic Substances Act 1985", "anchor": "ndps-1985/sec-37"},
    ]
    bhang = _grounded_joined(bhang_q, bhang_passages)
    assert _workflow_id(bhang_q, bhang_passages) == "ndps_bhang_lassi"
    assert "do not have the exact Maharashtra State Excise Act" in bhang
    assert "controlling State Excise source" in bhang

    goa_bhang_q = "bhang lassi holi goa police caught is it ndps"
    goa_bhang = _grounded_joined(goa_bhang_q, [
        {"index": 1, "title": "Narcotic Drugs and Psychotropic Substances Act 1985", "anchor": "ndps-1985/sec-2-a"},
    ])
    assert "local state-excise or bhang-rule source" in goa_bhang
    assert "Maharashtra State Excise Act" not in goa_bhang
    assert "Mahabaleshwar" not in goa_bhang

    witch_q = "neighbours calling me witch want to throw me out of village chaibasa what law"
    witch_passages = [
        {"index": 1, "title": "Bharatiya Nyaya Sanhita 2023", "anchor": "bns-2023/sec-76"},
        {"index": 2, "title": "Bharatiya Nagarik Suraksha Sanhita 2023", "anchor": "bnss-2023/sec-173"},
    ]
    witch = _joined(witch_q, witch_passages)
    assert "Jharkhand witch-practices State Act" in witch
    assert "retrieved index" in witch
    assert "controlling State Act" in witch

    witch_with_state = _joined(
        witch_q,
        [
            {"index": 1, "title": "Bharatiya Nyaya Sanhita 2023", "anchor": "bns-2023/sec-76"},
            {"index": 2, "title": "Bharatiya Nagarik Suraksha Sanhita 2023", "anchor": "bnss-2023/sec-173"},
            {
                "index": 3,
                "title": "Jharkhand Prevention of Witch (Daain) Practices Act 2001",
                "anchor": "jharkhand-prevention-witch-daain-practices-2001/sec-3",
                "source_type": "official_summary",
            },
        ],
    )
    assert "official court-reference marker" in witch_with_state
    assert "not the exact State Act text" in witch_with_state
    assert "retrieved index" not in witch_with_state
    assert "[3]" in witch_with_state

    witch_with_jhalsa = _joined(
        witch_q,
        [
            {"index": 1, "title": "Bharatiya Nyaya Sanhita 2023", "anchor": "bns-2023/sec-76"},
            {"index": 2, "title": "Bharatiya Nagarik Suraksha Sanhita 2023", "anchor": "bnss-2023/sec-173"},
            {
                "index": 3,
                "title": "Jharkhand Prevention of Witch (Daain) Practices Act 2001",
                "anchor": "jharkhand-prevention-witch-daain-practices-2001/sec-3",
                "source_type": "official_summary",
            },
            {
                "index": 4,
                "title": "Jharkhand State Legal Services Authority Dayan Pratha Pratishedh Adhiniyam 2001",
                "anchor": "jhalsa-dayan-pratha-pratishedh-2001/sec-4",
                "source_type": "official_guidance",
            },
        ],
    )
    assert "official court-reference marker" not in witch_with_jhalsa
    assert "JHALSA official-guidance source" in witch_with_jhalsa
    assert "Jharkhand Dayan Pratha Pratishedh Adhiniyam 2001" in witch_with_jhalsa
    assert "state witch-practices lane" in witch_with_jhalsa
    assert "[4]" in witch_with_jhalsa

    income_tax_no_143 = _joined(
        "got income tax notice under section 143(2) how much time to respond",
        [
            {"index": 1, "title": "Income-tax Act 1961", "anchor": "income-tax-1961/sec-142"},
            {"index": 2, "title": "Income-tax Act 1961", "anchor": "income-tax-1961/sec-144"},
        ],
    )
    assert "section 143(2) notice" not in income_tax_no_143

    cattle_q = "sir they arrested me for cow transport saying I am smuggling but I was taking my own buffalo to mandi"
    cattle_passages = [
        {"index": 1, "title": "Bharatiya Nagarik Suraksha Sanhita 2023", "anchor": "bnss-2023/sec-483"},
        {"index": 2, "title": "MULTANI HANIFBHAI KALUBHAI versus STATE OF GUJARAT & ANR.", "anchor": "2013-insc-69#header", "source_type": "sc_judgment"},
        {"index": 3, "title": "Prevention of Cruelty to Animals Act 1960", "anchor": "prevention-cruelty-animals-1960/sec-11"},
        {"index": 4, "title": "Transport of Animals Rules 1978", "anchor": "transport-of-animals-rules-1978/rules-46-56", "source_type": "rule"},
    ]
    cattle = _grounded_joined(cattle_q, cattle_passages)
    assert route_matter(cattle_q).label == "State cattle / animal-transport accused procedure"
    assert "Use the Prevention of Cruelty to Animals / Transport of Animals sources" in cattle
    assert "veterinary certificate" in cattle
    assert "do not have the exact state Cattle Preservation/Animal Preservation Act source" in cattle
    assert "do not treat a judgment or generic bail/procedure text as the controlling State Act" in cattle
    assert "does not replace the FIR's exact state Act and section text" in cattle


def test_income_tax_1432_notice_uses_exact_assessment_source():
    query = "i got income tax notice under section 143(2) for AY 2023-24 how much time do i have to respond"
    passages = [
        {"index": 1, "title": "Income-tax Act 1961", "anchor": "income-tax-1961/sec-143"},
        {"index": 2, "title": "Income-tax Act 1961", "anchor": "income-tax-1961/sec-142"},
        {"index": 3, "title": "Income-tax Act 1961", "anchor": "income-tax-1961/sec-144"},
    ]
    answer = _joined(
        query,
        passages,
    )
    diagnostics = common_workflow_contract_diagnostics(query, route_matter(query), passages)

    assert diagnostics["id"] == "income_tax_1432_notice"
    assert "section 143(2) notice" in answer
    assert "respond by the date/time stated in the notice" in answer
    assert "generic appeal or reassessment route" in answer
    assert "AIS/Form 26AS" in answer
    assert "[1]" in answer


def test_patch16_criminal_procedure_failures_get_source_gated_answer_owners():
    cases = {
        "my brother got arrested yesterday how do I apply for regular bail": (
            [
                {"index": 1, "title": "Bharatiya Nagarik Suraksha Sanhita 2023", "anchor": "bnss-2023/sec-483@2024-07-01"},
                {"index": 2, "title": "Bharatiya Nagarik Suraksha Sanhita 2023", "anchor": "bnss-2023/sec-480-a@2024-07-01"},
            ],
            "regular_bail_after_arrest",
            "primary",
            ("already arrested", "regular bail", "remand/trial court"),
            ("theft section", "first-time accused"),
        ),
        "father bail filed magistrate court ipc 376 rape case why direct to sessions court": (
            [
                {"index": 1, "title": "Bharatiya Nagarik Suraksha Sanhita 2023", "anchor": "bnss-2023/sec-483@2024-07-01"},
                {"index": 2, "title": "Bharatiya Nyaya Sanhita 2023", "anchor": "bns-2023/sec-64-b@2024-07-01"},
            ],
            "sexual_offence_sessions_bail_forum",
            "primary",
            ("IPC 376/rape", "Sessions/High Court bail forum", "Magistrate refusal/order"),
            ("theft section", "first-time accused"),
        ),
        "husband arrested 498a anticipatory bail filed sessions court rejected what next high court": (
            [
                {"index": 1, "title": "Bharatiya Nagarik Suraksha Sanhita 2023", "anchor": "bnss-2023/sec-482@2024-07-01"},
                {"index": 2, "title": "Code of Criminal Procedure 1973", "anchor": "crpc-1973/sec-438"},
                {"index": 3, "title": "Bharatiya Nagarik Suraksha Sanhita 2023", "anchor": "bnss-2023/sec-480-a@2024-07-01"},
                {"index": 4, "title": "Bharatiya Nyaya Sanhita 2023", "anchor": "bns-2023/sec-85@2024-07-01"},
            ],
            "anticipatory_bail_rejected_next_step",
            "primary",
            ("Sessions Court", "High Court", "rejection order"),
            (),
        ),
        "how much surety amount typically required for bail in cheque bounce case": (
            [
                {"index": 1, "title": "Bharatiya Nagarik Suraksha Sanhita 2023", "anchor": "bnss-2023/sec-483@2024-07-01"},
                {"index": 2, "title": "Negotiable Instruments Act 1881", "anchor": "negotiable-instruments-1881/sec-138"},
            ],
            "bail_surety_amount_context",
            "primary",
            ("no single standard surety amount", "cheque-bounce/NI Act", "same court"),
            ("already granted but",),
        ),
        "father bail in 498A magistrate granted but conditions too strict 50000 surety can challenge": (
            [
                {"index": 1, "title": "Bharatiya Nagarik Suraksha Sanhita 2023", "anchor": "bnss-2023/sec-483@2024-07-01"},
                {"index": 2, "title": "Constitution of India", "anchor": "constitution-india/sec-21"},
            ],
            "bail_surety_condition_modification",
            "primary",
            ("bail-condition modification", "same bail court", "reduced surety"),
            (),
        ),
        "brother in jail 18 months UAPA bail when prima facie case made out kya hota": (
            [
                {"index": 1, "title": "Unlawful Activities (Prevention) Act 1967", "anchor": "uapa-1967/sec-43d"},
                {"index": 2, "title": "Constitution of India", "anchor": "constitution-india/sec-21"},
                {"index": 3, "title": "Bharatiya Nagarik Suraksha Sanhita 2023", "anchor": "bnss-2023/sec-483@2024-07-01"},
            ],
            "uapa_prima_facie_bail",
            "safety_primary",
            ("prima facie case", "UAPA prima-facie", "prolonged-custody"),
            (),
        ),
        "is talking on phone with paying clients also illegal under pita I just take bookings I do not meet anyone": (
            [
                {"index": 1, "title": "Immoral Traffic (Prevention) Act 1956", "anchor": "itpa-1956/sec-5"},
                {"index": 2, "title": "Bharatiya Nagarik Suraksha Sanhita 2023", "anchor": "bnss-2023/sec-216@2024-07-01"},
            ],
            "itpa_booking_only_accused",
            "primary",
            ("phone calls or bookings", "booking-only facts", "FIR/notice"),
            (),
        ),
        "brother in handcuffs taken to court hearing is this legal high security prisoner": (
            [
                {"index": 1, "title": "Constitution of India", "anchor": "constitution-india/sec-21"},
                {"index": 2, "title": "Bharatiya Nagarik Suraksha Sanhita 2023", "anchor": "bnss-2023/sec-57@2024-07-01"},
            ],
            "handcuff_restraint_objection",
            "safety_primary",
            ("Handcuffing during court production", "security-risk claim", "future production"),
            (),
        ),
        "paralegal asking 65 yr old undertrial diabetic eligible review committee BNSS 479": (
            [
                {"index": 1, "title": "Constitution of India", "anchor": "constitution-india/sec-21"},
                {"index": 2, "title": "Code of Criminal Procedure 1973", "anchor": "crpc-1973/sec-436-a"},
                {"index": 3, "title": "Legal Services Authorities Act 1987", "anchor": "legal-services-authorities-1987/sec-9"},
                {"index": 4, "title": "Bharatiya Nagarik Suraksha Sanhita 2023", "anchor": "bnss-2023/sec-479@2024-07-01"},
            ],
            "undertrial_bnss479_review",
            "safety_primary",
            ("65-year-old diabetic undertrial", "BNSS Section 479", "one-page custody chart"),
            (),
        ),
        "father custodial death lockup byculla police saying suicide what is 196 procedure": (
            [
                {"index": 1, "title": "Constitution of India", "anchor": "constitution-india/sec-21"},
                {"index": 2, "title": "Protection of Human Rights Act 1993", "anchor": "protection-human-rights-1993/sec-12@1990-01-01"},
                {"index": 3, "title": "Code of Criminal Procedure 1973", "anchor": "crpc-1973/sec-176"},
            ],
            "custodial_death_inquiry",
            "safety_primary",
            ("custody-death/inquest", "post-mortem", "NHRC/SHRC"),
            (),
        ),
    }

    for query, (passages, workflow_id, answer_mode, expected_terms, forbidden_terms) in cases.items():
        result = common_workflow_contract_result(query, route_matter(query), passages)
        assert result is not None, query
        assert result.source == "authority_graph", query
        assert result.id == workflow_id, query
        assert result.answer_mode == answer_mode, query
        rendered = " ".join(result.lines)
        for term in expected_terms:
            assert term in rendered, query
        for term in forbidden_terms:
            assert term not in rendered, query


def test_patch16_criminal_procedure_contracts_do_not_overclaim_without_exact_sources():
    uapa_header_only = [
        {"index": 1, "title": "Unlawful Activities (Prevention) Act 1967", "anchor": "uapa-1967#header"},
        {"index": 2, "title": "Constitution of India", "anchor": "constitution-india/sec-21"},
        {"index": 3, "title": "Bharatiya Nagarik Suraksha Sanhita 2023", "anchor": "bnss-2023/sec-483@2024-07-01"},
    ]
    uapa_query = "brother in jail 18 months UAPA bail when prima facie case made out kya hota"
    assert authority_graph_workflow_event(uapa_query, route_matter(uapa_query), uapa_header_only) is None

    rape_offence_only = [
        {"index": 1, "title": "Bharatiya Nyaya Sanhita 2023", "anchor": "bns-2023/sec-64-b@2024-07-01"},
    ]
    rape_query = "father bail filed magistrate court ipc 376 rape case why direct to sessions court"
    assert authority_graph_workflow_event(rape_query, route_matter(rape_query), rape_offence_only) is None

    ordinary_prima_facie_bail = [
        {"index": 1, "title": "Bharatiya Nagarik Suraksha Sanhita 2023", "anchor": "bnss-2023/sec-483@2024-07-01"},
    ]
    ordinary_query = "my brother got arrested yesterday prima facie case weak how do I apply for regular bail"
    event = authority_graph_workflow_event(ordinary_query, route_matter(ordinary_query), ordinary_prima_facie_bail)
    assert event is not None
    assert event["id"] == "regular_bail_after_arrest"


def test_patch17_common_failure_cluster_gets_specific_source_gated_contracts():
    fake_trading_query = "i was duped of 3.5 lakh in fake stock trading app, transferred to multiple UPI ids, cyber cell complaint filed but no progress"
    fake_trading = common_workflow_contract_result(
        fake_trading_query,
        route_matter(fake_trading_query),
        [
            {"index": 1, "title": "Information Technology Act 2000", "anchor": "it-2000/sec-66D"},
            {"index": 2, "title": "Bharatiya Nyaya Sanhita 2023", "anchor": "bns-2023/sec-318-a@2024-07-01"},
            {"index": 3, "title": "Bharatiya Nagarik Suraksha Sanhita 2023", "anchor": "bnss-2023/sec-173-b@2024-07-01"},
        ],
    )
    assert fake_trading is not None
    assert fake_trading.id == "cyber_money_fraud"
    fake_trading_text = " ".join(fake_trading.lines)
    assert "fake stock/investment trading-app transfer" in fake_trading_text
    assert "cyber complaint acknowledgement" in fake_trading_text

    whatsapp_query = "my whatsapp account got hacked and someone is asking my contacts for money in my name"
    whatsapp = common_workflow_contract_result(
        whatsapp_query,
        route_matter(whatsapp_query),
        [
            {"index": 1, "title": "Information Technology Act 2000", "anchor": "it-2000/sec-66C"},
            {"index": 2, "title": "Bharatiya Nagarik Suraksha Sanhita 2023", "anchor": "bnss-2023/sec-173-b@2024-07-01"},
        ],
    )
    assert whatsapp is not None
    assert whatsapp.id == "cyber_money_fraud"
    whatsapp_text = " ".join(whatsapp.lines)
    assert "WhatsApp/account-takeover impersonation asking contacts for money" in whatsapp_text
    assert "Tinder" not in whatsapp_text
    assert "Bandra" not in whatsapp_text

    instagram_query = "someone made fake instagram account using my photos and dms girls"
    instagram = common_workflow_contract_result(
        instagram_query,
        route_matter(instagram_query),
        [
            {"index": 1, "title": "Bharatiya Nyaya Sanhita 2023", "anchor": "bns-2023/sec-319@2024-07-01"},
            {"index": 2, "title": "Information Technology Act 2000", "anchor": "it-2000/sec-66D"},
            {"index": 3, "title": "Bharatiya Nagarik Suraksha Sanhita 2023", "anchor": "bnss-2023/sec-173-b@2024-07-01"},
        ],
    )
    assert instagram is not None
    assert instagram.id == "cyber_stalking_online_harassment"
    instagram_text = " ".join(instagram.lines)
    assert "BNS stalking/intimidation" in instagram_text
    assert "IT Act privacy/electronic-record source" in instagram_text

    aadhaar_sim_query = "got message saying my aadhaar issued 4 sims i never took how to check"
    aadhaar_sim = common_workflow_contract_result(
        aadhaar_sim_query,
        route_matter(aadhaar_sim_query),
        [
            {"index": 1, "title": "Telecommunications Act 2023", "anchor": "telecommunications-2023/sec-42-b"},
            {"index": 2, "title": "Information Technology Act 2000", "anchor": "it-2000/sec-66C"},
            {"index": 3, "title": "Aadhaar (Targeted Delivery of Financial and Other Subsidies, Benefits and Services) Act 2016", "anchor": "aadhaar-2016/sec-29"},
            {"index": 4, "title": "Bharatiya Nagarik Suraksha Sanhita 2023", "anchor": "bnss-2023/sec-173"},
        ],
    )
    assert aadhaar_sim is not None
    assert aadhaar_sim.id == "aadhaar_sim_identity_misuse"
    aadhaar_sim_text = " ".join(aadhaar_sim.lines)
    assert "subscriber/KYC record" in aadhaar_sim_text
    assert "complaint/FIR number" in aadhaar_sim_text

    senior_query = "my mother 81 not allowed in her own kitchen by daughter in law mumbai legal remedy"
    senior = common_workflow_contract_result(
        senior_query,
        route_matter(senior_query),
        [
            {"index": 1, "title": "Maintenance and Welfare of Parents and Senior Citizens Act 2007", "anchor": "mwp-2007/sec-4"},
            {"index": 2, "title": "Maintenance and Welfare of Parents and Senior Citizens Act 2007", "anchor": "mwp-2007/sec-23"},
            {"index": 3, "title": "Protection of Women from Domestic Violence Act 2005", "anchor": "domestic-violence-2005/sec-19"},
        ],
    )
    assert senior is not None
    assert senior.id == "senior_parent_pension_neglect"
    senior_text = " ".join(senior.lines)
    assert "Section 23" in senior_text
    assert "kitchen" in senior_text

    forged_loan_query = "son took loan against my house i didn't sign told bank to stop ahmedabad"
    forged_loan = common_workflow_contract_result(
        forged_loan_query,
        route_matter(forged_loan_query),
        [
            {"index": 1, "title": "Credit Information Companies (Regulation) Act 2005", "anchor": "credit-information-companies-2005/sec-20"},
            {"index": 2, "title": "Reserve Bank Integrated Ombudsman Scheme 2021", "anchor": "rbi-integrated-ombudsman-2021/sec-2"},
            {"index": 3, "title": "Information Technology Act 2000", "anchor": "it-2000/sec-66C"},
            {"index": 4, "title": "Bharatiya Nyaya Sanhita 2023", "anchor": "bns-2023/sec-336"},
            {"index": 5, "title": "Bharatiya Nagarik Suraksha Sanhita 2023", "anchor": "bnss-2023/sec-173"},
            {"index": 6, "title": "Banking Regulation Act 1949", "anchor": "banking-regulation-1949/sec-21"},
        ],
    )
    assert forged_loan is not None
    assert forged_loan.id == "credit_identity_misuse"
    forged_text = " ".join(forged_loan.lines)
    assert "forged signature" in forged_text
    assert "police/cyber complaint track" in forged_text
    assert "Banking Regulation/bank-record source" in forged_text

    hospital_query = "hospital in jaipur kept father in icu 12 days without consent bill 18 lakh complaint"
    hospital = common_workflow_contract_result(
        hospital_query,
        route_matter(hospital_query),
        [
            {"index": 1, "title": "Consumer Protection Act 2019", "anchor": "consumer-protection-2019/sec-35"},
            {"index": 2, "title": "Clinical Establishments (Registration and Regulation) Act 2010", "anchor": "clinical-establishments-2010/sec-12"},
        ],
    )
    assert hospital is not None
    assert hospital.id == "hospital_records_billing"
    hospital_text = " ".join(hospital.lines)
    assert "ICU admission/continuation, consent, and a large hospital bill" in hospital_text
    assert "consent forms" in hospital_text

    thermal_query = "thermal plant blasting cracking our houses no compensation kalahandi"
    thermal = common_workflow_contract_result(
        thermal_query,
        route_matter(thermal_query),
        [
            {"index": 1, "title": "Right to Fair Compensation and Transparency in Land Acquisition, Rehabilitation and Resettlement Act 2013", "anchor": "rfctlarr-2013/sec-41-b"},
            {"index": 2, "title": "Environment (Protection) Act 1986", "anchor": "environment-protection-1986/sec-3-b"},
            {"index": 3, "title": "National Green Tribunal Act 2010", "anchor": "ngt-2010/sec-15"},
        ],
    )
    assert thermal is not None
    assert thermal.id == "thermal_blasting_house_damage_compensation"
    thermal_text = " ".join(thermal.lines)
    assert "thermal/power-plant blasting" in thermal_text
    assert "RFCTLARR section 41" in thermal_text


def test_fresh500_common_failure_answer_contracts_are_source_gated():
    tenant_passages = [
        {"index": 1, "title": "Transfer of Property Act 1882", "anchor": "transfer-of-property-1882/sec-111"},
        {"index": 2, "title": "Transfer of Property Act 1882", "anchor": "transfer-of-property-1882/sec-105"},
        {"index": 3, "title": "Transfer of Property Act 1882", "anchor": "transfer-of-property-1882/sec-106"},
        {"index": 4, "title": "Limitation Act 1963", "anchor": "limitation-1963/sec-3"},
    ]
    tenant = _grounded_joined("My tenant is not vacating house and not paying rent", tenant_passages)
    assert "tenant is not vacating or not paying rent" in tenant
    assert "Limitation Act source" in tenant
    assert "[4]" in tenant

    credit_passages = [
        {"index": 1, "title": "Credit Information Companies (Regulation) Act 2005", "anchor": "credit-information-companies-2005/sec-20"},
        {"index": 2, "title": "Reserve Bank Integrated Ombudsman Scheme 2021", "anchor": "rbi-integrated-ombudsman-2021/sec-2"},
        {"index": 3, "title": "Information Technology Act 2000", "anchor": "it-2000/sec-66C"},
        {"index": 4, "title": "Bharatiya Nyaya Sanhita 2023", "anchor": "bns-2023/sec-336"},
    ]
    credit = common_workflow_contract_result(
        "fake loan in my pan affecting cibil what legal action",
        route_matter("fake loan in my pan affecting cibil what legal action"),
        credit_passages,
    )
    assert credit is not None
    assert credit.id == "credit_identity_misuse"
    assert credit.answer_mode == "primary"
    rendered = " ".join(credit.lines)
    assert "credit-report/false-loan correction track" in rendered
    assert "cyber identity-theft/personation track" in rendered

    custody_passages = [
        {"index": 1, "title": "Constitution of India", "anchor": "constitution-india/sec-21"},
        {"index": 2, "title": "Bharatiya Nagarik Suraksha Sanhita 2023", "anchor": "bnss-2023/sec-479"},
        {"index": 3, "title": "Code of Criminal Procedure 1973", "anchor": "crpc-1973/sec-436A"},
    ]
    custody = _grounded_joined(
        "need help, i was in jail 7 yrs acquitted now how to get compensation state legal aid what next",
        custody_passages,
    )
    assert "compensation is not automatic" in custody
    assert "Article 21 liberty source" in custody
    assert "custody-delay/unlawful-detention timeline" in custody


def test_stage2_focus_failures_get_user_shaped_primary_contracts():
    maintenance_passages = [
        {"index": 1, "title": "Family Courts Act 1984", "anchor": "family-courts-1984/sec-7"},
        {"index": 2, "title": "Bharatiya Nagarik Suraksha Sanhita 2023", "anchor": "bnss-2023/sec-144-a"},
        {"index": 3, "title": "Protection of Women from Domestic Violence Act 2005", "anchor": "domestic-violence-2005/sec-20"},
        {"index": 4, "title": "Code of Criminal Procedure 1973", "anchor": "crpc-1973/sec-125-a"},
    ]
    maintenance = common_workflow_contract_result(
        "my husband left me with two kids and not giving money",
        route_matter("my husband left me with two kids and not giving money"),
        maintenance_passages,
    )
    assert maintenance is not None
    assert maintenance.id == "spouse_child_maintenance_no_support"
    assert maintenance.answer_mode == "primary"
    rendered = " ".join(maintenance.lines)
    assert "children" in rendered
    assert "maintenance and household-support" in rendered
    assert "Magistrate or Family Court" in rendered
    assert "income" in rendered

    death_passages = [
        {"index": 1, "title": "Employees' Compensation Act 1923", "anchor": "employees-compensation-1923/sec-3"},
        {"index": 2, "title": "Building and Other Construction Workers (Regulation of Employment and Conditions of Service) Act 1996", "anchor": "bocw-1996/sec-12"},
        {"index": 3, "title": "Factories Act 1948", "anchor": "factories-1948/sec-88"},
    ]
    death = common_workflow_contract_result(
        "worker died at site and owner not giving compensation",
        route_matter("worker died at site and owner not giving compensation"),
        death_passages,
    )
    assert death is not None
    assert death.id == "workplace_death_dependant_compensation"
    assert death.answer_mode == "primary"
    rendered = " ".join(death.lines)
    assert "worker who died" in rendered
    assert "dependant compensation" in rendered
    assert "supporting construction-worker/worksite record" in rendered
    assert "lost a hand/limb" not in rendered

    parent_context = common_workflow_contract_result(
        "my father left my mother with child no money and threatens her",
        route_matter("my father left my mother with child no money and threatens her"),
        maintenance_passages,
    )
    assert parent_context is None or parent_context.id != "spouse_child_maintenance_no_support"

    assault_passages = [
        {"index": 1, "title": "Bharatiya Nyaya Sanhita 2023", "anchor": "bns-2023/sec-117@2024-07-01"},
        {"index": 2, "title": "Employees' Compensation Act 1923", "anchor": "employees-compensation-1923/sec-3-a@1961-01-01"},
        {"index": 3, "title": "Code on Wages 2019", "anchor": "code-on-wages-2019/sec-17"},
        {"index": 4, "title": "Bharatiya Nagarik Suraksha Sanhita 2023", "anchor": "bnss-2023/sec-173"},
    ]
    for query in (
        "mukadam beat worker at site head injury and old wages not paid",
        "contractor beat me at construction site head injury and not paying old wages",
    ):
        assault = common_workflow_contract_result(query, route_matter(query), assault_passages)
        assert assault is not None
        assert assault.id == "worksite_assault_wage_injury"
        assert assault.answer_mode == "primary"
        rendered = " ".join(assault.lines)
        assert "police/FIR hurt" in rendered
        assert "Employees' Compensation" in rendered
        assert "Code on Wages" in rendered
        assert "lost a hand/limb" not in rendered


def test_patch14_expected_act_miss_workflows_are_source_gated_and_user_shaped():
    pds_query = "can u tell ration card cancelled because aadhaar mismatch BDO not agreeing renew bastar what can i do"
    pds = common_workflow_contract_result(
        pds_query,
        route_matter(pds_query),
        [
            {"index": 1, "title": "National Food Security Act 2013", "anchor": "national-food-security-2013/sec-14"},
            {"index": 2, "title": "Aadhaar (Targeted Delivery of Financial and Other Subsidies, Benefits and Services) Act 2016", "anchor": "aadhaar-2016/sec-7"},
            {"index": 3, "title": "Digital Personal Data Protection Act 2023", "anchor": "dpdp-2023/sec-13"},
            {"index": 4, "title": "Right to Information Act 2005", "anchor": "rti-2005/sec-6"},
        ],
    )
    assert pds is not None
    assert pds.id == "pds_aadhaar_cancellation"
    assert pds.answer_mode == "primary"
    rendered = " ".join(pds.lines)
    assert "ration-card cancellation" in rendered
    assert "Aadhaar authentication/identity route" in rendered
    assert "DPDP personal-data" in rendered
    assert "BDO" in rendered
    grounded_pds = _grounded_joined(
        pds_query,
        [
            {"index": 1, "title": "National Food Security Act 2013", "anchor": "national-food-security-2013/sec-14"},
            {"index": 2, "title": "Aadhaar (Targeted Delivery of Financial and Other Subsidies, Benefits and Services) Act 2016", "anchor": "aadhaar-2016/sec-7"},
            {"index": 3, "title": "Digital Personal Data Protection Act 2023", "anchor": "dpdp-2023/sec-13"},
            {"index": 4, "title": "Right to Information Act 2005", "anchor": "rti-2005/sec-6"},
        ],
    )
    assert "DPDP personal-data" in grounded_pds
    assert "ration-card cancellation" in grounded_pds

    posh_query = "i complained against my manager for harassment to HR and now they are putting me on PIP, is this retaliation"
    posh = common_workflow_contract_result(
        posh_query,
        route_matter(posh_query),
        [
            {"index": 1, "title": "Sexual Harassment of Women at Workplace Act 2013", "anchor": "posh-2013/sec-9"},
            {"index": 2, "title": "Industrial Disputes Act 1947", "anchor": "industrial-disputes-1947/sec-2A"},
            {"index": 3, "title": "Code on Wages 2019", "anchor": "code-on-wages-2019/sec-45"},
        ],
    )
    assert posh is not None
    assert posh.id == "posh_pip_retaliation"
    rendered = " ".join(posh.lines)
    assert "If the manager/HR harassment complaint was about sexual or gendered" in rendered
    assert "Internal Committee or Local Committee" in rendered
    assert "not automatically illegal" in rendered

    cab_query = "what to do ola driver suspended id no reason 4000 rupees earning gone how to complaint is this legal"
    cab = common_workflow_contract_result(
        cab_query,
        route_matter(cab_query),
        [
            {"index": 1, "title": "Motor Vehicle Aggregator Guidelines 2020", "anchor": "motor-vehicle-aggregator-guidelines-2020#driver-service-contract"},
            {"index": 2, "title": "Motor Vehicle Aggregator Guidelines 2020", "anchor": "motor-vehicle-aggregator-guidelines-2020#app-transparency-grievance"},
            {"index": 3, "title": "TheMotorVehiclesAct,1988", "anchor": "motor-vehicles-1988/sec-193"},
            {"index": 4, "title": "Code on Wages 2019", "anchor": "code-on-wages-2019/sec-17"},
        ],
    )
    assert cab is not None
    assert cab.id == "cab_aggregator_driver_account"
    rendered = " ".join(cab.lines)
    assert "Ola driver ID suspension" in rendered
    assert "Motor Vehicles Act aggregator source" in rendered
    assert "4000" not in rendered
    assert "pending payout ledger" in rendered

    contract_query = "what to do principal employer L&T claiming contract worker not their problem after accident pillar fell mumbai is this legal"
    contract_worker = common_workflow_contract_result(
        contract_query,
        route_matter(contract_query),
        [
            {"index": 1, "title": "Building and Other Construction Workers (Regulation of Employment and Conditions of Service) Act 1996", "anchor": "bocw-1996/sec-39"},
            {"index": 2, "title": "Contract Labour (Regulation and Abolition) Act 1970", "anchor": "contract-labour-1970/sec-21"},
            {"index": 3, "title": "TheMotorVehiclesAct,1988", "anchor": "motor-vehicles-1988/sec-165"},
            {"index": 4, "title": "Factories Act 1948", "anchor": "factories-1948/sec-111"},
            {"index": 5, "title": "Employees' Compensation Act 1923", "anchor": "employees-compensation-1923/sec-3-a"},
        ],
    )
    assert contract_worker is not None
    assert contract_worker.id == "workplace_injury_lost_limb_compensation"
    rendered = " ".join(contract_worker.lines)
    assert "principal employer" in rendered
    assert "Contract Labour Act" in rendered
    assert "BOCW" in rendered
    assert "injury-compensation" in rendered


def test_patch15_hard60_failure_contracts_include_user_scenario_terms():
    nclat = common_workflow_contract_result(
        "urgent tribunal order against me how to appeal NCLAT format and fees how to complain",
        route_matter("urgent tribunal order against me how to appeal NCLAT format and fees how to complain"),
        [
            {"index": 1, "title": "Insolvency and Bankruptcy Code 2016", "anchor": "ibc-2016/sec-61"},
            {"index": 2, "title": "Companies Act 2013", "anchor": "companies-2013/sec-421"},
        ],
    )
    assert nclat is not None
    assert nclat.id == "procedure_nclat_appeal"
    rendered = " ".join(nclat.lines)
    assert "NCLAT appeal procedure" in rendered
    assert "format and fees" in rendered
    assert "court fee" in rendered

    nclt = common_workflow_contract_result(
        "urgent procedure to file insolvency petition against cmpny in NCLT how to complain",
        route_matter("urgent procedure to file insolvency petition against cmpny in NCLT how to complain"),
        [
            {"index": 3, "title": "Insolvency and Bankruptcy Code 2016", "anchor": "ibc-2016/sec-8-b"},
            {"index": 4, "title": "Insolvency and Bankruptcy Code 2016", "anchor": "ibc-2016/sec-9"},
            {"index": 5, "title": "Companies Act 2013", "anchor": "companies-2013/sec-92"},
            {"index": 6, "title": "National Company Law Tribunal Rules 2016", "anchor": "nclt-rules-2016/rule-34", "source_type": "rule"},
        ],
    )
    assert nclt is not None
    assert nclt.id == "procedure_nclt_insolvency_petition"
    rendered = " ".join(nclt.lines)
    assert "procedure" in rendered
    assert "NCLT" in rendered
    assert "demand-notice" in rendered
    assert "NCLT Rules/Form source" in rendered

    ngt = common_workflow_contract_result(
        "urgent how to file complaint before NGT for illegal construction near wetland how to complain",
        route_matter("urgent how to file complaint before NGT for illegal construction near wetland how to complain"),
        [
            {"index": 4, "title": "National Green Tribunal Act 2010", "anchor": "ngt-2010/sec-15"},
            {"index": 5, "title": "Water (Prevention and Control of Pollution) Act 1974", "anchor": "water-pollution-1974/sec-17"},
        ],
    )
    assert ngt is not None
    assert ngt.id == "procedure_ngt_wetland_complaint"
    rendered = " ".join(ngt.lines)
    assert "NGT complaint/application procedure" in rendered
    assert "wetland" in rendered
    assert "filing format" in rendered

    vakalatnama = common_workflow_contract_result(
        "urgent how to file vakalatnama change of advocate during pending suit how to complain",
        route_matter("urgent how to file vakalatnama change of advocate during pending suit how to complain"),
        [
            {"index": 3, "title": "Code of Civil Procedure 1908", "anchor": "cpc-1908/sec-153"},
            {"index": 4, "title": "Legal Services Authorities Act 1987", "anchor": "legal-services-authorities-1987/sec-12"},
        ],
    )
    assert vakalatnama is not None
    assert vakalatnama.id == "procedure_vakalatnama_change"
    rendered = " ".join(vakalatnama.lines)
    assert "court procedure" in rendered
    assert "fresh vakalatnama" in rendered

    writ_fee = common_workflow_contract_result(
        "urgent court fee for filing writ petition in high court fixed or ad valorem how to complain",
        route_matter("urgent court fee for filing writ petition in high court fixed or ad valorem how to complain"),
        [
            {"index": 1, "title": "The Court-Fees Act, 1870", "anchor": "court-fees-1870/sec-7"},
            {"index": 2, "title": "Constitution of India", "anchor": "constitution-india/sec-226"},
        ],
    )
    assert writ_fee is not None
    assert writ_fee.id == "procedure_writ_court_fee"
    rendered = " ".join(writ_fee.lines)
    assert "fixed/ad valorem" in rendered
    assert "filing-procedure" in rendered

    auto = common_workflow_contract_result(
        "what to do auto permit chennai expired in lockdown how to renew tamil nadu i came from cuddalore is this legal",
        route_matter("what to do auto permit chennai expired in lockdown how to renew tamil nadu i came from cuddalore is this legal"),
        [
            {"index": 1, "title": "TheMotorVehiclesAct,1988", "anchor": "motor-vehicles-1988/sec-74-a"},
            {"index": 4, "title": "TheMotorVehiclesAct,1988", "anchor": "motor-vehicles-1988/sec-80-a"},
        ],
    )
    assert auto is not None
    assert auto.id == "transport_auto_permit_renewal"
    rendered = " ".join(auto.lines)
    assert "RTO/RTA" in rendered
    assert "Chennai/Tamil Nadu" in rendered
    assert "traffic-police challan" in rendered or "challan" in rendered

    gratuity = common_workflow_contract_result(
        "i am confused section 4 of payment of gratuity act eligibility 4 years 11 months service pls guide",
        route_matter("i am confused section 4 of payment of gratuity act eligibility 4 years 11 months service pls guide"),
        [
            {"index": 4, "title": "Payment of Gratuity Act 1972", "anchor": "gratuity-1972/sec-4-e"},
            {"index": 8, "title": "Payment of Gratuity Act 1972", "anchor": "gratuity-1972/sec-7"},
        ],
    )
    assert gratuity is not None
    assert gratuity.id == "gratuity_eligibility_4y11m"
    rendered = " ".join(gratuity.lines)
    assert "4 years 11 months" in rendered
    assert "employer" in rendered
    assert "Labour Commissioner" in rendered

    retrench = common_workflow_contract_result(
        "hi, want to retrench 8 workers factory has 120 employees ludhiana garments need permission can i file case",
        route_matter("hi, want to retrench 8 workers factory has 120 employees ludhiana garments need permission can i file case"),
        [
            {"index": 6, "title": "Industrial Disputes Act 1947", "anchor": "industrial-disputes-1947/sec-25F-a"},
            {"index": 7, "title": "Industrial Disputes Act 1947", "anchor": "industrial-disputes-1947/sec-25N-c"},
        ],
    )
    assert retrench is not None
    assert retrench.id == "retrenchment_permission_120_workers"
    rendered = " ".join(retrench.lines)
    assert "labour-compliance" in rendered
    assert "120 employees" in rendered
    assert "8 workers" in rendered


def test_patch15_succession_authority_contracts_cover_common_inheritance_misses():
    caretaker_q = "pls tell father has 4 children 2 daughters wants to make will giving more to caretaker daughter valid need lawyer or police"
    caretaker = common_workflow_contract_result(
        caretaker_q,
        route_matter(caretaker_q),
        [
            {"index": 2, "title": "Hindu Succession Act 1956 (with 2005 amendment)", "anchor": "hindu-succession-1956/sec-10"},
            {"index": 3, "title": "Indian Succession Act 1925", "anchor": "indian-succession-1925/sec-63"},
            {"index": 4, "title": "Registration Act 1908", "anchor": "registration-1908/sec-18"},
        ],
    )
    assert caretaker is not None
    assert caretaker.id == "caretaker_daughter_will"
    rendered = " ".join(caretaker.lines)
    assert "caretaker daughter" in rendered
    assert "civil court" in rendered
    assert "partition/title" in rendered

    registered_q = "pls tell i registered my will in sub registrar pune do i need to update it every year need lawyer or police"
    registered = common_workflow_contract_result(
        registered_q,
        route_matter(registered_q),
        [
            {"index": 3, "title": "Indian Succession Act 1925", "anchor": "indian-succession-1925/sec-62"},
            {"index": 4, "title": "Registration Act 1908", "anchor": "registration-1908/sec-18"},
        ],
    )
    assert registered is not None
    assert registered.id == "registered_will_update"
    rendered = " ".join(registered.lines)
    assert "does not need to be updated every year" in rendered
    assert "civil court" in rendered
    assert "police" in rendered

    parsi_q = "pls tell parsi mother passed away in mumbai how property divided among us three sisters need lawyer or police"
    parsi = common_workflow_contract_result(
        parsi_q,
        route_matter(parsi_q),
        [
            {"index": 1, "title": "Indian Succession Act 1925", "anchor": "indian-succession-1925/sec-50"},
            {"index": 5, "title": "Indian Succession Act 1925", "anchor": "indian-succession-1925/sec-51"},
        ],
    )
    assert parsi is not None
    assert parsi.id == "parsi_intestate_sisters"
    rendered = " ".join(parsi.lines)
    assert "Parsi mother" in rendered
    assert "three sisters" in rendered
    assert "civil court partition/title" in rendered

    daughter_q = "pls tell as a daughter am i coparcener in ancestral prop father died 2003 before amendment need lawyer or police"
    daughter = common_workflow_contract_result(
        daughter_q,
        route_matter(daughter_q),
        [
            {"index": 4, "title": "Hindu Succession Act 1956 (with 2005 amendment)", "anchor": "hindu-succession-1956/sec-6"},
            {"index": 6, "title": "Specific Relief Act 1963", "anchor": "specific-relief-1963/sec-34"},
        ],
    )
    assert daughter is not None
    assert daughter.id == "daughter_ancestral_share"
    rendered = " ".join(daughter.lines)
    assert "daughter/coparcener" in rendered
    assert "father's death/status" in rendered
    assert "partition" in rendered

    daughter_sec10_only = common_workflow_contract_result(
        daughter_q,
        route_matter(daughter_q),
        [
            {"index": 4, "title": "Hindu Succession Act 1956 (with 2005 amendment)", "anchor": "hindu-succession-1956/sec-10"},
            {"index": 6, "title": "Specific Relief Act 1963", "anchor": "specific-relief-1963/sec-34"},
        ],
    )
    assert daughter_sec10_only is None or daughter_sec10_only.id != "daughter_ancestral_share"


def test_patch15_latency_tail_property_family_transfer_contracts():
    lifetime_q = "pls tell father transferred flat to son before death now daughter wants share is gift valid need lawyer or police"
    lifetime = common_workflow_contract_result(
        lifetime_q,
        route_matter(lifetime_q),
        [
            {"index": 5, "title": "Transfer of Property Act 1882", "anchor": "transfer-of-property-1882/sec-122"},
            {"index": 7, "title": "Transfer of Property Act 1882", "anchor": "transfer-of-property-1882/sec-123"},
            {"index": 3, "title": "Registration Act 1908", "anchor": "registration-1908/sec-49"},
            {"index": 2, "title": "Hindu Succession Act 1956 (with 2005 amendment)", "anchor": "hindu-succession-1956/sec-15"},
        ],
    )
    assert lifetime is not None
    assert lifetime.id == "property_lifetime_gift_heir_share"
    rendered = " ".join(lifetime.lines)
    assert "father transferring or gifting a flat to a son before death" in rendered
    assert "daughter says the gift is invalid" in rendered
    assert "civil court title, cancellation, declaration, or partition" in rendered

    sale_q = "pls tell mother passed away last year father wants to sell flat what papers needed kolkata need lawyer or police"
    sale = common_workflow_contract_result(
        sale_q,
        route_matter(sale_q),
        [
            {"index": 2, "title": "Hindu Succession Act 1956 (with 2005 amendment)", "anchor": "hindu-succession-1956/sec-15"},
            {"index": 8, "title": "Hindu Succession Act 1956 (with 2005 amendment)", "anchor": "hindu-succession-1956/sec-10"},
            {"index": 1, "title": "Transfer of Property Act 1882", "anchor": "transfer-of-property-1882/sec-45"},
        ],
    )
    assert sale is not None
    assert sale.id == "property_sale_after_mother_death_docs"
    rendered = " ".join(sale.lines)
    assert "mother's name" in rendered
    assert "father alone can sell" in rendered
    assert "Kolkata" in rendered
    assert "police only for forgery" in rendered

    verbal_q = "pls tell mother gave land to younger son verbally now older son disputing it after 20 yrs need lawyer or police"
    verbal = common_workflow_contract_result(
        verbal_q,
        route_matter(verbal_q),
        [
            {"index": 5, "title": "Transfer of Property Act 1882", "anchor": "transfer-of-property-1882/sec-122"},
            {"index": 6, "title": "Transfer of Property Act 1882", "anchor": "transfer-of-property-1882/sec-123"},
            {"index": 3, "title": "Registration Act 1908", "anchor": "registration-1908/sec-49"},
            {"index": 2, "title": "Hindu Succession Act 1956 (with 2005 amendment)", "anchor": "hindu-succession-1956/sec-15"},
            {"index": 9, "title": "Limitation Act 1963", "anchor": "limitation-1963/sec-3"},
        ],
    )
    assert verbal is not None
    assert verbal.id == "property_verbal_land_gift_dispute"
    rendered = " ".join(verbal.lines)
    assert "verbally to a younger son" in rendered
    assert "20 years" in rendered
    assert "civil court declaration, partition, injunction" in rendered


def test_stage2_criminal_specific_contracts_preempt_generic_bail_and_article44():
    pmla_pre_arrest_q = "ed pmla raid summons husband can ask anticipatory bail before arrest"
    pmla_pre_arrest = common_workflow_contract_result(
        pmla_pre_arrest_q,
        route_matter(pmla_pre_arrest_q),
        [
            {"index": 1, "title": "Bharatiya Nagarik Suraksha Sanhita 2023", "anchor": "bnss-2023/sec-482@2024-07-01"},
            {"index": 2, "title": "Code of Criminal Procedure 1973", "anchor": "crpc-1973/sec-438"},
            {"index": 3, "title": "Prevention of Money Laundering Act 2002", "anchor": "pmla-2002/sec-45"},
            {"index": 4, "title": "Constitution of India", "anchor": "constitution-india/sec-21"},
            {"index": 5, "title": "Bharatiya Nagarik Suraksha Sanhita 2023", "anchor": "bnss-2023/sec-480-a@2024-07-01"},
        ],
    )
    assert pmla_pre_arrest is not None
    assert pmla_pre_arrest.id == "pmla_anticipatory_interim_bail"
    rendered = " ".join(pmla_pre_arrest.lines)
    assert "PMLA Section 45" in rendered
    assert "PMLA-specific pre-arrest protection" in rendered
    assert "ordinary regular bail alone" in rendered
    assert "not anticipatory bail" not in rendered
    pmla_line = next(line for line in pmla_pre_arrest.lines if "PMLA Section 45" in line)
    promoted_pmla = _promote_reviewed_workflow_contract_line(
        SentenceVerification(
            text=pmla_line,
            status=SentenceStatus.WEAK_SUPPORT,
            citations=[3],
            reason="simulated NLI drift",
        ),
        pmla_pre_arrest,
        pmla_pre_arrest.lines,
    )
    assert promoted_pmla.status == SentenceStatus.OK

    pmla_interim_q = "wife arrested pmla bank fraud is interim bail possible for new born baby"
    pmla_interim = common_workflow_contract_result(
        pmla_interim_q,
        route_matter(pmla_interim_q),
        [
            {"index": 1, "title": "Prevention of Money Laundering Act 2002", "anchor": "pmla-2002/sec-45"},
            {"index": 3, "title": "Code of Criminal Procedure 1973", "anchor": "crpc-1973/sec-437-a"},
            {"index": 5, "title": "Bharatiya Nagarik Suraksha Sanhita 2023", "anchor": "bnss-2023/sec-483@2024-07-01"},
        ],
    )
    assert pmla_interim is not None
    assert pmla_interim.id == "pmla_anticipatory_interim_bail"
    rendered = " ".join(pmla_interim.lines)
    assert "newborn-care" in rendered
    assert "woman/sick/infirm vulnerability" in rendered

    ed_only_q = "ed raid summons husband can ask anticipatory bail before arrest"
    ed_only = common_workflow_contract_result(
        ed_only_q,
        route_matter(ed_only_q),
        [
            {"index": 1, "title": "Prevention of Money Laundering Act 2002", "anchor": "pmla-2002/sec-45"},
            {"index": 2, "title": "Bharatiya Nagarik Suraksha Sanhita 2023", "anchor": "bnss-2023/sec-482@2024-07-01"},
        ],
    )
    assert ed_only is not None
    assert ed_only.id == "pmla_anticipatory_interim_bail"
    assert "PMLA/ED pre-arrest bail" in " ".join(ed_only.lines)

    ndps_q = "brother arrested NDPS 50 gram heroin commercial or not bail chances"
    ndps = common_workflow_contract_result(
        ndps_q,
        route_matter(ndps_q),
        [
            {"index": 1, "title": "Narcotic Drugs and Psychotropic Substances Act 1985", "anchor": "ndps-1985/sec-50"},
            {"index": 2, "title": "Bharatiya Nagarik Suraksha Sanhita 2023", "anchor": "bnss-2023/sec-483@2024-07-01"},
            {"index": 3, "title": "Code of Criminal Procedure 1973", "anchor": "crpc-1973/sec-437-a"},
            {"index": 4, "title": "Narcotic Drugs and Psychotropic Substances Act 1985", "anchor": "ndps-1985/sec-36A"},
        ],
    )
    assert ndps is not None
    assert ndps.id == "ndps_quantity_bail"
    rendered = " ".join(ndps.lines)
    assert "50 gram heroin" in rendered
    assert "commercial quantity" in rendered
    assert "ordinary bail" in rendered
    assert "already arrested or in custody" not in rendered

    uapa_default_q = "brother arrested uapa 90 days over no chargesheet default bail possible"
    uapa_default = common_workflow_contract_result(
        uapa_default_q,
        route_matter(uapa_default_q),
        [
            {"index": 1, "title": "Bharatiya Nagarik Suraksha Sanhita 2023", "anchor": "bnss-2023/sec-187-d@2024-07-01"},
            {"index": 2, "title": "Unlawful Activities (Prevention) Act 1967", "anchor": "uapa-1967/sec-43d"},
            {"index": 3, "title": "Code of Criminal Procedure 1973", "anchor": "crpc-1973/sec-167-b"},
        ],
    )
    assert uapa_default is not None
    assert uapa_default.id == "default_bail_no_chargesheet"
    rendered = " ".join(uapa_default.lines)
    assert "default-bail calculation" in rendered
    assert "UAPA extension source" in rendered
    assert "prima facie case made out" not in rendered

    uapa_prima = common_workflow_contract_result(
        "urgent brother in jail 18 months UAPA bail when prima facie case made out kya hota how to complain",
        route_matter("urgent brother in jail 18 months UAPA bail when prima facie case made out kya hota how to complain"),
        [
            {"index": 1, "title": "Unlawful Activities (Prevention) Act 1967", "anchor": "uapa-1967/sec-43d"},
            {"index": 2, "title": "Constitution of India", "anchor": "constitution-india/sec-21"},
            {"index": 3, "title": "Bharatiya Nagarik Suraksha Sanhita 2023", "anchor": "bnss-2023/sec-483@2024-07-01"},
        ],
    )
    assert uapa_prima is not None
    assert uapa_prima.id == "uapa_prima_facie_bail"
    rendered = " ".join(uapa_prima.lines)
    assert "UAPA bail" in rendered
    assert "Section 43D special bail filter" in rendered
    assert "BNSS bail source only for the forum/procedure side" in rendered
    assert "default-bail calculation" not in rendered

    prohibition_q = "police caught me drinking village they saying case under prohibition law what punishment"
    prohibition = common_workflow_contract_result(
        prohibition_q,
        route_matter(prohibition_q),
        [
            {"index": 1, "title": "Code of Criminal Procedure 1973", "anchor": "crpc-1973/sec-439"},
            {"index": 2, "title": "Constitution of India", "anchor": "constitution-india/sec-44"},
            {"index": 8, "title": "Bharatiya Nagarik Suraksha Sanhita 2023", "anchor": "bnss-2023/sec-47@2024-07-01"},
        ],
    )
    assert prohibition is not None
    assert prohibition.id == "state_prohibition_excise_accused"
    rendered = " ".join(prohibition.lines)
    assert "do not state a concrete punishment from BNSS/CrPC alone" in rendered
    assert "right to be released on bail" in rendered
    assert "does not itself decide the State prohibition punishment" in rendered
    assert "Article 44" not in rendered


def test_stage2_prohibition_contract_source_gating_variants():
    query = "police caught me drinking village they saying case under prohibition law what punishment"

    article_only = common_workflow_contract_result(
        query,
        route_matter(query),
        [{"index": 1, "title": "Constitution of India", "anchor": "constitution-india/sec-44"}],
    )
    assert article_only is None or article_only.id != "state_prohibition_excise_accused"

    procedure_only = common_workflow_contract_result(
        query,
        route_matter(query),
        [{"index": 2, "title": "Bharatiya Nagarik Suraksha Sanhita 2023", "anchor": "bnss-2023/sec-47@2024-07-01"}],
    )
    assert procedure_only is not None
    assert procedure_only.id == "state_prohibition_excise_accused"
    rendered = " ".join(procedure_only.lines)
    assert "do not state a concrete punishment from BNSS/CrPC alone" in rendered
    assert "FIR/notice section" in rendered
    assert "[2]" in rendered

    bihar = common_workflow_contract_result(
        "patna thana says section 37 bihar prohibition on me for liquor what can I do",
        route_matter("patna thana says section 37 bihar prohibition on me for liquor what can I do"),
        [
            {"index": 1, "title": "Bihar Prohibition and Excise Act 2016", "anchor": "bihar-prohibition-excise-2016/sec-37"},
            {"index": 2, "title": "Bharatiya Nagarik Suraksha Sanhita 2023", "anchor": "bnss-2023/sec-483@2024-07-01"},
        ],
    )
    assert bihar is not None
    assert bihar.id == "state_prohibition_excise_accused"
    rendered = " ".join(bihar.lines)
    assert "Bihar Prohibition and Excise Act source" in rendered
    assert "punishment turns on the state Act section" in rendered
    assert "[1]" in rendered


def test_stage3_critical_failure_contract_repairs():
    arrest_delay_q = "papa arrest 5 din ho gaya magistrate ke samne kab le jana hota hai"
    arrest_delay_sources = [
        {"index": 1, "title": "Constitution of India", "anchor": "constitution-india/sec-22"},
        {"index": 2, "title": "Bharatiya Nagarik Suraksha Sanhita 2023", "anchor": "bnss-2023/sec-58@2024-07-01"},
        {"index": 3, "title": "Constitution of India", "anchor": "constitution-india/sec-21"},
        {"index": 4, "title": "Code of Criminal Procedure 1973", "anchor": "crpc-1973/sec-57"},
    ]
    arrest_delay = _grounded_joined(arrest_delay_q, arrest_delay_sources)
    assert _workflow_id(arrest_delay_q, arrest_delay_sources) == "arrest_magistrate_production_delay"
    assert "urgent arrest-production" in arrest_delay
    assert "beyond 24 hours" in arrest_delay
    assert "DLSA" in arrest_delay
    arrest_delay_with_navtej_distractor = [
        *arrest_delay_sources,
        {"index": 5, "title": "NAVTEJ SINGH JOHAR & ORS. versus UNION OF INDIA", "anchor": "2018-insc-790#header"},
    ]
    assert _workflow_id(arrest_delay_q, arrest_delay_with_navtej_distractor) == "arrest_magistrate_production_delay"

    dk_basu_q = "police took my brother yesterday no arrest memo given dk basu kya hai"
    dk_basu_sources = [
        {"index": 1, "title": "Constitution of India", "anchor": "constitution-india/sec-21"},
        {"index": 2, "title": "Constitution of India", "anchor": "constitution-india/sec-22"},
        {"index": 3, "title": "Bharatiya Nagarik Suraksha Sanhita 2023", "anchor": "bnss-2023/sec-47@2024-07-01"},
    ]
    dk_basu = _grounded_joined(dk_basu_q, dk_basu_sources)
    assert _workflow_id(dk_basu_q, dk_basu_sources) == "arrest_memo_grounds_family_intimation"
    assert "DK Basu/no-arrest-memo" in dk_basu
    assert "arrest memo" in dk_basu

    lawyer_q = "husband first time arrest jail superintendent not allowing lawyer meeting legal"
    lawyer_sources = [
        {"index": 1, "title": "Constitution of India", "anchor": "constitution-india/sec-22"},
        {"index": 2, "title": "Bharatiya Nagarik Suraksha Sanhita 2023", "anchor": "bnss-2023/sec-47@2024-07-01"},
        {"index": 3, "title": "Legal Services Authorities Act 1987", "anchor": "legal-services-authorities-1987/sec-12"},
    ]
    lawyer = _grounded_joined(lawyer_q, lawyer_sources)
    assert _workflow_id(lawyer_q, lawyer_sources) == "custody_legal_aid_lawyer_access"
    assert "first arrest" in lawyer
    assert "same day" in lawyer
    assert "Jail Superintendent" in lawyer

    mdma_q = "drug dealer in goa caught with mdma in my bag he gave 200mg punishment"
    ndps_sources = [
        {"index": 1, "title": "Narcotic Drugs and Psychotropic Substances Act 1985", "anchor": "ndps-1985/sec-22"},
        {"index": 2, "title": "Narcotic Drugs and Psychotropic Substances Act 1985", "anchor": "ndps-1985/sec-37"},
    ]
    mdma = _grounded_joined(mdma_q, ndps_sources)
    assert _workflow_id(mdma_q, ndps_sources) == "ndps_quantity_bail"
    assert "200mg" in mdma
    assert "punishment" in mdma
    assert "conscious possession" in mdma

    bhang_q = "vit student caught with bhang lassi in mahabaleshwar holi is it ndps"
    bhang_sources = [
        {"index": 1, "title": "Narcotic Drugs and Psychotropic Substances Act 1985", "anchor": "ndps-1985/sec-2"},
        {"index": 2, "title": "Narcotic Drugs and Psychotropic Substances Act 1985", "anchor": "ndps-1985/sec-37"},
        {"index": 3, "title": "Maharashtra Prohibition Act 1949", "anchor": "maharashtra-state-excise-act-prohibition-1949/sec-2"},
    ]
    bhang = _grounded_joined(bhang_q, bhang_sources)
    assert _workflow_id(bhang_q, bhang_sources) == "ndps_bhang_lassi"
    assert "Maharashtra Prohibition/State Excise Act source" in bhang
    assert "NDPS, Maharashtra prohibition/excise" in bhang

    dv_q = "my husband gets angry and slaps me but says sorry next day my parents say all marriages are like this should I stay"
    dv_sources = [
        {"index": 1, "title": "Protection of Women from Domestic Violence Act 2005", "anchor": "domestic-violence-2005/sec-3"},
        {"index": 2, "title": "Bharatiya Nyaya Sanhita 2023", "anchor": "bns-2023/sec-115"},
        {"index": 3, "title": "Bharatiya Nagarik Suraksha Sanhita 2023", "anchor": "bnss-2023/sec-173"},
    ]
    dv = _grounded_joined(dv_q, dv_sources)
    assert _workflow_id(dv_q, dv_sources) == "domestic_violence_immediate_safety"
    assert "Do not decide whether to stay" in dv
    assert "all marriages are like this" in dv

    compensation_q = "son acquitted by sessions court after 4 yrs jail can sue state for compensation"
    compensation_sources = [
        {"index": 1, "title": "Constitution of India", "anchor": "constitution-india/sec-21"},
        {"index": 2, "title": "Bharatiya Nagarik Suraksha Sanhita 2023", "anchor": "bnss-2023/sec-479@2024-07-01"},
        {"index": 3, "title": "Code of Criminal Procedure 1973", "anchor": "crpc-1973/sec-436-a"},
    ]
    compensation = _grounded_joined(compensation_q, compensation_sources)
    assert _workflow_id(compensation_q, compensation_sources) == "custody_delay_compensation_after_release"
    assert "certified acquittal" in compensation
    assert "writ compensation under Article 21" in compensation

    odisha_land_q = "tribal land mutation to non tribal buyer in nuapada odisha what can we do"
    odisha_land_sources = [
        {"index": 1, "title": "Orissa Scheduled Areas Transfer of Immovable Property (By Scheduled Tribes) Regulation 1956", "anchor": "orissa-scheduled-areas-transfer-immovable-property-st-1956/sec-3"},
        {"index": 2, "title": "Constitution of India", "anchor": "constitution-india/sec-244"},
        {"index": 3, "title": "Panchayats (Extension to the Scheduled Areas) Act 1996", "anchor": "pesa-1996/sec-4-c"},
    ]
    odisha_land = _grounded_joined(odisha_land_q, odisha_land_sources)
    assert _workflow_id(odisha_land_q, odisha_land_sources) == "tribal_land_nontribal_transfer"
    assert "Orissa/Odisha Scheduled Areas Transfer Regulation" in odisha_land
    assert "controlling state-law lane" in odisha_land
    assert "uncle" not in odisha_land


def test_stage5_failure60_variants_keep_exact_source_and_actions():
    ap_land_q = "pls tell tehsildar transferred my baba land to bania without my consent agency area andhra need lawyer or police"
    ap_land_sources = [
        {"index": 1, "title": "Andhra Pradesh Scheduled Areas Land Transfer Regulation 1959", "anchor": "andhra-pradesh-scheduled-areas-land-transfer-regulation-1959/sec-3"},
        {"index": 2, "title": "Constitution of India", "anchor": "constitution-india/sec-244"},
        {"index": 3, "title": "Panchayats (Extension to the Scheduled Areas) Act 1996", "anchor": "pesa-1996/sec-4-c"},
    ]
    ap_land = _grounded_joined(ap_land_q, ap_land_sources)
    assert _workflow_id(ap_land_q, ap_land_sources) == "tribal_land_nontribal_transfer"
    assert "AP Scheduled Areas Land Transfer Regulation" in ap_land
    assert "controlling state-law lane" in ap_land
    assert "[1]" in ap_land

    munda_land_q = "pls tell munda land grabbed by upper caste in our agency village how to get back chaibasa need lawyer or police"
    munda_land_sources = [
        {"index": 1, "title": "Chota Nagpur Tenancy Act 1908", "anchor": "chota-nagpur-tenancy-1908/sec-46"},
        {"index": 2, "title": "Panchayats (Extension to the Scheduled Areas) Act 1996", "anchor": "pesa-1996/sec-4-c"},
        {"index": 3, "title": "Scheduled Castes and Scheduled Tribes (Prevention of Atrocities) Act 1989", "anchor": "sc-st-poa-1989/sec-3-d"},
    ]
    munda_land = _grounded_joined(munda_land_q, munda_land_sources)
    assert _workflow_id(munda_land_q, munda_land_sources) == "tribal_land_nontribal_transfer"
    assert "Chota Nagpur Tenancy Act" in munda_land
    assert "tribal land grab" in munda_land
    assert "[1]" in munda_land

    bhang_q = "pls tell vit student caught with bhang lassi in mahabaleshwar holi is it ndps need lawyer or police"
    bhang_sources = [
        {"index": 1, "title": "Narcotic Drugs and Psychotropic Substances Act 1985", "anchor": "ndps-1985/sec-2"},
        {"index": 2, "title": "Maharashtra Prohibition Act 1949", "anchor": "maharashtra-state-excise-act-prohibition-1949/sec-2"},
        {"index": 3, "title": "Narcotic Drugs and Psychotropic Substances Act 1985", "anchor": "ndps-1985/sec-37"},
    ]
    bhang = _grounded_joined(bhang_q, bhang_sources)
    assert _workflow_id(bhang_q, bhang_sources) == "ndps_bhang_lassi"
    assert "Maharashtra Prohibition/State Excise Act" in bhang
    assert "not treat every bhang-lassi fact pattern as an NDPS possession offence" in bhang

    bonded_q = "hi, thekedar took my aadhaar original 6 months back not returning he keeping bihar workers id can i file case"
    bonded_sources = [
        {"index": 1, "title": "Bonded Labour System (Abolition) Act 1976", "anchor": "bonded-labour-1976/sec-10"},
        {"index": 2, "title": "Aadhaar (Targeted Delivery of Financial and Other Subsidies, Benefits and Services) Act 2016", "anchor": "aadhaar-2016/sec-29"},
        {"index": 3, "title": "Inter-State Migrant Workmen (Regulation of Employment and Conditions of Service) Act 1979", "anchor": "ismw-1979/sec-12"},
    ]
    bonded = _grounded_joined(bonded_q, bonded_sources)
    bonded_result = common_workflow_contract_result(bonded_q, route_matter(bonded_q), bonded_sources)
    assert bonded_result is not None
    assert bonded_result.id == "bonded_labour_rescue_contract"
    assert "original Aadhaar or ID papers" in bonded
    assert "[2]" in bonded


def test_bonded_labour_coercion_owner_requires_section_12_and_stays_in_its_route():
    coercion_query = "thekedar took advance and is not letting us leave the brick kiln"
    action_source = [
        {"index": 1, "title": "Bonded Labour System (Abolition) Act 1976", "anchor": "bonded-labour-1976/sec-12"},
        {"index": 2, "title": "Bonded Labour System (Abolition) Act 1976", "anchor": "bonded-labour-1976/sec-4"},
    ]

    coercion = common_workflow_contract_result(
        coercion_query,
        route_matter(coercion_query),
        action_source,
    )
    assert coercion is not None
    assert coercion.id == "bonded_labour_coercion_release"
    assert coercion.answer_mode == "safety_primary"
    assert "District Magistrate/SDM" in " ".join(coercion.lines)
    assert "[1]" in " ".join(coercion.lines)

    no_action_source = common_workflow_contract_result(
        coercion_query,
        route_matter(coercion_query),
        [{"index": 2, "title": "Bonded Labour System (Abolition) Act 1976", "anchor": "bonded-labour-1976/sec-4"}],
    )
    assert no_action_source is None or no_action_source.id != "bonded_labour_coercion_release"

    wage_query = "contractor has not paid my overtime wages for two months"
    wage_owner = common_workflow_contract_result(
        wage_query,
        route_matter(wage_query),
        action_source,
    )
    assert wage_owner is None or wage_owner.id != "bonded_labour_coercion_release"


def test_marketplace_trademark_counter_notice_preempts_generic_notice_only_with_controlling_source():
    query = "amazon delisted my product after an IP complaint; how do I file a trademark counter notice"
    route = route_matter(query)
    controlling_source = [
        {"index": 1, "title": "Trade Marks Act 1999", "anchor": "trade-marks-1999/sec-29"},
        {"index": 2, "title": "Trade Marks Act 1999", "anchor": "trade-marks-1999/sec-134"},
    ]
    workflow = common_workflow_contract_result(query, route, controlling_source)

    assert workflow is not None
    assert workflow.id == "trademark_cease_desist_logo_similarity"
    assert _legacy_template_preempts_workflow(query, route, controlling_source, workflow)
    rendered = _grounded_joined(query, controlling_source)
    assert "product delisted on Amazon" in rendered
    assert "platform appeal/counter-record" in rendered

    weak_source = [
        {"index": 1, "title": "Trade Marks Act 1999", "anchor": "trade-marks-1999/sec-34"},
    ]
    weak_workflow = common_workflow_contract_result(query, route, weak_source)
    assert weak_workflow is not None
    assert not _legacy_template_preempts_workflow(query, route, weak_source, weak_workflow)


def test_stage5_safety_workflows_promote_reviewed_action_lines():
    cases = [
        (
            "i am confused how to file habeas corpus petition husband detained illegally by police pls guide",
            [
                {"index": 1, "title": "Constitution of India", "anchor": "constitution-india/sec-226"},
                {"index": 2, "title": "Constitution of India", "anchor": "constitution-india/sec-22"},
                {"index": 3, "title": "Bharatiya Nagarik Suraksha Sanhita 2023", "anchor": "bnss-2023/sec-58"},
            ],
            "custody_habeas_lockup_abuse",
        ),
        (
            "hi, my daughter eloped with boy of other religion family threatening her with khap panchayat can i file case",
            [
                {"index": 1, "title": "Constitution of India", "anchor": "constitution-india/sec-21"},
                {"index": 2, "title": "Bharatiya Nagarik Suraksha Sanhita 2023", "anchor": "bnss-2023/sec-173"},
                {"index": 3, "title": "Bharatiya Nyaya Sanhita 2023", "anchor": "bns-2023/sec-351"},
            ],
            "honour_threat_police_protection",
        ),
        (
            "my parents threatening to kill me if i marry inter caste need protection",
            [
                {"index": 1, "title": "Constitution of India", "anchor": "constitution-india/sec-21"},
                {"index": 2, "title": "Bharatiya Nagarik Suraksha Sanhita 2023", "anchor": "bnss-2023/sec-173"},
                {"index": 3, "title": "Bharatiya Nyaya Sanhita 2023", "anchor": "bns-2023/sec-351"},
            ],
            "honour_threat_police_protection",
        ),
        (
            "need help, my daughter is 16 her father is fixing marriage with 35 year old man fr money what can I do quickly what next",
            [
                {"index": 1, "title": "Prohibition of Child Marriage Act 2006", "anchor": "child-marriage-2006/sec-13"},
                {"index": 2, "title": "Protection of Children from Sexual Offences Act 2012", "anchor": "pocso-2012/sec-19"},
            ],
            "child_marriage_prevention",
        ),
        (
            "urgent village man dies cleaning septic tank no safety equipment cmpny refusing compensation how to complain",
            [
                {"index": 1, "title": "Prohibition of Employment as Manual Scavengers and their Rehabilitation Act 2013", "anchor": "manual-scavenging-2013/sec-7"},
                {"index": 2, "title": "Employees' Compensation Act 1923", "anchor": "employees-compensation-1923/sec-3"},
            ],
            "manual_scavenging_death_compensation",
        ),
        (
            "hi, thekedar took my aadhaar original 6 months back not returning he keeping bihar workers id can i file case",
            [
                {"index": 1, "title": "Bonded Labour System (Abolition) Act 1976", "anchor": "bonded-labour-1976/sec-10"},
                {"index": 2, "title": "Aadhaar (Targeted Delivery of Financial and Other Subsidies, Benefits and Services) Act 2016", "anchor": "aadhaar-2016/sec-29"},
            ],
            "bonded_labour_rescue_contract",
        ),
    ]

    for query, passages, expected_id in cases:
        result = common_workflow_contract_result(query, route_matter(query), passages)
        assert result is not None, query
        assert result.id == expected_id, query
        assert workflow_contract_promotes_verifier(result), query
        assert "**What you can do next**" in result.lines, query


def test_stage4_failure_cluster_repairs_preserve_user_shape():
    construction_q = "principal employer L&T claiming contract worker not their problem after accident pillar fell mumbai"
    construction = _grounded_joined(construction_q, [
        {"index": 1, "title": "Employees' Compensation Act 1923", "anchor": "employees-compensation-1923/sec-3"},
        {"index": 2, "title": "Employees' Compensation Act 1923", "anchor": "employees-compensation-1923/sec-22"},
        {"index": 3, "title": "Building and Other Construction Workers (Regulation of Employment and Conditions of Service) Act 1996", "anchor": "bocw-1996/sec-39"},
        {"index": 4, "title": "Contract Labour (Regulation and Abolition) Act 1970", "anchor": "contract-labour-1970/sec-21"},
        {"index": 5, "title": "Factories Act 1948", "anchor": "factories-1948/sec-111"},
    ])
    assert "pillar-fall construction-site accident in Mumbai" in construction
    assert "L&T/principal-employer details" in construction
    assert "lost a hand/limb" not in construction

    furlough_q = "65 yrs heart patient husband in jail furlough application uttar pradesh how to file"
    furlough = _grounded_joined(furlough_q, [
        {"index": 1, "title": "Prisons Act 1894", "anchor": "prisons-act-1894/sec-59"},
        {"index": 2, "title": "Constitution of India", "anchor": "constitution-india/sec-21"},
    ])
    assert _workflow_id(furlough_q, [
        {"index": 1, "title": "Prisons Act 1894", "anchor": "prisons-act-1894/sec-59"},
        {"index": 2, "title": "Constitution of India", "anchor": "constitution-india/sec-21"},
    ]) is None
    assert "Uttar Pradesh" in furlough
    assert "heart-condition medical proof" in furlough
    assert "visitor-list" not in furlough
    assert "mulaqat" not in furlough

    drawback_q = "drawback claim rejected by customs ngu shipping bill mismatched export incentive 9 lakh"
    drawback = _grounded_joined(drawback_q, [
        {"index": 1, "title": "Customs Act 1962", "anchor": "customs-1962/sec-75"},
        {"index": 2, "title": "Customs Act 1962", "anchor": "customs-1962/sec-27"},
        {"index": 3, "title": "Customs Act 1962", "anchor": "customs-1962/sec-128"},
    ])
    drawback_workflow = common_workflow_contract_result(drawback_q, route_matter(drawback_q), [
        {"index": 1, "title": "Customs Act 1962", "anchor": "customs-1962/sec-75"},
        {"index": 2, "title": "Customs Act 1962", "anchor": "customs-1962/sec-27"},
        {"index": 3, "title": "Customs Act 1962", "anchor": "customs-1962/sec-128"},
    ])
    assert drawback_workflow is not None
    assert drawback_workflow.id == "customs_drawback_export_mismatch"
    assert drawback_workflow.answer_mode == "primary"
    assert "drawback claim rejected" in drawback
    assert "shipping bill" in drawback
    assert "drawback/export-incentive file" in drawback

    icegate_q = "icegate showing bill of entry on hold misdeclaration alleged chinese led lights"
    icegate = _grounded_joined(icegate_q, [
        {"index": 1, "title": "Customs Act 1962", "anchor": "customs-1962/sec-124"},
        {"index": 2, "title": "Customs Act 1962", "anchor": "customs-1962/sec-111"},
        {"index": 3, "title": "Customs Act 1962", "anchor": "customs-1962/sec-112"},
        {"index": 4, "title": "Customs Act 1962", "anchor": "customs-1962/sec-17"},
        {"index": 5, "title": "Customs Act 1962", "anchor": "customs-1962/sec-128"},
    ])
    icegate_workflow = common_workflow_contract_result(icegate_q, route_matter(icegate_q), [
        {"index": 1, "title": "Customs Act 1962", "anchor": "customs-1962/sec-124"},
        {"index": 2, "title": "Customs Act 1962", "anchor": "customs-1962/sec-111"},
        {"index": 3, "title": "Customs Act 1962", "anchor": "customs-1962/sec-112"},
    ])
    assert icegate_workflow is not None
    assert icegate_workflow.id == "customs_icegate_misdeclaration_hold"
    assert icegate_workflow.answer_mode == "primary"
    assert "ICEGATE bill-of-entry hold" in icegate
    assert "Chinese LED lights" in icegate
    assert "misdeclaration" in icegate
    assert "ICEGATE hold or mismatch screenshot" in icegate

    stop_payment_q = "drawer ka cheque 3 lakh ka return aaya stop payment likh ke kya kar sakte hai"
    stop_payment = _grounded_joined(stop_payment_q, [
        {"index": 1, "title": "Negotiable Instruments Act 1881", "anchor": "ni-act-1881/sec-138"},
        {"index": 2, "title": "Negotiable Instruments Act 1881", "anchor": "ni-act-1881/sec-142"},
        {"index": 3, "title": "Bharatiya Nagarik Suraksha Sanhita 2023", "anchor": "bnss-2023/sec-223"},
    ])
    assert "your stop-payment cheque return" in stop_payment
    assert "3 lakh cheque" in stop_payment
    assert "drawer/company/signatory details" in stop_payment

    company_cheque_q = "private limited company partner gave me post dated cheque 12 lakh bounced coimbatore"
    company_cheque = _grounded_joined(company_cheque_q, [
        {"index": 1, "title": "Negotiable Instruments Act 1881", "anchor": "ni-act-1881/sec-138"},
        {"index": 2, "title": "Negotiable Instruments Act 1881", "anchor": "ni-act-1881/sec-142"},
        {"index": 3, "title": "Bharatiya Nagarik Suraksha Sanhita 2023", "anchor": "bnss-2023/sec-223"},
    ])
    assert "private-limited/company cheque" in company_cheque
    assert "drawer company" in company_cheque

    stalking_q = "ex boyfriend follows my scooty everyday from office to home he doesn't talk just follows what section is this"
    stalking = _grounded_joined(stalking_q, [
        {"index": 1, "title": "Bharatiya Nyaya Sanhita 2023", "anchor": "bns-2023/sec-78"},
        {"index": 2, "title": "Bharatiya Nagarik Suraksha Sanhita 2023", "anchor": "bnss-2023/sec-173"},
    ])
    assert "repeated following of your scooty from office to home" in stalking
    assert "BNS Section 78" in stalking
    assert "does not speak" in stalking

    lost_hand_q = "my husband lost hand in brick kiln no compensation owner saying he was careless"
    lost_hand = _grounded_joined(lost_hand_q, [
        {"index": 1, "title": "Employees' Compensation Act 1923", "anchor": "employees-compensation-1923/sec-3"},
        {"index": 2, "title": "Employees' Compensation Act 1923", "anchor": "employees-compensation-1923/sec-22"},
        {"index": 3, "title": "Factories Act 1948", "anchor": "factories-1948/sec-111"},
    ])
    assert "lost hand/limb" in lost_hand
    assert "worker was careless" in lost_hand
    assert "Employees' Compensation Commissioner" in lost_hand

    worksite_assault_q = "site mukadam beat me head injury 8 stitches when i asked for old wages mumbai"
    worksite_assault = _grounded_joined(worksite_assault_q, [
        {"index": 1, "title": "Bharatiya Nyaya Sanhita 2023", "anchor": "bns-2023/sec-117"},
        {"index": 2, "title": "Employees' Compensation Act 1923", "anchor": "employees-compensation-1923/sec-3"},
        {"index": 3, "title": "Code on Wages 2019", "anchor": "code-on-wages-2019/sec-17"},
    ])
    assert "mukadam" in worksite_assault
    assert "8-stitch head injury" in worksite_assault
    assert "BNS source covers voluntarily causing grievous hurt" in worksite_assault

    tcs_q = "TCS deducted on foreign remittance for my son education abroad how do i claim it back"
    tcs = _grounded_joined(tcs_q, [
        {"index": 1, "title": "Income-tax Act 1961", "anchor": "income-tax-1961/sec-206C"},
        {"index": 2, "title": "Income-tax Act 1961", "anchor": "income-tax-1961/sec-139"},
        {"index": 3, "title": "Income-tax Act 1961", "anchor": "income-tax-1961/sec-237"},
    ])
    assert "TCS deducted on foreign remittance for education abroad" in tcs
    assert "AIS/Form 26AS" in tcs
    assert "claim the TCS credit or refund" in tcs

    supplier_gst_q = "supplier gst cancelled retrospectively can i still claim ITC paid him 6 months back"
    supplier_gst = _grounded_joined(supplier_gst_q, [
        {"index": 1, "title": "Central Goods and Services Tax Act 2017", "anchor": "cgst-2017/sec-16"},
        {"index": 2, "title": "Central Goods and Services Tax Act 2017", "anchor": "cgst-2017/sec-29"},
        {"index": 3, "title": "Central Goods and Services Tax Act 2017", "anchor": "cgst-2017/sec-73"},
    ])
    assert "supplier retrospective-cancellation ITC issue" in supplier_gst
    assert "do not treat the supplier's revocation remedy as your own buyer-side ITC answer" in supplier_gst
    assert "supplier GST status" in supplier_gst

    foreign_invoice_q = "client in dubai not paying 4 lakh invoice for my saas work indian law"
    foreign_invoice = _grounded_joined(foreign_invoice_q, [
        {"index": 1, "title": "Indian Contract Act 1872", "anchor": "indian-contract-1872/sec-37"},
        {"index": 2, "title": "Foreign Exchange Management Act 1999", "anchor": "fema-1999/sec-8"},
    ])
    assert "Dubai/foreign client" in foreign_invoice
    assert "Indian SaaS or services invoice" in foreign_invoice
    assert "FEMA/foreign-exchange receipt" in foreign_invoice

    agent_q = "agent took my goods worth 7 lakh and absconded gujarat principal agent relationship"
    agent = _grounded_joined(agent_q, [
        {"index": 1, "title": "Indian Contract Act 1872", "anchor": "indian-contract-1872/sec-182"},
        {"index": 2, "title": "Indian Contract Act 1872", "anchor": "indian-contract-1872/sec-211"},
        {"index": 3, "title": "Indian Contract Act 1872", "anchor": "indian-contract-1872/sec-213"},
        {"index": 4, "title": "Specific Relief Act 1963", "anchor": "specific-relief-1963/sec-38"},
    ])
    assert "principal-agent relationship" in agent
    assert "entrustment of goods" in agent
    assert "police cheating or breach-of-trust track separate" in agent

    muslim_second_q = "husband took second wife without divorcing me he says muslim law allows him I am also muslim what protection do I have"
    muslim_second = _grounded_joined(muslim_second_q, [
        {"index": 1, "title": "Muslim Personal Law (Shariat) Application Act 1937", "anchor": "shariat-1937/sec-2"},
        {"index": 2, "title": "Family Courts Act 1984", "anchor": "family-courts-1984/sec-7"},
        {"index": 3, "title": "Protection of Women from Domestic Violence Act 2005", "anchor": "pwdva-2005/sec-12"},
        {"index": 4, "title": "Bharatiya Nyaya Sanhita 2023", "anchor": "bns-2023/sec-82"},
    ])
    assert "do not treat BNS bigamy alone" in muslim_second
    assert "Shariat/personal-law route" in muslim_second
    assert "PWDVA protection/residence/monetary-relief" in muslim_second


def test_stage4b_failure_ledger_answer_repairs_are_grounded_and_user_shaped():
    customs = _grounded_joined(
        "icegate showing bill of entry on hold misdeclaration alleged chinese led lights",
        [
            {"index": 1, "title": "Customs Act 1962", "anchor": "customs-1962/sec-17"},
            {"index": 2, "title": "Customs Act 1962", "anchor": "customs-1962/sec-111"},
            {"index": 3, "title": "Customs Act 1962", "anchor": "customs-1962/sec-112"},
            {"index": 4, "title": "Customs Act 1962", "anchor": "customs-1962/sec-124"},
            {"index": 5, "title": "Customs Act 1962", "anchor": "customs-1962/sec-128"},
        ],
    )
    assert "ICEGATE hold alleging misdeclaration" in customs
    assert "Section 111/112/124 track" in customs

    child_labour = _grounded_joined(
        "garment unit jharkhand girl 15 working with us factory says she is 18 no proof",
        [
            {"index": 1, "title": "Child and Adolescent Labour (Prohibition and Regulation) Act 1986", "anchor": "child-labour-1986/sec-3"},
            {"index": 2, "title": "Child and Adolescent Labour (Prohibition and Regulation) Act 1986", "anchor": "child-labour-1986/sec-17"},
            {"index": 3, "title": "Juvenile Justice (Care and Protection of Children) Act 2015", "anchor": "jj-2015/sec-2"},
        ],
    )
    assert "factory says the worker is 18 but there is no proof" in child_labour
    assert "labour inspector/CWC" in child_labour

    gratuity = _grounded_joined(
        "father epf trust delayed gratuity 18 months no interest paid hsmc bangalore",
        [
            {"index": 1, "title": "Payment of Gratuity Act 1972", "anchor": "gratuity-1972/sec-7"},
            {"index": 2, "title": "Employees Provident Funds and Miscellaneous Provisions Act 1952", "anchor": "epf-1952/sec-7A"},
        ],
    )
    assert "18-month gratuity delay" in gratuity or "delayed for 18 months" in gratuity
    assert "controlling authority" in gratuity

    company_cheque = _grounded_joined(
        "private limited company partner gave me post dated cheque 12 lakh bounced coimbatore",
        [
            {"index": 1, "title": "Negotiable Instruments Act 1881", "anchor": "ni-act-1881/sec-138"},
            {"index": 2, "title": "Negotiable Instruments Act 1881", "anchor": "ni-act-1881/sec-141"},
            {"index": 3, "title": "Negotiable Instruments Act 1881", "anchor": "ni-act-1881/sec-142"},
            {"index": 4, "title": "Bharatiya Nagarik Suraksha Sanhita 2023", "anchor": "bnss-2023/sec-223"},
        ],
    )
    assert "Section 141" in company_cheque
    assert "role/signatory facts" in company_cheque

    streedhan = _grounded_joined(
        "in-laws not giving back my jewellery streedhan after husband died",
        [
            {"index": 1, "title": "Protection of Women from Domestic Violence Act 2005", "anchor": "domestic-violence-2005/sec-3"},
            {"index": 2, "title": "Dowry Prohibition Act 1961", "anchor": "dowry-prohibition-1961/sec-6"},
            {"index": 3, "title": "Hindu Succession Act 1956", "anchor": "hindu-succession-1956/sec-14"},
            {"index": 4, "title": "Bharatiya Nyaya Sanhita 2023", "anchor": "bns-2023/sec-316"},
        ],
    )
    assert "Hindu Succession Section 14" in streedhan
    assert "ordinary in-law property" in streedhan

    exclusivity = _grounded_joined(
        "signed mou with dealer he is selling to my competitor now exclusivity clause kya kar sakte hai",
        [
            {"index": 1, "title": "Indian Contract Act 1872", "anchor": "indian-contract-1872/sec-27"},
            {"index": 2, "title": "Indian Contract Act 1872", "anchor": "indian-contract-1872/sec-73"},
            {"index": 3, "title": "Specific Relief Act 1963", "anchor": "specific-relief-1963/sec-42"},
        ],
    )
    assert "restraint-of-trade" in exclusivity
    assert "compensation source" in exclusivity
    assert "injunction source" in exclusivity

    kanya = _grounded_joined(
        "kanya vivah scheme money not given by government after my daughter wedding",
        [
            {"index": 1, "title": "Bihar Mukhyamantri Kanya Vivah Yojana Service Description", "anchor": "bihar-kanya-vivah-service#header"},
            {"index": 2, "title": "Right to Information Act 2005", "anchor": "rti-2005/sec-6"},
        ],
    )
    assert "state-scheme specific" in kanya
    assert "scheme office/portal first" in kanya

    scholarship = _grounded_joined(
        "post matric scholarship not credited for 2 years college fees due",
        [
            {"index": 1, "title": "Constitution of India", "anchor": "constitution-india/sec-46"},
            {"index": 2, "title": "Right to Information Act 2005", "anchor": "rti-2005/sec-6"},
        ],
    )
    assert "post-matric scholarship" in scholarship
    assert "college fee-demand proof" in scholarship

    mutual_mediation = _grounded_joined(
        "is mediation compulsory in mutual consent divorce family court",
        [
            {"index": 1, "title": "Family Courts Act 1984", "anchor": "family-courts-1984/sec-9"},
            {"index": 2, "title": "Hindu Marriage Act 1955", "anchor": "hindu-marriage-1955/sec-13B"},
        ],
    )
    assert "Family Court counselling/mediation" in mutual_mediation
    assert "do not confuse that with Commercial Courts Section 12A" in mutual_mediation

    dv_residence = _grounded_joined(
        "sasural waale mujhe ghar se nikal diya raat ko bina kuch diye kya main wapis ja sakti hoon",
        [
            {"index": 5, "title": "Protection of Women from Domestic Violence Act 2005", "anchor": "domestic-violence-2005/sec-3"},
            {"index": 1, "title": "Protection of Women from Domestic Violence Act 2005", "anchor": "domestic-violence-2005/sec-17"},
            {"index": 2, "title": "Protection of Women from Domestic Violence Act 2005", "anchor": "domestic-violence-2005/sec-19"},
            {"index": 3, "title": "Bharatiya Nyaya Sanhita 2023", "anchor": "bns-2023/sec-115"},
            {"index": 4, "title": "Bharatiya Nagarik Suraksha Sanhita 2023", "anchor": "bnss-2023/sec-173"},
        ],
    )
    assert _workflow_id(
        "sasural waale mujhe ghar se nikal diya raat ko bina kuch diye kya main wapis ja sakti hoon",
        [
            {"index": 5, "title": "Protection of Women from Domestic Violence Act 2005", "anchor": "domestic-violence-2005/sec-3"},
            {"index": 1, "title": "Protection of Women from Domestic Violence Act 2005", "anchor": "domestic-violence-2005/sec-17"},
            {"index": 2, "title": "Protection of Women from Domestic Violence Act 2005", "anchor": "domestic-violence-2005/sec-19"},
        ],
    ) == "domestic_violence_immediate_safety"
    assert "put you out of the matrimonial home" in dv_residence
    assert "return safely" in dv_residence
    assert "immediate safety first" in dv_residence


def test_stage3_refusal_families_get_reviewed_source_gated_owners():
    cases = [
        (
            "what to do moneylender took my thumb impression on blank paper now showing 5 lakh loan I never took is this legal",
            [
                {"index": 1, "title": "Bharatiya Nyaya Sanhita 2023", "anchor": "bns-2023/sec-336@2024-07-01"},
                {"index": 2, "title": "Bharatiya Nagarik Suraksha Sanhita 2023", "anchor": "bnss-2023/sec-173-a@2024-07-01"},
                {"index": 3, "title": "Code of Criminal Procedure 1973", "anchor": "crpc-1973/sec-200"},
            ],
            "blank_paper_moneylender_fraud",
            "primary",
            ("thumb impression", "blank paper", "forgery/cheating"),
        ),
        (
            "urgent police booked us under arms act for axe we use in farming gadchiroli how to complain",
            [
                {"index": 1, "title": "Arms Act 1959", "anchor": "arms-1959/sec-2"},
                {"index": 2, "title": "Bharatiya Nagarik Suraksha Sanhita 2023", "anchor": "bnss-2023/sec-216@2024-07-01"},
                {"index": 3, "title": "Bharatiya Nyaya Sanhita 2023", "anchor": "bns-2023/sec-351@2024-07-01"},
            ],
            "arms_act_farming_tool_defence",
            "primary",
            ("Arms Act", "farming tool", "seizure memo"),
        ),
        (
            "please help thekedar made fake theft fir against me after i asked wages now police calling station any remedy",
            [
                {"index": 1, "title": "Code on Wages 2019", "anchor": "code-on-wages-2019/sec-45@2019-08-08"},
                {"index": 2, "title": "Bharatiya Nyaya Sanhita 2023", "anchor": "bns-2023/sec-303-d@2024-07-01"},
                {"index": 3, "title": "Bharatiya Nagarik Suraksha Sanhita 2023", "anchor": "bnss-2023/sec-173-a@2024-07-01"},
            ],
            "wage_theft_false_fir",
            "primary",
            ("dual-track wages", "false FIR/police", "FIR/DD entry"),
        ),
        (
            "sir my wife filed 498A on whole family even my old mother how to defend where to go",
            [
                {"index": 1, "title": "Bharatiya Nyaya Sanhita 2023", "anchor": "bns-2023/sec-85@2024-07-01"},
                {"index": 2, "title": "Protection of Women from Domestic Violence Act 2005", "anchor": "domestic-violence-2005/sec-18@1974-01-01"},
                {"index": 3, "title": "Bharatiya Nagarik Suraksha Sanhita 2023", "anchor": "bnss-2023/sec-483@2024-07-01"},
            ],
            "false_fir_defence",
            "primary",
            ("498A/DV matrimonial", "each family member named", "elderly"),
        ),
        (
            "please help biharee called we are by site engineer pune always after wage complain is this crime any remedy",
            [
                {"index": 1, "title": "Code on Wages 2019", "anchor": "code-on-wages-2019/sec-45@2019-08-08"},
                {"index": 2, "title": "Bharatiya Nagarik Suraksha Sanhita 2023", "anchor": "bnss-2023/sec-216@2024-07-01"},
                {"index": 3, "title": "Bharatiya Nyaya Sanhita 2023", "anchor": "bns-2023/sec-351@2024-07-01"},
            ],
            "regional_slur_wage_retaliation",
            "primary",
            ("Bihari/Biharee", "wage-dispute file", "insult alone"),
        ),
        (
            "brother in jail 60 days completed maharashtra mcoca what is custody limit chargesheet",
            [
                {"index": 1, "title": "Bharatiya Nagarik Suraksha Sanhita 2023", "anchor": "bnss-2023/sec-187-d@2024-07-01"},
                {"index": 2, "title": "Code of Criminal Procedure 1973", "anchor": "crpc-1973/sec-167-b"},
                {"index": 3, "title": "Maharashtra Control of Organised Crime Act 1999", "anchor": "maharashtra-control-organised-crime-1999/sec-21"},
            ],
            "default_bail_no_chargesheet",
            "safety_primary",
            ("MCOCA", "Section 21", "filing date/status"),
        ),
        (
            "hi, my husband had affair I caught them I slapped the woman now she is filing case on me what to do can i file case",
            [
                {"index": 1, "title": "Bharatiya Nyaya Sanhita 2023", "anchor": "bns-2023/sec-115@2024-07-01"},
                {"index": 2, "title": "Bharatiya Nagarik Suraksha Sanhita 2023", "anchor": "bnss-2023/sec-48@2024-07-01"},
                {"index": 3, "title": "Code of Criminal Procedure 1973", "anchor": "crpc-1973/sec-50"},
            ],
            "criminal_defence_first_action",
            "primary",
            ("accused-side", "do not retaliate", "affair is a defence"),
        ),
        (
            "urgent police refused to file FIR for theft of my bike where do I go next how to complain",
            [
                {"index": 1, "title": "Bharatiya Nagarik Suraksha Sanhita 2023", "anchor": "bnss-2023/sec-173-a@2024-07-01"},
                {"index": 2, "title": "Bharatiya Nagarik Suraksha Sanhita 2023", "anchor": "bnss-2023/sec-173-c@2024-07-01"},
                {"index": 3, "title": "Code of Criminal Procedure 1973", "anchor": "crpc-1973/sec-154"},
            ],
            "vehicle_theft_fir_refusal",
            "primary",
            ("pre-1-July-2024", "incident on or after 1 July 2024", "Superintendent of Police"),
        ),
        (
            "please help delhi labour chowk police picking us morning saying nautanki begging not work how to stop any remedy",
            [
                {"index": 1, "title": "Code on Wages 2019", "anchor": "code-on-wages-2019/sec-45@2019-08-08"},
                {"index": 2, "title": "Bharatiya Nyaya Sanhita 2023", "anchor": "bns-2023/sec-127-a@2024-07-01"},
                {"index": 3, "title": "Bharatiya Nagarik Suraksha Sanhita 2023", "anchor": "bnss-2023/sec-216@2024-07-01"},
                {"index": 4, "title": "Inter-State Migrant Workmen Act 1979", "anchor": "inter-state-migrant-workmen-1979/sec-14"},
            ],
            "wage_theft_false_fir",
            "primary",
            ("police pickup/detention", "picking workers", "legal aid", "ISMW"),
        ),
        (
            "please help manager threatening to call police saying we are bangladeshi but we are from murshidabad west bengal any remedy",
            [
                {"index": 1, "title": "Constitution of India", "anchor": "constitution-india/sec-21"},
                {"index": 2, "title": "Bharatiya Nagarik Suraksha Sanhita 2023", "anchor": "bnss-2023/sec-173-b@2024-07-01"},
                {"index": 3, "title": "Bharatiya Nyaya Sanhita 2023", "anchor": "bns-2023/sec-351@2024-07-01"},
            ],
            "identity_police_threat_worker",
            "safety_primary",
            ("Bangladeshi", "Murshidabad", "ID/address proof"),
        ),
    ]

    for query, passages, expected_id, expected_mode, must_terms in cases:
        route = route_matter(query)
        workflow = common_workflow_contract_result(query, route, passages)
        rendered = _grounded_joined(query, passages)
        assert workflow is not None, query
        assert workflow.id == expected_id, query
        assert workflow.answer_mode == expected_mode, query
        for term in must_terms:
            assert term in rendered, (query, term, rendered)


def test_stage_c_reviewed_primary_workflows_own_cyber_posh_and_marital_intimacy_answers():
    cyber_query = "online cyber blackmail on bumble screenshots to my dad and he took my phone what to do"
    cyber_passages = [
        {"index": 1, "title": "Information Technology Act 2000", "anchor": "it-act-2000/sec-66d"},
        {"index": 2, "title": "Bharatiya Nyaya Sanhita 2023", "anchor": "bns-2023/sec-308"},
        {"index": 3, "title": "Bharatiya Nagarik Suraksha Sanhita 2023", "anchor": "bnss-2023/sec-173"},
    ]
    cyber = common_workflow_contract_result(cyber_query, route_matter(cyber_query), cyber_passages)
    assert cyber is not None
    assert cyber.id == "cyber_harassment_first_action"
    assert cyber.answer_mode == "primary"
    cyber_answer = _grounded_joined(cyber_query, cyber_passages)
    assert "dating-app blackmail" in cyber_answer
    assert "cybercrime.gov.in/1930" in cyber_answer

    posh_query = "workplace sexual harassment boss touched my back in office HR says ignore what can I do"
    posh_passages = [
        {"index": 1, "title": "Sexual Harassment of Women at Workplace Act 2013", "anchor": "posh-2013/sec-3"},
        {"index": 2, "title": "Bharatiya Nyaya Sanhita 2023", "anchor": "bns-2023/sec-74"},
        {"index": 3, "title": "Industrial Disputes Act 1947", "anchor": "industrial-disputes-1947/sec-2A"},
    ]
    posh = common_workflow_contract_result(posh_query, route_matter(posh_query), posh_passages)
    assert posh is not None
    assert posh.id == "workplace_sexual_harassment_first_action"
    assert posh.answer_mode == "primary"
    posh_answer = _grounded_joined(posh_query, posh_passages)
    assert "POSH workplace-sexual-harassment route" in posh_answer
    assert "separate BNS/police track" in posh_answer

    no_posh = common_workflow_contract_result(
        posh_query,
        route_matter(posh_query),
        [
            {"index": 1, "title": "Bharatiya Nyaya Sanhita 2023", "anchor": "bns-2023/sec-74"},
            {"index": 2, "title": "Industrial Disputes Act 1947", "anchor": "industrial-disputes-1947/sec-2A"},
        ],
    )
    assert no_posh is None or no_posh.id != "workplace_sexual_harassment_first_action"

    intimacy_query = "my wife denies sex from last 1 year what to do"
    intimacy_passages = [
        {"index": 1, "title": "Family Courts Act 1984", "anchor": "family-courts-1984/sec-7"},
        {"index": 2, "title": "Hindu Marriage Act 1955", "anchor": "hindu-marriage-1955/sec-9"},
    ]
    intimacy = common_workflow_contract_result(intimacy_query, route_matter(intimacy_query), intimacy_passages)
    assert intimacy is not None
    assert intimacy.id in {"marital_intimacy", "marital_intimacy_remedy"}
    assert intimacy.answer_mode == "primary"
    intimacy_answer = _grounded_joined(intimacy_query, intimacy_passages)
    assert "Consent matters" in intimacy_answer
    assert "do not force" in intimacy_answer


def test_stage_e1_refusal_cluster_gets_reviewed_source_gated_workflows():
    cases = [
        (
            "can u tell received summons under section 91 bnss for my deleted insta posts is it serious what can i do",
            [
                {"index": 1, "title": "Bharatiya Nagarik Suraksha Sanhita 2023", "anchor": "bnss-2023/sec-94"},
                {"index": 2, "title": "Information Technology Act 2000", "anchor": "it-act-2000/sec-2-c"},
                {"index": 3, "title": "Code of Criminal Procedure 1973", "anchor": "crpc-1973/sec-91"},
                {"index": 4, "title": "Bharatiya Nagarik Suraksha Sanhita 2023", "anchor": "bnss-2023/sec-91"},
            ],
            "criminal_production_notice_electronic_records",
            "safety_primary",
            ("production-of-records issue", "Do not ignore, destroy, edit, or selectively delete", "self-incrimination"),
        ),
        (
            "can u tell fanvue payment frozen 2400 usd indian creator how to release fund what can i do",
            [
                {"index": 1, "title": "Indian Contract Act 1872", "anchor": "indian-contract-1872/sec-37"},
                {"index": 2, "title": "Foreign Exchange Management Act 1999", "anchor": "fema-1999/sec-8"},
                {"index": 3, "title": "Income-tax Act 1961", "anchor": "income-tax-1961/sec-5"},
            ],
            "digital_creator_payout_freeze",
            "primary",
            ("Fanvue payout frozen", "FEMA/foreign-remittance", "payout ledger"),
        ),
        (
            "please help stranger on bumble sent me dick pic without consent is there any law for this in india any remedy",
            [
                {"index": 1, "title": "Information Technology Act 2000", "anchor": "it-act-2000/sec-66E"},
                {"index": 2, "title": "Bharatiya Nyaya Sanhita 2023", "anchor": "bns-2023/sec-75"},
                {"index": 3, "title": "Bharatiya Nagarik Suraksha Sanhita 2023", "anchor": "bnss-2023/sec-173"},
            ],
            "unsolicited_sexual_image_cyber",
            "safety_primary",
            ("cyber privacy/private-image evidence problem", "Do not forward", "cybercrime.gov.in"),
        ),
        (
            "can u tell swiggy pe customer abused me 1 star spam now my id blocked appeal kaha what can i do",
            [
                {"index": 1, "title": "Code on Social Security 2020", "anchor": "social-security-code-2020/sec-112"},
                {"index": 2, "title": "Code on Wages 2019", "anchor": "code-on-wages-2019/sec-17"},
                {"index": 3, "title": "Consumer Protection Act 2019", "anchor": "consumer-protection-2019/sec-2"},
            ],
            "gig_platform_worker_account_block",
            "primary",
            ("Swiggy delivery/partner ID blocked", "written deactivation reason", "payout ledger"),
        ),
        (
            "can u tell instagram suspended my page 200k followers no notice can i sue meta india what can i do",
            [
                {"index": 1, "title": "Information Technology Act 2000", "anchor": "it-act-2000/sec-79"},
                {"index": 2, "title": "Consumer Protection Act 2019", "anchor": "consumer-protection-2019/sec-2"},
            ],
            "social_media_account_suspension",
            "primary",
            ("Instagram/Meta suspension", "platform grievance", "appeal ticket"),
        ),
        (
            "can u tell lost 12 lakh on parimatch betting app can i recover money what can i do",
            [
                {"index": 1, "title": "Public Gambling Act 1867", "anchor": "public-gambling-act-1867/sec-12"},
                {"index": 2, "title": "Consumer Protection Act 2019", "anchor": "consumer-protection-2019/sec-2-f"},
            ],
            "online_gambling_platform_dispute",
            "primary",
            ("not assume losses are automatically recoverable", "platform grievance", "game ledger"),
        ),
        (
            "can u tell lost 50k on dream11 like app is online rummy legal in tamil nadu what can i do",
            [
                {"index": 1, "title": "Tamil Nadu Prohibition of Online Gambling and Regulation of Online Games Act 2022", "anchor": "tamil-nadu-online-gambling-2022/sec-7"},
                {"index": 2, "title": "Consumer Protection Act 2019", "anchor": "consumer-protection-2019/sec-2-f"},
            ],
            "online_gambling_platform_dispute",
            "primary",
            ("online rummy/betting/gambling in Tamil Nadu", "state online-gaming/gambling law", "platform grievance"),
        ),
        (
            "blue trunks app froze my account showing kyc pending pe stuck 80k",
            [
                {"index": 1, "title": "Consumer Protection Act 2019", "anchor": "consumer-protection-2019/sec-2-f"},
                {"index": 2, "title": "Information Technology Act 2000", "anchor": "it-act-2000/sec-79"},
                {"index": 3, "title": "Prevention of Money Laundering Act 2002", "anchor": "pmla-2002/sec-8-d"},
            ],
            "digital_platform_kyc_money_freeze",
            "primary",
            ("KYC-pending reason", "written hold basis", "deposit/withdrawal ledger"),
        ),
        (
            "hi, my husband took our 5 year old to delhi during fight and is not letting me meet how do I get her back fast can i file case",
            [
                {"index": 1, "title": "Hindu Minority and Guardianship Act 1956", "anchor": "hindu-minority-guardianship-1956/sec-6"},
                {"index": 2, "title": "Family Courts Act 1984", "anchor": "family-courts-1984/sec-7"},
                {"index": 3, "title": "Constitution of India", "anchor": "constitution-india/sec-226"},
                {"index": 4, "title": "Guardians and Wards Act 1890", "anchor": "guardians-wards-1890/sec-25"},
            ],
            "child_access",
            "primary",
            ("custody/access", "Family Court", "interim visitation", "High Court writ"),
        ),
    ]

    for query, passages, expected_id, expected_mode, must_terms in cases:
        route = route_matter(query)
        workflow = common_workflow_contract_result(query, route, passages)
        rendered = _grounded_joined(query, passages)
        assert workflow is not None, query
        assert workflow.id == expected_id, query
        assert workflow.answer_mode == expected_mode, query
        if expected_id == "unsolicited_sexual_image_cyber":
            assert workflow_contract_promotes_verifier(workflow)
        assert "[1]" in rendered or "[2]" in rendered or "[3]" in rendered or "[4]" in rendered
        for term in must_terms:
            assert term in rendered, (query, term, rendered)


def test_stage_e1_review_fixes_fail_closed_and_avoid_overbroad_detectors():
    sec49_only = _grounded_joined(
        "fanvue payment frozen 2400 usd indian creator how to release fund",
        [
            {"index": 1, "title": "Indian Contract Act 1872", "anchor": "indian-contract-1872/sec-37"},
            {"index": 2, "title": "Foreign Exchange Management Act 1999", "anchor": "fema-1999/sec-49"},
            {"index": 3, "title": "Income-tax Act 1961", "anchor": "income-tax-1961/sec-5"},
        ],
    )
    assert "FEMA/foreign-remittance compliance lane" not in sec49_only
    assert "platform contract/terms" in sec49_only

    child_property = common_workflow_contract_result(
        "my husband took our 5 year old car and not letting me get it back",
        route_matter("my husband took our 5 year old car and not letting me get it back"),
        [
            {"index": 1, "title": "Guardians and Wards Act 1890", "anchor": "guardians-wards-1890/sec-25"},
            {"index": 2, "title": "Family Courts Act 1984", "anchor": "family-courts-1984/sec-7"},
        ],
    )
    assert child_property is None or child_property.id != "child_access"

    swiggy_customer = common_workflow_contract_result(
        "i ordered food on swiggy and customer care not refunding damaged item",
        route_matter("i ordered food on swiggy and customer care not refunding damaged item"),
        [
            {"index": 1, "title": "Code on Social Security 2020", "anchor": "social-security-code-2020/sec-112"},
            {"index": 2, "title": "Consumer Protection Act 2019", "anchor": "consumer-protection-2019/sec-35"},
        ],
    )
    assert swiggy_customer is None or swiggy_customer.id != "gig_platform_worker_account_block"

    unknown_kyc = common_workflow_contract_result(
        "blue trunks app froze my account showing kyc pending pe stuck 80k",
        route_matter("blue trunks app froze my account showing kyc pending pe stuck 80k"),
        [
            {"index": 1, "title": "Consumer Protection Act 2019", "anchor": "consumer-protection-2019/sec-2"},
            {"index": 2, "title": "Information Technology Act 2000", "anchor": "it-act-2000/sec-79"},
            {"index": 3, "title": "Prevention of Money Laundering Act 2002", "anchor": "pmla-2002/sec-8"},
        ],
    )
    assert unknown_kyc is not None
    assert unknown_kyc.id == "digital_platform_kyc_money_freeze"

    blackmail = common_workflow_contract_result(
        "bf secretly recorded us during sex now threatening to upload",
        route_matter("bf secretly recorded us during sex now threatening to upload"),
        [
            {"index": 1, "title": "Information Technology Act 2000", "anchor": "it-2000/sec-67A"},
            {"index": 2, "title": "Bharatiya Nyaya Sanhita 2023", "anchor": "bns-2023/sec-351"},
            {"index": 3, "title": "Bharatiya Nagarik Suraksha Sanhita 2023", "anchor": "bnss-2023/sec-173"},
        ],
    )
    assert blackmail is None or blackmail.id != "unsolicited_sexual_image_cyber"


def test_stage_e2_common_failure_specificity_regressions():
    epf_query = "i am confused my employer is not depositing my PF for last 8 months, salary slip shows deduction but EPFO passbook shows nothing pls guide"
    epf_passages = [
        {"index": 1, "title": "Employees' Provident Funds and Miscellaneous Provisions Act 1952", "anchor": "epf-1952/sec-14-a"},
        {"index": 2, "title": "Code on Wages 2019", "anchor": "code-on-wages-2019/sec-45"},
        {"index": 3, "title": "Code on Social Security 2020", "anchor": "social-security-code-2020/sec-1"},
    ]
    epf = common_workflow_contract_result(epf_query, route_matter(epf_query), epf_passages)
    epf_answer = _grounded_joined(epf_query, epf_passages)
    assert epf is not None
    assert epf.id == "epf_not_deposited"
    assert "EPFO recovery/grievance" in epf_answer
    assert "daily food deductions" not in epf_answer

    poa_delay_query = "urgent special court POA case pending 5 yrs no judgement aurangabad maharashtra how to complain"
    poa_delay_passages = [
        {"index": 1, "title": "Scheduled Castes and Scheduled Tribes (Prevention of Atrocities) Act 1989", "anchor": "sc-st-poa-1989/sec-15A-a"},
        {"index": 2, "title": "Bharatiya Nagarik Suraksha Sanhita 2023", "anchor": "bnss-2023/sec-173"},
    ]
    poa_delay_answer = _grounded_joined(poa_delay_query, poa_delay_passages)
    assert "Special Court case pending for years" in poa_delay_answer
    assert "Special Public Prosecutor" in poa_delay_answer
    assert "Gram Sabha/FRC" not in poa_delay_answer

    temple_query = "sir thakur family stopped us from entering temple we are dalit where to go"
    temple_passages = [
        {"index": 1, "title": "Protection of Civil Rights Act 1955", "anchor": "protection-civil-rights-1955/sec-3"},
        {"index": 2, "title": "Scheduled Castes and Scheduled Tribes (Prevention of Atrocities) Act 1989", "anchor": "sc-st-poa-1989/sec-3"},
        {"index": 3, "title": "Constitution of India", "anchor": "constitution-india/sec-17"},
    ]
    temple_answer = _grounded_joined(temple_query, temple_passages)
    assert "public-access exclusion" in temple_answer
    assert "temple/well/water/public-place" in temple_answer
    assert "land/patta/IFR" not in temple_answer

    laptop_query = "i am confused my company laptop has been seized by police as part of investigation against my colleague, what are my rights pls guide"
    laptop_passages = [
        {"index": 1, "title": "Bharatiya Nagarik Suraksha Sanhita 2023", "anchor": "bnss-2023/sec-173-b"},
        {"index": 2, "title": "Information Technology Act 2000", "anchor": "it-2000/sec-2-c"},
        {"index": 3, "title": "Bharatiya Nagarik Suraksha Sanhita 2023", "anchor": "bnss-2023/sec-497"},
    ]
    laptop_answer = _grounded_joined(laptop_query, laptop_passages)
    assert "device seized in another person's investigation" in laptop_answer
    assert "release/superdari" in laptop_answer
    assert "written complaint separate from any insurance" not in laptop_answer

    forced_sex_query = "hi, husband forces me at night even when I say no I am tired or unwell is there any law fr this in india now can i file case"
    forced_sex_passages = [
        {"index": 1, "title": "Bharatiya Nagarik Suraksha Sanhita 2023", "anchor": "bnss-2023/sec-216"},
        {"index": 2, "title": "Bharatiya Nyaya Sanhita 2023", "anchor": "bns-2023/sec-67"},
        {"index": 3, "title": "Protection of Women from Domestic Violence Act 2005", "anchor": "domestic-violence-2005/sec-12"},
    ]
    forced_sex_answer = _grounded_joined(forced_sex_query, forced_sex_passages)
    assert "immediate safety and domestic-violence relief" in forced_sex_answer
    assert "ordinary marital disagreement" in forced_sex_answer

    disabled_baby_query = "hi, i gave birth to baby with disability my in laws want me to leave the baby in hospital what is the law can i file case"
    disabled_baby_passages = [
        {"index": 1, "title": "Bharatiya Nyaya Sanhita 2023", "anchor": "bns-2023/sec-351"},
        {"index": 2, "title": "Family Courts Act 1984", "anchor": "family-courts-1984/sec-7"},
        {"index": 3, "title": "Protection of Women from Domestic Violence Act 2005", "anchor": "domestic-violence-2005/sec-12"},
    ]
    disabled_baby_answer = _grounded_joined(disabled_baby_query, disabled_baby_passages)
    assert "disabled baby" in disabled_baby_answer
    assert "child-welfare support" in disabled_baby_answer

    promise_query = "need help, I am living with my boyfriend for 3 yrs he promised marriage now he is marrying another girl can I file case what next"
    promise_passages = [
        {"index": 1, "title": "Bharatiya Nagarik Suraksha Sanhita 2023", "anchor": "bnss-2023/sec-173-b"},
        {"index": 2, "title": "Bharatiya Nyaya Sanhita 2023", "anchor": "bns-2023/sec-69"},
        {"index": 3, "title": "Bharatiya Nyaya Sanhita 2023", "anchor": "bns-2023/sec-78"},
    ]
    promise_answer = _grounded_joined(promise_query, promise_passages)
    assert "BNS Section 69/deceitful-means" in promise_answer
    assert "not automatically a criminal case" in promise_answer
    assert "Whatever the defence route" not in promise_answer

    mining_query = "i am confused dM gave NOC to bauxite project bastar without gram sabha resolution how to challenge pls guide"
    mining_passages = [
        {"index": 1, "title": "Panchayats (Extension to the Scheduled Areas) Act 1996", "anchor": "pesa-1996/sec-4-c"},
        {"index": 2, "title": "Scheduled Tribes and Other Traditional Forest Dwellers (Recognition of Forest Rights) Act 2006", "anchor": "fra-2006/sec-5-a"},
        {"index": 3, "title": "Mines and Minerals (Development and Regulation) Act 1957", "anchor": "mmdr-1957/sec-10A-b"},
        {"index": 4, "title": "Forest (Conservation) Act 1980", "anchor": "forest-conservation-1980/sec-2"},
        {"index": 5, "title": "Right to Fair Compensation and Transparency in Land Acquisition, Rehabilitation and Resettlement Act 2013", "anchor": "rfctlarr-2013/sec-41-b"},
    ]
    mining_answer = _grounded_joined(mining_query, mining_passages)
    assert "bauxite/mining project or DM NOC" in mining_answer
    assert "MMDR/mining source" in mining_answer
    assert "Gram Sabha notice/minutes/resolution" in mining_answer

    crypto_query = "pls tell guy from telegram crypto group rugpulled me 3 lakh whom to complain need lawyer or police"
    crypto_passages = [
        {"index": 1, "title": "Information Technology Act 2000", "anchor": "it-2000/sec-66D"},
        {"index": 2, "title": "Bharatiya Nyaya Sanhita 2023", "anchor": "bns-2023/sec-319"},
        {"index": 3, "title": "Bharatiya Nagarik Suraksha Sanhita 2023", "anchor": "bnss-2023/sec-175"},
    ]
    crypto_answer = _grounded_joined(crypto_query, crypto_passages)
    assert "Telegram crypto/investment rug-pull" in crypto_answer
    assert "wallet addresses" in crypto_answer
    assert "OTP/UPI fraud" not in crypto_answer

    therapist_query = "pls tell someone leaked my chat with therapist on twitter mental health privacy need lawyer or police"
    therapist_passages = [
        {"index": 1, "title": "Digital Personal Data Protection Act 2023", "anchor": "dpdp-2023/sec-13"},
        {"index": 2, "title": "Mental Healthcare Act 2017", "anchor": "mental-healthcare-2017/sec-43"},
        {"index": 3, "title": "Information Technology Act 2000", "anchor": "it-2000/sec-72"},
    ]
    therapist_answer = _grounded_joined(therapist_query, therapist_passages)
    assert "Mental Healthcare Act confidentiality/privacy" in therapist_answer
    assert "IT Act confidentiality/privacy disclosure source" in therapist_answer
    assert "For a the" not in therapist_answer

    therapist_dpdp_only = common_workflow_contract_result(
        therapist_query,
        route_matter(therapist_query),
        [
            {"index": 1, "title": "Digital Personal Data Protection Act 2023", "anchor": "dpdp-2023/sec-13"},
            {"index": 3, "title": "Information Technology Act 2000", "anchor": "it-2000/sec-66E"},
        ],
    )
    therapist_dpdp_only_answer = _grounded_joined(
        therapist_query,
        [
            {"index": 1, "title": "Digital Personal Data Protection Act 2023", "anchor": "dpdp-2023/sec-13"},
            {"index": 3, "title": "Information Technology Act 2000", "anchor": "it-2000/sec-66E"},
        ],
    )
    assert therapist_dpdp_only is None or therapist_dpdp_only.id not in {"dpdp_data_breach", "cyber_harassment_first_action"}
    assert "DPDP personal-data grievance" not in therapist_dpdp_only_answer
    assert "therapist or mental-health professional" not in therapist_dpdp_only_answer
    assert "online harassment, blackmail, impersonation, or electronic-record abuse" not in therapist_dpdp_only_answer

    therapist_criminal_only = common_workflow_contract_result(
        therapist_query,
        route_matter(therapist_query),
        [
            {"index": 1, "title": "Information Technology Act 2000", "anchor": "it-2000/sec-66E"},
            {"index": 2, "title": "Bharatiya Nyaya Sanhita 2023", "anchor": "bns-2023/sec-356"},
            {"index": 3, "title": "Bharatiya Nagarik Suraksha Sanhita 2023", "anchor": "bnss-2023/sec-173"},
        ],
    )
    assert therapist_criminal_only is None or therapist_criminal_only.id != "cyber_harassment_first_action"

    crypto_variant_query = "crypto wallet transfer fraud 2 lakh telegram group vanished"
    crypto_variant_passages = [
        {"index": 1, "title": "Information Technology Act 2000", "anchor": "it-2000/sec-66D"},
        {"index": 2, "title": "Bharatiya Nyaya Sanhita 2023", "anchor": "bns-2023/sec-319"},
        {"index": 3, "title": "Bharatiya Nagarik Suraksha Sanhita 2023", "anchor": "bnss-2023/sec-175"},
    ]
    crypto_variant_answer = _grounded_joined(crypto_variant_query, crypto_variant_passages)
    assert route_matter(crypto_variant_query).category == "cyber_fraud_or_harassment"
    assert "Telegram crypto/investment rug-pull or wallet-transfer scam" in crypto_variant_answer
    assert "wallet addresses" in crypto_variant_answer

    paytm_wallet_query = "paytm wallet blocked support not replying"
    paytm_wallet_contract = common_workflow_contract_result(
        paytm_wallet_query,
        route_matter(paytm_wallet_query),
        [
            {"index": 1, "title": "Consumer Protection Act 2019", "anchor": "consumer-protection-2019/sec-35"},
            {"index": 2, "title": "Information Technology Act 2000", "anchor": "it-2000/sec-79"},
        ],
    )
    assert paytm_wallet_contract is None or paytm_wallet_contract.id != "crypto_exchange_wallet"

    bauxite_pollution_query = "bauxite mine pollution damaged my house in bastar what compensation"
    bauxite_pollution_common = common_workflow_contract_result(
        bauxite_pollution_query,
        route_matter(bauxite_pollution_query),
        [
            {"index": 1, "title": "Panchayats (Extension to the Scheduled Areas) Act 1996", "anchor": "pesa-1996/sec-4-c"},
            {"index": 2, "title": "Mines and Minerals (Development and Regulation) Act 1957", "anchor": "mmdr-1957/sec-10A-b"},
        ],
    )
    assert bauxite_pollution_common is None or bauxite_pollution_common.id != "mining_gram_sabha_consent_challenge"

    bauxite_pollution_event = authority_graph_workflow_event(
        bauxite_pollution_query,
        route_matter(bauxite_pollution_query),
        [
            {"index": 1, "title": "Right to Fair Compensation and Transparency in Land Acquisition, Rehabilitation and Resettlement Act 2013", "anchor": "rfctlarr-2013/sec-31"},
            {"index": 2, "title": "Panchayats (Extension to the Scheduled Areas) Act 1996", "anchor": "pesa-1996/sec-4-c"},
            {"index": 3, "title": "Mines and Minerals (Development and Regulation) Act 1957", "anchor": "mmdr-1957/sec-10A-b"},
        ],
    )
    assert bauxite_pollution_event is None or bauxite_pollution_event["id"] != "mining_displacement_rehabilitation"

    bumble_blackmail_query = "bumble match blackmailing me with screenshots of chat and threatening upload"
    bumble_blackmail_contract = common_workflow_contract_result(
        bumble_blackmail_query,
        route_matter(bumble_blackmail_query),
        [
            {"index": 1, "title": "Information Technology Act 2000", "anchor": "it-2000/sec-66E"},
            {"index": 2, "title": "Bharatiya Nyaya Sanhita 2023", "anchor": "bns-2023/sec-351"},
            {"index": 3, "title": "Bharatiya Nagarik Suraksha Sanhita 2023", "anchor": "bnss-2023/sec-173"},
        ],
    )
    assert bumble_blackmail_contract is None or bumble_blackmail_contract.id != "unsolicited_sexual_image_cyber"

    for promoted_query, promoted_passages, promoted_id in (
        (forced_sex_query, forced_sex_passages, "family_forced_sex_safety"),
        (laptop_query, laptop_passages, "police_seized_device_return"),
        (poa_delay_query, poa_delay_passages, "poa_special_court_delay"),
        (disabled_baby_query, disabled_baby_passages, "family_disabled_baby_safety"),
        (promise_query, promise_passages, "promise_to_marry_deceitful_intercourse_complaint"),
        (mining_query, mining_passages, "mining_gram_sabha_consent_challenge"),
        (crypto_query, crypto_passages, "cyber_money_fraud"),
        (therapist_query, therapist_passages, "dpdp_data_breach"),
    ):
        promoted = common_workflow_contract_result(promoted_query, route_matter(promoted_query), promoted_passages)
        assert promoted is not None
        assert promoted.id == promoted_id
        assert workflow_contract_promotes_verifier(promoted)


def test_stage_e2_review_fixes_fail_closed_for_weak_sources():
    temple_only_fra_query = "sir thakur family stopped us from entering temple we are dalit where to go"
    temple_only_fra_passages = [
        {"index": 1, "title": "Scheduled Tribes and Other Traditional Forest Dwellers (Recognition of Forest Rights) Act 2006", "anchor": "fra-2006/sec-5"},
        {"index": 2, "title": "Panchayats (Extension to the Scheduled Areas) Act 1996", "anchor": "pesa-1996/sec-4-c"},
    ]
    temple_only_fra = common_workflow_contract_result(
        temple_only_fra_query,
        route_matter(temple_only_fra_query),
        temple_only_fra_passages,
    )
    temple_only_fra_answer = _grounded_joined(temple_only_fra_query, temple_only_fra_passages)
    assert temple_only_fra is None or temple_only_fra.id not in {"caste_public_access_exclusion", "tribal_forest_land_access"}
    assert "Article 17" not in temple_only_fra_answer
    assert "Protection of Civil Rights" not in temple_only_fra_answer
    assert "SC/ST PoA" not in temple_only_fra_answer

    poa_only_bnss_query = "urgent special court POA case pending 5 yrs no judgement aurangabad maharashtra how to complain"
    poa_only_bnss_passages = [
        {"index": 1, "title": "Bharatiya Nagarik Suraksha Sanhita 2023", "anchor": "bnss-2023/sec-173"},
    ]
    poa_only_bnss = common_workflow_contract_result(
        poa_only_bnss_query,
        route_matter(poa_only_bnss_query),
        poa_only_bnss_passages,
    )
    poa_only_bnss_answer = _grounded_joined(poa_only_bnss_query, poa_only_bnss_passages)
    assert poa_only_bnss is None or poa_only_bnss.id != "poa_special_court_delay"
    assert "Special Public Prosecutor" not in poa_only_bnss_answer
    assert "victim/right-to-participate" not in poa_only_bnss_answer
    if poa_only_bnss is not None:
        assert not workflow_contract_promotes_verifier(poa_only_bnss)

    laptop_no_property_query = "my company laptop has been seized by police as part of investigation against my colleague what are my rights"
    laptop_no_property_passages = [
        {"index": 1, "title": "Bharatiya Nagarik Suraksha Sanhita 2023", "anchor": "bnss-2023/sec-173"},
        {"index": 2, "title": "Information Technology Act 2000", "anchor": "it-2000/sec-2-c"},
    ]
    laptop_no_property = common_workflow_contract_result(
        laptop_no_property_query,
        route_matter(laptop_no_property_query),
        laptop_no_property_passages,
    )
    laptop_no_property_answer = _grounded_joined(laptop_no_property_query, laptop_no_property_passages)
    assert laptop_no_property is None or laptop_no_property.id != "police_seized_device_return"
    assert "release/superdari" not in laptop_no_property_answer
    if laptop_no_property is not None:
        assert not workflow_contract_promotes_verifier(laptop_no_property)

    forced_no_pwdva_query = "husband forces me at night even when I say no I am tired or unwell what can i do"
    forced_no_pwdva_passages = [
        {"index": 1, "title": "Family Courts Act 1984", "anchor": "family-courts-1984/sec-7"},
        {"index": 2, "title": "Bharatiya Nyaya Sanhita 2023", "anchor": "bns-2023/sec-351"},
    ]
    forced_no_pwdva = common_workflow_contract_result(
        forced_no_pwdva_query,
        route_matter(forced_no_pwdva_query),
        forced_no_pwdva_passages,
    )
    forced_no_pwdva_answer = _grounded_joined(forced_no_pwdva_query, forced_no_pwdva_passages)
    assert forced_no_pwdva is None or forced_no_pwdva.id != "family_forced_sex_safety"
    assert "Protection Officer/Magistrate" not in forced_no_pwdva_answer
    if forced_no_pwdva is not None:
        assert not workflow_contract_promotes_verifier(forced_no_pwdva)


def test_stage_d_failure_cluster_workflows_own_reviewed_primary_answers():
    cases = [
        (
            "sir data breach at byjus my pan and aadhaar leaked , can i claim compensation under DPDP act where to go",
            [
                {"index": 1, "title": "Digital Personal Data Protection Act 2023", "anchor": "dpdp-2023/sec-8"},
                {"index": 2, "title": "Information Technology Act 2000", "anchor": "it-2000/sec-66C"},
                {"index": 3, "title": "Aadhaar Act 2016", "anchor": "aadhaar-2016/sec-28"},
            ],
            "dpdp_data_breach",
            "primary",
            ("DPDP personal-data grievance", "Data Protection Board", "cyber complaint"),
        ),
        (
            "need help, udyam registered manufacturer buyer crossed 45 days payment delay 22 lakh outstanding jaipur what next",
            [
                {"index": 1, "title": "Micro, Small and Medium Enterprises Development Act 2006", "anchor": "msmed-2006/sec-15"},
                {"index": 2, "title": "Indian Contract Act 1872", "anchor": "indian-contract-1872/sec-37"},
                {"index": 3, "title": "Sale of Goods Act 1930", "anchor": "sale-of-goods-1930/sec-55"},
            ],
            "msme_delayed_payment",
            "primary",
            ("Udyam/MSME registered", "45-day", "MSME Samadhaan"),
        ),
        (
            "hi, supplier delivered defective material now not agreeing refund 18 lakh contract can i file case",
            [
                {"index": 1, "title": "Indian Contract Act 1872", "anchor": "indian-contract-1872/sec-73"},
                {"index": 2, "title": "Sale of Goods Act 1930", "anchor": "sale-of-goods-1930/sec-59"},
                {"index": 3, "title": "Specific Relief Act 1963", "anchor": "specific-relief-1963/sec-38"},
            ],
            "business_contract_first_action",
            "primary",
            ("defective-material", "Sale of Goods", "legal notice"),
        ),
        (
            "hi, court ordered supervised visitation for my daughter but my ex's lawyer is asking unsupervised now I am scared can i file case",
            [
                {"index": 1, "title": "Guardians and Wards Act 1890", "anchor": "guardians-wards-1890/sec-17"},
                {"index": 2, "title": "Family Courts Act 1984", "anchor": "family-courts-1984/sec-7"},
                {"index": 3, "title": "Hindu Minority and Guardianship Act 1956", "anchor": "hindu-minority-guardianship-1956/sec-13"},
            ],
            "child_access",
            "primary",
            ("custody/access", "Family Court", "prior custody order"),
        ),
        (
            "hi, my daughter is 16 her father is fixing marriage with 35 year old man fr money what can I do quickly can i file case",
            [
                {"index": 1, "title": "Prohibition of Child Marriage Act 2006", "anchor": "child-marriage-2006/sec-13"},
                {"index": 2, "title": "Protection of Children from Sexual Offences Act 2012", "anchor": "pocso-2012/sec-19"},
                {"index": 3, "title": "Bharatiya Nagarik Suraksha Sanhita 2023", "anchor": "bnss-2023/sec-173"},
            ],
            "child_marriage_prevention",
            "safety_primary",
            ("child-marriage protection", "1098", "age proof"),
        ),
        (
            "please help I am 6 months pregnant after rape doctor says it is too late fr abortion but I cannot keep this child help any remedy",
            [
                {"index": 1, "title": "Medical Termination of Pregnancy Act 1971", "anchor": "mtp-1971/sec-3"},
                {"index": 2, "title": "Constitution of India", "anchor": "constitution-india/sec-21"},
                {"index": 3, "title": "Protection of Children from Sexual Offences Act 2012", "anchor": "pocso-2012/sec-19"},
            ],
            "mtp_reproductive_rights",
            "safety_primary",
            ("beyond 24 weeks", "registered medical practitioner", "DLSA/One Stop Centre"),
        ),
        (
            "can u tell bf secretly recorded us during sex now threatening to upload bro help what can i do",
            [
                {"index": 1, "title": "Information Technology Act 2000", "anchor": "it-2000/sec-67A"},
                {"index": 2, "title": "Bharatiya Nyaya Sanhita 2023", "anchor": "bns-2023/sec-351"},
                {"index": 3, "title": "Bharatiya Nagarik Suraksha Sanhita 2023", "anchor": "bnss-2023/sec-173"},
            ],
            "intimate_image_blackmail",
            "primary",
            ("non-consensual intimate-image", "Do not pay", "platform URLs"),
        ),
    ]

    for query, passages, expected_id, expected_mode, must_terms in cases:
        route = route_matter(query)
        workflow = common_workflow_contract_result(query, route, passages)
        rendered = _grounded_joined(query, passages)
        assert workflow is not None, query
        assert workflow.id == expected_id, query
        assert workflow.answer_mode == expected_mode, query
        for term in must_terms:
            assert term in rendered, (query, term, rendered)


def test_stage_d_failure_cluster_workflows_fail_closed_without_controlling_sources():
    cases = [
        (
            "byjus leaked my pan and aadhaar in data breach can i claim compensation under dpdp where to go",
            [
                {"index": 1, "title": "Information Technology Act 2000", "anchor": "it-2000/sec-66C"},
                {"index": 2, "title": "Aadhaar Act 2016", "anchor": "aadhaar-2016/sec-28"},
            ],
            "dpdp_data_breach",
            ("Data Protection Board", "DPDP personal-data grievance"),
        ),
        (
            "udyam registered manufacturer buyer crossed 45 days payment delay 22 lakh outstanding jaipur",
            [
                {"index": 1, "title": "Indian Contract Act 1872", "anchor": "indian-contract-1872/sec-37"},
                {"index": 2, "title": "Sale of Goods Act 1930", "anchor": "sale-of-goods-1930/sec-55"},
            ],
            "msme_delayed_payment",
            ("MSME Facilitation Council", "MSMED delayed-payment", "Udyam/MSME registered"),
        ),
        (
            "my daughter is 16 her father is fixing marriage with 35 year old man for money what can i do quickly",
            [
                {"index": 1, "title": "Protection of Children from Sexual Offences Act 2012", "anchor": "pocso-2012/sec-19"},
                {"index": 2, "title": "Bharatiya Nagarik Suraksha Sanhita 2023", "anchor": "bnss-2023/sec-173"},
            ],
            "child_marriage_prevention",
            ("Child Marriage Prohibition Officer", "child-marriage protection"),
        ),
        (
            "i am 6 months pregnant after rape doctor says too late for abortion but i cannot keep child",
            [
                {"index": 1, "title": "Constitution of India", "anchor": "constitution-india/sec-21"},
                {"index": 2, "title": "Protection of Children from Sexual Offences Act 2012", "anchor": "pocso-2012/sec-19"},
            ],
            "mtp_reproductive_rights",
            ("MTP source", "beyond 24 weeks", "medical-board"),
        ),
        (
            "co-founder promised equity but now diluted my shares and not showing company registers where to go",
            [
                {"index": 1, "title": "Indian Contract Act 1872", "anchor": "indian-contract-1872/sec-37"},
                {"index": 2, "title": "Specific Relief Act 1963", "anchor": "specific-relief-1963/sec-38"},
            ],
            "business_contract_first_action",
            ("company equity", "Companies Act route"),
        ),
        (
            "my partner in firm is not showing books and wants me to retire with liability what next",
            [
                {"index": 1, "title": "Indian Contract Act 1872", "anchor": "indian-contract-1872/sec-37"},
                {"index": 2, "title": "Specific Relief Act 1963", "anchor": "specific-relief-1963/sec-38"},
            ],
            "business_contract_first_action",
            ("Partnership Act source", "partnership exit"),
        ),
    ]

    for query, passages, blocked_id, forbidden_terms in cases:
        workflow = common_workflow_contract_result(query, route_matter(query), passages)
        rendered = _grounded_joined(query, passages)
        assert workflow is None or workflow.id != blocked_id, (query, workflow)
        if workflow is not None and workflow.answer_mode in {"primary", "safety_primary"}:
            for term in forbidden_terms:
                assert term not in rendered, (query, workflow, term, rendered)


def test_reviewed_workflow_relevance_override_is_source_gated_and_exact_owner_only():
    query = "what to do ismw registration who does it i never heard about it 15 years in surat textile is this legal"
    passages = [
        {
            "index": 1,
            "title": "Inter-State Migrant Workmen (Regulation of Employment and Conditions of Service) Act 1979",
            "anchor": "ismw-1979/sec-12",
        },
        {
            "index": 2,
            "title": "Code on Wages 2019",
            "anchor": "code-on-wages-2019/sec-45",
        },
    ]
    route = route_matter(query)
    workflow = common_workflow_contract_result(query, route, passages)
    assert workflow is not None
    assert workflow.answer_mode == "primary"
    cosine_false_negative = RelevanceResult(
        score=0.41,
        verdict=RelevanceVerdict.OFF_TOPIC,
        threshold=0.50,
        band=0.08,
    )

    overridden = _reviewed_workflow_relevance_result(
        cosine_false_negative,
        route=route,
        workflow_result=workflow,
        template_lines=workflow.lines,
        source_gap_event=None,
        emitted_citation_indices={1, 2},
    )
    assert overridden is not None
    assert overridden.verdict == RelevanceVerdict.OK
    assert overridden.score == cosine_false_negative.score

    weak_contract = _reviewed_workflow_relevance_result(
        cosine_false_negative,
        route=route,
        workflow_result=workflow,
        template_lines=workflow.lines,
        source_gap_event=None,
        emitted_citation_indices={1, 2},
        sentence_quality_failed=True,
    )
    assert weak_contract is not None
    assert weak_contract.verdict == RelevanceVerdict.OFF_TOPIC

    cosine_ok = RelevanceResult(
        score=0.72,
        verdict=RelevanceVerdict.OK,
        threshold=0.50,
        band=0.08,
    )
    quality_downgraded = _reviewed_workflow_relevance_result(
        cosine_ok,
        route=route,
        workflow_result=workflow,
        template_lines=workflow.lines,
        source_gap_event=None,
        emitted_citation_indices={1, 2},
        sentence_quality_failed=True,
    )
    assert quality_downgraded is not None
    assert quality_downgraded.verdict == RelevanceVerdict.PARTIAL

    no_citations = _reviewed_workflow_relevance_result(
        cosine_false_negative,
        route=route,
        workflow_result=workflow,
        template_lines=workflow.lines,
        source_gap_event=None,
        emitted_citation_indices=set(),
    )
    assert no_citations is not None
    assert no_citations.verdict == RelevanceVerdict.OFF_TOPIC

    visible_source_gap = _reviewed_workflow_relevance_result(
        cosine_false_negative,
        route=route,
        workflow_result=workflow,
        template_lines=workflow.lines,
        source_gap_event={"has_gap": True},
        emitted_citation_indices={1, 2},
    )
    assert visible_source_gap is not None
    assert visible_source_gap.verdict == RelevanceVerdict.OFF_TOPIC

    legacy_shadow = _reviewed_workflow_relevance_result(
        cosine_false_negative,
        route=route,
        workflow_result=workflow,
        template_lines=["legacy line [1]."],
        source_gap_event=None,
        emitted_citation_indices={1},
    )
    assert legacy_shadow is not None
    assert legacy_shadow.verdict == RelevanceVerdict.OFF_TOPIC


def test_registry_owned_bank_evidence_checklist_is_operational_guidance():
    query = "Bank deducted money wrongly and customer care is not helping"
    route = route_matter(query)
    plan = build_matter_plan(query, route)
    assert plan is not None
    header = SentenceVerification(
        text="**What you can do next**",
        status=SentenceStatus.META,
        citations=[],
        entailment_score=None,
        reason="meta line",
        auto_cited=False,
    )
    checklist = SentenceVerification(
        text="- Keep the bank statement entry, UPI/transaction ID/RRN, alerts, customer-care messages or call logs, complaint number, reply or no-reply proof, and debit/refund timeline.",
        status=SentenceStatus.UNSUPPORTED,
        citations=[],
        entailment_score=None,
        reason="operational checklist",
        auto_cited=False,
    )

    promoted = _promote_safe_route_next_step(checklist, route, header, plan)

    assert promoted.status == SentenceStatus.GUIDANCE
    assert promoted.citations == []


def test_ismw_registration_uses_narrow_source_gated_legacy_owner_not_labour_fallback():
    registration_query = "what to do ismw registration who does it i never heard about it 15 years in surat textile is this legal"
    registration_passages = [
        {
            "index": 1,
            "title": "Inter-State Migrant Workmen (Regulation of Employment and Conditions of Service) Act 1979",
            "anchor": "ismw-1979/sec-4",
        },
        {
            "index": 2,
            "title": "Inter-State Migrant Workmen (Regulation of Employment and Conditions of Service) Act 1979",
            "anchor": "ismw-1979/sec-12",
        },
    ]
    registration_route = route_matter(registration_query)
    registration_lines = _grounded_template_lines(registration_query, registration_route, registration_passages)
    registration_event = _workflow_event_payload(registration_query, registration_passages, registration_lines)

    assert "Surat textile work" in " ".join(registration_lines)
    assert registration_event["answer_owner"] == "legacy_grounded_template"
    assert registration_event["workflow_shadowed_by_legacy"] is True
    assert registration_event["shadowed_workflow_id"] == "labour_exploitation_first_action"

    weak_source_passages = [
        {
            "index": 1,
            "title": "Inter-State Migrant Workmen Act 1979",
            "anchor": "ismw-1979/sec-15",
        },
    ]
    weak_workflow = common_workflow_contract_result(registration_query, registration_route, weak_source_passages)
    weak_lines = _grounded_template_lines(registration_query, registration_route, weak_source_passages)
    weak_event = _workflow_event_payload(registration_query, weak_source_passages, weak_lines)

    assert weak_workflow is not None
    assert weak_workflow.id == "labour_exploitation_first_action"
    assert weak_lines == weak_workflow.lines
    assert weak_event["answer_owner"] == "common_workflow_contracts"
    assert weak_event["workflow_shadowed_by_legacy"] is False


def test_caste_public_access_workflow_preserves_temple_fact_without_inventing_it():
    passages = [
        {"index": 1, "title": "Constitution of India", "anchor": "constitution-india/sec-17"},
        {"index": 2, "title": "Protection of Civil Rights Act 1955", "anchor": "protection-civil-rights-1955/sec-3"},
    ]
    temple_query = "thakur family stopped us from entering temple we are dalit"
    temple_answer = _grounded_joined(temple_query, passages)
    shop_query = "dalit family was refused tea at a shop because of caste"
    shop_answer = _grounded_joined(shop_query, passages)

    assert "Thakur family stopped Dalit persons from entering a temple" in temple_answer
    assert "temple-entry/untouchability complaint" in temple_answer
    assert "Thakur family" not in shop_answer
    assert "entering a temple" not in shop_answer


def test_labour_subtype_owner_requires_the_controlling_source_and_specific_facts():
    wage_query = "came from supaul bihar to mumbai 6 months no payment munshi keeps saying next week"
    wage_passages = [
        {"index": 1, "title": "Code on Wages 2019", "anchor": "code-on-wages-2019/sec-17"},
        {"index": 2, "title": "Code on Wages 2019", "anchor": "code-on-wages-2019/sec-45"},
        {"index": 3, "title": "Inter-State Migrant Workmen Act 1979", "anchor": "ismw-1979/sec-12"},
    ]
    wage_route = route_matter(wage_query)
    wage_lines = _grounded_template_lines(wage_query, wage_route, wage_passages)
    wage_event = _workflow_event_payload(wage_query, wage_passages, wage_lines)

    assert "migrant-worker wage dispute" in " ".join(wage_lines)
    assert wage_event["answer_owner"] == "legacy_grounded_template"
    assert wage_event["shadowed_workflow_id"] == "labour_exploitation_first_action"

    weak_passages = [
        {"index": 1, "title": "Code on Wages 2019", "anchor": "code-on-wages-2019/sec-1"},
    ]
    weak_lines = _grounded_template_lines(wage_query, wage_route, weak_passages)
    weak_event = _workflow_event_payload(wage_query, weak_passages, weak_lines)

    assert weak_lines == []
    assert weak_event["answer_owner"] == "llm"
    assert weak_event["workflow_shadowed_by_legacy"] is False


def test_mgnrega_authority_contract_keeps_explicit_work_days_and_social_audit_source():
    query = "nrega 28 days work done village mukhiya not paid since 6 months"
    passages = [
        {"index": 1, "title": "Mahatma Gandhi National Rural Employment Guarantee Act 2005", "anchor": "mgnrega-2005/sec-19"},
        {"index": 2, "title": "Mahatma Gandhi National Rural Employment Guarantee Act 2005", "anchor": "mgnrega-2005/sec-17"},
    ]
    answer = _grounded_joined(query, passages)

    assert _workflow_id(query, passages) == "mgnrega_fake_muster"
    assert "28 days of NREGA work" in answer
    assert "grievance-redressal route [1]" in answer
    assert "social-audit source" in answer and "[2]" in answer


def test_answer_floor_uses_incident_date_not_reporting_year_for_criminal_regime():
    from apps.api.main import _answer_contract_lines

    query = "reported in 2025, but someone made a deepfake in June 2024 and is extorting me"
    passages = [
        {"index": 1, "title": "Information Technology Act 2000", "statute_short": "Information Technology Act 2000", "anchor": "it-2000/sec-66e", "source_type": "bare_act", "required_source_pack": "it_act_2000"},
        {"index": 2, "title": "Bharatiya Nyaya Sanhita 2023", "statute_short": "BNS 2023", "anchor": "bns-2023/sec-308", "source_type": "bare_act", "required_source_pack": "bns_2023"},
        {"index": 3, "title": "Bharatiya Nagarik Suraksha Sanhita 2023", "statute_short": "BNSS 2023", "anchor": "bnss-2023/sec-173", "source_type": "bare_act", "required_source_pack": "bnss_2023"},
        {"index": 4, "title": "Indian Penal Code 1860", "statute_short": "IPC 1860", "anchor": "ipc-1860/sec-384", "source_type": "bare_act", "required_source_pack": "ipc_1860"},
        {"index": 5, "title": "Code of Criminal Procedure 1973", "statute_short": "CrPC 1973", "anchor": "crpc-1973/sec-154", "source_type": "bare_act", "required_source_pack": "crpc_1973"},
    ]
    state = {
        "emitted_citation_indices": {1},
        "seen_sentences": set(),
        "saw_next_step_sentence": True,
        "saw_next_step_header": True,
        "emitted": 3,
    }
    answer = " ".join(_answer_contract_lines(route_matter(query), passages, state, query=query))

    assert "Indian Penal Code 1860" in answer and "[4]" in answer
    assert "Code of Criminal Procedure 1973" in answer and "[5]" in answer
    assert "Bharatiya Nyaya Sanhita" not in answer
    assert "Bharatiya Nagarik Suraksha" not in answer


def test_stage_e7_spousal_property_return_gets_neutral_reviewed_workflow():
    query = "my wife took my gold and left house"
    route = route_matter(query)
    passages = [
        {"index": 1, "title": "Family Courts Act 1984", "anchor": "family-courts-1984/sec-7"},
        {"index": 2, "title": "Bharatiya Nyaya Sanhita 2023", "anchor": "bns-2023/sec-316"},
        {"index": 3, "title": "Bharatiya Nagarik Suraksha Sanhita 2023", "anchor": "bnss-2023/sec-173"},
    ]

    workflow = common_workflow_contract_result(query, route, passages)
    assert workflow is not None
    assert workflow.id == "spousal_property_return"
    assert workflow.answer_mode == "primary"
    rendered = " ".join(workflow.lines)
    assert "spousal property-return" in rendered
    assert "do not label every spouse property dispute as a criminal case automatically" in rendered
    assert "item-wise list" in rendered


def test_stage_e7_domestic_violence_notice_response_gets_reviewed_workflow():
    query = "wife filed domestic violence case, no FIR just notice reply"
    route = route_matter(query)
    passages = [
        {"index": 1, "title": "Protection of Women from Domestic Violence Act 2005", "anchor": "domestic-violence-2005/sec-12"},
        {"index": 2, "title": "Family Courts Act 1984", "anchor": "family-courts-1984/sec-7"},
    ]

    workflow = common_workflow_contract_result(query, route, passages)
    assert workflow is not None
    assert workflow.id == "family_notice_response"
    assert workflow.answer_mode == "primary"
    rendered = " ".join(workflow.lines)
    assert "domestic-violence notice-response first" in rendered
    assert "do not assume every DV notice is automatically an FIR case" in rendered

    served_query = "wife filed domestic violence case and police complaint also sent me notice"
    served_workflow = common_workflow_contract_result(served_query, route_matter(served_query), passages)
    assert served_workflow is not None
    assert served_workflow.id == "family_notice_response"

    no_arrest_query = "wife filed domestic violence case no arrest notice only summons what do i reply"
    no_arrest_workflow = common_workflow_contract_result(no_arrest_query, route_matter(no_arrest_query), passages)
    assert no_arrest_workflow is not None
    assert no_arrest_workflow.id == "family_notice_response"

    no_police_query = "wife filed domestic violence case no police notice only court summons what do i reply"
    no_police_workflow = common_workflow_contract_result(no_police_query, route_matter(no_police_query), passages)
    assert no_police_workflow is not None
    assert no_police_workflow.id == "family_notice_response"


def test_stage_e7_hidden_orientation_misrepresentation_gets_reviewed_workflow():
    query = "i am hindu my husband is gay and hidden before marriage what can i do"
    route = route_matter(query)
    passages = [
        {"index": 1, "title": "Hindu Marriage Act 1955", "anchor": "hindu-marriage-1955/sec-12"},
        {"index": 2, "title": "Family Courts Act 1984", "anchor": "family-courts-1984/sec-7"},
    ]

    workflow = common_workflow_contract_result(query, route, passages)
    assert workflow is not None
    assert workflow.id == "marriage_misrepresentation_voidable"
    assert workflow.answer_mode == "primary"
    rendered = " ".join(workflow.lines)
    assert "hidden sexual-orientation" in rendered
    assert "not every lie automatically cancels a marriage" in rendered
    assert "not every nondisclosure automatically cancels a marriage" in rendered
    assert "privacy-preserving" in rendered


def test_stage_e7_domestic_residence_gets_reviewed_safety_workflow():
    query = "husband throws me out but house in mother in law name"
    route = route_matter(query)
    passages = [
        {"index": 1, "title": "Protection of Women from Domestic Violence Act 2005", "anchor": "domestic-violence-2005/sec-17"},
        {"index": 2, "title": "Protection of Women from Domestic Violence Act 2005", "anchor": "domestic-violence-2005/sec-19"},
        {"index": 3, "title": "Family Courts Act 1984", "anchor": "family-courts-1984/sec-7"},
    ]

    workflow = common_workflow_contract_result(query, route, passages)
    assert workflow is not None
    assert workflow.id == "domestic_residence_right"
    assert workflow.answer_mode == "safety_primary"
    rendered = " ".join(workflow.lines)
    assert "PWDVA residence/protection problem" in rendered
    assert "self-help lock-breaking" in rendered
    assert "Do not rely on force" in rendered


def test_stage_e9g_answer_layer_cites_required_precedents_and_controls_common_routes():
    pmla_query = "pmla case ED filed twin condition kya hai how to argue not guilty what next"
    pmla = common_workflow_contract_result(
        pmla_query,
        route_matter(pmla_query),
        [
            {"index": 1, "title": "Prevention of Money Laundering Act 2002", "anchor": "pmla-2002/sec-45"},
            {"index": 2, "title": "Bharatiya Nagarik Suraksha Sanhita 2023", "anchor": "bnss-2023/sec-483@2024-07-01"},
            {"index": 3, "title": "NIKESH TARACHAND SHAH versus UNION OF INDIA & ANR.", "anchor": "2017-insc-1137#header"},
        ],
    )
    assert pmla is not None
    assert pmla.id == "pmla_anticipatory_interim_bail"
    pmla_rendered = " ".join(pmla.lines)
    assert "Supreme Court PMLA bail/arrest precedent" in pmla_rendered
    assert "[3]" in pmla_rendered

    mtp_query = "had abortion 5 yrs back husband found out and is threatening divorce can he use this against me in court"
    mtp = common_workflow_contract_result(
        mtp_query,
        route_matter(mtp_query),
        [
            {"index": 1, "title": "Constitution of India", "anchor": "constitution-india/sec-21__3"},
            {"index": 2, "title": "Hindu Marriage Act 1955", "anchor": "hindu-marriage-1955/sec-13-d@2026-04-15"},
            {"index": 5, "title": "MS. Z  versus THE STATE OF BIHAR AND OTHERS", "anchor": "2017-insc-756#header"},
            {"index": 6, "title": "Medical Termination of Pregnancy Act 1971", "anchor": "mtp-1971/sec-3-b@2021-01-01"},
        ],
    )
    assert mtp is not None
    assert mtp.id == "mtp_reproductive_rights"
    mtp_rendered = " ".join(mtp.lines)
    assert "Supreme Court reproductive-autonomy/privacy precedent" in mtp_rendered
    assert "family-law/divorce source" in mtp_rendered
    assert "[2]" in mtp_rendered
    assert "[5]" in mtp_rendered

    spa_query = "I work at a place in malad they call it spa but customers want extra and owner makes us do it if we refuse no salary how do I get out"
    spa = common_workflow_contract_result(
        spa_query,
        route_matter(spa_query),
        [
            {"index": 1, "title": "Bharatiya Nyaya Sanhita 2023", "anchor": "bns-2023/sec-146@2024-07-01"},
            {"index": 4, "title": "Immoral Traffic (Prevention) Act 1956", "anchor": "itpa-1956/sec-8"},
            {"index": 6, "title": "Bharatiya Nagarik Suraksha Sanhita 2023", "anchor": "bnss-2023/sec-173-b@2024-07-01"},
        ],
    )
    assert spa is not None
    assert spa.id == "forced_sexual_exploitation_victim"
    spa_rendered = " ".join(spa.lines)
    assert "not as an ordinary wage complaint" in spa_rendered
    assert "not the exact rescue provision" in spa_rendered
    assert "[1]" in spa_rendered and "[4]" in spa_rendered and "[6]" in spa_rendered

    writ_query = "urgent difference between Article 32 Supreme Court and Article 226 High Court writ how to complain"
    writ = common_workflow_contract_result(
        writ_query,
        route_matter(writ_query),
        [
            {"index": 1, "title": "Constitution of India", "anchor": "constitution-india/sec-32"},
            {"index": 2, "title": "Constitution of India", "anchor": "constitution-india/sec-226"},
            {"index": 3, "title": "Legal Services Authorities Act 1987", "anchor": "legal-services-authorities-1987/sec-12"},
        ],
    )
    assert writ is not None
    assert writ.id == "procedure_writ_32_226_difference"
    writ_rendered = " ".join(writ.lines)
    assert "Article 32 is the Supreme Court procedure" in writ_rendered
    assert "Article 226 is the High Court writ route" in writ_rendered
    assert "[1]" in writ_rendered and "[2]" in writ_rendered

    acid_query = "auto driver threw something on my face on the road my eyes are burning hospital said acid what to do"
    acid = common_workflow_contract_result(
        acid_query,
        route_matter(acid_query),
        [
            {"index": 1, "title": "Bharatiya Nyaya Sanhita 2023", "anchor": "bns-2023/sec-124@2024-07-01"},
            {"index": 5, "title": "Bharatiya Nagarik Suraksha Sanhita 2023", "anchor": "bnss-2023/sec-173-b@2024-07-01"},
        ],
    )
    assert acid is not None
    assert acid.id == "acid_chemical_attack_first_response"
    acid_rendered = " ".join(acid.lines)
    assert "emergency acid-attack/hurt track" in acid_rendered
    assert "hospital/emergency care first" in acid_rendered

    hospital_query = "hospital in chennai operated wrong leg on my 80 yr old father how to file case need lawyer or police"
    hospital = common_workflow_contract_result(
        hospital_query,
        route_matter(hospital_query),
        [
            {"index": 1, "title": "Code of Medical Ethics Regulations 2002", "anchor": "medical-ethics-regulations-2002/reg-7.2"},
            {"index": 2, "title": "Bharatiya Nyaya Sanhita 2023", "anchor": "bns-2023/sec-106@2024-07-01"},
            {"index": 3, "title": "Bharatiya Nagarik Suraksha Sanhita 2023", "anchor": "bnss-2023/sec-173-b@2024-07-01"},
            {"index": 8, "title": "Consumer Protection Act 2019", "anchor": "consumer-protection-2019/sec-35@2021-09-17"},
        ],
    )
    assert hospital is not None
    assert hospital.id == "hospital_records_billing"
    hospital_rendered = " ".join(hospital.lines)
    assert "wrong-leg or wrong-site surgery/operation complaint" in hospital_rendered
    assert "police/criminal negligence" in hospital_rendered

    ip_query = "urgent interim injunction needed competitor passing off my product packaging can i skip 12A can i file case"
    ip = common_workflow_contract_result(
        ip_query,
        route_matter(ip_query),
        [
            {"index": 2, "title": "Trade Marks Act 1999", "anchor": "trade-marks-1999/sec-134"},
            {"index": 4, "title": "Commercial Courts Act 2015", "anchor": "commercial-courts-2015/sec-12A"},
            {"index": 6, "title": "Specific Relief Act 1963", "anchor": "specific-relief-1963/sec-38"},
        ],
    )
    assert ip is not None
    assert ip.id == "trademark_passing_off_interim_injunction"
    ip_rendered = " ".join(ip.lines)
    assert "urgent-interim-relief exception" in ip_rendered
    assert "Specific Relief Act" in ip_rendered
    assert "[4]" in ip_rendered and "[6]" in ip_rendered


def test_criminal_specialist_contracts_require_controlling_sources():
    pregnant_query = "paralegal volunteer 4 women undertrials byculla pregnant where rule postpone trial bail"
    pregnant_sources = [
        {"index": 1, "title": "Constitution of India", "anchor": "constitution-india/sec-21"},
        {"index": 2, "title": "Bharatiya Nagarik Suraksha Sanhita 2023", "anchor": "bnss-2023/sec-480-a"},
    ]
    pregnant = common_workflow_contract_result(
        pregnant_query,
        route_matter(pregnant_query),
        pregnant_sources,
    )
    assert pregnant is not None
    assert pregnant.id == "pregnant_undertrial_medical_bail"
    assert "woman, sick, or infirm" in " ".join(pregnant.lines)
    assert _workflow_id(pregnant_query, pregnant_sources[:-1]) != "pregnant_undertrial_medical_bail"

    receptionist_query = "I was arrested in a parlour raid; I was only a receptionist, not involved in anything else"
    receptionist_sources = [
        {"index": 1, "title": "Immoral Traffic (Prevention) Act 1956", "anchor": "itpa-1956/sec-5"},
        {"index": 2, "title": "Immoral Traffic (Prevention) Act 1956", "anchor": "itpa-1956/sec-8"},
        {"index": 3, "title": "Bharatiya Nagarik Suraksha Sanhita 2023", "anchor": "bnss-2023/sec-483"},
        {"index": 4, "title": "Bharatiya Nagarik Suraksha Sanhita 2023", "anchor": "bnss-2023/sec-216"},
    ]
    receptionist = common_workflow_contract_result(
        receptionist_query,
        route_matter(receptionist_query),
        receptionist_sources,
    )
    assert receptionist is not None
    assert receptionist.id == "itpa_receptionist_raid_accused"
    rendered = " ".join(receptionist.lines)
    assert "reception-desk work" in rendered
    assert "[1]" in rendered and "[2]" in rendered and "[3]" in rendered and "[4]" in rendered
    assert _workflow_id(receptionist_query, receptionist_sources[1:]) != "itpa_receptionist_raid_accused"

    bail_query = "husband arrested 498a anticipatory bail filed sessions court rejected what next high court"
    bail_sources = [
        {"index": 3, "title": "Bharatiya Nagarik Suraksha Sanhita 2023", "anchor": "bnss-2023/sec-480-a"},
        {"index": 4, "title": "Bharatiya Nyaya Sanhita 2023", "anchor": "bns-2023/sec-85"},
    ]
    bail = common_workflow_contract_result(bail_query, route_matter(bail_query), bail_sources)
    assert bail is not None
    assert bail.id == "498a_bail_rejection_source_gap"
    assert "do not include the specific anticipatory-bail provision" in " ".join(bail.lines)
    assert _workflow_id(bail_query, bail_sources[:1]) != "498a_bail_rejection_source_gap"


def test_civil_procedure_authority_contracts_are_section_gated_and_user_shaped():
    cases = [
        (
            "what to do is pre-litigation mediation mandatory before filing commercial suit is this legal",
            [
                {"index": 1, "title": "Commercial Courts Act 2015", "anchor": "commercial-courts-2015/sec-12A"},
                {"index": 2, "title": "Mediation Act 2023", "anchor": "mediation-2023/sec-5"},
            ],
            "commercial_preinstitution_mediation",
            "urgent interim relief",
        ),
        (
            "what to do how to initiate mediation under Mediation Act 2023 without going to court is this legal",
            [
                {"index": 1, "title": "Mediation Act 2023", "anchor": "mediation-2023/sec-5"},
                {"index": 2, "title": "Legal Services Authorities Act 1987", "anchor": "legal-services-authorities-1987/sec-12"},
            ],
            "voluntary_preinstitution_mediation",
            "before a suit",
        ),
        (
            "sir second appeal high court substantial question of law procedure where to go",
            [
                {"index": 1, "title": "Code of Civil Procedure 1908", "anchor": "cpc-1908/sec-100"},
                {"index": 2, "title": "Limitation Act 1963", "anchor": "limitation-1963/sec-5"},
            ],
            "civil_second_appeal_substantial_question",
            "substantial question of law",
        ),
        (
            "sir condonation of delay application section 5 limitation what grounds work where to go",
            [
                {"index": 1, "title": "Limitation Act 1963", "anchor": "limitation-1963/sec-5"},
                {"index": 2, "title": "Code of Civil Procedure 1908", "anchor": "cpc-1908/sec-151"},
            ],
            "limitation_delay_condonation",
            "sufficient cause",
        ),
        (
            "sir how to apply for transfer of case from one district court to another where to go",
            [{"index": 1, "title": "Code of Civil Procedure 1908", "anchor": "cpc-1908/sec-24"}],
            "civil_case_transfer",
            "transfer/withdrawal power",
        ),
    ]

    for query, passages, workflow_id, expected_text in cases:
        result = common_workflow_contract_result(query, route_matter(query), passages)
        assert result is not None
        assert result.id == workflow_id
        assert result.source == "authority_graph"
        assert result.answer_mode == "primary"
        assert expected_text in " ".join(result.lines)
        assert "[1]" in " ".join(result.lines)

    missing = common_workflow_contract_result(
        "sir second appeal high court substantial question of law procedure where to go",
        route_matter("sir second appeal high court substantial question of law procedure where to go"),
        [{"index": 1, "title": "Limitation Act 1963", "anchor": "limitation-1963/sec-5"}],
    )
    assert missing is None or missing.id != "civil_second_appeal_substantial_question"


def test_welfare_identity_contracts_separate_correction_from_rti_and_state_certificate_rules():
    aadhaar_query = "aadhaar number showing someone else photo cannot get pension help any remedy"
    aadhaar = common_workflow_contract_result(
        aadhaar_query,
        route_matter(aadhaar_query),
        [
            {"index": 1, "title": "Aadhaar (Targeted Delivery of Financial and Other Subsidies, Benefits and Services) Act 2016", "anchor": "aadhaar-2016/sec-31"},
            {"index": 2, "title": "Right to Information Act 2005", "anchor": "rti-2005/sec-6"},
            {"index": 3, "title": "National Social Assistance Programme Guidelines 2014", "anchor": "nsap-guidelines-2014/sec-3__2-c"},
        ],
    )
    assert aadhaar is not None
    assert aadhaar.id == "aadhaar_identity_record_correction_pension"
    aadhaar_text = " ".join(aadhaar.lines)
    assert "Do not use an RTI application or RTI appeal as the Aadhaar correction application" in aadhaar_text
    assert "Section 31" in aadhaar_text

    caste_query = "urgent sT cert not issued by tehsildar 8 mnths daughter exam form rejected jharkhand how to complain"
    caste = common_workflow_contract_result(
        caste_query,
        route_matter(caste_query),
        [
            {"index": 1, "title": "Constitution of India", "anchor": "constitution-india/sec-342"},
            {"index": 2, "title": "Right to Information Act 2005", "anchor": "rti-2005/sec-6"},
        ],
    )
    assert caste is not None
    assert caste.id == "caste_certificate_state_rule_intake"
    caste_text = " ".join(caste.lines)
    assert "Do not file an RTI appeal as though it overturns the certificate decision" in caste_text
    assert "State-rule dependent" in caste_text


def test_only_reviewed_common_workflows_preempt_legacy_specialists():
    generic_common = WorkflowTemplateResult(
        id="unreviewed_common_workflow",
        source="common_workflow_contracts",
        lines=["generic first-action workflow"],
        answer_mode="primary",
    )
    reviewed_common = WorkflowTemplateResult(
        id="online_defamation_abuse",
        source="common_workflow_contracts",
        lines=["reviewed common workflow"],
        answer_mode="primary",
    )
    authority = WorkflowTemplateResult(
        id="arrest_magistrate_production_delay",
        source="authority_graph",
        lines=["source-gated authority workflow"],
        answer_mode="primary",
    )
    safety = WorkflowTemplateResult(
        id="domestic_residence_right",
        source="common_workflow_contracts",
        lines=["safety workflow"],
        answer_mode="safety_primary",
    )
    external_primary = WorkflowTemplateResult(
        id="external_primary_contract",
        source="reviewed_integration",
        lines=["external reviewed workflow"],
        answer_mode="primary",
    )

    assert not workflow_contract_preempts_legacy(generic_common)
    assert workflow_contract_preempts_legacy(reviewed_common)
    assert workflow_contract_preempts_legacy(authority)
    assert workflow_contract_preempts_legacy(safety)
    assert workflow_contract_preempts_legacy(external_primary)
