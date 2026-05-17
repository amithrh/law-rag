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


def infer_subject_area(text: str) -> str | None:
    """Best-effort subject-area tag from text. Returns the area with the most
    keyword hits. Returns None only when the text genuinely has no legal
    subject signal (vanishingly rare on real judgments — most will match
    'criminal' at minimum because of references to CrPC / bail / etc.).

    The expanded keyword set (slice + 8 "other" categories) ensures we
    don't silently drop a constitutional / tax / civil / service judgment
    just because it doesn't fit the slice. Those judgments still appear in
    retrieval; they just carry an honest subject_area label.
    """
    if not text:
        return None
    text_lower = text.lower()[:10000]
    scores: dict[str, int] = {}
    for area, keywords in SUBJECT_AREA_KEYWORDS.items():
        # Score by distinct keyword hits, not raw match count (which would
        # over-favor categories that repeat the same word).
        scores[area] = sum(1 for kw in keywords if kw.lower() in text_lower)
    best_area, best_score = max(scores.items(), key=lambda kv: kv[1])
    return best_area if best_score >= 1 else None


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
