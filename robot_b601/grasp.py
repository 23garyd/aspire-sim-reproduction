"""Proprioceptive grasp + lift evaluation for the B601 real cube-lift (M3c). Pure; no
hardware. Grasp is inferred from the gripper stalling open on an object; lift from the
end-effector height (both read from real feedback on-bench, from the fake model in CI)."""
from __future__ import annotations


def grasp_detected(gripper_pos, closed_ref, min_object_open) -> bool:
    """True if, after a commanded close, the gripper stalled open by at least
    min_object_open above the fully-closed reference -- i.e. an object is between the
    fingers. A gripper that reaches (near) closed_ref grasped nothing."""
    return (float(gripper_pos) - float(closed_ref)) >= float(min_object_open)


def lifted(ee_z, lift_threshold) -> bool:
    return float(ee_z) > float(lift_threshold)


def cube_lift_success(grasped, ee_z, lift_threshold) -> bool:
    return bool(grasped) and lifted(ee_z, lift_threshold)
