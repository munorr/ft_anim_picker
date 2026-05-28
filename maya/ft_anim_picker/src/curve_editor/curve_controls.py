"""
UI Controls widget for the curve editor.

Provides a toolbar-style widget with:
- Tool selection (Node direct, Shape tools in flyout)
- Point type buttons (Corner, Smooth, Symmetric)
- Mirror controls in flyout panel
- Action buttons (Done, Cancel)

Styled to match TransformControlsWidget for visual consistency.
"""

try:
    from PySide6 import QtWidgets, QtCore, QtGui
    from PySide6.QtCore import QTimer, QPropertyAnimation, QEasingCurve, Signal
except ImportError:
    from PySide2 import QtWidgets, QtCore, QtGui
    from PySide2.QtCore import QTimer, QPropertyAnimation, QEasingCurve, Signal

from .curve_data import PointType
from .curve_tools import EditorTool
from .curve_mirror import MirrorAxis

# Import utils for icons if available
try:
    from .. import utils as UT
    HAS_UTILS = True
except ImportError:
    HAS_UTILS = False


# ==================== Flyout Panel ====================

class FlyoutPanel(QtWidgets.QWidget):
    """
    Small panel that flies out to the right of a trigger button.
    Styled to match the main toolbar. Auto-hides on outside click.
    """

    closed = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        # Embedded child widget (no window flags). Cross-window popups
        # (Qt.Tool / Qt.Popup) lose mouse-event delivery in Maya — clicks on
        # the flyout buttons get routed to the viewport instead. Keeping the
        # flyout as a child of the host window guarantees Qt's parent-child
        # hit testing routes clicks correctly.

        self._frame = QtWidgets.QFrame(self)
        self._frame.setStyleSheet("""
            QFrame {
                background-color: rgba(40, 40, 40, 0.95);
                border: 1px solid rgba(80, 80, 80, 0.8);
                border-radius: 4px;
            }
        """)

        self._layout = QtWidgets.QVBoxLayout(self._frame)
        self._layout.setContentsMargins(5, 5, 5, 5)
        self._layout.setSpacing(4)

        outer = QtWidgets.QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(self._frame)

        self.setVisible(False)
        self._app_filter_installed = False

    @property
    def content_layout(self) -> QtWidgets.QVBoxLayout:
        return self._layout

    def show_beside(self, trigger_btn: QtWidgets.QWidget):
        """Position and show the flyout to the right of the trigger button."""
        # Reparent under the trigger's top-level window so the flyout can
        # extend beyond the controls widget bounds, then position in that
        # window's coordinate space.
        host = trigger_btn.window()
        if host is None:
            return
        if self.parent() is not host:
            self.setParent(host)
        anchor = trigger_btn.mapTo(host, QtCore.QPoint(trigger_btn.width() + 4, 0))
        self.adjustSize()
        self.move(anchor)
        self.setVisible(True)
        self.raise_()
        # Outside-click dismissal via app-level mouse filter.
        if not self._app_filter_installed:
            app = QtWidgets.QApplication.instance()
            if app is not None:
                app.installEventFilter(self)
                self._app_filter_installed = True

    def hideEvent(self, event):
        super().hideEvent(event)
        if self._app_filter_installed:
            app = QtWidgets.QApplication.instance()
            if app is not None:
                app.removeEventFilter(self)
            self._app_filter_installed = False
        self.closed.emit()

    def eventFilter(self, obj, event):
        if event.type() == QtCore.QEvent.MouseButtonPress and self.isVisible():
            if hasattr(event, 'globalPosition'):
                global_pos = event.globalPosition().toPoint()
            else:
                global_pos = event.globalPos()
            local_pos = self.mapFromGlobal(global_pos)
            if not self.rect().contains(local_pos):
                self.setVisible(False)
        return False


# ==================== Main Controls Widget ====================

class CurveEditorControlsWidget(QtWidgets.QWidget):
    """
    Toolbar widget for curve editor controls.

    Layout:
        Node Tool (direct)
        Shape Tools trigger -> flyout (Pen, Rectangle, Ellipse)
        --- separator ---
        Point type buttons (Corner, Smooth, Symmetric)
        --- separator ---
        Mirror trigger -> flyout (toggle, axis)
        --- separator ---
        Done / Cancel
    """

    toolChanged = Signal(object)  # EditorTool
    pointTypeChanged = Signal(object)  # PointType
    mirrorToggled = Signal(bool)
    mirrorAxisChanged = Signal(object)  # MirrorAxis
    editingFinished = Signal()
    editingCancelled = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)

        self.current_tool = EditorTool.NODE
        self.current_point_type = PointType.SMOOTH
        self._current_mirror_axis = MirrorAxis.VERTICAL

        # Widget setup
        self.setFixedWidth(38)
        self.setup_ui()
        self.setVisible(False)

        self.setAttribute(QtCore.Qt.WA_StyledBackground, True)
        self.setMouseTracking(True)

    # ==================== UI Setup ====================

    def setup_ui(self):
        """Set up the UI layout and widgets."""
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addStretch()

        # Main frame
        self.frame = QtWidgets.QFrame()
        self.frame.setStyleSheet("""
            QFrame {
                background-color: rgba(40, 40, 40, 0.95);
                border: 1px solid rgba(80, 80, 80, 0.8);
                border-radius: 4px;
            }
        """)
        layout.addWidget(self.frame)

        frame_layout = QtWidgets.QVBoxLayout(self.frame)
        frame_layout.setContentsMargins(6, 6, 6, 6)
        frame_layout.setSpacing(6)

        # -- Tool buttons (Node direct + Shapes flyout trigger) --
        self.tool_buttons = {}
        self.tool_group = QtWidgets.QButtonGroup(self)
        self.tool_group.setExclusive(True)

        # Node tool -- always visible
        node_btn = self._create_tool_button('A', 'Node Tool (A) - Select and edit points', icon_file='point-arrow-icon.png')
        node_btn.setCheckable(True)
        node_btn.setChecked(True)
        node_btn.clicked.connect(lambda checked: self._on_tool_clicked(EditorTool.NODE))
        self.tool_group.addButton(node_btn)
        self.tool_buttons[EditorTool.NODE] = node_btn
        frame_layout.addWidget(node_btn)

        # Shape tools trigger button -- shows the currently-selected shape tool icon
        self._shape_tools_data = [
            (EditorTool.PEN, 'P', 'Pen Tool (P) - Draw new paths', 'pen-tool-icon.png'),
            (EditorTool.RECTANGLE, 'R', 'Rectangle (R) - Draw rectangles', 'draw-rectangle-icon.png'),
            (EditorTool.ELLIPSE, 'O', 'Ellipse (O) - Draw ellipses', 'draw-elipses-icon.png'),
        ]
        self._active_shape_tool = EditorTool.PEN  # default shape tool

        self.shape_trigger_btn = self._create_tool_button(
            'P', 'Shape Tools - Click to expand',
            icon_file='pen-tool-icon.png'
        )
        self.shape_trigger_btn.setCheckable(True)
        self.shape_trigger_btn.setChecked(False)
        self.tool_group.addButton(self.shape_trigger_btn)
        self.shape_trigger_btn.clicked.connect(self._on_shape_trigger_clicked)
        frame_layout.addWidget(self.shape_trigger_btn)

        # Build shape tools flyout
        self._shape_flyout = FlyoutPanel(self.parent())
        self._shape_flyout_buttons = {}
        flyout_tool_group = QtWidgets.QButtonGroup(self._shape_flyout)
        flyout_tool_group.setExclusive(True)
        self._flyout_tool_group = flyout_tool_group

        for tool, shortcut, tooltip, icon_file in self._shape_tools_data:
            btn = self._create_tool_button(shortcut, tooltip, icon_file=icon_file)
            btn.setCheckable(True)
            btn.setChecked(tool == self._active_shape_tool)
            btn.clicked.connect(lambda checked, t=tool: self._on_shape_flyout_tool_clicked(t))
            flyout_tool_group.addButton(btn)
            self._shape_flyout_buttons[tool] = btn
            self._shape_flyout.content_layout.addWidget(btn)
            # Also register in main tool_buttons dict for set_tool()
            self.tool_buttons[tool] = btn

        self._shape_flyout.closed.connect(self._on_shape_flyout_closed)

        # Separator
        frame_layout.addWidget(self._create_separator())

        # -- Point Type Buttons --
        self.point_type_buttons = {}
        self.point_type_group = QtWidgets.QButtonGroup(self)
        self.point_type_group.setExclusive(True)

        point_types = [
            (PointType.CORNER, '\u2b1c', 'Corner Point (Ctrl+Click) - Independent handles\nAlt+Click: Remove handles (sharp corner)\nCtrl+Shift+Click: Align linearly', 'independent-handle-icon.png'),
            (PointType.SMOOTH, '\u25ef', 'Smooth Point (Shift+Click) - Colinear handles, curved', 'colinear-handle-icon.png'),
            (PointType.SYMMETRIC, '\u25c9', 'Symmetric Point - Mirrored handles', 'mirrored-handle-icon.png'),
        ]

        for pt, symbol, tooltip, icon_file in point_types:
            btn = self._create_tool_button(symbol, tooltip, size=16, icon_file=icon_file)
            btn.setCheckable(True)
            btn.setChecked(pt == self.current_point_type)
            btn.clicked.connect(lambda checked, p=pt: self._on_point_type_clicked(p))
            self.point_type_group.addButton(btn)
            self.point_type_buttons[pt] = btn
            frame_layout.addWidget(btn)

        # Separator
        frame_layout.addWidget(self._create_separator())

        # -- Mirror trigger button --
        self.mirror_trigger_btn = self._create_tool_button('', 'Mirror Mode (M) - Click to expand', icon_file='mirror_icon.png')
        self.mirror_trigger_btn.setCheckable(True)
        self.mirror_trigger_btn.setChecked(False)
        self.mirror_trigger_btn.clicked.connect(self._on_mirror_trigger_clicked)
        frame_layout.addWidget(self.mirror_trigger_btn)

        # Build mirror flyout
        self._mirror_flyout = FlyoutPanel(self.parent())

        self.mirror_btn = self._create_tool_button('On', 'Toggle Mirror Mode')
        self.mirror_btn.setCheckable(True)
        self.mirror_btn.setChecked(False)
        self.mirror_btn.clicked.connect(self._on_mirror_toggled)
        self._mirror_flyout.content_layout.addWidget(self.mirror_btn)

        self.mirror_axis_btn = self._create_tool_button('|', 'Mirror Axis: Vertical (click to toggle)')
        self.mirror_axis_btn.setCheckable(False)
        self.mirror_axis_btn.setEnabled(False)
        self.mirror_axis_btn.clicked.connect(self._on_mirror_axis_clicked)
        self._mirror_flyout.content_layout.addWidget(self.mirror_axis_btn)

        self._mirror_flyout.closed.connect(self._on_mirror_flyout_closed)

        # Separator
        frame_layout.addWidget(self._create_separator())

        # -- Action Buttons --
        self.done_btn = QtWidgets.QPushButton("\u2713")
        self.done_btn.setFixedSize(24, 24)
        self.done_btn.setToolTip("Apply Changes (Enter)")
        self.done_btn.setStyleSheet(self._get_action_button_style('#4CAF50'))
        self.done_btn.clicked.connect(self._on_done_clicked)
        frame_layout.addWidget(self.done_btn)

        self.cancel_btn = QtWidgets.QPushButton("\u2715")
        self.cancel_btn.setFixedSize(24, 24)
        self.cancel_btn.setToolTip("Cancel (Escape)")
        self.cancel_btn.setStyleSheet(self._get_action_button_style('#f44336'))
        self.cancel_btn.clicked.connect(self._on_cancel_clicked)
        frame_layout.addWidget(self.cancel_btn)

        layout.addStretch()

    # ==================== Widget Factories ====================

    def _create_tool_button(self, text: str, tooltip: str, size: int = 18, icon_file: str = None) -> QtWidgets.QPushButton:
        """Create a styled tool button."""
        btn = QtWidgets.QPushButton(text)
        btn.setFixedSize(24, 24)
        btn.setToolTip(tooltip)

        if icon_file and HAS_UTILS:
            try:
                icon_pixmap = UT.get_icon(icon_file, size=16, opacity=0.9)
                btn.setIcon(QtGui.QIcon(icon_pixmap))
                btn.setText("")
            except:
                pass

        btn.setStyleSheet("""
            QPushButton {
                background-color: rgba(60, 60, 60, 0);
                border: 0px solid rgba(100, 100, 100, 150);
                border-radius: 3px;
                padding: 2px;
                color: #cccccc;
                font-size: 11px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: rgba(80, 80, 80, 220);
                border: 0px solid rgba(120, 120, 120, 180);
                color: #ffffff;
            }
            QPushButton:checked {
                background-color: rgba(75, 148, 234, 200);
                border: 0px solid rgba(100, 170, 255, 200);
                color: #ffffff;
            }
            QPushButton:pressed {
                background-color: rgba(50, 50, 50, 250);
            }
        """)
        return btn

    def _create_separator(self) -> QtWidgets.QFrame:
        """Create a horizontal separator line."""
        sep = QtWidgets.QFrame()
        sep.setFrameShape(QtWidgets.QFrame.HLine)
        sep.setFixedHeight(1)
        sep.setStyleSheet("background-color: rgba(100, 100, 100, 100);")
        return sep

    def _get_action_button_style(self, color: str) -> str:
        """Get stylesheet for action buttons (Done/Cancel)."""
        return f"""
            QPushButton {{
                background-color: {color};
                color: white;
                border: none;
                border-radius: 3px;
                font-weight: bold;
                font-size: 13px;
            }}
            QPushButton:hover {{
                background-color: {color};
                border: 1px solid rgba(255, 255, 255, 0.3);
            }}
            QPushButton:pressed {{
                background-color: {color};
            }}
        """

    # ==================== Shape Tools Flyout ====================

    def _on_shape_trigger_clicked(self, checked):
        """Toggle shape tools flyout panel."""
        if self._shape_flyout.isVisible():
            self._shape_flyout.setVisible(False)
        else:
            self._close_all_flyouts()
            self._shape_flyout.show_beside(self.shape_trigger_btn)
        # Activate the last-used shape tool
        self._on_tool_clicked(self._active_shape_tool)

    def _on_shape_flyout_tool_clicked(self, tool: EditorTool):
        """Handle shape tool selection from the flyout."""
        self._active_shape_tool = tool
        # Update the trigger button icon/text to match selected tool
        for t, shortcut, tooltip, icon_file in self._shape_tools_data:
            if t == tool:
                self.shape_trigger_btn.setToolTip(tooltip)
                if icon_file and HAS_UTILS:
                    try:
                        icon_pixmap = UT.get_icon(icon_file, size=16, opacity=0.9)
                        self.shape_trigger_btn.setIcon(QtGui.QIcon(icon_pixmap))
                        self.shape_trigger_btn.setText("")
                    except:
                        self.shape_trigger_btn.setText(shortcut)
                else:
                    self.shape_trigger_btn.setText(shortcut)
                break
        # Ensure trigger button shows as checked (it's the active tool)
        self.shape_trigger_btn.setChecked(True)
        self._on_tool_clicked(tool)
        self._shape_flyout.setVisible(False)

    def _on_shape_flyout_closed(self):
        """Handle shape flyout close -- keep trigger checked if a shape tool is active."""
        if self.current_tool not in (EditorTool.PEN, EditorTool.RECTANGLE, EditorTool.ELLIPSE):
            self.shape_trigger_btn.setChecked(False)

    # ==================== Mirror Flyout ====================

    def _on_mirror_trigger_clicked(self, checked):
        """Toggle mirror flyout panel."""
        if self._mirror_flyout.isVisible():
            self._mirror_flyout.setVisible(False)
        else:
            self._close_all_flyouts()
            self._mirror_flyout.show_beside(self.mirror_trigger_btn)

    def _on_mirror_toggled(self, checked: bool):
        """Handle mirror toggle button click."""
        self.mirror_axis_btn.setEnabled(checked)
        # Update trigger button visual
        self.mirror_trigger_btn.setChecked(checked)
        self.mirrorToggled.emit(checked)

    def _on_mirror_axis_clicked(self):
        """Toggle between vertical and horizontal mirror axis."""
        if self._current_mirror_axis == MirrorAxis.VERTICAL:
            self._current_mirror_axis = MirrorAxis.HORIZONTAL
            self.mirror_axis_btn.setText('\u2014')
            self.mirror_axis_btn.setToolTip('Mirror Axis: Horizontal (click to toggle)')
        else:
            self._current_mirror_axis = MirrorAxis.VERTICAL
            self.mirror_axis_btn.setText('|')
            self.mirror_axis_btn.setToolTip('Mirror Axis: Vertical (click to toggle)')
        self.mirrorAxisChanged.emit(self._current_mirror_axis)

    def _on_mirror_flyout_closed(self):
        """Handle mirror flyout close -- keep trigger checked if mirror is active."""
        if not self.mirror_btn.isChecked():
            self.mirror_trigger_btn.setChecked(False)

    # ==================== General Signal Handlers ====================

    def _on_tool_clicked(self, tool: EditorTool):
        """Handle tool activation."""
        self.current_tool = tool
        self.toolChanged.emit(tool)

    def _on_point_type_clicked(self, point_type: PointType):
        """Handle point type button click."""
        self.current_point_type = point_type
        self.pointTypeChanged.emit(point_type)

    def _on_done_clicked(self):
        self.editingFinished.emit()

    def _on_cancel_clicked(self):
        self.editingCancelled.emit()

    # ==================== Flyout Helpers ====================

    def _close_all_flyouts(self):
        """Close all open flyout panels."""
        self._shape_flyout.setVisible(False)
        self._mirror_flyout.setVisible(False)

    # ==================== External Control Methods ====================

    def set_tool(self, tool: EditorTool):
        """Programmatically set the active tool."""
        self.current_tool = tool
        if tool == EditorTool.NODE:
            self.tool_buttons[EditorTool.NODE].setChecked(True)
            self.shape_trigger_btn.setChecked(False)
        elif tool in (EditorTool.PEN, EditorTool.RECTANGLE, EditorTool.ELLIPSE):
            self._active_shape_tool = tool
            self.shape_trigger_btn.setChecked(True)
            # Update trigger icon
            for t, shortcut, tooltip, icon_file in self._shape_tools_data:
                if t == tool:
                    self.shape_trigger_btn.setToolTip(tooltip)
                    if icon_file and HAS_UTILS:
                        try:
                            icon_pixmap = UT.get_icon(icon_file, size=16, opacity=0.9)
                            self.shape_trigger_btn.setIcon(QtGui.QIcon(icon_pixmap))
                            self.shape_trigger_btn.setText("")
                        except:
                            self.shape_trigger_btn.setText(shortcut)
                    else:
                        self.shape_trigger_btn.setText(shortcut)
                    break
            # Update flyout radio state
            if tool in self._shape_flyout_buttons:
                self._shape_flyout_buttons[tool].setChecked(True)

    def set_point_type(self, point_type: PointType):
        """Programmatically set the point type."""
        self.current_point_type = point_type
        if point_type in self.point_type_buttons:
            self.point_type_buttons[point_type].setChecked(True)

    def set_mirror_enabled(self, enabled: bool):
        """Programmatically set mirror mode state."""
        self.mirror_btn.setChecked(enabled)
        self.mirror_axis_btn.setEnabled(enabled)
        self.mirror_trigger_btn.setChecked(enabled)

    def set_mirror_axis(self, axis: MirrorAxis):
        """Programmatically set mirror axis."""
        self._current_mirror_axis = axis
        if axis == MirrorAxis.VERTICAL:
            self.mirror_axis_btn.setText('|')
            self.mirror_axis_btn.setToolTip('Mirror Axis: Vertical (click to toggle)')
        else:
            self.mirror_axis_btn.setText('\u2014')
            self.mirror_axis_btn.setToolTip('Mirror Axis: Horizontal (click to toggle)')

    def update_from_selection(self, selected_points):
        """
        Update point type display based on selected points.

        Args:
            selected_points: List of (path, point, path_idx, point_idx) tuples
        """
        if not selected_points:
            return
        _, point, _, _ = selected_points[0]
        self.set_point_type(point.point_type)

    def update_position(self, target_rect: QtCore.QRectF):
        """Update widget position to appear to the left of the target rectangle."""
        if not self.isVisible():
            return
        parent = self.parent()
        if not parent:
            return
        widget_height = self.sizeHint().height()
        new_x = target_rect.left() - self.width() - 8
        new_y = target_rect.center().y() - widget_height / 2
        parent_rect = parent.rect()
        if new_x < 0:
            new_x = target_rect.right() + 8
        if new_y < 0:
            new_y = 0
        if new_y + widget_height > parent_rect.height():
            new_y = parent_rect.height() - widget_height
        self.move(int(new_x), int(new_y))

    def position_at_left(self, parent_height: int):
        """Position widget vertically centered on the left side of parent."""
        widget_height = self.sizeHint().height()
        new_y = (parent_height - widget_height) / 2
        self.move(8, int(new_y))

    # ==================== Event Handling ====================

    def showEvent(self, event):
        """Raise widget to top when shown."""
        super().showEvent(event)
        self.raise_()

    def hideEvent(self, event):
        """Close flyouts when the controls widget hides."""
        self._close_all_flyouts()
        super().hideEvent(event)

    def mousePressEvent(self, event):
        event.accept()
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        event.accept()
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        event.accept()
        super().mouseReleaseEvent(event)

    # ==================== Fade Animation ====================

    def handle_enter_event(self):
        """Handle mouse entering widget - stop fade and show full opacity."""
        self.fade_timer.stop()
        self.fade_animation.stop()
        self.fade_animation.setDuration(100)
        self.fade_animation.setStartValue(self.opacity_effect.opacity())
        self.fade_animation.setEndValue(1.0)
        self.fade_animation.start()

    def handle_leave_event(self):
        """Handle mouse leaving widget - start fade timer."""
        self.fade_timer.start(800)
