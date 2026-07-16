# infer-quaternion-convention-from-home-pose

category: forbidden-api-workaround

## Failure signature

A repair must author an absolute orientation, but the wrapper's quaternion ordering is undocumented — (w, x, y, z) and (x, y, z, w) are both plausible and the codebase cannot be read to settle it. Guessing wrong silently inverts the wrist: the program still runs, IK still solves, every primitive still reports [ok], and the grasp closes on air. The baseline's own constants are no help when they are numerically symmetric (e.g. [0.5, 0.5, 0.5, 0.5] decodes identically under both orderings), so the ambiguity survives inspection of the existing code.

## When to apply

Any task where a repair authors an absolute orientation against an undocumented pose API, and the trace reports at least one pose whose true orientation is independently known or visible in a keyframe. The arm's rest/home pose is the ideal probe because it is reported at step 0 of every seed and is almost always visually unambiguous (grippers hang down). Apply BEFORE writing any quaternion, not after a failed replay — a wrong ordering is silent, so the failed replay will not name it as the cause.

## Strategy

Turn the ordering into a decidable question instead of a guess, using two sources that already exist in the trace bundle. First, decode each reported home quaternion under BOTH orderings and ask which one is physically coherent; the discriminator is that the WRONG ordering usually breaks on only one arm, so decode every arm you have, not just one. Here arm0's home decoded to gripper-down under both orderings and was useless on its own, while arm1's decoded to gripper-down under (w,x,y,z) but gripper-UP under (x,y,z,w) — a rest pose no arm holds. Second, confirm against the home keyframe, which is an observation and costs nothing: seed*_step000_*_before.png showed both grippers hanging down, ruling out the (x,y,z,w) reading. Then bake the conclusion in as a permanent check rather than a comment: construct the grasp family so that its identity case (yaw = 0) reproduces the observed home quaternion. If the ordering assumption is ever wrong, the family no longer matches the pose the trace actually reports, so the error surfaces at authoring time instead of as an unexplained air grasp.

## Code sketch

# Reported home poses (step 0, every seed):
#   arm0: [ 0.0025,  0.9977, -0.0020,  0.0674]
#   arm1: [ 0.0491, -0.0058, -0.9988, -0.0024]
#
# Decode under BOTH orderings; the wrong one typically breaks on ONE arm only:
#   (x,y,z,w): arm0 -> 180 deg about Y -> z_g = -Z  (down, plausible)
#              arm1 -> 180 deg about Z -> z_g = +Z  (UP -- no arm rests like this)
#   (w,x,y,z): arm0 -> 180 deg about X -> z_g = -Z  (down)
#              arm1 -> 180 deg about Y -> z_g = -Z  (down)  <-- both coherent
# => ordering is (w, x, y, z). Confirm on the keyframe, which is an observation:
#   Read('traces/media/seed2_step000_get_arm0_gripper_pose_before.png')
#   -> both grippers visibly hang down. (x,y,z,w) is refuted.
#
# Bake it in: at yaw=0 the family must REPRODUCE the observed home orientation,
# so a wrong assumption fails loudly at authoring time, not silently at grasp.
def grasp_quat(yaw):                       # (w, x, y, z)
    half = 0.5 * yaw + 0.25 * np.pi
    return np.array([0.0, np.cos(half), np.sin(half), 0.0])
# grasp_quat(0) == [0, .707, .707, 0]: gripper down, 45 deg of wrist from home.
# NEVER settle this by reading the wrapper's source, .xml, or .urdf.

## Provenance

robosuite/two_arm_lift dbg=1.00 val=1.00
