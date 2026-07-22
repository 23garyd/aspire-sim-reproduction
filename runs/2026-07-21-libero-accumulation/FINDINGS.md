# LIBERO skill-accumulation campaign — findings (2026-07-22)

Warm (shared accumulated library) vs cold (empty per task) on libero_spatial,
privileged mode, `.venv-libero` (robosuite 1.4.0). Spec:
`docs/superpowers/specs/2026-07-21-libero-skill-accumulation-design.md`.

## What ran
- **Phase 1 (accumulate):** curriculum task_ids 2,1,0 into one shared library →
  **2 skills banked** (`api-contract-dtype-safety`, `engine-quirk-motion`).
- **Phase 2a (cold calibration, --t 5):** shortlist {8,6,5,3,9,7} → **spatial_5 and
  spatial_3** solvable cold; spatial_6, spatial_8 not solvable (dropped). 9,7 never
  reached (2 picked first).
- **Phase 2b (warm vs cold, 2 repeats/arm, --t 5):** on the 2 selected tasks.

## Honest verdict: NULL on success, weak-positive on speed
The runner's auto-verdict ("H1 suggestive, 0.75 vs 0.50") is **overstated** — its
cold arm pools spatial_6/spatial_8 (calibration rejects that warm never ran on).
Matched on the SAME two test tasks:

| arm  | success (matched) | attempts-to-solve (solved runs) |
|------|-------------------|---------------------------------|
| warm | 3/4 = 0.75        | {2, 2, 2}  mean 2.0             |
| cold | 3/4 = 0.75        | {11, 2, 3} mean 5.3            |

- **Success rate: a wash** (0.75 = 0.75). Accumulated skills did NOT change whether
  a held-out task gets solved.
- **Attempts-to-solve: weak positive.** Warm solved in 2 attempts every time; cold
  needed up to 11 on first exposure. Suggestive of a mild transfer benefit on
  *speed*, but N=4/arm, high variance (one warm run failed outright), largely driven
  by a single cold run (spatial_3 cold/1 = 11). Not conclusive.
- **Nothing compounded:** across the whole campaign, exactly ONE run admitted a new
  skill AND passed held-out validation (spatial_5 warm/1). Banked count stayed 2.
  Consistent with the concern that the 2 skills are "plumbing" (dtype/motion
  quirks), not manipulation strategy.

## Known confound in the analysis script
`analyze_libero_accumulation.py` pools ALL cold runs (incl. unselected calibration
probes) into the cold arm, inflating the warm-vs-cold gap. The matched table above
is the fair comparison. Raw per-run data in `results.json`.

## Takeaway for the reproduction goal
This is an honest, pre-registered outcome (a null on the headline metric counts, as
with the prior Robosuite ablations). ASPIRE's distinctive skill-accumulation claim
is **not yet reproduced as a solvability benefit** — the mild attempts-to-solve edge
is the only signal, and it's within noise at this N. Likely blockers: skills banked
are low-level plumbing, and Lean N is too small to separate a real effect from
LIBERO's high run-to-run variance.
