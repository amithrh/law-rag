#!/usr/bin/env python3
"""Backfill focused JJ Act adoption section chunks.

The indexed `jj-2015` document currently has clean section-30 CWC chunks but
does not expose Chapter VIII adoption sections. Relative-adoption queries then
either miss JJ Act authority or fall back to unrelated section-30 chunks.

This script adds narrow India Code-backed summary chunks for the adoption
sections the route/source-pack needs. It updates the local index only; it does
not commit generated data.
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


SOURCE_URL = "https://www.indiacode.nic.in/bitstream/123456789/2148/1/a2016-2.pdf"


JJ_ADOPTION_CHUNKS = [
    {
        "slug": "jj-2015",
        "title": "Juvenile Justice (Care and Protection of Children) Act 2015",
        "source_url": SOURCE_URL,
        "origin": "indiacode",
        "subject_area": "Family",
        "anchor": "jj-2015/sec-56",
        "section_no": "56",
        "section_title": "Adoption",
        "text_is_verbatim": False,
        "text": (
            "Juvenile Justice (Care and Protection of Children) Act 2015, Section 56 - Adoption.\n\n"
            "Section 56 is the core JJ Act adoption source. It says adoption is used to ensure "
            "a right to family for orphan, abandoned, and surrendered children under the Act, "
            "rules, and adoption regulations framed by the Authority. It also recognises "
            "relative-to-relative adoption irrespective of religion, subject to the Act and "
            "adoption regulations; Hindu Adoptions and Maintenance Act adoptions remain "
            "outside the JJ Act route. Inter-country adoption and taking a child abroad require "
            "the valid order route under the Act."
        ),
    },
    {
        "slug": "jj-2015",
        "title": "Juvenile Justice (Care and Protection of Children) Act 2015",
        "source_url": SOURCE_URL,
        "origin": "indiacode",
        "subject_area": "Family",
        "anchor": "jj-2015/sec-57",
        "section_no": "57",
        "section_title": "Eligibility of prospective adoptive parents",
        "text_is_verbatim": False,
        "text": (
            "Juvenile Justice (Care and Protection of Children) Act 2015, Section 57 - Eligibility of prospective adoptive parents.\n\n"
            "Section 57 is the eligibility source for prospective adoptive parents. It requires "
            "prospective adoptive parents to be physically fit, financially sound, mentally "
            "alert, and motivated to provide a good upbringing. For a couple, both spouses' "
            "consent is required. A single or divorced person may adopt subject to the Act and "
            "adoption regulations, but a single male is not eligible to adopt a girl child."
        ),
    },
    {
        "slug": "jj-2015",
        "title": "Juvenile Justice (Care and Protection of Children) Act 2015",
        "source_url": SOURCE_URL,
        "origin": "indiacode",
        "subject_area": "Family",
        "anchor": "jj-2015/sec-58",
        "section_no": "58",
        "section_title": "Procedure for adoption by Indian prospective adoptive parents living in India",
        "text_is_verbatim": False,
        "text": (
            "Juvenile Justice (Care and Protection of Children) Act 2015, Section 58 - Procedure for adoption by Indian prospective adoptive parents living in India.\n\n"
            "Section 58 is the domestic adoption procedure source. Indian prospective adoptive "
            "parents living in India may apply through a Specialised Adoption Agency as "
            "provided in adoption regulations. The agency prepares the home study report, "
            "refers a child declared legally free for adoption with child-study and medical "
            "reports, gives the child in pre-adoption foster care after acceptance, and files "
            "for the adoption order before the District Magistrate route under the amended Act."
        ),
    },
    {
        "slug": "jj-2015",
        "title": "Juvenile Justice (Care and Protection of Children) Act 2015",
        "source_url": SOURCE_URL,
        "origin": "indiacode",
        "subject_area": "Family",
        "anchor": "jj-2015/sec-60",
        "section_no": "60",
        "section_title": "Procedure for inter-country relative adoption",
        "text_is_verbatim": False,
        "text": (
            "Juvenile Justice (Care and Protection of Children) Act 2015, Section 60 - Procedure for inter-country relative adoption.\n\n"
            "Section 60 is the inter-country relative-adoption source. A relative living abroad "
            "who intends to adopt a child from a relative in India must obtain the District "
            "Magistrate order and apply for the Authority's no-objection certificate under "
            "the adoption regulations. The Authority issues the no-objection certificate to "
            "the concerned immigration authorities, and adoptive parents receive the child "
            "from the biological parents after the certificate."
        ),
    },
    {
        "slug": "jj-2015",
        "title": "Juvenile Justice (Care and Protection of Children) Act 2015",
        "source_url": SOURCE_URL,
        "origin": "indiacode",
        "subject_area": "Family",
        "anchor": "jj-2015/sec-62",
        "section_no": "62",
        "section_title": "Additional procedural requirements and documentation",
        "text_is_verbatim": False,
        "text": (
            "Juvenile Justice (Care and Protection of Children) Act 2015, Section 62 - Additional procedural requirements and documentation.\n\n"
            "Section 62 is the documentation source for adoption matters not expressly detailed "
            "in the Act. Documentation and other procedural requirements for adoption by "
            "Indian prospective adoptive parents, non-resident Indians, overseas citizens of "
            "India, persons of Indian origin, or foreign prospective adoptive parents are as "
            "provided in the adoption regulations framed by the Authority."
        ),
    },
    {
        "slug": "jj-2015",
        "title": "Juvenile Justice (Care and Protection of Children) Act 2015",
        "source_url": SOURCE_URL,
        "origin": "indiacode",
        "subject_area": "Family",
        "anchor": "jj-2015/sec-63",
        "section_no": "63",
        "section_title": "Effect of adoption",
        "text_is_verbatim": False,
        "text": (
            "Juvenile Justice (Care and Protection of Children) Act 2015, Section 63 - Effect of adoption.\n\n"
            "Section 63 is the legal-effect source. Once an adoption order is issued by the "
            "District Magistrate route under the amended Act, the child becomes the child of "
            "the adoptive parents and the adoptive parents become the child's parents as if "
            "the child had been born to them, including for intestacy. Ties with the birth "
            "family are replaced by the adoption order, subject to property already vested in "
            "the adopted child and related obligations."
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
        for spec in JJ_ADOPTION_CHUNKS:
            inserted += await _upsert_extra_section_chunk(conn, spec)
        print(f"jj adoption sources: inserted/updated {inserted} section chunks")
    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(main())
