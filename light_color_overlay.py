# small dot at each light's position tinted to its actual color
# blender doesn't expose light color on the built-in gizmo, so this fakes it
# area lights get their real shape (rect/square/disk/ellipse) + a direction line instead

import bpy
import gpu
from gpu_extras.batch import batch_for_shader
from mathutils import Vector
import math

_handler = None

def _circle_verts(segments=24):
    verts = []
    for i in range(segments):
        angle = 2 * math.pi * i / segments
        verts.append((math.cos(angle), math.sin(angle)))
    return verts

_CIRCLE = _circle_verts()

def _light_rgb(light):
    col = light.color
    # normalize so dim/bright lights still show a clear hue
    max_c = max(col[0], col[1], col[2], 0.0001)
    return col[0] / max_c, col[1] / max_c, col[2] / max_c

def _draw_dot(shader, origin, right, up, radius, color):
    coords = [origin + right * x * radius + up * y * radius for x, y in _CIRCLE]
    batch = batch_for_shader(shader, 'TRI_FAN', {"pos": coords})
    shader.uniform_float("color", color)
    batch.draw(shader)

def _area_shape_local_verts(light):
    shape = light.shape
    sx = light.size
    sy = light.size_y if shape in ('RECTANGLE', 'ELLIPSE') else light.size

    if shape in ('SQUARE', 'RECTANGLE'):
        hx, hy = sx / 2, sy / 2
        return [
            Vector((-hx, -hy, 0)), Vector((hx, -hy, 0)),
            Vector((hx, hy, 0)), Vector((-hx, hy, 0)),
        ]
    else:  # DISK, ELLIPSE
        rx, ry = sx / 2, sy / 2
        return [Vector((math.cos(a) * rx, math.sin(a) * ry, 0)) for a in
                (2 * math.pi * i / 32 for i in range(32))]

def _draw():
    scene = bpy.context.scene
    if not scene.tz_light_color_overlay_enabled:
        return

    region_data = bpy.context.region_data
    if region_data is None:
        return

    view_inv = region_data.view_matrix.inverted()
    view_rot = region_data.view_matrix.to_3x3().inverted()
    right = view_rot @ Vector((1, 0, 0))
    up = view_rot @ Vector((0, 1, 0))
    cam_pos = view_inv.translation

    shader = gpu.shader.from_builtin('UNIFORM_COLOR')
    gpu.state.blend_set('ALPHA')
    gpu.state.depth_test_set('LESS_EQUAL')

    for obj in bpy.context.view_layer.objects:
        if obj.type != 'LIGHT':
            continue
        if not obj.visible_get():
            continue

        light = obj.data
        r, g, b = _light_rgb(light)
        origin = obj.matrix_world.translation
        # push a touch toward the camera so it doesn't z-fight with the real icon
        push = (cam_pos - origin).normalized() * 0.01

        if light.type == 'AREA':
            local_verts = _area_shape_local_verts(light)
            world_verts = [obj.matrix_world @ v + push for v in local_verts]

            gpu.state.line_width_set(2)
            loop = world_verts + [world_verts[0]]
            batch = batch_for_shader(shader, 'LINE_STRIP', {"pos": loop})
            shader.uniform_float("color", (r, g, b, 0.9))
            batch.draw(shader)

            # direction line along local -Z, sized off the smaller side
            sx = light.size
            sy = light.size_y if light.shape in ('RECTANGLE', 'ELLIPSE') else light.size
            line_len = min(sx, sy)
            start = obj.matrix_world @ Vector((0, 0, 0)) + push
            end = obj.matrix_world @ Vector((0, 0, -line_len)) + push
            batch = batch_for_shader(shader, 'LINES', {"pos": [start, end]})
            shader.uniform_float("color", (r, g, b, 0.9))
            batch.draw(shader)
        else:
            radius = 0.03
            _draw_dot(shader, origin + push, right, up, radius, (r, g, b, 0.9))

    gpu.state.line_width_set(1)
    gpu.state.blend_set('NONE')
    gpu.state.depth_test_set('NONE')

class TZ_OT_toggle_light_color_overlay(bpy.types.Operator):
    bl_idname = "tz.toggle_light_color_overlay"
    bl_label = "Toggle Light Color Overlay"
    bl_description = "Show a colored marker on each light matching its actual color"

    def execute(self, context):
        context.scene.tz_light_color_overlay_enabled = not context.scene.tz_light_color_overlay_enabled
        for area in context.screen.areas:
            if area.type == 'VIEW_3D':
                area.tag_redraw()
        return {'FINISHED'}

def draw_overlay_toggle(self, context):
    self.layout.prop(context.scene, "tz_light_color_overlay_enabled", text="Light Colors", toggle=True, icon='LIGHT')

def register():
    global _handler
    bpy.types.Scene.tz_light_color_overlay_enabled = bpy.props.BoolProperty(
        name="Light Color Overlay",
        default=False,
        description="Show a colored marker on each light matching its actual color"
    )
    bpy.utils.register_class(TZ_OT_toggle_light_color_overlay)
    bpy.types.VIEW3D_HT_header.append(draw_overlay_toggle)
    _handler = bpy.types.SpaceView3D.draw_handler_add(_draw, (), 'WINDOW', 'POST_VIEW')

def unregister():
    global _handler
    if _handler is not None:
        bpy.types.SpaceView3D.draw_handler_remove(_handler, 'WINDOW')
        _handler = None
    try:
        bpy.types.VIEW3D_HT_header.remove(draw_overlay_toggle)
    except Exception:
        pass
    bpy.utils.unregister_class(TZ_OT_toggle_light_color_overlay)
    del bpy.types.Scene.tz_light_color_overlay_enabled
