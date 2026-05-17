-- Migration 002: source-of-truth provenance fields.
--
-- For every chunk we need to be able to answer:
--   "Where did this text come from, and is it still identical to the source?"
--
-- Layered approach:
--   - `sources` row carries the canonical URL + SHA-256 of the raw bytes
--     we downloaded.
--   - `documents` row carries when we extracted it, with what tool version,
--     and whether a verifier has confirmed it against re-fetched source.
--   - A periodic verifier job samples chunks, re-fetches the source PDF
--     from `sources.url`, re-extracts text, and diffs against what we
--     have stored. Results land in `provenance_audit`.

-- sources: add SHA-256 of raw bytes + size
ALTER TABLE sources
    ADD COLUMN IF NOT EXISTS raw_sha256        TEXT,
    ADD COLUMN IF NOT EXISTS raw_bytes_size    BIGINT,
    ADD COLUMN IF NOT EXISTS provenance_tier   TEXT NOT NULL DEFAULT 'unverified';
    -- provenance_tier:
    --   'canonical'   = downloaded directly from the official Govt source
    --                   (IndiaCode, eSCR, judgments.ecourts.gov.in)
    --   'mirror'      = downloaded from a 3rd-party mirror that we've spot-
    --                   checked against the canonical source (e.g. HF datasets
    --                   after a verify_provenance pass)
    --   'unverified'  = downloaded but not yet checked against the canonical
    --                   source. Quarantined from public-product queries.

-- documents: extraction metadata
ALTER TABLE documents
    ADD COLUMN IF NOT EXISTS extracted_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    ADD COLUMN IF NOT EXISTS extractor_version TEXT NOT NULL DEFAULT 'pymupdf-unknown',
    ADD COLUMN IF NOT EXISTS provenance_verified BOOLEAN NOT NULL DEFAULT false,
    ADD COLUMN IF NOT EXISTS provenance_verified_at TIMESTAMPTZ;

CREATE INDEX IF NOT EXISTS idx_documents_provenance_verified
    ON documents(provenance_verified);
CREATE INDEX IF NOT EXISTS idx_sources_provenance_tier
    ON sources(provenance_tier);

-- Periodic verifier output: one row per audit run, one row per sampled chunk.
CREATE TABLE IF NOT EXISTS provenance_audit (
    id              BIGSERIAL PRIMARY KEY,
    audited_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    chunk_id        BIGINT REFERENCES chunks(id) ON DELETE CASCADE,
    document_id     BIGINT REFERENCES documents(id) ON DELETE CASCADE,
    source_id       BIGINT REFERENCES sources(id) ON DELETE CASCADE,
    source_url      TEXT,
    -- Verdicts
    sha_match       BOOLEAN,           -- raw bytes hash matches what we stored
    text_match      BOOLEAN,           -- normalized text matches what we stored
    text_similarity FLOAT,             -- 0..1 if text_match is False
    -- Diagnostics
    refetch_status  TEXT,              -- 'ok' | 'http_4xx' | 'http_5xx' | 'timeout' | 'parse_failed'
    refetch_size    BIGINT,
    refetch_pages   INT,
    refetch_hash    TEXT,
    notes           TEXT
);

CREATE INDEX IF NOT EXISTS idx_provenance_audit_audited_at ON provenance_audit(audited_at DESC);
CREATE INDEX IF NOT EXISTS idx_provenance_audit_text_match ON provenance_audit(text_match)
    WHERE text_match = false;

-- Backfill provenance_tier for already-loaded sources, based on origin field.
UPDATE sources SET provenance_tier = 'canonical'
WHERE origin IN ('indiacode')
  AND provenance_tier = 'unverified';

UPDATE sources SET provenance_tier = 'mirror'
WHERE origin LIKE 'hf:%'
  AND provenance_tier = 'unverified';

INSERT INTO schema_migrations (version) VALUES ('002_provenance')
    ON CONFLICT (version) DO NOTHING;
