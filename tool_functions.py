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
        ts = 10 # text size
        bh = 20 # button height
        reset_move_button = CB.CustomButton(text='Move', icon=':delete.png', color='#262626', size=14, tooltip="Resets the moved object values to Origin.",text_size=ts, height=bh)
        reset_rotate_button = CB.CustomButton(text='Rotate', icon=':delete.png', color='#262626', size=14, tooltip="Resets the rotated object values to Origin.",text_size=ts, height=bh)
        reset_scale_button = CB.CustomButton(text='Scale', icon=':delete.png', color='#262626', size=14, tooltip="Resets the scaled object values to Origin.",text_size=ts, height=bh)
        reset_all_button = CB.CustomButton(text='Reset All', color='#CF2222', tooltip="Resets all the object transform to Origin.",text_size=ts, height=bh)
        reset_move_button.singleClicked.connect(reset_move)
        reset_rotate_button.singleClicked.connect(reset_rotate)
        reset_scale_button.singleClicked.connect(reset_scale)
        reset_all_button.singleClicked.connect(reset_all)
        self.col1.addWidget(reset_move_button)
        self.col1.addWidget(reset_rotate_button)
        self.col1.addWidget(reset_scale_button)
        self.col1.addWidget(reset_all_button)
        #---------------------------------------------------------------------------------------------------------------------------------------------------------------------------
        self.tools_scroll_frame_layout.addLayout(self.col1)
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
