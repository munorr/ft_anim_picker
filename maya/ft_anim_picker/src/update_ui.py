"""
Update UI components — UpdateBanner notification and DownloadWorker thread.

The legacy UpdateWidget standalone window has been removed.
UpdatesSection in settings_page.py now uses UpdateManager for all update logic.
"""

import os
import ssl
import sys
import json
import urllib.request
import zipfile
import tempfile
import shutil
from pathlib import Path


def _get_ssl_context():
    """Get an SSL context that works in Maya's bundled Python."""
    try:
        from .supabase_client import _SSL_CTX
        return _SSL_CTX
    except Exception:
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        return ctx


try:
    from PySide6 import QtCore, QtWidgets
    from PySide6.QtCore import Qt, Signal, QThread, QTimer
    from PySide6.QtWidgets import (
        QWidget, QVBoxLayout, QHBoxLayout,
        QPushButton, QLabel, QProgressBar, QFrame,
    )
except ImportError:
    from PySide2 import QtCore, QtWidgets
    from PySide2.QtCore import Qt, Signal, QThread, QTimer
    from PySide2.QtWidgets import (
        QWidget, QVBoxLayout, QHBoxLayout,
        QPushButton, QLabel, QProgressBar, QFrame,
    )


# ---------------------------------------------------------------------------
# DownloadWorker — kept for backward compat (used by old update paths)
# ---------------------------------------------------------------------------

def get_parent_dir():
    script_dir = os.path.normpath(os.path.dirname(os.path.realpath(__file__)))
    script_dir_normalized = script_dir.replace("\\", "/")
    parent_dir = os.path.normpath(os.path.dirname(script_dir))
    parent_dir_normalized = parent_dir.replace("\\", "/")
    return script_dir, script_dir_normalized, parent_dir, parent_dir_normalized


class DownloadWorker(QThread):
    """Worker thread to handle GitHub API requests and downloads."""
    progress_updated = Signal(int)
    status_updated = Signal(str)
    download_complete = Signal(bool, str)
    extract_progress = Signal(int)

    def __init__(self, repo_url, release_tag, download_path, folder_path=None):
        super().__init__()
        self.repo_url = repo_url
        self.release_tag = release_tag
        self.download_path = download_path
        self.folder_path = folder_path

    def run(self):
        try:
            if self.repo_url.endswith('.git'):
                self.repo_url = self.repo_url[:-4]

            parts = self.repo_url.replace('https://github.com/', '').split('/')
            if len(parts) < 2:
                self.status_updated.emit("Error: Invalid GitHub repository URL")
                self.download_complete.emit(False, "Invalid GitHub repository URL")
                return

            owner, repo = parts[0], parts[1]

            self.status_updated.emit(f"Downloading release {self.release_tag}...")
            release_url = f"https://api.github.com/repos/{owner}/{repo}/releases/tags/{self.release_tag}"
            self.status_updated.emit("Fetching release information...")

            headers = {'User-Agent': 'GitReleaseDownloader/1.0'}
            req = urllib.request.Request(release_url, headers=headers)

            with urllib.request.urlopen(req, context=_get_ssl_context()) as response:
                release_data = json.loads(response.read().decode())

            if self.download_path.endswith('.zip') and 'browser_download_url' in self.release_tag:
                download_url = self.release_tag
                asset = {'name': os.path.basename(self.download_path)}
            elif 'assets' not in release_data or not release_data['assets']:
                self.status_updated.emit("No assets found, downloading source code archive...")
                download_url = f"https://github.com/{owner}/{repo}/archive/refs/tags/{self.release_tag}.zip"
                asset = {'name': f"{repo}-{self.release_tag}.zip"}
            else:
                asset = release_data['assets'][0]
                download_url = asset['browser_download_url']

            os.makedirs(os.path.dirname(self.download_path) if os.path.dirname(self.download_path) else '.', exist_ok=True)

            self.status_updated.emit(f"Downloading {asset['name']}...")

            def report_progress(block_count, block_size, total_size):
                if total_size > 0:
                    percent = min(int(block_count * block_size * 100 / total_size), 100)
                    self.progress_updated.emit(percent)

            try:
                _ctx = _get_ssl_context()
                _opener = urllib.request.build_opener(
                    urllib.request.HTTPSHandler(context=_ctx)
                )
                urllib.request.install_opener(_opener)

                if self.folder_path:
                    with tempfile.TemporaryDirectory() as temp_dir:
                        temp_zip = os.path.join(temp_dir, 'release.zip')
                        urllib.request.urlretrieve(download_url, temp_zip, reporthook=report_progress)
                        self.status_updated.emit("Download complete, extracting specific folder...")
                        self.extract_folder_from_zip(temp_zip, self.folder_path, self.download_path)
                else:
                    urllib.request.urlretrieve(download_url, self.download_path, reporthook=report_progress)
                    self.status_updated.emit(f"Download complete: {self.download_path}")

                self.download_complete.emit(True, self.download_path)
            except Exception as e:
                self.status_updated.emit(f"Error downloading file: {str(e)}")
                self.download_complete.emit(False, str(e))

        except Exception as e:
            self.status_updated.emit(f"Error: {str(e)}")
            self.download_complete.emit(False, str(e))

    def extract_folder_from_zip(self, zip_path, folder_path, output_path):
        """Extract a specific folder from a zip file."""
        try:
            os.makedirs(os.path.dirname(output_path) if os.path.dirname(output_path) else '.', exist_ok=True)

            with tempfile.TemporaryDirectory() as temp_extract_dir:
                self.status_updated.emit("Extracting ZIP file...")
                with zipfile.ZipFile(zip_path, 'r') as zip_ref:
                    zip_ref.extractall(temp_extract_dir)

                extracted_folders = [d for d in os.listdir(temp_extract_dir) if os.path.isdir(os.path.join(temp_extract_dir, d))]
                if not extracted_folders:
                    raise Exception("No folders found in extracted ZIP")

                repo_folder = os.path.join(temp_extract_dir, extracted_folders[0])
                source_folder = os.path.join(repo_folder, folder_path)

                if not os.path.exists(source_folder):
                    raise Exception(f"Folder '{folder_path}' not found in release")

                if os.path.exists(output_path):
                    shutil.rmtree(output_path)

                self.status_updated.emit(f"Copying folder '{folder_path}' to destination...")
                shutil.copytree(source_folder, output_path)
                self.status_updated.emit(f"Successfully extracted folder to: {os.path.abspath(output_path)}")

        except Exception as e:
            self.status_updated.emit(f"Error extracting folder: {str(e)}")
            raise e


# ---------------------------------------------------------------------------
# UpdateBanner — thin notification banner above the canvas
# ---------------------------------------------------------------------------

class UpdateBanner(QWidget):
    """Top-of-window banner that appears when an update is available.

    Emits ``view_details`` when the user clicks "View Details" and
    ``dismissed`` when the user clicks the close button.
    """

    view_details = Signal()
    dismissed = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("UpdateBanner")
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setFixedHeight(0)  # starts collapsed
        self._target_height = 34
        self._release_info = None
        self._dismissed_this_session = None  # only dismiss for current session
        self._build_ui()
        self.setVisible(False)

    def _build_ui(self):
        self.setStyleSheet(
            "QWidget#UpdateBanner { background: qlineargradient("
            "x1:0, y1:0, x2:1, y2:0, stop:0 #1D65CA, stop:1 #1D65CA); }"
        )

        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 0, 8, 0)
        layout.setSpacing(8)

        self.icon_label = QLabel("↑")
        self.icon_label.setStyleSheet(
            "color: white; font-size: 14px; font-weight: bold; background: transparent; border: none;"
        )
        layout.addWidget(self.icon_label)

        self.text_label = QLabel("Update available")
        self.text_label.setStyleSheet(
            "color: white; font-size: 12px; font-weight: bold; background: transparent; border: none;"
        )
        layout.addWidget(self.text_label)

        layout.addStretch()

        self.details_btn = QPushButton("Update")
        self.details_btn.setCursor(Qt.PointingHandCursor)
        self.details_btn.setStyleSheet(
            "QPushButton { color: white; background: rgba(255,255,255,0.15); "
            "border: 1px solid rgba(255,255,255,0.3); border-radius: 4px; "
            "padding: 2px 10px; font-size: 11px; }"
            "QPushButton:hover { background: rgba(255,255,255,0.25); }"
        )
        self.details_btn.clicked.connect(self.view_details.emit)
        layout.addWidget(self.details_btn)

        self.close_btn = QPushButton("✕")
        self.close_btn.setFixedSize(20, 20)
        self.close_btn.setCursor(Qt.PointingHandCursor)
        self.close_btn.setStyleSheet(
            "QPushButton { color: rgba(255,255,255,0.6); background: transparent; "
            "border: none; font-size: 12px; }"
            "QPushButton:hover { color: white; }"
        )
        self.close_btn.clicked.connect(self._on_dismiss)
        layout.addWidget(self.close_btn)

    def show_update(self, release_info):
        """Show the banner with the given release info dict."""
        self._release_info = release_info
        version = release_info.get("version", "")
        is_critical = release_info.get("is_critical", False)

        self.text_label.setText(f"Update v{version} available")

        if is_critical:
            self.setStyleSheet(
                "QWidget#UpdateBanner { background: qlineargradient("
                "x1:0, y1:0, x2:1, y2:0, stop:0 #8b1a1a, stop:1 #cc3300); }"
            )
            self.icon_label.setText("⚠")
            self.text_label.setText(f"Critical update v{version} available")
            self.close_btn.setVisible(False)
        else:
            self.setStyleSheet(
                "QWidget#UpdateBanner { background: qlineargradient("
                "x1:0, y1:0, x2:1, y2:0, stop:0 #1D65CA, stop:1 #1D65CA); }"
            )
            self.icon_label.setText("↑")
            self.close_btn.setVisible(True)

        self.setVisible(True)
        self.setFixedHeight(self._target_height)

    def hide_banner(self):
        """Collapse and hide the banner."""
        self.setFixedHeight(0)
        self.setVisible(False)

    def _on_dismiss(self):
        """User dismissed — hide for this session only."""
        self.hide_banner()
        if self._release_info:
            self._dismissed_this_session = self._release_info.get("version")
        self.dismissed.emit()

    def is_dismissed_this_session(self, version):
        """Return True if the user dismissed this version during the current session."""
        return self._dismissed_this_session == version
