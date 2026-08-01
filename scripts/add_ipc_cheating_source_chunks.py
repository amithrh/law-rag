#!/usr/bin/env python3
"""Add official IPC cheating sections needed for old/new criminal-law routing.

IndiaCode has a usable official PDF for the Indian Penal Code, 1860, but the
full bare Act is not present in the local corpus. This script idempotently adds
the two sections needed by common IPC 420/default-bail and fraud queries, while
leaving full IPC ingestion as a separate corpus task.
"""
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


IPC_SOURCE_URL = (
    "https://www.indiacode.nic.in/bitstream/123456789/4219/1/"
    "THE-INDIAN-PENAL-CODE-1860.pdf"
)


CHUNKS = [
    {
        "anchor": "ipc-1860/sec-415",
        "section_no": "415",
        "section_title": "Cheating",
        "text": (
            "Indian Penal Code 1860, Section 415\n\n"
            "Section 415 defines cheating. Whoever, by deceiving any person, "
            "fraudulently or dishonestly induces the person so deceived to "
            "deliver any property to any person, or to consent that any person "
            "shall retain any property, or intentionally induces the person so "
            "deceived to do or omit to do anything which he would not do or "
            "omit if he were not so deceived, and which act or omission causes "
            "or is likely to cause damage or harm to that person in body, mind, "
            "reputation or property, is said to cheat."
        ),
    },
    {
        "anchor": "ipc-1860/sec-420",
        "section_no": "420",
        "section_title": "Cheating and dishonestly inducing delivery of property",
        "text": (
            "Indian Penal Code 1860, Section 420\n\n"
            "Section 420 covers cheating and dishonestly inducing delivery of "
            "property. Whoever cheats and thereby dishonestly induces the "
            "person deceived to deliver any property to any person, or to make, "
            "alter or destroy the whole or any part of a valuable security, or "
            "anything which is signed or sealed and capable of being converted "
            "into a valuable security, shall be punished with imprisonment of "
            "either description for a term which may extend to seven years, and "
            "shall also be liable to fine."
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


async def _upsert_chunk(conn: asyncpg.Connection, source_id: int, spec: dict) -> None:
    dense, sparse = _embed(spec["text"])
    doc_pk = await conn.fetchval("SELECT id FROM documents WHERE doc_id = 'ipc-1860'")
    doc_metadata = {
        "source_url": IPC_SOURCE_URL,
        "manual_section_backfill": True,
        "coverage_note": "partial official IPC source for common cheating/420 queries",
    }
    if doc_pk is None:
        doc_pk = await conn.fetchval(
            """
            INSERT INTO documents (
                source_id, doc_id, title, statute_short, statute_year,
                subject_area, as_at, metadata, provenance_verified
            )
            VALUES (
                $1, 'ipc-1860', 'Indian Penal Code 1860',
                'Indian Penal Code 1860', 1860, 'criminal',
                DATE '1860-10-06', $2, false
            )
            RETURNING id
            """,
            source_id,
            json.dumps(doc_metadata),
        )
    else:
        await conn.execute(
            """
            UPDATE documents
            SET source_id = $1,
                title = 'Indian Penal Code 1860',
                statute_short = 'Indian Penal Code 1860',
                statute_year = 1860,
                subject_area = 'criminal',
                as_at = DATE '1860-10-06',
                metadata = COALESCE(metadata, '{}'::jsonb) || $2::jsonb,
                -- This is a partial, manually reconstructed backfill. It is
                -- useful for offline repair work but is not a provenance pass.
                provenance_verified = false
            WHERE id = $3
            """,
            source_id,
            json.dumps(doc_metadata),
            doc_pk,
        )

    metadata = {
        "section_no": spec["section_no"],
        "section_title": spec["section_title"],
        "manual_section_backfill": True,
        "source_url": IPC_SOURCE_URL,
    }
    existing_chunk_id = await conn.fetchval(
        """
        SELECT id
        FROM chunks
        WHERE document_id = $1 AND anchor = $2 AND as_at = DATE '1860-10-06'
        ORDER BY id
        LIMIT 1
        """,
        doc_pk,
        spec["anchor"],
    )
    if existing_chunk_id:
        await conn.execute(
            """
            UPDATE chunks
            SET source_type = 'bare_act',
                subject_area = 'criminal',
                paragraph_no = NULL,
                token_count = $1,
                text = $2,
                embedding = $3::halfvec,
                embedding_sparse = $4::jsonb,
                chunk_strategy = 'section',
                metadata = $5,
                quarantined = false,
                provenance_verified = false,
                provenance_verified_at = NULL
            WHERE id = $6
            """,
            len(spec["text"].split()),
            spec["text"],
            dense,
            sparse,
            json.dumps(metadata),
            existing_chunk_id,
        )
        return

    await conn.execute(
        """
        INSERT INTO chunks (
            document_id, source_type, subject_area, anchor, paragraph_no,
            token_count, text, embedding, embedding_sparse, chunk_strategy,
            as_at, metadata, quarantined, provenance_verified
        )
        VALUES (
            $1, 'bare_act', 'criminal', $2, NULL, $3, $4, $5::halfvec,
            $6::jsonb, 'section', DATE '1860-10-06', $7, false, false
        )
        """,
        doc_pk,
        spec["anchor"],
        len(spec["text"].split()),
        spec["text"],
        dense,
        sparse,
        json.dumps(metadata),
    )


async def main() -> None:
    settings = get_settings()
    conn = await asyncpg.connect(settings.resolved_database_url_host_side)
    try:
        source_hash = hashlib.sha256(IPC_SOURCE_URL.encode()).hexdigest()
        source_id = await conn.fetchval(
            """
            INSERT INTO sources (
                source_type, origin, url, canonical_url_hash, metadata,
                provenance_tier
            )
            VALUES ('bare_act', 'indiacode', $1, $2, $3, 1)
            ON CONFLICT (canonical_url_hash) DO UPDATE
              SET source_type = EXCLUDED.source_type,
                  origin = EXCLUDED.origin,
                  metadata = EXCLUDED.metadata,
                  provenance_tier = EXCLUDED.provenance_tier
            RETURNING id
            """,
            IPC_SOURCE_URL,
            source_hash,
            json.dumps({"slug": "ipc-1860", "manual_section_backfill": True}),
        )
        for spec in CHUNKS:
            await _upsert_chunk(conn, source_id, spec)
        count = await conn.fetchval(
            "SELECT count(*) FROM chunks c JOIN documents d ON d.id = c.document_id WHERE d.doc_id = 'ipc-1860'"
        )
        print(f"ipc-1860: upserted {len(CHUNKS)} official chunks; document now has {count} chunks")
    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(main())
