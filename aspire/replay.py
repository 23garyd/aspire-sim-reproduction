"""Budgeted per-seed actor replay (Appendix E's inner loop, App E.3 step 3).

Purpose: give a Stage-1 debug actor an execution path INSIDE its task-dir sandbox to
validate a candidate `fix.py` against ONE debugging seed, through the same audited
engine as the main pipeline, without ever touching S_val or exceeding its per-seed
attempt budget.

Usage (cwd MUST be the task dir the coordinator materialized `replay.json` into):
    python3 -m aspire.replay <program.py> <seed>

Exit codes:
    0 = replay executed (the score is DATA — an audit-rejected or losing fix still
        exits 0; only tool-level failures use nonzero codes)
    2 = usage error (bad argv, or replay.json not materialized in this cwd)
    3 = seed guard: the requested seed is not a debugging seed
    4 = attempt-cap: this seed's per-session budget is exhausted
    5 = engine failure (EngineError from the wrapped engine)
"""
from __future__ import annotations

import json
import os
import shutil
import sys
from pathlib import Path

from aspire.engines import AuditedEngine, CapxEngine, EngineError, FakeEngine
from aspire.schemas import ExecuteResult
from aspire.task_context import summarize_traces

_USAGE = "usage: python3 -m aspire.replay <program.py> <seed>"


def _scrub_dir(path_str: str) -> None:
    """Remove an engine raw-output dir (result.json + keyframe PNGs). Used by the
    ablated replay path so the trace data the actor is meant to be blind to does
    not persist in the actor-readable sandbox after ./replay returns."""
    if path_str and os.path.isdir(path_str):
        shutil.rmtree(path_str, ignore_errors=True)


def _atomic_write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(text)
    os.replace(tmp, path)


def _build_engine(recipe: dict):
    etype = recipe.get("type")
    if etype == "fake":
        inner = FakeEngine([ExecuteResult(s) for s in recipe.get("scores", [])])
    elif etype == "capx":
        inner = CapxEngine(cmd_prefix=recipe["cmd_prefix"], out_root=Path(recipe["out_root"]),
                           timeout_s=recipe.get("timeout_s", 3600))
    else:
        raise EngineError(f"unknown engine type in replay.json: {etype!r}")
    return AuditedEngine(inner)


def main(argv=None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if len(argv) != 2:
        print(_USAGE, file=sys.stderr)
        return 2
    program_arg, seed_arg = argv
    try:
        seed = int(seed_arg)
    except ValueError:
        print(_USAGE, file=sys.stderr)
        return 2

    cwd = Path.cwd()
    recipe_path = cwd / "replay.json"
    if not recipe_path.exists():
        print("no replay.json (replay not materialized here)", file=sys.stderr)
        return 2
    try:
        recipe = json.loads(recipe_path.read_text())
    except (json.JSONDecodeError, KeyError, TypeError) as e:
        print(f"malformed replay.json: {e}", file=sys.stderr)
        return 2
    ablate_traces = bool(recipe.get("ablate_traces", False))

    s_dbg = recipe.get("s_dbg", [])
    if seed not in s_dbg:
        print(f"seed {seed} is not a debugging seed; only {s_dbg} may be replayed "
              "(validation seeds are off-limits)", file=sys.stderr)
        return 3

    program = cwd / program_arg
    if not program.exists():
        print(f"program not found: {program_arg}", file=sys.stderr)
        return 2

    max_attempts = recipe.get("max_attempts_per_seed", 3)
    attempts_path = cwd / "replays" / "attempts.json"
    attempts = {}
    if attempts_path.exists():
        try:
            attempts = json.loads(attempts_path.read_text())
        except (json.JSONDecodeError, KeyError, TypeError) as e:
            print(f"malformed replays/attempts.json: {e}", file=sys.stderr)
            return 2
    count = attempts.get(str(seed), 0)
    if count >= max_attempts:
        print(f"attempt cap reached for seed {seed} ({count}/{max_attempts})",
              file=sys.stderr)
        return 4

    # Atomic file replace (tmp + os.replace) BEFORE executing: a crashed replay
    # still consumed an attempt (deliberate, prevents cap evasion via kill). This
    # is atomic w.r.t. the write itself; the read-modify-write of the counter
    # assumes the actor replays sequentially — concurrent replays could double-
    # spend one attempt. S_val is unaffected either way (this budget only gates
    # replay.py, never Stage 2).
    attempt_no = count + 1
    attempts[str(seed)] = attempt_no
    _atomic_write(attempts_path, json.dumps(attempts))

    try:
        engine = _build_engine(recipe["engine"])
    except (KeyError, TypeError) as e:
        print(f"malformed replay.json: bad engine recipe: {e}", file=sys.stderr)
        return 2

    # M1/M3: execute a COPY inside the attempt dir, never the original path. This
    # keeps audit markers (.AUDIT_REJECTED) scoped to replays/ instead of polluting
    # the task-dir namespace the coordinator manages, and makes path-escape via
    # ../ or an absolute program_arg harmless — the executed artifact is always
    # inside out_dir regardless of where program_arg pointed.
    out = cwd / "replays" / f"seed{seed}_attempt{attempt_no}"
    out.mkdir(parents=True, exist_ok=True)
    exec_copy = out / Path(program_arg).name
    shutil.copyfile(program, exec_copy)

    # F2 (R3 live finding): the real engine's runner os.chdir()s to its own workdir
    # before reading --program; a path that isn't fully resolved (symlinks, or any
    # non-canonical component) then resolves against the WRONG cwd. Always hand the
    # engine a canonical absolute path.
    try:
        result = engine.execute(exec_copy.resolve(), [seed])
    except EngineError as e:
        print(str(e), file=sys.stderr)
        return 5

    if ablate_traces:
        # Ablation: scalar feedback only — no per-primitive trace, summary, or media.
        # The engine still wrote its full raw output (result.json + keyframe PNGs)
        # under result.raw_dir inside this actor-readable sandbox; scrub it before
        # returning so no trace data persists once ./replay hands control back.
        _scrub_dir(result.raw_dir)
        print(f"score: {result.score}")
        return 0

    media_dir = out / "media"
    media_dir.mkdir(parents=True, exist_ok=True)
    _atomic_write(out / "trace.json",
                 json.dumps([t.to_dict() for t in result.traces], indent=1))
    summary = summarize_traces(result.traces)
    _atomic_write(out / "summary.txt", summary)

    raw_dir = Path(result.raw_dir) if result.raw_dir else None
    for t in result.traces:
        for m in t.media:
            if raw_dir is None:
                continue
            src = raw_dir / m
            if not src.exists():
                continue
            dst = media_dir / m
            dst.parent.mkdir(parents=True, exist_ok=True)
            dst.write_bytes(src.read_bytes())

    print(f"score: {result.score}")
    print(summary)
    return 0


if __name__ == "__main__":
    sys.exit(main())
