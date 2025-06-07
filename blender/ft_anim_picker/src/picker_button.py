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
                    'script_data': self._safe_copy_dict(button.script_data)
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

        self.rotation = 0
    
        self.setStyleSheet(f"QToolTip {{background-color: {UT.rgba_value(color,.7,alpha=1)}; color: #eeeeee ; border: 1px solid rgba(255,255,255,.2); padding: 0px;}}")
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
        self.last_radius = None    # Track radius to know when to regenerate the pixmap
        self.last_text = None      # Track text to know when to regenerate the pixmap

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
                painter.setBrush(QtGui.QColor(self.color))
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
        """Button mouse press with alt-click duplication support - ENHANCED VERSION"""
        if event.button() == QtCore.Qt.LeftButton:
            canvas = self.parent()
            if canvas:
                # Check for Alt and Ctrl modifiers
                alt_held = event.modifiers() & QtCore.Qt.AltModifier
                ctrl_held = event.modifiers() & QtCore.Qt.ControlModifier
                
                if self.edit_mode:
                    # Alt+Click duplication in edit mode
                    if alt_held:
                        self.start_duplication_drag(event)
                    else:
                        # Normal dragging behavior
                        self.dragging = True
                        self.drag_start_pos = event.globalPos()
                        self.button_start_pos = self.scene_position
                        self.setCursor(QtCore.Qt.ClosedHandCursor)
                        
                        selected_buttons = canvas.get_selected_buttons()
                        
                        if not self.is_selected and not (event.modifiers() & QtCore.Qt.ShiftModifier):
                            canvas.clear_selection()
                            self.is_selected = True
                            self.selected.emit(self, True)
                            canvas.last_selected_button = self
                            canvas.button_selection_changed.emit()
                            self.update()
                        elif event.modifiers() & QtCore.Qt.ShiftModifier:
                            self.is_selected = not self.is_selected
                            if self.is_selected:
                                canvas.last_selected_button = self
                            self.selected.emit(self, self.is_selected)
                            canvas.button_selection_changed.emit()
                            self.update()
                        
                        # Set button start positions for dragging
                        for button in selected_buttons:
                            button.button_start_pos = button.scene_position
                else:
                    # Select mode behavior (existing code remains the same)
                    if self.mode == 'select':
                        if hasattr(self, 'selectable') and self.selectable:
                            shift_held = event.modifiers() & QtCore.Qt.ShiftModifier
                            
                            if not shift_held:
                                canvas.clear_selection()
                            
                            if shift_held:
                                self.is_selected = not self.is_selected
                            else:
                                self.is_selected = True
                            
                            if self.is_selected:
                                canvas.last_selected_button = self
                            
                            self.selected.emit(self, self.is_selected)
                            canvas.button_selection_changed.emit()
                            self.update()
                            
                            canvas.apply_final_selection(shift_held)
                            
                    elif self.mode == 'script':
                        self.execute_script_command()
                    elif self.mode == 'pose':
                        # Handle pose mode with mirror pose support
                        if ctrl_held:
                            # Ctrl+LMB applies mirrored pose
                            self.apply_pose_to_mirrored_objects()
                        else:
                            # Normal LMB applies regular pose
                            self.apply_pose()
                    
                event.accept()
        elif event.button() == QtCore.Qt.RightButton:
            canvas = self.parent()
            if canvas:
                if not self.is_selected:
                    canvas.clear_selection()
                    self.is_selected = True
                    self.selected.emit(self, True)
                    canvas.last_selected_button = self
                    canvas.button_selection_changed.emit()
                    self.update()
            
            self.show_context_menu(event.pos())
            event.accept()
        else:
            super().mousePressEvent(event)
        
        UT.blender_main_window()
    
    def mouseMoveEvent(self, event):
        """Enhanced mouse move with duplication support"""
        if hasattr(self, 'duplicating') and self.duplicating and event.buttons() & QtCore.Qt.LeftButton:
            # Handle duplication drag
            self.handle_duplication_drag(event)
            event.accept()
        elif self.dragging and event.buttons() & QtCore.Qt.LeftButton:
            # Normal dragging behavior
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
        """Enhanced mouse release with duplication completion"""
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
                    selected_buttons = canvas.get_selected_buttons()
                    
                    main_window = canvas.window()
                    if isinstance(main_window, UI.BlenderAnimPickerWindow):
                        was_batch_active = getattr(main_window, 'batch_update_active', False)
                        main_window.batch_update_active = False
                        
                        try:
                            for button in selected_buttons:
                                main_window._process_single_button_update(button)
                            
                            main_window.update_buttons_for_current_tab(force_update=True)
                            
                        finally:
                            main_window.batch_update_active = was_batch_active
                
                event.accept()
        else:
            super().mouseReleaseEvent(event)
        
        UT.blender_main_window()
    
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
        
        self.setToolTip(tooltip)
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
                main_window.batch_update_active = was_batch_active
    #---------------------------------------------------------------------------------------
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
        """Enhanced paste method that handles different types of paste operations - TRULY FIXED VERSION"""
        canvas = self.parent()
        if canvas and canvas.edit_mode:
            attributes = ButtonClipboard.instance().get_last_attributes()
            if attributes:
                selected_buttons = canvas.get_selected_buttons()
                
                if not selected_buttons:
                    return
                
                # Get main window for batch processing
                main_window = canvas.window()
                
                # CRITICAL FIX: Stop ALL timers and disable ALL update systems
                was_batch_active = getattr(main_window, 'batch_update_active', False)
                main_window.batch_update_active = False
                
                # Stop any pending batch timer
                if hasattr(main_window, 'batch_update_timer'):
                    main_window.batch_update_timer.stop()
                
                # Clear any pending updates
                if hasattr(main_window, 'pending_button_updates'):
                    main_window.pending_button_updates.clear()
                
                # Disable widget updates
                if hasattr(main_window, 'edit_widgets_update_enabled'):
                    was_widgets_enabled = main_window.edit_widgets_update_enabled
                    main_window.edit_widgets_update_enabled = False
                else:
                    was_widgets_enabled = True
                
                # Disable canvas updates during batch operation
                canvas.setUpdatesEnabled(False)
                
                # Disconnect the changed signal temporarily to prevent interference
                for button in selected_buttons:
                    try:
                        button.changed.disconnect()
                    except:
                        pass
                
                try:
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
                        
                        # Create complete button data for database
                        button_data = {
                            "id": button.unique_id,
                            "label": button.label,
                            "color": button.color,
                            "opacity": button.opacity,
                            "position": (button.scene_position.x(), button.scene_position.y()),
                            "width": button.width,
                            "height": button.height,
                            "radius": button.radius,
                            "assigned_objects": getattr(button, 'assigned_objects', []),
                            "mode": getattr(button, 'mode', 'select'),
                            "script_data": getattr(button, 'script_data', {'code': '', 'type': 'python'}),
                            "pose_data": getattr(button, 'pose_data', {}),
                            "thumbnail_path": getattr(button, 'thumbnail_path', '')
                        }
                        
                        # Update in tab_data
                        updated = False
                        for i, existing_button in enumerate(tab_data['buttons']):
                            if existing_button['id'] == button.unique_id:
                                tab_data['buttons'][i] = button_data
                                updated = True
                                break
                        
                        if not updated:
                            tab_data['buttons'].append(button_data)
                        
                        updated_buttons.append(button.unique_id)
                    
                    # Save all updates at once
                    DM.PickerDataManager.update_tab_data(current_tab, tab_data)
                    #print(f"Pasted attributes to {len(updated_buttons)} buttons: {updated_buttons}")
                    
                finally:
                    # Reconnect signals
                    for button in selected_buttons:
                        button.changed.connect(main_window.on_button_changed)
                    
                    # Restore batch mode state
                    main_window.batch_update_active = was_batch_active
                    
                    # Restore widget updates
                    if hasattr(main_window, 'edit_widgets_update_enabled'):
                        main_window.edit_widgets_update_enabled = was_widgets_enabled
                    
                    # Re-enable canvas updates
                    canvas.setUpdatesEnabled(True)
                    canvas.update_button_positions()
                    canvas.update()
                
                # Force immediate main window update
                if hasattr(main_window, 'update_buttons_for_current_tab'):
                    main_window.update_buttons_for_current_tab(force_update=True)
                
               #print(f"Paste operation completed successfully for {len(selected_buttons)} buttons ({paste_type})")
    #---------------------------------------------------------------------------------------
    def set_script_data(self, data):
        self.script_data = data
        self.changed.emit(self)
        self.update_tooltip()
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
        self.update_tooltip()
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
                print(f"Processing pose entry: '{pose_key}'")
                
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

    def apply_pose_to_mirrored_objects(self):
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
                print(f"Processing mirror pose for: '{pose_key}'")
                
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
                        print(f"Applied mirrored pose to object '{mirrored_obj.name}'")
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

    def _select_posed_objects_and_bones_with_namespace(self, successfully_posed_objects, posed_bones_by_armature):
        """Select the successfully posed objects and their bones in Blender with namespace priority"""
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
            bpy.context.view_layer.objects.active = successfully_posed_objects[-1]
            
            # Select posed bones if any exist, prioritizing current namespace
            if posed_bones_by_armature:
                # Find the target armature (namespace priority)
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
        self.setToolTip(f"Label: {self.label}\nSelect Set\nID: {self.unique_id}")
        # Force regeneration of text pixmap
        self.text_pixmap = None
        self.update()
        self.changed.emit(self)
    
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
            
            if active_obj and active_obj.type == 'ARMATURE':
                # Check if we're in pose mode or need to switch
                
                object_mode = getattr(active_obj, 'mode', 'OBJECT')
                context_mode = getattr(bpy.context, 'mode', 'OBJECT')
                
                print(f"Object mode: {object_mode}, Context mode: {context_mode}")
                
                # Try multiple methods to get selected pose bones
                selected_pose_bones = []
                
                # Method 1: Try context selected_pose_bones
                try:
                    context_bones = getattr(bpy.context, 'selected_pose_bones', None)
                    if context_bones:
                        selected_pose_bones = list(context_bones)
                        print(f"Found {len(selected_pose_bones)} bones via context")
                except:
                    pass
                
                # Method 2: If no bones found via context, check bone selection manually
                if not selected_pose_bones and active_obj.pose:
                    for pose_bone in active_obj.pose.bones:
                        if pose_bone.bone.select:
                            selected_pose_bones.append(pose_bone)
                    print(f"Found {len(selected_pose_bones)} bones via manual check")
                
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
                            print(f"Found {len(selected_pose_bones)} bones after mode switch")
                    except Exception as e:
                        print(f"Error switching to pose mode: {e}")
                
                print(f"Final selected pose bones: {[bone.name for bone in selected_pose_bones]}")
                
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
            
            print(f"Added {len(new_unique_objects)} new objects to picker")
        
        self.update_tooltip()
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