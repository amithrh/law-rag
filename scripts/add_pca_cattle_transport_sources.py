#!/usr/bin/env python3
"""Backfill narrow official animal-transport sources.

These chunks cover common cattle/buffalo transport accused-side prompts. They
use IndiaCode for the Prevention of Cruelty to Animals Act and AWBI for the
Transport of Animals Rules. The script updates the local index only; it does
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


PCA_SOURCE_URL = (
    "https://www.indiacode.nic.in/bitstream/123456789/11237/1/"
    "the_prevention_of_cruelty_to_animals_act%2C_1960.pdf"
)
TRANSPORT_RULES_URL = (
    "https://awbi.gov.in/uploads/regulations/"
    "163309961689TRANSPORT%20OF%20ANIMALS%2C%20RULES%2C%201978.pdf"
)


PCA_CATTLE_TRANSPORT_CHUNKS = [
    {
        "slug": "prevention-cruelty-animals-1960",
        "title": "Prevention of Cruelty to Animals Act 1960",
        "source_url": PCA_SOURCE_URL,
        "subject_area": "criminal",
        "anchor": "prevention-cruelty-animals-1960/sec-11",
        "section_no": "11",
        "section_title": "Treating animals cruelly",
        "text_is_verbatim": False,
        "text": (
            "Prevention of Cruelty to Animals Act 1960, Section 11\n\n"
            "Section 11 is the animal-cruelty source to verify when a cattle, cow, "
            "buffalo, bullock, calf, or other animal transport FIR alleges cruel "
            "carriage or transport conditions. It covers overloading, overdriving, "
            "beating, carrying or conveying an animal in a manner or position that "
            "subjects it to unnecessary pain or suffering, and lack of sufficient "
            "food, drink, or shelter. For an accused-side buffalo-to-mandi question, "
            "do not use this as a state cow-slaughter or cattle-preservation source; "
            "use it only for the animal-cruelty / transport-condition track."
        ),
    },
    {
        "slug": "prevention-cruelty-animals-1960",
        "title": "Prevention of Cruelty to Animals Act 1960",
        "source_url": PCA_SOURCE_URL,
        "subject_area": "criminal",
        "anchor": "prevention-cruelty-animals-1960/sec-29",
        "section_no": "29",
        "section_title": "Power of court to deprive person convicted of ownership of animal",
        "text_is_verbatim": False,
        "text": (
            "Prevention of Cruelty to Animals Act 1960, Section 29\n\n"
            "Section 29 is relevant where the seized animal's custody, forfeiture, "
            "or return is in issue after an animal-cruelty accusation. If the owner "
            "is convicted of an offence under the Act, the court may order forfeiture "
            "or disposal of the animal and may prohibit custody of animals in specified "
            "circumstances. For a buffalo/cattle transport arrest, keep this separate "
            "from bail/remand procedure and from the exact state cattle-preservation "
            "law named in the FIR."
        ),
    },
    {
        "slug": "transport-of-animals-rules-1978",
        "title": "Transport of Animals Rules 1978",
        "source_url": TRANSPORT_RULES_URL,
        "source_type": "rule",
        "origin": "animal_welfare_board_of_india",
        "subject_area": "criminal",
        "anchor": "transport-of-animals-rules-1978/rules-46-56",
        "section_no": "46-56",
        "section_title": "Transport of cattle",
        "manual_section_backfill": True,
        "text_is_verbatim": False,
        "text": (
            "Transport of Animals Rules 1978, Rules 46 to 56\n\n"
            "Rules 46 to 56 are the cattle transport rule cluster. They apply to "
            "transport by rail of cows, bulls, bullocks, buffaloes, yaks, and calves, "
            "and are useful checks for road/rail animal-transport allegations when "
            "the FIR or seizure memo mentions animal-transport conditions. The rules "
            "refer to a qualified veterinary surgeon's fitness certificate, refusal "
            "by the carrier if the certificate is absent, veterinary first-aid "
            "equipment, consignment labels, advance information to the consignee, "
            "minimum space, proper loading/unloading, feeding and watering before "
            "loading, pregnancy separation, emergency water/feed, ventilation, and "
            "attendant requirements. Use these as animal-transport-rule checks, not "
            "as a substitute for the exact State cattle/cow preservation law."
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
        for spec in PCA_CATTLE_TRANSPORT_CHUNKS:
            inserted += await _upsert_extra_section_chunk(conn, spec)
        print(f"pca cattle transport sources: inserted/updated {inserted} section chunks")
    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(main())
