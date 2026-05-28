"""ButtonAppearanceCard — one row in the TogglePanel's appearance list.

Groups the 5 controls for a single Button Appearance instance:
color, label, opacity, selectability, target buttons.

The card represents a *single state* worth of values. When the TogglePanel
switches between State 1 and State 2 it re-populates the card via
``set_state_values`` — ``target_buttons`` is shared between states so it is
managed separately via ``set_target_buttons`` / ``get_target_buttons``.
"""

from PySide6 import QtWidgets, QtCore, QtGui
from PySide6.QtGui import QColor, QAction

from . import utils as UT
from . import custom_button as CB
from . import custom_color_picker as CCP
from . import custom_slider as CS
from . import custom_segment_control as CSC
from . import custom_line_edit as CLE
from . import pb_target_buttons_widget as PTB
from . import pb_rich_tooltip as RT


_TOOLTIPS = {
    'color': (
        "Color",
        "Color applied to targets for this state. Click the swatch to pick; "
        "toggle <b>No color</b> in the popup to skip color on this state.",
    ),
    'label': (
        "Label",
        "Button label for this state. Leave blank to keep each target's "
        "current label unchanged.",
    ),
    'opacity': (
        "Opacity",
        "Button opacity (0&ndash;100%) applied for this state. "
        "Double-click to type a value.",
    ),
    'selectable': (
        "Selectable",
        "Whether targets can be selected in Select Mode while this state "
        "is active.",
    ),
    'target_buttons': (
        "Target Buttons",
        "Buttons this appearance applies to. <b>self</b> means only the "
        "toggle button itself. <b>+</b> adds currently selected canvas "
        "buttons, <b>&minus;</b> removes them, <b>&times;</b> clears all.",
    ),
    'more_options': (
        "More Options",
        "Show additional appearance fields: <b>Text Color</b> and "
        "<b>Text Style</b> (Bold / Italic / Underline).",
    ),
    'text_color': (
        "Text Color",
        "Color of the button label text for this state. Toggle "
        "<b>No color</b> in the popup to skip text color.",
    ),
    'text_style': (
        "Text Style",
        "Override the button text style for this state. Turn the master "
        "switch ON to apply <b>B</b>old, <b>I</b>talic, and <b>U</b>nderline "
        "as configured. Off = leave each target's text style unchanged.",
    ),
    'shape': (
        "Shape",
        "Override the button's physical shape: <b>W</b>idth, <b>H</b>eight, "
        "<b>R</b>adius (corner roundness), and <b>&#x21BB;</b> rotation in "
        "degrees. The transition is animated with a smooth ease.",
    ),
}


class _NoColorToggle(QtWidgets.QAbstractButton):
    """A small 'no color' indicator for the color picker popup.

    Default look: thin-stroke square (color is being applied — not ignored).
    When ``active`` (color is ignored): same square with a red diagonal slash
    across it, the classic 'no color' icon.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setCheckable(True)
        self.setCursor(QtCore.Qt.PointingHandCursor)
        self.setFixedHeight(24)
        self.setFixedWidth(72)
        self.setToolTip("Ignore color — leave target buttons' current color unchanged")

    def paintEvent(self, event):
        p = QtGui.QPainter(self)
        p.setRenderHint(QtGui.QPainter.Antialiasing)
        active = self.isChecked()

        # Background pill
        rect = self.rect().adjusted(1, 1, -1, -1)
        bg = QtGui.QColor(255, 60, 60, 40) if active else QtGui.QColor(255, 255, 255, 18)
        p.setPen(QtCore.Qt.NoPen)
        p.setBrush(bg)
        p.drawRoundedRect(rect, 4, 4)

        # Square glyph on the left
        box = QtCore.QRectF(rect.left() + 5, rect.center().y() - 7, 14, 14)
        stroke_col = QtGui.QColor("#db4040") if active else QtGui.QColor("#aaaaaa")
        p.setPen(QtGui.QPen(stroke_col, 1.4))
        p.setBrush(QtCore.Qt.NoBrush)
        p.drawRect(box)
        if active:
            # Diagonal slash from bottom-left to top-right
            slash_pen = QtGui.QPen(QtGui.QColor("#db4040"), 1.6)
            p.setPen(slash_pen)
            p.drawLine(QtCore.QPointF(box.left(), box.bottom()),
                       QtCore.QPointF(box.right(), box.top()))

        # Label
        p.setPen(QtGui.QColor("#e0a0a0") if active else QtGui.QColor("#bbbbbb"))
        f = p.font()
        # Some fonts come through with pointSize == -1 (pixel-sized) — guard
        # against the QFont warning by only adjusting when point-sized.
        ps = f.pointSizeF()
        if ps > 0:
            f.setPointSizeF(max(0.5, ps - 0.5))
            p.setFont(f)
        text_rect = QtCore.QRectF(box.right() + 6, rect.top(), rect.right() - box.right() - 8, rect.height())
        p.drawText(text_rect, QtCore.Qt.AlignVCenter | QtCore.Qt.AlignLeft, "No color")


class _NoColorOverlay(QtWidgets.QWidget):
    """Translucent overlay drawn on top of a color swatch to indicate the
    color is being ignored: an empty rounded box outline with a diagonal
    cross through it. Click events pass through to the swatch underneath."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(QtCore.Qt.WA_TransparentForMouseEvents, True)
        self.setAttribute(QtCore.Qt.WA_TranslucentBackground, True)

    def paintEvent(self, event):
        p = QtGui.QPainter(self)
        p.setRenderHint(QtGui.QPainter.Antialiasing)
        rect = QtCore.QRectF(self.rect()).adjusted(1.5, 1.5, -1.5, -1.5)
        # Empty rounded box outline
        pen = QtGui.QPen(QtGui.QColor("#cccccc"), 1.5)
        p.setPen(pen)
        p.setBrush(QtGui.QColor(30, 30, 30, 200))
        p.drawRoundedRect(rect, 3, 3)
        # Diagonal cross from bottom-left to top-right (classic "no" symbol)
        p.setPen(QtGui.QPen(QtGui.QColor("#db4040"), 1.6))
        p.drawLine(QtCore.QPointF(rect.left() + 2, rect.bottom() - 2),
                   QtCore.QPointF(rect.right() - 2, rect.top() + 2))


class _DragHandle(QtWidgets.QWidget):
    """A vertical 3-dot handle (two columns of 3 dots). Purely cosmetic for now."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(10, 18)
        self.setCursor(QtCore.Qt.SizeAllCursor)
        self.setToolTip("Drag to reorder")

    def paintEvent(self, event):
        p = QtGui.QPainter(self)
        p.setRenderHint(QtGui.QPainter.Antialiasing)
        p.setPen(QtCore.Qt.NoPen)
        p.setBrush(QtGui.QColor(150, 150, 150, 180))
        r = 1.3
        xs = [2.0, 6.0]
        ys = [3.0, 9.0, 15.0]
        for x in xs:
            for y in ys:
                p.drawEllipse(QtCore.QPointF(x, y), r, r)


DEFAULT_STATE = {
    'color': '#DB2525',
    'color_enabled': False,  # new appearance instances ignore color by default
    'label': '',
    'opacity': 1.0,
    'selectable': True,
    # More Options — additional fields, all "ignore by default" so existing
    # toggles aren't perturbed when the schema gains them.
    'text_color': '#dddddd',
    'text_color_enabled': False,
    'text_style_enabled': False,
    'text_bold': False,
    'text_italic': False,
    'text_underline': False,
    # Shape — width / height / corner radius / rotation. Single master gate so
    # the four physical-shape fields move together.
    'shape_enabled': False,
    'width': 80,
    'height': 30,
    'radius': 3,
    'rotation': 0,
}


class ButtonAppearanceCard(QtWidgets.QFrame):
    changed = QtCore.Signal()              # any field mutated (excludes name)
    name_changed = QtCore.Signal(str)
    delete_requested = QtCore.Signal(object)     # self
    duplicate_requested = QtCore.Signal(object)  # self
    move_up_requested = QtCore.Signal(object)    # self
    move_down_requested = QtCore.Signal(object)  # self

    def __init__(self, name="Button Appearance 01", parent=None):
        super().__init__(parent)
        self._name = name
        self._suppress_signals = False
        self._color_enabled = True
        self._text_color_enabled = False
        self._more_options_expanded = False
        self.setObjectName("appearanceCard")
        self.setFrameShape(QtWidgets.QFrame.NoFrame)
        self.setStyleSheet("""
            QFrame#appearanceCard {
                background: rgba(255, 255, 255, 0.04);
                border: 1px solid rgba(255, 255, 255, 0.08);
                border-radius: 6px;
            }
            QFrame#appearanceCard:hover {
                background: rgba(255, 255, 255, 0.07);
                border: 1px solid rgba(255, 255, 255, 0.14);
            }
        """)
        self.setContextMenuPolicy(QtCore.Qt.DefaultContextMenu)
        self._build_ui()
        # Let right-clicks anywhere on the card surface the card's menu
        self._propagate_context_menu()

    # ── UI ──────────────────────────────────────────────────────────────
    def _build_ui(self):
        outer = QtWidgets.QVBoxLayout(self)
        outer.setContentsMargins(8, 6, 8, 8)
        outer.setSpacing(6)

        # Header row: drag handle + name edit
        header = QtWidgets.QHBoxLayout()
        header.setContentsMargins(0, 0, 0, 0)
        header.setSpacing(6)

        self.drag_handle = _DragHandle()
        header.addWidget(self.drag_handle, 0, QtCore.Qt.AlignVCenter)

        self.name_edit = CLE.FocusLosingLineEdit(self._name)
        self.name_edit.setStyleSheet("""
            QLineEdit {
                background: transparent; color: #dddddd; border: none;
                font-size: 12px; padding: 2px 0px;
            }
            QLineEdit:focus { color: #ffffff; }
        """)
        self.name_edit.editingFinished.connect(self._on_name_edited)
        header.addWidget(self.name_edit, 1)

        # "More options" chevron-toggle on the right of the header row.
        self.more_options_btn = QtWidgets.QToolButton()
        self.more_options_btn.setCheckable(True)
        self.more_options_btn.setCursor(QtCore.Qt.PointingHandCursor)
        self.more_options_btn.setToolButtonStyle(QtCore.Qt.ToolButtonTextOnly)
        self.more_options_btn.setText("\u25B8 More")  # ▸
        self.more_options_btn.setStyleSheet("""
            QToolButton {
                background: transparent; color: #888888;
                border: none; padding: 2px 6px; font-size: 10px;
            }
            QToolButton:hover { color: #cccccc; }
            QToolButton:checked { color: #cccccc; }
        """)
        self.more_options_btn.toggled.connect(self._on_more_options_toggled)
        RT.attach(self.more_options_btn, *_TOOLTIPS['more_options'])
        header.addWidget(self.more_options_btn, 0, QtCore.Qt.AlignVCenter)

        outer.addLayout(header)

        # Controls row — indent roughly in line with the drag handle column
        controls = QtWidgets.QHBoxLayout()
        controls.setContentsMargins(16, 0, 0, 0)
        controls.setSpacing(6)

        # Color — swatch only (hide the inline hex QLineEdit, tighten layout)
        self.color_picker = CCP.ColorPicker(mode='color-popup')
        if hasattr(self.color_picker, 'hex_input'):
            self.color_picker.hex_input.hide()
            self.color_picker.hex_input.setFixedWidth(0)
        # Make the swatch a uniform 22×22 square and collapse surrounding padding
        swatch_size = 22
        if hasattr(self.color_picker, 'color_display'):
            self.color_picker.color_display.setFixedSize(swatch_size, swatch_size)
        for child in self.color_picker.findChildren(QtWidgets.QFrame):
            child.setStyleSheet("background: transparent; border: none; padding: 0px;")
        for child in self.color_picker.findChildren(QtWidgets.QHBoxLayout):
            child.setContentsMargins(0, 0, 0, 0)
            child.setSpacing(0)
        self.color_picker.main_layout.setContentsMargins(0, 0, 0, 0)
        self.color_picker.main_layout.setSpacing(0)
        self.color_picker.setFixedSize(swatch_size, swatch_size)
        self.color_picker.colorChanged.connect(self._on_color_changed)
        # Inject the "No color" toggle at the top of the color picker popup
        self._install_no_color_popup_injector()
        RT.attach(self.color_picker, *_TOOLTIPS['color'])
        controls.addWidget(self.color_picker, 0, QtCore.Qt.AlignVCenter)

        # Label
        self.label_edit = CLE.FocusLosingLineEdit()
        self.label_edit.setPlaceholderText("Text Here")
        self.label_edit.setFixedHeight(22)
        self.label_edit.setStyleSheet("""
            QLineEdit {
                background: rgba(255, 255, 255, 0.06); color: #dddddd;
                border: none; border-radius: 4px; padding: 2px 6px; font-size: 11px;
            }
        """)
        self.label_edit.textChanged.connect(self._emit_changed)
        RT.attach(self.label_edit, *_TOOLTIPS['label'])
        controls.addWidget(self.label_edit, 1)

        # Opacity (0-100 in the UI; stored/applied as 0-1)
        self.opacity_slider = CS.CustomSlider(
            min_value=0, max_value=100, width=70, height=22,
            float_precision=0, radius=4, color="#1D65CA", font_size=10,
            suffix="%",
        )
        self.opacity_slider.valueChanged.connect(self._emit_changed)
        RT.attach(self.opacity_slider, *_TOOLTIPS['opacity'])
        controls.addWidget(self.opacity_slider)

        # Selectable (True / False)
        self.selectable_segment = CSC.TextSegmentControl(
            ["True", "False"],
            height=24, font_size=10, radius=4,
            frame_radius=4, use_frame=True,
            frame_bg="rgba(255, 255, 255, 0.06)",
            selected_color="#1D65CA",
            expand=False,
        )
        self.selectable_segment.setFixedWidth(100)
        self.selectable_segment.segment_changed.connect(self._emit_changed)
        RT.attach(self.selectable_segment, *_TOOLTIPS['selectable'])
        controls.addWidget(self.selectable_segment)

        # Target buttons
        self.target_buttons = PTB.TargetButtonsWidget()
        self.target_buttons.buttons_changed.connect(self._emit_changed)
        RT.attach(self.target_buttons, *_TOOLTIPS['target_buttons'])
        controls.addWidget(self.target_buttons)

        outer.addLayout(controls)

        # ── More Options (hidden by default) ──────────────────────────
        self.extra_row = QtWidgets.QWidget()
        extra_root = QtWidgets.QVBoxLayout(self.extra_row)
        extra_root.setContentsMargins(0, 0, 0, 0)
        extra_root.setSpacing(6)
        extra_layout = QtWidgets.QHBoxLayout()
        extra_layout.setContentsMargins(16, 0, 0, 0)
        extra_layout.setSpacing(6)
        extra_root.addLayout(extra_layout)

        # Text color picker — same compact swatch + No-color popup as the
        # main color picker.
        self.text_color_picker = self._build_compact_color_picker(
            on_changed=self._on_text_color_changed,
        )
        # Install the popup injector AFTER assignment so the helper can read
        # ``self.text_color_picker``.
        self._install_text_no_color_popup_injector()
        RT.attach(self.text_color_picker, *_TOOLTIPS['text_color'])
        extra_layout.addWidget(self.text_color_picker, 0, QtCore.Qt.AlignVCenter)

        # Text style — master enable + B/I/U toggles
        # Group the override toggle + B/I/U buttons in a single frame so they
        # visually read as one control cluster.
        self.text_style_group = QtWidgets.QFrame()
        self.text_style_group.setObjectName("textStyleGroup")
        self.text_style_group.setStyleSheet("""
            QFrame#textStyleGroup {
                background: rgba(255, 255, 255, 0.06);
                border: none;
                border-radius: 6px;
            }
        """)
        ts_layout = QtWidgets.QHBoxLayout(self.text_style_group)
        ts_layout.setContentsMargins(3, 3, 3, 3)
        ts_layout.setSpacing(3)

        self.text_style_enable_segment = CSC.TextSegmentControl(
            ["Off", "On"],
            height=22, font_size=10, radius=4,
            frame_radius=4, use_frame=True,
            frame_bg="rgba(0, 0, 0, 0.18)",
            selected_color="#1D65CA",
            expand=False,
        )
        self.text_style_enable_segment.setFixedWidth(96)
        self.text_style_enable_segment.segment_changed.connect(self._on_text_style_enable_changed)
        RT.attach(self.text_style_enable_segment, *_TOOLTIPS['text_style'])
        ts_layout.addWidget(self.text_style_enable_segment)

        self.bold_btn = self._build_text_style_btn("B", bold=True)
        self.italic_btn = self._build_text_style_btn("I", italic=True)
        self.underline_btn = self._build_text_style_btn("U", underline=True)
        for b in (self.bold_btn, self.italic_btn, self.underline_btn):
            b.toggled.connect(self._emit_changed)
            ts_layout.addWidget(b)

        extra_layout.addWidget(self.text_style_group)

        extra_layout.addStretch(1)

        # Sub-row 2: Shape (W/H/R/Rotation) — single master gate, four fields.
        shape_row = QtWidgets.QHBoxLayout()
        shape_row.setContentsMargins(16, 0, 0, 0)
        shape_row.setSpacing(6)

        self.shape_group = QtWidgets.QFrame()
        self.shape_group.setObjectName("shapeGroup")
        self.shape_group.setStyleSheet("""
            QFrame#shapeGroup {
                background: rgba(255, 255, 255, 0.06);
                border: none; border-radius: 6px;
            }
        """)
        sg_layout = QtWidgets.QHBoxLayout(self.shape_group)
        sg_layout.setContentsMargins(3, 3, 3, 3)
        sg_layout.setSpacing(3)

        self.shape_enable_segment = CSC.TextSegmentControl(
            ["Off", "On"],
            height=22, font_size=10, radius=4,
            frame_radius=4, use_frame=True,
            frame_bg="rgba(0, 0, 0, 0.18)",
            selected_color="#1D65CA",
            expand=False,
        )
        self.shape_enable_segment.setFixedWidth(96)
        self.shape_enable_segment.segment_changed.connect(self._on_shape_enable_changed)
        RT.attach(self.shape_enable_segment, *_TOOLTIPS['shape'])
        sg_layout.addWidget(self.shape_enable_segment)

        self.width_edit = self._build_int_field(label="W", min_v=1, max_v=4000, width=58)
        self.height_edit = self._build_int_field(label="H", min_v=1, max_v=4000, width=58)
        self.radius_edit = self._build_int_field(label="R", min_v=0, max_v=200, width=52)
        self.rotation_edit = self._build_int_field(label="\u21BB", min_v=-180, max_v=180, width=58)
        for e in (self.width_edit, self.height_edit, self.radius_edit, self.rotation_edit):
            e.valueChanged.connect(self._emit_changed)
            sg_layout.addWidget(e)

        shape_row.addWidget(self.shape_group)
        shape_row.addStretch(1)
        extra_root.addLayout(shape_row)

        self.extra_row.setVisible(False)
        outer.addWidget(self.extra_row)

        # Apply defaults
        self.set_state_values(DEFAULT_STATE)

    # ── Signals ─────────────────────────────────────────────────────────
    def _emit_changed(self, *_):
        if self._suppress_signals:
            return
        self.changed.emit()

    def _on_color_changed(self, _qcolor):
        # Any user-driven color change (palette click, hue slider, gradient,
        # hex input) implies the user actually wants color applied — flip
        # "No color" off automatically. _suppress_signals guards the
        # programmatic path in set_state_values.
        if self._suppress_signals:
            return
        if not self._color_enabled:
            self._set_color_enabled(True)
            self._sync_popup_no_color_toggle()
        self._emit_changed()

    def _sync_popup_no_color_toggle(self):
        """If the color picker popup is currently open, reflect the new
        _color_enabled state on the injected _NoColorToggle button."""
        popup = getattr(self.color_picker, 'color_popup_widget', None)
        if popup is None or not popup.isVisible():
            return
        for child in popup.findChildren(_NoColorToggle):
            child.blockSignals(True)
            child.setChecked(not self._color_enabled)
            child.blockSignals(False)
            child.update()

    def _on_name_edited(self):
        new_name = self.name_edit.text().strip() or self._name
        if new_name != self._name:
            self._name = new_name
            self.name_changed.emit(new_name)

    # ── Context menu ────────────────────────────────────────────────────
    def _propagate_context_menu(self):
        """Install an event filter on every descendant so right-clicks surface
        the card's context menu instead of the children's defaults."""
        for w in self.findChildren(QtWidgets.QWidget):
            w.installEventFilter(self)

    def eventFilter(self, obj, event):
        if event.type() == QtCore.QEvent.ContextMenu:
            self.contextMenuEvent(event)
            return True
        return super().eventFilter(obj, event)

    def contextMenuEvent(self, event):
        menu = QtWidgets.QMenu(self)
        menu.setStyleSheet("""
            QMenu { background-color: #262626; color: #dddddd; border: 1px solid #3a3a3a; padding: 4px; }
            QMenu::item { padding: 5px 16px; border-radius: 3px; }
            QMenu::item:selected { background-color: rgba(255, 255, 255, 0.08); }
            QMenu::separator { height: 1px; background: #3a3a3a; margin: 4px 8px; }
        """)
        rename_action = QAction("Rename", self)
        rename_action.triggered.connect(lambda: (self.name_edit.setFocus(), self.name_edit.selectAll()))
        menu.addAction(rename_action)
        duplicate_action = QAction("Duplicate", self)
        duplicate_action.triggered.connect(lambda: self.duplicate_requested.emit(self))
        menu.addAction(duplicate_action)
        menu.addSeparator()
        move_up_action = QAction("Move Up", self)
        move_up_action.triggered.connect(lambda: self.move_up_requested.emit(self))
        menu.addAction(move_up_action)
        move_down_action = QAction("Move Down", self)
        move_down_action.triggered.connect(lambda: self.move_down_requested.emit(self))
        menu.addAction(move_down_action)
        menu.addSeparator()
        delete_action = QAction("Delete", self)
        delete_action.triggered.connect(lambda: self.delete_requested.emit(self))
        menu.addAction(delete_action)
        menu.exec(event.globalPos())

    # ── Compact color picker factory (shared by main color + text color) ──
    def _build_compact_color_picker(self, on_changed):
        """Build a 22×22 swatch-only ColorPicker. Returns the picker; caller
        is responsible for assigning it to ``self`` and then calling its
        no-color popup installer (the installer reads from ``self``)."""
        cp = CCP.ColorPicker(mode='color-popup')
        if hasattr(cp, 'hex_input'):
            cp.hex_input.hide()
            cp.hex_input.setFixedWidth(0)
        swatch_size = 22
        if hasattr(cp, 'color_display'):
            cp.color_display.setFixedSize(swatch_size, swatch_size)
        for child in cp.findChildren(QtWidgets.QFrame):
            child.setStyleSheet("background: transparent; border: none; padding: 0px;")
        for child in cp.findChildren(QtWidgets.QHBoxLayout):
            child.setContentsMargins(0, 0, 0, 0)
            child.setSpacing(0)
        cp.main_layout.setContentsMargins(0, 0, 0, 0)
        cp.main_layout.setSpacing(0)
        cp.setFixedSize(swatch_size, swatch_size)
        cp.colorChanged.connect(on_changed)
        return cp

    def _build_text_style_btn(self, letter, bold=False, italic=False, underline=False):
        btn = QtWidgets.QPushButton(letter)
        btn.setCheckable(True)
        btn.setCursor(QtCore.Qt.PointingHandCursor)
        btn.setFixedSize(22, 22)
        # Style the letter itself so the button visually previews what it does
        weight = "bold" if bold else "normal"
        style = "italic" if italic else "normal"
        deco = "underline" if underline else "none"
        btn.setStyleSheet(f"""
            QPushButton {{
                background: transparent;
                color: #999999;
                border: none; border-radius: 4px;
                font-size: 11px;
                font-weight: {weight};
                font-style: {style};
                text-decoration: {deco};
            }}
            QPushButton:hover {{ color: #ffffff; background: rgba(255, 255, 255, 0.08); }}
            QPushButton:checked {{
                background: #1D65CA; color: #ffffff;
            }}
            QPushButton:disabled {{
                color: #555555; background: transparent;
            }}
        """)
        return btn

    def _on_more_options_toggled(self, checked):
        self._more_options_expanded = bool(checked)
        self.extra_row.setVisible(self._more_options_expanded)
        self.more_options_btn.setText("\u25BE More" if self._more_options_expanded else "\u25B8 More")

    def _on_text_style_enable_changed(self, _idx):
        on = (self.text_style_enable_segment.selected_index == 1)
        self._apply_text_style_enabled(on)
        self._emit_changed()

    def _apply_text_style_enabled(self, on):
        # Visual dim is via the buttons' own `:disabled` stylesheet selectors.
        for b in (self.bold_btn, self.italic_btn, self.underline_btn):
            b.setEnabled(on)

    def _build_int_field(self, label, min_v, max_v, width):
        edit = CLE.IntegerLineEdit(
            min_value=min_v, max_value=max_v, increment=1, precision=0,
            width=width, height=22, label=label,
        )
        edit.setStyleSheet(
            "QLineEdit { background-color: rgba(0,0,0,0.18); color: #eeeeee; "
            "border: none; border-radius: 3px; padding: 2px; font-size: 11px; }"
            "QLineEdit:disabled { color: #555555; background-color: rgba(0,0,0,0.08); }"
        )
        return edit

    def _on_shape_enable_changed(self, _idx):
        on = (self.shape_enable_segment.selected_index == 1)
        self._apply_shape_enabled(on)
        self._emit_changed()

    def _apply_shape_enabled(self, on):
        # Visual dim is via the line-edit `:disabled` stylesheet selector.
        for e in (self.width_edit, self.height_edit, self.radius_edit, self.rotation_edit):
            e.setEnabled(on)

    def _install_no_color_popup_injector(self):
        """Wrap the shared ColorPicker's `_show_color_popup` on this instance
        only, so when the user clicks the swatch our 'No color' toggle is
        prepended to the popup layout."""
        original = self.color_picker._show_color_popup

        def wrapped():
            original()
            self._inject_no_color_toggle()

        self.color_picker._show_color_popup = wrapped

    def _inject_no_color_toggle(self):
        popup = getattr(self.color_picker, 'color_popup_widget', None)
        if popup is None:
            return
        layout = popup.layout()
        if layout is None:
            return
        btn = _NoColorToggle(popup)
        btn.setChecked(not self._color_enabled)
        btn.toggled.connect(self._on_no_color_toggled)
        layout.insertWidget(0, btn)

    def _on_no_color_toggled(self, checked):
        # checked==True means "no color is ON" → color change disabled
        self._set_color_enabled(not checked)
        self._emit_changed()

    def _set_color_enabled(self, enabled):
        """Reflect the 'ignore color' state on the swatch via an overlay
        widget that paints an empty-box-with-cross icon. Swatch stays
        clickable so the popup can re-arm the state."""
        self._color_enabled = bool(enabled)
        display = getattr(self.color_picker, 'color_display', None)
        if display is None:
            return
        overlay = getattr(self, '_color_no_overlay', None)
        if self._color_enabled:
            if overlay is not None:
                overlay.hide()
            self.color_picker.setToolTip("")
        else:
            if overlay is None:
                overlay = _NoColorOverlay(display)
                self._color_no_overlay = overlay
            overlay.setGeometry(display.rect())
            overlay.show()
            overlay.raise_()
            self.color_picker.setToolTip("Color is ignored — click the swatch to change")

    # ── Text color (More Options) ──────────────────────────────────────
    def _install_text_no_color_popup_injector(self):
        original = self.text_color_picker._show_color_popup

        def wrapped():
            original()
            self._inject_text_no_color_toggle()

        self.text_color_picker._show_color_popup = wrapped

    def _inject_text_no_color_toggle(self):
        popup = getattr(self.text_color_picker, 'color_popup_widget', None)
        if popup is None:
            return
        layout = popup.layout()
        if layout is None:
            return
        btn = _NoColorToggle(popup)
        btn.setChecked(not self._text_color_enabled)
        btn.toggled.connect(self._on_text_no_color_toggled)
        layout.insertWidget(0, btn)

    def _on_text_no_color_toggled(self, checked):
        self._set_text_color_enabled(not checked)
        self._emit_changed()

    def _set_text_color_enabled(self, enabled):
        self._text_color_enabled = bool(enabled)
        display = getattr(self.text_color_picker, 'color_display', None)
        if display is None:
            return
        overlay = getattr(self, '_text_color_no_overlay', None)
        if self._text_color_enabled:
            if overlay is not None:
                overlay.hide()
            self.text_color_picker.setToolTip("")
        else:
            if overlay is None:
                overlay = _NoColorOverlay(display)
                self._text_color_no_overlay = overlay
            overlay.setGeometry(display.rect())
            overlay.show()
            overlay.raise_()
            self.text_color_picker.setToolTip("Text color is ignored — click the swatch to change")

    def _on_text_color_changed(self, _qcolor):
        # Same auto-arm behaviour as the main color: any user-driven change
        # implies the user wants text color applied.
        if self._suppress_signals:
            return
        if not self._text_color_enabled:
            self._set_text_color_enabled(True)
            self._sync_text_popup_no_color_toggle()
        self._emit_changed()

    def _sync_text_popup_no_color_toggle(self):
        popup = getattr(self.text_color_picker, 'color_popup_widget', None)
        if popup is None or not popup.isVisible():
            return
        for child in popup.findChildren(_NoColorToggle):
            child.blockSignals(True)
            child.setChecked(not self._text_color_enabled)
            child.blockSignals(False)
            child.update()

    # ── Public API ──────────────────────────────────────────────────────
    def set_name(self, name):
        self._name = name or self._name
        self.name_edit.blockSignals(True)
        self.name_edit.setText(self._name)
        self.name_edit.blockSignals(False)

    def get_name(self):
        return self._name

    def set_state_values(self, state):
        """Populate per-state fields from a state dict."""
        s = dict(DEFAULT_STATE)
        s.update(state or {})
        self._suppress_signals = True
        try:
            # Color
            col = QColor(s.get('color', DEFAULT_STATE['color']))
            if not col.isValid():
                col = QColor(DEFAULT_STATE['color'])
            self.color_picker.current_color = col
            self.color_picker.update_all_from_color()
            self._set_color_enabled(bool(s.get('color_enabled', True)))
            # Label
            self.label_edit.setText(s.get('label', '') or '')
            # Opacity — schema stores 0.0–1.0; slider displays 0–100
            opacity = float(s.get('opacity', 1.0))
            self.opacity_slider.setValue(int(round(opacity * 100)))
            # Selectable
            selectable = bool(s.get('selectable', True))
            self.selectable_segment.set_selected_index(0 if selectable else 1)
            # ── More Options ──
            tcol = QColor(s.get('text_color', DEFAULT_STATE['text_color']))
            if not tcol.isValid():
                tcol = QColor(DEFAULT_STATE['text_color'])
            self.text_color_picker.current_color = tcol
            self.text_color_picker.update_all_from_color()
            self._set_text_color_enabled(bool(s.get('text_color_enabled', False)))

            text_style_on = bool(s.get('text_style_enabled', False))
            self.text_style_enable_segment.set_selected_index(1 if text_style_on else 0)
            self.bold_btn.setChecked(bool(s.get('text_bold', False)))
            self.italic_btn.setChecked(bool(s.get('text_italic', False)))
            self.underline_btn.setChecked(bool(s.get('text_underline', False)))
            self._apply_text_style_enabled(text_style_on)
            # Shape
            shape_on = bool(s.get('shape_enabled', False))
            self.shape_enable_segment.set_selected_index(1 if shape_on else 0)
            self.width_edit.setValue(int(s.get('width', DEFAULT_STATE['width'])))
            self.height_edit.setValue(int(s.get('height', DEFAULT_STATE['height'])))
            self.radius_edit.setValue(int(s.get('radius', DEFAULT_STATE['radius'])))
            self.rotation_edit.setValue(int(s.get('rotation', DEFAULT_STATE['rotation'])))
            self._apply_shape_enabled(shape_on)
        finally:
            self._suppress_signals = False

    def get_state_values(self):
        """Return the full per-state dict (standard + More Options fields)."""
        hex_color = self.color_picker.current_color.name()
        opacity = self.opacity_slider.value() / 100.0
        return {
            'color': hex_color,
            'color_enabled': self._color_enabled,
            'label': self.label_edit.text(),
            'opacity': float(opacity),
            'selectable': self.selectable_segment.selected_index == 0,
            'text_color': self.text_color_picker.current_color.name(),
            'text_color_enabled': self._text_color_enabled,
            'text_style_enabled': self.text_style_enable_segment.selected_index == 1,
            'text_bold': self.bold_btn.isChecked(),
            'text_italic': self.italic_btn.isChecked(),
            'text_underline': self.underline_btn.isChecked(),
            'shape_enabled': self.shape_enable_segment.selected_index == 1,
            'width': int(self.width_edit.value()),
            'height': int(self.height_edit.value()),
            'radius': int(self.radius_edit.value()),
            'rotation': int(self.rotation_edit.value()),
        }

    def set_target_buttons(self, ids):
        self.target_buttons.set_target_buttons(ids or [])

    def get_target_buttons(self):
        return self.target_buttons.target_buttons()
