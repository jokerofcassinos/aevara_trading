# @module: QROE_CYCLE_RUNNER
# @deps: qroe_router.py, phase_gate_validator.py, state_reconciler.py
# @status: INITIALIZED
# @last_update: 2026-04-06
# @summary: Script de execucao continua do ciclo QROE

#!/bin/bash
set -e

BASE_DIR="$(cd "$(dirname "$0")/.." && pwd)"
SCRIPTS_DIR="$BASE_DIR/scripts"
DOCS_DIR="$BASE_DIR/docs"

echo "[QROE] === Cycle Start ==="
echo "[QROE] $(date -u '+%Y-%m-%dT%H:%M:%SZ')"

# Step 1: Read state
echo "[QROE] Reading state..."
python3 "$SCRIPTS_DIR/qroe_router.py" --read-state

# Step 2: Validate state integrity
if [ ! -f "$DOCS_DIR/PROJECT_STATE.yaml" ]; then
    echo "[QROE] State file missing. Running reconcciliation..."
    python3 "$SCRIPTS_DIR/state_reconciler.py" "$BASE_DIR"
fi

# Step 3: Select next task
echo "[QROE] Selecting next task..."
TASK_INFO=$(python3 "$SCRIPTS_DIR/qroe_router.py" --read-state 2>/dev/null)
if [ $? -eq 0 ] && [ -n "$TASK_INFO" ]; then
    echo "[QROE] $TASK_INFO"
else
    echo "[QROE] No pending tasks or state error. Entering OBSERVE mode."
    exit 0
fi

echo "[QROE] === Cycle Complete ==="
