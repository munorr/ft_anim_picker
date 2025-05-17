"""
FT Anim Picker Installer for Maya
===========================

This script handles the installation of the FT Anim Picker for Maya,
setting up module files and ensuring the menu is available on startup.

Author: [Your Name]
Version: 1.0.0
"""

import os
import sys
import shutil
import maya.cmds as cmds
import maya.mel as mel


class FT_AnimPicker_Installer:
    """Handles the installation of FT Anim Picker to the user's Maya environment."""
    
    def __init__(self):
        """Initialize the installer with required paths and configurations."""
        self.current_dir = os.path.dirname(os.path.abspath(__file__))
        self.maya_version = int(mel.eval('getApplicationVersionAsFloat()'))
        self.maya_app_dir = os.path.normpath(os.path.expanduser('~/Documents/maya'))
        
        # Module information
        self.module_name = "ft_tools"
        self.module_file = os.path.join(self.current_dir, f"{self.module_name}.mod")
        
        # Setup code for userSetup.py
        self.setup_code = (
            f"import sys\n"
            f"sys.path.append(r'{self.current_dir}')\n"
            f"import ft_anim_picker.ft_menu_setup as menu_setup\n"
            f"menu_setup.setup_ft_tools()\n"
        )
    
    def get_maya_modules_dir(self):
        """
        Determine the appropriate Maya modules directory.
        
        Returns:
            str: Path to the Maya modules directory
        """
        # Try version-specific directory first
        version_dir = os.path.join(self.maya_app_dir, str(self.maya_version), 'modules')
        if os.path.exists(version_dir):
            return version_dir
            
        # Fall back to shared modules directory
        shared_dir = os.path.join(self.maya_app_dir, 'modules')
        return shared_dir
    
    def get_scripts_dir(self):
        """
        Determine the appropriate Maya scripts directory.
        
        Returns:
            str: Path to the Maya scripts directory
        """
        # Try version-specific directory first
        version_dir = os.path.join(self.maya_app_dir, str(self.maya_version), 'scripts')
        if os.path.exists(version_dir):
            return version_dir
            
        # Fall back to shared scripts directory
        shared_dir = os.path.join(self.maya_app_dir, 'scripts')
        return shared_dir
    
    def ensure_directory_exists(self, directory):
        """
        Create directory if it doesn't exist.
        
        Args:
            directory (str): Directory path to create
            
        Returns:
            bool: True if directory exists or was created successfully
        """
        if not os.path.exists(directory):
            try:
                os.makedirs(directory)
                print(f"Created directory: {directory}")
                return True
            except OSError as e:
                print(f"Failed to create directory {directory}: {e}")
                return False
        return True
    
    def install_module_file(self):
        """
        Install the module file to the Maya modules directory.
        
        Returns:
            bool: True if installation was successful
        """
        if not os.path.exists(self.module_file):
            print(f"Module file not found: {self.module_file}")
            return False
            
        modules_dir = self.get_maya_modules_dir()
        if not self.ensure_directory_exists(modules_dir):
            return False
            
        dest_module_file = os.path.join(modules_dir, f"{self.module_name}.mod")
        
        try:
            # Read and update module file with absolute path
            with open(self.module_file, 'r') as src:
                content = src.read()
                
            with open(dest_module_file, 'w') as dest:
                for line in content.splitlines():
                    if line.startswith('+'):
                        parts = line.split()
                        parts[-1] = self.current_dir
                        dest.write(' '.join(parts) + '\n')
                    else:
                        dest.write(line + '\n')
                        
            print(f"Module file installed to: {dest_module_file}")
            return True
        except Exception as e:
            print(f"Failed to install module file: {e}")
            return False
    
    def update_user_setup(self):
        """
        Create or update userSetup.py to load the menu on Maya startup.
        
        Returns:
            bool: True if update was successful
        """
        scripts_dir = self.get_scripts_dir()
        if not self.ensure_directory_exists(scripts_dir):
            return False
            
        usersetup_file = os.path.join(scripts_dir, 'userSetup.py')
        
        try:
            if os.path.exists(usersetup_file):
                # Check if our setup is already in the file
                with open(usersetup_file, 'r') as f:
                    content = f.read()
                    
                if 'ft_anim_picker.ft_menu_setup' not in content:
                    with open(usersetup_file, 'a') as f:
                        f.write('\n# FT Anim Picker Menu Setup\n')
                        f.write(self.setup_code)
                    print(f"Updated existing userSetup.py at: {usersetup_file}")
                else:
                    print("FT Anim Picker menu setup already exists in userSetup.py")
            else:
                # Create new userSetup.py
                with open(usersetup_file, 'w') as f:
                    f.write('# Maya userSetup.py\n')
                    f.write('# FT Anim Picker Menu Setup\n')
                    f.write(self.setup_code)
                print(f"Created new userSetup.py at: {usersetup_file}")
            return True
        except Exception as e:
            print(f"Failed to update userSetup.py: {e}")
            return False
    
    def setup_menu_in_current_session(self):
        """
        Set up the menu in the current Maya session.
        
        Returns:
            bool: True if setup was successful
        """
        try:
            # First, try to unload any existing ft_anim_picker package to refresh it
            self._unload_existing_package()
            
            # Now set up the menu with the latest version
            sys.path.insert(0, self.current_dir)  # Ensure current directory is first in path
            import ft_anim_picker.ft_menu_setup as menu_setup
            
            # If the FT menu already exists, delete it to recreate with updated version
            if cmds.menu('FTMenu', exists=True):
                cmds.deleteUI('FTMenu')
                print("Removed existing FT menu to refresh it")
            
            menu_setup.setup_ft_tools()
            print("FT Anim Picker menu has been added to the current Maya session.")
            return True
        except Exception as e:
            print(f"Error setting up menu in current session: {e}")
            return False
    
    def _unload_existing_package(self):
        """
        Attempt to unload any existing ft_anim_picker package.
        
        Returns:
            bool: True if unload was successful or not necessary
        """
        try:
            # Check if package is already loaded
            if 'ft_anim_picker' in sys.modules:
                try:
                    import ft_anim_picker.__unload_pkg as unloader
                    import ft_anim_picker
                    unloader.unload(ft_anim_picker)
                    print("Successfully unloaded existing ft_anim_picker package")
                except Exception as e:
                    print(f"Could not unload existing package: {e}")
                    return False
            return True
        except Exception as e:
            print(f"Error checking for existing package: {e}")
            return False
    
    def install(self):
        """
        Run the complete installation process.
        
        Returns:
            bool: True if installation was successful
        """
        print("Starting FT Anim Picker installation...")
        
        # Execute installation steps
        module_installed = self.install_module_file()
        if not module_installed:
            print("Failed to install module file. Aborting installation.")
            return False
            
        usersetup_updated = self.update_user_setup()
        if not usersetup_updated:
            print("Failed to update userSetup.py. Menu may not load on startup.")
            
        menu_setup = self.setup_menu_in_current_session()
        if not menu_setup:
            print("Failed to set up menu in current session.")
        
        # Check overall success
        success = module_installed and (usersetup_updated or menu_setup)
        
        if success:
            print("\nInstallation complete!")
            print("Restart Maya to complete the installation.")
        else:
            print("\nInstallation completed with warnings.")
            print("Please check the logs above for details.")
            
        return success

def main():
    """Main entry point for the installer."""
    installer = FT_AnimPicker_Installer()
    return installer.install()

if __name__ == "__main__":
    main()

