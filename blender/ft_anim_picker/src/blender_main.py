import bpy
import sys
import os

# Global variable to store the Qt application instance
_qt_app = None

# Function to get or create the Qt application
def get_qt_app():
    global _qt_app
    
    try:
        from PySide6 import QtWidgets, QtCore
    except ImportError:
        raise ImportError("PySide6 is required to use FT Animation Picker. Please install it to use this addon.")
    
    # Create Qt application if it doesn't exist
    if _qt_app is None:
        # Check if QApplication already exists (created by Blender)
        if QtWidgets.QApplication.instance():
            _qt_app = QtWidgets.QApplication.instance()
        else:
            # Create a new QApplication with Blender's args
            _qt_app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(sys.argv)
    
    return _qt_app

class PickerWindowManager:
    _instance = None
    _picker_widgets = []
    
    @classmethod
    def get_instance(cls):
        if cls._instance is None:
            cls._instance = PickerWindowManager()
        return cls._instance
    
    def create_window(self):
        # Ensure Qt app exists
        app = get_qt_app()
        
        # Lazy import UI to avoid circular dependency
        from . import blender_ui as UI
        
        # Create new picker widget
        picker_widget = UI.BlenderAnimPickerWindow()
        picker_widget.setObjectName(f"floatingTool_{len(self._picker_widgets)}")
        
        # Store reference to widget
        self._picker_widgets.append(picker_widget)
        
        # Connect close event
        picker_widget.destroyed.connect(lambda: self.remove_widget(picker_widget))
        
        # Show widget
        picker_widget.show()
        
        # Process some events to ensure the window appears
        app.processEvents()
        
        return picker_widget
    
    def remove_widget(self, widget):
        if widget in self._picker_widgets:
            self._picker_widgets.remove(widget)
    
    def close_all_windows(self):
        for widget in self._picker_widgets[:]:  # Create copy of list to avoid modification during iteration
            widget.close()
            widget.deleteLater()
        self._picker_widgets.clear()
        
        # Process events to ensure windows are closed
        app = get_qt_app()
        if app:
            app.processEvents()

def open():
    """Create a new instance of the animation picker window"""
    manager = PickerWindowManager.get_instance()
    return manager.create_window()

# Blender operator to open the picker
class ANIM_OT_open_ft_picker(bpy.types.Operator):
    bl_idname = "anim.open_ft_picker"
    bl_label = "FT Animation Picker"
    bl_description = "Open the FT Animation Picker"
    
    def execute(self, context):
        open()
        return {'FINISHED'}

# Registration
def register():
    bpy.utils.register_class(ANIM_OT_open_ft_picker)

def unregister():
    bpy.utils.unregister_class(ANIM_OT_open_ft_picker)

if __name__ == "__main__":
    register()
