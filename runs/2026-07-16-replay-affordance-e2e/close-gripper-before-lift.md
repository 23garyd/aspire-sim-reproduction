# close-gripper-before-lift

category: grasping

## Failure signature

A pick-transport-place program reaches the sampled grasp pose and then immediately moves to a lift/transport pose, but the target object never moves (it stays on the surface). Diagnostic tell: all primitives report status 'ok' and the trace shows FAILURES: 0, yet task reward is 0 — a silent broken-causal-chain failure rather than a primitive error, because no gripper-closing primitive was issued between the descent-to-grasp and the lift.

## When to apply

Any manipulation task whose code contains sample_grasp_pose(obj) -> goto_pose(grasp) -> goto_pose(lift-or-transport) with no close_gripper() (or equivalent grasp-securing primitive) between reaching the grasp pose and the first lifting/transport motion. Especially suspect this when every primitive is 'ok'/zero FAILURES but reward is 0.

## Strategy

Insert a single close_gripper() call immediately after the goto_pose that reaches the sampled grasp pose and before any lift/transport goto_pose, so the object is secured before it is moved. Confirm the repair from the trace: the post-lift keyframe should show the object rising with the gripper rather than remaining on the surface, and get_object_pose on the target after the lift should report a raised z. Do not diagnose from the sim handle or asset files — read only observations and rendered keyframes.

## Code sketch

pick_pos, pick_quat = sample_grasp_pose(obj)
goto_pose(pick_pos, pick_quat, z_approach=0.1)
close_gripper()  # secure the object before lifting; omitting this yields a silent 'air pick'
lift = pick_pos.copy(); lift[2] += 0.2
goto_pose(lift, pick_quat)

## Provenance

robosuite/cube_stack dbg=1.00 val=0.60
