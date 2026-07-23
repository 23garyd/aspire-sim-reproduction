#!/bin/bash
# ASPIRE LIBERO skill-accumulation FRONTIER campaign v2
# (spec: docs/superpowers/specs/2026-07-22-libero-accum-frontier-design.md).
# Two coupled levers over v1: (L1) a DEEPER baseline that folds in the two prior
# bug-fix lessons so the banked skill is a place/transport STRATEGY, not plumbing;
# (L2) FRONTIER test-task selection (solve exactly 1-of-2 cold probes) + higher N,
# so there is room for a warm-vs-cold success gap. Reuses aspire/ unchanged; runs
# LIBERO via cap-x .venv-libero. DRY=1 prints the plan without running (no GPU/credits).
# Idempotent via per-run DONE markers.
set -u
cd "$(dirname "$0")/.."
REPO="$PWD"
VENV=/home/demo/cap-x/.venv-libero/bin/python
CAPX="$REPO/scripts/capx_execute.py"
RUNS="$REPO/runs/2026-07-22-libero-accum-frontier"
TMPL="$RUNS/franka_libero_spatial_0_privileged.yaml"
BASELINE="$RUNS/baseline_grasp_lift.py"
ROOT=${ROOT:-$HOME/aspire_runs/libero_accum_v2}
CFGDIR="$ROOT/configs"
ACCUM_LIB="$ROOT/accumulated_library"
DRY=${DRY:-0}
ACCUM_TASKS=(0 1 2)              # curriculum: bank the grasp-place STRATEGY skill
CALIB_SHORTLIST=(8 6 5 3 9 7 4)  # held-out candidates; frontier probe picks 2
REPEATS=5                        # warm/cold repeats per selected test task (per arm)
PROBE_T=3                        # frontier probe budget (cheap cold probe)
PROBE_REPEATS=2                  # probe repeats per candidate (keep exactly-1-of-2)
TEST_T=5                         # warm-vs-cold test budget

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

solved_of() {  # solved_of <summary.json> -> 1 if dbg_score>=1.0 else 0
  python3 -c "import json,sys; s=json.load(open(sys.argv[1])); print(1 if float(s.get('dbg_score',0))>=1.0 else 0)" "$1" 2>/dev/null || echo 0
}

echo "=== PHASE 0: preflight guard + config gen ==="
if [ "$DRY" != 1 ]; then
  $VENV -c "import robosuite,sys; sys.exit(0 if robosuite.__version__.startswith('1.4') else 1)" \
    || { echo "FATAL: .venv-libero robosuite is not 1.4.x (LIBERO requires 1.4.0). Aborting."; exit 1; }
else
  echo "[dry] PHASE 0 preflight: assert $VENV robosuite startswith 1.4"
fi
for tid in "${ACCUM_TASKS[@]}" "${CALIB_SHORTLIST[@]}"; do gen_cfg "$tid" >/dev/null; done

echo "=== PHASE 1: accumulate deeper baseline on {${ACCUM_TASKS[*]}} (shared library $ACCUM_LIB) at --t $TEST_T ==="
mkdir -p "$ACCUM_LIB"
for tid in "${ACCUM_TASKS[@]}"; do run_one "$tid" "$ACCUM_LIB" "accumulate/spatial_$tid" "$TEST_T"; done
echo "=== PHASE 1 GATE: library must bank a PLACE/TRANSPORT/RELEASE strategy skill ==="
if [ "$DRY" != 1 ]; then
  if grep -riE 'place|transport|release|plate' "$ACCUM_LIB" --include=*.md >/dev/null 2>&1; then
    echo "GATE PASS: a place/transport/release strategy skill is banked."
  else
    echo "GATE FAIL: no banked skill signals a place/transport/release repair -> the deeper-baseline premise did not hold at this budget. Stopping."; exit 2
  fi
else
  echo "[dry] PHASE 1 gate: grep -riE 'place|transport|release|plate' $ACCUM_LIB --include=*.md ; else FAIL"
fi

echo "=== PHASE 2A: frontier probe (cold, empty lib, --t $PROBE_T x $PROBE_REPEATS) over shortlist {${CALIB_SHORTLIST[*]}} ==="
SELECTED=()
for tid in "${CALIB_SHORTLIST[@]}"; do
  nsolved=0
  for rep in $(seq 1 "$PROBE_REPEATS"); do
    run_one "$tid" "$ROOT/probe/spatial_$tid/$rep/lib" "probe/spatial_$tid/$rep" "$PROBE_T"
    if [ "$DRY" != 1 ]; then
      nsolved=$(( nsolved + $(solved_of "$ROOT/probe/spatial_$tid/$rep/summary.json") ))
    fi
  done
  if [ "$DRY" != 1 ]; then
    echo "probe spatial_$tid: solved $nsolved/$PROBE_REPEATS"
    [ "$nsolved" -eq 1 ] && SELECTED+=("$tid")   # frontier band: exactly 1-of-2
  else
    echo "[dry] frontier probe task_id $tid (cold, --t $PROBE_T, $PROBE_REPEATS reps); keep if exactly 1-of-2 solved"
  fi
  [ "${#SELECTED[@]}" -ge 2 ] && break
done
if [ "$DRY" = 1 ]; then SELECTED=(8 6); fi
echo "=== SELECTED FRONTIER TEST TASKS: ${SELECTED[*]:-none} ==="
if [ "$DRY" != 1 ] && [ "${#SELECTED[@]}" -lt 2 ]; then
  echo "GATE FAIL: <2 frontier tasks (exactly-1-of-2) after the whole shortlist. No frontier band exists at this budget."; exit 3; fi
# Write selected_tasks.json under root (analysis reads this to match the arms).
python3 -c "import json,sys; open(sys.argv[1],'w').write(json.dumps([int(x) for x in sys.argv[2:]]))" \
  "$ROOT/selected_tasks.json" "${SELECTED[@]}" 2>/dev/null \
  || printf '[%s]\n' "$(IFS=,; echo "${SELECTED[*]}")" > "$ROOT/selected_tasks.json"
echo "wrote $ROOT/selected_tasks.json = [$(IFS=,; echo "${SELECTED[*]}")]"

echo "=== PHASE 2B: warm vs cold on selected tasks ($REPEATS repeats/arm, --t $TEST_T) ==="
for tid in "${SELECTED[@]}"; do
  for rep in $(seq 1 "$REPEATS"); do
    # WARM: a fresh COPY of the frozen accumulated library per repeat (no cross-repeat leak).
    warm_lib="$ROOT/test/spatial_$tid/warm/$rep/lib"; mkdir -p "$warm_lib"
    [ "$DRY" = 1 ] || cp -r "$ACCUM_LIB/." "$warm_lib/" 2>/dev/null
    run_one "$tid" "$warm_lib" "test/spatial_$tid/warm/$rep" "$TEST_T"
    # COLD: a fresh EMPTY lib dir per repeat. All repeats independent t=5 runs.
    run_one "$tid" "$ROOT/test/spatial_$tid/cold/$rep/lib" "test/spatial_$tid/cold/$rep" "$TEST_T"
  done
done

echo "=== PHASE 3: analyze ==="
if [ "$DRY" != 1 ]; then
  python3 "$REPO/scripts/analyze_libero_accumulation_v2.py" --root "$ROOT"
else
  echo "[dry] python3 scripts/analyze_libero_accumulation_v2.py --root $ROOT"
fi
echo "=== CAMPAIGN v2 DONE ($(date -u +%FT%TZ)) root=$ROOT ==="
