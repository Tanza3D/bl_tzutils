import bpy

# what's on the "clipboard": (object name, modifier name)
_clip = {"obj": None, "mod": None}

SKIP = {"rna_type", "name", "type", "is_active", "is_override_data", "persistent_uid"}


def get_clip_mod():
    obj = bpy.data.objects.get(_clip["obj"] or "")
    if not obj:
        return None
    return obj.modifiers.get(_clip["mod"] or "")


def copy_modifier(src, dst):
    for prop in src.bl_rna.properties:
        pid = prop.identifier
        if pid in SKIP or prop.is_readonly:
            continue
        try:
            setattr(dst, pid, getattr(src, pid))
        except Exception:
            pass

    # geo nodes inputs live as custom props
    if src.type == 'NODES':
        dst.node_group = src.node_group
        for key in src.keys():
            try:
                dst[key] = src[key]
            except Exception:
                pass


class TZ_OT_copy_modifier(bpy.types.Operator):
    bl_idname = "tz.copy_modifier"
    bl_label = "Copy Modifier"
    bl_description = "Copy the active modifier"
    bl_options = {'REGISTER'}

    @classmethod
    def poll(cls, context):
        obj = context.object
        return obj and obj.modifiers.active

    def execute(self, context):
        mod = context.object.modifiers.active
        _clip["obj"] = context.object.name
        _clip["mod"] = mod.name
        self.report({'INFO'}, f"Copied {mod.name}")
        return {'FINISHED'}


class TZ_OT_paste_modifier(bpy.types.Operator):
    bl_idname = "tz.paste_modifier"
    bl_label = "Paste Modifier"
    bl_description = "Paste the copied modifier onto all selected objects (added below the active modifier)"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return get_clip_mod() is not None

    def execute(self, context):
        src = get_clip_mod()
        src_obj = bpy.data.objects[_clip["obj"]]
        targets = [o for o in context.selected_objects if o != src_obj] or [context.object]
        count = 0
        for obj in targets:
            if obj is None:
                continue
            active = obj.modifiers.active
            try:
                new = obj.modifiers.new(src.name, src.type)
            except Exception:
                continue
            if new is None:
                continue
            copy_modifier(src, new)
            # slot it in right under whatever was active
            if active:
                idx = list(obj.modifiers).index(active) + 1
                obj.modifiers.move(len(obj.modifiers) - 1, idx)
            obj.modifiers.active = new
            obj.update_tag()
            count += 1
        self.report({'INFO'}, f"Pasted {src.name} onto {count} object(s)")
        return {'FINISHED'}


def draw_buttons(self, context):
    row = self.layout.row(align=True)
    row.operator("tz.copy_modifier", text="Copy", icon='COPYDOWN')
    src = get_clip_mod()
    row.operator("tz.paste_modifier", text=f"Paste {src.name}" if src else "Paste", icon='PASTEDOWN')


classes = (TZ_OT_copy_modifier, TZ_OT_paste_modifier)


def register():
    for c in classes:
        bpy.utils.register_class(c)
    bpy.types.DATA_PT_modifiers.prepend(draw_buttons)


def unregister():
    bpy.types.DATA_PT_modifiers.remove(draw_buttons)
    for c in reversed(classes):
        bpy.utils.unregister_class(c)
