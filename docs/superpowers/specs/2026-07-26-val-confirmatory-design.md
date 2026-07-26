# Val-Pre-Registered Confirmatory Campaign

**Date:** 2026-07-26
**Status:** design approved, ready for planning
**Predecessor evidence:** `runs/VAL-REANALYSIS.md` + `scripts/reanalyze_val.py`
(the post-hoc finding this campaign confirms).

## North Star alignment

Single priority: reproduce ASPIRE's skill-accumulation claim, sim-first. The
cross-campaign re-analysis found that the accumulation benefit was **masked by the
scoring metric**: every prior campaign scored debug-seed solving (`dbg_score`), but on
**held-out validation** (`val_score`) the library arm generalizes far better than cold
(cold overfits the debug seed in 5/5 campaigns; pooled val library 0.45 vs cold 0.22,
Fisher p=0.006; the original frontier "null" was warm val 7/10 vs cold 2/10, p=0.070).
That finding is **post-hoc**. This campaign turns it into a **clean, pre-registered**
reproduction: val is the primary metric, and the task set, selection rule, N, and
decision rule are frozen before any test run.

## Pre-registration (frozen before the first TEST run)

The pre-registration is committed to git as `runs/2026-07-26-val-confirmatory/
PREREGISTRATION.md` and its commit hash recorded **before** any warm-vs-cold test run
executes. It fixes everything below. Nothing here may change after test runs begin;
any deviation is reported as a deviation, not a silent edit.

- **Primary metric:** `val_score` measured over **5 held-out validation seeds
  (`--s-val 200-204`)**, debug seed `--s-dbg 0`. Seeds 200-204 were not used by any
  prior campaign (which used seed 100), so the validation evidence is fresh.
- **Per-run outcome:** **val-solved = `val_score >= 0.5`** (solved ≥3 of 5 val seeds).
- **Arms:** `warm` (the library arm — dump-all retrieval over the frozen tiled
  library) vs `cold` (empty library). The bowl-anchor-limited `warm_geo` arm is
  **dropped** (it cannot run on non-bowl scenes).
- **Library:** the existing frozen tiled library
  `~/aspire_runs/libero_tiling/tiled_library` (8 strategy skills, 3 bowl locations),
  copied per warm rep. No re-accumulation.
- **Test budget:** `--t 2`. (Cold overfits the debug seed hardest at t=2 — the largest
  dbg→val gaps in the re-analysis were the t=2 campaigns C3/C4 — so t=2 maximizes the
  headroom the effect needs.)
- **N:** 10 reps per arm per selected task.
- **Primary decision rule — H1 (ASPIRE reproduced):** pooled over the selected tasks,
  warm val-solved rate > cold val-solved rate **AND** Fisher-exact p < **0.05**
  (stricter than the exploratory 0.10 because this is confirmatory). Otherwise **H0**.
- **Secondary (reported, not decisive):** continuous mean `val_score` per arm with a
  Mann-Whitney U test; and the `dbg_score` contrast (expected warm ≈ cold or cold
  higher — the overfitting signature).

## Task-selection rule (frozen, applied BEFORE the test)

The rule is mechanistic (selects for the overfitting the hypothesis is about), not
hand-picked, and it spans tasks the exploratory analysis never touched.

- **Candidate pool:** held-out spatial `{3,6,8}` (not used to build the library) + all
  libero_10 `{0,1,2,3,4,5,6,7,8,9}`. Of these, libero_10 `{1,2,4,5,7,8,9}` were
  **never** tested warm-vs-cold in any prior campaign — genuinely fresh.
- **Per-candidate cold statistics:** cold **dbg-rate** and cold **val-rate** at t=2.
  Reuse existing cold data where it exists at t=2 (spatial `{3,6,8}` from C3; libero_10
  `{0,3,6}` from C4); **probe fresh** the 7 remaining libero_10 tasks with 5 cold reps
  each (t=2, s-val 200-204).
- **Selection (the overfit band):** keep a task iff **cold dbg-rate ≥ 0.6 AND cold
  val-rate ≤ 0.2**. This selects tasks where cold reliably solves the debug seed but
  reliably fails to generalize — exactly where a library that generalizes can show a
  val gap, and where floor tasks (cold can't solve at all) and ceiling tasks (cold
  generalizes fine) are both excluded.
- **Selection guard:** if fewer than 2 tasks pass, stop and report "no overfit-band
  tasks exist at this budget" — an honest null of the selection step, not a fallback to
  hand-picked tasks.
- The selected task list is written to `selected_tasks.json` and frozen before the
  test phase.

**Known limitation of reuse (stated, not hidden):** reused cold data (spatial `{3,6,8}`,
libero_10 `{0,3,6}`) measured val on the prior single seed (100), while freshly probed
tasks use 5 seeds (200-204). The dbg-rate is comparable (debug seed 0 throughout); the
val-rate estimates differ slightly in seed protocol. This affects only the *coarse
selection filter* (which tasks enter the test), not the confirmatory test itself — the
TEST re-measures val on the fresh 200-204 seeds for BOTH arms, so the pre-registered
evidence is clean regardless of selection-input noise. The Thorough tier removes this by
re-probing every candidate on 200-204; Standard accepts it as a documented pre-filter
approximation.

## Campaign structure

Reuses the existing infrastructure. `.venv-libero` (robosuite 1.4.0), `MUJOCO_GL=egl`,
subscription billing (`env -u ANTHROPIC_API_KEY`), idempotent DONE markers, atomic
`.claim` files for parallel safety.

- **Phase 0 — preflight + pre-registration freeze.** Assert robosuite 1.4; assert the
  tiled library exists with ≥2 skills; commit `PREREGISTRATION.md` and record its hash
  in the run log. (No test run may precede this commit.)
- **Phase 1 — cold probe + select.** Gather cold dbg/val rates over the candidate pool
  (reuse + probe fresh), apply the frozen overfit-band rule, write `selected_tasks.json`
  and a `selection.md` audit (each candidate's cold dbg/val rate and keep/drop). Gate:
  ≥2 selected or stop.
- **Phase 2 — confirmatory test.** warm vs cold, N=10, t=2, `--s-val 200-204`, on the
  selected tasks. warm copies the frozen tiled library per rep; cold uses an empty
  library per rep.
- **Phase 3 — analyze (primary = val).** Run the analyzer with `--metric val` for the
  pre-registered verdict; also emit the dbg and continuous-val secondaries.

Config knobs: `POOL_SPATIAL=(3 6 8)`, `POOL_LIBERO10=(0..9)`, `PROBE_REPS=5`,
`TEST_REPS=10`, `TEST_T=2`, `VAL_SEEDS=200-204`, `DBG_SEED=0`,
`OVERFIT_DBG_MIN=0.6`, `OVERFIT_VAL_MAX=0.2`.

## Deliverables

- **`scripts/analyze_libero_tiling.py`** — add `--metric {dbg,val}` (default `dbg` for
  back-compat). `val` scores a cell as solved when `val_score >= 0.5`; the report and
  verdict use whichever metric is chosen. Because this campaign runs only
  `warm_dumpall` + `cold` (no `warm_geo`), the **primary pre-registered contrast is
  `warm_dumpall` vs `cold`** — the analyzer must report that pair's Fisher p as the
  headline (not the `warm_geo`-vs-cold `B_vs_C` slot, which is empty here) and must not
  emit a spurious verdict from a 0/0 arm. Small, unit-tested change; the stock dbg path
  is unchanged.
- **`scripts/val_confirmatory_select.py`** — pure selection: given per-candidate cold
  dbg-rate/val-rate (from reused summaries + fresh probe outputs), apply the frozen rule
  and emit the selected list + audit. Unit-tested against synthetic rates.
- **`scripts/val_confirmatory_campaign.sh`** — the runner (Phases 0-3): preflight +
  prereg freeze, cold probe of fresh tasks, selection, warm-vs-cold test via
  `libero_tiling_parallel.py` (`--arms warm_dumpall,cold --reps 10 --s-val 200-204
  --t 2`), then the `--metric val` analysis. `DRY=1`-safe, idempotent.
- **`runs/2026-07-26-val-confirmatory/`** — `PREREGISTRATION.md` (committed pre-run),
  config snapshot; after execution `selected_tasks.json`, `selection.md`,
  `results.json`, `FINDINGS.md`.
- **Tests:** `--metric val` analyzer behavior; selection-rule band (keeps overfit-band,
  drops floor/ceiling, signals insufficient when <2); runner dry-run.

## Testing

Pure pieces unit-tested; the runner is a committed script executed once under the
autonomous loop, exercised via `DRY=1`.

1. **Analyzer `--metric val`** — synthetic run dirs with distinct `dbg_score` and
   `val_score`; `--metric val` scores solved on `val_score >= 0.5`, `--metric dbg`
   unchanged; per-arm rates and Fisher p reflect the chosen metric.
2. **Selection rule** — synthetic candidate cold rates: keeps a task with dbg 0.8 /
   val 0.1 (overfit band), drops dbg 0.3 (floor) and dbg 0.9 / val 0.6 (ceiling),
   returns "insufficient" when <2 qualify.
3. **Runner dry-run** — `DRY=1` lists Phases 0-3, `.venv-libero`, `env -u
   ANTHROPIC_API_KEY`, `--t 2`, `--s-val 200-204`, arms `warm_dumpall`/`cold`, the
   candidate pool, and the prereg-freeze-before-test ordering.

Full suite green (`python3 -m pytest tests/ -q -p no:anyio`).

## Constraints (verbatim, bind every task)

- `.venv-libero` python = `/home/demo/cap-x/.venv-libero/bin/python`; robosuite 1.4.x
  (Phase 0 asserts). Never the main `.venv` for LIBERO.
- `aspire/` is not modified (val_score is already produced; only scripts change).
- Billing: every aspire.run invocation strips `ANTHROPIC_API_KEY` (subscription).
- Primary metric = `val_score`, val-solved threshold 0.5, val seeds `200-204`, debug
  seed `0`, test budget `t=2`, N=10, arms warm_dumpall vs cold.
- Overfit band: cold dbg-rate ≥ 0.6 AND cold val-rate ≤ 0.2; ≥2 selected or stop.
- Decision: H1 iff warm val-rate > cold val-rate AND Fisher p < 0.05; else H0.
- `PREREGISTRATION.md` committed and its hash logged BEFORE any test run.
- `MUJOCO_GL=egl`; idempotent DONE markers; `DRY=1`-safe.
