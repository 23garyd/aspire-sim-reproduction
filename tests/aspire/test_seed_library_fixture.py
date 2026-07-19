from aspire.skill_library import SkillLibrary

FIXTURE = "runs/2026-07-19-skill-transfer/seed_library"

def test_seed_library_is_exactly_the_two_handover_skills():
    skills = SkillLibrary(FIXTURE).load_all()
    assert len(skills) == 2
    assert sorted(s.name for s in skills) == [
        "allocate-shared-object-span-between-two-effectors",
        "keyframe-geometry-from-trace-images",
    ]
    for s in skills:
        assert "two_arm_handover" in s.provenance      # genuine cross-task seed
        assert "two_arm_lift" not in s.provenance       # lift-provenance excluded
