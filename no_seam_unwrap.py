import bpy
import bmesh

class OBJECT_OT_no_seam_unwrap(bpy.types.Operator):
    bl_idname = "object.no_seam_unwrap"
    bl_label = "No Seam Unwrap"
    bl_options = {'REGISTER', 'UNDO'}
    
    method: bpy.props.EnumProperty(
        name="Method",
        items=[
            ('ANGLE_BASED', "Angle Based", ""),
            ('CONFORMAL', "Conformal", "")
        ],
        default='ANGLE_BASED'
    )
    
    def execute(self, context):
        obj = context.object
        
        if obj is None or obj.type != 'MESH':
            self.report({'WARNING'}, "Select a mesh object")
            return {'CANCELLED'}
        
        if obj.mode != 'EDIT':
            bpy.ops.object.mode_set(mode='EDIT')
        
        bpy.context.view_layer.objects.active = obj
        
        bm = bmesh.from_edit_mesh(obj.data)
        
        seam_edges = [e for e in bm.edges if e.seam]
        
        for edge in seam_edges:
            edge.seam = False
        
        bmesh.update_edit_mesh(obj.data)
        
        bpy.ops.uv.unwrap(method=self.method)
        
        bm = bmesh.from_edit_mesh(obj.data)
        
        for edge in seam_edges:
            edge.seam = True
        
        bmesh.update_edit_mesh(obj.data)
        
        return {'FINISHED'}


def menu_func(self, context):
    self.layout.operator(OBJECT_OT_no_seam_unwrap.bl_idname, text="No Seam Unwrap")


def register():
    bpy.utils.register_class(OBJECT_OT_no_seam_unwrap)
    bpy.types.VIEW3D_MT_uv_map.append(menu_func)


def unregister():
    bpy.types.VIEW3D_MT_uv_map.remove(menu_func)
    bpy.utils.unregister_class(OBJECT_OT_no_seam_unwrap)