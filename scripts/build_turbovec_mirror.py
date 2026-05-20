#!/usr/bin/env python3
"""Mirror Postgres chunks into a TurboVec SQLite database.

Spike infrastructure (2026-05-21). Used today against raw 1024-d
bge-m3 embeddings to measure quality vs pgvector. Will be the
production builder once we have the stage-4 distilled 384-d embedder
(see docs/OFFLINE_DISTRIBUTION_TURBOVEC.md).

Usage:
  # Mirror all bare-act chunks at 3-bit quantization (the default)
  PYTHONPATH=. .venv/bin/python scripts/build_turbovec_mirror.py \\
      --where "source_type='bare_act'" \\
      --out /tmp/lawrag_bare_acts.db

  # With explicit bit budget + table name
  PYTHONPATH=. .venv/bin/python scripts/build_turbovec_mirror.py \\
      --where "source_type='bare_act'" \\
      --out /tmp/lawrag.db \\
      --table bare_acts \\
      --bits 3 \\
      --dim 1024
"""
from __future__ import annotations

import argparse
import ast
import asyncio
import os
import sys
import time
from pathlib import Path

import asyncpg
import numpy as np

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))


def _load_env() -> dict[str, str]:
    out: dict[str, str] = {}
    env = (ROOT / ".env").read_text().splitlines()
    for line in env:
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, _, v = line.partition("=")
        out[k.strip()] = v.strip().strip('"').strip("'")
    return out


async def fetch_embeddings(
    where_clause: str,
    pool: asyncpg.Pool,
) -> tuple[list[int], np.ndarray, list[str]]:
    """Pull (id, embedding, anchor) for all chunks matching the where clause."""
    query = f"""
        SELECT id, anchor, embedding::text AS emb
        FROM chunks
        WHERE {where_clause}
        ORDER BY id
    """
    rows = await pool.fetch(query)
    if not rows:
        raise RuntimeError(f"no chunks matched WHERE {where_clause}")
    ids: list[int] = []
    anchors: list[str] = []
    embs: list[list[float]] = []
    for r in rows:
        ids.append(r["id"])
        anchors.append(r["anchor"])
        # pgvector text format: "[v1,v2,...]"
        embs.append(ast.literal_eval(r["emb"]))
    return ids, np.asarray(embs, dtype=np.float32), anchors


async def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--where", required=True,
                   help="SQL WHERE clause (e.g. \"source_type='bare_act'\")")
    p.add_argument("--out", required=True, help="output .db path")
    p.add_argument("--table", default="chunks", help="TurboVec table name")
    p.add_argument("--dim", type=int, default=1024,
                   help="embedding dim (default 1024 for bge-m3)")
    p.add_argument("--bits", type=int, default=3,
                   help="quantization bits (1, 2, 3, 4, or 8)")
    p.add_argument("--metric", default="cosine",
                   choices=["cosine", "dot", "l2"])
    p.add_argument("--residual-qjl", action="store_true",
                   help="enable 1-bit QJL residual correction "
                        "(cosine/dot only)")
    args = p.parse_args()

    try:
        import turbovec  # noqa
    except ImportError:
        print("turbovec not installed. Run:", file=sys.stderr)
        print("  uv pip install -e /path/to/turbovec", file=sys.stderr)
        sys.exit(1)

    env = _load_env()
    dsn = (
        f"postgresql://{env['POSTGRES_USER']}:{env['POSTGRES_PASSWORD']}"
        f"@localhost:{env['POSTGRES_HOST_PORT']}/{env['POSTGRES_DB']}"
    )
    pool = await asyncpg.create_pool(dsn, min_size=1, max_size=4)
    try:
        print(f"=== mirror WHERE {args.where} → {args.out} ===")
        t0 = time.time()
        ids, embs, anchors = await fetch_embeddings(args.where, pool)
        print(f"  pulled {len(ids):,} rows in {time.time()-t0:.1f}s")
        print(f"  embeddings: shape={embs.shape}, dtype={embs.dtype}")
        norms = np.linalg.norm(embs, axis=1)
        print(f"  norms: min={norms.min():.4f}, max={norms.max():.4f}, "
              f"mean={norms.mean():.4f}")

        if embs.shape[1] != args.dim:
            print(f"  ⚠ embedding dim {embs.shape[1]} != --dim {args.dim}; "
                  f"using actual dim", file=sys.stderr)

        if os.path.exists(args.out):
            os.remove(args.out)
            print(f"  removed existing {args.out}")

        db = turbovec.connect(args.out)
        db.create_table(
            args.table,
            dim=embs.shape[1],
            bits=args.bits,
            metric=args.metric,
            residual_qjl=args.residual_qjl,
        )

        t0 = time.time()
        # Pass anchor + chunk_id as metadata so the offline client can
        # render citations without needing Postgres.
        metadata = [{"anchor": a, "pg_id": i} for i, a in zip(ids, anchors)]
        db.insert(args.table, ids=ids, embeddings=embs, metadata=metadata)
        insert_s = time.time() - t0
        print(f"  inserted {len(ids):,} in {insert_s:.1f}s "
              f"({len(ids)/insert_s:.0f}/s)")

        size_mb = os.path.getsize(args.out) / 1e6
        raw_fp16 = embs.nbytes // 2
        print(f"\n=== Size ===")
        print(f"  raw FP16:   {raw_fp16/1e6:>7.1f} MB "
              f"({raw_fp16//len(ids)} B/chunk)")
        print(f"  TurboVec:   {size_mb:>7.1f} MB "
              f"({int(size_mb*1e6//len(ids))} B/chunk)")
        print(f"  compression: {raw_fp16/(size_mb*1e6):.1f}×")
    finally:
        await pool.close()


if __name__ == "__main__":
    asyncio.run(main())
