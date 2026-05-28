"""
Main curve editor overlay widget.

This widget provides the visual interface for curve editing:
- Transparent overlay on top of the canvas
- Renders paths, points, and handles
- Handles all mouse/keyboard input for editing
- Coordinates with CurveEditorControlsWidget for UI
"""

import math

try:
    from PySide6 import QtWidgets, QtCore, QtGui
    from PySide6.QtCore import Signal
except ImportError:
    from PySide2 import QtWidgets, QtCore, QtGui
    from PySide2.QtCore import Signal
from typing import Optional

from .curve_data import ButtonShape, CurvePath, CurvePoint, PointType
from .curve_tools import (
    EditorTool, CurveEditorState, NodeTool, PenTool, RectangleTool, EllipseTool
)
from .curve_controls import CurveEditorControlsWidget
from .curve_mirror import (
    MirrorAxis, MirrorMap,
    symmetrize_path, rebuild_mirror_side, rebuild_mirror_side_cross_path,
    compute_default_line_position, hit_test_symmetry_line,
    create_mirrored_path_copy, MirrorPointInfo, PointRole,
    classify_point, mirror_point_position,
)


class CurveEditorOverlay(QtWidgets.QWidget):
    """
    Transparent overlay widget for curve editing.
    
    This widget sits on top of the canvas and handles all curve editing
    interactions. It renders the editing UI (points, handles, paths) and
    processes input events.
    
    Signals:
        editingFinished(str): Emitted with SVG path data when editing completes
        editingCancelled(): Emitted when editing is cancelled
    """
    
    editingFinished = Signal(str)  # SVG path data
    editingCancelled = Signal()
    
    # ==================== Visual Constants ====================
    ANCHOR_SIZE = 8
    ANCHOR_SELECTED_SIZE = 10
    HANDLE_SIZE = 6
    
    # Colors
    PATH_COLOR = QtGui.QColor(75, 148, 234, 220)
    PATH_PREVIEW_COLOR = QtGui.QColor(75, 148, 234, 120)
    ANCHOR_COLOR = QtGui.QColor(255, 255, 255)
    ANCHOR_SELECTED_COLOR = QtGui.QColor(75, 148, 234)
    ANCHOR_HOVER_COLOR = QtGui.QColor(255, 200, 50)
    HANDLE_COLOR = QtGui.QColor(200, 200, 200)
    HANDLE_LINE_COLOR = QtGui.QColor(150, 150, 150, 180)
    CLOSE_INDICATOR_COLOR = QtGui.QColor(100, 255, 100, 200)
    PREVIEW_LINE_COLOR = QtGui.QColor(75, 148, 234, 100)
    SHAPE_PREVIEW_COLOR = QtGui.QColor(75, 148, 234, 60)
    
    # Shape fill during editing (semi-transparent to see through)
    SHAPE_EDIT_FILL_COLOR = QtGui.QColor(75, 148, 234, 40)
    SHAPE_EDIT_STROKE_COLOR = QtGui.QColor(75, 148, 234, 180)
    
    # Dimming for other buttons
    OTHER_BUTTON_OPACITY = 0.08

    # Full-canvas tint overlay drawn behind curve editor content
    CANVAS_TINT_COLOR = QtGui.QColor(0, 0, 0, 80)

    # Symmetry line
    SYMMETRY_LINE_COLOR = QtGui.QColor(255, 150, 50, 180)
    SYMMETRY_LINE_HOVER_COLOR = QtGui.QColor(255, 200, 100, 220)
    SYMMETRY_LINE_WIDTH = 2
    SYMMETRY_LINE_DASH = [8, 4]
    SYMMETRY_LINE_HIT_RADIUS = 8
    
    def __init__(self, canvas, parent=None):
        super().__init__(parent)
        self.canvas = canvas
        self.target_button = None  # The button being edited
        
        # Editor state and tools
        self.state = CurveEditorState()
        self.node_tool = NodeTool(self.state)
        self.pen_tool = PenTool(self.state)
        self.rect_tool = RectangleTool(self.state)
        self.ellipse_tool = EllipseTool(self.state)
        
        # Hover tracking
        self.hover_hit: Optional[object] = None
        
        # Canvas state preservation for restore after editing
        self._saved_zoom = None
        self._saved_pan = None
        self._did_auto_zoom = False
        self._is_new_shape = False
        
        # Button dimming/hiding state
        self._original_button_opacities = {}
        self._original_button_visibility = {}
        self._original_button_mouse_enabled = {}  # Track mouse event state
        
        # Box selection state
        self._box_selecting = False
        self._box_start = None
        self._box_current = None
        
        # Panning state
        self._panning = False
        self._pan_start = None

        # Symmetry line state
        self._dragging_symmetry_line = False
        self._symmetry_line_hovered = False

        # Pre-mirror shape backup for non-destructive toggle
        self._pre_mirror_shape = None

        # Hover-over-other-button state (for quick shape-edit switching)
        self._hovered_other_button = None

        # Widget setup
        self.setAttribute(QtCore.Qt.WA_TranslucentBackground)
        self.setMouseTracking(True)
        self.setFocusPolicy(QtCore.Qt.StrongFocus)
        
        # Controls widget
        self.controls = CurveEditorControlsWidget(parent)
        self.controls.toolChanged.connect(self._on_tool_changed)
        self.controls.pointTypeChanged.connect(self._on_point_type_changed_from_controls)
        self.controls.editingFinished.connect(self._finish_editing)
        self.controls.editingCancelled.connect(self._cancel_editing)
        self.controls.mirrorToggled.connect(self._on_mirror_toggled)
        self.controls.mirrorAxisChanged.connect(self._on_mirror_axis_changed)
        
        # Store original button state for undo
        self._original_button_state = None
        
        self.setVisible(False)
    
    # ==================== Helper Methods ====================
    
    def _is_button_deleted(self, button) -> bool:
        """Check if a button's C++ object has been deleted."""
        if not button:
            return True
        try:
            # Try to access a simple property - will raise RuntimeError if deleted
            _ = button.parent()
            return False
        except RuntimeError:
            return True
    
    def _get_other_button_at_pos(self, canvas_pos):
        """Hit-test canvas buttons (excluding the current target) at *canvas_pos*.

        Buttons are dimmed and have WA_TransparentForMouseEvents during curve
        editing, so normal Qt hit-testing won't work.  We replicate the
        scene-space logic from PickerCanvas._get_button_at_position here.
        """
        if not self.canvas:
            return None

        scene_pos = self.canvas.canvas_to_scene_coords(QtCore.QPointF(canvas_pos))

        for button in reversed(self.canvas.buttons):
            if button is self.target_button:
                continue
            # Check original visibility (button is currently dimmed, not hidden)
            if button in self._original_button_visibility:
                if not self._original_button_visibility[button]:
                    continue
            elif not button.isVisible():
                continue

            if button._canvas_painted:
                env_w, env_h = button.rotated_envelope_size()
                bp = button.scene_position
                if (abs(scene_pos.x() - bp.x()) > env_w / 2 or
                        abs(scene_pos.y() - bp.y()) > env_h / 2):
                    continue
                if button.hit_test_scene(scene_pos):
                    return button
            else:
                # Legacy widget-based – approximate with scene rect
                w, h = button.width, button.height
                bp = button.scene_position
                half_w, half_h = w / 2, h / 2
                if (bp.x() - half_w <= scene_pos.x() <= bp.x() + half_w and
                        bp.y() - half_h <= scene_pos.y() <= bp.y() + half_h):
                    return button
        return None

    def _switch_to_button(self, button):
        """Finish current editing and immediately start editing *button*'s shape.

        Applies changes from the current session inline (without emitting
        editingFinished) so that transform guides never flash on/off between
        the two editing sessions.
        """
        if not button or not self.canvas:
            return

        # --- Apply current shape to old button (inline, no signal) ----------
        if self.state.current_shape and self.target_button:
            if not self._is_button_deleted(self.target_button):
                old_btn = self.target_button
                if self._is_new_shape:
                    self._fit_button_to_shape()
                else:
                    self._convert_shape_to_button_local()

                svg_data = self.state.current_shape.to_svg_path_data()
                if svg_data:
                    old_btn.shape_type = 'custom_path'
                    old_btn.svg_path_data = svg_data

                # Restore opacities before saving
                self._restore_button_opacities()
                self.canvas.update_button_positions()
                old_btn.update()
                self.canvas.update_button_data(old_btn)

        # --- Clean up state without hiding/showing guides -----------------
        self._cleanup()

        # --- Start editing the new button ---------------------------------
        self.canvas.start_curve_editing(button)

    # ==================== Public Interface ====================

    def start_editing(self, button, existing_shape: ButtonShape = None):
        """
        Start editing a button's shape.
        
        Args:
            button: The PickerButton to edit
            existing_shape: Optional existing ButtonShape to edit
        """
        self.target_button = button
        
        # Save original button state for undo
        self._original_button_state = {
            'shape_type': button.shape_type,
            'svg_path_data': button.svg_path_data,
            'svg_file_path': button.svg_file_path,
            'width': button.width,
            'height': button.height,
            'scene_position': (button.scene_position.x(), button.scene_position.y()),
            'opacity': button.opacity
        }
        
        # Initialize or load shape
        if existing_shape:
            self.state.current_shape = existing_shape.copy()
        elif button.shape_type == 'custom_path' and button.svg_path_data:
            self.state.current_shape = ButtonShape.from_svg_path_data(button.svg_path_data)
            # Normalize shape to button dimensions (0,0 to width,height)
            # SVG data from external imports may be in arbitrary coordinate space
            self._normalize_shape_to_button()
        else:
            # Create default shape from button dimensions
            self.state.current_shape = self._create_default_rect_shape()
        
        # Track whether this is a new shape (no existing paths)
        self._is_new_shape = (existing_shape is not None and len(existing_shape.paths) == 0)
        
        # Convert shape to scene coordinates for editing
        # For NEW shapes: Already in scene coords (will be drawn there)
        # For EXISTING shapes: Convert from button-local (0,0 to w,h) to scene coords
        if not self._is_new_shape:
            self._convert_shape_to_scene_coords()
        
        # Store original for cancel
        self.state.store_original_shape()
        
        # Reset state
        self.state.clear_selection()
        # Clear undo history for new editing session
        self.state.clear_undo_history()
        # Default to Pen tool for new/empty shapes, Node tool for editing existing
        if existing_shape and len(existing_shape.paths) == 0:
            self.state.active_tool = EditorTool.PEN
        else:
            self.state.active_tool = EditorTool.NODE
        self.pen_tool._reset_drawing_state()
        
        # No auto-zoom - editing should be 1:1 scale with the canvas
        # This ensures what you see while editing is exactly what you get
        
        # Hide/dim other buttons to focus on editing
        self._dim_other_buttons()
        
        # Position and show widgets
        self._update_geometry()
        self.setVisible(True)
        self.controls.setVisible(True)
        self.controls.set_tool(self.state.active_tool)
        self._update_controls_position()
        
        # CRITICAL: Raise overlay above all buttons to ensure mouse events reach handles/points
        # This must happen AFTER buttons are dimmed/disabled
        self.raise_()
        self.controls.raise_()
        
        self.setFocus()
        
        # Force immediate update to ensure shape is drawn correctly
        self.update()
        if self.canvas:
            self.canvas.update()
    
    def is_editing(self) -> bool:
        """Check if currently editing a button."""
        return self.isVisible() and self.target_button is not None and not self._is_button_deleted(self.target_button)
    
    def get_current_svg_data(self) -> str:
        """Get current shape as SVG path data."""
        if self.state.current_shape:
            return self.state.current_shape.to_svg_path_data()
        return ""
    
    # ==================== Internal Methods ====================
    
    def _create_default_rect_shape(self) -> ButtonShape:
        """Create a default rectangular shape based on button size."""
        if not self.target_button:
            return ButtonShape()
        
        shape = ButtonShape()
        path = CurvePath()
        
        w = self.target_button.width
        h = self.target_button.height
        
        # Simple rectangle with 4 corners
        corners = [
            QtCore.QPointF(0, 0),
            QtCore.QPointF(w, 0),
            QtCore.QPointF(w, h),
            QtCore.QPointF(0, h),
        ]
        
        for corner in corners:
            path.add_point(CurvePoint(position=corner, point_type=PointType.CORNER))
        
        path.close_path()
        shape.add_path(path)
        
        return shape

    def _normalize_shape_to_button(self):
        """
        Normalize a parsed shape so its points fit within (0,0) to (width, height).

        SVG data from external imports (SVG files, Blender curves) may use
        arbitrary coordinate spaces.  The button renderer (_create_svg_path)
        scales the QPainterPath at draw time, but the curve editor expects
        points already in button-local coords.  This method replicates that
        scaling on the raw CurvePoint data so editing works correctly.
        """
        shape = self.state.current_shape
        if not shape or not shape.paths or not self.target_button:
            return

        # Compute bounding rect of all points (including handle positions)
        bounds = shape.get_rendered_bounding_rect()
        if not bounds or bounds.width() <= 0 or bounds.height() <= 0:
            bounds = shape.get_bounding_rect()
        if not bounds or bounds.width() <= 0 or bounds.height() <= 0:
            return

        btn_w = self.target_button.width
        btn_h = self.target_button.height
        if btn_w <= 0 or btn_h <= 0:
            return

        # Check if shape is already in button-local range (0..width, 0..height)
        # Allow a small tolerance for floating-point drift
        tol = max(btn_w, btn_h) * 0.05
        already_local = (
            bounds.left() >= -tol and
            bounds.top() >= -tol and
            bounds.right() <= btn_w + tol and
            bounds.bottom() <= btn_h + tol and
            bounds.width() > 0.5 and
            bounds.height() > 0.5
        )
        if already_local:
            return

        # Scale uniformly to fit button dimensions (same as picker_button._create_svg_path)
        scale_x = btn_w / bounds.width()
        scale_y = btn_h / bounds.height()
        scale = min(scale_x, scale_y)

        # Center within button rect
        scaled_w = bounds.width() * scale
        scaled_h = bounds.height() * scale
        offset_x = (btn_w - scaled_w) / 2 - bounds.left() * scale
        offset_y = (btn_h - scaled_h) / 2 - bounds.top() * scale

        for path in shape.paths:
            for point in path.points:
                # Transform position
                point.position = QtCore.QPointF(
                    point.position.x() * scale + offset_x,
                    point.position.y() * scale + offset_y
                )
                # Scale handle vectors (relative offsets)
                if point.handle_in is not None:
                    point.handle_in = QtCore.QPointF(
                        point.handle_in.x() * scale,
                        point.handle_in.y() * scale
                    )
                if point.handle_out is not None:
                    point.handle_out = QtCore.QPointF(
                        point.handle_out.x() * scale,
                        point.handle_out.y() * scale
                    )

    def _update_geometry(self):
        """Update overlay geometry to cover the canvas."""
        if self.canvas:
            self.setGeometry(self.canvas.rect())
    
    def _update_controls_position(self):
        """Update the controls widget position."""
        if not self.controls.isVisible():
            return

        # Position controls vertically centered on the left side of the canvas
        canvas_height = self.canvas.height() if self.canvas else self.height()
        self.controls.position_at_left(canvas_height)
    
    def _get_button_canvas_rect(self) -> QtCore.QRectF:
        """Get the button rectangle in canvas coordinates."""
        if not self.target_button or not self.canvas:
            return QtCore.QRectF()
        
        # Convert button position to canvas coordinates
        pos = self.canvas.scene_to_canvas_coords(self.target_button.scene_position)
        zoom = self.canvas.zoom_factor
        
        # Use the button's full dimensions
        w = self.target_button.width * zoom
        h = self.target_button.height * zoom
        
        return QtCore.QRectF(
            pos.x() - w / 2,
            pos.y() - h / 2,
            w, h
        )
    
    def _get_scale(self) -> float:
        """Get current scale factor (zoom)."""
        if self.canvas:
            return self.canvas.zoom_factor
        return 1.0
    
    def _canvas_to_shape_coords(self, canvas_pos: QtCore.QPointF) -> QtCore.QPointF:
        """
        Convert canvas coordinates to shape coordinates.
        During editing, ALL shapes use scene coordinates for consistency.
        """
        if self.canvas:
            return self.canvas.canvas_to_scene_coords(canvas_pos)
        return canvas_pos
    
    def _shape_to_canvas_coords(self, shape_pos: QtCore.QPointF) -> QtCore.QPointF:
        """
        Convert shape coordinates to canvas coordinates.
        During editing, ALL shapes use scene coordinates.
        """
        if self.canvas:
            return self.canvas.scene_to_canvas_coords(shape_pos)
        return shape_pos
    
    @staticmethod
    def _rotate_point(point: QtCore.QPointF, center: QtCore.QPointF, angle_degrees: float) -> QtCore.QPointF:
        """Rotate a point around a center by angle_degrees."""
        if abs(angle_degrees) < 0.001:
            return QtCore.QPointF(point)
        rad = math.radians(angle_degrees)
        cos_a = math.cos(rad)
        sin_a = math.sin(rad)
        dx = point.x() - center.x()
        dy = point.y() - center.y()
        return QtCore.QPointF(
            center.x() + dx * cos_a - dy * sin_a,
            center.y() + dx * sin_a + dy * cos_a
        )

    @staticmethod
    def _rotate_vector(vec: QtCore.QPointF, angle_degrees: float) -> QtCore.QPointF:
        """Rotate a relative offset vector by angle_degrees."""
        if vec is None or abs(angle_degrees) < 0.001:
            return vec
        rad = math.radians(angle_degrees)
        cos_a = math.cos(rad)
        sin_a = math.sin(rad)
        return QtCore.QPointF(
            vec.x() * cos_a - vec.y() * sin_a,
            vec.x() * sin_a + vec.y() * cos_a
        )

    def _convert_shape_to_scene_coords(self):
        """
        Convert shape from button-local coordinates to scene coordinates.
        Called when starting to edit an existing button.
        Accounts for button rotation.
        """
        if not self.state.current_shape or not self.target_button:
            return

        # Calculate button's top-left corner in scene coordinates
        button_scene_center = self.target_button.scene_position
        half_width = self.target_button.width / 2
        half_height = self.target_button.height / 2
        rotation = getattr(self.target_button, 'rotation', 0) or 0

        button_scene_topleft = QtCore.QPointF(
            button_scene_center.x() - half_width,
            button_scene_center.y() - half_height
        )

        # Transform all points from button-local to scene coordinates
        for path in self.state.current_shape.paths:
            for point in path.points:
                # Point is in button-local coords (0,0 to width,height)
                # First translate to scene coords (unrotated)
                point.position = QtCore.QPointF(
                    button_scene_topleft.x() + point.position.x(),
                    button_scene_topleft.y() + point.position.y()
                )
                # Then rotate around button center by button's rotation
                if abs(rotation) > 0.001:
                    point.position = self._rotate_point(point.position, button_scene_center, rotation)
                    # Rotate handle vectors (relative offsets) around origin
                    if point.handle_in is not None:
                        point.handle_in = self._rotate_vector(point.handle_in, rotation)
                    if point.handle_out is not None:
                        point.handle_out = self._rotate_vector(point.handle_out, rotation)

    def _convert_shape_to_button_local(self):
        """
        Convert shape from scene coordinates to button-local coordinates.
        Called before finishing edit of an existing button.

        Accounts for button rotation by un-rotating points first.
        Uses get_rendered_bounding_rect() for pixel-perfect consistency
        between the curve editor view and the final button rendering.
        """
        if not self.state.current_shape or not self.target_button:
            return

        # Check if button has been deleted (e.g., by undo/redo)
        if self._is_button_deleted(self.target_button):
            return

        rotation = getattr(self.target_button, 'rotation', 0) or 0

        # Un-rotate points around the shape's center before computing bounds
        if abs(rotation) > 0.001:
            # Use the current rendered center as the rotation pivot
            tmp_bounds = self.state.current_shape.get_rendered_bounding_rect()
            if not tmp_bounds or tmp_bounds.width() <= 0 or tmp_bounds.height() <= 0:
                tmp_bounds = self.state.current_shape.get_bounding_rect()
            if tmp_bounds and tmp_bounds.width() > 0 and tmp_bounds.height() > 0:
                pivot = tmp_bounds.center()
                for path in self.state.current_shape.paths:
                    for point in path.points:
                        point.position = self._rotate_point(point.position, pivot, -rotation)
                        if point.handle_in is not None:
                            point.handle_in = self._rotate_vector(point.handle_in, -rotation)
                        if point.handle_out is not None:
                            point.handle_out = self._rotate_vector(point.handle_out, -rotation)

        # Use RENDERED bounds for pixel-perfect accuracy
        # This ensures the bounds match exactly what Qt will render
        bounds = self.state.current_shape.get_rendered_bounding_rect()
        if not bounds or bounds.width() <= 0 or bounds.height() <= 0:
            # Fallback to point-based bounds if rendered bounds fail
            bounds = self.state.current_shape.get_bounding_rect()
            if not bounds or bounds.width() <= 0 or bounds.height() <= 0:
                return

        # For existing buttons, update position and size based on edited shape
        self.target_button.scene_position = bounds.center()
        self.target_button.width = bounds.width()
        self.target_button.height = bounds.height()

        # Normalize to button-local coordinates (0,0 to width,height)
        self.state.current_shape.translate(-bounds.left(), -bounds.top())
    
    # ==================== Button Visibility Management ====================
    
    def _dim_other_buttons(self):
        """Dim all buttons except the one being edited for visual focus."""
        if not self.canvas:
            return
        
        self._original_button_opacities = {}
        self._original_button_visibility = {}
        self._original_button_mouse_enabled = {}  # Store mouse event state
        
        for button in self.canvas.buttons:
            # Store original state for ALL buttons
            self._original_button_opacities[button] = button.opacity
            self._original_button_visibility[button] = button.isVisible()
            self._original_button_mouse_enabled[button] = not button.testAttribute(QtCore.Qt.WA_TransparentForMouseEvents)
            
            if button == self.target_button:
                # HIDE the target button completely - we draw our own representation
                # Use both opacity AND visibility to ensure it doesn't block interaction
                button.opacity = 0.0
                button.setVisible(False)
            else:
                # Dim other buttons and disable their mouse events
                # This prevents them from intercepting clicks intended for the overlay
                button.opacity = button.opacity * self.OTHER_BUTTON_OPACITY
                button.setAttribute(QtCore.Qt.WA_TransparentForMouseEvents, True)
            button.update()
    
    def _restore_button_opacities(self):
        """Restore original button opacities, visibility, and mouse events after editing."""
        for button, original_opacity in self._original_button_opacities.items():
            # Check if button still exists and hasn't been deleted by C++
            try:
                if button and not self._is_button_deleted(button):
                    button.opacity = original_opacity
                    # Restore visibility
                    if button in self._original_button_visibility:
                        button.setVisible(self._original_button_visibility[button])
                    # Restore mouse event handling
                    if button in self._original_button_mouse_enabled:
                        was_enabled = self._original_button_mouse_enabled[button]
                        button.setAttribute(QtCore.Qt.WA_TransparentForMouseEvents, not was_enabled)
                    button.update()
            except RuntimeError:
                # Button was deleted, skip it
                pass
        
        self._original_button_opacities = {}
        self._original_button_visibility = {}
        self._original_button_mouse_enabled = {}

    # ==================== Signal Handlers ====================
    
    def _on_tool_changed(self, tool: EditorTool):
        """Handle tool change from controls."""
        self.state.active_tool = tool
        
        # Cancel any active drawing when switching tools
        if tool != EditorTool.PEN and self.pen_tool.has_active_path():
            self.pen_tool._finish_path()
        
        self.update()
    
    def _on_point_type_changed_from_controls(self, point_type: PointType):
        """Handle point type change from controls widget - pushes undo state."""
        if not self.state.current_shape or not self.state.has_selection():
            return
        
        # Determine action name based on point type
        if point_type == PointType.CORNER:
            action_name = "Convert to Corner"
        elif point_type == PointType.SMOOTH:
            action_name = "Convert to Smooth"
        else:
            action_name = "Convert to Symmetric"
        
        # Push undo state before making changes
        self.state.push_undo_state(action_name)
        
        # Apply the change
        self._on_point_type_changed(point_type)
    
    def _on_point_type_changed(self, point_type: PointType):
        """Handle point type change - apply to selected points."""
        if not self.state.current_shape or not self.state.has_selection():
            return
        
        for path_idx, point_idx in self.state.selected_points:
            if path_idx < len(self.state.current_shape.paths):
                path = self.state.current_shape.paths[path_idx]
                if point_idx < len(path.points):
                    point = path.points[point_idx]
                    
                    if point_type == PointType.CORNER:
                        point.convert_to_corner()
                    elif point_type == PointType.SMOOTH:
                        point.convert_to_smooth()
                    elif point_type == PointType.SYMMETRIC:
                        point.convert_to_symmetric()
        
        self.update()

    def _on_mirror_toggled(self, enabled: bool):
        """Handle mirror mode toggle."""
        self.state.push_undo_state("Enable Mirror" if enabled else "Disable Mirror")
        self.state.mirror_state.enabled = enabled
        if enabled:
            # Save the original shape before symmetrization for non-destructive workflow
            if self.state.current_shape:
                self._pre_mirror_shape = self.state.current_shape.copy()
            if self.state.current_shape and self.state.current_shape.paths:
                self.state.mirror_state.line_position = compute_default_line_position(
                    self.state.current_shape, self.state.mirror_state.axis
                )
            self._symmetrize_all_paths()
        else:
            # Restore pre-mirror shape for non-destructive workflow
            if self._pre_mirror_shape:
                self.state.current_shape = self._pre_mirror_shape.copy()
                self._pre_mirror_shape = None
            self.state.mirror_map.clear()
        self.update()

    def _on_mirror_axis_changed(self, axis):
        """Handle mirror axis change."""
        self.state.push_undo_state("Change Mirror Axis")
        self.state.mirror_state.axis = axis
        if self.state.current_shape and self.state.current_shape.paths:
            self.state.mirror_state.line_position = compute_default_line_position(
                self.state.current_shape, axis
            )
        self._symmetrize_all_paths()
        self.update()

    def _symmetrize_all_paths(self):
        """Rebuild all paths in the shape to be symmetric."""
        if not self.state.current_shape:
            return

        new_mirror_map = MirrorMap()
        new_paths = []

        for path_idx, path in enumerate(self.state.current_shape.paths):
            new_path, path_map = symmetrize_path(
                path, len(new_paths),
                self.state.mirror_state.axis,
                self.state.mirror_state.line_position,
                self.state.mirror_state.CENTER_SNAP_TOLERANCE
            )
            # Merge path_map entries with correct path index
            for key, info in path_map._map.items():
                new_mirror_map.set(len(new_paths), key[1], info)
                # Update partner keys to use correct path index
                if info.partner_key:
                    info.partner_key = (len(new_paths), info.partner_key[1])

            new_paths.append(new_path)

            # For open source-only paths, create mirrored copy
            if not path.is_closed:
                has_mirror_entries = any(
                    new_mirror_map.is_mirror(len(new_paths) - 1, i)
                    for i in range(len(new_path.points))
                )
                if not has_mirror_entries and len(new_path.points) > 0:
                    mirror_copy = create_mirrored_path_copy(
                        new_path,
                        self.state.mirror_state.axis,
                        self.state.mirror_state.line_position
                    )
                    mirror_path_idx = len(new_paths)
                    new_paths.append(mirror_copy)
                    # Set up cross-path pairings
                    src_path_idx = mirror_path_idx - 1
                    for i in range(len(new_path.points)):
                        mirror_pt_idx = len(mirror_copy.points) - 1 - i
                        new_mirror_map.set(
                            mirror_path_idx, mirror_pt_idx,
                            MirrorPointInfo(PointRole.MIRROR, partner_key=(src_path_idx, i))
                        )
                        src_info = new_mirror_map.get(src_path_idx, i)
                        if src_info:
                            src_info.partner_key = (mirror_path_idx, mirror_pt_idx)

        self.state.current_shape.paths = new_paths
        self.state.mirror_map = new_mirror_map
        self.state.clear_selection()

    def _rebuild_all_mirror_sides(self):
        """Update MIRROR points from SOURCE partners using the existing mirror map.

        Unlike ``_symmetrize_all_paths`` this does NOT reclassify or reorder
        points — it only moves MIRROR/CENTER points to match the current
        ``line_position``.  Used during symmetry-line dragging so the path
        structure stays stable.
        """
        if not self.state.current_shape:
            return
        ms = self.state.mirror_state
        for path_idx, path in enumerate(self.state.current_shape.paths):
            # Check for cross-path partners first (open-path mirrors)
            has_cross = any(
                (info.partner_key and info.partner_key[0] != path_idx)
                for key, info in self.state.mirror_map._map.items()
                if key[0] == path_idx
            )
            if has_cross:
                rebuild_mirror_side_cross_path(
                    self.state.current_shape, self.state.mirror_map,
                    path_idx, ms.axis, ms.line_position
                )
            else:
                rebuild_mirror_side(
                    path, self.state.mirror_map,
                    path_idx, ms.axis, ms.line_position
                )

    def _finish_editing(self):
        """Finish editing and apply changes to button."""
        if self.state.current_shape and self.target_button:
            # Check if button has been deleted (e.g., by undo/redo)
            if self._is_button_deleted(self.target_button):
                self._cancel_editing()
                return
            
            # Convert shape from scene coords to button-local and update button bounds
            if self._is_new_shape:
                self._fit_button_to_shape()
            else:
                self._convert_shape_to_button_local()
            
            # CRITICAL: Restore button opacities BEFORE emitting signal
            # This ensures the button has correct opacity when saved
            self._restore_button_opacities()
            
            # Get the shape's SVG data (now in button-local space 0,0 to width,height)
            svg_data = self.state.current_shape.to_svg_path_data()
            self.editingFinished.emit(svg_data)
        
        self._cleanup()
    
    def _fit_button_to_shape(self):
        """
        For newly drawn shapes, calculate the bounding box of the drawn shape
        and update the button's position and size to match.
        Also normalize the shape coordinates to start at (0,0).
        
        For new shapes, the coordinates are in SCENE space, so:
        - bounds.center() becomes the button's scene_position (buttons use center-based positioning)
        - bounds.size() becomes the button's width/height
        - Shape points are normalized to (0,0) to (width, height)
        
        Uses get_rendered_bounding_rect() for pixel-perfect consistency
        between the curve editor view and the final button rendering.
        """
        if not self.state.current_shape or not self.target_button:
            return
        
        # Check if button has been deleted (e.g., by undo/redo)
        if self._is_button_deleted(self.target_button):
            return
        
        # Use RENDERED bounds for pixel-perfect accuracy
        # This ensures the bounds match exactly what Qt will render
        bounds = self.state.current_shape.get_rendered_bounding_rect()
        if not bounds or bounds.width() <= 0 or bounds.height() <= 0:
            # Fallback to point-based bounds if rendered bounds fail
            bounds = self.state.current_shape.get_bounding_rect()
            if not bounds or bounds.width() <= 0 or bounds.height() <= 0:
                return
        
        # Set button position to shape's CENTER (buttons use center-based positioning)
        self.target_button.scene_position = bounds.center()
        
        # Set button size to match shape bounds
        self.target_button.width = bounds.width()
        self.target_button.height = bounds.height()
        
        # Normalize shape coordinates to start at (0, 0)
        # This converts from scene coords to button-local coords
        self.state.current_shape.translate(-bounds.left(), -bounds.top())
    
    def _cancel_editing(self):
        """Cancel editing without applying changes."""
        # CRITICAL: Restore button opacities BEFORE emitting signal
        self._restore_button_opacities()
        self.editingCancelled.emit()
        self._cleanup()
    
    def _cleanup(self):
        """Clean up after editing session."""
        # Restore button opacities and visibility (if not already done)
        # This is a safety measure in case restoration wasn't called earlier
        if self._original_button_opacities:
            self._restore_button_opacities()
        
        self.target_button = None
        self.state.current_shape = None
        self.state.original_shape = None
        self.state.clear_selection()
        self.state.clear_undo_history()
        self.state.mirror_state.enabled = False
        self.state.mirror_map.clear()
        self._pre_mirror_shape = None
        self.controls.set_mirror_enabled(False)
        self.pen_tool._reset_drawing_state()
        self.hover_hit = None
        self._hovered_other_button = None

        self.setVisible(False)
        self.controls.setVisible(False)
    
    # ==================== Painting ====================
    
    def paintEvent(self, event):
        """Paint the curve editor overlay."""
        painter = QtGui.QPainter(self)
        painter.setRenderHint(QtGui.QPainter.Antialiasing)

        # Full-canvas tint to dim everything underneath
        painter.fillRect(self.rect(), self.CANVAS_TINT_COLOR)

        scale = self._get_scale()

        # Draw the shape fill (semi-transparent) - Figma-style direct editing
        self._draw_shape_fill(painter)
        
        # Draw the shape paths
        if self.state.current_shape:
            for path in self.state.current_shape.paths:
                self._draw_path(painter, path, scale)
        
        # Draw pen tool preview
        if self.state.active_tool == EditorTool.PEN:
            preview_path = self.pen_tool.get_preview_path()
            if preview_path:
                self._draw_path(painter, preview_path, scale, is_preview=True)
            self._draw_pen_preview(painter, scale)
        
        # Draw rectangle/ellipse tool preview
        elif self.state.active_tool == EditorTool.RECTANGLE:
            rect = self.rect_tool.get_preview_rect()
            if rect:
                self._draw_rect_preview(painter, rect, scale)
        
        elif self.state.active_tool == EditorTool.ELLIPSE:
            rect = self.ellipse_tool.get_preview_rect()
            if rect:
                self._draw_ellipse_preview(painter, rect, scale)
        
        # Draw points and handles
        if self.state.current_shape:
            for path_idx, path in enumerate(self.state.current_shape.paths):
                for point_idx, point in enumerate(path.points):
                    is_selected = self.state.is_point_selected(path_idx, point_idx)
                    self._draw_point(painter, point, scale, is_selected, path_idx, point_idx)
        
        # Draw pen tool preview path points
        if self.state.active_tool == EditorTool.PEN:
            preview_path = self.pen_tool.get_preview_path()
            if preview_path:
                for point in preview_path.points:
                    self._draw_point(painter, point, scale, False, -1, -1, is_preview=True)
        
        # Draw segment hover indicator (add point on curve indicator)
        if self.state.active_tool == EditorTool.NODE:
            self._draw_segment_hover(painter, scale)
            self._draw_band_hover(painter, scale)
        
        # Draw symmetry line
        if self.state.mirror_state.enabled:
            self._draw_symmetry_line(painter)

        # Draw box selection rectangle
        if self._box_selecting and self._box_start and self._box_current:
            self._draw_selection_box(painter)

        # Draw hover highlight on other buttons for shape-edit switching
        if self._hovered_other_button is not None:
            self._draw_button_hover_highlight(painter, self._hovered_other_button)

    def _draw_selection_box(self, painter):
        """Draw the box selection rectangle."""
        x1 = min(self._box_start.x(), self._box_current.x())
        y1 = min(self._box_start.y(), self._box_current.y())
        x2 = max(self._box_start.x(), self._box_current.x())
        y2 = max(self._box_start.y(), self._box_current.y())
        
        rect = QtCore.QRectF(x1, y1, x2 - x1, y2 - y1)
        
        # Draw filled rectangle
        painter.setPen(QtGui.QPen(QtGui.QColor(75, 148, 234, 200), 1))
        painter.setBrush(QtGui.QColor(75, 148, 234, 40))
        painter.drawRect(rect)
    
    def _draw_button_hover_highlight(self, painter, button):
        """Draw a highlight outline following the button's actual shape."""
        if not self.canvas or self._is_button_deleted(button):
            return

        painter.save()

        # Get the button's scene-space path (centered at origin)
        w, h = button.width, button.height
        scene_path = button._get_scene_path(w, h)

        # Transform path from scene-space (origin = button center) to canvas pixels
        bp = button.scene_position
        center_canvas = self.canvas.scene_to_canvas_coords(bp)
        zoom = self.canvas.zoom_factor

        xform = QtGui.QTransform()
        xform.translate(center_canvas.x(), center_canvas.y())
        xform.scale(zoom, zoom)
        if button.rotation != 0:
            xform.rotate(button.rotation)
        canvas_path = xform.map(scene_path)

        # Dashed outline following the shape
        highlight_color = QtGui.QColor(255, 200, 50, 200)
        pen = QtGui.QPen(highlight_color, 1.5)
        pen.setDashPattern([6, 3])
        pen.setCosmetic(True)
        painter.setPen(pen)
        painter.setBrush(QtGui.QColor(255, 200, 50, 25))
        painter.drawPath(canvas_path)

        # Draw a small label above the shape (fixed width so it never crops)
        font = painter.font()
        font.setPixelSize(10)
        painter.setFont(font)
        painter.setPen(highlight_color)
        bounds = canvas_path.boundingRect()
        label_w = 80
        label_rect = QtCore.QRectF(
            bounds.center().x() - label_w / 2, bounds.top() - 14,
            label_w, 14
        )
        painter.drawText(label_rect, QtCore.Qt.AlignCenter, "Double-click")

        painter.restore()

    def _show_switch_context_menu(self, global_pos, button):
        """Show a context menu offering to switch shape editing to *button*."""
        menu = QtWidgets.QMenu(self)
        menu.setStyleSheet("""
            QMenu {
                background-color: #2b2b2b;
                color: #cccccc;
                border: 1px solid #555555;
                padding: 4px;
            }
            QMenu::item {
                padding: 4px 20px;
            }
            QMenu::item:selected {
                background-color: #4b90d9;
                color: #ffffff;
            }
        """)

        label = button.label if button.label else button.unique_id
        action = menu.addAction(f"Edit Shape: {label}")
        action.triggered.connect(lambda: self._switch_to_button(button))
        menu.exec_(global_pos)

    def _show_node_context_menu(self, global_pos):
        """Context menu for shape editing actions in the Node tool."""
        menu = QtWidgets.QMenu(self)
        menu.setStyleSheet("""
            QMenu {
                background-color: #2b2b2b;
                color: #cccccc;
                border: 1px solid #555555;
                padding: 4px;
            }
            QMenu::item {
                padding: 4px 20px;
            }
            QMenu::item:selected {
                background-color: #4b90d9;
                color: #ffffff;
            }
            QMenu::item:disabled {
                color: #666666;
            }
            QMenu::separator {
                height: 1px;
                background: #3a3a3a;
                margin: 4px 6px;
            }
        """)

        n_sel = len(self.state.selected_points)
        can_merge = n_sel >= 2

        merge_act = menu.addAction(f"Merge Points ({n_sel})" if can_merge else "Merge Points")
        merge_act.setEnabled(can_merge)
        merge_act.triggered.connect(self._action_merge_points)

        menu.addSeparator()

        corner_act = menu.addAction("Convert to Corner")
        corner_act.triggered.connect(lambda: self._action_convert_type(PointType.CORNER))
        smooth_act = menu.addAction("Convert to Smooth")
        smooth_act.triggered.connect(lambda: self._action_convert_type(PointType.SMOOTH))
        sym_act = menu.addAction("Convert to Symmetric")
        sym_act.triggered.connect(lambda: self._action_convert_type(PointType.SYMMETRIC))

        menu.addSeparator()

        del_act = menu.addAction("Delete Points")
        del_act.triggered.connect(self._action_delete_points)

        menu.exec_(global_pos)

    def _action_merge_points(self):
        if len(self.state.selected_points) < 2:
            return
        self.state.push_undo_state("Merge Points")
        if self.node_tool._merge_selected_points():
            if self.state.mirror_state.enabled:
                self._symmetrize_all_paths()
            self._update_controls_from_selection()
            self.update()

    def _action_convert_type(self, point_type: PointType):
        if not self.state.has_selection():
            return
        self.state.push_undo_state(f"Convert to {point_type.name.title()}")
        if self.node_tool._convert_selected_to_type(point_type):
            self._update_controls_from_selection()
            self.update()

    def _action_delete_points(self):
        if not self.state.has_selection():
            return
        self.state.push_undo_state("Delete Points")
        if self.node_tool._delete_selected_points():
            if self.state.mirror_state.enabled:
                self._symmetrize_all_paths()
            self._update_controls_from_selection()
            self.update()

    def _draw_symmetry_line(self, painter):
        """Draw the draggable symmetry line across the overlay."""
        ms = self.state.mirror_state
        if not ms.enabled:
            return

        color = self.SYMMETRY_LINE_HOVER_COLOR if (self._dragging_symmetry_line or self._symmetry_line_hovered) else self.SYMMETRY_LINE_COLOR

        pen = QtGui.QPen(color, self.SYMMETRY_LINE_WIDTH)
        pen.setDashPattern(self.SYMMETRY_LINE_DASH)
        pen.setCosmetic(True)
        painter.setPen(pen)

        if ms.axis == MirrorAxis.VERTICAL:
            canvas_pt = self._shape_to_canvas_coords(QtCore.QPointF(ms.line_position, 0))
            cx = canvas_pt.x()
            painter.drawLine(QtCore.QPointF(cx, 0), QtCore.QPointF(cx, self.height()))
            handle_pos = QtCore.QPointF(cx, self.height() / 2)
        else:
            canvas_pt = self._shape_to_canvas_coords(QtCore.QPointF(0, ms.line_position))
            cy = canvas_pt.y()
            painter.drawLine(QtCore.QPointF(0, cy), QtCore.QPointF(self.width(), cy))
            handle_pos = QtCore.QPointF(self.width() / 2, cy)

        # Draw drag handle indicator
        painter.setPen(QtGui.QPen(color, 1))
        painter.setBrush(color)
        painter.drawEllipse(handle_pos, 5, 5)

    def _draw_band_hover(self, painter, scale: float):
        """Preview for shift+hover near an anchor: dashed line from anchor to cursor
        with a ring at the cursor showing the handle that will be grabbed/created."""
        band = getattr(self.node_tool, 'band_hover', None)
        if not band or not self.state.current_shape:
            return
        path_idx = band['path_index']
        point_idx = band['point_index']
        if path_idx >= len(self.state.current_shape.paths):
            return
        path = self.state.current_shape.paths[path_idx]
        if point_idx >= len(path.points):
            return
        point = path.points[point_idx]

        side = band['side']
        cursor_shape = band['cursor_pos']

        # If the targeted handle already exists, show the preview at its current position
        # so the user knows they'll grab (not teleport) it. Otherwise preview at cursor.
        existing = point.handle_out if side == 'handle_out' else point.handle_in
        has_existing = existing is not None and point._vector_length(existing) > 0.0001
        target_shape = point.get_handle_out_absolute() if (side == 'handle_out' and has_existing) \
            else point.get_handle_in_absolute() if (side == 'handle_in' and has_existing) \
            else cursor_shape

        anchor_canvas = self._shape_to_canvas_coords(point.position)
        target_canvas = self._shape_to_canvas_coords(target_shape)

        color = QtGui.QColor(255, 180, 60, 230)

        # Dashed guide line from anchor to target
        pen = QtGui.QPen(color, 1.2)
        pen.setDashPattern([4, 3])
        pen.setCosmetic(True)
        painter.setPen(pen)
        painter.setBrush(QtCore.Qt.NoBrush)
        painter.drawLine(anchor_canvas, target_canvas)

        # Ring at target
        radius = 5
        ring_pen = QtGui.QPen(color, 1.5)
        ring_pen.setCosmetic(True)
        painter.setPen(ring_pen)
        painter.setBrush(QtGui.QColor(255, 180, 60, 90) if has_existing else QtCore.Qt.NoBrush)
        painter.drawEllipse(target_canvas, radius, radius)

    def _draw_segment_hover(self, painter, scale: float):
        """
        Draw a visual indicator when hovering over a curve segment.
        Shows a plus icon or circle to indicate where a point can be added.
        """
        segment_hover = self.node_tool.segment_hover
        if not segment_hover or not segment_hover.segment_point:
            return
        
        # Convert the segment point to canvas coordinates
        canvas_pos = self._shape_to_canvas_coords(segment_hover.segment_point)
        
        # Draw a circle with plus indicator
        radius = 6
        
        # Outer ring
        painter.setPen(QtGui.QPen(QtGui.QColor(255, 255, 255), 2))
        painter.setBrush(QtGui.QColor(75, 148, 234, 200))
        painter.drawEllipse(canvas_pos, radius, radius)
        
        # Plus sign inside
        plus_size = 3
        pen = QtGui.QPen(QtGui.QColor(255, 255, 255), 1.5)
        pen.setCapStyle(QtCore.Qt.RoundCap)
        painter.setPen(pen)
        painter.drawLine(
            QtCore.QPointF(canvas_pos.x() - plus_size, canvas_pos.y()),
            QtCore.QPointF(canvas_pos.x() + plus_size, canvas_pos.y())
        )
        painter.drawLine(
            QtCore.QPointF(canvas_pos.x(), canvas_pos.y() - plus_size),
            QtCore.QPointF(canvas_pos.x(), canvas_pos.y() + plus_size)
        )

    def _draw_shape_fill(self, painter):
        """
        Draw the shape with a semi-transparent fill for direct editing feel.
        This replaces the boundary box approach with a Figma-like experience
        where you edit the shape itself, not within a boundary.
        """
        if not self.state.current_shape or not self.state.current_shape.paths:
            return
        
        # Build combined path for all paths in the shape
        combined_path = QtGui.QPainterPath()
        
        for path in self.state.current_shape.paths:
            if not path.points:
                continue
            
            # Start subpath
            first_canvas = self._shape_to_canvas_coords(path.points[0].position)
            combined_path.moveTo(first_canvas)
            
            # Add segments
            for i in range(1, len(path.points)):
                prev = path.points[i - 1]
                curr = path.points[i]
                
                has_ctrl1 = prev.has_handle_out()
                has_ctrl2 = curr.has_handle_in()
                
                to_canvas = self._shape_to_canvas_coords(curr.position)
                
                if has_ctrl1 or has_ctrl2:
                    ctrl1 = self._shape_to_canvas_coords(
                        prev.get_handle_out_absolute() if has_ctrl1 else prev.position
                    )
                    ctrl2 = self._shape_to_canvas_coords(
                        curr.get_handle_in_absolute() if has_ctrl2 else curr.position
                    )
                    combined_path.cubicTo(ctrl1, ctrl2, to_canvas)
                else:
                    combined_path.lineTo(to_canvas)
            
            # Close if needed
            if path.is_closed and len(path.points) > 2:
                last = path.points[-1]
                first = path.points[0]
                
                has_ctrl1 = last.has_handle_out()
                has_ctrl2 = first.has_handle_in()
                
                to_canvas = self._shape_to_canvas_coords(first.position)
                
                if has_ctrl1 or has_ctrl2:
                    ctrl1 = self._shape_to_canvas_coords(
                        last.get_handle_out_absolute() if has_ctrl1 else last.position
                    )
                    ctrl2 = self._shape_to_canvas_coords(
                        first.get_handle_in_absolute() if has_ctrl2 else first.position
                    )
                    combined_path.cubicTo(ctrl1, ctrl2, to_canvas)
                else:
                    combined_path.lineTo(to_canvas)
                
                combined_path.closeSubpath()
        
        # Draw the filled shape with semi-transparent fill
        painter.setPen(QtCore.Qt.NoPen)
        painter.setBrush(self.SHAPE_EDIT_FILL_COLOR)
        painter.drawPath(combined_path)

    def _draw_path(self, painter, path: CurvePath, scale: float, is_preview: bool = False):
        """Draw a curve path."""
        if not path.points:
            return
        
        qpath = QtGui.QPainterPath()
        
        # Convert first point to canvas coords
        first_canvas = self._shape_to_canvas_coords(path.points[0].position)
        qpath.moveTo(first_canvas)
        
        # Draw segments
        for i in range(1, len(path.points)):
            prev = path.points[i - 1]
            curr = path.points[i]
            self._add_segment_to_qpath(qpath, prev, curr, scale)
        
        # Close path if needed
        if path.is_closed and len(path.points) > 2:
            self._add_segment_to_qpath(qpath, path.points[-1], path.points[0], scale)
            qpath.closeSubpath()
        
        # Draw the path
        pen = QtGui.QPen(self.PATH_PREVIEW_COLOR if is_preview else self.PATH_COLOR)
        pen.setWidth(2)
        pen.setCosmetic(True)
        painter.setPen(pen)
        painter.setBrush(QtCore.Qt.NoBrush)
        painter.drawPath(qpath)
    
    def _add_segment_to_qpath(self, qpath: QtGui.QPainterPath, 
                              from_point: CurvePoint, to_point: CurvePoint, scale: float):
        """Add a curve segment to a QPainterPath."""
        has_ctrl1 = from_point.has_handle_out()
        has_ctrl2 = to_point.has_handle_in()
        
        to_canvas = self._shape_to_canvas_coords(to_point.position)
        
        if has_ctrl1 or has_ctrl2:
            ctrl1 = self._shape_to_canvas_coords(
                from_point.get_handle_out_absolute() if has_ctrl1 else from_point.position
            )
            ctrl2 = self._shape_to_canvas_coords(
                to_point.get_handle_in_absolute() if has_ctrl2 else to_point.position
            )
            qpath.cubicTo(ctrl1, ctrl2, to_canvas)
        else:
            qpath.lineTo(to_canvas)
    
    def _draw_point(self, painter, point: CurvePoint, scale: float,
                    is_selected: bool, path_idx: int, point_idx: int, is_preview: bool = False):
        """Draw a point with its handles."""
        # Dim mirror points to distinguish auto-generated points
        is_mirror_pt = (self.state.mirror_state.enabled and path_idx >= 0 and point_idx >= 0
                        and self.state.mirror_map.is_mirror(path_idx, point_idx))
        if is_mirror_pt:
            painter.setOpacity(0.45)

        pos_canvas = self._shape_to_canvas_coords(point.position)

        # Draw handles for ALL points that have them (Figma-style)
        # This lets users see the curve structure at a glance
        if point.handle_in:
            h_in_canvas = self._shape_to_canvas_coords(point.get_handle_in_absolute())
            h_in_selected = is_selected or self.state.is_handle_selected(path_idx, point_idx, 'handle_in')
            self._draw_handle_line(painter, pos_canvas, h_in_canvas, h_in_selected)
            self._draw_handle(painter, h_in_canvas, h_in_selected)

        if point.handle_out:
            h_out_canvas = self._shape_to_canvas_coords(point.get_handle_out_absolute())
            h_out_selected = is_selected or self.state.is_handle_selected(path_idx, point_idx, 'handle_out')
            self._draw_handle_line(painter, pos_canvas, h_out_canvas, h_out_selected)
            self._draw_handle(painter, h_out_canvas, h_out_selected)

        # Draw anchor point
        self._draw_anchor(painter, pos_canvas, is_selected, point.point_type,
                         self._is_hover_point(path_idx, point_idx))

        if is_mirror_pt:
            painter.setOpacity(1.0)
    
    def _draw_anchor(self, painter, pos: QtCore.QPointF, is_selected: bool,
                     point_type: PointType, is_hovered: bool):
        """Draw an anchor point."""
        size = self.ANCHOR_SELECTED_SIZE if is_selected else self.ANCHOR_SIZE
        
        # Determine color
        if is_hovered:
            color = self.ANCHOR_HOVER_COLOR
        elif is_selected:
            color = self.ANCHOR_SELECTED_COLOR
        else:
            color = self.ANCHOR_COLOR
        
        painter.setPen(QtGui.QPen(QtCore.Qt.black, 1))
        painter.setBrush(color)
        
        if point_type == PointType.CORNER:
            # Square for corner points
            half = size / 2
            painter.drawRect(QtCore.QRectF(
                pos.x() - half, pos.y() - half,
                size, size
            ))
        else:
            # Circle for smooth/symmetric points
            painter.drawEllipse(pos, size / 2, size / 2)
    
    def _draw_handle(self, painter, pos: QtCore.QPointF, is_selected: bool = False):
        """Draw a bezier handle control point."""
        painter.setPen(QtGui.QPen(QtCore.Qt.black, 1))
        # Brighter/larger handles for selected points
        if is_selected:
            painter.setBrush(self.ANCHOR_SELECTED_COLOR)
            size = self.HANDLE_SIZE + 2
        else:
            painter.setBrush(self.HANDLE_COLOR)
            size = self.HANDLE_SIZE
        painter.drawEllipse(pos, size / 2, size / 2)
    
    def _draw_handle_line(self, painter, anchor: QtCore.QPointF, handle: QtCore.QPointF, is_selected: bool = False):
        """Draw line from anchor to handle."""
        if is_selected:
            pen = QtGui.QPen(QtGui.QColor(75, 148, 234, 220))
            pen.setWidth(2)
        else:
            pen = QtGui.QPen(self.HANDLE_LINE_COLOR)
            pen.setWidth(1)
        pen.setCosmetic(True)
        painter.setPen(pen)
        painter.drawLine(anchor, handle)
    
    def _draw_pen_preview(self, painter, scale: float):
        """Draw preview elements for pen tool."""
        if not self.pen_tool.has_active_path():
            return
        
        preview_path = self.pen_tool.get_preview_path()
        if not preview_path or not preview_path.points:
            return
        
        # Draw line from last point to cursor
        if self.state.preview_point:
            last_point = preview_path.points[-1]
            last_canvas = self._shape_to_canvas_coords(last_point.position)
            # Convert shape coords to canvas coords for drawing
            cursor_canvas = self._shape_to_canvas_coords(self.state.preview_point)
            
            pen = QtGui.QPen(self.PREVIEW_LINE_COLOR)
            pen.setWidth(1)
            pen.setStyle(QtCore.Qt.DashLine)
            pen.setCosmetic(True)
            painter.setPen(pen)
            painter.drawLine(last_canvas, cursor_canvas)
        
        # Draw close indicator if near start point
        if len(preview_path.points) > 2 and self.state.preview_point:
            first_point = preview_path.points[0]
            cursor_shape = self.state.preview_point  # Already in shape coords
            
            # Calculate distance in shape coordinates
            dist = ((cursor_shape.x() - first_point.position.x()) ** 2 + 
                   (cursor_shape.y() - first_point.position.y()) ** 2) ** 0.5
            
            # Adjust hit radius for scale
            hit_radius = self.pen_tool.HIT_RADIUS / scale if scale > 0 else self.pen_tool.HIT_RADIUS
            
            if dist < hit_radius:
                # Draw close indicator
                first_canvas = self._shape_to_canvas_coords(first_point.position)
                painter.setPen(QtGui.QPen(self.CLOSE_INDICATOR_COLOR, 2))
                painter.setBrush(QtCore.Qt.NoBrush)
                painter.drawEllipse(first_canvas, 12, 12)
    
    def _draw_rect_preview(self, painter, rect: QtCore.QRectF, scale: float):
        """Draw rectangle tool preview."""
        # Convert rect to canvas coords
        top_left = self._shape_to_canvas_coords(rect.topLeft())
        bottom_right = self._shape_to_canvas_coords(rect.bottomRight())
        canvas_rect = QtCore.QRectF(top_left, bottom_right)
        
        painter.setPen(QtGui.QPen(self.PATH_COLOR, 2))
        painter.setBrush(self.SHAPE_PREVIEW_COLOR)
        painter.drawRect(canvas_rect)
    
    def _draw_ellipse_preview(self, painter, rect: QtCore.QRectF, scale: float):
        """Draw ellipse tool preview."""
        top_left = self._shape_to_canvas_coords(rect.topLeft())
        bottom_right = self._shape_to_canvas_coords(rect.bottomRight())
        canvas_rect = QtCore.QRectF(top_left, bottom_right)
        
        painter.setPen(QtGui.QPen(self.PATH_COLOR, 2))
        painter.setBrush(self.SHAPE_PREVIEW_COLOR)
        painter.drawEllipse(canvas_rect)
    
    def _is_hover_point(self, path_idx: int, point_idx: int) -> bool:
        """Check if a point is being hovered."""
        if self.hover_hit and hasattr(self.hover_hit, 'path_index'):
            return (self.hover_hit.path_index == path_idx and 
                   self.hover_hit.point_index == point_idx and
                   self.hover_hit.element_type == 'anchor')
        return False
    
    # ==================== Event Handling ====================
    
    def mousePressEvent(self, event):
        """Handle mouse press events."""
        # Close any open flyout panels when clicking on the canvas
        self.controls._close_all_flyouts()

        canvas_pos = QtCore.QPointF(event.pos())
        modifiers = event.modifiers()
        
        # Check if Alt+Click is over a point or handle before allowing panning
        if event.button() == QtCore.Qt.LeftButton and modifiers & QtCore.Qt.AltModifier:
            shape_pos = self._canvas_to_shape_coords(canvas_pos)
            scale = self._get_scale()
            
            # Check if we're over a point or handle in Node tool
            if self.state.active_tool == EditorTool.NODE:
                hit = self.node_tool.hit_test(shape_pos, scale, include_segments=False)
                if hit.is_valid() and (hit.is_anchor() or hit.is_handle()):
                    # Push undo state before Alt+Click modification
                    self.state.push_undo_state("Modify Point")
                    # Alt+Click on a point or handle - let the tool handle it
                    handled = self.node_tool.on_mouse_press(shape_pos, modifiers, scale)
                    if handled:
                        self._update_controls_from_selection()
                        self.update()
                    return
            
            # Not over a point or handle - allow panning
            self._panning = True
            self._pan_start = canvas_pos
            self.setCursor(QtCore.Qt.ClosedHandCursor)
            return
        
        # Middle mouse for panning
        if event.button() == QtCore.Qt.MiddleButton:
            self._panning = True
            self._pan_start = canvas_pos
            self.setCursor(QtCore.Qt.ClosedHandCursor)
            return
        
        # Right-click: context menu — shape editing actions when in NODE tool
        # and either there's a selection or the click is on an anchor, else
        # offer to switch to another button's shape.
        if event.button() == QtCore.Qt.RightButton:
            shape_pos_rc = self._canvas_to_shape_coords(canvas_pos)
            scale_rc = self._get_scale()
            if self.state.active_tool == EditorTool.NODE and self.state.current_shape:
                hit = self.node_tool.hit_test(shape_pos_rc, scale_rc, include_segments=False)
                if hit.is_valid() and hit.is_anchor():
                    if not self.state.is_point_selected(hit.path_index, hit.point_index):
                        self.state.select_point(hit.path_index, hit.point_index, add_to_selection=False)
                        self._update_controls_from_selection()
                        self.update()
                if self.state.has_selection():
                    self._show_node_context_menu(event.globalPos())
                    return
            other = self._get_other_button_at_pos(canvas_pos)
            if other:
                self._show_switch_context_menu(event.globalPos(), other)
            return

        if event.button() != QtCore.Qt.LeftButton:
            return

        shape_pos = self._canvas_to_shape_coords(canvas_pos)
        scale = self._get_scale()

        # Check symmetry line drag before tool handling
        if self.state.mirror_state.enabled:
            line_hit_radius = self.SYMMETRY_LINE_HIT_RADIUS / scale if scale > 0 else self.SYMMETRY_LINE_HIT_RADIUS
            if hit_test_symmetry_line(shape_pos, self.state.mirror_state, line_hit_radius):
                self._dragging_symmetry_line = True
                ms = self.state.mirror_state
                if ms.axis == MirrorAxis.VERTICAL:
                    ms.drag_offset = shape_pos.x() - ms.line_position
                else:
                    ms.drag_offset = shape_pos.y() - ms.line_position
                self.state.push_undo_state("Move Symmetry Line")
                self.setCursor(
                    QtCore.Qt.SizeHorCursor if ms.axis == MirrorAxis.VERTICAL
                    else QtCore.Qt.SizeVerCursor
                )
                return

        handled = False
        tool = self.state.active_tool
        
        if tool == EditorTool.NODE:
            # Check what we're about to interact with to determine if we need undo state
            hit = self.node_tool.hit_test(shape_pos, scale, include_segments=True)
            will_modify = False
            action_name = "Edit"
            
            # Determine if this click will modify the shape
            if hit.is_valid():
                if hit.is_segment():
                    will_modify = True
                    action_name = "Add Point on Curve"
                elif hit.is_anchor() or hit.is_handle():
                    # Check for modifier-based conversions
                    ctrl = modifiers & QtCore.Qt.ControlModifier
                    shift = modifiers & QtCore.Qt.ShiftModifier
                    alt = modifiers & QtCore.Qt.AltModifier
                    
                    if hit.is_anchor() and (ctrl or shift or alt):
                        will_modify = True
                        if alt and not ctrl and not shift:
                            action_name = "Remove Handles"
                        elif ctrl and not shift and not alt:
                            action_name = "Convert to Corner"
                        elif shift and not ctrl and not alt:
                            action_name = "Convert to Smooth"
                        elif ctrl and shift:
                            action_name = "Align Handles"
                    elif hit.is_handle() and not alt:
                        # Handles can always be dragged (Shift adds to selection)
                        will_modify = True
                        action_name = "Move Handle"
                    elif hit.is_anchor() and not ctrl and not shift:
                        # Anchors drag without modifiers
                        will_modify = True
                        action_name = "Move Point"
            
            # Push undo state before modification
            if will_modify:
                self.state.push_undo_state(action_name)
            
            handled = self.node_tool.on_mouse_press(shape_pos, modifiers, scale)

            # After inserting a point on a segment, rebuild mirror map
            # Preserve drag state so click+drag works in one gesture
            if handled and hit.is_segment() and self.state.mirror_state.enabled:
                # Save position of inserted point before symmetrization
                inserted_pos = None
                was_dragging = self.state.dragging
                if self.state.drag_element:
                    de = self.state.drag_element
                    if de.path_index < len(self.state.current_shape.paths):
                        p = self.state.current_shape.paths[de.path_index]
                        if de.point_index < len(p.points):
                            ins_pt = p.points[de.point_index]

                            # If inserted on the MIRROR side, flip to SOURCE
                            # so it survives re-symmetrization (mirror copy
                            # is auto-generated at the original position)
                            ms = self.state.mirror_state
                            role = classify_point(
                                ins_pt, ms.axis, ms.line_position,
                                ms.CENTER_SNAP_TOLERANCE
                            )
                            if role == PointRole.MIRROR:
                                ins_pt.position = mirror_point_position(
                                    ins_pt.position, ms.axis, ms.line_position
                                )
                                # Negate perpendicular handle component
                                if ins_pt.handle_in is not None:
                                    if ms.axis == MirrorAxis.VERTICAL:
                                        ins_pt.handle_in.setX(-ins_pt.handle_in.x())
                                    else:
                                        ins_pt.handle_in.setY(-ins_pt.handle_in.y())
                                if ins_pt.handle_out is not None:
                                    if ms.axis == MirrorAxis.VERTICAL:
                                        ins_pt.handle_out.setX(-ins_pt.handle_out.x())
                                    else:
                                        ins_pt.handle_out.setY(-ins_pt.handle_out.y())

                            inserted_pos = QtCore.QPointF(ins_pt.position)

                self._symmetrize_all_paths()

                # Restore drag by finding the point at the same position
                if was_dragging and inserted_pos and self.state.current_shape:
                    best_key = None
                    best_dist = float('inf')
                    for pi, path in enumerate(self.state.current_shape.paths):
                        for pti, pt in enumerate(path.points):
                            dx = pt.position.x() - inserted_pos.x()
                            dy = pt.position.y() - inserted_pos.y()
                            d = (dx * dx + dy * dy) ** 0.5
                            if d < best_dist:
                                best_dist = d
                                best_key = (pi, pti)
                    if best_key and best_dist < 1.0:
                        from .curve_tools import HitResult as HR
                        self.state.select_point(best_key[0], best_key[1])
                        self.state.dragging = True
                        self.state.drag_start = QtCore.QPointF(shape_pos)
                        self.state.drag_element = HR(
                            path_index=best_key[0], point_index=best_key[1],
                            element_type='anchor', distance=0
                        )
                        self.node_tool._store_original_positions()

            # If nothing was hit, start box selection
            if not handled and not self.state.dragging:
                self._box_selecting = True
                self._box_start = canvas_pos
                self._box_current = canvas_pos
                # Clear selection unless shift is held
                if not (modifiers & QtCore.Qt.ShiftModifier):
                    self.state.clear_selection()
                handled = True
                
        elif tool == EditorTool.PEN:
            # Push undo state before adding a point
            self.state.push_undo_state("Add Point")
            handled = self.pen_tool.on_mouse_press(shape_pos, modifiers, scale)
            
        elif tool == EditorTool.RECTANGLE:
            # Undo state will be pushed after shape is completed
            handled = self.rect_tool.on_mouse_press(shape_pos, modifiers)
            
        elif tool == EditorTool.ELLIPSE:
            # Undo state will be pushed after shape is completed
            handled = self.ellipse_tool.on_mouse_press(shape_pos, modifiers)
        
        if handled:
            self._update_controls_from_selection()
            self.update()
    
    def mouseMoveEvent(self, event):
        """Handle mouse move events."""
        canvas_pos = QtCore.QPointF(event.pos())
        modifiers = event.modifiers()
        scale = self._get_scale()
        
        # Handle panning
        if self._panning and self._pan_start is not None:
            delta = canvas_pos - self._pan_start
            self._pan_start = canvas_pos
            if self.canvas:
                self.canvas.pan_offset += delta
                self.canvas.update()
                self.canvas.update_button_positions()
                self._update_geometry()
            self.update()
            return
        
        # Handle box selection
        if self._box_selecting:
            self._box_current = canvas_pos
            self.update()
            return
        
        # Handle symmetry line drag
        if self._dragging_symmetry_line:
            shape_pos = self._canvas_to_shape_coords(canvas_pos)
            ms = self.state.mirror_state
            if ms.axis == MirrorAxis.VERTICAL:
                ms.line_position = shape_pos.x() - ms.drag_offset
            else:
                ms.line_position = shape_pos.y() - ms.drag_offset
            # Rebuild mirror points from existing SOURCE/CENTER/MIRROR map
            # instead of re-classifying and destructively rebuilding the path.
            self._rebuild_all_mirror_sides()
            self.update()
            return

        shape_pos = self._canvas_to_shape_coords(canvas_pos)

        # Update symmetry line hover state
        if self.state.mirror_state.enabled and not self.state.dragging:
            scale = self._get_scale()
            line_hit_radius = self.SYMMETRY_LINE_HIT_RADIUS / scale if scale > 0 else self.SYMMETRY_LINE_HIT_RADIUS
            was_hovered = self._symmetry_line_hovered
            self._symmetry_line_hovered = hit_test_symmetry_line(shape_pos, self.state.mirror_state, line_hit_radius)
            if self._symmetry_line_hovered:
                ms = self.state.mirror_state
                self.setCursor(
                    QtCore.Qt.SizeHorCursor if ms.axis == MirrorAxis.VERTICAL
                    else QtCore.Qt.SizeVerCursor
                )
            elif was_hovered:
                self.setCursor(QtCore.Qt.ArrowCursor)

        # Store shape position for preview (in shape-local coordinates)
        self.state.preview_point = shape_pos

        # Update hover state for node tool
        if self.state.active_tool == EditorTool.NODE and not self.state.dragging:
            self.hover_hit = self.node_tool.hit_test(shape_pos, scale)
        else:
            self.hover_hit = None
        
        tool = self.state.active_tool
        
        if tool == EditorTool.NODE:
            self.node_tool.on_mouse_move(shape_pos, modifiers, scale)
        elif tool == EditorTool.PEN:
            self.pen_tool.on_mouse_move(shape_pos, modifiers)
        elif tool == EditorTool.RECTANGLE:
            self.rect_tool.on_mouse_move(shape_pos, modifiers)
        elif tool == EditorTool.ELLIPSE:
            self.ellipse_tool.on_mouse_move(shape_pos, modifiers)

        # Track hover over other buttons for quick shape-edit switching
        if not self.state.dragging and not self._panning and not self._box_selecting:
            self._hovered_other_button = self._get_other_button_at_pos(canvas_pos)
        else:
            self._hovered_other_button = None

        self.update()

    def mouseReleaseEvent(self, event):
        """Handle mouse release events."""
        canvas_pos = QtCore.QPointF(event.pos())
        modifiers = event.modifiers()
        
        # Handle panning release
        if event.button() == QtCore.Qt.MiddleButton or \
           (event.button() == QtCore.Qt.LeftButton and self._panning):
            self._panning = False
            self._pan_start = None
            self.setCursor(QtCore.Qt.ArrowCursor)
            return
        
        # Handle symmetry line release
        if self._dragging_symmetry_line and event.button() == QtCore.Qt.LeftButton:
            self._dragging_symmetry_line = False
            self.setCursor(QtCore.Qt.ArrowCursor)
            self._rebuild_all_mirror_sides()
            self.update()
            return

        # Handle box selection release
        if self._box_selecting and event.button() == QtCore.Qt.LeftButton:
            self._finish_box_selection(modifiers)
            self._box_selecting = False
            self._box_start = None
            self._box_current = None
            self._update_controls_from_selection()
            self.update()
            return
        
        if event.button() != QtCore.Qt.LeftButton:
            return
        
        shape_pos = self._canvas_to_shape_coords(canvas_pos)
        
        tool = self.state.active_tool
        
        if tool == EditorTool.NODE:
            self.node_tool.on_mouse_release(shape_pos, modifiers)
        elif tool == EditorTool.PEN:
            self.pen_tool.on_mouse_release(shape_pos, modifiers)
        elif tool == EditorTool.RECTANGLE:
            # Push undo state before adding shape
            if self.rect_tool.current_rect and not self.rect_tool.current_rect.isEmpty():
                self.state.push_undo_state("Draw Rectangle")
            self.rect_tool.on_mouse_release(shape_pos, modifiers)
        elif tool == EditorTool.ELLIPSE:
            # Push undo state before adding shape
            if self.ellipse_tool.current_rect and not self.ellipse_tool.current_rect.isEmpty():
                self.state.push_undo_state("Draw Ellipse")
            self.ellipse_tool.on_mouse_release(shape_pos, modifiers)
        
        self._update_controls_from_selection()
        self.update()

    def mouseDoubleClickEvent(self, event):
        """Handle double-click — switch to editing another button's shape."""
        if event.button() == QtCore.Qt.LeftButton:
            canvas_pos = QtCore.QPointF(event.pos())
            other = self._get_other_button_at_pos(canvas_pos)
            if other:
                self._switch_to_button(other)
                return
        # Fall through to normal press handling for double-clicks on the shape itself
        self.mousePressEvent(event)

    def _finish_box_selection(self, modifiers):
        """Complete box selection by selecting all points within the box."""
        if not self._box_start or not self._box_current or not self.state.current_shape:
            return
        
        # Create selection rectangle in canvas coordinates
        x1 = min(self._box_start.x(), self._box_current.x())
        y1 = min(self._box_start.y(), self._box_current.y())
        x2 = max(self._box_start.x(), self._box_current.x())
        y2 = max(self._box_start.y(), self._box_current.y())
        
        selection_rect = QtCore.QRectF(x1, y1, x2 - x1, y2 - y1)
        
        # Find all points within the box
        add_to_selection = bool(modifiers & QtCore.Qt.ShiftModifier)
        
        for path_idx, path in enumerate(self.state.current_shape.paths):
            for point_idx, point in enumerate(path.points):
                # Convert point to canvas coordinates
                point_canvas = self._shape_to_canvas_coords(point.position)
                
                if selection_rect.contains(point_canvas):
                    if add_to_selection:
                        # Add to existing selection
                        if not self.state.is_point_selected(path_idx, point_idx):
                            self.state.select_point(path_idx, point_idx, True)
                    else:
                        self.state.select_point(path_idx, point_idx, True)

    def keyPressEvent(self, event):
        """Handle key press events."""
        key = event.key()
        modifiers = event.modifiers()
        
        # Undo/Redo shortcuts (handle before other shortcuts)
        if modifiers & QtCore.Qt.ControlModifier:
            if key == QtCore.Qt.Key_Z:
                if modifiers & QtCore.Qt.ShiftModifier:
                    # Ctrl+Shift+Z = Redo
                    if self.state.redo():
                        self.controls.set_mirror_enabled(self.state.mirror_state.enabled)
                        self.update()
                else:
                    # Ctrl+Z = Undo
                    if self.state.undo():
                        self.controls.set_mirror_enabled(self.state.mirror_state.enabled)
                        self.update()
                return
            
            if key == QtCore.Qt.Key_Y:
                # Ctrl+Y = Redo
                if self.state.redo():
                    self.controls.set_mirror_enabled(self.state.mirror_state.enabled)
                    self.update()
                return
        
        # Tool shortcuts
        if key == QtCore.Qt.Key_A and not (modifiers & QtCore.Qt.ControlModifier):
            self.state.active_tool = EditorTool.NODE
            self.controls.set_tool(EditorTool.NODE)
            self.update()
            return
        
        if key == QtCore.Qt.Key_P:
            self.state.active_tool = EditorTool.PEN
            self.controls.set_tool(EditorTool.PEN)
            self.update()
            return
        
        if key == QtCore.Qt.Key_R:
            self.state.active_tool = EditorTool.RECTANGLE
            self.controls.set_tool(EditorTool.RECTANGLE)
            self.update()
            return
        
        if key == QtCore.Qt.Key_O:
            self.state.active_tool = EditorTool.ELLIPSE
            self.controls.set_tool(EditorTool.ELLIPSE)
            self.update()
            return

        if key == QtCore.Qt.Key_M and not (modifiers & QtCore.Qt.ControlModifier):
            new_state = not self.state.mirror_state.enabled
            self.controls.set_mirror_enabled(new_state)
            self._on_mirror_toggled(new_state)
            return

        # Point type shortcuts (only when points are selected)
        if self.state.has_selection():
            if key == QtCore.Qt.Key_1:
                # Corner point
                self.state.push_undo_state("Convert to Corner")
                self._on_point_type_changed(PointType.CORNER)
                self.controls.set_point_type(PointType.CORNER)
                return
            
            if key == QtCore.Qt.Key_2:
                # Smooth point
                self.state.push_undo_state("Convert to Smooth")
                self._on_point_type_changed(PointType.SMOOTH)
                self.controls.set_point_type(PointType.SMOOTH)
                return
            
            if key == QtCore.Qt.Key_3:
                # Symmetric point
                self.state.push_undo_state("Convert to Symmetric")
                self._on_point_type_changed(PointType.SYMMETRIC)
                self.controls.set_point_type(PointType.SYMMETRIC)
                return
        
        # Global shortcuts
        if key == QtCore.Qt.Key_Escape:
            if self.pen_tool.has_active_path():
                self.pen_tool._cancel_path()
                self.update()
            else:
                self._cancel_editing()
            return
        
        if key in (QtCore.Qt.Key_Return, QtCore.Qt.Key_Enter):
            if self.pen_tool.has_active_path():
                self.pen_tool._finish_path()
                self.update()
            else:
                self._finish_editing()
            return
        
        # Delete key - push undo state before deletion
        if key in (QtCore.Qt.Key_Delete, QtCore.Qt.Key_Backspace):
            if self.state.has_selection():
                self.state.push_undo_state("Delete Points")
        
        # Tool-specific key handling
        handled = False
        tool = self.state.active_tool
        
        if tool == EditorTool.NODE:
            handled = self.node_tool.on_key_press(key, modifiers)
        elif tool == EditorTool.PEN:
            handled = self.pen_tool.on_key_press(key, modifiers)

        if handled:
            # Rebuild mirror map after deletion or structural changes
            if self.state.mirror_state.enabled and key in (QtCore.Qt.Key_Delete, QtCore.Qt.Key_Backspace):
                self._symmetrize_all_paths()
            self._update_controls_from_selection()
            self.update()

    def _update_controls_from_selection(self):
        """Update controls widget based on current selection."""
        selected = self.state.get_selected_points()
        if selected:
            self.controls.update_from_selection(selected)
    
    def resizeEvent(self, event):
        """Handle resize to reposition controls if needed."""
        super().resizeEvent(event)
        # Only update controls on actual resize, not during normal operation
        if self.isVisible() and event.oldSize().isValid() and event.size() != event.oldSize():
            self._update_controls_position()
    
    def focusOutEvent(self, event):
        """Handle focus loss - don't cancel editing, just update state."""
        super().focusOutEvent(event)
        # We keep editing active, user can click back
