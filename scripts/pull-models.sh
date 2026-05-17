#!/usr/bin/env bash
# Pull Ollama models for law-rag. TEI auto-pulls its embedding model on container start.
# Idempotent — safe to re-run.
set -euo pipefail

# Load .env if present so LLM_MODEL / LLM_FALLBACK_MODEL are resolved.
if [ -f "$(dirname "$0")/../.env" ]; then
  # shellcheck disable=SC1091
  set -a; . "$(dirname "$0")/../.env"; set +a
fi

LLM_MODEL="${LLM_MODEL:-llama3.1:8b-instruct-q4_K_M}"
LLM_FALLBACK_MODEL="${LLM_FALLBACK_MODEL:-qwen2.5:7b-instruct-q4_K_M}"
OLLAMA_EMBED_MODEL="${OLLAMA_EMBED_MODEL:-bge-m3}"

echo "==> Waiting for ollama container to be ready..."
for _ in $(seq 1 30); do
  if docker exec lawrag-ollama ollama list >/dev/null 2>&1; then
    break
  fi
  sleep 2
done

echo "==> Pulling embedding model: $OLLAMA_EMBED_MODEL (~2.3 GB)"
docker exec lawrag-ollama ollama pull "$OLLAMA_EMBED_MODEL"

echo "==> Pulling primary LLM: $LLM_MODEL (~4.7 GB)"
docker exec lawrag-ollama ollama pull "$LLM_MODEL"

echo "==> Pulling fallback LLM: $LLM_FALLBACK_MODEL (~4.4 GB)"
docker exec lawrag-ollama ollama pull "$LLM_FALLBACK_MODEL"

echo "==> Models present:"
docker exec lawrag-ollama ollama list

echo ""
echo "==> Reranker (bge-reranker-v2-m3) and NLI (DeBERTa-v3-base-mnli) are loaded"
echo "    in-process by apps/api on startup — no separate pull needed."
echo ""
echo "==> On Linux prod, TEI is the production embedding backend (faster batch on CUDA);"
echo "    on Mac dev, Ollama serves embeddings via Metal — this is fine for ~1M chunks."
echo ""
echo "==> Capture model digests into infra/models.lock manually after pulls finish."
