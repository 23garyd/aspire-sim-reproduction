# B601 Milestone 3c — real cube-lift on hardware Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Run the cube-lift task on the real B601-RS — real perception localizes the cube, the arm reaches (vendor IK) → grasps → lifts, success judged proprioceptively — as a drop-in ASPIRE task through the unchanged `b601_execute` capx contract.

**Architecture:** A `MotionBackend` seam (`FakeMotionBackend` models the EE + gripper for CI; `RealMotionBackend` drives vendor MoveIt2/IK over ROS 2 on-bench) plus pure grasp/lift evaluators and a gripper-limit clamp. A new `RealCubeLiftEnv` composes a backend + a perception source + the evaluators behind the same primitive namespace as M2's `FakeCubeLiftEnv`, so `b601_execute` and the whole pipeline drive it unchanged. Task logic is CI-tested with fakes; IK/motion is on-bench behind deferred imports.

**Tech Stack:** Python 3, stdlib + numpy (CI-tested code). Deferred/on-bench: `rclpy` + vendor MoveIt2/IK (in `RealMotionBackend`). Reuses M2 `CubePose`/`TraceRecord`/`b601_execute`, M3a `limits`/`node`/`look_pose`, M3b `RealPerceptionSource`/`tf_pose`.

## Global Constraints

- **Deferred heavy imports:** `rclpy` and the vendor IK are imported ONLY inside `RealMotionBackend.connect()`/methods. `import robot_b601.motion`, `import robot_b601.task`, and `import robot_b601.grasp` MUST succeed with no `rclpy` (absent-safe). `robot_b601/task.py` stays stdlib+numpy at import scope (the Real backend/perception/d405/tf_pose imports live inside the real branch of the env factory).
- **`FakeCubeLiftEnv` and every existing test stay UNCHANGED — the full suite (270) must stay green.** M3c is additive: a new `RealCubeLiftEnv` beside the Fake, not a rewrite.
- **`aspire/` is unchanged.** `RealCubeLiftEnv` mirrors the M2 primitive namespace (`get_cube_pose`, `move_to_pose`, `set_gripper`, `open_gripper`, `close_gripper`) and the `namespace()`/`success()`/`traces()` contract so `b601_execute` and `aspire.run` are untouched beyond env selection.
- **Config is JSON, not YAML.** The spec named `cube_lift.yaml`; this plan uses `cube_lift_fake.json` (+ a documented real variant) so the engine stays on stdlib `json` (no PyYAML import in `b601_execute`) — a deliberate, flagged deviation matching `b601_rs_limits.json`/`hand_eye.json`.
- **Proprioceptive success:** `success = grasp_detected(gripper_position) AND ee_pose().z > lift_threshold`. Grasp detection is position-based (a commanded close that stalls open by ≥ the object width). No force/current sensing.
- **Gripper safety:** `set_gripper` clamps to gripper limits (the deferred M3a/M3b gripper-clamp item, closed here). Real joint moves go through `move_to_look_pose` (gripper-held, fail-loud).
- **Test command (REQUIRED flag):** `python3 -m pytest <path> -q -p no:anyio`. Run the full b601 suite `python3 -m pytest tests/b601/ -q -p no:anyio` before each commit.
- **Work from** `/home/demo/aspire_robot_engine` on branch `aspire_original_sim`.

---

### Task 1: Gripper limits — extend `robot_b601/limits.py`

**Files:**
- Modify: `robot_b601/limits.py` (append; do not change existing `JointLimits`/`clamp_to_limits`/`load_limits`)
- Test: `tests/b601/test_gripper_limits.py`

**Interfaces:**
- Produces: `GripperLimits(lo: float, hi: float)`; `DEFAULT_GRIPPER_LIMITS = GripperLimits(0.0, 0.08)`; `clamp_gripper(pos, limits) -> (clamped: float, was_clamped: bool)`; `load_gripper_limits(path=None) -> GripperLimits` (missing/None or missing keys → default; inverted lo>hi → `ValueError`).

- [ ] **Step 1: Write the failing test**

Create `tests/b601/test_gripper_limits.py`:

```python
import pytest
from robot_b601.limits import (GripperLimits, DEFAULT_GRIPPER_LIMITS,
                               clamp_gripper, load_gripper_limits)


def test_clamp_gripper_in_range_unchanged():
    lim = GripperLimits(lo=0.0, hi=0.08)
    c, was = clamp_gripper(0.03, lim)
    assert c == 0.03 and was is False


def test_clamp_gripper_over_and_under():
    lim = GripperLimits(lo=0.0, hi=0.08)
    assert clamp_gripper(0.5, lim) == (0.08, True)
    assert clamp_gripper(-0.2, lim) == (0.0, True)


def test_default_gripper_limits_shape():
    assert DEFAULT_GRIPPER_LIMITS.lo == 0.0 and DEFAULT_GRIPPER_LIMITS.hi == 0.08


def test_load_gripper_limits_default_when_missing(tmp_path):
    assert load_gripper_limits(None) == DEFAULT_GRIPPER_LIMITS
    assert load_gripper_limits("/no/such.json") == DEFAULT_GRIPPER_LIMITS
    p = tmp_path / "nogrip.json"
    p.write_text('{"lo": [0], "hi": [1]}')            # no grip_lo/grip_hi keys
    assert load_gripper_limits(p) == DEFAULT_GRIPPER_LIMITS


def test_load_gripper_limits_from_json(tmp_path):
    p = tmp_path / "g.json"
    p.write_text('{"grip_lo": 0.0, "grip_hi": 0.05}')
    assert load_gripper_limits(p) == GripperLimits(lo=0.0, hi=0.05)


def test_load_gripper_limits_inverted_raises(tmp_path):
    p = tmp_path / "bad.json"
    p.write_text('{"grip_lo": 0.05, "grip_hi": 0.0}')
    with pytest.raises(ValueError):
        load_gripper_limits(p)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/b601/test_gripper_limits.py -q -p no:anyio`
Expected: FAIL — `ImportError: cannot import name 'GripperLimits'`.

- [ ] **Step 3: Append to `robot_b601/limits.py`**

Add at the end of `robot_b601/limits.py` (leave everything above unchanged):

```python
@dataclass(frozen=True)
class GripperLimits:
    lo: float          # fully-closed position (metres)
    hi: float          # fully-open position (metres)


# Conservative default gripper stroke (metres) until finalized on-bench.
DEFAULT_GRIPPER_LIMITS = GripperLimits(lo=0.0, hi=0.08)


def clamp_gripper(pos, limits: GripperLimits):
    """Clamp a gripper command into [lo, hi] so set_gripper can never over-travel/crush."""
    c = min(max(float(pos), limits.lo), limits.hi)
    return c, (c != pos)


def load_gripper_limits(path=None) -> GripperLimits:
    """Gripper limits from a b601 config JSON (keys grip_lo/grip_hi). Missing file or
    missing keys -> conservative default; inverted lo>hi -> fail loud."""
    if path is None or not os.path.exists(path):
        return DEFAULT_GRIPPER_LIMITS
    d = json.loads(Path(path).read_text())
    if "grip_lo" not in d or "grip_hi" not in d:
        return DEFAULT_GRIPPER_LIMITS
    lo, hi = float(d["grip_lo"]), float(d["grip_hi"])
    if lo > hi:
        raise ValueError("b601 gripper limits inverted: grip_lo > grip_hi")
    return GripperLimits(lo=lo, hi=hi)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m pytest tests/b601/test_gripper_limits.py -q -p no:anyio`
Expected: PASS (6 tests).

- [ ] **Step 5: Commit**

```bash
git add robot_b601/limits.py tests/b601/test_gripper_limits.py
git commit -m "feat(b601): gripper-limit clamp (closes deferred gripper-clamp item) (M3c)"
```

---

### Task 2: `grasp.py` — grasp + lift evaluators

**Files:**
- Create: `robot_b601/grasp.py`
- Test: `tests/b601/test_grasp.py`

**Interfaces:**
- Produces: `grasp_detected(gripper_pos, closed_ref, min_object_open) -> bool`; `lifted(ee_z, lift_threshold) -> bool`; `cube_lift_success(grasped, ee_z, lift_threshold) -> bool`.

- [ ] **Step 1: Write the failing test**

Create `tests/b601/test_grasp.py`:

```python
from robot_b601.grasp import grasp_detected, lifted, cube_lift_success


def test_grasp_detected_when_gripper_stalls_open():
    # closed_ref 0.0, need >= 0.01 open to count as an object; gripper stalled at 0.03
    assert grasp_detected(0.03, closed_ref=0.0, min_object_open=0.01) is True


def test_no_grasp_when_gripper_fully_closes():
    assert grasp_detected(0.0, closed_ref=0.0, min_object_open=0.01) is False
    assert grasp_detected(0.005, closed_ref=0.0, min_object_open=0.01) is False


def test_lifted_threshold():
    assert lifted(0.17, 0.10) is True
    assert lifted(0.05, 0.10) is False


def test_cube_lift_success_needs_both():
    assert cube_lift_success(True, 0.17, 0.10) is True
    assert cube_lift_success(False, 0.17, 0.10) is False    # not grasped
    assert cube_lift_success(True, 0.05, 0.10) is False     # not lifted
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/b601/test_grasp.py -q -p no:anyio`
Expected: FAIL — `ModuleNotFoundError: robot_b601.grasp`.

- [ ] **Step 3: Write the implementation**

Create `robot_b601/grasp.py`:

```python
"""Proprioceptive grasp + lift evaluation for the B601 real cube-lift (M3c). Pure; no
hardware. Grasp is inferred from the gripper stalling open on an object; lift from the
end-effector height (both read from real feedback on-bench, from the fake model in CI)."""
from __future__ import annotations


def grasp_detected(gripper_pos, closed_ref, min_object_open) -> bool:
    """True if, after a commanded close, the gripper stalled open by at least
    min_object_open above the fully-closed reference -- i.e. an object is between the
    fingers. A gripper that reaches (near) closed_ref grasped nothing."""
    return (float(gripper_pos) - float(closed_ref)) >= float(min_object_open)


def lifted(ee_z, lift_threshold) -> bool:
    return float(ee_z) > float(lift_threshold)


def cube_lift_success(grasped, ee_z, lift_threshold) -> bool:
    return bool(grasped) and lifted(ee_z, lift_threshold)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m pytest tests/b601/test_grasp.py -q -p no:anyio`
Expected: PASS (4 tests).

- [ ] **Step 5: Commit**

```bash
git add robot_b601/grasp.py tests/b601/test_grasp.py
git commit -m "feat(b601): proprioceptive grasp + lift evaluators (M3c)"
```

---

### Task 3: `motion.py` — the `MotionBackend` seam (Fake + Real stub)

**Files:**
- Create: `robot_b601/motion.py`
- Test: `tests/b601/test_motion_fake.py`

**Interfaces:**
- Consumes: `robot_b601.node.MoveResult` (`MoveResult(reached, residual, status, iterations)`), `robot_b601.limits.{GripperLimits, DEFAULT_GRIPPER_LIMITS, clamp_gripper}` (Task 1).
- Produces: `EePose(x,y,z,roll=0,pitch=0,yaw=0)`; a `MotionBackend` Protocol (`move_to_pose`, `move_to_joints`, `set_gripper`, `gripper_position`, `ee_pose`, `reset`); `FakeMotionBackend(gripper_limits=DEFAULT_GRIPPER_LIMITS, start_ee=(0.0,0.0,0.30), start_grip=0.08, object_xyz=None, object_width=0.0, grasp_tol=0.03)`; `RealMotionBackend(gripper_limits=DEFAULT_GRIPPER_LIMITS, base_frame="base_link", gripper_frame="tool0")` (deferred `rclpy`; methods before `connect()` raise `RuntimeError`).

- [ ] **Step 1: Write the failing test**

Create `tests/b601/test_motion_fake.py`:

```python
import importlib
import pytest
from robot_b601.motion import EePose, FakeMotionBackend
from robot_b601.limits import GripperLimits


def test_move_to_pose_sets_ee():
    m = FakeMotionBackend()
    m.move_to_pose(0.4, 0.1, 0.2)
    ee = m.ee_pose()
    assert (round(ee.x, 3), round(ee.y, 3), round(ee.z, 3)) == (0.4, 0.1, 0.2)


def test_set_gripper_clamps_to_limits():
    m = FakeMotionBackend(gripper_limits=GripperLimits(0.0, 0.08))
    m.set_gripper(0.5)                     # over-open
    assert m.gripper_position() == 0.08
    m.set_gripper(-0.2)                    # over-closed
    assert m.gripper_position() == 0.0


def test_gripper_stalls_on_object_when_ee_near_it():
    # object 3cm wide at (0.4,0,0.02); closing at the object stalls the gripper at 0.03
    m = FakeMotionBackend(object_xyz=(0.4, 0.0, 0.02), object_width=0.03, grasp_tol=0.03)
    m.move_to_pose(0.4, 0.0, 0.02)         # EE at the object
    m.set_gripper(0.0)                     # command fully closed
    assert m.gripper_position() == 0.03    # stalled on the object


def test_gripper_fully_closes_when_ee_far_from_object():
    m = FakeMotionBackend(object_xyz=(0.4, 0.0, 0.02), object_width=0.03, grasp_tol=0.03)
    m.move_to_pose(0.0, 0.0, 0.30)         # EE far away
    m.set_gripper(0.0)
    assert m.gripper_position() == 0.0     # nothing to stall on


def test_reset_restores_start_state():
    m = FakeMotionBackend(start_ee=(0.0, 0.0, 0.30), start_grip=0.08)
    m.move_to_pose(0.4, 0.1, 0.2)
    m.set_gripper(0.0)
    m.reset()
    assert m.ee_pose().z == 0.30 and m.gripper_position() == 0.08


def test_motion_module_imports_without_rclpy():
    mod = importlib.import_module("robot_b601.motion")     # rclpy deferred in RealMotionBackend
    assert hasattr(mod, "RealMotionBackend") and hasattr(mod, "FakeMotionBackend")


def test_real_backend_before_connect_raises():
    from robot_b601.motion import RealMotionBackend
    with pytest.raises(RuntimeError):
        RealMotionBackend().move_to_pose(0.4, 0.0, 0.02)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/b601/test_motion_fake.py -q -p no:anyio`
Expected: FAIL — `ModuleNotFoundError: robot_b601.motion`.

- [ ] **Step 3: Write the implementation**

Create `robot_b601/motion.py`:

```python
"""MotionBackend seam for the B601 real cube-lift (M3c). The task calls Cartesian/gripper
primitives through a backend: FakeMotionBackend is a deterministic model (CI, no
hardware); RealMotionBackend drives the vendor MoveIt2/IK over ROS 2 (on-bench, rclpy
deferred). Swapping the backend swaps sim<->real; the task logic above is unchanged."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from robot_b601.limits import DEFAULT_GRIPPER_LIMITS, GripperLimits, clamp_gripper
from robot_b601.node import MoveResult


@dataclass
class EePose:
    x: float
    y: float
    z: float
    roll: float = 0.0
    pitch: float = 0.0
    yaw: float = 0.0


class MotionBackend(Protocol):
    def move_to_pose(self, x, y, z, roll=0.0, pitch=0.0, yaw=0.0) -> MoveResult: ...
    def move_to_joints(self, joints) -> MoveResult: ...
    def set_gripper(self, pos) -> MoveResult: ...
    def gripper_position(self) -> float: ...
    def ee_pose(self) -> EePose: ...
    def reset(self) -> None: ...


class FakeMotionBackend:
    """Deterministic motion model for CI. move_to_pose sets the EE directly (IK assumed to
    solve). set_gripper clamps to gripper limits; if a graspable object is configured and
    the EE is within grasp_tol of it, a commanded close stalls the gripper at object_width
    (modelling the fingers meeting the object) so grasp detection has a realistic reading."""

    def __init__(self, gripper_limits: GripperLimits = DEFAULT_GRIPPER_LIMITS,
                 start_ee=(0.0, 0.0, 0.30), start_grip=0.08,
                 object_xyz=None, object_width=0.0, grasp_tol=0.03):
        self._glim = gripper_limits
        self._start_ee = tuple(start_ee)
        self._start_grip = float(start_grip)
        self._object_xyz = tuple(object_xyz) if object_xyz is not None else None
        self._object_width = float(object_width)
        self._grasp_tol = float(grasp_tol)
        self.reset()

    def reset(self) -> None:
        self._ee = EePose(*self._start_ee)
        self._grip = self._start_grip

    def move_to_pose(self, x, y, z, roll=0.0, pitch=0.0, yaw=0.0) -> MoveResult:
        self._ee = EePose(float(x), float(y), float(z),
                          float(roll), float(pitch), float(yaw))
        return MoveResult(reached=True, residual=0.0, status="ok", iterations=1)

    def move_to_joints(self, joints) -> MoveResult:
        return MoveResult(reached=True, residual=0.0, status="ok", iterations=1)

    def set_gripper(self, pos) -> MoveResult:
        target, _ = clamp_gripper(pos, self._glim)
        if self._object_xyz is not None:
            ox, oy, oz = self._object_xyz
            d = ((self._ee.x - ox) ** 2 + (self._ee.y - oy) ** 2
                 + (self._ee.z - oz) ** 2) ** 0.5
            if d <= self._grasp_tol and target < self._object_width:
                target = self._object_width          # fingers meet the object -> stall
        self._grip = target
        return MoveResult(reached=True, residual=0.0, status="ok", iterations=1)

    def gripper_position(self) -> float:
        return self._grip

    def ee_pose(self) -> EePose:
        return self._ee


class RealMotionBackend:
    """Live backend (on-bench). move_to_pose sends the Cartesian goal to the vendor
    MoveIt2/IK over ROS 2 and executes; joint moves go through the M3a transport via the
    gripper-safe move_to_look_pose; gripper_position/ee_pose read /joint_states + TF.
    rclpy + the vendor IK client are imported in connect(). INTENTIONAL live-only stub:
    the exact vendor IK service/action and TF frames are finalized on-bench (like M1's
    bridge). Not unit-tested (needs ROS 2 + arm)."""

    def __init__(self, gripper_limits: GripperLimits = DEFAULT_GRIPPER_LIMITS,
                 base_frame="base_link", gripper_frame="tool0"):
        self._glim = gripper_limits
        self._base_frame = base_frame
        self._gripper_frame = gripper_frame
        self._connected = False

    def connect(self) -> None:
        import rclpy                                  # noqa: F401  (deferred; on-bench)
        # TODO(on-bench): init rclpy; create the vendor MoveIt2/IK client and the
        # gripper action client; build B601RosTransport + B601Node + TfGripperPose.
        raise NotImplementedError(
            "RealMotionBackend.connect() is finalized on-bench against rebotarm_bringup "
            "(vendor MoveIt2/IK service + gripper controller + TF frames).")

    def _require_connected(self):
        if not self._connected:
            raise RuntimeError("RealMotionBackend.connect() must be called before use")

    def move_to_pose(self, x, y, z, roll=0.0, pitch=0.0, yaw=0.0) -> MoveResult:
        self._require_connected()
        raise NotImplementedError("on-bench: vendor IK move_to_pose")

    def move_to_joints(self, joints) -> MoveResult:
        self._require_connected()
        raise NotImplementedError("on-bench: move_to_look_pose via B601Node")

    def set_gripper(self, pos) -> MoveResult:
        self._require_connected()
        clamp_gripper(pos, self._glim)               # clamp before any real command
        raise NotImplementedError("on-bench: vendor gripper controller")

    def gripper_position(self) -> float:
        self._require_connected()
        raise NotImplementedError("on-bench: read /joint_states gripper")

    def ee_pose(self) -> EePose:
        self._require_connected()
        raise NotImplementedError("on-bench: read TF base->tool")

    def reset(self) -> None:
        self._require_connected()
        raise NotImplementedError("on-bench: home the arm + open gripper")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m pytest tests/b601/test_motion_fake.py -q -p no:anyio`
Expected: PASS (7 tests). `import robot_b601.motion` succeeds with no `rclpy`; `RealMotionBackend().move_to_pose(...)` raises `RuntimeError` (not connected) before any deferred import.

- [ ] **Step 5: Commit**

```bash
git add robot_b601/motion.py tests/b601/test_motion_fake.py
git commit -m "feat(b601): MotionBackend seam — FakeMotionBackend + RealMotionBackend stub (M3c)"
```

---

### Task 4: `RealCubeLiftEnv` + `FakeCubePerception` in `robot_b601/task.py`

**Files:**
- Modify: `robot_b601/task.py` (append; leave `CubePose`/`FakeCubeLiftEnv`/`IsaacCubeLiftEnv` unchanged)
- Test: `tests/b601/test_real_cube_lift.py`

**Interfaces:**
- Consumes: `robot_b601.motion.FakeMotionBackend`, `robot_b601.grasp.{grasp_detected, cube_lift_success}`, `robot_b601.task.CubePose`, `aspire.schemas.TraceRecord` (already imported in task.py for the M2 envs).
- Produces: `FakeCubePerception(cube: CubePose)` with `get_cube_pose() -> CubePose`; `RealCubeLiftEnv(motion, perception, lift_threshold=0.10, closed_ref=0.0, min_object_open=0.01, close_pos=0.0, open_pos=0.08)` with `reset(seed)`, `get_cube_pose()`, `move_to_pose(x,y,z,roll=0,pitch=0,yaw=0)`, `set_gripper(pos)`, `open_gripper()`, `close_gripper()`, `namespace()`, `success()`, `traces()`.

- [ ] **Step 1: Write the failing test**

Create `tests/b601/test_real_cube_lift.py`:

```python
from robot_b601.task import RealCubeLiftEnv, FakeCubePerception, CubePose
from robot_b601.motion import FakeMotionBackend
from robot_b601.limits import GripperLimits


def _env(cube=(0.40, 0.0, 0.02)):
    c = CubePose(*cube)
    motion = FakeMotionBackend(gripper_limits=GripperLimits(0.0, 0.08),
                               object_xyz=cube, object_width=0.03, grasp_tol=0.03)
    return RealCubeLiftEnv(motion, FakeCubePerception(c), lift_threshold=0.10,
                           closed_ref=0.0, min_object_open=0.01,
                           close_pos=0.0, open_pos=0.08), c


def _run(env, ns):
    """A correct reach->grasp->lift program against the primitive namespace."""
    c = ns["get_cube_pose"]()
    ns["open_gripper"]()
    ns["move_to_pose"](c.x, c.y, c.z + 0.10)
    ns["move_to_pose"](c.x, c.y, c.z)
    ns["close_gripper"]()
    ns["move_to_pose"](c.x, c.y, c.z + 0.15)


def test_correct_program_lifts():
    env, _ = _env()
    env.reset(0)
    _run(env, env.namespace())
    assert env.success() is True


def test_noop_program_fails():
    env, _ = _env()
    env.reset(0)
    env.namespace()["get_cube_pose"]()          # perceive only, never move/grasp
    assert env.success() is False


def test_close_far_from_cube_does_not_grasp():
    env, c = _env()
    env.reset(0)
    ns = env.namespace()
    ns["move_to_pose"](0.0, 0.0, 0.30)          # nowhere near the cube
    ns["close_gripper"]()
    ns["move_to_pose"](0.0, 0.0, 0.30)
    assert env.success() is False               # gripper fully closed -> no grasp


def test_set_gripper_over_limit_is_clamped_no_crash():
    env, _ = _env()
    env.reset(0)
    env.namespace()["set_gripper"](0.5)         # over-open -> clamped by the backend
    assert env.motion.gripper_position() == 0.08


def test_primitives_emit_traces():
    env, _ = _env()
    env.reset(0)
    _run(env, env.namespace())
    fns = [t.function for t in env.traces()]
    assert "get_cube_pose" in fns and "move_to_pose" in fns and "set_gripper" in fns


def test_reset_clears_state_between_seeds():
    env, _ = _env()
    env.reset(0)
    _run(env, env.namespace())
    assert env.success() is True
    env.reset(1)                                # fresh seed: grasp + traces cleared, EE homed
    assert env.success() is False and env.traces() == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/b601/test_real_cube_lift.py -q -p no:anyio`
Expected: FAIL — `ImportError: cannot import name 'RealCubeLiftEnv'`.

- [ ] **Step 3: Append to `robot_b601/task.py`**

Add at the end of `robot_b601/task.py` (do not modify anything above). It uses `CubePose` and `TraceRecord`, both already defined/imported in that file:

```python
from dataclasses import dataclass as _dataclass

from robot_b601.grasp import cube_lift_success, grasp_detected
from robot_b601.motion import FakeMotionBackend


@_dataclass
class FakeCubePerception:
    """A get_cube_pose source that returns a fixed modeled cube (CI / fake-backed runs)."""
    cube: CubePose

    def get_cube_pose(self) -> CubePose:
        return self.cube


class RealCubeLiftEnv:
    """Real cube-lift task: a MotionBackend + a perception get_cube_pose source + the
    proprioceptive grasp/lift evaluators, behind the SAME primitive namespace as
    FakeCubeLiftEnv so b601_execute/aspire.run drive it unchanged. success = grasp
    detected (gripper stalled on the object) AND EE lifted above lift_threshold.
    reset(seed) re-homes the backend and clears traces; it does NOT move the physical
    cube (perception re-reads wherever it is) -- the seed is logged only."""

    def __init__(self, motion, perception, lift_threshold: float = 0.10,
                 closed_ref: float = 0.0, min_object_open: float = 0.01,
                 close_pos: float = 0.0, open_pos: float = 0.08):
        self.motion = motion
        self.perception = perception
        self.lift_threshold = lift_threshold
        self.closed_ref = closed_ref
        self.min_object_open = min_object_open
        self.close_pos = close_pos
        self.open_pos = open_pos
        self.reset(0)

    def reset(self, seed: int) -> None:
        self._seed = seed
        self.grasped = False
        self._traces: list = []
        self.motion.reset()

    def _trace(self, function: str, args: dict, summary: str) -> None:
        self._traces.append(TraceRecord(step=len(self._traces), function=function,
                                        args=args, status="ok", result_summary=summary,
                                        duration_ms=0.0, media=[]))

    def get_cube_pose(self) -> CubePose:
        c = self.perception.get_cube_pose()
        self._trace("get_cube_pose", {}, f"cube=({c.x:.3f},{c.y:.3f},{c.z:.3f})")
        return c

    def move_to_pose(self, x, y, z, roll=0.0, pitch=0.0, yaw=0.0) -> str:
        self.motion.move_to_pose(x, y, z, roll, pitch, yaw)
        self._trace("move_to_pose", {"x": x, "y": y, "z": z}, f"ee=({x:.3f},{y:.3f},{z:.3f})")
        return "ok"

    def set_gripper(self, pos) -> str:
        self.motion.set_gripper(pos)
        gp = self.motion.gripper_position()
        if pos <= self.close_pos + 1e-9:                 # a close -> evaluate grasp
            self.grasped = grasp_detected(gp, self.closed_ref, self.min_object_open)
        elif pos >= self.open_pos - 1e-9:                # an open -> release
            self.grasped = False
        self._trace("set_gripper", {"pos": pos}, f"grip={gp:.3f} grasped={self.grasped}")
        return "ok"

    def open_gripper(self) -> str:
        return self.set_gripper(self.open_pos)

    def close_gripper(self) -> str:
        return self.set_gripper(self.close_pos)

    def namespace(self) -> dict:
        return {"get_cube_pose": self.get_cube_pose, "move_to_pose": self.move_to_pose,
                "set_gripper": self.set_gripper, "open_gripper": self.open_gripper,
                "close_gripper": self.close_gripper}

    def success(self) -> bool:
        return cube_lift_success(self.grasped, self.motion.ee_pose().z, self.lift_threshold)

    def traces(self) -> list:
        return list(self._traces)


def build_real_cube_lift_env(cfg: dict):
    """Build a RealCubeLiftEnv from a config dict. backend=='fake' -> FakeMotionBackend +
    FakeCubePerception (CI/deterministic); otherwise the real, on-bench backend +
    D405 perception (deferred imports)."""
    from robot_b601.limits import GripperLimits
    glim = GripperLimits(lo=float(cfg.get("grip_lo", 0.0)), hi=float(cfg.get("grip_hi", 0.08)))
    kwargs = dict(lift_threshold=float(cfg.get("lift_threshold", 0.10)),
                  closed_ref=float(cfg.get("closed_ref", 0.0)),
                  min_object_open=float(cfg.get("min_object_open", 0.01)),
                  close_pos=glim.lo, open_pos=glim.hi)
    if cfg.get("backend", "real") == "fake":
        cc = cfg["cube"]
        cube = CubePose(float(cc["x"]), float(cc["y"]), float(cc["z"]))
        motion = FakeMotionBackend(gripper_limits=glim, object_xyz=(cube.x, cube.y, cube.z),
                                   object_width=float(cfg.get("object_width", 0.03)),
                                   grasp_tol=float(cfg.get("grasp_tol", 0.03)))
        perception = FakeCubePerception(cube)
        return RealCubeLiftEnv(motion, perception, **kwargs)
    # Real, on-bench path (deferred imports: hardware + ROS 2 only here).
    from robot_b601.motion import RealMotionBackend
    from robot_b601.perception import RealPerceptionSource
    from robot_b601.d405 import D405Camera
    from robot_b601.tf_pose import TfGripperPose
    from robot_b601.hand_eye import load_extrinsic
    motion = RealMotionBackend(gripper_limits=glim,
                               base_frame=cfg.get("base_frame", "base_link"),
                               gripper_frame=cfg.get("gripper_frame", "tool0"))
    motion.connect()
    camera = D405Camera(); camera.connect()
    tf = TfGripperPose(base_frame=cfg.get("base_frame", "base_link"),
                       gripper_frame=cfg.get("gripper_frame", "tool0")); tf.connect()
    perception = RealPerceptionSource(camera=camera, tf=tf,
                                      T_cam_gripper=load_extrinsic(cfg.get("extrinsic",
                                                                          "robot_b601/hand_eye.json")),
                                      marker_size=float(cfg.get("marker_size", 0.03)))
    return RealCubeLiftEnv(motion, perception, **kwargs)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m pytest tests/b601/test_real_cube_lift.py -q -p no:anyio`
Expected: PASS (6 tests). Also confirm `python3 -c "import robot_b601.task"` still imports with no rclpy (the real branch of `build_real_cube_lift_env` is the only place that touches hardware, and it is not reached at import time).

- [ ] **Step 5: Commit**

```bash
git add robot_b601/task.py tests/b601/test_real_cube_lift.py
git commit -m "feat(b601): RealCubeLiftEnv (MotionBackend + perception + grasp/lift) (M3c)"
```

---

### Task 5: Wire `RealCubeLiftEnv` into `b601_execute` + config + baseline + pipeline test

**Files:**
- Modify: `scripts/b601_execute.py` (only `_build_env`; leave `run_episode`/`main` logic intact)
- Create: `runs/2026-07-21-b601-real-cube-lift/cube_lift_fake.json` (fake-backed config)
- Create: `runs/2026-07-21-b601-real-cube-lift/baseline_lift.py` (correct baseline program)
- Test: `tests/b601/test_b601_execute_real.py`, `tests/b601/test_pipeline_integration_real.py`

**Interfaces:**
- Consumes: `robot_b601.task.build_real_cube_lift_env` (Task 4), the existing `run_episode`/capx contract.
- Produces: `b601_execute --config-path <cfg.json>` builds a `RealCubeLiftEnv` (fake or real backend per the config's `backend` field); `--selftest`/no config still builds `FakeCubeLiftEnv` (unchanged).

- [ ] **Step 1: Write the failing test**

Create `tests/b601/test_b601_execute_real.py`:

```python
import json
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
CFG = REPO / "runs" / "2026-07-21-b601-real-cube-lift" / "cube_lift_fake.json"
BASELINE = REPO / "runs" / "2026-07-21-b601-real-cube-lift" / "baseline_lift.py"


def test_real_env_fake_backend_scores_one(tmp_path):
    out = tmp_path / "out"
    proc = subprocess.run(
        [sys.executable, "scripts/b601_execute.py", "--program", str(BASELINE),
         "--seeds", "0,1,2", "--out-dir", str(out), "--config-path", str(CFG)],
        capture_output=True, text=True, cwd=REPO)
    assert proc.returncode == 0, proc.stderr
    result = json.loads((out / "result.json").read_text())
    assert result["score"] == 1.0                 # correct baseline lifts on every seed
    assert len(result["traces"]) > 0


def test_selftest_still_uses_fake_cube_lift_env(tmp_path):
    out = tmp_path / "out2"
    proc = subprocess.run(
        [sys.executable, "scripts/b601_execute.py", "--program", str(BASELINE),
         "--seeds", "0,1", "--out-dir", str(out), "--selftest"],
        capture_output=True, text=True, cwd=REPO)
    assert proc.returncode == 0, proc.stderr      # --selftest path unchanged, still runs
```

Create `tests/b601/test_pipeline_integration_real.py` (mirror `tests/b601/test_pipeline_integration.py`, but drive the real env via the fake-backed config so no LLM/hardware is needed):

```python
import json
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
BASE = REPO / "runs" / "2026-07-21-b601-real-cube-lift"
CORRECT = (BASE / "baseline_lift.py").read_text()


def test_real_cube_lift_drives_aspire_pipeline_no_llm(tmp_path):
    task = tmp_path / "robosuite" / "cube_lift"
    task.mkdir(parents=True)
    (task / "code.py").write_text(CORRECT)          # a passing baseline -> no actor called
    capx_cmd = (f"{sys.executable} {REPO}/scripts/b601_execute.py "
                f"--config-path {BASE / 'cube_lift_fake.json'}")
    proc = subprocess.run(
        [sys.executable, "-m", "aspire.run", "--task-dir", str(task),
         "--engine", "capx", "--capx-cmd", capx_cmd,
         "--out-root", str(tmp_path / "exec"), "--library", str(tmp_path / "lib"),
         "--s-dbg", "0,1,2", "--s-val", "100-104"],
        capture_output=True, text=True, cwd=REPO)
    assert proc.returncode == 0, proc.stderr
    summary = json.loads(proc.stdout.strip().splitlines()[-1])
    assert summary["stage_reached"] == "validated"
    assert summary["val_score"] == 1.0            # correct baseline lifts on all held-out seeds
    assert "claude" not in proc.stderr.lower()    # no LLM: a passing baseline never calls the actor
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/b601/test_b601_execute_real.py -q -p no:anyio`
Expected: FAIL — the config/baseline files and the real-env selection do not exist yet (FileNotFoundError / IsaacCubeLiftEnv SystemExit).

- [ ] **Step 3: Create the config and baseline, and switch `_build_env`**

Create `runs/2026-07-21-b601-real-cube-lift/cube_lift_fake.json`:

```json
{
  "backend": "fake",
  "cube": {"x": 0.40, "y": 0.00, "z": 0.02},
  "lift_threshold": 0.10,
  "grasp_tol": 0.03,
  "object_width": 0.03,
  "closed_ref": 0.0,
  "min_object_open": 0.01,
  "grip_lo": 0.0,
  "grip_hi": 0.08
}
```

Create `runs/2026-07-21-b601-real-cube-lift/baseline_lift.py`:

```python
# Correct B601 cube-lift baseline: perceive -> approach -> descend -> grasp -> lift.
c = get_cube_pose()
open_gripper()
move_to_pose(c.x, c.y, c.z + 0.10)
move_to_pose(c.x, c.y, c.z)
close_gripper()
move_to_pose(c.x, c.y, c.z + 0.15)
```

In `scripts/b601_execute.py`, replace the `_build_env` function body (leave the rest of the file unchanged):

```python
def _build_env(args):
    if args.selftest or not args.config_path:
        return FakeCubeLiftEnv()
    cfg = json.loads(Path(args.config_path).read_text())
    from robot_b601.task import build_real_cube_lift_env   # deferred: real deps only here
    return build_real_cube_lift_env(cfg)
```

(The module already imports `json` and `Path`. Remove the now-unused `IsaacCubeLiftEnv` import that lived inside the old `_build_env`; do not import `IsaacCubeLiftEnv` anymore. Update the module docstring's last sentence to say a real `--config-path` builds `RealCubeLiftEnv` (fake or on-bench backend) instead of `IsaacCubeLiftEnv`.)

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m pytest tests/b601/test_b601_execute_real.py tests/b601/test_pipeline_integration_real.py -q -p no:anyio`
Expected: PASS (3 tests) — the fake-backed real env scores 1.0 for the correct baseline, `--selftest` still works, and the real env reaches `validated` (val 1.0) through the ASPIRE pipeline with no actor/LLM.

- [ ] **Step 5: Commit**

```bash
git add scripts/b601_execute.py runs/2026-07-21-b601-real-cube-lift/ \
        tests/b601/test_b601_execute_real.py tests/b601/test_pipeline_integration_real.py
git commit -m "feat(b601): RealCubeLiftEnv drives b601_execute + ASPIRE pipeline (fake-backed CI) (M3c)"
```

---

### Task 6: Full-suite gate + on-bench bring-up note + push

**Files:** none (verification only)

- [ ] **Step 1: Run the complete suite**

Run: `python3 -m pytest tests/ -q -p no:anyio`
Expected: PASS — prior 270 + the new M3c tests (~26 across the 6 new test files); FakeCubeLiftEnv and all M2 tests still green.

- [ ] **Step 2: Confirm the real env imports with no hardware**

Run: `python3 -c "import robot_b601.motion, robot_b601.grasp, robot_b601.task; print('import OK')"`
Expected: prints `import OK` (no rclpy needed; the real backend/perception imports are inside `build_real_cube_lift_env`'s real branch, not reached at import).

- [ ] **Step 3: Push**

```bash
git push aspire_demo aspire_original_sim
```

- [ ] **Step 4: On-bench real cube-lift (LIVE — hardware present, after merge, not a unit test)**

Record for the operator (do NOT run in CI):
1. Complete M3b calibration first (`robot_b601/hand_eye.json` written; residual small).
2. Author `runs/2026-07-21-b601-real-cube-lift/cube_lift_real.json` = the fake config with `"backend": "real"`, plus measured `grip_lo`/`grip_hi`, `min_object_open` (object width), `marker_size`, and `base_frame`/`gripper_frame` confirmed against `rebotarm_bringup`'s URDF. Finalize `RealMotionBackend.connect()`/methods against the vendor MoveIt2/IK service + gripper controller (the on-bench TODOs).
3. `source` ROS 2; `ros2 launch rebotarm_bringup …` + MoveIt2 + `ros2 run rebotarm_monitor_ros2 …` (safe-park); e-stop in reach; workspace clear; connect the D405; place the marked cube on the table.
4. `python3 scripts/b601_execute.py --program runs/2026-07-21-b601-real-cube-lift/baseline_lift.py --seeds 0 --out-dir /tmp/m3c --config-path runs/2026-07-21-b601-real-cube-lift/cube_lift_real.json` — the arm perceives, reaches (vendor IK), grasps, lifts; `result.json` score reflects the real lift. Honest live validation, like M1's golden trace.

---

## Self-review notes (spec coverage)

- Gripper limits / clamp (closes the deferred gripper-clamp) → Task 1 (`GripperLimits`, `clamp_gripper`, `load_gripper_limits`).
- Proprioceptive grasp + lift evaluators → Task 2 (`grasp_detected`, `lifted`, `cube_lift_success`).
- `MotionBackend` seam (Fake CI model with grasp-stall; Real vendor-IK-over-ROS 2 stub, rclpy deferred) → Task 3.
- `RealCubeLiftEnv` (backend + perception + evaluators, M2 primitive namespace/contract) + `FakeCubePerception` + `build_real_cube_lift_env` factory → Task 4.
- `b601_execute` real-env selection (replaces the `IsaacCubeLiftEnv` stub) + JSON config + correct baseline + result.json test + the deterministic full-pipeline test (validated, no LLM) → Task 5.
- Sim-first / live split: all tested code stdlib+numpy; rclpy/vendor-IK deferred; real path on-bench → Tasks 3/4 (deferred-import guards) + Task 6 note.
- `FakeCubeLiftEnv` + M2 tests unchanged; `aspire/` unchanged; 270 stay green → Global Constraints + Task 6 gate.
- **Deliberate deviations (flagged):** config is `cube_lift_fake.json` (JSON) not the spec's `.yaml` (keeps the engine on stdlib `json`); the `IsaacCubeLiftEnv` stub is superseded by `RealCubeLiftEnv` as the config-selected env (RS-hardware target, per the spec's "not carried forward").
- **On-bench-finalized (honest boundary):** exact vendor MoveIt2/IK interface + TF frames; gripper limit values + fully-closed reference + object width; approach/lift heights + grasp_tol → Task 3 `RealMotionBackend` TODOs + Task 6 note.
