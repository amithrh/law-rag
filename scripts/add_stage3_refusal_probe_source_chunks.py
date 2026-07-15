#!/usr/bin/env python3
"""Backfill official sections for Stage 3 refusal-probe gaps.

These chunks are intentionally narrow. They support high-risk prompts where the
answer needs the controlling statute rather than a judgment that merely mentions
the statute.
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


STAGE3_REFUSAL_SOURCE_CHUNKS = [
    {
        "slug": "arms-1959",
        "title": "Arms Act 1959",
        "source_url": "https://www.indiacode.nic.in/bitstream/123456789/1398/1/A1959_54.pdf",
        "subject_area": "criminal",
        "anchor": "arms-1959/sec-2",
        "section_no": "2",
        "section_title": "Definitions and interpretation",
        "text_is_verbatim": False,
        "text": (
            "Arms Act 1959, Section 2\n\n"
            "Section 2 defines arms for the Act. The definition covers articles "
            "designed or adapted as weapons for offence or defence, including "
            "firearms and sharp-edged or other deadly weapons, but excludes "
            "articles designed solely for domestic or agricultural uses, such as "
            "ordinary agricultural or household implements, and toy or non-serviceable "
            "weapons.\n\n"
            "For a farming-tool allegation, use this definition source before "
            "assuming an axe, sickle, knife, or similar implement is automatically "
            "an Arms Act weapon. The FIR section, seizure memo, local notification, "
            "place, purpose, and allegation of threat or violence still matter."
        ),
    },
    {
        "slug": "arms-1959",
        "title": "Arms Act 1959",
        "source_url": "https://www.indiacode.nic.in/bitstream/123456789/1398/1/A1959_54.pdf",
        "subject_area": "criminal",
        "anchor": "arms-1959/sec-4",
        "section_no": "4",
        "section_title": "Licence for acquisition and possession of arms of specified description",
        "text_is_verbatim": False,
        "text": (
            "Arms Act 1959, Section 4\n\n"
            "Section 4 lets the Central Government notify an area and class or "
            "description of non-firearm arms for which acquisition, possession, "
            "or carrying requires a licence. If such a notification applies, a "
            "person must hold a licence for those notified arms in that area.\n\n"
            "For an axe or farming-tool case, verify whether Section 4 has been "
            "invoked through a notification covering the area and the exact class "
            "of article. Do not answer only from a generic weapon label."
        ),
    },
    {
        "slug": "arms-1959",
        "title": "Arms Act 1959",
        "source_url": "https://www.indiacode.nic.in/bitstream/123456789/1398/1/A1959_54.pdf",
        "subject_area": "criminal",
        "anchor": "arms-1959/sec-25",
        "section_no": "25",
        "section_title": "Punishment for certain offences",
        "text_is_verbatim": False,
        "text": (
            "Arms Act 1959, Section 25\n\n"
            "Section 25 is the penalty source for specified Arms Act offences, "
            "including contraventions involving prohibited arms or ammunition and "
            "other acquisition, possession, carrying, manufacture, sale, transfer, "
            "or transport offences covered by the Act.\n\n"
            "For a user booked under the Arms Act, collect the FIR section, seizure "
            "memo, article description, licence or notification allegation, and "
            "whether any separate violence or threat section is alleged before "
            "estimating bail or defence strategy."
        ),
    },
    {
        "slug": "maharashtra-control-organised-crime-1999",
        "title": "Maharashtra Control of Organised Crime Act 1999",
        "source_url": "https://www.indiacode.nic.in/bitstream/123456789/16362/1/the_maharashtra_control_of_organised.pdf",
        "subject_area": "criminal",
        "anchor": "maharashtra-control-organised-crime-1999/sec-21",
        "section_no": "21",
        "section_title": "Modified application of certain provisions of the Code",
        "text_is_verbatim": False,
        "text": (
            "Maharashtra Control of Organised Crime Act 1999, Section 21\n\n"
            "Section 21 modifies ordinary Code of Criminal Procedure custody and "
            "bail rules for MCOCA cases. For investigation custody, the Code's "
            "fifteen-day and sixty-day references are modified to thirty days and "
            "ninety days, and the Special Court may extend the investigation period "
            "up to one hundred and eighty days on the Public Prosecutor's report "
            "showing investigation progress and specific reasons for detention "
            "beyond ninety days.\n\n"
            "For a MCOCA default-bail question, verify first remand date, "
            "chargesheet status, the Public Prosecutor extension report, and the "
            "Special Court extension order before applying an ordinary 60/90-day "
            "default-bail calculation."
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
        for spec in STAGE3_REFUSAL_SOURCE_CHUNKS:
            count = await _upsert_extra_section_chunk(conn, spec)
            print(f"{spec['slug']}: inserted/updated {count} chunk at {spec['anchor']}")
    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(main())
