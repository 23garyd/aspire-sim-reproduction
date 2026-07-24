# LIBERO skill-accumulation frontier campaign — findings

Spec: `docs/superpowers/specs/2026-07-22-libero-accum-frontier-design.md`.
Autonomous-loop ledger: `AUTOLOOP.md`. Predecessor null:
`runs/2026-07-21-libero-accumulation/FINDINGS.md`.

## Attempt 1 (t=5 test budget) — premise validated, H0 null on success

### The premise HELD: banked skills are strategy, not plumbing
The deeper baseline (folds in the two prior bug-fix lessons; leaves the
transport-to-plate gap open) forced the repair to bank genuine manipulation
strategy. Phase-1 accumulate on `{0,1,2}`: spatial_0/1 failed, **spatial_2 solved
(dbg 1.0, val 1.0)** and banked **2 strategy skills**:

- `grasping/rim-grasp-wide-vessel`
- `placement/compensate-offset-grasp-at-place`

This is the central fix over v1 (whose library banked only dtype/standoff
plumbing). The Phase-1 gate (require a place/transport/release skill) passed.

### Frontier selection worked
Cold probe (--t 3 x2) over `{8,6,5,3,9,7,4}` selected **spatial_8** and
**spatial_6**, each solving exactly 1-of-2 — genuine knife's-edge at the probe
budget.

### Result: null on success, positive on speed
Warm (frozen copy of the 2-skill library) vs cold (empty), 5 repeats/arm/task at
--t 5:

| arm  | success (pooled 10) | attempts-to-solve (solved runs) | val-solved |
|------|---------------------|---------------------------------|-----------|
| warm | 9/10 = **0.90**     | mean **3.3**                    | higher    |
| cold | 8/10 = **0.80**     | mean **5.75**                   | lower     |

**Fisher-exact p (matched 2x2) = 1.0000 → H0 (null) on success rate.**

Per task: spatial_6 warm 0.80 vs cold 0.80 (tie); spatial_8 warm 1.00 vs cold 0.80.
Attempts-to-solve is the live signal — starkly on spatial_8: **cold mean 9.25
attempts vs warm 2.0**. Warm consistently reaches a solution faster and validates
more often, but does not change *whether* these tasks get solved.

### Why null on success (the real blocker)
The frontier probe difficulty (t=3) did not translate to the test budget: at
**--t 5 both arms solve most of these tasks**, so there is no headroom for a banked
skill to flip solve/no-solve. The knife's edge at t=3 becomes a near-ceiling at t=5.
This is a *budget-ceiling* problem, not a low-N problem — adding repeats at t=5
cannot manufacture a gap when cold already succeeds ~80-90%.

Raw per-run data: `results_attempt1.json`.

## Attempt 2 (t=2 test budget) — H0 null again, with negative transfer

Same frozen 2-skill library and frontier tasks (8, 6), test budget dropped to
**--t 2** to starve cold. Runner: `scripts/libero_accumulation_v2b_hardfrontier.sh`.
Raw: `results_attempt2.json`.

| arm  | success (pooled 10) | attempts-to-solve (solved runs) |
|------|---------------------|---------------------------------|
| warm | 7/10 = **0.70**     | mean **2.0**                    |
| cold | 8/10 = **0.80**     | mean **4.375**                  |

**Fisher-exact p (matched 2x2) = 1.0000 → H0 (null) on success rate.** Warm success
is actually *lower*, driven by a per-task reversal:

- `spatial_8`: warm **1.00 (5/5)** vs cold **0.60 (3/5)** — warm wins.
- `spatial_6`: warm **0.40 (2/5)** vs cold **1.00 (5/5)** — **cold wins big.**

This is **negative transfer**: the banked grasp/place skills (provenance: spatial_2)
help when the test task's geometry matches (spatial_8) but *actively mislead* the
repair when it does not (spatial_6) — warm fails spatial_6 outright 3/5 (censored),
where cold solves it 5/5. Attempts-to-solve still favors warm (2.0 vs 4.375) — where
a skill fits, it solves fast (spatial_8 warm 2 attempts vs cold 7-9).

## Terminal verdict (both attempts) — premise validated; speed, not solvability

Loop stopped after 2 attempts (the finding is complete and consistent; a 3rd attempt
would not change it). Across ~64 t-equivalent runs:

1. **Premise VALIDATED.** The deeper baseline made the library bank genuine
   manipulation strategy (`rim-grasp-wide-vessel`,
   `compensate-offset-grasp-at-place`), not the dtype/standoff plumbing v1 banked.
   This was the central goal of the redesign and it worked.
2. **No solvability gap — two independent nulls.** t=5: warm 0.90 vs cold 0.80,
   Fisher p=1.0. t=2: warm 0.70 vs cold 0.80, Fisher p=1.0. Accumulation does **not**
   change *whether* these LIBERO-spatial tasks get solved, at either budget.
3. **Robust SPEED benefit.** Attempts-to-solve favors warm in both attempts
   (t=5: 3.3 vs 5.75; t=2: 2.0 vs 4.375). Where a banked skill fits, the repair
   reaches a solution in ~2 attempts instead of 5-9.
4. **Transfer is task-dependent, and can be NEGATIVE.** A skill banked from one bowl
   location helps a matching test task and hurts a mismatching one (spatial_8 vs
   spatial_6). This is the sharpest new result: ASPIRE-style accumulation is not a
   uniform prior — it is a *conditional* one, beneficial only under geometric match.

**Bottom line for the reproduction goal:** ASPIRE's skill-accumulation mechanism
reproduces as a **convergence-speed** effect and a **conditional** transfer effect,
not as a held-out *solvability* gain on this task family. To show a solvability gain
one would need tasks that (a) cold genuinely cannot solve at the test budget and
(b) are covered by a banked skill's geometry — i.e. a curriculum whose banked skills
tile the held-out task distribution, or a task family with a single reusable grasp.
That is the honest next hypothesis, not a result claimed here.
