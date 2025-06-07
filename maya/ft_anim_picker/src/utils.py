import maya.cmds as cmds
from maya import OpenMayaUI as omui
from functools import wraps
from pathlib import Path
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
    

def undoable(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        cmds.undoInfo(openChunk=True)
        try:
            return func(*args, **kwargs)
        finally:
            cmds.undoInfo(closeChunk=True)
    return wrapper

def shortcuts(**shortcut_map):
    """Decorator to add parameter shortcuts to any function"""
    def decorator(func):
        def wrapper(*args, **kwargs):
            # Process shortcuts
            for short, full in shortcut_map.items():
                if short in kwargs and full not in kwargs:
                    kwargs[full] = kwargs.pop(short)
            return func(*args, **kwargs)
        return wrapper
    return decorator

def rgba_value(hex_color, factor, alpha=None):
    color = QColor(hex_color)
    r, g, b, a = color.getRgbF()
    
    if factor > 1:
        # Lighten: blend towards white
        # Formula: color + (1 - color) * (factor - 1) / factor
        blend_amount = (factor - 1) / factor
        r = r + (1 - r) * blend_amount
        g = g + (1 - g) * blend_amount
        b = b + (1 - b) * blend_amount
    else:
        # Darken: multiply normally
        r = r * factor
        g = g * factor
        b = b * factor
    
    # Ensure values stay within bounds
    r = min(max(r, 0), 1)
    g = min(max(g, 0), 1)
    b = min(max(b, 0), 1)
    
    # Use the provided alpha if given, otherwise keep the original
    a = alpha if alpha is not None else a
    
    color.setRgbF(r, g, b, a)
    return color.name(QColor.HexArgb)

def get_icon(icon_name, opacity=1.0, size=24):
    package_dir = Path(__file__).parent
    icon_path = package_dir / 'ft_picker_icons' / icon_name
    if icon_path.exists():
        icon_pixmap = QtGui.QPixmap(str(icon_path))
        icon_pixmap = icon_pixmap.scaled(size, size, QtCore.Qt.KeepAspectRatio)
        
        if opacity < 1.0:
            transparent_pixmap = QtGui.QPixmap(icon_pixmap.size())
            transparent_pixmap.fill(QtCore.Qt.transparent)
            
            painter = QtGui.QPainter(transparent_pixmap)
            painter.setOpacity(opacity)
            painter.drawPixmap(0, 0, icon_pixmap)
            painter.end()
            
            return transparent_pixmap
        
        return icon_pixmap
    return None
    
def maya_main_window():
    main_window_ptr = omui.MQtUtil.mainWindow()
    return wrapInstance(int(main_window_ptr), QtWidgets.QWidget)