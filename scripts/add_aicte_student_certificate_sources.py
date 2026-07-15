#!/usr/bin/env python3
"""Backfill official AICTE student certificate-return guideline chunks.

This covers high-frequency college prompts where an institution withholds
original certificates after withdrawal/cancellation. It stores only narrow,
reviewed official-guideline chunks so the product can fail closed unless this
source is present in the local index.
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


AICTE_APH_2022_23_URL = "https://aicte-qa.aicte-india.org/sites/default/files/Approval%20Process%20Handbook%2022-23.pdf"


AICTE_CERTIFICATE_CHUNKS = [
    {
        "slug": "aicte-approval-process-handbook-2023",
        "title": "All India Council for Technical Education Approval Process Handbook 2022-23",
        "source_url": AICTE_APH_2022_23_URL,
        "origin": "aicte",
        "source_type": "guideline",
        "subject_area": "education",
        "anchor": "aicte-approval-process-handbook-2023/refund-original-documents-8.13",
        "section_no": "8.13",
        "section_title": "Refund cases and return of original documents",
        "text_is_verbatim": False,
        "text": (
            "All India Council for Technical Education Approval Process Handbook 2022-23, Clause 8.13\n\n"
            "For refund/cancellation cases, the Handbook records that an institution should return "
            "the original documents and should not demand fee for subsequent years from students "
            "cancelling admission at any point of time. It also states that fee refund along with "
            "return of certificates should be completed within 7 days. This chunk is a narrow "
            "official-guideline summary for student prompts about colleges or technical institutions "
            "withholding original certificates after withdrawal, leaving a course, or cancellation."
        ),
    },
    {
        "slug": "aicte-approval-process-handbook-2023",
        "title": "All India Council for Technical Education Approval Process Handbook 2022-23",
        "source_url": AICTE_APH_2022_23_URL,
        "origin": "aicte",
        "source_type": "guideline",
        "subject_area": "education",
        "anchor": "aicte-approval-process-handbook-2023/complaint-cases",
        "section_no": "8.17",
        "section_title": "Complaint cases",
        "text_is_verbatim": False,
        "text": (
            "All India Council for Technical Education Approval Process Handbook 2022-23, Clause 8.17\n\n"
            "The Handbook describes complaint handling for AICTE-approved institutions through "
            "grievance redressal and AICTE complaint scrutiny/hearing processes. For a student "
            "whose original certificates are withheld, this supports asking the institution for a "
            "written reason and escalating with admission, withdrawal, fee, and certificate-return "
            "records to the institutional grievance cell and AICTE/technical-education grievance route "
            "where the institution or course is AICTE-approved."
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
        for spec in AICTE_CERTIFICATE_CHUNKS:
            inserted += await _upsert_extra_section_chunk(conn, spec)
        print(f"aicte certificate sources: inserted/updated {inserted} guideline chunks")
    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(main())
