from functools import partial
import bpy
import os
from functools import partial

from PySide6 import QtWidgets, QtCore, QtGui
from PySide6.QtGui import QColor, QAction
from PySide6.QtCore import QTimer, QPropertyAnimation, QEasingCurve, Signal

import re
import math

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


class ScreenRegionSelector(QtWidgets.QWidget):
    """
    A fullscreen overlay widget that allows users to select a square region
    of the screen for thumbnail capture.
    """
    region_selected = Signal(QtCore.QRect)
    cancelled = Signal()
    
    def __init__(self, background_pixmap, screen_geometry=None):
        super().__init__()
        self.background_pixmap = background_pixmap
        self.selection_start = None
        self.selection_rect = QtCore.QRect()
        self.is_selecting = False
        
        # Store screen geometry for coordinate mapping
        self.screen_geometry = screen_geometry
        
        # Setup fullscreen overlay - use Window flag instead of Tool for proper fullscreen
        self.setWindowFlags(
            QtCore.Qt.FramelessWindowHint |
            QtCore.Qt.WindowStaysOnTopHint
        )
        self.setAttribute(QtCore.Qt.WA_DeleteOnClose)
        self.setCursor(QtCore.Qt.CrossCursor)
        
        # Span the entire virtual desktop (all monitors)
        screens = QtGui.QGuiApplication.screens()
        if screens:
            virtual_rect = QtCore.QRect()
            for s in screens:
                virtual_rect = virtual_rect.united(s.geometry())
            self.setGeometry(virtual_rect)
            self.screen_offset = QtCore.QPoint(virtual_rect.x(), virtual_rect.y())
        else:
            self.screen_offset = QtCore.QPoint(0, 0)
            self.resize(800, 600)
        
        # Colors for the selection UI
        self.overlay_color = QtGui.QColor(0, 0, 0, 120)
        self.selection_border_color = QtGui.QColor(0, 174, 230)  # Bright cyan
        self.selection_fill_color = QtGui.QColor(0, 174, 230, 30)
        self.handle_color = QtGui.QColor(255, 255, 255)
        self.text_color = QtGui.QColor(255, 255, 255)
        self.text_bg_color = QtGui.QColor(0, 0, 0, 180)
        
        # Minimum selection size
        self.min_size = 50
        
        # Show the widget (not fullscreen mode, but covering full screen via geometry)
        self.show()
        self.raise_()
        self.activateWindow()
        
    def paintEvent(self, event):
        painter = QtGui.QPainter(self)
        painter.setRenderHint(QtGui.QPainter.Antialiasing)
        
        # Draw the background screenshot scaled to widget size
        # (grabWindow returns native-resolution pixels, widget is in logical coords)
        if self.background_pixmap and not self.background_pixmap.isNull():
            painter.drawPixmap(self.rect(), self.background_pixmap, self.background_pixmap.rect())
        
        # Draw semi-transparent overlay over the entire screen
        painter.fillRect(self.rect(), self.overlay_color)
        
        # If we have a selection, cut out that area and draw selection UI
        if not self.selection_rect.isNull() and self.selection_rect.isValid():
            # Clear the selection area to show the original image
            painter.setCompositionMode(QtGui.QPainter.CompositionMode_Clear)
            painter.fillRect(self.selection_rect, QtCore.Qt.transparent)
            
            # Reset composition mode
            painter.setCompositionMode(QtGui.QPainter.CompositionMode_SourceOver)
            
            # Draw the original image in the selection area
            # Source rect must be scaled by DPR to match native-resolution pixmap
            if self.background_pixmap and not self.background_pixmap.isNull():
                dpr = self.background_pixmap.devicePixelRatio()
                source_rect = QtCore.QRect(
                    int(self.selection_rect.x() * dpr),
                    int(self.selection_rect.y() * dpr),
                    int(self.selection_rect.width() * dpr),
                    int(self.selection_rect.height() * dpr)
                )
                painter.drawPixmap(
                    self.selection_rect,
                    self.background_pixmap,
                    source_rect
                )
            
            # Draw selection border with glow effect
            pen = QtGui.QPen(self.selection_border_color, 2)
            pen.setStyle(QtCore.Qt.SolidLine)
            painter.setPen(pen)
            painter.setBrush(QtCore.Qt.NoBrush)
            painter.drawRect(self.selection_rect)
            
            # Draw corner handles
            handle_size = 8
            corners = [
                self.selection_rect.topLeft(),
                self.selection_rect.topRight(),
                self.selection_rect.bottomLeft(),
                self.selection_rect.bottomRight()
            ]
            
            painter.setPen(QtCore.Qt.NoPen)
            painter.setBrush(self.handle_color)
            for corner in corners:
                handle_rect = QtCore.QRect(
                    corner.x() - handle_size // 2,
                    corner.y() - handle_size // 2,
                    handle_size,
                    handle_size
                )
                painter.drawRect(handle_rect)
            
            # Draw size indicator
            width = self.selection_rect.width()
            height = self.selection_rect.height()
            size_text = f"{width} × {height}"
            
            font = painter.font()
            font.setPointSize(10)
            font.setBold(True)
            painter.setFont(font)
            
            metrics = QtGui.QFontMetrics(font)
            text_rect = metrics.boundingRect(size_text)
            text_rect.adjust(-8, -4, 8, 4)
            
            # Position the text below the selection
            text_x = self.selection_rect.center().x() - text_rect.width() // 2
            text_y = self.selection_rect.bottom() + 10
            
            # Make sure text is visible on screen
            if text_y + text_rect.height() > self.height():
                text_y = self.selection_rect.top() - text_rect.height() - 10
            
            text_rect.moveTo(text_x, text_y)
            
            # Draw text background
            painter.setPen(QtCore.Qt.NoPen)
            painter.setBrush(self.text_bg_color)
            painter.drawRoundedRect(text_rect, 4, 4)
            
            # Draw text
            painter.setPen(self.text_color)
            painter.drawText(text_rect, QtCore.Qt.AlignCenter, size_text)
        
        # Draw instructions at the top
        self._draw_instructions(painter)
        
    def _draw_instructions(self, painter):
        """Draw instruction text at the top of the screen"""
        instruction_text = "Drag to select a region  •  ESC to cancel  •  Release to capture (auto-cropped to square)"
        
        font = painter.font()
        font.setPointSize(11)
        painter.setFont(font)
        
        metrics = QtGui.QFontMetrics(font)
        text_rect = metrics.boundingRect(instruction_text)
        text_rect.adjust(-16, -8, 16, 8)
        
        # Center horizontally at the top
        text_rect.moveTo(
            (self.width() - text_rect.width()) // 2,
            20
        )
        
        # Draw background
        painter.setPen(QtCore.Qt.NoPen)
        painter.setBrush(self.text_bg_color)
        painter.drawRoundedRect(text_rect, 6, 6)
        
        # Draw text
        painter.setPen(self.text_color)
        painter.drawText(text_rect, QtCore.Qt.AlignCenter, instruction_text)
    
    def mousePressEvent(self, event):
        if event.button() == QtCore.Qt.LeftButton:
            self.selection_start = event.pos()
            self.is_selecting = True
            self.selection_rect = QtCore.QRect()
            self.update()
    
    def mouseMoveEvent(self, event):
        if self.is_selecting and self.selection_start:
            current_pos = event.pos()
            
            # Create a rectangle from start to current position - simple and intuitive
            self.selection_rect = QtCore.QRect(self.selection_start, current_pos).normalized()
            
            # Clamp to screen bounds
            screen_rect = self.rect()
            if self.selection_rect.left() < 0:
                self.selection_rect.setLeft(0)
            if self.selection_rect.top() < 0:
                self.selection_rect.setTop(0)
            if self.selection_rect.right() > screen_rect.right():
                self.selection_rect.setRight(screen_rect.right())
            if self.selection_rect.bottom() > screen_rect.bottom():
                self.selection_rect.setBottom(screen_rect.bottom())
            
            self.update()
    
    def mouseReleaseEvent(self, event):
        if event.button() == QtCore.Qt.LeftButton and self.is_selecting:
            self.is_selecting = False
            
            if self.selection_rect.isValid() and self.selection_rect.width() >= self.min_size:
                self.region_selected.emit(self.selection_rect)
                self.close()
            else:
                # Selection too small, reset
                self.selection_rect = QtCore.QRect()
                self.update()
    
    def keyPressEvent(self, event):
        if event.key() == QtCore.Qt.Key_Escape:
            self.cancelled.emit()
            self.close()
        else:
            super().keyPressEvent(event)


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
                    'svg_file_path': button.svg_file_path,
                    'text_color': button.text_color,
                    'text_bold': button.text_bold,
                    'text_italic': button.text_italic,
                    'text_underline': button.text_underline,
                    'rotation': getattr(button, 'rotation', 0),
                }
                
                # Add pose-specific data if this is a pose button
                if button.mode == 'pose':
                    button_data['thumbnail_path'] = getattr(button, 'thumbnail_path', '')
                    button_data['pose_data'] = self._safe_copy_dict(getattr(button, 'pose_data', {}))
                    button_data['animation_data'] = self._safe_copy_dict(getattr(button, 'animation_data', {}))

                # Add controller-specific data
                if button.mode == 'controller':
                    button_data['controller_data'] = self._safe_copy_dict(getattr(button, 'controller_data', {}))

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
        self.text_bold = False
        self.text_italic = False
        self.text_underline = False
        
        # Pose dragging state
        self.pose_dragging = False
        self.pose_drag_start_pos = None
        self.current_pose_stage = 0  # Current stage (0-10)
        self.staged_poses = []  # Pre-calculated intermediate poses
        
        self.shape_type = shape_type  # 'rounded_rect' or 'custom_path'
        self.svg_path_data = svg_path_data  # Store the SVG path string
        self.svg_file_path = svg_file_path  # Store the original SVG file path

        self.cached_mask = None
        self.last_mask_zoom_factor = 0
        self.last_mask_size = None
        self.last_mask_radius = None
        self.last_mask_shape_type = None
        self.last_mask_svg_data = None
        self.last_mask_rotation = None

        self.rotation = 0

        # Canvas-painted mode: when True, the canvas draws this button
        # directly in its paintEvent instead of the button drawing itself.
        self._canvas_painted = False

        # --- Per-button paint caches (avoid per-frame allocations) ---
        self._cached_scene_path = None     # QPainterPath for paint_on_canvas
        self._cached_scene_path_key = None # (w, h, radii_tuple, shape_type) invalidation key
        self._cached_envelope = None       # (env_w, env_h) from rotated_envelope_size
        self._cached_envelope_key = None   # (rotation, w, h) invalidation key
        self._brush_normal = None          # QBrush for normal state
        self._brush_color_key = None       # color string for cache invalidation

        self.setStyleSheet(f"QToolTip {{background-color: {UT.rgba_value(color,.7,alpha=1)}; color: #eeeeee ; border: 1px solid rgba(255,255,255,.2); padding: 0px;}}")
        # Create tooltip widget once and reuse it
        self.tooltip_widget = CB.CustomTooltipWidget(parent=self)
        self._tooltip_populated = False
        self._tooltip_needs_update = True 
       
        self.edit_mode = False
        self.update_cursor()
        self.assigned_objects = []  

        self.mode = 'select'  # 'select', 'script', 'pose', or 'controller'
        self.script_data = {}  # Store script data
        self.pose_data = {}  # Store pose data
        self.animation_data = {}  # Store animation keyframe data (multi-frame)
        self.controller_data = {}  # Store controller mode config (field_type, data_path, min/max, etc.)

        # Controller mode runtime state (NOT persisted)
        self._controller_value = 0.0
        self._controller_value_y = 0.0
        self._controller_dragging = False
        self._controller_drag_start_x = 0.0
        self._controller_drag_start_y = 0.0
        self._controller_drag_start_val = 0.0
        self._controller_drag_start_val_y = 0.0
        self._controller_sync_timer = None
        self._controller_input_active = False
        self.controller_pixmap = None  # Cached pixmap for controller mode

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
        
    def rotated_envelope_size(self):
        """Return (width, height) of the axis-aligned bounding box after rotation.
        At rotation==0 this returns (self.width, self.height) with no math.
        Result is cached and invalidated when rotation or dimensions change."""
        key = (self.rotation, self.width, self.height)
        if self._cached_envelope_key == key and self._cached_envelope is not None:
            return self._cached_envelope
        if self.rotation == 0:
            result = (self.width, self.height)
        else:
            rad = math.radians(self.rotation)
            cos_a, sin_a = abs(math.cos(rad)), abs(math.sin(rad))
            result = (self.width * cos_a + self.height * sin_a,
                      self.width * sin_a + self.height * cos_a)
        self._cached_envelope = result
        self._cached_envelope_key = key
        return result

    def _content_rect_for_paint(self, zoom_factor):
        """Return the content QRectF for painting (un-rotated button dimensions).
        When rotation != 0, this is centered at origin (painter is already translated/rotated).
        When rotation == 0, this is self.rect().adjusted(1,1,-1,-1) as before."""
        if self.rotation == 0:
            return self.rect().adjusted(1, 1, -1, -1)
        cw = self.width * zoom_factor
        ch = self.height * zoom_factor
        return QtCore.QRectF(-cw / 2 + 1, -ch / 2 + 1, cw - 2, ch - 2)

    def _content_size_for_pixmap(self, zoom_factor):
        """Return QSize for pixmap rendering — content dimensions, not envelope."""
        if self.rotation == 0:
            return self.size()
        cw = max(1, int(self.width * zoom_factor + 0.5))
        ch = max(1, int(self.height * zoom_factor + 0.5))
        return QtCore.QSize(cw, ch)

    @property
    def scene_position(self):
        return self._scene_position

    @scene_position.setter
    def scene_position(self, pos):
        self._scene_position = pos
        if self.parent():
            self.parent().update_button_positions()

    def set_scene_position_silent(self, pos):
        """Set scene position without triggering canvas update.
        Caller is responsible for calling canvas.update_button_positions() after batch."""
        self._scene_position = pos

    @property
    def is_animation(self):
        """True if this button holds animation data rather than a single-frame pose."""
        return bool(self.animation_data)
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
            # Set up font for pose mode with text formatting
            pose_painter.setPen(QtGui.QColor(self.text_color))
            pose_font = pose_painter.font()
            font_size = max(int(calculated_font_size), 2)  # Ensure minimum readable size
            pose_font.setPixelSize(font_size)
            pose_font.setBold(self.text_bold)
            pose_font.setItalic(self.text_italic)
            pose_font.setUnderline(self.text_underline)
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
            
            # Draw text at bottom - show stage counter during pose dragging
            if hasattr(self, 'pose_dragging') and self.pose_dragging and hasattr(self, 'current_pose_stage'):
                stage_text = f"{self.current_pose_stage * 10}%"
                pose_painter.drawText(text_rect, QtCore.Qt.AlignHCenter | QtCore.Qt.AlignBottom, stage_text)
            else:
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

        # Draw animation badge if this is an animation button (play icon)
        # Scale proportionally to button width, same approach as label font sizing
        if self.is_animation:
            badge_size = max(2, int(self.width * 0.2 * zoom_factor))
            margin = max(1, int(badge_size * 0.15))
            badge_x = thumbnail_rect.right() - badge_size - margin
            badge_y = thumbnail_rect.top() + margin
            play_pixmap = UT.get_icon('play_icon.png', size=badge_size)
            if play_pixmap and not play_pixmap.isNull():
                pose_painter.drawPixmap(int(badge_x), int(badge_y), play_pixmap)

        pose_painter.end()
        return pose_pixmap

    def _render_text_pixmap(self, current_size, zoom_factor):
        """Render the pixmap for regular mode with centered text.
        
        Args:
            current_size (QSize): Current button size
            zoom_factor (float): Current zoom factor
            
        Returns:
            QPixmap: The rendered text pixmap
        """
        text_pixmap = QtGui.QPixmap(current_size)
        text_pixmap.fill(QtCore.Qt.transparent)
        
        text_painter = QtGui.QPainter(text_pixmap)
        text_painter.setRenderHint(QtGui.QPainter.Antialiasing)
        text_painter.setRenderHint(QtGui.QPainter.TextAntialiasing)
        
        # Set up font with text formatting
        text_painter.setPen(QtGui.QColor(self.text_color))
        font = text_painter.font()
        font.setBold(self.text_bold)
        font.setItalic(self.text_italic)
        font.setUnderline(self.text_underline)
        
        # Start with height-based calculation (preserve as priority)
        font_size = (self.height * 0.5) * zoom_factor
        
        # If font size is too small, skip rendering and return empty pixmap for performance
        if font_size < 0.1:
            text_painter.end()
            return text_pixmap
        
        # Calculate text rect with padding (use pixmap rect, not widget rect)
        text_rect = QtCore.QRect(0, 0, current_size.width(), current_size.height())
        bottom_padding = (self.height * 0.1) * zoom_factor
        text_rect.adjust(0, 0, 0, -int(bottom_padding))
        
        # Check if text fits width and adjust if needed
        # Ensure font size is at least 1 pixel
        font_size = max(1, int(font_size))
        font.setPixelSize(font_size)

        text_painter.setFont(font)
        text_metrics = text_painter.fontMetrics()
        text_width = text_metrics.horizontalAdvance(self.label)
        
        # If text is wider than button (with some padding), reduce font size to fit
        if text_width > (current_size.width() * 0.9):  # 10% padding
            width_based_font_size = font_size * (current_size.width() * 0.8) / text_width
            # Use the smaller of the two sizes to ensure text fits both dimensions
            font_size = min(font_size, width_based_font_size)
            # Ensure font size is at least 1 pixel before setting
            font_size = max(1, int(font_size))
            font.setPixelSize(font_size)
            text_painter.setFont(font)
        
        # Draw text centered - show stage counter during pose dragging
        if hasattr(self, 'pose_dragging') and self.pose_dragging and hasattr(self, 'current_pose_stage'):
            stage_text = f"Stage {self.current_pose_stage}/10"
            text_painter.drawText(text_rect, QtCore.Qt.AlignCenter, stage_text)
        else:
            text_painter.drawText(text_rect, QtCore.Qt.AlignCenter, self.label)
        text_painter.end()
        
        return text_pixmap

    # ── Controller mode rendering & sync ──────────────────────────────────

    # -- Omni controller layout fractions (shared by renderer, geometry,
    #    button-shape snap, and scale-lock so they stay in sync). ------------
    OMNI_TRACK_W_FRAC = 0.88
    OMNI_LABEL_HEADER_FRAC = 0.22
    OMNI_LABEL_TRACK_Y_FRAC = 0.22
    OMNI_LABEL_TRACK_H_FRAC = 0.74
    OMNI_NOLABEL_TRACK_Y_FRAC = 0.12
    OMNI_NOLABEL_TRACK_H_FRAC = 0.76

    @classmethod
    def omni_track_y_frac(cls, has_label):
        return cls.OMNI_LABEL_TRACK_Y_FRAC if has_label else cls.OMNI_NOLABEL_TRACK_Y_FRAC

    @classmethod
    def omni_track_h_frac(cls, has_label):
        return cls.OMNI_LABEL_TRACK_H_FRAC if has_label else cls.OMNI_NOLABEL_TRACK_H_FRAC

    @classmethod
    def omni_aspect_ratio(cls, has_label):
        """Return the height/width ratio that makes the omni pad square."""
        return cls.OMNI_TRACK_W_FRAC / cls.omni_track_h_frac(has_label)

    def _render_controller_pixmap(self, content_size, zoom_factor):
        """Render the pixmap for controller mode with header label and slider/input.

        Args:
            content_size (QSize): Pixel size of the pixmap
            zoom_factor (float): Current zoom factor

        Returns:
            QPixmap: The rendered controller pixmap
        """
        pixmap = QtGui.QPixmap(content_size)
        pixmap.fill(QtCore.Qt.transparent)

        p = QtGui.QPainter(pixmap)
        p.setRenderHint(QtGui.QPainter.Antialiasing)
        p.setRenderHint(QtGui.QPainter.TextAntialiasing)

        pw = content_size.width()
        ph = content_size.height()

        cd = self.controller_data
        field_type = cd.get('field_type', 'slider')
        slider_theme = cd.get('slider_theme', 'bar')
        is_omni = (field_type == 'omni')

        # ── Header label (top portion — only if label exists, non-empty, and show_label enabled) ──
        show_label = cd.get('show_label', True)
        has_label = bool(self.label and self.label.strip() and show_label)
        if has_label:
            # Omni uses a slightly tighter header so the pad gets more vertical
            # space; sliders keep the original 30% header.
            header_h = int(ph * (self.OMNI_LABEL_HEADER_FRAC if is_omni else 0.30))
            calculated_font_size = (self.height * 0.22) * zoom_factor
            if calculated_font_size >= 2:
                font = p.font()
                font_px = max(2, int(calculated_font_size))
                # Also cap by width so long labels don't overflow
                font_px = min(font_px, int(pw * 0.14))
                font.setPixelSize(max(2, font_px))
                font.setBold(self.text_bold)
                font.setItalic(self.text_italic)
                font.setUnderline(self.text_underline)
                p.setFont(font)
                p.setPen(QtGui.QColor(self.text_color))
                header_rect = QtCore.QRect(int(pw * 0.06), 0, int(pw * 0.88), header_h)
                p.drawText(header_rect, QtCore.Qt.AlignLeft | QtCore.Qt.AlignVCenter, self.label)

        # ── Control area ──
        margin_x = int(pw * 0.06)
        if is_omni:
            track_y = int(ph * self.omni_track_y_frac(has_label))
            track_h = int(ph * self.omni_track_h_frac(has_label))
        elif has_label:
            track_y = int(ph * 0.36)
            track_h = int(ph * 0.50)
        else:
            track_y = int(ph * 0.12)
            track_h = int(ph * 0.76)
        track_w = pw - margin_x * 2
        if track_w < 2 or track_h < 2:
            p.end()
            return pixmap

        # Omni (2-axis pad) renders its own control area and exits early.
        if is_omni:
            control_rect = QtCore.QRectF(margin_x, track_y, pw - margin_x * 2, track_h)
            self._render_controller_omni_pad(p, control_rect, cd)
            p.end()
            return pixmap

        track_rect = QtCore.QRectF(margin_x, track_y, track_w, track_h)
        fraction = self._controller_slider_fraction()

        if slider_theme == 'circle':
            # ── Circle-on-track theme ──
            # Thin horizontal track with a circle thumb
            track_line_h = max(2, track_h * 0.18)
            track_line_y = track_y + (track_h - track_line_h) / 2
            track_line_rect = QtCore.QRectF(margin_x, track_line_y, track_w, track_line_h)
            track_line_radius = track_line_h / 2

            # Background track line
            p.setPen(QtCore.Qt.NoPen)
            p.setBrush(QtGui.QColor(51, 51, 51))
            p.drawRoundedRect(track_line_rect, track_line_radius, track_line_radius)

            # Filled portion (left of thumb)
            slider_color = QtGui.QColor(self.color)
            if fraction > 0.001:
                fill_w = max(track_line_radius * 2, track_w * fraction)
                fill_rect = QtCore.QRectF(margin_x, track_line_y, fill_w, track_line_h)
                p.setBrush(slider_color)
                clip_path = QtGui.QPainterPath()
                clip_path.addRoundedRect(track_line_rect, track_line_radius, track_line_radius)
                p.setClipPath(clip_path)
                p.drawRect(fill_rect)
                p.setClipping(False)

            # Circle thumb
            thumb_radius = max(3, track_h * 0.40)
            thumb_cx = margin_x + track_w * fraction
            thumb_cx = max(margin_x + thumb_radius, min(margin_x + track_w - thumb_radius, thumb_cx))
            thumb_cy = track_y + track_h / 2
            p.setPen(QtCore.Qt.NoPen)
            p.setBrush(slider_color)
            p.drawEllipse(QtCore.QPointF(thumb_cx, thumb_cy), thumb_radius, thumb_radius)

        else:
            # ── Bar theme (default) ──
            track_radius = max(2, track_h * 0.25)

            # Background track
            p.setPen(QtCore.Qt.NoPen)
            p.setBrush(QtGui.QColor(51, 51, 51))
            p.drawRoundedRect(track_rect, track_radius, track_radius)

            # Filled portion
            if fraction > 0.001:
                fill_w = max(track_radius * 2, track_w * fraction)
                fill_rect = QtCore.QRectF(margin_x, track_y, fill_w, track_h)
                slider_color = QtGui.QColor(self.color)
                p.setBrush(slider_color)
                clip_path = QtGui.QPainterPath()
                clip_path.addRoundedRect(track_rect, track_radius, track_radius)
                p.setClipPath(clip_path)
                p.drawRect(fill_rect)
                p.setClipping(False)

        # Value text centered on track (bar theme only)
        if slider_theme != 'circle':
            precision = cd.get('precision', 2)
            val_text = f"{self._controller_value:.{precision}f}"
            val_font_size = max(2, int(track_h * 0.55))
            font = p.font()
            font.setPixelSize(val_font_size)
            font.setBold(False)
            font.setItalic(False)
            font.setUnderline(False)
            p.setFont(font)
            p.setPen(QtGui.QColor(255, 255, 255, 220))
            p.drawText(track_rect.toRect(), QtCore.Qt.AlignCenter, val_text)

        p.end()
        return pixmap

    def _apply_controller_drag_delta(self, global_dx, global_dy, zoom):
        """Apply a screen-space drag delta to this controller button.

        Handles both 1D sliders (delta projected onto the local X axis,
        rotation-aware) and omni 2D pads (both axes projected into the
        local frame).
        """
        cd = self.controller_data
        if self.rotation:
            rad = math.radians(-self.rotation)
            cos_a, sin_a = math.cos(rad), math.sin(rad)
            local_dx = global_dx * cos_a - global_dy * sin_a
            local_dy = global_dx * sin_a + global_dy * cos_a
        else:
            local_dx = global_dx
            local_dy = global_dy

        if cd.get('field_type') == 'omni':
            min_x = cd.get('min_value_x', -1.0)
            max_x = cd.get('max_value_x', 1.0)
            min_y = cd.get('min_value_y', -1.0)
            max_y = cd.get('max_value_y', 1.0)
            prec_x = cd.get('precision_x', 3)
            prec_y = cd.get('precision_y', 3)

            # Use the same pad geometry the renderer uses so the thumb tracks
            # the cursor 1:1.
            pad_size_px, thumb_radius_px = self._omni_pad_geometry(zoom)
            travel_px = max(1.0, pad_size_px - 2 * thumb_radius_px)

            dval_x = (local_dx / travel_px) * (max_x - min_x)
            dval_y = -(local_dy / travel_px) * (max_y - min_y)

            new_x = round(max(min_x, min(max_x, self._controller_drag_start_val + dval_x)), prec_x)
            new_y = round(max(min_y, min(max_y, self._controller_drag_start_val_y + dval_y)), prec_y)

            changed = False
            if abs(new_x - self._controller_value) > 1e-8:
                self._controller_value = new_x
                changed = True
            if abs(new_y - self._controller_value_y) > 1e-8:
                self._controller_value_y = new_y
                changed = True
            if changed:
                self._write_controller_xy(new_x, new_y)
                self.controller_pixmap = None
                canvas = self.parent()
                if canvas:
                    canvas.update()
            return

        # 1D slider — only the local X component contributes
        min_v = cd.get('min_value', 0.0)
        max_v = cd.get('max_value', 1.0)
        precision = cd.get('precision', 2)
        drag_range_px = max(1.0, self.width * zoom)
        delta_val = (local_dx / drag_range_px) * (max_v - min_v)
        new_val = round(max(min_v, min(max_v, self._controller_drag_start_val + delta_val)), precision)
        if abs(new_val - self._controller_value) > 1e-8:
            self._controller_value = new_val
            self._write_controller_value(new_val)
            self.controller_pixmap = None
            canvas = self.parent()
            if canvas:
                canvas.update()

    def _controller_slider_fraction(self):
        """Return the slider fill fraction clamped to [0, 1]."""
        cd = self.controller_data
        min_v = cd.get('min_value', 0.0)
        max_v = cd.get('max_value', 1.0)
        if max_v <= min_v:
            return 0.0
        return max(0.0, min(1.0, (self._controller_value - min_v) / (max_v - min_v)))

    def _controller_omni_fractions(self):
        """Return (fx, fy) thumb fractions in [0, 1] for the omni pad.

        fy is laid out so that max_value_y appears at the TOP of the pad
        (screen-up = +Y), matching common joystick / trackpad UX.
        """
        cd = self.controller_data
        min_x = cd.get('min_value_x', -1.0)
        max_x = cd.get('max_value_x', 1.0)
        min_y = cd.get('min_value_y', -1.0)
        max_y = cd.get('max_value_y', 1.0)
        fx = 0.5 if max_x <= min_x else (self._controller_value - min_x) / (max_x - min_x)
        fy_val = 0.5 if max_y <= min_y else (self._controller_value_y - min_y) / (max_y - min_y)
        fy = 1.0 - fy_val
        return max(0.0, min(1.0, fx)), max(0.0, min(1.0, fy))

    def _omni_pad_geometry(self, zoom):
        """Return shared pad geometry for the omni control area.

        The pad is always square — the largest square that fits in the
        control area — so the visual layout matches the drag math regardless
        of button aspect ratio.
        """
        pw = self.width * zoom
        ph = self.height * zoom
        margin_x = pw * 0.06
        show_label = self.controller_data.get('show_label', True)
        has_label = bool(self.label and self.label.strip() and show_label)
        track_h_avail = ph * self.omni_track_h_frac(has_label)
        track_w_avail = max(0.0, pw - 2 * margin_x)
        pad_size = max(0.0, min(track_w_avail, track_h_avail))
        thumb_radius = max(3.0, pad_size * 0.16)
        return pad_size, thumb_radius

    def _render_controller_omni_pad(self, p, control_rect, cd):
        """Render a 2D square pad with an outlined frame, axis guides, and a
        thumb dot. Frame and guides use the button color over transparent.
        """
        avail_w = control_rect.width()
        avail_h = control_rect.height()
        if avail_w < 4 or avail_h < 4:
            return

        pad_size = min(avail_w, avail_h)
        if pad_size < 4:
            return
        pad_left = control_rect.left() + (avail_w - pad_size) / 2.0
        pad_top = control_rect.top() + (avail_h - pad_size) / 2.0
        # Inset the rect by half the stroke width so the outline is fully
        # inside the available control area.
        stroke_w = max(1.0, pad_size * 0.025)
        inset = stroke_w / 2.0
        pad_rect = QtCore.QRectF(
            pad_left + inset, pad_top + inset,
            pad_size - 2 * inset, pad_size - 2 * inset
        )

        slider_color = QtGui.QColor(self.color)

        # Outlined frame in button color over transparent background
        pad_radius = max(3.0, pad_size * 0.10)
        frame_pen = QtGui.QPen(slider_color, stroke_w)
        frame_pen.setCosmetic(False)
        frame_pen.setJoinStyle(QtCore.Qt.RoundJoin)
        p.setPen(frame_pen)
        p.setBrush(QtCore.Qt.NoBrush)
        p.drawRoundedRect(pad_rect, pad_radius, pad_radius)

        # Axis guides at center — same color as the frame, low alpha
        axis_color = QtGui.QColor(slider_color)
        axis_color.setAlpha(90)
        axis_pen = QtGui.QPen(axis_color, max(1.0, stroke_w * 0.6))
        axis_pen.setCosmetic(False)
        p.setPen(axis_pen)
        cx = pad_rect.left() + pad_rect.width() / 2.0
        cy = pad_rect.top() + pad_rect.height() / 2.0
        guide_inset = pad_radius * 0.5
        p.drawLine(QtCore.QPointF(pad_rect.left() + guide_inset, cy),
                   QtCore.QPointF(pad_rect.right() - guide_inset, cy))
        p.drawLine(QtCore.QPointF(cx, pad_rect.top() + guide_inset),
                   QtCore.QPointF(cx, pad_rect.bottom() - guide_inset))

        # Thumb at fractional position
        fx, fy = self._controller_omni_fractions()
        thumb_radius = max(3.0, pad_size * 0.12)
        inner_w = pad_rect.width() - 2 * thumb_radius
        inner_h = pad_rect.height() - 2 * thumb_radius
        thumb_x = pad_rect.left() + thumb_radius + inner_w * fx
        thumb_y = pad_rect.top() + thumb_radius + inner_h * fy

        p.setPen(QtCore.Qt.NoPen)
        p.setBrush(slider_color)
        p.drawEllipse(QtCore.QPointF(thumb_x, thumb_y), thumb_radius, thumb_radius)

    def _resolve_controller_data_path(self, path_key='data_path'):
        """Resolve a controller data path, handling relative paths via namespace.

        Args:
            path_key: Which key in controller_data to read. Defaults to
                'data_path' (1D slider). For omni mode use 'data_path_x' or
                'data_path_y'.
        """
        cd = self.controller_data
        path_type = cd.get('path_type', 'absolute')
        data_path = cd.get(path_key, '')

        if not data_path:
            return ''

        if path_type == 'relative':
            # Resolve through the namespace armature
            current_ns, ns_prefix = self._get_namespace_info()
            armature_name = ''

            # 1. Try assigned_objects (if button has any)
            if self.assigned_objects:
                for obj_info in self.assigned_objects:
                    arm = obj_info.get('armature', '') or obj_info.get('source_armature', '')
                    if arm:
                        if ns_prefix and not arm.startswith(ns_prefix):
                            armature_name = ns_prefix + arm
                        else:
                            armature_name = arm
                        break

            # 2. Fallback: namespace dropdown value (often the armature name)
            if not armature_name and current_ns and current_ns != 'None':
                armature_name = current_ns

            # 3. Fallback: active object if it's an armature.
            # Use view_layer.objects.active — bpy.context.active_object is
            # not reliably available from Qt event callbacks in recent Blender.
            if not armature_name:
                try:
                    view_layer = bpy.context.view_layer
                    active = view_layer.objects.active if view_layer else None
                    if active and active.type == 'ARMATURE':
                        armature_name = active.name
                except Exception:
                    pass

            # 4. Fallback: first armature in scene
            if not armature_name:
                try:
                    for obj in bpy.context.scene.objects:
                        if obj.type == 'ARMATURE':
                            armature_name = obj.name
                            break
                except Exception:
                    pass

            if not armature_name:
                return ''

            # If the stored "relative" path still carries a bpy.data.objects[...]
            # prefix (e.g. the user typed/picked an absolute path then toggled
            # the segment to Relative), strip it so we don't double-prefix.
            import re as _re
            m = _re.match(r'^bpy\.data\.objects\["[^"]+"\]\.(.*)$', data_path)
            if m:
                data_path = m.group(1)
            return f'bpy.data.objects["{armature_name}"].{data_path}'

        return data_path

    def _select_controller_object(self):
        """Select the Blender objects/bones controlled by all selected controller buttons.

        Follows the same selection pattern as select-mode buttons:
        enters pose mode for bone paths, handles bone-collection visibility,
        and uses temp_override for operator context.
        """
        import re
        canvas = self.parent()
        if not canvas:
            return

        # Lock selection sync to prevent Blender->picker sync from
        # clearing our picker selection while we update Blender's selection.
        from . import selection_sync_manager as SSM
        sync_manager = None
        try:
            sync_manager = SSM.SelectionSyncManager.get_instance()
            sync_manager._sync_lock = True
        except Exception:
            pass

        # Gather all selected controller buttons (including self)
        targets = []  # list of (obj_name, bone_name_or_None)
        buttons = [self]
        for btn in canvas.get_selected_buttons():
            if btn.mode == 'controller' and btn is not self:
                buttons.append(btn)

        for btn in buttons:
            field_type = btn.controller_data.get('field_type', 'slider')
            if field_type == 'omni':
                path_keys = ('data_path_x', 'data_path_y')
            else:
                path_keys = ('data_path',)
            for pk in path_keys:
                path = btn._resolve_controller_data_path(pk)
                if not path:
                    continue
                m = re.match(r'bpy\.data\.objects\["([^"]+)"\]', path)
                if not m:
                    continue
                obj_name = m.group(1)
                bm = re.search(r'pose\.bones\["([^"]+)"\]', path)
                bone_name = bm.group(1) if bm else None
                # Avoid duplicate (obj, bone) entries (omni X & Y typically share)
                key = (obj_name, bone_name)
                if key not in targets:
                    targets.append(key)

        if not targets:
            # Release sync lock with delay (we're in Qt context)
            if sync_manager:
                QtCore.QTimer.singleShot(100, sync_manager._delayed_unlock)
            return

        try:
            with bpy.context.temp_override(window=bpy.context.window_manager.windows[0]):
                has_bones = any(t[1] for t in targets)

                if has_bones:
                    # Need pose mode — activate the first armature
                    first_arm_name = next((t[0] for t in targets if t[1]), None)
                    if first_arm_name:
                        arm_obj = bpy.data.objects.get(first_arm_name)
                        if arm_obj and arm_obj.type == 'ARMATURE':
                            arm_obj.select_set(True)
                            bpy.context.view_layer.objects.active = arm_obj
                            if bpy.context.mode != 'POSE':
                                bpy.ops.object.mode_set(mode='POSE')
                            bpy.ops.pose.select_all(action='DESELECT')

                    # Select all target bones
                    last_bone = None
                    last_arm = None
                    for obj_name, bone_name in targets:
                        if not bone_name:
                            continue
                        obj = bpy.data.objects.get(obj_name)
                        if not obj or obj.type != 'ARMATURE':
                            continue
                        pose_bone = obj.pose.bones.get(bone_name)
                        if not pose_bone:
                            continue
                        # Ensure bone collection visibility
                        if hasattr(canvas, '_PickerCanvas__ensure_bone_collections_visible'):
                            canvas._PickerCanvas__ensure_bone_collections_visible(obj, bone_name)
                        UT.set_bone_selected(pose_bone, True)
                        last_bone = pose_bone
                        last_arm = obj

                    # Set the last one as active bone
                    if last_bone and last_arm:
                        last_arm.data.bones.active = last_bone.bone
                else:
                    # Plain object selection
                    if bpy.context.mode == 'POSE':
                        bpy.ops.object.mode_set(mode='OBJECT')
                    bpy.ops.object.select_all(action='DESELECT')
                    last_obj = None
                    for obj_name, _ in targets:
                        obj = bpy.data.objects.get(obj_name)
                        if obj:
                            obj.select_set(True)
                            last_obj = obj
                    if last_obj:
                        bpy.context.view_layer.objects.active = last_obj
        except Exception:
            pass
        finally:
            # Release sync lock after a short delay (we're in Qt context)
            if sync_manager:
                QtCore.QTimer.singleShot(100, sync_manager._delayed_unlock)

    def _read_controller_value(self):
        """Read the current Blender property value from the data path.

        Returns:
            float or None: The current value, or None on error.
        """
        path = self._resolve_controller_data_path()
        if not path:
            return None
        try:
            value = eval(path)
            return float(value)
        except Exception as e:
            # Store last error for debugging (visible via Test Path)
            self._controller_last_error = str(e)
            return None

    def _write_controller_value(self, value):
        """Write a value to the Blender property at the data path."""
        path = self._resolve_controller_data_path()
        if not path:
            return
        try:
            exec(f"{path} = {value}")
        except Exception:
            pass

    # -- Omni (2-axis) read / write ----------------------------------------
    def _read_controller_xy(self):
        """Read both X and Y values for an omni controller.

        Returns:
            tuple(float|None, float|None): (x, y).
        """
        x_val = None
        y_val = None
        path_x = self._resolve_controller_data_path('data_path_x')
        if path_x:
            try:
                x_val = float(eval(path_x))
            except Exception as e:
                self._controller_last_error = str(e)
        path_y = self._resolve_controller_data_path('data_path_y')
        if path_y:
            try:
                y_val = float(eval(path_y))
            except Exception as e:
                self._controller_last_error = str(e)
        return x_val, y_val

    def _write_controller_xy(self, x_value, y_value):
        """Write X and Y values to the omni controller properties."""
        path_x = self._resolve_controller_data_path('data_path_x')
        if path_x:
            try:
                exec(f"{path_x} = {x_value}")
            except Exception:
                pass
        path_y = self._resolve_controller_data_path('data_path_y')
        if path_y:
            try:
                exec(f"{path_y} = {y_value}")
            except Exception:
                pass

    def _start_controller_sync(self):
        """Start the polling timer for Blender → picker sync."""
        if self._controller_sync_timer is not None:
            return
        # Read initial value(s)
        if self.controller_data.get('field_type') == 'omni':
            x_val, y_val = self._read_controller_xy()
            if x_val is not None:
                self._controller_value = x_val
            if y_val is not None:
                self._controller_value_y = y_val
        else:
            val = self._read_controller_value()
            if val is not None:
                self._controller_value = val
        self._controller_sync_timer = QTimer()
        self._controller_sync_timer.setInterval(100)
        self._controller_sync_timer.timeout.connect(self._poll_controller_value)
        self._controller_sync_timer.start()

    def _stop_controller_sync(self):
        """Stop the polling timer."""
        if self._controller_sync_timer is not None:
            self._controller_sync_timer.stop()
            self._controller_sync_timer.deleteLater()
            self._controller_sync_timer = None

    def _poll_controller_value(self):
        """Poll the Blender property and update if changed."""
        if self._controller_dragging:
            return  # Don't poll during drag
        if self.controller_data.get('field_type') == 'omni':
            x_val, y_val = self._read_controller_xy()
            changed = False
            if x_val is not None and abs(x_val - self._controller_value) > 1e-8:
                self._controller_value = x_val
                changed = True
            if y_val is not None and abs(y_val - self._controller_value_y) > 1e-8:
                self._controller_value_y = y_val
                changed = True
            if changed:
                self.controller_pixmap = None
                canvas = self.parent()
                if canvas:
                    canvas.update()
            return
        val = self._read_controller_value()
        if val is not None and abs(val - self._controller_value) > 1e-8:
            self._controller_value = val
            self.controller_pixmap = None  # Invalidate pixmap cache
            canvas = self.parent()
            if canvas:
                canvas.update()

    def show_controller_manager(self):
        """Open the Controller Manager popup dialog for this button."""
        from .pb_controller_manager import ControllerManagerDialog
        dialog = ControllerManagerDialog(self, parent=self.window())
        dialog.exec()

    def _reset_controller_value(self):
        """Reset controller value to its default for this and all selected controller buttons."""
        canvas = self.parent()
        buttons_to_reset = [self]
        if canvas:
            for btn in canvas.get_selected_buttons():
                if btn.mode == 'controller' and btn is not self:
                    buttons_to_reset.append(btn)
        for btn in buttons_to_reset:
            cd = btn.controller_data
            if cd.get('field_type') == 'omni':
                default_x = cd.get('default_value_x', 0.0)
                default_y = cd.get('default_value_y', 0.0)
                btn._controller_value = default_x
                btn._controller_value_y = default_y
                btn._write_controller_xy(default_x, default_y)
            else:
                default_val = cd.get('default_value', 0.0)
                btn._controller_value = default_val
                btn._write_controller_value(default_val)
            btn.controller_pixmap = None
        if canvas:
            canvas.update()

    def _show_controller_input_overlay(self, apply_to_selected=False):
        """Show a temporary QLineEdit overlay for typing a controller value.

        Args:
            apply_to_selected: If True, apply the typed value to all selected
                controller buttons (Shift+double-click behaviour).
        """
        canvas = self.parent()
        if not canvas:
            return

        self._controller_input_active = True

        # Compute position in canvas pixel coords
        center = canvas.scene_to_canvas_coords(self.scene_position)
        w_px = self.width * canvas.zoom_factor
        h_px = self.height * canvas.zoom_factor

        edit = QtWidgets.QLineEdit(canvas)
        cd = self.controller_data
        precision = cd.get('precision', 2)
        edit.setText(f"{self._controller_value:.{precision}f}")
        edit.setAlignment(QtCore.Qt.AlignCenter)
        edit.setStyleSheet(
            "QLineEdit { background: #282828; color: white; border: 1px solid #555; "
            "border-radius: 3px; padding: 2px; font-size: 12px; }"
        )
        edit_w = max(60, int(w_px * 0.88))
        edit_h = min(24, int(h_px * 0.45))
        edit.setFixedSize(edit_w, edit_h)
        # Position at the control area of the button
        edit.move(
            int(center.x() - edit_w / 2),
            int(center.y() + h_px * 0.05)
        )
        edit.show()
        edit.setFocus()
        edit.selectAll()

        # Gather target buttons
        target_buttons = [self]
        if apply_to_selected:
            for btn in canvas.get_selected_buttons():
                if btn.mode == 'controller' and btn is not self:
                    target_buttons.append(btn)

        def _commit():
            self._controller_input_active = False
            try:
                typed_val = float(edit.text())
                for btn in target_buttons:
                    bcd = btn.controller_data
                    b_min = bcd.get('min_value', 0.0)
                    b_max = bcd.get('max_value', 1.0)
                    val = max(b_min, min(b_max, typed_val))
                    btn._controller_value = val
                    btn._write_controller_value(val)
                    btn.controller_pixmap = None
                canvas.update()
            except ValueError:
                pass
            edit.deleteLater()
            UT.blender_main_window()

        def _cancel():
            self._controller_input_active = False
            edit.deleteLater()
            UT.blender_main_window()

        edit.returnPressed.connect(_commit)
        edit.editingFinished.connect(_commit)

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
        elif self.mode == 'controller':
            pixmap_missing = self.controller_pixmap is None
        else:
            pixmap_missing = self.text_pixmap is None

        zoom_changed = abs(self.last_zoom_factor - zoom_factor) > 0.1
        size_changed = self.last_size != current_size
        radius_changed = self.last_radius != current_radius
        text_changed = self.last_text != current_text

        # Controller mode also invalidates when value changes
        if self.mode == 'controller':
            last_cv = getattr(self, '_last_controller_value', None)
            if last_cv is None or abs(last_cv - self._controller_value) > 1e-8:
                return True
            if self.controller_data.get('field_type') == 'omni':
                last_cv_y = getattr(self, '_last_controller_value_y', None)
                if last_cv_y is None or abs(last_cv_y - self._controller_value_y) > 1e-8:
                    return True

        return pixmap_missing or zoom_changed or size_changed or radius_changed or text_changed
    
    # --- Static pens/brushes shared by all buttons (allocated once) ---
    _PEN_NONE = QtCore.Qt.NoPen
    _PEN_SEL_EDIT = None    # lazy-init in paint_on_canvas
    _PEN_SEL_NORMAL = None
    _PEN_POSE_DRAG = None
    _BRUSH_SELECTED = None

    @classmethod
    def _ensure_static_pens(cls):
        """One-time creation of static pens/brushes used by every button."""
        if cls._PEN_SEL_EDIT is not None:
            return
        pen = QtGui.QPen(QtGui.QColor(255, 255, 255, 200), 1.5)
        pen.setCosmetic(True)
        cls._PEN_SEL_EDIT = pen
        pen = QtGui.QPen(QtGui.QColor(255, 255, 255, 120), 1)
        pen.setCosmetic(True)
        cls._PEN_SEL_NORMAL = pen
        pen = QtGui.QPen(QtGui.QColor(57, 180, 225, 255), 2)
        pen.setCosmetic(True)
        cls._PEN_POSE_DRAG = pen
        cls._BRUSH_SELECTED = QtGui.QBrush(QtGui.QColor(255, 255, 255, 120))

    def _get_scene_path(self, w, h):
        """Return cached QPainterPath for the button shape in scene space.
        Rebuilds only when dimensions, radii, or shape type change."""
        radii_key = tuple(self.radius) if isinstance(self.radius, (list, tuple)) else self.radius
        key = (w, h, radii_key, self.shape_type,
               self.svg_path_data if self.shape_type == 'custom_path' else None)
        if self._cached_scene_path_key == key and self._cached_scene_path is not None:
            return self._cached_scene_path
        content_rect = QtCore.QRectF(-w / 2, -h / 2, w, h)
        self._cached_scene_path = self._create_button_path_scene(content_rect, self.radius)
        self._cached_scene_path_key = key
        return self._cached_scene_path

    def _get_normal_brush(self):
        """Return cached QBrush for the button's normal color."""
        if self._brush_color_key != self.color or self._brush_normal is None:
            self._brush_normal = QtGui.QBrush(QtGui.QColor(self.color))
            self._brush_color_key = self.color
        return self._brush_normal

    def paint_on_canvas(self, painter, zoom_factor, hover_button=None):
        """Paint this button directly on the canvas painter in scene-space coordinates.

        The painter should already be in scene space (translated to canvas center
        + pan_offset, and scaled by zoom_factor). This avoids QWidget overhead
        and integer-rounding jitter by painting at floating-point precision.
        """
        self._ensure_static_pens()

        painter.save()
        painter.setRenderHint(QtGui.QPainter.Antialiasing)
        painter.setRenderHint(QtGui.QPainter.SmoothPixmapTransform)

        # Move to button center in scene space
        painter.translate(self._scene_position.x(), self._scene_position.y())

        # Rotate if needed
        if self.rotation != 0:
            painter.rotate(self.rotation)

        w, h = self.width, self.height

        # Hover is determined by identity check against the canvas's single
        # hover reference — not a per-button flag that can get out of sync.
        is_hovered = (hover_button is self) and self.selectable

        # --- Background fill (cached brushes where possible) ---
        if self.mode == 'controller':
            # Controller mode: always transparent frame, only slider track visible
            painter.setBrush(QtCore.Qt.transparent)
        elif not self.is_selected:
            if is_hovered:
                hover_color = UT.rgba_value(self.color, 1.4, alpha=1)
                painter.setBrush(QtGui.QColor(hover_color))
            else:
                painter.setBrush(self._get_normal_brush())
        else:
            if self.edit_mode:
                painter.setBrush(self._get_normal_brush())
            else:
                painter.setBrush(self._BRUSH_SELECTED)

        # Opacity
        if self.edit_mode and self.mode != 'pose':
            painter.setOpacity(max(0.2, self.opacity))
        else:
            painter.setOpacity(self.opacity)
        painter.setPen(self._PEN_NONE)

        # Cached button path in scene space
        path = self._get_scene_path(w, h)
        painter.drawPath(path)

        # --- Pose drag border ---
        if self.pose_dragging:
            painter.setBrush(QtCore.Qt.NoBrush)
            painter.setPen(self._PEN_POSE_DRAG)
            painter.drawPath(path)

        # --- Selection border ---
        elif self.is_selected:
            painter.setBrush(QtCore.Qt.NoBrush)
            painter.setPen(self._PEN_SEL_EDIT if self.edit_mode else self._PEN_SEL_NORMAL)
            painter.drawPath(path)

        # --- Text/thumbnail pixmap ---
        painter.setOpacity(1.0)

        # Check/update pixmap cache (pixmaps are rendered at pixel resolution)
        pixel_w = max(1, int(w * zoom_factor + 0.5))
        pixel_h = max(1, int(h * zoom_factor + 0.5))
        content_size = QtCore.QSize(pixel_w, pixel_h)
        current_text = self.label

        if self._should_update_pixmaps(zoom_factor, content_size, self.radius, current_text):
            self.last_zoom_factor = zoom_factor
            self.last_size = content_size
            self.last_radius = self.radius
            self.last_text = current_text
            if self.mode == 'controller':
                self._last_controller_value = self._controller_value
                self._last_controller_value_y = self._controller_value_y
            if self.mode == 'pose':
                self.pose_pixmap = self._render_pose_pixmap(content_size, zoom_factor)
                self.text_pixmap = QtGui.QPixmap(content_size)
                self.text_pixmap.fill(QtCore.Qt.transparent)
            elif self.mode == 'controller':
                self.controller_pixmap = self._render_controller_pixmap(content_size, zoom_factor)
            else:
                self.text_pixmap = self._render_text_pixmap(content_size, zoom_factor)

        # Draw pixmap into scene-space rect (painter zoom handles screen mapping)
        if self.mode == 'pose':
            pixmap = self.pose_pixmap
        elif self.mode == 'controller':
            pixmap = self.controller_pixmap
        else:
            pixmap = self.text_pixmap
        if pixmap and not pixmap.isNull():
            target = QtCore.QRectF(-w / 2, -h / 2, w, h)
            painter.drawPixmap(target, pixmap, QtCore.QRectF(pixmap.rect()))

        painter.restore()

    def paint_ghost_on_canvas(self, painter, scene_pos):
        """Paint a translucent ghost copy at the given scene position.

        Used during duplication drag to show where buttons will be placed.
        Draws the button shape with its color at reduced opacity — no pixmap/text.
        """
        painter.save()
        painter.setRenderHint(QtGui.QPainter.Antialiasing)
        painter.translate(scene_pos.x(), scene_pos.y())
        if self.rotation != 0:
            painter.rotate(self.rotation)

        w, h = self.width, self.height
        content_rect = QtCore.QRectF(-w / 2, -h / 2, w, h)

        # Semi-transparent fill with button color
        color = QtGui.QColor(self.color)
        color.setAlpha(100)
        painter.setBrush(color)
        painter.setPen(QtCore.Qt.NoPen)

        path = self._create_button_path_scene(content_rect, self.radius)
        painter.drawPath(path)

        # Dashed outline for clarity
        outline_color = QtGui.QColor(255, 255, 255, 160)
        pen = QtGui.QPen(outline_color, 1.5)
        pen.setCosmetic(True)
        pen.setStyle(QtCore.Qt.DashLine)
        painter.setPen(pen)
        painter.setBrush(QtCore.Qt.NoBrush)
        painter.drawPath(path)

        # Draw label text if present
        if self.label and self.mode != 'pose':
            painter.setPen(QtGui.QColor(255, 255, 255, 180))
            font = painter.font()
            # Scale font size to scene units (approximate match to button rendering)
            font_size = max(1.0, min(h * 0.35, w * 0.15))
            font.setPointSizeF(font_size)
            painter.setFont(font)
            painter.drawText(content_rect, QtCore.Qt.AlignCenter, self.label)

        painter.restore()

    def paintEvent(self, event):
        """Paint the button with background, selection border, and text/thumbnail.

        Args:
            event (QPaintEvent): The paint event
        """
        # In canvas-painted mode, no visual drawing — canvas handles rendering.
        # No mask generation — hit-testing is done mathematically via _point_in_shape.
        if self._canvas_painted:
            return

        painter = QtGui.QPainter(self)
        painter.setRenderHint(QtGui.QPainter.Antialiasing)
        painter.setRenderHint(QtGui.QPainter.SmoothPixmapTransform)

        # Get the current zoom factor from the parent canvas
        zoom_factor = self.parent().zoom_factor if self.parent() else 1.0

        # Apply rotation transform around widget center
        if self.rotation != 0:
            center = self.rect().center()
            painter.translate(center)
            painter.rotate(self.rotation)

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
        # Use content rect (centered at origin when rotated, inset rect when not)
        rect = self._content_rect_for_paint(zoom_factor)
        path = self._create_button_path(rect, self.radius, zoom_factor)
        painter.drawPath(path)



        # Draw simple green border during pose dragging
        if hasattr(self, 'pose_dragging') and self.pose_dragging:
            painter.setBrush(QtCore.Qt.NoBrush)
            pen = QtGui.QPen(QtGui.QColor(57, 180, 225, 255), 2)
            pen.setCosmetic(True)
            painter.setPen(pen)
            painter.drawPath(path)

        # Draw selection border if selected
        elif self.is_selected:
            painter.setBrush(QtCore.Qt.NoBrush)
            if self.edit_mode:
                pen = QtGui.QPen(QtGui.QColor(255, 255, 255, 200), 1.5)
            else:
                pen = QtGui.QPen(QtGui.QColor(255, 255, 255, 120), 1)
            pen.setCosmetic(True)
            painter.setPen(pen)
            # Inset the outline slightly so it sits cleanly inside the fill edge
            stroker = QtGui.QPainterPathStroker()
            stroker.setWidth(1.5 if self.edit_mode else 0.8)
            inset_path = stroker.createStroke(path)
            painter.drawPath(inset_path)

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
            self.last_mask_rotation = self.rotation
            
            # Generate new mask
            self.cached_mask = self._generate_mask(zoom_factor)
            
            # Apply the cached mask
            if self.cached_mask:
                self.setMask(self.cached_mask)

        # Check if pixmaps need to be updated
        # Use content size (not envelope) for pixmap rendering
        content_size = self._content_size_for_pixmap(zoom_factor)
        current_radius = self.radius
        current_text = self.label
        if self._should_update_pixmaps(zoom_factor, content_size, current_radius, current_text):
            self.last_zoom_factor = zoom_factor
            self.last_size = content_size
            self.last_radius = current_radius
            self.last_text = current_text

            # Render appropriate pixmap based on mode
            if self.mode == 'controller':
                self._last_controller_value = self._controller_value
                self._last_controller_value_y = self._controller_value_y
            if self.mode == 'pose':
                self.pose_pixmap = self._render_pose_pixmap(content_size, zoom_factor)
                self.text_pixmap = QtGui.QPixmap(content_size)
                self.text_pixmap.fill(QtCore.Qt.transparent)
            elif self.mode == 'controller':
                self.controller_pixmap = self._render_controller_pixmap(content_size, zoom_factor)
            else:
                self.text_pixmap = self._render_text_pixmap(content_size, zoom_factor)

        # Draw the appropriate pixmap
        # When rotated, painter is already translated/rotated, so draw centered
        if self.rotation != 0:
            px_x = -content_size.width() / 2
            px_y = -content_size.height() / 2
        else:
            px_x, px_y = 0, 0

        if self.mode == 'pose':
            if self.pose_pixmap and not self.pose_pixmap.isNull():
                painter.drawPixmap(QtCore.QPointF(px_x, px_y), self.pose_pixmap)
        elif self.mode == 'controller':
            if self.controller_pixmap and not self.controller_pixmap.isNull():
                painter.drawPixmap(QtCore.QPointF(px_x, px_y), self.controller_pixmap)
        else:
            if self.text_pixmap and not self.text_pixmap.isNull():
                painter.drawPixmap(QtCore.QPointF(px_x, px_y), self.text_pixmap)
    #---------------------------------------------------------------------------------------
    def _create_button_path(self, rect, radii, zoom_factor):
        """Create button path based on shape type"""
        if self.shape_type == 'custom_path' and self.svg_path_data:
            return self._create_svg_path(rect, zoom_factor)
        else:
            return self._create_rounded_rect_path(rect, radii, zoom_factor)

    def _create_button_path_scene(self, rect, radii):
        """Create button path in scene coordinates (no zoom scaling on radii).
        Used by paint_on_canvas where the painter is already scaled by zoom."""
        if self.shape_type == 'custom_path' and self.svg_path_data:
            return self._create_svg_path(rect, 1.0)
        path = QtGui.QPainterPath()
        scale = 0.95
        tl, tr, br, bl = [r * scale for r in radii]
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
            
            # Use uniform scaling to maintain aspect ratio - no padding for accurate curve editing
            scale = min(scale_x, scale_y)
            
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

        # In canvas-painted mode, the widget is the full envelope (no mask).
        # Transform point into content space and test against content-sized path.
        if self._canvas_painted:
            return self._point_in_shape(point, zoom_factor)

        # Create the button path using the same method as in paintEvent
        # Use fixed 1px inset to match paintEvent for consistent hit detection
        rect = self.rect().adjusted(1, 1, -1, -1)
        path = self._create_button_path(rect, self.radius, zoom_factor)

        # Check if the point is within the path
        return path.contains(point)

    def _point_in_shape(self, local_pos, zoom_factor=None):
        """Math-based shape hit-test for canvas-painted mode (no mask needed).

        Converts the widget-local point to scene space and delegates to
        hit_test_scene, which uses the exact same path as paint_on_canvas.
        """
        if zoom_factor is None:
            zoom_factor = self.parent().zoom_factor if self.parent() else 1.0

        # Widget pixel center
        sz = self.size()
        cx = sz.width() / 2.0
        cy = sz.height() / 2.0

        # Convert widget-local point to scene offset from button center
        dx = (local_pos.x() - cx) / zoom_factor
        dy = (local_pos.y() - cy) / zoom_factor

        # Build scene point and delegate
        scene_pt = QtCore.QPointF(
            self._scene_position.x() + dx,
            self._scene_position.y() + dy
        )
        return self.hit_test_scene(scene_pt)

    def hit_test_scene(self, scene_point):
        """Test if a point in scene coordinates is inside this button's shape.

        Uses the exact same path construction as paint_on_canvas, so the
        clickable area always matches the visible shape perfectly.
        """
        # Offset from button center in scene space
        dx = scene_point.x() - self._scene_position.x()
        dy = scene_point.y() - self._scene_position.y()

        # Un-rotate into button-local scene coords
        if self.rotation != 0:
            rad = math.radians(-self.rotation)
            cos_a, sin_a = math.cos(rad), math.sin(rad)
            dx, dy = dx * cos_a - dy * sin_a, dx * sin_a + dy * cos_a

        # Test against the cached scene-space content path (same as paint_on_canvas)
        path = self._get_scene_path(self.width, self.height)
        return path.contains(QtCore.QPointF(dx, dy))

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
            
            # Use uniform scaling to maintain aspect ratio - no padding for accurate curve editing
            scale = min(scale_x, scale_y)
            
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
        zoom_threshold = 0.1  # Match pixmap threshold to avoid mask/pixmap desync
        size_threshold = 2    # Pixels threshold for size changes

        zoom_changed = abs(self.last_mask_zoom_factor - zoom_factor) > zoom_threshold
        size_changed = (self.last_mask_size is None or
                    abs(self.last_mask_size.width() - current_size.width()) > size_threshold or
                    abs(self.last_mask_size.height() - current_size.height()) > size_threshold)
        radius_changed = self.last_mask_radius != current_radius
        shape_changed = self.last_mask_shape_type != current_shape_type
        svg_data_changed = self.last_mask_svg_data != current_svg_data
        rotation_changed = getattr(self, 'last_mask_rotation', None) != self.rotation

        return mask_missing or zoom_changed or size_changed or radius_changed or shape_changed or svg_data_changed or rotation_changed

    def _generate_mask(self, zoom_factor):
        """Generate smooth mask using high-resolution rendering"""
        if not self.isVisible():
            return None

        rect = self.rect()

        try:
            # Create high-resolution pixmap for smooth mask edges
            scale_factor = 2
            high_res_size = rect.size() * scale_factor
            pixmap = QtGui.QPixmap(high_res_size)
            pixmap.fill(QtCore.Qt.transparent)

            painter = QtGui.QPainter(pixmap)
            painter.setRenderHint(QtGui.QPainter.Antialiasing, True)
            painter.setRenderHint(QtGui.QPainter.SmoothPixmapTransform, True)

            # Scale the painter to high resolution
            painter.scale(scale_factor, scale_factor)

            if self.rotation != 0:
                # Rotate around widget center, draw content rect centered
                cx, cy = rect.width() / 2, rect.height() / 2
                painter.translate(cx, cy)
                painter.rotate(self.rotation)
                cw = self.width * zoom_factor
                ch = self.height * zoom_factor
                content_rect = QtCore.QRectF(-cw / 2, -ch / 2, cw, ch)
            else:
                content_rect = QtCore.QRectF(0, 0, rect.width(), rect.height())

            # Create and fill path
            path = self._create_button_path(content_rect, self.radius, zoom_factor)
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
        self.last_mask_rotation = None
    #---------------------------------------------------------------------------------------
    def start_pose_drag(self, event):
        """Start a pose drag operation for gradual pose application"""
        if not self._validate_pose_data():
            print("No valid pose data found")
            return
        
        # Check if pose data actually exists
        if not hasattr(self, 'pose_data') or not self.pose_data or not self.pose_data.get("default"):
            print("No pose data available for gradual application")
            return
            
        self.pose_dragging = True
        self.pose_drag_start_pos = event.globalPos()
        self.current_pose_stage = 0
        
        # Pre-calculate all staged poses
        try:
            self.staged_poses = self._create_staged_poses()
        except Exception as e:
            print(f"Error creating staged poses: {e}")
            self.pose_dragging = False
            return
        
        if not self.staged_poses:
            self.pose_dragging = False
            print("No staged poses created")
            return
        
        print(f"Started pose drag with {len(self.staged_poses)} staged poses")
        
        # Force pixmap regeneration to show stage counter
        self.last_text = None
        self.update()

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

        # Store scene positions of all selected buttons relative to the drag origin
        drag_scene_pos = self._scene_position
        self._dup_ghost_offsets = []
        for btn in selected_buttons:
            offset = QtCore.QPointF(
                btn._scene_position.x() - drag_scene_pos.x(),
                btn._scene_position.y() - drag_scene_pos.y()
            )
            self._dup_ghost_offsets.append((btn, offset))

        # Store offset from dragged button to group bbox center so paste lands
        # where the ghost preview shows (paste uses group center as origin)
        min_x = min(btn.scene_position.x() for btn in selected_buttons)
        max_x = max(btn.scene_position.x() for btn in selected_buttons)
        min_y = min(btn.scene_position.y() for btn in selected_buttons)
        max_y = max(btn.scene_position.y() for btn in selected_buttons)
        group_center = QtCore.QPointF((min_x + max_x) / 2, (min_y + max_y) / 2)
        self._dup_group_center_offset = group_center - drag_scene_pos

        # Change cursor to indicate duplication
        if self._canvas_painted and canvas:
            canvas.setCursor(QtCore.Qt.DragCopyCursor)
        else:
            self.setCursor(QtCore.Qt.DragCopyCursor)
        
        #print(f"Started duplication drag with {len(selected_buttons)} buttons")

    def handle_pose_drag(self, event):
        """Update the pose drag operation to apply staged poses"""
        if not self.pose_dragging or not self.pose_drag_start_pos or not self.staged_poses:
            return
            

            
        # Calculate the horizontal drag distance
        delta_x = event.globalPos().x() - self.pose_drag_start_pos.x()
        
        # Convert drag distance to stage (100 pixels = 10 stages)
        # Negative values (dragging left) should give stage 0, positive (right) should give up to stage 10
        drag_sensitivity = 100.0  # pixels for all 10 stages
        stage_float = max(0.0, min(10.0, delta_x / drag_sensitivity * 10))
        new_stage = int(stage_float)
        
        # Only apply if stage changed
        if new_stage != self.current_pose_stage:
            self.current_pose_stage = new_stage
            
            # Apply the staged pose - with error handling
            try:
                self._apply_staged_pose(new_stage)
            except Exception as e:
                print(f"Error during pose drag at stage {new_stage}: {e}")
                # Stop pose dragging on error to prevent further crashes
                self.pose_dragging = False
                return
            
            # Just print to console for debugging
            print(f"Applied stage {new_stage}/10")
            
            # Force pixmap regeneration to update the stage text
            self.last_text = None  # This will force pixmap regeneration
            self.update()

    def handle_duplication_drag(self, event):
        """Handle the visual feedback during duplication drag"""
        canvas = self.parent()
        if not canvas:
            return
        # Calculate scene-space delta from drag start
        delta = event.globalPos() - self.drag_start_pos
        scene_delta = QtCore.QPointF(delta.x(), delta.y()) / canvas.zoom_factor
        # Store current ghost center for paintEvent
        self._dup_ghost_scene_center = QtCore.QPointF(
            self._scene_position.x() + scene_delta.x(),
            self._scene_position.y() + scene_delta.y()
        )
        canvas.update()

    def complete_pose_drag(self, event):
        """Complete the pose drag operation"""
        try:
            self.pose_dragging = False
            self.pose_drag_start_pos = None
            
            # Show final stage in console for feedback
            if hasattr(self, 'current_pose_stage'):
                print(f"Pose applied at stage {self.current_pose_stage}/10")
            
            # Force pixmap regeneration to restore normal label
            self.last_text = None
            self.update()
            
        except Exception as e:
            print(f"Error completing pose drag: {e}")
        finally:
            # Always clear the staged poses
            self.staged_poses = []
            self.current_pose_stage = 0
            self.pose_dragging = False
            
    def cancel_pose_drag(self):
        """Cancel pose dragging and reset to original state"""
        if not self.pose_dragging:
            return
            
        try:
            # Reset to stage 0 (original state)
            if self.staged_poses:
                self._apply_staged_pose(0)
            
            self.pose_dragging = False
            self.pose_drag_start_pos = None
            self.current_pose_stage = 0
            
            print("Pose drag cancelled")
            
            # Force pixmap regeneration to restore normal label
            self.last_text = None
            self.update()
            
        except Exception as e:
            print(f"Error cancelling pose drag: {e}")
        finally:
            # Always clean up
            self.staged_poses = []
            self.current_pose_stage = 0
            self.pose_dragging = False

    def complete_duplication_drag(self, event):
        """Complete the duplication drag operation"""
        canvas = self.parent()
        if not canvas:
            return

        try:
            # Compute drop scene position that matches the ghost preview.
            # Ghost center = dragged button scene pos + mouse delta in scene space.
            # paste_buttons_at_position expects the group bbox center, so offset
            # from the dragged button position by the stored group center offset.
            delta = event.globalPos() - self.drag_start_pos
            scene_delta = QtCore.QPointF(delta.x(), delta.y()) / canvas.zoom_factor
            ghost_center = QtCore.QPointF(
                self._scene_position.x() + scene_delta.x(),
                self._scene_position.y() + scene_delta.y()
            )
            group_offset = getattr(self, '_dup_group_center_offset', QtCore.QPointF(0, 0))
            paste_scene_pos = ghost_center + group_offset

            # Reset duplication state and ghost visuals
            self.duplicating = False
            self._dup_ghost_offsets = []
            self._dup_ghost_scene_center = None
            self._dup_group_center_offset = None
            self.update_cursor()

            # Paste at the computed scene position so buttons land where the ghost showed
            canvas.paste_buttons_at_position(paste_scene_pos, mirror=False, is_scene_coords=True)
            
            #print("Duplication completed successfully")
            
        except Exception as e:
            print(f"Error during duplication completion: {e}")
            # Reset state on error
            self.duplicating = False
            self._dup_ghost_offsets = []
            self._dup_ghost_scene_center = None
            self._dup_group_center_offset = None
            self.update_cursor()
    #---------------------------------------------------------------------------------------
    def update_cursor(self):
        """Updated cursor handling with duplication support"""
        if hasattr(self, 'duplicating') and self.duplicating:
            cursor = QtCore.Qt.DragCopyCursor
        elif self.edit_mode:
            cursor = QtCore.Qt.OpenHandCursor
        else:
            cursor = QtCore.Qt.ArrowCursor
        self.setCursor(cursor)
        # In canvas-painted mode, also set cursor on parent canvas
        if self._canvas_painted and self.parent():
            self.parent().setCursor(cursor)
    
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
        # Animation info (if animation button)
        if self.is_animation:
            anim = self.animation_data
            bone_count = sum(len(a.get('bones', {})) for a in anim.get('armatures', {}).values())
            anim_label = QtWidgets.QLabel(
                f"Animation: {anim.get('frame_count', 0)} frames \u00b7 {bone_count} bone{'s' if bone_count != 1 else ''}"
            )
            anim_label.setStyleSheet("color: #ffa000; font-size: 10px; border:none; background-color: transparent;")
            self.tooltip_widget.add_widget(anim_label)
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
                    button.height = button.width * 1.25
                elif button.mode == 'pose' and mode != 'pose' and hasattr(button, '_original_height'):
                    button.height = button._original_height

                # Controller mode: ensure minimum height for slider visibility
                if mode == 'controller':
                    button.height = max(button.height, 40)
                    button._start_controller_sync()
                elif button.mode == 'controller':
                    button._stop_controller_sync()

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
            if mode == 'pose' and self.mode != 'pose':
                self._original_height = self.height
                self.height = self.width * 1.25
            elif self.mode == 'pose' and mode != 'pose' and hasattr(self, '_original_height'):
                self.height = self._original_height

            if mode == 'controller':
                self.height = max(self.height, 40)
                self._start_controller_sync()
            elif self.mode == 'controller':
                self._stop_controller_sync()

            self.mode = mode
            self.update()
            self.changed.emit(self)
            canvas.update_button_positions()

        self.pose_pixmap = None
        self.controller_pixmap = None
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
        # Notify canvas so tooltip is suppressed and canvas context menu won't fire
        canvas = self.parent()
        if canvas:
            canvas._hide_button_tooltip()
            canvas._context_menu_open = True

        menu = UT.create_styled_menu()

        # Mode selection
        mode_menu = UT.create_styled_menu(title="Mode")
        
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

        controller_action = QtGui.QAction(QtGui.QIcon(UT.get_icon("preference_icon.png", size=20)), "Controller Mode", self)
        controller_action.setCheckable(True)
        controller_action.setChecked(self.mode == 'controller')
        controller_action.triggered.connect(lambda: self.set_mode('controller'))

        mode_group = QtGui.QActionGroup(self)
        mode_group.addAction(select_action)
        mode_group.addAction(script_action)
        mode_group.addAction(pose_action)
        mode_group.addAction(controller_action)

        mode_menu.addAction(select_action)
        mode_menu.addAction(script_action)
        mode_menu.addAction(pose_action)
        mode_menu.addAction(controller_action)
        
        
        # Copy, Paste and Delete Actions
        #---------------------------------------------------------------------------------------
        if self.edit_mode:
            # Add thumbnail options for pose mode buttons
            if self.mode == 'pose':
                thumbnail_menu = UT.create_styled_menu(parent=menu, title="Thumbnail")
                thumbnail_menu.setIcon(QtGui.QIcon(UT.get_icon('image.png')))

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

            # Controller Manager action for controller mode buttons
            if self.mode == 'controller':
                controller_manager_action = menu.addAction(QtGui.QIcon(UT.get_icon('preference_icon.png', size=20)), "Controller Manager")
                controller_manager_action.triggered.connect(self.show_controller_manager)

            #---------------------------------------------------------------------------------------
            # Button placement submenu
            placement_menu = UT.create_styled_menu(parent=menu, title="Placement")
            placement_menu.setIcon(QtGui.QIcon(UT.get_icon("align_left.png")))
            
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
            align_left_btn = create_alignment_button("align_left.png", "Align Left", self.parent().align_button_left)
            align_center_btn = create_alignment_button("align_vCenter.png", "Align Vertical Center", self.parent().align_button_center)
            align_right_btn = create_alignment_button("align_right.png", "Align Right", self.parent().align_button_right)
            v_space_btn = create_alignment_button("v_spacing.png", "Distribute Evenly (Vertical)", self.parent().evenly_space_vertical)
            
            # Row 2: Horizontal alignment options
            align_top_btn = create_alignment_button("align_top.png", "Align Top", self.parent().align_button_top)
            align_middle_btn = create_alignment_button("align_hCenter.png", "Align Horizontal Center", self.parent().align_button_middle)
            align_bottom_btn = create_alignment_button("align_bottom.png", "Align Bottom", self.parent().align_button_bottom)
            h_space_btn = create_alignment_button("h_spacing.png", "Distribute Evenly (Horizontal)", self.parent().evenly_space_horizontal)
            
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
            shape_menu = UT.create_styled_menu(parent=menu, title="Shape")
            shape_menu.setIcon(QtGui.QIcon(UT.get_icon('shape.png')))
            
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
            
            # Curve editor options - Edit Shape available for all buttons
            edit_shape_action = shape_menu.addAction("Edit Shape")
            edit_shape_action.triggered.connect(lambda: self.parent().start_curve_editing(self))
            
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
            paste_menu = UT.create_styled_menu(parent=menu, title="Paste Options")
            paste_menu.setIcon(QtGui.QIcon(UT.get_icon('paste.png')))
            
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

            duplicate_mirror_action = menu.addAction(QtGui.QIcon(UT.get_icon('paste.png')), "Duplicate Mirror")
            duplicate_mirror_action.setToolTip("Interactively duplicate selected buttons across a draggable mirror axis")
            duplicate_mirror_action.triggered.connect(lambda: self.parent().start_duplicate_mirror_tool())

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

                remove_selected_from_selection_action = menu.addAction(QtGui.QIcon(UT.get_icon('subtract.png')), "Remove Selected From Button")
                remove_selected_from_selection_action.triggered.connect(self.remove_selected_objects_for_selected_buttons)

                remove_all_from_selection_action = menu.addAction(QtGui.QIcon(UT.get_icon('close_01.png')), "Remove all Selection")
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
            elif self.mode == 'controller':
                # Controller Mode menu items
                controller_manager_action = menu.addAction(QtGui.QIcon(UT.get_icon('preference_icon.png', size=20)), "Controller Manager")
                controller_manager_action.triggered.connect(self.show_controller_manager)
                reset_action = menu.addAction(QtGui.QIcon(UT.get_icon('undo.png')), "Reset")
                reset_action.triggered.connect(self._reset_controller_value)
            elif self.mode == 'pose':
                # Pose Mode menu items
                add_pose_action = menu.addAction(QtGui.QIcon(UT.get_icon('add.png')), "Capture Pose")
                add_pose_action.triggered.connect(self.add_pose)

                capture_anim_action = menu.addAction(QtGui.QIcon(UT.get_icon('add.png')), "Capture Animation")
                capture_anim_action.triggered.connect(self.capture_animation_from_selection)

                # Apply Animation submenu (only for animation buttons)
                if self.is_animation:
                    apply_menu = UT.create_styled_menu(title="Apply Animation")

                    replace_action = apply_menu.addAction("Replace (clear range)")
                    replace_action.triggered.connect(lambda: self.apply_animation('replace'))
                    merge_action = apply_menu.addAction("Merge (overwrite at frame)")
                    merge_action.triggered.connect(lambda: self.apply_animation('merge'))
                    add_action = apply_menu.addAction("Add (offset values)")
                    add_action.triggered.connect(lambda: self.apply_animation('add'))
                    menu.addMenu(apply_menu)

                remove_pose_action = menu.addAction(QtGui.QIcon(UT.get_icon('subtract.png')),"Remove Pose")
                remove_pose_action.triggered.connect(self.remove_pose_for_selected_buttons)

                thumbnail_menu = UT.create_styled_menu(title="Thumbnail")
                thumbnail_menu.setIcon(QtGui.QIcon(UT.get_icon('image.png')))
                
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

        # Toggle "Set State" submenu — only when this is a configured toggle
        # button with more than one state. Lets the user jump to a specific
        # state from the right-click menu (no cycling required).
        if (self.mode == 'script'
                and isinstance(self.script_data, dict)
                and self.script_data.get('type') == 'toggle'):
            toggle_data = self.script_data.get('toggle_data') or {}
            state_count = max(1, min(3, int(toggle_data.get('state_count', 2) or 2)))
            if state_count > 1:
                state_labels = list(toggle_data.get('state_labels') or [])
                while len(state_labels) < state_count:
                    state_labels.append(f'State {len(state_labels) + 1}')
                current_state = int(toggle_data.get('current_state', 0) or 0)
                state_menu = UT.create_styled_menu(parent=menu, title="Set State")
                state_group = QtGui.QActionGroup(self)
                for i in range(state_count):
                    label = state_labels[i] or f'State {i + 1}'
                    action = QtGui.QAction(label, self)
                    action.setCheckable(True)
                    action.setChecked(i == current_state)
                    action.triggered.connect(partial(self._set_toggle_state, i))
                    state_group.addAction(action)
                    state_menu.addAction(action)
                menu.addMenu(state_menu)

        menu.addMenu(mode_menu)
        menu.addSeparator()

        menu.exec_(self.mapToGlobal(pos))

        # Reset canvas context menu flag
        if canvas:
            canvas._context_menu_open = False

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
                    button.changed.disconnect()
                    signal_connections[button.unique_id] = True
                except RuntimeError:
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
                        button.rotation = attributes.get('rotation', 0)

                        # Handle pose data if available
                        if 'pose_data' in attributes:
                            button.pose_data = attributes['pose_data'].copy()
                        if 'thumbnail_path' in attributes:
                            button.thumbnail_path = attributes.get('thumbnail_path', '')
                            # Use path resolution for thumbnail loading
                            if button.thumbnail_path:
                                resolved_path = DM.PickerDataManager.resolve_image_path(button.thumbnail_path, current_tab)
                                if resolved_path and os.path.exists(resolved_path):
                                    button.thumbnail_pixmap = QtGui.QPixmap(resolved_path)
                                
                    elif paste_type == 'dimension':
                        # Paste only dimensions
                        button.width = attributes['width']
                        button.height = attributes['height']
                        button.radius = attributes['radius'].copy()
                        button.rotation = attributes.get('rotation', 0)
                        
                    elif paste_type == 'function':
                        # Paste only functionality
                        button.assigned_objects = attributes.get('assigned_objects', []).copy()
                        button.mode = attributes.get('mode', 'select')
                        button.script_data = attributes.get('script_data', {}).copy()
                        
                        if 'pose_data' in attributes:
                            button.pose_data = attributes['pose_data'].copy()
                        if 'thumbnail_path' in attributes:
                            button.thumbnail_path = attributes.get('thumbnail_path', '')
                            # Use path resolution for thumbnail loading
                            if button.thumbnail_path:
                                resolved_path = DM.PickerDataManager.resolve_image_path(button.thumbnail_path, current_tab)
                                if resolved_path and os.path.exists(resolved_path):
                                    button.thumbnail_pixmap = QtGui.QPixmap(resolved_path)
                                
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
    # POSE & ANIMATION MANAGEMENT
    #---------------------------------------------------------------------------------------
    def show_capture_dialog(self):
        """Auto-detect capture: if keyframes are selected in the timeline, capture
        animation; otherwise capture a single-frame pose. No dialog needed."""
        active_obj = TF.active_object()
        if not active_obj:
            self._show_no_selection_dialog("No active object in Blender.")
            return

        if active_obj.type != 'ARMATURE':
            # Non-armature: always single-frame pose
            self.add_pose()
            return

        selected_bones = TF.selected_bones()
        if not selected_bones:
            self._show_no_selection_dialog("Please select bones in Blender first.")
            return

        # Check for selected keyframes in the timeline/dopesheet
        action = active_obj.animation_data.action if active_obj.animation_data else None
        bone_names = set(selected_bones)

        if action:
            frame_start, frame_end, selected_frames = TF.get_selected_keyframe_range(
                action, bone_names
            )
        else:
            frame_start, frame_end, selected_frames = None, None, None

        if selected_frames and len(selected_frames) > 1:
            # Multiple selected keyframes → capture animation
            self._update_assigned_bones_with_namespace(selected_bones)
            anim_data = self.capture_animation_data(
                frame_start, frame_end, selected_frames=selected_frames
            )
            if anim_data:
                self._save_animation_data(anim_data)
            else:
                self._show_no_selection_dialog("No keyframe data found for the selected frames.")
        else:
            # No selected keyframes or only 1 → capture single-frame pose
            self.add_pose()

    def capture_animation_from_selection(self):
        """Show a small dialog with In/Out frame fields, then capture animation."""
        active_obj = TF.active_object()
        if not active_obj:
            self._show_no_selection_dialog("No active object in Blender.")
            return

        if active_obj.type != 'ARMATURE':
            self._show_no_selection_dialog("Active object must be an armature to capture animation.")
            return

        selected_bones = TF.selected_bones()
        if not selected_bones:
            self._show_no_selection_dialog("Please select bones in Blender first.")
            return

        action = active_obj.animation_data.action if active_obj.animation_data else None
        if not action:
            self._show_no_selection_dialog("No action found on the armature. Create keyframes first.")
            return

        # Default to scene frame range
        scene = bpy.context.scene
        default_start = scene.frame_start
        default_end = scene.frame_end

        # Build dialog
        dialog = CD.CustomDialog(self, title="Capture Animation", size=(260, 130))

        # Frame range row
        range_layout = QtWidgets.QHBoxLayout()
        range_layout.setSpacing(8)

        in_label = QtWidgets.QLabel("In:")
        in_label.setStyleSheet("color: #cccccc; font-size: 11px;")
        in_field = CLE.IntegerLineEdit(
            min_value=-10000, max_value=100000, increment=1, precision=0,
            width=70, height=22, label="In"
        )
        in_field.setText(str(int(default_start)))

        out_label = QtWidgets.QLabel("Out:")
        out_label.setStyleSheet("color: #cccccc; font-size: 11px;")
        out_field = CLE.IntegerLineEdit(
            min_value=-10000, max_value=100000, increment=1, precision=0,
            width=70, height=22, label="Out"
        )
        out_field.setText(str(int(default_end)))

        range_layout.addWidget(in_label)
        range_layout.addWidget(in_field)
        range_layout.addStretch()
        range_layout.addWidget(out_label)
        range_layout.addWidget(out_field)

        range_widget = QtWidgets.QWidget()
        range_widget.setLayout(range_layout)
        dialog.add_widget(range_widget)

        # Add Accept / Close buttons
        accept_btn, close_btn = dialog.add_button_box()
        accept_btn.setText("Capture")
        close_btn.setText("Cancel")

        result = dialog.exec_()
        if result != QtWidgets.QDialog.Accepted:
            return

        # Parse frame range
        try:
            frame_start = int(float(in_field.text()))
            frame_end = int(float(out_field.text()))
        except ValueError:
            self._show_no_selection_dialog("Invalid frame range values.")
            return

        if frame_start >= frame_end:
            self._show_no_selection_dialog("In frame must be less than Out frame.")
            return

        self._update_assigned_bones_with_namespace(selected_bones)
        anim_data = self.capture_animation_data(frame_start, frame_end)
        if anim_data:
            self._save_animation_data(anim_data)
            bone_count = sum(len(a.get('bones', {})) for a in anim_data.get('armatures', {}).values())
            print(f"Animation captured: {anim_data.get('frame_count', 0)} frames, {bone_count} bones")
        else:
            self._show_no_selection_dialog("No keyframe data found in the specified frame range.")

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

    def capture_animation_data(self, frame_start, frame_end, selected_frames=None):
        """Capture animation keyframe data from fcurves for assigned bones.

        Args:
            frame_start: Start frame of capture range
            frame_end: End frame of capture range
            selected_frames: Optional set of frame numbers to capture (only these exact frames)
        """
        active_armature = TF.active_object()

        if not active_armature or active_armature.type != 'ARMATURE':
            return None

        action = active_armature.animation_data.action if active_armature.animation_data else None
        if not action:
            return None

        current_namespace = self._get_current_namespace_from_window()
        storage_key = current_namespace if current_namespace else active_armature.name

        # Collect bone names from assigned objects
        bone_names = set()
        for obj_data in self.assigned_objects:
            if obj_data.get('is_bone', False):
                bone_names.add(obj_data['name'])

        if not bone_names:
            return None

        bones_anim_data = TF.read_fcurve_keyframes(
            action, bone_names, frame_start, frame_end,
            selected_frames=selected_frames, armature_obj=active_armature
        )

        if not bones_anim_data:
            return None

        # Add rotation_mode per bone
        for bone_name in bones_anim_data:
            bone = active_armature.pose.bones.get(bone_name)
            if bone:
                bones_anim_data[bone_name]["rotation_mode"] = bone.rotation_mode

        return {
            "type": "animation",
            "version": 1,
            "frame_range": [frame_start, frame_end],
            "frame_count": int(frame_end - frame_start + 1),
            "source_fps": bpy.context.scene.render.fps,
            "armatures": {
                storage_key: {
                    "source_armature": active_armature.name,
                    "bones": bones_anim_data
                }
            }
        }

    def _save_animation_data(self, animation_data):
        """Save captured animation data to the button."""
        self.animation_data = animation_data
        # Clear single-frame pose data since this is now an animation button
        self.pose_data = {}
        self.pose_pixmap = None
        self._tooltip_needs_update = True
        self.changed.emit(self)
        self.update()  # Force repaint to show animation badge

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
        """Remove the pose/animation from the data and clear assigned objects"""
        # Clear both pose and animation data
        self.pose_data = {}
        self.animation_data = {}

        # Also clear assigned objects
        self.assigned_objects = []

        # Invalidate pixmap cache so badge disappears
        self.pose_pixmap = None

        # Update the tooltip to reflect the changes
        self._tooltip_needs_update = True

        # Emit the changed signal
        self.changed.emit(self)
        
    def remove_pose_for_selected_buttons(self):
        """Remove the pose/animation data for selected buttons"""
        for button in self.parent().get_selected_buttons():
            if not button.pose_data and not button.animation_data:
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
        thumbnail_dir = self._get_thumbnail_directory()

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

            # When a session is active, copy into the archive and use bpicker:// path
            store_path = file_path
            session = DM.PickerDataManager.get_active_session()
            if session:
                result = session.add_media_file(file_path, "thumbnails")
                if result:
                    store_path = result  # bpicker://thumbnails/filename.ext

            # Apply the thumbnail to all selected pose buttons
            for button in pose_buttons:
                # Store the image path
                button.thumbnail_path = store_path

                # Load the image into a pixmap
                button.thumbnail_pixmap = test_pixmap

                # Force regeneration of the pose_pixmap by invalidating cache parameters
                button.pose_pixmap = None
                button.last_zoom_factor = 0
                button.last_size = None

                # Update the button
                button.update()
                button.update_tooltip()
                button.changed.emit(button)
    
    def add_thumbnail(self):
        """Take a screenshot and use it as a thumbnail with region selection"""
        import os
        
        # Get selected pose buttons
        pose_buttons = self._get_selected_pose_buttons()
        if not pose_buttons:
            return
        
        # Store pose buttons for later use in callback
        self._pending_pose_buttons = pose_buttons
        self._pending_thumbnail_path = None
        
        # Start the region selection capture process
        self._start_region_capture(is_update=False)

    def _start_region_capture(self, is_update=False):
        """Start the screen region capture process"""
        # Get the top-level window
        top_window = self.window()
        
        # Store update mode flag
        self._capture_is_update = is_update
        
        # Remember window state and hide it
        self._was_visible = top_window.isVisible()
        top_window.hide()
        
        # Process events to ensure window is hidden
        QtCore.QCoreApplication.processEvents()
        
        # Small delay to ensure window is fully hidden before capture
        QtCore.QTimer.singleShot(50, self._show_region_selector)
    
    def _show_region_selector(self):
        """Show the region selector overlay"""
        try:
            # Get all screens for multi-monitor support
            screens = QtGui.QGuiApplication.screens()
            if not screens:
                raise Exception("No screen available for capture")

            # Compute the virtual desktop bounding rect
            virtual_rect = QtCore.QRect()
            for s in screens:
                virtual_rect = virtual_rect.united(s.geometry())

            # Determine DPR (use max across screens for consistency)
            max_dpr = max(s.devicePixelRatio() for s in screens)

            # Create a combined pixmap covering the entire virtual desktop
            combined = QtGui.QPixmap(
                int(virtual_rect.width() * max_dpr),
                int(virtual_rect.height() * max_dpr)
            )
            combined.setDevicePixelRatio(max_dpr)
            combined.fill(QtCore.Qt.black)

            painter = QtGui.QPainter(combined)
            for s in screens:
                geom = s.geometry()
                shot = s.grabWindow(0)
                # Paint at logical offset relative to virtual desktop origin
                x = geom.x() - virtual_rect.x()
                y = geom.y() - virtual_rect.y()
                painter.drawPixmap(x, y, geom.width(), geom.height(), shot)
            painter.end()

            background_pixmap = combined
            screen_geom = virtual_rect

            if background_pixmap.isNull():
                raise Exception("Failed to capture screen")

            # Store the background for later cropping
            self._capture_background = background_pixmap
            self._capture_screen_geometry = screen_geom
            
            # Create and show the region selector
            self._region_selector = ScreenRegionSelector(background_pixmap, screen_geom)
            self._region_selector.region_selected.connect(self._on_region_selected)
            self._region_selector.cancelled.connect(self._on_capture_cancelled)
            
        except Exception as e:
            self._restore_window()
            self._show_thumbnail_error(str(e))
    
    def _on_region_selected(self, rect):
        """Handle the selected region and create the thumbnail"""
        try:
            # Get thumbnail directory and path
            thumbnail_dir = self._get_thumbnail_directory()

            if self._capture_is_update and hasattr(self, '_update_thumbnail_path'):
                thumbnail_path = self._update_thumbnail_path
                # Resolve bpicker:// paths to the actual temp file for saving
                if thumbnail_path.startswith("bpicker://"):
                    session = DM.PickerDataManager.get_active_session()
                    if session:
                        resolved = session.get_media_path(thumbnail_path)
                        if resolved:
                            thumbnail_path = resolved
                        else:
                            # File doesn't exist yet — create in temp dir
                            thumbnail_path = self._generate_unique_thumbnail_path(thumbnail_dir)
            else:
                thumbnail_path = self._generate_unique_thumbnail_path(thumbnail_dir)
            
            # Crop the background image to the selected region
            if hasattr(self, '_capture_background') and self._capture_background:
                # Account for HiDPI/Retina: grabWindow() captures at native pixel
                # resolution, but the selection rect is in logical coordinates.
                dpr = self._capture_background.devicePixelRatio()
                scaled_rect = QtCore.QRect(
                    int(rect.x() * dpr),
                    int(rect.y() * dpr),
                    int(rect.width() * dpr),
                    int(rect.height() * dpr)
                )
                # First crop to the selected rectangle
                selected_image = self._capture_background.toImage().copy(scaled_rect)
                
                # Then crop to a square (center crop)
                cropped_image = self._crop_to_square_from_image(selected_image)
                
                # Save as JPG
                if not cropped_image.save(thumbnail_path, 'JPG', 95):
                    raise Exception("Failed to save thumbnail")
                
                # Convert to pixmap for display
                cropped_pixmap = QtGui.QPixmap.fromImage(cropped_image)
                
                # Apply to buttons
                if self._capture_is_update:
                    # Update existing thumbnails
                    if hasattr(self, '_update_buttons'):
                        self._update_existing_thumbnail(
                            self._update_buttons, 
                            thumbnail_path, 
                            cropped_pixmap
                        )
                else:
                    # Add new thumbnails
                    if hasattr(self, '_pending_pose_buttons'):
                        self._apply_thumbnail_to_buttons(
                            self._pending_pose_buttons, 
                            thumbnail_path, 
                            cropped_pixmap
                        )
            
        except Exception as e:
            self._show_thumbnail_error(str(e))
        finally:
            self._cleanup_capture()
            self._restore_window()
    
    def _crop_to_square_from_image(self, qimage):
        """Crop a QImage to a square (center crop)"""
        width = qimage.width()
        height = qimage.height()
        
        # Use the smaller dimension as the square size
        size = min(width, height)
        
        # Calculate center crop
        x = (width - size) // 2
        y = (height - size) // 2
        
        return qimage.copy(x, y, size, size)
    
    def _on_capture_cancelled(self):
        """Handle capture cancellation"""
        self._cleanup_capture()
        self._restore_window()
    
    def _cleanup_capture(self):
        """Clean up capture-related attributes"""
        if hasattr(self, '_capture_background'):
            del self._capture_background
        if hasattr(self, '_region_selector'):
            del self._region_selector
        if hasattr(self, '_pending_pose_buttons'):
            del self._pending_pose_buttons
        if hasattr(self, '_update_buttons'):
            del self._update_buttons
        if hasattr(self, '_update_thumbnail_path'):
            del self._update_thumbnail_path
    
    def _restore_window(self):
        """Restore the main window visibility"""
        if hasattr(self, '_was_visible') and self._was_visible:
            top_window = self.window()
            if top_window:
                top_window.show()
        QtCore.QCoreApplication.processEvents()

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
            
            # Get all screens for multi-monitor support
            screens = QtGui.QGuiApplication.screens()
            if not screens:
                raise Exception("No screen available for capture")

            # Find the screen the picker window is on, fall back to primary
            target_screen = QtGui.QGuiApplication.primaryScreen()
            window = self.windowHandle()
            if window and window.screen():
                target_screen = window.screen()

            # Capture just the target screen (auto-crop works on a single screen)
            original_pixmap = target_screen.grabWindow(0)

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
        """Get or create the thumbnail directory.

        When a .bpicker session is active, thumbnails are saved directly
        into the session's temp dir so they are packed into the archive.
        """
        # When a session is active, save directly into the archive's thumbnails dir
        session = DM.PickerDataManager.get_active_session()
        if session and session._temp_dir:
            from . import bpicker_format as BPF
            thumbnail_dir = os.path.join(session._temp_dir, BPF.THUMBNAILS_DIR)
            os.makedirs(thumbnail_dir, exist_ok=True)
            return thumbnail_dir

        # Fallback to default directory
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
        # When a session is active, convert to bpicker:// path for storage
        store_path = thumbnail_path
        session = DM.PickerDataManager.get_active_session()
        if session and session._temp_dir and thumbnail_path.startswith(session._temp_dir):
            from . import bpicker_format as BPF
            rel = os.path.relpath(thumbnail_path, session._temp_dir).replace("\\", "/")
            store_path = f"bpicker://{rel}"

        for button in pose_buttons:
            # Store the image path (bpicker:// when session active, absolute otherwise)
            button.thumbnail_path = store_path
            
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
        """Update existing thumbnail by overwriting the current thumbnail file with region selection"""
        # Get selected pose buttons
        pose_buttons = self._get_selected_pose_buttons()
        if not pose_buttons:
            return
        
        # Check if buttons have existing thumbnails (resolve bpicker:// paths first)
        buttons_with_thumbnails = []
        for btn in pose_buttons:
            if btn.thumbnail_path:
                resolved = DM.PickerDataManager.resolve_image_path(btn.thumbnail_path)
                if resolved and os.path.exists(resolved):
                    buttons_with_thumbnails.append(btn)
        
        if not buttons_with_thumbnails:
            self._show_no_existing_thumbnail_dialog()
            return
        
        # Store buttons and path for callback (keep original bpicker:// path - resolved later in _on_region_selected)
        self._update_buttons = buttons_with_thumbnails
        self._update_thumbnail_path = buttons_with_thumbnails[0].thumbnail_path

        
        # Start the region selection capture process
        self._start_region_capture(is_update=True)

    def _update_existing_thumbnail(self, buttons_with_thumbnails, thumbnail_path, cropped_pixmap):
        """Update existing thumbnail on buttons"""
        # Convert absolute temp path to bpicker:// for storage if inside a session
        store_path = thumbnail_path
        session = DM.PickerDataManager.get_active_session()
        if session and hasattr(session, '_temp_dir') and session._temp_dir:
            temp_dir = session._temp_dir.replace("\\", "/")
            norm_path = thumbnail_path.replace("\\", "/")
            if norm_path.startswith(temp_dir):
                rel = os.path.relpath(thumbnail_path, session._temp_dir).replace("\\", "/")
                store_path = f"bpicker://{rel}"

        for button in buttons_with_thumbnails:
            # Update the stored path and pixmap
            button.thumbnail_path = store_path
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
        # Use the directory of the first button's thumbnail as initial dir
        initial_dir = ''
        if pose_buttons_with_thumbnails:
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
    def _create_staged_poses(self):
        """Create 10 intermediate poses from current state to target pose"""
        if not self._validate_pose_data():
            return []
        
        # Import Blender here to avoid import issues
        try:
            import bpy
        except ImportError:
            print("Blender not available for pose staging")
            return []
        
        target_pose_data = self.pose_data.get("default", {})
        current_namespace = self._get_current_namespace_from_window()
        
        try:
            object_cache = self._build_namespace_object_cache(current_namespace)
        except Exception as cache_error:
            print(f"Error building object cache: {cache_error}")
            return []
        
        # First, capture the current state as stage 0
        current_state = {}
        
        try:
            for pose_key, target_attr_values in target_pose_data.items():
                if isinstance(target_attr_values, dict) and target_attr_values.get('is_armature_pose', False):
                    # Handle armature pose
                    armature_obj = self._resolve_armature_with_namespace_cached(
                        pose_key, current_namespace, target_attr_values, object_cache
                    )
                    
                    if armature_obj:
                        # Store current armature state
                        current_state[pose_key] = {
                            'location': list(armature_obj.location),
                            'scale': list(armature_obj.scale),
                            'is_armature_pose': True,
                            'source_armature': armature_obj.name,
                            'pose_bones': {}
                        }
                        
                        # Add current rotation based on mode
                        if armature_obj.rotation_mode == 'QUATERNION':
                            current_state[pose_key]['rotation_quaternion'] = list(armature_obj.rotation_quaternion)
                        elif armature_obj.rotation_mode == 'AXIS_ANGLE':
                            current_state[pose_key]['rotation_axis_angle'] = list(armature_obj.rotation_axis_angle)
                        else:
                            current_state[pose_key]['rotation_euler'] = list(armature_obj.rotation_euler)
                        
                        # Store current bone states
                        target_bones_data = target_attr_values.get('pose_bones', {})
                        for bone_name in target_bones_data.keys():
                            if bone_name in armature_obj.pose.bones:
                                bone = armature_obj.pose.bones[bone_name]
                                bone_data = {
                                    'location': list(bone.location),
                                    'scale': list(bone.scale)
                                }
                                
                                # Add current bone rotation based on mode
                                if bone.rotation_mode == 'QUATERNION':
                                    bone_data['rotation_quaternion'] = list(bone.rotation_quaternion)
                                elif bone.rotation_mode == 'AXIS_ANGLE':
                                    bone_data['rotation_axis_angle'] = list(bone.rotation_axis_angle)
                                else:
                                    bone_data['rotation_euler'] = list(bone.rotation_euler)
                                
                                current_state[pose_key]['pose_bones'][bone_name] = bone_data
                else:
                    # Handle regular object
                    obj = self._resolve_object_with_namespace_cached(
                        pose_key, current_namespace, object_cache
                    )
                    
                    if obj:
                        current_state[pose_key] = {
                            'location': list(obj.location),
                            'scale': list(obj.scale)
                        }
                        
                        # Add current rotation based on mode
                        if obj.rotation_mode == 'QUATERNION':
                            current_state[pose_key]['rotation_quaternion'] = list(obj.rotation_quaternion)
                        elif obj.rotation_mode == 'AXIS_ANGLE':
                            current_state[pose_key]['rotation_axis_angle'] = list(obj.rotation_axis_angle)
                        else:
                            current_state[pose_key]['rotation_euler'] = list(obj.rotation_euler)
                            
        except Exception as e:
            print(f"Error capturing current state: {e}")
            return []
        
        # Now create 10 intermediate poses
        staged_poses = []
        sr = 10
        for stage in range(sr + 1):  # 0 to 10 (11 stages total)
            if stage == 5:  # Skip the middle stage
                continue
            factor = stage / 10.0  # 0.0 to 1.0
            stage_pose = {}
            
            for pose_key in current_state.keys():
                if pose_key in target_pose_data:
                    current_data = current_state[pose_key]
                    target_data = target_pose_data[pose_key]
                    
                    # Interpolate the data
                    interpolated_data = self._interpolate_pose_data(current_data, target_data, factor)
                    stage_pose[pose_key] = interpolated_data
            
            staged_poses.append(stage_pose)
        
        print(f"Created {len(staged_poses)} staged poses")
        return staged_poses
    
    def _interpolate_pose_data(self, current_data, target_data, factor):
        """Interpolate between current and target pose data"""
        interpolated = {}
        
        # Copy basic structure from target
        for key in target_data.keys():
            if key in ['is_armature_pose', 'source_armature']:
                interpolated[key] = target_data[key]
            elif key == 'pose_bones':
                interpolated[key] = {}
                # Interpolate bone data
                current_bones = current_data.get('pose_bones', {})
                target_bones = target_data.get('pose_bones', {})
                
                for bone_name in target_bones.keys():
                    if bone_name in current_bones:
                        interpolated[key][bone_name] = self._interpolate_transform_values(
                            current_bones[bone_name], target_bones[bone_name], factor
                        )
                    else:
                        interpolated[key][bone_name] = target_bones[bone_name]
            elif key in ['location', 'scale', 'rotation_euler', 'rotation_quaternion', 'rotation_axis_angle']:
                # Interpolate transform values
                if key in current_data:
                    interpolated[key] = self._interpolate_list_values(
                        current_data[key], target_data[key], factor
                    )
                else:
                    interpolated[key] = target_data[key]
            else:
                # Copy other data as-is
                interpolated[key] = target_data[key]
        
        return interpolated
    
    def _interpolate_transform_values(self, current_transform, target_transform, factor):
        """Interpolate transform values between current and target"""
        interpolated = {}
        
        for key in target_transform.keys():
            if key in current_transform and key in ['location', 'scale', 'rotation_euler', 'rotation_quaternion', 'rotation_axis_angle']:
                interpolated[key] = self._interpolate_list_values(
                    current_transform[key], target_transform[key], factor
                )
            else:
                interpolated[key] = target_transform[key]
        
        return interpolated
    
    def _interpolate_list_values(self, current_list, target_list, factor):
        """Interpolate between two lists of numbers"""
        if len(current_list) != len(target_list):
            return target_list
        
        return [
            current_list[i] + (target_list[i] - current_list[i]) * factor
            for i in range(len(current_list))
        ]
    
    def _apply_staged_pose(self, stage):
        """Apply a pre-calculated staged pose using existing pose logic"""
        if stage < 0 or stage >= len(self.staged_poses):
            return
        
        # Get the staged pose data
        staged_pose_data = self.staged_poses[stage]
        
        # Temporarily replace the button's pose data with the staged data
        original_pose_data = self.pose_data.get("default", {})
        self.pose_data["default"] = staged_pose_data
        
        # Use the existing apply_pose logic - no reinventing the wheel!
        try:
            self.apply_pose()
        except Exception as e:
            print(f"Error applying staged pose {stage}: {e}")
        finally:
            # Restore original pose data
            self.pose_data["default"] = original_pose_data
    


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

    def apply_animation(self, apply_mode='replace'):
        """Apply stored animation keyframe data at the current playhead position."""
        if not self.animation_data:
            print("FT Anim Apply: No animation data on this button.")
            return

        current_namespace = self._get_current_namespace_from_window()
        object_cache = self._build_namespace_object_cache(current_namespace)
        base_frame = bpy.context.scene.frame_current
        frame_count = self.animation_data.get('frame_count', 1)

        print(f"FT Anim Apply: mode={apply_mode}, base_frame={base_frame}, "
              f"frame_count={frame_count}, armatures={list(self.animation_data.get('armatures', {}).keys())}")

        try:
            for arm_key, arm_data in self.animation_data.get('armatures', {}).items():
                armature_obj = self._resolve_armature_with_namespace_cached(
                    arm_key, current_namespace,
                    {'is_armature_pose': True, 'source_armature': arm_data.get('source_armature', '')},
                    object_cache
                )
                if not armature_obj:
                    print(f"FT Anim Apply: armature for key '{arm_key}' not found, skipping. "
                          f"source_armature='{arm_data.get('source_armature', '')}', namespace='{current_namespace}'")
                    continue

                bones_data = arm_data.get('bones', {})
                print(f"FT Anim Apply: writing {len(bones_data)} bones to '{armature_obj.name}'")
                TF.write_fcurve_keyframes(
                    armature_obj, bones_data, frame_count, base_frame, apply_mode
                )

            # Refresh viewport
            bpy.context.view_layer.update()
            for area in bpy.context.screen.areas:
                area.tag_redraw()
            print("FT Anim Apply: done.")

        except Exception as e:
            print(f"FT Anim Apply Error: {e}")
            import traceback
            traceback.print_exc()

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
        # Skip validation for animation buttons (they use animation_data, not pose_data)
        if self.is_animation:
            return False
        if not self.pose_data or not self.pose_data.get("default", {}):
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
            
            # First pass: Prioritize objects in the current view layer
            view_layer_objects = set(bpy.context.view_layer.objects)
            
            def add_object_to_cache(obj, priority_key_suffix=""):
                """Add object to cache with optional priority suffix for view layer objects"""
                name = obj.name
                
                # Store exact name (with priority for view layer objects)
                cache_key = name + priority_key_suffix
                if cache_key not in cache['exact'] or priority_key_suffix == "_viewlayer":
                    cache['exact'][name] = obj
                
                # Store by type for faster armature lookups
                obj_type = 'ARMATURE' if obj.type == 'ARMATURE' else ('MESH' if obj.type == 'MESH' else 'OTHER')
                if priority_key_suffix == "_viewlayer":
                    # Insert at beginning for priority
                    cache['by_type'][obj_type].insert(0, obj)
                else:
                    # Only add if not already present from view layer
                    if obj not in cache['by_type'][obj_type]:
                        cache['by_type'][obj_type].append(obj)
                
                # If we have a namespace, build namespace-aware cache
                if current_namespace:
                    for sep in separators:
                        # Check for namespace prefix patterns
                        prefix_pattern = f"{current_namespace}{sep}"
                        if name.startswith(prefix_pattern):
                            base_name = name[len(prefix_pattern):]
                            if base_name not in cache['namespace_prefix'] or priority_key_suffix == "_viewlayer":
                                cache['namespace_prefix'][base_name] = obj
                        
                        # Check for namespace suffix patterns
                        suffix_pattern = f"{sep}{current_namespace}"
                        if name.endswith(suffix_pattern):
                            base_name = name[:-len(suffix_pattern)]
                            if base_name not in cache['namespace_suffix'] or priority_key_suffix == "_viewlayer":
                                cache['namespace_suffix'][base_name] = obj
                    
                    # Handle case where object name equals namespace
                    if name == current_namespace:
                        if current_namespace not in cache['namespace_prefix'] or priority_key_suffix == "_viewlayer":
                            cache['namespace_prefix'][current_namespace] = obj
                        if current_namespace not in cache['namespace_suffix'] or priority_key_suffix == "_viewlayer":
                            cache['namespace_suffix'][current_namespace] = obj
                
                # Build partial match cache for fallback
                name_parts = name.lower().split('_') + name.lower().split('.')
                for part in name_parts:
                    if part and len(part) > 2:  # Only meaningful parts
                        if part not in cache['partial']:
                            cache['partial'][part] = []
                        # Prioritize view layer objects
                        if priority_key_suffix == "_viewlayer":
                            cache['partial'][part].insert(0, obj)
                        elif obj not in cache['partial'][part]:
                            cache['partial'][part].append(obj)
            
            # First pass: Add view layer objects with priority
            for obj in view_layer_objects:
                add_object_to_cache(obj, "_viewlayer")
            
            # Second pass: Add remaining objects from bpy.data.objects as fallback
            for obj in bpy.data.objects:
                if obj not in view_layer_objects:
                    add_object_to_cache(obj, "")
            
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
        import bpy
        
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
            found_obj = object_cache['exact'][obj_name]
            # Check if this object is in the view layer
            in_view_layer = found_obj.name in bpy.context.view_layer.objects
            print(f"Debug: Found object '{obj_name}' in cache, in_view_layer: {in_view_layer}")
            
            # If not in view layer, try to find a view layer alternative
            if not in_view_layer:
                print(f"Debug: Object '{obj_name}' not in view layer, searching for alternatives...")
                # Look for objects in view layer with similar names
                for view_obj in bpy.context.view_layer.objects:
                    if (view_obj.name.startswith(obj_name) or 
                        obj_name in view_obj.name or
                        (hasattr(view_obj, 'override_library') and view_obj.override_library and 
                         view_obj.override_library.reference == found_obj)):
                        print(f"Debug: Found view layer alternative '{view_obj.name}' for '{obj_name}'")
                        return view_obj
            
            return found_obj
        
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
            # Deselect all objects and select posed objects (only if they're in the view layer)
            bpy.ops.object.select_all(action='DESELECT')
            selectable_objects = []
            
            for obj in successfully_posed_objects:
                # Check if object is in the current view layer before trying to select it
                if obj.name in bpy.context.view_layer.objects:
                    try:
                        obj.select_set(True)
                        selectable_objects.append(obj)
                    except Exception as e:
                        print(f"Warning: Could not select object '{obj.name}': {e}")
                else:
                    # For linked objects, try to find a local instance or override
                    local_obj = None
                    for view_obj in bpy.context.view_layer.objects:
                        if (view_obj.name.startswith(obj.name) or 
                            (hasattr(view_obj, 'override_library') and view_obj.override_library and 
                             view_obj.override_library.reference == obj)):
                            local_obj = view_obj
                            break
                    
                    if local_obj:
                        try:
                            local_obj.select_set(True)
                            selectable_objects.append(local_obj)
                            print(f"Info: Selected local override/instance '{local_obj.name}' for linked object '{obj.name}'")
                        except Exception as e:
                            print(f"Warning: Could not select local object '{local_obj.name}': {e}")
                    else:
                        print(f"Warning: Object '{obj.name}' is not in the current view layer (likely a linked object with no local override)")
            
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
                    
                    # Check if armature is in view layer before setting it as active
                    if active_obj.name in bpy.context.view_layer.objects:
                        try:
                            bpy.context.view_layer.objects.active = active_obj
                            
                            with bpy.context.temp_override(window=bpy.context.window_manager.windows[0]):
                                bpy.ops.object.mode_set(mode='POSE')
                                bpy.ops.pose.select_all(action='DESELECT')
                                
                                # Select the posed bones in the target armature
                                if target_armature in posed_bones_by_armature:
                                    posed_bones = posed_bones_by_armature[target_armature]
                                    for bone in posed_bones:
                                        UT.set_bone_selected(bone, True)
                                    bpy.context.object.data.bones.active = bpy.context.object.data.bones[posed_bones[-1].name]
                                
                                # Stay in pose mode for bone posing
                        except Exception as e:
                            print(f"Warning: Could not set armature '{active_obj.name}' as active: {e}")
                    else:
                        # Try to find a local override or instance of the armature
                        local_armature = None
                        for view_obj in bpy.context.view_layer.objects:
                            if (view_obj.type == 'ARMATURE' and 
                                (view_obj.name.startswith(active_obj.name) or
                                 (hasattr(view_obj, 'override_library') and view_obj.override_library and 
                                  view_obj.override_library.reference == active_obj))):
                                local_armature = view_obj
                                break
                        
                        if local_armature:
                            try:
                                bpy.context.view_layer.objects.active = local_armature
                                print(f"Info: Using local armature '{local_armature.name}' for linked armature '{active_obj.name}'")
                                
                                with bpy.context.temp_override(window=bpy.context.window_manager.windows[0]):
                                    bpy.ops.object.mode_set(mode='POSE')
                                    bpy.ops.pose.select_all(action='DESELECT')
                                    
                                    # Select the posed bones in the local armature (same bone names should exist)
                                    if target_armature in posed_bones_by_armature:
                                        posed_bones = posed_bones_by_armature[target_armature]
                                        for bone in posed_bones:
                                            if bone.name in local_armature.pose.bones:
                                                UT.set_bone_selected(local_armature.pose.bones[bone.name], True)
                                        
                                        # Set active bone
                                        if posed_bones and posed_bones[-1].name in local_armature.data.bones:
                                            bpy.context.object.data.bones.active = bpy.context.object.data.bones[posed_bones[-1].name]
                                    
                                    # Stay in pose mode for bone posing
                            except Exception as e:
                                print(f"Warning: Could not set local armature '{local_armature.name}' as active: {e}")
                        else:
                            print(f"Warning: Armature '{active_obj.name}' is not in the current view layer (likely a linked object with no local override)")
            else:
                # OBJECT POSING: Set the last selected object as active (only if it's selectable)
                if selectable_objects:
                    last_selected_object = selectable_objects[-1]  # Use last selectable object
                    try:
                        bpy.context.view_layer.objects.active = last_selected_object
                    except Exception as e:
                        print(f"Warning: Could not set object '{last_selected_object.name}' as active: {e}")
                                
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

        stype = self.script_data.get('type', 'python')
        if stype == 'toggle':
            self._execute_toggle_command()
            return

        # Only support Python in Blender
        if stype != 'python':
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

    def _set_toggle_state(self, target_state):
        """Jump this toggle button directly to the given state index.

        Wired up by the right-click 'Set State' submenu — calls into the
        normal toggle execution path with ``target_state`` so appearances,
        per-state code, and persistence all behave the same as a click.
        """
        try:
            self._execute_toggle_command(target_state=int(target_state))
        except Exception as e:
            self._show_script_error(str(e))

    def _execute_toggle_command(self, target_state=None):
        """Execute a Toggle-mode script button.

        Reads ``toggle_data``, computes the *next* state by cycling through
        ``state_count`` (1, 2, or 3) states, applies each Button Appearance
        instance to its target buttons (standard fields via
        ``TF._apply_appearance_changes``, extended fields like text_color
        and text styles applied directly), batches a single persist call,
        runs the per-state code block, then writes the new ``current_state``.

        With ``state_count == 1`` clicks always re-apply state 1 (no cycle).

        ``target_state`` (0-indexed) overrides the cycling logic and jumps
        directly to that state — used by the right-click "Set State" menu.
        """
        toggle_data = dict(self.script_data.get('toggle_data') or {})
        appearances = toggle_data.get('appearances') or []
        any_code = any(
            (toggle_data.get(f'state_{i}_code') or '').strip()
            for i in (1, 2, 3)
        )
        if not appearances and not any_code:
            return

        state_count = int(toggle_data.get('state_count', 2) or 2)
        state_count = max(1, min(3, state_count))
        current_state = int(toggle_data.get('current_state', 0) or 0)
        if target_state is not None:
            next_state = max(0, min(state_count - 1, int(target_state)))
        elif state_count == 1:
            next_state = 0
        else:
            next_state = (current_state + 1) % state_count
        state_key = f'state_{next_state + 1}'
        code_key = f'state_{next_state + 1}_code'

        # 1) Apply appearances for the next state — direct dispatch through
        # the lower-level helpers so we can batch a single persist call and
        # extend with non-standard fields (text_color, text_style, ...).
        context = TF._discover_execution_context(self)
        all_modified = []
        if context and appearances:
            for ap in appearances:
                vals = ap.get(state_key, {}) or {}
                targets_arg = ap.get('target_buttons') or None  # None → source_button
                try:
                    targets = TF._resolve_target_buttons(targets_arg, context)
                except Exception as e:
                    self._show_script_error(f"Failed to resolve targets for '{ap.get('name','')}': {e}")
                    return
                if not targets:
                    continue

                # Standard fields — text/color/opacity/selectable
                opacity_val = vals.get('opacity', None)
                opacity_arg = str(opacity_val) if opacity_val is not None else ""
                selectable_val = vals.get('selectable', None)
                if selectable_val is True:
                    selectable_arg = "True"
                elif selectable_val is False:
                    selectable_arg = "False"
                else:
                    selectable_arg = ""
                color_arg = vals.get('color', '') or ""
                if not vals.get('color_enabled', True):
                    color_arg = ""

                validated = TF._process_appearance_parameters(
                    text=vals.get('label', '') or "",
                    color=color_arg,
                    opacity=opacity_arg,
                    selectable=selectable_arg,
                )
                modified = []
                if any(v is not None for v in validated.values()):
                    modified = TF._apply_appearance_changes(targets, validated)

                # Extended fields (More Options): text_color + text styles.
                # Reset all render caches the same way _apply_appearance_changes
                # does — text_pixmap *and* pose_pixmap *and* last_zoom_factor.
                for btn in targets:
                    extra_changed = False
                    if vals.get('text_color_enabled') and vals.get('text_color'):
                        tc = vals.get('text_color')
                        if isinstance(tc, str) and tc.startswith('#'):
                            btn.text_color = tc
                            extra_changed = True
                    if vals.get('text_style_enabled'):
                        btn.text_bold = bool(vals.get('text_bold'))
                        btn.text_italic = bool(vals.get('text_italic'))
                        btn.text_underline = bool(vals.get('text_underline'))
                        extra_changed = True
                    if extra_changed:
                        btn.text_pixmap = None
                        btn.pose_pixmap = None
                        btn.last_zoom_factor = 0
                        try:
                            btn.update_tooltip()
                        except Exception:
                            pass
                        btn.update()
                        if btn not in modified:
                            modified.append(btn)

                # Shape (More Options): width, height, radius, rotation —
                # commit target values immediately (so persist captures them),
                # remember 'prev' values so the post-persist pass can rewind
                # and animate forward with a smooth ease.
                if vals.get('shape_enabled'):
                    target_w = int(vals.get('width', 80))
                    target_h = int(vals.get('height', 30))
                    target_r = int(vals.get('radius', 3))
                    target_rot = int(vals.get('rotation', 0))
                    for btn in targets:
                        btn.width = target_w
                        btn.height = target_h
                        btn.radius = [target_r] * 4
                        btn.rotation = target_rot
                        btn.text_pixmap = None
                        btn.pose_pixmap = None
                        btn.last_zoom_factor = 0
                        btn.update()
                        if btn not in modified:
                            modified.append(btn)

                all_modified.extend(modified)

            # Dedup and persist all touched buttons in one pass
            seen = set()
            unique_modified = []
            for b in all_modified:
                if id(b) not in seen:
                    seen.add(id(b))
                    unique_modified.append(b)
            if unique_modified:
                try:
                    TF._persist_appearance_changes(unique_modified, context, {})
                except Exception as e:
                    self._show_script_error(f"Failed to persist appearance changes: {e}")
                    return

        # 2) Run the per-state code block, if any
        code = toggle_data.get(code_key, '') or ''
        if code.strip():
            try:
                current_ns, ns_prefix = self._get_namespace_info()
                modified_code = self._process_script_code(code, current_ns)
                global_vars = self._create_execution_environment(current_ns, ns_prefix)
                with bpy.context.temp_override(window=bpy.context.window_manager.windows[0]):
                    exec(modified_code, global_vars, global_vars)
            except Exception as e:
                self._show_script_error(str(e))
                return
            finally:
                self._update_blender_ui()

        # 3) Flip current_state and persist through the standard change signal
        toggle_data['current_state'] = next_state
        new_script_data = dict(self.script_data)
        new_script_data['toggle_data'] = toggle_data
        self.script_data = new_script_data
        try:
            self.changed.emit(self)
        except Exception:
            pass

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
        self.controller_pixmap = None
        self.update()
        self.changed.emit(self)  # Emit changed signal

    def change_opacity(self, value):
        self.opacity = value / 100.0
        self.update()
        self.changed.emit(self)  # Emit changed signal

    def rename_button(self, new_label):
        self.label = new_label
        # Force regeneration of text pixmap
        self.text_pixmap = None
        self.update()
        self.changed.emit(self)  # Emit changed signal
    
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
            self.label = new_label
            self.update()

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
            # Disconnect signals to prevent double-firing during deletion
            try:
                self.rename_edit.textChanged.disconnect()
                self.rename_edit.returnPressed.disconnect()
                self.rename_edit.editingFinished.disconnect()
            except:
                pass  # Signals might already be disconnected
            self.rename_edit.deleteLater()
            self.rename_edit = None
        
        self.update()
    
    def commit_rename(self):
        """Commit the rename changes and exit rename mode"""
        if not self.rename_mode or not self.rename_edit:
            return
        
        # Prevent re-entry (in case both returnPressed and editingFinished fire)
        if hasattr(self, '_committing_rename') and self._committing_rename:
            return
        
        self._committing_rename = True
        
        try:
            # Get the new label
            new_label = self.rename_edit.text().strip()
            
            self.rename_selected_buttons(new_label)
                
            # Exit rename mode
            self.exit_rename_mode()
        finally:
            self._committing_rename = False
    
    def delete_button(self):
        self.deleted.emit(self)
        self.deleteLater()
    #---------------------------------------------------------------------------------------
    def rename_selected_buttons(self, new_label):
        # Record undo state before change
        main_window = self.window()
        '''if isinstance(main_window, UI.BlenderAnimPickerWindow):
            DM.PickerDataManager.save_undo_state(f"Rename Button: {self.label} → {new_label}")'''
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
        # Record undo state before change
        main_window = self.window()
        '''if isinstance(main_window, UI.BlenderAnimPickerWindow):
            DM.PickerDataManager.save_undo_state(f"Change Button Color")'''
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
        # Record undo state before change
        main_window = self.window()
        '''if isinstance(main_window, UI.BlenderAnimPickerWindow):
            DM.PickerDataManager.save_undo_state(f"Change Button Opacity")'''
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
        
        #DM.PickerDataManager.save_undo_state(f"Delete {len(selected_buttons)} Button(s)")
        
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
                canvas.transform_guides.controls_widget.setVisible(False)

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
                
                # Method 1: Try context selected_pose_bones (handle Blender version compatibility)
                try:
                    # Try new attribute name first (Blender 4.0+)
                    context_bones = getattr(bpy.context, 'selected_pose_bones_from_active_object', None)
                    if not context_bones:
                        # Try legacy attribute name
                        context_bones = getattr(bpy.context, 'selected_pose_bones', None)
                    if context_bones:
                        selected_pose_bones = list(context_bones)
                        #print(f"Found {len(selected_pose_bones)} bones via context")
                except:
                    pass
                
                # Method 2: If no bones found via context, check bone selection manually
                if not selected_pose_bones and active_obj.pose:
                    for pose_bone in active_obj.pose.bones:
                        if UT.is_bone_selected(pose_bone):
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
                        
                        # Try getting selected bones again (handle Blender version compatibility)
                        context_bones = getattr(bpy.context, 'selected_pose_bones_from_active_object', None)
                        if not context_bones:
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

    def remove_selected_objects(self):
        """Remove currently selected Blender objects/bones from this button's assigned objects"""
        import bpy
        with bpy.context.temp_override(window=bpy.context.window_manager.windows[0]):
            active_obj = bpy.context.view_layer.objects.active
            current_mode = getattr(bpy.context, 'mode', None)

            # Get current namespace from main window
            main_window = self.window()
            current_namespace = None
            if hasattr(main_window, 'namespace_dropdown'):
                current_namespace = main_window.namespace_dropdown.currentText()
                if current_namespace == 'None':
                    current_namespace = None

            ids_to_remove = set()

            if active_obj and active_obj.type == 'ARMATURE' and current_mode == 'POSE':
                # Gather selected pose bone IDs
                selected_pose_bones = []
                try:
                    context_bones = getattr(bpy.context, 'selected_pose_bones_from_active_object', None)
                    if not context_bones:
                        context_bones = getattr(bpy.context, 'selected_pose_bones', None)
                    if context_bones:
                        selected_pose_bones = list(context_bones)
                except:
                    pass

                if not selected_pose_bones and active_obj.pose:
                    for pose_bone in active_obj.pose.bones:
                        if UT.is_bone_selected(pose_bone):
                            selected_pose_bones.append(pose_bone)

                armature_name = current_namespace if current_namespace else active_obj.name
                for bone in selected_pose_bones:
                    ids_to_remove.add(f"{armature_name}|{bone.name}")
            else:
                # Regular object selection
                selected = bpy.context.view_layer.objects.selected
                for obj in selected:
                    ids_to_remove.add(obj.name)

            if ids_to_remove:
                original_count = len(self.assigned_objects)
                self.assigned_objects = [
                    obj for obj in self.assigned_objects
                    if self._get_item_id(obj) not in ids_to_remove
                ]
                removed_count = original_count - len(self.assigned_objects)
                if removed_count > 0:
                    self._tooltip_needs_update = True
                    self.changed.emit(self)
                    print(f"Removed {removed_count} object(s) from picker button")
                else:
                    print("No matching objects found on this button")
            else:
                print("No objects/bones selected to remove")

    def remove_selected_objects_for_selected_buttons(self):
        """Remove currently selected objects/bones from all selected picker buttons"""
        canvas = self.parent()
        if canvas:
            selected_buttons = canvas.get_selected_buttons()
            for button in selected_buttons:
                button.remove_selected_objects()

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
        # In canvas-painted mode (no mask), the widget covers the full bounding rect.
        # Reject clicks outside the actual button shape so they fall through to canvas.
        if self._canvas_painted:
            local = QtCore.QPointF(event.pos().x(), event.pos().y())
            if not self._point_in_shape(local):
                event.ignore()
                return

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
                        if self._canvas_painted:
                            self.parent().setCursor(QtCore.Qt.ClosedHandCursor)
                        else:
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
                    elif self.mode == 'controller':
                        # Controller interaction — handle selection then slider drag
                        if not self.is_selected and not shift_held:
                            canvas.clear_selection()
                            self.is_selected = True
                            self.selected.emit(self, True)
                            canvas.last_selected_button = self
                            canvas.button_selection_changed.emit()
                        elif shift_held:
                            self.is_selected = not self.is_selected
                            if self.is_selected:
                                canvas.last_selected_button = self
                            self.selected.emit(self, self.is_selected)
                            canvas.button_selection_changed.emit()
                        # Select the controlled Blender object(s)
                        self._select_controller_object()
                        # Start drag on all selected controller buttons
                        self._controller_dragging = True
                        self._controller_drag_start_x = event.globalPos().x()
                        self._controller_drag_start_y = event.globalPos().y()
                        self._controller_drag_start_val = self._controller_value
                        self._controller_drag_start_val_y = self._controller_value_y
                        # Store start values for all selected controller buttons
                        self._controller_drag_peers = []
                        for btn in canvas.get_selected_buttons():
                            if btn.mode == 'controller' and btn is not self:
                                btn._controller_drag_start_val = btn._controller_value
                                btn._controller_drag_start_val_y = btn._controller_value_y
                                self._controller_drag_peers.append(btn)
                    elif self.mode == 'pose':
                        # Highlight the pressed pose button (sync no longer
                        # highlights pose buttons from control selection).
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
                        if self.is_animation:
                            # Animation button apply with modifier-based mode selection
                            if ctrl_held and shift_held:
                                self.apply_animation(apply_mode='add')
                            elif ctrl_held:
                                self.apply_animation(apply_mode='merge')
                            else:
                                self.apply_animation(apply_mode='replace')
                        else:
                            # Single-frame pose apply (existing behavior)
                            if alt_held:
                                self.apply_mirrored_pose()
                            elif shift_held:
                                self.start_pose_drag(event)
                            else:
                                self.apply_pose()
                    
                    
                event.accept()
        elif event.button() == QtCore.Qt.RightButton:
            alt_held = event.modifiers() & QtCore.Qt.AltModifier

            # If Alt is held, ignore the event and let canvas handle zoom
            if alt_held:
                event.ignore()
                return

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
            # Check if window is in edit mode
            main_window = self.window()
            if main_window.edit_mode == False:
                # Don't steal focus if controller input overlay is active
                if not (self.mode == 'controller' and getattr(self, '_controller_input_active', False)):
                    # Hand keyboard focus to Blender so viewport shortcuts
                    # work after a button click. Select-mode buttons also
                    # call this from inside apply_final_selection (after
                    # bpy.ops settles); this covers script/controller/pose
                    # modes that don't run bpy.ops.
                    UT.blender_main_window()

    def mouseDoubleClickEvent(self, event):
        """Handle double-click events for renaming buttons in edit mode"""
        if self._canvas_painted:
            local = QtCore.QPointF(event.pos().x(), event.pos().y())
            if not self._point_in_shape(local):
                event.ignore()
                return
        if not self.edit_mode:
            if self.mode == 'controller':
                # Double-click to type value in non-edit mode
                # Shift+double-click: apply typed value to all selected controller buttons
                shift_held = bool(event.modifiers() & QtCore.Qt.ShiftModifier)
                self._show_controller_input_overlay(apply_to_selected=shift_held)
                event.accept()
                return
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
        """Enhanced mouse move with duplication support, pose dragging, controller dragging, and optimized dragging"""
        # Handle controller slider drag (multi-select: relative delta to all)
        if self._controller_dragging and event.buttons() & QtCore.Qt.LeftButton:
            canvas = self.parent()
            global_dx = event.globalPos().x() - self._controller_drag_start_x
            global_dy = event.globalPos().y() - self._controller_drag_start_y
            zoom = canvas.zoom_factor if canvas else 1.0

            self._apply_controller_drag_delta(global_dx, global_dy, zoom)
            for peer in getattr(self, '_controller_drag_peers', []):
                peer._apply_controller_drag_delta(global_dx, global_dy, zoom)

            if canvas:
                canvas.update()
            event.accept()
            return

        if hasattr(self, 'pose_dragging') and self.pose_dragging and event.buttons() & QtCore.Qt.LeftButton:
            # Handle pose drag
            self.handle_pose_drag(event)
            event.accept()
        elif hasattr(self, 'duplicating') and self.duplicating and event.buttons() & QtCore.Qt.LeftButton:
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

            # Update positions without triggering individual canvas updates
            selected_buttons = canvas.get_selected_buttons()
            for button in selected_buttons:
                button.set_scene_position_silent(button.button_start_pos + scene_delta)

            # Single update for all button positions
            canvas.update_button_positions()

            # Re-enable updates
            canvas.setUpdatesEnabled(True)

            # Throttled transform guides update via persistent timer
            canvas._request_guides_update()
            
            event.accept()
        else:
            # In canvas-painted mode (no mask), the widget covers the full bounding
            # rect so the canvas's mouseMoveEvent doesn't fire. Forward the position
            # to the canvas for shape-aware hover tracking.
            if self._canvas_painted:
                canvas = self.parent()
                if canvas:
                    canvas._update_hover_button(self.mapToParent(event.pos()))
            super().mouseMoveEvent(event)

    def wheelEvent(self, event):
        """Forward wheel events to the parent canvas.

        Without this, after a button click steals focus to Blender,
        subsequent wheel events delivered over a button widget can fail to
        propagate to the canvas's wheelEvent handler — breaking zoom/pan.
        Explicitly forwarding bypasses any focus / event-routing oddities.
        """
        canvas = self.parent()
        if canvas is not None and hasattr(canvas, 'wheelEvent'):
            try:
                if not self.window().isActiveWindow():
                    UT.make_picker_key_window(self)
                widget_pos = QtCore.QPointF(event.position())
                canvas_pos = QtCore.QPointF(self.pos()) + widget_pos
                forwarded = QtGui.QWheelEvent(
                    canvas_pos,
                    event.globalPosition(),
                    event.pixelDelta(),
                    event.angleDelta(),
                    event.buttons(),
                    event.modifiers(),
                    event.phase(),
                    event.inverted(),
                )
                canvas.wheelEvent(forwarded)
                event.accept()
                return
            except Exception:
                pass
        event.ignore()

    def event(self, ev):
        """Forward trackpad native gesture events (pinch-to-zoom) to the
        parent canvas. Native gesture events are not propagated up the
        parent chain by Qt, so when the cursor is over a button after a
        click steals focus, the canvas never sees the gesture and trackpad
        zoom appears broken.
        """
        native_gesture_type = getattr(
            QtCore.QEvent.Type, 'NativeGesture',
            getattr(QtCore.QEvent, 'NativeGesture', None)
        )
        if native_gesture_type is not None and ev.type() == native_gesture_type:
            canvas = self.parent()
            if canvas is not None and hasattr(canvas, '_handle_native_gesture'):
                try:
                    if not self.window().isActiveWindow():
                        UT.make_picker_key_window(self)
                except Exception:
                    pass
                try:
                    widget_pos = QtCore.QPointF(ev.position())
                except Exception:
                    widget_pos = QtCore.QPointF(0, 0)
                canvas_pos = QtCore.QPointF(self.pos()) + widget_pos

                class _GestureShim:
                    def __init__(self, src, pos):
                        self._src = src
                        self._pos = pos
                    def gestureType(self):
                        return self._src.gestureType()
                    def value(self):
                        return self._src.value()
                    def position(self):
                        return self._pos
                    def accept(self):
                        return self._src.accept()

                try:
                    handled = canvas._handle_native_gesture(_GestureShim(ev, canvas_pos))
                except Exception:
                    handled = False
                if handled:
                    ev.accept()
                    return True
        return super().event(ev)

    def mouseReleaseEvent(self, event):
        """Enhanced mouse release with optimized batch updates"""
        if event.button() == QtCore.Qt.LeftButton:
            canvas = self.parent()

            # Handle controller drag completion
            if self._controller_dragging:
                self._controller_dragging = False
                self._controller_drag_peers = []
                # Deselect and reselect to force viewport refresh
                self._select_controller_object()
                event.accept()
                return

            # Handle pose drag completion
            if hasattr(self, 'pose_dragging') and self.pose_dragging:
                self.complete_pose_drag(event)
                event.accept()
                return
            
            # Handle duplication completion
            if hasattr(self, 'duplicating') and self.duplicating:
                self.complete_duplication_drag(event)
                event.accept()
                return
            
            # Handle normal dragging completion
            if self.dragging:
                self.dragging = False
                self.update_cursor()
                
                # Check if button actually moved from its starting position
                distance_moved = ((self.scene_position.x() - self.button_start_pos.x()) ** 2 + 
                                (self.scene_position.y() - self.button_start_pos.y()) ** 2) ** 0.5
                
                # Only save if moved more than 1 pixel
                if distance_moved > 1.0:
                    # Save the position change
                    selected_buttons = canvas.get_selected_buttons()
                    main_window = canvas.window()
                    if isinstance(main_window, UI.BlenderAnimPickerWindow):
                        self._batch_update_button_positions(selected_buttons, main_window)
                
                event.accept()
        else:
            super().mouseReleaseEvent(event)
        
    def event(self, event):
        """Override event to handle key events."""
        if event.type() == QtCore.QEvent.KeyPress:
            if event.key() == QtCore.Qt.Key_Escape:
                self.exit_rename_mode()
                return True
        return super().event(event)
    
    def enterEvent(self, event):
        """Called when mouse enters the button area."""
        if self._canvas_painted:
            # In canvas-painted mode, hover is managed by the canvas's
            # _update_hover_button (shape-aware). Skip widget-level hover
            # since the widget is the full bounding rect (no mask).
            super().enterEvent(event)
            return
        self.is_hovered = True
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event):
        """Called when mouse leaves the button area."""
        if self._canvas_painted:
            # Mouse left the bounding rect — clear canvas hover reference.
            # paint_on_canvas checks _current_hover_button, not is_hovered.
            canvas = self.parent()
            if canvas and canvas._current_hover_button is self:
                canvas._current_hover_button = None
                canvas.update()
            self.is_hovered = False
            super().leaveEvent(event)
            return
        self.is_hovered = False
        self.update()
        super().leaveEvent(event)
    
    def keyPressEvent(self, event):
        """Handle key press events"""
        if event.key() == QtCore.Qt.Key_Escape and hasattr(self, 'pose_dragging') and self.pose_dragging:
            # Cancel pose dragging on Escape key
            self.cancel_pose_drag()
            event.accept()
        else:
            super().keyPressEvent(event)
    
    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._update_rename_edit_geometry()

