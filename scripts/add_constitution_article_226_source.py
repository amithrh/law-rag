#!/usr/bin/env python3
"""Backfill a clean official-source Article 226 Constitution chunk.

The indexed Constitution currently has Article 21/22 chunks but no clean
`constitution-india/sec-226` chunk. Habeas and writ queries therefore retrieve
generic liberty sources or judgments while the route asks for Article 226.

This script adds a narrow Legislative Department-backed summary chunk. It
updates the local index only; it does not commit generated data.
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


SOURCE_URL = "https://legislative.gov.in/constitution-of-india/"


CONSTITUTION_ARTICLE_226_CHUNKS = [
    {
        "slug": "constitution-india",
        "title": "Constitution of India",
        "source_url": SOURCE_URL,
        "origin": "legislative_department",
        "subject_area": "constitutional",
        "anchor": "constitution-india/sec-226",
        "section_no": "226",
        "section_title": "Power of High Courts to issue certain writs",
        "text_is_verbatim": False,
        "text": (
            "Constitution of India, Article 226\n\n"
            "Article 226 is the High Court writ-jurisdiction source. It gives "
            "every High Court power, within its territorial jurisdiction, to "
            "issue directions, orders, or writs to persons, authorities, and "
            "appropriate governments. The writs include habeas corpus, "
            "mandamus, prohibition, quo warranto, and certiorari, for enforcing "
            "Part III fundamental rights and for other purposes. For illegal "
            "detention or habeas corpus questions, verify Article 21 personal "
            "liberty, Article 22 arrest safeguards, and Article 226 High Court "
            "writ jurisdiction together with the BNSS/CrPC production and "
            "arrest-safeguard provisions."
        ),
    },
]


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
        inserted = 0
        for spec in CONSTITUTION_ARTICLE_226_CHUNKS:
            inserted += await _upsert_extra_section_chunk(conn, spec)
        print(f"constitution article 226 sources: inserted/updated {inserted} section chunks")
    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(main())
