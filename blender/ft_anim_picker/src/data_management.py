import bpy
import json
import time
import threading
from collections import OrderedDict
from threading import Timer

from . import blender_ui as UI

class PickerDataManager:
    PROP_NAME = 'PickerToolData'
    DEFAULT_DATA = OrderedDict({
        'tabs': OrderedDict({
            'Tab 1': {
                'buttons': [],
                'image_path': None,
                'image_opacity': 1.0,
                'image_scale': 1.0,
                'background_value': 20,
                'namespace': 'None',
                'show_dots': False,
                'show_axes': True,    
                'show_grid': True,   
                'grid_size': 50       
            }
        }),
        'thumbnail_directory': ''
    })
    _undo_stack = []
    _redo_stack = []
    _max_undo_steps = 128
    _recording_enabled = True
    _in_batch_operation = False
    _last_undo_state = None
    _saving_in_progress = False  # NEW: Prevent recursion

    _batch_timer = None
    _batch_delay = 0.0  # 200ms delay for batching
    _pending_updates = False
    _last_save_time = 0
    _min_save_interval = 0.0  # Minimum 100ms between saves
    _cached_data = None
    _save_lock = threading.Lock()  # Thread safety for Blender

    #----------------------------------------------------------------------------------------------------------
    # UNDO REDO SYSTEM
    #----------------------------------------------------------------------------------------------------------
    @classmethod
    def save_undo_state(cls, operation_name="", selected_button_ids=None):
        """Save current state to undo stack with batching for rapid changes"""
        if selected_button_ids is None:
            selected_button_ids = cls._get_selected_button_ids()
        if not cls._recording_enabled or cls._in_batch_operation or cls._saving_in_progress:
            return
            
        # Only record undo states when any canvas is in edit mode
        if not cls._is_any_canvas_in_edit_mode():
            return
            
        current_time = time.time()
        
        # CRITICAL FIX: Prevent recursion by temporarily disabling undo recording
        cls._saving_in_progress = True
        try:
            # Import copy at the beginning where it's needed for both branches
            import copy
            
            # CRITICAL FIX: Use internal method to avoid recursion
            current_state = cls._get_data_internal()
            
            # Skip if state hasn't changed (avoid duplicate saves)
            '''if cls._last_undo_state and cls._states_equal(current_state, cls._last_undo_state):
                return
                '''
            # Batching logic: If last save was very recent, replace it instead of adding new entry
            batch_threshold = 0.25  # 250ms - batch rapid changes within this window
            
            if (cls._undo_stack and 
                len(cls._undo_stack) > 0 and 
                (current_time - cls._undo_stack[-1]['timestamp']) < batch_threshold):
                
                # Check if the last entry is marked as a batch entry
                last_entry = cls._undo_stack[-1]
                
                # If it's NOT already a batch entry, it means this is the start of a batch
                # We need to preserve this entry and create a new one for the batch
                if not last_entry.get('is_batch_entry', False):
                    # Create a new batch entry instead of replacing the existing one
                    batch_entry = {
                        'state': copy.deepcopy(current_state),
                        'operation': operation_name or "Change",
                        'timestamp': current_time,
                        'selected_button_ids': selected_button_ids,
                        'is_batch_entry': True,  # Mark this as a batch entry
                        'batch_start_time': last_entry['timestamp']  # Reference to when batch started
                    }
                    cls._undo_stack.append(batch_entry)
                    cls._last_undo_state = copy.deepcopy(current_state)
                    #print(f"Started batch undo state: {operation_name} (Stack size: {len(cls._undo_stack)})")
                else:
                    # This is a continuation of a batch - replace the batch entry
                    cls._undo_stack[-1] = {
                        'state': copy.deepcopy(current_state),
                        'operation': operation_name or "Change",
                        'timestamp': current_time,
                        'selected_button_ids': selected_button_ids,
                        'is_batch_entry': True,
                        'batch_start_time': last_entry.get('batch_start_time', last_entry['timestamp'])
                    }
                    cls._last_undo_state = copy.deepcopy(current_state)
                    #print(f"Updated batch undo state: {operation_name} (Stack size: {len(cls._undo_stack)})")
            else:
                # Check if we're ending a batch operation
                if (cls._undo_stack and 
                    len(cls._undo_stack) > 0 and 
                    cls._undo_stack[-1].get('is_batch_entry', False)):
                    
                    # This is the end of a batch - finalize the batch entry
                    # Always update the batch entry with the final state, even if it's the same
                    # This ensures the batch is properly finalized
                    cls._undo_stack[-1]['state'] = copy.deepcopy(current_state)
                    cls._undo_stack[-1]['timestamp'] = current_time
                    cls._undo_stack[-1]['operation'] = operation_name or "Change"
                    cls._undo_stack[-1]['selected_button_ids'] = selected_button_ids
                    cls._undo_stack[-1]['is_batch_entry'] = False  # Mark as finalized
                    cls._last_undo_state = copy.deepcopy(current_state)
                    #print(f"Finalized batch undo state: {operation_name} (Stack size: {len(cls._undo_stack)})")
                    
                    # Clear redo stack when new action is performed
                    cls._redo_stack.clear()
                    return
                    
                # Create new undo entry for changes outside batch window
                state_copy = copy.deepcopy(current_state)
                
                undo_entry = {
                    'state': state_copy,
                    'operation': operation_name or "Change",
                    'timestamp': current_time,
                    'selected_button_ids': selected_button_ids,
                    'is_batch_entry': False  # Regular entry
                }
                
                cls._undo_stack.append(undo_entry)
                cls._last_undo_state = state_copy
                
                # Limit undo stack size
                if len(cls._undo_stack) > cls._max_undo_steps:
                    cls._undo_stack.pop(0)
                
                print(f"Saved undo state: {operation_name} (Stack size: {len(cls._undo_stack)})")

            # Clear redo stack when new action is performed
            cls._redo_stack.clear()
            
        finally:
            cls._saving_in_progress = False
    
    @classmethod
    def _states_equal(cls, state1, state2):
        """Compare two states to see if they're identical"""
        try:
            import json
            return json.dumps(state1, sort_keys=True) == json.dumps(state2, sort_keys=True)
        except:
            return False
    
    @classmethod
    def can_undo(cls):
        """Check if undo is available"""
        return len(cls._undo_stack) > 0
    
    @classmethod
    def can_redo(cls):
        """Check if redo is available"""
        return len(cls._redo_stack) > 0
    
    @classmethod
    def undo(cls):
        """Restore previous state"""
        selected_button_ids = cls._get_selected_button_ids()
        if not cls.can_undo():
            return None, []
            
        # Save current state to redo stack
        import copy
        current_state = copy.deepcopy(cls.get_data())
        cls._redo_stack.append({
            'state': current_state,
            'timestamp': time.time(),
            'selected_button_ids': selected_button_ids   
        })
        
        # Restore previous state
        undo_entry = cls._undo_stack.pop()
        previous_state = undo_entry['state']
        restored_selected_ids = undo_entry.get('selected_button_ids', [])
        
        # Temporarily disable undo recording
        old_recording = cls._recording_enabled
        cls._recording_enabled = False
        try:
            # Force immediate save and update cache
            cls._perform_save(previous_state)
            cls._cached_data = copy.deepcopy(previous_state)
            cls._last_undo_state = copy.deepcopy(previous_state)
        finally:
            cls._recording_enabled = old_recording
            
        print(f"Undid: {undo_entry['operation']}")
        return undo_entry['operation'], restored_selected_ids
    
    @classmethod
    def redo(cls):
        """Restore next state"""
        selected_button_ids = cls._get_selected_button_ids()
        if not cls.can_redo():
            return None, []
            
        # Save current state to undo stack
        import copy
        current_state = copy.deepcopy(cls.get_data())
        cls._undo_stack.append({
            'state': current_state,
            'operation': 'before_redo',
            'timestamp': time.time(),
            'selected_button_ids': selected_button_ids
        })
        
        # Restore next state
        redo_entry = cls._redo_stack.pop()
        next_state = redo_entry['state']
        restored_selected_ids = redo_entry.get('selected_button_ids', [])
        
        # Temporarily disable undo recording
        old_recording = cls._recording_enabled
        cls._recording_enabled = False
        try:
            # Force immediate save and update cache
            cls._perform_save(next_state)
            cls._cached_data = copy.deepcopy(next_state)
            cls._last_undo_state = copy.deepcopy(next_state)
        finally:
            cls._recording_enabled = old_recording
            
        print("Redid operation")
        return "redo", restored_selected_ids
    
    @classmethod
    def clear_undo_history(cls):
        """Clear undo/redo history"""
        cls._undo_stack.clear()
        cls._redo_stack.clear()
        cls._last_undo_state = None
    
    @classmethod
    def _is_any_canvas_in_edit_mode(cls):
        """Check if any canvas in any picker window is in edit mode"""
        try:
            # Get the current window instance from the window manager
            from . import blender_main
            window_manager = blender_main.PickerWindowManager.get_instance()
            
            # Check if there are any picker windows available
            if not window_manager._picker_widgets:
                return False
            
            # Check all picker windows
            for picker_window in window_manager._picker_widgets:
                try:
                    # Check if window is still valid
                    if hasattr(picker_window, 'isValid') and not picker_window.isValid():
                        continue
                    
                    # Check if window is fully initialized
                    if not cls._is_window_fully_initialized(picker_window):
                        continue
                    
                    # Check edit mode on the window itself
                    if hasattr(picker_window, 'edit_mode') and picker_window.edit_mode:
                        return True
                        
                    # Also check if any canvas in the tab system is in edit mode
                    for tab_name, tab_data in picker_window.tab_system.tabs.items():
                        if 'canvas' in tab_data and hasattr(tab_data['canvas'], 'edit_mode'):
                            if tab_data['canvas'].edit_mode:
                                return True
                except (RuntimeError, AttributeError):
                    # Window might be deleted, skip it
                    continue
            
            return False
        except Exception as e:
            print(f"Error checking canvas edit mode: {e}")
            return False
    
    @classmethod
    def _is_window_fully_initialized(cls, picker_window):
        """Check if a picker window is fully initialized and ready to use"""
        try:
            # Check if window has all required attributes
            if not hasattr(picker_window, 'tab_system'):
                return False
            
            if not picker_window.tab_system:
                return False
            
            if not hasattr(picker_window.tab_system, 'current_tab'):
                return False
            
            if not picker_window.tab_system.current_tab:
                return False
            
            if not hasattr(picker_window.tab_system, 'tabs'):
                return False
            
            if picker_window.tab_system.current_tab not in picker_window.tab_system.tabs:
                return False
            
            tab_data = picker_window.tab_system.tabs[picker_window.tab_system.current_tab]
            if 'canvas' not in tab_data or not tab_data['canvas']:
                return False
            
            return True
        except Exception:
            return False
    
    @classmethod
    def _get_selected_button_ids(cls):
        """Get the IDs of currently selected buttons"""
        try:
            # Get the current window instance from the window manager
            from . import blender_main
            window_manager = blender_main.PickerWindowManager.get_instance()
            
            # Check if there are any windows at all
            if not window_manager._picker_widgets:
                return []
            
            # Get the active window using the window manager's method
            active_picker_window = window_manager.get_active_window()
            
            if not active_picker_window:
                return []
            
            # Check if the window is fully initialized
            if not cls._is_window_fully_initialized(active_picker_window):
                return []
            
            # If we found a valid window, try to get selected buttons
            if hasattr(active_picker_window, 'get_selected_buttons'):
                try:
                    selected_buttons = active_picker_window.get_selected_buttons()
                    if selected_buttons:
                        button_ids = [button.unique_id for button in selected_buttons if hasattr(button, 'unique_id')]
                        return button_ids
                    else:
                        return []
                except (RuntimeError, AttributeError) as e:
                    print(f"Error getting selected buttons from window: {e}")
                    return []
            else:
                return []
            
        except Exception as e:
            print(f"Error getting selected button IDs: {e}")
            return []
    
    #----------------------------------------------------------------------------------------------------------
    #DATA MANAGEMENT
    #----------------------------------------------------------------------------------------------------------
    @classmethod
    def initialize_data(cls):
        # Use scene as the storage object (equivalent to defaultObjectSet in Maya)
        scene = bpy.context.scene
        
        # Check if our property exists, if not create it
        if cls.PROP_NAME not in scene:
            # FIXED: Use internal save to prevent recursion during initialization
            cls._perform_save(cls.DEFAULT_DATA)

    @classmethod
    def reload_data_from_blender(cls):
        """Force reload data from Blender, clearing any cached data"""
        # Clear cached data
        cls._cached_data = None
        cls._pending_updates = False
        
        # Force initialize data if needed
        cls.initialize_data()
        
        # Get fresh data from Blender
        data_string = bpy.context.scene.get(cls.PROP_NAME)
        if data_string:
            try:
                data = json.loads(data_string, object_pairs_hook=OrderedDict)
                # Update cache with fresh data
                cls._cached_data = data
                return data
            except json.JSONDecodeError:
                print("Invalid data in PickerToolData. Resetting to default.")
                cls._perform_save(cls.DEFAULT_DATA)
                return cls.DEFAULT_DATA
        
        cls._cached_data = cls.DEFAULT_DATA
        return cls.DEFAULT_DATA

    @classmethod
    def _get_data_internal(cls):
        """Internal get_data method that doesn't trigger undo recording"""
        cls.initialize_data()
        scene = bpy.context.scene
        data_string = scene.get(cls.PROP_NAME, '')
        
        if data_string:
            try:
                data = json.loads(data_string, object_pairs_hook=OrderedDict)
                # Ensure 'buttons' key exists for each tab
                for tab in data['tabs']:
                    if 'buttons' not in data['tabs'][tab]:
                        data['tabs'][tab]['buttons'] = []
                    if 'namespace' not in data['tabs'][tab]:
                        data['tabs'][tab]['namespace'] = 'None'
                    
                    # Convert assigned objects to new format for each button
                    for button in data['tabs'][tab]['buttons']:
                        if 'assigned_objects' in button:
                            if not button['assigned_objects']:  # If empty list
                                button['assigned_objects'] = []
                            else:
                                # Check format of first object to determine if conversion needed
                                first_obj = button['assigned_objects'][0] if button['assigned_objects'] else None
                                if not isinstance(first_obj, dict):
                                    # Convert old format to new format
                                    converted_objects = []
                                    for obj in button['assigned_objects']:
                                        try:
                                            if obj in bpy.data.objects:
                                                obj_data = bpy.data.objects[obj]
                                                converted_objects.append({
                                                    'uuid': obj,
                                                    'name': obj_data.name_full
                                                })
                                            else:
                                                converted_objects.append({
                                                    'uuid': obj,
                                                    'name': ''
                                                })
                                        except:
                                            continue
                                    button['assigned_objects'] = converted_objects
                
                return data
                
            except json.JSONDecodeError:
                print("Invalid data in PickerToolData. Resetting to default.")
                cls._perform_save(cls.DEFAULT_DATA)
                return cls.DEFAULT_DATA
        
        return cls.DEFAULT_DATA
        
    @classmethod
    def get_data(cls):
        """Get data with caching for better performance"""
        # Return cached data if available and recent
        if cls._cached_data is not None and not cls._pending_updates:
            return cls._cached_data
            
        # Use internal method to get data
        data = cls._get_data_internal()
        
        # Cache the data
        cls._cached_data = data
        
        # Save converted data back to storage if needed
        if cls._pending_updates:
            cls._perform_save(data)
            
        return data
    
    @classmethod
    def save_data(cls, data, force_immediate=False):
        """Enhanced save_data with automatic undo recording - FIXED to prevent recursion"""
        # Existing save_data logic...
        with cls._save_lock:
            cls._cached_data = data
            
            current_time = time.time()
            
            if force_immediate:
                cls._perform_save(data)
                return
                
            if current_time - cls._last_save_time < cls._min_save_interval:
                cls._schedule_batched_save(data)
                return
                
            cls._perform_save(data)

    @classmethod
    def _perform_save(cls, data):
        """Actually perform the save operation"""
        try:
            scene = bpy.context.scene
            scene[cls.PROP_NAME] = json.dumps(data)
            cls._last_save_time = time.time()
            cls._pending_updates = False
            
            # Cancel any pending batch timer since we just saved
            if cls._batch_timer:
                cls._batch_timer.cancel()
                cls._batch_timer = None
                
        except Exception as e:
            print(f"Failed to save picker data: {e}")

    @classmethod
    def _schedule_batched_save(cls, data):
        """Schedule a batched save operation"""
        cls._pending_updates = True
        
        # Cancel existing timer if any
        if cls._batch_timer:
            cls._batch_timer.cancel()
            
        # Schedule new save
        cls._batch_timer = Timer(cls._batch_delay, cls._perform_save, args=[data])
        cls._batch_timer.start()

    @classmethod
    def batch_update_buttons(cls, tab_name, buttons_data):
        """Batch update multiple buttons at once for better performance"""
        data = cls.get_data()
        
        if tab_name in data['tabs']:
            tab_data = data['tabs'][tab_name]
            
            # Create a map of existing buttons by ID for faster lookup
            button_map = {btn['id']: i for i, btn in enumerate(tab_data.get('buttons', []))}
            
            # Update or add buttons
            for button_data in buttons_data:
                button_id = button_data['id']
                if button_id in button_map:
                    # Update existing
                    tab_data['buttons'][button_map[button_id]] = button_data
                else:
                    # Add new
                    tab_data['buttons'].append(button_data)
            
            # Use batched save for performance
            cls.save_data(data)
    #--------------------------------------------------------------------------------------------------------------------------------
    @classmethod
    def get_tab_data(cls, tab_name):
        data = cls.get_data()
        if tab_name not in data['tabs']:
            data['tabs'][tab_name] = OrderedDict({
                'buttons': [],
                'image_path': None,
                'image_opacity': 1.0,
                'image_scale': 1.0,
                'background_value': 20,
                'namespace': 'None',
                'show_dots': False,
                'show_axes': True,    
                'show_grid': True,   
                'grid_size': 50       
            })
            cls.save_data(data)
        return data['tabs'][tab_name]
    
    @classmethod
    def update_tab_data(cls, tab_name, tab_data):
        data = cls.get_data()
        data['tabs'][tab_name] = tab_data
        # Capture selected buttons before saving undo state
        selected_button_ids = cls._get_selected_button_ids()
        cls.save_undo_state("Data Change", selected_button_ids)
        cls.save_data(data, force_immediate=True)

    @classmethod
    def add_tab(cls, tab_name, operation_name="Add Tab"):
        #cls.save_undo_state(operation_name)
        data = cls.get_data()
        if tab_name not in data['tabs']:
            data['tabs'][tab_name] = OrderedDict({
                'buttons': [],
                'image_path': None,
                'image_opacity': 1.0,
                'image_scale': 1.0,
                'background_value': 20,
                'namespace': 'None',
                'show_dots': False,
                'show_axes': True,    
                'show_grid': True,   
                'grid_size': 50       
            })
            cls.save_data(data, force_immediate=True)

    @classmethod
    def delete_tab(cls, tab_name, operation_name="Delete Tab"):
        #cls.save_undo_state(operation_name)
        data = cls.get_data()
        if tab_name in data['tabs']:
            del data['tabs'][tab_name]
            cls.save_data(data, force_immediate=True)  # Force immediate for UI operations

    @classmethod
    def rename_tab(cls, old_name, new_name):
        data = cls.get_data()
        if old_name in data['tabs']:
            # Create a new OrderedDict to preserve the order
            new_tabs = OrderedDict()
            for tab_name, tab_data in data['tabs'].items():
                if tab_name == old_name:
                    new_tabs[new_name] = tab_data
                else:
                    new_tabs[tab_name] = tab_data
            data['tabs'] = new_tabs
            cls.save_data(data, force_immediate=True)  # Force immediate for UI operations
    #--------------------------------------------------------------------------------------------------------------------------------
    @classmethod
    def add_button(cls, tab_name, button_data, operation_name="Add Button"):
        #cls.save_undo_state(operation_name)
        data = cls.get_data()
        if tab_name not in data['tabs']:
            data['tabs'][tab_name] = {'buttons': [], 'image_path': None, 'image_opacity': 1.0}
        
        # Initialize default values if not present
        button_data['width'] = button_data.get('width', 80)
        button_data['height'] = button_data.get('height', 30)
        button_data['radius'] = button_data.get('radius', [3, 3, 3, 3])

        # Handle assigned_objects in new format for Blender
        if 'assigned_objects' in button_data:
            if not button_data['assigned_objects']:
                button_data['assigned_objects'] = []
            else:
                # Check if conversion needed
                first_obj = button_data['assigned_objects'][0] if button_data['assigned_objects'] else None
                if not isinstance(first_obj, dict):
                    converted_objects = []
                    for obj in button_data['assigned_objects']:
                        try:
                            if obj in bpy.data.objects:
                                obj_data = bpy.data.objects[obj]
                                converted_objects.append({
                                    'uuid': obj,
                                    'name': obj_data.name_full
                                })
                            else:
                                converted_objects.append({
                                    'uuid': obj,
                                    'name': ''
                                })
                        except:
                            continue
                    button_data['assigned_objects'] = converted_objects
        else:
            button_data['assigned_objects'] = []
        
        button_data['mode'] = button_data.get('mode', 'select')
        
        # Properly handle script data initialization
        if 'script_data' not in button_data:
            button_data['script_data'] = {
                'type': 'python',
                'python_code': '',
                'code': ''
            }
        elif button_data['script_data']:
            # Ensure all script data fields are present
            if isinstance(button_data['script_data'], dict):
                script_data = button_data['script_data']
                script_data.setdefault('type', 'python')
                script_data.setdefault('python_code', script_data.get('code', '') if script_data.get('type') == 'python' else '')
                script_data.setdefault('code', script_data.get('python_code', ''))
            else:
                button_data['script_data'] = {
                    'type': 'python',
                    'python_code': str(button_data['script_data']),
                    'code': str(button_data['script_data'])
                }
                
        # Initialize pose data if not present
        if 'pose_data' not in button_data:
            button_data['pose_data'] = {}

        data['tabs'][tab_name]['buttons'].append(button_data)
        cls.save_data(data)  # Uses batching

    @classmethod
    def update_button(cls, tab_name, button_id, button_data):
        """Update single button with batching"""
        data = cls.get_data()
        if tab_name in data['tabs']:
            for i, button in enumerate(data['tabs'][tab_name]['buttons']):
                if button['id'] == button_id:
                    data['tabs'][tab_name]['buttons'][i].update(button_data)
                    break
        cls.save_data(data)  # Uses batching

    @classmethod
    def delete_button(cls, tab_name, button_id, operation_name="Delete Button"):
        #cls.save_undo_state(operation_name)
        data = cls.get_data()
        if tab_name in data['tabs']:
            data['tabs'][tab_name]['buttons'] = [b for b in data['tabs'][tab_name]['buttons'] if b['id'] != button_id]
            cls.save_data(data, force_immediate=True)  # Force immediate for deletions
    #--------------------------------------------------------------------------------------------------------------------------------
    @classmethod
    def update_image_data(cls, tab_name, image_path, image_opacity, image_scale):
        """Update image data with batching"""
        data = cls.get_data()
        if tab_name in data['tabs']:
            data['tabs'][tab_name]['image_path'] = image_path
            data['tabs'][tab_name]['image_opacity'] = image_opacity
            data['tabs'][tab_name]['image_scale'] = image_scale
            cls.save_data(data)  # Uses batching

    @classmethod
    def update_axes_visibility(cls, tab_name, show_axes):
        data = cls.get_data()
        if tab_name in data['tabs']:
            data['tabs'][tab_name]['show_axes'] = show_axes
            cls.save_data(data)  # Uses batching

    @classmethod
    def update_dots_visibility(cls, tab_name, show_dots):
        data = cls.get_data()
        if tab_name in data['tabs']:
            data['tabs'][tab_name]['show_dots'] = show_dots
            cls.save_data(data)  # Uses batching

    @classmethod
    def update_grid_visibility(cls, tab_name, show_grid):
        """Update grid visibility setting"""
        data = cls.get_data()
        if tab_name in data['tabs']:
            data['tabs'][tab_name]['show_grid'] = show_grid
            cls.save_data(data)  # Uses batching

    @classmethod
    def update_grid_size(cls, tab_name, grid_size):
        """Update grid size setting"""
        data = cls.get_data()
        if tab_name in data['tabs']:
            data['tabs'][tab_name]['grid_size'] = grid_size
            cls.save_data(data)  # Uses batching

    @classmethod
    def update_button_positions(cls, tab_name, button_positions):
        """Update button positions with batching - important for drag performance"""
        data = cls.get_data()
        if tab_name in data['tabs']:
            if 'buttons' not in data['tabs'][tab_name]:
                data['tabs'][tab_name]['buttons'] = []
            for button in data['tabs'][tab_name]['buttons']:
                if button['id'] in button_positions:
                    button['position'] = button_positions[button['id']]
            cls.save_data(data)  # Uses batching - crucial for smooth dragging
    
    @classmethod
    def update_button_order(cls, tab_name, button_order_ids):
        """Update the order of buttons in a tab based on provided button IDs"""
        data = cls.get_data()
        
        if tab_name not in data['tabs']:
            return
        
        tab_data = data['tabs'][tab_name]
        existing_buttons = {btn['id']: btn for btn in tab_data.get('buttons', [])}
        
        # Reorder buttons based on the provided order
        reordered_buttons = []
        for button_id in button_order_ids:
            if button_id in existing_buttons:
                reordered_buttons.append(existing_buttons[button_id])
        
        # Add any buttons that weren't in the order list (shouldn't happen, but safety)
        for button_data in tab_data.get('buttons', []):
            if button_data['id'] not in button_order_ids:
                reordered_buttons.append(button_data)
        
        # Update the tab data
        tab_data['buttons'] = reordered_buttons
        cls.update_tab_data(tab_name, tab_data)

    @classmethod
    def update_tab_namespace(cls, tab_name, namespace):
        data = cls.get_data()
        if tab_name in data['tabs']:
            data['tabs'][tab_name]['namespace'] = namespace
            cls.save_data(data)  # Uses batching

    @classmethod
    def reorder_tabs(cls, new_order):
        data = cls.get_data()
        new_tabs = OrderedDict()
        for tab_name in new_order:
            if tab_name in data['tabs']:
                new_tabs[tab_name] = data['tabs'][tab_name]
        data['tabs'] = new_tabs
        cls.save_data(data, force_immediate=True)  # Force immediate for UI operations
        
    @classmethod
    def set_thumbnail_directory(cls, directory):
        data = cls.get_data()
        data['thumbnail_directory'] = directory
        cls.save_data(data, force_immediate=True)  # Force immediate for settings
        
    @classmethod
    def get_thumbnail_directory(cls):
        data = cls.get_data()
        return data.get('thumbnail_directory', '')

    @classmethod
    def flush_pending_saves(cls):
        """Force any pending saves to complete immediately"""
        with cls._save_lock:
            if cls._batch_timer:
                cls._batch_timer.cancel()
                cls._batch_timer = None
            
            if cls._pending_updates and cls._cached_data:
                cls._perform_save(cls._cached_data)

    @classmethod
    def set_batch_delay(cls, delay_seconds):
        """Adjust the batch delay for different performance needs"""
        cls._batch_delay = delay_seconds

    @classmethod
    def clear_cache(cls):
        """Clear cached data to force fresh read from Blender scene"""
        cls._cached_data = None
        cls._pending_updates = False

