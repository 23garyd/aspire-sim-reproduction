"""Real B601-RS transport over ROS 2 — the hardware counterpart of M1's Isaac UDP
transport, behind the SAME B601Transport seam (so B601Node/B601Engine are unchanged).
rclpy + sensor_msgs are DEFERRED-imported (inside connect/_publish/_read) so this
module and its pure helpers import and test WITHOUT ROS 2. Every command is clamped to
joint limits before the wire (safety). The exact controller command topic/msg is
confirmed on-bench against rebotarm_bringup; the clamped-positions helper is not
affected by that choice."""
from __future__ import annotations

from robot_b601.limits import DEFAULT_LIMITS, clamp_to_limits
from robot_b601.transport import JointState


def _positions_from_cmd(cmd, limits) -> list:
    clamped, _ = clamp_to_limits(cmd.joint_positions, limits)
    return clamped


def _state_from_positions(positions, gripper) -> JointState:
    return JointState(joint_positions=list(positions), gripper_position=float(gripper))


class B601RosTransport:
    def __init__(self, command_topic: str = "/rebotarm/joint_command",
                 state_topic: str = "/joint_states", limits=None,
                 node_name: str = "b601_aspire"):
        self._cmd_topic = command_topic
        self._state_topic = state_topic
        self._limits = limits or DEFAULT_LIMITS
        self._node_name = node_name
        self._node = None
        self._pub = None
        self._latest_positions = None

    def connect(self) -> None:
        """Live only: bring up the rclpy node, command publisher, and /joint_states
        subscriber + spin thread. Confirm the command topic/controller interface here
        against rebotarm_bringup on-bench (position vs trajectory controller, gripper
        joint index) — this is the one on-bench-finalized detail."""
        import threading

        import rclpy
        from rclpy.node import Node
        from sensor_msgs.msg import JointState as RosJointState

        rclpy.init(args=None)
        self._node = Node(self._node_name)
        self._pub = self._node.create_publisher(RosJointState, self._cmd_topic, 10)

        def _on_state(msg):
            self._latest_positions = list(msg.position)

        self._node.create_subscription(RosJointState, self._state_topic, _on_state, 10)
        threading.Thread(target=rclpy.spin, args=(self._node,), daemon=True).start()

    def publish(self, cmd) -> None:
        positions = _positions_from_cmd(cmd, self._limits)     # SAFETY: clamp before wire
        if self._pub is None:
            raise RuntimeError(
                "B601RosTransport.connect() must be called before publish (live ROS 2 only)")
        from sensor_msgs.msg import JointState as RosJointState
        msg = RosJointState()
        msg.position = list(positions) + [float(cmd.gripper_position)]
        self._pub.publish(msg)

    def latest(self):
        p = self._latest_positions
        if p is None:
            return None
        # convention (confirm on-bench): first 6 = arm joints, last = gripper if present
        joints = list(p[:6])
        gripper = float(p[6]) if len(p) > 6 else 0.0
        return _state_from_positions(joints, gripper)
