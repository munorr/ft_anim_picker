# Edit Mode Evaluation & Streamlining Plan

## Table of Contents
1. [Current Architecture Overview](#1-current-architecture-overview)
2. [File-by-File Breakdown](#2-file-by-file-breakdown)
3. [Connection Map](#3-connection-map)
4. [Problems with Current Architecture](#4-problems-with-current-architecture)
5. [Proposed Architecture](#5-proposed-architecture)
6. [Migration Plan](#6-migration-plan)
7. [Implementation Details](#7-implementation-details)

---

## 1. Current Architecture Overview

Edit mode functionality is currently scattered across **3 primary files** with additional
dependencies on 2 more files:

```
┌─────────────────────────────────────────────────────────────────────────┐
│                        CURRENT ARCHITECTURE                            │
│                                                                        │
│  button_edit_widgets.py     blender_ui.py            picker_canvas.py  │
│  ┌─────────────────────┐   ┌──────────────────────┐  ┌──────────────┐ │
│  │ UI CREATION         │   │ LOGIC & WIRING       │  │ CANVAS STATE │ │
│  │                     │   │                      │  │              │ │
│  │ - Rename widget     │──>│ - toggle_edit_mode() │<─│ - edit_mode  │ │
│  │ - Text format       │   │ - setup_edit_widgets │  │ - alignment  │ │
│  │ - Transform (W/H)   │──>│ - rename_selected    │<─│ - distribute │ │
│  │ - Radius controls   │   │ - change_opacity     │  │ - copy/paste │ │
│  │ - Opacity slider    │──>│ - set_size           │  │ - selection  │ │
│  │ - Color grid        │   │ - set_radius         │  │ - transform  │ │
│  │ - Placement buttons │──>│ - change_color       │  │   guides     │ │
│  │ - Thumbnail browse  │   │ - batch operations   │  │ - curve edit │ │
│  │                     │   │ - widget updates     │  │              │ │
│  │ - Queue functions   │──>│ - apply changes      │  │ - EditPanel  │ │
│  │ - Alignment helpers │──>│ - undo integration   │  │   (overlay)  │ │
│  └─────────────────────┘   └──────────────────────┘  └──────────────┘ │
│         │                         │    ▲                    ▲          │
│         │                         │    │                    │          │
│         └─────────────────────────┘    │                    │          │
│              All 3 cross-reference     │                    │          │
│              each other constantly     └────────────────────┘          │
│                                                                        │
│  picker_button.py              pb_transform_guides.py                  │
│  ┌──────────────────────┐      ┌──────────────────────┐               │
│  │ - edit_mode flag     │      │ - Transform handles   │               │
│  │ - cursor updates     │      │ - Drag resize/move    │               │
│  │ - paint differences  │      │ - Selection bounding  │               │
│  │ - context menu       │      │                       │               │
│  │ - double-click rename│      │                       │               │
│  └──────────────────────┘      └──────────────────────┘               │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## 2. File-by-File Breakdown

### 2.1 `button_edit_widgets.py` (~640 lines)
**Role:** Creates all edit mode UI widgets and provides queue/helper functions.

| Component | Lines | What It Does |
|-----------|-------|--------------|
| `create_button_edit_widgets(parent)` | 37-509 | Builds all UI widgets, returns dict |
| Rename widget | 37-81 | QLineEdit for button label |
| Text format drawer | 84-197 | Color picker, bold/italic/underline toggles |
| Transform widget | 199-233 | Width/Height fields, proportional checkbox |
| Radius widget | 235-284 | 4 corner radius controls, single-mode toggle |
| Opacity widget | 286-306 | Slider 0-100% |
| Thumbnail directory | 308-361 | Browse button + path display |
| Color widget | 363-408 | 5x6 color grid + color picker |
| Placement widget | 411-509 | Z-order, mirror, align, distribute buttons |
| `queue_*_change()` functions | 517-562 | 5 queue functions that call back to `parent` |
| `get_selected_picker_buttons()` | 600-605 | Helper to get selected buttons from main window |
| `align_selected_buttons_*()` | 607-637 | 6 alignment helpers that route through canvas |

**Problems:**
- `parent` is always `BlenderAnimPickerWindow` - tight coupling to main window
- Queue functions are in this file but call `parent._queue_*()` methods in blender_ui.py
- Alignment helpers go: `button_edit_widgets.py` -> `blender_ui.py` (parent) -> `picker_canvas.py` (canvas) - triple hop
- Widget creation is separate from the logic that uses them

### 2.2 `blender_ui.py` (~4,974 lines) — Edit Mode Portion (~790 lines, ~15.9%)
**Role:** The "brain" - all edit mode logic, widget wiring, and button mutation methods.

**Core Edit Mode Methods (13 methods):**

| Method | Lines | Purpose |
|--------|-------|---------|
| `toggle_edit_mode()` | 1277-1312 | Master toggle - shows/hides panel, syncs all canvases |
| `_animate_edit_mode_width()` | 1314-1341 | Smooth window expand/collapse animation |
| `_on_edit_panel_width_changed()` | 1379-1381 | React to panel resize |
| `setup_edit_widgets()` | 3810-3855 | Calls `create_button_edit_widgets()`, wires signals |
| `update_edit_widgets_delayed()` | 4135-4151 | 50ms debounce timer |
| `update_edit_widgets()` | 4153-4170 | Routes to clear or populate |
| `_clear_edit_widgets_optimized()` | 4172-4208 | Reset widgets when nothing selected |
| `_update_edit_widgets_with_selection_optimized()` | 4210-4310 | Populate widgets from selected buttons |
| `_apply_widget_changes()` | 4009-4043 | Apply queued changes to buttons |
| `_process_batch_updates()` | 4088-4107 | Batch database writes |
| `_cancel_active_curve_editing()` | 1073-1104 | Cancel curve editor on undo |
| `save_undo_for_curve_edit()` | 1107-1119 | Save undo state for curve edits |
| `clear_line_edit_focus()` | 3476-3478 | Clear rename field focus |

**Button Property Mutation Methods (20 methods):**

| Method | Lines | Purpose |
|--------|-------|---------|
| `rename_selected_buttons()` | 3622-3629 | Set label on selected buttons |
| `change_opacity_for_selected_buttons()` | 3631-3644 | Set opacity |
| `set_size_for_selected_buttons()` | 3646-3708 | Set width/height with proportional support |
| `_apply_width_to_all()` | 3710-3728 | Apply width to all selected |
| `_apply_height_to_all()` | 3730-3748 | Apply height to all selected |
| `match_button_size()` | 3749-3769 | Match width to height |
| `set_radius_for_selected_buttons()` | 3782-3788 | Set corner radii |
| `change_color_for_selected_buttons()` | 3790-3795 | Set button color |
| `change_text_color_for_selected_buttons()` | 3798-3804 | Set text color |
| `_queue_rename_change()` | 3855-3859 | Queue rename |
| `_immediate_rename_apply()` | 3861-3864 | Immediate rename on Enter |
| `_queue_opacity_change()` | 3866-3870 | Queue opacity change |
| `_queue_transform_change()` | 3872-3938 | Queue size change (complex) |
| `_queue_radius_change()` | 3940-3963 | Queue radius change |
| `_queue_color_change()` | 3965-3982 | Queue color change |
| `_handle_single_radius_toggle()` | 3984-4007 | Toggle all-corners-same mode |
| `_batch_button_operation()` | 2637-2678 | Execute operation on all selected |
| `on_rename_edit_return_pressed()` | 4348-4350 | Handle Enter in rename |
| `on_transform_edit_value_changed()` | 4356-4361 | Handle size field change |

**Problems:**
- blender_ui.py is already ~5000 lines; 790 lines of edit mode adds to bloat
- Button mutation logic (rename, resize, recolor) doesn't belong in the main window class
- Queue/batch system is split between button_edit_widgets.py and blender_ui.py
- `setup_edit_widgets()` has massive signal wiring block - fragile to maintain

### 2.3 `picker_canvas.py` — Edit Mode Portion
**Role:** Canvas-level edit state, alignment/distribution, transform guides, curve editor.

| Component | Lines | Purpose |
|-----------|-------|---------|
| `CanvasEditPanel` class | 257-400 | Overlay panel widget (right-side drawer) |
| `set_edit_mode()` | 668-686 | Set canvas edit state, update buttons |
| `copy_selected_buttons()` | 759-768 | Copy to clipboard |
| `paste_buttons()` | 770+ | Paste from clipboard |
| `delete_selected_buttons()` | 850+ | Delete selected |
| `align_button_left/right/top/bottom/center/middle()` | 770-926 | 6 alignment methods |
| `evenly_space_horizontal/vertical()` | 927-1002 | 2 distribution methods |
| Transform guides integration | 602-604, 1004-1025 | TransformGuides setup & signals |
| Curve editor integration | 606-609, 1028-1167 | CurveEditorOverlay setup & signals |

**Note:** The alignment and distribution methods rightfully live here (they operate on canvas coordinates), but the routing to get here is convoluted.

### 2.4 `picker_button.py` — Edit Mode Touchpoints
| Component | Purpose |
|-----------|---------|
| `self.edit_mode` flag | Per-button edit state |
| `update_cursor()` | OpenHandCursor in edit mode |
| Paint differences | Different selection rendering in edit vs select mode |
| Context menu | Edit-mode-specific menu items |
| Double-click | Triggers rename in edit mode |
| Signals: `selected`, `changed`, `deleted` | Notify canvas of changes |

---

## 3. Connection Map

### 3.1 Signal Flow Diagram

```
USER ACTION                    SIGNAL CHAIN
───────────                    ────────────

Toggle Edit Mode (Tab key)
  └─> BlenderAnimPickerWindow.toggle_edit_mode()
        ├─> canvas_edit_panel.setVisible()
        ├─> CanvasEditPanel._update_position()
        ├─> For each tab's canvas:
        │     ├─> canvas.set_edit_mode()
        │     │     ├─> button.edit_mode = True (for each button)
        │     │     ├─> button.update_cursor()
        │     │     └─> transform_guides.update_selection()
        │     └─> canvas.update()
        ├─> _animate_edit_mode_width()
        └─> update_edit_widgets_delayed()

Select Button in Edit Mode
  └─> PickerButton.mousePressEvent()
        └─> self.selected.emit(self, True)
              └─> PickerCanvas.on_button_selected()
                    └─> canvas.button_selection_changed.emit()
                          ├─> BlenderAnimPickerWindow.update_edit_widgets_delayed()
                          │     └─> (50ms) update_edit_widgets()
                          │           └─> _update_edit_widgets_with_selection_optimized()
                          └─> transform_guides.update_selection()

Change Color via Edit Widget
  └─> Color grid button clicked (button_edit_widgets.py)
        └─> queue_color_change() (button_edit_widgets.py)
              └─> parent._queue_color_change() (blender_ui.py)
                    └─> pending_widget_changes['color'] = value
                          └─> widget_update_timer.start(10ms)
                                └─> _apply_widget_changes() (blender_ui.py)
                                      └─> change_color_for_selected_buttons()
                                            └─> _batch_button_operation()
                                                  └─> button.color = new_color
                                                        └─> canvas.update()

Align Buttons Left
  └─> Align Left button clicked (button_edit_widgets.py)
        └─> align_selected_buttons_left(main_window) (button_edit_widgets.py)
              └─> get_selected_picker_buttons(main_window) (button_edit_widgets.py)
                    └─> main_window.get_canvas() (blender_ui.py)
                          └─> canvas.get_selected_buttons() (picker_canvas.py)
              └─> buttons[-1].parent().align_button_left() (picker_canvas.py)
```

### 3.2 Cross-File Dependencies

```
button_edit_widgets.py
  IMPORTS: None from project
  RECEIVES: parent (BlenderAnimPickerWindow) as argument
  CALLS INTO:
    → parent._queue_rename_change()         [blender_ui.py]
    → parent._queue_opacity_change()        [blender_ui.py]
    → parent._queue_transform_change()      [blender_ui.py]
    → parent._queue_radius_change()         [blender_ui.py]
    → parent._queue_color_change()          [blender_ui.py]
    → parent._handle_single_radius_toggle() [blender_ui.py]
    → parent.match_button_size()            [blender_ui.py]
    → parent.get_canvas()                   [blender_ui.py]
    → canvas.get_selected_buttons()         [picker_canvas.py]
    → canvas.align_button_*()               [picker_canvas.py]
    → canvas.evenly_space_*()               [picker_canvas.py]

blender_ui.py
  IMPORTS: button_edit_widgets as BEW
  CALLS INTO:
    → BEW.create_button_edit_widgets(self)  [button_edit_widgets.py]
    → canvas.set_edit_mode()                [picker_canvas.py]
    → canvas.get_selected_buttons()         [picker_canvas.py]
    → canvas.button_selection_changed       [picker_canvas.py signal]
    → button.label, button.color, etc.      [picker_button.py]

picker_canvas.py
  IMPORTS: pb_transform_guides, curve_editor
  CALLS INTO:
    → transform_guides.*                    [pb_transform_guides.py]
    → curve_editor.*                        [curve_editor/]
    → button.edit_mode                      [picker_button.py]
```

---

## 4. Problems with Current Architecture

### 4.1 Responsibility Fragmentation
The edit mode is split into 3 roles across 3 files with no clear ownership:
- **button_edit_widgets.py** = UI creation + queue functions + alignment routing
- **blender_ui.py** = Logic, wiring, mutations, widget updates, batch processing
- **picker_canvas.py** = Canvas state, alignment implementation, CanvasEditPanel overlay

This means modifying any edit feature requires touching 2-3 files.

### 4.2 Convoluted Call Chains
A simple operation like "align buttons left" traverses:
```
button_edit_widgets.py → blender_ui.py (get_canvas) → picker_canvas.py (align)
```
A color change traverses:
```
button_edit_widgets.py (queue) → blender_ui.py (queue → timer → apply → batch) → picker_button.py (set)
```

### 4.3 blender_ui.py Bloat
The main window class (`BlenderAnimPickerWindow`) handles:
- Window management, menus, shortcuts
- Tab system management
- File I/O
- Undo/redo
- Database management
- HUD display
- **AND** all edit mode logic (~790 lines)

This violates single-responsibility and makes the file hard to navigate at ~5000 lines.

### 4.4 Tight Coupling via `parent`
`button_edit_widgets.py` passes `parent` (the main window) everywhere. Every widget callback
reaches back into the main window to do work. The widgets are not self-contained.

### 4.5 Duplicated Selection Access
Getting selected buttons happens through at least 3 different code paths:
1. `canvas.get_selected_buttons()` — direct
2. `parent.get_canvas().get_selected_buttons()` — through main window
3. `get_selected_picker_buttons(main_window)` — helper in button_edit_widgets.py

### 4.6 Queue System Split
Queue functions are defined in `button_edit_widgets.py` but the actual queue processing
lives in `blender_ui.py`. The pending changes dict, timers, and apply logic are all in the
main window class.

---

## 5. Proposed Architecture

### 5.1 Core Idea: `EditModeController`

Create a single **`EditModeController`** class that owns the entire edit mode lifecycle.
It lives alongside the canvas and manages its own UI, state, and button mutations.

```
┌──────────────────────────────────────────────────────────────────────┐
│                      PROPOSED ARCHITECTURE                           │
│                                                                      │
│  BlenderAnimPickerWindow (blender_ui.py)                             │
│  ┌────────────────────────────────────────────────────────────────┐  │
│  │  - Window management, menus, shortcuts                        │  │
│  │  - Tab system, file I/O, undo/redo                            │  │
│  │  - toggle_edit_mode() → delegates to controller               │  │
│  │  - Holds reference: self.edit_controller = EditModeController  │  │
│  └───────────────────────┬────────────────────────────────────────┘  │
│                          │                                           │
│                          ▼                                           │
│  EditModeController (NEW: edit_mode_controller.py)                   │
│  ┌────────────────────────────────────────────────────────────────┐  │
│  │                                                                │  │
│  │  STATE            UI CREATION         BUTTON MUTATIONS         │  │
│  │  ─────            ───────────         ────────────────         │  │
│  │  - edit_mode      - EditPanel         - rename()               │  │
│  │  - selection ref  - All widgets       - resize()               │  │
│  │  - pending queue  - Color grid        - recolor()              │  │
│  │  - batch timer    - Placement btns    - set_opacity()          │  │
│  │                                       - set_radius()           │  │
│  │  WIDGET SYNC      QUEUE/BATCH         - set_text_format()      │  │
│  │  ───────────      ──────────                                   │  │
│  │  - on_selection   - queue_change()    ALIGNMENT/LAYOUT         │  │
│  │    _changed()     - apply_changes()   ───────────────          │  │
│  │  - populate()     - batch_update()    - align_*() (delegates   │  │
│  │  - clear()                            │  to canvas)            │  │
│  │                                       - distribute_*()         │  │
│  │                                       - mirror_*()             │  │
│  │                                       - z_order_*()            │  │
│  └───────────────────────┬────────────────────────────────────────┘  │
│                          │                                           │
│                          ▼                                           │
│  PickerCanvas (picker_canvas.py)          PickerButton               │
│  ┌────────────────────────────┐           ┌──────────────────┐      │
│  │  - set_edit_mode()         │           │  - edit_mode flag │      │
│  │  - get_selected_buttons()  │           │  - cursor updates │      │
│  │  - align_*() (geometry)    │           │  - paint mode     │      │
│  │  - distribute_*() (geom)   │           │  - context menu   │      │
│  │  - transform_guides        │           │  - properties     │      │
│  │  - curve_editor            │           └──────────────────┘      │
│  │  - selection signals       │                                      │
│  └────────────────────────────┘                                      │
└──────────────────────────────────────────────────────────────────────┘
```

### 5.2 What Changes

| Current Location | Moves To | Reason |
|-----------------|----------|--------|
| `button_edit_widgets.py` (all) | `EditModeController._build_ui()` | UI creation belongs with the controller that uses it |
| `blender_ui.py` queue methods | `EditModeController._queue_change()` | Single queue system in one place |
| `blender_ui.py` mutation methods | `EditModeController.rename()`, `.resize()`, etc. | Button mutations are edit-mode operations |
| `blender_ui.py` widget update methods | `EditModeController._on_selection_changed()` | Widget sync is internal to the controller |
| `blender_ui.py` batch processing | `EditModeController._apply_changes()` | Batch logic co-located with queue logic |
| `blender_ui.py` `setup_edit_widgets()` | `EditModeController.__init__()` | Setup is initialization |
| `picker_canvas.py` `CanvasEditPanel` | `EditModeController` (becomes the panel itself or owns it) | Panel is the edit mode's UI container |
| `picker_canvas.py` alignment methods | Stay in canvas (called by controller) | Geometry operations belong on canvas |

### 5.3 What Stays the Same

- **PickerCanvas** keeps: `set_edit_mode()`, `get_selected_buttons()`, alignment/distribution
  geometry methods, transform guides, curve editor, selection signals
- **PickerButton** keeps: `edit_mode` flag, cursor, paint differences, context menu, signals
- **BlenderAnimPickerWindow** keeps: `toggle_edit_mode()` (thin — delegates to controller),
  undo/redo integration, keyboard shortcuts

### 5.4 Interface Between Controller and Canvas

```python
class EditModeController(QObject):
    """Owns all edit-mode UI, state, and button mutation logic."""

    def __init__(self, main_window, canvas_frame):
        # main_window: for undo/redo access, tab system access
        # canvas_frame: parent widget for the edit panel overlay

    # --- PUBLIC API (called by main window) ---
    def activate(self):
        """Enter edit mode."""
    def deactivate(self):
        """Exit edit mode."""
    @property
    def is_active(self) -> bool: ...

    def on_tab_changed(self, canvas):
        """Re-bind to new canvas when tab switches."""

    # --- INTERNAL ---
    def _get_canvas(self) -> PickerCanvas: ...
    def _get_selected_buttons(self) -> list: ...
    def _on_selection_changed(self): ...
    def _build_ui(self) -> QWidget: ...
    def _queue_change(self, prop, value): ...
    def _apply_changes(self): ...

    # --- BUTTON MUTATIONS ---
    def rename(self, label): ...
    def resize(self, width, height): ...
    def recolor(self, color): ...
    def set_opacity(self, value): ...
    def set_radius(self, tl, tr, br, bl): ...
    def set_text_format(self, **kwargs): ...

    # --- LAYOUT OPERATIONS (delegates to canvas) ---
    def align_left(self): self._get_canvas().align_button_left()
    def align_right(self): self._get_canvas().align_button_right()
    # ... etc
```

---

## 6. Migration Plan

### Phase 1: Create `EditModeController` scaffold
**Files:** New `edit_mode_controller.py`

1. Create the `EditModeController` class with `__init__`, `activate()`, `deactivate()`
2. Move `CanvasEditPanel` from `picker_canvas.py` into the controller (or have controller own it)
3. Wire `toggle_edit_mode()` in blender_ui.py to delegate to controller
4. **Test:** Edit mode toggle still works, panel shows/hides

### Phase 2: Move UI creation
**Files:** `edit_mode_controller.py`, delete from `button_edit_widgets.py`

1. Move `create_button_edit_widgets()` logic into `EditModeController._build_ui()`
2. Widgets are now instance attributes of the controller (no more `widgets` dict passing)
3. Remove `button_edit_widgets.py` import from `blender_ui.py`
4. **Test:** All edit widgets render correctly in panel

### Phase 3: Move queue/batch system
**Files:** `edit_mode_controller.py`, remove from `blender_ui.py`

1. Move `pending_widget_changes`, `widget_update_timer` to controller
2. Move `_queue_*_change()` methods to controller as `_queue_change(prop, value)`
3. Move `_apply_widget_changes()` and `_process_batch_updates()` to controller
4. Connect widget signals directly to controller methods (no more routing through main window)
5. **Test:** Color, opacity, size, radius changes all work

### Phase 4: Move button mutation methods
**Files:** `edit_mode_controller.py`, remove from `blender_ui.py`

1. Move `rename_selected_buttons()` → `controller.rename()`
2. Move `change_color_for_selected_buttons()` → `controller.recolor()`
3. Move `change_opacity_for_selected_buttons()` → `controller.set_opacity()`
4. Move `set_size_for_selected_buttons()` → `controller.resize()`
5. Move `set_radius_for_selected_buttons()` → `controller.set_radius()`
6. Move `change_text_color_for_selected_buttons()` → `controller.set_text_format()`
7. Move `match_button_size()` → `controller.match_size()`
8. Move `_batch_button_operation()` → `controller._batch_operation()`
9. **Test:** All property edits work on single and multi-selected buttons

### Phase 5: Move widget update/sync
**Files:** `edit_mode_controller.py`, remove from `blender_ui.py`

1. Move `update_edit_widgets_delayed()` → `controller._on_selection_changed()`
2. Move `update_edit_widgets()` → `controller._sync_widgets()`
3. Move `_clear_edit_widgets_optimized()` → `controller._clear_widgets()`
4. Move `_update_edit_widgets_with_selection_optimized()` → `controller._populate_widgets()`
5. Connect `canvas.button_selection_changed` → `controller._on_selection_changed()`
6. **Test:** Selecting buttons updates all edit widgets correctly

### Phase 6: Clean up and wire remaining connections
**Files:** All affected files

1. Update `blender_ui.py` `toggle_edit_mode()` to be a thin wrapper:
   ```python
   def toggle_edit_mode(self):
       if self.edit_controller.is_active:
           self.edit_controller.deactivate()
       else:
           self.edit_controller.activate()
       self._animate_edit_mode_width()
   ```
2. Wire `on_tab_changed` to call `controller.on_tab_changed(new_canvas)`
3. Update undo/redo to interface with controller for curve edit cancellation
4. Remove alignment routing helpers from `button_edit_widgets.py`
5. Delete `button_edit_widgets.py` if fully emptied
6. **Test:** Full regression - all edit mode features work end-to-end

---

## 7. Implementation Details

### 7.1 File Structure After Migration

```
ft_anim_picker/src/
  ├── edit_mode_controller.py    (NEW - ~800 lines, consolidated)
  ├── blender_ui.py              (REDUCED - ~4,200 lines, -790 lines)
  ├── picker_canvas.py           (REDUCED - CanvasEditPanel removed)
  ├── picker_button.py           (UNCHANGED)
  ├── pb_transform_guides.py     (UNCHANGED)
  ├── curve_editor/              (UNCHANGED)
  └── button_edit_widgets.py     (DELETED)
```

### 7.2 Key Design Decisions

**Q: Should `EditModeController` subclass `QWidget`?**
A: No. It should be a `QObject` that *owns* the edit panel widget. This keeps the controller
testable and separates logic from presentation even within the controller.

**Q: Should alignment methods move to the controller?**
A: The *geometry calculation* stays on `PickerCanvas` (it needs canvas coordinates). The
controller provides thin wrappers that call `self._get_canvas().align_button_left()`. The
placement UI buttons connect directly to these wrappers.

**Q: How does the controller access the current canvas?**
A: Through a callback or reference:
```python
self._get_canvas = lambda: main_window.tab_system.tabs[
    main_window.tab_system.current_tab]['canvas']
```

**Q: How does undo/redo work?**
A: The controller calls `main_window.save_undo_state()` before mutations. This is the only
remaining dependency on the main window for edit operations.

### 7.3 Benefits of New Architecture

| Metric | Before | After |
|--------|--------|-------|
| Files touched to add edit feature | 2-3 | 1 (`edit_mode_controller.py`) |
| blender_ui.py size | ~4,974 lines | ~4,200 lines |
| Call chain depth (e.g., color change) | 4 hops across 3 files | 2 hops within controller |
| Selection access patterns | 3 different paths | 1 (`self._get_selected_buttons()`) |
| Queue system location | Split across 2 files | 1 file |
| Widget signal wiring | In `setup_edit_widgets()` far from widget creation | Co-located in `_build_ui()` |
| Code discoverability | Must search 3 files | One file for all edit mode |

### 7.4 Risk Mitigation

- **Migrate incrementally** — each phase produces a working state
- **Keep canvas alignment methods in place** — no risky geometry logic moves
- **Preserve the batch/queue optimization** — just relocate it, don't redesign it
- **Keep PickerButton's edit_mode flag** — buttons still need to know their state for rendering
- **Maintain signal-slot architecture** — just simplify the routing

### 7.5 What NOT to Change

- PickerButton paint logic, cursor handling, context menus
- PickerCanvas selection system, transform guides, curve editor
- Tab system, undo/redo infrastructure
- Database batch update mechanism
- Window animation for edit panel expansion
