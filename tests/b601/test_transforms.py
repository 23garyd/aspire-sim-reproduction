import numpy as np
from scipy.spatial.transform import Rotation
from robot_b601.transforms import make_transform, compose, invert, cube_base_pose


def _rigid(rng):
    R = Rotation.random(random_state=rng).as_matrix()
    t = rng.uniform(-0.5, 0.5, 3)
    return make_transform(R, t)


def test_invert_round_trips_to_identity():
    T = _rigid(np.random.RandomState(1))
    assert np.allclose(T @ invert(T), np.eye(4), atol=1e-9)
    assert np.allclose(invert(T) @ T, np.eye(4), atol=1e-9)


def test_compose_is_left_to_right_product():
    A = make_transform(np.eye(3), [1, 0, 0])
    B = make_transform(np.eye(3), [0, 2, 0])
    assert np.allclose(compose(A, B), A @ B)
    assert np.allclose(compose(A, B)[:3, 3], [1, 2, 0])


def test_cube_base_pose_pure_translation():
    # gripper at +1x in base, identity camera, cube 0.5 ahead of camera -> base (1,0,0.5)
    T_gripper_base = make_transform(np.eye(3), [1, 0, 0])
    T_cam_gripper = np.eye(4)
    T_cube_cam = make_transform(np.eye(3), [0, 0, 0.5])
    p = cube_base_pose(T_cube_cam, T_cam_gripper, T_gripper_base)
    assert np.allclose([p.x, p.y, p.z], [1, 0, 0.5], atol=1e-9)
    assert np.allclose([p.qx, p.qy, p.qz, p.qw], [0, 0, 0, 1], atol=1e-9)


def test_cube_base_pose_applies_rotation():
    # camera rotated +90deg about z in gripper; cube 0.5 along cam-x -> base y = +0.5
    Rz = Rotation.from_euler("z", 90, degrees=True).as_matrix()
    T_cam_gripper = make_transform(Rz, [0, 0, 0])
    T_cube_cam = make_transform(np.eye(3), [0.5, 0, 0])
    p = cube_base_pose(T_cube_cam, T_cam_gripper, np.eye(4))
    assert np.allclose([p.x, p.y, p.z], [0, 0.5, 0], atol=1e-9)
