# B601 Milestone 3d — the real ASPIRE repair loop on hardware (capstone) — design

_Date: 2026-07-21. Status: SPEC for review. Builds on M3c (`RealCubeLiftEnv`,
`MotionBackend` seam, `b601_execute` capx engine, `cube_lift_fake.json` +
`baseline_lift.py`), M3a/M3b (transport, perception, hand-eye), and the existing
`aspire/` coordinator→actor→engine + trace pipeline (UNCHANGED). Branch
`aspire_original_sim`. Hardware on the bench (B601-RS + D405)._

## Purpose

The credit-gated live capstone that closes the B601 track. A **failing** cube-lift
baseline (grasps in the air) → the coordinator's **Stage-1 trace-guided LLM repair
actor** reads the failing traces → writes a fix → re-run on `RealCubeLiftEnv` →
`validated`. M3c proved a *passing* baseline skips the actor (`dbg_score >= theta`);
M3d proves a *failing* baseline (`dbg_score < theta`) drives the full repair loop
(coordinator → Stage-1 actor → engine re-run → held-out validation) to success on the
real cube-lift.

Everything below the repair loop is already built and CI-proven: perception (M3b),
IK reach + grasp + lift (M3c), the capx engine + the whole ASPIRE pipeline. M3d adds
**no `aspire/` code** — it is a failing baseline + a deterministic CI proof that the
repair wiring closes on `RealCubeLiftEnv`, plus the documented live+credits procedure.

## The seam (why no pipeline changes)

`TaskPipeline.run()` (`aspire/coordinator.py`): Stage-0 runs the baseline on `S_dbg`;
if `dbg_score < theta`, Stage-1 loops `debug_rounds` times, each calling
`report = self.actor.run_debug(task_dir, model=...)`, then `fix = task_dir /
report.code_path`, `r = self.engine.execute(fix, s_dbg)`, adopting the fix if
`r.score > dbg_score`; on reaching theta it proceeds to Stage-2 validation on `S_val`.
The actor is injected (`ClaudeCodeActor` live, `FakeActor` scripted for CI). So the
repair loop is exercised on the real cube-lift by pointing the engine at
`b601_execute` (M3c) and letting a failing baseline fall below theta — with **no
changes to the coordinator, actor, engine, or trace pipeline.**

## Decisions (resolved during brainstorming)

1. **Failure mode: grasps in the air (no descend).** The failing baseline reaches the
   approach pose *above* the cube (`cube.z + 0.10`) and closes the gripper there
   without descending to `cube.z`. A single, cleanly trace-diagnosable bug: the trace
   shows `get_cube_pose cube=(…,0.02)`, `move_to_pose ee=(…,0.12)`,
   `set_gripper grasped=False` — the LLM can read "closed the gripper 10 cm above the
   cube" and add the descend. The fix is the existing M3c `baseline_lift.py`.
2. **CI test drives Stage-1 only** (`t=0`, so no evosearch fallback) to isolate the
   trace-guided repair path. Evosearch is already tested in `aspire/`.
3. **Commit a `cube_lift_real.json` template** (backend:real + documented placeholder
   fields) so the on-bench run has a starting point.
4. **The failing baseline lives beside the M3c baseline** in
   `runs/2026-07-21-b601-real-cube-lift/`.

## Components (files)

- **`runs/2026-07-21-b601-real-cube-lift/baseline_grasp_air.py`** — the FAILING
  baseline (agent program): perceive → `open_gripper` → `move_to_pose(cube.x, cube.y,
  cube.z + 0.10)` → `close_gripper` (grasps air) → `move_to_pose(cube.x, cube.y, cube.z
  + 0.15)`. On `RealCubeLiftEnv` (fake backend) it never grasps (`grasped=False`) →
  `success()` False → score 0. The bug the repair fixes.

- **`tests/b601/test_repair_loop.py`** — the deterministic CI proof. Constructs
  `TaskPipeline` in-process (mirroring `tests/aspire/test_coordinator.py`) with:
  - the REAL capx engine — `CapxEngine`/`AuditedEngine` wrapping
    `python scripts/b601_execute.py --config-path
    runs/2026-07-21-b601-real-cube-lift/cube_lift_fake.json` (RealCubeLiftEnv, fake
    backend);
  - a scripted `FakeActor(reports=[ActorReport(outcome="success",
    code_path="fix_code.py", …)])`;
  - a task dir with `code.py` = `baseline_grasp_air.py` and `fix_code.py` = the correct
    `baseline_lift.py`;
  - a config with `theta` between 0 and 1 (e.g. 0.5) and `t=0`.
  Runs the pipeline and asserts: (1) Stage-1 was triggered — `actor.debug_calls != []`
  (the failing baseline drove the repair path, unlike M3c's passing baseline); (2) the
  fix raised `dbg_score` from 0 to 1.0 (`>= theta`); (3) `result.stage_reached ==
  "validated"` and `result.val_score == 1.0`.

- **A trace-diagnosability assertion** (in `test_repair_loop.py`) — run
  `baseline_grasp_air.py` on `RealCubeLiftEnv` (fake backend) directly (or read the
  Stage-0 traces) and assert the failure is diagnosable from the trace text: a
  `set_gripper` trace carries `grasped=False`, and the closing `move_to_pose` z
  (`cube.z + 0.10`) is above the `get_cube_pose` cube.z. This proves a real LLM has the
  signal it needs; the repair is genuinely trace-guided, not luck.

- **`runs/2026-07-21-b601-real-cube-lift/cube_lift_real.json`** — a committed template
  for the on-bench run: `"backend": "real"` plus the measured fields as documented
  placeholders (`grip_lo`/`grip_hi`, `min_object_open`, `marker_size`,
  `base_frame`/`gripper_frame`, `lift_threshold`, `grasp_tol`) to finalize on-bench.

## The live capstone (on-bench + credits — the actual demonstration, not CI)

After M3b calibration (`hand_eye.json`) + M3c `RealMotionBackend.connect()` finalized +
the arm/MoveIt2/D405 up, with a task dir holding `baseline_grasp_air.py` as `code.py`:

```
python -m aspire.run --task-dir <dir> --engine capx \
  --capx-cmd "python scripts/b601_execute.py --config-path runs/2026-07-21-b601-real-cube-lift/cube_lift_real.json" \
  --library <lib> --s-dbg <seeds> --s-val <seeds>
```

The coordinator runs the failing baseline on the real arm (grasps air → `dbg_score <
theta`) → Stage-1: `ClaudeCodeActor` reads the real failing traces, writes `fix_code.py`
(adds the descend) → the engine re-runs it on the arm → grasps + lifts → Stage-2
validation → `validated`. The full ASPIRE reproduction closing on real hardware.
Reported honestly as a live+credits step, like the sim reproduction runs. Safety: all
M3a-c clamps + `move_to_look_pose` gripper-hold + the e-stop/monitor checklist apply;
run M3c's `--config-path` dry checks first.

## Testing

- **CI (deterministic, no LLM/credits/hardware):** `test_repair_loop` — Stage-1
  triggered, actor invoked, fix adopted, `validated` with `val_score 1.0`; the
  trace-diagnosability assertion; the failing baseline scores 0 standalone via
  `b601_execute --config-path cube_lift_fake.json` (a small direct subprocess check).
- **Live (credits + arm):** the `aspire.run` capstone above — the real
  `ClaudeCodeActor` repairing the grasp-in-air baseline on the real cube-lift.

## Not doing

- No `aspire/` changes — the coordinator/actor/engine/trace pipeline is reused verbatim.
- No new perception/motion/task code (M3a–c cover it).
- No new trace media (the existing text traces are diagnosable — YAGNI).
- No evosearch demonstration in the CI test (`t=0`; evosearch is tested in `aspire/`).
- No markerless perception, multi-object, or clutter.

## Deliverable mapping

- Completes "the ASPIRE trace-guided repair loop reproduces on the real robot": a
  failing real cube-lift baseline is repaired to a passing one through the full
  pipeline, CI-proven for the wiring and documented for the live+credits demonstration.
- Closes the B601 track (M3a first-light → M3b perception/calibration → M3c real
  cube-lift → M3d real repair loop). The remaining work is the on-bench live runs
  (hardware + credits), for which every software piece is now built and CI-proven.
