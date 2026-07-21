# FAILING B601 cube-lift baseline: closes the gripper at the APPROACH pose, above the
# cube, without ever descending to it -- so it grasps air and lifts nothing. The bug the
# ASPIRE repair actor must fix (add the descend to cube.z before closing).
c = get_cube_pose()
open_gripper()
move_to_pose(c.x, c.y, c.z + 0.10)     # approach ABOVE the cube
close_gripper()                         # BUG: grasps air -- never descended to c.z
move_to_pose(c.x, c.y, c.z + 0.15)      # "lifts" nothing
