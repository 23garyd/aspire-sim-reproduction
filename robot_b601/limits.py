"""Joint-limit safety clamp for the real B601 arm. Pure + stdlib; the transport
clamps every command before it reaches the wire. Absolute limits come from the
B601-RS URDF (rebotarm_bringup); b601_rs_limits.json ships conservative defaults
until finalized on-bench."""
from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class JointLimits:
    lo: list          # length 6, radians
    hi: list


# Conservative full-range defaults (radians) until finalized from the URDF on-bench.
DEFAULT_LIMITS = JointLimits(lo=[-2.6] * 6, hi=[2.6] * 6)


def clamp_to_limits(joints, limits: JointLimits):
    if not (len(joints) == len(limits.lo) == len(limits.hi)):
        raise ValueError("clamp_to_limits length mismatch")
    clamped = []
    was_clamped = False
    for j, lo, hi in zip(joints, limits.lo, limits.hi):
        c = min(max(float(j), lo), hi)
        if c != j:
            was_clamped = True
        clamped.append(c)
    return clamped, was_clamped


def load_limits(path=None) -> JointLimits:
    if path is None or not os.path.exists(path):
        return DEFAULT_LIMITS
    d = json.loads(Path(path).read_text())
    lo = [float(x) for x in d["lo"]]
    hi = [float(x) for x in d["hi"]]
    if not (len(lo) == 6 and len(hi) == 6):
        raise ValueError("b601 limits must have 6 lo and 6 hi values")
    for i, (lo_i, hi_i) in enumerate(zip(lo, hi)):
        if lo_i > hi_i:
            raise ValueError(f"b601 limits inverted at joint {i}: lo>hi")
    return JointLimits(lo=lo, hi=hi)


@dataclass(frozen=True)
class GripperLimits:
    lo: float          # fully-closed position (metres)
    hi: float          # fully-open position (metres)


# Conservative default gripper stroke (metres) until finalized on-bench.
DEFAULT_GRIPPER_LIMITS = GripperLimits(lo=0.0, hi=0.08)


def clamp_gripper(pos, limits: GripperLimits):
    """Clamp a gripper command into [lo, hi] so set_gripper can never over-travel/crush."""
    c = min(max(float(pos), limits.lo), limits.hi)
    return c, (c != pos)


def load_gripper_limits(path=None) -> GripperLimits:
    """Gripper limits from a b601 config JSON (keys grip_lo/grip_hi). Missing file or
    missing keys -> conservative default; inverted lo>hi -> fail loud."""
    if path is None or not os.path.exists(path):
        return DEFAULT_GRIPPER_LIMITS
    d = json.loads(Path(path).read_text())
    if "grip_lo" not in d or "grip_hi" not in d:
        return DEFAULT_GRIPPER_LIMITS
    lo, hi = float(d["grip_lo"]), float(d["grip_hi"])
    if lo > hi:
        raise ValueError("b601 gripper limits inverted: grip_lo > grip_hi")
    return GripperLimits(lo=lo, hi=hi)
