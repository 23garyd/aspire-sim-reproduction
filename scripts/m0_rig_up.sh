#!/bin/bash
# scripts/m0_rig_up.sh — run ON the GPU box (simhost) as user demo. Installs CaP-X,
# smoke-tests GPU rendering, runs the aspire contract selftest, then prints the
# guided adaptation step for wiring run_episode() to the real CaP-X API.
# Every phase prints PASS or the script dies (set -e) — no silent success claims.
set -euo pipefail

echo "[1/5] clone cap-x + install uv"
[ -d ~/cap-x ] || git clone https://github.com/capgym/cap-x ~/cap-x
command -v uv >/dev/null 2>&1 || curl -LsSf https://astral.sh/uv/install.sh | sh
export PATH="$HOME/.local/bin:$PATH"
echo "    PASS: cap-x present, uv $(uv --version 2>/dev/null || echo '?')"

echo "[2/5] sync env (authoritative steps: ~/cap-x/README.md + docs/)"
cd ~/cap-x && uv sync
echo "    PASS: uv sync"

echo "[3/5] GPU smoke: robosuite headless renders one frame"
uv run --no-sync python - <<'EOF'
import robosuite
env = robosuite.make("Lift", robots="Panda", has_renderer=False,
                     has_offscreen_renderer=True, use_camera_obs=True)
obs = env.reset()
img = next(v for k, v in obs.items() if k.endswith("_image"))
assert img.size > 0
print("    PASS: robosuite offscreen frame", img.shape)
EOF

echo "[4/5] aspire contract selftest (no CaP-X involvement)"
cd ~/aspire_robot_engine
python3 scripts/capx_execute.py --program scripts/capx_execute.py \
  --seeds 0,1 --out-dir /tmp/aspire_selftest --selftest
grep -q '"score": 0.5' /tmp/aspire_selftest/result.json
echo "    PASS: contract selftest (score 0.5)"

echo "[5/5] ADAPTATION step — wire run_episode() to the real CaP-X API"
cat <<'MSG'
Manual (agent-assisted) step, done once on this box:
  1. Read ~/cap-x/README.md, ~/cap-x/docs/, and capx/envs/launch.py to find the
     programmatic episode API (env construction from env_configs/*.yaml, program
     execution against the primitive namespace, per-primitive feedback).
  2. Fill run_episode() in ~/aspire_robot_engine/scripts/capx_execute.py:
     return (success: bool, traces: list of TraceRecord-shaped dicts); save any
     keyframe PNGs under out_dir and reference them in the media field.
  3. Golden capture — run a scripted no-LLM program on one Lift episode:
       python3 scripts/capx_execute.py --program <scripted_lift.py> --seeds 0 \
         --out-dir ~/aspire_runs/golden/lift_seed0 \
         --config-path ~/cap-x/env_configs/<lift-config>.yaml
  4. Copy result.json back to the repo as tests/aspire/golden/lift_seed0_result.json
     and add a test asserting ExecuteResult.from_json parses it, traces are
     non-empty, and every status is "ok" or "error".
M0 is DONE when that test passes on the dev Mac and this script exits 0 here.
MSG
