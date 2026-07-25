from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
from tag_skill_xy import tag_untagged
from aspire.skill_library import Skill, SkillLibrary, parse_skill


def test_stamps_only_untagged(tmp_path):
    lib = SkillLibrary(tmp_path)
    lib.add(Skill(name="fresh", category="grasping", failure_signature="f",
                  when_to_apply="w", strategy="s"))                       # untagged
    lib.add(Skill(name="already", category="grasping", failure_signature="f",
                  when_to_apply="w", strategy="s", source_xy="0.5,0.5"))  # tagged
    n = tag_untagged(tmp_path, "0.1,0.2")
    assert n == 1
    by_name = {s.name: s for s in lib.load_all()}
    assert by_name["fresh"].source_xy == "0.1,0.2"
    assert by_name["already"].source_xy == "0.5,0.5"   # untouched
