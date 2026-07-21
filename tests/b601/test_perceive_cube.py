import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]


def test_dry_run_exits_zero_and_reports_extrinsic():
    proc = subprocess.run(
        [sys.executable, "scripts/b601_perceive_cube.py", "--dry-run"],
        capture_output=True, text=True, cwd=REPO)
    assert proc.returncode == 0, proc.stderr
    out = proc.stdout.lower()
    assert "extrinsic" in out and "dry-run" in out


def test_format_pose_is_readable():
    sys.path.insert(0, str(REPO / "scripts"))
    import b601_perceive_cube as pc
    from robot_b601.task import CubePose
    s = pc.format_pose(CubePose(0.4, 0.0, 0.1))
    assert "0.4" in s and "0.1" in s
