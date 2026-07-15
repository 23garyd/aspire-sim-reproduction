"""On-disk contracts. ExecuteResult JSON is the pinned contract between the orchestrator
and scripts/capx_execute.py; change it only with a test change."""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field


@dataclass(frozen=True)
class TraceRecord:
    step: int
    function: str
    args: dict
    status: str            # "ok" | "error"
    result_summary: str
    duration_ms: float
    media: list = field(default_factory=list)   # engine-relative paths (keyframes, overlays)

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "TraceRecord":
        return cls(**d)


@dataclass(frozen=True)
class ExecuteResult:
    score: float           # fraction of seeds succeeded, 0..1
    traces: tuple = ()     # tuple[TraceRecord, ...]
    raw_dir: str = ""

    def __init__(self, score: float, traces=(), raw_dir: str = ""):
        object.__setattr__(self, "score", score)
        object.__setattr__(self, "traces", tuple(traces))
        object.__setattr__(self, "raw_dir", raw_dir)

    def to_json(self) -> str:
        return json.dumps({"score": self.score, "raw_dir": self.raw_dir,
                           "traces": [t.to_dict() for t in self.traces]}, indent=1)

    @classmethod
    def from_json(cls, text: str) -> "ExecuteResult":
        d = json.loads(text)
        return cls(score=d["score"], raw_dir=d.get("raw_dir", ""),
                   traces=[TraceRecord.from_dict(t) for t in d.get("traces", [])])
