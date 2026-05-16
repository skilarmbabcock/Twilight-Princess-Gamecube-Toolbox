bl_info = { 
    "name": "Link Autobuild Tool",
    "author": "ChatGPT (adapted for you)",
    "version": (1, 0, 2),
    "blender": (3, 0, 0),
    "location": "View3D > Sidebar > Link Tools",
    "description": "Import 3 DAE files into collections, clear transforms, unparent meshes; apply Edit Ready or Export Ready transforms; optimize weights; export DAE with texture copy and suffix cleanup.",
    "category": "Import-Export",
}

import bpy
from mathutils import Euler, Vector
import os
import re

COLLECTIONS = {"al", "al_head", "al_face"}

ASSEMBLED_OFFSETS = {
    "al": (Vector((0, 0, 0)), Euler((1.5708, 0, 0), 'XYZ')),
    "al_head": (Vector((0.000001, -1.64706, 151.263)), Euler((-1.5708, 0, -1.5708), 'XYZ')),
    "al_face": (Vector((0.000001, -1.64706, 151.263)), Euler((-1.5708, 0, -1.5708), 'XYZ')),
}

EXPORT_READY_OFFSETS = {
    "al": (Vector((0, 0, 0)), Euler((-1.5708, 0, 0), 'XYZ')),
    "al_head": (Vector((-1.64705, 151.263, 0.000012)), Euler((1.5708, -1.5708, 0), 'XYZ')),
    "al_face": (Vector((-1.64705, 151.263, 0.000012)), Euler((1.5708, -1.5708, 0), 'XYZ')),
}

def apply_offset_transform(obj, offset_loc, offset_rot):
    new_loc = obj.location + offset_loc
    new_rot = (obj.rotation_euler.to_matrix() @ offset_rot.to_matrix()).to_euler()
    obj.location = new_loc
    obj.rotation_euler = new_rot
    bpy.context.view_layer.objects.active = obj
    obj.select_set(True)
    bpy.ops.object.transform_apply(location=True, rotation=True, scale=False)
    obj.select_set(False)

def apply_transform_set(offsets):
    for obj in bpy.data.objects:
        if obj.users_collection and obj.users_collection[0].name in COLLECTIONS:
            col_name = obj.users_collection[0].name
            offset_loc, offset_rot = offsets[col_name]
            apply_offset_transform(obj, offset_loc, offset_rot)

class OBJECT_OT_apply_assembled(bpy.types.Operator):
    bl_idname = "object.apply_assembled"
    bl_label = "Edit Ready"
    bl_description = "Apply assembled transform to objects"

    def execute(self, context):
        apply_transform_set(ASSEMBLED_OFFSETS)
        self.report({'INFO'}, "Applied Assembled (Edit Ready) Transform")
        return {'FINISHED'}

class OBJECT_OT_apply_export_ready(bpy.types.Operator):
    bl_idname = "object.apply_export_ready"
    bl_label = "Export Ready"
    bl_description = "Apply export-ready transform to objects"

    def execute(self, context):
        apply_transform_set(EXPORT_READY_OFFSETS)
        self.report({'INFO'}, "Applied Export Ready Transform")
        return {'FINISHED'}

class OBJECT_OT_import_all_dae(bpy.types.Operator):
    bl_idname = "object.import_all_dae"
    bl_label = "Import All DAEs"
    bl_description = "Import the three DAE files into their collections, clear transforms, unparent meshes"

    def execute(self, context):
        scene = context.scene
        paths = {
            "al": scene.linktool_al_path,
            "al_head": scene.linktool_al_head_path,
            "al_face": scene.linktool_al_face_path,
        }

        for col_name, path in paths.items():
            if path and os.path.isfile(bpy.path.abspath(path)):
                bpy.ops.wm.collada_import(
                    filepath=bpy.path.abspath(path),
                    keep_bind_info=True,
                    import_units=True,
                )

                imported_objs = [obj for obj in context.selected_objects if obj.type in {'MESH', 'ARMATURE'}]

                if col_name not in bpy.data.collections:
                    new_col = bpy.data.collections.new(col_name)
                    bpy.context.scene.collection.children.link(new_col)
                else:
                    new_col = bpy.data.collections[col_name]

                for obj in imported_objs:
                    for c in obj.users_collection:
                        c.objects.unlink(obj)
                    new_col.objects.link(obj)

                for obj in imported_objs:
                    obj.location = (0, 0, 0)
                    obj.rotation_euler = (0, 0, 0)
                    obj.scale = (1, 1, 1)

                for obj in imported_objs:
                    if obj.type == 'MESH' and obj.parent:
                        obj.parent = None
                        obj.matrix_parent_inverse.identity()

        self.report({'INFO'}, "Imported all DAEs and prepared objects")
        return {'FINISHED'}

def quantize_weight(value, steps):
    step_size = 1.0 / steps
    return round(value / step_size) * step_size

def optimize_weights_on_object(obj, steps):
    if obj.type != 'MESH':
        return

    mesh = obj.data

    if not obj.vertex_groups:
        return

    for v in mesh.vertices:
        groups = v.groups

        if not groups:
            continue

        weights = [(g.group, g.weight) for g in groups]

        quantized = []
        for g_index, weight in weights:
            q = quantize_weight(weight, steps)
            q = min(max(q, 0.0), 1.0)
            quantized.append((g_index, q))

        total = sum(w for _, w in quantized)
        if total == 0:
            equal_weight = 1.0 / len(quantized)
            quantized = [(g_index, equal_weight) for g_index, _ in quantized]
        else:
            quantized = [(g_index, w / total) for g_index, w in quantized]

        for g_index, w in quantized:
            vg = obj.vertex_groups[g_index]
            vg.add([v.index], w, 'REPLACE')

class OBJECT_OT_optimize_weights(bpy.types.Operator):
    bl_idname = "object.optimize_weights"
    bl_label = "Optimize Weights"
    bl_description = "Clamp and normalize vertex weights on visible meshes"

    steps: bpy.props.EnumProperty(
        name="Quantize Steps",
        description="How finely to quantize weights",
        items=[
            ('4', "Lowest Quality (4 steps)", "Most optimized, lowest quality"),
            ('10', "Balanced (10 steps)", "Balanced quality and optimization"),
            ('25', "Highest Quality (25 steps)", "Least optimized, highest quality"),
        ],
        default='10',
    )

    def execute(self, context):
        steps = int(self.steps)
        for obj in bpy.data.objects:
            if obj.visible_get() and obj.type == 'MESH':
                optimize_weights_on_object(obj, steps)

        self.report({'INFO'}, f"Optimized weights using {steps} quantize steps")
        return {'FINISHED'}

def export_collection_dae(collection_name: str, export_path: str, copy_textures: bool):
    if not export_path or not os.path.isdir(os.path.dirname(bpy.path.abspath(export_path))):
        return f"Invalid export path for collection '{collection_name}': {export_path}"

    abs_path = bpy.path.abspath(export_path)
    coll = bpy.data.collections.get(collection_name)
    if not coll:
        return f"Collection '{collection_name}' not found."

    all_objects = list(bpy.data.objects)
    backup_vis = {obj: obj.hide_get() for obj in all_objects}
    backup_sel = {obj: obj.select_get() for obj in all_objects}
    backup_active = bpy.context.view_layer.objects.active

    try:
        # Hide all and deselect all first
        for obj in all_objects:
            obj.hide_set(True)
            obj.select_set(False)

        skeletons = [obj for obj in coll.objects if obj.type == 'ARMATURE']
        meshes = [obj for obj in coll.objects if obj.type == 'MESH']

        if skeletons:
            for skel in skeletons:
                # Save original names
                orig_name = skel.name
                orig_data_name = skel.data.name if skel.data else None

                # Rename skeleton to fixed name
                skel.name = "skeleton_root"
                if skel.data:
                    skel.data.name = "skeleton_root"

                # Hide all skeletons except current
                for other_skel in skeletons:
                    if other_skel != skel:
                        other_skel.hide_set(True)
                        other_skel.select_set(False)

                # Show current skeleton and all meshes
                skel.hide_set(False)
                skel.select_set(True)
                for m in meshes:
                    m.hide_set(False)
                    m.select_set(True)

                bpy.context.view_layer.objects.active = skel

                bpy.ops.wm.collada_export(
                    filepath=abs_path,
                    selected=True,
                    export_mesh_type=0,
                    sort_by_name=True,
                    use_texture_copies=copy_textures,
                )

                # Restore original names
                skel.name = orig_name
                if skel.data and orig_data_name:
                    skel.data.name = orig_data_name

                # Restore skeleton visibility/selection to hidden/deselected after export
                skel.hide_set(True)
                skel.select_set(False)

            # After exporting all skeletons, unhide all objects again
            for obj in coll.objects:
                obj.hide_set(False)
                obj.select_set(False)
        else:
            # No skeletons, export whole collection at once
            for obj in coll.objects:
                obj.hide_set(False)
                obj.select_set(True)

            bpy.ops.wm.collada_export(
                filepath=abs_path,
                selected=True,
                export_mesh_type=0,
                sort_by_name=True,
                use_texture_copies=copy_textures,
            )

            for obj in coll.objects:
                obj.hide_set(False)
                obj.select_set(False)

    except Exception as e:
        return f"Export failed for collection '{collection_name}': {e}"
    finally:
        for obj in all_objects:
            obj.hide_set(backup_vis[obj])
            obj.select_set(backup_sel[obj])
        bpy.context.view_layer.objects.active = backup_active

    return None

class OBJECT_OT_export_link_all(bpy.types.Operator):
    bl_idname = "object.export_link_all"
    bl_label = "Export Link"
    bl_description = "Export collections sequentially with export-ready transforms and visibility management"

    def execute(self, context):
        scene = context.scene
        copy_textures = getattr(scene, "linktool_copy_textures", False)

        body_path = getattr(scene, "linktool_export_body_path", "")
        head_path = getattr(scene, "linktool_export_head_path", "")
        face_path = getattr(scene, "linktool_export_face_path", "")

        # === Rename any existing skeleton_root to skeleton_root.123 once per export ===
        renamed_original = None
        for col_name in COLLECTIONS:
            col = bpy.data.collections.get(col_name)
            if not col:
                continue
            for obj in col.objects:
                if obj.type == 'ARMATURE' and obj.name == "skeleton_root":
                    # Rename to skeleton_root.123 to free name
                    obj.name = "skeleton_root.123"
                    if obj.data:
                        obj.data.name = "skeleton_root.123"
                    renamed_original = obj
                    # Unhide all since it'll all be fine after it starts the export process
                    for o in bpy.data.objects:
                        o.hide_set(False)
                    # Only rename first found, then break out
                    break
            if renamed_original:
                break

        collections_order = [("al", body_path), ("al_face", face_path), ("al_head", head_path)]

        bpy.ops.object.apply_export_ready()

        all_collections = [c for c in bpy.data.collections if c.name in COLLECTIONS]

        errors = []
        exported_ok = []

        # Hide all collections initially
        for col in all_collections:
            col.hide_viewport = True

        for col_name, path in collections_order:
            if not path:
                errors.append(f"Missing export path for collection '{col_name}'")
                continue

            # Show only the current collection
            for col in all_collections:
                col.hide_viewport = (col.name != col_name)

            err = export_collection_dae(col_name, path, copy_textures)
            if err:
                errors.append(err)
            else:
                exported_ok.append(col_name)

        # Unhide all collections after export
        for col in all_collections:
            col.hide_viewport = False

        bpy.ops.object.apply_assembled()

        # Restore original skeleton_root name if it was renamed
        if renamed_original:
            renamed_original.name = "skeleton_root"
            if renamed_original.data:
                renamed_original.data.name = "skeleton_root"

        if errors:
            if exported_ok:
                self.report({'INFO'}, "Exported successfully: " + ", ".join(exported_ok))
            self.report({'ERROR'}, " ; ".join(errors))
            return {'CANCELLED'}

        self.report({'INFO'}, "Exported all collections successfully with visibility toggling and transform simulation")
        return {'FINISHED'}

class VIEW3D_PT_link_transform_tools_panel(bpy.types.Panel):
    bl_label = "Link Autobuild Tool"
    bl_idname = "VIEW3D_PT_link_autobuild_tool"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "Link Tools"

    def draw(self, context):
        layout = self.layout
        scene = context.scene

        col = layout.column(align=True)
        col.label(text="DAE Import Paths:")
        col.prop(scene, "linktool_al_path", text="al.dae")
        col.prop(scene, "linktool_al_head_path", text="al_head.dae")
        col.prop(scene, "linktool_al_face_path", text="al_face.dae")

        layout.operator("object.import_all_dae", icon='IMPORT')

        layout.separator()

        layout.operator("object.apply_assembled", icon='MOD_ARMATURE')
        layout.operator("object.apply_export_ready", icon='EXPORT')

        layout.separator()

        layout.prop(scene, "optimize_weights_steps", text="Optimize Weights Steps")
        op = layout.operator("object.optimize_weights", icon='AUTOMERGE_ON')
        op.steps = scene.optimize_weights_steps

        layout.separator()

        layout.label(text="Link's DAE Export Paths:")
        layout.prop(scene, "linktool_export_body_path", text="Body DAE Path")
        layout.prop(scene, "linktool_export_head_path", text="Head DAE Path")
        layout.prop(scene, "linktool_export_face_path", text="Face DAE Path")
        layout.prop(scene, "linktool_copy_textures", text="Copy Textures")

        layout.operator("object.export_link_all", icon='EXPORT', text="Export Link")

classes = (
    OBJECT_OT_apply_assembled,
    OBJECT_OT_apply_export_ready,
    OBJECT_OT_import_all_dae,
    OBJECT_OT_optimize_weights,
    OBJECT_OT_export_link_all,
    VIEW3D_PT_link_transform_tools_panel,
)

def register():
    for cls in classes:
        bpy.utils.register_class(cls)

    bpy.types.Scene.linktool_al_path = bpy.props.StringProperty(
        name="al.dae Path",
        subtype='FILE_PATH',
    )
    bpy.types.Scene.linktool_al_head_path = bpy.props.StringProperty(
        name="al_head.dae Path",
        subtype='FILE_PATH',
    )
    bpy.types.Scene.linktool_al_face_path = bpy.props.StringProperty(
        name="al_face.dae Path",
        subtype='FILE_PATH',
    )

    bpy.types.Scene.optimize_weights_steps = bpy.props.EnumProperty(
        name="Optimize Weights Steps",
        description="Quantize steps for weight optimization",
        items=[
            ('4', "Lowest Quality (4 steps)", "Most optimized, lowest quality"),
            ('10', "Balanced (10 steps)", "Balanced quality and optimization"),
            ('25', "Highest Quality (25 steps)", "Least optimized, highest quality"),
        ],
        default='10',
    )

    bpy.types.Scene.linktool_export_body_path = bpy.props.StringProperty(
        name="Body Export Path",
        subtype='FILE_PATH',
    )
    bpy.types.Scene.linktool_export_head_path = bpy.props.StringProperty(
        name="Head Export Path",
        subtype='FILE_PATH',
    )
    bpy.types.Scene.linktool_export_face_path = bpy.props.StringProperty(
        name="Face Export Path",
        subtype='FILE_PATH',
    )
    bpy.types.Scene.linktool_copy_textures = bpy.props.BoolProperty(
        name="Copy Textures",
        default=False,
    )

def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)

    del bpy.types.Scene.linktool_al_path
    del bpy.types.Scene.linktool_al_head_path
    del bpy.types.Scene.linktool_al_face_path
    del bpy.types.Scene.optimize_weights_steps

    del bpy.types.Scene.linktool_export_body_path
    del bpy.types.Scene.linktool_export_head_path
    del bpy.types.Scene.linktool_export_face_path
    del bpy.types.Scene.linktool_copy_textures

if __name__ == "__main__":
    register()


# =========================
# Sword Sheath Transforms
# =========================
from math import radians

SHEATH_EXPORT_LOC = Vector((-18.8604, 0.992325, 12.1794))

# === ONLY CHANGE: set angle to exactly 33.0 degrees (and inverse to -33.0) ===
SHEATH_EXPORT_ROT = Euler((0.0, radians(33.0), 0.0), 'XYZ')
SHEATH_EDIT_LOC = Vector((18.8604, -0.992325, -12.1794))
SHEATH_EDIT_ROT = Euler((0.0, radians(-33.0), 0.0), 'XYZ')
# === END ONLY CHANGE ===

def _apply_sheath_transform_to_selection(context, offset_loc: Vector, offset_rot: Euler, two_stage_apply: bool = False):
    sel = list(context.selected_objects)
    if not sel:
        return False, "No objects selected. Select the sword sheath objects first."

    for obj in sel:
        context.view_layer.objects.active = obj
        obj.select_set(True)

        if two_stage_apply:
            # Step 1: move, apply LOCATION only
            obj.location = obj.location + offset_loc
            bpy.ops.object.transform_apply(location=True, rotation=False, scale=False)

            # Step 2: rotate, apply ROTATION only
            obj.rotation_euler = (obj.rotation_euler.to_matrix() @ offset_rot.to_matrix()).to_euler()
            bpy.ops.object.transform_apply(location=False, rotation=True, scale=False)
        else:
            # Original behavior: move+rotate then apply both
            obj.location = obj.location + offset_loc
            obj.rotation_euler = (obj.rotation_euler.to_matrix() @ offset_rot.to_matrix()).to_euler()
            bpy.ops.object.transform_apply(location=True, rotation=True, scale=False)

        obj.select_set(False)

    return True, "Applied Sword Sheath transform to selected objects."

class OBJECT_OT_sheath_edit_ready(bpy.types.Operator):
    bl_idname = "object.sheath_edit_ready"
    bl_label = "Sheath Edit Ready"
    bl_description = "Apply Sword Sheath Edit Ready transform (reverse of Export Ready) to selected objects"

    def execute(self, context):
        ok, msg = _apply_sheath_transform_to_selection(context, SHEATH_EDIT_LOC, SHEATH_EDIT_ROT, two_stage_apply=True)
        if not ok:
            self.report({'ERROR'}, msg)
            return {'CANCELLED'}
        self.report({'INFO'}, "Applied Sheath Edit Ready Transform")
        return {'FINISHED'}

class OBJECT_OT_sheath_export_ready(bpy.types.Operator):
    bl_idname = "object.sheath_export_ready"
    bl_label = "Sheath Export Ready"
    bl_description = "Apply Sword Sheath Export Ready transform to selected objects"

    def execute(self, context):
        ok, msg = _apply_sheath_transform_to_selection(context, SHEATH_EXPORT_LOC, SHEATH_EXPORT_ROT)
        if not ok:
            self.report({'ERROR'}, msg)
            return {'CANCELLED'}
        self.report({'INFO'}, "Applied Sheath Export Ready Transform")
        return {'FINISHED'}

class VIEW3D_PT_sword_sheath_transforms(bpy.types.Panel):
    bl_label = "Sword Sheath Transforms"
    bl_idname = "VIEW3D_PT_sword_sheath_transforms"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "Link Tools"
    bl_parent_id = "VIEW3D_PT_link_autobuild_tool"

    def draw(self, context):
        layout = self.layout
        col = layout.column(align=True)
        col.operator("object.sheath_edit_ready", icon='MOD_ARMATURE')
        col.operator("object.sheath_export_ready", icon='EXPORT')

_sheath_extra_classes = (
    OBJECT_OT_sheath_edit_ready,
    OBJECT_OT_sheath_export_ready,
    VIEW3D_PT_sword_sheath_transforms,
)

_old_register = register
_old_unregister = unregister

def register():
    _old_register()
    for cls in _sheath_extra_classes:
        bpy.utils.register_class(cls)

def unregister():
    for cls in reversed(_sheath_extra_classes):
        bpy.utils.unregister_class(cls)
    _old_unregister()

# === CRITICAL FIX FOR "Run Script" IN TEXT EDITOR ===
if __name__ == "__main__":
    for cls in _sheath_extra_classes:
        try:
            bpy.utils.register_class(cls)
        except Exception:
            pass


# =========================
# Misc
# =========================

class OBJECT_OT_clear_mesh_transforms(bpy.types.Operator):
    bl_idname = "object.clear_mesh_transforms"
    bl_label = "Clear Transforms"
    bl_description = "Set Location/Rotation to zero and Scale to 1 for every VISIBLE mesh/armature (does not apply transforms)"

    def execute(self, context):
        for obj in bpy.data.objects:
            if not obj.visible_get():
                continue
            if obj.type not in {'MESH', 'ARMATURE'}:
                continue

            obj.location = (0.0, 0.0, 0.0)
            obj.rotation_euler = (0.0, 0.0, 0.0)
            obj.scale = (1.0, 1.0, 1.0)

        self.report({'INFO'}, "Cleared transforms on all visible meshes + armatures (set, not applied)")
        return {'FINISHED'}


# === ONLY ADDITION IN YOUR REQUEST: Apply Modifiers button (includes Armature) ===
class OBJECT_OT_apply_all_modifiers(bpy.types.Operator):
    bl_idname = "object.apply_all_modifiers"
    bl_label = "Apply Modifiers"
    bl_description = "Apply ALL modifiers on every mesh, including Armature"

    def execute(self, context):
        # Ensure Object Mode
        if context.mode != 'OBJECT':
            try:
                bpy.ops.object.mode_set(mode='OBJECT')
            except Exception:
                pass

        view_layer = context.view_layer
        prev_active = view_layer.objects.active

        applied = 0
        failed = 0

        for obj in bpy.data.objects:
            if obj.type != 'MESH':
                continue

            view_layer.objects.active = obj
            obj.select_set(True)

            for mod in list(obj.modifiers):
                try:
                    bpy.ops.object.modifier_apply(modifier=mod.name)
                    applied += 1
                except Exception:
                    failed += 1

            obj.select_set(False)

        view_layer.objects.active = prev_active

        self.report({'INFO'}, f"Applied {applied} modifiers (including Armature). Failed: {failed}.")
        return {'FINISHED'}
# === END ONLY ADDITION ===


class VIEW3D_PT_misc_tools(bpy.types.Panel):
    bl_label = "Misc"
    bl_idname = "VIEW3D_PT_misc_tools"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "Link Tools"
    bl_parent_id = "VIEW3D_PT_link_autobuild_tool"

    def draw(self, context):
        layout = self.layout
        layout.operator("object.clear_mesh_transforms", icon='X')
        layout.operator("object.apply_all_modifiers", icon='MODIFIER')


_misc_extra_classes = (
    OBJECT_OT_clear_mesh_transforms,
    OBJECT_OT_apply_all_modifiers,
    VIEW3D_PT_misc_tools,
)

_old_register_2 = register
_old_unregister_2 = unregister

def register():
    _old_register_2()
    for cls in _misc_extra_classes:
        bpy.utils.register_class(cls)

def unregister():
    for cls in reversed(_misc_extra_classes):
        bpy.utils.unregister_class(cls)
    _old_unregister_2()

# Register immediately when running from Text Editor, same reason as sheath section.
if __name__ == "__main__":
    for cls in _misc_extra_classes:
        try:
            bpy.utils.register_class(cls)
        except Exception:
            pass
