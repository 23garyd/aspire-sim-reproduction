# allocate-shared-object-span-between-two-effectors

category: multi-effector-geometry

## Failure signature

Two effectors must engage the same rigid object at once (handover, dual-arm lift, hand-to-hand regrasp). The second effector's target is computed as object_origin + small_offset while the first effector holds the object AT or NEAR that same origin, so the two grippers end up only a few cm apart. All primitives report [ok], FAILURES: 0, and the second grasp looks geometrically 'on the object' -- yet the score is 0. The tell is that a correctly re-perceived, on-object target still fails: the offset was measured in the object's frame while the constraint that actually binds is gripper-to-gripper separation. Confirmed quantitatively in the originating task: identical programs differing only in this allocation scored 0.00 at ~5.1cm separation and 1.00 at ~11.5cm.

## When to apply

Whenever two effectors must occupy one object simultaneously and the object's graspable extent is comparable to the required inter-gripper clearance -- i.e. the span is a budget that must be DIVIDED, not a target both arms aim at independently. Apply as soon as a program computes both grasp points from the same perception origin. Also apply when a task brief, baseline comment, or authoring note asserts a minimum buffer/clearance between effectors: treat such a note as a real constraint until disproven, since here it was unconfirmed (task.md had no captured runtime language) yet turned out to be exactly the binding constraint.

## Strategy

Treat the object's exposed span as a resource allocated between the two effectors, and track TWO distinct quantities that a single offset silently conflates: (a) offset-from-object-origin, which decides whether the grasp lands on the object at all, and (b) separation-from-partner-gripper, which decides whether the buffer is honored. Repair in two coupled moves. First, bias the FIRST effector's grasp deliberately off-center, AWAY from the region the second effector needs -- this is the move that manufactures span; without it the first gripper sits on the origin and every offset the second effector uses is simultaneously (a) and (b), making the buffer unsatisfiable on a short object. Second, size the second effector's offset from the fresh origin so that the resulting gripper-to-gripper separation clears the buffer, remembering that the perception origin has itself shifted by the bias (a directly observable check: the re-perceived origin should move by ~the bias amount relative to the commanded first-gripper position -- if it does not, the bias sign or the object's convention is wrong, and that check costs nothing). Keep the bias magnitude CONSERVATIVE (~1/3 of the estimated half-span) so that a wrong sign degrades margin rather than causing the first effector to grasp the wrong part of the object entirely. Verify the direction of the bias with keyframe-geometry-from-trace-images, never from asset files.

## Code sketch

# The two quantities a naive single offset conflates:
#   (a) offset from the object's perception origin -> 'am I on the object?'
#   (b) separation from the partner gripper        -> 'do I clear the buffer?'
# If effector0 holds AT the origin, (a) == (b) and the budget is unsatisfiable.

BIAS = 0.03        # conservative: ~1/3 of estimated half-span, direction from keyframes
PARTNER_OFFSET = 0.08

# Move 1 -- effector0 grasps OFF-CENTER, away from the region effector1 needs.
# This manufactures exposed span; it is what decouples (a) from (b).
obj_pos, obj_quat = get_object_pose()
grasp0 = np.array([obj_pos[0], obj_pos[1] - BIAS, obj_pos[2]])  # -Y == away side
open_gripper_arm0()
goto_pose_arm0(grasp0, grasp_quat_arm0, z_approach=0.12)
close_gripper_arm0()

# ... lift / carry / reorient, commanding effector0's gripper to present_pos ...

# Move 2 -- re-perceive, then offset so gripper-to-gripper separation clears
# the buffer. Free sanity check: obj_pos_now should sit ~BIAS away from the
# commanded gripper position. If it does not, the bias direction is wrong.
obj_pos_now, _ = get_object_pose()
target1 = np.array([obj_pos_now[0] + PARTNER_OFFSET, obj_pos_now[1], obj_pos_now[2]])
# separation ~= PARTNER_OFFSET + BIAS, not PARTNER_OFFSET alone -- that sum is
# the quantity the buffer constrains.
open_gripper_arm1()
goto_pose_arm1(target1, grasp_quat_arm1, z_approach=0.12)
close_gripper_arm1()
open_gripper_arm0()  # release only after the partner has closed
# No env.handle.env.sim; no asset/.xml/.urdf reads.

## Provenance

robosuite/two_arm_handover dbg=1.00 val=1.00
