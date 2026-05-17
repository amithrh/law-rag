"""Bare-act chunker (PLAN §3.2).

Splits act text into one chunk per section. The section header travels with
sub-section chunks if a section is too long. Provisos/explanations stay
attached to the parent sub-section.

Anchor format: `<slug>/sec-<n>[@<as_at>]`.

Notes on the IndiaCode-served PDFs:
- They typically have a "Last Updated: <date>" or "[As on <date>]" header,
  which we extract as `as_at`.
- Section heads look like `^\\s*(\\d+[A-Z]?)\\.\\s+([A-Z][\\w\\s,()&]+?)\\.\\s`
  e.g. "1. Short title, extent, commencement and application." or "2A. Definitions.".
- Sub-sections: `(1)`, `(2)`, etc. We keep them inside the parent section
  unless the section is huge.
"""
from __future__ import annotations

import re
from collections.abc import Iterator
from datetime import date

import pysbd

from .types import Chunk, ChunkStrategy, estimate_tokens

# Section heading: number/alpha + period + space + uppercase title + period
# Handles "1.", "2A.", "234.", "356A.".
_SECTION_HEAD_RE = re.compile(
    r"^[ \t]*(\d{1,4}[A-Z]{0,2})\.[ \t]+([A-Z][^\n]{0,400}?)\.[ \t]*$",
    re.MULTILINE,
)

# As-on / Last-Updated dates in the act header
_AS_ON_RE = re.compile(
    r"\[As on (?:the\s+)?(\d{1,2}[a-z]{0,2}\s+\w+,?\s+\d{4})\]",
    re.IGNORECASE,
)
_LAST_UPDATED_RE = re.compile(r"Last Updated:\s*(\d{1,2})[-/](\d{1,2})[-/](\d{4})")

SECTION_MAX_TOKENS = 800
SECTION_TARGET_SUB_TOKENS = 400


def extract_as_at(text: str) -> date | None:
    """Pull the act's `as_at` date from header text. Returns None if not found."""
    head = text[:3000]
    m = _AS_ON_RE.search(head)
    if m:
        try:
            return _parse_human_date(m.group(1))
        except ValueError:
            pass
    m = _LAST_UPDATED_RE.search(head)
    if m:
        d, mo, y = int(m.group(1)), int(m.group(2)), int(m.group(3))
        try:
            return date(y, mo, d)
        except ValueError:
            try:
                return date(y, d, mo)
            except ValueError:
                return None
    return None


_MONTHS = {m: i + 1 for i, m in enumerate(
    "january february march april may june july august september october november december".split()
)}
_MONTH_ABBR = {k[:3]: v for k, v in _MONTHS.items()}


def _parse_human_date(s: str) -> date:
    """'15th April, 2026' or '6 October 2025' → date(2026, 4, 15)."""
    s = s.lower().strip().replace(",", " ")
    parts = re.findall(r"[a-z]+|\d+", s)
    day = month = year = None
    for p in parts:
        if p.isdigit():
            n = int(p)
            if n > 1900:
                year = n
            elif day is None:
                day = n
        elif p in _MONTHS:
            month = _MONTHS[p]
        elif p in _MONTH_ABBR:
            month = _MONTH_ABBR[p]
    if day and month and year:
        return date(year, month, day)
    raise ValueError(f"could not parse date: {s!r}")


def chunk_act(
    slug: str,
    text: str,
    as_at: date | None = None,
) -> Iterator[Chunk]:
    """Yield Chunks for an act. If `as_at` not provided, extract from text."""
    if as_at is None:
        as_at = extract_as_at(text)
    anchor_suffix = f"@{as_at.isoformat()}" if as_at else ""

    # Skip the front-matter (LIST OF AMENDING ACTS, table of contents) by
    # finding the first section heading and starting from there. Front-matter
    # is emitted as a single 'header' chunk.
    all_matches = list(_SECTION_HEAD_RE.finditer(text))

    # IndiaCode PDFs have a "TABLE OF CONTENTS" / "ARRANGEMENT OF SECTIONS"
    # block at the front where every section title is listed without body.
    # Detect this by walking forward and dropping matches whose body text
    # (between this match and the next) is too short to be a real section body.
    # Keep matches only once we see real content between consecutive matches.
    matches: list[re.Match[str]] = []
    for i, m in enumerate(all_matches):
        body_start = m.end()
        body_end = all_matches[i + 1].start() if i + 1 < len(all_matches) else len(text)
        body_text = text[body_start:body_end].strip()
        # "Real" section body is ≥ 40 chars (filters out TOC entries which
        # are just whitespace or page numbers between heading lines). This is
        # imperfect — drops a handful of legitimately short sections like
        # "11. Solitary confinement." that have body on the next page — but
        # those tend to reappear later in the actual section list anyway.
        if len(body_text) >= 40:
            matches.append(m)
    # If our heuristic filtered out everything (e.g. an act with no real
    # body content extracted, which would be a PDF-extraction failure),
    # fall back to all matches.
    if not matches:
        matches = all_matches

    if not matches:
        # Whole-act fallback — emit as one chunk (shouldn't happen for real acts)
        yield Chunk(
            text=text.strip()[:8000],
            anchor=f"{slug}{anchor_suffix}",
            chunk_strategy=ChunkStrategy.SECTION,
            token_count=estimate_tokens(text),
            as_at=as_at,
        )
        return

    # Header chunk
    header_text = text[: matches[0].start()].strip()
    if header_text and estimate_tokens(header_text) > 50:
        yield Chunk(
            text=header_text,
            anchor=f"{slug}#header{anchor_suffix}",
            chunk_strategy=ChunkStrategy.SECTION,
            token_count=estimate_tokens(header_text),
            as_at=as_at,
            metadata={"is_header": True},
        )

    # Section chunks
    for i, m in enumerate(matches):
        sec_no = m.group(1).strip()
        sec_title = m.group(2).strip()
        body_start = m.start()  # include the heading in the chunk
        body_end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        body = text[body_start:body_end].strip()
        if not body:
            continue

        tok = estimate_tokens(body)
        if tok <= SECTION_MAX_TOKENS:
            yield Chunk(
                text=body,
                anchor=f"{slug}/sec-{sec_no}{anchor_suffix}",
                chunk_strategy=ChunkStrategy.SECTION,
                token_count=tok,
                as_at=as_at,
                metadata={"section_no": sec_no, "section_title": sec_title},
            )
        else:
            yield from _split_long_section(slug, sec_no, sec_title, body, as_at, anchor_suffix)


def _split_long_section(
    slug: str,
    sec_no: str,
    sec_title: str,
    body: str,
    as_at: date | None,
    anchor_suffix: str,
) -> Iterator[Chunk]:
    """Sub-split an oversized section. Section header travels with each sub-chunk."""
    seg = pysbd.Segmenter(language="en", clean=False)
    sentences = seg.segment(body)
    # The first sentence is typically the section title — keep it in every chunk
    header = sentences[0] if sentences else f"{sec_no}. {sec_title}."
    rest = sentences[1:]

    sub_idx = 0
    buf: list[str] = []
    buf_tokens = estimate_tokens(header)
    header_tokens = buf_tokens

    for sent in rest:
        s_tok = estimate_tokens(sent)
        if buf and buf_tokens + s_tok > SECTION_TARGET_SUB_TOKENS:
            chunk_text = header + " " + " ".join(buf).strip()
            yield Chunk(
                text=chunk_text.strip(),
                anchor=f"{slug}/sec-{sec_no}-{chr(ord('a') + sub_idx)}{anchor_suffix}",
                chunk_strategy=ChunkStrategy.SUB_SECTION,
                token_count=buf_tokens,
                as_at=as_at,
                metadata={"section_no": sec_no, "section_title": sec_title, "sub_index": sub_idx},
            )
            buf = [sent]
            buf_tokens = header_tokens + s_tok
            sub_idx += 1
        else:
            buf.append(sent)
            buf_tokens += s_tok
    if buf:
        chunk_text = header + " " + " ".join(buf).strip()
        yield Chunk(
            text=chunk_text.strip(),
            anchor=f"{slug}/sec-{sec_no}-{chr(ord('a') + sub_idx)}{anchor_suffix}",
            chunk_strategy=ChunkStrategy.SUB_SECTION,
            token_count=buf_tokens,
            as_at=as_at,
            metadata={"section_no": sec_no, "section_title": sec_title, "sub_index": sub_idx},
        )


__all__ = ["chunk_act", "extract_as_at"]
