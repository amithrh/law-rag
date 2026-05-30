#!/usr/bin/env python3
"""Add exact Income-tax 43B(h) and 2025 transition chunks missing locally.

The local Income-tax Act extraction is present, but the relevant 43B(h) clause
is not exposed as its own searchable section. This focused supplemental chunk
keeps MSME delayed-payment answers grounded in the official Income Tax
Department section page instead of relying on generic Contract Act retrieval.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
from pathlib import Path

import asyncpg

ROOT = Path(__file__).parent.parent
OFFICIAL_URL = "https://www.incometaxindia.gov.in/w/section-43b-41"
TRANSITION_URL = "https://www.incometax.gov.in/iec/foportal/help/all-topics/e-filing-services/objective-and-scope-new-act-faq"
DOC_ID = "income-tax-1961"
ANCHOR = "income-tax-1961/sec-43B-h@2024-04-01"
TRANSITION_DOC_ID = "income-tax-2025-transition-faq"
TRANSITION_ANCHOR = "income-tax-2025-transition-faq#repeal-savings"

SECTION_TEXT = """
Income-tax Act 1961, Section 43B. Certain deductions to be only on actual
payment.

43B. Notwithstanding anything contained in any other provision of this Act, a
deduction otherwise allowable under this Act in respect of --

(h) any sum payable by the assessee to a micro or small enterprise beyond the
time limit specified in section 15 of the Micro, Small and Medium Enterprises
Development Act, 2006 (27 of 2006),

shall be allowed (irrespective of the previous year in which the liability to
pay such sum was incurred by the assessee according to the method of accounting
regularly employed by him) only in computing the income referred to in section
28 of that previous year in which such sum is actually paid by him.

Explanation 4. For the purposes of this section, "micro enterprise" shall have
the meaning assigned to it in clause (h) of section 2 of the Micro, Small and
Medium Enterprises Development Act, 2006 (27 of 2006), and "small enterprise"
shall have the meaning assigned to it in clause (m) of section 2 of that Act.

Official source notes: clause (h) was inserted by Act No. 8 of 2023 with effect
from 1 April 2024.
""".strip()

TRANSITION_TEXT = """
Income Tax Department FAQ, Objective and scope of the Income Tax Act 2025.

The FAQ says the Income Tax Act, 2025 replaces the Income Tax Act, 1961 and
that the 1961 Act stands repealed on 01.04.2026, subject to transitional
provisions.

The FAQ also says repeal of the 1961 Act does not disturb anything relating to
tax years before April 1, 2026; pending proceedings and proceedings for any tax
year beginning before 1 April 2026 continue under the repealed Act.

For practical parallel operation, the FAQ says that effective 1 April 2026 the
1961 Act is repealed, but its provisions continue to govern all tax years
beginning before 1 April 2026, while advance tax payments for Tax Year 2026-27
commencing from June 2026 will be made in accordance with the new Act.
""".strip()


def _load_env() -> dict[str, str]:
    out: dict[str, str] = {}
    for line in (ROOT / ".env").read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        out[key.strip()] = value.strip().strip('"').strip("'")
    return out


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
        url_hash = hashlib.sha256(OFFICIAL_URL.encode()).hexdigest()
        source_id = await conn.fetchval(
            """
            INSERT INTO sources (source_type, origin, url, canonical_url_hash, metadata)
            VALUES ('bare_act', 'income-tax-department', $1, $2, $3)
            ON CONFLICT (canonical_url_hash) DO UPDATE
              SET source_type = EXCLUDED.source_type,
                  metadata = EXCLUDED.metadata
            RETURNING id
            """,
            OFFICIAL_URL,
            url_hash,
            json.dumps({"official_section_page": OFFICIAL_URL}),
        )
        doc_pk = await conn.fetchval("SELECT id FROM documents WHERE doc_id = $1", DOC_ID)
        if doc_pk is None:
            doc_pk = await conn.fetchval(
                """
                INSERT INTO documents (
                    source_id, doc_id, title, statute_short, statute_year,
                    subject_area, as_at, metadata
                )
                VALUES ($1, $2, 'Income-tax Act 1961', 'Income-tax Act', 1961,
                        'tax', DATE '2024-04-01', $3)
                RETURNING id
                """,
                source_id,
                DOC_ID,
                json.dumps({"source_url": OFFICIAL_URL}),
            )
        await conn.execute(
            """
            INSERT INTO chunks (
                document_id, source_type, subject_area, anchor, paragraph_no,
                token_count, text, chunk_strategy, as_at, metadata
            )
            VALUES ($1, 'bare_act', 'tax', $2, 1, $3, $4,
                    'supplemental_section', DATE '2024-04-01', $5)
            ON CONFLICT (document_id, anchor, as_at) DO UPDATE
              SET text = EXCLUDED.text,
                  token_count = EXCLUDED.token_count,
                  metadata = EXCLUDED.metadata
            """,
            doc_pk,
            ANCHOR,
            len(SECTION_TEXT.split()),
            SECTION_TEXT,
            json.dumps({"section_no": "43B", "source_url": OFFICIAL_URL}),
        )
        transition_hash = hashlib.sha256(TRANSITION_URL.encode()).hexdigest()
        transition_source_id = await conn.fetchval(
            """
            INSERT INTO sources (source_type, origin, url, canonical_url_hash, metadata)
            VALUES ('circular', 'income-tax-department', $1, $2, $3)
            ON CONFLICT (canonical_url_hash) DO UPDATE
              SET source_type = EXCLUDED.source_type,
                  metadata = EXCLUDED.metadata
            RETURNING id
            """,
            TRANSITION_URL,
            transition_hash,
            json.dumps({"official_faq": TRANSITION_URL, "retrieved_for": "Income Tax Act 2025 transition"}),
        )
        transition_doc_pk = await conn.fetchval("SELECT id FROM documents WHERE doc_id = $1", TRANSITION_DOC_ID)
        if transition_doc_pk is None:
            transition_doc_pk = await conn.fetchval(
                """
                INSERT INTO documents (source_id, doc_id, title, subject_area, as_at, metadata)
                VALUES ($1, $2, 'Income Tax Act 2025 transition FAQ', 'tax',
                        DATE '2026-04-01', $3)
                RETURNING id
                """,
                transition_source_id,
                TRANSITION_DOC_ID,
                json.dumps({"source_url": TRANSITION_URL, "authority": "Income Tax Department"}),
            )
        else:
            await conn.execute(
                """
                UPDATE documents
                SET source_id = $1,
                    title = 'Income Tax Act 2025 transition FAQ',
                    subject_area = 'tax',
                    as_at = DATE '2026-04-01',
                    metadata = $2
                WHERE id = $3
                """,
                transition_source_id,
                json.dumps({"source_url": TRANSITION_URL, "authority": "Income Tax Department"}),
                transition_doc_pk,
            )
        await conn.execute(
            """
            INSERT INTO chunks (
                document_id, source_type, subject_area, anchor, paragraph_no,
                token_count, text, chunk_strategy, as_at, metadata
            )
            VALUES ($1, 'circular', 'tax', $2, 1, $3, $4,
                    'official_faq', DATE '2026-04-01', $5)
            ON CONFLICT (document_id, anchor, as_at) DO UPDATE
              SET text = EXCLUDED.text,
                  token_count = EXCLUDED.token_count,
                  metadata = EXCLUDED.metadata
            """,
            transition_doc_pk,
            TRANSITION_ANCHOR,
            len(TRANSITION_TEXT.split()),
            TRANSITION_TEXT,
            json.dumps({"source_url": TRANSITION_URL, "topic": "repeal_and_savings"}),
        )
    finally:
        await conn.close()
    print(f"inserted/updated {ANCHOR} and {TRANSITION_ANCHOR}")


if __name__ == "__main__":
    asyncio.run(main())
