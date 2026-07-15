"""AimdkNode: synchronous blocking facade over async AimDK ROS2 joint topics.

ASPIRE's API is synchronous (`move_to_joints(j)` returns when the motion is done),
but AimDK is publish-command / subscribe-state. This node bridges the two: publish
the command, then poll joint state until it converges within tolerance or times out.
The returned status ("ok" | "TIMEOUT") is what ASPIRE's failure attribution keys on.
"""
from __future__ import annotations

from dataclasses import dataclass

from robot_engine.clock import RealClock
from robot_engine.ros_transport import JointCommand


@dataclass
class MoveResult:
    reached: bool
    residual: float
    status: str          # "ok" | "TIMEOUT"
    iterations: int


def _max_abs_diff(a: list[float], b: list[float]) -> float:
    return max(abs(x - y) for x, y in zip(a, b))


class AimdkNode:
    def __init__(self, transport, command_topic: str, state_topic: str,
                 num_joints: int, clock=None, poll_dt: float = 0.01):
        self._transport = transport
        self._command_topic = command_topic
        self._state_topic = state_topic
        self._num_joints = num_joints
        self._clock = clock or RealClock()
        self._poll_dt = poll_dt

    def move_to_joints(self, joints, tol: float = 1e-3,
                       timeout_s: float = 5.0) -> MoveResult:
        target = list(joints)
        t0 = self._clock.now()
        iterations = 0
        residual = float("inf")
        while True:
            # Restream the setpoint every iteration — joint-servo controllers hold
            # only briefly, so a single publish is not enough (cf. arm.py @50Hz).
            self._transport.publish(self._command_topic, JointCommand(positions=target))
            state = self._transport.latest(self._state_topic)
            iterations += 1
            if state is not None:
                residual = _max_abs_diff(state.positions, target)
            if residual < tol:
                return MoveResult(True, residual, "ok", iterations)
            if self._clock.now() - t0 >= timeout_s:
                return MoveResult(False, residual, "TIMEOUT", iterations)
            self._clock.sleep(self._poll_dt)
