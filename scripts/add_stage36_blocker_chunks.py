#!/usr/bin/env python3
"""Add Stage36 official chunks for final100 blocker routes."""
from __future__ import annotations

import asyncio
import hashlib
import json
import sys
from pathlib import Path

import asyncpg

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from apps.api.config import get_settings  # noqa: E402
from apps.api.embeddings import (  # noqa: E402
    embedding_to_halfvec_literal,
    get_embedder,
    sparse_to_jsonb,
)


TRADE_MARKS_URL = (
    "https://upload.indiacode.nic.in/showfile?"
    "actid=AC_CEN_11_60_00004_199947_1517807323972"
    "&filename=a1999-47.pdf&type=actfile"
)
MAHARASHTRA_SHOPS_URL = (
    "https://mahakamgar.maharashtra.gov.in/Site/Upload/Pdf/"
    "Shops_Establishment_Regulation_of_Employment_Conditions_Eng_27.02.2018.pdf"
)
CONSTITUTION_URL = "https://www.legislative.gov.in/static/uploads/2025/07/359f70a69695affb9d72f8393102bd2e.pdf"
PROTECTION_CIVIL_RIGHTS_URL = "https://www.indiacode.nic.in/bitstream/123456789/1544/1/A1955-22Eng.pdf"
CONSUMER_JURISDICTION_RULES_URL = (
    "https://consumeraffairs.nic.in/sites/default/files/"
    "jurisdicton%20of%20Consumer%20Commissions.pdf"
)
SCST_POA_RULES_URL = "https://socialjustice.gov.in/writereaddata/UploadFile/POA%20Act.pdf"


CHUNKS = [
    {
        "slug": "constitution-india",
        "title": "Constitution of India",
        "year": 1950,
        "subject_area": "constitutional_law",
        "source_url": CONSTITUTION_URL,
        "origin": "legislative_department",
        "anchor": "constitution-india/sec-17",
        "section_no": "17",
        "section_title": "Abolition of Untouchability",
        "text": (
            "Constitution of India, Article 17\n\n"
            "Article 17 abolishes untouchability and forbids its practice in any form. "
            "It also makes enforcement of any disability arising out of untouchability "
            "an offence punishable in accordance with law. Use Article 17 for caste-linked "
            "temple entry, well or water access, and other untouchability-based disabilities."
        ),
    },
    {
        "slug": "protection-civil-rights-1955",
        "title": "Protection of Civil Rights Act 1955",
        "year": 1955,
        "subject_area": "civil_rights",
        "source_url": PROTECTION_CIVIL_RIGHTS_URL,
        "origin": "indiacode",
        "anchor": "protection-civil-rights-1955/sec-3",
        "section_no": "3",
        "section_title": "Punishment for enforcing religious disabilities",
        "text": (
            "Protection of Civil Rights Act 1955, Section 3\n\n"
            "Section 3 punishes preventing a person, on the ground of untouchability, from "
            "entering a place of public worship, worshipping or offering prayers there, or "
            "using waters of a sacred tank, well, spring, water-course or bathing ghat in the "
            "same manner and to the same extent as other persons of the same religion. Use "
            "Section 3 for temple-entry and religious well/water-access disabilities."
        ),
    },
    {
        "slug": "protection-civil-rights-1955",
        "title": "Protection of Civil Rights Act 1955",
        "year": 1955,
        "subject_area": "civil_rights",
        "source_url": PROTECTION_CIVIL_RIGHTS_URL,
        "origin": "indiacode",
        "anchor": "protection-civil-rights-1955/sec-4",
        "section_no": "4",
        "section_title": "Punishment for enforcing social disabilities",
        "text": (
            "Protection of Civil Rights Act 1955, Section 4\n\n"
            "Section 4 punishes enforcement of social disabilities on the ground of "
            "untouchability. It covers exclusion from shops, public restaurants, hotels, "
            "places of public entertainment, public places, public conveyances, public or "
            "charitable facilities, social or religious customs, processions, and other "
            "public-facing benefits or privileges. It should be checked with Section 3 and "
            "Article 17 where the facts involve temple entry, well/water access, or caste-based "
            "public exclusion."
        ),
    },
    {
        "slug": "protection-civil-rights-1955",
        "title": "Protection of Civil Rights Act 1955",
        "year": 1955,
        "subject_area": "civil_rights",
        "source_url": PROTECTION_CIVIL_RIGHTS_URL,
        "origin": "indiacode",
        "anchor": "protection-civil-rights-1955/sec-7",
        "section_no": "7",
        "section_title": "Punishment for other offences arising out of untouchability",
        "text": (
            "Protection of Civil Rights Act 1955, Section 7\n\n"
            "Section 7 punishes preventing a person from exercising a right accruing by reason "
            "of abolition of untouchability, molesting or obstructing a person in exercising "
            "that right, insulting or attempting to insult on the ground of untouchability, "
            "and encouraging or inciting untouchability. Use Section 7 when the facts involve "
            "pressure, obstruction, insult, or enforcement of an untouchability disability."
        ),
    },
    {
        "slug": "sc-st-poa-rules-1995",
        "title": "Scheduled Castes and Scheduled Tribes (Prevention of Atrocities) Rules 1995",
        "year": 1995,
        "subject_area": "criminal",
        "source_url": SCST_POA_RULES_URL,
        "origin": "socialjustice.gov.in",
        "anchor": "sc-st-poa-rules-1995/rule-7",
        "section_no": "7",
        "section_title": "Investigating Officer",
        "text": (
            "Scheduled Castes and Scheduled Tribes (Prevention of Atrocities) Rules 1995, Rule 7\n\n"
            "Rule 7 is the investigating-officer rule for offences under the SC/ST (Prevention of "
            "Atrocities) Act. It requires investigation by a police officer not below the rank of "
            "Deputy Superintendent of Police. The investigating officer is appointed by the State "
            "Government, Director General of Police, or Superintendent of Police after considering "
            "experience, ability, and capacity to investigate the case properly and quickly. The rule "
            "also directs completion of investigation on top priority and submission of the report to "
            "the Superintendent of Police for forwarding to the Director General of Police. Use Rule 7 "
            "when a user says an atrocity case has not been transferred to a DSP-rank officer or asks "
            "about the required rank of the investigating officer."
        ),
    },
    {
        "slug": "trade-marks-1999",
        "title": "Trade Marks Act 1999",
        "year": 1999,
        "subject_area": "intellectual_property",
        "source_url": TRADE_MARKS_URL,
        "origin": "indiacode",
        "anchor": "trade-marks-1999/sec-11",
        "section_no": "11",
        "section_title": "Relative grounds for refusal of registration",
        "text": (
            "Trade Marks Act 1999, Section 11\n\n"
            "Section 11 is the relative-grounds source for a trademark application opposed "
            "because another mark is identical or similar. It requires the Registrar to examine "
            "earlier marks, similarity of goods or services, likelihood of confusion, association "
            "with an earlier mark, and protection of well-known earlier marks. A trademark "
            "opposition based on confusing similarity should therefore be analysed under Section "
            "11 before treating the matter as a generic business dispute."
        ),
    },
    {
        "slug": "trade-marks-1999",
        "title": "Trade Marks Act 1999",
        "year": 1999,
        "subject_area": "intellectual_property",
        "source_url": TRADE_MARKS_URL,
        "origin": "indiacode",
        "anchor": "trade-marks-1999/sec-21",
        "section_no": "21",
        "section_title": "Opposition to registration",
        "text": (
            "Trade Marks Act 1999, Section 21\n\n"
            "Section 21 is the procedural source for opposition to trademark registration. "
            "It allows opposition after advertisement or re-advertisement of an application, "
            "requires the opponent to give notice to the Registrar within the statutory window, "
            "requires the applicant to file a counter-statement if it wants to contest the "
            "opposition, and lets the Registrar decide the matter after evidence and hearing. "
            "For a hearing on an opposed application, the Trade Marks Registry is the first forum."
        ),
    },
    {
        "slug": "trade-marks-1999",
        "title": "Trade Marks Act 1999",
        "year": 1999,
        "subject_area": "intellectual_property",
        "source_url": TRADE_MARKS_URL,
        "origin": "indiacode",
        "anchor": "trade-marks-1999/sec-29",
        "section_no": "29",
        "section_title": "Infringement of registered trade marks",
        "text": (
            "Trade Marks Act 1999, Section 29\n\n"
            "Section 29 is the infringement source for use of a registered trademark by another "
            "person in a way covered by the Act. It is relevant when the dispute is about market "
            "use of a mark, copying, confusing use, or enforcement after registration. Opposition "
            "to a pending application should still be separated from an infringement suit."
        ),
    },
    {
        "slug": "trade-marks-1999",
        "title": "Trade Marks Act 1999",
        "year": 1999,
        "subject_area": "intellectual_property",
        "source_url": TRADE_MARKS_URL,
        "origin": "indiacode",
        "anchor": "trade-marks-1999/sec-34",
        "section_no": "34",
        "section_title": "Saving for vested rights",
        "text": (
            "Trade Marks Act 1999, Section 34\n\n"
            "Section 34 is the prior-user source. It preserves the rights of a person who "
            "continuously used a trade mark from a date earlier than the registered proprietor's "
            "use or registration, and prevents the proprietor or registered user from interfering "
            "with that earlier use merely because the later registration exists. Use this section "
            "when a user says a competitor registered the brand first but they have already been "
            "using the brand for years."
        ),
    },
    {
        "slug": "trade-marks-1999",
        "title": "Trade Marks Act 1999",
        "year": 1999,
        "subject_area": "intellectual_property",
        "source_url": TRADE_MARKS_URL,
        "origin": "indiacode",
        "anchor": "trade-marks-1999/sec-57",
        "section_no": "57",
        "section_title": "Power to cancel or vary registration and to rectify the register",
        "text": (
            "Trade Marks Act 1999, Section 57\n\n"
            "Section 57 is the rectification source. It supports an application by a person "
            "aggrieved to cancel, vary, or rectify an entry on the trade marks register when a "
            "registration wrongly remains, is made without sufficient cause, or otherwise needs "
            "correction under the Act. Use this section when the remedy being checked is "
            "cancellation, rectification, or correction of a competitor's registered mark."
        ),
    },
    {
        "slug": "trade-marks-1999",
        "title": "Trade Marks Act 1999",
        "year": 1999,
        "subject_area": "intellectual_property",
        "source_url": TRADE_MARKS_URL,
        "origin": "indiacode",
        "anchor": "trade-marks-1999/sec-134",
        "section_no": "134",
        "section_title": "Suit for infringement, etc., to be instituted before District Court",
        "text": (
            "Trade Marks Act 1999, Section 134\n\n"
            "Section 134 is the forum source for suits for infringement of a registered trade "
            "mark, passing off, or related trade mark relief. It points the dispute to the "
            "District Court or competent civil/commercial court route for injunction, damages, "
            "or other court relief after the mark, use, marketplace listing, and confusion facts "
            "are organised."
        ),
    },
    {
        "slug": "consumer-jurisdiction-rules-2021",
        "title": "Consumer Protection (Jurisdiction of the District Commission, the State Commission and the National Commission) Rules 2021",
        "year": 2021,
        "subject_area": "consumer",
        "source_url": CONSUMER_JURISDICTION_RULES_URL,
        "origin": "department_of_consumer_affairs",
        "anchor": "consumer-jurisdiction-rules-2021/rule-2",
        "section_no": "2",
        "section_title": "Jurisdiction of District Commission",
        "text": (
            "Consumer Protection (Jurisdiction of the District Commission, the State Commission "
            "and the National Commission) Rules 2021, Rule 2\n\n"
            "Rule 2 gives District Commissions jurisdiction to entertain complaints where the "
            "value of the goods or services paid as consideration does not exceed fifty lakh "
            "rupees. Use Rule 2 for consumer complaints at or below Rs 50 lakh after checking "
            "the amount paid as consideration and the relief claimed."
        ),
    },
    {
        "slug": "consumer-jurisdiction-rules-2021",
        "title": "Consumer Protection (Jurisdiction of the District Commission, the State Commission and the National Commission) Rules 2021",
        "year": 2021,
        "subject_area": "consumer",
        "source_url": CONSUMER_JURISDICTION_RULES_URL,
        "origin": "department_of_consumer_affairs",
        "anchor": "consumer-jurisdiction-rules-2021/rule-3",
        "section_no": "3",
        "section_title": "Jurisdiction of State Commission",
        "text": (
            "Consumer Protection (Jurisdiction of the District Commission, the State Commission "
            "and the National Commission) Rules 2021, Rule 3\n\n"
            "Rule 3 gives State Commissions jurisdiction to entertain complaints where the "
            "value of the goods or services paid as consideration exceeds fifty lakh rupees "
            "but does not exceed two crore rupees. Use Rule 3 when the complaint value is above "
            "Rs 50 lakh and up to Rs 2 crore."
        ),
    },
    {
        "slug": "consumer-jurisdiction-rules-2021",
        "title": "Consumer Protection (Jurisdiction of the District Commission, the State Commission and the National Commission) Rules 2021",
        "year": 2021,
        "subject_area": "consumer",
        "source_url": CONSUMER_JURISDICTION_RULES_URL,
        "origin": "department_of_consumer_affairs",
        "anchor": "consumer-jurisdiction-rules-2021/rule-4",
        "section_no": "4",
        "section_title": "Jurisdiction of National Commission",
        "text": (
            "Consumer Protection (Jurisdiction of the District Commission, the State Commission "
            "and the National Commission) Rules 2021, Rule 4\n\n"
            "Rule 4 gives the National Commission jurisdiction to entertain complaints where "
            "the value of the goods or services paid as consideration exceeds two crore rupees. "
            "Use Rule 4 when the complaint value is above Rs 2 crore."
        ),
    },
    {
        "slug": "maharashtra-shops-establishments-2017",
        "title": "Maharashtra Shops and Establishments (Regulation of Employment and Conditions of Service) Act 2017",
        "year": 2017,
        "subject_area": "labour",
        "source_url": MAHARASHTRA_SHOPS_URL,
        "origin": "maharashtra_labour_department",
        "anchor": "maharashtra-shops-establishments-2017/sec-1",
        "section_no": "1",
        "section_title": "Short title, extent, application and commencement",
        "text": (
            "Maharashtra Shops and Establishments (Regulation of Employment and Conditions of "
            "Service) Act 2017, Section 1\n\n"
            "Section 1 applies the Act to Maharashtra. Except for Section 7, the Act applies to "
            "establishments employing ten or more workers; Section 7 applies to establishments "
            "with fewer than ten workers. A Maharashtra establishment with eleven workers is "
            "therefore within the Act's ordinary coverage unless a specific exemption applies."
        ),
    },
    {
        "slug": "maharashtra-shops-establishments-2017",
        "title": "Maharashtra Shops and Establishments (Regulation of Employment and Conditions of Service) Act 2017",
        "year": 2017,
        "subject_area": "labour",
        "source_url": MAHARASHTRA_SHOPS_URL,
        "origin": "maharashtra_labour_department",
        "anchor": "maharashtra-shops-establishments-2017/sec-15",
        "section_no": "15",
        "section_title": "Wages for overtime",
        "text": (
            "Maharashtra Shops and Establishments (Regulation of Employment and Conditions of "
            "Service) Act 2017, Section 15\n\n"
            "Section 15 is the overtime source. It gives a worker in an establishment overtime "
            "wages at twice the ordinary rate when work exceeds nine hours in a day or forty-eight "
            "hours in a week, and it caps total overtime hours at one hundred and twenty-five "
            "hours in a period of three months."
        ),
    },
    {
        "slug": "maharashtra-shops-establishments-2017",
        "title": "Maharashtra Shops and Establishments (Regulation of Employment and Conditions of Service) Act 2017",
        "year": 2017,
        "subject_area": "labour",
        "source_url": MAHARASHTRA_SHOPS_URL,
        "origin": "maharashtra_labour_department",
        "anchor": "maharashtra-shops-establishments-2017/sec-25",
        "section_no": "25",
        "section_title": "Maintenance of registers and records",
        "text": (
            "Maharashtra Shops and Establishments (Regulation of Employment and Conditions of "
            "Service) Act 2017, Section 25\n\n"
            "Section 25 requires every employer to maintain prescribed registers and records, "
            "allows records to be kept electronically or manually, requires signed hard copies "
            "to be submitted on inspection if demanded, and requires the employer or manager to "
            "produce registers, records and notices for inspection by the Chief Facilitator or "
            "Facilitator."
        ),
    },
    {
        "slug": "maharashtra-shops-establishments-2017",
        "title": "Maharashtra Shops and Establishments (Regulation of Employment and Conditions of Service) Act 2017",
        "year": 2017,
        "subject_area": "labour",
        "source_url": MAHARASHTRA_SHOPS_URL,
        "origin": "maharashtra_labour_department",
        "anchor": "maharashtra-shops-establishments-2017/sec-28",
        "section_no": "28",
        "section_title": "Appointment and powers of Facilitators",
        "text": (
            "Maharashtra Shops and Establishments (Regulation of Employment and Conditions of "
            "Service) Act 2017, Section 28\n\n"
            "Section 28 authorises appointment of Chief Facilitators and Facilitators. It allows "
            "inspection of establishments, examination of premises and prescribed records, taking "
            "evidence, requiring information, and searching, seizing or copying wage records, "
            "registers or notices relevant to an offence under the Act."
        ),
    },
    {
        "slug": "maharashtra-shops-establishments-2017",
        "title": "Maharashtra Shops and Establishments (Regulation of Employment and Conditions of Service) Act 2017",
        "year": 2017,
        "subject_area": "labour",
        "source_url": MAHARASHTRA_SHOPS_URL,
        "origin": "maharashtra_labour_department",
        "anchor": "maharashtra-shops-establishments-2017/sec-31",
        "section_no": "31",
        "section_title": "Penalty for obstruction or refusal to provide register",
        "text": (
            "Maharashtra Shops and Establishments (Regulation of Employment and Conditions of "
            "Service) Act 2017, Section 31\n\n"
            "Section 31 concerns obstruction of a Facilitator and refusal to produce registers "
            "or other documents kept under the Act or rules. It is the compliance-risk source "
            "when an employer has not produced an overtime or establishment register during a "
            "labour department inspection."
        ),
    },
]


_EMBED_CACHE: dict[str, tuple[str, str]] = {}


def _embed(text: str) -> tuple[str, str]:
    cached = _EMBED_CACHE.get(text)
    if cached is not None:
        return cached
    dense, sparse = get_embedder().encode_with_sparse([text])
    out = (embedding_to_halfvec_literal(dense[0]), sparse_to_jsonb(sparse[0]))
    _EMBED_CACHE[text] = out
    return out


async def _upsert_chunk(conn: asyncpg.Connection, spec: dict) -> None:
    source_hash = hashlib.sha256(spec["source_url"].encode()).hexdigest()
    source_id = await conn.fetchval(
        """
        INSERT INTO sources (source_type, origin, url, canonical_url_hash, metadata)
        VALUES ('bare_act', $1, $2, $3, $4)
        ON CONFLICT (canonical_url_hash) DO UPDATE
          SET source_type = EXCLUDED.source_type,
              origin = EXCLUDED.origin,
              metadata = EXCLUDED.metadata
        RETURNING id
        """,
        spec["origin"],
        spec["source_url"],
        source_hash,
        json.dumps({"slug": spec["slug"], "stage36_backfill": True}),
    )
    doc_id = await conn.fetchval("SELECT id FROM documents WHERE doc_id = $1", spec["slug"])
    if doc_id is None:
        doc_id = await conn.fetchval(
            """
            INSERT INTO documents (source_id, doc_id, title, statute_short,
                                   statute_year, subject_area, metadata)
            VALUES ($1, $2, $3, $3, $4, $5, $6)
            RETURNING id
            """,
            source_id,
            spec["slug"],
            spec["title"],
            spec["year"],
            spec["subject_area"],
            json.dumps({"source_url": spec["source_url"], "stage36_backfill": True}),
        )
    else:
        await conn.execute(
            """
            UPDATE documents
            SET source_id = COALESCE(source_id, $1),
                title = $2,
                statute_short = COALESCE(statute_short, $2),
                statute_year = COALESCE(statute_year, $3),
                subject_area = COALESCE(subject_area, $4),
                metadata = COALESCE(metadata, '{}'::jsonb) || $5::jsonb
            WHERE id = $6
            """,
            source_id,
            spec["title"],
            spec["year"],
            spec["subject_area"],
            json.dumps({"source_url": spec["source_url"], "stage36_backfill": True}),
            doc_id,
        )

    embedding, embedding_sparse = _embed(spec["text"])
    metadata = {
        "section_no": spec["section_no"],
        "section_title": spec["section_title"],
        "stage36_backfill": True,
        "source_url": spec["source_url"],
    }
    existing_chunk_id = await conn.fetchval(
        """
        SELECT id
        FROM chunks
        WHERE document_id = $1
          AND anchor = $2
          AND as_at IS NULL
        ORDER BY id
        LIMIT 1
        """,
        doc_id,
        spec["anchor"],
    )
    if existing_chunk_id:
        await conn.execute(
            """
            UPDATE chunks
            SET source_type = 'bare_act',
                subject_area = $1,
                paragraph_no = NULL,
                token_count = $2,
                text = $3,
                embedding = $4::halfvec,
                embedding_sparse = $5::jsonb,
                chunk_strategy = 'section',
                metadata = $6
            WHERE id = $7
            """,
            spec["subject_area"],
            len(spec["text"].split()),
            spec["text"],
            embedding,
            embedding_sparse,
            json.dumps(metadata),
            existing_chunk_id,
        )
        return

    await conn.execute(
        """
        INSERT INTO chunks (
            document_id, source_type, subject_area, anchor, paragraph_no,
            token_count, text, embedding, embedding_sparse, chunk_strategy,
            as_at, metadata
        )
        VALUES ($1, 'bare_act', $2, $3, NULL, $4, $5, $6::halfvec, $7::jsonb,
                'section', NULL, $8)
        """,
        doc_id,
        spec["subject_area"],
        spec["anchor"],
        len(spec["text"].split()),
        spec["text"],
        embedding,
        embedding_sparse,
        json.dumps(metadata),
    )


async def main() -> None:
    conn = await asyncpg.connect(get_settings().resolved_database_url_host_side)
    try:
        for spec in CHUNKS:
            await _upsert_chunk(conn, spec)
            print(f"upserted {spec['anchor']}")
    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(main())
