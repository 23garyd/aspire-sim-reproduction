"""TDD for the @trace decorator composing with the AimdkNode blocking loop.

This is the end-to-end validation goal: a traced RobotEngine primitive drives the
sync facade (which converges against the fake robot) AND emits one faithful
TraceRecord — all with zero hardware.
"""
from robot_engine.ros_transport import FakeRosTransport
from robot_engine.clock import ManualClock
from robot_engine.aimdk_node import AimdkNode
from robot_engine.trace import TraceLogger
from robot_engine.robot_engine import RobotEngine


def make_engine(gap_close):
    transport = FakeRosTransport(num_joints=7, gap_close=gap_close)
    node = AimdkNode(transport, command_topic="/aima/hal/joint/arm/command",
                     state_topic="/aima/hal/joint/arm/state", num_joints=7,
                     clock=ManualClock(), poll_dt=0.01)
    return RobotEngine(node=node, log=TraceLogger(trial_dir="/tmp/unused"))


def test_traced_move_converges_and_emits_one_record():
    engine = make_engine(gap_close=0.34)

    result = engine.move_to_joints([0.5] * 7, tol=1e-3, timeout_s=10.0)

    # blocking loop worked
    assert result.reached is True
    # exactly one trace record, faithful to the call
    assert len(engine._log.records) == 1
    rec = engine._log.records[0]
    assert rec.step == 1
    assert rec.function == "move_to_joints"
    assert rec.status == "ok"
    assert rec.result["reached"] is True
    assert rec.args["joints"] == {"len": 7}       # arrays summarized, not dumped raw
    assert rec.duration_ms >= 0.0


def test_traced_move_records_timeout_status():
    engine = make_engine(gap_close=0.0)

    engine.move_to_joints([0.5] * 7, tol=1e-3, timeout_s=0.05)

    rec = engine._log.records[0]
    assert rec.status == "TIMEOUT"
    assert rec.result["reached"] is False
