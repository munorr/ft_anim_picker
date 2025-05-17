import maya.cmds as cmds
import maya.mel as mel
import os
import sys
import importlib
from . import main

def onMayaDroppedPythonFile(*args, **kwargs):
    """Function called when the file is dropped onto the Maya viewport"""
    main.run()
    setup_ft_tools()

def discover_ft_tools():
    """Discover all available FT tools that can be added to the menu"""
    ft_tools = []
    
    # List of known FT tool packages to check
    known_packages = [
        {
            'name': 'ft_tool_box',
            'display_name': 'FT Tool Box',
            'main_module': 'main',
            'main_function': 'run'
        },
        {
            'name': 'ft_anim_picker',
            'display_name': 'FT Anim Picker',
            'main_module': 'main',
            'main_function': 'ft_anim_picker_window'
        }
        # Add more tools here as they are developed
    ]
    
    # Get the directory of this script for direct imports if needed
    script_dir = os.path.dirname(os.path.abspath(__file__))
    parent_dir = os.path.dirname(script_dir)
    
    # Make sure paths are clean
    sys.path = [p for p in sys.path if p and '\0' not in str(p)]
    
    # Ensure parent directory is in path
    if parent_dir not in sys.path:
        sys.path.insert(0, parent_dir)
    
    # Check which packages are available in the current environment
    for package_info in known_packages:
        package_name = package_info['name']
        try:
            # Try to import the package
            try:
                package = importlib.import_module(package_name)
                # Force reload to get the latest version
                importlib.reload(package)
            except ImportError as ie:
                # If standard import fails, try direct import
                print(f"Standard import failed: {ie}, trying direct import...")
                if package_name == 'ft_tool_box' and os.path.exists(script_dir):
                    # We're already in ft_tool_box, so import directly
                    import __init__ as package
                    importlib.reload(package)
                else:
                    # Try to import from parent directory
                    package_path = os.path.join(parent_dir, package_name)
                    if os.path.exists(package_path):
                        sys.path.insert(0, package_path)
                        import __init__ as package
                        importlib.reload(package)
                    else:
                        raise ImportError(f"Could not find package {package_name}")
            
            # Get the version if available
            version = getattr(package, '__version__', '1.0.0')
            
            # Add version to display name
            display_name = f"{package_info['display_name']} (v{version})"
            
            # Create the command string - use a more robust approach
            if package_name == 'ft_tool_box' and os.path.exists(script_dir):
                # For ft_tool_box, use a direct import approach since we're already in the package
                command = f"import sys; sys.path.append(r'{parent_dir}'); "
                command += f"import {package_name}.{package_info['main_module']} as module; "
                command += f"module.{package_info['main_function']}()"
            else:
                # Standard import approach for other packages
                command = f"import {package_name}.{package_info['main_module']} as module; "
                command += f"module.{package_info['main_function']}()"
            
            # Add to list of available tools
            ft_tools.append({
                'name': package_name,
                'display_name': display_name,
                'command': command
            })
            
            print(f"Found FT tool: {display_name}")
        except ImportError as ie:
            print(f"FT tool not available: {package_info['display_name']} - {ie}")
        except Exception as e:
            print(f"Error checking for {package_info['display_name']}: {e}")
    
    return ft_tools

def setup_ft_tools():
    """Set up the FT Tools menu in Maya"""
    try:
        # Get the directory of this script
        script_dir = os.path.dirname(os.path.abspath(__file__))
        parent_dir = os.path.dirname(script_dir)
        
        # Clean sys.path to remove paths with null characters
        sys.path = [p for p in sys.path if p and '\0' not in str(p)]
        
        # Add the parent directory to the Python path
        if parent_dir not in sys.path:
            sys.path.insert(0, parent_dir)  # Insert at beginning to ensure it's found first
        
        # Add the script directory to the Python path if not already there
        if script_dir not in sys.path:
            sys.path.insert(0, script_dir)  # Insert at beginning to ensure it's found first
        
        # Create the FT menu if it doesn't exist
        if not cmds.menu('FTMenu', exists=True):
            # Get the main Maya window's menu bar
            gMainWindow = mel.eval('$temp=$gMainWindow')
            cmds.menu('FTMenu', label='FT', parent=gMainWindow, tearOff=True)
            print("Created new FT menu")
        
        # Clear any existing menu items to avoid duplicates
        menu_items = cmds.menu('FTMenu', query=True, itemArray=True) or []
        for item in menu_items:
            cmds.deleteUI(item)
        
        # Discover available FT tools
        ft_tools = discover_ft_tools()
        
        if not ft_tools:
            print("Warning: No FT tools were discovered. Menu will only have uninstall option.")
        
        # Add menu items for each available tool
        for i, tool in enumerate(ft_tools):
            #if i > 0:
                #cmds.menuItem(divider=True, parent='FTMenu')
            
            cmds.menuItem(
                label=tool['display_name'],
                parent='FTMenu',
                command=tool['command']
            )
            print(f"Added menu item: {tool['display_name']}")
        
        # Add a separator and uninstall options at the end
        if ft_tools:
            cmds.menuItem(divider=True, parent='FTMenu')
        
        # Create an uninstall submenu
        cmds.menuItem(label='Uninstall', parent='FTMenu', subMenu=True)
        
        # Add uninstall option for FT Tool Box only
        uninstall_anim_picker_cmd = f"import sys; "
        uninstall_anim_picker_cmd += f"sys.path = [p for p in sys.path if p and '\\0' not in str(p)]; "  # Clean sys.path
        uninstall_anim_picker_cmd += f"sys.path.insert(0, r'{parent_dir}'); "  # Add parent dir to path
        uninstall_anim_picker_cmd += f"import importlib; "  # For reloading the module
        uninstall_anim_picker_cmd += f"import uninstall; importlib.reload(uninstall); uninstall.main('anim_picker')"
        
        cmds.menuItem(
            label='Uninstall FT Anim Picker',
            parent='Uninstall',
            command=uninstall_anim_picker_cmd
        )
        
        # Add uninstall option for All FT Tools
        uninstall_all_cmd = f"import sys; "
        uninstall_all_cmd += f"sys.path = [p for p in sys.path if p and '\\0' not in str(p)]; "  # Clean sys.path
        uninstall_all_cmd += f"sys.path.insert(0, r'{parent_dir}'); "  # Add parent dir to path
        uninstall_all_cmd += f"import importlib; "  # For reloading the module
        uninstall_all_cmd += f"import uninstall; importlib.reload(uninstall); uninstall.main('all')"
        
        cmds.menuItem(
            label='Uninstall All FT Tools',
            parent='Uninstall',
            command=uninstall_all_cmd
        )
        
        print("FT Tools menu has been set up successfully.")
        return True
    except Exception as e:
        print(f"Error setting up FT Tools menu: {e}")
        return False

# Run the setup function when this script is executed
if __name__ == "__main__":
    setup_ft_tools()
