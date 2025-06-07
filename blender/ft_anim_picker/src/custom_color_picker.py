import sys
import colorsys
from pathlib import Path

# Try PySide6 first, fallback to PySide2
try:
    from PySide6 import QtWidgets, QtCore, QtGui
    from PySide6.QtWidgets import (QApplication, QWidget, QVBoxLayout, QHBoxLayout, 
                                   QSlider, QLabel, QLineEdit, QPushButton, QFrame)
    from PySide6.QtCore import Qt, QTimer, Signal
    from PySide6.QtGui import (QColor, QPalette, QPixmap, QPainter, QLinearGradient, 
                               QBrush, QCursor, QScreen, QFont, QRegularExpressionValidator,
                               QPainterPath, QPen)
    from PySide6.QtCore import QRegularExpression
    PYSIDE_VERSION = 6
except ImportError:
    from PySide2 import QtWidgets, QtCore, QtGui
    from PySide2.QtWidgets import (QApplication, QWidget, QVBoxLayout, QHBoxLayout, 
                                   QSlider, QLabel, QLineEdit, QPushButton, QFrame)
    from PySide2.QtCore import Qt, QTimer, Signal
    from PySide2.QtGui import (QColor, QPalette, QPixmap, QPainter, QLinearGradient, 
                               QBrush, QCursor, QScreen, QFont, QRegExpValidator,
                               QPainterPath, QPen)
    from PySide2.QtCore import QRegExp
    PYSIDE_VERSION = 2

from . import utils as UT

class CursorPreviewWidget(QWidget):
    """A small widget that follows the cursor and shows the sampled color"""
    def __init__(self):
        super().__init__()
        self.setWindowFlags(Qt.WindowStaysOnTopHint | Qt.FramelessWindowHint | Qt.Tool)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setFixedSize(60, 60)
        self.current_color = QColor(255, 255, 255)
        
    def set_color(self, color):
        self.current_color = color
        self.update()
        
    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        
        # Draw outer ring
        painter.setPen(QPen(QColor(0, 0, 0), 3))
        painter.setBrush(QColor(255, 255, 255))
        painter.drawEllipse(5, 5, 50, 50)
        
        # Draw color circle
        painter.setPen(QPen(QColor(60, 60, 60), 2))
        painter.setBrush(self.current_color)
        painter.drawEllipse(10, 10, 40, 40)
        
        # Draw crosshair
        painter.setPen(QPen(QColor(255, 255, 255), 2))
        painter.drawLine(30, 15, 30, 25)
        painter.drawLine(30, 35, 30, 45)
        painter.drawLine(15, 30, 25, 30)
        painter.drawLine(35, 30, 45, 30)
        
        painter.setPen(QPen(QColor(0, 0, 0), 1))
        painter.drawLine(30, 15, 30, 25)
        painter.drawLine(30, 35, 30, 45)
        painter.drawLine(15, 30, 25, 30)
        painter.drawLine(35, 30, 45, 30)

class ColorSlider(QSlider):
    def __init__(self, orientation=Qt.Horizontal):
        super().__init__(orientation)
        self.setMinimum(0)
        self.setMaximum(100)
        self.setValue(0)
        # Increase height to accommodate the handle above the track
        self.setFixedHeight(24)  # Increased from 8 to 32
        self.gradient_colors = []
        self._updating_gradient = False  # Flag to prevent recursive updates
        
    def set_gradient_colors(self, colors):
        self.gradient_colors = colors
        self._updating_gradient = True
        self.update()
        self._updating_gradient = False
        
    def paintEvent(self, event):
        # Custom paint to show gradient background
        if self.gradient_colors:
            painter = QPainter(self)
            painter.setRenderHint(QPainter.Antialiasing)
            
            # Define track area (centered vertically)
            track_height = 14
            track_y = (self.height() - track_height) // 2  # Center track vertically
            track_rect = QtCore.QRect(10, track_y, self.width() - 20, track_height)
            
            # Create gradient for track
            gradient = QLinearGradient(0, 0, track_rect.width(), 0)
            for i, color in enumerate(self.gradient_colors):
                gradient.setColorAt(i / (len(self.gradient_colors) - 1), QColor(*color))
            
            # Create path with rounded corners for track
            path = QPainterPath()
            corner_radius = 7
            path.addRoundedRect(track_rect, corner_radius, corner_radius)
            
            # Draw gradient background with rounded corners
            painter.fillPath(path, QBrush(gradient))
            
            # Add a subtle border to track
            painter.setPen(QColor(80, 80, 80, 0))
            painter.drawPath(path)
            
            # Draw handle centered vertically on the slider
            painter.setRenderHint(QPainter.Antialiasing)
            handle_pos = int((self.value() / self.maximum()) * (track_rect.width())) + track_rect.x()
            handle_y = (self.height() - 16) // 2  # Center handle vertically (16 is handle diameter)
            
            # Draw handle shadow
            painter.setPen(QColor(0, 0, 0, 0))
            painter.setBrush(QColor(0, 0, 0, 60))
            painter.drawEllipse(handle_pos - 7, handle_y + 1, 16, 16)
            
            # Draw main handle
            #painter.setPen(QColor(200, 200, 200))
            painter.setBrush(QColor(255, 255, 255))
            painter.drawEllipse(handle_pos - 8, handle_y, 16, 16)
            
            # Add inner highlight to handle
            #painter.setPen(QColor(255, 255, 255, 180))
            #painter.setBrush(QColor(255, 255, 255, 50))
            #painter.drawEllipse(handle_pos - 6, handle_y + 2, 12, 12)
            
        else:
            super().paintEvent(event)
    
    def mousePressEvent(self, event):
        # Prevent interaction during gradient updates
        if self._updating_gradient:
            return
            
        # Adjust mouse interaction to work with centered layout
        if event.button() == Qt.LeftButton:
            track_height = 8
            track_y = (self.height() - track_height) // 2
            track_rect = QtCore.QRect(10, track_y, self.width() - 20, track_height)
            
            # Allow clicking anywhere on the slider area
            if 0 <= event.pos().x() <= self.width():
                # Calculate value based on x position
                relative_x = event.pos().x() - track_rect.x()
                if relative_x < 0:
                    relative_x = 0
                elif relative_x > track_rect.width():
                    relative_x = track_rect.width()
                
                value = int((relative_x / track_rect.width()) * self.maximum())
                self.setValue(value)
                self.sliderPressed.emit()
        
        super().mousePressEvent(event)
    
    def mouseMoveEvent(self, event):
        # Prevent interaction during gradient updates
        if self._updating_gradient:
            return
            
        # Handle dragging
        if event.buttons() & Qt.LeftButton:
            track_height = 8
            track_y = (self.height() - track_height) // 2
            track_rect = QtCore.QRect(10, track_y, self.width() - 20, track_height)
            
            relative_x = event.pos().x() - track_rect.x()
            if relative_x < 0:
                relative_x = 0
            elif relative_x > track_rect.width():
                relative_x = track_rect.width()
            
            value = int((relative_x / track_rect.width()) * self.maximum())
            self.setValue(value)
        
        super().mouseMoveEvent(event)
    
    def wheelEvent(self, event):
        # Override wheelEvent to prevent mouse wheel from changing the slider value
        event.ignore()

class ColorPicker(QWidget):
    colorChanged = Signal(QColor)
    
    def __init__(self, sample_hex=False, palette=False):
        super().__init__()
        self.sample_hex_mode = sample_hex  # Store the UI mode
        self.palette_mode = palette
        self.current_color = QColor(186, 24, 24)  # Default red color like in image
        self.sampling = False
        self.cursor_preview = None
        self._updating_sliders = False  # Flag to prevent recursive updates
        self.sliders_visible = False  # Track slider visibility
        self.color_palette_widget = None  # For the popup color palette
        self.setup_ui()
        self.update_all_from_color()
        
    def setup_ui(self):
        self.setWindowTitle("Color Picker")
        self.setStyleSheet("""
            QWidget {
                background-color: transparent;
                color: white;
                font-family: Arial;
                font-size: 12px;
            }
            QLineEdit {
                background-color: #404040;
                border: 1px solid #666;
                padding: 5px;
                border-radius: 3px;
            }
            QPushButton {
                background-color: #404040;
                border: 1px solid #666;
                padding: 8px;
                border-radius: 3px;
            }
            QPushButton:hover {
                background-color: #505050;
            }
            QPushButton:pressed {
                background-color: #606060;
            }
            QFrame {
                background-color: #1e1e1e;
                border: 0px solid rgba(255, 255, 255, 0.2);
                padding: 0px;
                border-radius: 3px;
            }
            QLabel {
                color: rgba(255, 255, 255, 0.8);
                border: none;
                background-color: transparent;
            }
            QToolTip {
                background-color: #404040;
                padding: 2px;
                border-radius: 3px;
            }
            
        """)
        
        self.main_layout = QVBoxLayout()
        self.set_margin_space(self.main_layout, 0, 0)

        self.frame = QFrame()
        self.frame.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Fixed)
        self.frame_layout = QVBoxLayout(self.frame)
        self.set_margin_space(self.frame_layout, 4 if self.sample_hex_mode else 6, 4)
        
        if not self.sample_hex_mode and not self.palette_mode:
            self.color_label = QLabel("Color")
            self.color_label.setStyleSheet("color: #444444;")
            self.frame_layout.addWidget(self.color_label)

        # Top section with color display and hex input (always visible)
        self.create_top_section(self.frame_layout if not self.palette_mode else self.main_layout)
        
        # HSV Sliders (only in full mode and initially hidden)
        if not self.sample_hex_mode:
            self.sliders_widget = QWidget()
            self.sliders_widget.setStyleSheet(f"""QWidget {{background-color: #222222; padding: 0px; 
            border-radius: 3px; border: 0px solid #666666;}}
            QLabel {{color: #aaaaaa; border: none;font-size: 11px;}}""")
            self.sliders_layout = QVBoxLayout(self.sliders_widget)
            self.set_margin_space(self.sliders_layout, 4, 2)
            self.create_sliders(self.sliders_layout)
            self.sliders_widget.hide()  # Initially hidden
            self.frame_layout.addWidget(self.sliders_widget)
        
        if not self.palette_mode:
            self.main_layout.addWidget(self.frame)
        self.setLayout(self.main_layout)
    
    def set_margin_space(self,layout,margin,space):
        layout.setContentsMargins(margin,margin,margin,margin)
        layout.setSpacing(space)
    
    def create_top_section(self, layout):
        if self.sample_hex_mode:
            # Sample hex mode: hex input, color display, picker button in horizontal layout
            top_layout = QHBoxLayout()
            self.set_margin_space(top_layout, 0, 4)
            h = 16
            # Hex input
            self.hex_input = QLineEdit()
            self.hex_input.setStyleSheet("border: 1px solid #444444; border-radius: 3px; color: #777777; padding: 1px;")
            self.hex_input.setAlignment(Qt.AlignCenter)
            self.hex_input.setFixedSize(60,h)
            self.hex_input.setMaxLength(7)
            self.hex_input.setToolTip("Color Hex code")
            
            # Validator for hex input - compatible with both PySide versions
            if PYSIDE_VERSION == 6:
                hex_validator = QRegularExpressionValidator(QRegularExpression("^#?[0-9A-Fa-f]{0,6}$"))
            else:
                hex_validator = QRegExpValidator(QRegExp("^#?[0-9A-Fa-f]{0,6}$"))

            self.hex_input.setValidator(hex_validator)
            self.hex_input.textChanged.connect(self.on_hex_changed)
            
            # Color display
            self.color_display = QPushButton()
            self.color_display.setFixedSize(h, h)
            self.color_display.setStyleSheet(f"border: 1px solid {UT.rgba_value(self.current_color,1.2)}; border-radius: 3px;")
            self.color_display.setToolTip("Right click: show color palette")
            self.color_display.setContextMenuPolicy(Qt.CustomContextMenu)
            self.color_display.customContextMenuRequested.connect(self.show_color_palette)
            self.color_display.clicked.connect(self.show_color_palette)

            
            # Color picker button
            self.picker_btn = QPushButton("")
            self.picker_btn.setIcon(QtGui.QIcon(get_icon('color_picker.png', opacity=0.8)))
            self.picker_btn.setIconSize(QtCore.QSize(h-2, h-2))
            self.picker_btn.setFixedHeight(h)
            self.picker_btn.setStyleSheet("border: 0px solid #666; border-radius: 3px; background-color: #333333;")
            self.picker_btn.setToolTip("Pick color from screen")
            self.picker_btn.clicked.connect(self.toggle_color_sampling)
            
            top_layout.addWidget(self.hex_input)
            top_layout.addWidget(self.color_display)
            top_layout.addWidget(self.picker_btn)
            
            layout.addLayout(top_layout)
        elif self.palette_mode:
            top_layout = QHBoxLayout()
            self.set_margin_space(top_layout, 0, 4)
            h = 18
            # Color display
            self.color_display = QPushButton()
            self.color_display.setFixedSize(h, h)
            self.color_display.setStyleSheet(f"border: 1px solid {UT.rgba_value(self.current_color,1.2)}; border-radius: 3px;")
            self.color_display.setToolTip("Right click: show color palette")
            #self.color_display.setContextMenuPolicy(Qt.CustomContextMenu)
            self.color_display.clicked.connect(self.show_color_palette)
            top_layout.addWidget(self.color_display)
            layout.addLayout(top_layout)
        else:
            # Full mode: original layout
            top_layout = QHBoxLayout()
            self.set_margin_space(top_layout, 0, 4)
            
            # Color picker button
            self.picker_btn = QPushButton("")
            self.picker_btn.setIcon(QtGui.QIcon(get_icon('color_picker.png', opacity=0.8)))
            self.picker_btn.setIconSize(QtCore.QSize(22, 22))
            self.picker_btn.setFixedSize(24, 24)
            self.picker_btn.setStyleSheet("border: 0px solid #666; border-radius: 3px; background-color: #333333;")
            self.picker_btn.setToolTip("Pick color from screen")
            self.picker_btn.clicked.connect(self.toggle_color_sampling)
            
            # Color display - clickable to toggle sliders
            self.color_display = QPushButton()
            self.color_display.setFixedHeight(24)
            self.color_display.setStyleSheet(f"border: 1px solid {UT.rgba_value(self.current_color,1.2)}; border-radius: 3px;")
            self.color_display.setToolTip("Left click: show/hide sliders\nRight click: show color palette")
            self.color_display.clicked.connect(self.toggle_sliders)
            self.color_display.setContextMenuPolicy(Qt.CustomContextMenu)
            self.color_display.customContextMenuRequested.connect(self.show_color_palette)

            top_layout.addWidget(self.color_display)
            top_layout.addWidget(self.picker_btn)

            layout.addLayout(top_layout)
    
    def create_sliders(self, layout):
        # Only create sliders in full mode
        if self.sample_hex_mode:
            return
            
        # Hue slider
        hue_layout = QHBoxLayout()
        self.set_margin_space(hue_layout, 0, 2)
        hue_label = QLabel("H")
        self.hue_slider = ColorSlider()
        self.hue_slider.setMaximum(360)
        self.hue_slider.setValue(0)
        hue_colors = [(255, 0, 0), (255, 255, 0), (0, 255, 0), 
                      (0, 255, 255), (0, 0, 255), (255, 0, 255), (255, 0, 0)]
        self.hue_slider.set_gradient_colors(hue_colors)
        self.hue_slider.valueChanged.connect(self.on_hue_changed)
        hue_layout.addWidget(hue_label)
        hue_layout.addWidget(self.hue_slider)
        layout.addLayout(hue_layout)
        
        # Saturation slider
        sat_layout = QHBoxLayout()
        self.set_margin_space(sat_layout, 0, 2)
        sat_label = QLabel("S")
        self.sat_slider = ColorSlider()
        self.sat_slider.valueChanged.connect(self.on_saturation_changed)
        sat_layout.addWidget(sat_label)
        sat_layout.addWidget(self.sat_slider)
        layout.addLayout(sat_layout)
        
        # Value slider
        val_layout = QHBoxLayout()
        self.set_margin_space(val_layout, 0, 2)
        val_label = QLabel("V")
        self.val_slider = ColorSlider()
        self.val_slider.valueChanged.connect(self.on_value_changed)
        val_layout.addWidget(val_label)
        val_layout.addWidget(self.val_slider)
        layout.addLayout(val_layout)

        # Hex section (in full mode, hex input is part of sliders)
        self.hex_input = QLineEdit()
        self.hex_input.setStyleSheet("border: 1px solid #444444; border-radius: 3px; color: #777777;")
        self.hex_input.setAlignment(Qt.AlignCenter)
        self.hex_input.setFixedHeight(24)
        self.hex_input.setMaxLength(7)

        # Validator for hex input - compatible with both PySide versions
        if PYSIDE_VERSION == 6:
            hex_validator = QRegularExpressionValidator(QRegularExpression("^#?[0-9A-Fa-f]{0,6}$"))
        else:
            hex_validator = QRegExpValidator(QRegExp("^#?[0-9A-Fa-f]{0,6}$"))

        self.hex_input.setValidator(hex_validator)
        self.hex_input.textChanged.connect(self.on_hex_changed)
        
        layout.addWidget(self.hex_input)
        
    def show_color_palette(self, position):
        """Show color palette widget on right click"""
        if self.color_palette_widget and self.color_palette_widget.isVisible():
            self.color_palette_widget.close()
            return
            
        # Create color palette widget
        self.color_palette_widget = QWidget()
        self.color_palette_widget.setWindowFlags(Qt.Popup | Qt.FramelessWindowHint)
        self.color_palette_widget.setStyleSheet('background-color:#222222; border: 1px solid #666; border-radius: 3px;')
        color_layout = QtWidgets.QGridLayout(self.color_palette_widget)
        color_layout.setSpacing(5)
        color_layout.setContentsMargins(6,6,6,6)
        
        color_palette = [
            "#66B2FF", "#C299FF", "#d8ecaa", "#edea8e", "#e6e6e6",
            "#3399FF", "#A366FF", "#a5d631", "#fbdc0e", "#b3b3b3",
            "#007FFF", "#8033FF", "#a0a617", "#fba70b", "#808080",
            "#0059B2", "#5C00B2", "#708622", "#e06202", "#4d4d4d",
            "#002F80", "#2A004D", "#3d7218", "#ec2d2d", "#000000"
        ]
        
        for i, color in enumerate(color_palette):
            color_button = QPushButton()
            color_button.setFixedSize(20, 20)
            color_button.setStyleSheet(f"""
                QPushButton {{
                    background-color: {color}; 
                    border: 0px solid #444; 
                    border-radius: 3px;
                }} 
                QPushButton:hover {{
                    border: 2px solid #888;
                }}
            """)
            color_layout.addWidget(color_button, i // 5, i % 5)
            
            # Connect color selection
            try:
                color_button.clicked.connect(lambda checked, c=color: self.select_palette_color(c))
            except:
                from functools import partial
                color_button.clicked.connect(partial(self.select_palette_color, color))
        
        if position is not None and hasattr(position, 'x'):
        # Called from context menu with a QPoint position
            global_pos = self.color_display.mapToGlobal(position)
            self.color_palette_widget.move(global_pos.x(), global_pos.y() + 25)
        else:
            # Called from left click or without position - position relative to color display
            global_pos = self.color_display.mapToGlobal(QtCore.QPoint(0, 0))
            self.color_palette_widget.move(global_pos.x(), global_pos.y() + self.color_display.height() + 5)
        self.color_palette_widget.show()
    
    def select_palette_color(self, color_hex):
        """Select a color from the palette"""
        color = QColor(color_hex)
        if color.isValid():
            self.current_color = color
            self.update_all_from_color()
        
        # Close the palette widget
        if self.color_palette_widget:
            self.color_palette_widget.close()
            self.color_palette_widget = None
        
        #selecting palette color should copy the color hex to clipboard
        clipboard = QApplication.clipboard()
        clipboard.setText(color_hex)
        
        
    
    def toggle_sliders(self):
        """Toggle the visibility of HSV sliders (only in full mode)"""
        if self.sample_hex_mode:
            return
            
        self.sliders_visible = not self.sliders_visible
        
        if self.sliders_visible:
            self.sliders_widget.show()
            # Update gradients when showing sliders
            self.update_saturation_gradient()
            self.update_value_gradient()
        else:
            self.sliders_widget.hide()
        
        # Adjust window size to fit content
        self.adjustSize()
        
    def update_saturation_gradient(self):
        if self.sample_hex_mode or not hasattr(self, 'hue_slider'):
            return
        h = self.hue_slider.value()
        sat_colors = []
        for s in [0, 100]:
            rgb = colorsys.hsv_to_rgb(h/360.0, s/100.0, 1.0)
            sat_colors.append((int(rgb[0]*255), int(rgb[1]*255), int(rgb[2]*255)))
        self.sat_slider.set_gradient_colors(sat_colors)
        
    def update_value_gradient(self):
        if self.sample_hex_mode or not hasattr(self, 'hue_slider'):
            return
        h = self.hue_slider.value()
        s = self.sat_slider.value()
        val_colors = []
        for v in [0, 100]:
            rgb = colorsys.hsv_to_rgb(h/360.0, s/100.0, v/100.0)
            val_colors.append((int(rgb[0]*255), int(rgb[1]*255), int(rgb[2]*255)))
        self.val_slider.set_gradient_colors(val_colors)
    
    def on_hue_changed(self):
        if self._updating_sliders or self.sample_hex_mode:
            return
        self.update_saturation_gradient()
        self.update_value_gradient()
        self.update_color_from_sliders()
    
    def on_saturation_changed(self):
        if self._updating_sliders or self.sample_hex_mode:
            return
        self.update_value_gradient()
        self.update_color_from_sliders()
    
    def on_value_changed(self):
        if self._updating_sliders or self.sample_hex_mode:
            return
        self.update_color_from_sliders()
    
    def update_color_from_sliders(self):
        """Update color based on current slider values (only in full mode)"""
        if self.sample_hex_mode:
            return
            
        h = self.hue_slider.value() / 360.0
        s = self.sat_slider.value() / 100.0
        v = self.val_slider.value() / 100.0
        
        rgb = colorsys.hsv_to_rgb(h, s, v)
        self.current_color = QColor(int(rgb[0]*255), int(rgb[1]*255), int(rgb[2]*255))
        
        self.update_color_display()
        self.update_hex_input()
        self.colorChanged.emit(self.current_color)
        
    def on_hex_changed(self):
        if self._updating_sliders:
            return
        hex_text = self.hex_input.text().strip()
        if not hex_text.startswith('#'):
            hex_text = '#' + hex_text
            
        if len(hex_text) == 7:
            try:
                color = QColor(hex_text)
                if color.isValid():
                    self.current_color = color
                    if not self.sample_hex_mode:
                        self.update_sliders_from_color()
                    self.update_color_display()
                    self.colorChanged.emit(self.current_color)
            except:
                pass
                
    def update_color_display(self):
        color = self.current_color
        if self.sample_hex_mode:
            # In sample hex mode, color display is a fixed size square
            self.color_display.setStyleSheet(f"""
                QPushButton {{
                    background-color: rgb({color.red()}, {color.green()}, {color.blue()});
                    border: 1px solid rgba(255, 255, 255, .1);
                    border-radius: 3px;
                }}
                QPushButton:hover {{
                    border: 2px solid {UT.rgba_value(self.current_color,1.2)};
                }}
            """)
        else:
            # In full mode, color display is expandable
            self.color_display.setStyleSheet(f"""
                QPushButton {{
                    background-color: rgb({color.red()}, {color.green()}, {color.blue()});
                    border: 1px solid rgba(255, 255, 255, .1);
                    border-radius: 3px;
                }}
                QPushButton:hover {{
                    border: 2px solid {UT.rgba_value(self.current_color,1.2)};
                }}
            """)
        
    def update_hex_input(self):
        hex_color = self.current_color.name().upper()
        if self.hex_input.text() != hex_color:
            self._updating_sliders = True
            self.hex_input.setText(hex_color)
            self._updating_sliders = False
            
    def update_sliders_from_color(self):
        """Update sliders based on current color (only in full mode)"""
        if self.sample_hex_mode:
            return
            
        self._updating_sliders = True
        
        color = self.current_color
        h, s, v = colorsys.rgb_to_hsv(color.red()/255.0, color.green()/255.0, color.blue()/255.0)
        
        # Update slider values
        self.hue_slider.setValue(int(h * 360))
        self.sat_slider.setValue(int(s * 100))
        self.val_slider.setValue(int(v * 100))
        
        # Update gradients only if sliders are visible
        if self.sliders_visible:
            self.update_saturation_gradient()
            self.update_value_gradient()
        
        self._updating_sliders = False
        
    def update_all_from_color(self):
        if not self.sample_hex_mode:
            self.update_sliders_from_color()
        self.update_color_display()
        self.update_hex_input()
        # Update gradients only if sliders are visible and in full mode
        if not self.sample_hex_mode and self.sliders_visible:
            self.update_saturation_gradient()
            self.update_value_gradient()
        # Always emit the signal when updating from a new color
        self.colorChanged.emit(self.current_color)
        
    def toggle_color_sampling(self):
        if self.sampling:
            self.stop_sampling()
        else:
            self.start_color_sampling()
    
    def start_color_sampling(self):
        self.sampling = True
        self.picker_btn.setIcon(QtGui.QIcon(get_icon('color_picker.png', opacity=0.8)))
        self.picker_btn.setStyleSheet("""
            QPushButton {
                background-color: #ff4444;
                border: 1px solid #ff6666;
                color: white;
            }
        """)
        
        # Create cursor preview widget
        self.cursor_preview = CursorPreviewWidget()
        self.cursor_preview.show()
        
        # Keep default arrow cursor during sampling
        self.original_cursor = QApplication.overrideCursor()
        # Don't change cursor - keep default arrow
        
        # Install global event filter to capture mouse clicks
        QApplication.instance().installEventFilter(self)
        
        # Grab mouse to ensure we get all mouse events
        self.grabMouse()
        
        # Start timer to sample color under cursor
        self.sample_timer = QTimer()
        self.sample_timer.timeout.connect(self.sample_color_under_cursor)
        self.sample_timer.start(50)  # Sample every 50ms
        
    def sample_color_under_cursor(self):
        if not self.sampling:
            return
            
        # Get screen and cursor position
        screen = QApplication.primaryScreen()
        if screen:
            cursor_pos = QCursor.pos()
            
            # Update cursor preview position
            if self.cursor_preview:
                self.cursor_preview.move(cursor_pos.x() + 20, cursor_pos.y() + 20)
            
            # Sample color at cursor position
            if PYSIDE_VERSION == 6:
                pixmap = screen.grabWindow(0, cursor_pos.x(), cursor_pos.y(), 1, 1)
            else:
                pixmap = screen.grabWindow(0, cursor_pos.x(), cursor_pos.y(), 1, 1)
            
            if not pixmap.isNull():
                image = pixmap.toImage()
                if not image.isNull():
                    if PYSIDE_VERSION == 6:
                        color = QColor(image.pixelColor(0, 0))
                    else:
                        color = QColor(image.pixel(0, 0))
                    if color.isValid():
                        self.current_color = color
                        self.update_all_from_color()
                        
                        # Update cursor preview
                        if self.cursor_preview:
                            self.cursor_preview.set_color(color)
    
    def eventFilter(self, obj, event):
        """Global event filter to capture mouse clicks during sampling"""
        if self.sampling:
            if event.type() == QtCore.QEvent.MouseButtonPress:
                if event.button() == Qt.LeftButton:
                    self.stop_sampling()
                    return True  # Consume the event
            elif event.type() == QtCore.QEvent.KeyPress:
                if event.key() == Qt.Key_Escape:
                    self.stop_sampling()
                    return True
                elif event.key() == Qt.Key_Return or event.key() == Qt.Key_Enter:
                    self.stop_sampling()
                    return True
        return False
                        
    def keyPressEvent(self, event):
        if self.sampling:
            if event.key() == Qt.Key_Escape:
                self.stop_sampling()
            elif event.key() == Qt.Key_Return or event.key() == Qt.Key_Enter:
                self.stop_sampling()
        super().keyPressEvent(event)
        
    def stop_sampling(self):
        if hasattr(self, 'sample_timer'):
            self.sample_timer.stop()
        
        # Release mouse grab
        self.releaseMouse()
        
        # Remove global event filter
        QApplication.instance().removeEventFilter(self)
        
        # Clean up cursor preview
        if self.cursor_preview:
            self.cursor_preview.close()
            self.cursor_preview = None
        
        # Reset cursor
        QApplication.restoreOverrideCursor()
        if self.original_cursor:
            QApplication.setOverrideCursor(self.original_cursor)
        
        self.sampling = False
        self.picker_btn.setIcon(QtGui.QIcon(get_icon('color_picker.png', opacity=0.8)))
        self.picker_btn.setStyleSheet("border: 0px solid #666; border-radius: 3px; background-color: #333333;")

        #copy color hex to clipboard
        clipboard = QApplication.clipboard()
        clipboard.setText(self.current_color.name())
    
    def closeEvent(self, event):
        """Clean up when widget is closed"""
        # Close color palette if open
        if self.color_palette_widget and self.color_palette_widget.isVisible():
            self.color_palette_widget.close()
        
        # Stop sampling if active
        if self.sampling:
            self.stop_sampling()
            
        super().closeEvent(event)


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

class MainWindow(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("HSV Color Picker")
        layout = QVBoxLayout()
        
        self.color_picker = ColorPicker()
        self.color_picker.colorChanged.connect(self.on_color_changed)
        layout.addWidget(self.color_picker)
        
        self.setLayout(layout)
        
    def on_color_changed(self, color):
        print(f"Color changed: {color.name()}")

if __name__ == "__main__":
    app = QApplication(sys.argv)
    
    print(f"Using PySide{PYSIDE_VERSION}")
    
    window = MainWindow()
    window.show()
    
    sys.exit(app.exec_() if PYSIDE_VERSION == 2 else app.exec())