import maya.cmds as cmds
import maya.mel as mel
import maya.api.OpenMaya as om
from maya import OpenMayaUI as omui
from functools import wraps
import re
import json

try:
    from PySide6 import QtWidgets, QtCore, QtGui
    from PySide6.QtGui import QColor
    from PySide6.QtCore import QTimer, QPropertyAnimation, QEasingCurve
    from shiboken6 import wrapInstance
except ImportError:
    from PySide2 import QtWidgets, QtCore, QtGui
    from PySide2.QtGui import QColor
    from PySide2.QtCore import QTimer, QPropertyAnimation, QEasingCurve
    from shiboken2 import wrapInstance

from . utils import undoable
from . import custom_button as CB
from . import custom_slider as CS
from . import custom_dialog as CD
from . import ui as UI
from . import main as MAIN

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
        #reset_move_button = CB.CustomButton(text='Move', icon=':delete.png', color='#262626', size=14, tooltip="Resets the moved object values to Origin.",text_size=ts, height=bh)
        #reset_rotate_button = CB.CustomButton(text='Rotate', icon=':delete.png', color='#262626', size=14, tooltip="Resets the rotated object values to Origin.",text_size=ts, height=bh)
        #reset_scale_button = CB.CustomButton(text='Scale', icon=':delete.png', color='#262626', size=14, tooltip="Resets the scaled object values to Origin.",text_size=ts, height=bh)
        reset_transform_button = CB.CustomButton(text='Reset', icon=':delete.png', color='#222222', size=14, tooltip="Resets the object transform to Origin.",
                                                 text_size=ts, height=bh,ContextMenu=True, onlyContext=False)
        reset_transform_button.addToMenu("Move", reset_move, icon='delete.png', position=(0,0))
        reset_transform_button.addToMenu("Rotate", reset_rotate, icon='delete.png', position=(1,0))
        reset_transform_button.addToMenu("Scale", reset_scale, icon='delete.png', position=(2,0))

        reset_all_button = CB.CustomButton(text='Reset All', icon=':delete.png', size=14, color='#222222', tooltip="Resets all the object transform to Origin.",text_size=ts, height=bh)

        timeLine_key_button = CB.CustomButton(text='Key', color='#d62e22', tooltip="Sets key frame.",text_size=ts, height=bh)
        timeLine_delete_key_button = CB.CustomButton(text='Key', icon=':delete.png', color='#222222', size=14, tooltip="Deletes keys from the given start frame to the current frame.",text_size=ts, height=bh)
        timeLine_copy_key_button = CB.CustomButton(text='Copy', color='#293F64', tooltip="Copy selected key(s).",text_size=ts, height=bh)
        timeLine_paste_key_button = CB.CustomButton(text='Paste', color='#1699CA', tooltip="Paste copied key(s).",text_size=ts, height=bh)
        timeLine_pasteInverse_key_button = CB.CustomButton(text='Paste Inverse', color='#9416CA', tooltip="Paste Inverted copied keys(s).",text_size=ts, height=bh)
        
        mirror_pose_button = CB.CustomButton(text='Mirror Pose', color='#8A2BE2', tooltip="Mirror Pose: Apply the pose of selected objects to their mirrored counterparts.",
                                           text_size=ts, height=bh, ContextMenu=True, onlyContext=False)
        mirror_pose_button.addToMenu("Custom Naming", self.show_mirror_pose_dialog, icon='ghostingObjectTypeLocator.png', position=(0,0))

        match_transforms_button = CB.CustomButton(text='Match', icon=':ghostingObjectTypeLocator.png', color='#262626', size=14, tooltip="Match Transforms.",
                                                  text_size=ts, height=bh,ContextMenu=True, onlyContext=True)
        match_transforms_button.addToMenu("Move", match_move, icon='ghostingObjectTypeLocator.png', position=(0,0))
        match_transforms_button.addToMenu("Rotate", match_rotate, icon='ghostingObjectTypeLocator.png', position=(1,0))
        match_transforms_button.addToMenu("Scale", match_scale, icon='ghostingObjectTypeLocator.png', position=(2,0))
        match_transforms_button.addToMenu("All", match_all, icon='ghostingObjectTypeLocator.png', position=(3,0))

        store_pos_button = CB.CustomButton(text='Store Pos', color='#16AAA6', tooltip="Store Position: Stores the position of selected Vertices, Edges or Faces. Double Click to make locator visible",
                                           text_size=ts, height=bh)
        move_to_pos_button = CB.CustomButton(text='Move to Pos', color='#D58C09', tooltip="Move to Position: Move selected object(s) to the stored position.",
                                             text_size=ts, height=bh)
        #---------------------------------------------------------------------------------------------------------------------------------------------------------------------------
        #reset_move_button.singleClicked.connect(reset_move)
        #reset_rotate_button.singleClicked.connect(reset_rotate)
        #reset_scale_button.singleClicked.connect(reset_scale)
        reset_transform_button.singleClicked.connect(reset_all)
        reset_all_button.singleClicked.connect(reset_all)

        timeLine_key_button.singleClicked.connect(set_key)
        timeLine_delete_key_button.singleClicked.connect(delete_keys)
        timeLine_copy_key_button.singleClicked.connect(copy_pose)
        timeLine_paste_key_button.singleClicked.connect(paste_pose)
        timeLine_pasteInverse_key_button.singleClicked.connect(paste_inverse_pose)

        mirror_pose_button.singleClicked.connect(apply_mirror_pose)
        store_pos_button.singleClicked.connect(store_component_position)
        move_to_pos_button.singleClicked.connect(move_objects_to_stored_position)
        #---------------------------------------------------------------------------------------------------------------------------------------------------------------------------
        #self.col1.addWidget(reset_move_button)
        #self.col1.addWidget(reset_rotate_button)
        #self.col1.addWidget(reset_scale_button)
        self.col1.addWidget(reset_transform_button)
        #self.col1.addWidget(reset_all_button)

        self.col1.addSpacing(4)

        self.col1.addWidget(timeLine_key_button)
        self.col1.addWidget(timeLine_delete_key_button)
        self.col1.addWidget(timeLine_copy_key_button)
        self.col1.addWidget(timeLine_paste_key_button)
        self.col1.addWidget(timeLine_pasteInverse_key_button)
        self.col1.addWidget(mirror_pose_button)

        self.col1.addSpacing(4)
        self.col1.addWidget(match_transforms_button)
        self.col1.addWidget(store_pos_button)
        self.col1.addWidget(move_to_pos_button)
        #---------------------------------------------------------------------------------------------------------------------------------------------------------------------------
        self.tools_scroll_frame_layout.addLayout(self.col1)
        self.tools_scroll_frame_layout.addSpacing(2)
        self.tools_scroll_frame_layout.addLayout(self.col2)
        self.layout.addWidget(self.tools_scroll_area)
        #---------------------------------------------------------------------------------------------------------------------------------------------------------------------------

@undoable
def reset_move():
    # Get the list of selected objects
    sel_objs = cmds.ls(sl=True)

    # Loop through each selected object
    for obj in sel_objs:
        attrs = ['tx', 'ty', 'tz']
        
        for attr in attrs:
            attr_path = f"{obj}.{attr}"
            
            # Check if attribute is locked
            is_locked = cmds.getAttr(attr_path, lock=True)
            
            # Check if attribute has non-keyed connections
            has_non_keyed_connection = False
            if cmds.connectionInfo(attr_path, isDestination=True):
                # Get the source of the connection
                source = cmds.connectionInfo(attr_path, sourceFromDestination=True)
                
                # Check if the connection is from an animation curve (keyed)
                is_keyed = source and "animCurve" in cmds.nodeType(source.split('.')[0])
                
                # If there's a connection and it's not from an animation curve
                has_non_keyed_connection = not is_keyed
            
            # Reset the attribute if it's not locked and has no non-keyed connections
            if not is_locked and not has_non_keyed_connection:
                cmds.setAttr(attr_path, 0)

@undoable
def reset_rotate():
    # Get the list of selected objects
    sel_objs = cmds.ls(sl=True)

    # Loop through each selected object
    for obj in sel_objs:
        attrs = ['rx', 'ry', 'rz']
        
        for attr in attrs:
            attr_path = f"{obj}.{attr}"
            
            # Check if attribute is locked
            is_locked = cmds.getAttr(attr_path, lock=True)
            
            # Check if attribute has non-keyed connections
            has_non_keyed_connection = False
            if cmds.connectionInfo(attr_path, isDestination=True):
                # Get the source of the connection
                source = cmds.connectionInfo(attr_path, sourceFromDestination=True)
                
                # Check if the connection is from an animation curve (keyed)
                is_keyed = source and "animCurve" in cmds.nodeType(source.split('.')[0])
                
                # If there's a connection and it's not from an animation curve
                has_non_keyed_connection = not is_keyed
            
            # Reset the attribute if it's not locked and has no non-keyed connections
            if not is_locked and not has_non_keyed_connection:
                cmds.setAttr(attr_path, 0)

@undoable
def reset_scale():
    # Get the list of selected objects
    sel_objs = cmds.ls(sl=True)

    # Loop through each selected object
    for obj in sel_objs:
        attrs = ['sx', 'sy', 'sz']
        
        for attr in attrs:
            attr_path = f"{obj}.{attr}"
            
            # Check if attribute is locked
            is_locked = cmds.getAttr(attr_path, lock=True)
            
            # Check if attribute has non-keyed connections
            has_non_keyed_connection = False
            if cmds.connectionInfo(attr_path, isDestination=True):
                # Get the source of the connection
                source = cmds.connectionInfo(attr_path, sourceFromDestination=True)
                
                # Check if the connection is from an animation curve (keyed)
                is_keyed = source and "animCurve" in cmds.nodeType(source.split('.')[0])
                
                # If there's a connection and it's not from an animation curve
                has_non_keyed_connection = not is_keyed
            
            # Reset the attribute if it's not locked and has no non-keyed connections
            if not is_locked and not has_non_keyed_connection:
                # Scale attributes need to be set to 1 instead of 0
                cmds.setAttr(attr_path, 1)

@undoable
def reset_all():
    # Get the list of selected objects
    sel_objs = cmds.ls(sl=True)

    # Loop through each selected object
    for obj in sel_objs:
        # Define the attributes to check
        attrs = ['tx', 'ty', 'tz', 'rx', 'ry', 'rz', 'sx', 'sy', 'sz']
        default_values = {'tx': 0, 'ty': 0, 'tz': 0, 'rx': 0, 'ry': 0, 'rz': 0, 'sx': 1, 'sy': 1, 'sz': 1}
        
        for attr in attrs:
            attr_path = f"{obj}.{attr}"
            
            # Check if attribute is locked
            is_locked = cmds.getAttr(attr_path, lock=True)
            
            # Check if attribute has non-keyed connections
            has_non_keyed_connection = False
            if cmds.connectionInfo(attr_path, isDestination=True):
                # Get the source of the connection
                source = cmds.connectionInfo(attr_path, sourceFromDestination=True)
                
                # Check if the connection is from an animation curve (keyed)
                is_keyed = source and "animCurve" in cmds.nodeType(source.split('.')[0])
                
                # If there's a connection and it's not from an animation curve
                has_non_keyed_connection = not is_keyed
            
            # Reset the attribute if it's not locked and has no non-keyed connections
            if not is_locked and not has_non_keyed_connection:
                cmds.setAttr(attr_path, default_values[attr])
     
#---------------------------------------------------------------------------------------------------------------
def set_key():
    mel.eval("setKeyframe -breakdown 0 -preserveCurveShape 1 -hierarchy none -controlPoints 0 -shape 0;")

def delete_keys():
    mel.eval('''timeSliderClearKey;''')

def copy_keys():
    mel.eval("timeSliderCopyKey;")
    
def paste_keys():
    mel.eval("timeSliderPasteKey false;")

@undoable
def paste_inverse():
    mel.eval("timeSliderPasteKey false;")
    try:
        # Get the list of selected objects
        sel_objs = cmds.ls(sl=True)

        # Loop through each selected object
        for obj in sel_objs:
            # Get the current translate, rotate, and scale values
            tx = cmds.getAttr(f"{obj}.tx")
            ty = cmds.getAttr(f"{obj}.ty")
            tz = cmds.getAttr(f"{obj}.tz")
            rx = cmds.getAttr(f"{obj}.rx")
            ry = cmds.getAttr(f"{obj}.ry")
            rz = cmds.getAttr(f"{obj}.rz")
            sx = cmds.getAttr(f"{obj}.sx")
            sy = cmds.getAttr(f"{obj}.sy")
            sz = cmds.getAttr(f"{obj}.sz")

            # Check if the attributes are locked
            tx_locked = cmds.getAttr(f"{obj}.tx", lock=True)
            ty_locked = cmds.getAttr(f"{obj}.ty", lock=True)
            tz_locked = cmds.getAttr(f"{obj}.tz", lock=True)
            rx_locked = cmds.getAttr(f"{obj}.rx", lock=True)
            ry_locked = cmds.getAttr(f"{obj}.ry", lock=True)
            rz_locked = cmds.getAttr(f"{obj}.rz", lock=True)
            sx_locked = cmds.getAttr(f"{obj}.sx", lock=True)
            sy_locked = cmds.getAttr(f"{obj}.sy", lock=True)
            sz_locked = cmds.getAttr(f"{obj}.sz", lock=True)

            # Reset the translate values if the attribute is not locked
            if not tx_locked:
                cmds.setAttr(f"{obj}.tx", tx * -1)

            '''if not ty_locked:
                cmds.setAttr(f"{obj}.ty", ty * -1)
            if not tz_locked:
                cmds.setAttr(f"{obj}.tz", tz * -1)'''

            # Reset the rotate values if the attribute is not locked
            if not rx_locked:
                cmds.setAttr(f"{obj}.rx", rx)
            if not ry_locked:
                cmds.setAttr(f"{obj}.ry", ry * -1)
            if not rz_locked:
                cmds.setAttr(f"{obj}.rz", rz * -1)
            
            '''# Reset the scale values if the attribute is not locked
            if not sx_locked:
                cmds.setAttr(f"{obj}.sx", 1)
            if not sy_locked:
                cmds.setAttr(f"{obj}.sy", 1)
            if not sz_locked:
                cmds.setAttr(f"{obj}.sz", 1)'''
    finally:
        cmds.undoInfo(closeChunk=True)    
#---------------------------------------------------------------------------------------------------------------
#---------------------------------------------------------------------------------------------------------------

# Global variable to store copied pose data
_copied_pose_data = {}

@undoable
def copy_pose():
    """Copy the current pose of selected objects."""
    global _copied_pose_data
    _copied_pose_data = {}
    
    # Get selected objects
    selected_objects = cmds.ls(selection=True)
    if not selected_objects:
        cmds.warning("No objects selected for copying pose.")
        return
    
    # For each selected object, store its keyable attributes
    for obj in selected_objects:
        keyable_attrs = cmds.listAttr(obj, keyable=True) or []
        attr_values = {}
        
        for attr in keyable_attrs:
            try:
                full_attr = f"{obj}.{attr}"
                if cmds.objExists(full_attr) and not cmds.getAttr(full_attr, lock=True):
                    attr_values[attr] = cmds.getAttr(full_attr)
            except Exception as e:
                print(f"Error getting attribute {attr} from {obj}: {e}")
        
        if attr_values:
            _copied_pose_data[obj] = attr_values
    
    print(f"Copied pose from {len(_copied_pose_data)} objects.")

@undoable
def paste_pose():
    """Paste the previously copied pose to selected objects."""
    global _copied_pose_data
    
    if not _copied_pose_data:
        cmds.warning("No pose data available. Copy a pose first.")
        return
    
    # Get selected objects
    selected_objects = cmds.ls(selection=True)
    if not selected_objects:
        print("No objects selected for pasting pose.")
        return
    
    # Apply pose based on selection order
    source_objects = list(_copied_pose_data.keys())
    for i, target_obj in enumerate(selected_objects):
        if i >= len(source_objects):
            break
            
        source_obj = source_objects[i]
        attr_values = _copied_pose_data[source_obj]
        
        for attr, value in attr_values.items():
            try:
                full_attr = f"{target_obj}.{attr}"
                if cmds.objExists(full_attr) and not cmds.getAttr(full_attr, lock=True):
                    cmds.setAttr(full_attr, value)
            except Exception as e:
                print(f"Error setting attribute {attr} on {target_obj}: {e}")
    
    print(f"Pasted pose to {min(len(selected_objects), len(source_objects))} objects.")

@undoable
def paste_inverse_pose():
    """Paste the inverse of the previously copied pose to selected objects."""
    global _copied_pose_data
    
    if not _copied_pose_data:
        cmds.warning("No pose data available. Copy a pose first.")
        return
    
    # Get selected objects
    selected_objects = cmds.ls(selection=True)
    if not selected_objects:
        cmds.warning("No objects selected for pasting inverse pose.")
        return
    
    # Apply inverse pose based on selection order
    source_objects = list(_copied_pose_data.keys())
    for i, target_obj in enumerate(selected_objects):
        if i >= len(source_objects):
            break
            
        source_obj = source_objects[i]
        attr_values = _copied_pose_data[source_obj]
        
        for attr, value in attr_values.items():
            try:
                full_attr = f"{target_obj}.{attr}"
                if cmds.objExists(full_attr) and not cmds.getAttr(full_attr, lock=True):
                    # Invert translate and rotate values for x-axis
                    if attr == 'translateX' or attr == 'rotateY' or attr == 'rotateZ':
                        cmds.setAttr(full_attr, -value)
                    else:
                        cmds.setAttr(full_attr, value)
            except Exception as e:
                print(f"Error setting attribute {attr} on {target_obj}: {e}")
    
    print(f"Pasted inverse pose to {min(len(selected_objects), len(source_objects))} objects.")

@undoable
def paste_inverse():
    mel.eval("timeSliderPasteKey false;")
    try:
        # Get the list of selected objects
        sel_objs = cmds.ls(sl=True)

        # Loop through each selected object
        for obj in sel_objs:
            # Get the current translate, rotate, and scale values
            tx = cmds.getAttr(f"{obj}.tx")
            ty = cmds.getAttr(f"{obj}.ty")
            tz = cmds.getAttr(f"{obj}.tz")
            rx = cmds.getAttr(f"{obj}.rx")
            ry = cmds.getAttr(f"{obj}.ry")
            rz = cmds.getAttr(f"{obj}.rz")
            sx = cmds.getAttr(f"{obj}.sx")
            sy = cmds.getAttr(f"{obj}.sy")
            sz = cmds.getAttr(f"{obj}.sz")

            # Check if the attributes are locked
            tx_locked = cmds.getAttr(f"{obj}.tx", lock=True)
            ty_locked = cmds.getAttr(f"{obj}.ty", lock=True)
            tz_locked = cmds.getAttr(f"{obj}.tz", lock=True)
            rx_locked = cmds.getAttr(f"{obj}.rx", lock=True)
            ry_locked = cmds.getAttr(f"{obj}.ry", lock=True)
            rz_locked = cmds.getAttr(f"{obj}.rz", lock=True)
            sx_locked = cmds.getAttr(f"{obj}.sx", lock=True)
            sy_locked = cmds.getAttr(f"{obj}.sy", lock=True)
            sz_locked = cmds.getAttr(f"{obj}.sz", lock=True)

            # Reset the translate values if the attribute is not locked
            if not tx_locked:
                cmds.setAttr(f"{obj}.tx", tx * -1)

            '''if not ty_locked:
                cmds.setAttr(f"{obj}.ty", ty * -1)
            if not tz_locked:
                cmds.setAttr(f"{obj}.tz", tz * -1)'''

            # Reset the rotate values if the attribute is not locked
            if not rx_locked:
                cmds.setAttr(f"{obj}.rx", rx)
            if not ry_locked:
                cmds.setAttr(f"{obj}.ry", ry * -1)
            if not rz_locked:
                cmds.setAttr(f"{obj}.rz", rz * -1)
            
            '''# Reset the scale values if the attribute is not locked
            if not sx_locked:
                cmds.setAttr(f"{obj}.sx", 1)
            if not sy_locked:
                cmds.setAttr(f"{obj}.sy", 1)
            if not sz_locked:
                cmds.setAttr(f"{obj}.sz", 1)'''
    finally:
        cmds.undoInfo(closeChunk=True)    
#---------------------------------------------------------------------------------------------------------------
#---------------------------------------------------------------------------------------------------------------
@undoable
def match_ik_to_fk(ik_controls, fk_joints):
    """
    Matches IK controls to FK joint positions and calculates the pole vector position.
    
    Args:
        ik_controls (list): List of IK controls where ik_controls[1] is the pole vector and ik_controls[2] is the end control
        fk_joints (list): List of FK joints
        pole_distance (float): Distance multiplier for pole vector positioning (default: 0.25)
    """
    # Match end IK control to end FK joint
    cmds.matchTransform(ik_controls[1], fk_joints[2], pos=True, rot=False)
    
    # Calculate pole vector position
    # Get world space positions of the joints
    start_pos = cmds.xform(fk_joints[2], query=True, worldSpace=True, translation=True)
    mid_pos = cmds.xform(fk_joints[1], query=True, worldSpace=True, translation=True)
    end_pos = cmds.xform(fk_joints[0], query=True, worldSpace=True, translation=True)

    # Convert to MVector for calculations
    start_vec = om.MVector(start_pos)
    mid_vec = om.MVector(mid_pos)
    end_vec = om.MVector(end_pos)

    # Calculate the pole vector position
    start_to_end = end_vec - start_vec
    start_to_mid = mid_vec - start_vec

    # Calculate the projection manually
    start_to_end_normalized = start_to_end.normal()
    projection_length = start_to_mid * start_to_end_normalized
    projection = start_to_end_normalized * projection_length

    # Calculate the pole vector direction
    pole_vec = (mid_vec - (start_vec + projection)).normal()

    # Calculate the final pole vector position
    pole_distance=.25
    chain_length = (mid_vec - start_vec).length() + (end_vec - mid_vec).length()
    pole_pos = mid_vec + (pole_vec * chain_length * pole_distance)

    # Create a temporary locator for positioning
    temp_locator = cmds.spaceLocator(name="temp_pole_locator")[0]
    cmds.xform(temp_locator, worldSpace=True, translation=pole_pos)

    # Match the pole vector control to the locator
    cmds.matchTransform(ik_controls[0], temp_locator, position=True)

    # Clean up
    cmds.delete(temp_locator)

    print(f"IK controls and pole vector have been matched to FK chain.")

@undoable
def match_fk_to_ik(fk_controls, ik_joints):
    '''
    Matches the FK controls to the corresponding IK joints.
    '''
    for fk_ctrl, ik_jnt in zip(fk_controls, ik_joints):
        cmds.matchTransform(fk_ctrl, ik_jnt, pos=False, rot=True)
    print("FK controls matched to IK joints.")
#---------------------------------------------------------------------------------------------------------------
@undoable
def store_component_position():
    # Get the active selection
    selection = cmds.ls(sl=True)
    
    # Get the defaultObjectSet
    default_set = 'defaultObjectSet'
    
    # Initialize the stored position
    stored_position = [0, 0, 0]  # Default to world origin
    
    # Check if there's an active selection
    if selection:
        # Get the manipulator position
        manipulator_pos = None
        current_ctx = cmds.currentCtx()
        if current_ctx == 'moveSuperContext':
            manipulator_pos = cmds.manipMoveContext('Move', q=True, position=True)
        elif current_ctx == 'RotateSuperContext':
            manipulator_pos = cmds.manipRotateContext('Rotate', q=True, position=True)
        elif current_ctx == 'scaleSuperContext':
            manipulator_pos = cmds.manipScaleContext('Scale', q=True, position=True)

        if manipulator_pos:
            stored_position = manipulator_pos
        else:
            cmds.warning("Unable to get manipulator position. Using world origin.")
    else:
        cmds.warning("Nothing selected. Using world origin.")

    # Check if the 'Stored Location' attribute exists, if not, create it
    if not cmds.attributeQuery('Stored_Location', node=default_set, exists=True):
        cmds.addAttr(default_set, longName='Stored_Location', attributeType='double3')
        cmds.addAttr(default_set, longName='Stored_Location_X', attributeType='double', parent='Stored_Location')
        cmds.addAttr(default_set, longName='Stored_Location_Y', attributeType='double', parent='Stored_Location')
        cmds.addAttr(default_set, longName='Stored_Location_Z', attributeType='double', parent='Stored_Location')

    # Store the position in the custom attribute
    cmds.setAttr(f'{default_set}.Stored_Location', *stored_position)

    print(f"Position stored in {default_set}.Stored_Location:", stored_position)

@undoable
def move_objects_to_stored_position():
    selected_objects = cmds.ls(selection=True, long=True)
    default_set = 'defaultObjectSet'
    
    # Check if the stored position attribute exists
    if not cmds.attributeQuery('Stored_Location', node=default_set, exists=True):
        cmds.warning("No stored position found. Please store a position first.")
        return

    # Get the stored position
    stored_position = cmds.getAttr(f'{default_set}.Stored_Location')[0]

    # Check if there are any objects selected
    if not selected_objects:
        cmds.warning("Please select at least one object to move.")
        return

    # Loop through the selected objects and move them to the stored position
    for obj in selected_objects:
        # Get the current world space rotate pivot of the object
        current_position = cmds.xform(obj, query=True, worldSpace=True, rotatePivot=True)
        
        # Calculate the difference between the stored position and current position
        offset = [stored_position[i] - current_position[i] for i in range(3)]
        
        # Move the object by the calculated offset
        cmds.move(offset[0], offset[1], offset[2], obj, relative=True, worldSpace=True)
    
    cmds.select(selected_objects)
    print(f"Moved {len(selected_objects)} object(s) to stored position: {stored_position}")
#---------------------------------------------------------------------------------------------------------------
def match_move():
    mel.eval('''MatchTranslation;''')

def match_rotate():
    mel.eval('''MatchRotation;''')

def match_scale():
    mel.eval('''MatchScaling;''')

def match_all():
    mel.eval('''MatchTransform;''')

#---------------------------------------------------------------------------------------------------------------
@undoable
def apply_mirror_pose(L="", R="", custom_flip_controls=None, auto_detect_orientation=True):
    """
    Applies the pose of selected objects to their mirrored counterparts.
    
    This function takes selected objects and applies their current pose to the opposing limb.
    For example, if L_arm is selected, it will apply its pose to R_arm.
    
    The function detects common naming conventions for left and right sides:
    - L_/R_
    - left_/right_
    - _L/_R
    - _left/_right
    
    Args:
        L (str, optional): Custom left side identifier. Default is "".
        R (str, optional): Custom right side identifier. Default is "".
        custom_flip_controls (dict, optional): Dictionary of controls that need custom flipping logic.
            Format: {"control_name": {"attrs": ["attr1", "attr2"], "flip": True/False}}
            If flip is True, the standard mirroring logic is applied.
            If flip is False, the value is copied directly without mirroring.
        auto_detect_orientation (bool, optional): If True, automatically determines which attributes
            need to be flipped based on the control's world orientation. Default is True.
    
    Example:
        apply_mirror_pose()  # Uses default naming conventions with auto-orientation detection
        apply_mirror_pose(L="LFT", R="RGT")  # Uses custom naming convention
        apply_mirror_pose(auto_detect_orientation=False, custom_flip_controls={"shoulder_ctrl": {"attrs": ["rotateX"], "flip": False}})
    """
    import maya.cmds as cmds
    
    # Get selected objects
    selected_objects = cmds.ls(selection=True, long=True)
    if not selected_objects:
        _show_dialog("No Selection", "Please select objects in Maya before applying mirror pose.")
        return
    
    # Initialize data structures
    naming_conventions = _get_naming_conventions(L, R)
    custom_flip_controls = custom_flip_controls or {}
    mirror_data = {}
    
    # Auto-detect orientation if enabled
    if auto_detect_orientation:
        orientation_data = _collect_orientation_data(selected_objects, cmds)
        custom_flip_controls = _analyze_orientations(selected_objects, orientation_data, naming_conventions, custom_flip_controls, cmds)
    
    # Process each selected object to collect mirror data
    mirror_data = _collect_mirror_data(selected_objects, naming_conventions, custom_flip_controls, cmds)
    
    # Apply the collected mirror data
    mirrored_objects = _apply_mirror_data(mirror_data, cmds)
    
    # Select the mirrored objects and show feedback
    if mirrored_objects:
        cmds.select(mirrored_objects, replace=True)
        #_show_dialog("Mirror Pose Applied", f"Successfully mirrored pose to {len(mirrored_objects)} object(s).")
    else:
        _show_dialog("Mirror Pose Failed", "Could not find any matching objects to mirror the pose to. "
                                      "Please check that your objects follow standard naming conventions "
                                      "(L_/R_, _L/_R, left_/right_, _left/_right) or provide custom prefixes.")

def _show_dialog(title, message, size=(300, 100)):
    """
    Shows a dialog with the given title and message.
    
    Args:
        title (str): The dialog title
        message (str): The message to display
        size (tuple, optional): Dialog size as (width, height). Default is (300, 100).
    """
    manager = MAIN.PickerWindowManager.get_instance()
    parent = manager._picker_widgets[0] if manager._picker_widgets else None
    dialog = CD.CustomDialog(parent=parent, title=title, size=size, info_box=True)
    message_label = QtWidgets.QLabel(message)
    message_label.setWordWrap(True)
    dialog.add_widget(message_label)
    dialog.add_button_box()
    dialog.exec_()

def _get_naming_conventions(L, R):
    """
    Returns a list of naming conventions for left and right sides.
    
    Args:
        L (str): Custom left side identifier
        R (str): Custom right side identifier
        
    Returns:
        list: List of dictionaries with left and right patterns
    """
    naming_conventions = [
        # Prefix
        {"left": "L_", "right": "R_"},
        {"left": "left_", "right": "right_"},
        {"left": "Lf_", "right": "Rt_"},
        {"left": "lt_", "right": "rt_"},
        
        # Suffix
        {"left": "_L", "right": "_R"},
        {"left": "_left", "right": "_right"},
        {"left": "_lt", "right": "_rt"},
        {"left": "_lf", "right": "_rf"},
        {"left": "_l_", "right": "_r_"},
        
        # Other patterns
        {"left": ":l_", "right": ":r_"},
        {"left": "^l_", "right": "^r_"},
        {"left": "_l$", "right": "_r$"},
        {"left": ":L", "right": ":R"},
        {"left": "^L", "right": "^R"},
        {"left": "Left", "right": "Right"},
        {"left": "left", "right": "right"}
    ]
    
    # Add custom naming convention if provided
    if L and R:
        naming_conventions.append({"left": L, "right": R})
        
    return naming_conventions

def _collect_orientation_data(objects, cmds):
    """
    Collects orientation data for the given objects.
    
    Args:
        objects (list): List of object names
        cmds: Maya commands module
        
    Returns:
        dict: Dictionary mapping object names to orientation data
    """
    orientation_data = {}
    
    for obj in objects:
        short_name = obj.split('|')[-1]
        
        try:
            # Get world matrix
            world_matrix = cmds.xform(obj, query=True, matrix=True, worldSpace=True)
            
            # Extract orientation vectors from the matrix
            x_axis = [world_matrix[0], world_matrix[1], world_matrix[2]]
            y_axis = [world_matrix[4], world_matrix[5], world_matrix[6]]
            z_axis = [world_matrix[8], world_matrix[9], world_matrix[10]]
            
            # Store orientation data
            orientation_data[short_name] = {
                'x_axis': x_axis,
                'y_axis': y_axis,
                'z_axis': z_axis
            }
            
            print(f"Collected orientation data for {short_name}")
        except Exception as e:
            print(f"Error collecting orientation data for {short_name}: {e}")
    
    return orientation_data

def _find_mirrored_name(obj_name, naming_conventions, mirror_preferences=None):
    """
    Finds the mirrored name for the given object name.
    
    Args:
        obj_name (str): Object name to find mirror for
        naming_conventions (list): List of naming conventions
        mirror_preferences (dict, optional): Dictionary of mirror preferences
        
    Returns:
        tuple: (mirrored_name, is_center_object) where mirrored_name is the name of the mirrored object
               and is_center_object is a boolean indicating if the object is a center object
    """
    # Check if we have a mirror preference with a counterpart defined
    if mirror_preferences:
        # First check if this object has preferences with a counterpart defined
        if obj_name in mirror_preferences:
            pref_data = mirror_preferences[obj_name]
            if "counterpart" in pref_data and pref_data["counterpart"]:
                return pref_data["counterpart"], False
        
        # If not, check if any object has this object defined as its counterpart
        for other_obj, pref_data in mirror_preferences.items():
            if "counterpart" in pref_data and pref_data["counterpart"] == obj_name:
                return other_obj, False
    
    is_center_object = True  # Assume it's a center object until proven otherwise
    
    for convention in naming_conventions:
        left_pattern = convention["left"]
        right_pattern = convention["right"]
        
        if left_pattern in obj_name:
            is_center_object = False
            mirrored_name = obj_name.replace(left_pattern, right_pattern)
            return mirrored_name, is_center_object
        elif right_pattern in obj_name:
            is_center_object = False
            mirrored_name = obj_name.replace(right_pattern, left_pattern)
            return mirrored_name, is_center_object
    
    # If no pattern matched, it's a center object
    return obj_name, is_center_object

def _analyze_orientations(objects, orientation_data, naming_conventions, custom_flip_controls, cmds):
    """
    Analyzes orientations of objects and their mirrors to determine custom flipping logic.
    
    Args:
        objects (list): List of object names
        orientation_data (dict): Dictionary of orientation data
        naming_conventions (list): List of naming conventions
        custom_flip_controls (dict): Dictionary of custom flip controls
        cmds: Maya commands module
        
    Returns:
        dict: Updated custom_flip_controls dictionary
    """
    for obj in objects:
        short_name = obj.split('|')[-1]
        
        # Skip if we don't have orientation data for this control
        if short_name not in orientation_data:
            continue
        
        # Find the mirrored object name
        mirrored_name, _ = _find_mirrored_name(short_name, naming_conventions)
        
        # Skip if we couldn't find a mirrored name or it doesn't exist in orientation data
        if mirrored_name != short_name and mirrored_name not in orientation_data:
            continue
        
        # Compare orientations between the control and its mirror
        obj_orient = orientation_data[short_name]
        mirror_orient = orientation_data[mirrored_name]
        
        # Initialize custom flip data for this control if not already present
        if short_name not in custom_flip_controls:
            custom_flip_controls[short_name] = {"attrs": [], "flip": {}}
        
        # Analyze X axis (affects rotateX)
        x_dot_product = obj_orient['x_axis'][0] * -mirror_orient['x_axis'][0]  # Negate for mirror reflection
        if x_dot_product < 0:  # Standard case
            custom_flip_controls[short_name]["flip"]["rotateX"] = True
        else:  # Needs custom handling
            custom_flip_controls[short_name]["attrs"].append("rotateX")
            custom_flip_controls[short_name]["flip"]["rotateX"] = False
            print(f"Auto-detected custom flipping for {short_name}.rotateX")
        
        # Analyze Y axis (affects rotateY)
        y_dot_product = obj_orient['y_axis'][1] * mirror_orient['y_axis'][1]  # No negation for Y
        if y_dot_product > 0:  # Standard case
            custom_flip_controls[short_name]["flip"]["rotateY"] = True
        else:  # Needs custom handling
            custom_flip_controls[short_name]["attrs"].append("rotateY")
            custom_flip_controls[short_name]["flip"]["rotateY"] = False
            print(f"Auto-detected custom flipping for {short_name}.rotateY")
        
        # Analyze Z axis (affects rotateZ)
        z_dot_product = obj_orient['z_axis'][2] * mirror_orient['z_axis'][2]  # No negation for Z
        if z_dot_product > 0:  # Standard case
            custom_flip_controls[short_name]["flip"]["rotateZ"] = True
        else:  # Needs custom handling
            custom_flip_controls[short_name]["attrs"].append("rotateZ")
            custom_flip_controls[short_name]["flip"]["rotateZ"] = False
            print(f"Auto-detected custom flipping for {short_name}.rotateZ")
        
        # Also add the mirrored control with the same settings
        if mirrored_name != short_name and mirrored_name not in custom_flip_controls:
            custom_flip_controls[mirrored_name] = {
                "attrs": custom_flip_controls[short_name]["attrs"].copy(),
                "flip": custom_flip_controls[short_name]["flip"].copy()
            }
    
    return custom_flip_controls

def _should_flip_attribute(control_name, attr, custom_flip_controls):
    """
    Determines if an attribute should be flipped based on custom flip controls.
    
    Args:
        control_name (str): Name of the control
        attr (str): Attribute name
        custom_flip_controls (dict): Dictionary of custom flip controls
        
    Returns:
        bool: True if the attribute should be flipped, False otherwise
    """
    should_flip = True  # Default behavior
    
    # Check if this control is in the custom flip controls dictionary
    if control_name in custom_flip_controls:
        # Check if this attribute has custom flipping logic
        if attr in custom_flip_controls[control_name].get('attrs', []):
            # Get the custom flipping logic for this attribute
            should_flip = custom_flip_controls[control_name].get('flip', {}).get(attr, True)
    
    return should_flip

def _collect_mirror_data(objects, naming_conventions, custom_flip_controls, cmds):
    """
    Collects mirror data for the given objects.
    
    Args:
        objects (list): List of object names
        naming_conventions (list): List of naming conventions
        custom_flip_controls (dict): Dictionary of custom flip controls
        cmds: Maya commands module
        
    Returns:
        dict: Dictionary mapping target objects to attribute values
    """
    mirror_data = {}
    
    # Load mirror preferences for all objects if they exist
    mirror_preferences = {}
    for obj in objects:
        short_name = obj.split('|')[-1]
        if cmds.attributeQuery("mirrorPreference", node=short_name, exists=True):
            try:
                pref_data_str = cmds.getAttr(f"{short_name}.mirrorPreference")
                mirror_preferences[short_name] = json.loads(pref_data_str)
            except (json.JSONDecodeError, Exception) as e:
                print(f"Error loading mirror preferences for {short_name}: {e}")
    
    # Also load mirror preferences for potential counterparts
    # This allows us to use counterpart preferences when an object doesn't have its own
    potential_counterparts = set()
    for obj in objects:
        short_name = obj.split('|')[-1]
        # Find the potential counterpart name
        counterpart_name, _ = _find_mirrored_name(short_name, naming_conventions)
        if counterpart_name != short_name:
            potential_counterparts.add(counterpart_name)
    
    # Load preferences for counterparts if they exist
    for counterpart in potential_counterparts:
        if counterpart not in mirror_preferences and cmds.objExists(counterpart):
            if cmds.attributeQuery("mirrorPreference", node=counterpart, exists=True):
                try:
                    pref_data_str = cmds.getAttr(f"{counterpart}.mirrorPreference")
                    mirror_preferences[counterpart] = json.loads(pref_data_str)
                except (json.JSONDecodeError, Exception) as e:
                    print(f"Error loading mirror preferences for counterpart {counterpart}: {e}")
    
    
    for obj in objects:
        # Get the short name for easier pattern matching
        short_name = obj.split('|')[-1]
        
        # Try to find the corresponding mirrored object
        mirrored_obj = None
        
        # Find mirrored name, using mirror preferences if available
        mirrored_name, is_center_object = _find_mirrored_name(short_name, naming_conventions, mirror_preferences)
        print(f"Found potential mirror: {mirrored_name}")
        
        # Check if mirrored object exists
        if cmds.objExists(mirrored_name):
            mirrored_obj = mirrored_name
        # If no mirrored object was found but it's a center object, use the object itself
        elif is_center_object:
            print(f"{short_name} appears to be a center object, will mirror its pose values")
            mirrored_obj = obj
        
        # If we found a mirrored object, collect the attribute values
        if mirrored_obj:
            # Initialize attribute dictionary for this mirrored object if not already done
            if mirrored_obj not in mirror_data:
                mirror_data[mirrored_obj] = {}
            
            # Get all keyable attributes of the source object
            attrs = cmds.listAttr(obj, keyable=True) or []
            print(f"Collecting attributes for {obj} -> {mirrored_obj}: {attrs}")
            
            # Check if this is a center object (self-mirroring)
            is_self_mirroring = (obj == mirrored_obj)
            
            # Collect attribute values, passing mirror preferences
            _collect_attribute_values(obj, mirrored_obj, attrs, short_name, is_self_mirroring, custom_flip_controls, mirror_data, cmds, mirror_preferences)
    
    return mirror_data

def _collect_attribute_values(source_obj, target_obj, attrs, control_name, is_self_mirroring, custom_flip_controls, mirror_data, cmds, mirror_preferences=None):
    """
    Collects attribute values from source object to target object.
    
    Args:
        source_obj (str): Source object name
        target_obj (str): Target object name
        attrs (list): List of attributes
        control_name (str): Control name for custom flip lookup
        is_self_mirroring (bool): Whether this is a self-mirroring (center) object
        custom_flip_controls (dict): Dictionary of custom flip controls
        mirror_data (dict): Dictionary to store mirror data
        cmds: Maya commands module
        mirror_preferences (dict, optional): Dictionary of mirror preferences
    """
    for attr in attrs:
        try:
            # Check if the attribute exists on both objects and is not locked on target
            if (cmds.objExists(f"{source_obj}.{attr}") and 
                cmds.objExists(f"{target_obj}.{attr}") and 
                not cmds.getAttr(f"{target_obj}.{attr}", lock=True)):
                
                # Get the value from the source object
                value = cmds.getAttr(f"{source_obj}.{attr}")
                
                # Handle different attribute types
                if isinstance(value, list):
                    _handle_multi_attribute(source_obj, attr, value, control_name, custom_flip_controls, target_obj, mirror_data)
                else:
                    _handle_simple_attribute(attr, value, control_name, custom_flip_controls, target_obj, mirror_data, is_self_mirroring, mirror_preferences)
        except Exception as e:
            print(f"Error collecting attribute {attr} from {source_obj} to {target_obj}: {e}")

def _handle_multi_attribute(source_obj, attr, value, control_name, custom_flip_controls, target_obj, mirror_data):
    """
    Handles multi-attributes like matrices or arrays.
    
    Args:
        source_obj (str): Source object name
        attr (str): Attribute name
        value (list): Attribute value
        control_name (str): Control name for custom flip lookup
        custom_flip_controls (dict): Dictionary of custom flip controls
        target_obj (str): Target object name
        mirror_data (dict): Dictionary to store mirror data
    """
    multi_values = []
    for i, val in enumerate(value[0]):
        # Check if we need to mirror the value
        mirrored_val = val
        
        # Check if this attribute should be flipped
        should_flip = _should_flip_attribute(control_name, attr, custom_flip_controls)
        
        # Apply standard mirroring logic if should_flip is True
        if should_flip and attr in ['translateX', 'rotateY', 'rotateZ']:
            mirrored_val = -val
        
        multi_values.append(mirrored_val)
    
    # Store the multi-attribute values
    mirror_data[target_obj][attr] = {'multi': True, 'values': multi_values}

def _handle_simple_attribute(attr, value, control_name, custom_flip_controls, target_obj, mirror_data, is_self_mirroring, mirror_preferences=None):
    """
    Handles simple (non-multi) attributes.
    
    Args:
        attr (str): Attribute name
        value: Attribute value
        control_name (str): Control name for custom flip lookup
        custom_flip_controls (dict): Dictionary of custom flip controls
        target_obj (str): Target object name
        mirror_data (dict): Dictionary to store mirror data
        is_self_mirroring (bool): Whether this is a self-mirroring (center) object
        mirror_preferences (dict, optional): Dictionary of mirror preferences
    """
    mirrored_val = value
    
    # Check if we have mirror preferences for this control or its counterpart
    use_mirror_prefs = False
    pref_data = None
    
    # First check if the object itself has mirror preferences
    if mirror_preferences and control_name in mirror_preferences:
        pref_data = mirror_preferences[control_name]
    else:
        # If not, check if we have the counterpart's preferences loaded
        # We need to find the counterpart name first
        for obj_name, prefs in mirror_preferences.items():
            if "counterpart" in prefs and prefs["counterpart"] == control_name:
                # We found a counterpart that points to this control
                pref_data = prefs
                print(f"Using counterpart {obj_name}'s mirror preferences for {control_name}")
                break
    
    if pref_data:
        # Handle translation attributes
        if attr.startswith('translate'):
            axis = attr[-1].lower()  # Get the axis (X, Y, or Z)
            if "translate" in pref_data and axis in pref_data["translate"]:
                use_mirror_prefs = True
                mirror_type = pref_data["translate"][axis]
                
                if mirror_type == "invert":
                    mirrored_val = -value
                else:  # "none"
                    mirrored_val = value
        
        # Handle rotation attributes
        elif attr.startswith('rotate'):
            axis = attr[-1].lower()  # Get the axis (X, Y, or Z)
            if "rotate" in pref_data and axis in pref_data["rotate"]:
                use_mirror_prefs = True
                mirror_type = pref_data["rotate"][axis]
                
                if mirror_type == "invert":
                    mirrored_val = -value
                else:  # "none"
                    mirrored_val = value
    
    # If we didn't use mirror preferences, use the standard logic
    if not use_mirror_prefs:
        # Check if this attribute should be flipped
        should_flip = _should_flip_attribute(control_name, attr, custom_flip_controls)
        
        # Apply standard mirroring logic if should_flip is True
        if should_flip and (attr == 'translateX' or attr == 'rotateY' or attr == 'rotateZ'):
            mirrored_val = -value
    
    # For center objects, only mirror specific attributes
    if is_self_mirroring:
        # Only store attributes that need to be flipped for center objects
        if (use_mirror_prefs or (should_flip and attr in ['translateX', 'rotateY', 'rotateZ'])):
            mirror_data[target_obj][attr] = {'multi': False, 'value': mirrored_val}
    else:
        # Store all attributes for regular mirroring
        mirror_data[target_obj][attr] = {'multi': False, 'value': mirrored_val}

def _apply_mirror_data(mirror_data, cmds):
    """
    Applies the collected mirror data to the target objects.
    
    Args:
        mirror_data (dict): Dictionary mapping target objects to attribute values
        cmds: Maya commands module
        
    Returns:
        list: List of mirrored objects
    """
    mirrored_objects = []
    locked_attrs = []
    print(f"Applying mirrored data to {len(mirror_data)} objects")
    
    for target_obj, attrs_data in mirror_data.items():
        print(f"Setting attributes for {target_obj}")
        for attr, data in attrs_data.items():
            full_attr = f"{target_obj}.{attr}"
            try:
                # Check if attribute is locked
                is_locked = False
                try:
                    is_locked = cmds.getAttr(full_attr, lock=True)
                except:
                    pass
                
                # Skip locked attributes instead of trying to unlock them
                if is_locked:
                    locked_attrs.append(full_attr)
                    print(f"Skipping locked attribute {full_attr}")
                    continue
                
                # Set the attribute value
                if data['multi']:
                    # Apply multi-attribute values
                    for i, val in enumerate(data['values']):
                        cmds.setAttr(f"{full_attr}[{i}]", val)
                else:
                    # Apply simple attribute value
                    cmds.setAttr(full_attr, data['value'])
                
                # Add to the list of mirrored objects if not already there
                if target_obj not in mirrored_objects:
                    mirrored_objects.append(target_obj)
                    
            except Exception as e:
                error_msg = str(e).lower()
                if "locked" in error_msg or "connected" in error_msg:
                    locked_attrs.append(full_attr)
                    print(f"Skipping locked or connected attribute {full_attr}: {e}")
                else:
                    print(f"Error setting attribute {attr} on {target_obj}: {e}")
    
    # Provide feedback about locked attributes if any were found
    if locked_attrs:
        print(f"Warning: {len(locked_attrs)} attributes were locked or connected and could not be modified:")
        for attr in locked_attrs:
            print(f"  - {attr}")
    
    return mirrored_objects

#---------------------------------------------------------------------------------------------------------------
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
    from . import main as MAIN
    import inspect
    
    # Determine if this function is being called from a button's script
    is_from_script = False
    if source_button is None:
        for frame_info in inspect.stack():
            if frame_info.function == 'execute_script_command':
                is_from_script = True
                break
    
    # Get the current picker window manager instance
    manager = MAIN.PickerWindowManager.get_instance()
    
    # Check if there are any picker widgets available
    if not manager or not manager._picker_widgets:
        print("No picker widgets found.")
        return
    
    # Get all available buttons by searching through the widget hierarchy
    all_buttons = []
    
    # First try to get the current picker widget and its canvas
    for picker_widget in manager._picker_widgets:
        # Try different ways to access the canvas
        canvas = None
        
        # Method 1: Direct canvas attribute
        if hasattr(picker_widget, 'canvas'):
            canvas = picker_widget.canvas
        
        # Method 2: Look for canvas in tab system
        elif hasattr(picker_widget, 'tab_widget'):
            tab_widget = picker_widget.tab_widget
            current_tab = tab_widget.currentWidget()
            if hasattr(current_tab, 'canvas'):
                canvas = current_tab.canvas
        
        # Method 3: Search for canvas in children
        if not canvas:
            for child in picker_widget.findChildren(QtWidgets.QWidget):
                if hasattr(child, 'buttons') and isinstance(child.buttons, list):
                    canvas = child
                    break
        
        # If we found a canvas, get its buttons
        if canvas and hasattr(canvas, 'buttons'):
            all_buttons.extend(canvas.buttons)
    
    # If we still don't have any buttons, try a more aggressive search
    if not all_buttons:
        # Look for any widget that might be a button
        for picker_widget in manager._picker_widgets:
            for child in picker_widget.findChildren(QtWidgets.QWidget):
                if hasattr(child, 'mode') and hasattr(child, 'label') and hasattr(child, 'unique_id'):
                    all_buttons.append(child)
    
    # If we still don't have any buttons, give up
    if not all_buttons:
        print("No buttons found in any picker widget.")
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
                # Find buttons by unique ID only
                for btn in all_buttons:
                    # Match by unique ID
                    if hasattr(btn, 'unique_id') and btn.unique_id == target:
                        buttons_to_modify.append(btn)
                        break
            else:
                # Assume it's a button object
                buttons_to_modify.append(target)
    
    # Case 2: Source button provided or detected from script execution
    elif source_button is not None:
        # Use the provided source button
        buttons_to_modify = [source_button]
    elif is_from_script:
        # We're being called from a script but don't have the source button
        # Try to find the button that's executing this script
        for frame_info in inspect.stack():
            if hasattr(frame_info, 'frame'):
                if 'self' in frame_info.frame.f_locals:
                    potential_button = frame_info.frame.f_locals['self']
                    if hasattr(potential_button, 'mode') and hasattr(potential_button, 'script_data'):
                        # This looks like a PickerButton
                        buttons_to_modify = [potential_button]
                        break
    
    # Case 3: Default to selected buttons
    else:
        # Get selected buttons
        buttons_to_modify = [btn for btn in all_buttons if btn.is_selected]
    
    # Check if we have any buttons to modify
    if not buttons_to_modify:
        print("No buttons to modify. Please select at least one button or call this function from a button's script.")
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
    
    # Apply changes to all buttons
    for button in buttons_to_modify:
        # Update text if provided
        if text:
            button.label = text
            # Reset text pixmap cache to force redraw
            button.text_pixmap = None
            button.pose_pixmap = None
            button.last_zoom_factor = 0
        
        # Update color if provided
        if color:
            # Validate color format
            if color.startswith('#') and (len(color) == 7 or len(color) == 9):
                button.color = color
            else:
                print(f"Invalid color format: {color}. Color should be in hex format (e.g., #FF0000).")
        
        # Update opacity if provided and valid
        if opacity_value is not None:
            button.opacity = opacity_value
            
        # Update selectable state if provided and valid
        if selectable_value is not None:
            # Add selectable attribute if it doesn't exist
            if not hasattr(button, 'selectable'):
                button.selectable = True  # Default to True for backward compatibility
            button.selectable = selectable_value
        
        # Update tooltip and force redraw
        button.update_tooltip()
        button.update()
    
    # Update the canvas if we have access to it
    if len(buttons_to_modify) > 0 and buttons_to_modify[0].parent():
        buttons_to_modify[0].parent().update()
    
    # Report changes
    changes = []
    if text: changes.append(f"text to '{text}'")
    if color: changes.append(f"color to '{color}'")
    if opacity_value is not None: changes.append(f"opacity to {opacity_value}")
    if selectable_value is not None: changes.append(f"selectable to {selectable_value}")
    
    if changes:
        print(f"Updated {len(buttons_to_modify)} button(s): {', '.join(changes)}")
    else:
        print("No changes were made. Please provide at least one parameter (text, color, or opacity).")
