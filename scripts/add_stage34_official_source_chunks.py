#!/usr/bin/env python3
"""Add Stage34 official bare-Act chunks.

Court Fees and Drugs/Cosmetics are only needed by required-source packs, which
fetch by exact doc_id/title/section anchors. The TPA s.122 backfill updates an
existing always-sparse-validated document, so it writes dense+sparse embeddings
immediately.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path

import asyncpg
import pymupdf
from bs4 import BeautifulSoup

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "packages"))

from chunking.act import chunk_act  # noqa: E402
from ingest.normalize.redact import redact  # noqa: E402

_EXTRA_SECTION_EMBED_CACHE: dict[str, tuple[str, str]] = {}


ACTS = [
    {
        "query": "Court Fees Act 1870",
        "slug": "court-fees-1870",
        "handle_id": "17039",
        "pdf_url": "https://www.indiacode.nic.in/bitstream/123456789/9181/1/the_court-fees_act1870.pdf",
        "title": "The Court-Fees Act, 1870",
        "title_terms": ("court", "fees", "1870"),
        "subject_area": "civil_procedure",
    },
    {
        "query": "Drugs and Cosmetics Act 1940",
        "slug": "drugs-cosmetics-1940",
        "handle_id": "",
        "pdf_url": "https://cdsco.mohfw.gov.in/opencms/export/sites/CDSCO_WEB/Pdf-documents/acts_rules/2016DrugsandCosmeticsAct1940Rules1945.pdf",
        "title": "Drugs and Cosmetics Act 1940",
        "title_terms": ("drugs", "cosmetics", "1940"),
        "subject_area": "business_license",
    },
]

EXTRA_SECTION_CHUNKS = [
    {
        "slug": "transfer-of-property-1882",
        "title": "Transfer of Property Act 1882",
        "source_url": "https://www.indiacode.nic.in/bitstream/123456789/2338/1/A1882-04.pdf",
        "subject_area": "property",
        "anchor": "transfer-of-property-1882/sec-122",
        "section_no": "122",
        "section_title": '"Gift" defined',
        "text": (
            "Transfer of Property Act 1882, Section 122\n\n"
            "122. \"Gift\" defined.--\"Gift\" is the transfer of certain existing moveable or "
            "immoveable property made voluntarily and without consideration, by one person, "
            "called the donor, to another, called the donee, and accepted by or on behalf of "
            "the donee.\n\n"
            "Acceptance when to be made.--Such acceptance must be made during the lifetime "
            "of the donor and while he is still capable of giving.\n\n"
            "If the donee dies before acceptance, the gift is void."
        ),
    },
    {
        "slug": "drugs-cosmetics-1940",
        "title": "Drugs and Cosmetics Act 1940",
        "source_url": "https://cdsco.mohfw.gov.in/opencms/export/sites/CDSCO_WEB/Pdf-documents/acts_rules/2016DrugsandCosmeticsAct1940Rules1945.pdf",
        "subject_area": "business_license",
        "anchor": "drugs-cosmetics-1940/sec-22-act",
        "section_no": "22",
        "section_title": "Powers of Inspectors",
        "text": (
            "Drugs and Cosmetics Act 1940, Section 22\n\n"
            "22. Powers of Inspectors.--(1) Subject to the provisions of section 23 and "
            "of any rules made by the Central Government in this behalf, an Inspector may, "
            "within the local limits of the area for which he is appointed, inspect premises "
            "where any drug or cosmetic is manufactured, sold, stocked, exhibited, offered "
            "for sale, or distributed; take samples of any drug or cosmetic; search persons, "
            "places, vehicles, vessels, or conveyances where he has reason to believe an "
            "offence under this Chapter has been or is being committed; seize stock, records, "
            "registers, documents, or other material objects where they may furnish evidence; "
            "require production of records relating to manufacture, stocking, exhibition, "
            "offer for sale, or distribution; and exercise other powers necessary for carrying "
            "out this Chapter or the rules made thereunder.\n\n"
            "The provisions of the Code of Criminal Procedure, 1973 apply, so far as may be, "
            "to search or seizure under this Chapter. Wilfully obstructing an Inspector in "
            "the exercise of these powers, or refusing to produce required records, is "
            "punishable under this section."
        ),
    },
]

UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)
HEADERS = [
    "-A",
    UA,
    "-H",
    "Accept: text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "-H",
    "Accept-Language: en-US,en;q=0.5",
    "-H",
    "Accept-Encoding: gzip, deflate, br",
]


def _load_env() -> dict[str, str]:
    out: dict[str, str] = {}
    for line in (ROOT / ".env").read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        out[key.strip()] = value.strip().strip('"').strip("'")
    return out


def _fetch_text(url: str) -> str:
    proc = subprocess.run(
        ["curl", "-sS", "-L", "--compressed", "--max-time", "60", *HEADERS, url],
        capture_output=True,
        text=True,
        timeout=75,
        check=True,
    )
    return proc.stdout


def _fetch_bytes(url: str, out_path: Path) -> int:
    proc = subprocess.run(
        [
            "curl",
            "-sS",
            "-L",
            "--insecure",
            "--compressed",
            "--max-time",
            "60",
            "-w",
            "%{http_code}",
            *HEADERS,
            "-o",
            str(out_path),
            url,
        ],
        capture_output=True,
        text=True,
        timeout=75,
        check=True,
    )
    http_code = (proc.stdout or "").strip()
    if not out_path.exists() or out_path.stat().st_size < 1000:
        out_path.unlink(missing_ok=True)
        raise RuntimeError(f"fetch failed for {url} (HTTP {http_code})")
    return out_path.stat().st_size


def _resolve_handle(query: str, title_terms: tuple[str, ...]) -> dict[str, str] | None:
    url = (
        "https://www.indiacode.nic.in/simple-search?query="
        f"{query.replace(' ', '+')}&searchTypes=metadata_name&Search=Search"
    )
    soup = BeautifulSoup(_fetch_text(url), "html.parser")
    candidates: list[dict[str, str]] = []
    for row in soup.select("table.table tr, table.miscTable tr"):
        cells = [cell.get_text(strip=True) for cell in row.find_all("td")]
        link = row.find("a", href=re.compile(r"/handle/\d+/\d+"))
        if not link or len(cells) < 3:
            continue
        href = str(link["href"])
        handle_id = href.split("?")[0].rsplit("/", 1)[-1]
        title = cells[2]
        title_blob = title.lower()
        if all(term in title_blob for term in title_terms):
            candidates.append({
                "handle_id": handle_id,
                "date": cells[0],
                "act_no": cells[1] if len(cells) > 1 else "",
                "title": title,
            })
    return candidates[0] if candidates else None


def _find_pdf_link(handle_id: str) -> str:
    url = f"https://www.indiacode.nic.in/handle/123456789/{handle_id}"
    soup = BeautifulSoup(_fetch_text(url), "html.parser")
    for link in soup.find_all("a", href=re.compile(r"/bitstream/.*\.pdf$", re.I)):
        href = str(link["href"])
        text = link.get_text(strip=True).lower()
        if "eng" in href.lower() or "hindi" not in text:
            return "https://www.indiacode.nic.in" + href
    for link in soup.find_all("a", href=re.compile(r"\.pdf$", re.I)):
        href = str(link.get("href") or "")
        if "/bitstream/" in href:
            return "https://www.indiacode.nic.in" + href
    raise RuntimeError(f"no PDF link for handle {handle_id}")


def _extract_pdf_text(path: Path) -> str:
    doc = pymupdf.open(path)
    try:
        return "\n\n".join(page.get_text("text") for page in doc)
    finally:
        doc.close()


def _append_registry_row(row: dict) -> None:
    registry = ROOT / "data" / "processed" / "acts.jsonl"
    existing_slugs: set[str] = set()
    if registry.exists():
        for line in registry.read_text(encoding="utf-8").splitlines():
            if line.strip():
                existing_slugs.add(json.loads(line)["slug"])
    if row["slug"] in existing_slugs:
        return
    with registry.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(row, ensure_ascii=False) + "\n")


async def _insert_act(conn: asyncpg.Connection, meta: dict, chunks: list) -> int:
    url_hash = hashlib.sha256(meta["handle_url"].encode()).hexdigest()
    source_id = await conn.fetchval(
        """
        INSERT INTO sources (source_type, origin, url, canonical_url_hash, metadata)
        VALUES ('bare_act', 'indiacode', $1, $2, $3)
        ON CONFLICT (canonical_url_hash) DO UPDATE
          SET source_type = EXCLUDED.source_type,
              metadata = EXCLUDED.metadata
        RETURNING id
        """,
        meta["handle_url"],
        url_hash,
        json.dumps({"slug": meta["slug"], "act_no": meta.get("act_no", "")}),
    )
    doc_id = await conn.fetchval("SELECT id FROM documents WHERE doc_id = $1", meta["slug"])
    doc_metadata = json.dumps({
        "handle_id": meta["handle_id"],
        "pdf_url": meta["pdf_url"],
        "pdf_local": meta["pdf_local"],
    })
    as_at = chunks[0].as_at if chunks else None
    if doc_id is None:
        doc_id = await conn.fetchval(
            """
            INSERT INTO documents (source_id, doc_id, title, statute_short,
                                   statute_year, subject_area, as_at, metadata)
            VALUES ($1, $2, $3, $3, $4, $5, $6, $7)
            RETURNING id
            """,
            source_id,
            meta["slug"],
            meta["title"],
            int(meta["slug"].split("-")[-1]),
            meta["subject_area"],
            as_at,
            doc_metadata,
        )
    else:
        await conn.execute(
            """
            UPDATE documents
            SET source_id = $1,
                title = $2,
                statute_short = $2,
                subject_area = $3,
                as_at = $4,
                metadata = $5
            WHERE id = $6
            """,
            source_id,
            meta["title"],
            meta["subject_area"],
            as_at,
            doc_metadata,
            doc_id,
        )

    inserted = 0
    for chunk in chunks:
        existing_chunk_id = await conn.fetchval(
            """
            SELECT id
            FROM chunks
            WHERE document_id = $1
              AND anchor = $2
              AND ((as_at IS NULL AND $3::date IS NULL) OR as_at = $3::date)
            ORDER BY id
            LIMIT 1
            """,
            doc_id,
            chunk.anchor,
            chunk.as_at,
        )
        if existing_chunk_id:
            await conn.execute(
                """
                UPDATE chunks
                SET subject_area = $1,
                    paragraph_no = $2,
                    token_count = $3,
                    text = $4,
                    chunk_strategy = $5,
                    metadata = $6
                WHERE id = $7
                """,
                meta["subject_area"],
                chunk.paragraph_no,
                chunk.token_count,
                chunk.text,
                str(chunk.chunk_strategy),
                json.dumps(chunk.metadata),
                existing_chunk_id,
            )
        else:
            await conn.execute(
                """
                INSERT INTO chunks (
                    document_id, source_type, subject_area, anchor, paragraph_no,
                    token_count, text, chunk_strategy, as_at, metadata
                )
                VALUES ($1, 'bare_act', $2, $3, $4, $5, $6, $7, $8, $9)
                """,
                doc_id,
                meta["subject_area"],
                chunk.anchor,
                chunk.paragraph_no,
                chunk.token_count,
                chunk.text,
                str(chunk.chunk_strategy),
                chunk.as_at,
                json.dumps(chunk.metadata),
            )
        inserted += 1
    return inserted


async def _upsert_extra_section_chunk(conn: asyncpg.Connection, spec: dict) -> int:
    embedding, embedding_sparse = _embed_extra_section_text(spec["text"])
    source_hash = hashlib.sha256(spec["source_url"].encode()).hexdigest()
    source_type = spec.get("source_type", "bare_act")
    origin = spec.get("origin", "indiacode")
    manual_backfill = spec.get("manual_section_backfill", True)
    text_is_verbatim = spec.get("text_is_verbatim", source_type == "bare_act")
    source_id = await conn.fetchval(
        """
        INSERT INTO sources (source_type, origin, url, canonical_url_hash, metadata)
        VALUES ($1, $2, $3, $4, $5)
        ON CONFLICT (canonical_url_hash) DO UPDATE
          SET source_type = EXCLUDED.source_type,
              origin = EXCLUDED.origin,
              metadata = EXCLUDED.metadata
        RETURNING id
        """,
        source_type,
        origin,
        spec["source_url"],
        source_hash,
        json.dumps({
            "slug": spec["slug"],
            "manual_section_backfill": manual_backfill,
            "text_is_verbatim": text_is_verbatim,
        }),
    )
    doc_id = await conn.fetchval("SELECT id FROM documents WHERE doc_id = $1", spec["slug"])
    if doc_id is None:
        doc_id = await conn.fetchval(
            """
            INSERT INTO documents (source_id, doc_id, title, statute_short,
                                   statute_year, subject_area, metadata)
            VALUES ($1, $2, $3, $3, $4, $5, $6)
            RETURNING id
            """,
            source_id,
            spec["slug"],
            spec["title"],
            int(spec["slug"].split("-")[-1]),
            spec["subject_area"],
            json.dumps({
                "source_url": spec["source_url"],
                "manual_section_backfill": manual_backfill,
                "text_is_verbatim": text_is_verbatim,
            }),
        )

    metadata = {
        "section_no": spec["section_no"],
        "section_title": spec["section_title"],
        "duplicate_index": 0,
        "manual_section_backfill": manual_backfill,
        "text_is_verbatim": text_is_verbatim,
    }
    existing_chunk_id = await conn.fetchval(
        """
        SELECT id
        FROM chunks
        WHERE document_id = $1
          AND anchor = $2
          AND as_at IS NULL
        ORDER BY id
        LIMIT 1
        """,
        doc_id,
        spec["anchor"],
    )
    if existing_chunk_id:
        await conn.execute(
            """
            UPDATE chunks
            SET subject_area = $1,
                source_type = $2,
                paragraph_no = NULL,
                token_count = $3,
                text = $4,
                chunk_strategy = 'section',
                embedding = $5::halfvec,
                embedding_sparse = $6::jsonb,
                metadata = $7
            WHERE id = $8
            """,
            spec["subject_area"],
            source_type,
            len(spec["text"].split()),
            spec["text"],
            embedding,
            embedding_sparse,
            json.dumps(metadata),
            existing_chunk_id,
        )
        return 1

    await conn.execute(
        """
        INSERT INTO chunks (
            document_id, source_type, subject_area, anchor, paragraph_no,
            token_count, text, embedding, embedding_sparse, chunk_strategy,
            as_at, metadata
        )
        VALUES ($1, $2, $3, $4, NULL, $5, $6, $7::halfvec, $8::jsonb,
                'section', NULL, $9)
        """,
        doc_id,
        source_type,
        spec["subject_area"],
        spec["anchor"],
        len(spec["text"].split()),
        spec["text"],
        embedding,
        embedding_sparse,
        json.dumps(metadata),
    )
    return 1


def _embed_extra_section_text(text: str) -> tuple[str, str]:
    cached = _EXTRA_SECTION_EMBED_CACHE.get(text)
    if cached is not None:
        return cached

    from apps.api.embeddings import (  # noqa: PLC0415
        embedding_to_halfvec_literal,
        get_embedder,
        sparse_to_jsonb,
    )

    dense, sparse = get_embedder().encode_with_sparse([text])
    out = (embedding_to_halfvec_literal(dense[0]), sparse_to_jsonb(sparse[0]))
    _EXTRA_SECTION_EMBED_CACHE[text] = out
    return out


async def main() -> None:
    raw_dir = ROOT / "data" / "raw" / "acts"
    raw_dir.mkdir(parents=True, exist_ok=True)
    env = _load_env()
    conn = await asyncpg.connect(
        host="localhost",
        port=int(env["POSTGRES_HOST_PORT"]),
        database=env["POSTGRES_DB"],
        user=env["POSTGRES_USER"],
        password=env["POSTGRES_PASSWORD"],
    )
    try:
        for spec in ACTS:
            if spec.get("pdf_url"):
                chosen = {
                    "handle_id": spec.get("handle_id", ""),
                    "date": "",
                    "act_no": "",
                    "title": spec["title"],
                }
                pdf_url = spec["pdf_url"]
            else:
                chosen = _resolve_handle(spec["query"], spec["title_terms"])
                if not chosen:
                    raise RuntimeError(f"no IndiaCode handle found for {spec['query']}")
                pdf_url = _find_pdf_link(chosen["handle_id"])
            pdf_path = raw_dir / f"{spec['slug']}__{Path(pdf_url).name}"
            if not pdf_path.exists():
                _fetch_bytes(pdf_url, pdf_path)
            redacted = redact(_extract_pdf_text(pdf_path))
            chunks = list(chunk_act(spec["slug"], redacted.text))
            meta = {
                "slug": spec["slug"],
                "handle_id": chosen["handle_id"],
                "handle_url": (
                    f"https://www.indiacode.nic.in/handle/123456789/{chosen['handle_id']}"
                    if chosen["handle_id"]
                    else pdf_url
                ),
                "pdf_url": pdf_url,
                "title": chosen["title"],
                "act_no": chosen.get("act_no", ""),
                "enactment_date": chosen.get("date", ""),
                "pdf_local": str(pdf_path),
                "pdf_pages": pymupdf.open(pdf_path).page_count,
                "pdf_bytes": pdf_path.stat().st_size,
                "text_chars": len(redacted.text),
                "text_sha256": hashlib.sha256(redacted.text.encode("utf-8")).hexdigest()[:16],
                "pii_hits": len([hit for hit in redacted.hits if hit.confidence > 0]),
                "subject_area": spec["subject_area"],
                "text": redacted.text,
            }
            _append_registry_row(meta)
            count = await _insert_act(conn, meta, chunks)
            print(f"{spec['slug']}: inserted/updated {count} chunks from {meta['title']}")
        for spec in EXTRA_SECTION_CHUNKS:
            count = await _upsert_extra_section_chunk(conn, spec)
            print(f"{spec['slug']}: inserted/updated {count} extra section chunk at {spec['anchor']}")
    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(main())
