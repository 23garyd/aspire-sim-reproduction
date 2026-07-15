"""Run parameters. K, T, theta are NOT published in the paper (Appendix E marks them
experiment-specific); these defaults are [RECONSTRUCTED] and must be logged per run."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field


@dataclass(frozen=True)
class RunConfig:
    k: int = 3                    # evosearch population per round
    t: int = 5                    # evosearch max rounds
    theta: float = 1.0            # early-stop score on debugging seeds
    debug_rounds: int = 2         # Stage-1 actor repair rounds before evosearch
    s_dbg: list = field(default_factory=lambda: [0, 1, 2])
    s_val: list = field(default_factory=lambda: [100, 101, 102, 103, 104])
    model_repair: str = "opus"    # diagnosis/repair/skill synthesis
    model_propose: str = "sonnet" # evosearch candidate proposals

    def to_dict(self) -> dict:
        return asdict(self)
