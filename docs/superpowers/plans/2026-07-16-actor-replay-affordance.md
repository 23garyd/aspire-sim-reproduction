# Actor Replay Affordance — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:subagent-driven-development.
> Executes against spec `docs/superpowers/specs/2026-07-16-actor-replay-affordance-design.md`.

**Goal:** budgeted per-seed replay command inside the actor sandbox (App E inner loop).
**Suite baseline:** 155 passed. Branch `aspire_original_sim`.

### Unit R1 — engine recipes + aspire/replay.py (TDD, fake-testable)
- `FakeEngine.describe()` → `{"type": "fake", "scores": [remaining scripted scores]}`;
  `CapxEngine.describe()` → `{"type": "capx", "cmd_prefix": [...], "out_root": "...",
  "timeout_s": N}`; `AuditedEngine.describe()` delegates to inner.
- `aspire/replay.py`: `main(argv)` per spec — args `<program> <seed>`; reads
  `./replay.json`; seed guard (exit 3), attempts cap via `replays/attempts.json`
  (exit 4), engine rebuild from recipe wrapped in `AuditedEngine`, execute single seed,
  write `replays/seed<N>_attempt<K>/{trace.json,summary.txt}` (+media copies re-using
  task_context helpers where sensible), print `score: X` + summary, exit 0; usage
  errors exit 2; EngineError → stderr + exit 5.
- Tests `tests/aspire/test_replay.py`: guard/cap/artifacts/stdout/attempt-persistence/
  recipe round-trip; all with fake recipes.

### Unit R2 — coordinator materialization + actor permission + prompt
- `aspire/coordinator.py`: `_materialize_replay()` writes `./replay` shim (chmod +x),
  `replay.json` from `self.engine.describe()` (out_root overridden to
  `<task>/replays/engine` for capx recipes), resets `replays/attempts.json`; called
  before EACH `actor.run_debug`.
- `aspire/actors.py`: `run_debug` adds `--allowedTools "Bash(./replay:*)"` (flag value
  a module constant so the on-box syntax fix, if needed, is one line). Shim test pins
  the flag in CLI args.
- `prompts/actor_debug.md`: replace the "no replay path" note with usage + cap +
  artifacts; lint test updated (must mention `./replay`, the cap, and that validation
  seeds are rejected).
- Coordinator test: after a run, shim+recipe exist in task dir, attempts.json reset
  between rounds (multi-round test), recipe engine type matches the pipeline engine.

### Unit R3 — on-box live smoke (ops, after R1/R2 review)
- rsync; on simhost run one real replay by hand in the M3 handover task dir (debug seed,
  the winning program) via the shim path; confirm exit 0, artifacts, sane score; then
  one full mini pipeline (broken-baseline stack task, fresh dir) to watch a real actor
  USE the affordance; verify report.seed_attempts populated. Verify/adjust the
  allowedTools syntax live.

Review: combined spec+quality (opus) after R1+R2; findings fix-first as usual.


## R3 outcome (2026-07-16) — DONE
Live smoke + real-actor e2e both passed (runs/2026-07-16-replay-affordance-e2e/).
Live findings fixed en route: shim PYTHONPATH trailing-colon dual-import (the review's
"harmless" residual proved catastrophic); seed_attempts shape mismatch (the G2-predicted
reader crash) — normalizer + arity guard + prompt example. allowedTools grant verified;
OS sandbox permits PYTHONPATH reads (no vendoring needed). First-ever actor run with
outcome "success", replay-validated on all three seeds, and no BLOCKED.md.
