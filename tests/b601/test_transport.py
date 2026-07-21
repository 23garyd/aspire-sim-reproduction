from robot_b601.transport import JointCommand, JointState, FakeB601Transport

def test_fake_converges_toward_target():
    t = FakeB601Transport(num_joints=6, gap_close=0.5)
    t.publish(JointCommand([1.0]*6, 0.04))
    s1 = t.latest()
    assert isinstance(s1, JointState)
    assert all(0.0 < p < 1.0 for p in s1.joint_positions)   # advanced, not yet there
    for _ in range(50):
        s = t.latest()
    assert all(abs(p - 1.0) < 1e-3 for p in s.joint_positions)   # converged
    assert abs(s.gripper_position - 0.04) < 1e-3

def test_fake_stuck_never_moves():
    t = FakeB601Transport(num_joints=6, gap_close=0.0)   # stuck robot
    t.publish(JointCommand([1.0]*6, 0.04))
    for _ in range(100):
        s = t.latest()
    assert all(p == 0.0 for p in s.joint_positions)      # never advanced -> exercises TIMEOUT
