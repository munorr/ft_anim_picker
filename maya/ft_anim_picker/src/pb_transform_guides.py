try:
    from PySide6 import QtWidgets, QtCore, QtGui
    from PySide6.QtCore import QTimer, QPropertyAnimation, QEasingCurve, Signal
    from shiboken6 import wrapInstance
except ImportError:
    from PySide2 import QtWidgets, QtCore, QtGui
    from PySide2.QtCore import QTimer, QPropertyAnimation, QEasingCurve, Signal
    from shiboken2 import wrapInstance
import math
from functools import partial

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
        self.handles = {
            'top_left': QtCore.QPointF(0, 0),
            'top_center': QtCore.QPointF(0.5, 0),
            'top_right': QtCore.QPointF(1, 0),
            'middle_left': QtCore.QPointF(0, 0.5),
            'middle_right': QtCore.QPointF(1, 0.5),
            'bottom_left': QtCore.QPointF(0, 1),
            'bottom_center': QtCore.QPointF(0.5, 1),
            'bottom_right': QtCore.QPointF(1, 1),
        }
        self.corner_icon = UT.get_icon("bottom_right_handle.png", opacity=0.8, size=12)

        # Rotation via corner zones (outside the resize handles)
        self.rotation_initial_angle = 0
        self.rotation_corner_margin = 10  # px outward from corner handles

        # Guide rotation — matches button rotation for single/uniform selection
        self.guide_rotation = 0

        # Current bounding rect of selected buttons (in un-rotated guide space)
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
            self.controls_widget.setVisible(True)
            self.update_position()

            # Update controls widget with selected buttons
            self.controls_widget.update_selection(current_selection)
        else:
            self.selected_buttons = []
            self.setVisible(False)
            self.visual_layer.setVisible(False)
            self.controls_widget.setVisible(False)
            self.original_states.clear()

        # Force widget update
        self.update()
        self.visual_layer.update()

    def _compute_guide_rotation(self):
        """Determine guide rotation from selected buttons.
        If all selected buttons share the same rotation, guides rotate to match.
        Otherwise guides stay axis-aligned (0)."""
        if not self.selected_buttons:
            return 0
        first_rot = self.selected_buttons[0].rotation
        for btn in self.selected_buttons[1:]:
            if abs(btn.rotation - first_rot) > 0.01:
                return 0  # mixed rotations -> axis-aligned
        return first_rot

    def calculate_bounding_rect(self):
        """Calculate the bounding rectangle of all selected buttons.
        When guide_rotation != 0, the rect is in the rotated coordinate frame
        (using un-rotated button dimensions). Otherwise axis-aligned envelope."""
        if not self.selected_buttons:
            self.bounding_rect = QtCore.QRectF()
            self.guide_rotation = 0
            return

        self.guide_rotation = self._compute_guide_rotation()

        min_x = float('inf')
        min_y = float('inf')
        max_x = float('-inf')
        max_y = float('-inf')

        if self.guide_rotation != 0:
            # Work in the rotated coordinate frame — use un-rotated button w/h
            rad = math.radians(-self.guide_rotation)
            cos_r, sin_r = math.cos(rad), math.sin(rad)
            for button in self.selected_buttons:
                pos = button.scene_position
                # Rotate position into guide frame
                rx = pos.x() * cos_r - pos.y() * sin_r
                ry = pos.x() * sin_r + pos.y() * cos_r
                hw = (button.width / 2) + 5
                hh = (button.height / 2) + 5
                min_x = min(min_x, rx - hw)
                max_x = max(max_x, rx + hw)
                min_y = min(min_y, ry - hh)
                max_y = max(max_y, ry + hh)
        else:
            # Axis-aligned — use rotated envelope
            for button in self.selected_buttons:
                pos = button.scene_position
                env_w, env_h = button.rotated_envelope_size()
                hw = (env_w / 2) + 5
                hh = (env_h / 2) + 5
                min_x = min(min_x, pos.x() - hw)
                max_x = max(max_x, pos.x() + hw)
                min_y = min(min_y, pos.y() - hh)
                max_y = max(max_y, pos.y() + hh)

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
                'rotation': button.rotation,
            }

    def create_mouse_mask(self):
        """Create a mask that only allows mouse events on handle areas and rotation zones"""
        if self.bounding_rect.isEmpty():
            return

        # Create a region that only includes handle areas
        region = QtGui.QRegion()

        for handle_name in self.handles:
            handle_rect = self.get_handle_rect(handle_name)
            if not handle_rect.isEmpty():
                expanded_rect = handle_rect.adjusted(-2, -2, 2, 2)
                region = region.united(QtGui.QRegion(expanded_rect.toRect()))

        # Include rotation corner zones (outside each corner handle)
        for corner, zone_rect in self.get_rotation_corner_rects().items():
            region = region.united(QtGui.QRegion(zone_rect.toRect()))

        # Set the mask - only these areas will receive mouse events
        self.setMask(region)

    def _bbox_center_in_scene(self):
        """Get the bounding rect center in scene coordinates.
        When guide_rotation != 0, the bounding rect is in rotated frame, so
        we rotate the center back to scene space."""
        center = self.bounding_rect.center()
        if self.guide_rotation == 0:
            return center
        rad = math.radians(self.guide_rotation)
        cos_r, sin_r = math.cos(rad), math.sin(rad)
        return QtCore.QPointF(
            center.x() * cos_r - center.y() * sin_r,
            center.x() * sin_r + center.y() * cos_r
        )

    def _rotated_corners_in_scene(self):
        """Get the four corners of the bounding rect rotated back to scene space."""
        r = self.bounding_rect
        corners = [r.topLeft(), r.topRight(), r.bottomRight(), r.bottomLeft()]
        if self.guide_rotation == 0:
            return corners
        rad = math.radians(self.guide_rotation)
        cos_r, sin_r = math.cos(rad), math.sin(rad)
        rotated = []
        for c in corners:
            rotated.append(QtCore.QPointF(
                c.x() * cos_r - c.y() * sin_r,
                c.x() * sin_r + c.y() * cos_r
            ))
        return rotated

    def update_position(self):
        """Update the widget position and size to match the bounding rect.

        When the bounding rect extends beyond the canvas viewport the widget
        geometry is clamped so that handles remain on-screen and accessible.
        """
        if self.bounding_rect.isEmpty() or not self.selected_buttons:
            self.setVisible(False)
            self.visual_layer.setVisible(False)
            self.controls_widget.setVisible(False)
            return

        padding = self.handle_size // 2 + self.rotation_corner_margin + 2

        if self.guide_rotation != 0:
            # Compute axis-aligned envelope of the rotated bounding rect in canvas coords
            scene_corners = self._rotated_corners_in_scene()
            canvas_corners = [self.canvas.scene_to_canvas_coords(sc) for sc in scene_corners]
            xs = [c.x() for c in canvas_corners]
            ys = [c.y() for c in canvas_corners]
            canvas_rect = QtCore.QRectF(
                min(xs), min(ys),
                max(xs) - min(xs), max(ys) - min(ys)
            )
            canvas_rect.adjust(-padding, -padding, padding, padding)
        else:
            top_left = self.canvas.scene_to_canvas_coords(self.bounding_rect.topLeft())
            bottom_right = self.canvas.scene_to_canvas_coords(self.bounding_rect.bottomRight())
            canvas_rect = QtCore.QRectF(top_left, bottom_right).normalized()
            canvas_rect.adjust(-padding, -padding, padding, padding)

        # Clamp to the canvas viewport so handles stay on-screen
        viewport = QtCore.QRectF(self.canvas.rect())
        canvas_rect = canvas_rect.intersected(viewport)
        if canvas_rect.isEmpty():
            # Guides entirely off-screen — hide until they scroll back
            self.setVisible(False)
            self.visual_layer.setVisible(False)
            self.controls_widget.setVisible(False)
            return

        # Set geometry for both layers
        self.setGeometry(canvas_rect.toRect())
        self.visual_layer.setGeometry(canvas_rect.toRect())

        # Create mouse mask for interactive layer
        self.create_mouse_mask()

        # Ensure proper stacking order
        self.visual_layer.raise_()
        self.controls_widget.raise_()
        self.raise_()

        # Update controls widget position
        self.controls_widget.update_position()

        # Force repaint
        self.update()
        self.visual_layer.update()

    def _handle_center_in_scene(self, handle_name):
        """Get the center of a handle in scene coordinates, accounting for guide rotation."""
        handle_pos = self.handles[handle_name]
        # Position in the bounding rect's local frame
        lx = self.bounding_rect.left() + self.bounding_rect.width() * handle_pos.x()
        ly = self.bounding_rect.top() + self.bounding_rect.height() * handle_pos.y()
        if self.guide_rotation == 0:
            return QtCore.QPointF(lx, ly)
        # Rotate from guide frame back to scene space
        rad = math.radians(self.guide_rotation)
        cos_r, sin_r = math.cos(rad), math.sin(rad)
        return QtCore.QPointF(lx * cos_r - ly * sin_r, lx * sin_r + ly * cos_r)

    def get_handle_rect(self, handle_name):
        """Get the rectangle for a specific handle in widget coordinates.

        Handle positions are clamped to the visible widget area so they remain
        accessible even when the bounding rect extends beyond the viewport.
        """
        if self.bounding_rect.isEmpty():
            return QtCore.QRectF()

        scene_pt = self._handle_center_in_scene(handle_name)
        canvas_pt = self.canvas.scene_to_canvas_coords(scene_pt)
        # Convert to widget-local
        wx = canvas_pt.x() - self.x()
        wy = canvas_pt.y() - self.y()

        # Clamp to widget bounds so off-screen handles stay reachable
        half_size = self.handle_size / 2
        margin = half_size + 2
        wx = max(margin, min(wx, self.width() - margin))
        wy = max(margin, min(wy, self.height() - margin))

        return QtCore.QRectF(wx - half_size, wy - half_size, self.handle_size, self.handle_size)

    def get_rotation_corner_rects(self):
        """Get rotation zone rectangles just outside each corner handle.
        Returns dict mapping corner name to QRectF in widget coords."""
        if self.bounding_rect.isEmpty():
            return {}
        margin = self.rotation_corner_margin
        zone_size = self.handle_size + margin * 2
        result = {}
        for corner in ('top_left', 'top_right', 'bottom_left', 'bottom_right'):
            handle_rect = self.get_handle_rect(corner)
            if handle_rect.isEmpty():
                continue
            # Expand outward from the corner direction
            cx, cy = handle_rect.center().x(), handle_rect.center().y()
            # Determine which direction is "outward" for this corner
            dx = -1 if 'left' in corner else 1
            dy = -1 if 'top' in corner else 1
            zone_cx = cx + dx * (self.handle_size / 2 + margin / 2)
            zone_cy = cy + dy * (self.handle_size / 2 + margin / 2)
            result[corner] = QtCore.QRectF(
                zone_cx - zone_size / 2, zone_cy - zone_size / 2,
                zone_size, zone_size
            )
        return result

    def get_handle_at_pos(self, pos):
        """Get the handle name at the given position, or None.
        Resize handles are checked first; rotation corner zones are checked after."""
        if hasattr(pos, 'x'):
            pos_f = QtCore.QPointF(pos.x(), pos.y()) if not isinstance(pos, QtCore.QPointF) else pos
        else:
            pos_f = QtCore.QPointF(pos)

        # Check resize handles first (they take priority over rotation zones)
        for handle_name in self.handles:
            handle_rect = self.get_handle_rect(handle_name)
            expanded_rect = handle_rect.adjusted(-2, -2, 2, 2)
            if expanded_rect.contains(pos_f):
                return handle_name

        # Check rotation corner zones (outside the corner handles)
        for corner, zone_rect in self.get_rotation_corner_rects().items():
            if zone_rect.contains(pos_f):
                return f'rotation_{corner}'

        return None

    def _make_rotation_cursor(self, angle_deg):
        """Create a rotation cursor from the rotate_icon.png, rotated per corner.
        Cached per angle to avoid re-creating every hover frame."""
        if not hasattr(self, '_rotation_cursor_cache'):
            self._rotation_cursor_cache = {}
        if angle_deg in self._rotation_cursor_cache:
            return self._rotation_cursor_cache[angle_deg]

        size = 24
        # Load the icon and scale it
        icon_pixmap = UT.get_icon("rotate_icon.png")
        if icon_pixmap.isNull():
            # Fallback to a standard cursor if icon not found
            self._rotation_cursor_cache[angle_deg] = QtCore.Qt.CrossCursor
            return QtCore.Qt.CrossCursor

        scaled = icon_pixmap.scaled(size, size, QtCore.Qt.KeepAspectRatio, QtCore.Qt.SmoothTransformation)

        # Rotate the icon to match the corner angle
        if abs(angle_deg) > 0.01:
            transform = QtGui.QTransform()
            transform.rotate(angle_deg)
            scaled = scaled.transformed(transform, QtCore.Qt.SmoothTransformation)

        cursor = QtGui.QCursor(scaled, scaled.width() // 2, scaled.height() // 2)
        self._rotation_cursor_cache[angle_deg] = cursor
        return cursor

    def get_cursor_for_handle(self, handle_name):
        """Get the appropriate cursor for a handle"""
        if handle_name.startswith('rotation'):
            # Map each corner to a rotation angle so the curved arrow
            # points in the natural drag direction for that corner
            corner_angles = {
                'rotation_top_left': 180,
                'rotation_top_right': 270,
                'rotation_bottom_right': 0,
                'rotation_bottom_left': 90,
            }
            angle = corner_angles.get(handle_name, 0)
            return self._make_rotation_cursor(angle)
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

        # CRITICAL FIX: Use global mouse position to avoid widget position drift issues.
        # The widget moves during left/top scaling, so we can't rely on widget-local coords.
        # Instead, get the global mouse position and convert to canvas coords.
        global_mouse_pos = self.mapToGlobal(mouse_pos_f.toPoint())
        canvas_mouse_pos = self.canvas.mapFromGlobal(global_mouse_pos)
        current_canvas_pos = QtCore.QPointF(canvas_mouse_pos)

        # Convert current position to scene coordinates
        current_scene_pos = self.canvas.canvas_to_scene_coords(current_canvas_pos)

        # Use the stored initial scene position (captured at mouse press)
        initial_scene_pos = self.initial_mouse_scene_pos

        # Calculate the movement delta in scene coordinates
        delta = current_scene_pos - initial_scene_pos

        # When guides are rotated, project delta into the guide frame
        if self.guide_rotation != 0:
            rad = math.radians(-self.guide_rotation)
            cos_r, sin_r = math.cos(rad), math.sin(rad)
            dx = delta.x() * cos_r - delta.y() * sin_r
            dy = delta.x() * sin_r + delta.y() * cos_r
            delta = QtCore.QPointF(dx, dy)

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

    def perform_rotation_transform(self, mouse_pos):
        """Rotate selected buttons as a group around the bounding box center.
        Each button's rotation AND position are updated so multiple buttons
        orbit together."""
        if not self.selected_buttons:
            return

        # Get global mouse position -> canvas coords for angle calculation
        mouse_pos_f = QtCore.QPointF(mouse_pos) if not isinstance(mouse_pos, QtCore.QPointF) else mouse_pos
        global_mouse_pos = self.mapToGlobal(mouse_pos_f.toPoint())
        canvas_mouse_pos = self.canvas.mapFromGlobal(global_mouse_pos)

        # Bounding box center in canvas coords (use stored pivot for stability)
        bbox_center = self.canvas.scene_to_canvas_coords(self.rotation_pivot_scene)

        dx = canvas_mouse_pos.x() - bbox_center.x()
        dy = canvas_mouse_pos.y() - bbox_center.y()
        current_angle = math.degrees(math.atan2(dy, dx))

        delta_angle = current_angle - self.rotation_initial_angle

        # Snap to 15-degree increments with Shift
        if QtWidgets.QApplication.keyboardModifiers() & QtCore.Qt.ShiftModifier:
            delta_angle = round(delta_angle / 15) * 15

        # Precompute orbit rotation (for orbiting positions around pivot)
        rad = math.radians(delta_angle)
        cos_d, sin_d = math.cos(rad), math.sin(rad)
        pivot = self.rotation_pivot_scene

        for button in self.selected_buttons:
            if button not in self.original_states:
                continue
            orig = self.original_states[button]

            # Rotate the button's own angle
            button.rotation = (orig['rotation'] + delta_angle) % 360

            # Orbit the button's position around the group pivot
            orig_pos = orig['position']
            rel_x = orig_pos.x() - pivot.x()
            rel_y = orig_pos.y() - pivot.y()
            new_x = pivot.x() + rel_x * cos_d - rel_y * sin_d
            new_y = pivot.y() + rel_x * sin_d + rel_y * cos_d
            button.scene_position = QtCore.QPointF(new_x, new_y)

        # Update canvas
        self.canvas.update_button_positions()
        self.calculate_bounding_rect()
        self.update_position()
        self.update_edit_widgets_during_transform()
        self.transform_updated.emit()

    def _scene_to_guide_frame(self, pt):
        """Transform a scene-space point into the guide's rotated coordinate frame."""
        if self.guide_rotation == 0:
            return pt
        rad = math.radians(-self.guide_rotation)
        cos_r, sin_r = math.cos(rad), math.sin(rad)
        return QtCore.QPointF(pt.x() * cos_r - pt.y() * sin_r,
                              pt.x() * sin_r + pt.y() * cos_r)

    def _guide_frame_to_scene(self, pt):
        """Transform a guide-frame point back to scene space."""
        if self.guide_rotation == 0:
            return pt
        rad = math.radians(self.guide_rotation)
        cos_r, sin_r = math.cos(rad), math.sin(rad)
        return QtCore.QPointF(pt.x() * cos_r - pt.y() * sin_r,
                              pt.x() * sin_r + pt.y() * cos_r)

    def _get_original_bounding_rect(self):
        """Get the bounding rect calculated from original button states.
        When guide_rotation != 0, computes in the rotated guide frame."""
        if not self.original_states:
            return self.bounding_rect

        min_x = float('inf')
        min_y = float('inf')
        max_x = float('-inf')
        max_y = float('-inf')

        for button, original in self.original_states.items():
            pos = self._scene_to_guide_frame(original['position'])
            half_width = original['width'] / 2
            half_height = original['height'] / 2

            min_x = min(min_x, pos.x() - half_width)
            max_x = max(max_x, pos.x() + half_width)
            min_y = min(min_y, pos.y() - half_height)
            max_y = max(max_y, pos.y() + half_height)

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
        """Apply scaling to buttons using their original states to avoid accumulation.
        transform_origin is in the guide frame (which may be rotated)."""
        for button in self.selected_buttons:
            if button not in self.original_states:
                continue

            original = self.original_states[button]

            # Check if this is a pose mode button
            if button.mode == 'pose':
                new_width = original['width'] * scale_x
                new_height = new_width * 1.25  # Maintain pose mode ratio
            elif (button.mode == 'controller'
                  and button.controller_data.get('field_type') == 'omni'):
                # Omni controllers use a square pad — width drives height so
                # the pad stays square during scaling, just like pose buttons.
                new_width = original['width'] * scale_x
                show_label = button.controller_data.get('show_label', True)
                has_label = bool(button.label and button.label.strip() and show_label)
                new_height = new_width * type(button).omni_aspect_ratio(has_label)
            else:
                new_width = original['width'] * scale_x
                new_height = original['height'] * scale_y

            # Clamp to reasonable sizes
            button.width = round(max(5, min(new_width, 2000)), 1)
            button.height = round(max(5, min(new_height, 2000)), 1)

            # Calculate new position — work in guide frame, then convert back
            guide_pos = self._scene_to_guide_frame(original['position'])
            offset_from_origin = guide_pos - transform_origin

            new_offset = QtCore.QPointF(
                offset_from_origin.x() * scale_x,
                offset_from_origin.y() * scale_y
            )
            new_guide_pos = transform_origin + new_offset
            button.scene_position = self._guide_frame_to_scene(new_guide_pos)

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
        """Update edit widgets during transform for real-time feedback (~15fps throttle)"""
        # Throttle widget updates — numbers don't need 60fps refresh
        current_time = QtCore.QTime.currentTime().msecsSinceStartOfDay()
        last = getattr(self, '_last_widget_update_time', 0)
        if current_time - last < 66:  # ~15fps
            return
        self._last_widget_update_time = current_time

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
                if 'rotation_edit' in main_window.edit_widgets:
                    main_window.edit_widgets['rotation_edit'].setValue(round(reference_button.rotation))
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
            self.active_handle = handle

            # CRITICAL: Convert mouse position to SCENE coordinates immediately and store that.
            # This avoids issues with widget position changing during transform.
            widget_pos = QtCore.QPointF(self.pos())
            initial_canvas_pos = widget_pos + pos_f
            self.initial_mouse_scene_pos = self.canvas.canvas_to_scene_coords(initial_canvas_pos)

            # Also store widget-local for cursor updates (not used for transform calc)
            self.last_mouse_pos = pos_f
            self.initial_mouse_pos = pos_f

            # Defensive refresh: re-sync from canvas selection in case some code path
            # changed selection without emitting button_selection_changed. Without this,
            # store_original_states() below would iterate stale buttons and the
            # transform pivot would be wrong (causes rotated-duplicate jump bug).
            current_selection = self.canvas.get_selected_buttons()
            if current_selection != self.selected_buttons:
                self.selected_buttons = current_selection
                self.calculate_bounding_rect()

            # Calculate and store original states (this is crucial for stability)
            self.store_original_states()

            if handle.startswith('rotation'):
                self.transform_mode = 'rotate'
                # Defer pixmap regeneration during rotation only — button size
                # doesn't change so the cached pixmap can be reused safely.
                # Scale must regenerate live so text/icons render at the new
                # size each frame (matches Blender behavior).
                for btn in self.selected_buttons:
                    btn._transform_active = True
                # Store the group pivot in scene coords for orbiting positions
                self.rotation_pivot_scene = self._bbox_center_in_scene()
                # Store initial angle from bbox center to mouse
                bbox_center = self.canvas.scene_to_canvas_coords(self.rotation_pivot_scene)
                dx = initial_canvas_pos.x() - bbox_center.x()
                dy = initial_canvas_pos.y() - bbox_center.y()
                self.rotation_initial_angle = math.degrees(math.atan2(dy, dx))
            else:
                self.transform_mode = 'scale'
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
        elif self.is_transforming and self.transform_mode == 'rotate':
            self.perform_rotation_transform(pos_f)
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

            # Re-enable pixmap regeneration so buttons render at final size
            for btn in self.selected_buttons:
                btn._transform_active = False

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
        """Paint the transform guides and handles with image for corners"""
        if not self.selected_buttons or self.bounding_rect.isEmpty() or not self.isVisible():
            return

        painter = QtGui.QPainter(self)
        painter.setRenderHint(QtGui.QPainter.Antialiasing)
        painter.setRenderHint(QtGui.QPainter.SmoothPixmapTransform)

        # Corner handles that get special rendering
        corner_handles = {'top_left', 'top_right', 'bottom_left', 'bottom_right'}

        # Draw handles
        for handle_name in self.handles:
            handle_rect = self.get_handle_rect(handle_name)
            if not handle_rect.isEmpty():
                if handle_name in corner_handles:
                    # Draw corner handles with diagonal resize appearance
                    painter.setPen(QtGui.QPen(self.guide_color, 1))
                    painter.setBrush(QtGui.QBrush(self.handle_color))
                    painter.drawRect(handle_rect)
                else:
                    # Draw edge handles (center handles on edges)
                    painter.setPen(QtGui.QPen(self.guide_color, 1))
                    painter.setBrush(QtGui.QBrush(self.handle_color))
                    painter.drawRect(handle_rect)

        # Rotation corner zones are invisible — cursor change indicates rotation

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

        guides = self.parent_guides
        pen = QtGui.QPen(guides.guide_color)
        pen.setWidth(guides.guide_width)
        pen.setStyle(QtCore.Qt.DashLine)
        painter.setPen(pen)
        painter.setBrush(QtCore.Qt.NoBrush)

        if guides.guide_rotation != 0:
            # Draw rotated bounding box as a polygon through the 4 corners
            corners_scene = guides._rotated_corners_in_scene()
            points = []
            for sc in corners_scene:
                cp = guides.canvas.scene_to_canvas_coords(sc)
                points.append(QtCore.QPointF(cp.x() - self.x(), cp.y() - self.y()))
            polygon = QtGui.QPolygonF(points)
            painter.drawPolygon(polygon)
        else:
            top_left_canvas = guides.canvas.scene_to_canvas_coords(
                guides.bounding_rect.topLeft()
            )
            bottom_right_canvas = guides.canvas.scene_to_canvas_coords(
                guides.bounding_rect.bottomRight()
            )
            widget_rect = QtCore.QRectF(
                top_left_canvas.x() - self.x(),
                top_left_canvas.y() - self.y(),
                bottom_right_canvas.x() - top_left_canvas.x(),
                bottom_right_canvas.y() - top_left_canvas.y()
            )
            if widget_rect.width() < 2 or widget_rect.height() < 2:
                return
            painter.drawRect(widget_rect)

class TransformControlsWidget(QtWidgets.QWidget):
    """Widget for controlling button properties that appears above transform guides"""

    def __init__(self, canvas, parent=None):
        super().__init__(parent)
        self.canvas = canvas
        self.selected_buttons = []

        # Widget properties
        self.setFixedHeight(32)
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
        # Mode selector dropdown
        self.mode_selector_btn = QtWidgets.QPushButton()
        self.mode_selector_btn.setFixedSize(18, 18)
        self.mode_selector_btn.setStyleSheet("""
            QPushButton {
                background-color: rgba(60, 60, 60, 200);
                border: 1px solid rgba(100, 100, 100, 150);
                border-radius: 2px;
                padding: 0px;
            }
            QPushButton:hover {
                background-color: rgba(80, 80, 80, 220);
                border: 1px solid rgba(120, 120, 120, 180);
            }
            QPushButton:pressed {
                background-color: rgba(50, 50, 50, 250);
            }
        """)
        self.mode_selector_btn.clicked.connect(self.show_mode_menu)
        self.current_mode = 'select'  # Track current mode
        self.update_mode_display()
        #---------------------------------------------------------------------------------------------------------------------------------------
        self.color_palette_btn = CCP.ColorPicker(mode='palette')
        def handle_color_picker_change(qcolor):
            main_window = self.window()
            if hasattr(main_window, 'edit_controller'):
                main_window.edit_controller._queue_color_change(qcolor)
            elif hasattr(main_window, "change_color_for_selected_buttons"):
                main_window.change_color_for_selected_buttons(qcolor)

        self.color_palette_btn.colorChanged.connect(handle_color_picker_change)
        if hasattr(self.color_palette_btn, 'dragFinished'):
            self.color_palette_btn.dragFinished.connect(self._commit_overlay_to_database)
        #---------------------------------------------------------------------------------------------------------------------------------------
        # Radius widgets
        bh = 2000  # button height max
        self.top_left_radius = CLE.IntegerLineEdit(min_value=0, max_value=bh, increment=1, height=18, width=45, label="R")
        self.top_right_radius = CLE.IntegerLineEdit(min_value=0, max_value=bh, increment=1, height=18, width=32, label="╮")
        self.bottom_left_radius = CLE.IntegerLineEdit(min_value=0, max_value=bh, increment=1, height=18, width=32, label="╰")
        self.bottom_right_radius = CLE.IntegerLineEdit(min_value=0, max_value=bh, increment=1, height=18, width=32, label="╯")

        def handle_radius_change(tl):
            main_window = self.window()
            if hasattr(main_window, 'edit_controller'):
                ctrl = main_window.edit_controller
                ctrl.pending_widget_changes['radius'] = (tl, tl, tl, tl)
                ctrl.widget_update_timer.start(ctrl.widget_update_delay)
            elif hasattr(main_window, "set_radius_for_selected_buttons"):
                main_window.set_radius_for_selected_buttons(tl, tl, tl, tl)

        self.top_left_radius.valueChanged.connect(lambda tl: handle_radius_change(tl))
        if hasattr(self.top_left_radius, 'dragFinished'):
            self.top_left_radius.dragFinished.connect(self._commit_overlay_to_database)

        #---------------------------------------------------------------------------------------------------------------------------------------
        # Shape edit button - opens curve editor for selected button
        self.edit_shape_btn = QtWidgets.QPushButton("Edit Shape")
        self.edit_shape_btn.setFixedHeight(18)
        self.edit_shape_btn.setStyleSheet("""
            QPushButton {
                background-color: rgba(60, 60, 60, 200);
                border: 1px solid rgba(100, 100, 100, 150);
                border-radius: 2px;
                padding: 0px 6px;
                color: rgba(220, 220, 220, 255);
                font-size: 10px;
            }
            QPushButton:hover {
                background-color: rgba(80, 80, 80, 220);
                border: 1px solid rgba(120, 120, 120, 180);
            }
            QPushButton:pressed {
                background-color: rgba(50, 50, 50, 250);
            }
        """)
        self.edit_shape_btn.setToolTip("Edit Shape")
        self.edit_shape_btn.clicked.connect(self._on_edit_shape)
        self.edit_shape_btn.setVisible(False)

        frame_layout.addWidget(self.mode_selector_btn)
        frame_layout.addWidget(self.top_left_radius)
        #frame_layout.addWidget(self.top_right_radius)
        #frame_layout.addWidget(self.bottom_left_radius)
        #frame_layout.addWidget(self.bottom_right_radius)
        frame_layout.addWidget(self.color_palette_btn)
        frame_layout.addWidget(self.edit_shape_btn)

    def _on_edit_shape(self):
        """Launch curve editor for the selected button's existing shape."""
        if self.selected_buttons:
            self.canvas.start_curve_editing(self.selected_buttons[0])
    #---------------------------------------------------------------------------------------------------------------------------------------
    def update_mode_display(self):
        """Update the mode selector button to show current mode icon only"""
        mode_icons = {
            'select': 'select.png',
            'script': 'code.png',
            'pose': 'pose_01.png',
            'controller': 'preference_icon.png',
        }
        mode_names = {
            'select': 'Select Mode',
            'script': 'Script Mode',
            'pose': 'Pose Mode',
            'controller': 'Controller Mode',
        }
        icon_name = mode_icons.get(self.current_mode, 'select.png')
        icon_size = 12 if self.current_mode == 'controller' else 14
        icon = UT.get_icon(icon_name, size=icon_size)
        self.mode_selector_btn.setIcon(icon)
        self.mode_selector_btn.setIconSize(QtCore.QSize(14, 14))
        self.mode_selector_btn.setToolTip(mode_names.get(self.current_mode, 'Select Mode'))

    def show_mode_menu(self):
        """Show dropdown menu with all mode options"""
        menu = QtWidgets.QMenu(self)
        menu.setStyleSheet("""
            QMenu {
                background-color: rgba(40, 40, 40, 240);
                border: 1px solid rgba(80, 80, 80, 200);
                border-radius: 4px;
                padding: 4px;
            }
            QMenu::item {
                padding: 4px 20px 4px 8px;
                border-radius: 2px;
            }
            QMenu::item:selected {
                background-color: rgba(75, 148, 234, 180);
            }
            QMenu::icon {
                padding-left: 4px;
            }
        """)

        # Define modes with icons and names
        modes_info = [
            ('select', 'select.png', 'Select Mode'),
            ('script', 'code.png', 'Script Mode'),
            ('pose', 'pose_01.png', 'Pose Mode'),
            ('controller', 'preference_icon.png', 'Controller Mode'),
        ]

        for mode_id, icon_name, mode_name in modes_info:
            icon_size = 13 if mode_id == 'controller' else 16
            action = QtGui.QAction(QtGui.QIcon(UT.get_icon(icon_name, size=icon_size)), mode_name, self)
            action.setCheckable(True)
            action.setChecked(self.current_mode == mode_id)
            action.triggered.connect(lambda *_, m=mode_id: self.set_mode_from_menu(m))
            menu.addAction(action)

        # Show menu below the button
        button_pos = self.mode_selector_btn.mapToGlobal(self.mode_selector_btn.rect().bottomLeft())
        menu.exec_(button_pos)

    def set_mode_from_menu(self, mode):
        """Set mode from dropdown menu selection"""
        self.current_mode = mode

        # Update display
        self.update_mode_display()

        # Apply mode to all selected buttons
        if self.selected_buttons:
            for button in self.selected_buttons:
                if hasattr(button, 'set_mode'):
                    button.set_mode(self.current_mode)
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

        # Update mode selector with the mode from the reference button
        if reference_button and hasattr(reference_button, 'mode'):
            self.current_mode = reference_button.mode
            self.update_mode_display()

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

        # Edit Shape is available for all buttons (matches context menu behavior)
        self.edit_shape_btn.setVisible(bool(selected_buttons))

        # Force layout recalculation so sizeHint() reflects the newly
        # shown/hidden edit_shape_btn before update_position() reads it.
        self.layout().activate()

    def update_position(self):
        """Update position to appear above transform guides.
        Anchored to the scene-space bounding rect center (stable during rotation)
        rather than the axis-aligned envelope edges (which jitter)."""
        if not self.isVisible():
            return

        guides = self.canvas.transform_guides
        if not guides.isVisible():
            return

        # Convert the four scene-space corners to canvas coords for a stable top edge
        scene_corners = guides._rotated_corners_in_scene()
        canvas_corners = [self.canvas.scene_to_canvas_coords(sc) for sc in scene_corners]
        top_y = min(c.y() for c in canvas_corners)
        bottom_y = max(c.y() for c in canvas_corners)
        center_x = sum(c.x() for c in canvas_corners) / 4

        w = self.sizeHint().width()
        h = self.sizeHint().height()

        # Account for the guides padding (handles + rotation margin)
        padding = guides.handle_size // 2 + guides.rotation_corner_margin + 2
        gap = 5
        edge_margin = 6

        canvas_rect = self.canvas.rect()
        canvas_w = canvas_rect.width()
        canvas_h = canvas_rect.height()

        above_y = int(top_y - padding - h - gap)
        below_y = int(bottom_y + padding + gap)

        # Prefer above the selection; fall back to below; else pin inside the
        # visible canvas so the widget stays reachable when the selection
        # covers the viewport on both top and bottom.
        if above_y >= edge_margin:
            new_y = above_y
        elif below_y + h <= canvas_h - edge_margin:
            new_y = below_y
        else:
            new_y = edge_margin

        new_x = int(center_x - w / 2)
        new_x = max(edge_margin, min(new_x, canvas_w - w - edge_margin))

        self.setGeometry(new_x, new_y, w, h)
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
            if hasattr(self.color_palette_btn, 'dragFinished'):
                self.color_palette_btn.dragFinished.disconnect()
            self.top_left_radius.valueChanged.disconnect()
            if hasattr(self.top_left_radius, 'dragFinished'):
                self.top_left_radius.dragFinished.disconnect()
        except Exception:
            # If signals were already disconnected or never connected, ignore errors
            pass

    def _commit_overlay_to_database(self):
        """Commit queued visual changes to database (called on drag release)."""
        main_window = self.window()
        if hasattr(main_window, 'edit_controller'):
            main_window.edit_controller._commit_drag_to_database()

    def _reconnect_signals(self):
        """Reconnect signals after updating UI controls"""
        # Reconnect color picker signal
        def handle_color_picker_change(qcolor):
            main_window = self.window()
            if hasattr(main_window, 'edit_controller'):
                main_window.edit_controller._queue_color_change(qcolor)
            elif hasattr(main_window, "change_color_for_selected_buttons"):
                main_window.change_color_for_selected_buttons(qcolor.name())

        self.color_palette_btn.colorChanged.connect(handle_color_picker_change)
        if hasattr(self.color_palette_btn, 'dragFinished'):
            self.color_palette_btn.dragFinished.connect(self._commit_overlay_to_database)

        # Reconnect radius signals
        def handle_radius_change(tl):
            main_window = self.window()
            if hasattr(main_window, 'edit_controller'):
                ctrl = main_window.edit_controller
                ctrl.pending_widget_changes['radius'] = (tl, tl, tl, tl)
                ctrl.widget_update_timer.start(ctrl.widget_update_delay)
            elif hasattr(main_window, "set_radius_for_selected_buttons"):
                main_window.set_radius_for_selected_buttons(tl, tl, tl, tl)

        self.top_left_radius.valueChanged.connect(lambda tl: handle_radius_change(tl))
        if hasattr(self.top_left_radius, 'dragFinished'):
            self.top_left_radius.dragFinished.connect(self._commit_overlay_to_database)
