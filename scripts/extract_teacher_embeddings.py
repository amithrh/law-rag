#!/usr/bin/env python3
"""Pre-extract teacher (bge-m3) embeddings for Stage 4 distillation.

Stratified sample 100K chunks: 10K bare_act + 60K sc_judgment + 30K hc_judgment.

Why stratify this way:
  - bare_act has only ~11.6K total chunks, so we cap at 10K (~86%)
  - sc_judgment dominates the corpus (473K); 60K is enough diversity without
    over-weighting the student to caselaw style
  - hc_judgment (256K) gets 30K — same logic, want geographic/court diversity

Output:
  data/training/teacher_emb_100k.npy   — float32, shape (N, 1024)
  data/training/teacher_emb_100k.jsonl — {id, text, source_type} per row,
                                          aligned to .npy by index

Wall: ~3-5 min on M4 Max (DB-bound, no GPU).
"""
from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

import numpy as np

from apps.api.db import get_pool

ROOT = Path(__file__).parent.parent
OUT_DIR = ROOT / "data/training"
OUT_DIR.mkdir(exist_ok=True, parents=True)

SAMPLE_SIZES = {
    "bare_act": 10_000,
    "sc_judgment": 60_000,
    "hc_judgment": 30_000,
}
SEED = 42  # baked into md5 hash for stable sampling


def parse_halfvec(s: str) -> np.ndarray:
    """halfvec ascii form '[a,b,c,...]' → float32 numpy array."""
    return np.fromstring(s.strip().lstrip("[").rstrip("]"), sep=",", dtype=np.float32)


async def main() -> None:
    pool = await get_pool()
    text_rows: list[dict] = []
    emb_rows: list[np.ndarray] = []

    async with pool.acquire() as c:
        for stype, n in SAMPLE_SIZES.items():
            print(f"=== sampling {n:,} of {stype} ===", flush=True)
            # Stable random sample via md5 hash of (id || seed). 'embedding' must
            # be non-null and not quarantined.
            rows = await c.fetch(
                f"""
                SELECT ch.id, ch.text, ch.embedding::text AS emb_str
                FROM chunks ch
                WHERE ch.source_type = $1
                  AND ch.embedding IS NOT NULL
                  AND ch.quarantined = false
                ORDER BY md5(ch.id::text || '{SEED}')
                LIMIT $2
                """,
                stype,
                n,
            )
            print(f"   fetched {len(rows):,} rows", flush=True)
            n_bad = 0
            for r in rows:
                v = parse_halfvec(r["emb_str"])
                if v.shape[0] != 1024:
                    n_bad += 1
                    continue
                emb_rows.append(v)
                text_rows.append(
                    {"id": str(r["id"]), "text": r["text"], "source_type": stype}
                )
            if n_bad:
                print(f"   skipped {n_bad} malformed embeddings", flush=True)

    n_total = len(emb_rows)
    arr = np.stack(emb_rows)
    print(
        f"\nTotal usable: {n_total:,} rows, dtype={arr.dtype}, shape={arr.shape}",
        flush=True,
    )

    npy_path = OUT_DIR / "teacher_emb_100k.npy"
    jsonl_path = OUT_DIR / "teacher_emb_100k.jsonl"
    np.save(npy_path, arr)
    with jsonl_path.open("w") as f:
        for r in text_rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    print(f"\n  wrote {npy_path}  ({arr.nbytes / 1e6:.1f} MB)")
    print(f"  wrote {jsonl_path}")


if __name__ == "__main__":
    asyncio.run(main())
