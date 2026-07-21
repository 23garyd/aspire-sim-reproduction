"""B601Node: synchronous blocking facade over the B601Transport. Re-streams the full
setpoint (joints + gripper) every poll (servo controllers hold only briefly), reads
state, and converges within tol or times out on an injectable clock."""
from __future__ import annotations

from dataclasses import dataclass

from robot_b601.clock import RealClock
from robot_b601.transport import JointCommand


@dataclass
class MoveResult:
    reached: bool
    residual: float
    status: str          # "ok" | "TIMEOUT"
    iterations: int


class B601Node:
    def __init__(self, transport, num_joints: int = 6, clock=None,
                 poll_dt: float = 0.01, home=None):
        self._t = transport
        self._nj = num_joints
        self._clock = clock or RealClock()
        self._poll = poll_dt
        self._last_joints = list(home) if home is not None else [0.0] * num_joints
        self._last_grip = 0.0

    def _stream_until(self, residual_fn, tol, timeout_s) -> MoveResult:
        t0 = self._clock.now()
        iters = 0
        residual = float("inf")
        while True:
            self._t.publish(JointCommand(list(self._last_joints), self._last_grip))
            state = self._t.latest()
            iters += 1
            if state is not None:
                residual = residual_fn(state)
            if residual < tol:
                return MoveResult(True, residual, "ok", iters)
            if self._clock.now() - t0 >= timeout_s:
                return MoveResult(False, residual, "TIMEOUT", iters)
            self._clock.sleep(self._poll)

    def move_to_joints(self, joints, tol: float = 1e-2, timeout_s: float = 5.0) -> MoveResult:
        self._last_joints = list(joints)
        return self._stream_until(
            lambda st: max(abs(a - b) for a, b in zip(st.joint_positions, self._last_joints)),
            tol, timeout_s)

    def set_gripper(self, pos: float, tol: float = 1e-2, timeout_s: float = 2.0) -> MoveResult:
        self._last_grip = float(pos)
        return self._stream_until(
            lambda st: abs(st.gripper_position - self._last_grip),
            tol, timeout_s)
