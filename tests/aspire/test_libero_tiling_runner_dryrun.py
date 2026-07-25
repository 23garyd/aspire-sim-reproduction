import subprocess
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]


def test_runner_dry_run_lists_phases_arms_and_budgets():
    proc = subprocess.run(["bash", "scripts/libero_tiling.sh"],
                          capture_output=True, text=True, cwd=REPO,
                          env={"DRY": "1", "PATH": "/usr/bin:/bin", "HOME": "/tmp",
                               "ROOT": "/tmp/libero_tiling_dry"})
    assert proc.returncode == 0, proc.stderr
    out = proc.stdout
    for token in ("PHASE 0", "PHASE 1", "PHASE 2", "PHASE 3", "PHASE 4",
                  ".venv-libero", "--t 5", "--t 2",
                  "warm_geo", "warm_dumpall", "cold",
                  "ASPIRE_RETRIEVAL=geometry"):
        assert token in out, f"missing {token}"
    # accumulate ids and held-out ids both appear
    assert "task_id: 0" in out and "task_id: 3" in out
