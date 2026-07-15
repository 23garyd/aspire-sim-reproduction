"""ROS2 arm codecs for the A2 sim, plus a helper to build the live write transport.

The A2 arm joint-servo interface is a ROS2 topic pair (confirmed on the running sim):
  * write: sensor_msgs/JointState -> /motion/control/arm_joint_command  (stream targets)
  * read:  sensor_msgs/JointState <- /motion/control/arm_joint_state

These codecs bridge the engine's neutral JointCommand/JointState (positions in ARM_JOINTS
order) to/from sensor_msgs/JointState (parallel name[]/position[] arrays). rclpy is only
needed by make_arm_write_transport (guarded via RclpyTransport).
"""
from __future__ import annotations

from robot_engine.ros_transport import JointCommand, JointState
from robot_engine.a2_rpc import ARM_JOINTS

ARM_COMMAND_TOPIC = "/motion/control/arm_joint_command"
ARM_STATE_TOPIC = "/motion/control/arm_joint_state"


def encode_arm_joint_command(cmd: JointCommand, JointStateCls):
    if len(cmd.positions) != len(ARM_JOINTS):
        raise ValueError(
            f"expected {len(ARM_JOINTS)} arm positions, got {len(cmd.positions)}")
    msg = JointStateCls()
    msg.name = list(ARM_JOINTS)
    msg.position = list(cmd.positions)
    return msg


def decode_arm_joint_state(msg) -> JointState:
    by_name = dict(zip(msg.name, msg.position))
    return JointState(positions=[by_name[n] for n in ARM_JOINTS])


def make_arm_write_transport(node, JointStateCls):
    """Build an RclpyTransport wired for the arm servo pair, using the codecs above."""
    from robot_engine.rclpy_transport import RclpyTransport

    tp = RclpyTransport(node)
    tp.register_publisher(ARM_COMMAND_TOPIC, JointStateCls,
                          encode=lambda cmd, cls: encode_arm_joint_command(cmd, cls))
    tp.register_subscription(ARM_STATE_TOPIC, JointStateCls,
                             decode=decode_arm_joint_state)
    return tp
