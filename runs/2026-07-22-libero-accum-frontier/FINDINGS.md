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

## Attempt 2 (t=2 test budget) — hardening the frontier
Next revision (auto-selected over the spec's N->8 step, which would not address the
ceiling): reuse the SAME accumulated strategy library and the SAME frontier tasks
(8, 6), but drop the **test** budget to **--t 2** so cold is starved and must rely on
discovering the strategy from scratch — where a banked strategy skill can plausibly
make the difference between solving and not. Success rate + attempts-to-solve
re-measured, same pre-registered H1 (Fisher p < 0.10) / H0 rule. See AUTOLOOP.md.
