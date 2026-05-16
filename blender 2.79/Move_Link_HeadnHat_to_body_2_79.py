import bpy
import math

# Forward transform:
# Rotate Y: -90°, then X: 180°
# Translate by: +0.000001 X, +151.263 Y, +1.64705 Z

rot_x = math.radians(180)
rot_y = math.radians(-90)

for obj in bpy.context.selected_objects:
    # Ensure Euler XYZ rotation mode
    obj.rotation_mode = 'XYZ'

    # Store current rotation as Euler XYZ
    eul = obj.rotation_euler

    # Apply rotation in correct order: Y then X
    eul = mathutils.Euler((eul.x, eul.y + rot_y, eul.z), 'XYZ')
    eul = mathutils.Euler((eul.x + rot_x, eul.y, eul.z), 'XYZ')
    obj.rotation_euler = eul

    # Apply translation
    obj.location.x += 0.000001
    obj.location.y += 151.263
    obj.location.z += 1.64705

print("Correct forward transform applied (Blender 2.79).")
