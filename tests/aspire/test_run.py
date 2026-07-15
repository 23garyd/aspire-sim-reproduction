import json
import subprocess
import sys
from pathlib import Path

from aspire.schemas import ExecuteResult

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "scripts" / "capx_execute.py"


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


def test_capx_execute_non_selftest_fails_without_result(tmp_path):
    out = tmp_path / "o"
    proc = subprocess.run(
        [sys.executable, str(SCRIPT), "--program", str(SCRIPT), "--seeds", "0",
         "--out-dir", str(out)],                  # no --selftest: run_episode is M0 stub
        capture_output=True, text=True)
    assert proc.returncode != 0
    assert not (out / "result.json").exists()


def test_cli_fake_dry_run(tmp_path):
    task = tmp_path / "robosuite" / "lift"
    task.mkdir(parents=True)
    (task / "code.py").write_text("pass")
    proc = subprocess.run(
        [sys.executable, "-m", "aspire.run", "--task-dir", str(task),
         "--engine", "fake", "--fake-scores", "1.0,0.9",
         "--library", str(tmp_path / "lib")],
        capture_output=True, text=True, cwd=REPO_ROOT)
    assert proc.returncode == 0, proc.stderr
    summary = json.loads(proc.stdout.strip().splitlines()[-1])
    assert summary["val_score"] == 0.9 and summary["stage_reached"] == "validated"
    assert summary["tainted"] is False
    assert "config" in summary and summary["config"]["k"] == 3


def test_cli_domain_error_exits_2_without_traceback(tmp_path):
    task = tmp_path / "robosuite" / "lift"
    task.mkdir(parents=True)
    (task / "code.py").write_text("pass")
    (task / "VALIDATION_STARTED").touch()         # crash artifact -> ValidationReuseError
    proc = subprocess.run(
        [sys.executable, "-m", "aspire.run", "--task-dir", str(task),
         "--engine", "fake", "--fake-scores", "1.0,0.9",
         "--library", str(tmp_path / "lib")],
        capture_output=True, text=True, cwd=REPO_ROOT)
    assert proc.returncode == 2
    assert "interrupted" in proc.stderr
    assert "Traceback" not in proc.stdout
    assert "Traceback" not in proc.stderr


def test_capx_actor_wired_with_evosearch_propose_prompt(tmp_path):
    from aspire.run import _build_capx_actors
    actor, judge = _build_capx_actors("prompts", tmp_path)
    assert actor._prompt_file.endswith("actor_debug.md")
    assert actor._propose_prompt_file.endswith("actor_evosearch.md")


def test_cli_capx_requires_cmd_and_out_root(tmp_path):
    task = tmp_path / "robosuite" / "lift"
    task.mkdir(parents=True)
    (task / "code.py").write_text("pass")
    proc = subprocess.run(
        [sys.executable, "-m", "aspire.run", "--task-dir", str(task),
         "--engine", "capx", "--library", str(tmp_path / "lib")],
        capture_output=True, text=True, cwd=REPO_ROOT)
    assert proc.returncode == 2
    assert "required for --engine capx" in proc.stderr
