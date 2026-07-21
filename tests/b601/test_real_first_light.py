import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]

def test_dry_run_prints_waypoints_and_exits_zero():
    proc = subprocess.run(
        [sys.executable, "scripts/b601_real_first_light.py", "--dry-run"],
        capture_output=True, text=True, cwd=REPO)
    assert proc.returncode == 0, proc.stderr      # runs in CI with NO ROS 2 -> proves rclpy not imported on this path
    assert "waypoint" in proc.stdout.lower()

def test_plan_waypoints_are_bounded():
    sys.path.insert(0, str(REPO / "scripts"))
    import b601_real_first_light as fl
    home = [0.1, -0.2, 0.0, 0.3, -0.1, 0.2]
    wps = fl.plan_waypoints(home, delta_max=0.15)
    assert wps[0] == home and wps[-1] == home     # starts and ends at home
    for wp in wps:
        for h, j in zip(home, wp):
            assert abs(j - h) <= 0.15 + 1e-9       # every waypoint within delta_max of home
