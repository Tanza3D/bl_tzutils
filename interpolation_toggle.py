import bpy

INTERPOLATION_TYPES = [
    ('CONSTANT', "Constant", ""),
    ('LINEAR', "Linear", ""),
    ('BEZIER', "Bezier", ""),
    ('SINE', "Sine", ""),
    ('QUAD', "Quadratic", ""),
    ('CUBIC', "Cubic", ""),
    ('QUART', "Quartic", ""),
    ('QUINT', "Quintic", ""),
    ('EXPO', "Exponential", ""),
    ('CIRC', "Circular", ""),
    ('BACK', "Back", ""),
    ('BOUNCE', "Bounce", ""),
    ('ELASTIC', "Elastic", ""),
]

class TZ_OT_set_interpolation(bpy.types.Operator):
    bl_idname = "tz.set_interpolation"
    bl_label = "Set Interpolation"
    bl_description = "Set keyframe interpolation mode"
    bl_options = {'REGISTER', 'UNDO'}

    mode: bpy.props.EnumProperty(
        name="Interpolation",
        description="Choose keyframe interpolation mode",
        items=INTERPOLATION_TYPES
    )

    def execute(self, context):
        context.preferences.edit.keyframe_new_interpolation_type = self.mode
        self.report({'INFO'}, f"Set interpolation to: {self.mode}")
        return {'FINISHED'}

def draw_interpolation_dropdown(self, context):
    layout = self.layout
    layout.label(text="Interp:")
    layout.operator_menu_enum("tz.set_interpolation", "mode", text=context.preferences.edit.keyframe_new_interpolation_type.title())

def register():
    bpy.utils.register_class(TZ_OT_set_interpolation)
    for header in (
        bpy.types.DOPESHEET_HT_header,
        bpy.types.GRAPH_HT_header,
        bpy.types.NLA_HT_header,
    ):
        header.append(draw_interpolation_dropdown)

def unregister():
    try: 
        bpy.utils.unregister_class(TZ_OT_set_interpolation)
        for header in (
            bpy.types.DOPESHEET_HT_header,
            bpy.types.GRAPH_HT_header,
            bpy.types.NLA_HT_header,
        ):
            header.remove(draw_interpolation_dropdown)
    except:
        print("eh")
