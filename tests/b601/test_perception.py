import numpy as np
import cv2
from robot_b601.perception import CameraIntrinsics, detect_cube_pose


def _marker_frame(marker_id=7, px=200, pad=60):
    """White frame (quiet zone) with a DICT_4X4_50 marker centered in it."""
    d = cv2.aruco.Dictionary_get(cv2.aruco.DICT_4X4_50)
    m = cv2.aruco.drawMarker(d, marker_id, px)
    side = px + 2 * pad
    img = np.full((side, side), 255, np.uint8)
    img[pad:pad + px, pad:pad + px] = m
    return cv2.cvtColor(img, cv2.COLOR_GRAY2BGR), side


def _intr(side):
    return CameraIntrinsics(fx=600.0, fy=600.0, cx=side / 2.0, cy=side / 2.0)


def test_detect_cube_pose_returns_pose_in_front_of_camera():
    frame, side = _marker_frame(marker_id=7)
    T = detect_cube_pose(frame, _intr(side), marker_size=0.05, marker_id=7)
    assert T is not None
    assert T.shape == (4, 4)
    assert T[2, 3] > 0                      # marker is in front of the camera (z > 0)
    assert abs(T[0, 3]) < 0.02 and abs(T[1, 3]) < 0.02   # centered -> x,y ~ 0


def test_detect_cube_pose_none_when_marker_absent():
    blank = np.full((320, 320, 3), 255, np.uint8)
    assert detect_cube_pose(blank, _intr(320), marker_size=0.05) is None


def test_detect_cube_pose_none_when_wrong_id():
    frame, side = _marker_frame(marker_id=3)      # a different id in view
    assert detect_cube_pose(frame, _intr(side), marker_size=0.05, marker_id=7) is None
