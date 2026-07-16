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


class ReportError(ValueError):
    """report.json missing, malformed, or violating the contract."""


def _normalize_seed_attempts(raw):
    """Accepts the spec's canonical list-of-pairs form AND the actor-friendly dict
    forms actors have been observed to write in the wild (R3 live crash: an actor
    wrote {"0": [{...one dict per attempt...}]}; the old code iterated the DICT
    KEYS into 1-tuples, and coordinator.py's sa[1] then IndexError'd). Returns a
    sorted tuple of (seed:int, attempts:int) pairs; raises ValueError/TypeError on
    anything else so the caller can wrap it into a ReportError."""
    if isinstance(raw, dict):
        # {"0": [ {...}, {...} ]} (one entry per attempt) or {"0": 2} (a count)
        out = []
        for k, v in raw.items():
            n = len(v) if isinstance(v, list) else int(v)
            out.append((int(k), n))
        return tuple(sorted(out))
    out = []
    for entry in raw:                      # spec form: [[seed, attempts], ...]
        seed, attempts = entry             # ValueError on wrong arity -> caught by load()
        out.append((int(seed), int(attempts)))
    return tuple(sorted(out))


@dataclass(frozen=True)
class ProposedSkill:
    name: str
    category: str
    failure_signature: str
    when_to_apply: str
    strategy: str
    code_sketch: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class ActorReport:
    outcome: str                   # "success" | "fail"
    diagnosis: str
    code_path: str                 # final program, relative to the task dir
    proposed_skills: tuple = ()
    debug_validation_rate: float = -1.0   # fraction of debug seeds the final fix passed
    seed_attempts: tuple = ()             # tuple of (seed, attempts) pairs

    _REQUIRED = ("outcome", "diagnosis", "code_path")

    @classmethod
    def load(cls, path) -> "ActorReport":
        try:
            data = json.loads(path.read_text())
        except (OSError, json.JSONDecodeError) as e:
            raise ReportError(f"cannot read {path.name}: {e}") from e
        missing = [k for k in cls._REQUIRED if k not in data]
        if missing:
            raise ReportError(f"{path.name} missing fields: {missing}")
        if data["outcome"] not in ("success", "fail"):
            raise ReportError(f"bad outcome: {data['outcome']!r}")
        try:
            skills = tuple(ProposedSkill(**s) for s in data.get("proposed_skills", []))
        except TypeError as e:
            raise ReportError(f"bad proposed_skill entry: {e}") from e
        try:
            debug_validation_rate = float(data.get("debug_validation_rate", -1.0))
        except (TypeError, ValueError) as e:
            raise ReportError(f"bad debug_validation_rate: {e}") from e
        try:
            seed_attempts = _normalize_seed_attempts(data.get("seed_attempts", []))
        except (ValueError, TypeError, KeyError) as e:
            raise ReportError(
                f"bad seed_attempts in {path.name}: expected [[seed, attempts], ...] "
                f"or {{seed: attempts|list}} ({e})") from e
        return cls(outcome=data["outcome"], diagnosis=data["diagnosis"],
                   code_path=data["code_path"], proposed_skills=skills,
                   debug_validation_rate=debug_validation_rate,
                   seed_attempts=seed_attempts)
