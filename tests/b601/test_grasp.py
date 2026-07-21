from robot_b601.grasp import grasp_detected, lifted, cube_lift_success


def test_grasp_detected_when_gripper_stalls_open():
    # closed_ref 0.0, need >= 0.01 open to count as an object; gripper stalled at 0.03
    assert grasp_detected(0.03, closed_ref=0.0, min_object_open=0.01) is True


def test_no_grasp_when_gripper_fully_closes():
    assert grasp_detected(0.0, closed_ref=0.0, min_object_open=0.01) is False
    assert grasp_detected(0.005, closed_ref=0.0, min_object_open=0.01) is False


def test_lifted_threshold():
    assert lifted(0.17, 0.10) is True
    assert lifted(0.05, 0.10) is False


def test_cube_lift_success_needs_both():
    assert cube_lift_success(True, 0.17, 0.10) is True
    assert cube_lift_success(False, 0.17, 0.10) is False    # not grasped
    assert cube_lift_success(True, 0.05, 0.10) is False     # not lifted
