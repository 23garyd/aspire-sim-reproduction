"""Probe the A2 action state-machine transitions (no rclpy). Uses A2RpcClient."""
import json
import os
import time
import urllib.request

from robot_engine.a2_rpc import A2RpcClient


class UrllibHttp:
    class _Resp:
        def __init__(self, status, body):
            self.status_code, self._body = status, body

        def json(self):
            return json.loads(self._body)

    def post(self, url, json=None):
        import json as _j
        req = urllib.request.Request(url, data=_j.dumps(json).encode(),
                                     headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=8) as r:
            return self._Resp(r.status, r.read())


def main():
    rpc = A2RpcClient(UrllibHttp(), host=os.environ.get("A2_HOST", "127.0.0.1"))
    print("start:", rpc.get_action())
    seq = [
        "McAction_MOBILE_PLATFORM_STAND_UP",
        "McAction_RL_LOCOMOTION_DEFAULT",
        "McAction_RL_LOCOMOTION_ARM_EXT_JOINT_SERVO",
    ]
    for act in seq:
        rpc.set_action(act)
        time.sleep(1.5)
        print(f"after set {act.split('McAction_')[-1]:38s} -> current = {rpc.get_action()}")


if __name__ == "__main__":
    main()
