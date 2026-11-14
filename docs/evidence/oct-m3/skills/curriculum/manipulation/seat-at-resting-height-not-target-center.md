# seat-at-resting-height-not-target-center

category: manipulation

## Failure signature

A pick-and-place / insertion / stacking program transports and releases the object over the target, but the object ends up perched on top and tips off; every primitive reports ok while task reward stays 0 across all seeds. The release height was taken from get_object_pose(target)[2], which returns the target's body-center rather than the support surface, so the object is dropped well above where it must seat.

## When to apply

Placements where the manipulated object ultimately rests on the same support surface it started from (drop-onto-peg, insertion, stacking onto a table-supported base) and get_object_pose returns a body-center z that sits above that surface. Signal: grasp/lift verified good, placement command constant across seeds, marginal physics outcome (some seeds barely rest, others fall). Do NOT apply when the target's reported z genuinely is the intended seating height (e.g. placing INTO a container whose reported center is the drop point).

## Strategy

Never seat the carried object at the target's reported center height. Before the pick, capture the object's own resting height rest_z = get_object_pose(object)[2]. Use only the target's x,y for horizontal alignment and rest_z for height: desired_center = [target_x, target_y, rest_z]. Map that desired object-center pose to the gripper/handle command through the fixed grasp transform computed at pick time. Approach from well above (dz ~0.15) with the correct orientation, then descend with a tall, slow z_approach (~0.14) so the object self-centers and drops fully down before open_gripper.

## Code sketch

import numpy as np
# --- before the pick: record the object's natural resting height ---
obj_pos, _ = get_object_pose('the object')
rest_z = obj_pos[2]                      # sits on the support surface
# ... grasp, capturing the rigid object-center -> grasp transform, then lift ...
# --- placement ---
tgt_pos, tgt_quat = get_object_pose('the target')
desired_center = np.array([tgt_pos[0], tgt_pos[1], rest_z])   # target x,y ; object's own z
grasp_pos_desired = desired_center + R_center_desired.apply(p_center_grasp)
above = grasp_pos_desired.copy(); above[2] += 0.15
goto_pose(above, grasp_quat_desired)                          # clear, aligned
goto_pose(grasp_pos_desired, grasp_quat_desired, z_approach=0.14)  # tall, slow, self-centering
open_gripper()

## Provenance

robosuite/nut_assembly dbg=1.00 val=0.80
