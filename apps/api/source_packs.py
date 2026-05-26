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
            ))

    elif category == "family_domestic":
        packs.append(SourcePack(
            id="pwdva_2005",
            title_patterns=("Protection of Women from Domestic Violence Act 2005",),
            search_query="Protection of Women from Domestic Violence Act 2005 section 12 protection residence maintenance",
        ))

    elif category == "senior_citizen":
        packs.append(SourcePack(
            id="senior_citizens_2007",
            title_patterns=("Maintenance and Welfare of Parents and Senior Citizens Act 2007",),
            search_query="Maintenance and Welfare of Parents and Senior Citizens Act 2007 section 4 section 23 maintenance tribunal transfer property",
        ))

    elif category == "cyber_fraud_or_harassment":
        packs.append(SourcePack(
            id="it_act_2000",
            title_patterns=("Information Technology Act 2000",),
            search_query="Information Technology Act 2000 section 66C 66D 66E 67 cyber fraud intimate image",
        ))

    elif category == "consumer":
        packs.append(SourcePack(
            id="consumer_protection_2019",
            title_patterns=("Consumer Protection Act 2019",),
            search_query="Consumer Protection Act 2019 deficiency goods service refund complaint district commission",
        ))

    elif category == "reproductive_rights_mtp":
        packs.append(SourcePack(
            id="mtp_1971",
            title_patterns=("Medical Termination of Pregnancy Act 1971",),
            search_query="Medical Termination of Pregnancy Act 1971 termination pregnancy rape survivor medical board",
        ))

    elif category == "ibc_nclt":
        packs.append(SourcePack(
            id="ibc_2016",
            title_patterns=("Insolvency and Bankruptcy Code 2016",),
            search_query="Insolvency and Bankruptcy Code 2016 section 7 section 9 operational creditor demand notice",
        ))

    elif category == "cheque_bounce":
        packs.append(SourcePack(
            id="ni_act_1881",
            title_patterns=("Negotiable Instruments Act 1881",),
            search_query="Negotiable Instruments Act 1881 section 138 section 142 cheque dishonour complaint limitation",
        ))

    elif category == "tax_gst_compliance":
        if _has_any(q, ("gst", "cgst", "gstr", "register gst")):
            packs.append(SourcePack(
                id="cgst_2017",
                title_patterns=("Central Goods and Services Tax Act 2017",),
                search_query="Central Goods and Services Tax Act 2017 section 22 registration threshold supply service",
            ))

    elif category == "trademark_ip":
        if _has_any(q, ("copyright", "song", "video", "script", "software", "unlicensed")):
            packs.append(SourcePack(
                id="copyright_1957",
                title_patterns=("Copyright Act 1957",),
                search_query="Copyright Act 1957 infringement section 51 section 52 remedies original work",
            ))

    elif category == "education_rights":
        packs.append(SourcePack(
            id="rte_2009",
            title_patterns=("Right of Children to Free and Compulsory Education Act 2009",),
            search_query="Right of Children to Free and Compulsory Education Act 2009 admission transfer certificate section 12",
        ))

    elif category == "mental_health_care_rights":
        packs.append(SourcePack(
            id="mental_healthcare_2017",
            title_patterns=("Mental Healthcare Act 2017",),
            search_query="Mental Healthcare Act 2017 supported admission rights safeguards mental health review board",
        ))

    elif category == "workplace_injury_compensation":
        packs.append(SourcePack(
            id="factories_1948",
            title_patterns=("Factories Act 1948",),
            search_query="Factories Act 1948 safety accident injury occupier inspector worker",
        ))

    elif category == "employment_wages":
        if "gratuity" in q:
            packs.append(SourcePack(
                id="gratuity_1972",
                title_patterns=("Payment of Gratuity Act 1972",),
                search_query="Payment of Gratuity Act 1972 section 7 section 8 delayed gratuity interest",
            ))
        elif _has_any(q, ("termination", "fired", "retrenchment", "labour court")):
            packs.append(SourcePack(
                id="industrial_disputes_1947",
                title_patterns=("Industrial Disputes Act 1947",),
                search_query="Industrial Disputes Act 1947 section 25F retrenchment labour court termination",
            ))
        elif "maternity" in q:
            packs.append(SourcePack(
                id="maternity_benefit_1961",
                title_patterns=("Maternity Benefit Act 1961",),
                search_query="Maternity Benefit Act 1961 section 5 section 12 maternity leave dismissal",
            ))

    return packs


def _has_any(text: str, needles: tuple[str, ...]) -> bool:
    return any(needle in text for needle in needles)


__all__ = ["SourcePack", "source_packs_for_route"]
