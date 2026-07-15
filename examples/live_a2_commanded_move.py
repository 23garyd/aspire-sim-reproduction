"""Live COMMANDED arm move on the running A2 sim (real closed loop).

Composes tested units: encode_arm_joint_command (ROS write) + A2RpcClient (HTTP read/
mode). Enters joint-servo mode, commands a small safe delta on one arm joint, streams
the setpoint via move_to_joints @50Hz over /motion/control/arm_joint_command, and reads
convergence from live GetJointState. Verifies the arm actually moved, then restores.

Run on the A2 box (needs rclpy):  PYTHONPATH=. python3 examples/live_a2_commanded_move.py
"""
import json
import os
import threading
import time
import urllib.request

import rclpy
from rclpy.qos import QoSProfile, QoSHistoryPolicy, QoSReliabilityPolicy
from sensor_msgs.msg import JointState as RosJS

from robot_engine.a2_rpc import A2RpcClient, ARM_JOINTS
from robot_engine.a2_ros_binding import encode_arm_joint_command, ARM_COMMAND_TOPIC
from robot_engine.ros_transport import JointState
from robot_engine.aimdk_node import AimdkNode
from robot_engine.clock import RealClock
from robot_engine.trace import TraceLogger
from robot_engine.robot_engine import RobotEngine

JOINT_TO_MOVE = 3          # idx16_left_arm_joint4 (elbow) — gentle, safe
DELTA = 0.30               # rad


class UrllibHttp:
    class _Resp:
        def __init__(self, status, body):
            self.status_code, self._body = status, body

        def json(self):
            return json.loads(self._body)

    def post(self, url, json=None):
        req = urllib.request.Request(
            url, data=json_dumps(json).encode(),
            headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=8) as r:
            return self._Resp(r.status, r.read())


def json_dumps(obj):
    import json as _j
    return _j.dumps(obj)


class ArmServoTransport:
    """publish -> ROS2 arm_joint_command (BEST_EFFORT); latest -> HTTP GetJointState."""

    def __init__(self, node, publisher, rpc):
        self._node, self._pub, self._rpc = node, publisher, rpc

    def publish(self, topic, cmd):
        msg = encode_arm_joint_command(cmd, RosJS)
        msg.header.stamp = self._node.get_clock().now().to_msg()
        self._pub.publish(msg)

    def latest(self, topic):
        return JointState(positions=self._rpc.joint_positions(ARM_JOINTS))


def _wait_action(rpc, target, timeout):
    t0 = time.time()
    while time.time() - t0 < timeout:
        if rpc.get_action() == target:
            return True
        time.sleep(0.5)
    return rpc.get_action() == target


def bring_to_arm_servo(rpc):
    """FSM path (action_manager/default.yaml; indirect transitions disabled):
    DEFAULT -> STAND_UP (legged stand, physical settle) -> RL_JOINT_DEFAULT (RL hold)
            -> RL_LOCOMOTION_ARM_EXT_JOINT_SERVO (stiff arm servo). Each hop is a direct
    next_action; settle time lets the physics/RL policy stabilize between hops."""
    print("current action:", rpc.get_action())
    chain = [
        ("McAction_STAND_UP", 8.0, 8.0),                        # stand physically
        ("McAction_RL_JOINT_DEFAULT", 8.0, 3.0),               # RL hold
        ("McAction_RL_LOCOMOTION_ARM_EXT_JOINT_SERVO", 8.0, 1.0),  # arm servo
    ]
    for act, wait_mode, settle in chain:
        rpc.set_action(act)
        if not _wait_action(rpc, act, wait_mode):
            print(f"  stuck before {act.split('McAction_')[-1]} (now {rpc.get_action()})")
            return None
        print(f"  reached {rpc.get_action()}; settling {settle}s")
        time.sleep(settle)
    return "RL_LOCOMOTION_ARM_EXT_JOINT_SERVO"


def main():
    host = os.environ.get("A2_HOST", "127.0.0.1")
    rpc = A2RpcClient(UrllibHttp(), host=host, port=int(os.environ.get("A2_PORT", "56322")))

    ok = bring_to_arm_servo(rpc)
    print(f"action now: {rpc.get_action()} (arm-servo ready={ok})")
    if not ok:
        print("could not reach arm-servo mode; aborting move.")
        return
    time.sleep(1.0)

    rclpy.init()
    node = rclpy.create_node("aspire_arm_commander")
    qos = QoSProfile(history=QoSHistoryPolicy.KEEP_LAST, depth=10,
                     reliability=QoSReliabilityPolicy.BEST_EFFORT)
    pub = node.create_publisher(RosJS, ARM_COMMAND_TOPIC, qos)
    executor = rclpy.executors.SingleThreadedExecutor()
    executor.add_node(node)
    threading.Thread(target=executor.spin, daemon=True).start()
    time.sleep(0.5)

    transport = ArmServoTransport(node, pub, rpc)
    aim = AimdkNode(transport, command_topic=ARM_COMMAND_TOPIC,
                    state_topic="/motion/control/arm_joint_state",
                    num_joints=14, clock=RealClock(), poll_dt=0.02)
    log = TraceLogger("/tmp/a2_cmd_move")
    robot = RobotEngine(node=aim, log=log)

    start = rpc.joint_positions(ARM_JOINTS)
    target = list(start)
    target[JOINT_TO_MOVE] += DELTA
    print(f"\njoint {ARM_JOINTS[JOINT_TO_MOVE]}: start={start[JOINT_TO_MOVE]:+.4f} "
          f"target={target[JOINT_TO_MOVE]:+.4f}")

    result = robot.move_to_joints(target, tol=0.03, timeout_s=8.0)
    after = rpc.joint_positions(ARM_JOINTS)
    moved = after[JOINT_TO_MOVE] - start[JOINT_TO_MOVE]
    print(f"move_to_joints -> reached={result.reached} status={result.status} "
          f"residual={result.residual:.4f} iters={result.iterations}")
    print(f"VERIFY via GetJointState: joint moved {moved:+.4f} rad "
          f"(now {after[JOINT_TO_MOVE]:+.4f}) -> {'MOVED' if abs(moved) > 0.1 else 'no motion'}")

    print("\nrestoring original pose...")
    robot.move_to_joints(start, tol=0.03, timeout_s=8.0)
    rpc.set_action("McAction_RL_JOINT_DEFAULT")  # safe standing hold (direct neighbor)
    log.write()
    print(f"trace.json: {len(log.records)} records @ {log.trial_dir}")
    node.destroy_node()
    rclpy.shutdown()


if __name__ == "__main__":
    main()
