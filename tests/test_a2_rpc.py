"""TDD for the A2 HTTP-RPC binding (McDataService/GetJointState, McActionService).

The A2 sim serves request/response services over HTTP on :56322. This client is
duck-typed on an httpx-style object (`.post(url, json=...) -> resp` with
`.status_code` / `.json()`), mirroring the vendor adapter's FakeHttpClient, so it's
fully unit-testable and later live-validated against the running sim.

Response schemas are taken verbatim from live sim calls.
"""
import pytest

from robot_engine.ros_transport import JointState, RosTransport
from robot_engine.a2_rpc import A2RpcClient, A2RpcError, A2RpcJointStateSource, ARM_JOINTS


class FakeResp:
    def __init__(self, payload, status=200):
        self._payload, self.status_code = payload, status

    def json(self):
        return self._payload


class FakeHttp:
    def __init__(self, payload):
        self._payload = payload
        self.calls = []

    def post(self, url, json=None):
        self.calls.append((url, json))
        return FakeResp(self._payload)


# Real GetJointState shape (trimmed to a few joints incl. arms).
JOINT_STATE_OK = {
    "header": {"code": "0", "msg": "called successfully."},
    "states": [
        {"name": "idx01_left_hip_roll", "position": -0.7, "velocity": 0.0, "effort": 0.0},
        {"name": "idx13_left_arm_joint1", "position": 0.11, "velocity": 0.0, "effort": 0.0},
        {"name": "idx20_right_arm_joint1", "position": -0.11, "velocity": 0.0, "effort": 0.0},
    ],
}


def test_get_joint_state_indexes_by_name():
    client = A2RpcClient(FakeHttp(JOINT_STATE_OK))
    states = client.get_joint_state()
    assert states["idx13_left_arm_joint1"]["position"] == 0.11
    assert set(states) == {"idx01_left_hip_roll", "idx13_left_arm_joint1", "idx20_right_arm_joint1"}


def test_call_hits_correct_rpc_url():
    http = FakeHttp(JOINT_STATE_OK)
    A2RpcClient(http, host="127.0.0.1", port=56322).get_joint_state()
    url, _ = http.calls[0]
    assert url == "http://127.0.0.1:56322/rpc/aimdk.protocol.McDataService/GetJointState"


def test_joint_positions_returns_vector_in_requested_order():
    client = A2RpcClient(FakeHttp(JOINT_STATE_OK))
    vec = client.joint_positions(["idx20_right_arm_joint1", "idx13_left_arm_joint1"])
    assert vec == [-0.11, 0.11]


def test_nonzero_header_code_raises():
    bad = {"header": {"code": "13", "msg": "rejected"}, "states": []}
    with pytest.raises(A2RpcError, match="rejected"):
        A2RpcClient(FakeHttp(bad)).get_joint_state()


def test_arm_joints_constant_is_14_dof_bimanual():
    assert len(ARM_JOINTS) == 14
    assert ARM_JOINTS[0] == "idx13_left_arm_joint1"
    assert ARM_JOINTS[-1] == "idx26_right_arm_joint7"


def test_set_action_uses_ext_cmd_envelope():
    http = FakeHttp({"header": {"code": "0", "msg": "ok"}})
    A2RpcClient(http).set_action("PASSIVE_UPPER_BODY_JOINT_SERVO")
    url, body = http.calls[0]
    assert url.endswith(".McActionService/SetAction")
    assert body["command"] == {
        "action": "McAction_USE_EXT_CMD",
        "ext_action": "PASSIVE_UPPER_BODY_JOINT_SERVO",
    }


class ScriptedHttp:
    """Returns scripted current_action values for GetAction; records call URLs."""

    def __init__(self, get_action_seq):
        self._seq = list(get_action_seq)
        self.calls = []

    def post(self, url, json=None):
        self.calls.append(url)
        if url.endswith("GetAction"):
            act = self._seq.pop(0) if len(self._seq) > 1 else self._seq[0]
            return FakeResp({"header": {"code": "0"}, "info": {"current_action": act}})
        return FakeResp({"header": {"code": "0", "msg": "ok"}})


def test_get_action_returns_current_action():
    http = ScriptedHttp(["McAction_RL_LOCOMOTION_DEFAULT"])
    assert A2RpcClient(http).get_action() == "McAction_RL_LOCOMOTION_DEFAULT"


def test_ensure_action_noops_when_already_in_mode():
    http = ScriptedHttp(["McAction_RL_LOCOMOTION_ARM_EXT_JOINT_SERVO"])
    ok = A2RpcClient(http).ensure_action("McAction_RL_LOCOMOTION_ARM_EXT_JOINT_SERVO",
                                         retry_interval=0)
    assert ok is True
    assert not any(u.endswith("SetAction") for u in http.calls)  # no switch needed


def test_ensure_action_sets_then_confirms():
    http = ScriptedHttp(["McAction_RL_LOCOMOTION_DEFAULT",
                         "McAction_RL_LOCOMOTION_ARM_EXT_JOINT_SERVO"])
    ok = A2RpcClient(http).ensure_action("McAction_RL_LOCOMOTION_ARM_EXT_JOINT_SERVO",
                                         retry_interval=0)
    assert ok is True
    assert any(u.endswith("SetAction") for u in http.calls)  # switched


def test_state_source_adapts_rpc_to_ros_transport_latest():
    src = A2RpcJointStateSource(A2RpcClient(FakeHttp(JOINT_STATE_OK)),
                                joint_order=["idx13_left_arm_joint1", "idx20_right_arm_joint1"])
    assert isinstance(src, RosTransport)
    state = src.latest("/motion/control/arm_joint_state")
    assert state == JointState(positions=[0.11, -0.11])
