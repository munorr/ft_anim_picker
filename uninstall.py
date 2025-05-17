'''
FT Tools Uninstaller

This script provides options to uninstall either just the FT Anim Picker or all FT Tools from Maya.
'''

import os
import sys
import shutil
import maya.cmds as cmds
import maya.mel as mel


class FT_Tools_Uninstaller:
    """Class to handle FT Tools uninstallation process"""
    
    def __init__(self, uninstall_all=True):
        """Initialize the uninstaller with paths
        
        Args:
            uninstall_all (bool): If True, uninstall all FT Tools. If False, uninstall only FT Anim Picker.
        """
        self.uninstall_all = uninstall_all
        self.maya_version = int(mel.eval('getApplicationVersionAsFloat()'))
        self.maya_app_dir = os.path.normpath(os.path.expanduser('~/Documents/maya'))
        self.version_modules_dir = os.path.join(self.maya_app_dir, str(self.maya_version), 'modules')
        self.shared_modules_dir = os.path.join(self.maya_app_dir, 'modules')
        self.version_scripts_dir = os.path.join(self.maya_app_dir, str(self.maya_version), 'scripts')
        self.shared_scripts_dir = os.path.join(self.maya_app_dir, 'scripts')
        self.ft_anim_picker_path = os.path.dirname(os.path.abspath(__file__))
        
    def remove_menu(self):
        """Remove the FT menu from Maya if it exists or update it to remove FT Anim Picker"""
        if not cmds.menu('FTMenu', exists=True):
            print("FT menu not found in Maya's menu bar")
            return
            
        if self.uninstall_all:
            # Remove the entire menu
            cmds.deleteUI('FTMenu')
            print("Removed FT menu from Maya's menu bar")
        else:
            # Just update the menu to remove FT Anim Picker
            # We'll force a menu refresh after uninstalling FT Anim Picker
            # The menu setup will automatically exclude the uninstalled tool
            try:
                # Import the menu setup from ft_anim_picker if available
                sys.path = [p for p in sys.path if p and '\0' not in str(p)]  # Clean sys.path
                parent_dir = os.path.dirname(self.ft_anim_picker_path)
                if parent_dir not in sys.path:
                    sys.path.insert(0, parent_dir)
                    
                # Try to import ft_anim_picker's menu setup
                try:
                    import ft_anim_picker.ft_menu_setup as anim_picker_menu
                    # Delete existing menu
                    if cmds.menu('FTMenu', exists=True):
                        cmds.deleteUI('FTMenu')
                    # Set up the menu again (will only include available tools)
                    anim_picker_menu.setup_ft_tools()
                    print("Updated FT menu to remove FT Anim Picker")
                except ImportError:
                    # If ft_anim_picker is not available, just remove the menu
                    cmds.deleteUI('FTMenu')
                    print("Removed FT menu from Maya's menu bar")
            except Exception as e:
                # If anything goes wrong, just remove the menu
                cmds.deleteUI('FTMenu')
                print(f"Removed FT menu from Maya's menu bar (Error: {e})")
    
    def find_file(self, filename, search_dirs):
        """Find a file in the given directories"""
        for directory in search_dirs:
            file_path = os.path.join(directory, filename)
            if os.path.exists(file_path):
                return file_path
        return None
    
    def remove_module_file(self):
        """Remove or update the FT Tools module file"""
        module_file = self.find_file('ft_tools.mod', [self.version_modules_dir, self.shared_modules_dir])
        
        if not module_file:
            print("Module file not found")
            return
            
        if self.uninstall_all:
            # Remove the entire module file
            os.remove(module_file)
            print(f"Removed module file: {module_file}")
        else:
            # Update the module file to remove only FT Anim Picker
            try:
                with open(module_file, 'r') as f:
                    lines = f.readlines()
                
                new_lines = []
                skip_section = False
                
                for line in lines:
                    # Skip lines related to FT Anim Picker
                    if 'ft_anim_picker' in line:
                        skip_section = True
                        continue
                    
                    # End of a module section
                    if skip_section and line.strip() == '':
                        skip_section = False
                        continue
                        
                    # Keep all other lines
                    if not skip_section:
                        new_lines.append(line)
                
                # If we have content left, write the updated file
                if new_lines:
                    with open(module_file, 'w') as f:
                        f.writelines(new_lines)
                    print(f"Updated module file to remove FT Anim Picker: {module_file}")
                else:
                    # If no content left, remove the file
                    os.remove(module_file)
                    print(f"Removed empty module file: {module_file}")
            except Exception as e:
                print(f"Error updating module file: {e}")
    
    def clean_usersetup_file(self):
        """Clean FT Tools references from userSetup.py"""
        usersetup_file = self.find_file('userSetup.py', [self.version_scripts_dir, self.shared_scripts_dir])
        
        if not usersetup_file:
            print("userSetup.py not found")
            return
            
        try:
            with open(usersetup_file, 'r') as f:
                lines = f.readlines()
            
            # Filter out lines related to FT Tools
            new_lines = self._filter_usersetup_lines(lines)
            
            # Write the cleaned file
            with open(usersetup_file, 'w') as f:
                f.writelines(new_lines)
            
            print(f"Removed FT Tools setup code from: {usersetup_file}")
        except Exception as e:
            print(f"Error cleaning userSetup.py: {e}")
    
    def _filter_usersetup_lines(self, lines):
        """Filter out FT Tools related lines from userSetup.py content"""
        new_lines = []
        skip_section = False
        skip_next_lines = 0
        
        for i, line in enumerate(lines):
            # If we're skipping lines due to a previous match
            if skip_next_lines > 0:
                skip_next_lines -= 1
                continue
            
            # Start of FT Tools section
            if '# FT Anim Picker Menu Setup' in line or '# FT Tools Menu Setup' in line:
                skip_section = True
                continue
            
            # Skip lines in the FT Tools section
            if skip_section:
                if self.uninstall_all:
                    # Skip all FT tool imports
                    if 'import ft_anim_picker.ft_menu_setup' in line or 'import ft_anim_picker.ft_menu_setup' in line:
                        continue
                else:
                    # Skip only FT Anim Picker imports
                    if 'import ft_anim_picker.ft_menu_setup' in line:
                        continue
                    # Keep other tool imports
                    if 'import ft_anim_picker.ft_menu_setup' in line:
                        new_lines.append(line)
                        continue
                        
                if 'menu_setup.setup_ft_tools()' in line:
                    if not self.uninstall_all:
                        # Keep the setup line if we're only removing FT Anim Picker
                        new_lines.append(line)
                    skip_section = False  # End of section
                    continue
            
            # Check for import sys followed by sys.path.append with our tool path
            if 'import sys' in line and i < len(lines) - 1:
                next_line = lines[i + 1]
                if 'sys.path.append' in next_line and (
                    'ft_anim_picker' in next_line or 
                    self.ft_anim_picker_path.replace('\\', '/') in next_line or
                    self.ft_anim_picker_path.replace('\\', '\\') in next_line
                ):
                    # Skip both the import sys and the sys.path.append lines
                    skip_next_lines = 1
                    continue
                
                # If we're only removing FT Anim Picker, keep the import sys line
                # if there are other imports that might need it
                if not self.uninstall_all:
                    has_other_imports = False
                    for j in range(i+1, min(i+5, len(lines))):
                        if 'ft_anim_picker' in lines[j]:
                            has_other_imports = True
                            break
                    if has_other_imports:
                        new_lines.append(line)
                    continue
            
            # Keep all other lines
            new_lines.append(line)
            
        return new_lines
    
    def unload_packages(self):
        """Unload FT Tools packages from memory"""
        if self.uninstall_all:
            packages_to_unload = [
                ('ft_tool_box', 'ft_tool_box.__unload_pkg'),
                ('ft_anim_picker', 'ft_anim_picker.__unload_pkg')
            ]
        else:
            packages_to_unload = [
                ('ft_anim_picker', 'ft_anim_picker.__unload_pkg')
            ]
        
        for package_name, unloader_module in packages_to_unload:
            try:
                pkg_module = __import__(package_name)
                unloader = __import__(unloader_module.replace('.', '.'), fromlist=['unload'])
                unloader.unload(pkg_module)
                print(f"Unloaded {package_name} package from memory")
            except Exception as e:
                print(f"Note: Could not unload {package_name} package: {e}")
    
    def run(self):
        """Run the complete uninstallation process"""
        print("Starting FT Tools uninstallation...")
        
        # Execute all uninstallation steps
        self.remove_menu()
        self.remove_module_file()
        self.clean_usersetup_file()
        self.unload_packages()
        
        print("\nUninstallation complete!")
        print("Restart Maya to complete the uninstallation.")
        return True


def main(uninstall_option=None):
    """Show confirmation dialog before uninstallation
    
    Args:
        uninstall_option (str, optional): If provided, skips the dialog and uninstalls based on the option.
            Can be 'all' or 'anim_picker'. If None, shows a dialog to choose.
    """
    if uninstall_option is None:
        result = cmds.confirmDialog(
            title='Uninstall FT Tools',
            message='What would you like to uninstall?',
            button=['All FT Tools', 'Only FT Anim Picker', 'Cancel'],
            defaultButton='Cancel',
            cancelButton='Cancel',
            dismissString='Cancel'
        )
        
        if result == 'All FT Tools':
            uninstall_all = True
        elif result == 'Only FT Anim Picker':
            uninstall_all = False
        else:
            return  # User cancelled
    else:
        if uninstall_option.lower() == 'all':
            uninstall_all = True
        elif uninstall_option.lower() == 'anim_picker':
            uninstall_all = False
        else:
            print(f"Invalid uninstall option: {uninstall_option}")
            return
    
    # Confirm the action
    message = 'Are you sure you want to uninstall ' + ('all FT Tools' if uninstall_all else 'only FT Anim Picker') + '?'
    confirm = cmds.confirmDialog(
        title='Confirm Uninstallation',
        message=message,
        button=['Yes', 'No'],
        defaultButton='No',
        cancelButton='No',
        dismissString='No'
    )
    
    if confirm == 'Yes':
        uninstaller = FT_Tools_Uninstaller(uninstall_all=uninstall_all)
        success = uninstaller.run()
        
        if success:
            what_uninstalled = 'All FT Tools' if uninstall_all else 'FT Anim Picker'
            cmds.confirmDialog(
                title='Uninstallation Complete',
                message=f'{what_uninstalled} have been uninstalled successfully!\n\n'
                        'Restart Maya to complete the uninstallation.',
                button=['OK'],
                defaultButton='OK'
            )


# Run the uninstaller when this script is executed
if __name__ == "__main__":
    main()