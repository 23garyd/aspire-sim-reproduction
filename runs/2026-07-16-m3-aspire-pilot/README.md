# M3 ASPIRE pilot — trend reproduction on the hard bimanual tasks

2026-07-16, simhost. ASPIRE (this repo) vs our own M1 CaP-Agent0 baseline
(runs/2026-07-15-m1-baseline-pilot/), same privileged CaP-X robosuite configs,
baselines = CaP-Agent0's own failed programs.

| task | baseline | ASPIRE (held-out) | mechanism |
|---|---|---|---|
| two_arm_handover | 3/10 (30%) | **5/5 (100%)** | evosearch (round-1 candidate B; Stage-1 repair had failed 0.0) |
| two_arm_lift | 1/10 (10%) | **5/5 (100%)** | single trace-guided Opus repair |

Paper's headline: handover 20% -> 92%. Ours: 30% -> 100% (pilot scale, n=5 held-out).
The two tasks succeeded by DIFFERENT mechanisms — the paper's architectural argument
for having both trace-guided repair and evolutionary search.

Notable: both actors' diagnoses were trace-grounded (per-seed handle-axis angles read
from trace.json; keyframe PNGs cited by filename). Both actors filed BLOCKED.md re: no
per-seed replay affordance (systematic; tracked in gap-fix plan backlog). 4 skills
admitted to the shared library (skills/). Lift's repair did not cite handover's skills —
no cross-task transfer claim from this run.

Caveats: pilot scale (10-trial baseline, 5-seed validation); privileged observation
mode; single campaign run; model = current Opus/Sonnet vs paper's Opus 4.6.
