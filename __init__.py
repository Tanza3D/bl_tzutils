bl_info = {
    "name": "TzUtils",
    "author": "Tanza",
    "version": (1, 0, 0),
    "blender": (2, 80, 0),
    "location": "Properties > Object Data",
    "description": ":3",
    "category": "Object",
}

import bpy
import importlib
import sys


module_names = [
    "quick_vertex_groups",
    "reload",
    "interpolation_toggle",
]

imported_modules = []

for name in module_names:
    full_name = f"{__name__}.{name}"
    if full_name in sys.modules:
        mod = importlib.reload(sys.modules[full_name])
    else:
        import importlib.util
        mod = importlib.import_module(full_name)
    imported_modules.append(mod)

def register():
    for mod in imported_modules:
        mod.register()

def unregister():
    for mod in reversed(imported_modules):
        mod.unregister()
