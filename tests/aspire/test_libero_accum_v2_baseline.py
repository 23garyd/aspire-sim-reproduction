import ast
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
BASELINE = REPO / "runs" / "2026-07-22-libero-accum-frontier" / "baseline_grasp_lift.py"


def _src():
    return BASELINE.read_text()


def test_baseline_parses_as_python():
    ast.parse(_src())  # raises SyntaxError if invalid


def test_baseline_has_positive_z_approach_ladder():
    src = _src()
    # A positive standoff ladder (descent), never z_approach=0.0.
    assert "z_approach=0.10" in src
    assert "z_approach=0.03" in src
    assert "z_approach=0.008" in src
    assert "z_approach=0.0)" not in src and "z_approach=0.0," not in src


def test_baseline_float_casts_quaternion():
    assert ".astype(float)" in _src()


def test_baseline_has_no_open_gripper_after_close_gripper():
    # Guards the "manipulation gap preserved" premise: grasp-and-lift only, no place
    # (a place would re-open the gripper to release). Assert on source order.
    src = _src()
    assert "close_gripper()" in src, "baseline must close the gripper (grasp)"
    close_idx = src.index("close_gripper()")
    after = src[close_idx:]
    assert "open_gripper" not in after, "no open_gripper after close_gripper (no release/place)"


def test_baseline_has_no_place_or_transport_to_plate():
    src = _src().lower()
    # No transport-to-plate step in the executable program. (Comments may mention the
    # word 'plate' descriptively, so check for a plate grasp-pose / goto being sampled.)
    assert "sample_grasp_pose(\"plate\")" not in _src()
    assert "sample_grasp_pose('plate')" not in _src()
