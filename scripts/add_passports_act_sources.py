#!/usr/bin/env python3
"""Backfill official Passports Act sections for passport-verification routes.

These chunks cover common RPO / police-verification questions where the corpus
previously had no verified Passports Act bare-Act source. They are section-scoped
and sourced from India Code / Passport Seva official PDFs.
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


PASSPORTS_SOURCE_URL = "https://www.indiacode.nic.in/bitstream/123456789/1372/1/196715.pdf"

PASSPORTS_SOURCE_META = {
    "source_type": "official_summary",
    "text_is_verbatim": False,
}

PASSPORTS_CHUNKS = [
    {
        "slug": "passports-1967",
        "title": "Passports Act 1967",
        "source_url": PASSPORTS_SOURCE_URL,
        "subject_area": "constitutional",
        **PASSPORTS_SOURCE_META,
        "anchor": "passports-1967/sec-5",
        "section_no": "5",
        "section_title": "Applications for passports, travel documents, etc., and orders thereon",
        "text": (
            "Passports Act 1967, Section 5\n\n"
            "Section 5 provides for an application to the passport authority for issue of a passport "
            "or travel document. After making inquiry, if any, the passport authority may issue the "
            "passport or travel document, refuse to make an endorsement, refuse to issue the passport "
            "or travel document, or issue it with endorsements. Where the authority refuses or restricts "
            "the passport under section 5(2)(b) or section 5(2)(c), it must record a brief statement "
            "of reasons in writing and furnish a copy on demand, unless furnishing reasons is withheld "
            "on the statutory public-interest grounds."
        ),
    },
    {
        "slug": "passports-1967",
        "title": "Passports Act 1967",
        "source_url": PASSPORTS_SOURCE_URL,
        "subject_area": "constitutional",
        **PASSPORTS_SOURCE_META,
        "anchor": "passports-1967/sec-6",
        "section_no": "6",
        "section_title": "Refusal of passports, travel documents, etc.",
        "text": (
            "Passports Act 1967, Section 6\n\n"
            "Section 6 limits the grounds on which the passport authority may refuse endorsement "
            "or issue of a passport or travel document. For issue of a passport, the listed grounds "
            "include citizenship, sovereignty and security concerns, friendly relations with foreign "
            "countries, conviction for certain offences during the preceding five years, pending "
            "criminal proceedings before a court, court warrant or summons, court order prohibiting "
            "departure from India, unreimbursed repatriation expenditure, and public interest. The "
            "authority must use the statutory grounds rather than an unsupported police-verification "
            "label."
        ),
    },
    {
        "slug": "passports-1967",
        "title": "Passports Act 1967",
        "source_url": PASSPORTS_SOURCE_URL,
        "subject_area": "constitutional",
        **PASSPORTS_SOURCE_META,
        "anchor": "passports-1967/sec-10",
        "section_no": "10",
        "section_title": "Variation, impounding and revocation of passports and travel documents",
        "text": (
            "Passports Act 1967, Section 10\n\n"
            "Section 10 deals with variation, impounding and revocation of passports and travel "
            "documents. The passport authority may vary or cancel endorsements and may impound or "
            "revoke a passport or travel document on statutory grounds, including wrong possession, "
            "suppression of material information, sovereignty/security/public-interest grounds, "
            "conviction after issue, pending criminal court proceedings, court warrant or summons, "
            "or court order prohibiting departure. The authority must record reasons in writing and "
            "provide a copy on demand unless the Act permits withholding reasons on specified grounds."
        ),
    },
    {
        "slug": "passports-1967",
        "title": "Passports Act 1967",
        "source_url": PASSPORTS_SOURCE_URL,
        "subject_area": "constitutional",
        **PASSPORTS_SOURCE_META,
        "anchor": "passports-1967/sec-11",
        "section_no": "11",
        "section_title": "Appeals",
        "text": (
            "Passports Act 1967, Section 11\n\n"
            "Section 11 provides an appeal route for persons aggrieved by passport-authority orders "
            "under the Act, including refusal, variation, impounding or revocation orders, subject to "
            "the statutory limits and prescribed procedure. For a passport-verification hold or adverse "
            "report, the practical first step is to obtain the written RPO/passport-authority order or "
            "reason, then use the passport grievance or appeal route with the file number and supporting "
            "case-status documents."
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
        for spec in PASSPORTS_CHUNKS:
            inserted += await _upsert_extra_section_chunk(conn, spec)
        print(f"passports-1967: inserted/updated {inserted} section chunks")
    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(main())
