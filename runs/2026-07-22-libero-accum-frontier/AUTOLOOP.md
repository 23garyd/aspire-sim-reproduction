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
STATE: BUILD  (build deliverables via subagent -> tests green -> commit)
NEXT: launch campaign attempt 1

## Decision log
- 2026-07-22: adopted Standard tier (2 frontier tasks, N=5/arm), deeper baseline +
  frontier selection, per approved spec. Loop armed.

## Attempt log
(empty)
