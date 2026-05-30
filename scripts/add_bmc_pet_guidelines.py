#!/usr/bin/env python3
"""Add BMC/AWBI-aligned pet and housing-society guidelines as a circular.

The consumer route was answering housing-society pet-fine prompts from generic
consumer-law sections because the local corpus had no pet/RWA/AOA authority.
This script ingests the text-readable BMC guideline PDF and keeps only focused
chunks needed for pet-owner/RWA questions.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import re
import subprocess
from pathlib import Path

import asyncpg
import pymupdf

ROOT = Path(__file__).parent.parent
PDF_URL = (
    "https://portal.mcgm.gov.in/irj/go/km/docs/documents/MCGM%20Department%20List/"
    "Veterinary%20Health%20Dept/BMC%20Guidelines%20with%20respect%20to%20pet%20dogs"
    "%20and%20street%20dogs%2C%20animal%20caretakers%20and%20feeders%2C%20RWAs%20%20"
    "and%20AOAs%2C%20Public%20Institutions.pdf"
)
DOC_ID = "bmc-pet-dog-guidelines"
TITLE = (
    "BMC Guidelines with respect to Pet & Street dogs, Community Animal Feeder/"
    "Care giver, RWAs and AOAs"
)


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
    if path.exists() and path.stat().st_size > 100_000:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        ["curl", "-sS", "-L", "--compressed", "--max-time", "60", "-o", str(path), PDF_URL],
        check=True,
    )
    if path.stat().st_size < 100_000:
        raise RuntimeError(f"downloaded PDF looks too small: {path.stat().st_size} bytes")


def _extract_text(path: Path) -> str:
    doc = pymupdf.open(path)
    try:
        text = "\n".join(page.get_text("text") for page in doc)
    finally:
        doc.close()
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    if len(text) < 5_000:
        raise RuntimeError("BMC guideline PDF extraction produced too little text")
    return text


def _slice(text: str, start: str, end: str | None = None, *, pad: int = 0) -> str:
    lower = text.lower()
    start_idx = lower.find(start.lower())
    if start_idx < 0:
        raise RuntimeError(f"could not find start marker: {start}")
    if end is None:
        end_idx = min(len(text), start_idx + 2200 + pad)
    else:
        end_idx = lower.find(end.lower(), start_idx)
        if end_idx < 0:
            raise RuntimeError(f"could not find end marker: {end}")
    return text[start_idx:end_idx].strip()


def _chunks(text: str) -> list[dict[str, str]]:
    return [
        {
            "anchor": f"{DOC_ID}#pet-dog-residents",
            "text": _slice(
                text,
                "I) WITH RESPECT TO PET DOGS & PET OWNING RESIDENTS:-",
                "II) WITH RESPECT TO STREET DOGS:-",
            ),
        },
        {
            "anchor": f"{DOC_ID}#housing-society-pet-bylaws",
            "text": _slice(
                text,
                "It is illegal for a housing society to pass pet bye laws that disallow pets.",
                "For any kind of queries / information required",
            ),
        },
        {
            "anchor": f"{DOC_ID}#pet-owner-license-and-rwa",
            "text": _slice(
                text,
                "It is mandatory for Pet Owners to abide by the terms and conditions of the BMC",
                "Pet owners can purchase a pedigree dog",
            ),
        },
    ]


async def main() -> None:
    env = _load_env()
    pdf_path = ROOT / "data" / "raw" / "guidelines" / "bmc_pet_guidelines.pdf"
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
            VALUES ('circular', 'mcgm', $1, $2, $3)
            ON CONFLICT (canonical_url_hash) DO UPDATE
              SET source_type = EXCLUDED.source_type,
                  metadata = EXCLUDED.metadata
            RETURNING id
            """,
            PDF_URL,
            url_hash,
            json.dumps({
                "pdf_local": str(pdf_path),
                "basis": "AWBI-aligned BMC pet guidelines",
                "jurisdiction": "Brihanmumbai / Mumbai municipal limits",
            }),
        )
        doc_pk = await conn.fetchval("SELECT id FROM documents WHERE doc_id = $1", DOC_ID)
        if doc_pk is None:
            doc_pk = await conn.fetchval(
                """
                INSERT INTO documents (source_id, doc_id, title, subject_area, metadata)
                VALUES ($1, $2, $3, 'consumer', $4)
                RETURNING id
                """,
                source_id,
                DOC_ID,
                TITLE,
                json.dumps({"source_url": PDF_URL, "authority": "Brihanmumbai Municipal Corporation"}),
            )
        else:
            await conn.execute(
                """
                UPDATE documents
                SET source_id = $1,
                    title = $2,
                    subject_area = 'consumer',
                    metadata = $3
                WHERE id = $4
                """,
                source_id,
                TITLE,
                json.dumps({
                    "source_url": PDF_URL,
                    "authority": "Brihanmumbai Municipal Corporation",
                    "jurisdiction": "Brihanmumbai / Mumbai municipal limits",
                }),
                doc_pk,
            )
        inserted = 0
        for i, chunk in enumerate(chunks, start=1):
            await conn.execute(
                """
                INSERT INTO chunks (
                    document_id, source_type, subject_area, anchor, paragraph_no,
                    token_count, text, chunk_strategy, metadata
                )
                VALUES ($1, 'circular', 'consumer', $2, $3, $4, $5, 'full_circular', $6)
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
                json.dumps({"source_url": PDF_URL}),
            )
            inserted += 1
    finally:
        await conn.close()
    print(f"inserted/updated {inserted} BMC pet guideline chunks")


if __name__ == "__main__":
    asyncio.run(main())
