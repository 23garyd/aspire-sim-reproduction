# Task analysis: robosuite/two_arm_handover

## Scene description (from traces/trace.json + traces/media, baseline run, all 3 debug seeds)

- Two-arm hammer handover. Arm0 is stationed near a table (base ~x=0.44)
  and starts closest to the hammer; arm1 is stationed further away with
  no table (base ~x=1.18), facing arm0 along the shared X-axis.
- `get_hammer_pose()` returns `(pos, quat)` of the **middle of the
  handle** (not the head, not the tip). Observed positions vary per
  seed (x in [0.32, 0.40], y in [-0.09, 0.08], z ~ -0.104), but the
  returned quaternion is **exactly** `[0.5, 0.5, 0.5, -0.5]` on all 3
  seeds, with no floating-point jitter. This strongly suggests hammer
  *orientation* is not randomized by this env (only position is) —
  treated as a working hypothesis carried into this round's
  hypotheses, not a certainty (3 samples is a small, potentially
  unrepresentative set of the held-out distribution).
- At rest, the handle runs along the **Y-axis**; the head is toward
  **-Y** from the handle-middle point and the free tip toward **+Y**
  (visible in `seed*_step000_*` keyframes, and consistent with the
  original baseline author's comment).
- Arm0's grasp-lift-carry-reorient-descend sequence is reliable on all
  3 seeds — every primitive in that sequence reports `[ok]`, no
  IK/perception failures, confirmed visually at each stage
  (`seed*_step002` grasp contact, `seed*_step004` lift, `seed*_step006`
  in-place reorientation to lay the hammer along the X-axis with the
  head ending up on **-X** near arm0 and the tip on **+X** toward
  arm1, `seed*_step007` presentation pose).
- Arm1's reach/IK is **not** the bottleneck: `goto_pose_arm1` reports
  `[ok]` reaching x=0.86 in the baseline trace — the failure is aim,
  not reachability.
- Failure (baseline `code.py`, score 0.0, all 3 seeds, deterministic):
  arm1's grasp target is the **hardcoded absolute coordinate**
  `handover_x + 0.05 = 0.86`, unrelated to where the hammer's handle
  actually ends up after arm0's carry (~x=0.80 by rough visual
  estimate, scaling the hammer against the two known gripper
  x-positions in `seed0_step009`). Arm1 closes on air
  (`seed*_step010`), arm0 releases (`step011`), hammer drops to the
  floor (`step012`, confirmed visually — hammer resting on the floor
  tile, both grippers empty).
- Available primitives observed in use: `get_hammer_pose()`,
  `open_gripper_arm0/1()`, `close_gripper_arm0/1()`,
  `goto_pose_arm0/1(pos, quat, z_approach=...)`. No grasp-success /
  contact-feedback primitive has been observed — success can only be
  inferred indirectly (position sanity via a fresh `get_hammer_pose()`
  call, or visual/score feedback after replay).

## Ledger

### Eliminated (confirmed by testing — do not retest)
- **Hardcoded absolute-world-coordinate target for arm1's grasp**,
  disconnected from the hammer's actual post-carry position. Confirmed
  root cause via trace + keyframe evidence on all 3 debug seeds
  (baseline `code.py`, score 0.0). Any candidate whose arm1 target is
  a constant not derived from a fresh `get_hammer_pose()` call taken
  after arm0's carry/reorient repeats this exact failure and should
  not be resubmitted.

### Blocked, untested (retry only with a new technique)
- **Off-center initial grasp biased toward the head**, to enlarge the
  exposed handle span for arm1 (relevant if the baseline's own
  ">8cm gripper buffer" comment is a real constraint — unconfirmed,
  since `task.md` has no captured runtime task language). Previously
  blocked because the head's direction in the world frame was judged
  unverifiable without reading the asset file. **Newly retestable
  this round**: the head direction is instead read off the existing
  `traces/media` keyframes (image evidence, not asset files) —
  head at -Y from the grasp point at rest, at -X after the fixed
  reorientation, consistent across all 3 debug seeds. Retried this
  round in Candidate B with a deliberately small bias (0.03m) to limit
  risk if the sign/magnitude estimate is imperfect on held-out seeds.
- **Skipping the X-axis reorientation stage**, having arm1 approach
  laterally along Y instead of along X. Not previously attempted in
  any candidate (all prior traces only ever moved arm1 along X at
  y=0). Untested for a structural reason, not a diagnosed blocker:
  nothing rules it out, but arm1's lateral (Y) reach and inter-arm
  clearance at the shared midpoint have never been exercised. Tested
  this round in Candidate C.

## This round's hypotheses (iter_00, candidates A/B/C)

- **H_A (candidate_A)**: the hardcoded-target defect is the *only*
  thing wrong. Re-perceiving the hammer pose after arm0's carry and
  offsetting by a small, span-centered amount (0.045m) — instead of
  the baseline's disconnected constant — is sufficient. Everything
  else (grasp point, lift, carry, reorient) is kept identical to the
  baseline since it was never implicated in the failure. Expected
  failure mode if wrong: the fixed 0.045m offset over/undershoots on
  held-out seeds whose exposed span differs materially from the ~9cm
  debug-seed estimate.
- **H_B (candidate_B)**: re-perception alone may leave too little
  margin to satisfy a possible buffer requirement. Biasing arm0's
  *initial* grasp 0.03m toward the head (using the image-established
  head direction, not asset data) should enlarge the exposed span
  enough to support a larger, safer arm1 offset (0.08m). Expected
  failure mode if wrong: a flipped head/tip direction on some held-out
  seed would shrink rather than grow the span; too-large a bias for a
  shorter-than-assumed handle would show up as an anomaly at the lift
  stage (arm0 partially gripping the head) rather than at arm1's
  grasp.
- **H_C (candidate_C)**: the reorientation-to-X-axis stage is not
  load-bearing and may itself be a source of error; removing it and
  having arm1 approach laterally (Y-axis) at the hammer's rest
  orientation is a structurally simpler path. Expected failure mode if
  wrong: arm1 lacks comfortable lateral reach at the shared midpoint,
  or the two grippers interfere at close range — should surface as a
  new failure signature (IK/reach anomaly or a carried-pose
  disturbance) distinct from baseline's "closes on air" pattern.

## Known unknowns carried forward
- Whether hammer orientation is truly fixed (position-only
  randomization) on held-out seeds, or just happened to match on all 3
  debug seeds.
- Whether the ">8cm gripper buffer" and z in [0.15, 0.20] constraints
  in the original baseline's comments are real task requirements or
  authoring notes — `task.md` still has no captured runtime task
  language.
- The true exposed-handle-span length; all offsets above are estimates
  from a single scaled image measurement, not a measured constant.

## iter_00
- iter_00/candidate_A/code.py: 0.00 — no failures
- iter_00/candidate_B/code.py: 1.00 — no failures
- iter_00/candidate_C/code.py: 0.00 — no failures
