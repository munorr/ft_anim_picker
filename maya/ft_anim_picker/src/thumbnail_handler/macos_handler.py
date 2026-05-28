"""
macOS Thumbnail Handler – Register .bpicker file type with Finder.

Two-layer approach:
  1. **File-type registration** (on first startup):
     Creates a minimal .app bundle that declares a UTI for .bpicker files
     with a branded icon. Registers it via ``lsregister`` so Finder shows
     the icon for every .bpicker file.

  2. **Per-file custom icon** (after each save):
     Composites the canvas preview + logo badge and writes it as the file's
     custom Finder icon using ``NSWorkspace`` via JXA (JavaScript for
     Automation).  This gives each .bpicker file its own unique thumbnail
     in Finder without needing a compiled Quick Look extension.
"""

import os
import plistlib
import shutil
import subprocess
import tempfile


# Where we install the stub .app
_APP_NAME = "BGenPickerFileType.app"
_INSTALL_DIR = os.path.join(
    os.path.expanduser("~"), "Library", "Application Support", "BGenPicker"
)
_APP_PATH = os.path.join(_INSTALL_DIR, _APP_NAME)

# UTI identifier
_UTI = "com.bgen.bpicker"

# lsregister path
_LSREGISTER = (
    "/System/Library/Frameworks/CoreServices.framework"
    "/Versions/A/Frameworks/LaunchServices.framework"
    "/Versions/A/Support/lsregister"
)


# ─── File-type registration ────────────────────────────────────────────

def install(file_icon_png):
    """Create a stub .app declaring the .bpicker UTI and register it.

    Args:
        file_icon_png: Path to the bpicker_file_icon.png.

    Returns:
        True on success.
    """
    if not os.path.isfile(file_icon_png):
        print(f"[BGEN Picker] Icon not found: {file_icon_png}")
        return False

    # Convert PNG → ICNS
    icns_path = _png_to_icns(file_icon_png)
    if not icns_path:
        print("[BGEN Picker] Failed to convert icon to ICNS format.")
        return False

    try:
        _create_stub_app(icns_path)
        _register_app()
        return True
    except Exception as e:
        print(f"[BGEN Picker] macOS install error: {e}")
        return False
    finally:
        # Clean up temp icns
        if icns_path and os.path.exists(icns_path):
            try:
                os.unlink(icns_path)
            except OSError:
                pass


def _png_to_icns(png_path):
    """Convert a PNG to an ICNS file using ``iconutil``.

    Creates a temporary iconset directory with the required sizes,
    then converts to .icns.

    Returns:
        Path to the .icns file, or None on failure.
    """
    try:
        tmp_dir = tempfile.mkdtemp(prefix="bpicker_icns_")
        iconset = os.path.join(tmp_dir, "bpicker.iconset")
        os.makedirs(iconset)

        # Required sizes for iconset: 16, 32, 64, 128, 256, 512, 1024
        sizes = [16, 32, 64, 128, 256, 512]
        for sz in sizes:
            # Standard resolution
            out = os.path.join(iconset, f"icon_{sz}x{sz}.png")
            subprocess.run(
                ["sips", "-z", str(sz), str(sz), png_path,
                 "--out", out],
                capture_output=True, timeout=10,
            )
            # @2x (Retina) – next size up, named at current nominal size
            sz2 = sz * 2
            if sz2 <= 1024:
                out2x = os.path.join(iconset, f"icon_{sz}x{sz}@2x.png")
                subprocess.run(
                    ["sips", "-z", str(sz2), str(sz2), png_path,
                     "--out", out2x],
                    capture_output=True, timeout=10,
                )

        # Convert iconset → icns
        icns_path = os.path.join(tmp_dir, "bpicker.icns")
        result = subprocess.run(
            ["iconutil", "-c", "icns", iconset, "-o", icns_path],
            capture_output=True, timeout=15,
        )

        if result.returncode == 0 and os.path.isfile(icns_path):
            return icns_path

        # Fallback: use sips directly (less ideal but works)
        icns_path2 = os.path.join(tmp_dir, "bpicker_fallback.icns")
        result2 = subprocess.run(
            ["sips", "-s", "format", "icns", png_path, "--out", icns_path2],
            capture_output=True, timeout=10,
        )
        if result2.returncode == 0 and os.path.isfile(icns_path2):
            return icns_path2

        return None
    except Exception:
        return None


def _create_stub_app(icns_path):
    """Create a minimal .app bundle that declares the .bpicker UTI.

    The app has no executable – it exists only to register the file type
    with Launch Services.
    """
    contents = os.path.join(_APP_PATH, "Contents")
    resources = os.path.join(contents, "Resources")
    macos_dir = os.path.join(contents, "MacOS")

    # Clean previous install
    if os.path.exists(_APP_PATH):
        shutil.rmtree(_APP_PATH)

    os.makedirs(resources, exist_ok=True)
    os.makedirs(macos_dir, exist_ok=True)

    # Copy icon
    dest_icns = os.path.join(resources, "bpicker.icns")
    shutil.copy2(icns_path, dest_icns)

    # Create a minimal executable (required for valid .app)
    stub_exec = os.path.join(macos_dir, "BGenPickerFileType")
    with open(stub_exec, "w") as f:
        f.write("#!/bin/sh\nexit 0\n")
    os.chmod(stub_exec, 0o755)

    # Write Info.plist
    plist = {
        "CFBundleIdentifier": "com.bgen.picker.filetype",
        "CFBundleName": "BGEN Picker File Type",
        "CFBundleDisplayName": "BGEN Picker File Type",
        "CFBundleVersion": "1.0",
        "CFBundleShortVersionString": "1.0",
        "CFBundlePackageType": "APPL",
        "CFBundleSignature": "????",
        "CFBundleExecutable": "BGenPickerFileType",
        "CFBundleIconFile": "bpicker",
        "LSMinimumSystemVersion": "10.15",
        "LSBackgroundOnly": True,

        # Declare the .bpicker UTI
        "UTExportedTypeDeclarations": [
            {
                "UTTypeIdentifier": _UTI,
                "UTTypeDescription": "BGEN Picker File",
                "UTTypeConformsTo": ["public.data", "public.composite-content"],
                "UTTypeIconFiles": ["bpicker.icns"],
                "UTTypeTagSpecification": {
                    "public.filename-extension": ["bpicker"],
                    "public.mime-type": "application/x-bpicker",
                },
            }
        ],

        # Associate .bpicker files with this app's icon
        "CFBundleDocumentTypes": [
            {
                "CFBundleTypeExtensions": ["bpicker"],
                "CFBundleTypeIconFile": "bpicker",
                "CFBundleTypeName": "BGEN Picker File",
                "CFBundleTypeRole": "Viewer",
                "LSHandlerRank": "Owner",
                "LSItemContentTypes": [_UTI],
            }
        ],
    }

    plist_path = os.path.join(contents, "Info.plist")
    with open(plist_path, "wb") as f:
        plistlib.dump(plist, f)


def _register_app():
    """Register the stub .app with Launch Services."""
    if not os.path.isdir(_APP_PATH):
        return

    # Register with Launch Services
    if os.path.isfile(_LSREGISTER):
        subprocess.run(
            [_LSREGISTER, "-f", _APP_PATH],
            capture_output=True, timeout=15,
        )

    # Reset Quick Look cache so thumbnails refresh
    subprocess.run(
        ["qlmanage", "-r", "cache"],
        capture_output=True, timeout=10,
    )


# ─── Per-file custom icon ──────────────────────────────────────────────

def set_file_icon(bpicker_path, preview_pixmap=None, badge_path=None,
                  fallback_icon=None):
    """Set a custom Finder icon on a .bpicker file.

    Composites the preview image with the logo badge, then uses
    NSWorkspace (via JXA) to apply it as the file's custom icon.
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
        _apply_finder_icon(bpicker_path, icon_path)
    finally:
        # Clean up temp icon
        try:
            os.unlink(icon_path)
        except OSError:
            pass


def _apply_finder_icon(target_path, icon_png_path):
    """Apply a custom Finder icon to a file using NSWorkspace via JXA.

    JXA (JavaScript for Automation) gives us access to Cocoa frameworks
    without needing pyobjc installed.
    """
    # Escape paths for JavaScript string literals
    icon_escaped = icon_png_path.replace("\\", "\\\\").replace("'", "\\'")
    target_escaped = target_path.replace("\\", "\\\\").replace("'", "\\'")

    script = f"""
    ObjC.import('Cocoa');
    var image = $.NSImage.alloc.initWithContentsOfFile('{icon_escaped}');
    if (image.isNil()) {{
        'FAIL: could not load icon image';
    }} else {{
        var ok = $.NSWorkspace.sharedWorkspace
                    .setIconForFileOptions(image, '{target_escaped}', 0);
        ok ? 'OK' : 'FAIL: setIcon returned false';
    }}
    """

    try:
        result = subprocess.run(
            ["osascript", "-l", "JavaScript", "-e", script],
            capture_output=True, text=True, timeout=10,
        )
        if "FAIL" in (result.stdout or ""):
            print(f"[BGEN Picker] Finder icon: {result.stdout.strip()}")
    except subprocess.TimeoutExpired:
        pass
    except FileNotFoundError:
        # osascript not available
        pass


# ─── Uninstall ──────────────────────────────────────────────────────────

def uninstall():
    """Remove the stub .app and deregister the UTI."""
    if os.path.isdir(_APP_PATH):
        # Deregister
        if os.path.isfile(_LSREGISTER):
            subprocess.run(
                [_LSREGISTER, "-u", _APP_PATH],
                capture_output=True, timeout=10,
            )
        shutil.rmtree(_APP_PATH, ignore_errors=True)

    # Clean up parent dir if empty
    try:
        os.rmdir(_INSTALL_DIR)
    except OSError:
        pass
