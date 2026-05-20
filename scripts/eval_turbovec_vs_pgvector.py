#!/usr/bin/env python3
"""Measure TurboVec retrieval quality vs the pgvector dense head.

Runs N queries through both stores, reports:
  - chunk-id-level recall@K (strict — same exact chunks)
  - section-level recall@K (treats sub-chunks as equivalent)
  - top-1 exact match rate
  - per-query latency

The section-level recall is the more meaningful number for our use:
if pgvector returns `cgst-2017/sec-7-a-1` and TurboVec returns
`cgst-2017/sec-7-a-2`, that's the same Act + same section, just
different sub-chunks of the same passage. Practically equivalent.

Usage:
  PYTHONPATH=. .venv/bin/python scripts/eval_turbovec_vs_pgvector.py \\
      --db /tmp/lawrag_bare_acts.db \\
      --table bare_acts \\
      --where "source_type='bare_act'" \\
      --k 20
"""
from __future__ import annotations

import argparse
import asyncio
import re
import sys
import time
from pathlib import Path

import asyncpg
import numpy as np

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

# A handful of representative queries spanning lay phrasing, explicit Act
# references, and edge cases. Add more by editing this list — the script
# does no inference so it's cheap to expand.
DEFAULT_QUERIES = [
    "section 138 Negotiable Instruments Act dishonour of cheque",
    "Industrial Disputes Act retrenchment notice period",
    "my landlord is not returning my deposit money",
    "section 23 Senior Citizens Act transfer of property",
    "Article 21 right to life Constitution India",
    "POSH internal complaints committee composition",
    "consumer protection act online refund",
    "Hindu Succession Act daughter coparcener 2005 amendment",
    "income tax section 80C deduction",
    "RERA builder possession delay",
    "boss fired me without notice and salary",
    "my husband is beating me what can I do",
]


def _section_key(anchor: str) -> str:
    """Strip sub-chunk suffix so 'sec-7-a-1' and 'sec-7-a-2' compare equal.

    The chunker emits sub-splits like `cgst-2017/sec-7-a-1` when a section
    exceeds SECTION_MAX_TOKENS. For retrieval quality we treat all
    sub-chunks of the same section as equivalent.
    """
    base = anchor.split("#")[0]
    # Strip trailing sub-section letters and indices: sec-7-a-1 → sec-7
    m = re.match(r"(.+/sec-\d+[A-Z]*)(?:[-_].*)?", base)
    return m.group(1) if m else base


def _load_env() -> dict[str, str]:
    out: dict[str, str] = {}
    for line in (ROOT / ".env").read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, _, v = line.partition("=")
        out[k.strip()] = v.strip().strip('"').strip("'")
    return out


async def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--db", required=True, help="TurboVec .db path")
    p.add_argument("--table", default="bare_acts", help="TurboVec table")
    p.add_argument("--where", default="source_type='bare_act'",
                   help="Postgres WHERE filter (must match the mirror)")
    p.add_argument("--k", type=int, default=20, help="top-K to compare")
    p.add_argument("--queries-file", default=None,
                   help="optional file with one query per line")
    args = p.parse_args()

    queries = DEFAULT_QUERIES
    if args.queries_file:
        queries = [
            l.strip() for l in Path(args.queries_file).read_text().splitlines()
            if l.strip() and not l.strip().startswith("#")
        ]

    try:
        import turbovec
    except ImportError:
        print("turbovec not installed", file=sys.stderr)
        sys.exit(1)

    # Load embedder (must match the indexed embedder!)
    from sentence_transformers import SentenceTransformer
    embedder = SentenceTransformer("BAAI/bge-m3", device="mps")
    embedder.max_seq_length = 512

    env = _load_env()
    dsn = (
        f"postgresql://{env['POSTGRES_USER']}:{env['POSTGRES_PASSWORD']}"
        f"@localhost:{env['POSTGRES_HOST_PORT']}/{env['POSTGRES_DB']}"
    )
    conn = await asyncpg.connect(dsn)
    db = turbovec.connect(args.db)

    K = args.k
    print(f"=== TurboVec vs pgvector (top-{K}, {len(queries)} queries) ===")
    print(f"  TurboVec DB:  {args.db}")
    print(f"  Postgres WHERE: {args.where}")
    print()

    rec_id_sum = 0.0
    rec_sec_sum = 0.0
    top1_match = 0
    pg_ms_total = 0.0
    tv_ms_total = 0.0

    print(f"{'query':<53} {'pg ms':>6} {'tv ms':>6} {'id@K':>6} {'sec@5':>6}")
    print("-" * 88)
    for q in queries:
        qv = embedder.encode(
            [q], normalize_embeddings=True, convert_to_numpy=True,
        )[0].astype(np.float32)
        emb_str = "[" + ",".join(f"{x:.7f}" for x in qv) + "]"

        # pgvector ground truth (HNSW approximate, but high recall vs brute)
        t0 = time.time()
        pg_rows = await conn.fetch(
            f"SELECT id, anchor FROM chunks WHERE {args.where} "
            f"ORDER BY embedding <=> $1::halfvec LIMIT {K}",
            emb_str,
        )
        pg_ms = (time.time() - t0) * 1000
        pg_ms_total += pg_ms
        pg_ids = [r["id"] for r in pg_rows]
        pg_anchors = [r["anchor"] for r in pg_rows]

        # TurboVec
        t0 = time.time()
        tv_results = db.search(args.table, qv, top_k=K)
        tv_ms = (time.time() - t0) * 1000
        tv_ms_total += tv_ms
        tv_ids = [r.id for r in tv_results]

        # Pull anchors for the TurboVec ids to compute section-level recall
        tv_rows = await conn.fetch(
            "SELECT id, anchor FROM chunks WHERE id = ANY($1::bigint[])",
            tv_ids,
        )
        anchor_by_id = {r["id"]: r["anchor"] for r in tv_rows}
        tv_anchors = [anchor_by_id.get(i, "") for i in tv_ids]

        # Metrics
        id_overlap = len(set(pg_ids) & set(tv_ids)) / K
        # Section-level: limit to top-5 because that's what the user actually sees
        N_sec = min(5, K)
        pg_secs = {_section_key(a) for a in pg_anchors[:N_sec]}
        tv_secs = {_section_key(a) for a in tv_anchors[:N_sec]}
        sec_overlap = len(pg_secs & tv_secs) / N_sec
        if pg_ids and tv_ids and pg_ids[0] == tv_ids[0]:
            top1_match += 1

        rec_id_sum += id_overlap
        rec_sec_sum += sec_overlap

        qshort = q[:50] + ("…" if len(q) > 50 else "")
        print(f"{qshort:<53} {pg_ms:>6.0f} {tv_ms:>6.0f} "
              f"{id_overlap*100:>5.0f}% {sec_overlap*100:>5.0f}%")

    n = len(queries)
    print()
    print(f"=== Summary ===")
    print(f"  chunk-id recall@{K} (strict):          "
          f"{100*rec_id_sum/n:>5.1f}%")
    print(f"  section-level recall@5 (semantic):    "
          f"{100*rec_sec_sum/n:>5.1f}%")
    print(f"  top-1 exact ID match:                  "
          f"{top1_match}/{n} ({100*top1_match/n:.0f}%)")
    print(f"  avg pgvector latency:                  "
          f"{pg_ms_total/n:>5.0f} ms")
    print(f"  avg TurboVec latency:                  "
          f"{tv_ms_total/n:>5.0f} ms")

    await conn.close()


if __name__ == "__main__":
    asyncio.run(main())
