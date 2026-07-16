# relocalize-support-immediately-before-placement

category: localization

## Failure signature

A pose read at reset disagrees with the same object's pose re-read later in the episode, with no intentional contact in between. Two distinct causes produce this: (a) settling, a consistent ~1cm z drop as spawned objects drop onto their support once physics steps (green cube z -0.087 -> -0.09710775 in every episode here), and (b) collateral disturbance, where the arm clips a neighbouring object while working (validation seed 103: support displaced 3.35cm in y and tumbled out of upright). Placements computed from the reset read land systematically high, or beside a support that is no longer there.

## When to apply

Any task computing a placement, stacking or insertion target from a pose sampled before the arm has moved: stacking, put-on-shelf, put-in-container, insertion. Cheap enough to apply unconditionally. The disturbance case makes it valuable even in harnesses without spawn-settling, and it matters most when the manipulated and support objects start close together, where the approach is most likely to clip the support.

## Strategy

Treat any pose read at t=0 as provisional. Re-read the SUPPORT object's position immediately before computing the placement target, after the pick has already stepped the sim; that single read absorbs both settling and any disturbance the arm caused on the way. Bounding-box extents are sizes, not poses, so they are unaffected by both and may safely be read once up front: refresh only the position. Add a small release clearance on top of the computed contact height so the held object is dropped a few millimetres rather than driven into its support. Two assumptions to keep in view: the sum-of-half-extents math is valid only because sample_grasp_pose returns the object's centre here, so the end-effector frame coincides with the held object's centre while grasped (verify this in a new harness rather than assuming it); and support_ext[2]/2 is the support's VERTICAL half-extent only while the support is upright, which seed 103 shows is not guaranteed. That approximation survived here only because a cube's extents are all equal; for a non-cube support, check the support's orientation before trusting it.

## Code sketch

# Extents are stable -> read once. Positions settle and get knocked -> re-read late.
_, _, support_ext = get_object_pose(support, return_bbox_extent=True)
_, _, held_ext = get_object_pose(held, return_bbox_extent=True)

pick_pos, pick_quat = sample_grasp_pose(held)
open_gripper()
goto_pose(pick_pos, pick_quat, z_approach=0.1)
close_gripper()
lift = pick_pos.copy(); lift[2] += 0.2
goto_pose(lift, pick_quat)

# ... the pick above has stepped the sim, so read the support NOW, not at reset ...
support_pos, support_quat, _ = get_object_pose(support, return_bbox_extent=False)

# Guard the upright assumption behind the half-extent math (pure-yaw quat => upright).
# For a non-cube support, a tumbled support_quat invalidates support_ext[2] as 'height'.
place = support_pos.copy()
place[2] = support_pos[2] + support_ext[2]/2 + held_ext[2]/2 + 0.005  # release clearance
goto_pose(place, pick_quat, z_approach=0.1)
open_gripper()

## Provenance

robosuite/cube_stack dbg=1.00 val=1.00
