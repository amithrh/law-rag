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


# Convenience: derive the slice subject area from a judgment's text / metadata.
# Used by adapters that don't carry subject-area tagging upstream (most do not).
SUBJECT_AREA_KEYWORDS: dict[str, tuple[str, ...]] = {
    "consumer": (
        "consumer protection", "consumer forum", "deficiency in service",
        "defective goods", "unfair trade practice", "Consumer Disputes Redressal",
    ),
    "family": (
        "Hindu Marriage Act", "Special Marriage Act", "divorce", "maintenance",
        "matrimonial", "custody of the child", "Domestic Violence Act",
    ),
    "criminal": (
        "Bharatiya Nyaya Sanhita", "BNS", "Indian Penal Code", "IPC",
        "CrPC", "Code of Criminal Procedure", "BNSS", "bail", "FIR",
        "Section 302", "Section 376", "anticipatory bail",
    ),
    "wages": (
        "Code on Wages", "Industrial Disputes Act", "Payment of Wages",
        "Payment of Gratuity", "Provident Fund", "minimum wages",
    ),
    "rti": (
        "Right to Information", "Central Information Commission",
        "State Information Commission", "RTI Act",
    ),
    "motor": (
        "Motor Vehicles Act", "Motor Accident Claims Tribunal", "MACT",
        "third party insurance", "compensation under section 166",
    ),
}


def infer_subject_area(text: str) -> str | None:
    """Best-effort subject-area tag from raw text. None if no clear match.

    Used by SC/HC adapters to populate `documents.subject_area` for the
    coverage chip (PLAN §4.4) and per-domain eval breakdown (PLAN §12).
    """
    text_lower = text.lower()[:10000]  # only inspect the start; cheaper, usually enough
    scores: dict[str, int] = {}
    for area, keywords in SUBJECT_AREA_KEYWORDS.items():
        scores[area] = sum(1 for kw in keywords if kw.lower() in text_lower)
    best_area, best_score = max(scores.items(), key=lambda kv: kv[1])
    return best_area if best_score >= 1 else None


__all__ = [
    "Adapter",
    "AdapterQuery",
    "AdapterStats",
    "RawDoc",
    "SUBJECT_AREA_KEYWORDS",
    "SourceType",
    "infer_subject_area",
]
