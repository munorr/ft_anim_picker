from functools import partial
import maya.cmds as cmds
import maya.mel as mel
import os
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

import math
import re

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
                    'relative_position': button.scene_position - center,
                    'assigned_objects': button.assigned_objects.copy(),
                    'mode': button.mode,
                    'script_data': button.script_data.copy()
                }
                
                # Add pose-specific data if this is a pose button
                if button.mode == 'pose':
                    button_data['thumbnail_path'] = button.thumbnail_path
                    button_data['pose_data'] = button.pose_data.copy()  # Copy the pose data
                
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

    def __init__(self, label, parent=None, unique_id=None, color='#444444', opacity=1, width=80, height=30, selectable=True):
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
    
        self.setStyleSheet(f"QToolTip {{background-color: {UT.rgba_value(color,.8,alpha=1)}; color: #eeeeee ; border: 1px solid rgba(255,255,255,.2); padding: 4px;}}")
        # Set tool tip to have translucent background and remove shadow
        
       
        self.edit_mode = False
        self.update_cursor()
        self.assigned_objects = []  

        self.mode = 'select'  # 'select', 'script', or 'pose'
        self.script_data = {}  # Store script data
        self.pose_data = {}  # Store pose data
        
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
    #---------------------------------------------------------------------------------------
    def update(self):
        """REPLACE your update method with this throttled version"""
        if not self.needs_update:
            self.needs_update = True
            self.update_timer.start(16)  # ~60fps
    
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
        
        # Set up font for pose mode
        pose_painter.setPen(QtGui.QColor('white'))
        pose_font = pose_painter.font()
        font_size = (self.width * 0.15) * zoom_factor  # Smaller font based on width
        pose_font.setPixelSize(int(font_size))
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
        else:
            # Draw placeholder text
            pose_painter.setPen(QtGui.QColor(255, 255, 255, 120))
            pose_painter.drawText(thumbnail_rect, QtCore.Qt.AlignCenter, "Thumbnail")
            pose_painter.setPen(QtGui.QColor('white'))  # Reset pen color
        
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
        
        # Set up font
        text_painter.setPen(QtGui.QColor('white'))
        font = text_painter.font()
        font_size = (self.height * 0.5) * zoom_factor
        font.setPixelSize(int(font_size))
        text_painter.setFont(font)
        
        # Calculate text rect with padding
        text_rect = self.rect()
        bottom_padding = (self.height * 0.1) * zoom_factor
        text_rect.adjust(0, 0, 0, -int(bottom_padding))
        
        # Draw text centered
        text_painter.drawText(text_rect, QtCore.Qt.AlignCenter, self.label)
        text_painter.end()
        
        return text_pixmap
    
    def _should_update_pixmaps(self, zoom_factor, current_size, current_radius, current_text):
        """More efficient pixmap update checking"""
        # Only update if significant changes
        zoom_threshold = 0.15  # Increase threshold for less updates
        size_threshold = 5     # Pixels threshold
        radius_threshold = 1   # Radius threshold
        #Update if text changes
        
        if self.mode == 'pose':
            pixmap_missing = self.pose_pixmap is None
        else:
            pixmap_missing = self.text_pixmap is None
            
        zoom_changed = abs(self.last_zoom_factor - zoom_factor) > zoom_threshold
        size_changed = (self.last_size is None or 
                       abs(self.last_size.width() - current_size.width()) > size_threshold or
                       abs(self.last_size.height() - current_size.height()) > size_threshold)
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
        path = self._create_rounded_rect_path(rect, self.radius, zoom_factor)
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
    def mousePressEvent(self, event):
        if event.button() == QtCore.Qt.LeftButton:
            canvas = self.parent()
            if canvas:
                alt_held = event.modifiers() & QtCore.Qt.AltModifier
                ctrl_held = event.modifiers() & QtCore.Qt.ControlModifier
                # Allow dragging only in edit mode
                if self.edit_mode:
                    if alt_held:
                        self.start_duplication_drag(event)
                    else:
                        self.dragging = True
                        self.drag_start_pos = event.globalPos()
                        self.button_start_pos = self.scene_position
                        self.setCursor(QtCore.Qt.ClosedHandCursor)
                        
                        selected_buttons = canvas.get_selected_buttons()
                        
                        if not self.is_selected and not (event.modifiers() & QtCore.Qt.ShiftModifier):
                            canvas.clear_selection()
                            canvas.buttons_in_current_drag.add(self)
                            self.is_selected = True
                            self.selected.emit(self, True)
                            canvas.last_selected_button = self  # Set as last selected
                            self.update()
                        elif event.modifiers() & QtCore.Qt.ShiftModifier:
                            canvas.buttons_in_current_drag.add(self)
                            self.is_selected = not self.is_selected
                            if self.is_selected:
                                canvas.last_selected_button = self  # Set as last selected if being selected
                            self.selected.emit(self, self.is_selected)
                            self.update()
                        
                        for button in selected_buttons:
                            button.button_start_pos = button.scene_position
                else:
                    if self.mode == 'select':
                        # Only allow selection if the button is selectable
                        if hasattr(self, 'selectable') and self.selectable:
                            # Existing selection behavior
                            canvas.buttons_in_current_drag.clear()
                            canvas.buttons_in_current_drag.add(self)
                            
                            if not event.modifiers() & QtCore.Qt.ShiftModifier:
                                canvas.clear_selection()
                            self.is_selected = not self.is_selected if event.modifiers() & QtCore.Qt.ShiftModifier else True
                            self.update()
                            
                            canvas.apply_final_selection(event.modifiers() & QtCore.Qt.ShiftModifier)
                    elif self.mode == 'script':
                        # script mode behavior
                        self.execute_script_command()
                    elif self.mode == 'pose':
                        # pose mode behavior
                        if ctrl_held:
                            self.apply_mirrored_pose()
                        else:
                            self.apply_pose()
                        
                
                event.accept()
        elif event.button() == QtCore.Qt.RightButton:
            if not self.is_selected:
                self.parent().clear_selection()
                self.toggle_selection()
            self.show_context_menu(event.pos())
            event.accept()
        else:
            super().mousePressEvent(event)
        UT.maya_main_window().activateWindow()

    def mouseMoveEvent(self, event):
        if hasattr(self, 'duplicating') and self.duplicating and event.buttons() & QtCore.Qt.LeftButton:
            # Handle duplication drag
            self.handle_duplication_drag(event)
            event.accept()
        elif self.dragging and event.buttons() & QtCore.Qt.LeftButton:
            canvas = self.parent()
            if not canvas:
                return

            delta = event.globalPos() - self.drag_start_pos
            scene_delta = QtCore.QPointF(delta.x(), delta.y()) / canvas.zoom_factor
            
            selected_buttons = canvas.get_selected_buttons()
            for button in selected_buttons:
                button.scene_position = button.button_start_pos + scene_delta
            
            if hasattr(self.parent(), '_update_transform_guides_position'):
                QtCore.QTimer.singleShot(1, self.parent()._update_transform_guides_position)
            
            canvas.update_button_positions()
            event.accept()
        else:
            super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if event.button() == QtCore.Qt.LeftButton:
            canvas = self.parent()
            
            # Handle duplication completion
            if hasattr(self, 'duplicating') and self.duplicating:
                self.complete_duplication_drag(event)
                event.accept()
                return

        if event.button() == QtCore.Qt.LeftButton and self.dragging:
            self.dragging = False
            self.update_cursor()
            canvas = self.parent()
            if canvas:
                for button in canvas.get_selected_buttons():
                    canvas.update_button_data(button)
            event.accept()
        else:
            super().mouseReleaseEvent(event)
        UT.maya_main_window().activateWindow()
    
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

    def update_tooltip(self):
        """Update the tooltip with button information"""
        
        # Check if the button has a custom tooltip from script
        if self.mode == 'script' and self.script_data and 'custom_tooltip' in self.script_data:
            # Use the custom tooltip from script
            custom_tooltip = self.script_data['custom_tooltip']
            #tooltip = f"<b><span style='font-size: 12px;'>{custom_tooltip}</span></b>"
            tooltip = f"{custom_tooltip}"
            tooltip += f"<i><div style='text-align: left; font-size: 9px; color: rgba(255, 255, 255, 0.7); '>ID: [{self.unique_id}]</div></i>"
            tooltip += f"<div style='text-align: center; font-size: 9px; color: rgba(255, 255, 255, 0.5); '>({self.mode.capitalize()} mode)</div>"
            self.setToolTip(tooltip)
            return
        elif self.mode == 'script':
            tooltip = f"<b><span style='font-size: 12px;'>Script Button</span></b>"
            tooltip += f"<i><div style='text-align: left; font-size: 9px; color: rgba(255, 255, 255, 0.7); '>ID: [{self.unique_id}]</div></i>"
            tooltip += f"<div style='text-align: center; font-size: 9px; color: rgba(255, 255, 255, 0.5); '>({self.mode.capitalize()} mode)</div>"
            self.setToolTip(tooltip)
            return
        
        # Default tooltip behavior
        tooltip = f"<b><span style='font-size: 12px;'>Assigned Objects <span style='color: rgba(255, 255, 255, 0.6);'>({len(self.assigned_objects)})</span>:</b></span>"

        # Frame
        tooltip += f"<div style='background-color: rgba(0, 0, 0, 0.1);'>"
        if self.assigned_objects:
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
                if len(object_names) > 10:
                    displayed_objects = object_names[:10]
                    remaining_count = len(object_names) - 10
                    objects_str = "- " + "<br>- ".join(displayed_objects)
                    objects_str += f"<br><span style='color: rgba(255, 255, 255, 0.5); font-size: 9px;'><i>...and {remaining_count} more object{'s' if remaining_count > 1 else ''}</i></span>"
                else:
                    objects_str = "- " + "<br>- ".join(object_names)
                tooltip += objects_str
            else:
                tooltip += "(No valid objects found)"
        else:
            tooltip += f"<i><span style='font-size: 9px; color: rgba(255, 255, 255, 0.6);'>No objects assigned</span></i>"

        tooltip += "</div>"
        tooltip += f"<i><div style='text-align: left; font-size: 10px; color: rgba(255, 255, 255, 0.8); '>ID: [{self.unique_id}]</div></i>"

        if self.thumbnail_path:
            tooltip += f"<br><span style='font-size: 10px; color: rgba(255, 255, 255, 0.6);'>[{os.path.basename(self.thumbnail_path).split('.')[0]}]</span>"
        else:
            tooltip += f"<br><i><span style='font-size: 9px; color: rgba(255, 255, 255, 0.6);'>No thumbnail</span></i>"
        # Button ID and mode
        tooltip += f"<b><div style='text-align: center; font-size: 10px; color: rgba(255, 255, 255, 0.7); '>({self.mode.capitalize()} mode)</div></b>"
        # Add padding to the tooltip
        self.setToolTip(tooltip)   
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
                
            self.mode = mode

            
            self.update()
            self.changed.emit(self)
            canvas.update_button_positions()

        self.pose_pixmap = None
        self.last_zoom_factor = 0
        self.last_size = None

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

    def show_context_menu(self, pos):
        menu = QtWidgets.QMenu()
        menu.setWindowFlags(menu.windowFlags() | QtCore.Qt.FramelessWindowHint | QtCore.Qt.NoDropShadowWindowHint)
        menu.setAttribute(QtCore.Qt.WA_TranslucentBackground)
        menu.setStyleSheet('''
            QMenu {
                background-color: rgba(30, 30, 30, .9);
                border: 1px solid #444444;
                border-radius: 3px;
                padding: 5px 7px;
            }
            QMenu::item {
                background-color: transparent;
                padding: 3px 15px 3px 3px; ;
                margin: 3px 0px  ;
                border-radius: 3px;
            }
            QMenu::item:hover {
                background-color: #444444;
            }
            QMenu::item:selected {
                background-color: #444444;
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
        
        mode_group = QActionGroup(self)
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
                
                menu.addMenu(thumbnail_menu)
            
            #---------------------------------------------------------------------------------------
            # Button placement submenu
            placement_menu = QtWidgets.QMenu("Placement", menu)
            placement_menu.setStyleSheet(menu.styleSheet())
            
            # Z-order actions (keep these as text)
            move_behind_action = placement_menu.addAction("Move Behind")
            move_behind_action.triggered.connect(self.move_button_behind)
            
            bring_forward_action = placement_menu.addAction("Bring Forward")
            bring_forward_action.triggered.connect(self.bring_button_forward)
            
            mirror_action = placement_menu.addAction("Mirror Selected")
            mirror_action.triggered.connect(self.parent().mirror_button_positions)
            
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

            color_palette_btn = CCP.ColorPicker(palette=True)
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
                
                menu.addMenu(thumbnail_menu)    
        
        menu.addMenu(mode_menu)
        menu.addSeparator()

        menu.exec_(self.mapToGlobal(pos))
    
    def color_button_clicked(self, color):
        self.change_color_for_selected_buttons(color)
    #---------------------------------------------------------------------------------------
    def align_button_center(self):
        """Align selected buttons to be centered horizontally"""
        canvas = self.parent()
        if canvas and canvas.edit_mode:
            selected_buttons = canvas.get_selected_buttons()
            if len(selected_buttons) <= 1:
                return
                
            # Get main window for batch processing
            main_window = canvas.window()
            
            # CRITICAL: Disable batch mode temporarily for alignment
            was_batch_active = getattr(main_window, 'batch_update_active', False)
            main_window.batch_update_active = False
            
            try:
                # Calculate the average x position (center point)
                avg_x = sum(button.scene_position.x() for button in selected_buttons) / len(selected_buttons)
                
                # Move all buttons to have the same x coordinate
                for button in selected_buttons:
                    current_pos = button.scene_position
                    new_pos = QtCore.QPointF(avg_x, current_pos.y())
                    button.scene_position = new_pos
                    
                    # Force immediate database update for position changes
                    if hasattr(main_window, '_process_single_button_update'):
                        main_window._process_single_button_update(button)
                    else:
                        button.changed.emit(button)
                        
                # Update the buttons for the current tab
                if hasattr(main_window, 'update_buttons_for_current_tab'):
                    main_window.update_buttons_for_current_tab(force_update=True)
            finally:
                # Restore batch mode state
                main_window.batch_update_active = was_batch_active
    
    def align_button_left(self):
        """Align selected buttons to the leftmost button's left edge"""
        canvas = self.parent()
        if canvas and canvas.edit_mode:
            selected_buttons = canvas.get_selected_buttons()
            if len(selected_buttons) <= 1:
                return
                
            # Get main window for batch processing
            main_window = canvas.window()
            
            # CRITICAL: Disable batch mode temporarily for alignment
            was_batch_active = getattr(main_window, 'batch_update_active', False)
            main_window.batch_update_active = False
            
            try:
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
                    
                    # Force immediate database update for position changes
                    if hasattr(main_window, '_process_single_button_update'):
                        main_window._process_single_button_update(button)
                    else:
                        button.changed.emit(button)
                        
                # Update the buttons for the current tab
                if hasattr(main_window, 'update_buttons_for_current_tab'):
                    main_window.update_buttons_for_current_tab(force_update=True)
            finally:
                # Restore batch mode state
                main_window.batch_update_active = was_batch_active
    
    def align_button_right(self):
        """Align selected buttons to the rightmost button's right edge"""
        canvas = self.parent()
        if canvas and canvas.edit_mode:
            selected_buttons = canvas.get_selected_buttons()
            if len(selected_buttons) <= 1:
                return
                
            # Get main window for batch processing
            main_window = canvas.window()
            
            # CRITICAL: Disable batch mode temporarily for alignment
            was_batch_active = getattr(main_window, 'batch_update_active', False)
            main_window.batch_update_active = False
            
            try:
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
                    
                    # Force immediate database update for position changes
                    if hasattr(main_window, '_process_single_button_update'):
                        main_window._process_single_button_update(button)
                    else:
                        button.changed.emit(button)
                        
                # Update the buttons for the current tab
                if hasattr(main_window, 'update_buttons_for_current_tab'):
                    main_window.update_buttons_for_current_tab(force_update=True)
            finally:
                # Restore batch mode state
                main_window.batch_update_active = was_batch_active#---------------------------------------------------------------------------------------
    
    def align_button_top(self):
        """Align selected buttons to the topmost button's top edge"""
        canvas = self.parent()
        if canvas and canvas.edit_mode:
            selected_buttons = canvas.get_selected_buttons()
            if len(selected_buttons) <= 1:
                return
                
            # Get main window for batch processing
            main_window = canvas.window()
            
            # CRITICAL: Disable batch mode temporarily for alignment
            was_batch_active = getattr(main_window, 'batch_update_active', False)
            main_window.batch_update_active = False
            
            try:
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
                    
                    # Force immediate database update for position changes
                    if hasattr(main_window, '_process_single_button_update'):
                        main_window._process_single_button_update(button)
                    else:
                        button.changed.emit(button)
                        
                # Update the buttons for the current tab
                if hasattr(main_window, 'update_buttons_for_current_tab'):
                    main_window.update_buttons_for_current_tab(force_update=True)
            finally:
                # Restore batch mode state
                main_window.batch_update_active = was_batch_active
    
    def align_button_middle(self):
        """Align selected buttons to be centered vertically"""
        canvas = self.parent()
        if canvas and canvas.edit_mode:
            selected_buttons = canvas.get_selected_buttons()
            if len(selected_buttons) <= 1:
                return
                
            # Get main window for batch processing
            main_window = canvas.window()
            
            # CRITICAL: Disable batch mode temporarily for alignment
            was_batch_active = getattr(main_window, 'batch_update_active', False)
            main_window.batch_update_active = False
            
            try:
                # Calculate the average y position (middle point)
                avg_y = sum(button.scene_position.y() for button in selected_buttons) / len(selected_buttons)
                
                # Move all buttons to have the same y coordinate
                for button in selected_buttons:
                    current_pos = button.scene_position
                    new_pos = QtCore.QPointF(current_pos.x(), avg_y)
                    button.scene_position = new_pos
                    
                    # Force immediate database update for position changes
                    if hasattr(main_window, '_process_single_button_update'):
                        main_window._process_single_button_update(button)
                    else:
                        button.changed.emit(button)
                        
                # Update the buttons for the current tab
                if hasattr(main_window, 'update_buttons_for_current_tab'):
                    main_window.update_buttons_for_current_tab(force_update=True)
            finally:
                # Restore batch mode state
                main_window.batch_update_active = was_batch_active
    
    def align_button_bottom(self):
        """Align selected buttons to the bottommost button's bottom edge"""
        canvas = self.parent()
        if canvas and canvas.edit_mode:
            selected_buttons = canvas.get_selected_buttons()
            if len(selected_buttons) <= 1:
                return
                
            # Get main window for batch processing
            main_window = canvas.window()
            
            # CRITICAL: Disable batch mode temporarily for alignment
            was_batch_active = getattr(main_window, 'batch_update_active', False)
            main_window.batch_update_active = False
            
            try:
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
                    
                    # Force immediate database update for position changes
                    if hasattr(main_window, '_process_single_button_update'):
                        main_window._process_single_button_update(button)
                    else:
                        button.changed.emit(button)
                        
                # Update the buttons for the current tab
                if hasattr(main_window, 'update_buttons_for_current_tab'):
                    main_window.update_buttons_for_current_tab(force_update=True)
            finally:
                # Restore batch mode state
                main_window.batch_update_active = was_batch_active
    #---------------------------------------------------------------------------------------       
    def evenly_space_horizontal(self):
        """Distribute selected buttons evenly along the horizontal axis"""
        canvas = self.parent()
        if canvas and canvas.edit_mode:
            selected_buttons = canvas.get_selected_buttons()
            if len(selected_buttons) <= 2:  # Need at least 3 buttons for spacing to make sense
                return
                
            # Get main window for batch processing
            main_window = canvas.window()
            
            # CRITICAL: Disable batch mode temporarily for alignment
            was_batch_active = getattr(main_window, 'batch_update_active', False)
            main_window.batch_update_active = False
            
            try:
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
                    
                    # Force immediate database update for position changes
                    if hasattr(main_window, '_process_single_button_update'):
                        main_window._process_single_button_update(button)
                    else:
                        button.changed.emit(button)
                        
                # Update the buttons for the current tab
                if hasattr(main_window, 'update_buttons_for_current_tab'):
                    main_window.update_buttons_for_current_tab(force_update=True)
            finally:
                # Restore batch mode state
                main_window.batch_update_active = was_batch_active
                
    def evenly_space_vertical(self):
        """Distribute selected buttons evenly along the vertical axis"""
        canvas = self.parent()
        if canvas and canvas.edit_mode:
            selected_buttons = canvas.get_selected_buttons()
            if len(selected_buttons) <= 2:  # Need at least 3 buttons for spacing to make sense
                return
                
            # Get main window for batch processing
            main_window = canvas.window()
            
            # CRITICAL: Disable batch mode temporarily for alignment
            was_batch_active = getattr(main_window, 'batch_update_active', False)
            main_window.batch_update_active = False
            
            try:
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
                    
                    # Force immediate database update for position changes
                    if hasattr(main_window, '_process_single_button_update'):
                        main_window._process_single_button_update(button)
                    else:
                        button.changed.emit(button)
                        
                # Update the buttons for the current tab
                if hasattr(main_window, 'update_buttons_for_current_tab'):
                    main_window.update_buttons_for_current_tab(force_update=True)
            finally:
                # Restore batch mode state
                main_window.batch_update_active = was_batch_active
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
        self.update_tooltip()
        
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
        self.update_tooltip()
        
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
        self.update_tooltip()
        
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
        if self.mode == 'script' and self.script_data:
            script_type = self.script_data.get('type', 'python')
            
            # Get the appropriate code based on type
            if script_type == 'python':
                code = self.script_data.get('python_code', self.script_data.get('code', ''))
            else:
                code = self.script_data.get('mel_code', self.script_data.get('code', ''))
            
            if code:
                try:
                    # Get current namespace from picker window
                    main_window = self.window()
                    if isinstance(main_window, UI.AnimPickerWindow):
                        current_ns = main_window.namespace_dropdown.currentText()
                        ns_prefix = f"{current_ns}:" if current_ns and current_ns != 'None' else ""
                        
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
                        
                        # Execute the modified code
                        if script_type == 'python':
                            #print(modified_code)
                            exec(modified_code)
                        else:
                            import maya.mel as mel
                            mel.eval(modified_code)
                except Exception as e:
                    cmds.warning(f"Error executing {script_type} code: {str(e)}")
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
        self.setToolTip(f"Label: {self.label}\nSelect Set\nID: {self.unique_id}")
        # Force regeneration of text pixmap
        self.text_pixmap = None
        self.update()
        self.changed.emit(self)
    
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
                    DM.PickerDataManager.update_tab_data(current_tab, tab_data)
                    # Force immediate save for single deletions too
                    DM.PickerDataManager.save_data(DM.PickerDataManager.get_data(), force_immediate=True)
                    
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
        if canvas:
            selected_buttons = canvas.get_selected_buttons()
            for button in selected_buttons:
                button.rename_button(new_label)
            
            # Update the main window
            main_window = canvas.window()
            if isinstance(main_window, UI.AnimPickerWindow):
                main_window.update_buttons_for_current_tab()
        
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
                    print(f"Successfully deleted {original_count - new_count} buttons from database")
                    
                    # Update the database with the modified data
                    DM.PickerDataManager.update_tab_data(current_tab, tab_data)
                    
                    # Force immediate save to ensure data persistence
                    DM.PickerDataManager.save_data(DM.PickerDataManager.get_data(), force_immediate=True)
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
                
            print(f"Batch deletion complete: {len(deleted_button_ids)} buttons removed")

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
            self.update_tooltip()
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

    def remove_all_objects(self):
        self.assigned_objects = []
        self.update_tooltip()
        self.changed.emit(self)  # Notify about the change to update data
    
    def remove_all_objects_for_selected_buttons(self):
        canvas = self.parent()
        if canvas:
            selected_buttons = canvas.get_selected_buttons()
            for button in selected_buttons:
                button.assigned_objects = []
                button.update_tooltip()
                button.changed.emit(button)  # Notify about the change to update data