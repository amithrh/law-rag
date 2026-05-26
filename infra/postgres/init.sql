-- =============================================================================
-- law-rag — Postgres schema (single un-partitioned chunks table per §5.4)
-- Runs once on first container start via docker-entrypoint-initdb.d.
-- =============================================================================

-- Extensions ------------------------------------------------------------------
CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS pg_trgm;
CREATE EXTENSION IF NOT EXISTS pg_stat_statements;

-- Sources: where each chunk originally came from -----------------------------
CREATE TABLE IF NOT EXISTS sources (
    id                  BIGSERIAL PRIMARY KEY,
    source_type         TEXT NOT NULL,                              -- 'sc_judgment' | 'hc_judgment' | 'bare_act' | 'circular'
    origin              TEXT NOT NULL,                              -- 'digiscr' | 'scr.sci' | 'judgments.ecourts' | 'indiacode' | 'hf:Rahul1872/...' | 'ia-snapshot' | ...
    url                 TEXT NOT NULL,
    canonical_url_hash  TEXT NOT NULL UNIQUE,                       -- sha256 of canonical url
    raw_storage_uri     TEXT,                                       -- s3://raw/... in MinIO
    fetched_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    metadata            JSONB NOT NULL DEFAULT '{}'::jsonb
);

CREATE INDEX IF NOT EXISTS idx_sources_source_type ON sources(source_type);
CREATE INDEX IF NOT EXISTS idx_sources_origin      ON sources(origin);
CREATE INDEX IF NOT EXISTS idx_sources_fetched_at  ON sources(fetched_at DESC);

-- Documents: normalized representation of a single judgment / act / circular -
CREATE TABLE IF NOT EXISTS documents (
    id                  BIGSERIAL PRIMARY KEY,
    source_id           BIGINT NOT NULL REFERENCES sources(id) ON DELETE CASCADE,
    doc_id              TEXT NOT NULL UNIQUE,                       -- e.g., 'sc/2023/scc-453' or 'consumer-protection-act-2019'
    title               TEXT,
    -- Judgment-specific
    court               TEXT,                                       -- 'SC' | 'Delhi HC' | etc.
    bench               TEXT,
    parties             TEXT,
    citation            TEXT,
    date_decided        DATE,
    -- Statute-specific
    statute_short       TEXT,                                       -- e.g., 'Consumer Protection Act 2019'
    statute_year        INT,
    as_at               DATE,                                       -- which amendment version this doc represents
    amendment_version   TEXT,                                       -- 'original' | '2019' | '2021_amend' | ...
    -- Common
    subject_area        TEXT,                                       -- 'consumer' | 'family' | 'criminal' | 'wages' | 'rti' | 'motor' (slice subject areas, §1 / §2.4)
    statutes_referred   TEXT[],
    cases_cited         TEXT[],
    metadata            JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_documents_doc_id        ON documents(doc_id);
CREATE INDEX IF NOT EXISTS idx_documents_court         ON documents(court);
CREATE INDEX IF NOT EXISTS idx_documents_statute_short ON documents(statute_short);
CREATE INDEX IF NOT EXISTS idx_documents_subject_area  ON documents(subject_area);
CREATE INDEX IF NOT EXISTS idx_documents_as_at         ON documents(as_at);
CREATE INDEX IF NOT EXISTS idx_documents_date_decided  ON documents(date_decided);

-- Fielded full-text expression indexes for legal retrieval. Title/statute/
-- doc-id hits should carry more signal than a random paragraph body hit when
-- users ask for exact Acts, forms, forums, deadlines, or section numbers.
-- Expression indexes avoid rewriting the large chunks table on existing DBs.
CREATE INDEX IF NOT EXISTS idx_documents_title_tsv
    ON documents USING GIN (to_tsvector('english', coalesce(title, '')));
CREATE INDEX IF NOT EXISTS idx_documents_statute_tsv
    ON documents USING GIN (to_tsvector('english', coalesce(statute_short, '')));
CREATE INDEX IF NOT EXISTS idx_documents_doc_id_tsv
    ON documents USING GIN (to_tsvector('english', coalesce(doc_id, '')));

-- Chunks: the unit of retrieval. Single un-partitioned table per §5.4 default.
CREATE TABLE IF NOT EXISTS chunks (
    id                  BIGSERIAL PRIMARY KEY,
    document_id         BIGINT NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    -- Denormalized for fast filtering without a join
    source_type         TEXT NOT NULL,                              -- 'sc_judgment' | 'hc_judgment' | 'bare_act' | 'circular'
    subject_area        TEXT,                                       -- mirrored from documents.subject_area for filter speed
    -- Anchor / position
    anchor              TEXT NOT NULL,                              -- 'sc/2023/scc-453#para-12' or 'consumer-protection-2019/sec-2(7)@2024-04-01'
    paragraph_no        INT,                                        -- for judgments; null for acts
    -- Content
    text                TEXT NOT NULL,
    token_count         INT NOT NULL,
    chunk_strategy      TEXT NOT NULL DEFAULT 'numbered_paragraph', -- numbered_paragraph | semantic_window | section | sub_section | full_circular
    -- Dense embedding (bge-m3 dense head, halfvec storage per §5.4)
    embedding           halfvec(1024),
    -- Sparse embedding (bge-m3 sparse head — reserved for v1.5 per §2.1)
    embedding_sparse    JSONB,
    embedding_model     TEXT NOT NULL DEFAULT 'BAAI/bge-m3',
    embedding_version   TEXT NOT NULL DEFAULT 'v1',
    -- Temporal (for bare acts — §3.2)
    as_at               DATE,
    -- PII redaction (§10.2)
    pii_redacted        BOOLEAN NOT NULL DEFAULT false,
    pii_confidence      FLOAT,
    quarantined         BOOLEAN NOT NULL DEFAULT false,             -- excluded from retrieval if true
    quarantine_reason   TEXT,
    -- OCR quality (§8 risk 2)
    ocr_quality         FLOAT,                                       -- null if text-native; 0..1 confidence
    -- Adapter-specific extras
    metadata            JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (document_id, anchor, as_at)
);

-- Filter indexes for the un-partitioned strategy (§5.4)
CREATE INDEX IF NOT EXISTS idx_chunks_source_type  ON chunks(source_type);
CREATE INDEX IF NOT EXISTS idx_chunks_subject_area ON chunks(subject_area);
CREATE INDEX IF NOT EXISTS idx_chunks_document_id  ON chunks(document_id);
CREATE INDEX IF NOT EXISTS idx_chunks_as_at        ON chunks(as_at);
-- Partial index: most queries care about non-quarantined chunks only
CREATE INDEX IF NOT EXISTS idx_chunks_live         ON chunks(id) WHERE NOT quarantined;

-- HNSW on the dense embedding. Params per §5.2: m=16, ef_construction=64.
-- Partial-index: quarantined chunks are NOT in the HNSW (saves index size + ensures
-- they cannot be returned by vector search even if the WHERE filter is forgotten).
-- NOTE: this index is best built AFTER bulk insert. Drop and recreate after large loads.
CREATE INDEX IF NOT EXISTS idx_chunks_embedding_hnsw
    ON chunks USING hnsw (embedding halfvec_cosine_ops)
    WITH (m = 16, ef_construction = 64)
    WHERE NOT quarantined;

-- BM25 / full-text via tsvector.
-- v1 uses 'english' config — known weak on Devanagari (§2.3); custom dictionary is post-slice.
ALTER TABLE chunks ADD COLUMN IF NOT EXISTS text_tsv tsvector
    GENERATED ALWAYS AS (to_tsvector('english', text)) STORED;
CREATE INDEX IF NOT EXISTS idx_chunks_text_tsv ON chunks USING GIN (text_tsv);
CREATE INDEX IF NOT EXISTS idx_chunks_anchor_tsv
    ON chunks USING GIN (to_tsvector('english', anchor));

-- Trigram index for fuzzy match (party-name lookup etc.)
CREATE INDEX IF NOT EXISTS idx_documents_parties_trgm ON documents USING GIN (parties gin_trgm_ops);
CREATE INDEX IF NOT EXISTS idx_documents_title_trgm   ON documents USING GIN (title   gin_trgm_ops);

-- Eval / observability tables ------------------------------------------------

CREATE TABLE IF NOT EXISTS eval_runs (
    id           BIGSERIAL PRIMARY KEY,
    git_sha      TEXT NOT NULL,
    started_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    finished_at  TIMESTAMPTZ,
    metrics      JSONB,                                              -- recall@10, MRR, citation_index_validity, nli_entailment_rate, per-subject breakdown
    notes        TEXT
);

CREATE TABLE IF NOT EXISTS query_log (
    id                 BIGSERIAL PRIMARY KEY,
    ts                 TIMESTAMPTZ NOT NULL DEFAULT now(),
    query_hash         TEXT NOT NULL,
    user_id            TEXT,                                          -- nullable in dev; populated in production
    query_text         TEXT NOT NULL,
    retrieval_ms       INT,
    rerank_ms          INT,
    llm_ttft_ms        INT,
    llm_total_ms       INT,
    tokens_in          INT,
    tokens_out         INT,
    unsupported_count  INT NOT NULL DEFAULT 0,
    weak_support_count INT NOT NULL DEFAULT 0,
    skipped_sentences  INT NOT NULL DEFAULT 0,
    skip_ratio         FLOAT,
    as_of              DATE,                                          -- statute version used
    coverage           JSONB,                                         -- coverage chip state
    verifier_state     JSONB,                                         -- per-sentence status array
    answer_text        TEXT,                                          -- redact in production per DPDP (§13.2)
    refused            BOOLEAN NOT NULL DEFAULT false,
    refuse_reason      TEXT
);

CREATE INDEX IF NOT EXISTS idx_query_log_ts          ON query_log(ts DESC);
CREATE INDEX IF NOT EXISTS idx_query_log_query_hash  ON query_log(query_hash);
CREATE INDEX IF NOT EXISTS idx_query_log_user_id     ON query_log(user_id) WHERE user_id IS NOT NULL;

-- PII eval (release gate, §10.2)
CREATE TABLE IF NOT EXISTS pii_eval (
    id              BIGSERIAL PRIMARY KEY,
    doc_id          TEXT NOT NULL,
    case_type       TEXT NOT NULL,                                    -- 'pocso' | 'matrimonial' | 'juvenile' | 'standard'
    labels          JSONB NOT NULL,                                   -- hand-labeled PII spans
    pred_regex      JSONB,                                            -- model predictions
    pred_ner        JSONB,
    regex_p         FLOAT,
    regex_r         FLOAT,
    ner_p           FLOAT,
    ner_r           FLOAT,
    evaluated_at    TIMESTAMPTZ
);

-- Migration version tracking -------------------------------------------------
CREATE TABLE IF NOT EXISTS schema_migrations (
    version     TEXT PRIMARY KEY,
    applied_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

INSERT INTO schema_migrations (version) VALUES ('001_initial')
    ON CONFLICT (version) DO NOTHING;
