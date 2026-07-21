import json
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]

CORRECT = (
    "p = get_cube_pose()\n"
    "move_to_pose(p.x, p.y, p.z + 0.10)\n"
    "open_gripper()\n"
    "move_to_pose(p.x, p.y, p.z)\n"
    "close_gripper()\n"
    "move_to_pose(p.x, p.y, p.z + 0.20)\n"
)

def _run(program_src, seeds, tmp_path):
    prog = tmp_path / "code.py"; prog.write_text(program_src)
    out = tmp_path / "o"
    proc = subprocess.run(
        [sys.executable, "scripts/b601_execute.py", "--selftest",
         "--program", str(prog), "--seeds", seeds, "--out-dir", str(out)],
        capture_output=True, text=True, cwd=REPO)
    assert proc.returncode == 0, proc.stderr
    return json.loads((out / "result.json").read_text())

def test_correct_program_scores_one(tmp_path):
    res = _run(CORRECT, "0,1,2", tmp_path)
    assert res["score"] == 1.0
    assert any(t["function"] == "get_cube_pose" for t in res["traces"])
    assert all(t["status"] == "ok" for t in res["traces"])

def test_noop_program_scores_zero(tmp_path):
    res = _run("pass\n", "0,1,2", tmp_path)
    assert res["score"] == 0.0

def test_audit_rejects_forbidden_program(tmp_path):
    res = _run("q = env.handle.env.sim.data.qpos\n", "0", tmp_path)
    assert res["score"] == 0.0
    assert any(t["function"] == "audit" and t["status"] == "error" for t in res["traces"])
