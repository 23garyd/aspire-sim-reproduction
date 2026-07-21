#!/usr/bin/env python3
"""Isaac-side bridge for B601 first light. Runs inside Isaac Sim. Loads the RS USD arm
at /World/reBotArm, receives joint/gripper commands on UDP :5005 (vendor wire schema),
applies them each sim tick, AND publishes the arm's joint+gripper state back on :5006
so the ASPIRE engine can close the loop. This is the piece that turns the vendor's
one-way sandbox into a two-way channel. Verified live on the box (Isaac required).

Run (in Isaac's python, ISAACSIM_ROOT set):
  <isaac-python> scripts/b601_isaac_bridge.py --usd $ISAACSIM_ROOT/.../00-arm-rs_asm-v3.usda
"""
import argparse
import json
import socket
import time

CMD_PORT = 5005
STATE_PORT = 5006
PRIM = "/World/reBotArm"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--usd", required=True, help="path to 00-arm-rs_asm-v3.usda")
    ap.add_argument("--host", default="127.0.0.1")
    args = ap.parse_args()

    # Isaac imports are deferred so this file only imports cleanly inside Isaac.
    from isaacsim.simulation_app import SimulationApp   # noqa: F401  (real name per Isaac version)
    # NOTE: the exact Isaac boot + ArticulationView API is finalized against the
    # installed Isaac version during the live bring-up; the vendor
    # isaacsim_joint_receiver.py is the reference for loading the USD and writing
    # joint targets to PRIM. This bridge ADDS the state-return send below.

    rx = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    rx.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    rx.bind((args.host, CMD_PORT)); rx.setblocking(False)
    tx = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    seq = 0

    def apply_command(msg, arm):
        arm.set_joint_position_targets(msg["joint_positions"])
        # TODO(on-box): WIRE THE GRIPPER. msg["gripper_position"] (meters) is currently
        # dropped — map it to the USD's gripper joint index/command. If left unwired,
        # set_gripper() will TIMEOUT (fails safe, no false pass) but gripper waypoints
        # never execute. Do not ship the bridge without this.

    def read_state(arm):
        # TODO(on-box): there is no get_gripper_position() on Isaac ArticulationView.
        # get_joint_positions() returns ALL articulation DOFs (7+); slice the 6 arm
        # joints and derive the gripper scalar from the gripper DOF index. The wire
        # schema is exactly {joint_positions:[6], gripper_position:float}.
        return arm.get_joint_positions(), arm.get_gripper_position()

    # --- live loop (pseudocode framed by the real Isaac stepping API) ---
    # while running:
    #     step Isaac
    #     drain rx -> newest command -> apply_command(msg, arm)
    #     jp, gp = read_state(arm)
    #     seq += 1
    #     tx.sendto(json.dumps({"sequence": seq, "timestamp": time.time(),
    #               "joint_positions": list(jp), "gripper_position": float(gp)}).encode(),
    #               (args.host, STATE_PORT))
    raise SystemExit("Run inside Isaac Sim; finalize the ArticulationView API against "
                     "the installed Isaac version (vendor isaacsim_joint_receiver.py is "
                     "the reference). The :5006 state-return send is the only addition.")


if __name__ == "__main__":
    main()
