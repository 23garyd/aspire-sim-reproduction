# bounded-action-budget-guard

category: engine-interaction

## Failure signature

A candidate with a per-cell / per-attempt verification or search loop (grid sweep, retry-until-success) crashes mid-run with 'ValueError: executing action in terminated episode' at a high, roughly constant call-index across seeds. Earlier bounded candidates on the same task never approached this; the episode's done flag silently latches once a hidden per-episode action-call budget is exhausted, after which ANY primitive call — including read-only state queries — raises.

## When to apply

Any episodic env (robosuite and similar step-budgeted manipulation/RL tasks) where every primitive call (motion, gripper, AND state reads) consumes a shared, unqueryable per-episode budget, and the candidate uses a nested or unbounded verification/search loop rather than a fixed open-loop sequence. Apply whenever a repair plan multiplies calls per grid cell / retry / arm.

## Strategy

Do not rely on the env to signal budget exhaustion — it only signals by crashing. Pre-bound total call count with a conservative ceiling comfortably below the observed crash point (e.g. ~150 when crashes land at ~190-200), counting reads as well as actions. Prefer a handful of pre-sized cells (e.g. a 2x2 grid, ~24 calls/arm) over dozens (a 5x4 grid, ~180 calls); when a multi-arm search runs sequentially, size it so the LAST arm is still guaranteed its full allotment, not just the first. Never issue an unbounded 'retry until it works' loop. This does not solve the task; it prevents budget-exhaustion crashes from invalidating an otherwise-valid experiment.

## Code sketch

# Hidden per-episode action-call budget: every primitive (motion, gripper,
# AND state reads) consumes it; once exhausted, any further call raises
# ValueError('executing action in terminated episode'). The budget is not
# queryable, so guard it yourself. No sim/asset access required.
MAX_CALLS = 150  # conservative margin below the ~190-200 observed crash point
_calls = 0
def budgeted(fn, *args, **kwargs):
    global _calls
    if _calls >= MAX_CALLS:
        raise RuntimeError('action-budget guard: stopping before episode termination')
    _calls += 1
    return fn(*args, **kwargs)

# Size searches up front so BOTH arms finish within budget:
#   for out in (0.03, 0.08):          # 2x2 = 4 cells/arm, not 5x4 = 20
#     for bar_z in (0.03, 0.07):
#       budgeted(goto_pose_both, ...) # ~6 calls/cell -> ~24 calls/arm
# Never: while not grasped: retry(...)   # unbounded -> guaranteed crash

## Provenance

robosuite/two_arm_lift dbg=0.00 val=0.00
