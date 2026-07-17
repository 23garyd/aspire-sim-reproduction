#!/bin/bash
# Campaign repeats on two_arm_lift — the variance instrument for the M3-pilot
# (5/5) vs M3X (0/20) contradiction. Spec:
# docs/superpowers/specs/2026-07-17-lift-repeats-variance-design.md
#
# N independent, sequential repeats. Each repeat gets a fresh task dir (pristine
# baseline code.py only), a fresh EMPTY skill library, and its own exec
# out-root, so repeats cannot contaminate each other (state markers live in the
# task dir; skill admission mutates the library). Config matches M3X exactly.
#
# Idempotent/resumable: a repeat whose task dir already has VALIDATION_DONE is
# skipped, so rerunning after a crash continues where it left off.
set -u
cd "$(dirname "$0")/.."

N=${N:-5}
ROOT=${ROOT:-$HOME/aspire_runs/lift_repeats}
BASELINE=$HOME/aspire_runs/m1_baseline/claude-opus-4-8/two_arm_lift/trial_01_sandboxrc_0_reward_0.026_taskcompleted_0/code.py
CFG=/home/demo/cap-x/env_configs/two_arm_lift/franka_robosuite_two_arm_lift_privileged.yaml
CAPX_CMD="/home/demo/cap-x/.venv/bin/python $PWD/scripts/capx_execute.py --workdir /home/demo/cap-x --config-path $CFG"

[ -f "$BASELINE" ] || { echo "FATAL: baseline missing: $BASELINE"; exit 1; }
mkdir -p "$ROOT"

for i in $(seq -w 1 "$N"); do
  rep="$ROOT/rep_$i"
  task="$rep/robosuite/two_arm_lift"
  echo "=== LIFT REPEAT $i/$N $(date -u +%FT%TZ) ==="
  if [ -f "$task/VALIDATION_DONE" ]; then
    echo "=== rep_$i already VALIDATION_DONE, skipping ==="
    continue
  fi
  # Proxy liveness: a dead proxy fails the repeat, not the campaign.
  if ! curl -s -o /dev/null --max-time 5 http://127.0.0.1:8110/; then
    echo "=== rep_$i SKIPPED: LLM proxy port 8110 not answering ==="
    continue
  fi
  mkdir -p "$task" "$rep/skill_library" "$rep/exec"
  cp "$BASELINE" "$task/code.py"
  MUJOCO_GL=egl PATH="$HOME/.local/bin:$PATH" python3 -m aspire.run \
    --task-dir "$task" \
    --engine capx \
    --capx-cmd "$CAPX_CMD" \
    --out-root "$rep/exec" \
    --library "$rep/skill_library" \
    --s-val 100-119
  echo "=== rep_$i exit=$? ==="
done
echo "=== LIFT REPEATS DONE $(date -u +%FT%TZ) ==="
