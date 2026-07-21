from robot_b601.clock import ManualClock
from robot_b601.transport import FakeB601Transport
from robot_b601.node import B601Node

def _node(gap_close):
    return B601Node(FakeB601Transport(num_joints=6, gap_close=gap_close),
                    clock=ManualClock(), poll_dt=0.02)

def test_move_reaches_target():
    r = _node(0.5).move_to_joints([0.5]*6, tol=1e-2, timeout_s=5.0)
    assert r.reached and r.status == "ok" and r.residual < 1e-2

def test_move_times_out_on_stuck_arm():
    r = _node(0.0).move_to_joints([0.5]*6, tol=1e-2, timeout_s=1.0)
    assert not r.reached and r.status == "TIMEOUT"

def test_gripper_reaches_and_holds_joints():
    node = _node(0.5)
    node.move_to_joints([0.3]*6, tol=1e-2, timeout_s=5.0)
    g = node.set_gripper(0.04, tol=1e-3, timeout_s=2.0)
    assert g.reached and g.status == "ok"
