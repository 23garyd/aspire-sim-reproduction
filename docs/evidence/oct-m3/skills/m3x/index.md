# Skill index

- [bounded-action-budget-guard](engine-interaction/bounded-action-budget-guard.md) — engine-interaction: Any episodic env (robosuite and similar step-budgeted manipulation/RL tasks) where every primitive call (motion, gripper, AND state reads) consumes a shared, unqueryable per-episode budget, and the candidate uses a nested or unbounded verification/search loop rather than a fixed open-loop sequence. Apply whenever a repair plan multiplies calls per grid cell / retry / arm.
