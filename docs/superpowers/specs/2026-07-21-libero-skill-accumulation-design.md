# ASPIRE skill-accumulation reproduction on a LIBERO transfer curriculum — design

_Date: 2026-07-21. Status: SPEC for review. Reproduces ASPIRE's distinctive **layer-2
(skill library) curriculum claim** — that skills accumulated from earlier tasks help
later held-out tasks — on a task suite where skills genuinely transfer. Reuses the
`aspire/` pipeline UNCHANGED; the campaign is a runner + analysis script + this design.
Branch `aspire_original_sim`._

## Purpose and question

The paper claims skills admitted while solving a curriculum accumulate into a shared
library that improves later tasks. Our earlier reproduction proved **trace-guided repair**
(handover 30%→95%) but every skill-accumulation attempt came back **null** — diagnosed as
a task-set problem: the Robosuite set had too few *transferable* skills (most tasks passed
at baseline; almost nothing accumulated). This campaign fixes that by moving to a suite
built for transfer, and asks the faithful question:

- **H1 (accumulation helps):** on held-out tasks, repair with a **warm** (curriculum-
  accumulated) library beats repair with a **cold** (empty) library — higher success
  and/or fewer attempts-to-solve.
- **H0 / falsification:** warm ≈ cold. An honest null closes the layer-2 question for
  this suite too, and is reported as such.

Pre-registered before any measurement, variance-aware, reported whichever way it falls —
the same discipline as the prior traces-vs-retry / skill-transfer / curriculum ablations.

## Why `libero_spatial` is the right vehicle

All 10 `libero_spatial` tasks are *"pick up the black bowl [at location X] and place it on
the plate."* Same object, same goal, same required skill (grasp-the-bowl → place-on-plate);
only the bowl's **location** varies (table center, next to ramekin, on the cookie box, on
the stove, in a drawer). A single skill applies to every task — so if ASPIRE skills
transfer anywhere, it is here, and skills banked on easy tasks are exactly what the harder
held-out tasks need. This is the cleanest possible accumulation test and directly repairs
the "too few relevant skills" failure of the Robosuite attempt. (`libero_goal` — wildly
different goals — would reintroduce that failure; `libero_object` is a viable second
vehicle if we extend.)

## Environment (verified feasible)

- **`.venv-libero`** (cap-x, Python 3.12, **robosuite 1.4.0**) runs LIBERO; the main
  `.venv` (robosuite 1.5.1) is Robosuite-only and **incompatible** with LIBERO. The
  campaign runner MUST use `.venv-libero` and **preflight-assert `robosuite` is 1.4.x**,
  failing loud otherwise (a wrong-venv run silently produces garbage).
- **Privileged-observation** LIBERO configs (`franka_libero_spatial_*_privileged.yaml`) —
  ground-truth perception, matching the reproduction's privileged mode; no SAM3 vision.
- Feasibility already proven end-to-end: LIBERO instantiates through our capx engine,
  per-primitive traces are captured, a naive baseline fails, and the full loop (2 debug
  rounds + evosearch `t=5`) **solved** `libero_spatial` task 0, **validated 1.0** on a
  held-out seed, and **admitted 2 skills** — in ~15 attempts (the cost driver).

## Design — three phases

### Phase 0 — preflight + config generation
Assert `.venv-libero` robosuite 1.4.x (the guard). Generate per-task privileged configs
from the `libero_spatial` template by setting `task_id` (0–9). A single generic naive
baseline program (grasp `black_bowl`, place — no committed descent/place refinement, so it
fails and triggers repair) serves every task, since all spatial tasks share the object and
goal.

### Phase 1 — accumulate (build the warm library)
Run **3 tasks** in sequence — `task_id 2 (table center) → 1 (next to ramekin) → 0 (between
plate and ramekin)` — each as a single-task `aspire.run` sharing **one** `--library` dir so
admitted skills accumulate (the paper's curriculum protocol). `--t 5` (full loop), `--s-dbg
0 --s-val 100`. Freeze the result as the **accumulated library**.
- **Gate:** Phase 1 must admit **≥1 skill**. If it admits 0 (all 3 fail to solve+validate),
  warm≡cold trivially — stop and report (either widen budget or pick easier accumulate
  tasks); do NOT spend Phase 2. (The confirmation shows skills do admit, so this is a
  guard, not the expected path.)

### Phase 2a — data-driven, arm-neutral test-task selection
From the **held-out** spatial tasks (task_ids not in {2,1,0}, i.e. {3,5,6,7,8,9}), run a
cheap **cold calibration probe** — one `aspire.run` per candidate, empty library, reduced
budget (`--t 3`), `--s-dbg 0 --s-val 100` — over a candidate shortlist {8, 6, 5, 3}
(tabletop-ish first; add 9/7 if fewer than 2 solve). **Select the 2 held-out tasks the cold
probe solves** (proving solvability → measurable signal); if >2 solve, take the 2 with the
**highest cold attempts-to-solve** (most headroom for warm to improve). Selection depends
only on the **cold** arm, so it cannot bias the warm-vs-cold comparison. Each selected
task's cold calibration run **is reused as cold repeat #1** (no wasted compute).

### Phase 2b — the warm-vs-cold test
For each of the 2 selected held-out tasks, run **2 repeats per arm** (warm already has cold
repeat #1 from calibration → 1 more cold + 2 warm):
- **WARM:** repair with a fresh **copy** of the frozen accumulated library (so within-run
  admissions don't leak across runs; we measure the benefit of the *pre-accumulated*
  skills). `--t 5`.
- **COLD:** repair with a fresh **empty** library. `--t 5`.
Everything else identical across arms: same task config, same naive baseline, same seeds
(`--s-dbg 0 --s-val 100`), same budget.

## Metrics and decision rule (pre-registered)

Per (task, arm, repeat):
- **solved** — did any attempt reach a validated winner (`dbg_score ≥ theta` and `val_score
  ≥ admission_min_val`) within budget? (binary)
- **attempts-to-solve** — the exec index of the first winning program (score ≥ theta on the
  dbg seed), scanning the run's exec dirs in order; **censored (= budget+1)** if unsolved.
  This is the sharper transfer signal (cold spatial_0 needed 15).

**Decision rule:** across the 2 test tasks × repeats, compare warm vs cold on (i) success
rate and (ii) mean/median attempts-to-solve (censored-aware). **H1** if warm shows higher
success AND/OR fewer attempts with a consistent direction; **H0** if warm ≈ cold. Given the
Lean sample (2 tasks × 2 repeats = 4 warm / 4 cold points, +2 cold calibration), report
**effect size and direction as "suggestive," not "proven"** — and report a clean null as a
real result.

## Components (files) — no `aspire/` changes

- `scripts/libero_accumulation.sh` — the campaign runner: (0) preflight guard + config
  generation; (1) Phase-1 accumulate loop (shared library) + skill-count gate; (2a) cold
  calibration + test-task selection; (2b) warm/cold test loop. Idempotent (per-run DONE
  markers), all runs via `.venv-libero`, `MUJOCO_GL=egl`.
- `scripts/analyze_libero_accumulation.py` — reads the run dirs, extracts per-run
  `solved` + `attempts-to-solve` (from the exec `result.json` sequence), emits a warm-vs-
  cold results table + the honest verdict (direction, effect size, H1/H0 call).
- `runs/2026-07-21-libero-accumulation/` — committed config template, the generic baseline,
  the accumulated-library snapshot, per-run logs, and `results.json` + the table.
- Reuse UNCHANGED: `aspire/` (coordinator, actor, evosearch, `skill_library`, capx engine),
  `scripts/capx_execute.py`.

## Budget (Lean tier)

~11 task-solves total: 3 (accumulate) + ≤4 (cold calibration on the shortlist, 2 of which
become test data) + 2 tasks × (2 warm + 1 more cold). ~1 day of GPU compute, modest LLM
credits. Gated: the Phase-1 skill-count gate and the Phase-2a solvability gate both prevent
spending on a study that can't produce signal.

## Honest risks (designed around)

- **Phase-1 banks no skill** → warm≡cold. Guarded by the skill-count gate before Phase 2.
- **No held-out task is solvable in budget** → no signal. Guarded by the cold-calibration
  selection (we only test tasks the cold arm can solve); if <2 solve, widen the shortlist
  or the budget, reported honestly.
- **Skills don't get retrieved for the test task** → warm≡cold. The prior skill-transfer
  test confirmed the retrieval mechanism fires (skills reach the actor); we log the skills
  surfaced per warm run to verify.
- **Lean N is small** → framed as "suggestive," extensible to the Standard/Thorough tiers
  (more test tasks, more repeats, a second suite) if the effect is promising.

## Not doing

- No `aspire/` changes; no new pipeline modules.
- No `libero_goal` (low transfer — wrong vehicle); `libero_object` only as a later
  cross-check if we extend.
- No non-privileged (SAM3 vision) mode in the first campaign.
- No scale-up beyond the Lean tier in this spec (a follow-on decision after the pilot).

## Deliverable mapping

- Directly targets the one ASPIRE mechanism the reproduction has built but never shown:
  curriculum skill accumulation, on a suite where transfer is possible. A positive result
  reproduces ASPIRE's distinctive claim; a null closes it honestly for this suite with a
  clear, pre-registered method — either is a real reproduction result within the ~2-month goal.
