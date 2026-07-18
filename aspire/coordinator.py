"""Per-task pipeline (spec data flow):
Stage 0 baseline on S_dbg -> Stage 1 actor debug rounds -> evosearch fallback ->
Stage 2 validation on S_val (EXACTLY ONCE) -> mechanical audit -> judge -> admission.
On a single-GPU box the paper's device-dispatch loop degenerates to sequential tasks;
aspire/run.py iterates TaskPipeline over a task list.
Task context files (traces/, skills.md, task.md) are materialized by TaskPipeline.run()
around each engine execute(), so the actor's task dir matches what its prompt claims."""
from __future__ import annotations

import json
import os
import re
import sys
from dataclasses import dataclass
from pathlib import Path

from aspire.actors import ActorError
from aspire.audit import audit_code
from aspire.config import RunConfig
from aspire.evosearch import evosearch
from aspire.skill_library import Skill, SkillLibrary
from aspire.task_context import (relevant_skills, summarize_traces,
                                 write_execution_context, write_skills_context,
                                 write_task_metadata)


class ValidationReuseError(RuntimeError):
    """S_val was already spent for this task; the run is tainted."""


def _atomic_write(path: Path, text: str) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(text)
    os.replace(tmp, path)


def _atomic_write_bytes(path: Path, data: bytes) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_bytes(data)
    os.replace(tmp, path)


@dataclass(frozen=True)
class TaskResult:
    stage_reached: str        # "validated"
    dbg_score: float
    val_score: float
    program: str              # path of the validated program
    admitted_skills: tuple = ()
    tainted: bool = False
    blocked: bool = False     # actor wrote BLOCKED.md during Stage 1


class TaskPipeline:
    def __init__(self, task_dir: Path, engine, actor, judge, library: SkillLibrary,
                 cfg: RunConfig, task_language: str = ""):
        self.task_dir = Path(task_dir)
        self.engine, self.actor, self.judge = engine, actor, judge
        self.library, self.cfg = library, cfg
        self.task_language = task_language

    # -- replay affordance (App E inner loop) --------------------------------
    def _materialize_replay(self) -> None:
        """Writes ./replay (executable shim), replay.json (engine recipe + policy),
        and resets replays/attempts.json — called before each Stage-1 actor round so
        the per-session attempt budget resets per round (spec: per-round reset)."""
        recipe = self.engine.describe()
        if recipe.get("type") == "capx":
            recipe = dict(recipe, out_root=str(self.task_dir / "replays" / "engine"))
        _atomic_write(self.task_dir / "replay.json", json.dumps(
            {"engine": recipe, "s_dbg": list(self.cfg.s_dbg),
             "max_attempts_per_seed": self.cfg.max_seed_attempts,
             "ablate_traces": self.cfg.ablate_traces}, indent=1))
        # Task dirs live OUTSIDE the repo (e.g. ~/aspire_runs/...); a bare
        # `python3 -m aspire.replay` there raises ModuleNotFoundError because the
        # `aspire` package is only importable from the repo root. Point PYTHONPATH
        # at this repo checkout and use the pipeline's own interpreter (sys.executable)
        # so the shim works regardless of which python/venv launched the run.
        # CAVEAT (verify in R3): this assumes the actor sandbox permits reading files
        # outside the task dir at the OS level. If a future sandbox blocks that,
        # PYTHONPATH alone won't suffice and aspire/ would need to be vendored into
        # the task dir instead.
        # F1 (R3 live finding): use bash's ${VAR:+...} guard, NOT a bare
        # "<repo>:$PYTHONPATH". With an empty/unset inherited $PYTHONPATH, the naive
        # form yields a trailing colon = an empty sys.path entry = cwd-at-import-time.
        # The replay's engine subprocess inherits that env; capx_execute chdirs to
        # ~/cap-x and Python then imports the `capx` package from the SOURCE TREE
        # instead of the venv-installed copy, splitting the API registry across two
        # module instances (live-verified: "API '...' not registered").
        shim = self.task_dir / "replay"
        repo_root = Path(__file__).resolve().parents[1]
        shim_body = (f"#!/bin/bash\n"
                     f"exec env PYTHONPATH=\"{repo_root}${{PYTHONPATH:+:$PYTHONPATH}}\" "
                     f"\"{sys.executable}\" -m aspire.replay \"$@\"\n")
        _atomic_write(shim, shim_body)
        shim.chmod(0o755)
        attempts = self.task_dir / "replays" / "attempts.json"
        attempts.parent.mkdir(parents=True, exist_ok=True)
        _atomic_write(attempts, "{}")

    # -- Stage 2 guard ------------------------------------------------------
    def validate(self, program: Path, dbg_score: float = -1.0):
        marker = self.task_dir / "VALIDATION_DONE"
        started = self.task_dir / "VALIDATION_STARTED"
        if marker.exists():
            (self.task_dir / "TAINTED").touch()
            raise ValidationReuseError(
                f"S_val already used for {self.task_dir}; run marked TAINTED")
        if started.exists():
            (self.task_dir / "TAINTED").touch()
            raise ValidationReuseError(
                f"validation was interrupted for {self.task_dir}; "
                "S_val possibly spent; manual review required")
        _atomic_write(started, json.dumps({"program": str(program)}))
        result = self.engine.execute(program, self.cfg.s_val)
        # G3 invariant: VALIDATION_DONE exists => winner/ is complete. The validation
        # bundle lands BEFORE the DONE marker; a crash in between leaves STARTED,
        # which taints on resume (no silent loss).
        winner_dir = self.task_dir / "winner"
        winner_dir.mkdir(exist_ok=True)
        _atomic_write(winner_dir / "validation_trace.json",
                     json.dumps([t.to_dict() for t in result.traces], indent=1))
        _atomic_write(winner_dir / "validation_summary.txt",
                     summarize_traces(result.traces))
        _atomic_write(marker, json.dumps({"program": str(program),
                                          "score": result.score,
                                          "dbg_score": dbg_score}))
        started.unlink(missing_ok=True)
        return result

    # -- full pipeline ------------------------------------------------------
    def run(self) -> TaskResult:
        """Resume semantics: a completed validation short-circuits the whole run;
        skills admitted before a crash persist in the library, skills not yet
        admitted at crash time are not re-derived (deliberate: re-running the
        actor would re-spend tokens and risk duplicate admissions)."""
        done = self.task_dir / "VALIDATION_DONE"
        if done.exists():
            marker = json.loads(done.read_text())
            return TaskResult(stage_reached="validated",
                              dbg_score=marker.get("dbg_score", -1.0),
                              val_score=marker["score"],
                              program=marker["program"],
                              admitted_skills=(),
                              tainted=(self.task_dir / "TAINTED").exists(),
                              blocked=(self.task_dir / "BLOCKED.md").exists())

        started = self.task_dir / "VALIDATION_STARTED"
        if started.exists():
            (self.task_dir / "TAINTED").touch()
            raise ValidationReuseError(
                f"validation was interrupted for {self.task_dir}; "
                "S_val possibly spent; manual review required")

        # Task dirs are reused (campaign retry, crash before STARTED); a stale
        # BLOCKED.md from a prior attempt must not truncate THIS run's debug loop.
        # Cleared after the DONE gate above so a resumed-done task still reports
        # its historical blocked state. Mirrors AuditedEngine's stale-marker clear.
        (self.task_dir / "BLOCKED.md").unlink(missing_ok=True)

        baseline = self.task_dir / "code.py"
        r = self.engine.execute(baseline, self.cfg.s_dbg)
        dbg_score, program, report = r.score, baseline, None
        latest = r
        winning_result = r          # bundle of the program currently in the lead
        winning_report = None       # Stage-1 report of the program currently in the lead
        # captured at adoption time, NOT read again later: a later Stage-1 round (or
        # even evosearch) may overwrite the same on-disk path (fix_code.py) in place,
        # so the bytes describing the CURRENT winner must be pinned the moment it wins.
        winning_bytes = baseline.read_bytes()
        write_execution_context(self.task_dir, r,
                                ablate_traces=self.cfg.ablate_traces)
        write_task_metadata(self.task_dir, task_language=self.task_language)

        blocked = False
        if dbg_score < self.cfg.theta:
            for _ in range(self.cfg.debug_rounds):          # Stage 1
                write_skills_context(self.task_dir,
                                     relevant_skills(self.library, latest.traces))
                self._materialize_replay()
                report = self.actor.run_debug(self.task_dir, model=self.cfg.model_repair)
                fix = self.task_dir / report.code_path
                r = self.engine.execute(fix, self.cfg.s_dbg)
                latest = r
                if r.score > dbg_score:
                    dbg_score, program = r.score, fix
                    winning_result, winning_report = r, report
                    winning_bytes = fix.read_bytes()
                # BLOCKED.md: the actor may have partially fixed before blocking, so
                # this round's fix is still executed (above) before we stop rounds.
                if (self.task_dir / "BLOCKED.md").exists():
                    blocked = True
                    break
                if dbg_score >= self.cfg.theta:
                    break
                write_execution_context(self.task_dir, r,   # refresh for next round
                                        ablate_traces=self.cfg.ablate_traces)

        evosearch_ran = False
        if self.cfg.t > 0 and dbg_score < self.cfg.theta:   # evosearch fallback
            evosearch_ran = True
            best = evosearch(self.task_dir, self.engine, self.actor, self.cfg,
                             skills=relevant_skills(self.library, latest.traces))
            # >= (adopt on ties) vs Stage-1's >: the evosearch best is
            # disk-checkpointed, so prefer it on ties for resumability.
            if best.score >= dbg_score:
                dbg_score, program = best.score, best.path
                # evosearch persists its own bundle at task level; no Stage-1
                # report describes this program, so both trackers reset:
                winning_result, winning_report = None, None
                # evosearch_best_code.py is already a stable, standalone copy (it is
                # never mutated again), so reading it now is safe.
                winning_bytes = best.path.read_bytes()

        # G3 binding: persist the debug-winner's trace bundle BEFORE validation so a
        # later phase (ExtractValidatedPatterns) can read it; validate() adds the
        # validation bundle before committing VALIDATION_DONE, so DONE => winner/
        # complete. It exists only in memory otherwise.
        winner_dir = self.task_dir / "winner"
        winner_dir.mkdir(exist_ok=True)
        if winning_result is not None:
            _atomic_write(winner_dir / "trace.json",
                         json.dumps([t.to_dict() for t in winning_result.traces], indent=1))
            _atomic_write(winner_dir / "summary.txt",
                         summarize_traces(winning_result.traces))
        else:                        # evosearch winner: bundle persisted at task level
            src = self.task_dir / "evosearch_best_trace.json"
            _atomic_write(winner_dir / "trace.json",
                         src.read_text() if src.exists() else "[]")
            srcsum = self.task_dir / "evosearch_best_summary.txt"
            _atomic_write(winner_dir / "summary.txt",
                         srcsum.read_text() if srcsum.exists() else "(unavailable)")

        # U1 (G6): validate a STABLE COPY of the winning bytes, not the live path —
        # Stage-1 rounds rewrite fix_code.py in place, so if a later round regresses
        # after an earlier round won, the live file no longer matches the winner the
        # dbg_score/winner bundle describe. winning_bytes was pinned at adoption time.
        _atomic_write_bytes(winner_dir / "program.py", winning_bytes)
        program = winner_dir / "program.py"

        val = self.validate(program, dbg_score)             # Stage 2, exactly once

        # Val-score gate on admission: a program that fails (or barely passes)
        # held-out validation must not seed the shared library — skills learned
        # from a near-failing run mislead later tasks. Two live campaigns admitted
        # skills from val 0.0 (M3X) and val 0.10 (lift rep_5); this bars that.
        # Placed before extraction so no actor tokens are spent producing skills
        # that could not be admitted anyway. 0.0 disables the gate.
        if val.score < self.cfg.admission_min_val:
            _atomic_write(self.task_dir / "ADMISSION_GATED",
                         json.dumps({"val_score": val.score,
                                     "admission_min_val": self.cfg.admission_min_val}))
            return TaskResult(stage_reached="validated", dbg_score=dbg_score,
                              val_score=val.score, program=str(program),
                              admitted_skills=(), blocked=blocked)

        # Algorithm 1 line 17 (ExtractValidatedPatterns): run the extraction actor
        # once per task whenever a repair happened (Stage-1 rounds and/or evosearch),
        # over the VALIDATED winner's evidence in winner/. Stage-1's own proposed
        # skills are admitted only from the WINNING round's report — a losing repair
        # (any round) must not leak skills into the library.
        admitted = []
        candidates = []
        repair_happened = (report is not None) or evosearch_ran
        if repair_happened:
            try:
                extraction = self.actor.extract(self.task_dir,
                                                model=self.cfg.model_repair)
                candidates.extend(extraction.proposed_skills)
            except ActorError as e:
                # extraction is best-effort post-validation; winner skills still
                # admitted below. Marker distinguishes "crashed" from "proposed
                # nothing" (G4 re-review carry-forward).
                _atomic_write(self.task_dir / "EXTRACTION_FAILED", str(e))
        if winning_report is not None:
            # Appendix E three-attempt cap: an actor that blew past max_seed_attempts
            # on any seed broke repair discipline — its proposed_skills (but not the
            # separately-vetted extraction candidates above) are ineligible.
            # Arity guard (belt-and-braces alongside schemas._normalize_seed_attempts):
            # a report loaded by OLD reader code could still carry malformed 1-tuple
            # entries; tolerate them here rather than sa[1] IndexError-ing (R3 live
            # crash: an over-eager actor's rich dict shape produced exactly this).
            violation = next((sa for sa in winning_report.seed_attempts
                              if len(sa) >= 2 and sa[1] > self.cfg.max_seed_attempts),
                             None)
            if violation is not None:
                seed, attempts = violation
                _atomic_write(self.task_dir / "DISCIPLINE_VIOLATION",
                             f"seed {seed} used {attempts} attempts "
                             f"(> max_seed_attempts={self.cfg.max_seed_attempts})")
            else:
                candidates.extend(winning_report.proposed_skills)

        provenance = (f"{self.task_dir.parent.name}/{self.task_dir.name} "
                      f"dbg={dbg_score:.2f} val={val.score:.2f}")
        judged_names = set()
        for ps in candidates:
            if ps.name in judged_names:
                continue                                    # judged once per run
            if audit_code(ps.code_sketch):
                continue                                    # mechanical reject, no judge
            kw = list(dict.fromkeys(
                w for w in re.findall(r"[a-z0-9]+",
                (ps.failure_signature + " " + ps.when_to_apply).lower())
                if len(w) >= 4))[:8]
            similar = (self.library.retrieve(categories=[ps.category], keywords=kw)[:5]
                       or self.library.retrieve(categories=[ps.category])[:5])
            judged_names.add(ps.name)
            if self.judge.admit(ps, existing=similar):
                skill = Skill.from_proposed(ps, provenance=provenance)
                self.library.add(skill)
                admitted.append(skill)

        return TaskResult(stage_reached="validated", dbg_score=dbg_score,
                          val_score=val.score, program=str(program),
                          admitted_skills=tuple(admitted), blocked=blocked)
