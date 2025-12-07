# NOTE:
# this system is designed to keep textures and assets in a single place per-file for my
# character folder - as such, it only ever functions/does anything when your blend file is
# in a folder named "chars_g" - it's main functionality is to move all textures that are
# referenced by or packed into the blend file into a "textures" folder next to the blend file
# and to store a screenshot of the viewport next to the file (upon saving)

# this probably isn't useful to you and you will never use it

import bpy
import os
import shutil
from bpy.app.handlers import persistent

def is_in_chars_g_folder(blend_filepath):
    folder_path = os.path.dirname(blend_filepath)

    while True:
        base = os.path.basename(folder_path)
        if "chars_g" in base:
            return True

        parent = os.path.dirname(folder_path)
        if parent == folder_path:
            return False

        folder_path = parent



def tz_copy_textures():
    blend = bpy.data.filepath
    if not blend:
        return

    if not is_in_chars_g_folder(blend):
        return

    folder = os.path.dirname(blend)
    tex_folder = os.path.join(folder, "textures")
    os.makedirs(tex_folder, exist_ok=True)

    temp_folder = os.path.join(folder, "__tz_unpack_temp__")
    os.makedirs(temp_folder, exist_ok=True)

    for img in bpy.data.images:
        if img.packed_file:
            try:
                img.unpack(method='WRITE_LOCAL')
            except:
                pass

    for img in bpy.data.images:
        if img.source != 'FILE':
            continue

        src = bpy.path.abspath(img.filepath)

        if not os.path.exists(src):
            try:
                src = os.path.join(temp_folder, img.name + ".png")
                img.save_render(src)
            except:
                continue

        dst = os.path.join(tex_folder, os.path.basename(src))

        if not os.path.exists(dst):
            try:
                shutil.copy2(src, dst)
            except:
                continue

        img.filepath = bpy.path.relpath(dst)

    try:
        for f in os.listdir(temp_folder):
            os.remove(os.path.join(temp_folder, f))
        os.rmdir(temp_folder)
    except:
        pass


def tz_delete_unused_textures():
    blend = bpy.data.filepath
    if not blend:
        return

    if not is_in_chars_g_folder(blend):
        return  

    folder = os.path.join(os.path.dirname(blend), "textures")
    if not os.path.exists(folder):
        return

    used_paths = set()
    for img in bpy.data.images:
        path = bpy.path.abspath(img.filepath)
        if path:
            used_paths.add(os.path.normpath(path))

    for f in os.listdir(folder):
        fpath = os.path.normpath(os.path.join(folder, f))
        if fpath not in used_paths and os.path.isfile(fpath):
            try:
                os.remove(fpath)
            except:
                pass

    for img in list(bpy.data.images):
        if img.users == 0:
            try:
                path = bpy.path.abspath(img.filepath)
                if path and os.path.exists(path):
                    os.remove(path)
                bpy.data.images.remove(img)
            except:
                pass


def tz_make_thumb():
    blend = bpy.data.filepath
    if not blend:
        return

    if not is_in_chars_g_folder(blend):
        return 

    win = bpy.context.window
    if not win:
        return

    scr = win.screen
    area = None
    region = None

    for a in scr.areas:
        if a.type == 'VIEW_3D':
            area = a
            break
    if not area:
        return

    for r in area.regions:
        if r.type == 'WINDOW':
            region = r
            break
    if not region:
        return

    folder = os.path.dirname(blend)
    out = os.path.join(folder, "blend_thumb.png")

    with bpy.context.temp_override(window=win, screen=scr, area=area, region=region):
        bpy.ops.screen.screenshot(filepath=out)


class TZ_OT_copy_tex(bpy.types.Operator):
    bl_idname = "tz.copy_textures"
    bl_label = "copy textures"

    def execute(self, context):
        tz_delete_unused_textures()
        tz_copy_textures()
        tz_make_thumb()
        return {'FINISHED'}


@persistent
def tz_save_handler(dummy):
    blend = bpy.data.filepath
    if not blend:
        return

    # Only run if the .blend file is in a folder containing 'chars_g'
    if not is_in_chars_g_folder(blend):
        return

    tz_delete_unused_textures()
    tz_copy_textures()
    tz_make_thumb()


def tz_draw_header(self, context):
    layout = self.layout
    layout.separator()
    layout.operator("tz.copy_textures", text="", icon="FILE_REFRESH")


classes = (
    TZ_OT_copy_tex,
)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)

    bpy.app.handlers.save_post.append(tz_save_handler)
    bpy.types.VIEW3D_HT_header.append(tz_draw_header)


def unregister():
    try:
        bpy.types.VIEW3D_HT_header.remove(tz_draw_header)
        bpy.app.handlers.save_post.remove(tz_save_handler)
    except:
        print("eh")

    for cls in reversed(classes):
        try:
            bpy.utils.unregister_class(cls)
        except:
            print("eh")
