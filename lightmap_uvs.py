import bpy
from bpy.app.handlers import persistent

PROP = "tz_uvsModified"
UV_NAME = "Lightmap"

_updating = False  # guard so the depsgraph handler doesn't re-dirty during UV gen


def mark_dirty(obj):
    obj[PROP] = 1


def mark_clean(obj):
    obj[PROP] = 0


def is_dirty(obj):
    return obj.get(PROP, 1) == 1


def generate_lightmap_uv(obj):
    mesh = obj.data

    if UV_NAME not in mesh.uv_layers:
        mesh.uv_layers.new(name=UV_NAME)

    prev_active_idx = mesh.uv_layers.active_index
    prev_selected = obj.select_get()
    prev_active_obj = bpy.context.view_layer.objects.active

    for o in bpy.context.view_layer.objects:
        o.select_set(False)

    bpy.context.view_layer.objects.active = obj
    obj.select_set(True)

    # object must be active before setting active_index, or smart_project
    # reads active_index off the stale evaluated depsgraph object
    lm_idx = mesh.uv_layers.find(UV_NAME)
    mesh.uv_layers.active_index = lm_idx

    bpy.ops.object.mode_set(mode='EDIT')
    bpy.ops.mesh.select_all(action='SELECT')
    bpy.ops.uv.smart_project(
        angle_limit=1.15192,  # ~66 degrees
        island_margin=0.02,
        correct_aspect=True,
    )
    bpy.ops.object.mode_set(mode='OBJECT')

    mesh.uv_layers.active_index = prev_active_idx
    obj.select_set(prev_selected)
    bpy.context.view_layer.objects.active = prev_active_obj


class TzUtils_OT_update_lightmap_uvs(bpy.types.Operator):
    bl_idname = "tzutils.update_lightmap_uvs"
    bl_label = "Update Lightmap UVs"
    bl_description = "Regenerate lightmap UVs for all dirty mesh objects in the file"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        global _updating

        orig_active = context.view_layer.objects.active
        orig_selected = [o for o in context.selected_objects]
        orig_mode = context.mode

        if orig_mode != 'OBJECT':
            bpy.ops.object.mode_set(mode='OBJECT')

        for o in context.selected_objects:
            o.select_set(False)

        updated = 0
        skipped = 0

        _updating = True
        try:
            for obj in bpy.data.objects:
                if obj.type != 'MESH':
                    continue
                if not obj.visible_get():
                    continue
                if not is_dirty(obj):
                    skipped += 1
                    continue
                try:
                    generate_lightmap_uv(obj)
                    mark_clean(obj)
                    updated += 1
                except Exception as e:
                    self.report({'WARNING'}, f"Failed on {obj.name}: {e}")
        finally:
            _updating = False

        for o in context.view_layer.objects:
            o.select_set(o in orig_selected)
        if orig_active:
            context.view_layer.objects.active = orig_active

        if orig_mode != 'OBJECT' and orig_active:
            mode_map = {
                'EDIT_MESH': 'EDIT', 'EDIT_CURVE': 'EDIT',
                'EDIT_SURFACE': 'EDIT', 'EDIT_ARMATURE': 'EDIT',
                'EDIT_METABALL': 'EDIT', 'EDIT_LATTICE': 'EDIT',
                'SCULPT': 'SCULPT', 'PAINT_WEIGHT': 'WEIGHT_PAINT',
                'PAINT_VERTEX': 'VERTEX_PAINT', 'PAINT_TEXTURE': 'TEXTURE_PAINT',
                'POSE': 'POSE',
            }
            restore_mode = mode_map.get(orig_mode, orig_mode)
            try:
                bpy.ops.object.mode_set(mode=restore_mode)
            except:
                pass

        self.report({'INFO'}, f"Lightmap UVs: {updated} updated, {skipped} skipped (clean)")
        return {'FINISHED'}


class TzUtils_OT_force_lightmap_uvs(bpy.types.Operator):
    bl_idname = "tzutils.force_lightmap_uvs"
    bl_label = "Force Update All"
    bl_description = "Mark all mesh objects as dirty and regenerate lightmap UVs"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        for obj in bpy.data.objects:
            if obj.type == 'MESH':
                mark_dirty(obj)
        return bpy.ops.tzutils.update_lightmap_uvs()


class TzUtils_OT_unwrap_selected(bpy.types.Operator):
    bl_idname = "tzutils.unwrap_selected"
    bl_label = "Unwrap Selected"
    bl_description = "Force-regenerate lightmap UVs for all selected mesh objects"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        targets = [o for o in context.selected_objects if o.type == 'MESH']
        if not targets:
            self.report({'WARNING'}, "No mesh objects selected")
            return {'CANCELLED'}

        global _updating
        _updating = True
        try:
            for obj in targets:
                try:
                    generate_lightmap_uv(obj)
                    mark_clean(obj)
                except Exception as e:
                    self.report({'WARNING'}, f"Failed on {obj.name}: {e}")
        finally:
            _updating = False

        self.report({'INFO'}, f"Lightmap UVs unwrapped for {len(targets)} object(s)")
        return {'FINISHED'}


class TzUtils_PT_lightmap_uvs_panel(bpy.types.Panel):
    bl_label = "Lightmap UVs"
    bl_idname = "TzUtils_PT_lightmap_uvs_panel"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'TzUtils'

    def draw(self, context):
        layout = self.layout

        layout.operator("tzutils.update_lightmap_uvs", icon='UV')
        layout.operator("tzutils.force_lightmap_uvs", icon='FILE_REFRESH')
        layout.operator("tzutils.unwrap_selected", icon='UV_SYNC_SELECT')

        obj = context.active_object
        if obj and obj.type == 'MESH':
            box = layout.box()
            dirty = is_dirty(obj)
            box.label(
                text=f"{obj.name}: {'needs update' if dirty else 'clean'}",
                icon='ERROR' if dirty else 'CHECKMARK'
            )


_tracked_hashes = {}


@persistent
def _on_depsgraph_update(scene, depsgraph):
    if _updating:
        return

    for update in depsgraph.updates:
        if not isinstance(update.id, bpy.types.Object):
            continue
        obj = update.id
        if obj.type != 'MESH':
            continue
        if not update.is_updated_geometry:
            continue
        mark_dirty(obj)


@persistent
def _on_load_post(dummy):
    _tracked_hashes.clear()


classes = (
    TzUtils_OT_update_lightmap_uvs,
    TzUtils_OT_force_lightmap_uvs,
    TzUtils_OT_unwrap_selected,
    TzUtils_PT_lightmap_uvs_panel,
)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)

    if _on_depsgraph_update not in bpy.app.handlers.depsgraph_update_post:
        bpy.app.handlers.depsgraph_update_post.append(_on_depsgraph_update)
    if _on_load_post not in bpy.app.handlers.load_post:
        bpy.app.handlers.load_post.append(_on_load_post)


def unregister():
    if _on_depsgraph_update in bpy.app.handlers.depsgraph_update_post:
        bpy.app.handlers.depsgraph_update_post.remove(_on_depsgraph_update)
    if _on_load_post in bpy.app.handlers.load_post:
        bpy.app.handlers.load_post.remove(_on_load_post)

    for cls in reversed(classes):
        try:
            bpy.utils.unregister_class(cls)
        except RuntimeError:
            pass
