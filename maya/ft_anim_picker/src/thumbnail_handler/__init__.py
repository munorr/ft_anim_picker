"""
Thumbnail Handler – Auto-register .bpicker file type with OS file managers.

On first startup:
  - macOS: Creates a minimal .app bundle declaring the .bpicker UTI with a
    branded icon, registers it with Launch Services.
  - Windows: Writes registry entries associating .bpicker with a branded icon.

After each save:
  - Composites the picker preview image with the BGEN logo badge and sets it
    as the file's custom icon (Finder on macOS, Explorer on Windows).
"""

import os
import sys
import platform
import threading

# Version bump this when the handler format changes to force re-install
_HANDLER_VERSION = "1"

_FLAG_DIR = os.path.join(os.path.expanduser("~"), ".bgen_picker")
_FLAG_FILE = os.path.join(_FLAG_DIR, f"thumbnail_handler_v{_HANDLER_VERSION}.flag")


def _icons_dir():
    """Return the path to the bgen_picker_icons directory."""
    return os.path.join(os.path.dirname(os.path.dirname(__file__)), "bgen_picker_icons")


def _file_icon_path():
    """Return the path to the default bpicker_file_icon.png."""
    return os.path.join(_icons_dir(), "bpicker_file_icon.png")


def _logo_badge_path():
    """Return the path to the small logo badge for compositing."""
    # Use the 64px logo as the badge overlay
    path = os.path.join(_icons_dir(), "ftap_logo_64.png")
    if os.path.exists(path):
        return path
    # Fallback: try the bgen picker icon
    for name in ("bgen-picker-icon-02.png", "bgen-picker-icon-01.png"):
        path = os.path.join(_icons_dir(), name)
        if os.path.exists(path):
            return path
    return None


def is_installed():
    """Check whether the thumbnail handler has already been installed."""
    return os.path.exists(_FLAG_FILE)


def _mark_installed():
    """Write the flag file to indicate successful installation."""
    os.makedirs(_FLAG_DIR, exist_ok=True)
    with open(_FLAG_FILE, "w") as f:
        f.write("installed")


def ensure_installed():
    """Install the OS thumbnail handler if not already done.

    Safe to call on every startup – returns immediately if already installed.
    Runs the actual installation in a background thread to avoid blocking
    the UI on startup.
    """
    if is_installed():
        return

    def _install():
        system = platform.system()
        success = False
        try:
            if system == "Darwin":
                from . import macos_handler
                success = macos_handler.install(
                    file_icon_png=_file_icon_path(),
                )
            elif system == "Windows":
                from . import windows_handler
                success = windows_handler.install(
                    file_icon_png=_file_icon_path(),
                )
            else:
                return  # Linux – no standard thumbnail API
        except Exception as e:
            print(f"[BGEN Picker] Thumbnail handler install failed: {e}")
            return

        if success:
            _mark_installed()
            print("[BGEN Picker] .bpicker file type registered with OS.")

    thread = threading.Thread(target=_install, daemon=True)
    thread.start()


def set_file_icon(bpicker_path, preview_pixmap=None):
    """Set a per-file custom icon on a .bpicker file.

    Args:
        bpicker_path: Absolute path to the .bpicker file.
        preview_pixmap: Optional QPixmap of the canvas preview. If None,
            the preview is extracted from the archive's cache/preview.png.
    """
    system = platform.system()
    try:
        if system == "Darwin":
            from . import macos_handler
            macos_handler.set_file_icon(
                bpicker_path,
                preview_pixmap=preview_pixmap,
                badge_path=_logo_badge_path(),
                fallback_icon=_file_icon_path(),
            )
        elif system == "Windows":
            from . import windows_handler
            windows_handler.set_file_icon(
                bpicker_path,
                preview_pixmap=preview_pixmap,
                badge_path=_logo_badge_path(),
                fallback_icon=_file_icon_path(),
            )
    except Exception as e:
        print(f"[BGEN Picker] set_file_icon failed: {e}")


def uninstall():
    """Remove the OS thumbnail handler registration.

    Useful for addon uninstall or troubleshooting.
    """
    system = platform.system()
    try:
        if system == "Darwin":
            from . import macos_handler
            macos_handler.uninstall()
        elif system == "Windows":
            from . import windows_handler
            windows_handler.uninstall()
    except Exception as e:
        print(f"[BGEN Picker] Thumbnail handler uninstall failed: {e}")

    if os.path.exists(_FLAG_FILE):
        os.remove(_FLAG_FILE)
    print("[BGEN Picker] Thumbnail handler uninstalled.")
