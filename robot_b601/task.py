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


class IsaacCubeLiftEnv:
    """Live, on-box cube-lift in Isaac Sim (RS USD). Spawns the cube, drives move_to_pose
    via the vendor IK sender -> M1 B601Node -> the :5005/:5006 bridge, and reads real
    ground-truth cube pose + physics grasp/lift. INTENTIONAL live-only stub: Isaac imports
    are deferred and the real ArticulationView/cube-spawn API is finalized on the box
    (M1 b601_isaac_bridge.py is the motion reference; only cube spawn + ground-truth read
    are added here). Not unit-tested (needs Isaac)."""

    def __init__(self, config_path: str):
        self._config_path = config_path
        raise SystemExit(
            "IsaacCubeLiftEnv is finalized on the box (needs Isaac + ISAACSIM_ROOT). "
            "TODO(on-box): load cube_lift.yaml; spawn the cube USD into the RS scene; "
            "implement get_cube_pose from the cube prim's world transform; route "
            "move_to_pose through IK -> B601Node.move_to_joints; success = cube prim "
            "world-z > lift_threshold. namespace()/success()/traces() mirror "
            "FakeCubeLiftEnv exactly so b601_execute is unchanged.")


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
