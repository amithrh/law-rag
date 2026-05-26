#!/usr/bin/env python3
"""Insert chunks for cached bare Acts without wiping the corpus.

This is the safe companion to `scripts/reingest_acts.py`: it reads selected
rows from `data/processed/acts.jsonl`, chunks and embeds only those Acts, and
skips any document that already has chunks.

Default target is the RTI Act, which existed locally as a zero-chunk document
after the wave-2 ingest work. Run from repo root:

  PYTHONPATH=. .venv/bin/python scripts/add_cached_act_chunks.py --slugs rti-2005
  PYTHONPATH=. .venv/bin/python scripts/add_cached_act_chunks.py --title-only \
    --slugs bns-2023 bnss-2023 code-on-wages-2019 rti-2005
"""
from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import sys
import time
from datetime import date
from pathlib import Path
from typing import Any

import numpy as np
from sentence_transformers import SentenceTransformer

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT / "packages"))

from chunking.act import chunk_act  # noqa: E402
from ingest.adapters.base import infer_subject_area  # noqa: E402
from ingest.normalize.redact import sanitize_for_db  # noqa: E402

from apps.api.db import close_pool, get_pool  # noqa: E402


DEFAULT_SLUGS = ("rti-2005",)
EMBEDDING_MODEL = "BAAI/bge-m3"

TITLE_OVERRIDES = {
    "bns-2023": "Bharatiya Nyaya Sanhita 2023",
    "bnss-2023": "Bharatiya Nagarik Suraksha Sanhita 2023",
    "rti-2005": "Right to Information Act 2005",
    "code-on-wages-2019": "Code on Wages 2019",
}

SUBJECT_OVERRIDES = {
    "bns-2023": "criminal",
    "bnss-2023": "criminal",
    "rti-2005": "rti",
    "code-on-wages-2019": "service_employment",
}


def _load_rows(slugs: set[str]) -> dict[str, dict[str, Any]]:
    path = ROOT / "data" / "processed" / "acts.jsonl"
    if not path.exists():
        raise FileNotFoundError(path)
    rows: dict[str, dict[str, Any]] = {}
    with path.open(errors="ignore") as f:
        for line in f:
            if not line.strip():
                continue
            row = json.loads(line)
            slug = row.get("slug")
            if slug in slugs:
                rows[slug] = row
    missing = sorted(slugs - set(rows))
    if missing:
        raise SystemExit(f"Missing slugs in {path}: {', '.join(missing)}")
    return rows


def _display_title(row: dict[str, Any]) -> str:
    slug = row["slug"]
    return TITLE_OVERRIDES.get(slug) or row.get("title", "").strip() or slug


def _subject_area(row: dict[str, Any]) -> str:
    slug = row["slug"]
    if slug in SUBJECT_OVERRIDES:
        return SUBJECT_OVERRIDES[slug]
    return infer_subject_area(_display_title(row), row.get("text", "")[:500]).value


def _year_from_slug(slug: str) -> int | None:
    last = slug.rsplit("-", 1)[-1]
    if last.isdigit() and 1850 <= int(last) <= 2100:
        return int(last)
    return None


async def _upsert_source(conn, row: dict[str, Any]) -> int:
    url = row.get("handle_url") or row.get("pdf_url") or row.get("pdf_local") or row["slug"]
    url_hash = hashlib.sha256(str(url).encode()).hexdigest()
    return await conn.fetchval(
        """
        INSERT INTO sources (source_type, origin, url, canonical_url_hash, metadata)
        VALUES ('bare_act', 'indiacode', $1, $2, $3)
        ON CONFLICT (canonical_url_hash) DO UPDATE
            SET metadata = COALESCE(sources.metadata, '{}'::jsonb) || EXCLUDED.metadata
        RETURNING id
        """,
        str(url),
        url_hash,
        json.dumps({
            "slug": row["slug"],
            "handle_id": row.get("handle_id"),
            "pdf_local": row.get("pdf_local"),
        }),
    )


async def _ensure_document(conn, row: dict[str, Any], src_id: int, as_at: date | None) -> tuple[int, int]:
    slug = row["slug"]
    title = _display_title(row)
    subject = _subject_area(row)
    existing = await conn.fetchrow(
        """
        SELECT d.id, count(c.id) AS n_chunks
        FROM documents d
        LEFT JOIN chunks c ON c.document_id = d.id
        WHERE d.doc_id = $1
        GROUP BY d.id
        """,
        slug,
    )
    metadata = json.dumps({
        "handle_id": row.get("handle_id"),
        "pdf_local": row.get("pdf_local"),
        "cached_act_backfill": True,
    })
    if existing:
        await conn.execute(
            """
            UPDATE documents
            SET title = $2,
                statute_short = $2,
                subject_area = COALESCE(subject_area, $3),
                metadata = COALESCE(metadata, '{}'::jsonb) || $4::jsonb
            WHERE id = $1
            """,
            existing["id"],
            title,
            subject,
            metadata,
        )
        return existing["id"], int(existing["n_chunks"])

    year = _year_from_slug(slug)
    doc_pk = await conn.fetchval(
        """
        INSERT INTO documents (
            source_id, doc_id, title, statute_short, statute_year,
            as_at, subject_area, metadata
        )
        VALUES ($1, $2, $3, $3, $4, $5, $6, $7)
        RETURNING id
        """,
        src_id,
        slug,
        title,
        year,
        as_at,
        subject,
        metadata,
    )
    return int(doc_pk), 0


async def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--slugs", nargs="+", default=list(DEFAULT_SLUGS))
    parser.add_argument(
        "--title-only",
        action="store_true",
        help="only normalize document title/statute metadata; do not chunk or embed",
    )
    args = parser.parse_args()

    rows = _load_rows(set(args.slugs))
    print(f"=== cached act chunk backfill: {', '.join(args.slugs)} ===", flush=True)

    if args.title_only:
        pool = await get_pool()
        async with pool.acquire() as conn:
            for slug in args.slugs:
                row = rows[slug]
                src_id = await _upsert_source(conn, row)
                doc_pk, existing_chunks = await _ensure_document(conn, row, src_id, None)
                print(
                    f"  ✓ {slug}: normalized title on doc={doc_pk} "
                    f"(chunks={existing_chunks})",
                    flush=True,
                )
        await close_pool()
        print("=== done: title metadata normalized ===")
        return

    prepared: list[tuple[dict[str, Any], list[Any]]] = []
    for slug in args.slugs:
        row = rows[slug]
        text = sanitize_for_db(row["text"])
        chunks = list(chunk_act(slug, text, act_title=_display_title(row)))
        prepared.append((row, chunks))
        print(f"  {slug}: {len(chunks)} chunks from {len(text):,} chars", flush=True)

    all_chunks = [(row, chunk) for row, chunks in prepared for chunk in chunks]
    if not all_chunks:
        print("Nothing to insert.")
        return

    print("loading bge-m3 on MPS...", flush=True)
    t0 = time.time()
    model = SentenceTransformer(EMBEDDING_MODEL, device="mps")
    model.max_seq_length = 512
    print(f"  loaded in {time.time() - t0:.1f}s", flush=True)

    texts = [chunk.text for _, chunk in all_chunks]
    t0 = time.time()
    embeddings = model.encode(
        texts,
        batch_size=16,
        show_progress_bar=True,
        convert_to_numpy=True,
        normalize_embeddings=True,
    )
    print(f"embedded {len(texts)} chunks in {time.time() - t0:.1f}s", flush=True)

    pool = await get_pool()
    inserted_total = 0
    skipped_total = 0
    async with pool.acquire() as conn:
        async with conn.transaction():
            cursor = 0
            for row, chunks in prepared:
                slug = row["slug"]
                src_id = await _upsert_source(conn, row)
                as_at = chunks[0].as_at if chunks else None
                doc_pk, existing_chunks = await _ensure_document(conn, row, src_id, as_at)
                if existing_chunks > 0:
                    print(f"  - {slug}: already has {existing_chunks} chunks; skipped")
                    skipped_total += existing_chunks
                    cursor += len(chunks)
                    continue

                insert_rows = []
                for chunk, emb in zip(chunks, embeddings[cursor: cursor + len(chunks)], strict=True):
                    emb32 = emb.astype(np.float32)
                    emb_str = "[" + ",".join(f"{x:.7f}" for x in emb32) + "]"
                    insert_rows.append((
                        doc_pk,
                        "bare_act",
                        _subject_area(row),
                        chunk.anchor,
                        chunk.paragraph_no,
                        chunk.token_count,
                        chunk.text,
                        emb_str,
                        chunk.chunk_strategy.value,
                        chunk.as_at,
                        json.dumps(chunk.metadata),
                    ))
                cursor += len(chunks)
                await conn.executemany(
                    """
                    INSERT INTO chunks (
                        document_id, source_type, subject_area, anchor, paragraph_no,
                        token_count, text, embedding, chunk_strategy, as_at, metadata
                    )
                    VALUES ($1, $2, $3, $4, $5, $6, $7, $8::halfvec, $9, $10, $11)
                    ON CONFLICT (document_id, anchor, as_at) DO NOTHING
                    """,
                    insert_rows,
                )
                inserted_total += len(insert_rows)
                print(f"  ✓ {slug}: inserted {len(insert_rows)} chunks")
    await close_pool()
    print(f"=== done: inserted={inserted_total}, skipped_existing={skipped_total} ===")


if __name__ == "__main__":
    asyncio.run(main())
