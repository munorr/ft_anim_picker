"""
Curve editor tool implementations.

This module provides the tools for interacting with curves:
- NodeTool: Select and edit existing points/handles
- PenTool: Draw new paths by adding points
- RectangleTool: Draw rectangular shapes
- EllipseTool: Draw elliptical shapes
"""

from PySide6 import QtCore, QtGui, QtWidgets
from enum import Enum, auto
from typing import Optional, List, Tuple
from dataclasses import dataclass, field
import math

from .curve_data import CurvePoint, CurvePath, ButtonShape, PointType
from .curve_mirror import MirrorState, MirrorMap, rebuild_mirror_side, PointRole


class EditorTool(Enum):
    """Available editing tools."""
    NONE = auto()
    PEN = auto()
    NODE = auto()
    RECTANGLE = auto()
    ELLIPSE = auto()


@dataclass
class HitResult:
    """
    Result of hit testing on curve elements.
    
    Attributes:
        path_index: Index of the path hit (-1 if none)
        point_index: Index of the point hit (-1 if none)
        element_type: Type of element ('anchor', 'handle_in', 'handle_out', 'segment')
        distance: Distance from hit point to element
        t_param: For segment hits, the t parameter (0-1) along the segment
        segment_point: For segment hits, the closest point on the segment
    """
    path_index: int = -1
    point_index: int = -1
    element_type: Optional[str] = None  # 'anchor', 'handle_in', 'handle_out', 'segment'
    distance: float = float('inf')
    t_param: float = 0.0  # Parameter along segment (0-1)
    segment_point: Optional[QtCore.QPointF] = None  # Closest point on segment
    
    def is_valid(self) -> bool:
        """Check if this hit result found an element."""
        return self.path_index >= 0 and self.point_index >= 0
    
    def is_anchor(self) -> bool:
        """Check if hit was on an anchor point."""
        return self.element_type == 'anchor'
    
    def is_handle(self) -> bool:
        """Check if hit was on a handle."""
        return self.element_type in ('handle_in', 'handle_out')
    
    def is_segment(self) -> bool:
        """Check if hit was on a curve segment."""
        return self.element_type == 'segment'


class CurveEditorState:
    """
    Maintains the current state of the curve editor.
    
    This is the central state management for the editor, tracking:
    - Active tool
    - Current shape being edited
    - Point selection
    - Drag operations
    - Modifier key states
    - Internal undo/redo stack for curve editing actions
    """
    
    # Maximum undo steps for curve editing
    MAX_UNDO_STEPS = 50
    
    def __init__(self):
        # Tool state
        self.active_tool: EditorTool = EditorTool.NODE
        
        # Shape data
        self.current_shape: Optional[ButtonShape] = None
        self.original_shape: Optional[ButtonShape] = None  # For cancel - restores to state before editing started
        
        # Selection
        self.selected_points: List[Tuple[int, int]] = []  # [(path_index, point_index), ...]
        self.selected_handles: List[Tuple[int, int, str]] = []  # [(path_idx, point_idx, 'handle_in'|'handle_out'), ...]
        
        # Drawing state (for pen tool)
        self.is_drawing: bool = False
        self.preview_point: Optional[QtCore.QPointF] = None
        self.preview_handle: Optional[QtCore.QPointF] = None
        
        # Drag state
        self.dragging: bool = False
        self.drag_start: Optional[QtCore.QPointF] = None
        self.drag_element: Optional[HitResult] = None
        self.drag_original_positions: dict = {}  # Store original positions for drag operation
        
        # Modifier states
        self.shift_held: bool = False
        self.alt_held: bool = False
        self.ctrl_held: bool = False
        
        # Mirror state
        self.mirror_state: MirrorState = MirrorState()
        self.mirror_map: MirrorMap = MirrorMap()

        # Internal undo/redo stacks for curve editing
        self._undo_stack: List[dict] = []
        self._redo_stack: List[dict] = []
        self._last_action_name: str = ""
    
    def clear_selection(self):
        """Clear all selected points and handles."""
        self.selected_points.clear()
        self.selected_handles.clear()

    def select_point(self, path_index: int, point_index: int, add_to_selection: bool = False):
        """
        Select a point.

        Args:
            path_index: Index of the path
            point_index: Index of the point within the path
            add_to_selection: If True, add to existing selection. If False, replace.
        """
        key = (path_index, point_index)
        if not add_to_selection:
            self.selected_points.clear()
            self.selected_handles.clear()
        if key not in self.selected_points:
            self.selected_points.append(key)

    def deselect_point(self, path_index: int, point_index: int):
        """Remove a point from selection."""
        key = (path_index, point_index)
        if key in self.selected_points:
            self.selected_points.remove(key)

    def toggle_point_selection(self, path_index: int, point_index: int):
        """Toggle selection state of a point."""
        key = (path_index, point_index)
        if key in self.selected_points:
            self.selected_points.remove(key)
        else:
            self.selected_points.append(key)

    def is_point_selected(self, path_index: int, point_index: int) -> bool:
        """Check if a point is selected."""
        return (path_index, point_index) in self.selected_points

    def select_handle(self, path_index: int, point_index: int, handle_type: str, add_to_selection: bool = False):
        """Select a handle independently."""
        key = (path_index, point_index, handle_type)
        if not add_to_selection:
            self.selected_points.clear()
            self.selected_handles.clear()
        if key not in self.selected_handles:
            self.selected_handles.append(key)

    def is_handle_selected(self, path_index: int, point_index: int, handle_type: str) -> bool:
        """Check if a specific handle is selected."""
        return (path_index, point_index, handle_type) in self.selected_handles
    
    def get_selected_points(self) -> List[Tuple[CurvePath, CurvePoint, int, int]]:
        """
        Get all selected points with their parent paths.
        
        Returns:
            List of (path, point, path_index, point_index) tuples
        """
        result = []
        if not self.current_shape:
            return result
        
        for path_idx, point_idx in self.selected_points:
            if path_idx < len(self.current_shape.paths):
                path = self.current_shape.paths[path_idx]
                if point_idx < len(path.points):
                    result.append((path, path.points[point_idx], path_idx, point_idx))
        
        return result
    
    def has_selection(self) -> bool:
        """Check if any points or handles are selected."""
        return len(self.selected_points) > 0 or len(self.selected_handles) > 0

    def selection_count(self) -> int:
        """Get number of selected points and handles."""
        return len(self.selected_points) + len(self.selected_handles)
    
    def store_original_shape(self):
        """Store copy of current shape for cancel/undo."""
        if self.current_shape:
            self.original_shape = self.current_shape.copy()
    
    def restore_original_shape(self):
        """Restore shape from stored original."""
        if self.original_shape:
            self.current_shape = self.original_shape.copy()
    
    def update_modifiers(self, modifiers: QtCore.Qt.KeyboardModifiers):
        """Update modifier key states from Qt modifiers."""
        self.shift_held = bool(modifiers & QtCore.Qt.ShiftModifier)
        self.alt_held = bool(modifiers & QtCore.Qt.AltModifier)
        self.ctrl_held = bool(modifiers & QtCore.Qt.ControlModifier)
    
    # ==================== Internal Undo/Redo System ====================
    
    def push_undo_state(self, action_name: str = ""):
        """
        Push current shape state to the undo stack.
        Call this BEFORE making changes to the shape.
        
        Args:
            action_name: Description of the action being performed
        """
        if not self.current_shape:
            return
        
        # Save current state with selection and mirror state
        state_snapshot = {
            'shape': self.current_shape.copy(),
            'selection': list(self.selected_points),
            'handle_selection': list(self.selected_handles),
            'action': action_name or "Edit",
            'mirror_map': self.mirror_map.copy(),
            'mirror_state': self.mirror_state.copy(),
        }
        
        self._undo_stack.append(state_snapshot)
        self._last_action_name = action_name
        
        # Clear redo stack on new action
        self._redo_stack.clear()
        
        # Limit stack size
        if len(self._undo_stack) > self.MAX_UNDO_STEPS:
            self._undo_stack.pop(0)
    
    def can_undo(self) -> bool:
        """Check if undo is available."""
        return len(self._undo_stack) > 0
    
    def can_redo(self) -> bool:
        """Check if redo is available."""
        return len(self._redo_stack) > 0
    
    def undo(self) -> bool:
        """
        Undo the last curve editing action.
        
        Returns:
            True if undo was performed, False if nothing to undo
        """
        if not self.can_undo() or not self.current_shape:
            return False
        
        # Save current state to redo stack
        redo_snapshot = {
            'shape': self.current_shape.copy(),
            'selection': list(self.selected_points),
            'action': self._last_action_name or "Undo",
            'mirror_map': self.mirror_map.copy(),
            'mirror_state': self.mirror_state.copy(),
        }
        self._redo_stack.append(redo_snapshot)

        # Restore previous state
        undo_snapshot = self._undo_stack.pop()
        self.current_shape = undo_snapshot['shape'].copy()
        self.selected_points = list(undo_snapshot['selection'])
        self.selected_handles = list(undo_snapshot.get('handle_selection', []))
        self._last_action_name = undo_snapshot.get('action', '')
        if 'mirror_map' in undo_snapshot:
            self.mirror_map = undo_snapshot['mirror_map'].copy()
        if 'mirror_state' in undo_snapshot:
            self.mirror_state = undo_snapshot['mirror_state'].copy()

        # Validate selection indices against restored shape
        self._validate_selection()

        return True
    
    def redo(self) -> bool:
        """
        Redo the last undone curve editing action.
        
        Returns:
            True if redo was performed, False if nothing to redo
        """
        if not self.can_redo() or not self.current_shape:
            return False
        
        # Save current state to undo stack
        undo_snapshot = {
            'shape': self.current_shape.copy(),
            'selection': list(self.selected_points),
            'action': self._last_action_name or "Redo",
            'mirror_map': self.mirror_map.copy(),
            'mirror_state': self.mirror_state.copy(),
        }
        self._undo_stack.append(undo_snapshot)

        # Restore next state
        redo_snapshot = self._redo_stack.pop()
        self.current_shape = redo_snapshot['shape'].copy()
        self.selected_points = list(redo_snapshot['selection'])
        self.selected_handles = list(redo_snapshot.get('handle_selection', []))
        self._last_action_name = redo_snapshot.get('action', '')
        if 'mirror_map' in redo_snapshot:
            self.mirror_map = redo_snapshot['mirror_map'].copy()
        if 'mirror_state' in redo_snapshot:
            self.mirror_state = redo_snapshot['mirror_state'].copy()
        
        # Validate selection indices against restored shape
        self._validate_selection()
        
        return True
    
    def clear_undo_history(self):
        """Clear all undo/redo history. Call when starting a new editing session."""
        self._undo_stack.clear()
        self._redo_stack.clear()
        self._last_action_name = ""
    
    def _validate_selection(self):
        """Validate and fix selection indices after undo/redo."""
        if not self.current_shape:
            self.selected_points.clear()
            return
        
        valid_selection = []
        for path_idx, point_idx in self.selected_points:
            if path_idx < len(self.current_shape.paths):
                path = self.current_shape.paths[path_idx]
                if point_idx < len(path.points):
                    valid_selection.append((path_idx, point_idx))
        
        self.selected_points = valid_selection
    
    def get_undo_action_name(self) -> str:
        """Get the name of the action that would be undone."""
        if self._undo_stack:
            return self._undo_stack[-1].get('action', 'Edit')
        return ""
    
    def get_redo_action_name(self) -> str:
        """Get the name of the action that would be redone."""
        if self._redo_stack:
            return self._redo_stack[-1].get('action', 'Edit')
        return ""


class NodeTool:
    """
    Node tool for selecting and editing existing points.
    
    Features:
    - Click to select points
    - Shift+click to add/remove from selection
    - Drag to move points/handles
    - Alt+drag on handle to break symmetry
    - Delete key to remove points
    - Number keys to change point type
    - Double-click on segment to add point
    """
    
    HIT_RADIUS = 10  # Pixels for anchor hit detection
    HANDLE_HIT_RADIUS = 8  # Pixels for handle hit detection
    SEGMENT_HIT_RADIUS = 6  # Pixels for segment hit detection
    NEAR_ANCHOR_BAND_FACTOR = 3.0  # Shift+drag near (but not on) an anchor creates a single-side handle within this multiple of HIT_RADIUS

    def __init__(self, state: CurveEditorState):
        self.state = state
        self.segment_hover: Optional[HitResult] = None  # Track segment hover for visualization
        self.band_hover: Optional[dict] = None  # Shift+hover near anchor: {path_index, point_index, side, cursor_pos}
        self._convert_drag_active: bool = False
        self._asymmetric_handle_drag: bool = False
    
    def hit_test(self, pos: QtCore.QPointF, scale: float = 1.0, include_segments: bool = True) -> HitResult:
        """
        Test what element is at the given position.
        
        Args:
            pos: Position in shape coordinates
            scale: Current zoom scale for adjusting hit radius
            include_segments: Whether to test curve segments (slower)
            
        Returns:
            HitResult describing what was hit
        """
        result = HitResult()
        
        if not self.state.current_shape:
            return result
        
        # Adjust hit radii for scale
        anchor_radius = self.HIT_RADIUS / scale
        handle_radius = self.HANDLE_HIT_RADIUS / scale
        segment_radius = self.SEGMENT_HIT_RADIUS / scale
        
        mirror_active = self.state.mirror_state.enabled and self.state.mirror_map.has_entries()

        # Test all paths and points - anchors and handles first (higher priority)
        for path_idx, path in enumerate(self.state.current_shape.paths):
            for point_idx, point in enumerate(path.points):

                # Skip mirror-side points so edits only happen on SOURCE side
                if mirror_active and self.state.mirror_map.is_mirror(path_idx, point_idx):
                    continue

                # Test anchor point
                dist = self._distance(pos, point.position)
                if dist < anchor_radius and dist < result.distance:
                    result.path_index = path_idx
                    result.point_index = point_idx
                    result.element_type = 'anchor'
                    result.distance = dist

                # Test handles for ALL points (not just selected)
                if point.handle_in:
                    h_pos = point.get_handle_in_absolute()
                    dist = self._distance(pos, h_pos)
                    if dist < handle_radius and dist < result.distance:
                        result.path_index = path_idx
                        result.point_index = point_idx
                        result.element_type = 'handle_in'
                        result.distance = dist

                if point.handle_out:
                    h_pos = point.get_handle_out_absolute()
                    dist = self._distance(pos, h_pos)
                    if dist < handle_radius and dist < result.distance:
                        result.path_index = path_idx
                        result.point_index = point_idx
                        result.element_type = 'handle_out'
                        result.distance = dist
        
        # If we hit an anchor or handle, return that (higher priority than segments)
        if result.is_valid():
            return result
        
        # Test curve segments (only if no point/handle was hit)
        if include_segments:
            segment_result = self._hit_test_segments(pos, segment_radius)
            if segment_result.is_valid() and segment_result.distance < result.distance:
                return segment_result
        
        return result
    
    def _hit_test_segments(self, pos: QtCore.QPointF, radius: float) -> HitResult:
        """Test all curve segments for hit."""
        result = HitResult()

        if not self.state.current_shape:
            return result

        mirror_active = self.state.mirror_state.enabled and self.state.mirror_map.has_entries()

        for path_idx, path in enumerate(self.state.current_shape.paths):
            num_points = len(path.points)
            if num_points < 2:
                continue

            # Test each segment
            num_segments = num_points if path.is_closed else num_points - 1
            for seg_idx in range(num_segments):
                end_idx = (seg_idx + 1) % num_points

                # Skip segments entirely within the mirror side (both endpoints MIRROR).
                # Allow CENTER↔MIRROR segments (top/bottom of closed paths) so the
                # user can add points there; the widget re-symmetrizes after insertion.
                if mirror_active:
                    if (self.state.mirror_map.is_mirror(path_idx, seg_idx) and
                            self.state.mirror_map.is_mirror(path_idx, end_idx)):
                        continue

                from_point = path.points[seg_idx]
                to_point = path.points[end_idx]

                # Find closest point on segment
                closest, t = self._closest_point_on_bezier(
                    pos, from_point, to_point
                )

                dist = self._distance(pos, closest)
                if dist < radius and dist < result.distance:
                    result.path_index = path_idx
                    result.point_index = seg_idx  # Index of starting point of segment
                    result.element_type = 'segment'
                    result.distance = dist
                    result.t_param = t
                    result.segment_point = closest

        return result
    
    def _closest_point_on_bezier(self, pos: QtCore.QPointF, from_point: CurvePoint, 
                                  to_point: CurvePoint) -> Tuple[QtCore.QPointF, float]:
        """
        Find the closest point on a bezier curve segment.
        
        Returns:
            (closest_point, t_parameter)
        """
        p0 = from_point.position
        p3 = to_point.position
        
        # Get control points
        has_ctrl1 = from_point.has_handle_out() if hasattr(from_point, 'has_handle_out') else from_point.handle_out is not None
        has_ctrl2 = to_point.has_handle_in() if hasattr(to_point, 'has_handle_in') else to_point.handle_in is not None
        
        if has_ctrl1 or has_ctrl2:
            p1 = from_point.get_handle_out_absolute() if has_ctrl1 else p0
            p2 = to_point.get_handle_in_absolute() if has_ctrl2 else p3
            return self._closest_point_on_cubic(pos, p0, p1, p2, p3)
        else:
            # Straight line
            return self._closest_point_on_line(pos, p0, p3)
    
    def _closest_point_on_line(self, pos: QtCore.QPointF, p0: QtCore.QPointF, 
                                p1: QtCore.QPointF) -> Tuple[QtCore.QPointF, float]:
        """Find closest point on a line segment."""
        dx = p1.x() - p0.x()
        dy = p1.y() - p0.y()
        
        if dx == 0 and dy == 0:
            return (p0, 0.0)
        
        t = ((pos.x() - p0.x()) * dx + (pos.y() - p0.y()) * dy) / (dx * dx + dy * dy)
        t = max(0.0, min(1.0, t))
        
        closest = QtCore.QPointF(p0.x() + t * dx, p0.y() + t * dy)
        return (closest, t)
    
    def _closest_point_on_cubic(self, pos: QtCore.QPointF, p0: QtCore.QPointF, 
                                 p1: QtCore.QPointF, p2: QtCore.QPointF, 
                                 p3: QtCore.QPointF) -> Tuple[QtCore.QPointF, float]:
        """Find closest point on a cubic bezier curve by sampling."""
        best_dist = float('inf')
        best_t = 0.0
        best_point = p0
        
        # Sample the curve at multiple points
        num_samples = 20
        for i in range(num_samples + 1):
            t = i / num_samples
            pt = self._evaluate_cubic(t, p0, p1, p2, p3)
            dist = self._distance(pos, pt)
            if dist < best_dist:
                best_dist = dist
                best_t = t
                best_point = pt
        
        # Refine around the best point
        for _ in range(3):
            step = 0.5 / num_samples
            for dt in [-step, step]:
                t = max(0.0, min(1.0, best_t + dt))
                pt = self._evaluate_cubic(t, p0, p1, p2, p3)
                dist = self._distance(pos, pt)
                if dist < best_dist:
                    best_dist = dist
                    best_t = t
                    best_point = pt
            num_samples *= 2
        
        return (best_point, best_t)
    
    def _evaluate_cubic(self, t: float, p0: QtCore.QPointF, p1: QtCore.QPointF,
                        p2: QtCore.QPointF, p3: QtCore.QPointF) -> QtCore.QPointF:
        """Evaluate a cubic bezier curve at parameter t."""
        mt = 1 - t
        mt2 = mt * mt
        mt3 = mt2 * mt
        t2 = t * t
        t3 = t2 * t
        
        x = mt3 * p0.x() + 3 * mt2 * t * p1.x() + 3 * mt * t2 * p2.x() + t3 * p3.x()
        y = mt3 * p0.y() + 3 * mt2 * t * p1.y() + 3 * mt * t2 * p2.y() + t3 * p3.y()
        
        return QtCore.QPointF(x, y)
    
    def add_point_on_segment(self, hit: HitResult, pos: QtCore.QPointF = None) -> Tuple[bool, int]:
        """
        Add a new point on a curve segment at the hit location.
        
        Args:
            hit: HitResult from segment hit test
            pos: Mouse position for initiating drag
            
        Returns:
            Tuple of (True if point was added, index of new point or -1)
        """
        if not hit.is_segment() or not self.state.current_shape:
            return (False, -1)
        
        path = self.state.current_shape.paths[hit.path_index]
        seg_start_idx = hit.point_index
        seg_end_idx = (seg_start_idx + 1) % len(path.points)
        
        from_point = path.points[seg_start_idx]
        to_point = path.points[seg_end_idx]
        t = hit.t_param
        
        # Create new point at the split position
        new_point = self._split_bezier_at_t(from_point, to_point, t)
        
        # Insert after the start point of the segment
        insert_idx = seg_start_idx + 1
        path.add_point(new_point, insert_idx)
        
        # Select the new point
        self.state.clear_selection()
        self.state.select_point(hit.path_index, insert_idx)
        
        # Start dragging the new point immediately for seamless UX
        if pos is not None:
            new_hit = HitResult(
                path_index=hit.path_index,
                point_index=insert_idx,
                element_type='anchor',
                distance=0
            )
            self.state.dragging = True
            self.state.drag_start = QtCore.QPointF(pos)
            self.state.drag_element = new_hit
            self._store_original_positions()
        
        return (True, insert_idx)
    
    def _split_bezier_at_t(self, from_point: CurvePoint, to_point: CurvePoint, 
                           t: float) -> CurvePoint:
        """
        Split a bezier curve at parameter t and return the new middle point.
        Also adjusts the handles of the original points.
        """
        p0 = from_point.position
        p3 = to_point.position
        
        has_ctrl1 = from_point.has_handle_out() if hasattr(from_point, 'has_handle_out') else from_point.handle_out is not None
        has_ctrl2 = to_point.has_handle_in() if hasattr(to_point, 'has_handle_in') else to_point.handle_in is not None
        
        if has_ctrl1 or has_ctrl2:
            p1 = from_point.get_handle_out_absolute() if has_ctrl1 else p0
            p2 = to_point.get_handle_in_absolute() if has_ctrl2 else p3
            
            # De Casteljau's algorithm for splitting
            # First level
            q0 = self._lerp(p0, p1, t)
            q1 = self._lerp(p1, p2, t)
            q2 = self._lerp(p2, p3, t)
            
            # Second level
            r0 = self._lerp(q0, q1, t)
            r1 = self._lerp(q1, q2, t)
            
            # Third level - the split point
            split_pos = self._lerp(r0, r1, t)
            
            # Update original handles
            from_point.handle_out = q0 - p0
            to_point.handle_in = q2 - p3
            
            # Create new point with handles
            new_point = CurvePoint(
                position=split_pos,
                handle_in=r0 - split_pos,
                handle_out=r1 - split_pos,
                point_type=PointType.SMOOTH
            )
        else:
            # Straight line - just add a corner point
            split_pos = self._lerp(p0, p3, t)
            new_point = CurvePoint(
                position=split_pos,
                point_type=PointType.CORNER
            )
        
        return new_point
    
    def _lerp(self, p0: QtCore.QPointF, p1: QtCore.QPointF, t: float) -> QtCore.QPointF:
        """Linear interpolation between two points."""
        return QtCore.QPointF(
            p0.x() + t * (p1.x() - p0.x()),
            p0.y() + t * (p1.y() - p0.y())
        )

    def _hit_test_anchor_band(self, pos: QtCore.QPointF, scale: float) -> HitResult:
        """Find an anchor within the near-anchor band (outside HIT_RADIUS, within NEAR_ANCHOR_BAND_FACTOR×HIT_RADIUS)."""
        result = HitResult()
        if not self.state.current_shape:
            return result

        anchor_radius = self.HIT_RADIUS / scale
        band_radius = anchor_radius * self.NEAR_ANCHOR_BAND_FACTOR
        mirror_active = self.state.mirror_state.enabled and self.state.mirror_map.has_entries()

        for path_idx, path in enumerate(self.state.current_shape.paths):
            for point_idx, point in enumerate(path.points):
                if mirror_active and self.state.mirror_map.is_mirror(path_idx, point_idx):
                    continue
                dist = self._distance(pos, point.position)
                if anchor_radius <= dist < band_radius and dist < result.distance:
                    result.path_index = path_idx
                    result.point_index = point_idx
                    result.element_type = 'anchor_band'
                    result.distance = dist
        return result

    def _classify_anchor_side(self, path: CurvePath, point_idx: int, click_pos: QtCore.QPointF) -> str:
        """Return 'handle_in' or 'handle_out' based on which side of the anchor the click landed."""
        point = path.points[point_idx]
        tangent_out = None
        if point.handle_out is not None:
            tangent_out = QtCore.QPointF(point.handle_out)
        elif point.handle_in is not None:
            tangent_out = QtCore.QPointF(-point.handle_in.x(), -point.handle_in.y())
        else:
            num_points = len(path.points)
            next_idx = point_idx + 1 if point_idx + 1 < num_points else (0 if path.is_closed else -1)
            prev_idx = point_idx - 1 if point_idx - 1 >= 0 else (num_points - 1 if path.is_closed else -1)
            if next_idx >= 0:
                tangent_out = path.points[next_idx].position - point.position
            elif prev_idx >= 0:
                rev = path.points[prev_idx].position - point.position
                tangent_out = QtCore.QPointF(-rev.x(), -rev.y())

        click_vec = click_pos - point.position
        if tangent_out is None:
            return 'handle_out' if (click_vec.x() > 0 or (click_vec.x() == 0 and click_vec.y() > 0)) else 'handle_in'

        dot = tangent_out.x() * click_vec.x() + tangent_out.y() * click_vec.y()
        return 'handle_out' if dot >= 0 else 'handle_in'

    def _begin_asymmetric_handle_drag(self, path_idx: int, point_idx: int, side: str, click_pos: QtCore.QPointF) -> bool:
        """Initialize a drag that edits only one handle of the given anchor.

        If the handle is missing or zero-length, create it at the click position (snap-to-cursor).
        If it already exists, grab it from its current position so it doesn't teleport.
        """
        if not self.state.current_shape:
            return False
        path = self.state.current_shape.paths[path_idx]
        point = path.points[point_idx]

        point.point_type = PointType.CORNER

        existing = point.handle_out if side == 'handle_out' else point.handle_in
        has_existing = existing is not None and point._vector_length(existing) > 0.0001

        if has_existing:
            original_handle_pos = point.position + existing
        else:
            if side == 'handle_out':
                point.handle_out = click_pos - point.position
            else:
                point.handle_in = click_pos - point.position
            original_handle_pos = QtCore.QPointF(click_pos)

        self.state.select_point(path_idx, point_idx, False)

        handle_hit = HitResult(
            path_index=path_idx,
            point_index=point_idx,
            element_type=side,
            distance=0,
        )
        self.state.dragging = True
        self.state.drag_start = QtCore.QPointF(click_pos)
        self.state.drag_element = handle_hit
        self.state.drag_original_positions.clear()
        self.state.drag_original_positions[(side, path_idx, point_idx)] = original_handle_pos
        self.state.drag_original_positions[('anchor', path_idx, point_idx)] = QtCore.QPointF(point.position)
        self._asymmetric_handle_drag = True
        return True

    def on_mouse_press(self, pos: QtCore.QPointF, modifiers: QtCore.Qt.KeyboardModifiers,
                       scale: float = 1.0) -> bool:
        """
        Handle mouse press for selection and drag start.
        
        Returns:
            True if event was handled
        """
        self.state.update_modifiers(modifiers)
        
        hit = self.hit_test(pos, scale)

        # Redirect mirror point clicks to their source partner
        if hit.is_valid() and self.state.mirror_state.enabled:
            info = self.state.mirror_map.get(hit.path_index, hit.point_index)
            if info and info.role == PointRole.MIRROR and info.partner_key:
                hit.path_index, hit.point_index = info.partner_key

        # Shift+drag near (but not on) an anchor → grab/create a single-side handle.
        # Only fires when the primary hit did not land on an anchor or handle, so the
        # existing shift+anchor "convert both handles" gesture keeps working.
        if (self.state.shift_held and not self.state.ctrl_held and not self.state.alt_held
                and not (hit.is_valid() and (hit.is_anchor() or hit.is_handle()))):
            band_hit = self._hit_test_anchor_band(pos, scale)
            if band_hit.is_valid():
                p_idx, pt_idx = band_hit.path_index, band_hit.point_index
                if self.state.mirror_state.enabled:
                    info = self.state.mirror_map.get(p_idx, pt_idx)
                    if info and info.role == PointRole.MIRROR and info.partner_key:
                        p_idx, pt_idx = info.partner_key
                path = self.state.current_shape.paths[p_idx]
                side = self._classify_anchor_side(path, pt_idx, pos)
                if self._begin_asymmetric_handle_drag(p_idx, pt_idx, side, pos):
                    if self.state.mirror_state.enabled:
                        rebuild_mirror_side(
                            path,
                            self.state.mirror_map, p_idx,
                            self.state.mirror_state.axis,
                            self.state.mirror_state.line_position,
                        )
                    return True

        if hit.is_valid():
            # Alt + Click on handle → Align that specific handle linearly
            if hit.is_handle() and self.state.alt_held and not self.state.ctrl_held and not self.state.shift_held:
                if self.state.current_shape:
                    path = self.state.current_shape.paths[hit.path_index]
                    point = path.points[hit.point_index]
                    
                    # Get neighboring points for alignment
                    prev_point = None
                    next_point = None
                    
                    if hit.point_index > 0:
                        prev_point = path.points[hit.point_index - 1]
                    elif path.is_closed and len(path.points) > 1:
                        prev_point = path.points[-1]
                    
                    if hit.point_index < len(path.points) - 1:
                        next_point = path.points[hit.point_index + 1]
                    elif path.is_closed and len(path.points) > 1:
                        next_point = path.points[0]
                    
                    # Align the specific handle that was clicked
                    if hit.element_type == 'handle_out' and next_point:
                        # Align out handle toward next point
                        direction = next_point.position - point.position
                        length = math.sqrt(direction.x() ** 2 + direction.y() ** 2)
                        if length > 0.0001:
                            # Keep current handle length if it exists
                            current_length = point._vector_length(point.handle_out) if point.handle_out else 30.0
                            direction = direction / length
                            scaled_length = min(current_length, length / 3)
                            point.handle_out = QtCore.QPointF(direction.x() * scaled_length, direction.y() * scaled_length)
                            # Make it a corner to prevent other handle from moving
                            point.point_type = PointType.CORNER
                    
                    elif hit.element_type == 'handle_in' and prev_point:
                        # Align in handle toward previous point
                        direction = prev_point.position - point.position
                        length = math.sqrt(direction.x() ** 2 + direction.y() ** 2)
                        if length > 0.0001:
                            # Keep current handle length if it exists
                            current_length = point._vector_length(point.handle_in) if point.handle_in else 30.0
                            direction = direction / length
                            scaled_length = min(current_length, length / 3)
                            point.handle_in = QtCore.QPointF(direction.x() * scaled_length, direction.y() * scaled_length)
                            # Make it a corner to prevent other handle from moving
                            point.point_type = PointType.CORNER

                    # Sync mirror side after handle alignment
                    if self.state.mirror_state.enabled:
                        rebuild_mirror_side(
                            path,
                            self.state.mirror_map, hit.path_index,
                            self.state.mirror_state.axis,
                            self.state.mirror_state.line_position
                        )

                    # Select the point to show feedback
                    self.state.select_point(hit.path_index, hit.point_index, False)
                    return True
            
            # Clicking on a handle selects it independently
            if hit.is_handle():
                already_selected = self.state.is_handle_selected(hit.path_index, hit.point_index, hit.element_type)
                if not already_selected:
                    add_to = bool(self.state.shift_held)
                    self.state.select_handle(hit.path_index, hit.point_index, hit.element_type, add_to)
            
            # Handle point type conversion with modifiers
            if hit.is_anchor():
                # Alt + Click → Remove handles (fully angular corner)
                if self.state.alt_held and not self.state.ctrl_held and not self.state.shift_held:
                    if self.state.current_shape:
                        path = self.state.current_shape.paths[hit.path_index]
                        point = path.points[hit.point_index]
                        point.remove_handles()
                        # Select the point after conversion
                        self.state.select_point(hit.path_index, hit.point_index, False)
                        return True
                
                # Ctrl + Click → Convert to Corner (angular with independent handles)
                elif self.state.ctrl_held and not self.state.shift_held and not self.state.alt_held:
                    if self.state.current_shape:
                        path = self.state.current_shape.paths[hit.path_index]
                        point = path.points[hit.point_index]
                        point.convert_to_corner()
                        # Select the point after conversion
                        self.state.select_point(hit.path_index, hit.point_index, False)
                        return True
                
                # Shift + Click → Convert to Smooth (curved with handles)
                elif self.state.shift_held and not self.state.ctrl_held and not self.state.alt_held:
                    if self.state.current_shape:
                        path = self.state.current_shape.paths[hit.path_index]
                        point = path.points[hit.point_index]

                        # Use SYMMETRIC so both handles grow equally toward
                        # the drag direction; converted to SMOOTH on release
                        point.point_type = PointType.SYMMETRIC
                        point.handle_out = QtCore.QPointF(0, 0)
                        point.handle_in = QtCore.QPointF(0, 0)
                        self._convert_drag_active = True

                        # Select the point after conversion
                        self.state.select_point(hit.path_index, hit.point_index, False)

                        # Start dragging handle_out immediately so user can control the angle
                        handle_hit = HitResult(
                            path_index=hit.path_index,
                            point_index=hit.point_index,
                            element_type='handle_out',
                            distance=0
                        )
                        self.state.dragging = True
                        self.state.drag_start = QtCore.QPointF(pos)
                        self.state.drag_element = handle_hit
                        # Store anchor position as the handle_out original so
                        # the handle extends directly from anchor toward cursor
                        self.state.drag_original_positions.clear()
                        self.state.drag_original_positions[('handle_out', hit.path_index, hit.point_index)] = QtCore.QPointF(point.position)
                        self.state.drag_original_positions[('anchor', hit.path_index, hit.point_index)] = QtCore.QPointF(point.position)

                        return True
                
                # Ctrl + Shift + Click → Align handles linearly
                elif self.state.ctrl_held and self.state.shift_held and not self.state.alt_held:
                    if self.state.current_shape:
                        path = self.state.current_shape.paths[hit.path_index]
                        point = path.points[hit.point_index]
                        
                        # Get neighboring points for alignment
                        prev_point = None
                        next_point = None
                        
                        if hit.point_index > 0:
                            prev_point = path.points[hit.point_index - 1]
                        elif path.is_closed and len(path.points) > 1:
                            prev_point = path.points[-1]
                        
                        if hit.point_index < len(path.points) - 1:
                            next_point = path.points[hit.point_index + 1]
                        elif path.is_closed and len(path.points) > 1:
                            next_point = path.points[0]
                        
                        point.align_handles_linearly(prev_point, next_point)
                        # Select the point after conversion
                        self.state.select_point(hit.path_index, hit.point_index, False)
                        return True
                
                # Regular selection (no modifiers)
                elif not self.state.ctrl_held and not self.state.shift_held and not self.state.alt_held:
                    if not self.state.is_point_selected(hit.path_index, hit.point_index):
                        # Select only this point
                        self.state.select_point(hit.path_index, hit.point_index, False)
                    # If already selected, keep selection for potential drag
            
            # Handle segment click - add point on curve
            if hit.is_segment():
                success, _ = self.add_point_on_segment(hit, pos)
                return success
            
            # Start dragging (only for anchors and handles, not when modifiers are for point type conversion)
            # Don't start dragging if Alt is held on a handle (that was for alignment)
            if hit.is_handle():
                # Handles: always start drag (Shift/Ctrl don't do type conversions on handles)
                # Exception: Alt+handle was already handled above (alignment)
                if not (self.state.alt_held):
                    self.state.dragging = True
                    self.state.drag_start = QtCore.QPointF(pos)
                    self.state.drag_element = hit
                    self._store_original_positions()
            elif hit.is_anchor():
                # Anchors: only drag when no modifier-based conversion is active
                if not (self.state.ctrl_held or self.state.shift_held):
                    self.state.dragging = True
                    self.state.drag_start = QtCore.QPointF(pos)
                    self.state.drag_element = hit
                    self._store_original_positions()

            return True
        
        # Clicked on empty space
        if not self.state.shift_held and not self.state.ctrl_held:
            self.state.clear_selection()
        
        return False
    
    def on_mouse_move(self, pos: QtCore.QPointF, modifiers: QtCore.Qt.KeyboardModifiers,
                      scale: float = 1.0) -> bool:
        """
        Handle mouse move for dragging and segment hover.
        
        Returns:
            True if event was handled (dragging active or segment hovered)
        """
        self.state.update_modifiers(modifiers)
        
        # Track segment hover for visualization (when not dragging)
        if not self.state.dragging:
            # First check if we're over any point or handle
            point_hit = self.hit_test(pos, scale, include_segments=False)

            # When shift is held alone and cursor is in the near-anchor band,
            # prefer band-hover feedback over segment "+" to signal the asymmetric
            # single-side handle gesture.
            prev_band = self.band_hover
            self.band_hover = None
            if (not point_hit.is_valid()
                    and self.state.shift_held and not self.state.ctrl_held and not self.state.alt_held):
                band_hit = self._hit_test_anchor_band(pos, scale)
                if band_hit.is_valid():
                    path = self.state.current_shape.paths[band_hit.path_index]
                    side = self._classify_anchor_side(path, band_hit.point_index, pos)
                    self.band_hover = {
                        'path_index': band_hit.path_index,
                        'point_index': band_hit.point_index,
                        'side': side,
                        'cursor_pos': QtCore.QPointF(pos),
                    }
                    if self.segment_hover is not None:
                        self.segment_hover = None
                    return True

            if self.band_hover is None and prev_band is not None:
                if not point_hit.is_valid():
                    segment_hit = self._hit_test_segments(pos, self.SEGMENT_HIT_RADIUS / scale)
                    self.segment_hover = segment_hit if segment_hit.is_valid() else None
                return True

            # Only test segments if we're NOT over a point or handle
            if not point_hit.is_valid():
                segment_hit = self._hit_test_segments(pos, self.SEGMENT_HIT_RADIUS / scale)
                old_hover = self.segment_hover
                self.segment_hover = segment_hit if segment_hit.is_valid() else None

                # Return True if hover state changed (to trigger repaint)
                if (old_hover is None) != (self.segment_hover is None):
                    return True
                if old_hover and self.segment_hover:
                    if (old_hover.path_index != self.segment_hover.path_index or
                        old_hover.point_index != self.segment_hover.point_index or
                        abs(old_hover.t_param - self.segment_hover.t_param) > 0.05):
                        return True
            else:
                # Clear segment hover when over a point/handle
                if self.segment_hover is not None:
                    self.segment_hover = None
                    return True

        if not self.state.dragging or not self.state.drag_start or not self.state.drag_element:
            return self.segment_hover is not None or self.band_hover is not None
        
        delta = pos - self.state.drag_start
        hit = self.state.drag_element
        
        if not self.state.current_shape:
            return False
        
        path = self.state.current_shape.paths[hit.path_index]
        point = path.points[hit.point_index]
        
        if hit.element_type == 'anchor':
            # Move all selected points
            self._move_selected_points(delta)
        
        elif hit.element_type in ('handle_in', 'handle_out'):
            # Move all selected handles by the same delta
            constrained_delta = delta
            # Skip axis constraint during Shift+click convert drag
            if (self.state.shift_held and not self.state.alt_held
                    and not getattr(self, '_convert_drag_active', False)
                    and not getattr(self, '_asymmetric_handle_drag', False)):
                if abs(delta.x()) > abs(delta.y()):
                    constrained_delta = QtCore.QPointF(delta.x(), 0)
                else:
                    constrained_delta = QtCore.QPointF(0, delta.y())

            # Collect all handles to move: from selected_points (same handle type)
            # and from independently selected handles
            handles_to_move = set()

            # Handles from selected points (move matching handle type)
            handle_key = hit.element_type
            for sel_path_idx, sel_point_idx in self.state.selected_points:
                handles_to_move.add((sel_path_idx, sel_point_idx, handle_key))

            # Independently selected handles
            for h_path, h_point, h_type in self.state.selected_handles:
                handles_to_move.add((h_path, h_point, h_type))

            # Always include the dragged handle itself
            handles_to_move.add((hit.path_index, hit.point_index, hit.element_type))

            for sel_path_idx, sel_point_idx, sel_handle_type in handles_to_move:
                original = self.state.drag_original_positions.get((sel_handle_type, sel_path_idx, sel_point_idx))
                if not original:
                    continue
                if sel_path_idx >= len(self.state.current_shape.paths):
                    continue
                sel_path = self.state.current_shape.paths[sel_path_idx]
                if sel_point_idx >= len(sel_path.points):
                    continue
                sel_point = sel_path.points[sel_point_idx]

                new_pos = original + constrained_delta

                if self.state.alt_held:
                    sel_point.point_type = PointType.CORNER
                    if sel_handle_type == 'handle_in':
                        sel_point.handle_in = new_pos - sel_point.position
                    else:
                        sel_point.handle_out = new_pos - sel_point.position
                else:
                    if sel_handle_type == 'handle_in':
                        sel_point.set_handle_in_absolute(new_pos)
                    else:
                        sel_point.set_handle_out_absolute(new_pos)

        # Sync mirror side after handle/point edit
        if self.state.mirror_state.enabled and (hit.element_type in ('handle_in', 'handle_out', 'anchor')):
            # Collect all affected paths
            affected_paths = {hit.path_index}
            for sel_path_idx, _ in self.state.selected_points:
                affected_paths.add(sel_path_idx)
            for sel_path_idx, _, _ in self.state.selected_handles:
                affected_paths.add(sel_path_idx)
            for ap_idx in affected_paths:
                if ap_idx < len(self.state.current_shape.paths):
                    rebuild_mirror_side(
                        self.state.current_shape.paths[ap_idx],
                        self.state.mirror_map, ap_idx,
                        self.state.mirror_state.axis,
                        self.state.mirror_state.line_position
                    )

        return True
    
    def on_mouse_release(self, pos: QtCore.QPointF, modifiers: QtCore.Qt.KeyboardModifiers) -> bool:
        """Handle mouse release to end drag."""
        was_dragging = self.state.dragging

        # If this was a Shift+click convert drag, switch from SYMMETRIC to SMOOTH
        if getattr(self, '_convert_drag_active', False) and self.state.drag_element:
            hit = self.state.drag_element
            if self.state.current_shape and hit.path_index < len(self.state.current_shape.paths):
                path = self.state.current_shape.paths[hit.path_index]
                if hit.point_index < len(path.points):
                    path.points[hit.point_index].point_type = PointType.SMOOTH
            self._convert_drag_active = False

        # Asymmetric handle drag: leave point_type as CORNER so the single-side edit persists
        if getattr(self, '_asymmetric_handle_drag', False):
            self._asymmetric_handle_drag = False

        self.state.dragging = False
        self.state.drag_start = None
        self.state.drag_element = None
        self.state.drag_original_positions.clear()

        return was_dragging

    def on_key_press(self, key: int, modifiers: QtCore.Qt.KeyboardModifiers) -> bool:
        """
        Handle key press for deletion and type conversion.
        
        Returns:
            True if event was handled
        """
        self.state.update_modifiers(modifiers)
        
        # Delete selected points
        if key in (QtCore.Qt.Key_Delete, QtCore.Qt.Key_Backspace):
            return self._delete_selected_points()
        
        # Point type conversion
        if key == QtCore.Qt.Key_1:
            return self._convert_selected_to_type(PointType.CORNER)
        if key == QtCore.Qt.Key_2:
            return self._convert_selected_to_type(PointType.SMOOTH)
        if key == QtCore.Qt.Key_3:
            return self._convert_selected_to_type(PointType.SYMMETRIC)
        
        # Select all
        if key == QtCore.Qt.Key_A and self.state.ctrl_held:
            return self._select_all_points()
        
        return False
    
    def _store_original_positions(self):
        """Store original positions of selected points/handles for drag operations."""
        self.state.drag_original_positions.clear()

        if not self.state.current_shape:
            return

        # Store positions for selected anchor points and their handles
        for path_idx, point_idx in self.state.selected_points:
            if path_idx < len(self.state.current_shape.paths):
                path = self.state.current_shape.paths[path_idx]
                if point_idx < len(path.points):
                    point = path.points[point_idx]

                    # Store anchor position
                    key = ('anchor', path_idx, point_idx)
                    self.state.drag_original_positions[key] = QtCore.QPointF(point.position)

                    # Store handle positions (absolute)
                    if point.handle_in:
                        key = ('handle_in', path_idx, point_idx)
                        self.state.drag_original_positions[key] = point.get_handle_in_absolute()

                    if point.handle_out:
                        key = ('handle_out', path_idx, point_idx)
                        self.state.drag_original_positions[key] = point.get_handle_out_absolute()

        # Store positions for independently selected handles
        for path_idx, point_idx, handle_type in self.state.selected_handles:
            if path_idx < len(self.state.current_shape.paths):
                path = self.state.current_shape.paths[path_idx]
                if point_idx < len(path.points):
                    point = path.points[point_idx]
                    key = (handle_type, path_idx, point_idx)
                    if key not in self.state.drag_original_positions:
                        if handle_type == 'handle_in' and point.handle_in:
                            self.state.drag_original_positions[key] = point.get_handle_in_absolute()
                        elif handle_type == 'handle_out' and point.handle_out:
                            self.state.drag_original_positions[key] = point.get_handle_out_absolute()
                        # Also store anchor for reference
                        anchor_key = ('anchor', path_idx, point_idx)
                        if anchor_key not in self.state.drag_original_positions:
                            self.state.drag_original_positions[anchor_key] = QtCore.QPointF(point.position)
    
    def _move_selected_points(self, delta: QtCore.QPointF):
        """Move all selected points by delta, with optional axis constraint."""
        if not self.state.current_shape:
            return

        # Apply axis constraint if Shift is held
        if self.state.shift_held:
            if abs(delta.x()) > abs(delta.y()):
                delta = QtCore.QPointF(delta.x(), 0)
            else:
                delta = QtCore.QPointF(0, delta.y())

        affected_paths = set()
        for path_idx, point_idx in self.state.selected_points:
            original_key = ('anchor', path_idx, point_idx)
            original_pos = self.state.drag_original_positions.get(original_key)

            if original_pos and path_idx < len(self.state.current_shape.paths):
                path = self.state.current_shape.paths[path_idx]
                if point_idx < len(path.points):
                    path.points[point_idx].position = original_pos + delta
                    affected_paths.add(path_idx)

        # Sync mirror side for affected paths
        if self.state.mirror_state.enabled:
            for path_idx in affected_paths:
                if path_idx < len(self.state.current_shape.paths):
                    rebuild_mirror_side(
                        self.state.current_shape.paths[path_idx],
                        self.state.mirror_map, path_idx,
                        self.state.mirror_state.axis,
                        self.state.mirror_state.line_position
                    )
    
    def _delete_selected_points(self) -> bool:
        """Delete all selected points."""
        if not self.state.has_selection() or not self.state.current_shape:
            return False

        # If mirror is active, expand selection to include mirror partners
        if self.state.mirror_state.enabled:
            expanded = set(self.state.selected_points)
            for path_idx, point_idx in list(expanded):
                partner = self.state.mirror_map.get_partner(path_idx, point_idx)
                if partner:
                    expanded.add(partner)
            sorted_selection = sorted(expanded, reverse=True)
        else:
            sorted_selection = sorted(self.state.selected_points, reverse=True)

        for path_idx, point_idx in sorted_selection:
            if path_idx < len(self.state.current_shape.paths):
                path = self.state.current_shape.paths[path_idx]
                if point_idx < len(path.points):
                    path.remove_point(point_idx)

                # Remove empty paths
                if path.point_count() < 2:
                    self.state.current_shape.remove_path(path_idx)
        
        self.state.clear_selection()
        return True

    def _merge_selected_points(self) -> bool:
        """Merge selected points within each path into a single averaged point.

        Per path, the earliest-indexed selected point is kept and moved to the
        average position of all selected points in that path. Its handle_in is
        preserved; handle_out is inherited from the latest-indexed selected
        point to keep curve continuity across the merged span. All other
        selected points in the path are removed.
        """
        if not self.state.current_shape:
            return False
        if len(self.state.selected_points) < 2:
            return False

        # Group selection by path
        by_path: dict = {}
        for path_idx, point_idx in self.state.selected_points:
            by_path.setdefault(path_idx, []).append(point_idx)

        # Must have at least one path with 2+ selected points
        if not any(len(v) >= 2 for v in by_path.values()):
            return False

        new_selection: List[Tuple[int, int]] = []

        # Process paths from highest index to lowest so removals don't shift
        for path_idx in sorted(by_path.keys(), reverse=True):
            if path_idx >= len(self.state.current_shape.paths):
                continue
            path = self.state.current_shape.paths[path_idx]
            indices = sorted(set(i for i in by_path[path_idx] if 0 <= i < len(path.points)))
            if len(indices) < 2:
                if indices:
                    new_selection.append((path_idx, indices[0]))
                continue

            first_idx = indices[0]
            last_idx = indices[-1]
            first_pt = path.points[first_idx]
            last_pt = path.points[last_idx]

            # Average position
            sx = sum(path.points[i].position.x() for i in indices)
            sy = sum(path.points[i].position.y() for i in indices)
            avg = QtCore.QPointF(sx / len(indices), sy / len(indices))

            # Preserve handle_in from first, handle_out from last (relative to
            # original anchors, so translate them into offsets from new anchor).
            new_handle_in = None
            new_handle_out = None
            if first_pt.handle_in is not None:
                abs_in = first_pt.get_handle_in_absolute()
                new_handle_in = abs_in - avg
            if last_pt.handle_out is not None:
                abs_out = last_pt.get_handle_out_absolute()
                new_handle_out = abs_out - avg

            first_pt.position = avg
            first_pt.handle_in = new_handle_in
            first_pt.handle_out = new_handle_out

            # Remove other selected points (descending) — indices after
            # first_idx shift down by 1 per removal, but we remove them in
            # descending order so earlier indices stay valid.
            for i in reversed(indices[1:]):
                path.remove_point(i)

            if path.point_count() < 2:
                self.state.current_shape.remove_path(path_idx)
            else:
                new_selection.append((path_idx, first_idx))

        # Rebuild mirror side if enabled
        if self.state.mirror_state.enabled:
            for path_idx in range(len(self.state.current_shape.paths)):
                rebuild_mirror_side(
                    self.state.current_shape.paths[path_idx],
                    self.state.mirror_map, path_idx,
                    self.state.mirror_state.axis,
                    self.state.mirror_state.line_position
                )

        self.state.clear_selection()
        for key in new_selection:
            self.state.selected_points.append(key)

        return True

    def _convert_selected_to_type(self, point_type: PointType) -> bool:
        """Convert all selected points to the specified type."""
        if not self.state.has_selection() or not self.state.current_shape:
            return False
        
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
        
        return True
    
    def _select_all_points(self) -> bool:
        """Select all points in the shape."""
        if not self.state.current_shape:
            return False
        
        self.state.clear_selection()
        
        for path_idx, path in enumerate(self.state.current_shape.paths):
            for point_idx in range(len(path.points)):
                self.state.select_point(path_idx, point_idx, add_to_selection=True)
        
        return True
    
    def _distance(self, p1: QtCore.QPointF, p2: QtCore.QPointF) -> float:
        """Calculate distance between two points."""
        diff = p1 - p2
        return math.sqrt(diff.x() ** 2 + diff.y() ** 2)


class PenTool:
    """
    Pen tool for drawing new paths point by point.
    
    Features:
    - Click to add corner point
    - Click+drag to add smooth point with handles
    - Ctrl+click to force corner point (no handles even with drag)
    - Shift+drag constrains handles to 45° angles
    - Click on start point to close path
    - Enter/Escape to finish/cancel
    """
    
    HIT_RADIUS = 10  # Pixels for detecting click on start point
    
    def __init__(self, state: CurveEditorState):
        self.state = state
        self.current_path: Optional[CurvePath] = None
        self.is_dragging_handle: bool = False
        self.is_dragging_point: bool = False  # Track point position dragging
        self._force_corner: bool = False  # When Ctrl is held, force corner point
        self._is_continuing_path: bool = False  # Track if continuing existing path
    
    def on_mouse_press(self, pos: QtCore.QPointF, modifiers: QtCore.Qt.KeyboardModifiers,
                       scale: float = 1.0) -> bool:
        """
        Handle mouse press to add points.
        
        Modifiers:
        - Ctrl+click: Force corner point (no handles)
        - Regular click+drag: Create smooth point with handles
        - Shift while dragging: Constrain handles to 45° angles
        
        Returns:
            True if event was handled
        """
        self.state.update_modifiers(modifiers)
        
        # Check if clicking on start point to close path
        if self.current_path and len(self.current_path.points) > 2:
            first_point = self.current_path.points[0]
            close_radius = self.HIT_RADIUS / scale
            
            if self._distance(pos, first_point.position) < close_radius:
                self._close_and_finish_path()
                return True
        
        # Start new path if needed
        if self.current_path is None:
            # Check if we should continue from a selected point
            if self._try_continue_from_selection():
                # Successfully continuing from selected point
                self.state.is_drawing = True
                self._is_continuing_path = True
            else:
                # Start a brand new path
                self.current_path = CurvePath()
                self.state.is_drawing = True
                self._is_continuing_path = False
        
        # Determine point type based on modifier
        # Ctrl+click forces corner point immediately
        if self.state.ctrl_held:
            new_point = CurvePoint(
                position=QtCore.QPointF(pos),
                point_type=PointType.CORNER
            )
            self.current_path.add_point(new_point)
            self.is_dragging_handle = False
            self.state.drag_start = None  # No handle drag for corner points
            self._force_corner = True
        else:
            new_point = CurvePoint(
                position=QtCore.QPointF(pos),
                point_type=PointType.SMOOTH  # Will become CORNER if no drag
            )
            self.current_path.add_point(new_point)
            # Start both point dragging AND handle creation
            self.state.drag_start = QtCore.QPointF(pos)
            self.is_dragging_handle = False
            self.is_dragging_point = True  # Enable point position dragging
            self._force_corner = False
        
        return True
    
    def on_mouse_move(self, pos: QtCore.QPointF, modifiers: QtCore.Qt.KeyboardModifiers) -> bool:
        """
        Handle mouse move during point placement.
        
        Returns:
            True if event was handled
        """
        self.state.update_modifiers(modifiers)
        
        # Update preview point for visualization
        self.state.preview_point = QtCore.QPointF(pos)
        
        # Skip handle creation if Ctrl was held (force corner)
        if self._force_corner:
            return self.state.is_drawing
        
        # If we're creating a point and dragging, move point first then create handles
        if self.state.drag_start and self.current_path and self.current_path.points:
            last_point = self.current_path.points[-1]
            
            # Calculate drag distance from original click position
            delta = pos - self.state.drag_start
            distance = math.sqrt(delta.x() ** 2 + delta.y() ** 2)
            
            # First phase: drag to position the point (small movement)
            if self.is_dragging_point and distance > 3:
                # Move the point to new position
                last_point.position = QtCore.QPointF(pos)
                self.state.drag_start = QtCore.QPointF(pos)  # Update drag start for handle phase
                self.is_dragging_point = False  # Switch to handle mode
            
            # Second phase: drag to create handles (after point is positioned or immediately)
            elif not self.is_dragging_point and distance > 3:
                self.is_dragging_handle = True
                
                # Calculate handle_out from current position
                handle_out = pos - last_point.position
                
                # Apply shift constraint (45° angles)
                if self.state.shift_held:
                    handle_out = self._constrain_to_45(handle_out)
                
                # Set both handles (symmetric for new points)
                last_point.handle_out = handle_out
                last_point.handle_in = QtCore.QPointF(-handle_out.x(), -handle_out.y())
                last_point.point_type = PointType.SYMMETRIC
                
                self.state.preview_handle = last_point.get_handle_out_absolute()
        
        return self.state.is_drawing
    
    def on_mouse_release(self, pos: QtCore.QPointF, modifiers: QtCore.Qt.KeyboardModifiers) -> bool:
        """Handle mouse release after point placement."""
        # If we didn't drag (or force corner), make it a corner point
        if self.current_path and self.current_path.points and (not self.is_dragging_handle or self._force_corner):
            last_point = self.current_path.points[-1]
            last_point.point_type = PointType.CORNER
            last_point.handle_in = None
            last_point.handle_out = None
        
        self.state.drag_start = None
        self.state.preview_handle = None
        self.is_dragging_handle = False
        self.is_dragging_point = False
        self._force_corner = False
        
        return self.state.is_drawing
    
    def on_key_press(self, key: int, modifiers: QtCore.Qt.KeyboardModifiers) -> bool:
        """
        Handle key press for path operations.
        
        Returns:
            True if event was handled
        """
        self.state.update_modifiers(modifiers)
        
        if key == QtCore.Qt.Key_Escape:
            self._cancel_path()
            return True
        
        if key in (QtCore.Qt.Key_Return, QtCore.Qt.Key_Enter):
            self._finish_path()
            return True
        
        # Backspace to remove last point
        if key == QtCore.Qt.Key_Backspace and self.current_path:
            if self.current_path.point_count() > 0:
                self.current_path.remove_point(self.current_path.point_count() - 1)
                if self.current_path.point_count() == 0:
                    self._cancel_path()
                return True
        
        return False
    
    def _close_and_finish_path(self):
        """Close the current path and finish drawing."""
        if self.current_path:
            self.current_path.close_path()
            self._finish_path()
    
    def _finish_path(self):
        """Finish the current path and add it to the shape."""
        if self.current_path and self.current_path.point_count() >= 2:
            # Only add the path if it's a new path, not a continuation
            if not self._is_continuing_path:
                if self.state.current_shape is None:
                    self.state.current_shape = ButtonShape()

                # Apply mirror symmetrization if active
                if self.state.mirror_state.enabled:
                    from .curve_mirror import symmetrize_path, create_mirrored_path_copy, MirrorPointInfo
                    new_path_idx = len(self.state.current_shape.paths)
                    sym_path, path_map = symmetrize_path(
                        self.current_path, new_path_idx,
                        self.state.mirror_state.axis,
                        self.state.mirror_state.line_position,
                        self.state.mirror_state.CENTER_SNAP_TOLERANCE
                    )
                    self.state.current_shape.add_path(sym_path)
                    # Merge into state mirror map
                    for key, info in path_map._map.items():
                        if info.partner_key:
                            info.partner_key = (new_path_idx, info.partner_key[1])
                        self.state.mirror_map.set(new_path_idx, key[1], info)

                    # For open paths without mirror entries, create a mirrored copy
                    if not self.current_path.is_closed:
                        has_mirrors = any(
                            self.state.mirror_map.is_mirror(new_path_idx, i)
                            for i in range(len(sym_path.points))
                        )
                        if not has_mirrors:
                            mirror_copy = create_mirrored_path_copy(
                                sym_path,
                                self.state.mirror_state.axis,
                                self.state.mirror_state.line_position
                            )
                            mirror_idx = len(self.state.current_shape.paths)
                            self.state.current_shape.add_path(mirror_copy)
                            for i in range(len(sym_path.points)):
                                mp_idx = len(mirror_copy.points) - 1 - i
                                self.state.mirror_map.set(
                                    mirror_idx, mp_idx,
                                    MirrorPointInfo(PointRole.MIRROR, partner_key=(new_path_idx, i))
                                )
                                src_info = self.state.mirror_map.get(new_path_idx, i)
                                if src_info:
                                    src_info.partner_key = (mirror_idx, mp_idx)
                else:
                    self.state.current_shape.add_path(self.current_path)
            # If continuing, the path is already in the shape, no need to add it

        self._reset_drawing_state()
    
    def _cancel_path(self):
        """Cancel the current path without saving."""
        self._reset_drawing_state()
    
    def _reset_drawing_state(self):
        """Reset all drawing state."""
        self.current_path = None
        self.is_dragging_handle = False
        self.is_dragging_point = False
        self._force_corner = False
        self._is_continuing_path = False
        self.state.is_drawing = False
        self.state.drag_start = None
        self.state.preview_point = None
        self.state.preview_handle = None
    
    def has_active_path(self) -> bool:
        """Check if there's a path being drawn."""
        return self.current_path is not None and self.current_path.point_count() > 0
    
    def get_preview_path(self) -> Optional[CurvePath]:
        """Get the current path being drawn for preview rendering."""
        return self.current_path
    
    def _constrain_to_45(self, vec: QtCore.QPointF) -> QtCore.QPointF:
        """Constrain vector to 45 degree increments."""
        angle = math.atan2(vec.y(), vec.x())
        length = math.sqrt(vec.x() ** 2 + vec.y() ** 2)
        
        # Snap to nearest 45 degrees (π/4 radians)
        snapped_angle = round(angle / (math.pi / 4)) * (math.pi / 4)
        
        return QtCore.QPointF(
            length * math.cos(snapped_angle),
            length * math.sin(snapped_angle)
        )
    
    def _distance(self, p1: QtCore.QPointF, p2: QtCore.QPointF) -> float:
        """Calculate distance between two points."""
        diff = p1 - p2
        return math.sqrt(diff.x() ** 2 + diff.y() ** 2)
    
    def _try_continue_from_selection(self) -> bool:
        """
        Try to continue drawing from a selected point.
        
        Returns True if we found a valid point to continue from,
        False if we should start a new path.
        """
        # Need exactly one point selected
        if not self.state.has_selection() or len(self.state.selected_points) != 1:
            return False
        
        if not self.state.current_shape:
            return False
        
        path_idx, point_idx = self.state.selected_points[0]
        
        # Validate indices
        if path_idx >= len(self.state.current_shape.paths):
            return False
        
        path = self.state.current_shape.paths[path_idx]
        
        if point_idx >= len(path.points):
            return False
        
        # Don't continue if path is closed
        if path.is_closed:
            return False
        
        # Can only continue from first or last point
        if point_idx == 0:
            # Continue from start - reverse the path so we're adding to the end
            path.reverse()
            self.current_path = path
            return True
        elif point_idx == len(path.points) - 1:
            # Continue from end - perfect, just use the path
            self.current_path = path
            return True
        
        # Selected point is in the middle - can't continue from there
        return False


class RectangleTool:
    """
    Tool for drawing rectangular shapes.
    
    Features:
    - Click+drag to draw rectangle
    - Shift constrains to square
    - Alt draws from center
    """
    
    def __init__(self, state: CurveEditorState):
        self.state = state
        self.start_pos: Optional[QtCore.QPointF] = None
        self.current_rect: Optional[QtCore.QRectF] = None
    
    def on_mouse_press(self, pos: QtCore.QPointF, modifiers: QtCore.Qt.KeyboardModifiers) -> bool:
        """Start drawing rectangle."""
        self.state.update_modifiers(modifiers)
        self.start_pos = QtCore.QPointF(pos)
        self.current_rect = QtCore.QRectF(pos, pos)
        self.state.is_drawing = True
        return True
    
    def on_mouse_move(self, pos: QtCore.QPointF, modifiers: QtCore.Qt.KeyboardModifiers) -> bool:
        """Update rectangle during drag."""
        if not self.start_pos:
            return False
        
        self.state.update_modifiers(modifiers)
        
        # Calculate rectangle
        x1, y1 = self.start_pos.x(), self.start_pos.y()
        x2, y2 = pos.x(), pos.y()
        
        # Shift constrains to square
        if self.state.shift_held:
            size = max(abs(x2 - x1), abs(y2 - y1))
            x2 = x1 + size * (1 if x2 > x1 else -1)
            y2 = y1 + size * (1 if y2 > y1 else -1)
        
        # Alt draws from center
        if self.state.alt_held:
            half_w = abs(x2 - x1)
            half_h = abs(y2 - y1)
            x1, y1 = self.start_pos.x() - half_w, self.start_pos.y() - half_h
            x2, y2 = self.start_pos.x() + half_w, self.start_pos.y() + half_h
        
        self.current_rect = QtCore.QRectF(
            QtCore.QPointF(min(x1, x2), min(y1, y2)),
            QtCore.QPointF(max(x1, x2), max(y1, y2))
        )
        
        return True
    
    def on_mouse_release(self, pos: QtCore.QPointF, modifiers: QtCore.Qt.KeyboardModifiers) -> bool:
        """Finish drawing and create path."""
        if not self.current_rect or self.current_rect.isEmpty():
            self._reset()
            return False

        # Create rectangular path
        path = self._create_rect_path(self.current_rect)

        if self.state.current_shape is None:
            self.state.current_shape = ButtonShape()

        # Apply mirror if active
        if self.state.mirror_state.enabled:
            from .curve_mirror import symmetrize_path
            new_idx = len(self.state.current_shape.paths)
            sym_path, path_map = symmetrize_path(
                path, new_idx,
                self.state.mirror_state.axis,
                self.state.mirror_state.line_position,
                self.state.mirror_state.CENTER_SNAP_TOLERANCE
            )
            self.state.current_shape.add_path(sym_path)
            for key, info in path_map._map.items():
                if info.partner_key:
                    info.partner_key = (new_idx, info.partner_key[1])
                self.state.mirror_map.set(new_idx, key[1], info)
        else:
            self.state.current_shape.add_path(path)

        self._reset()
        return True

    def _create_rect_path(self, rect: QtCore.QRectF) -> CurvePath:
        """Create a CurvePath from a rectangle."""
        path = CurvePath()
        
        # Four corners as corner points
        corners = [
            QtCore.QPointF(rect.left(), rect.top()),
            QtCore.QPointF(rect.right(), rect.top()),
            QtCore.QPointF(rect.right(), rect.bottom()),
            QtCore.QPointF(rect.left(), rect.bottom()),
        ]
        
        for corner in corners:
            path.add_point(CurvePoint(position=corner, point_type=PointType.CORNER))
        
        path.close_path()
        return path
    
    def _reset(self):
        """Reset tool state."""
        self.start_pos = None
        self.current_rect = None
        self.state.is_drawing = False
    
    def get_preview_rect(self) -> Optional[QtCore.QRectF]:
        """Get current rectangle for preview rendering."""
        return self.current_rect


class EllipseTool:
    """
    Tool for drawing elliptical shapes.
    
    Features:
    - Click+drag to draw ellipse
    - Shift constrains to circle
    - Alt draws from center
    """
    
    def __init__(self, state: CurveEditorState):
        self.state = state
        self.start_pos: Optional[QtCore.QPointF] = None
        self.current_rect: Optional[QtCore.QRectF] = None
    
    def on_mouse_press(self, pos: QtCore.QPointF, modifiers: QtCore.Qt.KeyboardModifiers) -> bool:
        """Start drawing ellipse."""
        self.state.update_modifiers(modifiers)
        self.start_pos = QtCore.QPointF(pos)
        self.current_rect = QtCore.QRectF(pos, pos)
        self.state.is_drawing = True
        return True
    
    def on_mouse_move(self, pos: QtCore.QPointF, modifiers: QtCore.Qt.KeyboardModifiers) -> bool:
        """Update ellipse during drag."""
        if not self.start_pos:
            return False
        
        self.state.update_modifiers(modifiers)
        
        x1, y1 = self.start_pos.x(), self.start_pos.y()
        x2, y2 = pos.x(), pos.y()
        
        # Shift constrains to circle
        if self.state.shift_held:
            size = max(abs(x2 - x1), abs(y2 - y1))
            x2 = x1 + size * (1 if x2 > x1 else -1)
            y2 = y1 + size * (1 if y2 > y1 else -1)
        
        # Alt draws from center
        if self.state.alt_held:
            half_w = abs(x2 - x1)
            half_h = abs(y2 - y1)
            x1, y1 = self.start_pos.x() - half_w, self.start_pos.y() - half_h
            x2, y2 = self.start_pos.x() + half_w, self.start_pos.y() + half_h
        
        self.current_rect = QtCore.QRectF(
            QtCore.QPointF(min(x1, x2), min(y1, y2)),
            QtCore.QPointF(max(x1, x2), max(y1, y2))
        )
        
        return True
    
    def on_mouse_release(self, pos: QtCore.QPointF, modifiers: QtCore.Qt.KeyboardModifiers) -> bool:
        """Finish drawing and create path."""
        if not self.current_rect or self.current_rect.isEmpty():
            self._reset()
            return False

        # Create elliptical path
        path = self._create_ellipse_path(self.current_rect)

        if self.state.current_shape is None:
            self.state.current_shape = ButtonShape()

        # Apply mirror if active
        if self.state.mirror_state.enabled:
            from .curve_mirror import symmetrize_path
            new_idx = len(self.state.current_shape.paths)
            sym_path, path_map = symmetrize_path(
                path, new_idx,
                self.state.mirror_state.axis,
                self.state.mirror_state.line_position,
                self.state.mirror_state.CENTER_SNAP_TOLERANCE
            )
            self.state.current_shape.add_path(sym_path)
            for key, info in path_map._map.items():
                if info.partner_key:
                    info.partner_key = (new_idx, info.partner_key[1])
                self.state.mirror_map.set(new_idx, key[1], info)
        else:
            self.state.current_shape.add_path(path)

        self._reset()
        return True
    
    def _create_ellipse_path(self, rect: QtCore.QRectF) -> CurvePath:
        """
        Create a CurvePath ellipse using 4 bezier curves.
        
        Uses the standard ellipse approximation constant (4/3 * tan(π/8) ≈ 0.5523)
        for accurate circular arcs.
        """
        path = CurvePath()
        
        # Ellipse parameters
        cx, cy = rect.center().x(), rect.center().y()
        rx, ry = rect.width() / 2, rect.height() / 2
        
        # Magic number for bezier approximation of quarter circle
        k = 0.5522847498  # 4/3 * tan(π/8)
        
        # Four cardinal points with bezier handles
        # Right point (0°)
        right = CurvePoint(
            position=QtCore.QPointF(cx + rx, cy),
            handle_in=QtCore.QPointF(0, ry * k),
            handle_out=QtCore.QPointF(0, -ry * k),
            point_type=PointType.SMOOTH
        )
        
        # Top point (90°)
        top = CurvePoint(
            position=QtCore.QPointF(cx, cy - ry),
            handle_in=QtCore.QPointF(rx * k, 0),
            handle_out=QtCore.QPointF(-rx * k, 0),
            point_type=PointType.SMOOTH
        )
        
        # Left point (180°)
        left = CurvePoint(
            position=QtCore.QPointF(cx - rx, cy),
            handle_in=QtCore.QPointF(0, -ry * k),
            handle_out=QtCore.QPointF(0, ry * k),
            point_type=PointType.SMOOTH
        )
        
        # Bottom point (270°)
        bottom = CurvePoint(
            position=QtCore.QPointF(cx, cy + ry),
            handle_in=QtCore.QPointF(-rx * k, 0),
            handle_out=QtCore.QPointF(rx * k, 0),
            point_type=PointType.SMOOTH
        )
        
        path.add_point(right)
        path.add_point(top)
        path.add_point(left)
        path.add_point(bottom)
        path.close_path()
        
        return path
    
    def _reset(self):
        """Reset tool state."""
        self.start_pos = None
        self.current_rect = None
        self.state.is_drawing = False
    
    def get_preview_rect(self) -> Optional[QtCore.QRectF]:
        """Get current rectangle for preview rendering."""
        return self.current_rect
