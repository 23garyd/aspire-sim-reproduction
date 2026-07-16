#!/bin/bash
# scripts/m1_baseline.sh — run ON the GPU box after M0 passes. Reproduces the
# released CaP-Agent0 baseline on 5 Robosuite tasks (paper Table-3 subset incl.
# the bimanual handover). Results land in ~/aspire_runs/m1_baseline/. These are
# OUR baseline numbers: every later ASPIRE comparison runs against results.json
# here, never against the paper's table directly.
set -euo pipefail
cd ~/cap-x
OUT=~/aspire_runs/m1_baseline
mkdir -p "$OUT"

# Task list: confirmed against ~/cap-x/env_configs/ during M0. CaP-X has no door or
# pick_place_can task; nut_assembly is the nearest pick/place. Handover is the headline.
TASKS=(cube_lifting cube_stack two_arm_handover nut_assembly two_arm_lift)

# Model id for the launcher is confirmed during M0 (CaP-X docs show an
# OpenAI-compatible proxy; use the Claude model configured there). CAPX_MODEL
# is mandatory: baseline numbers must never silently run under a proxy default.
MODEL="${CAPX_MODEL:?set CAPX_MODEL to the model id confirmed in M0}"

shopt -s nullglob
for t in "${TASKS[@]}"; do
  matches=(env_configs/*"$t"*.yaml)
  cfg="${matches[0]:-}"
  [ -n "$cfg" ] || { echo "FAIL: no env config matching '$t' in env_configs/"; exit 1; }
  echo "== CaP-Agent0 baseline: $t ($cfg, model=$MODEL) =="
  uv run --no-sync --active capx/envs/launch.py \
    --config-path "$cfg" \
    --model "$MODEL" \
    2>&1 | tee "$OUT/$t.log"
done

cat <<MSG
All task launches finished. Now collect per-task success into $OUT/results.json:
  {"<task>": {"episodes": N, "successes": M, "model": "$MODEL", "date": "<iso>"}}
(The launcher's own output layout is confirmed during M0 — read the logs above.)
MSG
