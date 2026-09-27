import bpy

MARK = "tz_uv_grid_preview_link"  # per-material: "nodename|socketname" it used to feed the output
NODE_NAMES = ("UVGridPreview_Image", "UVGridPreview_UVMap", "UVGridPreview_Missing")
GRID_IMAGE_NAME = "TzUtils UV Grid"


def _get_grid_image():
    img = bpy.data.images.get(GRID_IMAGE_NAME)
    if img is None:
        img = bpy.data.images.new(GRID_IMAGE_NAME, 1024, 1024)
        img.generated_type = 'UV_GRID'
    return img


def _enable_material(mat, obj):
    nt = mat.node_tree
    out = next((n for n in nt.nodes if n.type == 'OUTPUT_MATERIAL'), None)
    if out is None:
        return

    surf = out.inputs["Surface"]
    if not surf.is_linked:
        return

    link = surf.links[0]
    mat[MARK] = f"{link.from_node.name}|{link.from_socket.name}"

    if len(obj.data.uv_layers) < 2:
        red = nt.nodes.new("ShaderNodeEmission")
        red.name = NODE_NAMES[2]
        red.inputs["Color"].default_value = (1, 0, 0, 1)
        nt.links.new(red.outputs["Emission"], surf)
        return

    uv_node = nt.nodes.new("ShaderNodeUVMap")
    uv_node.name = NODE_NAMES[1]
    uv_node.uv_map = obj.data.uv_layers[1].name

    img_node = nt.nodes.new("ShaderNodeTexImage")
    img_node.name = NODE_NAMES[0]
    img_node.image = _get_grid_image()

    nt.links.new(uv_node.outputs["UV"], img_node.inputs["Vector"])
    nt.links.new(img_node.outputs["Color"], surf)


def _disable_material(mat):
    nt = mat.node_tree
    stored = mat.get(MARK)
    if not stored:
        return

    node_name, socket_name = stored.split("|", 1)

    for name in NODE_NAMES:
        node = nt.nodes.get(name)
        if node:
            nt.nodes.remove(node)

    out = next((n for n in nt.nodes if n.type == 'OUTPUT_MATERIAL'), None)
    src = nt.nodes.get(node_name)
    if out and src and socket_name in src.outputs:
        nt.links.new(src.outputs[socket_name], out.inputs["Surface"])

    del mat[MARK]


class TzUtils_OT_toggle_uv_grid_preview(bpy.types.Operator):
    bl_idname = "tzutils.toggle_uv_grid_preview"
    bl_label = "Toggle UV Grid Preview"
    bl_description = "Preview the 2nd UV map (lightmap) as a checker grid on every object's material, red if it has none"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        scene = context.scene
        turning_on = not scene.get("tz_uv_grid_preview_active", False)

        touched = set()
        for obj in bpy.data.objects:
            if obj.type != 'MESH':
                continue
            for slot in obj.material_slots:
                mat = slot.material
                if not mat or not mat.use_nodes or mat.name in touched:
                    continue
                touched.add(mat.name)
                if turning_on:
                    _enable_material(mat, obj)
                else:
                    _disable_material(mat)

        scene["tz_uv_grid_preview_active"] = turning_on
        self.report({'INFO'}, "UV grid preview " + ("enabled" if turning_on else "disabled"))
        return {'FINISHED'}


class TzUtils_PT_uv_grid_preview_panel(bpy.types.Panel):
    bl_label = "UV Grid Preview"
    bl_idname = "TzUtils_PT_uv_grid_preview_panel"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'TzUtils'

    def draw(self, context):
        layout = self.layout
        active = context.scene.get("tz_uv_grid_preview_active", False)
        layout.operator(
            "tzutils.toggle_uv_grid_preview",
            text="Disable Preview" if active else "Enable Preview",
            icon='UV' if not active else 'CANCEL',
            depress=active,
        )
        layout.label(text="Checks 2nd UV map, red = missing", icon='INFO')


classes = (
    TzUtils_OT_toggle_uv_grid_preview,
    TzUtils_PT_uv_grid_preview_panel,
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
