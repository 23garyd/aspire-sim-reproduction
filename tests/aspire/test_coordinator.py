import pytest

from aspire.actors import FakeActor, FakeJudge
from aspire.config import RunConfig
from aspire.coordinator import TaskPipeline, ValidationReuseError
from aspire.engines import FakeEngine
from aspire.schemas import ActorReport, ExecuteResult, ProposedSkill
from aspire.skill_library import SkillLibrary


CFG = RunConfig(k=2, t=2, theta=1.0, debug_rounds=1, s_dbg=[0, 1], s_val=[100, 101])


def _task(tmp_path, code="navigate_to_pose([1,2,0])"):
    task = tmp_path / "robosuite" / "handover"
    task.mkdir(parents=True)
    (task / "code.py").write_text(code)
    return task


def _skillful_report(code_path="fix_code.py"):
    return ActorReport(
        outcome="success", diagnosis="buffer", code_path=code_path,
        proposed_skills=(ProposedSkill(
            name="multi-angle-approach", category="navigation",
            failure_signature="PLANNING_ERROR", when_to_apply="near obstacle",
            strategy="rotate approach", code_sketch="for a in [180,-90,90]: pass"),))


def test_baseline_pass_goes_straight_to_validation(tmp_path):
    task = _task(tmp_path)
    engine = FakeEngine([ExecuteResult(1.0),   # Stage 0 on S_dbg
                         ExecuteResult(0.9)])  # Stage 2 on S_val
    lib = SkillLibrary(tmp_path / "lib")
    pipe = TaskPipeline(task, engine, FakeActor(), FakeJudge([]), lib, CFG)
    result = pipe.run()
    assert result.val_score == 0.9 and result.stage_reached == "validated"
    assert engine.calls[1][1] == (100, 101)


def test_debug_then_validate_and_admit_skill(tmp_path):
    task = _task(tmp_path)
    engine = FakeEngine([ExecuteResult(0.0),   # Stage 0 fails
                         ExecuteResult(1.0),   # fix_code.py on S_dbg passes
                         ExecuteResult(1.0)])  # Stage 2
    actor = FakeActor(reports=[_skillful_report()])
    lib = SkillLibrary(tmp_path / "lib")
    (task / "fix_code.py").write_text("clean_fix()")
    pipe = TaskPipeline(task, engine, actor, FakeJudge([True]), lib, CFG)
    result = pipe.run()
    assert result.val_score == 1.0
    assert [s.name for s in lib.load_all()] == ["multi-angle-approach"]


def test_judge_rejection_blocks_admission(tmp_path):
    task = _task(tmp_path)
    engine = FakeEngine([ExecuteResult(0.0), ExecuteResult(1.0), ExecuteResult(1.0)])
    (task / "fix_code.py").write_text("clean_fix()")
    lib = SkillLibrary(tmp_path / "lib")
    pipe = TaskPipeline(task, engine, FakeActor(reports=[_skillful_report()]),
                        FakeJudge([False]), lib, CFG)
    pipe.run()
    assert lib.load_all() == []


def test_audit_violation_blocks_admission_without_judge(tmp_path):
    task = _task(tmp_path)
    engine = FakeEngine([ExecuteResult(0.0), ExecuteResult(1.0), ExecuteResult(1.0)])
    (task / "fix_code.py").write_text("clean_fix()")
    bad = ActorReport(
        outcome="success", diagnosis="d", code_path="fix_code.py",
        proposed_skills=(ProposedSkill(
            name="cheat", category="grasping", failure_signature="f",
            when_to_apply="w", strategy="s",
            code_sketch="q = env.handle.env.sim.data.qpos"),))
    lib = SkillLibrary(tmp_path / "lib")
    pipe = TaskPipeline(task, engine, FakeActor(reports=[bad]),
                        FakeJudge([]), lib, CFG)   # judge never consulted (would raise on pop)
    pipe.run()
    assert lib.load_all() == []


def test_debug_exhausted_falls_through_to_evosearch(tmp_path):
    task = _task(tmp_path)
    engine = FakeEngine([ExecuteResult(0.0),                 # Stage 0
                         ExecuteResult(0.2),                 # debug round fix on S_dbg
                         ExecuteResult(0.0),                 # evosearch baseline re-exec
                         ExecuteResult(1.0), ExecuteResult(0.3),   # iter_00
                         ExecuteResult(0.8)])                # Stage 2 on best
    (task / "fix_code.py").write_text("still_bad()")
    actor = FakeActor(reports=[ActorReport(outcome="fail", diagnosis="d",
                                           code_path="fix_code.py")],
                      candidate_sources=[["good", "meh"]])
    lib = SkillLibrary(tmp_path / "lib")
    pipe = TaskPipeline(task, engine, actor, FakeJudge([]), lib, CFG)
    result = pipe.run()
    assert result.stage_reached == "validated" and result.val_score == 0.8
    assert (task / "evosearch_best_code.py").read_text() == "good"


def test_second_validation_marks_tainted(tmp_path):
    task = _task(tmp_path)
    engine = FakeEngine([ExecuteResult(1.0), ExecuteResult(0.9), ExecuteResult(0.9)])
    lib = SkillLibrary(tmp_path / "lib")
    pipe = TaskPipeline(task, engine, FakeActor(), FakeJudge([]), lib, CFG)
    pipe.run()
    with pytest.raises(ValidationReuseError):
        pipe.validate(task / "code.py")
    assert (task / "TAINTED").exists()
