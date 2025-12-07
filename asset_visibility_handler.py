# when saving a file, this saves a property in each collection of whether it should be hidden or not
# this is because when you append a collection into a file, it does not keep the visibility option of
# a collection, so this stores it separately and lets you "re-apply" it using the right click menu option

import bpy
from bpy.app.handlers import persistent

# ---------- UTILS ----------
def update_auto_hide_layer(layer_coll):
    coll = layer_coll.collection
    coll["auto_hide"] = layer_coll.exclude
    for child in layer_coll.children:
        update_auto_hide_layer(child)

def apply_auto_hide_layer(layer_coll):
    coll = layer_coll.collection
    if coll.get("auto_hide", False):
        layer_coll.exclude = True
    for child in layer_coll.children:
        apply_auto_hide_layer(child)

# ---------- OPERATOR ----------
class TZ_OT_apply_auto_hide(bpy.types.Operator):
    bl_idname = "tz.apply_auto_hide"
    bl_label = "Apply Auto Hide to This Collection"

    # property to store passed LayerCollection
    layer_collection: bpy.props.StringProperty()

    def execute(self, context):
        # get the LayerCollection from string path
        lc = context.view_layer.layer_collection
        path = self.layer_collection.split('|')
        for name in path[1:]:  # skip root
            lc = next(c for c in lc.children if c.name == name)
        apply_auto_hide_layer(lc)
        self.report({'INFO'}, f"Applied auto_hide to {lc.name} and children")
        return {'FINISHED'}

def outliner_menu(self, context):
    # get active layer collection from view layer
    lc = getattr(context.view_layer, "active_layer_collection", None)
    if not lc:
        return
    path = get_layer_collection_path(lc)
    self.layout.operator(
        TZ_OT_apply_auto_hide.bl_idname,
        text="Apply Auto Hide"
    ).layer_collection = path

def get_layer_collection_path(layer_coll):
    # start from the view layer root
    root = bpy.context.view_layer.layer_collection
    path = []

    def find_path(lc, target, current_path):
        if lc == target:
            path.extend(current_path + [lc.name])
            return True
        for child in lc.children:
            if find_path(child, target, current_path + [lc.name]):
                return True
        return False

    find_path(root, layer_coll, [])
    return '|'.join(path)


# ---------- HANDLERS ----------
@persistent
def on_save(dummy):
    lc = bpy.context.view_layer.layer_collection
    update_auto_hide_layer(lc)
    print("asset_visibility_handler: auto_hide updated on save")

# ---------- REGISTER ----------
classes = (TZ_OT_apply_auto_hide,)

def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    bpy.types.OUTLINER_MT_collection.append(outliner_menu)

    bpy.app.handlers.save_pre[:] = [h for h in bpy.app.handlers.save_pre if getattr(h, "__name__", "") != "on_save"]
    bpy.app.handlers.save_pre.append(on_save)
    print("asset_visibility_handler registered")

def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
    bpy.types.OUTLINER_MT_collection.remove(outliner_menu)
    bpy.app.handlers.save_pre[:] = [h for h in bpy.app.handlers.save_pre if h != on_save]
    print("asset_visibility_handler unregistered")
