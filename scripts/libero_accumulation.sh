#!/bin/bash
# ASPIRE LIBERO skill-accumulation campaign (spec: docs/superpowers/specs/2026-07-21-libero-skill-accumulation-design.md).
# Warm-vs-cold on libero_spatial. Reuses aspire/ unchanged; runs LIBERO via cap-x .venv-libero.
# DRY=1 prints the plan without running (no GPU/credits). Idempotent via per-run DONE markers.
set -u
cd "$(dirname "$0")/.."
REPO="$PWD"
VENV=/home/demo/cap-x/.venv-libero/bin/python
CAPX="$REPO/scripts/capx_execute.py"
TMPL=/home/demo/cap-x/env_configs/libero/franka_libero_spatial_0_privileged.yaml
RUNS="$REPO/runs/2026-07-21-libero-accumulation"
BASELINE="$RUNS/baseline_grasp_place.py"
ROOT=${ROOT:-$HOME/aspire_runs/libero_accum}
CFGDIR="$ROOT/configs"
ACCUM_LIB="$ROOT/accumulated_library"
DRY=${DRY:-0}
ACCUM_TASKS=(2 1 0)          # curriculum: bank the grasp-place skill
CALIB_SHORTLIST=(8 6 5 3 9 7)    # held-out candidates; cold calibration (--t 5) picks 2
REPEATS=2

mkdir -p "$ROOT" "$CFGDIR"

gen_cfg() { local tid=$1; local out="$CFGDIR/spatial_$tid.yaml"; sed "s/task_id: 0/task_id: $tid/" "$TMPL" > "$out"; echo "$out"; }

# run_one <task_id> <library> <sub> <t>  -> one aspire.run into $ROOT/<sub>
run_one() {
  local tid=$1 lib=$2 sub=$3 t=$4
  local cfg; cfg=$(gen_cfg "$tid")
  local rdir="$ROOT/$sub" task="$ROOT/$sub/task" out="$ROOT/$sub/exec"
  if [ -f "$rdir/DONE" ]; then echo "skip $sub (DONE)"; return; fi
  local capxcmd="$VENV $CAPX --workdir /home/demo/cap-x --config-path $cfg"
  if [ "$DRY" = 1 ]; then
    echo "[dry] $sub: aspire.run --task-dir $task --engine capx --capx-cmd \"$capxcmd\" --library $lib --s-dbg 0 --s-val 100 --t $t   ($(grep -o 'task_id: [0-9]*' "$cfg"))"
    return
  fi
  mkdir -p "$task" "$out"; cp "$BASELINE" "$task/code.py"
  MUJOCO_GL=egl PATH="$HOME/.local/bin:$PATH" python3 -m aspire.run \
    --task-dir "$task" --engine capx --capx-cmd "$capxcmd" \
    --out-root "$out" --library "$lib" --s-dbg 0 --s-val 100 --t "$t" \
    2>&1 | tee "$rdir/log.txt" | tail -1 > "$rdir/summary.json"
  touch "$rdir/DONE"
}

skill_count() { $VENV -c "from aspire.skill_library import SkillLibrary; print(len(SkillLibrary('$1').load_all()))" 2>/dev/null || echo 0; }

echo "=== PHASE 0: preflight guard + config gen ==="
if [ "$DRY" != 1 ]; then
  $VENV -c "import robosuite,sys; sys.exit(0 if robosuite.__version__.startswith('1.4') else 1)" \
    || { echo "FATAL: .venv-libero robosuite is not 1.4.x (LIBERO requires 1.4.0). Aborting."; exit 1; }
fi
for tid in "${ACCUM_TASKS[@]}" "${CALIB_SHORTLIST[@]}"; do gen_cfg "$tid" >/dev/null; done

echo "=== PHASE 1: accumulate (shared library $ACCUM_LIB) ==="
mkdir -p "$ACCUM_LIB"
for tid in "${ACCUM_TASKS[@]}"; do run_one "$tid" "$ACCUM_LIB" "accumulate/spatial_$tid" 5; done
if [ "$DRY" != 1 ]; then
  n=$(skill_count "$ACCUM_LIB")
  echo "=== accumulated skills: $n ==="
  [ "$n" -ge 1 ] || { echo "GATE FAIL: Phase 1 admitted 0 skills -> warm==cold trivially. Stopping before Phase 2."; exit 2; }
fi

echo "=== PHASE 2a: cold calibration (--t 5) over held-out shortlist -> pick 2 solvable ==="
SELECTED=()
for tid in "${CALIB_SHORTLIST[@]}"; do
  run_one "$tid" "$ROOT/calib/empty_$tid" "test/spatial_$tid/cold/1" 5    # empty lib per task; this IS cold repeat 1
  if [ "$DRY" != 1 ]; then
    solved=$(python3 -c "import json; s=json.load(open('$ROOT/test/spatial_$tid/cold/1/summary.json')); print(1 if float(s.get('dbg_score',0))>=1.0 else 0)" 2>/dev/null || echo 0)
    [ "$solved" = 1 ] && SELECTED+=("$tid")
  else
    echo "[dry] calibrate held-out task_id $tid (cold, --t 5); solvable ones become test tasks"
  fi
  [ "${#SELECTED[@]}" -ge 2 ] && break
done
if [ "$DRY" = 1 ]; then SELECTED=(8 6); fi
echo "=== SELECTED TEST TASKS: ${SELECTED[*]:-none} ==="
if [ "$DRY" != 1 ] && [ "${#SELECTED[@]}" -lt 2 ]; then
  echo "GATE FAIL: <2 held-out tasks solvable in calibration. Widen CALIB_SHORTLIST or budget."; exit 3; fi

echo "=== PHASE 2b: warm vs cold on selected tasks (2 repeats/arm; cold repeat 1 = calibration) ==="
for tid in "${SELECTED[@]}"; do
  for rep in $(seq 1 $REPEATS); do
    warm_lib="$ROOT/test/spatial_$tid/warm/$rep/lib"; mkdir -p "$warm_lib"
    [ "$DRY" = 1 ] || cp -r "$ACCUM_LIB/." "$warm_lib/" 2>/dev/null
    run_one "$tid" "$warm_lib" "test/spatial_$tid/warm/$rep" 5             # WARM: copy of frozen accumulated lib
    if [ "$rep" -ge 2 ]; then run_one "$tid" "$ROOT/test/spatial_$tid/cold/$rep/lib" "test/spatial_$tid/cold/$rep" 5; fi  # COLD repeat 2 (rep1 = calibration)
  done
done

echo "=== ANALYZE ==="
if [ "$DRY" != 1 ]; then python3 "$REPO/scripts/analyze_libero_accumulation.py" --root "$ROOT"; else echo "[dry] python3 scripts/analyze_libero_accumulation.py --root $ROOT"; fi
echo "=== CAMPAIGN DONE ($(date -u +%FT%TZ)) root=$ROOT ==="
