from functools import partial
import bpy
import os

from PySide6 import QtWidgets, QtCore, QtGui
from PySide6.QtGui import QColor, QAction
from PySide6.QtCore import QTimer, QPropertyAnimation, QEasingCurve, Signal

import re

from . import utils as UT
from . import custom_line_edit as CLE
from . import custom_button as CB
from . import data_management as DM
from . import blender_ui as UI
from . import tool_functions as TF
from . import custom_dialog as CD
from . import blender_main as MAIN
from . import custom_color_picker as CCP
from . utils import undoable

from .pb_selection_manager import SelectionManagerWidget
from .pb_script_manager import ScriptManagerWidget

class ButtonClipboard:
    _instance = None
    
    def __init__(self):
        self.copied_buttons = []
        self.copy_position = None
    
    @classmethod
    def instance(cls):
        if cls._instance is None:
            cls._instance = ButtonClipboard()
        return cls._instance
    
    def copy_buttons(self, buttons, position=None):
        """Enhanced copy method that captures all button data - FIXED VERSION"""
        self.copied_buttons = []
        self.copy_position = position
        
        # Calculate center of selected buttons
        if buttons:
            min_x = min(button.scene_position.x() for button in buttons)
            max_x = max(button.scene_position.x() for button in buttons)
            min_y = min(button.scene_position.y() for button in buttons)
            max_y = max(button.scene_position.y() for button in buttons)
            center = QtCore.QPointF((min_x + max_x) / 2, (min_y + max_y) / 2)
            
            # Store positions relative to center
            for button in buttons:
                # Create a comprehensive dictionary with all button properties
                button_data = {
                    'label': button.label,
                    'selectable': button.selectable,
                    'color': button.color,
                    'opacity': button.opacity,
                    'width': button.width,
                    'height': button.height,
                    'radius': button.radius.copy() if hasattr(button.radius, 'copy') else list(button.radius),
                    'relative_position': button.scene_position - center,
                    'assigned_objects': self._safe_copy_list(button.assigned_objects),
                    'mode': button.mode,
                    'script_data': self._safe_copy_dict(button.script_data),
                    'thumbnail_path': button.thumbnail_path,
                    'shape_type': button.shape_type,
                    'svg_path_data': button.svg_path_data,
                    'svg_file_path': button.svg_file_path
                }
                
                # Add pose-specific data if this is a pose button
                if button.mode == 'pose':
                    button_data['thumbnail_path'] = getattr(button, 'thumbnail_path', '')
                    button_data['pose_data'] = self._safe_copy_dict(getattr(button, 'pose_data', {}))
                
                self.copied_buttons.append(button_data)
            
            #print(f"Copied {len(buttons)} buttons to clipboard")

    def _safe_copy_list(self, original_list):
        """Safely copy a list, handling various data types"""
        if not original_list:
            return []
        
        try:
            # Deep copy for complex nested structures
            import copy
            return copy.deepcopy(original_list)
        except:
            # Fallback to simple copy
            try:
                return list(original_list)
            except:
                return []

    def _safe_copy_dict(self, original_dict):
        """Safely copy a dictionary, handling various data types"""
        if not original_dict:
            return {}
        
        try:
            # Deep copy for complex nested structures
            import copy
            return copy.deepcopy(original_dict)
        except:
            # Fallback to simple copy
            try:
                return dict(original_dict)
            except:
                return {}

    def get_last_attributes(self):
        if self.copied_buttons:
            return self.copied_buttons[-1]
        return None

    def get_all_buttons(self):
        return self.copied_buttons

class PickerButton(QtWidgets.QWidget):
    deleted = Signal(object)
    selected = Signal(object, bool)
    changed = Signal(object)
    
    def __init__(self, label, parent=None, unique_id=None, color='#444444', opacity=1, width=80, height=30, selectable=True, shape_type='rounded_rect', svg_path_data=None, svg_file_path=None):
        super(PickerButton, self).__init__(parent)
        self.label = label
        self.unique_id = unique_id
        self.color = color
        self.opacity = opacity
        self.width = width
        self.height = height
        self.original_size = QtCore.QSize(self.width, self.height)
        self.setCursor(QtCore.Qt.OpenHandCursor)
        self.setMouseTracking(True)
        self.dragging = False
        self._scene_position = QtCore.QPointF(0, 0)
        self.border_radius = 3
        self.radius = [3, 3, 3, 3]  # [top_left, top_right, bottom_right, bottom_left]
        self.is_selected = False
        self.selectable = selectable  # Whether the button can be selected in select mode (not edit mode)
        self.text_color = "#ffffff"
        
        self.shape_type = shape_type  # 'rounded_rect' or 'custom_path'
        self.svg_path_data = svg_path_data  # Store the SVG path string
        self.svg_file_path = svg_file_path  # Store the original SVG file path

        self.cached_mask = None
        self.last_mask_zoom_factor = 0
        self.last_mask_size = None
        self.last_mask_radius = None
        self.last_mask_shape_type = None
        self.last_mask_svg_data = None

        self.rotation = 0
    
        self.setStyleSheet(f"QToolTip {{background-color: {UT.rgba_value(color,.7,alpha=1)}; color: #eeeeee ; border: 1px solid rgba(255,255,255,.2); padding: 0px;}}")
        # Create tooltip widget once and reuse it
        self.tooltip_widget = CB.CustomTooltipWidget(parent=self)
        self._tooltip_populated = False
        self._tooltip_needs_update = True 
       
        self.edit_mode = False
        self.update_cursor()
        self.assigned_objects = []  

        self.mode = 'select'  # 'select', 'script', or 'pose'
        self.script_data = {}  # Store script data
        self.pose_data = {}  # Store pose data

        # Rename mode properties
        self.rename_mode = False
        self.rename_edit = None

        
        # Thumbnail image for pose mode
        self.thumbnail_path = ''  # Path to the thumbnail image
        self.thumbnail_pixmap = None  # Cached pixmap of the thumbnail
        
        # Cache for pose mode rendering
        self.pose_pixmap = None  # Cached pixmap for pose mode (thumbnail + text)

        # Pre-render text to pixmap for better performance
        self.text_pixmap = None
        self.last_zoom_factor = 0  # Track zoom factor to know when to regenerate the pixmap
        self.last_size = None      # Track size to know when to regenerate the pixmap
        self.last_radius = None    # Track radius to know when to regenerate the pixmap
        self.last_text = None      # Track text to know when to regenerate the pixmap

        self.is_hovered = False
        

        self.installEventFilter(self)
        #self._tooltip_needs_update = True
        self.update_tooltip()
        
    @property
    def scene_position(self):
        return self._scene_position

    @scene_position.setter
    def scene_position(self, pos):
        self._scene_position = pos
        if self.parent():
            self.parent().update_button_positions()    
    #---------------------------------------------------------------------------------------
    def _create_rounded_rect_path(self, rect, radii, zoom_factor):
        """Create a rounded rectangle path with the given corner radii.
        
        Args:
            rect (QRectF): Rectangle to create path for
            radii (list): List of 4 corner radii values [tl, tr, br, bl]
            zoom_factor (float): Current zoom factor
            
        Returns:
            QPainterPath: Path with rounded corners
        """
        path = QtGui.QPainterPath()
        
        # Apply zoom factor to radii
        zf = zoom_factor * 0.95
        tl, tr, br, bl = [radius * zf for radius in radii]
        
        # Create the path with adjusted radii
        path.moveTo(rect.left() + tl, rect.top())
        path.lineTo(rect.right() - tr, rect.top())
        path.arcTo(rect.right() - 2*tr, rect.top(), 2*tr, 2*tr, 90, -90)
        path.lineTo(rect.right(), rect.bottom() - br)
        path.arcTo(rect.right() - 2*br, rect.bottom() - 2*br, 2*br, 2*br, 0, -90)
        path.lineTo(rect.left() + bl, rect.bottom())
        path.arcTo(rect.left(), rect.bottom() - 2*bl, 2*bl, 2*bl, -90, -90)
        path.lineTo(rect.left(), rect.top() + tl)
        path.arcTo(rect.left(), rect.top(), 2*tl, 2*tl, 180, -90)
        
        return path
    
    def _calculate_thumbnail_rect(self, zoom_factor):
        """Calculate the rectangle for the thumbnail or placeholder.
        
        Args:
            zoom_factor (float): Current zoom factor
            
        Returns:
            QRectF: Rectangle for the thumbnail area
        """
        # Limit thumbnail size to ensure it doesn't overlap with text area
        max_thumbnail_height = self.height * 0.7  # Limit to 70% of button height
        thumbnail_width = self.width * 0.9  # 90% of button width
        thumbnail_size = min(thumbnail_width, max_thumbnail_height)
        
        # Position thumbnail in the upper part of the button, centered horizontally
        rect = QtCore.QRectF(
            (self.width - thumbnail_size) / 2.4,  # Center horizontally
            self.height * 0.04,  # Fixed position from top (4% of height)
            thumbnail_size,
            thumbnail_size
        )
        
        # Adjust for zoom factor
        return QtCore.QRectF(
            rect.x() * zoom_factor,
            rect.y() * zoom_factor,
            rect.width() * zoom_factor,
            rect.height() * zoom_factor
        )
    
    def _render_pose_pixmap(self, current_size, zoom_factor):
        """Render the pixmap for pose mode with thumbnail and text.
        
        Args:
            current_size (QSize): Current button size
            zoom_factor (float): Current zoom factor
            
        Returns:
            QPixmap: The rendered pose pixmap
        """
        # Create a new pixmap for pose mode
        pose_pixmap = QtGui.QPixmap(current_size)
        pose_pixmap.fill(QtCore.Qt.transparent)
        
        pose_painter = QtGui.QPainter(pose_pixmap)
        pose_painter.setRenderHint(QtGui.QPainter.Antialiasing)
        pose_painter.setRenderHint(QtGui.QPainter.TextAntialiasing)
        
        # Calculate font size and only render text if it's large enough
        calculated_font_size = (self.width * 0.15) * zoom_factor
        if calculated_font_size >= 2:  # Only render text if font would be 2px or larger
            # Set up font for pose mode
            pose_painter.setPen(QtGui.QColor('white'))
            pose_font = pose_painter.font()
            font_size = max(int(calculated_font_size), 2)  # Ensure minimum readable size
            pose_font.setPixelSize(font_size)
            pose_painter.setFont(pose_font)
            
            # Calculate text area at bottom of button
            min_text_height = 12  # Minimum height in pixels
            text_height = max(int(self.height * 0.2), min_text_height)
            fixed_position_from_top = self.height * 0.75  # Bottom 20% of button
            
            text_rect = QtCore.QRectF(
                0,  # Start at left edge
                fixed_position_from_top * zoom_factor,  # Fixed position from top
                self.width * zoom_factor,  # Full width
                text_height * zoom_factor  # Height scaled with zoom
            )
            
            # Draw text at bottom
            pose_painter.drawText(text_rect, QtCore.Qt.AlignHCenter | QtCore.Qt.AlignBottom, self.label)
        
        # Get thumbnail area
        thumbnail_rect = self._calculate_thumbnail_rect(zoom_factor)
        
        # Create thumbnail path with same corner radius as button
        thumbnail_path = self._create_rounded_rect_path(
            thumbnail_rect, 
            [self.radius[0]] * 4,  # Same radius for all corners
            zoom_factor
        )
        
        # Draw tinted background for thumbnail area
        tinted_color = UT.rgba_value(self.color, 0.4, 0.8)  # 40% tint, 80% opacity
        pose_painter.setBrush(QtGui.QColor(tinted_color))
        pose_painter.setPen(QtCore.Qt.NoPen)
        pose_painter.drawPath(thumbnail_path)
        
        # Draw thumbnail or placeholder
        if self.thumbnail_path and (self.thumbnail_pixmap is not None) and not self.thumbnail_pixmap.isNull():
            # Set clipping path for the thumbnail
            pose_painter.setClipPath(thumbnail_path)
            
            # Scale the pixmap to fit within the thumbnail area
            scaled_pixmap = self.thumbnail_pixmap.scaled(
                int(thumbnail_rect.width()),
                int(thumbnail_rect.height()),
                QtCore.Qt.KeepAspectRatio,
                QtCore.Qt.SmoothTransformation
            )
            
            # Center the image in the thumbnail area
            pixmap_rect = QtCore.QRectF(
                thumbnail_rect.x() + (thumbnail_rect.width() - scaled_pixmap.width()) / 2,
                thumbnail_rect.y() + (thumbnail_rect.height() - scaled_pixmap.height()) / 2,
                scaled_pixmap.width(),
                scaled_pixmap.height()
            )
            
            # Draw the thumbnail
            pose_painter.drawPixmap(pixmap_rect.toRect(), scaled_pixmap)
            pose_painter.setClipping(False)
        
        elif self.thumbnail_path:
            # We have a path but the image didn't load - show "broken" indicator with icon
            
            # Get error icon using the get_icon function
            error_icon = UT.get_icon("error_01.png", opacity=.5, size=128)
            
            if error_icon and not error_icon.isNull():
                # Set clipping path for the thumbnail area (same as working thumbnails)
                pose_painter.setClipPath(thumbnail_path)
                
                # Scale the error icon to fit within the thumbnail area, similar to how thumbnails are handled
                scaled_error_icon = error_icon.scaled(
                    int(thumbnail_rect.width() * 0.8),  # Make it 80% of thumbnail size for better visibility
                    int(thumbnail_rect.height() * 0.8),
                    QtCore.Qt.KeepAspectRatio,
                    QtCore.Qt.SmoothTransformation
                )
                
                # Center the error icon in the thumbnail area
                icon_rect = QtCore.QRectF(
                    thumbnail_rect.x() + (thumbnail_rect.width() - scaled_error_icon.width()) / 2,
                    thumbnail_rect.y() + (thumbnail_rect.height() - scaled_error_icon.height()) / 2,
                    scaled_error_icon.width(),
                    scaled_error_icon.height()
                )
                
                # Draw the scaled error icon (retains full resolution)
                pose_painter.drawPixmap(icon_rect.toRect(), scaled_error_icon)
                
                # Remove clipping
                pose_painter.setClipping(False)
                
            else:
                # Fallback to text if icon fails to load (same as before)
                # Only render this text if font is large enough
                if calculated_font_size >= 2:
                    pose_painter.setPen(QtGui.QColor(255, 100, 100, 150))
                    pose_painter.drawText(thumbnail_rect, QtCore.Qt.AlignCenter, "Missing\nThumbnail")

        else:
            # Draw placeholder text - only if font is large enough
            if calculated_font_size >= 2:
                pose_painter.setPen(QtGui.QColor(255, 255, 255, 120))
                pose_painter.drawText(thumbnail_rect, QtCore.Qt.AlignCenter, "Thumbnail")
                pose_painter.setPen(QtGui.QColor('white'))  # Reset pen color
        
        pose_painter.end()
        return pose_pixmap

    def _render_text_pixmap(self, current_size, zoom_factor):
        """Render the pixmap for regular mode with centered text."""
        text_pixmap = QtGui.QPixmap(current_size)
        text_pixmap.fill(QtCore.Qt.transparent)

        # Start with height-based calculation (preserve as priority)
        base_font_size = (self.height * 0.5) * zoom_factor
        
        # Only render text if the calculated font size is large enough
        if base_font_size >= 2:  # Only render text if font would be 2px or larger
            font_size = max(int(base_font_size), 2)  # Ensure minimum readable size
            min_font_size = 2  # Set a minimum font size for legibility
            max_width = current_size.width() * 0.9  # 10% padding

            # Prepare the display text (don't modify self.label)
            display_text = self.label
            
            # Only wrap if not already colored
            if "color:" not in display_text and "font color=" not in display_text:
                display_text = f"<span style='color: {self.text_color};'>{display_text}</span>"
            
            # Use QTextDocument for rich text, but single line only
            doc = QtGui.QTextDocument()
            doc.setHtml(display_text)  # Use display_text instead of self.label

            # Try to fit the text in one line by reducing font size if needed
            while font_size >= min_font_size:
                font = QtGui.QFont()
                font.setPixelSize(font_size)
                doc.setDefaultFont(font)
                doc.setTextWidth(-1)  # No wrapping
                text_width = doc.idealWidth()
                if text_width <= max_width:
                    break
                font_size -= 1
                
            # Set final font
            font = QtGui.QFont()
            font.setPixelSize(font_size)
            doc.setDefaultFont(font)
            doc.setTextWidth(-1)  # No wrapping
            text_width = doc.idealWidth()
            text_height = doc.size().height()

            # Center horizontally and vertically
            x = (current_size.width() - text_width) / 2
            y = (current_size.height() - text_height) / 2

            text_painter = QtGui.QPainter(text_pixmap)
            text_painter.setRenderHint(QtGui.QPainter.Antialiasing)
            text_painter.setRenderHint(QtGui.QPainter.TextAntialiasing)
            text_painter.translate(x, y)
            doc.drawContents(text_painter)
            text_painter.end()

        return text_pixmap
    
    def _should_update_pixmaps(self, zoom_factor, current_size, current_radius, current_text):
        """Determine if pixmaps need to be updated.
        
        Args:
            zoom_factor (float): Current zoom factor
            current_size (QSize): Current button size
            current_radius (list): Current button radius
            current_text (str): Current button text
        Returns:
            bool: True if pixmaps need to be updated
        """
        # Check if pixmaps are missing or if zoom/size has changed significantly
        if self.mode == 'pose':
            pixmap_missing = self.pose_pixmap is None
        else:
            pixmap_missing = self.text_pixmap is None
            
        zoom_changed = abs(self.last_zoom_factor - zoom_factor) > 0.1
        size_changed = self.last_size != current_size
        radius_changed = self.last_radius != current_radius
        text_changed = self.last_text != current_text
        
        return pixmap_missing or zoom_changed or size_changed or radius_changed or text_changed
    
    def paintEvent(self, event):
        """Paint the button with background, selection border, and text/thumbnail.
        
        Args:
            event (QPaintEvent): The paint event
        """
        painter = QtGui.QPainter(self)
        painter.setRenderHint(QtGui.QPainter.Antialiasing)

        # Get the current zoom factor from the parent canvas
        zoom_factor = self.parent().zoom_factor if self.parent() else 1.0

        # Draw button background
        if not self.is_selected:
            # Use lighter color on hover
            if self.is_hovered and self.selectable:
                hover_color = UT.rgba_value(self.color, 1.2, alpha=1)
                painter.setBrush(QtGui.QColor(hover_color))
            else:
                # Use normal color
                painter.setBrush(QtGui.QColor(self.color))
        else:
            if self.edit_mode:
                painter.setBrush(QtGui.QColor(self.color))
            else:
                painter.setBrush(QtGui.QColor(255, 255, 255, 120))
        
        # Apply the button's opacity
        if self.edit_mode and self.mode != 'pose':
            if self.opacity < .2:
                painter.setOpacity(.2)
            else:
                painter.setOpacity(self.opacity)
        else:
            painter.setOpacity(self.opacity)
        painter.setPen(QtCore.Qt.NoPen)

        # Create button path with rounded corners
        rect = self.rect().adjusted(zoom_factor, zoom_factor, -zoom_factor, -zoom_factor)
        path = self._create_button_path(rect, self.radius, zoom_factor)
        painter.drawPath(path)

        # Draw selection border if selected
        if self.is_selected:
            if self.edit_mode:
                painter.setBrush(QtGui.QColor(self.color))
                pen = QtGui.QPen(QtGui.QColor(255, 255, 255, 200), 2)
                pen.setCosmetic(True)  # Fixed width regardless of zoom
                painter.setPen(pen)
                painter.drawPath(path)
            else:   
                pen = QtGui.QPen(QtGui.QColor(255, 255, 255, 120), 1)
                pen.setCosmetic(True)
                painter.setPen(pen)
                painter.drawPath(path)

        # Reset opacity for text/thumbnail rendering
        painter.setOpacity(1.0)
        
        # Check if mask needs to be updated (similar to pixmap checking)
        current_size = self.size()
        current_radius = self.radius.copy()  # Make a copy to compare
        current_shape_type = self.shape_type
        current_svg_data = self.svg_path_data
        
        if self._should_update_mask(zoom_factor, current_size, current_radius, current_shape_type, current_svg_data):
            # Update cached parameters
            self.last_mask_zoom_factor = zoom_factor
            self.last_mask_size = current_size
            self.last_mask_radius = current_radius
            self.last_mask_shape_type = current_shape_type
            self.last_mask_svg_data = current_svg_data
            
            # Generate new mask
            self.cached_mask = self._generate_mask(zoom_factor)
            
            # Apply the cached mask
            if self.cached_mask:
                self.setMask(self.cached_mask)

        # Check if pixmaps need to be updated
        current_size = self.size()
        current_radius = self.radius
        current_text = self.label
        if self._should_update_pixmaps(zoom_factor, current_size, current_radius, current_text):
            self.last_zoom_factor = zoom_factor
            self.last_size = current_size
            self.last_radius = current_radius
            self.last_text = current_text
            
            # Render appropriate pixmap based on mode
            if self.mode == 'pose':
                self.pose_pixmap = self._render_pose_pixmap(current_size, zoom_factor)
                # Create an empty text_pixmap to avoid None checks
                self.text_pixmap = QtGui.QPixmap(current_size)
                self.text_pixmap.fill(QtCore.Qt.transparent)
            else:
                self.text_pixmap = self._render_text_pixmap(current_size, zoom_factor)
        
        # Draw the appropriate pixmap
        if self.mode == 'pose':
            if self.pose_pixmap and not self.pose_pixmap.isNull():
                painter.drawPixmap(0, 0, self.pose_pixmap)
        else:
            if self.text_pixmap and not self.text_pixmap.isNull():
                painter.drawPixmap(0, 0, self.text_pixmap)
    #---------------------------------------------------------------------------------------
    def _create_button_path(self, rect, radii, zoom_factor):
        """Create button path based on shape type"""
        if self.shape_type == 'custom_path' and self.svg_path_data:
            return self._create_svg_path(rect, zoom_factor)
        else:
            return self._create_rounded_rect_path(rect, radii, zoom_factor)

    def _create_svg_path(self, rect, zoom_factor):
        """Create a QPainterPath from SVG path data, scaled to fit the button rect"""
        try:
            path = QtGui.QPainterPath()
            
            # Parse the SVG path data
            svg_path = self._parse_svg_path(self.svg_path_data)
            if not svg_path:
                # Fallback to rounded rect if parsing fails
                return self._create_rounded_rect_path(rect, self.radius, zoom_factor)
            
            # Get the original path bounds
            original_bounds = svg_path.boundingRect()
            if original_bounds.isEmpty():
                return self._create_rounded_rect_path(rect, self.radius, zoom_factor)
            
            # Calculate scaling factors to fit the button rect
            scale_x = rect.width() / original_bounds.width()
            scale_y = rect.height() / original_bounds.height()
            
            # Use uniform scaling to maintain aspect ratio
            scale = min(scale_x, scale_y) * 0.9  # 0.9 for slight padding
            
            # Calculate centering offsets
            scaled_width = original_bounds.width() * scale
            scaled_height = original_bounds.height() * scale
            offset_x = rect.center().x() - (scaled_width / 2) - (original_bounds.x() * scale)
            offset_y = rect.center().y() - (scaled_height / 2) - (original_bounds.y() * scale)
            
            # Create transformation matrix
            transform = QtGui.QTransform()
            transform.translate(offset_x, offset_y)
            transform.scale(scale, scale)
            
            # Apply transformation to the SVG path
            return transform.map(svg_path)
            
        except Exception as e:
            print(f"Error creating SVG path: {e}")
            # Fallback to rounded rect
            return self._create_rounded_rect_path(rect, self.radius, zoom_factor)

    def _parse_svg_path(self, path_data):
        """Parse SVG path data string into QPainterPath - IMPROVED VERSION"""
        if not path_data:
            return None
            
        try:
            path = QtGui.QPainterPath()
            
            # Clean up the path data - normalize separators and whitespace
            path_data = path_data.strip()
            # Replace commas with spaces for easier parsing
            path_data = re.sub(r',', ' ', path_data)
            # Normalize whitespace
            path_data = re.sub(r'\s+', ' ', path_data)
            # Add spaces before negative signs that aren't preceded by 'e' or 'E' (for scientific notation)
            path_data = re.sub(r'(?<![eE])-', ' -', path_data)
            
            # Improved regex pattern that handles scientific notation and complex numbers
            # This pattern captures commands and all their numeric parameters
            command_pattern = r'([MmLlHhVvCcSsQqTtAaZz])\s*((?:[-+]?(?:\d+\.?\d*|\.\d+)(?:[eE][-+]?\d+)?\s*)*)'
            
            commands = re.findall(command_pattern, path_data)
            
            current_point = QtCore.QPointF(0, 0)
            path_start = QtCore.QPointF(0, 0)
            last_control_point = None  # For smooth curves
            
            for command, coords_str in commands:
                # Parse coordinates more robustly
                coords = []
                if coords_str.strip():
                    # Handle scientific notation and regular numbers
                    number_pattern = r'[-+]?(?:\d+\.?\d*|\.\d+)(?:[eE][-+]?\d+)?'
                    coord_matches = re.findall(number_pattern, coords_str)
                    try:
                        coords = [float(x) for x in coord_matches if x]
                    except ValueError as e:
                        print(f"Error parsing coordinates '{coords_str}': {e}")
                        continue
                
                # Handle different SVG path commands
                if command.upper() == 'M':  # Move to
                    if len(coords) >= 2:
                        x, y = coords[0], coords[1]
                        if command.islower():  # Relative
                            x += current_point.x()
                            y += current_point.y()
                        
                        current_point = QtCore.QPointF(x, y)
                        path.moveTo(current_point)
                        path_start = current_point
                        
                        # Handle additional coordinate pairs as line-to commands
                        for i in range(2, len(coords), 2):
                            if i + 1 < len(coords):
                                x, y = coords[i], coords[i + 1]
                                if command.islower():
                                    x += current_point.x()
                                    y += current_point.y()
                                else:
                                    # Convert to absolute if needed
                                    pass
                                current_point = QtCore.QPointF(x, y)
                                path.lineTo(current_point)
                
                elif command.upper() == 'L':  # Line to
                    for i in range(0, len(coords), 2):
                        if i + 1 < len(coords):
                            x, y = coords[i], coords[i + 1]
                            if command.islower():  # Relative
                                x += current_point.x()
                                y += current_point.y()
                            
                            current_point = QtCore.QPointF(x, y)
                            path.lineTo(current_point)
                
                elif command.upper() == 'H':  # Horizontal line
                    for coord in coords:
                        if command.islower():  # Relative
                            x = current_point.x() + coord
                        else:  # Absolute
                            x = coord
                        
                        current_point = QtCore.QPointF(x, current_point.y())
                        path.lineTo(current_point)
                
                elif command.upper() == 'V':  # Vertical line
                    for coord in coords:
                        if command.islower():  # Relative
                            y = current_point.y() + coord
                        else:  # Absolute
                            y = coord
                        
                        current_point = QtCore.QPointF(current_point.x(), y)
                        path.lineTo(current_point)
                
                elif command.upper() == 'C':  # Cubic Bezier curve
                    for i in range(0, len(coords), 6):
                        if i + 5 < len(coords):
                            x1, y1 = coords[i], coords[i + 1]
                            x2, y2 = coords[i + 2], coords[i + 3]
                            x, y = coords[i + 4], coords[i + 5]
                            
                            if command.islower():  # Relative
                                x1 += current_point.x()
                                y1 += current_point.y()
                                x2 += current_point.x()
                                y2 += current_point.y()
                                x += current_point.x()
                                y += current_point.y()
                            
                            c1 = QtCore.QPointF(x1, y1)
                            c2 = QtCore.QPointF(x2, y2)
                            end = QtCore.QPointF(x, y)
                            
                            path.cubicTo(c1, c2, end)
                            current_point = end
                            last_control_point = c2  # Store for smooth curves
                
                elif command.upper() == 'S':  # Smooth cubic Bezier
                    for i in range(0, len(coords), 4):
                        if i + 3 < len(coords):
                            x2, y2 = coords[i], coords[i + 1]
                            x, y = coords[i + 2], coords[i + 3]
                            
                            if command.islower():  # Relative
                                x2 += current_point.x()
                                y2 += current_point.y()
                                x += current_point.x()
                                y += current_point.y()
                            
                            # Calculate first control point as reflection of last control point
                            if last_control_point:
                                x1 = 2 * current_point.x() - last_control_point.x()
                                y1 = 2 * current_point.y() - last_control_point.y()
                            else:
                                x1, y1 = current_point.x(), current_point.y()
                            
                            c1 = QtCore.QPointF(x1, y1)
                            c2 = QtCore.QPointF(x2, y2)
                            end = QtCore.QPointF(x, y)
                            
                            path.cubicTo(c1, c2, end)
                            current_point = end
                            last_control_point = c2
                
                elif command.upper() == 'Q':  # Quadratic Bezier curve
                    for i in range(0, len(coords), 4):
                        if i + 3 < len(coords):
                            x1, y1 = coords[i], coords[i + 1]
                            x, y = coords[i + 2], coords[i + 3]
                            
                            if command.islower():  # Relative
                                x1 += current_point.x()
                                y1 += current_point.y()
                                x += current_point.x()
                                y += current_point.y()
                            
                            c1 = QtCore.QPointF(x1, y1)
                            end = QtCore.QPointF(x, y)
                            
                            path.quadTo(c1, end)
                            current_point = end
                            last_control_point = c1  # Store for smooth curves
                
                elif command.upper() == 'T':  # Smooth quadratic Bezier
                    for i in range(0, len(coords), 2):
                        if i + 1 < len(coords):
                            x, y = coords[i], coords[i + 1]
                            
                            if command.islower():  # Relative
                                x += current_point.x()
                                y += current_point.y()
                            
                            # Calculate control point as reflection of last control point
                            if last_control_point:
                                x1 = 2 * current_point.x() - last_control_point.x()
                                y1 = 2 * current_point.y() - last_control_point.y()
                            else:
                                x1, y1 = current_point.x(), current_point.y()
                            
                            c1 = QtCore.QPointF(x1, y1)
                            end = QtCore.QPointF(x, y)
                            
                            path.quadTo(c1, end)
                            current_point = end
                            last_control_point = c1
                
                elif command.upper() == 'A':  # Elliptical arc
                    for i in range(0, len(coords), 7):
                        if i + 6 < len(coords):
                            rx, ry = coords[i], coords[i + 1]
                            x_axis_rotation = coords[i + 2]
                            large_arc_flag = int(coords[i + 3])
                            sweep_flag = int(coords[i + 4])
                            x, y = coords[i + 5], coords[i + 6]
                            
                            if command.islower():  # Relative
                                x += current_point.x()
                                y += current_point.y()
                            
                            end = QtCore.QPointF(x, y)
                            
                            # For now, approximate arc with a line (proper arc implementation is complex)
                            # TODO: Implement proper arc-to-bezier conversion
                            path.lineTo(end)
                            current_point = end
                
                elif command.upper() == 'Z':  # Close path
                    path.closeSubpath()
                    current_point = path_start
                    last_control_point = None
                
                # Reset last_control_point for non-smooth commands
                if command.upper() not in ['S', 'T']:
                    if command.upper() not in ['C', 'Q']:
                        last_control_point = None
            
            return path
            
        except Exception as e:
            print(f"Error parsing SVG path: {e}")
            print(f"Problematic path data: {path_data[:100]}...")  # Show first 100 chars
            return None

    def set_custom_shape(self, preserve_individual=True):
        """Set buttons to use custom SVG shapes with option to preserve individual data"""
        canvas = self.parent()
        main_window = canvas.window() if canvas else None
        if canvas:
            selected_buttons = canvas.get_selected_buttons()
            if not selected_buttons:
                selected_buttons = [self]
        else:
            selected_buttons = [self]

        # Apply custom shape type to all selected buttons
        for button in selected_buttons:
            button.shape_type = 'custom_path'
            
            if preserve_individual:
                # Only apply SVG data to buttons that don't have any
                if not button.svg_path_data:
                    button.svg_path_data = self.svg_path_data
                    button.svg_file_path = self.svg_file_path
            else:
                # Apply the same SVG data to all buttons
                button.svg_path_data = self.svg_path_data
                button.svg_file_path = self.svg_file_path
            
            # Force update of the button
            #button._invalidate_mask_cache()
            #button.update()
        
        if hasattr(main_window, 'batch_update_buttons_to_database'):
            main_window.batch_update_buttons_to_database(selected_buttons)
        canvas.update_button_positions()
        canvas.update()
        
    def apply_same_shape_to_selected(self):
        """Apply this button's SVG shape to all selected buttons"""
        self.set_custom_shape(preserve_individual=False)

    def enable_custom_shapes_for_selected(self):
        """Enable custom shape mode for selected buttons while preserving their individual SVG data"""
        self.set_custom_shape(preserve_individual=True)
    
    def load_svg_shape(self):
        """Load SVG file and extract path data for the button shape"""
        # Get the SVG directory from data management (similar to thumbnail directory)
        data = DM.PickerDataManager.get_data()
        svg_dir = data.get('svg_directory', '')
        
        # If no SVG directory is set, use a dedicated directory
        if not svg_dir:
            script_dir = os.path.dirname(os.path.abspath(__file__))
            svg_dir = os.path.join(script_dir, 'picker_shapes')
        
        # Make sure the directory exists
        if not os.path.exists(svg_dir):
            try:
                os.makedirs(svg_dir)
            except:
                svg_dir = os.path.expanduser("~")
        
        file_path, _ = QtWidgets.QFileDialog.getOpenFileName(
            self, "Select SVG Shape", svg_dir,
            "SVG Files (*.svg)"
        )
        
        if file_path:
            try:
                # Parse the SVG file
                tree = ET.parse(file_path)
                root = tree.getroot()
                
                # Find the first path element
                path_element = root.find('.//{http://www.w3.org/2000/svg}path')
                if path_element is None:
                    # Try without namespace
                    path_element = root.find('.//path')
                
                if path_element is not None and 'd' in path_element.attrib:
                    # Get all selected buttons to apply the shape to
                    canvas = self.parent()
                    if canvas:
                        selected_buttons = canvas.get_selected_buttons()
                        if not selected_buttons:
                            selected_buttons = [self]
                    else:
                        selected_buttons = [self]
                    
                    # Apply the SVG shape to all selected buttons
                    for button in selected_buttons:
                        button.shape_type = 'custom_path'
                        button.svg_path_data = path_element.attrib['d']
                        button.svg_file_path = file_path
                        
                        # Force update of the button
                        button.update()
                        button.changed.emit(button)
                    
                    return True
                else:
                    # Show error dialog
                    dialog = CD.CustomDialog(self, title="Invalid SVG", size=(250, 100), info_box=True)
                    message_label = QtWidgets.QLabel("The selected SVG file does not contain a valid path element.")
                    message_label.setWordWrap(True)
                    dialog.add_widget(message_label)
                    dialog.add_button_box()
                    dialog.exec_()
                    
            except Exception as e:
                # Show error dialog
                dialog = CD.CustomDialog(self, title="Error", size=(250, 100), info_box=True)
                message_label = QtWidgets.QLabel(f"Error loading SVG file: {str(e)}")
                message_label.setWordWrap(True)
                dialog.add_widget(message_label)
                dialog.add_button_box()
                dialog.exec_()
        
        return False

    def reset_to_rounded_rect(self):
        """Reset button shape to default rounded rectangle"""
        canvas = self.parent()
        main_window = canvas.window() if canvas else None
        if canvas:
            selected_buttons = canvas.get_selected_buttons()
            if not selected_buttons:
                selected_buttons = [self]
        else:
            selected_buttons = [self]
        
        for button in selected_buttons:
            button.shape_type = 'rounded_rect'
            #button.svg_path_data = None
            #button.svg_file_path = None
            #button._invalidate_mask_cache()
            #button.update()
            button.changed.emit(button)
        
        if hasattr(main_window, 'batch_update_buttons_to_database'):
            main_window.batch_update_buttons_to_database(selected_buttons)
        canvas.update_button_positions()
        canvas.update()
    
    def mirror_svg_path_horizontal(self, svg_path_data, canvas_width=None):
        """
        Mirror SVG path data horizontally (flip left-right).
        
        Args:
            svg_path_data (str): The SVG path data string (d attribute)
            canvas_width (float, optional): Width of the canvas/button. If None, uses the path's bounding box
        
        Returns:
            str: The horizontally mirrored SVG path data
        """
        if not svg_path_data:
            return svg_path_data
        
        try:
            
            # Create a temporary path using your existing parser
            temp_path = self._parse_svg_path(svg_path_data)
            if not temp_path:
                return svg_path_data
            
            # Get bounding box
            bounds = temp_path.boundingRect()
            if bounds.isEmpty():
                return svg_path_data
            
            # Calculate center point for mirroring
            if canvas_width is None:
                center_x = bounds.center().x()
            else:
                center_x = canvas_width / 2
            
            # Create transformation matrix for horizontal mirroring
            transform = QtGui.QTransform()
            transform.translate(center_x, 0)
            transform.scale(-1, 1)  # Flip horizontally
            transform.translate(-center_x, 0)
            
            # Apply transformation
            mirrored_path = transform.map(temp_path)
            
            # Convert back to SVG path string
            return self._path_to_svg_string(mirrored_path)
            
        except Exception as e:
            print(f"Error mirroring SVG path horizontally: {e}")
            return svg_path_data

    def mirror_svg_path_vertical(self, svg_path_data, canvas_height=None):
        """
        Mirror SVG path data vertically (flip top-bottom).
        
        Args:
            svg_path_data (str): The SVG path data string (d attribute)
            canvas_height (float, optional): Height of the canvas/button. If None, uses the path's bounding box
        
        Returns:
        str: The vertically mirrored SVG path data
        """
        if not svg_path_data:
            return svg_path_data
        
        try:
            # Use existing parsing method to create QPainterPath
            from PySide6 import QtGui, QtCore
            
            # Create a temporary path using your existing parser
            temp_path = self._parse_svg_path(svg_path_data)
            if not temp_path:
                return svg_path_data
            
            # Get bounding box
            bounds = temp_path.boundingRect()
            if bounds.isEmpty():
                return svg_path_data
            
            # Calculate center point for mirroring
            if canvas_height is None:
                center_y = bounds.center().y()
            else:
                center_y = canvas_height / 2
            
            # Create transformation matrix for vertical mirroring
            transform = QtGui.QTransform()
            transform.translate(0, center_y)
            transform.scale(1, -1)  # Flip vertically
            transform.translate(0, -center_y)
            
            # Apply transformation
            mirrored_path = transform.map(temp_path)
            
            # Convert back to SVG path string
            return self._path_to_svg_string(mirrored_path)
            
        except Exception as e:
            print(f"Error mirroring SVG path vertically: {e}")
            return svg_path_data

    def _path_to_svg_string(self, qpainter_path):
        """
        Convert a QPainterPath back to an SVG path string.
        This is a simplified conversion that handles basic path elements.
        
        Args:
            qpainter_path (QPainterPath): The QPainterPath to convert
        
        Returns:
            str: SVG path data string
        """
        if not qpainter_path:
            return ""
        
        try:
            from PySide6 import QtGui, QtCore
            
            svg_commands = []
            
            # Iterate through path elements
            for i in range(qpainter_path.elementCount()):
                element = qpainter_path.elementAt(i)
                x, y = element.x, element.y
                
                if element.type == QtGui.QPainterPath.MoveToElement:
                    svg_commands.append(f"M{x:.6g},{y:.6g}")
                elif element.type == QtGui.QPainterPath.LineToElement:
                    svg_commands.append(f"L{x:.6g},{y:.6g}")
                elif element.type == QtGui.QPainterPath.CurveToElement:
                    # For cubic curves, we need the next two control points
                    if i + 2 < qpainter_path.elementCount():
                        cp1 = qpainter_path.elementAt(i + 1)
                        cp2 = qpainter_path.elementAt(i + 2)
                        svg_commands.append(f"C{x:.6g},{y:.6g},{cp1.x:.6g},{cp1.y:.6g},{cp2.x:.6g},{cp2.y:.6g}")
            
            # Add close path if needed
            if qpainter_path.elementCount() > 0:
                first_element = qpainter_path.elementAt(0)
                last_element = qpainter_path.elementAt(qpainter_path.elementCount() - 1)
                if (abs(first_element.x - last_element.x) < 0.001 and 
                    abs(first_element.y - last_element.y) < 0.001):
                    svg_commands.append("Z")
            
            return "".join(svg_commands)
            
        except Exception as e:
            print(f"Error converting path to SVG string: {e}")
            return ""
    #---------------------------------------------------------------------------------------
    def contains_point(self, local_pos):
        """
        Check if a local point is within the button's actual shape.
        This respects custom SVG shapes and rounded rectangles.
        
        Args:
            local_pos (QPoint): Position in button-local coordinates
            
        Returns:
            bool: True if point is within the button's shape
        """
        # Convert QPoint to QPointF for consistency
        point = QtCore.QPointF(local_pos.x(), local_pos.y())
        
        # Get current zoom factor from parent canvas
        zoom_factor = self.parent().zoom_factor if self.parent() else 1.0
        
        # Create the button path using the same method as in paintEvent
        rect = self.rect().adjusted(zoom_factor, zoom_factor, -zoom_factor, -zoom_factor)
        path = self._create_button_path(rect, self.radius, zoom_factor)
        
        # Check if the point is within the path
        return path.contains(point)

    def _create_button_path_for_hit_testing(self, rect, zoom_factor):
        """
        Create button path specifically for hit testing.
        This is similar to _create_button_path but optimized for hit detection.
        """
        if self.shape_type == 'custom_path' and self.svg_path_data:
            return self._create_svg_path_for_hit_testing(rect, zoom_factor)
        else:
            return self._create_rounded_rect_path(rect, self.radius, zoom_factor)

    def _create_svg_path_for_hit_testing(self, rect, zoom_factor):
        """Create SVG path for hit testing with proper scaling"""
        try:
            # Parse the SVG path data
            svg_path = self._parse_svg_path(self.svg_path_data)
            if not svg_path:
                # Fallback to rounded rect if parsing fails
                return self._create_rounded_rect_path(rect, self.radius, zoom_factor)
            
            # Get the original path bounds
            original_bounds = svg_path.boundingRect()
            if original_bounds.isEmpty():
                return self._create_rounded_rect_path(rect, self.radius, zoom_factor)
            
            # Calculate scaling factors to fit the button rect
            scale_x = rect.width() / original_bounds.width()
            scale_y = rect.height() / original_bounds.height()
            
            # Use uniform scaling to maintain aspect ratio
            scale = min(scale_x, scale_y) * 0.9  # 0.9 for slight padding
            
            # Calculate centering offsets
            scaled_width = original_bounds.width() * scale
            scaled_height = original_bounds.height() * scale
            offset_x = rect.center().x() - (scaled_width / 2) - (original_bounds.x() * scale)
            offset_y = rect.center().y() - (scaled_height / 2) - (original_bounds.y() * scale)
            
            # Create transformation matrix
            transform = QtGui.QTransform()
            transform.translate(offset_x, offset_y)
            transform.scale(scale, scale)
            
            # Apply transformation to the SVG path
            return transform.map(svg_path)
            
        except Exception as e:
            print(f"Error creating SVG path for hit testing: {e}")
            # Fallback to rounded rect
            return self._create_rounded_rect_path(rect, self.radius, zoom_factor)
    #---------------------------------------------------------------------------------------
    def _should_update_mask(self, zoom_factor, current_size, current_radius, current_shape_type, current_svg_data):
        """Check if mask needs to be regenerated based on cached parameters"""
        
        # Check if mask is missing
        mask_missing = self.cached_mask is None
        
        # Check if parameters changed significantly
        zoom_threshold = 0.2  # Only update mask for significant zoom changes
        size_threshold = 2    # Pixels threshold for size changes
        radius_threshold = 1  # Radius threshold
        
        zoom_changed = abs(self.last_mask_zoom_factor - zoom_factor) > zoom_threshold
        size_changed = (self.last_mask_size is None or 
                    abs(self.last_mask_size.width() - current_size.width()) > size_threshold or
                    abs(self.last_mask_size.height() - current_size.height()) > size_threshold)
        radius_changed = self.last_mask_radius != current_radius
        shape_changed = self.last_mask_shape_type != current_shape_type
        svg_data_changed = self.last_mask_svg_data != current_svg_data
        
        return mask_missing or zoom_changed or size_changed or radius_changed or shape_changed or svg_data_changed

    def _generate_mask(self, zoom_factor):
        """Generate smooth mask using high-resolution rendering"""
        if not self.isVisible():
            return None
        
        rect = self.rect()
        
        try:
            # Create high-resolution pixmap (2x or 4x)
            scale_factor = 4
            high_res_size = rect.size() * scale_factor
            pixmap = QtGui.QPixmap(high_res_size)
            pixmap.fill(QtCore.Qt.transparent)
            
            painter = QtGui.QPainter(pixmap)
            painter.setRenderHint(QtGui.QPainter.Antialiasing, True)
            painter.setRenderHint(QtGui.QPainter.SmoothPixmapTransform, True)
            
            # Scale the painter to high resolution
            painter.scale(scale_factor, scale_factor)
            
            # Create and fill path
            path = self._create_button_path(QtCore.QRect(0, 0, rect.width(), rect.height()), 
                                        self.radius, zoom_factor)
            painter.fillPath(path, QtCore.Qt.black)
            painter.end()
            
            # Scale back down with smooth transformation
            smooth_pixmap = pixmap.scaled(rect.size(), 
                                        QtCore.Qt.KeepAspectRatio, 
                                        QtCore.Qt.SmoothTransformation)
            
            # Create mask from the smooth pixmap
            return QtGui.QRegion(smooth_pixmap.createMaskFromColor(QtCore.Qt.transparent))
            
        except Exception as e:
            print(f"Warning: mask generation failed, using rectangular fallback: {e}")
            return QtGui.QRegion(rect)

    def _invalidate_mask_cache(self):
        """Invalidate the mask cache to force regeneration"""
        self.cached_mask = None
        self.last_mask_zoom_factor = 0
        self.last_mask_size = None
        self.last_mask_radius = None
        self.last_mask_shape_type = None
        self.last_mask_svg_data = None
    #---------------------------------------------------------------------------------------
    def start_duplication_drag(self, event):
        """Start the duplication drag operation"""
        canvas = self.parent()
        if not canvas:
            return
        
        # Ensure this button is selected
        if not self.is_selected:
            canvas.clear_selection()
            self.is_selected = True
            self.selected.emit(self, True)
            canvas.last_selected_button = self
            canvas.button_selection_changed.emit()
            self.update()
        
        # Get all selected buttons for duplication
        selected_buttons = canvas.get_selected_buttons()
        
        # Copy selected buttons to clipboard
        from . import picker_button as PB
        PB.ButtonClipboard.instance().copy_buttons(selected_buttons, event.pos())
        
        # Set duplication state
        self.duplicating = True
        self.drag_start_pos = event.globalPos()
        self.duplication_start_pos = event.pos()
        
        # Change cursor to indicate duplication
        self.setCursor(QtCore.Qt.DragCopyCursor)
        
        #print(f"Started duplication drag with {len(selected_buttons)} buttons")

    def handle_duplication_drag(self, event):
        """Handle the visual feedback during duplication drag"""
        # You could add visual feedback here if desired
        # For now, just update the cursor position
        pass

    def complete_duplication_drag(self, event):
        """Complete the duplication drag operation"""
        canvas = self.parent()
        if not canvas:
            return
        
        try:
            # Reset duplication state
            self.duplicating = False
            self.update_cursor()
            
            # Calculate the drop position
            canvas_pos = canvas.mapFromGlobal(event.globalPos())
            
            # Use the existing paste_buttons_at_position method
            #print(f"Completing duplication at canvas position: {canvas_pos}")
            canvas.paste_buttons_at_position(canvas_pos, mirror=False)
            
            #print("Duplication completed successfully")
            
        except Exception as e:
            print(f"Error during duplication completion: {e}")
            # Reset state on error
            self.duplicating = False
            self.update_cursor()
    #---------------------------------------------------------------------------------------
    def update_cursor(self):
        """Updated cursor handling with duplication support"""
        if hasattr(self, 'duplicating') and self.duplicating:
            self.setCursor(QtCore.Qt.DragCopyCursor)
        elif self.edit_mode:
            self.setCursor(QtCore.Qt.OpenHandCursor)
        else:
            self.setCursor(QtCore.Qt.ArrowCursor)
    
    def update(self):
        super().update()
        self.update_tooltip()
    #---------------------------------------------------------------------------------------
    def toolTip(self):
        """Override to return our custom tooltip text"""
        if hasattr(self, '_tooltip_text'):
            return self._tooltip_text
        return super().toolTip()

    def update_tooltip(self):
        """Update the tooltip with button information using direct widget building"""
        # Just mark that tooltip needs update, don't rebuild here
        self._tooltip_needs_update = True
        self._tooltip_populated = False

    def _rebuild_tooltip_content(self):
        """Actually rebuild the tooltip content when needed"""
        if not self._tooltip_needs_update:
            return
            
        # Clear existing content
        if hasattr(self.tooltip_widget, 'clear_content'):
            self.tooltip_widget.clear_content()
        else:
            # Fallback: recreate the widget if clear_content doesn't exist
            self.tooltip_widget = CB.CustomTooltipWidget(parent=self)
        
        # Create the tooltip content
        color = self.color
        color_box = QtWidgets.QFrame()
        color_box.setStyleSheet(f"background-color: {color}; border:none; border-radius: 4px; border: 1px solid {UT.rgba_value(color, 1.2)};")
        color_box.setFixedSize(12, 12)

        # Check if the button has a custom tooltip from script
        if self.mode == 'script':
            # Header with button name and object count
            header_layout = QtWidgets.QHBoxLayout()

            header_layout.addWidget(color_box)

            if self.script_data and 'custom_tooltip_header' in self.script_data:
                # Use the custom tooltip from script
                custom_tooltip = self.script_data['custom_tooltip_header']
                title_label = QtWidgets.QLabel(custom_tooltip)
                title_label.setStyleSheet("color: #ffffff; border: none; background-color: transparent;")
                header_layout.addWidget(title_label)
            else:
                title_label = QtWidgets.QLabel(f"<b>{self.label}</b>")
                title_label.setStyleSheet("color: #ffffff; font-size: 12px; border:none;background-color: transparent;")
                header_layout.addWidget(title_label)

            
            header_layout.addStretch()

            mode_icon = QtWidgets.QLabel()
            icon_pixmap = UT.get_icon('code.png', size=16)

            if icon_pixmap:
                mode_icon.setPixmap(icon_pixmap)

            header_layout.addWidget(mode_icon)
            self.tooltip_widget.add_layout(header_layout)
            #--------------------------------------------------------------------------------------------------------------------------------
            custom_tooltip_frame = QtWidgets.QFrame()
            custom_tooltip_frame.setFrameStyle(QtWidgets.QFrame.Box)
            custom_tooltip_frame.setStyleSheet("""
                QFrame {
                    background-color: rgba(0, 0, 0, 0.2);
                    border: 1px solid rgba(255, 255, 255, 0.1);
                    border-radius: 3px;
                    padding: 2px;
                }
            """)
            
            custom_tooltip_layout = QtWidgets.QVBoxLayout(custom_tooltip_frame)
            custom_tooltip_layout.setContentsMargins(2, 2, 2, 2)
            custom_tooltip_layout.setSpacing(2)

            if self.script_data and 'custom_tooltip' in self.script_data:
                
                # Use the custom tooltip from script
                custom_tooltip = self.script_data['custom_tooltip']
                custom_tooltip_label = QtWidgets.QLabel(custom_tooltip)
                custom_tooltip_label.setStyleSheet("color: #ffffff; border: none; background-color: transparent;")
            else:
                custom_tooltip_label = QtWidgets.QLabel("No custom tooltip available")
                custom_tooltip_label.setStyleSheet("color: #333333; border: none; background-color: transparent;")

            custom_tooltip_layout.addWidget(custom_tooltip_label)
            
            self.tooltip_widget.add_widget(custom_tooltip_frame)
            #--------------------------------------------------------------------------------------------------------------------------------
            # Info section with horizontal layout
            info_layout = QtWidgets.QHBoxLayout()
            
            # Button ID
            id_label = QtWidgets.QLabel(f"ID: {self.unique_id}")
            id_label.setStyleSheet("color: rgba(255, 255, 255, 0.4); font-size: 10px; border:none;background-color: transparent;")
            info_layout.addWidget(id_label)
            
            info_layout.addStretch()
            
            self.tooltip_widget.add_layout(info_layout)
            
            self._tooltip_needs_update = False
            self._tooltip_populated = True
            return
        #--------------------------------------------------------------------------------------------------------------------------------
        # Header with button name and object count
        header_layout = QtWidgets.QHBoxLayout()
        
        header_layout.addWidget(color_box)
        
        title_label = QtWidgets.QLabel(f"<b><font color='#333333'>NA</font></b>" if not self.label.strip() else f"<b>{self.label}</b>")
        title_label.setStyleSheet("color: #ffffff; font-size: 12px; border:none;background-color: transparent;")
        header_layout.addWidget(title_label)
        
        if self.assigned_objects:
            count_label = QtWidgets.QLabel(f"<span style='color: rgba(255, 255, 255, 0.6);'>({len(self.assigned_objects)})</span>")
            count_label.setStyleSheet("font-size: 12px; border:none;background-color: transparent;")
            header_layout.addWidget(count_label)
        
        header_layout.addStretch()

        mode_icon = QtWidgets.QLabel()
        if self.mode == 'select':
            icon_pixmap = UT.get_icon('select.png', size=16)
        elif self.mode == 'script':
            icon_pixmap = UT.get_icon('code.png', size=16)
        elif self.mode == 'pose':
            icon_pixmap = UT.get_icon('pose_01.png', size=16)

        if icon_pixmap:
            mode_icon.setPixmap(icon_pixmap)

        header_layout.addWidget(mode_icon)

        self.tooltip_widget.add_layout(header_layout)
        #--------------------------------------------------------------------------------------------------------------------------------
        # Objects section with frame
        objects_frame = QtWidgets.QFrame()
        objects_frame.setFrameStyle(QtWidgets.QFrame.Box)
        objects_frame.setStyleSheet("""
            QFrame {
                background-color: rgba(0, 0, 0, 0.2);
                border: 1px solid rgba(255, 255, 255, 0.1);
                border-radius: 3px;
                padding: 2px;
            }
        """)
        
        objects_layout = QtWidgets.QVBoxLayout(objects_frame)
        objects_layout.setContentsMargins(2, 2, 2, 2)
        objects_layout.setSpacing(2)
        
        if self.assigned_objects:
            objects_title = QtWidgets.QLabel("<b>Assigned Objects:</b>" if self.mode == 'select' else "<b>Pose Objects:</b>")
            objects_title.setStyleSheet("color: #ffffff; font-size: 11px; border:none;background-color: transparent;")
            objects_layout.addWidget(objects_title)
            
            object_names = []
            
            # Handle both bones and objects in the tooltip
            for obj_data in self.assigned_objects:
                if obj_data.get('is_bone', False):
                    # For bones, show bone name and armature
                    bone_name = obj_data.get('name', '')
                    armature_name = obj_data.get('armature', '')
                    display_name = f"{bone_name} (in {armature_name})"
                    object_names.append(display_name)
                else:
                    # For regular objects, just show the object name
                    obj_name = obj_data.get('name', '')
                    # Strip namespace for display if needed
                    short_name = obj_name.split('_')[-1] if '_' in obj_name else obj_name
                    object_names.append(short_name)
            
            if object_names:
                # Limit to first 10 objects and indicate if there are more
                displayed_objects = object_names[:5]
                
                for obj_name in displayed_objects:
                    obj_label = QtWidgets.QLabel(f"• {obj_name}")
                    obj_label.setStyleSheet("color: rgba(255, 255, 255, 0.9); font-size: 10px; margin-left: 8px; border:none;background-color: transparent;")
                    objects_layout.addWidget(obj_label)
                
                if len(object_names) > 5:
                    remaining_count = len(object_names) - 5
                    more_label = QtWidgets.QLabel(f"<i>...and {remaining_count} more object{'s' if remaining_count > 1 else ''}</i>")
                    more_label.setStyleSheet("color: rgba(255, 255, 255, 0.5); font-size: 9px; margin-left: 8px; border:none;background-color: transparent;")
                    objects_layout.addWidget(more_label)
            else:
                no_objects_label = QtWidgets.QLabel("(No valid objects found)")
                no_objects_label.setStyleSheet("color: rgba(255, 255, 255, 0.6); font-size: 9px; font-style: italic; border:none;background-color: transparent;")
                objects_layout.addWidget(no_objects_label)
        else:
            no_assigned_label = QtWidgets.QLabel("<i>No objects assigned</i>")
            no_assigned_label.setStyleSheet("color: rgba(255, 255, 255, 0.6); font-size: 9px; border:none;background-color: transparent;")
            objects_layout.addWidget(no_assigned_label)
        
        self.tooltip_widget.add_widget(objects_frame)
        #--------------------------------------------------------------------------------------------------------------------------------
        # Info section with horizontal layout
        info_layout = QtWidgets.QHBoxLayout()
        
        # Button ID
        id_label = QtWidgets.QLabel(f"ID: {self.unique_id}")
        id_label.setStyleSheet("color: rgba(255, 255, 255, 0.5); font-size: 10px; border:none;background-color: transparent;")
        info_layout.addWidget(id_label)
        
        info_layout.addStretch()
        
        # Thumbnail info for pose mode
        if self.mode == 'pose':
            if self.thumbnail_path:
                thumb_label = QtWidgets.QLabel(f"[{os.path.basename(self.thumbnail_path).split('.')[0]}]")
                thumb_label.setStyleSheet("color: rgba(255, 255, 255, 0.6); font-size: 10px; border:none;background-color: transparent;")
                info_layout.addWidget(thumb_label)
            else:
                no_thumb_label = QtWidgets.QLabel("<i>No thumbnail</i>")
                no_thumb_label.setStyleSheet("color: rgba(255, 255, 255, 0.4); font-size: 9px; border:none;background-color: transparent;")
                info_layout.addWidget(no_thumb_label)
        
        self.tooltip_widget.add_layout(info_layout)
        #--------------------------------------------------------------------------------------------------------------------------------
        
        # Mark as updated
        self._tooltip_needs_update = False
        self._tooltip_populated = True
    #---------------------------------------------------------------------------------------
    def set_mode(self, mode):
        canvas = self.parent()
        main_window = canvas.window()
        if canvas:
            # Apply mode change to all selected buttons
            selected_buttons = canvas.get_selected_buttons()

            canvas.setUpdatesEnabled(False)
            for button in selected_buttons:
                # Store original height before changing to pose mode
                if mode == 'pose' and button.mode != 'pose':
                    button._original_height = button.height
                    # Set height to 1.25 times width for pose mode
                    button.height = button.width * 1.25
                # Restore original height when changing from pose mode to another mode
                elif button.mode == 'pose' and mode != 'pose' and hasattr(button, '_original_height'):
                    button.height = button._original_height
                
                if hasattr(main_window, 'pending_button_updates'):
                    main_window.pending_button_updates.add(button.unique_id)
                
                button.mode = mode
                button.update()
                button.changed.emit(button)
                canvas.update_button_positions()

            if hasattr(main_window, '_flush_pending_updates'):
                main_window._flush_pending_updates()

            canvas.setUpdatesEnabled(True)
            
        else:
            # Fallback for single button if no canvas parent
            # Store original height before changing to pose mode
            if mode == 'pose' and self.mode != 'pose':
                self._original_height = self.height
                # Set height to 1.25 times width for pose mode
                self.height = self.width * 1.25
            # Restore original height when changing from pose mode to another mode
            elif self.mode == 'pose' and mode != 'pose' and hasattr(self, '_original_height'):
                self.height = self._original_height
                
            self.mode = mode
            self.update()
            self.changed.emit(self)
            canvas.update_button_positions()

        

        self.pose_pixmap = None
        self.last_zoom_factor = 0
        self.last_size = None

    def handle_select_mode_click(self, shift_held, ctrl_held, alt_held, canvas,event):
        """Handle selection logic for different modifier combinations"""
        if not self.selectable:
            event.ignore()
            return
        # Store this as the last clicked button for active object determination
        canvas.last_clicked_button = self
        
        if ctrl_held and shift_held and not alt_held:
            # Ctrl + Shift + Click: Toggle this button off if selected, ignore if not selected
            if self.is_selected:
                self.is_selected = False
                self.selected.emit(self, False)
                # Don't set as last_selected_button when deselecting
            # If not selected, do nothing (don't select it)
            
        elif shift_held and not ctrl_held and not alt_held:
            # Shift + Click: Add to selection
            if not self.is_selected:
                self.is_selected = True
                self.selected.emit(self, True)
                canvas.last_selected_button = self
            # If already selected, keep it selected
            
        elif alt_held and shift_held and not ctrl_held:
            # Alt + Shift + Click: Add counterparts to selection
            if not self.is_selected:
                self.is_selected = True
                self.selected.emit(self, True)
                canvas.last_selected_button = self
            # Apply selection with counterpart mode
            canvas.apply_final_selection(add_to_selection=True, ctrl_held=True)  # ctrl_held=True for counterparts
            return  # Early return since apply_final_selection handles everything
            
        elif alt_held and not shift_held and not ctrl_held:
            # Alt + Click: Replace selection with counterparts
            canvas.clear_selection()
            self.is_selected = True
            self.selected.emit(self, True)
            canvas.last_selected_button = self
            # Apply selection with counterpart mode
            canvas.apply_final_selection(add_to_selection=False, ctrl_held=True)  # ctrl_held=True for counterparts
            return  # Early return since apply_final_selection handles everything
            
        else:
            # No modifiers or unsupported combination: Replace selection
            canvas.clear_selection()
            self.is_selected = True
            self.selected.emit(self, True)
            canvas.last_selected_button = self
        
        # Update UI
        canvas.button_selection_changed.emit()
        self.update()
        
        # Apply regular selection (not counterpart)
        canvas.apply_final_selection(add_to_selection=shift_held, ctrl_held=False)

    def toggle_selection(self):
        self.set_selected(not self.is_selected)
        if self.parent():
            self.parent().button_selection_changed.emit()

    def set_selected(self, selected):
        """Update selection state without triggering Maya selection"""
        if self.is_selected != selected:
            self.is_selected = selected
            self.selected.emit(self, self.is_selected)
            self.update()
    
    def update_visual_state(self, selected):
        """Update only the visual selection state"""
        if self.is_selected != selected:
            self.is_selected = selected
            self.update()
    #---------------------------------------------------------------------------------------
    def toggle_selectable(self):
        self.selectable = True
        self.update()
        self.changed.emit(self)

    def toggle_selectable_for_selected_buttons(self):
        for button in self.parent().get_selected_buttons():
            button.toggle_selectable()
    
    def toggle_unselectable(self):
        self.selectable = False
        self.update()
        self.changed.emit(self)

    def toggle_unselectable_for_selected_buttons(self):
        for button in self.parent().get_selected_buttons():
            button.toggle_unselectable()
    #---------------------------------------------------------------------------------------
    def show_context_menu(self, pos):
        menu = QtWidgets.QMenu()
        menu.setWindowFlags(menu.windowFlags() | QtCore.Qt.FramelessWindowHint | QtCore.Qt.NoDropShadowWindowHint)
        menu.setAttribute(QtCore.Qt.WA_TranslucentBackground)
        menu.setStyleSheet(f'''
            QMenu {{
                background-color: rgba(30, 30, 30, .9);
                border: 1px solid #444444;
                border-radius: 3px;
                padding: 5px 7px;
            }}
            QMenu::item {{
                background-color: transparent;
                padding: 3px 30px 3px 3px; ;
                margin: 3px 0px  ;
                border-radius: 3px;
            }}
            QMenu::item:hover {{
                background-color: #444444;
            }}
            QMenu::item:selected {{
                background-color: #444444;
            }}
            QMenu::right-arrow {{
                width: 10px;
                height: 10px;
            }}
            QPushButton {{
                border-radius: 3px;
                background-color: #333333;
            }}
            QPushButton:hover {{
                background-color: #444444;
            }}''')

        # Mode selection
        mode_menu = QtWidgets.QMenu("Mode")
        mode_menu.setStyleSheet(menu.styleSheet())
        
        select_action = QtGui.QAction(QtGui.QIcon(UT.get_icon("select.png")), "Select Mode", self)
        select_action.setCheckable(True)
        select_action.setChecked(self.mode == 'select')
        select_action.triggered.connect(lambda: self.set_mode('select'))
        
        script_action = QtGui.QAction(QtGui.QIcon(UT.get_icon("code.png")), "Script Mode", self)
        script_action.setCheckable(True)
        script_action.setChecked(self.mode == 'script')
        script_action.triggered.connect(lambda: self.set_mode('script'))
        
        pose_action = QtGui.QAction(QtGui.QIcon(UT.get_icon("pose_01.png")), "Pose Mode", self)
        pose_action.setCheckable(True)
        pose_action.setChecked(self.mode == 'pose')
        pose_action.triggered.connect(lambda: self.set_mode('pose'))
        
        mode_group = QtGui.QActionGroup(self)
        mode_group.addAction(select_action)
        mode_group.addAction(script_action)
        mode_group.addAction(pose_action)
        
        mode_menu.addAction(select_action)
        mode_menu.addAction(script_action)
        mode_menu.addAction(pose_action)
        
        
        # Copy, Paste and Delete Actions
        #---------------------------------------------------------------------------------------
        if self.edit_mode:
            # Add thumbnail options for pose mode buttons
            if self.mode == 'pose':
                thumbnail_menu = QtWidgets.QMenu("Thumbnail", menu)
                thumbnail_menu.setIcon(QtGui.QIcon(UT.get_icon('image.png')))
                thumbnail_menu.setStyleSheet(menu.styleSheet())
                
                add_thumbnail_action = thumbnail_menu.addAction("Add Thumbnail")
                add_thumbnail_action.triggered.connect(self.add_thumbnail)

                update_thumbnail_action = thumbnail_menu.addAction("Update Thumbnail")
                update_thumbnail_action.triggered.connect(self.update_thumbnail)
                update_thumbnail_action.setEnabled(bool(self.thumbnail_path))
                
                select_thumbnail_action = thumbnail_menu.addAction("Select Thumbnail")
                select_thumbnail_action.triggered.connect(self.select_thumbnail)
                
                remove_thumbnail_action = thumbnail_menu.addAction("Remove Thumbnail")
                remove_thumbnail_action.triggered.connect(self.remove_thumbnail)
                remove_thumbnail_action.setEnabled(bool(self.thumbnail_path))
                
                repath_thumbnail_action = thumbnail_menu.addAction("Repath Thumbnail")
                repath_thumbnail_action.triggered.connect(partial(self.repath_thumbnails_for_selected_buttons))
                repath_thumbnail_action.setEnabled(bool(self.thumbnail_path))
                menu.addMenu(thumbnail_menu)
            
            #---------------------------------------------------------------------------------------
            # Button placement submenu
            placement_menu = QtWidgets.QMenu("Placement", menu)
            placement_menu.setIcon(QtGui.QIcon(UT.get_icon("align_left.png")))
            placement_menu.setStyleSheet(menu.styleSheet())
            
            # Z-order actions (keep these as text)
            move_behind_action = placement_menu.addAction("Move Behind")
            move_behind_action.triggered.connect(self.move_button_behind)
            
            bring_forward_action = placement_menu.addAction("Bring Forward")
            bring_forward_action.triggered.connect(self.bring_button_forward)

            horizontal_mirror_action = placement_menu.addAction("Horizontal Mirror")
            horizontal_mirror_action.triggered.connect(partial(self.parent().horizontal_mirror_button_positions))
            
            horizontal_mirror_flip_action = placement_menu.addAction("Horizontal Mirror (WC)")
            horizontal_mirror_flip_action.triggered.connect(partial(self.parent().horizontal_mirror_button_positions, apply_counterparts=True))
            horizontal_mirror_flip_action.setToolTip("Mirror selected buttons horizontally and assigne counterpart objects")

            vertical_mirror_action = placement_menu.addAction("Vertical Mirror")
            vertical_mirror_action.triggered.connect(partial(self.parent().vertical_mirror_button_positions))
            
            placement_menu.addSeparator()
            
            # Create a grid widget for alignment options
            grid_widget = QtWidgets.QWidget()
            grid_layout = QtWidgets.QGridLayout(grid_widget)
            grid_layout.setContentsMargins(2, 2, 2, 2)
            grid_layout.setSpacing(4)
            
            def create_alignment_button(icon_path, tooltip, callback):
                btn = QtWidgets.QPushButton()
                btn.setFixedSize(28, 28)
                btn.setIcon(UT.get_icon(icon_path, opacity=0.9))
                btn.setIconSize(QtCore.QSize(21, 21))
                btn.setToolTip(tooltip)
                btn.clicked.connect(callback)
                return btn
            
            # Row 1: Vertical alignment options
            align_left_btn = create_alignment_button("align_left.png", "Align Left", self.align_button_left)
            align_center_btn = create_alignment_button("align_vCenter.png", "Align Vertical Center", self.align_button_center)
            align_right_btn = create_alignment_button("align_right.png", "Align Right", self.align_button_right)
            v_space_btn = create_alignment_button("v_spacing.png", "Distribute Evenly (Vertical)", self.evenly_space_vertical)
            
            # Row 2: Horizontal alignment options
            align_top_btn = create_alignment_button("align_top.png", "Align Top", self.align_button_top)
            align_middle_btn = create_alignment_button("align_hCenter.png", "Align Horizontal Center", self.align_button_middle)
            align_bottom_btn = create_alignment_button("align_bottom.png", "Align Bottom", self.align_button_bottom)
            h_space_btn = create_alignment_button("h_spacing.png", "Distribute Evenly (Horizontal)", self.evenly_space_horizontal)
            
            color_palette_btn = CCP.ColorPicker(mode='palette')
            current_qcolor = QtGui.QColor(self.color)  # Convert hex string to QColor
            color_palette_btn.current_color = current_qcolor
            color_palette_btn.update_all_from_color()  # Update the palette's display
            color_palette_btn.colorChanged.connect(lambda c: self.change_color_for_selected_buttons(c.name()))
            
            grid_layout.addWidget(align_left_btn, 0, 0)
            grid_layout.addWidget(align_center_btn, 0, 1)
            grid_layout.addWidget(align_right_btn, 0, 2)
            grid_layout.addWidget(v_space_btn, 0, 3)

            grid_layout.addWidget(align_top_btn, 1, 0)
            grid_layout.addWidget(align_middle_btn, 1, 1)
            grid_layout.addWidget(align_bottom_btn, 1, 2)
            grid_layout.addWidget(h_space_btn, 1, 3)
            grid_layout.addWidget(color_palette_btn, 2, 0, 1, 4)

            # Add the grid widget to the placement menu
            grid_action = QtWidgets.QWidgetAction(placement_menu)
            grid_action.setDefaultWidget(grid_widget)
            placement_menu.addAction(grid_action)

            menu.addMenu(placement_menu)
            #---------------------------------------------------------------------------------------
            shape_menu = QtWidgets.QMenu("Shape", menu)
            shape_menu.setIcon(QtGui.QIcon(UT.get_icon('shape.png')))  # You'll need a shape icon
            shape_menu.setStyleSheet(menu.styleSheet())
            
            # Add shape options
            rounded_rect_action = shape_menu.addAction("Rounded Rectangle")
            rounded_rect_action.setCheckable(True)
            rounded_rect_action.setChecked(self.shape_type == 'rounded_rect')
            rounded_rect_action.triggered.connect(self.reset_to_rounded_rect)
            
            custom_shape_action = shape_menu.addAction("Enable Custom Shapes")
            custom_shape_action.setCheckable(True)
            custom_shape_action.setChecked(self.shape_type == 'custom_path')
            custom_shape_action.triggered.connect(self.enable_custom_shapes_for_selected)

            shape_menu.addSeparator()

            apply_shape_action = shape_menu.addAction("Apply This Shape to Selected")
            apply_shape_action.setEnabled(bool(self.svg_path_data))
            apply_shape_action.triggered.connect(self.apply_same_shape_to_selected)

            load_svg_action = shape_menu.addAction("Load SVG")
            load_svg_action.triggered.connect(self.load_svg_shape)
            
            menu.addMenu(shape_menu)
            #---------------------------------------------------------------------------------------
            # Copy Action
            menu.addSeparator()
            copy_action = menu.addAction(QtGui.QIcon(UT.get_icon('copy.png')), "Copy Button")
            copy_action.triggered.connect(self.copy_selected_buttons)
            
            #---------------------------------------------------------------------------------------
            # Create Paste submenu
            paste_menu = QtWidgets.QMenu("Paste Options", menu)
            paste_menu.setIcon(QtGui.QIcon(UT.get_icon('paste.png')))
            paste_menu.setStyleSheet(menu.styleSheet())
            
            paste_all_action = paste_menu.addAction("Paste All")
            paste_all_action.triggered.connect(lambda: self.paste_attributes('all'))
            
            paste_dimension_action = paste_menu.addAction("Paste Dimension")
            paste_dimension_action.triggered.connect(lambda: self.paste_attributes('dimension'))
            
            paste_function_action = paste_menu.addAction("Paste Function")
            paste_function_action.triggered.connect(lambda: self.paste_attributes('function'))
            
            paste_text_action = paste_menu.addAction("Paste Text")
            paste_text_action.triggered.connect(lambda: self.paste_attributes('text'))
            
            # Enable/disable paste actions based on clipboard content
            has_clipboard = bool(ButtonClipboard.instance().get_last_attributes())
            paste_all_action.setEnabled(has_clipboard)
            paste_dimension_action.setEnabled(has_clipboard)
            paste_function_action.setEnabled(has_clipboard)
            paste_text_action.setEnabled(has_clipboard)
            
            menu.addMenu(paste_menu)
            
            #---------------------------------------------------------------------------------------
            # Delete Action
            delete_action = menu.addAction(QtGui.QIcon(UT.get_icon('delete_red.png')),"Delete Button")
            delete_action.triggered.connect(self.delete_selected_buttons)
            menu.addSeparator()
            #---------------------------------------------------------------------------------------
            # Selectable Action
            selectable_action = QAction(QtGui.QIcon(UT.get_icon('selectable.png')),"Selectable")
            selectable_action.setCheckable(True)
            selectable_action.setChecked(True)
            selectable_action.triggered.connect(self.toggle_unselectable_for_selected_buttons)

            unselectable_action = QAction(QtGui.QIcon(UT.get_icon('selectable.png')),"Selectable")
            unselectable_action.setCheckable(True)
            unselectable_action.setChecked(False)
            unselectable_action.triggered.connect(self.toggle_selectable_for_selected_buttons)

            if self.selectable:
                menu.addAction(selectable_action)
            else:
                menu.addAction(unselectable_action)
            
            if self.mode == 'select':
                selection_manager_action = menu.addAction(QtGui.QIcon(UT.get_icon('select.png')),"Selection Manager")
                selection_manager_action.triggered.connect(self.show_selection_manager)
                selection_manager_action.setEnabled(
                    len(self.parent().get_selected_buttons()) == 1
                )
            elif self.mode == 'script':
                script_manager_action = menu.addAction(QtGui.QIcon(UT.get_icon('code.png')),"Script Manager")
                script_manager_action.triggered.connect(self.show_script_manager)
            #---------------------------------------------------------------------------------------
        else:
            # Selection 
            #---------------------------------------------------------------------------------------
            if self.mode == 'select':
                # Selection Mode menu items
                add_to_selection_action = menu.addAction(QtGui.QIcon(UT.get_icon('add.png')), "Add Selection")
                add_to_selection_action.triggered.connect(self.add_selected_objects)

                remove_all_from_selection_action = menu.addAction(QtGui.QIcon(UT.get_icon('subtract.png')), "Remove all Selection")
                remove_all_from_selection_action.triggered.connect(self.remove_all_objects_for_selected_buttons)

                selection_manager_action = menu.addAction(QtGui.QIcon(UT.get_icon('select.png')),"Selection Manager")
                selection_manager_action.triggered.connect(self.show_selection_manager)
                selection_manager_action.setEnabled(
                    len(self.parent().get_selected_buttons()) == 1
                )
            elif self.mode == 'script':
                # Script Mode menu items
                script_manager_action = menu.addAction(QtGui.QIcon(UT.get_icon('code.png')),"Script Manager")
                script_manager_action.triggered.connect(self.show_script_manager)
            elif self.mode == 'pose':
                # Pose Mode menu items
                add_pose_action = menu.addAction(QtGui.QIcon(UT.get_icon('add.png')),"Add Pose")
                add_pose_action.triggered.connect(self.add_pose)
                
                remove_pose_action = menu.addAction(QtGui.QIcon(UT.get_icon('subtract.png')),"Remove Pose")
                remove_pose_action.triggered.connect(self.remove_pose_for_selected_buttons)

                thumbnail_menu = QtWidgets.QMenu("Thumbnail")
                thumbnail_menu.setIcon(QtGui.QIcon(UT.get_icon('image.png')))
                thumbnail_menu.setStyleSheet(menu.styleSheet())
                
                add_thumbnail_action = thumbnail_menu.addAction("Add Thumbnail")
                add_thumbnail_action.triggered.connect(self.add_thumbnail)

                update_thumbnail_action = thumbnail_menu.addAction("Update Thumbnail")
                update_thumbnail_action.triggered.connect(self.update_thumbnail)
                update_thumbnail_action.setEnabled(bool(self.thumbnail_path))
                
                select_thumbnail_action = thumbnail_menu.addAction("Select Thumbnail")
                select_thumbnail_action.triggered.connect(self.select_thumbnail)
                
                remove_thumbnail_action = thumbnail_menu.addAction("Remove Thumbnail")
                remove_thumbnail_action.triggered.connect(self.remove_thumbnail)
                remove_thumbnail_action.setEnabled(bool(self.thumbnail_path))

                repath_thumbnail_action = thumbnail_menu.addAction("Repath Thumbnail")
                repath_thumbnail_action.triggered.connect(partial(self.repath_thumbnails_for_selected_buttons))
                repath_thumbnail_action.setEnabled(bool(self.thumbnail_path))
                
                menu.addMenu(thumbnail_menu)    
        
        menu.addMenu(mode_menu)
        menu.addSeparator()

        menu.exec_(self.mapToGlobal(pos))
        
    def show_selection_manager(self):
        # Find the parent picker window
        canvas = self.parent() if hasattr(self, 'parent') else None
        picker_window = canvas.window() if canvas else self.window()
        
        if not hasattr(self, 'selection_manager'):
            from . import pb_selection_manager
            self.selection_manager = pb_selection_manager.SelectionManagerWidget(picker_window)
        
        self.selection_manager.set_picker_button(self)
        
        # Position widget to the right of the button
        pos = self.mapToGlobal(self.rect().topRight())
        self.selection_manager.move(pos + QtCore.QPoint(10, 0))
        self.selection_manager.show()

    def show_script_manager(self):
        """Show the script manager widget for this button"""
        # Find the parent picker window
        canvas = self.parent()
        picker_window = canvas.window() if canvas else None
        
        # Check if a script manager already exists
        if not hasattr(self, 'script_manager') or not self.script_manager:
            from . import pb_script_manager
            # Pass the picker window as parent for proper tracking
            self.script_manager = pb_script_manager.ScriptManagerWidget(picker_window)
        
        self.script_manager.set_picker_button(self)
        self.script_manager.show()

    def move_button_behind(self):
        """Move the selected buttons behind other buttons in the z-order"""
        canvas = self.parent()
        if canvas and canvas.edit_mode:
            selected_buttons = canvas.get_selected_buttons()
            if selected_buttons:
                # For each selected button, move it to the beginning of the buttons list
                for button in selected_buttons:
                    if button in canvas.buttons:
                        canvas.buttons.remove(button)
                        canvas.buttons.insert(0, button)  # Insert at the beginning (bottom of z-order)
                        # Ensure button is visually at the bottom of the stack
                        button.lower()
                        # Trigger data update
                        canvas.update_button_data(button)
                
                # Update the button positions and z-order
                canvas.update_button_positions()
                # Force a repaint
                canvas.update()
                
                # Update the main window data
                main_window = canvas.window()
                if hasattr(main_window, 'update_button_z_order'):
                    main_window.update_button_z_order()
                     
    def bring_button_forward(self):
        """Bring the selected buttons forward in the z-order"""
        canvas = self.parent()
        if canvas and canvas.edit_mode:
            selected_buttons = canvas.get_selected_buttons()
            if selected_buttons:
                # For each selected button, move it to the end of the buttons list
                for button in selected_buttons:
                    if button in canvas.buttons:
                        canvas.buttons.remove(button)
                        canvas.buttons.append(button)  # Append to the end (top of z-order)
                        # Ensure button is visually at the top of the stack
                        button.raise_()
                        # Trigger data update
                        canvas.update_button_data(button)
                
                # Update the button positions and z-order
                canvas.update_button_positions()
                # Force a repaint
                canvas.update()
                
                # Update the main window data
                main_window = canvas.window()
                if hasattr(main_window, 'update_button_z_order'):
                    main_window.update_button_z_order()

    def _batch_update_button_positions(self, selected_buttons, main_window):
        """Optimized batch update for button positions after drag"""
        if not selected_buttons:
            return
        
        current_tab = main_window.tab_system.current_tab
        if not current_tab:
            return
        
        # CRITICAL: Completely disable all update systems during batch
        was_batch_active = getattr(main_window, 'batch_update_active', False)
        main_window.batch_update_active = True
        
        # Stop any running timers
        if hasattr(main_window, 'batch_update_timer'):
            main_window.batch_update_timer.stop()
        
        try:
            # Get tab data once
            tab_data = DM.PickerDataManager.get_tab_data(current_tab)
            
            # Build position update dictionary
            position_updates = {}
            updated_buttons = []
            
            # Disconnect changed signals temporarily to prevent interference
            for button in selected_buttons:
                try:
                    button.changed.disconnect()
                except:
                    pass
                
                # Collect position data
                position_updates[button.unique_id] = (
                    button.scene_position.x(), 
                    button.scene_position.y()
                )
                updated_buttons.append(button.unique_id)
            
            # Single database update for all positions
            for button_data in tab_data['buttons']:
                if button_data['id'] in position_updates:
                    new_x, new_y = position_updates[button_data['id']]
                    button_data['position'] = (new_x, new_y)
            
            # Write to database once
            DM.PickerDataManager.update_tab_data(current_tab, tab_data)
            
            # Reconnect signals
            for button in selected_buttons:
                button.changed.connect(main_window.on_button_changed)
            
            #print(f"Batch updated positions for {len(selected_buttons)} buttons")
            
        finally:
            # Restore batch mode state
            main_window.batch_update_active = was_batch_active
            
            # Update transform guides once at the end
            canvas = self.parent()
            if hasattr(canvas, 'transform_guides') and canvas.transform_guides.isVisible():
                QtCore.QTimer.singleShot(10, canvas._update_transform_guides_position)
    
    def _batch_update_button_scaling(self, selected_buttons, main_window):
        """Optimized batch update for button scaling after transform guide operations"""
        if not selected_buttons:
            return
        
        current_tab = main_window.tab_system.current_tab
        if not current_tab:
            return
        
        # CRITICAL: Completely disable all update systems during batch
        was_batch_active = getattr(main_window, 'batch_update_active', False)
        main_window.batch_update_active = True
        
        # Stop any running timers to prevent interference
        timers_to_stop = ['batch_update_timer', 'widget_update_timer']
        stopped_timers = {}
        
        for timer_name in timers_to_stop:
            if hasattr(main_window, timer_name):
                timer = getattr(main_window, timer_name)
                if timer.isActive():
                    timer.stop()
                    stopped_timers[timer_name] = True
        
        # Clear any pending updates
        if hasattr(main_window, 'pending_button_updates'):
            main_window.pending_button_updates.clear()
        
        try:
            # Store original signal connections for restoration
            signal_connections = {}
            
            # Disconnect changed signals temporarily to prevent interference
            for button in selected_buttons:
                try:
                    # Store the connection info before disconnecting
                    signal_connections[button.unique_id] = button.changed.receivers()
                    button.changed.disconnect()
                except:
                    pass
            
            # Get tab data once for efficiency
            tab_data = DM.PickerDataManager.get_tab_data(current_tab)
            
            # Build scaling update dictionary with all properties
            scaling_updates = {}
            for button in selected_buttons:
                scaling_updates[button.unique_id] = {
                    'position': (button.scene_position.x(), button.scene_position.y()),
                    'width': button.width,
                    'height': button.height,
                    'radius': button.radius.copy() if hasattr(button.radius, 'copy') else list(button.radius)
                }
            
            # Single database update for all scaling changes
            updated_count = 0
            for button_data in tab_data['buttons']:
                if button_data['id'] in scaling_updates:
                    updates = scaling_updates[button_data['id']]
                    button_data['position'] = updates['position']
                    button_data['width'] = updates['width']
                    button_data['height'] = updates['height']
                    button_data['radius'] = updates['radius']
                    updated_count += 1
            
            # Write to database once
            if updated_count > 0:
                DM.PickerDataManager.update_tab_data(current_tab, tab_data)
                #print(f"Batch updated scaling for {updated_count} buttons")
            
            # Reconnect signals properly
            for button in selected_buttons:
                # Reconnect to the main window's handler
                if hasattr(main_window, 'on_button_changed'):
                    button.changed.connect(main_window.on_button_changed)
                else:
                    # Fallback connection
                    button.changed.connect(main_window.update_button_data)
            
        except Exception as e:
            print(f"Error during batch scaling update: {e}")
            
            # Emergency signal reconnection
            for button in selected_buttons:
                try:
                    button.changed.connect(main_window.update_button_data)
                except:
                    pass
                    
        finally:
            # Restore batch mode state
            main_window.batch_update_active = was_batch_active
            
            # Restart stopped timers if they were originally active
            for timer_name, was_active in stopped_timers.items():
                if was_active and hasattr(main_window, timer_name):
                    timer = getattr(main_window, timer_name)
                    # Give a small delay before restarting
                    QtCore.QTimer.singleShot(100, timer.start)

    def color_button_clicked(self, color):
        self.change_color_for_selected_buttons(color)
    #---------------------------------------------------------------------------------------
    def align_button_center(self):
        """Align selected buttons to be centered horizontally"""
        canvas = self.parent()
        main_window = canvas.window()
        if canvas and canvas.edit_mode:
            selected_buttons = canvas.get_selected_buttons()
            if len(selected_buttons) <= 1:
                return
                
            # Calculate the average x position (center point)
            avg_x = sum(button.scene_position.x() for button in selected_buttons) / len(selected_buttons)
            
            # Move all buttons to have the same x coordinate
            for button in selected_buttons:
                current_pos = button.scene_position
                new_pos = QtCore.QPointF(avg_x, current_pos.y())
                button.scene_position = new_pos
                
                if hasattr(main_window, 'batch_update_buttons_to_database'):
                    main_window.batch_update_buttons_to_database(selected_buttons)
                canvas.update_button_positions()
                canvas.update()

    def align_button_left(self):
        """Align selected buttons to the leftmost button's left edge"""
        canvas = self.parent()
        main_window = canvas.window()

        if canvas and canvas.edit_mode:
            selected_buttons = canvas.get_selected_buttons()
            if len(selected_buttons) <= 1:
                return
                
            # Find the leftmost button's left edge position
            left_edge = float('inf')
            for button in selected_buttons:
                # Calculate the left edge position (center x - half width)
                button_left = button.scene_position.x() - (button.width / 2)
                left_edge = min(left_edge, button_left)
            
            # Move all buttons to align their left edges
            for button in selected_buttons:
                current_pos = button.scene_position
                # Calculate new center position (left_edge + half width)
                new_center_x = left_edge + (button.width / 2)
                new_pos = QtCore.QPointF(new_center_x, current_pos.y())
                button.scene_position = new_pos

            if hasattr(main_window, 'batch_update_buttons_to_database'):
                main_window.batch_update_buttons_to_database(selected_buttons)
            canvas.update_button_positions()
            canvas.update()
    
    def align_button_right(self):
        """Align selected buttons to the rightmost button's right edge"""
        canvas = self.parent()
        main_window = canvas.window()
        if canvas and canvas.edit_mode:
            selected_buttons = canvas.get_selected_buttons()
            if len(selected_buttons) <= 1:
                return
                
            # Find the rightmost button's right edge position
            right_edge = float('-inf')
            for button in selected_buttons:
                # Calculate the right edge position (center x + half width)
                button_right = button.scene_position.x() + (button.width / 2)
                right_edge = max(right_edge, button_right)
            
            # Move all buttons to align their right edges
            for button in selected_buttons:
                current_pos = button.scene_position
                # Calculate new center position (right_edge - half width)
                new_center_x = right_edge - (button.width / 2)
                new_pos = QtCore.QPointF(new_center_x, current_pos.y())
                button.scene_position = new_pos
            
            if hasattr(main_window, 'batch_update_buttons_to_database'):
                main_window.batch_update_buttons_to_database(selected_buttons)
            canvas.update_button_positions()
            canvas.update()
    #---------------------------------------------------------------------------------------
    def align_button_top(self):
        """Align selected buttons to the topmost button's top edge"""
        canvas = self.parent()
        main_window = canvas.window()
        if canvas and canvas.edit_mode:
            selected_buttons = canvas.get_selected_buttons()
            if len(selected_buttons) <= 1:
                return
                
            # Find the topmost button's top edge position (lowest y value in scene coordinates)
            top_edge = float('inf')
            for button in selected_buttons:
                # Calculate the top edge position (center y - half height)
                button_top = button.scene_position.y() - (button.height / 2)
                top_edge = min(top_edge, button_top)
            
            # Move all buttons to align their top edges
            for button in selected_buttons:
                current_pos = button.scene_position
                # Calculate new center position (top_edge + half height)
                new_center_y = top_edge + (button.height / 2)
                new_pos = QtCore.QPointF(current_pos.x(), new_center_y)
                button.scene_position = new_pos
            
            if hasattr(main_window, 'batch_update_buttons_to_database'):
                main_window.batch_update_buttons_to_database(selected_buttons)
            canvas.update_button_positions()
            canvas.update()
    
    def align_button_middle(self):
        """Align selected buttons to be centered vertically"""
        canvas = self.parent()
        main_window = canvas.window()
        if canvas and canvas.edit_mode:
            selected_buttons = canvas.get_selected_buttons()
            if len(selected_buttons) <= 1:
                return
                
            # Calculate the average y position (middle point)
            avg_y = sum(button.scene_position.y() for button in selected_buttons) / len(selected_buttons)
            
            # Move all buttons to have the same y coordinate
            for button in selected_buttons:
                current_pos = button.scene_position
                new_pos = QtCore.QPointF(current_pos.x(), avg_y)
                button.scene_position = new_pos
            
            if hasattr(main_window, 'batch_update_buttons_to_database'):
                main_window.batch_update_buttons_to_database(selected_buttons)
            canvas.update_button_positions()
            canvas.update()
    
    def align_button_bottom(self):
        """Align selected buttons to the bottommost button's bottom edge"""
        canvas = self.parent()
        main_window = canvas.window()
        if canvas and canvas.edit_mode:
            selected_buttons = canvas.get_selected_buttons()
            if len(selected_buttons) <= 1:
                return
                
            # Find the bottommost button's bottom edge position (highest y value in scene coordinates)
            bottom_edge = float('-inf')
            for button in selected_buttons:
                # Calculate the bottom edge position (center y + half height)
                button_bottom = button.scene_position.y() + (button.height / 2)
                bottom_edge = max(bottom_edge, button_bottom)
            
            # Move all buttons to align their bottom edges
            for button in selected_buttons:
                current_pos = button.scene_position
                # Calculate new center position (bottom_edge - half height)
                new_center_y = bottom_edge - (button.height / 2)
                new_pos = QtCore.QPointF(current_pos.x(), new_center_y)
                button.scene_position = new_pos
            
            if hasattr(main_window, 'batch_update_buttons_to_database'):
                main_window.batch_update_buttons_to_database(selected_buttons)
            canvas.update_button_positions()
            canvas.update()
    #---------------------------------------------------------------------------------------       
    def evenly_space_horizontal(self):
        """Distribute selected buttons evenly along the horizontal axis"""
        canvas = self.parent()
        main_window = canvas.window()
        if canvas and canvas.edit_mode:
            selected_buttons = canvas.get_selected_buttons()
            if len(selected_buttons) <= 2:  # Need at least 3 buttons for spacing to make sense
                return
                
            # Sort buttons by x position
            sorted_buttons = sorted(selected_buttons, key=lambda btn: btn.scene_position.x())
            
            # Get leftmost and rightmost positions
            left_x = sorted_buttons[0].scene_position.x()
            right_x = sorted_buttons[-1].scene_position.x()
            
            # Calculate spacing
            total_width = right_x - left_x
            spacing = total_width / (len(sorted_buttons) - 1) if len(sorted_buttons) > 1 else 0
            
            # Skip first and last buttons (they define the range)
            for i, button in enumerate(sorted_buttons[1:-1], 1):
                # Calculate new x position
                new_x = left_x + (i * spacing)
                current_pos = button.scene_position
                new_pos = QtCore.QPointF(new_x, current_pos.y())
                button.scene_position = new_pos
            
            if hasattr(main_window, 'batch_update_buttons_to_database'):
                main_window.batch_update_buttons_to_database(selected_buttons)
            canvas.update_button_positions()
            canvas.update()
                
    def evenly_space_vertical(self):
        """Distribute selected buttons evenly along the vertical axis"""
        canvas = self.parent()
        main_window = canvas.window()
        if canvas and canvas.edit_mode:
            selected_buttons = canvas.get_selected_buttons()
            if len(selected_buttons) <= 2:  # Need at least 3 buttons for spacing to make sense
                return
                
            main_window = canvas.window()
            
            # Sort buttons by y position
            sorted_buttons = sorted(selected_buttons, key=lambda btn: btn.scene_position.y())
            
            # Get topmost and bottommost positions
            top_y = sorted_buttons[0].scene_position.y()
            bottom_y = sorted_buttons[-1].scene_position.y()
            
            # Calculate spacing
            total_height = bottom_y - top_y
            spacing = total_height / (len(sorted_buttons) - 1) if len(sorted_buttons) > 1 else 0
            
            # Skip first and last buttons (they define the range)
            for i, button in enumerate(sorted_buttons[1:-1], 1):
                # Calculate new y position
                new_y = top_y + (i * spacing)
                current_pos = button.scene_position
                new_pos = QtCore.QPointF(current_pos.x(), new_y)
                button.scene_position = new_pos
            
            if hasattr(main_window, 'batch_update_buttons_to_database'):
                main_window.batch_update_buttons_to_database(selected_buttons)
            canvas.update_button_positions()
            canvas.update()
    
    def _apply_axis_constraint(self, scene_delta):
        """
        Apply axis constraint for shift-drag movement.
        Determines the dominant movement axis and constrains to that axis only.
        
        Args:
            scene_delta (QPointF): The original movement delta
            
        Returns:
            QPointF: The constrained movement delta
        """
        # Determine which axis has the larger movement
        abs_x = abs(scene_delta.x())
        abs_y = abs(scene_delta.y())
        
        # Set a minimum threshold to avoid jittery behavior
        threshold = 2.0  # Minimum movement before axis is determined
        
        if abs_x < threshold and abs_y < threshold:
            # Movement too small, don't constrain yet
            return scene_delta
        
        # Constrain to the axis with larger movement
        if abs_x >= abs_y:
            # Horizontal movement is dominant - constrain to X axis
            return QtCore.QPointF(scene_delta.x(), 0)
        else:
            # Vertical movement is dominant - constrain to Y axis
            return QtCore.QPointF(0, scene_delta.y())
    #---------------------------------------------------------------------------------------
    def copy_selected_buttons(self):
        canvas = self.parent()
        if canvas and canvas.edit_mode:
            selected_buttons = canvas.get_selected_buttons()
            if selected_buttons:
                ButtonClipboard.instance().copy_buttons(selected_buttons)

    def paste_attributes(self, paste_type='all'):
        """Enhanced paste method that handles different types of paste operations - TRULY FIXED VERSION"""
        canvas = self.parent()
        main_window = canvas.window()
        if canvas and canvas.edit_mode:
            attributes = ButtonClipboard.instance().get_last_attributes()
            if attributes:
                selected_buttons = canvas.get_selected_buttons()
                
                if not selected_buttons:
                    return
                
                # Get current tab data once
                current_tab = main_window.tab_system.current_tab
                tab_data = DM.PickerDataManager.get_tab_data(current_tab)
                updated_buttons = []
                
                # Process all buttons individually
                for button in selected_buttons:
                    if paste_type == 'all':
                        # Paste everything
                        button.label = attributes['label']
                        button.color = attributes['color']
                        button.opacity = attributes['opacity']
                        button.width = attributes['width']
                        button.height = attributes['height']
                        button.radius = attributes['radius'].copy()
                        button.assigned_objects = attributes.get('assigned_objects', []).copy()
                        button.mode = attributes.get('mode', 'select')
                        button.script_data = attributes.get('script_data', {}).copy()
                        button.shape_type = attributes.get('shape_type', 'rounded_rect')
                        button.svg_path_data = attributes.get('svg_path_data', None)
                        button.svg_file_path = attributes.get('svg_file_path', None) 

                        # Handle pose data if available
                        if 'pose_data' in attributes:
                            button.pose_data = attributes['pose_data'].copy()
                        if 'thumbnail_path' in attributes:
                            button.thumbnail_path = attributes.get('thumbnail_path', '')
                            if attributes.get('thumbnail_path') and os.path.exists(attributes['thumbnail_path']):
                                button.thumbnail_pixmap = QtGui.QPixmap(attributes['thumbnail_path'])
                                
                    elif paste_type == 'dimension':
                        # Paste only dimensions
                        button.width = attributes['width']
                        button.height = attributes['height']
                        button.radius = attributes['radius'].copy()
                        
                    elif paste_type == 'function':
                        # Paste only functionality
                        button.assigned_objects = attributes.get('assigned_objects', []).copy()
                        button.mode = attributes.get('mode', 'select')
                        button.script_data = attributes.get('script_data', {}).copy()
                        
                        if 'pose_data' in attributes:
                            button.pose_data = attributes['pose_data'].copy()
                        if 'thumbnail_path' in attributes:
                            button.thumbnail_path = attributes.get('thumbnail_path', '')
                            if attributes.get('thumbnail_path') and os.path.exists(attributes['thumbnail_path']):
                                button.thumbnail_pixmap = QtGui.QPixmap(attributes['thumbnail_path'])
                                
                    elif paste_type == 'text':
                        # Paste only the label text
                        button.label = attributes['label']
                    
                    # Clear cached pixmaps to force regeneration
                    button.text_pixmap = None
                    button.pose_pixmap = None
                    button.last_zoom_factor = 0
                    button.last_size = None
                    
                    # Update the button visually
                    button.update()
                    button.update_tooltip()

                if hasattr(main_window, 'batch_update_buttons_to_database'):
                    main_window.batch_update_buttons_to_database(selected_buttons)
                canvas.update_button_positions()
                canvas.update()
    #---------------------------------------------------------------------------------------
    def set_script_data(self, data):
        self.script_data = data
        self.changed.emit(self)
        self._tooltip_needs_update = True
        #self.update_tooltip()
    #---------------------------------------------------------------------------------------    
    # POSE MANAGEMENT
    #---------------------------------------------------------------------------------------
    def add_pose(self):
        """Add current pose of selected objects to the pose data"""
        active_obj = TF.active_object()
        
        if active_obj.type == 'ARMATURE':
            self._add_armature_pose()
        else:
            self._add_object_pose()

    def _add_armature_pose(self):
        """Handle pose addition for armature objects (bone route) with namespace priority"""
        selected_bones = TF.selected_bones()
        
        if not selected_bones:
            self._show_no_selection_dialog("Please select bones in Blender before adding a pose.")
            return
        
        self._update_assigned_bones_with_namespace(selected_bones)
        pose_data = self._capture_armature_pose_data()
        
        if pose_data:
            self._save_pose_data(pose_data)
            self._show_success_dialog()
        else:
            self._show_no_data_dialog()

    def _add_object_pose(self):
        """Handle pose addition for regular objects (object route)"""
        selected_objects = TF.selected_objects()
        
        if not selected_objects:
            self._show_no_selection_dialog("Please select objects in Blender before adding a pose.")
            return
        
        self._update_assigned_objects(selected_objects)
        pose_data = self._capture_object_pose_data()
        
        if pose_data:
            self._save_pose_data(pose_data)
            self._show_success_dialog()
        else:
            self._show_no_data_dialog()

    def _show_no_selection_dialog(self, message):
        """Show dialog when no objects/bones are selected"""
        dialog = CD.CustomDialog(self, title="No Selection", size=(200, 80), info_box=True)
        message_label = QtWidgets.QLabel(message)
        message_label.setWordWrap(True)
        dialog.add_widget(message_label)
        dialog.add_button_box()
        dialog.exec_()

    def _update_assigned_bones_with_namespace(self, selected_bones):
        """Update assigned bones with proper namespace handling - ENHANCED"""
        self.assigned_objects = []
        
        # Get current namespace from main window
        current_namespace = self._get_current_namespace_from_window()
        
        # Get the active armature name as fallback
        active_armature = TF.active_object()
        fallback_armature = active_armature.name if active_armature and active_armature.type == 'ARMATURE' else ""
        
        # Determine target armature for storage
        target_armature = current_namespace if current_namespace and current_namespace != 'None' else fallback_armature
        
        #print(f"Storing bones with target armature: '{target_armature}' (namespace: '{current_namespace}', active: '{fallback_armature}')")
        
        for bone_name in selected_bones:
            try:
                self.assigned_objects.append({
                    'name': bone_name,
                    'is_bone': True,
                    'armature': target_armature,
                    'source_armature': fallback_armature  # Keep track of where it came from
                })
                #print(f"Assigned bone '{bone_name}' to armature '{target_armature}'")
            except Exception as e:
                print(f"Error assigning bone {bone_name}: {e}")
                continue

    def _update_assigned_objects(self, selected_objects):
        """Update the assigned objects list with selected objects"""
        self.assigned_objects = []
        for obj in selected_objects:
            try:
                self.assigned_objects.append({
                    'name': obj,
                    'is_bone': False
                })
            except Exception:
                continue

    def _capture_armature_pose_data(self):
        """Capture pose data for selected bones in armature - NAMESPACE AWARE VERSION"""
        pose_data = {}
        active_armature = TF.active_object()
        
        if not active_armature or active_armature.type != 'ARMATURE' or not active_armature.pose:
            return pose_data
        
        try:
            # Get current namespace to determine storage strategy
            current_namespace = self._get_current_namespace_from_window()
            
            # Use a generic key for the armature data instead of the specific name
            # This allows namespace switching during application
            storage_key = current_namespace if current_namespace else active_armature.name
            
            bones_data = {}
            
            # Only capture data for selected bones
            for obj_data in self.assigned_objects:
                if obj_data['is_bone']:
                    bone_name = obj_data['name']
                    if bone_name in active_armature.pose.bones:
                        bone = active_armature.pose.bones[bone_name]
                        bone_data = self._get_bone_attributes(bone)
                        if bone_data:
                            bones_data[bone_name] = bone_data
            
            if bones_data:
                # Store with metadata about the source armature
                pose_data[storage_key] = {
                    'pose_bones': bones_data,
                    'source_armature': active_armature.name,  # Keep track of original
                    'is_armature_pose': True
                }
                #print(f"Stored pose for {len(bones_data)} bones from armature '{active_armature.name}' with key '{storage_key}'")
                
        except Exception as e:
            print(f"Error capturing armature pose: {str(e)}")
        
        return pose_data

    def _capture_object_pose_data(self):
        """Capture pose data for selected objects"""
        pose_data = {}
        
        for obj_data in self.assigned_objects:
            if not obj_data['is_bone']:
                try:
                    obj_name = obj_data['name']
                    if obj_name not in bpy.data.objects:
                        continue
                        
                    obj = bpy.data.objects[obj_name]
                    attr_values = self._get_object_attributes(obj)
                    
                    if attr_values:
                        pose_data[obj.name] = attr_values
                        
                except Exception as e:
                    print(f"Error capturing pose for {obj_name}: {str(e)}")
                    continue
        
        return pose_data

    def _get_object_attributes(self, obj):
        """Get all animatable attributes for a regular object"""
        attr_values = {}
        
        # Basic transform properties
        attr_values['location'] = list(obj.location)
        attr_values['scale'] = list(obj.scale)
        
        # Rotation based on mode
        self._add_rotation_data(obj, attr_values)
        
        # Custom properties
        self._add_custom_properties(obj, attr_values)
        
        return attr_values

    def _get_bone_attributes(self, bone):
        """Get all attributes for a pose bone"""
        bone_data = {
            'location': list(bone.location),
            'scale': list(bone.scale)
        }
        
        # Bone rotation based on mode
        self._add_bone_rotation_data(bone, bone_data)
        
        # Custom properties on bones
        self._add_custom_properties(bone, bone_data)
        
        return bone_data

    def _add_rotation_data(self, obj, attr_values):
        """Add rotation data based on object's rotation mode"""
        rotation_modes = {
            'QUATERNION': ('rotation_quaternion', obj.rotation_quaternion),
            'AXIS_ANGLE': ('rotation_axis_angle', obj.rotation_axis_angle)
        }
        
        if obj.rotation_mode in rotation_modes:
            key, value = rotation_modes[obj.rotation_mode]
            attr_values[key] = list(value)
        else:  # Euler rotations
            attr_values['rotation_euler'] = list(obj.rotation_euler)

    def _add_bone_rotation_data(self, bone, bone_data):
        """Add rotation data for a pose bone"""
        rotation_modes = {
            'QUATERNION': ('rotation_quaternion', bone.rotation_quaternion),
            'AXIS_ANGLE': ('rotation_axis_angle', bone.rotation_axis_angle)
        }
        
        if bone.rotation_mode in rotation_modes:
            key, value = rotation_modes[bone.rotation_mode]
            bone_data[key] = list(value)
        else:  # Euler rotations
            bone_data['rotation_euler'] = list(bone.rotation_euler)

    def _add_custom_properties(self, obj, attr_values):
        """Add custom properties to attribute values"""
        import json
        with bpy.context.temp_override(window=bpy.context.window_manager.windows[0]):
            for key in obj.keys():
                # Skip private properties and known problematic types
                if key.startswith("_") or key == "rigify_parameters":
                    continue
                    
                try:
                    # Get the property value
                    value = obj[key]
                    
                    # Check if the value is JSON serializable
                    try:
                        # Test if the value can be serialized to JSON
                        json.dumps(value)
                        # If successful, add it to attr_values
                        attr_values[key] = value
                        #print(f"Custom property added: {key} = {value}")
                    except TypeError:
                        # Skip non-serializable types instead of trying to convert them
                        print(f"Skipping non-serializable property: {key} (type: {type(value).__name__})")
                except Exception as e:
                    print(f"Failed to access custom property {key}: {e}")
                    continue

    def _save_pose_data(self, pose_data):
        """Save the captured pose data"""
        self.pose_data = {"default": pose_data}
        #self.update_tooltip()
        self._tooltip_needs_update = True
        self.changed.emit(self)

    def _show_success_dialog(self):
        """Show success dialog when pose is added"""
        dialog = CD.CustomDialog(self, title="Pose Added", size=(200, 80), info_box=True)
        message_label = QtWidgets.QLabel("Pose has been added successfully.")
        message_label.setWordWrap(True)
        dialog.add_widget(message_label)
        dialog.add_button_box()
        # Commented out to prevent blocking: dialog.exec_()

    def _show_no_data_dialog(self):
        """Show dialog when no attribute data could be captured"""
        dialog = CD.CustomDialog(self, title="No Data", size=(200, 80), info_box=True)
        message_label = QtWidgets.QLabel("Could not capture any attribute data for the selected objects.")
        message_label.setWordWrap(True)
        dialog.add_widget(message_label)
        dialog.add_button_box()
        dialog.exec_()
    
    def remove_pose(self):
        """Remove the pose from the pose data and clear assigned objects"""
        # Clear the pose data
        self.pose_data = {}
        
        # Also clear assigned objects
        self.assigned_objects = []
        
        # Update the tooltip to reflect the changes
        #self.update_tooltip()
        self._tooltip_needs_update = True
        
        # Emit the changed signal
        self.changed.emit(self)
        
    def remove_pose_for_selected_buttons(self):
        """Remove the pose data for selected buttons"""
        for button in self.parent().get_selected_buttons():
            if not button.pose_data:
                # Use custom dialog instead of QMessageBox
                dialog = CD.CustomDialog(self, title="No Pose", size=(200, 80), info_box=True)
                message_label = QtWidgets.QLabel("There is no pose to remove.")
                message_label.setWordWrap(True)
                dialog.add_widget(message_label)
                dialog.add_button_box()
                dialog.exec_()
                return
            button.remove_pose()
        
        dialog = CD.CustomDialog(self, title="Pose Removed", size=(200, 80), info_box=True)
        message_label = QtWidgets.QLabel("Pose and assigned objects have been removed.")
        message_label.setWordWrap(True)
        dialog.add_widget(message_label)
        dialog.add_button_box()
        dialog.exec_()
    #---------------------------------------------------------------------------------------
    # THUMBNAIL MANAGEMENT
    #---------------------------------------------------------------------------------------
    def select_thumbnail(self):
        """Add a thumbnail image to selected pose buttons"""
        # Get the parent canvas and selected buttons
        canvas = self.parent()
        if not canvas:
            return
            
        selected_buttons = canvas.get_selected_buttons()
        # Filter to only include pose mode buttons
        pose_buttons = [button for button in selected_buttons if button.mode == 'pose']
        
        if not pose_buttons:
            # If no pose buttons are selected, just use this button if it's in pose mode
            if self.mode == 'pose':
                pose_buttons = [self]
            else:
                dialog = CD.CustomDialog(self, title="No Pose Buttons", size=(250, 100), info_box=True)
                message_label = QtWidgets.QLabel("No pose buttons selected. Please select at least one button in pose mode.")
                message_label.setWordWrap(True)
                dialog.add_widget(message_label)
                dialog.add_button_box()
                dialog.exec_()
                return
        
        # Open file dialog to select an image
        # Get the thumbnail directory from data management
        data = DM.PickerDataManager.get_data()
        thumbnail_dir = data.get('thumbnail_directory', '')
        
        # If no thumbnail directory is set, use a dedicated directory in the ft_anim_picker environment
        if not thumbnail_dir:
            # Create a thumbnails directory in the ft_anim_picker environment
            script_dir = os.path.dirname(os.path.abspath(__file__))
            thumbnail_dir = os.path.join(script_dir, 'picker_thumbnails')
        
        # Make sure the directory exists
        if not os.path.exists(thumbnail_dir):
            try:
                os.makedirs(thumbnail_dir)
            except:
                thumbnail_dir = tempfile.gettempdir()

        file_path, _ = QtWidgets.QFileDialog.getOpenFileName(
            self, "Select Thumbnail Image", thumbnail_dir,
            "Image Files (*.png *.jpg *.jpeg *.bmp *.gif)"
        )
        
        if file_path:
            # Load the image into a pixmap to verify it's valid
            test_pixmap = QtGui.QPixmap(file_path)
            if test_pixmap.isNull():
                dialog = CD.CustomDialog(self, title="Error", size=(200, 80), info_box=True)
                message_label = QtWidgets.QLabel("Failed to load the selected image.")
                message_label.setWordWrap(True)
                dialog.add_widget(message_label)
                dialog.add_button_box()
                dialog.exec_()
                return
            
            # Apply the thumbnail to all selected pose buttons
            for button in pose_buttons:
                # Store the image path
                button.thumbnail_path = file_path
                
                # Load the image into a pixmap
                button.thumbnail_pixmap = QtGui.QPixmap(file_path)
                
                # Force regeneration of the pose_pixmap by invalidating cache parameters
                button.pose_pixmap = None
                button.last_zoom_factor = 0
                button.last_size = None
                
                # Update the button
                button.update()
                button.update_tooltip()
                button.changed.emit(button)
    
    def add_thumbnail(self):
        """Take a screenshot and use it as a thumbnail"""
        import os
        
        # Get selected pose buttons
        pose_buttons = self._get_selected_pose_buttons()
        if not pose_buttons:
            return
        
        # Get thumbnail directory and create unique filename
        thumbnail_dir = self._get_thumbnail_directory()
        thumbnail_path = self._generate_unique_thumbnail_path(thumbnail_dir)
        
        try:
            # Capture full screen
            cropped_pixmap = self._capture_screen_and_crop(thumbnail_path)
            
            # Apply thumbnail to all selected pose buttons
            self._apply_thumbnail_to_buttons(pose_buttons, thumbnail_path, cropped_pixmap)
            
        except Exception as e:
            self._show_thumbnail_error(str(e))

    def _capture_screen_and_crop(self, output_path):
        """Capture screen using Qt's grabWindow and crop to square"""
        # Get the top-level window
        top_window = self.window()
        
        # Remember window state
        was_visible = top_window.isVisible()
        
        try:
            # Hide the window temporarily
            top_window.hide()
            
            # Small delay to ensure window is hidden
            QtCore.QCoreApplication.processEvents()
            
            # Get the primary screen
            screen = QtGui.QGuiApplication.primaryScreen()
            
            # Check if we have a window handle for better screen detection
            window = self.windowHandle()
            if window:
                screen = window.screen()
            
            if not screen:
                raise Exception("No screen available for capture")
            
            # Capture the entire screen
            original_pixmap = screen.grabWindow(0)
            
            if original_pixmap.isNull():
                raise Exception("Failed to capture screen")
            
            # Convert to QImage for processing
            original_image = original_pixmap.toImage()
            
            # Crop to square (center crop)
            cropped_image = self._crop_to_square(original_image)
            
            # Save as JPG
            if not cropped_image.save(output_path, 'JPG', 95):
                raise Exception("Failed to save thumbnail")
            
            # Convert back to QPixmap for button display
            return QtGui.QPixmap.fromImage(cropped_image)
        
        finally:
            # Restore window visibility
            if was_visible:
                top_window.show()
            QtCore.QCoreApplication.processEvents()
            
    def _crop_to_square(self, qimage, exclude_bottom_percent=14, exclude_top_percent=7):
        """
        Crop QImage to square dimensions, avoiding taskbars and UI elements
        
        Args:
            qimage: The image to crop
            exclude_bottom_percent: Percentage of screen height to exclude from bottom (taskbar area)
            exclude_top_percent: Percentage of screen height to exclude from top (menu bars)
        """
        width = qimage.width()
        height = qimage.height()
        
        # Calculate available area after excluding UI regions
        exclude_top_pixels = int(height * exclude_top_percent / 100)
        exclude_bottom_pixels = int(height * exclude_bottom_percent / 100)
        available_height = height - exclude_top_pixels - exclude_bottom_pixels
        
        # Determine crop size based on available area
        crop_size = min(width, available_height)
        
        # If the available area is too small, fall back to using more of the screen
        if crop_size < min(width, height) * 0.5:  # If crop would be less than 50% of smallest dimension
            crop_size = min(width, int(height * 0.8))  # Use 80% of height
            exclude_top_pixels = int(height * 0.1)  # 10% from top
        
        # Calculate crop position
        left = (width - crop_size) // 2  # Center horizontally
        top = exclude_top_pixels + (available_height - crop_size) // 2  # Center in available area
        
        # Ensure we don't go beyond image bounds
        top = max(exclude_top_pixels, min(top, height - crop_size))
        left = max(0, min(left, width - crop_size))
        
        # Crop and return
        return qimage.copy(left, top, crop_size, crop_size)
    
    def _get_selected_pose_buttons(self):
        """Get selected pose buttons or current button if in pose mode"""
        canvas = self.parent()
        if not canvas:
            return []
        
        selected_buttons = canvas.get_selected_buttons()
        pose_buttons = [button for button in selected_buttons if button.mode == 'pose']
        
        if not pose_buttons:
            if self.mode == 'pose':
                pose_buttons = [self]
            else:
                self._show_no_pose_buttons_dialog()
                return []
        
        return pose_buttons

    def _get_thumbnail_directory(self):
        """Get or create the thumbnail directory"""
        # Try to get from data management first
        data = DM.PickerDataManager.get_data()
        thumbnail_dir = data.get('thumbnail_directory', '')
        
        # Fallback to default directory
        if not thumbnail_dir:
            script_dir = os.path.dirname(os.path.abspath(__file__))
            thumbnail_dir = os.path.join(script_dir, 'picker_thumbnails')
        
        # Create directory if it doesn't exist
        if not os.path.exists(thumbnail_dir):
            try:
                os.makedirs(thumbnail_dir)
            except Exception:
                import tempfile
                thumbnail_dir = tempfile.gettempdir()
        
        return thumbnail_dir

    def _generate_unique_thumbnail_path(self, thumbnail_dir):
        """Generate a unique thumbnail filename with sequential numbering"""
        highest_num = 0
        
        if os.path.exists(thumbnail_dir):
            for existing_file in os.listdir(thumbnail_dir):
                if existing_file.startswith('thumbnail_') and existing_file.endswith('.jpg'):
                    try:
                        num_part = existing_file.replace('thumbnail_', '').replace('.jpg', '')
                        if num_part.isdigit():
                            highest_num = max(highest_num, int(num_part))
                    except Exception:
                        continue
        
        next_num = highest_num + 1
        filename = f"thumbnail_{next_num:03d}.jpg"
        return os.path.join(thumbnail_dir, filename)

    def _apply_thumbnail_to_buttons(self, pose_buttons, thumbnail_path, cropped_pixmap):
        """Apply the captured thumbnail to all selected pose buttons"""
        for button in pose_buttons:
            # Store the image path
            button.thumbnail_path = thumbnail_path
            
            # Set the thumbnail pixmap
            button.thumbnail_pixmap = cropped_pixmap
            
            # Clear cached data to force regeneration
            button.pose_pixmap = None
            button.last_zoom_factor = 0
            button.last_size = None
            
            # Update the button
            button.update()
            button.update_tooltip()
            button.changed.emit(button)

    def _show_no_pose_buttons_dialog(self):
        """Show dialog when no pose buttons are selected"""
        dialog = CD.CustomDialog(self, title="No Pose Buttons", size=(250, 100), info_box=True)
        message_label = QtWidgets.QLabel("No pose buttons selected. Please select at least one button in pose mode.")
        message_label.setWordWrap(True)
        dialog.add_widget(message_label)
        dialog.add_button_box()
        dialog.exec_()

    def _show_thumbnail_error(self, error_message):
        """Show error dialog for thumbnail capture failures"""
        dialog = CD.CustomDialog(self, title="Error", size=(250, 100), info_box=True)
        message_label = QtWidgets.QLabel(f"Failed to capture viewport: {error_message}")
        message_label.setWordWrap(True)
        dialog.add_widget(message_label)
        dialog.add_button_box()
        dialog.exec_()

    def update_thumbnail(self):
        """Update existing thumbnail by overwriting the current thumbnail file"""
        # Get selected pose buttons
        pose_buttons = self._get_selected_pose_buttons()
        if not pose_buttons:
            return
        
        # Check if buttons have existing thumbnails
        buttons_with_thumbnails = [btn for btn in pose_buttons if btn.thumbnail_path and os.path.exists(btn.thumbnail_path)]
        
        if not buttons_with_thumbnails:
            self._show_no_existing_thumbnail_dialog()
            return
        
        try:
            # Use the first button's thumbnail path as the target
            target_thumbnail_path = buttons_with_thumbnails[0].thumbnail_path
            
            # Capture screen and overwrite existing thumbnail
            cropped_pixmap = self._capture_screen_and_crop(target_thumbnail_path)
            
            # Apply updated thumbnail to all buttons that had the same thumbnail
            self._update_existing_thumbnail(buttons_with_thumbnails, target_thumbnail_path, cropped_pixmap)
            
        except Exception as e:
            self._show_thumbnail_error(str(e))

    def _update_existing_thumbnail(self, buttons_with_thumbnails, thumbnail_path, cropped_pixmap):
        """Update existing thumbnail on buttons"""
        for button in buttons_with_thumbnails:
            # Update the thumbnail pixmap
            button.thumbnail_pixmap = cropped_pixmap
            
            # Clear cached data to force regeneration
            button.pose_pixmap = None
            button.last_zoom_factor = 0
            button.last_size = None
            
            # Update the button
            button.update()
            button.update_tooltip()
            button.changed.emit(button)

    def _show_no_existing_thumbnail_dialog(self):
        """Show dialog when no existing thumbnails are found"""
        dialog = CD.CustomDialog(self, title="No Existing Thumbnail", size=(250, 100), info_box=True)
        message_label = QtWidgets.QLabel("No existing thumbnails found to update. Please add a thumbnail first using 'Add Thumbnail'.")
        message_label.setWordWrap(True)
        dialog.add_widget(message_label)
        dialog.add_button_box()
        dialog.exec_()

    def add_thumbnail_with_delay(self, delay_seconds=0):
        """Add thumbnail with optional delay (useful for hiding UI first)"""
        if delay_seconds > 0:
            QtWidgets.QApplication.beep()  # Audio cue
            QtCore.QTimer.singleShot(delay_seconds * 1000, self.add_thumbnail)
        else:
            self.add_thumbnail()

    def update_thumbnail_with_delay(self, delay_seconds=0):
        """Update thumbnail with optional delay (useful for hiding UI first)"""
        if delay_seconds > 0:
            QtWidgets.QApplication.beep()  # Audio cue
            QtCore.QTimer.singleShot(delay_seconds * 1000, self.update_thumbnail)
        else:
            self.update_thumbnail()
    
    def remove_thumbnail(self):
        """Remove the thumbnail image from selected pose buttons"""
        # Get the parent canvas and selected buttons
        canvas = self.parent()
        if not canvas:
            return
            
        selected_buttons = canvas.get_selected_buttons()
        # Filter to only include pose mode buttons with thumbnails
        pose_buttons_with_thumbnails = [button for button in selected_buttons 
                                      if button.mode == 'pose' and button.thumbnail_path]
        
        if not pose_buttons_with_thumbnails:
            # If no pose buttons with thumbnails are selected, just use this button if applicable
            if self.mode == 'pose' and self.thumbnail_path:
                pose_buttons_with_thumbnails = [self]
            else:
                dialog = CD.CustomDialog(self, title="No Thumbnails", size=(250, 100), info_box=True)
                message_label = QtWidgets.QLabel("No pose buttons with thumbnails selected.")
                message_label.setWordWrap(True)
                dialog.add_widget(message_label)
                dialog.add_button_box()
                dialog.exec_()
                return
        
        # Remove thumbnails from all selected pose buttons
        for button in pose_buttons_with_thumbnails:
            # Clear the thumbnail data
            button.thumbnail_path = ''
            button.thumbnail_pixmap = None
            
            # Force regeneration of the pose_pixmap by invalidating cache parameters
            button.pose_pixmap = None
            button.last_zoom_factor = 0
            button.last_size = None
            
            # Update the button
            button.update()
            button.changed.emit(button)
    #---------------------------------------------------------------------------------------
    def repath_thumbnails_for_selected_buttons(self):
        """Repath thumbnails for selected pose buttons by choosing a new directory"""
        # Get the parent canvas and selected buttons
        canvas = self.parent()
        main_window = canvas.window() if canvas else None
        if not canvas:
            return
            
        selected_buttons = canvas.get_selected_buttons()
        # Filter to only include pose mode buttons with thumbnails
        pose_buttons_with_thumbnails = [button for button in selected_buttons 
                                    if button.mode == 'pose' and button.thumbnail_path]
        
        if not pose_buttons_with_thumbnails:
            # If no pose buttons with thumbnails are selected, just use this button if applicable
            if self.mode == 'pose' and self.thumbnail_path:
                pose_buttons_with_thumbnails = [self]
            else:
                dialog = CD.CustomDialog(self, title="No Thumbnails", size=(250, 100), info_box=True)
                message_label = QtWidgets.QLabel("No pose buttons with thumbnails selected.")
                message_label.setWordWrap(True)
                dialog.add_widget(message_label)
                dialog.add_button_box()
                dialog.exec_()
                return
        
        # Show directory selection dialog
        from . import data_management as DM
        data = DM.PickerDataManager.get_data()
        initial_dir = data.get('thumbnail_directory', '')
        
        # If no initial directory, use the directory of the first button's thumbnail
        if not initial_dir and pose_buttons_with_thumbnails:
            first_thumbnail = pose_buttons_with_thumbnails[0].thumbnail_path
            if first_thumbnail and os.path.exists(first_thumbnail):
                initial_dir = os.path.dirname(first_thumbnail)
            else:
                initial_dir = os.path.expanduser("~")
        
        new_directory = QtWidgets.QFileDialog.getExistingDirectory(
            self, "Select New Thumbnail Directory (will search subdirectories)", initial_dir
        )
        
        if not new_directory:
            return  # User cancelled
        
        # Show progress dialog for file scanning
        progress_dialog = QtWidgets.QProgressDialog(
            "Scanning directories for thumbnails...", "Cancel", 0, 100, self
        )
        progress_dialog.setWindowModality(QtCore.Qt.WindowModal)
        progress_dialog.setAutoClose(False)
        progress_dialog.setAutoReset(False)
        progress_dialog.show()
        
        try:
            # Analyze thumbnails and prepare repath data
            repath_results = []
            successful_repaths = []
            failed_repaths = []
            
            total_buttons = len(pose_buttons_with_thumbnails)
            
            for i, button in enumerate(pose_buttons_with_thumbnails):
                if progress_dialog.wasCanceled():
                    return
                
                progress_dialog.setValue(int((i / total_buttons) * 100))
                progress_dialog.setLabelText(f"Searching for: {os.path.basename(button.thumbnail_path)}")
                QtWidgets.QApplication.processEvents()
                
                old_path = button.thumbnail_path
                filename = os.path.basename(old_path)
                
                # Search for the file recursively
                found_files = self._find_thumbnail_files_recursive(new_directory, filename)
                
                if found_files:
                    # File(s) found - use the best match
                    best_match = found_files[0]  # Already sorted by relevance
                    repath_results.append({
                        'button': button,
                        'old_path': old_path,
                        'new_path': best_match['path'],
                        'filename': filename,
                        'status': 'found',
                        'all_matches': found_files,
                        'relative_path': os.path.relpath(best_match['path'], new_directory)
                    })
                else:
                    # Try to find similar files
                    similar_files = self._find_similar_thumbnail_files_recursive(new_directory, filename)
                    repath_results.append({
                        'button': button,
                        'old_path': old_path,
                        'new_path': '',
                        'filename': filename,
                        'status': 'missing',
                        'similar_files': similar_files
                    })
            
            progress_dialog.setValue(100)
            progress_dialog.close()
            
        except Exception as e:
            progress_dialog.close()
            error_dialog = CD.CustomDialog(self, title="Error", size=(300, 150), info_box=True)
            error_label = QtWidgets.QLabel(f"Error scanning directories: {str(e)}")
            error_label.setWordWrap(True)
            error_dialog.add_widget(error_label)
            error_dialog.add_button_box()
            error_dialog.exec_()
            return
        
        # Show repath preview dialog
        if self._show_repath_preview_dialog(repath_results, new_directory):
            # User confirmed, apply the repaths
            for result in repath_results:
                if result['status'] == 'found' or (result['status'] == 'manual' and result.get('selected_path')):
                    button = result['button']
                    final_path = result.get('selected_path', result['new_path'])
                    
                    try:
                        # Update the button's thumbnail path
                        button.thumbnail_path = final_path
                        
                        # Reload the thumbnail pixmap
                        button.thumbnail_pixmap = QtGui.QPixmap(final_path)
                        
                        # Force regeneration of the pose_pixmap
                        button.pose_pixmap = None
                        button.last_zoom_factor = 0
                        button.last_size = None
                        
                        # Update the button
                        button.update()
                        button.update_tooltip()
                        button.changed.emit(button)
                        
                        successful_repaths.append({
                            'button': button.label,
                            'filename': os.path.basename(final_path)
                        })
                        
                    except Exception as e:
                        failed_repaths.append({
                            'button': button.label,
                            'filename': result['filename'],
                            'error': str(e)
                        })
            
            # Show results
            self._show_repath_results_dialog(successful_repaths, failed_repaths)
            
            # Update thumbnail directory preference
            DM.PickerDataManager.set_thumbnail_directory(new_directory)
            # Update buttons in database
            if hasattr(main_window, 'batch_update_buttons_to_database'):
                main_window.batch_update_buttons_to_database(selected_buttons)
            canvas.update()

    def _find_thumbnail_files_recursive(self, root_directory, target_filename, max_depth=10):
        """Find files recursively that match the target filename exactly"""
        if not os.path.exists(root_directory):
            return []
        
        found_files = []
        valid_extensions = ['.png', '.jpg', '.jpeg', '.bmp', '.gif', '.tiff', '.webp']
        
        def scan_directory(directory, current_depth=0):
            if current_depth > max_depth:
                return
            
            try:
                for item in os.listdir(directory):
                    item_path = os.path.join(directory, item)
                    
                    if os.path.isfile(item_path):
                        # Check for exact filename match
                        if item.lower() == target_filename.lower():
                            # Verify it's an image file
                            _, ext = os.path.splitext(item)
                            if ext.lower() in valid_extensions:
                                # Calculate priority based on directory depth and name
                                priority = self._calculate_file_priority(item_path, root_directory, target_filename)
                                found_files.append({
                                    'filename': item,
                                    'path': item_path,
                                    'priority': priority,
                                    'depth': current_depth,
                                    'directory': directory
                                })
                    
                    elif os.path.isdir(item_path):
                        # Skip hidden directories and common non-image directories
                        if not item.startswith('.') and item.lower() not in ['__pycache__', 'node_modules', '.git']:
                            scan_directory(item_path, current_depth + 1)
            
            except (PermissionError, OSError) as e:
                # Skip directories we can't access
                pass
        
        scan_directory(root_directory)
        
        # Sort by priority (higher priority first)
        found_files.sort(key=lambda x: x['priority'], reverse=True)
        
        return found_files

    def _find_similar_thumbnail_files_recursive(self, root_directory, target_filename, max_depth=10):
        """Find files recursively that might be similar to the target filename"""
        if not os.path.exists(root_directory):
            return []
        
        similar_files = []
        valid_extensions = ['.png', '.jpg', '.jpeg', '.bmp', '.gif', '.tiff', '.webp']
        
        # Extract base name for comparison
        target_base = os.path.splitext(target_filename)[0]
        
        def scan_directory(directory, current_depth=0):
            if current_depth > max_depth:
                return
            
            try:
                for item in os.listdir(directory):
                    item_path = os.path.join(directory, item)
                    
                    if os.path.isfile(item_path):
                        file_base = os.path.splitext(item)[0]
                        file_ext = os.path.splitext(item)[1].lower()
                        
                        # Only consider image files
                        if file_ext in valid_extensions:
                            # Calculate similarity
                            similarity = self._calculate_filename_similarity(target_base, file_base)
                            
                            if similarity > 0.4:  # Lower threshold for recursive search
                                priority = self._calculate_file_priority(item_path, root_directory, target_filename)
                                similar_files.append({
                                    'filename': item,
                                    'path': item_path,
                                    'similarity': similarity,
                                    'priority': priority,
                                    'depth': current_depth,
                                    'directory': directory
                                })
                    
                    elif os.path.isdir(item_path):
                        # Skip hidden directories and common non-image directories
                        if not item.startswith('.') and item.lower() not in ['__pycache__', 'node_modules', '.git']:
                            scan_directory(item_path, current_depth + 1)
            
            except (PermissionError, OSError) as e:
                # Skip directories we can't access
                pass
        
        scan_directory(root_directory)
        
        # Sort by similarity first, then by priority
        similar_files.sort(key=lambda x: (x['similarity'], x['priority']), reverse=True)
        
        # Return top 10 matches to avoid overwhelming the user
        return similar_files[:10]

    def _calculate_file_priority(self, file_path, root_directory, target_filename):
        """Calculate priority for file selection based on various factors"""
        priority = 0
        
        directory = os.path.dirname(file_path)
        filename = os.path.basename(file_path)
        relative_path = os.path.relpath(directory, root_directory)
        
        # Higher priority for files closer to root
        depth = len(relative_path.split(os.sep)) if relative_path != '.' else 0
        priority += max(0, 10 - depth)  # Max 10 points for depth
        
        # Higher priority for directories with thumbnail-related names
        thumbnail_keywords = ['thumb', 'thumbnail', 'preview', 'icon', 'image', 'pic']
        dir_name_lower = os.path.basename(directory).lower()
        for keyword in thumbnail_keywords:
            if keyword in dir_name_lower:
                priority += 5
                break
        
        # Higher priority for exact filename matches (case insensitive)
        if filename.lower() == target_filename.lower():
            priority += 20
        
        # Slight priority for common image formats
        _, ext = os.path.splitext(filename)
        if ext.lower() in ['.png', '.jpg']:
            priority += 2
        
        # Priority for files that contain original filename parts
        target_base = os.path.splitext(target_filename)[0].lower()
        file_base = os.path.splitext(filename)[0].lower()
        
        if target_base in file_base or file_base in target_base:
            priority += 3
        
        return priority

    def _find_similar_thumbnail_files(self, directory, target_filename):
        """Legacy method - now calls the recursive version with depth 0"""
        return self._find_similar_thumbnail_files_recursive(directory, target_filename, max_depth=0)

    def _calculate_filename_similarity(self, name1, name2):
        """Calculate similarity between two filenames using improved string matching"""
        # Convert to lowercase for comparison
        name1 = name1.lower()
        name2 = name2.lower()
        
        # Exact match
        if name1 == name2:
            return 1.0
        
        # Check if one contains the other
        if name1 in name2 or name2 in name1:
            return 0.9
        
        # Check for common patterns (like thumbnail_001, thumbnail_002, etc.)
        import re
        
        # Remove numbers and compare
        name1_no_numbers = re.sub(r'\d+', '', name1)
        name2_no_numbers = re.sub(r'\d+', '', name2)
        
        if name1_no_numbers == name2_no_numbers and name1_no_numbers:
            return 0.8
        
        # Remove common separators and compare
        name1_clean = re.sub(r'[_\-\s]+', '', name1)
        name2_clean = re.sub(r'[_\-\s]+', '', name2)
        
        if name1_clean == name2_clean:
            return 0.7
        
        # Check for word overlap
        words1 = set(re.split(r'[_\-\s]+', name1))
        words2 = set(re.split(r'[_\-\s]+', name2))
        
        if words1 and words2:
            common_words = words1 & words2
            total_words = words1 | words2
            word_similarity = len(common_words) / len(total_words)
            if word_similarity > 0.5:
                return 0.6 + (word_similarity * 0.2)
        
        # Basic character overlap (Jaccard similarity)
        common_chars = set(name1) & set(name2)
        total_chars = set(name1) | set(name2)
        
        if total_chars:
            char_similarity = len(common_chars) / len(total_chars)
            return char_similarity * 0.6  # Scale down character-based similarity
        
        return 0.0

    def get_thumbnail_status(self):
        """Get the current status of the thumbnail."""
        if not self.thumbnail_path:
            return {
                'status': 'none',
                'message': 'No thumbnail assigned',
                'path': '',
                'exists': False,
                'loaded': False
            }
        
        exists = os.path.exists(self.thumbnail_path)
        loaded = self.thumbnail_pixmap is not None and not self.thumbnail_pixmap.isNull()
        
        if exists and loaded:
            status = 'valid'
            message = 'Thumbnail loaded successfully'
        elif exists and not loaded:
            status = 'load_error'
            message = 'Thumbnail file exists but failed to load'
        elif not exists:
            status = 'missing'
            message = 'Thumbnail file not found'
        else:
            status = 'unknown'
            message = 'Unknown thumbnail status'
        
        return {
            'status': status,
            'message': message,
            'path': self.thumbnail_path,
            'exists': exists,
            'loaded': loaded,
            'filename': os.path.basename(self.thumbnail_path) if self.thumbnail_path else ''
        }

    def _show_repath_preview_dialog(self, repath_results, new_directory):
        """Show a dialog previewing the repath operations with enhanced recursive search results"""
        dialog = CD.CustomDialog(self, title="Repath Thumbnails Preview", size=(600, 500))
        
        # Create main layout
        main_layout = QtWidgets.QVBoxLayout()
        
        # Info label
        info_label = QtWidgets.QLabel(f"Repath thumbnails to: {new_directory}\n(Searched subdirectories recursively)")
        info_label.setWordWrap(True)
        info_label.setStyleSheet("font-weight: bold; color: #00ade6;")
        main_layout.addWidget(info_label)
        
        # Create scroll area for results
        scroll_area = QtWidgets.QScrollArea()
        scroll_widget = QtWidgets.QWidget()
        scroll_layout = QtWidgets.QVBoxLayout(scroll_widget)
        
        # Store widgets for later access
        self._repath_widgets = []
        
        found_count = 0
        missing_count = 0
        
        for result in repath_results:
            # Create frame for each button
            frame = QtWidgets.QFrame()
            frame.setFrameStyle(QtWidgets.QFrame.Box)
            frame_layout = QtWidgets.QVBoxLayout(frame)
            
            # Button info
            button_info = QtWidgets.QLabel(f"Button: {result['button'].label}")
            button_info.setStyleSheet("font-weight: bold;")
            frame_layout.addWidget(button_info)
            
            # Original path
            orig_label = QtWidgets.QLabel(f"Original: {result['filename']}")
            frame_layout.addWidget(orig_label)
            
            if result['status'] == 'found':
                # File found - show success with path
                relative_path = result.get('relative_path', 'Found')
                status_label = QtWidgets.QLabel(f"✓ Found at: {relative_path}")
                status_label.setStyleSheet("color: green;")
                frame_layout.addWidget(status_label)
                
                # Show multiple matches if available
                if 'all_matches' in result and len(result['all_matches']) > 1:
                    matches_label = QtWidgets.QLabel(f"Found {len(result['all_matches'])} matches - using best match")
                    matches_label.setStyleSheet("color: #666; font-size: 10px;")
                    frame_layout.addWidget(matches_label)
                    
                    # Create combo box for alternative matches
                    file_combo = QtWidgets.QComboBox()
                    
                    for i, match in enumerate(result['all_matches']):
                        rel_path = os.path.relpath(match['path'], new_directory)
                        display_text = f"{rel_path}" + (" (Best Match)" if i == 0 else "")
                        file_combo.addItem(display_text, match['path'])
                    
                    frame_layout.addWidget(file_combo)
                    result['combo_widget'] = file_combo
                
                found_count += 1
                
            else:
                # File missing - show options
                status_label = QtWidgets.QLabel("✗ File not found in any subdirectory")
                status_label.setStyleSheet("color: red;")
                frame_layout.addWidget(status_label)
                
                # Show similar files if any
                if result['similar_files']:
                    similar_label = QtWidgets.QLabel(f"Found {len(result['similar_files'])} similar files:")
                    frame_layout.addWidget(similar_label)
                    
                    # Create combo box for file selection
                    file_combo = QtWidgets.QComboBox()
                    file_combo.addItem("-- Select a file --", "")
                    
                    for similar in result['similar_files']:
                        rel_path = os.path.relpath(similar['path'], new_directory)
                        display_text = f"{rel_path} ({similar['similarity']:.0%} match)"
                        file_combo.addItem(display_text, similar['path'])
                    
                    frame_layout.addWidget(file_combo)
                    
                    # Store combo box reference
                    result['combo_widget'] = file_combo
                else:
                    no_similar_label = QtWidgets.QLabel("No similar files found in directory tree")
                    no_similar_label.setStyleSheet("color: #888; font-style: italic;")
                    frame_layout.addWidget(no_similar_label)
                
                missing_count += 1
            
            scroll_layout.addWidget(frame)
            self._repath_widgets.append(result)
        
        scroll_area.setWidget(scroll_widget)
        scroll_area.setWidgetResizable(True)
        main_layout.addWidget(scroll_area)
        
        # Summary
        summary_label = QtWidgets.QLabel(f"Found: {found_count}, Missing: {missing_count}")
        summary_label.setStyleSheet("font-weight: bold;")
        main_layout.addWidget(summary_label)
        
        # Buttons
        button_layout = QtWidgets.QHBoxLayout()
        
        apply_button = QtWidgets.QPushButton("Apply Repath")
        apply_button.setStyleSheet("background-color: #4CAF50; color: white;")
        cancel_button = QtWidgets.QPushButton("Cancel")
        
        button_layout.addWidget(cancel_button)
        button_layout.addWidget(apply_button)
        main_layout.addLayout(button_layout)  
        
        # Use dialog.frame.layout instead of dialog.layout()
        dialog.frame.layout().addLayout(main_layout)
        
        # Connect buttons
        result = [False]  # Use list to allow modification in nested function
        
        def on_apply():
            # Process combo box selections
            for repath_result in repath_results:
                if 'combo_widget' in repath_result:
                    combo = repath_result['combo_widget']
                    selected_path = combo.currentData()
                    if selected_path:
                        repath_result['status'] = 'manual'
                        repath_result['selected_path'] = selected_path
            
            result[0] = True
            dialog.accept()
        
        def on_cancel():
            result[0] = False
            dialog.reject()
        
        apply_button.clicked.connect(on_apply)
        cancel_button.clicked.connect(on_cancel)
        
        dialog.exec_()
        return result[0]

    def _show_repath_results_dialog(self, successful_repaths, failed_repaths):
        """Show results of the repath operation"""
        title = "Repath Results"
        if successful_repaths and not failed_repaths:
            title = "Repath Successful"
        elif failed_repaths and not successful_repaths:
            title = "Repath Failed"
        
        dialog = CD.CustomDialog(self, title=title, size=(400, 300), info_box=True)
        
        # Create layout
        layout = QtWidgets.QVBoxLayout()
        
        if successful_repaths:
            success_label = QtWidgets.QLabel(f"Successfully repathed {len(successful_repaths)} thumbnails:")
            success_label.setStyleSheet("color: green; font-weight: bold;")
            layout.addWidget(success_label)
            
            for item in successful_repaths:
                item_label = QtWidgets.QLabel(f"✓ {item['button']}: {item['filename']}")
                layout.addWidget(item_label)
        
        if failed_repaths:
            if successful_repaths:
                layout.addWidget(QtWidgets.QLabel(""))  # Spacer
            
            failed_label = QtWidgets.QLabel(f"Failed to repath {len(failed_repaths)} thumbnails:")
            failed_label.setStyleSheet("color: red; font-weight: bold;")
            layout.addWidget(failed_label)
            
            for item in failed_repaths:
                item_label = QtWidgets.QLabel(f"✗ {item['button']}: {item['filename']}")
                error_label = QtWidgets.QLabel(f"   Error: {item['error']}")
                error_label.setStyleSheet("color: #888; font-size: 10px;")
                layout.addWidget(item_label)
                layout.addWidget(error_label)
        
        # Use dialog.frame.layout() instead of dialog.layout()
        dialog.frame.layout().addLayout(layout)
        dialog.add_button_box()
        dialog.exec_()
    #---------------------------------------------------------------------------------------
    # POSE APPLICATION
    #---------------------------------------------------------------------------------------
    def apply_pose(self):
        """Apply the stored pose to the assigned objects - OPTIMIZED VERSION WITH FULL NAMESPACE INTEGRATION"""
        if not self._validate_pose_data():
            return
        
        pose_data = self.pose_data.get("default", {})
        current_namespace = self._get_current_namespace_from_window()
        
        # Pre-build optimized object lookup cache with namespace support
        object_cache = self._build_namespace_object_cache(current_namespace)
        
        successfully_posed_objects = []
        posed_bones_by_armature = {}
        
        try:
            for pose_key, attr_values in pose_data.items():
                #print(f"Processing pose entry: '{pose_key}'")
                
                if isinstance(attr_values, dict) and attr_values.get('is_armature_pose', False):
                    # Handle armature pose with namespace priority
                    armature_obj = self._resolve_armature_with_namespace_cached(
                        pose_key, current_namespace, attr_values, object_cache
                    )
                    
                    if armature_obj:
                        successfully_posed_objects.append(armature_obj)
                        
                        # Apply armature-level transforms
                        armature_attrs = {k: v for k, v in attr_values.items() 
                                        if k not in ['pose_bones', 'source_armature', 'is_armature_pose']}
                        if armature_attrs:
                            self._apply_object_attributes(armature_obj, armature_attrs)
                        
                        # Apply bone poses with namespace priority
                        if 'pose_bones' in attr_values:
                            posed_bones = self._apply_bones_with_namespace_priority_cached(
                                armature_obj, attr_values['pose_bones'], current_namespace
                            )
                            if posed_bones:
                                posed_bones_by_armature[armature_obj.name] = posed_bones
                    else:
                        print(f"Warning: Could not find armature for pose key '{pose_key}'")
                else:
                    # Handle regular object pose with namespace priority
                    obj = self._resolve_object_with_namespace_cached(pose_key, current_namespace, object_cache)
                    if obj:
                        successfully_posed_objects.append(obj)
                        self._apply_object_attributes(obj, attr_values)
                    else:
                        print(f"Warning: Could not find object '{pose_key}'")
            
            # Select the posed objects and bones with namespace priority
            self._select_posed_objects_and_bones_with_namespace(successfully_posed_objects, posed_bones_by_armature)
            
        except Exception as e:
            self._handle_apply_error(e, successfully_posed_objects, posed_bones_by_armature)

    def apply_mirrored_pose(self):
        """Apply the stored pose to mirrored objects - OPTIMIZED VERSION WITH NAMESPACE INTEGRATION"""
        if not self._validate_pose_data():
            return
        
        pose_data = self.pose_data.get("default", {})
        current_namespace = self._get_current_namespace_from_window()
        
        # Pre-build optimized caches with namespace support
        object_cache = self._build_namespace_object_cache(current_namespace)
        mirror_cache = self._build_namespace_mirror_cache(object_cache, current_namespace)
        
        successfully_posed_objects = []
        posed_bones_by_armature = {}
        
        try:
            for pose_key, attr_values in pose_data.items():
                #print(f"Processing mirror pose for: '{pose_key}'")
                
                if isinstance(attr_values, dict) and attr_values.get('is_armature_pose', False):
                    # Handle mirrored armature pose with namespace priority
                    armature_obj = self._resolve_armature_with_namespace_cached(
                        pose_key, current_namespace, attr_values, object_cache
                    )
                    
                    if armature_obj:
                        successfully_posed_objects.append(armature_obj)
                        
                        if 'pose_bones' in attr_values:
                            posed_bones = self._apply_mirrored_bones_with_namespace_cached(
                                armature_obj, attr_values['pose_bones'], current_namespace, mirror_cache
                            )
                            if posed_bones:
                                posed_bones_by_armature[armature_obj.name] = posed_bones
                    else:
                        print(f"Warning: Could not find armature for mirror pose key '{pose_key}'")
                else:
                    # Handle mirrored regular object with namespace priority
                    mirrored_obj = self._find_mirrored_object_cached(pose_key, current_namespace, mirror_cache)
                    if mirrored_obj:
                        successfully_posed_objects.append(mirrored_obj)
                        mirrored_attrs = self._mirror_transform_attributes(attr_values)
                        self._apply_object_attributes(mirrored_obj, mirrored_attrs)
                        #print(f"Applied mirrored pose to object '{mirrored_obj.name}'")
                    else:
                        print(f"Warning: Could not find mirrored object for '{pose_key}'")
            
            self._select_posed_objects_and_bones_with_namespace(successfully_posed_objects, posed_bones_by_armature)
            
        except Exception as e:
            self._handle_apply_error(e, successfully_posed_objects, posed_bones_by_armature)

    def _validate_pose_data(self):
        """Validate that pose data exists and is not empty"""
        if not self.pose_data or not self.pose_data.get("default", {}):
            '''self._show_dialog("No Pose" if not self.pose_data else "Empty Pose", 
                            "There is no pose to apply. Please add a pose first." if not self.pose_data 
                            else "Pose does not contain any data.")'''
            print("No pose to apply. Please add a pose first.")
            return False
        return True

    def _get_current_namespace_from_window(self):
        """Get current namespace from main window"""
        main_window = self.window()
        if hasattr(main_window, 'namespace_dropdown'):
            namespace = main_window.namespace_dropdown.currentText()
            return namespace if namespace != 'None' else None
        return None

    def _build_namespace_object_cache(self, current_namespace):
        """Build optimized object lookup cache with comprehensive namespace support"""
        import bpy
        with bpy.context.temp_override(window=bpy.context.window_manager.windows[0]):
            cache = {
                'exact': {},           # Exact name matches
                'namespace_prefix': {},  # Objects with namespace prefixes
                'namespace_suffix': {},  # Objects with namespace suffixes
                'partial': {},         # Partial matches for fallback
                'by_type': {'ARMATURE': [], 'MESH': [], 'OTHER': []}  # Objects by type
            }
            
            separators = ['_', '.']
            
            for obj in bpy.data.objects:
                name = obj.name
                
                # Store exact name
                cache['exact'][name] = obj
                
                # Store by type for faster armature lookups
                obj_type = 'ARMATURE' if obj.type == 'ARMATURE' else ('MESH' if obj.type == 'MESH' else 'OTHER')
                cache['by_type'][obj_type].append(obj)
                
                # If we have a namespace, build namespace-aware cache
                if current_namespace:
                    for sep in separators:
                        # Check for namespace prefix patterns
                        prefix_pattern = f"{current_namespace}{sep}"
                        if name.startswith(prefix_pattern):
                            base_name = name[len(prefix_pattern):]
                            cache['namespace_prefix'][base_name] = obj
                        
                        # Check for namespace suffix patterns
                        suffix_pattern = f"{sep}{current_namespace}"
                        if name.endswith(suffix_pattern):
                            base_name = name[:-len(suffix_pattern)]
                            cache['namespace_suffix'][base_name] = obj
                    
                    # Handle case where object name equals namespace
                    if name == current_namespace:
                        cache['namespace_prefix'][current_namespace] = obj
                        cache['namespace_suffix'][current_namespace] = obj
                
                # Build partial match cache for fallback
                name_parts = name.lower().split('_') + name.lower().split('.')
                for part in name_parts:
                    if part and len(part) > 2:  # Only meaningful parts
                        if part not in cache['partial']:
                            cache['partial'][part] = []
                        cache['partial'][part].append(obj)
            
            return cache

    def _build_namespace_mirror_cache(self, object_cache, current_namespace):
        """Build mirror object lookup cache with namespace awareness"""
        mirror_cache = {}
        
        # Enhanced mirror patterns with both suffix and prefix support
        mirror_patterns = [
            # Suffix patterns
            ('_L', '_R'), ('_l', '_r'), ('.L', '.R'), ('.l', '.r'),
            ('Left', 'Right'), ('left', 'right'),
            ('_Left', '_Right'), ('_left', '_right'),
            ('.Left', '.Right'), ('.left', '.right'),
            # Prefix patterns
            ('L_', 'R_'), ('l_', 'r_'), ('L.', 'R.'), ('l.', 'r.'),
            ('Left_', 'Right_'), ('left_', 'right_'),
            ('Left.', 'Right.'), ('left.', 'right.')
        ]
        
        # Check all exact matches first (highest priority)
        for obj_name, obj in object_cache['exact'].items():
            for left_pat, right_pat in mirror_patterns:
                mirror_name = None
                
                # Check suffix patterns
                if obj_name.endswith(left_pat):
                    mirror_name = obj_name[:-len(left_pat)] + right_pat
                elif obj_name.endswith(right_pat):
                    mirror_name = obj_name[:-len(right_pat)] + left_pat
                # Check prefix patterns
                elif obj_name.startswith(left_pat):
                    mirror_name = right_pat + obj_name[len(left_pat):]
                elif obj_name.startswith(right_pat):
                    mirror_name = left_pat + obj_name[len(right_pat):]
                # Check anywhere in name (fallback)
                elif left_pat in obj_name:
                    mirror_name = obj_name.replace(left_pat, right_pat)
                elif right_pat in obj_name:
                    mirror_name = obj_name.replace(right_pat, left_pat)
                
                if mirror_name and mirror_name in object_cache['exact']:
                    mirror_cache[obj_name] = object_cache['exact'][mirror_name]
                    break
        
        # Also check namespace-aware matches
        if current_namespace:
            for base_name, obj in object_cache['namespace_prefix'].items():
                for left_pat, right_pat in mirror_patterns:
                    if left_pat in base_name:
                        mirror_base = base_name.replace(left_pat, right_pat)
                        if mirror_base in object_cache['namespace_prefix']:
                            mirror_cache[base_name] = object_cache['namespace_prefix'][mirror_base]
                            break
                    elif right_pat in base_name:
                        mirror_base = base_name.replace(right_pat, left_pat)
                        if mirror_base in object_cache['namespace_prefix']:
                            mirror_cache[base_name] = object_cache['namespace_prefix'][mirror_base]
                            break
        
        return mirror_cache

    def _resolve_object_with_namespace_cached(self, obj_name, current_namespace, object_cache):
        """Find object by name using cache, with namespace fallback - ENHANCED VERSION"""
        # Priority 1: Try with current namespace if available
        if current_namespace and current_namespace != 'None':
            # Try namespace prefix cache
            if obj_name in object_cache['namespace_prefix']:
                return object_cache['namespace_prefix'][obj_name]
            
            # Try namespace suffix cache
            if obj_name in object_cache['namespace_suffix']:
                return object_cache['namespace_suffix'][obj_name]
            
            # Try if obj_name equals namespace
            if obj_name == current_namespace and current_namespace in object_cache['exact']:
                return object_cache['exact'][current_namespace]
        
        # Priority 2: Try exact name match
        if obj_name in object_cache['exact']:
            return object_cache['exact'][obj_name]
        
        # Priority 3: Try partial matches as fallback
        obj_name_lower = obj_name.lower()
        for part in [obj_name_lower] + obj_name_lower.split('_') + obj_name_lower.split('.'):
            if part in object_cache['partial']:
                # Return the first match, or prefer one that contains the full name
                for obj in object_cache['partial'][part]:
                    if obj_name.lower() in obj.name.lower() or obj.name.lower() in obj_name.lower():
                        return obj
                # If no good partial match, return first
                return object_cache['partial'][part][0]
        
        print(f"Warning: Object '{obj_name}' not found in scene")
        return None

    def _resolve_armature_with_namespace_cached(self, pose_key, current_namespace, attr_values, object_cache):
        """Resolve which armature to use with namespace priority using cache"""
        source_armature = attr_values.get('source_armature', pose_key)
        
        # Priority 1: Use current namespace if it's an armature
        if current_namespace and current_namespace != 'None':
            if current_namespace in object_cache['exact']:
                obj = object_cache['exact'][current_namespace]
                if obj.type == 'ARMATURE':
                    return obj
        
        # Priority 2-4: Try candidates in order
        candidates = [pose_key, source_armature]
        
        # Add namespace pattern candidates
        if current_namespace and current_namespace != 'None':
            for candidate in [pose_key, source_armature]:
                for sep in ['_', '.']:
                    candidates.extend([
                        f"{current_namespace}{sep}{candidate}",
                        f"{candidate}{sep}{current_namespace}"
                    ])
        
        # Check each candidate
        for candidate in candidates:
            obj = self._resolve_object_with_namespace_cached(candidate, current_namespace, object_cache)
            if obj and obj.type == 'ARMATURE':
                return obj
        
        # Fallback: Check all armatures in cache
        for armature_obj in object_cache['by_type']['ARMATURE']:
            if (pose_key in armature_obj.name or armature_obj.name in pose_key or
                source_armature in armature_obj.name or armature_obj.name in source_armature):
                return armature_obj
        
        print(f"Could not resolve armature for pose key '{pose_key}' with namespace '{current_namespace}'")
        return None

    def _apply_bones_with_namespace_priority_cached(self, target_armature, bones_data, current_namespace):
        """Apply bone poses with namespace priority - cached version"""
        posed_bones = []
        
        for bone_name, bone_attr_values in bones_data.items():
            if bone_name in target_armature.pose.bones:
                bone = target_armature.pose.bones[bone_name]
                try:
                    self._apply_transform_data(bone, bone_attr_values)
                    self._apply_custom_properties(bone, bone_attr_values, exclude_keys=[
                        'location', 'rotation_quaternion', 'rotation_axis_angle', 
                        'rotation_euler', 'scale'
                    ])
                    posed_bones.append(bone)
                except Exception as e:
                    print(f"Error applying pose to bone {bone_name}: {e}")
            else:
                print(f"Warning: Bone '{bone_name}' not found in armature '{target_armature.name}'")
        
        return posed_bones

    def _find_mirrored_object_cached(self, obj_name, current_namespace, mirror_cache):
        """Find the mirrored counterpart using cache"""
        # Try direct cache lookup first
        if obj_name in mirror_cache:
            return mirror_cache[obj_name]
        
        # Try to find original object and check if it has a cached mirror
        # This handles namespace resolution automatically
        import bpy
        with bpy.context.temp_override(window=bpy.context.window_manager.windows[0]):
            for cached_name, mirror_obj in mirror_cache.items():
                if (obj_name in cached_name or cached_name in obj_name or
                    (current_namespace and (
                        cached_name == f"{current_namespace}_{obj_name}" or
                        cached_name == f"{obj_name}_{current_namespace}" or
                        cached_name == f"{current_namespace}.{obj_name}" or
                        cached_name == f"{obj_name}.{current_namespace}"
                    ))):
                    return mirror_obj
        
        return None

    def _apply_mirrored_bones_with_namespace_cached(self, armature_obj, bones_data, current_namespace, mirror_cache):
        """Apply mirrored bone poses efficiently using pre-built cache with namespace support"""
        import bpy
        with bpy.context.temp_override(window=bpy.context.window_manager.windows[0]):
            posed_bones = []
            
            # Build bone mirror cache for this armature (optimized)
            bone_mirror_cache = {}
            for bone in armature_obj.pose.bones:
                mirrored_name = self._get_mirrored_bone_name_enhanced(bone.name)
                if mirrored_name and mirrored_name in armature_obj.pose.bones:
                    bone_mirror_cache[bone.name] = armature_obj.pose.bones[mirrored_name]
            
            # Context management (optimized)
            original_mode = bpy.context.mode
            original_active = bpy.context.view_layer.objects.active
            context_changed = False
            
            try:
                if bpy.context.view_layer.objects.active != armature_obj:
                    bpy.context.view_layer.objects.active = armature_obj
                    context_changed = True
                
                if bpy.context.mode != 'POSE':
                    bpy.ops.object.mode_set(mode='POSE')
                    context_changed = True
                
                for bone_name, bone_attr_values in bones_data.items():
                    mirrored_bone = bone_mirror_cache.get(bone_name)
                    
                    if mirrored_bone:
                        try:
                            mirrored_attrs = self._mirror_transform_attributes(bone_attr_values)
                            self._apply_transform_data(mirrored_bone, mirrored_attrs)
                            self._apply_custom_properties(mirrored_bone, bone_attr_values, exclude_keys=[
                                'location', 'rotation_quaternion', 'rotation_axis_angle', 
                                'rotation_euler', 'scale'
                            ])
                            posed_bones.append(mirrored_bone)
                        except Exception as e:
                            print(f"Error applying mirrored pose to bone {mirrored_bone.name}: {e}")
                    else:
                        print(f"Warning: No mirrored bone found for '{bone_name}' in armature '{armature_obj.name}'")
            
            finally:
                if context_changed:
                    try:
                        if original_active and original_active != bpy.context.view_layer.objects.active:
                            bpy.context.view_layer.objects.active = original_active
                        if original_mode != 'POSE' and bpy.context.mode == 'POSE':
                            if 'EDIT' in original_mode:
                                bpy.ops.object.mode_set(mode='EDIT')
                            else:
                                bpy.ops.object.mode_set(mode='OBJECT')
                    except Exception as e:
                        print(f"Error restoring context: {e}")
            
            return posed_bones

    def _get_mirrored_bone_name_enhanced(self, bone_name):
        """Get mirrored bone name using enhanced patterns with prefix and suffix support"""
        # Enhanced patterns with both suffix and prefix support
        patterns = [
            # Suffix patterns (more common)
            ('_L', '_R'), ('_l', '_r'), ('.L', '.R'), ('.l', '.r'),
            ('Left', 'Right'), ('left', 'right'),
            ('_Left', '_Right'), ('_left', '_right'),
            ('.Left', '.Right'), ('.left', '.right'),
            # Prefix patterns
            ('L_', 'R_'), ('l_', 'r_'), ('L.', 'R.'), ('l.', 'r.'),
            ('Left_', 'Right_'), ('left_', 'right_'),
            ('Left.', 'Right.'), ('left.', 'right.')
        ]
        
        # Try exact suffix/prefix matches first (more precise)
        for left_pat, right_pat in patterns:
            if bone_name.endswith(left_pat):
                return bone_name[:-len(left_pat)] + right_pat
            elif bone_name.endswith(right_pat):
                return bone_name[:-len(right_pat)] + left_pat
            elif bone_name.startswith(left_pat):
                return right_pat + bone_name[len(left_pat):]
            elif bone_name.startswith(right_pat):
                return left_pat + bone_name[len(right_pat):]
        
        # Fallback to anywhere in name (for complex hierarchies)
        for left_pat, right_pat in patterns:
            if left_pat in bone_name:
                return bone_name.replace(left_pat, right_pat)
            elif right_pat in bone_name:
                return bone_name.replace(right_pat, left_pat)
        
        return None

    def _select_posed_objects_and_bones_with_namespace(self, successfully_posed_objects, posed_bones_by_armature, is_mirrored=False):
        """Select the successfully posed objects and their bones in Blender with namespace priority
        
        Args:
            successfully_posed_objects: List of objects that were successfully posed
            posed_bones_by_armature: Dictionary of armature names to posed bones
            is_mirrored: True if this is a mirrored pose application, False for regular poses
        """
        if not successfully_posed_objects:
            return
        
        # Get current namespace
        main_window = self.window()
        current_namespace = None
        if hasattr(main_window, 'namespace_dropdown'):
            current_namespace = main_window.namespace_dropdown.currentText()
            if current_namespace == 'None':
                current_namespace = None
        
        try:
            # Deselect all objects and select posed objects
            bpy.ops.object.select_all(action='DESELECT')
            for obj in successfully_posed_objects:
                obj.select_set(True)
            
            # Handle bone posing and object posing separately
            if posed_bones_by_armature:
                # BONE POSING: Find the target armature (namespace priority)
                target_armature = None
                
                if current_namespace and current_namespace in posed_bones_by_armature:
                    target_armature = current_namespace
                else:
                    # Use the first available armature
                    target_armature = next(iter(posed_bones_by_armature.keys()))
                
                if target_armature and target_armature in bpy.data.objects:
                    active_obj = bpy.data.objects[target_armature]
                    bpy.context.view_layer.objects.active = active_obj
                    
                    with bpy.context.temp_override(window=bpy.context.window_manager.windows[0]):
                        bpy.ops.object.mode_set(mode='POSE')
                        bpy.ops.pose.select_all(action='DESELECT')
                        
                        # Select the posed bones in the target armature
                        if target_armature in posed_bones_by_armature:
                            posed_bones = posed_bones_by_armature[target_armature]
                            for bone in posed_bones:
                                bone.bone.select = True
                            bpy.context.object.data.bones.active = bpy.context.object.data.bones[posed_bones[-1].name]
                        
                        # Stay in pose mode for bone posing
            else:
                # OBJECT POSING: Set the last selected object as active
                # For regular poses: this is the last original object
                # For mirrored poses: this is the last mirrored object
                last_selected_object = successfully_posed_objects[-1]
                bpy.context.view_layer.objects.active = last_selected_object
                                
        except Exception as e:
            print(f"Error selecting posed objects and bones: {e}")
            try:
                bpy.ops.object.mode_set(mode='OBJECT')
            except:
                pass

    def _apply_object_attributes(self, obj, attr_values):
        """Apply transform and custom properties to an object"""
        self._apply_transform_data(obj, attr_values)
        self._apply_custom_properties(obj, attr_values, exclude_keys=[
            'location', 'rotation_quaternion', 'rotation_axis_angle', 
            'rotation_euler', 'scale', 'pose_bones'
        ])

    def _apply_transform_data(self, target, attr_values):
        """Apply location, rotation, and scale data to target object or bone"""
        if 'location' in attr_values and len(attr_values['location']) == 3:
            target.location[:] = attr_values['location']
        
        if hasattr(target, 'rotation_mode'):
            if target.rotation_mode == 'QUATERNION' and 'rotation_quaternion' in attr_values:
                target.rotation_quaternion[:] = attr_values['rotation_quaternion'][:4]
            elif target.rotation_mode == 'AXIS_ANGLE' and 'rotation_axis_angle' in attr_values:
                target.rotation_axis_angle[:] = attr_values['rotation_axis_angle'][:4]
            elif 'rotation_euler' in attr_values:
                target.rotation_euler[:] = attr_values['rotation_euler'][:3]
        elif 'rotation_euler' in attr_values:
            target.rotation_euler[:] = attr_values['rotation_euler'][:3]
        
        if 'scale' in attr_values and len(attr_values['scale']) == 3:
            target.scale[:] = attr_values['scale']

    def _apply_custom_properties(self, target, attr_values, exclude_keys):
        """Apply custom properties to target object or bone"""
        for attr, value in attr_values.items():
            if attr not in exclude_keys:
                try:
                    target[attr] = value
                except Exception as e:
                    target_type = "bone" if hasattr(target, 'bone') else "object"
                    print(f"Error setting {target_type} custom property {attr}: {e}")

    def _mirror_transform_attributes(self, attr_values):
        """Mirror transform attributes for X-axis symmetry"""
        mirrored_attrs = attr_values.copy()
        
        if 'location' in attr_values and len(attr_values['location']) >= 3:
            mirrored_attrs['location'] = [-attr_values['location'][0], 
                                        attr_values['location'][1], 
                                        attr_values['location'][2]]
        
        if 'rotation_euler' in attr_values and len(attr_values['rotation_euler']) >= 3:
            mirrored_attrs['rotation_euler'] = [attr_values['rotation_euler'][0],
                                            -attr_values['rotation_euler'][1],
                                            -attr_values['rotation_euler'][2]]
        
        if 'rotation_quaternion' in attr_values and len(attr_values['rotation_quaternion']) >= 4:
            mirrored_attrs['rotation_quaternion'] = [attr_values['rotation_quaternion'][0],
                                                    attr_values['rotation_quaternion'][1],
                                                    -attr_values['rotation_quaternion'][2],
                                                    -attr_values['rotation_quaternion'][3]]
        
        if 'rotation_axis_angle' in attr_values and len(attr_values['rotation_axis_angle']) >= 4:
            mirrored_attrs['rotation_axis_angle'] = [-attr_values['rotation_axis_angle'][0],
                                                    attr_values['rotation_axis_angle'][1],
                                                    -attr_values['rotation_axis_angle'][2],
                                                    -attr_values['rotation_axis_angle'][3]]
        
        if 'scale' in attr_values:
            mirrored_attrs['scale'] = attr_values['scale']
        
        return mirrored_attrs

    def _handle_apply_error(self, error, successfully_posed_objects, posed_bones_by_armature=None):
        """Handle errors during pose application"""
        import bpy
        self._show_dialog("Error", f"Error applying pose: {error}")
        
        try:
            bpy.ops.ed.undo()
        except:
            pass
        
        if posed_bones_by_armature is None:
            posed_bones_by_armature = {}
        self._select_posed_objects_and_bones_with_namespace(successfully_posed_objects, posed_bones_by_armature)

    def _show_dialog(self, title, message):
        """Show a generic dialog with title and message"""
        dialog = CD.CustomDialog(self, title=title, size=(250, 100), info_box=True)
        message_label = QtWidgets.QLabel(message)
        message_label.setWordWrap(True)
        dialog.add_widget(message_label)
        dialog.add_button_box()
        dialog.exec_()
    #---------------------------------------------------------------------------------------
    # SCRIPT MANAGEMENT
    #---------------------------------------------------------------------------------------
    def execute_script_command(self):
        """Execute the script with namespace and token handling for Blender"""
        if self.mode != 'script' or not self.script_data:
            return
        
        # Only support Python in Blender
        if self.script_data.get('type', 'python') != 'python':
            self._show_error_dialog("MEL Not Supported", "MEL scripts are not supported in Blender. Please use Python instead.")
            return
        
        # Get the Python code
        code = self.script_data.get('python_code', self.script_data.get('code', ''))
        if not code.strip():
            self._show_error_dialog("Empty Script", "No script code to execute.")
            return
        
        try:
            # Get namespace info
            current_ns, ns_prefix = self._get_namespace_info()
            
            # Process the code (handle tokens and imports)
            modified_code = self._process_script_code(code, current_ns)
            
            # Set up execution environment
            global_vars = self._create_execution_environment(current_ns, ns_prefix)
            
            # Execute with proper Blender context
            #print(f"Executing script for button: {self.unique_id}")
            with bpy.context.temp_override(window=bpy.context.window_manager.windows[0]):
                exec(modified_code, global_vars, global_vars)
            #print("Script executed successfully")
            
        except Exception as e:
            self._show_script_error(str(e))
        finally:
            self._update_blender_ui()

    def _get_namespace_info(self):
        """Get current namespace and prefix from main window"""
        main_window = self.window()
        current_ns = ""
        ns_prefix = ""
        
        if isinstance(main_window, UI.BlenderAnimPickerWindow):
            current_ns = main_window.namespace_dropdown.currentText()
            ns_prefix = f"{current_ns}_" if current_ns and current_ns != 'None' else ""
        
        return current_ns, ns_prefix
    
    def _process_script_code(self, code, current_ns):
        """Process script code to handle tokens and imports"""
        modified_code = code
        
        # Remove tooltip functions (already handled in script manager)
        patterns_to_remove = [
            r'@TF\.tool_tip\s*\(\s*["\'](.+?)["\']\s*\)',
            r'@tool_tip\s*\(\s*["\'](.+?)["\']\s*\)',
            r'@tt\s*\(\s*["\'](.+?)["\']\s*\)',
        ]
        for pattern in patterns_to_remove:
            modified_code = re.sub(pattern, '', modified_code, flags=re.IGNORECASE)
        #--------------------------------------------------------------------------------------------------------
        # Replace namespace tokens with new logic
        def replace_ns_token(match):
            full_match = match.group(0)  # The entire @ns.qualifier
            qualifier = match.group(1)   # Just the qualifier part
            
            if current_ns and current_ns != 'None':
                # If there's a namespace, replace entire @ns.qualifier with just the namespace
                #print(f"Replacing '{full_match}' with '{current_ns}'")
                return current_ns
            else:
                # If namespace is None, replace @ns.qualifier with just the qualifier
                #print(f"Replacing '{full_match}' with '{qualifier}'")
                return qualifier
        
        # Replace @ns.qualifier patterns (this replaces the ENTIRE @ns.qualifier with the return value)
        modified_code = re.sub(r'@ns\.([a-zA-Z0-9_-]+)', replace_ns_token, modified_code, flags=re.IGNORECASE)
        #modified_code = re.sub(r'@ns\s*\(\s*["\'](.+?)["\']\s*\)', current_ns, modified_code, flags=re.IGNORECASE)
        
        # Handle @ns. without qualifier (standalone namespace references)
        if current_ns and current_ns != 'None':
            modified_code = re.sub(r'@ns(?!\w)', f'"{current_ns}"', modified_code, flags=re.IGNORECASE)
        else:
            modified_code = re.sub(r'@ns(?!\w)', '""', modified_code, flags=re.IGNORECASE)
        #--------------------------------------------------------------------------------------------------------
        # Handle TF function calls and add import if needed
        needs_tf_import = False
        
        # Handle general @TF.function_name calls
        tf_pattern = r'(\s*)@TF\.(?!tool_tip|tt)(\w+)\s*\(([^)]*)\)'
        if re.search(tf_pattern, modified_code, re.MULTILINE | re.IGNORECASE):
            modified_code = re.sub(tf_pattern, r'\1TF.\2(\3)', modified_code, flags=re.MULTILINE | re.IGNORECASE)
            needs_tf_import = True
        #--------------------------------------------------------------------------------------------------------
        # Handle @pb function calls and add import if needed
        pb_pattern = r'@pb\s*\(([^)]+)\)'
        if re.search(pb_pattern, modified_code, re.MULTILINE | re.IGNORECASE):
            modified_code = re.sub(pb_pattern, r'TF.pb(\1)', modified_code, flags=re.MULTILINE | re.IGNORECASE)
            needs_tf_import = True
        # second pattern for @pb
        pb_pattern_02 = r'@picker_button\s*\(([^)]+)\)'
        if re.search(pb_pattern_02, modified_code, re.MULTILINE | re.IGNORECASE):
            modified_code = re.sub(pb_pattern_02, r'TF.pb(\1)', modified_code, flags=re.MULTILINE | re.IGNORECASE)
            needs_tf_import = True
        #--------------------------------------------------------------------------------------------------------
        # handle @ba calls and add import if needed
        button_appearance_pattern = r'@ba\s*\(([^)]+)\)'
        if re.search(button_appearance_pattern, modified_code, re.MULTILINE | re.IGNORECASE):
            modified_code = re.sub(button_appearance_pattern, r'TF.button_appearance(\1)', modified_code, flags=re.MULTILINE | re.IGNORECASE)
            needs_tf_import = True
        # second pattern for @ba
        button_appearance_pattern_02 = r'@button_appearance\s*\(([^)]+)\)'
        if re.search(button_appearance_pattern_02, modified_code, re.MULTILINE | re.IGNORECASE):
            modified_code = re.sub(button_appearance_pattern_02, r'TF.button_appearance(\1)', modified_code, flags=re.MULTILINE | re.IGNORECASE)
            needs_tf_import = True
        #--------------------------------------------------------------------------------------------------------
        # handle @reset_all, @reset_translate, @reset_rotate, @reset_scale
        reset_all_pattern = r'@reset_all\b'
        if re.search(reset_all_pattern, modified_code, re.MULTILINE | re.IGNORECASE):
            modified_code = re.sub(reset_all_pattern, r'TF.reset_all()', modified_code, flags=re.MULTILINE | re.IGNORECASE)
            needs_tf_import = True
        reset_translate_pattern = r'@reset_move\b'
        if re.search(reset_translate_pattern, modified_code, re.MULTILINE | re.IGNORECASE):
            modified_code = re.sub(reset_translate_pattern, r'TF.reset_move()', modified_code, flags=re.MULTILINE | re.IGNORECASE)
            needs_tf_import = True
        reset_rotate_pattern = r'@reset_rotate\b'
        if re.search(reset_rotate_pattern, modified_code, re.MULTILINE | re.IGNORECASE):
            modified_code = re.sub(reset_rotate_pattern, r'TF.reset_rotate()', modified_code, flags=re.MULTILINE | re.IGNORECASE)
            needs_tf_import = True
        reset_scale_pattern = r'@reset_scale\b'
        if re.search(reset_scale_pattern, modified_code, re.MULTILINE | re.IGNORECASE):
            modified_code = re.sub(reset_scale_pattern, r'TF.reset_scale()', modified_code, flags=re.MULTILINE | re.IGNORECASE)
            needs_tf_import = True
        #--------------------------------------------------------------------------------------------------------
        # Handle Tool Tip calls and add import if needed
        tool_tip_pattern = r'@tt\s*\(([^)]+)\)'
        if re.search(tool_tip_pattern, modified_code, re.MULTILINE | re.IGNORECASE):
            modified_code = re.sub(tool_tip_pattern, r'TF.tool_tip(\1)', modified_code, flags=re.MULTILINE | re.IGNORECASE)
            needs_tf_import = True
        # second pattern for @tt
        tool_tip_pattern_02 = r'@tool_tip\s*\(([^)]+)\)'
        if re.search(tool_tip_pattern_02, modified_code, re.MULTILINE | re.IGNORECASE):
            modified_code = re.sub(tool_tip_pattern_02, r'TF.tool_tip(\1)', modified_code, flags=re.MULTILINE | re.IGNORECASE)
            needs_tf_import = True
        #--------------------------------------------------------------------------------------------------------
        # Add TF import if needed
        if needs_tf_import and 'import ft_anim_picker.src.tool_functions as TF' not in modified_code:
            modified_code = 'import ft_anim_picker.src.tool_functions as TF\n' + modified_code

        return modified_code

    def _create_execution_environment(self, current_ns, ns_prefix):
        """Create the execution environment with necessary variables and modules"""
        global_vars = {
            # Core Blender
            'bpy': bpy,
            'context': bpy.context,
            'data': bpy.data,
            'ops': bpy.ops,
            
            # Picker variables
            'picker_button': self,
            'assigned_objects': self.assigned_objects,
            'button_id': self.unique_id,
            'namespace': current_ns,
            'ns_prefix': ns_prefix,
            
            '__builtins__': __builtins__,
        }
        
        # Add optional modules if available
        for module_name in ['bmesh', 'mathutils']:
            try:
                module = __import__(module_name)
                global_vars[module_name] = module
            except ImportError:
                global_vars[module_name] = None
        
        return global_vars

    def _show_error_dialog(self, title, message):
        """Show a simple error dialog"""
        dialog = CD.CustomDialog(self, title=title, size=(250, 100), info_box=True)
        message_label = QtWidgets.QLabel(message)
        message_label.setWordWrap(True)
        dialog.add_widget(message_label)
        dialog.add_button_box()
        dialog.exec_()

    def _show_script_error(self, error_msg):
        """Show detailed script execution error"""
        print(f"Error executing Python script for button {self.unique_id}: {error_msg}")
        
        dialog = CD.CustomDialog(self, title="Script Execution Error", size=(400, 200), info_box=True)
        
        error_text = QtWidgets.QTextEdit()
        error_text.setReadOnly(True)
        error_text.setPlainText(f"Error in button '{self.label}' (ID: {self.unique_id}):\n\n{error_msg}")
        error_text.setStyleSheet("""
            QTextEdit {
                background-color: #2d2d2d;
                color: #ff6b6b;
                border: 1px solid #555;
                font-family: monospace;
                font-size: 11px;
            }
        """)
        error_text.setMaximumHeight(120)
        
        dialog.add_widget(error_text)
        dialog.add_button_box()
        dialog.exec_()

    def _update_blender_ui(self):
        """Force Blender UI updates"""
        try:
            with bpy.context.temp_override(window=bpy.context.window_manager.windows[0]):
                bpy.context.view_layer.update()
                for area in bpy.context.screen.areas:
                    if area.type == 'VIEW_3D':
                        area.tag_redraw()
        except:
            pass
    #---------------------------------------------------------------------------------------
    # BUTTON EDIT
    #---------------------------------------------------------------------------------------
    def set_size(self, width, height):
        self.width = width
        
        # In pose mode, height is always 1.25 times the width
        if self.mode == 'pose':
            # Store the provided height as original height for later use
            self._original_height = height
            # Force height to be 1.25 times width in pose mode
            self.height = width * 1.25
        else:
            self.height = height
            
        self.original_size = QtCore.QSize(self.width, self.height)
        self.update()
        self.changed.emit(self)
    
    def set_radius(self, top_left, top_right, bottom_right, bottom_left):
        self.radius = [top_left, top_right, bottom_right, bottom_left]
        self.update()
        self.changed.emit(self)

    def change_color(self, color):
        self.color = color
        self.update()
        self.changed.emit(self)  # Emit changed signal

    def change_opacity(self, value):
        self.opacity = value / 100.0
        self.update()
        self.changed.emit(self)  # Emit changed signal

    def rename_button(self, new_label):
        #if new_label and new_label != self.label:
        self.label = new_label
        # Force regeneration of text pixmap
        self.text_pixmap = None
        self.update()
        self.changed.emit(self)
    
    def enter_rename_mode(self):
        """Enter rename mode by creating a QLineEdit overlay"""
        if self.rename_mode:
            return
        canvas = self.parent()
        self.rename_mode = True
        zoom_factor = canvas.zoom_factor if canvas else 1.0

        # Create QLineEdit for renaming
        self.rename_edit = QtWidgets.QLineEdit(self)
        font = self.rename_edit.font()
        font.setPixelSize(int((self.height * 0.5) * zoom_factor))
        self.rename_edit.setFont(font)

        self.rename_edit.setText(self.label)
        self.rename_edit.setGeometry(self.rect())
        self.rename_edit.setToolTip("")
        self.rename_edit.setAlignment(QtCore.Qt.AlignCenter)
        self.rename_edit.setStyleSheet(f"""
            background-color: {self.color};
            color: #ffffff;
            border: 0px solid rgba(255,255,255,.8);
            border-radius: {self.border_radius}px;
            padding: 0px;
        """)
        
        def label_changed(new_label):
            for button in canvas.get_selected_buttons():
                button.label = new_label
                button.update()

        self.rename_edit.textChanged.connect(label_changed)
        self.rename_edit.returnPressed.connect(self.commit_rename)
        self.rename_edit.editingFinished.connect(self.commit_rename)
        
        # Show and focus
        self.rename_edit.show()
        self.rename_edit.selectAll()
        self.rename_edit.setFocus()
    
    def _update_rename_edit_geometry(self):
        if self.rename_mode and self.rename_edit:
            zoom_factor = self.parent().zoom_factor if self.parent() else 1.0
            self.rename_edit.setGeometry(self.rect())
            # Set font size using QFont
            font = self.rename_edit.font()
            font.setPixelSize(int((self.height * 0.5) * zoom_factor))
            self.rename_edit.setFont(font)
            # You can still use the stylesheet for color/background
            self.rename_edit.setStyleSheet(f"""
                background-color: {self.color};
                color: #ffffff;
                border: 0px solid rgba(255,255,255,.8);
                border-radius: {self.border_radius}px;
                padding: 0px;
            """)

    def exit_rename_mode(self):
        """Exit rename mode by removing the QLineEdit overlay"""
        if not self.rename_mode:
            return
            
        self.rename_mode = False
        
        if self.rename_edit:
            self.rename_edit.deleteLater()
            self.rename_edit = None
        
        self.update()
    
    def commit_rename(self):
        """Commit the rename changes and exit rename mode"""
        if not self.rename_mode or not self.rename_edit:
            return
            
        # Get the new label
        new_label = self.rename_edit.text().strip()
        
        self.rename_selected_buttons(new_label)
            
        # Exit rename mode
        self.exit_rename_mode()
    
    def delete_button(self):
        self.deleted.emit(self)
        self.deleteLater()
    #---------------------------------------------------------------------------------------
    def rename_selected_buttons(self, new_label):
        canvas = self.parent()
        if canvas:
            selected_buttons = canvas.get_selected_buttons()
            for button in selected_buttons:
                button.rename_button(new_label)
            
            # Update the main window
            main_window = canvas.window()
            if isinstance(main_window, UI.BlenderAnimPickerWindow):
                main_window.update_buttons_for_current_tab()
        self.update_tooltip()
        
    def change_color_for_selected_buttons(self, new_color):
        canvas = self.parent()
        if canvas:
            selected_buttons = canvas.get_selected_buttons()
            for button in selected_buttons:
                button.change_color(new_color)
            
            # Update the main window
            main_window = canvas.window()
            if isinstance(main_window, UI.BlenderAnimPickerWindow):
                main_window.update_buttons_for_current_tab()
    
    def change_opacity_for_selected_buttons(self, value):
        canvas = self.parent()
        if canvas:
            selected_buttons = canvas.get_selected_buttons()
            opacity = value #/ 100.0
            for button in selected_buttons:
                button.change_opacity(opacity)
            
            # Update the main window
            main_window = canvas.window()
            if isinstance(main_window, UI.BlenderAnimPickerWindow):
                main_window.update_buttons_for_current_tab()

    def delete_selected_buttons(self):
        """FIXED: Batch deletion with proper canvas and data handling"""
        canvas = self.parent()
        if not canvas:
            return
        
        selected_buttons = canvas.get_selected_buttons()
        
        if not selected_buttons:
            return
        
        # Get the main window for data updates
        main_window = canvas.window()
        
        # Disable canvas updates during batch operation
        canvas.setUpdatesEnabled(False)
        
        try:
            # Process deletions individually but efficiently
            deleted_button_ids = []
            
            for button in selected_buttons:
                deleted_button_ids.append(button.unique_id)
                
                # Remove from canvas buttons list
                if button in canvas.buttons:
                    canvas.buttons.remove(button)
                
                # Add to pending updates for data manager
                if hasattr(main_window, 'pending_button_updates'):
                    main_window.pending_button_updates.add(button.unique_id)
                
                # Clean up the widget
                button.deleteLater()
            if hasattr(canvas, 'transform_guides'):
                canvas.transform_guides.setVisible(False)
                canvas.transform_guides.visual_layer.setVisible(False)

            # Process the batch data update
            if hasattr(main_window, '_flush_pending_updates'):
                main_window._flush_pending_updates()
            
        finally:
            # Re-enable updates and refresh
            canvas.setUpdatesEnabled(True)
            canvas.update()
            
            # Force update of main window data
            if hasattr(main_window, 'update_buttons_for_current_tab'):
                main_window.update_buttons_for_current_tab(force_update=True)
    #---------------------------------------------------------------------------------------
    def add_selected_objects(self):
        """Store information about selected Blender objects or bones with namespace priority"""
        import bpy
        with bpy.context.temp_override(window=bpy.context.window_manager.windows[0]):
            new_objects = []
            active_obj = bpy.context.view_layer.objects.active
            current_mode = getattr(bpy.context, 'mode', None)
            
            # Get current namespace from main window
            main_window = self.window()
            current_namespace = None
            if hasattr(main_window, 'namespace_dropdown'):
                current_namespace = main_window.namespace_dropdown.currentText()
                if current_namespace == 'None':
                    current_namespace = None
            
            if active_obj:
                print(f"Active object: {active_obj.name}, Type: {active_obj.type}")
            
            if active_obj and active_obj.type == 'ARMATURE' and current_mode == 'POSE':
                # Check if we're in pose mode or need to switch
                
                object_mode = getattr(active_obj, 'mode', 'OBJECT')
                context_mode = getattr(bpy.context, 'mode', 'OBJECT')
                
                #print(f"Object mode: {object_mode}, Context mode: {context_mode}")
                
                # Try multiple methods to get selected pose bones
                selected_pose_bones = []
                
                # Method 1: Try context selected_pose_bones
                try:
                    context_bones = getattr(bpy.context, 'selected_pose_bones', None)
                    if context_bones:
                        selected_pose_bones = list(context_bones)
                        #print(f"Found {len(selected_pose_bones)} bones via context")
                except:
                    pass
                
                # Method 2: If no bones found via context, check bone selection manually
                if not selected_pose_bones and active_obj.pose:
                    for pose_bone in active_obj.pose.bones:
                        if pose_bone.bone.select:
                            selected_pose_bones.append(pose_bone)
                    #print(f"Found {len(selected_pose_bones)} bones via manual check")
                
                # Method 3: If still no bones and we're not in pose mode, try switching
                if not selected_pose_bones and object_mode != 'POSE':
                    try:
                        # Ensure armature is selected and active
                        bpy.ops.object.select_all(action='DESELECT')
                        active_obj.select_set(True)
                        bpy.context.view_layer.objects.active = active_obj
                        
                        # Switch to pose mode
                        bpy.ops.object.mode_set(mode='POSE')
                        bpy.context.view_layer.update()
                        
                        # Try getting selected bones again
                        context_bones = getattr(bpy.context, 'selected_pose_bones', None)
                        if context_bones:
                            selected_pose_bones = list(context_bones)
                            #print(f"Found {len(selected_pose_bones)} bones after mode switch")
                    except Exception as e:
                        print(f"Error switching to pose mode: {e}")
                
                #print(f"Final selected pose bones: {[bone.name for bone in selected_pose_bones]}")
                
                # Process selected bones with namespace priority
                for bone in selected_pose_bones:
                    try:
                        # Use current namespace if available, otherwise use active armature
                        armature_name = current_namespace if current_namespace else active_obj.name
                        
                        new_objects.append({
                            'name': bone.name,  # Just the bone name
                            'armature': armature_name,  # Use namespace or active armature
                            'is_bone': True
                        })
                        print(f"Added bone to picker: {bone.name} (in {armature_name})")
                    except Exception as e:
                        print(f"Error adding bone {bone.name}: {e}")
                        continue
                        
                # If no bones were selected, inform user
                if not selected_pose_bones:
                    print("No pose bones selected. Make sure bones are selected in pose mode.")
                    
            else:
                # Regular object selection
                print("Processing regular objects")
                selected = bpy.context.view_layer.objects.selected
                print(f"Selected objects: {[obj.name for obj in selected]}")
                
                for obj in selected:
                    try:
                        new_objects.append({
                            'name': obj.name,  # Simple Blender object name
                            'is_bone': False
                        })
                        print(f"Added object to picker: {obj.name}")
                    except Exception as e:
                        print(f"Error adding object {obj.name}: {e}")
                        continue
            
            # Add new objects, avoiding duplicates
            existing_names = {self._get_item_id(obj) for obj in self.assigned_objects}
            new_unique_objects = [obj for obj in new_objects if self._get_item_id(obj) not in existing_names]
            self.assigned_objects.extend(new_unique_objects)
            
            #print(f"Added {len(new_unique_objects)} new objects to picker")
        
        #self.update_tooltip()
        self._tooltip_needs_update = True
        self.changed.emit(self)
    
    def _get_item_id(self, obj_data):
        """Get unique identifier for an object/bone"""
        if obj_data.get('is_bone', False):
            return f"{obj_data.get('armature', '')}|{obj_data.get('name', '')}"
        return obj_data.get('name', '')
    
    def convert_assigned_objects(self, objects):
        """Convert old format (UUID only) to new format (UUID + long name) for Blender"""
        converted_objects = []
        for obj in objects:
            # Check if object is already in new format
            if isinstance(obj, dict) and 'uuid' in obj and 'name' in obj:
                converted_objects.append(obj)
            else:
                # Old format - only UUID or name
                try:
                    # In Blender, try to find the object by name
                    if obj in bpy.data.objects:
                        # For Blender, create a path that includes collection if available
                        obj_path = obj
                        blender_obj = bpy.data.objects[obj]
                        
                        # Try to find the collection it belongs to
                        for collection in bpy.data.collections:
                            if obj in collection.objects:
                                obj_path = f"{collection.name}/{obj}"
                                break
                                
                        converted_objects.append({
                            'uuid': obj,
                            'name': obj_path
                        })
                    else:
                        # Object might have been deleted, just store the name to avoid losing data
                        converted_objects.append({
                            'uuid': obj,
                            'name': obj
                        })
                except Exception as e:
                    print(f"Error converting object {obj}: {e}")
                    # Fall back to just storing the name
                    converted_objects.append({
                        'uuid': obj,
                        'name': obj
                    })
        return converted_objects

    def remove_all_objects(self):
        self.assigned_objects = []
        #self.update_tooltip()
        self._tooltip_needs_update = True
        self.changed.emit(self)  # Notify about the change to update data
    
    def remove_all_objects_for_selected_buttons(self):
        canvas = self.parent()
        if canvas:
            selected_buttons = canvas.get_selected_buttons()
            for button in selected_buttons:
                button.assigned_objects = []
                button.update_tooltip()
                button.changed.emit(button)  # Notify about the change to update data
    #---------------------------------------------------------------------------------------
    def mousePressEvent(self, event):
        """Enhanced button mouse press with proper modifier handling"""
        
        if event.button() == QtCore.Qt.LeftButton:
            canvas = self.parent()
            canvas._hide_button_tooltip()
            if canvas:
                # Get modifier states
                shift_held = event.modifiers() & QtCore.Qt.ShiftModifier
                ctrl_held = event.modifiers() & QtCore.Qt.ControlModifier
                alt_held = event.modifiers() & QtCore.Qt.AltModifier
                
                if self.edit_mode:
                    # Edit mode behavior (existing drag/duplicate logic)
                    if alt_held:
                        self.start_duplication_drag(event)
                    else:
                        self.dragging = True
                        self.drag_start_pos = event.globalPos()
                        self.button_start_pos = self.scene_position
                        self.setCursor(QtCore.Qt.ClosedHandCursor)

                        # Store the initial movement state for constraint calculation
                        self._initial_drag_pos = event.globalPos()
                        self._constraint_determined = False
                        self._constraint_axis = None  # 'x', 'y', or None
                        
                        if not self.is_selected and not shift_held:
                            canvas.clear_selection()
                            self.is_selected = True
                            self.selected.emit(self, True)
                            canvas.last_selected_button = self
                            canvas.button_selection_changed.emit()
                            self.update()
                        elif shift_held:
                            self.is_selected = not self.is_selected
                            if self.is_selected:
                                canvas.last_selected_button = self
                            self.selected.emit(self, self.is_selected)
                            canvas.button_selection_changed.emit()
                            self.update()
                        
                        # Set button start positions for dragging
                        for button in canvas.get_selected_buttons():
                            button.button_start_pos = button.scene_position
                else:
                    # Select mode behavior - handle all modifier combinations
                    if self.mode == 'select':
                        self.handle_select_mode_click(shift_held, ctrl_held, alt_held, canvas,event)
                    elif self.mode == 'script':
                        self.execute_script_command()
                    elif self.mode == 'pose':
                        if alt_held:
                            self.apply_mirrored_pose()
                        else:
                            self.apply_pose()
                    
                    
                event.accept()
        elif event.button() == QtCore.Qt.RightButton:
            shift_held = event.modifiers() & QtCore.Qt.ShiftModifier
            canvas = self.parent()
            if canvas:
                if not self.is_selected:
                    canvas.clear_selection() if not shift_held else None
                    self.is_selected = True
                    self.selected.emit(self, True)
                    canvas.last_selected_button = self
                    canvas.button_selection_changed.emit()
                    self.update()
            
            self.show_context_menu(event.pos())
            event.accept()
        else:
            super().mousePressEvent(event)
        
        double_click = event.type() == QtCore.QEvent.MouseButtonDblClick
        if not double_click:
            UT.blender_main_window()

    def mouseDoubleClickEvent(self, event):
        """Handle double-click events for renaming buttons in edit mode"""
        if not self.edit_mode:
            # Only handle double-clicks in edit mode
            super().mouseDoubleClickEvent(event)
            return
            
        # Start rename mode for all selected buttons
        canvas = self.parent()
        if canvas:
            selected_buttons = canvas.get_selected_buttons()
            
            # If this button is not selected, select it first
            if not self.is_selected:
                canvas.clear_selection()
                self.is_selected = True
                self.selected.emit(self, True)
                canvas.last_selected_button = self
                canvas.button_selection_changed.emit()
                self.update()
                selected_buttons = [self]
                
            # Enter rename mode for all selected buttons
            '''for button in selected_buttons:
                button.enter_rename_mode()'''
            self.enter_rename_mode()
        event.accept()

    def mouseMoveEvent(self, event):
        """Enhanced mouse move with duplication support and optimized dragging"""
        if hasattr(self, 'duplicating') and self.duplicating and event.buttons() & QtCore.Qt.LeftButton:
            # Handle duplication drag
            self.handle_duplication_drag(event)
            event.accept()
        elif self.dragging and event.buttons() & QtCore.Qt.LeftButton:
            canvas = self.parent()
            canvas._hide_button_tooltip()
            if not canvas:
                return

            # Throttle updates for better performance
            current_time = QtCore.QTime.currentTime().msecsSinceStartOfDay()
            if hasattr(self, 'last_drag_update'):
                if current_time - self.last_drag_update < 16:  # ~60fps limit
                    return
            self.last_drag_update = current_time

            delta = event.globalPos() - self.drag_start_pos
            scene_delta = QtCore.QPointF(delta.x(), delta.y()) / canvas.zoom_factor
            
            # Check for shift modifier for constrained movement
            shift_held = event.modifiers() & QtCore.Qt.ShiftModifier
            
            if shift_held:
                # Constrain movement to the dominant axis
                scene_delta = self._apply_axis_constraint(scene_delta)

            # CRITICAL: Disable all updates during drag
            canvas.setUpdatesEnabled(False)
            
            # Update positions without triggering individual signals
            selected_buttons = canvas.get_selected_buttons()
            for button in selected_buttons:
                button.scene_position = button.button_start_pos + scene_delta
            
            # Update button positions visually
            canvas.update_button_positions()
            
            # Re-enable updates
            canvas.setUpdatesEnabled(True)
            
            # Throttled transform guides update (much less frequent)
            if hasattr(canvas, '_update_transform_guides_position'):
                if not hasattr(canvas, '_last_guides_update'):
                    canvas._last_guides_update = 0
                
                current_time = QtCore.QTime.currentTime().msecsSinceStartOfDay()
                if current_time - canvas._last_guides_update > 50:  # Only update every 50ms
                    QtCore.QTimer.singleShot(1, canvas._update_transform_guides_position)
                    canvas._last_guides_update = current_time
            
            event.accept()
        else:
            super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        """Enhanced mouse release with optimized batch updates"""
        if event.button() == QtCore.Qt.LeftButton:
            canvas = self.parent()
            
            # Handle duplication completion
            if hasattr(self, 'duplicating') and self.duplicating:
                self.complete_duplication_drag(event)
                event.accept()
                return
            
            # Handle normal dragging completion
            if self.dragging:
                self.dragging = False
                self.update_cursor()
                
                if canvas:
                    # CRITICAL FIX: Batch update all dragged buttons at once
                    selected_buttons = canvas.get_selected_buttons()
                    
                    main_window = canvas.window()
                    if isinstance(main_window, UI.BlenderAnimPickerWindow):
                        # Use optimized batch position update
                        self._batch_update_button_positions(selected_buttons, main_window)
                
                event.accept()
        else:
            super().mouseReleaseEvent(event)
        
        #UT.blender_main_window()
    
    def event(self, event):
        """Override event to handle key events."""
        if event.type() == QtCore.QEvent.KeyPress:
            if event.key() == QtCore.Qt.Key_Escape:
                self.exit_rename_mode()
                return True
        return super().event(event)
    
    def enterEvent(self, event):
        """Called when mouse enters the button area."""
        self.is_hovered = True
        self.update()  # Trigger repaint
        super().enterEvent(event)

    def leaveEvent(self, event):
        """Called when mouse leaves the button area."""
        self.is_hovered = False
        self.update()  # Trigger repaint
        super().leaveEvent(event)
    
    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._update_rename_edit_geometry()

