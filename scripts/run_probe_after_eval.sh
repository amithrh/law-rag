#!/usr/bin/env bash
# Wait for eval PID 30054 to exit, then fire the 100-query retrieval probe.
set -euo pipefail
EVAL_PID=30054
LOG="logs/random100_retrieval_postEval_$(date +%Y%m%d_%H%M%S).log"
echo "[$(date +%H:%M:%S)] waiting for eval PID $EVAL_PID to finish ..." > "$LOG"
while kill -0 "$EVAL_PID" 2>/dev/null; do sleep 30; done
echo "[$(date +%H:%M:%S)] eval exited — firing probe" >> "$LOG"
cd "$(dirname "$0")/.."
PYTHONPATH=. .venv/bin/python -u scripts/random100_retrieval_probe.py >> "$LOG" 2>&1
