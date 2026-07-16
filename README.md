# ASPIRE → AgiBot A2 — Run Guide

Robot-execution layer for the ASPIRE architecture, driving a **live AgiBot A2 (26-joint
bimanual humanoid) simulation**. Proves the full pipeline end-to-end: agent-facing sync
API → traced primitives → transport (ROS2 / A2 HTTP-RPC) → commanded joint move on the
standing robot.

> **TL;DR** — On the Ubuntu box: `./scripts/start_a2_sim.sh` stands the robot, then
> `docker exec … python3 examples/live_a2_arm_move2.py` runs the verified arm move.

---

## Layout

| Path | What it is |
|------|-----------|
| `robot_engine/` | The engine. Sync facade (`aimdk_node.py`), transports (`rclpy_transport.py`, `a2_rpc.py`), ROS binding (`a2_ros_binding.py`), tracing (`trace.py`, `tracing.py`), agent API (`robot_engine.py`), injectable clock (`clock.py`). |
| `examples/` | Runnable demos against the live sim. `live_a2_arm_move2.py` is the **verified** commanded-move script. |
| `tests/` | Unit tests (transport/RPC/binding/tracing/facade). Run anywhere — no robot needed. |
| `scripts/start_a2_sim.sh` | One-command bring-up: container + sim + motion_control, then stands the robot. |

---

## Two ways to run

### A. Unit tests — any machine (Mac or Linux), no robot

Pure Python + pytest; the transports are faked. This is what you run to check the engine
logic without hardware.

```bash
cd /path/to/github_aspire
python3 -m pytest -q          # 27 tests, all green
```

> On the box, pytest needs `-p no:anyio` — a stray `anyio` plugin in `~/.local` is
> incompatible with the system pytest: `python3 -m pytest -q -p no:anyio`.

### B. Live sim — the Ubuntu ROS2 box only

The A2 MuJoCo sim + `motion_control` run inside the `a2-ultra-sim` Docker container on the
Ubuntu box (ROS2 Humble). The Mac **cannot** run this (no ROS2). Package is staged at
`~/aspire_robot_engine/` on the box.

**The box is `simhost` (REDACTED-HOST)** — `ssh USER@simhost`, key-based, no password. Reachable over
the VPN/Tailscale tunnel. Do **not** force password auth (`-o PubkeyAuthentication=no` breaks
the login).

Push changes from the Mac with:

```bash
rsync -az --exclude 'Aspire.pdf' --exclude '__pycache__' --exclude '.pytest_cache' \
  -e ssh ./ USER@simhost:aspire_robot_engine/
```

---

## Live run — step by step (on the Ubuntu box)

### 1. Bring up the stack and stand the robot

```bash
cd ~/aspire_robot_engine
./scripts/start_a2_sim.sh
```

This is idempotent-ish. It:
1. Starts the `a2-ultra-sim` container.
2. Purges stale iceoryx / X locks (the usual post-reboot failure — see Troubleshooting).
3. Launches `mujoco_sim` headless via `xvfb-run` (framebuffer on `DISPLAY=:99`).
4. Launches `motion_control` (serves HTTP-RPC on `:56322`).
5. Re-stages the package into the container (`/tmp/aspire` is ephemeral).
6. **Stands the robot**: `RL_JOINT_DEFAULT` → clicks the MuJoCo **"Load key"** button
   (loads the `home_default` keyframe via `xdotool` at pixel `68,547`) → `RL_LOCOMOTION_DEFAULT`.
7. Verifies and saves a screenshot to `/tmp/stand.png` in the container.

Wait for **`ROBOT STANDING`**. If the printed `current action` is
`McAction_RL_LOCOMOTION_DEFAULT`, the robot is balanced and holding.

### 2. Run the commanded arm move

```bash
docker exec -u 0 a2-ultra-sim bash -c \
  'source /opt/ros/humble/setup.bash; cd /tmp/aspire; \
   PYTHONPATH=.:$PYTHONPATH python3 examples/live_a2_arm_move2.py'
```

Expected behaviour (verified):
- Streams the current arm pose at 50 Hz (satisfies the servo **deadman watchdog**).
- Enters the stiff `RL_LOCOMOTION_ARM_EXT_JOINT_SERVO` mode and holds it.
- Ramps the left shoulder (`idx14_left_arm_joint2`) +1.0 rad over 4 s, logging `cmd` vs `actual`
  (tracks to ~1.657 rad, then hits the joint limit — expected).
- Restores the pose and leaves the robot balanced in `RL_LOCOMOTION_DEFAULT` (never drops to
  `DEFAULT`, which would collapse it).

### 3. Inspect the result visually (optional)

```bash
docker cp a2-ultra-sim:/tmp/stand.png ./stand.png   # then open it
```

---

## Why the sequence matters (the hard-won facts)

- **A2 speaks HTTP-RPC on `:56322`, not ROS2 topics**, for actions/state:
  `POST /rpc/aimdk.protocol.McActionService/SetAction` etc. Arm *joint commands* go over ROS2
  (`/motion/control/arm_joint_command`, `sensor_msgs/JointState`, BEST_EFFORT QoS).
- **The robot must be initialised to the `home_default` keyframe** (the "Load key" click) before
  RL locomotion is stable. Skipping it = robot reverts to `DEFAULT` and falls. This click has no
  keyboard shortcut, hence the `xdotool` pixel click on the Xvfb framebuffer.
- **`RL_LOCOMOTION_ARM_EXT_JOINT_SERVO` has a sub-1-second deadman.** You must be streaming arm
  setpoints *before* entering it and keep streaming, or it faults back to `DEFAULT`.
- **FSM path:** `DEFAULT → STAND_UP → RL_JOINT_DEFAULT → (Load key) → RL_LOCOMOTION_DEFAULT →
  RL_LOCOMOTION_ARM_EXT_JOINT_SERVO`. Indirect transitions are disallowed
  (`allow_action_indirect_transition: false`).

---

## Troubleshooting

| Symptom | Fix |
|---------|-----|
| `SecurityGuard: HAL data is lost` + every `SetAction` refused (action stays `DEFAULT`) | A **stale `motion_control` survived a restart**, still holding `:56322` with a dead iceoryx link. `pkill -9 motion_control` does **not** match it — you must match the full cmdline: `pkill -9 -f "[m]otion_control"`. `start_a2_sim.sh` now does this and verifies zero survivors. |
| `GetAction` returns `Http req has invalid content type application/x-www-form-urlencoded` | aimrt rejects curl's default. Always send `-H 'Content-Type: application/json'` — on **`GetAction` too**, not just `SetAction`. |
| `motion_control` cores on start; `iox-roudi` aborts on a stale lock | Post-reboot stale shared memory. `start_a2_sim.sh` purges it, but manually: `docker exec -u 0 a2-ultra-sim bash -c 'rm -f /tmp/iox* /tmp/*.lock; rm -rf /dev/shm/iceoryx* /dev/shm/iox*'` |
| `xvfb-run` / `xdotool` / `import` not found in container | Fresh container lacks them: `docker exec -u 0 a2-ultra-sim apt-get install -y xvfb xdotool imagemagick x11-utils`. Survives `docker start/stop`, **not** `docker rm`. |
| Robot resets to standing then instantly flops | `Load key` was clicked while the controller was **passive** (`DEFAULT`). Enter `RL_JOINT_DEFAULT` **first**, then click, then `RL_LOCOMOTION_DEFAULT`. |
| Robot not visible in the MuJoCo view after `Load key` | Expected — the keyframe teleports it back to origin while the camera still points where it fell. Not a fault; verify via RPC, not the camera. |
| `librclcpp.so not found` / rclpy import fails | Must `source /opt/ros/humble/setup.bash` before launching anything. |
| `rclpy` not found even after sourcing | Don't clobber ROS's PYTHONPATH — use `PYTHONPATH=.:$PYTHONPATH`, not `PYTHONPATH=.`. |
| Sim won't start headless (GLFW) | Launch via `xvfb-run -a` (framebuffer on `:99`). |
| Robot stands then falls to `DEFAULT` | The "Load key" init was skipped/failed. Re-run step 1; confirm `/tmp/stand.png` shows a standing robot. |
| Arm move shows near-zero motion | Deadman fired — the stream stopped or started too late. Use `live_a2_arm_move2.py` (pre-streams the hold pose). |

---

## Other example scripts

| Script | Purpose |
|--------|---------|
| `examples/live_a2_arm_move2.py` | **Verified** commanded move; assumes robot already standing (run after `start_a2_sim.sh`). |
| `examples/live_a2_arm_move.py` | Full version that also stands the robot itself (STAND_UP → RL_JOINT_DEFAULT → servo). |
| `examples/a2_servo_probe.py` | Diagnose whether the robot holds servo mode or reverts (falls). |
| `examples/a2_mode_probe.py` | Probe available actions / current FSM state. |
| `examples/live_a2_readloop.py` | Stream and print live joint state. |

- **Link probe** — `scripts/link_probe.py`: stdlib-only 50 Hz UDP link characterizer for the future WiFi-vs-NearLink benchmark. Run `--role echo --port 4700` on the far end and `--role probe --target HOST:4700 --hz 50 --duration 10 --json` on the near end to get RTT/jitter/loss plus `max_gap_ms` (the longest echo-free span — the deadman-relevant number, since the A2 servo watchdog faults at ~1s without a command).

Full design notes, feasibility assessment, and the API-mapping spike live in the Obsidian note
`octos/octos_aspire.md`.
