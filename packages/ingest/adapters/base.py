"""Adapter base types.

Every per-source adapter exposes the same surface so the ingestion CLI and
downstream chunking can treat all corpora uniformly. The contract is small on
purpose: list + fetch. State (HTTP sessions, rate limiters, dataset handles)
is the adapter's business.
"""
from __future__ import annotations

import hashlib
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from datetime import date, datetime
from enum import StrEnum
from typing import Protocol


class SourceType(StrEnum):
    SC_JUDGMENT = "sc_judgment"
    HC_JUDGMENT = "hc_judgment"
    BARE_ACT = "bare_act"
    CIRCULAR = "circular"


@dataclass(slots=True)
class RawDoc:
    """A single fetched item before normalization.

    `payload` is the bytes as fetched (HTML, PDF, or already-extracted text
    from a HF dataset). The normalizer picks the right path based on
    `content_type`.
    """

    source_type: SourceType
    origin: str                    # 'hf:Rahul1872/...' | 'indiacode' | 'delhi-hc' | ...
    url: str                       # canonical URL
    payload: bytes                 # raw bytes (HTML / PDF / pre-extracted text bytes)
    content_type: str              # 'text/html' | 'application/pdf' | 'text/plain'
    fetched_at: datetime = field(default_factory=lambda: datetime.utcnow())
    metadata: dict = field(default_factory=dict)

    @property
    def canonical_url_hash(self) -> str:
        return hashlib.sha256(self.url.encode("utf-8")).hexdigest()


@dataclass(slots=True)
class AdapterQuery:
    """Open-ended filter passed to `Adapter.list_ids` / `Adapter.iter_docs`.

    Not every adapter honors every field. Documented per-adapter.
    """

    year_from: int | None = None
    year_to: int | None = None
    subject_areas: list[str] | None = None      # 'consumer' | 'family' | ...
    courts: list[str] | None = None             # for HC adapters
    statute_short: str | None = None            # for bare-act adapters
    limit: int | None = None                    # cap for testing / partial runs


class Adapter(Protocol):
    """Per-source adapter contract.

    Implementations live in `packages/ingest/adapters/<source>.py`.
    The CLI dispatches by string name → adapter class.
    """

    name: str
    source_type: SourceType

    async def iter_docs(self, query: AdapterQuery) -> AsyncIterator[RawDoc]:
        """Yield raw docs matching `query`. Should respect rate limits and
        be idempotent — re-running with the same query yields the same docs.
        """
        ...


@dataclass(slots=True)
class AdapterStats:
    """Returned by the CLI; logged + tracked for monitoring."""

    adapter_name: str
    fetched: int = 0
    skipped_existing: int = 0
    errors: int = 0
    bytes_total: int = 0
    started_at: datetime = field(default_factory=lambda: datetime.utcnow())
    finished_at: datetime | None = None

    def mark_done(self) -> None:
        self.finished_at = datetime.utcnow()

    @property
    def duration_s(self) -> float | None:
        if self.finished_at is None:
            return None
        return (self.finished_at - self.started_at).total_seconds()


# Derive the slice subject area from a judgment's text / metadata.
#
# The keyword map is INTENTIONALLY broader than the slice's named domains —
# any SC judgment in our corpus belongs to *some* area of law, and silently
# dropping the ~20% that don't match a slice subject is a product defect
# (those judgments still get retrieved by dense embedding; they just lack
# the coverage-chip label).
#
# Two categories of subjects:
#   - **slice**: directly served by our product UI / golden eval breakdown
#   - **other**: still indexed, tagged for coverage transparency, but not
#     part of the 6-subject slice nav
SUBJECT_AREA_KEYWORDS: dict[str, tuple[str, ...]] = {
    # ===== slice subjects =====
    "consumer": (
        "consumer protection", "consumer forum", "deficiency in service",
        "defective goods", "unfair trade practice", "Consumer Disputes Redressal",
        "District Consumer", "State Consumer Commission", "National Consumer",
    ),
    "family": (
        "Hindu Marriage Act", "Special Marriage Act", "divorce", "maintenance",
        "matrimonial", "custody of the child", "Domestic Violence Act",
        "Hindu Succession", "Muslim Marriages", "judicial separation",
        "section 13(1)", "decree of divorce", "child custody",
    ),
    "criminal": (
        "Bharatiya Nyaya Sanhita", "BNS", "Indian Penal Code", "IPC",
        "CrPC", "Code of Criminal Procedure", "BNSS", "bail", "FIR",
        "anticipatory bail", "Section 302", "Section 376", "Section 498A",
        "POCSO", "NDPS Act", "Prevention of Money Laundering Act", "PMLA",
        "Section 161", "charge-sheet", "discharge",
    ),
    "wages": (
        "Code on Wages", "Industrial Disputes Act", "Payment of Wages",
        "Payment of Gratuity", "Provident Fund", "minimum wages",
        "termination of service", "industrial dispute", "workmen",
    ),
    "rti": (
        "Right to Information", "Central Information Commission",
        "State Information Commission", "RTI Act",
    ),
    "motor": (
        "Motor Vehicles Act", "Motor Accident Claims Tribunal", "MACT",
        "third party insurance", "compensation under section 166",
        "motor vehicle accident",
    ),

    # ===== other subjects (tagged for coverage transparency, not in slice UI) =====
    "constitutional": (
        "Article 14", "Article 19", "Article 21", "Article 32", "Article 226",
        "fundamental rights", "basic structure", "writ petition",
        "violation of fundamental", "Constitution of India",
    ),
    "tax": (
        "Income Tax Act", "GST", "Goods and Services Tax", "ITAT",
        "Income Tax Appellate Tribunal", "service tax", "excise duty",
        "customs", "TDS", "tax deduction at source",
    ),
    "company_securities": (
        "Companies Act", "SEBI", "Securities and Exchange Board",
        "IBC", "Insolvency and Bankruptcy Code", "NCLT", "NCLAT",
        "winding up", "share capital", "scheme of arrangement",
    ),
    "property": (
        "Transfer of Property Act", "Specific Relief Act",
        "sale deed", "specific performance", "easement",
        "agreement to sell", "encroachment", "title suit",
    ),
    "service_employment": (
        "service matter", "departmental enquiry", "promotion",
        "seniority", "retirement", "pension", "dismissal from service",
        "transfer order", "appointment", "CCS Rules",
    ),
    "land_revenue": (
        "land acquisition", "Land Acquisition Act", "encroachment of land",
        "revenue records", "agricultural land", "panchayat",
    ),
    "election": (
        "Representation of the People Act", "election petition", "Election Commission",
        "voter list", "panchayat election",
    ),
    "education": (
        "Right to Education Act", "RTE", "school admission",
        "University Grants Commission", "UGC", "admission to college",
    ),
    "civil_general": (
        "Civil Procedure Code", "CPC", "Order VII", "Order XXI",
        "execution petition", "decree of the trial court",
        "civil suit", "money decree",
    ),
}


# Slice subjects — used by the coverage chip and golden eval breakdown.
SLICE_SUBJECTS: frozenset[str] = frozenset({
    "consumer", "family", "criminal", "wages", "rti", "motor",
})


# Hard title signals — phrases that, when they appear in the case
# title, leave no doubt about the subject. They short-circuit the
# keyword-scoring path. Built from the audit of mis-tagged cases
# (2026-05-19): 87% of SC docs were tagged "criminal" because tax /
# customs / land cases tangentially mentioned "FIR" or "CrPC" in the
# body, and "criminal" has more keywords than other categories so it
# accumulated more hits.
_TITLE_SIGNALS: tuple[tuple[str, tuple[str, ...]], ...] = (
    # Order matters — earlier wins on overlap. Tax is first because
    # "Commissioner of Income Tax" is the single biggest mis-tag class.
    ("tax", (
        "income tax", "sales tax", "service tax", "trade tax",
        "central excise", "excise duty", "customs duty", "customs act",
        "commissioner of customs", "commissioner of central excise",
        "commissioner of income tax", "principal commissioner of income tax",
        "joint commissioner of income tax", "assistant commissioner of income tax",
        "directorate of revenue intelligence", "income tax appellate",
        "central goods and services", "cgst", "sgst", "gst act",
    )),
    ("land_revenue", (
        "land acquisition", "revenue divisional officer",
        "collector ... land", "land acquisition officer",
        "land acquisition act", "agricultural land",
    )),
    ("company_securities", (
        "companies act", "scheme of arrangement", "national company law",
        "nclt", "nclat", "ibc ", "insolvency and bankruptcy",
        "securities and exchange board", "sebi",
    )),
    ("property", (
        "transfer of property", "specific relief act", "specific performance",
        "agreement to sell", "sale deed", "title suit",
    )),
    ("election", (
        "representation of the people act", "election petition",
        "election commission",
    )),
    ("constitutional", (
        # Many writ petitions are tagged constitutional already; this
        # catches the explicit "Article 32 / 226 / 14" mentions in title.
        "article 32", "article 226", "article 14", "article 19",
        "fundamental rights",
    )),
    ("service_employment", (
        "departmental enquiry", "ccs rules", "service rules",
        "compulsory retirement", "pension regulation",
    )),
)


def infer_subject_area(text: str, *, title: str = "") -> str | None:
    """Best-effort subject-area tag from a doc's body text plus (preferred)
    its title. Returns the area with the highest weighted keyword score,
    or None when no clear signal exists.

    Two-stage classification (rewritten 2026-05-19 after the retrieval
    audit revealed 87% of SC docs mis-tagged as "criminal"):

    1. TITLE OVERRIDE — if the title contains a hard signal phrase
       ("Commissioner of Income Tax", "Land Acquisition", "Specific
       Relief Act", etc.), classify by that immediately. Bodies of
       tax / customs / property judgments routinely mention "FIR" or
       "CrPC" tangentially, which let the old classifier mis-tag them
       as criminal. The title is the most reliable single signal.

    2. KEYWORD SCORING — length-weighted. Multi-word phrases like
       "Bharatiya Nyaya Sanhita" (3 words) score more than "FIR"
       (1 word) because longer phrases are less likely to appear by
       coincidence. The old equal-weight scoring favored categories
       with many short keywords (criminal had ~15 short ones).

    A minimum confidence floor of 2 weighted points means weakly-
    signaled docs return None rather than getting force-tagged as the
    least-bad category.
    """
    if not text and not title:
        return None

    title_lower = (title or "").lower()
    text_lower = (text or "").lower()[:10000]
    haystack = f"{title_lower}\n{text_lower}"  # title appears first, so substring matches there get checked first

    # Stage 1 — title override
    if title_lower:
        for area, phrases in _TITLE_SIGNALS:
            for p in phrases:
                if p in title_lower:
                    return area

    # Stage 2 — length-weighted keyword scoring over title + body
    scores: dict[str, float] = {}
    for area, keywords in SUBJECT_AREA_KEYWORDS.items():
        total = 0.0
        for kw in keywords:
            kw_lower = kw.lower()
            if kw_lower in haystack:
                # Weight by word count of the keyword phrase. A 3-word
                # phrase like "Bharatiya Nyaya Sanhita" scores 3; a
                # 1-word like "FIR" scores 1.
                total += float(len(kw_lower.split()))
        scores[area] = total

    best_area, best_score = max(scores.items(), key=lambda kv: kv[1])
    # Min-confidence floor: 2 weighted points = either one strong 2-word
    # phrase or two 1-word matches. Below that, we can't tell.
    return best_area if best_score >= 2.0 else None


def is_slice_subject(area: str | None) -> bool:
    return area in SLICE_SUBJECTS


__all__ = [
    "Adapter",
    "AdapterQuery",
    "AdapterStats",
    "RawDoc",
    "SLICE_SUBJECTS",
    "SUBJECT_AREA_KEYWORDS",
    "SourceType",
    "infer_subject_area",
    "is_slice_subject",
]
