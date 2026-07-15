#!/usr/bin/env python3
"""Runs INSIDE the cap-x venv on the GPU box. Contract (pinned by tests/aspire/test_run.py):
  capx_execute.py --program P --seeds 0,1,2 --out-dir D [--config-path YAML] [--selftest]
writes D/result.json in the aspire.schemas.ExecuteResult JSON format.

run_episode() is adapted on-box during M0 against the real CaP-X API (see ~/cap-x/docs
and env_configs/*.yaml). --selftest exercises the full harness with a stub episode so
the contract is testable without CaP-X. This file must stay stdlib-only so it runs in
any venv."""
import argparse
import json
import time
from pathlib import Path


def selftest_episode(program_path, seed, out_dir):
    t0 = time.time()
    ok = seed % 2 == 0
    trace = [{"step": 1, "function": "selftest_primitive", "args": {"seed": seed},
              "status": "ok" if ok else "error",
              "result_summary": f"success={ok}",
              "duration_ms": (time.time() - t0) * 1000, "media": []}]
    return ok, trace


def run_episode(program_path, seed, out_dir, config_path):
    """[M0 ADAPTATION POINT] Replace body with real CaP-X calls: build env from
    config_path YAML with this seed, exec the program against the env's primitive
    namespace, collect per-primitive feedback + keyframe paths, return
    (success: bool, traces: list of TraceRecord-shaped dicts)."""
    raise NotImplementedError("adapt to CaP-X API on the GPU box during M0")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--program", required=True)
    ap.add_argument("--seeds", required=True)
    ap.add_argument("--out-dir", required=True)
    ap.add_argument("--config-path", default="")
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args()

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    seeds = [int(s) for s in args.seeds.split(",")]

    successes, all_traces = 0, []
    for seed in seeds:
        if args.selftest:
            ok, traces = selftest_episode(args.program, seed, out_dir)
        else:
            ok, traces = run_episode(args.program, seed, out_dir, args.config_path)
        successes += bool(ok)
        all_traces.extend(traces)

    (out_dir / "result.json").write_text(json.dumps(
        {"score": successes / len(seeds), "raw_dir": str(out_dir),
         "traces": all_traces}, indent=1))


if __name__ == "__main__":
    main()
