#!/usr/bin/env python3
"""Backfill narrow Customs Act sections for import/export procedure routes."""
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


CUSTOMS_ACT_URL = (
    "https://www.indiacode.nic.in/bitstream/123456789/15359/1/"
    "the_customs_act%2C_1962.pdf"
)


CUSTOMS_ACT_CHUNKS = [
    {
        "slug": "customs-1962",
        "title": "Customs Act 1962",
        "source_url": CUSTOMS_ACT_URL,
        "origin": "indiacode",
        "subject_area": "tax",
        "anchor": "customs-1962/sec-14",
        "section_no": "14",
        "section_title": "Valuation of goods",
        "text_is_verbatim": False,
        "text": (
            "Customs Act 1962, Section 14\n\n"
            "Section 14 is the valuation source for imported and export goods. "
            "It directs valuation by reference to transaction value, the price "
            "actually paid or payable for the goods when sold for export to or "
            "from India, subject to statutory conditions and valuation rules. "
            "Use this source for SVB, declared-value, related-party, invoice-value, "
            "and customs valuation disputes before deciding the duty or appeal route."
        ),
    },
    {
        "slug": "customs-1962",
        "title": "Customs Act 1962",
        "source_url": CUSTOMS_ACT_URL,
        "origin": "indiacode",
        "subject_area": "tax",
        "anchor": "customs-1962/sec-17",
        "section_no": "17",
        "section_title": "Assessment of duty",
        "text_is_verbatim": False,
        "text": (
            "Customs Act 1962, Section 17\n\n"
            "Section 17 is the assessment source for customs duty. It covers "
            "self-assessment by the importer or exporter, verification by the "
            "proper officer, reassessment where the self-assessment is not correct, "
            "and the assessment/reassessment record. Use this source for bill-of-entry, "
            "classification, reclassification, assessment, and higher-duty disputes."
        ),
    },
    {
        "slug": "customs-1962",
        "title": "Customs Act 1962",
        "source_url": CUSTOMS_ACT_URL,
        "origin": "indiacode",
        "subject_area": "tax",
        "anchor": "customs-1962/sec-27",
        "section_no": "27",
        "section_title": "Claim for refund of duty",
        "text_is_verbatim": False,
        "text": (
            "Customs Act 1962, Section 27\n\n"
            "Section 27 is the refund-claim source for customs duty and interest. "
            "It is relevant where a person seeks refund of duty, interest, or excess "
            "payment and must file the claim with supporting evidence and the order "
            "or payment record. Use this source for refund or rejected-refund questions, "
            "including duty refund linked to import/export records."
        ),
    },
    {
        "slug": "customs-1962",
        "title": "Customs Act 1962",
        "source_url": CUSTOMS_ACT_URL,
        "origin": "indiacode",
        "subject_area": "tax",
        "anchor": "customs-1962/sec-28",
        "section_no": "28",
        "section_title": "Recovery of duties not levied or short-levied",
        "text_is_verbatim": False,
        "text": (
            "Customs Act 1962, Section 28\n\n"
            "Section 28 is the duty-demand and recovery source where customs duty "
            "has not been levied, not paid, short-levied, short-paid, or erroneously "
            "refunded. It is relevant to show-cause notices, differential-duty demands, "
            "misdeclaration-linked demand, reclassification demand, and adjudication "
            "papers after assessment."
        ),
    },
    {
        "slug": "customs-1962",
        "title": "Customs Act 1962",
        "source_url": CUSTOMS_ACT_URL,
        "origin": "indiacode",
        "subject_area": "tax",
        "anchor": "customs-1962/sec-75",
        "section_no": "75",
        "section_title": "Drawback on imported materials used in exported goods",
        "text_is_verbatim": False,
        "text": (
            "Customs Act 1962, Section 75\n\n"
            "Section 75 is the drawback source for imported materials used in the "
            "manufacture, processing, or operation of goods that are exported. It "
            "supports checking drawback entitlement, shipping-bill/export records, "
            "drawback claim papers, and rejection reasons before choosing refund, "
            "rectification, or customs appeal."
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
        for spec in CUSTOMS_ACT_CHUNKS:
            count = await _upsert_extra_section_chunk(conn, spec)
            print(f"{spec['slug']}: inserted/updated {count} chunk at {spec['anchor']}")
    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(main())
