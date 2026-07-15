#!/usr/bin/env python3
"""Backfill the missing Hindu Succession Act Section 6 source chunk.

The base IndiaCode PDF for `hindu-succession-1956` is already part of the
local raw corpus, but the parser skipped the main Section 6 body while keeping
later state-amendment sections such as 6B and 6C. This script extracts the
body Section 6 text from that official PDF and upserts a single indexed chunk.
It updates the local database only; it does not commit generated corpus data.
"""
from __future__ import annotations

import asyncio
import re
import sys
from pathlib import Path

import asyncpg
import pymupdf

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from scripts.add_stage34_official_source_chunks import (  # noqa: E402
    _load_env,
    _upsert_extra_section_chunk,
)


HSA_PDF = ROOT / "data" / "raw" / "acts" / "hindu-succession-1956__AAA1956suc___30.pdf"
HSA_SOURCE_URL = "https://www.indiacode.nic.in/bitstream/123456789/1713/1/AAA1956suc___30.pdf"


def _extract_section_6_text() -> str:
    if not HSA_PDF.exists():
        raise FileNotFoundError(
            f"Missing official HSA PDF at {HSA_PDF}. Run the P0 Act ingest first."
        )

    doc = pymupdf.open(HSA_PDF)
    try:
        full_text = "\n".join(page.get_text("text") for page in doc)
    finally:
        doc.close()

    matches = list(re.finditer(r"6\.\s*Devolution of interest in coparcenary property", full_text))
    if len(matches) < 2:
        raise RuntimeError("Could not locate the body text for Hindu Succession Act Section 6")

    start = matches[1].start()
    state_amendments = full_text.find("STATE AMENDMENTS", start)
    if state_amendments == -1:
        raise RuntimeError("Could not locate the end of Hindu Succession Act Section 6")

    section = full_text[start:state_amendments].strip()
    section = re.sub(r"\n\s*\d+\.\s+Omitted by Act.*?\n", "\n", section)
    section = re.sub(r"\n\s*\d+\.\s+Subs\. by.*?\n", "\n", section)
    section = re.sub(r"\n\s*\d+\s*\n", "\n", section)
    section = re.sub(r"[ \t]+", " ", section)
    section = re.sub(r"\n{3,}", "\n\n", section)
    return "Hindu Succession Act 1956 (with 2005 amendment), Section 6\n\n" + section


async def main() -> None:
    env = _load_env()
    conn = await asyncpg.connect(
        host="localhost",
        port=int(env["POSTGRES_HOST_PORT"]),
        database=env["POSTGRES_DB"],
        user=env["POSTGRES_USER"],
        password=env["POSTGRES_PASSWORD"],
    )
    try:
        inserted = await _upsert_extra_section_chunk(conn, {
            "slug": "hindu-succession-1956",
            "title": "Hindu Succession Act 1956 (with 2005 amendment)",
            "source_url": HSA_SOURCE_URL,
            "subject_area": "family",
            "anchor": "hindu-succession-1956/sec-6",
            "section_no": "6",
            "section_title": "Devolution of interest in coparcenary property",
            "text_is_verbatim": True,
            "text": _extract_section_6_text(),
        })
        print(f"hindu succession sec6 source: inserted/updated {inserted} section chunk")
    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(main())
