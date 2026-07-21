"""B601Engine: agent-facing traced primitives over a B601Node. Each primitive emits
an aspire.schemas.TraceRecord (the same trace instrument the CaP-X reproduction uses);
result() aggregates them into an ExecuteResult. Duration is measured on the injectable
clock so tests are deterministic (ManualClock advances virtual time as the node polls)."""
from __future__ import annotations

from robot_b601.clock import RealClock
from aspire.schemas import ExecuteResult, TraceRecord


class B601Engine:
    def __init__(self, node, clock=None):
        self._node = node
        self._clock = clock or RealClock()
        self._traces: list[TraceRecord] = []

    def _run(self, function: str, args: dict, fn):
        step = len(self._traces)
        t0 = self._clock.now()
        status, summary = "ok", ""
        try:
            r = fn()
            status = "ok" if r.status == "ok" else "error"
            summary = (f"reached={r.reached} residual={r.residual:.4f} "
                       f"status={r.status} iters={r.iterations}")
        except Exception as e:                       # a primitive raising is a failed step
            status = "error"
            summary = f"{type(e).__name__}: {e}"
            r = None
        dur_ms = (self._clock.now() - t0) * 1000.0
        self._traces.append(TraceRecord(step=step, function=function, args=args,
                                        status=status, result_summary=summary,
                                        duration_ms=dur_ms, media=[]))
        return r

    def move_to_joints(self, joints, **kw):
        return self._run("move_to_joints", {"joints": list(joints)},
                         lambda: self._node.move_to_joints(joints, **kw))

    def set_gripper(self, pos, **kw):
        return self._run("set_gripper", {"pos": float(pos)},
                         lambda: self._node.set_gripper(pos, **kw))

    def result(self) -> ExecuteResult:
        n = len(self._traces)
        ok = sum(1 for t in self._traces if t.status == "ok")
        return ExecuteResult(score=(ok / n if n else 0.0), traces=tuple(self._traces))
