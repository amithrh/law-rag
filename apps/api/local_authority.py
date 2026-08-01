"""Shared local-authority identity checks used by routing and source gaps.

The same query fact must drive both the matter route and the required-source
gate. Keeping the city-corporation qualifier here prevents those decisions
from silently diverging.
"""
from __future__ import annotations

import re


CITY_CORPORATION_NAMES = (
    "vadodara", "ahmedabad", "surat", "rajkot", "baroda", "pune",
    "nagpur", "nashik", "thane", "indore", "bhopal", "jaipur",
    "jodhpur", "lucknow", "kanpur", "patna", "coimbatore", "madurai",
    "chennai", "hyderabad", "bengaluru", "bangalore", "mumbai",
)

_PRIVATE_ENTITY_BEFORE_AUTHORITY = re.compile(
    r"\b(?:private|pvt)(?:\s+\w+){0,2}\s*$"
)
_NAMED_ENTITY_BEFORE_AUTHORITY = re.compile(
    r"\b(?:entity|company)\s+named\s+(?:the\s+)?$"
)
_OWNER_ENTITY_BEFORE_AUTHORITY = re.compile(
    r"\b(?:company|entity)\s+(?:that\s+)?owns?\s+(?:the\s+)?$"
)
_OWNER_VERB_AFTER_CORPORATION = re.compile(r"\b(?:that\s+)?owns\b")
_ENTITY_SUFFIX_AFTER_AUTHORITY = re.compile(
    r"^\s*(?:ltd|limited|company|entity)\b"
)
_ENTITY_IDENTITY_AFTER_AUTHORITY = re.compile(
    r"^\s+is\s+(?:my\s+)?(?:company|entity)\b"
)
_NAMED_PRIVATE_ACTOR = re.compile(r"\b(?:company|entity)\s+named\b")
_PRIVATE_CITY_CORPORATION = re.compile(
    r"\b(?:private|pvt)(?:\s+\w+){0,2}\s+corporation\b"
)

MUNICIPAL_AUTHORITY_TERMS = (
    "municipality", "municipal", "municipal corporation", "city corporation",
    "ward office", "nagar palika", "nagarpalika", "mcd", "bmc", "bbmp",
    "noida authority", "development authority", "local body", "local authority",
    "local health authority", "local health department", "municipal health department",
    "city health department", "local health inspector", "local health officer",
    "municipal health inspector", "municipal health officer", "panchayat",
    "nagar nigam", "town vending committee",
)


def _is_private_qualified_match(query: str, match: re.Match[str]) -> bool:
    before = query[max(0, match.start() - 48): match.start()]
    after = query[match.end(): min(len(query), match.end() + 32)]
    if _PRIVATE_ENTITY_BEFORE_AUTHORITY.search(before):
        return True
    if _NAMED_ENTITY_BEFORE_AUTHORITY.search(before):
        return True
    if re.search(r"\b(?:ltd|limited)\b", after):
        return True
    if _OWNER_ENTITY_BEFORE_AUTHORITY.search(before):
        return True
    return (
        _ENTITY_SUFFIX_AFTER_AUTHORITY.search(after) is not None
        or _ENTITY_IDENTITY_AFTER_AUTHORITY.search(after) is not None
    )


def has_qualified_city_corporation(text: str, *, city: str | None = None) -> bool:
    """Return whether *text* names a municipal city corporation.

    A bare ``corporation`` is intentionally insufficient. The city must be
    one of the known municipal identities, and nearby private-company or
    owner wording is excluded to avoid turning a business name into a local
    authority.
    """
    query = str(text or "").lower()
    cities = (str(city or "").strip().lower(),) if city else CITY_CORPORATION_NAMES
    for candidate in cities:
        if candidate not in CITY_CORPORATION_NAMES:
            continue
        for match in re.finditer(rf"\b{re.escape(candidate)}\s+corporation\b", query):
            after = query[match.end(): min(len(query), match.end() + 32)]
            if _is_private_qualified_match(query, match):
                continue
            if _OWNER_VERB_AFTER_CORPORATION.search(after):
                continue
            return True
    return False


def has_explicit_municipal_authority_context(text: str) -> bool:
    """Return whether a query identifies a local public authority.

    Bare ``corporation`` and generic ``authority`` are intentionally absent.
    A named city corporation or an explicit local-body term is required, and
    private-company wording adjacent to that term is rejected.
    """
    query = str(text or "").lower()
    if has_qualified_city_corporation(query):
        return True
    for term in MUNICIPAL_AUTHORITY_TERMS:
        for match in re.finditer(rf"\b{re.escape(term)}\b", query):
            if not _is_private_qualified_match(query, match):
                return True
    return False


_PRIVATE_ACTOR_TERMS = (
    "landlord", "security guard", "security agency", "premises operator",
    "private premises operator", "shop owner", "private owner", "private company",
    "private corporation", "a company", "company", "entity", "operator", "owner",
)
_ENFORCEMENT_TERMS = (
    "sealed", "sealing", "closed", "closure", "locked", "removed", "seized",
    "took", "taken", "confiscated", "demolished",
)
_VENDOR_OBJECT_TERMS = (
    "cart", "stall", "hawker", "vendor", "street vending", "vending goods",
    "vendor goods", "vegetable", "fruit", "thela", "rehri",
)
_BUSINESS_OBJECT_TERMS = (
    "shop", "restaurant", "hotel", "factory", "clinic", "godown", "warehouse",
    "premises", "showroom", "business", "office",
)


def _has_private_actor_enforcement_context(
    text: str,
    object_terms: tuple[str, ...],
) -> bool:
    query = str(text or "").lower()
    if not any(term in query for term in object_terms):
        return False
    for action in _ENFORCEMENT_TERMS:
        for action_match in re.finditer(rf"\b{re.escape(action)}\b", query):
            before = query[max(0, action_match.start() - 88): action_match.start()]
            actor_matches = [
                match
                for term in _PRIVATE_ACTOR_TERMS
                for match in re.finditer(rf"\b{re.escape(term)}\b", before)
            ]
            if _NAMED_PRIVATE_ACTOR.search(before):
                return True
            if not actor_matches:
                continue
            actor_match = max(actor_matches, key=lambda match: match.end())
            between = query[actor_match.end(): action_match.start()]
            if has_explicit_municipal_authority_context(between):
                continue
            after = query[action_match.end(): action_match.end() + 64]
            if re.search(r"\b(?:by|from)\b", after) and has_explicit_municipal_authority_context(after):
                continue
            return True
    return False


def has_private_vendor_actor_context(text: str) -> bool:
    """Return whether a private actor, rather than a public body, took action."""
    return _has_private_actor_enforcement_context(text, _VENDOR_OBJECT_TERMS)


def has_private_business_actor_context(text: str) -> bool:
    """Return whether a private actor is the apparent business-closure actor."""
    return _has_private_actor_enforcement_context(text, _BUSINESS_OBJECT_TERMS)


def has_specific_hawker_corporation_context(text: str) -> bool:
    """Return whether a bare corporation reference is a specific public-vendor fact.

    A hawker/vending permit plus a concrete corporation removal/seizure is a
    useful public-body signal even when a user omits the city. The predicate
    stays deliberately narrow and rejects named private entities and other
    private-actor wording.
    """
    query = str(text or "").lower()
    if has_explicit_municipal_authority_context(query):
        return False
    if has_private_vendor_actor_context(query):
        return False
    if not re.search(r"\bcorporation\b", query):
        return False
    if not any(
        term in query
        for term in (
            "hawker license", "hawker licence", "vending license",
            "vending licence", "vending certificate", "certificate of vending",
        )
    ):
        return False
    if not any(
        term in query
        for term in (
            "corporation removed", "corporation seized", "corporation took",
            "corporation demolished", "corporation evicted",
        )
    ):
        return False
    if (
        _NAMED_PRIVATE_ACTOR.search(query)
        or _PRIVATE_CITY_CORPORATION.search(query)
        or _has_any_private_marker(query)
    ):
        return False
    return True


def _has_any_private_marker(query: str) -> bool:
    return any(
        marker in query
        for marker in (
            "private company", "private corporation", "private operator",
            "landlord", "security guard", "security agency", "shop owner",
            "private owner", "company that owns", "corporation that owns",
            "is my company", "is my entity",
        )
    )
