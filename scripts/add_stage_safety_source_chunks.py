#!/usr/bin/env python3
"""Backfill official source chunks for safety-regression authority gaps.

This is intentionally small and idempotent. It adds only official bare-Act
section chunks that required-source packs already ask for but the local index
may not contain.
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


SAFETY_SECTION_CHUNKS = [
    {
        "slug": "uapa-1967",
        "title": "Unlawful Activities (Prevention) Act 1967",
        "source_url": "https://www.mha.gov.in/sites/default/files/A1967-37.pdf",
        "subject_area": "criminal",
        "anchor": "uapa-1967/sec-43d",
        "section_no": "43D",
        "section_title": "Modified application of certain provisions of the Code",
        "text": (
            "Unlawful Activities (Prevention) Act 1967, Section 43D\n\n"
            "43D. Modified application of certain provisions of the Code.--"
            "The UAPA modifies ordinary criminal procedure for specified UAPA "
            "offences. For default-bail and no-charge-sheet questions, the "
            "ordinary Code period must be checked with the UAPA extension "
            "provision and the Special Court order.\n\n"
            "The statutory scheme permits extension of the investigation period "
            "up to one hundred and eighty days where the Court is satisfied with "
            "the report of the Public Prosecutor indicating progress of "
            "investigation and specific reasons for detention beyond the ordinary "
            "period. Without a valid extension or timely charge-sheet, default "
            "bail must be assessed from the custody/remand timeline.\n\n"
            "Section 43D is the controlling source to verify before answering a "
            "UAPA 90-day/no-charge-sheet/default-bail question."
        ),
    },
    {
        "slug": "ndps-1985",
        "title": "Narcotic Drugs and Psychotropic Substances Act 1985",
        "source_url": "https://www.indiacode.nic.in/bitstream/123456789/1791/5/a1985-61.pdf",
        "subject_area": "criminal",
        "anchor": "ndps-1985/sec-36A",
        "section_no": "36A",
        "section_title": "Offences triable by Special Courts",
        "text": (
            "Narcotic Drugs and Psychotropic Substances Act 1985, Section 36A\n\n"
            "36A. Offences triable by Special Courts.--Notwithstanding anything "
            "contained in the Code of Criminal Procedure, 1973, offences under "
            "the NDPS Act that are triable by a Special Court are to be tried by "
            "that Special Court.\n\n"
            "For persons accused of offences punishable under section 19, section "
            "24, section 27A, or offences involving commercial quantity, references "
            "in section 167(2) of the Code of Criminal Procedure to ninety days are "
            "construed as references to one hundred and eighty days. If investigation "
            "cannot be completed within one hundred and eighty days, the Special "
            "Court may extend the period up to one year on the Public Prosecutor's "
            "report indicating progress of investigation and specific reasons for "
            "detention beyond one hundred and eighty days.\n\n"
            "Section 36A is the source to verify NDPS default/statutory bail and "
            "no-charge-sheet custody timelines before applying ordinary remand "
            "periods."
        ),
    },
    {
        "slug": "hiv-aids-2017",
        "title": "Human Immunodeficiency Virus and Acquired Immune Deficiency Syndrome (Prevention and Control) Act 2017",
        "source_url": "https://www.indiacode.nic.in/bitstream/123456789/2254/1/a2017-16.pdf",
        "subject_area": "health_privacy",
        "anchor": "hiv-aids-2017/sec-8",
        "section_no": "8",
        "section_title": "Disclosure of HIV status",
        "text": (
            "Human Immunodeficiency Virus and Acquired Immune Deficiency Syndrome "
            "(Prevention and Control) Act 2017, Section 8\n\n"
            "8. Disclosure of HIV status.--No person shall be compelled to disclose "
            "his HIV status except by an order of the court where disclosure is "
            "necessary in the interest of justice for determining issues before it.\n\n"
            "No person shall disclose or be compelled to disclose the HIV status or "
            "other private information of another person imparted in confidence or "
            "in a fiduciary relationship, except with the informed consent of that "
            "person or representative, recorded in writing, or in the limited cases "
            "specified by the Act.\n\n"
            "This is the controlling source to verify before any public online post, "
            "warning, pressure tactic, or disclosure of another person's identifiable "
            "HIV or medical status."
        ),
    },
    {
        "slug": "hiv-aids-2017",
        "title": "Human Immunodeficiency Virus and Acquired Immune Deficiency Syndrome (Prevention and Control) Act 2017",
        "source_url": "https://www.indiacode.nic.in/bitstream/123456789/2254/1/a2017-16.pdf",
        "subject_area": "health_privacy",
        "anchor": "hiv-aids-2017/sec-9",
        "section_no": "9",
        "section_title": "Disclosure of HIV-positive status to partner of HIV-positive person",
        "text": (
            "Human Immunodeficiency Virus and Acquired Immune Deficiency Syndrome "
            "(Prevention and Control) Act 2017, Section 9\n\n"
            "9. Disclosure of HIV-positive status to partner of HIV-positive person.--"
            "No healthcare provider, except a physician or counsellor, shall disclose "
            "the HIV-positive status of a person to his or her partner.\n\n"
            "A physician or counsellor may disclose to the partner only under the "
            "conditions in section 9, including counselling, assessment of significant "
            "risk of transmission, counselling of the HIV-positive person, and informing "
            "that person of the intention to disclose. Disclosure under the section is "
            "made in person after counselling.\n\n"
            "This supports the product rule that a user should not make a public online "
            "warning about another person's HIV status and should seek legal/medical "
            "counselling instead."
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
        for spec in SAFETY_SECTION_CHUNKS:
            count = await _upsert_extra_section_chunk(conn, spec)
            print(f"{spec['slug']}: inserted/updated {count} chunk at {spec['anchor']}")
    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(main())
