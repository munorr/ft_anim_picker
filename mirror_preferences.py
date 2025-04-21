try:
    from PySide6 import QtWidgets, QtCore, QtGui
    from shiboken6 import wrapInstance
except ImportError:
    from PySide2 import QtWidgets, QtCore, QtGui
    from shiboken2 import wrapInstance

import maya.cmds as cmds
import json
from . import custom_dialog as CD
from . import custom_button as CB
from . import tool_functions as TF
from functools import partial

class MirrorPreferencesWindow(QtWidgets.QWidget):
    """Window for configuring mirror preferences for Maya objects using script manager style."""
    
    def __init__(self, parent=None):
        super(MirrorPreferencesWindow, self).__init__(parent)
        self.setWindowFlags(QtCore.Qt.Window | QtCore.Qt.FramelessWindowHint | QtCore.Qt.Tool)
        self.setWindowFlag(QtCore.Qt.WindowStaysOnTopHint)
        self.setAttribute(QtCore.Qt.WA_TranslucentBackground)
        
        # Setup resizing parameters
        self.resizing = False
        self.resize_edge = None
        self.resize_range = 8  # Pixels from edge where resizing is active
        self.setMinimumSize(280, 260)  # Set minimum size to match frame size
        
        # Dictionary to store mirror preferences for objects
        self.mirror_prefs = {}
        
        # Current selected objects and last selected object for state tracking
        self.selected_objects = []
        self.last_selected_object = None
        
        # Callback management
        self.selection_callback = None
        self.callback_active = True
        
        # Flag to track if we're initializing the UI
        self.initializing = True
        
        # Flag to prevent recursive updates
        self.is_updating = False
        
        # Setup UI
        self.setup_ui()
        
        # Set up the Maya callback after UI is created
        try:
            import maya.api.OpenMaya as om
            self.selection_callback = om.MEventMessage.addEventCallback("SelectionChanged", self._on_maya_selection_changed)
        except Exception as e:
            print(f"Could not set up Maya selection callback: {e}")
            
        # Mark initialization as complete
        self.initializing = False
            
        # Initial refresh - force it to run even if window isn't visible yet
        self.refresh_selection(force=True)
        
    def setup_ui(self):
        """Set up the user interface using the script manager style."""
        # Setup main layout
        self.main_layout = QtWidgets.QVBoxLayout(self)
        self.main_layout.setContentsMargins(4, 4, 4, 4)
        self.main_layout.setSpacing(4)
        
        # Create main frame
        self.frame = QtWidgets.QFrame()
        self.frame.setFixedSize(280, 260)
        self.frame.setStyleSheet("""
            QFrame {
                background-color: rgba(30, 30, 30, 1);
                border: 1px solid #444444;
                border-radius: 4px;
            }
        """)
        self.frame_layout = QtWidgets.QVBoxLayout(self.frame)
        self.frame_layout.setContentsMargins(6, 6, 6, 6)
        self.frame_layout.setSpacing(6)
        
        # Title bar with draggable area and close button
        self.title_bar = QtWidgets.QWidget()
        self.title_bar.setFixedHeight(30)
        self.title_bar.setStyleSheet("background: rgba(20, 20, 20, 1); border: none; border-radius: 3px;")
        title_layout = QtWidgets.QHBoxLayout(self.title_bar)
        title_layout.setContentsMargins(6, 6, 6, 6)
        title_layout.setSpacing(6)
        
        self.title_label = QtWidgets.QLabel("Mirror Preferences")
        self.title_label.setStyleSheet("color: #dddddd; background: transparent;")
        title_layout.addSpacing(4)
        title_layout.addWidget(self.title_label)
        
        # Refresh button - removed unused button
        
        # Close button
        self.close_button = QtWidgets.QPushButton("✕")
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
        self.close_button.clicked.connect(self.close)
        title_layout.addWidget(self.close_button)
        
        # Add title bar to main layout
        self.frame_layout.addWidget(self.title_bar)
        
        # Content area
        content_widget = QtWidgets.QWidget()
        content_layout = QtWidgets.QVBoxLayout(content_widget)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(10)
        
        # Object selection section
        selection_frame = QtWidgets.QFrame()
        selection_frame.setStyleSheet("""
            QFrame {
                background-color: rgba(40, 40, 40, 0.7);
                border: 1px solid #555555;
                border-radius: 3px;
            }
            QLabel {
                color: #dddddd;
                background: transparent;
            }
        """)
        selection_layout = QtWidgets.QVBoxLayout()
        # Current selection label
        self.selection_label = QtWidgets.QLabel("No objects selected")
        self.selection_label.setStyleSheet("color: #dddddd; background-color: #1e1e1e; border: 1px solid #444444; border-radius: 3px; padding: 5px;")
        self.selection_label.setAlignment(QtCore.Qt.AlignCenter)
        self.selection_label.setFixedHeight(30)
        selection_layout.addWidget(self.selection_label)
        
        #content_layout.addLayout(selection_layout)

        # Mirror configuration section
        self.config_frame = QtWidgets.QFrame()
        self.config_frame.setStyleSheet("""
            QFrame {
                background-color: rgba(40, 40, 40, 0.7);
                border: 1px solid #555555;
                border-radius: 3px;
            }
            QLabel {
                color: #dddddd;
                background: transparent;
            }
            QLineEdit {
                background-color: #1e1e1e;
                color: #dddddd;
                border: 1px solid #444444;
                border-radius: 3px;
                padding: 5px;
            }
        """)
        config_layout = QtWidgets.QVBoxLayout(self.config_frame)
        config_layout.setContentsMargins(2, 2, 2, 2)
        config_layout.setSpacing(2)
        
        # Section header
        config_header = QtWidgets.QLabel("Mirror Configuration")
        config_header.setStyleSheet("font-weight: bold; color: #aaaaaa; border: none;")
        #config_layout.addWidget(config_header)
        #--------------------------------------------------------------------------------------------------------------------------------------------
        # Mirror counterpart section
        counterpart_frame = QtWidgets.QFrame()
        counterpart_frame.setStyleSheet("background-color: rgba(45, 45, 45, 0.7); border-radius: 3px; padding: 2px;")
        counterpart_layout = QtWidgets.QVBoxLayout(counterpart_frame)
        counterpart_layout.setContentsMargins(1, 1, 1, 1)
        counterpart_layout1 = QtWidgets.QHBoxLayout()
        counterpart_layout1.setContentsMargins(1, 1, 1, 1)
        counterpart_layout2 = QtWidgets.QHBoxLayout()
        counterpart_layout2.setContentsMargins(1, 1, 1, 1)
        
        counterpart_label = QtWidgets.QLabel("Mirror Counterpart:")
        counterpart_label.setStyleSheet("color: #aaaaaa; border: none;")
        counterpart_layout1.addWidget(counterpart_label)
        
        self.counterpart_label = QtWidgets.QLabel("None")
        self.counterpart_label.setStyleSheet("color: #00aaff; border: none;")
        counterpart_layout1.addWidget(self.counterpart_label)
        
        self.manual_counterpart_edit = QtWidgets.QLineEdit()
        self.manual_counterpart_edit.setPlaceholderText("Enter manual counterpart name")
        self.manual_counterpart_edit.setEnabled(False)
        counterpart_layout2.addWidget(self.manual_counterpart_edit)
        
        self.set_counterpart_button = CB.CustomButton(
            text='Set',
            height=24,
            width=40,
            color='#385c73',
            textColor='#dddddd',
            radius=3
        )
        self.set_counterpart_button.clicked.connect(self.set_manual_counterpart)
        self.set_counterpart_button.setEnabled(False)
        counterpart_layout2.addWidget(self.set_counterpart_button)
        counterpart_layout.addLayout(counterpart_layout1)
        counterpart_layout.addLayout(counterpart_layout2)
        
        config_layout.addWidget(counterpart_frame)

        #--------------------------------------------------------------------------------------------------------------------------------------------
        # Axis mirroring section
        axis_layout = QtWidgets.QHBoxLayout()
        config_layout.addLayout(axis_layout)
        bh = 10
        #--------------------------------------------------------------------------------------------------------------------------------------------
        # Translation axis section
        trans_frame = QtWidgets.QFrame()
        trans_frame.setStyleSheet("background-color: rgba(30, 30, 30, 1); border-radius: 3px; padding: 4px; border: none;")
        trans_layout = QtWidgets.QVBoxLayout(trans_frame)
        trans_layout.setContentsMargins(1, 1, 1, 1)
        trans_layout.setSpacing(3)
        
        trans_header = QtWidgets.QLabel("Translation Axis")
        trans_header.setStyleSheet("color: #aaaaaa; font-weight: bold; border: none;")
        trans_layout.addWidget(trans_header)
        
        # X axis
        x_trans_layout = QtWidgets.QHBoxLayout()
        x_trans_label = QtWidgets.QLabel("X:")
        x_trans_label.setStyleSheet("color: #dddddd; border: none;")
        x_trans_label.setFixedWidth(20)
        x_trans_layout.addWidget(x_trans_label)
        
        
        self.x_trans_invert = CB.CustomRadioButton("Invert", color="#00aaff", group=True, height=bh, fill=True)
        self.x_trans_none = CB.CustomRadioButton("None", color="#00aaff", group=True, height=bh, fill=True)
        
        self.x_trans_invert.group('x_trans')
        self.x_trans_none.group('x_trans')
        
        # Don't set default checked state here, will be set in refresh_selection
        x_trans_layout.addWidget(self.x_trans_invert)
        x_trans_layout.addWidget(self.x_trans_none)
        trans_layout.addLayout(x_trans_layout)
        
        # Y axis
        y_trans_layout = QtWidgets.QHBoxLayout()
        y_trans_label = QtWidgets.QLabel("Y:")
        y_trans_label.setStyleSheet("color: #dddddd; border: none;")
        y_trans_label.setFixedWidth(20)
        y_trans_layout.addWidget(y_trans_label)
        
        self.y_trans_invert = CB.CustomRadioButton("Invert", color="#00aaff", group=True, height=bh, fill=True)
        self.y_trans_none = CB.CustomRadioButton("None", color="#00aaff", group=True, height=bh, fill=True)
        
        self.y_trans_invert.group('y_trans')
        self.y_trans_none.group('y_trans')
        
        # Don't set default checked state here, will be set in refresh_selection
        y_trans_layout.addWidget(self.y_trans_invert)
        y_trans_layout.addWidget(self.y_trans_none)
        trans_layout.addLayout(y_trans_layout)
        
        # Z axis
        z_trans_layout = QtWidgets.QHBoxLayout()
        z_trans_label = QtWidgets.QLabel("Z:")
        z_trans_label.setStyleSheet("color: #dddddd; border: none;")
        z_trans_label.setFixedWidth(20)
        z_trans_layout.addWidget(z_trans_label)
        
        self.z_trans_invert = CB.CustomRadioButton("Invert", color="#00aaff", group=True, height=bh, fill=True)
        self.z_trans_none = CB.CustomRadioButton("None", color="#00aaff", group=True, height=bh, fill=True)
        
        self.z_trans_invert.group('z_trans')
        self.z_trans_none.group('z_trans')
        
        # Don't set default checked state here, will be set in refresh_selection
        z_trans_layout.addWidget(self.z_trans_invert)
        z_trans_layout.addWidget(self.z_trans_none)
        trans_layout.addLayout(z_trans_layout)
        
        axis_layout.addWidget(trans_frame)
        #--------------------------------------------------------------------------------------------------------------------------------------------
        # Rotation axis section
        rot_frame = QtWidgets.QFrame()
        rot_frame.setStyleSheet("background-color: rgba(30, 30, 30, 1); border-radius: 3px; padding: 4px; border: none;")
        rot_layout = QtWidgets.QVBoxLayout(rot_frame)
        rot_layout.setContentsMargins(1, 1, 1, 1)
        rot_layout.setSpacing(3)
        
        rot_header = QtWidgets.QLabel("Rotation Axis")
        rot_header.setStyleSheet("color: #aaaaaa; font-weight: bold; border: none;")
        rot_layout.addWidget(rot_header)
        
        # X axis
        x_rot_layout = QtWidgets.QHBoxLayout()
        x_rot_label = QtWidgets.QLabel("X:")
        x_rot_label.setStyleSheet("color: #dddddd; border: none;")
        x_rot_label.setFixedWidth(20)
        x_rot_layout.addWidget(x_rot_label)
        
        self.x_rot_invert = CB.CustomRadioButton("Invert", color="#00aaff", group=True, height=bh, fill=True)
        self.x_rot_none = CB.CustomRadioButton("None", color="#00aaff", group=True, height=bh, fill=True)
        
        self.x_rot_invert.group('x_rot')
        self.x_rot_none.group('x_rot')
        
        # Don't set default checked state here, will be set in refresh_selection
        x_rot_layout.addWidget(self.x_rot_invert)
        x_rot_layout.addWidget(self.x_rot_none)
        rot_layout.addLayout(x_rot_layout)
        
        # Y axis
        y_rot_layout = QtWidgets.QHBoxLayout()
        y_rot_label = QtWidgets.QLabel("Y:")
        y_rot_label.setStyleSheet("color: #dddddd; border: none;")
        y_rot_label.setFixedWidth(20)
        y_rot_layout.addWidget(y_rot_label)
        
        self.y_rot_invert = CB.CustomRadioButton("Invert", color="#00aaff", group=True, height=bh, fill=True)
        self.y_rot_none = CB.CustomRadioButton("None", color="#00aaff", group=True, height=bh, fill=True)
        
        self.y_rot_invert.group('y_rot')
        self.y_rot_none.group('y_rot')
        
        # Don't set default checked state here, will be set in refresh_selection
        y_rot_layout.addWidget(self.y_rot_invert)
        y_rot_layout.addWidget(self.y_rot_none)
        rot_layout.addLayout(y_rot_layout)
        
        # Z axis
        z_rot_layout = QtWidgets.QHBoxLayout()
        z_rot_label = QtWidgets.QLabel("Z:")
        z_rot_label.setStyleSheet("color: #dddddd; border: none;")
        z_rot_label.setFixedWidth(20)
        z_rot_layout.addWidget(z_rot_label)
        
        self.z_rot_invert = CB.CustomRadioButton("Invert", color="#00aaff", group=True, height=bh, fill=True)
        self.z_rot_none = CB.CustomRadioButton("None", color="#00aaff", group=True, height=bh, fill=True)
        
        self.z_rot_invert.group('z_rot')
        self.z_rot_none.group('z_rot')
        
        # Don't set default checked state here, will be set in refresh_selection
        z_rot_layout.addWidget(self.z_rot_invert)
        z_rot_layout.addWidget(self.z_rot_none)
        rot_layout.addLayout(z_rot_layout)
        
        axis_layout.addWidget(rot_frame)
        
        # Removed the buttons frame since the remove button has been moved to the selection section
        
        # Add all content to the main frame
        content_layout.addWidget(self.config_frame)
        
        # Create buttons at the bottom of the window
        buttons_layout = QtWidgets.QHBoxLayout()
        buttons_layout.setContentsMargins(1, 1, 1, 1)
        buttons_layout.setSpacing(4)
        
        # Add mirror preference button
        add_pref_button = CB.CustomButton(
            text='Add Preference',
            height=30,
            color='#385c73',
            textColor='#dddddd',
            radius=3
        )
        add_pref_button.clicked.connect(self.add_mirror_preference)
        buttons_layout.addWidget(add_pref_button)
        
        # Remove mirror preference button
        self.remove_button = CB.CustomButton(
            text='Remove Preference',
            height=30,
            color='#a30000',
            textColor='#dddddd',
            radius=3
        )
        self.remove_button.clicked.connect(self.remove_mirror_preference)
        self.remove_button.setEnabled(False)
        self.remove_button.setVisible(False)  # Initially hidden
        buttons_layout.addWidget(self.remove_button)
        
        content_layout.addLayout(buttons_layout)
        self.frame_layout.addWidget(content_widget)
        
        # Initially hide the config frame until an object with preferences is selected
        self.config_frame.setVisible(False)
        
        # Add the main frame to the window layout
        self.main_layout.addWidget(self.frame)
        
        # Setup mouse events for dragging and resizing
        self.title_bar.mousePressEvent = self.title_bar_mouse_press_event
        self.title_bar.mouseMoveEvent = self.title_bar_mouse_move_event
        self.title_bar.mouseReleaseEvent = self.title_bar_mouse_release_event
        
        # Connect radio button signals
        for btn in [self.x_trans_invert, self.x_trans_none,
                   self.y_trans_invert, self.y_trans_none,
                   self.z_trans_invert, self.z_trans_none,
                   self.x_rot_invert, self.x_rot_none,
                   self.y_rot_invert, self.y_rot_none,
                   self.z_rot_invert, self.z_rot_none]:
            btn.toggled.connect(self.on_preference_changed)
            
        # Set up a Maya callback to automatically update when selection changes in Maya
        self.selection_callback = None
        self.callback_active = True  # Flag to track if callbacks should be processed
        
    def refresh_selection(self, force=False):
        """Refresh the selection from Maya and display settings for the first selected object.
        
        Args:
            force (bool): If True, refresh even if the window is not visible
        """
        try:
            # Prevent recursive updates
            if self.is_updating:
                return
                
            self.is_updating = True
                
            # Check if UI elements still exist
            if not self.callback_active or (not force and not self.isVisible()):
                self.is_updating = False
                return
                
            # Get the current selection from Maya
            selected_objects = cmds.ls(selection=True, long=True)
            
            if not selected_objects:
                # No objects selected
                self.title_label.setText("Mirror Preferences")
                self.clear_preference_ui()
                self.remove_button.setEnabled(False)
                self.remove_button.setVisible(False)  # Hide remove button
                self.manual_counterpart_edit.setEnabled(False)
                self.set_counterpart_button.setEnabled(False)
                self.toggle_config_frame(False)
                self.last_selected_object = None
                self.is_updating = False
                return
            
            # Update the title label with the selected object name
            if len(selected_objects) == 1:
                obj_name = selected_objects[0].split('|')[-1]  # Show the short name
                self.title_label.setText(f"Mirror: {obj_name}")
            else:
                self.title_label.setText(f"Mirror: {len(selected_objects)} objects")
            
            # Process the first selected object for preferences
            first_obj = selected_objects[0]
            
            # Check if we're processing the same object as before
            if first_obj == self.last_selected_object and not force:
                # Same object, don't reload preferences to avoid overriding user changes
                self.is_updating = False
                return
                
            # Update the last selected object
            self.last_selected_object = first_obj
            
            # Check if this object has mirror preferences
            has_preferences = self.has_mirror_preference(first_obj)
            
            # Show or hide the configuration frame based on whether the object has preferences
            self.toggle_config_frame(has_preferences)
            
            if has_preferences:
                # Load the saved preferences for this object
                self.load_preference_ui(first_obj)
                self.remove_button.setEnabled(True)
                self.remove_button.setVisible(True)  # Show remove button
            else:
                # Set default values if no preferences exist
                self.clear_preference_ui()
                self.remove_button.setEnabled(False)
                self.remove_button.setVisible(False)  # Hide remove button
                # Ensure the counterpart label is cleared
                self.counterpart_label.setText("None")
                self.manual_counterpart_edit.clear()
            
            # Find and display the mirror counterpart
            self.find_and_display_counterpart(first_obj)
            
            # Enable manual counterpart editing
            self.manual_counterpart_edit.setEnabled(True)
            self.set_counterpart_button.setEnabled(True)
            
            self.is_updating = False
        except Exception as e:
            # If any error occurs, disable the callback to prevent further errors
            print(f"Error refreshing selection: {e}")
            self.callback_active = False
            self.is_updating = False
    
    def toggle_config_frame(self, show):
        """Show or hide the configuration frame.
        
        Args:
            show (bool): Whether to show the configuration frame
        """
        self.config_frame.setVisible(show)
        
    def _on_maya_selection_changed(self, *args):
        """Callback when Maya's selection changes."""
        # Only process if the window is still active and callbacks are enabled
        if not self.callback_active or self.is_updating:
            return
            
        # Use a timer to prevent multiple rapid updates
        try:
            # Use a slightly longer delay to ensure Maya selection is fully updated
            QtCore.QTimer.singleShot(100, lambda: self.refresh_selection(force=False))
        except RuntimeError:
            # If we get a RuntimeError, the Qt objects might be deleted
            self.callback_active = False
    
    def has_mirror_preference(self, obj_path):
        """Check if the object has mirror preferences."""
        # Get short name for attribute lookup
        short_name = obj_path.split('|')[-1]
        
        # Check if the object has the mirror preference attribute
        return cmds.attributeQuery("mirrorPreference", node=short_name, exists=True)
    
    def load_preference_ui(self, obj_path):
        """Load mirror preferences into the UI."""
        # Get short name for attribute lookup
        short_name = obj_path.split('|')[-1]
        
        # Get the mirror preference data
        if cmds.attributeQuery("mirrorPreference", node=short_name, exists=True):
            pref_data_str = cmds.getAttr(f"{short_name}.mirrorPreference")
            try:
                # Temporarily block signals to prevent triggering on_preference_changed
                # during UI updates
                self._block_preference_signals(True)
                
                pref_data = json.loads(pref_data_str)
                
                # Store the loaded preferences for comparison
                self.loaded_preferences = pref_data.copy()
                
                # Set translation axis preferences
                if "translate" in pref_data:
                    trans_data = pref_data["translate"]
                    self._set_axis_preference(trans_data, "x", self.x_trans_invert, self.x_trans_none)
                    self._set_axis_preference(trans_data, "y", self.y_trans_invert, self.y_trans_none)
                    self._set_axis_preference(trans_data, "z", self.z_trans_invert, self.z_trans_none)
                
                # Set rotation axis preferences
                if "rotate" in pref_data:
                    rot_data = pref_data["rotate"]
                    self._set_axis_preference(rot_data, "x", self.x_rot_invert, self.x_rot_none)
                    self._set_axis_preference(rot_data, "y", self.y_rot_invert, self.y_rot_none)
                    self._set_axis_preference(rot_data, "z", self.z_rot_invert, self.z_rot_none)
                
                # Set counterpart if available
                if "counterpart" in pref_data:
                    counterpart = pref_data["counterpart"]
                    self.counterpart_label.setText(counterpart)
                    self.manual_counterpart_edit.setText(counterpart)
                
                # Force update the UI
                QtWidgets.QApplication.processEvents()
                
                # Re-enable signals after UI is updated
                self._block_preference_signals(False)
                
            except json.JSONDecodeError:
                print(f"Error decoding mirror preference data for {short_name}")
                # Re-enable signals in case of error
                self._block_preference_signals(False)
                
    def _set_axis_preference(self, data, axis, invert_button, none_button):
        """Helper method to set axis preference buttons."""
        if axis in data:
            # Convert old values to new format
            if data[axis] in ["positive", "negative", "invert"]:
                invert_button.setChecked(True)
            else:
                none_button.setChecked(True)
        else:
            # Set default if no data is available
            none_button.setChecked(True)
    
    def clear_preference_ui(self):
        """Clear the preference UI to default values."""
        # Block signals to prevent triggering on_preference_changed
        self._block_preference_signals(True)
        
        # Translation defaults
        self.x_trans_invert.setChecked(True)
        self.y_trans_none.setChecked(True)
        self.z_trans_none.setChecked(True)
        
        # Rotation defaults
        self.x_rot_none.setChecked(True)
        self.y_rot_invert.setChecked(True)
        self.z_rot_invert.setChecked(True)
        
        # Clear counterpart
        self.counterpart_label.setText("None")
        self.manual_counterpart_edit.clear()
        
        # Re-enable signals
        self._block_preference_signals(False)
        
        # Force update the UI
        QtWidgets.QApplication.processEvents()
    
    def find_and_display_counterpart(self, obj_path):
        """Find and display the mirror counterpart for the selected object."""
        short_name = obj_path.split('|')[-1]
        
        # Check if we already have a saved counterpart
        if cmds.attributeQuery("mirrorPreference", node=short_name, exists=True):
            pref_data_str = cmds.getAttr(f"{short_name}.mirrorPreference")
            try:
                pref_data = json.loads(pref_data_str)
                if "counterpart" in pref_data and pref_data["counterpart"]:
                    counterpart = pref_data["counterpart"]
                    self.counterpart_label.setText(counterpart)
                    self.manual_counterpart_edit.setText(counterpart)
                    return
            except json.JSONDecodeError:
                pass
        
        # Try to find the counterpart using the _find_mirrored_name function
        naming_conventions = TF._get_naming_conventions("", "")
        mirrored_name, is_center = TF._find_mirrored_name(short_name, naming_conventions)
        
        if mirrored_name != short_name:
            self.counterpart_label.setText(mirrored_name)
            self.manual_counterpart_edit.setText(mirrored_name)
        else:
            status = "None (Center Object)" if is_center else "Not Found"
            self.counterpart_label.setText(status)
            self.manual_counterpart_edit.clear()
    
    def set_manual_counterpart(self):
        """Set a manual counterpart name."""
        counterpart = self.manual_counterpart_edit.text().strip()
        if counterpart:
            self.counterpart_label.setText(counterpart)
            self.on_preference_changed()
    
    def _block_preference_signals(self, block):
        """Helper method to block/unblock signals from UI elements.
        
        Args:
            block (bool): Whether to block signals
        """
        for btn in [self.x_trans_invert, self.x_trans_none,
                   self.y_trans_invert, self.y_trans_none,
                   self.z_trans_invert, self.z_trans_none,
                   self.x_rot_invert, self.x_rot_none,
                   self.y_rot_invert, self.y_rot_none,
                   self.z_rot_invert, self.z_rot_none]:
            btn.blockSignals(block)
            
        # Also block the manual counterpart edit and button
        self.manual_counterpart_edit.blockSignals(block)
        self.set_counterpart_button.blockSignals(block)
    
    def on_preference_changed(self):
        """Handle when any preference is changed and automatically apply the changes."""
        # Prevent recursive updates
        if self.is_updating:
            return
            
        self.is_updating = True
        
        try:
            # Get the current selection from Maya
            selected_objects = cmds.ls(selection=True, long=True)
            if not selected_objects:
                self.is_updating = False
                return
            
            # Get base preferences from UI (without counterpart)
            base_prefs = self.get_current_preferences()
            
            # If there's a manual counterpart entered and only one object selected,
            # use that directly
            manual_counterpart = base_prefs["counterpart"]
            
            # Apply to all selected objects that already have mirror preferences
            for obj_path in selected_objects:
                short_name = obj_path.split('|')[-1]
                
                # Only update if the object already has mirror preferences
                if self.has_mirror_preference(obj_path):
                    # Create a copy of the base preferences for this object
                    obj_prefs = base_prefs.copy()
                    
                    # If multiple objects are selected or no manual counterpart is specified,
                    # find the appropriate counterpart for this specific object
                    if len(selected_objects) > 1 or not manual_counterpart:
                        naming_conventions = TF._get_naming_conventions("", "")
                        mirrored_name, is_center = TF._find_mirrored_name(short_name, naming_conventions)
                        
                        # Only update the counterpart if we found a valid mirror
                        if mirrored_name != short_name:
                            obj_prefs["counterpart"] = mirrored_name
                    
                    # Convert preferences to JSON string
                    prefs_json = json.dumps(obj_prefs)
                    
                    # Set the attribute value
                    cmds.setAttr(f"{short_name}.mirrorPreference", prefs_json, type="string")
                    
                    # Update counterpart display for the first object
                    if obj_path == selected_objects[0]:
                        self.counterpart_label.setText(obj_prefs["counterpart"])
        finally:
            self.is_updating = False
    
    def get_current_preferences(self):
        """Get the current preferences from the UI."""
        prefs = {
            "translate": {
                "x": "invert" if self.x_trans_invert.isChecked() else "none",
                "y": "invert" if self.y_trans_invert.isChecked() else "none",
                "z": "invert" if self.z_trans_invert.isChecked() else "none"
            },
            "rotate": {
                "x": "invert" if self.x_rot_invert.isChecked() else "none",
                "y": "invert" if self.y_rot_invert.isChecked() else "none",
                "z": "invert" if self.z_rot_invert.isChecked() else "none"
            },
            "counterpart": self.manual_counterpart_edit.text().strip()
        }
        return prefs
    
    def add_mirror_preference(self):
        """Add mirror preference to the currently selected Maya objects."""
        # Get the current selection from Maya
        selected_objects = cmds.ls(selection=True, long=True)
        if not selected_objects:
            cmds.warning("No objects selected. Please select at least one object.")
            return
        
        # Get base preferences from UI (without counterpart)
        base_prefs = self.get_current_preferences()
        
        # Apply to all selected objects with individual counterparts
        for obj_path in selected_objects:
            short_name = obj_path.split('|')[-1]
            
            # Create a copy of the base preferences for this object
            obj_prefs = base_prefs.copy()
            
            # Find the appropriate counterpart for this specific object
            naming_conventions = TF._get_naming_conventions("", "")
            mirrored_name, is_center = TF._find_mirrored_name(short_name, naming_conventions)
            
            # Set the counterpart in the preferences
            if mirrored_name != short_name:
                obj_prefs["counterpart"] = mirrored_name
            else:
                # If no counterpart found or it's a center object, use the manually entered value
                obj_prefs["counterpart"] = base_prefs["counterpart"]
            
            # Convert preferences to JSON string
            prefs_json = json.dumps(obj_prefs)
            
            # Add or update the attribute
            if not cmds.attributeQuery("mirrorPreference", node=short_name, exists=True):
                cmds.addAttr(short_name, longName="mirrorPreference", dataType="string")
            
            # Set the attribute value
            cmds.setAttr(f"{short_name}.mirrorPreference", prefs_json, type="string")
        
        # Update UI state
        self.remove_button.setEnabled(True)
        self.remove_button.setVisible(True)  # Make remove button visible
        
        # Show the configuration frame since the object now has preferences
        self.toggle_config_frame(True)
        
        # Refresh the selection to update the UI with the first selected object
        self.refresh_selection()
        
        # Show confirmation
        cmds.inViewMessage(amg=f"Mirror preferences added to {len(selected_objects)} object(s)", pos='midCenter', fade=True)
    
    def remove_mirror_preference(self):
        """Remove mirror preference from the currently selected Maya objects."""
        # Get the current selection from Maya
        selected_objects = cmds.ls(selection=True, long=True)
        if not selected_objects:
            cmds.warning("No objects selected. Please select at least one object.")
            return
        
        # Remove from all selected objects
        for obj_path in selected_objects:
            short_name = obj_path.split('|')[-1]
            
            # Remove the attribute if it exists
            if cmds.attributeQuery("mirrorPreference", node=short_name, exists=True):
                cmds.deleteAttr(f"{short_name}.mirrorPreference")
        
        # Update UI state
        self.clear_preference_ui()
        self.remove_button.setEnabled(False)
        self.remove_button.setVisible(False)  # Explicitly hide the remove button
        self.toggle_config_frame(False)
        
        # Refresh the selection to update the UI
        self.refresh_selection()
        
        # Show confirmation
        cmds.inViewMessage(amg=f"Mirror preferences removed from {len(selected_objects)} object(s)", pos='midCenter', fade=True)
    
    def title_bar_mouse_press_event(self, event):
        """Handle mouse press events on the title bar for dragging."""
        if event.button() == QtCore.Qt.LeftButton:
            self.drag_position = event.globalPos() - self.frameGeometry().topLeft()
            event.accept()
    
    def title_bar_mouse_move_event(self, event):
        """Handle mouse move events on the title bar for dragging."""
        if event.buttons() & QtCore.Qt.LeftButton:
            self.move(event.globalPos() - self.drag_position)
            event.accept()
    
    def title_bar_mouse_release_event(self, event):
        """Handle mouse release events on the title bar."""
        if event.button() == QtCore.Qt.LeftButton:
            event.accept()
    
    def mousePressEvent(self, event):
        """Handle mouse press events for resizing."""
        if event.button() == QtCore.Qt.LeftButton:
            # Check if we're on an edge for resizing
            rect = self.rect()
            pos = event.pos()
            
            # Determine which edge was clicked
            on_left = pos.x() < self.resize_range
            on_right = pos.x() > rect.width() - self.resize_range
            on_top = pos.y() < self.resize_range
            on_bottom = pos.y() > rect.height() - self.resize_range
            
            if on_left and on_top:
                self.resize_edge = 'top-left'
            elif on_right and on_top:
                self.resize_edge = 'top-right'
            elif on_left and on_bottom:
                self.resize_edge = 'bottom-left'
            elif on_right and on_bottom:
                self.resize_edge = 'bottom-right'
            elif on_left:
                self.resize_edge = 'left'
            elif on_right:
                self.resize_edge = 'right'
            elif on_top:
                self.resize_edge = 'top'
            elif on_bottom:
                self.resize_edge = 'bottom'
            else:
                self.resize_edge = None
            
            if self.resize_edge:
                self.resizing = True
                self.resize_start_pos = event.globalPos()
                self.resize_start_geometry = self.geometry()
                event.accept()
    
    def mouseMoveEvent(self, event):
        """Handle mouse move events for resizing."""
        if self.resizing and self.resize_edge:
            delta = event.globalPos() - self.resize_start_pos
            new_geo = QtCore.QRect(self.resize_start_geometry)
            
            # Apply the appropriate resize based on which edge is being dragged
            if 'left' in self.resize_edge:
                new_geo.setLeft(new_geo.left() + delta.x())
            if 'right' in self.resize_edge:
                new_geo.setRight(new_geo.right() + delta.x())
            if 'top' in self.resize_edge:
                new_geo.setTop(new_geo.top() + delta.y())
            if 'bottom' in self.resize_edge:
                new_geo.setBottom(new_geo.bottom() + delta.y())
            
            # Ensure we don't resize below minimum size
            if new_geo.width() >= self.minimumWidth() and new_geo.height() >= self.minimumHeight():
                self.setGeometry(new_geo)
            event.accept()
        else:
            # Update cursor based on position for resize feedback
            rect = self.rect()
            pos = event.pos()
            
            # Determine which edge the mouse is over
            on_left = pos.x() < self.resize_range
            on_right = pos.x() > rect.width() - self.resize_range
            on_top = pos.y() < self.resize_range
            on_bottom = pos.y() > rect.height() - self.resize_range
            
            if (on_left and on_top) or (on_right and on_bottom):
                self.setCursor(QtCore.Qt.SizeFDiagCursor)
            elif (on_right and on_top) or (on_left and on_bottom):
                self.setCursor(QtCore.Qt.SizeBDiagCursor)
            elif on_left or on_right:
                self.setCursor(QtCore.Qt.SizeHorCursor)
            elif on_top or on_bottom:
                self.setCursor(QtCore.Qt.SizeVerCursor)
            else:
                self.setCursor(QtCore.Qt.ArrowCursor)
    
    def mouseReleaseEvent(self, event):
        """Handle mouse release events for resizing."""
        if event.button() == QtCore.Qt.LeftButton and self.resizing:
            self.resizing = False
            self.resize_edge = None
            self.setCursor(QtCore.Qt.ArrowCursor)
            super().mouseReleaseEvent(event)
            
    def closeEvent(self, event):
        """Clean up when the window is closed."""
        # Disable callbacks first to prevent any race conditions
        self.callback_active = False
        self.is_updating = True  # Prevent any further updates
        
        # Remove the Maya callback if it exists
        if self.selection_callback is not None:
            try:
                import maya.api.OpenMaya as om
                om.MMessage.removeCallback(self.selection_callback)
                self.selection_callback = None
            except Exception as e:
                print(f"Error removing callback: {e}")
        
        # Save current state if needed
        selected_objects = cmds.ls(selection=True, long=True)
        if selected_objects and self.has_mirror_preference(selected_objects[0]):
            # Final save of preferences before closing
            try:
                prefs = self.get_current_preferences()
                short_name = selected_objects[0].split('|')[-1]
                prefs_json = json.dumps(prefs)
                cmds.setAttr(f"{short_name}.mirrorPreference", prefs_json, type="string")
            except Exception as e:
                print(f"Error saving preferences on close: {e}")
                
        super().closeEvent(event)
        
    def create_icon(self, text, color):
        """Create a QIcon with the given text and color."""
        # Create a pixmap
        pixmap = QtGui.QPixmap(24, 24)
        pixmap.fill(QtCore.Qt.transparent)
        
        # Create a painter to draw on the pixmap
        painter = QtGui.QPainter(pixmap)
        painter.setRenderHint(QtGui.QPainter.Antialiasing)
        
        # Set the font
        font = QtGui.QFont("Arial", 12)
        painter.setFont(font)
        
        # Set the color
        painter.setPen(QtGui.QColor(color))
        
        # Draw the text centered on the pixmap
        painter.drawText(pixmap.rect(), QtCore.Qt.AlignCenter, text)
        
        # End painting
        painter.end()
        
        # Create and return an icon from the pixmap
        return QtGui.QIcon(pixmap)

