#!/usr/bin/env python3
"""Backfill official Chhattisgarh Tonahi Act source chunks.

The common-user eval has accused-side and victim-side tonhi/witch-branding
questions. This script adds narrow IndiaCode-backed chunks for Chhattisgarh so
the answer can cite the state Act instead of only saying the source is missing.
It updates the local index; it does not commit generated data.
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


SOURCE_URL = "https://www.indiacode.nic.in/bitstream/123456789/12786/1/the_chhattisgarh_tonahi_pratadna_nivaran_act%2C_2005_no._17_of_2005_date_26.09.2005.pdf"


CHHATTISGARH_TONAHI_CHUNKS = [
    {
        "slug": "chhattisgarh-tonahi-pratadna-nivaran-2005",
        "title": "Chhattisgarh Tonahi Pratadna Nivaran Act 2005",
        "source_url": SOURCE_URL,
        "subject_area": "criminal",
        "anchor": "chhattisgarh-tonahi-pratadna-nivaran-2005/sec-1",
        "section_no": "1",
        "section_title": "Short title, extent and commencement",
        "text_is_verbatim": False,
        "text": (
            "Chhattisgarh Tonahi Pratadna Nivaran Act 2005, Section 1\n\n"
            "Section 1 states that the Act is called the Chhattisgarh Tonahi "
            "Pratadna Nivaran Adhiniyam, 2005, extends to the whole State of "
            "Chhattisgarh, and came into force from publication in the Official "
            "Gazette. For a tonhi or Tonahi allegation, verify the state and "
            "incident location before applying this Chhattisgarh-specific source."
        ),
    },
    {
        "slug": "chhattisgarh-tonahi-pratadna-nivaran-2005",
        "title": "Chhattisgarh Tonahi Pratadna Nivaran Act 2005",
        "source_url": SOURCE_URL,
        "subject_area": "criminal",
        "anchor": "chhattisgarh-tonahi-pratadna-nivaran-2005/sec-2",
        "section_no": "2",
        "section_title": "Definitions of Tonahi, identifier, Ojha and damage",
        "text_is_verbatim": False,
        "text": (
            "Chhattisgarh Tonahi Pratadna Nivaran Act 2005, Section 2\n\n"
            "Section 2 defines Tonahi as a person indicated by another as able "
            "to harm people, society, animals, or living things by black magic, "
            "evil eye, or similar means, including names such as Dayan or Tonaha. "
            "It also defines an identifier, an Ojha, and damage including physical, "
            "mental, economic and reputational harm."
        ),
    },
    {
        "slug": "chhattisgarh-tonahi-pratadna-nivaran-2005",
        "title": "Chhattisgarh Tonahi Pratadna Nivaran Act 2005",
        "source_url": SOURCE_URL,
        "subject_area": "criminal",
        "anchor": "chhattisgarh-tonahi-pratadna-nivaran-2005/sec-3",
        "section_no": "3",
        "section_title": "Act not in derogation of other law",
        "text_is_verbatim": False,
        "text": (
            "Chhattisgarh Tonahi Pratadna Nivaran Act 2005, Section 3\n\n"
            "Section 3 states that the Act is in addition to, and not in "
            "derogation of, other law for the time being in force. For accused "
            "or victim questions, keep the Tonahi Act separate from BNS/IPC "
            "and BNSS/CrPC offences and procedure."
        ),
    },
    {
        "slug": "chhattisgarh-tonahi-pratadna-nivaran-2005",
        "title": "Chhattisgarh Tonahi Pratadna Nivaran Act 2005",
        "source_url": SOURCE_URL,
        "subject_area": "criminal",
        "anchor": "chhattisgarh-tonahi-pratadna-nivaran-2005/sec-4",
        "section_no": "4",
        "section_title": "Punishment for identifying Tonahi",
        "text_is_verbatim": False,
        "text": (
            "Chhattisgarh Tonahi Pratadna Nivaran Act 2005, Section 4\n\n"
            "Section 4 punishes identifying any person as Tonahi by any means, "
            "with rigorous imprisonment that may extend to three years and fine. "
            "In a false-case or defence question, compare the FIR words and facts "
            "with the specific allegation of identifying someone as Tonahi."
        ),
    },
    {
        "slug": "chhattisgarh-tonahi-pratadna-nivaran-2005",
        "title": "Chhattisgarh Tonahi Pratadna Nivaran Act 2005",
        "source_url": SOURCE_URL,
        "subject_area": "criminal",
        "anchor": "chhattisgarh-tonahi-pratadna-nivaran-2005/sec-5",
        "section_no": "5",
        "section_title": "Punishment for harassment",
        "text_is_verbatim": False,
        "text": (
            "Chhattisgarh Tonahi Pratadna Nivaran Act 2005, Section 5\n\n"
            "Section 5 punishes physical or mental harassment or damage caused "
            "to a person identified as Tonahi, with rigorous imprisonment that "
            "may extend to five years and fine. For victim-side questions, "
            "collect injury, witness, location, and exact words used."
        ),
    },
    {
        "slug": "chhattisgarh-tonahi-pratadna-nivaran-2005",
        "title": "Chhattisgarh Tonahi Pratadna Nivaran Act 2005",
        "source_url": SOURCE_URL,
        "subject_area": "criminal",
        "anchor": "chhattisgarh-tonahi-pratadna-nivaran-2005/sec-10",
        "section_no": "10",
        "section_title": "Offences cognizable and non-bailable",
        "text_is_verbatim": False,
        "text": (
            "Chhattisgarh Tonahi Pratadna Nivaran Act 2005, Section 10\n\n"
            "Section 10 states that offences punishable under the Act are "
            "cognizable and non-bailable, and that bail should not be granted "
            "unless the public prosecutor has an opportunity to oppose release. "
            "For accused-side tonhi cases, this state source must be read with "
            "the exact FIR sections and the BNSS/CrPC bail route."
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
        for spec in CHHATTISGARH_TONAHI_CHUNKS:
            inserted += await _upsert_extra_section_chunk(conn, spec)
        print(f"chhattisgarh tonahi sources: inserted/updated {inserted} section chunks")
    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(main())
