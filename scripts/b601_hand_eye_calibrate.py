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
    # SAFETY: hold the REAL gripper (not B601Node's hardcoded 0.0 default) and fail
    # loud if no /joint_states arrives, instead of a bare node.move_to_joints(p) --
    # see robot_b601/look_pose.py for the shared M3a/M3b rationale.
    from robot_b601.look_pose import move_to_look_pose

    transport = B601RosTransport(limits=limits)
    transport.connect()
    node = B601Node(transport, clock=RealClock(), home=poses[0])
    camera = D405Camera(); camera.connect()
    tf = TfGripperPose(); tf.connect()

    samples = []
    for i, p in enumerate(poses):
        move_to_look_pose(transport, node, RealClock(), p)
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
