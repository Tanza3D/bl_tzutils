import bpy
import re
from bpy.props import StringProperty, FloatProperty, BoolProperty, PointerProperty

class QVG_Settings(bpy.types.PropertyGroup):
    match: StringProperty(name="Match", default=".*")
    weight: FloatProperty(name="Weight", min=0.0, max=1.0, default=1.0)
    show_vgroups: BoolProperty(name="Show Vertex Groups", default=False)
    invert: BoolProperty(name="Invert Selection", default=False)

class QVG_PT_panel(bpy.types.Panel):
    bl_label = "TZU/Vertex Groups"
    bl_idname = "QVG_PT_panel"
    bl_space_type = 'PROPERTIES'
    bl_region_type = 'WINDOW'
    bl_context = "data"
    bl_parent_id = "DATA_PT_vertex_groups"

    @classmethod
    def poll(cls, context):
        return context.object and context.object.type == 'MESH'

    def draw(self, context):
        layout = self.layout
        qvg = context.scene.qvg_settings
        obj = context.object

        layout.prop(qvg, "match")

        try:
            pattern = re.compile(qvg.match)
            valid = True
        except:
            valid = False

        text = "Valid Regex" if valid else "Invalid Regex"

        box = layout.box()
        row = box.row()
        row.prop(qvg, "show_vgroups", icon="TRIA_DOWN" if qvg.show_vgroups else "TRIA_RIGHT", emboss=False, text=text)

        if qvg.show_vgroups and obj:
            for vg in obj.vertex_groups:
                matched = False
                if valid:
                    matched = pattern.fullmatch(vg.name) is not None
                    if qvg.invert:
                        matched = not matched
                icon = 'CHECKMARK' if matched else 'X'
                box.label(text=vg.name, icon=icon)

        layout.prop(qvg, "weight", slider=True)
        
        layout.separator()
        
        layout.prop(qvg, "invert")
        
        # mode-dependent buttons
        if obj.mode == 'EDIT':
            row = layout.row()
            row.operator("qvg.set_weight", text="Set")
            row.operator("qvg.remove_weight", text="Remove")
        else:  # object mode
            row = layout.row()
            row.alert = True
            row.operator("qvg.delete", text="Delete", icon='ERROR')
            layout.separator()
            layout.operator("qvg.mirror_weights", text="Mirror Weights R → L", icon='MOD_MIRROR')

class QVG_OT_delete(bpy.types.Operator):
    bl_idname = "qvg.delete"
    bl_label = "Delete Vertex Groups"
    alt: BoolProperty(default=False)

    def invoke(self, context, event):
        self.alt = event.alt
        return self.execute(context)

    def execute(self, context):
        objs = [context.object]
        if self.alt:
            objs = [o for o in context.selected_objects if o.type == 'MESH']

        qvg = context.scene.qvg_settings
        try:
            pattern = re.compile(qvg.match)
        except:
            self.report({'ERROR'}, "Invalid regex pattern")
            return {'CANCELLED'}

        for obj in objs:
            if obj.mode != 'OBJECT':
                self.report({'WARNING'}, f"{obj.name} must be in Object mode")
                continue
            to_delete = []
            for vg in obj.vertex_groups:
                matched = pattern.fullmatch(vg.name) is not None
                if qvg.invert:
                    matched = not matched
                if matched:
                    to_delete.append(vg)
            for vg in to_delete:
                obj.vertex_groups.remove(vg)

        return {'FINISHED'}

class QVG_OT_set_weight(bpy.types.Operator):
    bl_idname = "qvg.set_weight"
    bl_label = "Set Vertex Weight"

    def execute(self, context):
        obj = context.object
        qvg = context.scene.qvg_settings
        
        try:
            pattern = re.compile(qvg.match)
        except:
            self.report({'ERROR'}, "Invalid regex pattern")
            return {'CANCELLED'}

        if obj.mode != 'EDIT':
            self.report({'WARNING'}, f"{obj.name} must be in Edit mode")
            return {'CANCELLED'}

        bpy.ops.object.mode_set(mode='OBJECT')
        for v in obj.data.vertices:
            if not v.select:
                continue
            for vg in obj.vertex_groups:
                matched = pattern.fullmatch(vg.name) is not None
                if qvg.invert:
                    matched = not matched
                if matched:
                    vg.add([v.index], qvg.weight, 'REPLACE')
        bpy.ops.object.mode_set(mode='EDIT')

        return {'FINISHED'}

class QVG_OT_mirror_weights(bpy.types.Operator):
    bl_idname = "qvg.mirror_weights"
    bl_label = "Mirror Weights R -> L"
    bl_description = "Copy all .R vertex group weights to their .L counterparts, using X axis mirror. Works with or without trailing number suffix."

    def execute(self, context):
        obj = context.object
        if not obj or obj.type != 'MESH':
            self.report({'ERROR'}, "No mesh object selected")
            return {'CANCELLED'}

        mesh = obj.data
        vgroups = obj.vertex_groups

        qvg = context.scene.qvg_settings
        try:
            pattern = re.compile(qvg.match)
        except:
            self.report({'ERROR'}, "Invalid regex pattern")
            return {'CANCELLED'}

        def is_matched(name):
            result = pattern.fullmatch(name) is not None
            return not result if qvg.invert else result

        # build a map of R group name -> L group name, filtered by match
        pairs = {}
        for vg in vgroups:
            if not is_matched(vg.name):
                continue
            # matches e.g. DEF-mouth.bottom.R.010 or DEF-mouth.bottom.R
            m = re.match(r'^(.*?)\.R(\.\d+)?$', vg.name)
            if m:
                prefix = m.group(1)
                suffix = m.group(2) or ''
                l_name = f"{prefix}.L{suffix}"
                if l_name in vgroups:
                    pairs[vg.name] = l_name

        if not pairs:
            self.report({'WARNING'}, "No matching .R / .L group pairs found")
            return {'CANCELLED'}

        # build per-vertex weight lookup for all R groups
        # structure: {r_group_name: {vert_index: weight}}
        r_weights = {r: {} for r in pairs}
        for v in mesh.vertices:
            for ge in v.groups:
                vg = vgroups[ge.group]
                if vg.name in r_weights:
                    r_weights[vg.name][v.index] = ge.weight

        # mirror: find each vertex's X-mirrored counterpart and copy weight
        # build a spatial lookup: position -> vertex index
        from mathutils import Vector

        pos_map = {}
        for v in mesh.vertices:
            key = (round(v.co.x, 4), round(v.co.y, 4), round(v.co.z, 4))
            pos_map[key] = v.index

        mirrored = 0
        for r_name, l_name in pairs.items():
            l_vg = vgroups[l_name]
            # clear existing L weights first
            l_vg.remove([v.index for v in mesh.vertices])
            for vi, w in r_weights[r_name].items():
                co = mesh.vertices[vi].co
                # look up the mirrored position (flip X)
                mirror_key = (round(-co.x, 4), round(co.y, 4), round(co.z, 4))
                if mirror_key in pos_map:
                    l_vg.add([pos_map[mirror_key]], w, 'REPLACE')
                    mirrored += 1

        self.report({'INFO'}, f"Mirrored {len(pairs)} group pair(s), {mirrored} weight(s) copied")
        return {'FINISHED'}


class QVG_OT_remove_weight(bpy.types.Operator):
    bl_idname = "qvg.remove_weight"
    bl_label = "Remove Vertex Weight"

    def execute(self, context):
        obj = context.object
        qvg = context.scene.qvg_settings
        
        try:
            pattern = re.compile(qvg.match)
        except:
            self.report({'ERROR'}, "Invalid regex pattern")
            return {'CANCELLED'}

        if obj.mode != 'EDIT':
            self.report({'WARNING'}, f"{obj.name} must be in Edit mode")
            return {'CANCELLED'}

        bpy.ops.object.mode_set(mode='OBJECT')
        for v in obj.data.vertices:
            if not v.select:
                continue
            for vg in obj.vertex_groups:
                matched = pattern.fullmatch(vg.name) is not None
                if qvg.invert:
                    matched = not matched
                if matched:
                    vg.remove([v.index])
        bpy.ops.object.mode_set(mode='EDIT')

        return {'FINISHED'}

classes = (
    QVG_Settings,
    QVG_PT_panel,
    QVG_OT_set_weight,
    QVG_OT_remove_weight,
    QVG_OT_delete,
    QVG_OT_mirror_weights,
)

def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    bpy.types.Scene.qvg_settings = PointerProperty(type=QVG_Settings)

def unregister():
    for cls in reversed(classes):
        try:
            bpy.utils.unregister_class(cls)
        except RuntimeError:
            pass
    del bpy.types.Scene.qvg_settings
