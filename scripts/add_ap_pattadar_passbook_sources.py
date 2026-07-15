#!/usr/bin/env python3
"""Backfill narrow official pattadar/passbook record-of-rights sources.

The hard user slice includes lost/delayed pattadar passbook questions. The
local corpus otherwise retrieves Supreme Court land-record snippets instead of
the controlling state record-of-rights statute. This script updates the local
index only; it does not commit generated data.
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


AP_ROR_SOURCE_URL = "https://www.indiacode.nic.in/bitstream/123456789/19253/1/ror_act_5.12.2022_.pdf"


AP_PATTADAR_PASSBOOK_CHUNKS = [
    {
        "slug": "andhra-pradesh-rights-land-pattadar-passbooks-1971",
        "title": "Andhra Pradesh Rights in Land and Pattadar Pass Books Act 1971",
        "source_url": AP_ROR_SOURCE_URL,
        "origin": "indiacode",
        "subject_area": "property",
        "anchor": "andhra-pradesh-rights-land-pattadar-passbooks-1971/sec-3",
        "section_no": "3",
        "section_title": "Preparation and maintenance of record of rights in all lands",
        "manual_section_backfill": True,
        "text_is_verbatim": False,
        "text": (
            "Andhra Pradesh Rights in Land and Pattadar Pass Books Act 1971, Section 3\n\n"
            "Section 3 is the record-of-rights source for Andhra Pradesh pattadar/passbook "
            "questions. It provides for preparation, updating, and maintenance of record "
            "of rights in village lands by the recording authority. The record includes "
            "names of owners, pattadars, mortgagees, occupants, tenants, the nature and "
            "extent of their rights or interests, revenue/rent liabilities, and prescribed "
            "particulars. A person affected by an entry can seek rectification through the "
            "prescribed revenue process."
        ),
    },
    {
        "slug": "andhra-pradesh-rights-land-pattadar-passbooks-1971",
        "title": "Andhra Pradesh Rights in Land and Pattadar Pass Books Act 1971",
        "source_url": AP_ROR_SOURCE_URL,
        "origin": "indiacode",
        "subject_area": "property",
        "anchor": "andhra-pradesh-rights-land-pattadar-passbooks-1971/sec-4",
        "section_no": "4",
        "section_title": "Acquisition of rights to be intimated",
        "manual_section_backfill": True,
        "text_is_verbatim": False,
        "text": (
            "Andhra Pradesh Rights in Land and Pattadar Pass Books Act 1971, Section 4\n\n"
            "Section 4 is the mutation-intimation source. A person acquiring a right by "
            "succession, survivorship, inheritance, partition, government patta, court "
            "decree, sale, gift, mortgage, lease, or other land transaction must intimate "
            "the acquisition to the Mandal Revenue Officer / revenue authority in writing. "
            "Use this source when the user asks how to enter a name in revenue records, "
            "mutate land after death or transfer, or follow up on a patta/passbook record."
        ),
    },
    {
        "slug": "andhra-pradesh-rights-land-pattadar-passbooks-1971",
        "title": "Andhra Pradesh Rights in Land and Pattadar Pass Books Act 1971",
        "source_url": AP_ROR_SOURCE_URL,
        "origin": "indiacode",
        "subject_area": "property",
        "anchor": "andhra-pradesh-rights-land-pattadar-passbooks-1971/sec-5",
        "section_no": "5",
        "section_title": "Amendment of record of rights and appeal",
        "manual_section_backfill": True,
        "text_is_verbatim": False,
        "text": (
            "Andhra Pradesh Rights in Land and Pattadar Pass Books Act 1971, Section 5\n\n"
            "Section 5 is the amendment/update source for record-of-rights entries after "
            "rights are acquired or a record needs correction. It is relevant to delayed "
            "mutation, name-entry, and patta/passbook correction questions. The route is "
            "the revenue authority first, followed by the prescribed appeal/revision route "
            "when an amendment is refused, delayed, or incorrectly made."
        ),
    },
    {
        "slug": "andhra-pradesh-rights-land-pattadar-passbooks-1971",
        "title": "Andhra Pradesh Rights in Land and Pattadar Pass Books Act 1971",
        "source_url": AP_ROR_SOURCE_URL,
        "origin": "indiacode",
        "subject_area": "property",
        "anchor": "andhra-pradesh-rights-land-pattadar-passbooks-1971/sec-6F-7",
        "section_no": "6F-7",
        "section_title": "Bhudhaar card, passbook status, inspection and certified copies",
        "manual_section_backfill": True,
        "text_is_verbatim": False,
        "text": (
            "Andhra Pradesh Rights in Land and Pattadar Pass Books Act 1971, Sections 6F and 7\n\n"
            "Sections 6F and 7 are useful for lost, damaged, or unavailable pattadar "
            "passbook / title-deed-cum-passbook questions. Section 6F addresses Bhudhaar "
            "cards generated for parcels of land and their legal value/status compared "
            "with pattadar passbook-cum-title deed records. Section 7 provides for public "
            "inspection of record-of-rights records and certified copies or extracts on "
            "payment of the prescribed fee. For a lost passbook after flood, first seek "
            "the certified extract/record, passbook/Bhudhaar status, and written rejection "
            "or missing-document reason from the Tahsildar/MRO or land-record portal."
        ),
    },
    {
        "slug": "andhra-pradesh-rights-land-pattadar-passbooks-1971",
        "title": "Andhra Pradesh Rights in Land and Pattadar Pass Books Act 1971",
        "source_url": AP_ROR_SOURCE_URL,
        "origin": "indiacode",
        "subject_area": "property",
        "anchor": "andhra-pradesh-rights-land-pattadar-passbooks-1971/sec-9-10",
        "section_no": "9-10",
        "section_title": "Revision and powers of recording/appellate authorities",
        "manual_section_backfill": True,
        "text_is_verbatim": False,
        "text": (
            "Andhra Pradesh Rights in Land and Pattadar Pass Books Act 1971, Sections 9 and 10\n\n"
            "Sections 9 and 10 support escalation where the recording authority or Mandal "
            "Revenue Officer delays, refuses, or incorrectly deals with a record-of-rights "
            "or passbook matter. The Collector/revisional authority can examine records "
            "for correctness, legality, and propriety, and recording/appellate authorities "
            "have civil-court-like powers for enquiry. Use this for revenue appeal/revision "
            "guidance after obtaining the application number, written order, or refusal."
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
        for spec in AP_PATTADAR_PASSBOOK_CHUNKS:
            inserted += await _upsert_extra_section_chunk(conn, spec)
        print(f"ap pattadar passbook sources: inserted/updated {inserted} section chunks")
    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(main())
