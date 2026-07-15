"""Execute(P, S) -> ExecuteResult (Algorithm 1). FakeEngine for tests; CapxEngine shells
out to scripts/capx_execute.py inside the cap-x venv on simhost and reads result.json."""
from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Protocol

from aspire.schemas import ExecuteResult


class EngineError(RuntimeError):
    pass


class EngineAdapter(Protocol):
    def execute(self, program: Path, seeds: list) -> ExecuteResult: ...


class FakeEngine:
    """Pops scripted ExecuteResults in order; records calls for assertions."""

    def __init__(self, results):
        self._results = list(results)
        self.calls = []

    def execute(self, program: Path, seeds: list) -> ExecuteResult:
        self.calls.append((str(program), tuple(seeds)))
        if not self._results:
            raise EngineError("FakeEngine exhausted: more execute() calls than scripted results")
        return self._results.pop(0)


class CapxEngine:
    """cmd_prefix examples: ["uv", "run", "--no-sync", "python", "scripts/capx_execute.py"]
    (on the GPU box) or an ssh-prefixed variant from the Mac.
    Contract: runner receives --program --seeds 0,1,2 --out-dir D and writes D/result.json."""

    def __init__(self, cmd_prefix: list, out_root: Path, timeout_s: int = 3600):
        self._prefix = list(cmd_prefix)
        self._out_root = Path(out_root)
        self._timeout = timeout_s
        self._n = 0

    def execute(self, program: Path, seeds: list) -> ExecuteResult:
        self._n += 1
        out_dir = self._out_root / f"exec_{self._n:04d}"
        cmd = self._prefix + ["--program", str(program),
                              "--seeds", ",".join(str(s) for s in seeds),
                              "--out-dir", str(out_dir)]
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=self._timeout)
        result_file = out_dir / "result.json"
        if not result_file.exists():
            raise EngineError(
                f"engine produced no result.json (exit {proc.returncode}); "
                f"stderr tail: {proc.stderr[-800:]}")
        return ExecuteResult.from_json(result_file.read_text())
