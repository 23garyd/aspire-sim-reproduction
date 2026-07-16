"""Regression test pinning a real CaP-X golden episode captured on the GPU box
(franka_robosuite_cube_stack_privileged_oracle, oracle program, seed=1).
Guards against ExecuteResult-shape regressions in scripts/capx_execute.py's
real (non-selftest) run_episode path, independent of GPU/CaP-X availability."""
import json
from pathlib import Path

from aspire.schemas import ExecuteResult

GOLDEN = Path(__file__).parent / "golden" / "stack_seed1_result.json"


def test_golden_capx_episode_parses_and_is_wellformed():
    res = ExecuteResult.from_json(GOLDEN.read_text())
    assert res.score in (0.0, 1.0)
    assert len(res.traces) >= 3, "oracle program must produce multiple primitive calls"
    assert all(t.status in ("ok", "error") for t in res.traces)
    fns = {t.function for t in res.traces}
    assert any("gripper" in f or "pose" in f for f in fns), fns
    assert all(t.duration_ms >= 0 for t in res.traces)
