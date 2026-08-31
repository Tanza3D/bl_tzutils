# mainly made for vrchat stuff, very specific for me, sorry
import bpy
import os
import numpy as np

from . import lightmap_uvs


class TzExportObjectSettings(bpy.types.PropertyGroup):
    skip_export: bpy.props.BoolProperty(
        name="Skip Export",
        description="Exclude this object from the FBX export",
        default=False,
    )
    skip_lightmap_rebake: bpy.props.BoolProperty(
        name="Skip Lightmap Rebake",
        description="Do not regenerate lightmap UVs for this object even if surface area grew",
        default=False,
    )
    skip_material_destruction: bpy.props.BoolProperty(
        name="Skip Material Destruction",
        description="Do not remap/strip materials on this object during export",
        default=False,
    )


class PT_TzExportObjectPanel(bpy.types.Panel):
    bl_label = "TzUtils Export"
    bl_idname = "TzUtils_PT_object_export"
    bl_space_type = 'PROPERTIES'
    bl_region_type = 'WINDOW'
    bl_context = 'object'

    @classmethod
    def poll(cls, context):
        return context.object is not None and context.object.type == 'MESH'

    def draw(self, context):
        obj = context.object
        s = obj.tz_export

        layout = self.layout
        layout.use_property_split = True
        layout.use_property_decorate = False

        prefix_skips = []
        if obj.name.startswith("EXCLUDE_"):
            prefix_skips.append("EXCLUDE_ prefix → skipped entirely")
        if obj.name.startswith("KP_"):
            prefix_skips.append("KP_ prefix → skipped entirely")

        if prefix_skips:
            box = layout.box()
            box.label(text="Prefix overrides active:", icon='INFO')
            for msg in prefix_skips:
                box.label(text=f"  {msg}")
            layout.separator()

        col = layout.column(align=True)

        row = col.row()
        row.prop(s, "skip_export")
        if obj.name.startswith("EXCLUDE_") or obj.name.startswith("KP_"):
            row.label(text="(forced by prefix)", icon='LOCKED')

        col.row().prop(s, "skip_lightmap_rebake")
        col.row().prop(s, "skip_material_destruction")


def _mesh_surface_area(obj):
    return sum(p.area for p in obj.data.polygons)


def _build_collection_excluded_set():
    excluded = set()

    def mark(col):
        if col.name in excluded:
            return
        if col.name.startswith("EXCLUDE_"):
            excluded.add(col.name)
        for child in col.children:
            mark(child)
            if child.name in excluded:
                excluded.add(col.name)

    for col in bpy.data.collections:
        mark(col)

    changed = True
    while changed:
        changed = False
        for col in bpy.data.collections:
            if col.name not in excluded:
                for child in col.children:
                    if child.name in excluded:
                        excluded.add(col.name)
                        changed = True
                        break

    return excluded


def _build_visible_name_set(context):
    return {obj.name for obj in context.view_layer.objects if obj.visible_get()}


def _is_excluded(obj, excluded_collections):
    if obj.name.startswith("EXCLUDE_"):
        return True
    for col in obj.users_collection:
        if col.name in excluded_collections:
            return True
    return False


def _should_skip_export(obj, excluded_collections):
    if obj.name.startswith("KP_"):
        return True
    if _is_excluded(obj, excluded_collections):
        return True
    return obj.tz_export.skip_export


def _should_skip_lightmap_rebake(obj):
    return obj.tz_export.skip_lightmap_rebake


def _should_skip_material_destruction(obj):
    return obj.tz_export.skip_material_destruction


def _eligible_meshes(context, excluded_collections, visible_names):
    for obj in context.scene.objects:
        if obj.type != 'MESH':
            continue
        if obj.name not in visible_names:
            continue
        if _is_excluded(obj, excluded_collections):
            continue
        yield obj


class OT_CustomFBXExporter(bpy.types.Operator):
    bl_idname = "export_scene.custom_fbx"
    bl_label = "Custom FBX Export"

    def execute(self, context):
        blend_path = bpy.data.filepath
        if not blend_path:
            self.report({'ERROR'}, "save the blend file first")
            return {'CANCELLED'}

        folder = os.path.dirname(blend_path)
        filename = os.path.splitext(os.path.basename(blend_path))[0]
        fbx_path = os.path.join(folder, filename + ".fbx")

        bpy.ops.wm.save_mainfile()

        try:
            excluded_collections = _build_collection_excluded_set()
            visible_names = _build_visible_name_set(context)

            for obj in _eligible_meshes(context, excluded_collections, visible_names):
                if _should_skip_export(obj, excluded_collections):
                    continue
                if _should_skip_material_destruction(obj):
                    continue

                mesh = obj.data

                kp_slots = {
                    i: mat for i, mat in enumerate(mesh.materials)
                    if mat and mat.name.startswith("KP_")
                }
                kp_mats = [kp_slots[i] for i in sorted(kp_slots.keys())]
                old_to_new = {
                    old_i: new_i
                    for new_i, old_i in enumerate(sorted(kp_slots.keys()))
                }

                n_polys = len(mesh.polygons)
                if n_polys > 0:
                    indices = np.empty(n_polys, dtype=np.int32)
                    mesh.polygons.foreach_get("material_index", indices)
                    remapped = np.vectorize(lambda x: old_to_new.get(x, 0))(indices)
                    mesh.polygons.foreach_set("material_index", remapped)

                for new_i, mat in enumerate(kp_mats):
                    if new_i < len(mesh.materials):
                        mesh.materials[new_i] = mat
                    else:
                        mesh.materials.append(mat)

                while len(mesh.materials) > len(kp_mats):
                    mesh.materials.pop(index=len(mesh.materials) - 1)

                keep = {"Oven", "automap"}
                to_remove = [
                    uv.name for uv in mesh.uv_layers
                    if uv.name not in keep and not uv.name.startswith("KP_")
                ]
                for name in to_remove:
                    mesh.uv_layers.remove(mesh.uv_layers[name])

                if "Oven" in mesh.uv_layers:
                    mesh.uv_layers.active = mesh.uv_layers["Oven"]
                elif mesh.uv_layers:
                    kp_uv = next(
                        (uv for uv in mesh.uv_layers if uv.name.startswith("KP_")),
                        None
                    )
                    if kp_uv:
                        mesh.uv_layers.active = kp_uv

            bpy.ops.export_scene.fbx(
                filepath=fbx_path,
                use_selection=False,
                apply_scale_options='FBX_SCALE_ALL',
                add_leaf_bones=False,
            )

        except Exception as e:
            self.report({'ERROR'}, f"export failed: {str(e)}")
            bpy.ops.wm.open_mainfile(filepath=blend_path)
            return {'CANCELLED'}

        bpy.ops.wm.open_mainfile(filepath=blend_path)
        self.report({'INFO'}, f"exported to {fbx_path}")
        return {'FINISHED'}


class OT_CustomFBXExporterWorld(bpy.types.Operator):
    bl_idname = "export_scene.custom_fbx_world"
    bl_label = "Custom FBX Export World"
    bl_description = "Apply modifiers, regenerate lightmap UVs for solidify objects, export FBX"

    def execute(self, context):
        blend_path = bpy.data.filepath
        if not blend_path:
            self.report({'ERROR'}, "save the blend file first")
            return {'CANCELLED'}

        folder = os.path.dirname(blend_path)
        filename = os.path.splitext(os.path.basename(blend_path))[0]
        fbx_path = os.path.join(folder, filename + ".fbx")

        bpy.ops.wm.save_mainfile()

        try:
            excluded_collections = _build_collection_excluded_set()
            visible_names = _build_visible_name_set(context)

            area_before = {}
            for obj in _eligible_meshes(context, excluded_collections, visible_names):
                if _should_skip_export(obj, excluded_collections):
                    continue
                if obj.modifiers:
                    area_before[obj.name] = _mesh_surface_area(obj)

            bpy.ops.object.select_all(action='DESELECT')
            active_set = False
            for obj in _eligible_meshes(context, excluded_collections, visible_names):
                if _should_skip_export(obj, excluded_collections):
                    continue
                if not obj.modifiers:
                    continue
                obj.select_set(True)
                if not active_set:
                    context.view_layer.objects.active = obj
                    active_set = True

            if active_set:
                bpy.ops.object.convert(target='MESH')
                bpy.ops.object.select_all(action='DESELECT')
                bpy.ops.outliner.orphans_purge(do_recursive=True)

            # rebake lightmap UVs on any object whose surface area changed
            # significantly (boolean ops can shrink area while still changing
            # topology, so check both directions not just growth).
            # delegates to lightmap_uvs.generate_lightmap_uv so this shares
            # the exact ordering that path needs (object active/selected
            # before uv_layers.active is set, or smart_project reads stale data)
            lightmap_uvs._updating = True
            try:
                for obj_name, before in area_before.items():
                    obj = bpy.data.objects.get(obj_name)
                    if obj is None:
                        continue
                    if obj.name not in visible_names:
                        continue
                    if obj.hide_select:
                        continue
                    if _should_skip_lightmap_rebake(obj):
                        continue
                    area_now = _mesh_surface_area(obj)
                    if before > 0 and abs(area_now - before) / before <= 0.001:
                        continue
                    try:
                        lightmap_uvs.generate_lightmap_uv(obj)
                        lightmap_uvs.mark_clean(obj)
                    except Exception as e:
                        self.report({'WARNING'}, f"lightmap UV failed on {obj.name}: {e}")
            finally:
                lightmap_uvs._updating = False

            bpy.ops.export_scene.fbx(
                filepath=fbx_path,
                use_selection=False,
                apply_scale_options='FBX_SCALE_ALL',
                add_leaf_bones=False,
            )

        except Exception as e:
            self.report({'ERROR'}, f"export failed: {str(e)}")
            bpy.ops.wm.open_mainfile(filepath=blend_path)
            return {'CANCELLED'}

        bpy.ops.wm.open_mainfile(filepath=blend_path)
        self.report({'INFO'}, f"exported world to {fbx_path}")
        return {'FINISHED'}


class PT_CustomExporterPanel(bpy.types.Panel):
    bl_label = "Custom FBX Export"
    bl_idname = "TzUtils_PT_custom_exporter"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'TzUtils'

    def draw(self, context):
        layout = self.layout

        box = layout.box()
        box.label(text="⚠ This will save your file before exporting", icon='ERROR')

        layout.operator("export_scene.custom_fbx")
        layout.separator()
        layout.operator("export_scene.custom_fbx_world")

        obj = context.object
        if obj and obj.type == 'MESH':
            layout.separator()
            box = layout.box()
            box.label(text=f"Selected: {obj.name}", icon='OBJECT_DATA')
            s = obj.tz_export
            col = box.column(align=True)
            col.prop(s, "skip_export")
            col.prop(s, "skip_lightmap_rebake")
            col.prop(s, "skip_material_destruction")


classes = (
    TzExportObjectSettings,
    PT_TzExportObjectPanel,
    OT_CustomFBXExporter,
    OT_CustomFBXExporterWorld,
    PT_CustomExporterPanel,
)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    bpy.types.Object.tz_export = bpy.props.PointerProperty(type=TzExportObjectSettings)


def unregister():
    try:
        del bpy.types.Object.tz_export
    except Exception:
        pass
    try:
        for cls in reversed(classes):
            bpy.utils.unregister_class(cls)
    except Exception:
        print("eh")
