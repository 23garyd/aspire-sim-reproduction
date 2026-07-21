# B601 Milestone 3b — D405 perception + hand-eye calibration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace M2's privileged `get_cube_pose()` with a real D405-derived cube pose in the arm/base frame, enabled by eye-in-hand hand-eye calibration.

**Architecture:** A pure numpy/scipy transform core (`transforms.py`) is composed by a cv2 ArUco cube detector (`perception.py`) and a cv2 ChArUco hand-eye calibrator (`hand_eye.py`); live capture (`d405.py`) and gripper-pose-from-TF (`tf_pose.py`) are thin seams whose heavy deps (`pyrealsense2`, `rclpy`/`tf2_ros`) are deferred-imported so everything imports and unit-tests with no hardware/ROS 2. Two on-bench scripts (`b601_hand_eye_calibrate.py`, `b601_perceive_cube.py`) wire it together, reusing M3a's bounded joint motion + limit clamp for safe look-pose moves.

**Tech Stack:** Python 3, numpy 1.21, scipy 1.8 (`scipy.spatial.transform.Rotation`), OpenCV 4.5.4 (`cv2`, `cv2.aruco` — the OLD pre-4.7 API), pytest. Deferred/on-bench: `pyrealsense2`, `rclpy`/`tf2_ros`.

## Global Constraints

- **Deferred heavy imports:** `pyrealsense2` is imported ONLY inside `D405Camera.connect()`/`capture()`; `rclpy`/`tf2_ros` ONLY inside `TfGripperPose.connect()`/`lookup()`. Every `robot_b601/*.py` module in this milestone MUST import successfully with neither installed. `pyrealsense2` is genuinely absent on this machine (so the D405 deferral is truly verified by import); `rclpy` IS present (so its test only proves no eager module-scope import).
- **cv2 4.5.4 OLD aruco API — use these exact names:** `cv2.aruco.Dictionary_get(id)`, `cv2.aruco.DetectorParameters_create()`, `cv2.aruco.detectMarkers(img, dict, parameters=...)`, `cv2.aruco.estimatePoseSingleMarkers(corners, size, K, dist)`, `cv2.aruco.CharucoBoard_create(sx, sy, sq, mk, dict)`, `cv2.aruco.interpolateCornersCharuco(corners, ids, img, board)`, `cv2.aruco.estimatePoseCharucoBoard(chC, chI, board, K, dist, None, None)`, `cv2.aruco.drawMarker(dict, id, px)`, `cv2.calibrateHandEye(...)`, `cv2.Rodrigues(rvec)`. Do NOT use the 4.7+ `ArucoDetector`/`CharucoDetector` classes.
- **Transform naming convention (document in every module):** `T_a_b` is a 4×4 that maps a point in frame `b` into frame `a` (equivalently, `b`'s pose expressed in `a`). Detected marker/board poses (`estimatePose*` rvec/tvec) are `T_cam_<thing>` (thing-in-camera). `cv2.calibrateHandEye` output is `T_cam_gripper` (camera-in-gripper). The seam op is `T_base_cube = T_gripper_base @ T_cam_gripper @ T_cube_cam`.
- **Test command (REQUIRED flag):** `python3 -m pytest <path> -q -p no:anyio`. Run the whole b601 suite `python3 -m pytest tests/b601/ -q -p no:anyio` before each commit.
- **No `aspire/` changes; `robot_b601/task.py` unchanged** — only import its `CubePose`.
- **All arm motion is M3a's bounded joint motion to PRESET look poses**, clamped to `robot_b601/limits.py`. No perception-driven motion, no IK, no reach-to-target in M3b.
- **ArUco/ChArUco defaults:** dictionary `cv2.aruco.DICT_4X4_50`; cube marker id `7`. These are committed defaults, finalized on-bench.
- **Work from** `/home/demo/aspire_robot_engine` on branch `aspire_original_sim`.

---

### Task 1: `transforms.py` — pure transform core + the arm-frame seam op

**Files:**
- Create: `robot_b601/transforms.py`
- Test: `tests/b601/test_transforms.py`

**Interfaces:**
- Consumes: `robot_b601.task.CubePose` (`CubePose(x,y,z,qx=0,qy=0,qz=0,qw=1)`).
- Produces: `make_transform(R, t) -> np.ndarray(4,4)`; `compose(*mats) -> np.ndarray(4,4)` (left-to-right product); `invert(T) -> np.ndarray(4,4)` (rigid inverse); `cube_base_pose(T_cube_cam, T_cam_gripper, T_gripper_base) -> CubePose`.

- [ ] **Step 1: Write the failing test**

Create `tests/b601/test_transforms.py`:

```python
import numpy as np
from scipy.spatial.transform import Rotation
from robot_b601.transforms import make_transform, compose, invert, cube_base_pose


def _rigid(rng):
    R = Rotation.random(random_state=rng).as_matrix()
    t = rng.uniform(-0.5, 0.5, 3)
    return make_transform(R, t)


def test_invert_round_trips_to_identity():
    T = _rigid(np.random.RandomState(1))
    assert np.allclose(T @ invert(T), np.eye(4), atol=1e-9)
    assert np.allclose(invert(T) @ T, np.eye(4), atol=1e-9)


def test_compose_is_left_to_right_product():
    A = make_transform(np.eye(3), [1, 0, 0])
    B = make_transform(np.eye(3), [0, 2, 0])
    assert np.allclose(compose(A, B), A @ B)
    assert np.allclose(compose(A, B)[:3, 3], [1, 2, 0])


def test_cube_base_pose_pure_translation():
    # gripper at +1x in base, identity camera, cube 0.5 ahead of camera -> base (1,0,0.5)
    T_gripper_base = make_transform(np.eye(3), [1, 0, 0])
    T_cam_gripper = np.eye(4)
    T_cube_cam = make_transform(np.eye(3), [0, 0, 0.5])
    p = cube_base_pose(T_cube_cam, T_cam_gripper, T_gripper_base)
    assert np.allclose([p.x, p.y, p.z], [1, 0, 0.5], atol=1e-9)
    assert np.allclose([p.qx, p.qy, p.qz, p.qw], [0, 0, 0, 1], atol=1e-9)


def test_cube_base_pose_applies_rotation():
    # camera rotated +90deg about z in gripper; cube 0.5 along cam-x -> base y = +0.5
    Rz = Rotation.from_euler("z", 90, degrees=True).as_matrix()
    T_cam_gripper = make_transform(Rz, [0, 0, 0])
    T_cube_cam = make_transform(np.eye(3), [0.5, 0, 0])
    p = cube_base_pose(T_cube_cam, T_cam_gripper, np.eye(4))
    assert np.allclose([p.x, p.y, p.z], [0, 0.5, 0], atol=1e-9)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/b601/test_transforms.py -q -p no:anyio`
Expected: FAIL — `ModuleNotFoundError: robot_b601.transforms`.

- [ ] **Step 3: Write the implementation**

Create `robot_b601/transforms.py`:

```python
"""Pure numpy/scipy 4x4 homogeneous transform helpers for B601 M3b perception.

Convention: T_a_b maps a point in frame b into frame a (b's pose expressed in a).
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
    """Move a cube pose seen in the CAMERA frame into the ARM/BASE frame:
    T_base_cube = T_gripper_base @ T_cam_gripper @ T_cube_cam."""
    T = compose(T_gripper_base, T_cam_gripper, T_cube_cam)
    x, y, z = T[:3, 3]
    qx, qy, qz, qw = Rotation.from_matrix(T[:3, :3]).as_quat()
    return CubePose(float(x), float(y), float(z),
                    float(qx), float(qy), float(qz), float(qw))
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m pytest tests/b601/test_transforms.py -q -p no:anyio`
Expected: PASS (4 tests).

- [ ] **Step 5: Commit**

```bash
git add robot_b601/transforms.py tests/b601/test_transforms.py
git commit -m "feat(b601): transforms core + cube_base_pose arm-frame seam (M3b)"
```

---

### Task 2: `perception.py` — ArUco cube detection (camera frame)

**Files:**
- Create: `robot_b601/perception.py`
- Test: `tests/b601/test_perception.py`

**Interfaces:**
- Consumes: `robot_b601.transforms.make_transform`.
- Produces: `CameraIntrinsics(fx, fy, cx, cy)` with `.matrix() -> np.ndarray(3,3)`; `ARUCO_DICT = cv2.aruco.DICT_4X4_50`; `detect_cube_pose(color, intrinsics, marker_size, marker_id=7, dict_id=ARUCO_DICT) -> np.ndarray(4,4) | None` (returns `T_cube_cam`, or None if the marker id is not seen).

- [ ] **Step 1: Write the failing test**

Create `tests/b601/test_perception.py`:

```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/b601/test_perception.py -q -p no:anyio`
Expected: FAIL — `ModuleNotFoundError: robot_b601.perception`.

- [ ] **Step 3: Write the implementation**

Create `robot_b601/perception.py`:

```python
"""D405 cube detection: find the cube's ArUco marker and return its pose in the CAMERA
frame (T_cube_cam, 4x4). cv2 only; takes a frame array in (no camera I/O), so a synthetic
frame tests it. Uses the OpenCV 4.5.4 aruco API. RealPerceptionSource (Task 5) composes
this into the arm frame."""
from __future__ import annotations

from dataclasses import dataclass

import cv2
import numpy as np

from robot_b601.transforms import make_transform

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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m pytest tests/b601/test_perception.py -q -p no:anyio`
Expected: PASS (3 tests).

- [ ] **Step 5: Commit**

```bash
git add robot_b601/perception.py tests/b601/test_perception.py
git commit -m "feat(b601): ArUco cube detection -> pose in camera frame (M3b)"
```

---

### Task 3: `hand_eye.py` — ChArUco detection, hand-eye solve, extrinsic I/O (fail-loud)

**Files:**
- Create: `robot_b601/hand_eye.py`
- Create: `robot_b601/hand_eye.json` (identity default)
- Test: `tests/b601/test_hand_eye.py`

**Interfaces:**
- Consumes: `robot_b601.transforms.{make_transform, invert}`, `robot_b601.perception.CameraIntrinsics`.
- Produces: `CharucoBoard(squares_x=5, squares_y=7, square_length=0.03, marker_length=0.022, dict_id=DICT_4X4_50)` with `.cv() -> (cv_board, dictionary)`; `detect_charuco_pose(frame, board, intrinsics) -> np.ndarray(4,4) | None` (`T_target_cam`); `HandEyeSample(T_target_cam, T_gripper_base)`; `solve_hand_eye(samples, method=cv2.CALIB_HAND_EYE_TSAI) -> np.ndarray(4,4)` (`T_cam_gripper`, raises `ValueError` if `<3` samples); `calibration_residual(samples, T_cam_gripper) -> float`; `save_extrinsic(path, T)`; `load_extrinsic(path=None) -> np.ndarray(4,4)` (missing/None → identity; fail-loud on non-4×4 or non-orthonormal rotation).

- [ ] **Step 1: Write the failing test**

Create `tests/b601/test_hand_eye.py`:

```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/b601/test_hand_eye.py -q -p no:anyio`
Expected: FAIL — `ModuleNotFoundError: robot_b601.hand_eye`.

- [ ] **Step 3: Write the implementation**

Create `robot_b601/hand_eye.py`:

```python
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


def solve_hand_eye(samples, method=cv2.CALIB_HAND_EYE_TSAI) -> np.ndarray:
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
```

- [ ] **Step 4: Create the identity-default config**

Create `robot_b601/hand_eye.json`:

```json
{
  "T_cam_gripper": [
    [1.0, 0.0, 0.0, 0.0],
    [0.0, 1.0, 0.0, 0.0],
    [0.0, 0.0, 1.0, 0.0],
    [0.0, 0.0, 0.0, 1.0]
  ]
}
```

- [ ] **Step 5: Run test to verify it passes**

Run: `python3 -m pytest tests/b601/test_hand_eye.py -q -p no:anyio`
Expected: PASS (9 tests). If the recover-extrinsic assertion is marginally over `1e-3`, the calibration is still correct — do NOT loosen silently; re-run (it is deterministic with the fixed seed) and only widen to `2e-3` with a code comment if it genuinely exceeds, noting Tsai's translation-stage precision.

- [ ] **Step 6: Commit**

```bash
git add robot_b601/hand_eye.py robot_b601/hand_eye.json tests/b601/test_hand_eye.py
git commit -m "feat(b601): ChArUco hand-eye solve + fail-loud extrinsic I/O (M3b)"
```

---

### Task 4: `d405.py` + `tf_pose.py` — live capture seams (deferred imports) + fakes

**Files:**
- Create: `robot_b601/d405.py`
- Create: `robot_b601/tf_pose.py`
- Test: `tests/b601/test_capture_seams.py`

**Interfaces:**
- Consumes: `robot_b601.perception.CameraIntrinsics`, `robot_b601.transforms.make_transform`.
- Produces: `D405Frame(color, depth, intrinsics)`; `FakeD405(frame)` (`.connect()`, `.capture() -> D405Frame`, `.close()`); `D405Camera(width=640, height=480, fps=30)` (same methods; `capture` before `connect` raises `RuntimeError`; `pyrealsense2` deferred). `FakeGripperPose(T)` (`.connect()`, `.lookup(base_frame=None, gripper_frame=None) -> np.ndarray(4,4)`); `TfGripperPose(base_frame="base_link", gripper_frame="tool0")` (same; `lookup` before `connect` raises `RuntimeError`; `rclpy`/`tf2_ros` deferred).

- [ ] **Step 1: Write the failing test**

Create `tests/b601/test_capture_seams.py`:

```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/b601/test_capture_seams.py -q -p no:anyio`
Expected: FAIL — `ModuleNotFoundError: robot_b601.d405`.

- [ ] **Step 3: Write `robot_b601/d405.py`**

```python
"""D405 depth-camera capture seam. D405Camera defers pyrealsense2 (imported inside
connect()/capture()) so this module imports with no pyrealsense2. FakeD405 returns an
injected frame for CI. The exact stream/alignment config is confirmed on-bench."""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from robot_b601.perception import CameraIntrinsics


@dataclass
class D405Frame:
    color: np.ndarray
    depth: np.ndarray
    intrinsics: CameraIntrinsics


class FakeD405:
    """Deterministic camera for CI: capture() returns the injected frame."""

    def __init__(self, frame: D405Frame):
        self._frame = frame

    def connect(self):
        pass

    def capture(self) -> D405Frame:
        return self._frame

    def close(self):
        pass


class D405Camera:
    """Live D405 (on-bench). pyrealsense2 is imported in connect(); confirm the stream and
    depth-alignment config against the D405 on the bench."""

    def __init__(self, width: int = 640, height: int = 480, fps: int = 30):
        self._w, self._h, self._fps = width, height, fps
        self._pipe = None
        self._intr = None

    def connect(self):
        import pyrealsense2 as rs
        self._pipe = rs.pipeline()
        cfg = rs.config()
        cfg.enable_stream(rs.stream.color, self._w, self._h, rs.format.bgr8, self._fps)
        cfg.enable_stream(rs.stream.depth, self._w, self._h, rs.format.z16, self._fps)
        profile = self._pipe.start(cfg)
        v = profile.get_stream(rs.stream.color).as_video_stream_profile().get_intrinsics()
        self._intr = CameraIntrinsics(v.fx, v.fy, v.ppx, v.ppy)

    def capture(self) -> D405Frame:
        if self._pipe is None:
            raise RuntimeError("D405Camera.connect() must be called before capture()")
        frames = self._pipe.wait_for_frames()
        color = np.asanyarray(frames.get_color_frame().get_data())
        depth = np.asanyarray(frames.get_depth_frame().get_data())
        return D405Frame(color, depth, self._intr)

    def close(self):
        if self._pipe is not None:
            self._pipe.stop()
            self._pipe = None
```

- [ ] **Step 4: Write `robot_b601/tf_pose.py`**

```python
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
```

- [ ] **Step 5: Run test to verify it passes**

Run: `python3 -m pytest tests/b601/test_capture_seams.py -q -p no:anyio`
Expected: PASS (6 tests). Note in your report: `rclpy` IS installed here, so `test_tf_pose_module_imports_without_ros` only proves no eager module-scope import (the deferral invariant holds); `pyrealsense2` is genuinely absent so the D405 deferral is fully proven.

- [ ] **Step 6: Commit**

```bash
git add robot_b601/d405.py robot_b601/tf_pose.py tests/b601/test_capture_seams.py
git commit -m "feat(b601): D405 + TF gripper-pose capture seams (deferred imports) + fakes (M3b)"
```

---

### Task 5: `RealPerceptionSource` — compose capture + extrinsic + TF into arm-frame `get_cube_pose`

**Files:**
- Modify: `robot_b601/perception.py` (append `RealPerceptionSource`)
- Test: `tests/b601/test_real_perception.py`

**Interfaces:**
- Consumes: `detect_cube_pose` (Task 2), `robot_b601.transforms.cube_base_pose` (Task 1), a duck-typed `camera` (`.capture() -> D405Frame` with `.color`/`.intrinsics`) and `tf` (`.lookup(base, gripper) -> 4x4`) from Task 4.
- Produces: `RealPerceptionSource(camera, tf, T_cam_gripper, marker_size, marker_id=7, base_frame="base_link", gripper_frame="tool0")` with `get_cube_pose() -> CubePose` (raises `RuntimeError` if no marker is detected).

- [ ] **Step 1: Write the failing test**

Create `tests/b601/test_real_perception.py`:

```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/b601/test_real_perception.py -q -p no:anyio`
Expected: FAIL — `ImportError: cannot import name 'RealPerceptionSource'`.

- [ ] **Step 3: Append the implementation to `robot_b601/perception.py`**

Add at the end of `robot_b601/perception.py` (and extend the existing imports with `from robot_b601.transforms import cube_base_pose`):

```python
from robot_b601.transforms import cube_base_pose


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
```

Note: `RealPerceptionSource` must be defined AFTER `detect_cube_pose`; keep the `from robot_b601.transforms import cube_base_pose` import at the top of the file with the other imports (shown here inline only for locality — do not create a duplicate import).

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m pytest tests/b601/test_real_perception.py -q -p no:anyio`
Expected: PASS (2 tests).

- [ ] **Step 5: Commit**

```bash
git add robot_b601/perception.py tests/b601/test_real_perception.py
git commit -m "feat(b601): RealPerceptionSource -> real arm-frame get_cube_pose (M3b)"
```

---

### Task 6: `scripts/b601_perceive_cube.py` — perception runner + `--dry-run`

**Files:**
- Create: `scripts/b601_perceive_cube.py`
- Test: `tests/b601/test_perceive_cube.py`

**Interfaces:**
- Consumes: `robot_b601.hand_eye.load_extrinsic`, `robot_b601.perception.{RealPerceptionSource, CameraIntrinsics}`, `robot_b601.d405.D405Camera`, `robot_b601.tf_pose.TfGripperPose` (live path only, deferred).
- Produces: `format_pose(pose) -> str`; a CLI with `--dry-run` (prints the loaded extrinsic summary + planned look pose, no hardware, exit 0), `--extrinsic` (default `robot_b601/hand_eye.json`), `--marker-size`, `--compare X Y Z` (prints position error), `--out`.

- [ ] **Step 1: Write the failing test**

Create `tests/b601/test_perceive_cube.py`:

```python
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]


def test_dry_run_exits_zero_and_reports_extrinsic():
    proc = subprocess.run(
        [sys.executable, "scripts/b601_perceive_cube.py", "--dry-run"],
        capture_output=True, text=True, cwd=REPO)
    assert proc.returncode == 0, proc.stderr
    out = proc.stdout.lower()
    assert "extrinsic" in out and "dry-run" in out


def test_format_pose_is_readable():
    sys.path.insert(0, str(REPO / "scripts"))
    import b601_perceive_cube as pc
    from robot_b601.task import CubePose
    s = pc.format_pose(CubePose(0.4, 0.0, 0.1))
    assert "0.4" in s and "0.1" in s
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/b601/test_perceive_cube.py -q -p no:anyio`
Expected: FAIL — script missing.

- [ ] **Step 3: Write the runner**

Create `scripts/b601_perceive_cube.py`:

```python
#!/usr/bin/env python3
"""B601-RS + D405 cube perception (M3b): move the wrist to a look pose, capture, detect
the cube's ArUco marker, and report its pose in the ARM/BASE frame using the calibrated
hand-eye extrinsic. --dry-run previews the loaded extrinsic + look pose with no hardware.

SAFETY (a live run moves the arm to a look pose via the M3a bounded joint motion):
  * e-stop within reach; workspace clear; vendor safe-park monitor running.
  * run --dry-run first; finalize robot_b601/hand_eye.json via b601_hand_eye_calibrate.py.
Live use (after calibration, ROS 2 sourced + arm powered + D405 connected):
  python3 scripts/b601_perceive_cube.py --marker-size 0.03 --compare 0.40 0.00 0.02
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np

from robot_b601.hand_eye import load_extrinsic

LOOK_POSE = [0.0, -0.3, 0.6, 0.0, 0.9, 0.0]   # nominal wrist-over-table look pose (rad)


def format_pose(pose) -> str:
    return (f"cube (base frame): x={pose.x:.3f} y={pose.y:.3f} z={pose.z:.3f} "
            f"q=({pose.qx:.3f},{pose.qy:.3f},{pose.qz:.3f},{pose.qw:.3f})")


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true",
                    help="preview extrinsic + look pose without hardware")
    ap.add_argument("--extrinsic", default="robot_b601/hand_eye.json")
    ap.add_argument("--marker-size", type=float, default=0.03)
    ap.add_argument("--marker-id", type=int, default=7)
    ap.add_argument("--compare", nargs=3, type=float, metavar=("X", "Y", "Z"), default=None)
    ap.add_argument("--out", default="b601_perceive_result.txt")
    args = ap.parse_args(argv)

    T_cam_gripper = load_extrinsic(args.extrinsic)
    calibrated = not np.allclose(T_cam_gripper, np.eye(4))
    if args.dry_run:
        print(f"[dry-run] extrinsic {args.extrinsic}: "
              f"{'calibrated' if calibrated else 'IDENTITY (uncalibrated!)'}")
        print(f"[dry-run] T_cam_gripper=\n{np.round(T_cam_gripper, 4)}")
        print(f"[dry-run] look pose (rad): {LOOK_POSE}")
        print("[dry-run] no hardware, no ROS 2, no motion.")
        return 0

    if not calibrated:
        print("[WARNING] extrinsic is identity -- run b601_hand_eye_calibrate.py first; "
              "the reported pose is UNCALIBRATED.", file=sys.stderr)

    # Live path (deferred: hardware + ROS 2 only here).
    from robot_b601.d405 import D405Camera
    from robot_b601.tf_pose import TfGripperPose
    from robot_b601.perception import RealPerceptionSource
    from robot_b601.limits import load_limits, clamp_to_limits
    from robot_b601.ros_transport import B601RosTransport
    from robot_b601.node import B601Node
    from robot_b601.clock import RealClock

    # Move the wrist to the (clamped) look pose via the M3a bounded joint path.
    limits = load_limits("robot_b601/b601_rs_limits.json")
    look, _ = clamp_to_limits(LOOK_POSE, limits)
    transport = B601RosTransport(limits=limits)
    transport.connect()
    node = B601Node(transport, clock=RealClock(), home=look)
    node.move_to_joints(look)

    camera = D405Camera(); camera.connect()
    tf = TfGripperPose(); tf.connect()
    src = RealPerceptionSource(camera=camera, tf=tf, T_cam_gripper=T_cam_gripper,
                              marker_size=args.marker_size, marker_id=args.marker_id)
    pose = src.get_cube_pose()
    line = format_pose(pose)
    print(line)
    if args.compare is not None:
        err = float(np.linalg.norm(np.array([pose.x, pose.y, pose.z]) - np.array(args.compare)))
        print(f"position error vs measured {tuple(args.compare)}: {err*1000:.1f} mm")
    Path(args.out).write_text(line + "\n")
    camera.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m pytest tests/b601/test_perceive_cube.py -q -p no:anyio`
Expected: PASS (2 tests) — `--dry-run` runs in CI with no hardware/ROS 2 (the live imports are inside the non-dry-run branch).

- [ ] **Step 5: Commit**

```bash
chmod +x scripts/b601_perceive_cube.py
git add scripts/b601_perceive_cube.py tests/b601/test_perceive_cube.py
git commit -m "feat(b601): perceive-cube runner (arm-frame pose + --dry-run + --compare) (M3b)"
```

---

### Task 7: `scripts/b601_hand_eye_calibrate.py` — calibration runner + `--dry-run`

**Files:**
- Create: `scripts/b601_hand_eye_calibrate.py`
- Test: `tests/b601/test_hand_eye_calibrate.py`

**Interfaces:**
- Consumes: `robot_b601.limits.{load_limits, clamp_to_limits}`, `robot_b601.hand_eye.{CharucoBoard, detect_charuco_pose, HandEyeSample, solve_hand_eye, calibration_residual, save_extrinsic}`, and (live only, deferred) `D405Camera`/`TfGripperPose`/`B601Node`.
- Produces: `calibration_look_poses(home, deltas=DEFAULT_CALIB_DELTAS) -> list[list[float]]` (each = clamped `home + delta`, varied orientations for a well-conditioned solve); a CLI with `--dry-run` (prints the clamped look poses + board config, no hardware, exit 0), `--limits`, `--out` (default `robot_b601/hand_eye.json`).

- [ ] **Step 1: Write the failing test**

Create `tests/b601/test_hand_eye_calibrate.py`:

```python
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]


def test_dry_run_exits_zero_and_lists_poses():
    proc = subprocess.run(
        [sys.executable, "scripts/b601_hand_eye_calibrate.py", "--dry-run"],
        capture_output=True, text=True, cwd=REPO)
    assert proc.returncode == 0, proc.stderr
    out = proc.stdout.lower()
    assert "pose" in out and "board" in out


def test_calibration_look_poses_are_bounded_and_multiple():
    sys.path.insert(0, str(REPO / "scripts"))
    import b601_hand_eye_calibrate as cal
    home = [0.0, -0.3, 0.6, 0.0, 0.9, 0.0]
    poses = cal.calibration_look_poses(home)
    assert len(poses) >= 8                      # enough varied views for a stable solve
    for p in poses:
        for h, j in zip(home, p):
            assert abs(j - h) <= cal.MAX_CALIB_DELTA + 1e-9
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/b601/test_hand_eye_calibrate.py -q -p no:anyio`
Expected: FAIL — script missing.

- [ ] **Step 3: Write the runner**

Create `scripts/b601_hand_eye_calibrate.py`:

```python
#!/usr/bin/env python3
"""B601-RS + D405 eye-in-hand hand-eye calibration (M3b): move the wrist through several
look poses over a fixed ChArUco board, capture the board pose + gripper TF at each, solve
cv2.calibrateHandEye, and write robot_b601/hand_eye.json. --dry-run previews the clamped
look poses + board config with no hardware.

SAFETY (a live run moves the arm through several look poses via M3a bounded joint motion):
  * e-stop within reach; workspace clear; vendor safe-park monitor running.
  * run --dry-run first; mount the ChArUco board rigidly in view of the table.
Live use (ROS 2 sourced + arm powered + D405 connected):
  python3 scripts/b601_hand_eye_calibrate.py --limits robot_b601/b601_rs_limits.json
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from robot_b601.limits import clamp_to_limits, load_limits
from robot_b601.hand_eye import CharucoBoard

HOME = [0.0, -0.3, 0.6, 0.0, 0.9, 0.0]     # nominal wrist-over-board look pose (rad)
MAX_CALIB_DELTA = 0.25                       # rad; per-joint bound for the varied views
# Varied small orientations around HOME so the hand-eye solve is well-conditioned:
DEFAULT_CALIB_DELTAS = [
    [0.0, 0.0, 0.0, 0.0, 0.0, 0.0],
    [0.15, 0.0, 0.0, 0.0, 0.0, 0.0],
    [-0.15, 0.0, 0.0, 0.0, 0.0, 0.0],
    [0.0, 0.15, 0.0, 0.0, 0.0, 0.0],
    [0.0, -0.15, 0.0, 0.0, 0.0, 0.0],
    [0.0, 0.0, 0.0, 0.15, 0.0, 0.2],
    [0.0, 0.0, 0.0, -0.15, 0.0, -0.2],
    [0.1, 0.0, 0.0, 0.0, 0.15, 0.0],
    [-0.1, 0.1, 0.0, 0.0, -0.15, 0.0],
    [0.0, 0.0, 0.0, 0.2, 0.0, 0.2],
]


def calibration_look_poses(home, deltas=DEFAULT_CALIB_DELTAS, limits=None):
    """home + each varied delta, clamped to joint limits. Varied orientations give the
    hand-eye solve enough rotational excitation to be well-conditioned."""
    poses = []
    for d in deltas:
        wp = [h + di for h, di in zip(home, d)]
        if limits is not None:
            wp, _ = clamp_to_limits(wp, limits)
        poses.append(wp)
    return poses


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true",
                    help="preview clamped look poses + board config without hardware")
    ap.add_argument("--limits", default="robot_b601/b601_rs_limits.json")
    ap.add_argument("--marker-size", type=float, default=0.03)
    ap.add_argument("--out", default="robot_b601/hand_eye.json")
    args = ap.parse_args(argv)

    limits = load_limits(args.limits)
    board = CharucoBoard()
    poses = calibration_look_poses(HOME, limits=limits)

    if args.dry_run:
        print(f"[dry-run] ChArUco board: {board.squares_x}x{board.squares_y} "
              f"square={board.square_length} marker={board.marker_length}")
        for i, p in enumerate(poses):
            print(f"[dry-run] look pose {i}: {[round(j, 3) for j in p]}")
        print("[dry-run] no hardware, no ROS 2, no motion.")
        return 0

    # Live path (deferred: hardware + ROS 2 only here).
    from robot_b601.clock import RealClock
    from robot_b601.d405 import D405Camera
    from robot_b601.hand_eye import (HandEyeSample, calibration_residual,
                                     detect_charuco_pose, save_extrinsic, solve_hand_eye)
    from robot_b601.node import B601Node
    from robot_b601.ros_transport import B601RosTransport
    from robot_b601.tf_pose import TfGripperPose

    transport = B601RosTransport(limits=limits)
    transport.connect()
    node = B601Node(transport, clock=RealClock(), home=poses[0])
    camera = D405Camera(); camera.connect()
    tf = TfGripperPose(); tf.connect()

    samples = []
    for i, p in enumerate(poses):
        node.move_to_joints(p)
        frame = camera.capture()
        T_target_cam = detect_charuco_pose(frame.color, board, frame.intrinsics)
        if T_target_cam is None:
            print(f"[calib] pose {i}: board not fully seen -- skipping", file=sys.stderr)
            continue
        T_gripper_base = tf.lookup()
        samples.append(HandEyeSample(T_target_cam, T_gripper_base))
        print(f"[calib] pose {i}: sample captured ({len(samples)} total)")

    if len(samples) < 3:
        print(f"[calib] only {len(samples)} samples -- need >=3; aborting", file=sys.stderr)
        camera.close()
        return 1
    T_cam_gripper = solve_hand_eye(samples)
    residual = calibration_residual(samples, T_cam_gripper)
    save_extrinsic(args.out, T_cam_gripper)
    print(f"[calib] solved from {len(samples)} samples; residual={residual*1000:.2f} mm; "
          f"wrote {args.out}")
    camera.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m pytest tests/b601/test_hand_eye_calibrate.py -q -p no:anyio`
Expected: PASS (2 tests) — `--dry-run` runs in CI with no hardware (live imports are inside the non-dry-run branch).

- [ ] **Step 5: Commit**

```bash
chmod +x scripts/b601_hand_eye_calibrate.py
git add scripts/b601_hand_eye_calibrate.py tests/b601/test_hand_eye_calibrate.py
git commit -m "feat(b601): hand-eye calibration runner (look poses + solve + --dry-run) (M3b)"
```

---

### Task 8: Full-suite gate + on-bench bring-up note + push

**Files:** none (verification only)

- [ ] **Step 1: Run the complete suite**

Run: `python3 -m pytest tests/ -q -p no:anyio`
Expected: PASS — prior 240 + the new M3b tests (~28 across the 7 new test files: 4+3+9+6+2+2+2).

- [ ] **Step 2: Confirm both safety dry-runs end-to-end**

Run:
```bash
python3 scripts/b601_perceive_cube.py --dry-run
python3 scripts/b601_hand_eye_calibrate.py --dry-run
```
Expected: both exit 0; perceive prints the extrinsic status (IDENTITY/uncalibrated by default) + look pose + `no hardware`; calibrate prints the board config + the ≥8 clamped look poses + `no hardware`.

- [ ] **Step 3: Push**

```bash
git push aspire_demo aspire_original_sim
```

- [ ] **Step 4: On-bench calibration + validation (LIVE — hardware present, after merge, not a unit test)**

Record for the operator (do NOT run in CI):
1. Print a `DICT_4X4_50` ChArUco board (5×7, 30 mm square / 22 mm marker) and mount it rigidly in view of the table; stick a `DICT_4X4_50` marker id 7 on the cube (measure its side in metres → `--marker-size`).
2. Confirm the TF frame names (`base_link` ↔ wrist/tool frame) against `rebotarm_bringup`'s URDF; set them via `TfGripperPose` defaults if they differ.
3. `source` ROS 2; `ros2 launch rebotarm_bringup …` + `ros2 run rebotarm_monitor_ros2 …`; e-stop in reach; workspace clear. Connect the D405.
4. `python3 scripts/b601_hand_eye_calibrate.py --dry-run` (review poses) → then the live run → check the reported residual is small (few mm); it writes `robot_b601/hand_eye.json`.
5. `python3 scripts/b601_perceive_cube.py --marker-size <m> --compare <X Y Z>` against a ruler-measured cube position → report the perception error. Honest live validation, like M1's golden trace.

---

## Self-review notes (spec coverage)

- `transforms.py` (numpy/scipy core + `cube_base_pose` seam) → Task 1.
- `perception.py` ArUco cube detection → Task 2; `RealPerceptionSource` composition → Task 5.
- `hand_eye.py` ChArUco detect + `solve_hand_eye` + residual + fail-loud extrinsic I/O + `hand_eye.json` → Task 3 (honest known-extrinsic-recovery proof test).
- `d405.py` + `tf_pose.py` deferred-import live seams + fakes → Task 4.
- Scripts `b601_perceive_cube.py` (validation, `--compare`) → Task 6; `b601_hand_eye_calibrate.py` (the vendor-gap routine) → Task 7. Both `--dry-run` CI-tested.
- Two safety bounds unchanged from M3a: all motion is bounded joint moves to preset look poses, limit-clamped; camera never commands the arm → Tasks 6/7 reuse `clamp_to_limits` + `B601Node`.
- Uncalibrated safety: identity extrinsic default + explicit "UNCALIBRATED" warning + printed residual → Tasks 3/6/7.
- CI without hardware/ROS 2: deferred `pyrealsense2`/`rclpy`/`tf2_ros`; all math on synthetic frames/known geometry → Tasks 1–5 unit tests + Tasks 6/7 `--dry-run` subprocess tests.
- **Known honest boundary (on-bench):** D405 intrinsics from the live stream; exact TF frame names; ArUco/board sizes; number/geometry of look poses → Task 8 on-bench note + config defaults.
- **Deliberate deviation:** spec said transforms are "pure numpy"; the plan uses `scipy.spatial.transform.Rotation` for the rotation↔quaternion conversion (scipy is installed and CI-tested) — flagged, keeps the quaternion math robust.
