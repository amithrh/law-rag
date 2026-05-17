"""Bare-act chunker (PLAN §3.2) — production-grade rewrite.

Design goals (citation correctness is paramount — a wrong section number
on a chunk anchor poisons every answer that cites it):

1. **TOC detection.** IndiaCode PDFs typically have "ARRANGEMENT OF SECTIONS"
   front-matter listing every section title before the act body. We detect
   the body-start position and start chunking from there.

2. **Section body anchor.** Real section bodies start with the pattern
       <n>. <Title>.[—–](<sub-section markers>)
   (e.g. `1. Short title, commencement and application.––(1) This Act…`).
   The em/en-dash + `(1)` pattern is highly specific to real bodies — TOC
   entries don't have it.

3. **Repeated headings.** Some acts (e.g. Hindu Marriage Act) restate section
   headings in the SCHEDULE. We disambiguate duplicate `sec-N` anchors by
   appending a stable counter, so the chunk anchor remains URL-safe and
   collisions don't drop content silently.

4. **as_at extraction.** Pulls from "[As on <date>]", "Last Updated: <date>",
   or the most recent amending-acts entry. Falls back to ingest date with a
   visible flag.

Tested in packages/chunking/tests/test_act.py with synthetic fixtures and
spot-checks on the real IndiaCode PDFs in data/processed/acts.jsonl.
"""
from __future__ import annotations

import re
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import date

import pysbd

from .types import Chunk, ChunkStrategy, estimate_tokens

# --- Patterns ---------------------------------------------------------------

# Candidate section heading: "NN. Title." at line start. Permissive on what
# follows (could be EOL, em-dash, inline content, etc.). We do a second-stage
# check to filter candidates down to real sections (see `_find_section_heads`).
#
# Captures: group(1) = section number ("1", "12A", "234B"); group(2) = title.
_SECTION_HEAD_CANDIDATE_RE = re.compile(
    r"^[ \t]*(\d{1,4}[A-Z]{0,2})\.[ \t]+([A-Z][^\n.]{0,300}?)\.",
    re.MULTILINE,
)

# Real section body marker: anywhere near the heading, we expect a `(1)`
# sub-section marker within the next ~500 chars. Used both to:
#   - Confirm a candidate heading is a real section (vs TOC / Schedule / footnote)
#   - Detect the act body start (the first real section anchor)
_SUBSECTION_MARKER_RE = re.compile(r"\(\s*1\s*\)\s+[A-Z\"“]", re.MULTILINE)


def _is_real_section_head(text: str, head_match: re.Match[str], lookahead: int = 600) -> bool:
    """Confirm a candidate heading by looking for a `(1)` sub-section marker
    within `lookahead` chars after the heading's title-terminal period.

    This filters out TOC entries (no body follows) and Schedule entries
    (one-line content like "Father's brother's daughter.").

    NOTE: Some real sections have no sub-sections (e.g. "4. Punishments.—
    The punishments to which offenders are liable…"). We give those a
    fallback: if no `(1)` is found, but a substantial body paragraph (>200
    chars with no other section heading) follows, accept the heading.
    """
    end = head_match.end()
    window = text[end:end + lookahead]
    if _SUBSECTION_MARKER_RE.search(window):
        return True
    # Fallback: substantial body without another section heading in the way
    next_head = _SECTION_HEAD_CANDIDATE_RE.search(window)
    body_end = next_head.start() if next_head else len(window)
    body_text = window[:body_end].strip()
    return len(body_text) >= 200


def _find_section_heads(text: str) -> list[re.Match[str]]:
    """Return real section heading matches in `text`. Filters candidates
    through the sub-section marker check and the footnote-title blacklist.
    """
    out: list[re.Match[str]] = []
    for m in _SECTION_HEAD_CANDIDATE_RE.finditer(text):
        if _is_footnote_title(m.group(2)):
            continue
        if not _is_real_section_head(text, m):
            continue
        out.append(m)
    return out


# Real section body marker: heading immediately followed by em-dash + (1).
# Used to detect where the act body begins (vs TOC front-matter).
_REAL_BODY_START_RE = re.compile(
    r"^[ \t]*(\d{1,4}[A-Z]{0,2})\.[ \t]+[A-Z][^\n]{0,400}?\.[—–\-]+[ \t]*\(\s*1\s*\)",
    re.MULTILINE,
)

# Fallback: first numbered sub-section marker anywhere
_SUBSECTION_RE = re.compile(r"^[ \t]*\(\s*1\s*\)[ \t]+\S", re.MULTILINE)

# As-on / Last-Updated dates in the act header
_AS_ON_RE = re.compile(
    r"\[As on (?:the\s+)?(\d{1,2}[a-z]{0,2}\s+\w+,?\s+\d{4})\]",
    re.IGNORECASE,
)
_LAST_UPDATED_RE = re.compile(r"Last Updated:\s*(\d{1,2})[-/](\d{1,2})[-/](\d{4})")

# Common amending-act citation, used as final fallback for as_at
_AMENDING_ACT_RE = re.compile(r"\((\d+)\s+of\s+(\d{4})\)", re.IGNORECASE)

# Sizing thresholds (per §3.2)
SECTION_MAX_TOKENS = 800
SECTION_TARGET_SUB_TOKENS = 400
HEADER_MIN_TOKENS = 30        # don't emit a header chunk for trivial preambles

# Footnote / amendment-annotation markers. When the section "title" contains
# any of these, it's almost certainly a marginal note about amendments
# ("Subs. by Act 12 of 1984, s. 5, for the words …"), not a real section
# heading. These get filtered out before chunk emission.
_FOOTNOTE_TITLE_MARKERS = (
    "Subs. by",     # Substituted by
    "Ins. by",      # Inserted by
    "Omitted by",
    "Omitted",
    "Renumbered",
    "Repealed by",
    "ibid.,",
    "w.e.f.",
    " ibid.",
)


def _is_footnote_title(title: str) -> bool:
    """Return True if a matched section "title" looks like an amendment annotation."""
    return any(m in title for m in _FOOTNOTE_TITLE_MARKERS)


# --- as_at -------------------------------------------------------------------

_MONTHS = {m: i + 1 for i, m in enumerate(
    "january february march april may june july august september october november december".split()
)}
_MONTH_ABBR = {k[:3]: v for k, v in _MONTHS.items()}


def _parse_human_date(s: str) -> date:
    """'15th April, 2026' or '6 October 2025' → date."""
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


def extract_as_at(text: str) -> date | None:
    """Pull the act's `as_at` from header text. Returns None if not found.

    Priority:
      1. [As on <date>]  — IndiaCode's stamp on consolidated PDFs
      2. Last Updated: dd-mm-yyyy
      3. Most recent year in an amending-act list (rough — Jan 1 of that year)
    """
    head = text[:5000]
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

    # Fallback: most recent amending-act year in the front matter
    years = [int(m.group(2)) for m in _AMENDING_ACT_RE.finditer(head)]
    years = [y for y in years if 1900 <= y <= 2100]
    if years:
        return date(max(years), 1, 1)
    return None


# --- Body-start detection ---------------------------------------------------

@dataclass(slots=True)
class BodyStart:
    """Where the real act body begins, and how we figured it out."""
    offset: int
    strategy: str   # 'em_dash_subsection' | 'first_subsection_marker' | 'first_heading' | 'doc_start'


def find_body_start(text: str) -> BodyStart:
    """Locate where the act's real section bodies begin.

    Strategy priority:
      1. First `<n>. <Title>.[—–]\\s*(1)` pattern — em-dash + sub-section.
         Highly specific to real section bodies; TOC never has this.
      2. First `(1)` sub-section marker (without the section heading right
         before it). Less specific but works for acts where the heading
         and body are split across page breaks.
      3. First section heading match (if neither 1 nor 2 fires, the act
         either has no sub-section structure or the heuristics missed —
         treat the whole doc as body).
    """
    m = _REAL_BODY_START_RE.search(text)
    if m:
        return BodyStart(offset=m.start(), strategy="em_dash_subsection")

    m = _SUBSECTION_RE.search(text)
    if m:
        # Back up to the most recent section heading before this sub-section
        head_iter = _find_section_heads(text[:m.start()])
        if head_iter:
            return BodyStart(offset=head_iter[-1].start(), strategy="first_subsection_marker")
        return BodyStart(offset=m.start(), strategy="first_subsection_marker")

    headings = _find_section_heads(text)
    if headings:
        return BodyStart(offset=headings[0].start(), strategy="first_heading")

    return BodyStart(offset=0, strategy="doc_start")


# --- Chunker ----------------------------------------------------------------

def chunk_act(
    slug: str,
    text: str,
    *,
    as_at: date | None = None,
) -> Iterator[Chunk]:
    """Yield Chunks for an act.

    Anchors are stable across re-chunking as long as section numbers don't move:
        <slug>#header[@<as_at>]                   — front-matter
        <slug>/sec-<N>[@<as_at>]                  — full section
        <slug>/sec-<N>-<a|b|c>[@<as_at>]          — sub-split of a long section
        <slug>/sec-<N>__<dup-idx>[@<as_at>]       — duplicate section (e.g. in schedule)
    """
    if as_at is None:
        as_at = extract_as_at(text)
    anchor_suffix = f"@{as_at.isoformat()}" if as_at else ""

    body_start = find_body_start(text)

    # Emit header chunk (TOC + front matter)
    header_text = text[: body_start.offset].strip()
    if header_text and estimate_tokens(header_text) >= HEADER_MIN_TOKENS:
        yield Chunk(
            text=header_text[:8000],  # cap; header is reference material, not retrieval target
            anchor=f"{slug}#header{anchor_suffix}",
            chunk_strategy=ChunkStrategy.SECTION,
            token_count=estimate_tokens(header_text),
            as_at=as_at,
            metadata={"is_header": True, "body_start_strategy": body_start.strategy,
                      "body_start_offset": body_start.offset},
        )

    body = text[body_start.offset:]
    if not body.strip():
        return

    # Find section headings IN THE BODY ONLY (not TOC).
    matches = _find_section_heads(body)
    if not matches:
        # Fall back: emit the whole body as a single section-equivalent chunk.
        yield Chunk(
            text=body.strip()[:6000],
            anchor=f"{slug}/full{anchor_suffix}",
            chunk_strategy=ChunkStrategy.SECTION,
            token_count=estimate_tokens(body),
            as_at=as_at,
            metadata={"reason": "no_section_headings_found"},
        )
        return

    # Disambiguate duplicate section numbers (e.g. SCHEDULE re-statements)
    seen_sec_no: dict[str, int] = {}

    # Pre-filter: drop footnote / amendment-annotation "headings"
    matches = [m for m in matches if not _is_footnote_title(m.group(2))]

    for i, m in enumerate(matches):
        sec_no = m.group(1).strip()
        sec_title = m.group(2).strip()
        body_text_start = m.start()
        body_text_end = matches[i + 1].start() if i + 1 < len(matches) else len(body)
        section_body = body[body_text_start:body_text_end].strip()
        if not section_body:
            continue

        # Disambiguate duplicates
        dup_idx = seen_sec_no.get(sec_no, 0)
        seen_sec_no[sec_no] = dup_idx + 1
        dup_suffix = "" if dup_idx == 0 else f"__{dup_idx + 1}"

        tok = estimate_tokens(section_body)
        if tok <= SECTION_MAX_TOKENS:
            yield Chunk(
                text=section_body,
                anchor=f"{slug}/sec-{sec_no}{dup_suffix}{anchor_suffix}",
                chunk_strategy=ChunkStrategy.SECTION,
                token_count=tok,
                as_at=as_at,
                metadata={"section_no": sec_no, "section_title": sec_title,
                          "duplicate_index": dup_idx},
            )
        else:
            yield from _split_long_section(
                slug, sec_no, sec_title, section_body,
                as_at=as_at, anchor_suffix=anchor_suffix, dup_suffix=dup_suffix,
            )


def _split_long_section(
    slug: str,
    sec_no: str,
    sec_title: str,
    body: str,
    *,
    as_at: date | None,
    anchor_suffix: str,
    dup_suffix: str,
) -> Iterator[Chunk]:
    """Sub-split an oversized section. Section header travels with each sub-chunk."""
    seg = pysbd.Segmenter(language="en", clean=False)
    sentences = seg.segment(body)
    # First sentence is typically the section title — keep in every chunk
    header = sentences[0] if sentences else f"{sec_no}. {sec_title}."
    rest = sentences[1:]
    header_tokens = estimate_tokens(header)

    sub_idx = 0
    buf: list[str] = []
    buf_tokens = header_tokens

    def flush():
        nonlocal sub_idx
        if not buf:
            return
        chunk_text = (header + " " + " ".join(buf).strip()).strip()
        yield Chunk(
            text=chunk_text,
            anchor=f"{slug}/sec-{sec_no}{dup_suffix}-{chr(ord('a') + sub_idx)}{anchor_suffix}",
            chunk_strategy=ChunkStrategy.SUB_SECTION,
            token_count=buf_tokens,
            as_at=as_at,
            metadata={"section_no": sec_no, "section_title": sec_title,
                      "sub_index": sub_idx},
        )
        sub_idx += 1

    for sent in rest:
        s_tok = estimate_tokens(sent)
        if buf and buf_tokens + s_tok > SECTION_TARGET_SUB_TOKENS:
            yield from flush()
            buf = [sent]
            buf_tokens = header_tokens + s_tok
        else:
            buf.append(sent)
            buf_tokens += s_tok
    if buf:
        yield from flush()


__all__ = ["BodyStart", "chunk_act", "extract_as_at", "find_body_start"]
