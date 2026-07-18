"""python -m aspire.run --task-dir T --engine fake|capx ...
   python -m aspire.run --tasks-root DIR --engine fake|capx ...   (sequential campaign)
Fake engine: --fake-scores comma list consumed in order (dry runs, CI smoke); for
--tasks-root a SINGLE engine instance is shared across every task in the campaign, so
scripted fake scores are consumed across tasks in the order tasks are dispatched.
Capx engine: --capx-cmd "uv run --no-sync python scripts/capx_execute.py" --out-root R.
--task-dir mode prints ONE json summary line to stdout (last line) for scripting.

--tasks-root mode (single-GPU degenerate form of Appendix E's device-dispatch loop):
tasks are discovered two levels deep under DIR (DIR/<suite>/<task>/ containing
code.py), sorted by (suite, task) for a deterministic, resumable order. A task whose
VALIDATION_DONE already exists is never redispatched -- it is "skipped" (a stderr
note is printed) and counted as already-done. A task whose run raises a domain error
(ValidationReuseError/EngineError/ActorError/EvosearchError) is recorded as "failed"
and the campaign continues to the next task. After EVERY task (skipped, done, or
failed) DIR/progress.json is atomically rewritten with the schema:
    {"done": [...], "failed": [...], "pending": [...], "last_update_task": "..."}
where each list holds "<suite>/<task>" keys. "done" includes both tasks completed
in this run AND tasks that were already done before this run started (skipped tasks
are done tasks from the campaign's point of view). "pending" holds not-yet-processed
tasks; "last_update_task" is the most recently processed key. The final stdout line
is a SEPARATE one-line JSON summary of just this run:
    {"tasks": N, "done": n1, "failed": n2, "skipped": n3}
where "done" here counts only tasks freshly validated THIS run (excludes skipped).
Exit code is 0 if no task failed this run, else 2."""
from __future__ import annotations

import argparse
import json
import os
import shlex
import sys
from pathlib import Path

from aspire.actors import ActorError, ClaudeCodeActor, ClaudeJudge, FakeActor, FakeJudge
from aspire.config import RunConfig
from aspire.coordinator import TaskPipeline, ValidationReuseError
from aspire.engines import AuditedEngine, CapxEngine, EngineError, FakeEngine
from aspire.evosearch import EvosearchError
from aspire.schemas import ExecuteResult
from aspire.skill_library import SkillLibrary

_DOMAIN_ERRORS = (ValidationReuseError, EngineError, ActorError, EvosearchError)


def _parse_seed_list(spec: str) -> list[int]:
    """"0,1,2" -> [0,1,2]; "100-103" -> [100,101,102,103] (inclusive);
    mixes like "100-102,200" -> [100,101,102,200]. Raises ValueError on
    malformed or backwards ranges/tokens."""
    if not spec:
        raise ValueError(f"empty seed spec: {spec!r}")
    seeds: list[int] = []
    for part in spec.split(","):
        part = part.strip()
        if not part:
            raise ValueError(f"malformed seed spec: {spec!r}")
        if "-" in part[1:]:
            lo_s, _, hi_s = part.partition("-")
            try:
                lo, hi = int(lo_s), int(hi_s)
            except ValueError:
                raise ValueError(f"malformed seed range: {part!r}") from None
            if hi < lo:
                raise ValueError(f"backwards seed range: {part!r}")
            seeds.extend(range(lo, hi + 1))
        else:
            try:
                seeds.append(int(part))
            except ValueError:
                raise ValueError(f"malformed seed: {part!r}") from None
    return seeds


def _atomic_write_json(path: Path, obj) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(obj, indent=1))
    os.replace(tmp, path)


def _build_capx_actors(prompts_dir: str, task_dir):
    """Actor: debug prompt for run_debug, evosearch prompt for propose."""
    actor = ClaudeCodeActor(
        prompt_file=f"{prompts_dir}/actor_debug.md",
        propose_prompt_file=f"{prompts_dir}/actor_evosearch.md",
        extract_prompt_file=f"{prompts_dir}/extract_patterns.md")
    judge = ClaudeJudge(prompt_file=f"{prompts_dir}/coordinator_admission.md",
                        workdir=Path(task_dir))
    return actor, judge


def _build_engine(args):
    """Every program (Stage-0/1 fixes, evosearch candidates) flows through the
    engine, so wrapping it here is the single choke point for the audit."""
    if args.engine == "fake":
        inner = FakeEngine([ExecuteResult(float(s))
                            for s in args.fake_scores.split(",") if s])
    else:
        inner = CapxEngine(cmd_prefix=shlex.split(args.capx_cmd),
                           out_root=Path(args.out_root))
    return AuditedEngine(inner)


def _discover_tasks(root: Path) -> list:
    """suite/task pattern: root/*/* directories containing code.py, sorted by
    (suite name, task name) for a deterministic, resumable dispatch order."""
    tasks = []
    for suite_dir in sorted(p for p in root.iterdir() if p.is_dir()):
        for task_dir in sorted(p for p in suite_dir.iterdir() if p.is_dir()):
            if (task_dir / "code.py").exists():
                tasks.append(task_dir)
    return tasks


def _run_campaign(args, cfg: RunConfig, engine) -> int:
    """Sequential campaign over --tasks-root: see module docstring for the
    progress.json schema and the done/failed/skipped semantics."""
    root = Path(args.tasks_root)
    tasks = _discover_tasks(root)
    keys = [f"{t.parent.name}/{t.name}" for t in tasks]
    progress = {"done": [], "failed": [], "pending": list(keys),
               "last_update_task": None}
    progress_path = root / "progress.json"
    library = SkillLibrary(Path(args.library))

    done_this_run = failed_this_run = skipped_this_run = 0
    for task_dir, key in zip(tasks, keys):
        progress["pending"].remove(key)
        progress["last_update_task"] = key
        if (task_dir / "VALIDATION_DONE").exists():
            print(f"aspire.run: skipped (done): {key}", file=sys.stderr)
            skipped_this_run += 1
            progress["done"].append(key)
            _atomic_write_json(progress_path, progress)
            continue

        if args.engine == "fake":
            actor, judge = FakeActor(), FakeJudge([])
        else:
            actor, judge = _build_capx_actors(args.prompts, task_dir)
        pipe = TaskPipeline(task_dir, engine, actor, judge, library, cfg)
        try:
            pipe.run()
        except _DOMAIN_ERRORS as e:
            print(f"aspire.run: {key}: {e}", file=sys.stderr)
            failed_this_run += 1
            progress["failed"].append(key)
        else:
            done_this_run += 1
            progress["done"].append(key)
        _atomic_write_json(progress_path, progress)

    print(json.dumps({"tasks": len(tasks), "done": done_this_run,
                      "failed": failed_this_run, "skipped": skipped_this_run}))
    return 0 if failed_this_run == 0 else 2


def main(argv=None):
    ap = argparse.ArgumentParser()
    group = ap.add_mutually_exclusive_group(required=True)
    group.add_argument("--task-dir")
    group.add_argument("--tasks-root")
    ap.add_argument("--engine", choices=("fake", "capx"), required=True)
    ap.add_argument("--library", required=True)
    ap.add_argument("--fake-scores", default="")
    ap.add_argument("--capx-cmd", default="")
    ap.add_argument("--out-root", default="")
    ap.add_argument("--prompts", default="prompts")
    ap.add_argument("--s-dbg", default=None,
                    help="CSV/range seed spec overriding RunConfig.s_dbg, e.g. '0,1,2'")
    ap.add_argument("--s-val", default=None,
                    help="CSV/range seed spec overriding RunConfig.s_val, e.g. '100-119'")
    ap.add_argument("--theta", type=float, default=None,
                    help="override RunConfig.theta (early-stop score on debugging seeds)")
    ap.add_argument("--admission-min-val", type=float, default=None,
                    help="override RunConfig.admission_min_val (min held-out val score "
                         "to admit skills; 0.0 disables the gate)")
    args = ap.parse_args(argv)
    if args.engine == "capx" and (not args.capx_cmd or not args.out_root):
        ap.error("--capx-cmd and --out-root are required for --engine capx")

    overrides = {}
    try:
        if args.s_dbg is not None:
            overrides["s_dbg"] = _parse_seed_list(args.s_dbg)
        if args.s_val is not None:
            overrides["s_val"] = _parse_seed_list(args.s_val)
    except ValueError as e:
        ap.error(str(e))
    if args.theta is not None:
        overrides["theta"] = args.theta
    if args.admission_min_val is not None:
        overrides["admission_min_val"] = args.admission_min_val
    defaults = RunConfig().to_dict()
    resolved_s_dbg = overrides.get("s_dbg", defaults["s_dbg"])
    resolved_s_val = overrides.get("s_val", defaults["s_val"])
    if set(resolved_s_dbg) & set(resolved_s_val):
        ap.error("--s-dbg and --s-val must not overlap")

    cfg = RunConfig(**{**defaults, **overrides})
    engine = _build_engine(args)

    if args.tasks_root:
        return _run_campaign(args, cfg, engine)

    if args.engine == "fake":
        actor, judge = FakeActor(), FakeJudge([])
    else:
        actor, judge = _build_capx_actors(args.prompts, args.task_dir)

    pipe = TaskPipeline(Path(args.task_dir), engine, actor, judge,
                        SkillLibrary(Path(args.library)), cfg)
    try:
        result = pipe.run()
    except _DOMAIN_ERRORS as e:
        print(f"aspire.run: {e}", file=sys.stderr)
        return 2
    print(json.dumps({"stage_reached": result.stage_reached,
                      "dbg_score": result.dbg_score, "val_score": result.val_score,
                      "program": result.program, "tainted": result.tainted,
                      "admitted": [s.name for s in result.admitted_skills],
                      "config": cfg.to_dict()}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
