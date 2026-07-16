# keyframe-geometry-from-trace-images

category: forbidden-api-workaround

## Failure signature

A repair branch is abandoned or marked BLOCKED in the ledger because it needs object-part geometry -- which end carries the head, which way a handle points, an object's extent or principal axis -- and that information appears reachable only through the forbidden simulator handle or asset files (.bddl/.xml/.urdf). The branch then stays untested indefinitely, not because it was disproven but because its evidence source was ruled out. In the originating task this exact branch was BLOCKED for a full pass and turned out to be the ONLY candidate of three that scored above zero.

## When to apply

Any time a promising repair stalls on 'I cannot know the object's geometry without reading the asset', AND the trace bundle contains recorded keyframe images (traces/media/seed*_step*_{before,after}.png). Applies across manipulation tasks needing part-level semantics: which end of a tool to grasp, a mug handle's direction, a drawer's pull axis, a peg's long axis. Also apply when re-reading a ledger: a BLOCKED entry is retestable if you can supply a genuinely NEW evidence technique, not merely retry the same reasoning with more confidence.

## Strategy

Read the geometry off the keyframe images already captured in the trace bundle -- they are observations, not asset reads, so they respect the forbidden-API wall. Establish the fact in the rest frame (e.g. 'the wide head sits on the -Y side of the reported origin at step000') and cross-check it on EVERY debug seed before relying on it; also confirm the corresponding post-manipulation frame (e.g. head ends up on -X after the commanded reorientation) so the fact holds in the frame the repair actually uses. Cross-validate against the reported pose stream: an orientation quaternion that is bit-identical across seeds with no floating-point jitter indicates orientation is not randomized, which is what makes an image-derived direction safe to reuse. Then hedge the commitment: because debug seeds are a small sample that may not cover the held-out distribution, size the resulting parameter conservatively so a flipped sign degrades margin rather than inverting the strategy, and write the expected failure mode if the sign is wrong into the candidate so a bad outcome is diagnostic. When re-entering a BLOCKED branch, state in the ledger which NEW technique unblocks it -- that is the admission criterion.

## Code sketch

# Ledger discipline -- a BLOCKED entry is retestable ONLY with a new technique:
#   BLOCKED: off-center grasp needs head direction; asset read forbidden.
#   RETESTABLE: head direction read from traces/media keyframes (observations,
#               not assets) -- consistent on all 3 debug seeds.

# Step 1: Read direction off recorded keyframes (allowed: they are observations).
#   Read('traces/media/seed0_step000_get_object_pose_before.png')  # rest frame
#   Read('traces/media/seed0_step006_goto_pose_arm0_after.png')    # post-reorient
# Confirm on seed1/seed2 too -- a fact true on one seed is an anecdote.

# Step 2: Corroborate with the reported pose stream. A quaternion that is
# bit-identical across seeds (e.g. exactly [0.5, 0.5, 0.5, -0.5], no jitter)
# implies orientation is NOT randomized -> an image-derived direction transfers.
_, q = get_object_pose()

# Step 3: Hedge the commitment. Small magnitude => a flipped sign on a held-out
# seed costs margin instead of inverting the strategy.
HEAD_BIAS = 0.03   # ~1/3 of estimated half-span, direction from keyframes above

# Step 4: Record the expected failure mode so a bad run is still informative:
#   'if head/tip is flipped on held-out seeds, the bias shrinks rather than
#    grows the span -> shows up at the partner grasp; if the magnitude is too
#    large for a short object, effector0 grips the head -> shows up at lift.'
# NEVER: env.handle.env.sim, or reading .bddl/.xml/.urdf to get this direction.

## Provenance

robosuite/two_arm_handover dbg=1.00 val=1.00
