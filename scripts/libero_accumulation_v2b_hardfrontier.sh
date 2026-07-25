#!/bin/bash
# ASPIRE LIBERO frontier campaign — attempt 2 (HARDEN FRONTIER).
# Reuses the frozen accumulated strategy library + the same frontier tasks (8,6)
# from attempt 1, but drops the TEST budget to --t 2 so cold is starved and a
# banked strategy skill has room to change solve/no-solve. Test-only: NO
# re-accumulate, NO re-probe (saves budget). Idempotent via DONE markers.
# Mirrors run_one from libero_accumulation_v2.sh exactly.
set -u
cd "$(dirname "$0")/.."
REPO="$PWD"
VENV=/home/demo/cap-x/.venv-libero/bin/python
CAPX="$REPO/scripts/capx_execute.py"
RUNS="$REPO/runs/2026-07-22-libero-accum-frontier"
TMPL="$RUNS/franka_libero_spatial_0_privileged.yaml"
BASELINE="$RUNS/baseline_grasp_lift.py"
SRC_LIB=${SRC_LIB:-$HOME/aspire_runs/libero_accum_v2/accumulated_library}   # frozen strategy library
ROOT=${ROOT:-$HOME/aspire_runs/libero_accum_v2b}
CFGDIR="$ROOT/configs"
FROZEN_LIB="$ROOT/accumulated_library"
DRY=${DRY:-0}
SELECTED=(8 6)                   # same frontier tasks as attempt 1
REPEATS=5
TEST_T=${TEST_T:-2}              # HARDENED test budget

mkdir -p "$ROOT" "$CFGDIR"
gen_cfg() { local tid=$1; local out="$CFGDIR/spatial_$tid.yaml"; sed "s/task_id: 0/task_id: $tid/" "$TMPL" > "$out"; echo "$out"; }

run_one() {
  local tid=$1 lib=$2 sub=$3 t=$4
  local cfg; cfg=$(gen_cfg "$tid")
  local rdir="$ROOT/$sub" task="$ROOT/$sub/task" out="$ROOT/$sub/exec"
  if [ -f "$rdir/DONE" ]; then echo "skip $sub (DONE)"; return; fi
  local capxcmd="$VENV $CAPX --workdir /home/demo/cap-x --config-path $cfg"
  if [ "$DRY" = 1 ]; then
    echo "[dry] $sub: aspire.run --library $lib --t $t   ($(grep -o 'task_id: [0-9]*' "$cfg"))"; return
  fi
  mkdir -p "$task" "$out"; cp "$BASELINE" "$task/code.py"
  env -u ANTHROPIC_API_KEY MUJOCO_GL=egl PATH="$HOME/.local/bin:$PATH" python3 -m aspire.run \
    --task-dir "$task" --engine capx --capx-cmd "$capxcmd" \
    --out-root "$out" --library "$lib" --s-dbg 0 --s-val 100 --t "$t" \
    2>&1 | tee "$rdir/log.txt" | tail -1 > "$rdir/summary.json"
  touch "$rdir/DONE"
}

echo "=== PHASE 0: preflight + freeze library ==="
if [ "$DRY" != 1 ]; then
  $VENV -c "import robosuite,sys; sys.exit(0 if robosuite.__version__.startswith('1.4') else 1)" \
    || { echo "FATAL: .venv-libero robosuite not 1.4.x. Aborting."; exit 1; }
  [ -d "$SRC_LIB" ] || { echo "FATAL: source library $SRC_LIB missing (run attempt 1 first)."; exit 1; }
  mkdir -p "$FROZEN_LIB"; cp -r "$SRC_LIB/." "$FROZEN_LIB/" 2>/dev/null
  n=$($VENV -c "from aspire.skill_library import SkillLibrary; print(len(SkillLibrary('$FROZEN_LIB').load_all()))" 2>/dev/null || echo 0)
  echo "frozen library skills: $n"
  [ "$n" -ge 1 ] || { echo "FATAL: frozen library has 0 skills. Aborting."; exit 1; }
fi
printf '[%s]\n' "$(IFS=,; echo "${SELECTED[*]}")" > "$ROOT/selected_tasks.json"
echo "selected test tasks = [$(IFS=,; echo "${SELECTED[*]}")], TEST_T=$TEST_T"

echo "=== PHASE 2B: warm vs cold on frontier tasks (${REPEATS}/arm, --t $TEST_T) ==="
for tid in "${SELECTED[@]}"; do
  for rep in $(seq 1 "$REPEATS"); do
    warm_lib="$ROOT/test/spatial_$tid/warm/$rep/lib"; mkdir -p "$warm_lib"
    [ "$DRY" = 1 ] || cp -r "$FROZEN_LIB/." "$warm_lib/" 2>/dev/null
    run_one "$tid" "$warm_lib" "test/spatial_$tid/warm/$rep" "$TEST_T"
    run_one "$tid" "$ROOT/test/spatial_$tid/cold/$rep/lib" "test/spatial_$tid/cold/$rep" "$TEST_T"
  done
done

echo "=== ANALYZE ==="
if [ "$DRY" != 1 ]; then python3 "$REPO/scripts/analyze_libero_accumulation_v2.py" --root "$ROOT"; else echo "[dry] analyze --root $ROOT"; fi
echo "=== ATTEMPT 2 DONE root=$ROOT ==="
