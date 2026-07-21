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
        target, _ = clamp_gripper(pos, self._glim)   # clamp before any real command
        # on-bench: send `target` (the CLAMPED value) to the vendor gripper controller --
        # never the raw pos -- this clamp is what closes the gripper-crush hazard.
        raise NotImplementedError(f"on-bench: command vendor gripper to {target}")

    def gripper_position(self) -> float:
        self._require_connected()
        raise NotImplementedError("on-bench: read /joint_states gripper")

    def ee_pose(self) -> EePose:
        self._require_connected()
        raise NotImplementedError("on-bench: read TF base->tool")

    def reset(self) -> None:
        self._require_connected()
        raise NotImplementedError("on-bench: home the arm + open gripper")
