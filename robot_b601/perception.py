"""D405 cube detection: find the cube's ArUco marker and return its pose in the CAMERA
frame (T_cube_cam, 4x4). cv2 only; takes a frame array in (no camera I/O), so a synthetic
frame tests it. Uses the OpenCV 4.5.4 aruco API. RealPerceptionSource (Task 5) composes
this into the arm frame."""
from __future__ import annotations

from dataclasses import dataclass

import cv2
import numpy as np

from robot_b601.transforms import make_transform, cube_base_pose

ARUCO_DICT = cv2.aruco.DICT_4X4_50


@dataclass(frozen=True)
class CameraIntrinsics:
    fx: float
    fy: float
    cx: float
    cy: float

    def matrix(self) -> np.ndarray:
        return np.array([[self.fx, 0.0, self.cx],
                         [0.0, self.fy, self.cy],
                         [0.0, 0.0, 1.0]])


def detect_cube_pose(color, intrinsics: CameraIntrinsics, marker_size: float,
                     marker_id: int = 7, dict_id: int = ARUCO_DICT):
    """Return T_cube_cam (4x4) for the cube's ArUco marker, or None if that id is not seen.
    marker_size is the marker side length in metres."""
    dictionary = cv2.aruco.Dictionary_get(dict_id)
    params = cv2.aruco.DetectorParameters_create()
    corners, ids, _ = cv2.aruco.detectMarkers(color, dictionary, parameters=params)
    if ids is None:
        return None
    id_list = ids.ravel().tolist()
    if marker_id not in id_list:
        return None
    i = id_list.index(marker_id)
    rvecs, tvecs, _ = cv2.aruco.estimatePoseSingleMarkers(
        [corners[i]], marker_size, intrinsics.matrix(), np.zeros(5))
    R, _ = cv2.Rodrigues(rvecs[0][0])
    return make_transform(R, tvecs[0][0])


@dataclass
class RealPerceptionSource:
    """Compose a live D405 capture + the calibrated extrinsic + gripper TF into a real
    arm-frame get_cube_pose(). camera and tf are duck-typed (D405Camera/FakeD405 and
    TfGripperPose/FakeGripperPose)."""
    camera: object
    tf: object
    T_cam_gripper: np.ndarray
    marker_size: float
    marker_id: int = 7
    base_frame: str = "base_link"
    gripper_frame: str = "tool0"

    def get_cube_pose(self):
        frame = self.camera.capture()
        T_cube_cam = detect_cube_pose(frame.color, frame.intrinsics,
                                      self.marker_size, self.marker_id)
        if T_cube_cam is None:
            raise RuntimeError("no cube ArUco marker detected in the D405 frame")
        T_gripper_base = self.tf.lookup(self.base_frame, self.gripper_frame)
        return cube_base_pose(T_cube_cam, self.T_cam_gripper, T_gripper_base)
