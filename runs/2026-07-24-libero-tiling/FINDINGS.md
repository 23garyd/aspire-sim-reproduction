# LIBERO tiling-curriculum + retrieval-discrimination — findings

Spec: `docs/superpowers/specs/2026-07-24-libero-tiling-curriculum-design.md`.
Plan: `docs/superpowers/plans/2026-07-24-libero-tiling-curriculum.md`.
Loop ledger: `AUTOLOOP.md`. Raw: `results.json`.

## Setup (all preconditions met, unlike prior campaigns)
- **Tiled library built:** Phase-1 accumulate over `{0,1,2,4,5,7,9}` banked **8 strategy
  skills from 3 distinct bowl locations** (spatial_1 @0.476,0.317; spatial_7
  @0.394,-0.145; spatial_9 @0.688,-0.282). Tile gate passed.
- **Geometry retrieval verified working end-to-end:** for held-out spatial_3 (bowl
  @0.717,0.024), warm_geo injected exactly the single nearest-location skill
  (@0.688,-0.282); warm_dumpall injected all 8. The arms are genuinely different.
- **Three arms, N=5/arm/task, held-out {3,6,8}, test budget t=2.**

## Result: H0 null on all pairs

| arm | success (pooled 15) | attempts-to-solve |
|-----|---------------------|-------------------|
| warm_geo (geometry retrieval) | 14/15 = **0.93** | 2.21 |
| warm_dumpall (stock dump-all) | 12/15 = **0.80** | 2.83 |
| cold (empty)                  | 14/15 = **0.93** | 2.21 |

Pairwise Fisher-exact: **p(B,C)=1.0000, p(B,A)=0.598, p(A,C)=0.598** — no pair
separates at p<0.10.

Per task (warm_geo / warm_dumpall / cold):
- spatial_3: 5/5 · 3/5 · 5/5   (dump-all hurt)
- spatial_6: 5/5 · 4/5 · 5/5   (dump-all slightly hurt; geo FIXED the frontier
  campaign's spatial_6 negative transfer, where warm was 2/5)
- spatial_8: 4/5 · 5/5 · 4/5   (dump-all best here — the pattern reverses)

## Interpretation

1. **Coverage hypothesis NOT reproduced.** warm_geo (0.93) exactly equals cold (0.93)
   on both success and attempts-to-solve. A tiled library with correct nearest-location
   retrieval does **not** beat cold — because cold already solves these tasks at t=2.
   This is the same solvability-ceiling that produced nulls in every prior campaign:
   whenever the test budget lets cold succeed, banked skills have no room to add a
   *solvability* gain.

2. **Retrieval hypothesis: directional, not significant.** warm_geo (0.93) > warm_dumpall
   (0.80), p=0.60. The consistent thread across tasks: geometry retrieval sits AT cold's
   level (never below), while dump-all dips below it. So the value of good retrieval is
   **avoiding negative transfer, not exceeding cold.** On spatial_3/6 dump-all clearly
   hurt and geometry avoided it; on spatial_8 the ordering reversed — net null at N=5.

3. **The one qualitative win:** geometry retrieval cleanly *repaired* the spatial_6
   negative transfer that the frontier campaign flagged (warm 2/5 → warm_geo 5/5). That
   mechanism is real; it just doesn't translate into a pooled success gain because cold
   is not failing enough to leave headroom.

## Where this leaves the four-campaign arc

Across all four campaigns the finding is stable and, taken together, informative:
- **Premise reproduced:** the pipeline banks genuine reusable manipulation strategy
  (not plumbing), and with location-aware retrieval it applies the right skill.
- **Solvability gain NOT reproduced** on LIBERO-spatial: at any budget where the
  experiment is well-posed, cold already solves the tasks, so accumulation cannot
  change *whether* they solve. Accumulation's measurable effects are **convergence
  speed** (frontier campaign) and **negative-transfer avoidance via good retrieval**
  (this campaign) — both real, neither large enough to clear significance at N=5.
- **The binding constraint is the task family, not the method.** To show a solvability
  gain you need held-out tasks that cold genuinely CANNOT solve at the test budget but
  a banked skill can unlock. LIBERO-spatial at t=2 doesn't provide that. The honest next
  step is a harder task distribution (e.g. libero_10 / longer-horizon tasks) where cold's
  success rate is well below ceiling — not more N on this family.
