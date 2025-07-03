import sys
import colorsys
from pathlib import Path
from enum import Enum

# Try PySide6 first, fallback to PySide2
try:
    from PySide6 import QtWidgets, QtCore, QtGui
    from PySide6.QtWidgets import (QApplication, QWidget, QVBoxLayout, QHBoxLayout, 
                                   QSlider, QLabel, QLineEdit, QPushButton, QFrame, QSizePolicy)
    from PySide6.QtCore import Qt, QTimer, Signal, QPointF, QRectF
    from PySide6.QtGui import (QColor, QPalette, QPixmap, QPainter, QLinearGradient, 
                               QBrush, QCursor, QScreen, QFont, QRegularExpressionValidator,
                               QPainterPath, QPen, QRadialGradient)
    from PySide6.QtCore import QRegularExpression
    PYSIDE_VERSION = 6
except ImportError:
    from PySide2 import QtWidgets, QtCore, QtGui
    from PySide2.QtWidgets import (QApplication, QWidget, QVBoxLayout, QHBoxLayout, 
                                   QSlider, QLabel, QLineEdit, QPushButton, QFrame, QSizePolicy)
    from PySide2.QtCore import Qt, QTimer, Signal, QPointF, QRectF
    from PySide2.QtGui import (QColor, QPalette, QPixmap, QPainter, QLinearGradient, 
                               QBrush, QCursor, QScreen, QFont, QRegExpValidator,
                               QPainterPath, QPen, QRadialGradient)
    from PySide2.QtCore import QRegExp
    PYSIDE_VERSION = 2

from . import utils as UT
from .utils import get_icon

#-----------------------------------------------------------------------------------------------------------------------------------------------
class ColorPickerMode(Enum):
    HSV = "hsv"
    HEX = "hex" 
    PALETTE = "palette"
    SQUARE = "square"

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
#-----------------------------------------------------------------------------------------------------------------------------------------------
class ColorSlider(QSlider):
    def __init__(self, vertical=False, radius=7, width=None, height=14, handle_size=16):
        orientation = Qt.Vertical if vertical else Qt.Horizontal
        super().__init__(orientation)
        self.setMinimum(0)
        self.setMaximum(100)
        self.setValue(0)
        
        # Store dimensions and properties
        self.gradient_colors = []
        self._updating_gradient = False
        self.radius = radius
        self.slider_width = width if width is not None else 100  # Default fallback
        self.slider_height = height
        self.vertical = vertical
        self.handle_size = handle_size  # Diameter of the handle
        self.handle_radius = handle_size // 2  # Radius for calculations
        
        # Set size based on orientation and whether width is specified
        if not vertical:  # Horizontal
            # Make sure height is at least handle_size + some padding
            fixed_height = max(height, handle_size + 4)
            self.setFixedHeight(fixed_height)
            
            if width is not None:
                # Fixed width behavior
                self.setFixedWidth(width)
            else:
                # Expandable width behavior
                self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
                self.setMinimumWidth(50)  # Minimum reasonable width
        else:  # Vertical
            # Make sure width is at least handle_size + some padding
            fixed_width = max(height, handle_size + 4)
            self.setFixedWidth(fixed_width)
            
            if width is not None:
                # Fixed height behavior for vertical slider
                self.setFixedHeight(width)
            else:
                # Expandable height behavior for vertical slider
                self.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Expanding)
                self.setMinimumHeight(50)  # Minimum reasonable height
    
    def resizeEvent(self, event):
        """Handle resize events to update internal dimensions"""
        super().resizeEvent(event)
        if not self.vertical:
            # Update internal width for horizontal sliders
            self.slider_width = self.width()
        else:
            # Update internal height for vertical sliders (width parameter controls height in vertical mode)
            self.slider_width = self.height()
    
    def set_gradient_colors(self, colors):
        self.gradient_colors = colors
        self._updating_gradient = True
        self.update()
        self._updating_gradient = False
        
    def paintEvent(self, event):
        if self.gradient_colors:
            painter = QPainter(self)
            painter.setRenderHint(QPainter.Antialiasing)
            
            if not self.vertical:  # Horizontal
                # Adjust track height based on handle size
                track_height = self.slider_height - 2
                track_y = (self.height() - track_height) // 2
                
                # Minimal padding - just enough for the handle to not go outside
                padding = self.handle_radius
                track_rect = QtCore.QRect(padding, track_y, self.width() - (2 * padding), track_height)
                
                gradient = QLinearGradient(0, 0, track_rect.width(), 0)
                for i, color in enumerate(self.gradient_colors):
                    gradient.setColorAt(i / (len(self.gradient_colors) - 1), QColor(*color))
                
                path = QPainterPath()
                path.addRoundedRect(track_rect, self.radius, self.radius)
                
                painter.fillPath(path, QBrush(gradient))
                painter.setPen(QColor(80, 80, 80, 0))
                painter.drawPath(path)
                
                # Handle position - constrained to keep handle within track bounds
                available_width = track_rect.width() - (2 * self.handle_radius)
                handle_offset = int((self.value() / self.maximum()) * available_width)
                handle_pos = track_rect.x() + self.handle_radius + handle_offset
                handle_y = self.height() // 2
                
                # Calculate the color at the current position
                color_position = self.value() / self.maximum()
                handle_color = self._interpolate_color(color_position)
                
                # Shadow (slightly offset)
                shadow_offset = 1
                painter.setPen(QColor(0, 0, 0, 0))
                painter.setBrush(QColor(0, 0, 0, 60))
                painter.drawEllipse(
                    handle_pos - self.handle_radius + shadow_offset, 
                    handle_y - self.handle_radius + shadow_offset, 
                    self.handle_size, 
                    self.handle_size
                )
                
                # Handle with current color
                painter.setBrush(handle_color)
                painter.drawEllipse(
                    handle_pos - self.handle_radius, 
                    handle_y - self.handle_radius, 
                    self.handle_size, 
                    self.handle_size
                )
                
                # White border around handle for visibility
                painter.setPen(QPen(QColor(255, 255, 255), 2))
                painter.setBrush(Qt.NoBrush)
                painter.drawEllipse(
                    handle_pos - self.handle_radius, 
                    handle_y - self.handle_radius, 
                    self.handle_size, 
                    self.handle_size
                )
                
            else:  # Vertical
                # Adjust track width based on handle size
                track_width = self.slider_height - 2
                track_x = (self.width() - track_width) // 2
                
                # Minimal padding - just enough for the handle to not go outside
                padding = self.handle_radius
                track_rect = QtCore.QRect(track_x, padding, track_width, self.height() - (2 * padding))
                
                # Gradient goes from bottom to top for vertical
                gradient = QLinearGradient(0, track_rect.height(), 0, 0)
                for i, color in enumerate(self.gradient_colors):
                    gradient.setColorAt(i / (len(self.gradient_colors) - 1), QColor(*color))
                
                path = QPainterPath()
                path.addRoundedRect(track_rect, self.radius, self.radius)
                
                painter.fillPath(path, QBrush(gradient))
                painter.setPen(QColor(80, 80, 80, 0))
                painter.drawPath(path)
                
                # Handle position - constrained to keep handle within track bounds
                available_height = track_rect.height() - (2 * self.handle_radius)
                handle_offset = int((1.0 - self.value() / self.maximum()) * available_height)
                handle_pos = track_rect.y() + self.handle_radius + handle_offset
                handle_x = self.width() // 2
                
                # Calculate the color at the current position
                color_position = self.value() / self.maximum()
                handle_color = self._interpolate_color(color_position)
                
                # Shadow
                shadow_offset = 1
                painter.setPen(QColor(0, 0, 0, 0))
                painter.setBrush(QColor(0, 0, 0, 60))
                painter.drawEllipse(
                    handle_x - self.handle_radius + shadow_offset, 
                    handle_pos - self.handle_radius + shadow_offset, 
                    self.handle_size, 
                    self.handle_size
                )
                
                # Handle with current color
                painter.setBrush(handle_color)
                painter.drawEllipse(
                    handle_x - self.handle_radius, 
                    handle_pos - self.handle_radius, 
                    self.handle_size, 
                    self.handle_size
                )
                
                # White border around handle for visibility
                painter.setPen(QPen(QColor(255, 255, 255), 2))
                painter.setBrush(Qt.NoBrush)
                painter.drawEllipse(
                    handle_x - self.handle_radius, 
                    handle_pos - self.handle_radius, 
                    self.handle_size, 
                    self.handle_size
                )
        else:
            super().paintEvent(event)

    def _interpolate_color(self, position):
        """Interpolate color based on position in gradient"""
        if not self.gradient_colors or len(self.gradient_colors) < 2:
            return QColor(255, 255, 255)
        
        # Handle edge cases
        if position <= 0:
            return QColor(*self.gradient_colors[0])
        if position >= 1:
            return QColor(*self.gradient_colors[-1])
        
        # Find which two colors we're between
        segment_size = 1.0 / (len(self.gradient_colors) - 1)
        segment_index = int(position / segment_size)
        
        # Ensure we don't go out of bounds
        if segment_index >= len(self.gradient_colors) - 1:
            return QColor(*self.gradient_colors[-1])
        
        # Calculate position within this segment (0 to 1)
        local_position = (position % segment_size) / segment_size
        
        # Get the two colors to interpolate between
        color1 = self.gradient_colors[segment_index]
        color2 = self.gradient_colors[segment_index + 1]
        
        # Interpolate between the colors
        r = int(color1[0] + (color2[0] - color1[0]) * local_position)
        g = int(color1[1] + (color2[1] - color1[1]) * local_position)
        b = int(color1[2] + (color2[2] - color1[2]) * local_position)
        
        return QColor(r, g, b)

    def mousePressEvent(self, event):
        if self._updating_gradient:
            return
            
        if event.button() == Qt.LeftButton:
            if not self.vertical:  # Horizontal
                track_height = min(self.slider_height - 2, self.height() - self.handle_size - 2)
                track_y = (self.height() - track_height) // 2
                padding = self.handle_radius
                track_rect = QtCore.QRect(padding, track_y, self.width() - (2 * padding), track_height)
                
                if 0 <= event.pos().x() <= self.width():
                    # Adjust for handle radius
                    relative_x = event.pos().x() - track_rect.x() - self.handle_radius
                    available_width = track_rect.width() - (2 * self.handle_radius)
                    relative_x = max(0, min(relative_x, available_width))
                    
                    value = int((relative_x / available_width) * self.maximum())
                    self.setValue(value)
                    self.sliderPressed.emit()
            else:  # Vertical
                track_width = min(self.slider_height - 2, self.width() - self.handle_size - 2)
                track_x = (self.width() - track_width) // 2
                padding = self.handle_radius
                track_rect = QtCore.QRect(track_x, padding, track_width, self.height() - (2 * padding))
                
                if 0 <= event.pos().y() <= self.height():
                    # Adjust for handle radius
                    relative_y = event.pos().y() - track_rect.y() - self.handle_radius
                    available_height = track_rect.height() - (2 * self.handle_radius)
                    relative_y = max(0, min(relative_y, available_height))
                    
                    # Invert for vertical (0 at bottom)
                    value = int((1.0 - relative_y / available_height) * self.maximum())
                    self.setValue(value)
                    self.sliderPressed.emit()
        
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._updating_gradient:
            return
            
        if event.buttons() & Qt.LeftButton:
            if not self.vertical:  # Horizontal
                track_height = self.slider_height - 2
                track_y = (self.height() - track_height) // 2
                track_rect = QtCore.QRect(self.handle_radius, track_y, self.width() - (2 * self.handle_radius), track_height)
                
                # Adjust for handle radius
                relative_x = event.pos().x() - track_rect.x() - self.handle_radius
                available_width = track_rect.width() - (2 * self.handle_radius)
                relative_x = max(0, min(relative_x, available_width))
                
                value = int((relative_x / available_width) * self.maximum())
                self.setValue(value)
            else:  # Vertical
                track_width = self.slider_height - 2
                track_x = (self.width() - track_width) // 2
                track_rect = QtCore.QRect(track_x, self.handle_radius, track_width, self.height() - (2 * self.handle_radius))
                
                # Adjust for handle radius
                relative_y = event.pos().y() - track_rect.y() - self.handle_radius
                available_height = track_rect.height() - (2 * self.handle_radius)
                relative_y = max(0, min(relative_y, available_height))
                
                # Invert for vertical (0 at bottom)
                value = int((1.0 - relative_y / available_height) * self.maximum())
                self.setValue(value)
        
        super().mouseMoveEvent(event)
    
    def wheelEvent(self, event):
        event.ignore()

class ColorSquareWidget(QWidget):
    """2D Saturation-Brightness picker widget"""
    colorChanged = Signal()
    
    def __init__(self, width=None, height=80, radius=6):
        super().__init__()
        self.radius = radius
        self._fixed_height = height
        
        # Set size policy based on whether width is specified
        if width is not None:
            self.setFixedSize(width, height)
            self.width = width
            self.height = height
        else:
            # Allow horizontal expansion, fix vertical size
            self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
            self.setFixedHeight(height)
            self.width = self.width()  # Will be updated in resizeEvent
            self.height = height
        
        self.setCursor(Qt.CrossCursor)
        
        # Initialize with red hue
        self._hue = 0.0  # 0-1 range
        self._saturation = 1.0  # 0-1 range
        self._brightness = 1.0  # 0-1 range
        
        # Marker position
        self._marker_pos = QPointF(0, 0)
        self._update_marker_position()
        
        # Create the color square pixmap
        self._square_pixmap = None
        self._update_square()
    
    def resizeEvent(self, event):
        """Handle resize events to update internal dimensions"""
        super().resizeEvent(event)
        self.width = self.size().width()
        self.height = self.size().height()
        self._update_marker_position()
        self._update_square()
        
    def _update_marker_position(self):
        """Update marker position based on current saturation/brightness"""
        if self.width > 0 and self.height > 0:
            x = self._saturation * (self.width - 1)
            y = (1.0 - self._brightness) * (self.height - 1)
            self._marker_pos = QPointF(x, y)
        
    def set_hue(self, hue):
        """Set the hue value (0-360)"""
        self._hue = hue / 360.0
        self._update_square()
        self.update()
        
    def set_saturation_brightness(self, saturation, brightness):
        """Set saturation and brightness (0-100)"""
        self._saturation = saturation / 100.0
        self._brightness = brightness / 100.0
        
        # Update marker position
        self._update_marker_position()
        self.update()
        
    def get_saturation(self):
        """Get saturation value (0-100)"""
        return int(self._saturation * 100)
        
    def get_brightness(self):
        """Get brightness value (0-100)"""
        return int(self._brightness * 100)
        
    def _update_square(self):
        """Update the color square pixmap based on current hue"""
        if self.width <= 0 or self.height <= 0:
            return
            
        self._square_pixmap = QPixmap(self.size())
        self._square_pixmap.fill(Qt.transparent)
        
        painter = QPainter(self._square_pixmap)
        painter.setRenderHint(QPainter.Antialiasing)
        
        # Set clipping to rounded rectangle
        border_radius = self.radius
        path = QPainterPath()
        path.addRoundedRect(QRectF(0, 0, self.width, self.height), 
                            border_radius, border_radius)
        painter.setClipPath(path)
        
        # Create the saturation-brightness gradient
        for x in range(self.width):
            saturation = x / float(self.width - 1)
            
            # Create vertical gradient for this column
            gradient = QLinearGradient(0, 0, 0, self.height)
            
            # Top: full brightness with current saturation
            rgb_top = colorsys.hsv_to_rgb(self._hue, saturation, 1.0)
            color_top = QColor.fromRgbF(rgb_top[0], rgb_top[1], rgb_top[2])
            
            # Bottom: zero brightness (black)
            color_bottom = QColor(0, 0, 0)
            
            gradient.setColorAt(0, color_top)
            gradient.setColorAt(1, color_bottom)
            
            painter.setPen(QPen(QBrush(gradient), 1))
            painter.drawLine(x, 0, x, self.height)
        
        painter.end()
        
    def paintEvent(self, event):
        """Paint the color square and marker"""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        
        # Define border radius
        border_radius = self.radius
        
        # Create rounded rectangle path for clipping
        path = QPainterPath()
        path.addRoundedRect(QRectF(0, 0, self.width, self.height), 
                            border_radius, border_radius)
        
        # Set clipping to rounded rectangle
        painter.setClipPath(path)
        
        # Draw the color square (now clipped to rounded rect)
        if self._square_pixmap:
            painter.drawPixmap(0, 0, self._square_pixmap)
        
        # Remove clipping for border and marker
        painter.setClipping(False)
        
        # Draw rounded border
        painter.setPen(QPen(QColor(60, 60, 60), 1))
        painter.drawRoundedRect(QRectF(0, 0, self.width - 1, self.height - 1), 
                            border_radius, border_radius)
        
        # Draw marker
        painter.setPen(QPen(QColor(255, 255, 255), 2))
        painter.drawEllipse(self._marker_pos, self.radius, self.radius)
        painter.setPen(QPen(QColor(0, 0, 0), 1))
        painter.drawEllipse(self._marker_pos, self.radius + 1, self.radius + 1)
        
    def mousePressEvent(self, event):
        """Handle mouse press to select color"""
        if event.button() == Qt.LeftButton:
            self._update_from_mouse(event.pos())
            
    def mouseMoveEvent(self, event):
        """Handle mouse drag to select color"""
        if event.buttons() & Qt.LeftButton:
            self._update_from_mouse(event.pos())
            
    def _update_from_mouse(self, pos):
        """Update color from mouse position"""
        # Clamp position to widget bounds
        x = max(0, min(pos.x(), self.width - 1))
        y = max(0, min(pos.y(), self.height - 1))
        
        # Calculate saturation and brightness
        self._saturation = x / float(self.width - 1)
        self._brightness = 1.0 - (y / float(self.height - 1))
        
        # Update marker position
        self._marker_pos = QPointF(x, y)
        
        self.update()
        self.colorChanged.emit()
#-----------------------------------------------------------------------------------------------------------------------------------------------
class ColorPicker(QWidget):
    colorChanged = Signal(QColor)
    
    def __init__(self, mode='hsv'):
        super().__init__()
        
        # Parse mode input
        if isinstance(mode, str):
            try:
                self.mode = ColorPickerMode(mode.lower())
            except ValueError:
                raise ValueError(f"Invalid mode: {mode}. Must be one of: hsv, hex, palette, square")
        elif isinstance(mode, ColorPickerMode):
            self.mode = mode
        else:
            raise ValueError(f"Mode must be string or ColorPickerMode enum, got {type(mode)}")
        
        # Initialize state
        self.current_color = QColor(186, 24, 24)
        self.sampling = False
        self.cursor_preview = None
        self._updating_sliders = False
        self.sliders_visible = False
        self.square_picker_visible = False  # Add this for square mode
        self.color_palette_widget = None
        
        self.setup_ui()
        self.update_all_from_color()
        
    def setup_ui(self):
        self.setWindowTitle("Color Picker")
        self.setStyleSheet(self._get_base_stylesheet())
        
        self.main_layout = QVBoxLayout()
        self._set_margin_space(self.main_layout, 0, 0)
        
        # Create UI based on mode
        if self.mode == ColorPickerMode.PALETTE:
            self._setup_palette_mode()
        else:
            self._setup_frame_based_mode()
        
        self.setLayout(self.main_layout)

    def _setup_palette_mode(self):
        """Setup UI for palette mode - just color display button"""
        top_layout = QHBoxLayout()
        self._set_margin_space(top_layout, 0, 4)
        
        self.color_display = QPushButton()
        self.color_display.setFixedSize(18, 18)
        self.color_display.setStyleSheet(f"border: 1px solid {UT.rgba_value(self.current_color,1.2)}; border-radius: 3px;")
        self.color_display.setToolTip("Click to show color palette")
        self.color_display.clicked.connect(self.show_color_palette)
        
        top_layout.addWidget(self.color_display)
        self.main_layout.addLayout(top_layout)
    
    def _setup_frame_based_mode(self):
        """Setup UI for HSV, HEX, and SQUARE modes using frame container"""
        self.frame = QFrame()
        self.frame.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Fixed)
        self.frame_layout = QVBoxLayout(self.frame)
        
        margin = 4 if self.mode == ColorPickerMode.HEX else 6
        self._set_margin_space(self.frame_layout, margin, 4)
        
        # Create mode-specific UI
        if self.mode == ColorPickerMode.HEX:
            self._create_hex_top_section()
        elif self.mode == ColorPickerMode.HSV:
            self._create_hsv_mode()
        elif self.mode == ColorPickerMode.SQUARE:
            self._create_square_mode()
        
        self.main_layout.addWidget(self.frame)
    
    def _create_hsv_mode(self):
        """Create full HSV mode UI"""
        # Add color label
        self.color_label = QLabel("Color")
        self.color_label.setStyleSheet("color: #444444;")
        self.frame_layout.addWidget(self.color_label)
        
        self._create_hsv_top_section()
        self._create_hsv_sliders()

    def _create_hex_top_section(self):
        """Create top section for HEX mode"""
        top_layout = QHBoxLayout()
        self._set_margin_space(top_layout, 0, 4)
        h = 16
        
        # Hex input
        self.hex_input = QLineEdit()
        self.hex_input.setStyleSheet("border: 1px solid #444444; border-radius: 3px; color: #777777; padding: 1px;")
        self.hex_input.setAlignment(Qt.AlignCenter)
        self.hex_input.setFixedSize(60, h)
        self.hex_input.setMaxLength(7)
        self.hex_input.setToolTip("Color Hex code")
        self._setup_hex_validator()
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
        
        self.frame_layout.addLayout(top_layout)
    
    def _create_hsv_top_section(self):
        """Create top section for HSV mode"""
        top_layout = QHBoxLayout()
        self._set_margin_space(top_layout, 0, 4)
        
        # Color picker button
        self.picker_btn = QPushButton("")
        self.picker_btn.setIcon(QtGui.QIcon(get_icon('color_picker.png', opacity=0.8, size=18)))
        self.picker_btn.setFixedSize(24, 24)
        self.picker_btn.setStyleSheet("border: 0px solid #666; border-radius: 3px; background-color: #333333;")
        self.picker_btn.setToolTip("Pick color from screen")
        self.picker_btn.clicked.connect(self.toggle_color_sampling)
        
        # Color display
        self.color_display = QPushButton()
        self.color_display.setFixedHeight(24)
        self.color_display.setStyleSheet(f"border: 1px solid {UT.rgba_value(self.current_color,1.2)}; border-radius: 3px;")
        self.color_display.setToolTip("Color palette")
        self.color_display.clicked.connect(self.show_color_palette)
        self.color_display.setContextMenuPolicy(Qt.CustomContextMenu)
        self.color_display.customContextMenuRequested.connect(self.show_color_palette)
        
        # Color dropdown
        self.color_dropdown = QPushButton()
        self.color_dropdown.setFixedSize(24, 24)
        self.color_dropdown.setStyleSheet("background-color: #333333; border-radius: 3px; border: 0px solid #666666;")
        self.color_dropdown.setIcon(QtGui.QIcon(get_icon('hamburger.png', opacity=0.8, size=18)))
        self.color_dropdown.setToolTip("Show HSV sliders")
        self.color_dropdown.clicked.connect(self.toggle_sliders)
        self.color_dropdown.setContextMenuPolicy(Qt.CustomContextMenu)
        self.color_dropdown.customContextMenuRequested.connect(self.show_color_palette)
        
        top_layout.addWidget(self.color_display)
        top_layout.addWidget(self.color_dropdown)
        top_layout.addWidget(self.picker_btn)
        
        self.frame_layout.addLayout(top_layout)
    
    def _create_hsv_sliders(self):
        """Create HSV sliders for HSV mode"""
        self.sliders_widget = QWidget()
        self.sliders_widget.setStyleSheet("""
            QWidget {
                background-color: #222222; 
                padding: 0px; 
                border-radius: 3px; 
                border: 0px solid #666666;
            }
            QLabel {
                color: #aaaaaa; 
                border: none;
                font-size: 11px;
            }
        """)
        
        self.sliders_layout = QVBoxLayout(self.sliders_widget)
        self._set_margin_space(self.sliders_layout, 4, 2)
        
        # Hue slider
        hue_layout = QHBoxLayout()
        self._set_margin_space(hue_layout, 0, 2)
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
        self.sliders_layout.addLayout(hue_layout)
        
        # Saturation slider
        sat_layout = QHBoxLayout()
        self._set_margin_space(sat_layout, 0, 2)
        sat_label = QLabel("S")
        self.sat_slider = ColorSlider()
        self.sat_slider.valueChanged.connect(self.on_saturation_changed)
        sat_layout.addWidget(sat_label)
        sat_layout.addWidget(self.sat_slider)
        self.sliders_layout.addLayout(sat_layout)
        
        # Value slider
        val_layout = QHBoxLayout()
        self._set_margin_space(val_layout, 0, 2)
        val_label = QLabel("V")
        self.val_slider = ColorSlider()
        self.val_slider.valueChanged.connect(self.on_value_changed)
        val_layout.addWidget(val_label)
        val_layout.addWidget(self.val_slider)
        self.sliders_layout.addLayout(val_layout)
        
        # Hex input for HSV mode
        self.hex_input = QLineEdit()
        self.hex_input.setStyleSheet("border: 1px solid #444444; border-radius: 3px; color: #777777;")
        self.hex_input.setAlignment(Qt.AlignCenter)
        self.hex_input.setFixedHeight(24)
        self.hex_input.setMaxLength(7)
        self._setup_hex_validator()
        self.hex_input.textChanged.connect(self.on_hex_changed)
        self.sliders_layout.addWidget(self.hex_input)
        
        self.sliders_widget.hide()  # Initially hidden
        self.frame_layout.addWidget(self.sliders_widget)
    
    def _setup_hex_validator(self):
        """Setup hex input validator based on PySide version"""
        if PYSIDE_VERSION == 6:
            hex_validator = QRegularExpressionValidator(QRegularExpression("^#?[0-9A-Fa-f]{0,6}$"))
        else:
            hex_validator = QRegExpValidator(QRegExp("^#?[0-9A-Fa-f]{0,6}$"))
        self.hex_input.setValidator(hex_validator)
    
    def _get_base_stylesheet(self):
        """Get base stylesheet for the widget"""
        return """
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
        """
    
    def _set_margin_space(self, layout, margin, space):
        """Helper to set layout margins and spacing"""
        layout.setContentsMargins(margin, margin, margin, margin)
        layout.setSpacing(space)
    
    #---------------------------------------------------------------------------------------------------------------------------------------
    # Mode-specific behavior methods
    def toggle_sliders(self):
        """Toggle HSV sliders visibility (HSV mode only)"""
        if self.mode != ColorPickerMode.HSV:
            return
            
        self.sliders_visible = not self.sliders_visible
        
        if self.sliders_visible:
            self.sliders_widget.show()
            self.update_saturation_gradient()
            self.update_value_gradient()
            self.color_dropdown.setToolTip("Hide HSV sliders")
        else:
            self.sliders_widget.hide()
            self.color_dropdown.setToolTip("Show HSV sliders")
        
        self.adjustSize()
    
    def update_saturation_gradient(self):
        """Update saturation slider gradient (HSV mode only)"""
        if self.mode != ColorPickerMode.HSV or not hasattr(self, 'hue_slider'):
            return
        h = self.hue_slider.value()
        sat_colors = []
        for s in [0, 100]:
            rgb = colorsys.hsv_to_rgb(h/360.0, s/100.0, 1.0)
            sat_colors.append((int(rgb[0]*255), int(rgb[1]*255), int(rgb[2]*255)))
        self.sat_slider.set_gradient_colors(sat_colors)
        
    def update_value_gradient(self):
        """Update value slider gradient (HSV mode only)"""
        if self.mode != ColorPickerMode.HSV or not hasattr(self, 'hue_slider'):
            return
        h = self.hue_slider.value()
        s = self.sat_slider.value()
        val_colors = []
        for v in [0, 100]:
            rgb = colorsys.hsv_to_rgb(h/360.0, s/100.0, v/100.0)
            val_colors.append((int(rgb[0]*255), int(rgb[1]*255), int(rgb[2]*255)))
        self.val_slider.set_gradient_colors(val_colors)
    
    def on_hue_changed(self):
        """Handle hue slider change (HSV mode only)"""
        if self._updating_sliders or self.mode != ColorPickerMode.HSV:
            return
        self.update_saturation_gradient()
        self.update_value_gradient()
        self.update_color_from_sliders()
    
    def on_saturation_changed(self):
        """Handle saturation slider change (HSV mode only)"""
        if self._updating_sliders or self.mode != ColorPickerMode.HSV:
            return
        self.update_value_gradient()
        self.update_color_from_sliders()
    
    def on_value_changed(self):
        """Handle value slider change (HSV mode only)"""
        if self._updating_sliders or self.mode != ColorPickerMode.HSV:
            return
        self.update_color_from_sliders()
    
    def update_color_from_sliders(self):
        """Update color from HSV sliders (HSV mode only)"""
        if self.mode != ColorPickerMode.HSV:
            return
            
        h = self.hue_slider.value() / 360.0
        s = self.sat_slider.value() / 100.0
        v = self.val_slider.value() / 100.0
        
        rgb = colorsys.hsv_to_rgb(h, s, v)
        self.current_color = QColor(int(rgb[0]*255), int(rgb[1]*255), int(rgb[2]*255))
        
        self.update_color_display()
        self.update_hex_input()
        self.colorChanged.emit(self.current_color)
    
    def update_sliders_from_color(self):
        """Update HSV sliders from current color (HSV mode only)"""
        if self.mode != ColorPickerMode.HSV:
            return
            
        self._updating_sliders = True
        
        color = self.current_color
        h, s, v = colorsys.rgb_to_hsv(color.red()/255.0, color.green()/255.0, color.blue()/255.0)
        
        self.hue_slider.setValue(int(h * 360))
        self.sat_slider.setValue(int(s * 100))
        self.val_slider.setValue(int(v * 100))
        
        if self.sliders_visible:
            self.update_saturation_gradient()
            self.update_value_gradient()
        
        self._updating_sliders = False
    
    #---------------------------------------------------------------------------------------------------------------------------------------
    def _create_square_mode(self):
        """Create UI elements for square mode"""
        # Add color label
        self.color_label = QLabel("Color")
        self.color_label.setStyleSheet("color: #444444;")
        self.frame_layout.addWidget(self.color_label)
        
        # Create top section (similar to HSV mode)
        top_layout = QHBoxLayout()
        self._set_margin_space(top_layout, 0, 4)
        
        # Color picker button
        self.picker_btn = QPushButton("")
        self.picker_btn.setIcon(QtGui.QIcon(get_icon('color_picker.png', opacity=0.8, size=18)))
        self.picker_btn.setFixedSize(24, 24)
        self.picker_btn.setStyleSheet("border: 0px solid #666; border-radius: 3px; background-color: #333333;")
        self.picker_btn.setToolTip("Pick color from screen")
        self.picker_btn.clicked.connect(self.toggle_color_sampling)
        
        # Color display
        self.color_display = QPushButton()
        self.color_display.setFixedHeight(24)
        self.color_display.setStyleSheet(f"border: 1px solid {UT.rgba_value(self.current_color,1.2)}; border-radius: 3px;")
        self.color_display.setToolTip("Color palette")
        self.color_display.clicked.connect(self.show_color_palette)
        self.color_display.setContextMenuPolicy(Qt.CustomContextMenu)
        self.color_display.customContextMenuRequested.connect(self.show_color_palette)
        
        # Color dropdown (to toggle square picker)
        self.color_dropdown = QPushButton()
        self.color_dropdown.setFixedSize(24, 24)
        self.color_dropdown.setStyleSheet("background-color: #333333; border-radius: 3px; border: 0px solid #666666;")
        self.color_dropdown.setIcon(QtGui.QIcon(get_icon('hamburger.png', opacity=0.8, size=18)))
        self.color_dropdown.setToolTip("Show color square picker")
        self.color_dropdown.clicked.connect(self.toggle_square_picker)
        self.color_dropdown.setContextMenuPolicy(Qt.CustomContextMenu)
        self.color_dropdown.customContextMenuRequested.connect(self.show_color_palette)
        
        top_layout.addWidget(self.color_display)
        top_layout.addWidget(self.color_dropdown)
        top_layout.addWidget(self.picker_btn)
        
        self.frame_layout.addLayout(top_layout)
        
        # Create square picker widget
        self._create_square_picker()

    def _create_square_picker(self):
        """Create the square color picker widget"""
        self.square_picker_widget = QWidget()
        self.square_picker_widget.setStyleSheet("""
            QWidget {
                background-color: #222222; 
                padding: 0px; 
                border-radius: 3px; 
                border: 0px solid #666666;
            }
            QLabel {
                color: #aaaaaa; 
                border: none;
                font-size: 11px;
            }
        """)
        
        self.square_picker_layout = QVBoxLayout(self.square_picker_widget)
        self._set_margin_space(self.square_picker_layout, 4, 4)
        
        # Create the color square widget
        self.color_square = ColorSquareWidget(height=80, radius=6)
        self.color_square.colorChanged.connect(self.on_square_color_changed)
        self.square_picker_layout.addWidget(self.color_square)
        
        self.square_hue_slider = ColorSlider(height=12, radius=4, vertical = False, handle_size=12)
        self.square_hue_slider.setMaximum(360)
        self.square_hue_slider.setValue(0)
        hue_colors = [(255, 0, 0), (255, 255, 0), (0, 255, 0), 
                    (0, 255, 255), (0, 0, 255), (255, 0, 255), (255, 0, 0)]
        self.square_hue_slider.set_gradient_colors(hue_colors)
        self.square_hue_slider.valueChanged.connect(self.on_square_hue_changed)
        

        self.square_picker_layout.addWidget(self.square_hue_slider)
        
        # Hex input
        self.hex_input = QLineEdit()
        self.hex_input.setStyleSheet("border: 1px solid #444444; border-radius: 3px; color: #777777;")
        self.hex_input.setAlignment(Qt.AlignCenter)
        self.hex_input.setFixedHeight(24)
        self.hex_input.setMaxLength(7)
        self._setup_hex_validator()
        self.hex_input.textChanged.connect(self.on_hex_changed)
        self.square_picker_layout.addWidget(self.hex_input)
        
        self.square_picker_widget.hide()  # Initially hidden
        self.frame_layout.addWidget(self.square_picker_widget)
        
    def toggle_square_picker(self):
        """Toggle square picker visibility (square mode only)"""
        if self.mode != ColorPickerMode.SQUARE:
            return
            
        self.square_picker_visible = not self.square_picker_visible
        
        if self.square_picker_visible:
            self.square_picker_widget.show()
            self.color_dropdown.setToolTip("Hide color square picker")
        else:
            self.square_picker_widget.hide()
            self.color_dropdown.setToolTip("Show color square picker")
        
        self.adjustSize()

    def on_square_hue_changed(self):
        """Handle hue slider change in square mode"""
        if self._updating_sliders or self.mode != ColorPickerMode.SQUARE:
            return
        
        hue = self.square_hue_slider.value()
        self.color_square.set_hue(hue)
        self.update_color_from_square()

    def on_square_color_changed(self):
        """Handle color change from square widget"""
        if self._updating_sliders or self.mode != ColorPickerMode.SQUARE:
            return
        
        self.update_color_from_square()

    def update_color_from_square(self):
        """Update color from square picker"""
        if self.mode != ColorPickerMode.SQUARE:
            return
            
        h = self.square_hue_slider.value() / 360.0
        s = self.color_square.get_saturation() / 100.0
        v = self.color_square.get_brightness() / 100.0
        
        rgb = colorsys.hsv_to_rgb(h, s, v)
        self.current_color = QColor(int(rgb[0]*255), int(rgb[1]*255), int(rgb[2]*255))
        
        self.update_color_display()
        self.update_hex_input()
        self.colorChanged.emit(self.current_color)

    def update_square_from_color(self):
        """Update square picker from current color"""
        if self.mode != ColorPickerMode.SQUARE:
            return
            
        self._updating_sliders = True
        
        color = self.current_color
        h, s, v = colorsys.rgb_to_hsv(color.red()/255.0, color.green()/255.0, color.blue()/255.0)
        
        self.square_hue_slider.setValue(int(h * 360))
        self.color_square.set_hue(int(h * 360))
        self.color_square.set_saturation_brightness(int(s * 100), int(v * 100))
        
        self._updating_sliders = False

    #---------------------------------------------------------------------------------------------------------------------------------------
    # Common methods for all modes
    def on_hex_changed(self):
        """Handle hex input change"""
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
                    if self.mode == ColorPickerMode.HSV:
                        self.update_sliders_from_color()
                    self.update_color_display()
                    self.colorChanged.emit(self.current_color)
            except:
                pass
    
    def update_color_display(self):
        """Update color display button"""
        color = self.current_color
        
        if self.mode == ColorPickerMode.HEX:
            style = f"""
                QPushButton {{
                    background-color: rgb({color.red()}, {color.green()}, {color.blue()});
                    border: 1px solid rgba(255, 255, 255, .1);
                    border-radius: 3px;
                }}
                QPushButton:hover {{
                    border: 2px solid {UT.rgba_value(self.current_color,1.2)};
                }}
            """
        else:
            style = f"""
                QPushButton {{
                    background-color: rgb({color.red()}, {color.green()}, {color.blue()});
                    border: 1px solid rgba(255, 255, 255, .1);
                    border-radius: 3px;
                }}
                QPushButton:hover {{
                    border: 2px solid {UT.rgba_value(self.current_color,1.2)};
                }}
            """
        
        self.color_display.setStyleSheet(style)
    
    def update_hex_input(self):
        """Update hex input field"""
        if hasattr(self, 'hex_input'):
            hex_color = self.current_color.name().upper()
            if self.hex_input.text() != hex_color:
                self._updating_sliders = True
                self.hex_input.setText(hex_color)
                self._updating_sliders = False
    
    def update_all_from_color(self):
        """Update all UI elements from current color"""
        if self.mode == ColorPickerMode.HSV:
            self.update_sliders_from_color()
        elif self.mode == ColorPickerMode.SQUARE:
            self.update_square_from_color()
            
        self.update_color_display()
        self.update_hex_input()
        
        if self.mode == ColorPickerMode.HSV and self.sliders_visible:
            self.update_saturation_gradient()
            self.update_value_gradient()
        
        self.colorChanged.emit(self.current_color)

    def show_color_palette(self, position=None):
        """Show color palette popup"""
        if self.color_palette_widget and self.color_palette_widget.isVisible():
            self.color_palette_widget.close()
            return
            
        self.color_palette_widget = QWidget()
        self.color_palette_widget.setWindowFlags(Qt.Popup | Qt.FramelessWindowHint)
        self.color_palette_widget.setStyleSheet('background-color:#222222; border: 1px solid #666; border-radius: 3px;')
        color_layout = QtWidgets.QGridLayout(self.color_palette_widget)
        color_layout.setSpacing(5)
        color_layout.setContentsMargins(6, 6, 6, 6)
        
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
        
        # Position palette widget
        if position is not None and hasattr(position, 'x'):
            global_pos = self.color_display.mapToGlobal(position)
            self.color_palette_widget.move(global_pos.x(), global_pos.y() + 25)
        else:
            global_pos = self.color_display.mapToGlobal(QtCore.QPoint(0, 0))
            self.color_palette_widget.move(global_pos.x(), global_pos.y() + self.color_display.height() + 5)
        
        self.color_palette_widget.show()
    
    def select_palette_color(self, color_hex):
        """Select a color from the palette"""
        color = QColor(color_hex)
        if color.isValid():
            self.current_color = color
            self.update_all_from_color()
        
        if self.color_palette_widget:
            self.color_palette_widget.close()
            self.color_palette_widget = None
        
        # Copy color hex to clipboard
        clipboard = QApplication.clipboard()
        clipboard.setText(color_hex)
    
    # Color sampling methods (available for HSV and HEX modes)
    def toggle_color_sampling(self):
        """Toggle color sampling mode"""
        if not hasattr(self, 'picker_btn'):
            return
            
        if self.sampling:
            self.stop_sampling()
        else:
            self.start_color_sampling()
    
    def start_color_sampling(self):
        """Start color sampling from screen"""
        self.sampling = True
        self.picker_btn.setIcon(QtGui.QIcon(get_icon('color_picker.png', opacity=0.8)))
        self.picker_btn.setStyleSheet("""
            QPushButton {
                background-color: #ff4444;
                border: 1px solid #ff6666;
                color: white;
            }
        """)
        
        self.cursor_preview = CursorPreviewWidget()
        self.cursor_preview.show()
        
        self.original_cursor = QApplication.overrideCursor()
        QApplication.instance().installEventFilter(self)
        self.grabMouse()
        
        self.sample_timer = QTimer()
        self.sample_timer.timeout.connect(self.sample_color_under_cursor)
        self.sample_timer.start(50)
        
    def sample_color_under_cursor(self):
        """Sample color under cursor position"""
        if not self.sampling:
            return
            
        screen = QApplication.primaryScreen()
        if screen:
            cursor_pos = QCursor.pos()
            
            if self.cursor_preview:
                self.cursor_preview.move(cursor_pos.x() + 20, cursor_pos.y() + 20)
            
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
                        
                        if self.cursor_preview:
                            self.cursor_preview.set_color(color)
    
    def eventFilter(self, obj, event):
        """Global event filter for color sampling"""
        if self.sampling:
            if event.type() == QtCore.QEvent.MouseButtonPress:
                if event.button() == Qt.LeftButton:
                    self.stop_sampling()
                    return True
            elif event.type() == QtCore.QEvent.KeyPress:
                if event.key() in (Qt.Key_Escape, Qt.Key_Return, Qt.Key_Enter):
                    self.stop_sampling()
                    return True
        return False
                        
    def keyPressEvent(self, event):
        """Handle key press events during sampling"""
        if self.sampling:
            if event.key() in (Qt.Key_Escape, Qt.Key_Return, Qt.Key_Enter):
                self.stop_sampling()
        super().keyPressEvent(event)
        
    def stop_sampling(self):
        """Stop color sampling mode"""
        if hasattr(self, 'sample_timer'):
            self.sample_timer.stop()
        
        self.releaseMouse()
        QApplication.instance().removeEventFilter(self)
        
        if self.cursor_preview:
            self.cursor_preview.close()
            self.cursor_preview = None
        
        QApplication.restoreOverrideCursor()
        if hasattr(self, 'original_cursor') and self.original_cursor:
            QApplication.setOverrideCursor(self.original_cursor)
        
        self.sampling = False
        
        if hasattr(self, 'picker_btn'):
            self.picker_btn.setIcon(QtGui.QIcon(get_icon('color_picker.png', opacity=0.8)))
            self.picker_btn.setStyleSheet("border: 0px solid #666; border-radius: 3px; background-color: #333333;")

        # Copy color hex to clipboard
        clipboard = QApplication.clipboard()
        clipboard.setText(self.current_color.name())
    
    def closeEvent(self, event):
        """Clean up on widget close"""
        if self.color_palette_widget and self.color_palette_widget.isVisible():
            self.color_palette_widget.close()
        
        if self.sampling:
            self.stop_sampling()
            
        super().closeEvent(event)
#-----------------------------------------------------------------------------------------------------------------------------------------------
class MainWindow(QWidget):
    """Example main window demonstrating different ColorPicker modes"""
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Color Picker Modes Demo")
        layout = QVBoxLayout()
        
        # Create color pickers in different modes
        hsv_picker = ColorPicker(mode='hsv')
        hsv_picker.colorChanged.connect(lambda c: print(f"HSV Color: {c.name()}"))
        
        hex_picker = ColorPicker(mode='hex')
        hex_picker.colorChanged.connect(lambda c: print(f"HEX Color: {c.name()}"))
        
        palette_picker = ColorPicker(mode='palette')
        palette_picker.colorChanged.connect(lambda c: print(f"Palette Color: {c.name()}"))
        
        # Add labels and pickers
        layout.addWidget(QLabel("HSV Mode:"))
        layout.addWidget(hsv_picker)
        
        layout.addWidget(QLabel("HEX Mode:"))
        layout.addWidget(hex_picker)
        
        layout.addWidget(QLabel("Palette Mode:"))
        layout.addWidget(palette_picker)
        
        self.setLayout(layout)

if __name__ == "__main__":
    app = QApplication(sys.argv)
    
    print(f"Using PySide{PYSIDE_VERSION}")
    
    # Example usage:
    # cp_hsv = ColorPicker(mode='hsv')        # Full HSV mode with sliders
    # cp_hex = ColorPicker(mode='hex')        # Compact hex input mode  
    # cp_palette = ColorPicker(mode='palette') # Minimal palette-only mode
    
    window = MainWindow()
    window.show()
    
    sys.exit(app.exec_() if PYSIDE_VERSION == 2 else app.exec())