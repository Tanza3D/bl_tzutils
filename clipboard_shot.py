import bpy
import gpu
import numpy as np
from bpy_extras.view3d_utils import location_3d_to_region_2d
import os
import shutil
import subprocess
import tempfile


def copy_png_to_clipboard(path):
    with open(path, "rb") as f:
        data = f.read()

    if os.environ.get("WAYLAND_DISPLAY") and shutil.which("wl-copy"):
        subprocess.Popen(["wl-copy", "--type", "image/png"], stdin=subprocess.PIPE).communicate(data)
        return True

    if shutil.which("xclip"):
        subprocess.Popen(["xclip", "-selection", "clipboard", "-t", "image/png"], stdin=subprocess.PIPE).communicate(data)
        return True

    return False


def save_render_result(scene, path):
    image = bpy.data.images.get("Render Result")
    if not image or not image.has_data:
        return False

    settings = scene.render.image_settings
    old_format = settings.file_format
    old_mode = settings.color_mode
    old_depth = settings.color_depth

    settings.file_format = 'PNG'
    settings.color_mode = 'RGBA'
    settings.color_depth = '8'
    try:
        image.save_render(path, scene=scene)
    finally:
        settings.file_format = old_format
        settings.color_mode = old_mode
        settings.color_depth = old_depth
    return True


def temp_png():
    return os.path.join(tempfile.gettempdir(), "tz_clipboard_shot.png")


def camera_frame_box(scene, region, rv3d, w, h):
    # pixel box of the camera frame inside the region, or the whole region if not in camera view
    if rv3d.view_perspective != 'CAMERA' or scene.camera is None:
        return 0, 0, w, h

    cam = scene.camera
    corners = [cam.matrix_world @ v for v in cam.data.view_frame(scene=scene)]
    xs = []
    ys = []
    for c in corners:
        p = location_3d_to_region_2d(region, rv3d, c)
        if p is not None:
            xs.append(p.x)
            ys.append(p.y)
    if not xs:
        return 0, 0, w, h

    x0 = max(int(round(min(xs))), 0)
    x1 = min(int(round(max(xs))), w)
    y0 = max(int(round(min(ys))), 0)
    y1 = min(int(round(max(ys))), h)
    return x0, y0, x1, y1


def load_png(path):
    image = bpy.data.images.load(path, check_existing=False)
    w, h = image.size
    pixels = np.empty(w * h * 4, dtype=np.float32)
    image.pixels.foreach_get(pixels)
    bpy.data.images.remove(image)
    return pixels.reshape(h, w, 4)


class TZ_OT_copy_viewport(bpy.types.Operator):
    bl_idname = "tz.copy_viewport"
    bl_label = "Copy Viewport"
    bl_description = "Copy exactly what the viewport shows (cycles too) with transparency, no re-render"

    def execute(self, context):
        window = context.window
        area = context.area
        space = context.space_data
        scene = context.scene
        region = None
        for r in area.regions:
            if r.type == 'WINDOW':
                region = r

        ui = context.preferences.themes[0].user_interface
        grad = context.preferences.themes[0].view_3d.space.gradients

        old = {
            "checker_a": tuple(ui.transparent_checker_primary),
            "checker_b": tuple(ui.transparent_checker_secondary),
            "bg_type": grad.background_type,
            "bg": tuple(grad.high_gradient),
            "overlays": space.overlay.show_overlays,
        }

        def set_backdrop(colour):
            # film transparent shows the checker, otherwise the theme background, so flip both
            ui.transparent_checker_primary = colour
            ui.transparent_checker_secondary = colour
            grad.background_type = 'SINGLE_COLOR'
            grad.high_gradient = colour
            space.overlay.show_overlays = False
            area.tag_redraw()

        def restore():
            ui.transparent_checker_primary = old["checker_a"]
            ui.transparent_checker_secondary = old["checker_b"]
            grad.background_type = old["bg_type"]
            grad.high_gradient = old["bg"]
            space.overlay.show_overlays = old["overlays"]
            area.tag_redraw()

        tmp = tempfile.gettempdir()
        black_path = os.path.join(tmp, "tz_grab_black.png")
        white_path = os.path.join(tmp, "tz_grab_white.png")

        def shoot(path):
            with bpy.context.temp_override(window=window, area=area, region=region):
                bpy.ops.screen.screenshot_area(filepath=path)

        # screenshots only see the real cycles image once the window has actually redrawn,
        # so each step waits a tick on a timer
        steps = []

        def step_black():
            set_backdrop((0.0, 0.0, 0.0))
            return None

        def step_shoot_black():
            shoot(black_path)
            set_backdrop((1.0, 1.0, 1.0))
            return None

        def step_shoot_white():
            try:
                shoot(white_path)
            finally:
                restore()
            finish()
            return None

        steps.extend([step_black, step_shoot_black, step_shoot_white])

        def run_next():
            fn = steps.pop(0)
            fn()
            if steps:
                return 0.05
            return None

        def finish():
            black = load_png(black_path)
            white = load_png(white_path)

            # area screenshot includes the header strip etc, line it up with the region
            ah = black.shape[0]
            oy = region.y - area.y
            ox = region.x - area.x
            black = black[oy:oy + region.height, ox:ox + region.width]
            white = white[oy:oy + region.height, ox:ox + region.width]

            h, w = black.shape[:2]
            x0, y0, x1, y1 = camera_frame_box(scene, region, space.region_3d, w, h)
            black = black[y0:y1, x0:x1, :3]
            white = white[y0:y1, x0:x1, :3]

            # over black you get colour * alpha, over white you get that plus (1 - alpha)
            alpha = np.clip(1.0 - (white - black).mean(axis=2), 0.0, 1.0)
            safe = np.maximum(alpha, 1e-4)[..., None]
            colour = np.clip(black / safe, 0.0, 1.0)

            out_h, out_w = alpha.shape
            pixels = np.dstack((colour, alpha)).astype(np.float32)
            image = bpy.data.images.new("tz_viewport_grab", out_w, out_h, alpha=True)
            image.pixels.foreach_set(pixels.ravel())
            path = temp_png()
            image.filepath_raw = path
            image.file_format = 'PNG'
            image.save()
            bpy.data.images.remove(image)

            if copy_png_to_clipboard(path):
                print("tz: viewport copied", out_w, out_h)
            else:
                print("tz: no wl-copy or xclip found")

        bpy.app.timers.register(run_next, first_interval=0.0)
        self.report({'INFO'}, "grabbing viewport...")
        return {'FINISHED'}


class TZ_OT_copy_render(bpy.types.Operator):
    bl_idname = "tz.copy_render"
    bl_label = "Copy Render"
    bl_description = "Copy the last render result to the clipboard"

    def execute(self, context):
        path = temp_png()
        if not save_render_result(context.scene, path):
            self.report({'ERROR'}, "no render to copy, hit F12 first")
            return {'CANCELLED'}

        if not copy_png_to_clipboard(path):
            self.report({'ERROR'}, "no wl-copy or xclip found")
            return {'CANCELLED'}

        self.report({'INFO'}, "render copied")
        return {'FINISHED'}


def draw_viewport_button(self, context):
    row = self.layout.row(align=True)
    row.operator("tz.copy_viewport", text="", icon='RESTRICT_VIEW_OFF')
    row.operator("tz.copy_render", text="", icon='RENDER_STILL')


def draw_image_button(self, context):
    image = context.space_data.image
    if image and image.type == 'RENDER_RESULT':
        self.layout.operator("tz.copy_render", text="Copy", icon='COPYDOWN')


classes = (
    TZ_OT_copy_viewport,
    TZ_OT_copy_render,
)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    bpy.types.VIEW3D_HT_header.append(draw_viewport_button)
    bpy.types.IMAGE_HT_header.append(draw_image_button)


def unregister():
    bpy.types.VIEW3D_HT_header.remove(draw_viewport_button)
    bpy.types.IMAGE_HT_header.remove(draw_image_button)
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
