# Cross-campaign re-analysis on held-out validation (2026-07-26)

Reproduce: `python3 scripts/reanalyze_val.py` (pure; reads existing per-cell
`summary.json`, no new runs).

## Why
Every campaign scored **"solved" = `dbg_score`** (the *debug seed* got solved).
ASPIRE's accumulation claim is about **generalization**. This re-scores every
existing campaign on **held-out validation** (`val_score >= 0.5`) — the metric we
should have been reading — to see whether the signal was masked.

## Per-campaign: dbg vs VAL, and the overfit gap (dbg-rate minus val-rate)

| campaign | arm | dbg | VAL | overfit gap |
|---|---|---|---|---|
| C1 spatial | cold | 0.50 | 0.00 | +3 |
| | warm | 0.75 | 0.25 | +2 |
| C2 frontier t=5 | cold | 0.80 | 0.20 | +6 |
| | warm | 0.90 | **0.70** | +2 |
| C2b frontier t=2 | cold | 0.80 | 0.50 | +3 |
| | warm | 0.70 | 0.60 | +1 |
| C3 tiling t=2 | cold | 0.93 | 0.40 | +8 |
| | warm_dumpall | 0.80 | 0.60 | +3 |
| | warm_geo | 0.93 | 0.33 | +9 |
| C4 libero_10 | cold | 0.38 | 0.11 | +10 |
| | warm_dumpall | 0.33 | 0.27 | +2 |
| | warm_geo | 0.10 | 0.00 | +1 |

Matched warm-vs-cold on VAL, per campaign: C2 frontier **p=0.070** (was a *null*
on dbg!), C4 libero_10 warm_dumpall **p=0.080** (middle-tasks-only pool p=0.020),
C2b p=1.0, C3 warm_dumpall p=0.47, C1 p=1.0.

## Cross-campaign pooled (primary library arms vs cold, VAL)

- **library 31/69 (0.45) vs cold 15/69 (0.22), Fisher p = 0.0064.**
- **Cold overfits the debug seed MORE than the library in 5/5 campaigns** (sign-test
  p = 0.0625).

## Reading
The reproduction signal was **hiding behind the metric.** Scored on debug-solve, the
series looked like a string of nulls. Scored on held-out generalization, the library
arm consistently overfits less than cold and generalizes ~2x better pooled. The
clearest single case is C2 (the original "frontier null"): warm val 7/10 vs cold 2/10
— cold solves the debug seed and fails to generalize; the library carries over.

## Honest caveats (this is a lead, not a closed result)
1. **Post-hoc.** `val` was not the pre-registered metric; this is exploratory
   re-scoring. The pooled p=0.0064 is subject to metric-selection risk.
2. **Pooled Fisher is optimistic** — it treats 69 reps as independent, but reps share
   tasks and campaigns differ (heterogeneous pool). The conservative statement is the
   **5/5 sign test (p=0.06)**, which is only borderline.
3. **warm_geo excluded** from the pool (bowl-anchor-limited; only testable on bowl
   scenes) — a defensible but explicit choice.

## Implication for next step
This turns the confirmatory run from "maybe" into "worth it, and now well-specified":
pre-register **`val_score`** as the primary metric, on the tasks with the most
overfitting headroom (C2/C4-style: cold high-dbg, low-val), N>=10, arms warm vs cold
(warm_dumpall as the library arm). If it holds pre-registered, that is a clean ASPIRE
reproduction: *accumulation improves held-out generalization.*
