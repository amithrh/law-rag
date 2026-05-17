"""Chunk types shared by all chunkers (PLAN §3.4)."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from enum import StrEnum


class ChunkStrategy(StrEnum):
    NUMBERED_PARAGRAPH = "numbered_paragraph"  # judgment paragraphs
    SEMANTIC_WINDOW = "semantic_window"        # fallback for unnumbered judgments
    SECTION = "section"                        # bare-act section
    SUB_SECTION = "sub_section"                # bare-act sub-section split
    FULL_CIRCULAR = "full_circular"            # single-chunk circulars


@dataclass(slots=True)
class Chunk:
    """A retrieval-ready chunk. Maps to one row in `chunks` table."""

    text: str
    anchor: str                           # e.g. 'sc/2024/...#para-12' or 'consumer-protection-2019/sec-2'
    chunk_strategy: ChunkStrategy
    token_count: int                      # approximate; the embedder validates
    paragraph_no: int | None = None
    as_at: date | None = None
    metadata: dict = field(default_factory=dict)


def estimate_tokens(text: str) -> int:
    """Rough estimate — ~1 token per 4 chars for English legal text.

    The real tokenizer (bge-m3) gives slightly different numbers; this is
    only used for chunk-size policy decisions, not for embedding cost
    calculations. Off by ~10-20%.
    """
    return len(text) // 4
