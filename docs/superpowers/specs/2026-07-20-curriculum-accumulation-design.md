# Curriculum-accumulation experiment — design

_Date: 2026-07-20. Status: SPEC for review — no code, no spend yet. Purpose:
reproduce ASPIRE's **layer 2 (skill library) in its intended curriculum mode** —
run a sequence of tasks with a shared, accumulating library, then measure whether
the accumulated library improves repair on the hardest held-out task. This is the
one architecture mechanism the reproduction has built but never exercised as the
paper intends; the earlier skill-transfer test used a hand-picked 2-skill seed and
came back null, so this is where the faithful answer lives._

## Question

The paper claims skills admitted while solving a curriculum accumulate into a
shared library that helps later tasks. Every campaign to date used **empty**
libraries; the skill-transfer test seeded 2 hand-picked handover skills (null).
Does the library **actually accumulated by running the other tasks** improve
held-out lift repair, versus an empty library?

- **H1 (accumulation helps):** lift run with the curriculum-accumulated library
  (warm) beats lift with an empty library (cold).
- **H0 / falsification:** warm ≈ cold. An honest null closes the layer-2 question
  for this suite.

## Two phases

**Phase 1 — accumulate (the curriculum).** Run the four **non-lift** tasks in
order — `cube_lifting → cube_stack → nut_assembly → two_arm_handover` — each as a
single-task `aspire.run`, all pointing at ONE shared `--library` dir so admitted
skills accumulate across the sequence. (We do NOT use `--tasks-root`: it bakes a
single `--config-path` into the shared capx-cmd and cannot handle the four
different env YAMLs. A bash loop of single-task runs sharing one `--library`
accumulates identically and handles per-task configs.) Freeze the result as the
**accumulated library**.

- Lift is EXCLUDED from the accumulation set, so no measured-task self-leakage —
  any benefit must come from *other* tasks' skills (the paper's actual claim).
- **Honest expectation (pre-registered):** the 3 easy tasks pass at baseline
  (reward 1.0 → no repair → no skills), so the accumulated library will be driven
  mainly by handover (and any nut_assembly failures). If it ends with <2 skills,
  the warm/cold test degenerates toward the transfer test — we say so, and the
  finding "our suite lacks enough failing-but-solvable diverse tasks for
  accumulation to matter" is itself a legitimate layer-2 reproduction result.

**Phase 2 — measure (warm vs cold on lift).** Reuse the skill-transfer harness:
- **Warm (arm S):** each lift repeat seeded with a fresh copy of the accumulated
  library.
- **Cold (arm E):** each lift repeat with an empty library.
- N repeats/arm, held-out `s_val 100-119`, pristine lift baseline (md5 0ada19ef),
  isolated dirs, `--t 0`. Single manipulated variable = library contents.

## Config (all phases)

`--t 0` (Stage-1 repair only — evosearch off), `s_dbg [0,1,2]`, `s_val 100-119`,
theta 1.0, debug_rounds 2, opus repair, `admission_min_val 0.5`. Rationale for
`--t 0` throughout: comparability with the traces-ablation and skill-transfer
tests, lower cost/variance, and skills still reach the Stage-1 repair actor via
`relevant_skills` (load_all fallback on the silently-failing lift baseline —
verified in the skill-transfer review). Accumulation admits skills from Stage-1
winners across the sequence, gated by `admission_min_val` (validated live).

## Metric & pre-registered analysis

Same as the ablation/transfer (variance-dominated ⇒ distributions):
- **N = 5/arm** staged (signal check), extend to **N = 8** if directionally
  consistent, N=16 only if still ambiguous. Done repeats skipped on re-run.
- **Primary:** one-sided Mann-Whitney U (warm=S vs cold=E) via the reused
  `scripts/analyze_skill_transfer.py` (arms S/E) — no reimplementation.
- **Secondary:** mean, median, P(val ≥ 0.80).
- **Pre-committed:** report either way; do not read a null from an underpowered
  run; the accumulated-library contents are logged so the result is interpretable
  against how many/which skills were actually available.

## Reused infrastructure (minimal new code)

- **Accumulation launcher** `scripts/curriculum_accumulate.sh` — bash loop over
  the 4 non-lift tasks, each `aspire.run --task-dir <task> --library
  $ACCUM_LIB --capx-cmd "...--config-path <task yaml>" --t 0 --s-val 100-119`,
  sharing one `$ACCUM_LIB`. Idempotent (VALIDATION_DONE skip). Prints the final
  accumulated skill list.
- **Task-dir fixtures** for the 4 non-lift tasks under
  `runs/2026-07-20-curriculum/tasks/<suite>/<task>/code.py` (trial_01 baseline
  copied from M1), committed for reproducibility, with a per-task env-config map
  in the launcher.
- **Phase-2 measurement**: reuse `scripts/skill_transfer.sh` unchanged by passing
  `SEED=$ACCUM_LIB` (its arm S copies `$SEED`, arm E empty). Confirm the seed-dir
  override is honored; if `SEED` is hard-coded, add a `SEED=${SEED:-<fixture>}`
  env override (one-line, tested via structural grep).
- **Analysis**: `scripts/analyze_skill_transfer.py` unchanged (arms S/E).
- **No `aspire/` package changes expected.**

## Verdict logic

- **Warm > cold:** first evidence ASPIRE's curriculum-accumulated library
  transfers — validates layer 2 in the paper's intended mode.
- **Warm ≈ cold:** honest null; combined with the transfer test, strong evidence
  that on this suite layer-2 accumulation adds no measurable value — the repair
  power lives in per-run trace-guided repair.

## Not doing (YAGNI)

- No `--tasks-root` dependency (heterogeneous-config limitation).
- No richer/synthetic curriculum (forcing easy tasks to fail) — that would be
  unfaithful; we report what the real baselines accumulate.
- No evosearch in the measurement (t=0), matching prior experiments.
- No positive control (accumulate-including-lift) — that reintroduces
  self-leakage the design specifically avoids.
