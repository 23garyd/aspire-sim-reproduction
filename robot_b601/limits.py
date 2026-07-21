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
    return JointLimits(lo=[float(x) for x in d["lo"]],
                       hi=[float(x) for x in d["hi"]])
