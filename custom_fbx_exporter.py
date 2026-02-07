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

        # save current file before making any changes
        bpy.ops.wm.save_mainfile()

        try:
            for obj in bpy.context.scene.objects:
                if obj.type != 'MESH':
                    continue

                # Skip objects that start with KP_ - don't touch them at all
                if obj.name.startswith("KP_"):
                    continue

                # For non-KP_ objects: keep only Oven, automap, and KP_ UVs
                uvs_to_keep = {}
                for uv in obj.data.uv_layers:
                    if uv.name in ["Oven", "automap"] or uv.name.startswith("KP_"):
                        uvs_to_keep[uv.name] = [loop_uv.uv.copy() for loop_uv in uv.data]
                
                # Remove all UVs
                while obj.data.uv_layers:
                    obj.data.uv_layers.remove(obj.data.uv_layers[0])
                
                # Recreate in order: Oven first, automap second, then KP_ UVs
                if "Oven" in uvs_to_keep:
                    new_uv = obj.data.uv_layers.new(name="Oven")
                    for i, loop_uv in enumerate(new_uv.data):
                        loop_uv.uv = uvs_to_keep["Oven"][i]
                
                if "automap" in uvs_to_keep:
                    new_uv = obj.data.uv_layers.new(name="automap")
                    for i, loop_uv in enumerate(new_uv.data):
                        loop_uv.uv = uvs_to_keep["automap"][i]
                
                # Add KP_ UVs
                for name, uv_data in uvs_to_keep.items():
                    if name not in ["Oven", "automap"]:
                        new_uv = obj.data.uv_layers.new(name=name)
                        for i, loop_uv in enumerate(new_uv.data):
                            loop_uv.uv = uv_data[i]
                
                # Set active UV
                if "Oven" in obj.data.uv_layers:
                    obj.data.uv_layers.active = obj.data.uv_layers["Oven"]
                elif obj.data.uv_layers:
                    kp_uv = next((uv for uv in obj.data.uv_layers if uv.name.startswith("KP_")), None)
                    if kp_uv:
                        obj.data.uv_layers.active = kp_uv
                
                # Handle materials - keep only KP_ materials
                kp_mats = [mat for mat in obj.data.materials if mat and mat.name.startswith("KP_")]
                obj.data.materials.clear()
                for mat in kp_mats:
                    obj.data.materials.append(mat)


            bpy.ops.export_scene.fbx(filepath=fbx_path, use_selection=False, apply_scale_options='FBX_SCALE_ALL', add_leaf_bones=False)

        except Exception as e:
            self.report({'ERROR'}, f"export failed: {str(e)}")
            # reload file to restore state
            bpy.ops.wm.open_mainfile(filepath=blend_path)
            return {'CANCELLED'}

        # reload file to restore original state
        bpy.ops.wm.open_mainfile(filepath=blend_path)

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
        
        # warning box
        box = layout.box()
        box.label(text="⚠ This will save your file before exporting", icon='ERROR')
        
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
