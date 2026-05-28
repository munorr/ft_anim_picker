import json
import os
import shutil
import bpy
from collections import OrderedDict
from pathlib import Path

from . import custom_dialog as CD
from . import blender_main as MAIN
from . import custom_button as CB
from PySide6 import QtWidgets

# Import the data manager
from . import data_management as DM
from . import bpicker_format as BPF
from .local_file_manager import LocalFileManager

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
        'settings': all_data.get('settings', {}),  # Include settings in export
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
            # Include settings in export
            if 'settings' not in data:
                data['settings'] = DM.PickerDataManager.get_global_settings()
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
        
        # Remember this location for future file dialogs
        DM.PickerDataManager.update_global_settings(
            last_picker_file_path=os.path.dirname(file_path)
        )
            
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
    OPTIMIZED: Load picker data from a JSON file into Blender's addon preferences.
    
    Args:
        file_path (str): Path to the JSON file to load
    """
    if not os.path.exists(file_path):
        raise RuntimeError(f"File not found: {file_path}")
    
    if not file_path.lower().endswith('.json'):
        raise RuntimeError("File must be a .json file")
    
    # OPTIMIZATION: Clear cache before loading to prevent conflicts
    DM.PickerDataManager.clear_cache()
    
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
    
    # Remember this file location for path resolution and future dialogs
    file_dir = os.path.dirname(file_path)
    DM.PickerDataManager.update_global_settings(last_picker_file_path=file_dir)
    
    # Get existing data from Blender addon preferences
    try:
        current_data = get_picker_data()
    except Exception as e:
        current_data = {'tabs': OrderedDict()}
    
    # Handle conflicts and merge data
    merged_data = {
        'settings': DM.PickerDataManager.get_global_settings(),
        'tabs': OrderedDict()
    }
    
    # OPTIMIZATION: Batch process tabs instead of one at a time
    tabs_to_skip = []
    tabs_to_add = []
    
    # Process each tab in the imported data
    for tab_name, tab_data in imported_data['tabs'].items():
        if tab_name in current_data.get('tabs', {}):
            action, new_name = handle_tab_conflict(tab_name, current_data)
            
            if action == 'skip':
                tabs_to_skip.append(tab_name)
                merged_data['tabs'][tab_name] = current_data['tabs'][tab_name]
                continue
            elif action == 'rename':
                tabs_to_add.append((new_name, tab_data))
                merged_data['tabs'][new_name] = tab_data
            else:  # overwrite
                tabs_to_add.append((tab_name, tab_data))
                merged_data['tabs'][tab_name] = tab_data
        else:
            tabs_to_add.append((tab_name, tab_data))
            merged_data['tabs'][tab_name] = tab_data
    
    # Add any remaining existing tabs that weren't in the imported data
    for tab_name, tab_data in current_data.get('tabs', {}).items():
        if tab_name not in merged_data['tabs']:
            merged_data['tabs'][tab_name] = tab_data
    
    # Save the merged data to Blender addon preferences
    try:
        save_picker_data(merged_data)
        
        # OPTIMIZATION: Clear cache and undo history after import to prevent memory buildup
        DM.PickerDataManager.clear_cache()
        DM.PickerDataManager.clear_undo_history()
        
        # OPTIMIZATION: Flush any pending saves
        DM.PickerDataManager.flush_pending_saves()
        
        print(f"Successfully loaded picker data: {len(tabs_to_add)} tabs imported, {len(tabs_to_skip)} tabs skipped")
        
    except Exception as e:
        raise RuntimeError(f"Failed to store picker data: {str(e)}")


# ---------------------------------------------------------------------------
# BPicker library operations
# ---------------------------------------------------------------------------

def detect_legacy_scene_data():
    """Check if the current scene has legacy embedded picker data (no scene link).

    Returns:
        bool – True if PickerToolData exists with real user content but no
        BGENPickerLink/FTPickerLink.  Empty default data (no buttons) is
        ignored so a fresh scene is not mistaken for legacy data.
    """
    try:
        scene = bpy.context.scene
        has_data = DM.PickerDataManager.PROP_NAME in scene
        has_link = (DM.PickerDataManager.SCENE_LINK_PROP in scene or
                    DM.PickerDataManager.SCENE_LINK_PROP_LEGACY in scene)
        if not has_data or has_link:
            return False

        # Guard against false positive: initialize_data() writes DEFAULT_DATA
        # to the scene before _check_launch_state runs. Only treat it as
        # legacy if there is at least one button in any tab.
        import json
        raw = scene.get(DM.PickerDataManager.PROP_NAME, '')
        if raw:
            data = json.loads(raw)
            tabs = data.get('tabs', {})
            for tab_data in tabs.values():
                if tab_data.get('buttons'):
                    return True
        return False
    except Exception:
        return False


def convert_legacy_scene_to_bpicker(picker_name="Converted Picker"):
    """Extract current scene's embedded picker data and package as .bpicker.

    Returns:
        str – UUID of the new .bpicker in the library, or None on failure.
    """
    try:
        picker_data = DM.PickerDataManager.get_data()
        if not picker_data or not picker_data.get('tabs'):
            print("[picker_io] No picker data to convert.")
            return None

        return _create_bpicker_from_data(picker_data, picker_name)

    except Exception as e:
        print(f"[picker_io] Legacy conversion failed: {e}")
        return None


def import_legacy_json_to_bpicker(json_path):
    """Parse a legacy .json picker file and convert to .bpicker in the library.

    Collects all referenced media files (backgrounds, thumbnails), packages
    them into the archive, and adds to the central library.

    Args:
        json_path: Path to the .json picker file.

    Returns:
        str – UUID of the new .bpicker, or None on failure.
    """
    json_path = str(json_path)
    if not os.path.isfile(json_path):
        print(f"[picker_io] File not found: {json_path}")
        return None

    try:
        with open(json_path, 'r', encoding='utf-8') as f:
            data = json.load(f, object_pairs_hook=OrderedDict)
    except Exception as e:
        print(f"[picker_io] Failed to read JSON: {e}")
        return None

    if not isinstance(data, dict) or 'tabs' not in data:
        print("[picker_io] Invalid picker JSON format.")
        return None

    picker_name = Path(json_path).stem
    json_dir = os.path.dirname(json_path)

    # Temporarily set paths so resolve_image_path can find media referenced
    # in the legacy JSON (image_base_path for {base}/ and pref: formats,
    # last_picker_file_path for ./ and ../ relative paths)
    original_settings = DM.PickerDataManager.get_global_settings()
    DM.PickerDataManager.update_global_settings(last_picker_file_path=json_dir)

    # If the imported JSON carries its own base path, inject it temporarily
    imported_base = ''
    if 'settings' in data:
        imported_base = data['settings'].get('image_base_path', '')
        if imported_base:
            DM.PickerDataManager.update_global_settings(image_base_path=imported_base)

    try:
        result_uuid = _create_bpicker_from_data(data, picker_name)
    finally:
        # Restore original settings
        DM.PickerDataManager.update_global_settings(
            last_picker_file_path=original_settings.get('last_picker_file_path', ''),
        )
        # Clean up temporary base path if we set one
        if imported_base:
            if original_settings.get('image_base_path'):
                DM.PickerDataManager.update_global_settings(
                    image_base_path=original_settings.get('image_base_path', ''),
                )
            else:
                # Remove the key we temporarily added
                data_obj = DM.PickerDataManager.get_data()
                data_obj.get('settings', {}).pop('image_base_path', None)
                DM.PickerDataManager.save_data(data_obj, force_immediate=True)

    return result_uuid


def import_bpicker_to_library(bpicker_path, overwrite=False):
    """Copy a .bpicker file into the central library.

    Handles UUID conflicts by prompting the user (or using overwrite flag).

    Args:
        bpicker_path: Path to the .bpicker file.
        overwrite: If True, silently overwrite on UUID conflict.

    Returns:
        str – UUID of the picker in the library, or None on failure.
    """
    bpicker_path = str(bpicker_path)
    try:
        info = BPF.BPickerArchive.read(bpicker_path)
        picker_uuid = info['metadata'].get('uuid', '')

        # Check for UUID conflict
        conflict = LocalFileManager.check_uuid_conflict(picker_uuid)
        if conflict and not overwrite:
            # Prompt user
            action = _show_uuid_conflict_dialog(
                info['metadata'].get('picker_name', 'Unknown'),
                conflict['name'],
            )
            if action == 'overwrite':
                # Remove existing first, then import
                LocalFileManager.remove_from_library(picker_uuid)
            elif action == 'rename':
                # Create with new UUID by re-creating metadata
                new_uuid = BPF.generate_uuid()
                info['metadata']['uuid'] = new_uuid
                # Repack with new metadata
                import tempfile
                temp_dir = BPF.BPickerArchive.extract_to_temp(bpicker_path)
                try:
                    meta_path = os.path.join(temp_dir, BPF.METADATA_NAME)
                    with open(meta_path, 'w', encoding='utf-8') as f:
                        json.dump(info['metadata'], f, indent=2)
                    temp_bpicker = os.path.join(
                        tempfile.gettempdir(),
                        os.path.basename(bpicker_path)
                    )
                    BPF.BPickerArchive.repack(temp_dir, temp_bpicker)
                    bpicker_path = temp_bpicker
                    picker_uuid = new_uuid
                finally:
                    shutil.rmtree(temp_dir, ignore_errors=True)
            else:  # cancel
                return None
        elif conflict and overwrite:
            LocalFileManager.remove_from_library(picker_uuid)

        LocalFileManager.add_to_library(bpicker_path)
        return picker_uuid

    except Exception as e:
        print(f"[picker_io] Failed to import .bpicker: {e}")
        return None


# ---------------------------------------------------------------------------
# Internal helpers for bpicker creation
# ---------------------------------------------------------------------------

def _create_bpicker_from_data(picker_data, picker_name):
    """Create a .bpicker archive from picker data dict.

    Resolves all media paths, copies files into the archive, and adds
    to the library.

    Returns:
        str – UUID of the created picker, or None on failure.
    """
    from . import __init__ as pkg
    tool_version = getattr(pkg, '__version__', '')

    metadata = BPF.build_metadata(
        picker_name=picker_name,
        tool_version=tool_version,
    )
    picker_uuid = metadata['uuid']

    # Collect media files: resolve paths and build archive mapping
    media_files = {}  # archive_rel_path → absolute_source_path
    path_remap = {}   # original_stored_path → archive_rel_path

    for tab_name, tab_data in picker_data.get('tabs', {}).items():
        # Background layers
        for layer in tab_data.get('background_layers', []):
            img_stored = layer.get('path')
            if img_stored:
                abs_path = DM.PickerDataManager.resolve_image_path(img_stored, tab_name)
                if abs_path and os.path.isfile(abs_path):
                    arc_rel = f"{BPF.BACKGROUNDS_DIR}/{os.path.basename(abs_path)}"
                    arc_rel = _unique_archive_path(media_files, arc_rel)
                    media_files[arc_rel] = abs_path
                    path_remap[img_stored] = arc_rel

        # Legacy single background image
        img_stored = tab_data.get('image_path')
        if img_stored:
            abs_path = DM.PickerDataManager.resolve_image_path(img_stored, tab_name)
            if abs_path and os.path.isfile(abs_path):
                arc_rel = f"{BPF.BACKGROUNDS_DIR}/{os.path.basename(abs_path)}"
                arc_rel = _unique_archive_path(media_files, arc_rel)
                media_files[arc_rel] = abs_path
                path_remap[img_stored] = arc_rel

        # Button thumbnails
        for btn in tab_data.get('buttons', []):
            thumb_stored = btn.get('thumbnail_path')
            if thumb_stored:
                abs_path = DM.PickerDataManager.resolve_image_path(thumb_stored, tab_name)
                if abs_path and os.path.isfile(abs_path):
                    arc_rel = f"{BPF.THUMBNAILS_DIR}/{os.path.basename(abs_path)}"
                    arc_rel = _unique_archive_path(media_files, arc_rel)
                    media_files[arc_rel] = abs_path
                    path_remap[thumb_stored] = arc_rel

    # Build manifest with remapped paths
    manifest = BPF.build_manifest_from_picker_data(picker_data, path_remap)

    # Create archive in a temp location first, then add to library
    import tempfile
    safe_name = picker_name.strip()
    for ch in r'<>:"/\|?*':
        safe_name = safe_name.replace(ch, '_')
    temp_path = os.path.join(tempfile.gettempdir(), f"{safe_name}.bpicker")

    BPF.BPickerArchive.create(
        dest_path=temp_path,
        manifest=manifest,
        metadata=metadata,
        media_files=media_files,
    )

    # Add to library
    try:
        LocalFileManager.add_to_library(temp_path)
    finally:
        # Clean up temp file if it was copied
        if os.path.exists(temp_path):
            try:
                os.remove(temp_path)
            except Exception:
                pass

    return picker_uuid


def _unique_archive_path(media_files, proposed_path):
    """Ensure the archive-relative path doesn't collide with existing entries."""
    if proposed_path not in media_files:
        return proposed_path

    base, ext = os.path.splitext(proposed_path)
    i = 1
    while f"{base}_{i}{ext}" in media_files:
        i += 1
    return f"{base}_{i}{ext}"


def _show_uuid_conflict_dialog(new_name, existing_name):
    """Show a dialog when importing a .bpicker with a conflicting UUID.

    Returns:
        str – 'overwrite', 'rename', or 'cancel'.
    """
    manager = MAIN.PickerWindowManager.get_instance()
    parent_widget = manager._picker_widgets[0] if manager._picker_widgets else None
    dialog = CD.CustomDialog(parent_widget, title="Duplicate Picker", size=(300, 120))

    msg = QtWidgets.QLabel(
        f"A picker named <b><font color='#00ade6'>{existing_name}</font></b> "
        f"with the same ID already exists in your library."
    )
    msg.setWordWrap(True)
    dialog.add_widget(msg)

    buttons_layout = QtWidgets.QHBoxLayout()
    overwrite_btn = CB.CustomButton("Overwrite", color="#ff5500", tooltip="Replace the existing picker")
    rename_btn = CB.CustomButton("Keep Both", color="#00749a", tooltip="Import as a new picker with a new ID")
    cancel_btn = CB.CustomButton("Cancel", color="#444444", tooltip="Cancel import")

    buttons_layout.addWidget(overwrite_btn)
    buttons_layout.addWidget(rename_btn)
    buttons_layout.addWidget(cancel_btn)
    dialog.add_layout(buttons_layout)

    result = [None]
    overwrite_btn.clicked.connect(lambda: (result.__setitem__(0, 'overwrite'), dialog.accept()))
    rename_btn.clicked.connect(lambda: (result.__setitem__(0, 'rename'), dialog.accept()))
    cancel_btn.clicked.connect(lambda: (result.__setitem__(0, 'cancel'), dialog.reject()))

    dialog.exec_()
    return result[0] if result[0] else 'cancel'


# ---------------------------------------------------------------------------
# Tab Export / Import
# ---------------------------------------------------------------------------

def _collect_tab_media(tab_name, tab_data, media_files, path_remap):
    """Collect media files for a single tab into the archive mapping dicts.

    Mutates *media_files* and *path_remap* in place.
    """
    # Background layers
    for layer in tab_data.get('background_layers', []):
        img_stored = layer.get('path')
        if img_stored:
            abs_path = DM.PickerDataManager.resolve_image_path(img_stored, tab_name)
            if abs_path and os.path.isfile(abs_path):
                arc_rel = f"{BPF.BACKGROUNDS_DIR}/{os.path.basename(abs_path)}"
                arc_rel = _unique_archive_path(media_files, arc_rel)
                media_files[arc_rel] = abs_path
                path_remap[img_stored] = arc_rel

    # Legacy single background image
    img_stored = tab_data.get('image_path')
    if img_stored:
        abs_path = DM.PickerDataManager.resolve_image_path(img_stored, tab_name)
        if abs_path and os.path.isfile(abs_path):
            arc_rel = f"{BPF.BACKGROUNDS_DIR}/{os.path.basename(abs_path)}"
            arc_rel = _unique_archive_path(media_files, arc_rel)
            media_files[arc_rel] = abs_path
            path_remap[img_stored] = arc_rel

    # Button thumbnails
    for btn in tab_data.get('buttons', []):
        thumb_stored = btn.get('thumbnail_path')
        if thumb_stored:
            abs_path = DM.PickerDataManager.resolve_image_path(thumb_stored, tab_name)
            if abs_path and os.path.isfile(abs_path):
                arc_rel = f"{BPF.THUMBNAILS_DIR}/{os.path.basename(abs_path)}"
                arc_rel = _unique_archive_path(media_files, arc_rel)
                media_files[arc_rel] = abs_path
                path_remap[thumb_stored] = arc_rel


def export_tab_as_bpicker(tab_name, dest_path):
    """Export a single tab as a standalone .bpicker file.

    Creates a minimal archive containing only the specified tab's data
    and its referenced media files.

    Returns:
        bool – True on success.
    """
    picker_data = DM.PickerDataManager.get_data()
    if tab_name not in picker_data.get('tabs', {}):
        print(f"[picker_io] Tab '{tab_name}' not found.")
        return False

    tab_data = picker_data['tabs'][tab_name]

    # Build single-tab picker data
    single_tab_data = OrderedDict({
        'settings': {},
        'tabs': OrderedDict({tab_name: tab_data}),
    })

    from . import __init__ as pkg
    tool_version = getattr(pkg, '__version__', '')

    metadata = BPF.build_metadata(
        picker_name=f"Tab: {tab_name}",
        tool_version=tool_version,
    )

    # Collect media
    media_files = {}
    path_remap = {}
    _collect_tab_media(tab_name, tab_data, media_files, path_remap)

    manifest = BPF.build_manifest_from_picker_data(single_tab_data, path_remap)

    BPF.BPickerArchive.create(
        dest_path=dest_path,
        manifest=manifest,
        metadata=metadata,
        media_files=media_files,
    )

    print(f"[picker_io] Tab '{tab_name}' exported to {dest_path}")
    return True


def _remap_imported_media(tab_data, source_temp_dir, session):
    """Copy media from a source temp dir into the active session.

    Resolves archive-relative paths in *tab_data* and rewrites them as
    ``bpicker://`` paths pointing into the active session's temp dir.

    Returns:
        dict – updated tab_data (mutated in place).
    """
    if not session:
        return tab_data

    # Background layers
    for layer in tab_data.get('background_layers', []):
        img_rel = layer.get('path', '')
        if img_rel:
            # Strip bpicker:// prefix if present
            clean = img_rel.replace('bpicker://', '')
            src = os.path.join(source_temp_dir, clean)
            if os.path.isfile(src):
                new_path = session.add_media_file(src, BPF.BACKGROUNDS_DIR)
                if new_path:
                    layer['path'] = new_path

    # Legacy single image
    img_rel = tab_data.get('image_path', '')
    if img_rel:
        clean = img_rel.replace('bpicker://', '')
        src = os.path.join(source_temp_dir, clean)
        if os.path.isfile(src):
            new_path = session.add_media_file(src, BPF.BACKGROUNDS_DIR)
            if new_path:
                tab_data['image_path'] = new_path

    # Button thumbnails
    for btn in tab_data.get('buttons', []):
        thumb_rel = btn.get('thumbnail_path', '')
        if thumb_rel:
            clean = thumb_rel.replace('bpicker://', '')
            src = os.path.join(source_temp_dir, clean)
            if os.path.isfile(src):
                new_path = session.add_media_file(src, BPF.THUMBNAILS_DIR)
                if new_path:
                    btn['thumbnail_path'] = new_path

    return tab_data


def import_tabs_from_bpicker(bpicker_path):
    """Import all tabs from a .bpicker file into the current picker.

    Handles name conflicts via ``handle_tab_conflict()``.
    Copies media into the active session's temp dir when a session is active.

    Returns:
        list[str] – tab names that were successfully imported.
    """
    try:
        info = BPF.BPickerArchive.read(bpicker_path)
    except Exception as e:
        print(f"[picker_io] Failed to read {bpicker_path}: {e}")
        return []

    manifest = info['manifest']
    imported_tabs = manifest.get('tabs', {})

    if not imported_tabs:
        print("[picker_io] No tabs found in the .bpicker file.")
        return []

    current_data = DM.PickerDataManager.get_data()
    session = DM.PickerDataManager.get_active_session()

    # Extract source bpicker to temp for media access
    source_temp = BPF.BPickerArchive.extract_to_temp(bpicker_path)

    result_tab_names = []
    try:
        for tab_name, tab_data in imported_tabs.items():
            final_name = tab_name

            if tab_name in current_data.get('tabs', {}):
                action, new_name = handle_tab_conflict(tab_name, current_data)
                if action == 'skip':
                    continue
                elif action == 'rename':
                    final_name = new_name
                # 'overwrite' keeps final_name = tab_name

            # Remap media into session
            tab_data_copy = dict(tab_data)
            if session:
                _remap_imported_media(tab_data_copy, source_temp, session)
            else:
                # Convert manifest paths to bpicker:// format
                converted = BPF.build_picker_data_from_manifest(
                    {"tabs": {final_name: tab_data_copy}}
                )
                tab_data_copy = converted["tabs"].get(final_name, tab_data_copy)

            DM.PickerDataManager.add_tab(final_name)
            DM.PickerDataManager.update_tab_data(final_name, tab_data_copy)
            result_tab_names.append(final_name)
    finally:
        shutil.rmtree(source_temp, ignore_errors=True)

    if result_tab_names:
        print(f"[picker_io] Imported tabs: {result_tab_names}")

    return result_tab_names


def get_tab_names_from_bpicker(bpicker_path):
    """Return the list of tab names in a .bpicker archive (no extraction)."""
    try:
        info = BPF.BPickerArchive.read(bpicker_path)
    except Exception as e:
        print(f"[picker_io] Failed to read {bpicker_path}: {e}")
        return []
    return list(info['manifest'].get('tabs', {}).keys())


def import_tab_from_bpicker(bpicker_path, tab_name):
    """Import a single tab by name from a .bpicker file into the current picker.

    Returns:
        list[str] – tab names that were successfully imported (0 or 1 item).
    """
    try:
        info = BPF.BPickerArchive.read(bpicker_path)
    except Exception as e:
        print(f"[picker_io] Failed to read {bpicker_path}: {e}")
        return []

    manifest = info['manifest']
    imported_tabs = manifest.get('tabs', {})

    if tab_name not in imported_tabs:
        print(f"[picker_io] Tab '{tab_name}' not found in {bpicker_path}.")
        return []

    current_data = DM.PickerDataManager.get_data()
    session = DM.PickerDataManager.get_active_session()

    source_temp = BPF.BPickerArchive.extract_to_temp(bpicker_path)

    result_tab_names = []
    try:
        tab_data = imported_tabs[tab_name]
        final_name = tab_name

        if tab_name in current_data.get('tabs', {}):
            action, new_name = handle_tab_conflict(tab_name, current_data)
            if action == 'skip':
                return []
            elif action == 'rename':
                final_name = new_name

        tab_data_copy = dict(tab_data)
        if session:
            _remap_imported_media(tab_data_copy, source_temp, session)
        else:
            converted = BPF.build_picker_data_from_manifest(
                {"tabs": {final_name: tab_data_copy}}
            )
            tab_data_copy = converted["tabs"].get(final_name, tab_data_copy)

        DM.PickerDataManager.add_tab(final_name)
        DM.PickerDataManager.update_tab_data(final_name, tab_data_copy)
        result_tab_names.append(final_name)
    finally:
        shutil.rmtree(source_temp, ignore_errors=True)

    if result_tab_names:
        print(f"[picker_io] Imported tab: {result_tab_names}")

    return result_tab_names


def export_all_as_bpicker(dest_path, picker_name=None):
    """Export all tabs as a standalone .bpicker file to an arbitrary location.

    Unlike ``_create_bpicker_from_data`` this does NOT add the archive to the
    library — it only writes to *dest_path*.

    Args:
        dest_path: Destination file path.
        picker_name: Optional name for metadata. Defaults to filename stem.

    Returns:
        bool – True on success.
    """
    picker_data = DM.PickerDataManager.get_data()
    if not picker_data or not picker_data.get('tabs'):
        print("[picker_io] No picker data to export.")
        return False

    if not picker_name:
        picker_name = Path(dest_path).stem

    from . import __init__ as pkg
    tool_version = getattr(pkg, '__version__', '')

    metadata = BPF.build_metadata(
        picker_name=picker_name,
        tool_version=tool_version,
    )

    # Collect media files from all tabs
    media_files = {}
    path_remap = {}
    for tab_name, tab_data in picker_data.get('tabs', {}).items():
        _collect_tab_media(tab_name, tab_data, media_files, path_remap)

    manifest = BPF.build_manifest_from_picker_data(picker_data, path_remap)

    BPF.BPickerArchive.create(
        dest_path=dest_path,
        manifest=manifest,
        metadata=metadata,
        media_files=media_files,
    )

    print(f"[picker_io] Exported all tabs to {dest_path}")
    return True


def get_import_mode_dialog(has_session=True):
    """Show dialog to choose between merging tabs or opening as a new picker.

    Args:
        has_session: Whether an active picker session exists. When False the
            dialog is skipped and ``'open'`` is returned directly.

    Returns:
        str: ``'merge'``, ``'open'``, or ``'cancel'``.
    """
    if not has_session:
        return 'open'

    manager = MAIN.PickerWindowManager.get_instance()
    parent_widget = manager._picker_widgets[0] if manager._picker_widgets else None
    dialog = CD.CustomDialog(parent_widget, title="Import Picker", size=(340, 110))

    message_label = QtWidgets.QLabel("How would you like to import this picker?")
    message_label.setStyleSheet(
        "font-size: 12px; font-weight: bold; color: #dddddd; margin-bottom: 10px;"
    )
    dialog.add_widget(message_label)

    buttons_layout = QtWidgets.QHBoxLayout()
    merge_button = CB.CustomButton(
        "Merge with Current", color="#5285a6",
        tooltip="Add imported tabs to the current picker session",
    )
    open_button = CB.CustomButton(
        "Open as New", color="#00749a",
        tooltip="Replace current session with the imported picker",
    )
    cancel_button = CB.CustomButton("Cancel", color="#444444")

    buttons_layout.addWidget(merge_button)
    buttons_layout.addWidget(open_button)
    buttons_layout.addWidget(cancel_button)
    dialog.add_layout(buttons_layout)

    result = [None]
    merge_button.clicked.connect(lambda: (result.__setitem__(0, 'merge'), dialog.accept()))
    open_button.clicked.connect(lambda: (result.__setitem__(0, 'open'), dialog.accept()))
    cancel_button.clicked.connect(lambda: (result.__setitem__(0, 'cancel'), dialog.reject()))

    dialog.exec_()
    return result[0] if result[0] is not None else 'cancel'