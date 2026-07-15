"""The @trace decorator: wraps a RobotEngine primitive so every call emits one
TraceRecord (timed, summarized args/result, status, optional keyframes).

Per-function summarizers keep trace.json compact; status resolvers turn a return
value into ASPIRE's failure-attribution signal (e.g. solve_ik None -> IK_INFEASIBLE).
"""
from __future__ import annotations

import inspect
import time
from functools import wraps

from robot_engine.trace import TraceRecord


def _summarize_value(v):
    if isinstance(v, (list, tuple)):
        return {"len": len(v)}
    if isinstance(v, (int, float, str, bool)) or v is None:
        return v
    shape = getattr(v, "shape", None)
    if shape is not None:
        return {"shape": list(shape)}
    return str(type(v).__name__)


def summarize_args(fn, args, kwargs) -> dict:
    try:
        bound = inspect.signature(fn).bind_partial(*args, **kwargs)
        return {name: _summarize_value(val)
                for name, val in bound.arguments.items() if name != "self"}
    except TypeError:
        return {f"arg{i}": _summarize_value(a) for i, a in enumerate(args)}


# function name -> (result -> summary dict)
SUMMARIZERS = {
    "move_to_joints": lambda r: {"reached": r.reached, "residual": round(r.residual, 6)},
}
# function name -> (result -> status str)
STATUS_RESOLVERS = {
    "move_to_joints": lambda r: r.status,
    "solve_ik": lambda r: "ok" if r is not None else "IK_INFEASIBLE",
}


def trace(fn):
    name = fn.__name__

    @wraps(fn)
    def wrapper(self, *args, **kwargs):
        step = self._log.next_step()
        pre = self._capture_keyframe(step, "pre")
        t0 = time.perf_counter()
        status, error, result = "ok", None, None
        try:
            result = fn(self, *args, **kwargs)
            status = STATUS_RESOLVERS.get(name, lambda r: "ok")(result)
        except Exception as e:
            status, error = "EXCEPTION", repr(e)
            raise
        finally:
            dt = (time.perf_counter() - t0) * 1e3
            post = self._capture_keyframe(step, "post")
            self._log.emit(TraceRecord(
                step=step, function=name,
                args=summarize_args(fn, (self,) + args, kwargs),
                duration_ms=round(dt, 1),
                result=SUMMARIZERS.get(name, lambda r: {})(result) if error is None else {},
                status=status, keyframe_saved=(pre or post), error=error))
        return result

    return wrapper
