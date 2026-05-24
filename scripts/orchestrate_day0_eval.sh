#!/usr/bin/env bash
# Day-0 orchestration: poll HC sparse coverage, then chain the full eval
# pipeline. Designed to run unattended in run_in_background so the harness
# notifies us once when the entire chain finishes.
#
# Sequence:
#   1. Poll HC sparse coverage every 30s until 100%
#   2. Run 500-query baseline eval (~7h)
#   3. Run LLM-judge classifier (~17 min)
#   4. Generate REAL_ISSUES markdown report
#
# Total wall: ~70 min wait + ~7h eval + ~20 min judge/report = ~8h
#
# Usage:
#   bash scripts/orchestrate_day0_eval.sh

set -euo pipefail
cd "$(dirname "$0")/.."

LOG_DIR=logs
mkdir -p "$LOG_DIR"
TS=$(date +%Y%m%d_%H%M%S)
LOG="$LOG_DIR/orchestrate_day0_${TS}.log"

echo "[orchestrate] starting at $(date -Iseconds), log=$LOG"

{
  echo "=== STEP 1: wait for HC sparse backfill to complete ==="
  echo "[$(date -Iseconds)] polling HC sparse coverage every 30s..."

  while :; do
    pct=$(PYTHONPATH=. .venv/bin/python -c "
import asyncio
from apps.api.db import get_pool
async def main():
    pool = await get_pool()
    async with pool.acquire() as c:
        r = await c.fetchrow(\"SELECT sum((embedding_sparse IS NOT NULL)::int)::int AS w, count(*) AS t FROM chunks WHERE source_type='hc_judgment'\")
        print(f'{100.0 * r[\"w\"] / r[\"t\"]:.1f}')
asyncio.run(main())
" 2>/dev/null || echo "0.0")
    echo "[$(date -Iseconds)] HC sparse coverage: ${pct}%"
    awk -v p="$pct" 'BEGIN { exit (p+0 >= 99.5) ? 0 : 1 }' && break
    sleep 30
  done
  echo "[$(date -Iseconds)] HC sparse backfill DONE"

  echo ""
  echo "=== STEP 2: 500-query baseline eval ==="
  echo "[$(date -Iseconds)] starting eval..."
  PYTHONPATH=. .venv/bin/python scripts/eval_200_runner.py \
      --queries-dir data/eval_500 \
      --prefix eval_500_baseline 2>&1 | tail -5

  # Find the latest eval output
  EVAL_FILE=$(ls -t data/processed/eval_500_baseline_*.jsonl | head -1)
  echo "[$(date -Iseconds)] eval output: $EVAL_FILE"

  echo ""
  echo "=== STEP 3: LLM-judge classifier ==="
  JUDGED_FILE="${EVAL_FILE%.jsonl}.judged.jsonl"
  PYTHONPATH=. .venv/bin/python scripts/llm_judge_eval.py \
      --eval "$EVAL_FILE" \
      --out "$JUDGED_FILE" 2>&1 | tail -20

  echo ""
  echo "=== STEP 4: REAL_ISSUES markdown report ==="
  REPORT_FILE="data/processed/eval_500_REAL_ISSUES_baseline_${TS}.md"
  PYTHONPATH=. .venv/bin/python scripts/report_real_issues.py \
      --in "$JUDGED_FILE" \
      --out "$REPORT_FILE" 2>&1 | tail -15

  echo ""
  echo "=== DONE at $(date -Iseconds) ==="
  echo "raw:     $EVAL_FILE"
  echo "judged:  $JUDGED_FILE"
  echo "report:  $REPORT_FILE"

  # Quick heuristic summary for the notification
  echo ""
  echo "=== Heuristic bucket summary ==="
  PYTHONPATH=. .venv/bin/python scripts/analyze_eval_200.py --eval "$EVAL_FILE" 2>&1 | head -30
} 2>&1 | tee -a "$LOG"
