try:
    from PySide6 import QtWidgets, QtCore, QtGui
    from PySide6.QtCore import Qt, Signal, QPointF, QRectF
except ImportError:
    from PySide2 import QtWidgets, QtCore, QtGui
    from PySide2.QtCore import Qt, Signal, QPointF, QRectF

import os

from . import picker_button as PB
from . import data_management as DM
from . import ui as UI


LINE_COLOR_IDLE = QtGui.QColor(120, 180, 255, 220)
LINE_COLOR_HOVER = QtGui.QColor(255, 200, 80, 240)
LINE_COLOR_DRAG = QtGui.QColor(255, 200, 80, 255)
LINE_DASH = [8, 4]
LINE_WIDTH_PX = 2
HANDLE_RADIUS_PX = 8
HIT_TOLERANCE_PX = 6
GHOST_OPACITY = 0.6
# Translucent dark wash painted over the existing scene to focus attention on
# the mirror line and ghost previews.
DIM_OVERLAY_COLOR = QtGui.QColor(0, 0, 0, 110)
# Shift-precision: line moves at this fraction of cursor delta while shift is held.
PRECISION_FACTOR = 0.1


class MirrorAcceptCancelOverlay(QtWidgets.QWidget):
    """Floating Accept/Cancel buttons shown next to the mirror line."""

    accepted = Signal()
    cancelled = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setStyleSheet("background: transparent;")

        layout = QtWidgets.QHBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(6)

        self.accept_btn = QtWidgets.QPushButton("✓")
        self.accept_btn.setFixedSize(28, 28)
        self.accept_btn.setToolTip("Accept (Enter)")
        self.accept_btn.setCursor(Qt.PointingHandCursor)
        self.accept_btn.setStyleSheet(
            "QPushButton { background-color: #3a8a3a; color: white; border: none;"
            " border-radius: 14px; font-size: 16px; font-weight: bold; }"
            "QPushButton:hover { background-color: #4ba84b; }"
            "QPushButton:pressed { background-color: #2e6d2e; }"
        )

        self.cancel_btn = QtWidgets.QPushButton("✕")
        self.cancel_btn.setFixedSize(28, 28)
        self.cancel_btn.setToolTip("Cancel (Esc)")
        self.cancel_btn.setCursor(Qt.PointingHandCursor)
        self.cancel_btn.setStyleSheet(
            "QPushButton { background-color: #a83a3a; color: white; border: none;"
            " border-radius: 14px; font-size: 14px; font-weight: bold; }"
            "QPushButton:hover { background-color: #c84b4b; }"
            "QPushButton:pressed { background-color: #7a2828; }"
        )

        layout.addWidget(self.accept_btn)
        layout.addWidget(self.cancel_btn)

        self.accept_btn.clicked.connect(self.accepted.emit)
        self.cancel_btn.clicked.connect(self.cancelled.emit)

        self.adjustSize()
        self.hide()

    def position_near_line(self, line_screen_x, canvas_size):
        gap = 14
        w = self.width()
        h = self.height()
        x = line_screen_x + gap
        if x + w > canvas_size.width():
            x = line_screen_x - gap - w
        x = max(0, min(x, canvas_size.width() - w))
        y = int(canvas_size.height() / 2 - h / 2)
        y = max(0, min(y, canvas_size.height() - h))
        self.move(int(x), int(y))


class DuplicateMirrorTool(QtCore.QObject):
    """Interactive tool for duplicating selected picker buttons across a draggable
    vertical mirror axis. Owned by PickerCanvas. Inactive by default."""

    def __init__(self, canvas):
        super().__init__(canvas)
        self.canvas = canvas

        self.active = False
        self.axis_x = 0.0
        self.dragging_line = False
        self.drag_offset = 0.0
        self._hovered = False
        # While True the axis follows the cursor; first left-click drops it.
        self._tracking_cursor = False
        # Shift-precision state — anchors captured on modifier transitions.
        self._precision_active = False
        self._precision_anchor_cursor_x = 0.0
        self._precision_anchor_axis_x = 0.0
        self.source_buttons = []
        self.apply_counterparts = True

        # Visibility we toggle off during the tool.
        self._suppressed_widgets = []

        self.overlay = MirrorAcceptCancelOverlay(canvas)
        self.overlay.accepted.connect(self.commit)
        self.overlay.cancelled.connect(self.cancel)

    # ------------------------------------------------------------------
    # Activation / deactivation
    # ------------------------------------------------------------------

    def activate(self, source_buttons, axis_x):
        if not source_buttons:
            return
        self.source_buttons = list(source_buttons)
        self.axis_x = float(axis_x)
        self.dragging_line = False
        self.drag_offset = 0.0
        self._hovered = False
        # Cursor-tracking on activation: line follows the mouse until the
        # first click drops it. Seed axis_x from the current cursor pos.
        self._tracking_cursor = True
        widget_pt = self.canvas.mapFromGlobal(QtGui.QCursor.pos())
        if (0 <= widget_pt.x() < self.canvas.width()
                and 0 <= widget_pt.y() < self.canvas.height()):
            cursor_scene = self.canvas.canvas_to_scene_coords(QPointF(widget_pt))
            self.axis_x = float(cursor_scene.x())
        self.active = True

        self._suppress_distractions()

        self.canvas.setFocus(Qt.OtherFocusReason)
        self.canvas.setMouseTracking(True)
        self.canvas.setCursor(Qt.SizeHorCursor)
        self.overlay.show()
        self.overlay.raise_()
        self._reposition_overlay()
        self.canvas.update()

    def cancel(self):
        if not self.active:
            return
        self.active = False
        self.dragging_line = False
        self._tracking_cursor = False
        self.source_buttons = []
        self.overlay.hide()
        self.canvas.unsetCursor()
        self._restore_distractions()
        self.canvas.update()

    def _suppress_distractions(self):
        """Hide overlay widgets that would paint on top of the dim wash."""
        self._suppressed_widgets = []
        guides = getattr(self.canvas, 'transform_guides', None)
        if guides is not None:
            for w in (guides, getattr(guides, 'visual_layer', None), getattr(guides, 'control_widget', None)):
                if w is not None and w.isVisible():
                    self._suppressed_widgets.append(w)
                    w.setVisible(False)

    def _restore_distractions(self):
        for w in self._suppressed_widgets:
            try:
                w.setVisible(True)
            except Exception:
                pass
        self._suppressed_widgets = []
        guides = getattr(self.canvas, 'transform_guides', None)
        if guides is not None and self.canvas.edit_mode:
            try:
                guides.update_selection()
            except Exception:
                pass

    # ------------------------------------------------------------------
    # Geometry helpers
    # ------------------------------------------------------------------

    def _line_screen_x(self):
        canvas_pt = self.canvas.scene_to_canvas_coords(QPointF(self.axis_x, 0.0))
        return canvas_pt.x()

    def _reposition_overlay(self):
        if not self.active:
            return
        self.overlay.position_near_line(self._line_screen_x(), self.canvas.size())

    def _hit_test(self, canvas_pos):
        line_x = self._line_screen_x()
        return abs(canvas_pos.x() - line_x) <= HIT_TOLERANCE_PX

    # ------------------------------------------------------------------
    # Mouse / key handling — invoked from PickerCanvas
    # ------------------------------------------------------------------

    def handle_mouse_press(self, event):
        if not self.active:
            return False

        # First click after activation: drop the line at the cursor.
        if self._tracking_cursor:
            scene_pos = self.canvas.canvas_to_scene_coords(QPointF(event.pos()))
            self.axis_x = scene_pos.x()
            self._tracking_cursor = False
            self._reposition_overlay()
            self.canvas.unsetCursor()
            self.canvas.update()
            return True

        if not self._hit_test(event.pos()):
            return False
        scene_pos = self.canvas.canvas_to_scene_coords(QPointF(event.pos()))
        self.dragging_line = True
        self.drag_offset = scene_pos.x() - self.axis_x
        self.canvas.setCursor(Qt.SizeHorCursor)
        return True

    def handle_mouse_move(self, event):
        if not self.active:
            return False

        scene_pos = self.canvas.canvas_to_scene_coords(QPointF(event.pos()))
        shift_held = bool(event.modifiers() & Qt.ShiftModifier)

        # Both cursor-tracking and active drag share the same offset-based math.
        if self._tracking_cursor or self.dragging_line:
            self.axis_x = self._compute_axis_x_for_cursor(scene_pos.x(), shift_held, drag_offset=self.drag_offset)
            if not shift_held:
                self.drag_offset = scene_pos.x() - self.axis_x
            self._reposition_overlay()
            self.canvas.update()
            return True

        # Not actively positioning — clear precision state.
        self._precision_active = False

        # Hover state
        hovered = self._hit_test(event.pos())
        if hovered != self._hovered:
            self._hovered = hovered
            if hovered:
                self.canvas.setCursor(Qt.SizeHorCursor)
            else:
                self.canvas.unsetCursor()
            self.canvas.update()
        return False

    def _compute_axis_x_for_cursor(self, cursor_scene_x, shift_held, drag_offset):
        """Resolve the new axis_x given cursor scene-X, shift state, and the
        active drag_offset. Re-anchors precision state on modifier transitions
        so toggling shift never causes the line to jump."""
        if shift_held:
            if not self._precision_active:
                self._precision_active = True
                self._precision_anchor_cursor_x = cursor_scene_x
                self._precision_anchor_axis_x = self.axis_x
            delta = (cursor_scene_x - self._precision_anchor_cursor_x) * PRECISION_FACTOR
            return self._precision_anchor_axis_x + delta

        if self._precision_active:
            # Just exited precision — preserve current axis_x; caller re-anchors drag_offset.
            self._precision_active = False
            return self.axis_x

        return cursor_scene_x - drag_offset

    def handle_mouse_release(self, event):
        if not self.active:
            return False
        if self.dragging_line:
            self.dragging_line = False
            if not self._hovered:
                self.canvas.unsetCursor()
            return True
        return False

    def handle_key_press(self, event):
        if not self.active:
            return False
        if event.key() in (Qt.Key_Return, Qt.Key_Enter):
            self.commit()
            return True
        if event.key() == Qt.Key_Escape:
            self.cancel()
            return True
        return False

    # ------------------------------------------------------------------
    # Painting — called from PickerCanvas.paintEvent (scene-space painter)
    # ------------------------------------------------------------------

    def paint(self, painter, zoom_factor):
        if not self.active:
            return

        self._reposition_overlay()

        # Visible scene rect — used for both the dim wash and the line height.
        tl = self.canvas.canvas_to_scene_coords(QPointF(0, 0))
        br = self.canvas.canvas_to_scene_coords(QPointF(self.canvas.width(), self.canvas.height()))
        visible = QRectF(tl, br).normalized()

        # Dim wash over everything painted before us.
        painter.save()
        painter.setOpacity(1.0)
        painter.setPen(Qt.NoPen)
        painter.setBrush(DIM_OVERLAY_COLOR)
        painter.drawRect(visible)
        painter.restore()

        # Ghost previews first so the line is drawn on top
        self._paint_ghosts(painter)
        self._paint_line(painter, zoom_factor, visible.top(), visible.bottom())

    def _paint_line(self, painter, zoom_factor, y_top, y_bottom):
        if self.dragging_line:
            color = LINE_COLOR_DRAG
        elif self._hovered:
            color = LINE_COLOR_HOVER
        else:
            color = LINE_COLOR_IDLE

        painter.save()
        painter.setOpacity(1.0)

        pen = QtGui.QPen(color, LINE_WIDTH_PX)
        pen.setCosmetic(True)
        pen.setDashPattern(LINE_DASH)
        painter.setPen(pen)
        painter.setBrush(Qt.NoBrush)
        painter.drawLine(QPointF(self.axis_x, y_top), QPointF(self.axis_x, y_bottom))

        center = self.canvas.canvas_to_scene_coords(QPointF(0, self.canvas.height() / 2))
        handle_radius_scene = HANDLE_RADIUS_PX / zoom_factor if zoom_factor else HANDLE_RADIUS_PX
        painter.setPen(QtGui.QPen(color, 1))
        painter.setBrush(color)
        painter.drawEllipse(QPointF(self.axis_x, center.y()), handle_radius_scene, handle_radius_scene)

        painter.restore()

    def _paint_ghosts(self, painter):
        """Render translucent previews. Uses painter.scale(-1, 1) so we can
        re-use the source button's un-mirrored path — equivalent to drawing
        the mirrored shape with negated rotation."""
        if not self.source_buttons:
            return

        ghost_pen = QtGui.QPen(LINE_COLOR_DRAG, 1.5)
        ghost_pen.setCosmetic(True)
        ghost_pen.setStyle(Qt.DashLine)

        for src in self.source_buttons:
            try:
                mx = 2 * self.axis_x - src.scene_position.x()
                my = src.scene_position.y()

                content_rect = QRectF(-src.width / 2.0, -src.height / 2.0, src.width, src.height)
                path = src._create_button_path_scene(content_rect, src.radius)

                painter.save()
                painter.setOpacity(GHOST_OPACITY)
                painter.translate(mx, my)
                painter.scale(-1.0, 1.0)
                if src.rotation:
                    painter.rotate(src.rotation)

                painter.setBrush(QtGui.QColor(src.color))
                painter.setPen(Qt.NoPen)
                painter.drawPath(path)

                painter.setOpacity(min(1.0, GHOST_OPACITY + 0.4))
                painter.setBrush(Qt.NoBrush)
                painter.setPen(ghost_pen)
                painter.drawPath(path)

                painter.restore()
            except Exception as e:
                print(f"DuplicateMirrorTool: ghost paint failed for button: {e}")

    # ------------------------------------------------------------------
    # Commit — create real mirrored duplicates
    # ------------------------------------------------------------------

    def commit(self):
        if not self.active:
            return

        sources = list(self.source_buttons)
        axis_x = self.axis_x
        canvas = self.canvas

        if not sources:
            self.cancel()
            return

        main_window = canvas.window()
        if not isinstance(main_window, UI.AnimPickerWindow):
            self.cancel()
            return

        try:
            DM.PickerDataManager.save_undo_state(f"Duplicate Mirror {len(sources)} Button(s)")
        except Exception:
            pass

        current_tab = main_window.tab_system.current_tab

        # L/R label swap uses naming conventions only (no namespace/prefs lookup —
        # we're operating on the button label, not on a Maya node name).
        try:
            naming_conventions = canvas._get_naming_conventions("", "")
        except Exception:
            naming_conventions = []

        new_buttons = []
        new_buttons_data = []

        import copy as _copy

        for src in sources:
            unique_id = main_window.generate_unique_id(current_tab)
            if current_tab not in main_window.available_ids:
                main_window.available_ids[current_tab] = set()
            main_window.available_ids[current_tab].add(unique_id)

            # Apply L/R name swap to the duplicate's label so it reads as a counterpart.
            new_label = src.label
            if naming_conventions and src.label:
                try:
                    swapped, _is_center = canvas._find_mirrored_name(src.label, naming_conventions, None, "")
                    new_label = swapped or src.label
                except Exception:
                    new_label = src.label

            new_button = PB.PickerButton(new_label, canvas, unique_id=unique_id)

            new_button.color = src.color
            new_button.opacity = src.opacity
            new_button.selectable = src.selectable
            new_button.width = src.width
            new_button.height = src.height
            new_button.radius = list(src.radius) if isinstance(src.radius, list) else src.radius
            new_button.mode = getattr(src, 'mode', 'select')
            new_button.script_data = _copy.deepcopy(getattr(src, 'script_data', {}) or {})
            new_button.shape_type = getattr(src, 'shape_type', 'rounded_rect')
            new_button.svg_path_data = getattr(src, 'svg_path_data', '') or ''
            new_button.svg_file_path = getattr(src, 'svg_file_path', '') or ''
            new_button.rotation = getattr(src, 'rotation', 0)

            new_button.assigned_objects = _copy.deepcopy(getattr(src, 'assigned_objects', []) or [])

            # Pose-specific data
            if new_button.mode == 'pose':
                thumb = getattr(src, 'thumbnail_path', None)
                if thumb:
                    new_button.thumbnail_path = thumb
                    if os.path.exists(thumb):
                        new_button.thumbnail_pixmap = QtGui.QPixmap(thumb)
                if getattr(src, 'pose_data', None):
                    new_button.pose_data = _copy.deepcopy(src.pose_data)
                if getattr(src, 'animation_data', None):
                    new_button.animation_data = _copy.deepcopy(src.animation_data)

            # Controller-specific data
            if new_button.mode == 'controller' and getattr(src, 'controller_data', None):
                new_button.controller_data = _copy.deepcopy(src.controller_data)
                if new_button.controller_data.get('data_path'):
                    val = new_button._read_controller_value()
                    if val is not None:
                        new_button._controller_value = val
                    else:
                        new_button._controller_value = new_button.controller_data.get('default_value', 0.0)
                    new_button._start_controller_sync()

            # Position starts at the source's position; mirror happens below.
            new_button.scene_position = QPointF(src.scene_position.x(), src.scene_position.y())

            # Add to canvas. Match paste-flow's pattern of suppressing the
            # per-button DB write here — we do a single batch write at the end.
            if hasattr(canvas, 'add_button_without_db_update'):
                canvas.add_button_without_db_update(new_button)
            else:
                old_method = main_window.update_button_data
                main_window.update_button_data = lambda *args, **kwargs: None
                try:
                    canvas.add_button(new_button)
                finally:
                    main_window.update_button_data = old_method

            new_buttons.append(new_button)

            # Database record built post-mirror below (after positions/rotations
            # / svg / assigned_objects are mutated).

        # Switch selection to the new buttons before mirroring.
        canvas.clear_selection()
        for nb in new_buttons:
            nb.is_selected = True
            nb._cached_envelope = None
            nb._cached_envelope_key = None
            nb._cached_scene_path = None
            nb._cached_scene_path_key = None
        canvas.button_selection_changed.emit()

        # Apply position/rotation/SVG/counterpart mirror across the user-chosen axis.
        canvas._apply_mirror_to_buttons(
            new_buttons,
            axis_x,
            apply_counterparts=self.apply_counterparts,
            mirror_rotation=True,
        )

        canvas.button_selection_changed.emit()

        # Build DB records reflecting post-mirror state, then batch-write.
        for nb in new_buttons:
            data = {
                "id": nb.unique_id,
                "selectable": nb.selectable,
                "label": nb.label,
                "color": nb.color,
                "opacity": nb.opacity,
                "position": (nb.scene_position.x(), nb.scene_position.y()),
                "rotation": nb.rotation,
                "width": nb.width,
                "height": nb.height,
                "radius": nb.radius,
                "assigned_objects": nb.assigned_objects,
                "mode": nb.mode,
                "script_data": nb.script_data,
                "shape_type": nb.shape_type,
                "svg_path_data": nb.svg_path_data,
                "svg_file_path": nb.svg_file_path,
            }
            if nb.mode == 'pose':
                if getattr(nb, 'thumbnail_path', None):
                    data["thumbnail_path"] = nb.thumbnail_path
                if getattr(nb, 'pose_data', None):
                    data["pose_data"] = nb.pose_data
                if getattr(nb, 'animation_data', None):
                    data["animation_data"] = nb.animation_data
            if nb.mode == 'controller' and getattr(nb, 'controller_data', None):
                data["controller_data"] = nb.controller_data
            new_buttons_data.append(data)

        if new_buttons_data:
            tab_data = DM.PickerDataManager.get_tab_data(current_tab)
            tab_data['buttons'].extend(new_buttons_data)
            DM.PickerDataManager.batch_update_buttons(current_tab, tab_data['buttons'])
            DM.PickerDataManager.flush_pending_saves()

        canvas.update_button_positions()
        if hasattr(canvas, 'update_hud_counts'):
            canvas.update_hud_counts()
        canvas.update()

        # Tear down tool state
        self.active = False
        self.dragging_line = False
        self._tracking_cursor = False
        self.source_buttons = []
        self.overlay.hide()
        self.canvas.unsetCursor()
        self._restore_distractions()
        self.canvas.update()
