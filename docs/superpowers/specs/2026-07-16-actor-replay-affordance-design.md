# Actor Replay Affordance — Design

**Date:** 2026-07-16 · **Status:** approved (user, this date)
**Origin:** both live actors filed BLOCKED.md — App E's inner loop (per-seed fix.py
replay, ≤3 attempts/seed) has no execution path from inside the actor sandbox. The
first actor's BLOCKED.md is the requirements doc: the affordance must live INSIDE the
task dir; without it, repairs are "diagnosis-driven, not validated".

**Scope (user-selected):** Stage-1 debug actors only; budget = 3 attempts per debug
seed per actor session (the paper's cap). Evosearch proposers do NOT get replays.

## Approach (A, approved)

Coordinator materializes into the task dir (alongside task.md/skills.md):
- `./replay` — executable shim: `exec python3 -m aspire.replay "$@"` (cwd = task dir).
- `replay.json` — engine recipe + policy:
  `{"engine": {"type": "capx", "cmd_prefix": [...], "out_root": "<task>/replays/engine"}
    | {"type": "fake", "scores": [...]},
    "s_dbg": [0,1,2], "max_attempts_per_seed": 3}`

New module `aspire/replay.py`, CLI `<program> <seed>`:
1. **Seed guard first**: seed ∉ recipe's s_dbg → refuse (exit 3). The module never
   learns S_val — validation seeds are structurally unreachable, not merely forbidden.
2. **Budget**: `replays/attempts.json` per-seed counter; at cap → refusal message
   naming the cap (exit 4), no execution. Counter reset by the coordinator per round.
3. **Audit wall intact**: execution always wrapped in `AuditedEngine` — a cheating fix
   is rejected with score 0.0 exactly as in the main pipeline.
4. **Artifacts + inline feedback**: writes `replays/seed<N>_attempt<K>/`
   (trace.json, summary.txt, media/), prints score + trace summary to stdout.
   Replay engine executions live under `replays/engine/` (own exec_NNNN namespace,
   never interleaved with the coordinator's out_root).

Engine change: `FakeEngine`/`CapxEngine` gain `describe() -> dict` (recipe above);
`AuditedEngine.describe()` delegates to inner (replay re-wraps with audit itself).

Coordinator: `materialize_replay(task_dir)` writes shim + recipe and resets
`replays/attempts.json`, called before each `actor.run_debug`. Existing seed-attempt
discipline check stays as the out-of-band backstop (the tool makes in-band over-cap
impossible; self-reported out-of-band attempts still auditable).

Actor wiring: `ClaudeCodeActor.run_debug` passes a narrowly-scoped
`--allowedTools "Bash(./replay:*)"` (exact syntax verified on-box — the one
integration risk; `acceptEdits` does not grant Bash execution).

Prompt: `prompts/actor_debug.md` — replace the "no replay path" M2-wiring note with
the affordance description: usage, the 3/seed cap, validation-seeds-rejected, artifact
locations; per-seed replay results feed `seed_attempts` in report.json (now real data).

## Rejected alternatives
- Coordinator-side replay loop (multi-turn actors): large architectural surgery.
- Raw engine command to actors: bypasses audit/budget/S_val protections; sandbox
  blocks the needed paths anyway.

## Budget math
Worst case 3 seeds × 3 attempts × 2 rounds = 18 sim episodes/task, no LLM cost.

## Error surface
exit 0 = replay ran (score is data); exit 2 usage; exit 3 seed guard; exit 4 cap.
Engine failures surface as the wrapped EngineError text on stderr, exit 5; partial
artifacts are overwritten on the next attempt to the same slot.

## Testing
Fake-testable end-to-end: seed guard, cap + persistence, artifacts + stdout, recipe
round-trip (describe→json→rebuild), coordinator materialization + per-round reset,
allowedTools flag pin, prompt lint. Live smoke on simhost afterward (one replay against
the real engine on a debug seed).
