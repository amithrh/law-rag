from __future__ import annotations

from contextlib import AbstractAsyncContextManager
from dataclasses import replace
from pathlib import Path

import pytest

from authority_registry.ingest import (
    AuthorityMigrationConflict,
    apply_authority_migration,
    build_projection,
)
from authority_registry.loader import load_authority_migrations


class _Transaction(AbstractAsyncContextManager):
    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False


class FakeConnection:
    def __init__(self):
        self.applied: dict[str, str] = {}
        self.executed: list[tuple[str, tuple]] = []
        self.document_id: int | None = None
        self.chunk_id: int | None = None

    def transaction(self):
        return _Transaction()

    async def fetchval(self, sql, *args):
        normalized = " ".join(sql.split())
        if "SELECT manifest_sha256" in normalized:
            return self.applied.get(args[0])
        if "INSERT INTO sources" in normalized:
            return 11
        if "SELECT id FROM documents" in normalized:
            return self.document_id
        if "INSERT INTO documents" in normalized:
            self.document_id = 22
            return self.document_id
        if "SELECT id FROM chunks" in normalized:
            return self.chunk_id
        if "INSERT INTO chunks" in normalized:
            self.chunk_id = 33
            return self.chunk_id
        raise AssertionError(f"unexpected fetchval SQL: {normalized}")

    async def fetch(self, sql, *args):
        normalized = " ".join(sql.split())
        if "FROM document_authorities" in normalized:
            return []
        raise AssertionError(f"unexpected fetch SQL: {normalized}")

    async def execute(self, sql, *args):
        normalized = " ".join(sql.split())
        self.executed.append((normalized, args))
        if "INSERT INTO authority_ingest_migrations" in normalized:
            self.applied[args[0]] = args[1]
        return "OK"


async def _embed(_text: str) -> tuple[str, str]:
    return "[0,0]", "{}"


@pytest.mark.asyncio
async def test_authority_migration_is_idempotent_and_never_self_verifies():
    loaded = load_authority_migrations()[0]
    conn = FakeConnection()
    first = await apply_authority_migration(conn, loaded, embed=_embed)
    second = await apply_authority_migration(conn, loaded, embed=_embed)
    assert first.status == "applied"
    assert first.records_applied == 1
    assert second.status == "no_op"
    assert second.records_applied == 0
    document_sql = " ".join(sql for sql, _ in conn.executed if "documents" in sql)
    assert "provenance_verified = true" not in document_sql


@pytest.mark.asyncio
async def test_same_migration_id_with_mutated_manifest_fails_closed():
    loaded = load_authority_migrations()[0]
    conn = FakeConnection()
    await apply_authority_migration(conn, loaded, embed=_embed)
    mutated = replace(loaded, manifest_sha256="0" * 64)
    with pytest.raises(AuthorityMigrationConflict, match="different hash"):
        await apply_authority_migration(conn, mutated, embed=_embed)


def test_projection_contains_stable_authority_and_provenance_declaration():
    record = load_authority_migrations()[0].manifest.operations[0].record
    projection = build_projection(record)
    assert "authority_id" not in projection.source_metadata
    assert "authority_id" not in projection.document_metadata
    assert "authority_registry_key" not in projection.document_metadata
    assert "text_sha256" not in projection.document_metadata
    assert projection.chunk_metadata["authority_id"] == record.authority_id_expected
    assert projection.chunk_metadata["text_sha256"] == record.text_sha256
    assert "status" not in projection.source_metadata["provenance_declaration"]
    assert projection.source_metadata["provenance_declaration"]["raw_sha256"] == (
        "2f28d487c18d33f65195d7ab99cb5dc8fd4dcf232c7deb18dee7f8fa289891b9"
    )


def test_fresh_database_schema_contains_registry_and_provenance_contracts():
    init_sql = Path("infra/postgres/init.sql").read_text()
    migration_sql = Path("infra/postgres/migrations/005_authority_registry.sql").read_text()
    for required in (
        "provenance_verified BOOLEAN NOT NULL DEFAULT false",
        "CREATE TABLE IF NOT EXISTS provenance_audit",
        "CREATE TABLE IF NOT EXISTS authority_ingest_migrations",
        "CREATE TABLE IF NOT EXISTS document_authorities",
    ):
        assert required in init_sql
    for required_upgrade in (
        "ADD COLUMN IF NOT EXISTS raw_sha256 TEXT",
        "ADD COLUMN IF NOT EXISTS raw_bytes_size BIGINT",
        "ADD COLUMN IF NOT EXISTS provenance_tier TEXT NOT NULL",
        "ALTER TABLE documents",
        "CREATE TABLE IF NOT EXISTS provenance_audit",
        "005_authority_registry",
    ):
        assert required_upgrade in migration_sql
