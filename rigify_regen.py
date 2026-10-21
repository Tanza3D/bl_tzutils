import bpy


def is_metarig(obj):
    if obj is None or obj.type != 'ARMATURE':
        return False

    # generated rigs carry a rig_id, metarigs don't
    if "rig_id" in obj.data:
        return False

    if obj.pose is None:
        return False

    for pbone in obj.pose.bones:
        if getattr(pbone, "rigify_type", ""):
            return True

    return False


class TZ_OT_rigify_regenerate(bpy.types.Operator):
    bl_idname = "tz.rigify_regenerate"
    bl_label = "Regenerate Rig"
    bl_description = "Regenerate the rigify rig from the selected metarig"

    @classmethod
    def poll(cls, context):
        return is_metarig(context.active_object)

    def execute(self, context):
        if not hasattr(bpy.ops.pose, "rigify_generate"):
            self.report({'ERROR'}, "rigify isn't enabled")
            return {'CANCELLED'}

        bpy.ops.pose.rigify_generate()
        self.report({'INFO'}, "rig regenerated")
        return {'FINISHED'}


def draw_header_button(self, context):
    if not is_metarig(context.active_object):
        return

    self.layout.operator("tz.rigify_regenerate", text="", icon='OUTLINER_OB_ARMATURE')


classes = (
    TZ_OT_rigify_regenerate,
)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    bpy.types.VIEW3D_HT_header.append(draw_header_button)


def unregister():
    bpy.types.VIEW3D_HT_header.remove(draw_header_button)
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
