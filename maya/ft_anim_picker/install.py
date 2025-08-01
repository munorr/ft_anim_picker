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

def get_parent_dir():
    script_dir = os.path.normpath(os.path.dirname(os.path.realpath(__file__)))
    parent_dir = os.path.normpath(os.path.dirname(script_dir))
    parent_dir_normalized = parent_dir.replace("\\", "/")
    return parent_dir_normalized

def unload(pkg):
    pkg_dir = os.path.abspath(os.path.dirname(pkg.__file__))
    #print("dir is {}".format(pkg_dir))

    def _is_part_of_pkg(module_):
        mod_path = getattr(module_, "__file__", os.sep)

        if mod_path is not None:
            mod_dir = os.path.abspath(os.path.dirname(mod_path))
        else:
            return None

        return mod_dir.startswith(pkg_dir)

    to_unload = [name for name, module in sys.modules.items() if _is_part_of_pkg(module)]

    for name in to_unload:
        sys.modules.pop(name)
        #print("Unloaded {}.".format(name))

def create_ft_anim_picker_button():
    # Get the directory where this script is located
    script_dir = os.path.normpath(os.path.dirname(os.path.realpath(__file__)))
    # Get the parent directory (where ft_anim_picker is located)
    parent_dir = os.path.normpath(os.path.dirname(script_dir))
    
    # Define the icon path
    icon_path = os.path.join(script_dir,'src', 'ft_picker_icons', 'ftap_logo_64.png')
    
    # Create the command string - use raw string and normalize path
    parent_dir_normalized = parent_dir.replace("\\", "/")
    command_str = r'''import sys
import os
sys.path.append("{0}")

import ft_anim_picker.src as ftap
import ft_anim_picker.src.__unload_pkg as unld

try:
	unld.unload(ftap)
	import ft_anim_picker.src.main as ftap_window
	ftap_window.open()
except:
	import ft_anim_picker.src.main as ftap_window
	ftap_window.open()
	unld.unload(ftap)
'''.format(parent_dir_normalized)
    
    # Get the active shelf
    gShelfTopLevel = mel.eval('$tmpVar=$gShelfTopLevel')
    
    # Create the button
    if gShelfTopLevel:
        current_shelf = cmds.tabLayout(gShelfTopLevel, query=True, selectTab=True)
        shelf_button = cmds.shelfButton(
            label="FT Anim Picker (v2.2.2)",
            image=icon_path,
            command=command_str,
            parent=current_shelf,
            imageOverlayLabel="",
            overlayLabelColor=[1, 1, 1],
            overlayLabelBackColor=[0, 0, 0, 0],
        )
        print("Button created:", shelf_button)
    else:
        cmds.warning("No active shelf found.")

def onMayaDroppedPythonFile(*args, **kwargs):
    try:
        sys.path.append(get_parent_dir())
        import ft_anim_picker
        unload(ft_anim_picker)
    except:
        pass
    create_ft_anim_picker_button()
    

# This will be executed when the file is dropped into Maya
if __name__ == '__main__':
    onMayaDroppedPythonFile()