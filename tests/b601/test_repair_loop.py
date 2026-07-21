import sys
from pathlib import Path

from aspire.actors import FakeActor, FakeJudge
from aspire.config import RunConfig
from aspire.coordinator import TaskPipeline
from aspire.engines import AuditedEngine, CapxEngine
from aspire.schemas import ActorReport, ProposedSkill
from aspire.skill_library import SkillLibrary

REPO = Path(__file__).resolve().parents[2]
BASE = REPO / "runs" / "2026-07-21-b601-real-cube-lift"
FAILING = (BASE / "baseline_grasp_air.py").read_text()
CORRECT = (BASE / "baseline_lift.py").read_text()          # M3c's correct lift = the "fix"


def _fix_report():
    return ActorReport(
        outcome="success",
        diagnosis="gripper closed 10cm above the cube; descend to cube.z before closing",
        code_path="fix_code.py",
        proposed_skills=(ProposedSkill(
            name="descend-before-grasp", category="manipulation",
            failure_signature="GRASP_MISS", when_to_apply="cube perceived but not grasped",
            strategy="move_to_pose to the cube's z, then close_gripper, then lift",
            code_sketch="move_to_pose(c.x,c.y,c.z); close_gripper()"),))


def test_failing_baseline_repaired_to_validated(tmp_path):
    task = tmp_path / "robosuite" / "cube_lift"
    task.mkdir(parents=True)
    (task / "code.py").write_text(FAILING)             # Stage-0: grasps air -> score 0 < theta
    (task / "fix_code.py").write_text(CORRECT)         # the actor's repair: the correct lift

    cmd = [sys.executable, str(REPO / "scripts" / "b601_execute.py"),
           "--config-path", str(BASE / "cube_lift_fake.json")]
    engine = AuditedEngine(CapxEngine(cmd, out_root=tmp_path / "exec"))
    actor = FakeActor(
        reports=[_fix_report()],
        extraction_reports=[ActorReport(outcome="success", diagnosis="d",
                                        code_path="fix_code.py")])
    cfg = RunConfig(k=2, t=0, theta=0.5, debug_rounds=1, s_dbg=[0, 1], s_val=[100, 101])
    lib = SkillLibrary(tmp_path / "lib")

    result = TaskPipeline(task, engine, actor, FakeJudge([True]), lib, cfg).run()

    # The FAILING baseline fell below theta and DROVE the repair path (unlike M3c's passing
    # baseline, which skipped the actor entirely):
    assert actor.debug_calls != []
    # The fix lifted -> reached held-out validation with a perfect score, no LLM/hardware:
    assert result.stage_reached == "validated"
    assert result.dbg_score == 1.0 and result.val_score == 1.0
