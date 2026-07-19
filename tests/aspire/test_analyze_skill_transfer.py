import json

def _done(dirpath, score):
    dirpath.mkdir(parents=True)
    (dirpath / "VALIDATION_DONE").write_text(
        json.dumps({"program": "x", "score": score, "dbg_score": 1.0}))

def test_reads_S_and_E_arms_and_returns_zero(tmp_path):
    for arm, scores in [("S", [0.9, 0.9, 1.0]), ("E", [0.1, 0.2, 0.3])]:
        for i, s in enumerate(scores, 1):
            _done(tmp_path / arm / f"rep_{i}" / "robosuite" / "two_arm_lift", s)
    from scripts.analyze_skill_transfer import main
    assert main([str(tmp_path)]) == 0

def test_missing_arm_returns_one(tmp_path):
    _done(tmp_path / "S" / "rep_1" / "robosuite" / "two_arm_lift", 0.9)
    from scripts.analyze_skill_transfer import main
    assert main([str(tmp_path)]) == 1        # E arm empty -> non-zero
