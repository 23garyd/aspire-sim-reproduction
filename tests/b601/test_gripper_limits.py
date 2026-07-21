import pytest
from robot_b601.limits import (GripperLimits, DEFAULT_GRIPPER_LIMITS,
                               clamp_gripper, load_gripper_limits)


def test_clamp_gripper_in_range_unchanged():
    lim = GripperLimits(lo=0.0, hi=0.08)
    c, was = clamp_gripper(0.03, lim)
    assert c == 0.03 and was is False


def test_clamp_gripper_over_and_under():
    lim = GripperLimits(lo=0.0, hi=0.08)
    assert clamp_gripper(0.5, lim) == (0.08, True)
    assert clamp_gripper(-0.2, lim) == (0.0, True)


def test_default_gripper_limits_shape():
    assert DEFAULT_GRIPPER_LIMITS.lo == 0.0 and DEFAULT_GRIPPER_LIMITS.hi == 0.08


def test_load_gripper_limits_default_when_missing(tmp_path):
    assert load_gripper_limits(None) == DEFAULT_GRIPPER_LIMITS
    assert load_gripper_limits("/no/such.json") == DEFAULT_GRIPPER_LIMITS
    p = tmp_path / "nogrip.json"
    p.write_text('{"lo": [0], "hi": [1]}')            # no grip_lo/grip_hi keys
    assert load_gripper_limits(p) == DEFAULT_GRIPPER_LIMITS


def test_load_gripper_limits_from_json(tmp_path):
    p = tmp_path / "g.json"
    p.write_text('{"grip_lo": 0.0, "grip_hi": 0.05}')
    assert load_gripper_limits(p) == GripperLimits(lo=0.0, hi=0.05)


def test_load_gripper_limits_inverted_raises(tmp_path):
    p = tmp_path / "bad.json"
    p.write_text('{"grip_lo": 0.05, "grip_hi": 0.0}')
    with pytest.raises(ValueError):
        load_gripper_limits(p)
