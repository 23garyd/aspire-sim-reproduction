import subprocess
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]


def test_runner_dry_run_lists_phases_and_tasks():
    proc = subprocess.run(
        ["bash", "scripts/libero_accumulation_v2.sh"],
        capture_output=True, text=True, cwd=REPO,
        env={"DRY": "1", "PATH": "/usr/bin:/bin", "HOME": "/tmp",
             "ROOT": "/tmp/libero_accum_v2_dryrun"})
    assert proc.returncode == 0, proc.stderr
    out = proc.stdout
    # All five phases present.
    for phase in ("PHASE 0", "PHASE 1", "PHASE 2A", "PHASE 2B", "PHASE 3"):
        assert phase in out, f"missing {phase}"
    # venv + both budgets.
    assert ".venv-libero" in out
    assert "--t 5" in out   # accumulate + test budget
    assert "--t 3" in out   # frontier probe budget
    # accumulate ids {0,1,2}.
    for tid in ("task_id: 0", "task_id: 1", "task_id: 2"):
        assert tid in out, f"missing {tid}"
