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
STATE: DONE (terminal). 45/45. H0 null all pairs: warm_geo 0.93 == cold 0.93 (p=1.0), warm_dumpall 0.80 (p(B,A)=0.60). Geometry retrieval avoids neg-transfer (=cold), doesn't beat cold (t=2 ceiling). Loop stopped.

## Decision log
- 2026-07-24: 3-arm design (warm_geo/warm_dumpall/cold), Standard tier (3 held-out
  x N=5), test t=2, geometry retrieval added to aspire (contained). Loop armed.

## Attempt log
- launched 2026-07-24; 3 arms x N=5 x heldout {3,6,8}, t=2; tiled lib from ACCUM {0,1,2,4,5,7,9}; root=~/aspire_runs/libero_tiling
- BUG CAUGHT+FIXED before wasting runs: bowl_xy captured LIBERO import banners (tagged skills 'Robosuite not installed!'),
  which would make source_xy unparseable -> geometry retrieval falls back to stock -> Arm B == Arm A (experiment ruined).
  Fix (committed): bowl_xy pipes probe through tail -1 + validates num,num, aborts otherwise. Root nuked, relaunched clean.
- relaunched as bash ba6et70xi with fixed runner.
- Phase 1 DONE: tile gate PASSED — 8 tagged skills from 3 DISTINCT locations
  (spatial_1 @0.47648,0.31660 adm3; spatial_7 @0.39434,-0.14527 adm2; spatial_9 @0.68843,-0.28180 adm3).
  spatial_0/2/4/5 adm0. Library genuinely tiles -> coverage/retrieval hypotheses are testable.
- Phase 3 DONE (45/45): warm_geo 14/15 (0.93), warm_dumpall 12/15 (0.80), cold 14/15 (0.93).
  Fisher p(B,C)=1.0, p(B,A)=0.60, p(A,C)=0.60 -> H0 null all pairs. geo==cold (avoids neg-transfer,
  no coverage gain); dumpall<cold (mild neg-transfer). geo FIXED frontier spatial_6 neg-transfer (2/5->5/5).
  Binding constraint = task family (cold solves at t=2); next = harder distribution (libero_10). See FINDINGS.md.
- ANOMALY (2026-07-25 ~10:37): my sequential task ba6et70xi died (exit 144); an UNTRACKED parallel
  runner scripts/libero_tiling_parallel.py (--jobs 6, NOT created by me — appeared in shared env) took over.
  INTEGRITY VERIFIED: it faithfully mirrors run_one (sets ASPIRE_RETRIEVAL=geometry+TARGET_XY only for warm_geo,
  atomic .claim + DONE, same cmd). Empirical proof: warm_geo spatial_3/1 skills.md injected EXACTLY the nearest
  tagged skill (0.68843,-0.28180, nearest to bowl 0.71673,0.02439); warm_dumpall injected ALL skills. Arms are
  genuinely differentiated -> results valid. Letting it finish; I will run my own analyzer + commit + ping.
