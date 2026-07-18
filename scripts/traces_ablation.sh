#!/bin/bash
# Traces-vs-retry ablation A/B campaign on two_arm_lift. Two arms, single manipulated
# variable: arm T sees traces, arm C is --ablate-traces. Both run --t 0 (evosearch off,
# Stage-1 repair only) so the comparison isolates the repair actor. Spec:
# docs/superpowers/specs/2026-07-17-traces-vs-retry-ablation-design.md
set -u
cd "$(dirname "$0")/.."

N=${N:-8}
ROOT=${ROOT:-$HOME/aspire_runs/traces_ablation}
BASELINE=$HOME/aspire_runs/m1_baseline/claude-opus-4-8/two_arm_lift/trial_01_sandboxrc_0_reward_0.026_taskcompleted_0/code.py
CFG=/home/demo/cap-x/env_configs/two_arm_lift/franka_robosuite_two_arm_lift_privileged.yaml
CAPX_CMD="/home/demo/cap-x/.venv/bin/python $PWD/scripts/capx_execute.py --workdir /home/demo/cap-x --config-path $CFG"

[ -f "$BASELINE" ] || { echo "FATAL: baseline missing: $BASELINE"; exit 1; }
mkdir -p "$ROOT"

run_arm() {           # $1 = arm label (T|C), $2 = extra aspire.run flags
  local arm="$1" extra="$2"
  for i in $(seq -w 1 "$N"); do
    local rep="$ROOT/$arm/rep_$i" task="$ROOT/$arm/rep_$i/robosuite/two_arm_lift"
    echo "=== ABLATION arm=$arm rep=$i/$N $(date -u +%FT%TZ) ==="
    if [ -f "$task/VALIDATION_DONE" ]; then echo "=== $arm/rep_$i done, skip ==="; continue; fi
    if ! curl -s -o /dev/null --max-time 5 http://127.0.0.1:8110/; then
      echo "=== $arm/rep_$i SKIPPED: LLM proxy :8110 down ==="; continue; fi
    mkdir -p "$task" "$rep/skill_library" "$rep/exec"
    cp "$BASELINE" "$task/code.py"
    MUJOCO_GL=egl PATH="$HOME/.local/bin:$PATH" python3 -m aspire.run \
      --task-dir "$task" --engine capx --capx-cmd "$CAPX_CMD" \
      --out-root "$rep/exec" --library "$rep/skill_library" \
      --s-val 100-119 --t 0 $extra
    echo "=== $arm/rep_$i exit=$? ==="
  done
}

run_arm T ""
run_arm C "--ablate-traces"
echo "=== ABLATION DONE $(date -u +%FT%TZ) ==="
