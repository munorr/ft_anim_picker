# FT Anim Picker

A powerful animation picker tool for 3D applications, part of the Floating Tools (FT) collection. This tool is available for both Maya and Blender, providing a consistent workflow across different 3D software platforms.

## Overview

FT Anim Picker is designed to streamline the animation workflow by providing a customizable interface for selecting and manipulating animation controls. The tool allows animators to create custom picker layouts that match their character rigs, making the animation process more efficient and intuitive.

## Features

- Custom animation picker interface for both Maya and Blender
- Pose button functionality with thumbnail support
- Copy and paste functionality for pose data
- Customizable picker layouts
- Character-specific picker configurations
- Cross-platform compatibility

## Repository Structure

- `/maya` - Contains the Maya implementation of FT Anim Picker
- `/blender` - Contains the Blender implementation of FT Anim Picker

## Installation

### Maya Installation

1. Download or clone this repository to your local machine
2. Open Maya
3. Drag and drop the `maya/ft_anim_picker/install.py` file onto the Maya viewport
4. The installation script will automatically add the FT Anim Picker to your active shelf
5. Restart Maya to complete the installation

### Blender Installation

Before installing the addon, make sure to install PySide6:

- Run Blender as administrator
- Open Python Console (Shift+F4)
- Run the following command:
```bash
import pip; pip.main(['install', 'PySide6'])
```

Then install the addon:

1. Download or clone this repository to your local machine
2. Open Blender
3. Go to File > User Preferences > Add-ons
4. Click on the "Install" button and select the `blender/ft_anim_picker` folder
5. Enable the addon by checking the box next to it
6. Restart Blender to complete the installation

## Usage

### Maya Usage

After installation, you can access the FT Anim Picker from your active shelf:

1. Click on the "FT Anim Picker" button in your active shelf
2. Create and customize your picker layout
3. Save your picker configuration for future use

### Blender Usage

After installation, you can access the FT Anim Picker from the main menu:

1. Click on the "FT Anim Picker" button in the top menu
2. Create and customize your picker layout
3. Save your picker configuration for future use

## Uninstallation

### Maya Uninstallation

1. Remove the FT Anim Picker button from your active shelf

### Blender Uninstallation

1. Go to File > User Preferences > Add-ons
2. Find the FT Anim Picker add-on and click on the "Uninstall" button

## License

[Specify your license information here]

## Contact

[Your contact information or support channels]
