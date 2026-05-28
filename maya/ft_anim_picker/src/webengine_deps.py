"""
WebEngine dependency detection and installation for Maya.

Handles the fact that neither Maya 2024 (PySide2) nor Maya 2025+ (PySide6)
bundles QtWebEngineWidgets. Pip-installs the appropriate package:
  - Maya 2025+: PySide6-Addons (adds QtWebEngine to existing PySide6)
  - Maya 2024-: PySide2 (full package from PyPI includes QtWebEngine)
"""

import sys
import importlib

try:
    from PySide6 import QtCore
except ImportError:
    from PySide2 import QtCore


# ---------------------------------------------------------------------------
# Detection
# ---------------------------------------------------------------------------

def detect_maya_version():
    """Return the Maya major version as an int (e.g. 2024, 2025).

    Returns 0 if detection fails (e.g. running outside Maya).
    """
    try:
        import maya.cmds as cmds
        ver_str = cmds.about(version=True)
        # e.g. "2025", "2024.2", "2025 Update 1"
        return int(ver_str.split(".")[0].split()[0])
    except Exception:
        return 0


def check_webengine_available():
    """Return True if QtWebEngineWidgets can be imported."""
    try:
        from PySide6.QtWebEngineWidgets import QWebEngineView  # noqa: F401
        return True
    except ImportError:
        pass
    try:
        from PySide2.QtWebEngineWidgets import QWebEngineView  # noqa: F401
        return True
    except ImportError:
        pass
    return False


def get_install_package():
    """Return the pip package name to install for the current Maya version.

    Maya 2025+ ships PySide6 base -> install PySide6-Addons (contains QtWebEngine).
    Maya 2024 and below ships PySide2 subset -> install full PySide2 from PyPI.
    """
    maya_ver = detect_maya_version()
    if maya_ver >= 2025:
        return "PySide6-Addons"
    return "PySide2"


def get_manual_install_command():
    """Return a shell command the user can run manually to install WebEngine."""
    pkg = get_install_package()
    # Try to find mayapy; fall back to generic instruction
    try:
        import os
        maya_bin = os.path.dirname(sys.executable)
        mayapy = os.path.join(maya_bin, "mayapy")
        if not os.path.exists(mayapy):
            mayapy = os.path.join(maya_bin, "mayapy.exe")
        if os.path.exists(mayapy):
            return f'"{mayapy}" -m pip install {pkg}'
    except Exception:
        pass
    return f"mayapy -m pip install {pkg}"


# ---------------------------------------------------------------------------
# Installation
# ---------------------------------------------------------------------------

def _pip_install(pip_name):
    """Install a package using pip (3-method fallback)."""
    # Method 1: pip.main()
    try:
        import pip
        result = pip.main(["install", pip_name])
        if result == 0:
            return True
    except (AttributeError, TypeError):
        pass

    # Method 2: pip._internal
    try:
        from pip._internal.cli.main import main as pip_main
        result = pip_main(["install", pip_name])
        if result == 0:
            return True
    except (ImportError, SystemExit) as exc:
        if isinstance(exc, SystemExit) and exc.code == 0:
            return True

    # Method 3: ensurepip + runpy
    try:
        import ensurepip
        ensurepip.bootstrap(upgrade=True, default_pip=True)
    except Exception:
        pass
    try:
        import runpy
        saved_argv = sys.argv
        sys.argv = ["pip", "install", pip_name]
        try:
            runpy.run_module("pip", run_name="__main__", alter_sys=True)
            return True
        except SystemExit as exc:
            if exc.code == 0:
                return True
            raise RuntimeError(f"pip install returned code {exc.code}")
        finally:
            sys.argv = saved_argv
    except RuntimeError:
        raise
    except Exception as exc:
        raise RuntimeError(f"All installation methods failed: {exc}")


class WebEngineInstallWorker(QtCore.QThread):
    """Background thread that pip-installs the WebEngine package."""

    progress = QtCore.Signal(str)        # status message
    finished_ok = QtCore.Signal()
    finished_err = QtCore.Signal(str)    # error message

    def run(self):
        pkg = get_install_package()
        self.progress.emit(f"Installing {pkg}...")
        try:
            _pip_install(pkg)
            importlib.invalidate_caches()
            if check_webengine_available():
                self.progress.emit("Installation complete.")
                self.finished_ok.emit()
            else:
                # Installed but import still fails -> needs restart
                self.progress.emit("Installed. Restart Maya to activate.")
                self.finished_ok.emit()
        except Exception as exc:
            self.finished_err.emit(str(exc))


def install_webengine_sync():
    """Blocking install (for use in non-UI contexts). Returns (ok, message)."""
    pkg = get_install_package()
    try:
        _pip_install(pkg)
        importlib.invalidate_caches()
        if check_webengine_available():
            return True, "WebEngine installed successfully."
        return True, "WebEngine installed. Please restart Maya to activate."
    except Exception as exc:
        cmd = get_manual_install_command()
        return False, (
            f"Automatic installation failed: {exc}\n\n"
            f"You can install manually by running:\n{cmd}"
        )
