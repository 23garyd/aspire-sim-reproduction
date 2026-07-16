# Code block 0
import numpy as np

# ============================================================
# Reasoning about the setup and handover strategy
# ============================================================
# Hammer lies flat on table, aligned along Y-axis:
#   - handle toward +Y, head toward -Y
#   - get_hammer_pose() returns the MIDDLE of the handle
#
# Arm0 at x~0.44, Arm1 at x~1.18. Midpoint x ~ 0.81
# Arms face each other along the X-axis.
#
# Handover strategy:
# - Arm0 picks the hammer. To hand over cleanly, we want the hammer
#   oriented along the X-axis (pointing between the two arms) so that
#   Arm1 can grasp the handle while Arm0 holds a different part.
# - Arm0 grabs near the head-side of the handle, Arm1 grabs the free
#   handle end. Since handle is toward +Y and head toward -Y initially,
#   the middle of the handle is our grasp reference.
#
# Plan:
# 1. Arm0 grasps the hammer at the handle-middle with gripper facing
#    down, opening along X (so fingers close across the thin handle
#    which lies along Y).  quaternion [0,0.707,0.707,0].
# 2. Lift up to a safe height.
# 3. Rotate/translate the hammer to the handover point (midpoint,
#    z between 0.15 and 0.20). Reorient hammer to lie along X-axis so
#    Arm1 can approach the handle end from the +X side.
# 4. Arm1 approaches and grasps the handle, Arm0 releases.
# ============================================================

# Get hammer pose (middle of handle)
hammer_pos, hammer_quat = get_hammer_pose()

# --- Step 1: Arm0 grasp the hammer at the handle middle ---
# Gripper facing down, opening along X-axis (fingers close across the
# handle which runs along Y). This gives a firm grasp on the handle.
grasp_quat_arm0 = np.array([0, 0.707, 0.707, 0])

# Approach from above then descend
open_gripper_arm0()
grasp_pos = np.array([hammer_pos[0], hammer_pos[1], hammer_pos[2]])
goto_pose_arm0(grasp_pos, grasp_quat_arm0, z_approach=0.12)
close_gripper_arm0()

# --- Step 2: Lift the hammer straight up ---
lift_pos = np.array([hammer_pos[0], hammer_pos[1], hammer_pos[2] + 0.20])
goto_pose_arm0(lift_pos, grasp_quat_arm0)

# --- Step 3: Move toward handover region while keeping hammer along Y ---
# Handover midpoint between arms: x ~ (0.44 + 1.18)/2 = 0.81
# Keep z in the target band [0.15, 0.20], choose 0.175.
handover_x = 0.81
handover_z = 0.175

# First translate in X toward the midpoint at a safe higher altitude
# to avoid dragging the hammer through the table region.
mid_high = np.array([handover_x - 0.05, 0.0, hammer_pos[2] + 0.20])
goto_pose_arm0(mid_high, grasp_quat_arm0)

# Now reorient the hammer so it lies along the X-axis.
# For a clean handover, Arm0 holds the hammer with the handle pointing
# toward +X (toward Arm1). Arm0 gripper facing down opening along Y-axis
# would hold the handle running along X. quaternion [0,1,0,0].
# Rotate in place at the high position first.
reorient_quat_arm0 = np.array([0, 1, 0, 0])
goto_pose_arm0(mid_high, reorient_quat_arm0)

# --- Step 4: Descend to handover height ---
# Arm0 holds the hammer at the head side (so the handle extends toward
# +X for Arm1). Position Arm0 gripper slightly on the -X side so the
# handle end is exposed toward Arm1.
handover_arm0_pos = np.array([handover_x - 0.10, 0.0, handover_z])
goto_pose_arm0(handover_arm0_pos, reorient_quat_arm0)

# --- Step 5: Arm1 approaches and grasps the handle end ---
# Arm1 gripper facing down opening along Y-axis: [0, 0, 1, 0].
# The handle extends from Arm0's grasp toward +X. Arm1 grabs the handle
# at a point on the +X side, maintaining >8cm buffer from Arm0 gripper.
open_gripper_arm1()
arm1_grasp_quat = np.array([0, 0, 1, 0])

# Handle extends toward +X. Grab ~0.12m toward +X from Arm0's gripper
# to keep a safe buffer.
arm1_grasp_pos = np.array([handover_x + 0.05, 0.0, handover_z])
# Approach from above
goto_pose_arm1(arm1_grasp_pos, arm1_grasp_quat, z_approach=0.12)
close_gripper_arm1()

# --- Step 6: Arm0 releases ---
open_gripper_arm0()

# --- Step 7: Arm0 retreats safely away (up and toward -X) ---
retreat_pos = np.array([handover_x - 0.20, 0.0, handover_z + 0.15])
goto_pose_arm0(retreat_pos, reorient_quat_arm0)