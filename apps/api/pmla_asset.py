"""Shared fact predicates for the PMLA asset-restraint workflow."""

from __future__ import annotations

import re


_PMLA_TERMS = ("pmla", "money laundering", "enforcement directorate", "ecir")
_ATTACHMENT_TERMS = (
    "provisional attachment", "attachment order", "property attachment",
    "section 5", "sec 5", "pao",
)
_ASSET_RE = (
    r"(?:bank\s+account|current\s+account|savings\s+account|account|"
    r"fixed\s+deposit|\bfd\b|demat\s+account|demat|locker|property|house|"
    r"flat|land|plot|vehicle|jewellery|jewelry|gold|shares?|securities|"
    r"funds?|money|assets?)"
)
_RESTRAINT_ACTION_RE = (
    r"(?:freez(?:e|ing)|frozen|froze|block(?:ed|ing)?|lock(?:ed|ing)?|"
    r"restrain(?:ed|ing)?|restraint|seiz(?:e|ed|ure)|lien(?:-marked|\s+marked)?|"
    r"hold|took\s+(?:physical\s+)?(?:possession|custody)|"
    r"taken\s+(?:physical\s+)?(?:possession|custody))"
)
_ASSET_TOKEN_RE = rf"\b{_ASSET_RE}\b(?!\s+(?:statement|records?|papers?|documents?|details?|information|proof)\b)"


def _has_any(text: str, terms: tuple[str, ...]) -> bool:
    return any(term in text for term in terms)


def _has_dealing_prohibition(text: str) -> bool:
    return re.search(
        r"\b(?:prohibit(?:ed|s|ing)?|barred|prevented|cannot|can't|not allowed)\b"
        r".{0,28}\bdeal(?:ing)?\b",
        text,
    ) is not None


def _has_asset_restraint_action(text: str) -> bool:
    if _has_any(
        text,
        (
            "provisional attachment",
            "attachment order",
            "freezing order",
            "section 5 order",
            "sec 5 order",
            "section 17 order",
            "sec 17 order",
            "pao",
        ),
    ):
        return True
    if re.search(
        r"\bblock(?:ed|ing)?\b.{0,24}\b(?:lawyer|advocate|representative|me|us|him|her)\b"
        r".{0,18}\bfrom\s+access(?:ing)?\b",
        text,
    ):
        return False
    paired = (
        rf"\b{_RESTRAINT_ACTION_RE}\b.{{0,48}}{_ASSET_TOKEN_RE}",
        rf"{_ASSET_TOKEN_RE}.{{0,48}}\b{_RESTRAINT_ACTION_RE}\b",
    )
    if any(re.search(pattern, text) is not None for pattern in paired):
        return True
    direct_transfer_bar = re.search(
        r"\b(?:must\s+not|cannot|can't|not\s+allowed\s+to|barred\s+from|"
        r"prohibited\s+from)\s+(?:sell|transfer|operate|withdraw|deal(?:ing)?)\b"
        rf".{{0,48}}{_ASSET_TOKEN_RE}",
        text,
    )
    reported_transfer_bar = re.search(
        r"\b(?:told|asked|directed|ordered|said)\b.{0,18}"
        r"\b(?:not\s+to|do\s+not)\s+(?:sell|transfer|operate|withdraw|deal(?:ing)?)\b"
        rf".{{0,48}}{_ASSET_TOKEN_RE}",
        text,
    )
    return direct_transfer_bar is not None or reported_transfer_bar is not None


def _has_attachment_restraint_action(text: str) -> bool:
    if _has_any(text, _ATTACHMENT_TERMS):
        return True
    return re.search(
        rf"\battach(?:ed|ing)?\b.{{0,32}}{_ASSET_TOKEN_RE}",
        text,
    ) is not None


def has_pmla_enforcement_context(text: str) -> bool:
    if _has_any(text, _PMLA_TERMS):
        return True
    ed_masked = re.sub(
        r"\bed\s+tech(?:nology)?\b|\bed-tech(?:nology)?\b",
        "edtech",
        text,
    )
    return bool(re.search(r"(?<![-\w])ed(?![-\w])", ed_masked)) and _has_any(
        text,
        (
            "notice", "order", "freeze", "freezing", "frozen", "froze",
            "attachment", "attached", "raid", "summons", "arrest", "arrested",
            "restrain",
            "restrained", "seize", "seized", "seizure",
            "hold", "lien", "locked", "took possession", "cannot operate",
            "took physical custody", "physical custody", "must not transfer",
            "do not transfer", "not to transfer", "prohibited",
        ),
    )


def is_pmla_asset_restraint_context(text: str) -> bool:
    return has_pmla_enforcement_context(text) and (
        _has_asset_restraint_action(text) or _has_dealing_prohibition(text)
    )


def is_pmla_provisional_attachment_context(text: str) -> bool:
    return is_pmla_asset_restraint_context(text) and _has_attachment_restraint_action(text)


def is_pmla_section17_restraint_context(text: str) -> bool:
    return (
        is_pmla_asset_restraint_context(text)
        and not is_pmla_provisional_attachment_context(text)
        and _has_any(
            text,
            (
                "freeze", "freezing", "frozen", "froze", "freezing order",
                "seize", "seized", "seizure", "section 17", "sec 17",
                "took possession", "taken possession", "took physical custody",
                "taken physical custody",
            ),
        )
    )


def is_pmla_ambiguous_restraint_context(text: str) -> bool:
    return (
        is_pmla_asset_restraint_context(text)
        and not is_pmla_provisional_attachment_context(text)
        and not is_pmla_section17_restraint_context(text)
    )


def is_pmla_seizure_context(text: str) -> bool:
    return _has_any(
        text,
        (
            "seize", "seized", "seizure", "took possession", "taken possession",
            "took physical custody", "taken physical custody",
        ),
    )
