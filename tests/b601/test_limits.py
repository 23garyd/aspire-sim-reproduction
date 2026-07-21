from robot_b601.limits import JointLimits, DEFAULT_LIMITS, clamp_to_limits, load_limits

def test_in_range_unchanged():
    lim = JointLimits(lo=[-1.0]*6, hi=[1.0]*6)
    c, was = clamp_to_limits([0.5, -0.5, 0.0, 0.9, -0.9, 0.1], lim)
    assert c == [0.5, -0.5, 0.0, 0.9, -0.9, 0.1]
    assert was is False

def test_out_of_range_clamps_per_joint():
    lim = JointLimits(lo=[-1.0]*6, hi=[1.0]*6)
    c, was = clamp_to_limits([2.0, -2.0, 0.0, 5.0, -5.0, 0.5], lim)
    assert c == [1.0, -1.0, 0.0, 1.0, -1.0, 0.5]
    assert was is True

def test_default_limits_shape():
    assert len(DEFAULT_LIMITS.lo) == 6 and len(DEFAULT_LIMITS.hi) == 6
    assert all(lo < hi for lo, hi in zip(DEFAULT_LIMITS.lo, DEFAULT_LIMITS.hi))

def test_load_default_when_missing():
    assert load_limits("/no/such/file.json") is DEFAULT_LIMITS
    assert load_limits(None) is DEFAULT_LIMITS

def test_load_from_json(tmp_path):
    p = tmp_path / "l.json"
    p.write_text('{"lo": [-1,-1,-1,-1,-1,-1], "hi": [1,1,1,1,1,1]}')
    lim = load_limits(str(p))
    assert lim.lo == [-1.0]*6 and lim.hi == [1.0]*6
