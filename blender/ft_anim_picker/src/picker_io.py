import json
import os
import bpy
from collections import OrderedDict
from pathlib import Path

from . import custom_dialog as CD
from . import blender_main as MAIN
from . import custom_button as CB
from PySide6 import QtWidgets

# Import the data manager
from . import data_management as DM

def get_file_dialog_directory():
    """
    Get the appropriate directory for file dialogs.
    Priority: Current Blender file directory > System last directory > User home directory
    
    Returns:
        str: Directory path to use for file dialogs
    """
    # First, try to get the current Blender file's directory
    if bpy.data.filepath:
        current_file_path = bpy.data.filepath
        if current_file_path and os.path.exists(current_file_path):
            file_dir = os.path.dirname(current_file_path)
            if os.path.exists(file_dir):
                return file_dir
    
    # If no current file or invalid path, try to get the last used directory
    # from Blender's file browser preferences
    try:
        # Try to get the last directory from Blender's file browser
        if hasattr(bpy.context.preferences, 'filepaths'):
            last_directory = bpy.context.preferences.filepaths.save_directory
            if last_directory and os.path.exists(last_directory):
                return last_directory
    except:
        pass
    
    # Fallback to user's home directory
    return os.path.expanduser("~")

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
    
    
    # Use custom dialog instead of QMessageBox
    # Get the manager instance
    manager = MAIN.PickerWindowManager.get_instance()
    # Get the first active picker window if available, or None if no windows exist
    parent_widget = manager._picker_widgets[0] if manager._picker_widgets else None
    dialog = CD.CustomDialog(parent_widget, title=f"Tab Conflict", size=(260, 105))
    
    # Add message label
    message_label = QtWidgets.QLabel(f"Tab <b><font color='#00ade6'>{tab_name}</font></b> already exists.")
    message_label.setWordWrap(True)
    dialog.add_widget(message_label)
    
    # Add question label
    question_label = QtWidgets.QLabel("How would you like to handle this?")
    dialog.add_widget(question_label)
    
    # Add buttons layout
    buttons_layout = QtWidgets.QHBoxLayout()
    rename_button = QtWidgets.QPushButton("Rename")
    overwrite_button = QtWidgets.QPushButton("Overwrite")
    skip_button = QtWidgets.QPushButton("Skip")
    
    # Set button styles
    rename_button.setStyleSheet("background-color: #00749a; color: white; border-radius: 3px; padding: 5px;")
    overwrite_button.setStyleSheet("background-color: #ff5500; color: white; border-radius: 3px; padding: 5px;")
    skip_button.setStyleSheet("background-color: #444444; color: white; border-radius: 3px; padding: 5px;")
    
    buttons_layout.addWidget(rename_button)
    buttons_layout.addWidget(overwrite_button)
    buttons_layout.addWidget(skip_button)
    dialog.add_layout(buttons_layout)
    
    # Set up result variable
    result = [None]
    
    # Connect button signals
    rename_button.clicked.connect(lambda: (result.__setitem__(0, 'rename'), dialog.accept()))
    overwrite_button.clicked.connect(lambda: (result.__setitem__(0, 'overwrite'), dialog.accept()))
    skip_button.clicked.connect(lambda: (result.__setitem__(0, 'skip'), dialog.accept()))
    
    # Execute dialog
    dialog.exec_()
    
    # Get result
    clicked_action = result[0]
    
    if clicked_action == 'rename':
        new_name = get_unique_tab_name(existing_data['tabs'].keys(), tab_name)
        return 'rename', new_name
    elif clicked_action == 'overwrite':
        return 'overwrite', tab_name
    else:  # skip
        return 'skip', tab_name

def get_save_mode_dialog():
    """
    Show dialog to choose between saving current tab or all tabs
    
    Returns:
        str: 'current', 'all', or 'cancel'
    """
    # Get the manager instance
    manager = MAIN.PickerWindowManager.get_instance()
    # Get the first active picker window if available, or None if no windows exist
    parent_widget = manager._picker_widgets[0] if manager._picker_widgets else None
    dialog = CD.CustomDialog(parent_widget, title="Save Picker Data", size=(280, 100))
    
    # Add message label
    message_label = QtWidgets.QLabel("What would you like to save?")
    #message_label.setAlignment(QtWidgets.QLabel.AlignCenter)
    message_label.setStyleSheet("font-size: 12px; font-weight: bold; color: #dddddd; margin-bottom: 10px;")
    dialog.add_widget(message_label)
    
    # Add buttons layout
    buttons_layout = QtWidgets.QHBoxLayout()
    current_button = CB.CustomButton("Current Tab",color="#5285a6",tooltip="Save only the currently active tab")
    all_button = CB.CustomButton("All Tabs",color="#00749a",tooltip="Save all tabs in the picker")
    cancel_button = CB.CustomButton("Cancel",color="#444444",tooltip="Cancel the save operation")
    
    buttons_layout.addWidget(current_button)
    buttons_layout.addWidget(all_button)
    buttons_layout.addWidget(cancel_button)
    dialog.add_layout(buttons_layout)
    
    # Set up result variable
    result = [None]
    
    # Connect button signals
    current_button.clicked.connect(lambda: (result.__setitem__(0, 'current'), dialog.accept()))
    all_button.clicked.connect(lambda: (result.__setitem__(0, 'all'), dialog.accept()))
    cancel_button.clicked.connect(lambda: (result.__setitem__(0, 'cancel'), dialog.reject()))
    
    # Execute dialog
    dialog.exec_()
    
    # Return the result
    return result[0] if result[0] is not None else 'cancel'

def get_picker_data():
    """Get the current picker data from Blender's scene data using PickerDataManager"""
    # Use the existing data manager to get the data
    return DM.PickerDataManager.get_data()

def get_current_tab_data(current_tab_name):
    """Get data for only the current tab"""
    all_data = get_picker_data()
    
    if not all_data or not all_data.get('tabs'):
        raise RuntimeError("No picker data available")
    
    if current_tab_name not in all_data['tabs']:
        raise RuntimeError(f"Current tab '{current_tab_name}' not found in picker data")
    
    # Create data structure with only the current tab
    current_tab_data = {
        'tabs': OrderedDict()
    }
    current_tab_data['tabs'][current_tab_name] = all_data['tabs'][current_tab_name]
    
    return current_tab_data

def save_picker_data(data):
    """Save picker data using the existing PickerDataManager"""
    # Use the existing data manager to save the data
    try:
        DM.PickerDataManager.save_data(data)
    except Exception as e:
        raise RuntimeError(f"Failed to save picker data: {str(e)}")

def store_picker_data(file_path, current_tab_name=None, save_mode='all'):
    """
    Store picker data to a JSON file.
    
    Args:
        file_path (str): Path where the JSON file will be saved
        current_tab_name (str): Name of the current tab (required if save_mode is 'current')
        save_mode (str): 'current' to save only current tab, 'all' to save all tabs
    """
    # Get picker data based on save mode
    try:
        if save_mode == 'current':
            if not current_tab_name:
                raise RuntimeError("Current tab name is required when saving current tab only")
            data = get_current_tab_data(current_tab_name)
            print(f"Saving current tab: {current_tab_name}")
        else:  # save_mode == 'all'
            data = get_picker_data()
            print("Saving all tabs")
            
    except Exception as e:
        raise RuntimeError(f"Failed to get picker data: {str(e)}")
    
    if not data or not data.get('tabs'):
        raise RuntimeError("No picker data available to save")
    
    # Ensure file has .json extension
    if not file_path.lower().endswith('.json'):
        file_path += '.json'
    
    # Save to file
    try:
        with open(file_path, 'w') as f:
            json.dump(data, f, indent=4)
            
        # Create a summary message
        tab_count = len(data['tabs'])
        if save_mode == 'current':
            print(f"Current tab '{current_tab_name}' saved to {file_path}")
        else:
            print(f"All {tab_count} tab(s) saved to {file_path}")
            
    except Exception as e:
        raise RuntimeError(f"Failed to save picker data to file: {str(e)}")

def load_picker_data(file_path):
    """
    Load picker data from a JSON file into Blender's addon preferences.
    
    Args:
        file_path (str): Path to the JSON file to load
    """
    if not os.path.exists(file_path):
        raise RuntimeError(f"File not found: {file_path}")
    
    if not file_path.lower().endswith('.json'):
        raise RuntimeError("File must be a .json file")
    
    # Load the imported data from file
    try:
        with open(file_path, 'r') as f:
            imported_data = json.load(f, object_pairs_hook=OrderedDict)
    except json.JSONDecodeError:
        raise RuntimeError("Invalid JSON file")
    except Exception as e:
        raise RuntimeError(f"Failed to read file: {str(e)}")
    
    # Validate imported data format
    if not isinstance(imported_data, dict) or 'tabs' not in imported_data:
        raise RuntimeError("Invalid picker data format: missing 'tabs' key")
    
    # Get existing data from Blender addon preferences
    try:
        current_data = get_picker_data()
    except Exception as e:
        current_data = {'tabs': OrderedDict()}
    
    # Handle conflicts and merge data
    merged_data = {'tabs': OrderedDict()}
    
    # Process each tab in the imported data
    for tab_name, tab_data in imported_data['tabs'].items():
        if tab_name in current_data.get('tabs', {}):
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
    for tab_name, tab_data in current_data.get('tabs', {}).items():
        if tab_name not in merged_data['tabs']:
            merged_data['tabs'][tab_name] = tab_data
    
    # Save the merged data to Blender addon preferences
    try:
        save_picker_data(merged_data)
    except Exception as e:
        raise RuntimeError(f"Failed to store picker data: {str(e)}")