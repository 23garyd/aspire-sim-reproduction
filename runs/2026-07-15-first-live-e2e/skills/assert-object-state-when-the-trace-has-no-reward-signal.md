# assert-object-state-when-the-trace-has-no-reward-signal

category: verification

## Failure signature

The harness reports a program as passing on the strength of 'FAILURES: 0' / all-ok statuses, but the trace schema contains no reward, success or solved field. A program that does nothing at all earns exactly the same score as one that solves the task, so the pass carries no information about the objective.

## When to apply

Any task whose trace records only per-call status (function/args/status/result_summary/duration_ms) with no task-level outcome field. Check this BEFORE trusting a validation result or declaring a repair validated. It applies to every task type in such a harness, and is most urgent when the failure mode under repair is a silent no-op, because that is precisely the mode a status-only metric cannot see.

## Strategy

Make the outcome observable from inside the program, using only permitted observation APIs. Re-read the MANIPULATED object's pose at the very end of the episode, compute the pose the task predicts, and record the comparison so the trace itself carries an outcome signal. This costs one extra call, needs no simulator access, and converts an unfalsifiable 'all primitives returned ok' into a checkable claim. Two corollaries: (a) do the same after the grasp (re-read the held object once the arm has lifted; if its z did not rise with the end-effector, the gripper closed on air), and (b) when reporting, keep 'the repair fixes a real defect' separate from 'the repair is measured to solve the task'; a status-only pass supports only the former.

## Code sketch

# Status-only traces cannot distinguish 'did the task' from 'did nothing'.
# Re-read the moved object at the end so the trace records an outcome.
import numpy as np

# after place + open_gripper + retract:
held_final, _, _ = get_object_pose(held, return_bbox_extent=False)
support_final, _, _ = get_object_pose(support, return_bbox_extent=False)
expected_z = support_final[2] + support_ext[2]/2 + held_ext[2]/2
xy_err = float(np.linalg.norm(held_final[:2] - support_final[:2]))
z_err = float(abs(held_final[2] - expected_z))
# surfaces in result_summary / stdout -> becomes real evidence in the trace
print('STACK_CHECK ok=%s xy_err=%.4f z_err=%.4f' % (xy_err < 0.02 and z_err < 0.01, xy_err, z_err))

# Grasp check, same idea: if the held object did not rise with the arm, we grabbed air.
# held_after_lift, _, _ = get_object_pose(held, return_bbox_extent=False)
# print('GRASP_CHECK', held_after_lift[2] - held_rest_z > 0.05)

## Provenance

robosuite/cube_stack dbg=1.00 val=1.00
