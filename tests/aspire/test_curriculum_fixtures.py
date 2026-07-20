from pathlib import Path

BASE = Path("runs/2026-07-20-curriculum/tasks/robosuite")
TASKS = ["cube_lifting", "cube_stack", "nut_assembly", "two_arm_handover"]

def test_four_nonlift_baselines_present_and_nonempty():
    for t in TASKS:
        p = BASE / t / "code.py"
        assert p.exists(), f"missing {p}"
        assert p.stat().st_size > 50, f"suspiciously small {p}"

def test_lift_is_excluded_from_accumulation_set():
    # no self-leakage: the measured task must NOT be in the accumulation set
    assert not (BASE / "two_arm_lift").exists()
