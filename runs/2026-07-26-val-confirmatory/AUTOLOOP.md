# Autonomous loop ledger — val-pre-registered confirmatory campaign

Spec: docs/superpowers/specs/2026-07-26-val-confirmatory-design.md
Plan: docs/superpowers/plans/2026-07-26-val-confirmatory.md

## Acceptance (terminal)
PRE-REGISTERED: H1 (ASPIRE reproduced) iff warm_dumpall val-rate > cold val-rate AND
Fisher p < 0.05 on the selected overfit-band tasks. Else H0. Either is a valid terminal
result. Selection gate: >=2 overfit-band tasks or stop (honest null of selection).

## Guardrails
- Auto-decide: recommended/first option; log; never block.
- PREREGISTRATION.md committed + hash logged BEFORE any test run (Phase 0).
- Subscription billing (env -u ANTHROPIC_API_KEY). WATCH rate-limit stalls: if the
  parallel runner's claude -p calls start failing, drop --jobs 4 -> 1-2 or fall back to API.
- Hard cap: stop if cumulative t-equiv runs > 150.
- Commit results.json + FINDINGS.md at terminal (+ continuous-val Mann-Whitney secondary
  from raw per-cell val_score).
- Ping user ONLY at terminal with ACTUAL val Fisher p.

## State machine
STATE: FINISHING (resume b9yhk5rly, ASPIRE_USE_API=1 JOBS=2). Was BLOCKED on subscription rate-limit (fixed via API);
then API run exited INCOMPLETE at 50/60: 10_2 reps 6-10 failed at STARTUP (empty logs) due to ~10 LEAKED
_start_api_servers holders causing port conflicts (NOT rate limit, NOT planner — 233G mem free). Killed all holders,
cleared stale claims + partial 10_2 cells, resuming the final 10 cells clean.
PARTIAL pooled (50/60): warm_dumpall 9/25 (0.36) vs cold 3/25 (0.12), Fisher p=0.0955 (just misses pre-reg 0.05) — NOT FINAL (10_2 truncated). Resume bx13hvb9s exhausted all 8 cooldown-retries on BOTH suites; a duplicate runner (420169, not launched by me) + ~20 leaked api-server holders were killed/cleaned. Single claude -p works (SUBOK) but sustained/concurrent load trips the Max rolling cap. AWAITING USER billing decision: wait-and-resume-on-subscription (free/slow) vs API-fallback (costs) vs jobs=1. Loop STOPPED. Partial data preserved (idempotent).
NEXT: on completion -> pre-registered val decision (pooled 3 tasks, p<0.05) -> FINDINGS + commit -> PING. Resume progress base: spatial_6 warm_dumpall 6/10 (3 val) cold 5/10 (1 val); 10_0/10_2 warm not started. API not subscription-rate-capped; jobs=4.

## Decision log
- 2026-07-26: val primary (seeds 200-204), overfit-band selection on broad pool
  (incl. fresh libero_10 1,2,4,5,7,8,9), warm_dumpall vs cold N=10 t=2, p<0.05. Armed.

## Attempt log
- launched 2026-07-26; PREREG frozen at 025ebce (before any test run); root=~/aspire_runs/libero_val_confirm
- STALL 1: first run (bldbckodd) tripped the parallel circuit breaker (3 consecutive planner-fails,
  subscription rate-limit burst at --jobs 4) mid-Phase-2; partial analysis in campaign.log is INVALID.
  Subscription verified healthy (transient). FIX: --jobs 4->2 + cooldown-retry on rc=3. Cleaned orphaned
  holders. Selection was already valid (gate passed): spatial_6, 10_0, 10_2. RESUMED as bash bx13hvb9s.
