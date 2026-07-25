#!/bin/bash
# ASPIRE LIBERO tiling-curriculum + retrieval-discrimination campaign
# (spec: docs/superpowers/specs/2026-07-24-libero-tiling-curriculum-design.md).
# Three arms over a tiled library: warm_geo (geometry retrieval) vs warm_dumpall
# (stock retrieval) vs cold (empty). Separates COVERAGE from RETRIEVAL.
set -u
cd "$(dirname "$0")/.."
REPO="$PWD"
VENV=/home/demo/cap-x/.venv-libero/bin/python
CAPX="$REPO/scripts/capx_execute.py"
BOWLXY="$REPO/scripts/capx_bowl_xy.py"
TAGXY="$REPO/scripts/tag_skill_xy.py"
RUNS="$REPO/runs/2026-07-24-libero-tiling"
TMPL="$RUNS/franka_libero_spatial_0_privileged.yaml"
BASELINE="$REPO/runs/2026-07-22-libero-accum-frontier/baseline_grasp_lift.py"
ROOT=${ROOT:-$HOME/aspire_runs/libero_tiling}
CFGDIR="$ROOT/configs"
TILED_LIB="$ROOT/tiled_library"
XYDIR="$ROOT/bowl_xy"
DRY=${DRY:-0}
ACCUM_TASKS=(0 1 2 4 5 7 9)      # tile the location space
HELDOUT_TASKS=(3 6 8)            # fixed, pre-registered; not in ACCUM_TASKS
REPEATS=5
ACCUM_T=5
TEST_T=2

mkdir -p "$ROOT" "$CFGDIR" "$XYDIR"
gen_cfg() { local tid=$1; local out="$CFGDIR/spatial_$tid.yaml"; sed "s/task_id: 0/task_id: $tid/" "$TMPL" > "$out"; echo "$out"; }

# run_one <task_id> <library> <sub> <t> <extra_env>
run_one() {
  local tid=$1 lib=$2 sub=$3 t=$4 extra=${5:-}
  local cfg; cfg=$(gen_cfg "$tid")
  local rdir="$ROOT/$sub" task="$ROOT/$sub/task" out="$ROOT/$sub/exec"
  if [ -f "$rdir/DONE" ]; then echo "skip $sub (DONE)"; return; fi
  local capxcmd="$VENV $CAPX --workdir /home/demo/cap-x --config-path $cfg"
  if [ "$DRY" = 1 ]; then
    echo "[dry] $sub: aspire.run --library $lib --t $t  env[$extra]  ($(grep -o 'task_id: [0-9]*' "$cfg"))"; return
  fi
  mkdir -p "$task" "$out"; cp "$BASELINE" "$task/code.py"
  env -u ANTHROPIC_API_KEY $extra MUJOCO_GL=egl PATH="$HOME/.local/bin:$PATH" python3 -m aspire.run \
    --task-dir "$task" --engine capx --capx-cmd "$capxcmd" \
    --out-root "$out" --library "$lib" --s-dbg 0 --s-val 100 --t "$t" \
    2>&1 | tee "$rdir/log.txt" | tail -1 > "$rdir/summary.json"
  touch "$rdir/DONE"
}

bowl_xy() {  # bowl_xy <task_id> -> echoes "x,y" (cached). LIBERO prints import banners to
             # stdout before the coordinate, so keep ONLY the last line, then validate it is
             # a real "num,num" — a garbage xy would silently disable geometry retrieval.
  local tid=$1 f="$XYDIR/spatial_$tid.txt"
  if [ ! -s "$f" ]; then
    MUJOCO_GL=egl "$VENV" "$BOWLXY" --workdir /home/demo/cap-x --config-path "$(gen_cfg "$tid")" 2>/dev/null | tail -1 > "$f"
  fi
  if ! grep -Eq '^-?[0-9]+(\.[0-9]+)?,-?[0-9]+(\.[0-9]+)?$' "$f"; then
    echo "FATAL: bowl_xy for task $tid is not a coordinate: '$(cat "$f")'. Aborting (would break geometry retrieval)." >&2
    rm -f "$f"; exit 4
  fi
  cat "$f"
}

echo "=== PHASE 0: preflight + config gen ==="
if [ "$DRY" != 1 ]; then
  $VENV -c "import robosuite,sys; sys.exit(0 if robosuite.__version__.startswith('1.4') else 1)" \
    || { echo "FATAL: .venv-libero robosuite not 1.4.x. Aborting."; exit 1; }
else echo "[dry] PHASE 0 preflight: assert $VENV robosuite startswith 1.4"; fi
for tid in "${ACCUM_TASKS[@]}" "${HELDOUT_TASKS[@]}"; do gen_cfg "$tid" >/dev/null; done

echo "=== PHASE 1: tile-accumulate deeper baseline on {${ACCUM_TASKS[*]}} at --t $ACCUM_T -> $TILED_LIB ==="
mkdir -p "$TILED_LIB"
for tid in "${ACCUM_TASKS[@]}"; do
  run_one "$tid" "$TILED_LIB" "accumulate/spatial_$tid" "$ACCUM_T"
  if [ "$DRY" != 1 ]; then
    xy=$(bowl_xy "$tid"); "$VENV" "$TAGXY" --library "$TILED_LIB" --xy "$xy" >/dev/null   # stamp new skills with this task's bowl xy
  else echo "[dry] tag new skills in $TILED_LIB with bowl xy of task_id $tid"; fi
done
if [ "$DRY" != 1 ]; then
  ntag=$("$VENV" -c "from aspire.skill_library import SkillLibrary; import collections; xs=[s.source_xy for s in SkillLibrary('$TILED_LIB').load_all() if s.source_xy]; print(len(xs), len(set(xs)))")
  set -- $ntag; echo "=== tiled library: $1 tagged skills from $2 distinct locations ==="
  { [ "$1" -ge 2 ] && [ "$2" -ge 2 ]; } || { echo "GATE FAIL: need >=2 tagged skills from >=2 locations to tile. Stopping."; exit 2; }
fi

echo "=== PHASE 2: fixed held-out tasks = ${HELDOUT_TASKS[*]} ==="
printf '[%s]\n' "$(IFS=,; echo "${HELDOUT_TASKS[*]}")" > "$ROOT/selected_tasks.json"

echo "=== PHASE 3: three arms (warm_geo / warm_dumpall / cold), $REPEATS/arm, --t $TEST_T ==="
for tid in "${HELDOUT_TASKS[@]}"; do
  [ "$DRY" = 1 ] && txy="0.0,0.0" || txy=$(bowl_xy "$tid")
  for rep in $(seq 1 "$REPEATS"); do
    # Arm B: warm_geo (geometry retrieval, single nearest-location skill)
    wg="$ROOT/test/spatial_$tid/warm_geo/$rep/lib"; mkdir -p "$wg"
    [ "$DRY" = 1 ] || cp -r "$TILED_LIB/." "$wg/" 2>/dev/null
    run_one "$tid" "$wg" "test/spatial_$tid/warm_geo/$rep" "$TEST_T" "ASPIRE_RETRIEVAL=geometry ASPIRE_TARGET_XY=$txy"
    # Arm A: warm_dumpall (stock retrieval)
    wd="$ROOT/test/spatial_$tid/warm_dumpall/$rep/lib"; mkdir -p "$wd"
    [ "$DRY" = 1 ] || cp -r "$TILED_LIB/." "$wd/" 2>/dev/null
    run_one "$tid" "$wd" "test/spatial_$tid/warm_dumpall/$rep" "$TEST_T"
    # Arm C: cold (empty)
    run_one "$tid" "$ROOT/test/spatial_$tid/cold/$rep/lib" "test/spatial_$tid/cold/$rep" "$TEST_T"
  done
done

echo "=== PHASE 4: ANALYZE ==="
if [ "$DRY" != 1 ]; then
  python3 "$REPO/scripts/analyze_libero_tiling.py" --root "$ROOT" --heldout "$(IFS=,; echo "${HELDOUT_TASKS[*]}")"
else echo "[dry] analyze --root $ROOT --heldout $(IFS=,; echo "${HELDOUT_TASKS[*]}")"; fi
echo "=== TILING CAMPAIGN DONE root=$ROOT ==="
