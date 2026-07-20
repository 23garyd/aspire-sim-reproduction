# Code block 0
import numpy as np

# Sample a grasp pose for the red cube
grasp_position, grasp_quaternion = sample_grasp_pose("red cube")

# Open the gripper before approaching
open_gripper()

# Move to the grasp pose with an approach offset in Z for a precise approach
goto_pose(grasp_position, grasp_quaternion, z_approach=0.1)

# Close the gripper to grasp the red cube
close_gripper()

# Lift the cube by moving up 0.2 meters in Z
lift_position = grasp_position + np.array([0.0, 0.0, 0.2])
goto_pose(lift_position, grasp_quaternion)