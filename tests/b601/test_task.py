from robot_b601.task import CubePose, FakeCubeLiftEnv

def _solve(env):
    ns = env.namespace()
    p = ns["get_cube_pose"]()
    ns["move_to_pose"](p.x, p.y, p.z + 0.10)
    ns["open_gripper"]()
    ns["move_to_pose"](p.x, p.y, p.z)
    ns["close_gripper"]()
    ns["move_to_pose"](p.x, p.y, p.z + 0.20)

def test_correct_sequence_lifts_cube():
    env = FakeCubeLiftEnv(); env.reset(0)
    _solve(env)
    assert env.success()

def test_noop_program_fails():
    env = FakeCubeLiftEnv(); env.reset(0)
    assert not env.success()

def test_grasp_requires_proximity():
    env = FakeCubeLiftEnv(grasp_tol=0.03); env.reset(0)
    ns = env.namespace(); p = ns["get_cube_pose"]()
    ns["move_to_pose"](p.x + 0.5, p.y, p.z)     # nowhere near the cube
    ns["close_gripper"]()
    ns["move_to_pose"](p.x + 0.5, p.y, p.z + 0.2)
    assert not env.success()                     # never grasped

def test_reset_is_seed_deterministic():
    a = FakeCubeLiftEnv(); a.reset(7)
    b = FakeCubeLiftEnv(); b.reset(7)
    c = FakeCubeLiftEnv(); c.reset(8)
    assert (a.cube.x, a.cube.y) == (b.cube.x, b.cube.y)
    assert (a.cube.x, a.cube.y) != (c.cube.x, c.cube.y)

def test_primitives_are_traced():
    env = FakeCubeLiftEnv(); env.reset(0)
    ns = env.namespace(); ns["get_cube_pose"](); ns["close_gripper"]()
    ts = env.traces()
    assert [t.function for t in ts] == ["get_cube_pose", "set_gripper"]
    assert all(t.status == "ok" for t in ts)
