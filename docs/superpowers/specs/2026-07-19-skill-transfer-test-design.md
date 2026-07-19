# Skill-transfer test — design

_Date: 2026-07-19. Status: SPEC for review — no code, no spend yet. Purpose:
validate ASPIRE **layer 2** (the skill library) by testing whether skills learned
on one task transfer to improve repair on a *different* task's baseline. This is
the sibling to the traces-vs-retry ablation: that tested the trace channel; this
tests the skill-accumulation channel, the other architecture layer this project
built but has never exercised (every campaign to date used empty libraries)._

## Question

ASPIRE claims skills extracted from solved tasks accumulate in a shared library
and help future tasks. We have never tested this — the lift-repeats and ablation
campaigns deliberately used **empty** libraries to isolate the repair loop. Does
seeding the library with skills from task A measurably improve held-out repair on
task B, versus an empty library, with everything else held equal?

- **H1 (transfer):** a lift run seeded with handover-derived skills produces
  higher held-out validation than a lift run with an empty library.
- **H0 / falsification:** seeded ≈ empty. If we cannot reject this, the skill
  layer does not demonstrably transfer here — an honest, reportable result.

## Direction: handover-provenance skills → `two_arm_lift`

Forced (correctly) by the task inventory:
- **Target = `two_arm_lift`** — baseline ~10%, real headroom to detect
  improvement. (Handover is near-ceiling at 95% and is useless as a target — no
  room to show a skill effect.)
- **Seed = the 2 handover-provenance skills** from the M3 pilot library
  (`~/aspire_runs/m3/skill_library/`, provenance verified `two_arm_handover
  dbg=1.00 val=1.00`):
  - `multi-effector-geometry/allocate-shared-object-span-between-two-effectors`
  - `forbidden-api-workaround/keyframe-geometry-from-trace-images`
- **Lift-provenance skills are EXCLUDED from the seed**
  (`derive-grasp-orientation-from-observed-part-axis`,
  `infer-quaternion-convention-from-home-pose`) so this is a genuine cross-task
  transfer, not lift-skills-helping-lift.

Plausible mechanism: `allocate-shared-object-span-between-two-effectors` is about
two effectors sharing one rigid object — directly relevant to lifting a two-handle
pot with two arms.

## Arms — single manipulated variable = library contents

| | **S (seeded)** | **E (empty)** |
|---|---|---|
| Library at repeat start | fresh copy of the 2 handover skills + index | empty dir |
| Everything else | baseline `code.py` (md5 0ada19ef), s_dbg [0,1,2], s_val 100-119, theta 1.0, debug_rounds 2, opus repair, **t=0 (evosearch off)**, isolated dirs | identical |

Per-repeat isolation exactly as lift-repeats/ablation: fresh task dir seeded with
the pristine baseline, **own fresh library copy** (so admission during one repeat
cannot leak into the next), own exec out-root. Arm E is byte-identical to the
lift-repeats condition.

## Why the seed reaches the repair actor (verified in code)

The lift baseline fails **silently** — every primitive returns `[ok]`, score 0,
no error-status traces (this is documented in the M3 skills themselves). So
`task_context.relevant_skills` finds no failure-token keywords, and its
`library.retrieve(...)` returns nothing, falling back to `library.load_all()`,
which writes the whole seeded library into `skills.md`. Therefore arm S's
Stage-1 repair actor genuinely sees both handover skills; arm E sees `(none)`.
`t=0` keeps the comparison on the Stage-1 repair actor (evosearch never runs),
matching the ablation and keeping cost/variance down; skills still reach that
actor via `skills.md`.

## Metric & pre-registered analysis

Identical to the ablation (variance-dominated task ⇒ distribution, not single
runs):
- **N = 8 per arm**, staged: N=5/arm signal check first, extend to N=8 (then N=16
  only if the direction is consistent but underpowered). Done repeats are skipped
  on re-run.
- **Primary:** one-sided Mann-Whitney U on the 8-vs-8 held-out `val_score`. The
  `mann_whitney_u` function in `scripts/analyze_ablation.py` is reused as-is; its
  `main()` currently hardcodes arm dirs `T`/`C`, so it gets a small,
  tested parameterization to accept arm labels (here `S`/`E`) — or a thin
  `scripts/analyze_skill_transfer.py` wrapper that calls the shared
  `mann_whitney_u`. Either way the statistic code is not reimplemented.
- **Secondary effect sizes:** mean, median, P(val ≥ 0.80).
- **Pre-committed reading:** report the result whichever way it falls, including
  "no detectable transfer." Do not read a null from an underpowered run; if the
  direction is consistent but non-significant, note "extend / redesign for power"
  rather than claiming either outcome.

## Reused infrastructure (little new code)

Almost entirely a **launcher + a seed-library fixture**; the engine, coordinator,
CLI, and analysis already exist:
- `scripts/skill_transfer.sh` — mirrors `scripts/traces_ablation.sh`: two arms
  (S, E) × N isolated lift repeats, both `--t 0`, `--s-val 100-119`. Arm S copies
  the seed library into each repeat's `skill_library/`; arm E leaves it empty.
- A committed seed-library fixture under the repo (e.g.
  `runs/2026-07-19-skill-transfer/seed_library/`) holding ONLY the 2 handover
  skills + a matching `index.md`, so the experiment is reproducible and not
  dependent on `~/aspire_runs/m3/` state. Built by copying the two provenance-
  verified skill files and regenerating the index.
- `~/start_skill_transfer.sh` — detached launcher (pidfile `/tmp/skill_transfer.pid`,
  log under `~/aspire_runs/skill_transfer/`), mirroring the ablation launcher.
- No changes to `aspire/` package code expected; if `analyze_ablation.py` needs
  arm-name/dir generality it gets a tiny, tested tweak, otherwise reused as-is.

## Verdict logic

- **S > E (significant or consistent effect):** first evidence ASPIRE's skill
  layer transfers across tasks — validates layer 2, the biggest un-tested part of
  the architecture.
- **S ≈ E:** honest evidence that, on this pair, learned skills do not
  demonstrably transfer — reframes the skill layer's value and is worth knowing.

## Not doing (YAGNI)

- No positive-control arm (lift-skills → lift) — a within-task sanity check, not
  the transfer question; can be a cheap follow-up if S≈E and we want to prove the
  instrument can detect *any* skill effect.
- No evosearch-path skill injection (t=0).
- No new statistics beyond the reused Mann-Whitney + effect sizes.
- No multi-task fan-out (handover→lift only) until this one shows signal.
