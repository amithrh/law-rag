#!/usr/bin/env python3
"""Backfill narrow official Gujarat municipal/shop sources.

These chunks cover high-frequency "municipality sealed my shop" prompts. They
come from public India Code/Gujarat Government PDFs and are intentionally
section-scoped so the product can cite primary authority instead of treating
RTI as the controlling sealing law.
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


GUJARAT_SHOPS_SOURCE_URL = "https://www.indiacode.nic.in/bitstream/123456789/15202/1/shops_estaact19.pdf"
GUJARAT_MUNICIPALITIES_SOURCE_URL = "https://www.indiacode.nic.in/bitstream/123456789/4664/1/municipalitiesact.pdf"
GUJARAT_PMC_SOURCE_URL = (
    "https://www.indiacode.nic.in/bitstream/123456789/4653/1/"
    "h-2002_the_guj_provincial_municipal_corporation_act.pdf"
)


GUJARAT_MUNICIPAL_SHOP_CHUNKS = [
    {
        "slug": "gujarat-shops-establishments-2019",
        "title": "Gujarat Shops and Establishments (Regulation of Employment and Conditions of Service) Act 2019",
        "source_url": GUJARAT_SHOPS_SOURCE_URL,
        "subject_area": "business_license",
        "anchor": "gujarat-shops-establishments-2019/sec-6",
        "section_no": "6",
        "section_title": "Registration of shops or establishments",
        "text": (
            "Gujarat Shops and Establishments (Regulation of Employment and Conditions of Service) Act 2019, Section 6\n\n"
            "6. Registration of shops or establishments.--Within sixty days from commencement of the Act "
            "or from the date on which a shop or establishment commences business, the employer must submit "
            "a prescribed registration application to the concerned Inspector with prescribed fees, "
            "self-declaration and self-certified documents. On receiving the application, documents and fees, "
            "the Inspector registers the shop or establishment in the register of establishments and issues "
            "a registration certificate within the prescribed time limit. The registration certificate must "
            "be produced whenever demanded by the Inspector, and remains in force until change in ownership "
            "or nature of business, when a fresh registration certificate is required."
        ),
    },
    {
        "slug": "gujarat-shops-establishments-2019",
        "title": "Gujarat Shops and Establishments (Regulation of Employment and Conditions of Service) Act 2019",
        "source_url": GUJARAT_SHOPS_SOURCE_URL,
        "subject_area": "business_license",
        "anchor": "gujarat-shops-establishments-2019/sec-8",
        "section_no": "8",
        "section_title": "Cancellation of registration of shop or establishment",
        "text": (
            "Gujarat Shops and Establishments (Regulation of Employment and Conditions of Service) Act 2019, Section 8\n\n"
            "8. Cancellation of registration of shop or establishment.--If it is found or brought to the "
            "Inspector's notice that registration of a shop or establishment was obtained by misrepresentation, "
            "suppression of material facts, false or forged documents, false declaration, or fraud, the Inspector "
            "must give the employer an opportunity of being heard before cancelling the registration and removing "
            "the shop or establishment from the register of establishments in the prescribed manner."
        ),
    },
    {
        "slug": "gujarat-shops-establishments-2019",
        "title": "Gujarat Shops and Establishments (Regulation of Employment and Conditions of Service) Act 2019",
        "source_url": GUJARAT_SHOPS_SOURCE_URL,
        "subject_area": "business_license",
        "anchor": "gujarat-shops-establishments-2019/sec-10",
        "section_no": "10",
        "section_title": "Notice for closure of business",
        "text": (
            "Gujarat Shops and Establishments (Regulation of Employment and Conditions of Service) Act 2019, Section 10\n\n"
            "10. Notice for closure of business.--The employer must inform the Inspector in the prescribed "
            "form and manner within thirty days from the closing of the business that the shop or establishment "
            "has been closed. On receiving the information and being satisfied about its correctness, the "
            "Inspector removes the shop or establishment from the register and cancels the registration "
            "certificate. If the Inspector does not receive information but is otherwise satisfied that the "
            "shop or establishment has closed, the Inspector may remove it from the register and cancel the certificate."
        ),
    },
    {
        "slug": "gujarat-municipalities-1963",
        "title": "Gujarat Municipalities Act 1963",
        "source_url": GUJARAT_MUNICIPALITIES_SOURCE_URL,
        "subject_area": "business_license",
        "anchor": "gujarat-municipalities-1963/sec-221",
        "section_no": "221",
        "section_title": "Regulation of certain trades",
        "text": (
            "Gujarat Municipalities Act 1963, Section 221\n\n"
            "221. Regulation of certain trades.--If the executive committee is satisfied that a building or "
            "place used for specified trades or business is, or is likely to become, a nuisance to the "
            "neighbourhood or dangerous to life, health or property, it may issue a written notice requiring "
            "the owner or occupier at once to discontinue the use, desist from the intended use, or use the "
            "building or place in the manner and after the structural alterations prescribed in the notice. "
            "After conviction for continuing such use, the Magistrate, on the executive committee's application, "
            "may order the place to be closed and appoint persons or take other steps to prevent such use. "
            "Where bye-laws prescribe licence conditions for such use, using the place without a licence, "
            "during suspension, or after withdrawal of the licence is punishable."
        ),
    },
    {
        "slug": "gujarat-municipalities-1963",
        "title": "Gujarat Municipalities Act 1963",
        "source_url": GUJARAT_MUNICIPALITIES_SOURCE_URL,
        "subject_area": "business_license",
        "anchor": "gujarat-municipalities-1963/sec-226",
        "section_no": "226",
        "section_title": "Service of notices",
        "text": (
            "Gujarat Municipalities Act 1963, Section 226\n\n"
            "226. Service of notices, etc.--The Act provides for service of notices and bills addressed to "
            "individuals, service of notices on owners or occupiers of buildings and lands, public and general "
            "notices, defective form not invalidating a notice, and execution of acts required to be done by "
            "a notice. For a shop-sealing or closure problem, the written notice/order and how it was served "
            "are therefore key procedural records to obtain and preserve."
        ),
    },
    {
        "slug": "gujarat-provincial-municipal-corporations-1949",
        "title": "Gujarat Provincial Municipal Corporations Act 1949",
        "source_url": GUJARAT_PMC_SOURCE_URL,
        "subject_area": "business_license",
        "anchor": "gujarat-provincial-municipal-corporations-1949/sec-376",
        "section_no": "376",
        "section_title": "Certain things and trades not to be carried on without licence",
        "text": (
            "Gujarat Provincial Municipal Corporations Act 1949, Section 376\n\n"
            "376. Certain things not to be kept, and certain trades and operations not to be carried on, without "
            "licence.--Except under and in conformity with the terms and conditions of a licence granted by "
            "the Commissioner, a person must not keep specified articles on premises or carry on specified "
            "trades or operations on premises. This includes trades or operations specified in rules, and any "
            "trade or operation which in the Commissioner's opinion is dangerous to life, health or property "
            "or likely to create a nuisance because of its nature, manner, or conditions. After written notice "
            "of the Commissioner's opinion, the person is deemed to know the trade or operation is dangerous "
            "or likely to create nuisance. The Commissioner may grant a licence with restrictions or conditions, "
            "withhold the licence, and enter or inspect licensed premises by day or night."
        ),
    },
    {
        "slug": "gujarat-provincial-municipal-corporations-1949",
        "title": "Gujarat Provincial Municipal Corporations Act 1949",
        "source_url": GUJARAT_PMC_SOURCE_URL,
        "subject_area": "business_license",
        "anchor": "gujarat-provincial-municipal-corporations-1949/sec-376A",
        "section_no": "376A",
        "section_title": "Power to stop use of premises where dangerous or nuisance",
        "text": (
            "Gujarat Provincial Municipal Corporations Act 1949, Section 376A\n\n"
            "376A. Power to stop use of premises where such use is dangerous or causes nuisance.--Where the "
            "Commissioner is of opinion that use of any premises for purposes specified in section 376(1) is "
            "dangerous to life, health or property or is causing a nuisance, and that the danger or nuisance "
            "should be immediately stopped, the Commissioner may require the owner or occupier to stop the "
            "danger or nuisance within the time specified in the requisition. If the owner or occupier fails "
            "to comply, the Commissioner may himself, or through a subordinate officer, cause such use to be stopped."
        ),
    },
    {
        "slug": "gujarat-provincial-municipal-corporations-1949",
        "title": "Gujarat Provincial Municipal Corporations Act 1949",
        "source_url": GUJARAT_PMC_SOURCE_URL,
        "subject_area": "business_license",
        "anchor": "gujarat-provincial-municipal-corporations-1949/sec-386",
        "section_no": "386",
        "section_title": "General provisions for licences and permits",
        "text": (
            "Gujarat Provincial Municipal Corporations Act 1949, Section 386\n\n"
            "386. General provisions regarding grant, suspension or revocation of licences and written "
            "permissions.--A licence or written permission must specify the period, restrictions and "
            "conditions, renewal date, and be signed by the Commissioner or empowered municipal officer. "
            "A licence or written permission may be suspended or revoked if obtained by misrepresentation "
            "or fraud, if restrictions or conditions are infringed or evaded, or if the holder is convicted "
            "of violating the Act, rules, by-laws or standing orders relating to that licence. When a licence "
            "is suspended, revoked, or expired, the holder is deemed without licence until cancellation of "
            "the suspension/revocation order or renewal."
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
        for spec in GUJARAT_MUNICIPAL_SHOP_CHUNKS:
            inserted += await _upsert_extra_section_chunk(conn, spec)
        print(f"gujarat municipal/shop sources: inserted/updated {inserted} section chunks")
    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(main())
