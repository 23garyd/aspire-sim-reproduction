#!/usr/bin/env python3
"""B601-RS real-hardware 'first light': drive the REAL arm through small bounded joint
waypoints via the ASPIRE engine, over ROS 2. --dry-run previews the CLAMPED waypoints
without ROS 2 or moving (always run this first).

SAFETY (real arm moves on a live run):
  * e-stop within reach; clear the workspace.
  * launch the vendor safe-park monitor: `ros2 run rebotarm_monitor_ros2 ...`.
  * bring up the controller: `ros2 launch rebotarm_bringup ...`.
  * finalize robot_b601/b601_rs_limits.json from the B601-RS URDF first.
Live use:
  ros2 ... (bringup + monitor); then
  python3 scripts/b601_real_first_light.py --limits robot_b601/b601_rs_limits.json
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from robot_b601.clock import RealClock
from robot_b601.engine import B601Engine
from robot_b601.limits import clamp_to_limits, load_limits
from robot_b601.node import B601Node


DELTA_MAX_WARN_CEILING = 0.3   # rad; conservative sanity ceiling for first contact (warn only, not a hard fail -- the absolute limit clamp is the backstop)


def plan_waypoints(home, delta_max: float = 0.15):
    """home -> home + a small bounded delta on all joints -> home. Deliberately gentle
    for first contact with a real arm; the limit clamp is the backstop."""
    bumped = [h + delta_max for h in home]
    return [list(home), bumped, list(home)]


def _wait_for_state(transport, clock, timeout_s: float, poll_dt: float = 0.01):
    """Poll transport.latest() on the injected clock until a real state arrives or
    the timeout elapses. Mirrors B601Node._stream_until's clock/poll idiom (same
    now()/sleep() usage) so this is deterministic and testable with ManualClock."""
    t0 = clock.now()
    while True:
        state = transport.latest()
        if state is not None:
            return state
        if clock.now() - t0 >= timeout_s:
            return None
        clock.sleep(poll_dt)


def run(transport, clock, delta_max: float = 0.15, state_timeout: float = 2.0):
    transport.connect()
    # SAFETY: connect() returns as soon as the ROS 2 spin thread starts -- it does NOT
    # guarantee /joint_states has arrived yet. Poll (bounded) for the REAL current pose
    # and use THAT as home. Never fall back to a hardcoded pose: doing so would jump the
    # real arm from its true (unknown) pose to that hardcoded one on the first move.
    state = _wait_for_state(transport, clock, state_timeout)
    if state is None:
        raise RuntimeError(
            f"b601_real_first_light: no /joint_states received within "
            f"{state_timeout}s of connect() -- refusing to move without a known "
            f"current pose (will NOT fall back to a hardcoded home)")
    home = state.joint_positions
    # SAFETY: same rationale as the joint home-read above, on the gripper axis. Every
    # JointCommand carries a gripper_position (B601Node re-streams joints+gripper
    # together on every poll; B601RosTransport packs it onto the wire); B601Node
    # defaults its gripper-hold value to 0.0 and never sets it on its own. Left alone,
    # first light would command the REAL gripper straight from its true (unknown)
    # position to a hardcoded 0.0 -- unbounded real gripper motion. Capture the real
    # gripper here and hold it via B601Node's public set_gripper() (called directly on
    # the node, not through the engine, so this does not add a step to eng.result()'s
    # traces) so the gripper stays exactly where it physically is, no motion at all.
    home_grip = state.gripper_position
    node = B601Node(transport, clock=clock, home=home)
    node.set_gripper(home_grip)
    eng = B601Engine(node, clock=clock)
    for wp in plan_waypoints(home, delta_max):
        eng.move_to_joints(wp)
    return eng.result()


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true",
                    help="preview clamped waypoints without ROS 2 or moving")
    ap.add_argument("--limits", default="robot_b601/b601_rs_limits.json")
    ap.add_argument("--delta-max", type=float, default=0.15)
    ap.add_argument("--command-topic", default="/rebotarm/joint_command")
    ap.add_argument("--state-topic", default="/joint_states")
    ap.add_argument("--out", default="b601_real_first_light_result.json")
    args = ap.parse_args(argv)

    limits = load_limits(args.limits)
    if args.delta_max > DELTA_MAX_WARN_CEILING:
        print(f"[WARNING] --delta-max={args.delta_max} exceeds the conservative "
              f"{DELTA_MAX_WARN_CEILING} rad ceiling for first contact -- the absolute "
              f"joint-limit clamp still backstops this, but double-check this is intended.",
              file=sys.stderr)
    if args.dry_run:
        home = [0.0] * 6                          # nominal home for the preview
        print(f"[dry-run] limits lo={limits.lo} hi={limits.hi} delta_max={args.delta_max}")
        for i, wp in enumerate(plan_waypoints(home, args.delta_max)):
            clamped, was = clamp_to_limits(wp, limits)
            print(f"[dry-run] waypoint {i}: {clamped}  clamped={was}")
        print("[dry-run] no ROS 2 connection, no motion.")
        return 0

    from robot_b601.ros_transport import B601RosTransport   # deferred: live path only
    transport = B601RosTransport(command_topic=args.command_topic,
                                 state_topic=args.state_topic, limits=limits)
    res = run(transport, RealClock(), args.delta_max)
    Path(args.out).write_text(res.to_json())
    print(f"score={res.score} primitives={len(res.traces)} -> {args.out}")
    return 0 if res.score == 1.0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
