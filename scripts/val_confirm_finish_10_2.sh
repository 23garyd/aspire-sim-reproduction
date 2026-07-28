#!/bin/bash
# Finish the last 10 cells of the val-confirmatory campaign (10_2 warm+cold reps 6-10)
# via DIRECT aspire.run, SERIALLY (concurrency=1: each cell starts its own env server on
# a fixed port, so concurrent cells collide — must be serial). Bypasses the parallel
# runner's shared api-server-holder bug. Billing: SUBSCRIPTION (env -u ANTHROPIC_API_KEY)
# — the API key is throttled after heavy use; the Max subscription has recovered.
# Only marks a cell DONE if its summary.json is VALID (no fake-DONE on failure).
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
  env -u ANTHROPIC_API_KEY MUJOCO_GL=egl PATH="$HOME/.local/bin:$PATH" python3 -m aspire.run \
    --task-dir "$task" --engine capx \
    --capx-cmd "$VENV $CAPX --workdir /home/demo/cap-x --config-path $CFG" \
    --out-root "$out" --library "$lib" --s-dbg 0 --s-val 200-204 --t 2 \
    > "$rdir/log.txt" 2>&1
  tail -1 "$rdir/log.txt" > "$rdir/summary.json"
  # only DONE if the summary is a valid JSON object carrying val_score
  if python3 -c "import json,sys; d=json.load(open('$rdir/summary.json')); sys.exit(0 if 'val_score' in d else 1)" 2>/dev/null; then
    touch "$rdir/DONE"; echo "done 10_2/$arm/$rep val=$(python3 -c "import json;print(json.load(open('$rdir/summary.json'))['val_score'])" 2>/dev/null)"
  else
    echo "FAILED 10_2/$arm/$rep (no valid summary — left un-DONE)"
  fi
}

for arm in warm_dumpall cold; do
  for rep in 6 7 8 9 10; do
    run_cell "$arm" "$rep"        # SERIAL: no & — one env server at a time
  done
done
n=$(find "$ROOT/test/10_2/warm_dumpall" "$ROOT/test/10_2/cold" -name DONE 2>/dev/null | wc -l)
echo "=== 10_2 DONE now: $n/20 (10 pre-existing + up to 10 new) ==="
