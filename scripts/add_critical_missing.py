#!/usr/bin/env python3
"""Wave-2 critical-missing-acts ingest — fast path, cached PDFs only.

Why this exists (May 23, 2026):
  The 500-query eval audit (data/processed/eval_500_REAL_ISSUES.md) found
  62.5% retrieval_miss across personas. Root cause: critical Acts whose
  full bare-Act PDFs were cached in data/raw/acts/ but never DB-inserted
  because tasks #14/#15 were marked complete prematurely. Re-running
  add_p0_batch.py wastes ~10 min trying to re-fetch the 77 wave-1
  handle-based entries (IndiaCode now returning 404s for handles), then
  reaching the cached_pdf entries.

  This script trims to the cached wave-2 entries only.

  Same chunk + embed + insert path as add_p0_batch.py — imports the
  pipeline functions directly to avoid duplication.

Wave-2 entries:
  - Bharatiya Nyaya Sanhita 2023        (BNS — replaces IPC 1860)
  - Bharatiya Nagarik Suraksha Sanhita 2023  (BNSS — replaces CrPC 1973)
  - Bharatiya Sakshya Adhiniyam 2023    (BSA — replaces IEA 1872)
  - Maintenance & Welfare of Parents 2007 (MWP — elder care)
  - Code on Wages 2019                  (wages consolidation)
  - Motor Vehicles Act 1988             (gig-economy / accidents)
  - Payment of Gratuity Act 1972        (retirement benefit)
  - Code of Criminal Procedure 1973     (legacy criminal procedure)
  - Street Vendors Act 2014             (municipal seizure / vending)
  - Forest Rights Act 2006              (tribal forest rights)
  - PESA Act 1996                       (Scheduled Area gram sabha consent)
  - MGNREGA Act 2005                    (job-card / wage-delay claims)
  - BOCW Act 1996                       (construction worker welfare)

Usage:
  PYTHONPATH=. .venv/bin/python scripts/add_critical_missing.py
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import sys
from datetime import date
from pathlib import Path

import numpy as np
import pymupdf
from sentence_transformers import SentenceTransformer

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT / "packages"))
from chunking.act import chunk_act  # noqa: E402
from ingest.adapters.base import infer_subject_area  # noqa: E402
from ingest.normalize.redact import redact  # noqa: E402

# Use the production pool helper so DSN comes from the same place /answer uses
from apps.api.db import get_pool  # noqa: E402


# ---------------------------------------------------------------------
# Wave-2 batch (cached_pdf entries only). pymupdf-verified valid Acts —
# see data/processed/eval_500_REAL_ISSUES.md for the audit trail.
# ---------------------------------------------------------------------
WAVE2 = [
    {"slug": "bns-2023",
     "title": "Bharatiya Nyaya Sanhita 2023",
     "cached_pdf": "data/raw/acts/bns-2023__a202345.pdf",
     "subject_area": "criminal",
     "as_at": "2024-07-01"},
    {"slug": "bnss-2023",
     "title": "Bharatiya Nagarik Suraksha Sanhita 2023",
     "cached_pdf": "data/raw/acts/bnss-2023__eng.pdf",
     "subject_area": "criminal",
     "as_at": "2024-07-01"},
    {"slug": "bsa-2023",
     "title": "Bharatiya Sakshya Adhiniyam 2023",
     "cached_pdf": "data/raw/acts/sakshya-adhiniyam-2023__aa202347.pdf",
     "subject_area": "criminal",
     "as_at": "2024-07-01"},
    {"slug": "mwp-2007",
     "title": "Maintenance and Welfare of Parents and Senior Citizens "
              "Act 2007",
     "cached_pdf": "data/raw/acts/senior-citizens-2007__200756.pdf",
     "subject_area": "family"},
    {"slug": "code-on-wages-2019",
     "title": "Code on Wages 2019",
     "cached_pdf": "data/raw/acts/code-on-wages-2019__aA2019-29.pdf",
     "subject_area": "service_employment",
     "as_at": "2019-08-08"},
    {"slug": "motor-vehicles-1988",
     "title": "Motor Vehicles Act 1988",
     "cached_pdf": "data/raw/acts/motor-vehicles-1988__aA1988-59.pdf",
     "subject_area": "civil_general"},
    {"slug": "gratuity-1972",
     "title": "Payment of Gratuity Act 1972",
     "cached_pdf": "data/raw/acts/gratuity-1972__a1972-39.pdf",
     "subject_area": "service_employment"},
    {"slug": "crpc-1973",
     "title": "Code of Criminal Procedure 1973",
     "cached_pdf": "data/raw/acts/crpc-1973__ccp1973.pdf",
     "pdf_url": "https://www.indiacode.nic.in/bitstream/123456789/6796/1/ccp1973.pdf",
     "subject_area": "criminal",
     "as_at": "1974-04-01"},
    {"slug": "street-vendors-2014",
     "title": "Street Vendors (Protection of Livelihood and Regulation of Street Vending) Act 2014",
     "cached_pdf": "data/raw/acts/street-vendors-2014__a2014-07.pdf",
     "pdf_url": "https://www.indiacode.nic.in/bitstream/123456789/2124/1/a2014-07.pdf",
     "subject_area": "civil_general",
     "as_at": "2014-03-04"},
    {"slug": "fra-2006",
     "title": "Scheduled Tribes and Other Traditional Forest Dwellers (Recognition of Forest Rights) Act 2006",
     "cached_pdf": "data/raw/acts/fra-2006__a2007-02.pdf",
     "pdf_url": "https://www.indiacode.nic.in/bitstream/123456789/8311/1/a2007-02.pdf",
     "subject_area": "tribal_caste",
     "as_at": "2007-01-01"},
    {"slug": "pesa-1996",
     "title": "Panchayats (Extension to the Scheduled Areas) Act 1996",
     "cached_pdf": "data/raw/acts/pesa-1996__A1996-40.pdf",
     "pdf_url": "https://www.indiacode.nic.in/bitstream/123456789/1973/1/A1996-40.pdf",
     "subject_area": "tribal_caste",
     "as_at": "1996-12-24"},
    {"slug": "mgnrega-2005",
     "title": "Mahatma Gandhi National Rural Employment Guarantee Act 2005",
     "cached_pdf": "data/raw/acts/mgnrega-2005__the_mahatma_gandhi_national_rural_employment_guarantee_act_2005.pdf",
     "pdf_url": "https://www.indiacode.nic.in/bitstream/123456789/6930/1/the_mahatma_gandhi_national_rural_employment_guarantee_act%2C_2005.pdf",
     "subject_area": "service_employment",
     "as_at": "2005-09-05"},
    {"slug": "bocw-1996",
     "title": "Building and Other Construction Workers (Regulation of Employment and Conditions of Service) Act 1996",
     "cached_pdf": "data/raw/acts/bocw-1996__building-and-other-construction-workers-act-1996.pdf",
     "pdf_url": "https://www.indiacode.nic.in/bitstream/123456789/9608/1/building-and-other-construction-workers-act-1996.pdf",
     "subject_area": "service_employment",
     "as_at": "1996-08-19"},
]

EMBEDDING_MODEL = "BAAI/bge-m3"


def parse_pdf(path: Path) -> tuple[str, int]:
    """Extract concatenated text from a PDF. Returns (text, n_pages)."""
    doc = pymupdf.open(str(path))
    n_pages = doc.page_count
    text = "\n\n".join(p.get_text("text") for p in doc)
    doc.close()
    return text, n_pages


def _registry_row(row: dict) -> dict:
    pdf_local = row["pdf_local"]
    return {
        "slug": row["slug"],
        "title": row["title"],
        "handle_id": row.get("handle_id", ""),
        "handle_url": row.get("handle_url", ""),
        "pdf_url": row.get("pdf_url") or f"file://{pdf_local}",
        "pdf_local": pdf_local,
        "pdf_pages": row["n_pages"],
        "pdf_bytes": row["pdf_bytes"],
        "text_chars": row["text_chars"],
        "text_sha256": row["text_sha256"],
        "pii_hits": row["pii_hits"],
        "subject_area_hint": row.get("subject_area"),
        "as_at": row.get("as_at"),
    }


def append_missing_acts_registry_rows(rows: list[dict]) -> int:
    """Append parsed Act metadata to data/processed/acts.jsonl if absent.

    The data directory is ignored in git, but local evaluation and corpus
    audits use this registry to decide whether a source-pack doc is genuinely
    available. Keep it in sync with DB ingest without duplicating slugs.
    """
    out_jsonl = ROOT / "data" / "processed" / "acts.jsonl"
    out_jsonl.parent.mkdir(parents=True, exist_ok=True)
    seen: set[str] = set()
    if out_jsonl.exists():
        with out_jsonl.open() as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    data = json.loads(line)
                except json.JSONDecodeError:
                    continue
                slug = data.get("slug")
                if isinstance(slug, str):
                    seen.add(slug)

    new_rows = [r for r in rows if r["slug"] not in seen]
    if not new_rows:
        return 0
    with out_jsonl.open("a") as f:
        for row in new_rows:
            f.write(json.dumps(_registry_row(row), ensure_ascii=False) + "\n")
    return len(new_rows)


async def existing_chunk_counts(pool, slugs: list[str]) -> dict[str, int]:
    if not slugs:
        return {}
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT d.doc_id, count(c.id)::int AS n_chunks
            FROM documents d
            LEFT JOIN chunks c ON c.document_id = d.id
            WHERE d.doc_id = ANY($1::text[])
            GROUP BY d.doc_id
            """,
            slugs,
        )
    return {row["doc_id"]: int(row["n_chunks"]) for row in rows}


async def main() -> None:
    print(f"=== Wave-2 critical-missing-acts ingest ({len(WAVE2)} acts) ===")

    # Step 1: parse all PDFs
    print("\nStep 1: parse + redact")
    parsed = []
    for entry in WAVE2:
        slug = entry["slug"]
        pdf = ROOT / entry["cached_pdf"]
        if not pdf.exists():
            print(f"  ✗ {slug}: cached_pdf not found at {pdf}")
            continue
        try:
            text, n_pages = parse_pdf(pdf)
        except Exception as e:
            print(f"  ✗ {slug}: parse failed — {e}")
            continue
        red = redact(text)
        pdf_bytes = pdf.stat().st_size
        parsed.append({
            **entry,
            "pdf_local": str(pdf),
            "n_pages": n_pages,
            "pdf_bytes": pdf_bytes,
            "text_chars": len(red.text),
            "text_sha256": hashlib.sha256(red.text.encode("utf-8")).hexdigest()[:16],
            "pii_hits": len([h for h in red.hits if h.confidence > 0]),
            "text": red.text,
        })
        print(f"  ✓ {slug}: pages={n_pages}, chars={len(red.text):,}")

    if not parsed:
        print("\nNothing to ingest — exiting.")
        return

    added_registry_rows = append_missing_acts_registry_rows(parsed)
    print(f"\nRegistry: appended {added_registry_rows} missing rows to data/processed/acts.jsonl")

    pool = await get_pool()
    counts = await existing_chunk_counts(pool, [r["slug"] for r in parsed])
    to_ingest = []
    for r in parsed:
        n_chunks = counts.get(r["slug"], 0)
        if n_chunks > 0:
            print(f"  - {r['slug']}: already has {n_chunks} chunks — skipping embed/insert")
            continue
        to_ingest.append(r)

    if not to_ingest:
        print("\n=== Done ===")
        print("  new documents : 0")
        print("  reused orphan : 0")
        print("  chunks inserted: 0")
        print("  Note: run backfill_sparse_embeddings.py next for sparse vectors.")
        return

    # Step 2: chunk all
    print("\nStep 2: chunk")
    all_chunks: list[tuple[dict, object]] = []
    for r in to_ingest:
        as_at_val = r.get("as_at")
        if isinstance(as_at_val, str) and as_at_val:
            try:
                as_at_val = date.fromisoformat(as_at_val)
            except ValueError:
                as_at_val = None
        chunks = list(chunk_act(
            slug=r["slug"],
            text=r["text"],
            act_title=r["title"],
            as_at=as_at_val,
        ))
        for c in chunks:
            all_chunks.append((r, c))
        print(f"  {r['slug']}: {len(chunks)} chunks")
    total = len(all_chunks)
    print(f"  total chunks: {total}")

    # Step 3: embed (single batched pass, FP16-friendly bge-m3 on MPS)
    print("\nStep 3: embed (this loads bge-m3 if not already in memory)")
    model = SentenceTransformer(EMBEDDING_MODEL, device="mps")
    texts = [c.text for _, c in all_chunks]
    embeddings = model.encode(
        texts, batch_size=16, show_progress_bar=True,
        convert_to_numpy=True, normalize_embeddings=True,
    )
    print(f"  embedded {embeddings.shape}")

    # Step 4: insert
    print("\nStep 4: insert")
    new_docs = 0
    reused_docs = 0
    inserted_total = 0
    async with pool.acquire() as conn:
        for r in parsed:
            slug = r["slug"]

            # Idempotency: skip if document exists AND has chunks
            existing = await conn.fetchrow(
                """
                SELECT d.id AS doc_pk, count(c.id) AS n_chunks
                FROM documents d
                LEFT JOIN chunks c ON c.document_id = d.id
                WHERE d.doc_id = $1
                GROUP BY d.id
                """, slug,
            )
            if existing and existing["n_chunks"] > 0:
                print(f"  - {slug}: already has {existing['n_chunks']} chunks "
                      f"— skipping")
                continue

            # subject area: hint > inferred
            subj = (r.get("subject_area")
                    or infer_subject_area(r["title"], r["text"][:500]).value)

            # source row — synthesize a 'cached_pdf' source
            url = f"file://{r['pdf_local']}"
            url_hash = hashlib.sha256(url.encode()).hexdigest()
            src_id = await conn.fetchval(
                """
                INSERT INTO sources (origin, source_type, url,
                                     canonical_url_hash, provenance_tier)
                VALUES ('indiacode', 'bare_act', $1, $2, 1)
                ON CONFLICT (canonical_url_hash) DO UPDATE SET origin=EXCLUDED.origin
                RETURNING id
                """, url, url_hash,
            )

            # document
            year = None
            for tok in r["title"].split():
                if tok.isdigit() and len(tok) == 4 and 1850 <= int(tok) <= 2030:
                    year = int(tok)
                    break
            as_at_raw = r.get("as_at") or (f"{year}-01-01" if year else None)
            as_at_str: date | None = None
            if as_at_raw:
                try:
                    as_at_str = date.fromisoformat(as_at_raw)
                except (ValueError, TypeError):
                    as_at_str = None
            doc_pk = existing["doc_pk"] if existing else await conn.fetchval(
                """
                INSERT INTO documents (source_id, doc_id, title, statute_short,
                                       statute_year, as_at, subject_area, metadata)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
                ON CONFLICT (doc_id) DO UPDATE SET title=EXCLUDED.title
                RETURNING id
                """,
                src_id, slug, r["title"], r["title"], year, as_at_str, subj,
                json.dumps({"source": "wave2", "cached_pdf": r["pdf_local"]}),
            )
            if existing:
                reused_docs += 1
            else:
                new_docs += 1

            # chunks — find embeddings for this slug
            global_indices = [
                i for i, (rr, _) in enumerate(all_chunks) if rr["slug"] == slug
            ]
            chunk_to_global = {id(all_chunks[gi][1]): gi for gi in global_indices}

            seen_anchors = set()
            inserted = 0
            for c in (cc for rr, cc in all_chunks if rr["slug"] == slug):
                if c.anchor in seen_anchors:
                    continue
                seen_anchors.add(c.anchor)
                gi = chunk_to_global.get(id(c))
                if gi is None:
                    continue
                emb = embeddings[gi].astype(np.float32)
                emb_str = "[" + ",".join(f"{x:.7f}" for x in emb) + "]"
                await conn.execute(
                    """
                    INSERT INTO chunks (document_id, source_type, subject_area,
                                        anchor, token_count, text, embedding,
                                        chunk_strategy, as_at, metadata)
                    VALUES ($1, 'bare_act', $2, $3, $4, $5, $6::halfvec, $7, $8, $9)
                    ON CONFLICT (document_id, anchor, as_at) DO NOTHING
                    """,
                    doc_pk, subj, c.anchor, c.token_count, c.text, emb_str,
                    c.chunk_strategy.value, c.as_at,
                    json.dumps(c.metadata),
                )
                inserted += 1
            inserted_total += inserted
            print(f"  ✓ {slug}: inserted {inserted} chunks (subject={subj})")

    # Don't close the shared pool — apps.api.db.get_pool() returns a
    # process-singleton pool. Pool teardown happens at process exit.
    print(f"\n=== Done ===")
    print(f"  new documents : {new_docs}")
    print(f"  reused orphan : {reused_docs}")
    print(f"  chunks inserted: {inserted_total}")
    print(f"  Note: run backfill_sparse_embeddings.py next for sparse vectors.")


if __name__ == "__main__":
    asyncio.run(main())
