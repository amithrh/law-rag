#!/usr/bin/env python3
"""Backfill narrow official NCLT/NCLAT procedural rule sources.

Common IBC/NCLT prompts ask for filing forms, fees, certified copies, and
appeal format. The IBC and Companies Act sources do not answer those procedural
details by themselves, so these chunks add non-verbatim rule summaries from
official NCLT/NCLAT rule sources.
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


NCLT_RULES_SOURCE_URL = "https://nclt.gov.in/act-rule"
NCLT_GAZETTE_SOURCE_URL = "https://egazette.nic.in/WriteReadData/2016/170999.pdf"
NCLAT_RULES_SOURCE_URL = "https://nclat.nic.in/sites/default/files/2023-06/NCLAT_Rules.pdf"


NCLT_NCLAT_RULE_CHUNKS = [
    {
        "slug": "nclt-rules-2016",
        "title": "National Company Law Tribunal Rules 2016",
        "source_url": NCLT_GAZETTE_SOURCE_URL,
        "source_type": "rule",
        "origin": "egazette",
        "subject_area": "ibc_nclt",
        "anchor": "nclt-rules-2016/rule-23",
        "section_no": "23",
        "section_title": "Presentation of petition, application, caveat, documents, and appeal",
        "text_is_verbatim": False,
        "text": (
            "National Company Law Tribunal Rules 2016, Rule 23.\n\n"
            "Rule 23 is the NCLT presentation rule for petitions, applications, "
            "caveats, interlocutory applications, documents, and appeals. It is the "
            "procedural source to verify prescribed form use, filing counter "
            "presentation, stipulated fee, representative authority, copies, and "
            "registry scrutiny before treating an IBC/NCLT filing as ready."
        ),
    },
    {
        "slug": "nclt-rules-2016",
        "title": "National Company Law Tribunal Rules 2016",
        "source_url": NCLT_GAZETTE_SOURCE_URL,
        "source_type": "rule",
        "origin": "egazette",
        "subject_area": "ibc_nclt",
        "anchor": "nclt-rules-2016/rule-34",
        "section_no": "34",
        "section_title": "General heading, forms, affidavits, notices, and document filing",
        "text_is_verbatim": False,
        "text": (
            "National Company Law Tribunal Rules 2016, Rule 34.\n\n"
            "Rule 34 is the NCLT procedural source for filing a petition, "
            "application, reference, or interlocutory application using NCLT forms, "
            "attachments, affidavit verification, notice forms, indexing, and "
            "paper-book style document preparation. Use it as the form/checklist "
            "source alongside IBC Section 7, Section 8, or Section 9."
        ),
    },
    {
        "slug": "nclat-rules-2016",
        "title": "National Company Law Appellate Tribunal Rules 2016",
        "source_url": NCLAT_RULES_SOURCE_URL,
        "source_type": "rule",
        "origin": "nclat",
        "subject_area": "ibc_nclt",
        "anchor": "nclat-rules-2016/rule-22",
        "section_no": "22",
        "section_title": "Presentation of appeal",
        "text_is_verbatim": False,
        "text": (
            "National Company Law Appellate Tribunal Rules 2016, Rule 22.\n\n"
            "Rule 22 is the NCLAT presentation rule for appeals. It supports "
            "checking Form NCLAT-1, copies, authorised representative details, "
            "stipulated filing fee, filing counter/e-filing presentation, and "
            "registry refusal or defect risk before filing an appeal from an NCLT "
            "order."
        ),
    },
    {
        "slug": "nclat-rules-2016",
        "title": "National Company Law Appellate Tribunal Rules 2016",
        "source_url": NCLAT_RULES_SOURCE_URL,
        "source_type": "rule",
        "origin": "nclat",
        "subject_area": "ibc_nclt",
        "anchor": "nclat-rules-2016/rule-55",
        "section_no": "55",
        "section_title": "Fee for appeal, interlocutory application, and process fee",
        "text_is_verbatim": False,
        "text": (
            "National Company Law Appellate Tribunal Rules 2016, Rule 55 and "
            "Schedule of fees.\n\n"
            "Rule 55 is the NCLAT procedural source for checking appeal fee, "
            "interlocutory-application fee, process fee, and the applicable schedule "
            "before telling a user the NCLAT filing-fee route."
        ),
    },
    {
        "slug": "nclat-rules-2016",
        "title": "National Company Law Appellate Tribunal Rules 2016",
        "source_url": NCLAT_RULES_SOURCE_URL,
        "source_type": "rule",
        "origin": "nclat",
        "subject_area": "ibc_nclt",
        "anchor": "nclat-rules-2016/form-nclat-1",
        "section_no": "Form NCLAT-1",
        "section_title": "Memorandum of appeal",
        "text_is_verbatim": False,
        "text": (
            "National Company Law Appellate Tribunal Rules 2016, Form NCLAT-1.\n\n"
            "Form NCLAT-1 is the memorandum-of-appeal form for an NCLAT appeal. "
            "For format questions, verify party details, impugned order details, "
            "grounds, relief, limitation/delay facts, annexures, authorisation, and "
            "registry defects against this form/rules source."
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
        for spec in NCLT_NCLAT_RULE_CHUNKS:
            inserted += await _upsert_extra_section_chunk(conn, spec)
        print(f"nclt/nclat rule sources: inserted/updated {inserted} chunks")
    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(main())
