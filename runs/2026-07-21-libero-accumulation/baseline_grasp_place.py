# Generic naive baseline for libero_spatial (every task = grasp the black bowl, place on
# the plate). Grasps at a single hover waypoint with no committed descent and no place ->
# fails, triggering trace-guided repair. Same program for all spatial tasks (shared object).
open_gripper()
gpos, gquat = sample_grasp_pose("black_bowl")
goto_pose(gpos, gquat, z_approach=0.05)
close_gripper()
