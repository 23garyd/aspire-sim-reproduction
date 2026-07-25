#!/usr/bin/env python3
"""Print 'x,y' of the black_bowl for a LIBERO task. Runs in .venv-libero.
Usage: capx_bowl_xy.py --workdir /home/demo/cap-x --config-path <cfg>

The env/api construction mirrors scripts/capx_execute.py:run_episode exactly
(chdir workdir, DictLoader.load([config]), instantiate(configs["env"]), reset),
then reads the privileged bowl pose from the instantiated api. Imports are
deferred so --help works outside .venv-libero."""
import argparse
import os


def _build_api(workdir, config_path):
    # Exact construction from capx_execute.py:run_episode (deferred imports so this
    # module stays import-light outside the capx venv).
    if workdir:
        os.chdir(workdir)
    from capx.envs.configs.instantiate import instantiate
    from capx.envs.configs.loader import DictLoader

    configs = DictLoader.load([config_path])
    env = instantiate(configs["env"])
    # capx_execute resets before touching apis; a valid privileged observation
    # needs the sim loaded for this task's seed.
    env.reset(seed=0, options={"trial": 0})
    # The privileged config declares a single api (FrankaLiberoPrivilegedApi);
    # pick the one exposing get_object_pose from env._apis (as capx_execute reaches
    # apis via env._apis).
    for api in env._apis.values():
        if hasattr(api, "get_object_pose"):
            return api
    raise RuntimeError("no api with get_object_pose in env._apis")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--workdir", required=True)
    ap.add_argument("--config-path", required=True)
    args = ap.parse_args()
    api = _build_api(args.workdir, args.config_path)
    # FrankaLiberoPrivilegedApi.get_object_pose(object_name) -> (position, quat_wxyz);
    # position is a (3,) XYZ array. (No use_multiview arg on the privileged api.)
    position, _quat = api.get_object_pose("black_bowl")
    x, y = float(position[0]), float(position[1])
    print(f"{x:.5f},{y:.5f}")


if __name__ == "__main__":
    main()
