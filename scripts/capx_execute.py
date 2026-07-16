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
import os
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
    """Real CaP-X episode: build env from config_path YAML, exec the whole program
    once against the env's primitive namespace (in-process, via env.step), tracing
    each primitive call, and return (success: bool, traces: list of TraceRecord dicts).

    Imports are deferred to keep this module import-light at the top level so
    --selftest keeps working in any (non-capx) venv.
    """
    import time as _time
    from pathlib import Path as _P

    from capx.envs.configs.instantiate import instantiate
    from capx.envs.configs.loader import DictLoader

    if not config_path:
        raise ValueError("--config-path is required for non-selftest run_episode")

    configs = DictLoader.load([config_path])
    env = instantiate(configs["env"])
    media_dir = _P(out_dir)
    traces = []

    def _fmt(v, cap=120):
        s = repr(v)
        return s if len(s) <= cap else s[:cap] + "..."

    def _fmt_args(a, kw):
        return {"args": [_fmt(x) for x in a],
                "kwargs": {k: _fmt(v) for k, v in kw.items()}}

    def _save_frame(tag):
        try:
            img = env.render()
            if img is None:
                return []
            from PIL import Image
            # Seed-prefixed so multiple seeds sharing one out-dir don't clobber
            # each other's frames.
            name = f"seed{seed}_{tag}.png"
            Image.fromarray(img).save(media_dir / name)
            return [name]
        except Exception:
            return []

    def _tracer(name, fn):
        def wrapped(*a, **kw):
            idx = len(traces)
            media = _save_frame(f"step{idx:03d}_{name}_before")
            t0 = _time.time()
            status, summary = "ok", ""
            try:
                result = fn(*a, **kw)
                summary = _fmt(result)
                return result
            except Exception as e:
                status, summary = "error", f"{type(e).__name__}: {e}"
                raise
            finally:
                media += _save_frame(f"step{idx:03d}_{name}_after")
                traces.append({"step": idx, "function": name,
                                "args": _fmt_args(a, kw),
                                "status": status, "result_summary": summary,
                                "duration_ms": (_time.time() - t0) * 1000,
                                "media": media})
        return wrapped

    try:
        env.reset(seed=int(seed), options={"trial": int(seed)})
        for api in env._apis.values():
            for fn_name, fn in list(api.functions().items()):
                setattr(api, fn_name, _tracer(fn_name, fn))
        program_src = _P(program_path).read_text()
        obs, reward, terminated, truncated, info = env.step(program_src)
        ok = bool(info.get("task_completed")) and info.get("sandbox_rc", 1) == 0
        if not traces:
            # Wrapper never fired: instrumentation regressed (e.g. api.functions()
            # binding no longer picks up instance-attribute overrides). Fail loudly
            # rather than silently reporting an empty, unverifiable trace.
            traces.append({"step": 0, "function": "instrumentation", "args": {},
                            "status": "error",
                            "result_summary": "no primitive calls captured",
                            "duration_ms": 0.0, "media": []})
            ok = False
        return ok, traces
    finally:
        try:
            env.close()
        except Exception:
            pass


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
    seeds = [int(s) for s in args.seeds.split(",") if s.strip()]
    if not seeds:
        ap.error("--seeds must be a non-empty comma list")

    if not args.selftest and args.config_path:
        # Launch any API servers (e.g. PyRoKi) declared in the config, once, up
        # front. _start_api_servers skips ports that are already listening, so
        # this is safe to call every invocation.
        from capx.envs.configs.loader import DictLoader
        from capx.envs.runner import _start_api_servers

        _cfgs = DictLoader.load([args.config_path])
        _start_api_servers(_cfgs.get("api_servers"))

    successes, all_traces = 0, []
    for seed in seeds:
        if args.selftest:
            ok, traces = selftest_episode(args.program, seed, out_dir)
        else:
            ok, traces = run_episode(args.program, seed, out_dir, args.config_path)
        successes += bool(ok)
        all_traces.extend(traces)

    tmp = out_dir / "result.json.tmp"
    tmp.write_text(json.dumps(
        {"score": successes / len(seeds), "raw_dir": str(out_dir),
         "traces": all_traces}, indent=1))
    os.replace(tmp, out_dir / "result.json")     # atomic: no torn result.json


if __name__ == "__main__":
    main()
