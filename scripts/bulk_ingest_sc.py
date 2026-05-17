#!/usr/bin/env python3
"""Bulk SC ingest: stream chunks through embedding + insert in fixed-size flushes.

Fixes vs v1:
- model.max_seq_length = 512 (truncates large chunks → caps attention buffer)
- batch_size = 16 (safer on MPS)
- FLUSH_EVERY chunks → embed + insert + free memory (no 25K-chunk pile-up)

Estimated ~120-220K chunks total at ~10-15 emb/s → 2-6 hours on M4 Max.
"""
from __future__ import annotations

import asyncio
import gc
import hashlib
import json
import re
import sys
import time
from datetime import datetime
from pathlib import Path

import asyncpg
import numpy as np
from sentence_transformers import SentenceTransformer

sys.path.insert(0, str(Path(__file__).parent.parent / "packages"))
from chunking.judgment import chunk_judgment  # noqa: E402
from ingest.normalize.redact import sanitize_for_db  # noqa: E402

ROOT = Path(__file__).parent.parent
SC_DIR = ROOT / "data" / "processed" / "sc"
LOG_PATH = SC_DIR / "ingest.log"

EMBED_BATCH = 16          # batch passed to sentence-transformers
FLUSH_EVERY = 500         # embed + insert every N accumulated chunks
MAX_SEQ_LEN = 512         # truncate inputs to this many tokens


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
    line = f"[{stamp}] {msg}"
    print(line, flush=True)
    with LOG_PATH.open("a") as f:
        f.write(line + "\n")


def doc_id_from_case_id(case_id: str, fallback_stem: str) -> str:
    s = (case_id or "").strip()
    if not s:
        return fallback_stem.lower().replace("_", "-")
    return re.sub(r"\s+", "-", s.lower())


def parse_decision_date(s: str):
    if not s:
        return None
    s = s.strip()
    for fmt in ("%d-%m-%Y", "%Y-%m-%d", "%d/%m/%Y"):
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    return None


async def get_or_create_year_source(conn, year: int) -> int:
    url = f"hf:Rahul1872/Indian-Supreme-Court-Judgments/year={year}"
    url_hash = hashlib.sha256(url.encode()).hexdigest()
    existing = await conn.fetchval(
        "SELECT id FROM sources WHERE canonical_url_hash = $1", url_hash,
    )
    if existing:
        return existing
    return await conn.fetchval(
        """INSERT INTO sources (source_type, origin, url, canonical_url_hash, metadata)
           VALUES ('sc_judgment', 'hf:Rahul1872', $1, $2, $3) RETURNING id""",
        url, url_hash, json.dumps({"year": year}),
    )


async def ensure_document(conn, src_id: int, doc_id: str, row: dict) -> int:
    """Idempotent upsert. Returns the documents.id."""
    dec_date = parse_decision_date(row.get("decision_date", ""))
    return await conn.fetchval(
        """INSERT INTO documents (source_id, doc_id, title, court, bench, parties,
                                  citation, date_decided, subject_area, metadata)
           VALUES ($1, $2, $3, 'SC', $4, $5, $6, $7, $8, $9)
           ON CONFLICT (doc_id) DO UPDATE SET title = EXCLUDED.title
           RETURNING id""",
        src_id, doc_id,
        (row.get("title", "") or "")[:512],
        (row.get("judge", "") or "")[:256],
        f"{row.get('petitioner','')} v. {row.get('respondent','')}"[:512],
        (row.get("citation", "") or "")[:200],
        dec_date, row.get("subject_area"),
        json.dumps({
            "case_id": row.get("case_id"),
            "cnr": row.get("cnr"),
            "nc_display": row.get("nc_display"),
            "case_type": row.get("case_type"),
            "pii_suspicious": row.get("pii_suspicious", False),
            "pdf_pages": row.get("pdf_pages"),
        }),
    )


async def flush_buffer(conn, model, buffer: list) -> int:
    """Embed + insert a buffer of (doc_pk, row, chunk) tuples."""
    if not buffer:
        return 0
    texts = [c.text for _, _, c in buffer]
    embeddings = model.encode(
        texts, batch_size=EMBED_BATCH, show_progress_bar=False,
        normalize_embeddings=True, convert_to_numpy=True,
    )
    rows = []
    seen = set()
    for i, (doc_pk, row, c) in enumerate(buffer):
        key = (doc_pk, c.anchor, c.as_at)
        if key in seen:
            continue
        seen.add(key)
        emb = embeddings[i].astype(np.float32)
        emb_str = "[" + ",".join(f"{x:.7f}" for x in emb) + "]"
        rows.append((
            doc_pk, "sc_judgment", row.get("subject_area"),
            c.anchor, c.paragraph_no, c.token_count, c.text, emb_str,
            c.chunk_strategy.value, c.as_at,
            json.dumps(c.metadata),
        ))
    if rows:
        await conn.executemany(
            """INSERT INTO chunks
               (document_id, source_type, subject_area, anchor, paragraph_no,
                token_count, text, embedding, chunk_strategy, as_at, metadata)
               VALUES ($1, $2, $3, $4, $5, $6, $7, $8::halfvec, $9, $10, $11)
               ON CONFLICT (document_id, anchor, as_at) DO NOTHING""",
            rows,
        )
    return len(rows)


async def main():
    env = load_env()
    LOG_PATH.write_text("")
    log("=== bulk_ingest_sc v2 starting ===")

    files = sorted(SC_DIR.glob("year=*.jsonl"))
    log(f"input files: {[f.name for f in files]}")

    log("loading bge-m3 on MPS...")
    t0 = time.time()
    model = SentenceTransformer("BAAI/bge-m3", device="mps")
    model.max_seq_length = MAX_SEQ_LEN
    log(f"  model loaded in {time.time()-t0:.1f}s; max_seq_length={model.max_seq_length}")

    conn = await asyncpg.connect(
        host="localhost", port=int(env["POSTGRES_HOST_PORT"]),
        database=env["POSTGRES_DB"], user=env["POSTGRES_USER"],
        password=env["POSTGRES_PASSWORD"],
    )

    loaded = {r["doc_id"] for r in await conn.fetch(
        "SELECT doc_id FROM documents WHERE court='SC'"
    )}
    log(f"resume: {len(loaded)} sc judgments already in db")

    overall_t0 = time.time()
    grand_total_chunks = 0
    grand_total_judgments = 0
    grand_total_skipped = 0

    for jsonl_file in files:
        year = int(jsonl_file.stem.split("=")[1])
        log(f"\n--- year={year} ---")
        src_id = await get_or_create_year_source(conn, year)

        buffer: list = []
        year_t0 = time.time()
        year_chunks = 0
        year_judgments = 0
        year_skipped = 0

        with jsonl_file.open() as f:
            for line in f:
                row = json.loads(line)
                did = doc_id_from_case_id(row.get("case_id", ""), row.get("path_stem", ""))
                if did in loaded:
                    year_skipped += 1
                    continue
                # Don't drop judgments with no subject_area tag — surface them
                # honestly with subject_area=null (the coverage chip + retrieval
                # filters can decide what to do with them).
                # If subject_area is missing from JSONL, infer it now from text.
                if not row.get("subject_area"):
                    try:
                        from ingest.adapters.base import infer_subject_area
                        row["subject_area"] = infer_subject_area(row["text"])
                    except Exception:
                        row["subject_area"] = None
                # Materialize the doc (so chunks have a valid foreign key)
                doc_pk = await ensure_document(conn, src_id, did, row)
                loaded.add(did)
                year_judgments += 1

                # Sanitize the source text before chunking. PyMuPDF can emit
                # NULL bytes from binary PDF glyphs which Postgres rejects;
                # we strip them at this boundary.
                clean_text = sanitize_for_db(row["text"])
                for c in chunk_judgment(did, clean_text):
                    # Belt-and-braces: in case the chunker re-introduced any
                    if "\x00" in c.text:
                        c.text = sanitize_for_db(c.text)
                    buffer.append((doc_pk, row, c))
                    if len(buffer) >= FLUSH_EVERY:
                        inserted = await flush_buffer(conn, model, buffer)
                        year_chunks += inserted
                        buffer = []
                        gc.collect()
                        rate = year_chunks / (time.time() - year_t0) if year_chunks else 0
                        log(f"  {year}: {year_judgments} judgments / {year_chunks} chunks "
                            f"({rate:.1f} emb/s, buffer drained)")

        # Final flush for the year
        if buffer:
            inserted = await flush_buffer(conn, model, buffer)
            year_chunks += inserted
            buffer = []
            gc.collect()

        year_elapsed = time.time() - year_t0
        log(f"  year {year} done: {year_judgments} judgments, {year_chunks} chunks, "
            f"{year_skipped} skipped, {year_elapsed:.0f}s "
            f"({year_chunks/year_elapsed:.1f} emb/s avg)")
        grand_total_chunks += year_chunks
        grand_total_judgments += year_judgments
        grand_total_skipped += year_skipped

    elapsed = time.time() - overall_t0
    db_count = await conn.fetchval("SELECT COUNT(*) FROM chunks WHERE source_type='sc_judgment'")
    db_docs = await conn.fetchval("SELECT COUNT(*) FROM documents WHERE court='SC'")
    log(f"\n=== bulk_ingest_sc v2 done ===")
    log(f"  elapsed: {elapsed:.0f}s ({elapsed/60:.1f} min)")
    log(f"  this run: {grand_total_judgments} judgments, {grand_total_chunks} chunks, "
        f"{grand_total_skipped} skipped")
    log(f"  DB totals — sc documents: {db_docs}, sc chunks: {db_count}")
    await conn.close()


if __name__ == "__main__":
    asyncio.run(main())
