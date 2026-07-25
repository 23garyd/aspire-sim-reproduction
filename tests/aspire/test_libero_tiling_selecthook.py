from aspire.skill_library import Skill, SkillLibrary
from aspire.task_context import select_skills


def _lib(tmp_path):
    lib = SkillLibrary(tmp_path)
    lib.add(Skill(name="near", category="grasping", failure_signature="f",
                  when_to_apply="w", strategy="s", source_xy="0.10,0.00"))
    lib.add(Skill(name="far", category="grasping", failure_signature="f",
                  when_to_apply="w", strategy="s", source_xy="0.90,0.90"))
    return lib


def test_geometry_mode_uses_location(tmp_path, monkeypatch):
    lib = _lib(tmp_path)
    monkeypatch.setenv("ASPIRE_RETRIEVAL", "geometry")
    monkeypatch.setenv("ASPIRE_TARGET_XY", "0.12,0.01")
    got = select_skills(lib, traces=[])   # traces ignored in geometry mode
    assert got[0].name == "near"


def test_default_mode_falls_back_to_relevant(tmp_path, monkeypatch):
    lib = _lib(tmp_path)
    monkeypatch.delenv("ASPIRE_RETRIEVAL", raising=False)
    # no error traces -> relevant_skills falls back to load_all (both skills)
    got = select_skills(lib, traces=[])
    assert {s.name for s in got} == {"near", "far"}


def test_geometry_mode_bad_xy_falls_back(tmp_path, monkeypatch):
    lib = _lib(tmp_path)
    monkeypatch.setenv("ASPIRE_RETRIEVAL", "geometry")
    monkeypatch.setenv("ASPIRE_TARGET_XY", "not-a-coord")
    got = select_skills(lib, traces=[])   # malformed -> stock path
    assert {s.name for s in got} == {"near", "far"}
