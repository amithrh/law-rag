#!/usr/bin/env python3
"""Add Motor Vehicle Aggregator Guidelines 2020 focused chunks.

The cab-aggregator route needs an official guideline source for driver
deactivation, ratings, fare share, and app-grievance questions. MoRTH's current
site serves the PDF through a JS shell in this environment, so this uses the
Kerala Motor Vehicle Department mirror of the same central guideline PDF.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import re
import subprocess
from datetime import date
from pathlib import Path

import asyncpg
import pymupdf

ROOT = Path(__file__).parent.parent
PDF_URL = "https://mvd.kerala.gov.in/sites/default/files/Downloads/DOC-20250727-WA0228..pdf"
MORTH_URL = "https://morth.nic.in/sites/default/files/notifications_document/Motor%20Vehicle%20Aggregators27112020150046.pdf"
DOC_ID = "motor-vehicle-aggregator-guidelines-2020"
TITLE = "Motor Vehicle Aggregator Guidelines 2020"
AS_AT = "2020-11-27"
AS_AT_DATE = date.fromisoformat(AS_AT)


def _load_env() -> dict[str, str]:
    out: dict[str, str] = {}
    for line in (ROOT / ".env").read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        out[key.strip()] = value.strip().strip('"').strip("'")
    return out


def _fetch_pdf(path: Path) -> None:
    if path.exists() and path.stat().st_size > 500_000:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        ["curl", "-sS", "-L", "--compressed", "--max-time", "60", "-o", str(path), PDF_URL],
        check=True,
    )
    if path.stat().st_size < 500_000:
        raise RuntimeError(f"downloaded guideline PDF looks too small: {path.stat().st_size} bytes")


def _extract_text(path: Path) -> str:
    doc = pymupdf.open(path)
    try:
        text = "\n".join(page.get_text("text") for page in doc)
    finally:
        doc.close()
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    if "Motor Vehicle Aggregator Guidelines" not in text and "Motor vehicle Aggregator Guidelines" not in text:
        raise RuntimeError("Motor Vehicle Aggregator guideline marker missing")
    return text


def _slice(text: str, start: str, end: str | None = None, max_chars: int = 2200) -> str:
    lower = text.lower()
    start_idx = lower.find(start.lower())
    if start_idx < 0:
        raise RuntimeError(f"could not find start marker: {start}")
    if end is None:
        end_idx = min(len(text), start_idx + max_chars)
    else:
        end_idx = lower.find(end.lower(), start_idx)
        if end_idx < 0:
            end_idx = min(len(text), start_idx + max_chars)
    return text[start_idx:end_idx].strip()


def _chunks(text: str) -> list[dict[str, str]]:
    return [
        {
            "anchor": f"{DOC_ID}#driver-service-contract",
            "text": _slice(
                text,
                "Execution of a vatid enforceabte Service Provider Contract",
                "The Aggregator shatt ensure comptiance with the fottowing conditions",
            ),
        },
        {
            "anchor": f"{DOC_ID}#app-transparency-grievance",
            "text": _slice(
                text,
                "Ensuring transparency in its. operations",
                "12. Non-discrimination policy",
                max_chars=3200,
            ),
        },
        {
            "anchor": f"{DOC_ID}#non-discrimination-driver-fare",
            "text": _slice(
                text,
                "12. Non-discrimination policy to be followed by the Aggregator",
                "15. Aggregation of non-transport",
                max_chars=3000,
            ),
        },
    ]


async def main() -> None:
    env = _load_env()
    pdf_path = ROOT / "data" / "raw" / "guidelines" / "mv_aggregator_guidelines_2020.pdf"
    _fetch_pdf(pdf_path)
    text = _extract_text(pdf_path)
    chunks = _chunks(text)

    conn = await asyncpg.connect(
        host="localhost",
        port=int(env["POSTGRES_HOST_PORT"]),
        database=env["POSTGRES_DB"],
        user=env["POSTGRES_USER"],
        password=env["POSTGRES_PASSWORD"],
    )
    try:
        url_hash = hashlib.sha256(PDF_URL.encode()).hexdigest()
        metadata = json.dumps({
            "pdf_local": str(pdf_path),
            "authority": "Ministry of Road Transport and Highways",
            "mirror": "Kerala Motor Vehicle Department",
            "morth_original_url": MORTH_URL,
        })
        source_id = await conn.fetchval(
            """
            INSERT INTO sources (source_type, origin, url, canonical_url_hash, metadata)
            VALUES ('guideline', 'kerala-mvd-morth-mirror', $1, $2, $3)
            ON CONFLICT (canonical_url_hash) DO UPDATE
              SET source_type = EXCLUDED.source_type,
                  metadata = EXCLUDED.metadata
            RETURNING id
            """,
            PDF_URL,
            url_hash,
            metadata,
        )
        doc_pk = await conn.fetchval("SELECT id FROM documents WHERE doc_id = $1", DOC_ID)
        doc_metadata = json.dumps({
            "source_url": PDF_URL,
            "morth_original_url": MORTH_URL,
            "authority": "Ministry of Road Transport and Highways",
        })
        if doc_pk is None:
            doc_pk = await conn.fetchval(
                """
                INSERT INTO documents (source_id, doc_id, title, subject_area, as_at, metadata)
                VALUES ($1, $2, $3, 'transport', $4::date, $5)
                RETURNING id
                """,
                source_id,
                DOC_ID,
                TITLE,
                AS_AT_DATE,
                doc_metadata,
            )
        else:
            await conn.execute(
                """
                UPDATE documents
                SET source_id = $1,
                    title = $2,
                    subject_area = 'transport',
                    as_at = $3::date,
                    metadata = $4
                WHERE id = $5
                """,
                source_id,
                TITLE,
                AS_AT_DATE,
                doc_metadata,
                doc_pk,
            )

        inserted = 0
        for i, chunk in enumerate(chunks, start=1):
            await conn.execute(
                """
                INSERT INTO chunks (
                    document_id, source_type, subject_area, anchor, paragraph_no,
                    token_count, text, chunk_strategy, as_at, metadata
                )
                VALUES ($1, 'guideline', 'transport', $2, $3, $4, $5,
                        'official_guideline', $6::date, $7)
                ON CONFLICT (document_id, anchor, as_at) DO UPDATE
                  SET text = EXCLUDED.text,
                      token_count = EXCLUDED.token_count,
                      metadata = EXCLUDED.metadata
                """,
                doc_pk,
                chunk["anchor"],
                i,
                len(chunk["text"].split()),
                chunk["text"],
                AS_AT_DATE,
                json.dumps({"source_url": PDF_URL, "morth_original_url": MORTH_URL}),
            )
            inserted += 1
    finally:
        await conn.close()
    print(f"inserted/updated {inserted} Motor Vehicle Aggregator Guidelines chunks")


if __name__ == "__main__":
    asyncio.run(main())
