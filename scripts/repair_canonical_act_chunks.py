#!/usr/bin/env python3
"""Replace hand-written Act backfills with text from the pinned PDF.

This is deliberately narrow. It preserves existing document/chunk identities
and only updates named section chunks after validating the local artifact's
SHA-256. Provenance verification remains the final promotion gate.
"""
from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import re
import sys
from pathlib import Path

import asyncpg
import pymupdf

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "packages"))

from apps.api.config import get_settings  # noqa: E402
from apps.api.embeddings import (  # noqa: E402
    embedding_to_halfvec_literal,
    get_embedder,
    sparse_to_jsonb,
)
from chunking.act import chunk_act  # noqa: E402
from ingest.normalize.redact import sanitize_for_db  # noqa: E402


ACT_SPECS = {
    "indian-succession-1925": {
        "title": "Indian Succession Act 1925",
        "pdf": ROOT / "data/raw/acts/indian-succession-1925__192539.pdf",
        "pdf_sha256": "fe096024e6c3a31932b4671bc50c364300c9115b96afcd182a160608ecc19392",
        "raw_bytes_size": 1144648,
        "source_url": "https://www.indiacode.nic.in/bitstream/123456789/2385/1/192539.pdf",
        "sections": ("50", "51", "54"),
        "expected_old_sha256": {
            "50": "7b9a8f30cf15560d1f814fe59e6b3589e68c862c02758905dcc55117857d07f5",
            "51": "ee195766bf0d669aefbc716fbe9572635d264af0d957b99cce06d0d86d7d36dd",
            "54": "04ec069ac2b91838cbecc5b50350ef502bf801720a8b64886811da0416e1df0a",
        },
    },
}


def _canonical_chunks(slug: str) -> dict[str, dict]:
    spec = ACT_SPECS[slug]
    data = spec["pdf"].read_bytes()
    actual_sha = hashlib.sha256(data).hexdigest()
    if actual_sha != spec["pdf_sha256"]:
        raise RuntimeError(
            f"refusing repair: {spec['pdf']} sha256={actual_sha}, "
            f"expected {spec['pdf_sha256']}"
        )
    document = pymupdf.open(stream=data, filetype="pdf")
    try:
        text = sanitize_for_db("\n\n".join(page.get_text("text") for page in document))
    finally:
        document.close()

    out: dict[str, dict] = {}
    for chunk in chunk_act(slug, text, act_title=spec["title"]):
        for section in spec["sections"]:
            base = f"{slug}/sec-{section}"
            if re.fullmatch(rf"{re.escape(base)}(?:@[^/]+)?", chunk.anchor):
                out[section] = {
                    "text": chunk.text,
                    "token_count": chunk.token_count,
                    "metadata": {
                        **chunk.metadata,
                        "canonical_artifact_sha256": actual_sha,
                        "canonical_repair": True,
                    },
                }
                break
    missing = [section for section in spec["sections"] if section not in out]
    if missing:
        raise RuntimeError(f"canonical chunker did not produce sections: {missing}")
    return out


async def repair(slug: str, *, dry_run: bool = False) -> list[dict]:
    spec = ACT_SPECS[slug]
    canonical = _canonical_chunks(slug)
    conn = await asyncpg.connect(get_settings().resolved_database_url_host_side)
    try:
        sources = await conn.fetch(
            """
            SELECT id, url, canonical_url_hash, raw_sha256, raw_bytes_size, source_type
            FROM sources
            WHERE url=$1 AND source_type='bare_act'
            """,
            spec["source_url"],
        )
        if len(sources) != 1:
            raise RuntimeError(f"refusing repair: expected one exact bare_act source, found {len(sources)}")
        source = sources[0]
        if source["canonical_url_hash"] != hashlib.sha256(spec["source_url"].encode()).hexdigest():
            raise RuntimeError("refusing repair: database canonical URL hash is not exact")
        if source["raw_sha256"] != spec["pdf_sha256"]:
            raise RuntimeError("refusing repair: database source hash is not pinned to the local artifact")
        if source["raw_bytes_size"] != spec["raw_bytes_size"]:
            raise RuntimeError("refusing repair: database source byte size is not pinned to the local artifact")
        documents = await conn.fetch(
            "SELECT id, title FROM documents WHERE doc_id=$1 AND source_id=$2",
            slug,
            source["id"],
        )
        if len(documents) != 1:
            raise RuntimeError(f"refusing repair: expected one exact document for {slug}, found {len(documents)}")
        document = documents[0]

        rows: list[dict] = []
        updates: list[tuple[dict, dict, int, str]] = []
        for section, replacement in canonical.items():
            base = f"{slug}/sec-{section}"
            chunks = await conn.fetch(
                """
                SELECT id, anchor, text, quarantined
                FROM chunks
                WHERE document_id=$1
                  AND anchor=$2
                  AND as_at IS NULL
                ORDER BY id
                """,
                document["id"],
                base,
            )
            if len(chunks) != 1:
                raise RuntimeError(f"refusing repair: expected one exact chunk for {base}, found {len(chunks)}")
            chunk = chunks[0]
            if chunk["quarantined"]:
                raise RuntimeError(f"refusing repair: target chunk is already quarantined: {base}")
            row = {
                "section": section,
                "chunk_id": chunk["id"],
                "anchor": chunk["anchor"],
                "old_chars": len(chunk["text"]),
                "new_chars": len(replacement["text"]),
            }
            if chunk["text"] == replacement["text"]:
                row["action"] = "no_op"
            else:
                expected_old = spec.get("expected_old_sha256", {}).get(section)
                actual_old = hashlib.sha256(chunk["text"].encode()).hexdigest()
                if expected_old and actual_old != expected_old:
                    raise RuntimeError(
                        f"refusing repair: unexpected existing text for {base} "
                        f"sha256={actual_old}"
                    )
                row["action"] = "repair"
                updates.append((replacement, row, chunk["id"], chunk["text"]))
            rows.append(row)

        if not dry_run and updates:
            embedded: list[tuple[dict, dict, int, str, str, str]] = []
            for replacement, row, chunk_id, old_text in updates:
                dense, sparse = get_embedder().encode_with_sparse([replacement["text"]])
                embedded.append((
                    replacement,
                    row,
                    chunk_id,
                    embedding_to_halfvec_literal(dense[0]),
                    sparse_to_jsonb(sparse[0]),
                    old_text,
                ))
            async with conn.transaction():
                for replacement, target_row, chunk_id, dense, sparse, old_text in embedded:
                    result = await conn.execute(
                        """
                        UPDATE chunks
                        SET text=$1,
                            token_count=$2,
                            embedding=$3::halfvec,
                            embedding_sparse=$4::jsonb,
                            chunk_strategy='section',
                            metadata=$5::jsonb,
                            provenance_verified=false,
                            provenance_verified_at=NULL
                        WHERE id=$6
                          AND document_id=$7
                          AND anchor=$8
                          AND as_at IS NULL
                          AND quarantined=false
                          AND text=$9
                        """,
                        replacement["text"],
                        replacement["token_count"],
                        dense,
                        sparse,
                        json.dumps(replacement["metadata"]),
                        chunk_id,
                        document["id"],
                        target_row["anchor"],
                        old_text,
                    )
                    if result != "UPDATE 1":
                        raise RuntimeError(
                            f"refusing repair: exact target changed during transaction for chunk {chunk_id}"
                        )
                document_result = await conn.execute(
                    "UPDATE documents SET provenance_verified=false, provenance_verified_at=NULL WHERE id=$1",
                    document["id"],
                )
                if document_result != "UPDATE 1":
                    raise RuntimeError("refusing repair: document state update failed")
        return rows
    finally:
        await conn.close()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--slug", choices=sorted(ACT_SPECS), default="indian-succession-1925")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    rows = asyncio.run(repair(args.slug, dry_run=args.dry_run))
    for row in rows:
        action = row["action"]
        if args.dry_run and action == "repair":
            action = "would_repair"
        print(f"{action} section {row['section']} chunk={row['chunk_id']} "
              f"chars={row['old_chars']}->{row['new_chars']}")


if __name__ == "__main__":
    main()
