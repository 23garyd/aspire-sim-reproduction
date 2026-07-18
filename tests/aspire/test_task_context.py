import json
from pathlib import Path

from aspire.schemas import ExecuteResult, TraceRecord
from aspire.skill_library import Skill, SkillLibrary
from aspire.task_context import (relevant_skills, summarize_traces,
                                 write_execution_context, write_skills_context,
                                 write_task_metadata)


def _tr(**kw):
    d = dict(step=1, function="grasp_object", args={}, status="ok",
             result_summary="in_hand=True", duration_ms=10.0, media=[])
    d.update(kw)
    return TraceRecord(**d)


def test_summarize_traces_lists_steps_and_counts_failures():
    s = summarize_traces([_tr(), _tr(step=2, function="navigate_to_pose",
                                     status="error", result_summary="PLANNING_ERROR")])
    assert "step 1: grasp_object [ok] in_hand=True" in s
    assert "step 2: navigate_to_pose [error] PLANNING_ERROR" in s
    assert s.strip().endswith("FAILURES: 1")


def test_write_execution_context_materializes_traces_and_media(tmp_path):
    task = tmp_path / "suite" / "task"; task.mkdir(parents=True)
    raw = tmp_path / "raw"; raw.mkdir()
    (raw / "kf_001.png").write_bytes(b"png")
    res = ExecuteResult(score=0.5, raw_dir=str(raw),
                        traces=[_tr(media=["kf_001.png", "missing.png"])])
    write_execution_context(task, res)
    loaded = json.loads((task / "traces" / "trace.json").read_text())
    assert loaded[0]["function"] == "grasp_object"
    assert "FAILURES: 0" in (task / "traces" / "summary.txt").read_text()
    assert (task / "traces" / "media" / "kf_001.png").read_bytes() == b"png"
    assert not (task / "traces" / "media" / "missing.png").exists()


def test_write_execution_context_overwrites_previous(tmp_path):
    task = tmp_path / "s" / "t"; task.mkdir(parents=True)
    write_execution_context(task, ExecuteResult(score=0.0, traces=[_tr()]))
    write_execution_context(task, ExecuteResult(score=1.0, traces=[
        _tr(step=9, function="fresh_call")]))
    text = (task / "traces" / "trace.json").read_text()
    assert "fresh_call" in text and "grasp_object" not in text


def test_write_task_metadata(tmp_path):
    task = tmp_path / "robosuite" / "handover"; task.mkdir(parents=True)
    write_task_metadata(task, task_language="hand the pot to the other arm")
    md = (task / "task.md").read_text()
    assert "# Task: robosuite/handover" in md
    assert "hand the pot to the other arm" in md
    write_task_metadata(task)   # no language
    assert "not yet captured" in (task / "task.md").read_text()


def test_relevant_skills_keys_on_failure_tokens(tmp_path):
    lib = SkillLibrary(tmp_path / "lib")
    lib.add(Skill(name="multi-angle-approach", category="navigation",
                  failure_signature="repeated PLANNING_ERROR near obstacle",
                  when_to_apply="w", strategy="s"))
    lib.add(Skill(name="obb-grasp", category="grasping",
                  failure_signature="grasp slips", when_to_apply="w", strategy="s"))
    traces = [_tr(status="error", function="navigate_to_pose",
                  result_summary="PLANNING_ERROR near table")]
    hits = relevant_skills(lib, traces)
    assert [s.name for s in hits] == ["multi-angle-approach"]


def test_relevant_skills_falls_back_to_all_when_no_failures(tmp_path):
    lib = SkillLibrary(tmp_path / "lib")
    lib.add(Skill(name="a-skill", category="c", failure_signature="f",
                  when_to_apply="w", strategy="s"))
    assert [s.name for s in relevant_skills(lib, [_tr()])] == ["a-skill"]


def test_media_copy_preserves_relative_subpaths_no_collision(tmp_path):
    task = tmp_path / "s" / "t"; task.mkdir(parents=True)
    raw = tmp_path / "raw"
    (raw / "a").mkdir(parents=True); (raw / "b").mkdir(parents=True)
    (raw / "a" / "kf.png").write_bytes(b"A")
    (raw / "b" / "kf.png").write_bytes(b"B")
    res = ExecuteResult(score=0.5, raw_dir=str(raw),
                        traces=[_tr(media=["a/kf.png"]), _tr(step=2, media=["b/kf.png"])])
    write_execution_context(task, res)
    assert (task / "traces" / "media" / "a" / "kf.png").read_bytes() == b"A"
    assert (task / "traces" / "media" / "b" / "kf.png").read_bytes() == b"B"


def test_write_skills_context(tmp_path):
    task = tmp_path / "s" / "t"; task.mkdir(parents=True)
    write_skills_context(task, [Skill(name="x-skill", category="c",
                                      failure_signature="f", when_to_apply="w",
                                      strategy="s")])
    md = (task / "skills.md").read_text()
    assert "x-skill" in md and md.startswith("# Retrieved skills")
    write_skills_context(task, [])
    assert "(none)" in (task / "skills.md").read_text()


def test_ablate_traces_writes_scalar_outcome_no_traces(tmp_path):
    tr = TraceRecord(step=0, function="grasp", args={}, status="error",
                     result_summary="PLANNING_ERROR", duration_ms=1.0, media=[])
    result = ExecuteResult(0.3333333333333333, traces=[tr])
    write_execution_context(tmp_path, result, ablate_traces=True)
    assert (tmp_path / "outcome.txt").read_text().strip() == "score: 0.3333333333333333"
    assert not (tmp_path / "traces").exists()          # no per-primitive leak
    assert "PLANNING_ERROR" not in (tmp_path / "outcome.txt").read_text()


def test_default_still_writes_full_traces(tmp_path):
    tr = TraceRecord(step=0, function="grasp", args={}, status="error",
                     result_summary="PLANNING_ERROR", duration_ms=1.0, media=[])
    write_execution_context(tmp_path, ExecuteResult(0.0, traces=[tr]))
    assert (tmp_path / "traces" / "trace.json").exists()
    assert "PLANNING_ERROR" in (tmp_path / "traces" / "summary.txt").read_text()
    assert not (tmp_path / "outcome.txt").exists()
