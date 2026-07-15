#!/usr/bin/env python3
"""Backfill narrow official Rajasthan shop-registration sources.

These chunks cover common "labour inspector asked me to register under Shop
Act in Jaipur/Rajasthan" prompts. They use IndiaCode for the Rajasthan Shops
and Commercial Establishments Act and the Rajasthan Labour Department fee /
checklist page. The script updates the local index only; it does not commit
generated data.
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


RAJASTHAN_SHOPS_SOURCE_URL = (
    "https://www.indiacode.nic.in/bitstream/123456789/18868/1/"
    "the_rajasthan_shops_and_commercial_establishments_act%2C_1958.pdf"
)
RAJASTHAN_SHOPS_FEE_URL = "https://labour.rajasthan.gov.in/FeeShop.aspx"


RAJASTHAN_SHOP_CHUNKS = [
    {
        "slug": "rajasthan-shops-establishments-1958",
        "title": "Rajasthan Shops and Commercial Establishments Act 1958",
        "source_url": RAJASTHAN_SHOPS_SOURCE_URL,
        "subject_area": "business_license",
        "anchor": "rajasthan-shops-establishments-1958/sec-1",
        "section_no": "1",
        "section_title": "Short title, extent, commencement and application",
        "text_is_verbatim": False,
        "text": (
            "Rajasthan Shops and Commercial Establishments Act 1958, Section 1\n\n"
            "Section 1 states that the Act extends to the whole State of Rajasthan and "
            "applies to notified areas. For a Jaipur or Rajasthan shop-registration question, "
            "first verify the local applicability, the labour/shops registration route, and "
            "the actual written notice before shifting the user to food-safety, municipal, "
            "or other licensing law."
        ),
    },
    {
        "slug": "rajasthan-shops-establishments-1958",
        "title": "Rajasthan Shops and Commercial Establishments Act 1958",
        "source_url": RAJASTHAN_SHOPS_SOURCE_URL,
        "subject_area": "business_license",
        "anchor": "rajasthan-shops-establishments-1958/sec-2",
        "section_no": "2",
        "section_title": "Definitions of shop, establishment, inspector and registration certificate",
        "text_is_verbatim": False,
        "text": (
            "Rajasthan Shops and Commercial Establishments Act 1958, Section 2\n\n"
            "Section 2 defines establishment, shop, inspector, register of establishments, "
            "and registration certificate. A shop covers premises where trade or business "
            "is carried on or services are rendered to customers, including connected offices, "
            "storerooms, godowns and warehouses. These definitions help decide whether a "
            "small shop with staff is on the Shops Act registration path rather than FSSAI "
            "or a different trade licence."
        ),
    },
    {
        "slug": "rajasthan-shops-establishments-1958",
        "title": "Rajasthan Shops and Commercial Establishments Act 1958",
        "source_url": RAJASTHAN_SHOPS_SOURCE_URL,
        "subject_area": "business_license",
        "anchor": "rajasthan-shops-establishments-1958/sec-4",
        "section_no": "4",
        "section_title": "Registration of establishments",
        "text_is_verbatim": False,
        "text": (
            "Rajasthan Shops and Commercial Establishments Act 1958, Section 4\n\n"
            "Section 4 is the registration source. The employer of every establishment must "
            "send the Inspector of the area a prescribed statement and prescribed fee with "
            "details such as employer/manager name, establishment address, establishment "
            "name, and other prescribed particulars. After receiving the statement and fee, "
            "the Inspector registers the establishment and issues a registration certificate "
            "to be displayed at the establishment. New establishments send the statement "
            "within the statutory period from commencement of work."
        ),
    },
    {
        "slug": "rajasthan-shops-establishments-1958",
        "title": "Rajasthan Shops and Commercial Establishments Act 1958",
        "source_url": RAJASTHAN_SHOPS_SOURCE_URL,
        "subject_area": "business_license",
        "anchor": "rajasthan-shops-establishments-1958/sec-5",
        "section_no": "5",
        "section_title": "Change to be communicated to Inspector",
        "text_is_verbatim": False,
        "text": (
            "Rajasthan Shops and Commercial Establishments Act 1958, Section 5\n\n"
            "Section 5 requires the employer to notify the Inspector in prescribed form of "
            "changes in the information supplied for registration. For a labour-inspector "
            "registration or employee-count dispute, ask for the exact change, deficiency "
            "memo, employee count, and whether a fresh or amended registration certificate "
            "is being required."
        ),
    },
    {
        "slug": "rajasthan-shops-establishments-1958",
        "title": "Rajasthan Shops and Commercial Establishments Act 1958",
        "source_url": RAJASTHAN_SHOPS_SOURCE_URL,
        "subject_area": "business_license",
        "anchor": "rajasthan-shops-establishments-1958/sec-6",
        "section_no": "6",
        "section_title": "Closing of establishment to be communicated to Inspector",
        "text_is_verbatim": False,
        "text": (
            "Rajasthan Shops and Commercial Establishments Act 1958, Section 6\n\n"
            "Section 6 requires the employer to notify the Inspector in writing when an "
            "establishment is closed. It is relevant where the office treats a closed, shifted, "
            "or changed shop as still active or asks for cancellation/update records."
        ),
    },
    {
        "slug": "rajasthan-shops-fee-checklist-2026",
        "title": "Rajasthan Shops and Commercial Establishments Act 1958 Fee Structure and Checklist",
        "source_url": RAJASTHAN_SHOPS_FEE_URL,
        "source_type": "guideline",
        "origin": "rajasthan_labour_department",
        "subject_area": "business_license",
        "anchor": "rajasthan-shops-fee-checklist-2026/registration-fee-checklist",
        "section_no": "fee-checklist",
        "section_title": "Registration fee and document checklist",
        "manual_section_backfill": True,
        "text_is_verbatim": False,
        "text": (
            "Rajasthan Labour Department fee/checklist page for Rajasthan Shops and "
            "Commercial Establishments Act 1958 registration\n\n"
            "The official Labour Department page lists fee slabs for registration, including "
            "the 0-10 employee slab, and says delayed registration or renewal attracts penalty "
            "after the due registration or renewal date. The checklist says online filing, "
            "online payment, and online document submission are mandatory. Documents include "
            "employer photograph, shop photo with owner, management employee list, wage rates, "
            "employee details, weekly holidays, establishment address proof such as rent "
            "agreement or ownership proof, affidavit/declaration, and employer photo ID. "
            "For Jaipur shop-registration questions, ask for the LDMS/application number, "
            "employee count, fee/penalty calculation, deficiency memo, and inspection note."
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
        for spec in RAJASTHAN_SHOP_CHUNKS:
            inserted += await _upsert_extra_section_chunk(conn, spec)
        print(f"rajasthan shop sources: inserted/updated {inserted} section chunks")
    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(main())
