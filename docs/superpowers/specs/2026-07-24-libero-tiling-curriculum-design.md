# ASPIRE Skill-Accumulation: Tiling Curriculum + Retrieval Discrimination

**Date:** 2026-07-24
**Status:** design approved, ready for planning
**Predecessors:**
- `docs/superpowers/specs/2026-07-22-libero-accum-frontier-design.md` (frontier campaign)
- `runs/2026-07-22-libero-accum-frontier/FINDINGS.md` (the two nulls + negative-transfer result)

## North Star alignment

Single priority: **reproduce ASPIRE's skill-accumulation claim** — banked skills
measurably help later held-out tasks. The frontier campaign showed accumulation
reproduces as a *convergence-speed* effect but not a *solvability* gain, and that
transfer is **task-dependent and can be negative** (a skill banked from one bowl
location hurts a mismatching test task). This campaign tests the two hypotheses that
result implicates, in one experiment.

## What the prior result established (the two hypotheses)

1. **Coverage hypothesis.** Negative transfer happened because the library held one
   location-specific grasp skill (from spatial_2) and no skill for the mismatching
   test location (spatial_6). A library that *tiles* the location distribution —
   holding a skill near every held-out location — might convert negative transfer to
   positive and yield a solvability gain.
2. **Retrieval hypothesis.** The bottleneck may be *retrieval*, not coverage.
   `relevant_skills` (`aspire/task_context.py:65`) extracts keywords from error
   traces, does a coarse substring match, and **falls back to `load_all()` (inject
   everything, cap 10) when there are no error-keywords or no keyword hits.** With a
   small library every skill is always injected; with a tiled library it would flood
   the proposer with mostly geometrically-wrong skills. Under this retrieval, tiling
   could *amplify* negative transfer. If instead retrieval injected the single
   nearest-location skill, the tiled library could help.

These are confounded in a naive tiling test. This campaign separates them with a
three-arm design.

## Design: three arms over a tiled library

Build one **tiled** accumulated library by accumulating across many libero_spatial
locations, then test held-out tasks under three retrieval/library regimes:

- **Arm A — warm-dumpall:** tiled library + the current `relevant_skills` retrieval
  (dump-all/coarse). Tests the coverage hypothesis under stock retrieval.
- **Arm B — warm-geometry:** tiled library + geometry-aware retrieval that injects
  the single skill whose source bowl location is nearest the test task's bowl
  location. Tests the coverage hypothesis under discriminating retrieval.
- **Arm C — cold:** empty library (baseline). The reference both warm arms are
  measured against.

The contrast **B vs A** isolates the *retrieval* effect (same library, different
retrieval). The contrast **B vs C** is the headline reproduction test (does a tiled
library with good retrieval beat cold on solvability). **A vs C** measures whether
naive tiling helps or hurts.

### Test budget: t=2

Test at **--t 2** (not t=5). The frontier campaign showed cold solves these tasks at
t=5 regardless (ceiling), and that a starved t=2 budget is where banked skills change
solve/no-solve — precisely the regime where a coverage/retrieval effect can show.

## The geometry-aware retrieval addition (Arm B)

A small, contained, unit-tested addition to `aspire/`. Reusing everything else
unchanged. Reproducing ASPIRE faithfully *requires* real retrieval; the stock
keyword retrieval is an under-implementation, so completing it is in-scope.

1. **Tag skills with source location.** At admission, record the source task's bowl
   location `(x, y)` in the skill's provenance/metadata. The accumulate runner knows
   which spatial task produced each skill; it writes the bowl `(x,y)` (read from the
   privileged observation / task config) into a `source_xy` field carried in the
   skill markdown front-matter or provenance line. Skills without `source_xy` (e.g.
   pure engine-quirk skills) are treated as location-agnostic (always eligible).
2. **Nearest-location retrieval.** A new function
   `retrieve_by_location(library, target_xy, k=1)` returns the `k` skills minimizing
   Euclidean distance from `source_xy` to `target_xy` (location-agnostic skills rank
   after location-tagged ones, or are always included as a small fixed set — decided
   in the plan). The test-time `target_xy` is the held-out task's bowl location, read
   the same way.
3. **Arm-B wiring.** The runner selects Arm B by pointing the actor at
   geometry-aware retrieval instead of `relevant_skills`. Implementation options (the
   plan picks the least-invasive): an env/flag the coordinator honors to swap the
   retrieval function, or a thin wrapper. Arms A and C use the stock path unchanged.

**Pure and testable:** `retrieve_by_location` and the `source_xy` tag parse/round-trip
are unit-tested with synthetic skills and coordinates; no GPU needed.

## Campaign structure (runner: `scripts/libero_tiling.sh`)

`.venv-libero` (robosuite 1.4.0), `MUJOCO_GL=egl`, idempotent via `DONE` markers.

- **Phase 0** — preflight-assert robosuite 1.4; generate per-task privileged configs.
- **Phase 1 — tile-accumulate.** Deeper baseline (`baseline_grasp_lift.py`, reused)
  over a broad location set `ACCUM_TASKS` (~7 tasks) into one shared library at
  --t 5. Each admitted skill is tagged `source_xy`. **Gate:** the tiled library must
  bank ≥2 location-tagged strategy skills from ≥2 distinct locations (else there is
  nothing to tile → stop and report). Record how many of the ~7 solved (honest
  coverage number).
- **Phase 2 — fix held-out set.** Hold out 3 tasks NOT in `ACCUM_TASKS`, chosen to
  sit *within* the convex range of accumulated locations where possible (so tiling
  has a chance). No frontier probe this time — the held-out set is fixed and
  pre-registered; log the accumulated vs held-out locations.
- **Phase 3 — three-arm test.** For each held-out task, N=5 repeats × 3 arms
  (warm-dumpall, warm-geometry, cold) at --t 2. Warm arms copy the frozen tiled
  library per repeat; cold uses an empty dir per repeat.
- **Phase 4 — analyze.**

Knobs: `ACCUM_TASKS` (~7 ids), `HELDOUT_TASKS` (3 ids), `REPEATS=5`,
`ACCUM_T=5`, `TEST_T=2`.

## Metrics and pre-registered decision rule

`scripts/analyze_libero_tiling.py` extends the v2 analyzer to three arms. Per arm
(pooled 15 = 3 tasks × 5): success rate + attempts-to-solve (censored). Pairwise
Fisher-exact p for **B vs C** (headline), **B vs A** (retrieval effect), **A vs C**
(naive-tiling effect). Per-task breakdown.

**Pre-registered rules:**
- **H1-coverage-reproduced:** warm-geometry (B) success > cold (C) AND Fisher p(B,C)
  < 0.10 → the tiled library with good retrieval reproduces a solvability gain.
- **H1-retrieval-is-the-bottleneck:** B success > A success AND Fisher p(B,A) < 0.10
  → retrieval discrimination, not coverage alone, is what matters (strong even if
  B vs C is only suggestive).
- **H0:** neither clears → null; report attempts-to-solve deltas and the per-task
  transfer pattern as the residual finding.

**Power/honesty:** N=5/arm/task (15/arm pooled) is **suggestive, not conclusive**.
Verdict strings must say so. Attempts-to-solve is reported alongside, since it has
been the robust signal.

## Testing

Pure pieces unit-tested; runner executed once (committed), exercised via `DRY=1`.

1. **`retrieve_by_location`** — nearest-`k` by Euclidean distance over synthetic
   `source_xy` skills; ties and location-agnostic handling; `k=1` returns the single
   closest.
2. **`source_xy` round-trip** — a skill written with a source location parses back to
   the same coordinate; a skill without one is treated as location-agnostic.
3. **Three-arm analyzer** — synthetic run dirs for arms A/B/C across 3 tasks →
   correct per-arm pooled success, three pairwise Fisher p, per-task breakdown;
   non-held-out tasks excluded.
4. **Runner dry-run** — `DRY=1` lists Phases 0-4, `.venv-libero`, `--t 5` accumulate
   / `--t 2` test, the three arms, `ACCUM_TASKS`, `HELDOUT_TASKS`.

Full suite green (`python3 -m pytest tests/ -q -p no:anyio`).

## Deliverables

- `aspire/` addition: `retrieve_by_location` + `source_xy` skill tag (contained,
  unit-tested; the stock `relevant_skills` path is untouched so Arms A/C are
  unchanged).
- `scripts/libero_tiling.sh` — runner (Phases 0-4, three arms).
- `scripts/analyze_libero_tiling.py` — three-arm analyzer, pairwise Fisher-exact.
- `runs/2026-07-24-libero-tiling/` — config template snapshot; after execution,
  `results.json` + `FINDINGS.md` with the honest verdict on both hypotheses.
- `tests/aspire/test_libero_tiling_*.py` — the four unit-test groups above.
- Reuse `baseline_grasp_lift.py` from the frontier run (do not re-create).

## Constraints (verbatim, bind every task)

- `.venv-libero` python = `/home/demo/cap-x/.venv-libero/bin/python`; robosuite must
  be 1.4.x (Phase 0 asserts). Never use the main `.venv` for LIBERO.
- Only the retrieval addition touches `aspire/`; the stock `relevant_skills` path and
  all other aspire modules are unchanged so Arms A and C reproduce prior behavior
  exactly.
- capx contract unchanged; `aspire.run` prints one JSON summary line; solved =
  `dbg_score >= 1.0`; admitted skill = non-empty `admitted`.
- `MUJOCO_GL=egl`; runner idempotent via `DONE` markers.
- theta = 1.0; admission_min_val = 0.5 (aspire defaults; not overridden).
- Test budget TEST_T = 2; accumulate ACCUM_T = 5.
- Verdicts labeled **suggestive, not conclusive** at N=5/arm/task.
