import maya.cmds as cmds
import json
from collections import OrderedDict
import time
from threading import Timer

class PickerDataManager:
    ATTR_NAME = 'PickerToolData'
    DEFAULT_DATA = OrderedDict({
        'tabs': OrderedDict({
            'Tab 1': {
                'buttons': [],
                'image_path': None,
                'image_opacity': 1.0,
                'image_scale': 1.0,
                'background_value': 20,
                'namespace': 'None',
                'show_dots': True,
                'show_axes': True,    
                'show_grid': False,   
                'grid_size': 50       
            }
        }),
        'thumbnail_directory': ''
    })

    # Batch update system
    _batch_timer = None
    _batch_delay = 0.2  # 200ms delay for batching
    _pending_updates = False
    _last_save_time = 0
    _min_save_interval = 0.1  # Minimum 100ms between saves
    _cached_data = None

    @classmethod
    def initialize_data(cls):
        if not cmds.objExists('defaultObjectSet'):
            cmds.createNode('objectSet', name='defaultObjectSet')
        
        if not cmds.attributeQuery(cls.ATTR_NAME, node='defaultObjectSet', exists=True):
            cmds.addAttr('defaultObjectSet', longName=cls.ATTR_NAME, dataType='string')
            cls.save_data(cls.DEFAULT_DATA, force_immediate=True)

    @classmethod
    def reload_data_from_maya(cls):
        """Force reload data from Maya, clearing any cached data"""
        # Clear cached data
        cls._cached_data = None
        cls._pending_updates = False
        
        # Force initialize data if needed
        cls.initialize_data()
        
        # Get fresh data from Maya
        data_string = cmds.getAttr(f'defaultObjectSet.{cls.ATTR_NAME}')
        if data_string:
            try:
                data = json.loads(data_string, object_pairs_hook=OrderedDict)
                # Update cache with fresh data
                cls._cached_data = data
                return data
            except json.JSONDecodeError:
                cmds.warning("Invalid data in PickerToolData. Resetting to default.")
                cls.save_data(cls.DEFAULT_DATA, force_immediate=True)
                return cls.DEFAULT_DATA
        
        cls._cached_data = cls.DEFAULT_DATA
        return cls.DEFAULT_DATA
    
    @classmethod
    def get_data(cls):
        """Get data with caching for better performance"""
        # Return cached data if available and recent
        if cls._cached_data is not None and not cls._pending_updates:
            return cls._cached_data
            
        cls.initialize_data()
        data_string = cmds.getAttr(f'defaultObjectSet.{cls.ATTR_NAME}')
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
                                            nodes = cmds.ls(obj, long=True)
                                            if nodes:
                                                converted_objects.append({
                                                    'uuid': obj,
                                                    'long_name': nodes[0]
                                                })
                                            else:
                                                converted_objects.append({
                                                    'uuid': obj,
                                                    'long_name': ''
                                                })
                                        except:
                                            continue
                                    button['assigned_objects'] = converted_objects
                
                # Cache the data
                cls._cached_data = data
                
                # Save converted data back to storage if needed
                if cls._pending_updates:
                    cls.save_data(data, force_immediate=True)
                    
                return data
                
            except json.JSONDecodeError:
                cmds.warning("Invalid data in PickerToolData. Resetting to default.")
                cls.save_data(cls.DEFAULT_DATA, force_immediate=True)
                return cls.DEFAULT_DATA
        
        cls._cached_data = cls.DEFAULT_DATA
        return cls.DEFAULT_DATA

    @classmethod
    def save_data(cls, data, force_immediate=False):
        """Save data with batching to improve performance"""
        # Update cache
        cls._cached_data = data
        
        current_time = time.time()
        
        # Force immediate save for critical operations
        if force_immediate:
            cls._perform_save(data)
            return
            
        # Check if we need to throttle saves
        if current_time - cls._last_save_time < cls._min_save_interval:
            # Schedule a batched save
            cls._schedule_batched_save(data)
            return
            
        # Perform immediate save if enough time has passed
        cls._perform_save(data)

    @classmethod
    def _perform_save(cls, data):
        """Actually perform the save operation"""
        try:
            cmds.setAttr(f'defaultObjectSet.{cls.ATTR_NAME}', json.dumps(data), type='string')
            cls._last_save_time = time.time()
            cls._pending_updates = False
            
            # Cancel any pending batch timer since we just saved
            if cls._batch_timer:
                cls._batch_timer.cancel()
                cls._batch_timer = None
                
        except Exception as e:
            cmds.warning(f"Failed to save picker data: {e}")

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
                'show_dots': True,
                'show_axes': True,    # ADD THIS LINE
                'show_grid': False,   # ADD THIS LINE
                'grid_size': 50       # ADD THIS LINE
            })
            cls.save_data(data)
        return data['tabs'][tab_name]

    @classmethod
    def update_tab_data(cls, tab_name, tab_data):
        """Update tab data with batching"""
        data = cls.get_data()
        data['tabs'][tab_name] = tab_data
        cls.save_data(data)  # Uses batching automatically

    @classmethod
    def add_tab(cls, tab_name):
        data = cls.get_data()
        if tab_name not in data['tabs']:
            data['tabs'][tab_name] = OrderedDict({
                'buttons': [],
                'image_path': None,
                'image_opacity': 1.0,
                'image_scale': 1.0,
                'background_value': 20,
                'namespace': 'None',
                'show_dots': True,
                'show_axes': True,    # ADD THIS LINE
                'show_grid': False,   # ADD THIS LINE
                'grid_size': 10       # ADD THIS LINE
            })
            cls.save_data(data, force_immediate=True)

    @classmethod
    def delete_tab(cls, tab_name):
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

    @classmethod
    def add_button(cls, tab_name, button_data):
        data = cls.get_data()
        if tab_name not in data['tabs']:
            data['tabs'][tab_name] = {'buttons': [], 'image_path': None, 'image_opacity': 1.0}
        
        # Initialize default values if not present
        button_data['width'] = button_data.get('width', 80)
        button_data['height'] = button_data.get('height', 30)
        button_data['radius'] = button_data.get('radius', [3, 3, 3, 3])

        # Handle assigned_objects in old or new format
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
                            nodes = cmds.ls(obj, long=True)
                            if nodes:
                                converted_objects.append({
                                    'uuid': obj,
                                    'long_name': nodes[0]
                                })
                            else:
                                converted_objects.append({
                                    'uuid': obj,
                                    'long_name': ''
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
                'mel_code': '',
                'code': ''
            }
        elif button_data['script_data']:
            # Ensure all script data fields are present
            if isinstance(button_data['script_data'], dict):
                script_data = button_data['script_data']
                script_data.setdefault('type', 'python')
                script_data.setdefault('python_code', script_data.get('code', '') if script_data.get('type') == 'python' else '')
                script_data.setdefault('mel_code', script_data.get('code', '') if script_data.get('type') == 'mel' else '')
                script_data.setdefault('code', script_data.get('python_code' if script_data['type'] == 'python' else 'mel_code', ''))
            else:
                button_data['script_data'] = {
                    'type': 'python',
                    'python_code': str(button_data['script_data']),
                    'mel_code': '',
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
    def delete_button(cls, tab_name, button_id):
        data = cls.get_data()
        if tab_name in data['tabs']:
            data['tabs'][tab_name]['buttons'] = [b for b in data['tabs'][tab_name]['buttons'] if b['id'] != button_id]
            cls.save_data(data, force_immediate=True)  # Force immediate for deletions

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
        """Update button positions with batching - this is called frequently during dragging"""
        data = cls.get_data()
        if tab_name in data['tabs']:
            if 'buttons' not in data['tabs'][tab_name]:
                data['tabs'][tab_name]['buttons'] = []
            for button in data['tabs'][tab_name]['buttons']:
                if button['id'] in button_positions:
                    button['position'] = button_positions[button['id']]
            cls.save_data(data)  # Uses batching - important for drag performance
    
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
        if cls._batch_timer:
            cls._batch_timer.cancel()
            cls._batch_timer = None
        
        if cls._pending_updates and cls._cached_data:
            cls._perform_save(cls._cached_data)

    @classmethod
    def set_batch_delay(cls, delay_seconds):
        """Adjust the batch delay for different performance needs"""
        cls._batch_delay = delay_seconds
    #----------------------------------------------------------------------------------------------------------------------------------------
    @classmethod
    def cleanup_stale_references(cls):
        """Clean up any stale object references in the data manager"""
        # Clear any cached data that might hold onto Maya objects
        if hasattr(cls, '_cached_data'):
            cls._cached_data.clear()
        
        # Clear any pending operations
        if hasattr(cls, '_pending_saves'):
            cls._pending_saves.clear()
    
    @classmethod
    def force_garbage_collection(cls):
        """Force cleanup of Maya-Python object references"""
        import gc
        
        # Clear Maya command cache if it exists
        try:
            import maya.cmds as cmds
            # Maya sometimes caches object references
            cmds.flushUndo()
        except:
            pass
        
        # Force Python garbage collection
        gc.collect()
