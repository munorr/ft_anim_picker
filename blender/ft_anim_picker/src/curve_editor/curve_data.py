"""
Core data structures for the curve editor.

This module defines the fundamental classes for representing and manipulating
bezier curves and shapes:

- PointType: Enum for point behavior (corner, smooth, symmetric)
- CurvePoint: Single anchor point with optional bezier handles
- CurvePath: A series of connected CurvePoints forming a path
- ButtonShape: Complete shape supporting compound paths
"""

from PySide6 import QtCore, QtGui
from dataclasses import dataclass, field
from typing import List, Optional, Tuple
from enum import Enum
import re
import math


class PointType(Enum):
    """
    Defines how bezier handles behave at a point.
    
    CORNER: Independent handles - can point in any direction
    SMOOTH: Colinear handles - same direction, different lengths
    SYMMETRIC: Mirrored handles - same direction AND length
    """
    CORNER = "corner"
    SMOOTH = "smooth"
    SYMMETRIC = "symmetric"


@dataclass
class CurvePoint:
    """
    Represents a single anchor point on a bezier curve.
    
    The handles are stored as RELATIVE offsets from the anchor position.
    Use get_handle_*_absolute() methods to get world coordinates.
    
    Attributes:
        position: The anchor point position (absolute coordinates)
        handle_in: Incoming bezier handle (relative to position)
        handle_out: Outgoing bezier handle (relative to position)
        point_type: Behavior of handles (corner, smooth, symmetric)
    """
    
    position: QtCore.QPointF
    handle_in: Optional[QtCore.QPointF] = None
    handle_out: Optional[QtCore.QPointF] = None
    point_type: PointType = PointType.CORNER
    
    def __post_init__(self):
        """Ensure position is QPointF."""
        if not isinstance(self.position, QtCore.QPointF):
            self.position = QtCore.QPointF(self.position)
    
    def get_handle_in_absolute(self) -> QtCore.QPointF:
        """Get incoming handle in absolute coordinates."""
        if self.handle_in is None:
            return QtCore.QPointF(self.position)
        return self.position + self.handle_in
    
    def get_handle_out_absolute(self) -> QtCore.QPointF:
        """Get outgoing handle in absolute coordinates."""
        if self.handle_out is None:
            return QtCore.QPointF(self.position)
        return self.position + self.handle_out
    
    def set_handle_in_absolute(self, pos: QtCore.QPointF):
        """
        Set incoming handle from absolute coordinates.
        Applies point type constraints automatically.
        """
        self.handle_in = pos - self.position
        self._apply_point_type_constraint('in')
    
    def set_handle_out_absolute(self, pos: QtCore.QPointF):
        """
        Set outgoing handle from absolute coordinates.
        Applies point type constraints automatically.
        """
        self.handle_out = pos - self.position
        self._apply_point_type_constraint('out')
    
    def _apply_point_type_constraint(self, changed_handle: str):
        """
        Apply constraints based on point type after handle modification.
        
        Args:
            changed_handle: Which handle was modified ('in' or 'out')
        """
        if self.point_type == PointType.CORNER:
            return  # No constraints for corner points
        
        if changed_handle == 'out' and self.handle_out is not None:
            if self.point_type == PointType.SYMMETRIC:
                # Mirror: same length, opposite direction
                self.handle_in = QtCore.QPointF(-self.handle_out.x(), -self.handle_out.y())
            
            elif self.point_type == PointType.SMOOTH:
                # Colinear: opposite direction, preserve incoming length
                if self.handle_in is not None:
                    in_length = self._vector_length(self.handle_in)
                    out_length = self._vector_length(self.handle_out)
                    if out_length > 0.0001:
                        scale = in_length / out_length
                        self.handle_in = QtCore.QPointF(
                            -self.handle_out.x() * scale,
                            -self.handle_out.y() * scale
                        )
                else:
                    # No incoming handle, create one mirrored
                    self.handle_in = QtCore.QPointF(-self.handle_out.x(), -self.handle_out.y())
        
        elif changed_handle == 'in' and self.handle_in is not None:
            if self.point_type == PointType.SYMMETRIC:
                self.handle_out = QtCore.QPointF(-self.handle_in.x(), -self.handle_in.y())
            
            elif self.point_type == PointType.SMOOTH:
                if self.handle_out is not None:
                    out_length = self._vector_length(self.handle_out)
                    in_length = self._vector_length(self.handle_in)
                    if in_length > 0.0001:
                        scale = out_length / in_length
                        self.handle_out = QtCore.QPointF(
                            -self.handle_in.x() * scale,
                            -self.handle_in.y() * scale
                        )
                else:
                    self.handle_out = QtCore.QPointF(-self.handle_in.x(), -self.handle_in.y())
    
    def _vector_length(self, vec: QtCore.QPointF) -> float:
        """Calculate the length of a vector."""
        return math.sqrt(vec.x() ** 2 + vec.y() ** 2)
    
    def has_handles(self) -> bool:
        """Check if this point has any bezier handles."""
        return self.handle_in is not None or self.handle_out is not None
    
    def has_handle_in(self) -> bool:
        """Check if this point has an incoming handle."""
        return self.handle_in is not None and self._vector_length(self.handle_in) > 0.0001
    
    def has_handle_out(self) -> bool:
        """Check if this point has an outgoing handle."""
        return self.handle_out is not None and self._vector_length(self.handle_out) > 0.0001
    
    def convert_to_corner(self):
        """Convert point to corner type (preserve handles but break constraint)."""
        self.point_type = PointType.CORNER
    
    def convert_to_smooth(self, default_handle_length: float = 20.0):
        """
        Convert point to smooth type (make handles colinear).
        
        If the point has no handles, creates default handles to make it a curve.
        This ensures the user sees an immediate visual change.
        
        Args:
            default_handle_length: Length for auto-generated handles
        """
        self.point_type = PointType.SMOOTH
        
        # If no handles exist, create default ones
        if self.handle_out is None and self.handle_in is None:
            # Create horizontal handles as a sensible default
            self.handle_out = QtCore.QPointF(default_handle_length, 0)
            self.handle_in = QtCore.QPointF(-default_handle_length, 0)
        elif self.handle_out is not None:
            self._apply_point_type_constraint('out')
        elif self.handle_in is not None:
            self._apply_point_type_constraint('in')
    
    def convert_to_symmetric(self, default_handle_length: float = 20.0):
        """
        Convert point to symmetric type (mirror handles).
        
        If the point has no handles, creates default handles.
        
        Args:
            default_handle_length: Length for auto-generated handles
        """
        self.point_type = PointType.SYMMETRIC
        
        # If no handles exist, create default ones
        if self.handle_out is None and self.handle_in is None:
            self.handle_out = QtCore.QPointF(default_handle_length, 0)
            self.handle_in = QtCore.QPointF(-default_handle_length, 0)
        elif self.handle_out is not None:
            self._apply_point_type_constraint('out')
        elif self.handle_in is not None:
            self._apply_point_type_constraint('in')
    
    def remove_handles(self):
        """Remove both handles, making this a corner point on a line."""
        self.handle_in = None
        self.handle_out = None
        self.point_type = PointType.CORNER
    
    def align_handles_linearly(self, prev_point: 'CurvePoint' = None, next_point: 'CurvePoint' = None, handle_length: float = 30.0):
        """
        Align handles linearly based on neighboring points to create smooth straight transitions.
        
        If neighboring points are provided, calculates handle direction from them.
        Otherwise, retracts handles to minimal length (creating nearly straight segment).
        
        Args:
            prev_point: Previous point in the path (optional)
            next_point: Next point in the path (optional)
            handle_length: Length for aligned handles
        """
        self.point_type = PointType.SMOOTH
        
        if prev_point and next_point:
            # Calculate direction from previous to next point
            direction = next_point.position - prev_point.position
            length = math.sqrt(direction.x() ** 2 + direction.y() ** 2)
            
            if length > 0.0001:
                # Normalize and scale
                direction = direction / length
                scaled_length = min(handle_length, length / 3)  # Limit to 1/3 of segment length
                
                self.handle_out = QtCore.QPointF(direction.x() * scaled_length, direction.y() * scaled_length)
                self.handle_in = QtCore.QPointF(-direction.x() * scaled_length, -direction.y() * scaled_length)
        elif next_point:
            # Only next point available - align toward it
            direction = next_point.position - self.position
            length = math.sqrt(direction.x() ** 2 + direction.y() ** 2)
            
            if length > 0.0001:
                direction = direction / length
                scaled_length = min(handle_length, length / 3)
                
                self.handle_out = QtCore.QPointF(direction.x() * scaled_length, direction.y() * scaled_length)
                self.handle_in = QtCore.QPointF(-direction.x() * scaled_length, -direction.y() * scaled_length)
        elif prev_point:
            # Only previous point available - align from it
            direction = self.position - prev_point.position
            length = math.sqrt(direction.x() ** 2 + direction.y() ** 2)
            
            if length > 0.0001:
                direction = direction / length
                scaled_length = min(handle_length, length / 3)
                
                self.handle_out = QtCore.QPointF(direction.x() * scaled_length, direction.y() * scaled_length)
                self.handle_in = QtCore.QPointF(-direction.x() * scaled_length, -direction.y() * scaled_length)
        else:
            # No neighbors - retract handles to minimal length (nearly linear)
            minimal_length = 2.0
            if self.handle_out:
                out_length = self._vector_length(self.handle_out)
                if out_length > 0.0001:
                    self.handle_out = self.handle_out * (minimal_length / out_length)
                else:
                    self.handle_out = QtCore.QPointF(minimal_length, 0)
            
            if self.handle_in:
                in_length = self._vector_length(self.handle_in)
                if in_length > 0.0001:
                    self.handle_in = self.handle_in * (minimal_length / in_length)
                else:
                    self.handle_in = QtCore.QPointF(-minimal_length, 0)
    
    def copy(self) -> 'CurvePoint':
        """Create a deep copy of this point."""
        return CurvePoint(
            position=QtCore.QPointF(self.position),
            handle_in=QtCore.QPointF(self.handle_in) if self.handle_in else None,
            handle_out=QtCore.QPointF(self.handle_out) if self.handle_out else None,
            point_type=self.point_type
        )


class CurvePath:
    """
    Represents a single path (series of connected CurvePoints).
    
    A path can be open (like a line) or closed (like a shape).
    Multiple CurvePaths can be combined into a ButtonShape for compound shapes.
    
    Attributes:
        points: List of CurvePoints defining the path
        is_closed: Whether the path forms a closed loop
    """
    
    def __init__(self, points: List[CurvePoint] = None, is_closed: bool = False):
        self.points: List[CurvePoint] = points if points is not None else []
        self.is_closed: bool = is_closed
    
    def add_point(self, point: CurvePoint, index: Optional[int] = None):
        """
        Add a point to the path.
        
        Args:
            point: The CurvePoint to add
            index: Optional position to insert at. If None, appends to end.
        """
        if index is None:
            self.points.append(point)
        else:
            self.points.insert(index, point)
    
    def remove_point(self, index: int) -> Optional[CurvePoint]:
        """
        Remove a point from the path.
        
        Args:
            index: Index of point to remove
            
        Returns:
            The removed point, or None if index invalid
        """
        if 0 <= index < len(self.points):
            return self.points.pop(index)
        return None
    
    def get_point(self, index: int) -> Optional[CurvePoint]:
        """Get point at index, or None if invalid."""
        if 0 <= index < len(self.points):
            return self.points[index]
        return None
    
    def point_count(self) -> int:
        """Get number of points in path."""
        return len(self.points)
    
    def close_path(self):
        """Close the path (connect last point to first)."""
        self.is_closed = True
    
    def open_path(self):
        """Open the path."""
        self.is_closed = False
    
    def reverse(self):
        """Reverse the direction of the path."""
        self.points.reverse()
        # Swap handles for each point
        for point in self.points:
            point.handle_in, point.handle_out = point.handle_out, point.handle_in
    
    def get_bounding_rect(self) -> QtCore.QRectF:
        """
        Calculate bounding rectangle of the path.
        Includes handle positions for accurate bounds.
        """
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
            
            # Include handles for accurate curve bounds
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
    
    def get_rendered_bounding_rect(self) -> QtCore.QRectF:
        """
        Get the actual rendered bounding rectangle using Qt's QPainterPath.
        This gives pixel-accurate bounds of the visible curve geometry,
        which may differ from handle-inclusive bounds.
        """
        qpath = self.to_qpainter_path()
        return qpath.boundingRect()
    
    def to_qpainter_path(self) -> QtGui.QPainterPath:
        """
        Convert to QPainterPath for rendering.
        
        Returns:
            QPainterPath that can be drawn with QPainter
        """
        path = QtGui.QPainterPath()
        
        if not self.points:
            return path
        
        # Move to first point
        path.moveTo(self.points[0].position)
        
        # Draw segments between consecutive points
        for i in range(1, len(self.points)):
            prev_point = self.points[i - 1]
            curr_point = self.points[i]
            self._add_segment_to_path(path, prev_point, curr_point)
        
        # Close path if needed
        if self.is_closed and len(self.points) > 2:
            last_point = self.points[-1]
            first_point = self.points[0]
            self._add_segment_to_path(path, last_point, first_point)
            path.closeSubpath()
        
        return path
    
    def _add_segment_to_path(self, path: QtGui.QPainterPath, 
                             from_point: CurvePoint, to_point: CurvePoint):
        """Add a segment between two points to the QPainterPath."""
        has_ctrl1 = from_point.has_handle_out()
        has_ctrl2 = to_point.has_handle_in()
        
        if has_ctrl1 or has_ctrl2:
            # Cubic bezier curve
            ctrl1 = from_point.get_handle_out_absolute() if has_ctrl1 else from_point.position
            ctrl2 = to_point.get_handle_in_absolute() if has_ctrl2 else to_point.position
            path.cubicTo(ctrl1, ctrl2, to_point.position)
        else:
            # Straight line
            path.lineTo(to_point.position)
    
    def copy(self) -> 'CurvePath':
        """Create a deep copy of this path."""
        return CurvePath(
            points=[p.copy() for p in self.points],
            is_closed=self.is_closed
        )


class ButtonShape:
    """
    Complete shape for a button, supporting compound paths.
    
    A ButtonShape can contain multiple CurvePaths, allowing for:
    - Shapes with holes (outer path + inner cutout paths)
    - Disconnected elements
    - Complex multi-part designs
    
    Attributes:
        paths: List of CurvePath objects
    """
    
    def __init__(self, paths: List[CurvePath] = None):
        self.paths: List[CurvePath] = paths if paths is not None else []
    
    def add_path(self, path: CurvePath):
        """Add a new sub-path to the shape."""
        self.paths.append(path)
    
    def remove_path(self, index: int) -> Optional[CurvePath]:
        """Remove a sub-path by index."""
        if 0 <= index < len(self.paths):
            return self.paths.pop(index)
        return None
    
    def get_path(self, index: int) -> Optional[CurvePath]:
        """Get path at index, or None if invalid."""
        if 0 <= index < len(self.paths):
            return self.paths[index]
        return None
    
    def path_count(self) -> int:
        """Get number of paths in shape."""
        return len(self.paths)
    
    def total_point_count(self) -> int:
        """Get total number of points across all paths."""
        return sum(path.point_count() for path in self.paths)
    
    def is_empty(self) -> bool:
        """Check if shape has no paths or points."""
        return not self.paths or all(p.point_count() == 0 for p in self.paths)
    
    def get_bounding_rect(self) -> QtCore.QRectF:
        """Get bounding rectangle encompassing all paths (includes handles)."""
        if not self.paths:
            return QtCore.QRectF()
        
        combined = QtCore.QRectF()
        for path in self.paths:
            rect = path.get_bounding_rect()
            if not rect.isEmpty():
                if combined.isEmpty():
                    combined = rect
                else:
                    combined = combined.united(rect)
        
        return combined
    
    def get_rendered_bounding_rect(self) -> QtCore.QRectF:
        """
        Get the actual rendered bounding rectangle using Qt's QPainterPath.
        This is the SINGLE SOURCE OF TRUTH for button sizing and positioning,
        ensuring pixel-perfect consistency between curve editor and button display.
        """
        qpath = self.to_qpainter_path()
        return qpath.boundingRect()
    
    def translate(self, dx: float, dy: float):
        """
        Translate all points in the shape by the given offset.
        
        Args:
            dx: X offset
            dy: Y offset
        """
        for path in self.paths:
            for point in path.points:
                point.position = QtCore.QPointF(
                    point.position.x() + dx,
                    point.position.y() + dy
                )
    
    def to_qpainter_path(self) -> QtGui.QPainterPath:
        """Combine all paths into single QPainterPath for rendering."""
        combined = QtGui.QPainterPath()
        for path in self.paths:
            combined.addPath(path.to_qpainter_path())
        return combined
    
    def infer_point_types(self):
        """
        Analyze handle geometry and assign point types accordingly.
        Called after SVG import to restore point type semantics that SVG
        does not encode.

        - No handles → CORNER
        - One handle only → CORNER
        - Both handles, colinear + equal length → SYMMETRIC
        - Both handles, colinear + different length → SMOOTH
        - Both handles, not colinear → CORNER
        """
        COLINEAR_TOLERANCE = 0.02  # cross-product threshold (normalized)
        LENGTH_RATIO_TOLERANCE = 0.05  # 5% length difference

        for path in self.paths:
            for point in path.points:
                h_in = point.handle_in
                h_out = point.handle_out

                in_len = math.sqrt(h_in.x() ** 2 + h_in.y() ** 2) if h_in else 0
                out_len = math.sqrt(h_out.x() ** 2 + h_out.y() ** 2) if h_out else 0

                # No handles or only one meaningful handle → CORNER
                if in_len < 0.001 or out_len < 0.001:
                    point.point_type = PointType.CORNER
                    continue

                # Check colinearity: handles should point in opposite directions
                # Normalize the vectors
                in_nx, in_ny = h_in.x() / in_len, h_in.y() / in_len
                out_nx, out_ny = h_out.x() / out_len, h_out.y() / out_len

                # Cross product (should be ~0 for colinear)
                cross = abs(in_nx * out_ny - in_ny * out_nx)
                # Dot product (should be negative for opposite directions)
                dot = in_nx * out_nx + in_ny * out_ny

                if cross < COLINEAR_TOLERANCE and dot < 0:
                    # Colinear and opposite → check if same length
                    max_len = max(in_len, out_len)
                    length_diff = abs(in_len - out_len) / max_len
                    if length_diff < LENGTH_RATIO_TOLERANCE:
                        point.point_type = PointType.SYMMETRIC
                    else:
                        point.point_type = PointType.SMOOTH
                else:
                    point.point_type = PointType.CORNER

    def to_svg_path_data(self) -> str:
        """
        Convert to SVG path data string (d attribute).

        Returns:
            SVG-compatible path data string
        """
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
                segments.append(self._segment_to_svg(prev, curr))
            
            # Close path if needed
            if path.is_closed and len(path.points) > 2:
                last = path.points[-1]
                first = path.points[0]
                
                # Add closing curve if there are handles
                closing_segment = self._segment_to_svg(last, first)
                if closing_segment.startswith('C'):
                    segments.append(closing_segment)
                
                segments.append("Z")
        
        return "".join(segments)
    
    def _segment_to_svg(self, from_point: CurvePoint, to_point: CurvePoint) -> str:
        """Convert a segment between two points to SVG command."""
        has_ctrl1 = from_point.has_handle_out()
        has_ctrl2 = to_point.has_handle_in()
        
        if has_ctrl1 or has_ctrl2:
            # Cubic bezier
            c1 = from_point.get_handle_out_absolute() if has_ctrl1 else from_point.position
            c2 = to_point.get_handle_in_absolute() if has_ctrl2 else to_point.position
            return (
                f"C{c1.x():.6g},{c1.y():.6g},"
                f"{c2.x():.6g},{c2.y():.6g},"
                f"{to_point.position.x():.6g},{to_point.position.y():.6g}"
            )
        else:
            # Line
            return f"L{to_point.position.x():.6g},{to_point.position.y():.6g}"
    
    @classmethod
    def from_svg_path_data(cls, svg_data: str) -> 'ButtonShape':
        """
        Parse SVG path data string into ButtonShape.
        
        Args:
            svg_data: SVG path data (d attribute value)
            
        Returns:
            ButtonShape instance
        """
        shape = cls()
        
        if not svg_data or not svg_data.strip():
            return shape
        
        # Clean and normalize the path data
        svg_data = svg_data.strip()
        svg_data = re.sub(r',', ' ', svg_data)
        svg_data = re.sub(r'\s+', ' ', svg_data)
        # Add space before negative signs (but not after e/E for scientific notation)
        svg_data = re.sub(r'(?<![eE])-', ' -', svg_data)
        
        # Parse commands and coordinates
        command_pattern = r'([MmLlHhVvCcSsQqTtAaZz])\s*((?:[-+]?(?:\d+\.?\d*|\.\d+)(?:[eE][-+]?\d+)?\s*)*)'
        commands = re.findall(command_pattern, svg_data)
        
        current_path = None
        current_point = QtCore.QPointF(0, 0)
        path_start = QtCore.QPointF(0, 0)
        last_control = None  # For smooth curves
        
        for command, coords_str in commands:
            coords = cls._parse_coordinates(coords_str)
            
            # Handle each SVG command
            if command.upper() == 'M':  # Move to
                current_path, current_point, path_start = cls._handle_move_to(
                    shape, current_path, command, coords, current_point
                )
                last_control = None
                
            elif command.upper() == 'L':  # Line to
                current_point = cls._handle_line_to(
                    current_path, command, coords, current_point
                )
                last_control = None
                
            elif command.upper() == 'H':  # Horizontal line
                current_point = cls._handle_horizontal_line(
                    current_path, command, coords, current_point
                )
                last_control = None
                
            elif command.upper() == 'V':  # Vertical line
                current_point = cls._handle_vertical_line(
                    current_path, command, coords, current_point
                )
                last_control = None
                
            elif command.upper() == 'C':  # Cubic bezier
                current_point, last_control = cls._handle_cubic_bezier(
                    current_path, command, coords, current_point
                )
                
            elif command.upper() == 'S':  # Smooth cubic
                current_point, last_control = cls._handle_smooth_cubic(
                    current_path, command, coords, current_point, last_control
                )
                
            elif command.upper() == 'Q':  # Quadratic bezier
                current_point, last_control = cls._handle_quadratic_bezier(
                    current_path, command, coords, current_point
                )
                
            elif command.upper() == 'T':  # Smooth quadratic
                current_point, last_control = cls._handle_smooth_quadratic(
                    current_path, command, coords, current_point, last_control
                )
                
            elif command.upper() == 'A':  # Arc (approximated)
                current_point = cls._handle_arc(
                    current_path, command, coords, current_point
                )
                last_control = None
                
            elif command.upper() == 'Z':  # Close path
                if current_path:
                    current_path.close_path()
                current_point = path_start
                last_control = None
        
        # Add final path if not empty
        if current_path and current_path.point_count() > 0:
            shape.add_path(current_path)

        # Infer point types from handle geometry since SVG doesn't store them
        shape.infer_point_types()

        return shape
    
    @staticmethod
    def _parse_coordinates(coords_str: str) -> List[float]:
        """Parse coordinate string into list of floats."""
        if not coords_str.strip():
            return []
        
        number_pattern = r'[-+]?(?:\d+\.?\d*|\.\d+)(?:[eE][-+]?\d+)?'
        matches = re.findall(number_pattern, coords_str)
        
        try:
            return [float(x) for x in matches if x]
        except ValueError:
            return []
    
    @classmethod
    def _handle_move_to(cls, shape: 'ButtonShape', current_path: CurvePath,
                        command: str, coords: List[float], 
                        current_point: QtCore.QPointF) -> Tuple[CurvePath, QtCore.QPointF, QtCore.QPointF]:
        """Handle M/m command."""
        # Save previous path if it has points
        if current_path and current_path.point_count() > 0:
            shape.add_path(current_path)
        
        # Start new path
        current_path = CurvePath()
        
        if len(coords) >= 2:
            x, y = coords[0], coords[1]
            if command.islower():  # Relative
                x += current_point.x()
                y += current_point.y()
            
            current_point = QtCore.QPointF(x, y)
            path_start = QtCore.QPointF(x, y)
            current_path.add_point(CurvePoint(position=current_point))
            
            # Additional coordinate pairs are treated as line-to
            for i in range(2, len(coords), 2):
                if i + 1 < len(coords):
                    x, y = coords[i], coords[i + 1]
                    if command.islower():
                        x += current_point.x()
                        y += current_point.y()
                    current_point = QtCore.QPointF(x, y)
                    current_path.add_point(CurvePoint(position=current_point))
        else:
            path_start = current_point
        
        return current_path, current_point, path_start
    
    @classmethod
    def _handle_line_to(cls, current_path: CurvePath, command: str,
                        coords: List[float], current_point: QtCore.QPointF) -> QtCore.QPointF:
        """Handle L/l command."""
        if not current_path:
            return current_point
        
        for i in range(0, len(coords), 2):
            if i + 1 < len(coords):
                x, y = coords[i], coords[i + 1]
                if command.islower():
                    x += current_point.x()
                    y += current_point.y()
                
                current_point = QtCore.QPointF(x, y)
                current_path.add_point(CurvePoint(position=current_point))
        
        return current_point
    
    @classmethod
    def _handle_horizontal_line(cls, current_path: CurvePath, command: str,
                                coords: List[float], current_point: QtCore.QPointF) -> QtCore.QPointF:
        """Handle H/h command."""
        if not current_path:
            return current_point
        
        for coord in coords:
            x = coord
            if command.islower():
                x += current_point.x()
            
            current_point = QtCore.QPointF(x, current_point.y())
            current_path.add_point(CurvePoint(position=current_point))
        
        return current_point
    
    @classmethod
    def _handle_vertical_line(cls, current_path: CurvePath, command: str,
                              coords: List[float], current_point: QtCore.QPointF) -> QtCore.QPointF:
        """Handle V/v command."""
        if not current_path:
            return current_point
        
        for coord in coords:
            y = coord
            if command.islower():
                y += current_point.y()
            
            current_point = QtCore.QPointF(current_point.x(), y)
            current_path.add_point(CurvePoint(position=current_point))
        
        return current_point
    
    @classmethod
    def _handle_cubic_bezier(cls, current_path: CurvePath, command: str,
                             coords: List[float], current_point: QtCore.QPointF) -> Tuple[QtCore.QPointF, QtCore.QPointF]:
        """Handle C/c command."""
        last_control = None
        
        if not current_path:
            return current_point, last_control
        
        for i in range(0, len(coords), 6):
            if i + 5 < len(coords):
                x1, y1 = coords[i], coords[i + 1]
                x2, y2 = coords[i + 2], coords[i + 3]
                x, y = coords[i + 4], coords[i + 5]
                
                if command.islower():
                    x1 += current_point.x()
                    y1 += current_point.y()
                    x2 += current_point.x()
                    y2 += current_point.y()
                    x += current_point.x()
                    y += current_point.y()
                
                # Set handle_out on previous point
                if current_path.points:
                    prev_point = current_path.points[-1]
                    prev_point.handle_out = QtCore.QPointF(x1, y1) - prev_point.position
                
                # Create new point with handle_in
                new_point = CurvePoint(
                    position=QtCore.QPointF(x, y),
                    handle_in=QtCore.QPointF(x2, y2) - QtCore.QPointF(x, y),
                    point_type=PointType.SMOOTH
                )
                current_path.add_point(new_point)
                
                current_point = QtCore.QPointF(x, y)
                last_control = QtCore.QPointF(x2, y2)
        
        return current_point, last_control
    
    @classmethod
    def _handle_smooth_cubic(cls, current_path: CurvePath, command: str,
                             coords: List[float], current_point: QtCore.QPointF,
                             last_control: QtCore.QPointF) -> Tuple[QtCore.QPointF, QtCore.QPointF]:
        """Handle S/s command (smooth cubic bezier)."""
        if not current_path:
            return current_point, last_control
        
        for i in range(0, len(coords), 4):
            if i + 3 < len(coords):
                x2, y2 = coords[i], coords[i + 1]
                x, y = coords[i + 2], coords[i + 3]
                
                if command.islower():
                    x2 += current_point.x()
                    y2 += current_point.y()
                    x += current_point.x()
                    y += current_point.y()
                
                # Calculate first control point (reflection of last control)
                if last_control:
                    x1 = 2 * current_point.x() - last_control.x()
                    y1 = 2 * current_point.y() - last_control.y()
                else:
                    x1, y1 = current_point.x(), current_point.y()
                
                # Set handle_out on previous point
                if current_path.points:
                    prev_point = current_path.points[-1]
                    prev_point.handle_out = QtCore.QPointF(x1, y1) - prev_point.position
                
                # Create new point
                new_point = CurvePoint(
                    position=QtCore.QPointF(x, y),
                    handle_in=QtCore.QPointF(x2, y2) - QtCore.QPointF(x, y),
                    point_type=PointType.SMOOTH
                )
                current_path.add_point(new_point)
                
                current_point = QtCore.QPointF(x, y)
                last_control = QtCore.QPointF(x2, y2)
        
        return current_point, last_control
    
    @classmethod
    def _handle_quadratic_bezier(cls, current_path: CurvePath, command: str,
                                 coords: List[float], current_point: QtCore.QPointF) -> Tuple[QtCore.QPointF, QtCore.QPointF]:
        """Handle Q/q command (quadratic bezier - converted to cubic)."""
        last_control = None
        
        if not current_path:
            return current_point, last_control
        
        for i in range(0, len(coords), 4):
            if i + 3 < len(coords):
                x1, y1 = coords[i], coords[i + 1]
                x, y = coords[i + 2], coords[i + 3]
                
                if command.islower():
                    x1 += current_point.x()
                    y1 += current_point.y()
                    x += current_point.x()
                    y += current_point.y()
                
                # Convert quadratic to cubic bezier control points
                # Cubic CP1 = P0 + 2/3 * (QP1 - P0)
                # Cubic CP2 = P2 + 2/3 * (QP1 - P2)
                qctrl = QtCore.QPointF(x1, y1)
                end = QtCore.QPointF(x, y)
                
                cp1 = current_point + (qctrl - current_point) * (2.0 / 3.0)
                cp2 = end + (qctrl - end) * (2.0 / 3.0)
                
                # Set handle_out on previous point
                if current_path.points:
                    prev_point = current_path.points[-1]
                    prev_point.handle_out = cp1 - prev_point.position
                
                # Create new point
                new_point = CurvePoint(
                    position=end,
                    handle_in=cp2 - end,
                    point_type=PointType.SMOOTH
                )
                current_path.add_point(new_point)
                
                current_point = end
                last_control = qctrl
        
        return current_point, last_control
    
    @classmethod
    def _handle_smooth_quadratic(cls, current_path: CurvePath, command: str,
                                 coords: List[float], current_point: QtCore.QPointF,
                                 last_control: QtCore.QPointF) -> Tuple[QtCore.QPointF, QtCore.QPointF]:
        """Handle T/t command (smooth quadratic bezier)."""
        if not current_path:
            return current_point, last_control
        
        for i in range(0, len(coords), 2):
            if i + 1 < len(coords):
                x, y = coords[i], coords[i + 1]
                
                if command.islower():
                    x += current_point.x()
                    y += current_point.y()
                
                # Calculate control point (reflection of last)
                if last_control:
                    x1 = 2 * current_point.x() - last_control.x()
                    y1 = 2 * current_point.y() - last_control.y()
                else:
                    x1, y1 = current_point.x(), current_point.y()
                
                qctrl = QtCore.QPointF(x1, y1)
                end = QtCore.QPointF(x, y)
                
                # Convert to cubic
                cp1 = current_point + (qctrl - current_point) * (2.0 / 3.0)
                cp2 = end + (qctrl - end) * (2.0 / 3.0)
                
                if current_path.points:
                    prev_point = current_path.points[-1]
                    prev_point.handle_out = cp1 - prev_point.position
                
                new_point = CurvePoint(
                    position=end,
                    handle_in=cp2 - end,
                    point_type=PointType.SMOOTH
                )
                current_path.add_point(new_point)
                
                current_point = end
                last_control = qctrl
        
        return current_point, last_control
    
    @classmethod
    def _handle_arc(cls, current_path: CurvePath, command: str,
                    coords: List[float], current_point: QtCore.QPointF) -> QtCore.QPointF:
        """
        Handle A/a command (elliptical arc).
        
        Note: Arcs are approximated with a line for now.
        TODO: Implement proper arc-to-bezier conversion.
        """
        if not current_path:
            return current_point
        
        for i in range(0, len(coords), 7):
            if i + 6 < len(coords):
                # rx, ry = coords[i], coords[i + 1]
                # x_rotation = coords[i + 2]
                # large_arc = int(coords[i + 3])
                # sweep = int(coords[i + 4])
                x, y = coords[i + 5], coords[i + 6]
                
                if command.islower():
                    x += current_point.x()
                    y += current_point.y()
                
                # Simplified: just draw line to endpoint
                # TODO: Implement arc approximation with bezier curves
                current_point = QtCore.QPointF(x, y)
                current_path.add_point(CurvePoint(position=current_point))
        
        return current_point
    
    def copy(self) -> 'ButtonShape':
        """Create a deep copy of this shape."""
        return ButtonShape(paths=[p.copy() for p in self.paths])
    
    def normalize_to_bounds(self, target_width: float, target_height: float) -> 'ButtonShape':
        """
        Create a normalized copy that fits within the given dimensions.
        
        Args:
            target_width: Target width to fit within
            target_height: Target height to fit within
            
        Returns:
            New ButtonShape scaled and centered to fit
        """
        bounds = self.get_bounding_rect()
        if bounds.isEmpty():
            return self.copy()
        
        # Calculate scale to fit
        scale_x = target_width / bounds.width() if bounds.width() > 0 else 1
        scale_y = target_height / bounds.height() if bounds.height() > 0 else 1
        scale = min(scale_x, scale_y) * 0.9  # 90% to add padding
        
        # Calculate offset to center
        offset_x = (target_width - bounds.width() * scale) / 2 - bounds.left() * scale
        offset_y = (target_height - bounds.height() * scale) / 2 - bounds.top() * scale
        
        # Create transformed copy
        new_shape = ButtonShape()
        
        for path in self.paths:
            new_path = CurvePath(is_closed=path.is_closed)
            
            for point in path.points:
                new_pos = QtCore.QPointF(
                    point.position.x() * scale + offset_x,
                    point.position.y() * scale + offset_y
                )
                
                new_handle_in = None
                if point.handle_in:
                    new_handle_in = QtCore.QPointF(
                        point.handle_in.x() * scale,
                        point.handle_in.y() * scale
                    )
                
                new_handle_out = None
                if point.handle_out:
                    new_handle_out = QtCore.QPointF(
                        point.handle_out.x() * scale,
                        point.handle_out.y() * scale
                    )
                
                new_path.add_point(CurvePoint(
                    position=new_pos,
                    handle_in=new_handle_in,
                    handle_out=new_handle_out,
                    point_type=point.point_type
                ))
            
            new_shape.add_path(new_path)
        
        return new_shape
