# B601 Isaac Backend — Milestone 1 ("first light") Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Prove ASPIRE's traced execution engine drives the reBot B601 arm in Isaac Sim — a scripted joint-space program + gripper runs on the arm, each primitive recorded as a `TraceRecord` → `ExecuteResult` — with a two-way command/state loop over the vendor's one-way sim.

**Architecture:** New `robot_b601/` module on `aspire_original_sim`, reusing `aspire/schemas.py` (`TraceRecord`/`ExecuteResult`) unchanged. Mirrors the proven A2 pattern: a `B601Transport` protocol (publish command / latest state) with a deterministic `FakeB601Transport` (unit-tested, no Isaac) and a live `B601IsaacUdpTransport` (UDP `:5005` send / `:5006` recv). A `B601Node` sync facade streams targets and polls to convergence on an injectable clock; a `B601Engine` wraps it with traced primitives. An Isaac-side bridge script closes the loop; a runner exercises it (`--selftest` = Fake).

**Tech Stack:** Python 3 (stdlib only in `robot_b601/` and scripts — `socket`, `json`; NO Isaac imports in unit-tested code), pytest (`-p no:anyio` on simhost), NVIDIA Isaac Sim (live bridge only, `ISAACSIM_ROOT`).

## Global Constraints

- Build on branch `aspire_original_sim`; all new code under `robot_b601/`, `scripts/b601_*.py`, `tests/b601/`. **No changes to `aspire/` package internals** — reuse `aspire.schemas` (`TraceRecord`, `ExecuteResult`) only.
- `robot_b601/` unit-tested code and `B601IsaacUdpTransport` are **stdlib-only** (no Isaac imports) so the whole stack tests without Isaac. Isaac imports appear ONLY in `scripts/b601_isaac_bridge.py` (the live piece, not unit-tested).
- UDP wire schema (both directions): `{"sequence": int, "timestamp": float, "joint_positions": [float×6] (radians), "gripper_position": float (meters)}`. Command port `5005`, state port `5006`.
- Sim: RS USD `usd/RS-rebot-dev-arm/00-arm-rs_asm-v3.usda`, prim `/World/reBotArm`. RS end-to-end (RS is also the real-hardware target, M3).
- Injectable clock everywhere timing matters (deterministic tests via `ManualClock`).
- Tests run with `python3 -m pytest <path> -q -p no:anyio` (the `-p no:anyio` flag is required on simhost). Full suite currently 201 passed.
- The Isaac-side bridge is verified live on the box, reported honestly — never unit-tested-as-passing.

---

### Task 1: `robot_b601` package — clock + transport protocol + `FakeB601Transport`

**Files:**
- Create: `robot_b601/__init__.py`, `robot_b601/clock.py`, `robot_b601/transport.py`
- Create: `tests/b601/__init__.py`, `tests/b601/test_transport.py`

**Interfaces:**
- Produces: `RealClock`/`ManualClock` (`now() -> float`, `sleep(dt)`); `JointCommand(joint_positions: list[float], gripper_position: float)`; `JointState(joint_positions: list[float], gripper_position: float)`; `B601Transport` Protocol (`publish(cmd: JointCommand) -> None`, `latest() -> JointState | None`); `FakeB601Transport(num_joints=6, gap_close=0.34, start=None)`.

- [ ] **Step 1: Write the failing test**

Create `tests/b601/__init__.py` (empty) and `tests/b601/test_transport.py`:

```python
from robot_b601.transport import JointCommand, JointState, FakeB601Transport

def test_fake_converges_toward_target():
    t = FakeB601Transport(num_joints=6, gap_close=0.5)
    t.publish(JointCommand([1.0]*6, 0.04))
    s1 = t.latest()
    assert isinstance(s1, JointState)
    assert all(0.0 < p < 1.0 for p in s1.joint_positions)   # advanced, not yet there
    for _ in range(50):
        s = t.latest()
    assert all(abs(p - 1.0) < 1e-3 for p in s.joint_positions)   # converged
    assert abs(s.gripper_position - 0.04) < 1e-3

def test_fake_stuck_never_moves():
    t = FakeB601Transport(num_joints=6, gap_close=0.0)   # stuck robot
    t.publish(JointCommand([1.0]*6, 0.04))
    for _ in range(100):
        s = t.latest()
    assert all(p == 0.0 for p in s.joint_positions)      # never advanced -> exercises TIMEOUT
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/b601/test_transport.py -q -p no:anyio`
Expected: FAIL — `ModuleNotFoundError: robot_b601`.

- [ ] **Step 3: Write the implementation**

Create `robot_b601/__init__.py` (empty). Create `robot_b601/clock.py`:

```python
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
```

Create `robot_b601/transport.py`:

```python
"""B601 transport seam: the ASPIRE facade talks to an abstract B601Transport, so it
runs against a deterministic FakeB601Transport in tests and a live UDP transport
against Isaac (or, later, real RS hardware). Same interface either way."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable


@dataclass
class JointCommand:
    joint_positions: list[float]     # radians, 6 joints
    gripper_position: float          # meters


@dataclass
class JointState:
    joint_positions: list[float]
    gripper_position: float


@runtime_checkable
class B601Transport(Protocol):
    def publish(self, cmd: JointCommand) -> None: ...
    def latest(self) -> "JointState | None": ...


class FakeB601Transport:
    """Deterministic robot model: closes a fixed fraction of the gap to the last
    commanded target on every state read. gap_close=0.0 models a stuck arm."""

    def __init__(self, num_joints: int = 6, gap_close: float = 0.34,
                 start: list[float] | None = None):
        self.num_joints = num_joints
        self.gap_close = gap_close
        self._cur = list(start) if start is not None else [0.0] * num_joints
        self._tgt = list(self._cur)
        self._grip_cur = 0.0
        self._grip_tgt = 0.0

    def publish(self, cmd: JointCommand) -> None:
        self._tgt = list(cmd.joint_positions)
        self._grip_tgt = float(cmd.gripper_position)

    def latest(self) -> JointState:
        self._cur = [c + self.gap_close * (t - c) for c, t in zip(self._cur, self._tgt)]
        self._grip_cur += self.gap_close * (self._grip_tgt - self._grip_cur)
        return JointState(joint_positions=list(self._cur), gripper_position=self._grip_cur)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m pytest tests/b601/test_transport.py -q -p no:anyio`
Expected: PASS (both)

- [ ] **Step 5: Commit**

```bash
git add robot_b601/__init__.py robot_b601/clock.py robot_b601/transport.py tests/b601/__init__.py tests/b601/test_transport.py
git commit -m "feat(b601): transport seam — protocol + clock + FakeB601Transport"
```

---

### Task 2: `B601Node` facade — poll-to-converge motion

**Files:**
- Create: `robot_b601/node.py`
- Test: `tests/b601/test_node.py`

**Interfaces:**
- Consumes: `B601Transport`, `JointCommand`, `JointState`, `RealClock`/`ManualClock` from Task 1.
- Produces: `MoveResult(reached: bool, residual: float, status: str, iterations: int)`; `B601Node(transport, num_joints=6, clock=None, poll_dt=0.01, home=None)` with `move_to_joints(joints, tol=1e-2, timeout_s=5.0) -> MoveResult` and `set_gripper(pos, tol=1e-2, timeout_s=2.0) -> MoveResult`. `status` is `"ok"` on reach, `"TIMEOUT"` on timeout.

- [ ] **Step 1: Write the failing test**

Create `tests/b601/test_node.py`:

```python
from robot_b601.clock import ManualClock
from robot_b601.transport import FakeB601Transport
from robot_b601.node import B601Node

def _node(gap_close):
    return B601Node(FakeB601Transport(num_joints=6, gap_close=gap_close),
                    clock=ManualClock(), poll_dt=0.02)

def test_move_reaches_target():
    r = _node(0.5).move_to_joints([0.5]*6, tol=1e-2, timeout_s=5.0)
    assert r.reached and r.status == "ok" and r.residual < 1e-2

def test_move_times_out_on_stuck_arm():
    r = _node(0.0).move_to_joints([0.5]*6, tol=1e-2, timeout_s=1.0)
    assert not r.reached and r.status == "TIMEOUT"

def test_gripper_reaches_and_holds_joints():
    node = _node(0.5)
    node.move_to_joints([0.3]*6, tol=1e-2, timeout_s=5.0)
    g = node.set_gripper(0.04, tol=1e-3, timeout_s=2.0)
    assert g.reached and g.status == "ok"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/b601/test_node.py -q -p no:anyio`
Expected: FAIL — `ModuleNotFoundError: robot_b601.node`.

- [ ] **Step 3: Write the implementation**

Create `robot_b601/node.py`:

```python
"""B601Node: synchronous blocking facade over the B601Transport. Re-streams the full
setpoint (joints + gripper) every poll (servo controllers hold only briefly), reads
state, and converges within tol or times out on an injectable clock."""
from __future__ import annotations

from dataclasses import dataclass

from robot_b601.clock import RealClock
from robot_b601.transport import JointCommand


@dataclass
class MoveResult:
    reached: bool
    residual: float
    status: str          # "ok" | "TIMEOUT"
    iterations: int


class B601Node:
    def __init__(self, transport, num_joints: int = 6, clock=None,
                 poll_dt: float = 0.01, home=None):
        self._t = transport
        self._nj = num_joints
        self._clock = clock or RealClock()
        self._poll = poll_dt
        self._last_joints = list(home) if home is not None else [0.0] * num_joints
        self._last_grip = 0.0

    def _stream_until(self, residual_fn, tol, timeout_s) -> MoveResult:
        t0 = self._clock.now()
        iters = 0
        residual = float("inf")
        while True:
            self._t.publish(JointCommand(list(self._last_joints), self._last_grip))
            state = self._t.latest()
            iters += 1
            if state is not None:
                residual = residual_fn(state)
            if residual < tol:
                return MoveResult(True, residual, "ok", iters)
            if self._clock.now() - t0 >= timeout_s:
                return MoveResult(False, residual, "TIMEOUT", iters)
            self._clock.sleep(self._poll)

    def move_to_joints(self, joints, tol: float = 1e-2, timeout_s: float = 5.0) -> MoveResult:
        self._last_joints = list(joints)
        return self._stream_until(
            lambda st: max(abs(a - b) for a, b in zip(st.joint_positions, self._last_joints)),
            tol, timeout_s)

    def set_gripper(self, pos: float, tol: float = 1e-2, timeout_s: float = 2.0) -> MoveResult:
        self._last_grip = float(pos)
        return self._stream_until(
            lambda st: abs(st.gripper_position - self._last_grip),
            tol, timeout_s)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m pytest tests/b601/test_node.py -q -p no:anyio`
Expected: PASS (all three)

- [ ] **Step 5: Commit**

```bash
git add robot_b601/node.py tests/b601/test_node.py
git commit -m "feat(b601): B601Node facade — re-stream setpoint, poll-to-converge, TIMEOUT"
```

---

### Task 3: `B601Engine` — traced primitives → `ExecuteResult`

**Files:**
- Create: `robot_b601/engine.py`
- Test: `tests/b601/test_engine.py`

**Interfaces:**
- Consumes: `B601Node`/`MoveResult` (Task 2), `RealClock`/`ManualClock` (Task 1), `aspire.schemas.TraceRecord`/`ExecuteResult`.
- Produces: `B601Engine(node, clock=None)` with traced `move_to_joints(joints, **kw)` and `set_gripper(pos, **kw)` (each returns the node's `MoveResult` and appends a `TraceRecord`), and `result() -> ExecuteResult` (score = fraction of primitives with status "ok").

- [ ] **Step 1: Write the failing test**

Create `tests/b601/test_engine.py`:

```python
from robot_b601.clock import ManualClock
from robot_b601.transport import FakeB601Transport
from robot_b601.node import B601Node
from robot_b601.engine import B601Engine
from aspire.schemas import ExecuteResult

def test_engine_traces_ok_primitive():
    clock = ManualClock()
    node = B601Node(FakeB601Transport(gap_close=0.5), clock=clock, poll_dt=0.02)
    eng = B601Engine(node, clock=clock)
    eng.move_to_joints([0.4]*6, tol=1e-2, timeout_s=5.0)
    eng.set_gripper(0.04, tol=1e-3, timeout_s=2.0)
    res = eng.result()
    assert isinstance(res, ExecuteResult)
    assert res.score == 1.0
    assert [t.function for t in res.traces] == ["move_to_joints", "set_gripper"]
    assert all(t.status == "ok" for t in res.traces)
    assert all(t.duration_ms >= 0.0 for t in res.traces)
    assert res.traces[0].step == 0 and res.traces[1].step == 1

def test_engine_records_timeout_as_error():
    clock = ManualClock()
    node = B601Node(FakeB601Transport(gap_close=0.0), clock=clock, poll_dt=0.02)
    eng = B601Engine(node, clock=clock)
    eng.move_to_joints([0.4]*6, tol=1e-2, timeout_s=1.0)   # stuck -> TIMEOUT
    res = eng.result()
    assert res.score == 0.0
    assert res.traces[0].status == "error"
    assert "TIMEOUT" in res.traces[0].result_summary
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/b601/test_engine.py -q -p no:anyio`
Expected: FAIL — `ModuleNotFoundError: robot_b601.engine`.

- [ ] **Step 3: Write the implementation**

Create `robot_b601/engine.py`:

```python
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m pytest tests/b601/test_engine.py -q -p no:anyio`
Expected: PASS (both)

- [ ] **Step 5: Commit**

```bash
git add robot_b601/engine.py tests/b601/test_engine.py
git commit -m "feat(b601): B601Engine — traced primitives -> aspire ExecuteResult"
```

---

### Task 4: `B601IsaacUdpTransport` — live two-way UDP

**Files:**
- Modify: `robot_b601/transport.py` (append the UDP transport)
- Test: `tests/b601/test_udp_transport.py`

**Interfaces:**
- Consumes: `JointCommand`/`JointState` (Task 1).
- Produces: `B601IsaacUdpTransport(host="127.0.0.1", cmd_port=5005, state_port=5006)` implementing `B601Transport`: `publish` sends the wire-schema JSON to `host:cmd_port`; `latest` non-blockingly reads the newest datagram on `state_port` and returns a `JointState` (or `None`). Exposes `.state_port` (the actually-bound port, so tests can pass `0`).

- [ ] **Step 1: Write the failing test**

Create `tests/b601/test_udp_transport.py`:

```python
import json
import socket
from robot_b601.transport import JointCommand, JointState, B601IsaacUdpTransport

def test_publish_sends_wire_schema():
    # bind a receiver on an ephemeral cmd port, point the transport at it
    rx = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    rx.bind(("127.0.0.1", 0))
    cmd_port = rx.getsockname()[1]
    t = B601IsaacUdpTransport(host="127.0.0.1", cmd_port=cmd_port, state_port=0)
    t.publish(JointCommand([0.1, 0.2, 0.3, 0.4, 0.5, 0.6], 0.04))
    rx.settimeout(1.0)
    data, _ = rx.recvfrom(4096)
    msg = json.loads(data)
    assert msg["joint_positions"] == [0.1, 0.2, 0.3, 0.4, 0.5, 0.6]
    assert msg["gripper_position"] == 0.04
    assert "sequence" in msg and "timestamp" in msg
    rx.close(); t.close()

def test_latest_reads_newest_state_or_none():
    t = B601IsaacUdpTransport(host="127.0.0.1", cmd_port=0, state_port=0)
    assert t.latest() is None                       # nothing sent yet
    tx = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    for jp in ([0.0]*6, [0.9]*6):                   # newest wins
        tx.sendto(json.dumps({"sequence": 1, "timestamp": 0.0,
                              "joint_positions": jp, "gripper_position": 0.02}).encode(),
                 ("127.0.0.1", t.state_port))
    import time; time.sleep(0.05)
    st = t.latest()
    assert isinstance(st, JointState) and st.joint_positions == [0.9]*6
    tx.close(); t.close()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/b601/test_udp_transport.py -q -p no:anyio`
Expected: FAIL — `ImportError: cannot import name 'B601IsaacUdpTransport'`.

- [ ] **Step 3: Write the implementation**

Append to `robot_b601/transport.py` (keep imports stdlib-only):

```python
import json
import socket
import time


class B601IsaacUdpTransport:
    """Live two-way UDP against the Isaac bridge: publish -> :cmd_port (vendor
    receiver applies joint/gripper targets); latest <- :state_port (the bridge's
    added state-return channel). Stdlib socket only; non-blocking reads. Same seam
    as FakeB601Transport, so the facade is identical in sim and hardware."""

    def __init__(self, host: str = "127.0.0.1", cmd_port: int = 5005,
                 state_port: int = 5006):
        self._host = host
        self._cmd_port = cmd_port
        self._seq = 0
        self._tx = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self._rx = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self._rx.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._rx.bind((host, state_port))
        self._rx.setblocking(False)
        self.state_port = self._rx.getsockname()[1]

    def publish(self, cmd: JointCommand) -> None:
        self._seq += 1
        msg = {"sequence": self._seq, "timestamp": time.time(),
               "joint_positions": list(cmd.joint_positions),
               "gripper_position": float(cmd.gripper_position)}
        self._tx.sendto(json.dumps(msg).encode(), (self._host, self._cmd_port))

    def latest(self) -> "JointState | None":
        newest = None
        while True:                                  # drain to the newest datagram
            try:
                data, _ = self._rx.recvfrom(4096)
            except BlockingIOError:
                break
            newest = data
        if newest is None:
            return None
        m = json.loads(newest)
        return JointState(joint_positions=list(m["joint_positions"]),
                          gripper_position=float(m["gripper_position"]))

    def close(self) -> None:
        self._tx.close()
        self._rx.close()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m pytest tests/b601/test_udp_transport.py -q -p no:anyio`
Expected: PASS (both)

- [ ] **Step 5: Commit**

```bash
git add robot_b601/transport.py tests/b601/test_udp_transport.py
git commit -m "feat(b601): B601IsaacUdpTransport — two-way UDP (:5005 cmd / :5006 state)"
```

---

### Task 5: First-light runner (`--selftest`) + Isaac-side bridge

**Files:**
- Create: `scripts/b601_first_light.py`, `scripts/b601_isaac_bridge.py`
- Test: `tests/b601/test_first_light.py`

**Interfaces:**
- Consumes: `B601Engine`/`B601Node` (Tasks 2–3), `FakeB601Transport`/`B601IsaacUdpTransport` (Tasks 1,4), `ManualClock`/`RealClock`.
- Produces: `scripts/b601_first_light.py` with `build_program()` (the scripted waypoints), a `run(transport, clock) -> ExecuteResult`, and a CLI: `--selftest` uses `FakeB601Transport`+`ManualClock`; otherwise `B601IsaacUdpTransport`+`RealClock`. Writes the result JSON to `--out` (default `b601_first_light_result.json`), exit 0 on success.

- [ ] **Step 1: Write the failing test**

Create `tests/b601/test_first_light.py`:

```python
import json
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]

def test_first_light_selftest_writes_valid_result(tmp_path):
    out = tmp_path / "res.json"
    proc = subprocess.run(
        [sys.executable, "scripts/b601_first_light.py", "--selftest", "--out", str(out)],
        capture_output=True, text=True, cwd=REPO)
    assert proc.returncode == 0, proc.stderr
    res = json.loads(out.read_text())
    assert res["score"] == 1.0                       # every scripted primitive reached
    funcs = [t["function"] for t in res["traces"]]
    assert "move_to_joints" in funcs and "set_gripper" in funcs
    assert all(t["status"] == "ok" for t in res["traces"])

def test_run_is_importable_and_deterministic():
    sys.path.insert(0, str(REPO / "scripts"))
    import b601_first_light as fl
    from robot_b601.clock import ManualClock
    from robot_b601.transport import FakeB601Transport
    res = fl.run(FakeB601Transport(gap_close=0.5), ManualClock())
    assert res.score == 1.0 and len(res.traces) >= 3
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/b601/test_first_light.py -q -p no:anyio`
Expected: FAIL — `scripts/b601_first_light.py` does not exist.

- [ ] **Step 3: Write the runner**

Create `scripts/b601_first_light.py`:

```python
#!/usr/bin/env python3
"""B601 Isaac 'first light': run a scripted joint-space program + gripper through the
traced B601 engine and write an ExecuteResult. --selftest uses the deterministic
FakeB601Transport (no Isaac); otherwise the live UDP transport against the bridge.

Live use (two terminals):
  1) in Isaac: ISAACSIM_ROOT=... <isaac python> scripts/b601_isaac_bridge.py
  2) python3 scripts/b601_first_light.py            # -> b601_first_light_result.json
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))   # repo root importable

from robot_b601.clock import ManualClock, RealClock
from robot_b601.engine import B601Engine
from robot_b601.node import B601Node
from robot_b601.transport import B601IsaacUdpTransport, FakeB601Transport

HOME = [0.0] * 6
WAYPOINTS = [[0.3, -0.2, 0.4, 0.0, 0.3, 0.0],
             [-0.3, 0.2, -0.2, 0.1, -0.3, 0.2]]


def build_program(eng: B601Engine) -> None:
    """home -> waypoint A -> close gripper -> waypoint B -> open gripper -> home."""
    eng.move_to_joints(HOME)
    eng.move_to_joints(WAYPOINTS[0])
    eng.set_gripper(0.0)                      # close
    eng.move_to_joints(WAYPOINTS[1])
    eng.set_gripper(0.04)                     # open
    eng.move_to_joints(HOME)


def run(transport, clock):
    node = B601Node(transport, clock=clock, poll_dt=0.02, home=HOME)
    eng = B601Engine(node, clock=clock)
    build_program(eng)
    return eng.result()


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--selftest", action="store_true",
                    help="run against FakeB601Transport (no Isaac)")
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--out", default="b601_first_light_result.json")
    args = ap.parse_args(argv)

    if args.selftest:
        transport, clock = FakeB601Transport(gap_close=0.5), ManualClock()
    else:
        transport, clock = B601IsaacUdpTransport(host=args.host), RealClock()
    res = run(transport, clock)
    Path(args.out).write_text(res.to_json())
    print(f"score={res.score} primitives={len(res.traces)} -> {args.out}")
    if hasattr(transport, "close"):
        transport.close()
    return 0 if res.score == 1.0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Write the Isaac-side bridge (live-only; not unit-tested)**

Create `scripts/b601_isaac_bridge.py`. It runs INSIDE Isaac Sim (needs `ISAACSIM_ROOT`), so it is verified live on the box, not by pytest:

```python
#!/usr/bin/env python3
"""Isaac-side bridge for B601 first light. Runs inside Isaac Sim. Loads the RS USD arm
at /World/reBotArm, receives joint/gripper commands on UDP :5005 (vendor wire schema),
applies them each sim tick, AND publishes the arm's joint+gripper state back on :5006
so the ASPIRE engine can close the loop. This is the piece that turns the vendor's
one-way sandbox into a two-way channel. Verified live on the box (Isaac required).

Run (in Isaac's python, ISAACSIM_ROOT set):
  <isaac-python> scripts/b601_isaac_bridge.py --usd $ISAACSIM_ROOT/.../00-arm-rs_asm-v3.usda
"""
import argparse
import json
import socket
import time

CMD_PORT = 5005
STATE_PORT = 5006
PRIM = "/World/reBotArm"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--usd", required=True, help="path to 00-arm-rs_asm-v3.usda")
    ap.add_argument("--host", default="127.0.0.1")
    args = ap.parse_args()

    # Isaac imports are deferred so this file only imports cleanly inside Isaac.
    from isaacsim.simulation_app import SimulationApp   # noqa: F401  (real name per Isaac version)
    # NOTE: the exact Isaac boot + ArticulationView API is finalized against the
    # installed Isaac version during the live bring-up; the vendor
    # isaacsim_joint_receiver.py is the reference for loading the USD and writing
    # joint targets to PRIM. This bridge ADDS the state-return send below.

    rx = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    rx.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    rx.bind((args.host, CMD_PORT)); rx.setblocking(False)
    tx = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    seq = 0

    def apply_command(msg, arm):
        arm.set_joint_position_targets(msg["joint_positions"])   # + gripper axis
        # (gripper mapping per the USD's gripper joint; see vendor receiver)

    def read_state(arm):
        return arm.get_joint_positions(), arm.get_gripper_position()

    # --- live loop (pseudocode framed by the real Isaac stepping API) ---
    # while running:
    #     step Isaac
    #     drain rx -> newest command -> apply_command(msg, arm)
    #     jp, gp = read_state(arm)
    #     seq += 1
    #     tx.sendto(json.dumps({"sequence": seq, "timestamp": time.time(),
    #               "joint_positions": list(jp), "gripper_position": float(gp)}).encode(),
    #               (args.host, STATE_PORT))
    raise SystemExit("Run inside Isaac Sim; finalize the ArticulationView API against "
                     "the installed Isaac version (vendor isaacsim_joint_receiver.py is "
                     "the reference). The :5006 state-return send is the only addition.")


if __name__ == "__main__":
    main()
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `python3 -m pytest tests/b601/test_first_light.py -q -p no:anyio`
Expected: PASS (both) — the runner selftest is deterministic; the bridge is not imported by the tests.

- [ ] **Step 6: Commit**

```bash
chmod +x scripts/b601_first_light.py scripts/b601_isaac_bridge.py
git add scripts/b601_first_light.py scripts/b601_isaac_bridge.py tests/b601/test_first_light.py
git commit -m "feat(b601): first-light runner (--selftest) + Isaac-side two-way bridge"
```

---

### Task 6: Full-suite regression gate + push

**Files:** none (verification only)

- [ ] **Step 1: Run the complete suite**

Run: `python3 -m pytest tests/ -q -p no:anyio`
Expected: PASS — prior 201 + the new `tests/b601/` tests (~9).

- [ ] **Step 2: Confirm first-light selftest end-to-end**

Run: `python3 scripts/b601_first_light.py --selftest --out /tmp/b601_res.json && cat /tmp/b601_res.json | python3 -c "import json,sys; d=json.load(sys.stdin); print('score', d['score'], 'primitives', len(d['traces']))"`
Expected: exit 0; `score 1.0 primitives 6`.

- [ ] **Step 3: Push**

```bash
git push aspire_demo aspire_original_sim
```

---

## Self-review notes (spec coverage)

- `B601Transport` protocol + `FakeB601Transport` (deterministic) → Task 1.
- `B601Node` facade (re-stream, poll-to-converge, TIMEOUT) → Task 2.
- Traced `B601Engine` → `aspire.schemas` `TraceRecord`/`ExecuteResult` (no `aspire/` changes) → Task 3.
- Two-way comms — the M1 crux — `B601IsaacUdpTransport` (:5005 cmd / :5006 state), loopback-tested → Task 4.
- First-light runner `--selftest` (CI-safe) + Isaac-side bridge (live-only, honest stub with the API finalized on-box) → Task 5.
- Success criteria (selftest score 1.0, valid traces; live bridge on-box) → Tasks 5–6.
- Stdlib-only in unit-tested code; Isaac imports only in the bridge (deferred) → Tasks 1–5 use no Isaac; Task 5 bridge defers Isaac imports.
- Injectable clock / determinism → `ManualClock` throughout Tasks 2–5.
- **Known honest boundary:** the bridge's exact Isaac boot + ArticulationView calls are finalized against the installed Isaac version during live bring-up (the vendor `isaacsim_joint_receiver.py` is the reference); everything the ASPIRE engine depends on — the transport seam, the two-way wire schema, the traced execution — is fully built and tested here without Isaac. This is the same sim-first / live-integration split the reproduction used for the golden trace.
```
