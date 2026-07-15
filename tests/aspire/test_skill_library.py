from aspire.schemas import ProposedSkill
from aspire.skill_library import Skill, SkillLibrary, parse_skill, render_skill


def make_skill(**kw):
    d = dict(name="multi-angle-approach", category="navigation",
             failure_signature="repeated PLANNING_ERROR near obstacle boundary",
             when_to_apply="nav goals fall inside the collision-avoidance buffer",
             strategy="rotate the approach vector by 45/90/180 degrees",
             code_sketch="for a in [180, -90, 90]: ...",
             provenance="robosuite/handover seeds 0-2 + val 100-104")
    d.update(kw)
    return Skill(**d)


def test_render_parse_round_trip():
    s = make_skill()
    assert parse_skill(render_skill(s)) == s


def test_add_writes_file_and_index(tmp_path):
    lib = SkillLibrary(tmp_path)
    path = lib.add(make_skill())
    assert path.exists() and path.suffix == ".md"
    assert "multi-angle-approach" in (tmp_path / "index.md").read_text()


def test_retrieve_by_category_and_keyword(tmp_path):
    lib = SkillLibrary(tmp_path)
    lib.add(make_skill())
    lib.add(make_skill(name="obb-axis-grasp", category="grasping",
                       failure_signature="grasp slips on box lid",
                       when_to_apply="thin box-like objects",
                       strategy="align gripper with shortest OBB axis"))
    nav = lib.retrieve(categories=["navigation"])
    assert [s.name for s in nav] == ["multi-angle-approach"]
    hits = lib.retrieve(keywords=["PLANNING_ERROR"])
    assert [s.name for s in hits] == ["multi-angle-approach"]
    assert len(lib.retrieve()) == 2


def test_from_proposed_adds_provenance():
    p = ProposedSkill(name="n", category="c", failure_signature="f",
                      when_to_apply="w", strategy="s")
    s = Skill.from_proposed(p, provenance="task X")
    assert s.provenance == "task X" and s.name == "n"
