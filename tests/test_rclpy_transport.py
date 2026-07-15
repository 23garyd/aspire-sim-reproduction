"""TDD for RclpyTransport — the real ROS side, exercised without rclpy.

The transport takes an already-constructed node exposing rclpy's Node surface
(create_publisher / create_subscription). Tests inject a FakeNode, so the encode/
decode + latest-message-cache logic is verified with no ROS installed. Only the
thin create() factory touches rclpy (covered by the guard test).
"""
from dataclasses import dataclass

import pytest

from robot_engine.ros_transport import JointCommand, JointState, RosTransport
from robot_engine.rclpy_transport import RclpyTransport
from robot_engine.aimdk_node import AimdkNode
from robot_engine.clock import ManualClock


@dataclass
class FakeMsg:
    positions: list


class FakePublisher:
    def __init__(self, sink, topic):
        self._sink, self._topic = sink, topic

    def publish(self, msg):
        self._sink.append((self._topic, msg))


class FakeNode:
    """Mimics the rclpy Node methods RclpyTransport uses."""

    def __init__(self):
        self.published = []
        self._subs = {}

    def create_publisher(self, msg_type, topic, qos):
        return FakePublisher(self.published, topic)

    def create_subscription(self, msg_type, topic, callback, qos):
        self._subs[topic] = callback
        return object()

    def deliver(self, topic, msg):
        self._subs[topic](msg)


def make_transport(node):
    tp = RclpyTransport(node)
    tp.register_publisher("/aima/hal/joint/arm/command", FakeMsg,
                          encode=lambda cmd, cls: cls(positions=list(cmd.positions)))
    tp.register_subscription("/aima/hal/joint/arm/state", FakeMsg,
                             decode=lambda m: JointState(positions=list(m.positions)))
    return tp


def test_publish_encodes_neutral_to_ros_msg_and_sends():
    node = FakeNode()
    tp = make_transport(node)

    tp.publish("/aima/hal/joint/arm/command", JointCommand(positions=[0.1, 0.2]))

    assert node.published == [("/aima/hal/joint/arm/command", FakeMsg(positions=[0.1, 0.2]))]


def test_latest_decodes_cached_subscription_message():
    node = FakeNode()
    tp = make_transport(node)

    node.deliver("/aima/hal/joint/arm/state", FakeMsg(positions=[0.3, 0.4]))

    assert tp.latest("/aima/hal/joint/arm/state") == JointState(positions=[0.3, 0.4])


def test_latest_returns_none_before_any_message():
    tp = make_transport(FakeNode())
    assert tp.latest("/aima/hal/joint/arm/state") is None


def test_conforms_to_ros_transport_protocol():
    assert isinstance(make_transport(FakeNode()), RosTransport)


def test_aimdk_node_drives_move_over_rclpy_transport():
    # The sync facade is transport-agnostic: the same move_to_joints loop that ran
    # over FakeRosTransport runs unchanged over RclpyTransport (fake node here).
    state_topic = "/aima/hal/joint/arm/state"
    node = FakeNode()
    tp = make_transport(node)
    aim = AimdkNode(tp, command_topic="/aima/hal/joint/arm/command",
                    state_topic=state_topic, num_joints=7,
                    clock=ManualClock(), poll_dt=0.01)

    # robot already reporting the target pose (spin thread would deliver this live)
    node.deliver(state_topic, FakeMsg(positions=[0.5] * 7))
    result = aim.move_to_joints([0.5] * 7, tol=1e-3, timeout_s=1.0)

    assert result.reached is True
    assert result.status == "ok"


def test_create_raises_clear_error_when_rclpy_missing(monkeypatch):
    # Deterministically simulate a machine without ROS2 by masking rclpy in
    # sys.modules (setting it to None makes `import rclpy` raise ImportError).
    # This passes whether or not rclpy is actually installed on the host.
    import sys
    monkeypatch.setitem(sys.modules, "rclpy", None)
    with pytest.raises(RuntimeError, match="rclpy is not available"):
        RclpyTransport.create()
