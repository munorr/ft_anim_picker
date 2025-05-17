"""
FT Anim Picker Drag and Drop Installer
===================================

This file is designed to be dragged and dropped into Maya's viewport.
It will install the FT Anim Picker and set up the menu in the current session.

Usage:
    Simply drag and drop this file into Maya's viewport.
"""

import os
import sys
import importlib

def onMayaDroppedPythonFile(*args, **kwargs):
    """Function called when the file is dropped onto Maya's viewport"""
    print("\n" + "-"*50)
    print("Installing FT Anim Picker...")
    print("-"*50)
    
    # Get the directory of this script
    current_dir = os.path.dirname(os.path.abspath(__file__))
    parent_dir = os.path.dirname(current_dir)
    
    # Clean sys.path to remove any paths with null characters
    sys.path = [p for p in sys.path if p and '\0' not in str(p)]
    
    # Add the parent directory to sys.path if not already there
    if parent_dir not in sys.path:
        sys.path.insert(0, parent_dir)
    
    # Add the current directory to sys.path if not already there
    if current_dir not in sys.path:
        sys.path.insert(0, current_dir)
    
    # Clean up any existing ft_anim_picker modules from sys.modules
    modules_to_remove = [m for m in sys.modules if m.startswith('ft_anim_picker')]
    for module in modules_to_remove:
        try:
            del sys.modules[module]
            print(f"Removed existing module: {module}")
        except:
            pass
    
    try:
        # Import the install module directly from the current directory
        print("Importing install module...")
        
        # Use importlib to import the install module
        spec = importlib.util.spec_from_file_location(
            "install", 
            os.path.join(current_dir, "install.py")
        )
        install_module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(install_module)
        
        # Run the installation
        print("Running installation...")
        result = install_module.main()
        
        if result:
            print("\n" + "-"*50)
            print("FT Anim Picker has been successfully installed!")
            print("-"*50)
            
            # Force reload the menu setup module and set up the menu
            try:
                print("Setting up menu in current session...")
                
                # Import the menu setup module
                import ft_anim_picker.ft_menu_setup as menu_setup
                importlib.reload(menu_setup)
                
                # Delete existing FT menu if it exists
                import maya.cmds as cmds
                if cmds.menu('FTMenu', exists=True):
                    cmds.deleteUI('FTMenu')
                    print("Removed existing FT menu to refresh it")
                
                # Set up the menu
                menu_setup.setup_ft_tools()
                print("Menu has been set up in the current session.")
            except Exception as e:
                print(f"Error setting up menu: {e}")
                print("You may need to restart Maya for the menu to appear.")
        else:
            print("\n" + "-"*50)
            print("Installation completed with warnings. Check the output above.")
            print("-"*50)
    except Exception as e:
        print("\n" + "-"*50)
        print(f"Error during installation: {e}")
        print("Installation failed.")
        print("-"*50)

# Run the installer when this script is executed
if __name__ == "__main__":
    onMayaDroppedPythonFile()
