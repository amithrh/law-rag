#!/usr/bin/env bash
# Auto-recover on Mac boot: start API + caffeinate + resume miner if it
# was running before the reboot.
#
# Install via launchd (one-time):
#   cp scripts/com.lawrag.autorecover.plist ~/Library/LaunchAgents/
#   launchctl load ~/Library/LaunchAgents/com.lawrag.autorecover.plist
#
# This script is idempotent — safe to invoke multiple times. It checks
# if processes are already running before starting.

set -uo pipefail
cd "$(dirname "$0")/.."
PROJECT_ROOT="$(pwd)"
LOG_DIR="$PROJECT_ROOT/logs"
mkdir -p "$LOG_DIR"
BOOT_LOG="$LOG_DIR/autorecover_$(date +%Y%m%d_%H%M%S).log"

log()  { echo "[$(date '+%H:%M:%S')] $*" | tee -a "$BOOT_LOG"; }

log "=== autorecover starting ==="
log "uptime: $(uptime)"

# Wait for system to settle (DB, ollama, network)
sleep 20

# ---- 1. caffeinate (prevent sleep)
if ! pgrep -fl "caffeinate -dimsu" > /dev/null; then
    log "starting caffeinate -dimsu"
    nohup caffeinate -dimsu > /dev/null 2>&1 &
    sleep 1
fi

# ---- 2. API (uvicorn)
if ! pgrep -f "uvicorn apps.api.main:app" > /dev/null; then
    log "starting uvicorn API"
    PREWARM_MODELS_ON_STARTUP=true PREWARM_MODELS_REQUIRED=true \
    PYTHONPATH=. nohup "$PROJECT_ROOT/.venv/bin/uvicorn" apps.api.main:app \
        --host 0.0.0.0 --port 8000 --workers 1 \
        > "$LOG_DIR/api_autoboot_$(date +%Y%m%d_%H%M%S).log" 2>&1 &
    sleep 6
fi

# ---- 3. Resume miner if a partial JSONL exists and it has fewer rows
# than the target
LATEST=$(ls -t "$PROJECT_ROOT/data/training/synthetic_triples_bare_act_"*.jsonl 2>/dev/null | head -1)
if [ -n "$LATEST" ]; then
    NROWS=$(wc -l < "$LATEST")
    if [ "$NROWS" -lt 12500 ] && ! pgrep -f "mine_synthetic_triples" > /dev/null; then
        log "resuming miner from $LATEST (currently $NROWS rows)"
        PYTHONPATH=. nohup "$PROJECT_ROOT/.venv/bin/python" -u \
            "$PROJECT_ROOT/scripts/mine_synthetic_triples.py" \
            --source-type bare_act --concurrency 4 --model qwen3:14b \
            --resume "$LATEST" --out "$LATEST" \
            > "$LOG_DIR/miner_autoboot_$(date +%Y%m%d_%H%M%S).log" 2>&1 &
        log "miner resumed PID $!"
    fi
fi

log "=== autorecover done ==="
log "API:        $(curl -s -m 3 http://localhost:8000/healthz || echo 'unreachable')"
log "caffeinate: $(pgrep -fl 'caffeinate -dimsu' | head -1 || echo 'not running')"
log "miner:      $(pgrep -fl 'mine_synthetic_triples' | head -1 || echo 'not running')"
