from robot_b601.task import RealCubeLiftEnv, FakeCubePerception, CubePose
from robot_b601.motion import FakeMotionBackend
from robot_b601.limits import GripperLimits


def _env(cube=(0.40, 0.0, 0.02)):
    c = CubePose(*cube)
    motion = FakeMotionBackend(gripper_limits=GripperLimits(0.0, 0.08),
                               object_xyz=cube, object_width=0.03, grasp_tol=0.03)
    return RealCubeLiftEnv(motion, FakeCubePerception(c), lift_threshold=0.10,
                           closed_ref=0.0, min_object_open=0.01,
                           close_pos=0.0, open_pos=0.08), c


def _run(env, ns):
    """A correct reach->grasp->lift program against the primitive namespace."""
    c = ns["get_cube_pose"]()
    ns["open_gripper"]()
    ns["move_to_pose"](c.x, c.y, c.z + 0.10)
    ns["move_to_pose"](c.x, c.y, c.z)
    ns["close_gripper"]()
    ns["move_to_pose"](c.x, c.y, c.z + 0.15)


def test_correct_program_lifts():
    env, _ = _env()
    env.reset(0)
    _run(env, env.namespace())
    assert env.success() is True


def test_noop_program_fails():
    env, _ = _env()
    env.reset(0)
    env.namespace()["get_cube_pose"]()          # perceive only, never move/grasp
    assert env.success() is False


def test_close_far_from_cube_does_not_grasp():
    env, c = _env()
    env.reset(0)
    ns = env.namespace()
    ns["move_to_pose"](0.0, 0.0, 0.30)          # nowhere near the cube
    ns["close_gripper"]()
    ns["move_to_pose"](0.0, 0.0, 0.30)
    assert env.success() is False               # gripper fully closed -> no grasp


def test_set_gripper_over_limit_is_clamped_no_crash():
    env, _ = _env()
    env.reset(0)
    env.namespace()["set_gripper"](0.5)         # over-open -> clamped by the backend
    assert env.motion.gripper_position() == 0.08


def test_primitives_emit_traces():
    env, _ = _env()
    env.reset(0)
    _run(env, env.namespace())
    fns = [t.function for t in env.traces()]
    assert "get_cube_pose" in fns and "move_to_pose" in fns and "set_gripper" in fns


def test_reset_clears_state_between_seeds():
    env, _ = _env()
    env.reset(0)
    _run(env, env.namespace())
    assert env.success() is True
    env.reset(1)                                # fresh seed: grasp + traces cleared, EE homed
    assert env.success() is False and env.traces() == []
