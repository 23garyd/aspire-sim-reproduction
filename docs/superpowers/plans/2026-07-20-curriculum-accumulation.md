# Curriculum-accumulation Experiment Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the harness to reproduce ASPIRE layer 2 in curriculum mode — accumulate a shared skill library by running the 4 non-lift tasks in sequence, then measure warm (accumulated library) vs cold (empty) held-out repair on two_arm_lift — reusing the existing engine, the skill-transfer launcher, and the skill-transfer analysis.

**Architecture:** No `aspire/` package changes. Phase 1 accumulates via a bash loop of single-task `aspire.run` calls all sharing ONE `--library` dir (not `--tasks-root`, which can't do per-task configs). Phase 2 reuses `scripts/skill_transfer.sh` (arm S=warm seeds the accumulated library, arm E=cold empty) by overriding its `SEED`/`ROOT`/`N` env vars — requiring only a one-line change to make `SEED` overridable. Analysis reuses `scripts/analyze_skill_transfer.py` unchanged (arms S/E).

**Tech Stack:** bash launchers, the existing `python -m aspire.run` CLI + `capx` engine, pytest (`-p no:anyio` on simhost), the `aspire.skill_library` loader.

## Global Constraints

- Lift is EXCLUDED from the accumulation set — no measured-task self-leakage (any warm benefit must come from *other* tasks' skills). The accumulation set is exactly: `cube_lifting`, `cube_stack`, `nut_assembly`, `two_arm_handover`.
- Accumulation shares ONE `--library` dir across the 4 single-task runs so skills accumulate; each run has its OWN `--config-path` (per-task env YAML).
- All runs use `--t 0` (evosearch off), `--s-val 100-119`, pristine baselines; the lift measurement uses the pristine lift baseline `code.py` md5 `0ada19ef` (via the reused skill_transfer.sh).
- Phase-2 arms differ in ONE thing only: arm S copies the accumulated library into each repeat, arm E leaves it empty. This is enforced by reusing `skill_transfer.sh` (already reviewed for that property) with `SEED` pointed at the accumulated library.
- Committed fixtures must be pristine SOURCES; launchers copy them into `~/aspire_runs/...` working dirs and never mutate the committed copies.
- Do NOT launch any campaign in this plan (no API spend). Verification is fixture tests + bash syntax/structure checks only.
- Tests run with `python3 -m pytest <path> -q -p no:anyio` (required on simhost). Full suite currently 199 passed.

---

### Task 1: Curriculum baseline fixtures (4 non-lift tasks)

**Files:**
- Create: `runs/2026-07-20-curriculum/tasks/robosuite/cube_lifting/code.py`
- Create: `runs/2026-07-20-curriculum/tasks/robosuite/cube_stack/code.py`
- Create: `runs/2026-07-20-curriculum/tasks/robosuite/nut_assembly/code.py`
- Create: `runs/2026-07-20-curriculum/tasks/robosuite/two_arm_handover/code.py`
- Test: `tests/aspire/test_curriculum_fixtures.py`

**Interfaces:**
- Produces: committed pristine baseline programs (one per non-lift task) under `runs/2026-07-20-curriculum/tasks/robosuite/<task>/code.py`, copied from the M1 CaP-Agent0 baseline (trial_01 per task).

- [ ] **Step 1: Write the failing test**

Create `tests/aspire/test_curriculum_fixtures.py`:

```python
from pathlib import Path

BASE = Path("runs/2026-07-20-curriculum/tasks/robosuite")
TASKS = ["cube_lifting", "cube_stack", "nut_assembly", "two_arm_handover"]

def test_four_nonlift_baselines_present_and_nonempty():
    for t in TASKS:
        p = BASE / t / "code.py"
        assert p.exists(), f"missing {p}"
        assert p.stat().st_size > 50, f"suspiciously small {p}"

def test_lift_is_excluded_from_accumulation_set():
    # no self-leakage: the measured task must NOT be in the accumulation set
    assert not (BASE / "two_arm_lift").exists()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/aspire/test_curriculum_fixtures.py -q -p no:anyio`
Expected: FAIL — fixture files do not exist yet.

- [ ] **Step 3: Copy the baselines**

From the repo root, copy each task's M1 trial_01 baseline into the fixture:

```bash
mkdir -p runs/2026-07-20-curriculum/tasks/robosuite/{cube_lifting,cube_stack,nut_assembly,two_arm_handover}
M1=/home/demo/aspire_runs/m1_baseline/claude-opus-4-8
cp "$M1/cube_lifting/trial_01_sandboxrc_0_reward_1.000_taskcompleted_1/code.py"      runs/2026-07-20-curriculum/tasks/robosuite/cube_lifting/code.py
cp "$M1/cube_stack/trial_01_sandboxrc_0_reward_1.000_taskcompleted_1/code.py"        runs/2026-07-20-curriculum/tasks/robosuite/cube_stack/code.py
cp "$M1/nut_assembly/trial_01_sandboxrc_0_reward_1.000_taskcompleted_1/code.py"      runs/2026-07-20-curriculum/tasks/robosuite/nut_assembly/code.py
cp "$M1/two_arm_handover/trial_01_sandboxrc_0_reward_0.020_taskcompleted_0/code.py"  runs/2026-07-20-curriculum/tasks/robosuite/two_arm_handover/code.py
```

If any source path is missing (M1 trial dirs are named by their reward), find the right trial_01 dir with:
```bash
ls -d "$M1/<task>/trial_01_"*
```
and copy that dir's `code.py`. Every non-lift task has a `trial_01_*` dir.

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m pytest tests/aspire/test_curriculum_fixtures.py -q -p no:anyio`
Expected: PASS (both tests)

- [ ] **Step 5: Commit**

```bash
git add runs/2026-07-20-curriculum/tasks tests/aspire/test_curriculum_fixtures.py
git commit -m "fixture: 4 non-lift baseline programs for the curriculum-accumulation experiment"
```

---

### Task 2: Make skill_transfer.sh SEED overridable

**Files:**
- Modify: `scripts/skill_transfer.sh:13`

**Interfaces:**
- Produces: `scripts/skill_transfer.sh` with `SEED` env-overridable (default unchanged), so Phase 2 can point arm S at the accumulated library via `SEED=<dir>`.

- [ ] **Step 1: Confirm current line and its default**

Run: `grep -n '^SEED=' scripts/skill_transfer.sh`
Expected: line 13 is `SEED="$REPO/runs/2026-07-19-skill-transfer/seed_library"` (hard-coded).

- [ ] **Step 2: Make it overridable**

Edit `scripts/skill_transfer.sh` line 13, replacing:
```bash
SEED="$REPO/runs/2026-07-19-skill-transfer/seed_library"
```
with:
```bash
SEED="${SEED:-$REPO/runs/2026-07-19-skill-transfer/seed_library}"
```

- [ ] **Step 3: Verify the override idiom (functional) + syntax + no regression**

Run these and check each line's output:
```bash
bash -n scripts/skill_transfer.sh && echo SYNTAX_OK
# default preserved when SEED unset:
REPO=/r bash -c 'SEED="${SEED:-$REPO/runs/2026-07-19-skill-transfer/seed_library}"; echo "$SEED"'
# override honored when SEED set:
SEED=/custom/lib REPO=/r bash -c 'SEED="${SEED:-$REPO/runs/2026-07-19-skill-transfer/seed_library}"; echo "$SEED"'
# skill-transfer wiring still intact:
grep -q 'run_arm S "$SEED"' scripts/skill_transfer.sh && grep -q 'run_arm E ""' scripts/skill_transfer.sh && grep -q -- '--t 0' scripts/skill_transfer.sh && grep -q -- '--s-val 100-119' scripts/skill_transfer.sh && echo WIRED
```
Expected: `SYNTAX_OK`; then `/r/runs/2026-07-19-skill-transfer/seed_library`; then `/custom/lib`; then `WIRED`.

- [ ] **Step 4: Confirm the transfer-test default still resolves to the committed fixture**

Run: `grep -q 'SEED="${SEED:-' scripts/skill_transfer.sh && test -d runs/2026-07-19-skill-transfer/seed_library && echo "default fixture intact"`
Expected: `default fixture intact`

- [ ] **Step 5: Commit**

```bash
git add scripts/skill_transfer.sh
git commit -m "scripts: make skill_transfer.sh SEED env-overridable (reuse for curriculum warm arm)"
```

---

### Task 3: Accumulation launcher (Phase 1)

**Files:**
- Create: `scripts/curriculum_accumulate.sh`

**Interfaces:**
- Produces: a launcher that runs the 4 non-lift tasks as single-task `aspire.run` calls, all sharing one `--library "$ACCUM_LIB"` so skills accumulate; each task uses its own env config. Idempotent (VALIDATION_DONE skip). Prints the final accumulated skill count. `ACCUM_LIB` defaults to `$HOME/aspire_runs/curriculum/accumulated_library`.

- [ ] **Step 1: Write the launcher**

Create `scripts/curriculum_accumulate.sh`:

```bash
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
```

- [ ] **Step 2: Syntax check**

Run: `bash -n scripts/curriculum_accumulate.sh && echo SYNTAX_OK`
Expected: `SYNTAX_OK`

- [ ] **Step 3: Structural checks (no launch, no spend)**

```bash
# exactly the 4 non-lift tasks, lift NOT present:
grep -q 'TASKS=(cube_lifting cube_stack nut_assembly two_arm_handover)' scripts/curriculum_accumulate.sh && echo "4 tasks, lift excluded"
# one shared library across all tasks:
test "$(grep -c -- '--library "$ACCUM_LIB"' scripts/curriculum_accumulate.sh)" = "1" && echo "single shared library"
# per-task config resolved inside the loop:
grep -q 'cfg=$(ls /home/demo/cap-x/env_configs' scripts/curriculum_accumulate.sh && echo "per-task config"
# t=0 and held-out seeds:
grep -q -- '--t 0' scripts/curriculum_accumulate.sh && grep -q -- '--s-val 100-119' scripts/curriculum_accumulate.sh && echo "t0 + heldout"
```
Expected: `4 tasks, lift excluded`, `single shared library`, `per-task config`, `t0 + heldout`.

- [ ] **Step 4: Verify each task's env config actually resolves (read-only, no run)**

```bash
for t in cube_lifting cube_stack nut_assembly two_arm_handover; do
  cfg=$(ls /home/demo/cap-x/env_configs/*/*"$t"*_privileged.yaml 2>/dev/null | head -1)
  echo "$t -> ${cfg:-MISSING}"
done
```
Expected: each task maps to a distinct existing `*_privileged.yaml` (no `MISSING`).

- [ ] **Step 5: Commit**

```bash
chmod +x scripts/curriculum_accumulate.sh
git add scripts/curriculum_accumulate.sh
git commit -m "scripts: curriculum accumulation launcher (4 non-lift tasks, shared library, --t 0)"
```

---

### Task 4: Orchestrator + home launcher + final gate

**Files:**
- Create: `scripts/curriculum.sh`
- Create: `~/start_curriculum.sh` (home dir, NOT committed)

**Interfaces:**
- Consumes: `scripts/curriculum_accumulate.sh` (Phase 1), `scripts/skill_transfer.sh` (Phase 2, via `SEED`/`ROOT`/`N` env overrides), `scripts/analyze_skill_transfer.py` (analysis).
- Produces: `scripts/curriculum.sh` runs Phase 1 then Phase 2 (warm=S seeded from the accumulated library, cold=E empty) into `~/aspire_runs/curriculum/{S,E}/`.

- [ ] **Step 1: Write the orchestrator**

Create `scripts/curriculum.sh`:

```bash
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
```

Create `~/start_curriculum.sh` (mirror `~/start_skill_transfer.sh`; NOT committed), pidfile `/tmp/curriculum.pid`, log `~/aspire_runs/curriculum/campaign.log`:

```bash
#!/bin/bash
# Detached launcher for the curriculum-accumulation experiment.
# Liveness: kill -0 $(cat /tmp/curriculum.pid)
# Log:      ~/aspire_runs/curriculum/campaign.log
set -u
mkdir -p ~/aspire_runs/curriculum
setsid bash -c 'echo $$ > /tmp/curriculum.pid; exec bash ~/aspire_robot_engine/scripts/curriculum.sh' \
  < /dev/null >> ~/aspire_runs/curriculum/campaign.log 2>&1 &
disown
sleep 2
if kill -0 "$(cat /tmp/curriculum.pid 2>/dev/null)" 2>/dev/null; then
  echo "CURRICULUM_UP pid=$(cat /tmp/curriculum.pid)"
else
  echo "CURRICULUM_FAILED"; tail -5 ~/aspire_runs/curriculum/campaign.log; exit 1
fi
```

- [ ] **Step 2: Syntax-check both**

Run: `bash -n scripts/curriculum.sh && bash -n ~/start_curriculum.sh && echo OK`
Expected: `OK`

- [ ] **Step 3: Structural checks (no launch, no spend)**

```bash
# Phase 1 then Phase 2 in order, Phase 2 passes SEED=accumulated lib + ROOT:
grep -q 'bash "$REPO/scripts/curriculum_accumulate.sh"' scripts/curriculum.sh && echo "phase1 wired"
grep -q 'SEED="$ACCUM_LIB" ROOT="$ROOT" N="$N" bash "$REPO/scripts/skill_transfer.sh"' scripts/curriculum.sh && echo "phase2 wired (warm=accumulated lib)"
# analysis reused, arms S/E under the curriculum ROOT:
grep -q 'analyze_skill_transfer.py' scripts/curriculum.sh && echo "analysis reused"
```
Expected: `phase1 wired`, `phase2 wired (warm=accumulated lib)`, `analysis reused`.

- [ ] **Step 4: Full-suite regression gate**

Run: `python3 -m pytest tests/ -q -p no:anyio`
Expected: PASS — prior 199 + the 2 new curriculum-fixture tests (201).

- [ ] **Step 5: Commit + push**

```bash
chmod +x scripts/curriculum.sh
git add scripts/curriculum.sh
git commit -m "scripts: curriculum orchestrator (accumulate -> warm/cold on lift, reuses skill_transfer + analysis)"
git push aspire_demo aspire_original_sim
```

---

## Self-review notes (spec coverage)

- Accumulate 4 non-lift tasks, shared library, lift excluded → Task 1 (fixtures, lift-excluded test) + Task 3 (loop, single shared `--library`, TASKS list without lift).
- No `--tasks-root` (heterogeneous configs) → Task 3 uses single-task runs with per-task `--config-path`.
- Warm vs cold on lift, single manipulated variable → Task 2 (SEED override) + Task 4 (Phase 2 reuses the already-reviewed skill_transfer.sh with SEED=accumulated lib).
- All `--t 0`, `--s-val 100-119`, pristine baselines → Tasks 3 & 4 (skill_transfer.sh already enforces the lift baseline + t0 + seeds).
- Reuse analysis unchanged (arms S/E) → Task 4 (curriculum ROOT has S/E dirs; analyze_skill_transfer reads them).
- N=5 staged, resumable → operational (`N` env var; VALIDATION_DONE skip in both launchers).
- Accumulated-library contents logged for interpretability → Task 3 prints skill count/names; the degenerate <2-skill case is visible there and reported in results.
- No `aspire/` package change, no spend in this plan → all tasks are fixtures/scripts/tests + syntax/structure checks.
```
