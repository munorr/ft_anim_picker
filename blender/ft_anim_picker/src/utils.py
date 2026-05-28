import bpy
from functools import wraps
from pathlib import Path

from PySide6 import QtWidgets, QtCore, QtGui
from PySide6.QtGui import QColor, QIcon, QPainter
from PySide6.QtCore import Qt, QTimer, QPropertyAnimation, QEasingCurve
from shiboken6 import wrapInstance

# Blender 5.0+ compatibility: bone selection API changed
# In Blender 5.0+, bone.select is removed from Bone objects
# Selection is now on PoseBone.select instead of PoseBone.bone.select
BLENDER_5_0_OR_LATER = bpy.app.version >= (5, 0, 0)


def picker_window_flags(always_on_top=False):
    """Return platform-appropriate Qt window flags for picker windows.

    On macOS, uses Qt.Tool so windows float with Blender naturally.
    On Windows/Linux, uses Qt.Window with WindowStaysOnTopHint.
    """
    import sys
    if sys.platform == "darwin":
        flags = QtCore.Qt.Tool | QtCore.Qt.FramelessWindowHint
    else:
        flags = QtCore.Qt.Window | QtCore.Qt.FramelessWindowHint | QtCore.Qt.WindowStaysOnTopHint
    if always_on_top:
        flags |= QtCore.Qt.WindowStaysOnTopHint
    return flags


def is_bone_selected(pose_bone):
    """
    Get the selection state of a pose bone, compatible with Blender 4.x and 5.0+.
    
    In Blender < 5.0: pose_bone.bone.select
    In Blender 5.0+: pose_bone.select
    
    Args:
        pose_bone: A PoseBone object from armature.pose.bones
        
    Returns:
        bool: True if the bone is selected, False otherwise
    """
    if BLENDER_5_0_OR_LATER:
        return pose_bone.select
    else:
        return pose_bone.bone.select


def set_bone_selected(pose_bone, selected):
    """
    Set the selection state of a pose bone, compatible with Blender 4.x and 5.0+.
    
    In Blender < 5.0: pose_bone.bone.select = value
    In Blender 5.0+: pose_bone.select = value
    
    Args:
        pose_bone: A PoseBone object from armature.pose.bones
        selected: bool - True to select, False to deselect
    """
    if BLENDER_5_0_OR_LATER:
        pose_bone.select = selected
    else:
        pose_bone.bone.select = selected


def get_selected_bone_names(armature_obj):
    """
    Get the names of all selected bones in an armature, compatible with Blender 4.x and 5.0+.
    
    Args:
        armature_obj: An armature object (bpy.types.Object with type='ARMATURE')
        
    Returns:
        list: List of bone names that are selected
    """
    if not armature_obj or armature_obj.type != 'ARMATURE':
        return []
    
    if BLENDER_5_0_OR_LATER:
        # In Blender 5.0+, use pose bone's select property
        if armature_obj.pose:
            return [pb.name for pb in armature_obj.pose.bones if pb.select]
        return []
    else:
        # In Blender < 5.0, use data.bones[].select
        return [bone.name for bone in armature_obj.data.bones if bone.select]


def undoable(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        # Start an undo block using Blender's context manager
        # This is more reliable than bpy.ops.ed.undo_push which requires specific context
        with bpy.context.temp_override(window=bpy.context.window_manager.windows[0]):
            # Create an undo step with a meaningful name
            bpy.ops.ed.undo_push(message=f"BGEN Picker: {func.__name__}")
            
        try:
            # Execute the function
            result = func(*args, **kwargs)
            
            # Update the viewport
            if bpy.context.screen:
                for area in bpy.context.screen.areas:
                    if area.type == 'VIEW_3D':
                        area.tag_redraw()
            
            return result
        except Exception as e:
            # If there's an error, attempt to undo if possible
            try:
                with bpy.context.temp_override(window=bpy.context.window_manager.windows[0]):
                    bpy.ops.ed.undo()
            except:
                print(f"Failed to undo after error in {func.__name__}")
            
            # Re-raise the original exception
            raise e
    
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
            # Parse "rgba(r, g, b, a)" or "rgb(r, g, b)"
            inner = s.split('(', 1)[1].rstrip(')')
            parts = [p.strip() for p in inner.split(',')]
            r, g, b = int(parts[0]), int(parts[1]), int(parts[2])
            if len(parts) == 4:
                a_val = float(parts[3])
                # If alpha is 0-1 float, convert to 0-255
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

def icon_render(icon_path: Path, opacity: float = 0.5, size: int = 10):
        """Create an icon with specified opacity"""
        # Load original pixmap
        pixmap = QtGui.QPixmap(str(icon_path))
        
        # Scale to desired size
        pixmap = pixmap.scaled(size, size, Qt.AspectRatioMode.KeepAspectRatio, 
                            Qt.TransformationMode.SmoothTransformation)
        
        # Create transparent version
        transparent_pixmap = QtGui.QPixmap(pixmap.size())
        transparent_pixmap.fill(Qt.GlobalColor.transparent)
        
        painter = QPainter(transparent_pixmap)
        painter.setOpacity(opacity)  # Set opacity here (0.0 to 1.0)
        painter.drawPixmap(0, 0, pixmap)
        painter.end()
        
        return QIcon(transparent_pixmap)
        
def get_icon(icon_name, opacity=1.0, size=24):
    package_dir = Path(__file__).parent
    icon_path = package_dir / 'bgen_picker_icons' / icon_name
    if icon_path.exists():
        icon_pixmap = QtGui.QPixmap(str(icon_path))
        icon_pixmap = icon_pixmap.scaled(size, size, QtCore.Qt.KeepAspectRatio, QtCore.Qt.SmoothTransformation)
        
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
#----------------------------------------------------------------------------------------------------------
import os
import sys
import subprocess
import ctypes
from ctypes import wintypes
import time
#----------------------------------------------------------------------------------------------------------
def blender_main_window():
    """Cross-platform method to focus Blender window"""
    system = sys.platform
    
    if system == "win32":
        return _focus_blender_windows()
    elif system == "darwin":
        return _focus_blender_macos()
    elif system.startswith("linux"):
        return _focus_blender_linux()
    else:
        print(f"Unsupported platform: {system}")
        return False

def _focus_blender_windows():
    """Windows implementation using Win32 API"""
    try:
        current_pid = os.getpid()
        
        def enum_windows_proc(hwnd, lParam):
            if ctypes.windll.user32.IsWindowVisible(hwnd):
                # Check 1: Process ID match
                process_id = wintypes.DWORD()
                ctypes.windll.user32.GetWindowThreadProcessId(hwnd, ctypes.byref(process_id))
                
                if process_id.value == current_pid:
                    # Check 2: Window title contains Blender
                    length = ctypes.windll.user32.GetWindowTextLengthW(hwnd)
                    if length > 0:
                        buffer = ctypes.create_unicode_buffer(length + 1)
                        ctypes.windll.user32.GetWindowTextW(hwnd, buffer, length + 1)
                        title = buffer.value
                        
                        # Check 3: Window class is Blender's
                        class_buffer = ctypes.create_unicode_buffer(256)
                        ctypes.windll.user32.GetClassNameW(hwnd, class_buffer, 256)
                        class_name = class_buffer.value
                        
                        if ("Blender" in title and 
                            class_name == "GHOST_WindowClass"):  # Blender's specific window class
                            ctypes.windll.user32.SetForegroundWindow(hwnd)
                            #print(f"Focused Blender window: {title}")
                            return False
            return True
        
        EnumWindowsProc = ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)
        ctypes.windll.user32.EnumWindows(EnumWindowsProc(enum_windows_proc), 0)
        return True
        
    except Exception as e:
        print(f"Error focusing window on Windows: {e}")
        return False

def _focus_blender_macos():
    """macOS: Use ObjC runtime via ctypes to make Blender's window the key window.

    The picker and Blender are both windows in the same process, so making the
    process frontmost (AppleScript) doesn't change which window has keyboard focus.
    Instead, we find Blender's NSWindow and call makeKeyAndOrderFront: on it.
    The picker stays visually on top (NSFloatingWindowLevel via WindowStaysOnTopHint)
    while Blender's window (NSNormalWindowLevel) becomes the key window receiving
    keyboard input — standard macOS floating palette behavior.
    """
    try:
        import ctypes
        import ctypes.util

        lib = ctypes.cdll.LoadLibrary(ctypes.util.find_library('objc'))

        lib.objc_getClass.restype = ctypes.c_void_p
        lib.objc_getClass.argtypes = [ctypes.c_char_p]
        lib.sel_registerName.restype = ctypes.c_void_p
        lib.sel_registerName.argtypes = [ctypes.c_char_p]

        def msg(obj, sel_name, *args, res=ctypes.c_void_p, extra_types=None):
            lib.objc_msgSend.restype = res
            lib.objc_msgSend.argtypes = [ctypes.c_void_p, ctypes.c_void_p] + (extra_types or [])
            return lib.objc_msgSend(obj, lib.sel_registerName(sel_name.encode()), *args)

        # NSApp = [NSApplication sharedApplication]
        NSApp = msg(lib.objc_getClass(b'NSApplication'), 'sharedApplication')

        # windows = [NSApp windows]
        windows = msg(NSApp, 'windows')
        count = msg(windows, 'count', res=ctypes.c_uint64)

        for i in range(count):
            win = msg(windows, 'objectAtIndex:', ctypes.c_uint64(i), extra_types=[ctypes.c_uint64])
            title_ns = msg(win, 'title')
            if not title_ns:
                continue
            title_bytes = msg(title_ns, 'UTF8String', res=ctypes.c_char_p)
            if not title_bytes:
                continue
            title = title_bytes.decode('utf-8', errors='ignore')

            if 'Blender' in title or '.blend' in title:
                msg(win, 'makeKeyAndOrderFront:', ctypes.c_void_p(0), extra_types=[ctypes.c_void_p])
                return True

        return False

    except Exception as e:
        print(f"Error focusing Blender on macOS: {e}")
        return _focus_blender_macos_applescript()


def make_picker_key_window(widget):
    """Cross-platform: make the given picker QWidget the OS-level key/active
    window. On macOS this uses ObjC to call -[NSWindow makeKeyAndOrderFront:]
    on the picker's underlying NSWindow, which is the only reliable way to
    reclaim key window status from Blender after a bpy.ops call has handed
    it to Blender's GHOST. On other platforms this falls back to Qt's
    activateWindow().
    """
    if widget is None:
        return False
    system = sys.platform
    if system == "darwin":
        return _make_picker_key_window_macos(widget)
    try:
        widget.window().raise_()
        widget.window().activateWindow()
        return True
    except Exception:
        return False


def _make_picker_key_window_macos(widget):
    """macOS: makeKeyAndOrderFront: on the picker's NSWindow.

    QWidget.winId() returns an NSView* on macOS. We get the enclosing
    NSWindow via [view window] and call makeKeyAndOrderFront: on it.
    This bypasses Qt's activateWindow() (which Blender's GHOST overrides
    at the NSEvent layer) and goes straight to AppKit.
    """
    try:
        import ctypes
        import ctypes.util

        view_id = int(widget.window().winId())
        if not view_id:
            return False

        lib = ctypes.cdll.LoadLibrary(ctypes.util.find_library('objc'))
        lib.objc_getClass.restype = ctypes.c_void_p
        lib.objc_getClass.argtypes = [ctypes.c_char_p]
        lib.sel_registerName.restype = ctypes.c_void_p
        lib.sel_registerName.argtypes = [ctypes.c_char_p]

        def msg(obj, sel_name, *args, res=ctypes.c_void_p, extra_types=None):
            lib.objc_msgSend.restype = res
            lib.objc_msgSend.argtypes = [ctypes.c_void_p, ctypes.c_void_p] + (extra_types or [])
            return lib.objc_msgSend(obj, lib.sel_registerName(sel_name.encode()), *args)

        # window = [view window]
        ns_window = msg(ctypes.c_void_p(view_id), 'window')
        if not ns_window:
            return False

        # [window makeKeyAndOrderFront:nil]
        msg(ns_window, 'makeKeyAndOrderFront:', ctypes.c_void_p(0),
            extra_types=[ctypes.c_void_p])
        return True
    except Exception as e:
        print(f"Error making picker key window on macOS: {e}")
        return False


def _focus_blender_macos_applescript():
    """Fallback: AppleScript approach (may not transfer keyboard focus between same-process windows)."""
    try:
        applescript = '''
        tell application "System Events"
            set blenderApps to (every process whose name contains "Blender")
            if (count of blenderApps) > 0 then
                set frontmost of first item of blenderApps to true
                return true
            else
                return false
            end if
        end tell
        '''
        result = subprocess.run(
            ['osascript', '-e', applescript],
            capture_output=True, text=True, timeout=5
        )
        return result.returncode == 0 and "true" in result.stdout
    except Exception:
        return False

def _focus_blender_linux():
    """Linux implementation using wmctrl and xdotool"""
    try:
        # Method 1: Try wmctrl (more reliable if available)
        if _command_exists('wmctrl'):
            result = subprocess.run(
                ['wmctrl', '-l'],
                capture_output=True,
                text=True,
                timeout=5
            )
            
            if result.returncode == 0:
                lines = result.stdout.strip().split('\n')
                for line in lines:
                    if 'Blender' in line:
                        # Extract window ID (first column)
                        window_id = line.split()[0]
                        # Activate the window
                        subprocess.run(['wmctrl', '-ia', window_id], timeout=5)
                        #print(f"Focused Blender window on Linux: {line.strip()}")
                        return True
        
        # Method 2: Try xdotool as fallback
        if _command_exists('xdotool'):
            result = subprocess.run(
                ['xdotool', 'search', '--name', 'Blender'],
                capture_output=True,
                text=True,
                timeout=5
            )
            
            if result.returncode == 0 and result.stdout.strip():
                window_ids = result.stdout.strip().split('\n')
                for window_id in window_ids:
                    if window_id:
                        # Activate the window
                        subprocess.run(['xdotool', 'windowactivate', window_id], timeout=5)
                        #print(f"Focused Blender window on Linux (xdotool): {window_id}")
                        return True
        
        # Method 3: Try xprop + xdotool combination
        if _command_exists('xprop') and _command_exists('xdotool'):
            result = subprocess.run(
                ['xdotool', 'search', '--class', 'Blender'],
                capture_output=True,
                text=True,
                timeout=5
            )
            
            if result.returncode == 0 and result.stdout.strip():
                window_ids = result.stdout.strip().split('\n')
                for window_id in window_ids:
                    if window_id:
                        subprocess.run(['xdotool', 'windowactivate', window_id], timeout=5)
                        #print(f"Focused Blender window on Linux (class search): {window_id}")
                        return True
        
        print("No Blender windows found on Linux or required tools not available")
        print("Install wmctrl or xdotool for better window management: sudo apt install wmctrl xdotool")
        return False
        
    except subprocess.TimeoutExpired:
        print("Timeout while trying to focus Blender on Linux")
        return False
    except Exception as e:
        print(f"Error focusing window on Linux: {e}")
        return False

def _command_exists(command):
    """Check if a command exists in the system PATH"""
    try:
        subprocess.run(
            ['which', command],
            capture_output=True,
            check=True,
            timeout=2
        )
        return True
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, FileNotFoundError):
        return False
#----------------------------------------------------------------------------------------------------------
def get_blender_windows_info():
    """Get information about Blender windows for debugging"""
    system = sys.platform
    
    if system == "win32":
        return _get_windows_info_windows()
    elif system == "darwin":
        return _get_windows_info_macos()
    elif system.startswith("linux"):
        return _get_windows_info_linux()
    else:
        return f"Unsupported platform: {system}"

def _get_windows_info_windows():
    """Get Blender window info on Windows"""
    try:
        current_pid = os.getpid()
        windows_info = []
        
        def enum_windows_proc(hwnd, lParam):
            if ctypes.windll.user32.IsWindowVisible(hwnd):
                process_id = wintypes.DWORD()
                ctypes.windll.user32.GetWindowThreadProcessId(hwnd, ctypes.byref(process_id))
                
                length = ctypes.windll.user32.GetWindowTextLengthW(hwnd)
                if length > 0:
                    buffer = ctypes.create_unicode_buffer(length + 1)
                    ctypes.windll.user32.GetWindowTextW(hwnd, buffer, length + 1)
                    title = buffer.value
                    
                    class_buffer = ctypes.create_unicode_buffer(256)
                    ctypes.windll.user32.GetClassNameW(hwnd, class_buffer, 256)
                    class_name = class_buffer.value
                    
                    if "Blender" in title or class_name == "GHOST_WindowClass":
                        windows_info.append({
                            'hwnd': hwnd,
                            'pid': process_id.value,
                            'title': title,
                            'class': class_name,
                            'is_current_process': process_id.value == current_pid
                        })
            return True
        
        EnumWindowsProc = ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)
        ctypes.windll.user32.EnumWindows(EnumWindowsProc(enum_windows_proc), 0)
        
        return windows_info
        
    except Exception as e:
        return f"Error getting window info: {e}"

def _get_windows_info_macos():
    """Get Blender window info on macOS"""
    try:
        applescript = '''
        tell application "System Events"
            set blenderProcesses to (every process whose name contains "Blender")
            set processInfo to {}
            repeat with proc in blenderProcesses
                set procWindows to windows of proc
                repeat with win in procWindows
                    set end of processInfo to {name of proc, name of win}
                end repeat
            end repeat
            return processInfo
        end tell
        '''
        
        result = subprocess.run(
            ['osascript', '-e', applescript],
            capture_output=True,
            text=True,
            timeout=5
        )
        
        return result.stdout if result.returncode == 0 else f"Error: {result.stderr}"
        
    except Exception as e:
        return f"Error getting window info: {e}"

def _get_windows_info_linux():
    """Get Blender window info on Linux"""
    try:
        info = []
        
        if _command_exists('wmctrl'):
            result = subprocess.run(
                ['wmctrl', '-l'],
                capture_output=True,
                text=True,
                timeout=5
            )
            
            if result.returncode == 0:
                lines = result.stdout.strip().split('\n')
                for line in lines:
                    if 'Blender' in line:
                        info.append(f"wmctrl: {line}")
        
        if _command_exists('xdotool'):
            result = subprocess.run(
                ['xdotool', 'search', '--name', 'Blender'],
                capture_output=True,
                text=True,
                timeout=5
            )
            
            if result.returncode == 0:
                window_ids = result.stdout.strip().split('\n')
                for window_id in window_ids:
                    if window_id:
                        info.append(f"xdotool: Window ID {window_id}")
        
        return info if info else "No Blender windows found"
        
    except Exception as e:
        return f"Error getting window info: {e}"


def parse_version(version_string):
    """Parse version string into comparable tuple of ints.  '2.3.0' → (2,3,0)"""
    import re
    version = str(version_string).strip().lstrip('v')
    numbers = re.findall(r'\d+', version)
    return tuple(map(int, numbers)) if numbers else (0,)


def is_version_less_than(version_a, version_b):
    """Return True if version_a < version_b."""
    return parse_version(version_a) < parse_version(version_b)


# =============================================================================
# CROSS-PLATFORM MENU & WINDOW STYLING
# =============================================================================

_DARK_MENU_STYLESHEET = '''
    QMenu {
        background-color: rgba(30, 30, 30, 230);
        color: #ffffff;
        border: 1px solid #444444;
        border-radius: 3px;
        padding: 5px 7px;
    }
    QMenu::item {
        background-color: transparent;
        color: #ffffff;
        padding: 3px 30px 3px 3px;
        margin: 3px 0px;
        border-radius: 3px;
    }
    QMenu::item:hover {
        background-color: #444444;
    }
    QMenu::item:selected {
        background-color: #444444;
    }
    QMenu::item:disabled {
        color: #888888;
    }
    QMenu::right-arrow {
        width: 10px;
        height: 10px;
    }
    QPushButton {
        border-radius: 3px;
        background-color: #333333;
        color: #ffffff;
    }
    QPushButton:hover {
        background-color: #444444;
    }
'''


def _apply_dark_palette(widget):
    """Apply a dark QPalette to a widget as a fallback for when QSS fails.

    On some systems (certain Windows GPU drivers, Linux compositors without
    translucency support), Qt stylesheets may not cascade correctly and the
    OS theme can override text colors to black. QPalette applies at the Qt
    level and is more reliable cross-platform than QSS alone.
    """
    palette = widget.palette()
    palette.setColor(QtGui.QPalette.Window, QtGui.QColor(30, 30, 30, 230))
    palette.setColor(QtGui.QPalette.WindowText, QtGui.QColor(255, 255, 255))
    palette.setColor(QtGui.QPalette.Base, QtGui.QColor(30, 30, 30, 230))
    palette.setColor(QtGui.QPalette.Text, QtGui.QColor(255, 255, 255))
    palette.setColor(QtGui.QPalette.Button, QtGui.QColor(51, 51, 51))
    palette.setColor(QtGui.QPalette.ButtonText, QtGui.QColor(255, 255, 255))
    palette.setColor(QtGui.QPalette.Highlight, QtGui.QColor(68, 68, 68))
    palette.setColor(QtGui.QPalette.HighlightedText, QtGui.QColor(255, 255, 255))
    widget.setPalette(palette)


def create_styled_menu(parent=None, title=None, stylesheet=None):
    """Create a QMenu with cross-platform-safe dark styling.

    Uses QPalette as a fallback for systems where QSS color does not
    propagate correctly.

    Args:
        parent: Optional parent widget.
        title: Optional menu title (for submenus).
        stylesheet: Optional custom stylesheet override. If None, uses
            the standard dark menu stylesheet.
    """
    if title:
        menu = QtWidgets.QMenu(title, parent)
    else:
        menu = QtWidgets.QMenu(parent)

    menu.setWindowFlags(
        menu.windowFlags()
        | QtCore.Qt.FramelessWindowHint
        | QtCore.Qt.NoDropShadowWindowHint
    )
    menu.setAttribute(QtCore.Qt.WA_TranslucentBackground)

    _apply_dark_palette(menu)
    menu.setStyleSheet(stylesheet if stylesheet else _DARK_MENU_STYLESHEET)

    return menu


def apply_dark_window_flags(widget):
    """Apply frameless + no-shadow flags and palette fallback to any widget.

    For non-QMenu widgets (dialogs, tooltips, custom popups) that need the
    same dark frameless styling.
    """
    widget.setWindowFlags(
        widget.windowFlags()
        | QtCore.Qt.FramelessWindowHint
        | QtCore.Qt.NoDropShadowWindowHint
    )
    widget.setAttribute(QtCore.Qt.WA_TranslucentBackground)
    _apply_dark_palette(widget)
