from __future__ import annotations

import hashlib
from dataclasses import replace
from pathlib import Path

import asyncpg
import pytest
from apps.api import retrieval
from apps.api.config import Settings
from apps.api.retrieval import _fetch_source_pack_candidates
from apps.api.source_packs import SourcePack

from authority_registry.ingest import AuthorityMigrationConflict, apply_authority_migration
from authority_registry.loader import (
    LoadedAuthorityMigration,
    load_authority_migrations,
    load_authority_registry,
)
from authority_registry.model import AuthorityMigration

ZERO_HALFVEC_1024 = "[" + ",".join("0" for _ in range(1024)) + "]"

LEGACY_SCHEMA_SQL = """
CREATE TABLE schema_migrations (
    version TEXT PRIMARY KEY,
    applied_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE TABLE sources (
    id BIGSERIAL PRIMARY KEY,
    source_type TEXT NOT NULL,
    origin TEXT NOT NULL,
    url TEXT NOT NULL,
    canonical_url_hash TEXT NOT NULL UNIQUE,
    raw_storage_uri TEXT,
    fetched_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb
);
CREATE TABLE documents (
    id BIGSERIAL PRIMARY KEY,
    source_id BIGINT NOT NULL REFERENCES sources(id) ON DELETE CASCADE,
    doc_id TEXT NOT NULL UNIQUE,
    title TEXT,
    court TEXT,
    citation TEXT,
    statute_short TEXT,
    statute_year INT,
    as_at DATE,
    subject_area TEXT,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb
);
CREATE TABLE chunks (
    id BIGSERIAL PRIMARY KEY,
    document_id BIGINT NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    source_type TEXT NOT NULL,
    subject_area TEXT,
    anchor TEXT NOT NULL,
    paragraph_no INT,
    text TEXT NOT NULL,
    token_count INT NOT NULL,
    chunk_strategy TEXT NOT NULL DEFAULT 'numbered_paragraph',
    embedding halfvec(1024),
    embedding_sparse JSONB,
    as_at DATE,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    quarantined BOOLEAN NOT NULL DEFAULT false,
    text_tsv TSVECTOR GENERATED ALWAYS AS (to_tsvector('english', text)) STORED
);
"""


async def _fixture_embed(_text: str) -> tuple[str, str]:
    return ZERO_HALFVEC_1024, "{}"


async def _broken_embed(_text: str) -> tuple[str, str]:
    raise RuntimeError("deliberate embedding failure")


class _ConnectionPool:
    def __init__(self, conn: asyncpg.Connection):
        self.conn = conn

    def acquire(self):
        conn = self.conn

        class _Context:
            async def __aenter__(self):
                return conn

            async def __aexit__(self, exc_type, exc, tb):
                return False

        return _Context()


@pytest.mark.needs_stack
@pytest.mark.asyncio
async def test_rbi_authority_family_real_postgres_contract():
    settings = Settings()
    conn = await asyncpg.connect(dsn=settings.resolved_database_url_host_side)
    outer = conn.transaction()
    await outer.start()
    try:
        await conn.execute("DROP SCHEMA IF EXISTS authority_registry_rbi_test CASCADE")
        await conn.execute("CREATE SCHEMA authority_registry_rbi_test")
        await conn.execute("SET LOCAL search_path TO authority_registry_rbi_test, public")
        await conn.execute(LEGACY_SCHEMA_SQL)
        await conn.execute(Path("infra/postgres/migrations/005_authority_registry.sql").read_text())

        migrations = load_authority_migrations()
        assert [item.manifest.migration_id for item in migrations] == [
            "0001_crpc_436a",
            "0002_rbi_grievance_family",
            "0003_it_act_private_image",
            "0004_it_act_66e_verbatim_correction",
            "0005_bns_extortion",
            "0006_custody_authority_family",
            "0007_custody_answer_citation_policy",
        ]
        result = await apply_authority_migration(conn, migrations[0], embed=_fixture_embed)
        assert result.status == "applied"

        rbi_record = migrations[1].manifest.operations[0].record
        legacy_source_id = await conn.fetchval(
            """
            INSERT INTO sources (
                source_type, origin, url, canonical_url_hash, provenance_tier,
                raw_sha256, raw_bytes_size
            ) VALUES ('bare_act', 'rbi', $1, $2, 'canonical', $3, $4)
            RETURNING id
            """,
            rbi_record.canonical_url,
            hashlib.sha256(rbi_record.canonical_url.encode()).hexdigest(),
            rbi_record.provenance.raw_sha256,
            rbi_record.provenance.raw_bytes_size,
        )
        legacy_document_id = await conn.fetchval(
            """
            INSERT INTO documents (
                source_id, doc_id, title, statute_short, statute_year,
                subject_area, as_at, provenance_verified
            ) VALUES ($1, $2, $3, $3, 2021, 'consumer', '2021-11-12', true)
            RETURNING id
            """,
            legacy_source_id,
            rbi_record.doc_id,
            rbi_record.title,
        )
        await conn.execute(
            """
            INSERT INTO chunks (
                document_id, source_type, subject_area, anchor, text,
                token_count, as_at, provenance_verified
            ) VALUES ($1, 'bare_act', 'consumer', $2, $3, 6, '2021-11-12', true)
            """,
            legacy_document_id,
            f"{rbi_record.doc_id}/sec-1",
            "Legacy 2021 Scheme snapshot",
        )

        result = await apply_authority_migration(conn, migrations[1], embed=_fixture_embed)
        assert result.status == "applied"

        rbi = migrations[1]
        assert (
            await conn.fetchval(
                "SELECT COUNT(*) FROM document_authorities WHERE migration_id = $1",
                rbi.manifest.migration_id,
            )
            == 8
        )
        rows = await conn.fetch(
            """
            SELECT da.canonical_key, s.origin, d.doc_id, c.anchor,
                   d.provenance_verified AS document_verified,
                   c.provenance_verified AS chunk_verified
            FROM document_authorities da
            JOIN sources s ON s.id = da.source_id
            JOIN documents d ON d.id = da.document_id
            JOIN chunks c ON c.id = da.chunk_id
            WHERE da.migration_id = $1
            ORDER BY c.anchor
            """,
            rbi.manifest.migration_id,
        )
        assert {row["canonical_key"] for row in rows} == {
            "rbi_integrated_ombudsman_2021_clause_1",
            "rbi_integrated_ombudsman_2021_clause_3",
            "rbi_integrated_ombudsman_2021_clause_6",
            "rbi_integrated_ombudsman_2021_clause_9",
            "rbi_integrated_ombudsman_2021_clause_10",
            "rbi_digital_lending_2025_paragraph_11",
            "rbi_digital_lending_2025_paragraph_12",
            "rbi_recovery_agents_2022_paragraph_2",
        }
        assert {row["origin"] for row in rows} == {"rbi"}
        assert {row["doc_id"] for row in rows} == {
            "rbi-integrated-ombudsman-2021",
            "rbi-digital-lending-directions-2025",
            "rbi-recovery-agents-2022",
        }
        assert {row["anchor"] for row in rows} == {
            "rbi-integrated-ombudsman-2021/sec-1@2022-08-05",
            "rbi-integrated-ombudsman-2021/sec-3@2022-08-05",
            "rbi-integrated-ombudsman-2021/sec-6@2022-08-05",
            "rbi-integrated-ombudsman-2021/sec-9@2022-08-05",
            "rbi-integrated-ombudsman-2021/sec-10@2022-08-05",
            "rbi-digital-lending-directions-2025/para-11",
            "rbi-digital-lending-directions-2025/para-12",
            "rbi-recovery-agents-2022/para-2",
        }
        assert all(
            row["document_verified"] is (row["doc_id"] == "rbi-integrated-ombudsman-2021")
            for row in rows
        )
        assert all(row["chunk_verified"] is False for row in rows)
        historical = await conn.fetchrow(
            """
            SELECT quarantined, provenance_verified, as_at
            FROM chunks
            WHERE document_id = $1 AND anchor = $2
            """,
            legacy_document_id,
            f"{rbi_record.doc_id}/sec-1",
        )
        assert historical is not None
        assert historical["quarantined"] is False
        assert historical["provenance_verified"] is True
        assert str(historical["as_at"]) == "2021-11-12"

        no_op = await apply_authority_migration(conn, rbi, embed=_fixture_embed)
        assert no_op.status == "no_op"
        assert no_op.records_applied == 0

        private_image = migrations[2]
        result = await apply_authority_migration(
            conn,
            private_image,
            embed=_fixture_embed,
        )
        assert result.status == "applied"
        it_row = await conn.fetchrow(
            """
            SELECT da.authority_id, da.canonical_key, s.origin, s.provenance_tier,
                   s.raw_sha256, s.raw_bytes_size, d.doc_id, c.anchor,
                   c.provenance_verified
            FROM document_authorities da
            JOIN sources s ON s.id = da.source_id
            JOIN documents d ON d.id = da.document_id
            JOIN chunks c ON c.id = da.chunk_id
            WHERE da.migration_id = $1
            """,
            private_image.manifest.migration_id,
        )
        assert it_row is not None
        assert it_row["authority_id"] == "authority_ad90922325a79b902a63"
        assert it_row["canonical_key"] == "information_technology_act_2000_section_66e"
        assert it_row["origin"] == "indiacode"
        assert it_row["provenance_tier"] == "canonical"
        assert it_row["raw_sha256"] == (
            "e71725fa32e892f887308816046c42275fc855b5cbb4ee1063cdbd518f165140"
        )
        assert it_row["raw_bytes_size"] == 832355
        assert it_row["doc_id"] == "it-2000"
        assert it_row["anchor"] == "it-2000/sec-66E"
        assert it_row["provenance_verified"] is False

        no_op = await apply_authority_migration(
            conn,
            private_image,
            embed=_fixture_embed,
        )
        assert no_op.status == "no_op"
        assert no_op.records_applied == 0

        correction = migrations[3]
        result = await apply_authority_migration(
            conn,
            correction,
            embed=_fixture_embed,
        )
        assert result.status == "applied"
        corrected = await conn.fetchrow(
            """
            SELECT da.migration_id, da.record_sha256, c.text,
                   c.provenance_verified, c.metadata->>'text_sha256' AS text_sha256
            FROM document_authorities da
            JOIN chunks c ON c.id = da.chunk_id
            WHERE da.authority_id = 'authority_ad90922325a79b902a63'
            """
        )
        assert corrected["migration_id"] == "0004_it_act_66e_verbatim_correction"
        assert corrected["record_sha256"] == (
            load_authority_registry()
            .by_key("information_technology_act_2000_section_66e")
            .record_sha256
        )
        assert corrected["text_sha256"] == (
            "24957549caaf03e1e8d323c66863d43c7830fd93658cbcd70c74509e89ecde19"
        )
        assert "regardless of whether that person is in a public or private place" in (
            corrected["text"]
        )
        assert corrected["provenance_verified"] is False

        bns_extortion = migrations[4]
        result = await apply_authority_migration(
            conn,
            bns_extortion,
            embed=_fixture_embed,
        )
        assert result.status == "applied"
        bns_row = await conn.fetchrow(
            """
            SELECT da.authority_id, da.canonical_key, s.origin, s.provenance_tier,
                   s.raw_sha256, s.raw_bytes_size, d.doc_id, c.anchor,
                   c.provenance_verified
            FROM document_authorities da
            JOIN sources s ON s.id = da.source_id
            JOIN documents d ON d.id = da.document_id
            JOIN chunks c ON c.id = da.chunk_id
            WHERE da.migration_id = $1
            """,
            bns_extortion.manifest.migration_id,
        )
        assert bns_row is not None
        assert bns_row["authority_id"] == "authority_1377e9f3337ec9d06de0"
        assert bns_row["canonical_key"] == "bharatiya_nyaya_sanhita_2023_section_308"
        assert bns_row["origin"] == "indiacode"
        assert bns_row["provenance_tier"] == "canonical"
        assert bns_row["raw_sha256"] == (
            "ff92dcc72778944011807644b6033b1140ddbe6d7e9f82ac32fd419dae03aa86"
        )
        assert bns_row["raw_bytes_size"] == 896392
        assert bns_row["doc_id"] == "bns-2023"
        assert bns_row["anchor"] == "bns-2023/sec-308"
        assert bns_row["provenance_verified"] is False
    finally:
        await outer.rollback()
        await conn.close()


@pytest.mark.needs_stack
@pytest.mark.asyncio
async def test_authority_migration_real_postgres_contract(monkeypatch):  # noqa: PLR0915
    settings = Settings()
    conn = await asyncpg.connect(dsn=settings.resolved_database_url_host_side)
    outer = conn.transaction()
    await outer.start()
    try:
        await conn.execute("DROP SCHEMA IF EXISTS authority_registry_upgrade_test CASCADE")
        await conn.execute("CREATE SCHEMA authority_registry_upgrade_test")
        await conn.execute("SET LOCAL search_path TO authority_registry_upgrade_test, public")
        await conn.execute(LEGACY_SCHEMA_SQL)
        await conn.execute(Path("infra/postgres/migrations/005_authority_registry.sql").read_text())
        for table_name, column_name in (
            ("sources", "raw_sha256"),
            ("sources", "raw_bytes_size"),
            ("sources", "provenance_tier"),
            ("documents", "provenance_verified"),
            ("documents", "provenance_verified_at"),
            ("chunks", "provenance_verified"),
            ("chunks", "provenance_verified_at"),
        ):
            assert await conn.fetchval(
                """
                SELECT EXISTS (
                    SELECT 1 FROM information_schema.columns
                    WHERE table_schema = current_schema()
                      AND table_name = $1 AND column_name = $2
                )
                """,
                table_name,
                column_name,
            )
        assert await conn.fetchval("SELECT to_regclass('provenance_audit')") is not None
        try:
            loaded = load_authority_migrations()[0]
            await conn.execute(
                "DELETE FROM document_authorities WHERE migration_id = $1",
                loaded.manifest.migration_id,
            )
            await conn.execute(
                "DELETE FROM authority_ingest_migrations WHERE migration_id = $1",
                loaded.manifest.migration_id,
            )

            first = await apply_authority_migration(conn, loaded, embed=_fixture_embed)
            assert first.status == "applied"

            await conn.execute(
                "UPDATE documents SET provenance_verified = true WHERE doc_id = 'crpc-1973'"
            )
            await conn.execute(
                """
                UPDATE sources SET origin = 'legacy_wrong_origin'
                WHERE id = (
                    SELECT source_id FROM document_authorities WHERE migration_id = $1
                )
                """,
                loaded.manifest.migration_id,
            )
            await conn.execute(
                "DELETE FROM document_authorities WHERE migration_id = $1",
                loaded.manifest.migration_id,
            )
            await conn.execute(
                "DELETE FROM authority_ingest_migrations WHERE migration_id = $1",
                loaded.manifest.migration_id,
            )

            reapplied = await apply_authority_migration(conn, loaded, embed=_fixture_embed)
            second = await apply_authority_migration(conn, loaded, embed=_fixture_embed)
            assert reapplied.status == "applied"
            assert second.status == "no_op"

            row = await conn.fetchrow(
                """
                SELECT da.authority_id, da.canonical_key, d.doc_id, c.id AS chunk_id, c.anchor,
                       d.provenance_verified AS document_verified,
                       c.provenance_verified AS chunk_verified,
                       s.origin, s.raw_sha256, s.raw_bytes_size,
                       c.metadata->>'text_sha256' AS text_sha256
                FROM document_authorities da
                JOIN sources s ON s.id = da.source_id
                JOIN documents d ON d.id = da.document_id
                JOIN chunks c ON c.id = da.chunk_id
                WHERE da.migration_id = $1
            """,
                loaded.manifest.migration_id,
            )
            assert row is not None
            assert row["authority_id"] == "authority_348b7d2511bb3e5a2618"
            assert row["canonical_key"] == "crpc_1973_section_436a"
            assert row["doc_id"] == "crpc-1973"
            assert row["anchor"] == "crpc-1973/sec-436-a"
            assert row["document_verified"] is True
            assert row["chunk_verified"] is False
            assert row["origin"] == "indiacode"
            assert row["raw_sha256"] == (
                "2f28d487c18d33f65195d7ab99cb5dc8fd4dcf232c7deb18dee7f8fa289891b9"
            )
            assert row["raw_bytes_size"] == 1660268
            assert row["text_sha256"] == (
                "af5b7c0357534a32522f3249c0d4f8185d5d612318259a8e931348ae8e6c98bb"
            )

            pack = SourcePack(
                id="crpc_1973",
                title_patterns=("Code of Criminal Procedure 1973",),
                doc_ids=("crpc-1973",),
                anchor_patterns=("/sec-436-a",),
                search_query=(
                    "Code of Criminal Procedure 1973 section 436A "
                    "undertrial detention half maximum sentence"
                ),
            )
            monkeypatch.setattr(
                retrieval,
                "get_settings",
                lambda: Settings(require_provenance_verified=True),
            )
            pool = _ConnectionPool(conn)
            hidden = await _fetch_source_pack_candidates(
                pool,
                "undertrial detained for half the maximum sentence",
                packs=[pack],
                limit_per_pack=4,
            )
            assert hidden == []

            await conn.execute(
                "UPDATE chunks SET provenance_verified = true WHERE id = $1",
                row["chunk_id"],
            )
            visible = await _fetch_source_pack_candidates(
                pool,
                "undertrial detained for half the maximum sentence",
                packs=[pack],
                limit_per_pack=4,
            )
            assert [chunk.anchor for chunk in visible] == ["crpc-1973/sec-436-a"]

            original_record = loaded.manifest.operations[0].record
            corrected_record = original_record.model_copy(
                update={
                    "doc_id": "crpc-1973-corrected",
                    "provision": original_record.provision.model_copy(
                        update={
                            "canonical_anchor": "/sec-436-a-corrected",
                            "anchor_aliases": (),
                        }
                    ),
                    "retrieval": original_record.retrieval.model_copy(
                        update={
                            "doc_ids": ("crpc-1973-corrected",),
                        }
                    ),
                }
            )
            correction_manifest = AuthorityMigration.model_validate(
                {
                    "migration_id": "0002_crpc_436a_projection_correction",
                    "schema_version": 1,
                    "operations": [
                        {
                            "op": "upsert",
                            "record": corrected_record.model_dump(mode="json"),
                            "expected_previous_record_sha256": original_record.record_sha256,
                        }
                    ],
                }
            )
            correction = LoadedAuthorityMigration(
                path="test://0002_crpc_436a_projection_correction",
                manifest=correction_manifest,
                manifest_sha256="e" * 64,
            )
            correction_result = await apply_authority_migration(
                conn,
                correction,
                embed=_fixture_embed,
            )
            assert correction_result.status == "applied"
            assert (
                await conn.fetchval(
                    "SELECT COUNT(*) FROM document_authorities WHERE authority_id = $1",
                    original_record.authority_id_expected,
                )
                == 1
            )
            moved = await conn.fetchrow(
                """
                SELECT da.document_id, da.chunk_id, d.doc_id, c.anchor,
                       c.provenance_verified, c.quarantined
                FROM document_authorities da
                JOIN documents d ON d.id = da.document_id
                JOIN chunks c ON c.id = da.chunk_id
                WHERE da.authority_id = $1
                """,
                original_record.authority_id_expected,
            )
            assert moved["doc_id"] == "crpc-1973-corrected"
            assert moved["anchor"] == "crpc-1973-corrected/sec-436-a-corrected"
            assert moved["provenance_verified"] is False
            assert moved["quarantined"] is False
            retired = await conn.fetchrow(
                """
                SELECT provenance_verified, quarantined
                FROM chunks WHERE id = $1
                """,
                row["chunk_id"],
            )
            assert retired["provenance_verified"] is False
            assert retired["quarantined"] is True

            await conn.execute(
                "UPDATE chunks SET provenance_verified = true WHERE id = $1",
                moved["chunk_id"],
            )
            corrected_pack = SourcePack(
                id="crpc_1973",
                title_patterns=("Code of Criminal Procedure 1973",),
                doc_ids=("crpc-1973-corrected",),
                anchor_patterns=("/sec-436-a-corrected",),
                search_query=(
                    "Code of Criminal Procedure 1973 section 436A "
                    "undertrial detention half maximum sentence"
                ),
            )
            corrected_visible = await _fetch_source_pack_candidates(
                pool,
                "undertrial detained for half the maximum sentence",
                packs=[corrected_pack],
                limit_per_pack=4,
            )
            assert [chunk.anchor for chunk in corrected_visible] == [
                "crpc-1973-corrected/sec-436-a-corrected"
            ]

            with pytest.raises(AuthorityMigrationConflict):
                await apply_authority_migration(
                    conn,
                    replace(loaded, manifest_sha256="0" * 64),
                    embed=_fixture_embed,
                )

            failed_payload = loaded.manifest.model_dump(mode="json")
            failed_payload["migration_id"] = "9999_registry_rollback_probe"
            failed = replace(
                loaded,
                manifest=AuthorityMigration.model_validate(failed_payload),
                manifest_sha256="f" * 64,
            )
            with pytest.raises(RuntimeError, match="deliberate embedding failure"):
                await apply_authority_migration(conn, failed, embed=_broken_embed)
            assert (
                await conn.fetchval(
                    "SELECT COUNT(*) FROM authority_ingest_migrations WHERE migration_id = $1",
                    failed.manifest.migration_id,
                )
                == 0
            )
        finally:
            await outer.rollback()
    finally:
        await conn.close()
