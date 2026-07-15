import pytest

from aspire.actors import FakeActor, FakeJudge
from aspire.config import RunConfig
from aspire.coordinator import TaskPipeline, ValidationReuseError
from aspire.engines import AuditedEngine, EngineError, FakeEngine
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


def test_run_short_circuits_after_validation(tmp_path):
    task = _task(tmp_path)
    lib = SkillLibrary(tmp_path / "lib")
    first = TaskPipeline(task, FakeEngine([ExecuteResult(1.0), ExecuteResult(0.9)]),
                         FakeActor(), FakeJudge([]), lib, CFG).run()
    assert not (task / "VALIDATION_STARTED").exists()
    # resume: FakeEngine([]) raises if ANY engine call happens
    second = TaskPipeline(task, FakeEngine([]), FakeActor(), FakeJudge([]), lib, CFG).run()
    assert second.val_score == first.val_score == 0.9
    assert second.program == first.program
    assert second.dbg_score == first.dbg_score == 1.0
    assert not (task / "TAINTED").exists()
    assert second.tainted is False


def test_run_fast_fails_on_interrupted_marker_before_any_work(tmp_path):
    task = _task(tmp_path)
    (task / "VALIDATION_STARTED").touch()
    lib = SkillLibrary(tmp_path / "lib")
    pipe = TaskPipeline(task, FakeEngine([]), FakeActor(), FakeJudge([]), lib, CFG)
    with pytest.raises(ValidationReuseError, match="interrupted"):
        pipe.run()   # FakeEngine([]) proves no Stage-0 work happened


def test_interrupted_validation_taints(tmp_path):
    task = _task(tmp_path)
    (task / "VALIDATION_STARTED").touch()          # crash artifact
    lib = SkillLibrary(tmp_path / "lib")
    pipe = TaskPipeline(task, FakeEngine([ExecuteResult(1.0)]), FakeActor(),
                        FakeJudge([]), lib, CFG)
    with pytest.raises(ValidationReuseError, match="interrupted"):
        pipe.run()
    assert (task / "TAINTED").exists()


def test_evosearch_worse_than_debug_keeps_debug_program(tmp_path):
    task = _task(tmp_path)
    cfg = RunConfig(k=2, t=1, theta=1.0, debug_rounds=1, s_dbg=[0, 1], s_val=[100, 101])
    engine = FakeEngine([ExecuteResult(0.0),               # Stage 0
                         ExecuteResult(0.5),               # debug fix on S_dbg
                         ExecuteResult(0.0),               # evosearch baseline
                         ExecuteResult(0.3), ExecuteResult(0.2),  # iter_00 candidates
                         ExecuteResult(0.9)])              # Stage 2 on the DEBUG program
    (task / "fix_code.py").write_text("decent_fix()")
    actor = FakeActor(reports=[ActorReport(outcome="fail", diagnosis="d",
                                           code_path="fix_code.py")],
                      candidate_sources=[["worse1", "worse2"]])
    lib = SkillLibrary(tmp_path / "lib")
    result = TaskPipeline(task, engine, actor, FakeJudge([]), lib, cfg).run()
    assert result.dbg_score == 0.5
    assert result.program.endswith("fix_code.py")          # debug program won
    assert engine.calls[-1][0].endswith("fix_code.py")     # S_val ran on it


def test_second_validation_marks_tainted(tmp_path):
    task = _task(tmp_path)
    engine = FakeEngine([ExecuteResult(1.0), ExecuteResult(0.9), ExecuteResult(0.9)])
    lib = SkillLibrary(tmp_path / "lib")
    pipe = TaskPipeline(task, engine, FakeActor(), FakeJudge([]), lib, CFG)
    pipe.run()
    with pytest.raises(ValidationReuseError):
        pipe.validate(task / "code.py")
    assert (task / "TAINTED").exists()


def test_cheating_fix_scores_zero_and_never_executes(tmp_path):
    task = _task(tmp_path)                        # clean baseline code.py
    engine = FakeEngine([ExecuteResult(0.4),      # Stage 0 baseline (clean, executes)
                         # NOTE: no result scripted for the fix — it must be blocked
                         ExecuteResult(0.4),      # evosearch baseline re-exec
                         ExecuteResult(0.5), ExecuteResult(0.6),  # clean candidates
                         ExecuteResult(0.9)])     # Stage 2 validation on best
    audited = AuditedEngine(engine)
    (task / "fix_code.py").write_text("q = env.handle.env.sim.data.qpos  # cheat")
    actor = FakeActor(reports=[ActorReport(outcome="success", diagnosis="d",
                                           code_path="fix_code.py")],
                      candidate_sources=[["cand1", "cand2"]])
    lib = SkillLibrary(tmp_path / "lib")
    cfg = RunConfig(k=2, t=1, theta=1.0, debug_rounds=1, s_dbg=[0, 1], s_val=[100, 101])
    result = TaskPipeline(task, audited, actor, FakeJudge([]), lib, cfg).run()
    # cheat fix audited out (score 0 < baseline 0.4) -> evosearch wins with 0.6
    assert result.dbg_score == 0.6
    assert (task / "fix_code.py.AUDIT_REJECTED").exists()
    assert result.val_score == 0.9


def test_validate_blocks_cheating_program(tmp_path):
    task = _task(tmp_path)
    cheat = task / "cheat.py"
    cheat.write_text("if seed == 100:\n    return_success()")
    engine = AuditedEngine(FakeEngine([]))    # any real execution would raise
    lib = SkillLibrary(tmp_path / "lib")
    pipe = TaskPipeline(task, engine, FakeActor(), FakeJudge([]), lib, CFG)
    result = pipe.validate(cheat)
    assert result.score == 0.0
    assert (task / "cheat.py.AUDIT_REJECTED").exists()


def test_run_materializes_task_context_for_actor(tmp_path):
    from aspire.schemas import TraceRecord
    from aspire.skill_library import Skill
    task = _task(tmp_path)
    fail_trace = TraceRecord(step=1, function="navigate_to_pose", args={},
                             status="error", result_summary="PLANNING_ERROR near table",
                             duration_ms=5.0, media=[])
    engine = FakeEngine([ExecuteResult(0.0, traces=[fail_trace]),
                         ExecuteResult(1.0), ExecuteResult(1.0)])
    (task / "fix_code.py").write_text("clean_fix()")
    lib = SkillLibrary(tmp_path / "lib")
    lib.add(Skill(name="multi-angle-approach", category="navigation",
                  failure_signature="repeated PLANNING_ERROR near obstacle",
                  when_to_apply="w", strategy="s"))
    pipe = TaskPipeline(task, engine, FakeActor(reports=[_skillful_report()]),
                        FakeJudge([True]), lib, CFG, task_language="pick up the can")
    pipe.run()
    assert "PLANNING_ERROR" in (task / "traces" / "summary.txt").read_text()
    assert "pick up the can" in (task / "task.md").read_text()
    assert "multi-angle-approach" in (task / "skills.md").read_text()


def test_second_debug_round_context_reflects_first_fix_failure(tmp_path):
    from aspire.schemas import TraceRecord
    from aspire.skill_library import Skill
    task = _task(tmp_path)
    base_fail = TraceRecord(step=1, function="navigate_to_pose", args={}, status="error",
                            result_summary="PLANNING_ERROR near table", duration_ms=1.0,
                            media=[])
    fix1_fail = TraceRecord(step=1, function="grasp_object", args={}, status="error",
                            result_summary="GRIPPER_SLIP on lid", duration_ms=1.0,
                            media=[])
    engine = FakeEngine([ExecuteResult(0.0, traces=[base_fail]),   # Stage 0
                         ExecuteResult(0.2, traces=[fix1_fail]),   # round-1 fix
                         ExecuteResult(1.0),                       # round-2 fix
                         ExecuteResult(0.9)])                      # S_val
    (task / "fix_code.py").write_text("attempt()")
    lib = SkillLibrary(tmp_path / "lib")
    lib.add(Skill(name="slip-recovery", category="grasping",
                  failure_signature="GRIPPER_SLIP under load",
                  when_to_apply="w", strategy="s"))
    cfg = RunConfig(k=2, t=1, theta=1.0, debug_rounds=2, s_dbg=[0, 1], s_val=[100, 101])
    actor = FakeActor(reports=[
        ActorReport(outcome="fail", diagnosis="d1", code_path="fix_code.py"),
        ActorReport(outcome="success", diagnosis="d2", code_path="fix_code.py")])
    pipe = TaskPipeline(task, engine, actor, FakeJudge([]), lib, cfg)
    result = pipe.run()
    assert result.val_score == 0.9
    # round-2 skills.md was retrieved from round-1's GRIPPER_SLIP failure
    assert "slip-recovery" in (task / "skills.md").read_text()
    # traces/ holds round-1's failure (written at end of round 1), not the winning round-2 trace
    assert "GRIPPER_SLIP" in (task / "traces" / "summary.txt").read_text()


def test_winner_bundle_persisted_for_extraction(tmp_path):
    from aspire.schemas import TraceRecord
    task = _task(tmp_path)
    fix_trace = TraceRecord(step=1, function="grasp_object", args={}, status="ok",
                            result_summary="in_hand=True", duration_ms=1.0, media=[])
    val_trace = TraceRecord(step=1, function="grasp_object", args={}, status="ok",
                            result_summary="validated_grasp", duration_ms=1.0, media=[])
    engine = FakeEngine([ExecuteResult(0.0),                       # Stage 0
                         ExecuteResult(1.0, traces=[fix_trace]),   # fix wins
                         ExecuteResult(0.9, traces=[val_trace])])  # S_val
    (task / "fix_code.py").write_text("clean_fix()")
    lib = SkillLibrary(tmp_path / "lib")
    pipe = TaskPipeline(task, engine, FakeActor(reports=[_skillful_report()]),
                        FakeJudge([True]), lib, CFG)
    pipe.run()
    w = task / "winner"
    assert "in_hand=True" in (w / "trace.json").read_text()
    assert "validated_grasp" in (w / "validation_trace.json").read_text()
    assert "FAILURES: 0" in (w / "summary.txt").read_text()


def test_winner_bundle_from_evosearch_winner(tmp_path):
    task = _task(tmp_path)
    engine = FakeEngine([ExecuteResult(0.0),                 # Stage 0
                         ExecuteResult(0.2),                 # debug fix
                         ExecuteResult(0.0),                 # evosearch baseline
                         ExecuteResult(1.0), ExecuteResult(0.3),  # candidates
                         ExecuteResult(0.8)])                # S_val
    (task / "fix_code.py").write_text("still_bad()")
    actor = FakeActor(reports=[ActorReport(outcome="fail", diagnosis="d",
                                           code_path="fix_code.py")],
                      candidate_sources=[["good", "meh"]])
    lib = SkillLibrary(tmp_path / "lib")
    pipe = TaskPipeline(task, engine, actor, FakeJudge([]), lib, CFG)
    pipe.run()
    w = task / "winner"
    assert (w / "trace.json").exists()          # sourced from evosearch_best_trace.json
    assert (w / "validation_trace.json").exists()


def test_baseline_immediate_win_persists_winner_bundle(tmp_path):
    from aspire.schemas import TraceRecord
    task = _task(tmp_path)
    ok_tr = TraceRecord(step=1, function="grasp_object", args={}, status="ok",
                        result_summary="clean_baseline_win", duration_ms=1.0, media=[])
    engine = FakeEngine([ExecuteResult(1.0, traces=[ok_tr]), ExecuteResult(0.9)])
    lib = SkillLibrary(tmp_path / "lib")
    TaskPipeline(task, engine, FakeActor(), FakeJudge([]), lib, CFG).run()
    assert "clean_baseline_win" in (task / "winner" / "trace.json").read_text()
    assert (task / "winner" / "validation_trace.json").exists()


def test_winner_debug_bundle_written_before_validation(tmp_path):
    from aspire.schemas import TraceRecord
    task = _task(tmp_path)
    tr = TraceRecord(step=1, function="f", args={}, status="ok",
                     result_summary="pre_val_evidence", duration_ms=1.0, media=[])
    # engine exhausts ON the S_val call -> validate raises EngineError
    engine = FakeEngine([ExecuteResult(1.0, traces=[tr])])
    lib = SkillLibrary(tmp_path / "lib")
    pipe = TaskPipeline(task, engine, FakeActor(), FakeJudge([]), lib, CFG)
    with pytest.raises(EngineError):
        pipe.run()
    # debug-winner bundle already on disk despite validation never completing
    assert "pre_val_evidence" in (task / "winner" / "trace.json").read_text()
    assert not (task / "VALIDATION_DONE").exists()


def test_admission_passes_similar_skills_to_judge(tmp_path):
    from aspire.skill_library import Skill
    task = _task(tmp_path)
    engine = FakeEngine([ExecuteResult(0.0), ExecuteResult(1.0), ExecuteResult(1.0)])
    (task / "fix_code.py").write_text("clean_fix()")
    lib = SkillLibrary(tmp_path / "lib")
    lib.add(Skill(name="old-nav-skill", category="navigation", failure_signature="f",
                  when_to_apply="w", strategy="s"))
    judge = FakeJudge([True])
    pipe = TaskPipeline(task, engine, FakeActor(reports=[_skillful_report()]),
                        judge, lib, CFG)
    pipe.run()
    assert judge.admit_calls == [("multi-angle-approach", ("old-nav-skill",))]
