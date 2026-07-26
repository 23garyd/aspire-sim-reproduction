import subprocess
from pathlib import Path
REPO = Path(__file__).resolve().parents[2]


def test_sval_passthrough_shows_in_dry_summary():
    proc = subprocess.run(
        ["python3", "scripts/libero_tiling_parallel.py", "--dry",
         "--root", "/tmp/vc_svaltest", "--suite", "libero_10", "--tasks", "6",
         "--arms", "warm_dumpall,cold", "--reps", "1", "--t", "2",
         "--s-val", "200-204", "--library", "/tmp/nolib"],
        capture_output=True, text=True, cwd=REPO)
    assert proc.returncode == 0, proc.stderr
    assert "s_val=200-204" in proc.stdout
