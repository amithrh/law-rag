"""User-visible source-gap helpers for the answer API.

The eval stack can diagnose missing route-required authority after the fact.
This module exposes the same product idea at runtime: if a route says a
controlling source is required but the answer source window does not contain
it, the API can tell the user instead of quietly letting a neighboring source
stand in for it.
"""
from __future__ import annotations

import re
from typing import Any

from apps.api.legal_issue_plan import MatterPlan, authority_ids_for_passage
from apps.api.customs_logic import (
    customs_assessment_issue,
    customs_classification_issue,
    customs_drawback_issue,
    customs_misdeclaration_issue,
    customs_svb_issue,
)


_STOPWORDS = {
    "a", "an", "and", "as", "based", "be", "for", "in", "is", "of", "on",
    "or", "procedure", "relevant", "route", "section", "sections", "source",
    "sources", "state", "the", "to", "where", "with",
}

_FAMILY_PERSONAL_LAW_TRIGGER_TERMS = (
    "matrimonial", "annulment", "annul", "void marriage",
    "voidable", "divorce", "separation", "restitution", "conjugal",
    "second wife", "second husband", "second marriage", "bigamy", "maintenance",
    "alimony", "streedhan", "stridhan", "custody", "child custody",
    "guardianship", "personal law", "hindu marriage", "special marriage",
    "muslim marriage", "before marriage", "lied before marriage",
)

_MAINTENANCE_TRIGGER_TERMS = (
    "maintenance", "alimony", "child support", "interim maintenance",
    "monthly support", "support order", "section 125", "sec 125",
    "125 crpc", "144 bnss", "not paying maintenance", "maintenance case",
)

_CRIMINAL_PROCESS_TRIGGER_TERMS = (
    "fir", "f.i.r", "arrest", "arrested", "detain", "detained",
    "custody", "lockup", "lock-up", "picked", "station",
    "police station", "police notice", "police called", "police calling",
    "police came", "police visit", "police asked", "police took",
    "police picked", "police arrested", "police refusing",
    "police refused", "police not filing", "police filed",
    "police case", "police complaint",
    "bail", "anticipatory", "regular bail", "interim bail",
    "default bail", "surety", "remand", "chargesheet", "charge sheet",
    "notice", "summons", "warrant", "magistrate", "complaint",
    "criminal court", "accused", "case against me", "case on me",
)

_CRIMINAL_OFFENCE_TRIGGER_TERMS = (
    "acid", "assault", "attack", "beat", "beaten", "blackmail",
    "cheating", "cruelty", "dacoity", "dowry", "extortion", "forgery",
    "forged", "fraud", "harass", "harassment", "hurt", "intimidation",
    "kidnap", "murder", "ndps", "pocso", "rape", "sexual assault",
    "stalk", "stalking", "threat", "threaten", "threatening", "theft",
    "stolen", "trafficking", "uapa", "violence", "witch", "wrongful",
    "confine", "confinement", "locked", "not letting leave", "forced",
    "fake register", "false register", "fake case", "false fir",
    "blank paper", "thumb impression", "false document", "fake document",
    "drug parcel", "drug dealer", "mdma", "ganja", "charas", "cocaine",
    "heroin", "narcotic", "contraband", "psychotropic",
)

_GENERAL_CRIMINAL_OFFENCE_TRIGGER_TERMS = tuple(
    term for term in _CRIMINAL_OFFENCE_TRIGGER_TERMS
    if term not in {"ndps", "uapa", "pocso"}
)

_PHYSICAL_STALKING_THREAT_TRIGGER_TERMS = (
    "assault", "attack", "beat", "beaten", "hit", "hurt", "injury",
    "injured", "slap", "slapped", "touch", "touched", "grop", "molest",
    "stalk", "stalking", "follow", "following", "threat", "threaten",
    "threatening", "intimidat", "force", "forced", "coercion", "confine",
    "locked", "not letting", "acid", "knife", "weapon",
)

_LIMITATION_TRIGGER_TERMS = (
    "delay", "delayed", "late", "limitation", "time limit", "deadline",
    "appeal period", "appeal deadline", "after 30 days", "after 60 days",
    "after 90 days", "after 120 days", "condonation", "time barred",
    "time-barred", "years back", "months late", "execution delay",
)

_PESA_TRIGGER_TERMS = (
    "pesa", "gram sabha", "scheduled area", "fifth schedule",
    "tribal village", "mining", "bauxite", "displacement", "noc",
    "land acquisition", "rehabilitation",
)

_FRA_TRIGGER_TERMS = (
    "forest", "forest right", "forest rights", "fra", "ifr", "cfr",
    "patta", "tendu", "bamboo", "minor forest produce", "mfp",
    "forest guard", "van adhikar",
)

def _has_adoption_source_context(q: str) -> bool:
    return (
        _has(q, ("adoption", "adopted", "adoptive", "cara", "relative adoption"))
        or re.search(r"(?<![a-z0-9])adopt(?:s|ing|er|ers)?(?![a-z0-9])", q) is not None
    )


def _has_criminal_process_context(q: str) -> bool:
    return _has_trigger_term(q, _CRIMINAL_PROCESS_TRIGGER_TERMS)


def _has_criminal_offence_context(q: str) -> bool:
    if _has(q, _GENERAL_CRIMINAL_OFFENCE_TRIGGER_TERMS):
        return True
    return (
        re.search(r"\b(?:sec(?:tion)?\.?\s*)\d{2,3}[a-z]?\b", q) is not None
        and _has(q, ("bns", "ipc"))
    ) or re.search(r"\b(?:bns|ipc)\s*\d{2,3}[a-z]?\b|\b\d{2,3}[a-z]?\s*(?:bns|ipc)\b", q) is not None


def _has_streedhan_or_entrustment_context(q: str) -> bool:
    return _has(q, (
        "streedhan", "stridhan", "jewellery", "jewelry", "gold",
        "wedding jewellery", "wedding jewelry", "in laws not returning",
        "in-laws not returning", "not returning my jewellery",
        "not returning my jewelry", "not returning my gold",
        "refusing to return", "refused to return", "kept my jewellery",
        "kept my jewelry", "entrusted jewellery", "entrusted jewelry",
    ))


def _has_trafficking_exploitation_context(q: str) -> bool:
    return _has(q, (
        "trafficking", "exploitation", "sex work", "sex worker",
        "brothel", "spa raid", "spa was raided", "spa raided",
        "massage parlour", "massage parlor", "massage centre",
        "massage center", "massage girls", "police took me and other girls",
        "girls to station", "women to station", "rescued from spa",
        "itpa raid", "raid at spa", "raided last week",
        "customers want extra", "owner makes us", "if we refuse no salary",
        "forced sexual exploitation",
    ))


def _has_police_threatening_arrest_without_offence_context(q: str) -> bool:
    police_threat = _has(q, (
        "police still threatening to arrest",
        "police threatening to arrest",
        "police threatened arrest",
        "threatening to arrest",
    ))
    bail_order = _has(q, (
        "anticipatory bail granted", "bail granted", "granted bail",
        "bail order", "high court granted bail", "hc granted bail",
    ))
    explicit_offence = _has(q, (
        "rape", "murder", "theft", "stolen", "cheating", "fraud",
        "forgery", "dowry", "cruelty", "assault", "hit", "beat",
        "ndps", "pocso", "uapa", "extortion", "blackmail",
        "section ", "sec ", "bns ", "ipc ",
    ))
    return police_threat and bail_order and not explicit_offence


def _has_physical_stalking_threat_context(q: str) -> bool:
    if _has_negated_family_criminal_force_context(q):
        return False
    return _has(q, _PHYSICAL_STALKING_THREAT_TRIGGER_TERMS)


def _has_limitation_trigger_context(q: str) -> bool:
    return _has(q, _LIMITATION_TRIGGER_TERMS) or re.search(r"\b\d+\s+(?:year|years|month|months|day|days)\s+(?:late|delay|after)\b", q) is not None


def _has_pesa_trigger_context(q: str) -> bool:
    non_scheduled = _has(q, ("non scheduled", "non-scheduled"))
    return _has(q, _PESA_TRIGGER_TERMS) and not non_scheduled


def _has_fra_trigger_context(q: str) -> bool:
    return _has(q, _FRA_TRIGGER_TERMS)


def build_source_gap_event(
    *,
    query: str,
    route_category: str,
    required_sources: list[str],
    passages: list[dict[str, Any]],
    plan: MatterPlan | None = None,
) -> dict[str, Any] | None:
    if (
        plan is not None
        and plan.answer_policy.fallback_reason == "multiple_plan_owners"
    ):
        return {
            "has_gap": True,
            "route_category": route_category,
            "gap_kinds": ["answer_owner_ambiguity"],
            "missing_required_sources": [],
            "message": (
                "Your question contains more than one legal problem that needs a "
                "different reviewed answer path. I will not combine them into one "
                "possibly misleading answer. Ask one issue at a time or use legal-aid "
                "intake to separate the immediate problem and next step."
            ),
            "handoff": "DLSA/legal aid, a qualified lawyer, or the relevant court/forum",
            "policy": "separate_conflicting_answer_owners",
            "conflicting_primary_owners": list(
                plan.answer_policy.conflicting_primary_owners
            ),
        }
    missing = (
        missing_plan_authorities(plan=plan, passages=passages, query=query)
        if plan is not None
        else missing_required_authorities(
            required_sources=required_sources,
            passages=passages,
            query=query,
        )
    )
    if not missing:
        return None

    kinds = sorted({item["kind"] for item in missing})
    state_or_local = any(kind == "state_or_local_authority_gap" for kind in kinds)
    high_risk = (
        plan.answer_policy.requires_reviewed_contract
        if plan is not None
        else route_category in {
            "arrest_custody_safeguard",
            "business_contract_partnership",
            "criminal_defence_bail",
            "criminal_general",
            "cyber_fraud_or_harassment",
            "child_marriage_protection",
            "child_custody_adoption",
            "criminal_procedure_notice",
            "custody_compensation",
            "digital_platform_account",
            "family_domestic",
            "labour_exploitation_discrimination",
            "manual_scavenging_safety",
            "pmla_ed",
            "police_fir",
            "reproductive_rights_mtp",
            "sexual_offence_survivor",
            "tribal_caste_atrocity",
            "workplace_sexual_harassment",
        }
    )
    if state_or_local:
        message = (
            "I do not have every controlling state or local source needed for this route. "
            "I will not treat a neighboring law or judgment as the final authority; verify "
            "the local rule with DLSA/legal aid or the relevant department before acting."
        )
    elif high_risk:
        message = (
            "A required authority for this high-risk route is missing from the retrieved "
            "source window. Treat this as intake and legal-aid handoff first, not a final "
            "legal answer."
        )
    else:
        message = (
            "One or more route-required authorities were not found in the retrieved source "
            "window. Read any answer as preliminary and verify the missing source before "
            "taking action."
        )

    return {
        "has_gap": True,
        "route_category": route_category,
        "gap_kinds": kinds,
        "missing_required_sources": missing,
        "message": message,
        "handoff": "DLSA/legal aid, a qualified lawyer, or the relevant court/forum",
        "policy": "do_not_substitute_neighboring_authority",
    }


def missing_plan_authorities(
    *,
    plan: MatterPlan,
    passages: list[dict[str, Any]],
    query: str,
) -> list[dict[str, Any]]:
    """Find missing authorities using MatterPlan IDs as the primary key."""
    missing: list[dict[str, Any]] = []
    for entry in plan.authority_ledger:
        requirement_type = classify_required_source_requirement(entry.source)
        if requirement_type == "fact_or_document_requirement":
            continue
        if entry.conditional:
            if entry.note == "category_dependent_sc_article_341_vs_st_article_342":
                continue
            if not _should_enforce_requirement(entry.source, "conditional_authority", query):
                continue
        elif not entry.must_cite:
            continue
        if any(
            _passage_satisfies_plan_entry(plan, entry, passage)
            for passage in passages
            if isinstance(passage, dict)
        ):
            continue
        match_mode = "authority_id"
        missing.append({
            "required_source": entry.source,
            "authority_id": entry.authority_id,
            "source_pack_id": entry.source_pack_id,
            "identity_status": entry.identity_status,
            "required_anchor_patterns": list(entry.required_anchor_patterns),
            "match_mode": match_mode,
            "kind": source_gap_kind(entry.source, query=query),
        })
    return missing


def _passage_satisfies_plan_entry(
    plan: MatterPlan,
    entry: Any,
    passage: dict[str, Any],
) -> bool:
    authority_ids = authority_ids_for_passage(
        plan,
        title=str(passage.get("title") or ""),
        anchor=str(passage.get("anchor") or ""),
        source_pack_id=passage.get("required_source_pack"),
        source_type=passage.get("source_type"),
    )
    if entry.authority_id not in authority_ids:
        return False
    required_anchors = tuple(entry.required_anchor_patterns or ())
    if not required_anchors:
        return True
    anchor = str(passage.get("anchor") or "").lower()
    return any(_plan_anchor_matches(anchor, pattern) for pattern in required_anchors)


def _plan_anchor_matches(anchor: str, pattern: str) -> bool:
    needle = str(pattern or "").lower()
    if needle.startswith("/sec-"):
        return re.search(rf"{re.escape(needle)}(?=@|-|__|$)", anchor) is not None
    return needle in anchor


def missing_required_authorities(
    *,
    required_sources: list[str],
    passages: list[dict[str, Any]],
    query: str,
) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for required in required_sources or []:
        text = str(required or "").strip()
        if not text:
            continue
        requirement_type = classify_required_source_requirement(text)
        if not _should_enforce_requirement(text, requirement_type, query):
            continue
        matched = best_source_match(text, passages, query=query)
        if matched is not None:
            continue
        out.append({
            "required_source": text,
            "kind": source_gap_kind(text, query=query),
        })
    return out


def classify_required_source_requirement(text: str) -> str:
    lower = str(text or "").strip().lower()
    if not lower:
        return "fact_or_document_requirement"
    if any(term in lower for term in (
        "records only after",
        "records only to identify",
        "documents only after",
        "documents only to identify",
    )):
        return "fact_or_document_requirement"
    names_concrete_authority = (
        bool(re.search(r"\bact\b|\bcode\b|\bregulations?\b|\barticle\s+\d+", lower))
        or _has(lower, (
            "bns", "bnss", "bharatiya nyaya sanhita",
            "bharatiya nagarik suraksha sanhita",
            "bharatiya sakshya adhiniyam", "crpc", "ipc", "constitution", "ombudsman",
            "rbi", "cgst", "gst", "income tax", "customs", "pmla", "pocso",
            "pwdva", "nalsa", "dlsa", "statute", "nclt", "nclat",
            "medical council", "medical ethics",
            "compoundability", "compoundable", "compounding",
        ))
    )
    if any(term in lower for term in (
        "bank statement", "complaint number", "date", "details", "document",
        "documents", "evidence", "proof", "record", "records",
        "transaction reference",
    )) and not names_concrete_authority:
        return "fact_or_document_requirement"
    procedural_terms = (
        "court rules", "practice directions", "state rules",
        "state maintenance tribunal rules", "scheme rules", "portal",
        "procedure", "grievance route", "complaint route", "forum",
        "forms", "fees", "certified-copy", "certified copy",
        "help desk", "identity-record update rules",
        "school board", "state caste-certificate",
        "state caste certificate", "state education rules",
    )
    if any(term in lower for term in procedural_terms) and not names_concrete_authority:
        return "procedural_or_local_source"
    conditional_terms = (
        " only if ", " only where ", " where applicable", " where relevant",
        " where needed", " where ", " if ", " based on ", " depending on ",
        " when ",
    )
    if any(term in f" {lower} " for term in conditional_terms):
        return "conditional_authority"
    if _looks_like_authority(lower):
        return "must_cite_authority"
    if any(term in f" {lower} " for term in (
        " based on ", " depending on ", " if ", " only where ", " when ",
        " where ", " where applicable", " where needed", " where relevant",
    )):
        return "conditional_authority"
    return "fact_or_document_requirement"


def should_enforce_required_source(required_source: str, *, query: str) -> bool:
    """Return whether a route-required source should be enforced for this query."""
    text = str(required_source or "").strip()
    if not text:
        return False
    requirement_type = classify_required_source_requirement(text)
    return _should_enforce_requirement(text, requirement_type, query)


def _should_enforce_requirement(text: str, requirement_type: str, query: str) -> bool:
    lower = text.lower()
    q = query.lower()
    if _has(lower, (
        "state education rules",
        "school board or education-record correction rules",
        "school board",
        "education-record correction rules",
        "state caste-certificate issuance and appeal rules",
        "state caste certificate",
        "state caste-certificate",
    )):
        return False
    if _has(lower, (
        "loan documents and rbi restructuring/settlement guidance",
        "gst refund/bank operation records",
        "cooperative-bank grievance route and state cooperative-society forum",
        "victim-compensation and dlsa procedure",
        "victim compensation and dlsa procedure",
    )):
        return False
    if "juvenile justice" in lower and "adoption" in lower:
        return _has_adoption_source_context(q)
    if "indian succession act" in lower and _has(q, ("muslim", "sunni", "shariat")):
        return False
    if "information technology act" in lower and _has(lower, ("platform", "dms", "online accounts")):
        return _has(q, (
            "cyber", "online", "instagram", "insta", "whatsapp", "telegram",
            "facebook", "dm", "dms", "message", "account", "profile",
            "deepfake", "otp", "upi", "data",
        ))
    if _has_statute_alias(lower, ("bnss", "crpc")) and _has(lower, (
        "protection, complaint", "complaint, and maintenance procedure",
        "complaint and maintenance procedure",
    )):
        return _has_family_police_help_needed_context(q)
    if (
        _has_statute_alias(lower, ("bnss", "crpc"))
        and "complaint procedure" in lower
        and "wage complaint" in q
        and not _has(q, (
            "police", "fir", "thana", "station", "magistrate",
            "criminal complaint", "police complaint", "refused fir",
            "not registering", "arrest", "case filed", "file case",
        ))
    ):
        return False
    if "family law statute" in lower or "personal law" in lower:
        return _has(q, _FAMILY_PERSONAL_LAW_TRIGGER_TERMS)
    if "maintenance" in lower and _has(lower, ("bnss", "crpc")):
        return _has(q, _MAINTENANCE_TRIGGER_TERMS)
    if (
        ("hindu marriage act" in lower or "special marriage act" in lower)
        and _has(lower, ("voidable", "matrimonial relief", "marriage", "section 12", "sec 12"))
    ):
        return _has_marriage_validity_source_context(q)
    if "only where a separate fir" in lower or "criminal complaint exists" in lower:
        return _has_separate_criminal_case_context(q)
    if _has_statute_alias(lower, ("bns", "ipc")) and _has(lower, (
        "marital-exception", "marital exception", "sexual-offence", "sexual offence",
    )):
        return _has_separate_criminal_case_context(q)
    if "labour/dlsa grievance route" in lower or "labour dlsa grievance route" in lower:
        return _has(q, (
            "dlsa", "legal aid", "free lawyer", "cannot afford lawyer",
            "no lawyer", "legal help", "nalsa", "slsa",
        ))
    if "victim-compensation" in lower or "victim compensation" in lower:
        return _has(q, (
            "acid attack", "acid thrown", "burn", "burns", "injury", "injured",
            "hospital", "treatment", "compensation", "medical bill",
        ))
    if "adult criminal-procedure wrapper" in lower and _has(q, (
        "juvenile", "minor", "16 yr", "16 year", "17 yr", "17 year",
        "observation home", "school id", "age proof",
    )):
        return False
    if requirement_type in {"fact_or_document_requirement", "procedural_or_local_source"}:
        return False
    if requirement_type != "conditional_authority":
        return True
    if "limitation act" in lower:
        return _has_limitation_trigger_context(q)
    if "commercial courts" in lower and _has(lower, ("where", "if", "when", "12a", "pre-institution", "pre institution")):
        return _has(q, (
            "commercial suit", "commercial dispute", "commercial court",
            "commercial division", "pre institution", "pre-institution",
            "section 12a", "sec 12a", "mediation", "injunction",
            "interim relief", "damages", "court route",
        ))
    if "mediation act" in lower:
        return _has(q, (
            "mediation", "pre litigation", "pre-litigation",
            "pre institution", "pre-institution", "section 12a",
            "sec 12a", "commercial suit", "commercial dispute",
        ))
    if "copyright" in lower and _has(lower, ("where", "if", "when", "copyright", "counter-notice", "counter notice")):
        trademark_only = _has(q, ("trademark", "trade mark", "brand name", "brand", "passing off")) and not _has(q, (
            "copyright", "copying", "piracy", "software license", "unlicensed",
            "dmca", "creative", "artwork", "logo", "photo", "image", "video",
            "content",
        ))
        if trademark_only:
            return False
        return _has(q, (
            "copyright", "copying", "piracy", "software license", "unlicensed",
            "dmca", "counter notice", "counter-notice", "creative", "artwork",
            "logo", "photo", "image", "video", "content",
        ))
    if "pesa" in lower and "forest rights" in lower:
        return _has_pesa_trigger_context(q) or _has_fra_trigger_context(q)
    if "pesa" in lower:
        return _has_pesa_trigger_context(q)
    if "forest conservation act" in lower:
        return _has(q, (
            "forest land", "forest clearance", "forest diversion",
            "reserved forest", "protected forest", "non-forest use",
        ))
    if "forest rights" in lower:
        return _has_fra_trigger_context(q)
    if _has_statute_alias(lower, ("bns", "ipc")) and _has(lower, (
        "physical assault", "stalking", "threat", "threats", "hurt",
        "intimidation", "confinement", "coercion", "where assault",
        "where physical", "where threats",
    )):
        if _has_negated_family_criminal_force_context(q):
            return False
        return _has_physical_stalking_threat_context(q)
    if _has_statute_alias(lower, ("bnss", "crpc")) and "where police help is needed" in lower:
        return _has_family_police_help_needed_context(q)
    if _has_statute_alias(lower, ("bns", "ipc")) and _has(lower, (
        "offence provisions where relevant",
        "offence provisions where applicable",
        "provisions where relevant",
        "provisions where applicable",
        "where relevant",
        "where applicable",
    )):
        if _has_police_threatening_arrest_without_offence_context(q):
            return False
        return _has_criminal_offence_context(q)
    if "based on incident date" in lower and _has(lower, ("bns", "bnss", "ipc", "crpc")):
        has_procedure_code = _has_statute_alias(lower, ("bnss", "crpc"))
        has_offence_code = _has_statute_alias(lower, ("bns", "ipc"))
        if has_procedure_code and not has_offence_code:
            return _has_criminal_process_context(q) or _has_criminal_offence_context(q)
        if has_offence_code and not has_procedure_code:
            if _has_police_threatening_arrest_without_offence_context(q):
                return False
            if _has(lower, ("breach of trust", "criminal breach of trust")):
                return _has_criminal_offence_context(q) or _has_streedhan_or_entrustment_context(q)
            if _has(lower, ("trafficking", "exploitation")):
                return _has_criminal_offence_context(q) or _has_trafficking_exploitation_context(q)
            return _has_criminal_offence_context(q)
        return _has_criminal_process_context(q) or _has_criminal_offence_context(q)
    if "pocso" in lower or "protection of children from sexual offences" in lower:
        return _has(q, ("pocso", "minor", "child", "girl", "boy", "under 18", "17 year", "16 year", "15 year", "14 year"))
    if _has(lower, ("maternity benefit", "maternity")):
        return _has(q, ("maternity", "pregnan", "delivery", "delivered", "baby", "leave"))
    if _has(lower, ("epf", "provident")):
        return _has(q, ("epf", "pf", "provident", "uan", "pension"))
    if "industrial disputes" in lower:
        return _has(q, ("termination", "terminated", "retrench", "fired", "labour court", "factory closed", "no notice"))
    if "indian partnership" in lower:
        return _has(q, ("partner", "partnership", "firm", "llp"))
    if "aadhaar" in lower:
        if _has(lower, ("only where", "uidai records are directly involved", "authentication")):
            return _has(q, (
                "uidai", "aadhaar authentication", "aadhar authentication",
                "authentication failed", "authentication", "biometric",
                "ekyc", "e-kyc", "kyc", "identity mismatch",
                "aadhaar used", "aadhar used", "aadhaar issued",
                "aadhar issued", "aadhaar linked", "aadhar linked",
            ))
        return _has(q, ("aadhaar", "aadhar", "uidai", "kyc", "biometric", "identity mismatch"))
    if "consumer protection" in lower:
        if _has(lower, ("bank", "service deficiency", "service-deficiency")):
            return _has(q, (
                "bank", "atm", "upi", "card", "account", "debit", "deducted",
                "wrongly deducted", "failed transaction", "money not credited",
                "chargeback", "refund", "customer care", "complaint", "grievance",
                "service deficiency", "service-deficiency",
            ))
        return _has(q, (
            "consumer", "refund", "replace", "replacement", "defect", "defective",
            "damaged", "warranty", "service deficiency", "service-deficiency",
            "company not accepting", "seller", "shop", "invoice",
        ))
    if "sale of goods" in lower:
        if _has(q, (
            "no quality issue", "no quality dispute", "no defect", "no defects",
            "not defective", "not damaged", "not a defect", "no rejection",
            "not rejected", "accepted without dispute", "accepted goods no dispute",
        )):
            return False
        return _has(q, ("goods", "material", "defect", "defective", "delivery", "quality", "rejection", "refund"))
    if "indian contract" in lower:
        return _has(q, (
            "consent", "coercion", "undue influence", "authority",
            "blank paper", "thumb impression", "misrepresentation",
            "fraud", "contract", "agreement", "signed", "signature",
        ))
    if "specific relief" in lower:
        if "injunction/performance is sought" in lower:
            return _has(q, (
                "injunction", "specific performance", "performance of contract",
                "perform the contract", "restrain", "stay order",
                "interim relief", "negative covenant", "exclusive",
                "exclusivity", "declaration",
            ))
        return _has(q, ("injunction", "specific performance", "exclusivity", "exclusive", "cancel", "cancellation", "declaration", "restrain", "gift deed", "blank paper", "thumb impression", "sale deed"))
    if "transfer of property" in lower:
        return _has(q, (
            "gift", "gift deed", "settlement", "transfer paper", "property transfer",
            "transferred property", "sale deed", "lease deed", "oral gift",
            "verbally", "cancel", "cancellation", "revoke", "revocation",
        ))
    if "registration act" in lower:
        return _has(q, (
            "registration", "registered", "unregistered", "sub registrar",
            "sub-registrar", "sale deed", "gift deed", "lease deed",
            "document validity", "admissibility", "blank paper",
            "thumb impression", "property paper",
        ))
    if "inter-state migrant" in lower or "inter state migrant" in lower:
        return _has(q, (
            "inter-state", "inter state", "migrant", "came from", "brought from",
            "recruited from", "return ticket", "journey allowance", "go back home",
            "walked from", "home state", "native place",
        ))
    if "forest rights" in lower or "pesa" in lower:
        return _has_fra_trigger_context(q) or _has_pesa_trigger_context(q)
    if "code on social security" in lower:
        return _has(q, ("pf", "epf", "esi", "gig", "platform", "social security", "provident"))
    if "rbi" in lower or "kyc" in lower or "online-gaming" in lower:
        return _has(q, ("bank", "rbi", "kyc", "gaming", "rummy", "dream11", "account", "wallet", "upi"))
    if "medical ethics" in lower or "medical council" in lower:
        return _has(q, (
            "medical records", "case papers", "hospital records", "not giving records",
            "wrong treatment", "wrong injection", "wrong surgery", "wrong leg",
            "negligence", "medical negligence", "died", "death", "dead",
            "injury", "misconduct", "operated wrong",
        ))
    if "clinical establishments" in lower:
        if _has(q, ("tamil nadu", "tamilnadu", "chennai", "coimbatore", "madurai")):
            return False
        return _has(q, ("hospital", "doctor", "medical", "icu", "billing", "bill", "records", "negligence", "wrong surgery", "wrong leg"))
    if "prevention of corruption" in lower:
        if _has(q, (
            "no bribe", "not bribe", "not a bribe", "without bribe",
            "no cash demand", "no money demand", "no money demanded",
            "not asking money", "not asked money", "did not ask money",
            "didn't ask money", "no payment demand",
        )):
            return False
        return _has(q, (
            "bribe", "corruption", "cash", "demanding money",
            "fake job card", "fake job cards", "fake muster", "muster",
            "forged", "misappropriation", "dead people", "dead persons",
            "fake entries", "action taken report", "atr",
        ))
    if "bnss/crpc custody" in lower or ("bnss" in lower and "crpc" in lower and "custody" in lower):
        return _has(q, (
            "custody", "jail", "remand", "undertrial", "acquitted",
            "acquittal", "released", "compensation", "appeal", "bail",
        ))
    if "state prison rules" in lower or "prison manual" in lower:
        return _has(q, ("prison", "jail", "tihar", "mulaqat", "books", "furlough", "parole"))
    if "real estate" in lower or "rera" in lower:
        return _has(q, ("rera", "builder", "flat", "possession", "carpet", "project", "allotment"))
    if "bonded labour" in lower:
        return _has(q, (
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
        return _has(q, (
            "cess", "fake register", "false register", "fake registers",
            "same name", "fake entry", "fake entries", "muster roll",
            "register fraud", "welfare board record", "welfare-board record",
            "cess record", "cess records",
        ))
    if "criminal-negligence" in lower or "criminal negligence" in lower:
        return _has(q, (
            "negligence", "wrong treatment", "death", "died", "dead", "injury",
            "assault", "medical negligence", "wrong injection", "wrong surgery",
        ))
    if "building and other construction" in lower or "bocw" in lower or "factories act" in lower:
        if _has(lower, ("where the workplace is a construction", "construction/building worksite")):
            return _has(q, (
                "construction", "building work", "worksite", "construction site",
                "site worker", "bocw", "builder site", "thekedar",
            ))
        return _has(q, (
            "construction", "building work", "site", "worksite", "factory",
            "plant", "boiler", "machine", "accident at work", "worker died",
            "fell from", "lost hand", "lost limb", "bocw", "cess",
            "register", "fake register", "false register", "same name",
            "welfare board", "benefit claim", "thekedar",
        ))
    if "code on wages" in lower or "minimum wage" in lower:
        if "where unpaid overtime wages are also claimed" in lower:
            return _has(q, (
                "unpaid overtime", "overtime wages", "overtime payment",
                "not paid overtime", "wages unpaid", "salary unpaid",
                "payment withheld", "wage claim", "wage dues",
            ))
        if "only if" in lower:
            return _has(q, (
                "wage", "wages", "salary", "overtime", "deduct", "deducted",
                "minimum", "full and final", "leave encash", "payment withheld",
                "unpaid dues", "not paid salary", "food deducted",
            ))
        return _has(q, ("wage", "salary", "overtime", "deduct", "minimum", "full and final", "payment"))
    if "legal services authorities" in lower or "legal aid" in lower or "dlsa" in lower:
        return _has(q, (
            "dlsa", "legal aid", "free lawyer", "legal services", "nalsa",
            "slsa", "legal help", "cannot afford lawyer", "no lawyer",
            "lawyer not coming", "jail legal aid",
        ))
    if "compound" in lower or "compoundability" in lower:
        return _has_criminal_process_context(q) or _has_criminal_offence_context(q) or _has(q, (
            "settlement", "settle", "compromise", "compound",
            "quash", "quashing", "permission",
        ))
    if "article 32" in lower:
        return _has(q, ("supreme court", "article 32", "fundamental right"))
    if "registration act only if" in lower:
        return _has(q, (
            "registration", "registered", "unregistered", "sub registrar",
            "sub-registrar", "sale deed", "gift deed", "lease deed",
            "admissibility", "document validity",
        ))
    if "bnss" in lower and "crpc" in lower and "only if" in lower:
        return _has_criminal_offence_context(q) or _has_trigger_term(q, (
            "criminal case", "criminal court", "summons in criminal",
            "warrant in criminal", "accused", "fir", "f.i.r",
            "police notice", "arrest", "arrested", "bns", "ipc",
            "bnss", "crpc",
        ))
    if _is_bns_bnss_or_ipc_crpc_requirement(lower) and _has(lower, ("cheating", "forgery", "false register", "fake register")):
        return _has(q, (
            "cheating", "forgery", "forged", "fake register", "false register",
            "fake registers", "same name", "fake entry", "false entry",
            "muster roll fraud", "fake muster", "false muster", "cess fraud",
            "fake benefit claim", "false benefit claim", "benefit fraud",
            "thekedar cheated", "contractor cheated",
        ))
    if _has_statute_alias(lower, ("bnss", "crpc")):
        return _has_criminal_process_context(q) or _has_criminal_offence_context(q)
    if _has_statute_alias(lower, ("bns", "ipc")):
        return _has_criminal_offence_context(q) or _has_physical_stalking_threat_context(q)
    if "information technology" in lower:
        return _has(q, ("cyber", "online", "instagram", "whatsapp", "telegram", "account", "deepfake", "otp", "upi", "data"))
    return False


def best_source_match(required_source: str, passages: list[dict[str, Any]], *, query: str) -> dict[str, Any] | None:
    constitution_match = _constitution_article_requirement_match(required_source, passages)
    if constitution_match is not None:
        return constitution_match
    if _is_hard_composite_requirement(required_source):
        return _composite_route_source_match(required_source, passages, query=query)
    composite_match = _composite_route_source_match(required_source, passages, query=query)
    if composite_match is not None:
        return composite_match
    if _is_dual_regime_requirement(required_source):
        return _dual_regime_source_match(required_source, passages, query=query)
    tokens = _source_tokens(required_source)
    best: tuple[float, dict[str, Any] | None] = (0.0, None)
    for item in passages or []:
        if not isinstance(item, dict):
            continue
        blob = _item_blob(item)
        if _canonical_match(required_source, blob, query=query):
            return item
        if not tokens:
            continue
        score = _coverage_score(tokens, blob)
        if score > best[0]:
            best = (score, item)
    if _is_hard_canonical_requirement(required_source):
        return None
    if not tokens:
        return None
    return best[1] if best[0] >= _threshold(tokens) else None


def source_gap_kind(required_source: str, *, query: str = "") -> str:
    source_blob = _blob(required_source)
    if _has(source_blob, ("employees provident", "epf", "provident fund", "code on social security")):
        return "national_labor_source_gap"
    if _has(source_blob, ("bns", "bnss", "ipc", "crpc", "pocso", "ndps", "uapa", "criminal")):
        return "national_criminal_source_gap"
    if _has(source_blob, ("gst", "cgst", "customs", "income tax", "tds", "tcs", "icegate")):
        return "national_tax_source_gap"
    if _has(source_blob, ("constitution", "article 14", "article 21", "article 22", "article 226")):
        return "constitutional_authority_gap"
    if _has(source_blob, (
        "state", "local", "municipal", "municipality", "panchayat",
        "scheduled area", "scheduled areas", "tribal land", "witch",
        "daain", "dayan", "tonahi", "tonhi", "cattle preservation",
        "excise", "bhang", "shops and establishments",
        "prison rules", "rent-control", "tenancy law",
    )):
        return "state_or_local_authority_gap"
    blob = _blob(required_source, query)
    if _has(blob, ("gst", "cgst", "customs", "income tax", "tds", "tcs", "icegate")):
        return "national_tax_source_gap"
    if _has(blob, ("bns", "bnss", "ipc", "crpc", "pocso", "ndps", "uapa", "criminal")):
        return "national_criminal_source_gap"
    if _has(blob, ("constitution", "article 14", "article 21", "article 22", "article 226")):
        return "constitutional_authority_gap"
    return "national_statute_retrieval_gap"


def _canonical_match(required_source: str, item_blob: str, *, query: str) -> bool:
    lower = required_source.lower()
    q = query.lower()
    if (
        ("employees' provident" in lower or "employees provident" in lower or "epf" in lower)
        and "code on social security" in lower
    ):
        epf_match = ("provident" in item_blob or "epf" in item_blob) and _has_any_exact_anchor(
            item_blob,
            ("sec-6a", "/sec-6a"),
        )
        social_security_match = ("social security" in item_blob or "social-security" in item_blob) and _has_any_exact_anchor(
            item_blob,
            ("sec-15", "/sec-15"),
        )
        return epf_match or social_security_match
    if "code on social security" in lower:
        if _has(lower, ("contribution", "classification")):
            return ("social security" in item_blob or "social-security" in item_blob) and (
                _has_any_anchor(item_blob, (
                    "sec-15", "sec-31", "sec-125", "sec-126",
                    "sec-128", "sec-129", "/sec-15", "/sec-31",
                    "/sec-125", "/sec-126", "/sec-128", "/sec-129",
                ))
                or "#header" in item_blob
            )
        return ("social security" in item_blob or "social-security" in item_blob) and (
            _has_any_anchor(item_blob, (
                "sec-109", "sec-112", "sec-113",
                "/sec-109", "/sec-112", "/sec-113",
            ))
            or "#header" in item_blob
        )
    if _is_pmla_sc_precedent_requirement(lower):
        return _pmla_sc_precedent_item_matches(item_blob)
    if "bnss/crpc custody" in lower or ("bnss" in lower and "crpc" in lower and "custody" in lower):
        return _has(item_blob, (
            "bnss", "bharatiya nagarik", "crpc", "code of criminal procedure",
            "criminal procedure",
        )) and _has_any_anchor(item_blob, (
            "sec-167", "sec-187", "sec-436a", "sec-436-a", "sec-479",
            "sec-50", "sec-57", "sec-397", "sec-374", "/sec-167",
            "/sec-187", "/sec-436a", "/sec-436-a", "/sec-479",
            "/sec-50", "/sec-57", "/sec-397", "/sec-374",
        ))
    if "dowry prohibition" in lower:
        return "dowry prohibition" in item_blob and _has_any_anchor(item_blob, ("sec-2", "sec-3", "sec-4", "sec-6", "sec-10", "/sec-2", "/sec-3", "/sec-4", "/sec-6", "/sec-10"))
    if "clinical establishments" in lower or "clinical-establishment" in lower:
        return ("clinical establishments" in item_blob or "clinical-establishments" in item_blob) and _has_any_anchor(item_blob, ("sec-12", "sec-42", "/sec-12", "/sec-42"))
    if "mental healthcare act" in lower or "mental-healthcare" in lower:
        if "mental healthcare" not in item_blob and "mental-healthcare" not in item_blob:
            return False
        privacy_context = _has(lower, ("confidential", "privacy", "therapist", "records", "communication"))
        confinement_context = _has(q, (
            "chain", "chains", "chained", "tied", "confined", "locked in room",
            "kept locked", "ill treated", "ill-treated", "neglected",
        ))
        if privacy_context:
            return _has_any_anchor(item_blob, (
                "sec-23", "sec-24", "sec-25", "sec-43",
                "/sec-23", "/sec-24", "/sec-25", "/sec-43",
            ))
        if confinement_context:
            return _has_any_anchor(item_blob, (
                "sec-20", "sec-94", "sec-97", "sec-100",
                "/sec-20", "/sec-94", "/sec-97", "/sec-100",
            ))
        return True
    if "representation of the people" in lower or "voter-list" in lower or "voter list" in lower:
        return (
            "representation of the people" in item_blob
            or "rpa-1950" in item_blob
            or "rpa-1951" in item_blob
        ) and _has_any_anchor(item_blob, (
            "sec-19", "sec-22", "sec-23", "sec-24", "sec-62",
            "/sec-19", "/sec-22", "/sec-23", "/sec-24", "/sec-62",
        ))
    if "limitation act" in lower:
        return "limitation" in item_blob and _has_any_anchor(item_blob, ("sec-3", "sec-5", "sec-14", "/sec-3", "/sec-5", "/sec-14"))
    charge_sheet_or_discharge_context = _has(
        lower,
        (
            "charge-sheet", "chargesheet", "charge sheet", "police report",
            "summons", "discharge",
        ),
    )
    if (
        _has_statute_alias(lower, ("bnss", "crpc"))
        and _has(lower, ("bail", "arrest"))
        and not charge_sheet_or_discharge_context
    ):
        anchors = _bail_arrest_safeguard_anchor_terms(q, lower)
        return _has(item_blob, (
            "bnss", "bharatiya nagarik", "crpc", "code of criminal procedure",
            "criminal procedure",
        )) and _has_any_anchor(item_blob, anchors)
    if _single_statute_section_match(lower, item_blob):
        return True
    if "indian contract act" in lower or "contract act" in lower:
        if "indian contract" not in item_blob and "contract act" not in item_blob:
            return False
        if _has(lower, ("consent", "coercion", "undue", "fraud", "void", "authority")):
            return _has_any_anchor(item_blob, (
                "sec-14", "sec-15", "sec-16", "sec-17", "sec-18", "sec-19",
                "sec-19-a", "sec-19-b", "/sec-14", "/sec-15", "/sec-16",
                "/sec-17", "/sec-18", "/sec-19", "/sec-19-a", "/sec-19-b",
            ))
        return _has_any_anchor(item_blob, ("sec-37", "sec-73", "sec-74", "/sec-37", "/sec-73", "/sec-74"))
    if "registration act" in lower:
        return "registration" in item_blob and _has_any_anchor(item_blob, ("sec-17", "sec-23", "sec-49", "/sec-17", "/sec-23", "/sec-49"))
    if "specific relief act" in lower:
        return "specific relief" in item_blob and _has_any_anchor(item_blob, (
            "sec-10", "sec-14", "sec-16", "sec-20", "sec-21",
            "sec-31", "sec-34", "sec-38", "sec-42",
            "/sec-10", "/sec-14", "/sec-16", "/sec-20", "/sec-21",
            "/sec-31", "/sec-34", "/sec-38", "/sec-42",
        ))
    if "transfer of property act" in lower:
        return "transfer of property" in item_blob and _has_any_anchor(item_blob, (
            "sec-44", "sec-45", "sec-54", "sec-105", "sec-106", "sec-111",
            "sec-122", "sec-126", "/sec-44", "/sec-45", "/sec-54", "/sec-105",
            "/sec-106", "/sec-111", "/sec-122", "/sec-126",
        ))
    if "consumer protection" in lower:
        return "consumer protection" in item_blob and _has_any_anchor(item_blob, ("sec-2", "sec-35", "sec-38", "sec-39", "/sec-2", "/sec-35", "/sec-38", "/sec-39"))
    if "prevention of corruption" in lower:
        return "prevention of corruption" in item_blob and _has_any_anchor(item_blob, ("sec-7", "sec-8", "sec-13", "/sec-7", "/sec-8", "/sec-13"))
    if "bnss 2023 arrest" in lower or "bnss arrest" in lower:
        return _has(item_blob, ("bnss", "bharatiya nagarik")) and _has_any_anchor(item_blob, (
            "sec-35", "sec-47", "sec-48", "sec-57", "sec-58", "sec-187",
            "/sec-35", "/sec-47", "/sec-48", "/sec-57", "/sec-58", "/sec-187",
        ))
    if "crpc 1973 arrest" in lower or "crpc arrest" in lower:
        return _has(item_blob, ("crpc", "code of criminal procedure", "criminal procedure")) and _has_any_anchor(item_blob, (
            "sec-41", "sec-50", "sec-56", "sec-57", "sec-160", "sec-167",
            "/sec-41", "/sec-50", "/sec-56", "/sec-57", "/sec-160", "/sec-167",
        ))
    if "cgst" in lower or "goods and services tax" in lower or "gst" in lower:
        if "rule 86b" in lower or "86b" in lower:
            return _cgst_rule_86b_item_matches(item_blob)
        return ("cgst" in item_blob or "goods and services tax" in item_blob) and _has_any_anchor(item_blob, (
            "sec-16", "sec-22", "sec-24", "sec-29", "sec-47", "sec-73",
            "sec-67", "sec-74", "sec-75", "sec-49", "sec-49a", "sec-49b",
            "/sec-16", "/sec-22", "/sec-24", "/sec-29", "/sec-47",
            "/sec-49", "/sec-49a", "/sec-49b", "/sec-67", "/sec-73",
            "/sec-74", "/sec-75",
        ))
    if "customs act" in lower or _has(lower, ("icegate", "import/export", "drawback", "classification", "valuation", "svb")):
        return _customs_requirement_matches(lower, item_blob, q)
    if "unlawful activities" in lower or "uapa" in lower:
        return (
            ("unlawful activities" in item_blob or "uapa" in item_blob)
            and _has_any_anchor(item_blob, ("sec-43d", "/sec-43d"))
        )
    if "hindu marriage act" in lower and "special marriage act" in lower:
        if re.search(r"\b(?:section|sec|s)\.?\s*13\b", lower):
            hma_section_13 = (
                ("hindu marriage" in item_blob or "hindu-marriage" in item_blob)
                and _has_hindu_marriage_section_13_ground_anchor(item_blob)
            )
            sma_divorce = (
                ("special marriage" in item_blob or "special-marriage" in item_blob)
                and _has_any_exact_anchor(item_blob, ("sec-27", "/sec-27"))
            )
            return hma_section_13 or sma_divorce
        if re.search(r"\b(?:section|sec|s)\.?\s*12\b", lower) or "voidable" in lower:
            hma_voidable = (
                ("hindu marriage" in item_blob or "hindu-marriage" in item_blob)
                and _has_any_exact_anchor(item_blob, ("sec-12", "/sec-12"))
            )
            sma_voidable = (
                ("special marriage" in item_blob or "special-marriage" in item_blob)
                and _has_any_exact_anchor(item_blob, ("sec-24", "sec-25", "/sec-24", "/sec-25"))
            )
            return hma_voidable or sma_voidable
        hma_match = (
            ("hindu marriage" in item_blob or "hindu-marriage" in item_blob)
            and (
                _has_any_exact_anchor(item_blob, ("sec-12", "/sec-12"))
                or _has_any_anchor(item_blob, (
                    "sec-9", "sec-13", "sec-13b", "sec-13-b", "sec-24",
                    "sec-25", "sec-26", "/sec-9", "/sec-13", "/sec-13b",
                    "/sec-13-b", "/sec-24", "/sec-25", "/sec-26",
                ))
            )
        )
        sma_match = (
            ("special marriage" in item_blob or "special-marriage" in item_blob)
            and _has_any_anchor(item_blob, (
                "sec-24", "sec-25", "sec-27", "/sec-24", "/sec-25", "/sec-27",
            ))
        )
        return hma_match or sma_match
    if "hindu marriage act" in lower or "hindu marriage" in lower:
        if "hindu marriage" not in item_blob and "hindu-marriage" not in item_blob:
            return False
        if "section 13b" in lower or "sec 13b" in lower or "13b" in lower:
            return _has_any_exact_anchor(item_blob, ("sec-13b", "sec-13-b", "/sec-13b", "/sec-13-b"))
        if re.search(r"\b(?:section|sec|s)\.?\s*13\b", lower):
            return _has_hindu_marriage_section_13_ground_anchor(item_blob)
        if re.search(r"\b(?:section|sec|s)\.?\s*12\b", lower):
            return _has_any_exact_anchor(item_blob, ("sec-12", "/sec-12"))
        return _has_any_anchor(item_blob, (
            "sec-9", "sec-12", "sec-13", "sec-13b", "sec-13-b",
            "sec-24", "sec-25", "sec-26", "/sec-9", "/sec-12",
            "/sec-13", "/sec-13b", "/sec-13-b", "/sec-24",
            "/sec-25", "/sec-26",
        ))
    if "family courts act" in lower or "family court" in lower:
        return (
            "family courts" in item_blob or "family-courts" in item_blob
        ) and _has_any_anchor(item_blob, ("sec-7", "sec-8", "/sec-7", "/sec-8"))
    if "medical/vulnerability bail" in lower or ("vulnerability" in lower and "bail" in lower):
        return (
            (_has(item_blob, ("constitution",)) and _has_any_exact_anchor(item_blob, ("sec-21", "/sec-21")))
            or (
                _has(item_blob, ("bnss", "bharatiya nagarik", "crpc", "code of criminal procedure", "criminal procedure"))
                and _has_any_exact_anchor(item_blob, (
                    "sec-437", "sec-480", "sec-483",
                    "/sec-437", "/sec-480", "/sec-483",
                ))
            )
        )
    if "legal services authorities act" in lower or "legal aid" in lower or "dlsa" in lower:
        return "legal services authorities" in item_blob and _has_any_anchor(item_blob, ("sec-9", "sec-12", "sec-13", "sec-21", "/sec-9", "/sec-12", "/sec-13", "/sec-21"))
    if "aadhaar act" in lower:
        return ("aadhaar" in item_blob or "unique identification" in item_blob) and _has_any_anchor(item_blob, (
            "sec-7", "sec-8", "sec-29", "sec-59",
            "/sec-7", "/sec-8", "/sec-29", "/sec-59",
        ))
    if "right to information" in lower or re.search(r"\brti\b", lower):
        return ("right to information" in item_blob or re.search(r"\brti\b", item_blob)) and _has_any_anchor(item_blob, ("sec-6", "sec-7", "sec-19", "/sec-6", "/sec-7", "/sec-19"))
    if "national food security" in lower or re.search(r"\bration\b", lower):
        return "national food security" in item_blob and _has_any_anchor(item_blob, ("sec-3", "sec-12", "sec-14", "sec-15", "/sec-3", "/sec-12", "/sec-14", "/sec-15"))
    if "forest rights act" in lower:
        return ("forest rights" in item_blob or "scheduled tribes and other traditional forest dwellers" in item_blob or "fra-2006" in item_blob) and (
            "#header" in item_blob
            or _has_any_anchor(item_blob, ("sec-3", "sec-4", "sec-5", "sec-6", "/sec-3", "/sec-4", "/sec-5", "/sec-6"))
        )
    if "pesa act" in lower or ("pesa" in lower and "gram sabha" in lower):
        return ("pesa" in item_blob or "panchayats" in item_blob) and _has_any_anchor(item_blob, ("sec-4", "/sec-4"))
    if "bonded labour" in lower:
        return "bonded labour" in item_blob and _has_any_anchor(item_blob, ("sec-4", "sec-10", "sec-12", "/sec-4", "/sec-10", "/sec-12"))
    if "inter-state migrant" in lower or "inter state migrant" in lower:
        return ("inter-state migrant" in item_blob or "inter state migrant" in item_blob) and _has_any_anchor(item_blob, ("sec-6", "sec-12", "sec-14", "/sec-6", "/sec-12", "/sec-14"))
    if "industrial disputes" in lower:
        return "industrial disputes" in item_blob and _has_any_anchor(item_blob, ("sec-2a", "sec-2-a", "sec-10", "sec-25f", "sec-25-f", "/sec-2a", "/sec-2-a", "/sec-10", "/sec-25f", "/sec-25-f"))
    if (
        (
            "bocw act" in lower
            and "factories act" in lower
        )
        or "bocw act 1996 / factories act" in lower
    ):
        return (
            (
                "building and other construction workers" in item_blob
                or "bocw-1996" in item_blob
            )
            and _has_any_anchor(item_blob, (
                "sec-12", "sec-13", "sec-14", "sec-39", "sec-40", "sec-44",
                "/sec-12", "/sec-13", "/sec-14", "/sec-39", "/sec-40", "/sec-44",
            ))
        ) or (
            ("factories act" in item_blob or "factories-1948" in item_blob)
            and _has_any_anchor(item_blob, (
                "sec-7a", "sec-40", "sec-41", "sec-41b", "sec-41c",
                "sec-87", "sec-88", "sec-92", "sec-111",
                "/sec-7a", "/sec-40", "/sec-41", "/sec-41b", "/sec-41c",
                "/sec-87", "/sec-88", "/sec-92", "/sec-111",
            ))
        )
    if (
        "building and other construction workers act" in lower
        or "bocw act" in lower
        or "bocw registration" in lower
        or "welfare-board provisions" in lower
    ):
        return (
            "building and other construction workers" in item_blob
            or "bocw-1996" in item_blob
        ) and _has_any_anchor(item_blob, ("sec-12", "sec-13", "sec-14", "/sec-12", "/sec-13", "/sec-14"))
    if "bocw cess" in lower or "welfare-board cess" in lower or "welfare board cess" in lower or "construction workers welfare cess" in lower:
        return (
            "building and other construction workers welfare cess" in item_blob
            or "bocw cess" in item_blob
            or "bocw-cess" in item_blob
        ) and _has_any_anchor(item_blob, ("sec-3", "sec-4", "/sec-3", "/sec-4"))
    if "maternity benefit" in lower:
        return "maternity benefit" in item_blob and _has_any_anchor(item_blob, ("sec-5", "sec-12", "/sec-5", "/sec-12"))
    if "employees' provident" in lower or "employees provident" in lower or "epf" in lower:
        return ("provident" in item_blob or "epf" in item_blob) and _has_any_anchor(item_blob, ("sec-6", "sec-7a", "sec-14", "/sec-6", "/sec-7a", "/sec-14"))
    if "employees state insurance" in lower or re.search(r"\besi\b", lower):
        return ("employees state insurance" in item_blob or "esi" in item_blob) and _has_any_anchor(item_blob, ("sec-38", "sec-39", "sec-46", "/sec-38", "/sec-39", "/sec-46"))
    if "indian partnership act" in lower:
        return "partnership" in item_blob and _has_any_anchor(item_blob, ("sec-9", "sec-12", "sec-32", "sec-44", "/sec-9", "/sec-12", "/sec-32", "/sec-44"))
    if "sale of goods act" in lower:
        return "sale of goods" in item_blob and _has_any_anchor(item_blob, ("sec-11", "sec-12", "sec-31", "sec-42", "/sec-11", "/sec-12", "/sec-31", "/sec-42"))
    if "msmed act" in lower or "micro, small" in lower:
        return ("msmed" in item_blob or "micro, small" in item_blob) and _has_any_anchor(item_blob, ("sec-15", "sec-16", "sec-18", "/sec-15", "/sec-16", "/sec-18"))
    if "pwdva" in lower or "domestic violence" in lower:
        return ("domestic violence" in item_blob or "pwdva" in item_blob) and _has_any_anchor(item_blob, ("sec-3", "sec-12", "sec-18", "sec-19", "sec-20", "/sec-3", "/sec-12", "/sec-18", "/sec-19", "/sec-20"))
    if "hindu succession act" in lower:
        return "hindu succession" in item_blob and _has_any_anchor(item_blob, ("sec-6", "sec-8", "sec-10", "sec-14", "sec-15", "/sec-6", "/sec-8", "/sec-10", "/sec-14", "/sec-15"))
    if "income tax act" in lower or "income-tax act" in lower:
        if _has(lower, ("143(2)", "section 143")) or _has(q, ("143(2)", "section 143", "sec 143")):
            return (
                "income tax" in item_blob
                or "income-tax" in item_blob
            ) and (
                _has_any_anchor(item_blob, (
                    "sec-143",
                    "/sec-143",
                ))
                or _has(item_blob, ("section 143", "sub-section (2) of section 143"))
            )
        return ("income tax" in item_blob or "income-tax" in item_blob) and _has_any_anchor(item_blob, ("sec-5", "sec-9", "sec-45", "sec-54", "sec-54f", "sec-139", "sec-143", "sec-154", "sec-195", "sec-214", "sec-234e", "sec-246a", "sec-249", "sec-250", "sec-253", "sec-254", "sec-255", "sec-80", "sec-80a", "sec-80c", "sec-80ccd", "sec-80cce", "sec-194", "sec-206c", "/sec-5", "/sec-9", "/sec-45", "/sec-54", "/sec-54f", "/sec-139", "/sec-143", "/sec-154", "/sec-195", "/sec-214", "/sec-234e", "/sec-246a", "/sec-249", "/sec-250", "/sec-253", "/sec-254", "/sec-255", "/sec-80", "/sec-80a", "/sec-80c", "/sec-80ccd", "/sec-80cce", "/sec-194", "/sec-206c"))
    if "employees compensation" in lower or "employees' compensation" in lower:
        return (
            "employees' compensation" in item_blob
            or "employees compensation" in item_blob
            or "employees-compensation" in item_blob
        ) and _has_any_anchor(item_blob, (
            "sec-3", "sec-4", "sec-4a", "sec-4-a", "sec-10", "sec-11",
            "/sec-3", "/sec-4", "/sec-4a", "/sec-4-a", "/sec-10", "/sec-11",
        ))
    if "drugs and cosmetics" in lower:
        return (
            "drugs and cosmetics" in item_blob
            or "drugs-cosmetics" in item_blob
        ) and _has_any_anchor(item_blob, (
            "sec-18", "sec-22", "sec-23", "sec-27",
            "/sec-18", "/sec-22", "/sec-23", "/sec-27",
        ))
    if "trade marks act" in lower or "trademark" in lower or "trade mark" in lower:
        return (
            "trade marks" in item_blob
            or "trade-marks" in item_blob
            or "trademark" in item_blob
        ) and _has_any_anchor(item_blob, (
            "sec-11", "sec-28", "sec-29", "sec-34", "sec-124",
            "sec-134", "sec-135", "/sec-11", "/sec-28", "/sec-29",
            "/sec-34", "/sec-124", "/sec-134", "/sec-135",
        ))
    if "rbi/kyc" in lower or ("rbi" in lower and "kyc" in lower):
        if "online-gaming" in lower or "online gaming" in lower:
            return (
                (
                    "reserve bank integrated ombudsman" in item_blob
                    or "rbi-integrated-ombudsman" in item_blob
                    or "banking regulation" in item_blob
                )
                and _has_any_anchor(item_blob, (
                    "#header", "sec-2", "sec-3", "sec-35a", "sec-35-a",
                    "/sec-2", "/sec-3", "/sec-35a", "/sec-35-a",
                ))
            ) or (
                ("prevention of money laundering" in item_blob or "pmla" in item_blob)
                and _has_any_anchor(item_blob, (
                    "sec-5", "sec-8", "sec-17", "sec-50",
                    "/sec-5", "/sec-8", "/sec-17", "/sec-50",
                ))
            ) or (
                ("public gambling" in item_blob or "online gambling" in item_blob)
                and _has_any_anchor(item_blob, (
                    "sec-3", "sec-12", "sec-13",
                    "/sec-3", "/sec-12", "/sec-13",
                ))
            ) or (
                ("information technology" in item_blob or "it-2000" in item_blob)
                and _has_any_anchor(item_blob, ("sec-79", "/sec-79"))
            )
        return (
            "reserve bank integrated ombudsman" in item_blob
            or "rbi-integrated-ombudsman" in item_blob
            or "banking regulation" in item_blob
        ) and _has_any_anchor(item_blob, (
            "#header", "sec-2", "sec-3", "sec-35a", "sec-35-a",
            "/sec-2", "/sec-3", "/sec-35a", "/sec-35-a",
        ))
    if "mines and minerals" in lower or "mmdr" in lower or "mining lease" in lower or "mineral-concession" in lower or "mineral concession" in lower:
        return (
            "mines and minerals" in item_blob
            or "mmdr" in item_blob
            or "mmdr-1957" in item_blob
        ) and _has_any_anchor(item_blob, (
            "sec-4", "sec-10", "sec-10a", "sec-10-a", "sec-10b",
            "sec-10-b", "sec-11", "sec-13", "/sec-4", "/sec-10",
            "/sec-10a", "/sec-10-a", "/sec-10b", "/sec-10-b",
            "/sec-11", "/sec-13",
        ))
    if "real estate" in lower or "rera" in lower:
        return ("real estate" in item_blob or "rera" in item_blob) and _has_any_anchor(item_blob, ("sec-11", "sec-14", "sec-18", "sec-31", "sec-34", "/sec-11", "/sec-14", "/sec-18", "/sec-31", "/sec-34"))
    if "prison rules" in lower or "prison manual" in lower:
        if _is_delhi_prison_rules_blob(item_blob) and not _has_delhi_prison_query_context(q):
            return False
        return (
            ("prison rules" in item_blob or "prison manual" in item_blob)
            or ("prisons act" in item_blob and _has_any_anchor(item_blob, ("sec-59", "/sec-59")))
        )
    if "juvenile justice" in lower:
        return ("juvenile justice" in item_blob or "jj-2015" in item_blob) and _has_any_anchor(item_blob, (
            "sec-9", "sec-12", "sec-56", "sec-57", "sec-58", "sec-59",
            "sec-62", "sec-63", "sec-94",
            "/sec-9", "/sec-12", "/sec-56", "/sec-57", "/sec-58",
            "/sec-59", "/sec-62", "/sec-63", "/sec-94",
        ))
    if "immoral traffic" in lower:
        return ("immoral traffic" in item_blob or "itpa" in item_blob) and _has_any_anchor(item_blob, ("sec-5", "sec-6", "sec-17", "/sec-5", "/sec-6", "/sec-17"))
    if (
        "prevention of atrocities" in lower
        and "rule 7" in lower
    ) or (
        "sc/st" in lower
        and "rule 7" in lower
    ):
        return (
            "prevention of atrocities" in item_blob
            or "sc-st-poa-rules" in item_blob
        ) and _has_any_anchor(item_blob, ("rule-7", "/rule-7"))
    if "public gambling" in lower:
        return "public gambling" in item_blob and _has_any_anchor(item_blob, ("sec-3", "sec-4", "sec-12", "/sec-3", "/sec-4", "/sec-12"))
    if "registration of births and deaths" in lower:
        return "registration of births" in item_blob and _has_any_anchor(item_blob, ("sec-8", "sec-12", "sec-13", "/sec-8", "/sec-12", "/sec-13"))
    if "code on social security" in lower:
        if _has(lower, ("contribution", "classification")):
            return ("social security" in item_blob or "social-security" in item_blob) and (
                _has_any_anchor(item_blob, (
                    "sec-15", "sec-31", "sec-125", "sec-126",
                    "sec-128", "sec-129", "/sec-15", "/sec-31",
                    "/sec-125", "/sec-126", "/sec-128", "/sec-129",
                ))
                or "#header" in item_blob
            )
        return ("social security" in item_blob or "social-security" in item_blob) and (_has_any_anchor(item_blob, ("sec-109", "sec-112", "sec-113", "/sec-109", "/sec-112", "/sec-113")) or "#header" in item_blob)
    if (
        ("information technology act" in lower or "it act" in lower)
        and "67b" in lower
        and not _has(lower, ("66e", "67a"))
    ):
        return (
            "information technology" in item_blob
            or "it-2000" in item_blob
        ) and _has_any_anchor(item_blob, ("sec-67b", "/sec-67b"))
    if "information technology act" in lower or "it act" in lower or "it rules" in lower:
        return ("information technology" in item_blob or "it-2000" in item_blob) and _has_any_anchor(item_blob, (
            "sec-66c", "sec-66d", "sec-66e", "sec-67", "sec-67a", "sec-67b",
            "sec-69", "sec-69a", "sec-79", "sec-90", "/sec-66c",
            "/sec-66d", "/sec-66e", "/sec-67", "/sec-67a", "/sec-67b",
            "/sec-69", "/sec-69a", "/sec-79", "/sec-90",
        ))
    if "pocso" in lower or "protection of children from sexual offences" in lower:
        return (
            "pocso" in item_blob
            or "protection of children from sexual offences" in item_blob
        ) and _has_any_anchor(item_blob, (
            "sec-13", "sec-13-a", "sec-13-b", "sec-15", "sec-19",
            "/sec-13", "/sec-13-a", "/sec-13-b", "/sec-15", "/sec-19",
        ))
    if "bns/modified" in lower:
        return False
    if lower.strip() == "bns/bnss or ipc/crpc based on incident date" or "bns/bnss or ipc/crpc based on incident date" in lower:
        return False
    if "code on wages" in lower:
        return "code on wages" in item_blob and _has_any_anchor(item_blob, (
            "sec-17", "sec-45", "sec-53", "sec-54",
            "/sec-17", "/sec-45", "/sec-53", "/sec-54",
        ))
    if "information technology act" in lower and "67b" in lower and not _has(lower, ("66e", "67a")):
        return (
            "information technology" in item_blob
            or "it-2000" in item_blob
        ) and _has_any_anchor(item_blob, ("sec-67b", "/sec-67b"))
    if "cgst" in lower and "section 67" in lower:
        return ("cgst" in item_blob or "central goods and services tax" in item_blob) and "sec-67" in item_blob
    if "income" in lower and ("206c" in lower or "tcs" in lower):
        return "income" in item_blob and ("sec-206c" in item_blob or "206c" in item_blob)
    if "commercial courts" in lower and "12a" in lower:
        return "commercial courts" in item_blob and ("sec-12a" in item_blob or "12a" in item_blob)
    if "commercial courts" in lower and _has(lower, ("pre-institution", "pre institution", "pre-litigation", "pre litigation", "mediation")):
        return "commercial courts" in item_blob and ("sec-12a" in item_blob or "12a" in item_blob)
    if "commercial courts" in lower:
        return "commercial courts" in item_blob and _has_any_anchor(item_blob, (
            "sec-2", "sec-6", "sec-7", "sec-12a", "sec-12-a",
            "/sec-2", "/sec-6", "/sec-7", "/sec-12a", "/sec-12-a",
        ))
    if "mediation act" in lower:
        return (
            "mediation act" in item_blob
            or "mediation-2023" in item_blob
        ) and _has_any_anchor(item_blob, (
            "sec-3", "sec-5", "sec-6", "sec-18", "sec-19",
            "sec-43", "/sec-3", "/sec-5", "/sec-6",
            "/sec-18", "/sec-19", "/sec-43",
        ))
    if _has(lower, ("witch", "witch-hunting", "witch hunting", "daain", "daayan", "tonhi", "tonahi")):
        if _has(q, ("assam", "barpeta")):
            return "assam-witch-hunting-2015" in item_blob or (
                "assam" in item_blob and "witch" in item_blob
            )
        if _has(q, ("jharkhand", "ranchi", "chaibasa", "gumla", "khunti", "simdega", "singhbhum")):
            return (
                ("bare_act" in item_blob or "official_guidance" in item_blob)
                and "jharkhand" in item_blob
                and ("witch" in item_blob or "daain" in item_blob or "daayan" in item_blob or "dayan" in item_blob)
            )
    if "witch" in lower and "jharkhand" in q:
        return (
            ("bare_act" in item_blob or "official_guidance" in item_blob)
            and "jharkhand" in item_blob
            and ("witch" in item_blob or "daain" in item_blob or "dayan" in item_blob)
        )
    if "arms act" in lower:
        if "definition" in lower or "farming tool" in lower or "agricultural" in lower:
            return (
                ("arms act" in item_blob or "arms-1959" in item_blob)
                and _has_any_anchor(item_blob, ("sec-2", "/sec-2"))
            )
        return (
            ("arms act" in item_blob or "arms-1959" in item_blob)
            and _has_any_anchor(item_blob, ("sec-2", "sec-4", "sec-25", "/sec-2", "/sec-4", "/sec-25"))
        )
    if "maharashtra control of organised crime" in lower or "mcoca" in lower:
        return (
            ("maharashtra control of organised crime" in item_blob or "mcoca" in item_blob)
            and ("sec-21" in item_blob or "/sec-21" in item_blob)
        )
    if _canonical_alias_match(lower, item_blob):
        return True
    if _constitutional_reproductive_precedent_match(lower, item_blob):
        return True
    if _has_statute_alias(lower, ("bnss", "crpc")):
        return _bnss_crpc_requirement_matches(lower, item_blob, q)
    if _has_statute_alias(lower, ("bns", "ipc")):
        return _bns_ipc_requirement_matches(lower, item_blob, q)
    return False


def _customs_requirement_matches(required_lower: str, item_blob: str, query_lower: str) -> bool:
    if "customs act" not in item_blob and "customs-1962" not in item_blob:
        return False

    # The route-required source label is intentionally broad ("ICEGATE,
    # duty, valuation, SVB, drawback, classification"). Issue type must
    # therefore come from the user's facts, not from the label itself.
    context = query_lower
    drawback_context = customs_drawback_issue(context)
    misdeclaration_context = customs_misdeclaration_issue(context)
    valuation_context = customs_svb_issue(context)
    classification_context = customs_classification_issue(context) or customs_assessment_issue(context)

    if drawback_context:
        core = ("sec-75", "sec-74", "sec-27", "/sec-75", "/sec-74", "/sec-27")
        if _has(context, ("appeal", "order", "rejection order", "commissioner")):
            return _has_any_anchor(item_blob, (*core, "sec-128", "/sec-128"))
        return _has_any_anchor(item_blob, core)
    if misdeclaration_context:
        return _has_any_anchor(item_blob, (
            "sec-124", "sec-111", "sec-112",
            "/sec-124", "/sec-111", "/sec-112",
        ))
    if valuation_context:
        return _has_any_anchor(item_blob, (
            "sec-14", "sec-17", "sec-28", "sec-128",
            "/sec-14", "/sec-17", "/sec-28", "/sec-128",
        ))
    if classification_context:
        return _has_any_anchor(item_blob, (
            "sec-17", "sec-28", "sec-128",
            "/sec-17", "/sec-28", "/sec-128",
        ))
    return _has_any_anchor(item_blob, (
        "sec-17", "sec-27", "sec-28", "sec-74", "sec-75",
        "sec-111", "sec-112", "sec-124", "sec-128",
        "/sec-17", "/sec-27", "/sec-28", "/sec-74", "/sec-75",
        "/sec-111", "/sec-112", "/sec-124", "/sec-128",
    ))


def _cgst_rule_86b_item_matches(item_blob: str) -> bool:
    return (
        (
            "cgst rules" in item_blob
            or "goods and services tax rules" in item_blob
            or "central goods and services tax rules" in item_blob
        )
        and _has(item_blob, (
            "86b", "86-b", "rule 86b", "rule 86-b",
            "electronic credit ledger", "ninety-nine per cent",
            "ninety nine per cent", "99 per cent",
            "cgst-rules-2017/sec-85", "cgst-rules-2017/sec-85-e",
        ))
    )


def _composite_route_source_match(
    required_source: str,
    passages: list[dict[str, Any]],
    *,
    query: str,
) -> dict[str, Any] | None:
    lower = required_source.lower()
    q = query.lower()
    if "cgst rules" in lower and "86b" in lower and "cgst act" in lower:
        matched: dict[str, dict[str, Any]] = {}
        for item in passages or []:
            if not isinstance(item, dict):
                continue
            blob = _item_blob(item)
            if "rule_86b" not in matched and _cgst_rule_86b_item_matches(blob):
                matched["rule_86b"] = item
            if "cgst_act_49" not in matched and (
                ("cgst" in blob or "goods and services tax" in blob)
                and "rules" not in blob
                and _has_any_anchor(blob, (
                    "sec-49", "sec-49a", "sec-49b",
                    "/sec-49", "/sec-49a", "/sec-49b",
                ))
            ):
                matched["cgst_act_49"] = item
        if len(matched) == 2:
            return {
                "title": "CGST Rule 86B and electronic-credit-ledger composite source",
                "anchor": f"{matched['rule_86b'].get('anchor')}; {matched['cgst_act_49'].get('anchor')}",
                "source_type": "aggregate",
            }
        return None
    if "pesa act" in lower and "forest rights" in lower:
        matched: dict[str, dict[str, Any]] = {}
        for item in passages or []:
            if not isinstance(item, dict):
                continue
            blob = _item_blob(item)
            if "pesa" not in matched and (
                ("pesa" in blob or "panchayats" in blob)
                and _has_any_anchor(blob, ("sec-4", "/sec-4"))
            ):
                matched["pesa"] = item
            if "forest_rights" not in matched and (
                (
                    "forest rights" in blob
                    or "scheduled tribes and other traditional forest dwellers" in blob
                    or "fra-2006" in blob
                )
                and (
                    "#header" in blob
                    or _has_any_anchor(blob, (
                        "sec-3", "sec-4", "sec-5", "sec-6",
                        "/sec-3", "/sec-4", "/sec-5", "/sec-6",
                    ))
                )
            ):
                matched["forest_rights"] = item
        if "forest_rights" in matched and not _has_pesa_trigger_context(q):
            return matched["forest_rights"]
        if len(matched) == 2:
            return {
                "title": "PESA/FRA composite route source",
                "anchor": f"{matched['pesa'].get('anchor')}; {matched['forest_rights'].get('anchor')}",
                "source_type": "aggregate",
        }
        return None
    if _is_bns_bnss_or_ipc_crpc_requirement(lower) and _has(lower, ("cheating", "forgery", "false register", "fake register")):
        bns_item = _find_regime_item(
            passages,
            title_terms=("bns", "bharatiya nyaya"),
            anchors=("sec-318", "sec-336", "sec-340", "/sec-318", "/sec-336", "/sec-340"),
        )
        bnss_item = _find_regime_item(
            passages,
            title_terms=("bnss", "bharatiya nagarik"),
            anchors=("sec-173", "sec-175", "/sec-173", "/sec-175"),
        )
        ipc_item = _find_regime_item(
            passages,
            title_terms=("ipc", "indian penal"),
            anchors=("sec-420", "sec-468", "sec-471", "/sec-420", "/sec-468", "/sec-471"),
        )
        crpc_item = _find_regime_item(
            passages,
            title_terms=("crpc", "criminal procedure"),
            anchors=("sec-154", "sec-156", "/sec-154", "/sec-156"),
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
    if "income tax" in lower and "80c" in lower and "80ccd" in lower:
        found: dict[str, dict[str, Any]] = {}
        for item in passages or []:
            if not isinstance(item, dict):
                continue
            blob = _item_blob(item)
            if "income tax" not in blob and "income-tax" not in blob:
                continue
            if "80c" not in found and _has_any_anchor(blob, ("sec-80c", "/sec-80c")):
                found["80c"] = item
            if "80ccd" not in found and _has_any_anchor(blob, ("sec-80ccd", "/sec-80ccd")):
                found["80ccd"] = item
        if len(found) == 2:
            return {
                "title": "Income-tax Act 1961 composite deduction source",
                "anchor": f"{found['80c'].get('anchor')}; {found['80ccd'].get('anchor')}",
                "source_type": "aggregate",
            }
        return None
    if "copyright act" in lower and _has(lower, ("infringement", "exception", "fair dealing", "civil remedies", "civil remedy")):
        needed = {
            "infringement": ("/sec-51", "sec-51"),
            "exceptions": ("/sec-52", "sec-52"),
            "remedies": ("/sec-55", "sec-55"),
        }
        matched: dict[str, dict[str, Any]] = {}
        for item in passages or []:
            if not isinstance(item, dict):
                continue
            blob = _item_blob(item)
            if "copyright" not in blob:
                continue
            for role, anchors in needed.items():
                if role in matched:
                    continue
                if _has_any_anchor(blob, anchors):
                    matched[role] = item
        if len(matched) == len(needed):
            return {
                "title": "Copyright Act 1957 composite route source",
                "anchor": "; ".join(str(matched[role].get("anchor") or "") for role in needed),
                "source_type": "aggregate",
            }
    return None


def _is_hard_composite_requirement(required_source: str) -> bool:
    lower = required_source.lower()
    return (
        ("pesa act" in lower and "forest rights" in lower)
        or ("cgst rules" in lower and "86b" in lower and "cgst act" in lower)
        or ("income tax" in lower and "80c" in lower and "80ccd" in lower)
        or (
            "copyright act" in lower
            and _has(lower, ("infringement", "exception", "fair dealing", "civil remedies", "civil remedy"))
        )
        or (
            _is_bns_bnss_or_ipc_crpc_requirement(lower)
            and _has(lower, ("cheating", "forgery", "false register", "fake register"))
        )
    )


def _is_hard_canonical_requirement(required_source: str) -> bool:
    lower = required_source.lower()
    return (
        _is_pmla_sc_precedent_requirement(lower)
        or _has_statute_alias(lower, ("bns", "ipc"))
        or (
            _has_statute_alias(lower, ("bnss", "crpc"))
            and re.search(r"\b(?:section|sec)\.?\s*\d+", lower) is not None
        )
        or (_has_statute_alias(lower, ("bnss", "crpc")) and "based on incident date" in lower)
        or "bocw cess" in lower
        or "welfare-board cess" in lower
        or "welfare board cess" in lower
        or "construction workers welfare cess" in lower
        or "building and other construction workers act" in lower
        or "bocw act" in lower
        or "bocw registration" in lower
        or "welfare-board provisions" in lower
        or "mental healthcare act" in lower
        or "mental-healthcare" in lower
        or (
            ("hindu marriage act" in lower or "special marriage act" in lower)
            and _has(lower, ("section 12", "sec 12", "section 13", "sec 13", "voidable", "divorce ground", "matrimonial relief"))
        )
    )


def _constitutional_reproductive_precedent_match(required_lower: str, item_blob: str) -> bool:
    if not _has(required_lower, (
        "reproductive autonomy", "privacy precedents", "reproductive privacy",
        "constitutional reproductive",
    )):
        return False
    return _has(item_blob, (
        "x versus the principal secretary",
        "principal secretary health and family welfare",
        "ms. z  versus the state of bihar",
        "ms. z versus the state of bihar",
        "suchita srivastava",
        "puttaswamy",
        "justice k.s. puttaswamy",
        "2017-insc-756",
        "2022-insc-740",
    ))


def _canonical_alias_match(required_lower: str, item_blob: str) -> bool:
    canonical_aliases: tuple[tuple[tuple[str, ...], tuple[str, ...], tuple[str, ...]], ...] = (
        (
            ("motor vehicles act", "driving licence", "traffic enforcement", "traffic challan", "permit"),
            ("motor vehicles act", "themotorvehiclesact"),
            ("sec-3", "sec-4", "sec-19", "sec-74", "sec-130", "sec-177", "sec-182", "sec-183", "sec-200", "sec-206", "/sec-3", "/sec-4", "/sec-19", "/sec-74", "/sec-130", "/sec-177", "/sec-182", "/sec-183", "/sec-200", "/sec-206"),
        ),
        (
            ("motor vehicles act", "aggregator licensing", "aggregator licence", "aggregator"),
            ("motor vehicle aggregator guidelines", "motor vehicles act", "themotorvehiclesact"),
            ("driver-service-contract", "app-transparency-grievance", "non-discrimination-driver-fare", "sec-93", "sec-193", "/sec-93", "/sec-193"),
        ),
        (
            ("guardians and wards", "custody principles", "child custody"),
            ("guardians and wards", "guardian and wards", "guardians-wards"),
            ("sec-7", "sec-17", "sec-25", "/sec-7", "/sec-17", "/sec-25"),
        ),
        (
            ("shops and establishments", "shop act", "shops establishment"),
            ("shops and commercial establishments", "shops establishments", "shop establishment"),
            ("sec-2", "sec-4", "sec-5", "registration-fee-checklist", "/sec-2", "/sec-4", "/sec-5"),
        ),
        (
            ("national food security", "tpds", "ration entitlement"),
            ("national food security",),
            ("sec-3", "sec-12", "sec-14", "sec-15", "/sec-3", "/sec-12", "/sec-14", "/sec-15"),
        ),
        (
            ("protection of civil rights", "temple", "well/water", "public-access"),
            ("protection of civil rights",),
            ("sec-3", "sec-4", "sec-7", "/sec-3", "/sec-4", "/sec-7"),
        ),
        (
            ("customs act", "icegate", "import/export", "drawback", "classification", "valuation", "svb"),
            ("customs act",),
            (
                "sec-14", "sec-17", "sec-18", "sec-27", "sec-28",
                "sec-74", "sec-75", "sec-111", "sec-112", "sec-124",
                "sec-128", "sec-129a", "/sec-14", "/sec-17", "/sec-18",
                "/sec-27", "/sec-28", "/sec-74", "/sec-75", "/sec-111",
                "/sec-112", "/sec-124", "/sec-128", "/sec-129a",
            ),
        ),
        (
            ("banking regulation act", "bank-service dispute", "banking grievance", "education-loan refusal", "education loan refusal", "rbi/banking grievance", "rbi integrated ombudsman", "rbi integrated ombudsman scheme"),
            ("banking regulation", "reserve bank integrated ombudsman", "rbi integrated ombudsman"),
            ("#header", "sec-2", "sec-20", "sec-35a", "sec-35-a", "sec-45za", "sec-45-za", "/sec-2", "/sec-20", "/sec-35a", "/sec-35-a", "/sec-45za", "/sec-45-za"),
        ),
        (
            ("negotiable instruments act", "negotiable instrument", "ni act", "cheque dishonour"),
            ("negotiable instruments",),
            ("sec-138", "sec-141", "sec-142", "/sec-138", "/sec-141", "/sec-142"),
        ),
        (
            ("code of civil procedure", "cpc", "order xxi", "order 21", "execution procedure", "execution petition", "decree", "summons", "plaint rejection", "threshold objections"),
            ("code of civil procedure", "cpc"),
            ("sec-51", "sec-47", "sec-108", "sec-151", "sec-96", "sec-100", "sec-24", "sec-33", "sec-65", "sec-89", "/sec-51", "/sec-47", "/sec-108", "/sec-151", "/sec-96", "/sec-100", "/sec-24", "/sec-33", "/sec-65", "/sec-89"),
        ),
        (
            ("nclt", "ibc application", "application forms"),
            ("national company law tribunal", "nclt"),
            ("rule-6", "rule-10", "rule-11", "rule-23", "rule-34", "rule-35", "/rule-6", "/rule-10", "/rule-11", "/rule-23", "/rule-34", "/rule-35"),
        ),
        (
            ("nclat", "certified-copy", "certified copy", "limitation facts", "forms, fees"),
            ("national company law appellate tribunal", "nclat"),
            ("rule-22", "rule-23", "rule-26", "rule-48", "rule-50", "/rule-22", "/rule-23", "/rule-26", "/rule-48", "/rule-50"),
        ),
        (
            ("food safety", "fssai", "food business", "misbranding", "improvement notice"),
            ("food safety", "fssai"),
            ("sec-26", "sec-31", "sec-32", "sec-42", "sec-50", "sec-59", "sec-63", "/sec-26", "/sec-31", "/sec-32", "/sec-42", "/sec-50", "/sec-59", "/sec-63"),
        ),
        (
            ("limited liability partnership", "llp"),
            ("limited liability partnership", "llp"),
            ("sec-35", "sec-75", "sec-75-a", "sec-75-b", "sec-75-c", "/sec-35", "/sec-75", "/sec-75-a", "/sec-75-b", "/sec-75-c"),
        ),
        (
            ("sarfaesi", "securitisation", "security interest"),
            ("sarfaesi", "securitisation", "security interest"),
            ("sec-13", "sec-17", "/sec-13", "/sec-17"),
        ),
        (
            ("state land revenue", "mutation", "pattadar", "land record", "land revenue"),
            ("pattadar", "rights in land", "land revenue", "mutation", "chota nagpur tenancy", "santhal parganas tenancy"),
            ("sec-3", "sec-4", "sec-5", "sec-6", "sec-9", "sec-10", "sec-46", "sec-71-a", "/sec-3", "/sec-4", "/sec-5", "/sec-6", "/sec-9", "/sec-10", "/sec-46", "/sec-71-a"),
        ),
        (
            ("family law statute", "personal law by religion", "personal law", "marriage statute"),
            ("hindu marriage", "special marriage", "muslim personal", "dissolution of muslim", "family courts"),
            ("sec-5", "sec-7", "sec-9", "sec-12", "sec-13", "sec-13b", "sec-13-b", "sec-24", "sec-25", "sec-27", "/sec-5", "/sec-7", "/sec-9", "/sec-12", "/sec-13", "/sec-13b", "/sec-13-b", "/sec-24", "/sec-25", "/sec-27"),
        ),
        (
            ("aadhaar act", "aadhaar authentication", "identity information", "uidai"),
            ("aadhaar", "unique identification"),
            ("sec-7", "sec-8", "sec-29", "sec-59", "/sec-7", "/sec-8", "/sec-29", "/sec-59"),
        ),
        (
            ("copyright act", "creative work", "logo"),
            ("copyright",),
            ("sec-51", "sec-55", "/sec-51", "/sec-55"),
        ),
        (
            ("protection of human rights", "human rights act", "nhrc", "shrc"),
            ("protection of human rights", "human-rights"),
            ("sec-12", "sec-13", "sec-17", "sec-30", "/sec-12", "/sec-13", "/sec-17", "/sec-30"),
        ),
        (
            ("motor vehicles act", "insurance", "claims tribunal", "mact", "third party"),
            ("motor vehicles act", "themotorvehiclesact"),
            ("sec-134", "sec-146", "sec-147", "sec-149", "sec-164", "sec-165", "sec-166", "/sec-134", "/sec-146", "/sec-147", "/sec-149", "/sec-164", "/sec-165", "/sec-166"),
        ),
        (
            ("insurance ombudsman", "insurer grievance", "insurance grievance", "claim repudiation", "claim rejection"),
            ("insurance ombudsman rules", "insurance ombudsman"),
            ("sec-3", "sec-4", "sec-5", "sec-6", "sec-13", "sec-14", "sec-15", "sec-16", "sec-17", "/sec-3", "/sec-4", "/sec-5", "/sec-6", "/sec-13", "/sec-14", "/sec-15", "/sec-16", "/sec-17"),
        ),
        (
            ("clinical establishments", "clinical-establishment", "hospital records", "hospital billing", "hospital records, billing"),
            ("clinical establishments", "clinical establishment"),
            ("sec-11", "sec-12", "sec-33", "sec-42", "/sec-11", "/sec-12", "/sec-33", "/sec-42"),
        ),
        (
            ("medical council", "medical ethics", "professional-conduct", "professional conduct"),
            ("medical ethics", "professional conduct", "medical council"),
            ("reg-1.3.1", "reg-1.3.2", "reg-7.2"),
        ),
        (
            ("national green tribunal", "environmental relief", "environmental compensation"),
            ("national green tribunal", "ngt"),
            ("sec-14", "sec-15", "sec-16", "sec-18", "/sec-14", "/sec-15", "/sec-16", "/sec-18"),
        ),
        (
            ("companies act", "annual filing", "director disqualification", "restoration"),
            ("companies act",),
            ("sec-92", "sec-137", "sec-164", "sec-167", "sec-248", "sec-252", "/sec-92", "/sec-137", "/sec-164", "/sec-167", "/sec-248", "/sec-252"),
        ),
        (
            ("rfctlarr", "land acquisition", "compensation award", "reference-to-authority", "reference to authority"),
            ("right to fair compensation", "rfctlarr", "land acquisition"),
            ("sec-31", "sec-38", "sec-64", "sec-77", "/sec-31", "/sec-38", "/sec-64", "/sec-77"),
        ),
        (
            ("legal services authorities", "under trial review committee", "under-trial review committee", "utrc"),
            ("legal services authorities",),
            ("sec-9", "sec-12", "sec-13", "sec-21", "/sec-9", "/sec-12", "/sec-13", "/sec-21"),
        ),
        (
            ("real estate", "rera"),
            ("real estate", "rera"),
            ("sec-11", "sec-14", "sec-18", "sec-31", "sec-34", "/sec-11", "/sec-14", "/sec-18", "/sec-31", "/sec-34"),
        ),
        (
            ("prevention of money laundering", "pmla", "twin condition", "money laundering"),
            ("prevention of money laundering", "pmla"),
            ("sec-19", "sec-45", "/sec-19", "/sec-45"),
        ),
        (
            ("compoundability", "compoundable", "offence-compoundability", "court permission"),
            ("bnss", "bharatiya nagarik", "crpc", "criminal procedure"),
            ("sec-359", "sec-320", "/sec-359", "/sec-320"),
        ),
        (
            ("specific relief act", "injunction", "specific performance", "negative covenant", "exclusivity"),
            ("specific relief",),
            ("sec-31", "sec-34", "sec-38", "sec-42", "/sec-31", "/sec-34", "/sec-38", "/sec-42"),
        ),
    )
    for required_aliases, title_aliases, anchor_aliases in canonical_aliases:
        if not _has(required_lower, required_aliases):
            continue
        if not _has(item_blob, title_aliases):
            continue
        if anchor_aliases and not _has_any_anchor(item_blob, anchor_aliases):
            continue
        return True
    return False


def _is_dual_regime_requirement(required_source: str) -> bool:
    lower = required_source.lower()
    return (
        "bnss" in lower
        and "crpc" in lower
        and (
            "based on incident date" in lower
            or "based on incident/procedure date" in lower
            or "based on procedure date" in lower
        )
    )


def _dual_regime_source_match(
    required_source: str,
    passages: list[dict[str, Any]],
    *,
    query: str,
) -> dict[str, Any] | None:
    lower = required_source.lower()
    q = query.lower()
    anchors = _bnss_crpc_anchor_terms(lower)
    if _has_default_bail_query_context(q) and _has(lower, (
        "default bail", "default-bail", "no chargesheet", "no charge sheet",
        "undertrial", "under-trial", "custody",
    )):
        anchors = {
            "bnss": ("sec-187", "/sec-187"),
            "crpc": ("sec-167", "/sec-167"),
        }
    is_offence_plus_procedure = _is_bns_bnss_or_ipc_crpc_requirement(lower)
    if is_offence_plus_procedure and _has(q, (
        "cyber", "online", "instagram", "insta", "whatsapp", "telegram",
        "deepfake", "morphed", "intimate", "private video", "private photo",
        "blackmail", "extort", "extorting", "threat", "threatening",
        "fake account", "fake profile", "otp", "upi",
    )) and not _has(q, ("bail", "arrest", "arrested", "custody", "remand", "anticipatory")):
        anchors = {
            "bnss": ("sec-173", "sec-175", "/sec-173", "/sec-175"),
            "crpc": ("sec-154", "sec-156", "sec-200", "/sec-154", "/sec-156", "/sec-200"),
        }
    if is_offence_plus_procedure and _has_cyber_notice_no_paper_context(q):
        anchors = {
            "bnss": ("sec-35", "sec-173", "sec-175", "/sec-35", "/sec-173", "/sec-175"),
            "crpc": (
                "sec-41a", "sec-41-a", "sec-154", "sec-156", "sec-200",
                "/sec-41a", "/sec-41-a", "/sec-154", "/sec-156", "/sec-200",
            ),
        }
    offence_anchors = _bns_ipc_anchor_terms(lower, q) if is_offence_plus_procedure else ()
    bns_item = _find_regime_item(
        passages,
        title_terms=("bns", "bharatiya nyaya"),
        anchors=offence_anchors,
    )
    bnss_item = _find_regime_item(
        passages,
        title_terms=("bnss", "bharatiya nagarik"),
        anchors=anchors["bnss"],
    )
    ipc_item = _find_regime_item(
        passages,
        title_terms=("ipc", "indian penal"),
        anchors=offence_anchors,
    )
    crpc_item = _find_regime_item(
        passages,
        title_terms=("crpc", "criminal procedure"),
        anchors=anchors["crpc"],
    )
    if is_offence_plus_procedure and _has_cyber_notice_no_paper_context(q):
        if _query_points_to_old_criminal_regime(q):
            return crpc_item
        if _query_points_to_new_criminal_regime(q):
            return bnss_item
        return bnss_item or crpc_item
    if is_offence_plus_procedure:
        if _query_points_to_old_criminal_regime(q):
            return _criminal_regime_pair_item(
                "IPC/CrPC composite route source",
                ipc_item,
                crpc_item,
            )
        if _query_points_to_new_criminal_regime(q):
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
    if _query_points_to_old_criminal_regime(q):
        return crpc_item
    if _query_points_to_new_criminal_regime(q):
        return bnss_item
    if _has(lower, ("chargesheet", "charge sheet", "charge-sheet", "police report", "summons", "discharge")):
        return bnss_item or crpc_item
    if not _requires_dual_procedure_counterpart(q, lower):
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


def _has_cyber_notice_no_paper_context(q: str) -> bool:
    cyber_notice = _has(q, (
        "cyber case", "cyber police", "cyber cell", "notice in cyber",
        "cyber notice", "police calling", "police called", "calling me",
    ))
    no_paper = _has(q, (
        "not giving paper", "without paper", "no paper", "no written",
        "no written notice", "not giving notice", "written notice",
    ))
    return cyber_notice and no_paper


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


def _requires_dual_procedure_counterpart(query_lower: str, required_lower: str) -> bool:
    """Require both old/new procedure only when the facts make that risk real."""
    if _query_points_to_old_criminal_regime(query_lower) or _query_points_to_new_criminal_regime(query_lower):
        return True
    if _has_default_bail_query_context(query_lower):
        return True
    if _has(required_lower, (
        "default bail", "default-bail", "undertrial", "under-trial",
        "no chargesheet", "no charge sheet",
    )):
        return True
    if re.search(r"\b(?:[2-9]|1[0-9])\s*(?:month|months|yr|yrs|year|years)\b", query_lower):
        return True
    return _has(query_lower, (
        "long custody", "prolonged custody", "trial pending for",
        "pending 5 years", "pending five years",
    ))


def _find_regime_item(
    passages: list[dict[str, Any]],
    *,
    title_terms: tuple[str, ...],
    anchors: tuple[str, ...],
) -> dict[str, Any] | None:
    for item in passages or []:
        if not isinstance(item, dict):
            continue
        blob = _item_blob(item)
        if not _has_statute_alias(blob, title_terms):
            continue
        if anchors and not any(_anchor_term_matches(blob, anchor) for anchor in anchors):
            continue
        return item
    return None


def _bnss_crpc_requirement_matches(required_lower: str, item_blob: str, query_lower: str) -> bool:
    anchors = _bnss_crpc_anchor_terms(required_lower)
    if _has_default_bail_query_context(query_lower) and _has(required_lower, (
        "default bail", "default-bail", "no chargesheet", "no charge sheet",
        "undertrial", "under-trial", "custody",
    )):
        anchors = {
            "bnss": ("sec-187", "/sec-187"),
            "crpc": ("sec-167", "/sec-167"),
        }
    has_bnss = _has_statute_alias(item_blob, ("bnss", "bharatiya nagarik")) and _has_any_anchor(item_blob, anchors["bnss"])
    has_crpc = _has_statute_alias(item_blob, ("crpc", "criminal procedure")) and _has_any_anchor(item_blob, anchors["crpc"])
    requires_bnss = _has_statute_alias(required_lower, ("bnss", "bharatiya nagarik"))
    requires_crpc = _has_statute_alias(required_lower, ("crpc", "criminal procedure"))
    if requires_bnss and not requires_crpc:
        return has_bnss
    if requires_crpc and not requires_bnss:
        return has_crpc
    if "based on incident date" in required_lower:
        if _query_points_to_old_criminal_regime(query_lower):
            return has_crpc
        if _query_points_to_new_criminal_regime(query_lower):
            return has_bnss
        return has_bnss and has_crpc
    return has_bnss or has_crpc


def _bns_ipc_requirement_matches(required_lower: str, item_blob: str, query_lower: str) -> bool:
    has_bns = _has_statute_alias(item_blob, ("bns", "bharatiya nyaya"))
    has_ipc = _has_statute_alias(item_blob, ("ipc", "indian penal"))
    anchors = _bns_ipc_anchor_terms(required_lower, query_lower)
    if anchors and not _has_any_anchor(item_blob, anchors):
        return False
    if _query_points_to_old_criminal_regime(query_lower):
        return has_ipc
    if _query_points_to_new_criminal_regime(query_lower):
        return has_bns
    return has_bns or has_ipc


def _bns_ipc_anchor_terms(required_lower: str, query_lower: str) -> tuple[str, ...]:
    blob = f"{required_lower} {query_lower}"
    negated_extortion = _has_negated_extortion_money_context(query_lower)
    groups: list[tuple[str, tuple[str, ...]]] = [
        ("acid", ("sec-124", "sec-326a", "sec-326b", "/sec-124", "/sec-326a", "/sec-326b")),
        ("sexual", ("sec-63", "sec-64", "sec-65", "sec-67", "sec-69", "sec-70", "sec-74", "sec-75", "sec-76", "sec-77", "sec-78", "sec-79", "sec-354", "sec-354a", "sec-354b", "sec-354c", "sec-354d", "sec-376", "/sec-63", "/sec-64", "/sec-65", "/sec-67", "/sec-69", "/sec-70", "/sec-74", "/sec-75", "/sec-76", "/sec-77", "/sec-78", "/sec-79", "/sec-354", "/sec-354a", "/sec-354b", "/sec-354c", "/sec-354d", "/sec-376")),
        ("rape", ("sec-63", "sec-64", "sec-65", "sec-69", "sec-70", "sec-376", "/sec-63", "/sec-64", "/sec-65", "/sec-69", "/sec-70", "/sec-376")),
        ("promise", ("sec-69", "/sec-69")),
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
        ("breach of trust", ("sec-316", "sec-316-a", "sec-316-b", "sec-316-c", "sec-405", "sec-406", "/sec-316", "/sec-316-a", "/sec-316-b", "/sec-316-c", "/sec-405", "/sec-406")),
        ("entrust", ("sec-316", "sec-316-a", "sec-316-b", "sec-316-c", "sec-405", "sec-406", "/sec-316", "/sec-316-a", "/sec-316-b", "/sec-316-c", "/sec-405", "/sec-406")),
        ("forgery", ("sec-336", "sec-337", "sec-338", "sec-340", "sec-463", "sec-464", "sec-465", "sec-468", "sec-471", "/sec-336", "/sec-337", "/sec-338", "/sec-340", "/sec-463", "/sec-464", "/sec-465", "/sec-468", "/sec-471")),
        ("false document", ("sec-336", "sec-337", "sec-338", "sec-340", "sec-463", "sec-464", "sec-465", "sec-468", "sec-471", "/sec-336", "/sec-337", "/sec-338", "/sec-340", "/sec-463", "/sec-464", "/sec-465", "/sec-468", "/sec-471")),
        ("blank paper", ("sec-336", "sec-337", "sec-338", "sec-340", "sec-463", "sec-464", "sec-465", "sec-468", "sec-471", "/sec-336", "/sec-337", "/sec-338", "/sec-340", "/sec-463", "/sec-464", "/sec-465", "/sec-468", "/sec-471")),
        ("thumb impression", ("sec-336", "sec-337", "sec-338", "sec-340", "sec-463", "sec-464", "sec-465", "sec-468", "sec-471", "/sec-336", "/sec-337", "/sec-338", "/sec-340", "/sec-463", "/sec-464", "/sec-465", "/sec-468", "/sec-471")),
        ("theft", ("sec-303", "sec-305", "sec-317", "sec-378", "sec-379", "sec-411", "/sec-303", "/sec-305", "/sec-317", "/sec-378", "/sec-379", "/sec-411")),
        ("stolen", ("sec-303", "sec-305", "sec-317", "sec-378", "sec-379", "sec-411", "/sec-303", "/sec-305", "/sec-317", "/sec-378", "/sec-379", "/sec-411")),
        ("cruelty", ("sec-85", "sec-86", "sec-498a", "sec-498-a", "/sec-85", "/sec-86", "/sec-498a", "/sec-498-a")),
        ("dowry", ("sec-80", "sec-85", "sec-86", "sec-304b", "sec-304-b", "sec-498a", "sec-498-a", "/sec-80", "/sec-85", "/sec-86", "/sec-304b", "/sec-304-b", "/sec-498a", "/sec-498-a")),
        ("extort", ("sec-308", "sec-383", "sec-384", "/sec-308", "/sec-383", "/sec-384")),
        ("confinement", ("sec-126", "sec-127", "sec-146", "sec-339", "sec-340", "sec-341", "sec-342", "sec-374", "/sec-126", "/sec-127", "/sec-146", "/sec-339", "/sec-340", "/sec-341", "/sec-342", "/sec-374")),
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
        if term == "extort" and negated_extortion:
            continue
        if term in blob:
            anchors.extend(anchor for anchor in term_anchors if anchor not in anchors)
    return tuple(anchors)


def _has_negated_extortion_money_context(q: str) -> bool:
    return _has(q, (
        "not extorting", "not extort", "not extortion",
        "no extortion", "without extortion", "no money demand",
        "no money demanded", "not demanding money", "not demanded money",
        "did not demand money", "didn't demand money",
        "just threatening to share", "only threatening to share",
    ))


def _bnss_crpc_anchor_terms(required_lower: str) -> dict[str, tuple[str, ...]]:
    if _has(required_lower, ("search", "seizure", "seize")):
        return {
            "bnss": (
                "sec-105", "sec-173", "sec-175", "sec-187", "sec-480", "sec-483",
                "/sec-105", "/sec-173", "/sec-175", "/sec-187", "/sec-480", "/sec-483",
            ),
            "crpc": (
                "sec-100", "sec-102", "sec-154", "sec-156", "sec-165", "sec-167",
                "sec-437", "sec-438", "sec-439",
                "/sec-100", "/sec-102", "/sec-154", "/sec-156", "/sec-165", "/sec-167",
                "/sec-437", "/sec-438", "/sec-439",
            ),
        }
    if _has(required_lower, ("arrest",)) and _has(required_lower, ("fir", "remand", "bail")):
        return {
            "bnss": (
                "sec-35", "sec-47", "sec-48", "sec-57", "sec-58", "sec-173",
                "sec-175", "sec-187", "sec-480", "sec-483",
                "/sec-35", "/sec-47", "/sec-48", "/sec-57", "/sec-58",
                "/sec-173", "/sec-175", "/sec-187", "/sec-480", "/sec-483",
            ),
            "crpc": (
                "sec-41", "sec-50", "sec-56", "sec-57", "sec-154", "sec-156",
                "sec-167", "sec-437", "sec-438", "sec-439",
                "/sec-41", "/sec-50", "/sec-56", "/sec-57", "/sec-154",
                "/sec-156", "/sec-167", "/sec-437", "/sec-438", "/sec-439",
            ),
        }
    if _has(required_lower, ("default bail", "default-bail", "no chargesheet", "no charge sheet", "undertrial")):
        return {
            "bnss": ("sec-187", "sec-479", "/sec-187", "/sec-479"),
            "crpc": ("sec-167", "sec-436a", "sec-436-a", "/sec-167", "/sec-436a", "/sec-436-a", "/sec-436A"),
        }
    if _has(required_lower, ("chargesheet", "charge sheet", "charge-sheet", "police report", "discharge")):
        return {
            "bnss": (
                "sec-193", "sec-250", "sec-251", "sec-262", "sec-263",
                "sec-268", "sec-269", "sec-480", "sec-483",
                "/sec-193", "/sec-250", "/sec-251", "/sec-262", "/sec-263",
                "/sec-268", "/sec-269", "/sec-480", "/sec-483",
            ),
            "crpc": (
                "sec-173", "sec-227", "sec-239", "sec-245", "sec-437",
                "sec-438", "sec-439",
                "/sec-173", "/sec-227", "/sec-239", "/sec-245", "/sec-437",
                "/sec-438", "/sec-439",
            ),
        }
    if "bail" in required_lower:
        return {
            "bnss": ("sec-479", "sec-480", "sec-482", "sec-483", "/sec-479", "/sec-480", "/sec-482", "/sec-483"),
            "crpc": ("sec-436", "sec-436a", "sec-436-a", "sec-437", "sec-438", "sec-439", "/sec-436", "/sec-436a", "/sec-436-a", "/sec-437", "/sec-438", "/sec-439"),
        }
    if _has(required_lower, ("fir", "complaint", "investigation", "medical", "statement", "inquest")):
        return {
            "bnss": ("sec-173", "sec-175", "sec-176", "sec-180", "sec-183", "sec-184", "sec-223", "/sec-173", "/sec-175", "/sec-176", "/sec-180", "/sec-183", "/sec-184", "/sec-223"),
            "crpc": ("sec-154", "sec-156", "sec-157", "sec-174", "sec-176", "sec-190", "sec-200", "sec-202", "/sec-154", "/sec-156", "/sec-157", "/sec-174", "/sec-176", "/sec-190", "/sec-200", "/sec-202"),
        }
    if _has(required_lower, ("arrest", "detention", "production", "remand", "notice")):
        return {
            "bnss": ("sec-35", "sec-47", "sec-48", "sec-57", "sec-58", "sec-187", "/sec-35", "/sec-47", "/sec-48", "/sec-57", "/sec-58", "/sec-187"),
            "crpc": ("sec-41", "sec-50", "sec-56", "sec-57", "sec-160", "sec-167", "/sec-41", "/sec-50", "/sec-56", "/sec-57", "/sec-160", "/sec-167"),
        }
    return {
        "bnss": ("bnss", "bharatiya nagarik"),
        "crpc": ("crpc", "criminal procedure"),
    }


def _bail_arrest_safeguard_anchor_terms(query_lower: str, required_lower: str = "") -> tuple[str, ...]:
    if _has_default_bail_query_context(query_lower) and _has(required_lower, (
        "default bail", "default-bail", "no chargesheet", "no charge sheet",
        "undertrial", "under-trial",
    )):
        return (
            "sec-167", "sec-187", "/sec-167", "/sec-187",
        )
    arrest_procedure_context = _has(query_lower, (
        "arrest", "arrested", "detain", "detained", "custody", "picked",
        "pickup", "police took", "not produced", "24 hours",
        "twenty four hours", "arrest memo", "grounds of arrest",
        "lawyer during interrogation",
    ))
    bail_context = _has(query_lower, (
        "bail", "anticipatory", "default bail", "regular bail",
        "twin condition", "pmla", "surety",
    ))
    arrest_anchors = (
        "sec-35", "sec-41", "sec-47", "sec-48", "sec-50", "sec-56",
        "sec-57", "sec-58", "sec-160", "sec-167", "sec-187",
        "/sec-35", "/sec-41", "/sec-47", "/sec-48", "/sec-50",
        "/sec-56", "/sec-57", "/sec-58", "/sec-160", "/sec-167",
        "/sec-187",
    )
    bail_anchors = (
        "sec-436", "sec-436a", "sec-436-a", "sec-437", "sec-438",
        "sec-439", "sec-479", "sec-480", "sec-482", "sec-483",
        "/sec-436", "/sec-436a", "/sec-436-a", "/sec-437", "/sec-438",
        "/sec-439", "/sec-479", "/sec-480", "/sec-482", "/sec-483",
    )
    if arrest_procedure_context and not bail_context:
        return arrest_anchors
    if bail_context and not arrest_procedure_context:
        return bail_anchors
    return arrest_anchors + bail_anchors


def _has_default_bail_query_context(query_lower: str) -> bool:
    return _has(query_lower, (
        "default bail", "default-bail", "statutory bail",
        "no chargesheet", "no charge sheet", "no charge-sheet",
        "chargesheet not", "charge sheet not", "charge-sheet not",
        "no challan", "challan not", "no complaint filed",
        "complaint not filed", "no final report", "final report not",
    )) or re.search(r"\b(?:6[0-9]|[7-9][0-9]|1[0-9]{2})\s*days?\b", query_lower) is not None


def _has_any_anchor(blob: str, anchors: tuple[str, ...]) -> bool:
    return any(_anchor_term_matches(blob, anchor) for anchor in anchors)


def _has_separate_criminal_case_context(query_lower: str) -> bool:
    if _has_no_separate_criminal_case_context(query_lower):
        return False
    return _has(query_lower, (
        "fir", "police case", "criminal case", "criminal complaint",
        "arrest notice", "police notice", "station notice", "arrested",
        "arrest", "police called", "police station", "criminal court",
        "bns", "ipc", "bnss", "crpc", "498a", "rape case",
        "sexual offence", "section 85", "sec 85", "section 86", "sec 86",
    ))


def _has_no_separate_criminal_case_context(query_lower: str) -> bool:
    return _has(query_lower, (
        "no fir", "without fir", "no police case", "no criminal case",
        "no criminal complaint", "only notice", "just notice",
        "no arrest notice", "no police notice",
    )) and not _has(query_lower, (
        "separate fir", "fir under", "police sent arrest notice",
        "arrest notice under", "criminal complaint filed", "case registered",
        "arrested", "summoned in criminal court",
    ))


def _has_negated_family_criminal_force_context(query_lower: str) -> bool:
    return _has(query_lower, (
        "no assault", "no physical assault", "without assault",
        "no threat", "no threats", "without threat", "without threats",
        "no violence", "without violence", "no beating", "not beaten",
        "no injury", "no hurt", "no coercion", "not threatened",
        "not threatening", "no confinement", "not confined",
    ))


def _has_family_police_help_needed_context(query_lower: str) -> bool:
    if _has_no_separate_criminal_case_context(query_lower) or _has(query_lower, (
        "no police help", "police help not needed", "no police needed",
        "not going to police", "do not want police",
    )):
        return False
    return _has(query_lower, (
        "police", "fir", "emergency", "112", "100", "assault", "attack",
        "beat", "beaten", "hit", "hurt", "injury", "threat", "threaten",
        "threatening", "locked", "confinement", "forced", "coercion",
        "criminal complaint", "arrest", "arrested",
    )) and not _has_negated_family_criminal_force_context(query_lower)


def _has_marriage_validity_source_context(query_lower: str) -> bool:
    return _has(query_lower, (
        "hindu", "special marriage", "sma", "registered marriage",
        "court marriage", "voidable", "annulment", "annul", "fraud",
        "lied before marriage", "before marriage", "hidden", "concealed",
        "hid", "misrepresented", "misrepresentation", "gay", "lesbian",
        "same sex", "same-sex", "sexual orientation", "already married",
        "previous marriage", "prior marriage", "job", "salary", "health",
        "disease", "hiv", "adultery", "affair", "another woman",
        "another man", "caught", "having sex", "extra marital",
        "extramarital",
    ))


def _has_hindu_marriage_section_13_ground_anchor(item_blob: str) -> bool:
    if _has_any_exact_anchor(item_blob, ("sec-13", "/sec-13")):
        return True
    # The indexed HMA corpus splits some Section 13 grounds as sec-13-a/c/d,
    # while true neighboring sections appear as sec-13A/sec-13B. Accept only
    # the ground fragments we have verified from the corpus, not 13A/13B.
    return _has_any_exact_anchor(item_blob, (
        "sec-13-a", "sec-13-c", "sec-13-d",
        "/sec-13-a", "/sec-13-c", "/sec-13-d",
    ))


def _has_any_exact_anchor(blob: str, anchors: tuple[str, ...]) -> bool:
    return any(_exact_anchor_term_matches(blob, anchor) for anchor in anchors)


def _anchor_term_matches(blob: str, anchor: str) -> bool:
    normalized = anchor.lower().lstrip("/")
    if normalized.startswith("#"):
        return normalized in blob
    return bool(re.search(rf"(?<![a-z0-9])/?{re.escape(normalized)}(?![a-z0-9])", blob))


def _exact_anchor_term_matches(blob: str, anchor: str) -> bool:
    normalized = anchor.lower().lstrip("/")
    if normalized.startswith("#"):
        return normalized in blob
    return bool(re.search(rf"(?<![a-z0-9])/?{re.escape(normalized)}(?![-a-z0-9])", blob))


def _single_statute_section_match(required_lower: str, item_blob: str) -> bool:
    section_numbers = re.findall(r"\b(?:section|sec|s)\.?\s*([0-9]+[a-z]?)\b", required_lower)
    if not section_numbers:
        return False
    statute_terms = (
        (("bnss", "bharatiya nagarik"), ("bnss", "bharatiya nagarik")),
        (("crpc", "code of criminal procedure", "criminal procedure"), ("crpc", "code of criminal procedure", "criminal procedure")),
        (("bns", "bharatiya nyaya"), ("bns", "bharatiya nyaya")),
        (("ipc", "indian penal"), ("ipc", "indian penal")),
        (("code on wages",), ("code on wages",)),
        (("industrial disputes",), ("industrial disputes",)),
        (("indian contract", "contract act"), ("indian contract", "contract act")),
        (("constitution",), ("constitution",)),
        (("maharashtra control of organised crime", "mcoca"), ("maharashtra control of organised crime", "mcoca")),
    )
    if not any(
        _has_statute_alias(required_lower, required_terms)
        and _has_statute_alias(item_blob, item_terms)
        for required_terms, item_terms in statute_terms
    ):
        return False
    return any(_section_anchor_matches(item_blob, section) for section in section_numbers)


def _section_anchor_matches(item_blob: str, section: str) -> bool:
    normalized = section.lower()
    anchors = [f"sec-{normalized}", f"/sec-{normalized}"]
    split = re.match(r"^([0-9]+)([a-z])$", normalized)
    if split:
        numeric, suffix = split.groups()
        anchors.extend((f"sec-{numeric}-{suffix}", f"/sec-{numeric}-{suffix}"))
    return _has_any_anchor(item_blob, tuple(anchors))


def _constitution_article_requirement_match(required_source: str, passages: list[dict[str, Any]]) -> dict[str, Any] | None:
    lower = required_source.lower()
    article_numbers = re.findall(r"\barticles?\s+([0-9]+[a-z]?)\b", lower)
    if re.search(r"\barticle\s+22\b", lower) or re.search(r"\barticles\s+21\s+and\s+22\b", lower):
        article_numbers.append("22")
    if "lawyer-access" in lower or "lawyer access" in lower:
        for item in passages or []:
            if not isinstance(item, dict):
                continue
            blob = _item_blob(item)
            if _has(blob, ("constitution",)) and _has_any_anchor(blob, ("sec-22", "/sec-22")):
                return item
    article_numbers = sorted(set(article_numbers))
    if not article_numbers:
        return None
    if len(article_numbers) == 1:
        number = article_numbers[0]
        for item in passages or []:
            if not isinstance(item, dict):
                continue
            blob = _item_blob(item)
            if _has(blob, ("constitution",)) and _has_any_anchor(blob, (f"sec-{number}", f"/sec-{number}")):
                return item
        return None
    found: dict[str, dict[str, Any]] = {}
    for item in passages or []:
        if not isinstance(item, dict):
            continue
        blob = _item_blob(item)
        if not _has(blob, ("constitution",)):
            continue
        for number in article_numbers:
            if _has_any_anchor(blob, (f"sec-{number}", f"/sec-{number}")):
                found[number] = item
    if all(number in found for number in article_numbers):
        return {
            "title": "Constitution composite article source",
            "anchor": "; ".join(str(found[number].get("anchor") or "") for number in article_numbers),
            "source_type": "aggregate",
        }
    return None


def _query_points_to_old_criminal_regime(query_lower: str) -> bool:
    if _has(query_lower, (
        "before 1 july 2024", "before 01 july 2024", "before july 2024",
        "pre july 2024", "pre-july 2024", "pre-2024",
        "prior to 1 july 2024", "prior to 01 july 2024",
        "until 1 july 2024", "until 01 july 2024",
        "till 1 july 2024", "till 01 july 2024",
    )):
        return True
    if re.search(r"\b(?:before|pre|prior to|until|till)\s+0?1[-/]0?7[-/]2024\b", query_lower) is not None:
        return True
    if re.search(r"\b(?:before|pre|prior to|until|till)\s+2024[-/]0?7[-/]0?1\b", query_lower) is not None:
        return True
    if (
        re.search(r"\bjuly\s+1(?:st)?\s*,?\s*2024\b", query_lower) is not None
        and _has(query_lower, ("before", "pre", "prior to", "until", "till"))
    ):
        return True
    return any(marker < (2024, 7, 1) for marker in _criminal_regime_date_markers(query_lower))


def _query_points_to_new_criminal_regime(query_lower: str) -> bool:
    if _query_points_to_old_criminal_regime(query_lower):
        return False
    if _has(query_lower, ("after 1 july 2024", "after july 2024", "from 1 july 2024", "new bnss")):
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
        if year <= 2023:
            markers.append((year, 1, 1))
        elif year >= 2025:
            markers.append((year, 1, 1))
    return markers


def _looks_like_authority(lower: str) -> bool:
    return (
        bool(re.search(r"\bact\b|\bcode\b|\bregulations?\b|\brules?\b|\barticle\s+\d+", lower))
        or _has(lower, (
            "bns", "bnss", "bharatiya nyaya sanhita",
            "bharatiya nagarik suraksha sanhita",
            "bharatiya sakshya adhiniyam", "crpc", "ipc", "constitution", "ombudsman",
            "rbi", "cgst", "gst", "income tax", "customs", "pmla", "pocso",
            "pwdva", "nalsa", "dlsa", "statute", "nclt", "nclat",
            "compoundability", "compoundable", "compounding",
        ))
    )


def _source_tokens(text: str) -> set[str]:
    raw = re.findall(r"[a-z0-9]+", text.lower())
    return {token for token in raw if len(token) >= 3 and token not in _STOPWORDS}


def _coverage_score(tokens: set[str], blob: str) -> float:
    if not tokens:
        return 0.0
    hits = sum(1 for token in tokens if token in blob)
    return hits / len(tokens)


def _threshold(tokens: set[str]) -> float:
    if len(tokens) <= 2:
        return 1.0
    if len(tokens) <= 5:
        return 0.8
    return 0.65


def _item_blob(item: dict[str, Any]) -> str:
    return _blob(
        item.get("title"),
        item.get("anchor"),
        item.get("citation"),
        item.get("court"),
        item.get("source_type"),
        item.get("document_id"),
        item.get("statute_short"),
    )


def _blob(*parts: Any) -> str:
    values: list[str] = []
    for part in parts:
        if part is None:
            continue
        if isinstance(part, list):
            values.extend(str(item) for item in part)
        else:
            values.append(str(part))
    text = re.sub(r"\s+", " ", " ".join(values).lower())
    dehyphenated = text.replace("-", " ")
    return f"{text} {dehyphenated}" if dehyphenated != text else text


def _has(blob: str, terms: tuple[str, ...]) -> bool:
    return any(term in blob for term in terms)


def _has_trigger_term(blob: str, terms: tuple[str, ...]) -> bool:
    for term in terms:
        normalized = term.lower()
        if re.fullmatch(r"[a-z0-9]+", normalized):
            if re.search(rf"(?<![a-z0-9]){re.escape(normalized)}(?![a-z0-9])", blob):
                return True
            continue
        if normalized in blob:
            return True
    return False


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


def _is_delhi_prison_rules_blob(blob: str) -> bool:
    return "delhi prison rules" in blob or "delhi-prison-rules-2018" in blob


def _has_delhi_prison_query_context(query: str) -> bool:
    if _has(query, (
        "tihar", "mandoli", "rohini jail", "rohini prison",
        "delhi jail", "delhi prison", "central jail delhi",
    )):
        return True
    return "delhi" in query and _has(query, (
        "jail", "prison", "prisoner", "mulaqat", "mulakat",
        "parole", "furlough", "superintendent",
    ))


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
        and _has(item_blob, (
            "pmla", "money laundering", "prevention of money laundering",
            "vijay madanlal", "nikesh tarachand", "pankaj bansal",
            "senthil balaji", "saumya chaurasia", "tarsem lal",
        ))
    )
