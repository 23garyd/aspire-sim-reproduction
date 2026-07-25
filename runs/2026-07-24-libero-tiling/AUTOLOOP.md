# Autonomous loop ledger — LIBERO tiling-curriculum campaign

Spec: docs/superpowers/specs/2026-07-24-libero-tiling-curriculum-design.md
Plan: docs/superpowers/plans/2026-07-24-libero-tiling-curriculum.md

## Acceptance (terminal SUCCESS)
Either pre-registered H1 clears:
- H1-COVERAGE: warm_geo > cold AND Fisher p(B,C) < 0.10.
- H1-RETRIEVAL: warm_geo > warm_dumpall AND Fisher p(B,A) < 0.10.
Else H0 null = also a valid terminal result (report the pairwise p + attempts-to-solve).

## Guardrails
- Auto-decide: any choice -> recommended/first option; log; never block.
- Single campaign (3 arms, N=5, 3 held-out tasks, ~53 runs at t=2). If Phase-1 tile
  gate trips (<2 tagged skills from <2 locations) -> widen ACCUM_TASKS once, relaunch.
- Hard cap: stop if cumulative t-equiv runs > 120.
- Commit results.json + FINDINGS.md at terminal.
- Ping user ONLY at terminal state with ACTUAL pairwise Fisher p.

## State machine
STATE: BUILD (subagent implementing 6-task plan; TDD; commit)
NEXT: on build done+green -> pre-launch checks (proxy :8110, robosuite 1.4,
      capx_bowl_xy.py live smoke) -> launch scripts/libero_tiling.sh in background

## Decision log
- 2026-07-24: 3-arm design (warm_geo/warm_dumpall/cold), Standard tier (3 held-out
  x N=5), test t=2, geometry retrieval added to aspire (contained). Loop armed.

## Attempt log
(empty)
