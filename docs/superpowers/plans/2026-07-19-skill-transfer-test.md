# Skill-transfer Test Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the harness for the skill-transfer test — seed a `two_arm_lift` run's library with only the handover-provenance skills and measure held-out repair vs an empty library (arm S vs arm E) — reusing the existing engine, coordinator, CLI, and analysis.

**Architecture:** No `aspire/` package changes. Three artifacts: (1) a committed 2-skill seed-library fixture (handover-provenance only), (2) a thin analysis wrapper reusing `scripts/analyze_ablation.py`'s `mann_whitney_u`/`_arm_scores` for arms S/E, (3) an A/B campaign launcher that seeds arm S's per-repeat library from the fixture and leaves arm E empty — the single manipulated variable being library contents. Both arms run identical config (`--t 0`, `--s-val 100-119`, pristine baseline).

**Tech Stack:** Python 3 (stdlib-only for the analysis script), pytest (`-p no:anyio` on simhost), bash launcher, the existing `aspire.skill_library` loader.

## Global Constraints

- The seed library must contain ONLY the two `two_arm_handover`-provenance skills; the two `two_arm_lift`-provenance skills must be EXCLUDED (else it is not a cross-task transfer).
- Arms differ in ONE thing only: arm S seeds each repeat's library from the fixture; arm E leaves it empty. Everything else identical — same baseline `code.py` (md5 `0ada19ef`), `s_dbg [0,1,2]`, `s_val 100-119`, `theta 1.0`, `debug_rounds 2`, opus repair, `--t 0` (evosearch off). Any other cross-arm difference is a Critical confound.
- Per-repeat isolation exactly like `scripts/lift_repeats.sh`/`traces_ablation.sh`: fresh task dir seeded with the pristine baseline, **own fresh library copy per repeat** (admission during a repeat must not leak into the next), own exec out-root.
- `scripts/analyze_ablation.py` is REUSED, not reimplemented — import `mann_whitney_u` and `_arm_scores` from it.
- Do NOT launch any campaign in this plan (no API spend). Verification is fixture-load tests, unit tests, and bash syntax/structure checks only.
- Tests run with `python3 -m pytest <path> -q -p no:anyio` (the `-p no:anyio` flag is required on simhost). Full suite is currently 196 passed.
- `SkillLibrary` on-disk format: one markdown file per skill at `root/<category>/<slug>.md`, plus `index.md` at root; `load_all()` globs `root/*/*.md`.

---

### Task 1: Committed seed-library fixture (handover-provenance only)

**Files:**
- Create: `runs/2026-07-19-skill-transfer/seed_library/multi-effector-geometry/allocate-shared-object-span-between-two-effectors.md`
- Create: `runs/2026-07-19-skill-transfer/seed_library/forbidden-api-workaround/keyframe-geometry-from-trace-images.md`
- Create: `runs/2026-07-19-skill-transfer/seed_library/index.md` (generated)
- Test: `tests/aspire/test_seed_library_fixture.py`

**Interfaces:**
- Produces: a committed `SkillLibrary`-format directory at `runs/2026-07-19-skill-transfer/seed_library/` that `SkillLibrary(...).load_all()` reads as exactly the 2 handover skills.

- [ ] **Step 1: Write the failing test**

Create `tests/aspire/test_seed_library_fixture.py`:

```python
from aspire.skill_library import SkillLibrary

FIXTURE = "runs/2026-07-19-skill-transfer/seed_library"

def test_seed_library_is_exactly_the_two_handover_skills():
    skills = SkillLibrary(FIXTURE).load_all()
    assert len(skills) == 2
    assert sorted(s.name for s in skills) == [
        "allocate-shared-object-span-between-two-effectors",
        "keyframe-geometry-from-trace-images",
    ]
    for s in skills:
        assert "two_arm_handover" in s.provenance      # genuine cross-task seed
        assert "two_arm_lift" not in s.provenance       # lift-provenance excluded
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/aspire/test_seed_library_fixture.py -q -p no:anyio`
Expected: FAIL — fixture dir does not exist yet (`load_all()` returns `[]`, first assert fails).

- [ ] **Step 3: Build the fixture**

Copy the two provenance-verified handover skills from the M3 library into the fixture, then regenerate `index.md` via the loader. Run from the repo root:

```bash
mkdir -p runs/2026-07-19-skill-transfer/seed_library/multi-effector-geometry \
         runs/2026-07-19-skill-transfer/seed_library/forbidden-api-workaround
cp /home/demo/aspire_runs/m3/skill_library/multi-effector-geometry/allocate-shared-object-span-between-two-effectors.md \
   runs/2026-07-19-skill-transfer/seed_library/multi-effector-geometry/
cp /home/demo/aspire_runs/m3/skill_library/forbidden-api-workaround/keyframe-geometry-from-trace-images.md \
   runs/2026-07-19-skill-transfer/seed_library/forbidden-api-workaround/
python3 - <<'PY'
from pathlib import Path
from aspire.skill_library import SkillLibrary, parse_skill
root = Path("runs/2026-07-19-skill-transfer/seed_library")
lib = SkillLibrary(root)
for p in sorted(root.glob("*/*.md")):          # re-add each: idempotent rewrite + regenerates index.md
    lib.add(parse_skill(p.read_text()))
print("skills:", [s.name for s in lib.load_all()])
PY
```

Expected stdout: `skills: ['allocate-shared-object-span-between-two-effectors', 'keyframe-geometry-from-trace-images']` (order may vary).

Verify the lift-provenance skill was NOT copied:
```bash
grep -rl "two_arm_lift" runs/2026-07-19-skill-transfer/seed_library/ || echo "NO lift-provenance present (correct)"
```
Expected: `NO lift-provenance present (correct)`

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m pytest tests/aspire/test_seed_library_fixture.py -q -p no:anyio`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add runs/2026-07-19-skill-transfer/seed_library tests/aspire/test_seed_library_fixture.py
git commit -m "fixture: 2-skill handover-provenance seed library for the skill-transfer test"
```

---

### Task 2: Analysis wrapper for arms S/E

**Files:**
- Create: `scripts/analyze_skill_transfer.py`
- Test: `tests/aspire/test_analyze_skill_transfer.py`

**Interfaces:**
- Consumes: `mann_whitney_u`, `_arm_scores` from `scripts/analyze_ablation.py` (already package-importable — `scripts/__init__.py` exists).
- Produces: `main(argv=None) -> int` reading `<root>/S` and `<root>/E` arm dirs; prints per-arm mean/median/P(val>=0.80) and Mann-Whitney U(S vs E), z; returns 1 if either arm has no scores, else 0.

- [ ] **Step 1: Write the failing test**

Create `tests/aspire/test_analyze_skill_transfer.py`:

```python
import json

def _done(dirpath, score):
    dirpath.mkdir(parents=True)
    (dirpath / "VALIDATION_DONE").write_text(
        json.dumps({"program": "x", "score": score, "dbg_score": 1.0}))

def test_reads_S_and_E_arms_and_returns_zero(tmp_path):
    for arm, scores in [("S", [0.9, 0.9, 1.0]), ("E", [0.1, 0.2, 0.3])]:
        for i, s in enumerate(scores, 1):
            _done(tmp_path / arm / f"rep_{i}" / "robosuite" / "two_arm_lift", s)
    from scripts.analyze_skill_transfer import main
    assert main([str(tmp_path)]) == 0

def test_missing_arm_returns_one(tmp_path):
    _done(tmp_path / "S" / "rep_1" / "robosuite" / "two_arm_lift", 0.9)
    from scripts.analyze_skill_transfer import main
    assert main([str(tmp_path)]) == 1        # E arm empty -> non-zero
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/aspire/test_analyze_skill_transfer.py -q -p no:anyio`
Expected: FAIL — `ModuleNotFoundError: scripts.analyze_skill_transfer`.

- [ ] **Step 3: Write the wrapper**

Create `scripts/analyze_skill_transfer.py`:

```python
#!/usr/bin/env python3
"""Pre-registered analysis for the skill-transfer test (arms S=seeded, E=empty).
Reuses the ablation's Mann-Whitney U and per-arm score reader — the statistic is
NOT reimplemented. Reports mean/median, P(val>=0.80), and U(S vs E) with z.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))   # repo root on path
from scripts.analyze_ablation import _arm_scores, mann_whitney_u


def main(argv=None):
    argv = argv if argv is not None else sys.argv[1:]
    root = Path(argv[0]) if argv else Path.home() / "aspire_runs" / "skill_transfer"
    s = _arm_scores(root / "S")
    e = _arm_scores(root / "E")
    if not s or not e:
        print(f"missing scores (S={len(s)}, E={len(e)}) under {root}")
        return 1
    u, z = mann_whitney_u(s, e)

    def summ(label, xs):
        xs = sorted(xs)
        mean = sum(xs) / len(xs)
        med = xs[len(xs) // 2] if len(xs) % 2 else (xs[len(xs)//2 - 1] + xs[len(xs)//2]) / 2
        strong = sum(1 for v in xs if v >= 0.80) / len(xs)
        print(f"{label}: n={len(xs)} mean={mean:.3f} median={med:.3f} "
              f"P(val>=0.80)={strong:.2f} scores={xs}")

    summ("S (seeded)", s)
    summ("E (empty)", e)
    print(f"Mann-Whitney U(S vs E)={u:.1f}  z={z:.3f}  "
          f"(z>0 => seeded arm ranks higher)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m pytest tests/aspire/test_analyze_skill_transfer.py -q -p no:anyio`
Expected: PASS (both)

- [ ] **Step 5: Commit**

```bash
git add scripts/analyze_skill_transfer.py tests/aspire/test_analyze_skill_transfer.py
git commit -m "feat(scripts): skill-transfer analysis wrapper (reuses ablation Mann-Whitney)"
```

---

### Task 3: A/B campaign launcher

**Files:**
- Create: `scripts/skill_transfer.sh`
- Create: `~/start_skill_transfer.sh` (home dir, NOT committed)

**Interfaces:**
- Produces: a launcher running N isolated `two_arm_lift` repeats for arm S (per-repeat library seeded from the committed fixture) and arm E (empty library), both `--t 0 --s-val 100-119`, into `~/aspire_runs/skill_transfer/{S,E}/rep_NN/`. Idempotent/resumable (skip a repeat whose task dir has `VALIDATION_DONE`).

- [ ] **Step 1: Write the launcher**

Create `scripts/skill_transfer.sh` (model on `scripts/traces_ablation.sh`; the ONLY per-arm difference is seeding the library):

```bash
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
SEED="$REPO/runs/2026-07-19-skill-transfer/seed_library"
BASELINE=$HOME/aspire_runs/m1_baseline/claude-opus-4-8/two_arm_lift/trial_01_sandboxrc_0_reward_0.026_taskcompleted_0/code.py
CFG=/home/demo/cap-x/env_configs/two_arm_lift/franka_robosuite_two_arm_lift_privileged.yaml
CAPX_CMD="/home/demo/cap-x/.venv/bin/python $REPO/scripts/capx_execute.py --workdir /home/demo/cap-x --config-path $CFG"

[ -f "$BASELINE" ] || { echo "FATAL: baseline missing: $BASELINE"; exit 1; }
[ -d "$SEED" ]    || { echo "FATAL: seed library missing: $SEED"; exit 1; }
mkdir -p "$ROOT"

run_arm() {           # $1 = arm label (S|E), $2 = seed dir ("" = empty library)
  local arm="$1" seed="$2"
  for i in $(seq -w 1 "$N"); do
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
```

Create `~/start_skill_transfer.sh` (mirror `~/start_traces_ablation.sh` exactly, swapping names): detached `setsid`, pidfile `/tmp/skill_transfer.pid`, log `~/aspire_runs/skill_transfer/campaign.log`, `disown`, `kill -0` liveness echo:

```bash
#!/bin/bash
# Detached launcher for the skill-transfer A/B campaign.
# Liveness: kill -0 $(cat /tmp/skill_transfer.pid)
# Log:      ~/aspire_runs/skill_transfer/campaign.log
set -u
mkdir -p ~/aspire_runs/skill_transfer
setsid bash -c 'echo $$ > /tmp/skill_transfer.pid; exec bash ~/aspire_robot_engine/scripts/skill_transfer.sh' \
  < /dev/null >> ~/aspire_runs/skill_transfer/campaign.log 2>&1 &
disown
sleep 2
if kill -0 "$(cat /tmp/skill_transfer.pid 2>/dev/null)" 2>/dev/null; then
  echo "SKILL_TRANSFER_UP pid=$(cat /tmp/skill_transfer.pid)"
else
  echo "SKILL_TRANSFER_FAILED"; tail -5 ~/aspire_runs/skill_transfer/campaign.log; exit 1
fi
```

- [ ] **Step 2: Syntax-check both scripts**

Run: `bash -n scripts/skill_transfer.sh && bash -n ~/start_skill_transfer.sh && echo OK`
Expected: `OK`

- [ ] **Step 3: Structural checks (no spend)**

Confirm the single-manipulated-variable property and that arm S seeds while arm E does not:
```bash
grep -q 'run_arm S "$SEED"' scripts/skill_transfer.sh \
  && grep -q 'run_arm E ""' scripts/skill_transfer.sh \
  && grep -q -- '--t 0' scripts/skill_transfer.sh \
  && grep -q -- '--s-val 100-119' scripts/skill_transfer.sh \
  && echo WIRED
```
Expected: `WIRED`

Confirm the aspire.run invocation is shared (one line, both arms use it — so nothing but the library differs):
```bash
test "$(grep -c 'python3 -m aspire.run' scripts/skill_transfer.sh)" = "1" && echo "single shared invocation"
```
Expected: `single shared invocation`

- [ ] **Step 4: Commit (repo script only)**

```bash
chmod +x scripts/skill_transfer.sh
git add scripts/skill_transfer.sh
git commit -m "scripts: skill-transfer A/B campaign launcher (seeded vs empty library, --t 0)"
```

---

### Task 4: Full-suite regression gate + push

**Files:** none (verification only)

- [ ] **Step 1: Run the complete suite**

Run: `python3 -m pytest tests/ -q -p no:anyio`
Expected: PASS — all tests (prior 196 + the ~4 new: 1 fixture test + 2 analysis tests).

- [ ] **Step 2: Confirm the fixture loads as a real 2-skill library end-to-end**

Run:
```bash
python3 -c "from aspire.skill_library import SkillLibrary; print([s.name for s in SkillLibrary('runs/2026-07-19-skill-transfer/seed_library').load_all()])"
```
Expected: the two handover skill names, nothing else.

- [ ] **Step 3: Push**

```bash
git push aspire_demo aspire_original_sim
```

---

## Self-review notes (spec coverage)

- Direction handover→lift, lift-provenance excluded → Task 1 (fixture + test asserting provenance is handover-only).
- Single manipulated variable = library contents → Task 3 (one shared `aspire.run` invocation; only arm S runs the `cp` seed step; structural checks enforce it).
- `t=0`, `s-val 100-119`, pristine baseline, per-repeat isolation, fresh library copy → Task 3 launcher (mirrors lift_repeats/traces_ablation).
- Reuse Mann-Whitney + effect sizes, arms S/E → Task 2 (imports from analyze_ablation, no reimplementation).
- N=8/arm staged, resumable → operational (`N` env var; VALIDATION_DONE skip), same as the ablation.
- No `aspire/` package change, no spend in this plan → all tasks are fixtures/scripts/tests + syntax/structure checks.
- Seeded skills reach the actor via `load_all()` fallback on silent lift failure → guaranteed by existing `task_context.relevant_skills` (unchanged); no task needed, noted in the spec.
```
