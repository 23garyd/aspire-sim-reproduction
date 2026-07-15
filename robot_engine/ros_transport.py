"""ROS transport abstraction.

The AimdkNode facade talks to an abstract RosTransport, not rclpy directly, so it
can run against a FakeRosTransport in tests. The real implementation (RclpyTransport)
wraps publishers/subscribers and a background executor spin thread; it is a drop-in
that satisfies the same interface.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable


@dataclass
class JointCommand:
    positions: list[float]


@dataclass
class JointState:
    positions: list[float]


@runtime_checkable
class RosTransport(Protocol):
    def publish(self, topic: str, msg: object) -> None: ...
    def latest(self, topic: str) -> object | None: ...


class FakeRosTransport:
    """Models a robot that closes a fixed fraction of the joint-space gap to its
    last commanded target on every state read. Deterministic; no threads.

    gap_close=0.0 models a stuck robot (never converges -> exercises TIMEOUT).
    """

    def __init__(self, num_joints: int, gap_close: float = 0.34,
                 start: list[float] | None = None):
        self.num_joints = num_joints
        self.gap_close = gap_close
        self._current = list(start) if start is not None else [0.0] * num_joints
        self._target = list(self._current)

    def publish(self, topic: str, msg: JointCommand) -> None:
        self._target = list(msg.positions)

    def latest(self, topic: str) -> JointState:
        # Advance toward target, then report. Side-effecting getter is acceptable
        # for a fake and keeps convergence tied deterministically to poll count.
        self._current = [c + self.gap_close * (t - c)
                         for c, t in zip(self._current, self._target)]
        return JointState(positions=list(self._current))
