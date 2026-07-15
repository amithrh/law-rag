-- Deterministic synthetic corpus used only by clean-clone and CI smoke tests.
-- This is not legal authority content and must never be used for answer quality.

INSERT INTO sources (
    source_type,
    origin,
    url,
    canonical_url_hash,
    metadata
)
VALUES (
    'bare_act',
    'ci-fixture',
    'https://example.invalid/law-rag-ci-fixture',
    'law-rag-ci-fixture-v1',
    '{"ci_fixture": true, "provenance_verified": false}'::jsonb
)
ON CONFLICT (canonical_url_hash) DO UPDATE
SET metadata = EXCLUDED.metadata;

INSERT INTO documents (
    source_id,
    doc_id,
    title,
    statute_short,
    statute_year,
    as_at,
    amendment_version,
    subject_area,
    metadata
)
SELECT
    id,
    'ci/synthetic-health-fixture',
    'Synthetic CI Health Fixture',
    'Synthetic CI Health Fixture',
    2000,
    DATE '2000-01-01',
    'synthetic-v1',
    'ci_fixture',
    '{"ci_fixture": true, "not_legal_authority": true}'::jsonb
FROM sources
WHERE canonical_url_hash = 'law-rag-ci-fixture-v1'
ON CONFLICT (doc_id) DO UPDATE
SET metadata = EXCLUDED.metadata;

INSERT INTO chunks (
    document_id,
    source_type,
    subject_area,
    anchor,
    text,
    token_count,
    chunk_strategy,
    embedding_model,
    embedding_version,
    as_at,
    pii_redacted,
    metadata
)
SELECT
    id,
    'bare_act',
    'ci_fixture',
    'ci/synthetic-health-fixture/sec-1',
    'Synthetic text for database and API startup verification only.',
    10,
    'section',
    'none',
    'ci-fixture-v1',
    DATE '2000-01-01',
    true,
    '{"ci_fixture": true, "not_legal_authority": true}'::jsonb
FROM documents
WHERE doc_id = 'ci/synthetic-health-fixture'
ON CONFLICT (document_id, anchor, as_at) DO UPDATE
SET text = EXCLUDED.text,
    token_count = EXCLUDED.token_count,
    metadata = EXCLUDED.metadata;
