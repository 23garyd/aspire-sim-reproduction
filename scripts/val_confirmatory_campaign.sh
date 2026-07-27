#!/bin/bash
# Val-pre-registered confirmatory campaign
# (spec: docs/superpowers/specs/2026-07-26-val-confirmatory-design.md).
# Primary metric = held-out val_score (seeds 200-204). warm_dumpall vs cold on a
# mechanistically-selected overfit-band task set. Reuses the tiled library + parallel
# runner. Subscription billing. DRY=1 prints the plan. Idempotent via DONE markers.
set -u
cd "$(dirname "$0")/.."
REPO="$PWD"
VENV=/home/demo/cap-x/.venv-libero/bin/python
PAR="$REPO/scripts/libero_tiling_parallel.py"
SEL="$REPO/scripts/val_confirmatory_select.py"
ANALYZE="$REPO/scripts/analyze_libero_tiling.py"
LIB="$HOME/aspire_runs/libero_tiling/tiled_library"
RUNS="$REPO/runs/2026-07-26-val-confirmatory"
ROOT=${ROOT:-$HOME/aspire_runs/libero_val_confirm}
DRY=${DRY:-0}
VAL_SEEDS="200-204"; TEST_T="2"; PROBE_REPS=5; TEST_REPS=10
# Billing: subscription by default (strip API key); ASPIRE_USE_API=1 keeps the key + tells
# the parallel runner to keep it too, for a run the subscription rate-cap can't finish.
JOBS=${JOBS:-2}
if [ -n "${ASPIRE_USE_API:-}" ]; then BILLENV="env ASPIRE_USE_API=1"; else BILLENV="env -u ANTHROPIC_API_KEY"; fi
FRESH_10=(1 2 4 5 7 8 9)                    # libero_10 tasks never tested warm-vs-cold
REUSE_SPATIAL=(3 6 8); REUSE_10=(0 3 6)     # cold data reused from prior t=2 campaigns
mkdir -p "$ROOT"

echo "=== PHASE 0: preflight + PREREGISTRATION freeze (before any test run) ==="
if [ "$DRY" = 1 ]; then
  echo "[dry] assert .venv-libero robosuite 1.4; assert $LIB has >=2 skills"
  echo "[dry] commit $RUNS/PREREGISTRATION.md and log its git hash BEFORE any test run"
else
  $VENV -c "import robosuite,sys; sys.exit(0 if robosuite.__version__.startswith('1.4') else 1)" \
    || { echo "FATAL: .venv-libero robosuite not 1.4.x"; exit 1; }
  n=$($VENV -c "from aspire.skill_library import SkillLibrary; print(len(SkillLibrary('$LIB').load_all()))" 2>/dev/null || echo 0)
  [ "$n" -ge 2 ] || { echo "FATAL: tiled library $LIB has <2 skills ($n)"; exit 1; }
  git add "$RUNS/PREREGISTRATION.md" && git commit -q -m "prereg: val-confirmatory campaign frozen" || true
  PREREG_HASH=$(git rev-parse HEAD)
  echo "PREREGISTRATION committed at $PREREG_HASH (frozen before any test run)"
fi

echo "=== PHASE 1: cold probe (fresh libero_10 ${FRESH_10[*]}) + reuse -> select overfit band ==="
# cold-rate helper: reads a glob of cold summary.json, prints "dbg_rate val_rate"
cold_rates() {  # cold_rates <glob>
  $VENV - "$@" <<'PY'
import glob,json,sys
fs=[f for g in sys.argv[1:] for f in glob.glob(g)]
d=v=n=0
for f in fs:
    try: s=json.load(open(f))
    except: continue
    n+=1
    d+= float(s.get("dbg_score",0))>=1.0
    v+= float(s.get("val_score",0))>=0.5
print(f"{(d/n if n else 0):.4f} {(v/n if n else 0):.4f}")
PY
}
if [ "$DRY" = 1 ]; then
  echo "[dry] probe cold reps=$PROBE_REPS t=$TEST_T --s-val $VAL_SEEDS on fresh libero_10 ${FRESH_10[*]}"
  echo "[dry] reuse cold summaries: spatial ${REUSE_SPATIAL[*]} (libero_tiling), libero_10 ${REUSE_10[*]} (libero_hard)"
  echo "[dry] apply val_confirmatory_select.py -> selected_tasks.json + selection.md; gate >=2 or stop"
else
  # probe fresh libero_10 tasks (cold only) into the confirmatory root
  $BILLENV python3 "$PAR" --root "$ROOT" --suite libero_10 \
    --tasks "$(IFS=,; echo "${FRESH_10[*]}")" --arms cold --reps "$PROBE_REPS" \
    --t "$TEST_T" --s-val "$VAL_SEEDS" --library "$LIB" --no-analyze --jobs "$JOBS"
  # build candidates JSON (reused + freshly probed)
  cand="$ROOT/candidates.json"
  {
    echo "["
    first=1
    emit() { local task=$1 suite=$2 glob=$3; read dr vr < <(cold_rates "$glob")
             [ $first = 1 ] || echo ","; first=0
             printf '{"task":"%s","suite":"%s","cold_dbg_rate":%s,"cold_val_rate":%s}' "$task" "$suite" "$dr" "$vr"; }
    for t in "${REUSE_SPATIAL[@]}"; do emit "spatial_$t" libero_spatial "$HOME/aspire_runs/libero_tiling/test/spatial_$t/cold/*/summary.json"; done
    for t in "${REUSE_10[@]}"; do emit "10_$t" libero_10 "$HOME/aspire_runs/libero_hard/test/10_$t/cold/*/summary.json"; done
    for t in "${FRESH_10[@]}"; do emit "10_$t" libero_10 "$ROOT/test/10_$t/cold/*/summary.json"; done
    echo "]"
  } > "$cand"
  $VENV "$SEL" --candidates "$cand" --out "$ROOT/selection.json" | tee "$ROOT/selection.md"
  python3 -c "import json,sys; d=json.load(open('$ROOT/selection.json')); open('$ROOT/selected_tasks.json','w').write(json.dumps(d['selected'])); sys.exit(0 if d['sufficient'] else 3)" \
    || { echo "GATE FAIL: <2 overfit-band tasks. Stopping (honest null of selection)."; exit 3; }
fi

echo "=== PHASE 2: warm_dumpall vs cold on selected tasks (N=$TEST_REPS, t=$TEST_T, --s-val $VAL_SEEDS) ==="
if [ "$DRY" = 1 ]; then
  echo "[dry] group selected by suite; per suite: env -u ANTHROPIC_API_KEY python3 $PAR --root $ROOT --suite <suite> --tasks <ids> --arms warm_dumpall,cold --reps $TEST_REPS --t $TEST_T --s-val $VAL_SEEDS --library $LIB --no-analyze"
else
  # group selected tasks by suite (spatial_* vs 10_*) and run per suite
  sel=$(cat "$ROOT/selected_tasks.json")
  for suite in libero_spatial libero_10; do
    pfx=$([ "$suite" = libero_spatial ] && echo spatial || echo 10)
    ids=$(python3 -c "import json,sys; pfx='$pfx'; print(','.join(t.split('_',1)[1] for t in json.load(open('$ROOT/selected_tasks.json')) if t.startswith(pfx+'_')))")
    [ -z "$ids" ] && continue
    # jobs=2 (the subscription rate-limits above ~2 concurrent claude -p); retry on the
    # parallel runner's circuit breaker (rc=3) with a cooldown so a burst self-heals.
    tries=0
    while true; do
      $BILLENV python3 "$PAR" --root "$ROOT" --suite "$suite" \
        --tasks "$ids" --arms warm_dumpall,cold --reps "$TEST_REPS" --t "$TEST_T" \
        --s-val "$VAL_SEEDS" --library "$LIB" --no-analyze --jobs "$JOBS"
      rc=$?
      if [ "$rc" -eq 3 ] && [ "$tries" -lt 8 ]; then
        tries=$((tries + 1)); echo "[wrapper] circuit breaker on $suite; cooldown 300s, resume ($tries/8)"; sleep 300; continue
      fi
      break
    done
  done
fi

echo "=== PHASE 3: analyze (primary metric = val, alpha=0.05) ==="
if [ "$DRY" = 1 ]; then
  echo "[dry] per suite: python3 $ANALYZE --root $ROOT --heldout <ids> --prefix <pfx> --metric val --alpha 0.05"
else
  for suite in libero_spatial libero_10; do
    pfx=$([ "$suite" = libero_spatial ] && echo spatial || echo 10)
    ids=$(python3 -c "import json; pfx='$pfx'; print(','.join(t.split('_',1)[1] for t in json.load(open('$ROOT/selected_tasks.json')) if t.startswith(pfx+'_')))")
    [ -z "$ids" ] && continue
    echo "--- suite $suite tasks $ids ---"
    python3 "$ANALYZE" --root "$ROOT" --heldout "$ids" --prefix "$pfx" --metric val --alpha 0.05
  done
fi
echo "=== VAL-CONFIRMATORY DONE root=$ROOT ==="
