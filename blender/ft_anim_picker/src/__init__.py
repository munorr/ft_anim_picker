"""FT Anim Picker - A powerful animation picker tool for Maya and Blender

Part of the Floating Tools (FT) collection.
"""

__version__ = '2.2.0'
__author__ = 'Floating Tools'

# Make main functions available at the package level
try:
    # Check if we're in Blender
    import bpy
    from .blender_main import open
except ImportError:
    # Fall back to Maya
    from .blender_main import open
