import pytest

from robot_b601.clock import ManualClock
from robot_b601.transport import FakeB601Transport
from robot_b601.node import B601Node
from robot_b601 import look_pose


class _GripperReportingFakeTransport:
    """Same recording-wrapper pattern as tests/b601/test_real_first_light.py's
    _GripperReportingFakeTransport: FakeB601Transport always starts its gripper at
    0.0, which can't distinguish "held the real gripper" from "commanded the
    hardcoded 0.0 default" -- both look like 0.0. Wrap it so latest() reports a
    real, non-zero starting gripper, and record every published JointCommand so
    the test can assert on the commanded gripper value without touching
    robot_b601/transport.py."""

    def __init__(self, start, grip_start):
        self._inner = FakeB601Transport(start=start)
        self._inner._grip_cur = grip_start
        self._inner._grip_tgt = grip_start
        self.published = []

    def publish(self, cmd):
        self.published.append(cmd)
        return self._inner.publish(cmd)

    def latest(self):
        return self._inner.latest()


class _NeverReportsTransport:
    """connect()-less analog of test_real_first_light.py's _NeverReportsTransport:
    simulates a /joint_states topic that hasn't published yet -- latest() never
    returns a state. Used to prove move_to_look_pose fails loud instead of
    blind-moving the real arm from an unknown pose."""

    def __init__(self):
        self.publish_calls = 0

    def publish(self, cmd):
        self.publish_calls += 1

    def latest(self):
        return None


def test_move_to_look_pose_holds_real_gripper_not_hardcoded_zero():
    """SAFETY: this must fail against the pre-fix perceive_cube code path (a bare
    node.move_to_joints(look) with no gripper seed), because B601Node initializes
    _last_grip = 0.0 and re-publishes joints+gripper together every poll -- so the
    real gripper would snap from its true (unknown, non-zero) position to a
    hardcoded 0.0 on the very first publish."""
    home = [0.1, -0.2, 0.0, 0.3, -0.1, 0.2]
    look = [0.0, -0.3, 0.6, 0.0, 0.9, 0.0]
    real_grip = 0.041
    transport = _GripperReportingFakeTransport(start=home, grip_start=real_grip)
    clock = ManualClock()
    node = B601Node(transport, clock=clock, home=home)

    state = look_pose.move_to_look_pose(transport, node, clock, look)

    assert state.gripper_position == real_grip
    assert transport.published, "no commands were published to the transport"
    for cmd in transport.published:
        assert cmd.gripper_position == real_grip
        assert cmd.gripper_position != 0.0
    # the joints commanded on the final publish are the requested look pose
    assert transport.published[-1].joint_positions == look


def test_move_to_look_pose_fails_loud_when_no_state_arrives():
    """No /joint_states ever arrives -> refuse to move at all (no blind move)."""
    transport = _NeverReportsTransport()
    clock = ManualClock()
    node = B601Node(transport, clock=clock, home=[0.0] * 6)

    with pytest.raises(RuntimeError):
        look_pose.move_to_look_pose(transport, node, clock, [0.0] * 6, timeout_s=0.05)

    assert transport.publish_calls == 0    # no move was ever commanded to the real arm
