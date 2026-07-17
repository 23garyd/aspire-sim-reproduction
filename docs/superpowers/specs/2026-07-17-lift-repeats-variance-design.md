# Lift campaign-repeats variance experiment — design

_Date: 2026-07-17. Status: executed autonomously per handoff TODO #2 ("campaign
repeats (N runs/task) on two_arm_lift — the variance instrument for the
0/20-vs-5/5 finding"). Parameter choices below were made by the agent under the
standing "continue" authorization; user review welcome — repeats are additive
and the campaign can be killed via `/tmp/lift_repeats.pid` at any time._

## Question

The M3 pilot repaired `two_arm_lift` 10% → 100% (dbg 1.0, val 5/5). M3X, same
baseline program and same pipeline, got dbg 0.0, val 0/20. Which run was
representative? Estimate p = P(a campaign run produces a validated-successful
lift program) and characterize *where* runs diverge (Stage-1 repair vs
evosearch rescue vs total failure).

## Approaches considered

1. **N independent repeats, empty per-repeat skill library** (chosen).
   Matches M3X's starting condition; every repeat is i.i.d. — the cleanest
   estimate of run-to-run variance of the repair pipeline itself.
2. Repeats sharing one accumulating library — measures cross-run learning, not
   variance; skill admission in repeat k contaminates repeat k+1. Rejected for
   this instrument (interesting follow-up).
3. Repeats seeded with the M3 pilot's final 4-skill library — measures whether
   prior knowledge stabilizes lift. Also a follow-up, not the variance
   instrument.

## Design

- **Task**: `two_arm_lift` only. Handover is settled (95% @ n=20, Stage-1-only);
  lift is where variance dominates.
- **N = 5** sequential repeats. Enough to distinguish p≈0 from p≈0.5 at pilot
  scale; each failure-path repeat costs ~2.4 h (M3X measured 18:28→20:52),
  success-path much less. Worst case ≈ 12 h (overnight). Repeats are numbered
  and independent, so extending to N=10 later is trivial — just run more.
- **Config identical to M3X** for comparability: s_dbg [0,1,2] (default),
  `--s-val 100-119` (n=20), theta 1.0, debug_rounds 2, same capx-cmd/config
  yaml, same LLM proxy setup.
- **Per-repeat isolation** (state markers live in the task dir; the library is
  mutated by admission):
  - `~/aspire_runs/lift_repeats/rep_N/robosuite/two_arm_lift/` — fresh task
    dir containing ONLY the pristine baseline `code.py` (byte-identical in m3
    and m3x task dirs; verified the pipeline never writes that path — task.md,
    traces/, skills.md are materialized by TaskPipeline).
  - `~/aspire_runs/lift_repeats/rep_N/skill_library/` — fresh EMPTY library
    (verified `SkillLibrary.load_all()/retrieve()` return `[]` on an empty
    dir; M3X itself started empty).
  - `~/aspire_runs/lift_repeats/rep_N/exec/` — per-repeat out-root.
- **Metrics per repeat** (from the CLI's JSON result line + task-dir
  artifacts): stage_reached, dbg_score, val_score, mechanism (Stage-1 round
  that won / evosearch round / none), skills admitted. The campaign-level
  result is the distribution over 5 repeats plus the two historical points
  (pilot=success, M3X=fail).
- **Launcher**: `scripts/lift_repeats.sh` (versioned, does staging + the loop,
  logs to `~/aspire_runs/lift_repeats/campaign.log`) + thin
  `~/start_lift_repeats.sh` detached starter with pidfile
  `/tmp/lift_repeats.pid`, per the established on-box daemon pattern.
  Staging is idempotent-safe: a rep dir that already has `VALIDATION_DONE` is
  skipped (crash-resume = rerun the launcher).

## Error handling

- A repeat that exits non-zero is logged and the campaign continues to the
  next repeat (one bad repeat must not kill the instrument).
- LLM proxy checked before launch; each repeat re-checks the proxy port and
  aborts that repeat (not the campaign) if it is down.

## Not doing (YAGNI)

- No repo-code changes: the existing CLI (`--s-val` range parsing from
  eabf263) is sufficient. No new tests — this is campaign tooling, exercised
  live; the 182-test suite is untouched.
- No handover repeats, no TRIALS=100 baseline re-run, no val-score admission
  gate (separate backlog items).
