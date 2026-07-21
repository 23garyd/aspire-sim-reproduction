import json
import socket
from robot_b601.transport import JointCommand, JointState, B601IsaacUdpTransport

def test_publish_sends_wire_schema():
    # bind a receiver on an ephemeral cmd port, point the transport at it
    rx = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    rx.bind(("127.0.0.1", 0))
    cmd_port = rx.getsockname()[1]
    t = B601IsaacUdpTransport(host="127.0.0.1", cmd_port=cmd_port, state_port=0)
    t.publish(JointCommand([0.1, 0.2, 0.3, 0.4, 0.5, 0.6], 0.04))
    rx.settimeout(1.0)
    data, _ = rx.recvfrom(4096)
    msg = json.loads(data)
    assert msg["joint_positions"] == [0.1, 0.2, 0.3, 0.4, 0.5, 0.6]
    assert msg["gripper_position"] == 0.04
    assert "sequence" in msg and "timestamp" in msg
    rx.close(); t.close()

def test_latest_reads_newest_state_or_none():
    t = B601IsaacUdpTransport(host="127.0.0.1", cmd_port=0, state_port=0)
    assert t.latest() is None                       # nothing sent yet
    tx = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    for jp in ([0.0]*6, [0.9]*6):                   # newest wins
        tx.sendto(json.dumps({"sequence": 1, "timestamp": 0.0,
                              "joint_positions": jp, "gripper_position": 0.02}).encode(),
                 ("127.0.0.1", t.state_port))
    import time; time.sleep(0.05)
    st = t.latest()
    assert isinstance(st, JointState) and st.joint_positions == [0.9]*6
    tx.close(); t.close()
