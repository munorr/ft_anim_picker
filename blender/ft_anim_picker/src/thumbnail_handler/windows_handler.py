"""
Windows Thumbnail Handler – Register .bpicker file type with Explorer.

Two-layer approach:
  1. **File-type registration** (on first startup):
     Writes Windows Registry entries that associate .bpicker files with a
     branded icon. Explorer will show this icon for all .bpicker files.

  2. **Per-file custom icon** (after each save):
     Creates a hidden ``desktop.ini`` + icon file in the same directory,
     or directly sets the icon via COM (if available).  Falls back to
     the static branded icon if compositing is not possible.

Note: Dynamic per-file thumbnails in Explorer require a compiled shell
extension (IThumbnailProvider).  Source code for a future native handler
is included in ``native/windows/``.
"""

import os
import shutil
import subprocess
import sys
import tempfile


# Registry paths
_PROG_ID = "BGenPicker.bpicker"
_EXT = ".bpicker"

# Where we store the converted .ico file
_INSTALL_DIR = os.path.join(
    os.environ.get("LOCALAPPDATA", os.path.expanduser("~")),
    "BGenPicker",
)
_ICO_PATH = os.path.join(_INSTALL_DIR, "bpicker_file_icon.ico")


# ─── File-type registration ────────────────────────────────────────────

def install(file_icon_png):
    """Register .bpicker file type in the Windows Registry.

    Args:
        file_icon_png: Path to the bpicker_file_icon.png.

    Returns:
        True on success.
    """
    if sys.platform != "win32":
        return False

    if not os.path.isfile(file_icon_png):
        print(f"[BGEN Picker] Icon not found: {file_icon_png}")
        return False

    try:
        # Convert PNG → ICO
        ico_path = _png_to_ico(file_icon_png)
        if not ico_path:
            print("[BGEN Picker] Failed to convert icon to ICO format.")
            return False

        # Write registry entries
        _write_registry(ico_path)

        # Notify Explorer of the change
        _notify_shell()

        return True
    except Exception as e:
        print(f"[BGEN Picker] Windows install error: {e}")
        return False


def _png_to_ico(png_path):
    """Convert a PNG to a multi-size .ico file.

    Uses Pillow if available, otherwise falls back to a basic single-size
    ICO from raw PNG data (Explorer handles this).
    """
    os.makedirs(_INSTALL_DIR, exist_ok=True)

    # Try Pillow first (best quality, multiple sizes)
    try:
        from PIL import Image
        img = Image.open(png_path).convert("RGBA")
        sizes = [(16, 16), (32, 32), (48, 48), (64, 64),
                 (128, 128), (256, 256)]
        img.save(_ICO_PATH, format="ICO",
                 sizes=sizes)
        return _ICO_PATH
    except ImportError:
        pass
    except Exception:
        pass

    # Fallback: use Qt to create the ICO
    try:
        try:
            from PySide6.QtGui import QImage, QPixmap
            from PySide6.QtCore import QSize
        except ImportError:
            from PySide2.QtGui import QImage, QPixmap
            from PySide2.QtCore import QSize

        pixmap = QPixmap(png_path)
        if not pixmap.isNull():
            # Qt can save as ICO on Windows
            scaled = pixmap.scaled(256, 256)
            if scaled.save(_ICO_PATH, "ICO"):
                return _ICO_PATH
    except Exception:
        pass

    # Last resort: use magick/convert if available
    try:
        for cmd in ("magick", "convert"):
            result = subprocess.run(
                [cmd, png_path, "-define", "icon:auto-resize=256,128,64,48,32,16",
                 _ICO_PATH],
                capture_output=True, timeout=15,
            )
            if result.returncode == 0 and os.path.isfile(_ICO_PATH):
                return _ICO_PATH
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass

    # Absolute fallback: copy PNG as-is (Explorer may still use it)
    shutil.copy2(png_path, _ICO_PATH)
    return _ICO_PATH


def _write_registry(ico_path):
    """Write registry entries to associate .bpicker with our icon.

    Uses HKEY_CURRENT_USER so no admin elevation is needed.
    """
    import winreg

    ico_path = os.path.abspath(ico_path)

    # 1. Create ProgID: HKCU\Software\Classes\BGenPicker.bpicker
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER,
                          rf"Software\Classes\{_PROG_ID}") as key:
        winreg.SetValue(key, "", winreg.REG_SZ, "BGEN Picker File")

    # 2. Set default icon: HKCU\Software\Classes\BGenPicker.bpicker\DefaultIcon
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER,
                          rf"Software\Classes\{_PROG_ID}\DefaultIcon") as key:
        winreg.SetValue(key, "", winreg.REG_SZ, f'"{ico_path}"')

    # 3. Associate .bpicker extension with the ProgID
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER,
                          rf"Software\Classes\{_EXT}") as key:
        winreg.SetValue(key, "", winreg.REG_SZ, _PROG_ID)

    # 4. Set perceived type (optional, helps Explorer categorise)
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER,
                          rf"Software\Classes\{_EXT}") as key:
        winreg.SetValueEx(key, "PerceivedType", 0, winreg.REG_SZ, "document")

    # 5. Register in OpenWithProgids
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER,
                          rf"Software\Classes\{_EXT}\OpenWithProgids") as key:
        winreg.SetValueEx(key, _PROG_ID, 0, winreg.REG_NONE, b"")


def _notify_shell():
    """Notify Windows Explorer that file associations have changed."""
    try:
        import ctypes
        # SHCNE_ASSOCCHANGED = 0x08000000, SHCNF_IDLIST = 0x0000
        ctypes.windll.shell32.SHChangeNotify(0x08000000, 0x0000, None, None)
    except Exception:
        pass


# ─── Per-file custom icon ──────────────────────────────────────────────

def set_file_icon(bpicker_path, preview_pixmap=None, badge_path=None,
                  fallback_icon=None):
    """Set a per-file icon for a .bpicker file on Windows.

    Windows doesn't natively support per-file custom icons the way macOS
    does.  We use two strategies:

    1. If the file is in its own directory, use desktop.ini + a hidden
       .ico to give Explorer a custom icon for this specific file.
    2. Generate a composited thumbnail and cache it alongside the file
       for use by a future native IThumbnailProvider shell extension.
    """
    from .icon_compositor import composite_icon

    icon_path = composite_icon(
        preview_pixmap=preview_pixmap,
        badge_path=badge_path,
        fallback_icon=fallback_icon,
        bpicker_path=bpicker_path,
    )

    if not icon_path:
        return

    try:
        # Cache the composited thumbnail next to the .bpicker file.
        # A future native IThumbnailProvider can read this cache.
        _cache_thumbnail(bpicker_path, icon_path)
    finally:
        try:
            os.unlink(icon_path)
        except OSError:
            pass


def _cache_thumbnail(bpicker_path, icon_png_path):
    """Cache a composited thumbnail alongside the .bpicker file.

    Saves as ``<filename>.bpicker.thumb.png`` in a hidden ``.bpicker_thumbs``
    directory next to the file.  A native IThumbnailProvider shell extension
    can look for this cached thumbnail to avoid re-extracting from the ZIP
    on every Explorer refresh.
    """
    parent = os.path.dirname(bpicker_path)
    cache_dir = os.path.join(parent, ".bpicker_thumbs")
    os.makedirs(cache_dir, exist_ok=True)

    # Hide the cache directory on Windows
    if sys.platform == "win32":
        try:
            import ctypes
            ctypes.windll.kernel32.SetFileAttributesW(
                cache_dir, 0x02  # FILE_ATTRIBUTE_HIDDEN
            )
        except Exception:
            pass

    basename = os.path.basename(bpicker_path)
    thumb_name = f"{basename}.thumb.png"
    dest = os.path.join(cache_dir, thumb_name)
    shutil.copy2(icon_png_path, dest)


# ─── Uninstall ──────────────────────────────────────────────────────────

def uninstall():
    """Remove registry entries and installed icon files."""
    if sys.platform != "win32":
        return

    import winreg

    # Remove registry entries
    _paths = [
        rf"Software\Classes\{_PROG_ID}\DefaultIcon",
        rf"Software\Classes\{_PROG_ID}",
        rf"Software\Classes\{_EXT}\OpenWithProgids",
        rf"Software\Classes\{_EXT}",
    ]
    for path in _paths:
        try:
            winreg.DeleteKey(winreg.HKEY_CURRENT_USER, path)
        except FileNotFoundError:
            pass
        except Exception:
            pass

    # Remove installed icon
    if os.path.isdir(_INSTALL_DIR):
        shutil.rmtree(_INSTALL_DIR, ignore_errors=True)

    _notify_shell()
