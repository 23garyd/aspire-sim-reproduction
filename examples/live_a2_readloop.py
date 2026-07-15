"""Live validation against the running A2 sim RPC on :56322.

Pulls real joint telemetry through A2RpcClient, then runs the actual
AimdkNode.move_to_joints blocking loop against live state via the RPC read path:
  - target == current live pose  -> converges (reached=True)
  - target == current + offset   -> read-only source never moves -> TIMEOUT

Proves the sync facade + trace logger work against the real sim. Stdlib only.
Run on the A2 box: PYTHONPATH=. python3 examples/live_a2_readloop.py
"""
import json
import os
import tempfile
import urllib.request

from robot_engine.a2_rpc import A2RpcClient, A2RpcJointStateSource, ARM_JOINTS
from robot_engine.aimdk_node import AimdkNode
from robot_engine.clock import RealClock
from robot_engine.trace import TraceLogger
from robot_engine.robot_engine import RobotEngine


class UrllibHttp:
    """Minimal httpx-shaped client: .post(url, json=...) -> resp(.status_code/.json())."""

    class _Resp:
        def __init__(self, status, body):
            self.status_code, self._body = status, body

        def json(self):
            return json.loads(self._body)

    def post(self, url, json=None):
        data = (json_lib_dumps(json)).encode()
        req = urllib.request.Request(url, data=data,
                                     headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=8) as r:
            return self._Resp(r.status, r.read())


def json_lib_dumps(obj):
    import json as _j
    return _j.dumps(obj)


def main():
    host = os.environ.get("A2_HOST", "127.0.0.1")
    port = int(os.environ.get("A2_PORT", "56322"))
    client = A2RpcClient(UrllibHttp(), host=host, port=port)

    live = client.joint_positions(ARM_JOINTS)
    print(f"LIVE 14 arm joint positions from {host}:{port}:")
    for name, pos in zip(ARM_JOINTS, live):
        print(f"  {name:24s} {pos:+.5f}")

    source = A2RpcJointStateSource(client, joint_order=ARM_JOINTS)
    node = AimdkNode(source, command_topic="/motion/control/arm_joint_command",
                     state_topic="/motion/control/arm_joint_state",
                     num_joints=14, clock=RealClock(), poll_dt=0.05)
    log = TraceLogger(tempfile.mkdtemp(prefix="a2live_"))
    robot = RobotEngine(node=node, log=log)

    r_hold = robot.move_to_joints(live, tol=1e-2, timeout_s=2.0)
    print(f"\nmove_to_joints(current pose)   -> reached={r_hold.reached} "
          f"status={r_hold.status} residual={r_hold.residual:.4f}")

    target = [p + 0.05 for p in live]
    r_move = robot.move_to_joints(target, tol=1e-3, timeout_s=1.0)
    print(f"move_to_joints(current+0.05)   -> reached={r_move.reached} "
          f"status={r_move.status} residual={r_move.residual:.4f}  (read-only: no command sent)")

    log.write()
    print(f"\ntrace.json written with {len(log.records)} records @ {log.trial_dir}")


if __name__ == "__main__":
    main()
