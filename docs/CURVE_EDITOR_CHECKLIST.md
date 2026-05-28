# Curve Editor Implementation Checklist

## Overview
Implementation of the curve/shape editor for FT Anim Picker buttons.

**Start Date:** January 18, 2026  
**Target Completion:** ~12-18 days

---

## Phase 1: Core Data Structures ✅ COMPLETE
**Estimated:** 1-2 days | **Actual:** 1 day

- [x] Create `curve_editor/` module directory
- [x] Create `__init__.py`
- [x] Create `curve_data.py`
  - [x] `PointType` enum (CORNER, SMOOTH, SYMMETRIC)
  - [x] `CurvePoint` dataclass
  - [x] `CurvePath` class
  - [x] `ButtonShape` class
  - [x] `to_svg_path_data()` method
  - [x] `from_svg_path_data()` method (SVG parsing)
- [ ] Unit tests for path conversion (deferred to Phase 6)

---

## Phase 2: Visual Rendering ✅ COMPLETE
**Estimated:** 2-3 days | **Actual:** 1 day

- [x] Create `curve_editor_widget.py`
  - [x] `CurveEditorOverlay` class
  - [x] Path rendering
  - [x] Anchor point rendering
  - [x] Handle rendering
  - [x] Handle lines rendering
- [x] Coordinate system transformation (canvas ↔ shape)
- [x] Zoom factor handling
- [x] Preview rendering (for pen tool)

---

## Phase 3: Node Tool (Selection & Editing) ✅ COMPLETE
**Estimated:** 3-4 days | **Actual:** 1 day

- [x] Create `curve_tools.py`
  - [x] `EditorTool` enum
  - [x] `HitResult` class
  - [x] `CurveEditorState` class
- [x] `NodeTool` class
  - [x] Hit testing for anchors
  - [x] Hit testing for handles
  - [x] Single point selection
  - [x] Multi-point selection (Shift+click)
  - [x] Point dragging
  - [x] Handle dragging
  - [x] Alt+drag to break handles
  - [x] Point deletion (Delete key)
  - [x] Point type conversion (1, 2, 3 keys)

---

## Phase 4: Pen Tool (Drawing) ✅ COMPLETE
**Estimated:** 3-4 days | **Actual:** 1 day

- [x] `PenTool` class
  - [x] Click to add corner point
  - [x] Click+drag to add smooth point
  - [x] Path start/continuation
  - [x] Path closure detection (click on start)
  - [x] Escape to cancel path
  - [x] Enter to finish path
  - [x] Shift constraint (45° angles)
  - [x] Preview line while drawing

---

## Phase 5: UI Controls Widget ✅ COMPLETE
**Estimated:** 1-2 days | **Actual:** 1 day

- [x] Create `curve_controls.py`
  - [x] `CurveEditorControlsWidget` class
  - [x] Tool buttons (Pen, Node, Rectangle, Ellipse)
  - [x] Point type buttons (Corner, Smooth, Symmetric)
  - [x] Done button
  - [x] Cancel button
  - [x] Fade animation (match TransformControlsWidget)
  - [x] Position updating

---

## Phase 6: Integration & Polish 🔄 IN PROGRESS
**Estimated:** 2-3 days

- [x] Integration with `PickerCanvas`
  - [x] `start_curve_editing()` method
  - [x] `start_new_shape_drawing()` method
  - [x] `_on_curve_editing_finished()` handler
  - [x] `_on_curve_editing_cancelled()` handler
  - [x] `is_curve_editing()` check method
  - [x] Curve editor import and initialization
  - [x] Resize event handling for curve editor
- [x] Integration with `PickerButton`
  - [x] Context menu "Edit Shape" option
  - [x] Context menu "Draw New Shape" option
  - [ ] Double-click to edit (in edit mode) - OPTIONAL
- [ ] Undo/Redo integration
- [ ] Keyboard shortcuts documentation
- [ ] Testing and bug fixes
- [ ] Performance optimization

---

## Files Created

| File | Status | Description |
|------|--------|-------------|
| `curve_editor/__init__.py` | ✅ | Module init |
| `curve_editor/curve_data.py` | ✅ | Core data structures |
| `curve_editor/curve_tools.py` | ✅ | Tool implementations |
| `curve_editor/curve_controls.py` | ✅ | UI controls widget |
| `curve_editor/curve_editor_widget.py` | ✅ | Main editor overlay |

## Files Modified

| File | Changes |
|------|---------|
| `picker_canvas.py` | Added curve editor import, init, methods, resize handler |
| `picker_button.py` | Added "Edit Shape" and "Draw New Shape" context menu options |

---

## Notes & Decisions

### January 18, 2026
- Started implementation
- Created core data structures
- Decision: Using dataclasses for clean, typed data structures
- Decision: PointType as Enum for type safety
- Completed all core module files (Phases 1-5)
- Rectangle and Ellipse tools also implemented
- Ready for Phase 6: Integration with PickerCanvas and PickerButton
- Added curve editor integration to PickerCanvas
- Added context menu options to PickerButton Shape menu

---

## Testing Notes

*(Add testing observations here)*

---

## Known Issues

*(Track bugs/issues here)*

