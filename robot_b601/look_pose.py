"""Shared M3b look-pose helper: hold the REAL gripper and refuse to move blind.

B601Node re-streams the full setpoint (joints + gripper) together on every poll and
initializes _last_grip = 0.0, never setting it on its own (see robot_b601/node.py).
Any caller that does a bare node.move_to_joints(...) without first seeding the
gripper would command the REAL gripper straight from its true (unknown) position to
a hardcoded 0.0 on the very first publish -- unbounded real gripper motion. This
mirrors the fix already proven in scripts/b601_real_first_light.py (its
_wait_for_state + set_gripper(state.gripper_position) pattern); both b601_perceive_cube.py
and the upcoming calibration runner reuse it here instead of duplicating it.

Stdlib + robot_b601 only. Duck-typed over transport/node/clock (no imports of
pyrealsense2/rclpy/numpy) so this module is safe to import with no hardware present.
"""
from __future__ import annotations


def wait_for_state(transport, clock, timeout_s: float = 2.0, poll_dt: float = 0.01):
    """Poll transport.latest() on the injected clock until a real state arrives, or
    return None once timeout_s elapses. Mirrors b601_real_first_light.py's
    _wait_for_state idiom exactly (same now()/sleep() clock usage) so this is
    deterministic and testable with ManualClock."""
    t0 = clock.now()
    while True:
        state = transport.latest()
        if state is not None:
            return state
        if clock.now() - t0 >= timeout_s:
            return None
        clock.sleep(poll_dt)


def move_to_look_pose(transport, node, clock, joints, timeout_s: float = 2.0):
    """Move node to a look pose while holding the REAL gripper at its true current
    position. Fails loud (RuntimeError) if no joint state arrives within timeout_s
    instead of falling back to a blind move -- never move without a known current
    pose/gripper."""
    state = wait_for_state(transport, clock, timeout_s)
    if state is None:
        raise RuntimeError(
            f"move_to_look_pose: no joint state received within {timeout_s}s -- "
            f"refusing to move without a known current pose/gripper (will NOT "
            f"blind-move)")
    # SAFETY: hold the real gripper exactly where it physically is (no motion at
    # all) before moving the joints, so B601Node's re-streamed JointCommand never
    # snaps it to the hardcoded 0.0 default.
    node.set_gripper(state.gripper_position)
    node.move_to_joints(joints)
    return state
