"""Pure numpy/scipy 4x4 homogeneous transform helpers for B601 M3b perception.

Convention (object-first, matching the variable names used throughout): T_x_y is the
pose of x expressed in frame y -- equivalently, the 4x4 that maps a point in frame x
into frame y. So T_cube_cam is the cube expressed in the camera, T_cam_gripper the
camera expressed in the gripper, T_gripper_base the gripper expressed in the base.
Chaining is object-first: T_cube_cam then T_cam_gripper then T_gripper_base yields the
cube expressed in the base. Keep this ordering when editing compose() calls.
No cv2, no I/O -- the numeric core the perception/calibration code composes."""
from __future__ import annotations

import numpy as np
from scipy.spatial.transform import Rotation

from robot_b601.task import CubePose


def make_transform(R, t) -> np.ndarray:
    """Build a 4x4 from a 3x3 rotation R and a length-3 translation t."""
    T = np.eye(4)
    T[:3, :3] = np.asarray(R, float)
    T[:3, 3] = np.asarray(t, float).reshape(3)
    return T


def compose(*mats) -> np.ndarray:
    """Left-to-right matrix product: compose(A, B, C) == A @ B @ C."""
    out = np.eye(4)
    for m in mats:
        out = out @ np.asarray(m, float)
    return out


def invert(T) -> np.ndarray:
    """Exact inverse of a rigid 4x4: (R^T, -R^T t)."""
    T = np.asarray(T, float)
    R, t = T[:3, :3], T[:3, 3]
    Ti = np.eye(4)
    Ti[:3, :3] = R.T
    Ti[:3, 3] = -R.T @ t
    return Ti


def cube_base_pose(T_cube_cam, T_cam_gripper, T_gripper_base) -> CubePose:
    """Move a cube pose seen in the CAMERA frame into the ARM/BASE frame.
    T_cube_base (cube expressed in base) = T_gripper_base @ T_cam_gripper @ T_cube_cam
    -- the object-first chain cube->cam->gripper->base (see the module docstring)."""
    T = compose(T_gripper_base, T_cam_gripper, T_cube_cam)
    x, y, z = T[:3, 3]
    qx, qy, qz, qw = Rotation.from_matrix(T[:3, :3]).as_quat()
    return CubePose(float(x), float(y), float(z),
                    float(qx), float(qy), float(qz), float(qw))
