# B601 Milestone 3a — real-hardware "first light" (RS arm over ROS 2) — design

_Date: 2026-07-20. Status: SPEC for review. Builds on M1 (`robot_b601/` transport
seam, node, engine, first-light) and M2 (task loop). Branch `aspire_original_sim`.
Hardware is on the bench (B601-RS + D405)._

## Purpose

Drive the **real B601-RS arm** from the ASPIRE engine — the hardware analog of M1's
sim "first light." The `B601Transport` seam swaps from sim UDP (M1) to a **real ROS 2
transport**; the `B601Node`, `B601Engine`, and trace pipeline are reused unchanged.
Because we command a physical arm, M3a adds a **safety layer** (joint-limit clamp +
small bounded motions + the vendor safe-park monitor) and ends in a real on-bench
validation move. Perception (D405), grasp, reward, and the full ASPIRE loop are
**deferred to M3b/c/d** — M3a is "the ASPIRE engine moves the real arm, safely."

## What exists (the two seams we build on)

1. **The `B601Transport` seam** (M1): `publish(JointCommand)` / `latest() -> JointState`.
   `B601Node` re-streams the full setpoint each poll and converges/timeouts on an
   injectable clock. Swapping the transport swaps the robot; nothing above changes.
2. **Vendor RS ROS 2 stack:** `rebotarm_bringup` (controller, MoveIt2, gravity
   compensation), `reBotArmController_ROS2`, and `rebotarm_monitor_ros2` (**safe park
   & shutdown** — captures rest pose on connect, slow return; gravity-comp smooth
   stop). We command joints through the controller and read `/joint_states`; the
   monitor provides fault-safe behavior. (CAN/MotorBridge is a lower-level fallback,
   out of M3a scope.)

## Architecture

- **`robot_b601/limits.py` — safety clamp (pure, CI-tested).** `JointLimits` (6
  joints, `(lo, hi)` radians) and `clamp_to_limits(joints, limits) -> (clamped:
  list[float], was_clamped: bool)`. The transport NEVER publishes a joint outside
  limits. Real limit values come from the B601-RS URDF (in `rebotarm_bringup`) and
  are committed to `robot_b601/b601_rs_limits.yaml` during on-bench bring-up;
  conservative defaults ship until then. The clamp function is limits-parameterized
  and fully unit-tested (in-range passes; out-of-range clamps + flags).

- **`robot_b601/ros_transport.py` — `B601RosTransport` (implements `B601Transport`).**
  `publish(cmd)`: `clamp_to_limits` the joints, then publish to the controller command
  topic. `latest()`: return the newest `/joint_states` as a `JointState`. Uses
  `rclpy`, imported **deferred** (inside `connect()`), so the module + its pure
  helpers import and test WITHOUT ROS 2. Pure, CI-tested helpers: `_positions_from_cmd(cmd)
  -> list[float]` (the 6 joint values to put on the wire, post-clamp) and
  `_state_from_positions(positions, gripper) -> JointState`. The exact command topic /
  controller interface (position vs trajectory controller, gripper mapping) is the ONE
  detail confirmed on-bench against `rebotarm_bringup` — like M1's Isaac
  ArticulationView finalization; it does not affect the tested helpers.

- **`scripts/b601_real_first_light.py` — the real-arm runner.** Reads the arm's
  current pose as `home` (via `latest()`), then commands **small bounded joint
  waypoints** (home ± `delta_max`, default 0.15 rad) through `B601Engine` (M1 tracing),
  and writes an `ExecuteResult`. `--dry-run` prints the planned, clamped waypoints
  **without connecting to ROS 2 or moving** — a CI-testable safety preview. A live run
  (`--host`/topic args) needs ROS 2 sourced + the arm powered.

## Safety (foregrounded — this moves a real arm)

- **Two independent bounds:** motions are small deltas from the *current* pose
  (primary), AND every command is `clamp_to_limits`'d to absolute joint limits
  (backstop). Neither alone; both.
- **Vendor safe-park monitor** (`rebotarm_monitor_ros2`) runs alongside — fault →
  slow return to rest; gravity-comp smooth stop.
- **Bring-up checklist** in the runner docstring: e-stop within reach; monitor
  launched; `delta_max` small; first run at reduced speed; clear workspace.
- **`--dry-run` first** — always preview the clamped waypoints before any live move.

## Testing

- **CI (no hardware, no ROS 2):** `clamp_to_limits` (in-range unchanged; out-of-range
  clamped to the boundary + `was_clamped=True`; per-joint independent); the transport's
  pure helpers (`_positions_from_cmd` applies the clamp; `_state_from_positions` shape);
  the runner's `--dry-run` prints clamped safe waypoints and exits 0 without importing
  `rclpy`; `B601Node`/`B601Engine` over `FakeB601Transport` (reused from M1). Deferred
  `rclpy` import verified: `import robot_b601.ros_transport` succeeds with no ROS 2.
- **On-bench (live, ROS 2 + arm — done now, hardware is present):** `--dry-run` review;
  source ROS 2, `ros2 launch rebotarm_bringup …` + `rebotarm_monitor_ros2`, run
  `b601_real_first_light.py`; the real arm gently executes the bounded waypoints,
  `/joint_states` converges, traces recorded. Reported honestly as a live step (like
  M1's golden trace); safety checklist enforced.

## Components (files)

- `robot_b601/limits.py` (`JointLimits`, `clamp_to_limits`), `robot_b601/b601_rs_limits.yaml`
  (conservative defaults; finalized from the URDF on-bench).
- `robot_b601/ros_transport.py` (`B601RosTransport` + pure helpers).
- `scripts/b601_real_first_light.py` (runner + `--dry-run`).
- `tests/b601/test_limits.py`, `tests/b601/test_ros_transport_helpers.py`,
  `tests/b601/test_real_first_light_dryrun.py`.

## Decisions (flag if you disagree)

1. **ROS 2, not CAN**, for M3a — reuses the vendor controller, MoveIt2, gravity comp,
   and the `rebotarm_monitor_ros2` safe-park. CAN/MotorBridge is a later fallback.
2. **`rclpy` deferred-imported** so the module + all safety/conversion logic are
   CI-tested without ROS 2; the live node is on-bench.
3. **Small-delta-from-current waypoints** (not sim's aggressive poses) + absolute-limit
   clamp — conservative first contact with a real arm.
4. Perception/grasp/reward/full-loop are **M3b/c/d**, not M3a.

## Not doing (M3b+)

- No D405 / `pyrealsense2` / perception; no `get_object_pose` from camera (M3b).
- No hand-eye calibration (M3b — the known vendor gap).
- No grasp, no cube-lift task, no reward on hardware (M3c).
- No ASPIRE repair loop on hardware (M3d).
- No CAN/MotorBridge transport (fallback, later).
- No `aspire/` changes; reuse the M1/M2 stack unchanged.

## Deliverable mapping

- Completes the sim→real transport swap: the ASPIRE engine drives the real B601-RS,
  safely, through the same seam that drove Isaac (M1) and ran the cube-lift task (M2).
- The safety layer + vendor safe-park is the SOW's **safety-response** story surfacing
  on real hardware. Sets up M3b (D405 perception + hand-eye) and M3c/d (real task +
  loop).
