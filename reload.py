import bpy
import importlib
import sys

class TzUtils_OT_reload_addon(bpy.types.Operator):
    bl_idname = "tzutils.reload_addon"
    bl_label = "Reload TzUtils"
    bl_description = "reload the addon!"

    def execute(self, context):
        modname = "TzUtils"
        if modname in sys.modules:
            mod = sys.modules[modname]
            try:
                importlib.reload(mod)
                mod.unregister()
                mod.register()
                self.report({'INFO'}, "TzUtils reloaded.")
            except Exception as e:
                self.report({'ERROR'}, f"Failed to reload: {e}")
                raise e
        else:
            self.report({'WARNING'}, "TzUtils module not found.")
        return {'FINISHED'}


class TzUtils_PT_reload_panel(bpy.types.Panel):
    bl_label = "TzUtils Dev"
    bl_idname = "TzUtils_PT_reload_panel"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'TzUtils'

    def draw(self, context):
        layout = self.layout
        layout.operator("tzutils.reload_addon", icon='FILE_REFRESH')

# standard register/unregister
classes = (
    TzUtils_OT_reload_addon,
    TzUtils_PT_reload_panel,
)

def register():
    for cls in classes:
        bpy.utils.register_class(cls)

def unregister():
    for cls in reversed(classes):
        try:
            bpy.utils.unregister_class(cls)
        except RuntimeError:
            # ignore if class not registered
            pass
