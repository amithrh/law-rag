#!/usr/bin/env python3
"""Timed 100-question /answer eval using the SSE `timing` event.

This runner is for product gating, not model benchmarking:
  - stage latency: preflight, route, retrieval, prompt, LLM, verifier, relevance
  - user outcome: refused/error/relevance verdict/suppressed sentences
  - matter route: category, urgency, legal regime, action pack
  - expected Act hit: did cited source metadata contain the expected Act family?

Usage:
  PYTHONPATH=. .venv/bin/python scripts/eval_timed_100.py --api http://localhost:8001
  PYTHONPATH=. .venv/bin/python scripts/eval_timed_100.py --limit 10 --api http://localhost:8001
"""
from __future__ import annotations

import argparse
import json
import random
import re
import time
import urllib.error
import urllib.request
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any

from scripts.legal_safety_eval import (
    analyze_safety_row,
    has_criminal_regime_caveat,
    summarize_safety,
)

ROOT = Path(__file__).parent.parent

_INDIA_STATE_OR_UT_TERMS = (
    "andaman", "andaman and nicobar", "andhra", "andhra pradesh",
    "arunachal", "arunachal pradesh", "assam", "bihar", "chandigarh",
    "chhattisgarh", "dadra", "dadra and nagar haveli", "daman", "daman and diu",
    "delhi", "nct delhi", "goa", "gujarat", "haryana", "himachal",
    "himachal pradesh", "jammu", "jammu and kashmir", "jharkhand", "karnataka",
    "kerala", "ladakh", "lakshadweep", "madhya pradesh", "maharashtra",
    "manipur", "meghalaya", "mizoram", "nagaland", "odisha", "orissa",
    "puducherry", "pondicherry", "punjab", "rajasthan", "sikkim",
    "tamil nadu", "telangana", "tripura", "uttar pradesh", "uttarakhand",
    "west bengal",
    # Common city/district phrasing in human prompts where state law is inferable.
    "ahmedabad", "aurangabad", "bangalore", "bengaluru", "bhopal", "chennai",
    "coimbatore", "goa", "hyderabad", "jaipur", "kochi", "kolkata",
    "lucknow", "mahabaleshwar", "mumbai", "nagpur", "noida", "patna",
    "pune", "ranchi", "surat",
)


ACT_ALIASES: dict[str, tuple[str, ...]] = {
    "BNSS": ("bnss", "bharatiya nagarik suraksha", "nagarik suraksha"),
    "BNS": ("bns", "bharatiya nyaya", "nyaya sanhita"),
    "BSA": ("bsa", "bharatiya sakshya", "sakshya adhiniyam"),
    "CrPC": ("crpc", "criminal procedure", "code of criminal procedure"),
    "IPC": ("ipc", "indian penal", "penal code"),
    "Evidence Act": ("evidence act", "indian evidence"),
    "Constitution": ("constitution", "article 226", "article 32", "article 46", "article 39a", "article 22", "article 17", "article 25", "article 341", "article 342", "schedule v", "sch v", "habeas"),
    "Consumer Protection Act": ("consumer protection", "consumer-protection", "cpa-2019"),
    "Information Technology Act": ("information technology", "it-act", "it act", "it-2000"),
    "Digital Personal Data Protection Act": ("digital personal data protection", "dpdp"),
    "Shariat Act": ("shariat", "muslim personal law", "muslim pl"),
    "Street Vendors Act": ("street vendors", "street vendor"),
    "Shops and Establishments Act": ("shops & establishments", "shops and establishments", "commercial establishments", "shop act"),
    "Article 21": ("article 21",),
    "Senior Citizens Act": ("senior citizens", "parents and senior citizens", "mwp", "maintenance and welfare of parents", "mwp-2007"),
    "PWDVA": ("domestic violence", "pwdva", "protection of women", "dv act"),
    "Dowry Prohibition Act": ("dowry prohibition",),
    "POCSO": ("pocso", "children from sexual offences"),
    "SC/ST POA Act": ("scheduled castes", "scheduled tribes", "poa", "atrocities"),
    "Scheduled Areas Land Transfer Regulation": (
        "scheduled areas land transfer", "cnt act", "chotanagpur tenancy",
        "chota nagpur tenancy", "chota-nagpur-tenancy-1908",
        "santhal parganas tenancy", "santhal-parganas-tenancy-1949",
    ),
    "NI Act": ("negotiable instruments", "ni act", "section 138", "s.138"),
    "Code on Wages": ("code on wages", "payment of wages", "minimum wages", "equal remuneration"),
    "Contract Labour Act": ("contract labour",),
    "Inter-State Migrant Workmen Act": ("inter-state migrant", "inter state migrant", "ismw"),
    "Bonded Labour Act": ("bonded labour", "bonded labor"),
    "BOCW Act": ("building and other construction workers act", "building and other construction workers (regulation", "bocw act", "bocw-1996"),
    "BOCW Cess Act": ("bocw cess", "building and other construction workers welfare cess"),
    "Child Labour Act": ("child labour", "child and adolescent labour"),
    "Employees Compensation Act": ("employees compensation", "employees' compensation", "workmen's compensation", "workmens compensation"),
    "ESI Act": ("employees state insurance", "employees' state insurance", "esi act", "esic"),
    "Social Security Code": ("code on social security", "social security code"),
    "Maternity Benefit Act": ("maternity benefit",),
    "Payment of Gratuity Act": ("payment of gratuity", "gratuity act"),
    "EPF Act": ("epf", "provident fund", "employees provident"),
    "Industrial Disputes Act": ("industrial disputes", "retrenchment"),
    "POSH Act": ("posh", "sexual harassment of women at workplace", "vishaka"),
    "Tamil Nadu Online Gambling Act": (
        "tamil nadu prohibition of online gambling",
        "tamil-nadu-online-gambling",
        "online gambling and regulation of online games act",
    ),
    "RERA": ("rera", "real estate"),
    "RTI Act": ("right to information", "rti"),
    "Legal Services Authorities Act": ("legal services authorities", "nalsa"),
    "Motor Vehicles Act": ("motor vehicles", "motor-vehicles", "themotorvehiclesact", "mact"),
    "MV Act": ("mv act", "motor vehicle act", "motor vehicles act", "motor-vehicles", "themotorvehiclesact"),
    "Motor Vehicle Aggregator Guidelines": ("motor vehicle aggregator", "mv aggregator"),
    "Family Courts Act": ("family courts", "family court"),
    "Guardians and Wards Act": ("guardians and wards", "guardian and wards", "guardians-wards"),
    "Juvenile Justice Act": ("juvenile justice", "jj act"),
    "Hindu Marriage Act": ("hindu marriage", "hma"),
    "Hindu Succession Act": ("hindu succession",),
    "Hindu Minority and Guardianship Act": ("hindu minority", "minority and guardianship", "hindu-minority-guardianship"),
    "Hindu Adoptions and Maintenance Act": ("hindu adoptions", "hama"),
    "Indian Succession Act": ("indian succession",),
    "Special Marriage Act": ("special marriage",),
    "Prohibition of Child Marriage Act": ("prohibition of child marriage", "pcma", "child marriage act"),
    "Registration Act": ("registration act",),
    "Record of Rights Act": ("record of rights", "pattadar pass books"),
    "Transfer of Property Act": ("transfer of property", "tpa"),
    "Specific Relief Act": ("specific relief",),
    "Indian Contract Act": ("indian contract", "contract act"),
    "MSMED Act": ("msmed", "msme samadhan", "facilitation council", "msmed-2006"),
    "Sale of Goods Act": ("sale of goods",),
    "Indian Partnership Act": ("indian partnership", "partnership act"),
    "LLP Act": ("llp act", "limited liability partnership"),
    "Companies Act": ("companies act 2013",),
    "Copyright Act": ("copyright",),
    "Trade Marks Act": ("trade marks", "trademark", "trade mark"),
    "FEMA": ("foreign exchange management", "fema"),
    "Limitation Act": ("limitation act",),
    "Code of Civil Procedure": ("cpc", "code of civil procedure", "order xxi", "order 21", "order v", "order ix", "order vii"),
    "Court Fees Act": ("court fees", "court fee", "court-fees", "court-fees act"),
    "Commercial Courts Act": ("commercial courts", "commercial courts act", "commercial-courts", "commercial-courts-2015"),
    "Mediation Act": ("mediation act",),
    "Income Tax Act": ("income tax", "income-tax", "itr", "tds", "26as", "43b"),
    "CGST Act": ("cgst act", "cgst-2017", "gst act", "central goods and services tax act"),
    "CGST Rules": ("cgst rules", "central goods and services tax rules", "rule 86b", "cgst-rules-2017"),
    "Customs Act": ("customs act", "customs"),
    "NDPS Act": ("ndps", "narcotic"),
    "UAPA": ("uapa", "unlawful activities"),
    "PMLA": ("pmla", "money laundering"),
    "ITPA": ("itpa", "immoral traffic"),
    "Surrogacy Act": ("surrogacy",),
    "MTP Act": ("medical termination", "mtp"),
    "Transgender Persons Act": ("transgender",),
    "RPwD Act": ("persons with disabilities", "rpwd", "rights of persons with disabilities"),
    "HIV Act": ("hiv",),
    "Mental Healthcare Act": ("mental healthcare", "mental health care"),
    "Aadhaar Act": ("aadhaar", "aadhar", "uidai", "aadhaar-2016"),
    "Telecommunications Act": ("telecommunications", "telecom act", "telecommunications-2023"),
    "National Food Security Act": ("national food security", "nfsa", "pds"),
    "MGNREGA": ("mgnrega", "nrega", "mahatma gandhi national rural employment"),
    "Forest Rights Act": ("forest rights", "fra 2006"),
    "PESA": ("pesa", "panchayats extension"),
    "Panchayati Raj Act": ("panchayati raj", "gram panchayat", "village panchayat", "panchayat"),
    "RFCTLARR Act": ("right to fair compensation", "land acquisition", "larr", "rfctlarr"),
    "MMDR Act": ("mmdr", "mines and minerals", "mmdr-1957"),
    "Forest Conservation Act": ("forest conservation", "forest (conservation)", "fca 1980", "forest-conservation-1980"),
    "Environment Protection Act": ("environment protection", "environment (protection)", "environment-protection-1986"),
    "National Green Tribunal Act": ("national green tribunal", "ngt", "ngt-2010"),
    "Water Act": ("water prevention", "water (prevention", "water pollution"),
    "Witch-Hunting State Acts": (
        "assam witch hunting", "witch hunting prohibition",
        "jharkhand prevention of witch", "jharkhand witchcraft",
        "jharkhand witch practices", "jharkhand daain", "witch practices act",
        "daain practices act", "chhattisgarh tonahi",
        "assam-witch-hunting-2015",
    ),
    "Manual Scavengers Act": ("manual scavengers", "manual scavenging"),
    "Protection of Civil Rights Act": ("protection of civil rights", "pcr act", "protection-civil-rights-1955"),
    "Right to Education Act": ("right to education", "rte"),
    "Representation of People Act": ("representation of people", "representation of the people", "rpa"),
    "Banking Regulation Act": ("banking regulation",),
    "Cooperative Societies Act": (
        "cooperative societies", "co-operative societies",
        "cooperative society", "co-operative society",
        "cooperative housing society", "co-operative housing society",
        "registrar cooperative societies", "registrar,cooperative societies",
    ),
    "Banking Ombudsman": (
        "banking ombudsman", "rbi ombudsman", "reserve bank integrated ombudsman",
        "integrated ombudsman", "rbi integrated ombudsman", "rbi-ios", "rb-ios",
        "rbi-integrated-ombudsman-2021", "fair practices", "recovery agents",
        "customer liability",
    ),
    "Credit Information Companies Act": (
        "credit information companies", "credit information companies regulation",
        "credit-information-companies-2005", "cibil",
    ),
    "IRDAI": ("irdai", "insurance regulatory", "insurance ombudsman", "insurance-ombudsman-rules-2017"),
    "FSSAI Act": ("fssai", "food safety"),
    "Prevention of Corruption Act": ("prevention of corruption", "prevention-of-corruption", "pca 1988"),
    "Births and Deaths Act": ("registration of births and deaths",),
    "Drugs and Cosmetics Act": ("drugs and cosmetics",),
    "Clinical Establishments Act": ("clinical establishments",),
    "Prison Act": ("prison act", "prisons act", "prison rules", "model prison manual", "delhi prison rules", "prisons-1894"),
    "NHRC Act": (
        "nhrc", "human rights commission", "protection of human rights",
        "protection-human-rights-1993",
    ),
    "Public Gambling Act": ("public gambling", "public-gambling", "the public gambling act"),
    "State Pension Scheme": (
        "pension rules", "widow pension", "old age pension",
        "indira gandhi national old age pension", "indira gandhi pension",
        "national old age pension", "national social assistance", "nsap",
        "ignwps", "ignoaps",
    ),
    "Army Pension Regulations": (
        "pension regulations for the army", "pension-regulations-army-2008",
        "army pension", "service pension", "family pension",
    ),
    "State Welfare Scheme": (
        "mukhyamantri", "kanya vivah", "national rural health mission",
        "national health mission", "nrhm", "nhm", "asha incentives",
        "nhm-asha-incentives-2025",
    ),
    "State Excise Act": (
        "state prohibition act", "state prohibition", "state excise act",
        "state excise acts", "prohibition / excise", "bihar prohibition",
        "gujarat prohibition", "excise act", "excise acts",
    ),
    "Cattle Preservation Act": ("cattle preservation",),
    "SARFAESI": ("sarfaesi",),
    "IBC": ("insolvency", "bankruptcy", "ibc"),
    "Gazette Name Change Procedure": (
        "gazette notification process", "change of name", "change of name adult",
        "name change", "gazette of india", "department of publication",
    ),
    "Trade Marks Opposition Procedure": ("trade marks", "trademark", "trade mark"),
    "RFCTLARR Compensation Procedure": ("right to fair compensation", "land acquisition", "rfctlarr"),
    "Lok Adalat Procedure": ("legal services authorities", "lok adalat"),
    "Maharashtra Shops Register Procedure": ("maharashtra shops", "shops and establishments"),
    "Untouchability Civil Rights Procedure": ("constitution", "article 17", "protection of civil rights"),
    "RBI Ombudsman Credit Procedure": ("rbi ombudsman credit procedure", "reserve bank integrated ombudsman", "credit information companies", "cibil"),
}

PROCEDURE_SOURCE_KEYS = {"Gazette Name Change Procedure"}

PROCEDURE_REQUIRED_ANCHORS: dict[str, tuple[str, ...]] = {
    "Gazette Name Change Procedure": (
        "deptpub-name-change-adult-guidelines#adult-required-documents",
        "deptpub-name-change-adult-guidelines#adult-formalities",
        "deptpub-name-change-adult-guidelines#egazette-download-and-submission",
    ),
    "JJ Age Determination Procedure": (
        "jj-2015/sec-9",
        "jj-2015/sec-94",
    ),
    "Trade Marks Opposition Procedure": (
        "trade-marks-1999/sec-21",
    ),
    "RFCTLARR Compensation Procedure": (
        "rfctlarr-2013/sec-77-a",
        "rfctlarr-2013/sec-64",
    ),
    "Lok Adalat Procedure": (
        "legal-services-authorities-1987/sec-20",
    ),
    "Maharashtra Shops Register Procedure": (
        "maharashtra-shops-establishments-2017/sec-25",
        "maharashtra-shops-establishments-2017/sec-28",
    ),
    "Untouchability Civil Rights Procedure": (
        "constitution-india/sec-17",
        "protection-civil-rights-1955/sec-3",
    ),
    "RBI Ombudsman Credit Procedure": (
        "rbi-integrated-ombudsman-2021/sec-2",
        "credit-information-companies-2005/sec-20",
    ),
}


def load_eval_rows(queries_dir: Path, *, limit: int, seed: int) -> list[dict[str, Any]]:
    by_persona: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for path in sorted(queries_dir.glob("*.jsonl")):
        persona = path.stem
        # JSONL records are LF-delimited; splitlines() treats U+0085 as a newline.
        for line in path.read_text(encoding="utf-8").split("\n"):
            if not line.strip():
                continue
            row = json.loads(line)
            row.setdefault("persona", persona)
            by_persona[row["persona"]].append(row)

    rng = random.Random(seed)
    for rows in by_persona.values():
        rng.shuffle(rows)

    selected: list[dict[str, Any]] = []
    personas = sorted(by_persona)
    cursor = {p: 0 for p in personas}
    while len(selected) < limit:
        progressed = False
        for persona in personas:
            idx = cursor[persona]
            rows = by_persona[persona]
            if idx >= len(rows):
                continue
            selected.append(rows[idx])
            cursor[persona] += 1
            progressed = True
            if len(selected) >= limit:
                break
        if not progressed:
            break
    return selected


def jsonl_dumps(row: dict[str, Any]) -> str:
    """Serialize one JSONL row without raw Unicode line-separator bytes."""
    return (
        json.dumps(row, ensure_ascii=False)
        .replace("\u0085", "\\u0085")
        .replace("\u2028", "\\u2028")
        .replace("\u2029", "\\u2029")
    )


def stream_answer(api: str, query: str, *, timeout_s: int) -> dict[str, Any]:
    req = urllib.request.Request(
        f"{api.rstrip('/')}/answer",
        data=json.dumps({"q": query, "top_k": 8}).encode("utf-8"),
        headers={"Content-Type": "application/json", "Accept": "text/event-stream"},
        method="POST",
    )
    out: dict[str, Any] = {
        "events": Counter(),
        "sentences": [],
        "suppressed_count": 0,
        "refused": None,
        "error": None,
        "relevance": None,
        "coverage": None,
        "passages": [],
        "sources": [],
        "matter_route": None,
        "legal_issue_plan": None,
        "timing": None,
        "wall_ms": None,
    }
    t0 = time.perf_counter()
    try:
        with urllib.request.urlopen(req, timeout=timeout_s) as resp:
            event_name = "message"
            for raw in resp:
                line = raw.decode("utf-8", errors="replace").rstrip("\n")
                if not line:
                    continue
                if line.startswith("event:"):
                    event_name = line.split(":", 1)[1].strip()
                    continue
                if not line.startswith("data:"):
                    continue
                payload = line.split(":", 1)[1].strip()
                try:
                    data = json.loads(payload)
                except json.JSONDecodeError:
                    data = payload
                out["events"][event_name] += 1
                if event_name == "matter_route":
                    out["matter_route"] = data
                elif event_name == "legal_issue_plan":
                    out["legal_issue_plan"] = data if isinstance(data, dict) else None
                elif event_name == "coverage":
                    out["coverage"] = data
                elif event_name == "passages":
                    out["passages"] = data if isinstance(data, list) else []
                elif event_name == "sentence":
                    out["sentences"].append(data)
                elif event_name == "suppressed":
                    out["suppressed_count"] += 1
                elif event_name == "refused":
                    out["refused"] = data
                elif event_name == "sources":
                    out["sources"] = data if isinstance(data, list) else []
                elif event_name == "relevance":
                    out["relevance"] = data
                elif event_name == "timing":
                    out["timing"] = data
                elif event_name == "error":
                    out["error"] = data
    except urllib.error.HTTPError as e:
        out["error"] = {"message": f"HTTP {e.code}: {e.read().decode(errors='replace')[:200]}"}
    except Exception as e:
        out["error"] = {"message": f"{type(e).__name__}: {e}"}
    out["wall_ms"] = round((time.perf_counter() - t0) * 1000, 1)
    out["events"] = dict(out["events"])
    return out


def expected_act_keys(hint: str | None, query: str | None = None) -> list[str]:
    if not hint:
        return []
    h = hint.lower()
    q = (query or "").lower()
    keys: list[str] = []
    for canonical, aliases in ACT_ALIASES.items():
        if (
            canonical in PROCEDURE_REQUIRED_ANCHORS
            and canonical != "Gazette Name Change Procedure"
            and canonical.lower() not in h
        ):
            continue
        if canonical == "Information Technology Act" and _is_income_tax_it_act_43b_hint(h):
            continue
        if any(_alias_in_text(alias, h) for alias in aliases):
            keys.append(canonical)
    if _is_income_tax_it_act_43b_hint(h):
        keys.append("Income Tax Act")
    if (
        "age determination" in h
        and re.search(r"\bs\.?\s*9\b|\bsection\s+9\b", h)
        and re.search(r"\bs\.?\s*94\b|\bsection\s+94\b", h)
    ):
        keys.append("JJ Age Determination Procedure")
    keys = sorted(set(keys))
    if q:
        keys = _apply_conditional_expected_keys(keys, h, q)
    return keys


def _apply_conditional_expected_keys(keys: list[str], hint: str, query: str) -> list[str]:
    out = list(keys)
    if "BNS" in out and "IPC" in out:
        if _has_legacy_criminal_date_context(query):
            out.remove("BNS")
        else:
            out.remove("IPC")
    if "BNSS" in out and "CrPC" in out:
        if _has_legacy_criminal_date_context(query):
            out.remove("BNSS")
        else:
            out.remove("CrPC")
    if "Panchayati Raj Act" in out and not _has_india_state_or_ut_context(query):
        out.remove("Panchayati Raj Act")
        if "Constitution" not in out:
            out.append("Constitution")
    if "Cooperative Societies Act" in out and not _has_india_state_or_ut_context(query):
        out.remove("Cooperative Societies Act")
    if (
        "SC/ST POA Act" in out
        and (
            re.search(r"\bif\s+(?:victim|person|worker|family)\s+is\s+(?:sc/st|sc|st|scheduled caste|scheduled tribe)\b", hint)
            or ("Bonded Labour Act" in out and _has_bonded_labour_context(query))
        )
        and not _has_scst_protected_context(query)
    ):
        out.remove("SC/ST POA Act")
    if "State Pension Scheme" in out:
        if _has_army_service_pension_context(query):
            out.remove("State Pension Scheme")
            if "Army Pension Regulations" not in out:
                out.append("Army Pension Regulations")
        elif not _has_specific_pension_scheme_context(query):
            out.remove("State Pension Scheme")
    if "State Excise Act" in out and not _has_state_excise_jurisdiction_context(query):
        out.remove("State Excise Act")
    if "Right to Education Act" in out and _has_education_loan_context(query):
        out.remove("Right to Education Act")
        if "Banking Ombudsman" not in out:
            out.append("Banking Ombudsman")
    return sorted(set(out))


def _has_scst_protected_context(text: str) -> bool:
    return bool(re.search(r"\b(?:sc|st)\b", text)) or any(
        term in text
        for term in (
            "dalit", "scheduled caste", "scheduled tribe", "sc/st", "sc st",
            "adivasi", "tribal", "untouchable", "chamar",
            "munda", "sarna", "pahan",
        )
    )


def _has_bonded_labour_context(text: str) -> bool:
    return any(
        term in text
        for term in (
            "bonded labour", "bonded labor", "no wages", "just food",
            "release certificate", "rehab money", "cannot leave",
            "not letting leave", "must work till loan", "advance",
        )
    )


def _has_education_loan_context(text: str) -> bool:
    q = text.lower()
    loan_context = any(term in q for term in ("education loan", "student loan", "loan for education", "loan for college", "loan for school"))
    bank_context = any(term in q for term in ("bank", "nbfc", "loan"))
    school_access_context = any(term in q for term in ("admission denied", "school admission", "rte quota", "tc refused", "transfer certificate"))
    return loan_context and bank_context and not school_access_context


def _has_legacy_criminal_date_context(text: str) -> bool:
    return bool(
        re.search(r"\b(?:19|20)(?:[0-1]\d|2[0-3])\b", text)
        or re.search(r"\b2024\b", text) and _has_any_date_before_july_2024(text)
        or any(
            term in text
            for term in (
                "before july 2024", "before 1 july 2024", "before 01 july 2024",
                "before 1st july 2024", "before bns", "old ipc", "ipc case",
                "crpc case", "2023 fir", "2022 fir", "2021 fir",
            )
        )
    )


def _has_any_date_before_july_2024(text: str) -> bool:
    return any(
        term in text
        for term in (
            "jan 2024", "feb 2024", "mar 2024", "apr 2024", "may 2024", "jun 2024",
            "january 2024", "february 2024", "march 2024", "april 2024", "june 2024",
            "1/2024", "2/2024", "3/2024", "4/2024", "5/2024", "6/2024",
            "01/2024", "02/2024", "03/2024", "04/2024", "05/2024", "06/2024",
        )
    )


def _has_specific_pension_scheme_context(text: str) -> bool:
    welfare_scheme_context = any(
        term in text
        for term in (
            "widow pension", "old age pension", "disability pension", "army pension",
            "epfo", "eps", "provident fund",
            "indira gandhi pension", "indira gandhi national old age pension",
            "national old age pension", "national social assistance", "nsap",
            "ignwps", "ignoaps",
        )
    )
    if welfare_scheme_context:
        return True
    if any(term in text for term in ("family pension", "service pension")):
        return False
    return _has_india_state_or_ut_context(text) and "pension" in text


def _has_army_service_pension_context(text: str) -> bool:
    return "pension" in text and any(
        term in text
        for term in (
            "army", "defence", "defense", "soldier", "military",
        )
    )


def _has_state_excise_jurisdiction_context(text: str) -> bool:
    return "abkari" in text or _has_india_state_or_ut_context(text)


def _has_india_state_or_ut_context(text: str) -> bool:
    return any(term in text for term in _INDIA_STATE_OR_UT_TERMS)


def _is_income_tax_it_act_43b_hint(text: str) -> bool:
    return bool(re.search(r"\bit\s+act\b", text)) and bool(re.search(r"\b43b(?:\(h\))?\b", text))


def _alias_in_text(alias: str, text: str) -> bool:
    if not alias:
        return False
    pattern = re.escape(alias.strip().lower())
    pattern = pattern.replace(r"\ ", r"\s+")
    pattern = pattern.replace(r"\-", r"[-\s]?")
    return re.search(rf"(?<![a-z0-9]){pattern}(?![a-z0-9])", text) is not None


def re_search_word(term: str, text: str) -> bool:
    return re.search(rf"\b{re.escape(term)}\b", text) is not None


def expected_act_hit(keys: list[str], sources: list[dict[str, Any]], passages: list[dict[str, Any]]) -> bool | None:
    if not keys:
        return None
    items = [item for item in [*sources, *passages] if isinstance(item, dict)]
    if not items:
        return False
    hits: dict[str, bool] = {}
    for key in keys:
        if key == "Article 21":
            hits[key] = any(
                _alias_in_text("constitution", _item_blob(item))
                and (
                    _alias_in_text("article 21", _item_blob(item))
                    or _alias_in_text("article-21", _item_blob(item))
                    or "/sec-21" in _item_blob(item)
                )
                and _is_statutory_source_item(item)
                for item in items
            )
            continue
        if key == "JJ Age Determination Procedure":
            required = PROCEDURE_REQUIRED_ANCHORS[key]
            hits[key] = all(
                any(
                    _procedure_anchor_matches(str(item.get("anchor") or ""), anchor)
                    and _is_statutory_source_item(item)
                    for item in items
                )
                for anchor in required
            )
            continue
        aliases = ACT_ALIASES.get(key, (key.lower(),))
        if key in PROCEDURE_SOURCE_KEYS:
            hits[key] = any(
                _alias_in_text(alias, _item_blob(item))
                and _is_official_procedure_source_item(item)
                for alias in aliases
                for item in items
            )
            continue
        hits[key] = any(
            _alias_in_text(alias, _item_blob(item))
            and _is_statutory_source_item(item)
            for alias in aliases
            for item in items
        )
    return all(hits.values())


def _item_blob(item: dict[str, Any]) -> str:
    return (
        str(item.get("title", ""))
        + " "
        + str(item.get("anchor", ""))
        + " "
        + str(item.get("citation", ""))
        + " "
        + str(item.get("statute_short", ""))
    ).lower()


def _is_statutory_source_item(item: dict[str, Any]) -> bool:
    source_type = str(item.get("source_type") or "").lower()
    if source_type == "bare_act":
        return True
    if source_type in {"guideline", "circular", "notification", "scheme", "rule"}:
        return True
    if source_type.endswith("judgment"):
        return False
    title = str(item.get("title") or "").lower()
    if " versus " in title or " vs " in title or " v. " in title:
        return False
    anchor = str(item.get("anchor") or "").lower()
    if re.match(r"^(?:hc/|\d{4}-insc)", anchor):
        return False
    if anchor.startswith("constitution-india"):
        return True
    if re.search(r"\b(act|code|constitution|regulation|rules|scheme|guideline|guidelines|notification|circular)\b", title):
        return True
    if any(marker in title for marker in ("sanhita", "adhiniyam")):
        return True
    return bool(anchor and "/" in anchor)


def _is_official_procedure_source_item(item: dict[str, Any]) -> bool:
    source_type = str(item.get("source_type") or "").lower()
    if source_type not in {"circular", "notification", "guideline"}:
        return False
    anchor = str(item.get("anchor") or "").lower()
    return any(
        _procedure_anchor_matches(anchor, required)
        for required_anchors in PROCEDURE_REQUIRED_ANCHORS.values()
        for required in required_anchors
    )


def expected_procedure_anchor_coverage(
    keys: list[str],
    sources: list[dict[str, Any]],
    passages: list[dict[str, Any]],
    sentences: list[dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    """Track whether procedural gold sources covered every required sub-anchor.

    The normal Expected Act metric intentionally asks a coarser question:
    did the answer cite a valid official source for this expected authority?
    For procedural sources, production gates also need to know whether the
    cited sources cover each required sub-part of the official procedure.
    """
    required_by_key = {
        key: PROCEDURE_REQUIRED_ANCHORS[key]
        for key in keys
        if key in PROCEDURE_REQUIRED_ANCHORS
    }
    if not required_by_key:
        return {}

    items = [item for item in [*(sources or []), *(passages or [])] if isinstance(item, dict)]
    cited_indices = _cited_source_indices(sentences)
    cited_items = [
        item
        for item in items
        if isinstance(item.get("index"), int) and item["index"] in cited_indices
    ]

    out: dict[str, dict[str, Any]] = {}
    for key, required_anchors in required_by_key.items():
        present = _matched_required_anchors(key, required_anchors, items)
        cited = _matched_required_anchors(key, required_anchors, cited_items)
        out[key] = {
            "required": list(required_anchors),
            "present": present,
            "cited": cited,
            "present_ok": len(present) == len(required_anchors),
            "cited_ok": len(cited) == len(required_anchors),
            "missing_present": [anchor for anchor in required_anchors if anchor not in present],
            "missing_cited": [anchor for anchor in required_anchors if anchor not in cited],
        }
    return out


def _matched_required_anchors(key: str, required_anchors: tuple[str, ...], items: list[dict[str, Any]]) -> list[str]:
    found: list[str] = []
    for required in required_anchors:
        if any(
            _procedure_anchor_matches(str(item.get("anchor") or ""), required)
            and _valid_procedure_source_type(key, item)
            for item in items
        ):
            found.append(required)
    return found


def _valid_procedure_source_type(key: str, item: dict[str, Any]) -> bool:
    if key == "Gazette Name Change Procedure":
        return str(item.get("source_type") or "").lower() in {"circular", "notification", "guideline"}
    if key == "JJ Age Determination Procedure":
        return _is_statutory_source_item(item)
    return True


def _procedure_anchor_matches(anchor: str, required: str) -> bool:
    anchor_l = anchor.lower()
    required_l = required.lower()
    return (
        anchor_l == required_l
        or anchor_l.startswith(required_l + "@")
        or anchor_l.startswith(required_l + "__")
    )


def _cited_source_indices(sentences: list[dict[str, Any]]) -> set[int]:
    cited_indices: set[int] = set()
    for sentence in sentences:
        if not isinstance(sentence, dict):
            continue
        text = str(sentence.get("text") or "")
        for match in re.finditer(r"\[(\d{1,3})\]", text):
            cited_indices.add(int(match.group(1)))
    return cited_indices


def expected_act_cited_hit(
    keys: list[str],
    sources: list[dict[str, Any]],
    passages: list[dict[str, Any]],
    sentences: list[dict[str, Any]],
) -> bool | None:
    if not keys:
        return None
    cited_indices = _cited_source_indices(sentences)
    if not cited_indices:
        return False

    by_index: dict[int, dict[str, Any]] = {}
    for item in [*(sources or []), *(passages or [])]:
        if not isinstance(item, dict):
            continue
        idx = item.get("index")
        if isinstance(idx, int) and idx in cited_indices and idx not in by_index:
            by_index[idx] = item
    if not by_index:
        return False
    return expected_act_hit(keys, list(by_index.values()), [])


def answer_quality_flags(row: dict[str, Any]) -> list[str]:
    flags: list[str] = []
    answer_text = str(row.get("answer_text") or "").strip()
    answer_lower = answer_text.lower()
    if not answer_text and not row.get("refused") and not row.get("error"):
        flags.append("empty_answer")
    if row.get("expected_act_cited_hit") is False:
        flags.append("expected_act_not_cited")
    if any(
        not coverage.get("cited_ok")
        for coverage in (row.get("expected_procedure_anchor_coverage") or {}).values()
    ):
        flags.append("expected_procedure_anchors_not_cited")
    if answer_text and not row.get("refused") and not row.get("error"):
        if "**what you can do next**" not in answer_lower:
            flags.append("missing_next_step_section")
        if int(row.get("suppressed_count") or 0) > 0:
            flags.append("suppressed_sentences")
        if int(row.get("ok_sentences") or 0) == 0:
            flags.append("zero_ok_legal_sentences")
        if (
            row.get("legal_regime") == "incident_date_needed_for_bns_bnss_bsa_vs_ipc_crpc"
            and _uses_criminal_code_framing(answer_lower)
            and not has_criminal_regime_caveat(answer_lower)
        ):
            flags.append("missing_criminal_regime_caveat")
    if "provided passages do not state a concrete next step" in answer_lower:
        flags.append("no_concrete_next_step")
    next_header = "**what you can do next**"
    if next_header in answer_lower:
        tail = answer_lower.rsplit(next_header, 1)[1].strip()
        if not tail:
            flags.append("dangling_next_step_header")
        elif "provided passages do not state a concrete next step" in tail:
            flags.append("no_concrete_next_step")
    return list(dict.fromkeys(flags))


def _uses_criminal_code_framing(text: str) -> bool:
    return any(
        term in text
        for term in (
            "bns", "bnss", "bharatiya nyaya sanhita", "bharatiya nagarik suraksha",
            "ipc", "crpc", "indian penal code", "code of criminal procedure",
        )
    )


def flatten_row(eval_row: dict[str, Any], observed: dict[str, Any]) -> dict[str, Any]:
    route = observed.get("matter_route") or {}
    plan = observed.get("legal_issue_plan") or {}
    timing = observed.get("timing") or {}
    relevance = observed.get("relevance") or {}
    refused = observed.get("refused")
    error = observed.get("error")
    expected_keys = expected_act_keys(eval_row.get("expected_act_hint"), eval_row.get("query"))
    hit = expected_act_hit(expected_keys, observed.get("sources") or [], observed.get("passages") or [])
    sentences = observed.get("sentences") or []
    cited_hit = expected_act_cited_hit(
        expected_keys,
        observed.get("sources") or [],
        observed.get("passages") or [],
        sentences,
    )
    procedure_anchor_coverage = expected_procedure_anchor_coverage(
        expected_keys,
        observed.get("sources") or [],
        observed.get("passages") or [],
        sentences,
    )
    action_pack = route.get("action_pack") or {}
    row = {
        "query": eval_row.get("query"),
        "persona": eval_row.get("persona"),
        "expected_category": eval_row.get("expected_category"),
        "expected_act_hint": eval_row.get("expected_act_hint"),
        "expected_act_keys": expected_keys,
        "expected_act_hit": hit,
        "expected_act_cited_hit": cited_hit,
        "expected_procedure_anchor_coverage": procedure_anchor_coverage,
        "is_accused_subject": bool(eval_row.get("is_accused_subject")),
        "route_category": route.get("category"),
        "route_label": route.get("label"),
        "route_urgency": route.get("urgency"),
        "route_confidence": route.get("confidence"),
        "legal_regime": route.get("legal_regime"),
        "route_required_sources": route.get("required_sources") or [],
        "route_forums": route.get("forums") or [],
        "route_missing_facts": route.get("missing_facts") or [],
        "action_pack_id": action_pack.get("id") if action_pack else None,
        "action_pack_cautions": action_pack.get("cautions") or [],
        "action_pack_next_steps": action_pack.get("next_steps") or [],
        "red_flags": route.get("red_flags") or [],
        "legal_issue_plan": plan,
        "plan_primary_issue": plan.get("primary_issue"),
        "plan_secondary_issues": plan.get("secondary_issues") or [],
        "plan_user_role": plan.get("user_role"),
        "plan_desired_outcome": plan.get("desired_outcome"),
        "plan_safety_flags": plan.get("safety_flags") or [],
        "refused": bool(refused),
        "refused_reason": refused.get("reason") if isinstance(refused, dict) else None,
        "error": error.get("message") if isinstance(error, dict) else error,
        "relevance_verdict": relevance.get("verdict"),
        "relevance_score": relevance.get("score"),
        "sentence_count": len(sentences),
        "ok_sentences": sum(1 for s in sentences if s.get("status") == "ok"),
        "weak_sentences": sum(1 for s in sentences if s.get("status") == "weak_support"),
        "suppressed_count": observed.get("suppressed_count", 0),
        "answer_text": " ".join(str(s.get("text") or "") for s in sentences if isinstance(s, dict))[:4000],
        "source_count": len(observed.get("sources") or []),
        "top_sources": [
            {
                "title": s.get("title"),
                "anchor": s.get("anchor"),
                "court": s.get("court"),
                "citation": s.get("citation"),
                "source_type": s.get("source_type"),
                "document_id": s.get("document_id"),
                "statute_short": s.get("statute_short"),
            }
            for s in (observed.get("sources") or observed.get("passages") or [])[:5]
            if isinstance(s, dict)
        ],
        "timing": timing,
        "wall_ms": observed.get("wall_ms"),
        "events": observed.get("events"),
    }
    row["answer_quality_flags"] = answer_quality_flags(row)
    row["legal_safety"] = analyze_safety_row(row)
    return row


def percentile(values: list[float], pct: float) -> float | None:
    vals = sorted(v for v in values if v is not None)
    if not vals:
        return None
    if len(vals) == 1:
        return vals[0]
    idx = (len(vals) - 1) * pct
    lo = int(idx)
    hi = min(lo + 1, len(vals) - 1)
    frac = idx - lo
    return vals[lo] * (1 - frac) + vals[hi] * frac


def fmt_ms(value: float | None) -> str:
    if value is None:
        return "n/a"
    return f"{value / 1000:.1f}s"


def _clip(value: object, limit: int = 90) -> str:
    text = "" if value is None else str(value)
    text = text.replace("|", " ").replace("\n", " ").strip()
    return text[:limit]


def write_report(rows: list[dict[str, Any]], out: Path, report: Path) -> None:
    scored_act = [r for r in rows if r["expected_act_hit"] is not None]
    unscored_act = [r for r in rows if r["expected_act_hint"] and r["expected_act_hit"] is None]
    act_hits = sum(1 for r in scored_act if r["expected_act_hit"])
    scored_cited_act = [r for r in rows if r.get("expected_act_cited_hit") is not None]
    cited_act_hits = sum(1 for r in scored_cited_act if r.get("expected_act_cited_hit"))
    refused = sum(1 for r in rows if r["refused"])
    errors = sum(1 for r in rows if r["error"])
    verdicts = Counter(r["relevance_verdict"] or ("refused" if r["refused"] else "no_relevance") for r in rows)
    routes = Counter(r["route_category"] or "unknown" for r in rows)
    action_packs = Counter(r["action_pack_id"] or "none" for r in rows)
    safety = summarize_safety(rows)
    safety_labels = Counter(safety["label_counts"])
    quality_flags = Counter(
        flag
        for r in rows
        for flag in (r.get("answer_quality_flags") or [])
    )
    procedure_coverages = [
        coverage
        for r in rows
        for coverage in (r.get("expected_procedure_anchor_coverage") or {}).values()
    ]
    procedure_cited_ok = sum(1 for coverage in procedure_coverages if coverage.get("cited_ok"))

    stage_names = [
        "total_ms",
        "matter_route_ms",
        "llm_preflight_ms",
        "query_expand_ms",
        "retrieval_single_query_ms",
        "single_expanded_retrieval_ms",
        "variant_candidate_retrieval_ms",
        "required_source_pack_ms",
        "variant_rerank_ms",
        "retrieval_ms",
        "prompt_build_ms",
        "llm_stream_ms",
        "verification_ms",
        "relevance_ms",
    ]
    lines = [
        f"# Timed {len(rows)}-question eval",
        "",
        f"Rows: {len(rows)}",
        f"Input/output: `{out}`",
        "",
        "## Outcome",
        "",
        f"- Refused: {refused}/{len(rows)}",
        f"- Errors: {errors}/{len(rows)}",
        f"- Relevance verdicts: {dict(verdicts)}",
        f"- Expected Act hit: {act_hits}/{len(scored_act)} ({(act_hits / len(scored_act) * 100) if scored_act else 0:.1f}%)",
        f"- Expected Act cited hit: {cited_act_hits}/{len(scored_cited_act)} ({(cited_act_hits / len(scored_cited_act) * 100) if scored_cited_act else 0:.1f}%)",
        f"- Expected Act unscored: {len(unscored_act)}/{len(rows)}",
        f"- Expected procedure anchor cited coverage: {procedure_cited_ok}/{len(procedure_coverages)} ({(procedure_cited_ok / len(procedure_coverages) * 100) if procedure_coverages else 0:.1f}%)",
        f"- Answer quality flags: {dict(quality_flags)}",
        f"- Legal-safety gate: {safety['gate']} ({safety['hard_fails']}/{len(rows)} hard fails)",
        "",
        "## Latency",
        "",
        "| stage | p50 | p90 | max |",
        "| --- | ---: | ---: | ---: |",
    ]
    for stage in stage_names:
        vals = [
            (r.get("timing") or {}).get(stage)
            for r in rows
            if isinstance(r.get("timing"), dict)
        ]
        vals = [float(v) for v in vals if isinstance(v, int | float)]
        lines.append(
            f"| {stage} | {fmt_ms(percentile(vals, 0.50))} | "
            f"{fmt_ms(percentile(vals, 0.90))} | {fmt_ms(max(vals) if vals else None)} |"
        )

    lines.extend([
        "",
        "## Route Distribution",
        "",
        "| route | count |",
        "| --- | ---: |",
    ])
    for route, count in routes.most_common():
        lines.append(f"| {route} | {count} |")

    lines.extend([
        "",
        "## Action Packs",
        "",
        "| action_pack | count |",
        "| --- | ---: |",
    ])
    for pack, count in action_packs.most_common():
        lines.append(f"| {pack} | {count} |")

    lines.extend([
        "",
        "## Answer Quality Flags",
        "",
        "| flag | count |",
        "| --- | ---: |",
    ])
    for flag, count in quality_flags.most_common():
        lines.append(f"| {flag} | {count} |")
    if not quality_flags:
        lines.append("| none | 0 |")

    lines.extend([
        "",
        "## Legal Safety Gate",
        "",
        f"Gate: **{safety['gate']}**",
        "",
        "| label | count |",
        "| --- | ---: |",
    ])
    for label in (
        "wrong_forum",
        "wrong_deadline",
        "wrong_regime",
        "dangerous_off_topic",
        "unsafe_refusal",
        "dangerous_framing",
    ):
        lines.append(f"| {label} | {safety_labels.get(label, 0)} |")

    safety_failures = [r for r in rows if (r.get("legal_safety") or {}).get("hard_fail")][:15]
    lines.extend([
        "",
        "### Legal-Safety Failures",
        "",
        "| labels | route | expected | query | reasons |",
        "| --- | --- | --- | --- | --- |",
    ])
    for r in safety_failures:
        safety_row = r.get("legal_safety") or {}
        labels = ", ".join(k for k, v in (safety_row.get("labels") or {}).items() if v)
        q = (r["query"] or "").replace("|", " ")[:90]
        reasons = "; ".join(safety_row.get("reasons") or []).replace("|", " ")[:140]
        lines.append(
            f"| {labels} | {r.get('route_category')} | {r.get('expected_category')} | {q} | {reasons} |"
        )

    worst_total = sorted(
        rows,
        key=lambda r: (r.get("timing") or {}).get("total_ms") or r.get("wall_ms") or 0,
        reverse=True,
    )[:15]
    lines.extend([
        "",
        "## Slowest Rows",
        "",
        "| total | retrieval | llm | verify | route | query |",
        "| ---: | ---: | ---: | ---: | --- | --- |",
    ])
    for r in worst_total:
        t = r.get("timing") or {}
        lines.append(
            f"| {fmt_ms(t.get('total_ms') or r.get('wall_ms'))} | "
            f"{fmt_ms(t.get('retrieval_ms'))} | {fmt_ms(t.get('llm_stream_ms'))} | "
            f"{fmt_ms(t.get('verification_ms'))} | {r.get('route_category')} | {_clip(r.get('query'))} |"
        )

    lines.extend([
        "",
        "## Expected-Act Unscored",
        "",
        "| persona | hint | route | query | reason |",
        "| --- | --- | --- | --- | --- |",
    ])
    for r in unscored_act[:20]:
        lines.append(
            f"| {r.get('persona')} | {_clip(r.get('expected_act_hint'))} | "
            f"{r.get('route_category')} | {_clip(r.get('query'))} | "
            "state/procedure source key unavailable or conditional |"
        )
    if not unscored_act:
        lines.append("| none | n/a | n/a | n/a | n/a |")

    misses = [r for r in scored_act if r["expected_act_hit"] is False][:20]
    lines.extend([
        "",
        "## Expected-Act Misses",
        "",
        "| persona | expected | route | query | top source |",
        "| --- | --- | --- | --- | --- |",
    ])
    for r in misses:
        source = r["top_sources"][0]["title"] if r["top_sources"] else ""
        expected = ", ".join(r["expected_act_keys"])
        lines.append(
            f"| {r.get('persona')} | {expected} | {r.get('route_category')} | {_clip(r.get('query'))} | {_clip(source)} |"
        )

    cited_misses = [r for r in scored_cited_act if r.get("expected_act_cited_hit") is False][:20]
    lines.extend([
        "",
        "## Expected-Act Cited Misses",
        "",
        "| persona | expected | route | query | cited answer excerpt |",
        "| --- | --- | --- | --- | --- |",
    ])
    for r in cited_misses:
        expected = ", ".join(r["expected_act_keys"])
        lines.append(
            f"| {r.get('persona')} | {expected} | {r.get('route_category')} | {_clip(r.get('query'))} | {_clip(r.get('answer_text'), 120)} |"
        )

    procedure_misses = [
        (r, key, coverage)
        for r in rows
        for key, coverage in (r.get("expected_procedure_anchor_coverage") or {}).items()
        if not coverage.get("cited_ok")
    ][:20]
    lines.extend([
        "",
        "## Expected Procedure Anchor Misses",
        "",
        "| persona | procedure | route | query | missing cited anchors |",
        "| --- | --- | --- | --- | --- |",
    ])
    for r, key, coverage in procedure_misses:
        missing = ", ".join(coverage.get("missing_cited") or [])
        lines.append(
            f"| {r.get('persona')} | {key} | {r.get('route_category')} | {_clip(r.get('query'))} | {_clip(missing, 180)} |"
        )
    if not procedure_misses:
        lines.append("| none | n/a | n/a | n/a | n/a |")

    report.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--api", default="http://localhost:8000")
    parser.add_argument("--queries-dir", type=Path, default=ROOT / "data" / "eval_500")
    parser.add_argument("--limit", type=int, default=100)
    parser.add_argument("--seed", type=int, default=20260525)
    parser.add_argument("--timeout-s", type=int, default=180)
    parser.add_argument("--out", type=Path, default=None)
    parser.add_argument("--report", type=Path, default=None)
    args = parser.parse_args()

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    out = args.out or ROOT / "data" / "processed" / f"timed_eval_100_{stamp}.jsonl"
    report = args.report or ROOT / "data" / "processed" / f"timed_eval_100_{stamp}.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    rows_in = load_eval_rows(args.queries_dir, limit=args.limit, seed=args.seed)
    if not rows_in:
        raise SystemExit(f"no eval rows found under {args.queries_dir}")

    print(f"=== timed eval: {len(rows_in)} queries -> {out} ===", flush=True)
    rows: list[dict[str, Any]] = []
    with out.open("w", encoding="utf-8") as f:
        for idx, eval_row in enumerate(rows_in, 1):
            observed = stream_answer(args.api, eval_row["query"], timeout_s=args.timeout_s)
            row = flatten_row(eval_row, observed)
            rows.append(row)
            f.write(jsonl_dumps(row) + "\n")
            f.flush()
            timing = row.get("timing") or {}
            outcome = "ERR" if row["error"] else "REF" if row["refused"] else row["relevance_verdict"] or "NO_REL"
            route_name = row.get("route_category") or "unknown"
            print(
                f"[{idx:03}/{len(rows_in)}] {outcome:<7} "
                f"{fmt_ms(timing.get('total_ms') or row.get('wall_ms')):>6} "
                f"retr={fmt_ms(timing.get('retrieval_ms')):>6} "
                f"llm={fmt_ms(timing.get('llm_stream_ms')):>6} "
                f"route={route_name:<26} "
                f"act_hit={row.get('expected_act_hit')} "
                f"cited={row.get('expected_act_cited_hit')} "
                f"q={row['query'][:70]!r}",
                flush=True,
            )

    write_report(rows, out, report)
    print(f"\nreport: {report}", flush=True)


if __name__ == "__main__":
    main()
