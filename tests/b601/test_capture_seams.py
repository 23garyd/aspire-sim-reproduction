import importlib
import numpy as np
import pytest
from robot_b601.perception import CameraIntrinsics


def test_d405_module_imports_without_pyrealsense2():
    m = importlib.import_module("robot_b601.d405")          # pyrealsense2 is absent here
    assert hasattr(m, "D405Camera") and hasattr(m, "FakeD405")


def test_fake_d405_returns_injected_frame():
    from robot_b601.d405 import FakeD405, D405Frame
    fr = D405Frame(color=np.zeros((4, 4, 3), np.uint8), depth=np.zeros((4, 4), np.uint16),
                   intrinsics=CameraIntrinsics(1, 1, 2, 2))
    cam = FakeD405(fr)
    cam.connect()
    assert cam.capture() is fr


def test_real_d405_capture_before_connect_raises():
    from robot_b601.d405 import D405Camera
    with pytest.raises(RuntimeError):
        D405Camera().capture()


def test_tf_pose_module_imports_without_ros():
    m = importlib.import_module("robot_b601.tf_pose")
    assert hasattr(m, "TfGripperPose") and hasattr(m, "FakeGripperPose")


def test_fake_gripper_pose_returns_injected_transform():
    from robot_b601.tf_pose import FakeGripperPose
    T = np.eye(4); T[0, 3] = 0.5
    g = FakeGripperPose(T)
    g.connect()
    assert np.allclose(g.lookup("base_link", "tool0"), T)


def test_tf_pose_lookup_before_connect_raises():
    from robot_b601.tf_pose import TfGripperPose
    with pytest.raises(RuntimeError):
        TfGripperPose().lookup()
