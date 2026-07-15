#!/usr/bin/env python3
"""Validate or transactionally apply immutable authority migrations."""

from __future__ import annotations

import argparse
import asyncio
import json
import os

import asyncpg
from apps.api.embeddings import (
    embedding_to_halfvec_literal,
    get_embedder,
    sparse_to_jsonb,
)

from authority_registry.ingest import apply_authority_migration
from authority_registry.loader import (
    ROOT,
    build_authority_registry,
    load_authority_migrations,
    reconcile_applied_migrations,
)


def load_env() -> dict[str, str]:
    values = dict(os.environ)
    env_path = ROOT / ".env"
    if env_path.exists():
        for raw_line in env_path.read_text().splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            values.setdefault(key.strip(), value.strip().strip('"').strip("'"))
    return values


async def embed(text: str) -> tuple[str, str]:
    dense, sparse = get_embedder().encode_with_sparse([text])
    return embedding_to_halfvec_literal(dense[0]), sparse_to_jsonb(sparse[0])


async def run(*, dry_run: bool, migration_id: str | None) -> None:
    migrations = load_authority_migrations()
    build_authority_registry(migrations)
    if dry_run:
        if migration_id:
            migrations = reconcile_applied_migrations(
                migrations,
                [],
                through_migration_id=migration_id,
            )
        print(
            json.dumps(
                [
                    {
                        "migration_id": loaded.manifest.migration_id,
                        "manifest_sha256": loaded.manifest_sha256,
                        "records": [
                            operation.record.canonical_key
                            for operation in loaded.manifest.operations
                        ],
                    }
                    for loaded in migrations
                ],
                indent=2,
            )
        )
        return

    env = load_env()
    conn = await asyncpg.connect(
        host=env.get("POSTGRES_HOST_SIDE", "localhost"),
        port=int(env["POSTGRES_HOST_PORT"]),
        database=env["POSTGRES_DB"],
        user=env["POSTGRES_USER"],
        password=env["POSTGRES_PASSWORD"],
    )
    try:
        schema_sql = (
            ROOT / "infra" / "postgres" / "migrations" / "005_authority_registry.sql"
        ).read_text()
        await conn.execute(schema_sql)
        applied_rows = await conn.fetch("""
            SELECT migration_id, manifest_sha256
            FROM authority_ingest_migrations
            ORDER BY migration_id
        """)
        pending = reconcile_applied_migrations(
            migrations,
            [(row["migration_id"], row["manifest_sha256"]) for row in applied_rows],
            through_migration_id=migration_id,
        )
        for loaded in pending:
            result = await apply_authority_migration(conn, loaded, embed=embed)
            print(json.dumps(result.__dict__, sort_keys=True))
        if not pending:
            print(
                json.dumps(
                    {
                        "status": "no_op",
                        "through_migration_id": migration_id
                        or migrations[-1].manifest.migration_id,
                    },
                    sort_keys=True,
                )
            )
    finally:
        await conn.close()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--migration")
    args = parser.parse_args()
    asyncio.run(run(dry_run=args.dry_run, migration_id=args.migration))


if __name__ == "__main__":
    main()
