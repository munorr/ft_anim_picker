try:
    from PySide6 import QtWidgets, QtCore, QtGui
except ImportError:
    from PySide2 import QtWidgets, QtCore, QtGui

from . import ui as UI
from . import utils as UT

def ft_anim_picker_window():
    try:
        if hasattr(UT.maya_main_window(), '_picker_widget'):
            UT.maya_main_window()._picker_widget.close()
            UT.maya_main_window()._picker_widget.deleteLater()
    except:
        pass

    picker_widget = UI.AnimPickerWindow(parent=UT.maya_main_window())
    picker_widget.setObjectName("floatingTool")
    #picker_widget.move(1280, 700)
    picker_widget.show()
    UT.maya_main_window()._picker_widget= picker_widget
    UT.maya_main_window().activateWindow()

ft_anim_picker_window()