from functools import partial
import maya.cmds as cmds
import maya.mel as mel
import os
try:
    from PySide6 import QtWidgets, QtCore, QtGui
    from PySide6.QtGui import QColor, QAction, QActionGroup
    from PySide6.QtCore import QTimer, QPropertyAnimation, QEasingCurve, Signal
    from shiboken6 import wrapInstance
except ImportError:
    from PySide2 import QtWidgets, QtCore, QtGui
    from PySide2.QtWidgets import QAction, QActionGroup
    from PySide2.QtGui import QColor
    from PySide2.QtCore import QTimer, QPropertyAnimation, QEasingCurve, Signal
    from shiboken2 import wrapInstance

import math
import re

from . import utils as UT
from . import custom_line_edit as CLE
from . import custom_button as CB
from . import data_management as DM
from . import ui as UI
from . import tool_functions as TF
from . import custom_dialog as CD
from . import main as MAIN

class SelectionManagerWidget(QtWidgets.QWidget):
    def __init__(self, parent=None):
        if parent is None:
            manager = MAIN.PickerWindowManager.get_instance()
            parent = manager._picker_widgets[0] if manager._picker_widgets else None
        super(SelectionManagerWidget, self).__init__(parent)
        self.setWindowFlags(QtCore.Qt.Window | QtCore.Qt.FramelessWindowHint)
        self.setAttribute(QtCore.Qt.WA_TranslucentBackground)
        
        # Setup main layout
        self.main_layout = QtWidgets.QVBoxLayout(self)
        self.main_layout.setContentsMargins(4, 4, 4, 4)
        self.main_layout.setSpacing(4)
        
        # Create main frame
        self.frame = QtWidgets.QFrame()
        self.frame.setFixedWidth(200)
        self.frame.setStyleSheet("""
            QFrame {
                background-color: rgba(36, 36, 36, .9);
                border: 1px solid #444444;
                border-radius: 4px;
            }
        """)
        self.frame_layout = QtWidgets.QVBoxLayout(self.frame)
        self.frame_layout.setContentsMargins(6, 6, 6, 6)
        self.frame_layout.setSpacing(6)
        
        # Title bar with draggable area and close button
        self.title_bar = QtWidgets.QWidget()
        self.title_bar.setFixedHeight(30)
        self.title_bar.setStyleSheet("background: rgba(30, 30, 30, .9); border: none; border-radius: 3px;")
        title_layout = QtWidgets.QHBoxLayout(self.title_bar)
        title_layout.setContentsMargins(6, 6, 6, 6)
        title_layout.setSpacing(6)
        
        self.title_label = QtWidgets.QLabel("Selection Manager")
        self.title_label.setStyleSheet("color: #dddddd; background: transparent;")
        title_layout.addWidget(self.title_label)
        
        self.close_button = QtWidgets.QPushButton("✕")
        self.close_button.setFixedSize(16, 16)
        self.close_button.setStyleSheet("""
            QPushButton {
                background-color: rgba(200, 0, 0, 0.6);
                color: #ff9393;
                border: none;
                border-radius: 2px;
                padding: 0px 0px 2px 0px;
            }
            QPushButton:hover {
                background-color: rgba(255, 0, 0, 0.6);
            }
        """)
        title_layout.addWidget(self.close_button)
        
        # Selection buttons
        self.button_layout = QtWidgets.QHBoxLayout()
        self.add_selection_btn = QtWidgets.QPushButton("Add")
        self.add_selection_btn.setFixedHeight(20)
        self.add_selection_btn.setStyleSheet("""
            QPushButton {
                background-color: #5285a6;
                color: white;
                border: none;
                border-radius: 3px;
            }
            QPushButton:hover {
                background-color: #619ac2;
            }
        """)
        
        self.remove_selection_btn = QtWidgets.QPushButton("Remove")
        self.remove_selection_btn.setFixedHeight(20)
        self.remove_selection_btn.setStyleSheet("""
            QPushButton {
                background-color: #494949;
                color: white;
                border: none;
                border-radius: 3px;
            }
            QPushButton:hover {
                background-color: #5a5a5a;
            }
        """)
        
        self.button_layout.addWidget(self.add_selection_btn)
        self.button_layout.addWidget(self.remove_selection_btn)
        
        # Selection list
        self.list_frame = QtWidgets.QFrame()
        self.list_frame.setStyleSheet("""
            QFrame {
                background-color: #1e1e1e;
                border-radius: 2px;
            }
        """)
        self.list_layout = QtWidgets.QVBoxLayout(self.list_frame)
        self.list_layout.setContentsMargins(2, 2, 2, 2)
        
        self.selection_list = QtWidgets.QListWidget()
        self.selection_list.setFixedHeight(200)
        self.selection_list.setSelectionMode(QtWidgets.QAbstractItemView.ExtendedSelection)
        self.selection_list.setStyleSheet("""
            QListWidget {
                background-color: transparent;
                border: none;
                color: #dddddd;
                outline: 0;
            }
                QListWidget::item:focus {
                border: none;  /* Remove focus border */
                outline: none;  /* Remove focus outline */
            }
            QListWidget::item {
                padding: 3px;
                border-radius: 0px;
            }
            QListWidget::item:selected {
                background-color: #2c4759;
            }
            QListWidget::item:hover {
                background-color: rgba(44, 71, 89, 0.5);
            }
        """)
        self.list_layout.addWidget(self.selection_list)
        
        # Add all layouts to main layout
        self.frame_layout.addWidget(self.title_bar)
        self.frame_layout.addLayout(self.button_layout)
        self.frame_layout.addWidget(self.list_frame)
        self.main_layout.addWidget(self.frame)
        
        # Connect signals
        self.close_button.clicked.connect(self.close)
        self.add_selection_btn.clicked.connect(self.add_selection)
        self.remove_selection_btn.clicked.connect(self.remove_selection)
        
        # Window dragging
        self.dragging = False
        self.offset = None
        self.title_bar.mousePressEvent = self.title_bar_mouse_press
        self.title_bar.mouseMoveEvent = self.title_bar_mouse_move
        self.title_bar.mouseReleaseEvent = self.title_bar_mouse_release
        
        self.picker_button = None

    def set_picker_button(self, button):
        self.picker_button = button
        self.refresh_list()
        self.position_window()
        
    def position_window(self):
        if self.picker_button:
            button_geometry = self.picker_button.geometry()
            global_pos = self.picker_button.mapToGlobal(button_geometry.topRight())
            # Add some offset to position it slightly to the right
            self.move(global_pos + QtCore.QPoint(10, 0))
    
    def refresh_list(self):
        """Refresh the list with human-readable object names, compatible with new object structure"""
        self.selection_list.clear()
        if self.picker_button:
            for obj_data in self.picker_button.assigned_objects:
                try:
                    # Handle both old format (just UUID) and new format (dict with UUID and long_name)
                    if isinstance(obj_data, dict):
                        uuid = obj_data['uuid']
                        long_name = obj_data['long_name']
                        
                        # Try to resolve current name from UUID first
                        nodes = cmds.ls(uuid, long=True)
                        node_name = ""
                        
                        if nodes:
                            # Use UUID resolution if available
                            node_name = nodes[0]
                        elif cmds.objExists(long_name):
                            # Fallback to long name if UUID fails
                            node_name = long_name
                        
                        if node_name:
                            # Strip namespace by taking the last part after any ':'
                            short_name = node_name.split('|')[-1].split(':')[-1]
                            item = QtWidgets.QListWidgetItem(short_name)
                            # Store the complete object data for removal
                            item.setData(QtCore.Qt.UserRole, obj_data)
                            self.selection_list.addItem(item)
                    else:
                        # Legacy format - just UUID
                        uuid = obj_data
                        nodes = cmds.ls(uuid, long=True)
                        if nodes:
                            # Strip namespace by taking the last part after any ':'
                            short_name = nodes[0].split('|')[-1].split(':')[-1]
                            item = QtWidgets.QListWidgetItem(short_name)
                            # Store the UUID as item data for removal
                            item.setData(QtCore.Qt.UserRole, uuid)
                            self.selection_list.addItem(item)
                except Exception as e:
                    # Handle case where object no longer exists
                    continue
                
    def add_selection(self):
        """Add selected objects using new object structure"""
        if self.picker_button:
            self.picker_button.add_selected_objects()
            self.refresh_list()
        UT.maya_main_window().activateWindow()
            
    def remove_selection(self):
        """Remove selected objects using new object structure"""
        if self.picker_button:
            selected_items = self.selection_list.selectedItems()
            
            # Extract objects to remove
            objects_to_remove = []
            for item in selected_items:
                item_data = item.data(QtCore.Qt.UserRole)
                objects_to_remove.append(item_data)
            
            # Filter out selected objects
            new_assigned_objects = []
            for obj_data in self.picker_button.assigned_objects:
                # Check if this object should be removed
                should_remove = False
                
                for remove_data in objects_to_remove:
                    if isinstance(obj_data, dict) and isinstance(remove_data, dict):
                        # Both are dictionaries - new format
                        if obj_data['uuid'] == remove_data['uuid']:
                            should_remove = True
                            break
                    elif isinstance(obj_data, dict) and not isinstance(remove_data, dict):
                        # Mixed format - compare UUID only
                        if obj_data['uuid'] == remove_data:
                            should_remove = True
                            break
                    elif not isinstance(obj_data, dict) and not isinstance(remove_data, dict):
                        # Both are old format - direct comparison
                        if obj_data == remove_data:
                            should_remove = True
                            break
                
                if not should_remove:
                    new_assigned_objects.append(obj_data)
            
            self.picker_button.assigned_objects = new_assigned_objects
            self.picker_button.update_tooltip()
            self.picker_button.changed.emit(self.picker_button)
            self.refresh_list()
        UT.maya_main_window().activateWindow()

    # Window dragging methods
    def title_bar_mouse_press(self, event):
        if event.button() == QtCore.Qt.LeftButton:
            self.dragging = True
            self.offset = event.globalPos() - self.pos()
        UT.maya_main_window().activateWindow()
            
    def title_bar_mouse_move(self, event):
        if self.dragging and event.buttons() == QtCore.Qt.LeftButton:
            self.move(event.globalPos() - self.offset)
            
    def title_bar_mouse_release(self, event):
        if event.button() == QtCore.Qt.LeftButton:
            self.dragging = False

    def closeEvent(self, event):
        super().closeEvent(event)
        UT.maya_main_window().activateWindow()
