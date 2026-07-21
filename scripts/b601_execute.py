#!/usr/bin/env python3
"""B601 cube-lift engine. Honors the capx_execute contract so it is a drop-in for
`aspire.run --engine capx --capx-cmd`. Per seed: reset env, audit the program text
(reused forbidden-API wall), exec it against the env's privileged primitive namespace,
score by env.success(). --selftest uses the deterministic FakeCubeLiftEnv (no Isaac);
a real --config-path uses IsaacCubeLiftEnv (on-box)."""
import argparse
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))   # repo root importable

from aspire.audit import audit_code
from robot_b601.task import FakeCubeLiftEnv


def _err_trace(step, function, summary):
    return {"step": step, "function": function, "args": {}, "status": "error",
            "result_summary": summary, "duration_ms": 0.0, "media": []}


def run_episode(program_path, seed, env):
    env.reset(seed)
    src = Path(program_path).read_text()
    violations = audit_code(src)
    if violations:
        return False, [_err_trace(0, "audit", "; ".join(violations))]
    ns = env.namespace()
    try:
        exec(src, ns)                       # program calls primitives by bare name
        ok = env.success()
    except Exception as e:                  # a raising program fails the seed, not the run
        traces = [t.to_dict() for t in env.traces()]
        traces.append(_err_trace(len(traces), "program_error", f"{type(e).__name__}: {e}"))
        return False, traces
    return ok, [t.to_dict() for t in env.traces()]


def _build_env(args):
    if args.selftest or not args.config_path:
        return FakeCubeLiftEnv()
    from robot_b601.task import IsaacCubeLiftEnv     # deferred: Isaac only on the live path
    return IsaacCubeLiftEnv(args.config_path)


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--program", required=True)
    ap.add_argument("--seeds", required=True)
    ap.add_argument("--out-dir", required=True)
    ap.add_argument("--config-path", default="")
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--workdir", default="")
    args = ap.parse_args(argv)
    if args.workdir:
        os.chdir(args.workdir)

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    seeds = [int(s) for s in args.seeds.split(",") if s.strip()]
    env = _build_env(args)

    successes, all_traces = 0, []
    for seed in seeds:
        ok, traces = run_episode(args.program, seed, env)
        successes += bool(ok)
        all_traces.extend(traces)

    tmp = out_dir / "result.json.tmp"
    tmp.write_text(json.dumps(
        {"score": successes / len(seeds), "raw_dir": str(out_dir),
         "traces": all_traces}, indent=1))
    os.replace(tmp, out_dir / "result.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
