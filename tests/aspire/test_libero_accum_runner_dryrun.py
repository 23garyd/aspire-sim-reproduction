import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]


def test_runner_dry_run_lists_phases_and_tasks():
    proc = subprocess.run(["bash", "scripts/libero_accumulation.sh"],
                          capture_output=True, text=True, cwd=REPO,
                          env={"DRY": "1", "PATH": "/usr/bin:/bin", "HOME": "/tmp",
                               "ROOT": "/tmp/libero_accum_dryrun"})
    assert proc.returncode == 0, proc.stderr
    out = proc.stdout
    assert "PHASE 1" in out and "PHASE 2" in out
    # accumulate task_ids 2,1,0 and the held-out calibration shortlist 8,6,5,3 appear
    for tid in ("task_id: 2", "task_id: 1", "task_id: 0", "task_id: 8", "task_id: 6"):
        assert tid in out, f"missing {tid}"
    assert ".venv-libero" in out and "--t 5" in out and "--t 3" in out
