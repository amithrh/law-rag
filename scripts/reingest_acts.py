#!/usr/bin/env python3
"""Re-ingest all bare acts in data/processed/acts.jsonl with the current chunker.

Wipes existing `bare_act` rows in postgres and re-loads from JSONL. SC chunks
are not affected. This is the operation to run after a chunker code change.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import sys
import time
from datetime import datetime
from pathlib import Path

import asyncpg
import numpy as np
from sentence_transformers import SentenceTransformer

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT / "packages"))
from chunking.act import chunk_act  # noqa: E402
from ingest.normalize.redact import sanitize_for_db  # noqa: E402


def load_env(p: str = ".env") -> dict:
    out = {}
    for line in (ROOT / p).read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, _, v = line.partition("=")
        out[k.strip()] = v.strip().strip('"').strip("'")
    return out


def log(msg: str) -> None:
    stamp = datetime.utcnow().strftime("%H:%M:%S")
    print(f"[{stamp}] {msg}", flush=True)


async def main():
    env = load_env()
    jsonl = ROOT / "data" / "processed" / "acts.jsonl"
    if not jsonl.exists():
        log(f"ERROR: {jsonl} not found")
        return

    # --- Read JSONL ---------------------------------------------------------
    rows = [json.loads(line) for line in jsonl.read_text().splitlines() if line.strip()]
    log(f"loaded {len(rows)} act rows from {jsonl.name}")

    # --- Chunk all acts (CPU work) ------------------------------------------
    t0 = time.time()
    all_chunks: list[tuple[dict, object]] = []
    per_act: dict[str, int] = {}
    for row in rows:
        # Sanitize source text — protect against NULL bytes from PDF
        text = sanitize_for_db(row["text"])
        chunks = list(chunk_act(row["slug"], text))
        per_act[row["slug"]] = len(chunks)
        for c in chunks:
            if "\x00" in c.text:
                c.text = sanitize_for_db(c.text)
            all_chunks.append((row, c))
    log(f"chunked {len(all_chunks)} chunks across {len(rows)} acts in {time.time()-t0:.1f}s")
    for slug, n in per_act.items():
        log(f"  {slug:30s}: {n:>4d} chunks")

    # --- Embed --------------------------------------------------------------
    log("loading bge-m3 on MPS...")
    t0 = time.time()
    model = SentenceTransformer("BAAI/bge-m3", device="mps")
    model.max_seq_length = 512
    log(f"  loaded in {time.time()-t0:.1f}s")

    texts = [c.text for _, c in all_chunks]
    t0 = time.time()
    embeddings = model.encode(
        texts, batch_size=16, show_progress_bar=False,
        normalize_embeddings=True, convert_to_numpy=True,
    )
    log(f"embedded {len(texts)} chunks in {time.time()-t0:.0f}s "
        f"({len(texts)/(time.time()-t0):.1f} emb/s)")

    # --- Write to postgres --------------------------------------------------
    conn = await asyncpg.connect(
        host="localhost", port=int(env["POSTGRES_HOST_PORT"]),
        database=env["POSTGRES_DB"], user=env["POSTGRES_USER"],
        password=env["POSTGRES_PASSWORD"],
    )

    async with conn.transaction():
        # Wipe existing bare_act data
        log("wiping existing bare_act rows...")
        deleted = await conn.fetchval(
            "WITH d AS (DELETE FROM documents "
            "WHERE id IN (SELECT id FROM documents WHERE source_id IN "
            "             (SELECT id FROM sources WHERE source_type='bare_act')) "
            "RETURNING id) SELECT COUNT(*) FROM d"
        )
        log(f"  deleted {deleted} bare_act documents (cascades to chunks)")
        # Clean up sources too
        await conn.execute("DELETE FROM sources WHERE source_type='bare_act'")

        # Re-insert per act
        by_slug: dict[str, tuple[dict, list, list[int]]] = {}
        for i, (row, c) in enumerate(all_chunks):
            entry = by_slug.setdefault(row["slug"], (row, [], []))
            entry[1].append(c)
            entry[2].append(i)

        total_inserted = 0
        for slug, (row, chunks, global_indices) in by_slug.items():
            url = row["handle_url"]
            url_hash = hashlib.sha256(url.encode()).hexdigest()
            src_id = await conn.fetchval(
                """INSERT INTO sources (source_type, origin, url, canonical_url_hash, metadata)
                   VALUES ('bare_act', 'indiacode', $1, $2, $3) RETURNING id""",
                url, url_hash,
                json.dumps({"slug": slug, "act_no": row.get("act_no", ""),
                            "title": row.get("title", "")}),
            )
            as_at = chunks[0].as_at if chunks else None
            doc_pk = await conn.fetchval(
                """INSERT INTO documents (source_id, doc_id, title, statute_short, statute_year, as_at, metadata)
                   VALUES ($1, $2, $3, $4, $5, $6, $7) RETURNING id""",
                src_id, slug, row.get("title", "").strip() or slug, row.get("title", "").strip() or slug,
                int(slug.split('-')[-1]) if slug.split('-')[-1].isdigit() else None,
                as_at, json.dumps({"handle_id": row.get("handle_id")}),
            )
            # Build batched insert
            insert_rows = []
            for chunk, global_idx in zip(chunks, global_indices, strict=True):
                emb = embeddings[global_idx].astype(np.float32)
                emb_str = "[" + ",".join(f"{x:.7f}" for x in emb) + "]"
                insert_rows.append((
                    doc_pk, "bare_act", chunk.anchor, chunk.paragraph_no,
                    chunk.token_count, chunk.text, emb_str,
                    chunk.chunk_strategy.value, chunk.as_at,
                    json.dumps(chunk.metadata),
                ))
            await conn.executemany(
                """INSERT INTO chunks
                   (document_id, source_type, anchor, paragraph_no,
                    token_count, text, embedding, chunk_strategy, as_at, metadata)
                   VALUES ($1, $2, $3, $4, $5, $6, $7::halfvec, $8, $9, $10)
                   ON CONFLICT (document_id, anchor, as_at) DO NOTHING""",
                insert_rows,
            )
            log(f"  ✓ {slug:30s}: {len(chunks)} chunks")
            total_inserted += len(chunks)

    total_chunks = await conn.fetchval(
        "SELECT COUNT(*) FROM chunks WHERE source_type='bare_act'"
    )
    total_docs = await conn.fetchval(
        "SELECT COUNT(*) FROM documents WHERE source_id IN "
        "(SELECT id FROM sources WHERE source_type='bare_act')"
    )
    log(f"\nDB: {total_docs} act documents, {total_chunks} bare_act chunks "
        f"(this run inserted {total_inserted})")
    await conn.close()


if __name__ == "__main__":
    asyncio.run(main())
