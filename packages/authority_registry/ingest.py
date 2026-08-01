"""Transactional projection of immutable authority migrations into the corpus."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from .loader import LoadedAuthorityMigration
from .model import AuthorityRecord

EmbeddingProvider = Callable[[str], Awaitable[tuple[str, str]]]


class AuthorityMigrationConflict(RuntimeError):
    pass


@dataclass(frozen=True)
class AuthorityProjection:
    canonical_url_hash: str
    source_metadata: dict
    document_metadata: dict
    chunk_metadata: dict


@dataclass(frozen=True)
class AuthorityMigrationResult:
    migration_id: str
    manifest_sha256: str
    status: str
    records_applied: int


def build_projection(record: AuthorityRecord) -> AuthorityProjection:
    source_metadata = {
        "canonical_url": record.canonical_url,
        "publisher": record.publisher.model_dump(mode="json"),
        "provenance_declaration": record.provenance.model_dump(mode="json"),
        "registry_projection": "source",
    }
    document_metadata = {
        "canonical_url": record.canonical_url,
        "jurisdiction": record.jurisdiction.model_dump(mode="json"),
        "consolidation_as_at": (
            record.consolidation_as_at.isoformat() if record.consolidation_as_at else None
        ),
        "registry_projection": "document",
    }
    provision_metadata = {
        "authority_registry_key": record.canonical_key,
        "authority_id": record.authority_id_expected,
        "authority_record_sha256": record.record_sha256,
        "effective_from": record.effective_from.isoformat(),
        "effective_to": record.effective_to.isoformat() if record.effective_to else None,
        "consolidation_as_at": (
            record.consolidation_as_at.isoformat() if record.consolidation_as_at else None
        ),
        "savings": record.savings.model_dump(mode="json") if record.savings else None,
        "verbatim_status": record.verbatim_status,
        "text_sha256": record.text_sha256,
    }
    return AuthorityProjection(
        canonical_url_hash=hashlib.sha256(record.canonical_url.encode("utf-8")).hexdigest(),
        source_metadata=source_metadata,
        document_metadata=document_metadata,
        chunk_metadata={
            **provision_metadata,
            "registry_projection": "chunk",
            "section_no": record.provision.number,
            "section_title": record.provision.heading,
            "text_is_verbatim": record.verbatim_status in {"declared", "verified"},
        },
    )


async def apply_authority_migration(
    conn,
    loaded: LoadedAuthorityMigration,
    *,
    embed: EmbeddingProvider,
) -> AuthorityMigrationResult:
    migration = loaded.manifest
    async with conn.transaction():
        existing_hash = await conn.fetchval(
            """
            SELECT manifest_sha256
            FROM authority_ingest_migrations
            WHERE migration_id = $1
            FOR UPDATE
            """,
            migration.migration_id,
        )
        if existing_hash is not None:
            if existing_hash != loaded.manifest_sha256:
                raise AuthorityMigrationConflict(
                    f"migration {migration.migration_id} already applied with a different hash"
                )
            return AuthorityMigrationResult(
                migration_id=migration.migration_id,
                manifest_sha256=loaded.manifest_sha256,
                status="no_op",
                records_applied=0,
            )

        # Insert the migration row first so document_authorities can reference
        # it inside the same all-or-nothing transaction.
        await conn.execute(
            """
            INSERT INTO authority_ingest_migrations (migration_id, manifest_sha256)
            VALUES ($1, $2)
            """,
            migration.migration_id,
            loaded.manifest_sha256,
        )

        applied = 0
        for operation in migration.operations:
            await _project_record(
                conn,
                operation.record,
                migration_id=migration.migration_id,
                embed=embed,
            )
            applied += 1

        return AuthorityMigrationResult(
            migration_id=migration.migration_id,
            manifest_sha256=loaded.manifest_sha256,
            status="applied",
            records_applied=applied,
        )


async def _project_record(
    conn,
    record: AuthorityRecord,
    *,
    migration_id: str,
    embed: EmbeddingProvider,
) -> None:
    projection = build_projection(record)
    previous_source_hash = await conn.fetchval(
        """
        SELECT raw_sha256
        FROM sources
        WHERE canonical_url_hash = $1
        FOR UPDATE
        """,
        projection.canonical_url_hash,
    )
    existing_projections = await conn.fetch(
        """
        SELECT da.document_id, da.chunk_id, da.authority_id, da.canonical_key,
               c.as_at AS chunk_as_at
        FROM document_authorities da
        JOIN chunks c ON c.id = da.chunk_id
        WHERE da.authority_id = $1 OR da.canonical_key = $2
        FOR UPDATE
        """,
        record.authority_id_expected,
        record.canonical_key,
    )
    if len(existing_projections) > 1:
        raise AuthorityMigrationConflict(
            f"authority {record.canonical_key} has multiple active corpus projections"
        )
    existing_projection = existing_projections[0] if existing_projections else None
    if existing_projection is not None and (
        existing_projection["authority_id"] != record.authority_id_expected
        or existing_projection["canonical_key"] != record.canonical_key
    ):
        raise AuthorityMigrationConflict(f"authority identity conflict for {record.canonical_key}")
    source_id = await conn.fetchval(
        """
        INSERT INTO sources (
            source_type, origin, url, canonical_url_hash, provenance_tier,
            raw_sha256, raw_bytes_size, metadata
        ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8::jsonb)
        ON CONFLICT (canonical_url_hash) DO UPDATE
        SET source_type = EXCLUDED.source_type,
            origin = EXCLUDED.origin,
            url = EXCLUDED.url,
            provenance_tier = EXCLUDED.provenance_tier,
            raw_sha256 = EXCLUDED.raw_sha256,
            raw_bytes_size = EXCLUDED.raw_bytes_size,
            metadata = sources.metadata || EXCLUDED.metadata
        RETURNING id
        """,
        record.source_type,
        record.source_origin,
        record.canonical_url,
        projection.canonical_url_hash,
        record.provenance.tier,
        record.provenance.raw_sha256,
        record.provenance.raw_bytes_size,
        json.dumps(projection.source_metadata),
    )

    # A changed official file means every projection from that source needs a
    # fresh audit. Updating just the newly migrated provision would leave
    # neighbouring previously verified chunks eligible against bytes that have
    # not been rechecked.
    if previous_source_hash and previous_source_hash != record.provenance.raw_sha256:
        await conn.execute(
            """
            UPDATE chunks
            SET provenance_verified = false, provenance_verified_at = NULL
            WHERE document_id IN (SELECT id FROM documents WHERE source_id = $1)
            """,
            source_id,
        )
        await conn.execute(
            """
            UPDATE documents
            SET provenance_verified = false, provenance_verified_at = NULL
            WHERE source_id = $1
            """,
            source_id,
        )

    document_id = await conn.fetchval(
        "SELECT id FROM documents WHERE doc_id = $1 FOR UPDATE",
        record.doc_id,
    )
    if document_id is None:
        document_id = await conn.fetchval(
            """
            INSERT INTO documents (
                source_id, doc_id, title, statute_short, statute_year,
                subject_area, as_at, metadata, provenance_verified
            ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8::jsonb, false)
            RETURNING id
            """,
            source_id,
            record.doc_id,
            record.title,
            record.statute,
            record.year,
            record.subject_area,
            record.consolidation_as_at,
            json.dumps(projection.document_metadata),
        )
    else:
        # Provision projection changes are verified at chunk scope. Preserve
        # an existing whole-document verdict for all untouched provisions.
        await conn.execute(
            """
            UPDATE documents
            SET source_id = $1,
                title = $2,
                statute_short = $3,
                statute_year = $4,
                subject_area = $5,
                as_at = $6,
                metadata = metadata || $7::jsonb
            WHERE id = $8
            """,
            source_id,
            record.title,
            record.statute,
            record.year,
            record.subject_area,
            record.consolidation_as_at,
            json.dumps(projection.document_metadata),
            document_id,
        )

    version_suffix = (
        f"@{record.consolidation_as_at.isoformat()}"
        if record.consolidation_as_at is not None
        else ""
    )
    anchors = tuple(
        f"{record.doc_id}{anchor}{version_suffix}"
        for anchor in record.provision.all_anchors
    )
    chunk_rows = await conn.fetch(
        """
        SELECT id
        FROM chunks
        WHERE document_id = $1 AND anchor = ANY($2::text[])
        ORDER BY id
        FOR UPDATE
        """,
        document_id,
        list(anchors),
    )
    if len(chunk_rows) > 1:
        raise RuntimeError(
            f"authority {record.canonical_key} has duplicate live chunk projections"
        )
    chunk_id = chunk_rows[0]["id"] if chunk_rows else None
    dense, sparse = await embed(record.text)
    canonical_anchor = (
        f"{record.doc_id}{record.provision.canonical_anchor}{version_suffix}"
    )
    if chunk_id is None:
        chunk_id = await conn.fetchval(
            """
            INSERT INTO chunks (
                document_id, source_type, subject_area, anchor, paragraph_no,
                text, token_count, chunk_strategy, embedding, embedding_sparse,
                as_at, metadata
            ) VALUES (
                $1, $2, $3, $4, NULL, $5, $6, 'section', $7::halfvec,
                $8::jsonb, $9, $10::jsonb
            )
            RETURNING id
            """,
            document_id,
            record.source_type,
            record.subject_area,
            canonical_anchor,
            record.text,
            len(record.text.split()),
            dense,
            sparse,
            record.consolidation_as_at,
            json.dumps(projection.chunk_metadata),
        )
    else:
        await conn.execute(
            """
            UPDATE chunks
            SET source_type = $1,
                subject_area = $2,
                anchor = $3,
                paragraph_no = NULL,
                text = $4,
                token_count = $5,
                chunk_strategy = 'section',
                embedding = $6::halfvec,
                embedding_sparse = $7::jsonb,
                as_at = $8,
                quarantined = false,
                provenance_verified = false,
                provenance_verified_at = NULL,
                metadata = metadata || $9::jsonb
            WHERE id = $10
            """,
            record.source_type,
            record.subject_area,
            canonical_anchor,
            record.text,
            len(record.text.split()),
            dense,
            sparse,
            record.consolidation_as_at,
            json.dumps(projection.chunk_metadata),
            chunk_id,
        )

    # A dated correction replaces an undated legacy projection for the same
    # provision. Keep explicitly dated historical snapshots: they may be the
    # legally correct version for an earlier event date and must remain
    # available to temporal retrieval.
    if record.consolidation_as_at is not None:
        retired_anchors = [
            f"{record.doc_id}{anchor}"
            for anchor in (
                record.provision.canonical_anchor,
                f"{record.provision.canonical_anchor}-official",
                *record.provision.anchor_aliases,
            )
        ]
        await conn.execute(
            """
            UPDATE chunks AS c
            SET quarantined = true,
                provenance_verified = false,
                provenance_verified_at = NULL,
                metadata = (c.metadata || $1::jsonb)
                    || jsonb_build_object(
                        'authority_projection_retired_by_migration',
                        COALESCE(
                            c.metadata->>'authority_projection_retired_by_migration',
                            $5
                        )
                    )
            WHERE c.document_id = $2
              AND c.id <> $3
              AND EXISTS (
                  SELECT 1
                  FROM unnest($4::text[]) AS retired(anchor)
                  WHERE c.anchor = retired.anchor
                     OR c.anchor LIKE retired.anchor || '@%'
              )
              AND c.as_at IS NULL
            """,
            json.dumps(
                {
                    "authority_projection_retired": True,
                    "authority_projection_replaced_by_chunk_id": chunk_id,
                }
            ),
            document_id,
            chunk_id,
            retired_anchors,
            migration_id,
        )

    replaces_same_snapshot = (
        existing_projection is not None
        and existing_projection["chunk_as_at"] == record.consolidation_as_at
    )
    if (
        existing_projection is not None
        and existing_projection["chunk_id"] != chunk_id
        and replaces_same_snapshot
    ):
        await conn.execute(
            """
            UPDATE chunks
            SET quarantined = true,
                provenance_verified = false,
                provenance_verified_at = NULL,
                metadata = metadata || $1::jsonb
            WHERE id = $2
            """,
            json.dumps(
                {
                    "authority_projection_retired": True,
                    "authority_projection_replaced_by_chunk_id": chunk_id,
                    "authority_projection_retired_by_migration": migration_id,
                }
            ),
            existing_projection["chunk_id"],
        )

    await conn.execute(
        """
        INSERT INTO document_authorities (
            source_id, document_id, chunk_id, authority_id, canonical_key, migration_id,
            record_sha256, canonical_anchor
        ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
        ON CONFLICT (authority_id) DO UPDATE
        SET source_id = EXCLUDED.source_id,
            document_id = EXCLUDED.document_id,
            chunk_id = EXCLUDED.chunk_id,
            canonical_key = EXCLUDED.canonical_key,
            migration_id = EXCLUDED.migration_id,
            record_sha256 = EXCLUDED.record_sha256,
            canonical_anchor = EXCLUDED.canonical_anchor
        """,
        source_id,
        document_id,
        chunk_id,
        record.authority_id_expected,
        record.canonical_key,
        migration_id,
        record.record_sha256,
        canonical_anchor,
    )
