# B601 Milestone 3b — D405 perception + hand-eye calibration (eye-in-hand) — design

_Date: 2026-07-21. Status: SPEC for review. Builds on M2 (`robot_b601/task.py` —
`CubeLiftEnv`, `CubePose`, the privileged `get_cube_pose` seam) and M3a
(`robot_b601/{limits,ros_transport}.py`, `scripts/b601_real_first_light.py`, the
`B601Transport` seam + bounded joint motion + safety layer). Branch
`aspire_original_sim`. Hardware is on the bench (B601-RS + Intel RealSense D405)._

## Purpose

Replace the **privileged** `get_cube_pose() -> CubePose` (M2's ground-truth
perception) with a **real D405-derived** cube pose expressed in the **arm/base
frame**. The enabling piece is **eye-in-hand hand-eye calibration** — computing the
fixed camera→gripper transform so a pose seen by the wrist camera can be moved into
the arm frame. Hand-eye calibration is the known vendor gap; M3b fills it.

M3b stops at a **validated arm-frame pose**: perceive the cube, express it in the
arm frame, and compare against a measured ground truth. Driving the arm to the cube
(IK / reach), grasp, lift, and camera reward are **M3c** — M3b does not touch IK.

Same sim-first / live-integration split as M1–M3a: every piece of math (transforms,
ArUco detection, the hand-eye solve, the composition) is CI-tested with
`numpy`/`cv2` on synthetic frames and known geometry; only the live capture
(`pyrealsense2` frames + ROS 2 TF reads) is on-bench, behind deferred imports.

## Decisions (resolved during brainstorming)

1. **Eye-in-hand** — the D405 is mounted on the wrist/gripper and moves with the
   arm. Fits the D405's short range (~7–50 cm) and the reBot DevArm demos; no
   external rig. Calibration solves the fixed **camera→gripper** transform.
2. **ArUco fiducial on the cube** for detection — `cv2.aruco` + `solvePnP` gives a
   robust full-6-DOF pose in the camera frame, and reuses the same `cv2.aruco` stack
   as the calibration board (one dependency family). Keeps M3b about the
   perception→arm-frame seam, not about detection robustness.
3. **ChArUco board** (checkerboard + embedded ArUco), fixed to the table, as the
   calibration target — cv2's gold-standard target (sub-pixel corners, robust to
   partial views).
4. **Scope: validated pose, no target reach** — no IK, no reach-to-cube, no grasp.
5. **Gripper pose (FK) from ROS 2 TF** — read `T_gripper_base` from `/tf` (published
   by `robot_state_publisher` from the URDF), deferred-imported, consistent with the
   M3a ROS 2 stack; no reimplemented kinematics. The composition math stays CI-tested
   because it takes the transform as an input.

## Dependency landscape (verified)

`numpy` 1.21, `cv2` 4.5.4 (has `aruco`, `calibrateHandEye`, `solvePnP`,
`estimatePoseCharucoBoard`), and `scipy` 1.8 are installed → the full perception +
calibration math is CI-testable. Only `pyrealsense2` is missing (on-bench only,
deferred import), like `rclpy` in M3a.

## Architecture

### Data flow (perception)

```
D405 (wrist)  ──color+depth+intrinsics──▶ cv2.aruco detect cube marker
                                              │ solvePnP (marker_size)
                                              ▼
                                   cube pose in CAMERA frame  (T_cube_cam)
                                              │
   T_cam_gripper (calibrated, hand_eye.json) │  T_gripper_base (ROS 2 TF, live)
                                              ▼
                       T_base_cube = T_gripper_base ∘ T_cam_gripper ∘ T_cube_cam
                                              ▼
                                    CubePose in the ARM/BASE frame
```

### Components (files)

- **`robot_b601/transforms.py`** — pure `numpy`, CI-tested. 4×4 homogeneous
  transforms: `compose(*Ts)`, `invert(T)`, `mat_from_rvec_tvec(rvec, tvec)`,
  `quat_from_mat(R)` / `mat_from_quat`. The seam op:
  `cube_base_pose(T_cube_cam, T_cam_gripper, T_gripper_base) -> CubePose`
  (= `T_gripper_base ∘ T_cam_gripper ∘ T_cube_cam`, then extract x,y,z + quaternion
  into M2's `CubePose`). No cv2, no I/O — the numeric core.

- **`robot_b601/perception.py`** — `cv2`, CI-tested. `CameraIntrinsics(fx,fy,cx,cy)`;
  `detect_cube_pose(color, intrinsics, marker_size, dictionary) -> T_cube_cam | None`
  via `cv2.aruco.detectMarkers` + `cv2.solvePnP` on the marker's 4 corners. Returns
  `None` when the marker is not seen (honest no-detection). No camera I/O — takes a
  frame array in (so a synthetic frame tests it).

- **`robot_b601/hand_eye.py`** — `cv2`, CI-tested. `CharucoBoard` config wrapper;
  `detect_charuco_pose(frame, board, intrinsics) -> T_target_cam | None`
  (`detectMarkers` → `interpolateCornersCharuco` → `estimatePoseCharucoBoard`);
  `HandEyeSample(T_target_cam, T_gripper_base)`;
  `solve_hand_eye(samples) -> T_cam_gripper` wrapping `cv2.calibrateHandEye`
  (eye-in-hand form: gripper→base and target→cam lists), needing ≥3 (use ≥8)
  non-degenerate samples; `calibration_residual(samples, T_cam_gripper) -> float`
  (reprojection/consistency error, for honest reporting).
  `load_extrinsic(path) -> 4x4` / `save_extrinsic(path, T)` →
  `robot_b601/hand_eye.json`, with **fail-loud validation** (reject non-4×4, reject
  a non-orthonormal rotation block within tolerance) — mirrors M3a `load_limits`.
  Identity default if the file is missing, so CI/dry-run work uncalibrated.

- **`robot_b601/d405.py`** — live capture behind a small seam.
  `D405Frame(color, depth, intrinsics)`; `D405Camera` with **deferred
  `pyrealsense2`** import inside `connect()` (`connect()`, `capture() -> D405Frame`,
  `close()`); `FakeD405(frame)` returns a deterministic injected frame for CI. The
  exact stream config (resolution, aligned depth) is confirmed on-bench.

- **`robot_b601/tf_pose.py`** — the gripper pose source: a tiny `TfGripperPose`
  reader with **deferred `rclpy`/`tf2_ros`** import,
  `lookup(base_frame, gripper_frame) -> T_gripper_base`. A `FakeGripperPose(T)`
  returns an injected transform for CI. Frame names are config (defaults confirmed
  on-bench against `rebotarm_bringup`'s URDF). Stdlib-only at import (deferred ROS 2),
  kept separate from `d405.py` so the camera seam stays focused.

### Scripts (on-bench runners)

- **`scripts/b601_hand_eye_calibrate.py`** — the calibration routine (the vendor
  gap). Drives the wrist through **N preset look poses** (reusing M3a's bounded
  joint motion + limit clamp + safety checklist); at each pose captures a ChArUco
  frame (`detect_charuco_pose`) and reads `T_gripper_base` (TF); accumulates
  `HandEyeSample`s; `solve_hand_eye`; writes `robot_b601/hand_eye.json` and prints
  the residual + sample count. `--dry-run` prints the planned look poses (clamped)
  with **no hardware / no ROS 2 / no motion**. Skips samples where the board is not
  fully seen (honest, logged).

- **`scripts/b601_perceive_cube.py`** — the M3b **live validation**. Moves to a
  single look pose, captures, `detect_cube_pose`, composes with the loaded extrinsic
  + live TF into the arm frame, and prints the `CubePose`. `--compare X Y Z` reports
  the position error vs a ruler-measured ground truth. `--dry-run` prints the load
  pose + loaded-extrinsic summary with no hardware.

### Env integration (seam-compatible, not the full loop)

A thin `RealPerceptionSource` (D405 + extrinsic + TF → `get_cube_pose`) is what
`b601_perceive_cube.py` uses. **M3b does NOT wire real perception into the
`b601_execute` ASPIRE task loop** — that (real `get_cube_pose` inside a running
`CubeLiftEnv`, with grasp/lift/reward) is M3c. Keeping M3b to the pose deliverable
avoids pulling IK and the task loop into this milestone. `robot_b601/task.py` and
`aspire/` are unchanged.

## Testing

- **CI (no hardware, no ROS 2, no pyrealsense2):**
  - `transforms`: `compose`/`invert` round-trip to identity; a hand-computed case —
    known `T_cam_gripper`, `T_gripper_base`, `T_cube_cam` → asserted base-frame
    `CubePose` (position + orientation within tolerance); quat↔mat round-trip.
  - `perception`: render a synthetic ArUco marker at a known pose with `cv2` →
    `detect_cube_pose` recovers it within tolerance; a blank frame → `None`.
  - `hand_eye` (the honest calibration proof): synthesize ≥8 samples from a **known
    ground-truth `T_cam_gripper`** (random gripper poses + a fixed board → consistent
    `T_target_cam`) → `solve_hand_eye` recovers the ground truth within tolerance;
    `calibration_residual` is near zero for consistent samples and large for a
    corrupted one.
  - `hand_eye` I/O: `save`/`load` round-trip; load rejects non-4×4 and a
    non-orthonormal rotation (fail-loud).
  - `charuco`: synthetic ChArUco image → `detect_charuco_pose` recovers the pose.
  - end-to-end on fakes: `FakeD405(frame)` + `FakeGripperPose(T)` +
    `RealPerceptionSource` → a known arm-frame `CubePose`.
  - deferred-import guard: `import robot_b601.perception`, `.hand_eye`,
    `.transforms`, `.d405` all succeed with no `pyrealsense2`/`rclpy` present;
    `b601_perceive_cube.py --dry-run` and `b601_hand_eye_calibrate.py --dry-run`
    exit 0 in CI.

- **On-bench (live — hardware present):** print/mount the ChArUco board (fixed) and
  stick the ArUco marker on the cube; run `b601_hand_eye_calibrate.py` through the N
  look poses → `hand_eye.json` + residual; then `b601_perceive_cube.py --compare`
  against a ruler-measured cube position → report calibration residual + perception
  error. Safety checklist from M3a enforced (e-stop, monitor, clamp, dry-run first).
  Reported honestly as a live step, like M1's golden trace.

## Safety

- All arm motion during calibration/perception is the **M3a bounded joint motion**
  (small deltas from the current pose, absolute limit clamp, gripper held) driving to
  **preset look poses** — no perception-driven motion, no reach-to-target. The camera
  never commands the arm in M3b.
- `--dry-run` on both scripts previews poses with no hardware, always run first.
- Uncalibrated safety: a missing/invalid `hand_eye.json` loads identity and the
  perceive script reports the pose as **uncalibrated** rather than silently trusting
  a wrong extrinsic; calibration residual is always printed so a bad calibration is
  visible, not hidden.

## Components summary (files)

- `robot_b601/transforms.py`, `robot_b601/perception.py`, `robot_b601/hand_eye.py`,
  `robot_b601/d405.py`, `robot_b601/tf_pose.py`, `robot_b601/hand_eye.json` (identity
  default; finalized on-bench).
- `scripts/b601_hand_eye_calibrate.py`, `scripts/b601_perceive_cube.py`.
- `tests/b601/test_transforms.py`, `test_perception.py`, `test_hand_eye.py`,
  `test_d405_fake.py`, `test_tf_pose_fake.py`, `test_perceive_cube_dryrun.py`,
  `test_hand_eye_calibrate_dryrun.py`.

## On-bench-finalized (honest boundary)

- D405 intrinsics from the live stream (`pyrealsense2` provides them); the exact
  stream/alignment config.
- TF frame names (`base_link` ↔ tool/gripper frame) against `rebotarm_bringup`'s URDF.
- ArUco dictionary + marker/board sizes (config; committed defaults).
- Number and geometry of calibration look poses (well-separated orientations for a
  well-conditioned hand-eye solve) — tuned on-bench; committed defaults.

## Not doing (M3c+)

- No grasp, lift, or camera reward on real perception (M3c).
- No IK / `move_to_pose` / reach-to-cube on hardware (M3c).
- No real `get_cube_pose` inside the running `b601_execute` ASPIRE loop (M3c).
- No ASPIRE repair loop on hardware (M3d).
- No learned/markerless detection; no multi-object; single marked cube only.
- No `aspire/` changes; `robot_b601/task.py` unchanged.

## Deliverable mapping

- Fills the hand-eye calibration vendor gap and turns the M2 privileged
  `get_cube_pose` into a real, D405-derived, arm-frame pose — the perception
  foundation the SOW's real-hardware manipulation story needs.
- Sets up M3c (real cube-lift: real `get_cube_pose` in the task loop + IK reach +
  grasp + camera reward) and M3d (real ASPIRE repair loop on hardware).
