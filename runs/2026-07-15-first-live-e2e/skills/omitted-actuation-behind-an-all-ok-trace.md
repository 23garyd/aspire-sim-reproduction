# omitted-actuation-behind-an-all-ok-trace

category: diagnosis

## Failure signature

Every primitive returns [ok], the summary reports FAILURES: 0, yet the task is not accomplished and the target object's pose is unchanged between the first and last keyframe. Perception, grasp sampling and IK all look healthy in isolation, and no parameter looks wrong because no primitive complained.

## When to apply

Any manipulation task whose trace shows no failed primitive but no object motion either: pick-and-place, stacking, insertion, put-in-container, drawer/door opening. Reach for this BEFORE re-tuning perception prompts, grasp poses or approach heights: a zero-failure trace actively misdirects toward those, because every primitive that did run really did work. The tell is that the failure is in an action that was never requested, not in one that errored.

## Strategy

Stop triaging by status and triage by causal chain. Write down the primitives the task REQUIRES, then diff that list against the primitives the trace actually CONTAINS. A silent no-op episode is usually an omitted actuation primitive (close before transport, open before release, a missing lift) rather than a mis-parameterised one. Confirm by pairing the keyframe at the moment of the supposed state change against the object's pose: if the arm is at the lift height and the object is still on the table, the transport is carrying nothing. Before adding the missing call, verify the primitive's NAME against an evidenced source (an existing call in the program, the skill library, or a prior trace); guessing a name converts a silent no-op into a hard NameError and regresses below baseline. Here open_gripper() was attested in the baseline and close_gripper() was only inferred from its existence, which was correctly flagged as the top risk and then confirmed to resolve on replay.

## Code sketch

# Trace shows:    sample_grasp_pose -> goto_pose(grasp) -> goto_pose(lift) -> open_gripper
# Task requires:  sample_grasp_pose -> goto_pose(grasp) -> CLOSE -> goto_pose(lift) -> open_gripper
#                                                          ^^^^^ absent from trace, never errored
pick_pos, pick_quat = sample_grasp_pose(obj)
open_gripper()                        # ensure fingers are open before the approach
goto_pose(pick_pos, pick_quat, z_approach=0.1)
close_gripper()                       # the omitted link in the causal chain
lift = pick_pos.copy(); lift[2] += 0.2
goto_pose(lift, pick_quat)

## Provenance

robosuite/cube_stack dbg=1.00 val=1.00
