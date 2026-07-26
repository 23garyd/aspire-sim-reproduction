import subprocess
from pathlib import Path
REPO = Path(__file__).resolve().parents[2]


def test_runner_dry_lists_phases_and_pinned_params():
    proc = subprocess.run(["bash", "scripts/val_confirmatory_campaign.sh"],
                          capture_output=True, text=True, cwd=REPO,
                          env={"DRY": "1", "PATH": "/usr/bin:/bin", "HOME": "/tmp",
                               "ROOT": "/tmp/val_confirm_dry"})
    assert proc.returncode == 0, proc.stderr
    out = proc.stdout
    for tok in ("PHASE 0", "PHASE 1", "PHASE 2", "PHASE 3",
                ".venv-libero", "env -u ANTHROPIC_API_KEY", "--t 2", "--s-val 200-204",
                "warm_dumpall,cold", "--metric val", "--alpha 0.05",
                "PREREGISTRATION", "before any test run"):
        assert tok in out, f"missing {tok}"
