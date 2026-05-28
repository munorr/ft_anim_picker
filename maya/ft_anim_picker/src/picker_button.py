from functools import partial
import maya.cmds as cmds
import maya.mel as mel
import os
import math
import re
import xml.etree.ElementTree as ET
try:
    from PySide6 import QtWidgets, QtCore, QtGui
    from PySide6.QtGui import QColor, QAction, QActionGroup
    from PySide6.QtCore import QTimer, QPropertyAnimation, QEasingCurve, Signal
    from shiboken6 import wrapInstance
except ImportError:
    from PySide2 import QtWidgets, QtCore, QtGui
    from PySide2.QtWidgets import QAction, QActionGroup
    from PySide2.QtGui import QColor
    from PySide2.QtCore import QTimer, QPropertyAnimation, QEasingCurve, Signal
    from shiboken2 import wrapInstance

from . import utils as UT
from . import custom_line_edit as CLE
from . import custom_button as CB
from . import data_management as DM
from . import ui as UI
from . import tool_functions as TF
from . import custom_dialog as CD
from . import main as MAIN
from . import custom_color_picker as CCP

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
                # Create a dictionary with all button properties
                button_data = {
                    'label': button.label,
                    'selectable': button.selectable,
                    'color': button.color,
                    'opacity': button.opacity,
                    'width': button.width,
                    'height': button.height,
                    'radius': button.radius.copy(),
                    'rotation': button.rotation,
                    'relative_position': button.scene_position - center,
                    'assigned_objects': button.assigned_objects.copy(),
                    'mode': button.mode,
                    'script_data': button.script_data.copy(),
                    'thumbnail_path': button.thumbnail_path,
                    'shape_type': button.shape_type,
                    'svg_path_data': button.svg_path_data,
                    'svg_file_path': button.svg_file_path
                }
                
                # Add pose-specific data if this is a pose button
                if button.mode == 'pose':
                    button_data['thumbnail_path'] = button.thumbnail_path
                    button_data['pose_data'] = button.pose_data.copy()  # Copy the pose data
                    button_data['animation_data'] = button.animation_data.copy() if button.animation_data else {}

                # Add controller-specific data if this is a controller button
                if button.mode == 'controller':
                    button_data['controller_data'] = button.controller_data.copy() if button.controller_data else {}

                self.copied_buttons.append(button_data)

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
        self._transform_active = False     # True during active drag/scale — defers pixmap regen

        self.setStyleSheet(f"QToolTip {{background-color: {UT.rgba_value(color,.8,alpha=1)}; color: #eeeeee ; border: 1px solid rgba(255,255,255,.2); padding: 4px;}}")
        # Set tool tip to have translucent background and remove shadow
        self.tooltip_widget = CB.CustomTooltipWidget(parent=self)
        self._tooltip_populated = False
        self._tooltip_needs_update = True 
       
        self.edit_mode = False
        self.update_cursor()
        self.assigned_objects = []  

        self.mode = 'select'  # 'select', 'script', 'pose', or 'controller'
        self.script_data = {}  # Store script data
        self.pose_data = {}  # Store pose data
        self.animation_data = {}  # Store animation keyframe data
        self.controller_data = {}  # Store controller mode config (field_type, data_path, min/max, etc.)

        # Controller mode state
        self._controller_value = 0.0          # X-axis value (also used as the single value for 1D sliders)
        self._controller_value_y = 0.0        # Y-axis value (omni mode only)
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
        self.last_radius = None       # Track radius to know when to regenerate the pixmap
        self.last_text = None        # Track text to know when to regenerate the pixmap

        # Add update throttling
        self.update_timer = QTimer()
        self.update_timer.setSingleShot(True)
        self.update_timer.timeout.connect(self._delayed_update)
        self.needs_update = False

        # Pose staging for gradual pose application
        self.pose_dragging = False
        self.pose_drag_start_pos = None
        self.current_pose_stage = 0
        self.staged_poses = []  # Pre-calculated intermediate poses
        self._pose_object_cache = {}  # Cache resolved object names during pose dragging

        self.is_hovered = False
        self.update_tooltip()

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

    #---------------------------------------------------------------------------------------
    def update(self):
        """REPLACE your update method with this throttled version"""
        if not self.needs_update:
            self.needs_update = True
            self.update_timer.start(16)  # ~60fps
        self.update_tooltip()
    
    def _delayed_update(self):
        """ADD this method for actual updates"""
        if self.needs_update:
            self.needs_update = False
            super().update()

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
        
        pose_painter.end()
        return pose_pixmap

    def _render_text_pixmap(self, current_size, zoom_factor):
        """Render the pixmap for regular mode with centered text.

        Args:
            current_size (QSize): Current button size in pixels
            zoom_factor (float): Current zoom factor

        Returns:
            QPixmap: The rendered text pixmap
        """
        text_pixmap = QtGui.QPixmap(current_size)
        text_pixmap.fill(QtCore.Qt.transparent)

        # Skip rendering if too small to show text
        if current_size.width() < 4 or current_size.height() < 4:
            return text_pixmap

        text_painter = QtGui.QPainter(text_pixmap)
        text_painter.setRenderHint(QtGui.QPainter.Antialiasing)
        text_painter.setRenderHint(QtGui.QPainter.TextAntialiasing)

        text_painter.setPen(QtGui.QColor(self.text_color))
        font = text_painter.font()

        # Font size based on button logical height scaled by zoom
        font_size = (self.height * 0.5) * zoom_factor

        # Use the pixmap rect (not self.rect() which is the QWidget envelope)
        text_rect = QtCore.QRect(0, 0, current_size.width(), current_size.height())
        bottom_padding = int((self.height * 0.1) * zoom_factor)
        text_rect.adjust(0, 0, 0, -bottom_padding)

        # Clamp font size to valid range
        font_size_int = max(1, int(font_size))
        font.setPixelSize(font_size_int)
        text_painter.setFont(font)

        # Shrink font if text is wider than button
        text_metrics = text_painter.fontMetrics()
        text_width = text_metrics.horizontalAdvance(self.label)
        if text_width > 0 and text_width > (current_size.width() * 0.9):
            width_based = font_size * (current_size.width() * 0.8) / text_width
            font_size_int = max(1, int(min(font_size, width_based)))
            font.setPixelSize(font_size_int)
            text_painter.setFont(font)

        # Only draw if font is readable
        if font_size_int >= 2:
            if hasattr(self, 'pose_dragging') and self.pose_dragging and hasattr(self, 'current_pose_stage'):
                text_painter.drawText(text_rect, QtCore.Qt.AlignCenter, f"Stage {self.current_pose_stage}/10")
            else:
                text_painter.drawText(text_rect, QtCore.Qt.AlignCenter, self.label)

        text_painter.end()
        return text_pixmap

    # -- Omni controller layout fractions (shared by renderer, geometry,
    #    button-shape snap, and scale-lock so they stay in sync). ------------
    OMNI_TRACK_W_FRAC = 0.88              # control area width as fraction of pixel width
    OMNI_LABEL_HEADER_FRAC = 0.22         # label header height as fraction of pixel height
    OMNI_LABEL_TRACK_Y_FRAC = 0.22        # control top with a label
    OMNI_LABEL_TRACK_H_FRAC = 0.74        # control height with a label
    OMNI_NOLABEL_TRACK_Y_FRAC = 0.12      # control top without a label
    OMNI_NOLABEL_TRACK_H_FRAC = 0.76      # control height without a label

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

    # -- Controller mode rendering & sync ------------------------------------

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

        # -- Header label (top portion -- only if label exists and non-empty) --
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
                p.setFont(font)
                p.setPen(QtGui.QColor(self.text_color))
                header_rect = QtCore.QRect(int(pw * 0.06), 0, int(pw * 0.88), header_h)
                p.drawText(header_rect, QtCore.Qt.AlignLeft | QtCore.Qt.AlignVCenter, self.label)

        # -- Control area --
        margin_x = int(pw * 0.06)
        if is_omni:
            # Omni uses its own (more generous) track fractions so the pad
            # fills most of the button vertically — see omni_track_*_frac.
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
        local frame). Reads its own per-button drag-start values stored
        at mousePress time, so it works the same for the active button
        and for peers in a multi-select drag.
        """
        cd = self.controller_data
        # Project global delta into this button's local frame so rotated
        # controls drag along their visual axes.
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
            # the cursor 1:1. The thumb traverses (pad_size - 2*thumb_radius)
            # pixels across the pad — that's the pixel range for the value.
            pad_size_px, thumb_radius_px = self._omni_pad_geometry(zoom)
            travel_px = max(1.0, pad_size_px - 2 * thumb_radius_px)

            # Note: screen Y grows downward; flip so dragging up = +Y
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
        # Flip so screen-down maps to lower Y values
        fy = 1.0 - fy_val
        return max(0.0, min(1.0, fx)), max(0.0, min(1.0, fy))

    def _omni_pad_geometry(self, zoom):
        """Return shared pad geometry for the omni control area.

        The pad is always square — sized to the largest square that fits in
        the control area — so the visual layout matches the drag math
        regardless of button aspect ratio. Used by both the renderer and
        ``_apply_controller_drag_delta`` so the thumb tracks the cursor 1:1.

        Returns:
            tuple: (pad_size_px, thumb_radius_px) in screen pixels.
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
        """Render a 2D square pad with an outlined frame, axis guides, and
        a thumb dot.

        ``control_rect`` is the available control area (full width × control
        height). The pad is drawn as the largest centered square inside it.
        The frame is outlined in the button's color over a transparent
        background; the axis guides and thumb also use the button color.
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
        # Inset the guides slightly so they don't visually touch the rounded corners
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

        For Maya:
        - 'relative' means prepend the namespace from the picker window
          e.g. 'ctrl_arm_L.rotateY' -> 'charNS:ctrl_arm_L.rotateY'
        - 'absolute' means use the path as-is
          e.g. '|group1|pCube1.translateX'

        Returns:
            str: The fully resolved Maya attribute path, or '' on failure.
        """
        cd = self.controller_data
        path_type = cd.get('path_type', 'absolute')
        data_path = cd.get(path_key, '')

        if not data_path:
            return ''

        if path_type == 'relative':
            # Get namespace from the picker window
            current_ns, ns_prefix = self._get_namespace_info()
            if ns_prefix:
                # Split into node.attr -- prepend namespace to node part
                if '.' in data_path:
                    node_part, attr_part = data_path.split('.', 1)
                    return f"{ns_prefix}{node_part}.{attr_part}"
                else:
                    return f"{ns_prefix}{data_path}"
            # No namespace active -- use path as-is
            return data_path

        # Absolute path -- use as-is
        return data_path

    def _select_controller_object(self):
        """Select the Maya object(s) controlled by all selected controller buttons."""
        canvas = self.parent()
        if not canvas:
            return

        # Gather all selected controller buttons (including self)
        buttons = [self]
        for btn in canvas.get_selected_buttons():
            if btn.mode == 'controller' and btn is not self:
                buttons.append(btn)

        nodes_to_select = []
        for btn in buttons:
            # For omni buttons, gather both X and Y paths so the node still
            # gets selected even when 'data_path' is empty.
            field_type = btn.controller_data.get('field_type', 'slider')
            if field_type == 'omni':
                path_keys = ('data_path_x', 'data_path_y')
            else:
                path_keys = ('data_path',)
            for pk in path_keys:
                path = btn._resolve_controller_data_path(pk)
                if not path:
                    continue
                # Extract the node name from 'node.attr'
                node_name = path.split('.')[0] if '.' in path else path
                if node_name and node_name not in nodes_to_select:
                    try:
                        if cmds.objExists(node_name):
                            nodes_to_select.append(node_name)
                    except Exception:
                        pass

        if nodes_to_select:
            try:
                cmds.select(clear=True)
                cmds.select(nodes_to_select, replace=True)
            except Exception:
                pass

    def _read_controller_value(self):
        """Read the current Maya attribute value from the data path.

        Returns:
            float or None: The current value, or None on error.
        """
        path = self._resolve_controller_data_path()
        if not path:
            return None
        try:
            value = cmds.getAttr(path)
            return float(value)
        except Exception as e:
            # Store last error for debugging (visible via Test Path)
            self._controller_last_error = str(e)
            return None

    def _write_controller_value(self, value):
        """Write a value to the Maya attribute at the data path."""
        path = self._resolve_controller_data_path()
        if not path:
            return
        try:
            cmds.setAttr(path, value)
        except Exception:
            pass

    # -- Omni (2-axis) read / write ----------------------------------------
    def _read_controller_xy(self):
        """Read both X and Y attribute values for an omni controller.

        Returns:
            tuple(float|None, float|None): (x, y) — either may be None on error.
        """
        x_val = None
        y_val = None
        path_x = self._resolve_controller_data_path('data_path_x')
        if path_x:
            try:
                x_val = float(cmds.getAttr(path_x))
            except Exception as e:
                self._controller_last_error = str(e)
        path_y = self._resolve_controller_data_path('data_path_y')
        if path_y:
            try:
                y_val = float(cmds.getAttr(path_y))
            except Exception as e:
                self._controller_last_error = str(e)
        return x_val, y_val

    def _write_controller_xy(self, x_value, y_value):
        """Write X and Y values to the omni controller attributes."""
        path_x = self._resolve_controller_data_path('data_path_x')
        if path_x:
            try:
                cmds.setAttr(path_x, x_value)
            except Exception:
                pass
        path_y = self._resolve_controller_data_path('data_path_y')
        if path_y:
            try:
                cmds.setAttr(path_y, y_value)
            except Exception:
                pass

    def _start_controller_sync(self):
        """Start the polling timer for Maya -> picker sync."""
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
        """Poll the Maya attribute and update if changed."""
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

        def _cancel():
            self._controller_input_active = False
            edit.deleteLater()

        edit.returnPressed.connect(_commit)
        edit.editingFinished.connect(_commit)

    def _should_update_pixmaps(self, zoom_factor, current_size, current_radius, current_text):
        """Determine if pixmaps need to be updated."""
        if self.mode == 'pose':
            pixmap_missing = self.pose_pixmap is None
        elif self.mode == 'controller':
            pixmap_missing = self.controller_pixmap is None
        else:
            pixmap_missing = self.text_pixmap is None

        # During active transforms (drag/scale/rotate), reuse existing pixmap
        # to avoid expensive per-frame regeneration. Pixmaps refresh on release.
        if self._transform_active and not pixmap_missing:
            return False

        zoom_changed = abs(self.last_zoom_factor - zoom_factor) > 0.1
        # Use threshold for size comparison to avoid thrashing during smooth resizes
        if self.last_size is not None:
            size_changed = (abs(self.last_size.width() - current_size.width()) > 2 or
                           abs(self.last_size.height() - current_size.height()) > 2)
        else:
            size_changed = True
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
            font_size = max(1.0, min(h * 0.35, w * 0.15))
            font.setPointSizeF(font_size)
            painter.setFont(font)
            painter.drawText(content_rect, QtCore.Qt.AlignCenter, self.label)

        painter.restore()

    def hit_test_scene(self, scene_point):
        """Test if a point in scene coordinates is inside this button's shape.

        Uses the exact same path construction as paint_on_canvas, so the
        clickable area always matches the visible shape perfectly.
        """
        dx = scene_point.x() - self._scene_position.x()
        dy = scene_point.y() - self._scene_position.y()

        # Un-rotate into button-local scene coords
        if self.rotation != 0:
            rad = math.radians(-self.rotation)
            cos_a, sin_a = math.cos(rad), math.sin(rad)
            dx, dy = dx * cos_a - dy * sin_a, dx * sin_a + dy * cos_a

        path = self._get_scene_path(self.width, self.height)
        return path.contains(QtCore.QPointF(dx, dy))

    def paintEvent(self, event):
        """Paint the button with background, selection border, and text/thumbnail.

        Args:
            event (QPaintEvent): The paint event
        """
        # In canvas-painted mode, no visual drawing — canvas handles rendering.
        if self._canvas_painted:
            return

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
        # Use fixed 1px inset for consistent rendering regardless of zoom level
        # This ensures pixel-perfect alignment between curve editor and button display
        rect = self.rect().adjusted(1, 1, -1, -1)
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
            if self.mode == 'controller':
                self._last_controller_value = self._controller_value
                self._last_controller_value_y = self._controller_value_y
            if self.mode == 'pose':
                self.pose_pixmap = self._render_pose_pixmap(current_size, zoom_factor)
                # Create an empty text_pixmap to avoid None checks
                self.text_pixmap = QtGui.QPixmap(current_size)
                self.text_pixmap.fill(QtCore.Qt.transparent)
            elif self.mode == 'controller':
                self.controller_pixmap = self._render_controller_pixmap(current_size, zoom_factor)
            else:
                self.text_pixmap = self._render_text_pixmap(current_size, zoom_factor)

        # Draw the appropriate pixmap
        if self.mode == 'pose':
            if self.pose_pixmap and not self.pose_pixmap.isNull():
                painter.drawPixmap(0, 0, self.pose_pixmap)
        elif self.mode == 'controller':
            if self.controller_pixmap and not self.controller_pixmap.isNull():
                painter.drawPixmap(0, 0, self.controller_pixmap)
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
            scale = min(scale_x, scale_y)  # No padding — accurate curve editing
            
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
            button._invalidate_mask_cache()
            button.update()
            button.changed.emit(button)

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
            button._invalidate_mask_cache()
            button.update()
            button.changed.emit(button)
    
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
        # Use fixed 1px inset to match paintEvent for consistent hit detection
        rect = self.rect().adjusted(1, 1, -1, -1)
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
            scale = min(scale_x, scale_y)  # No padding — accurate curve editing
            
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
        """Start the duplication drag operation with ghost preview setup."""
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

    def handle_duplication_drag(self, event):
        """Handle the visual feedback during duplication drag — update ghost positions."""
        canvas = self.parent()
        if not canvas:
            return
        # Calculate scene-space delta from drag start (zoom-aware)
        delta = event.globalPos() - self.drag_start_pos
        scene_delta = QtCore.QPointF(delta.x(), delta.y()) / canvas.zoom_factor
        # Store current ghost center for paintEvent rendering
        self._dup_ghost_scene_center = QtCore.QPointF(
            self._scene_position.x() + scene_delta.x(),
            self._scene_position.y() + scene_delta.y()
        )
        canvas.update()  # Trigger canvas repaint to show ghosts

    def complete_duplication_drag(self, event):
        """Complete the duplication drag operation — create duplicates at ghost positions."""
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
            if canvas:
                canvas.setCursor(QtCore.Qt.ArrowCursor)

            # Paste at the computed scene position so buttons land where the ghost showed
            canvas.paste_buttons_at_position(paste_scene_pos, mirror=False, is_scene_coords=True)

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
            self.setCursor(QtCore.Qt.DragCopyCursor)
        elif self.edit_mode:
            self.setCursor(QtCore.Qt.OpenHandCursor)
        else:
            self.setCursor(QtCore.Qt.ArrowCursor)
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
            
            # Use already resolved names from the database instead of resolving again
            for obj_data in self.assigned_objects:
                # Extract the short name directly from the long_name in the database
                try:
                    long_name = obj_data['long_name']
                except:
                    long_name = ''
                # Strip namespace for display
                short_name = long_name.split('|')[-1].split(':')[-1]
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
        if canvas:
            # Apply mode change to all selected buttons
            selected_buttons = canvas.get_selected_buttons()
            for button in selected_buttons:
                # Store original height before changing to pose mode
                if mode == 'pose' and button.mode != 'pose':
                    button._original_height = button.height
                    # Set height to 1.25 times width for pose mode
                    button.height = button.width * 1.25

                # Restore original height when changing from pose mode to another mode
                elif button.mode == 'pose' and mode != 'pose' and hasattr(button, '_original_height'):
                    button.height = button._original_height

                # Controller mode: ensure minimum height for slider visibility
                if mode == 'controller':
                    button.height = max(button.height, 40)
                    button._start_controller_sync()
                elif button.mode == 'controller':
                    button._stop_controller_sync()

                button.mode = mode
                button.update()
                button.changed.emit(button)
                canvas.update_button_positions()

                #canvas.update_buttons_for_current_tab()
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

            # Controller mode: ensure minimum height for slider visibility
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

    def _handle_edit_mode_selection(self, event, canvas, shift_held):
        """Handle selection in edit mode"""
        self.dragging = True
        self.drag_start_pos = event.globalPos()
        self.button_start_pos = self.scene_position
        self.setCursor(QtCore.Qt.ClosedHandCursor)

        # Store the initial movement state for constraint calculation
        self._initial_drag_pos = event.globalPos()
        self._constraint_determined = False
        self._constraint_axis = None  # 'x', 'y', or None
        
        selected_buttons = canvas.get_selected_buttons()
        
        if not self.is_selected and not shift_held:
            canvas.clear_selection()
            canvas.buttons_in_current_drag.add(self)
            self.is_selected = True
            self.selected.emit(self, True)
            canvas.last_selected_button = self
            self.update()
        elif shift_held:
            canvas.buttons_in_current_drag.add(self)
            self.selected.emit(self, True)
            self.is_selected = not self.is_selected
            if self.is_selected:
                canvas.last_selected_button = self
            self.selected.emit(self, self.is_selected)
            self.update()
        
        # Store positions for dragging
        for button in selected_buttons:
            button.button_start_pos = button.scene_position
        
        canvas.button_selection_changed.emit()
        self.update()

    def _handle_select_mode_click(self, event, canvas, shift_held, ctrl_held, alt_held):
        """Handle button click in select mode with all modifier combinations"""
        # Only allow selection if the button is selectable
        if not (hasattr(self, 'selectable') and self.selectable):
            return
        
        # Store this button in current drag for selection processing
        canvas.buttons_in_current_drag.clear()
        canvas.buttons_in_current_drag.add(self)
        
        # Store modifier states for selection processing
        canvas.ctrl_held_during_selection = ctrl_held
        canvas.alt_held_during_selection = alt_held
        
        # Handle visual selection state
        if shift_held and ctrl_held:
            # Shift + Ctrl: Remove from selection
            self.is_selected = False
            self.selected.emit(self, False)
        elif shift_held:
            # Shift only: Add to selection (keep current state, will be processed in apply_final_selection)
            self.is_selected = True
            self.selected.emit(self, True)
        else:
            # No modifiers or Alt only: Clear others and select this one
            canvas.clear_selection()
            self.is_selected = True
            self.selected.emit(self, True)
        
        self.update()
        canvas.button_selection_changed.emit()
        # Apply the selection immediately with all modifier states
        canvas.apply_final_selection(shift_held, ctrl_held, alt_held)

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
        menu.setStyleSheet('''
            QMenu {
                background-color: rgba(30, 30, 30, .9);
                color: #ffffff;
                border: 1px solid #444444;
                border-radius: 3px;
                padding: 5px 7px;
            }
            QMenu::item {
                background-color: transparent;
                color: #ffffff;
                padding: 3px 30px 3px 3px; ;
                margin: 3px 0px  ;
                border-radius: 3px;
            }
            QMenu::item:hover {
                background-color: #444444;
            }
            QMenu::item:selected {
                background-color: #444444;
            }
            QMenu::right-arrow {
                width: 10px;
                height: 10px;
            }
            QPushButton {
                border-radius: 3px;
                background-color: #333333;
            }
            QPushButton:hover {
                background-color: #444444;
            }''')


        # Mode selection
        mode_menu = QtWidgets.QMenu("Mode")
        mode_menu.setWindowFlags(mode_menu.windowFlags() | QtCore.Qt.FramelessWindowHint | QtCore.Qt.NoDropShadowWindowHint)
        mode_menu.setAttribute(QtCore.Qt.WA_TranslucentBackground)
        mode_menu.setStyleSheet(menu.styleSheet())
        
        select_action = QAction(QtGui.QIcon(UT.get_icon("select.png")), "Select Mode", self)
        select_action.setCheckable(True)
        select_action.setChecked(self.mode == 'select')
        select_action.triggered.connect(lambda: self.set_mode('select'))
        
        script_action = QAction(QtGui.QIcon(UT.get_icon("code.png")), "Script Mode", self)
        script_action.setCheckable(True)
        script_action.setChecked(self.mode == 'script')
        script_action.triggered.connect(lambda: self.set_mode('script'))
        
        pose_action = QAction(QtGui.QIcon(UT.get_icon("pose_01.png")), "Pose Mode", self)
        pose_action.setCheckable(True)
        pose_action.setChecked(self.mode == 'pose')
        pose_action.triggered.connect(lambda: self.set_mode('pose'))

        controller_action = QAction(QtGui.QIcon(UT.get_icon("preference_icon.png", size=20)), "Controller Mode", self)
        controller_action.setCheckable(True)
        controller_action.setChecked(self.mode == 'controller')
        controller_action.triggered.connect(lambda: self.set_mode('controller'))

        mode_group = QActionGroup(self)
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
                thumbnail_menu = QtWidgets.QMenu("Thumbnail", menu)
                thumbnail_menu.setWindowFlags(thumbnail_menu.windowFlags() | QtCore.Qt.FramelessWindowHint | QtCore.Qt.NoDropShadowWindowHint)
                thumbnail_menu.setAttribute(QtCore.Qt.WA_TranslucentBackground)
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

            # Controller Manager action for controller mode buttons
            if self.mode == 'controller':
                controller_manager_action = menu.addAction(QtGui.QIcon(UT.get_icon('preference_icon.png', size=20)), "Controller Manager")
                controller_manager_action.triggered.connect(self.show_controller_manager)

            #---------------------------------------------------------------------------------------
            # Button placement submenu
            placement_menu = QtWidgets.QMenu("Placement", menu)
            placement_menu.setWindowFlags(placement_menu.windowFlags() | QtCore.Qt.FramelessWindowHint | QtCore.Qt.NoDropShadowWindowHint)
            placement_menu.setAttribute(QtCore.Qt.WA_TranslucentBackground)
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
            shape_menu = QtWidgets.QMenu("Shape", menu)
            shape_menu.setWindowFlags(shape_menu.windowFlags() | QtCore.Qt.FramelessWindowHint | QtCore.Qt.NoDropShadowWindowHint)
            shape_menu.setAttribute(QtCore.Qt.WA_TranslucentBackground)
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
            paste_menu = QtWidgets.QMenu("Paste Options", menu)
            paste_menu.setWindowFlags(paste_menu.windowFlags() | QtCore.Qt.FramelessWindowHint | QtCore.Qt.NoDropShadowWindowHint)
            paste_menu.setAttribute(QtCore.Qt.WA_TranslucentBackground)
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
            elif self.mode == 'controller':
                controller_manager_action = menu.addAction(QtGui.QIcon(UT.get_icon('preference_icon.png', size=20)), "Controller Manager")
                controller_manager_action.triggered.connect(self.show_controller_manager)
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
                add_pose_action = menu.addAction(QtGui.QIcon(UT.get_icon('add.png')),"Add Pose")
                add_pose_action.triggered.connect(self.add_pose)
                
                remove_pose_action = menu.addAction(QtGui.QIcon(UT.get_icon('subtract.png')),"Remove Pose")
                remove_pose_action.triggered.connect(self.remove_pose_for_selected_buttons)

                thumbnail_menu = QtWidgets.QMenu("Thumbnail")
                thumbnail_menu.setWindowFlags(thumbnail_menu.windowFlags() | QtCore.Qt.FramelessWindowHint | QtCore.Qt.NoDropShadowWindowHint)
                thumbnail_menu.setAttribute(QtCore.Qt.WA_TranslucentBackground)
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

                menu.addSeparator()
                capture_anim_action = menu.addAction("Capture Animation")
                capture_anim_action.triggered.connect(self.capture_animation_from_selection)

                if self.is_animation:
                    apply_menu = QtWidgets.QMenu("Apply Animation")
                    # Style the submenu to match
                    apply_menu.setWindowFlags(apply_menu.windowFlags() | QtCore.Qt.FramelessWindowHint | QtCore.Qt.NoDropShadowWindowHint)
                    apply_menu.setAttribute(QtCore.Qt.WA_TranslucentBackground)
                    apply_menu.setStyleSheet(menu.styleSheet())

                    replace_action = apply_menu.addAction("Replace (clear range)")
                    replace_action.triggered.connect(lambda: self.apply_animation('replace'))
                    merge_action = apply_menu.addAction("Merge (overwrite at frame)")
                    merge_action.triggered.connect(lambda: self.apply_animation('merge'))
                    add_action = apply_menu.addAction("Add (offset values)")
                    add_action.triggered.connect(lambda: self.apply_animation('add'))
                    menu.addMenu(apply_menu)

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
    
    def show_selection_manager(self):
        if not hasattr(self, 'selection_manager'):
            self.selection_manager = SelectionManagerWidget()
        
        self.selection_manager.set_picker_button(self)
        
        # Position widget to the right of the button
        pos = self.mapToGlobal(self.rect().topRight())
        self.selection_manager.move(pos + QtCore.QPoint(10, 0))
        self.selection_manager.show()

    def show_script_manager(self):
        if not hasattr(self, 'script_manager'):
            self.script_manager = ScriptManagerWidget()
        
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
            
            # Build position update dictionary
            position_updates = {}
            for button in selected_buttons:
                position_updates[button.unique_id] = (
                    button.scene_position.x(), 
                    button.scene_position.y()
                )
            
            # Single database update for all positions
            updated_count = 0
            for button_data in tab_data['buttons']:
                if button_data['id'] in position_updates:
                    new_x, new_y = position_updates[button_data['id']]
                    button_data['position'] = (new_x, new_y)
                    updated_count += 1
            
            # Write to database once
            if updated_count > 0:
                #DM.PickerDataManager.update_tab_data(current_tab, tab_data)
                DM.PickerDataManager.batch_update_buttons(current_tab, DM.PickerDataManager.get_tab_data(current_tab)['buttons'])
                #print(f"Batch updated positions for {updated_count} buttons")
            
            # Reconnect signals properly
            for button in selected_buttons:
                # Reconnect to the main window's handler
                if hasattr(main_window, 'on_button_changed'):
                    button.changed.connect(main_window.on_button_changed)
                else:
                    # Fallback connection
                    button.changed.connect(main_window.update_button_data)
            
        except Exception as e:
            print(f"Error during batch position update: {e}")
            
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
            
            # Update transform guides once at the end
            canvas = self.parent()
            if canvas and hasattr(canvas, 'transform_guides') and canvas.transform_guides.isVisible():
                QtCore.QTimer.singleShot(50, canvas.transform_guides.update_selection)

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
        """Enhanced paste method that handles different types of paste operations"""
        canvas = self.parent()
        if canvas and canvas.edit_mode:
            attributes = ButtonClipboard.instance().get_last_attributes()
            if attributes:
                selected_buttons = canvas.get_selected_buttons()
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
                        button.animation_data = attributes.get('animation_data', {}).copy() if attributes.get('animation_data') else {}

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
                        button.animation_data = attributes.get('animation_data', {}).copy() if attributes.get('animation_data') else {}
                    elif paste_type == 'text':
                        # Paste only the label text
                        button.label = attributes['label']
                    
                    button.update()
                    button.update_tooltip()
                    button.changed.emit(button)
    #---------------------------------------------------------------------------------------
    def set_script_data(self, data):
        self.script_data = data
        self.changed.emit(self)
        #self.update_tooltip()
        self._tooltip_needs_update = True 
        
    def add_pose(self):
        """Add current pose of selected objects to the pose data"""
        import maya.cmds as cmds
        
        # Get currently selected objects in Maya
        selected_objects = cmds.ls(selection=True, long=True)
        if not selected_objects:
            # Use custom dialog instead of QMessageBox
            dialog = CD.CustomDialog(self, title="No Selection", size=(200, 80), info_box=True)
            message_label = QtWidgets.QLabel("Please select objects in Maya before adding a pose.")
            message_label.setWordWrap(True)
            dialog.add_widget(message_label)
            dialog.add_button_box()
            dialog.exec_()
            return
        
        # First, add the selected objects to the button's assigned objects
        self.assigned_objects = []  # Clear existing assignments
        for obj in selected_objects:
            try:
                # Get the UUID for the object
                uuid = cmds.ls(obj, uuid=True)[0]
                # Add to assigned objects
                self.assigned_objects.append({
                    'uuid': uuid,
                    'long_name': obj
                })
            except:
                continue
        
        # Store the current attribute values for all assigned objects
        pose_data = {}
        
        for obj_data in self.assigned_objects:
            try:
                # Get the object from the data
                obj = obj_data['long_name']
                
                if cmds.objExists(obj):
                    # Extract the base name without namespace for storage
                    # This makes poses reusable across different namespaces
                    base_name = obj.split('|')[-1].split(':')[-1]
                    
                    # Get all keyable attributes
                    attrs = cmds.listAttr(obj, keyable=True) or []
                    attr_values = {}
                    
                    for attr in attrs:
                        try:
                            full_attr = f"{obj}.{attr}"
                            if cmds.objExists(full_attr):
                                attr_values[attr] = cmds.getAttr(full_attr)
                        except:
                            continue
                            
                    if attr_values:
                        # Store with base name for namespace compatibility
                        pose_data[base_name] = attr_values
            except:
                continue
        
        # Update the tooltip with the new assigned objects
        #self.update_tooltip()
        self._tooltip_needs_update = True 
        
        if pose_data:
            # Use a simple default name - the button itself represents the pose
            self.pose_data = {"default": pose_data}  # Replace any existing poses with this one
            self.changed.emit(self)
            dialog = CD.CustomDialog(self, title="Pose Added", size=(200, 80), info_box=True)
            message_label = QtWidgets.QLabel("Pose has been added successfully.")
            message_label.setWordWrap(True)
            dialog.add_widget(message_label)
            dialog.add_button_box()
            #dialog.exec_()
        else:
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
    # ANIMATION DATA MANAGEMENT
    #---------------------------------------------------------------------------------------
    def capture_animation_data(self, frame_start=None, frame_end=None):
        """Capture animation keyframe data from Maya for assigned objects."""
        import maya.cmds as cmds

        if frame_start is None:
            frame_start = cmds.playbackOptions(q=True, min=True)
        if frame_end is None:
            frame_end = cmds.playbackOptions(q=True, max=True)

        current_namespace = self._get_current_namespace()

        # Resolve assigned objects with namespace
        nodes = []
        for obj_data in self.assigned_objects:
            node_name = obj_data.get('long_name', '') if isinstance(obj_data, dict) else str(obj_data)
            if current_namespace:
                node_name = current_namespace + ':' + node_name.split(':')[-1]
            if cmds.objExists(node_name):
                nodes.append(node_name)

        if not nodes:
            return None

        nodes_anim_data = {}
        for node in nodes:
            # Get all animated attributes
            anim_attrs = cmds.listAnimatable(node) or []
            node_data = {}
            for attr_path in anim_attrs:
                # attr_path is like "namespace:nodeName.translateX"
                attr_name = attr_path.split('.')[-1]
                full_attr = f"{node}.{attr_name}"

                # Get keyframe times in range
                times = cmds.keyframe(full_attr, q=True, time=(frame_start, frame_end), timeChange=True) or []
                if not times:
                    continue

                values = cmds.keyframe(full_attr, q=True, time=(frame_start, frame_end), valueChange=True) or []
                in_tangent_types = cmds.keyTangent(full_attr, q=True, time=(frame_start, frame_end), inTangentType=True) or []
                out_tangent_types = cmds.keyTangent(full_attr, q=True, time=(frame_start, frame_end), outTangentType=True) or []
                in_weights = cmds.keyTangent(full_attr, q=True, time=(frame_start, frame_end), inWeight=True) or []
                out_weights = cmds.keyTangent(full_attr, q=True, time=(frame_start, frame_end), outWeight=True) or []
                in_angles = cmds.keyTangent(full_attr, q=True, time=(frame_start, frame_end), inAngle=True) or []
                out_angles = cmds.keyTangent(full_attr, q=True, time=(frame_start, frame_end), outAngle=True) or []

                keyframes = []
                for i, t in enumerate(times):
                    kf = [
                        t - frame_start,  # frame offset
                        values[i] if i < len(values) else 0,
                        in_tangent_types[i] if i < len(in_tangent_types) else 'auto',
                        out_tangent_types[i] if i < len(out_tangent_types) else 'auto',
                        in_weights[i] if i < len(in_weights) else 1.0,
                        out_weights[i] if i < len(out_weights) else 1.0,
                        in_angles[i] if i < len(in_angles) else 0.0,
                        out_angles[i] if i < len(out_angles) else 0.0,
                    ]
                    keyframes.append(kf)

                if keyframes:
                    node_data[attr_name] = {"keyframes": keyframes}

            if node_data:
                # Store using the short name (without namespace) for portability
                short_name = node.split(':')[-1]
                nodes_anim_data[short_name] = {"channels": node_data}

        if not nodes_anim_data:
            return None

        return {
            "type": "animation",
            "version": 1,
            "frame_range": [frame_start, frame_end],
            "frame_count": int(frame_end - frame_start + 1),
            "source_fps": cmds.currentUnit(q=True, time=True),
            "nodes": nodes_anim_data
        }

    def _save_animation_data(self, animation_data):
        """Save captured animation data to the button."""
        self.animation_data = animation_data
        self.pose_data = {}  # Clear single-frame pose
        self.pose_pixmap = None
        self._tooltip_needs_update = True
        self.changed.emit(self)
        self.update()

    def apply_animation(self, apply_mode='replace'):
        """Apply stored animation keyframe data at the current playhead position."""
        import maya.cmds as cmds

        if not self.animation_data:
            return

        current_namespace = self._get_current_namespace()
        base_frame = cmds.currentTime(q=True)
        frame_count = self.animation_data.get('frame_count', 1)

        cmds.undoInfo(openChunk=True)
        try:
            for short_name, node_data in self.animation_data.get('nodes', {}).items():
                # Resolve with namespace
                if current_namespace:
                    node_name = current_namespace + ':' + short_name
                else:
                    node_name = short_name

                if not cmds.objExists(node_name):
                    continue

                for attr_name, attr_data in node_data.get('channels', {}).items():
                    full_attr = f"{node_name}.{attr_name}"

                    if apply_mode == 'replace':
                        # Remove existing keys in target range
                        target_start = base_frame
                        target_end = base_frame + frame_count
                        cmds.cutKey(full_attr, time=(target_start, target_end), clear=True)

                    for kf in attr_data.get('keyframes', []):
                        frame_offset, value, in_tt, out_tt, in_w, out_w, in_a, out_a = kf
                        target_frame = base_frame + frame_offset

                        if apply_mode == 'add':
                            existing = cmds.getAttr(full_attr, time=target_frame)
                            value = existing + value

                        cmds.setKeyframe(node_name, attribute=attr_name, time=target_frame, value=value)
                        cmds.keyTangent(full_attr, time=(target_frame, target_frame),
                                       inTangentType=in_tt, outTangentType=out_tt,
                                       inWeight=in_w, outWeight=out_w,
                                       inAngle=in_a, outAngle=out_a)
        finally:
            cmds.undoInfo(closeChunk=True)

    def capture_animation_from_selection(self):
        """Capture animation from the current timeline range."""
        import maya.cmds as cmds
        anim_data = self.capture_animation_data()
        if anim_data:
            self._save_animation_data(anim_data)
            print(f"Captured animation: {anim_data['frame_count']} frames, {len(anim_data['nodes'])} nodes")
        else:
            cmds.warning("No animation data found for assigned objects in the current frame range.")

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
        """Take a playblast of the current Maya viewport and use it as a thumbnail"""
        import maya.cmds as cmds
        import tempfile
        import os
        
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
        
        # Get the thumbnail directory from the main window
        main_window = None
        for widget in QtWidgets.QApplication.topLevelWidgets():
            if widget.__class__.__name__ == 'AnimPickerWindow':
                main_window = widget
                break
        
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
        
        # Generate a unique filename with sequential numbering
        # Find the highest existing thumbnail number
        highest_num = 0
        if os.path.exists(thumbnail_dir):
            for existing_file in os.listdir(thumbnail_dir):
                if existing_file.startswith('thumbnail_') and existing_file.endswith('.jpg'):
                    try:
                        # Extract the number part from the filename
                        num_part = existing_file.replace('thumbnail_', '').replace('.jpg', '')
                        if num_part.isdigit():
                            num = int(num_part)
                            highest_num = max(highest_num, num)
                    except:
                        pass
        
        # Create new filename with incremented number (3 digits format)
        next_num = highest_num + 1
        # Use just the base name without extension for playblast - Maya will add its own extension
        base_filename = f"thumbnail_{next_num:03d}"
        filepath = os.path.join(thumbnail_dir, base_filename)
        
        # Take the playblast using Maya's playblast command
        try:
            # Get the active panel
            panel = cmds.getPanel(withFocus=True)
            if not panel or 'modelPanel' not in cmds.getPanel(typeOf=panel):
                panel = cmds.getPanel(type="modelPanel")[0]
            
            # Get the active viewport dimensions to maintain aspect ratio
            active_view = None
            if panel and 'modelPanel' in cmds.getPanel(typeOf=panel):
                active_view = cmds.playblast(activeEditor=True)
            
            # Get viewport width and height
            viewport_width = cmds.control(active_view, query=True, width=True)
            viewport_height = cmds.control(active_view, query=True, height=True)
            
            # Calculate aspect ratio and adjust dimensions while keeping max dimension at 200px
            aspect_ratio = float(viewport_width) / float(viewport_height)
            img_size = 500
            if aspect_ratio >= 1.0:  # Wider than tall
                width = img_size
                height = int(img_size / aspect_ratio)
            else:  # Taller than wide
                height = img_size
                width = int(500 * aspect_ratio)
            
            cmds.playblast(
                frame=cmds.currentTime(query=True),
                format="image",
                compression="jpg",
                quality=100,
                width=width,
                height=height,
                percent=100,
                viewer=False,
                showOrnaments=False,
                filename=filepath,
                clearCache=True,
                framePadding=0
            )
            
            # Maya adds a frame number and extension to the filename, so we need to find the actual file
            dirname = os.path.dirname(filepath)
            basename = os.path.basename(filepath)
            
            # Find the generated file - Maya adds frame number and extension
            actual_filepath = None
            for f in os.listdir(dirname):
                # Look for files that start with our base filename and have an image extension
                if f.startswith(basename) and (f.endswith('.jpg') or f.endswith('.jpeg')):
                    actual_filepath = os.path.join(dirname, f)
                    break
                    
            if not actual_filepath:
                raise Exception("Could not find generated thumbnail image")
            
            # Load the original image into a pixmap
            original_pixmap = QtGui.QPixmap(actual_filepath)
            
            # Crop the image to a 1:1 aspect ratio (square)
            # Calculate the center and the size of the crop
            orig_width = original_pixmap.width()
            orig_height = original_pixmap.height()
            crop_size = min(orig_width, orig_height)
            
            # Calculate the crop rectangle centered in the image
            x_offset = (orig_width - crop_size) // 2
            y_offset = (orig_height - crop_size) // 2
            crop_rect = QtCore.QRect(x_offset, y_offset, crop_size, crop_size)
            
            # Crop the pixmap to a square
            cropped_pixmap = original_pixmap.copy(crop_rect)
            
            # Save the cropped square image with our intended filename format
            final_filename = f"thumbnail_{next_num:03d}.jpg"  # Use our sequential naming format
            final_filepath = os.path.join(thumbnail_dir, final_filename)
            cropped_pixmap.save(final_filepath, 'JPG', 100)
            
            # Remove the original playblast file to avoid clutter
            try:
                if os.path.exists(actual_filepath) and actual_filepath != final_filepath:
                    os.remove(actual_filepath)
            except Exception as e:
                print(f"Warning: Could not remove original playblast file: {e}")
            
            # Apply the thumbnail to all selected pose buttons
            for button in pose_buttons:
                # Store the image path with our clean naming format
                button.thumbnail_path = final_filepath
                
                # Set the thumbnail pixmap
                button.thumbnail_pixmap = cropped_pixmap
                
                # Force regeneration of the pose_pixmap by invalidating cache parameters
                button.pose_pixmap = None
                button.last_zoom_factor = 0
                button.last_size = None
                
                # Update the button
                button.update()
                button.update_tooltip()
                button.changed.emit(button)
                
            # No need to remove the original image as we've overwritten it with the square version
                
            
            
        except Exception as e:
            # Show error message
            dialog = CD.CustomDialog(self, title="Error", size=(250, 100), info_box=True)
            message_label = QtWidgets.QLabel(f"Failed to take playblast: {str(e)}")
            message_label.setWordWrap(True)
            dialog.add_widget(message_label)
            dialog.add_button_box()
            dialog.exec_()
    
    def update_thumbnail(self):
        """Take a playblast of the current Maya viewport and update the existing thumbnail"""
        import maya.cmds as cmds
        import tempfile
        import os
        
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
                message_label = QtWidgets.QLabel("No pose buttons with thumbnails selected. Please select at least one button in pose mode with an existing thumbnail.")
                message_label.setWordWrap(True)
                dialog.add_widget(message_label)
                dialog.add_button_box()
                dialog.exec_()
                return
        
        # Take the playblast using Maya's playblast command
        try:
            # Get the active panel
            panel = cmds.getPanel(withFocus=True)
            if not panel or 'modelPanel' not in cmds.getPanel(typeOf=panel):
                panel = cmds.getPanel(type="modelPanel")[0]
            
            # Get the active viewport dimensions to maintain aspect ratio
            active_view = None
            if panel and 'modelPanel' in cmds.getPanel(typeOf=panel):
                active_view = cmds.playblast(activeEditor=True)
            
            # Get viewport width and height
            viewport_width = cmds.control(active_view, query=True, width=True)
            viewport_height = cmds.control(active_view, query=True, height=True)
            
            # Calculate aspect ratio and adjust dimensions while keeping max dimension at 500px
            aspect_ratio = float(viewport_width) / float(viewport_height)
            img_size = 500
            if aspect_ratio >= 1.0:  # Wider than tall
                width = img_size
                height = int(img_size / aspect_ratio)
            else:  # Taller than wide
                height = img_size
                width = int(500 * aspect_ratio)
            
            # Create a temporary file for the playblast
            temp_dir = tempfile.gettempdir()
            temp_filepath = os.path.join(temp_dir, "temp_thumbnail")
            
            cmds.playblast(
                frame=cmds.currentTime(query=True),
                format="image",
                compression="jpg",
                quality=100,
                width=width,
                height=height,
                percent=100,
                viewer=False,
                showOrnaments=False,
                filename=temp_filepath,
                clearCache=True,
                framePadding=0
            )
            
            # Maya adds a frame number and extension to the filename, so we need to find the actual file
            dirname = os.path.dirname(temp_filepath)
            basename = os.path.basename(temp_filepath)
            
            # Find the generated file - Maya adds frame number and extension
            actual_filepath = None
            for f in os.listdir(dirname):
                # Look for files that start with our base filename and have an image extension
                if f.startswith(basename) and (f.endswith('.jpg') or f.endswith('.jpeg')):
                    actual_filepath = os.path.join(dirname, f)
                    break
                    
            if not actual_filepath:
                raise Exception("Could not find generated thumbnail image")
            
            # Load the original image into a pixmap
            original_pixmap = QtGui.QPixmap(actual_filepath)
            
            # Crop the image to a 1:1 aspect ratio (square)
            # Calculate the center and the size of the crop
            orig_width = original_pixmap.width()
            orig_height = original_pixmap.height()
            crop_size = min(orig_width, orig_height)
            
            # Calculate the crop rectangle centered in the image
            x_offset = (orig_width - crop_size) // 2
            y_offset = (orig_height - crop_size) // 2
            crop_rect = QtCore.QRect(x_offset, y_offset, crop_size, crop_size)
            
            # Crop the pixmap to a square
            cropped_pixmap = original_pixmap.copy(crop_rect)
            
            # Update all selected pose buttons with thumbnails
            for button in pose_buttons_with_thumbnails:
                # Get the existing thumbnail path
                existing_path = button.thumbnail_path
                
                # Save the cropped square image to the existing path
                cropped_pixmap.save(existing_path, 'JPG', 100)
                
                # Update the thumbnail pixmap
                button.thumbnail_pixmap = cropped_pixmap
                
                # Force regeneration of the pose_pixmap by invalidating cache parameters
                button.pose_pixmap = None
                button.last_zoom_factor = 0
                button.last_size = None
                
                # Update the button
                button.update()
                button.update_tooltip()
                button.changed.emit(button)
            
            # Remove the temporary playblast file
            try:
                if os.path.exists(actual_filepath):
                    os.remove(actual_filepath)
            except Exception as e:
                print(f"Warning: Could not remove temporary playblast file: {e}")
                
        except Exception as e:
            # Show error message
            dialog = CD.CustomDialog(self, title="Error", size=(250, 100), info_box=True)
            message_label = QtWidgets.QLabel(f"Failed to update thumbnail: {str(e)}")
            message_label.setWordWrap(True)
            dialog.add_widget(message_label)
            dialog.add_button_box()
            dialog.exec_()
    
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
    
    def repath_thumbnails_for_selected_buttons(self):
        """Repath thumbnails for selected pose buttons by choosing a new directory"""
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
        """Apply the stored pose to the assigned objects"""
        import maya.cmds as cmds
        
        # Validate pose data
        if not self._validate_pose_data():
            return
        
        pose_data = self.pose_data["default"]
        current_namespace = self._get_current_namespace()
        successfully_posed_objects = []
        
        # Apply pose within undo chunk
        cmds.undoInfo(openChunk=True, chunkName="Apply Pose")
        
        try:
            for obj_name, attr_values in pose_data.items():
                resolved_obj = self._resolve_object_name(obj_name, current_namespace)
                
                if resolved_obj:
                    if self._apply_object_attributes(resolved_obj, attr_values):
                        successfully_posed_objects.append(self._get_full_path(resolved_obj))
            
            # Select successfully posed objects
            if successfully_posed_objects:
                self._select_objects(successfully_posed_objects)
                
        except Exception as e:
            self._show_error_dialog("Error applying pose", str(e))
        finally:
            cmds.undoInfo(closeChunk=True)

    def _validate_pose_data(self):
        """Validate that pose data exists and is not empty"""
        if not self.pose_data:
            '''self._show_info_dialog("No Pose", "There is no pose to apply. Please add a pose first.")'''
            print("No pose data found. Please add a pose first.")
            return False
        
        pose_data = self.pose_data.get("default", {})
        if not pose_data:
            self._show_info_dialog("Empty Pose", "Pose does not contain any data.")
            return False
        
        return True

    def _get_current_namespace(self):
        """Get the current namespace from the main window"""
        main_window = self.window()
        if hasattr(main_window, 'namespace_dropdown'):
            namespace = main_window.namespace_dropdown.currentText()
            return namespace if namespace != 'None' else None
        return None

    def _resolve_object_name(self, obj_name, current_namespace):
        """Resolve object name considering namespace and hierarchy"""
        import maya.cmds as cmds
        
        # Try original object name first
        if cmds.objExists(obj_name):
            return obj_name
        
        # Extract base name for namespace resolution
        base_name = obj_name.split('|')[-1].split(':')[-1]
        
        # Try with current namespace
        if current_namespace:
            namespaced_obj = f"{current_namespace}:{base_name}"
            if cmds.objExists(namespaced_obj):
                return namespaced_obj
        
        # Try base name only
        if cmds.objExists(base_name):
            try:
                full_paths = cmds.ls(base_name, long=True)
                return full_paths[0] if full_paths else base_name
            except Exception:
                return base_name
        
        return None

    def _apply_object_attributes(self, obj_name, attr_values):
        """Apply attribute values to an object"""
        import maya.cmds as cmds
        
        success = False
        for attr, value in attr_values.items():
            if self._set_attribute(obj_name, attr, value):
                success = True
        
        return success

    def _set_attribute(self, obj_name, attr, value):
        """Set a single attribute value with error handling"""
        import maya.cmds as cmds
        
        try:
            full_attr = f"{obj_name}.{attr}"
            
            if not cmds.objExists(full_attr) or cmds.getAttr(full_attr, lock=True):
                return False
            
            if isinstance(value, list):
                for i, val in enumerate(value):
                    cmds.setAttr(f"{full_attr}[{i}]", val)
            else:
                cmds.setAttr(full_attr, value)
            
            return True
            
        except Exception as e:
            print(f"Error setting attribute {full_attr}: {e}")
            return False

    def _get_full_path(self, obj_name):
        """Get the full path of an object for unique identification"""
        import maya.cmds as cmds
        
        try:
            full_paths = cmds.ls(obj_name, long=True)
            return full_paths[0] if full_paths else obj_name
        except Exception:
            return obj_name

    def _select_objects(self, objects):
        """Select the given objects with error handling"""
        import maya.cmds as cmds
        
        try:
            cmds.select(objects, replace=True)
        except Exception as e:
            print(f"Error selecting posed objects: {e}")

    def _show_info_dialog(self, title, message):
        """Show an information dialog"""
        dialog = CD.CustomDialog(self, title=title, size=(200, 80), info_box=True)
        message_label = QtWidgets.QLabel(message)
        message_label.setWordWrap(True)
        dialog.add_widget(message_label)
        dialog.add_button_box()
        dialog.exec_()

    def _show_error_dialog(self, title, message):
        """Show an error dialog"""
        dialog = CD.CustomDialog(self, title=title, size=(200, 80), info_box=True)
        message_label = QtWidgets.QLabel(f"{title}: {message}")
        message_label.setWordWrap(True)
        dialog.add_widget(message_label)
        dialog.add_button_box()
        dialog.exec_()
    #---------------------------------------------------------------------------------------
    def apply_mirrored_pose(self, L="", R="", custom_flip_controls=None, auto_detect_orientation=True):
        """
        Apply the stored pose to the mirrored counterparts of the assigned objects.
        
        This function takes the stored pose data and applies it to the opposing limb objects.
        For example, if the pose contains L_arm data, it will apply the mirrored values to R_arm.
        
        Args:
            L (str, optional): Custom left side identifier. Default is "".
            R (str, optional): Custom right side identifier. Default is "".
            custom_flip_controls (dict, optional): Dictionary of controls that need custom flipping logic.
                Format: {"control_name": {"attrs": ["attr1", "attr2"], "flip": True/False}}
            auto_detect_orientation (bool, optional): If True, automatically determines which attributes
                need to be flipped based on the control's world orientation. Default is True.
        """
        import maya.cmds as cmds
        import json
        
        # Validate pose data
        if not self._validate_pose_data():
            return
        
        pose_data = self.pose_data["default"]
        current_namespace = self._get_current_namespace()
        
        # Initialize mirroring components
        naming_conventions = self._get_naming_conventions(L, R)
        custom_flip_controls = custom_flip_controls or {}
        successfully_posed_objects = []
        
        # Apply mirrored pose within undo chunk
        cmds.undoInfo(openChunk=True, chunkName="Apply Mirrored Pose")
        
        try:
            # Auto-detect orientation if enabled
            if auto_detect_orientation:
                orientation_data = self._collect_orientation_data_for_pose(pose_data, current_namespace, cmds)
                custom_flip_controls = self._analyze_orientations_for_pose(pose_data, orientation_data, naming_conventions, custom_flip_controls, current_namespace, cmds)
            
            # Load mirror preferences for all objects in pose data
            mirror_preferences = self._load_mirror_preferences_for_pose(pose_data, current_namespace, cmds)
            
            # Process each object in the pose data
            for obj_name, attr_values in pose_data.items():
                resolved_source_obj = self._resolve_object_name(obj_name, current_namespace)
                
                if resolved_source_obj:
                    # Find the mirrored object
                    namespace, short_name = self._extract_namespace_and_name(resolved_source_obj)
                    mirrored_name, is_center_object = self._find_mirrored_name(short_name, naming_conventions, mirror_preferences, namespace)
                    
                    if cmds.objExists(mirrored_name):
                        # Apply mirrored attributes to the target object
                        mirrored_attrs = self._calculate_mirrored_attributes(
                            attr_values, short_name, is_center_object, custom_flip_controls, mirror_preferences
                        )
                        
                        if self._apply_object_attributes(mirrored_name, mirrored_attrs):
                            successfully_posed_objects.append(self._get_full_path(mirrored_name))
                            #print(f"Applied mirrored pose from {resolved_source_obj} to {mirrored_name}")
                    else:
                        print(f"Mirrored object {mirrored_name} does not exist for {resolved_source_obj}")
            
            # Select successfully posed objects
            if successfully_posed_objects:
                self._select_objects(successfully_posed_objects)
            else:
                cmds.warning("Could not find any matching objects to apply the mirrored pose to. "
                                    "Please check that your objects follow standard naming conventions.")
                
        except Exception as e:
            self._show_error_dialog("Error applying mirrored pose", str(e))
        finally:
            cmds.undoInfo(closeChunk=True)

    def _get_naming_conventions(self, L, R):
        """
        Returns a list of naming conventions for left and right sides.
        
        Args:
            L (str): Custom left side identifier
            R (str): Custom right side identifier
            
        Returns:
            list: List of dictionaries with left and right patterns
        """
        naming_conventions = [
            # Prefix
            {"left": "L_", "right": "R_"},
            {"left": "left_", "right": "right_"},
            {"left": "Lf_", "right": "Rt_"},
            {"left": "lt_", "right": "rt_"},
            
            # Suffix
            {"left": "_L", "right": "_R"},
            {"left": "_left", "right": "_right"},
            {"left": "_lt", "right": "_rt"},
            {"left": "_lf", "right": "_rf"},
            {"left": "_l_", "right": "_r_"},
            
            # Other patterns
            {"left": ":l_", "right": ":r_"},
            {"left": "^l_", "right": "^r_"},
            {"left": "_l$", "right": "_r$"},
            {"left": ":L", "right": ":R"},
            {"left": "^L", "right": "^R"},
            {"left": "Left", "right": "Right"},
            {"left": "left", "right": "right"}
        ]
        
        # Add custom naming convention if provided
        if L and R:
            naming_conventions.append({"left": L, "right": R})
            
        return naming_conventions

    def _extract_namespace_and_name(self, full_name):
        """
        Extracts namespace and object name from a full object path.
        
        Args:
            full_name (str): Full object name with potential namespace
            
        Returns:
            tuple: (namespace, short_name) where namespace includes the colon if present
        """
        # Handle long names (with |) - get the leaf name first
        leaf_name = full_name.split('|')[-1]
        
        # Check for namespace
        if ':' in leaf_name:
            parts = leaf_name.split(':')
            namespace = ':'.join(parts[:-1]) + ':'  # Keep the colon
            short_name = parts[-1]
        else:
            namespace = ""
            short_name = leaf_name
        
        return namespace, short_name

    def _construct_full_name(self, namespace, short_name):
        """
        Constructs full object name with namespace.
        
        Args:
            namespace (str): Namespace with colon if present
            short_name (str): Short object name
            
        Returns:
            str: Full object name
        """
        return f"{namespace}{short_name}" if namespace else short_name

    def _find_mirrored_name(self, obj_name, naming_conventions, mirror_preferences=None, namespace=""):
        """
        Finds the mirrored name for the given object name.
        
        Args:
            obj_name (str): Object name to find mirror for (short name without namespace)
            naming_conventions (list): List of naming conventions
            mirror_preferences (dict, optional): Dictionary of mirror preferences
            namespace (str, optional): Namespace to apply to the mirrored name
            
        Returns:
            tuple: (mirrored_name, is_center_object) where mirrored_name is the full name of the mirrored object
                and is_center_object is a boolean indicating if the object is a center object
        """
        # Check if we have a mirror preference with a counterpart defined
        if mirror_preferences:
            # First check if this object has preferences with a counterpart defined
            if obj_name in mirror_preferences:
                pref_data = mirror_preferences[obj_name]
                if "counterpart" in pref_data and pref_data["counterpart"]:
                    counterpart = pref_data["counterpart"]
                    # Apply namespace to counterpart
                    full_counterpart = self._construct_full_name(namespace, counterpart)
                    return full_counterpart, False
            
            # If not, check if any object has this object defined as its counterpart
            for other_obj, pref_data in mirror_preferences.items():
                if "counterpart" in pref_data and pref_data["counterpart"] == obj_name:
                    # Apply namespace to the other object
                    full_other = self._construct_full_name(namespace, other_obj)
                    return full_other, False
        
        is_center_object = True  # Assume it's a center object until proven otherwise
        
        for convention in naming_conventions:
            left_pattern = convention["left"]
            right_pattern = convention["right"]
            
            if left_pattern in obj_name:
                is_center_object = False
                mirrored_short_name = obj_name.replace(left_pattern, right_pattern)
                mirrored_name = self._construct_full_name(namespace, mirrored_short_name)
                return mirrored_name, is_center_object
            elif right_pattern in obj_name:
                is_center_object = False
                mirrored_short_name = obj_name.replace(right_pattern, left_pattern)
                mirrored_name = self._construct_full_name(namespace, mirrored_short_name)
                return mirrored_name, is_center_object
        
        # If no pattern matched, it's a center object - return with namespace
        full_name = self._construct_full_name(namespace, obj_name)
        return full_name, is_center_object

    def _collect_orientation_data_for_pose(self, pose_data, current_namespace, cmds):
        """
        Collects orientation data for objects in the pose data.
        
        Args:
            pose_data (dict): Dictionary of pose data
            current_namespace (str): Current namespace
            cmds: Maya commands module
            
        Returns:
            dict: Dictionary mapping object names to orientation data
        """
        orientation_data = {}
        
        for obj_name in pose_data.keys():
            resolved_obj = self._resolve_object_name(obj_name, current_namespace)
            if resolved_obj and cmds.objExists(resolved_obj):
                namespace, short_name = self._extract_namespace_and_name(resolved_obj)
                
                try:
                    # Get world matrix
                    world_matrix = cmds.xform(resolved_obj, query=True, matrix=True, worldSpace=True)
                    
                    # Extract orientation vectors from the matrix
                    x_axis = [world_matrix[0], world_matrix[1], world_matrix[2]]
                    y_axis = [world_matrix[4], world_matrix[5], world_matrix[6]]
                    z_axis = [world_matrix[8], world_matrix[9], world_matrix[10]]
                    
                    # Store orientation data using the resolved object name as key
                    orientation_data[resolved_obj] = {
                        'x_axis': x_axis,
                        'y_axis': y_axis,
                        'z_axis': z_axis,
                        'namespace': namespace,
                        'short_name': short_name
                    }
                    
                    #print(f"Collected orientation data for {resolved_obj}")
                except Exception as e:
                    print(f"Error collecting orientation data for {resolved_obj}: {e}")
        
        return orientation_data

    def _analyze_orientations_for_pose(self, pose_data, orientation_data, naming_conventions, custom_flip_controls, current_namespace, cmds):
        """
        Analyzes orientations of pose objects and their mirrors to determine custom flipping logic.
        
        Args:
            pose_data (dict): Dictionary of pose data
            orientation_data (dict): Dictionary of orientation data
            naming_conventions (list): List of naming conventions
            custom_flip_controls (dict): Dictionary of custom flip controls
            current_namespace (str): Current namespace
            cmds: Maya commands module
            
        Returns:
            dict: Updated custom_flip_controls dictionary
        """
        for obj_name in pose_data.keys():
            resolved_obj = self._resolve_object_name(obj_name, current_namespace)
            
            # Skip if we don't have orientation data for this control
            if not resolved_obj or resolved_obj not in orientation_data:
                continue
            
            obj_data = orientation_data[resolved_obj]
            namespace = obj_data['namespace']
            short_name = obj_data['short_name']
            
            # Find the mirrored object name
            mirrored_name, _ = self._find_mirrored_name(short_name, naming_conventions, namespace=namespace)
            
            # Skip if we couldn't find a mirrored name or it doesn't exist
            if mirrored_name == resolved_obj or not cmds.objExists(mirrored_name):
                continue
            
            # Collect orientation data for the mirrored object if we don't have it
            if mirrored_name not in orientation_data:
                try:
                    world_matrix = cmds.xform(mirrored_name, query=True, matrix=True, worldSpace=True)
                    x_axis = [world_matrix[0], world_matrix[1], world_matrix[2]]
                    y_axis = [world_matrix[4], world_matrix[5], world_matrix[6]]
                    z_axis = [world_matrix[8], world_matrix[9], world_matrix[10]]
                    
                    mirror_namespace, mirror_short_name = self._extract_namespace_and_name(mirrored_name)
                    orientation_data[mirrored_name] = {
                        'x_axis': x_axis,
                        'y_axis': y_axis,
                        'z_axis': z_axis,
                        'namespace': mirror_namespace,
                        'short_name': mirror_short_name
                    }
                except Exception as e:
                    print(f"Error collecting orientation data for mirror {mirrored_name}: {e}")
                    continue
            
            # Compare orientations between the control and its mirror
            obj_orient = orientation_data[resolved_obj]
            mirror_orient = orientation_data[mirrored_name]
            
            # Initialize custom flip data for this control if not already present
            # Use short name as key for consistency
            if short_name not in custom_flip_controls:
                custom_flip_controls[short_name] = {"attrs": [], "flip": {}}
            
            # Analyze X axis (affects rotateX)
            x_dot_product = obj_orient['x_axis'][0] * -mirror_orient['x_axis'][0]  # Negate for mirror reflection
            if x_dot_product < 0:  # Standard case
                custom_flip_controls[short_name]["flip"]["rotateX"] = True
            else:  # Needs custom handling
                custom_flip_controls[short_name]["attrs"].append("rotateX")
                custom_flip_controls[short_name]["flip"]["rotateX"] = False
                #print(f"Auto-detected custom flipping for {short_name}.rotateX")
            
            # Analyze Y axis (affects rotateY)
            y_dot_product = obj_orient['y_axis'][1] * mirror_orient['y_axis'][1]  # No negation for Y
            if y_dot_product > 0:  # Standard case
                custom_flip_controls[short_name]["flip"]["rotateY"] = True
            else:  # Needs custom handling
                custom_flip_controls[short_name]["attrs"].append("rotateY")
                custom_flip_controls[short_name]["flip"]["rotateY"] = False
                #print(f"Auto-detected custom flipping for {short_name}.rotateY")
            
            # Analyze Z axis (affects rotateZ)
            z_dot_product = obj_orient['z_axis'][2] * mirror_orient['z_axis'][2]  # No negation for Z
            if z_dot_product > 0:  # Standard case
                custom_flip_controls[short_name]["flip"]["rotateZ"] = True
            else:  # Needs custom handling
                custom_flip_controls[short_name]["attrs"].append("rotateZ")
                custom_flip_controls[short_name]["flip"]["rotateZ"] = False
                #print(f"Auto-detected custom flipping for {short_name}.rotateZ")
            
            # Also add the mirrored control with the same settings (using its short name)
            mirror_namespace, mirror_short_name = self._extract_namespace_and_name(mirrored_name)
            if mirror_short_name not in custom_flip_controls:
                custom_flip_controls[mirror_short_name] = {
                    "attrs": custom_flip_controls[short_name]["attrs"].copy(),
                    "flip": custom_flip_controls[short_name]["flip"].copy()
                }
        
        return custom_flip_controls

    def _load_mirror_preferences_for_pose(self, pose_data, current_namespace, cmds):
        """
        Loads mirror preferences for all objects in the pose data and their potential counterparts.
        
        Args:
            pose_data (dict): Dictionary of pose data
            current_namespace (str): Current namespace
            cmds: Maya commands module
            
        Returns:
            dict: Dictionary of mirror preferences
        """
        import json
        mirror_preferences = {}
        naming_conventions = self._get_naming_conventions("", "")
        
        # Load mirror preferences for all objects in pose data
        for obj_name in pose_data.keys():
            resolved_obj = self._resolve_object_name(obj_name, current_namespace)
            if resolved_obj and cmds.objExists(resolved_obj):
                namespace, short_name = self._extract_namespace_and_name(resolved_obj)
                
                if cmds.attributeQuery("mirrorPreference", node=resolved_obj, exists=True):
                    try:
                        pref_data_str = cmds.getAttr(f"{resolved_obj}.mirrorPreference")
                        mirror_preferences[short_name] = json.loads(pref_data_str)
                    except (json.JSONDecodeError, Exception) as e:
                        print(f"Error loading mirror preferences for {resolved_obj}: {e}")
        
        # Also load mirror preferences for potential counterparts
        potential_counterparts = set()
        for obj_name in pose_data.keys():
            resolved_obj = self._resolve_object_name(obj_name, current_namespace)
            if resolved_obj:
                namespace, short_name = self._extract_namespace_and_name(resolved_obj)
                # Find the potential counterpart name
                counterpart_name, _ = self._find_mirrored_name(short_name, naming_conventions, namespace=namespace)
                if counterpart_name != resolved_obj:
                    potential_counterparts.add(counterpart_name)
        
        # Load preferences for counterparts if they exist
        for counterpart in potential_counterparts:
            if cmds.objExists(counterpart):
                counterpart_namespace, counterpart_short = self._extract_namespace_and_name(counterpart)
                if counterpart_short not in mirror_preferences:
                    if cmds.attributeQuery("mirrorPreference", node=counterpart, exists=True):
                        try:
                            pref_data_str = cmds.getAttr(f"{counterpart}.mirrorPreference")
                            mirror_preferences[counterpart_short] = json.loads(pref_data_str)
                        except (json.JSONDecodeError, Exception) as e:
                            print(f"Error loading mirror preferences for counterpart {counterpart}: {e}")
        
        return mirror_preferences

    def _calculate_mirrored_attributes(self, attr_values, control_name, is_center_object, custom_flip_controls, mirror_preferences=None):
        """
        Calculates mirrored attribute values for an object.
        
        Args:
            attr_values (dict): Dictionary of attribute values from pose data
            control_name (str): Control name for custom flip lookup (short name without namespace)
            is_center_object (bool): Whether this is a center object
            custom_flip_controls (dict): Dictionary of custom flip controls
            mirror_preferences (dict, optional): Dictionary of mirror preferences
            
        Returns:
            dict: Dictionary of mirrored attribute values
        """
        mirrored_attrs = {}
        
        for attr, value in attr_values.items():
            mirrored_val = value
            
            # Check if we have mirror preferences for this control or its counterpart
            use_mirror_prefs = False
            pref_data = None
            
            # First check if the object itself has mirror preferences
            if mirror_preferences and control_name in mirror_preferences:
                pref_data = mirror_preferences[control_name]
            else:
                # If not, check if we have the counterpart's preferences loaded
                # We need to find the counterpart name first
                for obj_name, prefs in mirror_preferences.items() if mirror_preferences else []:
                    if "counterpart" in prefs and prefs["counterpart"] == control_name:
                        # We found a counterpart that points to this control
                        pref_data = prefs
                        #print(f"Using counterpart {obj_name}'s mirror preferences for {control_name}")
                        break
            
            if pref_data:
                # Handle translation attributes
                if attr.startswith('translate'):
                    axis = attr[-1].lower()  # Get the axis (X, Y, or Z)
                    if "translate" in pref_data and axis in pref_data["translate"]:
                        use_mirror_prefs = True
                        mirror_type = pref_data["translate"][axis]
                        
                        if mirror_type == "invert":
                            if isinstance(value, list):
                                mirrored_val = [-v for v in value]
                            else:
                                mirrored_val = -value
                        else:  # "none"
                            mirrored_val = value
                
                # Handle rotation attributes
                elif attr.startswith('rotate'):
                    axis = attr[-1].lower()  # Get the axis (X, Y, or Z)
                    if "rotate" in pref_data and axis in pref_data["rotate"]:
                        use_mirror_prefs = True
                        mirror_type = pref_data["rotate"][axis]
                        
                        if mirror_type == "invert":
                            if isinstance(value, list):
                                mirrored_val = [-v for v in value]
                            else:
                                mirrored_val = -value
                        else:  # "none"
                            mirrored_val = value
            
            # If we didn't use mirror preferences, use the standard logic
            if not use_mirror_prefs:
                # Check if this attribute should be flipped
                should_flip = self._should_flip_attribute(control_name, attr, custom_flip_controls)
                
                # Apply standard mirroring logic if should_flip is True
                if should_flip and (attr == 'translateX' or attr == 'rotateY' or attr == 'rotateZ'):
                    if isinstance(value, list):
                        mirrored_val = [-v for v in value]
                    else:
                        mirrored_val = -value
            
            # For center objects, only include attributes that need to be flipped
            if is_center_object:
                if (use_mirror_prefs or 
                    (self._should_flip_attribute(control_name, attr, custom_flip_controls) and 
                    attr in ['translateX', 'rotateY', 'rotateZ'])):
                    mirrored_attrs[attr] = mirrored_val
            else:
                # Include all attributes for regular mirroring
                mirrored_attrs[attr] = mirrored_val
        
        return mirrored_attrs

    def _should_flip_attribute(self, control_name, attr, custom_flip_controls):
        """
        Determines if an attribute should be flipped based on custom flip controls.
        
        Args:
            control_name (str): Name of the control (short name without namespace)
            attr (str): Attribute name
            custom_flip_controls (dict): Dictionary of custom flip controls
            
        Returns:
            bool: True if the attribute should be flipped, False otherwise
        """
        should_flip = True  # Default behavior
        
        # Check if this control is in the custom flip controls dictionary
        if control_name in custom_flip_controls:
            # Check if this attribute has custom flipping logic
            if attr in custom_flip_controls[control_name].get('attrs', []):
                # Get the custom flipping logic for this attribute
                should_flip = custom_flip_controls[control_name].get('flip', {}).get(attr, True)
        
        return should_flip
    #---------------------------------------------------------------------------------------
    # SCRIPT MANAGEMENT
    #---------------------------------------------------------------------------------------
    def execute_script_command(self):
        """Execute the script with namespace and match function token handling"""
        if self.mode != 'script' or not self.script_data:
            return

        script_type = self.script_data.get('type', 'python')

        if script_type == 'toggle':
            self._execute_toggle_command()
            return

        # Get the appropriate code based on type
        if script_type == 'python':
            code = self.script_data.get('python_code', self.script_data.get('code', ''))
        else:
            code = self.script_data.get('mel_code', self.script_data.get('code', ''))

        if not code.strip():
            cmds.warning("No script code to execute.")
            return

        try:
            # Get namespace info
            current_ns, ns_prefix = self._get_namespace_info()

            # Process the code (handle tokens and imports)
            modified_code = self._process_script_code(code, ns_prefix)

            # Execute the modified code
            self._execute_processed_code(modified_code, script_type)

        except Exception as e:
            cmds.warning(f"Error executing {script_type} code: {str(e)}")

    def _set_toggle_state(self, target_state):
        """Jump this toggle button directly to the given state index.

        Wired up by the right-click 'Set State' submenu — calls into the
        normal toggle execution path with ``target_state`` so appearances,
        per-state code, and persistence all behave the same as a click.
        """
        try:
            self._execute_toggle_command(target_state=int(target_state))
        except Exception as e:
            cmds.warning(f"Failed to set toggle state: {e}")

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
        # Empty-state guard: any code (python or mel, any state, or legacy
        # state_X_code) counts as "configured".
        any_code = any((toggle_data.get(k) or '').strip() for k in (
            'state_1_code', 'state_2_code', 'state_3_code',
            'state_1_python_code', 'state_2_python_code', 'state_3_python_code',
            'state_1_mel_code', 'state_2_mel_code', 'state_3_mel_code',
        ))
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

        context = TF._discover_execution_context(self)
        all_modified = []
        if context and appearances:
            for ap in appearances:
                vals = ap.get(state_key, {}) or {}
                targets_arg = ap.get('target_buttons') or None
                try:
                    targets = TF._resolve_target_buttons(targets_arg, context)
                except Exception as e:
                    cmds.warning(f"Failed to resolve targets for '{ap.get('name','')}': {e}")
                    return
                if not targets:
                    continue

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
                # Clear all render caches so font/color edits actually redraw.
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

                # Shape (More Options): commit target dimensions immediately;
                # the post-persist pass rewinds to prev and animates forward.
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
                    cmds.warning(f"Failed to persist appearance changes: {e}")
                    return

        # Resolve which language + code to run for this state.
        next_lang = (toggle_data.get(f'state_{next_state + 1}_lang') or 'python').lower()
        if next_lang == 'mel':
            code = toggle_data.get(f'state_{next_state + 1}_mel_code', '') or ''
        else:
            code = (
                toggle_data.get(f'state_{next_state + 1}_python_code', '')
                or toggle_data.get(code_key, '')
                or ''
            )
        if code.strip():
            try:
                current_ns, ns_prefix = self._get_namespace_info()
                modified_code = self._process_script_code(code, ns_prefix)
                self._execute_processed_code(modified_code, next_lang)
            except Exception as e:
                cmds.warning(f"Error executing toggle state {next_lang} code: {e}")
                return

        toggle_data['current_state'] = next_state
        new_script_data = dict(self.script_data)
        new_script_data['toggle_data'] = toggle_data
        self.script_data = new_script_data
        try:
            self.changed.emit(self)
        except Exception:
            pass

    def _get_namespace_info(self):
        """Get current namespace and prefix from picker window"""
        main_window = self.window()
        current_ns = ""
        ns_prefix = ""
        
        if isinstance(main_window, UI.AnimPickerWindow):
            current_ns = main_window.namespace_dropdown.currentText()
            ns_prefix = f"{current_ns}:" if current_ns and current_ns != 'None' else ""
        
        return current_ns, ns_prefix

    def _process_script_code(self, code, ns_prefix):
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
        
        # Replace '@ns' tokens
        modified_code = re.sub(r'@ns\.?([a-zA-Z0-9_])', fr'{ns_prefix}\1', modified_code, flags=re.IGNORECASE)  # Replace @ns. followed by identifier
        modified_code = re.sub(r'@ns\.?(?!\w)', f'"{ns_prefix}"', modified_code, flags=re.IGNORECASE)
        
        #--------------------------------------------------------------------------------------------------------
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
        #--------------------------------------------------------------------------------------------------------
        
        return modified_code

    def _execute_processed_code(self, modified_code, script_type):
        """Execute the processed code based on script type"""
        if script_type == 'python':
            #print(modified_code)
            exec(modified_code)
        else:
            import maya.mel as mel
            mel.eval(modified_code)
    #---------------------------------------------------------------------------------------
    # POSE STAGING
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
        
        # Initialize object cache for performance
        self._pose_object_cache = {}
        
        # Force pixmap regeneration to show stage counter
        self.last_text = None
        self.update()

    def handle_pose_drag(self, event):
        """Update the pose drag operation to apply staged poses"""
        if not self.pose_dragging or not self.pose_drag_start_pos or not self.staged_poses:
            return
            
        # Throttle updates for better performance (60fps max)
        current_time = QtCore.QTime.currentTime().msecsSinceStartOfDay()
        if hasattr(self, 'last_pose_drag_update'):
            if current_time - self.last_pose_drag_update < 16:  # ~60fps limit
                return
        self.last_pose_drag_update = current_time
            
        # Calculate the horizontal drag distance
        delta_x = event.globalPos().x() - self.pose_drag_start_pos.x()
        
        # Convert drag distance to stage (80 pixels = 10 stages for better responsiveness)
        # Negative values (dragging left) should give stage 0, positive (right) should give up to stage 10
        drag_sensitivity = 80.0  # pixels for all 10 stages
        stage_float = max(0.0, min(10.0, delta_x / drag_sensitivity * 10))
        new_stage = int(stage_float)
        
        # Only apply if stage changed
        if new_stage != self.current_pose_stage:
            self.current_pose_stage = new_stage
            
            # Apply the staged pose - with error handling
            try:
                self._apply_staged_pose_optimized(new_stage)
            except Exception as e:
                print(f"Error during pose drag at stage {new_stage}: {e}")
                # Stop pose dragging on error to prevent further crashes
                self.pose_dragging = False
                return
            
            # Batch UI updates - update only on key stages for better performance
            # Update on every 3rd stage, first stage, and last stage
            if new_stage % 3 == 0 or new_stage == 0 or new_stage == len(self.staged_poses) - 1:
                # Force pixmap regeneration to update the stage text
                self.last_text = None  # This will force pixmap regeneration
                # Use a timer for deferred UI update to avoid blocking pose application
                if not hasattr(self, '_ui_update_timer'):
                    self._ui_update_timer = QtCore.QTimer()
                    self._ui_update_timer.setSingleShot(True)
                    self._ui_update_timer.timeout.connect(self.update)
                self._ui_update_timer.start(5)  # 5ms delayed update

    def complete_pose_drag(self, event):
        """Complete the pose drag operation"""
        try:
            # Apply the final pose using the non-optimized method for proper completion
            # This ensures proper selection, undo state, etc.
            if hasattr(self, 'current_pose_stage') and self.staged_poses:
                self._apply_staged_pose(self.current_pose_stage)
                print(f"Pose finalized at stage {self.current_pose_stage}/10")
            
            self.pose_dragging = False
            self.pose_drag_start_pos = None
            
            # Force pixmap regeneration to restore normal label
            self.last_text = None
            self.update()
            
        except Exception as e:
            print(f"Error completing pose drag: {e}")
        finally:
            # Always clear the staged poses and cache
            self.staged_poses = []
            self.current_pose_stage = 0
            self.pose_dragging = False
            self._pose_object_cache = {}
            
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
            
            # Force pixmap regeneration to restore normal label
            self.last_text = None
            self.update()
            
        except Exception as e:
            print(f"Error canceling pose drag: {e}")
        finally:
            # Always clear the staged poses and cache
            self.staged_poses = []
            self.current_pose_stage = 0
            self.pose_dragging = False
            self._pose_object_cache = {}

    def _create_staged_poses(self):
        """Create 10 intermediate poses from current state to target pose"""
        if not self._validate_pose_data():
            return []
        
        # Import Maya cmds
        try:
            import maya.cmds as cmds
        except ImportError:
            print("Maya not available for pose staging")
            return []
        
        target_pose_data = self.pose_data.get("default", {})
        current_namespace = self._get_current_namespace()
        
        # First, capture the current state as stage 0
        current_state = {}
        
        try:
            for obj_name, target_attr_values in target_pose_data.items():
                resolved_obj = self._resolve_object_name(obj_name, current_namespace)
                
                if resolved_obj and cmds.objExists(resolved_obj):
                    # Store current object state
                    current_state[obj_name] = {}
                    
                    for attr_name in target_attr_values.keys():
                        full_attr = f"{resolved_obj}.{attr_name}"
                        if cmds.objExists(full_attr):
                            try:
                                current_value = cmds.getAttr(full_attr)
                                current_state[obj_name][attr_name] = current_value
                            except Exception as e:
                                print(f"Could not get current value for {full_attr}: {e}")
                                
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
            
            for obj_name in current_state.keys():
                if obj_name in target_pose_data:
                    current_data = current_state[obj_name]
                    target_data = target_pose_data[obj_name]
                    
                    # Interpolate the data
                    interpolated_data = self._interpolate_pose_data(current_data, target_data, factor)
                    stage_pose[obj_name] = interpolated_data
            
            staged_poses.append(stage_pose)
        
        print(f"Created {len(staged_poses)} staged poses")
        return staged_poses
    
    def _interpolate_pose_data(self, current_data, target_data, factor):
        """Interpolate between current and target pose data"""
        interpolated = {}
        
        # Interpolate each attribute
        for attr_name in target_data.keys():
            if attr_name in current_data:
                current_value = current_data[attr_name]
                target_value = target_data[attr_name]
                
                # Handle numeric interpolation
                if isinstance(current_value, (int, float)) and isinstance(target_value, (int, float)):
                    interpolated[attr_name] = current_value + (target_value - current_value) * factor
                elif isinstance(current_value, (list, tuple)) and isinstance(target_value, (list, tuple)):
                    # Handle list/tuple interpolation (for transforms with multiple values)
                    if len(current_value) == len(target_value):
                        interpolated[attr_name] = [
                            current_value[i] + (target_value[i] - current_value[i]) * factor
                            for i in range(len(current_value))
                        ]
                    else:
                        interpolated[attr_name] = target_value
                else:
                    # For non-numeric values, just use target
                    interpolated[attr_name] = target_value
            else:
                interpolated[attr_name] = target_data[attr_name]
        
        return interpolated
    
    def _apply_staged_pose(self, stage):
        """Apply a pre-calculated staged pose using existing pose logic"""
        if stage < 0 or stage >= len(self.staged_poses):
            return
        
        # Get the staged pose data
        staged_pose_data = self.staged_poses[stage]
        
        # Temporarily replace the button's pose data with the staged data
        original_pose_data = self.pose_data.get("default", {})
        self.pose_data["default"] = staged_pose_data
        
        # Apply the pose using existing logic
        try:
            self.apply_pose()
        except Exception as e:
            print(f"Error applying staged pose {stage}: {e}")
        finally:
            # Restore original pose data
            self.pose_data["default"] = original_pose_data

    def _apply_staged_pose_optimized(self, stage):
        """Optimized version for real-time pose application during dragging"""
        if stage < 0 or stage >= len(self.staged_poses):
            return
        
        # Get the staged pose data
        staged_pose_data = self.staged_poses[stage]
        current_namespace = self._get_current_namespace()
        
        # Import Maya cmds (should be cached after first import)
        import maya.cmds as cmds
        
        # Direct attribute setting without the overhead of full pose logic
        try:
            # Disable undo during real-time dragging for performance
            cmds.undoInfo(stateWithoutFlush=False)
            
            for obj_name, attr_values in staged_pose_data.items():
                # Use cached object resolution for performance
                cache_key = f"{obj_name}_{current_namespace}"
                if cache_key not in self._pose_object_cache:
                    resolved_obj = self._resolve_object_name(obj_name, current_namespace)
                    if resolved_obj and cmds.objExists(resolved_obj):
                        self._pose_object_cache[cache_key] = resolved_obj
                    else:
                        self._pose_object_cache[cache_key] = None
                
                resolved_obj = self._pose_object_cache[cache_key]
                if resolved_obj:
                    for attr_name, value in attr_values.items():
                        full_attr = f"{resolved_obj}.{attr_name}"
                        try:
                            # Fast attribute setting - skip expensive checks during dragging
                            cmds.setAttr(full_attr, value)
                        except Exception:
                            # Skip attributes that can't be set
                            pass
                                
        except Exception as e:
            print(f"Error in optimized staged pose {stage}: {e}")
        finally:
            # Re-enable undo
            cmds.undoInfo(stateWithoutFlush=True)

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
        self._invalidate_mask_cache()
        self.update()
        self.changed.emit(self)
    
    def set_radius(self, top_left, top_right, bottom_right, bottom_left):
        self.radius = [top_left, top_right, bottom_right, bottom_left]
        self._invalidate_mask_cache()
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
        window = self.window()
        if not self.rename_mode or not self.rename_edit:
            return
        
        # Prevent re-entry (in case both returnPressed and editingFinished fire)
        if hasattr(self, '_committing_rename') and self._committing_rename:
            return
        
        self._committing_rename = True
        
        try:
            # Get the new label
            new_label = self.rename_edit.text().strip()
            
            window.rename_selected_buttons(new_label)
                
            # Exit rename mode
            self.exit_rename_mode()
        finally:
            self._committing_rename = False
    
    def delete_button(self):
        """Delete a single button with proper database cleanup"""
        # Mark button as being deleted to prevent update conflicts
        self._being_deleted = True
        
        # Get canvas and main window references
        canvas = self.parent()
        if canvas:
            main_window = canvas.window()
            current_tab = None
            
            if isinstance(main_window, UI.AnimPickerWindow) and main_window.tab_system.current_tab:
                current_tab = main_window.tab_system.current_tab
                
                # Handle database cleanup immediately
                from . import data_management as DM
                
                # Get current tab data
                tab_data = DM.PickerDataManager.get_tab_data(current_tab)
                
                # Remove this button from the database
                original_count = len(tab_data['buttons'])
                tab_data['buttons'] = [b for b in tab_data['buttons'] if b['id'] != self.unique_id]
                new_count = len(tab_data['buttons'])
                
                if new_count < original_count:
                    # Update the database
                    #DM.PickerDataManager.update_tab_data(current_tab, tab_data)
                    DM.PickerDataManager.batch_update_buttons(current_tab, DM.PickerDataManager.get_tab_data(current_tab)['buttons'])
                    # batch_update_buttons debounces; flush so the
                    # deletion lands in the scene attr immediately.
                    DM.PickerDataManager.flush_pending_saves()
                    
                    # Return button ID to available pool
                    if hasattr(main_window, 'available_ids'):
                        if current_tab not in main_window.available_ids:
                            main_window.available_ids[current_tab] = set()
                        main_window.available_ids[current_tab].add(self.unique_id)
            
            # Remove from canvas buttons list
            if self in canvas.buttons:
                canvas.buttons.remove(self)
        
        # Emit the deleted signal and schedule widget deletion
        self.deleted.emit(self)
        self.deleteLater()
    #---------------------------------------------------------------------------------------
    def rename_selected_buttons(self, new_label):
        canvas = self.parent()
        main_window = canvas.window()
        current_tab = main_window.tab_system.current_tab
        if canvas:
            selected_buttons = canvas.get_selected_buttons()
            for button in selected_buttons:
                button.rename_button(new_label)
            
            
            # Update the main window
            if isinstance(main_window, UI.AnimPickerWindow):
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
            if isinstance(main_window, UI.AnimPickerWindow):
                main_window.update_buttons_for_current_tab()
    
    def change_opacity_for_selected_buttons(self, value):
        canvas = self.parent()
        if canvas:
            selected_buttons = canvas.get_selected_buttons()
            opacity = value #/ 100.0
            for button in selected_buttons:
                button.change_opacity(opacity)
            
            # Update the main window

    def delete_selected_buttons(self):
        canvas = self.parent()
        
        if canvas:
            selected_buttons = canvas.get_selected_buttons()
            
            if not selected_buttons:
                return
                
            # Get the main window reference before deletion
            main_window = canvas.window()
            current_tab = None
            
            # Get current tab name for data synchronization
            if isinstance(main_window, UI.AnimPickerWindow) and main_window.tab_system.current_tab:
                current_tab = main_window.tab_system.current_tab
            
            # Disable updates during batch operation for better performance
            canvas.setUpdatesEnabled(False)
            
            # Store button IDs and references for proper cleanup
            buttons_to_delete = selected_buttons[:]  # Create a copy
            deleted_button_ids = [button.unique_id for button in buttons_to_delete]
            
            # IMPORTANT: Clear any pending batch updates first
            if hasattr(main_window, 'pending_button_updates'):
                main_window.pending_button_updates.clear()
            if hasattr(main_window, 'batch_update_timer'):
                main_window.batch_update_timer.stop()
            if hasattr(canvas, 'transform_guides'):
                canvas.transform_guides.setVisible(False)
                canvas.transform_guides.visual_layer.setVisible(False)
                canvas.transform_guides.controls_widget.setVisible(False)
            
            # Remove buttons from canvas first (prevents further updates)
            for button in buttons_to_delete:
                if button in canvas.buttons:
                    canvas.buttons.remove(button)
            
            # Now handle database cleanup synchronously
            if current_tab:
                from . import data_management as DM
                
                # Get current tab data
                tab_data = DM.PickerDataManager.get_tab_data(current_tab)
                
                # Remove all selected buttons from the database in one operation
                original_count = len(tab_data['buttons'])
                tab_data['buttons'] = [b for b in tab_data['buttons'] if b['id'] not in deleted_button_ids]
                new_count = len(tab_data['buttons'])
                
                # Verify deletion worked
                if new_count < original_count:
                    #print(f"Successfully deleted {original_count - new_count} buttons from database")
                    
                    # Update the database with the modified data
                    #DM.PickerDataManager.update_tab_data(current_tab, tab_data)
                    DM.PickerDataManager.batch_update_buttons(current_tab, DM.PickerDataManager.get_tab_data(current_tab)['buttons'])
                    # batch_update_buttons debounces; flush so the
                    # multi-delete lands in the scene attr immediately.
                    DM.PickerDataManager.flush_pending_saves()
                else:
                    print("Warning: No buttons were removed from the database")
            
            # Now safely delete the button widgets
            for button in buttons_to_delete:
                # Disconnect all signals to prevent further updates
                try:
                    button.deleted.disconnect()
                    button.selected.disconnect()
                    button.changed.disconnect()
                except:
                    pass
                
                # Set parent to None and schedule for deletion
                button.setParent(None)
                button.deleteLater()
            
            # Return button IDs to available pool
            if hasattr(main_window, 'available_ids') and current_tab:
                if current_tab not in main_window.available_ids:
                    main_window.available_ids[current_tab] = set()
                main_window.available_ids[current_tab].update(deleted_button_ids)
            
            # Re-enable updates
            canvas.setUpdatesEnabled(True)
            
            # Update canvas display
            canvas.update_button_positions()
            canvas.update_hud_counts()
            canvas.clear_selection()  # Clear selection since buttons are deleted
            canvas.update()
            
            # Force update of the current tab's button data
            if isinstance(main_window, UI.AnimPickerWindow):
                main_window.update_buttons_for_current_tab(force_update=True)
                
            #print(f"Batch deletion complete: {len(deleted_button_ids)} buttons removed")
        
    def add_selected_objects(self):
        """Store both UUID and long name for selected objects"""
        selected = cmds.ls(selection=True, long=True)
        if selected:
            # Create a list of {uuid, long_name} pairs for selected objects
            new_objects = []
            for obj in selected:
                try:
                    uuid = cmds.ls(obj, uuid=True)[0]
                    new_objects.append({
                        'uuid': uuid,
                        'long_name': obj
                    })
                except:
                    continue
                    
            # Add new objects to existing list, avoiding duplicates by UUID
            existing_uuids = {obj['uuid'] for obj in self.assigned_objects}
            self.assigned_objects.extend([obj for obj in new_objects if obj['uuid'] not in existing_uuids])
            #self.update_tooltip()
            self._tooltip_needs_update = True 
            self.changed.emit(self)
    
    def convert_assigned_objects(self, objects):
        """Convert old format (UUID only) to new format (UUID + long name)"""
        converted_objects = []
        for obj in objects:
            # Check if object is already in new format
            if isinstance(obj, dict) and 'uuid' in obj and 'long_name' in obj:
                converted_objects.append(obj)
            else:
                # Old format - only UUID
                try:
                    nodes = cmds.ls(obj, long=True)
                    if nodes:
                        converted_objects.append({
                            'uuid': obj,
                            'long_name': nodes[0]
                        })
                    else:
                        # If can't resolve UUID, still store it with empty long name
                        converted_objects.append({
                            'uuid': obj,
                            'long_name': ''
                        })
                except:
                    continue
        return converted_objects

    def remove_selected_objects(self):
        """Remove currently selected Maya objects from this button's assigned objects"""
        selected = cmds.ls(selection=True, long=True)
        if not selected:
            print("No objects selected to remove")
            return

        # Build set of UUIDs to remove
        uuids_to_remove = set()
        for obj in selected:
            try:
                uuid = cmds.ls(obj, uuid=True)[0]
                uuids_to_remove.add(uuid)
            except:
                continue

        if uuids_to_remove:
            original_count = len(self.assigned_objects)
            self.assigned_objects = [
                obj for obj in self.assigned_objects
                if obj.get('uuid') not in uuids_to_remove
            ]
            removed_count = original_count - len(self.assigned_objects)
            if removed_count > 0:
                self._tooltip_needs_update = True
                self.changed.emit(self)
                print(f"Removed {removed_count} object(s) from picker button")
            else:
                print("No matching objects found on this button")

    def remove_selected_objects_for_selected_buttons(self):
        """Remove currently selected objects from all selected picker buttons"""
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
        if event.button() == QtCore.Qt.LeftButton:
            canvas = self.parent()
            canvas._hide_button_tooltip()
            if canvas:
                alt_held = event.modifiers() & QtCore.Qt.AltModifier
                ctrl_held = event.modifiers() & QtCore.Qt.ControlModifier
                shift_held = event.modifiers() & QtCore.Qt.ShiftModifier
                
                # Allow dragging only in edit mode
                if self.edit_mode:
                    if alt_held:
                        self.start_duplication_drag(event)
                    else:
                        self._handle_edit_mode_selection(event, canvas, shift_held)
                else:
                    # Select mode - handle different button modes
                    if self.mode == 'select':
                        self._handle_select_mode_click(event, canvas, shift_held, ctrl_held, alt_held)
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
                        # Select the controlled Maya object(s)
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
                        if self.is_animation:
                            if ctrl_held and shift_held:
                                self.apply_animation(apply_mode='add')
                            elif ctrl_held:
                                self.apply_animation(apply_mode='merge')
                            else:
                                self.apply_animation(apply_mode='replace')
                        elif alt_held:
                            self.apply_mirrored_pose()
                        elif shift_held:
                            # Start pose dragging for gradual application
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
            if not self.is_selected:
                canvas = self.parent()
                canvas.clear_selection() if not shift_held else None
                self.is_selected = True
                self.selected.emit(self, True)
                canvas.last_selected_button = self
                canvas.button_selection_changed.emit()
            self.show_context_menu(event.pos())
            event.accept()
        else:
            super().mousePressEvent(event)
        
        double_click = event.type() == QtCore.QEvent.MouseButtonDblClick
        if not double_click:
            main_window = self.window()
            if main_window.edit_mode == False:
                # Don't steal focus if controller input overlay is active
                if not (self.mode == 'controller' and getattr(self, '_controller_input_active', False)):
                    # Mark that Maya should be re-activated once the cursor
                    # actually leaves the picker. Doing it immediately here
                    # would make Maya's main window the macOS *key window*,
                    # which causes trackpad pinch-zoom (NSEvent gestures) to
                    # be routed to Maya's viewport instead of the picker —
                    # breaking zoom-on-trackpad in non-edit mode. The
                    # activation happens in PickerCanvas.leaveEvent so the
                    # picker stays key while the cursor remains over it.
                    canvas = self.parent()
                    if canvas is not None:
                        canvas._pending_maya_activation = True

    def mouseDoubleClickEvent(self, event):
        """Handle double-click events for renaming buttons in edit mode"""
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
        """Optimized mouse move with minimal updates during drag"""
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

        if hasattr(self, 'duplicating') and self.duplicating and event.buttons() & QtCore.Qt.LeftButton:
            self.handle_duplication_drag(event)
            event.accept()
            
        elif self.pose_dragging and event.buttons() & QtCore.Qt.LeftButton:
            self.handle_pose_drag(event)
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

            # CRITICAL: Disable all updates during batch position change
            canvas.setUpdatesEnabled(False)

            # Update positions using silent setter (no per-button canvas reflow)
            selected_buttons = canvas.get_selected_buttons()
            for button in selected_buttons:
                button.set_scene_position_silent(button.button_start_pos + scene_delta)

            # Single update for all button positions
            canvas.update_button_positions()

            # Re-enable updates — triggers single consolidated repaint
            canvas.setUpdatesEnabled(True)

            # Throttled transform guide update via canvas-level timer
            if hasattr(canvas, 'transform_guides') and canvas.transform_guides.isVisible():
                canvas._request_guides_update()
            
            event.accept()
        else:
            super().mouseMoveEvent(event)

    def wheelEvent(self, event):
        """Forward wheel events to the parent canvas.

        Without this, after a button click steals focus to Maya (see the
        ``UT.maya_main_window().activateWindow()`` call in mousePressEvent),
        subsequent wheel events delivered over a button widget can fail to
        propagate to the canvas's wheelEvent handler — breaking zoom/pan.
        Explicitly forwarding bypasses any focus / event-routing oddities.
        """
        canvas = self.parent()
        if canvas is not None and hasattr(canvas, 'wheelEvent'):
            # Re-target the event to the canvas's coordinate space.
            try:
                # Qt6: QWheelEvent has position() returning a QPointF in widget-local coords
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
        parent canvas. Unlike wheel events, native gesture events are NOT
        propagated up the parent chain by Qt, so when the cursor is over a
        button after a button click steals focus to the host app, the
        canvas never sees the gesture and zoom appears broken on trackpads.
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
                        self.window().activateWindow()
                except Exception:
                    pass
                # Translate the gesture position from button-local to
                # canvas-local coords. The canvas handler reads .position()
                # directly, so wrap the original event in a tiny shim that
                # returns the translated point but otherwise delegates.
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
                # Deselect and reselect to force Maya viewport refresh
                self._select_controller_object()
                event.accept()
                return

            # Handle duplication completion
            if hasattr(self, 'duplicating') and self.duplicating:
                self.complete_duplication_drag(event)
                event.accept()
                return

            # Handle pose drag completion
            if self.pose_dragging:
                self.complete_pose_drag(event)
                event.accept()
                return
            
            # Handle normal dragging completion
            if self.dragging:
                self.dragging = False
                self.update_cursor()
                
                if canvas:
                    # Check if button actually moved from its starting position
                    distance_moved = ((self.scene_position.x() - self.button_start_pos.x()) ** 2 + 
                                    (self.scene_position.y() - self.button_start_pos.y()) ** 2) ** 0.5
                    
                    # Only save if moved more than 1 pixel
                    if distance_moved > 1.0:
                        # Save the position change
                        selected_buttons = canvas.get_selected_buttons()
                        main_window = canvas.window()
                        
                        # Check for the correct main window class (you had BlenderAnimPickerWindow, should be AnimPickerWindow)
                        if isinstance(main_window, UI.AnimPickerWindow):
                            # Use optimized batch position update
                            self._batch_update_button_positions(selected_buttons, main_window)
                        else:
                            # Fallback to individual updates if needed
                            for button in selected_buttons:
                                canvas.update_button_data(button)
                
                event.accept()
        else:
            super().mouseReleaseEvent(event)
    
    def event(self, event):
        """Override event to handle key events."""
        if event.type() == QtCore.QEvent.KeyPress:
            if event.key() == QtCore.Qt.Key_Escape:
                if self.pose_dragging:
                    self.cancel_pose_drag()
                    return True
                else:
                    self.exit_rename_mode()
                    return True
        return super().event(event)
    
    def enterEvent(self, event):
        """Called when mouse enters the button area."""
        # Reclaim window activation so macOS resumes delivering trackpad
        # NativeGesture / phased scroll events to the picker. Without
        # this, gestures over a button after a click that handed focus
        # to Maya silently route to Maya instead.
        win = self.window()
        if win is not None and not win.isActiveWindow():
            win.activateWindow()
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
            canvas = self.parent()
            if canvas and hasattr(canvas, '_current_hover_button') and canvas._current_hover_button is self:
                canvas._current_hover_button = None
                canvas.update()
            self.is_hovered = False
            super().leaveEvent(event)
            return
        self.is_hovered = False
        self.update()
        super().leaveEvent(event)
    
    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._update_rename_edit_geometry()

