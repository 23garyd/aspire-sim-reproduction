"""RobotEngine: the agent-facing ASPIRE API. Every primitive is @traced.

This is the only robot object placed in the agent's namespace (the ground-truth
wall). It delegates motion to the AimdkNode sync facade; perception/grasp/IK are
injected collaborators (SAM3/Molmo, GraspNet, cuRobo) added in later cycles.

Only move_to_joints is implemented so far — built test-first alongside the facade.
"""
from __future__ import annotations

from robot_engine.tracing import trace


class RobotEngine:
    def __init__(self, node, log, camera=None):
        self._node = node
        self._log = log
        self._cam = camera

    def _capture_keyframe(self, step: int, when: str) -> bool:
        # No camera wired in this cycle -> nothing saved. CameraClient lands with
        # get_observation (pending the CameraInfo/TF verification).
        if self._cam is None:
            return False
        return self._cam.save_keyframe(self._log, step, when)

    @trace
    def move_to_joints(self, joints, tol: float = 1e-3, timeout_s: float = 5.0):
        return self._node.move_to_joints(joints, tol=tol, timeout_s=timeout_s)
