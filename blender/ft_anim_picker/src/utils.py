import bpy
from functools import wraps
from pathlib import Path

from PySide6 import QtWidgets, QtCore, QtGui
from PySide6.QtGui import QColor
from PySide6.QtCore import QTimer, QPropertyAnimation, QEasingCurve
from shiboken6 import wrapInstance

    

def undoable(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        # Start an undo block using Blender's context manager
        # This is more reliable than bpy.ops.ed.undo_push which requires specific context
        with bpy.context.temp_override(window=bpy.context.window_manager.windows[0]):
            # Create an undo step with a meaningful name
            bpy.ops.ed.undo_push(message=f"FT Anim Picker: {func.__name__}")
            
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
    """macOS implementation using AppleScript"""
    try:
        # Method 1: Try to activate Blender application
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
            capture_output=True,
            text=True,
            timeout=5
        )
        
        if result.returncode == 0 and "true" in result.stdout:
            #print("Focused Blender window on macOS")
            return True
        
        # Method 2: Try alternative approach with specific window
        applescript_alt = '''
        tell application "System Events"
            set blenderWindows to (every window of every process whose name contains "Blender")
            if (count of blenderWindows) > 0 then
                set frontmost of (process of first item of blenderWindows) to true
                return true
            else
                return false
            end if
        end tell
        '''
        
        result = subprocess.run(
            ['osascript', '-e', applescript_alt],
            capture_output=True,
            text=True,
            timeout=5
        )
        
        if result.returncode == 0 and "true" in result.stdout:
            #print("Focused Blender window on macOS (alternative method)")
            return True
            
        print("No Blender windows found on macOS")
        return False
        
    except subprocess.TimeoutExpired:
        print("Timeout while trying to focus Blender on macOS")
        return False
    except Exception as e:
        print(f"Error focusing window on macOS: {e}")
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

    
    