#!/usr/bin/env python3
"""Add Department of Publication adult name-change Gazette guidelines.

The family/name-change route needs an official procedure source for users who
ask whether a surname/name change after marriage requires Gazette publication.
This script downloads the official Department of Publication PDF and stores
focused chunks for the adult Gazette of India Part-IV process.
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
PDF_URL = (
    "https://cdnbbsr.s3waas.gov.in/s3ea6b2efbdd4255a9f1b3bbc6399b58f4/"
    "uploads/2023/06/202312082035285613.pdf"
)
DOC_ID = "deptpub-name-change-adult-guidelines"
TITLE = "Department of Publication Guidelines for Change of Name Adult Major"
AS_AT = "2023-12-08"
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
    if path.exists() and path.stat().st_size > 20_000:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        ["curl", "-sS", "-L", "--compressed", "--max-time", "60", "-o", str(path), PDF_URL],
        check=True,
    )
    if path.stat().st_size < 20_000:
        raise RuntimeError(f"downloaded PDF looks too small: {path.stat().st_size} bytes")


def _extract_text(path: Path) -> str:
    doc = pymupdf.open(path)
    try:
        text = "\n".join(page.get_text("text") for page in doc)
    finally:
        doc.close()
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    if "GUIDELINES FOR CHANGE OF NAME FOR ADULT" not in text:
        raise RuntimeError("Department of Publication name-change guideline marker missing")
    return text


def _slice(text: str, start: str, end: str | None = None) -> str:
    lower = text.lower()
    start_idx = lower.find(start.lower())
    if start_idx < 0:
        raise RuntimeError(f"could not find start marker: {start}")
    if end is None:
        end_idx = min(len(text), start_idx + 2200)
    else:
        end_idx = lower.find(end.lower(), start_idx)
        if end_idx < 0:
            raise RuntimeError(f"could not find end marker: {end}")
    return text[start_idx:end_idx].strip()


def _chunks(text: str) -> list[dict[str, str]]:
    return [
        {
            "anchor": f"{DOC_ID}#adult-required-documents",
            "text": _slice(
                text,
                "The following documents are required for publication of advertisement in the Gazette of India Part-IV",
                "A person attaining the age of 18 years",
            ),
        },
        {
            "anchor": f"{DOC_ID}#adult-formalities",
            "text": _slice(
                text,
                "A person attaining the age of 18 years",
                "For Indians living abroad",
            ),
        },
        {
            "anchor": f"{DOC_ID}#egazette-download-and-submission",
            "text": _slice(
                text,
                "to download his/her gazette from the website",
                "The documents once submitted",
            ),
        },
    ]


async def main() -> None:
    env = _load_env()
    pdf_path = ROOT / "data" / "raw" / "guidelines" / "deptpub_name_change_adult_guidelines.pdf"
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
        source_id = await conn.fetchval(
            """
            INSERT INTO sources (source_type, origin, url, canonical_url_hash, metadata)
            VALUES ('circular', 'department-of-publication', $1, $2, $3)
            ON CONFLICT (canonical_url_hash) DO UPDATE
              SET source_type = EXCLUDED.source_type,
                  metadata = EXCLUDED.metadata
            RETURNING id
            """,
            PDF_URL,
            url_hash,
            json.dumps({
                "pdf_local": str(pdf_path),
                "authority": "Department of Publication, Government of India",
                "topic": "Gazette of India Part-IV adult change of name",
            }),
        )
        doc_pk = await conn.fetchval("SELECT id FROM documents WHERE doc_id = $1", DOC_ID)
        if doc_pk is None:
            doc_pk = await conn.fetchval(
                """
                INSERT INTO documents (source_id, doc_id, title, subject_area, as_at, metadata)
                VALUES ($1, $2, $3, 'family', $4::date, $5)
                RETURNING id
                """,
                source_id,
                DOC_ID,
                TITLE,
                AS_AT_DATE,
                json.dumps({"source_url": PDF_URL, "authority": "Department of Publication"}),
            )
        else:
            await conn.execute(
                """
                UPDATE documents
                SET source_id = $1,
                    title = $2,
                    subject_area = 'family',
                    as_at = $3::date,
                    metadata = $4
                WHERE id = $5
                """,
                source_id,
                TITLE,
                AS_AT_DATE,
                json.dumps({"source_url": PDF_URL, "authority": "Department of Publication"}),
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
                VALUES ($1, 'circular', 'family', $2, $3, $4, $5,
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
                json.dumps({"source_url": PDF_URL}),
            )
            inserted += 1
    finally:
        await conn.close()
    print(f"inserted/updated {inserted} Department of Publication name-change chunks")


if __name__ == "__main__":
    asyncio.run(main())
