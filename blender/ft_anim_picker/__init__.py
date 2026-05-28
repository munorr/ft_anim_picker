bl_info = {
    "name": "BGEN Picker",
    "author": "M2KY inc.",
    "version": (3, 0, 8),
    "blender": (4, 0, 0),
    "location": "Main Menu > BGEN > Picker",
    "description": "Animation picker for Blender",
    "category": "Animation",
}

import bpy
import sys
import os
import subprocess
import importlib
from pathlib import Path

# =============================================================================
# DEPENDENCY MANAGEMENT SYSTEM
# =============================================================================

# List of required packages: (import_name, pip_name, description)
REQUIRED_PACKAGES = [
    ("PySide6", "PySide6", "Qt6 bindings for Python UI"),
    ("shiboken6", "shiboken6", "PySide6 wrapper utilities"),
]

# Global state for deferred loading
_dependencies_installed = False
_main_module_loaded = False
_blender_main = None
_install_success_pending_restart = False  # True when install succeeded but restart needed
_last_install_successful = []  # List of successfully installed package names
_last_install_errors = []  # List of (package_name, error_msg) tuples

# Icon preview collections
_preview_collections = {}


def get_python_executable():
    """Get the path to Blender's Python executable."""
    return sys.executable


def check_package_installed(package_name):
    """Check if a package is installed and can be imported."""
    # Clear any cached failed imports first
    if package_name in sys.modules:
        # Module is loaded, but let's verify it's actually usable
        module = sys.modules[package_name]
        if module is None:
            # Cached failed import
            del sys.modules[package_name]
            return False
    
    try:
        importlib.import_module(package_name)
        return True
    except ImportError:
        return False
    except Exception:
        # Any other error means the package is broken
        return False


def deep_check_pyside6():
    """
    Perform a thorough check that PySide6 is properly installed and functional.
    This goes beyond just importing - it verifies critical components work.
    """
    try:
        # Clear any stale cached imports
        modules_to_clear = [k for k in sys.modules.keys() if k.startswith(('PySide6', 'shiboken6'))]
        for mod in modules_to_clear:
            if sys.modules.get(mod) is None:
                del sys.modules[mod]
        
        # Invalidate import caches
        importlib.invalidate_caches()
        
        # Test 1: Basic import
        import PySide6
        
        # Test 2: Import QtWidgets (this is what we actually use)
        from PySide6 import QtWidgets, QtCore, QtGui
        
        # Test 3: Verify shiboken6 works (needed for some widgets)
        from shiboken6 import wrapInstance
        
        # Test 4: Try to access a class (catches DLL/so issues)
        _ = QtWidgets.QWidget
        _ = QtCore.QTimer
        _ = QtGui.QColor
        
        # Test 5: Check version is accessible (sanity check)
        _ = PySide6.__version__
        
        return True
        
    except ImportError as e:
        print(f"[BGEN Picker] PySide6 import check failed: {e}")
        return False
    except AttributeError as e:
        print(f"[BGEN Picker] PySide6 attribute check failed: {e}")
        return False
    except Exception as e:
        print(f"[BGEN Picker] PySide6 check failed with unexpected error: {e}")
        return False


def check_all_dependencies():
    """Check if all required dependencies are installed and functional."""
    missing = []
    
    # Use deep check for PySide6 since it's critical and can have subtle issues
    if not deep_check_pyside6():
        # Add both packages as missing since they work together
        for import_name, pip_name, description in REQUIRED_PACKAGES:
            missing.append((import_name, pip_name, description))
        return missing
    
    # If deep check passes, all dependencies are good
    return missing


def install_package(package_name, pip_name=None):
    """Install a package using pip directly within Blender's Python."""
    if pip_name is None:
        pip_name = package_name
    
    # Method 1: Use pip.main() - most reliable for Blender's embedded Python
    try:
        import pip
        pip.main(['install', pip_name])
        return True
    except AttributeError:
        pass  # pip.main might not exist in newer pip versions
    
    # Method 2: Use pip._internal (for newer pip versions)
    try:
        from pip._internal.cli.main import main as pip_main
        result = pip_main(['install', pip_name])
        if result == 0:
            return True
    except ImportError:
        pass
    
    # Method 3: Use ensurepip and runpy as fallback
    try:
        import ensurepip
        ensurepip.bootstrap(upgrade=True, default_pip=True)
    except Exception:
        pass
    
    try:
        import runpy
        sys.argv = ['pip', 'install', pip_name]
        runpy.run_module('pip', run_name='__main__', alter_sys=True)
        return True
    except SystemExit as e:
        if e.code == 0:
            return True
        raise RuntimeError(f"pip install returned code {e.code}")
    except Exception as e:
        raise RuntimeError(f"All installation methods failed: {e}")


def install_all_dependencies():
    """Install all missing dependencies."""
    missing = check_all_dependencies()
    errors = []
    
    # First ensure pip is available
    try:
        import ensurepip
        ensurepip.bootstrap(upgrade=True, default_pip=True)
        print("[BGEN Picker] pip bootstrapped successfully")
    except Exception as e:
        print(f"[BGEN Picker] ensurepip note: {e}")
    
    for import_name, pip_name, description in missing:
        try:
            install_package(import_name, pip_name)
            print(f"[BGEN Picker] Successfully installed {pip_name}")
        except Exception as e:
            errors.append((pip_name, str(e)))
            print(f"[BGEN Picker] Failed to install {pip_name}: {e}")
    
    # Refresh the import cache
    importlib.invalidate_caches()
    
    return errors


def load_main_modules():
    """Load the main addon modules after dependencies are verified."""
    global _main_module_loaded, _blender_main
    
    if _main_module_loaded:
        return _blender_main
    
    # Add the src directory to the path
    src_dir = os.path.join(os.path.dirname(__file__), "src")
    if src_dir not in sys.path:
        sys.path.append(src_dir)
    
    # Now safe to import the main modules
    from .src import blender_main
    _blender_main = blender_main
    _main_module_loaded = True
    
    return blender_main


# =============================================================================
# OPERATORS
# =============================================================================

class BGEN_OT_install_dependencies(bpy.types.Operator):
    """Install required Python packages for BGEN Picker"""
    bl_idname = "ft_anim_picker.install_dependencies"
    bl_label = "Install Dependencies"
    bl_description = "Install required Python packages (PySide6, shiboken6)"
    bl_options = {'REGISTER', 'INTERNAL'}
    
    _timer = None
    _install_step = 0
    _packages_to_install = []
    _errors = []
    _successful_installs = []  # Track successfully installed packages
    _current_package = ""
    
    def modal(self, context, event):
        if event.type == 'TIMER':
            wm = context.window_manager
            
            # Step 0: Initialize
            if self._install_step == 0:
                wm.bgen_install_status = "Preparing pip..."
                wm.bgen_install_progress = 5
                self._install_step = 1
                self._redraw_areas(context)
                return {'RUNNING_MODAL'}
            
            # Step 1: Bootstrap pip
            elif self._install_step == 1:
                try:
                    import ensurepip
                    ensurepip.bootstrap(upgrade=True, default_pip=True)
                except Exception as e:
                    print(f"[BGEN Picker] ensurepip note: {e}")
                
                wm.bgen_install_progress = 10
                wm.bgen_install_status = "pip ready..."
                self._install_step = 2
                self._redraw_areas(context)
                return {'RUNNING_MODAL'}
            
            # Step 2+: Install packages one by one
            elif self._install_step >= 2:
                pkg_index = self._install_step - 2
                total = len(self._packages_to_install)
                
                # First update UI, then install on NEXT timer tick
                if pkg_index < total:
                    # Check if we need to do the install or just updated UI
                    if not hasattr(self, '_ui_updated') or not self._ui_updated:
                        # Update UI first
                        import_name, pip_name, description = self._packages_to_install[pkg_index]
                        self._current_package = pip_name
                        
                        progress = 15 + (pkg_index / total) * 80
                        wm.bgen_install_progress = int(progress)
                        wm.bgen_install_status = f"Installing {pip_name}... ({pkg_index + 1}/{total})"
                        self._redraw_areas(context)
                        self._ui_updated = True
                        return {'RUNNING_MODAL'}
                    else:
                        # Now do the actual install
                        import_name, pip_name, description = self._packages_to_install[pkg_index]
                        self._ui_updated = False
                        
                        try:
                            success = self._do_pip_install(pip_name)
                            if success:
                                self._successful_installs.append(pip_name)
                            else:
                                self._errors.append((pip_name, "pip install failed"))
                        except Exception as e:
                            self._errors.append((pip_name, str(e)))
                            print(f"[BGEN Picker] Error installing {pip_name}: {e}")
                        
                        self._install_step += 1
                        return {'RUNNING_MODAL'}
                
                else:
                    # All packages attempted - finalize
                    global _install_success_pending_restart, _last_install_successful, _last_install_errors
                    
                    wm.bgen_install_progress = 100
                    
                    if self._successful_installs:
                        wm.bgen_install_status = "Installation complete! Restart required."
                        _install_success_pending_restart = True
                        _last_install_successful = self._successful_installs.copy()
                        _last_install_errors = self._errors.copy()
                        
                        installed_names = ", ".join(self._successful_installs)
                        print(f"[BGEN Picker] Successfully installed: {installed_names}")
                        
                        # Clean up and refresh UI
                        self.finish(context)
                        self._redraw_areas(context)
                        
                        if self._errors:
                            error_names = ", ".join([pkg for pkg, _ in self._errors])
                            self.report({'WARNING'}, f"Installed: {installed_names}. Failed: {error_names}. Check preferences for details.")
                        else:
                            self.report({'INFO'}, "Dependencies installed! Check preferences then restart Blender.")
                        
                        return {'FINISHED'}
                    else:
                        wm.bgen_install_status = "Installation failed"
                        self.finish(context)
                        self._redraw_areas(context)
                        
                        error_names = ", ".join([pkg for pkg, _ in self._errors])
                        self.report({'ERROR'}, f"Failed to install: {error_names}. Try running Blender as Administrator.")
                        return {'CANCELLED'}
        
        return {'PASS_THROUGH'}
    
    def _do_pip_install(self, pip_name):
        """Install a single package using pip.main() - the method that works in Blender."""
        print(f"[BGEN Picker] Installing {pip_name}...")
        
        # Method 1: import pip; pip.main() - your known working method
        try:
            import pip
            result = pip.main(['install', pip_name])
            if result == 0:
                print(f"[BGEN Picker] Successfully installed {pip_name}")
                return True
        except AttributeError:
            print("[BGEN Picker] pip.main not available, trying alternative...")
        except Exception as e:
            print(f"[BGEN Picker] pip.main error: {e}")
        
        # Method 2: pip._internal for newer pip versions
        try:
            from pip._internal.cli.main import main as pip_main
            result = pip_main(['install', pip_name])
            if result == 0:
                print(f"[BGEN Picker] Successfully installed {pip_name} via pip._internal")
                return True
        except SystemExit as e:
            if e.code == 0:
                print(f"[BGEN Picker] Successfully installed {pip_name}")
                return True
            print(f"[BGEN Picker] pip._internal returned code {e.code}")
        except ImportError:
            print("[BGEN Picker] pip._internal not available")
        except Exception as e:
            print(f"[BGEN Picker] pip._internal error: {e}")
        
        return False
    
    def _redraw_areas(self, context):
        """Force UI redraw."""
        for area in context.screen.areas:
            if area.type == 'PREFERENCES':
                area.tag_redraw()
    
    def invoke(self, context, event):
        # Show confirmation dialog first
        return context.window_manager.invoke_confirm(self, event)
    
    def execute(self, context):
        # Check what needs to be installed
        self._packages_to_install = check_all_dependencies()
        
        if not self._packages_to_install:
            self.report({'INFO'}, "All dependencies are already installed!")
            return {'FINISHED'}
        
        # Reset state
        self._install_step = 0
        self._errors = []
        self._successful_installs = []
        self._current_package = ""
        self._ui_updated = False
        
        # Initialize progress properties
        wm = context.window_manager
        wm.bgen_install_progress = 0
        wm.bgen_install_status = "Starting installation..."
        wm.bgen_install_active = True
        
        # Start timer for modal updates (slower interval since pip.main blocks anyway)
        self._timer = context.window_manager.event_timer_add(0.2, window=context.window)
        context.window_manager.modal_handler_add(self)
        
        self.report({'INFO'}, "Installing dependencies... Blender may freeze briefly.")
        
        return {'RUNNING_MODAL'}
    
    def finish(self, context):
        """Clean up timer."""
        context.window_manager.bgen_install_active = False
        
        if self._timer:
            context.window_manager.event_timer_remove(self._timer)
            self._timer = None
    
    def cancel(self, context):
        self.finish(context)


class BGEN_OT_open_picker_with_check(bpy.types.Operator):
    """Open BGEN Picker (with dependency check)"""
    bl_idname = "ft_anim_picker.open_picker"
    bl_label = "BGEN Picker"
    bl_description = "Open the BGEN Picker window"
    bl_options = {'REGISTER'}
    
    def execute(self, context):
        # Always do a fresh deep check before opening
        missing = check_all_dependencies()
        
        if missing:
            missing_names = ", ".join([name for name, _, _ in missing])
            self.report({'ERROR'}, f"Missing dependencies: {missing_names}. Please install them in addon preferences.")
            # Open preferences to the addon
            bpy.ops.preferences.addon_show(module=__name__)
            return {'CANCELLED'}
        
        # Extra safety: wrap everything in try-except to prevent crashes
        try:
            # Verify imports one more time right before loading
            from PySide6 import QtWidgets
            _ = QtWidgets.QApplication
        except Exception as e:
            self.report({'ERROR'}, f"PySide6 verification failed: {e}. Please reinstall dependencies.")
            bpy.ops.preferences.addon_show(module=__name__)
            return {'CANCELLED'}
        
        # Load modules if not already loaded
        try:
            blender_main = load_main_modules()
            # Register the main module's operators if not already registered
            blender_main.register()
            # Call the actual picker operator
            return bpy.ops.anim.open_bgen_picker('INVOKE_DEFAULT')
        except ImportError as e:
            self.report({'ERROR'}, f"Import error: {str(e)}. Please reinstall dependencies.")
            bpy.ops.preferences.addon_show(module=__name__)
            return {'CANCELLED'}
        except Exception as e:
            self.report({'ERROR'}, f"Failed to open picker: {str(e)}")
            return {'CANCELLED'}


# =============================================================================
# FILE IMPORT OPERATOR + FILE HANDLER
# =============================================================================

class BGEN_OT_import_bpicker(bpy.types.Operator):
    """Import a .bpicker animation picker file"""
    bl_idname = "ft_anim_picker.import_bpicker"
    bl_label = "Import BPicker"
    bl_description = "Import a .bpicker animation picker file"
    bl_options = {'REGISTER', 'UNDO'}

    filepath: bpy.props.StringProperty(subtype='FILE_PATH')
    directory: bpy.props.StringProperty(subtype='DIR_PATH')
    filter_glob: bpy.props.StringProperty(default="*.bpicker", options={'HIDDEN'})

    def execute(self, context):
        if not self.filepath:
            self.report({'ERROR'}, "No file selected")
            return {'CANCELLED'}

        # Check dependencies
        missing = check_all_dependencies()
        if missing:
            missing_names = ", ".join([name for name, _, _ in missing])
            self.report({'ERROR'}, f"Missing dependencies: {missing_names}. Install in addon preferences.")
            bpy.ops.preferences.addon_show(module=__name__)
            return {'CANCELLED'}

        # Load main modules (deferred PySide6 loading)
        try:
            from PySide6 import QtWidgets
            _ = QtWidgets.QApplication
        except Exception as e:
            self.report({'ERROR'}, f"PySide6 verification failed: {e}. Please reinstall dependencies.")
            bpy.ops.preferences.addon_show(module=__name__)
            return {'CANCELLED'}

        try:
            blender_main = load_main_modules()
            blender_main.register()
        except Exception as e:
            self.report({'ERROR'}, f"Failed to load picker modules: {e}")
            return {'CANCELLED'}

        # Get or create a picker window, then import
        try:
            picker = blender_main.import_bpicker_file(self.filepath)
            if picker:
                self.report({'INFO'}, f"Imported {os.path.basename(self.filepath)}")
                return {'FINISHED'}
            else:
                self.report({'ERROR'}, "Import failed")
                return {'CANCELLED'}
        except Exception as e:
            self.report({'ERROR'}, f"Import failed: {e}")
            return {'CANCELLED'}

    def invoke(self, context, event):
        # If filepath already set (from FileHandler/drag-drop), execute directly
        if self.filepath:
            return self.execute(context)
        # Otherwise show file browser
        context.window_manager.fileselect_add(self)
        return {'RUNNING_MODAL'}


# FileHandler for drag-and-drop support (Blender 4.0+)
if hasattr(bpy.types, 'FileHandler'):
    class BGEN_FH_bpicker(bpy.types.FileHandler):
        bl_idname = "BGEN_FH_bpicker"
        bl_label = "BPicker"
        bl_import_operator = "ft_anim_picker.import_bpicker"
        bl_file_extensions = ".bpicker"

        @classmethod
        def poll_drop(cls, context):
            return True


def menu_func_import(self, context):
    pcoll = _preview_collections.get("main")
    if pcoll and "bpicker_file_icon" in pcoll:
        self.layout.operator(
            BGEN_OT_import_bpicker.bl_idname,
            text="BGEN Picker (.bpicker)",
            icon_value=pcoll["bpicker_file_icon"].icon_id
        )
    else:
        self.layout.operator(
            BGEN_OT_import_bpicker.bl_idname,
            text="BGEN Picker (.bpicker)"
        )


# =============================================================================
# ADDON PREFERENCES
# =============================================================================

class BGEN_AddonPreferences(bpy.types.AddonPreferences):
    bl_idname = __name__  # Must match the module name

    def draw(self, context):
        layout = self.layout
        wm = context.window_manager
        
        # Check if installation is in progress
        install_active = getattr(wm, 'bgen_install_active', False)
        
        if install_active:
            # Show progress UI during installation
            progress_box = layout.box()
            progress_box.label(text="Installing Dependencies...", icon="TIME")
            
            # Progress bar
            progress = getattr(wm, 'bgen_install_progress', 0)
            status = getattr(wm, 'bgen_install_status', "Working...")
            
            # Status message
            row = progress_box.row()
            row.label(text=status, icon="SORTTIME")
            
            # Visual progress bar
            col = progress_box.column(align=True)
            col.scale_y = 1.5
            col.prop(wm, "bgen_install_progress", text=f"Progress: {progress}%", slider=True)
            
            # Warning not to close Blender
            progress_box.separator()
            row = progress_box.row()
            row.alert = True
            row.label(text="Please wait... Blender may freeze during download.", icon="ERROR")
            
            return  # Don't show rest of UI during installation
        
        # Check if install succeeded but needs restart
        if _install_success_pending_restart:
            # Show restart required message
            restart_box = layout.box()

            col = restart_box.column(align=True)
            col.scale_y = 1.2
            col.label(text="Installation Successful!", icon="CHECKMARK")
            col.separator()
            
            # Show what was installed
            if _last_install_successful:
                results_col = restart_box.column(align=True)
                results_col.label(text="Successfully installed:", icon="PACKAGE")
                for pkg in _last_install_successful:
                    row = results_col.row()
                    row.label(text=f"  ✓ {pkg}", icon="CHECKMARK")
            
            # Show what failed (if any)
            if _last_install_errors:
                restart_box.separator()
                error_col = restart_box.column(align=True)
                error_col.label(text="Failed packages:", icon="ERROR")
                for pkg, err in _last_install_errors:
                    row = error_col.row()
                    row.label(text=f"  ✗ {pkg}", icon="X")
                error_col.separator()
                error_col.label(text="You can retry failed packages after restart.")
            
            restart_box.separator()
            
            # Main restart message
            msg_col = restart_box.column(align=True)
            msg_col.scale_y = 1.3
            row = msg_col.row()
            row.alert = True
            row.label(text="⚠ RESTART BLENDER NOW", icon="ERROR")
            msg_col.label(text="Save your work and restart to complete installation.")
            
            layout.separator()
            
            # Still show info section below
            info_box = layout.box()
            info_box.label(text="About", icon="INFO")
            row = info_box.row()
            row.operator(
                "wm.url_open",
                text="Original Addon by M2KY Dev",
                icon="URL"
            ).url = "https://m2ky.com/dev/tools/bgen-picker?tab=manual"
            
            return  # Don't show the normal dependency check UI
        
        # Check dependency status
        missing = check_all_dependencies()
        
        # Dependencies section
        dep_box = layout.box()
        dep_header = dep_box.row()
        dep_header.label(text="Dependencies", icon="PACKAGE")
        
        if missing:
            # Show warning and install button
            dep_box.label(text="Required packages are missing!", icon="ERROR")
            
            col = dep_box.column(align=True)
            for import_name, pip_name, description in missing:
                row = col.row()
                row.label(text=f"• {pip_name}: {description}", icon="X")
            
            dep_box.separator()
            
            row = dep_box.row()
            row.scale_y = 1.5
            row.operator("ft_anim_picker.install_dependencies", 
                        text="Install Dependencies", 
                        icon="IMPORT")
            
            # Help text
            help_box = dep_box.box()
            help_box.label(text="Installation Notes:", icon="QUESTION")
            col = help_box.column(align=True)
            col.scale_y = 0.8
            col.label(text="• If installation fails, try running Blender as Administrator")
            col.label(text="• On some systems, you may need to restart Blender after installation")
            col.label(text="• Make sure you have internet connection")
        else:
            # All dependencies installed
            dep_box.label(text="All dependencies are installed!", icon="CHECKMARK")
            
            col = dep_box.column(align=True)
            for import_name, pip_name, description in REQUIRED_PACKAGES:
                row = col.row()
                row.label(text=f"• {pip_name}: {description}", icon="CHECKMARK")
        
        layout.separator()
        
        # Info section
        info_box = layout.box()
        info_box.label(text="About", icon="INFO")
        row = info_box.row()
        row.operator(
            "wm.url_open",
            text="Original Addon by M2KY Dev",
            icon="URL"
        ).url = "https://m2ky.com/dev/tools/bgen-picker"
        
        row = info_box.row()
        row.operator(
            "wm.url_open",
            text="Documentation / Manual",
            icon="HELP"
        ).url = "https://m2ky.com/dev/tools/bgen-picker?tab=manual"
        #https://m2ky.com/dev/tools/bgen-picker?tab=manual


# =============================================================================
# MENU
# =============================================================================

class BGEN_MT_main_menu(bpy.types.Menu):
    bl_idname = "BGEN_MT_main_menu"
    bl_label = "BGEN"

    def draw(self, context):
        layout = self.layout
        
        # Check if dependencies are installed
        missing = check_all_dependencies()
        
        if missing:
            # Show install option instead
            layout.operator("ft_anim_picker.open_picker", text="Picker (Setup Required)", icon="ERROR")
            layout.separator()
            layout.operator("preferences.addon_show", text="Install Dependencies...").module = __name__
        else:
            # Normal menu when everything is ready
            if _main_module_loaded and _blender_main:
                layout.operator(_blender_main.ANIM_OT_open_bgen_picker.bl_idname, text="Picker")
            else:
                layout.operator("ft_anim_picker.open_picker", text="Picker")
        
        layout.separator()
        layout.operator("wm.url_open", text="Help").url = "https://m2ky.com/dev/tools/bgen-picker?tab=manual"


def add_bgen_menu(self, context):
    self.layout.menu(BGEN_MT_main_menu.bl_idname)


# =============================================================================
# REGISTRATION
# =============================================================================

# Classes that are always registered (no dependencies needed)
_base_classes = [
    BGEN_OT_install_dependencies,
    BGEN_OT_open_picker_with_check,
    BGEN_OT_import_bpicker,
    BGEN_AddonPreferences,
    BGEN_MT_main_menu,
]

# FileHandler class (only available in Blender 4.0+)
_file_handler_classes = []
if hasattr(bpy.types, 'FileHandler'):
    _file_handler_classes.append(BGEN_FH_bpicker)


def register_progress_properties():
    """Register window manager properties for installation progress."""
    bpy.types.WindowManager.bgen_install_progress = bpy.props.IntProperty(
        name="Installation Progress",
        description="Progress of dependency installation",
        default=0,
        min=0,
        max=100,
        subtype='PERCENTAGE'
    )
    bpy.types.WindowManager.bgen_install_status = bpy.props.StringProperty(
        name="Installation Status",
        description="Current installation status message",
        default=""
    )
    bpy.types.WindowManager.bgen_install_active = bpy.props.BoolProperty(
        name="Installation Active",
        description="Whether installation is currently in progress",
        default=False
    )


def unregister_progress_properties():
    """Unregister window manager properties."""
    try:
        del bpy.types.WindowManager.bgen_install_progress
    except:
        pass
    try:
        del bpy.types.WindowManager.bgen_install_status
    except:
        pass
    try:
        del bpy.types.WindowManager.bgen_install_active
    except:
        pass


def register():
    # Register progress properties first
    register_progress_properties()

    # Register custom icon for .bpicker files
    try:
        import bpy.utils.previews
        pcoll = bpy.utils.previews.new()
        icons_dir = os.path.join(os.path.dirname(__file__), "src", "bgen_picker_icons")
        icon_file = os.path.join(icons_dir, "bpicker_file_icon.png")
        if os.path.isfile(icon_file):
            pcoll.load("bpicker_file_icon", icon_file, 'IMAGE')
        _preview_collections["main"] = pcoll
    except Exception as e:
        print(f"[BGEN Picker] Icon registration note: {e}")

    # Always register base classes (these have no external dependencies)
    for cls in _base_classes:
        bpy.utils.register_class(cls)

    # Register file handler classes (Blender 4.0+)
    for cls in _file_handler_classes:
        bpy.utils.register_class(cls)

    # Add the BGEN menu to the main menu bar
    bpy.types.TOPBAR_MT_editor_menus.append(add_bgen_menu)

    # Add File > Import menu entry
    bpy.types.TOPBAR_MT_file_import.append(menu_func_import)

    # Check if dependencies are available (but do NOT load modules yet)
    # Loading PySide6 modules during registration can crash on certain Windows
    # configurations because Qt tries to create QPixmap before QGuiApplication exists.
    missing = check_all_dependencies()

    if not missing:
        global _dependencies_installed
        _dependencies_installed = True
        print("[BGEN Picker] Addon loaded successfully with all dependencies.")
    else:
        missing_names = ", ".join([name for name, _, _ in missing])
        print(f"[BGEN Picker] Dependencies missing: {missing_names}")
        print("[BGEN Picker] Please open addon preferences to install required packages.")


def unregister():
    # Remove the BGEN menu from the main menu bar
    bpy.types.TOPBAR_MT_editor_menus.remove(add_bgen_menu)

    # Remove File > Import menu entry
    bpy.types.TOPBAR_MT_file_import.remove(menu_func_import)

    # Unregister main modules if they were loaded
    if _main_module_loaded and _blender_main:
        try:
            _blender_main.unregister()
        except Exception as e:
            print(f"[BGEN Picker] Warning during unregister: {e}")

    # Unregister file handler classes
    for cls in reversed(_file_handler_classes):
        try:
            bpy.utils.unregister_class(cls)
        except:
            pass

    # Unregister base classes
    for cls in reversed(_base_classes):
        try:
            bpy.utils.unregister_class(cls)
        except:
            pass

    # Clean up icon previews
    for pcoll in _preview_collections.values():
        bpy.utils.previews.remove(pcoll)
    _preview_collections.clear()

    # Unregister progress properties
    unregister_progress_properties()


if __name__ == "__main__":
    register()
