"""Injectable clock so poll loops are testable without real time (mirrors the A2 pattern)."""
import time


class RealClock:
    def now(self) -> float:
        return time.perf_counter()

    def sleep(self, dt: float) -> None:
        time.sleep(dt)


class ManualClock:
    """Deterministic clock: sleep advances virtual time instead of blocking."""

    def __init__(self, start: float = 0.0):
        self._t = start

    def now(self) -> float:
        return self._t

    def sleep(self, dt: float) -> None:
        self._t += dt
