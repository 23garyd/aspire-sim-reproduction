# Code block 0
import numpy as np

"""
CANDIDATE B -- head-biased initial grasp to enlarge the exposed handle
span, plus re-perceive for arm1 (retries a previously BLOCKED branch
with a new, image-grounded technique)

HYPOTHESIS
Candidate A fixes the diagnosed root cause (arm1's hardcoded target)
but still only has ~0.09m of exposed handle to work with, because arm0
grasps the handle at its exact reported middle (get_hammer_pose()'s
convention). The baseline's own comments assert a ">8cm gripper
buffer" requirement; a ~9cm total span leaves almost no room to honor
that while also keeping both grippers clear of the handle's ends.

An earlier debugging pass explicitly flagged an off-center grasp (arm0
holding closer to the head, exposing more handle toward the tip) as a
fix, but marked it BLOCKED: it requires knowing which way the head
points in the world frame, and reading that from the asset file is
forbidden. This candidate retries that branch with a technique that
does NOT require asset access: the head direction is read directly off
the keyframe images already captured in traces/media -- in
seed*_step000 (before arm0's grasp) the hammer's wide head is visible
on the -Y side of the handle-middle point on all 3 debug seeds, and in
seed*_step006/007 (after the fixed reorientation) it consistently ends
up on the -X side, near arm0. That correspondence is deterministic
given this code's own fixed grasp_quat_arm0 and carry_quat_arm0 -- it
does not depend on the hammer's randomized position, only its
(observed-constant) orientation.

Because the debug seeds are only 3 samples and the orientation could
in principle vary on held-out seeds, the bias applied here is
deliberately small (0.03m, roughly a third of the previously-estimated
half-span) rather than a large commitment -- enough to meaningfully
grow the exposed span without much risk of the gripper landing on the
head itself if the estimate is somewhat off.

DIFFERENCE FROM OTHER CANDIDATES
Candidate A never changes arm0's grasp point. Candidate C removes the
reorientation stage entirely. This candidate keeps the baseline's
grasp-lift-carry-reorient structure intact and only perturbs *where on
the handle* arm0 grasps, then reuses re-perception (as in A) with a
larger arm1 offset that the enlarged span should now safely
accommodate.

EXPECTED FAILURE MODE IF WRONG
If the head/tip direction is flipped on a held-out seed (orientation
randomization the 3 debug seeds didn't happen to sample), the bias
moves the grasp *toward* the tip instead of the head, shrinking rather
than growing the usable span -- likely still recoverable by A's
mechanism but with less margin. If the bias magnitude is simply too
large for a shorter-than-expected handle, close_gripper_arm0 could grip
partially on the head, which would tend to show up as an anomaly at
the lift stage (step 2) rather than at arm1's grasp.
"""

grasp_quat_arm0 = np.array([0, 0.707, 0.707, 0])
carry_quat_arm0 = np.array([0, 1, 0, 0])
arm1_grasp_quat = np.array([0, 0, 1, 0])

PRESENT_X = 0.76
PRESENT_Z = 0.175

# Small, conservative bias of arm0's initial grasp toward the head
# (observed at -Y from the handle-middle point in seed*_step000 images,
# consistently across all 3 debug seeds). Growing the exposed span this
# way lets arm1's offset be larger and safer than in Candidate A.
HEAD_BIAS_OFFSET = 0.03
ARM1_OFFSET = 0.08  # only viable because of the enlarged exposed span

# --- Step 1: arm0 grasps the handle, biased toward the head ---
hammer_pos, hammer_quat = get_hammer_pose()

grasp_pos_arm0 = np.array([
    hammer_pos[0],
    hammer_pos[1] - HEAD_BIAS_OFFSET,
    hammer_pos[2],
])

open_gripper_arm0()
goto_pose_arm0(grasp_pos_arm0, grasp_quat_arm0, z_approach=0.12)
close_gripper_arm0()

# --- Step 2: lift clear of the table ---
lift_pos = np.array([grasp_pos_arm0[0], grasp_pos_arm0[1], grasp_pos_arm0[2] + 0.20])
goto_pose_arm0(lift_pos, grasp_quat_arm0)

# --- Step 3: carry to the handover region, then lay the hammer along X ---
carry_pos = np.array([PRESENT_X, 0.0, grasp_pos_arm0[2] + 0.20])
goto_pose_arm0(carry_pos, grasp_quat_arm0)
goto_pose_arm0(carry_pos, carry_quat_arm0)

# --- Step 4: descend to handover height ---
present_pos = np.array([PRESENT_X, 0.0, PRESENT_Z])
goto_pose_arm0(present_pos, carry_quat_arm0)

# --- Step 5: re-perceive, then aim arm1 at the enlarged exposed span ---
hammer_pos_now, hammer_quat_now = get_hammer_pose()

arm1_grasp_pos = np.array([
    hammer_pos_now[0] + ARM1_OFFSET,
    hammer_pos_now[1],
    hammer_pos_now[2],
])

open_gripper_arm1()
goto_pose_arm1(arm1_grasp_pos, arm1_grasp_quat, z_approach=0.12)
close_gripper_arm1()

# --- Step 6: arm0 releases ---
open_gripper_arm0()

# --- Step 7: arm0 retreats down and away in -X, clear of the hammer ---
retreat_pos = np.array([hammer_pos_now[0] - 0.22, 0.0, PRESENT_Z + 0.18])
goto_pose_arm0(retreat_pos, carry_quat_arm0)
