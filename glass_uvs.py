import bpy
import bmesh
import math
import random

COLOR_NAME = "GlassRandom"


def is_face_uv_selected(face, uv_layer, sync_select):
    if sync_select:
        return face.select

    if not face.select:
        return False

    # in the uv editor, only count faces whose uvs are all selected
    for loop in face.loops:
        try:
            if not loop[uv_layer].select:
                return False
        except AttributeError:
            return True

    return True


def uv_key(loop, uv_layer):
    uv = loop[uv_layer].uv
    return (round(uv.x, 5), round(uv.y, 5))


def find_islands(faces, uv_layer):
    face_set = set(faces)
    visited = set()
    islands = []

    for start in faces:
        if start in visited:
            continue

        island = []
        stack = [start]
        visited.add(start)

        while stack:
            face = stack.pop()
            island.append(face)

            for loop in face.loops:
                # neighbour across this edge, only if the uvs are joined there too
                for other in loop.edge.link_loops:
                    other_face = other.face
                    if other_face in visited or other_face not in face_set:
                        continue

                    joined = False
                    if uv_key(loop, uv_layer) == uv_key(other.link_loop_next, uv_layer):
                        if uv_key(loop.link_loop_next, uv_layer) == uv_key(other, uv_layer):
                            joined = True

                    if joined:
                        visited.add(other_face)
                        stack.append(other_face)

        islands.append(island)

    return islands


def get_straighten_angle(island, uv_layer):
    # finds the longest uv edge and returns the angle that'd make it axis aligned
    longest = 0
    angle = 0

    for face in island:
        for loop in face.loops:
            a = loop[uv_layer].uv
            b = loop.link_loop_next[uv_layer].uv
            dx = b.x - a.x
            dy = b.y - a.y
            length = dx * dx + dy * dy

            if length > longest:
                longest = length
                angle = math.atan2(dy, dx)

    # snap to the nearest 90 degrees
    quarter = math.pi / 2
    return angle - round(angle / quarter) * quarter


def fit_island(island, uv_layer, straighten):
    loops = []
    for face in island:
        for loop in face.loops:
            loops.append(loop[uv_layer])

    if straighten:
        angle = -get_straighten_angle(island, uv_layer)
        cos_a = math.cos(angle)
        sin_a = math.sin(angle)

        for luv in loops:
            x = luv.uv.x
            y = luv.uv.y
            luv.uv.x = x * cos_a - y * sin_a
            luv.uv.y = x * sin_a + y * cos_a

    min_x = min(luv.uv.x for luv in loops)
    max_x = max(luv.uv.x for luv in loops)
    min_y = min(luv.uv.y for luv in loops)
    max_y = max(luv.uv.y for luv in loops)

    width = max_x - min_x
    height = max_y - min_y

    for luv in loops:
        if width > 0:
            luv.uv.x = (luv.uv.x - min_x) / width
        else:
            luv.uv.x = 0

        if height > 0:
            luv.uv.y = (luv.uv.y - min_y) / height
        else:
            luv.uv.y = 0


class UV_OT_tz_glass_uvs(bpy.types.Operator):
    bl_idname = "uv.tz_glass_uvs"
    bl_label = "Fit Islands To 0-1"
    bl_description = "Stretch each selected uv island to fill the full 0-1 square (for glass panes)"
    bl_options = {'REGISTER', 'UNDO'}

    straighten: bpy.props.BoolProperty(
        name="Straighten",
        description="Rotate each island so its longest edge is axis aligned first",
        default=True
    )

    random_colour: bpy.props.BoolProperty(
        name="Random Island Colour",
        description="Write a random vertex colour per island so the shader can offset smudges",
        default=True
    )

    @classmethod
    def poll(cls, context):
        return context.mode == 'EDIT_MESH'

    def execute(self, context):
        sync_select = context.tool_settings.use_uv_select_sync
        island_count = 0

        for obj in context.objects_in_mode_unique_data:
            if obj.type != 'MESH':
                continue

            bm = bmesh.from_edit_mesh(obj.data)
            uv_layer = bm.loops.layers.uv.active

            if uv_layer is None:
                continue

            faces = []
            for face in bm.faces:
                if is_face_uv_selected(face, uv_layer, sync_select):
                    faces.append(face)

            islands = find_islands(faces, uv_layer)

            colour_layer = None
            if self.random_colour:
                colour_layer = bm.loops.layers.float_color.get(COLOR_NAME)
                if colour_layer is None:
                    colour_layer = bm.loops.layers.float_color.new(COLOR_NAME)

            for island in islands:
                fit_island(island, uv_layer, self.straighten)

                if colour_layer is not None:
                    value = random.random()
                    for face in island:
                        for loop in face.loops:
                            loop[colour_layer] = (value, value, value, 1)

            island_count += len(islands)
            bmesh.update_edit_mesh(obj.data)

            if colour_layer is not None:
                attr = obj.data.color_attributes.get(COLOR_NAME)
                if attr is not None:
                    obj.data.color_attributes.active_color = attr
                    obj.data.color_attributes.render_color_index = obj.data.color_attributes.find(COLOR_NAME)

        if island_count == 0:
            self.report({'WARNING'}, "No uv islands selected")
            return {'CANCELLED'}

        self.report({'INFO'}, f"Fitted {island_count} island(s) to 0-1")
        return {'FINISHED'}


def menu_func(self, context):
    self.layout.separator()
    self.layout.operator(UV_OT_tz_glass_uvs.bl_idname, text="Fit Islands To 0-1 (Glass)")


def register():
    bpy.utils.register_class(UV_OT_tz_glass_uvs)
    bpy.types.IMAGE_MT_uvs.append(menu_func)
    bpy.types.VIEW3D_MT_uv_map.append(menu_func)


def unregister():
    bpy.types.VIEW3D_MT_uv_map.remove(menu_func)
    bpy.types.IMAGE_MT_uvs.remove(menu_func)
    bpy.utils.unregister_class(UV_OT_tz_glass_uvs)
