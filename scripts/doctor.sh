#!/usr/bin/env bash
# Health check for the law-rag stack. Used by `make doctor`.
# Verifies: services up, extensions present, models pulled, env vars set.
set -uo pipefail

# Load .env
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
if [ -f "$ROOT/.env" ]; then
  # shellcheck disable=SC1091
  set -a; . "$ROOT/.env"; set +a
else
  echo "ERROR: .env not found. Copy .env.example to .env first."
  exit 1
fi

FAIL=0
ok()   { printf "  \033[32m✓\033[0m %s\n" "$1"; }
fail() { printf "  \033[31m✗\033[0m %s\n" "$1"; FAIL=1; }
hdr()  { printf "\n\033[1m%s\033[0m\n" "$1"; }

hdr "1. Required env vars"
for v in POSTGRES_HOST POSTGRES_DB POSTGRES_USER POSTGRES_PASSWORD \
         OLLAMA_HOST_PORT MINIO_HOST_PORT LLM_MODEL OLLAMA_EMBED_MODEL EMBEDDING_BACKEND; do
  if [ -n "${!v:-}" ]; then ok "$v set"; else fail "$v unset"; fi
done

hdr "2. Docker compose services (Mac dev profile: TEI omitted)"
for svc in lawrag-postgres lawrag-redis lawrag-ollama lawrag-minio; do
  if docker ps --format '{{.Names}}' | grep -q "^${svc}$"; then
    ok "$svc running"
  else
    fail "$svc not running (try: make up)"
  fi
done

hdr "3. Postgres extensions"
if docker exec lawrag-postgres psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -tAc \
   "SELECT extname FROM pg_extension" 2>/dev/null | grep -q "^vector$"; then
  ok "pgvector installed"
else
  fail "pgvector NOT installed"
fi
for ext in pg_trgm pg_stat_statements; do
  if docker exec lawrag-postgres psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -tAc \
     "SELECT extname FROM pg_extension" 2>/dev/null | grep -q "^${ext}$"; then
    ok "$ext installed"
  else
    fail "$ext NOT installed"
  fi
done

hdr "4. Schema tables"
for tbl in sources documents chunks eval_runs query_log pii_eval; do
  if docker exec lawrag-postgres psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -tAc \
     "SELECT to_regclass('public.${tbl}')" 2>/dev/null | grep -q "^${tbl}$"; then
    ok "table $tbl present"
  else
    fail "table $tbl missing"
  fi
done

hdr "5. Ollama models (LLM + embeddings on Mac)"
OLLAMA_LIST=$(docker exec lawrag-ollama ollama list 2>/dev/null || echo "")
if echo "$OLLAMA_LIST" | tail -n +2 | awk '{print $1}' | grep -q "${LLM_MODEL%%:*}"; then
  ok "LLM_MODEL ($LLM_MODEL) pulled"
else
  fail "LLM_MODEL ($LLM_MODEL) not pulled (try: make pull-models)"
fi
if echo "$OLLAMA_LIST" | tail -n +2 | awk '{print $1}' | grep -q "${OLLAMA_EMBED_MODEL%%:*}"; then
  ok "OLLAMA_EMBED_MODEL ($OLLAMA_EMBED_MODEL) pulled"
else
  fail "OLLAMA_EMBED_MODEL ($OLLAMA_EMBED_MODEL) not pulled (try: make pull-models)"
fi

hdr "6. Embedding sanity check (Ollama /api/embeddings)"
EMBED_TEST=$(curl -sS -m 30 -X POST "http://localhost:${OLLAMA_HOST_PORT}/api/embeddings" \
  -d "{\"model\":\"${OLLAMA_EMBED_MODEL}\",\"prompt\":\"test\"}" 2>/dev/null)
if echo "$EMBED_TEST" | grep -q '"embedding"'; then
  DIM=$(echo "$EMBED_TEST" | python3 -c "import json,sys; d=json.load(sys.stdin); print(len(d['embedding']))" 2>/dev/null)
  ok "embedding endpoint healthy (dim=$DIM, expected 1024)"
else
  fail "embedding endpoint not responding (model may still be loading)"
fi

hdr "7. MinIO buckets"
if docker exec lawrag-minio mc alias set local http://localhost:9000 "$MINIO_ROOT_USER" "$MINIO_ROOT_PASSWORD" >/dev/null 2>&1 && \
   docker exec lawrag-minio mc ls local/ 2>/dev/null | grep -q "${MINIO_BUCKET_RAW}"; then
  ok "MinIO bucket $MINIO_BUCKET_RAW present"
else
  fail "MinIO bucket $MINIO_BUCKET_RAW missing (run: make up — minio-init service creates it)"
fi

echo ""
if [ "$FAIL" -eq 0 ]; then
  printf "\033[32mAll checks passed.\033[0m\n"
  exit 0
else
  printf "\033[31mSome checks failed.\033[0m See above.\n"
  exit 1
fi
