# LinkAdapter + link-drop safety benchmark — design

_Date: 2026-07-20. Status: SPEC for review._

**Implementation target: branch `aspire_a2_sim`** (where `robot_engine/` lives:
`ros_transport.py`, `aimdk_node.py`, `clock.py`, `trace.py`). The design doc is
filed with the other specs on `aspire_original_sim` for discoverability; the code
and its plan will be built on a branch off `aspire_a2_sim`.

## Purpose

Deliver the SOW's **acceptance-backbone** artifact — the link-drop safety
benchmark: a robot arm receiving 50 Hz commands over a link; the link is broken
mid-motion; the robot freezes safely within its watchdog window instead of
flailing; the link recovers and work resumes — measured, per carrier, and
re-runnable. Two coupled pieces:
1. **`LinkAdapter`** — a transport-neutral seam so the same 50 Hz control stream +
   telemetry runs over loopback / Wi-Fi / NearLink unchanged (the M2 adapter item;
   NearLink is just another carrier).
2. **The benchmark** — inject a mid-motion link break and measure time-to-fault,
   spurious-fault rate, and reconnect-recovery off the existing trace pipeline.

## What already exists (the seam we build on)

`AimdkNode.move_to_joints(joints, tol, timeout_s)` talks to an abstract
`RosTransport` (Protocol: `publish(topic, msg)` / `latest(topic)`) and
**re-streams the setpoint every poll iteration**, converging within `tol` or
timing out on an **injectable clock** (`RealClock` / `ManualClock`). Tests use
`FakeRosTransport` (deterministic; `gap_close` models convergence, `gap_close=0`
models a stuck robot). This means the whole benchmark is deterministically
testable with no hardware — the LinkAdapter slots in at the transport seam and the
ManualClock makes timing exact.

## Architecture

### Part 1 — `LinkAdapter` (a `RosTransport` decorator)

`LinkAdapter(inner: RosTransport, condition: LinkCondition, clock)` implements the
`RosTransport` Protocol, so `AimdkNode` is unchanged. It gates every call through a
link condition:
- `publish(topic, msg)`: if the link is UP → forward to `inner`; if DOWN → drop
  (the setpoint never reaches the robot). Optional loss/latency/jitter.
- `latest(topic)`: if UP → return `inner.latest`; if DOWN → return `None` (the
  telemetry return path is cut too).

**`LinkCondition` policies** (small, pluggable, clock-keyed):
- `AlwaysUp` — loopback / healthy (identity passthrough).
- `ScriptedLink(intervals)` — up/down on a schedule keyed to `clock.now()`, e.g.
  "UP until t=T, DOWN for D, UP after" — the mid-motion break. Optional
  `loss`/`latency_s`/`jitter_s` for degraded (not-fully-down) conditions.

**Carrier neutrality:** the same `LinkAdapter` runs in-sim (`inner =
FakeRosTransport`, deterministic) or over a real radio (`inner =` a UDP transport
to the robot-side node — the M2 `link_probe.py` already proves 50 Hz UDP works over
the carrier). Swapping the inner transport swaps the carrier; the safety logic and
metrics are identical. This is the transport-neutrality the SOW requires and what
makes NearLink "just another transport."

### Part 2 — `DeadmanWatchdog` + benchmark

The real A2 joint-servo mode faults to safe (DEFAULT) if the 50 Hz stream stops for
its sub-1s window. We model that explicitly (it is the safety property, distinct
from `move_to_joints`'s longer convergence `timeout_s`):

`DeadmanWatchdog(window_s)`: fed the setpoint **arrival** timeline; `faulted()` is
true once `now - last_arrival > window_s`. In sim, "arrival" = a `publish` that the
`LinkAdapter` actually forwarded (UP); a DOWN link stops arrivals → the gap grows →
at `window_s` the watchdog faults. On real hardware this mirrors the controller's
built-in deadman; the model lets us measure it deterministically.

**Benchmark harness** (`scripts/link_drop_benchmark.py`): drives a commanded arm
move through `AimdkNode` + `LinkAdapter`, with a `ScriptedLink` break at a chosen
mid-motion time, feeding each forwarded setpoint's timestamp to the
`DeadmanWatchdog`. It records, per run, three **pre-registered** metrics and emits
a per-carrier result table.

## Pre-registered metrics

Definitions fixed before any measurement:
- **time-to-fault** = (watchdog fault time) − (link-break time). Safety target:
  **≤ `window_s`** — the robot freezes within its deadman window instead of
  flailing. Reported in ms.
- **spurious-fault rate** = number of watchdog faults during a **healthy** run (no
  scripted break), over N runs. Target **0**. Validates the watchdog threshold
  against the link's real jitter (M2 measured max gap 38 ms ≪ 1 s window ⇒ predicts
  zero false trips; the benchmark confirms it per carrier).
- **reconnect-recovery time** = (motion resumes: first post-restore setpoint the
  robot acts on / convergence resumes) − (link-restore time). Reported in ms.

## Data flow

1. Harness builds `AimdkNode(LinkAdapter(inner, ScriptedLink(break@T,dur=D), clock),
   ...)` and a `DeadmanWatchdog(window_s)`.
2. Runs `move_to_joints(target)`; each poll, `LinkAdapter.publish` either forwards
   (arrival → watchdog fed) or drops (no arrival).
3. At `T`, link goes DOWN → arrivals stop → at `T + window_s` the watchdog faults
   (time-to-fault ≈ window_s). At `T+D`, link restores → arrivals resume →
   recovery time measured.
4. The `@trace`d primitive records the timeline (`TraceRecord`); the harness reads
   fault/recovery timestamps from it and writes a JSON result + a table row.

## Testing (deterministic, no hardware)

Every metric has a `ManualClock` + `FakeRosTransport` + `ScriptedLink` test:
- `LinkAdapter` passthrough when UP == inner's behavior; drops publishes and
  returns None when DOWN.
- time-to-fault: scripted break → watchdog faults at ~`window_s` after the break
  (exact under ManualClock).
- spurious-fault: healthy run (AlwaysUp) over the full move → watchdog never faults.
- reconnect-recovery: break then restore → arrivals resume, recovery time == restore
  → next-arrival gap.
Follows the existing `robot_engine/` TDD discipline (fake at the transport boundary,
ManualClock for time).

## Components (files)

- `robot_engine/link_adapter.py` — `LinkAdapter` + `LinkCondition` (`AlwaysUp`,
  `ScriptedLink`).
- `robot_engine/deadman.py` — `DeadmanWatchdog`.
- `scripts/link_drop_benchmark.py` — harness: run move, inject break, collect the 3
  metrics, write result JSON + per-carrier table.
- `tests/test_link_adapter.py`, `tests/test_deadman.py`,
  `tests/test_link_drop_benchmark.py` — deterministic coverage.

## Sim-first, real-radio as a carrier swap

Build and validate the entire benchmark deterministically in-sim first
(ManualClock / FakeRosTransport). The real-radio measurement pass then swaps the
inner transport to a UDP socket to the robot-side node over the carrier
(loopback / Wi-Fi / NearLink / BLE) — the radio changes the numbers, not the logic
— producing the per-carrier comparison rows for M2 (adapter + baselines) and M4
(the finale). The real-radio carrier is a thin concrete `RosTransport` added at
measurement time; it is out of scope for the first (sim) build.

## Not doing (YAGNI)

- No real-radio UDP transport in the first build (sim-first; carrier swap later).
- No changes to `AimdkNode`/`RobotEngine` (the seam already fits).
- No live A2-sim integration test in the plan (the deterministic model is the
  testable core; the live A2 run is a separate measurement pass, like the golden
  trace).
- No new metrics beyond the three pre-registered ones.
- No RclpyTransport changes (the LinkAdapter wraps whatever inner transport it is
  given).

## Deliverable mapping

- **M2:** `LinkAdapter` = the "interchangeable communication-adapter interface"
  item; running the probe/benchmark over carriers fills the radio-comparison tables.
- **M4:** the link-drop safety benchmark = the acceptance-backbone deliverable;
  its recording is the finale demo (arm over radio → break → safe freeze → recover).
