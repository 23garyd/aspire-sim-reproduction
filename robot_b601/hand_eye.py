"""Eye-in-hand hand-eye calibration for the B601-RS + D405. Detect a fixed ChArUco board
in the wrist camera, pair each detection with the gripper pose in base (from TF), and solve
cv2.calibrateHandEye for the fixed camera->gripper transform. Load/save the result with
fail-loud validation. cv2/numpy; no camera or ROS I/O here. OpenCV 4.5.4 aruco API."""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np

from robot_b601.perception import CameraIntrinsics
from robot_b601.transforms import make_transform

CHARUCO_DICT = cv2.aruco.DICT_4X4_50


@dataclass(frozen=True)
class CharucoBoard:
    squares_x: int = 5
    squares_y: int = 7
    square_length: float = 0.03     # metres
    marker_length: float = 0.022    # metres
    dict_id: int = CHARUCO_DICT

    def cv(self):
        dictionary = cv2.aruco.Dictionary_get(self.dict_id)
        board = cv2.aruco.CharucoBoard_create(
            self.squares_x, self.squares_y,
            self.square_length, self.marker_length, dictionary)
        return board, dictionary


def detect_charuco_pose(frame, board: CharucoBoard, intrinsics: CameraIntrinsics):
    """Return T_target_cam (4x4) for the ChArUco board, or None if too few corners."""
    cv_board, dictionary = board.cv()
    params = cv2.aruco.DetectorParameters_create()
    corners, ids, _ = cv2.aruco.detectMarkers(frame, dictionary, parameters=params)
    if ids is None:
        return None
    retval, ch_corners, ch_ids = cv2.aruco.interpolateCornersCharuco(
        corners, ids, frame, cv_board)
    if not retval or retval < 4:
        return None
    ok, rvec, tvec = cv2.aruco.estimatePoseCharucoBoard(
        ch_corners, ch_ids, cv_board, intrinsics.matrix(), np.zeros(5), None, None)
    if not ok:
        return None
    R, _ = cv2.Rodrigues(rvec)
    return make_transform(R, tvec)


@dataclass
class HandEyeSample:
    T_target_cam: np.ndarray     # board pose in camera
    T_gripper_base: np.ndarray   # gripper pose in base


def solve_hand_eye(samples, method=cv2.CALIB_HAND_EYE_PARK) -> np.ndarray:
    """Return T_cam_gripper (camera pose in gripper, 4x4) from >=3 samples."""
    if len(samples) < 3:
        raise ValueError(f"hand-eye calibration needs >=3 samples, got {len(samples)}")
    R_g2b = [np.asarray(s.T_gripper_base, float)[:3, :3] for s in samples]
    t_g2b = [np.asarray(s.T_gripper_base, float)[:3, 3] for s in samples]
    R_t2c = [np.asarray(s.T_target_cam, float)[:3, :3] for s in samples]
    t_t2c = [np.asarray(s.T_target_cam, float)[:3, 3] for s in samples]
    R_c2g, t_c2g = cv2.calibrateHandEye(R_g2b, t_g2b, R_t2c, t_t2c, method=method)
    return make_transform(R_c2g, t_c2g)


def calibration_residual(samples, T_cam_gripper) -> float:
    """Mean spread (metres) of the board's position in base across samples. For a perfect
    calibration the board is stationary in base, so the spread is the residual."""
    T_cam_gripper = np.asarray(T_cam_gripper, float)
    bases = []
    for s in samples:
        T_base_target = (np.asarray(s.T_gripper_base, float)
                         @ T_cam_gripper @ np.asarray(s.T_target_cam, float))
        bases.append(T_base_target[:3, 3])
    bases = np.array(bases)
    return float(np.mean(np.linalg.norm(bases - bases.mean(axis=0), axis=1)))


def save_extrinsic(path, T) -> None:
    Path(path).write_text(json.dumps(
        {"T_cam_gripper": np.asarray(T, float).tolist()}, indent=2))


def load_extrinsic(path=None) -> np.ndarray:
    """Load T_cam_gripper (4x4). Missing/None -> identity (uncalibrated). Fail-loud on a
    malformed matrix: must be 4x4 with an orthonormal rotation block."""
    if path is None or not Path(path).exists():
        return np.eye(4)
    T = np.array(json.loads(Path(path).read_text())["T_cam_gripper"], float)
    if T.shape != (4, 4):
        raise ValueError(f"hand_eye extrinsic must be 4x4, got {T.shape}")
    R = T[:3, :3]
    if (not np.allclose(R @ R.T, np.eye(3), atol=1e-3)
            or not np.isclose(np.linalg.det(R), 1.0, atol=1e-3)):
        raise ValueError("hand_eye extrinsic rotation block is not orthonormal")
    return T
