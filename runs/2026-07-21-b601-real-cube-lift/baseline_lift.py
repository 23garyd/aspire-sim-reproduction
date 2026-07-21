# Correct B601 cube-lift baseline: perceive -> approach -> descend -> grasp -> lift.
c = get_cube_pose()
open_gripper()
move_to_pose(c.x, c.y, c.z + 0.10)
move_to_pose(c.x, c.y, c.z)
close_gripper()
move_to_pose(c.x, c.y, c.z + 0.15)
