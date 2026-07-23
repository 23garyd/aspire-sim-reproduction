# Autonomous loop ledger — LIBERO skill-accumulation frontier campaign

Spec: docs/superpowers/specs/2026-07-22-libero-accum-frontier-design.md

## Acceptance (terminates loop as SUCCESS)
H1: warm > cold matched held-out success on frontier tasks AND Fisher-exact p < 0.10.

## Guardrails
- Auto-decide: any choice -> recommended/first option; log below; never block.
- Max 3 campaign attempts. Null -> ONE change, in order:
  (1) fix the specific phase-gate blocker that tripped (no place-skill banked / no frontier band);
  (2) bump N 5 -> 8 per arm (power);
  (3) widen CALIB_SHORTLIST / soften frontier band.
  After attempt 3: STOP, write consolidated honest null (acceptable terminal result).
- Hard credit cap: stop if cumulative t=5-equivalent runs > 100.
- Commit results.json + FINDINGS.md every attempt.
- Ping user ONLY at terminal state.

## State machine
STATE: RUNNING attempt 1 (build committed d25ff80, 325 tests green)
NEXT: on completion -> analyze -> check H1

## Decision log
- 2026-07-22: adopted Standard tier (2 frontier tasks, N=5/arm), deeper baseline +
  frontier selection, per approved spec. Loop armed.

## Attempt log
- attempt 1: launched 2026-07-22; deeper baseline + frontier, N=5/arm; root=~/aspire_runs/libero_accum_v2
  - Phase 1: spatial_0/1 FAILED (dbg 0.0), spatial_2 SOLVED (dbg 1.0 val 1.0 adm 2). GATE PASS.
  - banked STRATEGY skills (not plumbing!): grasping/rim-grasp-wide-vessel,
    placement/compensate-offset-grasp-at-place. Premise validated.
  - Phase 2A: frontier tasks SELECTED = spatial_8 (1/2), spatial_6 (1/2) — knife's-edge.
  - now in Phase 2B: warm vs cold, 5 reps/arm at t=5 (20 test runs).
