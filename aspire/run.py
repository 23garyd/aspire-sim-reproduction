"""python -m aspire.run --task-dir T --engine fake|capx ...
Fake engine: --fake-scores comma list consumed in order (dry runs, CI smoke).
Capx engine: --capx-cmd "uv run --no-sync python scripts/capx_execute.py" --out-root R.
Prints ONE json summary line to stdout (last line) for scripting."""
from __future__ import annotations

import argparse
import json
import shlex
import sys
from pathlib import Path

from aspire.actors import ClaudeCodeActor, ClaudeJudge, FakeActor, FakeJudge
from aspire.config import RunConfig
from aspire.coordinator import TaskPipeline
from aspire.engines import CapxEngine, FakeEngine
from aspire.schemas import ExecuteResult
from aspire.skill_library import SkillLibrary


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--task-dir", required=True)
    ap.add_argument("--engine", choices=("fake", "capx"), required=True)
    ap.add_argument("--library", required=True)
    ap.add_argument("--fake-scores", default="")
    ap.add_argument("--capx-cmd", default="")
    ap.add_argument("--out-root", default="")
    ap.add_argument("--prompts", default="prompts")
    args = ap.parse_args(argv)

    cfg = RunConfig()
    if args.engine == "fake":
        engine = FakeEngine([ExecuteResult(float(s))
                             for s in args.fake_scores.split(",") if s])
        actor, judge = FakeActor(), FakeJudge([])
    else:
        engine = CapxEngine(cmd_prefix=shlex.split(args.capx_cmd),
                            out_root=Path(args.out_root))
        actor = ClaudeCodeActor(prompt_file=f"{args.prompts}/actor_debug.md")
        judge = ClaudeJudge(prompt_file=f"{args.prompts}/coordinator_admission.md",
                            workdir=Path(args.task_dir))

    pipe = TaskPipeline(Path(args.task_dir), engine, actor, judge,
                        SkillLibrary(Path(args.library)), cfg)
    result = pipe.run()
    print(json.dumps({"stage_reached": result.stage_reached,
                      "dbg_score": result.dbg_score, "val_score": result.val_score,
                      "program": result.program, "tainted": result.tainted,
                      "admitted": [s.name for s in result.admitted_skills],
                      "config": cfg.to_dict()}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
