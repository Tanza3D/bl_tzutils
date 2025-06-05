import bpy
import re
from bpy.props import StringProperty, FloatProperty, BoolProperty, CollectionProperty, PointerProperty

class QVG_Settings(bpy.types.PropertyGroup):
    match: StringProperty(name="Match", default=".*")
    weight: FloatProperty(name="Weight", min=0.0, max=1.0, default=1.0)
    show_vgroups: BoolProperty(name="Show Vertex Groups", default=False)
    show_dangerous: BoolProperty(name="Show Dangerous", default=False)

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

        text = "Valid Regex"

        if valid:
            text = "Valid Regex"
        else:
            text = "Invalid Regex"

        # collapsible box for vertex groups list
        box = layout.box()
        row = box.row()
        row.prop(qvg, "show_vgroups", icon="TRIA_DOWN" if qvg.show_vgroups else "TRIA_RIGHT", emboss=False, text=text)

        if qvg.show_vgroups and obj:
            for vg in obj.vertex_groups:
                matched = False
                if valid:
                    matched = pattern.fullmatch(vg.name) is not None
                icon = 'CHECKMARK' if matched else 'X'
                box.label(text=vg.name, icon=icon)
                

        layout.prop(qvg, "weight", slider=True)

        row = layout.row()
        row.operator("qvg.set_weight", text="Set")
        row.operator("qvg.remove_weight", text="Remove")

        layout.separator()
        layout.separator()

        row2 = layout.row()
        icon = "ERROR"
        row2.prop(qvg, "show_dangerous", icon="TRIA_DOWN" if qvg.show_dangerous else "TRIA_RIGHT", emboss=False, text="Dangerous Operations")
        row2.label(text="", icon=icon)

        if qvg.show_dangerous and obj:
            row = layout.row()
            row.alert = True
            row.operator("qvg.delete", text="Delete", icon='ERROR')

class QVG_OT_delete(bpy.types.Operator):
    bl_idname = "qvg.delete"
    bl_label = "Delete Vertex Groups"

    def execute(self, context):
        obj = context.object
        if obj.mode != 'OBJECT':
            self.report({'WARNING'}, "Must be in Object mode")
            return {'CANCELLED'}
        
        qvg = context.scene.qvg_settings
        try:
            pattern = re.compile(qvg.match)
        except:
            self.report({'ERROR'}, "Invalid regex pattern")
            return {'CANCELLED'}
        
        to_delete = [vg for vg in obj.vertex_groups if pattern.fullmatch(vg.name)]
        for vg in to_delete:
            obj.vertex_groups.remove(vg)
        
        return {'FINISHED'}


class QVG_OT_set_weight(bpy.types.Operator):
    bl_idname = "qvg.set_weight"
    bl_label = "Set Vertex Weight"

    def execute(self, context):
        obj = context.object
        if obj.mode != 'EDIT':
            self.report({'WARNING'}, "Must be in Edit mode")
            return {'CANCELLED'}

        qvg = context.scene.qvg_settings
        try:
            pattern = re.compile(qvg.match)
        except:
            self.report({'ERROR'}, "Invalid regex pattern")
            return {'CANCELLED'}
        weight = qvg.weight

        bpy.ops.object.mode_set(mode='OBJECT')
        for v in obj.data.vertices:
            if not v.select:
                continue
            for vg in obj.vertex_groups:
                if pattern.fullmatch(vg.name):
                    vg.add([v.index], weight, 'REPLACE')
        bpy.ops.object.mode_set(mode='EDIT')
        return {'FINISHED'}

class QVG_OT_remove_weight(bpy.types.Operator):
    bl_idname = "qvg.remove_weight"
    bl_label = "Remove Vertex Weight"

    def execute(self, context):
        obj = context.object
        if obj.mode != 'EDIT':
            self.report({'WARNING'}, "Must be in Edit mode")
            return {'CANCELLED'}

        qvg = context.scene.qvg_settings
        try:
            pattern = re.compile(qvg.match)
        except:
            self.report({'ERROR'}, "Invalid regex pattern")
            return {'CANCELLED'}

        bpy.ops.object.mode_set(mode='OBJECT')
        for v in obj.data.vertices:
            if not v.select:
                continue
            for vg in obj.vertex_groups:
                if pattern.fullmatch(vg.name):
                    vg.remove([v.index])
        bpy.ops.object.mode_set(mode='EDIT')
        return {'FINISHED'}

classes = (
    QVG_Settings,
    QVG_PT_panel,
    QVG_OT_set_weight,
    QVG_OT_remove_weight,
    QVG_OT_delete,
)

def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    bpy.types.Scene.qvg_settings = bpy.props.PointerProperty(type=QVG_Settings)

def unregister():
    for cls in reversed(classes):
        try:
            bpy.utils.unregister_class(cls)
        except RuntimeError:
            pass
    del bpy.types.Scene.qvg_settings
