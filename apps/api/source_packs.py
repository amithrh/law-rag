"""Route-aware authoritative source packs.

The matter router knows what legal bucket a lay query belongs to. These
packs turn that signal into exact document-title searches for Acts already
present in the corpus, so retrieval gets a chance to cite the operative
law even when dense/BM25/rerank prefer a judgment.

Important: packs only reference sources we have verified are indexed in
the current local corpus. Missing Acts stay missing; the coverage gate
should still fail closed instead of inventing authority.
"""
from __future__ import annotations

from dataclasses import dataclass

from .matter_router import MatterRoute


@dataclass(frozen=True)
class SourcePack:
    id: str
    title_patterns: tuple[str, ...]
    search_query: str
    doc_ids: tuple[str, ...] = ()
    anchor_patterns: tuple[str, ...] = ()
    source_types: tuple[str, ...] = ("bare_act",)
    priority: float = 1.0


def source_packs_for_route(route: MatterRoute, query: str) -> list[SourcePack]:
    """Return exact-source packs for a routed query.

    Order matters: earlier packs are more likely to survive the bounded
    rerank candidate window when a category has multiple authoritative
    sources.
    """
    q = query.lower()
    category = route.category
    packs: list[SourcePack] = []

    if category == "tribal_caste_atrocity":
        if _has_any(q, ("dalit", "caste", "sc ", "st ", "scheduled caste", "scheduled tribe", "atrocity", "thakur", "pahan", "sarna", "adivasi")):
            packs.append(SourcePack(
                id="scst_poa_1989",
                title_patterns=(
                    "Scheduled Castes and Scheduled Tribes (Prevention of Atrocities) Act 1989",
                    "Prevention of Atrocities Act 1989",
                ),
                search_query="Scheduled Castes Scheduled Tribes Prevention of Atrocities Act 1989 section 3 offence atrocity",
                doc_ids=("sc-st-poa-1989",),
            ))

    elif category == "family_domestic":
        packs.append(SourcePack(
            id="pwdva_2005",
            title_patterns=("Protection of Women from Domestic Violence Act 2005",),
            search_query="Protection of Women from Domestic Violence Act 2005 section 12 protection residence maintenance",
            doc_ids=("domestic-violence-2005",),
        ))

    elif category == "senior_citizen":
        packs.append(SourcePack(
            id="senior_citizens_2007",
            title_patterns=("Maintenance and Welfare of Parents and Senior Citizens Act 2007",),
            search_query="Maintenance and Welfare of Parents and Senior Citizens Act 2007 section 4 section 23 maintenance tribunal transfer property",
            doc_ids=("mwp-2007", "senior-citizens-2007"),
        ))

    elif category == "cyber_fraud_or_harassment":
        packs.append(SourcePack(
            id="it_act_2000",
            title_patterns=("Information Technology Act 2000",),
            search_query="Information Technology Act 2000 section 66C 66D 66E 67 cyber fraud intimate image",
            doc_ids=("it-2000",),
        ))

    elif category == "consumer":
        packs.append(SourcePack(
            id="consumer_protection_2019",
            title_patterns=("Consumer Protection Act 2019",),
            search_query="Consumer Protection Act 2019 deficiency goods service refund complaint district commission",
            doc_ids=("consumer-protection-2019",),
        ))

    elif category == "reproductive_rights_mtp":
        packs.append(SourcePack(
            id="mtp_1971",
            title_patterns=("Medical Termination of Pregnancy Act 1971",),
            search_query="Medical Termination of Pregnancy Act 1971 termination pregnancy rape survivor medical board",
            doc_ids=("mtp-1971",),
        ))

    elif category == "ibc_nclt":
        packs.append(SourcePack(
            id="ibc_2016",
            title_patterns=("Insolvency and Bankruptcy Code 2016",),
            search_query="Insolvency and Bankruptcy Code 2016 section 7 section 9 operational creditor demand notice",
            doc_ids=("ibc-2016",),
        ))

    elif category == "cheque_bounce":
        packs.append(SourcePack(
            id="ni_act_1881",
            title_patterns=("Negotiable Instruments Act 1881",),
            search_query="Negotiable Instruments Act 1881 section 138 section 142 cheque dishonour complaint limitation",
            doc_ids=("negotiable-instruments-1881",),
        ))

    elif category == "tax_gst_compliance":
        if _has_any(q, ("gst", "cgst", "gstr", "register gst")):
            packs.append(SourcePack(
                id="cgst_2017",
                title_patterns=("Central Goods and Services Tax Act 2017",),
                search_query="Central Goods and Services Tax Act 2017 section 22 registration threshold supply service",
                doc_ids=("cgst-2017",),
            ))

    elif category == "trademark_ip":
        if _has_any(q, ("copyright", "song", "video", "script", "software", "unlicensed")):
            packs.append(SourcePack(
                id="copyright_1957",
                title_patterns=("Copyright Act 1957",),
                search_query="Copyright Act 1957 infringement section 51 section 52 remedies original work",
                doc_ids=("copyright-1957",),
            ))

    elif category == "education_rights":
        packs.append(SourcePack(
            id="rte_2009",
            title_patterns=("Right of Children to Free and Compulsory Education Act 2009",),
            search_query="Right of Children to Free and Compulsory Education Act 2009 admission transfer certificate section 12",
            doc_ids=("rte-2009",),
        ))

    elif category == "mental_health_care_rights":
        packs.append(SourcePack(
            id="mental_healthcare_2017",
            title_patterns=("Mental Healthcare Act 2017",),
            search_query="Mental Healthcare Act 2017 supported admission rights safeguards mental health review board",
            doc_ids=("mental-healthcare-2017",),
        ))

    elif category == "workplace_injury_compensation":
        packs.append(SourcePack(
            id="factories_1948",
            title_patterns=("Factories Act 1948",),
            search_query="Factories Act 1948 safety accident injury occupier inspector worker",
            doc_ids=("factories-1948",),
        ))

    elif category == "employment_wages":
        if _has_any(q, ("pf", "epf", "provident")):
            packs.append(SourcePack(
                id="epf_1952",
                title_patterns=("Employees Provident Funds and Miscellaneous Provisions Act 1952",),
                search_query="Employees Provident Funds and Miscellaneous Provisions Act 1952 provident fund contribution withdrawal employer default",
                doc_ids=("epf-1952",),
            ))
            packs.append(SourcePack(
                id="social_security_code_2020",
                title_patterns=("Code on Social Security 2020",),
                search_query="Code on Social Security 2020 provident fund employee social security contribution",
                doc_ids=("social-security-code-2020",),
                priority=0.9,
            ))
        if "gratuity" in q:
            packs.append(SourcePack(
                id="gratuity_1972",
                title_patterns=("Payment of Gratuity Act 1972",),
                search_query="Payment of Gratuity Act 1972 section 7 section 8 delayed gratuity interest",
                doc_ids=("gratuity-1972",),
            ))
        if _has_any(q, ("termination", "fired", "retrenchment", "labour court")):
            packs.append(SourcePack(
                id="industrial_disputes_1947",
                title_patterns=("Industrial Disputes Act 1947",),
                search_query="Industrial Disputes Act 1947 section 25F retrenchment labour court termination",
                doc_ids=("industrial-disputes-1947",),
            ))
        if "maternity" in q:
            packs.append(SourcePack(
                id="maternity_benefit_1961",
                title_patterns=("Maternity Benefit Act 1961",),
                search_query="Maternity Benefit Act 1961 section 5 section 12 maternity leave dismissal",
                doc_ids=("maternity-benefit-1961",),
            ))
        if _has_any(q, ("salary", "wages", "minimum wage", "overtime", "contractor")):
            packs.append(SourcePack(
                id="code_on_wages_2019",
                title_patterns=("Code on Wages 2019",),
                search_query="Code on Wages 2019 minimum wages payment of wages overtime contractor employee",
                doc_ids=("code-on-wages-2019",),
            ))

    elif category == "labour_exploitation_discrimination":
        if _has_any(q, ("wage", "wages", "salary", "half pay", "contractor", "minimum")):
            packs.append(SourcePack(
                id="code_on_wages_2019",
                title_patterns=("Code on Wages 2019",),
                search_query="Code on Wages 2019 minimum wages payment of wages contractor employee",
                doc_ids=("code-on-wages-2019",),
            ))

    elif category == "social_welfare_identity":
        if _has_any(q, ("aadhaar", "aadhar", "identity", "authentication", "biometric")):
            packs.append(SourcePack(
                id="aadhaar_2016",
                title_patterns=(
                    "Aadhaar (Targeted Delivery of Financial and Other Subsidies, Benefits and Services) Act 2016",
                ),
                search_query="Aadhaar Act 2016 authentication identity subsidy benefit grievance",
                doc_ids=("aadhaar-2016",),
            ))
        if _has_any(q, ("reason", "status", "reply", "information", "rejected", "pending")):
            packs.append(_rti_pack())

    elif category == "rti":
        packs.append(_rti_pack())

    elif category in {"police_fir", "criminal_defence_bail", "custody_compensation", "criminal_general"}:
        if not _uses_legacy_criminal_regime(route):
            packs.append(_bnss_pack(q))
            if _has_any(q, ("theft", "rape", "cheating", "420", "assault", "threat", "hurt", "murder")):
                packs.append(_bns_pack(q))

    elif category == "sexual_offence_survivor":
        if not _uses_legacy_criminal_regime(route):
            packs.append(_bnss_pack(q))
            packs.append(_bns_pack(q))
        if _has_any(q, ("child", "minor", "pocso", "under 18")):
            packs.append(SourcePack(
                id="pocso_2012",
                title_patterns=("Protection of Children from Sexual Offences Act 2012",),
                search_query="Protection of Children from Sexual Offences Act 2012 reporting child sexual offence special court",
                doc_ids=("pocso-2012",),
            ))

    elif category == "workplace_sexual_harassment":
        packs.append(SourcePack(
            id="posh_2013",
            title_patterns=("Sexual Harassment of Women at Workplace Act 2013",),
            search_query="Sexual Harassment of Women at Workplace Act 2013 internal committee complaint retaliation",
            doc_ids=("posh-2013",),
        ))

    elif category == "pmla_ed":
        packs.append(SourcePack(
            id="pmla_2002",
            title_patterns=("Prevention of Money Laundering Act 2002",),
            search_query="Prevention of Money Laundering Act 2002 arrest summons bail attachment scheduled offence",
            doc_ids=("pmla-2002",),
        ))
        if not _uses_legacy_criminal_regime(route):
            packs.append(_bnss_pack(q))

    return packs


def _bnss_pack(query: str) -> SourcePack:
    if _has_any(query, ("fir", "police refused", "police not", "thana", "station")):
        search_query = "Bharatiya Nagarik Suraksha Sanhita 2023 FIR information police refusal magistrate investigation"
        anchor_patterns = ("/sec-173", "/sec-174", "/sec-175")
    elif _has_any(query, ("default bail", "no chargesheet", "charge sheet", "60 days", "90 days", "custody")):
        search_query = "Bharatiya Nagarik Suraksha Sanhita 2023 default bail detention chargesheet custody section 187"
        anchor_patterns = ("/sec-187",)
    else:
        search_query = "Bharatiya Nagarik Suraksha Sanhita 2023 bail arrest remand custody criminal procedure"
        anchor_patterns = ()
    return SourcePack(
        id="bnss_2023",
        title_patterns=("Bharatiya Nagarik Suraksha Sanhita 2023",),
        search_query=search_query,
        doc_ids=("bnss-2023",),
        anchor_patterns=anchor_patterns,
    )


def _bns_pack(query: str) -> SourcePack:
    if _has_any(query, ("theft", "stolen", "steal")):
        search_query = "Bharatiya Nyaya Sanhita 2023 theft stolen property punishment"
        anchor_patterns = ("/sec-303", "/sec-317")
    elif _has_any(query, ("rape", "sexual")):
        search_query = "Bharatiya Nyaya Sanhita 2023 rape sexual offence punishment"
        anchor_patterns = ("/sec-63", "/sec-64")
    elif _has_any(query, ("cheating", "420")):
        search_query = "Bharatiya Nyaya Sanhita 2023 cheating fraud dishonestly inducement"
        anchor_patterns = ("/sec-318", "/sec-319")
    else:
        search_query = "Bharatiya Nyaya Sanhita 2023 offence punishment criminal law"
        anchor_patterns = ()
    return SourcePack(
        id="bns_2023",
        title_patterns=("Bharatiya Nyaya Sanhita 2023",),
        search_query=search_query,
        doc_ids=("bns-2023",),
        anchor_patterns=anchor_patterns,
    )


def _rti_pack() -> SourcePack:
    return SourcePack(
        id="rti_2005",
        title_patterns=("Right to Information Act 2005",),
        search_query="Right to Information Act 2005 section 6 section 7 section 19 first appeal information commission",
        doc_ids=("rti-2005",),
        anchor_patterns=("/sec-19", "/sec-7", "/sec-6"),
    )


def _uses_legacy_criminal_regime(route: MatterRoute) -> bool:
    return bool(route.legal_regime and route.legal_regime.startswith("legacy_"))


def _has_any(text: str, needles: tuple[str, ...]) -> bool:
    return any(needle in text for needle in needles)


__all__ = ["SourcePack", "source_packs_for_route"]
