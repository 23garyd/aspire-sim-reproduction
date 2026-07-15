"""Diagnose whether the robot holds RL arm-servo mode or reverts (falls) to DEFAULT."""
import json
import os
import time
import urllib.request

from robot_engine.a2_rpc import A2RpcClient


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


def main():
    rpc = A2RpcClient(UrllibHttp(), host=os.environ.get("A2_HOST", "127.0.0.1"))
    http = rpc._http

    def base_z():
        try:
            d = http.post("http://127.0.0.1:56322/rpc/aimdk.protocol.McBaseService/GetState",
                          json={"header": {"control_source": "ControlSource_SAFE"}}).json()
            return json.dumps(d)[:200]
        except Exception as e:
            return f"(GetState err {e})"

    print("start:", rpc.get_action())
    for act, settle in [("McAction_STAND_UP", 8), ("McAction_RL_JOINT_DEFAULT", 3),
                        ("McAction_RL_LOCOMOTION_ARM_EXT_JOINT_SERVO", 1)]:
        rpc.set_action(act)
        t0 = time.time()
        while time.time() - t0 < 8 and rpc.get_action() != act:
            time.sleep(0.5)
        print(f"set {act.split('McAction_')[-1]:34s} -> {rpc.get_action()}")
        time.sleep(settle)
    print("\nHOLDING? polling mode for 8s:")
    for i in range(8):
        time.sleep(1)
        print(f"  t+{i+1}s: {rpc.get_action()}")
    print("\nbase state:", base_z())


if __name__ == "__main__":
    main()
