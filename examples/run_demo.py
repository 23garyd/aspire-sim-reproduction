"""End-to-end demo: drive the traced facade against the fake robot, write trace.json.

No ROS, no hardware. Shows the artifact an ASPIRE actor agent reads for failure
attribution. Run: python examples/run_demo.py
"""
import json
import tempfile

from robot_engine.ros_transport import FakeRosTransport
from robot_engine.clock import ManualClock
from robot_engine.aimdk_node import AimdkNode
from robot_engine.trace import TraceLogger
from robot_engine.robot_engine import RobotEngine


def build(gap_close):
    t = FakeRosTransport(num_joints=7, gap_close=gap_close)
    node = AimdkNode(t, "/aima/hal/joint/arm/command", "/aima/hal/joint/arm/state",
                     num_joints=7, clock=ManualClock(), poll_dt=0.01)
    return node


trial_dir = tempfile.mkdtemp(prefix="trial_")
log = TraceLogger(trial_dir)

# A healthy arm reaches a grasp pose...
robot = RobotEngine(node=build(gap_close=0.34), log=log)
r1 = robot.move_to_joints([0.5] * 7, tol=1e-3, timeout_s=10.0)

# ...then a second move stalls (models a joint hitting a limit / stuck).
robot._node = build(gap_close=0.0)
r2 = robot.move_to_joints([1.2] * 7, tol=1e-3, timeout_s=0.05)

log.write()

print(f"move 1: reached={r1.reached} status={r1.status} iters={r1.iterations}")
print(f"move 2: reached={r2.reached} status={r2.status} iters={r2.iterations}")
print(f"\ntrace.json @ {trial_dir}:\n")
print(json.dumps(json.load(open(f"{trial_dir}/trace.json")), indent=2))
