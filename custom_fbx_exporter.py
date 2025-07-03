# this is mainly made for vrchat stuff, very specific for me, sorry
import bpy
import os


class OT_CustomFBXExporter(bpy.types.Operator):
    bl_idname = "export_scene.custom_fbx"
    bl_label = "Custom FBX Export"

    def execute(self, context):
        blend_path = bpy.data.filepath
        if not blend_path:
            self.report({'ERROR'}, "save the blend file first")
            return {'CANCELLED'}

        folder = os.path.dirname(blend_path)
        filename = os.path.splitext(os.path.basename(blend_path))[0]
        fbx_path = os.path.join(folder, filename + ".fbx")

        bpy.ops.ed.undo_push(message="Before Custom FBX Export")

        try:
            for obj in bpy.context.scene.objects:
                if obj.type != 'MESH':
                    continue

                allowed_uvs = [uv for uv in obj.data.uv_layers if uv.name == "Oven" or uv.name.startswith("KP_")]
                saved_uv_data = {}
                for uv in allowed_uvs:
                    saved_uv_data[uv.name] = [loop_uv.uv.copy() for loop_uv in uv.data]

                while obj.data.uv_layers:
                    obj.data.uv_layers.remove(obj.data.uv_layers[0])

                for name, uv_data in saved_uv_data.items():
                    new_uv = obj.data.uv_layers.new(name=name)
                    for i, loop_uv in enumerate(new_uv.data):
                        loop_uv.uv = uv_data[i]

                if "Oven" in obj.data.uv_layers:
                    obj.data.uv_layers.active = obj.data.uv_layers["Oven"]
                else:
                    kp_uv = next((uv for uv in obj.data.uv_layers if uv.name.startswith("KP_")), None)
                    if kp_uv:
                        obj.data.uv_layers.active = kp_uv

                obj.data.materials.clear()

            bpy.ops.export_scene.fbx(filepath=fbx_path, use_selection=False)

        except Exception as e:
            self.report({'ERROR'}, f"export failed: {str(e)}")
            bpy.ops.ed.undo()
            return {'CANCELLED'}

        bpy.ops.ed.undo()

        self.report({'INFO'}, f"exported to {fbx_path}")
        return {'FINISHED'}

class PT_CustomExporterPanel(bpy.types.Panel):
    bl_label = "Custom FBX Export"
    bl_idname = "TzUtils_PT_custom_exporter"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'TzUtils'

    def draw(self, context):
        layout = self.layout
        layout.operator("export_scene.custom_fbx")


classes = (OT_CustomFBXExporter, PT_CustomExporterPanel)

def register():
    for cls in classes:
        bpy.utils.register_class(cls)

def unregister():
    try: 
        for cls in reversed(classes):
            bpy.utils.unregister_class(cls)
    except:
        print("eh")
