"""Judgment chunker (PLAN §3.1).

Primary strategy: split on numbered paragraphs (`^\\s*(\\d+)\\.\\s`).
Fallback: semantic-window splitter for older / unnumbered judgments.

Token budget:
- target: 200–800 tokens/chunk (per PLAN §3.1, §5.3 MPS throughput).
- if a numbered paragraph > 1000 tokens, sub-split at sentence boundaries.
"""
from __future__ import annotations

import re
from collections.abc import Iterator

import pysbd

from .types import Chunk, ChunkStrategy, estimate_tokens

# Numbered-paragraph head: digits + period + space, at line start.
# Allow leading whitespace, allow up to 4 digits.
_NUMBERED_PARA_RE = re.compile(r"^\s*(\d{1,4})\.\s+", re.MULTILINE)

# Semantic-window target — fallback only.
SEMANTIC_TARGET_TOKENS = 350
SEMANTIC_MAX_TOKENS = 600

# Numbered-paragraph hard split — if a paragraph exceeds this, sentence-split it.
PARA_MAX_TOKENS = 1000


def chunk_judgment(
    doc_id: str,
    text: str,
) -> Iterator[Chunk]:
    """Yield Chunks for a judgment text.

    Uses numbered-paragraph splitter when available; semantic-window fallback
    otherwise. Each chunk's anchor is `<doc_id>#para-<n>` for numbered,
    `<doc_id>#win-<n>` for semantic windows.
    """
    matches = list(_NUMBERED_PARA_RE.finditer(text))
    if len(matches) >= 5:
        yield from _chunk_numbered(doc_id, text, matches)
    else:
        yield from _chunk_semantic(doc_id, text)


def _chunk_numbered(
    doc_id: str,
    text: str,
    matches: list[re.Match[str]],
) -> Iterator[Chunk]:
    """Numbered-paragraph chunker."""
    # Optional pre-paragraph header (case caption, headnotes) → emit as 'header' chunk
    head_text = text[: matches[0].start()].strip()
    if head_text and estimate_tokens(head_text) > 30:
        yield Chunk(
            text=head_text,
            anchor=f"{doc_id}#header",
            chunk_strategy=ChunkStrategy.NUMBERED_PARAGRAPH,
            token_count=estimate_tokens(head_text),
            paragraph_no=None,
        )

    for i, m in enumerate(matches):
        para_no = int(m.group(1))
        body_start = m.end()
        body_end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        body = text[body_start:body_end].strip()
        if not body:
            continue

        para_tokens = estimate_tokens(body)
        if para_tokens <= PARA_MAX_TOKENS:
            yield Chunk(
                text=body,
                anchor=f"{doc_id}#para-{para_no}",
                chunk_strategy=ChunkStrategy.NUMBERED_PARAGRAPH,
                token_count=para_tokens,
                paragraph_no=para_no,
            )
        else:
            # Hard split — sentence-window within the para
            yield from _sub_split_para(doc_id, para_no, body)


def _sub_split_para(
    doc_id: str,
    para_no: int,
    body: str,
) -> Iterator[Chunk]:
    """Sub-split an oversized numbered paragraph at sentence boundaries."""
    seg = pysbd.Segmenter(language="en", clean=False)
    sentences = seg.segment(body)
    sub_idx = 0
    buf: list[str] = []
    buf_tokens = 0
    for sent in sentences:
        s_tok = estimate_tokens(sent)
        if buf and buf_tokens + s_tok > SEMANTIC_TARGET_TOKENS:
            chunk_text = " ".join(buf).strip()
            yield Chunk(
                text=chunk_text,
                anchor=f"{doc_id}#para-{para_no}-{chr(ord('a') + sub_idx)}",
                chunk_strategy=ChunkStrategy.NUMBERED_PARAGRAPH,
                token_count=buf_tokens,
                paragraph_no=para_no,
            )
            buf = [sent]
            buf_tokens = s_tok
            sub_idx += 1
        else:
            buf.append(sent)
            buf_tokens += s_tok
    if buf:
        chunk_text = " ".join(buf).strip()
        yield Chunk(
            text=chunk_text,
            anchor=f"{doc_id}#para-{para_no}-{chr(ord('a') + sub_idx)}",
            chunk_strategy=ChunkStrategy.NUMBERED_PARAGRAPH,
            token_count=buf_tokens,
            paragraph_no=para_no,
        )


def _chunk_semantic(doc_id: str, text: str) -> Iterator[Chunk]:
    """Semantic-window fallback for unnumbered judgments."""
    seg = pysbd.Segmenter(language="en", clean=False)
    sentences = seg.segment(text)
    win_idx = 0
    buf: list[str] = []
    buf_tokens = 0
    for sent in sentences:
        s_tok = estimate_tokens(sent)
        if buf and buf_tokens + s_tok > SEMANTIC_TARGET_TOKENS:
            chunk_text = " ".join(buf).strip()
            yield Chunk(
                text=chunk_text,
                anchor=f"{doc_id}#win-{win_idx}",
                chunk_strategy=ChunkStrategy.SEMANTIC_WINDOW,
                token_count=buf_tokens,
            )
            buf = [sent]
            buf_tokens = s_tok
            win_idx += 1
        else:
            buf.append(sent)
            buf_tokens += s_tok
    if buf:
        chunk_text = " ".join(buf).strip()
        yield Chunk(
            text=chunk_text,
            anchor=f"{doc_id}#win-{win_idx}",
            chunk_strategy=ChunkStrategy.SEMANTIC_WINDOW,
            token_count=buf_tokens,
        )


__all__ = ["chunk_judgment"]
