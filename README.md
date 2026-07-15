# law-rag

An Indian legal-help application that turns a user problem into a matter plan,
retrieved authorities, cited plain-language answer, and an escalation or
source-gap handoff. It is not a legal-advice substitute and is not yet
production ready.

The live product is a FastAPI streamed-answer API plus a Next.js interface.
It combines hybrid retrieval, route-aware authority packs, reranking,
sentence-level citation verification, and deterministic action contracts for
reviewed high-risk routes.

## Quick start (Mac dev)

```bash
# 1. Install local development dependencies
uv sync --extra dev --frozen
cd apps/web && npm ci && cd ../..

# 2. Configure the local data plane
cp .env.example .env
$EDITOR .env  # set POSTGRES_PASSWORD, MINIO_ROOT_PASSWORD, etc.

# 3. Start Postgres, Redis, the Ollama container, and MinIO
make up
# Mac development uses the Ollama container; Linux production uses TEI.

# 4. Pull the configured Ollama models into that container
make pull-models

# 5. For a clean-clone startup smoke only, load the synthetic one-row fixture.
#    It is not legal content and cannot be used to evaluate answer quality.
make seed-ci-corpus

# 6. Verify data-plane dependencies, then run the API and web app in separate terminals
make doctor
make api-dev
make web-dev
```

The API listens on `http://127.0.0.1:8000`; the web app listens on
`http://127.0.0.1:3000`. Set `NEXT_PUBLIC_API_BASE` when the web app should use
another API origin.

The real legal corpus is deliberately not stored in Git. `make seed-ci-corpus`
only proves schema and API startup from a clean clone. Reconstructing a reviewed,
provenance-verified legal corpus from authority records remains a P2 production
gate; do not treat the synthetic fixture as a usable product corpus.

## Verification

```bash
make test-workflows    # deterministic owner/source-contract suite
make test-api-ci       # clean-clone deterministic API suite
make test-api          # full local suite; needs corpus, models, and eval data
make test-models       # local model-backed integration slice
make test-eval-data    # validate ignored local evaluation datasets
make test-eval-gates   # eval scoring and holdout guard tests
make typecheck-web     # TypeScript check
make corpus-manifest   # aggregate DB/runtime/provenance snapshot
```

`make test-api-ci` is the reproducible clean-clone gate. `make test-api` is the
larger local regression gate and intentionally exercises the populated legal
corpus, installed models, and ignored evaluation datasets. Neither a passing
focused test nor a generated evaluation set is production evidence. See
[docs/PRODUCT_RECOVERY_TODO.md](docs/PRODUCT_RECOVERY_TODO.md) for the current
measured blockers and release criteria.

## Deployment Boundary

`infra/docker-compose.prod.yml` is a Linux/GPU production overlay and expects
prebuilt `API_IMAGE` and `WEB_IMAGE`. It enables model prewarming and requires
provenance-verified sources. Do not deploy it until the recovery TODO's API,
holdout, PII, security, and operations gates are all green.

## Repo layout

```
apps/
  api/          FastAPI: /search, /answer (SSE stream), /verify
  web/          Next.js: streamed answer UI + citation popovers + coverage chip
packages/
  ingest/       Per-source adapters + PII redactor + PDF/OCR normalize
  chunking/     judgment / act / circular chunkers
  retrieval/    hybrid BM25 + dense + reranker
  eval/         golden Q&A, metrics, ragas integration
infra/
  docker-compose.yml
  postgres/init.sql      schema (single un-partitioned chunks table per §5.4)
  models.lock            pinned model versions
scripts/
  pull-models.sh         Ollama model pulls
  doctor.sh              health check
  bench-day0.sh          Day-0 model-dependent benches (Q1–Q4)
ops/
  PORT.md, RESTORE.md, SOURCES.md
PLAN.md                  source of truth for design intent
OPEN_QUESTIONS.md        decisions deferred to Day-0 benches / human input
```

## Documents to read first

1. [PLAN.md](PLAN.md) — full design. Especially §1 (corpus), §4 (citation grounding), §10 (legal/PII posture), §13 (productization track).
2. [OPEN_QUESTIONS.md](OPEN_QUESTIONS.md) — Day-0 benches that haven't run yet, plus deferred design choices.

## Constraints

- Fully local OSS at runtime (no paid LLM APIs in the serving path).
- No paid aggregators (no IndianKanoon, no Manupatra) — see PLAN §1.8 and §10.1.
- PII redaction is **release-gating** for any non-localhost deployment (PLAN §10.2). The slice ships local-only until the 200-doc PII eval gate passes.
- The serving path emits a non-removable "information, not legal advice" disclaimer on every answer (PLAN §4.4). Don't remove it.

## Status

Current branch status and production gates are intentionally recorded in
[docs/PRODUCT_RECOVERY_TODO.md](docs/PRODUCT_RECOVERY_TODO.md). The project is
under active recovery. The local deterministic and stack-backed API regression
gates are green at the current checkpoint, but independent legal holdout,
provenance, privacy, security, and operational gates remain open. It must not be
presented as production ready.
