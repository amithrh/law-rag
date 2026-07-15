#!/usr/bin/env python3
"""Backfill official-reference Jharkhand witch-practices chunks.

The exact government bare-Act PDF is not present in the local corpus. These
chunks use an official Jharkhand High Court cause-list reference confirming the
Prevention of Witch (Daain) Practices Act sections 3/4 in live Jharkhand cases.
They are deliberately marked as non-verbatim official summaries, so answer
contracts can tell users to verify the state Act instead of pretending this is
the full statute text.
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


SOURCE_URL = "https://jharkhandhighcourt.nic.in/display_pdf/entire_causelist/VACATION_BENCH_27052025.pdf"


JHARKHAND_WITCH_CHUNKS = [
    {
        "slug": "jharkhand-prevention-witch-daain-practices-2001",
        "title": "Jharkhand Prevention of Witch (Daain) Practices Act 2001",
        "source_url": SOURCE_URL,
        "origin": "jharkhand-high-court",
        "source_type": "official_summary",
        "subject_area": "criminal",
        "anchor": "jharkhand-prevention-witch-daain-practices-2001/sec-3",
        "section_no": "3",
        "section_title": "Identification of Witch (Daain)",
        "text_is_verbatim": False,
        "text": (
            "Jharkhand Prevention of Witch (Daain) Practices Act 2001, Section 3\n\n"
            "Official Jharkhand High Court cause-list records identify live matters under "
            "the Prevention of Witch (Daain) Practices Act and list sections 3/4 of the "
            "PWP Act with Jharkhand criminal cases. Treat this as an official court-source "
            "marker for the Jharkhand witch-branding state-law lane, not as verbatim Act "
            "text. For Ranchi, Chaibasa, Gumla, Khunti, Simdega or other Jharkhand facts, "
            "verify the exact Act text, FIR sections, incident date, and BNS/BNSS companion "
            "offences before giving final offence details."
        ),
    },
    {
        "slug": "jharkhand-prevention-witch-daain-practices-2001",
        "title": "Jharkhand Prevention of Witch (Daain) Practices Act 2001",
        "source_url": SOURCE_URL,
        "origin": "jharkhand-high-court",
        "source_type": "official_summary",
        "subject_area": "criminal",
        "anchor": "jharkhand-prevention-witch-daain-practices-2001/sec-4",
        "section_no": "4",
        "section_title": "State-law offence route to verify for witch-practice accusation",
        "text_is_verbatim": False,
        "text": (
            "Jharkhand Prevention of Witch (Daain) Practices Act 2001, Section 4\n\n"
            "Official Jharkhand High Court cause-list records show Prevention of Witch "
            "(Daain) Practices Act section 3/4 references in Jharkhand cases. Use this "
            "source to keep daain, dayan, witch, ojha, black-magic branding, village "
            "pressure, expulsion, public humiliation, stripping or assault in the "
            "Jharkhand state-law lane. Do not substitute Assam, Chhattisgarh, BNS, BNSS, "
            "or a tangential judgment as the controlling Jharkhand state source."
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
        for spec in JHARKHAND_WITCH_CHUNKS:
            inserted += await _upsert_extra_section_chunk(conn, spec)
        await conn.execute(
            """
            UPDATE chunks c
            SET quarantined = FALSE,
                source_type = 'official_summary'
            FROM documents d
            WHERE c.document_id = d.id
              AND d.doc_id = 'jharkhand-prevention-witch-daain-practices-2001'
              AND c.anchor = ANY($1::text[])
            """,
            [spec["anchor"] for spec in JHARKHAND_WITCH_CHUNKS],
        )
        print(f"jharkhand witch official summaries: inserted/updated {inserted} chunks")
    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(main())
