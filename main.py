try:
    from PySide6 import QtWidgets, QtCore, QtGui
except ImportError:
    from PySide2 import QtWidgets, QtCore, QtGui

# Import utils at the top level
from . import utils as UT

# UI module will be imported on demand to avoid circular imports

class PickerWindowManager:
    _instance = None
    _picker_widgets = []
    
    @classmethod
    def get_instance(cls):
        if cls._instance is None:
            cls._instance = PickerWindowManager()
        return cls._instance
    
    def create_window(self):
        # Lazy import UI to avoid circular dependency
        from . import ui as UI
        
        # Create new picker widget
        picker_widget = UI.AnimPickerWindow(parent=UT.maya_main_window())
        picker_widget.setObjectName(f"floatingTool_{len(self._picker_widgets)}")
        
        # Store reference to widget
        self._picker_widgets.append(picker_widget)
        
        # Connect close event
        picker_widget.destroyed.connect(lambda: self.remove_widget(picker_widget))
        
        # Show widget
        picker_widget.show()
        UT.maya_main_window().activateWindow()
        
        return picker_widget
    
    def remove_widget(self, widget):
        if widget in self._picker_widgets:
            self._picker_widgets.remove(widget)
    
    def close_all_windows(self):
        for widget in self._picker_widgets[:]:  # Create copy of list to avoid modification during iteration
            widget.close()
            widget.deleteLater()
        self._picker_widgets.clear()

def ft_anim_picker_window():
    """Create a new instance of the animation picker window"""
    manager = PickerWindowManager.get_instance()
    return manager.create_window()

if __name__ == "__main__":
    ft_anim_picker_window()