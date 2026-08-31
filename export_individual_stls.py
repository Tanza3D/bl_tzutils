# exports all visible mesh objects as individual STL files into timestamped folders
import bpy
import os
import shutil
from datetime import datetime


def _find_layer_collection(layer_col, target_name):
    if layer_col.collection.name == target_name:
        return layer_col
    for child in layer_col.children:
        found = _find_layer_collection(child, target_name)
        if found:
            return found
    return None


def _get_layer_collection_path(layer_col, target_name, path=None):
    if path is None:
        path = []
    if layer_col.collection.name == target_name:
        return path, layer_col.exclude
    for child in layer_col.children:
        result = _get_layer_collection_path(child, target_name, path + [layer_col.collection.name])
        if result is not None:
            child_path, child_excluded = result
            return child_path, (child_excluded or layer_col.exclude)
    return None


def _get_object_collection_name(obj):
    for col in bpy.data.collections:
        if obj.name in col.objects:
            return col.name
    return None


class TzUtils_OT_export_individual_stls(bpy.types.Operator):
    """Export all visible objects as individual STL files"""
    bl_idname = "export_mesh.tz_individual_stls"
    bl_label = "Export Individual STLs"
    bl_description = "Export all visible mesh objects as individual STL files into timestamped folders"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        blend_path = bpy.path.abspath("//")
        if not blend_path:
            self.report({'ERROR'}, "Save your .blend file first!")
            return {'CANCELLED'}

        timestamp = datetime.now().strftime("%y-%m-%d_%H-%M")
        base_export_path = os.path.join(blend_path, "exports", timestamp)
        latest_export_path = os.path.join(blend_path, "exports", "latest")

        if os.path.exists(latest_export_path):
            shutil.rmtree(latest_export_path)

        original_selection = context.selected_objects.copy()
        original_active = context.view_layer.objects.active

        root_layer_col = context.view_layer.layer_collection

        objects_to_export = []
        skipped_hidden = 0
        skipped_excluded = 0
        skipped_nx = 0

        for obj in context.view_layer.objects:
            if obj.type != 'MESH':
                continue
            if obj.name.startswith("NX"):
                skipped_nx += 1
                continue
            if obj.hide_render or obj.hide_get():
                skipped_hidden += 1
                continue

            col_name = _get_object_collection_name(obj)
            if col_name:
                result = _get_layer_collection_path(root_layer_col, col_name)
                if result and result[1]:
                    skipped_excluded += 1
                    continue

            objects_to_export.append(obj)

        exported_count = 0

        for obj in objects_to_export:
            col_name = _get_object_collection_name(obj)
            col_path = ""
            if col_name:
                result = _get_layer_collection_path(root_layer_col, col_name)
                if result:
                    path_parts, _ = result
                    col_path = "/".join(path_parts + [col_name])

            if col_path:
                export_dir = os.path.join(base_export_path, col_path)
                latest_dir = os.path.join(latest_export_path, col_path)
            else:
                export_dir = base_export_path
                latest_dir = latest_export_path

            os.makedirs(export_dir, exist_ok=True)
            os.makedirs(latest_dir, exist_ok=True)

            safe_name = bpy.path.clean_name(obj.name)
            filepath = os.path.join(export_dir, f"{safe_name}.stl")
            latest_filepath = os.path.join(latest_dir, f"{safe_name}.stl")

            for o in context.view_layer.objects:
                o.select_set(False)

            obj.select_set(True)
            context.view_layer.objects.active = obj
            context.view_layer.update()

            try:
                bpy.ops.wm.stl_export(
                    filepath=filepath,
                    export_selected_objects=True,
                    apply_modifiers=True
                )
            except AttributeError:
                bpy.ops.export_mesh.stl(
                    filepath=filepath,
                    use_selection=True,
                    use_mesh_modifiers=True
                )

            shutil.copy2(filepath, latest_filepath)
            exported_count += 1

        for o in context.view_layer.objects:
            o.select_set(o in original_selection)
        context.view_layer.objects.active = original_active

        self.report(
            {'INFO'},
            f"Exported {exported_count} STLs (skipped {skipped_hidden} hidden, "
            f"{skipped_excluded} in excluded collections, {skipped_nx} NX_) "
            f"to exports/{timestamp}/ and exports/latest/"
        )
        return {'FINISHED'}


def menu_func_export(self, context):
    self.layout.operator(TzUtils_OT_export_individual_stls.bl_idname, text="Export Individual STLs")


class TzUtils_PT_export_individual_stls(bpy.types.Panel):
    bl_label = "Export Individual STLs"
    bl_idname = "TzUtils_PT_export_individual_stls"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'TzUtils'

    def draw(self, context):
        layout = self.layout
        layout.operator(TzUtils_OT_export_individual_stls.bl_idname, text="Export STLs", icon='EXPORT')


classes = (
    TzUtils_OT_export_individual_stls,
    TzUtils_PT_export_individual_stls,
)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    bpy.types.TOPBAR_MT_file_export.append(menu_func_export)


def unregister():
    bpy.types.TOPBAR_MT_file_export.remove(menu_func_export)
    for cls in reversed(classes):
        try:
            bpy.utils.unregister_class(cls)
        except RuntimeError:
            pass
