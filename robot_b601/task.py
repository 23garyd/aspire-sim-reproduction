"""B601 cube-lift task. FakeCubeLiftEnv is a deterministic Cartesian model (no Isaac,
no physics): a correct reach->grasp->lift program succeeds, a no-op or wrong-pose
program fails, so the reward is meaningful and the whole engine contract is testable
without Isaac. IsaacCubeLiftEnv (below) is the live, on-box counterpart.

Simplification (honest): grasp = gripper closes within grasp_tol of the cube; while
grasped the cube follows the EE; success = final cube height > lift_threshold. Real
grasp physics is Isaac-only."""
from __future__ import annotations

import random
from dataclasses import dataclass

from aspire.schemas import TraceRecord


@dataclass
class CubePose:
    x: float
    y: float
    z: float
    qx: float = 0.0
    qy: float = 0.0
    qz: float = 0.0
    qw: float = 1.0


class FakeCubeLiftEnv:
    def __init__(self, grasp_tol: float = 0.03, lift_threshold: float = 0.10,
                 table_z: float = 0.0, cube_xy=(0.4, 0.0)):
        self.grasp_tol = grasp_tol
        self.lift_threshold = lift_threshold
        self.table_z = table_z
        self._cube_xy = cube_xy
        self.reset(0)

    def reset(self, seed: int) -> None:
        rng = random.Random(seed)                      # seed-deterministic cube pose
        dx = (rng.random() - 0.5) * 0.10
        dy = (rng.random() - 0.5) * 0.10
        self.cube = CubePose(self._cube_xy[0] + dx, self._cube_xy[1] + dy, self.table_z)
        self.ee = [0.0, 0.0, 0.30]
        self.grip = 0.04
        self.grasped = False
        self._traces: list[TraceRecord] = []

    def _trace(self, function: str, args: dict, summary: str) -> None:
        self._traces.append(TraceRecord(step=len(self._traces), function=function,
                                        args=args, status="ok", result_summary=summary,
                                        duration_ms=0.0, media=[]))

    def get_cube_pose(self) -> CubePose:
        self._trace("get_cube_pose", {}, f"cube=({self.cube.x:.3f},{self.cube.y:.3f},{self.cube.z:.3f})")
        return self.cube

    def move_to_pose(self, x, y, z, roll=0.0, pitch=0.0, yaw=0.0) -> str:
        self.ee = [float(x), float(y), float(z)]
        if self.grasped:
            self.cube = CubePose(float(x), float(y), float(z))   # cube rides the EE
        self._trace("move_to_pose", {"x": x, "y": y, "z": z}, f"ee=({x:.3f},{y:.3f},{z:.3f})")
        return "ok"

    def set_gripper(self, pos: float) -> str:
        self.grip = float(pos)
        if pos < 0.02 and not self.grasped:            # closing
            d = ((self.ee[0] - self.cube.x) ** 2 + (self.ee[1] - self.cube.y) ** 2
                 + (self.ee[2] - self.cube.z) ** 2) ** 0.5
            if d <= self.grasp_tol:
                self.grasped = True
        self._trace("set_gripper", {"pos": pos}, f"grip={pos} grasped={self.grasped}")
        return "ok"

    def open_gripper(self) -> str:
        return self.set_gripper(0.04)

    def close_gripper(self) -> str:
        return self.set_gripper(0.0)

    def namespace(self) -> dict:
        return {"get_cube_pose": self.get_cube_pose, "move_to_pose": self.move_to_pose,
                "set_gripper": self.set_gripper, "open_gripper": self.open_gripper,
                "close_gripper": self.close_gripper}

    def success(self) -> bool:
        return self.grasped and self.cube.z > self.lift_threshold

    def traces(self) -> list:
        return list(self._traces)
