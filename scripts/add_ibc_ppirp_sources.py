#!/usr/bin/env python3
"""Backfill narrow official PPIRP filing sources for MSME pre-pack queries.

The IBC Act source explains the pre-packaged insolvency framework, but common
user questions also ask the filing process. These chunks add source-backed
Rules/Regulations coverage so the answer can cite the application/form route
instead of pretending the Act alone covers every filing detail.
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


PPIRP_RULES_SOURCE_URL = "https://ibbi.gov.in/uploads/legalframwork/f75906d8657a51f214785c697d9bb296.pdf"
PPIRP_REGULATIONS_SOURCE_URL = "https://ibbi.gov.in/uploads/legalframwork/0d3172dcf2af1abd881ffd62acb86553.pdf"


PPIRP_CHUNKS = [
    {
        "slug": "ibc-ppirp-rules-2021",
        "title": "Insolvency and Bankruptcy (Pre-Packaged Insolvency Resolution Process) Rules 2021",
        "source_url": PPIRP_RULES_SOURCE_URL,
        "source_type": "official_summary",
        "origin": "ibbi",
        "subject_area": "ibc_nclt",
        "anchor": "ibc-ppirp-rules-2021/rule-4",
        "section_no": "4",
        "section_title": "Application by corporate applicant",
        "manual_section_backfill": True,
        "text_is_verbatim": False,
        "text": (
            "Insolvency and Bankruptcy (Pre-Packaged Insolvency Resolution Process) Rules 2021, Rule 4\n\n"
            "Rule 4 is the PPIRP filing route for an application by a corporate applicant. "
            "A corporate applicant seeking initiation of pre-packaged insolvency resolution "
            "process files an application to the Adjudicating Authority in Form 1, accompanied "
            "by the specified fee and documents. For an MSME/corporate-debtor pre-pack question, "
            "verify the board/member approvals, creditor approvals, base resolution plan, "
            "proposed resolution professional, debt/default record, and Form 1 application papers "
            "before any NCLT filing."
        ),
    },
    {
        "slug": "ibc-ppirp-rules-2021",
        "title": "Insolvency and Bankruptcy (Pre-Packaged Insolvency Resolution Process) Rules 2021",
        "source_url": PPIRP_RULES_SOURCE_URL,
        "source_type": "official_summary",
        "origin": "ibbi",
        "subject_area": "ibc_nclt",
        "anchor": "ibc-ppirp-rules-2021/form-1",
        "section_no": "Form 1",
        "section_title": "Application for initiating PPIRP",
        "manual_section_backfill": True,
        "text_is_verbatim": False,
        "text": (
            "Insolvency and Bankruptcy (Pre-Packaged Insolvency Resolution Process) Rules 2021, Form 1\n\n"
            "Form 1 is the prescribed application format for initiating a pre-packaged "
            "insolvency resolution process. It collects corporate-debtor details, registered-office "
            "and identification particulars, proposed resolution-professional details, debt/default "
            "information, approvals, and supporting documents. For a user asking the full PPIRP "
            "process, the practical NCLT filing file must be prepared around Form 1 and the IBC "
            "Section 54A eligibility record."
        ),
    },
    {
        "slug": "ibbi-ppirp-regulations-2021",
        "title": "IBBI Pre-Packaged Insolvency Resolution Process Regulations 2021",
        "source_url": PPIRP_REGULATIONS_SOURCE_URL,
        "source_type": "official_summary",
        "origin": "ibbi",
        "subject_area": "ibc_nclt",
        "anchor": "ibbi-ppirp-regulations-2021/reg-14",
        "section_no": "14",
        "section_title": "Declaration by partners or directors",
        "manual_section_backfill": True,
        "text_is_verbatim": False,
        "text": (
            "IBBI Pre-Packaged Insolvency Resolution Process Regulations 2021, Regulation 14\n\n"
            "The PPIRP Regulations require preparatory corporate-debtor records and declarations "
            "before filing. The filing workflow should check director or partner declarations, "
            "creditor approval, eligibility, base resolution plan, proposed resolution professional, "
            "list of creditors, claims information, and related records. For an MSME debtor-side "
            "pre-pack, this regulation source supports the document checklist before NCLT/Form 1 "
            "filing."
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
        for spec in PPIRP_CHUNKS:
            inserted += await _upsert_extra_section_chunk(conn, spec)
        print(f"ibc ppirp sources: inserted/updated {inserted} section chunks")
    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(main())
