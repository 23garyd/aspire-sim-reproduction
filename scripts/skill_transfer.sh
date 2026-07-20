#!/bin/bash
# Skill-transfer test: does seeding a lift run's library with HANDOVER-provenance
# skills beat an empty library? Two arms, single manipulated variable = library
# contents. Arm S seeds each repeat's library from the committed 2-skill fixture;
# arm E leaves it empty. Both --t 0 (evosearch off), same baseline + seeds. Spec:
# docs/superpowers/specs/2026-07-19-skill-transfer-test-design.md
set -u
cd "$(dirname "$0")/.."
REPO="$PWD"

N=${N:-8}
ROOT=${ROOT:-$HOME/aspire_runs/skill_transfer}
SEED="${SEED:-$REPO/runs/2026-07-19-skill-transfer/seed_library}"
BASELINE=$HOME/aspire_runs/m1_baseline/claude-opus-4-8/two_arm_lift/trial_01_sandboxrc_0_reward_0.026_taskcompleted_0/code.py
CFG=/home/demo/cap-x/env_configs/two_arm_lift/franka_robosuite_two_arm_lift_privileged.yaml
CAPX_CMD="/home/demo/cap-x/.venv/bin/python $REPO/scripts/capx_execute.py --workdir /home/demo/cap-x --config-path $CFG"

[ -f "$BASELINE" ] || { echo "FATAL: baseline missing: $BASELINE"; exit 1; }
[ -d "$SEED" ]    || { echo "FATAL: seed library missing: $SEED"; exit 1; }
mkdir -p "$ROOT"

run_arm() {           # $1 = arm label (S|E), $2 = seed dir ("" = empty library)
  local arm="$1" seed="$2"
  for i in $(seq -f "%02g" 1 "$N"); do
    local rep="$ROOT/$arm/rep_$i" task="$ROOT/$arm/rep_$i/robosuite/two_arm_lift"
    echo "=== SKILL-TRANSFER arm=$arm rep=$i/$N $(date -u +%FT%TZ) ==="
    if [ -f "$task/VALIDATION_DONE" ]; then echo "=== $arm/rep_$i done, skip ==="; continue; fi
    if ! curl -s -o /dev/null --max-time 5 http://127.0.0.1:8110/; then
      echo "=== $arm/rep_$i SKIPPED: LLM proxy :8110 down ==="; continue; fi
    mkdir -p "$task" "$rep/skill_library" "$rep/exec"
    cp "$BASELINE" "$task/code.py"
    [ -n "$seed" ] && cp -r "$seed"/. "$rep/skill_library/"
    MUJOCO_GL=egl PATH="$HOME/.local/bin:$PATH" python3 -m aspire.run \
      --task-dir "$task" --engine capx --capx-cmd "$CAPX_CMD" \
      --out-root "$rep/exec" --library "$rep/skill_library" \
      --s-val 100-119 --t 0
    echo "=== $arm/rep_$i exit=$? ==="
  done
}

run_arm S "$SEED"
run_arm E ""
echo "=== SKILL-TRANSFER DONE $(date -u +%FT%TZ) ==="
