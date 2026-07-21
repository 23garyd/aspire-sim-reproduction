# B601 Milestone 3d — real ASPIRE repair loop (capstone) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Prove a FAILING cube-lift baseline drives the coordinator's Stage-1 trace-guided repair loop to `validated` on `RealCubeLiftEnv` — deterministically in CI (scripted `FakeActor` + the real capx engine), with the live LLM run documented for on-bench.

**Architecture:** No `aspire/` changes — the coordinator→actor→engine→trace pipeline is reused verbatim. Add a failing baseline (grasps in the air) whose failure is trace-diagnosable, then drive the real pipeline in-process: `TaskPipeline` + `AuditedEngine(CapxEngine(b601_execute --config-path cube_lift_fake.json))` + a scripted `FakeActor` pointing at the correct M3c fix. A failing baseline falls below theta → Stage-1 runs the fix → validated.

**Tech Stack:** Python 3, stdlib, pytest. Reuses `aspire/` (coordinator/actor/engine/schemas) + M3c (`RealCubeLiftEnv`, `b601_execute`, `cube_lift_fake.json`, `baseline_lift.py`).

## Global Constraints

- **No `aspire/` changes.** The coordinator, actor, engine, and trace pipeline are reused verbatim; M3d is a failing baseline + tests + an on-bench config template only.
- **No new `robot_b601/` code.** M3a–c cover perception/motion/task; M3d adds no module.
- **Config is JSON** (`cube_lift_fake.json` from M3c drives the CI test; `cube_lift_real.json` is a committed on-bench template).
- The failing baseline and both configs live in `runs/2026-07-21-b601-real-cube-lift/` beside M3c's `baseline_lift.py` and `cube_lift_fake.json`.
- **CI test isolates Stage-1:** `RunConfig(t=0, ...)` so no evosearch fallback runs (evosearch is tested separately in `aspire/`).
- The failing baseline and the fix must pass the mechanical audit wall (`AuditedEngine` audits every program) — they only call the task primitives (`get_cube_pose`/`move_to_pose`/`open_gripper`/`close_gripper`), which is audit-safe.
- **Test command (REQUIRED flag):** `python3 -m pytest <path> -q -p no:anyio`. Run the full suite before each commit; the current baseline is 296 passing and must not regress.
- **Work from** `/home/demo/aspire_robot_engine` on branch `aspire_original_sim`.

---

### Task 1: The failing baseline + its "fails, and is trace-diagnosable" test

**Files:**
- Create: `runs/2026-07-21-b601-real-cube-lift/baseline_grasp_air.py`
- Test: `tests/b601/test_baseline_grasp_air.py`

**Interfaces:**
- Consumes: M3c `scripts/b601_execute.py`, `runs/2026-07-21-b601-real-cube-lift/cube_lift_fake.json` (RealCubeLiftEnv, fake backend). The task primitive namespace is `get_cube_pose`, `move_to_pose`, `open_gripper`, `close_gripper`, `set_gripper`.
- Produces: `baseline_grasp_air.py` — a program that scores 0 on the fake-backed `RealCubeLiftEnv` and whose traces show `grasped=False`.

- [ ] **Step 1: Write the failing test**

Create `tests/b601/test_baseline_grasp_air.py`:

```python
import json
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
BASE = REPO / "runs" / "2026-07-21-b601-real-cube-lift"
CFG = BASE / "cube_lift_fake.json"
FAILING = BASE / "baseline_grasp_air.py"


def test_grasp_air_baseline_scores_zero(tmp_path):
    out = tmp_path / "out"
    proc = subprocess.run(
        [sys.executable, "scripts/b601_execute.py", "--program", str(FAILING),
         "--seeds", "0,1,2", "--out-dir", str(out), "--config-path", str(CFG)],
        capture_output=True, text=True, cwd=REPO)
    assert proc.returncode == 0, proc.stderr
    result = json.loads((out / "result.json").read_text())
    assert result["score"] == 0.0                    # closes above the cube -> never lifts


def test_grasp_air_failure_is_trace_diagnosable(tmp_path):
    out = tmp_path / "out2"
    subprocess.run(
        [sys.executable, "scripts/b601_execute.py", "--program", str(FAILING),
         "--seeds", "0", "--out-dir", str(out), "--config-path", str(CFG)],
        capture_output=True, text=True, cwd=REPO, check=True)
    traces = json.loads((out / "result.json").read_text())["traces"]
    # the failure cause is legible in the trace text (what a real LLM would read):
    # the gripper closed but grasped nothing.
    assert any(t["function"] == "set_gripper" and "grasped=False" in t["result_summary"]
               for t in traces)
    # and the arm did perceive the cube first (so the bug is 'wrong height', not 'no perception')
    assert any(t["function"] == "get_cube_pose" for t in traces)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/b601/test_baseline_grasp_air.py -q -p no:anyio`
Expected: FAIL — `baseline_grasp_air.py` does not exist (b601_execute can't read the program → non-zero exit / assertion fails).

- [ ] **Step 3: Write the failing baseline**

Create `runs/2026-07-21-b601-real-cube-lift/baseline_grasp_air.py`:

```python
# FAILING B601 cube-lift baseline: closes the gripper at the APPROACH pose, above the
# cube, without ever descending to it -- so it grasps air and lifts nothing. The bug the
# ASPIRE repair actor must fix (add the descend to cube.z before closing).
c = get_cube_pose()
open_gripper()
move_to_pose(c.x, c.y, c.z + 0.10)     # approach ABOVE the cube
close_gripper()                         # BUG: grasps air -- never descended to c.z
move_to_pose(c.x, c.y, c.z + 0.15)      # "lifts" nothing
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m pytest tests/b601/test_baseline_grasp_air.py -q -p no:anyio`
Expected: PASS (2 tests). On the fake backend the EE closes at z=cube.z+0.10 (0.12), 10 cm above the cube at 0.02 — distance 0.10 > `grasp_tol` 0.03 → no stall → gripper fully closes → `grasped=False` → score 0; the `set_gripper` trace carries `grasped=False`.

- [ ] **Step 5: Commit**

```bash
git add runs/2026-07-21-b601-real-cube-lift/baseline_grasp_air.py tests/b601/test_baseline_grasp_air.py
git commit -m "feat(b601): failing grasp-in-air cube-lift baseline (M3d) — scores 0, trace-diagnosable"
```

---

### Task 2: The deterministic repair-loop test + the on-bench real config template

**Files:**
- Create: `runs/2026-07-21-b601-real-cube-lift/cube_lift_real.json`
- Test: `tests/b601/test_repair_loop.py`

**Interfaces:**
- Consumes: `aspire.coordinator.TaskPipeline(task_dir, engine, actor, judge, library, cfg)`; `aspire.engines.{AuditedEngine, CapxEngine}` (`CapxEngine(cmd_prefix: list, out_root: Path)`, `AuditedEngine(inner)`); `aspire.actors.{FakeActor, FakeJudge}` (`FakeActor(reports=[...], extraction_reports=[...])`, `FakeJudge([bool,...])`); `aspire.schemas.{ActorReport, ProposedSkill}` (`ActorReport(outcome, diagnosis, code_path, proposed_skills=())`; `ProposedSkill(name, category, failure_signature, when_to_apply, strategy, code_sketch)`); `aspire.config.RunConfig(k, t, theta, debug_rounds, s_dbg, s_val)`; `aspire.skill_library.SkillLibrary(path)`; `TaskResult(stage_reached, dbg_score, val_score, ...)`. The coordinator reads `task_dir/<report.code_path>` and executes it as the fix.
- Produces: proof that a failing baseline drives Stage-1 repair to `validated`; a committed `cube_lift_real.json` template for the on-bench run.

- [ ] **Step 1: Write the failing test**

First read `tests/aspire/test_coordinator.py::test_debug_then_validate_and_admit_skill` — this test mirrors its scaffolding (scripted `FakeActor` reports + `extraction_reports` + `FakeJudge([True])`, with `task_dir/fix_code.py` pre-written), swapping the `FakeEngine` for the real `AuditedEngine(CapxEngine(b601_execute))` so the scores come from actually executing on `RealCubeLiftEnv`.

Create `tests/b601/test_repair_loop.py`:

```python
import sys
from pathlib import Path

from aspire.actors import FakeActor, FakeJudge
from aspire.config import RunConfig
from aspire.coordinator import TaskPipeline
from aspire.engines import AuditedEngine, CapxEngine
from aspire.schemas import ActorReport, ProposedSkill
from aspire.skill_library import SkillLibrary

REPO = Path(__file__).resolve().parents[2]
BASE = REPO / "runs" / "2026-07-21-b601-real-cube-lift"
FAILING = (BASE / "baseline_grasp_air.py").read_text()
CORRECT = (BASE / "baseline_lift.py").read_text()          # M3c's correct lift = the "fix"


def _fix_report():
    return ActorReport(
        outcome="success",
        diagnosis="gripper closed 10cm above the cube; descend to cube.z before closing",
        code_path="fix_code.py",
        proposed_skills=(ProposedSkill(
            name="descend-before-grasp", category="manipulation",
            failure_signature="GRASP_MISS", when_to_apply="cube perceived but not grasped",
            strategy="move_to_pose to the cube's z, then close_gripper, then lift",
            code_sketch="move_to_pose(c.x,c.y,c.z); close_gripper()"),))


def test_failing_baseline_repaired_to_validated(tmp_path):
    task = tmp_path / "robosuite" / "cube_lift"
    task.mkdir(parents=True)
    (task / "code.py").write_text(FAILING)             # Stage-0: grasps air -> score 0 < theta
    (task / "fix_code.py").write_text(CORRECT)         # the actor's repair: the correct lift

    cmd = [sys.executable, str(REPO / "scripts" / "b601_execute.py"),
           "--config-path", str(BASE / "cube_lift_fake.json")]
    engine = AuditedEngine(CapxEngine(cmd, out_root=tmp_path / "exec"))
    actor = FakeActor(
        reports=[_fix_report()],
        extraction_reports=[ActorReport(outcome="success", diagnosis="d",
                                        code_path="fix_code.py")])
    cfg = RunConfig(k=2, t=0, theta=0.5, debug_rounds=1, s_dbg=[0, 1], s_val=[100, 101])
    lib = SkillLibrary(tmp_path / "lib")

    result = TaskPipeline(task, engine, actor, FakeJudge([True]), lib, cfg).run()

    # The FAILING baseline fell below theta and DROVE the repair path (unlike M3c's passing
    # baseline, which skipped the actor entirely):
    assert actor.debug_calls != []
    # The fix lifted -> reached held-out validation with a perfect score, no LLM/hardware:
    assert result.stage_reached == "validated"
    assert result.dbg_score == 1.0 and result.val_score == 1.0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/b601/test_repair_loop.py -q -p no:anyio`
Expected: collection error / no tests (the file does not exist yet). NOTE: this task adds
NO production code — it is an integration test over the existing `aspire/` pipeline + the
M3c wiring, so once the test file is written it is expected to PASS immediately (there is
no red→green implementation step). The honest "red" state is simply the absent test file.
Before writing it, sanity-check that Task 1's `baseline_grasp_air.py` and M3c's
`baseline_lift.py` + `cube_lift_fake.json` all exist (the test reads them).

- [ ] **Step 3: Add the on-bench real config template**

Create `runs/2026-07-21-b601-real-cube-lift/cube_lift_real.json` (the on-bench operator finalizes the measured values; committed as a starting point):

```json
{
  "backend": "real",
  "lift_threshold": 0.10,
  "grasp_tol": 0.03,
  "min_object_open": 0.01,
  "closed_ref": 0.0,
  "grip_lo": 0.0,
  "grip_hi": 0.08,
  "marker_size": 0.03,
  "base_frame": "base_link",
  "gripper_frame": "tool0",
  "extrinsic": "robot_b601/hand_eye.json",
  "_note": "on-bench: finalize grip_lo/grip_hi + min_object_open (object width) + marker_size from measurement; confirm base_frame/gripper_frame against rebotarm_bringup URDF; hand_eye.json from M3b calibration."
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m pytest tests/b601/test_repair_loop.py -q -p no:anyio`
Expected: PASS (1 test) — the failing baseline scores 0 on Stage-0, the scripted actor's `fix_code.py` scores 1.0 on Stage-1 (≥ theta 0.5), Stage-2 validation scores 1.0 → `validated`; `actor.debug_calls` is non-empty (Stage-1 ran).

- [ ] **Step 5: Commit**

```bash
git add tests/b601/test_repair_loop.py runs/2026-07-21-b601-real-cube-lift/cube_lift_real.json
git commit -m "test(b601): failing baseline -> Stage-1 repair -> validated on RealCubeLiftEnv (M3d) + real config template"
```

---

### Task 3: Full-suite gate + on-bench live-capstone note + push

**Files:** none (verification only)

- [ ] **Step 1: Run the complete suite**

Run: `python3 -m pytest tests/ -q -p no:anyio`
Expected: PASS — prior 296 + the 3 new M3d tests (299); no `aspire/` or M3a–c regression.

- [ ] **Step 2: Confirm the repair path is genuinely exercised (not a Fake fallback)**

Run: `python3 -m pytest tests/b601/test_repair_loop.py tests/b601/test_baseline_grasp_air.py -q -p no:anyio -v`
Expected: all pass; the repair-loop test drives the real `CapxEngine` (b601_execute → RealCubeLiftEnv) with `--config-path cube_lift_fake.json` (not `--selftest`), and asserts `actor.debug_calls != []` (Stage-1 ran).

- [ ] **Step 3: Push**

```bash
git push aspire_demo aspire_original_sim
```

- [ ] **Step 4: On-bench live capstone (LIVE — hardware + credits, after merge, not a unit test)**

Record for the operator (do NOT run in CI):
1. Complete M3b calibration (`hand_eye.json`) and finalize M3c `RealMotionBackend.connect()` against the vendor MoveIt2/IK + gripper controller + TF frames; finalize `runs/2026-07-21-b601-real-cube-lift/cube_lift_real.json` measured values.
2. `ros2 launch rebotarm_bringup …` + MoveIt2 + `ros2 run rebotarm_monitor_ros2 …`; e-stop in reach; workspace clear; D405 connected; place the marked cube.
3. Put `baseline_grasp_air.py` as the task's `code.py` (a task dir `<t>/robosuite/cube_lift/code.py`), then run:
   ```bash
   python -m aspire.run --task-dir <t> --engine capx \
     --capx-cmd "python scripts/b601_execute.py --config-path runs/2026-07-21-b601-real-cube-lift/cube_lift_real.json" \
     --library <lib> --s-dbg 0 --s-val 1
   ```
4. The coordinator runs the failing baseline on the real arm (grasps air → `dbg_score < theta`) → Stage-1: `ClaudeCodeActor` reads the real failing traces, writes `fix_code.py` (adds the descend) → the engine re-runs it on the arm → grasps + lifts → Stage-2 → `validated`. The full ASPIRE trace-guided repair loop closing on real hardware — the credit-gated capstone, reported honestly like the sim reproduction runs.

---

## Self-review notes (spec coverage)

- Failing grasp-in-air baseline (scores 0, trace-diagnosable) → Task 1.
- Deterministic CI repair-loop proof (failing baseline → Stage-1 actor → fix → `validated`, no LLM/hardware; asserts Stage-1 actually ran) → Task 2.
- On-bench `cube_lift_real.json` template → Task 2.
- The live+credits capstone procedure (real `ClaudeCodeActor` on the arm) → Task 3 note.
- No `aspire/` changes; the coordinator/actor/engine/trace pipeline reused verbatim; CI drives it in-process with a scripted `FakeActor` + the real `CapxEngine` → Global Constraints + Task 2.
- Stage-1 isolation (`t=0`, no evosearch) → Task 2 `RunConfig`.
- 296 stay green → Task 3 gate.
- **On-bench-finalized (honest boundary):** vendor IK interface + TF frames + measured gripper/object/marker values (from M3c) → Task 2 template `_note` + Task 3 note.
