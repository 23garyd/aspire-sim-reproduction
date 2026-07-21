# B601 Milestone 3c — real cube-lift on hardware — design

_Date: 2026-07-21. Status: SPEC for review. Builds on M2 (`robot_b601/task.py` —
`FakeCubeLiftEnv`, `CubePose`, the primitive namespace; `scripts/b601_execute.py`
capx-contract engine), M3a (`B601Transport`/`B601Node`, `limits.py`, `move_to_look_pose`
gripper-hold), and M3b (`transforms`, `perception.RealPerceptionSource`, `hand_eye`,
`d405`, `tf_pose`). Branch `aspire_original_sim`. Hardware on the bench (B601-RS + D405)._

## Purpose

Run the full **cube-lift task on the real B601-RS**: real D405 perception (M3b)
localizes the cube, the arm **reaches** (vendor IK) → **grasps** → **lifts**, and
success is judged **proprioceptively** — all behind the existing `b601_execute`
capx-contract engine, so it is a drop-in ASPIRE task with **no `aspire/` changes**.

The LLM/ASPIRE repair loop on hardware is **M3d**. M3c ends when a correct hand-written
baseline program lifts the real cube end-to-end through `b601_execute`.

Same sim-first / live-integration split as M1–M3b: the task sequencing, grasp/lift
evaluation, and gripper-limit logic are CI-tested with fakes; the vendor IK/MoveIt2
motion and the D405 capture are on-bench behind deferred imports.

## Decisions (resolved during brainstorming)

1. **Vendor MoveIt2 / IK over ROS 2** turns a Cartesian `move_to_pose` goal into joint
   angles on the real arm — reuses the arm's tested, collision-aware motion stack (in
   `rebotarm_bringup`); least new kinematics code; safest for a real pick. It sits behind
   a `MotionBackend` seam, so the CI-tested task logic is unaffected and the exact vendor
   IK interface is finalized on-bench (like M3a's command topic).
2. **Proprioceptive success.** Perception localizes the cube for the REACH (the real
   `get_cube_pose`); the wrist-mounted D405 is occluded once the cube is grasped, so
   success = **grasp confirmed** (after a close, the gripper stalls open by ≥ the object
   width → object held) **AND EE height** (from ROS 2 TF) **> lift_threshold**. Robust,
   no occlusion dependency; perception is meaningfully in the loop for localization.
3. **Grasp detection is position-based** — the gripper's achieved position from
   `/joint_states` after a commanded close (no force/current sensing assumed).
4. **EE height from ROS 2 TF** (reuse `robot_b601/tf_pose.py`).
5. **`RealCubeLiftEnv.reset(seed)` does NOT move the physical cube** (it cannot) — it
   re-perceives wherever the cube physically is; the seed is logged only. An honest
   boundary: on real hardware, "seeds" are repeated physical trials, not programmatic
   randomization.

## Dependency landscape

`rclpy`/`tf2_ros` (M3b) drive the vendor stack, deferred-imported (on-bench). No new
Python deps: IK lives in the vendor ROS 2 stack, not in our code. The CI-tested code is
stdlib + numpy only (`FakeMotionBackend`, grasp/lift math, gripper clamp).

## Architecture

### Data flow (one real trial)

```
D405 ──▶ real get_cube_pose (M3b, arm frame)
             │  program (agent code):
             ▼
   move_to_pose(cube.x, cube.y, approach_z)   ─┐ vendor IK (MoveIt2/ROS 2)
   move_to_pose(cube.x, cube.y, cube.z)        ┘ reach
   close_gripper()                              → set_gripper clamped to gripper limits
             │  gripper_position() from /joint_states
             ▼
   grasp_detected(gripper_pos, ...)             → object held?
   move_to_pose(cube.x, cube.y, lift_z)         → lift
             │  ee_pose().z from ROS 2 TF
             ▼
   success = grasped AND ee_z > lift_threshold
```

### Components (files)

- **`robot_b601/motion.py` — the `MotionBackend` seam.**
  - `MoveResult` (reuse or mirror `robot_b601/node.py`'s); a `MotionBackend` Protocol:
    `move_to_pose(x,y,z,roll=0,pitch=0,yaw=0) -> MoveResult`, `move_to_joints(joints) ->
    MoveResult`, `set_gripper(pos) -> MoveResult`, `gripper_position() -> float`,
    `ee_pose() -> EePose(x,y,z,roll,pitch,yaw)`.
  - **`FakeMotionBackend`** (CI, stdlib): owns a modeled EE pose + gripper position;
    `move_to_pose` sets the EE directly (IK assumed to solve); `set_gripper` clamps to
    gripper limits and models a stall at the object width when the EE is within
    `grasp_tol` of the held object; `gripper_position`/`ee_pose` return the model. This
    reproduces M2's `FakeCubeLiftEnv` physics so the whole task is unit-testable.
  - **`RealMotionBackend`** (on-bench, deferred `rclpy`): `move_to_pose` sends the
    Cartesian goal to the vendor IK/MoveIt2 over ROS 2 and executes; `move_to_joints`
    goes through M3a `B601RosTransport` + `B601Node` via `move_to_look_pose` (gripper
    held, fail-loud); `set_gripper` clamps to gripper limits then commands the gripper;
    `gripper_position()` reads `/joint_states`; `ee_pose()` reads TF (`tf_pose`).
    Intentional live-only stub with `TODO(on-bench)` markers for the exact vendor IK
    service/action and TF frames, like M1's bridge. Not unit-tested (needs ROS 2 + arm).

- **`robot_b601/limits.py` (extend) — gripper limits.** Add a gripper `(lo, hi)` bound
  and `clamp_gripper(pos, limits) -> (clamped, was_clamped)` so `set_gripper` can never
  over-travel or crush — the deferred M3a/M3b gripper-clamp item, now closed. Gripper
  bounds join `b601_rs_limits.json` (conservative defaults; finalized on-bench). Fully
  CI-tested (in-range passes; out-of-range clamps + flags), mirroring the joint clamp.

- **`robot_b601/grasp.py` — grasp + lift evaluation (pure, CI-tested).**
  `grasp_detected(gripper_pos, closed_ref, min_object_open) -> bool` (a close that
  stalls open by ≥ `min_object_open` above `closed_ref` means an object is between the
  fingers); `lifted(ee_z, lift_threshold) -> bool`; `cube_lift_success(grasped, ee_z,
  lift_threshold) -> bool`.

- **`robot_b601/task.py` (add `RealCubeLiftEnv`).** Composes a `MotionBackend` + a
  `get_cube_pose` source (M3b `RealPerceptionSource`, or a fake returning a modeled
  cube) + the grasp/lift evaluators. Same contract as `FakeCubeLiftEnv`: `reset(seed)`
  (re-perceive the cube, home the EE, log the seed — NO physical randomization),
  `namespace()` (the traced primitives: `get_cube_pose`, `move_to_pose`, `set_gripper`,
  `open_gripper`, `close_gripper`), `success()` (grasp-detected ∧ EE-lifted),
  `traces()`. Each primitive emits a `TraceRecord` (reuse M2's trace machinery).
  `FakeCubeLiftEnv` is unchanged.

- **`scripts/b601_execute.py` (modify env selection).** `--selftest`/no `--config-path`
  → `FakeCubeLiftEnv` (unchanged). A real `--config-path` → `RealCubeLiftEnv` (deferred
  import), replacing the `IsaacCubeLiftEnv` stub. The `--program/--seeds/--out-dir →
  result.json {score,raw_dir,traces}` capx contract is unchanged.

## The CI-testable slice (no hardware)

`RealCubeLiftEnv` is fully unit-testable by injecting a `FakeMotionBackend` + a fake
perception source (returns a modeled cube pose) + the fake gripper feedback:
- a **correct** reach→grasp→lift program → `success()` True;
- a no-op or wrong-pose program → cube not grasped/lifted → False;
- grasp only registers when the gripper closes with the EE within `grasp_tol` of the
  cube (stall model);
- `set_gripper` beyond the gripper limits is clamped;
- the primitives emit traces.
Plus the **deterministic full-pipeline test** (mirrors M2): a correct baseline program
run through `aspire.run --engine capx --capx-cmd "python scripts/b601_execute.py …"`
selecting the fake-backed `RealCubeLiftEnv` reaches `validated` with `val_score 1.0` and
calls no actor (a passing baseline skips repair → no LLM, no credits). `FakeCubeLiftEnv`
and all M2 tests stay green (270 passing preserved).

## On-bench (live — hardware present)

After M3b calibration (`hand_eye.json`) + ROS 2 up (`rebotarm_bringup` + MoveIt2 +
`rebotarm_monitor_ros2` safe-park) + D405 connected: run `b601_execute` with the real
config + a correct baseline program → the arm perceives the cube, reaches (vendor IK),
grasps (gripper clamped), lifts, and `success()` reports honestly. Safety: gripper +
joint clamps, `move_to_look_pose` gripper-hold on joint moves, e-stop/monitor checklist,
`--dry-run`/preview first. Reported honestly as a live step, like M1's golden trace.

## Testing

- **CI (no hardware, no ROS 2):** the gripper clamp (`clamp_gripper`); grasp/lift
  evaluators (`grasp_detected`, `lifted`, `cube_lift_success`) on hand-computed cases;
  `FakeMotionBackend` (move_to_pose sets EE; set_gripper clamps + models the grasp
  stall; gripper_position/ee_pose return the model); `RealCubeLiftEnv` over the fake
  backend + fake perception (correct program lifts; no-op/miss fails; grasp only within
  `grasp_tol`; clamp respected; primitives traced); `b601_execute` selecting the
  fake-backed real env writes a valid `result.json`; the full-pipeline integration test;
  deferred-import guard (`import robot_b601.motion` succeeds with no `rclpy`).
- **On-bench (live):** the real cube-lift via `b601_execute` on the arm (vendor IK reach
  + real grasp/lift + real perception localization). Reported honestly as a live step.

## Components summary (files)

- `robot_b601/motion.py` (`MotionBackend`, `FakeMotionBackend`, `RealMotionBackend`,
  `EePose`, `MoveResult`).
- `robot_b601/grasp.py` (`grasp_detected`, `lifted`, `cube_lift_success`).
- `robot_b601/limits.py` (extend: gripper `(lo,hi)` + `clamp_gripper`).
- `robot_b601/task.py` (add `RealCubeLiftEnv`).
- `scripts/b601_execute.py` (real-env selection).
- `runs/2026-07-21-b601-real-cube-lift/cube_lift.yaml` (real-hardware config: gripper
  limits, `lift_threshold`, `grasp_tol`, `min_object_open`, approach/lift heights, marker
  size, TF frames) + a committed correct baseline program for the integration test.
- Tests: `tests/b601/test_gripper_limits.py`, `test_grasp.py`, `test_motion_fake.py`,
  `test_real_cube_lift.py`, `test_b601_execute_real.py` (fake-backed), and the
  full-pipeline integration test extension.

## On-bench-finalized (honest boundary)

- The exact vendor IK interface (MoveIt2 MoveGroup action vs a reBot IK service) and its
  ROS 2 topics/frames — the one detail confirmed against `rebotarm_bringup` on-bench.
- Gripper limit values + the fully-closed reference + object width (`min_object_open`)
  measured from the real gripper + cube.
- Approach/lift heights and `grasp_tol` tuned on-bench; committed defaults.

## Not doing (M3d+)

- No LLM / ASPIRE repair loop on hardware (M3d).
- No markerless/learned perception; single marked cube only.
- No multi-object, clutter, or collision-scene modeling beyond what vendor MoveIt2 gives.
- No `aspire/` changes; `FakeCubeLiftEnv` and the M2 tests unchanged; the `IsaacCubeLiftEnv`
  stub is superseded by `RealCubeLiftEnv` as the config-selected env (the Isaac path is
  not carried forward — the platform target is RS hardware).

## Deliverable mapping

- Completes "the ASPIRE cube-lift task runs on the real robot": real perception + vendor
  IK reach + real grasp/lift, pipeline-integrated via the unchanged capx contract, with
  the task logic CI-tested and the motion on-bench. Closes the deferred gripper-clamp.
- Sets up M3d (the real ASPIRE repair loop: a failing baseline → LLM repair → re-run on
  the real cube-lift).
