#!/usr/bin/env python3
"""Backfill CrPC Section 436A for legacy undertrial-release comparison."""
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


CRPC_436A_CHUNK = {
    "slug": "crpc-1973",
    "title": "Code of Criminal Procedure 1973",
    "source_url": "https://www.indiacode.nic.in/bitstream/123456789/6796/1/ccp1973.pdf",
    "source_type": "bare_act",
    "origin": "indiacode",
    "subject_area": "criminal",
    "anchor": "crpc-1973/sec-436-a",
    "section_no": "436A",
    "section_title": "Maximum period for which an undertrial prisoner can be detained",
    "manual_section_backfill": True,
    "text_is_verbatim": True,
    "text": (
        "Code of Criminal Procedure 1973, Section 436A\n\n"
        "436A. Maximum period for which an undertrial prisoner can be detained. "
        "Where a person has, during the period of investigation, inquiry or trial "
        "under this Code of an offence under any law, other than an offence for "
        "which the punishment of death has been specified as one of the punishments "
        "under that law, undergone detention for a period extending up to one-half "
        "of the maximum period of imprisonment specified for that offence under "
        "that law, he shall be released by the Court on his personal bond with or "
        "without sureties. Provided that the Court may, after hearing the Public "
        "Prosecutor and for reasons to be recorded in writing, order continued "
        "detention for a longer period than one-half of the said period or release "
        "him on bail instead of the personal bond with or without sureties. Provided "
        "further that no such person shall in any case be detained during the period "
        "of investigation, inquiry or trial for more than the maximum period of "
        "imprisonment provided for the said offence under that law. Explanation. "
        "In computing the period of detention under this section for granting bail, "
        "the period of detention passed due to delay in proceeding caused by the "
        "accused shall be excluded."
    ),
}


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
        inserted = await _upsert_extra_section_chunk(conn, CRPC_436A_CHUNK)
    finally:
        await conn.close()
    print(f"crpc 436A source: inserted/updated {inserted} section chunk")


if __name__ == "__main__":
    asyncio.run(main())
