"""TDD for the AimdkNode sync facade over async ROS2 topics.

The facade turns AimDK's async topic pattern (publish JointCommand, subscribe
JointState) into ASPIRE's synchronous blocking `move_to_joints`. Tests run
against a FakeRosTransport that models a robot converging toward its command,
so no ROS/hardware is required.
"""
from robot_engine.ros_transport import FakeRosTransport
from robot_engine.clock import ManualClock
from robot_engine.aimdk_node import AimdkNode


def make_node(transport, clock, **kw):
    return AimdkNode(
        transport,
        command_topic="/aima/hal/joint/arm/command",
        state_topic="/aima/hal/joint/arm/state",
        num_joints=7,
        clock=clock,
        poll_dt=0.01,
        **kw,
    )


def test_move_to_joints_blocks_until_converged():
    # Robot closes 34% of the gap to target on each state tick.
    transport = FakeRosTransport(num_joints=7, gap_close=0.34)
    node = make_node(transport, ManualClock())

    result = node.move_to_joints([0.5] * 7, tol=1e-3, timeout_s=10.0)

    assert result.reached is True
    assert result.status == "ok"
    assert result.residual < 1e-3


def test_move_to_joints_streams_setpoint_every_poll():
    # Real joint-servo controllers need the setpoint restreamed continuously
    # (arm.py streams at 50Hz). The loop must publish each iteration, not once.
    class CountingTransport(FakeRosTransport):
        def __init__(self):
            super().__init__(num_joints=7, gap_close=0.0)  # never converges
            self.publishes = 0

        def publish(self, topic, msg):
            self.publishes += 1
            super().publish(topic, msg)

    t = CountingTransport()
    node = make_node(t, ManualClock())
    result = node.move_to_joints([0.5] * 7, tol=1e-3, timeout_s=0.05)

    assert result.status == "TIMEOUT"
    assert t.publishes == result.iterations  # one setpoint publish per poll


def test_move_to_joints_times_out_when_robot_stuck():
    # gap_close=0.0 -> joints never move toward target.
    transport = FakeRosTransport(num_joints=7, gap_close=0.0)
    node = make_node(transport, ManualClock())

    result = node.move_to_joints([0.5] * 7, tol=1e-3, timeout_s=0.05)

    assert result.reached is False
    assert result.status == "TIMEOUT"
    assert result.residual == 0.5  # full gap never closed
