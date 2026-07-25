from aspire.skill_library import Skill, render_skill, parse_skill


def _skill(**kw):
    base = dict(name="rim grasp", category="grasping", failure_signature="fs",
                when_to_apply="wa", strategy="st", code_sketch="cs", provenance="spatial_2")
    base.update(kw)
    return Skill(**base)


def test_sourcexy_roundtrips_when_set():
    s = _skill(source_xy="0.123,-0.045")
    back = parse_skill(render_skill(s))
    assert back.source_xy == "0.123,-0.045"
    # all other fields survive unchanged
    assert back.name == "rim grasp" and back.category == "grasping" and back.strategy == "st"


def test_sourcexy_absent_defaults_empty():
    s = _skill()  # no source_xy
    text = render_skill(s)
    assert "source_xy:" not in text          # not emitted when empty
    assert parse_skill(text).source_xy == ""


def test_sourcexy_line_does_not_break_section_parse():
    s = _skill(source_xy="1.0,2.0", strategy="line1\nline2")
    back = parse_skill(render_skill(s))
    assert back.strategy == "line1\nline2" and back.source_xy == "1.0,2.0"
