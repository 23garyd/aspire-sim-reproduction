"""TDD for the ROS2 arm write/read codecs (sensor_msgs/JointState <-> neutral types).

Write path: JointCommand(positions) -> sensor_msgs/JointState(name=ARM_JOINTS, position=..)
            published to /motion/control/arm_joint_command.
Read path:  sensor_msgs/JointState(name[]/position[]) -> JointState(positions in ARM order).
Tested with a duck-typed fake JointState (name/position lists), no rclpy needed.
"""
import pytest

from robot_engine.ros_transport import JointState, JointCommand
from robot_engine.a2_rpc import ARM_JOINTS
from robot_engine.a2_ros_binding import encode_arm_joint_command, decode_arm_joint_state


class FakeJS:
    def __init__(self, name=None, position=None):
        self.name = list(name or [])
        self.position = list(position or [])


def test_encode_builds_jointstate_with_14_arm_names_and_positions():
    positions = [0.1 * i for i in range(14)]
    msg = encode_arm_joint_command(JointCommand(positions=positions), FakeJS)
    assert msg.name == ARM_JOINTS
    assert msg.position == positions


def test_encode_rejects_wrong_arity():
    with pytest.raises(ValueError):
        encode_arm_joint_command(JointCommand(positions=[0.0, 0.0]), FakeJS)


def test_decode_reorders_parallel_arrays_into_arm_order():
    # Sim publishes many joints in arbitrary order; we want the 14 arm ones, in ARM order.
    names = ["idx01_left_hip_roll"] + list(reversed(ARM_JOINTS))
    positions = [9.9] + [float(i) for i in reversed(range(14))]  # matches reversed ARM order
    state = decode_arm_joint_state(FakeJS(name=names, position=positions))
    assert state == JointState(positions=[float(i) for i in range(14)])
