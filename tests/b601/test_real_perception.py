import numpy as np
import cv2
import pytest
from robot_b601.perception import CameraIntrinsics, RealPerceptionSource
from robot_b601.transforms import make_transform
from robot_b601.d405 import FakeD405, D405Frame
from robot_b601.tf_pose import FakeGripperPose


def _marker_frame(marker_id=7, px=200, pad=60):
    d = cv2.aruco.Dictionary_get(cv2.aruco.DICT_4X4_50)
    m = cv2.aruco.drawMarker(d, marker_id, px)
    side = px + 2 * pad
    img = np.full((side, side), 255, np.uint8)
    img[pad:pad + px, pad:pad + px] = m
    return cv2.cvtColor(img, cv2.COLOR_GRAY2BGR), side


def test_get_cube_pose_maps_detection_into_base_frame():
    color, side = _marker_frame()
    intr = CameraIntrinsics(600.0, 600.0, side / 2.0, side / 2.0)
    frame = D405Frame(color=color, depth=np.zeros((side, side), np.uint16), intrinsics=intr)
    T_gripper_base = make_transform(np.eye(3), [1.0, 0.0, 0.0])   # gripper at +1x in base
    src = RealPerceptionSource(camera=FakeD405(frame), tf=FakeGripperPose(T_gripper_base),
                               T_cam_gripper=np.eye(4), marker_size=0.05)
    pose = src.get_cube_pose()
    # camera & extrinsic identity, so base = gripper(+1x) offset applied to a frontal marker:
    assert abs(pose.x - 1.0) < 0.02      # +1x gripper offset carried through
    assert abs(pose.y) < 0.02
    assert pose.z > 0.0                   # marker was in front of the camera


def test_get_cube_pose_raises_when_no_marker():
    side = 320
    intr = CameraIntrinsics(600.0, 600.0, side / 2.0, side / 2.0)
    frame = D405Frame(color=np.full((side, side, 3), 255, np.uint8),
                      depth=np.zeros((side, side), np.uint16), intrinsics=intr)
    src = RealPerceptionSource(camera=FakeD405(frame), tf=FakeGripperPose(np.eye(4)),
                               T_cam_gripper=np.eye(4), marker_size=0.05)
    with pytest.raises(RuntimeError):
        src.get_cube_pose()
