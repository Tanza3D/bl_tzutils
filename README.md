# Collection of Blender scripts Iuse
you might find these helpful, you might not!

## quick_vertex_groups
Available under the vertex groups area in Data (properties panel) - allows for setting, removing, or deleting vertex groups by regex.

## interpolation_toggle
Quick default interpolation toggle above timeline so new keyframes can be changed quickly

## custom_fbx_importer
Custom fbx importer, intended for use alongside VRChat
When exporting this will:
- Remove all UV maps apart from maps called "Oven" (for texture bakes) and any which are prefixed with "KP_" (keep)
- Remove all materials (do them in unity)
- Save to the same folder as your blend file, with the same name as your blend file

The intent for this is that you can quickly iterate on your mesh, materials, and textures, without having to constantly delete uv maps or set your baking output to the main one and without having to mess with materials.