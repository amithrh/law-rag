#!/usr/bin/env python3
"""Backfill narrow official Tamil Nadu / Coimbatore shop-license sources.

These chunks cover common shop-license renewal and penalty questions. They use
IndiaCode for the Tamil Nadu Shops and Establishments Act and the Coimbatore
City Municipal Corporation public page for D&O trade-license process/penalty
facts. The script updates the local index; it does not commit generated data.
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


TN_SHOPS_SOURCE_URL = "https://www.indiacode.nic.in/bitstream/123456789/13171/1/tn-shops-and-establishments-act_1947.pdf"
CCMC_TRADE_LICENSE_SOURCE_URL = "https://ccmc.gov.in/index.php/department/licensing-of-offensive-trades"


TAMIL_NADU_SHOP_CHUNKS = [
    {
        "slug": "tamil-nadu-shops-establishments-1947",
        "title": "Tamil Nadu Shops and Establishments Act 1947",
        "source_url": TN_SHOPS_SOURCE_URL,
        "subject_area": "business_license",
        "anchor": "tamil-nadu-shops-establishments-1947/sec-1",
        "section_no": "1",
        "section_title": "Short title, extent and commencement",
        "text_is_verbatim": False,
        "text": (
            "Tamil Nadu Shops and Establishments Act 1947, Section 1\n\n"
            "1. Short title, extent and commencement.--The Act extends to the whole State "
            "of Tamil Nadu. The Act originally came into force in notified municipal and "
            "panchayat areas, and the 2018 Government notification recorded in the IndiaCode "
            "text extended its applicability to all areas of Tamil Nadu from 14 November 2018. "
            "For a Tamil Nadu shop or establishment question, first verify whether the issue is "
            "under the Shops Act/labour-establishment route or under a separate municipal trade "
            "licence, health licence, food licence, or local-body order."
        ),
    },
    {
        "slug": "tamil-nadu-shops-establishments-1947",
        "title": "Tamil Nadu Shops and Establishments Act 1947",
        "source_url": TN_SHOPS_SOURCE_URL,
        "subject_area": "business_license",
        "anchor": "tamil-nadu-shops-establishments-1947/sec-2",
        "section_no": "2",
        "section_title": "Definitions of shop, establishment, employer and inspector",
        "text_is_verbatim": False,
        "text": (
            "Tamil Nadu Shops and Establishments Act 1947, Section 2\n\n"
            "2. Definitions.--The Act defines commercial establishment, employer, establishment, "
            "inspector, shop, and related terms. A shop includes premises where trade or business "
            "is carried on or services are rendered to customers, including connected offices, "
            "storerooms, godowns and warehouses. For a licence-renewal or penalty dispute, these "
            "definitions help decide whether the Tamil Nadu Shops Act is the right labour/shop "
            "establishment source, separate from local municipal trade-licence requirements."
        ),
    },
    {
        "slug": "tamil-nadu-shops-establishments-1947",
        "title": "Tamil Nadu Shops and Establishments Act 1947",
        "source_url": TN_SHOPS_SOURCE_URL,
        "subject_area": "business_license",
        "anchor": "tamil-nadu-shops-establishments-1947/sec-42",
        "section_no": "42",
        "section_title": "Appointment of Inspectors",
        "text_is_verbatim": False,
        "text": (
            "Tamil Nadu Shops and Establishments Act 1947, Section 42\n\n"
            "42. Appointment of Inspectors.--The State Government may appoint officers of "
            "the State Government or of a local authority as Inspectors for the purposes of "
            "the Act and assign their local limits. For a pending renewal, inspection, or "
            "penalty dispute, the user should identify the inspector/office, local limits, "
            "written inspection note, deficiency memo, and order or fee demand."
        ),
    },
    {
        "slug": "tamil-nadu-shops-establishments-1947",
        "title": "Tamil Nadu Shops and Establishments Act 1947",
        "source_url": TN_SHOPS_SOURCE_URL,
        "subject_area": "business_license",
        "anchor": "tamil-nadu-shops-establishments-1947/sec-43",
        "section_no": "43",
        "section_title": "Powers and duties of Inspectors",
        "text_is_verbatim": False,
        "text": (
            "Tamil Nadu Shops and Establishments Act 1947, Section 43\n\n"
            "43. Powers and duties of Inspectors.--An Inspector may at all reasonable hours "
            "enter premises that are, or are believed to be, an establishment, and examine "
            "the premises and prescribed registers, records or notices. For a shop-license "
            "renewal delay or penalty issue, preserve inspection notices, registers, records, "
            "fee receipts, and any written demand or inspection remarks."
        ),
    },
    {
        "slug": "tamil-nadu-shops-establishments-1947",
        "title": "Tamil Nadu Shops and Establishments Act 1947",
        "source_url": TN_SHOPS_SOURCE_URL,
        "subject_area": "business_license",
        "anchor": "tamil-nadu-shops-establishments-1947/sec-45",
        "section_no": "45",
        "section_title": "Penalties",
        "text_is_verbatim": False,
        "text": (
            "Tamil Nadu Shops and Establishments Act 1947, Section 45\n\n"
            "45. Penalties.--Contravention of listed provisions of the Act is punishable "
            "for a first offence with fine up to five thousand rupees and for a second or "
            "subsequent offence with fine up to ten thousand rupees. This is not by itself "
            "the calculation for every municipal trade-licence renewal penalty; the user must "
            "compare the notice with the exact provision, rule, licence condition, and local "
            "municipal demand."
        ),
    },
    {
        "slug": "tamil-nadu-shops-establishments-1947",
        "title": "Tamil Nadu Shops and Establishments Act 1947",
        "source_url": TN_SHOPS_SOURCE_URL,
        "subject_area": "business_license",
        "anchor": "tamil-nadu-shops-establishments-1947/sec-46A",
        "section_no": "46A",
        "section_title": "Compounding of offences",
        "text_is_verbatim": False,
        "text": (
            "Tamil Nadu Shops and Establishments Act 1947, Section 46A\n\n"
            "46A. Compounding of offences.--An offence punishable under Section 45 or rules "
            "made under Section 49 may be compounded by the Commissioner of Labour or an "
            "authorised officer on payment of a specified sum, subject to the statutory ceiling. "
            "After compounding, no further proceeding is taken for that compounded offence. "
            "For a penalty dispute, ask for the written compounding or penalty basis and the "
            "authority that calculated it."
        ),
    },
    {
        "slug": "coimbatore-trade-license-2026",
        "title": "Coimbatore City Municipal Corporation Licensing of Offensive Trades",
        "source_url": CCMC_TRADE_LICENSE_SOURCE_URL,
        "source_type": "guideline",
        "origin": "coimbatore_city_municipal_corporation",
        "subject_area": "business_license",
        "anchor": "coimbatore-trade-license-2026/d-and-o-renewal-penalty",
        "section_no": "D&O",
        "section_title": "D&O trade license renewal and penalty",
        "manual_section_backfill": True,
        "text_is_verbatim": False,
        "text": (
            "Coimbatore City Municipal Corporation Licensing of Offensive Trades, D&O trade "
            "license renewal and penalty\n\n"
            "The Coimbatore Corporation public licensing page says Dangerous and Offensive "
            "Trades should renew licences before 45 days of the commencement of the trade "
            "financial year, i.e. 1 April, and renew every financial year. It states that "
            "defaulters should pay an extra 25 percent of the licence fee as penalty. The "
            "page also states the ordinary D&O process: application at zonal offices, scrutiny, "
            "Sanitary Inspector remarks, Zonal Sanitary Officer route, Assistant Commissioner, "
            "and issue of recommended trade licences. It lists timing as 7 days for application "
            "processing, 30 days for intimation for fee remittance, and 45 days for issue of "
            "licence. For a pending renewal, ask for application number, inspection remarks, "
            "fee intimation, penalty calculation, and the written authority for delay or demand."
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
        for spec in TAMIL_NADU_SHOP_CHUNKS:
            inserted += await _upsert_extra_section_chunk(conn, spec)
        print(f"tamil nadu/coimbatore shop sources: inserted/updated {inserted} section chunks")
    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(main())
