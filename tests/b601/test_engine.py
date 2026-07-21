from robot_b601.clock import ManualClock
from robot_b601.transport import FakeB601Transport
from robot_b601.node import B601Node
from robot_b601.engine import B601Engine
from aspire.schemas import ExecuteResult

def test_engine_traces_ok_primitive():
    clock = ManualClock()
    node = B601Node(FakeB601Transport(gap_close=0.5), clock=clock, poll_dt=0.02)
    eng = B601Engine(node, clock=clock)
    eng.move_to_joints([0.4]*6, tol=1e-2, timeout_s=5.0)
    eng.set_gripper(0.04, tol=1e-3, timeout_s=2.0)
    res = eng.result()
    assert isinstance(res, ExecuteResult)
    assert res.score == 1.0
    assert [t.function for t in res.traces] == ["move_to_joints", "set_gripper"]
    assert all(t.status == "ok" for t in res.traces)
    assert all(t.duration_ms >= 0.0 for t in res.traces)
    assert res.traces[0].step == 0 and res.traces[1].step == 1

def test_engine_records_timeout_as_error():
    clock = ManualClock()
    node = B601Node(FakeB601Transport(gap_close=0.0), clock=clock, poll_dt=0.02)
    eng = B601Engine(node, clock=clock)
    eng.move_to_joints([0.4]*6, tol=1e-2, timeout_s=1.0)   # stuck -> TIMEOUT
    res = eng.result()
    assert res.score == 0.0
    assert res.traces[0].status == "error"
    assert "TIMEOUT" in res.traces[0].result_summary
