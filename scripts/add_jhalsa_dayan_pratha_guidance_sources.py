#!/usr/bin/env python3
"""Backfill JHALSA official-guidance chunks for Jharkhand witch-branding law.

The full Gazette/bare-Act text is still not in the local corpus. This script
adds section-level, non-verbatim guidance from the Jharkhand State Legal
Services Authority pamphlet titled "Dayan Pratha Pratishedh Adhiniyam, 2001".
It is an official legal-services source, so it can support user-facing
Jharkhand witch-branding guidance without pretending to be a Gazette copy.
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


SOURCE_URL = "https://jhalsa.org/Jhalsa_Pamphlets_Web/2014/05_Dayan_Pratha.pdf"


JHALSA_DAYAN_CHUNKS = [
    {
        "slug": "jhalsa-dayan-pratha-pratishedh-2001",
        "title": "Jharkhand State Legal Services Authority Dayan Pratha Pratishedh Adhiniyam 2001",
        "source_url": SOURCE_URL,
        "origin": "jhalsa",
        "source_type": "official_guidance",
        "subject_area": "criminal",
        "anchor": "jhalsa-dayan-pratha-pratishedh-2001/sec-3",
        "section_no": "3",
        "section_title": "Dayan/Daain identification offence",
        "text_is_verbatim": False,
        "text": (
            "Jharkhand State Legal Services Authority pamphlet: Dayan Pratha "
            "Pratishedh Adhiniyam, 2001, Section 3.\n\n"
            "The JHALSA pamphlet presents the Jharkhand Dayan Pratha Pratishedh "
            "Adhiniyam, 2001 as applying across Jharkhand. It explains that a person "
            "who identifies another person as dayan/daain or takes action on that "
            "identification may be punished with imprisonment up to three months, "
            "fine up to one thousand rupees, or both. Use this as official legal-aid "
            "guidance for Jharkhand witch/daain-branding facts in Ranchi, Chaibasa, "
            "Gumla, Khunti, Simdega, Singhbhum, or other Jharkhand districts."
        ),
    },
    {
        "slug": "jhalsa-dayan-pratha-pratishedh-2001",
        "title": "Jharkhand State Legal Services Authority Dayan Pratha Pratishedh Adhiniyam 2001",
        "source_url": SOURCE_URL,
        "origin": "jhalsa",
        "source_type": "official_guidance",
        "subject_area": "criminal",
        "anchor": "jhalsa-dayan-pratha-pratishedh-2001/sec-4",
        "section_no": "4",
        "section_title": "Harassment or instigation after branding as dayan/daain",
        "text_is_verbatim": False,
        "text": (
            "Jharkhand State Legal Services Authority pamphlet: Dayan Pratha "
            "Pratishedh Adhiniyam, 2001, Sections 4 to 6.\n\n"
            "The JHALSA pamphlet explains that harassing or mentally/physically "
            "torturing a woman after identifying her as dayan/daain may attract "
            "punishment up to six months and fine up to two thousand rupees. It also "
            "describes punishment for encouraging, helping, or abetting identification "
            "as dayan/daain, and for treatment or ritual acts such as jhad-phook or "
            "totka that cause physical or mental harm after a woman is identified as "
            "dayan/daain. Keep this Jharkhand state-law lane alongside BNS/BNSS FIR, "
            "Magistrate, medical-record, and protection steps where violence, public "
            "humiliation, stripping, expulsion, or mob pressure is alleged."
        ),
    },
    {
        "slug": "jhalsa-dayan-pratha-pratishedh-2001",
        "title": "Jharkhand State Legal Services Authority Dayan Pratha Pratishedh Adhiniyam 2001",
        "source_url": SOURCE_URL,
        "origin": "jhalsa",
        "source_type": "official_guidance",
        "subject_area": "criminal",
        "anchor": "jhalsa-dayan-pratha-pratishedh-2001/sec-7",
        "section_no": "7",
        "section_title": "Cognizable and non-bailable procedure",
        "text_is_verbatim": False,
        "text": (
            "Jharkhand State Legal Services Authority pamphlet: Dayan Pratha "
            "Pratishedh Adhiniyam, 2001, Section 7.\n\n"
            "The JHALSA pamphlet states that offences under the Act are cognizable "
            "and non-bailable. For a Jharkhand user reporting daain/dayan/witch "
            "branding, this supports treating the matter as police-protection and "
            "criminal-procedure work, with immediate complaint/FIR, SP/DLSA, and "
            "Magistrate escalation if police refuse action."
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
        for spec in JHALSA_DAYAN_CHUNKS:
            inserted += await _upsert_extra_section_chunk(conn, spec)
        await conn.execute(
            """
            UPDATE chunks c
            SET quarantined = FALSE,
                source_type = 'official_guidance'
            FROM documents d
            WHERE c.document_id = d.id
              AND d.doc_id = 'jhalsa-dayan-pratha-pratishedh-2001'
              AND c.anchor = ANY($1::text[])
            """,
            [spec["anchor"] for spec in JHALSA_DAYAN_CHUNKS],
        )
        print(f"jhalsa dayan pratha official guidance: inserted/updated {inserted} chunks")
    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(main())
