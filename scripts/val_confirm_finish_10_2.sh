#!/bin/bash
# One-off: finish the last 10 cells of the val-confirmatory campaign (10_2 warm+cold
# reps 6-10) by calling aspire.run DIRECTLY, bypassing libero_tiling_parallel.py's
# shared api-server-holder (which deterministically fails 10_2 reps 6+ with rc=2).
# 2 concurrent (each cell starts its own env; GPU has ample headroom). API billing
# (ANTHROPIC_API_KEY inherited — subscription cap can't finish this). Idempotent (DONE).
set -u
ROOT="$HOME/aspire_runs/libero_val_confirm"
VENV=/home/demo/cap-x/.venv-libero/bin/python
CAPX="/home/demo/aspire_robot_engine/scripts/capx_execute.py"
LIB="$HOME/aspire_runs/libero_tiling/tiled_library"
BASELINE="/home/demo/aspire_robot_engine/runs/2026-07-22-libero-accum-frontier/baseline_grasp_lift.py"
CFG="$ROOT/configs/10_2.yaml"

run_cell() {
  local arm=$1 rep=$2
  local rdir="$ROOT/test/10_2/$arm/$rep"
  local task="$rdir/task" out="$rdir/exec"
  [ -f "$rdir/DONE" ] && { echo "skip 10_2/$arm/$rep (DONE)"; return; }
  rm -rf "$rdir"; mkdir -p "$task" "$out"; cp "$BASELINE" "$task/code.py"
  local lib="$rdir/lib"; mkdir -p "$lib"
  [ "$arm" = warm_dumpall ] && cp -r "$LIB/." "$lib/" 2>/dev/null
  MUJOCO_GL=egl PATH="$HOME/.local/bin:$PATH" python3 -m aspire.run \
    --task-dir "$task" --engine capx \
    --capx-cmd "$VENV $CAPX --workdir /home/demo/cap-x --config-path $CFG" \
    --out-root "$out" --library "$lib" --s-dbg 0 --s-val 200-204 --t 2 \
    > "$rdir/log.txt" 2>&1
  tail -1 "$rdir/log.txt" > "$rdir/summary.json"
  touch "$rdir/DONE"
  echo "done 10_2/$arm/$rep"
}

# 2 concurrent at a time across the 10 cells
pids=()
for arm in warm_dumpall cold; do
  for rep in 6 7 8 9 10; do
    run_cell "$arm" "$rep" &
    pids+=($!)
    # cap concurrency at 2
    while [ "$(jobs -rp | wc -l)" -ge 2 ]; do sleep 30; done
  done
done
wait
echo "=== ALL 10_2 REMAINING CELLS DONE ==="
