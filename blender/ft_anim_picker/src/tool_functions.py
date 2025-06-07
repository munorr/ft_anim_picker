#import maya.cmds as cmds
#import maya.mel as mel
#import maya.api.OpenMaya as om
#from maya import OpenMayaUI as omui
import bpy
from functools import wraps
import re
import json

from PySide6 import QtWidgets, QtCore, QtGui
from PySide6.QtGui import QColor
from PySide6.QtCore import QTimer, QPropertyAnimation, QEasingCurve
from shiboken6 import wrapInstance

from . utils import undoable, shortcuts
from . import custom_button as CB
from . import custom_slider as CS
from . import custom_dialog as CD
from . import blender_ui as UI
from . import blender_main as MAIN

class animation_tool_layout:
    def show_mirror_pose_dialog(self):
        """
        Shows a dialog to input custom naming conventions for left and right sides.
        This allows users to specify custom prefixes or suffixes for mirroring poses.
        """

        # Create custom dialog for mirror pose options
        manager = MAIN.PickerWindowManager.get_instance()
        parent = manager._picker_widgets[0] if manager._picker_widgets else None
        dialog = CD.CustomDialog(parent=parent, title="Mirror Pose Options", size=(250, 180))
        
        # Create form layout for the inputs
        form_layout = QtWidgets.QFormLayout()
        
        # Create input fields for left and right naming conventions
        left_input = QtWidgets.QLineEdit()
        left_input.setPlaceholderText("e.g., L_, left_, _L, _left")
        
        right_input = QtWidgets.QLineEdit()
        right_input.setPlaceholderText("e.g., R_, right_, _R, _right")
        
        # Add fields to form layout
        form_layout.addRow("Left Side Identifier:", left_input)
        form_layout.addRow("Right Side Identifier:", right_input)
        
        # Add explanation text
        explanation = QtWidgets.QLabel("Enter custom naming conventions for left and right sides. "
                                   "These will be used to identify and mirror objects between sides.")
        explanation.setWordWrap(True)
        
        # Create layout for the dialog
        main_layout = QtWidgets.QVBoxLayout()
        main_layout.addWidget(explanation)
        main_layout.addLayout(form_layout)
        
        # Add the layout to the dialog
        dialog.add_layout(main_layout)
        
        # Add buttons
        def apply_custom_mirror():
            # Get the values from the input fields
            left_value = left_input.text().strip()
            right_value = right_input.text().strip()
            
            # Validate inputs
            if not left_value or not right_value:
                manager = MAIN.PickerWindowManager.get_instance()
                parent = manager._picker_widgets[0] if manager._picker_widgets else None
                error_dialog = CD.CustomDialog(parent=parent, title="Error", size=(250, 100), info_box=True)
                error_label = QtWidgets.QLabel("Both left and right identifiers must be specified.")
                error_label.setWordWrap(True)
                error_dialog.add_widget(error_label)
                error_dialog.add_button_box()
                error_dialog.exec_()
                return
            
            # Call the apply_mirror_pose function with custom naming conventions
            apply_mirror_pose(L=left_value, R=right_value)
            
            # Close the dialog
            dialog.accept()
        
        # Add apply and cancel buttons
        button_box = QtWidgets.QDialogButtonBox()
        apply_button = button_box.addButton("Apply", QtWidgets.QDialogButtonBox.AcceptRole)
        cancel_button = button_box.addButton("Cancel", QtWidgets.QDialogButtonBox.RejectRole)
        
        # Connect button signals
        apply_button.clicked.connect(apply_custom_mirror)
        cancel_button.clicked.connect(dialog.reject)
        
        # Add button box to dialog
        dialog.add_widget(button_box)
        
        # Show the dialog
        dialog.exec_()
    
    def __init__(self):
        self.layout = QtWidgets.QVBoxLayout()
        lm = 1 # layout margin
        self.layout.setContentsMargins(lm, lm, lm, lm)
        self.layout.setSpacing(lm)
        #---------------------------------------------------------------------------------------------------------------------------------------------------------------------------
        self.tools_scroll_frame = QtWidgets.QFrame()
        self.tools_scroll_frame.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Fixed)
        self.tools_scroll_frame.setStyleSheet(f'''QFrame {{border: 0px solid gray; border-radius: 3px; background-color: rgba(36, 36, 36, 0);}}''')
        #self.tools_scroll_frame.setFixedHeight(24)
        self.tools_scroll_frame_layout = QtWidgets.QVBoxLayout(self.tools_scroll_frame)
        self.tools_scroll_frame_layout.setContentsMargins(0, 0, 0, 0)
        self.tools_scroll_frame_layout.setSpacing(0)

        self.tools_scroll_area = CS.HorizontalScrollArea()
        self.tools_scroll_area.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Fixed)
        self.tools_scroll_area.setFixedHeight(22)
        self.tools_scroll_area.setWidgetResizable(True)
        
        self.tools_scroll_area.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)
        self.tools_scroll_area.setVerticalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)
        self.tools_scroll_area.setStyleSheet("""
            QScrollArea {
                background-color: transparent;
                border: none;
            }
            QScrollBar:horizontal {
                border: none;
                background: transparent;
                height: 8px;
                margin: 0px 0px 0px 0px;
            }
            QScrollBar::handle:horizontal {
                background: rgba(100, 100, 100, 0.5);
                min-width: 20px;
                border-radius: 0px;
            }
            QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {
                width: 0px;
            }
        """)
        self.tools_scroll_area.setWidget(self.tools_scroll_frame)
        #---------------------------------------------------------------------------------------------------------------------------------------------------------------------------
        #---------------------------------------------------------------------------------------------------------------------------------------------------------------------------
        self.col1 = QtWidgets.QHBoxLayout()
        self.col1.setSpacing(5)
        self.col2 = QtWidgets.QHBoxLayout()
        self.col2.setSpacing(4)
        #---------------------------------------------------------------------------------------------------------------------------------------------------------------------------
        ts = 11 # text size
        bh = 20 # button height
        #---------------------------------------------------------------------------------------------------------------------------------------------------------------------------
        reset_transform_button = CB.CustomButton(text='Reset', icon=':delete.png', color='#222222', size=14, tooltip="Resets the object transform to Origin.",
                                                 text_size=ts, height=bh,ContextMenu=True, onlyContext=False)
        reset_transform_button.addToMenu("Move", reset_move, icon='delete.png', position=(0,0))
        reset_transform_button.addToMenu("Rotate", reset_rotate, icon='delete.png', position=(1,0))
        reset_transform_button.addToMenu("Scale", reset_scale, icon='delete.png', position=(2,0))
        #---------------------------------------------------------------------------------------------------------------------------------------------------------------------------
        reset_transform_button.singleClicked.connect(reset_all)
        #---------------------------------------------------------------------------------------------------------------------------------------------------------------------------
        self.col1.addWidget(reset_transform_button)

        #---------------------------------------------------------------------------------------------------------------------------------------------------------------------------
        self.tools_scroll_frame_layout.addLayout(self.col1)
        self.tools_scroll_frame_layout.addSpacing(2)
        self.tools_scroll_frame_layout.addLayout(self.col2)
        self.layout.addWidget(self.tools_scroll_area)
        #---------------------------------------------------------------------------------------------------------------------------------------------------------------------------

def reset_move():
    with bpy.context.temp_override(window=bpy.context.window_manager.windows[0]):
        if bpy.context.mode == 'POSE':
            bpy.ops.pose.loc_clear()
        elif bpy.context.mode == 'OBJECT':
            bpy.ops.object.location_clear(clear_delta=False)

def reset_rotate():
    with bpy.context.temp_override(window=bpy.context.window_manager.windows[0]):
        if bpy.context.mode == 'POSE':
            bpy.ops.pose.rot_clear()
        elif bpy.context.mode == 'OBJECT':
            bpy.ops.object.rotation_clear(clear_delta=False)

def reset_scale():
    with bpy.context.temp_override(window=bpy.context.window_manager.windows[0]):
        if bpy.context.mode == 'POSE':
            bpy.ops.pose.scale_clear()
        elif bpy.context.mode == 'OBJECT':
            bpy.ops.object.scale_clear(clear_delta=False)

@undoable
def reset_all():
    '''with bpy.context.temp_override(window=bpy.context.window_manager.windows[0]):
        if bpy.context.mode == 'POSE':
            bpy.ops.pose.loc_clear()
            bpy.ops.pose.rot_clear()
            bpy.ops.pose.scale_clear()
        elif bpy.context.mode == 'OBJECT':
            bpy.ops.object.location_clear(clear_delta=False)
            bpy.ops.object.rotation_clear(clear_delta=False)
            bpy.ops.object.scale_clear(clear_delta=False)'''
    with bpy.context.temp_override(window=bpy.context.window_manager.windows[0]):
        active_object = bpy.context.view_layer.objects.active
        if bpy.context.mode == 'POSE':
            for bone in selected_bones():
                active_object.pose.bones[bone].location = (0, 0, 0)
                # Try different rotation methods
                try:
                    active_object.pose.bones[bone].rotation_euler = (0, 0, 0)
                except:
                    active_object.pose.bones[bone].rotation_quaternion = (1, 0, 0, 0)
                finally:
                    pass
                active_object.pose.bones[bone].scale = (1, 1, 1)
        elif bpy.context.mode == 'OBJECT':
            for obj in selected_objects():
                bpy.data.objects[obj].location = (0, 0, 0)
                # Try different rotation methods
                try:
                    bpy.data.objects[obj].rotation_euler = (0, 0, 0)
                except:
                    bpy.data.objects[obj].rotation_quaternion = (1, 0, 0, 0)
                finally:
                    pass
                bpy.data.objects[obj].scale = (1, 1, 1)

def selected_objects():
    object_list = []
    selected_objects = []
    vl_objects = bpy.context.view_layer.objects.items()
    for object in vl_objects:
        object_list.append(object[0])

    for obj in object_list:
        if bpy.context.view_layer.objects[obj].select_get():
            selected_objects.append(obj)
    #print(selected_objects)
    return selected_objects

def selcected_bones_in_pose_mode():
    with bpy.context.temp_override(window=bpy.context.window_manager.windows[0]):
        objects_in_pose_mode = []
        for obj in bpy.data.objects:
            if obj.type == 'ARMATURE' and obj.mode == 'POSE':
                objects_in_pose_mode.append(obj)
        
        selected_bones = []
        for obj in objects_in_pose_mode:
            for bone in obj.data.bones:
                if bone.select:
                    selected_bones.append(bone.name)
        return selected_bones

def deselect_all_selected_bones_in_pose_mode():
    with bpy.context.temp_override(window=bpy.context.window_manager.windows[0]):
        selected_bones = selcected_bones_in_pose_mode()
        for bone in selected_bones:
            bpy.data.objects[bone].select_set(False)

def selected_bones():
    with bpy.context.temp_override(window=bpy.context.window_manager.windows[0]):
        active_object = bpy.context.view_layer.objects.active
        if active_object.type == 'ARMATURE':
            selected_bones = [bone.name for bone in active_object.data.bones if bone.select]
            #print(selected_bones)
            return selected_bones
        else:
            #print("No active armature object.")
            return []

def active_object():
    return bpy.context.view_layer.objects.active
#---------------------------------------------------------------------------------------------------------------


@shortcuts(t='text', c='color', o='opacity', s='selectable', sb='source_button', tb='target_buttons')
def button_appearance(text="", color="", opacity="", selectable="", source_button=None, target_buttons=None):
    """
    Changes the appearance of buttons in the animation picker.
    
    This function allows modifying the text, color, and opacity of buttons.
    If a parameter is left empty, that property will remain unchanged.
    
    When called from a script attached to a button, it will modify that specific button.
    When called directly, it will modify all selected buttons.
    
    Can be used in button scripts with the @TF.button_appearance() qualifier syntax:
    @TF.button_appearance(text="New Label", color="#FF0000")
    
    Args:
        text (str, optional): New text/label for the button(s). Default is "".
        color (str, optional): New color for the button(s) in hex format (e.g., "#FF0000"). Default is "".
        opacity (str, optional): New opacity value for the button(s) between 0 and 1. Default is "".
        selectable (str, optional): Whether the button can be selected in select mode (not edit mode). 
            Values can be "True"/"False" or "1"/"0". Default is "" (no change).
        source_button (PickerButton, optional): The button that executed the script. Default is None.
            This is automatically set when the function is called from a button's script.
        target_buttons (list or str, optional): Specific buttons to modify. Can be:
            - A list of button objects
            - A list of button unique IDs as strings
            - A single button unique ID as a string
            - None (default): Uses source_button if called from a script, or selected buttons otherwise
    
    Example:
        button_appearance(text="New Label")  # Only changes the text
        button_appearance(color="#FF0000")  # Only changes the color to red
        button_appearance(opacity="0.5")    # Only changes the opacity to 50%
        button_appearance(selectable="False")  # Makes the button not selectable in select mode
        button_appearance(text="New Label", color="#FF0000", opacity="0.8")  # Changes all properties
        
        # In button scripts with qualifier syntax:
        @TF.button_appearance(text="IK")
        @TF.button_appearance(text="FK", color="#FF0000")
    """
    # Import needed modules
    from . import blender_main as MAIN
    import inspect
    
    # Determine if this function is being called from a button's script
    is_from_script = False
    script_source_button = None
    
    if source_button is None:
        # Walk up the call stack to find the executing button
        for frame_info in inspect.stack():
            if frame_info.function == 'execute_script_command':
                # Found the execute_script_command frame
                if hasattr(frame_info, 'frame') and 'self' in frame_info.frame.f_locals:
                    potential_button = frame_info.frame.f_locals['self']
                    if hasattr(potential_button, 'mode') and hasattr(potential_button, 'script_data'):
                        # This is the button that's executing the script
                        script_source_button = potential_button
                        is_from_script = True
                        break
    else:
        script_source_button = source_button
        is_from_script = True
    
    # Get the correct picker window instance
    target_picker_widget = None
    
    if script_source_button:
        # Find the picker widget that contains this button by walking up the widget hierarchy
        current_widget = script_source_button
        while current_widget:
            # Check if this widget is a BlenderAnimPickerWindow
            if current_widget.__class__.__name__ == 'BlenderAnimPickerWindow':
                target_picker_widget = current_widget
                break
            current_widget = current_widget.parent()
    
    # If we couldn't find the specific window, fall back to manager approach
    if not target_picker_widget:
        manager = MAIN.PickerWindowManager.get_instance()
        if not manager or not manager._picker_widgets:
            print("No picker widgets found.")
            return
        # Use the first available picker widget as fallback
        target_picker_widget = manager._picker_widgets[0]
    
    # Get all buttons from the correct picker widget instance only
    all_buttons = []
    
    # Try different ways to access the canvas from the target picker widget
    canvas = None
    
    # Method 1: Direct canvas attribute
    if hasattr(target_picker_widget, 'canvas'):
        canvas = target_picker_widget.canvas
    
    # Method 2: Look for canvas in tab system
    elif hasattr(target_picker_widget, 'tab_system'):
        if target_picker_widget.tab_system.current_tab:
            current_tab = target_picker_widget.tab_system.current_tab
            if current_tab in target_picker_widget.tab_system.tabs:
                canvas = target_picker_widget.tab_system.tabs[current_tab]['canvas']
    
    # Method 3: Search for canvas in children of the target widget only
    if not canvas:
        for child in target_picker_widget.findChildren(QtWidgets.QWidget):
            if hasattr(child, 'buttons') and isinstance(child.buttons, list):
                canvas = child
                break
    
    # If we found a canvas, get its buttons
    if canvas and hasattr(canvas, 'buttons'):
        all_buttons.extend(canvas.buttons)
    
    # If we still don't have any buttons from the target widget, search more thoroughly
    if not all_buttons:
        for child in target_picker_widget.findChildren(QtWidgets.QWidget):
            if hasattr(child, 'mode') and hasattr(child, 'label') and hasattr(child, 'unique_id'):
                all_buttons.append(child)
    
    # If we still don't have any buttons, give up
    if not all_buttons:
        print("No buttons found in the target picker widget.")
        return
    
    # Get buttons to modify
    buttons_to_modify = []
    
    # Case 1: Specific target buttons provided
    if target_buttons is not None:
        # Convert single string to list
        if isinstance(target_buttons, str):
            target_buttons = [target_buttons]
            
        # Process each target
        for target in target_buttons:
            if isinstance(target, str):
                # Find buttons by unique ID only in the target widget
                for btn in all_buttons:
                    # Match by unique ID
                    if hasattr(btn, 'unique_id') and btn.unique_id == target:
                        buttons_to_modify.append(btn)
                        break
            else:
                # Assume it's a button object - verify it belongs to the target widget
                if target in all_buttons:
                    buttons_to_modify.append(target)
    
    # Case 2: Source button provided or detected from script execution
    elif script_source_button is not None:
        # Use the source button, but verify it belongs to the target widget
        if script_source_button in all_buttons:
            buttons_to_modify = [script_source_button]
        else:
            print("Source button not found in the target picker widget.")
            return
    
    # Case 3: Default to selected buttons in the target widget only
    else:
        # Get selected buttons from the target widget only
        buttons_to_modify = [btn for btn in all_buttons if hasattr(btn, 'is_selected') and btn.is_selected]
    
    # Check if we have any buttons to modify
    if not buttons_to_modify:
        print("No buttons to modify in the target picker widget. Please select at least one button or call this function from a button's script.")
        return
    
    # Process and validate the opacity value
    opacity_value = None
    if opacity == 0:
        opacity = 0.001
    if opacity:
        try:
            opacity_value = float(opacity)
            if opacity_value < 0 or opacity_value > 1:
                print("Opacity must be between 0 and 1. Using current opacity.")
                opacity_value = None
        except ValueError:
            print(f"Invalid opacity value: {opacity}. Using current opacity.")
    
    # Process and validate the selectable value
    selectable_value = None
    selectable = str(selectable)
    if selectable:
        if selectable.lower() in ["true", "1"]:
            selectable_value = True
        elif selectable.lower() in ["false", "0"]:
            selectable_value = False
        else:
            print(f"Invalid selectable value: {selectable}. Use 'True'/'False' or '1'/'0'. Using current setting.")
    
    # Track if any changes were made
    changes_made = False
    modified_buttons = []  # Track which buttons were actually modified
    
    # Apply changes to all buttons
    for button in buttons_to_modify:
        button_changed = False
        
        # Update text if provided
        if text:
            button.label = text
            # Reset text pixmap cache to force redraw
            button.text_pixmap = None
            button.pose_pixmap = None
            button.last_zoom_factor = 0
            button_changed = True
        
        # Update color if provided
        if color:
            # Validate color format
            if color.startswith('#') and (len(color) == 7 or len(color) == 9):
                button.color = color
                button_changed = True
            else:
                print(f"Invalid color format: {color}. Color should be in hex format (e.g., #FF0000).")
        
        # Update opacity if provided and valid
        if opacity_value is not None:
            button.opacity = opacity_value
            button_changed = True
            
        # Update selectable state if provided and valid
        if selectable_value is not None:
            # Add selectable attribute if it doesn't exist
            if not hasattr(button, 'selectable'):
                button.selectable = True  # Default to True for backward compatibility
            button.selectable = selectable_value
            button_changed = True
        
        # If any changes were made to this button, track it for updates
        if button_changed:
            changes_made = True
            modified_buttons.append(button)
            
            # Update tooltip and force redraw
            button.update_tooltip()
            button.update()
    
    # Process database updates for ALL modified buttons at once
    if modified_buttons and canvas:
        # Get the current tab from the target picker widget
        current_tab = None
        if hasattr(target_picker_widget, 'tab_system') and target_picker_widget.tab_system.current_tab:
            current_tab = target_picker_widget.tab_system.current_tab
        
        if current_tab:
            # Import data management module
            from . import data_management as DM
            
            # Initialize tab data if needed
            if hasattr(target_picker_widget, 'initialize_tab_data'):
                target_picker_widget.initialize_tab_data(current_tab)
            
            # CRITICAL: Temporarily disable the main window's batch update system to prevent conflicts
            original_batch_active = getattr(target_picker_widget, 'batch_update_active', False)
            target_picker_widget.batch_update_active = True
            
            try:
                # Get current tab data
                tab_data = DM.PickerDataManager.get_tab_data(current_tab)
                
                # Create a map of existing buttons for faster lookups
                button_map = {btn['id']: i for i, btn in enumerate(tab_data['buttons'])}
                
                # Process all modified buttons
                buttons_updated = 0
                for button in modified_buttons:
                    # Create complete button data
                    button_data = {
                        "id": button.unique_id,
                        "label": button.label,
                        "color": button.color,
                        "opacity": button.opacity,
                        "position": (button.scene_position.x(), button.scene_position.y()),
                        "width": getattr(button, 'width', 80),
                        "height": getattr(button, 'height', 30),
                        "radius": getattr(button, 'radius', [3, 3, 3, 3]),
                        "assigned_objects": getattr(button, 'assigned_objects', []),
                        "mode": getattr(button, 'mode', 'select'),
                        "script_data": getattr(button, 'script_data', {'code': '', 'type': 'python'}),
                        "pose_data": getattr(button, 'pose_data', {}),
                        "thumbnail_path": getattr(button, 'thumbnail_path', '')
                    }
                    
                    # Update existing button data or add new one
                    if button.unique_id in button_map:
                        # Update existing button
                        index = button_map[button.unique_id]
                        tab_data['buttons'][index] = button_data
                        buttons_updated += 1
                    else:
                        # Add new button
                        tab_data['buttons'].append(button_data)
                        buttons_updated += 1
                
                # Save the updated tab data once for all buttons with force immediate save
                DM.PickerDataManager.update_tab_data(current_tab, tab_data)
                
                # Force immediate save to ensure data persistence
                DM.PickerDataManager.save_data(DM.PickerDataManager.get_data(), force_immediate=True)
                
                #print(f"Database updated for {buttons_updated} button(s) in tab '{current_tab}'")
                
                # Now emit changed signals for UI consistency (after database is saved)
                for button in modified_buttons:
                    if hasattr(button, 'changed'):
                        try:
                            # Block the signal temporarily to prevent recursive updates
                            button.changed.blockSignals(True)
                            button.changed.emit(button)
                            button.changed.blockSignals(False)
                        except:
                            # If blocking fails, just emit normally
                            button.changed.emit(button)
                            
            finally:
                # Restore original batch update state
                target_picker_widget.batch_update_active = original_batch_active
    
    # Update the canvas if we have access to it and changes were made
    if changes_made and canvas:
        canvas.update()
        
        # Also trigger a button positions update to ensure everything is synchronized
        if hasattr(canvas, 'update_button_positions'):
            canvas.update_button_positions()
        
        # Update the main window if possible
        if hasattr(target_picker_widget, 'update_buttons_for_current_tab'):
            target_picker_widget.update_buttons_for_current_tab()
    
    # Report changes
    if changes_made:
        changes = []
        if text: changes.append(f"text to '{text}'")
        if color: changes.append(f"color to '{color}'")
        if opacity_value is not None: changes.append(f"opacity to {opacity_value}")
        if selectable_value is not None: changes.append(f"selectable to {selectable_value}")
        
        widget_name = getattr(target_picker_widget, 'objectName', lambda: 'Unknown')()
        #print(f"Updated {len(modified_buttons)} button(s) in widget '{widget_name}': {', '.join(changes)}")
        #print("Changes have been saved to the database.")
    else:
        print("No changes were made. Please provide at least one parameter (text, color, opacity, or selectable).")
#---------------------------------------------------------------------------------------------------------------
def tool_tip(tooltip_text=""):
    """
    Sets a custom tooltip for a button in the animation picker.
    
    This function allows setting a custom tooltip for a button.
    When called from a script attached to a button, it will modify that specific button's tooltip.
    
    Can be used in button scripts with the @TF.tool_tip() qualifier syntax:
    @TF.tool_tip("My custom tooltip")
    
    Args:
        tooltip_text (str): The custom tooltip text to display when hovering over the button.
        
    Returns:
        None: This function is meant to be used as a decorator in button scripts.
        
    Example:
        @TF.tool_tip("This button resets the character pose")
        
        # Can be combined with other decorators:
        @TF.tool_tip("Switch to FK mode")
        @TF.button_appearance(text="FK", color="#FF0000")
    """
    # This function is meant to be used as a decorator in button scripts
    # The actual implementation is handled in the PickerButton.execute_script_command method
    pass


def pb(button_ids):
    """
    Access picker button parameters by button ID(s).
    
    Returns a PickerButtonProxy object for single IDs or PickerButtonCollection 
    for multiple IDs that allows easy access to button properties like color, opacity, text, etc.
    
    Args:
        button_ids (str or list): The unique ID(s) of the button(s) to access
        
    Returns:
        PickerButtonProxy: For single button ID - an object with properties matching the button's attributes
        PickerButtonCollection: For multiple button IDs - a collection object that provides list-like access
        None: If no buttons are found
    
    Example:
        # Single button access
        print(pb("button_id").color)     # Prints the button's color
        print(pb("button_id").opacity)   # Prints the button's opacity
        print(pb("button_id").label)     # Prints the button's text/label
        
        # Multiple button access
        buttons = pb(["btn1", "btn2", "btn3"])
        print(buttons.color)             # Prints list of colors for all buttons
        print(buttons[0].color)          # Prints color of first button
        print(len(buttons))              # Prints number of found buttons
        
        # Check if button exists
        button = pb("my_button")
        if button:
            print(f"Button color: {button.color}")
            print(f"Button opacity: {button.opacity}")
        else:
            print("Button not found")
    """
    # Import needed modules
    from . import blender_main as MAIN
    import inspect
    
    class PickerButtonCollection:
        """
        Collection object that provides access to multiple picker buttons.
        Supports both list-like access and collective property access.
        """
        def __init__(self, buttons):
            self._buttons = buttons
            self._proxies = [PickerButtonProxy(btn) for btn in buttons]
            
        def __len__(self):
            """Return the number of buttons in the collection."""
            return len(self._proxies)
            
        def __getitem__(self, index):
            """Get a specific button by index."""
            return self._proxies[index]
            
        def __iter__(self):
            """Iterate over the buttons."""
            return iter(self._proxies)
            
        def __bool__(self):
            """Return True if collection is not empty."""
            return len(self._proxies) > 0
            
        @property
        def color(self):
            """Get list of colors for all buttons."""
            return [proxy.color for proxy in self._proxies]
            
        @property
        def opacity(self):
            """Get list of opacities for all buttons."""
            return [proxy.opacity for proxy in self._proxies]
            
        @property
        def label(self):
            """Get list of labels for all buttons."""
            return [proxy.label for proxy in self._proxies]
            
        @property
        def text(self):
            """Alias for label - get list of text for all buttons."""
            return self.label
            
        @property
        def position(self):
            """Get list of positions for all buttons."""
            return [proxy.position for proxy in self._proxies]
            
        @property
        def width(self):
            """Get list of widths for all buttons."""
            return [proxy.width for proxy in self._proxies]
            
        @property
        def height(self):
            """Get list of heights for all buttons."""
            return [proxy.height for proxy in self._proxies]
            
        @property
        def radius(self):
            """Get list of corner radii for all buttons."""
            return [proxy.radius for proxy in self._proxies]
            
        @property
        def mode(self):
            """Get list of modes for all buttons."""
            return [proxy.mode for proxy in self._proxies]
            
        @property
        def selectable(self):
            """Get list of selectable states for all buttons."""
            return [proxy.selectable for proxy in self._proxies]
            
        @property
        def is_selected(self):
            """Get list of selection states for all buttons."""
            return [proxy.is_selected for proxy in self._proxies]
            
        @property
        def unique_id(self):
            """Get list of unique IDs for all buttons."""
            return [proxy.unique_id for proxy in self._proxies]
            
        @property
        def assigned_objects(self):
            """Get flattened list of all assigned object names from all buttons."""
            all_objects = []
            for proxy in self._proxies:
                all_objects.extend(proxy.assigned_objects)
            return all_objects
            
        @property
        def script_data(self):
            """Get list of script data for all buttons."""
            return [proxy.script_data for proxy in self._proxies]
            
        @property
        def pose_data(self):
            """Get list of pose data for all buttons."""
            return [proxy.pose_data for proxy in self._proxies]
            
        @property
        def thumbnail_path(self):
            """Get list of thumbnail paths for all buttons."""
            return [proxy.thumbnail_path for proxy in self._proxies]
            
        def __str__(self):
            """String representation of the collection."""
            if not self._proxies:
                return "PickerButtonCollection(empty)"
            return f"PickerButtonCollection({len(self._proxies)} buttons)"
            
        def __repr__(self):
            """Detailed representation of the collection."""
            if not self._proxies:
                return "PickerButtonCollection([])"
            ids = [proxy.unique_id for proxy in self._proxies]
            return f"PickerButtonCollection({ids})"

    class PickerButtonProxy:
        """
        Proxy object that provides easy access to picker button properties.
        """
        def __init__(self, button):
            self._button = button
            
        @property
        def color(self):
            """Get the button's color."""
            return getattr(self._button, 'color', None)
            
        @property
        def opacity(self):
            """Get the button's opacity."""
            return getattr(self._button, 'opacity', None)
            
        @property
        def label(self):
            """Get the button's text/label."""
            return getattr(self._button, 'label', None)
            
        @property
        def text(self):
            """Alias for label - get the button's text."""
            return self.label
            
        @property
        def position(self):
            """Get the button's position as (x, y) tuple."""
            if hasattr(self._button, 'scene_position'):
                pos = self._button.scene_position
                return (pos.x(), pos.y())
            return None
            
        @property
        def width(self):
            """Get the button's width."""
            return getattr(self._button, 'width', None)
            
        @property
        def height(self):
            """Get the button's height."""
            return getattr(self._button, 'height', None)
            
        @property
        def radius(self):
            """Get the button's corner radius."""
            return getattr(self._button, 'radius', None)
            
        @property
        def mode(self):
            """Get the button's mode (e.g., 'select', 'pose', 'script')."""
            return getattr(self._button, 'mode', None)
            
        @property
        def selectable(self):
            """Get whether the button is selectable."""
            return getattr(self._button, 'selectable', True)
            
        @property
        def is_selected(self):
            """Get whether the button is currently selected."""
            return getattr(self._button, 'is_selected', False)
            
        @property
        def unique_id(self):
            """Get the button's unique ID."""
            return getattr(self._button, 'unique_id', None)
            
        @property
        def assigned_objects(self):
            """Get the list of object names assigned to this button."""
            raw_objects = getattr(self._button, 'assigned_objects', [])
            # Extract just the names from the objects
            object_names = []
            for obj in raw_objects:
                if hasattr(obj, 'name'):
                    # Blender object with .name attribute
                    object_names.append(obj.name)
                elif isinstance(obj, str):
                    # Already a string (object name)
                    object_names.append(obj)
                elif isinstance(obj, dict) and 'name' in obj:
                    # Dictionary with name key
                    object_names.append(obj['name'])
                else:
                    # Fallback - convert to string
                    object_names.append(str(obj))
            return object_names
            
        @property
        def script_data(self):
            """Get the button's script data."""
            return getattr(self._button, 'script_data', {})
            
        @property
        def pose_data(self):
            """Get the button's pose data."""
            return getattr(self._button, 'pose_data', {})
            
        @property
        def thumbnail_path(self):
            """Get the button's thumbnail path."""
            return getattr(self._button, 'thumbnail_path', '')
            
        def __str__(self):
            """String representation of the button."""
            return f"PickerButton(id='{self.unique_id}', label='{self.label}', color='{self.color}')"
            
        def __repr__(self):
            """Detailed representation of the button."""
            return (f"PickerButton(id='{self.unique_id}', label='{self.label}', "
                   f"color='{self.color}', opacity={self.opacity}, mode='{self.mode}')")
    
    # Convert single string to list for uniform processing
    if isinstance(button_ids, str):
        button_ids = [button_ids]
        single_button = True
    else:
        single_button = False
    
    # Get the correct picker window instance
    target_picker_widget = None
    
    # Try to find the picker widget from the current context
    # First, check if we're being called from a script and can find the source button
    script_source_button = None
    for frame_info in inspect.stack():
        if frame_info.function == 'execute_script_command':
            if hasattr(frame_info, 'frame') and 'self' in frame_info.frame.f_locals:
                potential_button = frame_info.frame.f_locals['self']
                if hasattr(potential_button, 'mode') and hasattr(potential_button, 'script_data'):
                    script_source_button = potential_button
                    break
    
    if script_source_button:
        # Find the picker widget that contains this button
        current_widget = script_source_button
        while current_widget:
            if current_widget.__class__.__name__ == 'BlenderAnimPickerWindow':
                target_picker_widget = current_widget
                break
            current_widget = current_widget.parent()
    
    # If we couldn't find the specific window, fall back to manager approach
    if not target_picker_widget:
        manager = MAIN.PickerWindowManager.get_instance()
        if not manager or not manager._picker_widgets:
            print("No picker widgets found.")
            return None
        # Use the first available picker widget as fallback
        target_picker_widget = manager._picker_widgets[0]
    
    # Get all buttons from the correct picker widget instance
    all_buttons = []
    
    # Try different ways to access the canvas from the target picker widget
    canvas = None
    
    # Method 1: Direct canvas attribute
    if hasattr(target_picker_widget, 'canvas'):
        canvas = target_picker_widget.canvas
    
    # Method 2: Look for canvas in tab system
    elif hasattr(target_picker_widget, 'tab_system'):
        if target_picker_widget.tab_system.current_tab:
            current_tab = target_picker_widget.tab_system.current_tab
            if current_tab in target_picker_widget.tab_system.tabs:
                canvas = target_picker_widget.tab_system.tabs[current_tab]['canvas']
    
    # Method 3: Search for canvas in children of the target widget only
    if not canvas:
        for child in target_picker_widget.findChildren(QtWidgets.QWidget):
            if hasattr(child, 'buttons') and isinstance(child.buttons, list):
                canvas = child
                break
    
    # If we found a canvas, get its buttons
    if canvas and hasattr(canvas, 'buttons'):
        all_buttons.extend(canvas.buttons)
    
    # If we still don't have any buttons from the target widget, search more thoroughly
    if not all_buttons:
        for child in target_picker_widget.findChildren(QtWidgets.QWidget):
            if hasattr(child, 'mode') and hasattr(child, 'label') and hasattr(child, 'unique_id'):
                all_buttons.append(child)
    
    # Find buttons with matching IDs
    found_buttons = []
    for button_id in button_ids:
        for button in all_buttons:
            if hasattr(button, 'unique_id') and button.unique_id == button_id:
                found_buttons.append(button)
                break
    
    # Handle results based on input type
    if single_button:
        # Original single button behavior
        if found_buttons:
            return PickerButtonProxy(found_buttons[0])
        else:
            print(f"Button with ID '{button_ids[0]}' not found.")
            return None
    else:
        # Multiple buttons - return collection
        if found_buttons:
            return PickerButtonCollection(found_buttons)
        else:
            print(f"No buttons found for IDs: {button_ids}")
            return None

def list_buttons():
    """
    List all available buttons with their IDs and basic info.
    
    Returns:
        list: List of dictionaries containing button information
    """
    from . import blender_main as MAIN
    import inspect
    
    # Get picker widget (reusing logic from pb function)
    target_picker_widget = None
    script_source_button = None
    
    for frame_info in inspect.stack():
        if frame_info.function == 'execute_script_command':
            if hasattr(frame_info, 'frame') and 'self' in frame_info.frame.f_locals:
                potential_button = frame_info.frame.f_locals['self']
                if hasattr(potential_button, 'mode') and hasattr(potential_button, 'script_data'):
                    script_source_button = potential_button
                    break
    
    if script_source_button:
        current_widget = script_source_button
        while current_widget:
            if current_widget.__class__.__name__ == 'BlenderAnimPickerWindow':
                target_picker_widget = current_widget
                break
            current_widget = current_widget.parent()
    
    if not target_picker_widget:
        manager = MAIN.PickerWindowManager.get_instance()
        if not manager or not manager._picker_widgets:
            return []
        target_picker_widget = manager._picker_widgets[0]
    
    # Get all buttons
    all_buttons = []
    canvas = None
    
    if hasattr(target_picker_widget, 'canvas'):
        canvas = target_picker_widget.canvas
    elif hasattr(target_picker_widget, 'tab_system'):
        if target_picker_widget.tab_system.current_tab:
            current_tab = target_picker_widget.tab_system.current_tab
            if current_tab in target_picker_widget.tab_system.tabs:
                canvas = target_picker_widget.tab_system.tabs[current_tab]['canvas']
    
    if not canvas:
        for child in target_picker_widget.findChildren(QtWidgets.QWidget):
            if hasattr(child, 'buttons') and isinstance(child.buttons, list):
                canvas = child
                break
    
    if canvas and hasattr(canvas, 'buttons'):
        all_buttons.extend(canvas.buttons)
    
    if not all_buttons:
        for child in target_picker_widget.findChildren(QtWidgets.QWidget):
            if hasattr(child, 'mode') and hasattr(child, 'label') and hasattr(child, 'unique_id'):
                all_buttons.append(child)
    
    # Return button info
    button_info = []
    for button in all_buttons:
        if hasattr(button, 'unique_id'):
            info = {
                'id': getattr(button, 'unique_id', 'Unknown'),
                'label': getattr(button, 'label', ''),
                'color': getattr(button, 'color', ''),
                'opacity': getattr(button, 'opacity', 1.0),
                'mode': getattr(button, 'mode', 'select')
            }
            button_info.append(info)
    
    return button_info

def print_buttons():
    """
    Print all available buttons in a formatted way.
    """
    buttons = list_buttons()
    if not buttons:
        print("No buttons found.")
        return
    
    print(f"Found {len(buttons)} button(s):")
    print("-" * 60)
    for button in buttons:
        print(f"ID: {button['id']:<20} | Label: {button['label']:<15} | Color: {button['color']:<8} | Opacity: {button['opacity']:<4} | Mode: {button['mode']}")
