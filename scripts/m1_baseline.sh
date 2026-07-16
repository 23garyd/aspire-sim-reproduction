#!/bin/bash
# scripts/m1_baseline.sh — run ON the GPU box after M0 passes. Reproduces the
# released CaP-Agent0 baseline on 5 Robosuite tasks. Results land in
# ~/aspire_runs/m1_baseline/. These are OUR baseline numbers: every later ASPIRE
# comparison runs against these, never against the paper's table directly.
#
# Observation mode: PRIVILEGED configs (ground-truth object poses, PyRoKi only) —
# matches the observation mode our ASPIRE-side runs use, so baseline-vs-ASPIRE is
# apples-to-apples; also avoids the SAM3/HuggingFace weight dependency. Say so in
# any report: this is CaP-Agent0-privileged, not the full-vision variant.
#
# Prereq: the LLM proxy must be serving on :8110
#   (cd ~/cap-x && uv run --no-sync python capx/serving/openrouter_server.py \
#      --api-key "$ANTHROPIC_API_KEY" --base-url https://api.anthropic.com/v1/ --port 8110)
#
# Scale: TRIALS=10 pilot by default; rerun with TRIALS=100 for paper-scale.
set -euo pipefail
cd ~/cap-x
OUT=~/aspire_runs/m1_baseline
mkdir -p "$OUT"

# Task list: confirmed against ~/cap-x/env_configs/ during M0. CaP-X has no door or
# pick_place_can task; nut_assembly is the nearest pick/place. Handover is the headline.
TASKS=(cube_lifting cube_stack two_arm_handover nut_assembly two_arm_lift)

# CAPX_MODEL is mandatory: baseline numbers must never silently run under a default.
MODEL="${CAPX_MODEL:?set CAPX_MODEL to the model id served by the :8110 proxy}"
TRIALS="${TRIALS:-10}"

curl -s -m 45 http://127.0.0.1:8110/chat/completions -o /dev/null -w "%{http_code}" \
     -H 'Content-Type: application/json' \
     -d '{"model":"'"$MODEL"'","messages":[{"role":"user","content":"ok"}],"max_tokens":1}' \
  | grep -q 200 || { echo "FAIL: LLM proxy on :8110 not answering for model $MODEL"; exit 1; }
echo "proxy OK (model=$MODEL, trials/task=$TRIALS)"

shopt -s nullglob
for t in "${TASKS[@]}"; do
  matches=(env_configs/*"$t"*_privileged.yaml)
  cfg="${matches[0]:-}"
  [ -n "$cfg" ] || { echo "FAIL: no privileged env config matching '$t'"; exit 1; }
  echo "== CaP-Agent0 baseline: $t ($cfg, model=$MODEL, trials=$TRIALS) =="
  uv run --no-sync --active capx/envs/launch.py \
    --config-path "$cfg" \
    --model "$MODEL" \
    --total-trials "$TRIALS" \
    --output-dir "$OUT/$t" \
    2>&1 | tee "$OUT/$t.log"
done

echo "All task launches finished. Per-task artifacts under $OUT/<task>/ (trial dirs are"
echo "named ..._taskcompleted_{0|1}); logs at $OUT/<task>.log. Collect into results.json:"
echo '  {"<task>": {"trials": N, "task_completed": M, "model": "'"$MODEL"'", "mode": "privileged"}}'
