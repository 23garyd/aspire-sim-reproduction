"""Per-task pipeline (spec data flow):
Stage 0 baseline on S_dbg -> Stage 1 actor debug rounds -> evosearch fallback ->
Stage 2 validation on S_val (EXACTLY ONCE) -> mechanical audit -> judge -> admission.
On a single-GPU box the paper's device-dispatch loop degenerates to sequential tasks;
aspire/run.py iterates TaskPipeline over a task list."""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from aspire.audit import audit_code
from aspire.config import RunConfig
from aspire.evosearch import evosearch
from aspire.skill_library import Skill, SkillLibrary


class ValidationReuseError(RuntimeError):
    """S_val was already spent for this task; the run is tainted."""


@dataclass(frozen=True)
class TaskResult:
    stage_reached: str        # "validated"
    dbg_score: float
    val_score: float
    program: str              # path of the validated program
    admitted_skills: tuple = ()


class TaskPipeline:
    def __init__(self, task_dir: Path, engine, actor, judge, library: SkillLibrary,
                 cfg: RunConfig):
        self.task_dir = Path(task_dir)
        self.engine, self.actor, self.judge = engine, actor, judge
        self.library, self.cfg = library, cfg

    # -- Stage 2 guard ------------------------------------------------------
    def validate(self, program: Path):
        marker = self.task_dir / "VALIDATION_DONE"
        if marker.exists():
            (self.task_dir / "TAINTED").touch()
            raise ValidationReuseError(
                f"S_val already used for {self.task_dir}; run marked TAINTED")
        result = self.engine.execute(program, self.cfg.s_val)
        marker.write_text(json.dumps({"program": str(program), "score": result.score}))
        return result

    # -- full pipeline ------------------------------------------------------
    def run(self) -> TaskResult:
        baseline = self.task_dir / "code.py"
        r = self.engine.execute(baseline, self.cfg.s_dbg)
        dbg_score, program, report = r.score, baseline, None

        if dbg_score < self.cfg.theta:
            for _ in range(self.cfg.debug_rounds):          # Stage 1
                report = self.actor.run_debug(self.task_dir, model=self.cfg.model_repair)
                fix = self.task_dir / report.code_path
                r = self.engine.execute(fix, self.cfg.s_dbg)
                if r.score > dbg_score:
                    dbg_score, program = r.score, fix
                if dbg_score >= self.cfg.theta:
                    break

        if dbg_score < self.cfg.theta:                      # evosearch fallback
            best = evosearch(self.task_dir, self.engine, self.actor, self.cfg,
                             skills=self.library.load_all())
            if best.score >= dbg_score:
                dbg_score, program = best.score, best.path

        val = self.validate(program)                        # Stage 2, exactly once

        admitted = []
        if report is not None:
            provenance = (f"{self.task_dir.parent.name}/{self.task_dir.name} "
                          f"dbg={dbg_score:.2f} val={val.score:.2f}")
            for ps in report.proposed_skills:
                if audit_code(ps.code_sketch):
                    continue                                # mechanical reject, no judge
                if self.judge.admit(ps):
                    skill = Skill.from_proposed(ps, provenance=provenance)
                    self.library.add(skill)
                    admitted.append(skill)

        return TaskResult(stage_reached="validated", dbg_score=dbg_score,
                          val_score=val.score, program=str(program),
                          admitted_skills=tuple(admitted))
