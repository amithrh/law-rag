#!/usr/bin/env bash
# Day-0 model-dependent benches per OPEN_QUESTIONS.md.
# Resolves: Q1 (verifier latency), Q3 (bge-m3 embedding throughput),
#           Q4 (reranker batch latency), Q2 (HNSW partition vs un-partitioned).
#
# Requires: docker compose stack up + models pulled (`make up && make pull-models`).
# Output: writes results to bench/results/day0-$(date +%Y%m%d-%H%M).json
#
# Status: scaffold — individual bench scripts land alongside the Python packages
# in Days 6–7 (embedding throughput) and Days 8–10 (verifier + reranker).
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
OUT_DIR="$ROOT/bench/results"
mkdir -p "$OUT_DIR"
STAMP="$(date +%Y%m%d-%H%M)"
OUT="$OUT_DIR/day0-$STAMP.json"

echo "==> Day-0 benches will write to $OUT"
echo "==> Not yet implemented. Each bench lands with its corresponding sprint day:"
echo "    Q3 (embedding throughput)  — implemented in Days 6–7 alongside packages/ingest/embed.py"
echo "    Q4 (reranker batch)        — implemented in Days 8–10 alongside packages/retrieval/rerank.py"
echo "    Q1 (verifier latency)      — implemented in Days 8–10 alongside apps/api/verifier.py"
echo "    Q2 (HNSW topology)         — implemented in Days 6–7 alongside packages/retrieval/hybrid.py"
echo ""
echo "==> For now, manually probe TEI / Ollama:"
echo "    curl -s http://localhost:\${TEI_HOST_PORT}/health"
echo "    curl -s http://localhost:\${OLLAMA_HOST_PORT}/api/version"
echo ""
echo "==> Once benches land, this script wires them all together and writes one JSON."
exit 0
