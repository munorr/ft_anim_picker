import bpy
import sys
import os
import PySide6
from PySide6 import QtWidgets, QtCore
# Global variable to store the Qt application instance
_qt_app = None

# Function to get or create the Qt application
def get_qt_app():
    global _qt_app
    
    try:
        from PySide6 import QtWidgets, QtCore
    except ImportError:
        raise ImportError("PySide6 is required to use FT Animation Picker. Please install it to use this addon.")
    
    # Create Qt application if it doesn't exist
    if _qt_app is None:
        # Check if QApplication already exists (created by Blender)
        if QtWidgets.QApplication.instance():
            _qt_app = QtWidgets.QApplication.instance()
        else:
            # Create a new QApplication with Blender's args
            _qt_app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(sys.argv)
    
    return _qt_app

class PickerVisibilityManager:
    """FIXED: Centralized visibility manager for all picker instances"""
    _instance = None
    _registered_pickers = []
    _registered_child_widgets = {} 
    _visibility_timer = None
    _should_be_visible = True
    _last_check_time = 0
    _state_lock = False
    
    @classmethod
    def get_instance(cls):
        if cls._instance is None:
            cls._instance = PickerVisibilityManager()
        return cls._instance
    
    def register_picker(self, picker_widget):
        """Register a picker widget for centralized visibility management"""
        if picker_widget not in self._registered_pickers:
            self._registered_pickers.append(picker_widget)
            #print(f"Registered picker widget. Total active: {len(self._registered_pickers)}")
            
            # Start the timer if this is the first picker
            if len(self._registered_pickers) == 1:
                self._start_visibility_timer()
    
    def unregister_picker(self, picker_widget):
        """ENHANCED: Unregister a picker widget with proper cleanup"""
        if picker_widget in self._registered_pickers:
            self._registered_pickers.remove(picker_widget)
            #print(f"Unregistered picker widget. Total active: {len(self._registered_pickers)}")
            
            # CRITICAL FIX: Stop the timer if no pickers remain
            if len(self._registered_pickers) == 0:
                #print("No pickers remaining after unregister, stopping timer")
                self._stop_visibility_timer()
                # Reset state
                self._should_be_visible = True
                self._state_lock = False
        else:
            # Even if not in list, check if we should stop timer
            #print(f"Picker not found in registered list, checking if timer should stop")
            if len(self._registered_pickers) == 0:
                #print("No pickers remaining, stopping timer")
                self._stop_visibility_timer()
                self._should_be_visible = True
                self._state_lock = False
    
    def register_child_widget(self, parent_picker, child_widget):
        """Register a child widget (like ScriptManagerWidget) to a parent picker"""
        if parent_picker not in self._registered_child_widgets:
            self._registered_child_widgets[parent_picker] = []
        if child_widget not in self._registered_child_widgets[parent_picker]:
            self._registered_child_widgets[parent_picker].append(child_widget)
            #print(f"Registered child widget {type(child_widget).__name__} to picker")
    
    def unregister_child_widget(self, parent_picker, child_widget):
        """Unregister a child widget"""
        if parent_picker in self._registered_child_widgets:
            if child_widget in self._registered_child_widgets[parent_picker]:
                self._registered_child_widgets[parent_picker].remove(child_widget)
                if not self._registered_child_widgets[parent_picker]:
                    del self._registered_child_widgets[parent_picker]

    def _start_visibility_timer(self):
        """Start the centralized visibility timer"""
        if self._visibility_timer is None:
            from PySide6.QtCore import QTimer
            self._visibility_timer = QTimer()
            self._visibility_timer.timeout.connect(self._check_all_windows_visibility)
            self._visibility_timer.start(150)  # Slower check - 150ms to reduce conflicts
            #print("Started centralized visibility timer")
    
    def _stop_visibility_timer(self):
        """ENHANCED: Stop the centralized visibility timer with proper cleanup"""
        if self._visibility_timer:
            #print("Stopping visibility timer...")
            self._visibility_timer.stop()
            self._visibility_timer.timeout.disconnect()  # Disconnect signal
            self._visibility_timer.deleteLater()
            self._visibility_timer = None
            #print("Visibility timer stopped and cleaned up")
        
        # Reset state when stopping
        self._state_lock = False
        self._should_be_visible = True
        
        # Clear any remaining invalid references
        self._registered_pickers = [picker for picker in self._registered_pickers 
                                   if self._is_picker_still_valid(picker)]
        
        if self._registered_pickers:
            print(f"Warning: {len(self._registered_pickers)} pickers still registered after timer stop")
    
    def _is_picker_still_valid(self, picker):
        """FIXED: Better validation of picker widget"""
        try:
            if not picker:
                return False
            
            # Check if the widget has been deleted (most common case)
            if hasattr(picker, 'isValid'):
                if not picker.isValid():
                    return False
            
            # Try to access basic widget properties
            try:
                _ = picker.isVisible()
                _ = picker.windowTitle()  # This will fail if widget is deleted
                return True
            except RuntimeError:
                # Widget has been deleted
                return False
                
        except Exception as e:
            print(f"Error checking picker validity: {e}")
            return False
    
    def _check_all_windows_visibility(self):
        """FIXED: Check if any picker windows should be visible and apply to all"""
        try:
            # CRITICAL FIX: Prevent rapid state changes with lock
            if self._state_lock:
                return
            
            import time
            current_time = time.time()
            
            # CRITICAL FIX: Minimum interval between state changes (200ms)
            if current_time - self._last_check_time < 0.2:
                return
            
            # Remove any invalid references (windows that were closed improperly)
            valid_pickers = []
            for picker in self._registered_pickers[:]:  # Use copy to avoid modification during iteration
                try:
                    # Test if picker is still valid by checking multiple properties
                    _ = picker.isVisible()
                    _ = picker.isValid() if hasattr(picker, 'isValid') else True
                    # Additional check: see if the widget still has a parent or is properly initialized
                    if hasattr(picker, 'parent') and picker.parent() is None and not picker.isWindow():
                        raise RuntimeError("Widget appears to be deleted")
                    valid_pickers.append(picker)
                except (RuntimeError, AttributeError):
                    # Picker was deleted, remove it
                    print(f"Removed invalid picker reference")
                    continue
            
            self._registered_pickers = valid_pickers
            
            # CRITICAL FIX: Stop timer if no valid pickers remain
            if not self._registered_pickers:
                #print("No valid pickers remaining, stopping visibility timer")
                self._stop_visibility_timer()
                return
            
            # CRITICAL FIX: Check if ANY picker or its children are active
            any_picker_active = self._is_any_picker_or_child_active()
            
            # CRITICAL FIX: Only check Blender if NO picker is active
            blender_active = False
            if not any_picker_active:
                blender_active = self._is_blender_window_active()
            
            # Check if we're in task switcher mode
            task_switcher_active = self._is_task_switcher_active()
            
            # CRITICAL FIX: Windows should be visible if ANY picker is active OR Blender is active
            should_be_visible = any_picker_active or blender_active
            
            # Debug output - but less frequent
            if should_be_visible != self._should_be_visible or (current_time - getattr(self, '_last_debug_time', 0) > 2.0):
                #print(f"Visibility: picker_active={any_picker_active}, blender_active={blender_active}, should_be_visible={should_be_visible}")
                self._last_debug_time = current_time
            
            # Don't change visibility during task switching
            if task_switcher_active:
                return
            
            # CRITICAL FIX: Only apply changes if state actually changed AND sufficient time has passed
            if should_be_visible != self._should_be_visible:
                self._state_lock = True  # Lock to prevent rapid changes
                self._should_be_visible = should_be_visible
                self._last_check_time = current_time
                
                # Apply visibility to all picker windows
                self._apply_visibility_to_all(should_be_visible)
                
                # CRITICAL FIX: Add delay before unlocking to prevent rapid toggling
                def unlock_state():
                    self._state_lock = False
                
                from PySide6.QtCore import QTimer
                QTimer.singleShot(300, unlock_state)  # 300ms lock period
                
        except Exception as e:
            print(f"Error in centralized visibility check: {e}")
            import traceback
            traceback.print_exc()
            # Reset lock on error
            self._state_lock = False

    def _is_any_picker_or_child_active(self):
        """ENHANCED: Check if ANY picker window or any of their children are active"""
        from PySide6.QtWidgets import QApplication
        from PySide6.QtCore import Qt
        
        # CRITICAL FIX: First check if any registered picker is the active window
        for picker in self._registered_pickers:
            if picker.isActiveWindow():
                return True
        
        # Check if any child widgets are active (dialogs, etc.)
        active_window = QApplication.activeWindow()
        if active_window:
            # Check if it's a registered child widget (like ScriptManagerWidget)
            for picker, child_widgets in self._registered_child_widgets.items():
                if active_window in child_widgets:
                    return True
            
            # Check parent hierarchy for picker relationships
            for picker in self._registered_pickers:
                # Direct parent relationship
                if active_window == picker:
                    return True
                
                # Check parent hierarchy
                parent = active_window.parent()
                while parent:
                    if parent == picker:
                        return True
                    parent = parent.parent()
                
                # Additional check for window title patterns
                if (hasattr(active_window, 'windowTitle') and 
                    active_window.windowTitle() and
                    any(pattern in active_window.windowTitle() for pattern in ['Script Manager', 'Selection Manager'])):
                    return True

        return False
    
    def _is_blender_window_active(self):
        """Check if Blender window is active - FIXED to not conflict with picker detection"""
        if not self._registered_pickers:
            return False
        
        # Use a centralized method instead of relying on individual picker methods
        return self._check_blender_active_centralized()
    
    def _check_blender_active_centralized(self):
        """ENHANCED: Centralized Blender activity detection that doesn't conflict with picker detection"""
        import sys
        import os
        
        system = sys.platform
        
        if system == "win32":
            return self._is_blender_active_windows_centralized()
        elif system == "darwin":
            return self._is_blender_active_macos_centralized()
        elif system.startswith("linux"):
            return self._is_blender_active_linux_centralized()
        else:
            return True  # Default to assuming Blender is active on unknown platforms
    
    def _is_blender_active_windows_centralized(self):
        """ENHANCED Windows: Check if active window is Blender (not picker)"""
        try:
            import ctypes
            from ctypes import wintypes
            
            current_pid = os.getpid()
            
            # Get the foreground window
            hwnd = ctypes.windll.user32.GetForegroundWindow()
            if not hwnd:
                return False
            
            # Get process ID of the foreground window
            process_id = wintypes.DWORD()
            ctypes.windll.user32.GetWindowThreadProcessId(hwnd, ctypes.byref(process_id))
            
            # If the active window belongs to our process (Blender)
            if process_id.value == current_pid:
                # Get window class name
                class_buffer = ctypes.create_unicode_buffer(256)
                ctypes.windll.user32.GetClassNameW(hwnd, class_buffer, 256)
                class_name = class_buffer.value
                
                # CRITICAL: Only return True for actual Blender windows, not Qt windows
                if class_name == "GHOST_WindowClass":  # Blender window
                    return True
                else:
                    # CRITICAL FIX: Check if it's one of our Qt picker windows
                    qt_classes = ["Qt660QWindowIcon", "Qt660QWindowOwnDCIcon", 
                                 "Qt5QWindowIcon", "Qt5QWindowOwnDCIcon", "Qt562QWindowIcon"]
                    
                    if class_name in qt_classes:
                        # This is our picker window - let the picker detection handle it
                        return False
                    
                    # Unknown window type in our process - assume it's Blender related
                    return True
            
            return False
            
        except Exception as e:
            print(f"Error checking Windows Blender state: {e}")
            return False

    def _is_blender_active_macos_centralized(self):
        """ENHANCED macOS: Check if Blender application is frontmost (not picker)"""
        try:
            import subprocess
            
            # CRITICAL FIX: First check if any Qt windows are active (our pickers)
            from PySide6.QtWidgets import QApplication
            app = QApplication.instance()
            if app:
                active_window = app.activeWindow()
                if active_window:
                    # If a Qt window is active, let picker detection handle it
                    for picker in self._registered_pickers:
                        if active_window == picker:
                            return False
                        # Check parent hierarchy
                        parent = active_window.parent()
                        while parent:
                            if parent == picker:
                                return False
                            parent = parent.parent()
            
            # Check if Blender itself is frontmost
            applescript = '''
            tell application "System Events"
                set frontApp to first application process whose frontmost is true
                set frontAppName to name of frontApp
                if frontAppName contains "Blender" then
                    return true
                else
                    return false
                end if
            end tell
            '''
            
            result = subprocess.run(
                ['osascript', '-e', applescript],
                capture_output=True,
                text=True,
                timeout=2
            )
            
            if result.returncode == 0:
                return "true" in result.stdout.strip().lower()
            
            return False
            
        except Exception as e:
            print(f"Error checking macOS Blender state: {e}")
            return False

    def _is_blender_active_linux_centralized(self):
        """ENHANCED Linux: Check if active window is Blender (not picker)"""
        try:
            import subprocess
            current_pid = os.getpid()
            
            # Import utils for command checking
            def command_exists(command):
                from shutil import which
                return which(command) is not None
            
            # Try xdotool first
            if command_exists('xdotool'):
                # Get active window ID
                result = subprocess.run(
                    ['xdotool', 'getactivewindow'],
                    capture_output=True,
                    text=True,
                    timeout=2
                )
                
                if result.returncode == 0:
                    window_id = result.stdout.strip()
                    
                    # Get PID of active window
                    pid_result = subprocess.run(
                        ['xdotool', 'getwindowpid', window_id],
                        capture_output=True,
                        text=True,
                        timeout=2
                    )
                    
                    if pid_result.returncode == 0:
                        try:
                            window_pid = int(pid_result.stdout.strip())
                            # If active window belongs to our process
                            if window_pid == current_pid:
                                # Get window class to determine if it's Blender or Qt
                                class_result = subprocess.run(
                                    ['xdotool', 'getwindowclassname', window_id],
                                    capture_output=True,
                                    text=True,
                                    timeout=2
                                )
                                
                                if class_result.returncode == 0:
                                    window_class = class_result.stdout.strip().lower()
                                    # CRITICAL FIX: If it's a Qt window, let picker detection handle it
                                    qt_indicators = ['qt', 'python', 'python3', 'pyside', 'picker']
                                    if any(indicator in window_class for indicator in qt_indicators):
                                        return False
                                    # Otherwise it's likely Blender
                                    return True
                                
                                # Fallback: check window name
                                name_result = subprocess.run(
                                    ['xdotool', 'getwindowname', window_id],
                                    capture_output=True,
                                    text=True,
                                    timeout=2
                                )
                                if name_result.returncode == 0:
                                    window_name = name_result.stdout.strip().lower()
                                    # If contains picker/animation terms, let picker detection handle
                                    picker_indicators = ['picker', 'animation', 'qt']
                                    if any(indicator in window_name for indicator in picker_indicators):
                                        return False
                                    # If contains blender, it's blender
                                    if 'blender' in window_name:
                                        return True
                                
                                # CRITICAL FIX: Unknown window in our process - assume Blender
                                return True
                        except ValueError:
                            pass
            
            # Fallback to wmctrl with similar logic...
            # (keeping existing wmctrl code but with similar Qt detection fixes)
            
            return False
            
        except Exception as e:
            print(f"Error checking Linux Blender state: {e}")
            return False
    
    def _is_task_switcher_active(self):
        """Check if task switcher is active"""
        if not self._registered_pickers:
            return False
            
        # Use the first picker's task switcher detection method
        return self._registered_pickers[0]._is_task_switcher_active()
    
    def _apply_visibility_to_all(self, should_be_visible):
        """ENHANCED: Apply visibility state to all registered picker windows with safety checks"""
        #print(f"Applying visibility {should_be_visible} to {len(self._registered_pickers)} windows")
        
        successful_updates = 0
        for picker in self._registered_pickers[:]:  # Use copy to avoid modification during iteration
            try:
                # Double-check picker is still valid
                if not picker or not hasattr(picker, 'isVisible'):
                    continue
                    
                # Skip if already in correct state to avoid unnecessary operations
                current_visible = picker.isVisible()
                if (should_be_visible and current_visible) or (not should_be_visible and not current_visible):
                    successful_updates += 1
                    continue
                
                # Apply visibility change
                if should_be_visible:
                    picker._ensure_window_visible()
                else:
                    picker._ensure_window_hidden()
                    
                successful_updates += 1

                if picker in self._registered_child_widgets:
                    for child_widget in self._registered_child_widgets[picker][:]:
                        try:
                            if should_be_visible:
                                # Only show if it was previously visible
                                if hasattr(child_widget, '_was_visible') and child_widget._was_visible:
                                    child_widget.show()
                            else:
                                # Store visibility state before hiding
                                child_widget._was_visible = child_widget.isVisible()
                                child_widget.hide()
                        except Exception as e:
                            print(f"Error updating child widget visibility: {e}")
                            # Remove invalid child widget
                            self._registered_child_widgets[picker].remove(child_widget)
                
            except Exception as e:
                print(f"Error applying visibility to picker {id(picker)}: {e}")
                # Remove invalid picker from list
                try:
                    self._registered_pickers.remove(picker)
                except ValueError:
                    pass
        
        #print(f"Successfully updated visibility for {successful_updates}/{len(self._registered_pickers)} windows")
                       
class PickerWindowManager:
    _instance = None
    _picker_widgets = []
    
    @classmethod
    def get_instance(cls):
        if cls._instance is None:
            cls._instance = PickerWindowManager()
        return cls._instance
    
    def create_window(self):
        # Ensure Qt app exists
        app = get_qt_app()
        
        # Lazy import UI to avoid circular dependency
        from . import blender_ui as UI
        
        # Create new picker widget
        picker_widget = UI.BlenderAnimPickerWindow()
        picker_widget.setObjectName(f"floatingTool_{len(self._picker_widgets)}")
        
        # Store reference to widget
        self._picker_widgets.append(picker_widget)
        
        # Register with visibility manager
        visibility_manager = PickerVisibilityManager.get_instance()
        visibility_manager.register_picker(picker_widget)
        
        # Connect close event
        picker_widget.destroyed.connect(lambda: self.remove_widget(picker_widget))
        
        # Show widget
        picker_widget.show()
        
        # Process some events to ensure the window appears
        app.processEvents()
        
        return picker_widget
    
    def remove_widget(self, widget):
        if widget in self._picker_widgets:
            self._picker_widgets.remove(widget)
            
            # Unregister from visibility manager
            visibility_manager = PickerVisibilityManager.get_instance()
            visibility_manager.unregister_picker(widget)
    
    def close_all_windows(self):
        # Get visibility manager
        visibility_manager = PickerVisibilityManager.get_instance()
        
        for widget in self._picker_widgets[:]:  # Create copy of list to avoid modification during iteration
            # Unregister first
            visibility_manager.unregister_picker(widget)
            widget.close()
            widget.deleteLater()
        self._picker_widgets.clear()
        
        # Process events to ensure windows are closed
        app = get_qt_app()
        if app:
            app.processEvents()

def open():
    """Create a new instance of the animation picker window"""
    manager = PickerWindowManager.get_instance()
    return manager.create_window()

# Blender operator to open the picker
class ANIM_OT_open_ft_picker(bpy.types.Operator):
    bl_idname = "anim.open_ft_picker"
    bl_label = "FT Animation Picker"
    bl_description = "Open the FT Animation Picker"
    
    def execute(self, context):
        open()
        return {'FINISHED'}

# Registration
def register():
    bpy.utils.register_class(ANIM_OT_open_ft_picker)

def unregister():

    bpy.utils.unregister_class(ANIM_OT_open_ft_picker)

if __name__ == "__main__":
    register()
