import bpy
from bpy.props import BoolProperty

PROXY_KEY = "tzu_lattice_src"

addon_keymaps = []


def lattice_index(u, v, w, pu, pv):
    # blender orders lattice points u fastest, then v, then w
    return u + v * pu + w * pu * pv


def build_faces(pu, pv, pw):
    faces = []
    # uv planes
    for w in range(pw):
        for v in range(pv - 1):
            for u in range(pu - 1):
                faces.append((
                    lattice_index(u, v, w, pu, pv),
                    lattice_index(u + 1, v, w, pu, pv),
                    lattice_index(u + 1, v + 1, w, pu, pv),
                    lattice_index(u, v + 1, w, pu, pv),
                ))
    # uw planes
    for v in range(pv):
        for w in range(pw - 1):
            for u in range(pu - 1):
                faces.append((
                    lattice_index(u, v, w, pu, pv),
                    lattice_index(u + 1, v, w, pu, pv),
                    lattice_index(u + 1, v, w + 1, pu, pv),
                    lattice_index(u, v, w + 1, pu, pv),
                ))
    # vw planes
    for u in range(pu):
        for w in range(pw - 1):
            for v in range(pv - 1):
                faces.append((
                    lattice_index(u, v, w, pu, pv),
                    lattice_index(u, v + 1, w, pu, pv),
                    lattice_index(u, v + 1, w + 1, pu, pv),
                    lattice_index(u, v, w + 1, pu, pv),
                ))
    return faces


def find_armature(lattice_obj):
    for mod in lattice_obj.modifiers:
        if mod.type == 'ARMATURE' and mod.object:
            return mod.object
    if lattice_obj.parent and lattice_obj.parent.type == 'ARMATURE':
        return lattice_obj.parent
    return None


def make_proxy(context, lat_obj, copy_existing=True):
    lat = lat_obj.data
    pu, pv, pw = lat.points_u, lat.points_v, lat.points_w

    verts = [p.co_deform.copy() for p in lat.points]
    faces = build_faces(pu, pv, pw)

    mesh = bpy.data.meshes.new(f"{lat_obj.name}_weights")
    mesh.from_pydata(verts, [], faces)
    mesh.update()

    proxy = bpy.data.objects.new(f"{lat_obj.name}_weights", mesh)
    proxy.matrix_world = lat_obj.matrix_world.copy()
    proxy[PROXY_KEY] = lat_obj

    coll = lat_obj.users_collection[0] if lat_obj.users_collection else context.scene.collection
    coll.objects.link(proxy)

    if copy_existing:
        for lvg in lat_obj.vertex_groups:
            pvg = proxy.vertex_groups.new(name=lvg.name)
            for i in range(len(lat.points)):
                try:
                    w = lvg.weight(i)
                except RuntimeError:
                    continue
                pvg.add([i], w, 'REPLACE')

    return proxy


def auto_weight_proxy(context, proxy, arm):
    for o in context.selected_objects:
        o.select_set(False)
    proxy.select_set(True)
    arm.select_set(True)
    context.view_layer.objects.active = arm
    bpy.ops.object.parent_set(type='ARMATURE_AUTO')


def copy_back(proxy, lat_obj):
    mesh = proxy.data
    count = len(lat_obj.data.points)
    if len(mesh.vertices) != count:
        return False

    all_points = list(range(count))
    for pvg in proxy.vertex_groups:
        lvg = lat_obj.vertex_groups.get(pvg.name) or lat_obj.vertex_groups.new(name=pvg.name)
        lvg.remove(all_points)

    # vertex index == lattice point index, so this is a straight copy
    for v in mesh.vertices:
        for ge in v.groups:
            name = proxy.vertex_groups[ge.group].name
            lat_obj.vertex_groups[name].add([v.index], ge.weight, 'REPLACE')
    return True


def delete_proxy(proxy):
    mesh = proxy.data
    bpy.data.objects.remove(proxy)
    bpy.data.meshes.remove(mesh)


def bind_lattice(lat_obj, arm):
    world = lat_obj.matrix_world.copy()
    lat_obj.parent = arm
    lat_obj.parent_type = 'OBJECT'
    lat_obj.matrix_world = world

    mod = next((m for m in lat_obj.modifiers if m.type == 'ARMATURE'), None)
    if not mod:
        mod = lat_obj.modifiers.new("Armature", 'ARMATURE')
    mod.object = arm
    mod.use_vertex_groups = True
    mod.use_bone_envelopes = False


def unweighted_points(lat_obj):
    count = len(lat_obj.data.points)
    missing = 0
    for i in range(count):
        total = 0.0
        for vg in lat_obj.vertex_groups:
            try:
                total += vg.weight(i)
            except RuntimeError:
                pass
        if total <= 0.0:
            missing += 1
    return missing


class TZU_OT_lattice_auto_weight(bpy.types.Operator):
    bl_idname = "tzu.lattice_auto_weight"
    bl_label = "[TZ] Lattice Auto Weight"
    bl_description = "Parent selected lattices to the active armature with automatic weights"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        arm = context.active_object
        if not arm or arm.type != 'ARMATURE' or context.mode != 'OBJECT':
            return False
        return any(o.type == 'LATTICE' for o in context.selected_objects)

    def execute(self, context):
        arm = context.active_object
        lattices = [o for o in context.selected_objects if o.type == 'LATTICE']

        for lat_obj in lattices:
            proxy = make_proxy(context, lat_obj, copy_existing=False)
            auto_weight_proxy(context, proxy, arm)

            # clear old groups so stale weights don't linger
            lat_obj.vertex_groups.clear()
            copy_back(proxy, lat_obj)
            delete_proxy(proxy)
            bind_lattice(lat_obj, arm)

            missing = unweighted_points(lat_obj)
            if missing:
                self.report({'WARNING'}, f"{lat_obj.name}: {missing} point(s) got no weight")

        for o in context.selected_objects:
            o.select_set(False)
        for lat_obj in lattices:
            lat_obj.select_set(True)
        arm.select_set(True)
        context.view_layer.objects.active = arm

        self.report({'INFO'}, f"Auto weighted {len(lattices)} lattice(s)")
        return {'FINISHED'}


class TZU_MT_lattice_parent(bpy.types.Menu):
    bl_label = "Set Parent To"
    bl_idname = "TZU_MT_lattice_parent"

    def draw(self, context):
        layout = self.layout
        layout.operator_context = 'EXEC_DEFAULT'

        layout.operator("tzu.lattice_auto_weight", icon='LATTICE_DATA')
        layout.separator()

        layout.operator("object.parent_set", text="Object").type = 'OBJECT'
        op = layout.operator("object.parent_set", text="Object (Keep Transform)")
        op.type = 'OBJECT'
        op.keep_transform = True
        layout.separator()
        layout.operator("object.parent_set", text="Armature Deform").type = 'ARMATURE'
        layout.operator("object.parent_set", text="   With Empty Groups").type = 'ARMATURE_NAME'
        layout.operator("object.parent_set", text="   With Envelope Weights").type = 'ARMATURE_ENVELOPE'
        layout.separator()
        layout.operator("object.parent_set", text="Bone").type = 'BONE'


class TZU_OT_lattice_parent_menu(bpy.types.Operator):
    bl_idname = "tzu.lattice_parent_menu"
    bl_label = "Parent (Lattice Aware)"
    bl_options = {'INTERNAL'}

    def invoke(self, context, event):
        # only take over ctrl+p when a lattice is going onto an armature
        if TZU_OT_lattice_auto_weight.poll(context):
            bpy.ops.wm.call_menu(name=TZU_MT_lattice_parent.bl_idname)
            return {'FINISHED'}
        return {'PASS_THROUGH'}


class TZU_OT_lattice_proxy_create(bpy.types.Operator):
    bl_idname = "tzu.lattice_proxy_create"
    bl_label = "Create Weight Proxy"
    bl_description = "Make a paintable mesh with one vertex per lattice point"
    bl_options = {'REGISTER', 'UNDO'}

    auto_weights: BoolProperty(
        name="Automatic Weights",
        description="Parent the proxy to the lattice's armature with automatic weights",
        default=False,
    )

    @classmethod
    def poll(cls, context):
        obj = context.object
        return obj and obj.type == 'LATTICE' and obj.mode == 'OBJECT'

    def execute(self, context):
        lat_obj = context.object
        proxy = make_proxy(context, lat_obj)

        arm = find_armature(lat_obj)
        if self.auto_weights and arm:
            auto_weight_proxy(context, proxy, arm)
        elif arm:
            # keep an armature on it so posing previews while painting
            mod = proxy.modifiers.new("Armature", 'ARMATURE')
            mod.object = arm

        for o in context.selected_objects:
            o.select_set(False)
        proxy.select_set(True)
        context.view_layer.objects.active = proxy
        lat_obj.hide_set(True)

        return {'FINISHED'}


class TZU_OT_lattice_proxy_apply(bpy.types.Operator):
    bl_idname = "tzu.lattice_proxy_apply"
    bl_label = "Apply Weights to Lattice"
    bl_description = "Copy the proxy's vertex groups back onto its lattice"
    bl_options = {'REGISTER', 'UNDO'}

    delete_proxy: BoolProperty(name="Delete Proxy", default=True)

    @classmethod
    def poll(cls, context):
        obj = context.object
        return obj and obj.type == 'MESH' and obj.get(PROXY_KEY) is not None

    def execute(self, context):
        proxy = context.object
        lat_obj = proxy.get(PROXY_KEY)

        if not lat_obj or lat_obj.type != 'LATTICE':
            self.report({'ERROR'}, "Source lattice is missing")
            return {'CANCELLED'}

        if proxy.mode != 'OBJECT':
            bpy.ops.object.mode_set(mode='OBJECT')

        if not copy_back(proxy, lat_obj):
            self.report({'ERROR'}, "Vertex count changed, can't map back to lattice")
            return {'CANCELLED'}

        lat_obj.hide_set(False)

        if self.delete_proxy:
            delete_proxy(proxy)
            lat_obj.select_set(True)
            context.view_layer.objects.active = lat_obj

        self.report({'INFO'}, f"Copied weights to {lat_obj.name}")
        return {'FINISHED'}


class TZU_PT_lattice_weights(bpy.types.Panel):
    bl_label = "TZU/Lattice Weights"
    bl_idname = "TZU_PT_lattice_weights"
    bl_space_type = 'PROPERTIES'
    bl_region_type = 'WINDOW'
    bl_context = "data"

    @classmethod
    def poll(cls, context):
        obj = context.object
        if not obj:
            return False
        return obj.type == 'LATTICE' or (obj.type == 'MESH' and obj.get(PROXY_KEY) is not None)

    def draw(self, context):
        layout = self.layout
        obj = context.object

        if obj.type == 'LATTICE':
            layout.operator("tzu.lattice_proxy_create", icon='MESH_GRID')
        else:
            src = obj.get(PROXY_KEY)
            layout.label(text=f"Proxy for {src.name if src else 'missing lattice'}", icon='LATTICE_DATA')
            layout.operator("tzu.lattice_proxy_apply", icon='CHECKMARK')


def parent_menu_entry(self, context):
    self.layout.separator()
    self.layout.operator("tzu.lattice_auto_weight", icon='LATTICE_DATA')


classes = (
    TZU_OT_lattice_auto_weight,
    TZU_MT_lattice_parent,
    TZU_OT_lattice_parent_menu,
    TZU_OT_lattice_proxy_create,
    TZU_OT_lattice_proxy_apply,
    TZU_PT_lattice_weights,
)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)

    bpy.types.VIEW3D_MT_object_parent.append(parent_menu_entry)

    kc = bpy.context.window_manager.keyconfigs.addon
    if kc:
        km = kc.keymaps.new(name="Object Mode", space_type='EMPTY')
        kmi = km.keymap_items.new(TZU_OT_lattice_parent_menu.bl_idname, 'P', 'PRESS', ctrl=True)
        addon_keymaps.append((km, kmi))


def unregister():
    for km, kmi in addon_keymaps:
        km.keymap_items.remove(kmi)
    addon_keymaps.clear()

    try:
        bpy.types.VIEW3D_MT_object_parent.remove(parent_menu_entry)
    except Exception:
        pass

    for cls in reversed(classes):
        try:
            bpy.utils.unregister_class(cls)
        except RuntimeError:
            pass
