#!/bin/bash
# Phase 1 of the curriculum-accumulation experiment: run the 4 NON-LIFT tasks in
# sequence, all sharing ONE library dir so admitted skills accumulate (the paper's
# layer-2 curriculum). Single-task runs (NOT --tasks-root) so each task uses its own
# env config. --t 0 throughout. Spec:
# docs/superpowers/specs/2026-07-20-curriculum-accumulation-design.md
set -u
cd "$(dirname "$0")/.."
REPO="$PWD"

ROOT=${ROOT:-$HOME/aspire_runs/curriculum}
ACCUM_LIB=${ACCUM_LIB:-$ROOT/accumulated_library}
FIXT="$REPO/runs/2026-07-20-curriculum/tasks/robosuite"
TASKS=(cube_lifting cube_stack nut_assembly two_arm_handover)   # curriculum order; lift excluded

mkdir -p "$ROOT" "$ACCUM_LIB"

for t in "${TASKS[@]}"; do
  cfg=$(ls /home/demo/cap-x/env_configs/*/*"$t"*_privileged.yaml 2>/dev/null | head -1)
  [ -n "$cfg" ] || { echo "FATAL: no env config for $t"; exit 1; }
  [ -f "$FIXT/$t/code.py" ] || { echo "FATAL: missing baseline fixture for $t"; exit 1; }
  task="$ROOT/accumulate/robosuite/$t"
  echo "=== CURRICULUM ACCUMULATE task=$t $(date -u +%FT%TZ) ==="
  if [ -f "$task/VALIDATION_DONE" ]; then echo "=== $t done, skip ==="; continue; fi
  if ! curl -s -o /dev/null --max-time 5 http://127.0.0.1:8110/; then
    echo "=== $t SKIPPED: LLM proxy :8110 down ==="; continue; fi
  mkdir -p "$task" "$ROOT/accumulate/exec_$t"
  cp "$FIXT/$t/code.py" "$task/code.py"
  MUJOCO_GL=egl PATH="$HOME/.local/bin:$PATH" python3 -m aspire.run \
    --task-dir "$task" --engine capx \
    --capx-cmd "/home/demo/cap-x/.venv/bin/python $REPO/scripts/capx_execute.py --workdir /home/demo/cap-x --config-path $cfg" \
    --out-root "$ROOT/accumulate/exec_$t" \
    --library "$ACCUM_LIB" \
    --s-val 100-119 --t 0
  echo "=== $t exit=$? ==="
done

echo "=== ACCUMULATED LIBRARY: $ACCUM_LIB ==="
python3 -c "from aspire.skill_library import SkillLibrary; s=SkillLibrary('$ACCUM_LIB').load_all(); print('accumulated skills:', len(s), [x.name for x in s])"
echo "=== CURRICULUM ACCUMULATE DONE $(date -u +%FT%TZ) ==="
