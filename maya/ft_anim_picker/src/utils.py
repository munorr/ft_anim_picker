import sys
import os
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
    

def get_module(relative_path, package_name):
    """
    Helper function to handle both relative and absolute imports for Python 2/3 compatibility.
    Args:
        relative_path (str): The relative import path (e.g., '.main')
        package_name (str): The actual module name (e.g., 'main')
    Returns:
        module: The imported module
    """
    try:
        # Python 3 style relative import
        if relative_path.startswith('.'):
            # Remove the leading dot for absolute import fallback
            package_name = relative_path[1:]
        return __import__(relative_path, globals(), locals(), ['*'], 1)
    except (ImportError, ValueError, SystemError):
        # Python 2 fallback - attempt absolute import from the same directory
        current_dir = os.path.dirname(os.path.abspath(__file__))
        if current_dir not in sys.path:
            sys.path.append(current_dir)
        return __import__(package_name)

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

def to_qcolor(color_input):
    """Convert various color formats to a QColor.
    Accepts: hex string, rgb/rgba CSS string, tuple/list of (r,g,b) or (r,g,b,a).
    """
    if isinstance(color_input, QColor):
        return QColor(color_input)
    if isinstance(color_input, (tuple, list)):
        return QColor(*[int(c) for c in color_input])
    if isinstance(color_input, str):
        s = color_input.strip()
        if s.startswith(('rgba(', 'rgb(')):
            inner = s.split('(', 1)[1].rstrip(')')
            parts = [p.strip() for p in inner.split(',')]
            r, g, b = int(parts[0]), int(parts[1]), int(parts[2])
            if len(parts) == 4:
                a_val = float(parts[3])
                if a_val <= 1.0:
                    a_val = int(a_val * 255)
                else:
                    a_val = int(a_val)
                return QColor(r, g, b, a_val)
            return QColor(r, g, b)
    return QColor(color_input)

def rgba_value(hex_color, factor, alpha=None):
    color = to_qcolor(hex_color)
    r, g, b, a = color.getRgbF()
    
    # Apply factor to RGB values
    r = min(max(r * factor, 0), 1)
    g = min(max(g * factor, 0), 1)
    b = min(max(b * factor, 0), 1)
    
    # Use the provided alpha if given, otherwise keep the original
    a = alpha if alpha is not None else a
    
    color.setRgbF(r, g, b, a)
    return color.name(QColor.HexArgb)

def get_icon(icon_name, opacity=1.0, size=24):
    package_dir = Path(__file__).parent
    icon_path = package_dir / 'bgen_picker_icons' / icon_name
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
    return QtGui.QPixmap()

def icon_render(icon_path, opacity=0.5, size=10):
    """Create a QIcon from a file path with specified opacity and size."""
    pixmap = QtGui.QPixmap(str(icon_path))
    pixmap = pixmap.scaled(size, size, QtCore.Qt.KeepAspectRatio,
                           QtCore.Qt.SmoothTransformation)
    transparent_pixmap = QtGui.QPixmap(pixmap.size())
    transparent_pixmap.fill(QtCore.Qt.transparent)
    painter = QtGui.QPainter(transparent_pixmap)
    painter.setOpacity(opacity)
    painter.drawPixmap(0, 0, pixmap)
    painter.end()
    return QtGui.QIcon(transparent_pixmap)

def parse_version(version_string):
    """Parse version string into comparable tuple of ints.  '2.3.0' → (2,3,0)"""
    import re
    version = str(version_string).strip().lstrip('v')
    numbers = re.findall(r'\d+', version)
    return tuple(map(int, numbers)) if numbers else (0,)

def is_version_less_than(version_a, version_b):
    """Return True if version_a < version_b."""
    return parse_version(version_a) < parse_version(version_b)

def maya_main_window():
    main_window_ptr = omui.MQtUtil.mainWindow()
    return wrapInstance(int(main_window_ptr), QtWidgets.QWidget)