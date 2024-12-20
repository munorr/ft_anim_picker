import json
import os
from collections import OrderedDict
import maya.cmds as cmds
from PySide2 import QtWidgets

def get_unique_tab_name(existing_tabs, base_name):
    """
    Generate a unique tab name by appending a number if the base name already exists.
    
    Args:
        existing_tabs (list): List of existing tab names
        base_name (str): Desired base name for the tab
        
    Returns:
        str: Unique tab name
    """
    if base_name not in existing_tabs:
        return base_name
        
    counter = 1
    while f"{base_name}_{counter}" in existing_tabs:
        counter += 1
    return f"{base_name}_{counter}"

def handle_tab_conflict(tab_name, existing_data):
    """
    Handle tab name conflicts when loading picker data.
    
    Args:
        tab_name (str): The conflicting tab name
        existing_data (dict): Current picker data
        
    Returns:
        tuple: (action, new_name) where action is one of 'skip', 'rename', 'overwrite'
                and new_name is the new tab name if action is 'rename'
    """
    msgBox = QtWidgets.QMessageBox()
    msgBox.setIcon(QtWidgets.QMessageBox.Warning)
    msgBox.setText(f"Tab '{tab_name}' already exists.")
    msgBox.setInformativeText("How would you like to handle this?")
    
    rename_button = msgBox.addButton("Rename New", QtWidgets.QMessageBox.ActionRole)
    overwrite_button = msgBox.addButton("Overwrite", QtWidgets.QMessageBox.ActionRole)
    skip_button = msgBox.addButton("Skip", QtWidgets.QMessageBox.ActionRole)
    
    msgBox.exec_()
    
    clicked_button = msgBox.clickedButton()
    
    if clicked_button == rename_button:
        new_name = get_unique_tab_name(existing_data['tabs'].keys(), tab_name)
        return 'rename', new_name
    elif clicked_button == overwrite_button:
        return 'overwrite', tab_name
    else:  # skip_button
        return 'skip', tab_name

def store_picker_data(file_path):
    """
    Store the current picker data from defaultObjectSet to a JSON file.
    
    Args:
        file_path (str): Path where the JSON file will be saved
    """
    if not cmds.attributeQuery('PickerToolData', node='defaultObjectSet', exists=True):
        raise RuntimeError("No PickerToolData found in defaultObjectSet")
    
    data_string = cmds.getAttr('defaultObjectSet.PickerToolData')
    if not data_string:
        raise RuntimeError("PickerToolData is empty")
    
    try:
        data = json.loads(data_string, object_pairs_hook=OrderedDict)
    except json.JSONDecodeError:
        raise RuntimeError("Invalid JSON data in PickerToolData")
    
    if not file_path.lower().endswith('.json'):
        file_path += '.json'
    
    try:
        with open(file_path, 'w') as f:
            json.dump(data, f, indent=4)
    except Exception as e:
        raise RuntimeError(f"Failed to save picker data: {str(e)}")

def load_picker_data(file_path):
    """
    Load picker data from a JSON file into defaultObjectSet.
    
    Args:
        file_path (str): Path to the JSON file to load
    """
    if not os.path.exists(file_path):
        raise RuntimeError(f"File not found: {file_path}")
    
    if not file_path.lower().endswith('.json'):
        raise RuntimeError("File must be a .json file")
    
    try:
        with open(file_path, 'r') as f:
            imported_data = json.load(f, object_pairs_hook=OrderedDict)
    except json.JSONDecodeError:
        raise RuntimeError("Invalid JSON file")
    except Exception as e:
        raise RuntimeError(f"Failed to read file: {str(e)}")
    
    if not isinstance(imported_data, dict) or 'tabs' not in imported_data:
        raise RuntimeError("Invalid picker data format: missing 'tabs' key")
    
    # Get existing data
    if cmds.attributeQuery('PickerToolData', node='defaultObjectSet', exists=True):
        current_data_string = cmds.getAttr('defaultObjectSet.PickerToolData')
        try:
            current_data = json.loads(current_data_string, object_pairs_hook=OrderedDict)
        except:
            current_data = {'tabs': OrderedDict()}
    else:
        current_data = {'tabs': OrderedDict()}
        cmds.addAttr('defaultObjectSet', longName='PickerToolData', dataType='string')
    
    # Handle conflicts and merge data
    merged_data = {'tabs': OrderedDict()}
    
    # Process each tab in the imported data
    for tab_name, tab_data in imported_data['tabs'].items():
        if tab_name in current_data['tabs']:
            action, new_name = handle_tab_conflict(tab_name, current_data)
            
            if action == 'skip':
                merged_data['tabs'][tab_name] = current_data['tabs'][tab_name]
                continue
            elif action == 'rename':
                merged_data['tabs'][new_name] = tab_data
            else:  # overwrite
                merged_data['tabs'][tab_name] = tab_data
        else:
            merged_data['tabs'][tab_name] = tab_data
    
    # Add any remaining existing tabs that weren't in the imported data
    for tab_name, tab_data in current_data['tabs'].items():
        if tab_name not in merged_data['tabs']:
            merged_data['tabs'][tab_name] = tab_data
    
    # Save the merged data
    try:
        cmds.setAttr('defaultObjectSet.PickerToolData', json.dumps(merged_data), type='string')
    except Exception as e:
        raise RuntimeError(f"Failed to store picker data: {str(e)}")