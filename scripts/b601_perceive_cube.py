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
    # SAFETY: hold the REAL gripper (not B601Node's hardcoded 0.0 default) and fail
    # loud if no /joint_states arrives, instead of a bare node.move_to_joints(look) --
    # see robot_b601/look_pose.py for the shared M3a/M3b rationale.
    from robot_b601.look_pose import move_to_look_pose
    move_to_look_pose(transport, node, RealClock(), look)

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
