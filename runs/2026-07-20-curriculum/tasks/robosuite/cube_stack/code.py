# Code block 0
import numpy as np

# Get poses and extents
red_pos, red_quat, red_extent = get_object_pose("red cube", return_bbox_extent=True)
green_pos, green_quat, green_extent = get_object_pose("green cube", return_bbox_extent=True)

# Sample grasp pose for the red cube
grasp_pos, grasp_quat = sample_grasp_pose("red cube")

# Open gripper before grasping
open_gripper()

# Approach and grasp the red cube
goto_pose(grasp_pos, grasp_quat, z_approach=0.1)
close_gripper()

# Lift the red cube to a safe height
lift_pos = grasp_pos.copy()
lift_pos[2] += 0.2
goto_pose(lift_pos, grasp_quat)

# Compute placement position on top of the green cube
place_z = green_pos[2] + green_extent[2] / 2 + red_extent[2] / 2
place_pos = np.array([green_pos[0], green_pos[1], place_z])

# Approach placement location with controlled descent using grasp orientation
goto_pose(place_pos, grasp_quat, z_approach=0.1)

# Gently release the red cube
open_gripper()