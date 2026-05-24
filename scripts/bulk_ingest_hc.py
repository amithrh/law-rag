#!/usr/bin/env python3
"""Bulk HC ingest — mirror of `bulk_ingest_sc.py` but for High Courts.

Pulls judgments from the AWS Open Data Registry mirror of ecourts.gov.in
(see `packages/ingest/adapters/hc.py` for the long-form rationale), then
runs the same chunker + embedder + DB-insert path the SC pipeline uses.

The fetch path:
  1. List benches under `metadata/parquet/year=YYYY/court=N_M/`
  2. Download each bench's `metadata.parquet` (canonical Govt metadata).
  3. For each row, fetch the PDF from `data/pdf/.../<basename>.pdf`.
  4. Extract text with PyMuPDF, infer subject_area, chunk, embed, insert.

Two operating modes:
  --dry-run     (default for safety) — fetch + extract + chunk, write a
                JSONL row per judgment to data/processed/hc/year=YYYY.jsonl,
                but DO NOT touch the DB or call the embedder.
                This is what `--max-docs 5` will use for sanity-checking
                the prototype without spinning up Postgres / loading the
                bge-m3 model.

  --commit      Full path: also load bge-m3 on MPS, embed every chunk in
                FLUSH_EVERY batches, and INSERT into Postgres exactly the
                way `bulk_ingest_sc.py` does. Idempotent on `doc_id`.

Loud-fail policy (per task brief):
  * HTTP 429 from S3 → RateLimitedError, exit non-zero. We do NOT retry
    silently. The user inspects, throttles, and re-runs.
  * HTML CAPTCHA page returned where a PDF was expected →
    CaptchaRequiredError, exit non-zero. (Should never happen on the S3
    path; surfaces if anyone re-points the adapter at a portal that
    silently CAPTCHA-walls us.)
  * PDF 404 rate > 30% → assume bucket layout has shifted, error out.

Setup (run once after pulling this branch):
  uv pip install -e .                  # picks up pyarrow / httpx / pymupdf
  # no `playwright install` needed — this adapter is httpx-only.

Sanity check (5 docs, no DB, no embedder):
  python scripts/bulk_ingest_hc.py --max-docs 5

Full Delhi HC ingest (when ready):
  python scripts/bulk_ingest_hc.py --commit --year-from 2024 --year-to 2025
"""
from __future__ import annotations

import argparse
import asyncio
import gc
import hashlib
import json
import logging
import os
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT / "packages"))

from ingest.adapters.base import AdapterQuery, infer_subject_area  # noqa: E402
from ingest.adapters.hc import (  # noqa: E402
    CaptchaRequiredError,
    DEFAULT_YEAR_FROM,
    DEFAULT_YEAR_TO,
    HCEcourtsAdapter,
    RateLimitedError,
)
from ingest.normalize.redact import sanitize_for_db  # noqa: E402

HC_DIR = ROOT / "data" / "processed" / "hc"
LOG_PATH = HC_DIR / "ingest.log"

EMBED_BATCH = 16
FLUSH_EVERY = 500
MAX_SEQ_LEN = 512

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("bulk_ingest_hc")


def log(msg: str) -> None:
    stamp = datetime.now(timezone.utc).strftime("%H:%M:%S")
    line = f"[{stamp}] {msg}"
    print(line, flush=True)
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with LOG_PATH.open("a") as f:
        f.write(line + "\n")


def load_env(p: str = ".env") -> dict:
    env: dict[str, str] = {}
    p_file = ROOT / p
    if not p_file.exists():
        return env
    for line in p_file.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, _, v = line.partition("=")
        env[k.strip()] = v.strip().strip('"').strip("'")
    return env


def doc_id_from_cnr(cnr: str, fallback: str) -> str:
    """Build a stable doc_id from the canonical CNR. Falls back to a hash
    of the mirror URL if CNR is missing — every doc must have a unique id.
    """
    cnr = (cnr or "").strip()
    if cnr:
        return f"hc/{cnr.lower()}"
    return f"hc/sha-{hashlib.sha256(fallback.encode()).hexdigest()[:16]}"


def parse_pdf_to_text(pdf_bytes: bytes) -> tuple[str, int]:
    import fitz  # PyMuPDF

    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    pages = len(doc)
    parts: list[str] = []
    for page in doc:
        parts.append(page.get_text("text"))
    doc.close()
    return "\n".join(parts), pages


def synth_jsonl_row(raw_doc, text: str, pages: int) -> dict:
    """Build a JSONL row matching the SC ingest shape (so the chunker +
    embedder code paths don't need to know whether the source is SC or HC).
    """
    md = raw_doc.metadata or {}
    cnr = md.get("cnr") or ""
    title = md.get("title") or ""
    # Pull petitioner / respondent out of "<X> Vs <Y>" if present
    petitioner, respondent = _parse_parties(title)
    return {
        "doc_id": doc_id_from_cnr(cnr, raw_doc.url),
        "court": md.get("court_short", "HC"),
        "court_full": md.get("court"),
        "bench": md.get("bench"),
        "bench_code": md.get("bench_code"),
        "cnr": cnr,
        "title": title,
        "petitioner": petitioner,
        "respondent": respondent,
        "citation": "",  # HC parquet does not carry a printed citation
        "case_id": cnr,
        "judge": md.get("judge"),
        "decision_date": md.get("decision_date"),
        "date_of_registration": md.get("date_of_registration"),
        "disposal_nature": md.get("disposal_nature"),
        "year": md.get("year"),
        "subject_area": infer_subject_area(text, title=md.get("title") or ""),
        "pdf_url": md.get("mirror_url"),
        "canonical_url": md.get("canonical_url"),
        "license": md.get("license", "CC-BY-4.0"),
        "pdf_pages": pages,
        "pdf_bytes": len(raw_doc.payload),
        "text_chars": len(text),
        "text_sha256": hashlib.sha256(text.encode("utf-8", errors="replace")).hexdigest()[:16],
        "text": text,
    }


_PARTIES_RE = re.compile(r"(.+?)\s+Vs\.?\s+(.+)", re.IGNORECASE)


def _parse_parties(title: str) -> tuple[str, str]:
    if not title:
        return "", ""
    # Drop the leading "W.P.(C)/123/2024 of " case-number prefix if present
    m = re.match(r"^\s*[A-Z\.\(\)]+\s*/[\w/-]+\s+of\s+(.+)$", title)
    payload = m.group(1) if m else title
    m2 = _PARTIES_RE.match(payload)
    if not m2:
        return payload.strip()[:256], ""
    return m2.group(1).strip()[:256], m2.group(2).strip()[:256]


async def write_dry_run_jsonl(rows: list[dict], year: int) -> Path:
    out = HC_DIR / f"year={year}.jsonl"
    HC_DIR.mkdir(parents=True, exist_ok=True)
    with out.open("a") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    return out


def append_dry_run_row(row: dict, year: int) -> Path:
    """Crash-safe per-doc append: write+fsync one row to year file.

    Prevents the 3,298-doc loss we saw when an httpx.ConnectError mid-stream
    killed the job before the end-of-loop bulk write fired.
    """
    out = HC_DIR / f"year={year}.jsonl"
    HC_DIR.mkdir(parents=True, exist_ok=True)
    with out.open("a") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")
        f.flush()
        os.fsync(f.fileno())
    return out


# ---------------------------------------------------------------------------
# DB-commit path: lazily imported so dry-run mode works without Postgres
# ---------------------------------------------------------------------------


async def get_or_create_hc_source(conn, court_code: str, year: int) -> int:
    url = f"s3:indian-high-court-judgments/year={year}/court={court_code}"
    url_hash = hashlib.sha256(url.encode()).hexdigest()
    existing = await conn.fetchval(
        "SELECT id FROM sources WHERE canonical_url_hash = $1", url_hash,
    )
    if existing:
        return existing
    return await conn.fetchval(
        """INSERT INTO sources (source_type, origin, url, canonical_url_hash, metadata)
           VALUES ('hc_judgment', 's3:indian-high-court-judgments', $1, $2, $3) RETURNING id""",
        url, url_hash, json.dumps({"year": year, "court_code": court_code}),
    )


async def ensure_document(conn, src_id: int, row: dict) -> int:
    dec_date = row.get("decision_date")
    try:
        dec = datetime.strptime(dec_date, "%Y-%m-%d").date() if dec_date else None
    except (ValueError, TypeError):
        dec = None
    parties = f"{row.get('petitioner','')} v. {row.get('respondent','')}"[:512]
    return await conn.fetchval(
        """INSERT INTO documents (source_id, doc_id, title, court, bench, parties,
                                  citation, date_decided, subject_area, metadata)
           VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)
           ON CONFLICT (doc_id) DO UPDATE SET title = EXCLUDED.title
           RETURNING id""",
        src_id, row["doc_id"], (row.get("title") or "")[:512],
        row.get("court") or "HC", (row.get("bench") or "")[:256], parties,
        row.get("citation", "")[:200], dec, row.get("subject_area"),
        json.dumps({
            "cnr": row.get("cnr"),
            "case_id": row.get("case_id"),
            "court_full": row.get("court_full"),
            "bench_code": row.get("bench_code"),
            "judge": row.get("judge"),
            "pdf_url": row.get("pdf_url"),
            "canonical_url": row.get("canonical_url"),
            "license": row.get("license"),
            "disposal_nature": row.get("disposal_nature"),
            "pdf_pages": row.get("pdf_pages"),
            "text_chars": row.get("text_chars"),
            "text_sha256": row.get("text_sha256"),
        }),
    )


async def flush_buffer(conn, model, buffer: list) -> int:
    if not buffer:
        return 0
    import numpy as np

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
            doc_pk, "hc_judgment", row.get("subject_area"),
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
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--year-from", type=int, default=DEFAULT_YEAR_FROM,
                    help=f"first year to ingest (default {DEFAULT_YEAR_FROM})")
    ap.add_argument("--year-to", type=int, default=DEFAULT_YEAR_TO,
                    help=f"last year to ingest (default {DEFAULT_YEAR_TO})")
    ap.add_argument("--courts", default="7_26",
                    help="comma-separated court codes (default 7_26 = Delhi HC). "
                         "See packages/ingest/adapters/hc.py for the full mapping.")
    ap.add_argument("--max-docs", type=int, default=None,
                    help="cap total judgments (per-run). None = no cap.")
    ap.add_argument("--throttle-s", type=float, default=0.2,
                    help="seconds to sleep between PDF fetches")
    ap.add_argument("--commit", action="store_true",
                    help="actually embed + insert into Postgres. "
                         "Without this flag, runs in --dry-run mode (jsonl only).")
    ap.add_argument("--dry-run", action="store_true",
                    help="explicit dry-run (default if --commit not given)")
    args = ap.parse_args()

    is_dry = not args.commit
    courts = [c.strip() for c in args.courts.split(",") if c.strip()]
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    log(f"=== bulk_ingest_hc starting (mode={'DRY-RUN' if is_dry else 'COMMIT'}) ===")
    log(f"  courts: {courts}")
    log(f"  years:  {args.year_from} → {args.year_to}")
    log(f"  max-docs: {args.max_docs}")

    conn = None
    model = None
    if not is_dry:
        env = load_env()
        if not env.get("POSTGRES_HOST_PORT"):
            log("FATAL: --commit requires .env with POSTGRES_HOST_PORT, POSTGRES_DB, "
                "POSTGRES_USER, POSTGRES_PASSWORD")
            sys.exit(2)
        import asyncpg
        from sentence_transformers import SentenceTransformer

        log("loading bge-m3 on MPS...")
        t0 = time.time()
        model = SentenceTransformer("BAAI/bge-m3", device="mps")
        model.max_seq_length = MAX_SEQ_LEN
        log(f"  model loaded in {time.time()-t0:.1f}s")
        conn = await asyncpg.connect(
            host="localhost", port=int(env["POSTGRES_HOST_PORT"]),
            database=env["POSTGRES_DB"], user=env["POSTGRES_USER"],
            password=env["POSTGRES_PASSWORD"],
        )

    grand_total_judgments = 0
    grand_total_chunks = 0
    overall_t0 = time.time()

    try:
        async with HCEcourtsAdapter(courts=courts, throttle_s=args.throttle_s) as adapter:
            query = AdapterQuery(
                year_from=args.year_from,
                year_to=args.year_to,
                courts=courts,
                limit=args.max_docs,
            )
            jsonl_rows: list[dict] = []
            buffer: list = []
            year_buckets: dict[int, list[dict]] = {}

            async for raw_doc in adapter.iter_docs(query):
                md = raw_doc.metadata or {}
                try:
                    text, pages = parse_pdf_to_text(raw_doc.payload)
                except Exception as e:
                    log(f"  WARN: pdf parse failed for {md.get('cnr')}: {e!r}")
                    continue
                if len(text.strip()) < 100:
                    log(f"  WARN: empty/short text for {md.get('cnr')} — skipping")
                    continue
                row = synth_jsonl_row(raw_doc, text, pages)
                grand_total_judgments += 1
                year = md.get("year") or args.year_from
                year_buckets.setdefault(year, []).append(row)
                log(f"  fetched {grand_total_judgments}: {row['doc_id']} "
                    f"({pages}p, {row['text_chars']:,} chars, "
                    f"subject={row['subject_area']})")

                # Crash-safe: append each dry-run row to disk immediately,
                # so a mid-stream network/system failure doesn't lose the
                # whole run. The end-of-loop bulk write becomes a no-op.
                if is_dry:
                    append_dry_run_row(row, year)

                if not is_dry:
                    from chunking.judgment import chunk_judgment

                    src_id = await get_or_create_hc_source(conn, md.get("court_code"), year)
                    doc_pk = await ensure_document(conn, src_id, row)
                    clean = sanitize_for_db(text)
                    for c in chunk_judgment(row["doc_id"], clean):
                        if "\x00" in c.text:
                            c.text = sanitize_for_db(c.text)
                        buffer.append((doc_pk, row, c))
                        if len(buffer) >= FLUSH_EVERY:
                            inserted = await flush_buffer(conn, model, buffer)
                            grand_total_chunks += inserted
                            buffer = []
                            gc.collect()
                            log(f"    flushed {inserted} chunks "
                                f"(running total: {grand_total_chunks:,})")

            # Final flush
            if is_dry:
                # Per-doc append_dry_run_row already wrote each row safely
                # mid-stream. Just print the summary tally per year.
                for year, rows in year_buckets.items():
                    log(f"  total dry-run rows for year={year}: {len(rows)} "
                        f"(already persisted incrementally)")
            else:
                if buffer:
                    grand_total_chunks += await flush_buffer(conn, model, buffer)

    except RateLimitedError as e:
        log(f"FATAL: rate-limited by S3 → {e}")
        sys.exit(3)
    except CaptchaRequiredError as e:
        log(f"FATAL: CAPTCHA required on what should be the S3 path → {e}")
        sys.exit(4)
    except KeyboardInterrupt:
        log("interrupted by user")
        sys.exit(130)
    finally:
        if conn is not None:
            await conn.close()

    elapsed = time.time() - overall_t0
    log(f"\n=== bulk_ingest_hc done (mode={'DRY-RUN' if is_dry else 'COMMIT'}) ===")
    log(f"  elapsed:    {elapsed:.0f}s")
    log(f"  judgments:  {grand_total_judgments}")
    if not is_dry:
        log(f"  chunks:     {grand_total_chunks}")


if __name__ == "__main__":
    asyncio.run(main())
