# Two-arm pot lift.
#
# The pot's yaw is randomized per episode. Across the three debug seeds the
# handle0 -> handle1 axis sits at 68.6 / 19.1 / 19.7 degrees while the handle
# separation stays fixed at 0.310 m, so the pot is the same object rotated.
# The baseline used constant grasp quaternions, which cannot track that yaw,
# and additionally aimed both grippers along world +X (a horizontal approach)
# when the handles are flat horizontal loops that have to be taken from above.
# Both closes were air grasps and the pot never moved, yet every primitive
# still reported ok.
#
# Everything below derives the grasp from the two observed handle positions,
# so it follows whatever yaw the episode happens to draw. No seed-specific
# branches, no simulator handle, no asset reads.

import numpy as np

OUTWARD_BIAS = 0.03       # along the handle axis, away from the pot body
PRE_GRASP_HEIGHT = 0.10
LIFT_HEIGHT = 0.20
CLEAR_HEIGHT = 0.15


def wrap_yaw(yaw):
    """Fold a yaw into (-pi/2, pi/2].

    A parallel-jaw grasp is unchanged by rotating 180 degrees about its own
    approach axis, so this picks the equivalent wrist angle nearest each arm's
    home orientation and keeps us away from wrist limits.
    """
    return (yaw + 0.5 * np.pi) % np.pi - 0.5 * np.pi


def grasp_quat(yaw):
    """Gripper pointing straight down, fingers closing along the handle axis.

    Quaternions are (w, x, y, z) here: that is the only ordering under which
    both reported home poses come out gripper-down, and the home keyframes show
    both grippers pointing down. At yaw = 0 this is a 45-degree wrist rotation
    from the observed home orientation, so it stays well inside the wrist range.
    """
    half = 0.5 * yaw + 0.25 * np.pi
    return np.array([0.0, np.cos(half), np.sin(half), 0.0])


# Step 1: clear both arms upward, each keeping its current orientation, so
# nothing hangs over the pot while we perceive it.
pos0, q0 = get_arm0_gripper_pose()
pos1, q1 = get_arm1_gripper_pose()

clear0 = pos0.copy()
clear0[2] += CLEAR_HEIGHT
clear1 = pos1.copy()
clear1[2] += CLEAR_HEIGHT
goto_pose_both(clear0, q0, clear1, q1)

open_gripper_arm0()
open_gripper_arm1()

# Step 2: read the pot's yaw off the handle axis. Both handles are observable,
# so the axis between them gives the rotation directly.
handle0 = np.asarray(get_handle0_pos(), dtype=float)
handle1 = np.asarray(get_handle1_pos(), dtype=float)

axis = handle1 - handle0
axis[2] = 0.0
axis /= np.linalg.norm(axis)
quat = grasp_quat(wrap_yaw(np.arctan2(axis[1], axis[0])))

# Step 3: bias each grasp outward along the handle axis, away from the pot.
# The handles are open loops, so aiming at the reported centre risks closing
# through the hole. With an ~8 cm finger span centred 3 cm outboard, the
# fingers cover roughly 1 cm inboard to 7 cm outboard of the reported site,
# which brackets the loop's outer bar whether that site sits at the loop's
# centre or at the bar itself.
# If this is wrong it fails as another air grasp at the lift, with the pot left
# on the table: too large a bias closes past the bar, too small closes in the
# hole. Both show the same signature, so sweep OUTWARD_BIAS if the lift fails.
grasp0 = handle0 - OUTWARD_BIAS * axis
grasp1 = handle1 + OUTWARD_BIAS * axis

pre0 = grasp0.copy()
pre0[2] += PRE_GRASP_HEIGHT
pre1 = grasp1.copy()
pre1[2] += PRE_GRASP_HEIGHT
goto_pose_both(pre0, quat, pre1, quat)

# Step 4: descend onto the handle bars and close.
goto_pose_both(grasp0, quat, grasp1, quat, z_approach=PRE_GRASP_HEIGHT)
close_gripper_arm0()
close_gripper_arm1()

# Step 5: lift both handles by the same amount so the pot comes up level.
lift0 = grasp0.copy()
lift0[2] += LIFT_HEIGHT
lift1 = grasp1.copy()
lift1[2] += LIFT_HEIGHT
goto_pose_both(lift0, quat, lift1, quat)
