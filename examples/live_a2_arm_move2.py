"""Live commanded arm move — assumes robot ALREADY standing in RL_LOCOMOTION_DEFAULT
(reached via: RL_JOINT_DEFAULT -> GUI 'Load key' (home_default keyframe) ->
RL_LOCOMOTION_DEFAULT). From there: stream arm hold pose (deadman), enter the stiff
RL_LOCOMOTION_ARM_EXT_JOINT_SERVO, command the move, verify, and leave the robot
balanced (never drop to DEFAULT, which collapses it).
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

JOINT, DELTA = 1, 1.00  # idx14_left_arm_joint2 (shoulder), +1.0 rad, ramped


class UrllibHttp:
    class _R:
        def __init__(self, s, b):
            self.status_code, self._b = s, b

        def json(self):
            return json.loads(self._b)

    def post(self, url, json=None):
        import json as _j
        req = urllib.request.Request(url, data=_j.dumps(json).encode(),
                                     headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=8) as r:
            return self._R(r.status, r.read())


class ArmStreamer:
    def __init__(self, node, pub):
        self._node, self._pub, self._sp = node, pub, None
        self._lock, self._run = threading.Lock(), True

    def set(self, p):
        with self._lock:
            self._sp = list(p)

    def _loop(self):
        while self._run:
            with self._lock:
                sp = self._sp
            if sp is not None:
                m = encode_arm_joint_command(JointCommand(positions=sp), RosJS)
                m.header.stamp = self._node.get_clock().now().to_msg()
                self._pub.publish(m)
            time.sleep(0.02)

    def start(self):
        threading.Thread(target=self._loop, daemon=True).start()

    def stop(self):
        self._run = False


def main():
    rpc = A2RpcClient(UrllibHttp(), host=os.environ.get("A2_HOST", "127.0.0.1"))
    print("action at start:", rpc.get_action())  # expect RL_LOCOMOTION_DEFAULT

    rclpy.init()
    node = rclpy.create_node("aspire_arm_move2")
    qos = QoSProfile(history=QoSHistoryPolicy.KEEP_LAST, depth=10,
                     reliability=QoSReliabilityPolicy.BEST_EFFORT)
    pub = node.create_publisher(RosJS, ARM_COMMAND_TOPIC, qos)
    ex = rclpy.executors.SingleThreadedExecutor()
    ex.add_node(node)
    threading.Thread(target=ex.spin, daemon=True).start()

    streamer = ArmStreamer(node, pub)
    streamer.set(rpc.joint_positions(ARM_JOINTS))  # hold current pose
    streamer.start()
    time.sleep(0.5)

    rpc.set_action("McAction_RL_LOCOMOTION_ARM_EXT_JOINT_SERVO")
    t0 = time.time()
    while time.time() - t0 < 8 and rpc.get_action() != "McAction_RL_LOCOMOTION_ARM_EXT_JOINT_SERVO":
        time.sleep(0.3)
    time.sleep(2.0)
    print("mode after servo+2s:", rpc.get_action(), "(holds if standing + deadman OK)")

    start = rpc.joint_positions(ARM_JOINTS)
    tgt = start[JOINT] + DELTA
    print(f"\n{ARM_JOINTS[JOINT]}: start={start[JOINT]:+.4f} target={tgt:+.4f} (ramped)")
    # Ramp the setpoint gradually (like arm.py), print cmd vs actual.
    N = 40
    for k in range(N + 1):
        sp = list(start)
        sp[JOINT] = start[JOINT] + (tgt - start[JOINT]) * k / N
        streamer.set(sp)
        time.sleep(0.1)
        if k % 5 == 0:
            act = rpc.joint_positions(ARM_JOINTS)[JOINT]
            print(f"  t={k*0.1:4.1f}s cmd={sp[JOINT]:+.3f} actual={act:+.3f}")
    time.sleep(1.5)
    after = rpc.joint_positions(ARM_JOINTS)[JOINT]
    moved = after - start[JOINT]
    print(f"mode={rpc.get_action()} final={after:+.4f} moved={moved:+.4f} rad "
          f"-> {'TRACKED' if abs(moved) > 0.3 else 'poor tracking'}")
    start = list(start)  # keep restore target as original full pose

    print("restoring arm; leaving robot balanced in RL_LOCOMOTION_DEFAULT")
    streamer.set(start)
    time.sleep(2.0)
    streamer.stop()
    time.sleep(0.3)
    rpc.set_action("McAction_RL_LOCOMOTION_DEFAULT")
    node.destroy_node()
    rclpy.shutdown()


if __name__ == "__main__":
    main()
