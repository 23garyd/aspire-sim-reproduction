#!/bin/bash
# Harder-held-out campaign (libero_10) — stage-chained parallel runner with
# cool-down/resume when the planner circuit breaker trips (exit code 3).
set -u
cd "$(dirname "$0")/.."
ROOT="$HOME/aspire_runs/libero_hard"
LIB="$HOME/aspire_runs/libero_tiling/tiled_library"
COMMON=(--root "$ROOT" --suite libero_10 --jobs 4 --stagger 20 --library "$LIB" --no-analyze)

run_stage() {
  local tries=0
  while true; do
    env -u ANTHROPIC_API_KEY python3 scripts/libero_tiling_parallel.py "${COMMON[@]}" "$@"
    rc=$?
    if [ "$rc" -eq 3 ]; then
      echo "[wrapper] circuit breaker tripped; cooling down 30 min before resume"
      sleep 1800
      continue
    fi
    if [ "$rc" -eq 4 ] && [ "$tries" -lt 5 ]; then
      tries=$((tries + 1))
      echo "[wrapper] cells left behind by transient failures; re-invoking ($tries/5)"
      sleep 60
      continue
    fi
    return "$rc"
  done
}

echo "[wrapper] stage 1: warm_dumpall+cold on 10_0, 10_6, 10_3 (10 reps)"
run_stage --tasks 0,6,3 --arms warm_dumpall,cold --reps 10 || exit 1
echo "[wrapper] stage 2: warm_geo on 10_3 only (bowl anchor exists there)"
run_stage --tasks 3 --arms warm_geo --reps 10 || exit 1
echo "[wrapper] analysis"
python3 scripts/analyze_libero_tiling.py --root "$ROOT" --heldout 0,6,3 --prefix 10 \
  > "$ROOT/analysis.log" 2>&1
echo "[wrapper] HARD CAMPAIGN DONE root=$ROOT"
