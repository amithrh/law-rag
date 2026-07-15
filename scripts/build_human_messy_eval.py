#!/usr/bin/env python3
"""Build a fresh human-style prompt eval pack.

This does not pretend to be real production user logs. It takes the curated
eval inventory with expected Act hints and rewrites a balanced sample into
shorter, messier UI-style questions: fragments, typos, missing punctuation,
and "what can I do" endings. The expected hints are preserved so the timed
eval can still score retrieval/citation quality.

The generated rows also carry product-gate metadata. Without those fields a
fresh eval can report a deceptively clean route/must-term score even when the
UI answers feel generic to real users.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import random
import re
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from apps.api.matter_router import route_matter
from scripts.eval_timed_100 import expected_act_keys


PREFIXES = (
    "",
    "pls tell ",
    "what to do ",
    "need help, ",
    "urgent ",
    "sir ",
    "hi, ",
    "can u tell ",
    "i am confused ",
    "please help ",
)

SUFFIXES = (
    "",
    " what can i do",
    " how to complain",
    " need lawyer or police",
    " pls guide",
    " where to go",
    " is this legal",
    " any remedy",
    " can i file case",
    " what next",
)

REPLACEMENTS: tuple[tuple[str, str], ...] = (
    (r"\bcannot\b", "cant"),
    (r"\bcan not\b", "cant"),
    (r"\bdoesn't\b", "doesnt"),
    (r"\bdon't\b", "dont"),
    (r"\brefused\b", "not agreeing"),
    (r"\brefusing\b", "not agreeing"),
    (r"\bapplication\b", "appln"),
    (r"\bdocuments\b", "docs"),
    (r"\bdocument\b", "doc"),
    (r"\bcertificate\b", "cert"),
    (r"\bcomplaint\b", "complain"),
    (r"\bregister\b", "file"),
    (r"\bregistration\b", "regn"),
    (r"\bgovernment\b", "govt"),
    (r"\bofficer\b", "offcr"),
    (r"\bcompany\b", "cmpny"),
    (r"\bproperty\b", "prop"),
    (r"\bmonths\b", "mnths"),
    (r"\byears\b", "yrs"),
    (r"\bplease\b", "pls"),
)

BAD_ROUTE_CATEGORIES = {"", "unknown", "general_legal", "off_topic"}

CATEGORY_ROUTE_HINTS: tuple[tuple[tuple[str, ...], tuple[str, ...]], ...] = (
    (("cyber", "image_based_abuse", "deepfake", "sim_fraud"), ("cyber_fraud_or_harassment", "police_fir")),
    (("bank", "finance", "cibil", "loan_app"), ("banking_credit_dispute", "consumer")),
    (("consumer", "hospital_negligence", "e_commerce", "cab_aggregator"), ("consumer",)),
    (("fir", "police", "custodial", "arrest", "false_fir"), ("police_fir", "arrest_custody_safeguard")),
    (("false_charge", "bail", "ndps", "uapa", "pmla", "juvenile_age", "accused"), ("criminal_defence_bail",)),
    (("undertrial", "mulaqat", "parole", "furlough"), ("undertrial_review_release", "legal_aid")),
    (("domestic", "dowry", "streedhan", "economic_abuse"), ("family_domestic", "police_fir")),
    (("family", "marriage", "maintenance", "divorce", "alimony", "adultery"), ("family_marriage_status", "family_domestic")),
    (("custody", "adoption", "visitation"), ("child_custody_adoption", "family_marriage_status")),
    (("pocso", "sexual", "rape", "stalking", "acid", "harassment"), ("sexual_offence_survivor", "police_fir")),
    (("workplace_harassment", "posh"), ("workplace_sexual_harassment",)),
    (("wage", "employment", "epf", "esi", "gig", "contract_labour", "migrant"), ("employment_wages", "labour_exploitation_discrimination")),
    (("bonded", "child_labour", "manual_scavenging"), ("labour_exploitation_discrimination", "bonded_labour_rescue")),
    (("construction_accident", "labour_accident", "bocw"), ("workplace_injury_compensation", "employment_wages")),
    (("street_vendor",), ("street_vendor_municipal", "business_license_compliance")),
    (("shop_license", "food_license", "business", "compliance"), ("business_license_compliance",)),
    (("cheque_bounce",), ("cheque_bounce", "business_contract_partnership")),
    (("contract_breach", "msme", "partnership"), ("business_contract_partnership",)),
    (("ibc",), ("ibc_nclt",)),
    (("tax", "gst", "customs"), ("tax_gst_compliance",)),
    (("inheritance", "will", "gift_deed", "property", "land_revenue"), ("property_tenancy", "succession_inheritance")),
    (("tribal", "caste", "atrocity", "forest_rights", "pesa", "witch", "land_alienation"), ("tribal_caste_atrocity", "land_revenue_records")),
    (("senior", "elder"), ("senior_citizen",)),
    (("aadhaar", "pds", "pension", "welfare", "certificate", "identity"), ("social_welfare_identity",)),
    (("education", "school", "reserved_education"), ("education_rights", "social_welfare_identity")),
    (("disability",), ("disability_access",)),
    (("mental_health",), ("mental_health_care_rights",)),
    (("environment", "mining", "water"), ("environment_compensation",)),
    (("rti",), ("rti",)),
    (("procedure", "civil"), ("court_procedure", "legal_aid")),
)

CRITICAL_CATEGORY_TERMS = (
    "arrest", "custodial", "custody", "fir_refusal", "police", "bail", "ndps", "uapa", "pmla",
    "domestic_violence", "dowry_death", "trafficking", "itpa", "rape", "sexual", "pocso",
    "acid", "stalking", "child_marriage", "deepfake", "csam", "image_based_abuse",
    "cyber_privacy", "cyber_harassment", "cyber_fir", "bonded_labour", "manual_scavenging",
    "child_labour", "caste_atrocity", "witch_hunting", "land_alienation",
)

CRITICAL_QUERY_TERMS = (
    "arrest", "detained", "picked", "police took", "fir copy", "beating me", "unsafe",
    "threatening", "blackmail", "private photo", "deepfake", "minor", "child porn",
    "csam", "rape", "pocso", "bonded", "not letting leave", "witch", "atrocity",
)

ACT_MUST_TERMS: dict[str, tuple[str, ...]] = {
    "Aadhaar Act": ("aadhaar", "uidai"),
    "Banking Ombudsman": ("rbi", "ombudsman", "bank"),
    "BNSS": ("bnss", "fir", "magistrate", "police"),
    "BNS": ("bns", "police", "offence"),
    "BOCW Act": ("bocw", "construction", "labour"),
    "Bonded Labour Act": ("bonded labour", "release certificate", "district magistrate"),
    "Child Labour Act": ("child labour", "labour department"),
    "Code on Wages": ("wages", "labour", "commissioner"),
    "Consumer Protection Act": ("consumer", "district commission", "refund"),
    "Credit Information Companies Act": ("cibil", "credit information", "dispute"),
    "CGST Act": ("gst", "notice", "portal"),
    "CGST Rules": ("gst", "rule", "portal"),
    "CrPC": ("crpc", "fir", "magistrate", "police"),
    "Customs Act": ("customs", "notice", "appeal"),
    "Family Courts Act": ("family court", "maintenance", "divorce"),
    "FEMA": ("foreign exchange", "fema", "remittance"),
    "Forest Rights Act": ("forest rights", "gram sabha"),
    "Hindu Marriage Act": ("hindu marriage", "section 12", "divorce"),
    "Hindu Succession Act": ("succession", "legal heir", "partition"),
    "Income Tax Act": ("income tax", "itr", "notice"),
    "Information Technology Act": ("it act", "cyber", "electronic"),
    "Juvenile Justice Act": ("juvenile", "jj act", "child welfare"),
    "Legal Services Authorities Act": ("legal aid", "dlsa"),
    "MGNREGA": ("mgnrega", "job card", "wages"),
    "Motor Vehicles Act": ("motor", "maact", "insurance"),
    "NDPS Act": ("ndps", "bail", "quantity"),
    "NI Act": ("cheque", "138", "notice"),
    "POCSO": ("pocso", "minor", "special court"),
    "Prison Act": ("prison", "jail", "mulaqat"),
    "Prohibition of Child Marriage Act": ("legal age", "21", "18", "child marriage"),
    "POSH Act": ("posh", "internal committee", "local committee"),
    "PWDVA": ("domestic violence", "protection officer", "magistrate"),
    "PESA": ("pesa", "gram sabha", "scheduled area"),
    "PMLA": ("pmla", "ed", "bail"),
    "RTI Act": ("rti", "information officer"),
    "RERA": ("rera", "builder", "possession"),
    "RPwD Act": ("disability", "reasonable accommodation"),
    "SC/ST POA Act": ("sc/st", "atrocity", "special court"),
    "Senior Citizens Act": ("senior citizen", "maintenance tribunal"),
    "ESI Act": ("esi", "contribution", "employer"),
    "Shops and Establishments Act": ("shop", "licence", "establishment"),
    "Specific Relief Act": ("injunction", "specific relief"),
    "Street Vendors Act": ("street vendor", "town vending committee", "certificate"),
    "Transfer of Property Act": ("lease", "sale deed", "title"),
    "Trade Marks Act": ("trademark", "registry", "opposition"),
    "UAPA": ("uapa", "bail", "special court"),
    "National Food Security Act": ("ration", "nfsa", "dealer", "grievance"),
    "RFCTLARR Act": ("land acquisition", "compensation", "award", "authority"),
    "Mental Healthcare Act": ("mental health", "hospital", "board", "supported admission"),
}

CATEGORY_MUST_TERMS: tuple[tuple[tuple[str, ...], tuple[str, ...]], ...] = (
    (("bank", "finance", "cibil"), ("bank", "rbi", "ombudsman", "freeze", "lien")),
    (("cyber", "deepfake", "image_based_abuse"), ("cyber", "platform", "police", "it act", "takedown")),
    (("fir", "arrest", "custodial"), ("fir", "police", "magistrate", "legal aid")),
    (("bail", "false_charge", "ndps", "uapa", "pmla"), ("bail", "court", "lawyer", "fir")),
    (("domestic", "family", "marriage"), ("family court", "protection officer", "maintenance", "divorce")),
    (("wage", "employment", "labour"), ("wages", "labour", "employer", "commissioner")),
    (("street_vendor",), ("street vendor", "municipal", "town vending committee")),
    (("tribal", "caste", "forest", "pesa"), ("tribal", "gram sabha", "collector", "sc/st")),
    (("consumer", "hospital"), ("consumer", "district commission", "refund")),
    (("property", "land", "inheritance", "will"), ("civil court", "sale deed", "partition", "title")),
    (("welfare", "pension", "pds", "aadhaar"), ("aadhaar", "scheme", "grievance", "rti")),
    (("tax", "gst", "customs"), ("income tax", "gst", "notice", "portal", "appeal")),
)

EXACT_CATEGORY_MUST_TERMS: dict[str, tuple[str, ...]] = {
    "child_marriage": ("child marriage", "child marriage prohibition officer", "child welfare committee", "police", "magistrate"),
    "child_marriage_prevention": ("child marriage", "child marriage prohibition officer", "child welfare committee", "police", "magistrate"),
    "honour_threat": ("khap", "police protection", "dlsa", "high court", "article 21"),
    "itpa_subject_of_raid": ("itpa", "spa", "role", "fir", "dlsa", "custody"),
    "land_alienation": ("tribal", "non-tribal", "dc", "restoration", "scheduled area", "mutation", "deed"),
    "witch_hunting": ("witch", "daayan", "state act", "bns", "police"),
    "accused_cattle": ("cattle", "buffalo", "mandi", "state cattle", "fir", "bail"),
}


def read_rows(source: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for path in sorted(source.glob("*.jsonl")):
        persona = path.stem
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            row = json.loads(line)
            row.setdefault("persona", persona)
            rows.append(row)
    return rows


def balanced_sample(rows: list[dict[str, Any]], *, limit: int, seed: int) -> list[dict[str, Any]]:
    by_persona: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        by_persona[str(row.get("persona") or "unknown")].append(row)
    rng = random.Random(seed)
    for bucket in by_persona.values():
        rng.shuffle(bucket)

    selected: list[dict[str, Any]] = []
    personas = sorted(by_persona)
    cursors = {p: 0 for p in personas}
    while len(selected) < limit:
        progressed = False
        for persona in personas:
            idx = cursors[persona]
            if idx >= len(by_persona[persona]):
                continue
            selected.append(by_persona[persona][idx])
            cursors[persona] += 1
            progressed = True
            if len(selected) >= limit:
                break
        if not progressed:
            break
    return selected


def messy_query(query: str, *, idx: int, rng: random.Random) -> str:
    q = " ".join(query.strip().split())
    q = q.rstrip("?.!")
    if idx % 2 == 0:
        q = q[:1].lower() + q[1:]
    if idx % 5 == 0:
        q = q.replace(",", " ,")
    if idx % 7 == 0:
        q = q.replace(" and ", " n ")
    if idx % 11 == 0:
        q = q.replace(" for ", " fr ")
    if idx % 13 == 0:
        q = q.replace(" is ", " is ")

    for pattern, replacement in REPLACEMENTS:
        if rng.random() < 0.22:
            q = re.sub(pattern, replacement, q, flags=re.IGNORECASE)

    prefix = PREFIXES[idx % len(PREFIXES)]
    suffix = SUFFIXES[(idx * 3) % len(SUFFIXES)]
    q = f"{prefix}{q}{suffix}"
    q = re.sub(r"\s+", " ", q).strip()
    return q


def build(
    source: Path,
    out_dir: Path,
    *,
    limit: int,
    seed: int,
    filename: str | None = None,
    exclude_prompts: list[Path] | None = None,
    exclude_exact_prompts: list[Path] | None = None,
) -> Path:
    excluded_queries = load_excluded_source_queries(exclude_prompts or [])
    excluded_exact_queries = load_excluded_exact_queries(exclude_exact_prompts or [])
    source_rows = [
        row
        for row in read_rows(source)
        if normalize_query_for_exclusion(str(row.get("query") or "")) not in excluded_queries
    ]
    rows = balanced_sample(source_rows, limit=limit, seed=seed)
    if len(rows) < limit:
        raise SystemExit(
            f"only found {len(rows)} rows under {source} after exclusions, need {limit}"
        )

    rng = random.Random(seed + 17)
    used_output_queries = set(excluded_exact_queries)
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / (filename or f"human_messy_{limit}.jsonl")
    with out_path.open("w", encoding="utf-8") as f:
        for idx, row in enumerate(rows, 1):
            source_query = str(row["query"])
            metadata = product_metadata(row, source_query=source_query, source=source, idx=idx)
            query = None
            for attempt in range(200):
                variant_idx = idx + (attempt * 997)
                variant_rng = random.Random(seed + 17 + (idx * 1009) + (attempt * 7919))
                candidate = messy_query(source_query, idx=variant_idx, rng=variant_rng if attempt else rng)
                normalized_candidate = normalize_query_for_exclusion(candidate)
                if normalized_candidate not in used_output_queries:
                    used_output_queries.add(normalized_candidate)
                    query = candidate
                    break
            if query is None:
                raise SystemExit(f"could not generate unique messy query for row {idx}: {source_query}")
            out = {
                "query": query,
                **metadata,
                "expected_category": row.get("expected_category"),
                "expected_act_hint": row.get("expected_act_hint"),
                "is_accused_subject": bool(row.get("is_accused_subject")),
                "source_query": source_query,
                "eval_variant": "human_messy_v2",
                "generated_from": str(source),
                "synthetic_note": "human-like rewrite; not real user log",
                "excluded_prompt_sources": [str(path) for path in (exclude_prompts or [])],
                "excluded_exact_prompt_sources": [str(path) for path in (exclude_exact_prompts or [])],
            }
            f.write(json.dumps(out, ensure_ascii=False) + "\n")
    return out_path


def load_excluded_source_queries(paths: list[Path]) -> set[str]:
    excluded: set[str] = set()
    for path in paths:
        files = sorted(path.glob("*.jsonl")) if path.is_dir() else [path]
        for file in files:
            for line_no, line in enumerate(file.read_text(encoding="utf-8").splitlines(), start=1):
                if not line.strip():
                    continue
                row = json.loads(line)
                source_query = str(row.get("source_query") or row.get("query") or "")
                normalized = normalize_query_for_exclusion(source_query)
                if not normalized:
                    raise ValueError(f"{file}:{line_no}: excluded prompt row has no query/source_query")
                excluded.add(normalized)
    return excluded


def load_excluded_exact_queries(paths: list[Path]) -> set[str]:
    excluded: set[str] = set()
    for path in paths:
        files = sorted(path.glob("*.jsonl")) if path.is_dir() else [path]
        for file in files:
            for line_no, line in enumerate(file.read_text(encoding="utf-8").splitlines(), start=1):
                if not line.strip():
                    continue
                row = json.loads(line)
                query = str(row.get("query") or "")
                normalized = normalize_query_for_exclusion(query)
                if not normalized:
                    raise ValueError(f"{file}:{line_no}: excluded exact prompt row has no query")
                excluded.add(normalized)
    return excluded


def normalize_query_for_exclusion(query: str) -> str:
    return re.sub(r"\s+", " ", query.strip().lower())


def product_metadata(row: dict[str, Any], *, source_query: str, source: Path, idx: int) -> dict[str, Any]:
    persona = str(row.get("persona") or "unknown")
    category = str(row.get("expected_category") or "").strip()
    act_hint = str(row.get("expected_act_hint") or "")
    route = route_matter(source_query)
    return {
        "base_id": stable_base_id(source=source, persona=persona, idx=idx, query=source_query),
        "persona": f"human_messy_{persona}",
        "common_issue": common_issue(row, route_category=route.category),
        "product_priority": product_priority(category=category, query=source_query, route_category=route.category),
        "expected_route_any": expected_routes(category=category, query=source_query, route_category=route.category),
        "must_include_any": must_include_terms(category=category, query=source_query, act_hint=act_hint),
        "must_include_all": [],
    }


def stable_base_id(*, source: Path, persona: str, idx: int, query: str) -> str:
    digest = hashlib.sha1(f"{source}:{persona}:{idx}:{query}".encode("utf-8")).hexdigest()[:12]
    return f"hm2-{persona}-{idx:04d}-{digest}"


def common_issue(row: dict[str, Any], *, route_category: str) -> str:
    category = str(row.get("expected_category") or "").strip()
    if category:
        return category
    if route_category and route_category.lower() not in BAD_ROUTE_CATEGORIES:
        return route_category
    return str(row.get("persona") or "unknown")


def product_priority(*, category: str, query: str, route_category: str) -> str:
    blob = f"{category} {route_category} {query}".lower()
    if any(term in blob for term in CRITICAL_CATEGORY_TERMS) or any(term in blob for term in CRITICAL_QUERY_TERMS):
        return "critical"
    return "high"


def expected_routes(*, category: str, query: str, route_category: str) -> list[str]:
    blob = f"{category} {query}".lower()
    routes: list[str] = []
    for triggers, route_hints in CATEGORY_ROUTE_HINTS:
        if any(trigger_matches(blob, trigger) for trigger in triggers):
            routes.extend(route_hints)
    if route_category and route_category.lower() not in BAD_ROUTE_CATEGORIES:
        routes.append(route_category)
    return unique_preserving_order(routes) or [route_category or "general_legal"]


def trigger_matches(blob: str, trigger: str) -> bool:
    trigger = trigger.strip().lower()
    if not trigger:
        return False
    if re.fullmatch(r"[a-z0-9_]+", trigger):
        return re.search(rf"(?<![a-z0-9_]){re.escape(trigger)}(?![a-z0-9_])", blob) is not None
    return trigger in blob


def must_include_terms(*, category: str, query: str, act_hint: str) -> list[str]:
    blob = f"{category} {query} {act_hint}".lower()
    category_blob = f"{category} {act_hint}".lower()
    terms: list[str] = []
    category_key = category.strip().lower()
    if "gazette" in blob or "surname after marriage" in blob or "name change" in blob:
        return ["gazette", "affidavit", "newspaper", "name change", "documents"]
    if "form 11" in blob and ("llp" in blob or "limited liability partnership" in blob):
        return ["llp", "form 11", "annual return", "registrar", "strike off"]
    if "section 9" in blob and ("ibc" in blob or "operational creditor" in blob):
        return ["operational creditor", "section 9", "demand notice", "nclt", "dispute"]
    if "habeas" in blob or "detained illegally" in blob:
        return ["habeas", "high court", "detention", "police", "urgent"]
    if "no chargesheet" in blob or "no charge sheet" in blob or "no challan" in blob:
        return ["default bail", "chargesheet", "remand", "deadline", "court"]
    if "first appeal" in blob and "decree" in blob:
        return ["appeal", "decree", "limitation", "certified copy", "delay"]
    if "land taken" in blob and "compensation" in blob:
        return ["land acquisition", "compensation", "award", "authority", "collector"]
    if "mental" in blob and ("chains" in blob or "admit" in blob or "hospital" in blob):
        return ["mental health", "hospital", "board", "supported admission", "rights"]
    if (
        ("trademark" in blob or "trade mark" in blob or "brand name" in blob)
        and any(term in blob for term in (
            "prior user", "prior use", "already using", "using for", "using since",
            "used for", "used since", "competitor registered", "registered first",
            "registered my brand", "registered our brand",
        ))
    ):
        return ["trademark", "prior user", "rectification", "registry", "passing off"]
    if "non compete" in blob or "non-compete" in blob or "restraint of trade" in blob:
        return ["non-compete", "section 27", "contract", "employer legal notice", "injunction"]
    if "silicosis" in blob or ("quarry" in blob and any(term in blob for term in ("lungs", "cough", "dust"))):
        return ["silicosis", "quarry", "occupational disease", "compensation", "medical"]
    if category_key in {"family", "family_marriage_status"} and any(
        term in blob for term in ("legal age", "age legal", "marriage age", "got married")
    ):
        return ["legal age", "21", "18", "child marriage", "consent"]
    if category_key == "mulaqat_visit" or any(term in blob for term in ("mulaqat", "mulakat", "tihar", "prison books")):
        return ["prison", "jail", "mulaqat", "books", "superintendent"]
    if "fanvue" in blob or ("creator" in blob and any(term in blob for term in ("payout", "payment frozen", "usd"))):
        return ["platform", "payout", "foreign exchange", "income tax", "gst", "bank"]
    if category_key in {"employment", "wage_theft", "employment_wages"} and any(
        term in blob for term in ("notice period", "offer letter", "90 day", "60 day", "appointment letter")
    ):
        return ["notice period", "offer letter", "60 days", "90 days", "hr", "contract"]
    if category_key == "inheritance" and any(term in blob for term in ("christian", "widow", "stepchildren", "step children")):
        return ["succession", "widow", "stepchildren", "lineal descendants", "civil"]
    if category_key == "civil" and any(term in blob for term in ("society", "pet", "fine", "rwa")):
        return ["civil", "society", "cooperative", "fine", "pet"]
    for key in expected_act_keys(act_hint, query):
        terms.extend(ACT_MUST_TERMS.get(key, ()))
    exact_terms = list(EXACT_CATEGORY_MUST_TERMS.get(category.strip().lower(), ()))
    if category.strip().lower() == "cab_aggregator" and any(
        term in blob for term in ("traffic police", "no challan", "license", "licence", "permit")
    ):
        exact_terms = ["traffic police", "challan", "licence", "license", "corruption", "rto"]
    if exact_terms:
        terms.extend(exact_terms)
    else:
        for triggers, route_terms in CATEGORY_MUST_TERMS:
            if any(trigger_matches(category_blob, trigger) for trigger in triggers):
                terms.extend(route_terms)
    if "deepfake" in blob:
        terms.extend(("deepfake", "takedown", "cyber"))
    if "loan app" in blob:
        terms.extend(("loan app", "rbi", "cyber", "contacts"))
    if "account" in blob and any(term in blob for term in ("freeze", "frozen", "lien")):
        terms.extend(("freeze", "lien", "bank", "police"))
    if not terms and category:
        terms.extend(term for term in re.split(r"[_\W]+", category) if len(term) >= 4)
    return unique_preserving_order(terms)[:12]


def unique_preserving_order(items: list[str] | tuple[str, ...]) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for item in items:
        value = str(item).strip()
        key = value.lower()
        if not value or key in seen:
            continue
        seen.add(key)
        out.append(value)
    return out


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=ROOT / "data" / "eval_500")
    parser.add_argument("--out-dir", type=Path, default=ROOT / "data" / "eval_human_messy_200")
    parser.add_argument("--limit", type=int, default=200)
    parser.add_argument("--seed", type=int, default=20260531)
    parser.add_argument("--filename", default=None)
    parser.add_argument(
        "--exclude-prompts",
        type=Path,
        action="append",
        default=[],
        help="Prompt JSONL file or directory whose source_query/query rows must not be reused.",
    )
    parser.add_argument(
        "--exclude-exact-prompts",
        type=Path,
        action="append",
        default=[],
        help="Prompt JSONL file or directory whose exact generated query text must not be reused.",
    )
    args = parser.parse_args()

    out_path = build(
        args.source,
        args.out_dir,
        limit=args.limit,
        seed=args.seed,
        filename=args.filename,
        exclude_prompts=args.exclude_prompts,
        exclude_exact_prompts=args.exclude_exact_prompts,
    )
    print(out_path)


if __name__ == "__main__":
    main()
