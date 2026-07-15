#!/usr/bin/env python3
"""Backfill an official Income-tax Act section 143(2) source chunk.

The local Income-tax extraction has adjacent assessment sections but not a
clean section 143 chunk, so common 143(2) notice questions drift to section 148
or other unrelated anchors. This adds a narrow official-section chunk from the
Income Tax Department page; it updates only the local index data.
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

import asyncpg

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from scripts.add_stage34_official_source_chunks import (  # noqa: E402
    _load_env,
    _upsert_extra_section_chunk,
)


SOURCE_URL = "https://www.incometaxindia.gov.in/w/section-143-64"


INCOME_TAX_143_CHUNK = {
    "slug": "income-tax-1961",
    "title": "Income-tax Act 1961",
    "source_url": SOURCE_URL,
    "origin": "income-tax-department",
    "source_type": "bare_act",
    "subject_area": "tax",
    "anchor": "income-tax-1961/sec-143",
    "section_no": "143",
    "section_title": "Assessment",
    "text_is_verbatim": False,
    "text": (
        "Income-tax Act 1961, Section 143. Assessment\n\n"
        "Section 143(2) covers a notice after a return is furnished under section "
        "139 or in response to section 142(1). The notice requires the assessee, "
        "on the date specified in the notice, to attend the office or produce "
        "evidence relied on in support of the return.\n\n"
        "The current official Income Tax Department section page carries the "
        "three-month service limit for a section 143(2) notice, counted from the "
        "end of the financial year in which the return is furnished."
    ),
}


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
        inserted = await _upsert_extra_section_chunk(conn, INCOME_TAX_143_CHUNK)
        print(f"income tax 143(2) source: inserted/updated {inserted} section chunk")
    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(main())
