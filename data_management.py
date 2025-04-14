import maya.cmds as cmds
import json
from collections import OrderedDict

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
                'show_dots': True
            }
        }),
        'thumbnail_directory': ''  # Default empty string for thumbnail directory
    })

    @classmethod
    def initialize_data(cls):
        if not cmds.objExists('defaultObjectSet'):
            cmds.createNode('objectSet', name='defaultObjectSet')
        
        if not cmds.attributeQuery(cls.ATTR_NAME, node='defaultObjectSet', exists=True):
            cmds.addAttr('defaultObjectSet', longName=cls.ATTR_NAME, dataType='string')
            cls.save_data(cls.DEFAULT_DATA)

    @classmethod
    def get_data(cls):
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
                
                # Save converted data back to storage
                cls.save_data(data)
                return data
                
            except json.JSONDecodeError:
                cmds.warning("Invalid data in PickerToolData. Resetting to default.")
                cls.save_data(cls.DEFAULT_DATA)
                return cls.DEFAULT_DATA
        return cls.DEFAULT_DATA

    @classmethod
    def save_data(cls, data):
        cmds.setAttr(f'defaultObjectSet.{cls.ATTR_NAME}', json.dumps(data), type='string')

    @classmethod
    def get_tab_data(cls, tab_name):
        data = cls.get_data()
        if tab_name not in data['tabs']:
            data['tabs'][tab_name] = OrderedDict({
                'buttons': [],
                'image_path': None,
                'image_opacity': 1.0,
                'image_scale': 1.0,
                'namespace': 'None'
            })
            cls.save_data(data)
        return data['tabs'][tab_name]

    @classmethod
    def update_tab_data(cls, tab_name, tab_data):
        data = cls.get_data()
        data['tabs'][tab_name] = tab_data
        cls.save_data(data)

    @classmethod
    def add_tab(cls, tab_name):
        data = cls.get_data()
        if tab_name not in data['tabs']:
            data['tabs'][tab_name] = OrderedDict({
                'buttons': [],
                'image_path': None,
                'image_opacity': 1.0
            })
            cls.save_data(data)

    @classmethod
    def delete_tab(cls, tab_name):
        data = cls.get_data()
        if tab_name in data['tabs']:
            del data['tabs'][tab_name]
            cls.save_data(data)

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
            cls.save_data(data)

    @classmethod
    def add_button(cls, tab_name, button_data):
        data = cls.get_data()
        if tab_name not in data['tabs']:
            data['tabs'][tab_name] = {'buttons': [], 'image_path': None, 'image_opacity': 1.0}
        
        # Initialize default values if not present
        button_data['width'] = button_data.get('width', 80)
        button_data['height'] = button_data.get('height', 30)
        button_data['radius'] = button_data.get('radius', [3, 3, 3, 3])
        #button_data['assigned_objects'] = button_data.get('assigned_objects', [])

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
        cls.save_data(data)

    @classmethod
    def update_button(cls, tab_name, button_id, button_data):
        data = cls.get_data()
        if tab_name in data['tabs']:
            for i, button in enumerate(data['tabs'][tab_name]['buttons']):
                if button['id'] == button_id:
                    data['tabs'][tab_name]['buttons'][i].update(button_data)
                    break
        cls.save_data(data)

    @classmethod
    def delete_button(cls, tab_name, button_id):
        data = cls.get_data()
        if tab_name in data['tabs']:
            data['tabs'][tab_name]['buttons'] = [b for b in data['tabs'][tab_name]['buttons'] if b['id'] != button_id]
            cls.save_data(data)

    @classmethod
    def update_image_data(cls, tab_name, image_path, image_opacity, image_scale):
        data = cls.get_data()
        if tab_name in data['tabs']:
            data['tabs'][tab_name]['image_path'] = image_path
            data['tabs'][tab_name]['image_opacity'] = image_opacity
            data['tabs'][tab_name]['image_scale'] = image_scale
            cls.save_data(data)

    @classmethod
    def update_axes_visibility(cls, tab_name, show_axes):
        data = cls.get_data()
        if tab_name in data['tabs']:
            data['tabs'][tab_name]['show_axes'] = show_axes
            cls.save_data(data)

    @classmethod
    def update_dots_visibility(cls, tab_name, show_dots):
        data = cls.get_data()
        if tab_name in data['tabs']:
            data['tabs'][tab_name]['show_dots'] = show_dots
            cls.save_data(data)

    @classmethod
    def update_button_positions(cls, tab_name, button_positions):
        data = cls.get_data()
        if tab_name in data['tabs']:
            if 'buttons' not in data['tabs'][tab_name]:
                data['tabs'][tab_name]['buttons'] = []
            for button in data['tabs'][tab_name]['buttons']:
                if button['id'] in button_positions:
                    button['position'] = button_positions[button['id']]
            cls.save_data(data)
    
    @classmethod
    def update_tab_namespace(cls, tab_name, namespace):
        data = cls.get_data()
        if tab_name in data['tabs']:
            data['tabs'][tab_name]['namespace'] = namespace
            cls.save_data(data)
    @classmethod
    def reorder_tabs(cls, new_order):
        data = cls.get_data()
        new_tabs = OrderedDict()
        for tab_name in new_order:
            if tab_name in data['tabs']:
                new_tabs[tab_name] = data['tabs'][tab_name]
        data['tabs'] = new_tabs
        cls.save_data(data)
        
    @classmethod
    def set_thumbnail_directory(cls, directory):
        data = cls.get_data()
        data['thumbnail_directory'] = directory
        cls.save_data(data)
        
    @classmethod
    def get_thumbnail_directory(cls):
        data = cls.get_data()
        return data.get('thumbnail_directory', '')