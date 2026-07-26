# Pre-registration — val-confirmatory campaign (frozen 2026-07-26)

Committed BEFORE any test run; its git hash is logged by the runner at Phase 0.

- Primary metric: val_score over held-out seeds 200-204 (debug seed 0); val-solved = val_score >= 0.5.
- Arms: warm_dumpall (library = ~/aspire_runs/libero_tiling/tiled_library, frozen) vs cold.
- Test budget: t=2. N: 10 reps/arm/task.
- Candidate pool: spatial {3,6,8} + libero_10 {0..9}.
- Selection rule (overfit band): cold dbg-rate >= 0.6 AND cold val-rate <= 0.2; >=2 selected or stop.
- Decision: H1 iff warm_dumpall val-rate > cold val-rate AND Fisher p < 0.05; else H0.
- Secondary (non-decisive): dbg contrast; continuous mean val_score + Mann-Whitney.
- Known limitation: reused cold data (spatial 3,6,8; libero_10 0,3,6) estimated val on the prior
  single seed 100; freshly probed tasks use 200-204. Affects only the coarse selection filter, not
  the test (which re-measures both arms on 200-204).
