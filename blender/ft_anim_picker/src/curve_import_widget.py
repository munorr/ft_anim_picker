from PySide6 import QtWidgets, QtCore, QtGui
from PySide6.QtGui import QColor
from PySide6.QtCore import QTimer, QPropertyAnimation, QEasingCurve
from shiboken6 import wrapInstance

from .custom_button import CustomRadioButton
from .blender_curve_converter import CoordinatePlaneConfig


class CurveImportOptionsWidget(QtWidgets.QWidget):
    """
    Widget that provides the same UI as the curve import dialog
    but can be embedded in menus or other widgets.
    """
    
    def __init__(self, parent=None, canvas=None):
        super().__init__(parent)
        self.canvas = canvas
        self.setup_ui()
        
    def setup_ui(self):
        """Set up the user interface"""

        def set_margin_space(layout,margin,space):
            layout.setContentsMargins(margin,margin,margin,margin)
            layout.setSpacing(space)

        # Main layout
        main_layout = QtWidgets.QVBoxLayout(self)
        set_margin_space(main_layout,2,4)
        # Set fixed size for the widget
        self.setFixedSize(200, 150)
        
        # Set widget styling for menu integration
        self.setStyleSheet('''
            QWidget {
                background-color: transparent;
                border: none;
            }
            QLabel {
                color: white;
                background-color: transparent;
                border: none;
                font-weight: bold;
            }
        ''')
        #-------------------------------------------------------------------------------------------------------------------
        # Add spline mode description
        spline_desc_label = QtWidgets.QLabel("Spline handling:")
        spline_desc_label.setWordWrap(True)
        main_layout.addWidget(spline_desc_label)
        
        # Add spline mode options
        self.spline_button_group = QtWidgets.QButtonGroup()
        self.spline_radio_buttons = {}
        
        spline_option_frame = QtWidgets.QFrame()
        spline_option_frame.setStyleSheet("QFrame { background-color: #1e1e1e; margin: 2px; border-radius: 4px; }")
        spline_option_layout = QtWidgets.QHBoxLayout(spline_option_frame)
        set_margin_space(spline_option_layout,4,2)
        
        # Get current spline mode from canvas
        separate_splines = True
        if self.canvas:
            separate_splines = self.canvas.get_separate_splines_mode()
        
        separate_radio = CustomRadioButton("Separate", group=True, height=16)
        separate_radio.group('spline_mode')
        separate_radio.setToolTip("Create one button per spline")
        separate_radio.setChecked(separate_splines)
        
        if self.canvas:
            separate_radio.toggled.connect(lambda checked: self._on_spline_mode_changed(True) if checked else None)
        
        self.spline_radio_buttons['separate'] = separate_radio
        spline_option_layout.addWidget(separate_radio)
        
        combine_radio = CustomRadioButton("Combined", group=True, height=16)
        combine_radio.group('spline_mode')
        combine_radio.setToolTip("Create one button per curve object with all splines combined")
        combine_radio.setChecked(not separate_splines)
        
        if self.canvas:
            combine_radio.toggled.connect(lambda checked: self._on_spline_mode_changed(False) if checked else None)
        
        self.spline_radio_buttons['combine'] = combine_radio
        spline_option_layout.addWidget(combine_radio)
        
        main_layout.addWidget(spline_option_frame)
        #-------------------------------------------------------------------------------------------------------------------
        # Flat plane selection
        self.auto_detect_checkbox = CustomRadioButton("Auto detect flat plane", height=16)
        self.auto_detect_checkbox.setToolTip("Automatically detect the best coordinate plane from selected curves")
        
        # Check if auto-detection is enabled (default to True)
        auto_detect_enabled = True
        if self.canvas:
            auto_detect_enabled = self.canvas.get_auto_detect_plane_mode()
        
        self.auto_detect_checkbox.setChecked(auto_detect_enabled)
        
        if self.canvas:
            self.auto_detect_checkbox.toggled.connect(self._on_auto_detect_changed)
        
        desc_label = QtWidgets.QLabel("Choose curve flat plane:")
        desc_label.setWordWrap(True)
        main_layout.addWidget(desc_label)

        self.flat_plane_frame = QtWidgets.QFrame()
        self.flat_plane_frame.setStyleSheet("QFrame { background-color: #1e1e1e; margin: 2px; border-radius: 4px; }")
        flat_plane_layout = QtWidgets.QVBoxLayout(self.flat_plane_frame)
        set_margin_space(flat_plane_layout,4,4)
        flat_plane_layout.addWidget(self.auto_detect_checkbox)
        

        # Add radio buttons for main coordinate planes
        self.plane_button_group = QtWidgets.QButtonGroup()
        self.plane_radio_buttons = {}
        
        # 3x2 grid layout for plane options
        self.radio_button_frame = QtWidgets.QFrame()
        self.radio_button_frame.setStyleSheet("QFrame { background-color: transparent; margin: 0px}")
        radio_button_layout = QtWidgets.QGridLayout(self.radio_button_frame)
        set_margin_space(radio_button_layout,4,4)
        
        current_plane = CoordinatePlaneConfig.get_current_plane_name()
        
        # Define the main planes (without flipped versions)
        main_planes = ['XY', 'XZ', 'YZ']
        
        for i, plane_key in enumerate(main_planes):
            plane_config = CoordinatePlaneConfig.PLANES[plane_key]
            radio = CustomRadioButton(f"{plane_config['name']}", group=True, height=16)
            radio.group('plane_selector')
            radio.setToolTip(plane_config['description'])
            
            # Check if this plane is currently selected (including flipped versions)
            is_current = (plane_key == current_plane or 
                         (plane_key == 'XY' and current_plane == 'XY_FLIPPED') or
                         (plane_key == 'XZ' and current_plane == 'XZ_FLIPPED') or
                         (plane_key == 'YZ' and current_plane == 'YZ_FLIPPED'))
            
            if is_current:
                radio.setChecked(True)
            
            # Connect to canvas method if available
            if self.canvas:
                radio.toggled.connect(lambda checked, key=plane_key: self._on_plane_changed(key) if checked else None)
            
            self.plane_button_group.addButton(radio)
            self.plane_radio_buttons[plane_key] = radio
            
            # Place in first row
            radio_button_layout.addWidget(radio, 0, i+1)

        # Add negative checkbox in second row
        self.negative_checkbox = CustomRadioButton("", height=12, width=6, fill = True, color = "#b30718")
        self.negative_checkbox.setToolTip("Flip the Y or Z axis (creates -XY, -XZ, or -YZ)")
        
        # Check if negative mode is currently active
        is_negative = current_plane in ['XY_FLIPPED', 'XZ_FLIPPED', 'YZ_FLIPPED']
        self.negative_checkbox.setChecked(is_negative)
        
        if self.canvas:
            self.negative_checkbox.toggled.connect(self._on_negative_changed)
        
        # Place checkbox in second row, centered
        radio_button_layout.addWidget(self.negative_checkbox, 0, 0)
        
        flat_plane_layout.addWidget(self.radio_button_frame)
        main_layout.addWidget(self.flat_plane_frame)
        
        self.radio_button_frame.setVisible(not auto_detect_enabled)
        # Set initial visibility based on auto-detect state
        #self.desc_label.setVisible(not auto_detect_enabled)
        #self.flat_plane_frame.setVisible(not auto_detect_enabled)
        
        main_layout.addStretch()
        #-------------------------------------------------------------------------------------------------------------------
        # Add current settings display
        self.settings_label = QtWidgets.QLabel()
        self.settings_label.setStyleSheet("""
            QLabel {
                color: #999999;
                font-style: italic;
                font-size: 11px;
                background-color: transparent;
                border: none;
                padding: 4px 0px;
            }
        """)
        self.update_settings_display()
        #main_layout.addWidget(self.settings_label)
        #-------------------------------------------------------------------------------------------------------------------
        
    
    def _on_plane_changed(self, plane_key):
        """Handle plane selection change"""
        if self.canvas:
            # Determine if we should use flipped version based on negative checkbox
            is_negative = self.negative_checkbox.isChecked()
            final_plane_key = f"{plane_key}_FLIPPED" if is_negative else plane_key
            
            self.canvas.set_coordinate_plane(final_plane_key)
            self.update_settings_display()
    
    def _on_negative_changed(self, is_negative):
        """Handle negative checkbox change"""
        if self.canvas:
            # Get currently selected plane
            current_plane = CoordinatePlaneConfig.get_current_plane_name()
            
            # Determine the base plane (remove _FLIPPED suffix if present)
            base_plane = current_plane.replace('_FLIPPED', '')
            
            # Set the new plane with or without flipped suffix
            final_plane_key = f"{base_plane}_FLIPPED" if is_negative else base_plane
            
            self.canvas.set_coordinate_plane(final_plane_key)
            self.update_settings_display()
    
    def _on_spline_mode_changed(self, separate_splines):
        """Handle spline mode change"""
        if self.canvas:
            self.canvas.set_separate_splines_mode(separate_splines)
            self.update_settings_display()
    
    def _on_auto_detect_changed(self, enabled):
        """Handle auto-detection checkbox change"""
        if self.canvas:
            self.canvas.set_auto_detect_plane_mode(enabled)
            if enabled:
                print("Auto-detection enabled - coordinate plane will be automatically detected from selected curves")
            else:
                print("Auto-detection disabled - using manually selected coordinate plane")
        
        # Show/hide the manual plane selection elements
        #self.desc_label.setVisible(not enabled)
        #self.flat_plane_frame.setVisible(not enabled)
        self.radio_button_frame.setVisible(not enabled)
    
    def update_settings_display(self):
        """Update the current settings display"""
        if self.canvas:
            summary = self.canvas.get_curve_import_settings_summary()
            self.settings_label.setText(f"Current: {summary}")
        else:
            plane_name = CoordinatePlaneConfig.get_current_plane()['name']
            self.settings_label.setText(f"Current: Plane: {plane_name} | Mode: Separate")
    
    def refresh_display(self):
        """Refresh the display to show current settings"""
        # Update radio button states
        current_plane = CoordinatePlaneConfig.get_current_plane_name()
        
        # Determine which base plane is selected (including flipped versions)
        base_plane = current_plane.replace('_FLIPPED', '')
        
        for plane_key, radio in self.plane_radio_buttons.items():
            # Check if this plane is currently selected (including flipped versions)
            is_current = (plane_key == current_plane or 
                         (plane_key == 'XY' and current_plane == 'XY_FLIPPED') or
                         (plane_key == 'XZ' and current_plane == 'XZ_FLIPPED') or
                         (plane_key == 'YZ' and current_plane == 'YZ_FLIPPED'))
            radio.setChecked(is_current)
        
        # Update negative checkbox
        is_negative = current_plane in ['XY_FLIPPED', 'XZ_FLIPPED', 'YZ_FLIPPED']
        self.negative_checkbox.setChecked(is_negative)
        
        # Update spline mode
        separate_splines = True
        if self.canvas:
            separate_splines = self.canvas.get_separate_splines_mode()
        
        for mode_key, radio in self.spline_radio_buttons.items():
            if mode_key == 'separate':
                radio.setChecked(separate_splines)
            else:
                radio.setChecked(not separate_splines)
        
        # Update settings display
        self.update_settings_display()
    
    def reset_settings(self):
        """Reset settings and refresh display"""
        if self.canvas:
            self.canvas.reset_curve_import_settings()
            self.refresh_display()
    
    def handle_refresh(self):
        """Handle refresh action"""
        self.refresh_display() 