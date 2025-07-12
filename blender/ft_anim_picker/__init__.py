bl_info = {
    "name": "FT Animation Picker",
    "author": "MUNORR - [Floating Tools]",
    "version": (2, 0, 0),
    "blender": (4, 0, 0),
    "location": "Main Menu > FT > Anim Picker",
    "description": "Animation picker for Blender",
    "category": "Animation",
}

import bpy
import sys
import os
from .src import utils as UT

# Make sure PySide6 is available
try:
    from PySide6 import QtWidgets
except ImportError:
    print("PySide6 not found. Please install it to use FT Animation Picker.")

# Add the src directory to the path
src_dir = os.path.join(os.path.dirname(__file__), "src")
if src_dir not in sys.path:
    sys.path.append(src_dir)

# Import the Blender-specific modules
from .src import blender_main

# Data is managed by the PickerDataManager class in src/data_management.py

# FT Main Menu class
class FT_MT_main_menu(bpy.types.Menu):
    bl_idname = "FT_MT_main_menu"
    bl_label = "FT"
    
    def draw(self, context):
        layout = self.layout
        layout.operator(blender_main.ANIM_OT_open_ft_picker.bl_idname, text="Anim Picker")

# Function to add the FT menu to the main menu bar
def add_ft_menu(self, context):
    self.layout.menu(FT_MT_main_menu.bl_idname)

# Register the addon
def register():
    # Register the main functionality
    blender_main.register()
    
    # Register the FT menu
    bpy.utils.register_class(FT_MT_main_menu)
    
    # Add the FT menu to the main menu bar (after the Help menu)
    bpy.types.TOPBAR_MT_editor_menus.append(add_ft_menu)

def unregister():
    # Remove the FT menu from the main menu bar
    bpy.types.TOPBAR_MT_editor_menus.remove(add_ft_menu)
    
    # Unregister the FT menu
    bpy.utils.unregister_class(FT_MT_main_menu)
    
    # Unregister the main functionality
    blender_main.unregister()

if __name__ == "__main__":
    register()
