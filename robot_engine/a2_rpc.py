"""A2 HTTP-RPC binding (AgiBot A2 sim / v1.3 firmware).

The A2 serves request/response services over HTTP on :56322 (motion PC). This module
covers the confirmed-schema services the sync facade needs for its READ / mode path:

  * McDataService/GetJointState  -> per-joint {position, velocity, effort}
  * McActionService/SetAction    -> enter an action mode (e.g. joint-servo)
  * McActionService/GetAvailableActions

The WRITE path (streaming arm joint targets) is ROS2 — publish sensor_msgs/JointState to
/motion/control/arm_joint_command via RclpyTransport — so it is NOT here.

Duck-typed on an httpx-style client: `http.post(url, json=...) -> resp` with
`.status_code` and `.json()`. Pass FakeHttp in tests; a urllib/httpx client live.
"""
from __future__ import annotations

import time
from typing import Any

from robot_engine.ros_transport import JointState

# 7-DoF-per-arm bimanual, in the sim's idx order (from live GetJointState).
ARM_JOINTS = [f"idx{13 + i}_left_arm_joint{i + 1}" for i in range(7)] + \
             [f"idx{20 + i}_right_arm_joint{i + 1}" for i in range(7)]

_RPC_BASE = "http://{host}:{port}/rpc/aimdk.protocol"


class A2RpcError(RuntimeError):
    def __init__(self, code, msg):
        super().__init__(f"A2 RPC error code={code}: {msg}")
        self.code, self.msg = code, msg


def _header(control_source: str = "ControlSource_SAFE") -> dict:
    now = time.time()
    return {
        "timestamp": {"seconds": int(now), "nanos": int((now % 1) * 1e9),
                      "ms_since_epoch": int(now * 1000)},
        "control_source": control_source,
    }


class A2RpcClient:
    def __init__(self, http, host: str = "127.0.0.1", port: int = 56322):
        self._http = http
        self._base = _RPC_BASE.format(host=host, port=port)

    def _call(self, service: str, method: str, payload: dict) -> dict:
        resp = self._http.post(f"{self._base}.{service}/{method}", json=payload)
        status = getattr(resp, "status_code", 200)
        if status != 200:
            raise A2RpcError(f"http{status}", "transport")
        data = resp.json()
        code = str(data.get("header", {}).get("code", "0"))
        if code != "0":
            raise A2RpcError(code, data.get("header", {}).get("msg", ""))
        return data

    def get_joint_state(self) -> dict[str, dict]:
        data = self._call("McDataService", "GetJointState", {"header": _header()})
        return {s["name"]: s for s in data.get("states", [])}

    def joint_positions(self, joint_order: list[str]) -> list[float]:
        states = self.get_joint_state()
        return [states[name]["position"] for name in joint_order]

    def get_available_actions(self) -> list[Any]:
        data = self._call("McActionService", "GetAvailableActions", {"header": _header()})
        return data.get("actions", data.get("commands", []))

    def set_action(self, action: str) -> dict:
        # A2 wraps ext actions in a USE_EXT_CMD envelope (from vendor SetAction.py).
        return self._call("McActionService", "SetAction", {
            "header": _header(),
            "command": {"action": "McAction_USE_EXT_CMD", "ext_action": action},
        })

    def get_action(self) -> str:
        data = self._call("McActionService", "GetAction", {})
        return data["info"]["current_action"]

    def ensure_action(self, action: str, retries: int = 3,
                      retry_interval: float = 0.5) -> bool:
        """Set the action and confirm via GetAction (vendor pattern) — SetAction alone
        returns 'ok' without guaranteeing the mode switched."""
        for _ in range(retries):
            if self.get_action() == action:
                return True
            self.set_action(action)
            if retry_interval:
                time.sleep(retry_interval)
        return self.get_action() == action


class A2RpcJointStateSource:
    """Adapts A2RpcClient to the RosTransport interface for the facade's READ path:
    latest() returns a JointState of positions in `joint_order`. publish() is a no-op
    (the write path is ROS2), so it can back a read-only convergence check against
    live joint telemetry."""

    def __init__(self, client: A2RpcClient, joint_order: list[str] = ARM_JOINTS):
        self._client = client
        self._order = joint_order

    def publish(self, topic: str, msg) -> None:
        # write path is ROS2 (/motion/control/arm_joint_command); nothing to do here
        return None

    def latest(self, topic: str) -> JointState:
        return JointState(positions=self._client.joint_positions(self._order))
