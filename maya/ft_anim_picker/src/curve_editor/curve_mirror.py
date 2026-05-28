"""
Mirror mode for the curve editor.

Provides symmetry editing capabilities:
- MirrorAxis: Vertical (left/right) or horizontal (top/bottom)
- MirrorState: Tracks enabled state, axis, and line position
- MirrorMap: Bidirectional point-role mapping for source/center/mirror classification
- Symmetrization algorithms for closed and open paths
- Real-time mirror rebuild during point dragging
"""

try:
    from PySide6 import QtCore
except ImportError:
    from PySide2 import QtCore

from dataclasses import dataclass, field
from typing import Optional, Dict, Tuple, List, Set
from enum import Enum, auto

from .curve_data import CurvePoint, CurvePath, ButtonShape, PointType


# ==================== Enums ====================

class MirrorAxis(Enum):
    """Axis of symmetry."""
    VERTICAL = auto()    # Left/right symmetry (line is vertical at x=L)
    HORIZONTAL = auto()  # Top/bottom symmetry (line is horizontal at y=L)


class PointRole(Enum):
    """Role of a point in a mirrored path."""
    SOURCE = "source"   # On the source side (right for vertical, bottom for horizontal)
    CENTER = "center"   # On or near the symmetry line
    MIRROR = "mirror"   # Auto-generated reflection of a SOURCE point


# ==================== Data Structures ====================

@dataclass
class MirrorState:
    """Tracks mirror mode state for the curve editor."""
    enabled: bool = False
    axis: MirrorAxis = MirrorAxis.VERTICAL
    line_position: float = 0.0      # x for VERTICAL, y for HORIZONTAL (scene coords)
    dragging_line: bool = False
    drag_offset: float = 0.0

    CENTER_SNAP_TOLERANCE: float = 3.0

    def copy(self) -> 'MirrorState':
        return MirrorState(
            enabled=self.enabled,
            axis=self.axis,
            line_position=self.line_position,
            dragging_line=self.dragging_line,
            drag_offset=self.drag_offset
        )


@dataclass
class MirrorPointInfo:
    """Info about a single point's role in the mirror system."""
    role: PointRole
    partner_key: Optional[Tuple[int, int]] = None  # (path_idx, point_idx) of paired point


class MirrorMap:
    """
    Bidirectional map from (path_idx, point_idx) -> MirrorPointInfo.
    Rebuilt whenever mirror state changes or paths are restructured.
    """

    def __init__(self):
        self._map: Dict[Tuple[int, int], MirrorPointInfo] = {}

    def set(self, path_idx: int, point_idx: int, info: MirrorPointInfo):
        self._map[(path_idx, point_idx)] = info

    def get(self, path_idx: int, point_idx: int) -> Optional[MirrorPointInfo]:
        return self._map.get((path_idx, point_idx))

    def get_partner(self, path_idx: int, point_idx: int) -> Optional[Tuple[int, int]]:
        info = self._map.get((path_idx, point_idx))
        if info and info.partner_key:
            return info.partner_key
        return None

    def clear(self):
        self._map.clear()

    def is_source(self, path_idx: int, point_idx: int) -> bool:
        info = self._map.get((path_idx, point_idx))
        return info is not None and info.role == PointRole.SOURCE

    def is_center(self, path_idx: int, point_idx: int) -> bool:
        info = self._map.get((path_idx, point_idx))
        return info is not None and info.role == PointRole.CENTER

    def is_mirror(self, path_idx: int, point_idx: int) -> bool:
        info = self._map.get((path_idx, point_idx))
        return info is not None and info.role == PointRole.MIRROR

    def remove_path(self, path_idx: int):
        """Remove all entries for a given path index."""
        keys_to_remove = [k for k in self._map if k[0] == path_idx]
        for k in keys_to_remove:
            del self._map[k]

    def has_entries(self) -> bool:
        return len(self._map) > 0

    def copy(self) -> 'MirrorMap':
        new_map = MirrorMap()
        for key, info in self._map.items():
            new_map._map[key] = MirrorPointInfo(
                role=info.role,
                partner_key=info.partner_key
            )
        return new_map


# ==================== Point Classification ====================

def classify_point(point: CurvePoint, axis: MirrorAxis, line_pos: float,
                   tolerance: float) -> PointRole:
    """Classify a point as SOURCE, CENTER, or MIRROR based on its position."""
    if axis == MirrorAxis.VERTICAL:
        coord = point.position.x()
    else:
        coord = point.position.y()

    if abs(coord - line_pos) <= tolerance:
        return PointRole.CENTER
    elif coord > line_pos:
        return PointRole.SOURCE
    else:
        return PointRole.MIRROR


# ==================== Point Mirroring ====================

def mirror_point_position(pos: QtCore.QPointF, axis: MirrorAxis,
                          line_pos: float) -> QtCore.QPointF:
    """Reflect a position across the symmetry line."""
    if axis == MirrorAxis.VERTICAL:
        return QtCore.QPointF(2.0 * line_pos - pos.x(), pos.y())
    else:
        return QtCore.QPointF(pos.x(), 2.0 * line_pos - pos.y())


def create_mirror_point(point: CurvePoint, axis: MirrorAxis,
                        line_pos: float) -> CurvePoint:
    """
    Create a mirrored copy of a CurvePoint.

    Handles are swapped (in<->out) AND flipped along the mirror axis because
    mirroring reverses the path winding direction.
    """
    mirrored_pos = mirror_point_position(point.position, axis, line_pos)

    if axis == MirrorAxis.VERTICAL:
        # Swap handles and negate x component
        if point.handle_out is not None:
            new_handle_in = QtCore.QPointF(-point.handle_out.x(), point.handle_out.y())
        else:
            new_handle_in = None

        if point.handle_in is not None:
            new_handle_out = QtCore.QPointF(-point.handle_in.x(), point.handle_in.y())
        else:
            new_handle_out = None
    else:
        # Swap handles and negate y component
        if point.handle_out is not None:
            new_handle_in = QtCore.QPointF(point.handle_out.x(), -point.handle_out.y())
        else:
            new_handle_in = None

        if point.handle_in is not None:
            new_handle_out = QtCore.QPointF(point.handle_in.x(), -point.handle_in.y())
        else:
            new_handle_out = None

    return CurvePoint(
        position=mirrored_pos,
        handle_in=new_handle_in,
        handle_out=new_handle_out,
        point_type=point.point_type
    )


def constrain_center_point(point: CurvePoint, axis: MirrorAxis, line_pos: float):
    """
    Snap a center point onto the symmetry line and zero
    the perpendicular handle component.
    """
    if axis == MirrorAxis.VERTICAL:
        point.position.setX(line_pos)
        if point.handle_in is not None:
            point.handle_in.setX(0.0)
        if point.handle_out is not None:
            point.handle_out.setX(0.0)
    else:
        point.position.setY(line_pos)
        if point.handle_in is not None:
            point.handle_in.setY(0.0)
        if point.handle_out is not None:
            point.handle_out.setY(0.0)


# ==================== Path Symmetrization ====================

def _sort_key_along_line(point: CurvePoint, axis: MirrorAxis) -> float:
    """Get the coordinate along the symmetry line for sorting center points."""
    if axis == MirrorAxis.VERTICAL:
        return point.position.y()
    else:
        return point.position.x()


def _sort_source_points_by_angle(source_points: List[CurvePoint],
                                  center_of_mass: QtCore.QPointF,
                                  axis: MirrorAxis) -> List[CurvePoint]:
    """
    Sort source points by angle from the center of mass.
    This maintains a consistent winding order for path reconstruction.
    """
    import math

    def angle_key(pt):
        dx = pt.position.x() - center_of_mass.x()
        dy = pt.position.y() - center_of_mass.y()
        return math.atan2(dy, dx)

    return sorted(source_points, key=angle_key)


def symmetrize_path(path: CurvePath, path_idx: int, axis: MirrorAxis,
                    line_pos: float, tolerance: float) -> Tuple[CurvePath, MirrorMap]:
    """
    Symmetrize a path around the given axis.

    For closed paths: rebuilds the path as center0 -> sources -> center1 -> mirrors(reversed)
    For open paths entirely on source side: returns original + mirrored copy

    Returns:
        Tuple of (new_path_or_paths, mirror_map)
        For closed paths, returns a single CurvePath.
        For open source-only paths, caller should handle adding the mirror path.
    """
    if path.is_closed:
        return _symmetrize_closed_path(path, path_idx, axis, line_pos, tolerance)
    else:
        return _symmetrize_open_path(path, path_idx, axis, line_pos, tolerance)


def _merge_duplicate_endpoints(path: CurvePath) -> CurvePath:
    """
    Merge duplicate first/last point on a closed path.

    SVG paths commonly end with a curve command whose endpoint coincides with
    the initial ``M`` point, producing two points at the same position.  This
    transfers the last point's ``handle_in`` to the first point and removes
    the duplicate so that symmetry classification counts SOURCE and MIRROR
    sides correctly.

    Returns a (possibly new) CurvePath — the original is not mutated.
    """
    if not path.is_closed or len(path.points) < 3:
        return path

    first = path.points[0]
    last = path.points[-1]
    dist = (first.position - last.position).manhattanLength()
    if dist > 0.5:
        return path  # Not a duplicate

    # Duplicate detected — merge last point's handle_in into first point
    merged = path.copy()
    last_pt = merged.points[-1]
    if last_pt.handle_in is not None:
        merged.points[0].handle_in = QtCore.QPointF(last_pt.handle_in)
    # If the first point had no point_type set (default CORNER from M command)
    # and the last point was SMOOTH, adopt that for a clean merge.
    if (first.point_type == PointType.CORNER and
            last_pt.point_type == PointType.SMOOTH and
            merged.points[0].handle_out is not None):
        merged.points[0].point_type = PointType.SMOOTH
    merged.points.pop()
    return merged


def _try_preserve_symmetric_path(path: CurvePath, path_idx: int, axis: MirrorAxis,
                                  line_pos: float, tolerance: float) -> Optional[Tuple[CurvePath, MirrorMap]]:
    """
    Check if a closed path is already symmetric around the mirror line.

    If every SOURCE point can be paired with an existing MIRROR point at the
    expected reflected position, the path is already symmetric and can be kept
    as-is with only a mirror map built on top of it.  Returns None when the
    path is NOT already symmetric and needs destructive rebuild.
    """
    center_indices: List[int] = []
    source_indices: List[int] = []
    mirror_indices: List[int] = []

    for i, pt in enumerate(path.points):
        role = classify_point(pt, axis, line_pos, tolerance)
        if role == PointRole.CENTER:
            center_indices.append(i)
        elif role == PointRole.SOURCE:
            source_indices.append(i)
        else:
            mirror_indices.append(i)

    # Must have equal SOURCE and MIRROR counts to be already-symmetric
    if len(source_indices) != len(mirror_indices):
        return None

    # Try to pair each source with a mirror point at the expected position
    available_mirrors = set(mirror_indices)
    pairings: Dict[int, int] = {}  # source_idx -> mirror_idx

    for si in source_indices:
        src_pt = path.points[si]
        expected_pos = mirror_point_position(src_pt.position, axis, line_pos)

        best_match = -1
        best_dist = float('inf')
        for mi in available_mirrors:
            mir_pt = path.points[mi]
            dist = (mir_pt.position - expected_pos).manhattanLength()
            if dist < best_dist:
                best_dist = dist
                best_match = mi

        if best_match >= 0 and best_dist < tolerance * 2:
            pairings[si] = best_match
            available_mirrors.discard(best_match)
        else:
            return None  # Cannot pair — not symmetric

    # All paired — build mirror map over the existing point indices
    mirror_map = MirrorMap()
    for ci in center_indices:
        mirror_map.set(path_idx, ci, MirrorPointInfo(PointRole.CENTER))
    for si, mi in pairings.items():
        mirror_map.set(path_idx, si,
                       MirrorPointInfo(PointRole.SOURCE, partner_key=(path_idx, mi)))
        mirror_map.set(path_idx, mi,
                       MirrorPointInfo(PointRole.MIRROR, partner_key=(path_idx, si)))

    # Copy the path, only snap center points to the line (minimal change)
    new_path = path.copy()
    for ci in center_indices:
        constrain_center_point(new_path.points[ci], axis, line_pos)

    return new_path, mirror_map


def _symmetrize_closed_path(path: CurvePath, path_idx: int, axis: MirrorAxis,
                             line_pos: float, tolerance: float) -> Tuple[CurvePath, MirrorMap]:
    """Symmetrize a closed path."""

    # Merge duplicate first/last point that SVG parsing commonly creates
    path = _merge_duplicate_endpoints(path)

    # Fast path: if the shape is already symmetric, preserve it as-is
    preserved = _try_preserve_symmetric_path(path, path_idx, axis, line_pos, tolerance)
    if preserved is not None:
        return preserved

    mirror_map = MirrorMap()

    # Step 1: Classify all points
    sources = []   # (original_index, CurvePoint copy)
    centers = []   # (original_index, CurvePoint copy)
    for i, pt in enumerate(path.points):
        role = classify_point(pt, axis, line_pos, tolerance)
        if role == PointRole.SOURCE:
            sources.append((i, pt.copy()))
        elif role == PointRole.CENTER:
            centers.append((i, pt.copy()))
        # MIRROR points are discarded — they'll be regenerated

    # If no source points, nothing to mirror from — return path as-is
    if not sources:
        new_path = path.copy()
        for i in range(len(new_path.points)):
            mirror_map.set(path_idx, i, MirrorPointInfo(PointRole.CENTER))
        return new_path, mirror_map

    # Step 2: Sort center points along the line axis
    centers.sort(key=lambda item: _sort_key_along_line(item[1], axis))

    # Step 3: Constrain center points to the line
    for _, pt in centers:
        constrain_center_point(pt, axis, line_pos)

    # Step 4: Sort source points to maintain winding order
    # Use original path order — find contiguous source runs
    # The simplest robust approach: keep sources in original order
    source_points = [pt for _, pt in sources]

    # Step 5: Build the symmetric path
    new_path = CurvePath(is_closed=True)
    point_index = 0

    # Add first center point (if exists)
    center_indices = []
    if len(centers) >= 1:
        new_path.add_point(centers[0][1])
        mirror_map.set(path_idx, point_index, MirrorPointInfo(PointRole.CENTER))
        center_indices.append(point_index)
        point_index += 1

    # Add source points
    source_start_idx = point_index
    for sp in source_points:
        new_path.add_point(sp)
        mirror_map.set(path_idx, point_index, MirrorPointInfo(PointRole.SOURCE))
        point_index += 1

    # Add second center point (if exists)
    if len(centers) >= 2:
        new_path.add_point(centers[1][1])
        mirror_map.set(path_idx, point_index, MirrorPointInfo(PointRole.CENTER))
        center_indices.append(point_index)
        point_index += 1

    # Add mirror points (reverse order of source)
    for i, sp in enumerate(reversed(source_points)):
        mp = create_mirror_point(sp, axis, line_pos)
        new_path.add_point(mp)

        # Set up bidirectional pairing
        source_idx = source_start_idx + len(source_points) - 1 - i
        mirror_idx = point_index

        mirror_map.set(path_idx, mirror_idx,
                       MirrorPointInfo(PointRole.MIRROR, partner_key=(path_idx, source_idx)))
        # Update source entry with partner
        source_info = mirror_map.get(path_idx, source_idx)
        if source_info:
            source_info.partner_key = (path_idx, mirror_idx)

        point_index += 1

    # Fix collapsed center handles (e.g., circle centered on mirror line)
    if center_indices:
        _fix_center_handles(new_path, center_indices, axis, line_pos)

    return new_path, mirror_map


def _fix_center_handles(path: CurvePath, center_indices: List[int],
                         axis: MirrorAxis, line_pos: float):
    """
    Recompute CENTER point handles that collapsed to zero after constraining.

    When a center point's handles are entirely perpendicular to the symmetry
    line (e.g., circle top/bottom), constraining zeroes them. This recomputes
    handles along the symmetry line axis using neighbor distance and the
    standard bezier circle approximation constant.
    """
    k = 0.5522847498  # 4/3 * tan(pi/8)
    num_pts = len(path.points)
    if num_pts < 3:
        return

    for ci in center_indices:
        pt = path.points[ci]

        has_in = (pt.handle_in is not None and
                  (abs(pt.handle_in.x()) > 0.001 or abs(pt.handle_in.y()) > 0.001))
        has_out = (pt.handle_out is not None and
                   (abs(pt.handle_out.x()) > 0.001 or abs(pt.handle_out.y()) > 0.001))

        if has_in and has_out:
            continue  # Handles are fine

        prev_pt = path.points[(ci - 1) % num_pts]
        next_pt = path.points[(ci + 1) % num_pts]

        if axis == MirrorAxis.VERTICAL:
            # Handles should point along Y
            d_prev = abs(prev_pt.position.y() - pt.position.y())
            d_next = abs(next_pt.position.y() - pt.position.y())
            dir_in_y = 1.0 if prev_pt.position.y() > pt.position.y() else -1.0
            dir_out_y = 1.0 if next_pt.position.y() > pt.position.y() else -1.0

            if not has_in and d_prev > 0.001:
                pt.handle_in = QtCore.QPointF(0.0, dir_in_y * d_prev * k)
            if not has_out and d_next > 0.001:
                pt.handle_out = QtCore.QPointF(0.0, dir_out_y * d_next * k)
        else:
            # Handles should point along X
            d_prev = abs(prev_pt.position.x() - pt.position.x())
            d_next = abs(next_pt.position.x() - pt.position.x())
            dir_in_x = 1.0 if prev_pt.position.x() > pt.position.x() else -1.0
            dir_out_x = 1.0 if next_pt.position.x() > pt.position.x() else -1.0

            if not has_in and d_prev > 0.001:
                pt.handle_in = QtCore.QPointF(dir_in_x * d_prev * k, 0.0)
            if not has_out and d_next > 0.001:
                pt.handle_out = QtCore.QPointF(dir_out_x * d_next * k, 0.0)


def _symmetrize_open_path(path: CurvePath, path_idx: int, axis: MirrorAxis,
                           line_pos: float, tolerance: float) -> Tuple[CurvePath, MirrorMap]:
    """
    Symmetrize an open path.

    If the path is entirely on the source side, returns the original.
    The caller is responsible for creating the mirrored copy path.
    """
    mirror_map = MirrorMap()

    # Classify points
    has_source = False
    has_mirror = False
    for pt in path.points:
        role = classify_point(pt, axis, line_pos, tolerance)
        if role == PointRole.SOURCE:
            has_source = True
        elif role == PointRole.MIRROR:
            has_mirror = True

    # If it has points on both sides, treat as a closed-path-like symmetrization
    if has_source and has_mirror:
        # Remove mirror side points, regenerate them
        new_points = []
        for i, pt in enumerate(path.points):
            role = classify_point(pt, axis, line_pos, tolerance)
            if role != PointRole.MIRROR:
                new_points.append(pt.copy())
                if role == PointRole.CENTER:
                    constrain_center_point(new_points[-1], axis, line_pos)

        new_path = CurvePath(points=new_points, is_closed=False)
        for i in range(len(new_path.points)):
            pt = new_path.points[i]
            role = classify_point(pt, axis, line_pos, tolerance)
            mirror_map.set(path_idx, i, MirrorPointInfo(
                PointRole.CENTER if role == PointRole.CENTER else PointRole.SOURCE
            ))
        return new_path, mirror_map

    # Path is entirely on source side — keep as is, mark all as SOURCE
    new_path = path.copy()
    for i in range(len(new_path.points)):
        mirror_map.set(path_idx, i, MirrorPointInfo(PointRole.SOURCE))
    return new_path, mirror_map


def create_mirrored_path_copy(path: CurvePath, axis: MirrorAxis,
                               line_pos: float) -> CurvePath:
    """
    Create a full mirrored copy of a path as a separate path.
    Used for open paths entirely on the source side.
    Points are reversed to maintain consistent winding.
    """
    mirrored = CurvePath(is_closed=path.is_closed)
    for pt in reversed(path.points):
        mirrored.add_point(create_mirror_point(pt, axis, line_pos))
    return mirrored


# ==================== Real-time Mirror Rebuild ====================

def rebuild_mirror_side(path: CurvePath, mirror_map: MirrorMap,
                        path_idx: int, axis: MirrorAxis, line_pos: float):
    """
    Update all MIRROR points from their SOURCE partners.
    Also constrains CENTER points to the symmetry line.
    Called during real-time dragging for live feedback.
    """
    for point_idx in range(len(path.points)):
        info = mirror_map.get(path_idx, point_idx)
        if not info:
            continue

        point = path.points[point_idx]

        if info.role == PointRole.CENTER:
            constrain_center_point(point, axis, line_pos)

        elif info.role == PointRole.MIRROR and info.partner_key:
            src_path_idx, src_point_idx = info.partner_key
            # Partner should be in the same path for closed-path mirrors
            if src_path_idx == path_idx and src_point_idx < len(path.points):
                source_point = path.points[src_point_idx]
                mirrored = create_mirror_point(source_point, axis, line_pos)
                point.position = mirrored.position
                point.handle_in = mirrored.handle_in
                point.handle_out = mirrored.handle_out
                point.point_type = mirrored.point_type


def rebuild_mirror_side_cross_path(shape: ButtonShape, mirror_map: MirrorMap,
                                    path_idx: int, axis: MirrorAxis, line_pos: float):
    """
    Rebuild mirror for a path that may have cross-path partners
    (e.g., open source path with a separate mirror path).
    """
    if path_idx >= len(shape.paths):
        return

    # First, rebuild within-path mirrors
    rebuild_mirror_side(shape.paths[path_idx], mirror_map, path_idx, axis, line_pos)

    # Check for cross-path partners
    path = shape.paths[path_idx]
    for point_idx in range(len(path.points)):
        info = mirror_map.get(path_idx, point_idx)
        if info and info.role == PointRole.SOURCE and info.partner_key:
            partner_path_idx, partner_point_idx = info.partner_key
            if partner_path_idx != path_idx and partner_path_idx < len(shape.paths):
                partner_path = shape.paths[partner_path_idx]
                if partner_point_idx < len(partner_path.points):
                    source_point = path.points[point_idx]
                    mirrored = create_mirror_point(source_point, axis, line_pos)
                    partner = partner_path.points[partner_point_idx]
                    partner.position = mirrored.position
                    partner.handle_in = mirrored.handle_in
                    partner.handle_out = mirrored.handle_out
                    partner.point_type = mirrored.point_type


# ==================== Utility Functions ====================

def compute_default_line_position(shape: ButtonShape, axis: MirrorAxis) -> float:
    """Compute the center of the shape's bounding box along the relevant axis."""
    bounds = shape.get_bounding_rect()
    if bounds.isNull() or bounds.isEmpty():
        return 0.0
    if axis == MirrorAxis.VERTICAL:
        return bounds.center().x()
    else:
        return bounds.center().y()


def hit_test_symmetry_line(pos: QtCore.QPointF, mirror_state: MirrorState,
                           hit_radius: float) -> bool:
    """Check if a position is within hit_radius of the symmetry line."""
    if not mirror_state.enabled:
        return False
    if mirror_state.axis == MirrorAxis.VERTICAL:
        return abs(pos.x() - mirror_state.line_position) < hit_radius
    else:
        return abs(pos.y() - mirror_state.line_position) < hit_radius
