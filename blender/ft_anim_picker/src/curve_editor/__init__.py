"""
Curve Editor Module for BGEN Picker

This module provides curve drawing and editing capabilities for creating
custom button shapes within the picker interface.

Components:
- curve_data: Core data structures (CurvePoint, CurvePath, ButtonShape)
- curve_tools: Tool implementations (PenTool, NodeTool)
- curve_controls: UI controls widget
- curve_editor_widget: Main editor overlay

Usage:
    from .curve_editor import CurveEditorOverlay, ButtonShape
    
    # Start editing a button
    editor = CurveEditorOverlay(canvas, parent)
    editor.start_editing(button)
"""

from .curve_data import (
    PointType,
    CurvePoint,
    CurvePath,
    ButtonShape,
)

from .curve_tools import (
    EditorTool,
    CurveEditorState,
    NodeTool,
    PenTool,
    RectangleTool,
    EllipseTool,
    HitResult,
)

from .curve_controls import CurveEditorControlsWidget
from .curve_editor_widget import CurveEditorOverlay

from .curve_mirror import (
    MirrorAxis,
    MirrorState,
    MirrorMap,
    PointRole,
)

__all__ = [
    # Data structures
    'PointType',
    'CurvePoint',
    'CurvePath',
    'ButtonShape',

    # Tools
    'EditorTool',
    'CurveEditorState',
    'NodeTool',
    'PenTool',
    'RectangleTool',
    'EllipseTool',
    'HitResult',

    # Mirror
    'MirrorAxis',
    'MirrorState',
    'MirrorMap',
    'PointRole',

    # Widgets
    'CurveEditorControlsWidget',
    'CurveEditorOverlay',
]
