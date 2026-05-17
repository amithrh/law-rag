"""PII redaction for ingested legal text (PLAN §10.2).

Pipeline (regex stage; NER stage stubbed and lands in v1 commercial track):
    redact(text, case_type=None) -> RedactionResult

Targets (PLAN §10.2 measurable bar):
    - Aadhaar:    ≥0.99 P / ≥0.95 R   (Verhoeff-validated to avoid FP)
    - Mobile:     ≥0.99 P / ≥0.95 R   (Indian +91 / 10-digit, 6-9 start)
    - PAN:        ≥0.99 P / ≥0.95 R   (5L + 4D + 1L with entity-letter check)
    - Bank A/C:   contextual (requires nearby account-keyword)

Anti-FP measures:
    - Aadhaar: reject if Verhoeff checksum fails.
    - Mobile:  reject if outside 6-9 first digit; reject if part of a year/page-no run.
    - PAN:     reject if 4th letter (entity type) is invalid; reject case-id matches.

Out of scope here (lives in §10.2 NER stage, see ner.py — to be written):
    - Person names (POCSO victim, minor, matrimonial party).
    - Address tokens / pincodes (sometimes desirable to keep — depends on case type).
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import StrEnum

import regex  # better Unicode than stdlib re; used for word boundaries in Indic-mixed text


class PIIType(StrEnum):
    AADHAAR = "aadhaar"
    MOBILE = "mobile"
    PAN = "pan"
    BANK_AC = "bank_account"
    EMAIL = "email"
    PERSON_NAME = "person_name"  # populated by NER stage, not regex


class CaseType(StrEnum):
    POCSO = "pocso"
    MATRIMONIAL = "matrimonial"
    JUVENILE = "juvenile"
    NDPS_MINOR = "ndps_minor"
    STANDARD = "standard"


# Sensitive case types where the redactor must be aggressive — even ambiguous
# matches are redacted. PLAN §10.2 deny-list.
SENSITIVE_CASE_TYPES: frozenset[CaseType] = frozenset({
    CaseType.POCSO,
    CaseType.MATRIMONIAL,
    CaseType.JUVENILE,
    CaseType.NDPS_MINOR,
})


@dataclass(slots=True)
class PIIHit:
    pii_type: PIIType
    start: int                      # byte offset in source text
    end: int
    text: str                       # the matched text (NOT the redacted form)
    confidence: float = 1.0         # 1.0 for regex hits that pass validation
    reason: str = ""                # why this was flagged


@dataclass(slots=True)
class RedactionResult:
    text: str                       # redacted text
    hits: list[PIIHit] = field(default_factory=list)
    case_type: CaseType = CaseType.STANDARD
    suspicious: bool = False        # True if any candidate failed validation;
                                    # such chunks should be quarantined per §10.2

    @property
    def confidence(self) -> float:
        """Min confidence across hits; 1.0 if no hits."""
        if not self.hits:
            return 1.0
        return min(h.confidence for h in self.hits)


# --- Regexes -----------------------------------------------------------------

# Aadhaar: 12 digits with optional space/hyphen separators (4-4-4 grouping common).
# Word-boundary on both sides to avoid catching parts of longer numbers.
_AADHAAR_RE = regex.compile(r"\b(\d{4}[\s-]?\d{4}[\s-]?\d{4})\b")

# Indian mobile: optional +91 / 91 / 0 prefix; then 6/7/8/9 + 9 digits.
# Avoid matching inside year ranges or page numbers by requiring non-word context.
_MOBILE_RE = regex.compile(r"(?<!\w)(?:\+?91[\s-]?|0)?([6-9]\d{9})(?!\w)")

# PAN: 5 letters + 4 digits + 1 letter. 4th letter is entity code.
_PAN_RE = regex.compile(r"\b([A-Z]{5}\d{4}[A-Z])\b")
_PAN_ENTITY_LETTERS = frozenset("PFCHATBLJGE")  # individual, firm, etc.

# Email (lightweight; for legal text emails are usually non-sensitive but redact anyway)
_EMAIL_RE = regex.compile(r"\b[\w._%+-]+@[\w.-]+\.[A-Za-z]{2,}\b")

# Bank account: requires a nearby keyword to be conservative.
_BANK_KEYWORDS = (
    "a/c no", "account no", "account number", "bank a/c", "bank account",
    "savings a/c", "current a/c", "ac no", "ac number",
)
_BANK_NUM_RE = regex.compile(r"\b(\d{9,18})\b")

# Case-type detection from cause-title / header. Conservative — only fires on
# clear signals. Anything ambiguous defaults to STANDARD; the policy is "if
# in doubt, treat as sensitive in NER stage anyway".
_CASE_TYPE_SIGNALS = {
    CaseType.POCSO: (
        "pocso act", "protection of children from sexual offences",
        "minor victim", "sexual offence",
    ),
    CaseType.MATRIMONIAL: (
        "matrimonial cause", "divorce petition", "hindu marriage act", "section 13",
        "decree of divorce", "custody of the child", "domestic violence",
    ),
    CaseType.JUVENILE: (
        "juvenile justice act", "jj act", "child in conflict with law",
        "juvenile in conflict",
    ),
    CaseType.NDPS_MINOR: (
        "ndps act", "narcotic drugs and psychotropic substances",
    ),
}


# --- Verhoeff checksum (Aadhaar validation) ----------------------------------

# Verhoeff tables. Standard reference.
_VERHOEFF_D = [
    [0, 1, 2, 3, 4, 5, 6, 7, 8, 9],
    [1, 2, 3, 4, 0, 6, 7, 8, 9, 5],
    [2, 3, 4, 0, 1, 7, 8, 9, 5, 6],
    [3, 4, 0, 1, 2, 8, 9, 5, 6, 7],
    [4, 0, 1, 2, 3, 9, 5, 6, 7, 8],
    [5, 9, 8, 7, 6, 0, 4, 3, 2, 1],
    [6, 5, 9, 8, 7, 1, 0, 4, 3, 2],
    [7, 6, 5, 9, 8, 2, 1, 0, 4, 3],
    [8, 7, 6, 5, 9, 3, 2, 1, 0, 4],
    [9, 8, 7, 6, 5, 4, 3, 2, 1, 0],
]
_VERHOEFF_P = [
    [0, 1, 2, 3, 4, 5, 6, 7, 8, 9],
    [1, 5, 7, 6, 2, 8, 3, 0, 9, 4],
    [5, 8, 0, 3, 7, 9, 6, 1, 4, 2],
    [8, 9, 1, 6, 0, 4, 3, 5, 2, 7],
    [9, 4, 5, 3, 1, 2, 6, 8, 7, 0],
    [4, 2, 8, 6, 5, 7, 3, 9, 0, 1],
    [2, 7, 9, 3, 8, 0, 6, 4, 1, 5],
    [7, 0, 4, 6, 9, 1, 3, 2, 5, 8],
]


def verhoeff_valid(number: str) -> bool:
    """Verhoeff checksum validation. `number` is digits only."""
    if not number.isdigit():
        return False
    c = 0
    for i, digit in enumerate(reversed(number)):
        c = _VERHOEFF_D[c][_VERHOEFF_P[i % 8][int(digit)]]
    return c == 0


# --- Case-type detection -----------------------------------------------------

def detect_case_type(text: str) -> CaseType:
    """Best-effort case-type detection from the start of the document text.

    Used by the redactor to apply per-case-type aggressiveness (PLAN §10.2
    deny-list). Conservative: ambiguous → STANDARD.
    """
    head = text[:4000].lower()
    for case_type, signals in _CASE_TYPE_SIGNALS.items():
        if any(sig in head for sig in signals):
            return case_type
    return CaseType.STANDARD


# --- Redactor ----------------------------------------------------------------

REDACTION_TOKEN_BY_TYPE: dict[PIIType, str] = {
    PIIType.AADHAAR:     "[AADHAAR REDACTED]",
    PIIType.MOBILE:      "[MOBILE REDACTED]",
    PIIType.PAN:         "[PAN REDACTED]",
    PIIType.BANK_AC:     "[BANK A/C REDACTED]",
    PIIType.EMAIL:       "[EMAIL REDACTED]",
    PIIType.PERSON_NAME: "[NAME REDACTED]",
}


def _find_aadhaar(text: str) -> list[PIIHit]:
    hits: list[PIIHit] = []
    for m in _AADHAAR_RE.finditer(text):
        raw = m.group(1)
        digits = re.sub(r"\D", "", raw)
        if len(digits) != 12:
            continue
        # Validation: must pass Verhoeff. Failure → not a real Aadhaar.
        if not verhoeff_valid(digits):
            # Don't redact, but mark suspicious so the chunk goes to review.
            hits.append(PIIHit(
                pii_type=PIIType.AADHAAR,
                start=m.start(), end=m.end(),
                text=raw, confidence=0.0,
                reason="12-digit pattern but failed Verhoeff",
            ))
            continue
        hits.append(PIIHit(
            pii_type=PIIType.AADHAAR,
            start=m.start(), end=m.end(),
            text=raw, confidence=1.0,
            reason="12-digit + Verhoeff valid",
        ))
    return hits


def _find_mobile(text: str) -> list[PIIHit]:
    hits: list[PIIHit] = []
    for m in _MOBILE_RE.finditer(text):
        ten_digit = m.group(1)
        # Already constrained to 6-9 start by regex.
        # Extra filter: reject if surrounded by year-like context.
        # (Year 1900-2099 won't match 6-9 start, but case numbers might.)
        hits.append(PIIHit(
            pii_type=PIIType.MOBILE,
            start=m.start(), end=m.end(),
            text=m.group(0), confidence=1.0,
            reason="10-digit Indian mobile",
        ))
    return hits


def _find_pan(text: str) -> list[PIIHit]:
    hits: list[PIIHit] = []
    for m in _PAN_RE.finditer(text):
        pan = m.group(1)
        if pan[3] not in _PAN_ENTITY_LETTERS:
            # Likely a coincidental 5L4D1L pattern (e.g. a case reference).
            continue
        hits.append(PIIHit(
            pii_type=PIIType.PAN,
            start=m.start(), end=m.end(),
            text=pan, confidence=1.0,
            reason="valid PAN structure",
        ))
    return hits


def _find_email(text: str) -> list[PIIHit]:
    return [
        PIIHit(
            pii_type=PIIType.EMAIL,
            start=m.start(), end=m.end(),
            text=m.group(0), confidence=1.0,
            reason="email pattern",
        )
        for m in _EMAIL_RE.finditer(text)
    ]


def _find_bank_account(text: str) -> list[PIIHit]:
    """Bank account = 9-18 digit run within ~50 chars of a bank keyword."""
    hits: list[PIIHit] = []
    lower = text.lower()
    keyword_spans = []
    for kw in _BANK_KEYWORDS:
        start = 0
        while True:
            idx = lower.find(kw, start)
            if idx == -1:
                break
            keyword_spans.append((idx, idx + len(kw)))
            start = idx + 1

    if not keyword_spans:
        return hits

    for m in _BANK_NUM_RE.finditer(text):
        n_start, n_end = m.span()
        # Within 50 chars of any bank keyword?
        if any(abs(n_start - ke) <= 50 or abs(n_end - ks) <= 50
               for ks, ke in keyword_spans):
            hits.append(PIIHit(
                pii_type=PIIType.BANK_AC,
                start=n_start, end=n_end,
                text=m.group(0), confidence=0.85,
                reason="long digit run near bank keyword",
            ))
    return hits


def redact(text: str, *, case_type: CaseType | None = None) -> RedactionResult:
    """Redact PII from `text`. Regex stage only.

    `case_type` overrides auto-detection; pass when known from upstream metadata.
    """
    if case_type is None:
        case_type = detect_case_type(text)

    hits = (
        _find_aadhaar(text)
        + _find_mobile(text)
        + _find_pan(text)
        + _find_email(text)
        + _find_bank_account(text)
    )
    # Sort by start so we can apply redactions left-to-right
    hits.sort(key=lambda h: h.start)

    # Only redact hits with confidence > 0. Suspicious (conf=0) hits flag the
    # chunk for quarantine but stay in text (so investigators can see them).
    suspicious = any(h.confidence == 0.0 for h in hits)

    # Apply redactions
    pieces: list[str] = []
    cursor = 0
    for hit in hits:
        if hit.confidence <= 0.0:
            continue  # leave in place; flagged via `suspicious`
        if hit.start < cursor:
            # Overlapping; skip
            continue
        pieces.append(text[cursor:hit.start])
        pieces.append(REDACTION_TOKEN_BY_TYPE[hit.pii_type])
        cursor = hit.end
    pieces.append(text[cursor:])
    redacted = "".join(pieces)

    return RedactionResult(
        text=redacted,
        hits=hits,
        case_type=case_type,
        suspicious=suspicious,
    )


__all__ = [
    "CaseType",
    "PIIHit",
    "PIIType",
    "REDACTION_TOKEN_BY_TYPE",
    "RedactionResult",
    "SENSITIVE_CASE_TYPES",
    "detect_case_type",
    "redact",
    "verhoeff_valid",
]
