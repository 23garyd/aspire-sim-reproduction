# Code block 0
import numpy as np
from scipy.spatial.transform import Rotation as R

# Start from home position
goto_home_joint_position()
open_gripper()

# 1. Get the grasp pose at the handle of the nut
grasp_pos, grasp_quat = sample_grasp_pose("extruded handle of the brown square nut")

# 2. Get the nut's object center pose (white hollow center)
nut_center_pos, nut_center_quat = get_object_pose("white hollow center of the brown square nut")

# 3. Compute the rigid transform between the nut center and the grasp handle pose.
# We express the grasp pose relative to the nut center frame.
# T_world_center and T_world_grasp are known; compute T_center_grasp = inv(T_world_center) * T_world_grasp
R_world_center = R.from_quat(np.array([nut_center_quat[1], nut_center_quat[2], nut_center_quat[3], nut_center_quat[0]]))
R_world_grasp = R.from_quat(np.array([grasp_quat[1], grasp_quat[2], grasp_quat[3], grasp_quat[0]]))

# Position offset of grasp relative to center, expressed in center frame
p_center_grasp = R_world_center.inv().apply(grasp_pos - nut_center_pos)
# Rotation of grasp relative to center
R_center_grasp = R_world_center.inv() * R_world_grasp

# 4. Move to the grasp pose to grasp the nut by its handle (with an approach from above)
goto_pose(grasp_pos, grasp_quat, z_approach=0.10)
close_gripper()

# 5. Lift up
lift_pos = grasp_pos.copy()
lift_pos[2] += 0.15
goto_pose(lift_pos, grasp_quat)

# 6. Get the target peg pose (brown square block)
peg_pos, peg_quat = get_object_pose("brown square block")
R_world_peg = R.from_quat(np.array([peg_quat[1], peg_quat[2], peg_quat[3], peg_quat[0]]))

# 7. Compute where the grasp pose must be so that the nut center aligns with the peg.
# We want the nut center to be positioned at the peg (aligned in orientation as well).
# Desired nut center pose in world = peg pose.
# T_world_grasp_desired = T_world_center_desired * T_center_grasp
R_center_desired = R_world_peg
grasp_pos_desired = peg_pos + R_center_desired.apply(p_center_grasp)
R_grasp_desired = R_center_desired * R_center_grasp
grasp_quat_desired_xyzw = R_grasp_desired.as_quat()
grasp_quat_desired = np.array([grasp_quat_desired_xyzw[3], grasp_quat_desired_xyzw[0],
                               grasp_quat_desired_xyzw[1], grasp_quat_desired_xyzw[2]])

# 8. Move above the peg first, then insert down onto the peg
grasp_pos_above = grasp_pos_desired.copy()
grasp_pos_above[2] += 0.10
goto_pose(grasp_pos_above, grasp_quat_desired)

# 9. Insert the nut onto the peg with a slow approach from above
goto_pose(grasp_pos_desired, grasp_quat_desired, z_approach=0.08)

# 10. Release the nut
open_gripper()

# 11. Retreat upward
retreat_pos = grasp_pos_desired.copy()
retreat_pos[2] += 0.15
goto_pose(retreat_pos, grasp_quat_desired)

goto_home_joint_position()