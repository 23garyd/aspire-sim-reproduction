# B601 Isaac backend — Milestone 2 (cube-lift task + full ASPIRE loop) — design

_Date: 2026-07-20. Status: SPEC for review. Builds on Milestone 1
(`robot_b601/` — transport/node/engine/first-light, merged). Branch
`aspire_original_sim`._

## Purpose

Turn the B601 backend from "moves the arm" (M1) into "runs a manipulation task
through the full ASPIRE loop." Add a **cube-lift** task (object + privileged
ground-truth perception + reward), a Cartesian **`move_to_pose`** primitive, and a
`b601_execute.py` that honors the existing engine contract — so
`aspire.run --engine capx --capx-cmd "python scripts/b601_execute.py …"` drives the
whole reproduction pipeline (baseline → repair → evosearch → skills → held-out
validation) on the B601 cube-lift with **no `aspire/` changes**.

## The integration seam (why no pipeline changes)

`aspire.run --engine capx` shells out to `--capx-cmd` with
`--program P --seeds S --out-dir D [--config-path YAML]` and reads back
`D/result.json` in `ExecuteResult` format (`{score, raw_dir, traces}`) — see
`scripts/capx_execute.py` and `CapxEngine` (`aspire/engines.py`). A
**`b601_execute.py` honoring that exact contract is a drop-in engine**: the
coordinator, `aspire.run`, `CapxEngine`, the audit wall, evosearch, and skill
admission are all reused unchanged. The B601 is "just another engine."

## Task: cube lift (matches the reproduction's `cube_lifting`)

Single arm + gripper: a cube on a table at a per-seed randomized pose; success =
cube lifted above a height threshold. The simplest task that exercises perception →
reach → grasp → lift, and a clean fit for the 6-DOF B601 + gripper.

## Architecture

### 1. Cartesian task primitives (M2's new layer, above M1's joint layer)

Manipulation reasoning is Cartesian, so the agent-facing primitives are:
- `get_cube_pose() -> CubePose(x,y,z, qx,qy,qz,qw)` — **privileged** ground-truth
  from the env (the only perception; no camera in M2).
- `move_to_pose(x, y, z, roll, pitch, yaw) -> MoveResult` — EE pose command. **Live**:
  IK (vendor `isaacsim_ik_sender` / Pinocchio) → joints → M1 `B601Node.move_to_joints`
  → transport. **Fake**: sets the modeled EE pose directly (IK assumed to solve).
- `set_gripper(pos)` / `open_gripper()` / `close_gripper()` — from M1.
- `move_to_joints(joints)` — from M1 (kept for joint-space programs).

Each primitive emits an `aspire.schemas.TraceRecord` (reuse the M1 trace machinery).

### 2. `CubeLiftEnv` — task abstraction (Fake + Isaac)

`robot_b601/task.py`:
- `CubeLiftEnv` base: `reset(seed)` (place cube at a seeded pose, EE home),
  `namespace() -> dict` (the primitives above, bound + traced, for the program to
  call), `success() -> bool` (cube.z > lift_threshold), `traces() -> list[TraceRecord]`.
- **`FakeCubeLiftEnv`** — deterministic Cartesian model, NO Isaac. Owns EE pose,
  gripper, cube pose, `grasped` flag. Honest simplified success model (no physics):
  `close_gripper()` sets `grasped=True` iff the EE is within `grasp_tol` of the cube
  and the gripper closes; while `grasped`, the cube follows the EE; `success()` =
  final cube.z > `lift_threshold`. A *correct* reach→grasp→lift program → success;
  a no-op or wrong-pose program → cube unmoved → failure. This makes the whole
  contract unit-testable and the reward meaningful without Isaac.
- **`IsaacCubeLiftEnv`** — live, on-box. Spawns the cube USD in the RS scene, drives
  `move_to_pose` via IK → M1 transport (`:5005`/`:5006` bridge), reads real
  ground-truth cube pose and physics grasp/lift. **Intentional live-only stub** with
  `TODO(on-box)` markers (like M1's bridge) — finalized against the installed Isaac
  API; needs Isaac + `ISAACSIM_ROOT`.

### 3. `scripts/b601_execute.py` — the engine (capx contract)

Honors `--program --seeds --out-dir [--config-path] [--selftest] [--workdir]`;
writes `out-dir/result.json` = `{score, raw_dir, traces}`. Per seed:
1. `env.reset(seed)`.
2. `violations = aspire.audit.audit_code(program_src)`; a forbidden/seed-specific
   program fails that seed (score 0, an `audit` error trace) — reuse the wall
   unchanged.
3. `exec(program_src, env.namespace())` — run the agent program against the
   primitive namespace only (privileged-but-fair; no raw env/sim access exposed).
4. `ok = env.success()`; collect `env.traces()`.
`score = successes / len(seeds)`. `--selftest` (or no `--config-path`) uses
`FakeCubeLiftEnv` (no Isaac, CI-safe); a real `--config-path` selects
`IsaacCubeLiftEnv` (on-box). Mirrors `capx_execute.py` exactly.

### 4. Task config fixture

`runs/2026-07-20-b601-cube-lift/cube_lift.yaml` (committed): cube pose
randomization range, `lift_threshold`, `grasp_tol`, IK/frame params. The
`--config-path` the engine loads.

## The deterministic full-pipeline integration test (no Isaac, no credits)

A **passing** baseline skips the repair actor (coordinator: `dbg_score >= theta` ⇒
no Stage-1, no evosearch, no extraction ⇒ **no `claude -p` call**). So we test the
B601 backend *inside the real ASPIRE pipeline* deterministically:
- Provide a **correct** cube-lift baseline program (`get_cube_pose` → reach → grasp
  → lift) that scores 1.0 in `FakeCubeLiftEnv`.
- Run `aspire.run --task-dir <t> --engine capx --capx-cmd "python scripts/b601_execute.py --selftest" --library <l> --s-dbg 0,1,2 --s-val 100-104`.
- Assert it reaches `validated` with `val_score 1.0` and calls no actor.
This proves the drop-in engine works end-to-end in the pipeline — without Isaac and
without API spend. (The *repair* loop — a failing baseline → LLM repair — is the
credit-gated on-box run, not a unit test.)

## Testing

- **Deterministic (no Isaac, no credits):** `FakeCubeLiftEnv` success model (correct
  program → success; no-op/wrong-pose → failure; grasp only within `grasp_tol`);
  the primitive namespace + tracing (`move_to_pose`, `get_cube_pose`, gripper emit
  `TraceRecord`s); `b601_execute --selftest` writes a valid `result.json` whose score
  reflects program correctness; `audit_code` rejects a forbidden program; the
  full-pipeline integration test above.
- **Live on-box (Isaac + later credits):** `IsaacCubeLiftEnv` cube spawn + physics
  grasp/lift + real ground-truth; then the actual ASPIRE repair loop on a failing
  baseline (LLM). Reported honestly as live steps, like M1's bridge/golden trace.

## Components (files)

- `robot_b601/task.py` (`CubeLiftEnv`, `FakeCubeLiftEnv`, `IsaacCubeLiftEnv` stub,
  `CubePose`). The Cartesian `move_to_pose` seam lives here for M2: `FakeCubeLiftEnv`
  sets the modeled EE pose directly (IK assumed to solve); `IsaacCubeLiftEnv` (stub)
  routes it through the vendor IK sender → M1 `B601Node`. No separate kinematics
  module in M2.
- `scripts/b601_execute.py` (capx-contract engine).
- `runs/2026-07-20-b601-cube-lift/cube_lift.yaml` (task config) + a committed correct
  baseline program for the integration test.
- `tests/b601/test_task.py`, `tests/b601/test_b601_execute.py`,
  `tests/b601/test_pipeline_integration.py`.

## Not doing (deferred)

- No live Isaac env build beyond the stub (on-box).
- No camera / D405 / real perception (M3); perception is privileged `get_cube_pose`.
- No real-hardware path (M3).
- No `aspire/` package changes — reuse `schemas`, `audit`, `engines`, the whole
  pipeline via the capx contract.
- No second task yet (cube lift only); more tasks are a later milestone and the
  richer curriculum a fair layer-2 test would need.

## Deliverable mapping

- Completes "the ASPIRE loop reproduces on the new robot" in sim: the B601 cube-lift
  is a real ASPIRE engine, pipeline-integrated and tested without Isaac/credits.
- Sets up the on-box run (live Isaac cube-lift + a real repair loop) and M3 (real
  B601-RS + D405).
