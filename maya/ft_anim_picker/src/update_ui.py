import os
import sys
import json
import urllib.request
import zipfile
import tempfile
import shutil
from pathlib import Path

# PySide compatibility imports
try:
    # Try PySide6 first
    from PySide6 import QtCore, QtWidgets
    from PySide6.QtCore import Qt, Signal, QThread
    from PySide6.QtWidgets import (
        QWidget, QVBoxLayout, QHBoxLayout, QComboBox, 
        QPushButton, QLabel, QProgressBar, QMessageBox,QFrame,QApplication
    )
    PYSIDE_VERSION = 6
except ImportError:
    # Fall back to PySide2
    from PySide2 import QtCore, QtWidgets
    from PySide2.QtCore import Qt, Signal as Signal
    from PySide2.QtWidgets import (
        QWidget, QVBoxLayout, QHBoxLayout, QComboBox, 
        QPushButton, QLabel, QProgressBar, QMessageBox,QFrame,QApplication
    )
    PYSIDE_VERSION = 2
#-----------------------------------------------------------------------------------------------------------------------------------------------------
def get_parent_dir():
    script_dir = os.path.normpath(os.path.dirname(os.path.realpath(__file__)))
    script_dir_normalized = script_dir.replace("\\", "/")
    parent_dir = os.path.normpath(os.path.dirname(script_dir))
    parent_dir_normalized = parent_dir.replace("\\", "/")
    return script_dir, script_dir_normalized, parent_dir, parent_dir_normalized
#-----------------------------------------------------------------------------------------------------------------------------------------------------
class DownloadWorker(QThread):
    """Worker thread to handle GitHub API requests and downloads"""
    progress_updated = Signal(int)
    status_updated = Signal(str)
    download_complete = Signal(bool, str)
    extract_progress = Signal(int)
    
    def __init__(self, repo_url, release_tag, download_path, folder_path=None):
        super().__init__()
        self.repo_url = repo_url
        self.release_tag = release_tag
        self.download_path = download_path
        self.folder_path = folder_path  # Path to specific folder to extract
        
    def run(self):
        try:
            # Parse repository URL
            if self.repo_url.endswith('.git'):
                self.repo_url = self.repo_url[:-4]
            
            parts = self.repo_url.replace('https://github.com/', '').split('/')
            if len(parts) < 2:
                self.status_updated.emit("Error: Invalid GitHub repository URL")
                self.download_complete.emit(False, "Invalid GitHub repository URL")
                return
            
            owner, repo = parts[0], parts[1]
            
            # Download the release asset
            self.status_updated.emit(f"Downloading release {self.release_tag}...")
            
            # Get the release assets URL
            release_url = f"https://api.github.com/repos/{owner}/{repo}/releases/tags/{self.release_tag}"
            
            # Open the URL and read the response
            self.status_updated.emit("Fetching release information...")
            
            # Create a request with a User-Agent header to avoid GitHub API limitations
            headers = {'User-Agent': 'GitReleaseDownloader/1.0'}
            req = urllib.request.Request(release_url, headers=headers)
            
            with urllib.request.urlopen(req) as response:
                release_data = json.loads(response.read().decode())
                
            print(f"Release data: {release_data.keys()}")
            
            # Check if this is a direct download URL (not from API)
            if self.download_path.endswith('.zip') and 'browser_download_url' in self.release_tag:
                download_url = self.release_tag
                asset = {'name': os.path.basename(self.download_path)}
            elif 'assets' not in release_data or not release_data['assets']:
                # Try to use the source code archive as fallback
                self.status_updated.emit("No assets found, downloading source code archive...")
                download_url = f"https://github.com/{owner}/{repo}/archive/refs/tags/{self.release_tag}.zip"
                asset = {'name': f"{repo}-{self.release_tag}.zip"}
            else:
            
                # Get the first asset (usually the zip file)
                asset = release_data['assets'][0]
                download_url = asset['browser_download_url']
                
            print(f"Using download URL: {download_url}")
            
            # Create directory if it doesn't exist
            os.makedirs(os.path.dirname(self.download_path) if os.path.dirname(self.download_path) else '.', exist_ok=True)
            
            # Download the file with progress reporting
            self.status_updated.emit(f"Downloading {asset['name']}...")
            
            def report_progress(block_count, block_size, total_size):
                if total_size > 0:
                    percent = min(int(block_count * block_size * 100 / total_size), 100)
                    self.progress_updated.emit(percent)
            
            try:
                # Create a temporary file if we need to extract a specific folder
                if self.folder_path:
                    with tempfile.TemporaryDirectory() as temp_dir:
                        temp_zip = os.path.join(temp_dir, 'release.zip')
                        urllib.request.urlretrieve(download_url, temp_zip, reporthook=report_progress)
                        self.status_updated.emit("Download complete, extracting specific folder...")
                        
                        # Extract the specific folder
                        self.extract_folder_from_zip(temp_zip, self.folder_path, self.download_path)
                else:
                    # Direct download without extraction
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
        """Extract a specific folder from a zip file"""
        try:
            # Make sure the output directory exists
            os.makedirs(os.path.dirname(output_path) if os.path.dirname(output_path) else '.', exist_ok=True)
            
            # Extract the zip file to a temporary directory
            with tempfile.TemporaryDirectory() as temp_extract_dir:
                self.status_updated.emit("Extracting ZIP file...")
                with zipfile.ZipFile(zip_path, 'r') as zip_ref:
                    # Get total number of files for progress reporting
                    total_files = len(zip_ref.namelist())
                    extracted_files = 0
                    
                    # Extract all files
                    zip_ref.extractall(temp_extract_dir)
                    
                # Find the extracted folder (usually named repo-branch)
                extracted_folders = [d for d in os.listdir(temp_extract_dir) if os.path.isdir(os.path.join(temp_extract_dir, d))]
                if not extracted_folders:
                    raise Exception("No folders found in extracted ZIP")
                
                repo_folder = os.path.join(temp_extract_dir, extracted_folders[0])
                source_folder = os.path.join(repo_folder, folder_path)
                
                # Check if the target folder exists
                if not os.path.exists(source_folder):
                    raise Exception(f"Folder '{folder_path}' not found in release")
                
                # Copy the folder
                if os.path.exists(output_path):
                    shutil.rmtree(output_path)
                
                self.status_updated.emit(f"Copying folder '{folder_path}' to destination...")
                shutil.copytree(source_folder, output_path)
                self.status_updated.emit(f"Successfully extracted folder to: {os.path.abspath(output_path)}")
                
        except Exception as e:
            self.status_updated.emit(f"Error extracting folder: {str(e)}")
            raise e

class UpdateWidget(QWidget):
    """Widget for selecting and downloading GitHub releases"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        # Set window properties similar to ScriptManagerWidget
        self.setWindowFlags(QtCore.Qt.Window | QtCore.Qt.FramelessWindowHint | QtCore.Qt.WindowStaysOnTopHint)
        self.setAttribute(QtCore.Qt.WA_TranslucentBackground)
        self.setAttribute(QtCore.Qt.WA_AlwaysShowToolTips, True)
        
        # Setup resizing parameters
        self.resizing = False
        self.resize_edge = None
        self.resize_range = 8  # Pixels from edge where resizing is active
        self.br = 4  # Border radius
        
        # Set initial size and position to center of screen
        self.width = 300
        self.height = 125
        self.setFixedSize(self.width, self.height)
        
        '''# Get screen geometry based on PySide version
        if PYSIDE_VERSION == 6:
            # In PySide6, we use QScreen
            screen = QApplication.primaryScreen()
            screen_geometry = screen.geometry()
        else:
            # In PySide2, we can still use desktop()
            screen_geometry = QApplication.desktop().screenGeometry()
            
        x = (screen_geometry.width() - self.width) // 2
        y = (screen_geometry.height() - self.height) // 2
        self.move(x, y)'''
        
        # Hardcoded repository URL
        self.repo_url = "https://github.com/munorr/ft_anim_picker"
        # Hardcoded folder path to download (set to None to download entire release)
        self.folder_path = "maya/ft_anim_picker"
        self.releases = []
        self.download_worker = None
        
        self.init_ui()
        self.load_releases()
    
    def init_ui(self):
        # Setup main layout
        self.main_layout = QVBoxLayout(self)
        self.main_layout.setContentsMargins(4, 4, 4, 4)
        self.main_layout.setSpacing(4)
        
        # Create main frame
        self.frame = QFrame()
        #self.frame.setMinimumWidth(300)
        self.frame.setStyleSheet(f"""
            QFrame {{
                background-color: rgba(36, 36, 36, .95);
                border: 1px solid #444444;
                border-radius: {self.br}px;
            }}""")
        self.frame_layout = QVBoxLayout(self.frame)
        self.frame_layout.setContentsMargins(6, 6, 6, 6)
        self.frame_layout.setSpacing(6)
        
        # Title bar with draggable area and close button
        self.title_bar = QWidget()
        self.title_bar.setFixedHeight(30)
        self.title_bar.setStyleSheet(f"background: rgba(30, 30, 30, .9); border: none; border-radius: {self.br}px;")
        title_layout = QHBoxLayout(self.title_bar)
        title_layout.setContentsMargins(6, 6, 6, 6)
        title_layout.setSpacing(6)
        
        # Title label
        self.title_label = QLabel("Update FT Anim Picker")
        self.title_label.setStyleSheet("color: #dddddd; background: transparent; border: none; font-weight: bold;")
        title_layout.addWidget(self.title_label)
        
        # Close button
        self.close_button = QPushButton("✕")
        self.close_button.setFixedSize(16, 16)
        self.close_button.setStyleSheet("""
            QPushButton {
                background-color: rgba(200, 0, 0, 0.6);
                color: #ff9393;
                border: none;
                border-radius: 2px;
                padding: 0px 0px 2px 0px;
            }
            QPushButton:hover {
                background-color: rgba(255, 0, 0, 0.6);
            }
        """)
        title_layout.addStretch(1)
        title_layout.addWidget(self.close_button)
        #---------------------------------------------------------------------------------------------------------------------------------------------
        # Repository info section
        self.repo_info_label = QLabel(f"Repository: {self.repo_url}")
        self.repo_info_label.setStyleSheet(f"color: #eeeeee; padding: 4px; font-size: 12px; border-radius: {self.br}px; background-color: #222222;")
        
        # Folder path info (if specified)
        if self.folder_path:
            folder_text = f"Downloading folder: {self.folder_path}"
        else:
            folder_text = "Downloading entire release"
        self.folder_info_label = QLabel(folder_text)
        self.folder_info_label.setStyleSheet("color: #aaaaaa; font-style: italic; padding: 2px;")
        #---------------------------------------------------------------------------------------------------------------------------------------------
        # Releases dropdown section
        releases_widget = QWidget()
        releases_layout = QHBoxLayout(releases_widget)
        releases_layout.setContentsMargins(0, 0, 0, 0)
        releases_layout.setSpacing(10)
        
        releases_label = QLabel("Available Versions:")
        releases_label.setStyleSheet("color: #dddddd; font-weight: bold; border: none;")
        
        self.releases_combo = QComboBox()
        #self.releases_combo.setMinimumWidth(300)
        self.releases_combo.setStyleSheet(f"""
            QComboBox {{
                background-color: #2a2a2a;
                color: #dddddd;
                border: 1px solid #555555;
                border-radius: {self.br}px;
                padding: 6px;
                selection-background-color: #4ca3fe;
            }}
            QComboBox:hover {{
                border-color: #4ca3fe;
            }}
            QComboBox::drop-down {{
                border: none;
                width: 20px;
            }}
            QComboBox::down-arrow {{
                image: none;
                border: 2px solid #aaaaaa;
                border-top: none;
                border-left: none;
                width: 6px;
                height: 6px;
                margin-right: 6px;
            }}
            QComboBox QAbstractItemView {{
                background-color: #2a2a2a;
                border: 1px solid #555555;
                selection-background-color: #4ca3fe;
                color: #dddddd;
            }}
        """)
        
        releases_layout.addWidget(releases_label)
        releases_layout.addWidget(self.releases_combo)
        #---------------------------------------------------------------------------------------------------------------------------------------------
        # Download button
        self.download_button = QPushButton("Download Release")
        self.download_button.setFixedHeight(32)
        self.download_button.setEnabled(False)
        self.download_button.setStyleSheet(f"""
            QPushButton {{
                background-color: #5285a6;
                color: white;
                border: none;
                border-radius: {self.br}px;
                padding: 6px 16px;
                font-weight: bold;
            }}
            QPushButton:hover {{
                background-color: #67c2f2;
            }}
            QPushButton:disabled {{
                background-color: #444444;
                color: #888888;
            }}
        """)
        #---------------------------------------------------------------------------------------------------------------------------------------------
        # Status and progress section
        self.status_label = QLabel("Ready")
        self.status_label.setStyleSheet("color: #dddddd; padding: 4px;")
        
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        self.progress_bar.setStyleSheet(f"""
            QProgressBar {{
                border: 1px solid #555555;
                border-radius: {self.br}px;
                text-align: center;
                background-color: #2a2a2a;
                color: #dddddd;
            }}
            QProgressBar::chunk {{
                background-color: #4ca3fe;
                border-radius: {self.br}px;
            }}
        """)
        
        # Add all widgets to frame layout
        self.frame_layout.addWidget(self.title_bar)
        #self.frame_layout.addWidget(self.repo_info_label)
        #self.frame_layout.addWidget(self.folder_info_label)
        self.frame_layout.addWidget(releases_widget)
        self.frame_layout.addWidget(self.download_button)
        #self.frame_layout.addWidget(self.status_label)
        #self.frame_layout.addWidget(self.progress_bar)
        self.frame_layout.addStretch()
        
        # Add frame to main layout
        self.main_layout.addWidget(self.frame)
        
        # Connect signals
        self.close_button.clicked.connect(self.close)
        self.download_button.clicked.connect(self.download_release)
        
        # Install event filter for the frame
        self.frame.setMouseTracking(True)
        self.frame.installEventFilter(self)
    
    def load_releases(self):
        """Load releases from the hardcoded GitHub repository"""
        try:
            # Parse repository URL
            if self.repo_url.endswith('.git'):
                self.repo_url = self.repo_url[:-4]
            
            parts = self.repo_url.replace('https://github.com/', '').split('/')
            if len(parts) < 2:
                self.status_label.setText("Error: Invalid GitHub repository URL")
                return
            
            owner, repo = parts[0], parts[1]
            
            # Get releases from GitHub API
            self.status_label.setText(f"Loading releases from {owner}/{repo}...")
            api_url = f"https://api.github.com/repos/{owner}/{repo}/releases"
            
            # Create a request with a User-Agent header to avoid GitHub API limitations
            headers = {'User-Agent': 'GitReleaseDownloader/1.0'}
            req = urllib.request.Request(api_url, headers=headers)
            
            with urllib.request.urlopen(req) as response:
                releases_data = json.loads(response.read().decode())
            
            # Clear and populate the releases dropdown
            self.releases_combo.clear()
            self.releases = []
            
            if not releases_data:
                self.status_label.setText("No releases found for this repository")
                return
            
            for release in releases_data:
                tag_name = release['tag_name']
                name = release['name'] if release['name'] else tag_name
                self.releases.append({
                    'tag': tag_name,
                    'name': name,
                    'url': release['html_url'],
                    'assets': release['assets']
                })
                #self.releases_combo.addItem(f"{name} ({tag_name})")

                tag_name_clean = tag_name.replace("_", "")
                if tag_name_clean >= "100":
                    self.releases_combo.addItem(f"{tag_name}")
            
            self.status_label.setText(f"Loaded {len(self.releases)} releases")
            self.download_button.setEnabled(True)
            
        except Exception as e:
            self.status_label.setText(f"Error loading releases: {str(e)}")
            # Note: QMessageBox would need to be styled similarly for consistency
    
    def download_release(self):
        """Download the selected release"""
        if not self.releases or self.releases_combo.currentIndex() < 0:
            return
        
        release = self.releases[self.releases_combo.currentIndex()]
        
        # Debug information
        print(f"Selected release: {release['name']} ({release['tag']})")
        print(f"Assets: {release['assets']}")
        
        if not release['assets']:
            # If no assets, try to download the source code zip directly
            tag = release['tag']
            parts = self.repo_url.replace('https://github.com/', '').split('/')
            owner, repo = parts[0], parts[1]
            
            # Create a synthetic asset for the source code zip
            if self.folder_path:
                asset_name = os.path.basename(self.folder_path)
            else:
                asset_name = f"{repo}-{tag}.zip"
                
            asset = {
                'name': asset_name,
                'browser_download_url': f"https://github.com/{owner}/{repo}/archive/refs/tags/{tag}.zip"
            }
            
            print(f"No assets found, using source code download URL: {asset['browser_download_url']}")
        else:
            # Get the first asset (usually the zip file)
            asset = release['assets'][0]
        
        # Use parent directory as the download location
        script_dir = get_parent_dir()[2]
        
        # Set download path based on whether we're extracting a folder
        if self.folder_path:
            # Use the last part of the folder path as the output folder name
            output_folder_name = os.path.basename(self.folder_path)
            download_path = script_dir
            #download_path = os.path.join(script_dir, asset['name'])
        else:
            download_path = os.path.join(script_dir, asset['name'])
        
        # Start the download worker
        self.progress_bar.setValue(0)
        #self.progress_bar.setVisible(True)
        self.download_button.setEnabled(False)
        
        # Create the download worker with the hardcoded folder path
        self.download_worker = DownloadWorker(self.repo_url, release['tag'], download_path, self.folder_path)
        self.download_worker.progress_updated.connect(self.update_progress)
        self.download_worker.status_updated.connect(self.update_status)
        self.download_worker.download_complete.connect(self.on_download_complete)
        self.download_worker.start()
    
    def update_progress(self, value):
        """Update the progress bar"""
        self.progress_bar.setValue(value)
    
    def update_status(self, message):
        """Update the status label"""
        self.status_label.setText(message)
    
    def on_download_complete(self, success, message):
        """Handle download completion"""
        #self.progress_bar.setVisible(False)
        self.download_button.setEnabled(True)
        
        if success:
            # Note: QMessageBox would need to be styled similarly for consistency
            print(f"Download Complete: Release downloaded successfully to:\n{message}")
        else:
            print(f"Download Failed: Failed to download release: {message}")
#-----------------------------------------------------------------------------------------------------------------------------------------------------
if __name__ == "__main__":
    # Determine which PySide version to use
    if PYSIDE_VERSION == 6:
        from PySide6.QtWidgets import QApplication
    else:
        from PySide2.QtWidgets import QApplication
    
    print("Parent directory: ", get_parent_dir()[0])
    app = QApplication(sys.argv)
    
    widget = UpdateWidget()
    widget.show()
    
    sys.exit(app.exec_() if PYSIDE_VERSION == 2 else app.exec())
