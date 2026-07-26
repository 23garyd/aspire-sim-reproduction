# Handoff: harder-held-out campaign (libero_10) — already designed, run, and nearly complete

For whichever Claude session owns aspire going forward. The "harder task
distribution" follow-up suggested in FINDINGS (post-7d78842) has **already been
executed** — do not spec or launch a duplicate.

## Campaign (root: ~/aspire_runs/libero_hard)

- **Probe (done 2026-07-25):** all 10 libero_10 tasks, cold arm, 1 rep.
  Ranking: 10_1/3/4/5/8/9 = hard floor (0.0/0.0, 10-11 attempts);
  10_0/10_6 = middle band (dbg 1.0 / val 0.0); 10_2/10_7 = ceiling (1.0/1.0).
- **Anchor finding:** only 10_3's scene has a bowl → warm_geo (ASPIRE_TARGET_XY)
  is undefined on every other libero_10 task. Geometry retrieval as implemented
  does not transfer beyond bowl scenes — worth a line in FINDINGS.
- **Main design:** 10_0 + 10_6 (middle) + 10_3 (floor, bowl present);
  warm_dumpall vs cold on all three x 10 reps; warm_geo on 10_3 only x 10 reps;
  --t 2, --s-val 100, library = ~/aspire_runs/libero_tiling/tiled_library.
- **Status at handoff:** 67/70 cells DONE, last 3 finishing; wrapper
  (scripts/libero_hard_campaign.sh) auto-runs the analysis into
  ~/aspire_runs/libero_hard/analysis.log when done
  (analyze_libero_tiling.py --root ~/aspire_runs/libero_hard --heldout 0,6,3 --prefix 10).

## Infrastructure changes on disk (uncommitted)

- `scripts/libero_tiling_parallel.py` — parallel queue runner (atomic .claim
  files, DONE-compatible resume, shared API-server holder, planner-failure
  guard + circuit breaker; exit 3 = breaker tripped, exit 4 = transient
  failures left cells behind). Generalized: --root/--suite/--tasks/--reps/
  --arms/--prefix/--library/--no-analyze; defaults reproduce the spatial campaign.
- `scripts/libero_hard_campaign.sh` — staged wrapper with cool-down/retry.
- `aspire/schemas.py` — **bug fix**: ActorReport.load now filters unknown keys
  from proposed_skills entries (actors emit e.g. "provenance"; the strict
  dataclass kwargs crashed whole runs). This killed spatial warm_dumpall/3 once
  and 6 libero_hard warm cells — i.e. it selectively suppressed the library
  arms. Unit-tested; affected cells were reset and re-run post-fix.
- `scripts/analyze_libero_tiling.py` — --prefix arg (default "spatial";
  regression-tested against the spatial campaign result).
- Auth policy: runner strips ANTHROPIC_API_KEY/ANTHROPIC_AUTH_TOKEN from child
  envs — subscription billing only (matches commit c869b7f's intent).

## Failure archives

Failed-attempt logs preserved per cell as log.failed-apilimit.txt /
log.plannerfail.*.txt / .failed*/ subdirs (2026-07-25 API-key rate-limit
incident + provenance-bug crashes).

## Results (final, 2026-07-26 08:31, 70/70 cells)

analysis.log aggregate says H0 — but it is confounded twice: (1) warm_geo ran
only on 10_3 (hardest task) yet is aggregated against mixed-task arms; (2) the
analyzer scores dbg_score (debug-seed solved), not held-out validation.
Per-task, on val_score (held-out generalization):

| task | warm_dumpall | cold | Fisher p |
|---|---|---|---|
| 10_0 (middle) | 4/10 | 1/10 | 0.30 |
| 10_6 (middle) | 4/10 | 0/10 | 0.087 (< .10) |
| 10_3 (floor)  | 0/10 (geo 0/10) | 1/10 | — |
| pooled 10_0+10_6 (post-hoc) | 8/20 | 1/20 | 0.020 |

Key reading: on middle-band harder tasks the library flips to decisively
helpful on held-out validation — cold overfits the debug seed (10_0: dbg 9/10
but val 1/10) while warm_dumpall generalizes (val 8/20 vs 1/20). Floor tasks
stay unsolvable for every arm. warm_geo remains bowl-anchor-limited and showed
nothing on 10_3. Suggested FINDINGS framing: "library value appears exactly
where cold has headroom AND is measured on held-out validation, not debug."
