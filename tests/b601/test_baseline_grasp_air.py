import json
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
BASE = REPO / "runs" / "2026-07-21-b601-real-cube-lift"
CFG = BASE / "cube_lift_fake.json"
FAILING = BASE / "baseline_grasp_air.py"


def test_grasp_air_baseline_scores_zero(tmp_path):
    out = tmp_path / "out"
    proc = subprocess.run(
        [sys.executable, "scripts/b601_execute.py", "--program", str(FAILING),
         "--seeds", "0,1,2", "--out-dir", str(out), "--config-path", str(CFG)],
        capture_output=True, text=True, cwd=REPO)
    assert proc.returncode == 0, proc.stderr
    result = json.loads((out / "result.json").read_text())
    assert result["score"] == 0.0                    # closes above the cube -> never lifts


def test_grasp_air_failure_is_trace_diagnosable(tmp_path):
    out = tmp_path / "out2"
    subprocess.run(
        [sys.executable, "scripts/b601_execute.py", "--program", str(FAILING),
         "--seeds", "0", "--out-dir", str(out), "--config-path", str(CFG)],
        capture_output=True, text=True, cwd=REPO, check=True)
    traces = json.loads((out / "result.json").read_text())["traces"]
    # the failure cause is legible in the trace text (what a real LLM would read):
    # the gripper closed but grasped nothing.
    assert any(t["function"] == "set_gripper" and "grasped=False" in t["result_summary"]
               for t in traces)
    # and the arm did perceive the cube first (so the bug is 'wrong height', not 'no perception')
    assert any(t["function"] == "get_cube_pose" for t in traces)
