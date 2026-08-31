import bpy
import os


class OT_RepackNumberedTextures(bpy.types.Operator):
    bl_idname = "tz.repack_numbered_textures"
    bl_label = "Repack Textures as Numbered"
    bl_description = "Pack all textures, then unpack them to numbered filenames (001.png, 002.png, ...)"

    output_subdir: bpy.props.StringProperty(
        name="Subfolder",
        description="Subfolder relative to the .blend file to write textures into",
        default="textures",
    )

    prefix: bpy.props.StringProperty(
        name="Prefix",
        description="Optional filename prefix (e.g. 'tex_' -> tex_001.png)",
        default="",
    )

    def invoke(self, context, event):
        return context.window_manager.invoke_props_dialog(self)

    def draw(self, context):
        layout = self.layout
        layout.prop(self, "output_subdir")
        layout.prop(self, "prefix")

    def execute(self, context):
        if not bpy.data.filepath:
            self.report({'ERROR'}, "save the .blend file first")
            return {'CANCELLED'}

        output_dir = os.path.join(os.path.dirname(bpy.data.filepath), self.output_subdir)
        os.makedirs(output_dir, exist_ok=True)

        valid_exts = {".png", ".jpg", ".jpeg", ".tga", ".exr", ".hdr", ".tif", ".tiff", ".bmp"}

        packed_count = 0
        for img in bpy.data.images:
            if img.library:
                continue  # skip linked images — they're read-only
            if img.source in ("FILE", "SEQUENCE", "MOVIE") and not img.packed_file:
                try:
                    img.pack()
                    packed_count += 1
                except Exception as e:
                    self.report({'WARNING'}, f"couldn't pack '{img.name}': {e}")

        # unpack(method="WRITE_LOCAL") ignores filepath and derives its own path
        # from the image name, so write the packed bytes directly instead
        counter = 1
        unpacked_count = 0
        for img in bpy.data.images:
            if not img.packed_file:
                continue
            if img.library:
                continue  # skip linked images — they're read-only

            _, ext = os.path.splitext(img.name)
            if not ext or ext.lower() not in valid_exts:
                ext = ".png"

            numbered_name = f"{self.prefix}{counter:03d}{ext}"
            dest_path = os.path.join(output_dir, numbered_name)

            with open(dest_path, "wb") as f:
                f.write(img.packed_file.data)

            img.filepath = dest_path
            img.filepath_raw = dest_path
            img.unpack(method="USE_LOCAL")
            img.name = numbered_name

            counter += 1
            unpacked_count += 1

        self.report(
            {'INFO'},
            f"packed {packed_count} new image(s), unpacked {unpacked_count} total -> {output_dir}"
        )
        return {'FINISHED'}


def menu_draw(self, context):
    self.layout.separator()
    self.layout.operator(
        OT_RepackNumberedTextures.bl_idname,
        icon='IMAGE_DATA',
    )


classes = (OT_RepackNumberedTextures,)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    bpy.types.TOPBAR_MT_file_external_data.append(menu_draw)


def unregister():
    bpy.types.TOPBAR_MT_file_external_data.remove(menu_draw)
    for cls in reversed(classes):
        try:
            bpy.utils.unregister_class(cls)
        except Exception as e:
            print(f"failed to unregister {cls}: {e}")
