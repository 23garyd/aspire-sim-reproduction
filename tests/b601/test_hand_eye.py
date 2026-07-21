import numpy as np
import cv2
import pytest
from scipy.spatial.transform import Rotation
from robot_b601.transforms import make_transform, invert
from robot_b601.perception import CameraIntrinsics
from robot_b601.hand_eye import (
    CharucoBoard, detect_charuco_pose,
    HandEyeSample, solve_hand_eye, calibration_residual,
    save_extrinsic, load_extrinsic,
)


def test_detect_charuco_pose_on_rendered_board():
    board = CharucoBoard()
    cv_board, _ = board.cv()
    img = cv2.cvtColor(cv_board.draw((500, 700)), cv2.COLOR_GRAY2BGR)
    intr = CameraIntrinsics(600.0, 600.0, 250.0, 350.0)
    T = detect_charuco_pose(img, board, intr)
    assert T is not None and T.shape == (4, 4)
    assert T[2, 3] > 0                       # board is in front of the camera


def test_detect_charuco_pose_none_on_blank():
    board = CharucoBoard()
    intr = CameraIntrinsics(600.0, 600.0, 250.0, 350.0)
    blank = np.full((700, 500, 3), 255, np.uint8)
    assert detect_charuco_pose(blank, board, intr) is None


def _rigid(rng):
    return make_transform(Rotation.random(random_state=rng).as_matrix(),
                          rng.uniform(-0.3, 0.3, 3))


def _synth_samples(T_cam_gripper_true, n=12, seed=0):
    rng = np.random.RandomState(seed)
    T_base_target = _rigid(rng)                       # board fixed in base
    samples = []
    for _ in range(n):
        T_gripper_base = _rigid(rng)
        T_cam_base = T_gripper_base @ T_cam_gripper_true      # camera in base
        T_target_cam = invert(T_cam_base) @ T_base_target     # board in camera
        samples.append(HandEyeSample(T_target_cam, T_gripper_base))
    return samples


def test_solve_hand_eye_recovers_known_extrinsic():
    rng = np.random.RandomState(42)
    T_true = _rigid(rng)
    samples = _synth_samples(T_true)
    T_est = solve_hand_eye(samples)
    assert np.allclose(T_est[:3, :3], T_true[:3, :3], atol=1e-3)
    assert np.allclose(T_est[:3, 3], T_true[:3, 3], atol=1e-3)


def test_residual_small_for_consistent_large_for_corrupted():
    rng = np.random.RandomState(7)
    T_true = _rigid(rng)
    samples = _synth_samples(T_true)
    assert calibration_residual(samples, T_true) < 1e-6
    samples[0].T_target_cam[:3, 3] += [0.1, 0.0, 0.0]        # corrupt one sample
    assert calibration_residual(samples, T_true) > 1e-3


def test_solve_hand_eye_rejects_too_few_samples():
    with pytest.raises(ValueError):
        solve_hand_eye([])


def test_extrinsic_save_load_round_trip(tmp_path):
    rng = np.random.RandomState(3)
    T = _rigid(rng)
    p = tmp_path / "he.json"
    save_extrinsic(p, T)
    assert np.allclose(load_extrinsic(p), T, atol=1e-12)


def test_load_extrinsic_default_identity_when_missing():
    assert np.allclose(load_extrinsic(None), np.eye(4))
    assert np.allclose(load_extrinsic("/no/such/he.json"), np.eye(4))


def test_load_extrinsic_fail_loud_on_bad_shape(tmp_path):
    p = tmp_path / "bad.json"
    p.write_text('{"T_cam_gripper": [[1,0,0],[0,1,0],[0,0,1]]}')     # 3x3, not 4x4
    with pytest.raises(ValueError):
        load_extrinsic(p)


def test_load_extrinsic_fail_loud_on_non_orthonormal(tmp_path):
    p = tmp_path / "bad2.json"
    T = np.eye(4); T[0, 0] = 2.0                                      # rotation block not orthonormal
    p.write_text('{"T_cam_gripper": %s}' % T.tolist())
    with pytest.raises(ValueError):
        load_extrinsic(p)
