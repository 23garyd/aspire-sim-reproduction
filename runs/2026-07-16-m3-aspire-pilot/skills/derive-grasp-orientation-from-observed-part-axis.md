# derive-grasp-orientation-from-observed-part-axis

category: perception-driven-geometry

## Failure signature

A manipulation program carries hardcoded grasp quaternions as module-level constants while the object's yaw is randomized per episode. Every primitive returns [ok] with FAILURES: 0 and no IK or perception failure, but the score is 0 and the object never moves in the post-lift keyframe. The tell is in the perception stream rather than the status stream: the axis between two perceived parts of the same rigid object changes direction across seeds (68.6 deg on one seed vs ~19 deg on two others) while the distance between them stays constant to three decimals — the same object, rotated. A constant quaternion cannot track that, so it can be correct on at most one rotation and is wrong everywhere else.

## When to apply

Any task where the grasp orientation is a literal in the program and the object pose is randomized, AND two or more parts of the same rigid object are separately perceivable (two handles, two ends of a bar, a lid and a body). Diagnose it by computing the inter-part vector on every debug seed: if its direction varies while its norm is constant, orientation is randomized and any hardcoded quaternion is a latent bug. Also apply the converse as a licensing check — a norm AND direction that are both constant across seeds mean orientation is not randomized, which is what makes a keyframe-derived constant safe to reuse (see keyframe-geometry-from-trace-images).

## Strategy

Never write the grasp orientation as a constant; write it as a function of an axis you measured this episode. Recover the axis from the parts the perception API already returns — this is an observation, so it respects the forbidden-API wall and needs no asset read. Project the inter-part vector to horizontal, take yaw = atan2(dy, dx), and build the quaternion from that yaw. Three details matter. First, pin the quaternion ordering empirically before trusting any formula: derive the family so that at yaw=0 it reproduces the arm's OBSERVED home orientation, which turns the home pose into a free unit test (see infer-quaternion-convention-from-home-pose). Second, a parallel-jaw grasp is invariant to 180 deg about its own approach axis, so fold the yaw into (-pi/2, pi/2] to pick the wrist angle nearest home and stay off the wrist limits. Third, decide the finger axis from the part's shape rather than by default: fingers must close ACROSS a thin bar, so for a loop or ring take the axis that straddles a bar, not the one that closes through the hole. Cross-check the finger-axis choice against the required opening — if straddling needs more than the jaw span, you picked the wrong axis or the wrong bar.

## Code sketch

# Diagnosis: same object, rotated -- direction varies, norm does not.
#   seed0: axis 68.6 deg, |h1-h0| = 0.310
#   seed1: axis 19.1 deg, |h1-h0| = 0.310
#   seed2: axis 19.7 deg, |h1-h0| = 0.310
# => any hardcoded grasp quaternion is wrong on at least 2 of 3 seeds.

# Measure the axis from perception, not from a literal and not from an asset.
h0 = np.asarray(get_handle0_pos(), dtype=float)
h1 = np.asarray(get_handle1_pos(), dtype=float)
axis = h1 - h0
axis[2] = 0.0
axis /= np.linalg.norm(axis)

# Parallel jaws are symmetric under 180 deg about the approach axis: fold the
# yaw so the wrist stays near home.
def wrap_yaw(yaw):
    return (yaw + 0.5 * np.pi) % np.pi - 0.5 * np.pi

# Build the orientation as a FUNCTION of the measured yaw. Anchor the family so
# that yaw=0 reproduces the observed home quaternion -- a free correctness check.
def grasp_quat(yaw):                       # (w, x, y, z)
    half = 0.5 * yaw + 0.25 * np.pi
    return np.array([0.0, np.cos(half), np.sin(half), 0.0])

quat = grasp_quat(wrap_yaw(np.arctan2(axis[1], axis[0])))
# One quat, both arms: each gripper points down, fingers close along `axis`.
# NEVER: env.handle.env.sim, or reading .xml/.urdf to recover this rotation.

## Provenance

robosuite/two_arm_lift dbg=1.00 val=1.00
