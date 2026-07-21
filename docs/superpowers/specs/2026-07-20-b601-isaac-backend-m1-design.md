# B601 Isaac backend — Milestone 1 ("first light") — design

_Date: 2026-07-20. Status: SPEC for review._

**Branch target: `aspire_original_sim`** (canonical, pushed to `aspire_demo`). New
module `robot_b601/`, reusing `aspire/schemas.py` (`TraceRecord`, `ExecuteResult`)
as the trace/result contract. This is the go-forward robot; the A2 stack
(`aspire_a2_sim`) is shelved.

## Purpose

Prove ASPIRE's traced execution engine drives the **reBot B601 arm in Isaac Sim**
end-to-end: a scripted program of joint-space primitives + gripper runs on the arm,
each primitive recorded as a `TraceRecord`, producing an `ExecuteResult`. The one
hard unknown solved here is that the vendor Isaac package is **command-only
(one-way UDP)** — Milestone 1 adds a **state-return channel** so the ASPIRE engine
can close the loop (command → observe → converge). No manipulation objects,
ground-truth poses, or reward yet — those are Milestone 2.

**Target: RS end-to-end** — the **RS** USD (`usd/RS-rebot-dev-arm/00-arm-rs_asm-v3.usda`,
prim `/World/reBotArm`) in sim, and the **RS (Robstride)** arm as the real-hardware
target (Milestone 3). RS is chosen throughout for full sim-to-real consistency
(same arm in sim and reality) and because RS ships the mature vendor stack —
completed Isaac integration and the fuller ROS 2 + MoveIt2 path (kinematics,
trajectory planning, gravity compensation). This also retires the missing-DM-USD
blocker entirely. The `B601Transport` seam keeps the real-hardware control layer a
swap, not a redesign, if the motor variant ever changes.

## What exists (the two seams we build on)

1. **Vendor Isaac control** (`reBot-Isaacsim`): one-way UDP-JSON on `:5005` —
   `{sequence:int, timestamp:float, joint_positions:[float×6] (rad),
   gripper_position:float (m)}` — applied by `isaacsim_joint_receiver.py` to
   `/World/reBotArm`. Env: `ISAACSIM_ROOT`. **No state return, no objects, no
   camera.**
2. **ASPIRE trace/result contract** (`aspire/schemas.py`): `TraceRecord(step,
   function, args:dict, status:"ok"|"error", result_summary, duration_ms,
   media:list)` and `ExecuteResult(score, traces, raw_dir)` with `to_json()`.
   Reused unchanged — the B601 backend emits the same records the reproduction and
   any later safety/link work consume.

## Architecture (mirrors the proven A2 + CaP-X patterns)

- **`B601Transport` protocol** (`robot_b601/transport.py`): `publish(cmd:
  JointCommand) -> None`, `latest() -> JointState | None`, where
  `JointCommand(joint_positions: list[float], gripper_position: float)` and
  `JointState(joint_positions: list[float], gripper_position: float)`. Two impls:
  - **`FakeB601Transport`** — deterministic; `publish` sets the target, `latest`
    advances each joint a fixed fraction toward the target and returns it
    (`gap_close` like `FakeRosTransport`; `gap_close=0` models a stuck arm →
    TIMEOUT). No sockets, no threads → unit-testable without Isaac.
  - **`B601IsaacUdpTransport`** — live: `publish` sends the vendor `:5005` JSON;
    `latest` reads the newest `:5006` state datagram (the return channel added by
    the bridge, §Return channel). Stdlib `socket` only.
- **`B601Node`** (`robot_b601/node.py`): sync facade over the transport, injectable
  clock (reuse the `RealClock`/`ManualClock` pattern) and `poll_dt`:
  - `move_to_joints(joints, tol=1e-2, timeout_s=5.0) -> MoveResult(reached,
    residual, status:"ok"|"TIMEOUT", iterations)` — re-streams the target every
    poll (joint-servo controllers hold only briefly), reads state, converges within
    `tol` or times out on the clock.
  - `set_gripper(pos, timeout_s=2.0) -> MoveResult` — same poll-to-converge on the
    gripper axis.
- **Traced primitive API** (`robot_b601/engine.py`): `B601Engine` wrapping a
  `B601Node`, exposing agent-facing primitives (`move_to_joints`, `set_gripper`)
  each decorated to emit a `TraceRecord` (step, function, args, ok/error, a
  `result_summary` like `reached residual=…`, `duration_ms`). Accumulates a trace
  list → `ExecuteResult`.
- **Isaac-side bridge** (`scripts/b601_isaac_bridge.py`): adapted from the vendor
  `isaacsim_joint_receiver.py` — loads the RS USD arm at `/World/reBotArm`, applies
  incoming `:5005` joint/gripper targets, **and every sim tick reads the arm's
  joint + gripper state via the Isaac Python API and sends it back on `:5006`** as
  the same JSON shape. This is the piece that turns the one-way sandbox into a
  closed loop. Runs inside Isaac (`ISAACSIM_ROOT`).
- **First-light runner** (`scripts/b601_first_light.py`): runs a scripted primitive
  program — a few joint waypoints (e.g. home → target-A → target-B → home) with a
  gripper open/close — through `B601Engine`, writes `ExecuteResult` JSON + prints a
  summary. `--selftest` uses `FakeB601Transport` (CI-safe, no Isaac); without it,
  uses `B601IsaacUdpTransport` against the live bridge.

## The return channel (the M1 crux)

The vendor sim is command-only. M1 adds a **second UDP port `:5006`** for state:
the bridge, inside Isaac, publishes `{sequence, timestamp, joint_positions[6],
gripper_position}` every tick; `B601IsaacUdpTransport.latest()` non-blockingly reads
the newest datagram. This is the minimal closed loop — no ROS 2, no vendor-code
fork beyond the bridge script. (Real hardware, M3, replaces this with the
ROS 2/CAN joint-state path; the `B601Transport` seam is unchanged.)

## Data flow

1. `b601_first_light.py` builds `B601Engine(B601Node(transport, clock))`.
2. For each primitive: `B601Node` re-streams the target via `transport.publish`
   (→ `:5005` → Isaac moves the arm), reads state via `transport.latest`
   (→ `:5006`), converges or times out; `B601Engine` records a `TraceRecord`.
3. On completion, an `ExecuteResult` (score = fraction of primitives that reached,
   traces = the records) is written as JSON.
4. Live: the bridge runs in Isaac and the arm visibly executes the waypoints; the
   trace file is the machine-readable proof. Selftest: identical flow over
   `FakeB601Transport`, deterministic.

## Testing

- **Deterministic (no Isaac), unit-tested:** `FakeB601Transport` convergence and
  stuck-arm TIMEOUT; `B601Node.move_to_joints`/`set_gripper` reach vs timeout under
  `ManualClock`; `B601Engine` emits well-formed `TraceRecord`s (ok on reach, error
  on timeout) and a valid `ExecuteResult`; `--selftest` runner exits 0 and writes a
  parseable result. Follows the existing TDD-at-the-transport-boundary discipline.
- **Live on-box (Isaac):** run `b601_isaac_bridge.py` in Isaac (RS USD) + the
  runner without `--selftest`; confirm the arm executes the waypoints and the trace
  file records real convergence. Reported honestly as a live step (like the
  reproduction's golden trace); **not** faked-as-passing, and not a unit test.

## Components (files)

- `robot_b601/__init__.py`, `robot_b601/transport.py` (protocol + Fake + IsaacUdp),
  `robot_b601/node.py` (`B601Node`, `MoveResult`), `robot_b601/engine.py`
  (`B601Engine`, traced primitives), `robot_b601/clock.py` (or reuse a shared clock).
- `scripts/b601_isaac_bridge.py` (Isaac-side), `scripts/b601_first_light.py`
  (runner + `--selftest`).
- `tests/b601/` — deterministic coverage for transport/node/engine/runner.

## Success criteria (Milestone 1)

- `--selftest` runs the scripted program over `FakeB601Transport`, writes a valid
  `ExecuteResult` (score 1.0 when all primitives reach), traces well-formed. Green
  in CI, no Isaac needed.
- On the box: the live bridge + runner move the RS-USD B601 arm through the
  waypoints in Isaac, and the trace file records real convergence — documented,
  reproducible.

## Not doing (Milestone 2+)

- No manipulation objects, ground-truth object poses, or reward/success check
  (M2 — the ASPIRE task loop on B601).
- No EE-pose/IK primitive yet (M1 is joint-space; the vendor IK sender is the fast
  follow for `move_to_pose`).
- No D405 / camera / perception (M3, real hardware).
- No real-hardware ROS 2/CAN path or RS (Robstride) motor control (M3).
- No changes to `aspire/` package internals (reuse `schemas.py` only).

## Deliverable mapping

- Advances the "move to a different robot" goal: ASPIRE's execution engine + trace
  pipeline proven on the B601-in-Isaac (RS USD), with the two-way comms solved.
- Sets up Milestone 2 (a B601 manipulation task + privileged reward → the full
  ASPIRE loop on the new robot) and Milestone 3 (real B601-RS + D405).
