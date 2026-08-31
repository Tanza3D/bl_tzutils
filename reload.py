import bpy
import importlib
import sys

def _do_reload():
    modname = "TzUtils"
    if modname not in sys.modules:
        print("TzUtils module not found.")
        return
    mod = sys.modules[modname]
    try:
        mod.unregister()
        importlib.reload(mod)
        mod.register()
        print("TzUtils reloaded.")
    except Exception as e:
        print(f"Failed to reload TzUtils: {e}")

class TzUtils_OT_reload_addon(bpy.types.Operator):
    bl_idname = "tzutils.reload_addon"
    bl_label = "Reload TzUtils"
    bl_description = "reload the addon!"

    def execute(self, context):
        # deferred so this operator (defined inside the module being
        # reloaded) isn't unregistered while it's still executing
        bpy.app.timers.register(_do_reload, first_interval=0.0)
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
            pass
