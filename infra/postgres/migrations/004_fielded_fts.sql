-- Migration 004: fielded full-text search for legal retrieval.
--
-- The original BM25 head only searched `chunks.text_tsv`. That is too flat
-- for law: a hit in the Act title, statute short name, doc id, or anchor
-- often matters more than a hit buried in paragraph body text. This migration
-- adds expression indexes for those fields so retrieval can score a weighted
-- vector while still using GIN prefilters. We intentionally avoid stored
-- generated columns here because adding one to `chunks` rewrites the whole
-- corpus table.

CREATE INDEX IF NOT EXISTS idx_documents_title_tsv
    ON documents USING GIN (to_tsvector('english', coalesce(title, '')));
CREATE INDEX IF NOT EXISTS idx_documents_statute_tsv
    ON documents USING GIN (to_tsvector('english', coalesce(statute_short, '')));
CREATE INDEX IF NOT EXISTS idx_documents_doc_id_tsv
    ON documents USING GIN (to_tsvector('english', coalesce(doc_id, '')));

CREATE INDEX IF NOT EXISTS idx_chunks_anchor_tsv
    ON chunks USING GIN (to_tsvector('english', anchor));

INSERT INTO schema_migrations (version) VALUES ('004_fielded_fts')
    ON CONFLICT (version) DO NOTHING;
