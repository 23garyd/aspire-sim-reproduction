#!/bin/bash
# Curriculum-accumulation experiment orchestrator.
# Phase 1: accumulate a shared library over the 4 non-lift tasks.
# Phase 2: warm (S, accumulated library) vs cold (E, empty) on two_arm_lift,
#          reusing skill_transfer.sh with SEED pointed at the accumulated library.
# Spec: docs/superpowers/specs/2026-07-20-curriculum-accumulation-design.md
set -u
cd "$(dirname "$0")/.."
REPO="$PWD"

ROOT=${ROOT:-$HOME/aspire_runs/curriculum}
ACCUM_LIB=${ACCUM_LIB:-$ROOT/accumulated_library}
N=${N:-5}

echo "=== CURRICULUM PHASE 1 (accumulate) ==="
ROOT="$ROOT" ACCUM_LIB="$ACCUM_LIB" bash "$REPO/scripts/curriculum_accumulate.sh"

echo "=== CURRICULUM PHASE 2 (warm S vs cold E on two_arm_lift) ==="
# skill_transfer.sh: arm S copies $SEED into each repeat's library, arm E empty.
SEED="$ACCUM_LIB" ROOT="$ROOT" N="$N" bash "$REPO/scripts/skill_transfer.sh"

echo "=== CURRICULUM DONE — analyze with: python3 scripts/analyze_skill_transfer.py $ROOT ==="
