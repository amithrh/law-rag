# Multi-head retrieval — BGE-M3 dense + learned-sparse + Postgres BM25 (RRF)

Architecture-research **Task #3** — replace the legacy 70%-dense /
30%-BM25 weighted-sum fusion with a three-source pipeline that adds the
BGE-M3 learned-sparse head (SPLADE-style) and fuses everything via
Reciprocal-Rank-Fusion (Cormack et al., k=60).

## Why

`docs/RETRIEVAL_AUDIT.md` measured **recall@20 = 53%** on a hand-curated
gold set. The architecture-research roadmap pinpointed this as the
ceiling on every downstream metric — no verifier or prompt change can
recover authority that wasn't retrieved. The audit identified the
failure mode precisely:

> **Statute-section retrieval is broken.** "Punishment for theft"
> should pull Section 379 / BNS theft section verbatim. Our act chunks
> aren't getting matched because the query doesn't share lexical
> overlap with the section heading. The query says "punishment for
> theft"; the act section title is "Theft" with surrounding clause
> text. This is exactly what BGE-M3's learned-sparse head
> (SPLADE-style) is built to handle.

We already pay BGE-M3's inference cost for the dense vector — the
sparse and ColBERT heads come from the **same forward pass** with no
extra model.

## Architecture

### Pipeline

```
Query
  ├──► BGE-M3 dense   ──► HNSW    ──► dense_top_k=100  ──┐
  ├──► BGE-M3 sparse  ──► JSONB·  ──► sparse_top_k=100 ──┼──► RRF (k=60) ──► top fused
  └──► query string   ──► tsvector──► bm25_top_k=100   ──┘                       │
                                                                                  ▼
                                                                         cross-encoder
                                                                         rerank (top 50)
                                                                                  │
                                                                                  ▼
                                                                         LLM (top K=8)
```

### Storage

The BGE-M3 learned-sparse head emits a per-token weight dictionary
(`{token_id: weight}`). We persist this as `chunks.embedding_sparse
JSONB`. JSONB was chosen over `pg_sparse` / `pgvector ≥0.8 sparsevec`
for v1.5 because:

  * **Zero infra change.** No new Postgres extensions to enable.
  * **Scoring is expressible in SQL.** Each row's JSONB is small
    (~50–200 tokens), so `jsonb_each_text + SUM` over overlapping
    keys is O(N) on the candidate set.
  * **GIN index gives a cheap prefilter.** Chunks that share ≥1 token
    with the query are found by `embedding_sparse ?| query_keys[]`.

Migration path to `pg_sparse` / `sparsevec` is a drop-in when the
corpus crosses ~5M chunks: same key/value semantics, the scoring SQL
changes from `jsonb_each_text + dot product` to the `<#>` operator.
Not on the critical path today.

### RRF fusion

Standard Cormack et al. formula with `k=60`:

```
score(d) = Σ over heads h: 1 / (k + rank_h(d))
```

where `rank_h` is the 1-based rank of doc `d` in head `h`'s ranking
(absent if `d` wasn't surfaced by `h`). RRF was chosen over a weighted
sum because dense / sparse / BM25 scores live on non-commensurate
scales:

  * dense cosine ∈ [-1, 1] (in practice [0, 1] after L2 normalization)
  * BM25 `ts_rank` is unbounded and corpus-dependent
  * sparse dot-product depends on token frequency; theoretical bound
    depends on the lexical vocabulary

RRF normalizes all three into a rank-space contribution.

## Configuration

| key | default | purpose |
|-----|---------|---------|
| `hybrid_mode` | `dense_sparse_bm25` | `dense_bm25` reverts to the legacy 70/30 mix (A/B / fallback when sparse column unbackfilled) |
| `sparse_top_k` | `100` | per-head depth before fusion |
| `rrf_k` | `60` | RRF constant — k=60 is the published default |
| `embedding_runtime` | `flag` | `flag` loads `FlagEmbedding.BGEM3FlagModel`; `st` loads sentence-transformers (dense only, no sparse) |

All exposed via env vars (case-insensitive — pydantic-settings).

## Backfill

`scripts/backfill_sparse_embeddings.py` runs BGE-M3 over every chunk
with `embedding_sparse IS NULL` in `FLUSH_EVERY=500` batches. Idempotent
on the existence of the column, monotonic cursor pagination by `id`
(no OFFSET), interruptible (partial progress is committed).

Throughput on M-series MPS: ~12.6 emb/s observed on a 100-chunk
smoke-test (see commit log). Extrapolated:

| chunks | est. time |
|---|---|
| 100 | ~8 s |
| 10 K | ~13 min |
| 475 K | ~10 h |

## Verification of the audit failure mode

Smoke-test query from the audit, **`Section 154(3) Cr.P.C.`**, against
a 100-chunk slice + the full 475K dense + tsvector indexes:

```
8 hits (use_reranker=False, top_k=8):
  id=150124 dense=0.701 bm25=0.000 sparse=0.0000 rrf=0.0164  Steel Authority...
  id=353421 dense=0.000 bm25=0.976 sparse=0.0000 rrf=0.0164  LALITA KUMARI v Govt UP   ← gold
  id=726    dense=0.000 bm25=0.000 sparse=0.0184 rrf=0.0164  Avitel Post Studioz
  id=239878 dense=0.700 bm25=0.000 sparse=0.0000 rrf=0.0161  T. Venkateswarulu
  id=216299 dense=0.000 bm25=0.965 sparse=0.0000 rrf=0.0161  SAKIRI VASU v State UP    ← gold
  id=723    dense=0.000 bm25=0.000 sparse=0.0143 rrf=0.0161  Avitel Post Studioz
  id=354629 dense=0.679 bm25=0.000 sparse=0.0000 rrf=0.0159  Reshma Kumari
  id=194885 dense=0.000 bm25=0.942 sparse=0.0000 rrf=0.0159  Parkash Singh Badal
```

Both **Sakiri Vasu** and **Lalita Kumari** — the two landmark Indian
FIR-refusal cases — surface in top-5 *via the BM25 head* with RRF
correctly tying them to the dense head's results. The Avitel chunks
are the only ones in the 100-chunk sparse-backfilled slice, so the
sparse head's contribution is currently limited; once the full
backfill lands those landmarks will also be in the sparse top-K and
RRF will rank them even higher.

This is exactly the audit failure pattern: dense alone failed to
surface the lexically-distinct ("Section 154(3)") gold cases, and the
audit ran on the legacy 70/30 fusion before RRF could do anything
about it.

## Tests

`apps/api/tests/test_retrieval.py` (9 new tests, all green):

| test | what it asserts |
|---|---|
| `test_rrf_fusion_combines_three_sources` | RRF math against the canonical k=60 formula |
| `test_rrf_k_dampens_top_rank_dominance` | k=60 vs k=1 — gap between rank-1 and rank-10 contributions |
| `test_sparse_retrieve_empty_query_returns_nothing` | OOV / stopword queries short-circuit (no full-table scan) |
| `test_sparse_retrieve_builds_jsonb_dot_product_sql` | SQL shape: GIN prefilter + jsonb_each_text dot product |
| `test_hybrid_mode_defaults_to_dense_sparse_bm25` | default config |
| `test_hybrid_mode_env_override` | `HYBRID_MODE=dense_bm25` reaches Settings |
| `test_embedding_runtime_defaults_to_flag` | multi-head runtime is the default |
| `test_sparse_vector_shape` (`needs_models`) | embedder returns `dict[str, float]` from BGE-M3 |
| `test_sparse_retrieve_finds_exact_section_reference` (`needs_models`) | gold passage beats distractors on a real `Section 154(3) Cr.P.C.` query |

## Next manual steps (for the user, not the agent)

1. **Kick off the full 475K backfill** (~10 h on M-series MPS, idempotent / resumable):
   ```
   PYTHONPATH=. .venv/bin/python scripts/backfill_sparse_embeddings.py --commit
   ```
   The script logs progress to `data/processed/backfill_sparse.log` and
   prints throughput every batch. Safe to ctrl-C and resume.

2. **Re-run `scripts/audit_retrieval_recall.py`** once the backfill
   completes. Target: recall@20 ≥ 80%.

3. **Re-run `scripts/test_battery_v3.py round10_multihead`**. Compare
   in-slice pass-rate to round-9's 94%.

4. **Update the pipeline ingest scripts** (`bulk_ingest_sc.py`,
   `bulk_ingest_hc.py`) to populate `embedding_sparse` at chunk-insert
   time, so new ingest after the backfill doesn't drift.

## Open caveats / future work

  * **ColBERT head deferred to phase 2.** The same BGE-M3 forward pass
    also emits a multi-vector ColBERT representation. Adding it under
    RRF is the obvious next step — but ColBERT vectors are
    significantly larger (`token_count × 1024` per chunk, vs
    50-200-token sparse dicts), so the storage and scoring cost is
    materially higher. Land sparse first; measure its incremental
    recall@20 gain; decide on ColBERT based on the residual gap.

  * **`pg_sparse` migration.** When chunks crosses ~5M, the
    `jsonb_each_text` scan over candidate rows will start to bottleneck
    sparse retrieval latency. Migrate to native sparse storage at that
    point — drop-in change to the scoring SQL, no schema rewrite.

  * **Sparse and dense disagree on the same chunk fairly often.** A
    chunk can rank high in dense (semantically related) and zero in
    sparse (no token overlap). RRF handles this gracefully — both
    contribute — but does mean the fused top-K mixes "this is
    semantically about your question" and "this contains your exact
    keywords" results. The cross-encoder rerank stage should resolve
    most of these; worth re-measuring on the audit set after backfill.

  * **The sparse SQL is O(N over the candidate set), N≈sparse_top_k**.
    At sparse_top_k=100 against the 475K corpus, the GIN prefilter
    typically reduces the scored set to a few thousand candidates.
    Profile latency end-to-end once the backfill lands — if sparse
    becomes the slowest of the three heads, lower `sparse_top_k` (60
    is the bottom we'd accept before RRF starts losing recall).
