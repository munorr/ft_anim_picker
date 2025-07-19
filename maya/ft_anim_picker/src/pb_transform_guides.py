try:
    from PySide6 import QtWidgets, QtCore, QtGui
    from PySide6.QtCore import QTimer, QPropertyAnimation, QEasingCurve, Signal
    from shiboken6 import wrapInstance
except ImportError:
    from PySide2 import QtWidgets, QtCore, QtGui
    from PySide2.QtCore import QTimer, QPropertyAnimation, QEasingCurve, Signal
    from shiboken2 import wrapInstance
import math

from . import utils as UT
from . import custom_line_edit as CLE
from . import custom_color_picker as CCP
from . import ui as UI
from . import data_management as DM

class TransformGuides(QtWidgets.QWidget):
    """Transform guides for scaling and manipulating selected picker buttons"""
    
    # Signals for transform operations
    transform_started = Signal()
    transform_updated = Signal()
    transform_finished = Signal()
    
    def __init__(self, canvas, parent=None):
        super().__init__(parent)
        self.canvas = canvas
        self.selected_buttons = []
        self.original_states = {}  # Store original button states
        self.setMouseTracking(True)
        # Transform state
        self.is_transforming = False
        self.transform_mode = None  # 'scale', 'rotate', 'move'
        self.transform_origin = QtCore.QPointF(0, 0)
        self.last_mouse_pos = QtCore.QPointF(0, 0)
        self.initial_mouse_pos = QtCore.QPointF(0, 0)
        self.active_handle = None
        
        # Visual properties
        self.guide_color = QtGui.QColor(75, 148, 234, 180)  
        self.handle_color = QtGui.QColor(255, 255, 255, 200)  
        self.handle_size = 8
        self.guide_width = 1
        
        # Handle positions (relative to bounding rect)
        '''self.handles = {
            'top_left': QtCore.QPointF(0, 0),
            'top_center': QtCore.QPointF(0.5, 0),
            'top_right': QtCore.QPointF(1, 0),
            'middle_left': QtCore.QPointF(0, 0.5),
            'middle_right': QtCore.QPointF(1, 0.5),
            'bottom_left': QtCore.QPointF(0, 1),
            'bottom_center': QtCore.QPointF(0.5, 1),
            'bottom_right': QtCore.QPointF(1, 1),
        }'''
        self.handles = {
            'middle_right': QtCore.QPointF(1, 0.5),      # Right edge handle
            'bottom_center': QtCore.QPointF(0.5, 1),     # Bottom edge handle  
            'bottom_right': QtCore.QPointF(1, 1),        # Corner handle (will be beveled)
        }
        self.corner_icon = UT.get_icon("bottom_right_handle.png", opacity=0.8, size=12)
        # Current bounding rect of selected buttons
        self.bounding_rect = QtCore.QRectF()
        
        self.visual_layer = TransformGuidesVisual(self, parent)
        self.setVisible(False)
        self.visual_layer.setVisible(False)
        self.setAttribute(QtCore.Qt.WA_TransparentForMouseEvents, False)
        
        # Create transform controls widget
        self.controls_widget = TransformControlsWidget(canvas, parent)
        
        # Connect to canvas selection changes
        if hasattr(canvas, 'button_selection_changed'):
            canvas.button_selection_changed.connect(self.update_selection)
    
    def update_selection(self):
        """Update the transform guides based on current selection"""
        # Get fresh selection from canvas
        current_selection = self.canvas.get_selected_buttons()
        
        # Only show guides in edit mode with selected buttons
        if len(current_selection) > 0 and self.canvas.edit_mode:
            self.selected_buttons = current_selection
            self.calculate_bounding_rect()
            self.store_original_states()
            self.setVisible(True)
            self.visual_layer.setVisible(True)
            self.controls_widget.setVisible(True)  # Add this line
            self.update_position()
            
            # Update controls widget with selected buttons
            self.controls_widget.update_selection(current_selection)  # Add this line
        else:
            self.selected_buttons = []
            self.setVisible(False)
            self.visual_layer.setVisible(False)
            self.controls_widget.setVisible(False)  # Add this line
            self.original_states.clear()
        
        # Force widget update
        self.update()
        self.visual_layer.update()
    
    def calculate_bounding_rect(self):
        """Calculate the bounding rectangle of all selected buttons in scene coordinates"""
        if not self.selected_buttons:
            self.bounding_rect = QtCore.QRectF()
            return
        
        # Get button positions and sizes in scene coordinates
        min_x = float('inf')
        min_y = float('inf')
        max_x = float('-inf')
        max_y = float('-inf')
        
        for button in self.selected_buttons:
            pos = button.scene_position
            half_width = (button.width / 2) + 5
            half_height = (button.height / 2) + 5
            
            left = pos.x() - half_width
            right = pos.x() + half_width
            top = pos.y() - half_height
            bottom = pos.y() + half_height
            
            min_x = min(min_x, left)
            max_x = max(max_x, right)
            min_y = min(min_y, top)
            max_y = max(max_y, bottom)
        
        # Add small padding to prevent zero-width/height rectangles
        if max_x <= min_x:
            max_x = min_x + 10
        if max_y <= min_y:
            max_y = min_y + 10
            
        self.bounding_rect = QtCore.QRectF(min_x, min_y, max_x - min_x, max_y - min_y)
    
    def store_original_states(self):
        """Store original states of selected buttons for transform operations"""
        self.original_states = {}
        for button in self.selected_buttons:
            self.original_states[button] = {
                'position': QtCore.QPointF(button.scene_position),
                'width': button.width,
                'height': button.height,
            }
    
    def create_mouse_mask(self):
        """Create a mask that only allows mouse events on handle areas"""
        if self.bounding_rect.isEmpty():
            return
        
        # Create a region that only includes handle areas
        region = QtGui.QRegion()
        
        for handle_name in self.handles:
            handle_rect = self.get_handle_rect(handle_name)
            if not handle_rect.isEmpty():
                # Expand handle rect slightly for easier clicking
                expanded_rect = handle_rect.adjusted(-2, -2, 2, 2)
                region = region.united(QtGui.QRegion(expanded_rect.toRect()))
        
        # Set the mask - only these areas will receive mouse events
        self.setMask(region)
    
    def update_position(self):
        """Update the widget position and size to match the bounding rect"""
        if self.bounding_rect.isEmpty() or not self.selected_buttons:
            self.setVisible(False)
            self.visual_layer.setVisible(False)
            self.controls_widget.setVisible(False)
            return
        
        # Convert scene coordinates to canvas coordinates
        top_left = self.canvas.scene_to_canvas_coords(self.bounding_rect.topLeft())
        bottom_right = self.canvas.scene_to_canvas_coords(self.bounding_rect.bottomRight())
        
        # Create canvas rect and add padding for handles
        canvas_rect = QtCore.QRectF(top_left, bottom_right).normalized()
        padding = self.handle_size //2
        canvas_rect.adjust(-padding, -padding, padding, padding)
        
        # Set geometry for both layers
        self.setGeometry(canvas_rect.toRect())
        self.visual_layer.setGeometry(canvas_rect.toRect())
        
        # Create mouse mask for interactive layer
        self.create_mouse_mask()
        
        # Ensure proper stacking order
        #self.visual_layer.lower()
        self.visual_layer.raise_() 
        self.controls_widget.raise_() 
        self.raise_()              
        
        # Update controls widget position
        self.controls_widget.update_position()
        
        # Force repaint
        self.update()
        self.visual_layer.update()
    
    def get_handle_rect(self, handle_name):
        """Get the rectangle for a specific handle in widget coordinates"""
        if self.bounding_rect.isEmpty():
            return QtCore.QRectF()
        
        # Convert bounding rect to canvas coordinates
        top_left_canvas = self.canvas.scene_to_canvas_coords(self.bounding_rect.topLeft())
        bottom_right_canvas = self.canvas.scene_to_canvas_coords(self.bounding_rect.bottomRight())
        
        # Convert to widget coordinates
        widget_rect = QtCore.QRectF(
            top_left_canvas.x() - self.x(),
            top_left_canvas.y() - self.y(),
            bottom_right_canvas.x() - top_left_canvas.x(),
            bottom_right_canvas.y() - top_left_canvas.y()
        )
        
        # Get handle position
        handle_pos = self.handles[handle_name]
        center_x = widget_rect.left() + widget_rect.width() * handle_pos.x()
        center_y = widget_rect.top() + widget_rect.height() * handle_pos.y()
        
        half_size = self.handle_size / 2
        return QtCore.QRectF(
            center_x - half_size,
            center_y - half_size,
            self.handle_size,
            self.handle_size
        )
    
    def get_handle_at_pos(self, pos):
        """Get the handle name at the given position, or None - FIXED VERSION"""
        # Handle the case where pos might be QPoint or QPointF
        if hasattr(pos, 'x'):
            pos_f = QtCore.QPointF(pos.x(), pos.y()) if not isinstance(pos, QtCore.QPointF) else pos
        else:
            pos_f = QtCore.QPointF(pos)
        
        for handle_name in self.handles:
            handle_rect = self.get_handle_rect(handle_name)
            # Expand handle rect slightly for easier clicking (same as the old mask expansion)
            expanded_rect = handle_rect.adjusted(-2, -2, 2, 2)
            if expanded_rect.contains(pos_f):
                return handle_name
        return None

    def get_cursor_for_handle(self, handle_name):
        """Get the appropriate cursor for a handle"""
        cursor_map = {
            'top_left': QtCore.Qt.SizeFDiagCursor,
            'top_center': QtCore.Qt.SizeVerCursor,
            'top_right': QtCore.Qt.SizeBDiagCursor,
            'middle_left': QtCore.Qt.SizeHorCursor,
            'middle_right': QtCore.Qt.SizeHorCursor,
            'bottom_left': QtCore.Qt.SizeBDiagCursor,
            'bottom_center': QtCore.Qt.SizeVerCursor,
            'bottom_right': QtCore.Qt.SizeFDiagCursor,
        }
        return cursor_map.get(handle_name, QtCore.Qt.ArrowCursor)
    #---------------------------------------------------------------------------
    def perform_scale_transform(self, mouse_pos):
        """Ultra-stable version that completely rebuilds scaling from scratch each time"""
        if not self.selected_buttons or not hasattr(self, 'active_handle'):
            return
        
        # Ensure we have a QPointF
        mouse_pos_f = QtCore.QPointF(mouse_pos) if not isinstance(mouse_pos, QtCore.QPointF) else mouse_pos
        
        # Convert to scene coordinates
        current_scene_pos = self.canvas.canvas_to_scene_coords(mouse_pos_f)
        initial_scene_pos = self.canvas.canvas_to_scene_coords(QtCore.QPointF(self.initial_mouse_pos))
        
        # Calculate the movement delta in scene coordinates
        delta = current_scene_pos - initial_scene_pos
        
        # Get original bounding rect from stored states
        original_rect = self._get_original_bounding_rect()
        
        # Calculate new dimensions based on handle and delta
        new_width = original_rect.width()
        new_height = original_rect.height()
        
        # Apply delta based on handle type
        if 'left' in self.active_handle:
            new_width = original_rect.width() - delta.x()
        elif 'right' in self.active_handle:
            new_width = original_rect.width() + delta.x()
        
        if 'top' in self.active_handle:
            new_height = original_rect.height() - delta.y()
        elif 'bottom' in self.active_handle:
            new_height = original_rect.height() + delta.y()
        
        # Ensure minimum size
        new_width = max(10, new_width)
        new_height = max(10, new_height)
        
        # Calculate scale factors
        scale_x = new_width / original_rect.width()
        scale_y = new_height / original_rect.height()
        
        # Handle uniform scaling with Shift
        if QtWidgets.QApplication.keyboardModifiers() & QtCore.Qt.ShiftModifier:
            avg_scale = (scale_x + scale_y) / 2
            scale_x = scale_y = avg_scale
        
        # Get transform origin
        transform_origin = self._get_transform_origin_for_handle(self.active_handle, original_rect)
        
        # Apply scaling from original states
        self._apply_scaling_from_original_states(scale_x, scale_y, transform_origin)
        
        # Update visuals
        self.calculate_bounding_rect()
        self.update_position()
        self.update_edit_widgets_during_transform()
        self.transform_updated.emit()

    def _get_original_bounding_rect(self):
        """Get the bounding rect calculated from original button states"""
        if not self.original_states:
            return self.bounding_rect
        
        min_x = float('inf')
        min_y = float('inf')
        max_x = float('-inf')
        max_y = float('-inf')
        
        for button, original in self.original_states.items():
            pos = original['position']
            half_width = original['width'] / 2
            half_height = original['height'] / 2
            
            left = pos.x() - half_width
            right = pos.x() + half_width
            top = pos.y() - half_height
            bottom = pos.y() + half_height
            
            min_x = min(min_x, left)
            max_x = max(max_x, right)
            min_y = min(min_y, top)
            max_y = max(max_y, bottom)
        
        return QtCore.QRectF(min_x, min_y, max_x - min_x, max_y - min_y)

    def _get_transform_origin_for_handle(self, handle_name, rect):
        """Get the transform origin for a specific handle and rectangle"""
        origin_map = {
            'top_left': rect.bottomRight(),
            'top_center': QtCore.QPointF(rect.center().x(), rect.bottom()),
            'top_right': rect.bottomLeft(),
            'middle_left': QtCore.QPointF(rect.right(), rect.center().y()),
            'middle_right': QtCore.QPointF(rect.left(), rect.center().y()),
            'bottom_left': rect.topRight(),
            'bottom_center': QtCore.QPointF(rect.center().x(), rect.top()),
            'bottom_right': rect.topLeft(),
        }
        return origin_map.get(handle_name, rect.center())

    def _apply_scaling_from_original_states(self, scale_x, scale_y, transform_origin):
        """Apply scaling to buttons using their original states to avoid accumulation"""
        for button in self.selected_buttons:
            if button not in self.original_states:
                continue
            
            original = self.original_states[button]
            
            # Check if this is a pose mode button
            if button.mode == 'pose':
                new_width = original['width'] * scale_x
                new_height = new_width * 1.25  # Maintain pose mode ratio
            else:
                if button.shape_type == 'custom_path':
                    new_width = original['width'] * scale_x
                    new_height = original['height'] * scale_y
                else:
                    new_width = original['width'] * scale_x
                    new_height = original['height'] * scale_y
            
            # Clamp to reasonable sizes
            button.width = round(max(5, min(new_width, 2000)), 1)
            button.height = round(max(5, min(new_height, 2000)), 1)
            
            # Calculate new position from original position
            original_pos = original['position']
            offset_from_origin = original_pos - transform_origin
            
            # Scale the offset and calculate new position
            new_offset = QtCore.QPointF(
                offset_from_origin.x() * scale_x,
                offset_from_origin.y() * scale_y
            )
            button.scene_position = transform_origin + new_offset
            
            # Update button visual
            button.update()
        
        # Update canvas
        self.canvas.update_button_positions()
    #---------------------------------------------------------------------------
    def get_transform_origin(self, handle_name):
        """Get the transform origin point for a given handle in scene coordinates"""
        # For proper 1:1 scaling, use the opposite edge/corner as the anchor point
        origin_map = {
            'top_left': self.bounding_rect.bottomRight(),
            'top_center': QtCore.QPointF(self.bounding_rect.center().x(), self.bounding_rect.bottom()),
            'top_right': self.bounding_rect.bottomLeft(),
            'middle_left': QtCore.QPointF(self.bounding_rect.right(), self.bounding_rect.center().y()),
            'middle_right': QtCore.QPointF(self.bounding_rect.left(), self.bounding_rect.center().y()),
            'bottom_left': self.bounding_rect.topRight(),
            'bottom_center': QtCore.QPointF(self.bounding_rect.center().x(), self.bounding_rect.top()),
            'bottom_right': self.bounding_rect.topLeft(),
        }
        
        return origin_map.get(handle_name, self.bounding_rect.center())
    
    def update_button_data(self):
        """Update button data in the main window after transform"""
        main_window = self.canvas.window()
        if hasattr(main_window, 'batch_update_buttons_to_database'):
            main_window.batch_update_buttons_to_database(self.selected_buttons)
            #for button in self.selected_buttons:
            #    main_window.update_button_data(button)
    
    def update_edit_widgets(self):
        """FIXED: Trigger edit widget updates after transform completion"""
        main_window = self.canvas.window()
        if hasattr(main_window, 'update_edit_widgets_delayed'):
            main_window.update_edit_widgets_delayed()
    
    def update_edit_widgets_during_transform(self):
        """FIXED: Update edit widgets during transform for real-time feedback"""
        main_window = self.canvas.window()
        if (hasattr(main_window, 'edit_widgets') and 
            hasattr(main_window, 'is_updating_widgets') and 
            self.selected_buttons):
            
            # Get reference button (last selected or first in list)
            canvas = self.canvas
            reference_button = (canvas.last_selected_button 
                               if canvas.last_selected_button and canvas.last_selected_button.is_selected 
                               else self.selected_buttons[-1])
            
            # Update transform widgets with current values
            main_window.is_updating_widgets = True
            try:
                if 'transform_w_edit' in main_window.edit_widgets:
                    main_window.edit_widgets['transform_w_edit'].setValue(round(reference_button.width))
                if 'transform_h_edit' in main_window.edit_widgets:
                    main_window.edit_widgets['transform_h_edit'].setValue(round(reference_button.height))
            finally:
                main_window.is_updating_widgets = False
    #---------------------------------------------------------------------------    
    def mousePressEvent(self, event):
        """Handle mouse press for starting transforms - FIXED VERSION"""
        if event.button() == QtCore.Qt.MiddleButton:
            event.ignore()
            return
        
        if event.button() != QtCore.Qt.LeftButton:
            event.ignore()
            return
        
        # Convert to QPointF to avoid type issues
        pos_f = QtCore.QPointF(event.pos())
        handle = self.get_handle_at_pos(pos_f)
        
        if handle:
            self.is_transforming = True
            self.transform_mode = 'scale'
            self.active_handle = handle
            
            # Store mouse positions as QPointF
            self.last_mouse_pos = pos_f
            self.initial_mouse_pos = pos_f
            
            # Calculate and store original states (this is crucial for stability)
            self.store_original_states()
            
            # Calculate transform origin based on original rect, not current
            original_rect = self._get_original_bounding_rect()
            self.transform_origin = self._get_transform_origin_for_handle(handle, original_rect)
            
            self.transform_started.emit()
            event.accept()
        else:
            # Clicked outside handle areas - consume the event to prevent canvas drag selection
            # but don't start any transform operation
            event.accept()
        
    def mouseMoveEvent(self, event):
        """Handle mouse move for active transforms and cursor updates - FIXED VERSION"""
        if event.buttons() & QtCore.Qt.MiddleButton:
            event.ignore()
            return
        
        # Convert to QPointF
        pos_f = QtCore.QPointF(event.pos())
        
        if self.is_transforming and self.transform_mode == 'scale':
            self.perform_scale_transform(pos_f)
            event.accept()
        else:
            # Update cursor based on handle under mouse
            handle = self.get_handle_at_pos(pos_f)
            if handle:
                self.setCursor(self.get_cursor_for_handle(handle))
            else:
                self.setCursor(QtCore.Qt.ArrowCursor)
            event.accept()
    
    def mouseReleaseEvent(self, event):
        """Handle mouse release to finish transforms"""
        if event.buttons() & QtCore.Qt.MiddleButton:
            event.ignore()
            return

        if event.button() == QtCore.Qt.MiddleButton:
            event.ignore()
            return
        
        if self.is_transforming:
            self.is_transforming = False
            self.transform_mode = None
            self.active_handle = None
            
            # Update button data and emit signal
            self.update_button_data()
            self.transform_finished.emit()
            
            # Recalculate and update position
            self.calculate_bounding_rect()
            self.update_position()
            
            event.accept()
        else:
            event.ignore()
    
    def wheelEvent(self, event):
        """Let wheel events pass through for zooming"""
        event.ignore()

    def paintEvent(self, event):
        """Paint the transform guides and handles with image for corner"""
        if not self.selected_buttons or self.bounding_rect.isEmpty() or not self.isVisible():
            return
        
        painter = QtGui.QPainter(self)
        painter.setRenderHint(QtGui.QPainter.Antialiasing)
        painter.setRenderHint(QtGui.QPainter.SmoothPixmapTransform)
        
        # Draw handles
        for handle_name in self.handles:
            handle_rect = self.get_handle_rect(handle_name)
            if not handle_rect.isEmpty():
                if handle_name == 'bottom_right':
                    # Draw image handle for corner
                    self._draw_image_handle(painter, handle_rect)
                else:
                    # Draw regular square handles for edges
                    painter.setPen(QtGui.QPen(self.guide_color, 1))
                    painter.setBrush(QtGui.QBrush(self.handle_color))
                    painter.drawRect(handle_rect)

    def _draw_image_handle(self, painter, handle_rect):
        """Draw the corner handle using an image"""
        if self.corner_icon and not self.corner_icon.isNull():
            # Calculate position to center the icon in the handle rect
            icon_rect = QtCore.QRect(
                int(handle_rect.center().x() - self.corner_icon.width() / 2),
                int(handle_rect.center().y() - self.corner_icon.height() / 2),
                self.corner_icon.width(),
                self.corner_icon.height()
            )
            
            # Draw the icon
            painter.drawPixmap(icon_rect, self.corner_icon)

class TransformGuidesVisual(QtWidgets.QWidget):
    """Visual-only widget for drawing guide lines - transparent to mouse events"""
    
    def __init__(self, parent_guides, parent=None):
        super().__init__(parent)
        self.parent_guides = parent_guides
        self.setAttribute(QtCore.Qt.WA_TransparentForMouseEvents, True)
        self.setAttribute(QtCore.Qt.WA_TranslucentBackground, True)
        
    def paintEvent(self, event):
        """Paint only the guide lines, not the handles"""
        if (not self.parent_guides.selected_buttons or 
            self.parent_guides.bounding_rect.isEmpty() or 
            not self.isVisible()):
            return
        
        painter = QtGui.QPainter(self)
        painter.setRenderHint(QtGui.QPainter.Antialiasing)
        
        # Convert bounding rect to widget coordinates
        top_left_canvas = self.parent_guides.canvas.scene_to_canvas_coords(
            self.parent_guides.bounding_rect.topLeft()
        )
        bottom_right_canvas = self.parent_guides.canvas.scene_to_canvas_coords(
            self.parent_guides.bounding_rect.bottomRight()
        )
        
        # Widget-relative coordinates
        widget_rect = QtCore.QRectF(
            top_left_canvas.x() - self.x(),
            top_left_canvas.y() - self.y(),
            bottom_right_canvas.x() - top_left_canvas.x(),
            bottom_right_canvas.y() - top_left_canvas.y()
        )
        
        # Don't draw if the rect is too small or invalid
        if widget_rect.width() < 2 or widget_rect.height() < 2:
            return
        
        # Draw bounding box with blue dashed lines
        pen = QtGui.QPen(self.parent_guides.guide_color)
        pen.setWidth(self.parent_guides.guide_width)
        pen.setStyle(QtCore.Qt.DashLine)
        painter.setPen(pen)
        painter.setBrush(QtCore.Qt.NoBrush)
        painter.drawRect(widget_rect)
 
class TransformControlsWidget(QtWidgets.QWidget):
    """Widget for controlling button properties that appears above transform guides"""
    
    def __init__(self, canvas, parent=None):
        super().__init__(parent)
        self.canvas = canvas
        self.selected_buttons = []
        
        # Widget properties
        self.setFixedHeight(28)
        self.setup_ui()
        self.setVisible(False)

        # Use QGraphicsOpacityEffect instead of windowOpacity
        self.opacity_effect = QtWidgets.QGraphicsOpacityEffect()
        self.opacity_effect.setOpacity(0.2)
        self.setGraphicsEffect(self.opacity_effect)

        self.fade_timer = QTimer(self)
        self.fade_timer.setSingleShot(True)
        self.fade_timer.timeout.connect(self.start_fade_animation)

        # Animate the opacity effect instead
        self.fade_animation = QPropertyAnimation(self.opacity_effect, b"opacity")
        self.fade_animation.setDuration(1000)
        self.fade_animation.setEasingCurve(QEasingCurve.InOutQuad)

        self.installEventFilter(self)
        
    def setup_ui(self):
        """Set up the UI layout"""
        def set_margin_space(layout,margin,space):
            layout.setContentsMargins(margin,margin,margin,margin)
            layout.setSpacing(space)
        
        layout = QtWidgets.QHBoxLayout(self)
        set_margin_space(layout,0,0)
        layout.addStretch()
        
        frame = QtWidgets.QFrame()
        frame.setStyleSheet("background-color: rgba(40, 40, 40, 0.9); border: 1px solid rgba(80, 80, 80, 0.8); border-radius: 4px;")
        layout.addWidget(frame)
        frame_layout = QtWidgets.QHBoxLayout(frame)
        set_margin_space(frame_layout,4,2)
        frame_layout.addStretch()

        #---------------------------------------------------------------------------------------------------------------------------------------
        self.color_palette_btn = CCP.ColorPicker(mode='palette')
        def handle_color_picker_change(qcolor):
            main_window = self.window()
            if hasattr(main_window, "change_color_for_selected_buttons"):
                main_window.change_color_for_selected_buttons(qcolor)
        
        self.color_palette_btn.colorChanged.connect(handle_color_picker_change)
        #---------------------------------------------------------------------------------------------------------------------------------------
        # Radius widgets
        bh = 2000  # button height max
        self.top_left_radius = CLE.IntegerLineEdit(min_value=0, max_value=bh, increment=1, height=18, width=45, label="R")
        self.top_right_radius = CLE.IntegerLineEdit(min_value=0, max_value=bh, increment=1, height=18, width=32, label="╮")
        self.bottom_left_radius = CLE.IntegerLineEdit(min_value=0, max_value=bh, increment=1, height=18, width=32, label="╰")
        self.bottom_right_radius = CLE.IntegerLineEdit(min_value=0, max_value=bh, increment=1, height=18, width=32, label="╯")
        
        def handle_radius_change(tl, tr, bl, br):
            main_window = self.window()
            if hasattr(main_window, "set_radius_for_selected_buttons"):
                main_window.set_radius_for_selected_buttons(tl, tr, br, bl)
        
        # Connect final value changes (mouse release) to database save
        self.top_left_radius.valueChanged.connect(lambda tl: handle_radius_change(tl, tl, tl, tl))
        
        # Connect real-time changes (during drag) to visual updates only
        #self.top_left_radius.valueChangedRealTime.connect(lambda tl: handle_radius_change(tl, tl, tl, tl, save_to_db=False))
        #self.top_right_radius.valueChanged.connect(lambda tr: handle_radius_change(self.top_left_radius.value(), tr, self.bottom_left_radius.value(), self.bottom_right_radius.value()))
        #self.bottom_left_radius.valueChanged.connect(lambda bl: handle_radius_change(self.top_left_radius.value(), self.top_right_radius.value(), bl, self.bottom_right_radius.value()))
        #self.bottom_right_radius.valueChanged.connect(lambda br: handle_radius_change(self.top_left_radius.value(), self.top_right_radius.value(), self.bottom_left_radius.value(), br))
        
        frame_layout.addWidget(self.top_left_radius)
        #frame_layout.addWidget(self.top_right_radius)
        #frame_layout.addWidget(self.bottom_left_radius)
        #frame_layout.addWidget(self.bottom_right_radius)
        frame_layout.addWidget(self.color_palette_btn)
    #---------------------------------------------------------------------------------------------------------------------------------------
    def update_selection(self, selected_buttons):
        """Update the controls based on selected buttons"""
        self.selected_buttons = selected_buttons
        
        if not selected_buttons:
            self.setVisible(False)
            return
        
        # Show widget if buttons are selected
        self.setVisible(True)
        
        # Get the last selected button as reference for the UI controls
        # This only updates the UI controls, not the actual button properties
        reference_button = selected_buttons[-1] if selected_buttons else None
        
        # Temporarily disconnect signals to prevent triggering changes
        # when we're just updating the UI controls
        self._disconnect_signals()
        
        # Update color picker with the color from the reference button
        if reference_button and hasattr(reference_button, 'color'):
            current_qcolor = QtGui.QColor(reference_button.color)
            self.color_palette_btn.current_color = current_qcolor
            self.color_palette_btn.update_all_from_color()
        
        # Update radius widgets with the radius from the reference button
        if reference_button and hasattr(reference_button, 'radius'):
            self.top_left_radius.setValue(reference_button.radius[0])
            self.top_right_radius.setValue(reference_button.radius[1])
            self.bottom_left_radius.setValue(reference_button.radius[2])
            self.bottom_right_radius.setValue(reference_button.radius[3])
        
        # Reconnect signals after updating UI controls
        self._reconnect_signals()
    
    def update_position(self):
        """Update position to appear above transform guides"""
        if not self.isVisible():
            return
        
        # Get transform guides position and size
        guides = self.canvas.transform_guides
        if not guides.isVisible():
            return
        
        guides_rect = guides.geometry()
        
        # Position above the guides, aligned to the right edge
        new_x = guides_rect.right() - self.width()  # Align to right edge
        new_y = guides_rect.top() - self.height() - 5  # 5px spacing above
        
        # Ensure it doesn't go off screen
        canvas_rect = self.canvas.rect()
        if new_y < 0:
            new_y = guides_rect.bottom() + 5  # Position below if can't fit above
        
        if new_x < 0:
            new_x = 0  # Don't go past left edge
        
        if new_x + self.width() > canvas_rect.width():
            new_x = canvas_rect.width() - self.width()  # Don't go past right edge
        
        self.setGeometry(new_x, new_y, self.width(), self.height())
    #---------------------------------------------------------------------------------------------------------------------------------------
    def handle_enter_event(self):
        self.fade_timer.stop()
        self.fade_animation.stop()
        self.fade_animation.setDuration(100)
        self.fade_animation.setStartValue(self.opacity_effect.opacity())
        self.fade_animation.setEndValue(1.0)
        self.fade_animation.start()

    def handle_leave_event(self):
        self.fade_timer.start(10)

    def start_fade_animation(self):
        self.fade_animation.setDuration(400)
        self.fade_animation.setStartValue(self.opacity_effect.opacity())
        self.fade_animation.setEndValue(0.2)
        self.fade_animation.start()

    def eventFilter(self, obj, event):
        if obj == self:
            if event.type() == QtCore.QEvent.Enter:
                self.handle_enter_event()
            elif event.type() == QtCore.QEvent.Leave:
                self.handle_leave_event()
        return super().eventFilter(obj, event)
        
    def _disconnect_signals(self):
        """Temporarily disconnect signals to prevent triggering changes when updating UI controls"""
        try:
            self.color_palette_btn.colorChanged.disconnect()
            self.top_left_radius.valueChanged.disconnect()
        except Exception:
            # If signals were already disconnected or never connected, ignore errors
            pass
            
    def _reconnect_signals(self):
        """Reconnect signals after updating UI controls"""
        # Reconnect color picker signal
        def handle_color_picker_change(qcolor):
            main_window = self.window()
            if hasattr(main_window, "change_color_for_selected_buttons"):
                main_window.change_color_for_selected_buttons(qcolor.name())
                
        self.color_palette_btn.colorChanged.connect(handle_color_picker_change)
        
        # Reconnect radius signals
        def handle_radius_change(tl):
            main_window = self.window()
            if hasattr(main_window, "set_radius_for_selected_buttons"):
                main_window.set_radius_for_selected_buttons(tl, tl, tl, tl)
                
        self.top_left_radius.valueChanged.connect(lambda tl: handle_radius_change(tl))

 