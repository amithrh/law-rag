#!/usr/bin/env python3
"""Synthetic-triple miner — use a local LLM (qwen3:32b) as teacher to generate
(lay_query, positive_passage, hard_negative_passage) triples from our corpus.

Why this exists (May 23, 2026):
  The 500-query honest eval showed 16.8% truly-clean answers. Root cause is
  not the retrieval pipeline (RRF, sparse, rerank, expander dictionary) but
  the fact that none of our models have ever been trained on Indian legal
  text. We have 8K SC mined triples but only 2.5K survive filtering. That's
  too small for embedder DAPT and barely enough for a reranker fine-tune.

  Goal: 50K high-quality (lay_query, positive, hard_negative) triples,
  generated 100% locally via ollama (no paid APIs). These triples feed:
    - Stage 3 reranker fine-tune (current 2.5K → 50K)
    - Stage 4 embedder DAPT (continued pretraining of bge-m3)

Approach:
  Phase A — bare-Act chunks (13K, prioritized):
    For each bare-Act section chunk in DB, prompt qwen3:32b to imagine the
    real-world Indian legal-aid user whose problem THIS section answers, and
    generate ONE lay-phrase question. Hard negative = chunk from same
    subject_area but different slug (same domain, wrong Act).

  Phase B — SC paragraphs (50K sample):
    Similar approach but framed as "imagine the disputant who'd benefit from
    THIS judgment paragraph". Hard negative = paragraph from different SC
    case.

Quality bar (sampled checks before full run):
  - Query mentions city/state/amount/relationship (specific, not generic)
  - Query in 8-25 words, broken-English / Hindi-English mix OK
  - Query does NOT mention Act name or section number (we want LAY phrases)
  - Hard negative is from same subject_area (close-but-wrong)

Output format (one JSON per line):
  {"query": ..., "positive_chunk_id": ..., "positive_text": ...,
   "positive_anchor": ..., "negative_chunk_id": ..., "negative_text": ...,
   "negative_anchor": ..., "subject_area": ..., "source_type": ...,
   "teacher_model": "qwen3:32b"}

Wall budget (M4 Max, ollama qwen3:32b, concurrency=4):
  Phase A bare-Act (13K chunks): ~2-3h
  Phase B SC paragraphs (50K):   ~10-14h
  Total: ~12-17h, designed to run unattended overnight.

Usage:
  # smoke test (10 queries)
  PYTHONPATH=. .venv/bin/python scripts/mine_synthetic_triples.py \\
      --source-type bare_act --limit 10

  # full Phase A
  PYTHONPATH=. .venv/bin/python scripts/mine_synthetic_triples.py \\
      --source-type bare_act --concurrency 4

  # Phase B
  PYTHONPATH=. .venv/bin/python scripts/mine_synthetic_triples.py \\
      --source-type sc_judgment --limit 50000 --concurrency 4
"""
from __future__ import annotations

import argparse
import asyncio
import json
import random
import sys
import time
from datetime import datetime
from pathlib import Path

from apps.api.db import get_pool
from apps.api.llm import chat_once

ROOT = Path(__file__).parent.parent
TRAINING_DIR = ROOT / "data/training"
TRAINING_DIR.mkdir(parents=True, exist_ok=True)

# Default teacher — qwen3:32b is the strongest local model that fits memory.
# Falls back to qwen3:14b if 32b unavailable.
DEFAULT_MODEL = "qwen3:32b"
SEED = 42


# ---------------------------------------------------------------------------
# Prompts — DESIGNED FOR LAY-USER VOICE, not legal vocabulary
# ---------------------------------------------------------------------------

_SYSTEM_PROMPT_BARE_ACT = (
    "You are simulating an Indian legal-aid client — someone who walks into "
    "a DLSA / Lok Adalat / paralegal volunteer asking about their problem. "
    "You will be given a section from an Indian Act. Your job: generate ONE "
    "realistic lay-phrase question that this section directly answers.\n\n"

    "The question MUST:\n"
    "1. Sound like a real Indian user — broken English, Hindi-English mix "
    "  ('papa', 'thekedar', 'munshi', 'thana', 'tehsildar'), regional terms\n"
    "2. Mention SPECIFIC circumstances — a city/state, an amount in rupees, "
    "  a relationship ('mother in lucknow', 'son in bangalore', '40000'), "
    "  or a workplace / contractor name\n"
    "3. NOT mention the Act name explicitly (no 'under MWP Act', no 'section "
    "  138 NI Act'). The whole point of training is to learn lay→legal "
    "  mapping; if you include the Act name, you defeat the purpose.\n"
    "4. Be 8-25 words long\n"
    "5. Be specific enough that THIS section is clearly the answer\n\n"

    "EXAMPLES of the format:\n\n"
    "[Section: 138 NI Act on cheque bouncing]\n"
    "  → boss gave me cheque 80000 bounced 3 times now blocking calls bangalore "
    "what to do\n\n"
    "[Section: 437 CrPC on regular bail by magistrate]\n"
    "  → my brother arrested theft yesterday tihar how to apply bail "
    "magistrate court\n\n"
    "[Section: 5 MWP Act on senior-citizens tribunal]\n"
    "  → mother in lucknow 68 years son not paying maintenance where to file "
    "tribunal procedure\n\n"
    "[Section: 6 HSA on daughter coparcener]\n"
    "  → as a daughter am i entitled to ancestral land father died 2003 "
    "before amendment\n\n"
    "[Section: 187 BNSS on default bail]\n"
    "  → brother in jail 6 months no chargesheet ipc 420 cheating when "
    "automatic bail\n\n"

    "OUTPUT FORMAT: ONLY the lay question, one line, no quotes, no preamble, "
    "no 'Question:' prefix. If the section is procedural metadata (like 'short "
    "title and extent', schedule headers, definitions only), output: SKIP\n"
)


_SYSTEM_PROMPT_SC_PARA = (
    "You are simulating an Indian legal-aid client. You will be given a "
    "paragraph from an Indian Supreme Court judgment. Your job: generate "
    "ONE realistic lay-phrase question that this paragraph could help "
    "answer.\n\n"

    "Same rules as before:\n"
    "1. Real Indian user voice, broken English / Hindi-English mix\n"
    "2. SPECIFIC circumstances — city, amount, relationship, workplace\n"
    "3. NOT mention the case name or Act citation\n"
    "4. 8-25 words\n"
    "5. The paragraph must clearly help answer the question — if the "
    "paragraph is just procedural (case header, arrangement of arguments, "
    "history of the appeal), output: SKIP\n\n"

    "OUTPUT: ONLY the lay question, one line.\n"
)


# ---------------------------------------------------------------------------
# DB sampling
# ---------------------------------------------------------------------------


async def fetch_candidates(
    pool, source_type: str, limit: int | None
) -> list[dict]:
    """Sample chunks to generate queries for. Stable order via md5 hash."""
    async with pool.acquire() as c:
        # We want non-quarantined, non-trivial chunks (>=120 chars) with
        # embedding already present. For bare-act, skip #header anchors
        # since those are TOC / front-matter.
        sql = """
            SELECT ch.id, ch.text, ch.anchor, ch.subject_area, ch.source_type,
                   d.title AS doc_title
            FROM chunks ch
            JOIN documents d ON d.id = ch.document_id
            WHERE ch.source_type = $1
              AND ch.quarantined = false
              AND char_length(ch.text) BETWEEN 120 AND 2500
              AND ch.embedding IS NOT NULL
              AND ch.anchor NOT LIKE '%#header%'
            ORDER BY md5(ch.id::text || '42')
        """
        if limit:
            sql += f" LIMIT {int(limit)}"
        rows = await c.fetch(sql, source_type)
        return [dict(r) for r in rows]


async def sample_hard_negative(
    pool,
    *,
    positive_chunk_id,
    subject_area: str,
    source_type: str,
    positive_slug: str | None,
    seed_salt: str,
) -> dict | None:
    """Sample a hard negative: same subject_area, DIFFERENT slug if bare_act,
    or DIFFERENT document if SC."""
    async with pool.acquire() as c:
        if source_type == "bare_act":
            # Same subject_area, different bare-act slug
            row = await c.fetchrow(
                """
                SELECT ch.id, ch.text, ch.anchor
                FROM chunks ch
                WHERE ch.source_type = 'bare_act'
                  AND ch.subject_area = $1
                  AND ch.id != $2
                  AND split_part(ch.anchor, '/', 1) != $3
                  AND ch.quarantined = false
                  AND char_length(ch.text) BETWEEN 120 AND 2500
                  AND ch.anchor NOT LIKE '%#header%'
                ORDER BY md5(ch.id::text || $4)
                LIMIT 1
                """,
                subject_area, positive_chunk_id, positive_slug or "",
                seed_salt,
            )
        else:
            # SC: different document
            row = await c.fetchrow(
                """
                SELECT ch.id, ch.text, ch.anchor
                FROM chunks ch
                JOIN documents d ON d.id = ch.document_id
                WHERE ch.source_type = $1
                  AND ch.subject_area = $2
                  AND ch.document_id != (
                      SELECT document_id FROM chunks WHERE id = $3
                  )
                  AND ch.quarantined = false
                  AND char_length(ch.text) BETWEEN 120 AND 2500
                ORDER BY md5(ch.id::text || $4)
                LIMIT 1
                """,
                source_type, subject_area, positive_chunk_id, seed_salt,
            )
        return dict(row) if row else None


# ---------------------------------------------------------------------------
# Generation
# ---------------------------------------------------------------------------


async def generate_query(
    positive_text: str,
    *,
    source_type: str,
    model: str,
    timeout_s: int = 90,
) -> str | None:
    """Ask the teacher LLM to produce one lay-phrase query for this passage."""
    if source_type == "bare_act":
        sys_p = _SYSTEM_PROMPT_BARE_ACT
    else:
        sys_p = _SYSTEM_PROMPT_SC_PARA

    # qwen3 sometimes wraps think tags even with think:false — we strip
    # post-hoc just in case.
    messages = [
        {"role": "system", "content": sys_p},
        {"role": "user", "content": f"Passage:\n{positive_text[:1500]}"},
    ]
    try:
        out = await asyncio.wait_for(
            chat_once(messages, model=model, temperature=0.7, max_tokens=80),
            timeout=timeout_s,
        )
    except (asyncio.TimeoutError, Exception):
        return None
    out = out.strip()
    # strip <think>...</think> blocks
    import re
    out = re.sub(r"<think>.*?</think>", "", out, flags=re.DOTALL).strip()
    if not out or out.upper().strip(".:!").endswith("SKIP"):
        return None
    # Take first line only
    out = out.split("\n", 1)[0].strip()
    out = out.strip('"').strip("'").strip()
    # Sanity gates
    if len(out) < 12 or len(out) > 300:
        return None
    # Reject obvious Act-name mentions (defeats the lay→legal training)
    blacklist = ("Act 19", "Act 20", "section ", "Section ", "Sec.", "s. ",
                 "IPC", "CrPC", "IEA", "BNS", "BNSS", "BSA")
    # allow IT (Information Technology) but reject IPC/CrPC/etc.
    hits = sum(1 for b in blacklist if b in out)
    if hits >= 2:  # too legalese
        return None
    return out


# ---------------------------------------------------------------------------
# Main loop
# ---------------------------------------------------------------------------


async def process_one(
    pool, row: dict, *, source_type: str, model: str, seed: int,
) -> dict | None:
    """Generate one triple from one positive chunk."""
    pos_text = row["text"]
    pos_id = row["id"]
    subj = row["subject_area"] or "civil_general"
    anchor = row["anchor"] or ""
    pos_slug = anchor.split("/", 1)[0] if "/" in anchor else None

    query = await generate_query(
        pos_text, source_type=source_type, model=model,
    )
    if not query:
        return None

    neg = await sample_hard_negative(
        pool,
        positive_chunk_id=pos_id,
        subject_area=subj,
        source_type=source_type,
        positive_slug=pos_slug,
        seed_salt=f"{seed}-{pos_id}",
    )
    if not neg:
        return None

    return {
        "query": query,
        "positive_chunk_id": str(pos_id),
        "positive_text": pos_text,
        "positive_anchor": anchor,
        "negative_chunk_id": str(neg["id"]),
        "negative_text": neg["text"],
        "negative_anchor": neg["anchor"],
        "subject_area": subj,
        "source_type": source_type,
        "teacher_model": model,
    }


async def worker(
    pool,
    in_queue: asyncio.Queue,
    out_queue: asyncio.Queue,
    *,
    source_type: str,
    model: str,
    seed: int,
) -> None:
    while True:
        row = await in_queue.get()
        if row is None:
            in_queue.task_done()
            break
        try:
            triple = await process_one(
                pool, row, source_type=source_type, model=model, seed=seed,
            )
        except Exception as e:
            triple = {"_error": str(e), "_chunk_id": str(row.get("id"))}
        await out_queue.put(triple)
        in_queue.task_done()


async def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--source-type", choices=("bare_act", "sc_judgment", "hc_judgment"),
                   default="bare_act")
    p.add_argument("--limit", type=int, default=None,
                   help="cap total chunks to process")
    p.add_argument("--concurrency", type=int, default=4,
                   help="parallel ollama calls")
    p.add_argument("--model", default=DEFAULT_MODEL)
    p.add_argument("--out", default=None,
                   help="output JSONL path (default: data/training/"
                        "synthetic_triples_<source>_<ts>.jsonl)")
    p.add_argument("--resume", default=None,
                   help="existing JSONL to skip already-processed chunks "
                        "(by positive_chunk_id)")
    args = p.parse_args()

    out_path = (Path(args.out) if args.out else
                TRAINING_DIR / f"synthetic_triples_{args.source_type}_"
                f"{datetime.now().strftime('%Y%m%d_%H%M%S')}.jsonl")
    out_path.parent.mkdir(parents=True, exist_ok=True)

    pool = await get_pool()
    candidates = await fetch_candidates(pool, args.source_type, args.limit)
    print(f"loaded {len(candidates):,} candidate chunks "
          f"(source_type={args.source_type})", flush=True)

    # Resume: skip already-done chunk_ids
    done_ids: set[str] = set()
    if args.resume:
        rf = Path(args.resume)
        if rf.exists():
            with rf.open() as f:
                for line in f:
                    try:
                        done_ids.add(json.loads(line)["positive_chunk_id"])
                    except Exception:
                        pass
            candidates = [c for c in candidates if str(c["id"]) not in done_ids]
            print(f"resume: skipped {len(done_ids):,}; "
                  f"remaining {len(candidates):,}", flush=True)
            # Append mode if resume; new file otherwise
            file_mode = "a"
        else:
            file_mode = "w"
    else:
        file_mode = "w"

    in_q: asyncio.Queue = asyncio.Queue(maxsize=args.concurrency * 4)
    out_q: asyncio.Queue = asyncio.Queue()

    workers = [
        asyncio.create_task(
            worker(pool, in_q, out_q,
                   source_type=args.source_type,
                   model=args.model, seed=SEED),
        )
        for _ in range(args.concurrency)
    ]

    async def producer():
        for r in candidates:
            await in_q.put(r)
        for _ in range(args.concurrency):
            await in_q.put(None)

    asyncio.create_task(producer())

    t0 = time.time()
    n_written = 0
    n_skipped = 0
    n_errors = 0
    with out_path.open(file_mode) as f:
        for i in range(len(candidates)):
            triple = await out_q.get()
            if triple is None:
                continue
            if "_error" in triple:
                n_errors += 1
                continue
            if triple is None:
                n_skipped += 1
                continue
            f.write(json.dumps(triple, ensure_ascii=False) + "\n")
            f.flush()
            n_written += 1
            if n_written % 25 == 0:
                elapsed = time.time() - t0
                rate = (i + 1) / elapsed if elapsed else 0
                remaining_s = (len(candidates) - i - 1) / rate if rate else 0
                print(f"  [{i+1:>5}/{len(candidates):>5}] "
                      f"written={n_written:>5} skip={n_skipped:>3} "
                      f"err={n_errors:>3}  {rate:.2f}/s  "
                      f"ETA={remaining_s/60:.1f}min  q={triple['query'][:60]!r}",
                      flush=True)

    for w in workers:
        w.cancel()
    elapsed = (time.time() - t0) / 60
    print(f"\n=== done in {elapsed:.1f} min ===")
    print(f"  written: {n_written}")
    print(f"  skipped: {n_skipped}  (teacher said SKIP or sanity-rejected)")
    print(f"  errors : {n_errors}")
    print(f"  output : {out_path}")


if __name__ == "__main__":
    asyncio.run(main())
