#!/usr/bin/env python3
"""One-off: render a FIXED CaP-X program to an mp4 (no LLM). Reuses the ASPIRE
engine's env setup (capx_execute.run_episode) plus CaP-X's built-in frame
recorder (enable_video_capture / get_video_frames). Writes <out>.mp4 and prints
reward / task_completed so the filename/caption is truthful.

Usage:
  python render_clip.py --program P --config-path YAML --seed S --out OUT.mp4 [--label L]
"""
import argparse
import os
from pathlib import Path

import imageio
import numpy as np


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--program", required=True)
    ap.add_argument("--config-path", required=True)
    ap.add_argument("--seed", type=int, required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--workdir", default="/home/demo/cap-x")
    ap.add_argument("--fps", type=int, default=30)
    args = ap.parse_args()

    os.chdir(args.workdir)

    from capx.envs.configs.instantiate import instantiate
    from capx.envs.configs.loader import DictLoader
    from capx.envs.runner import _start_api_servers

    cfgs = DictLoader.load([args.config_path])
    _start_api_servers(cfgs.get("api_servers"))
    env = instantiate(cfgs["env"])
    try:
        env.reset(seed=args.seed, options={"trial": args.seed})
        if not hasattr(env, "enable_video_capture"):
            raise SystemExit("env has no enable_video_capture — wrong env type")
        env.enable_video_capture(True, clear=True)
        program_src = Path(args.program).read_text()
        obs, reward, terminated, truncated, info = env.step(program_src)
        frames = env.get_video_frames(clear=True)
        ok = bool(info.get("task_completed")) and info.get("sandbox_rc", 1) == 0
        print(f"RESULT seed={args.seed} reward={reward:.3f} "
              f"task_completed={int(info.get('task_completed', False))} "
              f"sandbox_rc={info.get('sandbox_rc')} frames={len(frames)}")
        if not frames:
            raise SystemExit("no frames captured")
        out = Path(args.out)
        out.parent.mkdir(parents=True, exist_ok=True)
        with imageio.get_writer(out, fps=args.fps, format="FFMPEG",
                                codec="libx264") as w:
            for f in frames:
                w.append_data(np.ascontiguousarray(f))
        print(f"WROTE {out} ({len(frames)} frames, {args.fps} fps)")
    finally:
        try:
            env.close()
        except Exception:
            pass


if __name__ == "__main__":
    main()
