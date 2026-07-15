from aspire.audit import audit_code


def test_clean_code_passes():
    assert audit_code("pos = get_robot_position()\nnavigate_to_pose([1, 2, 0.5])") == []


def test_forbidden_sim_handle_flagged():
    v = audit_code("q = env.handle.env.sim.data.qpos")
    assert any("env.handle.env.sim" in x for x in v)


def test_reading_asset_files_flagged():
    for fname in ("scene.xml", "task.bddl", "robot.urdf"):
        v = audit_code(f"data = open('{fname}').read()")
        assert v, f"{fname} should be flagged"


def test_seed_specific_branch_flagged():
    v = audit_code("if seed == 3:\n    target_z = 0.91")
    assert any("seed" in x for x in v)


def test_seed_word_in_comment_ok():
    assert audit_code("# works across seeds\nx = 1") == []
