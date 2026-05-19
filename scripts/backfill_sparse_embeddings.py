#!/usr/bin/env python3
"""Backfill `chunks.embedding_sparse` for the existing corpus.

Re-runs BGE-M3 over every chunk that doesn't yet have a sparse vector and
populates the column. The dense vector is already there; this run only
uses the sparse head of the same forward pass (we still run a full
forward pass per chunk — there is no API to recover the sparse head from
a stored dense vector, that's not how the model works).

Mirrors the FLUSH_EVERY=500 batch pattern from `scripts/bulk_ingest_sc.py`.

Operating modes:

  --dry-run        Process the first 5 chunks, do NOT write to the DB.
                   Validates the pipeline end-to-end without committing.

  --commit         Actually write. Default `--limit` is None (all chunks).

  --limit N        Stop after N chunks. Useful for the 100-chunk
                   smoke-test (`--commit --limit 100`) the task spec
                   calls for before kicking off the full ~475K-chunk
                   backfill.

Idempotent: the WHERE clause filters to `embedding_sparse IS NULL`, so
re-running this script never recomputes chunks that already have a
sparse vector. A planned re-embed (model swap, etc.) is a separate
operation — see the `--force` flag.

Approx timing on M-series MPS at ~10-15 emb/s:
  *   100 chunks ≈ 10–15 s
  *  10K chunks ≈ 12-17 min
  * 475K chunks ≈ 9-13 h (do this overnight; the user kicks it off)

Estimated dense-cost wasted: ~0% (the dense head IS the bottleneck of
the forward pass — sparse is essentially free given the same input).

Run from repo root:
  PYTHONPATH=. .venv/bin/python scripts/backfill_sparse_embeddings.py --dry-run
  PYTHONPATH=. .venv/bin/python scripts/backfill_sparse_embeddings.py --commit --limit 100
"""
from __future__ import annotations

import argparse
import asyncio
import gc
import json
import logging
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

import asyncpg  # noqa: E402

# Reuse the env loader from the other bulk_ingest scripts so behaviour is
# consistent across the ingest pipeline.
sys.path.insert(0, str(ROOT / "scripts"))

LOG_PATH = ROOT / "data" / "processed" / "backfill_sparse.log"

EMBED_BATCH = 16
FLUSH_EVERY = 500
MAX_SEQ_LEN = 512


def load_env(p: str = ".env") -> dict:
    out: dict[str, str] = {}
    p_file = ROOT / p
    if not p_file.exists():
        return out
    for line in p_file.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, _, v = line.partition("=")
        out[k.strip()] = v.strip().strip('"').strip("'")
    return out


def log(msg: str) -> None:
    stamp = datetime.now(timezone.utc).strftime("%H:%M:%S")
    line = f"[{stamp}] {msg}"
    print(line, flush=True)
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with LOG_PATH.open("a") as f:
        f.write(line + "\n")


async def fetch_batch(conn, last_id: int, batch_size: int, *, force: bool):
    """Return up to `batch_size` chunks past `last_id` that still need
    backfilling. Order by id so we can use the last id of one batch as
    the cursor for the next (cheap monotonic pagination, no OFFSET).
    """
    if force:
        # `--force` re-embeds even chunks that already have a sparse
        # vector — useful if the model changes.
        sql = """SELECT id, text FROM chunks
                 WHERE id > $1 AND NOT quarantined
                 ORDER BY id ASC
                 LIMIT $2"""
    else:
        sql = """SELECT id, text FROM chunks
                 WHERE id > $1
                   AND embedding_sparse IS NULL
                   AND NOT quarantined
                 ORDER BY id ASC
                 LIMIT $2"""
    return await conn.fetch(sql, last_id, batch_size)


async def update_batch(conn, rows: list[tuple[int, str]]) -> int:
    """Write a batch of (chunk_id, jsonb_str) updates."""
    if not rows:
        return 0
    # executemany is fine for hundreds; for larger writes we'd use
    # COPY or UPSERT-from-VALUES. Keeping it consistent with the
    # bulk_ingest_sc/hc pattern.
    await conn.executemany(
        "UPDATE chunks SET embedding_sparse = $2::jsonb WHERE id = $1",
        rows,
    )
    return len(rows)


async def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--commit", action="store_true",
                    help="actually write to the DB. Without this, the script "
                         "embeds a small sample and prints what it would write.")
    ap.add_argument("--dry-run", action="store_true",
                    help="explicit dry-run (default if --commit not given)")
    ap.add_argument("--limit", type=int, default=None,
                    help="cap total chunks processed (per-run). None = no cap.")
    ap.add_argument("--batch-size", type=int, default=FLUSH_EVERY,
                    help=f"chunks per embed+flush cycle (default {FLUSH_EVERY})")
    ap.add_argument("--force", action="store_true",
                    help="re-embed even chunks that already have a sparse vector. "
                         "Use for model swaps.")
    args = ap.parse_args()

    is_dry = not args.commit
    if is_dry and args.limit is None:
        # In dry-run, cap small so we don't waste 10 minutes embedding
        # 100K rows that we then throw away.
        args.limit = 5

    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    log(f"=== backfill_sparse_embeddings starting (mode={'DRY-RUN' if is_dry else 'COMMIT'}) ===")
    log(f"  limit:      {args.limit}")
    log(f"  batch_size: {args.batch_size}")
    log(f"  force:      {args.force}")

    env = load_env()
    if not env.get("POSTGRES_HOST_PORT"):
        log("FATAL: missing .env with POSTGRES_* — cannot connect to DB")
        sys.exit(2)

    # Load BGE-M3 multi-head model.
    from apps.api.embeddings import sparse_to_jsonb  # noqa: E402
    from FlagEmbedding import BGEM3FlagModel  # noqa: E402

    log("loading FlagEmbedding bge-m3 on MPS (multi-head)...")
    t0 = time.time()
    model = BGEM3FlagModel("BAAI/bge-m3", use_fp16=False, device="mps")
    log(f"  model loaded in {time.time()-t0:.1f}s")

    conn = await asyncpg.connect(
        host="localhost", port=int(env["POSTGRES_HOST_PORT"]),
        database=env["POSTGRES_DB"], user=env["POSTGRES_USER"],
        password=env["POSTGRES_PASSWORD"],
    )

    overall_t0 = time.time()
    grand_total = 0
    last_id = 0
    remaining = args.limit  # may be None

    try:
        while True:
            this_batch = args.batch_size
            if remaining is not None:
                this_batch = min(this_batch, remaining)
            if this_batch <= 0:
                break
            chunks = await fetch_batch(conn, last_id, this_batch, force=args.force)
            if not chunks:
                log("  no more chunks to backfill; done")
                break

            texts = [r["text"] for r in chunks]
            t_emb = time.time()
            out = model.encode(
                texts,
                batch_size=EMBED_BATCH,
                max_length=MAX_SEQ_LEN,
                return_dense=False,         # we already have dense
                return_sparse=True,
                return_colbert_vecs=False,
            )
            emb_secs = time.time() - t_emb

            update_rows: list[tuple[int, str]] = []
            for r, raw in zip(chunks, out["lexical_weights"], strict=True):
                sparse: dict[str, float] = {
                    str(k): float(v) for k, v in raw.items() if float(v) > 0.0
                }
                update_rows.append((r["id"], sparse_to_jsonb(sparse)))

            if is_dry:
                sample = update_rows[:2]
                for cid, jb in sample:
                    parsed = json.loads(jb)
                    keys_preview = list(parsed.items())[:6]
                    log(f"  DRY  chunk {cid}: {len(parsed)} tokens, sample {keys_preview}")
            else:
                inserted = await update_batch(conn, update_rows)
                grand_total += inserted
                last_id = chunks[-1]["id"]
                rate = grand_total / (time.time() - overall_t0)
                log(
                    f"  flushed {inserted} (running total {grand_total:,}; "
                    f"batch embed {emb_secs:.1f}s @ {len(chunks)/emb_secs:.1f} emb/s; "
                    f"overall {rate:.1f} emb/s)"
                )

            if is_dry:
                last_id = chunks[-1]["id"]  # still advance cursor for dry-run
                grand_total += len(chunks)

            if remaining is not None:
                remaining -= len(chunks)

            gc.collect()

        elapsed = time.time() - overall_t0
        log(f"\n=== backfill done (mode={'DRY-RUN' if is_dry else 'COMMIT'}) ===")
        log(f"  elapsed:    {elapsed:.0f}s")
        log(f"  processed:  {grand_total:,}")
        if not is_dry:
            still_null = await conn.fetchval(
                "SELECT COUNT(*) FROM chunks WHERE embedding_sparse IS NULL AND NOT quarantined"
            )
            log(f"  remaining null sparse rows in DB: {still_null:,}")

    except KeyboardInterrupt:
        log("interrupted by user — partial progress is committed (idempotent)")
        sys.exit(130)
    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(main())
