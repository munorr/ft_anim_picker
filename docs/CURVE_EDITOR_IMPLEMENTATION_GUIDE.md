# Curve Editor Technical Implementation Guide

## Overview

This document provides detailed technical specifications for implementing the curve/shape editor feature in the FT Anim Picker. The design follows the existing UI patterns established by `TransformControlsWidget` and `TransformGuides`.

---

## 1. Core Data Classes

### curve_data.py

```python
from PySide6 import QtCore, QtGui
from dataclasses import dataclass, field
from typing import List, Optional, Tuple
from enum import Enum
import re

class PointType(Enum):
    CORNER = "corner"       # Sharp corner, independent handles
    SMOOTH = "smooth"       # Smooth, handles are colinear but can have different lengths
    SYMMETRIC = "symmetric" # Handles are mirrored (same length and opposite direction)


@dataclass
class CurvePoint:
    """Represents a single anchor point on a curve with optional bezier handles."""
    
    position: QtCore.QPointF
    handle_in: Optional[QtCore.QPointF] = None   # Relative to position
    handle_out: Optional[QtCore.QPointF] = None  # Relative to position
    point_type: PointType = PointType.CORNER
    
    def get_handle_in_absolute(self) -> QtCore.QPointF:
        """Get incoming handle in absolute coordinates."""
        if self.handle_in is None:
            return self.position
        return self.position + self.handle_in
    
    def get_handle_out_absolute(self) -> QtCore.QPointF:
        """Get outgoing handle in absolute coordinates."""
        if self.handle_out is None:
            return self.position
        return self.position + self.handle_out
    
    def set_handle_in_absolute(self, pos: QtCore.QPointF):
        """Set incoming handle from absolute coordinates."""
        self.handle_in = pos - self.position
        self._apply_point_type_constraint('in')
    
    def set_handle_out_absolute(self, pos: QtCore.QPointF):
        """Set outgoing handle from absolute coordinates."""
        self.handle_out = pos - self.position
        self._apply_point_type_constraint('out')
    
    def _apply_point_type_constraint(self, changed_handle: str):
        """Apply constraints based on point type after handle modification."""
        if self.point_type == PointType.CORNER:
            return  # No constraints
        
        if changed_handle == 'out' and self.handle_out and self.handle_in:
            if self.point_type == PointType.SYMMETRIC:
                # Mirror handle: same length, opposite direction
                self.handle_in = QtCore.QPointF(-self.handle_out.x(), -self.handle_out.y())
            elif self.point_type == PointType.SMOOTH:
                # Colinear: same direction, preserve length
                length = (self.handle_in.x()**2 + self.handle_in.y()**2)**0.5
                out_length = (self.handle_out.x()**2 + self.handle_out.y()**2)**0.5
                if out_length > 0:
                    scale = length / out_length
                    self.handle_in = QtCore.QPointF(
                        -self.handle_out.x() * scale,
                        -self.handle_out.y() * scale
                    )
        
        elif changed_handle == 'in' and self.handle_in and self.handle_out:
            if self.point_type == PointType.SYMMETRIC:
                self.handle_out = QtCore.QPointF(-self.handle_in.x(), -self.handle_in.y())
            elif self.point_type == PointType.SMOOTH:
                length = (self.handle_out.x()**2 + self.handle_out.y()**2)**0.5
                in_length = (self.handle_in.x()**2 + self.handle_in.y()**2)**0.5
                if in_length > 0:
                    scale = length / in_length
                    self.handle_out = QtCore.QPointF(
                        -self.handle_in.x() * scale,
                        -self.handle_in.y() * scale
                    )
    
    def has_handles(self) -> bool:
        """Check if this point has any bezier handles."""
        return self.handle_in is not None or self.handle_out is not None
    
    def convert_to_corner(self):
        """Convert point to corner type (preserve handles but break constraint)."""
        self.point_type = PointType.CORNER
    
    def convert_to_smooth(self):
        """Convert point to smooth type (make handles colinear)."""
        self.point_type = PointType.SMOOTH
        if self.handle_out:
            self._apply_point_type_constraint('out')
    
    def convert_to_symmetric(self):
        """Convert point to symmetric type (mirror handles)."""
        self.point_type = PointType.SYMMETRIC
        if self.handle_out:
            self._apply_point_type_constraint('out')


@dataclass
class CurvePath:
    """Represents a single path (series of connected points)."""
    
    points: List[CurvePoint] = field(default_factory=list)
    is_closed: bool = False
    
    def add_point(self, point: CurvePoint, index: Optional[int] = None):
        """Add a point to the path."""
        if index is None:
            self.points.append(point)
        else:
            self.points.insert(index, point)
    
    def remove_point(self, index: int):
        """Remove a point from the path."""
        if 0 <= index < len(self.points):
            self.points.pop(index)
    
    def close_path(self):
        """Close the path."""
        self.is_closed = True
    
    def open_path(self):
        """Open the path."""
        self.is_closed = False
    
    def get_bounding_rect(self) -> QtCore.QRectF:
        """Calculate bounding rectangle of the path."""
        if not self.points:
            return QtCore.QRectF()
        
        min_x = min_y = float('inf')
        max_x = max_y = float('-inf')
        
        for point in self.points:
            # Include anchor point
            min_x = min(min_x, point.position.x())
            max_x = max(max_x, point.position.x())
            min_y = min(min_y, point.position.y())
            max_y = max(max_y, point.position.y())
            
            # Include handles
            if point.handle_in:
                h = point.get_handle_in_absolute()
                min_x = min(min_x, h.x())
                max_x = max(max_x, h.x())
                min_y = min(min_y, h.y())
                max_y = max(max_y, h.y())
            
            if point.handle_out:
                h = point.get_handle_out_absolute()
                min_x = min(min_x, h.x())
                max_x = max(max_x, h.x())
                min_y = min(min_y, h.y())
                max_y = max(max_y, h.y())
        
        return QtCore.QRectF(min_x, min_y, max_x - min_x, max_y - min_y)
    
    def to_qpainter_path(self) -> QtGui.QPainterPath:
        """Convert to QPainterPath for rendering."""
        path = QtGui.QPainterPath()
        
        if not self.points:
            return path
        
        # Move to first point
        path.moveTo(self.points[0].position)
        
        # Draw segments
        for i in range(1, len(self.points)):
            prev_point = self.points[i - 1]
            curr_point = self.points[i]
            
            # Determine if this is a curve or line
            has_ctrl1 = prev_point.handle_out is not None
            has_ctrl2 = curr_point.handle_in is not None
            
            if has_ctrl1 or has_ctrl2:
                # Cubic bezier
                ctrl1 = prev_point.get_handle_out_absolute() if has_ctrl1 else prev_point.position
                ctrl2 = curr_point.get_handle_in_absolute() if has_ctrl2 else curr_point.position
                path.cubicTo(ctrl1, ctrl2, curr_point.position)
            else:
                # Straight line
                path.lineTo(curr_point.position)
        
        # Close path if needed
        if self.is_closed and len(self.points) > 2:
            last_point = self.points[-1]
            first_point = self.points[0]
            
            has_ctrl1 = last_point.handle_out is not None
            has_ctrl2 = first_point.handle_in is not None
            
            if has_ctrl1 or has_ctrl2:
                ctrl1 = last_point.get_handle_out_absolute() if has_ctrl1 else last_point.position
                ctrl2 = first_point.get_handle_in_absolute() if has_ctrl2 else first_point.position
                path.cubicTo(ctrl1, ctrl2, first_point.position)
            
            path.closeSubpath()
        
        return path


@dataclass  
class ButtonShape:
    """Complete shape for a button, supporting compound paths."""
    
    paths: List[CurvePath] = field(default_factory=list)
    
    def add_path(self, path: CurvePath):
        """Add a new sub-path."""
        self.paths.append(path)
    
    def remove_path(self, index: int):
        """Remove a sub-path."""
        if 0 <= index < len(self.paths):
            self.paths.pop(index)
    
    def to_qpainter_path(self) -> QtGui.QPainterPath:
        """Combine all paths into single QPainterPath."""
        combined = QtGui.QPainterPath()
        for path in self.paths:
            combined.addPath(path.to_qpainter_path())
        return combined
    
    def to_svg_path_data(self) -> str:
        """Convert to SVG path data string."""
        segments = []
        
        for path in self.paths:
            if not path.points:
                continue
            
            # Move to first point
            p = path.points[0].position
            segments.append(f"M{p.x():.6g},{p.y():.6g}")
            
            # Draw segments
            for i in range(1, len(path.points)):
                prev = path.points[i - 1]
                curr = path.points[i]
                
                has_ctrl1 = prev.handle_out is not None
                has_ctrl2 = curr.handle_in is not None
                
                if has_ctrl1 or has_ctrl2:
                    c1 = prev.get_handle_out_absolute() if has_ctrl1 else prev.position
                    c2 = curr.get_handle_in_absolute() if has_ctrl2 else curr.position
                    segments.append(
                        f"C{c1.x():.6g},{c1.y():.6g},{c2.x():.6g},{c2.y():.6g},"
                        f"{curr.position.x():.6g},{curr.position.y():.6g}"
                    )
                else:
                    segments.append(f"L{curr.position.x():.6g},{curr.position.y():.6g}")
            
            # Close if needed
            if path.is_closed:
                last = path.points[-1]
                first = path.points[0]
                has_ctrl1 = last.handle_out is not None
                has_ctrl2 = first.handle_in is not None
                
                if has_ctrl1 or has_ctrl2:
                    c1 = last.get_handle_out_absolute() if has_ctrl1 else last.position
                    c2 = first.get_handle_in_absolute() if has_ctrl2 else first.position
                    segments.append(
                        f"C{c1.x():.6g},{c1.y():.6g},{c2.x():.6g},{c2.y():.6g},"
                        f"{first.position.x():.6g},{first.position.y():.6g}"
                    )
                segments.append("Z")
        
        return "".join(segments)
    
    @classmethod
    def from_svg_path_data(cls, svg_data: str) -> 'ButtonShape':
        """Parse SVG path data string into ButtonShape."""
        shape = cls()
        # ... parsing implementation (reuse logic from picker_button._parse_svg_path)
        return shape
```

---

## 2. Curve Editor Tools

### curve_tools.py

```python
from PySide6 import QtCore, QtGui, QtWidgets
from enum import Enum, auto
from typing import Optional, Tuple, List
from .curve_data import CurvePoint, CurvePath, ButtonShape, PointType


class EditorTool(Enum):
    NONE = auto()
    PEN = auto()
    NODE = auto()
    RECTANGLE = auto()
    ELLIPSE = auto()


class HitResult:
    """Result of hit testing on curve elements."""
    
    def __init__(self):
        self.path_index: int = -1
        self.point_index: int = -1
        self.element_type: str = None  # 'anchor', 'handle_in', 'handle_out', 'segment'
        self.distance: float = float('inf')
    
    def is_valid(self) -> bool:
        return self.path_index >= 0


class CurveEditorState:
    """Maintains the current state of the curve editor."""
    
    def __init__(self):
        self.active_tool: EditorTool = EditorTool.NODE
        self.current_shape: Optional[ButtonShape] = None
        self.selected_points: List[Tuple[int, int]] = []  # [(path_index, point_index), ...]
        self.is_drawing: bool = False
        self.preview_point: Optional[QtCore.QPointF] = None
        self.preview_handle: Optional[QtCore.QPointF] = None
        self.dragging: bool = False
        self.drag_start: Optional[QtCore.QPointF] = None
        self.drag_element: Optional[HitResult] = None
        
        # Modifier states
        self.shift_held: bool = False
        self.alt_held: bool = False
        self.ctrl_held: bool = False
    
    def clear_selection(self):
        self.selected_points.clear()
    
    def select_point(self, path_index: int, point_index: int, add_to_selection: bool = False):
        key = (path_index, point_index)
        if not add_to_selection:
            self.selected_points.clear()
        if key not in self.selected_points:
            self.selected_points.append(key)
    
    def deselect_point(self, path_index: int, point_index: int):
        key = (path_index, point_index)
        if key in self.selected_points:
            self.selected_points.remove(key)
    
    def is_point_selected(self, path_index: int, point_index: int) -> bool:
        return (path_index, point_index) in self.selected_points


class PenTool:
    """Pen tool for drawing new paths."""
    
    HIT_RADIUS = 8  # Pixels
    
    def __init__(self, state: CurveEditorState):
        self.state = state
        self.current_path: Optional[CurvePath] = None
    
    def on_mouse_press(self, pos: QtCore.QPointF, modifiers: QtCore.Qt.KeyboardModifiers) -> bool:
        """Handle mouse press. Returns True if event was handled."""
        
        if self.current_path is None:
            # Start new path
            self.current_path = CurvePath()
            self.state.is_drawing = True
        
        # Check if clicking on first point to close path
        if len(self.current_path.points) > 2:
            first_point = self.current_path.points[0]
            dist = self._distance(pos, first_point.position)
            if dist < self.HIT_RADIUS:
                self._close_and_finish_path()
                return True
        
        # Add new point
        point_type = PointType.SMOOTH if not (modifiers & QtCore.Qt.AltModifier) else PointType.CORNER
        new_point = CurvePoint(position=pos, point_type=point_type)
        self.current_path.add_point(new_point)
        
        # Start handle drag
        self.state.drag_start = pos
        return True
    
    def on_mouse_move(self, pos: QtCore.QPointF, modifiers: QtCore.Qt.KeyboardModifiers) -> bool:
        """Handle mouse move during drawing."""
        
        if not self.state.is_drawing or not self.current_path or not self.current_path.points:
            self.state.preview_point = pos
            return False
        
        # Update preview handle
        self.state.preview_point = pos
        
        # If dragging after point creation, update handles
        if self.state.drag_start:
            last_point = self.current_path.points[-1]
            
            # Calculate handle from drag
            handle_out = pos - last_point.position
            
            # Apply shift constraint (45 degree angles)
            if modifiers & QtCore.Qt.ShiftModifier:
                handle_out = self._constrain_to_45(handle_out)
            
            last_point.handle_out = handle_out
            
            # Set opposite handle for smooth/symmetric
            if last_point.point_type in (PointType.SMOOTH, PointType.SYMMETRIC):
                last_point.handle_in = QtCore.QPointF(-handle_out.x(), -handle_out.y())
            
            self.state.preview_handle = last_point.get_handle_out_absolute()
        
        return True
    
    def on_mouse_release(self, pos: QtCore.QPointF, modifiers: QtCore.Qt.KeyboardModifiers) -> bool:
        """Handle mouse release."""
        self.state.drag_start = None
        self.state.preview_handle = None
        return True
    
    def on_key_press(self, key: int, modifiers: QtCore.Qt.KeyboardModifiers) -> bool:
        """Handle key press. Returns True if event was handled."""
        
        if key == QtCore.Qt.Key_Escape:
            self._cancel_path()
            return True
        
        if key == QtCore.Qt.Key_Return or key == QtCore.Qt.Key_Enter:
            self._finish_path()
            return True
        
        return False
    
    def _close_and_finish_path(self):
        """Close the current path and finish."""
        if self.current_path:
            self.current_path.close_path()
            self._finish_path()
    
    def _finish_path(self):
        """Finish the current path."""
        if self.current_path and len(self.current_path.points) >= 2:
            if self.state.current_shape is None:
                self.state.current_shape = ButtonShape()
            self.state.current_shape.add_path(self.current_path)
        
        self.current_path = None
        self.state.is_drawing = False
        self.state.preview_point = None
        self.state.preview_handle = None
    
    def _cancel_path(self):
        """Cancel the current path."""
        self.current_path = None
        self.state.is_drawing = False
        self.state.preview_point = None
        self.state.preview_handle = None
    
    def _distance(self, p1: QtCore.QPointF, p2: QtCore.QPointF) -> float:
        diff = p1 - p2
        return (diff.x()**2 + diff.y()**2)**0.5
    
    def _constrain_to_45(self, vec: QtCore.QPointF) -> QtCore.QPointF:
        """Constrain vector to 45 degree increments."""
        import math
        angle = math.atan2(vec.y(), vec.x())
        length = (vec.x()**2 + vec.y()**2)**0.5
        
        # Snap to nearest 45 degrees
        snapped_angle = round(angle / (math.pi / 4)) * (math.pi / 4)
        
        return QtCore.QPointF(
            length * math.cos(snapped_angle),
            length * math.sin(snapped_angle)
        )


class NodeTool:
    """Node tool for selecting and editing existing points."""
    
    HIT_RADIUS = 8
    HANDLE_HIT_RADIUS = 6
    
    def __init__(self, state: CurveEditorState):
        self.state = state
    
    def hit_test(self, pos: QtCore.QPointF) -> HitResult:
        """Test what element is at the given position."""
        result = HitResult()
        
        if not self.state.current_shape:
            return result
        
        # Test points and handles
        for path_idx, path in enumerate(self.state.current_shape.paths):
            for point_idx, point in enumerate(path.points):
                
                # Test anchor point
                dist = self._distance(pos, point.position)
                if dist < self.HIT_RADIUS and dist < result.distance:
                    result.path_index = path_idx
                    result.point_index = point_idx
                    result.element_type = 'anchor'
                    result.distance = dist
                
                # Test handles (only for selected points)
                if self.state.is_point_selected(path_idx, point_idx):
                    if point.handle_in:
                        h_pos = point.get_handle_in_absolute()
                        dist = self._distance(pos, h_pos)
                        if dist < self.HANDLE_HIT_RADIUS and dist < result.distance:
                            result.path_index = path_idx
                            result.point_index = point_idx
                            result.element_type = 'handle_in'
                            result.distance = dist
                    
                    if point.handle_out:
                        h_pos = point.get_handle_out_absolute()
                        dist = self._distance(pos, h_pos)
                        if dist < self.HANDLE_HIT_RADIUS and dist < result.distance:
                            result.path_index = path_idx
                            result.point_index = point_idx
                            result.element_type = 'handle_out'
                            result.distance = dist
        
        return result
    
    def on_mouse_press(self, pos: QtCore.QPointF, modifiers: QtCore.Qt.KeyboardModifiers) -> bool:
        """Handle mouse press for selection and drag start."""
        
        hit = self.hit_test(pos)
        
        if hit.is_valid():
            add_to_selection = bool(modifiers & QtCore.Qt.ShiftModifier)
            
            if hit.element_type == 'anchor':
                # Select or toggle selection
                if add_to_selection:
                    if self.state.is_point_selected(hit.path_index, hit.point_index):
                        self.state.deselect_point(hit.path_index, hit.point_index)
                    else:
                        self.state.select_point(hit.path_index, hit.point_index, True)
                else:
                    self.state.select_point(hit.path_index, hit.point_index, False)
            
            # Start dragging
            self.state.dragging = True
            self.state.drag_start = pos
            self.state.drag_element = hit
            
            return True
        
        # Clicked on empty space - clear selection
        if not (modifiers & QtCore.Qt.ShiftModifier):
            self.state.clear_selection()
        
        return False
    
    def on_mouse_move(self, pos: QtCore.QPointF, modifiers: QtCore.Qt.KeyboardModifiers) -> bool:
        """Handle mouse move for dragging."""
        
        if not self.state.dragging or not self.state.drag_element:
            return False
        
        delta = pos - self.state.drag_start
        hit = self.state.drag_element
        
        path = self.state.current_shape.paths[hit.path_index]
        point = path.points[hit.point_index]
        
        if hit.element_type == 'anchor':
            # Move all selected points
            for path_idx, point_idx in self.state.selected_points:
                p = self.state.current_shape.paths[path_idx].points[point_idx]
                p.position = p.position + delta
        
        elif hit.element_type == 'handle_in':
            new_handle_pos = point.get_handle_in_absolute() + delta
            
            # Break handle symmetry if Alt is held
            if modifiers & QtCore.Qt.AltModifier:
                point.point_type = PointType.CORNER
            
            point.set_handle_in_absolute(new_handle_pos)
        
        elif hit.element_type == 'handle_out':
            new_handle_pos = point.get_handle_out_absolute() + delta
            
            if modifiers & QtCore.Qt.AltModifier:
                point.point_type = PointType.CORNER
            
            point.set_handle_out_absolute(new_handle_pos)
        
        self.state.drag_start = pos
        return True
    
    def on_mouse_release(self, pos: QtCore.QPointF, modifiers: QtCore.Qt.KeyboardModifiers) -> bool:
        """Handle mouse release to end drag."""
        self.state.dragging = False
        self.state.drag_start = None
        self.state.drag_element = None
        return True
    
    def on_key_press(self, key: int, modifiers: QtCore.Qt.KeyboardModifiers) -> bool:
        """Handle key press for deletion and conversion."""
        
        if key in (QtCore.Qt.Key_Delete, QtCore.Qt.Key_Backspace):
            return self._delete_selected_points()
        
        if key == QtCore.Qt.Key_1:
            return self._convert_selected_to_type(PointType.CORNER)
        
        if key == QtCore.Qt.Key_2:
            return self._convert_selected_to_type(PointType.SMOOTH)
        
        if key == QtCore.Qt.Key_3:
            return self._convert_selected_to_type(PointType.SYMMETRIC)
        
        return False
    
    def _delete_selected_points(self) -> bool:
        """Delete all selected points."""
        if not self.state.selected_points or not self.state.current_shape:
            return False
        
        # Sort by index descending to avoid index shifting issues
        sorted_selection = sorted(self.state.selected_points, reverse=True)
        
        for path_idx, point_idx in sorted_selection:
            if path_idx < len(self.state.current_shape.paths):
                path = self.state.current_shape.paths[path_idx]
                if point_idx < len(path.points):
                    path.remove_point(point_idx)
                
                # Remove empty paths
                if len(path.points) < 2:
                    self.state.current_shape.remove_path(path_idx)
        
        self.state.clear_selection()
        return True
    
    def _convert_selected_to_type(self, point_type: PointType) -> bool:
        """Convert selected points to the specified type."""
        if not self.state.selected_points or not self.state.current_shape:
            return False
        
        for path_idx, point_idx in self.state.selected_points:
            path = self.state.current_shape.paths[path_idx]
            point = path.points[point_idx]
            
            if point_type == PointType.CORNER:
                point.convert_to_corner()
            elif point_type == PointType.SMOOTH:
                point.convert_to_smooth()
            elif point_type == PointType.SYMMETRIC:
                point.convert_to_symmetric()
        
        return True
    
    def _distance(self, p1: QtCore.QPointF, p2: QtCore.QPointF) -> float:
        diff = p1 - p2
        return (diff.x()**2 + diff.y()**2)**0.5
```

---

## 3. Curve Editor Controls Widget

### curve_controls.py

Following the `TransformControlsWidget` pattern:

```python
from PySide6 import QtWidgets, QtCore, QtGui
from PySide6.QtCore import QTimer, QPropertyAnimation, QEasingCurve, Signal

from . import utils as UT
from .curve_data import PointType
from .curve_tools import EditorTool


class CurveEditorControlsWidget(QtWidgets.QWidget):
    """Widget for curve editor tools and options - appears above edited button."""
    
    toolChanged = Signal(EditorTool)
    pointTypeChanged = Signal(PointType)
    editingFinished = Signal()
    editingCancelled = Signal()
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.current_tool = EditorTool.NODE
        self.current_point_type = PointType.SMOOTH
        
        # Widget properties
        self.setFixedHeight(32)
        self.setup_ui()
        self.setVisible(False)
        
        # Fade effect (matching TransformControlsWidget)
        self.opacity_effect = QtWidgets.QGraphicsOpacityEffect()
        self.opacity_effect.setOpacity(0.9)
        self.setGraphicsEffect(self.opacity_effect)
        
        self.fade_timer = QTimer(self)
        self.fade_timer.setSingleShot(True)
        self.fade_timer.timeout.connect(self.start_fade_animation)
        
        self.fade_animation = QPropertyAnimation(self.opacity_effect, b"opacity")
        self.fade_animation.setDuration(300)
        self.fade_animation.setEasingCurve(QEasingCurve.InOutQuad)
        
        self.installEventFilter(self)
    
    def setup_ui(self):
        """Set up the UI layout."""
        layout = QtWidgets.QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addStretch()
        
        # Main frame
        frame = QtWidgets.QFrame()
        frame.setStyleSheet("""
            QFrame {
                background-color: rgba(40, 40, 40, 0.95);
                border: 1px solid rgba(80, 80, 80, 0.8);
                border-radius: 4px;
            }
        """)
        layout.addWidget(frame)
        
        frame_layout = QtWidgets.QHBoxLayout(frame)
        frame_layout.setContentsMargins(6, 4, 6, 4)
        frame_layout.setSpacing(4)
        
        # ============== Tool Buttons ==============
        self.tool_group = QtWidgets.QButtonGroup(self)
        self.tool_group.setExclusive(True)
        
        tools = [
            (EditorTool.NODE, 'node_tool.png', 'Node Tool (A)', 'A'),
            (EditorTool.PEN, 'pen_tool.png', 'Pen Tool (P)', 'P'),
            (EditorTool.RECTANGLE, 'rect_tool.png', 'Rectangle (R)', 'R'),
            (EditorTool.ELLIPSE, 'ellipse_tool.png', 'Ellipse (O)', 'O'),
        ]
        
        for tool, icon_name, tooltip, shortcut in tools:
            btn = self._create_tool_button(icon_name, tooltip)
            btn.setCheckable(True)
            btn.setChecked(tool == self.current_tool)
            btn.clicked.connect(lambda checked, t=tool: self._on_tool_clicked(t))
            self.tool_group.addButton(btn)
            frame_layout.addWidget(btn)
        
        # Separator
        sep1 = self._create_separator()
        frame_layout.addWidget(sep1)
        
        # ============== Point Type Buttons ==============
        self.point_type_group = QtWidgets.QButtonGroup(self)
        self.point_type_group.setExclusive(True)
        
        point_types = [
            (PointType.CORNER, 'point_corner.png', 'Corner Point (1)'),
            (PointType.SMOOTH, 'point_smooth.png', 'Smooth Point (2)'),
            (PointType.SYMMETRIC, 'point_symmetric.png', 'Symmetric Point (3)'),
        ]
        
        for pt, icon_name, tooltip in point_types:
            btn = self._create_tool_button(icon_name, tooltip, size=16)
            btn.setCheckable(True)
            btn.setChecked(pt == self.current_point_type)
            btn.clicked.connect(lambda checked, p=pt: self._on_point_type_clicked(p))
            self.point_type_group.addButton(btn)
            frame_layout.addWidget(btn)
        
        # Separator
        sep2 = self._create_separator()
        frame_layout.addWidget(sep2)
        
        # ============== Action Buttons ==============
        # Done button
        self.done_btn = QtWidgets.QPushButton("✓")
        self.done_btn.setFixedSize(24, 20)
        self.done_btn.setToolTip("Finish Editing (Enter)")
        self.done_btn.setStyleSheet(self._get_action_button_style('#4CAF50'))
        self.done_btn.clicked.connect(self._on_done_clicked)
        frame_layout.addWidget(self.done_btn)
        
        # Cancel button
        self.cancel_btn = QtWidgets.QPushButton("✕")
        self.cancel_btn.setFixedSize(24, 20)
        self.cancel_btn.setToolTip("Cancel (Escape)")
        self.cancel_btn.setStyleSheet(self._get_action_button_style('#f44336'))
        self.cancel_btn.clicked.connect(self._on_cancel_clicked)
        frame_layout.addWidget(self.cancel_btn)
        
        layout.addStretch()
    
    def _create_tool_button(self, icon_name: str, tooltip: str, size: int = 18) -> QtWidgets.QPushButton:
        """Create a tool button with icon."""
        btn = QtWidgets.QPushButton()
        btn.setFixedSize(24, 22)
        btn.setToolTip(tooltip)
        
        # Try to load icon, fallback to text
        icon = UT.get_icon(icon_name, size=size) if hasattr(UT, 'get_icon') else None
        if icon and not icon.isNull():
            btn.setIcon(QtGui.QIcon(icon))
            btn.setIconSize(QtCore.QSize(size, size))
        
        btn.setStyleSheet("""
            QPushButton {
                background-color: rgba(60, 60, 60, 200);
                border: 1px solid rgba(100, 100, 100, 150);
                border-radius: 3px;
                padding: 2px;
            }
            QPushButton:hover {
                background-color: rgba(80, 80, 80, 220);
                border: 1px solid rgba(120, 120, 120, 180);
            }
            QPushButton:checked {
                background-color: rgba(75, 148, 234, 200);
                border: 1px solid rgba(100, 170, 255, 200);
            }
            QPushButton:pressed {
                background-color: rgba(50, 50, 50, 250);
            }
        """)
        
        return btn
    
    def _create_separator(self) -> QtWidgets.QFrame:
        """Create a vertical separator."""
        sep = QtWidgets.QFrame()
        sep.setFrameShape(QtWidgets.QFrame.VLine)
        sep.setStyleSheet("color: rgba(100, 100, 100, 100);")
        return sep
    
    def _get_action_button_style(self, color: str) -> str:
        """Get stylesheet for action buttons."""
        return f"""
            QPushButton {{
                background-color: {color};
                color: white;
                border: none;
                border-radius: 3px;
                font-weight: bold;
                font-size: 12px;
            }}
            QPushButton:hover {{
                background-color: {color};
                filter: brightness(1.2);
            }}
            QPushButton:pressed {{
                background-color: {color};
                filter: brightness(0.8);
            }}
        """
    
    def _on_tool_clicked(self, tool: EditorTool):
        """Handle tool button click."""
        self.current_tool = tool
        self.toolChanged.emit(tool)
    
    def _on_point_type_clicked(self, point_type: PointType):
        """Handle point type button click."""
        self.current_point_type = point_type
        self.pointTypeChanged.emit(point_type)
    
    def _on_done_clicked(self):
        """Handle done button click."""
        self.editingFinished.emit()
    
    def _on_cancel_clicked(self):
        """Handle cancel button click."""
        self.editingCancelled.emit()
    
    def update_position(self, target_rect: QtCore.QRectF):
        """Update position above the target rectangle."""
        if not self.isVisible():
            return
        
        parent = self.parent()
        if not parent:
            return
        
        # Position above the target, centered
        new_x = target_rect.center().x() - self.width() / 2
        new_y = target_rect.top() - self.height() - 8
        
        # Keep within parent bounds
        parent_rect = parent.rect()
        if new_y < 0:
            new_y = target_rect.bottom() + 8
        if new_x < 0:
            new_x = 0
        if new_x + self.width() > parent_rect.width():
            new_x = parent_rect.width() - self.width()
        
        self.move(int(new_x), int(new_y))
    
    # Fade animation methods (matching TransformControlsWidget)
    def handle_enter_event(self):
        self.fade_timer.stop()
        self.fade_animation.stop()
        self.fade_animation.setDuration(100)
        self.fade_animation.setStartValue(self.opacity_effect.opacity())
        self.fade_animation.setEndValue(1.0)
        self.fade_animation.start()
    
    def handle_leave_event(self):
        self.fade_timer.start(500)
    
    def start_fade_animation(self):
        self.fade_animation.setDuration(400)
        self.fade_animation.setStartValue(self.opacity_effect.opacity())
        self.fade_animation.setEndValue(0.7)
        self.fade_animation.start()
    
    def eventFilter(self, obj, event):
        if obj == self:
            if event.type() == QtCore.QEvent.Enter:
                self.handle_enter_event()
            elif event.type() == QtCore.QEvent.Leave:
                self.handle_leave_event()
        return super().eventFilter(obj, event)
```

---

## 4. Main Curve Editor Widget

### curve_editor_widget.py

```python
from PySide6 import QtWidgets, QtCore, QtGui
from PySide6.QtCore import Signal

from .curve_data import ButtonShape, CurvePath, CurvePoint, PointType
from .curve_tools import EditorTool, CurveEditorState, PenTool, NodeTool
from .curve_controls import CurveEditorControlsWidget


class CurveEditorOverlay(QtWidgets.QWidget):
    """Transparent overlay for curve editing on top of the canvas."""
    
    editingFinished = Signal(str)  # Emits SVG path data
    editingCancelled = Signal()
    
    # Visual constants
    ANCHOR_SIZE = 8
    HANDLE_SIZE = 6
    ANCHOR_COLOR = QtGui.QColor(255, 255, 255)
    ANCHOR_SELECTED_COLOR = QtGui.QColor(75, 148, 234)
    HANDLE_COLOR = QtGui.QColor(200, 200, 200)
    HANDLE_LINE_COLOR = QtGui.QColor(150, 150, 150, 180)
    PATH_COLOR = QtGui.QColor(75, 148, 234, 200)
    PATH_PREVIEW_COLOR = QtGui.QColor(75, 148, 234, 100)
    CLOSE_INDICATOR_COLOR = QtGui.QColor(100, 255, 100, 200)
    
    def __init__(self, canvas, parent=None):
        super().__init__(parent)
        self.canvas = canvas
        self.target_button = None  # The button being edited
        
        # Editor state
        self.state = CurveEditorState()
        self.pen_tool = PenTool(self.state)
        self.node_tool = NodeTool(self.state)
        
        # UI setup
        self.setAttribute(QtCore.Qt.WA_TranslucentBackground)
        self.setMouseTracking(True)
        self.setFocusPolicy(QtCore.Qt.StrongFocus)
        
        # Controls widget
        self.controls = CurveEditorControlsWidget(parent)
        self.controls.toolChanged.connect(self._on_tool_changed)
        self.controls.pointTypeChanged.connect(self._on_point_type_changed)
        self.controls.editingFinished.connect(self._finish_editing)
        self.controls.editingCancelled.connect(self._cancel_editing)
        
        self.setVisible(False)
    
    def start_editing(self, button, existing_shape: ButtonShape = None):
        """Start editing a button's shape."""
        self.target_button = button
        
        if existing_shape:
            self.state.current_shape = existing_shape
        else:
            # Create default rectangular shape
            self.state.current_shape = self._create_default_rect_shape(button)
        
        self.state.clear_selection()
        self.state.active_tool = EditorTool.NODE
        
        # Position overlay
        self._update_geometry()
        
        # Show widgets
        self.setVisible(True)
        self.controls.setVisible(True)
        self.controls.update_position(self._get_button_rect())
        
        self.setFocus()
        self.update()
    
    def _create_default_rect_shape(self, button) -> ButtonShape:
        """Create a default rectangular shape based on button size."""
        shape = ButtonShape()
        path = CurvePath()
        
        # Create rectangle with rounded corners (simplified as lines for now)
        w, h = button.width, button.height
        r = min(button.radius) if button.radius else 3
        
        # Simplified rectangle (4 corner points)
        points = [
            QtCore.QPointF(r, 0),
            QtCore.QPointF(w - r, 0),
            QtCore.QPointF(w, r),
            QtCore.QPointF(w, h - r),
            QtCore.QPointF(w - r, h),
            QtCore.QPointF(r, h),
            QtCore.QPointF(0, h - r),
            QtCore.QPointF(0, r),
        ]
        
        for p in points:
            path.add_point(CurvePoint(position=p, point_type=PointType.CORNER))
        
        path.close_path()
        shape.add_path(path)
        
        return shape
    
    def _update_geometry(self):
        """Update overlay geometry to match canvas."""
        if self.canvas:
            self.setGeometry(self.canvas.rect())
    
    def _get_button_rect(self) -> QtCore.QRectF:
        """Get the button rectangle in canvas coordinates."""
        if not self.target_button:
            return QtCore.QRectF()
        
        # Convert button position to canvas coordinates
        pos = self.canvas.scene_to_canvas_coords(self.target_button.scene_position)
        zoom = self.canvas.zoom_factor
        
        w = self.target_button.width * zoom
        h = self.target_button.height * zoom
        
        return QtCore.QRectF(
            pos.x() - w/2,
            pos.y() - h/2,
            w, h
        )
    
    def _scene_to_shape_coords(self, pos: QtCore.QPointF) -> QtCore.QPointF:
        """Convert canvas position to shape-local coordinates."""
        btn_rect = self._get_button_rect()
        return QtCore.QPointF(
            pos.x() - btn_rect.left(),
            pos.y() - btn_rect.top()
        )
    
    def _shape_to_scene_coords(self, pos: QtCore.QPointF) -> QtCore.QPointF:
        """Convert shape-local coordinates to canvas position."""
        btn_rect = self._get_button_rect()
        zoom = self.canvas.zoom_factor if self.canvas else 1.0
        return QtCore.QPointF(
            btn_rect.left() + pos.x() * zoom,
            btn_rect.top() + pos.y() * zoom
        )
    
    def _on_tool_changed(self, tool: EditorTool):
        """Handle tool change from controls."""
        self.state.active_tool = tool
        self.update()
    
    def _on_point_type_changed(self, point_type: PointType):
        """Handle point type change - apply to selected points."""
        if not self.state.current_shape:
            return
        
        for path_idx, point_idx in self.state.selected_points:
            path = self.state.current_shape.paths[path_idx]
            point = path.points[point_idx]
            
            if point_type == PointType.CORNER:
                point.convert_to_corner()
            elif point_type == PointType.SMOOTH:
                point.convert_to_smooth()
            elif point_type == PointType.SYMMETRIC:
                point.convert_to_symmetric()
        
        self.update()
    
    def _finish_editing(self):
        """Finish editing and apply shape to button."""
        if self.state.current_shape and self.target_button:
            svg_data = self.state.current_shape.to_svg_path_data()
            self.editingFinished.emit(svg_data)
        
        self._cleanup()
    
    def _cancel_editing(self):
        """Cancel editing without applying changes."""
        self.editingCancelled.emit()
        self._cleanup()
    
    def _cleanup(self):
        """Clean up after editing."""
        self.target_button = None
        self.state.current_shape = None
        self.state.clear_selection()
        self.setVisible(False)
        self.controls.setVisible(False)
    
    # ==================== Event Handlers ====================
    
    def paintEvent(self, event):
        """Paint the curve editor overlay."""
        painter = QtGui.QPainter(self)
        painter.setRenderHint(QtGui.QPainter.Antialiasing)
        
        if not self.state.current_shape:
            return
        
        btn_rect = self._get_button_rect()
        zoom = self.canvas.zoom_factor if self.canvas else 1.0
        
        # Draw paths
        for path in self.state.current_shape.paths:
            self._draw_path(painter, path, btn_rect, zoom)
        
        # Draw preview for pen tool
        if self.state.active_tool == EditorTool.PEN and self.pen_tool.current_path:
            self._draw_path(painter, self.pen_tool.current_path, btn_rect, zoom, is_preview=True)
            self._draw_pen_preview(painter, btn_rect, zoom)
        
        # Draw points and handles
        for path_idx, path in enumerate(self.state.current_shape.paths):
            for point_idx, point in enumerate(path.points):
                is_selected = self.state.is_point_selected(path_idx, point_idx)
                self._draw_point(painter, point, btn_rect, zoom, is_selected)
    
    def _draw_path(self, painter, path: CurvePath, btn_rect: QtCore.QRectF, 
                   zoom: float, is_preview: bool = False):
        """Draw a path."""
        if not path.points:
            return
        
        # Create QPainterPath with transformed coordinates
        qpath = QtGui.QPainterPath()
        
        first_point = path.points[0]
        start = self._shape_to_scene_coords(first_point.position)
        qpath.moveTo(start)
        
        for i in range(1, len(path.points)):
            prev = path.points[i - 1]
            curr = path.points[i]
            
            if prev.handle_out or curr.handle_in:
                c1 = self._shape_to_scene_coords(
                    prev.get_handle_out_absolute() if prev.handle_out else prev.position
                )
                c2 = self._shape_to_scene_coords(
                    curr.get_handle_in_absolute() if curr.handle_in else curr.position
                )
                end = self._shape_to_scene_coords(curr.position)
                qpath.cubicTo(c1, c2, end)
            else:
                qpath.lineTo(self._shape_to_scene_coords(curr.position))
        
        if path.is_closed and len(path.points) > 2:
            qpath.closeSubpath()
        
        # Draw the path
        pen = QtGui.QPen(self.PATH_PREVIEW_COLOR if is_preview else self.PATH_COLOR)
        pen.setWidth(2)
        pen.setCosmetic(True)
        painter.setPen(pen)
        painter.setBrush(QtCore.Qt.NoBrush)
        painter.drawPath(qpath)
    
    def _draw_point(self, painter, point: CurvePoint, btn_rect: QtCore.QRectF,
                    zoom: float, is_selected: bool):
        """Draw a single point with its handles."""
        pos = self._shape_to_scene_coords(point.position)
        
        # Draw handles (only for selected points)
        if is_selected:
            if point.handle_in:
                h_in = self._shape_to_scene_coords(point.get_handle_in_absolute())
                self._draw_handle_line(painter, pos, h_in)
                self._draw_handle(painter, h_in)
            
            if point.handle_out:
                h_out = self._shape_to_scene_coords(point.get_handle_out_absolute())
                self._draw_handle_line(painter, pos, h_out)
                self._draw_handle(painter, h_out)
        
        # Draw anchor point
        self._draw_anchor(painter, pos, is_selected, point.point_type)
    
    def _draw_anchor(self, painter, pos: QtCore.QPointF, is_selected: bool, 
                     point_type: PointType):
        """Draw an anchor point."""
        size = self.ANCHOR_SIZE
        color = self.ANCHOR_SELECTED_COLOR if is_selected else self.ANCHOR_COLOR
        
        painter.setPen(QtGui.QPen(QtCore.Qt.black, 1))
        painter.setBrush(color)
        
        if point_type == PointType.CORNER:
            # Square for corner
            painter.drawRect(
                int(pos.x() - size/2), int(pos.y() - size/2),
                size, size
            )
        else:
            # Circle for smooth/symmetric
            painter.drawEllipse(pos, size/2, size/2)
    
    def _draw_handle(self, painter, pos: QtCore.QPointF):
        """Draw a handle control point."""
        size = self.HANDLE_SIZE
        painter.setPen(QtGui.QPen(QtCore.Qt.black, 1))
        painter.setBrush(self.HANDLE_COLOR)
        painter.drawEllipse(pos, size/2, size/2)
    
    def _draw_handle_line(self, painter, anchor: QtCore.QPointF, handle: QtCore.QPointF):
        """Draw line from anchor to handle."""
        pen = QtGui.QPen(self.HANDLE_LINE_COLOR)
        pen.setWidth(1)
        pen.setCosmetic(True)
        painter.setPen(pen)
        painter.drawLine(anchor, handle)
    
    def _draw_pen_preview(self, painter, btn_rect: QtCore.QRectF, zoom: float):
        """Draw preview line for pen tool."""
        if not self.pen_tool.current_path or not self.pen_tool.current_path.points:
            return
        
        if self.state.preview_point:
            last_point = self.pen_tool.current_path.points[-1]
            last_pos = self._shape_to_scene_coords(last_point.position)
            
            pen = QtGui.QPen(self.PATH_PREVIEW_COLOR)
            pen.setWidth(1)
            pen.setStyle(QtCore.Qt.DashLine)
            pen.setCosmetic(True)
            painter.setPen(pen)
            painter.drawLine(last_pos, self.state.preview_point)
    
    def mousePressEvent(self, event):
        pos = event.pos()
        shape_pos = self._scene_to_shape_coords(QtCore.QPointF(pos))
        modifiers = event.modifiers()
        
        handled = False
        if self.state.active_tool == EditorTool.PEN:
            handled = self.pen_tool.on_mouse_press(shape_pos, modifiers)
        elif self.state.active_tool == EditorTool.NODE:
            handled = self.node_tool.on_mouse_press(shape_pos, modifiers)
        
        if handled:
            self.update()
            self.controls.update_position(self._get_button_rect())
    
    def mouseMoveEvent(self, event):
        pos = QtCore.QPointF(event.pos())
        shape_pos = self._scene_to_shape_coords(pos)
        modifiers = event.modifiers()
        
        self.state.preview_point = pos  # Store canvas coords for preview
        
        handled = False
        if self.state.active_tool == EditorTool.PEN:
            handled = self.pen_tool.on_mouse_move(shape_pos, modifiers)
        elif self.state.active_tool == EditorTool.NODE:
            handled = self.node_tool.on_mouse_move(shape_pos, modifiers)
        
        self.update()
    
    def mouseReleaseEvent(self, event):
        pos = QtCore.QPointF(event.pos())
        shape_pos = self._scene_to_shape_coords(pos)
        modifiers = event.modifiers()
        
        if self.state.active_tool == EditorTool.PEN:
            self.pen_tool.on_mouse_release(shape_pos, modifiers)
        elif self.state.active_tool == EditorTool.NODE:
            self.node_tool.on_mouse_release(shape_pos, modifiers)
        
        self.update()
    
    def keyPressEvent(self, event):
        key = event.key()
        modifiers = event.modifiers()
        
        # Tool shortcuts
        if key == QtCore.Qt.Key_P:
            self.state.active_tool = EditorTool.PEN
            self.update()
            return
        elif key == QtCore.Qt.Key_A:
            self.state.active_tool = EditorTool.NODE
            self.update()
            return
        
        # Global shortcuts
        if key == QtCore.Qt.Key_Escape:
            if self.state.is_drawing:
                self.pen_tool._cancel_path()
            else:
                self._cancel_editing()
            return
        
        if key == QtCore.Qt.Key_Return or key == QtCore.Qt.Key_Enter:
            if self.state.is_drawing:
                self.pen_tool._finish_path()
            else:
                self._finish_editing()
            return
        
        # Tool-specific key handling
        handled = False
        if self.state.active_tool == EditorTool.PEN:
            handled = self.pen_tool.on_key_press(key, modifiers)
        elif self.state.active_tool == EditorTool.NODE:
            handled = self.node_tool.on_key_press(key, modifiers)
        
        if handled:
            self.update()
    
    def resizeEvent(self, event):
        """Handle resize to update controls position."""
        super().resizeEvent(event)
        if self.isVisible():
            self.controls.update_position(self._get_button_rect())
```

---

## 5. Integration with PickerCanvas

Add to [picker_canvas.py](../blender/ft_anim_picker/src/picker_canvas.py):

```python
# In __init__:
from .curve_editor.curve_editor_widget import CurveEditorOverlay

# Add curve editor overlay
self.curve_editor = CurveEditorOverlay(self, self)
self.curve_editor.editingFinished.connect(self._on_curve_editing_finished)
self.curve_editor.editingCancelled.connect(self._on_curve_editing_cancelled)

# Methods:
def start_curve_editing(self, button):
    """Start curve editing for a button."""
    if not self.edit_mode:
        return
    
    # Parse existing shape if custom
    existing_shape = None
    if button.shape_type == 'custom_path' and button.svg_path_data:
        from .curve_editor.curve_data import ButtonShape
        existing_shape = ButtonShape.from_svg_path_data(button.svg_path_data)
    
    self.curve_editor.start_editing(button, existing_shape)

def _on_curve_editing_finished(self, svg_path_data: str):
    """Handle curve editing completion."""
    button = self.curve_editor.target_button
    if button:
        button.shape_type = 'custom_path'
        button.svg_path_data = svg_path_data
        button._invalidate_mask_cache()
        button.changed.emit(button)
        
        # Save to database
        main_window = self.window()
        if hasattr(main_window, 'batch_update_buttons_to_database'):
            main_window.batch_update_buttons_to_database([button])

def _on_curve_editing_cancelled(self):
    """Handle curve editing cancellation."""
    pass  # No changes to apply
```

---

## Summary

This implementation provides:

1. **Data Layer**: Clean separation of curve data from rendering
2. **Tool Architecture**: Extensible tool system following common patterns
3. **UI Controls**: Consistent with existing `TransformControlsWidget` styling
4. **Canvas Integration**: Overlay-based editing without modifying core canvas code
5. **Keyboard-First UX**: Professional shortcuts matching industry standards

The code follows the existing patterns in the codebase and can be incrementally implemented phase by phase.
