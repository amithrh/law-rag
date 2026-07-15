#!/usr/bin/env python3
"""Write a reproducible, aggregate-only snapshot of the serving corpus."""
from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

import asyncpg

from apps.api.config import Settings


ROOT = Path(__file__).resolve().parents[1]
INIT_SQL = ROOT / "infra" / "postgres" / "init.sql"
MANIFEST_VERSION = 1


def init_sql_sha256() -> str:
    return hashlib.sha256(INIT_SQL.read_bytes()).hexdigest()


def runtime_manifest(settings: Settings) -> dict[str, Any]:
    return {
        "embedding_backend": settings.embedding_backend,
        "embedding_model": settings.embedding_model,
        "embedding_runtime": settings.embedding_runtime,
        "embedding_dim": settings.embedding_dim,
        "rerank_enabled": settings.rerank_enabled,
        "rerank_model": settings.rerank_model,
        "rerank_model_path": settings.rerank_model_path or None,
        "llm_model": settings.llm_model,
        "require_provenance_verified": settings.require_provenance_verified,
    }


def build_manifest(*, settings: Settings, database: dict[str, Any] | None) -> dict[str, Any]:
    return {
        "manifest_version": MANIFEST_VERSION,
        "generated_at": datetime.now(UTC).isoformat(),
        "schema": {
            "management": "bootstrap_sql_no_migration_table",
            "init_sql_path": str(INIT_SQL.relative_to(ROOT)),
            "init_sql_sha256": init_sql_sha256(),
        },
        "runtime": runtime_manifest(settings),
        "database": database,
    }


async def database_manifest(dsn: str) -> dict[str, Any]:
    conn = await asyncpg.connect(dsn)
    try:
        has_provenance = await conn.fetchval(
            """
            SELECT EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_schema = 'public'
                  AND table_name = 'documents'
                  AND column_name = 'provenance_verified'
            )
            """
        )
        document_count = await conn.fetchval("SELECT COUNT(*) FROM documents")
        active_chunk_count = await conn.fetchval(
            "SELECT COUNT(*) FROM chunks WHERE NOT quarantined"
        )
        source_snapshot = await conn.fetchrow(
            """
            SELECT
                MAX(s.fetched_at) AS latest_source_fetched_at,
                MAX(d.created_at) AS latest_document_created_at,
                MAX(d.as_at) AS latest_document_as_at
            FROM documents d
            JOIN sources s ON s.id = d.source_id
            """
        )
        embedding_models = await conn.fetch(
            """
            SELECT embedding_model, embedding_version, COUNT(*) AS chunk_count
            FROM chunks
            WHERE NOT quarantined
            GROUP BY embedding_model, embedding_version
            ORDER BY chunk_count DESC, embedding_model, embedding_version
            """
        )
        provenance: list[dict[str, Any]] | None = None
        if has_provenance:
            rows = await conn.fetch(
                """
                SELECT provenance_verified, COUNT(*) AS document_count
                FROM documents
                GROUP BY provenance_verified
                ORDER BY provenance_verified NULLS FIRST
                """
            )
            provenance = [dict(row) for row in rows]
        return {
            "document_count": int(document_count),
            "active_chunk_count": int(active_chunk_count),
            "source_snapshot": dict(source_snapshot) if source_snapshot else {},
            "embedding_models": [dict(row) for row in embedding_models],
            "provenance_by_document": provenance,
        }
    finally:
        await conn.close()


def json_default(value: object) -> str:
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    raise TypeError(f"Cannot serialize {type(value)!r}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, help="Write JSON to this path instead of stdout.")
    parser.add_argument("--database-url", help="Override DATABASE_URL for this one snapshot.")
    parser.add_argument(
        "--offline",
        action="store_true",
        help="Record runtime/schema metadata without connecting to Postgres.",
    )
    return parser.parse_args()


async def run(args: argparse.Namespace) -> dict[str, Any]:
    settings = Settings()
    if args.offline:
        database = None
    else:
        dsn = args.database_url or settings.resolved_database_url_host_side
        database = await database_manifest(dsn)
    return build_manifest(settings=settings, database=database)


def main() -> int:
    args = parse_args()
    manifest = asyncio.run(run(args))
    rendered = json.dumps(manifest, indent=2, sort_keys=True, default=json_default) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered)
        print(args.output)
    else:
        print(rendered, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
