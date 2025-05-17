# FT Anim Picker

A powerful animation picker tool for Maya, part of the Floating Tools (FT) collection.

## Features

- Custom animation picker interface for Maya
- Pose button functionality with thumbnail support
- Copy and paste functionality for pose data
- Integrated with Maya's menu bar under the "FT" menu

## Installation

### Automatic Installation

1. Download or clone this repository to your local machine
2. Open Maya
3. Drag and drop the `install.py` file onto the Maya viewport
4. The installation script will automatically:
   - Set up the module file in your Maya modules directory
   - Create or update your userSetup.py to load the FT menu
   - Add the FT menu to your current Maya session
5. Restart Maya to complete the installation

### Manual Installation

1. Copy the entire `ft_anim_picker` directory to a location of your choice
2. Copy the `ft_tools.mod` file to your Maya modules directory:
   - Windows: `C:\Users\[username]\Documents\maya\[version]\modules`
   - macOS: `~/Library/Preferences/Autodesk/maya/[version]/modules`
   - Linux: `~/maya/[version]/modules`
3. Edit the module file to point to the location where you copied the `ft_anim_picker` directory
4. Add the following code to your Maya userSetup.py:
   ```python
   import sys
   sys.path.append(r'path/to/ft_anim_picker')
   import ft_anim_picker.ft_menu_setup as menu_setup
   menu_setup.setup_ft_tools()
   ```
5. Restart Maya

## Usage

After installation, you can access the FT Anim Picker from the Maya menu bar:

1. Click on the "FT" menu in the Maya menu bar
2. Select "FT Anim Picker" to open the tool

## Uninstallation

1. Remove the `ft_tools.mod` file from your Maya modules directory
2. Remove the FT Tools setup code from your userSetup.py
3. Restart Maya

## Adding More Tools to the FT Menu

To add more tools to the FT menu, modify the `ft_menu_setup.py` file and add additional menu items in the `setup_ft_tools()` function.
