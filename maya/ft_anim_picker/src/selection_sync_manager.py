"""
Selection Synchronization Manager for BGEN Picker (Maya Version)
Provides 2-way selection synchronization between Maya and the picker interface
"""

import maya.cmds as cmds
try:
    from PySide6 import QtCore
    from PySide6.QtCore import QObject, Signal, QTimer
except ImportError:
    from PySide2 import QtCore
    from PySide2.QtCore import QObject, Signal, QTimer

import weakref
import threading
from typing import Set, List, Optional, Tuple


class SelectionSyncManager(QObject):
    """
    Manages 2-way selection synchronization between BGEN Picker and Maya.
    
    Features:
    - Listens to Maya selection changes via scriptJob
    - Syncs picker button selections to Maya objects
    - Syncs Maya selections back to picker buttons
    - Prevents infinite selection loops
    - Handles multiple picker instances
    """
    
    # Signals
    maya_selection_changed = Signal(list)  # objects
    
    _instance = None
    _lock = threading.Lock()
    
    def __init__(self):
        super().__init__()
        
        # State management
        self._sync_enabled = True
        self._sync_lock = False  # Prevents infinite loops
        self._registered_canvases = weakref.WeakSet()
        
        # Maya state tracking
        self._last_selected_objects = set()
        self._selection_script_job = None
        
        # Timer for debounced updates
        self._update_timer = QTimer()
        self._update_timer.setSingleShot(True)
        self._update_timer.timeout.connect(self._process_maya_selection_change)
        
        # Setup Maya monitoring
        self._setup_maya_handlers()
        
    
    @classmethod
    def get_instance(cls):
        """Get singleton instance of SelectionSyncManager"""
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = cls()
        return cls._instance
    
    @classmethod
    def cleanup_instance(cls):
        """Cleanup singleton instance"""
        if cls._instance:
            cls._instance.cleanup()
            cls._instance = None
    
    def register_canvas(self, canvas):
        """Register a picker canvas for selection synchronization"""
        self._registered_canvases.add(canvas)
        
        # Connect canvas signals
        if hasattr(canvas, 'button_selection_changed'):
            canvas.button_selection_changed.connect(self._on_picker_selection_changed)
        
    
    def unregister_canvas(self, canvas):
        """Unregister a picker canvas"""
        try:
            self._registered_canvases.discard(canvas)
            
            # Disconnect signals if still connected
            if hasattr(canvas, 'button_selection_changed'):
                try:
                    canvas.button_selection_changed.disconnect(self._on_picker_selection_changed)
                except:
                    pass  # Signal might not be connected
                    
        except Exception as e:
            print(f"SelectionSyncManager (Maya): Error unregistering canvas: {e}")
    
    def set_sync_enabled(self, enabled: bool):
        """Enable or disable synchronization"""
        self._sync_enabled = enabled
        if enabled:
            self._setup_maya_handlers()
        else:
            self._cleanup_maya_handlers()
    
    def _setup_maya_handlers(self):
        """Setup Maya scriptJob to monitor selection changes"""
        try:
            # Remove any existing script job first
            self._cleanup_maya_handlers()
            
            # Create new script job for selection changes
            self._selection_script_job = cmds.scriptJob(
                event=['SelectionChanged', self._on_maya_selection_changed],
                protected=False,
                killWithScene=False
            )
            
        except Exception as e:
            print(f"SelectionSyncManager (Maya): Error setting up Maya handlers: {e}")
    
    def _cleanup_maya_handlers(self):
        """Remove Maya scriptJob"""
        try:
            if self._selection_script_job is not None:
                if cmds.scriptJob(exists=self._selection_script_job):
                    cmds.scriptJob(kill=self._selection_script_job)
                self._selection_script_job = None
            
        except Exception as e:
            print(f"SelectionSyncManager (Maya): Error cleaning up handlers: {e}")
    
    def _on_maya_selection_changed(self):
        """Handle Maya selection changes"""
        if not self._sync_enabled or self._sync_lock:
            return
        
        try:
            # Get current selection
            current_objects = set(cmds.ls(selection=True) or [])
            
            # Check if selection actually changed
            if current_objects != self._last_selected_objects:
                # Update tracking
                self._last_selected_objects = current_objects
                
                # Debounce updates
                if not self._update_timer.isActive():
                    self._update_timer.start(50)  # 50ms delay
        
        except Exception as e:
            print(f"SelectionSyncManager (Maya): Error in selection handler: {e}")
    
    def _process_maya_selection_change(self):
        """Process Maya selection changes and sync to picker"""
        if not self._sync_enabled or self._sync_lock:
            return
        
        try:
            # Set sync lock to prevent infinite loops
            self._sync_lock = True
            
            # Get current selections
            selected_objects = list(self._last_selected_objects)
            
            # Emit signal for any listeners
            self.maya_selection_changed.emit(selected_objects)
            
            # Update picker canvases
            self._sync_maya_to_picker(selected_objects)
            
        except Exception as e:
            print(f"SelectionSyncManager (Maya): Error processing Maya selection change: {e}")
        finally:
            # Always release the lock with a small delay to ensure Maya state is stable
            QTimer.singleShot(100, self._delayed_unlock)  # Longer delay for Maya stability
    
    def _sync_maya_to_picker(self, selected_objects: List[str]):
        """Sync Maya selection to picker buttons"""
        try:
            for canvas in list(self._registered_canvases):
                if canvas is None:
                    continue

                # Skip canvases in edit mode: scene selection shouldn't
                # mirror to canvas button highlighting while the user is
                # editing button layout.
                if getattr(canvas, 'edit_mode', False):
                    continue

                # Get current namespace for this canvas
                current_namespace = self._get_canvas_namespace(canvas)
                
                # Find buttons that should be selected
                buttons_to_select = set()
                
                for button in canvas.buttons:
                    if not hasattr(button, 'assigned_objects') or not button.assigned_objects:
                        continue
                    
                    # ALL-match: button is selected only when every assigned object
                    # is present in the Maya selection (prevents group buttons from
                    # highlighting when only some of their objects are selected)
                    all_objects_matched = True
                    has_valid_objects = False

                    for obj_data in button.assigned_objects:
                        # Maya stores object names in 'long_name' key, not 'name'
                        obj_name = obj_data.get('long_name', '')
                        if not obj_name:
                            continue

                        has_valid_objects = True

                        # Extract short name from long name for namespace handling
                        short_name = obj_name.split('|')[-1].split(':')[-1]

                        # Build possible object names to match
                        possible_names = set()
                        possible_names.add(obj_name)
                        possible_names.add(short_name)

                        if current_namespace and current_namespace != 'None':
                            possible_names.add(f"{current_namespace}:{short_name}")

                        # Check if this object is in Maya's selection
                        obj_matched = False
                        for selected_obj in selected_objects:
                            selected_short = selected_obj.split('|')[-1].split(':')[-1]

                            if (selected_obj in possible_names or
                                selected_short == short_name or
                                any(selected_obj.endswith(name) for name in possible_names)):
                                obj_matched = True
                                break

                        if not obj_matched:
                            all_objects_matched = False
                            break

                    if has_valid_objects and all_objects_matched:
                        buttons_to_select.add(button)
                
                # Update button selection states
                self._update_canvas_selection(canvas, buttons_to_select)
        
        except Exception as e:
            print(f"SelectionSyncManager (Maya): Error syncing Maya to picker: {e}")
    
    def _get_canvas_namespace(self, canvas) -> Optional[str]:
        """Get the current namespace for a canvas"""
        try:
            # Try to get namespace from parent window
            main_window = canvas.window()
            if hasattr(main_window, '_get_current_namespace'):
                return main_window._get_current_namespace()
            elif hasattr(main_window, 'namespace_dropdown'):
                current_text = main_window.namespace_dropdown.currentText()
                return current_text if current_text != 'None' else None
        except:
            pass
        return None
    
    def _update_canvas_selection(self, canvas, buttons_to_select: Set):
        """Update canvas button selection states"""
        try:
            selection_changed = False
            
            for button in canvas.buttons:
                old_selected = button.is_selected
                new_selected = button in buttons_to_select
                
                if old_selected != new_selected:
                    button.is_selected = new_selected
                    button.update()
                    selection_changed = True
            
            if selection_changed:
                # Emit canvas selection change signal
                canvas._emit_selection_changed()
        
        except Exception as e:
            print(f"SelectionSyncManager (Maya): Error updating canvas selection: {e}")
    
    def _delayed_unlock(self):
        """Release sync lock and re-sync to catch any swallowed SelectionChanged events"""
        self._sync_lock = False
        self._post_unlock_resync()

    def _post_unlock_resync(self):
        """Re-check Maya selection after lock release to catch swallowed events.

        When the picker changes Maya selection, the SelectionChanged scriptJob fires
        during the sync lock and gets discarded. After unlock, this method detects the
        change and triggers a sync so individual buttons get highlighted.
        """
        if not self._sync_enabled or self._sync_lock:
            return
        if getattr(self, '_in_post_unlock_resync', False):
            return
        self._in_post_unlock_resync = True
        try:
            current_objects = set(cmds.ls(selection=True) or [])
            if current_objects != self._last_selected_objects:
                self._last_selected_objects = current_objects
                if not self._update_timer.isActive():
                    self._update_timer.start(50)
        except Exception as e:
            print(f"SelectionSyncManager (Maya): Error in post-unlock resync: {e}")
        finally:
            QTimer.singleShot(200, lambda: setattr(self, '_in_post_unlock_resync', False))
    
    def _on_picker_selection_changed(self):
        """Handle picker selection changes"""
        if not self._sync_enabled or self._sync_lock:
            return
        
        # The existing apply_final_selection in canvas already handles picker->Maya sync
        # We just need to make sure it doesn't conflict with our Maya->picker sync
        pass
    
    def cleanup(self):
        """Cleanup the sync manager"""
        try:
            self._sync_enabled = False
            self._cleanup_maya_handlers()
            
            # Clear registered canvases
            self._registered_canvases.clear()
            
        except Exception as e:
            print(f"SelectionSyncManager (Maya): Error during cleanup: {e}")


# Global functions for integration
def enable_selection_sync():
    """Enable 2-way selection synchronization"""
    manager = SelectionSyncManager.get_instance()
    manager.set_sync_enabled(True)


def disable_selection_sync():
    """Disable 2-way selection synchronization"""
    manager = SelectionSyncManager.get_instance()
    manager.set_sync_enabled(False)


def register_canvas_for_sync(canvas):
    """Register a canvas for selection synchronization"""
    manager = SelectionSyncManager.get_instance()
    manager.register_canvas(canvas)


def unregister_canvas_from_sync(canvas):
    """Unregister a canvas from selection synchronization"""
    manager = SelectionSyncManager.get_instance()
    manager.unregister_canvas(canvas)


def cleanup_selection_sync():
    """Cleanup selection synchronization"""
    SelectionSyncManager.cleanup_instance()
