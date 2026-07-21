import json
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]

def test_first_light_selftest_writes_valid_result(tmp_path):
    out = tmp_path / "res.json"
    proc = subprocess.run(
        [sys.executable, "scripts/b601_first_light.py", "--selftest", "--out", str(out)],
        capture_output=True, text=True, cwd=REPO)
    assert proc.returncode == 0, proc.stderr
    res = json.loads(out.read_text())
    assert res["score"] == 1.0                       # every scripted primitive reached
    funcs = [t["function"] for t in res["traces"]]
    assert "move_to_joints" in funcs and "set_gripper" in funcs
    assert all(t["status"] == "ok" for t in res["traces"])

def test_run_is_importable_and_deterministic():
    sys.path.insert(0, str(REPO / "scripts"))
    import b601_first_light as fl
    from robot_b601.clock import ManualClock
    from robot_b601.transport import FakeB601Transport
    res = fl.run(FakeB601Transport(gap_close=0.5), ManualClock())
    assert res.score == 1.0 and len(res.traces) >= 3
