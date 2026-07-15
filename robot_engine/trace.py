"""Per-primitive trace record and logger — the heart of ASPIRE's execution engine.

Every primitive call emits one TraceRecord. `write()` serializes them to trace.json
in the trial directory, in the exact shape the actor agent inspects for failure
attribution (function, summarized args, duration, summarized result, status, keyframe).
"""
from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass, asdict, field
from typing import Any


@dataclass
class TraceRecord:
    step: int
    function: str
    args: dict[str, Any]
    duration_ms: float
    result: dict[str, Any]
    status: str                      # "ok" | "IK_INFEASIBLE" | "PLANNING_ERROR" | "TIMEOUT" | ...
    keyframe_saved: bool
    error: str | None = None
    t: float = field(default_factory=time.time)


class TraceLogger:
    def __init__(self, trial_dir: str):
        self.trial_dir = trial_dir
        self.keyframe_dir = os.path.join(trial_dir, "keyframes")
        self._step = 0
        self.records: list[TraceRecord] = []

    def next_step(self) -> int:
        self._step += 1
        return self._step

    def emit(self, record: TraceRecord) -> None:
        self.records.append(record)

    def write(self) -> None:
        os.makedirs(self.trial_dir, exist_ok=True)
        path = os.path.join(self.trial_dir, "trace.json")
        with open(path, "w") as f:
            json.dump([asdict(r) for r in self.records], f, indent=2)
