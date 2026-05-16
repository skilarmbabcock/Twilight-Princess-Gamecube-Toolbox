import bpy
import math
import mathutils

# Define the forward transform matrix (rotate then translate)
rot_x = math.radians(180)
rot_y = math.radians(-90)

rot_x_mat = mathutils.Matrix.Rotation(rot_x, 4, 'X')
rot_y_mat = mathutils.Matrix.Rotation(rot_y, 4, 'Y')

# Multiply rotation matrices (order: X then Y)
rotation_mat = rot_y_mat * rot_x_mat  # Use * for matrix multiplication in 2.79

translation_vec = mathutils.Vector((0.000001, 151.263, 1.64705))

transform_mat = mathutils.Matrix.Translation(translation_vec) * rotation_mat

inverse_transform = transform_mat.inverted()

for obj in bpy.context.selected_objects:
    # Apply inverse transform to the object's matrix_world
    obj.matrix_world = inverse_transform * obj.matrix_world

print("Applied inverse transform around pivot at origin to selected objects.")
