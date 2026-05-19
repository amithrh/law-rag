#!/usr/bin/env python3
"""Add the Maintenance and Welfare of Parents and Senior Citizens Act 2007.

Surfaced as a corpus gap on 2026-05-19 — the query "my son threw me out of
the house" got generic criminal cases instead of the proper landmark.

This Act (No. 56 of 2007) is the direct remedy:
  - Section 4-9   : maintenance entitlement of senior citizens from children
  - Section 23    : protection from transfer of property / eviction
  - Section 7-9   : District-level Maintenance Tribunal as the forum

Mirrors `scripts/add_more_acts.py` exactly. Idempotent on slug.
Dense-only embeddings — sparse vectors get filled in by the running
`scripts/backfill_sparse_embeddings.py` (idempotent on embedding_sparse IS NULL).
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import re
import subprocess
import sys
import time
from pathlib import Path

import asyncpg
import numpy as np
import pymupdf
from bs4 import BeautifulSoup
from sentence_transformers import SentenceTransformer

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT / "packages"))
from chunking.act import chunk_act  # noqa: E402
from ingest.normalize.redact import redact  # noqa: E402

NEW_ACTS = [
    ("Maintenance and Welfare of Parents and Senior Citizens Act 2007",
     "senior-citizens-2007"),
]
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
HEADERS = [
    "-A", UA,
    "-H", "Accept: text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "-H", "Accept-Language: en-US,en;q=0.5",
    "-H", "Accept-Encoding: gzip, deflate, br",
]
CENTRAL_COLLECTION = "123456789/1362"


def fetch_text(url: str) -> str:
    r = subprocess.run(
        ["curl", "-sS", "-L", "--compressed", "--max-time", "25",
         *HEADERS, url],
        capture_output=True, text=True, timeout=35,
    )
    return r.stdout


def fetch_bytes(url: str, out_path: Path) -> int:
    r = subprocess.run(
        ["curl", "-sS", "-L", "--compressed", "--max-time", "60",
         "-w", "%{http_code}", *HEADERS, "-o", str(out_path), url],
        capture_output=True, text=True, timeout=70,
    )
    http_code = (r.stdout or "").strip()
    if not out_path.exists() or out_path.stat().st_size < 1000:
        out_path.unlink(missing_ok=True)
        raise RuntimeError(f"fetch failed for {url} (HTTP {http_code})")
    return out_path.stat().st_size


def resolve_handle(query: str) -> dict | None:
    url = (f"https://www.indiacode.nic.in/simple-search?query="
           f"{query.replace(' ', '+')}&searchTypes=metadata_name&Search=Search")
    html = fetch_text(url)
    soup = BeautifulSoup(html, "html.parser")
    candidates = []
    for tr in soup.select("table.table tr, table.miscTable tr"):
        cells = [td.get_text(strip=True) for td in tr.find_all("td")]
        a = tr.find("a", href=re.compile(r"/handle/\d+/\d+"))
        if a and len(cells) >= 3:
            href = a["href"]
            hid = href.split("?")[0].rsplit("/", 1)[-1]
            m = re.search(r"col=(\d+/\d+)", href)
            col = m.group(1) if m else ""
            candidates.append({
                "handle_id": hid, "collection": col,
                "date": cells[0],
                "act_no": cells[1] if len(cells) > 1 else "",
                "title": cells[2] if len(cells) > 2 else "",
            })
    year = query.split()[-1]
    matching_year = [c for c in candidates
                     if year in c["date"] or year in c["title"]]
    central = [c for c in matching_year if c["collection"] == CENTRAL_COLLECTION]
    return central[0] if central else (
        matching_year[0] if matching_year else (
            candidates[0] if candidates else None))


def find_pdf_link(handle_id: str) -> str | None:
    handle_url = f"https://www.indiacode.nic.in/handle/123456789/{handle_id}"
    html = fetch_text(handle_url)
    soup = BeautifulSoup(html, "html.parser")
    for a in soup.find_all("a", href=re.compile(r"/bitstream/.*\.pdf$", re.I)):
        href = a["href"]
        text = a.get_text(strip=True)
        if "eng" in href.lower() or "hindi" not in text.lower():
            return href
    for a in soup.find_all("a", href=re.compile(r"\.pdf$", re.I)):
        if "/bitstream/" in (a.get("href") or ""):
            return a["href"]
    return None


def load_env(p=".env"):
    out = {}
    for line in (ROOT / p).read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, _, v = line.partition("=")
        out[k.strip()] = v.strip().strip('"').strip("'")
    return out


async def main():
    env = load_env()
    (ROOT / "data" / "raw" / "acts").mkdir(parents=True, exist_ok=True)
    out_jsonl = ROOT / "data" / "processed" / "acts.jsonl"

    print("=== Step 1: resolve handle IDs ===")
    resolved = []
    for query, slug in NEW_ACTS:
        chosen = resolve_handle(query)
        if not chosen:
            print(f"  ✗ {query} — no result")
            continue
        print(f"  ✓ {query} → handle={chosen['handle_id']} "
              f"col={chosen['collection']} title={chosen['title'][:60]}")
        resolved.append((slug, query, chosen))
        time.sleep(1.0)

    print("\n=== Step 2: download + extract + redact ===")
    new_rows = []
    for slug, query, chosen in resolved:
        handle_url = (f"https://www.indiacode.nic.in/handle/123456789/"
                      f"{chosen['handle_id']}")
        pdf_link = find_pdf_link(chosen["handle_id"])
        if not pdf_link:
            print(f"  ✗ {slug}: no PDF link")
            continue
        pdf_url = "https://www.indiacode.nic.in" + pdf_link
        pdf_name = Path(pdf_link).name
        local_pdf = ROOT / "data" / "raw" / "acts" / f"{slug}__{pdf_name}"
        if not local_pdf.exists():
            try:
                sz = fetch_bytes(pdf_url, local_pdf)
                print(f"  ↓ {slug}: {sz/1024:.0f} KB")
            except Exception as e:
                print(f"  ✗ {slug}: download failed ({e})")
                continue
        else:
            print(f"  ✓ {slug}: cached")
        try:
            pdf_bytes = local_pdf.read_bytes()
            doc = pymupdf.open(stream=pdf_bytes, filetype="pdf")
            n_pages = doc.page_count
            text = "\n\n".join(p.get_text("text") for p in doc)
            doc.close()
        except Exception as e:
            print(f"  ✗ {slug}: PDF parse failed: {e}")
            continue
        red = redact(text)
        new_rows.append({
            "slug": slug, "handle_id": chosen["handle_id"],
            "handle_url": handle_url, "pdf_url": pdf_url,
            "title": chosen.get("title", "").strip(),
            "act_no": chosen.get("act_no", ""),
            "enactment_date": chosen.get("date", ""),
            "pdf_local": str(local_pdf),
            "pdf_pages": n_pages, "pdf_bytes": len(pdf_bytes),
            "text_chars": len(red.text),
            "text_sha256": hashlib.sha256(red.text.encode("utf-8")).hexdigest()[:16],
            "pii_hits": len([h for h in red.hits if h.confidence > 0]),
            "text": red.text,
        })
        print(f"     pages={n_pages}, chars={len(red.text):,}, "
              f"pii_hits={red.suspicious}")
        time.sleep(1.0)

    if not new_rows:
        print("\nNo acts to add.")
        return

    with out_jsonl.open("a") as f:
        for r in new_rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    print(f"\n=== Step 3: appended {len(new_rows)} rows to {out_jsonl} ===")

    print("\n=== Step 4: chunk + embed + insert ===")
    all_chunks: list[tuple[dict, object]] = []
    for r in new_rows:
        for c in chunk_act(r["slug"], r["text"]):
            all_chunks.append((r, c))
    print(f"  chunks: {len(all_chunks)}")

    print("  loading bge-m3 on MPS (sentence-transformers wrapper) ...")
    t0 = time.time()
    model = SentenceTransformer("BAAI/bge-m3", device="mps")
    model.max_seq_length = 512
    print(f"    loaded in {time.time()-t0:.1f}s")

    print(f"  embedding {len(all_chunks)} chunks (dense only — sparse will "
          f"be filled by backfill) ...")
    texts = [c.text for _, c in all_chunks]
    t0 = time.time()
    embeddings = model.encode(
        texts, batch_size=16, show_progress_bar=False,
        normalize_embeddings=True, convert_to_numpy=True,
    )
    elapsed = time.time() - t0
    print(f"    done in {elapsed:.0f}s ({len(texts)/elapsed:.1f} emb/s)")

    print("  inserting into postgres...")
    conn = await asyncpg.connect(
        host="localhost", port=int(env["POSTGRES_HOST_PORT"]),
        database=env["POSTGRES_DB"], user=env["POSTGRES_USER"],
        password=env["POSTGRES_PASSWORD"],
    )

    by_slug: dict[str, tuple[dict, list]] = {}
    for r, c in all_chunks:
        by_slug.setdefault(r["slug"], (r, []))[1].append(c)

    inserted = 0
    skipped = 0
    for slug, (meta, chunks) in by_slug.items():
        existing = await conn.fetchval(
            "SELECT id FROM documents WHERE doc_id = $1", slug,
        )
        if existing:
            print(f"  - {slug}: already in DB, skipping")
            skipped += len(chunks)
            continue

        url_hash = hashlib.sha256(meta["handle_url"].encode()).hexdigest()
        src_id = await conn.fetchval(
            """INSERT INTO sources (source_type, origin, url,
                                    canonical_url_hash, metadata)
               VALUES ('bare_act', 'indiacode', $1, $2, $3)
               ON CONFLICT (canonical_url_hash) DO UPDATE
                 SET source_type = EXCLUDED.source_type
               RETURNING id""",
            meta["handle_url"], url_hash,
            json.dumps({"slug": slug, "act_no": meta.get("act_no", "")}),
        )
        as_at = chunks[0].as_at if chunks else None
        doc_pk = await conn.fetchval(
            """INSERT INTO documents (source_id, doc_id, title, statute_short,
                                      statute_year, as_at, metadata)
               VALUES ($1, $2, $3, $4, $5, $6, $7)
               RETURNING id""",
            src_id, slug, meta["title"], meta["title"],
            int(slug.split('-')[-1]) if slug.split('-')[-1].isdigit() else None,
            as_at, json.dumps({"handle_id": meta["handle_id"]}),
        )

        seen = set()
        for c in chunks:
            if c.anchor in seen:
                continue
            seen.add(c.anchor)
            # Find this chunk's index in the full all_chunks list to fetch
            # the corresponding embedding vector
            for global_i, (rr, cc) in enumerate(all_chunks):
                if rr["slug"] == slug and cc is c:
                    emb = embeddings[global_i].astype(np.float32)
                    break
            else:
                continue
            emb_str = "[" + ",".join(f"{x:.7f}" for x in emb) + "]"
            await conn.execute(
                """
                INSERT INTO chunks (document_id, source_type, anchor,
                                    token_count, text, embedding,
                                    chunk_strategy, as_at, metadata)
                VALUES ($1, 'bare_act', $2, $3, $4, $5::halfvec, $6, $7, $8)
                ON CONFLICT (document_id, anchor, as_at) DO NOTHING
                """,
                doc_pk, c.anchor, c.token_count, c.text, emb_str,
                c.chunk_strategy.value, c.as_at,
                json.dumps(c.metadata),
            )
            inserted += 1

    await conn.close()
    print(f"\n=== Done: inserted {inserted} chunks, skipped "
          f"{skipped} (already in DB) ===")
    print("   Note: sparse vectors will populate automatically as the "
          "backfill script runs (filters on embedding_sparse IS NULL).")


if __name__ == "__main__":
    asyncio.run(main())
