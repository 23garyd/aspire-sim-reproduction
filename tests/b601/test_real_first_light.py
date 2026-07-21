import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "scripts"))


def test_dry_run_prints_waypoints_and_exits_zero():
    proc = subprocess.run(
        [sys.executable, "scripts/b601_real_first_light.py", "--dry-run"],
        capture_output=True, text=True, cwd=REPO)
    assert proc.returncode == 0, proc.stderr      # runs in CI with NO ROS 2 -> proves rclpy not imported on this path
    assert "waypoint" in proc.stdout.lower()

def test_plan_waypoints_are_bounded():
    import b601_real_first_light as fl
    home = [0.1, -0.2, 0.0, 0.3, -0.1, 0.2]
    wps = fl.plan_waypoints(home, delta_max=0.15)
    assert wps[0] == home and wps[-1] == home     # starts and ends at home
    for wp in wps:
        for h, j in zip(home, wp):
            assert abs(j - h) <= 0.15 + 1e-9       # every waypoint within delta_max of home


class _ConnectableFakeTransport:
    """FakeB601Transport (M1) has no connect() -- it's only ever used directly by
    B601Node/B601Engine in the M1 tests. b601_real_first_light.run() calls
    transport.connect() first (mirroring the live B601RosTransport), so wrap the
    fake with a no-op connect() rather than modifying robot_b601/transport.py."""

    def __init__(self, start):
        from robot_b601.transport import FakeB601Transport
        self._inner = FakeB601Transport(start=start)

    def connect(self):
        pass

    def publish(self, cmd):
        return self._inner.publish(cmd)

    def latest(self):
        return self._inner.latest()


class _NeverReportsTransport:
    """Simulates a real transport whose /joint_states topic hasn't published yet:
    connect() succeeds but latest() never returns a state. Used to prove run() fails
    loud instead of silently falling back to a hardcoded zero home."""

    def __init__(self):
        self.publish_calls = 0

    def connect(self):
        pass

    def publish(self, cmd):
        self.publish_calls += 1

    def latest(self):
        return None


def test_run_uses_real_current_pose_as_home_not_zero():
    import b601_real_first_light as fl
    from robot_b601.clock import ManualClock

    home_pose = [0.4, -0.3, 0.2, 0.1, -0.2, 0.05]
    transport = _ConnectableFakeTransport(start=home_pose)
    res = fl.run(transport, ManualClock(), delta_max=0.15)

    assert res.score == 1.0
    assert len(res.traces) == 3                          # home -> bumped -> home
    # the first commanded waypoint must be the REAL current pose, not [0.0] * 6
    assert res.traces[0].args["joints"] == home_pose
    assert res.traces[0].args["joints"] != [0.0] * 6
    assert res.traces[-1].args["joints"] == home_pose
    assert all(t.status == "ok" for t in res.traces)

def test_run_raises_if_no_joint_state_arrives_within_timeout():
    import b601_real_first_light as fl
    from robot_b601.clock import ManualClock

    transport = _NeverReportsTransport()
    clock = ManualClock()
    with pytest.raises(RuntimeError):
        fl.run(transport, clock, delta_max=0.15, state_timeout=0.05)
    assert transport.publish_calls == 0    # no move was ever commanded to the real arm
