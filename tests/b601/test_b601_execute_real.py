import json
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
CFG = REPO / "runs" / "2026-07-21-b601-real-cube-lift" / "cube_lift_fake.json"
BASELINE = REPO / "runs" / "2026-07-21-b601-real-cube-lift" / "baseline_lift.py"


def test_real_env_fake_backend_scores_one(tmp_path):
    out = tmp_path / "out"
    proc = subprocess.run(
        [sys.executable, "scripts/b601_execute.py", "--program", str(BASELINE),
         "--seeds", "0,1,2", "--out-dir", str(out), "--config-path", str(CFG)],
        capture_output=True, text=True, cwd=REPO)
    assert proc.returncode == 0, proc.stderr
    result = json.loads((out / "result.json").read_text())
    assert result["score"] == 1.0                 # correct baseline lifts on every seed
    assert len(result["traces"]) > 0


def test_selftest_still_uses_fake_cube_lift_env(tmp_path):
    out = tmp_path / "out2"
    proc = subprocess.run(
        [sys.executable, "scripts/b601_execute.py", "--program", str(BASELINE),
         "--seeds", "0,1", "--out-dir", str(out), "--selftest"],
        capture_output=True, text=True, cwd=REPO)
    assert proc.returncode == 0, proc.stderr      # --selftest path unchanged, still runs
    result = json.loads((out / "result.json").read_text())
    assert result["score"] == 1.0                 # baseline lifts on the M2 FakeCubeLiftEnv too
