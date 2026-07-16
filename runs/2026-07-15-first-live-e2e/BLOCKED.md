# BLOCKED: repair written but never replayed

## What is blocked
Step 3 of the workflow (write `fix.py`, replay on each debugging seed, iterate on the new
trace) could not be started. Zero replay attempts were made against seeds 0/1/2 — not
because the three-attempt cap was exhausted, but because no replay path exists from this
session.

## Why
- The session sandbox restricts file access to `/home/demo/aspire_runs/live/robosuite/cube_stack`.
  Listing `/home/demo/aspire_runs/live/robosuite/` is refused, so the capx-path runner
  (which lives above the task dir) cannot be located or invoked.
- The task dir contains no runner: only `code.py`, `skills.md`, `task.md`, `traces/`.
- Probing for an importable engine (`robosuite`, `capx`, ...) required approval that was
  not granted, so engine availability is unconfirmed either way.

## Consequence for the report
`fix_code.py` is a diagnosis-driven repair, **not** a validated one. The diagnosis itself
is well-supported by the trace and keyframes (see `report.json`), but the claim "this
repair makes the seeds pass" has not been tested and is not being made.

## Residual risk in `fix_code.py`
- `close_gripper()` is **not** attested anywhere in `code.py` or `trace.json`. Its
  existence is inferred from the presence of `open_gripper()` and from the task requiring
  a grasp. If the real primitive is named differently, `fix_code.py` raises `NameError` at
  that line and regresses relative to baseline. This is the single highest-risk line and
  the first thing a replay would settle.
- No post-grasp verification (e.g. a gripper-width check) is included, because no such
  getter appears in the trace and inventing one risks the same `NameError`. A marginal or
  air grasp would therefore still fail silently, exactly as the baseline does.
- The `+0.005` release clearance is a judgement call, not a measured value.

## What a replay should check, in order
1. Does `close_gripper()` resolve? If not, grep the skill library / API surface for the
   real name and re-run.
2. Gripper width after the close, and red-cube z after the lift — confirms grasp vs. air
   grasp.
3. Red-cube pose after `open_gripper()` — confirms the stack holds rather than topples.
