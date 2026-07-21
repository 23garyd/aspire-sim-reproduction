"""Gripper-pose source for M3b. TfGripperPose reads gripper->base from ROS 2 TF (rclpy/
tf2_ros deferred inside connect()/lookup()) so this module imports with no ROS 2.
FakeGripperPose returns an injected 4x4 for CI. Frame names are confirmed on-bench against
rebotarm_bringup's URDF."""
from __future__ import annotations

import numpy as np

from robot_b601.transforms import make_transform


class FakeGripperPose:
    """Deterministic gripper pose for CI: lookup() returns the injected transform."""

    def __init__(self, T):
        self._T = np.asarray(T, float)

    def connect(self):
        pass

    def lookup(self, base_frame=None, gripper_frame=None) -> np.ndarray:
        return self._T


class TfGripperPose:
    """Live TF reader (on-bench). rclpy/tf2_ros imported in connect()/lookup()."""

    def __init__(self, base_frame: str = "base_link", gripper_frame: str = "tool0"):
        self.base_frame = base_frame
        self.gripper_frame = gripper_frame
        self._node = None
        self._buffer = None
        self._listener = None

    def connect(self):
        import rclpy
        import tf2_ros
        from rclpy.node import Node
        if not rclpy.ok():
            rclpy.init(args=None)
        self._node = Node("b601_tf_pose")
        self._buffer = tf2_ros.Buffer()
        self._listener = tf2_ros.TransformListener(self._buffer, self._node)

    def lookup(self, base_frame=None, gripper_frame=None) -> np.ndarray:
        if self._buffer is None:
            raise RuntimeError("TfGripperPose.connect() must be called before lookup()")
        import rclpy
        from rclpy.time import Time
        from scipy.spatial.transform import Rotation
        bf = base_frame or self.base_frame
        gf = gripper_frame or self.gripper_frame
        rclpy.spin_once(self._node, timeout_sec=0.5)
        tr = self._buffer.lookup_transform(bf, gf, Time())
        t, q = tr.transform.translation, tr.transform.rotation
        R = Rotation.from_quat([q.x, q.y, q.z, q.w]).as_matrix()
        return make_transform(R, [t.x, t.y, t.z])
