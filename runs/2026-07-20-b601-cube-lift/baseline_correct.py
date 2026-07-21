# A correct cube-lift baseline program (privileged perception). Scores 1.0 in
# FakeCubeLiftEnv; used by the M2 pipeline-integration test as a passing baseline.
p = get_cube_pose()
move_to_pose(p.x, p.y, p.z + 0.10)   # approach above the cube
open_gripper()
move_to_pose(p.x, p.y, p.z)          # descend to the cube
close_gripper()                       # grasp
move_to_pose(p.x, p.y, p.z + 0.20)   # lift above the threshold
