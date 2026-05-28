# Picker Button Rendering System & Curve Editor Plan

## Table of Contents
1. [Current Button System Analysis](#current-button-system-analysis)
2. [Button Shape Types](#button-shape-types)
3. [Rendering Pipeline](#rendering-pipeline)
4. [Button Creation Methods](#button-creation-methods)
5. [Curve Editor Feature Plan](#curve-editor-feature-plan)
6. [UI/UX Design](#uiux-design)
7. [Implementation Roadmap](#implementation-roadmap)

---

## Current Button System Analysis

### Core Button Class: `PickerButton`

Location: [picker_button.py](../blender/ft_anim_picker/src/picker_button.py)

#### Key Properties

| Property | Type | Description |
|----------|------|-------------|
| `shape_type` | `str` | Either `'rounded_rect'` or `'custom_path'` |
| `svg_path_data` | `str` | Raw SVG path string (d attribute) |
| `svg_file_path` | `str` | Reference to original SVG file |
| `radius` | `list[4]` | Corner radii `[top_left, top_right, bottom_right, bottom_left]` |
| `width` / `height` | `int` | Button dimensions |
| `scene_position` | `QPointF` | Position in canvas scene coordinates |

#### Initialization Parameters

```python
def __init__(self, label, parent=None, unique_id=None, color='#444444', 
             opacity=1, width=80, height=30, selectable=True, 
             shape_type='rounded_rect', svg_path_data=None, svg_file_path=None):
```

---

## Button Shape Types

### 1. Rounded Rectangle (Default)
- Created using `_create_rounded_rect_path()`
- Supports individual corner radii
- Most performant option

```python
def _create_rounded_rect_path(self, rect, radii, zoom_factor):
    path = QtGui.QPainterPath()
    zf = zoom_factor * 0.95
    tl, tr, br, bl = [radius * zf for radius in radii]
    
    # Creates path with arc corners
    path.moveTo(rect.left() + tl, rect.top())
    path.lineTo(rect.right() - tr, rect.top())
    path.arcTo(...)  # Top-right corner
    # ... continues for all corners
    return path
```

### 2. Custom SVG Path
- Created using `_create_svg_path()`
- Parses SVG path data string
- Scales to fit button bounds while maintaining aspect ratio

```python
def _create_svg_path(self, rect, zoom_factor):
    svg_path = self._parse_svg_path(self.svg_path_data)
    # Calculate scaling to fit rect
    scale = min(scale_x, scale_y) * 0.9  # 90% padding
    # Apply transformation
    return transform.map(svg_path)
```

---

## Rendering Pipeline

### Paint Event Flow

```
paintEvent()
    ├── Get zoom_factor from parent canvas
    ├── Set background brush (normal/hover/selected states)
    ├── Apply opacity
    ├── Create button path via _create_button_path()
    │       ├── If shape_type == 'custom_path' → _create_svg_path()
    │       └── Else → _create_rounded_rect_path()
    ├── Draw path fill
    ├── Draw selection/hover border
    ├── Check if mask needs update → _generate_mask()
    ├── Check if pixmaps need update
    │       ├── Pose mode → _render_pose_pixmap()
    │       └── Other modes → _render_text_pixmap()
    └── Draw appropriate pixmap
```

### SVG Path Parsing

The `_parse_svg_path()` method handles:
- **Move commands**: `M`, `m`
- **Line commands**: `L`, `l`, `H`, `h`, `V`, `v`
- **Cubic Bezier**: `C`, `c`, `S`, `s`
- **Quadratic Bezier**: `Q`, `q`, `T`, `t`
- **Elliptical Arc**: `A`, `a` (approximated with lines currently)
- **Close path**: `Z`, `z`

### Mask Generation

```python
def _generate_mask(self, zoom_factor):
    # Creates QBitmap mask for accurate hit testing
    # Respects both rounded_rect and custom_path shapes
```

---

## Button Creation Methods

### Method 1: Add Button at Position (Context Menu)
Location: [picker_canvas.py](../blender/ft_anim_picker/src/picker_canvas.py#L3104)

```python
def add_button_at_position(self, position):
    # Creates default rounded_rect button
    new_button = PB.PickerButton("Button", self, unique_id=unique_id)
```

### Method 2: SVG File Import (Drag & Drop)
Location: [picker_canvas.py](../blender/ft_anim_picker/src/picker_canvas.py#L2297)

- `_create_buttons_from_svg()` - Creates multiple buttons from SVG paths
- `_create_combined_button_from_svg()` - Merges all paths into single button
- Preserves SVG spatial layout
- Applies styling from SVG (fill color, opacity)

### Method 3: Blender Curve Conversion
Location: [blender_curve_converter.py](../blender/ft_anim_picker/src/blender_curve_converter.py)

- Converts Blender curve objects to SVG path data
- Supports coordinate plane selection (XY, XZ, YZ)
- Auto-detects optimal projection plane
- Handles Bezier, NURBS, and Poly curves

### Method 4: Paste/Duplicate
Location: [picker_canvas.py](../blender/ft_anim_picker/src/picker_canvas.py#L3144)

- Copies all attributes including shape data
- Supports mirror paste with horizontal flip

### Method 5: Load Shape from SVG File
Location: [picker_button.py](../blender/ft_anim_picker/src/picker_button.py#L1165)

```python
def load_svg_shape(self):
    # Applies SVG path to existing button
    # Available via context menu
```

---

## Curve Editor Feature Plan

### Research: Vector Design Tool Patterns

#### Figma Approach
- **Pen Tool**: Click to add points, drag to create curves
- **Direct Selection**: Click on anchor/handles to edit
- **Path Operations**: Boolean operations, flatten, outline stroke
- **Keyboard Modifiers**: Shift (45° constraint), Alt (independent handles)

#### Affinity Designer Approach
- **Node Tool**: Direct node manipulation
- **Pen Tool**: Separate mode for curve drawing
- **Smart Mode**: Auto-converts sharp to smooth based on angle
- **Context Toolbar**: Shows different options based on selection

### Proposed Feature Set

#### Core Drawing Tools

| Tool | Icon | Shortcut | Description |
|------|------|----------|-------------|
| **Pen Tool** | ✒️ | `P` | Draw curves point-by-point |
| **Node Tool** | ⬡ | `A` | Select and edit anchor points |
| **Rectangle** | ▢ | `R` | Draw rectangles with radius |
| **Ellipse** | ⭕ | `O` | Draw ellipses/circles |

#### Pen Tool Behaviors

```
Click         → Add corner point
Click + Drag  → Add smooth point with handles
Shift + Drag  → Constrain handle to 45° increments
Alt + Click   → Convert smooth to corner
Ctrl + Click  → End current path
Double-click  → End current path
Click on start→ Close path
```

#### Node Tool Behaviors

```
Click Node    → Select single node
Shift + Click → Add/remove from selection
Drag Node     → Move selected nodes
Drag Handle   → Adjust bezier curve
Alt + Handle  → Break handle symmetry
Delete        → Remove selected nodes
```

### Path Data Structure

```python
class CurvePoint:
    position: QPointF          # Anchor point position
    handle_in: QPointF         # Incoming bezier handle (relative)
    handle_out: QPointF        # Outgoing bezier handle (relative)
    point_type: str            # 'corner' | 'smooth' | 'symmetric'
    
class CurvePath:
    points: List[CurvePoint]
    is_closed: bool
    
class ButtonShape:
    paths: List[CurvePath]     # Support compound paths
    
    def to_svg_path_data(self) -> str
    def from_svg_path_data(cls, svg_data: str) -> 'ButtonShape'
```

---

## UI/UX Design

### Curve Editor Controls Widget

Similar to existing `TransformControlsWidget`:

```
┌────────────────────────────────────────────────────────────┐
│  [✒️] [⬡] [▢] [⭕]  │  ● Corner  ◐ Smooth  ◉ Symmetric  │  [✓ Done] │
└────────────────────────────────────────────────────────────┘
     Tools                    Point Type                       Actions
```

### Visual Indicators

#### Path Display (While Editing)
```
     ┌──────────────────────────────────────┐
     │                                      │
     │     ○──────●══════════●──────○      │  ● = Anchor point
     │            │          │              │  ○ = Handle
     │            └──────────┘              │  ═ = Curve segment
     │                                      │  ─ = Handle line
     └──────────────────────────────────────┘
```

#### Selection States
- **Unselected Point**: White fill, dark outline
- **Selected Point**: Blue fill, white outline
- **Hovered Point**: Yellow highlight
- **Handles**: Smaller circles, connected by thin line

### Keyboard Shortcuts

| Key | Action |
|-----|--------|
| `P` | Switch to Pen tool |
| `A` | Switch to Node tool |
| `Delete` / `Backspace` | Delete selected points |
| `Escape` | Cancel current operation / Exit edit mode |
| `Enter` | Confirm shape / Exit edit mode |
| `Ctrl+Z` | Undo |
| `Ctrl+Shift+Z` | Redo |

### Integration Points

#### 1. Context Menu Integration
```
Right-click on button (Edit Mode):
├── Edit Shape (new) ──→ Opens curve editor for this button
├── Draw Custom Shape (new) ──→ Starts drawing mode
├── ...existing options...
└── Reset to Rectangle
```

#### 2. Toolbar Integration
- Add curve editor toggle to edit mode toolbar
- Or integrate into existing TransformControlsWidget

#### 3. Double-click Behavior
- Double-click button in edit mode → Enter curve editing mode
- Shows all anchor points and handles
- Allows direct manipulation

---

## Implementation Roadmap

### Phase 1: Core Data Structures
**Duration**: 1-2 days

1. Create `CurvePoint` and `CurvePath` classes
2. Implement SVG path ↔ CurvePath conversion
3. Add unit tests for path conversion

### Phase 2: Visual Rendering
**Duration**: 2-3 days

1. Create `CurveEditorOverlay` widget (transparent overlay on canvas)
2. Implement point/handle rendering
3. Implement path preview rendering
4. Handle zoom factor coordination with canvas

### Phase 3: Node Tool (Selection & Editing)
**Duration**: 3-4 days

1. Implement point hit-testing
2. Implement single/multi point selection
3. Implement point dragging
4. Implement handle manipulation
5. Implement point type conversion

### Phase 4: Pen Tool (Drawing)
**Duration**: 3-4 days

1. Implement point addition
2. Implement handle drag during creation
3. Implement path closure detection
4. Implement keyboard modifiers (Shift, Alt)
5. Implement curve preview during drawing

### Phase 5: UI Controls Widget
**Duration**: 1-2 days

1. Create `CurveEditorControlsWidget` (similar to `TransformControlsWidget`)
2. Implement tool buttons
3. Implement point type selector
4. Connect to editor state

### Phase 6: Integration & Polish
**Duration**: 2-3 days

1. Integrate with button context menu
2. Implement undo/redo integration
3. Add keyboard shortcuts
4. Testing and bug fixes
5. Performance optimization

### Total Estimated Time: 12-18 days

---

## Technical Considerations

### Performance

1. **Path Caching**: Cache parsed QPainterPath to avoid re-parsing on every paint
2. **Lazy Updates**: Only regenerate paths when data actually changes
3. **Efficient Hit Testing**: Use bounding box pre-check before detailed path check

### Coordinate System Handling

```
Scene Coords ←→ Canvas Coords ←→ Widget Coords ←→ Button Local Coords
     ↑              ↑                ↑                    ↑
     │              │                │                    │
  zoom-independent  zoom-applied   widget offset    normalized to button size
```

### SVG Path Data Preservation

- Store original SVG string for maximum precision
- Only regenerate from internal structure when edited
- Handle floating point precision carefully

### Undo/Redo Integration

```python
# Before any curve edit operation
DM.PickerDataManager.save_undo_state("Edit Shape")

# After operation completes
button.svg_path_data = new_path_data
button.changed.emit(button)
```

---

## File Structure Proposal

```
blender/ft_anim_picker/src/
├── curve_editor/
│   ├── __init__.py
│   ├── curve_data.py          # CurvePoint, CurvePath, ButtonShape classes
│   ├── curve_editor_widget.py # Main curve editor overlay widget
│   ├── curve_tools.py         # Pen tool, Node tool implementations
│   ├── curve_controls.py      # UI controls widget
│   └── svg_converter.py       # SVG ↔ CurvePath conversion utilities
├── picker_button.py           # (Modified) Use curve_data for shape storage
├── picker_canvas.py           # (Modified) Host curve editor overlay
└── ...
```

---

## Open Questions

1. **Should primitive shapes (rect, ellipse) have their own optimized paths or convert to curves?**
   - Recommendation: Use optimized paths but allow conversion to curves for editing

2. **How to handle compound paths (multiple sub-paths)?**
   - Store as list of CurvePaths
   - Support "Add to Shape" vs "New Sub-path" modes

3. **Should we support boolean operations (union, subtract, intersect)?**
   - Nice to have but complex - consider for future phase

4. **How to handle very complex imported SVG paths?**
   - Add simplification tool
   - Set reasonable point limit with warning

---

## References

- [SVG Path Specification](https://www.w3.org/TR/SVG/paths.html)
- [Qt QPainterPath Documentation](https://doc.qt.io/qt-6/qpainterpath.html)
- [Figma Pen Tool Guide](https://help.figma.com/hc/en-us/articles/360040450133)
- [Bezier Curve Mathematics](https://pomax.github.io/bezierinfo/)
