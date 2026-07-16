# First live end-to-end ASPIRE run (G5 exit criterion)

2026-07-15, simhost (RTX 5090), real CaP-X robosuite cube-stack (privileged config,
PyRoKi only), real Claude actors (Opus repair / judge, per RunConfig in summary.json).

Setup: baseline = the task's oracle program with `close_gripper()` removed (silent
no-grasp failure; every primitive returns ok, task never completes).

Outcome (summary.json): debug 1.0 (3/3 seeds incl. physics-flaky seed 0),
**validation 1.0 (5/5 held-out seeds)**, not tainted. One actor round; evosearch not
needed. Actor's diagnosis nailed the omitted actuation from traces alone and added an
unprompted settle-drift re-localization before placement (fix_code.py vs code.py).

Skills: 3 admitted, all via ExtractValidatedPatterns (skills/); the actor's own two
report proposals were judge-rejected as near-duplicates of the extraction output —
library-context dedup working as designed.

BLOCKED.md is legitimate actor feedback: Appendix E's inner per-seed replay loop needs
an execution affordance actors don't have (fixes run coordinator-side). Tracked in the
gap-fix plan backlog.
