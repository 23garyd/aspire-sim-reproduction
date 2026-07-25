from aspire.skill_library import Skill, SkillLibrary


def _add(lib, name, xy):
    lib.add(Skill(name=name, category="grasping", failure_signature="f",
                  when_to_apply="w", strategy="s", source_xy=xy))


def test_nearest_one_by_location(tmp_path):
    lib = SkillLibrary(tmp_path)
    _add(lib, "near", "0.10,0.00")
    _add(lib, "far", "0.90,0.90")
    got = lib.retrieve_by_location((0.12, 0.01), k=1, include_untagged=False)
    assert [s.name for s in got] == ["near"]


def test_untagged_appended_when_included(tmp_path):
    lib = SkillLibrary(tmp_path)
    _add(lib, "near", "0.10,0.00")
    lib.add(Skill(name="plumbing", category="engine-quirk-motion", failure_signature="f",
                  when_to_apply="w", strategy="s"))  # no source_xy
    got = lib.retrieve_by_location((0.0, 0.0), k=1, include_untagged=True)
    names = [s.name for s in got]
    assert names[0] == "near" and "plumbing" in names


def test_untagged_excluded_when_flag_false(tmp_path):
    lib = SkillLibrary(tmp_path)
    _add(lib, "near", "0.10,0.00")
    lib.add(Skill(name="plumbing", category="engine-quirk-motion", failure_signature="f",
                  when_to_apply="w", strategy="s"))
    got = lib.retrieve_by_location((0.0, 0.0), k=1, include_untagged=False)
    assert [s.name for s in got] == ["near"]
