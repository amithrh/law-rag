#!/usr/bin/env python3
"""Backfill narrow official social-welfare sources for Stage II-C1.

This script inserts a few source-backed bare-Act chunks without writing corpus
JSONL/PDF data into the repository. It is intentionally small: these sections
support high-frequency birth/death certificate user questions where the full
Act is not yet present in the local index.
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


RBD_SOURCE_URL = "https://www.indiacode.nic.in/bitstream/123456789/1682/1/A1969-18.pdf"

RBD_CHUNKS = [
    {
        "slug": "registration-births-deaths-1969",
        "title": "Registration of Births and Deaths Act 1969",
        "source_url": RBD_SOURCE_URL,
        "subject_area": "constitutional",
        "anchor": "registration-births-deaths-1969/sec-7",
        "section_no": "7",
        "section_title": "Registrars",
        "text": (
            "Registration of Births and Deaths Act 1969, Section 7\n\n"
            "7. Registrars.--(1) The State Government may appoint a Registrar for each local area "
            "comprising the area within the jurisdiction of a municipality, panchayat or other local "
            "authority or any other area or a combination of any two or more of them. "
            "(2) Every Registrar shall enter in the register all information given under section 8 "
            "or section 9 in respect of births and deaths which have taken place in his jurisdiction, "
            "and shall take steps to inform himself carefully of every birth and death in his jurisdiction "
            "and ascertain and register the particulars required to be registered."
        ),
    },
    {
        "slug": "registration-births-deaths-1969",
        "title": "Registration of Births and Deaths Act 1969",
        "source_url": RBD_SOURCE_URL,
        "subject_area": "constitutional",
        "anchor": "registration-births-deaths-1969/sec-8",
        "section_no": "8",
        "section_title": "Persons required to register births and deaths",
        "text": (
            "Registration of Births and Deaths Act 1969, Section 8\n\n"
            "8. Persons required to register births and deaths.--(1) It shall be the duty of the "
            "specified persons to give or cause to be given, orally or in writing with signature, "
            "within such time as may be prescribed, information to the Registrar of the particulars "
            "required to be entered in the prescribed forms. In respect of births and deaths in a "
            "house, whether residential or non-residential, the head of the house or household, "
            "or the nearest relative present, or in their absence the oldest adult person present, "
            "is the reporting person."
        ),
    },
    {
        "slug": "registration-births-deaths-1969",
        "title": "Registration of Births and Deaths Act 1969",
        "source_url": RBD_SOURCE_URL,
        "subject_area": "constitutional",
        "anchor": "registration-births-deaths-1969/sec-12",
        "section_no": "12",
        "section_title": "Certificate of registration of births or deaths",
        "text": (
            "Registration of Births and Deaths Act 1969, Section 12\n\n"
            "12. Certificate of registration of births or deaths.--The Registrar shall, as soon as "
            "the registration of a birth or death has been completed, but not later than seven days, "
            "give, free of charge, electronically or otherwise under his signature, to the person who "
            "gives information under section 8 or section 9, a certificate extracted from the register "
            "relating to such birth or death in the prescribed form and manner."
        ),
    },
    {
        "slug": "registration-births-deaths-1969",
        "title": "Registration of Births and Deaths Act 1969",
        "source_url": RBD_SOURCE_URL,
        "subject_area": "constitutional",
        "anchor": "registration-births-deaths-1969/sec-13",
        "section_no": "13",
        "section_title": "Delayed registration of births and deaths",
        "text": (
            "Registration of Births and Deaths Act 1969, Section 13\n\n"
            "13. Delayed registration of births and deaths.--(1) A birth or death reported after "
            "the prescribed period but within thirty days shall be registered on payment of the "
            "prescribed late fee. (2) If delayed information is given after thirty days but within "
            "one year, registration requires written permission of the District Registrar or other "
            "authority, prescribed fee, and prescribed self-attested document. (3) If delayed "
            "information is given after one year, registration requires an order of the District "
            "Magistrate, Sub-Divisional Magistrate, or authorised Executive Magistrate having "
            "jurisdiction over the place of birth or death."
        ),
    },
    {
        "slug": "registration-births-deaths-1969",
        "title": "Registration of Births and Deaths Act 1969",
        "source_url": RBD_SOURCE_URL,
        "subject_area": "constitutional",
        "anchor": "registration-births-deaths-1969/sec-15",
        "section_no": "15",
        "section_title": "Correction or cancellation of entry",
        "text": (
            "Registration of Births and Deaths Act 1969, Section 15\n\n"
            "15. Correction or cancellation of entry in the register of births and deaths.--If it is "
            "proved to the satisfaction of the Registrar that an entry of a birth or death is erroneous "
            "in form or substance, or has been fraudulently or improperly made, he may, subject to "
            "State Government rules on conditions and circumstances, correct the error or cancel the "
            "entry by suitable marginal entry, without altering the original entry, and shall sign the "
            "marginal entry and add the date of correction or cancellation."
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
        for spec in RBD_CHUNKS:
            inserted += await _upsert_extra_section_chunk(conn, spec)
        print(f"registration-births-deaths-1969: inserted/updated {inserted} section chunks")
    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(main())
