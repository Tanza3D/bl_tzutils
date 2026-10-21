import bpy
import re
from bpy.props import StringProperty, FloatProperty, BoolProperty, PointerProperty, CollectionProperty, IntProperty

class QVG_Pattern(bpy.types.PropertyGroup):
    pattern: StringProperty(name="Pattern", default=".*")


class QVG_Settings(bpy.types.PropertyGroup):
    patterns: CollectionProperty(type=QVG_Pattern)
    active_pattern: IntProperty(default=0)
    weight: FloatProperty(name="Weight", min=0.0, max=1.0, default=1.0)
    show_vgroups: BoolProperty(name="Show Vertex Groups", default=False)
    invert: BoolProperty(name="Invert Selection", default=False)

def compile_patterns(qvg):
    # returns a list of compiled regexes, or None if any of them are broken
    compiled = []
    for item in qvg.patterns:
        try:
            compiled.append(re.compile(item.pattern))
        except re.error:
            return None
    return compiled


def name_matches(compiled, name, invert):
    matched = False
    for pattern in compiled:
        if pattern.fullmatch(name) is not None:
            matched = True
            break

    if invert:
        return not matched
    return matched


class QVG_UL_patterns(bpy.types.UIList):
    def draw_item(self, context, layout, data, item, icon, active_data, active_propname, index):
        valid = True
        try:
            re.compile(item.pattern)
        except re.error:
            valid = False

        row = layout.row(align=True)
        row.alert = not valid
        row.prop(item, "pattern", text="", emboss=False)


class QVG_OT_pattern_add(bpy.types.Operator):
    bl_idname = "qvg.pattern_add"
    bl_label = "Add Pattern"

    def execute(self, context):
        qvg = context.scene.qvg_settings
        qvg.patterns.add()
        qvg.active_pattern = len(qvg.patterns) - 1
        return {'FINISHED'}


class QVG_OT_pattern_remove(bpy.types.Operator):
    bl_idname = "qvg.pattern_remove"
    bl_label = "Remove Pattern"

    def execute(self, context):
        qvg = context.scene.qvg_settings
        if len(qvg.patterns) == 0:
            return {'CANCELLED'}
        qvg.patterns.remove(qvg.active_pattern)
        qvg.active_pattern = max(0, min(qvg.active_pattern, len(qvg.patterns) - 1))
        return {'FINISHED'}


class QVG_PT_panel(bpy.types.Panel):
    bl_label = "TZU/Vertex Groups"
    bl_idname = "QVG_PT_panel"
    bl_space_type = 'PROPERTIES'
    bl_region_type = 'WINDOW'
    bl_context = "data"
    bl_parent_id = "DATA_PT_vertex_groups"

    @classmethod
    def poll(cls, context):
        return context.object and context.object.type == 'MESH'

    def draw(self, context):
        layout = self.layout
        qvg = context.scene.qvg_settings
        obj = context.object

        row = layout.row()
        row.template_list("QVG_UL_patterns", "", qvg, "patterns", qvg, "active_pattern", rows=3)
        col = row.column(align=True)
        col.operator("qvg.pattern_add", text="", icon='ADD')
        col.operator("qvg.pattern_remove", text="", icon='REMOVE')

        compiled = compile_patterns(qvg)
        valid = compiled is not None

        text = "Valid Regex" if valid else "Invalid Regex"

        box = layout.box()
        row = box.row()
        row.prop(qvg, "show_vgroups", icon="TRIA_DOWN" if qvg.show_vgroups else "TRIA_RIGHT", emboss=False, text=text)

        if qvg.show_vgroups and obj:
            for vg in obj.vertex_groups:
                matched = False
                if valid:
                    matched = name_matches(compiled, vg.name, qvg.invert)
                icon = 'CHECKMARK' if matched else 'X'
                box.label(text=vg.name, icon=icon)

        layout.prop(qvg, "weight", slider=True)
        
        layout.separator()
        
        layout.prop(qvg, "invert")
        
        # mode-dependent buttons
        if obj.mode == 'EDIT':
            row = layout.row()
            row.operator("qvg.set_weight", text="Set")
            row.operator("qvg.remove_weight", text="Remove")
        else:  # object mode
            row = layout.row()
            row.alert = True
            row.operator("qvg.delete", text="Delete", icon='ERROR')
            layout.separator()
            layout.operator("qvg.mirror_weights", text="Mirror Weights R → L", icon='MOD_MIRROR')
            layout.operator("qvg.auto_weights", text="Auto Weight Matching Bones", icon='ARMATURE_DATA')

class QVG_OT_delete(bpy.types.Operator):
    bl_idname = "qvg.delete"
    bl_label = "Delete Vertex Groups"
    alt: BoolProperty(default=False)

    def invoke(self, context, event):
        self.alt = event.alt
        return self.execute(context)

    def execute(self, context):
        objs = [context.object]
        if self.alt:
            objs = [o for o in context.selected_objects if o.type == 'MESH']

        qvg = context.scene.qvg_settings
        compiled = compile_patterns(qvg)
        if compiled is None:
            self.report({'ERROR'}, "Invalid regex pattern")
            return {'CANCELLED'}

        for obj in objs:
            if obj.mode != 'OBJECT':
                self.report({'WARNING'}, f"{obj.name} must be in Object mode")
                continue
            to_delete = []
            for vg in obj.vertex_groups:
                matched = name_matches(compiled, vg.name, qvg.invert)
                if matched:
                    to_delete.append(vg)
            for vg in to_delete:
                obj.vertex_groups.remove(vg)

        return {'FINISHED'}

class QVG_OT_set_weight(bpy.types.Operator):
    bl_idname = "qvg.set_weight"
    bl_label = "Set Vertex Weight"

    def execute(self, context):
        obj = context.object
        qvg = context.scene.qvg_settings
        
        compiled = compile_patterns(qvg)
        if compiled is None:
            self.report({'ERROR'}, "Invalid regex pattern")
            return {'CANCELLED'}

        if obj.mode != 'EDIT':
            self.report({'WARNING'}, f"{obj.name} must be in Edit mode")
            return {'CANCELLED'}

        bpy.ops.object.mode_set(mode='OBJECT')
        for v in obj.data.vertices:
            if not v.select:
                continue
            for vg in obj.vertex_groups:
                matched = name_matches(compiled, vg.name, qvg.invert)
                if matched:
                    vg.add([v.index], qvg.weight, 'REPLACE')
        bpy.ops.object.mode_set(mode='EDIT')

        return {'FINISHED'}

class QVG_OT_mirror_weights(bpy.types.Operator):
    bl_idname = "qvg.mirror_weights"
    bl_label = "Mirror Weights R -> L"
    bl_description = "Copy all .R vertex group weights to their .L counterparts, using X axis mirror. Works with or without trailing number suffix."

    def execute(self, context):
        obj = context.object
        if not obj or obj.type != 'MESH':
            self.report({'ERROR'}, "No mesh object selected")
            return {'CANCELLED'}

        mesh = obj.data
        vgroups = obj.vertex_groups

        qvg = context.scene.qvg_settings
        compiled = compile_patterns(qvg)
        if compiled is None:
            self.report({'ERROR'}, "Invalid regex pattern")
            return {'CANCELLED'}

        def is_matched(name):
            return name_matches(compiled, name, qvg.invert)

        # build a map of R group name -> L group name, filtered by match
        pairs = {}
        for vg in vgroups:
            if not is_matched(vg.name):
                continue
            # matches e.g. DEF-mouth.bottom.R.010 or DEF-mouth.bottom.R
            m = re.match(r'^(.*?)\.R(\.\d+)?$', vg.name)
            if m:
                prefix = m.group(1)
                suffix = m.group(2) or ''
                l_name = f"{prefix}.L{suffix}"
                if l_name in vgroups:
                    pairs[vg.name] = l_name

        if not pairs:
            self.report({'WARNING'}, "No matching .R / .L group pairs found")
            return {'CANCELLED'}

        # build per-vertex weight lookup for all R groups
        # structure: {r_group_name: {vert_index: weight}}
        r_weights = {r: {} for r in pairs}
        for v in mesh.vertices:
            for ge in v.groups:
                vg = vgroups[ge.group]
                if vg.name in r_weights:
                    r_weights[vg.name][v.index] = ge.weight

        # mirror: find each vertex's X-mirrored counterpart and copy weight
        # build a spatial lookup: position -> vertex index
        from mathutils import Vector

        pos_map = {}
        for v in mesh.vertices:
            key = (round(v.co.x, 4), round(v.co.y, 4), round(v.co.z, 4))
            pos_map[key] = v.index

        mirrored = 0
        for r_name, l_name in pairs.items():
            l_vg = vgroups[l_name]
            # clear existing L weights first
            l_vg.remove([v.index for v in mesh.vertices])
            for vi, w in r_weights[r_name].items():
                co = mesh.vertices[vi].co
                # look up the mirrored position (flip X)
                mirror_key = (round(-co.x, 4), round(co.y, 4), round(co.z, 4))
                if mirror_key in pos_map:
                    l_vg.add([pos_map[mirror_key]], w, 'REPLACE')
                    mirrored += 1

        self.report({'INFO'}, f"Mirrored {len(pairs)} group pair(s), {mirrored} weight(s) copied")
        return {'FINISHED'}


class QVG_OT_remove_weight(bpy.types.Operator):
    bl_idname = "qvg.remove_weight"
    bl_label = "Remove Vertex Weight"

    def execute(self, context):
        obj = context.object
        qvg = context.scene.qvg_settings
        
        compiled = compile_patterns(qvg)
        if compiled is None:
            self.report({'ERROR'}, "Invalid regex pattern")
            return {'CANCELLED'}

        if obj.mode != 'EDIT':
            self.report({'WARNING'}, f"{obj.name} must be in Edit mode")
            return {'CANCELLED'}

        bpy.ops.object.mode_set(mode='OBJECT')
        for v in obj.data.vertices:
            if not v.select:
                continue
            for vg in obj.vertex_groups:
                matched = name_matches(compiled, vg.name, qvg.invert)
                if matched:
                    vg.remove([v.index])
        bpy.ops.object.mode_set(mode='EDIT')

        return {'FINISHED'}

def find_armature(obj):
    candidates = []
    for mod in obj.modifiers:
        if mod.type == 'ARMATURE' and mod.object is not None:
            candidates.append(mod.object)
    if obj.parent is not None and obj.parent.type == 'ARMATURE':
        candidates.append(obj.parent)

    # pick whichever armature has the most deform bones lining up with our vertex groups
    # starts at -1 so a mesh with no groups yet still gets the first armature
    best = None
    best_score = -1
    for arm in candidates:
        score = 0
        for bone in arm.data.bones:
            if bone.use_deform and bone.name in obj.vertex_groups:
                score += 1
        if score > best_score:
            best = arm
            best_score = score

    return best


class QVG_OT_auto_weights(bpy.types.Operator):
    bl_idname = "qvg.auto_weights"
    bl_label = "Auto Weight Matching Bones"
    bl_description = "Redo automatic weights, but only for bones matching the patterns"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        obj = context.object
        qvg = context.scene.qvg_settings

        if obj is None or obj.type != 'MESH' or obj.mode != 'OBJECT':
            self.report({'ERROR'}, "need a mesh in object mode")
            return {'CANCELLED'}

        compiled = compile_patterns(qvg)
        if compiled is None:
            self.report({'ERROR'}, "Invalid regex pattern")
            return {'CANCELLED'}

        arm = find_armature(obj)
        if arm is None:
            self.report({'ERROR'}, "couldn't find an armature for this mesh")
            return {'CANCELLED'}

        # temp copy of the armature
        tmp = arm.copy()
        tmp.data = arm.data.copy()
        tmp.animation_data_clear()
        context.scene.collection.objects.link(tmp)

        # remember stuff we're about to stomp on
        old_selected = list(context.selected_objects)
        old_active = context.view_layer.objects.active
        old_parent = obj.parent
        old_parent_type = obj.parent_type
        old_parent_bone = obj.parent_bone
        old_parent_inverse = obj.matrix_parent_inverse.copy()
        old_world = obj.matrix_world.copy()
        old_mod_names = set(m.name for m in obj.modifiers)

        kept = []
        try:
            # turn off deform on bones that don't match, so auto weights skips them
            for bone in tmp.data.bones:
                if bone.use_deform and name_matches(compiled, bone.name, qvg.invert):
                    kept.append(bone.name)
                else:
                    bone.use_deform = False

            for o in context.selected_objects:
                o.select_set(False)

            if not kept:
                self.report({'WARNING'}, "no bones matched")
                return {'CANCELLED'}

            # wipe old weights on those groups so it's a clean redo
            for name in kept:
                vg = obj.vertex_groups.get(name)
                if vg is not None:
                    vg.remove([v.index for v in obj.data.vertices])

            obj.select_set(True)
            tmp.select_set(True)
            context.view_layer.objects.active = tmp
            # the button lives in the properties editor, so run this from a 3d viewport
            view3d_area = None
            for area in context.screen.areas:
                if area.type == 'VIEW_3D':
                    view3d_area = area
                    break

            if view3d_area is None:
                self.report({'ERROR'}, "need a 3d viewport open")
                return {'CANCELLED'}

            region = None
            for r in view3d_area.regions:
                if r.type == 'WINDOW':
                    region = r
                    break

            with context.temp_override(
                area=view3d_area,
                region=region,
                active_object=tmp,
                object=tmp,
                selected_objects=[obj, tmp],
                selected_editable_objects=[obj, tmp],
            ):
                result = bpy.ops.object.parent_set(type='ARMATURE_AUTO')

            if 'FINISHED' not in result:
                self.report({'ERROR'}, f"auto weights didn't run ({result})")
                return {'CANCELLED'}

            made = 0
            for name in kept:
                if name in obj.vertex_groups:
                    made += 1
            print(f"tz auto weights: {made}/{len(kept)} groups exist after parent_set")
        finally:
            if context.object is not None and context.object.mode != 'OBJECT':
                bpy.ops.object.mode_set(mode='OBJECT')

            # remove the modifier parent_set added
            for mod in list(obj.modifiers):
                if mod.name not in old_mod_names:
                    obj.modifiers.remove(mod)

            # put the parenting back how it was
            obj.parent = old_parent
            obj.parent_type = old_parent_type
            obj.parent_bone = old_parent_bone
            obj.matrix_parent_inverse = old_parent_inverse
            obj.matrix_world = old_world

            tmp_data = tmp.data
            bpy.data.objects.remove(tmp)
            bpy.data.armatures.remove(tmp_data)

            for o in context.selected_objects:
                o.select_set(False)
            for o in old_selected:
                o.select_set(True)
            context.view_layer.objects.active = old_active

        self.report({'INFO'}, f"auto weighted {len(kept)} bone(s) using {arm.name}")
        return {'FINISHED'}


classes = (
    QVG_Pattern,
    QVG_Settings,
    QVG_UL_patterns,
    QVG_OT_pattern_add,
    QVG_OT_pattern_remove,
    QVG_OT_auto_weights,
    QVG_PT_panel,
    QVG_OT_set_weight,
    QVG_OT_remove_weight,
    QVG_OT_delete,
    QVG_OT_mirror_weights,
)

def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    bpy.types.Scene.qvg_settings = PointerProperty(type=QVG_Settings)

def unregister():
    for cls in reversed(classes):
        try:
            bpy.utils.unregister_class(cls)
        except RuntimeError:
            pass
    del bpy.types.Scene.qvg_settings
