#!/usr/bin/env python3
"""B601 Isaac 'first light': run a scripted joint-space program + gripper through the
traced B601 engine and write an ExecuteResult. --selftest uses the deterministic
FakeB601Transport (no Isaac); otherwise the live UDP transport against the bridge.

Live use (two terminals):
  1) in Isaac: ISAACSIM_ROOT=... <isaac python> scripts/b601_isaac_bridge.py
  2) python3 scripts/b601_first_light.py            # -> b601_first_light_result.json
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))   # repo root importable

from robot_b601.clock import ManualClock, RealClock
from robot_b601.engine import B601Engine
from robot_b601.node import B601Node
from robot_b601.transport import B601IsaacUdpTransport, FakeB601Transport

HOME = [0.0] * 6
WAYPOINTS = [[0.3, -0.2, 0.4, 0.0, 0.3, 0.0],
             [-0.3, 0.2, -0.2, 0.1, -0.3, 0.2]]


def build_program(eng: B601Engine) -> None:
    """home -> waypoint A -> close gripper -> waypoint B -> open gripper -> home."""
    eng.move_to_joints(HOME)
    eng.move_to_joints(WAYPOINTS[0])
    eng.set_gripper(0.0)                      # close
    eng.move_to_joints(WAYPOINTS[1])
    eng.set_gripper(0.04)                     # open
    eng.move_to_joints(HOME)


def run(transport, clock):
    node = B601Node(transport, clock=clock, poll_dt=0.02, home=HOME)
    eng = B601Engine(node, clock=clock)
    build_program(eng)
    return eng.result()


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--selftest", action="store_true",
                    help="run against FakeB601Transport (no Isaac)")
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--out", default="b601_first_light_result.json")
    args = ap.parse_args(argv)

    if args.selftest:
        transport, clock = FakeB601Transport(gap_close=0.5), ManualClock()
    else:
        transport, clock = B601IsaacUdpTransport(host=args.host), RealClock()
    res = run(transport, clock)
    Path(args.out).write_text(res.to_json())
    print(f"score={res.score} primitives={len(res.traces)} -> {args.out}")
    if hasattr(transport, "close"):
        transport.close()
    return 0 if res.score == 1.0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
