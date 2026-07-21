import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]


def test_dry_run_exits_zero_and_lists_poses():
    proc = subprocess.run(
        [sys.executable, "scripts/b601_hand_eye_calibrate.py", "--dry-run"],
        capture_output=True, text=True, cwd=REPO)
    assert proc.returncode == 0, proc.stderr
    out = proc.stdout.lower()
    assert "pose" in out and "board" in out


def test_calibration_look_poses_are_bounded_and_multiple():
    sys.path.insert(0, str(REPO / "scripts"))
    import b601_hand_eye_calibrate as cal
    home = [0.0, -0.3, 0.6, 0.0, 0.9, 0.0]
    poses = cal.calibration_look_poses(home)
    assert len(poses) >= 8                      # enough varied views for a stable solve
    for p in poses:
        for h, j in zip(home, p):
            assert abs(j - h) <= cal.MAX_CALIB_DELTA + 1e-9
