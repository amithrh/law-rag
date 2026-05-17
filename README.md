# law-rag

Self-hosted Retrieval-Augmented Generation system over Indian primary law (Supreme Court + selected High Courts + bare acts + regulator circulars). Pre-implementation phase — see [PLAN.md](PLAN.md) and [OPEN_QUESTIONS.md](OPEN_QUESTIONS.md).

The first deliverable is a **research-grade engine slice** focused on common-public law (consumer, family, criminal procedure, wages, RTI, motor vehicles). Productization (auth, billing, ads, hosting, multilingual, audio) lives in [PLAN.md §13](PLAN.md).

## Quick start (Mac dev)

```bash
# 1. Configure
cp .env.example .env
$EDITOR .env  # set POSTGRES_PASSWORD, MINIO_ROOT_PASSWORD, etc.

# 2. Start the data plane (postgres+pgvector, redis, ollama, tei, minio)
make up
# TEI downloads bge-m3 (~2 GB) on first start. Watch progress:
docker logs -f lawrag-tei

# 3. Pull Ollama LLMs (~5 GB each for the 7-8B q4_K_M variants)
make pull-models

# 4. Health check
make doctor
```

Once `make doctor` reports all green, the data plane is ready. The sprint then proceeds per [PLAN.md §9](PLAN.md):

- **Days 3–5:** ingest adapters (SC via HF Rahul1872 + IndiaCode for selected acts + Tier-A HCs) and PII redactor.
- **Days 6–7:** chunkers + 1M-chunk embedding + HNSW build.
- **Days 8–10:** retrieval API + per-sentence verifier + lay-friendly prompt.
- **Days 11–13:** Next.js UI.
- **Days 14–15:** golden-set eval + ops + demo.

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

Pre-implementation. Repo currently contains: planning docs, Docker Compose for the data plane, Postgres schema, model pull scripts, doctor script. No application code yet — the sprint starts here.
