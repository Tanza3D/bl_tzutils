import bpy

addon_keymaps = []

def register():
    wm = bpy.context.window_manager
    kc = wm.keyconfigs.addon
    if not kc:
        return
    km = kc.keymaps.new(name='Mesh', space_type='EMPTY')
    
    kmi_loop = km.keymap_items.new('mesh.select_edge_loop_multi', 'L', 'PRESS', ctrl=True, shift=True)
    kmi_ring = km.keymap_items.new('mesh.select_edge_ring_multi', 'L', 'PRESS', ctrl=True, shift=True, alt=True)
    
    addon_keymaps.append((km, kmi_loop))
    addon_keymaps.append((km, kmi_ring))

def unregister():
    for km, kmi in addon_keymaps:
        km.keymap_items.remove(kmi)
    addon_keymaps.clear()
