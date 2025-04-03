try:
    from PySide6 import QtWidgets, QtCore, QtGui
    from shiboken6 import wrapInstance
except ImportError:
    from PySide2 import QtWidgets, QtCore, QtGui
    from shiboken2 import wrapInstance

import maya.cmds as cmds
import maya.OpenMayaUI as omui
import os
import json

from . import utils as UT
from .graphics_picker_view import PickerGraphicsView


def maya_main_window():
    """Return Maya's main window as a QWidget"""
    main_window_ptr = omui.MQtUtil.mainWindow()
    if main_window_ptr is not None:
        return wrapInstance(int(main_window_ptr), QtWidgets.QWidget)
    return None


class GraphicsPickerTest(QtWidgets.QDialog):
    """Test dialog for the QGraphicsView-based picker"""
    
    def __init__(self, parent=maya_main_window()):
        super().__init__(parent)
        
        self.setWindowTitle("Graphics Picker Test")
        self.setMinimumSize(800, 600)
        self.setWindowFlags(self.windowFlags() | QtCore.Qt.Window)
        
        # Create UI
        self.create_ui()
        self.create_connections()
        
        # Add some test buttons
        self.add_test_buttons()
    
    def create_ui(self):
        """Create the UI elements"""
        # Main layout
        main_layout = QtWidgets.QVBoxLayout(self)
        main_layout.setContentsMargins(2, 2, 2, 2)
        main_layout.setSpacing(2)
        
        # Toolbar
        toolbar = QtWidgets.QHBoxLayout()
        toolbar.setContentsMargins(0, 0, 0, 0)
        toolbar.setSpacing(2)
        main_layout.addLayout(toolbar)
        
        # Edit mode toggle
        self.edit_mode_btn = QtWidgets.QPushButton("Edit Mode")
        self.edit_mode_btn.setCheckable(True)
        toolbar.addWidget(self.edit_mode_btn)
        
        # Add button
        self.add_button_btn = QtWidgets.QPushButton("Add Button")
        toolbar.addWidget(self.add_button_btn)
        
        # Reset view button
        self.reset_view_btn = QtWidgets.QPushButton("Reset View")
        toolbar.addWidget(self.reset_view_btn)
        
        # Spacer
        toolbar.addStretch()
        
        # Namespace dropdown
        toolbar.addWidget(QtWidgets.QLabel("Namespace:"))
        self.namespace_dropdown = QtWidgets.QComboBox()
        self.namespace_dropdown.addItem("None")
        toolbar.addWidget(self.namespace_dropdown)
        
        # Save/Load buttons
        self.save_btn = QtWidgets.QPushButton("Save")
        toolbar.addWidget(self.save_btn)
        
        self.load_btn = QtWidgets.QPushButton("Load")
        toolbar.addWidget(self.load_btn)
        
        # Graphics view
        self.graphics_view = PickerGraphicsView()
        main_layout.addWidget(self.graphics_view)
    
    def create_connections(self):
        """Connect signals and slots"""
        # Toolbar buttons
        self.edit_mode_btn.toggled.connect(self.toggle_edit_mode)
        self.add_button_btn.clicked.connect(self.add_new_button)
        self.reset_view_btn.clicked.connect(self.graphics_view.reset_view)
        self.save_btn.clicked.connect(self.save_picker)
        self.load_btn.clicked.connect(self.load_picker)
        
        # Refresh namespace dropdown when window is shown
        self.shown = False
        
    def showEvent(self, event):
        """Handle show event"""
        super().showEvent(event)
        
        # Only refresh namespaces the first time shown
        if not self.shown:
            self.refresh_namespaces()
            self.shown = True
    
    def toggle_edit_mode(self, enabled):
        """Toggle edit mode"""
        self.graphics_view.set_edit_mode(enabled)
        self.add_button_btn.setEnabled(enabled)
    
    def add_new_button(self):
        """Add a new button to the view"""
        self.graphics_view.add_button("Button")
    
    def add_test_buttons(self):
        """Add some test buttons to the view"""
        # Add a few test buttons
        colors = ['#5285a6', '#91cb08', '#cb0891', '#cb4f08']
        positions = [
            QtCore.QPointF(-150, -50),
            QtCore.QPointF(0, -50),
            QtCore.QPointF(150, -50),
            QtCore.QPointF(-150, 50),
            QtCore.QPointF(0, 50),
            QtCore.QPointF(150, 50)
        ]
        
        for i, pos in enumerate(positions):
            color = colors[i % len(colors)]
            button = self.graphics_view.add_button(
                f"Button {i+1}",
                pos=pos,
                color=color
            )
            
            # Add some test objects to every other button
            if i % 2 == 0:
                button.assigned_objects = [
                    {'uuid': f'test_uuid_{i}', 'long_name': f'test_object_{i}'}
                ]
            else:
                # Make every other button a script button
                button.set_mode('script')
                button.set_script_data({
                    'language': 'python',
                    'script': f'print("Button {i+1} script executed")'
                })
            
            button.update_tooltip()
    
    def refresh_namespaces(self):
        """Refresh the namespace dropdown"""
        # Store current selection
        current_ns = self.namespace_dropdown.currentText()
        
        # Clear and repopulate
        self.namespace_dropdown.clear()
        self.namespace_dropdown.addItem("None")
        
        # Get all namespaces from Maya
        try:
            namespaces = cmds.namespaceInfo(listOnlyNamespaces=True, recurse=True) or []
            for ns in sorted(namespaces):
                if ns not in ['UI', 'shared']:
                    self.namespace_dropdown.addItem(ns)
        except Exception as e:
            cmds.warning(f"Error getting namespaces: {e}")
        
        # Restore selection if possible
        index = self.namespace_dropdown.findText(current_ns)
        if index >= 0:
            self.namespace_dropdown.setCurrentIndex(index)
    
    def save_picker(self):
        """Save the picker data to a file"""
        # Get file path
        file_path, _ = QtWidgets.QFileDialog.getSaveFileName(
            self, "Save Picker", "", "Picker Files (*.picker);;All Files (*)"
        )
        
        if not file_path:
            return
            
        # Add extension if not present
        if not file_path.endswith('.picker'):
            file_path += '.picker'
        
        # Get data from view
        data = self.graphics_view.save_data()
        
        # Save to file
        try:
            with open(file_path, 'w') as f:
                json.dump(data, f, indent=2)
            cmds.inViewMessage(message=f"Picker saved to {os.path.basename(file_path)}", 
                               pos='topCenter', fade=True)
        except Exception as e:
            cmds.warning(f"Error saving picker: {e}")
            QtWidgets.QMessageBox.critical(self, "Save Error", f"Error saving picker: {e}")
    
    def load_picker(self):
        """Load picker data from a file"""
        # Get file path
        file_path, _ = QtWidgets.QFileDialog.getOpenFileName(
            self, "Load Picker", "", "Picker Files (*.picker);;All Files (*)"
        )
        
        if not file_path or not os.path.exists(file_path):
            return
        
        # Load data from file
        try:
            with open(file_path, 'r') as f:
                data = json.load(f)
            
            # Apply data to view
            self.graphics_view.load_data(data)
            cmds.inViewMessage(message=f"Picker loaded from {os.path.basename(file_path)}", 
                               pos='topCenter', fade=True)
        except Exception as e:
            cmds.warning(f"Error loading picker: {e}")
            QtWidgets.QMessageBox.critical(self, "Load Error", f"Error loading picker: {e}")


def show_graphics_test():
    """Show the graphics picker test dialog"""
    # Close existing dialog if it exists
    for widget in QtWidgets.QApplication.topLevelWidgets():
        if isinstance(widget, GraphicsPickerTest):
            widget.close()
    
    # Create and show new dialog
    dialog = GraphicsPickerTest()
    dialog.show()
    
    return dialog


# For testing in Maya
if __name__ == "__main__":
    show_graphics_test()
