import maya.cmds as cmds
import maya.mel as mel
import maya.api.OpenMaya as om
from maya import OpenMayaUI as omui
from functools import wraps

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

class animation_tool_layout:
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
        reset_transform_button = CB.CustomButton(text='Reset', color='#262626', size=14, tooltip="Resets the object transform to Origin.",
                                                 text_size=ts, height=bh,ContextMenu=True, onlyContext=True)
        reset_transform_button.addToMenu("Move", reset_move, icon='delete.png', position=(0,0))
        reset_transform_button.addToMenu("Rotate", reset_rotate, icon='delete.png', position=(1,0))
        reset_transform_button.addToMenu("Scale", reset_scale, icon='delete.png', position=(2,0))

        reset_all_button = CB.CustomButton(text='Reset All', icon=':delete.png', size=14, color='#262626', tooltip="Resets all the object transform to Origin.",text_size=ts, height=bh)

        timeLine_key_button = CB.CustomButton(text='Key', color='#d62e22', tooltip="Sets key frame.",text_size=ts, height=bh)
        timeLine_delete_key_button = CB.CustomButton(text='Key', icon=':delete.png', color='#262626', size=14, tooltip="Deletes keys from the given start frame to the current frame.",text_size=ts, height=bh)
        timeLine_copy_key_button = CB.CustomButton(text='Copy', color='#293F64', tooltip="Copy selected key(s).",text_size=ts, height=bh)
        timeLine_paste_key_button = CB.CustomButton(text='Paste', color='#1699CA', tooltip="Paste copied key(s).",text_size=ts, height=bh)
        timeLine_pasteInverse_key_button = CB.CustomButton(text='Paste Inverse', color='#9416CA', tooltip="Paste Inverted copied keys(s).",text_size=ts, height=bh)

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
        reset_all_button.singleClicked.connect(reset_all)

        timeLine_key_button.singleClicked.connect(set_key)
        timeLine_delete_key_button.singleClicked.connect(delete_keys)
        timeLine_copy_key_button.singleClicked.connect(copy_keys)
        timeLine_paste_key_button.singleClicked.connect(paste_keys)
        timeLine_pasteInverse_key_button.singleClicked.connect(paste_inverse)

        store_pos_button.singleClicked.connect(store_component_position)
        move_to_pos_button.singleClicked.connect(move_objects_to_stored_position)
        #---------------------------------------------------------------------------------------------------------------------------------------------------------------------------
        #self.col1.addWidget(reset_move_button)
        #self.col1.addWidget(reset_rotate_button)
        #self.col1.addWidget(reset_scale_button)
        self.col1.addWidget(reset_transform_button)
        self.col1.addWidget(reset_all_button)

        self.col1.addSpacing(4)

        self.col1.addWidget(timeLine_key_button)
        self.col1.addWidget(timeLine_delete_key_button)
        self.col1.addWidget(timeLine_copy_key_button)
        self.col1.addWidget(timeLine_paste_key_button)
        self.col1.addWidget(timeLine_pasteInverse_key_button)

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
    cmds.undoInfo(openChunk=True)
    try:
        # Get the list of selected objects
        sel_objs = cmds.ls(sl=True)

        # Loop through each selected object
        for obj in sel_objs:
            # Get the current translate values
            tx = cmds.getAttr(f"{obj}.tx")
            ty = cmds.getAttr(f"{obj}.ty")
            tz = cmds.getAttr(f"{obj}.tz")

            # Check if the attributes are locked
            tx_locked = cmds.getAttr(f"{obj}.tx", lock=True)
            ty_locked = cmds.getAttr(f"{obj}.ty", lock=True)
            tz_locked = cmds.getAttr(f"{obj}.tz", lock=True)

            # Reset the translate values if the attribute is not locked
            if not tx_locked:
                cmds.setAttr(f"{obj}.tx", 0)

            if not ty_locked:
                cmds.setAttr(f"{obj}.ty", 0)

            if not tz_locked:
                cmds.setAttr(f"{obj}.tz", 0)
    finally:
        cmds.undoInfo(closeChunk=True) 

@undoable
def reset_rotate():
    cmds.undoInfo(openChunk=True)
    try:
        # Get the list of selected objects
        sel_objs = cmds.ls(sl=True)

        # Loop through each selected object
        for obj in sel_objs:
            # Get the current rotate values
            rx = cmds.getAttr(f"{obj}.rx")
            ry = cmds.getAttr(f"{obj}.ry")
            rz = cmds.getAttr(f"{obj}.rz")

            # Check if the rotate attributes are locked
            rx_locked = cmds.getAttr(f"{obj}.rx", lock=True)
            ry_locked = cmds.getAttr(f"{obj}.ry", lock=True)
            rz_locked = cmds.getAttr(f"{obj}.rz", lock=True)

            # Reset the rotate values if the attribute is not locked
            if not rx_locked:
                cmds.setAttr(f"{obj}.rx", 0)
            if not ry_locked:
                cmds.setAttr(f"{obj}.ry", 0)
            if not rz_locked:
                cmds.setAttr(f"{obj}.rz", 0)
    finally:
        cmds.undoInfo(closeChunk=True)

@undoable   
def reset_scale():
    cmds.undoInfo(openChunk=True)
    try:
        # Get the list of selected objects
        sel_objs = cmds.ls(sl=True)

        # Loop through each selected object
        for obj in sel_objs:
            # Get the current scale values
            sx = cmds.getAttr(f"{obj}.sx")
            sy = cmds.getAttr(f"{obj}.sy")
            sz = cmds.getAttr(f"{obj}.sz")

            # Check if the scale attributes are locked
            sx_locked = cmds.getAttr(f"{obj}.sx", lock=True)
            sy_locked = cmds.getAttr(f"{obj}.sy", lock=True)
            sz_locked = cmds.getAttr(f"{obj}.sz", lock=True)

            # Reset the scale values if the attribute is not locked
            if not sx_locked:
                cmds.setAttr(f"{obj}.sx", 1)
            if not sy_locked:
                cmds.setAttr(f"{obj}.sy", 1)
            if not sz_locked:
                cmds.setAttr(f"{obj}.sz", 1)
    finally:
        cmds.undoInfo(closeChunk=True) 

@undoable
def reset_all():
    cmds.undoInfo(openChunk=True)
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
                cmds.setAttr(f"{obj}.tx", 0)
            if not ty_locked:
                cmds.setAttr(f"{obj}.ty", 0)
            if not tz_locked:
                cmds.setAttr(f"{obj}.tz", 0)

            # Reset the rotate values if the attribute is not locked
            if not rx_locked:
                cmds.setAttr(f"{obj}.rx", 0)
            if not ry_locked:
                cmds.setAttr(f"{obj}.ry", 0)
            if not rz_locked:
                cmds.setAttr(f"{obj}.rz", 0)

            # Reset the scale values if the attribute is not locked
            if not sx_locked:
                cmds.setAttr(f"{obj}.sx", 1)
            if not sy_locked:
                cmds.setAttr(f"{obj}.sy", 1)
            if not sz_locked:
                cmds.setAttr(f"{obj}.sz", 1)
    finally:
        cmds.undoInfo(closeChunk=True) 
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
