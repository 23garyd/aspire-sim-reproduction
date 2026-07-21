# B601 Milestone 3a — Real-hardware First Light Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Drive the real B601-RS arm from the ASPIRE engine over ROS 2 — a `B601RosTransport` swap behind the existing `B601Transport` seam, a joint-limit safety clamp, and a gentle bounded first-light runner (with a CI-safe `--dry-run`).

**Architecture:** New `robot_b601/limits.py` (pure safety clamp) and `robot_b601/ros_transport.py` (`B601RosTransport` implementing the M1 `B601Transport` seam, `rclpy` deferred-imported), plus `scripts/b601_real_first_light.py` (reuses M1 `B601Node`/`B601Engine`). Everything except the live `rclpy` node + real arm move is unit-tested without ROS 2; the live move is the on-bench step (hardware is present).

**Tech Stack:** Python 3 stdlib + `robot_b601` (M1/M2). `rclpy` + `sensor_msgs` (ROS 2) are used ONLY at live-run time, deferred-imported. pytest (`-p no:anyio`).

## Global Constraints

- Build on `aspire_original_sim`; new code under `robot_b601/{limits,ros_transport}.py`, `scripts/b601_real_first_light.py`, `robot_b601/b601_rs_limits.json`, `tests/b601/`. **NO changes to `aspire/`**; reuse M1 `B601Node`/`B601Engine`/`FakeB601Transport`/`JointCommand`/`JointState`.
- `robot_b601/` is STDLIB-ONLY in imported/tested code (M1/M2 constraint) — so the limits config is `b601_rs_limits.json` (NOT yaml; PyYAML isn't stdlib). `rclpy`/`sensor_msgs` appear ONLY inside deferred imports in `ros_transport.py` live methods — never at module top level, so the module imports and tests without ROS 2.
- **Safety is two independent bounds:** the runner commands small deltas from the arm's CURRENT pose (primary) AND every published command is `clamp_to_limits`'d to absolute joint limits (backstop). Never one alone.
- Absolute joint limits come from the B601-RS URDF (`rebotarm_bringup`); `b601_rs_limits.json` ships conservative defaults and is finalized from the URDF during on-bench bring-up.
- Tests run with `python3 -m pytest <path> -q -p no:anyio`. Full suite currently 221 passed.
- The live `rclpy` node + real arm move are on-bench, reported honestly (like M1's golden trace) — never unit-tested-as-passing.

---

### Task 1: `limits.py` — joint-limit safety clamp

**Files:**
- Create: `robot_b601/limits.py`, `robot_b601/b601_rs_limits.json`
- Test: `tests/b601/test_limits.py`

**Interfaces:**
- Produces: `JointLimits(lo: list[float], hi: list[float])` (each length 6); `DEFAULT_LIMITS`; `clamp_to_limits(joints, limits) -> (clamped: list[float], was_clamped: bool)`; `load_limits(path=None) -> JointLimits` (returns `DEFAULT_LIMITS` if path is None/missing).

- [ ] **Step 1: Write the failing test**

Create `tests/b601/test_limits.py`:

```python
from robot_b601.limits import JointLimits, DEFAULT_LIMITS, clamp_to_limits, load_limits

def test_in_range_unchanged():
    lim = JointLimits(lo=[-1.0]*6, hi=[1.0]*6)
    c, was = clamp_to_limits([0.5, -0.5, 0.0, 0.9, -0.9, 0.1], lim)
    assert c == [0.5, -0.5, 0.0, 0.9, -0.9, 0.1]
    assert was is False

def test_out_of_range_clamps_per_joint():
    lim = JointLimits(lo=[-1.0]*6, hi=[1.0]*6)
    c, was = clamp_to_limits([2.0, -2.0, 0.0, 5.0, -5.0, 0.5], lim)
    assert c == [1.0, -1.0, 0.0, 1.0, -1.0, 0.5]
    assert was is True

def test_default_limits_shape():
    assert len(DEFAULT_LIMITS.lo) == 6 and len(DEFAULT_LIMITS.hi) == 6
    assert all(lo < hi for lo, hi in zip(DEFAULT_LIMITS.lo, DEFAULT_LIMITS.hi))

def test_load_default_when_missing():
    assert load_limits("/no/such/file.json") is DEFAULT_LIMITS
    assert load_limits(None) is DEFAULT_LIMITS

def test_load_from_json(tmp_path):
    p = tmp_path / "l.json"
    p.write_text('{"lo": [-1,-1,-1,-1,-1,-1], "hi": [1,1,1,1,1,1]}')
    lim = load_limits(str(p))
    assert lim.lo == [-1.0]*6 and lim.hi == [1.0]*6
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/b601/test_limits.py -q -p no:anyio`
Expected: FAIL — `ModuleNotFoundError: robot_b601.limits`.

- [ ] **Step 3: Write the implementation**

Create `robot_b601/limits.py`:

```python
"""Joint-limit safety clamp for the real B601 arm. Pure + stdlib; the transport
clamps every command before it reaches the wire. Absolute limits come from the
B601-RS URDF (rebotarm_bringup); b601_rs_limits.json ships conservative defaults
until finalized on-bench."""
from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class JointLimits:
    lo: list          # length 6, radians
    hi: list


# Conservative full-range defaults (radians) until finalized from the URDF on-bench.
DEFAULT_LIMITS = JointLimits(lo=[-2.6] * 6, hi=[2.6] * 6)


def clamp_to_limits(joints, limits: JointLimits):
    clamped = []
    was_clamped = False
    for j, lo, hi in zip(joints, limits.lo, limits.hi):
        c = min(max(float(j), lo), hi)
        if c != j:
            was_clamped = True
        clamped.append(c)
    return clamped, was_clamped


def load_limits(path=None) -> JointLimits:
    if path is None or not os.path.exists(path):
        return DEFAULT_LIMITS
    d = json.loads(Path(path).read_text())
    return JointLimits(lo=[float(x) for x in d["lo"]],
                       hi=[float(x) for x in d["hi"]])
```

Create `robot_b601/b601_rs_limits.json`:

```json
{
  "_comment": "Conservative default B601-RS joint limits (radians). FINALIZE from the B601-RS URDF (rebotarm_bringup) during on-bench bring-up.",
  "lo": [-2.6, -2.6, -2.6, -2.6, -2.6, -2.6],
  "hi": [2.6, 2.6, 2.6, 2.6, 2.6, 2.6]
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m pytest tests/b601/test_limits.py -q -p no:anyio`
Expected: PASS (all 5)

- [ ] **Step 5: Commit**

```bash
git add robot_b601/limits.py robot_b601/b601_rs_limits.json tests/b601/test_limits.py
git commit -m "feat(b601): joint-limit safety clamp + conservative RS default limits"
```

---

### Task 2: `B601RosTransport` — real ROS 2 transport (rclpy deferred)

**Files:**
- Create: `robot_b601/ros_transport.py`
- Test: `tests/b601/test_ros_transport.py`

**Interfaces:**
- Consumes: `JointCommand`/`JointState` (M1 `robot_b601.transport`), `clamp_to_limits`/`load_limits`/`DEFAULT_LIMITS` (Task 1).
- Produces: pure helpers `_positions_from_cmd(cmd, limits) -> list[float]` (returns the CLAMPED 6 joint values), `_state_from_positions(positions, gripper) -> JointState`; class `B601RosTransport(command_topic="/rebotarm/joint_command", state_topic="/joint_states", limits=None)` implementing `B601Transport` (`publish(cmd)`, `latest()`), with `connect()` (deferred `rclpy`). `publish` before `connect` raises `RuntimeError`.

- [ ] **Step 1: Write the failing test**

Create `tests/b601/test_ros_transport.py`:

```python
import pytest
from robot_b601.transport import JointCommand, JointState
from robot_b601.limits import JointLimits

def test_module_imports_without_ros2():
    import robot_b601.ros_transport as rt      # rclpy is deferred; must import with no ROS 2
    assert hasattr(rt, "B601RosTransport")

def test_positions_from_cmd_clamps():
    from robot_b601.ros_transport import _positions_from_cmd
    lim = JointLimits(lo=[-1.0]*6, hi=[1.0]*6)
    out = _positions_from_cmd(JointCommand([2.0]*6, 0.0), lim)
    assert out == [1.0]*6                        # SAFETY: clamped before the wire

def test_state_from_positions_shape():
    from robot_b601.ros_transport import _state_from_positions
    st = _state_from_positions([0.1]*6, 0.03)
    assert isinstance(st, JointState)
    assert st.joint_positions == [0.1]*6 and st.gripper_position == 0.03

def test_publish_before_connect_raises():
    from robot_b601.ros_transport import B601RosTransport
    t = B601RosTransport()
    with pytest.raises(RuntimeError):
        t.publish(JointCommand([0.0]*6, 0.0))    # not connected -> refuse (no silent no-op)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/b601/test_ros_transport.py -q -p no:anyio`
Expected: FAIL — `ModuleNotFoundError: robot_b601.ros_transport`.

- [ ] **Step 3: Write the implementation**

Create `robot_b601/ros_transport.py`:

```python
"""Real B601-RS transport over ROS 2 — the hardware counterpart of M1's Isaac UDP
transport, behind the SAME B601Transport seam (so B601Node/B601Engine are unchanged).
rclpy + sensor_msgs are DEFERRED-imported (inside connect/_publish/_read) so this
module and its pure helpers import and test WITHOUT ROS 2. Every command is clamped to
joint limits before the wire (safety). The exact controller command topic/msg is
confirmed on-bench against rebotarm_bringup; the clamped-positions helper is not
affected by that choice."""
from __future__ import annotations

from robot_b601.limits import DEFAULT_LIMITS, clamp_to_limits
from robot_b601.transport import JointState


def _positions_from_cmd(cmd, limits) -> list:
    clamped, _ = clamp_to_limits(cmd.joint_positions, limits)
    return clamped


def _state_from_positions(positions, gripper) -> JointState:
    return JointState(joint_positions=list(positions), gripper_position=float(gripper))


class B601RosTransport:
    def __init__(self, command_topic: str = "/rebotarm/joint_command",
                 state_topic: str = "/joint_states", limits=None,
                 node_name: str = "b601_aspire"):
        self._cmd_topic = command_topic
        self._state_topic = state_topic
        self._limits = limits or DEFAULT_LIMITS
        self._node_name = node_name
        self._node = None
        self._pub = None
        self._latest_positions = None

    def connect(self) -> None:
        """Live only: bring up the rclpy node, command publisher, and /joint_states
        subscriber + spin thread. Confirm the command topic/controller interface here
        against rebotarm_bringup on-bench (position vs trajectory controller, gripper
        joint index) — this is the one on-bench-finalized detail."""
        import threading

        import rclpy
        from rclpy.node import Node
        from sensor_msgs.msg import JointState as RosJointState

        rclpy.init(args=None)
        self._node = Node(self._node_name)
        self._pub = self._node.create_publisher(RosJointState, self._cmd_topic, 10)

        def _on_state(msg):
            self._latest_positions = list(msg.position)

        self._node.create_subscription(RosJointState, self._state_topic, _on_state, 10)
        threading.Thread(target=rclpy.spin, args=(self._node,), daemon=True).start()

    def publish(self, cmd) -> None:
        positions = _positions_from_cmd(cmd, self._limits)     # SAFETY: clamp before wire
        if self._pub is None:
            raise RuntimeError(
                "B601RosTransport.connect() must be called before publish (live ROS 2 only)")
        from sensor_msgs.msg import JointState as RosJointState
        msg = RosJointState()
        msg.position = list(positions) + [float(cmd.gripper_position)]
        self._pub.publish(msg)

    def latest(self):
        p = self._latest_positions
        if p is None:
            return None
        # convention (confirm on-bench): first 6 = arm joints, last = gripper if present
        joints = list(p[:6])
        gripper = float(p[6]) if len(p) > 6 else 0.0
        return _state_from_positions(joints, gripper)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m pytest tests/b601/test_ros_transport.py -q -p no:anyio`
Expected: PASS (all 4) — the module imports with no ROS 2 (rclpy deferred), the clamp helper works, publish-before-connect refuses.

- [ ] **Step 5: Commit**

```bash
git add robot_b601/ros_transport.py tests/b601/test_ros_transport.py
git commit -m "feat(b601): B601RosTransport (real ROS 2, rclpy deferred) + clamp-before-wire"
```

---

### Task 3: `b601_real_first_light.py` — bounded runner + `--dry-run`

**Files:**
- Create: `scripts/b601_real_first_light.py`
- Test: `tests/b601/test_real_first_light.py`

**Interfaces:**
- Consumes: `B601RosTransport` (Task 2), `clamp_to_limits`/`load_limits` (Task 1), M1 `B601Node`/`B601Engine`/`RealClock`.
- Produces: `plan_waypoints(home, delta_max=0.15) -> list[list[float]]` (home → home+bounded delta → home); `run(transport, clock, delta_max=0.15) -> ExecuteResult`; a CLI: `--dry-run` prints the clamped planned waypoints (no ROS 2, no move) and exits 0; a live run connects `B601RosTransport`, reads current pose as home, and executes the bounded waypoints.

- [ ] **Step 1: Write the failing test**

Create `tests/b601/test_real_first_light.py`:

```python
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]

def test_dry_run_prints_waypoints_and_exits_zero():
    proc = subprocess.run(
        [sys.executable, "scripts/b601_real_first_light.py", "--dry-run"],
        capture_output=True, text=True, cwd=REPO)
    assert proc.returncode == 0, proc.stderr      # runs in CI with NO ROS 2 -> proves rclpy not imported on this path
    assert "waypoint" in proc.stdout.lower()

def test_plan_waypoints_are_bounded():
    sys.path.insert(0, str(REPO / "scripts"))
    import b601_real_first_light as fl
    home = [0.1, -0.2, 0.0, 0.3, -0.1, 0.2]
    wps = fl.plan_waypoints(home, delta_max=0.15)
    assert wps[0] == home and wps[-1] == home     # starts and ends at home
    for wp in wps:
        for h, j in zip(home, wp):
            assert abs(j - h) <= 0.15 + 1e-9       # every waypoint within delta_max of home
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/b601/test_real_first_light.py -q -p no:anyio`
Expected: FAIL — `scripts/b601_real_first_light.py` does not exist.

- [ ] **Step 3: Write the runner**

Create `scripts/b601_real_first_light.py`:

```python
#!/usr/bin/env python3
"""B601-RS real-hardware 'first light': drive the REAL arm through small bounded joint
waypoints via the ASPIRE engine, over ROS 2. --dry-run previews the CLAMPED waypoints
without ROS 2 or moving (always run this first).

SAFETY (real arm moves on a live run):
  * e-stop within reach; clear the workspace.
  * launch the vendor safe-park monitor: `ros2 run rebotarm_monitor_ros2 ...`.
  * bring up the controller: `ros2 launch rebotarm_bringup ...`.
  * finalize robot_b601/b601_rs_limits.json from the B601-RS URDF first.
Live use:
  ros2 ... (bringup + monitor); then
  python3 scripts/b601_real_first_light.py --limits robot_b601/b601_rs_limits.json
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from robot_b601.clock import RealClock
from robot_b601.engine import B601Engine
from robot_b601.limits import clamp_to_limits, load_limits
from robot_b601.node import B601Node


def plan_waypoints(home, delta_max: float = 0.15):
    """home -> home + a small bounded delta on all joints -> home. Deliberately gentle
    for first contact with a real arm; the limit clamp is the backstop."""
    bumped = [h + delta_max for h in home]
    return [list(home), bumped, list(home)]


def run(transport, clock, delta_max: float = 0.15):
    transport.connect()
    state = transport.latest()
    home = state.joint_positions if state is not None else [0.0] * 6
    node = B601Node(transport, clock=clock, home=home)
    eng = B601Engine(node, clock=clock)
    for wp in plan_waypoints(home, delta_max):
        eng.move_to_joints(wp)
    return eng.result()


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true",
                    help="preview clamped waypoints without ROS 2 or moving")
    ap.add_argument("--limits", default="robot_b601/b601_rs_limits.json")
    ap.add_argument("--delta-max", type=float, default=0.15)
    ap.add_argument("--command-topic", default="/rebotarm/joint_command")
    ap.add_argument("--state-topic", default="/joint_states")
    ap.add_argument("--out", default="b601_real_first_light_result.json")
    args = ap.parse_args(argv)

    limits = load_limits(args.limits)
    if args.dry_run:
        home = [0.0] * 6                          # nominal home for the preview
        print(f"[dry-run] limits lo={limits.lo} hi={limits.hi} delta_max={args.delta_max}")
        for i, wp in enumerate(plan_waypoints(home, args.delta_max)):
            clamped, was = clamp_to_limits(wp, limits)
            print(f"[dry-run] waypoint {i}: {clamped}  clamped={was}")
        print("[dry-run] no ROS 2 connection, no motion.")
        return 0

    from robot_b601.ros_transport import B601RosTransport   # deferred: live path only
    transport = B601RosTransport(command_topic=args.command_topic,
                                 state_topic=args.state_topic, limits=limits)
    res = run(transport, RealClock(), args.delta_max)
    Path(args.out).write_text(res.to_json())
    print(f"score={res.score} primitives={len(res.traces)} -> {args.out}")
    return 0 if res.score == 1.0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m pytest tests/b601/test_real_first_light.py -q -p no:anyio`
Expected: PASS (both) — `--dry-run` runs in CI without ROS 2 (proving the live import is deferred).

- [ ] **Step 5: Commit**

```bash
chmod +x scripts/b601_real_first_light.py
git add scripts/b601_real_first_light.py tests/b601/test_real_first_light.py
git commit -m "feat(b601): real-arm first-light runner — bounded waypoints + safety dry-run"
```

---

### Task 4: Full-suite gate + on-bench bring-up note + push

**Files:** none (verification only)

- [ ] **Step 1: Run the complete suite**

Run: `python3 -m pytest tests/ -q -p no:anyio`
Expected: PASS — prior 221 + the new `tests/b601/` M3a tests (~11).

- [ ] **Step 2: Confirm the safety dry-run end-to-end**

Run: `python3 scripts/b601_real_first_light.py --dry-run --limits robot_b601/b601_rs_limits.json`
Expected: exit 0; prints the 3 clamped waypoints (home, home+delta, home) and `no ROS 2 connection, no motion.`

- [ ] **Step 3: Push**

```bash
git push aspire_demo aspire_original_sim
```

- [ ] **Step 4: On-bench bring-up (LIVE — hardware present, done after merge, not a unit test)**

Record for the operator (do NOT run in CI):
1. Finalize `robot_b601/b601_rs_limits.json` from the B601-RS URDF (`rebotarm_bringup`).
2. `source` ROS 2; `ros2 launch rebotarm_bringup ...` (controller); `ros2 run rebotarm_monitor_ros2 ...` (safe-park). E-stop within reach; workspace clear.
3. `python3 scripts/b601_real_first_light.py --dry-run` — review clamped waypoints.
4. `python3 scripts/b601_real_first_light.py --limits robot_b601/b601_rs_limits.json` — the arm gently executes the bounded waypoints; confirm `/joint_states` convergence and the recorded trace. This is the honest live validation (like M1's golden trace).

---

## Self-review notes (spec coverage)

- Joint-limit safety clamp (pure, CI-tested) → Task 1 (`clamp_to_limits`, `DEFAULT_LIMITS`, `load_limits`, `b601_rs_limits.json`).
- `B601RosTransport` implementing the `B601Transport` seam, `rclpy` deferred, clamp-before-wire, publish-before-connect refuses → Task 2; pure helpers CI-tested.
- Bounded runner + `--dry-run` safety preview, reusing M1 `B601Node`/`B601Engine` → Task 3.
- Two independent safety bounds (small-delta-from-current + absolute-limit clamp) → Task 3 `plan_waypoints` (delta-from-home) + Task 1 clamp (applied in Task 2 `publish`).
- Vendor safe-park monitor + bring-up checklist → Task 3 runner docstring + Task 4 on-bench note.
- No `aspire/` changes; stdlib-only tested code; `rclpy`/`sensor_msgs` only in deferred imports → all tasks (CI has no ROS 2; the import-without-ros2 test guards it).
- **Known honest boundary:** the exact controller command topic/msg + gripper index are finalized on-bench against `rebotarm_bringup`; the URDF joint limits replace the conservative defaults there. Everything the ASPIRE engine depends on — the seam, the clamp, the bounded runner — is built and tested here without ROS 2. Same sim-first / live-integration split as M1.
- Spec used `b601_rs_limits.yaml`; this plan uses `b601_rs_limits.json` to keep `robot_b601` stdlib-only (PyYAML isn't stdlib) — a deliberate, flagged deviation.
```
