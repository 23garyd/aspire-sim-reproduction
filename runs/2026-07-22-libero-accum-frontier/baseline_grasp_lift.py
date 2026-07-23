# Deeper naive baseline for libero_spatial (every task = grasp the black bowl, place on
# the plate). This baseline folds in the two prior bug-fix lessons so they are no longer
# failure modes: it float-casts the sampled quaternion (no int-dtype truncation) and
# descends via a POSITIVE standoff ladder (never a zero standoff, so the descent is
# genuinely committed). It grasps and lifts the bowl clear -- but deliberately does NOT
# transport the bowl to the plate and does NOT release it. The remaining gap is the
# strategic manipulation step (transport-to-plate + lower + release), so trace-guided
# repair banks a strategy skill, not dtype/standoff plumbing. Same program for all
# spatial tasks (shared object; only bowl location varies).
open_gripper()
gpos, gquat = sample_grasp_pose("black_bowl")
# gquat may be int-dtype (e.g. array([0,1,0,0])); .astype(float) yields a new float array
# so any fractional orientation write would not truncate (fixes the dtype-truncation bug).
quat = gquat.astype(float)
# Positive standoff ladder: coarse hover -> intermediate -> shallow committed contact.
# Never a zero standoff (the engine treats a falsy/zero standoff as 'stay put').
goto_pose(gpos, quat, z_approach=0.10)   # hover
goto_pose(gpos, quat, z_approach=0.03)   # intermediate
goto_pose(gpos, quat, z_approach=0.008)  # committed contact -- small POSITIVE, never 0.0
close_gripper()
goto_pose(gpos, quat, z_approach=0.25)   # lift clear (larger positive standoff)
