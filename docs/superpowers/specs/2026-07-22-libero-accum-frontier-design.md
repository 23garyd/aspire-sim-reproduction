# ASPIRE Skill-Accumulation Follow-up: Frontier + Deeper Baseline

**Date:** 2026-07-22
**Status:** design approved, ready for planning
**Predecessor:** `docs/superpowers/specs/2026-07-21-libero-skill-accumulation-design.md`
(first campaign) and its result `runs/2026-07-21-libero-accumulation/FINDINGS.md`.

## North Star alignment

Single priority: **reproduce ASPIRE's distinctive skill-accumulation claim** —
skills banked from earlier tasks measurably help later held-out tasks — sim-first,
credit-conscious. This spec is the second attempt at the *success-rate* form of that
claim after the first campaign returned a null. `aspire/` (coordinator, actor,
evosearch, skill_library, capx_execute) is reused **unchanged**; deliverables are a
runner script, an analysis script, task assets, and this design doc.

## Why the first campaign was null (root cause)

The 2026-07-21 campaign found warm == cold on held-out **success** (0.75 = 0.75 on
matched tasks), with only a weak attempts-to-solve edge (warm mean 2.0 vs cold 5.3).
Root cause is two structural choices, not a true absence of transfer:

1. **Shallow baseline failures.** The naive baseline had two *bugs*
   (`z_approach=0.0` no-op descent; int-dtype quaternion truncation). The library
   therefore banked two bug-fix skills
   (`nonzero-positive-standoff-for-committed-descent`,
   `float-cast-sampled-quaternion-before-fractional-write`). Cold rediscovers those
   same fixes in 2-3 attempts, so banking them saves a few attempts but never the
   difference between solve and fail.
2. **Test tasks pre-selected to be cold-solvable.** The calibration gate required
   each test task to be solvable cold at `--t 5`. Selecting for cold-success
   structurally guarantees a null on success rate — there is no room for a banked
   skill to *unlock* a task.

An additional confound inflated the auto-verdict: the analysis script pooled all
cold runs (including the two unsolvable calibration-reject tasks the warm arm never
ran on) into the cold arm, producing a misleading "0.75 vs 0.50 / H1 suggestive".
The matched comparison was a wash.

## Approach: two coupled levers

### Lever 1 — Deeper baseline (bank strategy, not plumbing)

Fold the two prior bug-fix lessons **into** the baseline so they are no longer
failure modes, but deliberately leave the genuine manipulation gap open. The new
baseline `runs/2026-07-22-libero-accum-frontier/baseline_grasp_lift.py`:

- opens the gripper,
- samples the grasp pose and **float-casts** the quaternion (`.astype(float)`),
- descends via a **positive standoff ladder** (e.g. 0.10 -> 0.03 -> 0.008; never
  `z_approach=0.0`),
- closes the gripper and lifts clear,
- **does NOT transport the bowl to the plate and does NOT release it.**

Because the two shallow bugs are gone, the repair's *first* required fix is the
strategic one: add the transport-to-plate-pose + lower + open-gripper release. That
sequence is a reusable manipulation lesson across every spatial task (same
grasp-place-bowl skill, only bowl location varies), so it is what the skill library
banks. Strategy in the library, not dtype/standoff plumbing.

**Invariant (unit-tested):** the baseline is valid Python, contains the descent
ladder and the float-cast, and contains **no** place/transport/`open_gripper`-after-
grasp step. This guards the "gap preserved" premise — if a future edit accidentally
completes the task in the baseline, no repair fires and no skill is banked.

### Lever 2 — Frontier test tasks + higher N (create room for success gap)

Invert the selection rule. Instead of "tasks cold can solve", select tasks on the
**solvability knife's edge**: hard enough that cold usually fails, but demonstrably
achievable so warm has a real target and we avoid the both-arms-fail null.

**Frontier probe.** A cheap cold probe at `--t 3`, 2 repeats, over a candidate
shortlist. Keep only tasks that solve **exactly 1 of 2** probe repeats:

- 2/2 solved -> too easy (cold already wins) -> exclude.
- 0/2 solved -> likely unsolvable at this budget (both arms would fail) -> exclude.
- 1/2 solved -> frontier band -> keep.

Select the first 2 qualifying tasks. If fewer than 2 qualify, widen the shortlist
once; if it still fails, stop and report "no frontier band exists at this budget" —
an honest finding (a null of the third kind), not a silent fallback.

**Higher N.** Test at N=5 repeats per arm per task (up from 2), pooled to 10/arm
across the 2 test tasks. This tightens the attempts-to-solve signal and gives the
success-rate contrast enough runs to be *suggestive* (see Power below).

## Campaign structure (runner: `scripts/libero_accumulation_v2.sh`)

All LIBERO runs use cap-x `.venv-libero` (robosuite 1.4.0). `MUJOCO_GL=egl`.
Idempotent via per-run `DONE` markers. Reruns resume; deleting a run dir re-runs it.

- **Phase 0 — preflight + configs.** Assert `.venv-libero` robosuite starts with
  `1.4` (abort otherwise). Generate per-task privileged configs from the
  `franka_libero_spatial_0_privileged.yaml` template by rewriting `task_id`.
- **Phase 1 — accumulate.** Deeper baseline on easy tasks `{0, 1, 2}` into one
  shared library at `--t 5 --s-dbg 0 --s-val 100`. **Gate:** the library must bank
  at least one skill whose provenance is a *place/transport* repair (checked by
  scanning banked skill files for a place/transport/release provenance or category
  signal), not merely >=1 skill of any kind. If the gate fails, the deeper-baseline
  premise did not hold at this budget -> stop with a clear message. This library is
  fresh (the deeper baseline banks different skills than the old 2-skill library);
  do not reuse the 2026-07-21 `accumulated_library`.
- **Phase 2a — frontier probe.** The `--t 3` x 2-repeat cold probe over the
  candidate shortlist; select 2 test tasks by the 1-of-2 rule above. Gate: <2
  selected after one shortlist widening -> stop and report.
- **Phase 2b — warm vs cold.** For each selected task, N=5 repeats per arm at
  `--t 5`. Warm library = a frozen **copy** of the accumulated library (one copy per
  repeat, so admissions during a warm run never leak across repeats). Cold library =
  a fresh empty dir per repeat. All repeats are independent t=5 runs (no
  calibration-reuse, so no budget-mismatch confound).
- **Phase 3 — analyze.** Run `analyze_libero_accumulation_v2.py --root <root>`.

Config knobs at the top of the runner: `ACCUM_TASKS=(0 1 2)`,
`CALIB_SHORTLIST` (candidate held-out ids, e.g. `(8 6 5 3 9 7 4)`), `REPEATS=5`,
`PROBE_T=3`, `PROBE_REPEATS=2`, `TEST_T=5`.

## Metrics and pre-registered decision rule

Analysis (`scripts/analyze_libero_accumulation_v2.py`) compares warm vs cold
**only on the matched selected test tasks** — it never pools probe or reject tasks
into either arm (this is the confound fix). Per arm it reports:

- **Primary: held-out success rate** (fraction of repeats reaching `dbg_score >=
  theta`, theta=1.0), pooled 10/arm, with a **Fisher-exact p** on the 2x2
  warm/cold x solved/unsolved table.
- **Secondary: attempts-to-solve** — exec index of the first `result.json` with
  `score >= theta`, censored (recorded as such) when a run never solves; report mean
  over solved runs and the censored count.
- Per-task breakdown so a single lucky task cannot masquerade as a pooled effect.

**Pre-registered rule:**

- **H1 (reproduced, suggestive):** warm success > cold success on matched tasks AND
  Fisher p < 0.10.
- **H0 (null):** otherwise. Report the attempts-to-solve delta as the residual
  signal and state plainly that accumulation did not change solvability at this
  budget.

**Power / honesty.** N=5/arm/task (10/arm pooled) is explicitly **suggestive, not
conclusive**: a real effect of warm ~60% vs cold ~20% lands near p~0.15. The verdict
string must carry this caveat; no overclaiming. A conclusive result would need
~N=8/arm/task (deferred unless the suggestive read is positive).

## Testing

Pure pieces are unit-tested; the runner is a committed script executed once (long
GPU + credits run), exercised only via `DRY=1`.

1. **Baseline invariant** — `baseline_grasp_lift.py` parses as Python, contains the
   descent-ladder (a positive `z_approach`) and `.astype(float)`, and contains no
   place step (no `open_gripper` after `close_gripper`, no transport-to-plate move).
2. **Frontier selector** — given synthetic probe results, selects exactly the tasks
   with 1-of-2 solved, skips 0/2 and 2/2, returns the first 2, and signals "insufficient"
   when <2 qualify.
3. **Analyze v2** — computes matched per-arm success rates and a Fisher-exact p from
   synthetic run dirs, and **excludes** non-test tasks from both arms (guards the
   confound fix); attempts-to-solve censoring matches the v1 semantics.
4. **Runner dry-run** — `DRY=1` lists Phase 0/1/2a/2b/3, shows `.venv-libero`,
   `--t 5` for accumulate and test, `--t 3` for the probe, and the accumulate ids
   `{0,1,2}`.

Full suite must stay green (`python3 -m pytest tests/ -q -p no:anyio`).

## Deliverables

- `scripts/libero_accumulation_v2.sh` — the runner (Phases 0-3).
- `scripts/analyze_libero_accumulation_v2.py` — matched warm-vs-cold analysis with
  Fisher-exact p and attempts-to-solve.
- `runs/2026-07-22-libero-accum-frontier/baseline_grasp_lift.py` — deeper baseline.
- `runs/2026-07-22-libero-accum-frontier/franka_libero_spatial_0_privileged.yaml` —
  config template snapshot (provenance).
- `tests/aspire/test_libero_accum_v2_*.py` — the four unit-test groups above.
- After execution: `runs/2026-07-22-libero-accum-frontier/{results.json, FINDINGS.md}`
  committed with an honest one-line verdict.

## Constraints (verbatim, bind every task)

- `.venv-libero` python = `/home/demo/cap-x/.venv-libero/bin/python`; robosuite must
  be 1.4.x (Phase 0 asserts). Never use the main `.venv` (robosuite 1.5.1) for LIBERO.
- `aspire/` is not modified. No new aspire modules.
- capx contract unchanged: `capx_execute.py --workdir /home/demo/cap-x --config-path
  <cfg>`; `aspire.run` prints one JSON summary line
  (`{stage_reached, dbg_score, val_score, program, tainted, admitted, config}`);
  solved = `dbg_score >= 1.0`; admitted skill = non-empty `admitted`.
- `MUJOCO_GL=egl`; runner idempotent via `DONE` markers.
- theta = 1.0; admission_min_val = 0.5 (aspire config defaults; not overridden).
- Verdict labeled **suggestive, not conclusive** at N=5/arm/task.
