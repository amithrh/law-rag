-- Migration 003: multi-head retrieval — BGE-M3 lexical-sparse vector
--
-- BGE-M3 emits a learned-sparse "lexical weights" head from the same forward
-- pass as the dense head. Storing it lets us run a SPLADE-style retrieval
-- alongside dense ANN and Postgres tsvector BM25, then fuse the three via
-- Reciprocal-Rank-Fusion. Per docs/RETRIEVAL_AUDIT.md (recall@20 = 53%),
-- the failures we observe — "punishment for theft" not finding Section 379,
-- "Section 154(3)" not finding the CrPC section — are exactly the
-- exact-token / statute-reference cases that learned-sparse fixes.
--
-- Storage choice: JSONB, shape `{"<token_id>": <weight>, ...}`
--
--   * Zero infra change. No new Postgres extensions, no rebuilds.
--   * Scoring is dot-product over overlapping keys; that's expressible in
--     SQL via `jsonb_each_text(sparse)` and is O(N) on the candidate set.
--     Each row's JSONB is small (~50-200 tokens) so scanning works at the
--     475K-chunk corpus size we have today.
--   * Migration path to `pg_sparse` (or pgvector ≥0.8 sparsevec) is a
--     drop-in: same key/value semantics, the scoring SQL changes from
--     `jsonb_each_text + dot product` to `<#>` operator. Not on the
--     critical path; revisit when the corpus crosses ~5M chunks.
--
-- NB: the column itself was reserved in init.sql ("embedding_sparse JSONB"
-- — see comment there about v1.5). This migration:
--   1. Asserts it idempotently (in case a fresh DB skipped init.sql for
--      whatever reason).
--   2. Adds a partial index that gives us a cheap "which chunks still need
--      sparse backfill?" lookup.
--   3. Adds a GIN index on the JSONB keys for the "find chunks sharing
--      ≥1 token with the query" prefilter that the sparse retriever
--      relies on.

-- Step 1 — column (idempotent). init.sql already adds this; we keep the
-- ALTER as a safety net for environments that pre-date init.sql changes.
ALTER TABLE chunks
    ADD COLUMN IF NOT EXISTS embedding_sparse JSONB;

-- Step 2 — partial index on "has been backfilled". Lets the backfill
-- script efficiently slice on `WHERE embedding_sparse IS NULL` without
-- touching the full HNSW or text_tsv indexes.
CREATE INDEX IF NOT EXISTS idx_chunks_sparse_missing
    ON chunks (id)
    WHERE embedding_sparse IS NULL AND NOT quarantined;

-- Step 3 — GIN index on the JSONB keys (token-id strings). The sparse
-- retriever asks "give me chunks whose embedding_sparse has any key
-- present in the query's sparse vector". GIN on JSONB makes the `?|`
-- operator (key existence over an array) fast.
CREATE INDEX IF NOT EXISTS idx_chunks_sparse_gin
    ON chunks USING GIN (embedding_sparse jsonb_path_ops);

INSERT INTO schema_migrations (version) VALUES ('003_sparse_embedding')
    ON CONFLICT (version) DO NOTHING;
