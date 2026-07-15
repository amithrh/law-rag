-- Migration 005: immutable authority-manifest projection ledger.
--
-- The JSON migration manifests remain canonical. These tables only prove
-- which exact manifest and authority record produced a corpus document/chunk.

CREATE TABLE IF NOT EXISTS authority_ingest_migrations (
    migration_id       TEXT PRIMARY KEY,
    manifest_sha256    TEXT NOT NULL,
    applied_at         TIMESTAMPTZ NOT NULL DEFAULT now()
);

ALTER TABLE sources
    ADD COLUMN IF NOT EXISTS raw_sha256 TEXT,
    ADD COLUMN IF NOT EXISTS raw_bytes_size BIGINT,
    ADD COLUMN IF NOT EXISTS provenance_tier TEXT NOT NULL DEFAULT 'unverified';

ALTER TABLE documents
    ADD COLUMN IF NOT EXISTS provenance_verified BOOLEAN NOT NULL DEFAULT false,
    ADD COLUMN IF NOT EXISTS provenance_verified_at TIMESTAMPTZ;

ALTER TABLE chunks
    ADD COLUMN IF NOT EXISTS provenance_verified BOOLEAN NOT NULL DEFAULT false,
    ADD COLUMN IF NOT EXISTS provenance_verified_at TIMESTAMPTZ;

CREATE INDEX IF NOT EXISTS idx_chunks_provenance_verified
    ON chunks(provenance_verified) WHERE provenance_verified;

CREATE INDEX IF NOT EXISTS idx_documents_provenance_verified
    ON documents(provenance_verified);

CREATE INDEX IF NOT EXISTS idx_sources_provenance_tier
    ON sources(provenance_tier);

CREATE TABLE IF NOT EXISTS provenance_audit (
    id              BIGSERIAL PRIMARY KEY,
    audited_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    chunk_id        BIGINT REFERENCES chunks(id) ON DELETE CASCADE,
    document_id     BIGINT REFERENCES documents(id) ON DELETE CASCADE,
    source_id       BIGINT REFERENCES sources(id) ON DELETE CASCADE,
    source_url      TEXT,
    sha_match       BOOLEAN,
    text_match      BOOLEAN,
    text_similarity FLOAT,
    refetch_status  TEXT,
    refetch_size    BIGINT,
    refetch_pages   INT,
    refetch_hash    TEXT,
    notes           TEXT
);

CREATE INDEX IF NOT EXISTS idx_provenance_audit_audited_at
    ON provenance_audit(audited_at DESC);

CREATE INDEX IF NOT EXISTS idx_provenance_audit_text_match
    ON provenance_audit(text_match) WHERE text_match = false;

CREATE TABLE IF NOT EXISTS document_authorities (
    source_id           BIGINT NOT NULL REFERENCES sources(id) ON DELETE CASCADE,
    document_id        BIGINT NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    chunk_id           BIGINT NOT NULL REFERENCES chunks(id) ON DELETE CASCADE,
    authority_id       TEXT NOT NULL,
    canonical_key      TEXT NOT NULL,
    migration_id       TEXT NOT NULL REFERENCES authority_ingest_migrations(migration_id),
    record_sha256      TEXT NOT NULL,
    canonical_anchor   TEXT NOT NULL,
    created_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (document_id, authority_id),
    UNIQUE (chunk_id, authority_id)
);

ALTER TABLE document_authorities
    ADD COLUMN IF NOT EXISTS source_id BIGINT REFERENCES sources(id) ON DELETE CASCADE;

UPDATE document_authorities da
SET source_id = d.source_id
FROM documents d
WHERE da.document_id = d.id AND da.source_id IS NULL;

ALTER TABLE document_authorities
    ALTER COLUMN source_id SET NOT NULL;

CREATE INDEX IF NOT EXISTS idx_document_authorities_authority_id
    ON document_authorities(authority_id);

CREATE UNIQUE INDEX IF NOT EXISTS idx_document_authorities_one_active_authority
    ON document_authorities(authority_id);

INSERT INTO schema_migrations (version) VALUES ('005_authority_registry')
    ON CONFLICT (version) DO NOTHING;
