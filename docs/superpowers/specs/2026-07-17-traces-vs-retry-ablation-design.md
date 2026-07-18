# Traces-vs-retry ablation — design

_Date: 2026-07-17. Status: SPEC for review — no code, no spend yet. Purpose:
test whether ASPIRE's per-primitive multimodal traces are **causally** responsible
for the repair improvement, or whether a plain reward-driven retry with the same
compute budget does just as well. This is the experiment that can falsify the
architecture's central claim, so the design is built to make disconfirmation
possible and clean._

## Question

Our campaigns show the ASPIRE repair loop lifts a 10–30% CaP-Agent0 baseline to
85–95% held-out on two bimanual tasks. But we have only shown the *whole loop*
helps — not *which signal* does the work. ASPIRE's signature ingredient is the
per-primitive trace (function, args, status, result_summary, duration, and
keyframe images). Does that trace channel improve repair over an actor that sees
only the scalar outcome (per-seed pass/fail + aggregate score) and the program,
given the **same** model, attempt budget, and execution access?

- **H1 (treatment effect):** the trace-equipped actor produces higher held-out
  validation scores than the trace-blind actor on `two_arm_lift`.
- **H0 / falsification:** trace-blind ≈ trace-equipped. If we cannot reject this,
  traces do not earn their keep on this task, and we should say so.

## Arms

Two arms, identical in every respect except trace access:

| | **T (treatment)** | **C (control / plain retry)** |
|---|---|---|
| Actor sees | full traces: per-primitive records + `summary.txt` + keyframe images | scalar only: per-seed pass/fail + aggregate score, plus the program |
| Task-dir context | `traces/` materialized as today | `traces/` replaced by a one-line `outcome.txt` (score, per-seed booleans) |
| Repair prompt | current trace-conditioned prompt | trace-blind variant (same ask: diagnose + rewrite; no trace data) |
| Replay affordance | returns full trace as today | matched budget, **trace-stripped** feedback (returns only the scalar score) |
| Model / temp / seeds | opus repair, `s_dbg=[0,1,2]`, `s_val=100–119` | identical |
| Attempt budget | `debug_rounds`, `max_seed_attempts` as today | identical |
| Skill library | empty (isolate the repair loop) | empty |
| Evosearch | **disabled** (see below) | disabled |

The control is a genuine reward-driven retry with matched compute — not a
strawman. It gets the same number of program executions/replays; the only thing
withheld is the *content* of the feedback (per-primitive trace → scalar).

## Key design decisions (made by the agent; flag for override)

1. **Evosearch disabled in both arms.** Evosearch proposals are also
   trace-conditioned (G3 history carries trace summaries), so leaving it on would
   confound the attribution. The clean claim is about the **repair actor**, so
   both arms run Stage-1 repair only. This is a valid regime: the variance
   campaign showed Stage-1 alone solved 3/5 lift runs. (Follow-up could ablate
   traces through the full pipeline including evosearch.)
2. **Primary task = `two_arm_lift`.** It is the hard, repair-dependent task where
   traces should matter most. Handover is near-saturated (95%) and would give a
   ceiling'd, low-power comparison. Handover included only as a stretch secondary.
3. **Empty skill library in both arms.** Removes the skill-transfer confound;
   isolates the within-task repair signal. (Matches the variance campaign.)
4. **Trace channel ablated as a whole** (structured records *and* keyframe
   images). This tests the full trace channel. A finer future ablation could
   separate text-trace vs image contribution.

## Variance-aware analysis (pre-registered)

Lift repair is variance-dominated (measured: held-out val spans 0.0–1.0, mean
0.67 across 7 runs). A single run per arm proves nothing. Therefore:

- **N = 8 independent repeats per arm** (pilot). 16 lift runs total. Each repeat
  fully isolated exactly as the lift-repeats campaign (fresh task dir with the
  pristine baseline `code.py` md5 `0ada19ef`, fresh empty library, own exec root).
- **Primary metric:** distribution of held-out `val_score` per arm. Report both
  arms' full per-run scores, mean, and median.
- **Decision rule (pre-registered):** one-sided Mann–Whitney U on the 8-vs-8
  per-run val scores (rank-based — the distribution is non-normal and bounded),
  plus the effect size (difference in means and in P(val ≥ 0.80)). We commit to
  reporting the result **whichever way it falls**, including "no detectable
  difference."
- **Secondary metrics:** Stage-1 first-attempt solve rate; token cost per
  validated success; qualitative diff of *how* each arm's diagnoses read
  (trace-cited vs blind-guess).
- **Power caveat, stated up front:** N=8/arm is a pilot. Given the variance, only
  a large effect is detectable at this N. If the result is ambiguous (overlapping
  distributions, U-test inconclusive), the honest read is "underpowered — extend
  to N=16/arm," not "no effect." The spec pre-commits to that escalation rather
  than over-reading a null.

## Implementation surface (for the later build, not this spec)

Small, FakeEngine-testable — the ablation is entirely about *what context the
actor receives*:

- `RunConfig.ablate_traces: bool = False` (logged per run like `admission_min_val`).
- `write_execution_context`: when ablated, write `outcome.txt` (score + per-seed
  booleans) instead of `traces/trace.json` + `summary.txt` + keyframes.
- New trace-blind repair prompt file (`prompts/`), selected when ablated.
- Replay shim: when ablated, `replay.json` policy returns scalar-only feedback.
- Evosearch off for the campaign via config (`t=0` or a guard), both arms.
- CLI: `--ablate-traces`; a campaign launcher mirroring `scripts/lift_repeats.sh`
  that runs N repeats of each arm.

## Cost

16 lift runs (8/arm). Lift runs measured at ~0.5–2.4 h each depending on how far
repair goes, plus opus repair tokens per run. Budget deliberately: this needs
API credits and ~1–2 days of GPU wall-clock. **Recommended staging:** run N=5/arm
first (10 runs) as a signal check; if a gap is visible, extend to N=8–16/arm for
the reportable result. Kill/resume via the same pidfile+VALIDATION_DONE pattern.

## Not doing (YAGNI)

- No text-trace-vs-image sub-ablation (future).
- No evosearch-path ablation (future).
- No handover unless lift shows signal and budget remains.
- No new statistical machinery beyond Mann–Whitney U + effect sizes.

## Success = a defensible answer either way

This experiment succeeds if it yields a clean, pre-registered answer:
- **If T > C:** first causal evidence that per-primitive traces (not just extra
  retries) drive ASPIRE's repair gains — the strongest single result we could add.
- **If T ≈ C:** honest evidence that on this task, scalar-driven retry with a
  capable model matches trace-guided repair — which reframes the architecture's
  value proposition and is worth knowing before scaling.
