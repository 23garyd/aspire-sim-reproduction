"""Execute(P, S) -> ExecuteResult (Algorithm 1). FakeEngine for tests; CapxEngine shells
out to scripts/capx_execute.py inside the cap-x venv on simhost and reads result.json."""
from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Protocol

from aspire.audit import audit_code
from aspire.schemas import ExecuteResult, TraceRecord


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


class AuditedEngine:
    """Decorator engine: every program is mechanically audited before execution.
    Wraps any EngineAdapter so coordinator Stage 0/1, evosearch baseline re-exec,
    and every candidate all flow through the audit choke point."""

    def __init__(self, inner):
        self._inner = inner

    def execute(self, program: Path, seeds: list) -> ExecuteResult:
        try:
            text = program.read_text()
        except OSError as e:
            raise EngineError(f"cannot read program for audit: {e}") from e
        violations = audit_code(text)
        if not violations:
            # clear stale marker: fix_code.py is rewritten in place each round
            program.with_suffix(program.suffix + ".AUDIT_REJECTED").unlink(missing_ok=True)
            return self._inner.execute(program, seeds)
        marker = program.with_suffix(program.suffix + ".AUDIT_REJECTED")
        marker.write_text("\n".join(violations))
        return ExecuteResult(
            score=0.0,
            traces=[TraceRecord(step=0, function="audit", args={"program": str(program)},
                                status="error", result_summary="; ".join(violations),
                                duration_ms=0.0, media=[])],
            raw_dir="")


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
        try:
            proc = subprocess.run(cmd, capture_output=True, text=True,
                                  errors="replace", timeout=self._timeout)
        except subprocess.TimeoutExpired as e:
            raise EngineError(f"engine timed out after {self._timeout}s") from e
        result_file = out_dir / "result.json"
        if not result_file.exists():
            raise EngineError(
                f"engine produced no result.json (exit {proc.returncode}); "
                f"stderr tail: {proc.stderr[-800:]}")
        try:
            return ExecuteResult.from_json(result_file.read_text())
        except (json.JSONDecodeError, KeyError, TypeError) as e:
            raise EngineError(f"malformed result.json: {e}") from e
