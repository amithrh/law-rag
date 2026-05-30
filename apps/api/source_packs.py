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

import re
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


def _ni_act_cheque_pack(priority: float = 1.08) -> SourcePack:
    return SourcePack(
        id="ni_act_1881",
        title_patterns=("Negotiable Instruments Act 1881",),
        search_query="Negotiable Instruments Act 1881 section 138 section 142 cheque dishonour notice complaint limitation",
        doc_ids=("negotiable-instruments-1881",),
        anchor_patterns=("/sec-138", "/sec-142"),
        priority=priority,
    )


def _contract_labour_wage_packs(query: str) -> list[SourcePack]:
    packs = [
        SourcePack(
            id="contract_labour_1970",
            title_patterns=("Contract Labour (Regulation and Abolition) Act 1970",),
            search_query="Contract Labour Regulation and Abolition Act 1970 section 21 responsibility for payment of wages principal employer contractor workmen",
            doc_ids=("contract-labour-1970",),
            anchor_patterns=("/sec-21",),
            priority=1.12,
        )
    ]
    if _has_interstate_migrant_context(query):
        packs.append(SourcePack(
            id="ismw_1979",
            title_patterns=("Inter-State Migrant Workmen (Regulation of Employment and Conditions of Service) Act 1979",),
            search_query="Inter-State Migrant Workmen Act 1979 contractor principal employer wages displacement allowance journey allowance duties",
            doc_ids=("ismw-1979",),
            anchor_patterns=("/sec-12", "/sec-14", "/sec-15", "/sec-16"),
            priority=1.04,
        ))
    return packs


def source_packs_for_route(route: MatterRoute, query: str) -> list[SourcePack]:
    """Return exact-source packs for a routed query.

    Order matters: earlier packs are more likely to survive the bounded
    rerank candidate window when a category has multiple authoritative
    sources.
    """
    q = query.lower()
    category = route.category
    packs: list[SourcePack] = []

    if category == "child_marriage_protection":
        packs.append(SourcePack(
            id="child_marriage_2006",
            title_patterns=("Prohibition of Child Marriage Act 2006",),
            search_query="Prohibition of Child Marriage Act 2006 child marriage injunction annulment child marriage prohibition officer",
            doc_ids=("child-marriage-2006",),
            anchor_patterns=("/sec-3", "/sec-5", "/sec-9", "/sec-13", "/sec-16"),
            priority=1.08,
        ))
        if _has_child_age_context(q) or _has_any(q, ("pocso", "sexual", "rape", "pregnant")):
            packs.append(SourcePack(
                id="pocso_2012",
                title_patterns=("Protection of Children from Sexual Offences Act 2012",),
                search_query="Protection of Children from Sexual Offences Act 2012 child sexual offence reporting special court",
                doc_ids=("pocso-2012",),
                priority=0.95,
            ))

    elif category == "bonded_labour_rescue":
        packs.append(SourcePack(
            id="bonded_labour_1976",
            title_patterns=("Bonded Labour System (Abolition) Act 1976",),
            search_query="Bonded Labour System Abolition Act 1976 abolition release certificate district magistrate vigilance committee rehabilitation",
            doc_ids=("bonded-labour-1976",),
            anchor_patterns=("/sec-4", "/sec-5", "/sec-10", "/sec-12", "/sec-13"),
            priority=1.08,
        ))
        if _has_interstate_migrant_context(q):
            packs.append(SourcePack(
                id="ismw_1979",
                title_patterns=("Inter-State Migrant Workmen (Regulation of Employment and Conditions of Service) Act 1979",),
                search_query="Inter-State Migrant Workmen Act 1979 contractor licence displacement allowance journey allowance wages duties",
                doc_ids=("ismw-1979",),
                anchor_patterns=("/sec-12", "/sec-14", "/sec-15", "/sec-16"),
                priority=1.12,
            ))
        packs.append(SourcePack(
            id="bonded_labour_pucl_sc",
            title_patterns=("PUBLIC UNION FOR CIVIL LIBERTIES", "PUBLIC UNION OF CLVIL LIBERTIES"),
            search_query="bonded labour release certificate rehabilitation vigilance committee district magistrate Supreme Court",
            source_types=("sc_judgment",),
            priority=0.92,
        ))
        if _has_any(q, ("wage", "wages", "salary", "minimum", "contractor", "advance", "debt")):
            packs.append(SourcePack(
                id="code_on_wages_2019",
                title_patterns=("Code on Wages 2019",),
                search_query="Code on Wages 2019 minimum wages payment of wages contractor employee",
                doc_ids=("code-on-wages-2019",),
                priority=0.88,
            ))
        if _has_any(q, ("aadhaar", "aadhar", "id card", "identity document")):
            packs.append(SourcePack(
                id="aadhaar_2016",
                title_patterns=("Aadhaar (Targeted Delivery of Financial and Other Subsidies, Benefits and Services) Act 2016",),
                search_query="Aadhaar Act 2016 identity information restriction sharing possession documents",
                doc_ids=("aadhaar-2016",),
                anchor_patterns=("/sec-29", "/sec-37"),
                priority=0.9,
            ))
        if (
            not _uses_legacy_criminal_regime(route)
            and not _has_any(q, ("name change", "change my name", "change my surname", "change surname", "gazette"))
        ):
            packs.append(_bnss_pack(q))
            packs.append(_bns_pack(q))
            if route.legal_regime == "incident_date_needed_for_bns_bnss_bsa_vs_ipc_crpc":
                packs.append(_crpc_pack(q))
        else:
            packs.append(_crpc_pack(q))

    elif category == "disability_access":
        rpwd_search = "Rights of Persons with Disabilities Act 2016 disability certificate certifying authority UDID accessibility reasonable accommodation"
        rpwd_anchors = ("/sec-56", "/sec-57", "/sec-58", "/sec-89")
        if _has_any(q, ("terminated", "termination", "company", "employer", "targets", "reasonable accommodation", "work")):
            rpwd_search = "Rights of Persons with Disabilities Act 2016 section 20 non discrimination in employment reasonable accommodation"
            rpwd_anchors = ("/sec-20", "/sec-21", "/sec-89")
        packs.append(SourcePack(
            id="rpwd_2016",
            title_patterns=("Rights of Persons with Disabilities Act 2016",),
            search_query=rpwd_search,
            doc_ids=("rpwd-2016",),
            anchor_patterns=rpwd_anchors,
            priority=1.06,
        ))

    elif category == "arrest_custody_safeguard":
        packs.append(_constitution_article_21_pack("Article 21 Article 22 arrest custody handcuff personal liberty"))
        packs.append(_constitution_article_22_pack(q))
        if _uses_legacy_criminal_regime(route):
            packs.append(_crpc_pack(q))
        else:
            packs.append(_bnss_pack(q))
            if route.legal_regime == "incident_date_needed_for_bns_bnss_bsa_vs_ipc_crpc":
                packs.append(_crpc_pack(q))

    elif category == "undertrial_review_release":
        packs.append(_constitution_article_21_pack("undertrial speedy trial custody liberty Article 21"))
        packs.append(SourcePack(
            id="bnss_2023",
            title_patterns=("Bharatiya Nagarik Suraksha Sanhita 2023",),
            search_query="Bharatiya Nagarik Suraksha Sanhita 2023 section 479 maximum period undertrial prisoner detention release",
            doc_ids=("bnss-2023",),
            anchor_patterns=("/sec-479",),
        ))
        packs.append(SourcePack(
            id="crpc_1973",
            title_patterns=("Code of Criminal Procedure 1973", "Code of Criminal Procedure, 1973"),
            search_query="Code of Criminal Procedure 1973 section 436A maximum period undertrial prisoner detention release",
            doc_ids=("crpc-1973",),
            anchor_patterns=("/sec-436A", "/sec-436-a"),
            priority=0.94,
        ))
        packs.append(SourcePack(
            id="legal_services_authorities_1987",
            title_patterns=("Legal Services Authorities Act 1987",),
            search_query="Legal Services Authorities Act 1987 legal aid undertrial prisoner District Legal Services Authority section 12",
            doc_ids=("legal-services-authorities-1987",),
            anchor_patterns=("/sec-12", "/sec-9"),
            priority=0.86,
        ))

    elif category == "tribal_caste_atrocity":
        if _has_any(q, ("bonded labour", "no wages", "just food", "only food", "years no wages")):
            packs.append(SourcePack(
                id="bonded_labour_1976",
                title_patterns=("Bonded Labour System (Abolition) Act 1976",),
                search_query="Bonded Labour System Abolition Act 1976 abolition release certificate district magistrate forced labour no wages",
                doc_ids=("bonded-labour-1976",),
                anchor_patterns=("/sec-4", "/sec-5", "/sec-10", "/sec-12", "/sec-13"),
                priority=1.10,
            ))
            packs.append(SourcePack(
                id="code_on_wages_2019",
                title_patterns=("Code on Wages 2019",),
                search_query="Code on Wages 2019 payment of wages minimum wages claims authority",
                doc_ids=("code-on-wages-2019",),
                anchor_patterns=("/sec-17", "/sec-18", "/sec-21", "/sec-45"),
                priority=0.96,
            ))
        if _is_scst_poa_context(q):
            poa_search = "Scheduled Castes Scheduled Tribes Prevention of Atrocities Act 1989 section 3 offence atrocity"
            poa_anchors: tuple[str, ...] = ()
            poa_priority = 1.0
            if _has_any(q, ("special court", "exclusive special court", "pending", "delay", "victim", "15a", "poa case")):
                poa_search = "Scheduled Castes Scheduled Tribes Prevention of Atrocities Act 1989 section 14 Special Court section 15A victim rights speedy trial"
                poa_anchors = ("/sec-13", "/sec-14", "/sec-15A")
                poa_priority = 1.08
            packs.append(SourcePack(
                id="scst_poa_1989",
                title_patterns=(
                    "Scheduled Castes and Scheduled Tribes (Prevention of Atrocities) Act 1989",
                    "Prevention of Atrocities Act 1989",
                ),
                search_query=poa_search,
                doc_ids=("sc-st-poa-1989",),
                anchor_patterns=poa_anchors,
                priority=poa_priority,
            ))
            if _has_any(q, ("fir", "police", "beat", "beaten", "violence", "threat", "not registered")):
                packs.append(_bnss_pack(q))
                packs.append(_bns_pack(q))
                if route.legal_regime == "incident_date_needed_for_bns_bnss_bsa_vs_ipc_crpc":
                    packs.append(_crpc_pack(q))
            if _has_any(q, ("untouchability", "temple", "dirty water", "well", "dalit cannot touch", "article 17")):
                if _has_any(q, ("temple", "well", "water", "dirty water")):
                    packs.append(SourcePack(
                        id="protection_civil_rights_1955_religious_access",
                        title_patterns=("Protection of Civil Rights Act 1955",),
                        search_query="Protection of Civil Rights Act 1955 section 3 untouchability temple entry place of public worship well water access",
                        doc_ids=("protection-civil-rights-1955",),
                        anchor_patterns=("/sec-3",),
                        priority=1.18,
                    ))
                packs.append(SourcePack(
                    id="protection_civil_rights_1955",
                    title_patterns=("Protection of Civil Rights Act 1955",),
                    search_query="Protection of Civil Rights Act 1955 untouchability religious social disability temple entry well water services",
                    doc_ids=("protection-civil-rights-1955",),
                    anchor_patterns=("/sec-3", "/sec-4", "/sec-5", "/sec-6", "/sec-7", "/sec-15A"),
                    priority=1.10,
                ))
                packs.append(SourcePack(
                    id="constitution_article_17",
                    title_patterns=("Constitution of India",),
                    search_query="Constitution of India Article 17 abolition of untouchability caste discrimination",
                    doc_ids=("constitution-india",),
                    anchor_patterns=("/sec-17",),
                    priority=1.14,
                ))
        if _has_any(q, ("forest", "tendu", "ifr", "cfr", "minor forest produce", "community forest")):
            packs.append(SourcePack(
                id="fra_2006",
                title_patterns=("Scheduled Tribes and Other Traditional Forest Dwellers (Recognition of Forest Rights) Act 2006",),
                search_query="Forest Rights Act 2006 community forest rights minor forest produce gram sabha title",
                doc_ids=("fra-2006",),
                anchor_patterns=("/sec-3", "/sec-4", "/sec-6"),
                priority=1.05,
            ))
        if _has_any(q, ("gram sabha", "scheduled area", "pesa")):
            packs.append(SourcePack(
                id="pesa_1996",
                title_patterns=("Panchayats (Extension to the Scheduled Areas) Act 1996",),
                search_query="PESA Act 1996 Scheduled Areas Gram Sabha consultation land acquisition minor minerals",
                doc_ids=("pesa-1996",),
                anchor_patterns=("/sec-4",),
                priority=1.04,
            ))
        if _has_tribal_land_transfer_context(q):
            if _has_jharkhand_tribal_land_context(q):
                packs.append(SourcePack(
                    id="chota_nagpur_tenancy_1908_transfer_restriction",
                    title_patterns=("Chota Nagpur Tenancy Act 1908",),
                    search_query="Chota Nagpur Tenancy Act 1908 section 46 transfer tribal land non tribal raiyat permission Deputy Commissioner no transfer valid court",
                    doc_ids=("chota-nagpur-tenancy-1908",),
                    anchor_patterns=("sec-45-c", "sec-45-b"),
                    priority=1.18,
                ))
                packs.append(SourcePack(
                    id="chota_nagpur_tenancy_1908_restoration",
                    title_patterns=("Chota Nagpur Tenancy Act 1908",),
                    search_query="Chota Nagpur Tenancy Act 1908 section 71A restore possession Scheduled Tribes land unlawfully transferred Deputy Commissioner",
                    doc_ids=("chota-nagpur-tenancy-1908",),
                    anchor_patterns=("sec-71-a",),
                    priority=1.16,
                ))
                packs.append(SourcePack(
                    id="santhal_parganas_tenancy_1949",
                    title_patterns=("Santhal Parganas Tenancy Act 1949",),
                    search_query="Santhal Parganas Tenancy Act 1949 transfer tribal land non tribal raiyat restoration",
                    doc_ids=("santhal-parganas-tenancy-1949",),
                    priority=1.08,
                ))
            packs.append(SourcePack(
                id="constitution_scheduled_areas",
                title_patterns=("Constitution of India",),
                search_query="Constitution of India Article 244 Fifth Schedule Scheduled Areas tribal land administration",
                doc_ids=("constitution-india",),
                priority=1.02,
            ))
        if _has_land_acquisition_context(q) or (
            _has_any(q, ("bauxite", "coal block", "mining project"))
            and _has_any(q, ("gram sabha", "scheduled area", "land", "acquisition", "noc"))
        ):
            packs.append(SourcePack(
                id="rfctlarr_2013",
                title_patterns=("Right to Fair Compensation and Transparency in Land Acquisition, Rehabilitation and Resettlement Act 2013",),
                search_query="Right to Fair Compensation and Transparency in Land Acquisition Rehabilitation Resettlement Act 2013 Scheduled Areas consent compensation rehabilitation",
                doc_ids=("rfctlarr-2013",),
                anchor_patterns=("/sec-41", "/sec-31", "/sec-38"),
                priority=1.02,
            ))
        if _has_any(q, ("bauxite", "coal block", "mining", "minor mineral", "mine", "mines", "minerals")):
            packs.append(SourcePack(
                id="mmdr_1957",
                title_patterns=("Mines and Minerals (Development and Regulation) Act 1957",),
                search_query="Mines and Minerals Development and Regulation Act 1957 mining lease mineral concession scheduled area gram sabha consultation",
                doc_ids=("mmdr-1957",),
                priority=1.02,
            ))
        if _has_any(q, ("forest", "forest clearance", "fca", "bauxite", "coal block", "mining project")):
            packs.append(SourcePack(
                id="forest_conservation_1980",
                title_patterns=("Forest (Conservation) Act 1980",),
                search_query="Forest Conservation Act 1980 section 2 forest land non forest purpose prior approval mining project",
                doc_ids=("forest-conservation-1980",),
                priority=1.0,
            ))

    elif category == "family_domestic":
        if _is_divorce_context(q):
            if _is_special_marriage_context(q):
                packs.append(_special_marriage_pack(q))
            elif _is_muslim_family_context(q):
                packs.append(SourcePack(
                    id="dissolution_muslim_marriages_1939",
                    title_patterns=("Dissolution of Muslim Marriages Act 1939",),
                    search_query="Dissolution of Muslim Marriages Act 1939 Muslim wife divorce grounds family court",
                    doc_ids=("dissolution-muslim-marriages-1939",),
                    priority=1.02,
                ))
                packs.append(SourcePack(
                    id="shariat_1937",
                    title_patterns=("Muslim Personal Law (Shariat) Application Act 1937",),
                    search_query="Muslim Personal Law Shariat Application Act 1937 marriage dissolution personal law",
                    doc_ids=("shariat-1937",),
                    priority=0.88,
                ))
            elif _is_christian_family_context(q):
                packs.append(SourcePack(
                    id="indian_divorce_1869",
                    title_patterns=("Divorce Act 1869", "Indian Divorce Act"),
                    search_query="Divorce Act 1869 Christian divorce mutual consent family court",
                    doc_ids=("indian-divorce-1869",),
                    priority=1.02,
                ))
            else:
                packs.append(_hindu_marriage_pack(q))
            packs.append(_family_courts_pack())
        if _is_family_safety_or_support_context(q) or not packs:
            pwdva_search = "Protection of Women from Domestic Violence Act 2005 section 12 protection residence maintenance"
            pwdva_anchors: tuple[str, ...] = ()
            if _has_any(q, ("grabbed", "touching", "touched", "uncomfortable", "brother in law", "brother-in-law", "husband's brother")):
                pwdva_search = "Protection of Women from Domestic Violence Act 2005 section 3 physical sexual verbal emotional abuse section 18 protection order section 12 application"
                pwdva_anchors = ("/sec-3", "/sec-18", "/sec-12")
            elif not _has_negated_sexual_coercion(q) and _has_any(q, ("forces sex", "force sex", "forced sex", "marital rape", "even when i say no", "sex when i say no", "without consent")):
                pwdva_search = "Protection of Women from Domestic Violence Act 2005 section 3 sexual abuse physical abuse emotional abuse section 18 protection order section 12 application"
                pwdva_anchors = ("/sec-3", "/sec-18", "/sec-12")
            elif _has_any(q, ("residence", "shared household", "ghar se nikal", "threw me out", "kicked me out", "sasural")):
                pwdva_search = "Protection of Women from Domestic Violence Act 2005 section 17 section 19 shared household residence order"
                pwdva_anchors = ("/sec-17", "/sec-19", "/sec-12", "/sec-18", "/sec-20")
            elif _has_any(q, ("salary", "atm card", "groceries", "breadwinner", "economic abuse", "not giving money")):
                pwdva_search = "Protection of Women from Domestic Violence Act 2005 section 3 economic abuse section 20 monetary relief"
                pwdva_anchors = ("/sec-3", "/sec-20", "/sec-12")
            elif _has_any(q, ("maintenance", "child support", "school fees", "monetary relief", "not paying")):
                pwdva_search = "Protection of Women from Domestic Violence Act 2005 section 20 monetary relief maintenance section 12 application"
                pwdva_anchors = ("/sec-20", "/sec-12")
            packs.append(SourcePack(
                id="pwdva_2005",
                title_patterns=("Protection of Women from Domestic Violence Act 2005",),
                search_query=pwdva_search,
                doc_ids=("domestic-violence-2005",),
                anchor_patterns=pwdva_anchors,
            ))
        if _has_adult_choice_marriage_context(q):
            packs.append(_constitution_article_21_pack(q))
            packs.append(_special_marriage_pack(q))
        if _has_any(q, ("child support", "child maintenance", "maintenance order", "not paying", "arrears")):
            packs.append(_bnss_pack(q))
            packs.append(_crpc_pack(q))
        if _has_any(q, (
            "slaps me", "beats me", "beating me", "hit me", "hitting me",
            "threat", "threatens", "threatened", "dowry", "cruelty",
            "grabbed", "touching", "touched", "sexual", "uncomfortable",
        )) or (not _has_negated_sexual_coercion(q) and _has_any(q, (
            "forces sex", "force sex", "forced sex", "marital rape",
            "even when i say no", "without consent",
        ))):
            packs.append(_bns_pack(q))
            if not _uses_legacy_criminal_regime(route):
                packs.append(_bnss_pack(q))
        if _has_any(q, ("streedhan", "stridhan", "jewellery", "jewelry")):
            packs.append(SourcePack(
                id="dowry_prohibition_1961",
                title_patterns=("Dowry Prohibition Act 1961",),
                search_query="Dowry Prohibition Act 1961 dowry property presents streedhan return criminal complaint",
                doc_ids=("dowry-prohibition-1961",),
                priority=1.04,
            ))
            packs.append(SourcePack(
                id="hindu_succession_1956",
                title_patterns=("Hindu Succession Act 1956",),
                search_query="Hindu Succession Act 1956 section 14 female property absolute ownership jewellery stridhan succession",
                doc_ids=("hindu-succession-1956",),
                anchor_patterns=("/sec-14",),
                priority=1.02,
            ))

    elif category == "senior_citizen":
        has_gift_transfer = _has_any(q, ("gift", "gifted", "gift deed", "transfer", "transferred", "settlement deed"))
        if _has_any(q, ("enforce", "enforcement", "stopped paying", "not paying", "tribunal ordered", "tribunal order", "default")):
            senior_anchor_patterns = (("/sec-23", "/sec-11", "/sec-13", "/sec-9", "/sec-5") if has_gift_transfer else ("/sec-11", "/sec-13", "/sec-9", "/sec-5"))
            senior_search = "Maintenance and Welfare of Parents and Senior Citizens Act 2007 section 11 enforcement order maintenance section 13 deposit maintenance amount tribunal"
            if has_gift_transfer:
                senior_search += " section 23 transfer property gift deed void"
        elif has_gift_transfer:
            senior_anchor_patterns = ("/sec-23",)
            senior_search = "Maintenance and Welfare of Parents and Senior Citizens Act 2007 section 23 maintenance tribunal transfer property"
        else:
            senior_anchor_patterns = ("/sec-4", "/sec-5", "/sec-9", "/sec-23")
            senior_search = "Maintenance and Welfare of Parents and Senior Citizens Act 2007 section 4 section 23 maintenance tribunal transfer property"
        packs.append(SourcePack(
            id="senior_citizens_2007",
            title_patterns=("Maintenance and Welfare of Parents and Senior Citizens Act 2007",),
            search_query=senior_search,
            doc_ids=("mwp-2007", "senior-citizens-2007"),
            anchor_patterns=senior_anchor_patterns,
        ))
        if _has_any(q, ("cheque", "cheques", "bounced", "dishonour", "dishonored")):
            packs.append(_ni_act_cheque_pack(priority=1.06))
        if _has_elderly_woman_domestic_context(q):
            packs.append(SourcePack(
                id="pwdva_2005",
                title_patterns=("Protection of Women from Domestic Violence Act 2005",),
                search_query="Protection of Women from Domestic Violence Act 2005 residence order shared household domestic relationship elderly woman daughter in law",
                doc_ids=("domestic-violence-2005",),
                anchor_patterns=("/sec-17", "/sec-19", "/sec-12"),
                priority=1.04,
            ))
        if _has_any(q, ("gift", "gifted", "transfer", "transferred", "settlement deed", "not caring", "cancel", "son not caring", "daughter not caring")):
            packs.append(SourcePack(
                id="transfer_property_1882",
                title_patterns=("Transfer of Property Act 1882",),
                search_query="Transfer of Property Act 1882 gift transfer section 122 revocation suspension section 126 property deed",
                doc_ids=("transfer-of-property-1882",),
                anchor_patterns=("/sec-122", "/sec-123", "/sec-126"),
                priority=0.94,
            ))
        if _has_any(q, ("ulip", "insurance", "policy", "agent sold", "mis-selling", "misselling")):
            packs.append(SourcePack(
                id="consumer_protection_2019",
                title_patterns=("Consumer Protection Act 2019",),
                search_query="Consumer Protection Act 2019 insurance policy agent mis-selling service deficiency complaint",
                doc_ids=("consumer-protection-2019",),
                anchor_patterns=("/sec-2-", "/sec-35", "/sec-38"),
                priority=1.02,
            ))
            packs.append(SourcePack(
                id="insurance_ombudsman_rules_2017",
                title_patterns=("Insurance Ombudsman Rules 2017", "IRDAI Insurance Ombudsman Rules 2017"),
                search_query="Insurance Ombudsman Rules 2017 IRDAI insurance policy mis-selling complaint award",
                doc_ids=("insurance-ombudsman-rules-2017",),
                priority=1.0,
            ))
        if _has_any(q, ("fake call", "fraud call", "scam call", "pension office", "took 2 lakh", "debited", "transferred")):
            packs.append(SourcePack(
                id="it_act_2000",
                title_patterns=("Information Technology Act 2000",),
                search_query="Information Technology Act 2000 section 66C identity theft section 66D cheating by personation cyber fraud",
                doc_ids=("it-2000",),
                anchor_patterns=("/sec-66C", "/sec-66D"),
                priority=1.04,
            ))
            packs.append(_bnss_pack(q))
            packs.append(_bns_pack(q))
            if route.legal_regime == "incident_date_needed_for_bns_bnss_bsa_vs_ipc_crpc":
                packs.append(_crpc_pack(q))

    elif category == "cyber_fraud_or_harassment":
        it_search = "Information Technology Act 2000 section 66C 66D 66E 67 cyber fraud intimate image"
        it_anchors: tuple[str, ...] = ()
        child_intimate_image_context = _has_child_intimate_image_subject_context(q)
        if child_intimate_image_context:
            it_search = "Information Technology Act 2000 section 67B child sexually explicit material section 66E privacy section 67A electronic publication"
            it_anchors = ("/sec-67B", "/sec-66E", "/sec-67A", "/sec-67")
        elif _has_any(q, (
            "nude", "private photo", "private photos", "private picture",
            "private pictures", "intimate", "sex video", "porn video",
            "morphed", "deepfake", "lookalike", "look alike", "face same",
            "not me but face", "onlyfans content", "leaked my onlyfans",
        )):
            it_search = "Information Technology Act 2000 section 66E privacy section 67 section 67A publishing obscene sexually explicit electronic material intimate image"
            it_anchors = ("/sec-66E", "/sec-67", "/sec-67A")
        elif _has_any(q, ("stalker", "stalking", "dm daily", "direct message", "dms", "insta", "instagram", "after blocking", "bumble", "screenshot", "screenshots", "send screenshots", "dating app")):
            it_search = "Information Technology Act 2000 section 66E privacy electronic communication cyber harassment"
            it_anchors = ("/sec-66E", "/sec-67")
        elif _has_any(q, ("tinder", "extortion", "gang", "took my phone", "personation")):
            it_search = "Information Technology Act 2000 section 66D cheating by personation section 66E privacy cyber complaint"
            it_anchors = ("/sec-66D", "/sec-66E", "/sec-67")
        elif _has_any(q, ("crypto", "rugpull", "rugpulled", "telegram group")):
            it_search = "Information Technology Act 2000 section 66D cheating by personation cyber fraud online investment group"
            it_anchors = ("/sec-66D",)
        packs.append(SourcePack(
            id="it_act_2000",
            title_patterns=("Information Technology Act 2000",),
            search_query=it_search,
            doc_ids=("it-2000",),
            anchor_patterns=it_anchors,
        ))
        if _has_any(q, ("onlyfans", "fanvue content", "creator content", "copyright")) and _has_any(q, ("leaked", "leak", "without permission")):
            packs.append(SourcePack(
                id="copyright_1957",
                title_patterns=("Copyright Act 1957",),
                search_query="Copyright Act 1957 section 51 infringement section 63 criminal offence online content without permission",
                doc_ids=("copyright-1957",),
                anchor_patterns=("/sec-51", "/sec-63"),
                priority=1.06,
            ))
            packs.append(SourcePack(
                id="it_act_2000_intermediary",
                title_patterns=("Information Technology Act 2000",),
                search_query="Information Technology Act 2000 section 79 intermediary platform liability online content takedown due diligence",
                doc_ids=("it-2000",),
                anchor_patterns=("/sec-79",),
                priority=1.04,
            ))
        if _has_any(q, ("deepfake", "lookalike", "look alike", "face same", "not me but face", "ai porn")):
            packs.append(SourcePack(
                id="dpdp_2023_deepfake",
                title_patterns=("Digital Personal Data Protection Act 2023",),
                search_query="Digital Personal Data Protection Act 2023 section 8 personal data security safeguards breach deepfake image identity",
                doc_ids=("dpdp-2023",),
                anchor_patterns=("/sec-8", "/sec-13", "/sec-27"),
                priority=1.04,
            ))
        if _has_any(q, (
            "privacy", "personal data", "data breach", "dpdp",
            "pan leaked", "aadhaar leaked", "aadhar leaked",
            "pan and aadhaar", "pan and aadhar", "data leaked",
            "therapist", "mental health", "chat leak", "leaked my chat", "leaked chat",
        )):
            packs.append(SourcePack(
                id="dpdp_2023",
                title_patterns=("Digital Personal Data Protection Act 2023",),
                search_query="Digital Personal Data Protection Act 2023 section 8 personal data breach security safeguards breach notice",
                doc_ids=("dpdp-2023",),
                anchor_patterns=("/sec-8",),
                priority=1.12,
            ))
            packs.append(SourcePack(
                id="dpdp_2023_grievance",
                title_patterns=("Digital Personal Data Protection Act 2023",),
                search_query="Digital Personal Data Protection Act 2023 section 13 grievance redressal exhaust before approaching Board",
                doc_ids=("dpdp-2023",),
                anchor_patterns=("/sec-13",),
                priority=1.10,
            ))
            packs.append(SourcePack(
                id="dpdp_2023_board",
                title_patterns=("Digital Personal Data Protection Act 2023",),
                search_query="Digital Personal Data Protection Act 2023 section 27 Board complaint personal data breach inquiry impose penalty",
                doc_ids=("dpdp-2023",),
                anchor_patterns=("/sec-27",),
                priority=1.10,
            ))
            if _has_any(q, ("therapist", "mental health", "psychiatric", "psychologist", "counsellor", "counselor")):
                packs.append(SourcePack(
                    id="mental_healthcare_2017",
                    title_patterns=("Mental Healthcare Act 2017",),
                    search_query="Mental Healthcare Act 2017 confidentiality mental healthcare information privacy mental health professional",
                    doc_ids=("mental-healthcare-2017",),
                    priority=1.0,
                ))
        if _has_any(q, ("sim", "new sim", "mobile number", "subscriber", "telecom")):
            packs.append(SourcePack(
                id="telecommunications_2023",
                title_patterns=("Telecommunications Act 2023",),
                search_query="Telecommunications Act 2023 identity misuse SIM subscriber fraud",
                doc_ids=("telecommunications-2023",),
                anchor_patterns=("/sec-29", "/sec-42"),
                priority=1.02,
            ))
        if _has_any(q, ("otp", "phishing", "unauthorized debit", "unauthorised debit", "bank says my fault", "no refund", "icici", "sbi", "hdfc")) and _has_any(q, ("bank", "account", "upi", "debit", "lost", "refund", "transaction")):
            packs.append(SourcePack(
                id="rbi_integrated_ombudsman_2021",
                title_patterns=(
                    "Reserve Bank Integrated Ombudsman Scheme 2021",
                    "Reserve Bank - Integrated Ombudsman Scheme 2021",
                ),
                search_query="Reserve Bank Integrated Ombudsman Scheme 2021 bank customer complaint unauthorized electronic transaction customer liability refund",
                doc_ids=("rbi-integrated-ombudsman-2021",),
                anchor_patterns=("/sec-2", "/sec-3"),
                priority=1.12,
            ))
        if (
            _has_any(q, (
            "nude", "private photo", "private photos", "private picture", "private pictures", "intimate", "sex video", "porn", "morphed",
            "deepfake", "leaked", "blackmail", "stalker", "stalking", "tinder",
            "extortion", "gang", "threatening", "telegram", "took my phone", "otp", "phonepe", "upi",
            "fraud", "scam", "fake whatsapp", "harassing", "harassment",
            "identity misuse", "identity theft", "fake loan", "cheating",
            "tweet", "defamation", "fake call", "phishing", "debited",
            "transferred", "took 2 lakh", "lost money", "rugpull", "rugpulled",
            "crypto group", "seed phrase", "connect wallet", "wallet drained",
            "drained account", "admin vanished", "stole my crypto",
            ))
            and not _is_plain_personal_data_breach(q)
        ):
            packs.append(_bns_pack(q))
            packs.append(_bnss_pack(q))
        if _has_any(q, ("crypto", "rugpull", "rugpulled", "usdt", "wallet")):
            packs.append(SourcePack(
                id="pmla_2002",
                title_patterns=("Prevention of Money Laundering Act 2002",),
                search_query="Prevention of Money Laundering Act 2002 proceeds of crime crypto fraud suspicious transaction reporting",
                doc_ids=("pmla-2002",),
                anchor_patterns=("/sec-2", "/sec-5", "/sec-17", "/sec-50"),
                priority=0.98,
            ))
        if _has_election_campaign_context(q):
            packs.append(SourcePack(
                id="rpa_1951",
                title_patterns=("Representation of the People Act 1951",),
                search_query="Representation of the People Act 1951 false statement corrupt practice election campaign candidate party",
                doc_ids=("rpa-1951",),
                anchor_patterns=("/sec-123", "/sec-125", "/sec-125A"),
                priority=0.96,
            ))
        if child_intimate_image_context:
            packs.append(SourcePack(
                id="pocso_2012",
                title_patterns=("Protection of Children from Sexual Offences Act 2012",),
                search_query="Protection of Children from Sexual Offences Act 2012 section 13 section 14 section 15 child pornography sexual image reporting special court",
                doc_ids=("pocso-2012",),
                anchor_patterns=("/sec-13", "/sec-14", "/sec-15", "/sec-19"),
                priority=1.12,
            ))

    elif category == "consumer":
        housing_pet_issue = _has_pet_context(q) and _has_any(q, ("society", "housing", "apartment", "rwa", "fine", "approval"))
        housing_parking_issue = _has_any(q, ("parking", "parking slot", "dedicated parking", "allotted parking", "stilt parking", "car park")) and _has_any(q, ("society", "housing", "apartment", "rwa", "security guard"))
        if housing_pet_issue:
            packs.append(SourcePack(
                id="bmc_pet_guidelines_ban",
                title_patterns=("BMC Guidelines with respect to Pet", "Pet & Street dogs", "RWAs and AOAs"),
                search_query="pet dogs cats RWA AOA cannot legally introduce ban association keeping pet dogs cats",
                doc_ids=("bmc-pet-dog-guidelines",),
                source_types=("circular",),
                priority=1.18,
            ))
            packs.append(SourcePack(
                id="bmc_pet_guidelines_bylaws",
                title_patterns=("BMC Guidelines with respect to Pet", "Pet & Street dogs", "RWAs and AOAs"),
                search_query="illegal housing society pet bye laws disallow pets rules welfare residents interests",
                doc_ids=("bmc-pet-dog-guidelines",),
                source_types=("circular",),
                priority=1.16,
            ))
            packs.append(SourcePack(
                id="bmc_pet_guidelines_license",
                title_patterns=("BMC Guidelines with respect to Pet", "Pet & Street dogs", "RWAs and AOAs"),
                search_query="pet owners licence license vaccination RWA AOA society updated pet records",
                doc_ids=("bmc-pet-dog-guidelines",),
                source_types=("circular",),
                priority=1.12,
            ))
            packs.append(SourcePack(
                id="cooperative_housing_society_case_law",
                title_patterns=("CO-OPERATIVE HOUSING SOCIETY", "COOPERATIVE G/H SOCIETY", "REGISTRAR COOPERATIVE SOCIETIES"),
                search_query="cooperative housing society registrar managing committee fine member dispute",
                doc_ids=("2022-insc-33", "hc/dlhc010407932023", "hc/dlhc010254612023"),
                source_types=("sc_judgment", "hc_judgment"),
                priority=1.02,
            ))
        if housing_parking_issue:
            packs.append(SourcePack(
                id="housing_parking_case_law",
                title_patterns=("VELAGACHARLA JAYARAM REDDY",),
                search_query="parking area layout plan society definite material reserved as parking area cooperative officer",
                doc_ids=("2022-insc-31",),
                source_types=("sc_judgment",),
                priority=1.12,
            ))
        if not housing_pet_issue:
            packs.append(SourcePack(
                id="consumer_protection_2019",
                title_patterns=("Consumer Protection Act 2019",),
                search_query="Consumer Protection Act 2019 deficiency goods service refund complaint district commission apartment parking service",
                doc_ids=("consumer-protection-2019",),
                anchor_patterns=("/sec-2-", "/sec-35", "/sec-38"),
            ))
        if _has_any(q, ("rera", "builder", "possession", "flat", "apartment")):
            packs.append(SourcePack(
                id="rera_2016",
                title_patterns=("Real Estate (Regulation and Development) Act 2016",),
                search_query="Real Estate Regulation Development Act 2016 builder possession delay complaint authority adjudicating officer",
                doc_ids=("rera-2016",),
                anchor_patterns=("/sec-18", "/sec-31", "/sec-34", "/sec-71"),
                priority=1.04,
            ))
        if _has_any(q, ("sale deed", "registered sale deed", "register sale deed", "hasnt registered", "hasn't registered")):
            packs.append(SourcePack(
                id="registration_1908",
                title_patterns=("Registration Act 1908",),
                search_query="Registration Act 1908 sale deed compulsory registration immovable property",
                doc_ids=("registration-1908",),
                anchor_patterns=("/sec-17", "/sec-23", "/sec-49"),
                priority=1.04,
            ))

    elif category == "digital_platform_account":
        if _has_online_gambling_context(q):
            if _has_tamil_nadu_context(q):
                packs.append(SourcePack(
                    id="tamil_nadu_online_gambling_2022",
                    title_patterns=("Tamil Nadu Prohibition of Online Gambling and Regulation of Online Games Act 2022",),
                    search_query="Tamil Nadu Prohibition of Online Gambling Regulation Online Games Act 2022 online gambling online game of chance prohibition transfer funds restrictions",
                    doc_ids=("tamil-nadu-online-gambling-2022",),
                    anchor_patterns=("/sec-2", "/sec-7", "/sec-9", "/sec-14", "/sec-16"),
                    priority=1.32,
                ))
            packs.append(SourcePack(
                id="public_gambling_1867",
                title_patterns=("Public Gambling Act 1867", "The Public Gambling Act, 1867"),
                search_query="Public Gambling Act 1867 common gaming house game of mere skill section 12 public gambling",
                doc_ids=("public-gambling-1867",),
                anchor_patterns=("/sec-3", "/sec-12", "/sec-13"),
                priority=1.22,
            ))
        packs.append(SourcePack(
            id="it_act_2000",
            title_patterns=("Information Technology Act 2000",),
            search_query="Information Technology Act 2000 intermediary platform grievance user account",
            doc_ids=("it-2000",),
            priority=0.98,
        ))
        packs.append(SourcePack(
            id="consumer_protection_2019",
            title_patterns=("Consumer Protection Act 2019",),
            search_query="Consumer Protection Act 2019 deficiency in digital platform service complaint",
            doc_ids=("consumer-protection-2019",),
            anchor_patterns=("/sec-2-", "/sec-35", "/sec-38"),
            priority=0.94,
        ))
        if _has_any(q, ("uber", "ola", "zomato", "swiggy", "rider", "driver", "gig", "platform worker", "delivery partner")):
            passenger_negation = _has_any(q, (
                "no driver", "not driver", "not a driver", "not driving",
                "i am customer", "i am a customer",
                "i'm customer", "i'm a customer", "customer account",
                "my customer account", "as customer", "as a customer",
                "as passenger", "as a passenger", "i was passenger",
                "i am passenger", "i am a passenger",
            ))
            worker_platform_context = (
                not passenger_negation
                and _has_any(q, (
                    "driver", "rider", "gig", "platform worker", "delivery partner",
                    "driver partner", "platform partner", "worker dues",
                ))
            )
            cab_driver_context = (
                _has_any(q, ("uber", "ola", "cab", "taxi"))
                and _has_any(q, (
                    "cab driver", "taxi driver", "uber driver", "ola driver",
                    "driver id", "driver account", "driver profile",
                    "driver partner", "platform partner", "vehicle integrated",
                ))
                and not passenger_negation
            )
            if cab_driver_context:
                packs.append(SourcePack(
                    id="motor_vehicle_aggregator_guidelines_2020_contract",
                    title_patterns=("Motor Vehicle Aggregator Guidelines 2020", "Motor Vehicle Aggregators Guidelines-2020"),
                    search_query="Motor Vehicle Aggregator Guidelines 2020 driver service provider contract deactivation terms",
                    doc_ids=("motor-vehicle-aggregator-guidelines-2020",),
                    anchor_patterns=("driver-service-contract",),
                    source_types=("guideline",),
                    priority=1.20,
                ))
                packs.append(SourcePack(
                    id="motor_vehicle_aggregator_guidelines_2020_grievance",
                    title_patterns=("Motor Vehicle Aggregator Guidelines 2020", "Motor Vehicle Aggregators Guidelines-2020"),
                    search_query="Motor Vehicle Aggregator Guidelines 2020 app transparency grievance rating driver disclosures",
                    doc_ids=("motor-vehicle-aggregator-guidelines-2020",),
                    anchor_patterns=("app-transparency-grievance",),
                    source_types=("guideline",),
                    priority=1.18,
                ))
                packs.append(SourcePack(
                    id="motor_vehicle_aggregator_guidelines_2020_nondiscrimination",
                    title_patterns=("Motor Vehicle Aggregator Guidelines 2020", "Motor Vehicle Aggregators Guidelines-2020"),
                    search_query="Motor Vehicle Aggregator Guidelines 2020 non discrimination driver fare regional bias",
                    doc_ids=("motor-vehicle-aggregator-guidelines-2020",),
                    anchor_patterns=("non-discrimination-driver-fare",),
                    source_types=("guideline",),
                    priority=1.16,
                ))
                packs.append(SourcePack(
                    id="motor_vehicles_1988_aggregator",
                    title_patterns=("Motor Vehicles Act 1988", "TheMotorVehiclesAct,1988"),
                    search_query="Motor Vehicles Act 1988 aggregator licence section 93 section 193 aggregator proper authority",
                    doc_ids=("motor-vehicles-1988",),
                    anchor_patterns=("/sec-193",),
                    priority=1.02,
                ))
            if worker_platform_context and _has_any(q, ("id blocked", "profile blocked", "deactivated", "suspended", "wage", "earning", "payment", "full and final")):
                packs.append(SourcePack(
                    id="code_on_wages_2019",
                    title_patterns=("Code on Wages 2019",),
                    search_query="Code on Wages 2019 payment of wages employee worker dues platform rider wage authority",
                    doc_ids=("code-on-wages-2019",),
                    anchor_patterns=("/sec-17", "/sec-18", "/sec-43", "/sec-45"),
                    priority=1.02,
                ))
            if worker_platform_context:
                packs.append(SourcePack(
                    id="social_security_code_2020",
                    title_patterns=("Code on Social Security 2020",),
                    search_query="Code on Social Security 2020 gig worker platform worker registration social security scheme",
                    doc_ids=("social-security-code-2020",),
                    anchor_patterns=("/sec-112", "/sec-113", "/sec-114", "/sec-141"),
                    priority=0.92,
                ))
            if worker_platform_context and _has_any(q, ("racist", "hindi speaker", "bengali", "gujarati", "language", "migrant", "go back home")):
                packs.append(SourcePack(
                    id="constitution_article_14",
                    title_patterns=("Constitution of India",),
                    search_query="Constitution of India Article 14 equality before law non discrimination language place of birth",
                    doc_ids=("constitution-india",),
                    anchor_patterns=("/sec-14",),
                    priority=0.98,
                ))
        if _has_any(q, ("binance", "usdt", "wallet", "dream11", "parimatch", "betting", "rummy", "online gaming")):
            packs.append(SourcePack(
                id="consumer_protection_2019",
                title_patterns=("Consumer Protection Act 2019",),
                search_query="Consumer Protection Act 2019 digital platform wallet online service deficiency complaint",
                doc_ids=("consumer-protection-2019",),
                anchor_patterns=("/sec-2-", "/sec-35", "/sec-38"),
                priority=1.04,
            ))
            if _has_any(q, ("binance", "usdt", "crypto", "wallet", "suspicious trade", "suspicious transaction", "aml", "fiu", "frozen", "froze")):
                packs.append(SourcePack(
                    id="pmla_2002",
                    title_patterns=("Prevention of Money Laundering Act 2002",),
                    search_query="Prevention of Money Laundering Act 2002 suspicious transaction crypto wallet freeze money laundering",
                    doc_ids=("pmla-2002",),
                    anchor_patterns=("/sec-5", "/sec-8", "/sec-17", "/sec-50"),
                    priority=1.06,
                ))

    elif category == "reproductive_rights_mtp":
        packs.append(SourcePack(
            id="mtp_1971",
            title_patterns=("Medical Termination of Pregnancy Act 1971",),
            search_query="Medical Termination of Pregnancy Act 1971 termination pregnancy rape survivor medical board",
            doc_ids=("mtp-1971",),
        ))

    elif category == "ibc_nclt":
        if _has_any(q, ("llp", "limited liability partnership", "form 11")):
            packs.append(SourcePack(
                id="llp_2008",
                title_patterns=("Limited Liability Partnership Act 2008",),
                search_query="Limited Liability Partnership Act 2008 section 35 annual return section 75 strike off defunct LLP Registrar Form 11",
                doc_ids=("llp-2008",),
                anchor_patterns=("/sec-35", "/sec-75"),
                priority=1.12,
            ))
            return packs
        if _has_any(q, ("company", "private limited", "pvt ltd", "mgt", "aoc", "roc", "director", "disqualified", "strike off", "revive")):
            packs.append(SourcePack(
                id="companies_2013",
                title_patterns=("Companies Act 2013",),
                search_query="Companies Act 2013 annual return financial statement director disqualification strike off restoration",
                doc_ids=("companies-2013",),
                anchor_patterns=("/sec-92", "/sec-137", "/sec-164", "/sec-252"),
                priority=1.08,
            ))
        ibc_search = "Insolvency and Bankruptcy Code 2016 section 7 section 9 operational creditor demand notice"
        ibc_anchors: tuple[str, ...] = ()
        ibc_priority = 1.0
        if _has_any(q, ("nclat", "appeal", "order", "days limit", "limitation")):
            ibc_search = "Insolvency and Bankruptcy Code 2016 section 61 appeal to NCLAT thirty days condonation fifteen days NCLT order"
            ibc_anchors = ("/sec-61",)
            ibc_priority = 1.12
        packs.append(SourcePack(
            id="ibc_2016",
            title_patterns=("Insolvency and Bankruptcy Code 2016",),
            search_query=ibc_search,
            doc_ids=("ibc-2016",),
            anchor_patterns=ibc_anchors,
            priority=ibc_priority,
        ))

    elif category == "cheque_bounce":
        packs.append(SourcePack(
            id="ni_act_1881",
            title_patterns=("Negotiable Instruments Act 1881",),
            search_query="Negotiable Instruments Act 1881 section 138 section 142 cheque dishonour complaint limitation",
            doc_ids=("negotiable-instruments-1881",),
            anchor_patterns=("/sec-138", "/sec-142"),
        ))

    elif category == "tax_gst_compliance":
        if _is_customs_context(q):
            customs_search = "Customs Act 1962 bill of entry assessment classification duty appeal adjudication"
            customs_anchors = ("/sec-17", "/sec-28", "/sec-128", "/sec-129A")
            if _has_any(q, ("refund", "drawback", "duty refund", "rejected drawback")):
                customs_search = "Customs Act 1962 section 27 refund duty drawback section 74 section 75 appeal"
                customs_anchors = ("/sec-27", "/sec-74", "/sec-75", "/sec-128")
            packs.append(SourcePack(
                id="customs_1962",
                title_patterns=("Customs Act 1962",),
                search_query=customs_search,
                doc_ids=("customs-1962",),
                anchor_patterns=customs_anchors,
                priority=1.05,
            ))
        if _has_any(q, ("gst", "cgst", "gstr", "register gst", "rule 86b", "86b", "1% cash", "1 percent cash", "one percent cash")):
            gst_search = "Central Goods and Services Tax Act 2017 section 22 registration threshold supply service"
            gst_anchors: tuple[str, ...] = ()
            if _has_any(q, ("sealed", "seal", "search", "godown", "without notice", "inspection")):
                gst_search = "Central Goods and Services Tax Act 2017 section 67 inspection search seizure section 83 provisional attachment"
                gst_anchors = ("/sec-67", "/sec-83")
            elif _has_any(q, ("rule 86b", "86b", "1% cash", "1 percent cash", "one percent cash")):
                gst_search = "Central Goods and Services Tax Act 2017 input tax credit electronic credit ledger cash payment restriction rule 86B"
                gst_anchors = ("/sec-49", "/sec-49A", "/sec-49B")
                packs.append(SourcePack(
                    id="cgst_rules_2017",
                    title_patterns=("Central Goods and Services Tax Rules 2017",),
                    search_query="Central Goods and Services Tax Rules 2017 Rule 86B electronic credit ledger ninety nine percent cash payment restriction",
                    doc_ids=("cgst-rules-2017",),
                    priority=1.12,
                ))
            elif _has_any(q, ("cancellation", "cancelled", "cancelled registration", "registration cancelled", "nil returns", "nil return", "revocation")):
                gst_search = "Central Goods and Services Tax Act 2017 section 29 cancellation registration section 30 revocation cancellation section 107 appeal"
                gst_anchors = ("/sec-29", "/sec-30", "/sec-107")
            elif _has_any(q, ("appeal", "assessment order", "adjudication order")):
                gst_search = "Central Goods and Services Tax Act 2017 section 107 appeal assessment adjudication order"
                gst_anchors = ("/sec-107",)
            elif _has_any(q, ("late return", "late fee", "penalty", "notice")):
                gst_search = "Central Goods and Services Tax Act 2017 section 47 late fee section 73 tax demand penalty notice"
                gst_anchors = ("/sec-47", "/sec-73", "/sec-74")
            packs.append(SourcePack(
                id="cgst_2017",
                title_patterns=("Central Goods and Services Tax Act 2017",),
                search_query=gst_search,
                doc_ids=("cgst-2017",),
                anchor_patterns=gst_anchors,
            ))
        income_tax_context = _has_any(q, (
            "itr", "income tax", "tds", "tcs", "foreign remittance",
            "remittance", "206c", "upwork", "ay ", "assessment year", "234f",
            "belated return", "itat", "cit(a)", "80c", "80ccd",
            "nps", "capital gains", "54f", "143(2)",
            "freelance", "freelancer", "consultant", "professional income",
        ))
        income_tax_context = income_tax_context or (
            _has_any(q, ("assessment order", "143(3)", "section 143", "commissioner appeals"))
            and not _has_any(q, ("gst", "cgst", "gstr"))
        )
        income_tax_context = income_tax_context or (
            _has_any(q, ("gst", "cgst", "register gst", "registration"))
            and _has_any(q, ("income", "professional income", "freelance", "freelancer", "consultant"))
        )
        if income_tax_context:
            tax_search = "Income-tax Act 1961 section 234F late filing fee return of income belated return"
            tax_anchors = ("/sec-234F", "/sec-139")
            tax_priority = 1.0
            if _has_any(q, ("80c", "80ccd", "nps")):
                tax_search = "Income-tax Act 1961 section 80C section 80CCD National Pension System deduction"
                tax_anchors = ("/sec-80C", "/sec-80CCD")
                tax_priority = 1.06
            elif _has_any(q, ("capital gains", "54f", "sale of flat")):
                tax_search = "Income-tax Act 1961 section 45 capital gains section 54F exemption sale of flat"
                tax_anchors = ("/sec-45", "/sec-54F", "/sec-54")
                tax_priority = 1.06
            elif _has_any(q, ("tcs", "foreign remittance", "remittance", "206c")):
                tax_search = "Income-tax Act 1961 section 206C tax collected at source foreign remittance section 139 return refund"
                tax_anchors = ("/sec-206C", "/sec-139", "/sec-237")
                tax_priority = 1.06
            elif _has_any(q, ("tds", "upwork", "194c", "194j")):
                tax_search = "Income-tax Act 1961 section 194C section 194J tax deducted at source return of income section 139 refund"
                tax_anchors = ("/sec-194C", "/sec-194J", "/sec-139", "/sec-237")
                tax_priority = 1.06
            elif _has_any(q, ("143(2)", "section 143(2)")):
                tax_search = "Income-tax Act 1961 section 143 notice assessment response"
                tax_anchors = ("/sec-143",)
                tax_priority = 1.06
            elif _has_any(q, ("refund stuck", "processed no refund", "income tax refund", "refund not received")):
                tax_search = "Income-tax Act 1961 section 237 refund of tax section 244A interest on refund"
                tax_anchors = ("/sec-237", "/sec-244A")
                tax_priority = 1.05
            elif _has_any(q, ("cit(a)", "commissioner appeals")):
                tax_search = "Income-tax Act 1961 section 246A appeal Commissioner Appeals section 249 limitation"
                tax_anchors = ("/sec-246A", "/sec-249")
                tax_priority = 1.05
            elif _has_any(q, ("itat", "appellate tribunal")):
                tax_search = "Income-tax Act 1961 section 253 appeal Appellate Tribunal ITAT limitation"
                tax_anchors = ("/sec-253", "/sec-254")
                tax_priority = 1.05
            elif _has_any(q, ("appeal", "assessment order", "143(3)", "section 143")):
                tax_search = "Income-tax Act 1961 section 246A section 249 appeal assessment order limitation"
                tax_anchors = ("/sec-246A", "/sec-249", "/sec-253")
                tax_priority = 1.04
            packs.append(SourcePack(
                id="income_tax_1961",
                title_patterns=("Income-tax Act 1961", "Income Tax Act 1961"),
                search_query=tax_search,
                doc_ids=("income-tax-1961",),
                anchor_patterns=tax_anchors,
                priority=tax_priority,
            ))

    elif category == "labour_compliance":
        if _has_labour_overtime_register_context(q):
            packs.append(SourcePack(
                id="maharashtra_shops_establishments_2017",
                title_patterns=(
                    "Maharashtra Shops and Establishments (Regulation of Employment and Conditions of Service) Act 2017",
                    "Maharashtra Shops and Establishments",
                ),
                search_query="Maharashtra Shops and Establishments Act 2017 section 15 overtime section 25 registers records section 28 facilitator inspection section 31 refusal to produce register",
                doc_ids=("maharashtra-shops-establishments-2017",),
                anchor_patterns=("/sec-1", "/sec-15", "/sec-25", "/sec-28", "/sec-31"),
                priority=1.18,
            ))
        if _has_overtime_register_inspection_context(q) and _has_construction_worksite_context(q):
            packs.append(SourcePack(
                id="bocw_1996",
                title_patterns=("Building and Other Construction Workers (Regulation of Employment and Conditions of Service) Act 1996",),
                search_query="Building and Other Construction Workers Act 1996 registration employer compliance labour department inspection records overtime construction workers",
                doc_ids=("bocw-1996",),
                anchor_patterns=("/sec-12", "/sec-28", "/sec-39", "/sec-40"),
                priority=1.08,
            ))
        if _has_any(q, ("code on wages", "minimum wage", "minimum wages", "wage notification", "state rate", "unskilled")):
            packs.append(SourcePack(
                id="code_on_wages_2019",
                title_patterns=("Code on Wages 2019",),
                search_query="Code on Wages 2019 section 5 minimum wages section 6 fixation section 8 revision section 9 floor wage",
                doc_ids=("code-on-wages-2019",),
                anchor_patterns=("/sec-5", "/sec-6", "/sec-8", "/sec-9"),
                priority=1.12,
            ))
        if _has_any(q, ("esi", "esic", "employees state insurance", "employees' state insurance", "contribution", "casual workers")):
            packs.append(SourcePack(
                id="esi_1948",
                title_patterns=("Employees' State Insurance Act 1948", "Employees State Insurance Act 1948"),
                search_query="Employees State Insurance Act 1948 contribution employer inspection determination ESI Court section 40 section 45A section 75",
                doc_ids=("esi-1948",),
                anchor_patterns=("/sec-40", "/sec-43", "/sec-75"),
                priority=1.08,
            ))
            packs.append(SourcePack(
                id="social_security_code_2020",
                title_patterns=("Code on Social Security 2020",),
                search_query="Code on Social Security 2020 social security contribution employer employee inspection assessment",
                doc_ids=("social-security-code-2020",),
                priority=0.9,
            ))

    elif category == "manual_scavenging_safety":
        packs.append(SourcePack(
            id="manual_scavenging_2013",
            title_patterns=("Prohibition of Employment as Manual Scavengers and their Rehabilitation Act 2013",),
            search_query="Prohibition of Employment as Manual Scavengers and their Rehabilitation Act 2013 hazardous cleaning sewer septic tank compensation rehabilitation",
            doc_ids=("manual-scavenging-2013",),
            anchor_patterns=("/sec-2", "/sec-5", "/sec-7", "/sec-13", "/sec-22", "/sec-23"),
            priority=1.1,
        ))
        packs.append(SourcePack(
            id="employees_compensation_1923",
            title_patterns=("Employees' Compensation Act 1923", "Workmen's Compensation Act 1923"),
            search_query="Employees Compensation Act 1923 death injury accident compensation employer dependant commissioner",
            doc_ids=("employees-compensation-1923",),
            anchor_patterns=("/sec-3", "/sec-4", "/sec-10"),
            priority=1.02,
        ))
        packs.append(_bnss_pack(q))
        packs.append(_bns_pack(q))

    elif category == "trademark_ip":
        if _has_any(q, ("opposed", "opposition", "counter statement", "counter-statement", "hearing", "journal", "advertised", "application opposed", "trademark application", "trade mark application")):
            packs.append(SourcePack(
                id="trade_marks_1999_opposition",
                title_patterns=("Trade Marks Act 1999", "The Trade Marks Act, 1999"),
                search_query="Trade Marks Act 1999 section 21 opposition registration notice counter statement evidence hearing Trade Marks Registry",
                doc_ids=("trade-marks-1999",),
                anchor_patterns=("/sec-21",),
                priority=1.22,
            ))
            packs.append(SourcePack(
                id="trade_marks_1999",
                title_patterns=("Trade Marks Act 1999", "The Trade Marks Act, 1999"),
                search_query="Trade Marks Act 1999 section 11 relative grounds similar mark confusion opposition",
                doc_ids=("trade-marks-1999",),
                anchor_patterns=("/sec-11",),
                priority=1.16,
            ))
        else:
            packs.append(SourcePack(
                id="trade_marks_1999",
                title_patterns=("Trade Marks Act 1999", "The Trade Marks Act, 1999"),
                search_query="Trade Marks Act 1999 section 11 relative grounds section 29 infringement similar mark confusion",
                doc_ids=("trade-marks-1999",),
                anchor_patterns=("/sec-11", "/sec-29"),
                priority=1.16,
            ))
        if _has_any(q, ("copyright", "song", "video", "script", "software", "unlicensed")):
            packs.append(SourcePack(
                id="copyright_1957",
                title_patterns=("Copyright Act 1957",),
                search_query="Copyright Act 1957 infringement section 51 section 52 remedies original work",
                doc_ids=("copyright-1957",),
            ))

    elif category == "education_loan_denial":
        packs.append(SourcePack(
            id="rbi_integrated_ombudsman_2021",
            title_patterns=(
                "Reserve Bank Integrated Ombudsman Scheme 2021",
                "Reserve Bank - Integrated Ombudsman Scheme 2021",
            ),
            search_query="Reserve Bank Integrated Ombudsman Scheme 2021 bank education loan complaint deficiency in service",
            doc_ids=("rbi-integrated-ombudsman-2021",),
            priority=1.10,
        ))
        packs.append(SourcePack(
            id="consumer_protection_2019",
            title_patterns=("Consumer Protection Act 2019",),
            search_query="Consumer Protection Act 2019 banking service deficiency complaint education loan",
            doc_ids=("consumer-protection-2019",),
            anchor_patterns=("/sec-2-", "/sec-35", "/sec-38"),
            priority=1.04,
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
        gig_context = _has_any(q, ("zomato", "swiggy", "uber", "ola", "rider", "driver", "gig", "platform worker", "delivery partner"))
        if gig_context:
            motor_priority = 1.07 if _has_any(q, ("accident", "scooter", "bike", "road", "vehicle", "hit", "injury", "insurance")) else 0.98
            packs.append(SourcePack(
                id="social_security_code_2020",
                title_patterns=("Code on Social Security 2020",),
                search_query="Code on Social Security 2020 gig worker platform worker accident insurance social security",
                doc_ids=("social-security-code-2020",),
                anchor_patterns=("/sec-112", "/sec-113", "/sec-114", "/sec-141"),
                priority=0.98 if motor_priority > 1.0 else 1.05,
            ))
            packs.append(SourcePack(
                id="motor_vehicles_1988",
                title_patterns=("Motor Vehicles Act 1988",),
                search_query="Motor Vehicles Act 1988 motor accident insurance claims tribunal compensation",
                doc_ids=("motor-vehicles-1988",),
                anchor_patterns=("/sec-146", "/sec-147", "/sec-164", "/sec-165", "/sec-166"),
                priority=motor_priority,
            ))
        if _has_any(q, ("beat", "beaten", "assault", "head injury", "head", "mukadam", "contractor beat")):
            packs.append(_bns_pack(q))
            packs.append(_bnss_pack(q))
            if _has_any(q, ("wage", "wages", "old wages", "salary", "payment")):
                packs.append(SourcePack(
                    id="code_on_wages_2019",
                    title_patterns=("Code on Wages 2019",),
                    search_query="Code on Wages 2019 payment of wages employee dues wage authority",
                    doc_ids=("code-on-wages-2019",),
                    anchor_patterns=("/sec-17", "/sec-18", "/sec-45"),
                    priority=1.02,
                ))
        construction_context = _has_any(q, (
            "construction", "bocw", "bocw card", "building", "mason",
            "scaffold", "scaffolding", "fell from",
        )) or (_has_any(q, ("site", "worksite")) and _has_any(q, ("thekedar", "contractor")))
        if construction_context:
            packs.append(SourcePack(
                id="bocw_1996",
                title_patterns=("Building and Other Construction Workers (Regulation of Employment and Conditions of Service) Act 1996",),
                search_query="Building and Other Construction Workers Act 1996 welfare board registration safety accident injury construction worker no BOCW card",
                doc_ids=("bocw-1996",),
                anchor_patterns=("/sec-12", "/sec-13", "/sec-14", "/sec-39", "/sec-40"),
                priority=1.12,
            ))
        if not gig_context:
            packs.append(SourcePack(
                id="employees_compensation_1923",
                title_patterns=("Employees' Compensation Act 1923", "Workmen's Compensation Act 1923"),
                search_query="Employees Compensation Act 1923 personal injury accident death arising out of employment compensation",
                doc_ids=("employees-compensation-1923",),
                anchor_patterns=("/sec-3", "/sec-4", "/sec-10"),
                priority=1.04,
            ))
            packs.append(SourcePack(
                id="factories_1948",
                title_patterns=("Factories Act 1948",),
                search_query="Factories Act 1948 safety accident injury occupier inspector worker",
                doc_ids=("factories-1948",),
            ))

    elif category == "employment_wages":
        if _has_any(q, (
            "give up wages", "waive wages", "waiver of wages", "signed paper",
            "signed document", "signed form",
        )):
            packs.append(SourcePack(
                id="code_on_wages_2019_contracting_out",
                title_patterns=("Code on Wages 2019",),
                search_query="Code on Wages 2019 section 60 contracting out relinquishes right amount minimum wages agreement null void section 45 claims",
                doc_ids=("code-on-wages-2019",),
                anchor_patterns=("/sec-60", "/sec-61", "/sec-45"),
                priority=1.24,
            ))
            packs.append(SourcePack(
                id="indian_contract_1872_free_consent",
                title_patterns=("Indian Contract Act 1872",),
                search_query="Indian Contract Act 1872 section 19 voidability agreement without free consent coercion fraud misrepresentation",
                doc_ids=("indian-contract-1872",),
                anchor_patterns=("/sec-19",),
                priority=1.10,
            ))
        if _has_gig_platform_work_context(q):
            packs.append(SourcePack(
                id="social_security_code_2020_gig_platform",
                title_patterns=("Code on Social Security 2020",),
                search_query="Code on Social Security 2020 Chapter IX gig worker platform worker registration social security schemes aggregator contribution",
                doc_ids=("social-security-code-2020",),
                anchor_patterns=("/sec-112", "/sec-113", "/sec-114", "/sec-141"),
                priority=1.20,
            ))
            packs.append(SourcePack(
                id="industrial_disputes_1947_platform_status",
                title_patterns=("Industrial Disputes Act 1947",),
                search_query="Industrial Disputes Act 1947 retrenchment termination workman employee platform worker status section 25F labour court",
                doc_ids=("industrial-disputes-1947",),
                anchor_patterns=("/sec-2", "/sec-25F"),
                priority=0.96,
            ))
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
        if _has_any(q, ("esi", "esic", "employees state insurance", "employees' state insurance")):
            packs.append(SourcePack(
                id="esi_1948",
                title_patterns=("Employees' State Insurance Act 1948", "Employees State Insurance Act 1948"),
                search_query="Employees State Insurance Act 1948 contribution employer employee casual worker ESI Court section 40 section 45A section 75",
                doc_ids=("esi-1948",),
                anchor_patterns=("/sec-40", "/sec-43", "/sec-75"),
                priority=1.06,
            ))
        if _has_any(q, (
            "termination", "fired", "retrench", "retrenched", "retrenchment",
            "layoff", "lay off", "labour court", "forced resign",
            "forced resignation", "pip", "performance improvement plan",
            "bad rating", "retaliation", "performance issue",
        )):
            id_search = "Industrial Disputes Act 1947 section 25F section 25N retrenchment compensation prior permission labour court termination"
            id_anchors = ("/sec-25F", "/sec-25N")
            if _has_any(q, ("kept", "same site", "same work", "junior", "last in first out", "25g", "25h", "re-employ", "reemploy")):
                id_search = "Industrial Disputes Act 1947 section 25F section 25G last come first go section 25H re employment retrenched workmen"
                id_anchors = ("/sec-25F", "/sec-25G", "/sec-25H")
                packs.append(SourcePack(
                    id="industrial_disputes_1947_lifo",
                    title_patterns=("Industrial Disputes Act 1947",),
                    search_query="Industrial Disputes Act 1947 section 25G procedure for retrenchment last come first go category workmen",
                    doc_ids=("industrial-disputes-1947",),
                    anchor_patterns=("sec-25G",),
                    priority=1.14,
                ))
                packs.append(SourcePack(
                    id="industrial_disputes_1947_reemployment",
                    title_patterns=("Industrial Disputes Act 1947",),
                    search_query="Industrial Disputes Act 1947 section 25H re employment of retrenched workmen employer proposes to employ persons",
                    doc_ids=("industrial-disputes-1947",),
                    anchor_patterns=("sec-25H",),
                    priority=1.12,
                ))
            packs.append(SourcePack(
                id="industrial_disputes_1947",
                title_patterns=("Industrial Disputes Act 1947",),
                search_query=id_search,
                doc_ids=("industrial-disputes-1947",),
                anchor_patterns=id_anchors,
            ))
            if _has_any(q, ("bengali", "gujarati", "hindi speaker", "racist", "language", "migrant", "outsider", "go back")):
                packs.append(SourcePack(
                    id="constitution_article_14",
                    title_patterns=("Constitution of India",),
                    search_query="Constitution of India Article 14 equality before law non discrimination employment retrenchment language migrant",
                    doc_ids=("constitution-india",),
                    anchor_patterns=("/sec-14",),
                    priority=1.02,
                ))
        if _has_any(q, ("posh", "sexual harassment", "icc", "internal committee", "local committee")) and _has_any(q, ("pip", "retaliation", "bad rating", "performance", "complaint")):
            packs.append(SourcePack(
                id="posh_2013",
                title_patterns=("Sexual Harassment of Women at Workplace Act 2013",),
                search_query="Sexual Harassment of Women at Workplace Act 2013 employer duties Internal Committee retaliation workplace harassment complaint",
                doc_ids=("posh-2013",),
                anchor_patterns=("/sec-3", "/sec-4", "/sec-9", "/sec-19"),
                priority=1.04,
            ))
        if "maternity" in q:
            packs.append(SourcePack(
                id="maternity_benefit_1961",
                title_patterns=("Maternity Benefit Act 1961",),
                search_query="Maternity Benefit Act 1961 section 5 section 12 maternity leave dismissal",
                doc_ids=("maternity-benefit-1961",),
            ))
        if _has_contract_labour_wage_context(q):
            packs.extend(_contract_labour_wage_packs(q))
        if _has_labour_overtime_register_context(q):
            packs.append(SourcePack(
                id="maharashtra_shops_establishments_2017",
                title_patterns=(
                    "Maharashtra Shops and Establishments (Regulation of Employment and Conditions of Service) Act 2017",
                    "Maharashtra Shops and Establishments",
                ),
                search_query="Maharashtra Shops and Establishments Act 2017 overtime wages registers records labour department inspection",
                doc_ids=("maharashtra-shops-establishments-2017",),
                anchor_patterns=("/sec-1", "/sec-15", "/sec-25", "/sec-28", "/sec-31"),
                priority=1.16,
            ))
        if _has_overtime_register_inspection_context(q) and _has_construction_worksite_context(q):
            packs.append(SourcePack(
                id="bocw_1996",
                title_patterns=("Building and Other Construction Workers (Regulation of Employment and Conditions of Service) Act 1996",),
                search_query="Building and Other Construction Workers Act 1996 registration employer compliance labour inspection construction workers",
                doc_ids=("bocw-1996",),
                anchor_patterns=("/sec-12", "/sec-28", "/sec-39", "/sec-40"),
                priority=1.06,
            ))
        if _has_any(q, ("salary", "wages", "minimum wage", "overtime", "contractor", "full and final", "final settlement", "dues", "id blocked", "notice period")):
            packs.append(SourcePack(
                id="code_on_wages_2019",
                title_patterns=("Code on Wages 2019",),
                search_query="Code on Wages 2019 minimum wages payment of wages overtime employee dues wage authority",
                doc_ids=("code-on-wages-2019",),
                anchor_patterns=("/sec-17", "/sec-18", "/sec-43", "/sec-45"),
                priority=1.02,
            ))
        if _has_any(q, ("notice period", "offer letter", "appointment letter", "employment contract", "bond", "resignation", "full and final")):
            packs.append(SourcePack(
                id="indian_contract_1872",
                title_patterns=("Indian Contract Act 1872",),
                search_query="Indian Contract Act 1872 performance of contract breach compensation notice period employment contract",
                doc_ids=("indian-contract-1872",),
                anchor_patterns=("/sec-37", "/sec-73"),
                priority=0.94,
            ))

    elif category == "property_tenancy":
        packs.append(SourcePack(
            id="transfer_property_1882",
            title_patterns=("Transfer of Property Act 1882",),
            search_query="Transfer of Property Act 1882 gift deed transfer joint ownership section 45 section 122 section 126 revocation",
            doc_ids=("transfer-of-property-1882",),
            anchor_patterns=("/sec-45", "/sec-122", "/sec-123", "/sec-126"),
            priority=1.08,
        ))
        if _has_any(q, ("father", "mother", "daughter", "son", "brother", "sister", "heir", "share", "verbal", "verbally", "before death", "after death")):
            packs.append(SourcePack(
                id="hindu_succession_1956",
                title_patterns=("Hindu Succession Act 1956",),
                search_query="Hindu Succession Act 1956 intestate succession daughter son heir property share",
                doc_ids=("hindu-succession-1956",),
                anchor_patterns=("/sec-6", "/sec-8", "/sec-10", "/sec-14", "/sec-15"),
                priority=1.04,
            ))
        if _has_any(q, ("registered", "registration", "sale deed", "gift deed", "registered gift", "stamp")):
            packs.append(SourcePack(
                id="registration_1908",
                title_patterns=("Registration Act 1908",),
                search_query="Registration Act 1908 compulsory registration gift deed sale deed effect of non registration",
                doc_ids=("registration-1908",),
                anchor_patterns=("/sec-17", "/sec-23", "/sec-49"),
                priority=1.02,
            ))
        if _has_any(q, ("specific performance", "injunction", "possession", "cancel", "cancellation", "set aside", "challenge")):
            packs.append(SourcePack(
                id="specific_relief_1963",
                title_patterns=("Specific Relief Act 1963",),
                search_query="Specific Relief Act 1963 cancellation of instruments declaratory relief injunction possession",
                doc_ids=("specific-relief-1963",),
                anchor_patterns=("/sec-31", "/sec-34", "/sec-38"),
                priority=0.96,
            ))
        if _has_any(q, ("thumb impression", "blank paper", "under pressure", "coercion", "undue influence", "fraud", "didn't sign", "did not sign")):
            packs.append(SourcePack(
                id="indian_contract_1872",
                title_patterns=("Indian Contract Act 1872",),
                search_query="Indian Contract Act 1872 consent coercion undue influence fraud voidable agreement",
                doc_ids=("indian-contract-1872",),
                anchor_patterns=("/sec-14", "/sec-15", "/sec-16", "/sec-17", "/sec-19"),
                priority=0.94,
            ))

    elif category == "business_license_compliance":
        if _has_any(q, (
            "auto permit", "taxi permit", "cab permit", "transport permit",
            "permit renewal", "permit expired", "auto driver", "taxi driver",
            "cab driver", "traffic police", "challan", "license invalid",
            "licence invalid", "driving license", "driving licence",
        )):
            motor_search = "Motor Vehicles Act 1988 section 74 contract carriage permit renewal Regional Transport Authority"
            motor_anchors = ("/sec-66", "/sec-74", "/sec-80", "/sec-86")
            if _has_any(q, ("traffic police", "challan", "license invalid", "licence invalid", "driving license", "driving licence", "no challan")):
                motor_search = "Motor Vehicles Act 1988 driving licence validity traffic challan enforcement penalty"
                motor_anchors = ("/sec-3", "/sec-19", "/sec-130", "/sec-200", "/sec-206")
            packs.append(SourcePack(
                id="motor_vehicles_1988",
                title_patterns=("Motor Vehicles Act 1988",),
                search_query=motor_search,
                doc_ids=("motor-vehicles-1988",),
                anchor_patterns=motor_anchors,
                priority=1.08,
            ))
            if _has_any(q, ("bribe", "taking 500", "taking money", "no challan", "pay 500", "paying 500")):
                packs.append(SourcePack(
                    id="prevention_corruption_1988",
                    title_patterns=("Prevention of Corruption Act 1988",),
                    search_query="Prevention of Corruption Act 1988 undue advantage public servant bribed bribing report compelled bribe section 7 section 8",
                    doc_ids=("prevention-of-corruption-1988",),
                    anchor_patterns=("/sec-7", "/sec-8"),
                    priority=1.06,
                ))
        if _has_any(q, ("fssai", "food", "snack", "kirana", "adulteration", "misbranding", "designated officer")):
            food_search = "Food Safety and Standards Act 2006 food business operator licence registration FSSAI standards notice"
            food_anchors = ("/sec-31", "/sec-32", "/sec-63")
            if _has_any(q, ("adulteration", "misbranding", "sample", "food safety officer", "designated officer", "improvement notice")):
                food_search = "Food Safety and Standards Act 2006 section 26 food business operator responsibilities section 32 improvement notice section 42 sample section 50 misbranded food section 59 unsafe food"
                food_anchors = ("/sec-26", "/sec-32", "/sec-42", "/sec-50", "/sec-59")
            packs.append(SourcePack(
                id="food_safety_2006",
                title_patterns=("Food Safety and Standards Act 2006",),
                search_query=food_search,
                doc_ids=("food-safety-standards-2006",),
                anchor_patterns=food_anchors,
                priority=1.08,
            ))
        if _has_any(q, ("drug inspector", "drugs inspector", "medical store", "pharmacy", "chemist", "schedule h", "without prescription")):
            packs.append(SourcePack(
                id="drugs_cosmetics_1940",
                title_patterns=("Drugs and Cosmetics Act 1940",),
                search_query="Drugs and Cosmetics Act 1940 section 18 manufacture sale drugs section 22 powers of inspectors section 23 procedure of inspectors samples",
                doc_ids=("drugs-cosmetics-1940",),
                anchor_patterns=("/sec-18", "/sec-22", "/sec-23", "/sec-27"),
                priority=1.10,
            ))
        if _has_any(q, ("shop act", "shop license", "shops act", "shops and establishment", "labour inspector", "trade license", "licence renewal", "license renewal")):
            packs.append(_rti_pack())

    elif category == "labour_exploitation_discrimination":
        if _has_any(q, ("asha worker", "asha", "honorarium", "incentive", "nhm", "nrhm")):
            packs.append(SourcePack(
                id="nhm_asha_incentives_2025",
                title_patterns=("National Health Mission ASHA Incentives Guidelines 2025",),
                search_query="National Health Mission ASHA incentives guidelines honorarium payment grievance ASHA worker",
                doc_ids=("nhm-asha-incentives-2025",),
                priority=1.12,
            ))
        if _has_contract_labour_wage_context(q):
            packs.extend(_contract_labour_wage_packs(q))
        if _has_any(q, ("child", "minor", "girl 15", "boy 15", "15 working", "16 working", "17 working", "under 18")) or _has_child_age_context(q):
            packs.append(SourcePack(
                id="child_labour_1986",
                title_patterns=("Child and Adolescent Labour (Prohibition and Regulation) Act 1986", "Child Labour (Prohibition and Regulation) Act 1986"),
                search_query="Child and Adolescent Labour Prohibition Regulation Act 1986 prohibition child labour adolescent hazardous occupation inspector",
                doc_ids=("child-labour-1986",),
                anchor_patterns=("/sec-3", "/sec-3A", "/sec-14"),
                priority=1.08,
            ))
            packs.append(SourcePack(
                id="jj_2015",
                title_patterns=("Juvenile Justice (Care and Protection of Children) Act 2015",),
                search_query="Juvenile Justice Act 2015 child in need of care and protection child labour rescue Child Welfare Committee",
                doc_ids=("jj-2015",),
                anchor_patterns=("/sec-2", "/sec-27", "/sec-31", "/sec-36"),
                priority=1.04,
            ))
        if _has_any(q, ("bocw", "construction worker", "construction 8 years", "building worker", "mason")):
            packs.append(SourcePack(
                id="bocw_1996",
                title_patterns=("Building and Other Construction Workers (Regulation of Employment and Conditions of Service) Act 1996",),
                search_query="Building and Other Construction Workers Act 1996 section 12 registration section 13 identity card section 14 cessation welfare board construction worker benefits",
                doc_ids=("bocw-1996",),
                anchor_patterns=("/sec-12", "/sec-13", "/sec-14"),
                priority=1.08,
            ))
            if _has_any(q, ("cess", "levy", "collection")):
                packs.append(SourcePack(
                    id="bocw_cess_1996",
                    title_patterns=("Building and Other Construction Workers Welfare Cess Act 1996",),
                    search_query="Building and Other Construction Workers Welfare Cess Act 1996 section 3 levy collection cess construction cost",
                    doc_ids=("bocw-cess-1996",),
                    anchor_patterns=("/sec-3", "/sec-4"),
                    priority=1.04,
                ))
            if _has_any(q, ("cheating", "fraud", "fake", "same name", "false register", "cess")):
                packs.append(_bns_pack(q))
                packs.append(_bnss_pack(q))
        if _has_any(q, (
            "ismw", "inter-state migrant workmen", "inter state migrant workmen",
            "migrant registration", "migrant worker", "inter state migrant",
            "inter-state migrant", "displacement allowance", "came together",
            "brought from", "return ticket", "go back home", "walked from",
            "journey allowance",
        )):
            packs.append(SourcePack(
                id="ismw_1979",
                title_patterns=("Inter-State Migrant Workmen (Regulation of Employment and Conditions of Service) Act 1979",),
                search_query="Inter-State Migrant Workmen Act 1979 registration contractor licence displacement allowance journey allowance wages duties",
                doc_ids=("ismw-1979",),
                anchor_patterns=("/sec-4", "/sec-6", "/sec-12", "/sec-14", "/sec-15", "/sec-16"),
                priority=1.08,
            ))
            packs.append(SourcePack(
                id="code_on_wages_2019",
                title_patterns=("Code on Wages 2019",),
                search_query="Code on Wages 2019 migrant worker wage register contractor employee records",
                doc_ids=("code-on-wages-2019",),
                anchor_patterns=("/sec-17", "/sec-45"),
                priority=0.96,
            ))
        if _has_any(q, ("nrega", "mgnrega", "job card", "mate", "muster roll", "bdo", "mukhiya", "social audit", "sarpanch", "gram sabha")):
            packs.append(SourcePack(
                id="mgnrega_2005",
                title_patterns=("Mahatma Gandhi National Rural Employment Guarantee Act 2005",),
                search_query="Mahatma Gandhi National Rural Employment Guarantee Act 2005 job card wage payment unemployment allowance grievance",
                doc_ids=("mgnrega-2005",),
                anchor_patterns=("/sec-3@", "/sec-6@", "/sec-17@", "/sec-19@", "/sec-23@"),
            ))
        if _has_any(q, (
            "wage", "wages", "salary", "half pay", "contractor", "minimum",
            "domestic worker", "madam not paying", "factory deducted",
            "deducted 800", "wage deducted", "uniform never given", "shoes uniform",
            "no payment", "never paid", "not paid", "displacement allowance",
            "journey allowance", "munshi", "labour", "worker", "working",
        )):
            wage_search = "Code on Wages 2019 minimum wages payment of wages contractor employee"
            wage_anchors = ("/sec-17", "/sec-18", "/sec-21", "/sec-43", "/sec-45")
            if _has_any(q, ("minimum wage", "minimum wages", "state rate", "unskilled")):
                wage_search = "Code on Wages 2019 section 6 fixation of minimum wages section 7 components section 8 revision section 9 floor wage section 45 claims"
                wage_anchors = ("/sec-6", "/sec-7", "/sec-8", "/sec-9", "/sec-45")
            packs.append(SourcePack(
                id="code_on_wages_2019",
                title_patterns=("Code on Wages 2019",),
                search_query=wage_search,
                doc_ids=("code-on-wages-2019",),
                anchor_patterns=wage_anchors,
            ))

    elif category == "banking_credit_dispute":
        if _has_any(q, ("security cheque", "post dated cheque", "post-dated cheque", "cheque", "cheques")) and _has_any(q, ("misuse", "misusing", "landlord", "security", "notice under 138")):
            packs.append(SourcePack(
                id="ni_act_138_security_cheque",
                title_patterns=("Negotiable Instruments Act 1881",),
                search_query="Negotiable Instruments Act 1881 section 138 cheque discharge debt liability payee notice drawer fifteen days",
                doc_ids=("negotiable-instruments-1881",),
                anchor_patterns=("/sec-138",),
                priority=1.18,
            ))
            packs.append(_ni_act_cheque_pack(priority=1.10))
        agri_recovery_context = _has_any(q, (
            "crop loan", "agri loan", "agricultural loan", "farm loan", "kisan loan",
            "agricultural development bank", "land mortgage bank",
            "buffalo", "livestock", "tractor",
        ))
        if agri_recovery_context:
            packs.append(SourcePack(
                id="cooperative_bank_recovery_case_law",
                title_patterns=("COOPERATIVE AGRICULTURAL DEVELOPMENT BANK", "COOPERATIVE LAND MORTGAGE BANK", "REGISTRAR,COOPERATIVE SOCIETIES"),
                search_query="cooperative agricultural bank crop loan recovery livestock seizure registrar cooperative societies",
                doc_ids=("2022-insc-34", "2022-insc-1084", "2014-insc-971"),
                source_types=("sc_judgment",),
                priority=1.08,
            ))
            packs.append(SourcePack(
                id="sarfaesi_2002",
                title_patterns=("Securitisation and Reconstruction of Financial Assets and Enforcement of Security Interest Act 2002",),
                search_query="SARFAESI Act 2002 section 31 provisions not apply pledge movables agricultural land section 13 secured asset enforcement section 17 DRT",
                doc_ids=("sarfaesi-2002",),
                anchor_patterns=("/sec-31", "/sec-13", "/sec-17"),
                priority=1.06,
            ))
        if _has_any(q, ("sarfaesi", "13(2)", "security interest", "possession notice", "home loan default")):
            packs.append(SourcePack(
                id="sarfaesi_2002",
                title_patterns=("Securitisation and Reconstruction of Financial Assets and Enforcement of Security Interest Act 2002",),
                search_query="SARFAESI Act 2002 section 13(2) demand notice section 13(4) possession section 17 DRT appeal",
                doc_ids=("sarfaesi-2002",),
                anchor_patterns=("/sec-13", "/sec-17"),
                priority=1.1,
            ))
        fd_nominee_context = _has_any(q, (
            "fixed deposit", "fd ", " fd", "fd of", "fd not", "fd account",
            "nominee", "depositor", "deposit not honoured", "not honoured",
        ))
        banking_search = "Banking Regulation Act 1949 cooperative bank depositor fixed deposit banking company"
        banking_anchors: tuple[str, ...] = ()
        if fd_nominee_context:
            banking_search = "Banking Regulation Act 1949 section 45ZA nomination depositor death fixed deposit nominee payment"
            banking_anchors = ("/sec-45ZA",)
        packs.append(SourcePack(
            id="banking_regulation_1949",
            title_patterns=("Banking Regulation Act 1949",),
            search_query=banking_search,
            doc_ids=("banking-regulation-1949",),
            anchor_patterns=banking_anchors,
            priority=1.16 if fd_nominee_context else 1.04,
        ))
        if fd_nominee_context or _has_any(q, (
            "ombudsman", "rbi", "cms.rbi", "fair practices", "deficiency in service",
            "recovery agent", "recovery agents", "customer liability", "bank complaint",
            "nbfc complaint", "credit card complaint", "education loan", "student loan",
            "emi", "bank error", "bounced", "bounce", "penalty", "nbfc", "bajaj finserv",
            "loan app", "finance company", "threatening cibil", "threaten cibil",
        )):
            packs.append(SourcePack(
                id="rbi_integrated_ombudsman_2021",
                title_patterns=(
                    "Reserve Bank Integrated Ombudsman Scheme 2021",
                    "Reserve Bank - Integrated Ombudsman Scheme 2021",
                ),
                search_query="Reserve Bank Integrated Ombudsman Scheme 2021 bank NBFC customer complaint ombudsman deficiency in service",
                doc_ids=("rbi-integrated-ombudsman-2021",),
                anchor_patterns=("/sec-2", "/sec-3"),
                priority=1.08,
            ))
        if _has_any(q, (
            "cibil", "credit score", "credit report", "credit bureau",
            "credit information", "wrong loan", "wrong entry",
        )):
            packs.append(SourcePack(
                id="credit_information_companies_2005",
                title_patterns=("Credit Information Companies (Regulation) Act 2005",),
                search_query="Credit Information Companies Regulation Act 2005 CIBIL credit report correction dispute privacy",
                doc_ids=("credit-information-companies-2005",),
                anchor_patterns=("/sec-18", "/sec-19", "/sec-20", "/sec-21", "/sec-22"),
                priority=1.08,
            ))
        packs.append(SourcePack(
            id="consumer_protection_2019",
            title_patterns=("Consumer Protection Act 2019",),
            search_query="Consumer Protection Act 2019 banking service deficiency fixed deposit nominee complaint",
            doc_ids=("consumer-protection-2019",),
            anchor_patterns=("/sec-2", "/sec-35", "/sec-38"),
            priority=1.14 if fd_nominee_context else 1.02,
        ))

    elif category == "social_welfare_identity":
        if _has_caste_certificate_context(q):
            packs.append(SourcePack(
                id="constitution_article_341_342",
                title_patterns=("Constitution of India",),
                search_query="Constitution of India Article 341 Scheduled Castes Article 342 Scheduled Tribes caste certificate state list",
                doc_ids=("constitution-india",),
                anchor_patterns=("/sec-341", "/sec-342"),
                priority=1.20,
            ))
            packs.append(_rti_pack())
        trans_negation = _has_any(q, ("not gender change", "not a gender change", "not changing gender"))
        trans_identity_context = (not trans_negation) and _has_any(q, (
            "transgender", "trans woman", "transwoman", "trans man", "transman",
            "change my gender", "gender change", "gender on aadhaar", "gender on aadhar",
            "gender on 10th", "gender on certificate",
        ))
        if trans_identity_context:
            trans_search = "Transgender Persons Protection of Rights Act 2019 section 6 certificate of identity transgender self perceived gender District Magistrate"
            trans_anchors = ("/sec-6", "/sec-4", "/sec-5")
            trans_priority = 1.22
            if not _has_any(q, ("not had surgery", "without surgery", "no surgery")):
                trans_search = "Transgender Persons Protection of Rights Act 2019 certificate identity section 6 revised certificate section 7 gender"
                trans_anchors = ("/sec-6", "/sec-7", "/sec-4", "/sec-5")
                trans_priority = 1.16
            packs.append(SourcePack(
                id="transgender_2019",
                title_patterns=("Transgender Persons (Protection of Rights) Act 2019",),
                search_query=trans_search,
                doc_ids=("transgender-2019",),
                anchor_patterns=trans_anchors,
                priority=trans_priority,
            ))
            if _has_any(q, ("surgery", "medical intervention", "revised certificate")):
                packs.append(SourcePack(
                    id="transgender_2019_revised_certificate",
                    title_patterns=("Transgender Persons (Protection of Rights) Act 2019",),
                    search_query="Transgender Persons Protection of Rights Act 2019 section 7 revised certificate medical intervention",
                    doc_ids=("transgender-2019",),
                    anchor_patterns=("/sec-7",),
                    priority=0.94,
                ))
        if _has_any(q, ("birth certificate", "birth registration", "death certificate", "born at home", "home birth")):
            packs.append(_rti_pack())
        if _has_any(q, (
            "sc scholarship", "st scholarship", "obc scholarship",
            "post-matric", "post matric", "reserved education",
            "scheduled caste", "scheduled tribe", "dalit", "adivasi",
        )):
            packs.append(SourcePack(
                id="constitution_article_46",
                title_patterns=("Constitution of India",),
                search_query="Constitution of India Article 46 promotion of educational and economic interests Scheduled Castes Scheduled Tribes scholarship",
                doc_ids=("constitution-india",),
                # The IndiaCode Constitution extract stores Articles 45-46 in
                # the Article 44 chunk; retrieval focuses the returned text to
                # Article 46 before exposing it as a required source.
                anchor_patterns=("/sec-44", "/sec-46"),
                priority=1.08,
            ))
            packs.append(_rti_pack())
        if _has_any(q, ("kanya vivah", "kanyadan", "kanya bibaha", "vivah yojana", "daughter wedding", "marriage scheme")):
            if _has_bihar_context(q):
                packs.append(SourcePack(
                    id="bihar_kanya_vivah_service",
                    title_patterns=(
                        "Bihar Mukhyamantri Kanya Vivah Yojana Service Description",
                        "Bihar Mukhyamantri Kanya Vivah Yojana Service Rules",
                    ),
                    search_query="Bihar Mukhyamantri Kanya Vivah Yojana service delivery eligibility marriage certificate income proof grievance status",
                    doc_ids=("bihar-kanya-vivah-service",),
                    priority=1.12,
                ))
            packs.append(_rti_pack())
        if _has_ration_context(q):
            packs.append(SourcePack(
                id="national_food_security_2013",
                title_patterns=("National Food Security Act 2013",),
                search_query="National Food Security Act 2013 ration card targeted public distribution system grievance redressal food security allowance",
                doc_ids=("national-food-security-2013",),
                anchor_patterns=("/sec-3", "/sec-12", "/sec-14", "/sec-15"),
                priority=1.08,
            ))
        if _has_any(q, ("epfo", "epf", "pension arrears", "provident")):
            packs.append(SourcePack(
                id="epf_1952",
                title_patterns=("Employees Provident Funds and Miscellaneous Provisions Act 1952",),
                search_query="Employees Provident Funds Act 1952 pension provident fund arrears grievance",
                doc_ids=("epf-1952",),
                priority=1.04,
            ))
            packs.append(_rti_pack())
        if _has_welfare_pension_scheme_context(q):
            packs.append(SourcePack(
                id="nsap_guidelines_2014",
                title_patterns=(
                    "National Social Assistance Programme Guidelines 2014",
                    "National Social Assistance Programme",
                    "Indira Gandhi National Old Age Pension Scheme",
                    "Indira Gandhi National Widow Pension Scheme",
                ),
                search_query="National Social Assistance Programme Guidelines 2014 IGNOAPS IGNWPS old age pension widow pension eligibility sanction grievance",
                doc_ids=("nsap-guidelines-2014",),
                priority=1.08,
            ))
            packs.append(_rti_pack())
        if _has_army_service_pension_context(q):
            packs.append(SourcePack(
                id="army_pension_regulations_2008_part_i",
                title_patterns=("Pension Regulations for the Army 2008 Part I",),
                search_query="Pension Regulations for the Army 2008 Part I family pension widow ordinary family pension eligibility",
                doc_ids=("pension-regulations-army-2008-part-i",),
                priority=1.12,
            ))
            packs.append(SourcePack(
                id="army_pension_regulations_2008_part_ii",
                title_patterns=("Pension Regulations for the Army 2008 Part II",),
                search_query="Pension Regulations for the Army 2008 Part II claims initial grant family pension documents procedure",
                doc_ids=("pension-regulations-army-2008-part-ii",),
                priority=1.10,
            ))
        if _has_any(q, ("ulip", "insurance", "policy", "agent sold")):
            packs.append(SourcePack(
                id="consumer_protection_2019",
                title_patterns=("Consumer Protection Act 2019",),
                search_query="Consumer Protection Act 2019 insurance policy agent mis-selling service deficiency complaint",
                doc_ids=("consumer-protection-2019",),
                anchor_patterns=("/sec-2-", "/sec-35", "/sec-38"),
                priority=1.04,
            ))
        if _has_any(q, ("aadhaar", "aadhar", "identity", "authentication", "biometric")):
            packs.append(SourcePack(
                id="aadhaar_2016",
                title_patterns=(
                    "Aadhaar (Targeted Delivery of Financial and Other Subsidies, Benefits and Services) Act 2016",
                ),
                search_query="Aadhaar Act 2016 authentication identity subsidy benefit grievance",
                doc_ids=("aadhaar-2016",),
            ))
        if _has_any(q, ("sim", "sims", "mobile connection", "telecom", "parcel has drugs")):
            packs.append(SourcePack(
                id="telecommunications_2023",
                title_patterns=("Telecommunications Act 2023",),
                search_query="Telecommunications Act 2023 identity misuse SIM subscriber fraud",
                doc_ids=("telecommunications-2023",),
                anchor_patterns=("/sec-29", "/sec-42"),
                priority=1.02,
            ))
            packs.append(SourcePack(
                id="it_act_2000",
                title_patterns=("Information Technology Act 2000",),
                search_query="Information Technology Act 2000 section 66C identity theft section 66D cheating by personation",
                doc_ids=("it-2000",),
                anchor_patterns=("/sec-66C", "/sec-66D"),
                priority=0.98,
            ))
        if _has_any(q, (
            "rti", "reason", "status", "reply", "information", "rejected", "pending",
            "removed", "stopped", "deleted", "widow pension", "old age pension",
            "pension not", "pension nahi", "nahi aayi", "not received pension",
            "not paid pension", "pension 6 month", "pension 6 months",
        )):
            packs.append(_rti_pack())

    elif category == "election_voter_rights":
        packs.append(SourcePack(
            id="rpa_1950",
            title_patterns=("Representation of the People Act 1950",),
            search_query="Representation of the People Act 1950 section 19 section 22 section 23 electoral roll correction inclusion voter EPIC",
            doc_ids=("rpa-1950",),
            anchor_patterns=("/sec-19@", "/sec-22@", "/sec-23-", "/sec-24@"),
            priority=1.06,
        ))
        if _has_any(q, ("denied vote", "denied me vote", "polling booth", "booth officer", "not allowed to vote")):
            packs.append(SourcePack(
                id="rpa_1951",
                title_patterns=("Representation of the People Act 1951",),
                search_query="Representation of the People Act 1951 section 62 right to vote voting election",
                doc_ids=("rpa-1951",),
                anchor_patterns=("/sec-62@",),
                priority=0.94,
            ))

    elif category == "election_candidate_dispute":
        election_search = "Representation of the People Act 1951 candidate nomination disqualification election petition corrupt practice"
        election_anchors = (
            "/sec-8", "/sec-33", "/sec-36",
            "/sec-80@", "/sec-80A@", "/sec-81@", "/sec-100@",
            "/sec-123",
        )
        if _has_any(q, ("convicted", "conviction", "disqualified", "disqualification", "two years", "2 years")):
            election_search = "Representation of the People Act 1951 section 8 disqualification on conviction candidate contest election"
            election_anchors = ("/sec-8", "/sec-10A@", "/sec-11A@")
        elif _has_any(q, (
            "false affidavit", "affidavit false", "false assets", "hid assets",
            "hide assets", "hidden assets", "wrong affidavit", "fake affidavit",
            "suppressed criminal case", "concealed criminal case",
            "hid criminal case", "hide criminal case", "hidden criminal case",
        )):
            election_search = "Representation of the People Act 1951 section 33A section 125A false affidavit assets criminal cases election petition section 80 section 81 section 83 section 100"
            election_anchors = ("/sec-33A@", "/sec-125A@", "/sec-80@", "/sec-81@", "/sec-83@", "/sec-100@")
            if _has_any(q, ("corrupt practice", "bribe", "booth capturing", "religion appeal", "hate speech")):
                election_search += " section 123 corrupt practices"
                election_anchors = ("/sec-33A@", "/sec-125A@", "/sec-123", "/sec-80@", "/sec-81@", "/sec-83@", "/sec-100@")
        elif _has_any(q, ("corrupt practice", "bribe", "booth capturing", "religion appeal", "hate speech")):
            election_search = "Representation of the People Act 1951 section 123 corrupt practices election petition section 80 section 81 section 100"
            election_anchors = ("/sec-123", "/sec-80@", "/sec-80A@", "/sec-81@", "/sec-100@")
        elif _has_any(q, ("nomination", "returning officer", "affidavit")):
            election_search = "Representation of the People Act 1951 section 33 nomination section 36 scrutiny rejection returning officer"
            election_anchors = ("/sec-33", "/sec-36")
        elif _has_any(q, ("petition", "election petition", "recount", "counting", "set aside")):
            election_search = "Representation of the People Act 1951 section 80 section 81 section 100 election petition result void"
            election_anchors = ("/sec-80@", "/sec-80A@", "/sec-81@", "/sec-100@")
        packs.append(SourcePack(
            id="rpa_1951",
            title_patterns=("Representation of the People Act 1951",),
            search_query=election_search,
            doc_ids=("rpa-1951",),
            anchor_patterns=election_anchors,
            priority=1.08,
        ))

    elif category == "rti":
        packs.append(_rti_pack())

    elif category == "business_contract_partnership":
        if _has_any(q, (
            "invoice", "client not paying", "not paying invoice", "saas work",
            "buyer deducting payment", "quality issue", "formal rejection",
            "lakh stuck", "msme", "msmed", "udyam", "samadhan", "msefc",
            "samadhaan", "msme registered party", "msme samadhan portal",
            "public sector buyer", "psu not paid",
            "45 days payment", "45 day payment", "delayed payment",
            "payment delay", "amount outstanding", "outstanding", "buyer crossed",
            "fanvue", "creator payment", "creator payout", "platform payout",
            "payment frozen", "release fund", "usd",
        )):
            if _has_any(q, (
                "msme", "msmed", "udyam", "samadhan", "msefc",
                "samadhaan", "msme registered party", "msme samadhan portal",
                "public sector buyer", "psu not paid",
                "buyer deducting payment", "formal rejection", "lakh stuck",
                "45 days payment", "45 day payment", "delayed payment",
                "payment delay", "amount outstanding", "outstanding", "buyer crossed",
            )):
                packs.append(SourcePack(
                    id="msmed_2006",
                    title_patterns=("Micro, Small and Medium Enterprises Development Act 2006",),
                    search_query="MSMED Act 2006 section 15 liability of buyer delayed payment section 16 interest section 18 Facilitation Council",
                    doc_ids=("msmed-2006",),
                    anchor_patterns=("/sec-15", "/sec-16", "/sec-18"),
                    priority=1.1,
                ))
                if _has_any(q, ("43b", "43b(h)", "section 43b", "disallowance")):
                    packs.append(SourcePack(
                        id="income_tax_2025_transition_faq",
                        title_patterns=("Income Tax Act 2025 transition FAQ",),
                        search_query="Income Tax Act 2025 repeal savings transition tax year before 1 April 2026 old Act continues",
                        doc_ids=("income-tax-2025-transition-faq",),
                        source_types=("circular",),
                        priority=1.09,
                    ))
                    packs.append(SourcePack(
                        id="income_tax_43b_h",
                        title_patterns=("Income-tax Act 1961", "Income Tax Act 1961"),
                        search_query="Income-tax Act 1961 section 43B clause h micro small enterprise beyond time limit section 15 MSMED actual payment",
                        doc_ids=("income-tax-1961",),
                        anchor_patterns=("/sec-43B",),
                        priority=1.08,
                    ))
                if _has_any(q, ("commercial court", "commercial suit", "pre litigation mediation", "pre-litigation mediation", "file directly", "rejected at threshold", "section 12a", "12a")):
                    packs.append(SourcePack(
                        id="commercial_courts_2015",
                        title_patterns=("Commercial Courts Act 2015",),
                        search_query="Commercial Courts Act 2015 section 12A pre institution mediation commercial dispute suit threshold",
                        doc_ids=("commercial-courts-2015",),
                        priority=1.08,
                    ))
            packs.append(SourcePack(
                id="indian_contract_1872",
                title_patterns=("Indian Contract Act 1872",),
                search_query="Indian Contract Act 1872 breach of contract compensation unpaid invoice section 73 performance",
                doc_ids=("indian-contract-1872",),
                anchor_patterns=("/sec-37", "/sec-73"),
                priority=1.08,
            ))
            if _is_tangible_goods_delivery_context(q):
                packs.append(SourcePack(
                    id="sale_of_goods_1930",
                    title_patterns=("Sale of Goods Act 1930",),
                    search_query="Sale of Goods Act 1930 delivery of goods breach buyer seller price damages section 55",
                    doc_ids=("sale-of-goods-1930",),
                    anchor_patterns=("/sec-31", "/sec-32", "/sec-55", "/sec-56"),
                    priority=1.04,
                ))
            if _has_any(q, ("dubai", "foreign", "export", "saas", "fanvue", "creator", "platform payout", "usd", "remittance")):
                packs.append(SourcePack(
                    id="fema_1999",
                    title_patterns=("Foreign Exchange Management Act 1999",),
                    search_query="Foreign Exchange Management Act 1999 export services foreign exchange realisation",
                    doc_ids=("fema-1999",),
                    priority=0.9,
                ))
            if _has_any(q, ("fanvue", "creator", "usd", "foreign platform", "remittance")):
                packs.append(SourcePack(
                    id="income_tax_1961",
                    title_patterns=("Income-tax Act 1961", "Income Tax Act 1961"),
                    search_query="Income-tax Act 1961 section 5 scope total income resident foreign platform creator freelance income",
                    doc_ids=("income-tax-1961",),
                    anchor_patterns=("/sec-5",),
                    priority=0.92,
                ))
        if _has_any(q, ("co founder", "co-founder", "equity", "esop", "shareholder", "registers", "board")):
            packs.append(SourcePack(
                id="companies_2013",
                title_patterns=("Companies Act 2013",),
                search_query="Companies Act 2013 section 62 share capital ESOP section 94 registers section 241 242 oppression mismanagement",
                doc_ids=("companies-2013",),
                anchor_patterns=("/sec-62", "/sec-94", "/sec-241", "/sec-242"),
                priority=1.06,
            ))
        if _has_any(q, ("partnership", "partner", "firm")):
            packs.append(SourcePack(
                id="partnership_1932",
                title_patterns=("Indian Partnership Act 1932",),
                search_query="Indian Partnership Act 1932 retirement partner liability notice firm",
                doc_ids=("partnership-1932",),
                priority=1.02,
            ))
        if not any(pack.id == "indian_contract_1872" for pack in packs):
            packs.append(SourcePack(
                id="indian_contract_1872",
                title_patterns=("Indian Contract Act 1872",),
                search_query="Indian Contract Act 1872 agency principal agent bailment compensation breach contract",
                doc_ids=("indian-contract-1872",),
                priority=0.96,
            ))
        if _is_tangible_goods_delivery_context(q) and not any(pack.id == "sale_of_goods_1930" for pack in packs):
            packs.append(SourcePack(
                id="sale_of_goods_1930",
                title_patterns=("Sale of Goods Act 1930",),
                search_query="Sale of Goods Act 1930 delivery of goods breach buyer seller price damages section 55",
                doc_ids=("sale-of-goods-1930",),
                anchor_patterns=("/sec-31", "/sec-32", "/sec-55", "/sec-56"),
                priority=1.04,
            ))
        if _has_any(q, ("injunction", "specific performance", "performance", "restrain", "enforce", "nda", "customer list", "trade secret")):
            packs.append(SourcePack(
                id="specific_relief_1963",
                title_patterns=("Specific Relief Act 1963",),
                search_query="Specific Relief Act 1963 injunction specific performance contract",
                doc_ids=("specific-relief-1963",),
                priority=0.9,
            ))

    elif category == "legal_aid":
        packs.append(SourcePack(
            id="constitution_legal_aid",
            title_patterns=("Constitution of India",),
            search_query="Constitution of India Article 39A equal justice free legal aid Article 22 right to consult lawyer arrest custody",
            doc_ids=("constitution-india",),
            anchor_patterns=("/sec-39A", "/sec-22"),
            priority=1.08,
        ))
        packs.append(SourcePack(
            id="legal_services_authorities_1987",
            title_patterns=("Legal Services Authorities Act 1987",),
            search_query="Legal Services Authorities Act 1987 legal aid District Legal Services Authority Lok Adalat section 12",
            doc_ids=("legal-services-authorities-1987",),
            anchor_patterns=("/sec-12", "/sec-9", "/sec-19", "/sec-20", "/sec-21"),
        ))

    elif category == "lok_adalat_award_challenge":
        packs.append(SourcePack(
            id="legal_services_authorities_1987",
            title_patterns=("Legal Services Authorities Act 1987",),
            search_query="Legal Services Authorities Act 1987 section 21 Lok Adalat award final binding no appeal settlement",
            doc_ids=("legal-services-authorities-1987",),
            anchor_patterns=("/sec-21", "/sec-20", "/sec-19"),
        ))

    elif category == "criminal_procedure_notice":
        if _uses_legacy_criminal_regime(route):
            packs.append(_crpc_pack(q, notice=True))
        elif route.legal_regime == "current_bns_bnss_bsa_for_post_2024_incident":
            packs.append(_bnss_pack(q))
        else:
            packs.append(_bnss_pack(q))
            packs.append(_crpc_pack(q, notice=True))
        if _has_digital_evidence_context(q):
            packs.append(_it_electronic_record_pack(q))

    elif category == "passport_police_verification":
        # No verified Passports Act bare-Act PDF is indexed locally yet. Keep
        # this route procedural, but do not fabricate an authoritative pack.
        return packs

    elif category == "prison_parole_furlough":
        packs.append(SourcePack(
            id="prisons_1894",
            title_patterns=("Prisons Act 1894",),
            search_query="Prisons Act 1894 prison superintendent prisoner interview visit discipline state prison rules",
            doc_ids=("prisons-1894",),
            priority=1.08,
        ))
        if _has_any(q, ("article 21", "writ", "high court", "medical", "health", "mulaqat", "visit")):
            packs.append(_constitution_article_21_pack(q))

    elif category in {"police_fir", "criminal_defence_bail", "custody_compensation", "criminal_general"}:
        if category in {"police_fir", "criminal_general"} and _has_custody_liberty_context(q):
            packs.append(_constitution_article_21_pack(q))
        if category in {"police_fir", "criminal_general"} and _has_arrest_information_context(q):
            packs.append(_constitution_article_22_pack(q))
        if category in {"police_fir", "criminal_general"} and _has_digital_evidence_context(q):
            packs.append(_it_electronic_record_pack(q))
        if category in {"police_fir", "criminal_general", "custody_compensation"} and _has_human_rights_commission_context(q):
            packs.append(SourcePack(
                id="protection_human_rights_1993",
                title_patterns=("Protection of Human Rights Act 1993",),
                search_query="Protection of Human Rights Act 1993 National Human Rights Commission complaint custody lockup torture human rights court",
                doc_ids=("protection-human-rights-1993",),
                anchor_patterns=("/sec-12", "/sec-13", "/sec-17", "/sec-30"),
                priority=1.12,
            ))
        if category in {"custody_compensation", "criminal_defence_bail"} and _has_any(q, (
            "article 21", "speedy trial", "acquitted", "compensation",
            "medical", "doctor", "tb", "long custody", "prolonged",
            "3 yrs", "3 years", "bail rejected", "rejected 6 times",
            "pregnant", "pregnancy", "newborn", "new born",
        )):
            packs.append(_constitution_article_21_pack(q))
        if category == "criminal_defence_bail" and _has_criminal_quashing_context(q):
            if not _uses_legacy_criminal_regime(route):
                packs.append(SourcePack(
                    id="bnss_2023_quashing",
                    title_patterns=("Bharatiya Nagarik Suraksha Sanhita 2023",),
                    search_query="Bharatiya Nagarik Suraksha Sanhita 2023 section 528 inherent powers High Court quashing criminal proceeding FIR",
                    doc_ids=("bnss-2023",),
                    anchor_patterns=("/sec-528",),
                    priority=1.22,
                ))
            if _uses_legacy_criminal_regime(route) or route.legal_regime == "incident_date_needed_for_bns_bnss_bsa_vs_ipc_crpc":
                packs.append(SourcePack(
                    id="crpc_1973_quashing",
                    title_patterns=("Code of Criminal Procedure 1973", "Code of Criminal Procedure, 1973"),
                    search_query="Code of Criminal Procedure 1973 section 482 inherent powers High Court quashing FIR criminal proceeding",
                    doc_ids=("crpc-1973",),
                    anchor_patterns=("/sec-482",),
                    priority=1.22 if _uses_legacy_criminal_regime(route) else 1.18,
                ))
        if category == "criminal_defence_bail" and _has_any(q, ("pregnant", "pregnancy", "sick", "infirm", "medical bail", "interim bail")):
            packs.append(SourcePack(
                id="bnss_2023_medical_bail",
                title_patterns=("Bharatiya Nagarik Suraksha Sanhita 2023",),
                search_query="Bharatiya Nagarik Suraksha Sanhita 2023 section 480 bail woman sick infirm accused",
                doc_ids=("bnss-2023",),
                anchor_patterns=("/sec-480-b", "/sec-480-c"),
                priority=1.18,
            ))
        if category == "custody_compensation" and _has_any(q, ("delay", "18 months", "released", "compensation", "undertrial")):
            packs.append(SourcePack(
                id="bnss_2023",
                title_patterns=("Bharatiya Nagarik Suraksha Sanhita 2023",),
                search_query="Bharatiya Nagarik Suraksha Sanhita 2023 section 479 maximum period undertrial prisoner detention release",
                doc_ids=("bnss-2023",),
                anchor_patterns=("/sec-479",),
                priority=1.08,
            ))
            packs.append(SourcePack(
                id="crpc_1973",
                title_patterns=("Code of Criminal Procedure 1973", "Code of Criminal Procedure, 1973"),
                search_query="Code of Criminal Procedure 1973 section 436A maximum period undertrial prisoner detention release",
                doc_ids=("crpc-1973",),
                anchor_patterns=("/sec-436A", "/sec-436-a"),
                priority=0.94,
            ))
        if category == "criminal_defence_bail" and _has_pmla_ed_context(q):
            packs.append(SourcePack(
                id="pmla_2002",
                title_patterns=("Prevention of Money Laundering Act 2002",),
                search_query="Prevention of Money Laundering Act 2002 bail summons arrest section 45 twin conditions",
                doc_ids=("pmla-2002",),
                anchor_patterns=("/sec-19", "/sec-45"),
                priority=1.1,
            ))
        if category == "criminal_defence_bail" and _has_any(q, ("uapa", "43d", "terrorist", "unlawful activities")):
            uapa_search = "Unlawful Activities Prevention Act 1967 section 43D bail default bail extension chargesheet one hundred eighty days"
            if _has_any(q, ("43d(5)", "43d", "2 yrs", "2 years", "no trial", "trial started")):
                uapa_search = "Unlawful Activities Prevention Act 1967 section 43D(5) bail no trial prolonged incarceration"
            packs.append(SourcePack(
                id="uapa_1967",
                title_patterns=("Unlawful Activities (Prevention) Act 1967",),
                search_query=uapa_search,
                doc_ids=("uapa-1967",),
                priority=1.12,
            ))
        if category == "criminal_defence_bail" and _has_any(q, ("jail", "prison", "arthur road", "tihar", "yerwada", "byculla", "doctor", "tb", "medical", "pregnant", "pregnancy")):
            packs.append(SourcePack(
                id="prisons_1894",
                title_patterns=("Prisons Act 1894",),
                search_query="Prisons Act 1894 jail superintendent prisoner medical officer health treatment prison discipline pregnant prisoner",
                doc_ids=("prisons-1894",),
                priority=0.94,
            ))
        if category == "criminal_defence_bail" and _is_scst_poa_context(q):
            packs.append(SourcePack(
                id="scst_poa_1989",
                title_patterns=(
                    "Scheduled Castes and Scheduled Tribes (Prevention of Atrocities) Act 1989",
                    "Prevention of Atrocities Act 1989",
                ),
                search_query="SC ST Prevention of Atrocities Act 1989 section 18 anticipatory bail accused false case prima facie",
                doc_ids=("sc-st-poa-1989",),
                anchor_patterns=("/sec-18", "/sec-18A"),
                priority=1.08,
            ))
        if category == "criminal_defence_bail" and _has_any(q, ("67 case", "section 67", "it act 67", "filed 67", "normal selfie", "whatsapp group")):
            packs.append(SourcePack(
                id="it_act_2000",
                title_patterns=("Information Technology Act 2000",),
                search_query="Information Technology Act 2000 section 67 obscene electronic content section 66E privacy accused defence",
                doc_ids=("it-2000",),
                anchor_patterns=("/sec-67", "/sec-66E"),
                priority=1.08,
            ))
        if category == "criminal_defence_bail" and _has_any(q, (
            "itpa", "pita", "immoral traffic", "parlour", "spa", "spa raid",
            "spa was raided", "spa raided", "police came to spa", "raided", "massage", "receptionist",
        )):
            packs.append(SourcePack(
                id="itpa_1956",
                title_patterns=("Immoral Traffic (Prevention) Act 1956",),
                search_query="Immoral Traffic Prevention Act 1956 section 7 section 8 accused defence prostitution public place soliciting",
                doc_ids=("itpa-1956",),
                anchor_patterns=("/sec-7", "/sec-8"),
                priority=1.08,
            ))
        if category == "criminal_defence_bail" and _has_any(q, (
            "forest guard", "forest officer", "tendu", "minor forest produce",
            "community forest", "mahua", "bamboo",
        )):
            packs.append(SourcePack(
                id="fra_2006",
                title_patterns=("Scheduled Tribes and Other Traditional Forest Dwellers (Recognition of Forest Rights) Act 2006",),
                search_query="Forest Rights Act 2006 section 3 minor forest produce community forest rights tendu leaves",
                doc_ids=("fra-2006",),
                anchor_patterns=("/sec-3",),
                priority=1.12,
            ))
        if category == "criminal_defence_bail" and _has_any(q, ("prohibition law", "excise act", "liquor case", "alcohol case", "caught me drinking", "drinking village", "sharab", "desi daru")):
            if _has_bihar_excise_jurisdiction_context(q):
                packs.append(SourcePack(
                    id="bihar_prohibition_excise_2016",
                    title_patterns=(
                        "Bihar Prohibition and Excise Act 2016",
                        "BIHAR PROHIBITION AND EXCISE ACT, 2016",
                    ),
                    search_query="Bihar Prohibition and Excise Act 2016 section 13 prohibition section 37 consumption liquor section 76 cognizable non-bailable",
                    doc_ids=("bihar-prohibition-excise-2016",),
                    anchor_patterns=("/sec-13", "/sec-37", "/sec-76"),
                    priority=1.16,
                ))
            packs.append(SourcePack(
                id="constitution_article_47",
                title_patterns=("Constitution of India",),
                search_query="Constitution of India Article 47 prohibition consumption intoxicating drinks public health",
                doc_ids=("constitution-india",),
                # The local Constitution chunk starts at Article 44 and includes
                # Articles 45-47 in the same chunk.
                anchor_patterns=("/sec-44",),
                priority=1.08,
            ))
            packs.append(SourcePack(
                id="bnss_2023",
                title_patterns=("Bharatiya Nagarik Suraksha Sanhita 2023",),
                search_query="Bharatiya Nagarik Suraksha Sanhita 2023 arrest bail notice criminal court accused procedure",
                doc_ids=("bnss-2023",),
                anchor_patterns=("/sec-35", "/sec-47", "/sec-478", "/sec-480", "/sec-528"),
                priority=1.04,
            ))
            packs.append(SourcePack(
                id="crpc_1973",
                title_patterns=("Code of Criminal Procedure 1973", "Code of Criminal Procedure, 1973"),
                search_query="Code of Criminal Procedure 1973 arrest bail accused criminal court procedure",
                doc_ids=("crpc-1973",),
                anchor_patterns=("/sec-41", "/sec-50", "/sec-437", "/sec-439"),
                priority=0.96,
            ))
        juvenile_accused = category == "criminal_defence_bail" and _has_explicit_child_age_context(q) and _has_any(q, ("arrested", "theft", "observation home", "jail", "verify age", "age determination"))
        if juvenile_accused:
            packs.append(SourcePack(
                id="jj_2015",
                title_patterns=("Juvenile Justice (Care and Protection of Children) Act 2015",),
                search_query="age determination school date birth certificate matriculation medical age test",
                doc_ids=("jj-2015",),
                anchor_patterns=("/sec-2-t", "/sec-2-u"),
                priority=1.18,
            ))
            packs.append(SourcePack(
                id="jj_2015_age_claim_court",
                title_patterns=("Juvenile Justice (Care and Protection of Children) Act 2015",),
                search_query="person child court determine age",
                doc_ids=("jj-2015",),
                anchor_patterns=("/sec-2-t",),
                priority=1.22,
            ))
            packs.append(SourcePack(
                id="jj_2015_age_documents",
                title_patterns=("Juvenile Justice (Care and Protection of Children) Act 2015",),
                search_query="Juvenile Justice Act section 94 age determination date of birth certificate school matriculation panchayat ossification test",
                doc_ids=("jj-2015",),
                anchor_patterns=("/sec-2-t",),
                priority=1.24,
            ))
            packs.append(SourcePack(
                id="jj_2015_bail_board",
                title_patterns=("Juvenile Justice (Care and Protection of Children) Act 2015",),
                search_query="Juvenile Justice Act 2015 child in conflict with law Juvenile Justice Board bail observation home place of safety",
                doc_ids=("jj-2015",),
                priority=1.12,
            ))
        child_criminal_context = _has_any(q, ("pocso", "minor", "under 18", "under eighteen")) or _has_explicit_child_age_context(q)
        if category == "criminal_defence_bail" and not juvenile_accused and child_criminal_context:
            packs.append(SourcePack(
                id="pocso_2012",
                title_patterns=("Protection of Children from Sexual Offences Act 2012",),
                search_query="Protection of Children from Sexual Offences Act 2012 child sexual offence special court bail procedure",
                doc_ids=("pocso-2012",),
                anchor_patterns=("/sec-3", "/sec-4", "/sec-29", "/sec-33"),
                priority=1.12,
            ))
            if _has_explicit_child_age_context(q) or _has_any(q, ("i am 17", "i was 17", "juvenile", "minor accused")):
                packs.append(SourcePack(
                    id="jj_2015",
                    title_patterns=("Juvenile Justice (Care and Protection of Children) Act 2015",),
                    search_query="age determination school date birth certificate matriculation medical age test child in conflict",
                    doc_ids=("jj-2015",),
                    anchor_patterns=("/sec-2-t", "/sec-2-u"),
                    priority=1.10,
                ))
                packs.append(SourcePack(
                    id="jj_2015_age_claim_court",
                    title_patterns=("Juvenile Justice (Care and Protection of Children) Act 2015",),
                    search_query="person child court determine age",
                    doc_ids=("jj-2015",),
                    anchor_patterns=("/sec-2-t",),
                    priority=1.14,
                ))
                packs.append(SourcePack(
                    id="jj_2015_bail_board",
                    title_patterns=("Juvenile Justice (Care and Protection of Children) Act 2015",),
                    search_query="Juvenile Justice Act 2015 child in conflict with law Juvenile Justice Board bail",
                    doc_ids=("jj-2015",),
                    priority=1.08,
                ))
        if category in {"police_fir", "criminal_general"} and (_has_any(q, ("pocso", "minor", "under 18", "under eighteen")) or _has_child_age_context(q)):
            packs.append(SourcePack(
                id="pocso_2012",
                title_patterns=("Protection of Children from Sexual Offences Act 2012",),
                search_query="Protection of Children from Sexual Offences Act 2012 child sexual offence reporting police special court",
                doc_ids=("pocso-2012",),
                priority=1.06,
            ))
        if category in {"police_fir", "criminal_general"} and _is_scst_poa_context(q):
            packs.append(SourcePack(
                id="scst_poa_1989",
                title_patterns=(
                    "Scheduled Castes and Scheduled Tribes (Prevention of Atrocities) Act 1989",
                    "Prevention of Atrocities Act 1989",
                ),
                search_query="Scheduled Castes Scheduled Tribes Prevention of Atrocities Act 1989 FIR refusal investigation atrocity Special Court",
                doc_ids=("sc-st-poa-1989",),
                anchor_patterns=("/sec-3", "/sec-4", "/sec-14"),
                priority=1.08,
            ))
            packs.append(SourcePack(
                id="bnss_2023_magistrate_investigation",
                title_patterns=("Bharatiya Nagarik Suraksha Sanhita 2023",),
                search_query="Bharatiya Nagarik Suraksha Sanhita 2023 section 175 Magistrate order investigation police refusal FIR",
                doc_ids=("bnss-2023",),
                anchor_patterns=("/sec-175",),
                priority=1.10,
            ))
        if category in {"police_fir", "criminal_general"} and _has_any(q, ("mother in law", "father in law", "in laws", "in-laws", "husband", "wife", "domestic")) and _has_any(q, ("acid", "dowry", "threat", "threatening", "violence")):
            packs.append(SourcePack(
                id="pwdva_2005",
                title_patterns=("Protection of Women from Domestic Violence Act 2005",),
                search_query="Protection of Women from Domestic Violence Act 2005 protection order domestic violence threats Magistrate section 18",
                doc_ids=("domestic-violence-2005",),
                anchor_patterns=("/sec-3", "/sec-12", "/sec-18"),
                priority=1.06,
            ))
        if category in {"police_fir", "criminal_general"} and _has_any(q, ("khap", "honour", "honor", "eloped", "other religion", "inter religion", "inter-religion")):
            packs.append(SourcePack(
                id="bnss_2023_fir_information",
                title_patterns=("Bharatiya Nagarik Suraksha Sanhita 2023",),
                search_query="Bharatiya Nagarik Suraksha Sanhita 2023 section 173 information to police FIR refusal threat complaint",
                doc_ids=("bnss-2023",),
                anchor_patterns=("/sec-173",),
                priority=1.10,
            ))
        if category in {"police_fir", "criminal_general"} and _has_any(q, ("bangladeshi", "murshidabad", "nationality", "citizen", "migrant", "illegal immigrant")):
            packs.append(_constitution_article_21_pack("Article 21 personal liberty police threat identity nationality"))
        if category in {"police_fir", "criminal_general", "criminal_defence_bail"} and _has_witch_hunting_state_law_context(q):
            packs.append(_witch_hunting_state_pack(q))
        if category == "criminal_general" and _has_any(q, ("daughter in law", "daughter-in-law", "bahu")) and _has_any(q, ("jewellery", "jewelry", "gold", "streedhan", "stridhan")):
            packs.append(SourcePack(
                id="pwdva_2005",
                title_patterns=("Protection of Women from Domestic Violence Act 2005",),
                search_query="Protection of Women from Domestic Violence Act 2005 section 3 economic abuse stridhan jewellery daughter in law domestic relationship",
                doc_ids=("domestic-violence-2005",),
                anchor_patterns=("/sec-3", "/sec-12", "/sec-18", "/sec-20"),
                priority=1.02,
            ))
        if _uses_legacy_criminal_regime(route):
            packs.append(_crpc_pack(q))
        else:
            packs.append(_bnss_pack(q))
            if _has_any(q, ("theft", "rape", "cheating", "420", "assault", "threat", "hurt", "murder", "fraud", "forgery", "blank paper", "thumb impression", "moneylender", "witch", "daayan", "dayan", "tonhi", "daini", "498a", "dowry", "cruelty", "spa", "trafficking", "customers want extra", "didn't sign", "did not sign", "fake signature", "loan against", "stalker", "stalking", "follows", "following", "extortion", "robbery", "dacoity", "took my phone", "promised marriage", "promise marriage", "khap", "love jihad", "bangladeshi", "murshidabad", "nationality", "illegal immigrant", "beat", "beaten", "beating", "torture", "lockup", "slap", "slapped", "hit", "pushed", "jewellery", "jewelry", "safe keeping", "not returning")):
                packs.append(_bns_pack(q))
            elif _has_any(q, ("burnt", "burned", "arson", "fire")):
                packs.append(_bns_pack(q))
            elif _has_any(q, ("acid", "chemical", "eyes burning", "threw something on my face", "slur", "biharee", "bihari", "tweet", "defamation")):
                packs.append(_bns_pack(q))
            if route.legal_regime == "incident_date_needed_for_bns_bnss_bsa_vs_ipc_crpc":
                packs.append(_crpc_pack(q))
        if _has_any(q, ("ndps", "narcotic", "ganja", "charas", "mdma", "heroin", "cannabis", "weed", "hash", "cbd", "thc", "vape", "vape pen", "vape cartridge")):
            ndps_search = "NDPS Act 1985 section 36A section 37 default bail extended custody narcotic drug psychotropic substance"
            ndps_anchors = ("/sec-35-b", "/sec-35-c", "/sec-35-d")
            ndps_priority = 1.03
            if _has_any(q, (
                "cbd", "thc", "vape", "vape pen", "vape cartridge",
                "cannabis", "weed", "hash", "ganja", "charas",
                "personal use", "small quantity", "50 gram", "50 grams",
                "50g", "first time accused", "first-time accused",
            )):
                ndps_search = "NDPS Act 1985 section 2 cannabis hemp ganja charas small quantity bail seizure section 37"
                ndps_anchors = ("/sec-2-a", "/sec-14", "/sec-37")
                if _has_any(q, ("cbd", "thc", "vape", "vape pen", "vape cartridge", "mdma", "psychotropic")):
                    ndps_search = "NDPS Act 1985 psychotropic substance possession small quantity bail seizure section 22 section 37"
                    ndps_anchors = ("/sec-22", "/sec-37", "/sec-2")
                ndps_priority = 1.08
            if _has_any(q, ("no chargesheet", "no charge sheet", "default bail", "180 days", "4 months", "commercial")):
                ndps_search = "NDPS Act 1985 section 36A one hundred eighty days custody chargesheet default bail commercial quantity section 37"
                ndps_anchors = ("/sec-35-b", "/sec-35-c", "/sec-35-d")
                ndps_priority = 1.08
            packs.append(SourcePack(
                id="ndps_1985",
                title_patterns=("Narcotic Drugs and Psychotropic Substances Act 1985",),
                search_query=ndps_search,
                doc_ids=("ndps-1985",),
                anchor_patterns=ndps_anchors,
                priority=ndps_priority,
            ))
        if category == "criminal_general" and _has_any(q, ("spa", "customers want extra", "itpa", "trafficking")):
            packs.append(SourcePack(
                id="itpa_1956",
                title_patterns=("Immoral Traffic (Prevention) Act 1956",),
                search_query="Immoral Traffic Prevention Act 1956 trafficking commercial sexual exploitation brothel rescue",
                doc_ids=("itpa-1956",),
                priority=1.04,
            ))

    elif category == "sexual_offence_survivor":
        if (
            not _uses_legacy_criminal_regime(route)
            and not _has_any(q, ("name change", "change my name", "change my surname", "change surname", "gazette"))
        ):
            packs.append(_bnss_pack(q))
            packs.append(_bns_pack(q))
        if _has_any(q, ("child", "minor", "pocso", "under 18")) or _has_child_age_context(q):
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
            anchor_patterns=("/sec-2", "/sec-3", "/sec-4", "/sec-9"),
            priority=1.10,
        ))

    elif category == "family_marriage_status":
        if _has_any(q, ("name change", "change my name", "change my surname", "change surname", "gazette")):
            packs.append(SourcePack(
                id="deptpub_name_change_adult_formalities",
                title_patterns=("Department of Publication Guidelines for Change of Name",),
                search_query="Department of Publication change of name adult Gazette of India Part IV daily local leading newspaper father husband residential address old name typed proforma witnesses",
                doc_ids=("deptpub-name-change-adult-guidelines",),
                anchor_patterns=("adult-formalities",),
                source_types=("circular",),
                priority=1.22,
            ))
            packs.append(SourcePack(
                id="deptpub_name_change_adult_required_documents",
                title_patterns=("Department of Publication Guidelines for Change of Name",),
                search_query="Department of Publication change of name adult required documents undertaking original newspaper prescribed proforma duplicate witnesses photographs ID proof request letter fee",
                doc_ids=("deptpub-name-change-adult-guidelines",),
                anchor_patterns=("adult-required-documents",),
                source_types=("circular",),
                priority=1.20,
            ))
            packs.append(SourcePack(
                id="deptpub_name_change_adult_egazette_download",
                title_patterns=("Department of Publication Guidelines for Change of Name",),
                search_query="Department of Publication download gazette egazette.gov.in Weekly Gazette Part IV find old new name PDF copy no certification",
                doc_ids=("deptpub-name-change-adult-guidelines",),
                anchor_patterns=("egazette-download-and-submission",),
                source_types=("circular",),
                priority=1.16,
            ))
            packs.append(SourcePack(
                id="name_change_case_law",
                title_patterns=("QUDSIYA", "SADANAND", "TANISHKA MAHESHWARI"),
                search_query="name change surname marriage official gazette public documents identity records",
                doc_ids=("hc/dlhc010002672024", "hc/dlhc013384342018", "hc/dlhc010239002020"),
                source_types=("hc_judgment",),
                priority=1.08,
            ))
        if _has_any(q, ("legal age", "age legal", "marriage age", "got married")):
            packs.append(SourcePack(
                id="child_marriage_2006",
                title_patterns=("Prohibition of Child Marriage Act 2006",),
                search_query="Prohibition of Child Marriage Act 2006 marriage age child marriage validity",
                doc_ids=("child-marriage-2006",),
                anchor_patterns=("/sec-2", "/sec-3"),
                priority=1.04,
            ))
            packs.append(_special_marriage_pack(q))
        if _has_any(q, ("muslim", "shariat")):
            packs.append(SourcePack(
                id="shariat_1937",
                title_patterns=("Muslim Personal Law (Shariat) Application Act 1937",),
                search_query="Muslim Personal Law Shariat Application Act 1937 marriage dissolution maintenance inheritance",
                doc_ids=("shariat-1937",),
            ))
        if _has_any(q, ("triple talaq", "talaq-e-biddat", "instant talaq")):
            packs.append(SourcePack(
                id="muslim_women_2019",
                title_patterns=("Muslim Women (Protection of Rights on Marriage) Act 2019",),
                search_query="Muslim Women Protection of Rights on Marriage Act 2019 marriage protection",
                doc_ids=("muslim-women-2019",),
                priority=0.85,
            ))
        if _has_any(q, ("hindu", "first marriage", "second marriage", "bigamy")) and not _has_any(q, ("muslim", "shariat", "christian", "special marriage", "interfaith", "inter-faith")):
            packs.append(_hindu_marriage_pack(q, bigamy=True))
        if (
            not _uses_legacy_criminal_regime(route)
            and not _has_any(q, ("name change", "change my name", "change my surname", "change surname", "gazette"))
        ):
            packs.append(_bnss_pack(q))
            packs.append(_bns_pack(q))
            if route.legal_regime == "incident_date_needed_for_bns_bnss_bsa_vs_ipc_crpc":
                packs.append(_crpc_pack(q))

    elif category == "child_custody_adoption":
        packs.append(SourcePack(
            id="guardians_wards_1890",
            title_patterns=("Guardians and Wards Act 1890",),
            search_query="Guardians and Wards Act 1890 custody guardian welfare of minor child",
            doc_ids=("guardians-wards-1890",),
            anchor_patterns=("/sec-7", "/sec-17", "/sec-25"),
            priority=1.06,
        ))
        if _has_any(q, ("not letting me meet", "get her back", "get him back", "return", "took our", "took my child", "blocked calls", "fast")):
            packs.append(_constitution_article_21_pack("Article 21 child custody child return habeas corpus personal liberty welfare"))
        non_hindu_family_context = _is_non_hindu_family_context(q)
        if not non_hindu_family_context:
            packs.append(SourcePack(
                id="hindu_minority_guardianship_1956",
                title_patterns=("Hindu Minority and Guardianship Act 1956",),
                search_query="Hindu Minority and Guardianship Act 1956 natural guardian welfare of minor custody",
                doc_ids=("hindu-minority-guardianship-1956",),
                anchor_patterns=("/sec-6", "/sec-13"),
                priority=1.02,
            ))
        packs.append(_family_courts_pack())
        if _has_any(q, ("hindu",)) and not non_hindu_family_context:
            packs.append(_hindu_marriage_pack(q, custody=True))
        if _has_any(q, ("adoption", "adopted", "papers", "cara")):
            if not non_hindu_family_context:
                packs.append(SourcePack(
                    id="hindu_adoptions_maintenance_1956",
                    title_patterns=("Hindu Adoptions and Maintenance Act 1956",),
                    search_query="Hindu Adoptions and Maintenance Act 1956 valid adoption conditions capacity consent proof section 6 section 16",
                    doc_ids=("hindu-adoptions-maintenance-1956",),
                    anchor_patterns=("/sec-6", "/sec-16"),
                    priority=1.08,
                ))
            packs.append(SourcePack(
                id="jj_2015",
                title_patterns=("Juvenile Justice (Care and Protection of Children) Act 2015",),
                search_query="Juvenile Justice Act 2015 section 56 relative adoption irrespective religion section 58 adoption procedure court order",
                doc_ids=("jj-2015",),
                anchor_patterns=("/sec-30-x", "/sec-30-y", "/sec-30-z"),
                priority=1.08,
            ))

    elif category == "surrogacy_parenthood":
        surrogacy_search = "Surrogacy Regulation Act 2021 section 4 eligibility intending couple intending woman certificate appropriate authority"
        surrogacy_anchors = ("surrogacy-2021/sec-2-", "surrogacy-2021/sec-4-", "surrogacy-2021/sec-6@")
        if _has_any(q, ("abandon", "abandoned", "child rights", "abortion", "terminate")):
            surrogacy_search = "Surrogacy Regulation Act 2021 section 7 section 8 section 10 abandon child rights abortion"
            surrogacy_anchors = ("surrogacy-2021/sec-7@", "surrogacy-2021/sec-8@", "surrogacy-2021/sec-10@")
        elif _has_any(q, ("clinic", "registration", "registered")):
            surrogacy_search = "Surrogacy Regulation Act 2021 section 3 section 11 registration surrogacy clinic appropriate authority"
            surrogacy_anchors = ("surrogacy-2021/sec-3@", "surrogacy-2021/sec-11@", "surrogacy-2021/sec-12@")
        packs.append(SourcePack(
            id="surrogacy_2021",
            title_patterns=("Surrogacy (Regulation) Act 2021", "Surrogacy Regulation Act 2021"),
            search_query=surrogacy_search,
            doc_ids=("surrogacy-2021",),
            anchor_patterns=surrogacy_anchors,
            priority=1.08,
        ))
        if _has_any(q, ("abortion", "abort", "terminate pregnancy", "termination", "mtp")):
            packs.append(SourcePack(
                id="mtp_1971",
                title_patterns=("Medical Termination of Pregnancy Act 1971",),
                search_query="Medical Termination of Pregnancy Act 1971 termination pregnancy consent medical practitioner",
                doc_ids=("mtp-1971",),
                priority=0.92,
            ))

    elif category == "succession_inheritance":
        if _has_any(q, ("muslim", "shariat", "islamic")):
            packs.append(SourcePack(
                id="shariat_1937",
                title_patterns=("Muslim Personal Law (Shariat) Application Act 1937",),
                search_query="Muslim Personal Law Shariat Application Act 1937 intestate succession inheritance heirs property",
                doc_ids=("shariat-1937",),
            ))
        elif _has_any(q, ("christian",)):
            packs.append(SourcePack(
                id="indian_succession_1925",
                title_patterns=("Indian Succession Act 1925",),
                search_query="Indian Succession Act 1925 section 32 section 33 section 33A Christian intestate succession widow lineal descendants kindred stepchildren",
                doc_ids=("indian-succession-1925",),
                anchor_patterns=("/sec-32", "/sec-33", "/sec-33A"),
                priority=1.12,
            ))
        elif _has_any(q, ("parsi",)):
            packs.append(SourcePack(
                id="indian_succession_1925",
                title_patterns=("Indian Succession Act 1925",),
                search_query="Indian Succession Act 1925 Parsi intestate succession section 50 section 51 section 54 children daughters sisters",
                doc_ids=("indian-succession-1925",),
                anchor_patterns=("/sec-50", "/sec-51", "/sec-54", "/schedule-ii"),
                priority=1.18,
            ))
        if _has_any(q, ("hindu", "coparcener", "daughter", "ancestral")) and not _has_any(q, ("muslim", "shariat", "islamic")):
            packs.append(SourcePack(
                id="hindu_succession_1956",
                title_patterns=("Hindu Succession Act 1956",),
                search_query="Hindu Succession Act 1956 section 6 daughter coparcener intestate succession",
                doc_ids=("hindu-succession-1956",),
                anchor_patterns=("/sec-6", "/sec-8", "/sec-10"),
            ))
        elif _has_any(q, ("father", "mother", "son", "daughter", "brother", "sister", "property", "flat", "land", "share")) and not _has_any(q, ("muslim", "shariat", "islamic", "parsi", "christian")):
            packs.append(SourcePack(
                id="hindu_succession_1956",
                title_patterns=("Hindu Succession Act 1956",),
                search_query="Hindu Succession Act 1956 intestate succession heirs sons daughters property share",
                doc_ids=("hindu-succession-1956",),
                anchor_patterns=("/sec-8", "/sec-10", "/sec-15"),
                priority=0.98,
            ))
        if _has_any(q, ("will", "registered", "registration", "unregistered", "latest one", "1998")):
            packs.append(SourcePack(
                id="indian_succession_1925",
                title_patterns=("Indian Succession Act 1925",),
                search_query="Indian Succession Act 1925 section 63 execution of unprivileged will attestation probate",
                doc_ids=("indian-succession-1925",),
                anchor_patterns=("/sec-63", "/sec-57", "/sec-213"),
                priority=1.06,
            ))
            packs.append(SourcePack(
                id="registration_1908",
                title_patterns=("Registration Act 1908",),
                search_query="Registration Act 1908 registration optional will compulsory registration effect of non registration",
                doc_ids=("registration-1908",),
                anchor_patterns=("/sec-17", "/sec-18", "/sec-49"),
                priority=1.02,
            ))
        if not packs:
            packs.append(SourcePack(
                id="indian_succession_1925",
                title_patterns=("Indian Succession Act 1925",),
                search_query="Indian Succession Act 1925 intestate succession will property heirs",
                doc_ids=("indian-succession-1925",),
            ))

    elif category == "land_revenue_records":
        if _has_any(q, ("sarpanch", "panchayat", "gram sabha", "common village land", "common land", "panchayat land")):
            packs.append(SourcePack(
                id="constitution_panchayats_part_ix",
                title_patterns=("Constitution of India",),
                search_query="Constitution of India Part IX Panchayat Gram Sabha powers authority responsibilities Article 243G",
                doc_ids=("constitution-india",),
                anchor_patterns=("/sec-243", "/sec-243G"),
                priority=1.08,
            ))
            packs.append(SourcePack(
                id="panchayat_common_land_case_law",
                title_patterns=("GRAM PANCHAYAT", "PANCHAYAT"),
                search_query="Gram Panchayat common village land resolution allotment public land",
                doc_ids=("2000-insc-465", "2006-insc-459", "2006-insc-620", "2022-insc-1016"),
                source_types=("sc_judgment",),
                priority=1.08,
            ))
        if _has_any(q, ("bribe", "asking 5000", "asking money", "patwari asking", "corruption")):
            packs.append(SourcePack(
                id="prevention_corruption_1988",
                title_patterns=("Prevention of Corruption Act 1988",),
                search_query="Prevention of Corruption Act 1988 public servant bribe gratification complaint",
                doc_ids=("prevention-of-corruption-1988",),
                anchor_patterns=("/sec-7", "/sec-8", "/sec-13"),
                priority=1.08,
            ))
        if _has_any(q, ("husband died", "wife died", "widow", "death", "died", "succession", "heir")):
            packs.append(SourcePack(
                id="hindu_succession_1956",
                title_patterns=("Hindu Succession Act 1956",),
                search_query="Hindu Succession Act 1956 widow heir intestate succession property mutation",
                doc_ids=("hindu-succession-1956",),
                anchor_patterns=("/sec-8", "/sec-10", "/sec-14", "/sec-15"),
                priority=1.04,
            ))
        packs.append(_rti_pack())

    elif category == "pmla_ed":
        packs.append(SourcePack(
            id="pmla_2002",
            title_patterns=("Prevention of Money Laundering Act 2002",),
            search_query="Prevention of Money Laundering Act 2002 section 50 summons section 5 provisional attachment section 19 arrest section 45 bail",
            doc_ids=("pmla-2002",),
            anchor_patterns=("/sec-50", "/sec-5", "/sec-8", "/sec-19", "/sec-45"),
        ))
        if not _uses_legacy_criminal_regime(route):
            packs.append(_bnss_pack(q))

    elif category == "street_vendor_municipal":
        packs.append(SourcePack(
            id="street_vendors_2014",
            title_patterns=("Street Vendors (Protection of Livelihood and Regulation of Street Vending) Act 2014",),
            search_query="Street Vendors Act 2014 Town Vending Committee certificate of vending seizure eviction goods",
            doc_ids=("street-vendors-2014",),
            anchor_patterns=("/sec-3", "/sec-18", "/sec-19", "/sec-27"),
        ))
        if _has_any(q, ("bribe", "pay 2000", "pay 5000", "inspector", "corruption")):
            packs.append(SourcePack(
                id="prevention_corruption_1988",
                title_patterns=("Prevention of Corruption Act 1988",),
                search_query="Prevention of Corruption Act 1988 public servant demanding undue advantage bribe complaint",
                doc_ids=("prevention-of-corruption-1988",),
                anchor_patterns=("/sec-7", "/sec-8", "/sec-13"),
                priority=1.04,
            ))

    elif category == "land_acquisition_compensation":
        packs.append(SourcePack(
            id="rfctlarr_2013",
            title_patterns=("Right to Fair Compensation and Transparency in Land Acquisition, Rehabilitation and Resettlement Act 2013",),
            search_query="Right to Fair Compensation and Transparency in Land Acquisition Rehabilitation Resettlement Act 2013 compensation award payment deposit reference Authority highway road widening",
            doc_ids=("rfctlarr-2013",),
            anchor_patterns=("/sec-31", "/sec-38", "/sec-64", "/sec-77"),
            priority=1.18,
        ))

    elif category == "environment_compensation":
        if _has_any(q, ("pil", "high court", "article 226", "writ")):
            packs.append(SourcePack(
                id="constitution_article_226",
                title_patterns=("Constitution of India",),
                search_query="Constitution of India Article 226 writ PIL High Court environmental pollution",
                doc_ids=("constitution-india",),
                anchor_patterns=("/sec-226",),
                priority=1.08,
            ))
        if _has_land_acquisition_context(q):
            packs.append(SourcePack(
                id="rfctlarr_2013_scheduled_area_rr",
                title_patterns=("Right to Fair Compensation and Transparency in Land Acquisition, Rehabilitation and Resettlement Act 2013",),
                search_query="RFCTLARR Act 2013 section 41 special provisions Scheduled Castes Scheduled Tribes Scheduled Areas rehabilitation resettlement displacement",
                doc_ids=("rfctlarr-2013",),
                anchor_patterns=("/sec-41",),
                priority=1.14,
            ))
            packs.append(SourcePack(
                id="rfctlarr_2013",
                title_patterns=("Right to Fair Compensation and Transparency in Land Acquisition, Rehabilitation and Resettlement Act 2013",),
                search_query="Right to Fair Compensation and Transparency in Land Acquisition Rehabilitation Resettlement Act 2013 compensation award payment deposit reference Authority highway land acquired",
                doc_ids=("rfctlarr-2013",),
                anchor_patterns=("/sec-31", "/sec-38", "/sec-64", "/sec-77"),
                priority=1.08,
            ))
        if _has_any(q, ("gram sabha", "palli sabha", "pesa", "scheduled area", "coal block", "bauxite", "mining project")):
            packs.append(SourcePack(
                id="pesa_1996",
                title_patterns=("Panchayats (Extension to the Scheduled Areas) Act 1996",),
                search_query="PESA Act 1996 Scheduled Areas Gram Sabha consultation land acquisition minor minerals",
                doc_ids=("pesa-1996",),
                anchor_patterns=("/sec-4",),
                priority=1.06,
            ))
        if _has_any(q, ("bauxite", "coal block", "mining", "minor mineral", "mine", "mines", "minerals")):
            packs.append(SourcePack(
                id="mmdr_1957",
                title_patterns=("Mines and Minerals (Development and Regulation) Act 1957",),
                search_query="Mines and Minerals Development and Regulation Act 1957 mining lease mineral concession state government approval",
                doc_ids=("mmdr-1957",),
                priority=1.04,
            ))
        if _has_any(q, ("forest", "forest clearance", "fca", "bauxite", "coal block", "mining project")):
            packs.append(SourcePack(
                id="forest_conservation_1980",
                title_patterns=("Forest (Conservation) Act 1980",),
                search_query="Forest Conservation Act 1980 section 2 forest land non forest purpose prior approval mining project",
                doc_ids=("forest-conservation-1980",),
                priority=1.02,
            ))
        if _has_any(q, ("ngt", "national green tribunal", "wetland", "illegal construction", "encroachment")):
            packs.append(SourcePack(
                id="ngt_2010",
                title_patterns=("National Green Tribunal Act 2010",),
                search_query="National Green Tribunal Act 2010 section 14 section 15 application environmental dispute compensation restitution wetland illegal construction",
                doc_ids=("ngt-2010",),
                anchor_patterns=("/sec-14", "/sec-15", "/sec-18"),
                priority=1.12,
            ))
        if _has_any(q, ("water", "borewell", "effluent", "chemicals", "pollution", "factory")):
            packs.append(SourcePack(
                id="environment_protection_1986",
                title_patterns=("Environment (Protection) Act 1986", "Environment Protection Act 1986"),
                search_query="Environment Protection Act 1986 environmental pollution hazardous substances directions penalties",
                doc_ids=("environment-protection-1986",),
                anchor_patterns=("/sec-3", "/sec-5", "/sec-7", "/sec-8", "/sec-15", "/sec-19"),
                priority=1.1,
            ))
            packs.append(SourcePack(
                id="water_pollution_1974",
                title_patterns=("Water (Prevention and Control of Pollution) Act 1974",),
                search_query="Water Prevention and Control of Pollution Act 1974 state pollution control board consent effluent sample complaint",
                doc_ids=("water-pollution-1974",),
                anchor_patterns=("/sec-17", "/sec-21", "/sec-24", "/sec-25", "/sec-33A"),
                priority=1.08,
            ))
            if not any(pack.id == "ngt_2010" for pack in packs):
                packs.append(SourcePack(
                    id="ngt_2010",
                    title_patterns=("National Green Tribunal Act 2010",),
                    search_query="National Green Tribunal Act 2010 section 14 section 15 compensation restitution environmental pollution application",
                    doc_ids=("ngt-2010",),
                    priority=1.0,
                ))
        if not packs:
            packs.append(_rti_pack())

    elif category == "court_procedure":
        if _has_any(q, ("court fee", "court fees", "valuation", "suit valuation", "civil suit valuation")):
            packs.append(SourcePack(
                id="court_fees_1870",
                title_patterns=("Court Fees Act 1870",),
                search_query="Court Fees Act 1870 section 7 computation of fees civil suit money recovery valuation plaint",
                doc_ids=("court-fees-1870",),
                anchor_patterns=("/sec-7", "/sec-8", "/sec-9"),
                priority=1.12,
            ))
        if _has_any(q, (
            "cognizance", "private complaint", "156(3)", "156 3",
            "section 156", "section 200", "magistrate complaint",
            "refused to take complaint", "refused to take cognizance",
        )):
            packs.append(SourcePack(
                id="crpc_1973",
                title_patterns=("Code of Criminal Procedure 1973", "Code of Criminal Procedure, 1973"),
                search_query="Code of Criminal Procedure 1973 section 156(3) section 190 section 200 section 203 section 204 magistrate complaint cognizance revision",
                doc_ids=("crpc-1973",),
                anchor_patterns=("/sec-203", "/sec-397", "/sec-200", "/sec-190", "/sec-156", "/sec-204"),
                priority=1.12,
            ))
            packs.append(SourcePack(
                id="bnss_2023",
                title_patterns=("Bharatiya Nagarik Suraksha Sanhita 2023",),
                search_query="Bharatiya Nagarik Suraksha Sanhita 2023 section 223 examination of complainant section 175 Magistrate order investigation police inaction section 226 dismissal of complaint",
                doc_ids=("bnss-2023",),
                anchor_patterns=("/sec-226", "/sec-442", "/sec-223", "/sec-210", "/sec-175"),
                priority=1.06,
            ))
            return packs
        if _has_any(q, ("commercial suit", "commercial court", "pre litigation mediation", "pre-litigation mediation", "pre institution mediation", "pre-institution mediation", "section 12a", "12a")):
            packs.append(SourcePack(
                id="commercial_courts_2015",
                title_patterns=("Commercial Courts Act 2015",),
                search_query="Commercial Courts Act 2015 section 12A pre institution mediation commercial court suit rejection threshold",
                doc_ids=("commercial-courts-2015",),
                priority=1.1,
            ))
            packs.append(SourcePack(
                id="mediation_2023",
                title_patterns=("Mediation Act 2023",),
                search_query="Mediation Act 2023 pre litigation mediation court referred mediation settlement agreement",
                doc_ids=("mediation-2023",),
                priority=1.04,
            ))
        packs.append(_cpc_pack(q))
        if _has_any(q, ("limitation", "delay", "condonation", "time barred", "time-barred", "time limit", "how much time", "appeal time", "appeal against")):
            packs.append(SourcePack(
                id="limitation_1963",
                title_patterns=("Limitation Act 1963",),
                search_query="Limitation Act 1963 condonation of delay appeal limitation section 5",
                doc_ids=("limitation-1963",),
                anchor_patterns=("/sec-5",),
                priority=0.92,
            ))

    return packs


def _cpc_pack(query: str) -> SourcePack:
    search_query = "Code of Civil Procedure 1908 civil court procedure filing appeal decree"
    anchor_patterns: tuple[str, ...] = ()
    priority = 1.0
    if _has_any(query, (
        "order 21", "order xxi", "execution", "decree holder",
        "execute decree", "judgment debtor", "judgement debtor",
        "money decree", "attach property", "attachment of property",
    )):
        search_query = "Code of Civil Procedure 1908 execution of decrees Order XXI judgment debtor money decree attachment property"
        anchor_patterns = ("/sec-51", "/sec-47")
        priority = 1.12
    elif _has_any(query, ("second appeal", "substantial question", "section 100", "cpc 100")):
        search_query = "Code of Civil Procedure 1908 section 100 second appeal substantial question of law"
        anchor_patterns = ("/sec-100",)
        priority = 1.06
    elif _has_any(query, ("first appeal", "district court dismissed", "dismissed my civil suit", "section 96")):
        search_query = "Code of Civil Procedure 1908 section 96 first appeal Order XLI decree civil suit"
        anchor_patterns = ("/sec-96",)
        priority = 1.05
    elif _has_any(query, ("transfer of case", "case transfer", "section 24", "cpc 24")):
        search_query = "Code of Civil Procedure 1908 section 24 transfer of suit appeal proceeding district court high court"
        anchor_patterns = ("/sec-24",)
        priority = 1.04
    elif _has_any(query, ("order 7", "order vii", "reject plaint")):
        search_query = "Code of Civil Procedure 1908 Order VII Rule 11 rejection of plaint"
        priority = 1.03
    return SourcePack(
        id="cpc_1908",
        title_patterns=("Code of Civil Procedure 1908",),
        search_query=search_query,
        doc_ids=("cpc-1908",),
        anchor_patterns=anchor_patterns,
        priority=priority,
    )


def _hindu_marriage_pack(query: str, *, custody: bool = False, bigamy: bool = False) -> SourcePack:
    search_query = "Hindu Marriage Act 1955 divorce mutual consent custody maintenance family court"
    anchor_patterns = ("/sec-13B", "/sec-19", "/sec-24", "/sec-25", "/sec-26")
    priority = 1.0
    if custody:
        search_query = "Hindu Marriage Act 1955 section 26 custody children minor welfare"
        anchor_patterns = ("/sec-26",)
        priority = 0.94
    elif bigamy:
        search_query = "Hindu Marriage Act 1955 section 5 section 17 bigamy second marriage void"
        anchor_patterns = ("/sec-5", "/sec-17")
        priority = 0.96
    elif _has_any(query, ("mutual consent", "13b", "both agree")):
        search_query = "Hindu Marriage Act 1955 section 13B mutual consent divorce petition"
        anchor_patterns = ("/sec-13B", "/sec-13-b")
        priority = 1.06
    return SourcePack(
        id="hindu_marriage_1955",
        title_patterns=("Hindu Marriage Act 1955",),
        search_query=search_query,
        doc_ids=("hindu-marriage-1955",),
        anchor_patterns=anchor_patterns,
        priority=priority,
    )


def _special_marriage_pack(query: str) -> SourcePack:
    search_query = "Special Marriage Act 1954 marriage notice solemnization divorce mutual consent"
    anchor_patterns = ("/sec-5", "/sec-11", "/sec-13", "/sec-28")
    if _has_any(query, ("divorce", "mutual consent", "both agree")):
        search_query = "Special Marriage Act 1954 section 28 divorce by mutual consent"
        anchor_patterns = ("/sec-28",)
    return SourcePack(
        id="special_marriage_1954",
        title_patterns=("Special Marriage Act 1954",),
        search_query=search_query,
        doc_ids=("special-marriage-1954",),
        anchor_patterns=anchor_patterns,
        priority=0.94,
    )


def _is_special_marriage_context(text: str) -> bool:
    return _has_any(text, (
        "special marriage", "special marriage act", "court marriage",
        "interfaith", "inter-faith", "registered under special marriage",
    ))


def _is_muslim_family_context(text: str) -> bool:
    return _has_any(text, ("muslim", "shariat", "islam", "islamic", "nikah", "talaq"))


def _is_christian_family_context(text: str) -> bool:
    return _has_any(text, ("christian", "catholic", "protestant", "church marriage", "indian divorce act"))


def _is_non_hindu_family_context(text: str) -> bool:
    if re.search(r"\b(?:not|non)\s+(?:a\s+)?hindu\b", text):
        return True
    return _is_muslim_family_context(text) or _is_christian_family_context(text) or _has_any(text, (
        "non hindu", "non-hindu", "not hindu", "parsi", "jewish",
        "interfaith", "inter-faith", "special marriage", "nikah", "church",
        "canonical", "personal law",
    ))


def _family_courts_pack() -> SourcePack:
    return SourcePack(
        id="family_courts_1984",
        title_patterns=("Family Courts Act 1984",),
        search_query="Family Courts Act 1984 jurisdiction suits proceedings family marriage custody maintenance",
        doc_ids=("family-courts-1984",),
        anchor_patterns=("/sec-7", "/sec-8"),
        priority=0.9,
    )


def _bnss_pack(query: str) -> SourcePack:
    if _has_criminal_quashing_context(query):
        search_query = "Bharatiya Nagarik Suraksha Sanhita 2023 section 528 saving inherent powers High Court quashing criminal proceeding FIR"
        anchor_patterns = ("/sec-528",)
    elif _has_production_notice_context(query):
        search_query = "Bharatiya Nagarik Suraksha Sanhita 2023 section 94 summons to produce document electronic record thing"
        anchor_patterns = ("/sec-94",)
    elif _has_digital_device_seizure_context(query):
        search_query = (
            "Bharatiya Nagarik Suraksha Sanhita 2023 section 105 recording search seizure "
            "section 106 police seize property section 185 search by police section 497 "
            "custody disposal property pending trial section 503 police seizure property"
        )
        anchor_patterns = ("/sec-105", "/sec-106", "/sec-185", "/sec-497", "/sec-503")
    elif _has_any(query, ("custodial death", "lockup death", "death lockup", "lockup suicide", "custody death", "custody suicide", "section 196", " 196 procedure")):
        search_query = "Bharatiya Nagarik Suraksha Sanhita 2023 section 196 inquiry by magistrate custodial death suicide police custody"
        anchor_patterns = ("/sec-196",)
    elif _has_any(query, ("police torture", "torture case", "custodial torture")):
        search_query = "Bharatiya Nagarik Suraksha Sanhita 2023 FIR information police complaint magistrate investigation sections 173 175"
        anchor_patterns = ("/sec-173", "/sec-175")
    elif _has_any(query, ("handcuff", "handcuffs", "hand cuff", "hand cuffs", "chained", "shackled")):
        search_query = "Bharatiya Nagarik Suraksha Sanhita 2023 section 43 arrest handcuff restraint section 47 arrest information section 58 produced before magistrate"
        anchor_patterns = ("/sec-43", "/sec-47", "/sec-58")
    elif _has_custody_procedure_context(query):
        search_query = "Bharatiya Nagarik Suraksha Sanhita 2023 arrest information custody produced before magistrate sections 47 48 57 58"
        anchor_patterns = ("/sec-47", "/sec-48", "/sec-57", "/sec-58")
    elif _has_any(query, ("child support", "child maintenance", "maintenance order", "maintenance for child", "not paying maintenance")):
        search_query = "Bharatiya Nagarik Suraksha Sanhita 2023 section 144 maintenance wife child parents enforcement"
        anchor_patterns = ("/sec-144",)
    elif _has_any(query, ("fir copy", "copy of fir", "no fir copy", "fir ki copy", "fir ka copy")):
        search_query = "Bharatiya Nagarik Suraksha Sanhita 2023 section 173 FIR copy information police station"
        anchor_patterns = ("/sec-173",)
    elif _has_any(query, ("magistrate", "24 hours", "twenty four hours", "not produced", "5 din", "5 days", "detained")):
        search_query = "Bharatiya Nagarik Suraksha Sanhita 2023 arrest produced before magistrate twenty four hours sections 57 58"
        anchor_patterns = ("/sec-57", "/sec-58", "/sec-47", "/sec-48")
    elif _has_any(query, ("default bail", "no chargesheet", "no charge sheet", "60 days", "90 days", "custody")):
        search_query = "Bharatiya Nagarik Suraksha Sanhita 2023 default bail detention chargesheet custody section 187"
        anchor_patterns = ("/sec-187",)
    elif _has_any(query, ("bail", "surety", "bond", "first time accused", "first-time accused")):
        search_query = "Bharatiya Nagarik Suraksha Sanhita 2023 regular bail bond surety sections 480 483"
        anchor_patterns = ("/sec-480", "/sec-483")
    elif _has_any(query, ("chargesheet", "charge sheet")):
        search_query = "Bharatiya Nagarik Suraksha Sanhita 2023 section 193 police report completion of investigation charge sheet"
        anchor_patterns = ("/sec-193",)
    elif _mentions_fir_context(query):
        search_query = "Bharatiya Nagarik Suraksha Sanhita 2023 FIR information police refusal magistrate investigation"
        anchor_patterns = ("/sec-173", "/sec-174", "/sec-175")
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


def _crpc_pack(query: str, *, notice: bool = False) -> SourcePack:
    if _has_criminal_quashing_context(query):
        search_query = "Code of Criminal Procedure 1973 section 482 saving inherent powers High Court quashing criminal proceeding FIR"
        anchor_patterns = ("/sec-482",)
    elif notice or _has_production_notice_context(query):
        search_query = "Code of Criminal Procedure 1973 section 91 summons to produce document or other thing"
        anchor_patterns = ("/sec-91",)
    elif _has_digital_device_seizure_context(query):
        search_query = (
            "Code of Criminal Procedure 1973 section 100 search section 102 police seize property "
            "section 165 search by police section 451 custody disposal property pending trial "
            "section 457 police seizure property"
        )
        anchor_patterns = ("/sec-100", "/sec-102", "/sec-165", "/sec-451", "/sec-457")
    elif _has_any(query, ("custodial death", "lockup death", "death lockup", "lockup suicide", "custody death", "custody suicide", "section 196", " 196 procedure")):
        search_query = "Code of Criminal Procedure 1973 section 176 inquiry by magistrate death in custody police custody suicide"
        anchor_patterns = ("/sec-176",)
    elif _has_any(query, ("handcuff", "handcuffs", "hand cuff", "hand cuffs", "chained", "shackled")):
        search_query = "Code of Criminal Procedure 1973 section 49 arrest no more restraint than necessary section 56 section 57 production before magistrate"
        anchor_patterns = ("/sec-49", "/sec-56", "/sec-57")
    elif _has_custody_procedure_context(query):
        search_query = "Code of Criminal Procedure 1973 arrest information custody produced before magistrate sections 50 56 57"
        anchor_patterns = ("/sec-50", "/sec-56", "/sec-57")
    elif _has_any(query, ("child support", "child maintenance", "maintenance order", "maintenance for child", "not paying maintenance")):
        search_query = "Code of Criminal Procedure 1973 section 125 maintenance wife child parents enforcement"
        anchor_patterns = ("/sec-125",)
    elif _has_any(query, ("fir copy", "copy of fir", "no fir copy", "fir ki copy", "fir ka copy")):
        search_query = "Code of Criminal Procedure 1973 section 154 FIR copy information police station"
        anchor_patterns = ("/sec-154",)
    elif _has_any(query, ("magistrate", "24 hours", "twenty four hours", "not produced", "5 din", "5 days", "detained")):
        search_query = "Code of Criminal Procedure 1973 arrest produced before magistrate twenty four hours sections 56 57"
        anchor_patterns = ("/sec-56", "/sec-57")
    elif _has_any(query, ("default bail", "no chargesheet", "charge sheet", "60 days", "90 days", "custody", "remand")):
        search_query = "Code of Criminal Procedure 1973 section 167 default bail detention chargesheet custody remand"
        # This older IndiaCode PDF extracts s.167 text under a split s.161
        # anchor sequence. Keep the real section in the query and include the
        # observed anchors so the exact text is still promoted.
        anchor_patterns = ("/sec-161-j", "/sec-161-k", "/sec-161-l", "/sec-161-m", "/sec-167")
    elif _mentions_fir_context(query):
        search_query = "Code of Criminal Procedure 1973 section 154 FIR police refusal magistrate investigation"
        anchor_patterns = ("/sec-154", "/sec-156")
    elif _has_any(query, ("anticipatory", "before arrest")):
        search_query = "Code of Criminal Procedure 1973 section 438 anticipatory bail"
        anchor_patterns = ("/sec-438",)
    else:
        search_query = "Code of Criminal Procedure 1973 bail arrest remand criminal procedure"
        anchor_patterns = ("/sec-437", "/sec-439", "/sec-167")
    return SourcePack(
        id="crpc_1973",
        title_patterns=("Code of Criminal Procedure 1973", "Code of Criminal Procedure, 1973"),
        search_query=search_query,
        doc_ids=("crpc-1973",),
        anchor_patterns=anchor_patterns,
    )


def _bns_pack(query: str) -> SourcePack:
    private_image_context = _has_any(query, ("nude", "private photo", "private photos", "private picture", "private pictures", "intimate", "sex video", "porn", "morphed", "deepfake", "leaked", "voyeur"))
    threat_image_context = private_image_context and _has_any(query, ("blackmail", "threat", "threatening", "extortion", "coerce", "coercion"))
    if _has_any(query, ("acid", "chemical attack", "threw something on my face", "eyes burning")):
        if _has_any(query, ("threat", "threatening", "threaten", "throw acid", "throw chemical")):
            search_query = "Bharatiya Nyaya Sanhita 2023 section 351 criminal intimidation threat section 124 acid attack"
            anchor_patterns = ("/sec-351", "/sec-124", "/sec-117")
        else:
            search_query = "Bharatiya Nyaya Sanhita 2023 section 124 acid attack voluntarily causing hurt grievous hurt"
            anchor_patterns = ("/sec-124", "/sec-115", "/sec-117")
    elif _has_any(query, ("tweet", "defamation", "cm corrupt")):
        search_query = "Bharatiya Nyaya Sanhita 2023 section 356 defamation electronic publication"
        anchor_patterns = ("/sec-356",)
    elif _has_any(query, ("biharee", "bihari", "slur", "insult", "called we are")):
        search_query = "Bharatiya Nyaya Sanhita 2023 words insult provocation defamation public mischief criminal intimidation"
        anchor_patterns = ("/sec-356", "/sec-351", "/sec-352")
    elif _has_any(query, ("bangladeshi", "murshidabad", "nationality", "illegal immigrant", "citizen")):
        search_query = "Bharatiya Nyaya Sanhita 2023 section 351 criminal intimidation threat false accusation police"
        anchor_patterns = ("/sec-351", "/sec-217")
    elif _has_any(query, ("theft", "stolen", "steal")):
        search_query = "Bharatiya Nyaya Sanhita 2023 theft stolen property punishment"
        anchor_patterns = ("/sec-303", "/sec-317")
    elif _has_any(query, ("stalker", "stalking", "stalked", "follows", "following", "followed")):
        search_query = "Bharatiya Nyaya Sanhita 2023 section 78 stalking section 351 criminal intimidation"
        anchor_patterns = ("/sec-78", "/sec-351")
    elif _has_any(query, ("extortion", "robbery", "dacoity", "took my phone", "gang")):
        if "dacoity" in query:
            search_query = "Bharatiya Nyaya Sanhita 2023 section 310 dacoity five or more persons robbery gang section 309 robbery"
            anchor_patterns = ("/sec-310", "/sec-309", "/sec-308")
        else:
            search_query = "Bharatiya Nyaya Sanhita 2023 section 308 extortion section 309 robbery section 310 dacoity gang"
            anchor_patterns = ("/sec-308", "/sec-309", "/sec-310")
    elif _has_any(query, ("dowry death", "body had marks", "suicide", "died at in laws", "died at in-laws")):
        search_query = "Bharatiya Nyaya Sanhita 2023 section 80 dowry death section 85 cruelty section 86 cruelty defined"
        anchor_patterns = ("/sec-80", "/sec-85", "/sec-86")
    elif _has_any(query, ("promised marriage", "promise marriage", "deceitful", "relationship for 2 years", "live in")):
        search_query = "Bharatiya Nyaya Sanhita 2023 section 69 sexual intercourse by deceitful means promise to marry section 63 rape"
        anchor_patterns = ("/sec-69", "/sec-63", "/sec-64")
    elif _has_any(query, ("khap", "honour", "honor", "eloped", "other religion", "inter religion", "inter-religion", "love jihad")):
        search_query = "Bharatiya Nyaya Sanhita 2023 section 351 criminal intimidation threat honour violence wrongful confinement"
        anchor_patterns = ("/sec-351", "/sec-127", "/sec-126")
    elif _has_any(query, ("beat", "beaten", "beating", "torture", "assault", "hurt", "injury", "slap", "slaps", "slapped", "hit", "hit me", "hitting me", "pushed")):
        search_query = "Bharatiya Nyaya Sanhita 2023 hurt assault grievous hurt extortion public servant custody"
        anchor_patterns = ("/sec-115", "/sec-117", "/sec-308")
    elif _has_any(query, ("grabbed", "touching", "touched", "sexual harassment", "uncomfortable", "asks for date", "asking for date")):
        search_query = "Bharatiya Nyaya Sanhita 2023 section 74 assault criminal force woman modesty section 75 sexual harassment section 79 insult modesty"
        anchor_patterns = ("/sec-74", "/sec-75", "/sec-79")
    elif _has_any(query, ("rape", "sexual")):
        search_query = "Bharatiya Nyaya Sanhita 2023 rape sexual offence punishment"
        anchor_patterns = ("/sec-63", "/sec-64")
    elif _has_any(query, ("pan leaked", "aadhaar leaked", "aadhar leaked", "personal data", "data breach", "identity misuse", "fake loan")) and _has_any(query, ("fraud", "misuse", "fake loan", "cheating", "identity theft")):
        search_query = "Bharatiya Nyaya Sanhita 2023 cheating forgery identity misuse false document"
        anchor_patterns = ("/sec-318", "/sec-319", "/sec-336", "/sec-338", "/sec-340")
    elif threat_image_context:
        search_query = "Bharatiya Nyaya Sanhita 2023 section 351 criminal intimidation section 77 voyeurism intimate image defamation"
        anchor_patterns = ("/sec-351", "/sec-77", "/sec-78", "/sec-356")
    elif private_image_context:
        search_query = "Bharatiya Nyaya Sanhita 2023 section 77 voyeurism intimate image section 356 defamation electronic publication"
        anchor_patterns = ("/sec-77", "/sec-356", "/sec-78")
    elif _has_any(query, ("didn't sign", "did not sign", "fake signature", "forged", "forgery", "loan against", "blank paper", "thumb impression")):
        search_query = "Bharatiya Nyaya Sanhita 2023 cheating forgery false document using forged document property fraud"
        anchor_patterns = ("/sec-318", "/sec-319", "/sec-336", "/sec-338", "/sec-340")
    elif _has_any(query, ("jewellery", "jewelry", "ornaments", "safe keeping", "safekeeping", "not returning")):
        search_query = "Bharatiya Nyaya Sanhita 2023 section 316 criminal breach of trust entrusted property jewellery"
        anchor_patterns = ("/sec-316", "/sec-318")
    elif _has_any(query, ("cheating", "420", "fake call", "phishing", "debited", "transferred", "lost money", "took 2 lakh")):
        search_query = "Bharatiya Nyaya Sanhita 2023 cheating fraud dishonestly inducement"
        anchor_patterns = ("/sec-318", "/sec-319")
    elif _has_any(query, ("second wife", "second marriage", "bigamy", "without divorcing")):
        search_query = "Bharatiya Nyaya Sanhita 2023 section 82 marrying again during lifetime of husband or wife bigamy"
        anchor_patterns = ("/sec-82",)
    elif _has_any(query, ("498a", "dowry", "cruelty")):
        search_query = "Bharatiya Nyaya Sanhita 2023 section 85 section 86 cruelty by husband or relatives"
        anchor_patterns = ("/sec-85", "/sec-86")
    elif _has_any(query, ("spa", "trafficking", "customers want extra", "commercial sexual exploitation")):
        search_query = "Bharatiya Nyaya Sanhita 2023 trafficking person exploitation compulsory labour"
        anchor_patterns = ("/sec-143", "/sec-144", "/sec-146")
    elif _has_any(query, ("stripped", "disrobed", "paraded", "public humiliation", "daayan", "dayan", "witch", "tonhi", "daini")):
        search_query = "Bharatiya Nyaya Sanhita 2023 hurt assault wrongful restraint criminal intimidation defamation public humiliation"
        anchor_patterns = ("/sec-115", "/sec-117", "/sec-126", "/sec-127", "/sec-351", "/sec-356")
    elif _has_any(query, ("hostage", "confined", "confinement", "cannot leave", "beaten", "hurt", "assault", "threat", "beat", "head injury", "mukadam")):
        search_query = "Bharatiya Nyaya Sanhita 2023 wrongful confinement hurt assault criminal intimidation"
        anchor_patterns = ("/sec-115", "/sec-117", "/sec-126", "/sec-127", "/sec-351")
    elif _has_any(query, ("burnt", "burned", "arson", "fire")):
        search_query = "Bharatiya Nyaya Sanhita 2023 mischief by fire explosive substance property damage"
        anchor_patterns = ("/sec-326", "/sec-287")
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
        anchor_patterns=("/sec-6", "/sec-7", "/sec-19"),
    )


def _it_electronic_record_pack(query: str) -> SourcePack:
    search_query = "Information Technology Act 2000 electronic record computer resource intermediary digital evidence police investigation"
    anchor_patterns = ("/sec-2",)
    if _has_any(query, ("insta", "instagram", "social media", "deleted post", "deleted posts", "whatsapp")):
        search_query = "Information Technology Act 2000 electronic record social media computer resource section 66E section 67 investigation"
        anchor_patterns = ("/sec-2", "/sec-66E", "/sec-67")
    return SourcePack(
        id="it_act_2000",
        title_patterns=("Information Technology Act 2000",),
        search_query=search_query,
        doc_ids=("it-2000",),
        anchor_patterns=anchor_patterns,
        priority=1.06,
    )


def _witch_hunting_state_pack(query: str) -> SourcePack:
    if _has_any(query, ("assam", "barpeta", "guwahati", "dibrugarh", "jorhat")):
        return SourcePack(
            id="assam_witch_hunting_2015",
            title_patterns=("Assam Witch Hunting (Prohibition, Prevention and Protection) Act 2015",),
            search_query="Assam Witch Hunting Prohibition Prevention Protection Act 2015 witch branding daayan violence victim protection",
            doc_ids=("assam-witch-hunting-2015",),
            priority=1.12,
        )
    return SourcePack(
        id="assam_witch_hunting_2015",
        title_patterns=("Assam Witch Hunting (Prohibition, Prevention and Protection) Act 2015",),
        search_query="Assam Witch Hunting Prohibition Prevention Protection Act 2015 witch branding daayan violence victim protection",
        doc_ids=("assam-witch-hunting-2015",),
        priority=0.74,
    )


def _constitution_article_21_pack(query: str) -> SourcePack:
    search_query = "Constitution of India Article 21 life personal liberty custody medical care speedy trial compensation"
    anchor_patterns = ("/sec-21",)
    if _has_any(query, ("medical", "doctor", "tb", "treatment", "hospital", "pregnant", "pregnancy", "newborn", "new born")):
        search_query = "Constitution of India Article 21 right to life prisoner medical care custody treatment"
    elif _has_any(query, ("speedy trial", "undertrial", "delay", "acquitted", "compensation")):
        search_query = "Constitution of India Article 21 speedy trial wrongful custody compensation personal liberty"
    elif _has_any(query, ("habeas corpus", "illegal detention", "illegally detained")):
        search_query = "Constitution of India Article 21 personal liberty Article 226 habeas corpus illegal detention"
        anchor_patterns = ("/sec-21", "/sec-226")
    elif _has_adult_choice_marriage_context(query):
        search_query = "Constitution of India Article 21 privacy dignity choice adult marriage partner sexual orientation"
    return SourcePack(
        id="constitution_article_21",
        title_patterns=("Constitution of India",),
        search_query=search_query,
        doc_ids=("constitution-india",),
        anchor_patterns=anchor_patterns,
        priority=1.16,
    )


def _constitution_article_22_pack(query: str) -> SourcePack:
    return SourcePack(
        id="constitution_article_22",
        title_patterns=("Constitution of India",),
        search_query="Constitution of India Article 22 arrest grounds informed consult lawyer produced before magistrate",
        doc_ids=("constitution-india",),
        anchor_patterns=("/sec-22",),
        priority=1.14,
    )


def _uses_legacy_criminal_regime(route: MatterRoute) -> bool:
    return bool(route.legal_regime and route.legal_regime.startswith("legacy_"))


def _has_negated_sexual_coercion(q: str) -> bool:
    return _has_any(q, (
        "does not force sex", "doesn't force sex", "not force sex",
        "never forces sex", "never forced sex", "no forced sex",
        "not forcing sex", "not forcing me for sex",
    ))


def _has_pmla_ed_context(text: str) -> bool:
    if _has_any(text, (
        "pmla", "enforcement directorate", "ecir", "twin condition",
        "money laundering",
    )):
        return True
    ed_masked = re.sub(r"\bed\s+tech(?:nology)?\b|\bed-tech(?:nology)?\b", "edtech", text)
    return bool(re.search(r"(?<![-\w])ed(?![-\w])", ed_masked)) and _has_any(text, (
        "summons", "notice", "raid", "raided", "arrest", "attachment",
        "provisional attachment", "ecir", "pmla", "money laundering",
        "directorate",
    ))


def _has_land_acquisition_context(text: str) -> bool:
    education_room_context = _has_any(text, (
        "engineering college", "college", "hostel room", "hostel", "dorm room",
        "campus room",
    ))
    project_land_context = _has_any(text, (
        "land acquisition", "land acquired", "village", "villages", "palli sabha",
        "gram sabha", "mining company", "mining project", "iron ore",
        "coal block", "bauxite project", "lease", "rehabilitation colony",
    ))
    if education_room_context and not project_land_context:
        return False
    explicit_acquisition = _has_any(text, (
        "land acquisition", "land acquired", "acquired for", "larr",
        "rfctlarr", "coal block", "bauxite project", "mining project",
        "iron ore mine", "mine displaced", "mining displacement",
        "land taken for highway", "taken for highway", "highway compensation",
        "road widening", "road widening compensation", "compensation not received",
        "award not paid", "payment not received",
    ))
    displacement = _has_any(text, ("displaced", "displacement", "affected family", "affected families"))
    submergence = _has_any(text, ("submerge", "submerges", "submerged", "submergence"))
    project_words = _has_any(text, (
        "project", "highway", "road widening", "acquisition", "coal block",
        "bauxite", "mining project", "mining company", "mine displaced", "iron ore",
    )) or bool(re.search(r"\bdam\b", text))
    compensation_words = _has_any(text, (
        "compensation", "award", "payment", "deposit", "not paid", "not received",
        "still not received",
    ))
    return explicit_acquisition or ((displacement or submergence or compensation_words) and project_words)


def _has_labour_overtime_register_context(text: str) -> bool:
    return _has_overtime_register_inspection_context(text) and _has_maharashtra_context(text)


def _has_overtime_register_inspection_context(text: str) -> bool:
    inspection_context = _has_any(text, (
        "labour department", "labor department", "labour inspector",
        "labor inspector", "facilitator", "inspection", "raid", "raided",
    ))
    register_context = _has_any(text, (
        "overtime register", "ot register", "register not maintained",
        "not maintained", "records not maintained", "registers", "records",
    ))
    worker_count_context = bool(re.search(r"\b(?:1[0-9]|[2-9][0-9])\s+workers?\b", text))
    overtime_context = "overtime" in text
    return inspection_context and register_context and (worker_count_context or overtime_context)


def _has_maharashtra_context(text: str) -> bool:
    return _has_any(text, ("maharashtra", "mumbai", "pune", "thane", "nagpur", "vidarbha"))


def _has_construction_worksite_context(text: str) -> bool:
    return _has_any(text, (
        "construction", "building work", "building worker", "construction worker",
        "construction site", "worksite", "site labour", "contractor site",
        "mason", "scaffold", "bocw",
    ))


def _has_tribal_land_transfer_context(text: str) -> bool:
    tribal_context = _has_any(text, (
        "tribal", "adivasi", "scheduled tribe", "st land", "munda",
        "santhal", "oraon", "khuntkatti", "cnt", "chotanagpur",
        "chota nagpur", "santhal parganas", "non tribal", "non-tribal",
    ))
    land_noun_context = bool(re.search(
        r"\b(?:land|plot|raiyat|tenancy|khata|khasra)\b",
        text,
    )) or _has_any(text, ("cnt", "chotanagpur", "chota nagpur", "santhal parganas"))
    transfer_context = _has_any(text, (
        "sold", "sale deed", "land transfer", "land transferred",
        "plot transfer", "registered deed", "without our consent",
        "restore", "restoration", "grabbed", "land grab",
        "land restoration", "mortgage", "mortgaged", "sahukar",
        "moneylender", "refusing return", "refusing to return",
        "not returning land", "took my land",
    )) or bool(re.search(
        r"\btransfer(?:red)?\s+of\s+(?:tribal\s+)?(?:land|plot)\b",
        text,
    ))
    return tribal_context and land_noun_context and transfer_context


def _has_custody_procedure_context(text: str) -> bool:
    direct = _has_any(text, (
        "lockup", "custody", "custodial", "detention", "after arrest",
        "during arrest", "not released", "did not release", "police beating",
        "police beat", "torture",
    ))
    injury_during_custody = _has_any(text, ("hurt", "assault", "injury", "medical help", "medical")) and _has_any(text, (
        "arrest", "custody", "lockup", "detention", "detained",
    ))
    return direct or injury_during_custody


def _has_custody_liberty_context(text: str) -> bool:
    return _has_custody_procedure_context(text) or _has_any(text, (
        "lockup", "custody", "custodial", "police beating", "police beat",
        "torture", "handcuff", "handcuffs", "chained", "shackled",
        "not produced", "24 hours", "twenty four hours",
        "habeas corpus", "illegal detention", "illegally detained",
        "nhrc", "human rights", "arthur road",
    ))


def _has_any(text: str, needles: tuple[str, ...]) -> bool:
    return any(needle in text for needle in needles)


def _has_pet_context(text: str) -> bool:
    return re.search(r"\b(?:pet|pets|dog|dogs|cat|cats)\b", text) is not None


def _is_plain_personal_data_breach(q: str) -> bool:
    data_context = _has_any(q, (
        "data breach", "personal data", "dpdp", "pan leaked", "aadhaar leaked",
        "aadhar leaked", "pan and aadhaar", "pan and aadhar", "data leaked",
    ))
    criminal_context = _has_any(q, (
        "otp", "phishing", "fraud", "scam", "lost money", "blackmail",
        "threat", "extortion", "intimate", "nude", "private photo",
        "sex video", "morphed", "deepfake", "account hacked", "identity theft",
        "identity misuse", "fake loan", "cheating",
    ))
    return data_context and not criminal_context


def _has_ration_context(text: str) -> bool:
    if re.search(r"\bration(?:\s+(?:card|shop|dealer|records?))?\b", text):
        return True
    return _has_any(text, (
        "pds", "fair price", "food security", "one nation one card",
        "onor c", "onorc", "no rice", "rice not given",
    ))


def _has_election_campaign_context(text: str) -> bool:
    if _has_any(text, (
        "not during election", "not election", "no election",
        "not related to election", "outside election",
    )):
        return False
    if _has_any(text, (
        "housing society election", "rwa election", "apartment election",
        "student union", "campus election", "college election",
        "school election", "association election", "cooperative society election",
        "company voting", "hr group", "job candidate", "trade union election",
        "club election", "cooperative bank election",
    )):
        return False
    public_election_context = _has_any(text, (
        "lok sabha", "rajya sabha", "vidhan sabha", "assembly election",
        "parliament election", "general election", "panchayat election",
        "municipal election", "election commission", "returning officer",
        "polling booth", "politician",
        "political party", "party worker",
    )) or re.search(r"\b(?:mla|mp|eci)\b", text) is not None
    campaign_subject = _has_any(text, (
        "candidate", "campaign", "nomination", "party worker", "politician",
        "election petition", "booth",
    ))
    return public_election_context and campaign_subject


def _is_tangible_goods_delivery_context(text: str) -> bool:
    service_context = _has_any(text, (
        "software", "saas", "website", "marketing", "design", "logo",
        "consulting", "service contract", "app development", "digital agency",
        "license seats", "licence seats", "cad seats", "service",
        "training", "course", "workshop", "wedding decoration", "decoration",
        "event management", "event", "catering service", "catering",
        "caterer", "photography", "photographer", "videography",
        "photo shoot", "photoshoot", "coaching", "audit", "repair service",
        "architect", "architecture", "interior design",
    ))
    tangible_context = _has_any(text, (
        "goods", "product", "products", "material", "materials", "stock",
        "inventory", "machine", "machinery", "equipment", "parts", "items",
        "quality issue", "formal rejection",
    ))
    delivery_context = _has_any(text, (
        "delivery", "deliver", "vendor", "seller", "supplier", "buyer",
        "cancel", "recover advance", "advance",
    ))
    if service_context and not tangible_context:
        return False
    return (tangible_context and delivery_context) or _has_any(text, (
        "vendor agreed delivery", "delivery in 30 days", "cancel and recover",
        "recover advance",
    ))


def _has_army_service_pension_context(text: str) -> bool:
    pension_context = _has_any(text, (
        "pension", "widow", "husband died", "papers", "documents",
        "service pension", "family pension",
    ))
    if not pension_context:
        return False
    military_service_context = _has_any(text, (
        "army", "defence", "defense", "soldier", "jawan", "sepoy",
        "ex serviceman", "ex-serviceman", "serving soldier", "army service",
        "in army",
    ))
    if not military_service_context:
        return False
    contractor_context = _has_any(text, (
        "civilian contractor", "contractor", "vendor", "outsourced",
        "canteen contractor", "security contractor",
    ))
    explicit_service_context = _has_any(text, (
        "soldier", "jawan", "sepoy", "ex serviceman", "ex-serviceman",
        "serving soldier", "army service", "served in army", "retired from army",
    ))
    return not contractor_context or explicit_service_context


def _has_welfare_pension_scheme_context(text: str) -> bool:
    service_or_employer_pension = _has_any(text, (
        "service pension", "family pension", "teacher", "retired teacher",
        "retired employee", "government employee", "state government retired",
        "employee pension", "epfo", "eps", "provident fund", "army",
        "defence", "defense", "military", "contractor", "canteen",
    ))
    explicit_welfare_scheme = _has_any(text, (
        "old age pension", "vridha pension", "widow pension", "disability pension",
        "indira gandhi pension", "indira gandhi national old age pension",
        "national old age pension", "national social assistance", "nsap",
        "ignwps", "ignoaps",
    ))
    if service_or_employer_pension and not _has_any(text, (
        "old age pension", "vridha pension", "disability pension",
        "indira gandhi pension", "indira gandhi national old age pension",
        "national old age pension", "national social assistance", "nsap",
        "ignoaps",
    )):
        return False
    if _has_any(text, (
        "old age pension", "vridha pension", "widow pension", "disability pension",
        "indira gandhi pension", "indira gandhi national old age pension",
        "national old age pension", "national social assistance", "nsap",
        "ignwps", "ignoaps",
    )):
        return True
    pension_problem = "pension" in text and _has_any(text, (
        "stopped", "removed", "deleted", "not paid", "not received",
        "nahi aayi", "nahi mili", "pending", "arrears", "rti",
    ))
    return pension_problem and _has_any(text, (
        "bihar", "delhi", "karnataka", "kerala", "maharashtra", "tamil nadu",
        "telangana", "uttar pradesh", "west bengal", "jharkhand", "odisha",
        "orissa", "rajasthan", "gujarat", "madhya pradesh", "chhattisgarh",
    ))


def _has_bihar_excise_jurisdiction_context(q: str) -> bool:
    if _has_any(q, (
        "bihar colony", "bihar border", "near bihar border", "bihar bhawan",
        "from bihar",
    )):
        return False
    if _has_any(q, ("delhi", "uttar pradesh", " up ", " u.p.", "noida", "lucknow")):
        return False
    return _has_any(q, (
        "bihar prohibition", "bihar excise", "in bihar", "at bihar",
        "under bihar", "bihar police", "bihar thana", "patna", "gaya",
        "muzaffarpur", "bhagalpur", "darbhanga", "purnea", "samastipur",
        "siwan", "chhapra", "motihari", "nalanda", "begusarai",
        "madhubani",
    ))


def _has_online_gambling_context(q: str) -> bool:
    gambling_context = _has_any(q, (
        "dream11", "parimatch", "betting app", "betting site",
        "online betting", "online gambling", "online rummy", "rummy app",
        "fantasy app", "real money game", "real-money game",
    ))
    stake_context = _has_any(q, (
        "lost", "recover", "money", "stake", "stakes", "wager", "bet",
        "legal", "illegal", "allowed", "ban", "banned", "50k", "lakh",
    ))
    return gambling_context and stake_context


def _has_tamil_nadu_context(q: str) -> bool:
    return _has_any(q, (
        "tamil nadu", "chennai", "coimbatore", "madurai",
        "tiruchirappalli", "trichy", "salem", "tirunelveli", "cuddalore",
    ))


def _has_caste_certificate_context(q: str) -> bool:
    certificate_context = _has_any(q, (
        "caste certificate", "sc certificate", "st certificate",
        "scheduled caste certificate", "scheduled tribe certificate",
        "community certificate",
    ))
    rejection_context = _has_any(q, (
        "rejected", "reject", "refused", "denied", "not giving",
        "not issuing", "appeal", "tehsildar", "tahsildar", "revenue officer",
    ))
    return certificate_context and rejection_context


def _has_gig_platform_work_context(q: str) -> bool:
    platform_context = _has_any(q, (
        "urban company", "housejoy", "zomato", "swiggy", "ola", "uber",
        "blinkit", "zepto", "rapido", "dunzo", "gig worker",
        "platform worker", "delivery partner", "driver partner",
        "beautician", "service partner",
    ))
    adverse_or_labour = _has_any(q, (
        "termination", "terminated", "fired", "deactivated", "suspended",
        "id blocked", "profile blocked", "3 strike", "three strike",
        "strike system", "unfair", "bad rating", "low rating",
        "labour law", "labor law", "employment", "wage", "payout",
        "earning", "full and final", "dues",
    ))
    return platform_context and adverse_or_labour


def _has_jharkhand_tribal_land_context(text: str) -> bool:
    return _has_any(text, (
        "jharkhand", "chotanagpur", "chota nagpur", "santhal parganas",
        "cnt", "spt", "ranchi", "khunti", "chaibasa", "latehar",
        "gumla", "dumka", "simdega", "lohardaga", "singhbhum",
        "palamu", "hazaribagh",
    ))


def _mentions_fir_context(text: str) -> bool:
    return bool(re.search(r"\bfir\b", text)) or _has_any(text, ("police refused", "police not", "thana", "station"))


def _is_customs_context(text: str) -> bool:
    return _has_any(text, (
        "customs", "icegate", "bill of entry", "shipping bill", "drawback",
        "import duty", "customs duty", "port hold", "classification",
        "reclassified", "shipment held at port", "duty demand",
    ))


def _is_divorce_context(text: str) -> bool:
    return _has_any(text, (
        "divorce", "mutual consent", "13b", "separation", "judicial separation",
        "both agree",
    ))


def _is_family_safety_or_support_context(text: str) -> bool:
    return _has_any(text, (
        "domestic violence", "beat", "beating", "hit me", "threat", "dowry",
        "maintenance", "school fees", "left me", "no money", "residence",
        "protection", "threw me out", "cruelty", "grabbed", "touching",
        "touched", "uncomfortable", "brother in law", "brother-in-law",
    ))


def _has_adult_choice_marriage_context(text: str) -> bool:
    choice_context = _has_any(text, (
        "forcing me to marry", "force me to marry", "forced marriage",
        "forcing marriage", "marry a girl", "marry a boy", "against my wish",
        "choice marriage", "adult relationship", "same sex", "gay",
        "lesbian", "queer", "sexual orientation", "lgbt", "lgbtq",
    ))
    adult_context = _has_adult_age_context(text) or _has_any(text, (
        "adult", "major", "i am 18", "i am 19", "i am 20", "i am 21",
        "i am 22", "i am 23", "i am 24", "i am 25", "i am 26",
        "i am 27", "i am 28", "i am 29", "i am 30",
    ))
    return choice_context and adult_context


def _has_child_age_context(text: str) -> bool:
    patterns = (
        r"\b(?:age|aged|is|was)\s+([1-9]|1[0-7])\b",
        r"\bi\s+am\s+([1-9]|1[0-7])\b",
        r"\b(?:son|daughter|boy|girl|child)\s+(?:is\s+)?([1-9]|1[0-7])\s*(?:year|years|yr|yrs)\b",
        r"\b([1-9]|1[0-7])\s*(?:year|years|yr|yrs)\s*old\b",
        r"\b([1-9]|1[0-7])\s*(?:year|years|yr|yrs)\s+(?:daughter|son|girl|boy|child|minor)\b",
        r"\b([1-9]|1[0-7])\s*(?:yo|saal)\b",
    )
    if any(re.search(pattern, text) for pattern in patterns):
        return True
    if _has_adult_age_context(text):
        return False
    return _has_any(text, ("child", "minor", "under 18", "under eighteen"))


def _has_child_intimate_image_subject_context(text: str) -> bool:
    image_context = _has_any(text, (
        "nude", "private photo", "private photos", "private picture",
        "private pictures", "intimate", "sex video", "porn", "morphed",
        "deepfake", "leaked",
    ))
    if not image_context or not _has_child_age_context(text):
        return False
    if _has_any(text, (
        "child saw", "child watched", "my child saw", "my child watched",
        "daughter saw", "son saw", "student saw", "minor saw",
    )):
        return False
    return bool(re.search(r"\bi\s+am\s+([1-9]|1[0-7])\b", text)) or _has_any(text, (
        "i am one of", "one of them", "girls in class", "boys in class",
        "schoolmate", "classmate", "minor girl", "minor boy", "child nude",
        "child porn", "child pornography", "daughter nude", "son nude",
        "my daughter", "my son", "under 18 girl", "under 18 boy",
    ))


def _has_explicit_child_age_context(text: str) -> bool:
    if _has_any(text, ("minor", "under 18", "under eighteen", "juvenile", "pocso")):
        return True
    patterns = (
        r"\b(?:age|aged|is|was)\s+([1-9]|1[0-7])\b",
        r"\b(?:son|daughter|boy|girl|child)\s+(?:is\s+)?([1-9]|1[0-7])\s*(?:year|years|yr|yrs)\b",
        r"\b([1-9]|1[0-7])\s*(?:year|years|yr|yrs)\s*old\b",
        r"\b([1-9]|1[0-7])\s*(?:year|years|yr|yrs)\s+(?:daughter|son|girl|boy|child|minor)\b",
        r"\b([1-9]|1[0-7])\s*(?:yo|saal)\b",
    )
    return any(re.search(pattern, text) for pattern in patterns)


def _has_adult_age_context(text: str) -> bool:
    patterns = (
        r"\b(?:age|aged|is|was)\s+(1[8-9]|[2-9][0-9])\b",
        r"\b(1[8-9]|[2-9][0-9])\s*(?:year|years|yr|yrs)\s*old\b",
        r"\b(1[8-9]|[2-9][0-9])\s*(?:year|years|yr|yrs)\s+(?:daughter|son|girl|boy|child)\b",
        r"\b(1[8-9]|[2-9][0-9])\s*(?:yo|saal)\b",
    )
    return any(re.search(pattern, text) for pattern in patterns)


def _is_scst_poa_context(q: str) -> bool:
    if _has_any(q, (
        "dalit", "caste", "scheduled caste", "scheduled tribe", "atrocity",
        "pahan", "sarna", "adivasi", "sc/st", "sc st",
        "untouchable", "upper caste", "munda",
    )):
        return True
    return re.search(r"\b(?:sc|st)\b", q) is not None


def _has_human_rights_commission_context(q: str) -> bool:
    direct = _has_any(q, ("nhrc", "human rights commission", "state human rights commission", "shrc"))
    custody = _has_any(q, (
        "lockup", "custody", "custodial", "police beating", "torture",
        "arthur road", "custodial death", "lockup death",
    ))
    complaint = _has_any(q, (
        "complain", "complaint", "procedure", "how to file", "medical help",
        "beating", "death", "suicide", "section 196", "torture case",
        "file police torture", "police torture case",
    ))
    return direct or (custody and complaint)


def _has_arrest_information_context(q: str) -> bool:
    arrest_or_fir = _has_any(q, (
        "arrest", "arrested", "custody", "detained", "fir copy",
        "copy of fir", "no fir copy", "police took", "police picked",
    ))
    secrecy_or_family = _has_any(q, (
        "secret", "family", "not informed", "grounds", "reason", "copy",
        "arrest memo", "no arrest memo", "dk basu", "d.k. basu",
    ))
    return arrest_or_fir and secrecy_or_family


def _has_digital_evidence_context(q: str) -> bool:
    device_context = _has_any(q, (
        "phone", "mobile", "laptop", "computer", "device", "hard disk",
        "pendrive", "pen drive", "electronic record", "server",
    ))
    platform_context = _has_any(q, (
        "insta", "instagram", "whatsapp", "telegram", "social media",
        "deleted post", "deleted posts", "tweet", "online post",
    ))
    police_context = _has_any(q, (
        "section 91", "bnss", "crpc", "notice", "summons", "police",
        "investigation", "seized", "seizure", "fir", "case",
    ))
    return (device_context or platform_context) and police_context


def _has_production_notice_context(q: str) -> bool:
    if _has_digital_device_seizure_context(q):
        return False
    return _has_any(q, (
        "section 91", "crpc 91", "summons to produce", "produce document",
        "notice asking", "summons under", "asked me to produce",
    ))


def _has_criminal_quashing_context(q: str) -> bool:
    quashing = _has_any(q, (
        "quash", "quashing", "482 crpc", "crpc 482", "section 482",
        "sec 482", "482 petition", "bnss 528", "section 528", "sec 528",
    ))
    criminal_case = _has_any(q, (
        "fir", "criminal case", "chargesheet", "charge sheet", "summons",
        "accused", "police case", "criminal proceeding", "criminal proceedings",
        "criminal complaint", "police report", "charge-sheet",
    ))
    return quashing and criminal_case


def _has_digital_device_seizure_context(q: str) -> bool:
    device_context = _has_any(q, (
        "phone", "mobile", "laptop", "computer", "device", "hard disk",
        "hard drive", "pendrive", "pen drive", "server", "electronic record",
    ))
    seizure_context = _has_any(q, ("seized", "seizure", "confiscated", "taken", "took", "kept"))
    police_context = _has_any(q, ("police", "fir", "case", "investigation", "cyber cell", "io ", "investigating officer"))
    return device_context and seizure_context and police_context


def _has_contract_labour_wage_context(q: str) -> bool:
    wage_context = _has_any(q, (
        "wage", "wages", "salary", "not paid", "unpaid",
        "dues", "wage dues", "salary dues", "4 months wages",
        "months wages", "payment of wages",
    ))
    if not wage_context:
        return False
    if _has_any(q, ("principal employer", "contract labour", "contract labor", "workmen")):
        return True
    worker_context = _has_any(q, (
        "worker", "workers", "workmen", "labour", "labor", "mazdoor",
        "site worker", "construction worker", "factory worker",
        "22 workers", "10 workers", "migrant worker",
    ))
    return _has_any(q, ("contractor", "thekedar")) and worker_context and _has_any(q, (
        "site", "worksite", "factory", "construction", "plant",
        "company", "labour", "labor", "mazdoor",
    ))


def _has_interstate_migrant_context(q: str) -> bool:
    source_place = _has_bihar_context(q) or _has_any(q, (
        "odisha", "orissa", "jharkhand", "uttar pradesh", "up worker",
        "chhattisgarh", "rajasthan", "murshidabad", "west bengal",
    ))
    destination_place = _has_any(q, (
        "bangalore", "bengaluru", "whitefield", "karnataka", "surat",
        "gujarat", "mumbai", "maharashtra", "delhi", "gurgaon",
        "gurugram", "noida", "tamil nadu", "hyderabad", "telangana",
    ))
    if source_place and destination_place:
        return True
    return _has_any(q, (
        "ismw", "inter-state migrant workmen", "inter state migrant workmen",
        "migrant registration", "migrant worker", "inter state migrant",
        "inter-state migrant", "displacement allowance", "came together",
        "brought from", "return ticket", "go back home", "walked from",
        "journey allowance", "other state", "another state",
        "from bihar", "from odisha", "from orissa", "from bengal",
        "from jharkhand", "from up ", "from uttar pradesh",
        "from chhattisgarh", "from rajasthan", "to gujarat",
        "to maharashtra", "to delhi", "to karnataka", "to tamil nadu",
    ))


def _has_bihar_context(q: str) -> bool:
    return _has_any(q, (
        "bihar", "patna", "gaya", "muzaffarpur", "bhagalpur",
        "darbhanga", "purnea", "samastipur", "siwan", "chhapra",
        "motihari", "nalanda", "begusarai", "madhubani",
    ))


def _has_elderly_woman_domestic_context(q: str) -> bool:
    woman_context = _has_any(q, (
        "mother", "saas", "mother in law", "mother-in-law", "widow",
        "elderly woman", "old woman", "she ", " her ",
    ))
    domestic_context = _has_any(q, (
        "daughter in law", "daughter-in-law", "kitchen", "not allowed",
        "own house", "own kitchen", "locked", "domestic", "shared household",
    ))
    return woman_context and domestic_context


def _has_witch_hunting_state_law_context(q: str) -> bool:
    witch_context = _has_any(q, ("daayan", "dayan", "tonhi", "daini", "witch", "witch hunting", "witch-hunting"))
    if not witch_context:
        return False
    return _has_any(q, ("assam", "barpeta", "guwahati", "dibrugarh", "jorhat"))


__all__ = ["SourcePack", "source_packs_for_route"]
