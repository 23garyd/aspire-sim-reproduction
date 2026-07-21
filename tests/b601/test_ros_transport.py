import pytest
from robot_b601.transport import JointCommand, JointState
from robot_b601.limits import JointLimits

def test_module_imports_without_ros2():
    import robot_b601.ros_transport as rt      # rclpy is deferred; must import with no ROS 2
    assert hasattr(rt, "B601RosTransport")

def test_positions_from_cmd_clamps():
    from robot_b601.ros_transport import _positions_from_cmd
    lim = JointLimits(lo=[-1.0]*6, hi=[1.0]*6)
    out = _positions_from_cmd(JointCommand([2.0]*6, 0.0), lim)
    assert out == [1.0]*6                        # SAFETY: clamped before the wire

def test_state_from_positions_shape():
    from robot_b601.ros_transport import _state_from_positions
    st = _state_from_positions([0.1]*6, 0.03)
    assert isinstance(st, JointState)
    assert st.joint_positions == [0.1]*6 and st.gripper_position == 0.03

def test_publish_before_connect_raises():
    from robot_b601.ros_transport import B601RosTransport
    t = B601RosTransport()
    with pytest.raises(RuntimeError):
        t.publish(JointCommand([0.0]*6, 0.0))    # not connected -> refuse (no silent no-op)
