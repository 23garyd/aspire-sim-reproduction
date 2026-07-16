# Code block 0
import numpy as np

# Sideways grasp orientations:
# We want the gripper y-axis aligned with world z-axis, and gripper approaching the handle horizontally.
# Arm 0 grasps handle 0, Arm 1 grasps handle 1 (opposite sides of the pot).

# Quaternion for arm 0 (sideways grasp, approaching from arm0's side)
# This orientation aligns gripper y-axis with world z and approaches horizontally.
quat_arm0 = np.array([0.5, 0.5, 0.5, 0.5])
# Quaternion for arm 1 (sideways grasp from opposite side, rotated 180 deg about world z)
quat_arm1 = np.array([0.5, -0.5, 0.5, -0.5])

# Step 1: Slightly lift both arms first to avoid occluding the pot and handles.
pos0, q0 = get_arm0_gripper_pose()
pos1, q1 = get_arm1_gripper_pose()

pos0_lift = pos0.copy()
pos0_lift[2] += 0.15
pos1_lift = pos1.copy()
pos1_lift[2] += 0.15

goto_pose_both(pos0_lift, quat_arm0, pos1_lift, quat_arm1)

# Open both grippers
open_gripper_arm0()
open_gripper_arm1()

# Step 2: Get handle positions
handle0 = get_handle0_pos()
handle1 = get_handle1_pos()

# Step 3: Move both arms above their respective handles (pre-grasp), approaching from above with offset
pre_grasp0 = handle0.copy()
pre_grasp0[2] += 0.10
pre_grasp1 = handle1.copy()
pre_grasp1[2] += 0.10

goto_pose_both(pre_grasp0, quat_arm0, pre_grasp1, quat_arm1)

# Step 4: Move down to grasp the handles using z_approach for precise approach
grasp0 = handle0.copy()
grasp1 = handle1.copy()

goto_pose_both(grasp0, quat_arm0, grasp1, quat_arm1, z_approach=0.10)

# Step 5: Close both grippers to grasp handles
close_gripper_arm0()
close_gripper_arm1()

# Step 6: Lift the pot up at the same height simultaneously
lift0 = grasp0.copy()
lift0[2] += 0.20
lift1 = grasp1.copy()
lift1[2] += 0.20

goto_pose_both(lift0, quat_arm0, lift1, quat_arm1)