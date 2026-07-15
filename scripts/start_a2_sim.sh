#!/bin/bash
# Bring up the A2 sim stack and stand the robot, from the Ubuntu host.
# Run on REDACTED-HOST as user `demo`:  ./scripts/start_a2_sim.sh
# Idempotent-ish: cleans stale state, (re)launches sim + motion_control, re-stages the
# package into the container, then stands the robot (RL_JOINT_DEFAULT -> Load key ->
# RL_LOCOMOTION_DEFAULT). After it prints "ROBOT STANDING", run the demos (see bottom).
set -u
C=a2-ultra-sim
PKG=/home/demo/aspire_robot_engine
RPC=http://127.0.0.1:56322/rpc/aimdk.protocol.McActionService
JH="Content-Type: application/json"   # aimrt REJECTS the curl default (x-www-form-urlencoded)
dex() { docker exec -u 0 "$C" bash -c "$1"; }
getact() { dex "curl -s -m3 -X POST $RPC/GetAction -H '$JH' -d '{}'" \
             | grep -oE '"current_action":"[^"]*"' | cut -d'"' -f4; }

echo "[1/7] start container"
docker start "$C" >/dev/null; sleep 3

echo "[2/7] purge stale procs + iceoryx / X locks"
# MUST match on full cmdline (-f): plain `pkill -9 motion_control` does NOT match it and
# silently leaves it alive, still holding :56322 while its iceoryx link to the old RouDi
# is dead -> "SecurityGuard: HAL data is lost" and every SetAction is refused.
# [b]racket trick stops the pattern from matching this shell's own cmdline (self-kill).
dex 'pkill -9 -f "[a]imrt_main"; pkill -9 -f "[i]ox-roudi"; pkill -9 -f "[m]otion_control"; pkill -9 -f "[X]vfb"; sleep 3; rm -f /tmp/iox* /tmp/*.lock /tmp/.X*-lock; rm -rf /dev/shm/iceoryx* /dev/shm/iox* 2>/dev/null; true'
LEFT=$(dex 'ps -eo args | grep -cE "[a]imrt_main|[i]ox-roudi|[m]otion_control"' | tr -d '[:space:]')
[ "${LEFT:-0}" = "0" ] || { echo "    FAILED: $LEFT stale proc(s) survived the purge"; exit 1; }

echo "[3/7] launch mujoco_sim (headless via xvfb)"
docker exec -d -u 0 "$C" bash -c 'source /opt/ros/humble/setup.bash && cd /home/agi/a2_simulation/mujoco_sim_ultra_1.3/bin && xvfb-run -a ./start_a2_t2d0_ultra.sh > /tmp/sim.log 2>&1'
for i in $(seq 1 15); do sleep 2; dex 'grep -q "startup completed" /tmp/sim.log 2>/dev/null' && { echo "    sim up"; break; }; done

echo "[4/7] launch motion_control (serves :56322)"
docker exec -d -u 0 "$C" bash -c 'source /opt/ros/humble/setup.bash && cd /home/agi/a2_simulation/motion_control_ultra_1.3.26/scripts/motion_control && ./start_motion_control.sh > /tmp/mc.log 2>&1'
for i in $(seq 1 15); do sleep 3; [ -n "$(getact)" ] && { echo "    RPC up (~$((i*3))s)"; break; }; done
[ -n "$(getact)" ] || { echo "    FAILED: no RPC on :56322 after 45s -- see /tmp/mc.log"; exit 1; }

echo "[5/7] re-stage package into container (/tmp is ephemeral)"
dex 'rm -rf /tmp/aspire'; docker cp "$PKG" "$C:/tmp/aspire" >/dev/null

echo "[6/7] stand the robot: RL_JOINT_DEFAULT -> Load key -> RL_LOCOMOTION_DEFAULT"
setact() { dex "curl -s -m4 -X POST $RPC/SetAction -H '$JH' -d '{\"command\":{\"action\":\"McAction_USE_EXT_CMD\",\"ext_action\":\"$1\"}}'" >/dev/null; }
# Order is load-bearing: the controller must be ACTIVE (RL_JOINT_DEFAULT) before the
# keyframe reset, else the robot resets to standing and immediately flops (passive).
setact McAction_RL_JOINT_DEFAULT; sleep 3
[ "$(getact)" = "McAction_RL_JOINT_DEFAULT" ] || { echo "    FAILED: could not enter RL_JOINT_DEFAULT (got '$(getact)')"; exit 1; }
# Load key: click the MuJoCo "Load key" button in the Xvfb :99 framebuffer (no shortcut
# exists). Loads the home_default keyframe (base z=0.95). Coords valid at 1280x1024.
dex 'AUTH=$(ps -eo cmd | grep -oE "/tmp/xvfb-run[^ ]*/Xauthority" | head -1); DISPLAY=:99 XAUTHORITY=$AUTH xdotool mousemove 68 547 sleep 0.3 click 1'
sleep 4
setact McAction_RL_LOCOMOTION_DEFAULT; sleep 4

echo "[7/7] verify"
ACT=$(getact)
echo "    current action: $ACT"
dex 'AUTH=$(ps -eo cmd | grep -oE "/tmp/xvfb-run[^ ]*/Xauthority" | head -1); DISPLAY=:99 XAUTHORITY=$AUTH import -window root /tmp/stand.png' 2>/dev/null
echo "    screenshot saved in container at /tmp/stand.png (docker cp out to inspect)"
echo
# Hold check: SecurityGuard reverts to DEFAULT within ~1s of a fall, so surviving a
# few seconds in RL_LOCOMOTION_DEFAULT is the real proof the robot is standing.
sleep 5
if [ "$(getact)" != "McAction_RL_LOCOMOTION_DEFAULT" ]; then
  echo "NOT STANDING: fell back to '$(getact)' -- robot fell (see /tmp/mc.log for SecurityGuard)."
  exit 1
fi
echo "ROBOT STANDING (RL_LOCOMOTION_DEFAULT held 5s). Now run a demo, e.g.:"
echo "  docker exec -u 0 $C bash -c 'source /opt/ros/humble/setup.bash; cd /tmp/aspire; PYTHONPATH=.:\$PYTHONPATH python3 examples/live_a2_arm_move2.py'"
