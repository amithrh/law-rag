#!/usr/bin/env python3
"""Quarantine known Act fragments whose anchor is not legally trustworthy.

Quarantine is preferable to promotion when the words are present in the
official artifact but the stored section identity is wrong. The row remains
available for a later exact re-ingest under its true section.
"""
from __future__ import annotations

import argparse
import asyncio
import hashlib
import sys
from pathlib import Path

import asyncpg

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from apps.api.config import get_settings  # noqa: E402


TARGETS = {
    "registration-1908/sec-3__3-d": {
        "document_id": "registration-1908",
        "source_url": "https://www.indiacode.nic.in/bitstream/123456789/2190/5/A1908-16.pdf",
        "expected_text_sha256": "a3e651ebf884a438fcf10f554a9fd93886bd654b9f621edb15d489baec2de9a3",
        "reason": "misanchored amendment fragment; text belongs to Registration Act section 69, not section 3",
    },
}


async def quarantine(anchor: str, *, dry_run: bool = False) -> dict:
    target = TARGETS[anchor]
    conn = await asyncpg.connect(get_settings().resolved_database_url_host_side)
    try:
        async def fetch_exact_target():
            rows = await conn.fetch(
                """
                SELECT c.id, c.document_id, c.anchor, c.text, c.quarantined
                FROM chunks c
                JOIN documents d ON d.id = c.document_id
                JOIN sources s ON s.id = d.source_id
                WHERE c.anchor=$1
                  AND d.doc_id=$2
                  AND s.url=$3
                  AND s.source_type='bare_act'
                  AND c.as_at IS NULL
                """,
                anchor,
                target["document_id"],
                target["source_url"],
            )
            if len(rows) != 1:
                raise RuntimeError(
                    f"refusing quarantine: expected one exact target for {anchor}, found {len(rows)}"
                )
            row = rows[0]
            text_sha256 = hashlib.sha256(row["text"].encode()).hexdigest()
            if text_sha256 != target["expected_text_sha256"]:
                raise RuntimeError(
                    f"refusing quarantine: text fingerprint mismatch for {anchor}: "
                    f"{text_sha256} != {target['expected_text_sha256']}"
                )
            return row

        if dry_run:
            row = await fetch_exact_target()
            return {
                "anchor": anchor,
                "chunk_id": row["id"],
                "action": "no_op" if row["quarantined"] else "would_quarantine",
                "already_quarantined": bool(row["quarantined"]),
            }

        async with conn.transaction():
            row = await fetch_exact_target()
            if row["quarantined"]:
                return {
                    "anchor": anchor,
                    "chunk_id": row["id"],
                    "action": "no_op",
                    "already_quarantined": True,
                }
            result = await conn.execute(
                """
                UPDATE chunks
                SET quarantined=true,
                    quarantine_reason=$1,
                    provenance_verified=false,
                    provenance_verified_at=NULL
                WHERE id=$2
                  AND document_id=$3
                  AND anchor=$4
                  AND as_at IS NULL
                  AND quarantined=false
                  AND text=$5
                """,
                target["reason"],
                row["id"],
                row["document_id"],
                row["anchor"],
                row["text"],
            )
            if result != "UPDATE 1":
                raise RuntimeError(f"refusing quarantine: exact target changed during transaction for {anchor}")
            document_result = await conn.execute(
                "UPDATE documents SET provenance_verified=false, provenance_verified_at=NULL WHERE id=$1",
                row["document_id"],
            )
            if document_result != "UPDATE 1":
                raise RuntimeError(f"refusing quarantine: document state update failed for {anchor}")
        return {
            "anchor": anchor,
            "chunk_id": row["id"],
            "action": "quarantine",
            "already_quarantined": False,
        }
    finally:
        await conn.close()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--anchor", choices=sorted(TARGETS), default="registration-1908/sec-3__3-d")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    result = asyncio.run(quarantine(args.anchor, dry_run=args.dry_run))
    print(f"{result['action']} {result['anchor']} chunk={result['chunk_id']}")


if __name__ == "__main__":
    main()
