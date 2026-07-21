import json
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
BASE = REPO / "runs" / "2026-07-21-b601-real-cube-lift"
CORRECT = (BASE / "baseline_lift.py").read_text()


def test_real_cube_lift_drives_aspire_pipeline_no_llm(tmp_path):
    task = tmp_path / "robosuite" / "cube_lift"
    task.mkdir(parents=True)
    (task / "code.py").write_text(CORRECT)          # a passing baseline -> no actor called
    capx_cmd = (f"{sys.executable} {REPO}/scripts/b601_execute.py "
                f"--config-path {BASE / 'cube_lift_fake.json'}")
    proc = subprocess.run(
        [sys.executable, "-m", "aspire.run", "--task-dir", str(task),
         "--engine", "capx", "--capx-cmd", capx_cmd,
         "--out-root", str(tmp_path / "exec"), "--library", str(tmp_path / "lib"),
         "--s-dbg", "0,1,2", "--s-val", "100-104"],
        capture_output=True, text=True, cwd=REPO)
    assert proc.returncode == 0, proc.stderr
    summary = json.loads(proc.stdout.strip().splitlines()[-1])
    assert summary["stage_reached"] == "validated"
    assert summary["val_score"] == 1.0            # correct baseline lifts on all held-out seeds
    assert "claude" not in proc.stderr.lower()    # no LLM: a passing baseline never calls the actor
