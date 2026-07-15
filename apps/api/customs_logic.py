"""Customs Act query-shape helpers shared by routing, source gaps, and answers."""
from __future__ import annotations


def _has_any(text: str, terms: tuple[str, ...]) -> bool:
    lower = text.lower()
    return any(term in lower for term in terms)


def customs_drawback_negated(text: str) -> bool:
    return _has_any(text, (
        "no drawback", "not drawback", "not a drawback", "not claiming drawback",
        "without drawback", "no refund claim", "not a refund claim",
        "without refund", "no export incentive", "not export incentive",
        "only port code", "only amendment", "only correction",
    ))


def customs_misdeclaration_negated(text: str) -> bool:
    return _has_any(text, (
        "no misdeclaration", "not misdeclaration", "not a misdeclaration",
        "no penalty", "not penalty", "not a penalty", "not a penalty issue",
        "not penalty issue", "no confiscation", "not confiscation",
        "only assessment", "only assessment query", "only correction",
    ))


def customs_svb_negated(text: str) -> bool:
    return _has_any(text, (
        "no svb", "svb not opened", "without svb", "no valuation dispute",
        "not valuation", "not a valuation",
    ))


def customs_related_party_negated(text: str) -> bool:
    return _has_any(text, (
        "no related party", "no related-party", "not related party",
        "not related-party", "not a related party",
    ))


def customs_drawback_issue(text: str) -> bool:
    if customs_drawback_negated(text):
        return False
    lower = text.lower()
    return (
        _has_any(lower, (
            "drawback", "duty refund", "refund rejected", "rejected drawback",
            "export incentive", "export benefit",
        ))
        or (
            _has_any(lower, ("shipping bill", "export"))
            and _has_any(lower, ("claim rejected", "rejected", "mismatch", "mismatched"))
        )
    )


def customs_misdeclaration_issue(text: str) -> bool:
    if customs_misdeclaration_negated(text):
        return False
    lower = text.lower()
    return (
        _has_any(lower, (
            "misdeclaration", "misdeclared", "show cause", "scn",
            "confiscation", "penalty",
        ))
        or (
            _has_any(lower, ("icegate", "bill of entry", "port hold"))
            and _has_any(lower, ("hold", "on hold", "detained", "detention", "blocked"))
        )
    )


def customs_svb_issue(text: str) -> bool:
    if customs_svb_negated(text):
        return False
    if _has_any(text, ("svb", "special valuation branch", "valuation", "declared value")):
        return True
    return _has_any(text, ("related party", "related-party")) and not customs_related_party_negated(text)


def customs_classification_issue(text: str) -> bool:
    return _has_any(text, (
        "classification", "reclassified", "reclassification", "tariff",
        "hss", "hsn", "wire harness", "higher duty",
    ))


def customs_assessment_issue(text: str) -> bool:
    return _has_any(text, (
        "bill of entry", "assessment", "assessed", "reassessed",
        "duty demand",
    ))
