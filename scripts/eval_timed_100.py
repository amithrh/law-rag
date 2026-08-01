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
from types import SimpleNamespace
from typing import Any

from apps.api.source_gap import (
    is_active_plan_authority_entry as runtime_is_active_plan_authority_entry,
    missing_plan_authorities as runtime_missing_plan_authorities,
    _should_enforce_requirement as runtime_should_enforce_requirement,
    best_source_match as runtime_best_source_match,
    classify_required_source_requirement as runtime_classify_required_source_requirement,
)
from apps.api.runtime_identity import runtime_identity
from scripts.eval_source_gaps import route_required_source_gap_classifications
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
    "Arms Act": ("arms act", "arms-1959", "the arms act"),
    "MCOCA": ("mcoca", "maharashtra control of organised crime", "organised crime act", "organized crime act"),
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
    "EPF Act": ("epf", "epf-1952", "provident fund", "provident funds", "employees provident", "employees' provident"),
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
    "ASHA Incentives": ("asha incentive", "asha incentives", "asha honorarium", "national health mission asha", "national rural health mission", "nhm asha", "nrhm asha"),
    "Anganwadi Honorarium": ("anganwadi", "icds", "ameerbi", "maniben"),
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
    "AP Rights in Land and Pattadar Pass Books Act": ("andhra pradesh rights in land", "pattadar pass books", "pattadar passbooks"),
    "Andhra Pradesh Rights in Land and Pattadar Pass Books Act": ("andhra pradesh rights in land", "pattadar pass books", "pattadar passbooks"),
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
        "daain practices act", "dayan pratha", "dayan pratha pratishedh",
        "jharkhand dayan pratha", "jhalsa dayan pratha",
        "jhalsa-dayan-pratha-pratishedh-2001", "chhattisgarh tonahi",
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
        "customer liability", "rbi customer liability",
    ),
    "Municipal Law": (
        "municipal law", "municipalities act", "municipality act",
        "municipal corporation", "municipalities", "nagarpalika",
        "municipalities-1963", "municipal-corporations",
    ),
    "Credit Information Companies Act": (
        "credit information companies", "credit information companies regulation",
        "credit-information-companies-2005", "cibil",
    ),
    "IRDAI": ("irdai", "insurance regulatory", "insurance ombudsman", "insurance-ombudsman-rules-2017"),
    "FSSAI Act": ("fssai", "food safety"),
    "Passports Act": ("passports act", "passport act", "passports-1967", "passport-1967"),
    "Prevention of Corruption Act": ("prevention of corruption", "prevention-of-corruption", "pca 1988"),
    "Births and Deaths Act": ("registration of births and deaths",),
    "Drugs and Cosmetics Act": ("drugs and cosmetics",),
    "Clinical Establishments Act": ("clinical establishments",),
    "Prison Act": ("prison act", "prisons act", "prison rules", "model prison manual", "delhi prison rules", "delhi prisons rules", "delhi-prison-rules-2018", "prisons-1894"),
    "NHRC Act": (
        "nhrc", "human rights commission", "protection of human rights",
        "protection-human-rights-1993",
    ),
    "Public Gambling Act": ("public gambling", "public-gambling", "the public gambling act"),
    "State Pension Scheme": (
        "state pension scheme", "state pension", "pension rules", "widow pension", "old age pension",
        "indira gandhi national old age pension", "indira gandhi pension",
        "national old age pension", "national social assistance", "nsap",
        "ignwps", "ignoaps",
    ),
    "Army Pension Regulations": (
        "pension regulations for the army", "pension-regulations-army-2008",
        "army pension", "service pension", "family pension",
    ),
    "State Welfare Scheme": (
        "mukhyamantri", "kanya vivah",
    ),
    "State Excise Act": (
        "state prohibition act", "state prohibition", "state excise act",
        "state excise acts", "prohibition / excise", "bihar prohibition",
        "gujarat prohibition", "excise act", "excise acts",
    ),
    "Cattle Preservation Act": ("cattle preservation",),
    "Prevention of Cruelty to Animals Act": ("prevention of cruelty to animals", "pca act"),
    "Transport of Animals Rules": ("transport of animals rules", "animal-transport rules", "animal transport rules"),
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

FAMILY_PERSONAL_LAW_TRIGGER_TERMS = (
    "matrimonial", "annulment", "annul", "void marriage",
    "voidable", "divorce", "separation", "restitution", "conjugal",
    "second wife", "second husband", "second marriage", "bigamy", "maintenance",
    "alimony", "streedhan", "stridhan", "custody", "child custody",
    "guardianship", "personal law", "hindu marriage", "special marriage",
    "muslim marriage", "before marriage", "lied before marriage",
)

MAINTENANCE_TRIGGER_TERMS = (
    "maintenance", "alimony", "child support", "interim maintenance",
    "monthly support", "support order", "section 125", "sec 125",
    "125 crpc", "144 bnss", "not paying maintenance", "maintenance case",
)


def _has_adoption_source_context(q: str) -> bool:
    return (
        _has_any(q, ("adoption", "adopted", "adoptive", "cara", "relative adoption"))
        or re.search(r"(?<![a-z0-9])adopt(?:s|ing|er|ers)?(?![a-z0-9])", q) is not None
    )


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
        "suppressed": [],
        "refused": None,
        "error": None,
        "relevance": None,
        "coverage": None,
        "source_gap": None,
        "passages": [],
        "sources": [],
        "matter_route": None,
        "matter_plan": None,
        "workflow": None,
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
                elif event_name == "matter_plan":
                    out["matter_plan"] = data if isinstance(data, dict) else None
                elif event_name == "coverage":
                    out["coverage"] = data
                elif event_name == "source_gap":
                    out["source_gap"] = data if isinstance(data, dict) else None
                elif event_name == "passages":
                    out["passages"] = data if isinstance(data, list) else []
                elif event_name == "workflow":
                    out["workflow"] = data if isinstance(data, dict) else None
                elif event_name == "sentence":
                    out["sentences"].append(data)
                elif event_name == "suppressed":
                    out["suppressed_count"] += 1
                    if isinstance(data, dict):
                        out["suppressed"].append(data)
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


def fetch_runtime_health(api: str, *, timeout_s: int) -> dict[str, Any]:
    """Fetch the serving identity before an eval and fail on missing identity."""
    req = urllib.request.Request(
        f"{api.rstrip('/')}/healthz",
        headers={"Accept": "application/json"},
        method="GET",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout_s) as response:
            health = json.loads(response.read().decode("utf-8"))
    except Exception as exc:
        raise RuntimeError(f"could not read live API identity: {type(exc).__name__}: {exc}") from exc
    fingerprint = health.get("build_fingerprint")
    source = health.get("build_fingerprint_source")
    if (
        not isinstance(fingerprint, str)
        or not re.fullmatch(r"[0-9a-f]{64}", fingerprint)
        or source not in {"git_worktree", "environment_verified"}
    ):
        raise RuntimeError("live API does not expose build_fingerprint; refusing benchmark")
    return health


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
    if "ASHA Incentives" in keys and "State Welfare Scheme" in keys:
        keys.remove("State Welfare Scheme")
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
    elif "IPC" in out and "BNS" not in out:
        user_explicitly_asked_ipc = re.search(r"\bipc\b|indian penal", query) is not None
        if not user_explicitly_asked_ipc and not _has_legacy_criminal_date_context(query):
            out.remove("IPC")
            out.append("BNS")
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
    if "Shops and Establishments Act" in out and not _has_india_state_or_ut_context(query):
        out.remove("Shops and Establishments Act")
    if "Municipal Law" in out and not _has_india_state_or_ut_context(query):
        out.remove("Municipal Law")
    if "SC/ST POA Act" in out and not _has_scst_protected_context(query):
        out.remove("SC/ST POA Act")
    if "State Pension Scheme" in out:
        if _has_army_service_pension_context(query):
            out.remove("State Pension Scheme")
            if "Army Pension Regulations" not in out:
                out.append("Army Pension Regulations")
        elif not _has_specific_pension_scheme_context(query):
            out.remove("State Pension Scheme")
    if "Aadhaar Act" in out and _is_welfare_aadhaar_hint_overbroad(hint, query):
        out.remove("Aadhaar Act")
    if _is_bank_freeze_hint_overbroad(hint, query):
        for key in ("BNSS", "Information Technology Act"):
            if key in out:
                out.remove(key)
        for key in ("Banking Ombudsman", "Banking Regulation Act"):
            if key not in out:
                out.append(key)
    if _is_conditional_ni_act_hint_overbroad(hint, query):
        if "NI Act" in out:
            out.remove("NI Act")
    if _is_municipal_article226_hint_overbroad(hint, query):
        if "Constitution" in out:
            out.remove("Constitution")
        if "Municipal Law" not in out:
            out.append("Municipal Law")
    if "Municipal Law" in out and not _has_india_state_or_ut_context(query):
        out.remove("Municipal Law")
    if _is_identity_misuse_hint_overbroad(hint, query):
        if _has_sim_identity_context(query):
            if "Credit Information Companies Act" in out:
                out.remove("Credit Information Companies Act")
            if "Telecommunications Act" not in out:
                out.append("Telecommunications Act")
        elif _has_nbfc_signature_context(query):
            for key in ("Aadhaar Act", "Information Technology Act"):
                if key in out:
                    out.remove(key)
            if "Banking Ombudsman" not in out:
                out.append("Banking Ombudsman")
    if _is_pf_hint_overbroad(hint, query):
        if "Code on Wages" in out:
            out.remove("Code on Wages")
    if _is_banking_regulation_hint_overbroad(hint, query):
        if "Banking Regulation Act" in out:
            out.remove("Banking Regulation Act")
    if _is_scst_bns_hint_overbroad(hint, query):
        if "BNS" in out:
            out.remove("BNS")
        if "IPC" in out:
            out.remove("IPC")
    if _is_conditional_bns_offence_hint_overbroad(hint, query):
        if "BNS" in out:
            out.remove("BNS")
        if "IPC" in out:
            out.remove("IPC")
    if _is_male_domestic_family_court_hint_overbroad(hint, query):
        if "Family Courts Act" in out:
            out.remove("Family Courts Act")
    if _is_generic_tribal_land_hint_overbroad(hint, query):
        for key in ("Scheduled Areas Land Transfer Regulation", "PESA"):
            if key in out:
                out.remove(key)
        if "Constitution" not in out:
            out.append("Constitution")
    if _is_scheduled_area_land_hint_overbroad(hint, query):
        if "Scheduled Areas Land Transfer Regulation" in out:
            out.remove("Scheduled Areas Land Transfer Regulation")
        for key in ("Constitution", "PESA"):
            if key not in out:
                out.append(key)
    if _is_jharkhand_tribal_land_hint_overbroad(hint, query):
        for key in ("Constitution", "PESA"):
            if key in out:
                out.remove(key)
        if "Scheduled Areas Land Transfer Regulation" not in out:
            out.append("Scheduled Areas Land Transfer Regulation")
    if "State Excise Act" in out and not _has_state_excise_jurisdiction_context(query):
        out.remove("State Excise Act")
    if (
        "Cattle Preservation Act" in out
        and "Prevention of Cruelty to Animals Act" in out
        and not _has_india_state_or_ut_context(query)
    ):
        out.remove("Cattle Preservation Act")
    if "Right to Education Act" in out and _has_education_loan_context(query):
        out.remove("Right to Education Act")
        if "Banking Ombudsman" not in out:
            out.append("Banking Ombudsman")
    if (
        "POSH Act" in out
        and "where sexual harassment facts exist" in hint
        and not _has_explicit_posh_context(query)
    ):
        out.remove("POSH Act")
    return sorted(set(out))


def _is_bank_freeze_hint_overbroad(hint: str, query: str) -> bool:
    has_bank_ombudsman = "banking ombudsman" in hint or "rbi ombudsman" in hint
    if not (has_bank_ombudsman and "bnss" in hint and ("information technology" in hint or "it act" in hint or "cyber" in hint)):
        return False
    q = query.lower()
    freeze = any(term in q for term in ("account frozen", "account is frozen", "upi account frozen", "bank account is frozen", "blocked", "lien"))
    legal_hold = any(term in q for term in ("police", "thana", "cyber", "court", "ed", "legal hold", "fraud complaint", "fir"))
    return freeze and not legal_hold


def _is_conditional_bns_offence_hint_overbroad(hint: str, query: str) -> bool:
    if not any(term in hint for term in (
        "where alleged", "where threat", "where hurt", "where detention",
        "where relevant", "if threat", "if hurt",
    )):
        return False
    q = query.lower()
    offence_facts = (
        "threat", "threaten", "threatening", "hurt", "hit", "slap", "slapped",
        "assault", "violence", "injury", "injured", "beat", "beaten",
        "detain", "detained", "picked", "picking", "wrongful restraint",
        "wrongful confinement", "intimidation", "theft", "stolen", "cheating",
        "forgery", "fraud",
    )
    return not any(term in q for term in offence_facts)


def _is_conditional_ni_act_hint_overbroad(hint: str, query: str) -> bool:
    if "ni act" not in hint and "negotiable instruments" not in hint:
        return False
    if "if cheque" not in hint and "where cheque" not in hint and "if a cheque" not in hint:
        return False
    q = query.lower()
    return not any(term in q for term in ("cheque", "check bounce", "dishonour", "dishonor", "return memo", "138"))


def _is_municipal_article226_hint_overbroad(hint: str, query: str) -> bool:
    if "article 226" not in hint:
        return False
    if "municipal" not in hint and "municipality" not in hint and "shop" not in hint:
        return False
    q = query.lower()
    municipal_shop = any(term in q for term in ("municipality", "municipal", "nagarpalika", "corporation")) and any(
        term in q for term in ("shop", "sealed", "seal", "licence", "license")
    )
    high_court_context = any(term in q for term in ("high court", "writ", "article 226", "constitutional"))
    return municipal_shop and not high_court_context


def _is_identity_misuse_hint_overbroad(hint: str, query: str) -> bool:
    return (
        "aadhaar act" in hint
        and "credit information" in hint
        and ("information technology" in hint or "it act" in hint)
        and (_has_sim_identity_context(query) or _has_nbfc_signature_context(query))
    )


def _has_sim_identity_context(query: str) -> bool:
    q = query.lower()
    return any(term in q for term in ("sim", "mobile subscriber", "telecom", "phone number")) and any(term in q for term in ("aadhaar", "aadhar", "kyc", "fraud case"))


def _has_nbfc_signature_context(query: str) -> bool:
    q = query.lower()
    return any(term in q for term in ("nbfc", "loan showing", "finance company", "lender", "cibil")) and any(
        term in q
        for term in ("signature not mine", "not my signature", "did not sign", "didn't sign", "never signed", "documents")
    )


def _is_pf_hint_overbroad(hint: str, query: str) -> bool:
    if not ("epf" in hint or "provident" in hint):
        return False
    if "code on wages" not in hint:
        return False
    q = query.lower()
    pf_context = any(term in q for term in ("pf", "epf", "epfo", "provident fund", "uan", "passbook"))
    wage_only_context = any(term in q for term in ("minimum wage", "salary unpaid", "unpaid salary", "full and final"))
    return pf_context and not wage_only_context


def _is_banking_regulation_hint_overbroad(hint: str, query: str) -> bool:
    if "banking regulation" not in hint:
        return False
    q = query.lower()
    wrong_debit = any(term in q for term in ("wrong debit", "deducted money wrongly", "failed atm", "failed transaction", "customer care", "closing ticket"))
    restructuring = any(term in q for term in ("restructuring", "emi bounced", "emi bounce", "need restructuring"))
    return wrong_debit or restructuring


def _is_scst_bns_hint_overbroad(hint: str, query: str) -> bool:
    if "sc/st" not in hint and "scheduled castes" not in hint and "poa" not in hint:
        return False
    if "bns" not in hint and "ipc" not in hint:
        return False
    q = query.lower()
    caste_abuse = any(term in q for term in ("caste name", "chamar", "dalit", "sc/st", "scheduled caste", "scheduled tribe"))
    physical_crime = any(term in q for term in ("beat", "hit", "assault", "injury", "threaten", "threatened", "burn", "rape", "kill"))
    return caste_abuse and not physical_crime


def _is_male_domestic_family_court_hint_overbroad(hint: str, query: str) -> bool:
    if "family courts" not in hint:
        return False
    q = query.lower()
    male_victim = any(term in q for term in ("wife is beating", "wife beating", "wife beat", "wife hit", "wife slapped", "false dowry"))
    immediate_safety = any(term in q for term in ("safety", "complaint path", "not divorce", "police", "beating", "threatening"))
    return male_victim and immediate_safety


def _is_scheduled_area_land_hint_overbroad(hint: str, query: str) -> bool:
    has_scheduled_land_hint = "scheduled areas land transfer" in hint
    has_national_anchor = "pesa" in hint or "constitution" in hint or "schedule v" in hint or "fifth schedule" in hint
    if not (has_scheduled_land_hint and has_national_anchor):
        return False
    q = query.lower()
    if "non scheduled" in q or "non-scheduled" in q:
        return False
    if _has_jharkhand_tribal_land_context(q):
        return False
    return any(term in q for term in ("scheduled area", "agency area", "agency village"))


def _is_generic_tribal_land_hint_overbroad(hint: str, query: str) -> bool:
    has_scheduled_land_hint = "scheduled areas land transfer" in hint
    has_national_anchor = "pesa" in hint or "constitution" in hint or "schedule v" in hint or "fifth schedule" in hint
    if not (has_scheduled_land_hint and has_national_anchor):
        return False
    q = query.lower()
    non_scheduled = "non scheduled" in q or "non-scheduled" in q
    tribal = any(term in q for term in ("tribal", "adivasi", "scheduled tribe", "st land", "munda", "santhal"))
    land = any(term in q for term in ("land", "plot", "khata", "khatian", "mutation", "property"))
    transfer = any(term in q for term in (
        "transfer", "transferred", "sold", "sale deed", "moneylender", "sahukar",
        "mortgage", "blank paper", "thumb impression", "mutation", "grabbed",
    ))
    specific_state_or_area = (
        _has_india_state_or_ut_context(q)
        or _has_jharkhand_tribal_land_context(q)
        or (any(term in q for term in ("scheduled area", "agency area", "agency village", "gram sabha", "pesa", "fifth schedule", "article 244")) and not non_scheduled)
    )
    return tribal and land and transfer and not specific_state_or_area


def _is_jharkhand_tribal_land_hint_overbroad(hint: str, query: str) -> bool:
    has_scheduled_land_hint = "scheduled areas land transfer" in hint
    has_national_anchor = "pesa" in hint or "constitution" in hint or "schedule v" in hint or "fifth schedule" in hint
    if not (has_scheduled_land_hint and has_national_anchor):
        return False
    q = query.lower()
    non_scheduled = "non scheduled" in q or "non-scheduled" in q
    scheduled_area_context = any(
        term in q
        for term in ("scheduled area", "agency area", "agency village", "fifth schedule", "article 244")
    ) and not non_scheduled
    return _has_jharkhand_tribal_land_context(q) and not scheduled_area_context


def _has_jharkhand_tribal_land_context(text: str) -> bool:
    return any(
        term in text
        for term in (
            "jharkhand", "cnt", "spt", "chota nagpur", "chotanagpur",
            "santhal", "ranchi", "khunti", "chaibasa", "latehar",
            "gumla", "dumka", "simdega", "lohardaga", "singhbhum",
            "palamu", "hazaribagh",
        )
    )


def _has_explicit_posh_context(text: str) -> bool:
    q = text.lower()
    return any(
        term in q
        for term in (
            "posh", "sexual harassment", "sexually harassed", "sexual",
            "icc", "internal committee", "local committee", "vishaka",
            "boss touched", "manager touched", "touched me", "inappropriate touch",
            "asked for sex", "favours", "favor", "quid pro quo",
        )
    )


def _has_scst_protected_context(text: str) -> bool:
    return bool(re.search(r"\b(?:sc|st)\b", text)) or any(
        term in text
        for term in (
            "dalit", "scheduled caste", "scheduled tribe", "sc/st", "sc st",
            "adivasi", "tribal", "untouchable", "chamar", "caste name",
            "munda", "sarna", "pahan",
            "poa act", "scst act", "sc/st act", "atrocity case",
            "atrocities act", "prevention of atrocities",
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
        if key in {"ASHA Incentives", "Anganwadi Honorarium"}:
            aliases = ACT_ALIASES.get(key, (key.lower(),))
            hits[key] = any(
                _alias_in_text(alias, _item_blob(item))
                and _is_welfare_authority_source_item(key, item)
                for alias in aliases
                for item in items
            )
            continue
        if key == "Witch-Hunting State Acts":
            aliases = ACT_ALIASES.get(key, (key.lower(),))
            hits[key] = any(
                _alias_in_text(alias, _item_blob(item))
                and _is_witch_hunting_state_source_item(item)
                for alias in aliases
                for item in items
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
    text = (
        str(item.get("title", ""))
        + " "
        + str(item.get("anchor", ""))
        + " "
        + str(item.get("citation", ""))
        + " "
        + str(item.get("statute_short", ""))
    ).lower()
    dehyphenated = text.replace("-", " ")
    return f"{text} {dehyphenated}" if dehyphenated != text else text


def _is_statutory_source_item(item: dict[str, Any]) -> bool:
    source_type = str(item.get("source_type") or "").lower()
    if source_type == "bare_act":
        return True
    if source_type in {"guideline", "circular", "notification", "scheme", "rule", "regulation"}:
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


def _is_witch_hunting_state_source_item(item: dict[str, Any]) -> bool:
    source_type = str(item.get("source_type") or "").lower()
    if source_type not in {"bare_act", "official_guidance"}:
        return False
    if _is_judgment_source(item):
        return False
    blob = _item_blob(item)
    state_marker = any(
        marker in blob
        for marker in (
            "assam", "jharkhand", "chhattisgarh", "chattisgarh",
            "jhalsa", "dayan pratha", "tonahi",
        )
    )
    witch_marker = any(
        marker in blob
        for marker in (
            "witch", "daain", "dayan", "daayan", "tonahi", "tonhi",
            "pratishedh", "pratadna",
        )
    )
    return state_marker and witch_marker


def _is_welfare_authority_source_item(key: str, item: dict[str, Any]) -> bool:
    blob = _item_blob(item)
    source_type = str(item.get("source_type") or "").lower()
    if key == "ASHA Incentives":
        return (
            "asha" in blob
            and (
                "national health mission" in blob
                or "national rural health mission" in blob
                or "nhm" in blob
                or "nrhm" in blob
            )
            and source_type not in {"hc_judgment", "sc_judgment"}
        )
    if key == "Anganwadi Honorarium":
        return (
            "anganwadi" in blob
            or "icds" in blob
            or "ameerbi" in blob
            or "maniben" in blob
        )
    return _is_statutory_source_item(item)


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


def _is_welfare_aadhaar_hint_overbroad(hint: str, query: str) -> bool:
    welfare_hint = any(term in hint for term in ("pension", "ration", "pds", "food security", "welfare"))
    welfare_query = any(term in query for term in ("pension", "ration", "pds", "foodgrain", "food grain", "widow", "disability pension"))
    aadhaar_fact = any(term in query for term in (
        "aadhaar", "aadhar", "uidai", "biometric", "fingerprint",
        "authentication", "kyc", "linked", "linking", "dbt",
        "mismatch", "identity", "id proof",
    ))
    return welfare_hint and welfare_query and not aadhaar_fact


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


def _ordered_cited_source_indices(sentences: list[dict[str, Any]]) -> list[int]:
    ordered: list[int] = []
    for sentence in sentences:
        if not isinstance(sentence, dict):
            continue
        text = str(sentence.get("text") or "")
        for match in re.finditer(r"\[(\d{1,3})\]", text):
            ordered.append(int(match.group(1)))
    return ordered


def cited_source_order_metrics(
    sources: list[dict[str, Any]],
    passages: list[dict[str, Any]],
    sentences: list[dict[str, Any]],
) -> dict[str, Any]:
    by_index: dict[int, dict[str, Any]] = {}
    for item in [*(sources or []), *(passages or [])]:
        if not isinstance(item, dict):
            continue
        idx = item.get("index")
        if isinstance(idx, int) and idx not in by_index:
            by_index[idx] = item

    first_cited: dict[str, Any] | None = None
    first_actionable_pos: int | None = None
    first_judgment_pos: int | None = None
    for pos, idx in enumerate(_ordered_cited_source_indices(sentences)):
        source = by_index.get(idx)
        if not source:
            continue
        if first_cited is None:
            first_cited = source
        if first_actionable_pos is None and _is_actionable_source(source):
            first_actionable_pos = pos
        if first_judgment_pos is None and _is_judgment_source(source):
            first_judgment_pos = pos

    first_type = str(first_cited.get("source_type") or "") if first_cited else None
    first_title = str(first_cited.get("title") or "") if first_cited else None
    judgment_before_actionable = (
        first_judgment_pos is not None
        and (first_actionable_pos is None or first_judgment_pos < first_actionable_pos)
    )
    return {
        "first_cited_source_type": first_type,
        "first_cited_source_title": first_title,
        "first_cited_is_actionable": _is_actionable_source(first_cited) if first_cited else None,
        "first_actionable_citation_position": first_actionable_pos,
        "first_judgment_citation_position": first_judgment_pos,
        "judgment_before_actionable_source": judgment_before_actionable,
    }


def _is_actionable_source(source: dict[str, Any] | None) -> bool:
    if not source:
        return False
    source_type = str(source.get("source_type") or "").lower()
    title = str(source.get("title") or "").lower()
    anchor = str(source.get("anchor") or "").lower()
    if any(term in title for term in ("anganwadi", "ameerbi", "maniben")):
        return True
    if source_type in {"bare_act", "rule", "regulation", "scheme", "guideline", "circular", "notification"}:
        return True
    if _is_judgment_source(source):
        return False
    return bool(
        anchor.startswith("constitution-india")
        or "/sec-" in anchor
        or "#sec-" in anchor
        or re.search(r"\b(act|code|rules|scheme|guideline|notification|circular)\b", title)
        or any(term in title for term in ("sanhita", "adhiniyam"))
    )


def _is_judgment_source(source: dict[str, Any] | None) -> bool:
    if not source:
        return False
    source_type = str(source.get("source_type") or "").lower()
    title = str(source.get("title") or "").lower()
    anchor = str(source.get("anchor") or "").lower()
    return (
        source_type.endswith("judgment")
        or anchor.startswith("hc/")
        or bool(re.match(r"^\d{4}-(?:insc|\d+-\d+)", anchor))
        or " versus " in title
        or " vs " in title
        or " v. " in title
    )


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
    if row.get("source_gap_outcome") == "source_gap_handoff":
        flags.append("source_gap_handoff")
    if row.get("source_gap_visible"):
        flags.append("visible_source_gap")
    if not answer_text and not row.get("refused") and not row.get("error"):
        flags.append("empty_answer")
    if row.get("expected_act_cited_hit") is False:
        flags.append("expected_act_not_cited")
    if row.get("route_required_sources_cited_missing"):
        flags.append("route_required_source_not_cited")
    if row.get("plan_authority_ids_missing"):
        flags.append("matter_plan_authority_not_retrieved")
    if row.get("plan_authority_ids_uncited"):
        flags.append("matter_plan_authority_not_cited")
    if matter_plan_applicable_for_eval(row) and not (row.get("matter_plan_contract") or {}).get("valid"):
        flags.append("missing_or_invalid_matter_plan")
    if row.get("judgment_before_actionable_source"):
        flags.append("judgment_before_actionable_source")
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
        if int(row.get("unknown_citation_count") or 0) > 0:
            flags.append("unknown_citation_indices")
        weak_count = int(row.get("weak_sentences") or 0)
        has_meaningful_weak_support = (
            weak_count >= 2
            and int(row.get("suppressed_count") or 0) == 0
            and str(row.get("relevance_verdict") or "").lower() == "ok"
            and row.get("first_cited_is_actionable") is not False
            and row.get("expected_act_cited_hit") is not False
        )
        if int(row.get("ok_sentences") or 0) == 0 and not has_meaningful_weak_support:
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


_INTERNAL_SERVICE_GAP_REASONS = frozenset(
    {
        "answer_preparation_error",
        "answer_retrieval_error",
        "answer_stream_error",
        "llm_unavailable",
        "rerank_unavailable",
    }
)


def internal_service_error_reason(row: dict[str, Any]) -> str | None:
    """Expose operational failures even when the API safely hands off.

    The public API intentionally emits a sanitized source-gap handoff instead
    of an internal exception. The evaluator must retain that safety contract
    while distinguishing a corpus/source gap from a serving failure.
    """
    reason = str(row.get("source_gap_reason") or "").strip()
    return reason if reason in _INTERNAL_SERVICE_GAP_REASONS else None


def _uses_criminal_code_framing(text: str) -> bool:
    return any(
        term in text
        for term in (
            "bns", "bnss", "bharatiya nyaya sanhita", "bharatiya nagarik suraksha",
            "ipc", "crpc", "indian penal code", "code of criminal procedure",
        )
    )


def flatten_row(
    eval_row: dict[str, Any],
    observed: dict[str, Any],
    *,
    runtime: dict[str, Any] | None = None,
) -> dict[str, Any]:
    route = observed.get("matter_route") or {}
    plan = observed.get("matter_plan") or {}
    workflow = observed.get("workflow") or {}
    timing = observed.get("timing") or {}
    relevance = observed.get("relevance") or {}
    refused = observed.get("refused")
    error = observed.get("error")
    expected_keys = [str(item) for item in (eval_row.get("expected_act_keys") or []) if str(item).strip()]
    if not expected_keys:
        expected_keys = expected_act_keys(eval_row.get("expected_act_hint"), eval_row.get("query"))
    hit = expected_act_hit(expected_keys, observed.get("sources") or [], observed.get("passages") or [])
    sentences = observed.get("sentences") or []
    cited_hit = expected_act_cited_hit(
        expected_keys,
        observed.get("sources") or [],
        [],
        sentences,
    )
    procedure_anchor_coverage = expected_procedure_anchor_coverage(
        expected_keys,
        observed.get("sources") or [],
        [],
        sentences,
    )
    source_order = cited_source_order_metrics(
        observed.get("sources") or [],
        [],
        sentences,
    )
    citation_integrity = citation_integrity_metrics(
        observed.get("sources") or [],
        [],
        sentences,
    )
    plan_authority_sources = [
        str(item.get("source"))
        for item in (plan.get("authority_ledger") or [])
        if isinstance(item, dict) and item.get("source")
    ]
    route_required_sources = route.get("required_sources") or []
    route_required_source_coverage = required_source_coverage(
        route_required_sources,
        observed.get("sources") or [],
        observed.get("passages") or [],
        query=str(eval_row.get("query") or ""),
    )
    retrieved_source_records = [
        s
        for s in [*(observed.get("sources") or []), *(observed.get("passages") or [])]
        if isinstance(s, dict)
    ]
    retrieved_sources = [
        compact_source_item(s)
        for s in retrieved_source_records
    ]
    cited_source_records = cited_source_records_for_sentences(
        observed.get("sources") or [],
        [],
        sentences,
    )
    cited_sources = [compact_source_item(item) for item in cited_source_records]
    plan_authority_retrieval_coverage = matter_plan_authority_coverage(
        plan,
        retrieved_source_records,
        query=str(eval_row.get("query") or ""),
    )
    plan_authority_cited_coverage = matter_plan_authority_coverage(
        plan,
        cited_source_records,
        query=str(eval_row.get("query") or ""),
    )
    route_required_source_cited_coverage = required_source_coverage(
        route_required_sources,
        cited_sources,
        [],
        query=str(eval_row.get("query") or ""),
    )
    action_pack = route.get("action_pack") or {}
    row = {
        "runtime_fingerprint": runtime.get("build_fingerprint") if runtime else None,
        "runtime_fingerprint_source": runtime.get("build_fingerprint_source") if runtime else None,
        "query": eval_row.get("query"),
        "persona": eval_row.get("persona"),
        "product_priority": eval_row.get("product_priority"),
        "eval_family": (
            eval_row.get("family")
            or eval_row.get("issue_family")
            or eval_row.get("category_family")
            or eval_row.get("expected_family")
        ),
        "expected_route_category": eval_row.get("expected_route_category"),
        "expected_route_label": eval_row.get("expected_route_label"),
        "expected_answer_owner": eval_row.get("expected_answer_owner"),
        "expected_answer_mode": eval_row.get("expected_answer_mode"),
        "source_gap_policy": eval_row.get("source_gap_policy"),
        "expected_source_gap_policy": eval_row.get("expected_source_gap_policy"),
        "expected_controlling_source_any": eval_row.get("expected_controlling_source_any") or [],
        "expected_forum_any": eval_row.get("expected_forum_any") or [],
        "expected_user_role": eval_row.get("expected_user_role"),
        "expected_category": eval_row.get("expected_category"),
        "expected_act_hint": eval_row.get("expected_act_hint"),
        "expected_primary_act_any": eval_row.get("expected_primary_act_any") or [],
        "expected_act_keys": expected_keys,
        "expected_act_hit": hit,
        "expected_act_cited_hit": cited_hit,
        "expected_procedure_anchor_coverage": procedure_anchor_coverage,
        **source_order,
        "is_accused_subject": bool(eval_row.get("is_accused_subject")),
        "route_category": route.get("category"),
        "route_label": route.get("label"),
        "route_urgency": route.get("urgency"),
        "route_confidence": route.get("confidence"),
        "legal_regime": route.get("legal_regime"),
        "route_required_sources": route_required_sources,
        "route_forums": route.get("forums") or [],
        "route_missing_facts": route.get("missing_facts") or [],
        "action_pack_id": action_pack.get("id") if action_pack else None,
        "action_pack_cautions": action_pack.get("cautions") or [],
        "action_pack_next_steps": action_pack.get("next_steps") or [],
        "red_flags": route.get("red_flags") or [],
        "matter_plan": plan,
        "matter_plan_required": matter_plan_required_for_eval(eval_row, route),
        "matter_plan_contract": matter_plan_contract_status(plan),
        "plan_primary_issue": plan.get("primary_issue"),
        "plan_primary_label": plan.get("primary_label"),
        "plan_confidence": plan.get("confidence"),
        "plan_urgency": plan.get("urgency"),
        "plan_legal_regime": plan.get("legal_regime"),
        "plan_secondary_issues": plan.get("secondary_issues") or [],
        "plan_user_role": plan.get("user_role"),
        "plan_desired_outcome": plan.get("desired_outcome"),
        "plan_safety_flags": plan.get("safety_flags") or [],
        "plan_required_sources": plan_authority_sources,
        "plan_forums": plan.get("forums") or [],
        "plan_required_facts": plan.get("required_facts") or [],
        "plan_action_pack_id": plan.get("action_pack_id"),
        "plan_action_pack_cautions": plan.get("cautions") or [],
        "plan_action_pack_next_steps": plan.get("next_steps") or [],
        "workflow": workflow,
        "workflow_id": workflow.get("id"),
        "workflow_source": workflow.get("source"),
        "workflow_selected": workflow.get("selected"),
        "workflow_answer_owner": workflow.get("answer_owner"),
        "workflow_answer_mode": workflow.get("answer_mode"),
        "workflow_contract_miss_reason": workflow.get("contract_miss_reason"),
        "workflow_line_count": workflow.get("line_count"),
        "workflow_shadowed_by_legacy": workflow.get("workflow_shadowed_by_legacy"),
        "shadowed_workflow_id": workflow.get("shadowed_workflow_id"),
        "shadowed_workflow_source": workflow.get("shadowed_workflow_source"),
        "shadowed_workflow_answer_mode": workflow.get("shadowed_workflow_answer_mode"),
        "workflow_required_sources": workflow.get("required_sources") or [],
        "workflow_source_indices": workflow.get("source_indices") or {},
        "source_gap_event": observed.get("source_gap"),
        "source_gap_visible": bool((observed.get("source_gap") or {}).get("has_gap")),
        "source_gap_missing_required_sources": [
            item.get("required_source")
            for item in ((observed.get("source_gap") or {}).get("missing_required_sources") or [])
            if isinstance(item, dict) and item.get("required_source")
        ],
        "source_gap_kinds": (observed.get("source_gap") or {}).get("gap_kinds") or [],
        "source_gap_handoff": (observed.get("source_gap") or {}).get("handoff"),
        "source_gap_outcome": (observed.get("source_gap") or {}).get("outcome"),
        "source_gap_reason": (observed.get("source_gap") or {}).get("reason"),
        "source_gap_safe_handoff_only": bool(
            (observed.get("source_gap") or {}).get("safe_handoff_only")
        ),
        "source_gap_policy": (observed.get("source_gap") or {}).get("policy") or eval_row.get("source_gap_policy"),
        "refused": bool(refused),
        "refused_reason": refused.get("reason") if isinstance(refused, dict) else None,
        "error": error.get("message") if isinstance(error, dict) else error,
        "relevance_verdict": relevance.get("verdict"),
        "relevance_score": relevance.get("score"),
        "sentence_count": len(sentences),
        "ok_sentences": sum(1 for s in sentences if s.get("status") == "ok"),
        "weak_sentences": sum(1 for s in sentences if s.get("status") == "weak_support"),
        "suppressed_count": observed.get("suppressed_count", 0),
        "suppressed": observed.get("suppressed") or [],
        "suppressed_status_counts": dict(Counter(
            str(item.get("status") or "unknown")
            for item in (observed.get("suppressed") or [])
            if isinstance(item, dict)
        )),
        **citation_integrity,
        "answer_text": " ".join(str(s.get("text") or "") for s in sentences if isinstance(s, dict))[:4000],
        "source_count": len(observed.get("sources") or []),
        "top_sources": [
            compact_source_item(s)
            for s in (observed.get("sources") or observed.get("passages") or [])[:5]
            if isinstance(s, dict)
        ],
        "retrieved_sources": retrieved_sources,
        "cited_sources": cited_sources,
        "plan_authority_retrieval_coverage": plan_authority_retrieval_coverage,
        "plan_authority_ids_required": plan_authority_retrieval_coverage["required_ids"],
        "plan_authority_ids_retrieved": plan_authority_retrieval_coverage["found_ids"],
        "plan_authority_ids_missing": plan_authority_retrieval_coverage["missing_ids"],
        "plan_authority_cited_coverage": plan_authority_cited_coverage,
        "plan_authority_ids_cited": plan_authority_cited_coverage["found_ids"],
        "plan_authority_ids_uncited": plan_authority_cited_coverage["missing_ids"],
        "route_required_source_coverage": route_required_source_coverage,
        "route_required_sources_found": [
            item["required_source"]
            for item in route_required_source_coverage
            if item.get("found") is True
        ],
        "route_required_sources_missing": [
            item["required_source"]
            for item in route_required_source_coverage
            if item.get("found") is False
        ],
        "route_required_source_cited_coverage": route_required_source_cited_coverage,
        "route_required_sources_cited_found": [
            item["required_source"]
            for item in route_required_source_cited_coverage
            if item.get("found") is True
        ],
        "route_required_sources_cited_missing": [
            item["required_source"]
            for item in route_required_source_cited_coverage
            if item.get("found") is False
        ],
        "route_required_sources_cited_skipped": [
            item["required_source"]
            for item in route_required_source_cited_coverage
            if item.get("skipped")
        ],
        "route_required_sources_skipped": [
            item["required_source"]
            for item in route_required_source_coverage
            if item.get("skipped")
        ],
        "timing": timing,
        "wall_ms": observed.get("wall_ms"),
        "events": observed.get("events"),
    }
    row["route_required_source_gap_classifications"] = route_required_source_gap_classifications(row)
    row["route_required_source_gap_kinds"] = [
        item["kind"] for item in row["route_required_source_gap_classifications"]
    ]
    row["internal_service_error"] = internal_service_error_reason(row)
    row["matter_plan_applicable"] = bool(
        row["matter_plan_required"] and not safe_source_gap_handoff_for_eval(row)
    )
    row["answer_quality_flags"] = answer_quality_flags(row)
    row["legal_safety"] = analyze_safety_row(row)
    return row


def compact_source_item(source: dict[str, Any]) -> dict[str, Any]:
    return {
        "index": source.get("index"),
        "title": source.get("title"),
        "anchor": source.get("anchor"),
        "court": source.get("court"),
        "citation": source.get("citation"),
        "source_type": source.get("source_type"),
        "document_id": source.get("document_id"),
        "provenance_verified": source.get("provenance_verified") is True,
        "statute_short": source.get("statute_short"),
        "heading": source.get("heading"),
        "required_source_pack": source.get("required_source_pack"),
        "as_at": source.get("as_at"),
        "authority_ids": [
            str(authority_id)
            for authority_id in (source.get("authority_ids") or [])
            if authority_id
        ],
    }


def matter_plan_contract_status(plan: dict[str, Any]) -> dict[str, Any]:
    errors: list[str] = []
    if plan.get("schema_version") != 2:
        errors.append("schema_version_not_2")
    if not str(plan.get("plan_id") or "").startswith("matter_plan_v2_"):
        errors.append("invalid_plan_id")
    for field in (
        "primary_issue",
        "primary_label",
        "user_role",
        "incident_date_status",
        "case_stage",
        "desired_outcome",
    ):
        if not isinstance(plan.get(field), str) or not str(plan.get(field)).strip():
            errors.append(f"invalid_{field}")
    confidence = plan.get("confidence")
    if isinstance(confidence, bool) or not isinstance(confidence, (int, float)):
        errors.append("invalid_confidence")
    if plan.get("urgency") not in {"low", "medium", "high", "emergency"}:
        errors.append("invalid_urgency")
    for field in ("legal_regime", "action_pack_id", "action_pack_title"):
        value = plan.get(field)
        if value is not None and not isinstance(value, str):
            errors.append(f"invalid_{field}")
    for field in (
        "secondary_issues",
        "required_facts",
        "forums",
        "remedies",
        "deadlines",
        "documents",
        "next_steps",
        "portals",
        "escalation",
        "cautions",
        "safety_flags",
    ):
        if not _is_string_list(plan.get(field)):
            errors.append(f"invalid_{field}")

    jurisdiction = plan.get("jurisdiction")
    if not isinstance(jurisdiction, dict):
        errors.append("invalid_jurisdiction")
    else:
        for field in ("state", "city", "forum_mentioned"):
            value = jurisdiction.get(field)
            if value is not None and not isinstance(value, str):
                errors.append(f"invalid_jurisdiction_{field}")
        if not isinstance(jurisdiction.get("needs_state"), bool):
            errors.append("invalid_jurisdiction_needs_state")

    answer_policy = plan.get("answer_policy")
    if not isinstance(answer_policy, dict):
        errors.append("invalid_answer_policy")
    else:
        for field in ("required_primary_owner", "fallback_owner"):
            if not isinstance(answer_policy.get(field), str) or not str(answer_policy.get(field)).strip():
                errors.append(f"invalid_answer_policy_{field}")
        for field in ("allow_freeform_llm", "requires_reviewed_contract"):
            if not isinstance(answer_policy.get(field), bool):
                errors.append(f"invalid_answer_policy_{field}")

    authority_ledger = plan.get("authority_ledger")
    if not isinstance(authority_ledger, list):
        errors.append("invalid_authority_ledger")
    else:
        if not authority_ledger:
            errors.append("empty_authority_ledger")
        for index, entry in enumerate(authority_ledger):
            if not _valid_authority_ledger_entry(entry):
                errors.append(f"invalid_authority_ledger_entry_{index}")
        if not any(_is_enforceable_plan_obligation(entry) for entry in authority_ledger):
            errors.append("missing_enforceable_authority_obligation")

    retrieval_sources = plan.get("retrieval_sources")
    if not isinstance(retrieval_sources, list):
        errors.append("invalid_retrieval_sources")
    else:
        if not retrieval_sources:
            errors.append("empty_retrieval_sources")
        for index, source in enumerate(retrieval_sources):
            if not _valid_retrieval_source(source):
                errors.append(f"invalid_retrieval_source_{index}")
    return {"valid": not errors, "errors": errors}


def matter_plan_required_for_eval(
    eval_row: dict[str, Any],
    observed_route: dict[str, Any],
) -> bool:
    expected_category = str(eval_row.get("expected_category") or "").strip().lower()
    if expected_category:
        return expected_category not in {"off_topic", "non_legal"}
    return observed_route.get("category") != "off_topic"


def safe_source_gap_handoff_for_eval(row: dict[str, Any]) -> bool:
    """Whether the stream intentionally withheld an answer and plan.

    A safe source-gap handoff is still a product failure until the corpus is
    repaired, but it is not a malformed MatterPlan. Keeping this distinction
    makes the report identify the missing authority rather than blaming the
    renderer for correctly refusing to answer.
    """
    return bool(
        row.get("source_gap_outcome") == "source_gap_handoff"
        and row.get("source_gap_safe_handoff_only") is True
        and int(row.get("source_count") or 0) == 0
    )


def matter_plan_applicable_for_eval(row: dict[str, Any]) -> bool:
    """Whether a row should carry a renderable MatterPlan contract."""
    if "matter_plan_applicable" in row:
        return bool(row["matter_plan_applicable"])
    return bool(row.get("matter_plan_required") and not safe_source_gap_handoff_for_eval(row))


def _is_string_list(value: Any) -> bool:
    return isinstance(value, list) and all(isinstance(item, str) for item in value)


def _valid_authority_ledger_entry(entry: Any) -> bool:
    if not isinstance(entry, dict):
        return False
    nullable_strings = ("canonical_name", "act", "section", "source_pack_id", "note")
    if not isinstance(entry.get("source"), str) or not str(entry.get("source")).strip():
        return False
    if not isinstance(entry.get("authority_id"), str) or not str(entry.get("authority_id")).strip():
        return False
    if any(entry.get(field) is not None and not isinstance(entry.get(field), str) for field in nullable_strings):
        return False
    if entry.get("identity_status") not in {"canonical", "provisional"}:
        return False
    if not _is_string_list(entry.get("required_anchor_patterns")):
        return False
    if not isinstance(entry.get("claim_type"), str):
        return False
    if entry.get("priority") not in {"must_cite", "conditional", "background"}:
        return False
    if not isinstance(entry.get("must_cite"), bool) or not isinstance(entry.get("conditional"), bool):
        return False
    return (entry.get("priority") == "must_cite") == entry.get("must_cite")


def _is_enforceable_plan_obligation(entry: Any) -> bool:
    return (
        _valid_authority_ledger_entry(entry)
        and entry.get("priority") == "must_cite"
        and entry.get("must_cite") is True
        and bool(str(entry.get("authority_id") or "").strip())
    )


def _valid_retrieval_source(source: Any) -> bool:
    if not isinstance(source, dict):
        return False
    if not isinstance(source.get("source_pack_id"), str) or not str(source.get("source_pack_id")).strip():
        return False
    if not isinstance(source.get("search_query"), str) or not str(source.get("search_query")).strip():
        return False
    if isinstance(source.get("priority"), bool) or not isinstance(source.get("priority"), (int, float)):
        return False
    return all(
        _is_string_list(source.get(field))
        for field in ("title_patterns", "doc_ids", "anchor_patterns", "source_types")
    )


def matter_plan_authority_coverage(
    plan: dict[str, Any],
    source_items: list[dict[str, Any]],
    *,
    query: str = "",
) -> dict[str, Any]:
    """Measure every activated MatterPlan authority obligation by stable ID."""
    ledger = plan.get("authority_ledger") or []
    invalid_entry_indices = [
        index
        for index, item in enumerate(ledger)
        if not isinstance(item, dict) or not str(item.get("authority_id") or "").strip()
    ]
    required_entries = [
        item
        for item in ledger
        if isinstance(item, dict)
        and item.get("authority_id")
        and item.get("priority") != "background"
        and runtime_is_active_plan_authority_entry(item, plan=plan, query=query)
    ]
    required_ids = sorted({str(item["authority_id"]) for item in required_entries})
    runtime_plan = _runtime_plan_from_payload(plan)
    missing_entries = runtime_missing_plan_authorities(
        plan=runtime_plan,
        passages=source_items,
        query=query,
    )
    missing_ids = sorted({
        str(item.get("authority_id"))
        for item in missing_entries
        if item.get("authority_id")
    })
    found_ids = [authority_id for authority_id in required_ids if authority_id not in missing_ids]
    sources_by_id = {
        str(item["authority_id"]): str(item.get("source") or "")
        for item in required_entries
    }
    return {
        "required_ids": required_ids,
        "found_ids": found_ids,
        "missing_ids": missing_ids,
        "missing_sources": [sources_by_id[authority_id] for authority_id in missing_ids],
        "coverage": (len(found_ids) / len(required_ids)) if required_ids else None,
        "invalid_entry_indices": invalid_entry_indices,
        "ok": not missing_ids and not invalid_entry_indices,
        "applicable": bool(required_ids or invalid_entry_indices),
    }


def _runtime_plan_from_payload(plan: dict[str, Any]) -> SimpleNamespace:
    """Adapt an event payload to the runtime matcher used by serving.

    The evaluator must not award authority coverage from an ID alone. The
    serving matcher also checks source-pack identity, document/type metadata,
    and provision anchors. This small adapter keeps one matching function for
    both paths without making the event JSON schema depend on Python classes.
    """
    def namespace(value: Any) -> Any:
        if isinstance(value, dict):
            return SimpleNamespace(**{key: namespace(item) for key, item in value.items()})
        if isinstance(value, list):
            return [namespace(item) for item in value]
        return value

    ledger = []
    for item in plan.get("authority_ledger") or []:
        if not isinstance(item, dict):
            continue
        entry = dict(item)
        for field in (
            "authority_id", "identity_status", "registry_key", "source_pack_id",
            "required_anchor_patterns", "section", "note", "canonical_name", "act",
        ):
            default = [] if field == "required_anchor_patterns" else None
            if field == "identity_status":
                default = "provisional"
            if field == "authority_id":
                default = ""
            entry.setdefault(field, default)
        ledger.append(namespace(entry))
    retrieval_sources = []
    for item in plan.get("retrieval_sources") or []:
        if not isinstance(item, dict):
            continue
        source = dict(item)
        for field in ("doc_ids", "source_types", "title_patterns", "anchor_patterns", "authority_ids"):
            source.setdefault(field, [])
        retrieval_sources.append(namespace(source))
    return SimpleNamespace(
        incident_date_status=plan.get("incident_date_status"),
        authority_ledger=ledger,
        retrieval_sources=retrieval_sources,
    )
def citation_integrity_metrics(
    sources: list[dict[str, Any]],
    passages: list[dict[str, Any]],
    sentences: list[dict[str, Any]],
) -> dict[str, Any]:
    cited_indices = sorted(_cited_source_indices(sentences))
    known_indices = sorted({
        int(item["index"])
        for item in [*(sources or []), *(passages or [])]
        if isinstance(item, dict) and isinstance(item.get("index"), int)
    })
    unknown = [idx for idx in cited_indices if idx not in set(known_indices)]
    return {
        "cited_indices": cited_indices,
        "known_source_indices": known_indices,
        "unknown_citation_indices": unknown,
        "unknown_citation_count": len(unknown),
        "citation_integrity_ok": not unknown,
    }


_SOURCE_COVERAGE_STOPWORDS = {
    "a", "an", "and", "act", "article", "based", "by", "code", "for", "if",
    "in", "is", "law", "of", "on", "or", "procedure", "provisions",
    "required", "route", "section", "sections", "source", "sources", "state", "the",
    "to", "under", "where", "with",
}

_SOURCE_COVERAGE_TOKEN_ALIASES = {
    "msmed": (
        "micro small and medium enterprises",
        "micro small medium enterprises",
        "micro and small enterprises",
        "medium enterprises development",
        "msefc",
    ),
    "rti": ("right to information",),
}


def classify_required_source_requirement(text: str) -> tuple[str, str | None]:
    """Classify route.required_sources strings for diagnostic scoring.

    Route requirements mix several kinds of things: controlling Acts, conditional
    authorities, local rules, procedural aids, and document/fact needs. Only a
    concrete authority should count as a retrieval miss in timed reports.
    """
    lower = str(text or "").strip().lower()
    if not lower:
        return "fact_or_document_requirement", "empty_requirement"

    if not _looks_like_authority_requirement(lower):
        authority_requirement = False
    else:
        authority_requirement = True

    fact_terms = (
        "bank statement", "transaction reference", "complaint number",
        "written grievance", "document", "documents", "proof", "evidence",
        "record, and", "details", "date", "amount",
    )
    if not authority_requirement and any(term in lower for term in fact_terms):
        return "fact_or_document_requirement", "evidence_or_fact_requirement"

    if not authority_requirement:
        return "fact_or_document_requirement", "not_an_authority_requirement"

    names_concrete_authority = (
        bool(re.search(r"\bact\b|\bregulations?\b", lower))
        or bool(re.search(r"\barticle\s+\d+", lower))
        or any(term in lower for term in (
            "bns", "bnss", "crpc", "ipc", "constitution",
            "consumer protection", "code on wages", "rbi integrated ombudsman",
            "reserve bank integrated ombudsman", "banking ombudsman",
            "insurance ombudsman", "ndps", "pmla", "pocso", "statute",
        ))
    )
    conditional_terms = (
        " only where ", " where ", " where applicable", " where relevant",
        " where needed", " if ", " based on ", " depending on ",
        " when ", " to identify ",
    )
    if any(term in f" {lower} " for term in conditional_terms) and not names_concrete_authority:
        return "conditional_authority", "conditional_authority_requirement"
    procedural_terms = (
        "court rules", "practice directions", "state rules",
        "state education rules", "local education rules",
        "state maintenance tribunal rules", "scheme rules",
        "rules based on state", "portal", "procedure", "grievance route",
        "complaint route", "legal-aid", "legal aid", "dlsa", "nalsa",
        "forum", "help desk", "identity-record update rules",
    )
    if not names_concrete_authority and any(term in lower for term in procedural_terms):
        return "procedural_or_local_source", "procedural_or_local_requirement"

    return "must_cite_authority", None


def required_source_coverage(
    required_sources: list[str],
    sources: list[dict[str, Any]],
    passages: list[dict[str, Any]],
    query: str | None = None,
) -> list[dict[str, Any]]:
    """Best-effort diagnostic for route required sources vs retrieved items.

    This is not a product gate by itself. It is for failure triage: a missing
    match points to retrieval/source-pack coverage; a found match with a bad
    answer points to answer-layer or verifier behavior.
    """
    items = [
        item
        for item in [*(sources or []), *(passages or [])]
        if isinstance(item, dict)
    ]
    out: list[dict[str, Any]] = []
    for required in required_sources or []:
        required_text = str(required or "").strip()
        runtime_requirement_type = runtime_classify_required_source_requirement(required_text)
        if not runtime_should_enforce_requirement(
            required_text,
            runtime_requirement_type,
            str(query or ""),
        ):
            out.append({
                "required_source": required_text,
                "requirement_type": runtime_requirement_type,
                "found": None,
                "skipped": True,
                "skip_reason": _runtime_skip_reason(required_text, runtime_requirement_type),
                "match_score": None,
                "matched_source": None,
            })
            continue
        runtime_match = runtime_best_source_match(required_text, items, query=str(query or ""))
        if runtime_match is not None:
            out.append({
                "required_source": required_text,
                "requirement_type": runtime_requirement_type,
                "found": True,
                "match_score": 1.0,
                "matched_source": compact_source_item(runtime_match),
            })
            continue
        out.append({
            "required_source": required_text,
            "requirement_type": runtime_requirement_type,
            "found": False,
            "match_score": 0.0,
            "matched_source": None,
        })
    return out


def _runtime_skip_reason(required_text: str, requirement_type: str) -> str:
    lower = str(required_text or "").lower()
    if requirement_type == "conditional_authority":
        return "conditional_authority_not_triggered_by_query"
    if requirement_type == "procedural_or_local_source":
        return "procedural_or_local_requirement"
    if requirement_type == "fact_or_document_requirement":
        if any(term in lower for term in (
            "bank statement", "transaction reference", "complaint number",
            "written grievance", "document", "documents", "proof", "evidence",
            "details", "date", "amount",
        )):
            return "evidence_or_fact_requirement"
        return "not_an_authority_requirement"
    return "runtime_requirement_not_triggered_by_query"


def _is_untriggered_conditional_authority(required_text: str, query: str) -> bool:
    lower = required_text.lower()
    q = query.lower()
    runtime_requirement_type = runtime_classify_required_source_requirement(required_text)
    if runtime_requirement_type == "conditional_authority":
        return not runtime_should_enforce_requirement(required_text, runtime_requirement_type, query)
    if "juvenile justice" in lower and "adoption" in lower:
        return not _has_adoption_source_context(q)
    if "indian succession act" in lower and _has_any(q, ("muslim", "sunni", "shariat")):
        return True
    if "information technology act" in lower and any(term in lower for term in ("platform", "dms", "online accounts")):
        return not _has_any(q, (
            "cyber", "online", "instagram", "insta", "whatsapp", "telegram",
            "facebook", "dm", "dms", "message", "account", "profile",
            "deepfake", "otp", "upi", "data",
        ))
    if "family law statute" in lower or "personal law" in lower:
        return not _has_any(q, FAMILY_PERSONAL_LAW_TRIGGER_TERMS)
    if "maintenance" in lower and any(term in lower for term in ("bnss", "crpc")):
        return not _has_any(q, MAINTENANCE_TRIGGER_TERMS)
    if not any(term in f" {lower} " for term in (
        " where ", " where applicable", " where relevant", " where needed",
        " only if ", " only where ", " if ",
    )):
        return False
    if "based on incident date" in lower and any(term in lower for term in ("bns", "bnss", "ipc", "crpc")):
        return False
    if "pocso" in lower or "protection of children from sexual offences" in lower:
        return not _has_any(q, ("pocso", "minor", "child", "girl", "boy", "under 18", "17 year", "16 year", "15 year", "14 year"))
    if "indian partnership" in lower:
        return not _has_any(q, ("partner", "partnership", "firm", "llp"))
    if "aadhaar" in lower:
        return not _has_any(q, ("aadhaar", "aadhar", "uidai", "kyc", "biometric", "identity mismatch"))
    if "specific relief" in lower:
        return not _has_any(q, ("injunction", "specific performance", "exclusivity", "exclusive", "cancel", "cancellation", "declaration", "restrain", "gift deed", "blank paper", "thumb impression", "sale deed"))
    if "transfer of property" in lower:
        return not _has_any(q, (
            "gift", "gift deed", "settlement", "transfer paper", "property transfer",
            "transferred property", "sale deed", "lease deed", "oral gift",
            "verbally", "cancel", "cancellation", "revoke", "revocation",
        ))
    if "inter-state migrant" in lower or "inter state migrant" in lower:
        return not _has_any(q, (
            "inter-state", "inter state", "migrant", "came from", "brought from",
            "recruited from", "return ticket", "journey allowance", "go back home",
            "walked from", "home state", "native place",
        ))
    if "bonded labour" in lower:
        return not _has_any(q, (
            "bonded", "advance", "debt", "loan", "release certificate",
            "rehabilitation", "hostage", "not letting", "cannot leave",
            "forced to work", "document kept", "id kept", "aadhaar kept",
        ))
    if (
        "bocw cess" in lower
        or "welfare-board cess" in lower
        or "welfare board cess" in lower
        or "construction workers welfare cess" in lower
    ):
        return not _has_any(q, (
            "cess", "fake register", "false register", "fake registers",
            "same name", "fake entry", "fake entries", "muster roll",
            "register fraud", "welfare board record", "welfare-board record",
            "cess record", "cess records",
        ))
    if "medical ethics" in lower or "medical council" in lower:
        return not _has_any(q, (
            "medical records", "case papers", "hospital records", "not giving records",
            "wrong treatment", "wrong injection", "wrong surgery", "wrong leg",
            "negligence", "medical negligence", "died", "death", "dead",
            "injury", "misconduct",
        ))
    if "clinical establishments" in lower:
        return not _has_any(q, (
            "hospital", "doctor", "medical", "icu", "billing", "bill",
            "records", "negligence", "wrong surgery", "wrong leg",
        ))
    if "prevention of corruption" in lower:
        if _has_any(q, (
            "no bribe", "not bribe", "not a bribe", "without bribe",
            "no cash demand", "no money demand", "no money demanded",
            "not asking money", "not asked money", "did not ask money",
            "didn't ask money", "no payment demand",
        )):
            return True
    if "labour/dlsa grievance route" in lower or "labour dlsa grievance route" in lower:
        return not _has_any(q, (
            "dlsa", "legal aid", "free lawyer", "cannot afford lawyer",
            "no lawyer", "legal help", "nalsa", "slsa",
        ))
    if "victim-compensation" in lower or "victim compensation" in lower:
        return not _has_any(q, (
            "acid attack", "acid thrown", "burn", "burns", "injury", "injured",
            "hospital", "treatment", "compensation", "medical bill",
        ))
    if "sale of goods" in lower:
        return not _has_any(q, ("goods", "material", "defect", "defective", "delivery", "quality", "rejection", "refund"))
    if "industrial disputes" in lower:
        return not _has_any(q, ("industrial dispute", "industrial disputes", "section 10", "sec 10", "termination", "terminated", "retrench", "fired", "labour court", "factory closed", "no notice"))
    if "maternity benefit" in lower:
        return not _has_any(q, ("maternity", "pregnan", "delivery", "delivered", "baby", "leave"))
    if "epf" in lower or "provident" in lower:
        return not _has_any(q, ("epf", "pf", "provident", "uan", "pension"))
    if "forest rights" in lower or "pesa" in lower:
        non_scheduled = _has_any(q, ("non scheduled", "non-scheduled"))
        scheduled_context = _has_any(q, ("scheduled area", "fifth schedule", "pesa")) and not non_scheduled
        return not (_has_any(q, ("forest", "gram sabha", "ifr", "cfr")) or scheduled_context)
    if "building and other construction" in lower or "bocw" in lower or "factories act" in lower:
        return not _has_any(q, (
            "construction", "building work", "site", "worksite", "factory",
            "plant", "boiler", "machine", "accident at work", "worker died",
            "fell from", "lost hand", "lost limb", "bocw", "cess",
            "register", "fake register", "false register", "same name",
            "welfare board", "benefit claim", "thekedar",
        ))
    if "criminal-negligence" in lower or "criminal negligence" in lower:
        return not _has_any(q, (
            "negligence", "wrong treatment", "death", "died", "dead", "injury",
            "assault", "medical negligence", "wrong injection", "wrong surgery",
        ))
    if "code on wages" in lower or "minimum wage" in lower:
        if "only if" in lower:
            return not _has_any(q, (
                "wage", "wages", "salary", "overtime", "deduct", "deducted",
                "minimum", "full and final", "leave encash", "payment withheld",
                "unpaid dues", "not paid salary", "food deducted",
            ))
        return not _has_any(q, ("wage", "wages", "salary", "overtime", "deduct", "minimum", "payment"))
    if "legal services authorities" in lower or "legal aid" in lower or "dlsa" in lower:
        return not _has_any(q, (
            "dlsa", "legal aid", "free lawyer", "legal services", "nalsa",
            "slsa", "legal help", "cannot afford lawyer", "no lawyer",
            "lawyer not coming", "jail legal aid",
        ))
    if "article 32" in lower:
        return not _has_any(q, ("supreme court", "article 32", "fundamental right"))
    if "registration act only if" in lower:
        return not _has_any(q, (
            "registration", "registered", "unregistered", "sub registrar",
            "sub-registrar", "sale deed", "gift deed", "lease deed",
            "admissibility", "document validity",
        ))
    if "bnss" in lower and "crpc" in lower and "only if" in lower:
        return not _has_any(q, (
            "fir", "arrest", "bail", "criminal", "ipc", "bns",
            "bnss", "crpc", "chargesheet", "charge sheet", "remand",
            "custody", "summons in criminal", "warrant", "accused",
        ))
    if "bns" in lower or "ipc" in lower:
        return False
    if "bnss" in lower or "crpc" in lower:
        return False
    return False


def _has_any(text: str, terms: tuple[str, ...]) -> bool:
    return any(term in text for term in terms)


def _canonical_required_source_match(
    required_text: str,
    items: list[dict[str, Any]],
    query: str | None = None,
) -> dict[str, Any] | None:
    lower = required_text.lower()
    query_lower = str(query or "").lower()
    if _is_state_prison_manual_requirement(required_text) and not _has_delhi_prison_query_context(query_lower):
        return None
    if "information technology act" in lower and "67b" in lower:
        if "66e" not in lower and "67a" not in lower:
            for item in items:
                blob = _item_blob(item)
                if (
                    "information technology" in blob
                    or "it-2000" in blob
                ) and re.search(r"sec-67b\b|/sec-67b\b", blob):
                    return item
            return None
        for item in items:
            blob = _item_blob(item)
            if (
                "information technology" in blob
                or "it-2000" in blob
            ) and re.search(r"sec-66e\b|/sec-66e\b|sec-67\b|/sec-67\b|sec-67a\b|/sec-67a\b|sec-67b\b|/sec-67b\b", blob):
                return item
        return None
    if "pocso" in lower or "protection of children from sexual offences" in lower:
        for item in items:
            blob = _item_blob(item)
            if (
                "pocso" in blob
                or "protection of children from sexual offences" in blob
            ) and re.search(r"sec-13\\b|/sec-13\\b|sec-13-a\\b|/sec-13-a\\b|sec-13-b\\b|/sec-13-b\\b|sec-15\\b|/sec-15\\b|sec-19\\b|/sec-19\\b", blob):
                return item
        return None
    if "arms act" in lower:
        for item in items:
            blob = _item_blob(item)
            if (
                ("arms act" in blob or "arms-1959" in blob)
                and any(anchor in blob for anchor in ("sec-2", "sec-4", "sec-25"))
            ):
                return item
        return None
    if "maharashtra control of organised crime" in lower or "mcoca" in lower:
        for item in items:
            blob = _item_blob(item)
            if (
                ("maharashtra control of organised crime" in blob or "mcoca" in blob)
                and ("sec-21" in blob or "/sec-21" in blob)
            ):
                return item
        return None
    if _has_statute_alias(lower, ("bnss", "crpc")) and "based on incident date" in lower:
        return _dual_regime_bnss_crpc_match(lower, items, query_lower)
    if "bnss/crpc custody" in lower or (_has_statute_alias(lower, ("bnss", "crpc")) and "custody" in lower):
        for item in items:
            blob = _item_blob(item)
            if (
                _has_statute_alias(blob, ("bnss", "crpc"))
                and any(anchor in blob for anchor in (
                    "sec-167", "sec-187", "sec-436a", "sec-436-a", "sec-479",
                    "sec-50", "sec-57", "sec-397", "sec-374",
                ))
            ):
                return item
        return None
    if _has_statute_alias(lower, ("bns", "ipc")):
        for item in items:
            blob = _item_blob(item)
            if _bns_ipc_item_matches(lower, blob, query_lower):
                return item
        return None
    if _is_state_prison_manual_requirement(required_text) and _has_delhi_prison_query_context(query_lower):
        for item in items:
            if _is_delhi_prison_rules_item(item):
                return item

    if "copyright act" in lower and any(
        term in lower
        for term in ("infringement", "exception", "fair dealing", "civil remedies", "civil remedy")
    ):
        needed = {
            "infringement": ("/sec-51",),
            "exceptions": ("/sec-52",),
            "remedies": ("/sec-55",),
        }
        matched: dict[str, dict[str, Any]] = {}
        for item in items:
            blob = _item_blob(item)
            title = str(item.get("title") or "").lower()
            anchor = str(item.get("anchor") or "").lower()
            if "copyright" not in title and "copyright" not in blob:
                continue
            for role, anchors in needed.items():
                if role in matched:
                    continue
                if any(anchor_term in anchor for anchor_term in anchors):
                    matched[role] = item
        if len(matched) == len(needed):
            anchors = ", ".join(str(matched[role].get("anchor") or "") for role in needed)
            return {
                "title": "Copyright Act 1957 composite route source",
                "anchor": anchors,
                "source_type": "aggregate",
            }

    if "article 21" in lower and "article 226" in lower:
        matched: dict[str, dict[str, Any]] = {}
        for item in items:
            blob = _item_blob(item)
            title = str(item.get("title") or "").lower()
            anchor = str(item.get("anchor") or "").lower()
            if "constitution" not in title and "constitution" not in blob:
                continue
            if "/sec-21" in anchor or "article 21" in blob:
                matched.setdefault("article21", item)
            if "/sec-226" in anchor or "article 226" in blob:
                matched.setdefault("article226", item)
        if {"article21", "article226"} <= set(matched):
            anchors = ", ".join(str(matched[role].get("anchor") or "") for role in ("article21", "article226"))
            return {
                "title": "Constitution of India Article 21/226 composite route source",
                "anchor": anchors,
                "source_type": "aggregate",
            }

    if ("article 21" in lower or "articles 21" in lower) and "22" in lower:
        matched: dict[str, dict[str, Any]] = {}
        for item in items:
            blob = _item_blob(item)
            title = str(item.get("title") or "").lower()
            anchor = str(item.get("anchor") or "").lower()
            if "constitution" not in title and "constitution" not in blob:
                continue
            if "/sec-21" in anchor or "article 21" in blob:
                matched.setdefault("article21", item)
            if "/sec-22" in anchor or "article 22" in blob:
                matched.setdefault("article22", item)
        if {"article21", "article22"} <= set(matched):
            anchors = ", ".join(str(matched[role].get("anchor") or "") for role in ("article21", "article22"))
            return {
                "title": "Constitution of India Article 21/22 composite route source",
                "anchor": anchors,
                "source_type": "aggregate",
            }

    if "article 21" in lower or "constitutional custody-health" in lower or "constitutional safeguards" in lower:
        for item in items:
            blob = _item_blob(item)
            title = str(item.get("title") or "").lower()
            anchor = str(item.get("anchor") or "").lower()
            if ("constitution" in title or "constitution" in blob) and (
                "/sec-21" in anchor or "article 21" in blob
            ):
                return item
    article_numbers = re.findall(r"\barticles?\s+([0-9]+[a-z]?)\b", lower)
    if article_numbers:
        wanted = sorted(set(article_numbers))
        matched: dict[str, dict[str, Any]] = {}
        for item in items:
            blob = _item_blob(item)
            title = str(item.get("title") or "").lower()
            anchor = str(item.get("anchor") or "").lower()
            if "constitution" not in title and "constitution" not in blob:
                continue
            for number in wanted:
                if f"/sec-{number}" in anchor or f"sec-{number}" in anchor or f"article {number}" in blob:
                    matched.setdefault(number, item)
        if all(number in matched for number in wanted):
            if len(wanted) == 1:
                return matched[wanted[0]]
            return {
                "title": "Constitution of India composite article source",
                "anchor": ", ".join(str(matched[number].get("anchor") or "") for number in wanted),
                "source_type": "aggregate",
            }

    if "bnss 2023 arrest" in lower or "bnss arrest" in lower:
        return _find_criminal_regime_item(
            items,
            title_aliases=("bharatiya nagarik suraksha", "bnss"),
            anchor_aliases=("/sec-35", "/sec-47", "/sec-48", "/sec-57", "/sec-58", "/sec-187"),
        )
    if "crpc 1973 arrest" in lower or "crpc arrest" in lower:
        return _find_criminal_regime_item(
            items,
            title_aliases=("code of criminal procedure", "criminal procedure", "crpc"),
            anchor_aliases=("/sec-41", "/sec-50", "/sec-56", "/sec-57", "/sec-160", "/sec-167"),
        )
    if _has_statute_alias(lower, ("bnss", "crpc")) and "bail and arrest safeguards" in lower:
        return _find_criminal_regime_item(
            items,
            title_aliases=(
                "bharatiya nagarik suraksha",
                "bnss",
                "code of criminal procedure",
                "criminal procedure",
                "crpc",
            ),
            anchor_aliases=_bail_arrest_safeguard_anchor_aliases(query_lower),
        )
    if (
        "constitutional liberty" in lower
        or "medical/vulnerability bail" in lower
        or "reproductive autonomy" in lower
        or "privacy precedents" in lower
    ):
        for item in items:
            blob = _item_blob(item)
            title = str(item.get("title") or "").lower()
            anchor = str(item.get("anchor") or "").lower()
            if ("constitution" in title or "constitution" in blob) and (
                "/sec-21" in anchor or "article 21" in blob
            ):
                return item

    if _is_pmla_sc_precedent_requirement(lower):
        for item in items:
            if _pmla_sc_precedent_item_matches(_item_blob(item)):
                return item
        return None

    if "income tax" in lower and "80c" in lower and "80ccd" in lower:
        found: dict[str, dict[str, Any]] = {}
        for item in items:
            blob = _item_blob(item)
            anchor = str(item.get("anchor") or "").lower()
            if "income tax" not in blob and "income-tax" not in blob:
                continue
            if "80c" not in found and _anchor_alias_matches(anchor, "/sec-80c"):
                found["80c"] = item
            if "80ccd" not in found and _anchor_alias_matches(anchor, "/sec-80ccd"):
                found["80ccd"] = item
        if len(found) == 2:
            return {
                "title": "Income-tax Act 1961 composite deduction source",
                "anchor": f"{found['80c'].get('anchor')}; {found['80ccd'].get('anchor')}",
                "source_type": "aggregate",
            }
        return None

    if _is_bns_bnss_or_ipc_crpc_requirement(lower) and _has_any(lower, ("cheating", "forgery", "false register", "fake register")):
        bns_item = _find_criminal_regime_item(
            items,
            title_aliases=("bharatiya nyaya sanhita", "bharatiya nyaya", "bns"),
            anchor_aliases=("sec-318", "sec-336", "sec-340", "/sec-318", "/sec-336", "/sec-340"),
        )
        bnss_item = _find_criminal_regime_item(
            items,
            title_aliases=("bharatiya nagarik suraksha", "bnss"),
            anchor_aliases=("sec-173", "sec-175", "/sec-173", "/sec-175"),
        )
        ipc_item = _find_criminal_regime_item(
            items,
            title_aliases=("indian penal code", "indian penal", "ipc"),
            anchor_aliases=("sec-420", "sec-468", "sec-471", "/sec-420", "/sec-468", "/sec-471"),
        )
        crpc_item = _find_criminal_regime_item(
            items,
            title_aliases=("code of criminal procedure", "criminal procedure", "crpc"),
            anchor_aliases=("sec-154", "sec-156", "/sec-154", "/sec-156"),
        )
        current_pair = _criminal_regime_pair_item(
            "BNS/BNSS fake-register route source",
            bns_item,
            bnss_item,
        )
        if current_pair is not None:
            return current_pair
        return _criminal_regime_pair_item(
            "IPC/CrPC fake-register route source",
            ipc_item,
            crpc_item,
        )

    if "pesa act" in lower and "forest rights" in lower:
        found: dict[str, dict[str, Any]] = {}
        for item in items:
            blob = _item_blob(item)
            anchor = str(item.get("anchor") or "").lower()
            if ("pesa" in blob or "panchayats" in blob) and any(_anchor_alias_matches(anchor, a) for a in ("/sec-4", "sec-4")):
                found["pesa"] = item
            if ("forest rights" in blob or "scheduled tribes and other traditional forest dwellers" in blob) and (
                "#header" in anchor
                or any(_anchor_alias_matches(anchor, a) for a in ("/sec-3", "/sec-4", "/sec-5", "/sec-6", "sec-3", "sec-4", "sec-5", "sec-6"))
            ):
                found["forest_rights"] = item
        pesa_context = _has_any(query_lower, (
            "pesa", "gram sabha", "scheduled area", "fifth schedule",
            "tribal village", "mining", "bauxite", "displacement", "noc",
            "land acquisition", "rehabilitation",
        )) and not _has_any(query_lower, ("non scheduled", "non-scheduled"))
        if "forest_rights" in found and not pesa_context:
            return found["forest_rights"]
        if len(found) == 2:
            return {
                "title": "PESA/FRA composite route source",
                "anchor": f"{found['pesa'].get('anchor')}; {found['forest_rights'].get('anchor')}",
                "source_type": "aggregate",
            }
        return None

    canonical_aliases: tuple[tuple[tuple[str, ...], tuple[str, ...], tuple[str, ...]], ...] = (
        (
            (
                "bnss 2023 / crpc 1973 bail provisions",
                "bnss 2023 / crpc 1973 bail procedure",
                "bnss/crpc bail provisions",
                "bnss/crpc bail procedure",
                "bail provisions",
                "bail and custody provisions",
                "bail and quashing procedure",
                "bail, notice, and investigation procedure",
                "bail and arrest safeguards",
            ),
            (
                "bharatiya nagarik suraksha",
                "bnss",
                "code of criminal procedure",
                "criminal procedure",
            ),
            (
                "/sec-436",
                "/sec-436a",
                "/sec-436-a",
                "/sec-437",
                "/sec-438",
                "/sec-439",
                "/sec-479",
                "/sec-480",
                "/sec-482",
                "/sec-483",
            ),
        ),
        (
            (
                "insurance ombudsman",
                "insurer grievance",
                "insurance grievance",
                "claim repudiation",
                "claim rejection",
            ),
            (
                "insurance ombudsman rules",
                "insurance ombudsman",
            ),
            (
                "/sec-3",
                "/sec-4",
                "/sec-5",
                "/sec-6",
                "/sec-13",
                "/sec-14",
                "/sec-15",
                "/sec-16",
                "/sec-17",
            ),
        ),
        (
            (
                "bnss/crpc complaint procedure",
                "bnss/crpc complaint",
                "bnss 2023 / crpc 1973 complaint",
                "bnss 2023 / crpc 1973 fir",
                "complaint/fir procedure",
                "complaint and investigation procedure",
                "complaint procedure",
                "criminal-complaint procedure",
                "criminal complaint procedure",
                "fir, statement, and medical-examination procedure",
                "fir and complaint procedure",
                "inquest, fir, post-mortem, and investigation procedure",
            ),
            (
                "bharatiya nagarik suraksha",
                "bnss",
                "code of criminal procedure",
                "criminal procedure",
            ),
            (
                "/sec-154",
                "/sec-156",
                "/sec-157",
                "/sec-173",
                "/sec-174",
                "/sec-175",
                "/sec-176",
                "/sec-180",
                "/sec-183",
                "/sec-184",
                "/sec-190",
                "/sec-200",
                "/sec-202",
                "/sec-223",
            ),
        ),
        (
            (
                "bnss/crpc default bail",
                "default bail and speedy trial",
                "undertrial custody",
                "speedy-trial law",
                "speedy trial law",
            ),
            (
                "bharatiya nagarik suraksha",
                "bnss",
                "code of criminal procedure",
                "criminal procedure",
            ),
            ("/sec-167", "/sec-187", "/sec-436a", "/sec-436-a", "/sec-479"),
        ),
        (
            (
                "consumer protection act",
                "product defect",
                "warranty",
                "repair",
                "return",
                "refund",
                "service deficiency",
                "paid service",
                "consumer forum",
            ),
            ("consumer protection",),
            ("/sec-2", "/sec-35", "/sec-38", "/sec-39"),
        ),
        (
            ("dowry prohibition act", "dowry or marriage-gift", "wedding expenses"),
            ("dowry prohibition",),
            ("/sec-2", "/sec-3", "/sec-4", "/sec-6", "/sec-10"),
        ),
        (
            ("clinical establishments", "clinical-establishment", "clinical establishment"),
            ("clinical establishments", "clinical-establishments"),
            ("/sec-12", "/sec-42"),
        ),
        (
            ("representation of the people", "voter-list", "voter list", "election rules"),
            ("representation of the people", "rpa-1950", "rpa-1951"),
            ("/sec-19", "/sec-22", "/sec-23", "/sec-24", "/sec-62"),
        ),
        (
            ("industrial disputes act", "industrial dispute", "labour court", "retrenchment"),
            ("industrial disputes",),
            ("/sec-2a", "/sec-2-a", "/sec-10", "/sec-25f", "/sec-25-f", "/sec-25n", "/sec-25-n"),
        ),
        (
            ("building and other construction workers act", "bocw act", "bocw registration", "welfare-board provisions"),
            ("building and other construction workers", "bocw-1996"),
            ("/sec-12", "/sec-13", "/sec-14", "/sec-39", "/sec-40", "/sec-44"),
        ),
        (
            ("factories act",),
            ("factories act", "factories-1948"),
            ("/sec-7a", "/sec-40", "/sec-41", "/sec-41b", "/sec-41c", "/sec-87", "/sec-88", "/sec-92", "/sec-111"),
        ),
        (
            ("bocw cess", "welfare-board cess", "welfare board cess", "construction workers welfare cess"),
            ("building and other construction workers welfare cess", "bocw cess", "bocw-cess"),
            ("/sec-3", "/sec-4"),
        ),
        (
            ("customs act", "icegate", "import/export", "bill of entry", "drawback", "classification"),
            ("customs act",),
            ("/sec-17", "/sec-18", "/sec-27", "/sec-28", "/sec-74", "/sec-75", "/sec-128"),
        ),
        (
            ("nclt rules", "ibc application forms", "nclt rules / ibc application forms"),
            ("national company law tribunal", "nclt rules", "insolvency and bankruptcy"),
            (),
        ),
        (
            ("nclat rules", "certified-copy", "certified copy", "nclat limitation", "nclat appeal"),
            ("national company law appellate tribunal", "nclat rules", "insolvency and bankruptcy"),
            (),
        ),
        (
            ("fssai licensing", "licensing and registration regulations", "food safety", "food licence", "food license"),
            ("food safety and standards", "licensing and registration"),
            (),
        ),
        (
            ("motor vehicles act", "driving licence", "traffic enforcement", "traffic challan", "permit", "aggregator"),
            ("motor vehicles act", "themotorvehiclesact"),
            ("/sec-3", "/sec-4", "/sec-19", "/sec-74", "/sec-93", "/sec-130", "/sec-177", "/sec-183", "/sec-193", "/sec-206"),
        ),
        (
            ("trade marks act", "trademark", "trade mark", "passing off"),
            ("trade marks act",),
            ("/sec-21", "/sec-27", "/sec-28", "/sec-29", "/sec-134", "/sec-135"),
        ),
        (
            ("companies act", "director disqualification", "annual filing", "restoration"),
            ("companies act",),
            ("/sec-92", "/sec-137", "/sec-164", "/sec-167", "/sec-248", "/sec-252"),
        ),
        (
            ("public gambling act", "common gaming-house", "game-of-skill", "online gaming"),
            ("public gambling act",),
            ("/sec-3", "/sec-4", "/sec-12"),
        ),
        (
            ("employees compensation act", "employee compensation", "workplace injury compensation"),
            ("employees compensation", "employees' compensation", "workmen's compensation", "workmens compensation"),
            ("/sec-3", "/sec-4", "/sec-10", "/sec-22"),
        ),
        (
            ("legal services authorities act", "dlsa assistance", "legal aid", "legal-aid"),
            ("legal services authorities",),
            ("/sec-12", "/sec-13", "/sec-21"),
        ),
        (("transfer of property act",), ("transfer of property act",), ("/sec-44", "/sec-45", "/sec-54", "/sec-105", "/sec-106", "/sec-111", "/sec-122", "/sec-126")),
        (("prevention of corruption act", "prevention of corruption"), ("prevention of corruption",), ("/sec-7", "/sec-8", "/sec-13")),
        (("specific relief act",), ("specific relief act",), ("/sec-31", "/sec-34", "/sec-38")),
        (("registration act",), ("registration act",), ("/sec-17", "/sec-23", "/sec-49")),
        (("hindu succession act",), ("hindu succession act",), ("/sec-6", "/sec-8", "/sec-10", "/sec-14", "/sec-15")),
        (("indian succession act",), ("indian succession act",), ("/sec-32", "/sec-33", "/sec-59", "/sec-63")),
        (
            (
                "indian contract act",
                "employment contract",
                "free-consent",
                "free consent",
                "undue influence",
                "coercion",
                "fraud source",
                "voidability source",
            ),
            ("indian contract",),
            ("/sec-14", "/sec-15", "/sec-16", "/sec-17", "/sec-18", "/sec-19", "/sec-19-a", "/sec-19-b", "/sec-37", "/sec-73"),
        ),
        (("right of children to free", "rte"), ("right of children to free",), ("/sec-12", "/sec-13", "/sec-14", "/sec-15")),
        (
            ("domestic violence", "pwdva", "protection of women from domestic violence"),
            ("domestic violence", "pwdva"),
            ("/sec-3", "/sec-12", "/sec-18", "/sec-19", "/sec-20", "/sec-22"),
        ),
        (("family courts act", "family court"), ("family courts",), ("/sec-7", "/sec-9")),
        (
            ("hindu marriage act", "marriage statute", "family law statute"),
            ("hindu marriage", "special marriage", "muslim personal", "dissolution of muslim"),
            ("/sec-9", "/sec-10", "/sec-12", "/sec-13", "/sec-24", "/sec-25", "/sec-27"),
        ),
        (
            ("cgst act", "gst registration"),
            ("central goods and services tax", "cgst"),
            ("/sec-16", "/sec-22", "/sec-24", "/sec-29", "/sec-41", "/sec-47", "/sec-67", "/sec-73", "/sec-74", "/sec-75"),
        ),
        (
            ("banking regulation act", "regulated-entity records", "regulated entity records"),
            ("banking regulation",),
            ("/sec-35a", "/sec-35-a", "/sec-45za", "/sec-45-za"),
        ),
        (
            ("municipal law", "municipalities act", "municipal corporation", "nagarpalika"),
            ("municipal", "municipalities", "municipal corporation", "nagarpalika"),
            ("/sec-221", "/sec-331", "/sec-376", "/sec-376a", "/sec-376-a"),
        ),
        (
            ("code on wages", "payment of wages"),
            ("code on wages", "payment of wages"),
            ("/sec-17", "/sec-18", "/sec-43", "/sec-45"),
        ),
        (("minimum wage", "minimum wages"), ("minimum wages", "code on wages"), ("/sec-3", "/sec-5", "/sec-17", "/sec-45")),
        (("maternity benefit", "maternity"), ("maternity benefit",), ("/sec-5", "/sec-12")),
        (("employees provident", "employees' provident", "epf", "provident fund"), ("provident", "epf"), ("/sec-6", "/sec-7a", "/sec-14")),
        (("employees state insurance", "esi"), ("employees state insurance", "esi"), ("/sec-38", "/sec-39", "/sec-46")),
        (("inter-state migrant", "inter state migrant", "ismw"), ("inter-state migrant", "inter state migrant"), ("/sec-6", "/sec-12", "/sec-14")),
        (("bonded labour", "bonded labor"), ("bonded labour", "bonded labor"), ("/sec-4", "/sec-10", "/sec-12")),
        (("mgnrega", "mahatma gandhi national rural employment", "nrega"), ("mahatma gandhi national rural employment", "mgnrega", "nrega"), ("/sec-3", "/sec-15", "/sec-19", "/sec-23")),
        (
            ("right to information", "rti"),
            ("right to information", "rti"),
            ("/sec-6", "/sec-7", "/sec-19"),
        ),
        (("national food security", "ration", "tpds"), ("national food security",), ("/sec-3", "/sec-12", "/sec-14", "/sec-15")),
        (
            ("aadhaar act", "aadhaar authentication", "uidai"),
            ("aadhaar", "unique identification"),
            ("/sec-7", "/sec-8", "/sec-59"),
        ),
        (("forest rights act", "fra 2006", "forest rights"), ("forest rights", "scheduled tribes and other traditional forest dwellers", "fra-2006"), ("#header", "/sec-3", "/sec-4", "/sec-5", "/sec-6")),
        (("pesa act", "pesa", "scheduled area", "gram sabha"), ("pesa", "panchayats"), ("/sec-4",)),
        (("indian partnership act", "partnership act"), ("partnership",), ("/sec-9", "/sec-12", "/sec-32", "/sec-44")),
        (("sale of goods act", "sale of goods"), ("sale of goods",), ("/sec-11", "/sec-12", "/sec-31", "/sec-42")),
        (("msmed act", "msme", "facilitation council"), ("micro, small", "msmed"), ("/sec-15", "/sec-16", "/sec-18")),
        (("income tax act", "tds", "tcs", "assessment", "appeal"), ("income tax",), ("/sec-45", "/sec-54", "/sec-54f", "/sec-80", "/sec-80a", "/sec-80c", "/sec-80ccd", "/sec-80cce", "/sec-143", "/sec-154", "/sec-194", "/sec-206c", "/sec-246a", "/sec-249")),
        (("limitation act", "condonation of delay", "delay or appeal time"), ("limitation",), ("/sec-3", "/sec-5", "/sec-14")),
        (("real estate", "rera"), ("real estate", "rera"), ("/sec-11", "/sec-18", "/sec-31", "/sec-34")),
        (("prison rules", "prison manual", "state prison rules"), ("prison rules", "prison manual", "prisons act"), ("/rule-2", "/rule-613", "/rule-614", "/rule-615", "/rule-616", "/sec-59")),
        (
            ("juvenile justice", "jj act"),
            ("juvenile justice", "jj-2015"),
            ("/sec-9", "/sec-12", "/sec-56", "/sec-57", "/sec-58", "/sec-59", "/sec-62", "/sec-63", "/sec-94"),
        ),
        (("immoral traffic", "itpa"), ("immoral traffic", "itpa"), ("/sec-5", "/sec-6", "/sec-17")),
        (("public gambling", "common gaming-house", "game-of-skill"), ("public gambling",), ("/sec-3", "/sec-4", "/sec-12")),
        (("registration of births and deaths", "births and deaths"), ("registration of births",), ("/sec-8", "/sec-12", "/sec-13")),
        (("code on social security", "social-security coverage"), ("social security",), ("#header", "/sec-109", "/sec-112", "/sec-113")),
        (("information technology act", "it act", "it rules", "intermediary grievance", "identity-theft"), ("information technology", "it-2000"), ("/sec-66c", "/sec-66d", "/sec-67", "/sec-67a", "/sec-67b", "/sec-69", "/sec-69a", "/sec-79", "/sec-90")),
        (
            ("article 21 and article 22 lawyer-access", "article 21 and article 22 lawyer access"),
            ("constitution of india", "constitution"),
            ("/sec-21", "/sec-22"),
        ),
        (
            ("compoundable", "compounding", "compoundable offences", "court permission and offence-compoundability"),
            ("bharatiya nagarik suraksha", "code of criminal procedure", "criminal procedure"),
            ("/sec-359", "/sec-320"),
        ),
        (
            ("bnss 2023 section 35", "bnss section 35", "police notice/appearance", "notice-to-appear"),
            ("bharatiya nagarik suraksha", "bnss"),
            ("/sec-35", "/sec-35-a", "/sec-35-b", "/sec-35-c", "/sec-35-d"),
        ),
        (
            ("crpc 1973 section 160", "crpc section 160", "witness-attendance"),
            ("code of criminal procedure", "criminal procedure"),
            ("/sec-160",),
        ),
        (
            ("bnss 2023 arrest and 24-hour production", "bnss arrest and 24-hour production", "24-hour production safeguards"),
            ("bharatiya nagarik suraksha", "bnss"),
            ("/sec-47", "/sec-48", "/sec-57", "/sec-58"),
        ),
        (
            ("crpc 1973 arrest and 24-hour production", "crpc arrest and 24-hour production"),
            ("code of criminal procedure", "criminal procedure"),
            ("/sec-50", "/sec-56", "/sec-57"),
        ),
        (
            ("crpc 1973 section 436a", "crpc section 436a", "section 436a", "undertrial custody"),
            ("code of criminal procedure", "criminal procedure"),
            ("/sec-436a", "/sec-436-a", "/sec-436A"),
        ),
        (
            ("bnss 2023 section 479", "bnss section 479", "undertrial custody-review"),
            ("bharatiya nagarik suraksha", "bnss"),
            ("/sec-479",),
        ),
        (
            ("bnss 2023 section 528", "bnss section 528", "high court inherent-powers", "inherent-powers/quashing", "quashing framing"),
            ("bharatiya nagarik suraksha", "bnss"),
            ("/sec-528",),
        ),
    )
    for required_aliases, title_aliases, anchor_aliases in canonical_aliases:
        if not any(alias in lower for alias in required_aliases):
            continue
        for item in items:
            blob = _item_blob(item)
            title = str(item.get("title") or "").lower()
            anchor = str(item.get("anchor") or "").lower()
            if not any(alias in title or alias in blob for alias in title_aliases):
                continue
            if anchor_aliases and not any(_anchor_alias_matches(anchor, anchor_alias) for anchor_alias in anchor_aliases):
                continue
            if _is_statutory_source_item(item):
                return item
    return None


def _dual_regime_bnss_crpc_match(
    required_lower: str,
    items: list[dict[str, Any]],
    query_lower: str,
) -> dict[str, Any] | None:
    anchors = _bnss_crpc_anchor_aliases_for_requirement(required_lower)
    is_offence_plus_procedure = _is_bns_bnss_or_ipc_crpc_requirement(required_lower)
    offence_anchors = _bns_ipc_anchor_terms(required_lower, query_lower) if is_offence_plus_procedure else ()
    bns_item = _find_criminal_regime_item(
        items,
        title_aliases=("bharatiya nyaya sanhita", "bharatiya nyaya", "bns"),
        anchor_aliases=offence_anchors,
    )
    bnss_item = _find_criminal_regime_item(
        items,
        title_aliases=("bharatiya nagarik suraksha", "bnss"),
        anchor_aliases=anchors["bnss"],
    )
    ipc_item = _find_criminal_regime_item(
        items,
        title_aliases=("indian penal code", "indian penal", "ipc"),
        anchor_aliases=offence_anchors,
    )
    crpc_item = _find_criminal_regime_item(
        items,
        title_aliases=("code of criminal procedure", "criminal procedure", "crpc"),
        anchor_aliases=anchors["crpc"],
    )
    if is_offence_plus_procedure:
        if _query_points_to_old_criminal_regime(query_lower):
            return _criminal_regime_pair_item(
                "IPC/CrPC composite route source",
                ipc_item,
                crpc_item,
            )
        if _query_points_to_new_criminal_regime(query_lower):
            return _criminal_regime_pair_item(
                "BNS/BNSS composite route source",
                bns_item,
                bnss_item,
            )
        current_pair = _criminal_regime_pair_item(
            "BNS/BNSS composite route source",
            bns_item,
            bnss_item,
        )
        if current_pair is not None:
            return current_pair
        return _criminal_regime_pair_item(
            "IPC/CrPC composite route source",
            ipc_item,
            crpc_item,
        )
    if _query_points_to_old_criminal_regime(query_lower):
        return crpc_item
    if _query_points_to_new_criminal_regime(query_lower):
        return bnss_item
    if any(term in required_lower for term in ("chargesheet", "charge sheet", "charge-sheet", "police report", "summons", "discharge")):
        return bnss_item or crpc_item
    if bnss_item is not None and crpc_item is not None:
        return {
            "title": "BNSS/CrPC composite route source",
            "anchor": f"{bnss_item.get('anchor')}; {crpc_item.get('anchor')}",
            "source_type": "aggregate",
        }
    return None


def _is_bns_bnss_or_ipc_crpc_requirement(required_lower: str) -> bool:
    return (
        _has_statute_alias(required_lower, ("bns", "bharatiya nyaya"))
        and _has_statute_alias(required_lower, ("bnss", "bharatiya nagarik"))
        and _has_statute_alias(required_lower, ("ipc", "indian penal"))
        and _has_statute_alias(required_lower, ("crpc", "criminal procedure"))
    )


def _criminal_regime_pair_item(
    title: str,
    offence_item: dict[str, Any] | None,
    procedure_item: dict[str, Any] | None,
) -> dict[str, Any] | None:
    if offence_item is None or procedure_item is None:
        return None
    return {
        "title": title,
        "anchor": f"{offence_item.get('anchor')}; {procedure_item.get('anchor')}",
        "source_type": "aggregate",
    }


def _is_hard_canonical_requirement(required_text: str) -> bool:
    lower = required_text.lower()
    return (
        ("bnss" in lower and "crpc" in lower and "based on incident date" in lower)
        or ("bns" in lower and "ipc" in lower)
        or _is_pmla_sc_precedent_requirement(lower)
        or ("income tax" in lower and "80c" in lower and "80ccd" in lower)
        or ("pesa act" in lower and "forest rights" in lower)
        or "bnss 2023 arrest" in lower
        or "crpc 1973 arrest" in lower
        or "bocw cess" in lower
        or "welfare-board cess" in lower
        or "welfare board cess" in lower
        or "construction workers welfare cess" in lower
        or "building and other construction workers act" in lower
        or "bocw act" in lower
        or "bocw registration" in lower
        or "welfare-board provisions" in lower
    )


def _find_criminal_regime_item(
    items: list[dict[str, Any]],
    *,
    title_aliases: tuple[str, ...],
    anchor_aliases: tuple[str, ...],
) -> dict[str, Any] | None:
    for item in items:
        blob = _item_blob(item)
        title = str(item.get("title") or "").lower()
        anchor = str(item.get("anchor") or "").lower()
        if not _has_statute_alias(f"{title} {blob}", title_aliases):
            continue
        if anchor_aliases and not any(_anchor_alias_matches(anchor, alias) for alias in anchor_aliases):
            continue
        if _is_statutory_source_item(item):
            return item
    return None


def _bnss_crpc_anchor_aliases_for_requirement(required_lower: str) -> dict[str, tuple[str, ...]]:
    if any(term in required_lower for term in ("search", "seizure", "seize")):
        return {
            "bnss": ("/sec-105", "/sec-173", "/sec-175", "/sec-187", "/sec-480", "/sec-483"),
            "crpc": (
                "/sec-100", "/sec-102", "/sec-154", "/sec-156", "/sec-165",
                "/sec-167", "/sec-437", "/sec-438", "/sec-439",
            ),
        }
    if "arrest" in required_lower and any(term in required_lower for term in ("fir", "remand", "bail")):
        return {
            "bnss": (
                "/sec-35", "/sec-47", "/sec-48", "/sec-57", "/sec-58",
                "/sec-173", "/sec-175", "/sec-187", "/sec-480", "/sec-483",
            ),
            "crpc": (
                "/sec-41", "/sec-50", "/sec-56", "/sec-57", "/sec-154",
                "/sec-156", "/sec-167", "/sec-437", "/sec-438", "/sec-439",
            ),
        }
    if any(term in required_lower for term in ("default bail", "default-bail", "no chargesheet", "no charge sheet", "undertrial")):
        return {
            "bnss": ("/sec-187", "/sec-479"),
            "crpc": ("/sec-167", "/sec-436a", "/sec-436-a", "/sec-436A"),
        }
    if any(term in required_lower for term in ("chargesheet", "charge sheet", "charge-sheet", "police report", "discharge")):
        return {
            "bnss": (
                "/sec-193", "/sec-250", "/sec-251", "/sec-262", "/sec-263",
                "/sec-268", "/sec-269", "/sec-480", "/sec-483",
            ),
            "crpc": (
                "/sec-173", "/sec-227", "/sec-239", "/sec-245",
                "/sec-437", "/sec-438", "/sec-439",
            ),
        }
    if "bail" in required_lower:
        return {
            "bnss": ("/sec-479", "/sec-480", "/sec-482", "/sec-483"),
            "crpc": ("/sec-436", "/sec-436a", "/sec-436-a", "/sec-437", "/sec-438", "/sec-439"),
        }
    if any(term in required_lower for term in ("fir", "complaint", "investigation", "medical", "statement", "inquest")):
        return {
            "bnss": ("/sec-173", "/sec-175", "/sec-176", "/sec-180", "/sec-183", "/sec-184", "/sec-223"),
            "crpc": ("/sec-154", "/sec-156", "/sec-157", "/sec-174", "/sec-176", "/sec-190", "/sec-200", "/sec-202"),
        }
    if any(term in required_lower for term in ("arrest", "detention", "production", "remand", "notice")):
        return {
            "bnss": ("/sec-35", "/sec-47", "/sec-48", "/sec-57", "/sec-58", "/sec-187"),
            "crpc": ("/sec-41", "/sec-50", "/sec-56", "/sec-57", "/sec-160", "/sec-167"),
        }
    return {"bnss": (), "crpc": ()}


def _bail_arrest_safeguard_anchor_aliases(query_lower: str) -> tuple[str, ...]:
    arrest_procedure_context = _has_any(query_lower, (
        "arrest", "arrested", "detain", "detained", "custody", "picked",
        "pickup", "police took", "not produced", "24 hours",
        "twenty four hours", "arrest memo", "grounds of arrest",
        "lawyer during interrogation",
    ))
    bail_context = _has_any(query_lower, (
        "bail", "anticipatory", "default bail", "regular bail",
        "twin condition", "pmla", "surety",
    ))
    arrest_anchors = (
        "/sec-35", "/sec-41", "/sec-47", "/sec-48", "/sec-50", "/sec-56",
        "/sec-57", "/sec-58", "/sec-160", "/sec-167", "/sec-187",
    )
    bail_anchors = (
        "/sec-436", "/sec-436a", "/sec-436-a", "/sec-437", "/sec-438",
        "/sec-439", "/sec-479", "/sec-480", "/sec-482", "/sec-483",
    )
    if arrest_procedure_context and not bail_context:
        return arrest_anchors
    if bail_context and not arrest_procedure_context:
        return bail_anchors
    return arrest_anchors + bail_anchors


def _anchor_alias_matches(anchor: str, alias: str) -> bool:
    normalized = alias.lower().lstrip("/")
    return bool(re.search(rf"(?<![a-z0-9])/?{re.escape(normalized)}(?![a-z0-9])", anchor))


def _query_points_to_old_criminal_regime(query_lower: str) -> bool:
    if _has_any(query_lower, (
        "before 1 july 2024", "before july 2024", "pre july 2024",
        "pre-2024",
    )):
        return True
    return any(marker < (2024, 7, 1) for marker in _criminal_regime_date_markers(query_lower))


def _query_points_to_new_criminal_regime(query_lower: str) -> bool:
    if _query_points_to_old_criminal_regime(query_lower):
        return False
    if _has_any(query_lower, (
        "after 1 july 2024", "after july 2024", "from 1 july 2024",
        "new bnss",
    )):
        return True
    return any(marker >= (2024, 7, 1) for marker in _criminal_regime_date_markers(query_lower))


def _criminal_regime_date_markers(query_lower: str) -> list[tuple[int, int, int]]:
    markers: list[tuple[int, int, int]] = []
    month_names = {
        "jan": 1, "january": 1,
        "feb": 2, "february": 2,
        "mar": 3, "march": 3,
        "apr": 4, "april": 4,
        "may": 5,
        "jun": 6, "june": 6,
        "jul": 7, "july": 7,
        "aug": 8, "august": 8,
        "sep": 9, "sept": 9, "september": 9,
        "oct": 10, "october": 10,
        "nov": 11, "november": 11,
        "dec": 12, "december": 12,
    }
    for match in re.finditer(
        r"\b(?:(?P<day>\d{1,2})(?:st|nd|rd|th)?\s+)?(?P<month>jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|jul(?:y)?|aug(?:ust)?|sep(?:t|tember)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)\s*,?\s*(?P<year>20\d{2})\b",
        query_lower,
    ):
        year = int(match.group("year"))
        month = month_names[match.group("month")]
        day = int(match.group("day") or 1)
        markers.append((year, month, day))
    for match in re.finditer(r"\b(?P<year>20\d{2})[-/](?P<month>\d{1,2})(?:[-/](?P<day>\d{1,2}))?\b", query_lower):
        year = int(match.group("year"))
        month = int(match.group("month"))
        day = int(match.group("day") or 1)
        if 1 <= month <= 12 and 1 <= day <= 31:
            markers.append((year, month, day))
    for match in re.finditer(r"\b(?P<day>\d{1,2})[-/](?P<month>\d{1,2})[-/](?P<year>20\d{2})\b", query_lower):
        year = int(match.group("year"))
        month = int(match.group("month"))
        day = int(match.group("day"))
        if 1 <= month <= 12 and 1 <= day <= 31:
            markers.append((year, month, day))
    if markers:
        return markers
    for match in re.finditer(r"\b(?:fir from|fir|incident in|incident|arrested in|case from|from|in)\s+(?P<year>20\d{2})\b", query_lower):
        year = int(match.group("year"))
        if year <= 2023 or year >= 2025:
            markers.append((year, 1, 1))
    return markers


def _has_statute_alias(blob: str, terms: tuple[str, ...]) -> bool:
    for term in terms:
        normalized = term.lower()
        if normalized in {"bns", "bnss", "ipc", "crpc"}:
            if re.search(rf"(?<![a-z0-9]){re.escape(normalized)}(?![a-z0-9])", blob):
                return True
            continue
        if normalized in blob:
            return True
    return False


def _bns_ipc_item_matches(required_lower: str, item_blob: str, query_lower: str) -> bool:
    has_bns = _has_statute_alias(item_blob, ("bns", "bharatiya nyaya"))
    has_ipc = _has_statute_alias(item_blob, ("ipc", "indian penal"))
    anchors = _bns_ipc_anchor_terms(required_lower, query_lower)
    if anchors and not any(anchor in item_blob for anchor in anchors):
        return False
    if _query_points_to_old_criminal_regime(query_lower):
        return has_ipc
    if _query_points_to_new_criminal_regime(query_lower):
        return has_bns
    return has_bns or has_ipc


def _bns_ipc_anchor_terms(required_lower: str, query_lower: str) -> tuple[str, ...]:
    blob = f"{required_lower} {query_lower}"
    groups: list[tuple[str, tuple[str, ...]]] = [
        ("acid", ("sec-124", "sec-326a", "sec-326b", "/sec-124", "/sec-326a", "/sec-326b")),
        ("sexual", ("sec-63", "sec-64", "sec-65", "sec-70", "sec-74", "sec-75", "sec-76", "sec-77", "sec-78", "sec-79", "sec-354", "sec-354a", "sec-354b", "sec-354c", "sec-354d", "sec-376", "/sec-63", "/sec-64", "/sec-65", "/sec-70", "/sec-74", "/sec-75", "/sec-76", "/sec-77", "/sec-78", "/sec-79", "/sec-354", "/sec-354a", "/sec-354b", "/sec-354c", "/sec-354d", "/sec-376")),
        ("rape", ("sec-63", "sec-64", "sec-65", "sec-70", "sec-376", "/sec-63", "/sec-64", "/sec-65", "/sec-70", "/sec-376")),
        ("stalk", ("sec-78", "sec-354d", "/sec-78", "/sec-354d")),
        ("threat", ("sec-351", "sec-503", "sec-506", "/sec-351", "/sec-503", "/sec-506")),
        ("intimidation", ("sec-351", "sec-503", "sec-506", "/sec-351", "/sec-503", "/sec-506")),
        ("defamation", ("sec-356", "sec-499", "sec-500", "/sec-356", "/sec-499", "/sec-500")),
        ("reputation", ("sec-356", "sec-499", "sec-500", "/sec-356", "/sec-499", "/sec-500")),
        ("dacoity", ("sec-309", "sec-310", "sec-311", "sec-391", "sec-395", "sec-398", "/sec-309", "/sec-310", "/sec-311", "/sec-391", "/sec-395", "/sec-398")),
        ("robbery", ("sec-309", "sec-310", "sec-390", "sec-392", "sec-394", "/sec-309", "/sec-310", "/sec-390", "/sec-392", "/sec-394")),
        ("cheating", ("sec-318", "sec-319", "sec-415", "sec-416", "sec-420", "/sec-318", "/sec-319", "/sec-415", "/sec-416", "/sec-420")),
        ("personation", ("sec-319", "sec-416", "/sec-319", "/sec-416")),
        ("hacked", ("sec-318", "sec-319", "sec-415", "sec-416", "sec-420", "/sec-318", "/sec-319", "/sec-415", "/sec-416", "/sec-420")),
        ("account hacked", ("sec-318", "sec-319", "sec-415", "sec-416", "sec-420", "/sec-318", "/sec-319", "/sec-415", "/sec-416", "/sec-420")),
        ("forgery", ("sec-336", "sec-337", "sec-338", "sec-340", "sec-463", "sec-464", "sec-465", "sec-468", "sec-471", "/sec-336", "/sec-337", "/sec-338", "/sec-340", "/sec-463", "/sec-464", "/sec-465", "/sec-468", "/sec-471")),
        ("false document", ("sec-336", "sec-337", "sec-338", "sec-340", "sec-463", "sec-464", "sec-465", "sec-468", "sec-471", "/sec-336", "/sec-337", "/sec-338", "/sec-340", "/sec-463", "/sec-464", "/sec-465", "/sec-468", "/sec-471")),
        ("blank paper", ("sec-336", "sec-337", "sec-338", "sec-340", "sec-463", "sec-464", "sec-465", "sec-468", "sec-471", "/sec-336", "/sec-337", "/sec-338", "/sec-340", "/sec-463", "/sec-464", "/sec-465", "/sec-468", "/sec-471")),
        ("thumb impression", ("sec-336", "sec-337", "sec-338", "sec-340", "sec-463", "sec-464", "sec-465", "sec-468", "sec-471", "/sec-336", "/sec-337", "/sec-338", "/sec-340", "/sec-463", "/sec-464", "/sec-465", "/sec-468", "/sec-471")),
        ("theft", ("sec-303", "sec-305", "sec-317", "sec-378", "sec-379", "sec-411", "/sec-303", "/sec-305", "/sec-317", "/sec-378", "/sec-379", "/sec-411")),
        ("stolen", ("sec-303", "sec-305", "sec-317", "sec-378", "sec-379", "sec-411", "/sec-303", "/sec-305", "/sec-317", "/sec-378", "/sec-379", "/sec-411")),
        ("cruelty", ("sec-85", "sec-86", "sec-498a", "sec-498-a", "/sec-85", "/sec-86", "/sec-498a", "/sec-498-a")),
        ("dowry", ("sec-80", "sec-85", "sec-86", "sec-304b", "sec-304-b", "sec-498a", "sec-498-a", "/sec-80", "/sec-85", "/sec-86", "/sec-304b", "/sec-304-b", "/sec-498a", "/sec-498-a")),
        ("extortion", ("sec-308", "sec-383", "sec-384", "/sec-308", "/sec-383", "/sec-384")),
        ("confinement", ("sec-126", "sec-127", "sec-339", "sec-340", "sec-341", "sec-342", "/sec-126", "/sec-127", "/sec-339", "/sec-340", "/sec-341", "/sec-342")),
        ("trafficking", (
            "sec-143", "sec-144", "sec-145", "sec-146",
            "sec-370", "sec-370a", "sec-371", "sec-372", "sec-373", "sec-374",
            "/sec-143", "/sec-144", "/sec-145", "/sec-146",
            "/sec-370", "/sec-370a", "/sec-371", "/sec-372", "/sec-373", "/sec-374",
        )),
        ("exploitation", (
            "sec-143", "sec-144", "sec-145", "sec-146",
            "sec-370", "sec-370a", "sec-371", "sec-372", "sec-373", "sec-374",
            "/sec-143", "/sec-144", "/sec-145", "/sec-146",
            "/sec-370", "/sec-370a", "/sec-371", "/sec-372", "/sec-373", "/sec-374",
        )),
        ("beat", ("sec-115", "sec-117", "sec-118", "sec-323", "sec-325", "sec-326", "/sec-115", "/sec-117", "/sec-118", "/sec-323", "/sec-325", "/sec-326")),
        ("beaten", ("sec-115", "sec-117", "sec-118", "sec-323", "sec-325", "sec-326", "/sec-115", "/sec-117", "/sec-118", "/sec-323", "/sec-325", "/sec-326")),
        ("hit", ("sec-115", "sec-117", "sec-118", "sec-323", "sec-325", "sec-326", "/sec-115", "/sec-117", "/sec-118", "/sec-323", "/sec-325", "/sec-326")),
        ("slap", ("sec-115", "sec-117", "sec-118", "sec-323", "sec-325", "sec-326", "/sec-115", "/sec-117", "/sec-118", "/sec-323", "/sec-325", "/sec-326")),
        ("hurt", ("sec-115", "sec-117", "sec-118", "sec-323", "sec-325", "sec-326", "/sec-115", "/sec-117", "/sec-118", "/sec-323", "/sec-325", "/sec-326")),
        ("injury", ("sec-115", "sec-117", "sec-118", "sec-323", "sec-325", "sec-326", "/sec-115", "/sec-117", "/sec-118", "/sec-323", "/sec-325", "/sec-326")),
        ("assault", ("sec-115", "sec-117", "sec-118", "sec-74", "sec-75", "sec-323", "sec-325", "sec-326", "sec-354", "sec-354a", "/sec-115", "/sec-117", "/sec-118", "/sec-74", "/sec-75", "/sec-323", "/sec-325", "/sec-326", "/sec-354", "/sec-354a")),
    ]
    anchors: list[str] = []
    for term, term_anchors in groups:
        if term in blob:
            anchors.extend(anchor for anchor in term_anchors if anchor not in anchors)
    return tuple(anchors)


def _is_pmla_sc_precedent_requirement(required_lower: str) -> bool:
    return (
        "pmla" in required_lower
        and ("supreme court" in required_lower or "precedent" in required_lower)
    )


def _pmla_sc_precedent_item_matches(item_blob: str) -> bool:
    return (
        (
            "sc_judgment" in item_blob
            or "supreme court" in item_blob
            or re.search(r"(?<![a-z0-9])20\d{2}-insc", item_blob) is not None
        )
        and _has_any(item_blob, (
            "pmla", "money laundering", "prevention of money laundering",
            "vijay madanlal", "nikesh tarachand", "pankaj bansal",
            "senthil balaji", "saumya chaurasia", "tarsem lal",
        ))
    )


def _has_delhi_prison_query_context(query: str) -> bool:
    if any(term in query for term in (
        "tihar", "mandoli", "rohini jail", "rohini prison",
        "delhi jail", "delhi prison", "central jail delhi",
    )):
        return True
    return "delhi" in query and any(term in query for term in (
        "jail", "prison", "prisoner", "mulaqat", "mulakat",
        "parole", "furlough", "superintendent",
    ))


def _is_state_prison_manual_requirement(text: str) -> bool:
    lower = text.lower()
    return any(term in lower for term in (
        "prison rules", "prison manual", "state prison", "prison/parole/furlough",
        "jail manual", "state parole/furlough",
    ))


def _is_delhi_prison_rules_item(item: dict[str, Any]) -> bool:
    blob = _item_blob(item)
    title = str(item.get("title") or "").lower()
    anchor = str(item.get("anchor") or "").lower()
    return ("delhi prison rules" in title or "delhi prison rules" in blob) and "delhi-prison-rules-2018" in anchor


def _looks_like_authority_requirement(text: str) -> bool:
    lower = text.lower()
    return bool(
        re.search(
            r"\b(?:act|articles?|authority|bns|bnss|code|constitution|constitutional|consumer|"
            r"crpc|ipc|ndps|pmla|pocso|ombudsman|regulations?|rules?|schemes?|"
            r"sections?|statute|tribunal)\b",
            lower,
        )
    )


def _source_coverage_tokens(text: str) -> set[str]:
    tokens = {
        token
        for token in re.findall(r"[a-z0-9]{2,}", text.lower())
        if token not in _SOURCE_COVERAGE_STOPWORDS
    }
    return tokens


def _source_coverage_score(required_tokens: set[str], item_blob: str) -> float:
    if not required_tokens:
        return 0.0
    normalized_blob = re.sub(r"[^a-z0-9]+", " ", item_blob.lower())
    blob_tokens = set(re.findall(r"[a-z0-9]{2,}", normalized_blob))
    if not blob_tokens:
        return 0.0

    def token_hit(token: str) -> bool:
        if token in blob_tokens or token in normalized_blob:
            return True
        return any(alias in normalized_blob for alias in _SOURCE_COVERAGE_TOKEN_ALIASES.get(token, ()))

    hits = sum(1 for token in required_tokens if token_hit(token))
    return hits / max(1, len(required_tokens))


def _source_coverage_threshold(tokens: set[str]) -> float:
    if len(tokens) <= 2:
        return 1.0
    if len(tokens) <= 4:
        return 0.5
    return 0.35


def cited_source_items(
    sources: list[dict[str, Any]],
    passages: list[dict[str, Any]],
    sentences: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    return [
        compact_source_item(item)
        for item in cited_source_records_for_sentences(sources, passages, sentences)
    ]


def cited_source_records_for_sentences(
    sources: list[dict[str, Any]],
    passages: list[dict[str, Any]],
    sentences: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Return raw cited records so provenance checks see every source field."""
    cited_indices = _cited_source_indices(sentences)
    if not cited_indices:
        return []
    by_index: dict[int, dict[str, Any]] = {}
    for item in [*(sources or []), *(passages or [])]:
        if not isinstance(item, dict):
            continue
        idx = item.get("index")
        if isinstance(idx, int) and idx not in by_index:
            by_index[idx] = item
    return [by_index[idx] for idx in sorted(cited_indices) if idx in by_index]


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


def product_pass(row: dict[str, Any]) -> bool:
    """Strict row-level gate for user-visible product quality diagnostics.

    This intentionally combines existing automated signals instead of replacing
    human review: the row must answer, stay on-topic, avoid legal-safety hard
    fails, cite the expected controlling authority when the prompt declares one,
    and avoid unfilled must-cite route source slots.
    """
    if (
        row.get("refused")
        or row.get("error")
        or row.get("internal_service_error")
        or row.get("source_gap_outcome") == "source_gap_handoff"
    ):
        return False
    if matter_plan_applicable_for_eval(row) and not (row.get("matter_plan_contract") or {}).get("valid"):
        return False
    if row.get("relevance_verdict") != "ok":
        return False
    if (row.get("legal_safety") or {}).get("hard_fail"):
        return False
    if row.get("expected_act_cited_hit") is False:
        return False
    if int(row.get("unknown_citation_count") or 0) > 0:
        return False
    if row.get("route_required_sources_missing"):
        return False
    if row.get("route_required_sources_cited_missing"):
        return False
    if row.get("plan_authority_ids_missing"):
        return False
    if row.get("plan_authority_ids_uncited"):
        return False
    if row.get("source_gap_visible"):
        return False
    return True


def _rows_summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    if not rows:
        return {
            "rows": 0,
            "product_pass": 0,
            "relevance_ok": 0,
            "safety_hard_fails": 0,
            "act_cited_hits": 0,
            "act_cited_scored": 0,
            "route_source_gaps": 0,
            "route_source_citation_gaps": 0,
            "plan_authority_rows": 0,
            "plan_authority_retrieval_gaps": 0,
            "plan_authority_citation_gaps": 0,
            "matter_plan_contract_failures": 0,
            "visible_source_gaps": 0,
            "source_gap_handoffs": 0,
            "refused": 0,
            "errors": 0,
            "internal_service_errors": 0,
            "p90_total_ms": None,
        }
    scored_cited = [r for r in rows if r.get("expected_act_cited_hit") is not None]
    total_vals = [
        float((r.get("timing") or {}).get("total_ms") or r.get("wall_ms"))
        for r in rows
        if isinstance((r.get("timing") or {}).get("total_ms") or r.get("wall_ms"), int | float)
    ]
    return {
        "rows": len(rows),
        "product_pass": sum(1 for r in rows if product_pass(r)),
        "relevance_ok": sum(1 for r in rows if r.get("relevance_verdict") == "ok"),
        "safety_hard_fails": sum(1 for r in rows if (r.get("legal_safety") or {}).get("hard_fail")),
        "act_cited_hits": sum(1 for r in scored_cited if r.get("expected_act_cited_hit")),
        "act_cited_scored": len(scored_cited),
        "route_source_gaps": sum(1 for r in rows if r.get("route_required_sources_missing")),
        "route_source_citation_gaps": sum(1 for r in rows if r.get("route_required_sources_cited_missing")),
        "plan_authority_rows": sum(
            1 for r in rows
            if (r.get("plan_authority_retrieval_coverage") or {}).get("applicable")
        ),
        "plan_authority_retrieval_gaps": sum(1 for r in rows if r.get("plan_authority_ids_missing")),
        "plan_authority_citation_gaps": sum(1 for r in rows if r.get("plan_authority_ids_uncited")),
        "matter_plan_contract_failures": sum(
            1 for r in rows
            if matter_plan_applicable_for_eval(r)
            and not (r.get("matter_plan_contract") or {}).get("valid")
        ),
        "visible_source_gaps": sum(1 for r in rows if r.get("source_gap_visible")),
        "source_gap_handoffs": sum(
            1 for r in rows if r.get("source_gap_outcome") == "source_gap_handoff"
        ),
        "refused": sum(1 for r in rows if r.get("refused")),
        "errors": sum(1 for r in rows if r.get("error") or r.get("internal_service_error")),
        "internal_service_errors": sum(1 for r in rows if r.get("internal_service_error")),
        "p90_total_ms": percentile(total_vals, 0.90),
    }


def _append_slice_table(
    lines: list[str],
    title: str,
    rows: list[dict[str, Any]],
    key: str,
    *,
    limit: int | None = None,
) -> None:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[str(row.get(key) or "unspecified")].append(row)
    lines.extend([
        "",
        f"### {title}",
        "",
        "| slice | rows | product pass | relevance ok | safety hard fails | expected Act cited | route retrieval gaps | route citation gaps | plan retrieval gaps | plan citation gaps | plan contract fails | visible source gaps | refused | errors | p90 |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ])
    items = sorted(grouped.items(), key=lambda item: (-len(item[1]), item[0]))
    if limit is not None:
        items = items[:limit]
    for name, slice_rows in items:
        summary = _rows_summary(slice_rows)
        act_cited = (
            f"{summary['act_cited_hits']}/{summary['act_cited_scored']}"
            if summary["act_cited_scored"]
            else "n/a"
        )
        lines.append(
            f"| {_clip(name, 60)} | {summary['rows']} | {summary['product_pass']}/{summary['rows']} | "
            f"{summary['relevance_ok']}/{summary['rows']} | {summary['safety_hard_fails']} | "
            f"{act_cited} | {summary['route_source_gaps']} | {summary['route_source_citation_gaps']} | "
            f"{summary['plan_authority_retrieval_gaps']} | {summary['plan_authority_citation_gaps']} | "
            f"{summary['matter_plan_contract_failures']} | {summary['visible_source_gaps']} | {summary['refused']} | "
            f"{summary['errors']} | {fmt_ms(summary['p90_total_ms'])} |"
        )
    if not items:
        lines.append("| none | 0 | 0/0 | 0/0 | 0 | n/a | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | n/a |")


def write_report(rows: list[dict[str, Any]], out: Path, report: Path) -> None:
    scored_act = [r for r in rows if r["expected_act_hit"] is not None]
    unscored_act = [r for r in rows if r["expected_act_hint"] and r["expected_act_hit"] is None]
    act_hits = sum(1 for r in scored_act if r["expected_act_hit"])
    scored_cited_act = [r for r in rows if r.get("expected_act_cited_hit") is not None]
    cited_act_hits = sum(1 for r in scored_cited_act if r.get("expected_act_cited_hit"))
    refused = sum(1 for r in rows if r["refused"])
    transport_errors = sum(1 for r in rows if r["error"])
    internal_service_errors = sum(1 for r in rows if r.get("internal_service_error"))
    errors = sum(
        1
        for r in rows
        if r["error"] or r.get("internal_service_error")
    )
    verdicts = Counter(r["relevance_verdict"] or ("refused" if r["refused"] else "no_relevance") for r in rows)
    routes = Counter(r["route_category"] or "unknown" for r in rows)
    action_packs = Counter(r["action_pack_id"] or "none" for r in rows)
    workflows = Counter(r.get("workflow_id") or "none" for r in rows)
    workflow_owners = Counter(r.get("workflow_answer_owner") or "unknown" for r in rows)
    workflow_modes = Counter(r.get("workflow_answer_mode") or "unknown" for r in rows)
    workflow_miss_reasons = Counter(r.get("workflow_contract_miss_reason") or "none" for r in rows)
    workflow_shadowed_by_legacy = sum(1 for r in rows if r.get("workflow_shadowed_by_legacy") is True)
    route_source_gaps = [
        r for r in rows if r.get("route_required_sources_missing")
    ]
    route_source_citation_gaps = [
        r for r in rows if r.get("route_required_sources_cited_missing")
    ]
    visible_source_gap_rows = [
        r for r in rows if r.get("source_gap_visible")
    ]
    plan_authority_rows = [
        r for r in rows
        if (r.get("plan_authority_retrieval_coverage") or {}).get("applicable")
    ]
    plan_authority_retrieval_gaps = [
        r for r in plan_authority_rows if r.get("plan_authority_ids_missing")
    ]
    plan_authority_citation_gaps = [
        r for r in plan_authority_rows if r.get("plan_authority_ids_uncited")
    ]
    matter_plan_contract_failures = [
        r for r in rows
        if matter_plan_applicable_for_eval(r)
        and not (r.get("matter_plan_contract") or {}).get("valid")
    ]
    matter_plan_required_rows = [
        r for r in rows
        if matter_plan_applicable_for_eval(r)
    ]
    plan_authority_required_count = sum(
        len(r.get("plan_authority_ids_required") or []) for r in plan_authority_rows
    )
    plan_authority_retrieved_count = sum(
        len(r.get("plan_authority_ids_retrieved") or []) for r in plan_authority_rows
    )
    plan_authority_cited_count = sum(
        len(r.get("plan_authority_ids_cited") or []) for r in plan_authority_rows
    )
    route_source_gap_kinds = Counter(
        str(item.get("kind") or "unknown")
        for r in route_source_gaps
        for item in (r.get("route_required_source_gap_classifications") or [])
        if isinstance(item, dict)
    )
    unknown_citation_rows = [
        r for r in rows if int(r.get("unknown_citation_count") or 0) > 0
    ]
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
    answered_rows = [
        r for r in rows
        if not r["refused"]
        and not r["error"]
        and r.get("sentence_count")
        and r.get("source_gap_outcome") != "source_gap_handoff"
    ]
    source_gap_handoffs = sum(
        1 for r in rows if r.get("source_gap_outcome") == "source_gap_handoff"
    )
    first_actionable = sum(1 for r in answered_rows if r.get("first_cited_is_actionable") is True)
    judgment_before_actionable = sum(1 for r in answered_rows if r.get("judgment_before_actionable_source") is True)
    template_path_rows = [r for r in rows if _generation_path(r) == "template_or_rule"]
    llm_path_rows = [r for r in rows if _generation_path(r) == "llm"]
    product_pass_rows = sum(1 for r in rows if product_pass(r))
    critical_rows = [r for r in rows if str(r.get("product_priority") or "").lower() == "critical"]
    critical_pass_rows = sum(1 for r in critical_rows if product_pass(r))
    runtime_fingerprints = sorted({
        str(r.get("runtime_fingerprint"))
        for r in rows
        if r.get("runtime_fingerprint")
    })

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
        f"Runtime fingerprint(s): `{', '.join(runtime_fingerprints) or 'missing'}`",
        "",
        "## Outcome",
        "",
        f"- Refused: {refused}/{len(rows)}",
        f"- Source-gap handoffs (non-answers): {source_gap_handoffs}/{len(rows)}",
        f"- Errors: {errors}/{len(rows)}",
        f"- Transport errors: {transport_errors}/{len(rows)}",
        f"- Internal service errors hidden behind safe handoff: {internal_service_errors}/{len(rows)}",
        f"- Relevance verdicts: {dict(verdicts)}",
        f"- Expected Act hit: {act_hits}/{len(scored_act)} ({(act_hits / len(scored_act) * 100) if scored_act else 0:.1f}%)",
        f"- Expected Act cited hit: {cited_act_hits}/{len(scored_cited_act)} ({(cited_act_hits / len(scored_cited_act) * 100) if scored_cited_act else 0:.1f}%)",
        f"- Expected Act unscored: {len(unscored_act)}/{len(rows)}",
        f"- Strict product pass: {product_pass_rows}/{len(rows)} ({(product_pass_rows / len(rows) * 100) if rows else 0:.1f}%)",
        f"- Critical strict pass: {critical_pass_rows}/{len(critical_rows)} ({(critical_pass_rows / len(critical_rows) * 100) if critical_rows else 0:.1f}%)",
        f"- Expected procedure anchor cited coverage: {procedure_cited_ok}/{len(procedure_coverages)} ({(procedure_cited_ok / len(procedure_coverages) * 100) if procedure_coverages else 0:.1f}%)",
        f"- First cited source actionable: {first_actionable}/{len(answered_rows)} ({(first_actionable / len(answered_rows) * 100) if answered_rows else 0:.1f}%)",
        f"- Judgment before actionable source: {judgment_before_actionable}/{len(answered_rows)}",
        f"- Unknown citation indices: {len(unknown_citation_rows)}/{len(rows)}",
        f"- Route required-source retrieval gaps: {len(route_source_gaps)}/{len(rows)}",
        f"- Route required-source citation gaps: {len(route_source_citation_gaps)}/{len(rows)}",
        f"- MatterPlan contract valid: {len(matter_plan_required_rows) - len(matter_plan_contract_failures)}/{len(matter_plan_required_rows)} applicable answer rows",
        f"- MatterPlan not applicable on safe source-gap handoffs: {sum(1 for r in rows if safe_source_gap_handoff_for_eval(r))}/{len(rows)}",
        f"- MatterPlan authority-obligation retrieval: {plan_authority_retrieved_count}/{plan_authority_required_count} authority obligations ({len(plan_authority_retrieval_gaps)} rows with gaps)",
        f"- MatterPlan authority-obligation citation: {plan_authority_cited_count}/{plan_authority_required_count} authority obligations ({len(plan_authority_citation_gaps)} rows with gaps)",
        f"- Visible source-gap warnings: {len(visible_source_gap_rows)}/{len(rows)}",
        f"- Route source-gap kinds: {dict(route_source_gap_kinds)}",
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
        "## Generation Path Split",
        "",
        "Rows with near-zero `llm_stream_ms` are deterministic/template or rule-contract answers. Rows with non-zero `llm_stream_ms` exercised the LLM answer path.",
        "",
        "| path | rows | relevance ok | safety hard fails | expected Act cited | p50 total | p90 total | max total |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ])
    for path_name, path_rows in (
        ("template_or_rule", template_path_rows),
        ("llm", llm_path_rows),
    ):
        path_safety = summarize_safety(path_rows) if path_rows else {"hard_fails": 0}
        path_scored_cited = [r for r in path_rows if r.get("expected_act_cited_hit") is not None]
        path_cited_hits = sum(1 for r in path_scored_cited if r.get("expected_act_cited_hit"))
        path_relevance_ok = sum(1 for r in path_rows if r.get("relevance_verdict") == "ok")
        total_vals = [
            float((r.get("timing") or {}).get("total_ms") or r.get("wall_ms"))
            for r in path_rows
            if isinstance((r.get("timing") or {}).get("total_ms") or r.get("wall_ms"), int | float)
        ]
        lines.append(
            f"| {path_name} | {len(path_rows)} | {path_relevance_ok}/{len(path_rows)} | "
            f"{path_safety['hard_fails']} | {path_cited_hits}/{len(path_scored_cited)} | "
            f"{fmt_ms(percentile(total_vals, 0.50))} | {fmt_ms(percentile(total_vals, 0.90))} | "
            f"{fmt_ms(max(total_vals) if total_vals else None)} |"
        )

    lines.extend([
        "",
        "## Product Gate Slices",
        "",
        "Strict product pass requires: answered row, relevance ok, no legal-safety hard fail, expected Act cited when scored, no unknown citation index, complete retrieved and cited MatterPlan authority obligations (canonical or activated provisional), no missing enforced route source, no uncited enforced route source, and no visible source-gap warning.",
    ])
    _append_slice_table(lines, "By Priority", rows, "product_priority")
    _append_slice_table(lines, "By Eval Family", rows, "eval_family", limit=30)
    _append_slice_table(lines, "By Expected Category", rows, "expected_category", limit=30)

    lines.extend([
        "",
        "## MatterPlan Contract And Authority Failures",
        "",
        "| query | contract errors | missing retrieved authority IDs | uncited authority IDs |",
        "| --- | --- | --- | --- |",
    ])
    plan_failure_rows = [
        row for row in rows
        if (
            row in matter_plan_contract_failures
            or row.get("plan_authority_ids_missing")
            or row.get("plan_authority_ids_uncited")
        )
    ]
    for row in plan_failure_rows:
        lines.append(
            f"| {_clip(row.get('query'), 90)} | "
            f"{_clip(', '.join((row.get('matter_plan_contract') or {}).get('errors') or []), 80)} | "
            f"{_clip(', '.join(row.get('plan_authority_ids_missing') or []), 100)} | "
            f"{_clip(', '.join(row.get('plan_authority_ids_uncited') or []), 100)} |"
        )
    if not plan_failure_rows:
        lines.append("| none |  |  |  |")

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
        "## Workflow Diagnostics",
        "",
        f"Workflow contracts shadowed by legacy templates: {workflow_shadowed_by_legacy}/{len(rows)}",
        "",
        "| answer_owner | count |",
        "| --- | ---: |",
    ])
    for owner, count in workflow_owners.most_common():
        lines.append(f"| {owner} | {count} |")

    lines.extend([
        "",
        "| answer_mode | count |",
        "| --- | ---: |",
    ])
    for mode, count in workflow_modes.most_common():
        lines.append(f"| {mode} | {count} |")

    lines.extend([
        "",
        "| workflow | count |",
        "| --- | ---: |",
    ])
    for workflow, count in workflows.most_common():
        lines.append(f"| {workflow} | {count} |")

    lines.extend([
        "",
        "| contract_miss_reason | count |",
        "| --- | ---: |",
    ])
    for reason, count in workflow_miss_reasons.most_common():
        lines.append(f"| {reason} | {count} |")

    lines.extend([
        "",
        "## Route Required-Source Gaps",
        "",
        "| persona | route | kind | query | missing route source |",
        "| --- | --- | --- | --- | --- |",
    ])
    for r in route_source_gaps[:25]:
        classes = r.get("route_required_source_gap_classifications") or []
        if not classes:
            missing = "; ".join(str(item) for item in (r.get("route_required_sources_missing") or []))
            lines.append(
                f"| {r.get('persona')} | {r.get('route_category')} | unclassified_route_source_gap | "
                f"{_clip(r.get('query'))} | {_clip(missing, 180)} |"
            )
            continue
        for item in classes:
            if not isinstance(item, dict):
                continue
            lines.append(
                f"| {r.get('persona')} | {r.get('route_category')} | {item.get('kind')} | "
                f"{_clip(r.get('query'))} | {_clip(item.get('required_source'), 180)} |"
            )
    if not route_source_gaps:
        lines.append("| none | n/a | n/a | n/a | n/a |")

    lines.extend([
        "",
        "## Citation Integrity",
        "",
        "| persona | route | query | unknown indices |",
        "| --- | --- | --- | --- |",
    ])
    for r in unknown_citation_rows[:25]:
        lines.append(
            f"| {r.get('persona')} | {r.get('route_category')} | {_clip(r.get('query'))} | {r.get('unknown_citation_indices')} |"
        )
    if not unknown_citation_rows:
        lines.append("| none | n/a | n/a | [] |")

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


def _generation_path(row: dict[str, Any]) -> str:
    """Approximate whether an answer bypassed the LLM generation path.

    The API records `llm_stream_ms` as 0 for deterministic template/rule
    answers. A tiny epsilon avoids classifying timer noise as generation.
    """
    value = (row.get("timing") or {}).get("llm_stream_ms")
    if isinstance(value, int | float) and float(value) > 1.0:
        return "llm"
    return "template_or_rule"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--api", default="http://localhost:8000")
    parser.add_argument("--queries-dir", type=Path, default=ROOT / "data" / "eval_500")
    parser.add_argument("--limit", type=int, default=100)
    parser.add_argument("--seed", type=int, default=20260525)
    parser.add_argument("--timeout-s", type=int, default=180)
    parser.add_argument("--out", type=Path, default=None)
    parser.add_argument("--report", type=Path, default=None)
    parser.add_argument(
        "--expected-fingerprint",
        default=None,
        help="expected live API fingerprint; defaults to this worktree's fingerprint",
    )
    args = parser.parse_args()

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    out = args.out or ROOT / "data" / "processed" / f"timed_eval_100_{stamp}.jsonl"
    report = args.report or ROOT / "data" / "processed" / f"timed_eval_100_{stamp}.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    rows_in = load_eval_rows(args.queries_dir, limit=args.limit, seed=args.seed)
    if not rows_in:
        raise SystemExit(f"no eval rows found under {args.queries_dir}")

    runtime_health = fetch_runtime_health(args.api, timeout_s=min(args.timeout_s, 20))
    expected_fingerprint = args.expected_fingerprint or runtime_identity()["fingerprint"]
    if expected_fingerprint == "unknown":
        raise SystemExit("local worktree fingerprint is unavailable; refusing benchmark")
    if runtime_health["build_fingerprint"] != expected_fingerprint:
        raise SystemExit(
            "refusing benchmark: live API fingerprint does not match the evaluated "
            f"worktree (live={runtime_health['build_fingerprint']}, expected={expected_fingerprint})"
        )
    runtime_metadata = {
        "build_fingerprint": runtime_health["build_fingerprint"],
        "build_fingerprint_source": runtime_health.get("build_fingerprint_source"),
    }

    print(
        f"=== timed eval: {len(rows_in)} queries -> {out} "
        f"(runtime={runtime_metadata['build_fingerprint']}) ===",
        flush=True,
    )
    rows: list[dict[str, Any]] = []
    with out.open("w", encoding="utf-8") as f:
        for idx, eval_row in enumerate(rows_in, 1):
            observed = stream_answer(args.api, eval_row["query"], timeout_s=args.timeout_s)
            row = flatten_row(eval_row, observed, runtime=runtime_metadata)
            rows.append(row)
            f.write(jsonl_dumps(row) + "\n")
            f.flush()
            timing = row.get("timing") or {}
            outcome = (
                "ERR"
                if row["error"] or row.get("internal_service_error")
                else "REF"
                if row["refused"]
                else "GAP"
                if row.get("source_gap_outcome") == "source_gap_handoff"
                else row["relevance_verdict"] or "NO_REL"
            )
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
