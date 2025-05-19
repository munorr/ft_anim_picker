"""
Drag and drop this file into Maya to install the FT Anim Picker.

This will:
- Create a button in the active shelf with the FT Anim Picker logo
- The button will load/reload the FT Anim Picker tool
"""

import maya.cmds as cmds
import maya.mel as mel
import os
import sys

def create_ft_anim_picker_button():
    # Get the directory where this script is located
    script_dir = os.path.normpath(os.path.dirname(os.path.realpath(__file__)))
    # Get the parent directory (where ft_anim_picker is located)
    parent_dir = os.path.normpath(os.path.dirname(script_dir))
    
    # Define the icon path
    icon_path = os.path.join(script_dir, 'ft_picker_icons', 'ftap_logo_1080.png')
    
    # Create the command string - use raw string and normalize path
    parent_dir_normalized = parent_dir.replace("\\", "/")
    command_str = r'''
import sys
import os
sys.path.append("{0}")

import ft_anim_picker.__unload_pkg as unld

try:
	unld.unload(ft_anim_picker)
	import ft_anim_picker.main as ftap_window
	ftap_window.open()
except:
	import ft_anim_picker.main as ftap_window
	ftap_window.open()
	unld.unload(ft_anim_picker)
'''.format(parent_dir_normalized)
    
    # Get the active shelf
    gShelfTopLevel = mel.eval('$tmpVar=$gShelfTopLevel')
    active_shelf = cmds.tabLayout(gShelfTopLevel, query=True, selectTab=True)
    
    # Create the button
    button = cmds.shelfButton(
        label="FT Anim Picker",
        image=icon_path,
        command=command_str,
        parent=active_shelf,
        imageOverlayLabel="",
        overlayLabelColor=[1, 1, 1],
        overlayLabelBackColor=[0, 0, 0, 0],
    )
    
    print("FT Anim Picker button added to the '{0}' shelf.".format(active_shelf))
    return "FT Anim Picker button added to the '{0}' shelf.".format(active_shelf)

def onMayaDroppedPythonFile(*args, **kwargs):
    create_ft_anim_picker_button()

# This will be executed when the file is dropped into Maya
if __name__ == '__main__':
    onMayaDroppedPythonFile()
