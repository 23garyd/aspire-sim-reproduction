import json
import subprocess
import sys
from pathlib import Path

from aspire.schemas import ExecuteResult

SCRIPT = Path("scripts/capx_execute.py")


def test_capx_execute_selftest_mode_writes_contract_result(tmp_path):
    out = tmp_path / "o"
    proc = subprocess.run(
        [sys.executable, str(SCRIPT), "--program", str(SCRIPT), "--seeds", "0,1",
         "--out-dir", str(out), "--selftest"],
        capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr
    res = ExecuteResult.from_json((out / "result.json").read_text())
    assert res.score == 0.5                       # selftest: seed 0 passes, seed 1 fails
    assert res.traces[0].function == "selftest_primitive"


def test_cli_fake_dry_run(tmp_path):
    task = tmp_path / "robosuite" / "lift"
    task.mkdir(parents=True)
    (task / "code.py").write_text("pass")
    proc = subprocess.run(
        [sys.executable, "-m", "aspire.run", "--task-dir", str(task),
         "--engine", "fake", "--fake-scores", "1.0,0.9",
         "--library", str(tmp_path / "lib")],
        capture_output=True, text=True, cwd="/Users/Shared/github_aspire")
    assert proc.returncode == 0, proc.stderr
    summary = json.loads(proc.stdout.strip().splitlines()[-1])
    assert summary["val_score"] == 0.9 and summary["stage_reached"] == "validated"
    assert summary["tainted"] is False
    assert "config" in summary and summary["config"]["k"] == 3
