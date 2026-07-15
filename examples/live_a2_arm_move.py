"""Live commanded arm move on the A2 sim — with the deadman-satisfying stream.

Key fix over the earlier attempt: RL_LOCOMOTION_ARM_EXT_JOINT_SERVO is an *external*
joint-servo mode with a deadman watchdog — if no arm command streams, it faults back to
passive DEFAULT. So we start a 50Hz background stream of the current (hold) pose BEFORE
entering the servo mode, keep it running, then update the setpoint to move.

FSM path (from action_manager/default.yaml): DEFAULT -> STAND_UP -> RL_JOINT_DEFAULT ->
RL_LOCOMOTION_ARM_EXT_JOINT_SERVO.

Run in the container: PYTHONPATH=.:$PYTHONPATH python3 examples/live_a2_arm_move.py
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
from robot_engine.ros_transport import JointCommand

JOINT = 3        # idx16_left_arm_joint4 (elbow)
DELTA = 0.30


class UrllibHttp:
    class _Resp:
        def __init__(self, s, b):
            self.status_code, self._b = s, b

        def json(self):
            return json.loads(self._b)

    def post(self, url, json=None):
        import json as _j
        req = urllib.request.Request(url, data=_j.dumps(json).encode(),
                                     headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=8) as r:
            return self._Resp(r.status, r.read())


class ArmStreamer:
    """Publishes the current setpoint to arm_joint_command at 50Hz (like arm.py),
    satisfying the servo deadman. Thread-safe setpoint update."""

    def __init__(self, node, pub):
        self._node, self._pub = node, pub
        self._sp, self._lock, self._run = None, threading.Lock(), True

    def set(self, positions):
        with self._lock:
            self._sp = list(positions)

    def _loop(self):
        while self._run:
            with self._lock:
                sp = self._sp
            if sp is not None:
                msg = encode_arm_joint_command(JointCommand(positions=sp), RosJS)
                msg.header.stamp = self._node.get_clock().now().to_msg()
                self._pub.publish(msg)
            time.sleep(0.02)

    def start(self):
        threading.Thread(target=self._loop, daemon=True).start()

    def stop(self):
        self._run = False


def wait_mode(rpc, target, timeout):
    t0 = time.time()
    while time.time() - t0 < timeout:
        if rpc.get_action() == target:
            return True
        time.sleep(0.4)
    return rpc.get_action() == target


def main():
    rpc = A2RpcClient(UrllibHttp(), host=os.environ.get("A2_HOST", "127.0.0.1"))

    rclpy.init()
    node = rclpy.create_node("aspire_arm_move")
    qos = QoSProfile(history=QoSHistoryPolicy.KEEP_LAST, depth=10,
                     reliability=QoSReliabilityPolicy.BEST_EFFORT)
    pub = node.create_publisher(RosJS, ARM_COMMAND_TOPIC, qos)
    ex = rclpy.executors.SingleThreadedExecutor()
    ex.add_node(node)
    threading.Thread(target=ex.spin, daemon=True).start()
    streamer = ArmStreamer(node, pub)
    streamer.start()

    print("current action:", rpc.get_action())
    # Stand and enter RL hold (no arm stream needed yet).
    for act, settle in [("McAction_STAND_UP", 8), ("McAction_RL_JOINT_DEFAULT", 3)]:
        rpc.set_action(act)
        wait_mode(rpc, act, 8)
        print(f"  reached {rpc.get_action()}; settle {settle}s")
        time.sleep(settle)

    # Robot standing: begin streaming the HOLD pose, THEN enter servo (deadman satisfied).
    hold = rpc.joint_positions(ARM_JOINTS)
    streamer.set(hold)
    time.sleep(0.5)
    rpc.set_action("McAction_RL_LOCOMOTION_ARM_EXT_JOINT_SERVO")
    wait_mode(rpc, "McAction_RL_LOCOMOTION_ARM_EXT_JOINT_SERVO", 8)
    time.sleep(2.0)
    print(f"mode after entering servo + 2s: {rpc.get_action()}  (holds if stream works)")

    # Command the move by updating the streamed setpoint.
    start = rpc.joint_positions(ARM_JOINTS)
    target = list(start)
    target[JOINT] += DELTA
    print(f"\n{ARM_JOINTS[JOINT]}: start={start[JOINT]:+.4f} target={target[JOINT]:+.4f}")
    streamer.set(target)
    t0, reached = time.time(), False
    while time.time() - t0 < 8.0:
        time.sleep(0.2)
        now = rpc.joint_positions(ARM_JOINTS)[JOINT]
        if abs(now - target[JOINT]) < 0.03:
            reached = True
            break
    after = rpc.joint_positions(ARM_JOINTS)[JOINT]
    print(f"reached={reached} mode={rpc.get_action()} now={after:+.4f} "
          f"moved={after - start[JOINT]:+.4f} rad -> {'MOVED' if abs(after-start[JOINT])>0.1 else 'no motion'}")

    print("restoring + releasing...")
    streamer.set(start)
    time.sleep(2.0)
    streamer.stop()
    rpc.set_action("McAction_RL_JOINT_DEFAULT")
    node.destroy_node()
    rclpy.shutdown()


if __name__ == "__main__":
    main()
