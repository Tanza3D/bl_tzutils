import bpy
from bpy.props import (
    StringProperty,
    PointerProperty,
    CollectionProperty,
    IntProperty,
    BoolProperty,
    EnumProperty,
    FloatProperty,
    FloatVectorProperty,
)
from mathutils import Vector, Quaternion, Euler, Matrix


def action_fcurves(action):
    """blender 5.x layered actions keep fcurves under layers/strips/channelbags
    rather than on the action itself."""
    for layer in action.layers:
        for strip in layer.strips:
            for cb in strip.channelbags:
                for fc in cb.fcurves:
                    yield fc


def source_bone_keys(action):
    """{bone name: {frame: interpolation}} across every pose-bone channel.

    mocap isn't necessarily baked to every frame -- a mixamo action can sit
    on sparse keys with gaps of several frames -- so copying the animation
    faithfully means keying where IT is keyed, not everywhere."""
    out = {}
    for fc in action_fcurves(action):
        if not fc.data_path.startswith('pose.bones["'):
            continue
        bone = fc.data_path.split('"')[1]
        per = out.setdefault(bone, {})
        for kp in fc.keyframe_points:
            per.setdefault(int(round(kp.co[0])), kp.interpolation)
    return out


def contributing_source_bones(source_armature, mapping):
    """the source bones whose animation actually feeds this mapping.

    an IK target moves whenever anything in its limb moves, and a pole
    depends on all three joints of the triangle -- so those follow the union
    of their chain's keys, not just the one bone they're named after."""
    if mapping.role == "IK_TARGET" and mapping.chain_root_bone:
        return chain_bone_names(
            source_armature, mapping.chain_root_bone, mapping.source_bone
        )
    if mapping.role == "POLE":
        names = [mapping.source_bone]
        if mapping.chain_root_bone:
            names.append(mapping.chain_root_bone)
        if mapping.chain_end_bone:
            names.append(mapping.chain_end_bone)
        return names
    return [mapping.source_bone]


def world_rest_matrix(armature_obj, bone_name):
    """a bone's rest orientation matrix in world space (rotation only)."""
    bone = armature_obj.data.bones.get(bone_name)
    if not bone:
        return None
    return (armature_obj.matrix_world @ bone.matrix_local).to_3x3().to_4x4()


def world_rest_head(armature_obj, bone_name):
    bone = armature_obj.data.bones.get(bone_name)
    if not bone:
        return None
    return armature_obj.matrix_world @ bone.head_local


def bone_rest_length(armature_obj, bone_name):
    bone = armature_obj.data.bones.get(bone_name)
    if not bone:
        return None
    head = armature_obj.matrix_world @ bone.head_local
    tail = armature_obj.matrix_world @ bone.tail_local
    return (tail - head).length


_NON_CONTROL_PREFIXES = ("mch-", "def-", "org-", "vis_")


def _is_control_bone(name):
    lower = name.lower()
    return not lower.startswith(_NON_CONTROL_PREFIXES)


def guess_target_bone(src_name, target_armature):
    """fuzzy-match a mixamo bone name to an unprefixed control bone on
    the target armature (rigify-style rigs only expose those to animators)."""
    if not target_armature:
        return ""

    clean = src_name
    if ":" in clean:
        clean = clean.split(":", 1)[1]

    for prefix in ("mixamorig1", "mixamorig2", "mixamorig"):
        if clean.lower().startswith(prefix.lower()):
            clean = clean[len(prefix) :]
            break

    side = ""
    lower = clean.lower()
    if lower.startswith("left"):
        side = "l"
        clean = clean[4:]
    elif lower.startswith("right"):
        side = "r"
        clean = clean[5:]

    import re

    tokens = re.findall(r"[A-Z]?[a-z]+|[A-Z]+(?![a-z])|\d+", clean)
    key = "".join(t.lower() for t in tokens)

    synonyms = [
        ("hips", ["torso"]),
        ("spine2", ["chest"]),
        ("spine1", ["spine_fk.001"]),
        ("spine", ["spine_fk"]),
        ("neck", ["neck"]),
        ("head", ["head"]),
        ("shoulder", ["shoulder"]),
        ("forearm", ["forearm_fk"]),
        ("arm", ["upper_arm_fk"]),
        ("hand", ["hand_fk"]),
        ("upleg", ["thigh_fk"]),
        ("leg", ["shin_fk"]),
        ("foot", ["foot_fk"]),
        ("toebase", ["toe_fk"]),
    ]

    candidates = []
    for word, frags in synonyms:
        if word in key:
            candidates.extend(frags)
            break

    if not candidates:
        return ""

    bone_names = [b for b in target_armature.data.bones.keys() if _is_control_bone(b)]
    for frag in candidates:
        matches = []
        for bn in bone_names:
            bnl = bn.lower()
            if frag not in bnl:
                continue
            if side:
                if f".{side}" not in bnl and f"_{side}" not in bnl:
                    continue
            else:
                if ".l" in bnl or ".r" in bnl:
                    continue

            base = bnl.split(".l")[0].split(".r")[0] if side else bnl
            matches.append((0 if base == frag else 1, len(bn), bn))
        if matches:
            matches.sort()
            return matches[0][2]
    return ""


class ART_BoneMapItem(bpy.types.PropertyGroup):
    source_bone: StringProperty(name="Source Bone")
    target_bone: StringProperty(name="Target Bone")
    role: EnumProperty(
        name="Role",
        items=[
            ("NONE", "FK", "copy rotation only, world-space delta from rest"),
            (
                "IK_TARGET",
                "IK Target",
                "drive this control bone's location from the source chain end, scaled",
            ),
            (
                "POLE",
                "Pole",
                "drive this control bone's location as a pole target, scaled",
            ),
        ],
        default="NONE",
    )

    chain_root_bone: StringProperty(name="Chain Root (source)")

    chain_end_bone: StringProperty(name="Chain End (source)")
    rot_mode: EnumProperty(
        name="Rotation",
        items=[
            (
                "DELTA",
                "From Rest",
                "apply the source bone's rotation relative to its own rest pose. right for FK joints -- spine, limbs, head",
            ),
            (
                "ABSOLUTE",
                "Match World",
                "take the source bone's world orientation outright. right for IK end effectors (hands/feet), where the rig's rest roll differs from the source's",
            ),
        ],
        default="DELTA",
    )

    rotation_offset: FloatVectorProperty(
        name="Rotation Offset",
        subtype="EULER",
        size=3,
        default=(0.0, 0.0, 0.0),
        unit="ROTATION",
    )
    enabled: BoolProperty(default=True)


class ART_Settings(bpy.types.PropertyGroup):
    source: PointerProperty(
        name="Source (Mixamo)",
        type=bpy.types.Object,
        description="animated mixamo armature",
        poll=lambda self, obj: obj.type == "ARMATURE",
    )
    scale_ref: PointerProperty(
        name="Scale Reference",
        type=bpy.types.Object,
        description="copy of the source armature, reposed in edit mode to match the target's proportions",
        poll=lambda self, obj: obj.type == "ARMATURE",
    )
    target: PointerProperty(
        name="Target Rig",
        type=bpy.types.Object,
        description="the rig to retarget onto (drives FK bones + IK/pole controls)",
        poll=lambda self, obj: obj.type == "ARMATURE",
    )

    bone_map: CollectionProperty(type=ART_BoneMapItem)
    bone_map_index: IntProperty(default=0)

    key_source_frames: BoolProperty(
        name="Match Source Keyframes",
        description=(
            "key only on the frames the source is actually keyed on, reusing its "
            "interpolation, rather than baking every frame. keeps the result "
            "editable and matching the original's timing. note that IK and pole "
            "targets are interpolated along straight lines between those keys, so "
            "a fast arc over a long gap can cut its corner -- turn this off to bake "
            "every frame if that shows"
        ),
        default=True,
    )

    use_scene_range: BoolProperty(name="Use Scene Frame Range", default=True)
    frame_start: IntProperty(name="Start", default=1)
    frame_end: IntProperty(name="End", default=250)

    pole_distance: FloatProperty(
        name="Pole Distance",
        description="how far out pole targets sit from the joint, scaled with the limb's length ratio",
        default=0.5,
        min=0.0,
    )

    pole_smoothing: FloatProperty(
        name="Pole Smoothing",
        description=(
            "smooth the elbow/knee bend direction over time. the bend direction is a "
            "perpendicular residual, so even clean mocap produces a very noisy one -- "
            "raising this trades a frame or two of lag for a steady pole. 0 uses the raw "
            "per-frame direction"
        ),
        default=0.7,
        min=0.0,
        max=0.95,
    )


def build_ratio_cache(art):
    """per-source-bone rest length ratio: scale_ref length / source length."""
    cache = {}
    for bone in art.source.data.bones:
        src_len = bone_rest_length(art.source, bone.name)
        ref_len = bone_rest_length(art.scale_ref, bone.name)
        if src_len and ref_len and src_len > 1e-8:
            cache[bone.name] = ref_len / src_len
        else:
            cache[bone.name] = 1.0
    return cache


def chain_bone_names(source_armature, root_name, end_name, max_len=32):
    """bone names from end_name up to (and including) root_name, walking
    the source armature's rest-pose parent hierarchy."""
    bones = source_armature.data.bones
    chain = []
    b = bones.get(end_name)
    steps = 0
    while b and steps < max_len:
        chain.append(b.name)
        if b.name == root_name:
            break
        b = b.parent
        steps += 1
    return chain


def average_chain_ratio(ratio_cache, chain):
    if not chain:
        return 1.0
    vals = [ratio_cache.get(n, 1.0) for n in chain]
    return sum(vals) / len(vals)


def find_root_item(source_armature, bone_map):
    """the one FK-role mapping whose source bone has no parent -- the
    mixamo hierarchy root (normally Hips). its translation is never
    otherwise touched, since every other FK bone is a pure rotation joint,
    so this is the only place root/world motion comes from."""
    for m in bone_map:
        if not (m.enabled and m.role == "NONE" and m.target_bone):
            continue
        src_bone = source_armature.data.bones.get(m.source_bone)
        if src_bone and src_bone.parent is None:
            return m
    return None


def find_leg_ratio(source_armature, ratio_cache, root_item, bone_map):
    """average bone-length ratio across the hip->foot chains, used to
    scale root/hip translation. using leg-specific ratio (rather than a
    blanket average across all bones, including arms/spine which may be
    scaled differently on a stylized rig) keeps floor contact accurate,
    since leg length is what actually governs standing height."""
    if not root_item:
        return None
    ratios = []
    for m in bone_map:
        if not (m.enabled and m.role == "IK_TARGET" and m.target_bone):
            continue
        if "foot" not in m.source_bone.lower():
            continue
        chain = chain_bone_names(source_armature, root_item.source_bone, m.source_bone)
        if chain:
            ratios.append(average_chain_ratio(ratio_cache, chain))
    if not ratios:
        return None
    return sum(ratios) / len(ratios)


def _find_ik_variant(target_armature, fk_guess, fk_token, ik_token):
    """given a guessed *_fk control bone name, find its *_ik sibling by
    swapping the token (e.g. hand_fk.L -> hand_ik.L). falls back to a
    straight search if the guess didn't contain the fk token."""
    if not target_armature:
        return ""
    bone_names = set(target_armature.data.bones.keys())
    if fk_guess and fk_token in fk_guess:
        candidate = fk_guess.replace(fk_token, ik_token)
        if candidate in bone_names:
            return candidate

    side = ""
    if fk_guess and (".l" in fk_guess.lower() or "_l" in fk_guess.lower()):
        side = "l"
    elif fk_guess and (".r" in fk_guess.lower() or "_r" in fk_guess.lower()):
        side = "r"
    for bn in bone_names:
        if not _is_control_bone(bn):
            continue
        bnl = bn.lower()
        if ik_token not in bnl:
            continue
        if side and f".{side}" not in bnl and f"_{side}" not in bnl:
            continue
        return bn
    return ""


def _find_pole_bone(target_armature, name_fragment, side):
    """find a control bone matching a pole-target naming fragment and side
    (e.g. 'upper_arm_ik_target' + 'l' -> 'upper_arm_ik_target.L')."""
    if not target_armature:
        return ""
    for bn in target_armature.data.bones.keys():
        if not _is_control_bone(bn):
            continue
        bnl = bn.lower()
        if name_fragment not in bnl:
            continue
        if side and f".{side}" not in bnl and f"_{side}" not in bnl:
            continue
        return bn
    return ""


def _limb_root(source_armature, end_effector_name, levels=2):
    """the top of a limb chain -- the shoulder for a hand, the thigh for a
    foot (hand -> forearm -> arm, so two levels up).

    anchoring an IK target at the limb's root rather than at its immediate
    parent means the whole limb's reach gets scaled as one unit, and the
    shoulder is a far steadier reference than the elbow."""
    bone = source_armature.data.bones.get(end_effector_name)
    for _ in range(levels):
        if not bone or not bone.parent:
            break
        bone = bone.parent
    return bone.name if bone else ""


def _add_pole_row(art, end_effector_source_bone, target_pole_bone):
    """add a bone map row for a pole target, derived from the limb's end
    effector: hand -> forearm (the elbow) -> arm (the shoulder).

    all three points are needed to get a bend direction perpendicular to
    the limb. note the middle one is the FOREARM, not the upper arm: a
    bone's head is its *upper* joint, so the upper arm's head is the
    shoulder -- using it puts the root and the middle of the triangle in
    the same place, leaving a degenerate bend vector that's pure noise."""
    end_bone = art.source.data.bones.get(end_effector_source_bone)
    if not end_bone or not end_bone.parent or not end_bone.parent.parent:
        return
    mid_bone = end_bone.parent
    root_bone = mid_bone.parent

    item = art.bone_map.add()
    item.source_bone = mid_bone.name
    item.target_bone = target_pole_bone
    item.role = "POLE"
    item.chain_root_bone = root_bone.name
    item.chain_end_bone = end_effector_source_bone
    item.enabled = True


class ART_OT_guess_mapping(bpy.types.Operator):
    bl_idname = "animretarget.guess_mapping"
    bl_label = "Guess Bone Mapping"
    bl_description = "auto-fill the bone map by matching mixamo bone names to target bone names (edit results before retargeting)"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        art = context.scene.art_settings
        if not art.source or not art.target:
            self.report({"ERROR"}, "set source and target armatures first")
            return {"CANCELLED"}

        art.bone_map.clear()
        hand_items = []
        foot_items = []

        for bone in art.source.data.bones:
            lname = bone.name.lower()
            side = "l" if "left" in lname else ("r" if "right" in lname else "")
            is_finger = any(
                f in lname for f in ("thumb", "index", "middle", "ring", "pinky")
            )

            is_junk = lname.endswith("_end") or "eye" in lname

            item = art.bone_map.add()
            item.source_bone = bone.name

            if is_finger or is_junk:

                item.target_bone = ""
                item.enabled = False
                continue

            guessed = guess_target_bone(bone.name, art.target)
            item.target_bone = guessed
            item.enabled = bool(guessed)

            if "hand" in lname:
                hand_items.append((item, side))
            elif (lname.endswith("foot") or ".foot" in lname) and "toe" not in lname:
                foot_items.append((item, side))

        for item, side in hand_items:
            ik_name = _find_ik_variant(
                art.target, item.target_bone, "hand_fk", "hand_ik"
            )
            if ik_name:
                item.target_bone = ik_name
            item.role = "IK_TARGET"
            item.chain_root_bone = _limb_root(art.source, item.source_bone)

        for item, side in foot_items:
            ik_name = _find_ik_variant(
                art.target, item.target_bone, "foot_fk", "foot_ik"
            )
            if ik_name:
                item.target_bone = ik_name
            item.role = "IK_TARGET"
            item.chain_root_bone = _limb_root(art.source, item.source_bone)

        for item, side in hand_items:
            pole_bone = _find_pole_bone(art.target, "upper_arm_ik_target", side)
            if pole_bone:
                _add_pole_row(art, item.source_bone, pole_bone)

        for item, side in foot_items:
            pole_bone = _find_pole_bone(art.target, "thigh_ik_target", side)
            if pole_bone:
                _add_pole_row(art, item.source_bone, pole_bone)

        claimed = set()
        clashes = 0
        for item in art.bone_map:
            if not (item.enabled and item.target_bone):
                continue
            key = (item.target_bone, item.role)
            if key in claimed:
                item.enabled = False
                clashes += 1
            else:
                claimed.add(key)

        found = sum(1 for i in art.bone_map if i.enabled and i.target_bone)
        msg = f"guessed {found} of {len(art.bone_map)} bones -- check the list before retargeting"
        if clashes:
            msg += f" ({clashes} duplicate target(s) disabled)"
        self.report({"INFO"}, msg)
        return {"FINISHED"}


class ART_OT_add_bone_map_item(bpy.types.Operator):
    bl_idname = "animretarget.add_bone_map_item"
    bl_label = "Add Bone Pair"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        art = context.scene.art_settings
        art.bone_map.add()
        art.bone_map_index = len(art.bone_map) - 1
        return {"FINISHED"}


class ART_OT_remove_bone_map_item(bpy.types.Operator):
    bl_idname = "animretarget.remove_bone_map_item"
    bl_label = "Remove Bone Pair"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        art = context.scene.art_settings
        idx = art.bone_map_index
        if 0 <= idx < len(art.bone_map):
            art.bone_map.remove(idx)
            art.bone_map_index = min(idx, len(art.bone_map) - 1)
        return {"FINISHED"}


class ART_OT_retarget(bpy.types.Operator):
    bl_idname = "animretarget.retarget"
    bl_label = "Retarget Animation"
    bl_description = "bake the source animation onto the target rig, scaling IK/pole targets using the scale reference armature"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        art = context.scene.art_settings
        src = art.source
        ref = art.scale_ref
        tgt = art.target

        if not (src and ref and tgt):
            self.report(
                {"ERROR"}, "source, scale reference, and target must all be set"
            )
            return {"CANCELLED"}
        if not (src.animation_data and src.animation_data.action):
            self.report({"ERROR"}, "source armature has no active action")
            return {"CANCELLED"}

        mapped = [m for m in art.bone_map if m.enabled and m.target_bone]
        if not mapped:
            self.report({"ERROR"}, "no enabled bone mappings")
            return {"CANCELLED"}

        for m in mapped:
            if m.role in ("IK_TARGET", "POLE") and not m.chain_root_bone:
                self.report(
                    {"ERROR"},
                    f"'{m.source_bone}' needs a Chain Root set (it's an IK/Pole target)",
                )
                return {"CANCELLED"}
            if m.role == "POLE" and not m.chain_end_bone:
                self.report(
                    {"ERROR"},
                    f"'{m.source_bone}' needs a Chain End set (it's a Pole target)",
                )
                return {"CANCELLED"}

        ratio_cache = build_ratio_cache(art)

        target_rest_rot = {}
        for m in mapped:
            if m.role not in ("NONE", "IK_TARGET"):
                continue
            bone = tgt.data.bones.get(m.target_bone)
            if bone:
                target_rest_rot[m.target_bone] = bone.matrix_local.to_quaternion()

        source_rest_world_rot = {}
        for m in mapped:
            if m.role not in ("NONE", "IK_TARGET"):
                continue
            mat = world_rest_matrix(src, m.source_bone)
            if mat is not None:
                source_rest_world_rot[m.source_bone] = mat.to_quaternion()

        root_item = find_root_item(src, mapped)
        root_ratio = (
            find_leg_ratio(src, ratio_cache, root_item, mapped) if root_item else None
        )
        if root_ratio is None:
            root_ratio = (
                (sum(ratio_cache.values()) / len(ratio_cache)) if ratio_cache else 1.0
            )

        root_source_rest_head = None
        root_target_rest_head = None
        if root_item:
            root_source_rest_head = world_rest_head(src, root_item.source_bone)
            root_target_rest_head = world_rest_head(tgt, root_item.target_bone)

        self.root_ratio = root_ratio
        self.root_source_rest_head = root_source_rest_head
        self.root_target_rest_head = root_target_rest_head

        self.limb_ratios = {}
        for m in mapped:
            if m.role in ("IK_TARGET", "POLE") and m.chain_root_bone:
                chain = chain_bone_names(src, m.chain_root_bone, m.source_bone)
                self.limb_ratios[m.source_bone] = average_chain_ratio(
                    ratio_cache, chain
                )

        self.last_bend_dir = {}

        if art.use_scene_range:
            frame_start = context.scene.frame_start
            frame_end = context.scene.frame_end
        else:
            frame_start = art.frame_start
            frame_end = art.frame_end

        per_bone_frames = {}
        if art.key_source_frames:
            src_keys = source_bone_keys(src.animation_data.action)

            for m in mapped if src_keys else []:
                merged = {}
                for bname in contributing_source_bones(src, m):
                    for f, interp in src_keys.get(bname, {}).items():
                        if frame_start <= f <= frame_end:
                            merged.setdefault(f, interp)
                if merged:

                    ordered = sorted(merged)
                    merged.setdefault(frame_start, merged[ordered[0]])
                    merged.setdefault(frame_end, merged[ordered[-1]])
                else:

                    merged = {frame_start: "LINEAR", frame_end: "LINEAR"}
                per_bone_frames[m.target_bone] = merged

        if per_bone_frames:
            sample_frames = sorted(
                {f for table in per_bone_frames.values() for f in table}
            )
        else:
            sample_frames = list(range(frame_start, frame_end + 1))

        if not tgt.animation_data:
            tgt.animation_data_create()
        action_name = f"{src.animation_data.action.name}_retarget"
        new_action = bpy.data.actions.new(action_name)
        tgt.animation_data.action = new_action

        scene = context.scene
        original_frame = scene.frame_current

        helpers = []
        temp_coll = bpy.data.collections.new("ART_retarget_temp")
        scene.collection.children.link(temp_coll)
        constrained = []

        try:
            for m in mapped:
                tgt_pbone = tgt.pose.bones.get(m.target_bone)
                if not tgt_pbone:
                    continue
                empty = bpy.data.objects.new(f"ART_tmp_{m.target_bone}", None)
                empty.empty_display_size = 0.05
                temp_coll.objects.link(empty)
                helpers.append((m, empty, tgt_pbone))

                wants_loc = m.role in ("IK_TARGET", "POLE") or (
                    root_item is not None and m.source_bone == root_item.source_bone
                )
                wants_rot = m.role != "POLE"

                if wants_loc:
                    c = tgt_pbone.constraints.new("COPY_LOCATION")
                    c.name = "ART_TEMP_loc"
                    c.target = empty
                    constrained.append((tgt_pbone, c))
                if wants_rot:
                    c = tgt_pbone.constraints.new("COPY_ROTATION")
                    c.name = "ART_TEMP_rot"
                    c.target = empty
                    constrained.append((tgt_pbone, c))

            baked = []
            for frame in sample_frames:
                scene.frame_set(frame)
                depsgraph = context.evaluated_depsgraph_get()
                src_eval = src.evaluated_get(depsgraph)

                for m, empty, tgt_pbone in helpers:
                    src_pbone = src_eval.pose.bones.get(m.source_bone)
                    if not src_pbone:
                        continue
                    world = self._desired_world_matrix(
                        art,
                        ratio_cache,
                        src,
                        src_eval,
                        tgt,
                        m,
                        tgt_pbone,
                        src_pbone,
                        source_rest_world_rot.get(m.source_bone),
                        target_rest_rot.get(m.target_bone),
                        root_item,
                    )
                    if world is not None:
                        empty.matrix_world = world

                bpy.context.view_layer.update()

                frame_pose = {}
                for m, empty, tgt_pbone in helpers:
                    frame_pose[m.target_bone] = tgt.convert_space(
                        pose_bone=tgt_pbone,
                        matrix=tgt_pbone.matrix,
                        from_space="POSE",
                        to_space="LOCAL",
                    ).copy()
                baked.append((frame, frame_pose))

        finally:

            for pbone, c in constrained:
                try:
                    pbone.constraints.remove(c)
                except (RuntimeError, ReferenceError):
                    pass
            for _, empty, _ in helpers:
                bpy.data.objects.remove(empty, do_unlink=True)
            bpy.data.collections.remove(temp_coll)

        prev_rot = {}
        for frame, frame_pose in baked:
            for m in mapped:
                tgt_pbone = tgt.pose.bones.get(m.target_bone)
                mat = frame_pose.get(m.target_bone)
                if not tgt_pbone or mat is None:
                    continue
                table = per_bone_frames.get(m.target_bone)
                if table is not None and frame not in table:
                    continue

                tgt_pbone.matrix_basis = mat
                prev = prev_rot.get(m.target_bone)

                if tgt_pbone.rotation_mode == "QUATERNION":
                    q = tgt_pbone.rotation_quaternion.copy()
                    if prev is not None and q.dot(prev) < 0.0:
                        q = Quaternion((-q.w, -q.x, -q.y, -q.z))
                        tgt_pbone.rotation_quaternion = q
                    prev_rot[m.target_bone] = q
                    tgt_pbone.keyframe_insert(
                        data_path="rotation_quaternion", frame=frame
                    )
                else:
                    e = (
                        mat.to_euler(tgt_pbone.rotation_mode, prev)
                        if prev is not None
                        else mat.to_euler(tgt_pbone.rotation_mode)
                    )
                    tgt_pbone.rotation_euler = e
                    prev_rot[m.target_bone] = e.copy()
                    tgt_pbone.keyframe_insert(data_path="rotation_euler", frame=frame)

                tgt_pbone.keyframe_insert(data_path="location", frame=frame)

        for fc in action_fcurves(new_action):
            if not fc.data_path.startswith('pose.bones["'):
                continue
            table = per_bone_frames.get(fc.data_path.split('"')[1])
            if not table:
                continue
            for kp in fc.keyframe_points:
                interp = table.get(int(round(kp.co[0])))
                if interp:
                    kp.interpolation = interp
            fc.update()

        scene.frame_set(original_frame)

        self.report(
            {"INFO"},
            f"retargeted {len(mapped)} bone(s) over {frame_end - frame_start + 1} frames onto '{new_action.name}'",
        )
        return {"FINISHED"}

    def _world_rotation_delta(
        self,
        src_obj,
        src_pbone,
        tgt_obj,
        src_rest_world_rot,
        tgt_rest_local_rot,
        rotation_offset=None,
        rot_mode="DELTA",
    ):
        """the target bone's desired world rotation.

        DELTA: apply the source bone's rotation delta from its own rest (in
        world space) on top of the target bone's own rest orientation. right
        for FK joints -- it transfers how far a joint bent, so it survives
        the two rigs having completely different bone orientations at rest.

        ABSOLUTE: take the source bone's world orientation outright. right
        for IK end effectors. DELTA *preserves* any rest-pose mismatch by
        design (identical source rest -> identical target rest), so when the
        two rigs' rest rolls differ -- e.g. this rig's hand_ik sits 60deg
        rolled about its own axis vs mixamo's hand -- every frame inherits
        that constant error. hands/feet want to point where the animation
        says they point, in world space, so match it directly instead.

        rotation_offset (euler, radians) is a fixed correction applied on
        top in the bone's own local axes, for dialing out whatever's left."""
        src_world_rot = (src_obj.matrix_world @ src_pbone.matrix).to_quaternion()

        if rot_mode == "ABSOLUTE":
            result = src_world_rot
        else:
            if src_rest_world_rot is None or tgt_rest_local_rot is None:
                return None
            delta = src_world_rot @ src_rest_world_rot.inverted()
            tgt_rest_world_rot = (
                tgt_obj.matrix_world.to_quaternion() @ tgt_rest_local_rot
            )
            result = delta @ tgt_rest_world_rot

        if rotation_offset is not None and tuple(rotation_offset) != (0.0, 0.0, 0.0):
            offset_quat = Euler(tuple(rotation_offset), "XYZ").to_quaternion()
            result = result @ offset_quat
        return result

    def _body_space(self, world_point):
        """map a point from the source's world space into the target's,
        using the same body-scale transform the root translation uses.

        this is what keeps IK targets steady. anchoring them off the target
        rig's *current* pose (its elbow, its knee) meant every retargeted
        rotation upstream -- torso, chest, shoulder, upper arm -- fed its
        own small error into the hand's position, so a source hand moving
        smoothly came out visibly noisy, and the first frames needed a
        couple of passes to settle because the chain hadn't converged yet.
        derived purely from source data plus fixed rest constants, an IK
        target is as smooth as the animation it came from."""
        if self.root_source_rest_head is None or self.root_target_rest_head is None:
            return world_point
        return (
            self.root_target_rest_head
            + (world_point - self.root_source_rest_head) * self.root_ratio
        )

    def _desired_world_matrix(
        self,
        art,
        ratio_cache,
        src,
        src_eval,
        tgt,
        mapping,
        tgt_pbone,
        src_pbone,
        src_rest_world_rot,
        tgt_rest_local_rot,
        root_item,
    ):
        """the world transform this control bone should end up at.

        derived entirely from the source rig plus fixed rest constants --
        it never reads the target's own evolving pose. that's what makes
        the read phase possible: the whole animation can be worked out
        before a single channel is written."""
        world_rotation = None
        world_translation = None

        if mapping.role == "NONE":
            world_rotation = self._world_rotation_delta(
                src,
                src_pbone,
                tgt,
                src_rest_world_rot,
                tgt_rest_local_rot,
                mapping.rotation_offset,
                mapping.rot_mode,
            )
            if root_item is not None and mapping.source_bone == root_item.source_bone:
                world_translation = self._body_space(src.matrix_world @ src_pbone.head)

        elif mapping.role == "IK_TARGET":
            world_translation, world_rotation = self._ik_target_transform(
                art,
                ratio_cache,
                src,
                src_eval,
                tgt,
                mapping,
                src_rest_world_rot,
                tgt_rest_local_rot,
            )

        elif mapping.role == "POLE":
            world_translation = self._pole_position(
                art, ratio_cache, src, src_eval, tgt, mapping
            )

        if world_rotation is None and world_translation is None:
            return None

        mat = (
            world_rotation.to_matrix().to_4x4()
            if world_rotation is not None
            else Matrix.Identity(4)
        )
        if world_translation is None:

            world_translation = tgt.matrix_world @ tgt_pbone.head
        mat.translation = world_translation
        return mat

    def _ik_target_transform(
        self,
        art,
        ratio_cache,
        src,
        src_eval,
        tgt,
        mapping,
        src_rest_world_rot,
        tgt_rest_local_rot,
    ):
        """an IK control bone's location AND rotation.

        location: place the limb's root (shoulder/hip) in the target's body
        space, then add the limb's own reach vector scaled by that limb's
        length ratio. splitting it this way means body placement scales with
        the body and reach scales with the limb, which is what a rig with
        different proportions actually needs.

        rotation: IK control bones on rigify-style rigs drive the end
        effector's orientation directly -- it isn't solved from the chain --
        so it has to be set explicitly or hands/feet just keep their
        starting rotation all the way through."""
        limb_ratio = self.limb_ratios.get(mapping.source_bone, 1.0)

        src_root = src_eval.pose.bones.get(mapping.chain_root_bone)
        src_end = src_eval.pose.bones.get(mapping.source_bone)
        if not src_root or not src_end:
            return None, None

        src_root_world = src.matrix_world @ src_root.head
        src_end_world = src.matrix_world @ src_end.head

        limb_root_target = self._body_space(src_root_world)
        world_target = limb_root_target + (src_end_world - src_root_world) * limb_ratio

        world_rotation = self._world_rotation_delta(
            src,
            src_end,
            tgt,
            src_rest_world_rot,
            tgt_rest_local_rot,
            mapping.rotation_offset,
            mapping.rot_mode,
        )
        return world_target, world_rotation

    def _pole_position(self, art, ratio_cache, src, src_eval, tgt, mapping):
        """a pole target's location, from the limb's actual bend
        direction: how far the elbow/knee deviates from the straight line
        between the limb's root and its end effector. the raw root->elbow
        vector points along the limb itself, which places the pole
        somewhere useless."""
        limb_ratio = self.limb_ratios.get(mapping.source_bone, 1.0)

        src_root = src_eval.pose.bones.get(mapping.chain_root_bone)
        src_mid = src_eval.pose.bones.get(mapping.source_bone)
        src_end = src_eval.pose.bones.get(mapping.chain_end_bone)
        if not src_root or not src_mid or not src_end:
            return

        root_world = src.matrix_world @ src_root.head
        mid_world = src.matrix_world @ src_mid.head
        end_world = src.matrix_world @ src_end.head

        straight = end_world - root_world
        limb_len = straight.length
        straight_dir = straight.normalized() if limb_len > 1e-6 else Vector((0, -1, 0))

        to_mid = mid_world - root_world
        projected_point = root_world + straight_dir * to_mid.dot(straight_dir)
        bend_vec = mid_world - projected_point

        key = mapping.source_bone
        prev = self.last_bend_dir.get(key)

        if bend_vec.length > max(limb_len * 0.02, 1e-5):
            raw_dir = bend_vec.normalized()
        else:
            raw_dir = prev if prev is not None else Vector((0, -1, 0))

        if prev is None:
            bend_dir = raw_dir
        else:
            alpha = 1.0 - art.pole_smoothing
            bend_dir = prev.lerp(raw_dir, alpha)
            bend_dir = bend_dir.normalized() if bend_dir.length > 1e-6 else raw_dir
        self.last_bend_dir[key] = bend_dir

        mid_target = (
            self._body_space(root_world) + (mid_world - root_world) * limb_ratio
        )
        world_target = mid_target + bend_dir * max(art.pole_distance * limb_ratio, 0.01)

        return world_target


class ART_UL_bone_map(bpy.types.UIList):
    def draw_item(
        self, context, layout, data, item, icon, active_data, active_propname
    ):
        row = layout.row(align=True)
        row.prop(item, "enabled", text="")
        row.label(text=item.source_bone)
        row.label(text="", icon="FORWARD")
        target_armature = context.scene.art_settings.target
        row.prop_search(
            item,
            "target_bone",
            target_armature.data if target_armature else data,
            "bones",
            text="",
        )
        row.prop(item, "role", text="")


class ART_PT_panel(bpy.types.Panel):
    bl_label = "TZU/Anim Retarget"
    bl_idname = "ART_PT_panel"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "TzUtils"

    def draw(self, context):
        layout = self.layout
        art = context.scene.art_settings

        col = layout.column(align=True)
        col.prop(art, "source")
        col.prop(art, "scale_ref")
        col.prop(art, "target")

        layout.separator()

        layout.prop(art, "key_source_frames")

        row = layout.row()
        row.prop(art, "use_scene_range")
        if not art.use_scene_range:
            row = layout.row(align=True)
            row.prop(art, "frame_start")
            row.prop(art, "frame_end")

        col = layout.column(align=True)
        col.prop(art, "pole_distance")
        col.prop(art, "pole_smoothing")

        layout.separator()
        layout.operator("animretarget.guess_mapping", icon="VIEWZOOM")

        row = layout.row()
        row.template_list(
            "ART_UL_bone_map", "", art, "bone_map", art, "bone_map_index", rows=6
        )
        col = row.column(align=True)
        col.operator("animretarget.add_bone_map_item", icon="ADD", text="")
        col.operator("animretarget.remove_bone_map_item", icon="REMOVE", text="")

        if 0 <= art.bone_map_index < len(art.bone_map):
            item = art.bone_map[art.bone_map_index]
            if item.role in ("IK_TARGET", "POLE"):
                box = layout.box()
                box.prop_search(
                    item,
                    "chain_root_bone",
                    art.source.data if art.source else item,
                    "bones",
                    text="Chain Root",
                )
                if item.role == "POLE":
                    box.prop_search(
                        item,
                        "chain_end_bone",
                        art.source.data if art.source else item,
                        "bones",
                        text="Chain End",
                    )
            if item.role in ("NONE", "IK_TARGET"):
                box = layout.box()
                box.prop(item, "rot_mode", text="Rotation")
                box.label(text="Rotation Offset")
                box.prop(item, "rotation_offset", text="")

        layout.separator()
        row = layout.row()
        row.scale_y = 1.5
        row.operator("animretarget.retarget", icon="ARMATURE_DATA")


classes = (
    ART_BoneMapItem,
    ART_Settings,
    ART_OT_guess_mapping,
    ART_OT_add_bone_map_item,
    ART_OT_remove_bone_map_item,
    ART_OT_retarget,
    ART_UL_bone_map,
    ART_PT_panel,
)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    bpy.types.Scene.art_settings = PointerProperty(type=ART_Settings)


def unregister():
    try:
        del bpy.types.Scene.art_settings
    except AttributeError:
        pass
    for cls in reversed(classes):
        try:
            bpy.utils.unregister_class(cls)
        except RuntimeError:
            pass
