# Replay affordance — live end-to-end validation (R3)

2026-07-16, simhost. Same broken-baseline cube-stack setup as the first live e2e, but the
actor now has `./replay <program> <seed>` (budgeted App E inner loop).

What the actor did, from attempts.json + report.json: replayed its repair once on EACH
debug seed (0, 1, 2 — one attempt each, 3 of 9 budget), saw 3/3 pass, wrote fix_code.py
and reported outcome "success" with seed_attempts evidence — and, for the first time
across all live runs, **no BLOCKED.md**. Pipeline: dbg 1.0 → val 0.6 (3/5 held-out,
physics variance) → skill "close-gripper-before-lift" admitted through the discipline
check that the previous attempt crashed.

R3 also caught and fixed, live: the shim's trailing-colon PYTHONPATH poisoning the
engine subprocess (dual-import split the CaP-X API registry), and the seed_attempts
shape mismatch the G2 review had predicted ("add an arity guard when a reader lands").
Both now normalized/guarded with the live payloads as regression tests.
