"""B601 transport seam: the ASPIRE facade talks to an abstract B601Transport, so it
runs against a deterministic FakeB601Transport in tests and a live UDP transport
against Isaac (or, later, real RS hardware). Same interface either way."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable


@dataclass
class JointCommand:
    joint_positions: list[float]     # radians, 6 joints
    gripper_position: float          # meters


@dataclass
class JointState:
    joint_positions: list[float]
    gripper_position: float


@runtime_checkable
class B601Transport(Protocol):
    def publish(self, cmd: JointCommand) -> None: ...
    def latest(self) -> "JointState | None": ...


class FakeB601Transport:
    """Deterministic robot model: closes a fixed fraction of the gap to the last
    commanded target on every state read. gap_close=0.0 models a stuck arm."""

    def __init__(self, num_joints: int = 6, gap_close: float = 0.34,
                 start: list[float] | None = None):
        self.num_joints = num_joints
        self.gap_close = gap_close
        self._cur = list(start) if start is not None else [0.0] * num_joints
        self._tgt = list(self._cur)
        self._grip_cur = 0.0
        self._grip_tgt = 0.0

    def publish(self, cmd: JointCommand) -> None:
        self._tgt = list(cmd.joint_positions)
        self._grip_tgt = float(cmd.gripper_position)

    def latest(self) -> JointState:
        self._cur = [c + self.gap_close * (t - c) for c, t in zip(self._cur, self._tgt)]
        self._grip_cur += self.gap_close * (self._grip_tgt - self._grip_cur)
        return JointState(joint_positions=list(self._cur), gripper_position=self._grip_cur)
