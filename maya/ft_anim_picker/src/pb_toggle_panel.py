"""Toggle Panel for the Maya Script Manager.

Mirror of the Blender implementation. Declarative UI for building
1/2/3-state toggle buttons: each state declares a list of Button Appearance
instances (target buttons + color/label/opacity/selectable) plus an optional
code block to run. ``target_buttons`` is shared across states; the per-state
values diverge. Reducing state_count keeps the dropped state's data in the
dict — re-expanding restores it.
"""

try:
    from PySide6 import QtWidgets, QtCore, QtGui
except ImportError:
    from PySide2 import QtWidgets, QtCore, QtGui

from . import custom_segment_control as CSC
from . import pb_button_appearance_card as PBAC


_SCROLL_STYLE = """
    QScrollArea { background: transparent; border: none; }
    QScrollBar:vertical { border: none; background: transparent; width: 6px; padding-top: 6px; padding-bottom: 6px; padding-right: 4px; }
    QScrollBar::handle:vertical { background: rgba(100,100,100,0.4); border-radius: 3px; min-height: 20px; }
    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0px; }
    QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical { background: transparent; }
"""


_STATE_COUNT_OPTIONS = [(1, "1 State"), (2, "2 States"), (3, "3 States")]
_DEFAULT_STATE_LABELS = ["State 1", "State 2", "State 3"]


class _StateLineEdit(QtWidgets.QLineEdit):
    """Single segment in the editable state-segment widget.

    Click handling: emits ``clicked`` *before* QLineEdit's own mousePress so
    the parent can route selection (and focus the segment) before the cursor
    is positioned.
    """

    clicked = QtCore.Signal()

    def mousePressEvent(self, event):
        if event.button() == QtCore.Qt.LeftButton:
            self.clicked.emit()
        super().mousePressEvent(event)


class _EditableStateSegment(QtWidgets.QFrame):
    """Segment-control-style widget where each segment label is editable.

    Visually mirrors ``TextSegmentControl`` (same frame, same selected
    pill) but each segment is a ``_StateLineEdit``: the active segment is
    editable and highlighted; inactive segments are read-only buttons.
    Clicking an inactive segment selects it; ``label_changed(idx, text)``
    fires on commit (Enter or focus leaving the segment).
    """

    segment_changed = QtCore.Signal(int)
    label_changed = QtCore.Signal(int, str)

    def __init__(self, labels, parent=None):
        super().__init__(parent)
        self.setObjectName("editableStateSegmentFrame")
        self.setStyleSheet("""
            QFrame#editableStateSegmentFrame {
                background: rgba(255, 255, 255, 0.06);
                border-radius: 6px;
                border: none;
            }
        """)
        self.setFixedHeight(28)
        self._segments = []
        self._labels = list(labels)
        self._selected_index = 0

        self._h_layout = QtWidgets.QHBoxLayout(self)
        self._h_layout.setContentsMargins(3, 3, 3, 3)
        self._h_layout.setSpacing(0)

        self._build_segments()

    def _build_segments(self):
        for i, label in enumerate(self._labels):
            seg = self._make_segment(i, label)
            self._segments.append(seg)
            self._h_layout.addWidget(seg)
        self._apply_styles()

    def _make_segment(self, idx, label):
        seg = _StateLineEdit(label)
        seg.setAlignment(QtCore.Qt.AlignCenter)
        seg.setFrame(False)
        seg.setReadOnly(True)
        seg.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Fixed)
        seg.setFixedHeight(22)
        seg.setCursor(QtCore.Qt.PointingHandCursor)
        seg.setMaxLength(40)
        seg.clicked.connect(lambda i=idx: self._on_segment_clicked(i))
        seg.editingFinished.connect(lambda i=idx, w=seg: self._on_segment_committed(i, w))
        return seg

    def _on_segment_clicked(self, idx):
        if idx == self._selected_index:
            return
        self._selected_index = idx
        self._apply_styles()
        self.segment_changed.emit(idx)

    def _on_segment_committed(self, idx, widget):
        if idx >= len(self._labels):
            return
        new_text = widget.text().strip()
        if not new_text:
            widget.blockSignals(True)
            widget.setText(self._labels[idx])
            widget.blockSignals(False)
            return
        if new_text != self._labels[idx]:
            self._labels[idx] = new_text
            self.label_changed.emit(idx, new_text)

    def _apply_styles(self):
        for i, seg in enumerate(self._segments):
            is_active = (i == self._selected_index)
            seg.setReadOnly(not is_active)
            seg.setCursor(QtCore.Qt.IBeamCursor if is_active else QtCore.Qt.PointingHandCursor)
            bg = "#1D65CA" if is_active else "transparent"
            fg = "#dddddd" if is_active else "#999999"
            seg.setStyleSheet(f"""
                QLineEdit {{
                    background: {bg};
                    color: {fg};
                    border: none;
                    border-radius: 6px;
                    padding: 0px 12px;
                    font-size: 11px;
                    selection-background-color: rgba(255, 255, 255, 0.25);
                }}
                QLineEdit:hover {{ color: #dddddd; }}
            """)

    def set_labels(self, labels, selected_index=0):
        for seg in self._segments:
            self._h_layout.removeWidget(seg)
            seg.deleteLater()
        self._segments = []
        self._labels = list(labels)
        if self._labels:
            self._selected_index = max(0, min(int(selected_index), len(self._labels) - 1))
        else:
            self._selected_index = 0
        self._build_segments()

    def set_selected_index(self, index):
        if 0 <= index < len(self._segments):
            self._selected_index = index
            self._apply_styles()

    def get_selected_index(self):
        return self._selected_index

    def get_labels(self):
        return list(self._labels)

_DOTS_BUTTON_STYLE = (
    "QPushButton { background: rgba(255, 255, 255, 0.06); color: #cccccc; "
    "border: none; border-radius: 6px; font-size: 16px; padding-bottom: 4px; }"
    "QPushButton:hover { background: rgba(255, 255, 255, 0.10); color: #ffffff; }"
    "QPushButton:pressed { background: rgba(255, 255, 255, 0.12); }"
)
_MENU_STYLE = (
    "QMenu { background-color: #262626; color: #dddddd; "
    "border: 1px solid #3a3a3a; padding: 4px; }"
    "QMenu::item { padding: 5px 16px; border-radius: 3px; }"
    "QMenu::item:selected { background-color: rgba(255, 255, 255, 0.08); }"
    "QMenu::separator { height: 1px; background: #3a3a3a; margin: 4px 8px; }"
)
# QAction lives in QtGui in PySide6, QtWidgets in PySide2.
_QAction = getattr(QtGui, 'QAction', None) or QtWidgets.QAction


class TogglePanel(QtWidgets.QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._picker_button = None
        self._active_state = 0
        self._current_state_runtime = 0
        self._cards = []
        self._appearance_data = []
        # Per-state, per-language code caches (Maya supports both Python + MEL
        # within the same toggle button). All caches are length 3 so dropped-
        # state data round-trips even when the user is in 1/2-state mode.
        # _state_code_cache kept for legacy call paths; new code reads from
        # the per-language caches.
        self._state_code_cache = ['', '', '']
        self._state_python_code_cache = ['', '', '']
        self._state_mel_code_cache = ['', '', '']
        self._state_languages = ['python', 'python', 'python']
        self._state_labels = list(_DEFAULT_STATE_LABELS)
        self._state_count = 2
        self._build_ui()
        self.set_toggle_data(None)

    def _build_ui(self):
        outer = QtWidgets.QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(8)

        self.setStyleSheet("QWidget { background: 1d1d1d; border: none;}")

        # State selector + state-count dropdown — pinned above the scroll
        # area so the row stays visible while appearance cards scroll.
        self.state_row = QtWidgets.QWidget()
        state_row_layout = QtWidgets.QHBoxLayout(self.state_row)
        state_row_layout.setContentsMargins(4, 4, 4, 4)
        state_row_layout.setSpacing(6)

        self.state_segment = _EditableStateSegment(["State 1", "State 2"])
        self.state_segment.segment_changed.connect(self._on_state_changed)
        self.state_segment.label_changed.connect(self._on_state_label_changed)
        state_row_layout.addWidget(self.state_segment, 1)

        self.state_count_button = QtWidgets.QPushButton("⋯")  # horizontal ellipsis
        self.state_count_button.setFixedSize(28, 28)
        self.state_count_button.setCursor(QtCore.Qt.PointingHandCursor)
        self.state_count_button.setToolTip(
            "Number of states this toggle button cycles through."
        )
        self.state_count_button.setStyleSheet(_DOTS_BUTTON_STYLE)
        self.state_count_button.clicked.connect(self._show_state_count_menu)
        state_row_layout.addWidget(self.state_count_button, 0)

        outer.addWidget(self.state_row)

        self.scroll_area = QtWidgets.QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setFrameShape(QtWidgets.QFrame.NoFrame)
        self.scroll_area.setStyleSheet(_SCROLL_STYLE)
        self.scroll_area.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)
        self.scroll_area.viewport().setAutoFillBackground(False)
        self.scroll_area.setAttribute(QtCore.Qt.WA_TranslucentBackground, False)
        outer.addWidget(self.scroll_area)

        content = QtWidgets.QWidget()
        root = QtWidgets.QVBoxLayout(content)
        root.setContentsMargins(6, 6, 6, 6)
        root.setSpacing(8)
        self.scroll_area.setWidget(content)

        self.list_frame = QtWidgets.QFrame()
        self.list_frame.setFrameShape(QtWidgets.QFrame.NoFrame)
        self.list_frame.setStyleSheet("QFrame { background: transparent; border: none; }")
        list_frame_layout = QtWidgets.QVBoxLayout(self.list_frame)
        list_frame_layout.setContentsMargins(6, 6, 6, 6)
        list_frame_layout.setSpacing(8)

        self._list_layout = QtWidgets.QVBoxLayout()
        self._list_layout.setContentsMargins(0, 0, 0, 0)
        self._list_layout.setSpacing(6)
        list_frame_layout.addLayout(self._list_layout)

        self.add_appearance_btn = QtWidgets.QPushButton("+  Add Button Appearance Control")
        self.add_appearance_btn.setFixedHeight(28)
        self.add_appearance_btn.setCursor(QtCore.Qt.PointingHandCursor)
        self.add_appearance_btn.setStyleSheet("""
            QPushButton {
                background: rgba(255, 255, 255, 0.04);
                color: #cccccc; border: 1px dashed rgba(255,255,255,0.10);
                border-radius: 6px; font-size: 11px;
            }
            QPushButton:hover { background: rgba(255, 255, 255, 0.08); color: #ffffff; }
        """)
        self.add_appearance_btn.clicked.connect(self._on_add_appearance)
        list_frame_layout.addWidget(self.add_appearance_btn)

        root.addWidget(self.list_frame)

        # Per-state code editor — same rounded container pattern as the main
        # Script Manager editor.
        from . import pb_script_manager as PSM

        # Small Python/MEL segment above the editor — independent per state.
        lang_row = QtWidgets.QHBoxLayout()
        lang_row.setContentsMargins(0, 0, 0, 0)
        self.lang_segment = CSC.TextSegmentControl(
            ["Python", "MEL"],
            height=26, font_size=10, radius=4,
            frame_radius=4, use_frame=True,
            frame_bg="rgba(255, 255, 255, 0.06)",
            selected_color="#1D65CA",
            expand=False,
        )
        self.lang_segment.setFixedWidth(120)
        self.lang_segment.segment_changed.connect(self._on_lang_changed)
        lang_row.addWidget(self.lang_segment)
        lang_row.addStretch(1)
        root.addLayout(lang_row)

        self.editor_container = QtWidgets.QFrame()
        self.editor_container.setStyleSheet(PSM.CODE_EDITOR_CONTAINER_STYLE)
        ec_lay = QtWidgets.QVBoxLayout(self.editor_container)
        ec_lay.setContentsMargins(0, 0, 0, 0)
        ec_lay.setSpacing(0)

        self.code_editor = PSM.CodeEditor()
        self.code_editor.setStyleSheet(PSM.CODE_EDITOR_STYLE)
        self.code_editor.setMinimumHeight(120)
        self.code_editor.document().setDocumentMargin(5)
        font = self.code_editor.font()
        fm = QtGui.QFontMetrics(font)
        self.code_editor.setTabStopDistance(fm.horizontalAdvance(' ') * 4)
        self._highlighter = PSM.ScriptSyntaxHighlighter(self.code_editor.document())
        self.code_editor.textChanged.connect(self._on_code_changed)
        ec_lay.addWidget(self.code_editor)
        # Stretch=1 so the editor absorbs extra height when the script
        # manager window grows. Without this, a trailing addStretch ate
        # the slack and the editor stayed at its sizeHint.
        root.addWidget(self.editor_container, 1)

    # ── Public API ──────────────────────────────────────────────────────
    def set_toggle_data(self, toggle_data, picker_button=None):
        self._picker_button = picker_button
        data = dict(toggle_data) if toggle_data else {}
        self._appearance_data = [dict(a) for a in (data.get('appearances') or [])]
        for ap in self._appearance_data:
            ap.setdefault('id', f"ap_{id(ap)}")
            ap.setdefault('name', 'Button Appearance')
            ap.setdefault('target_buttons', [])
            # Always allocate all three state slots so dropped-state data
            # round-trips even when the user is in 1- or 2-state mode.
            ap.setdefault('state_1', dict(PBAC.DEFAULT_STATE))
            ap.setdefault('state_2', dict(PBAC.DEFAULT_STATE))
            ap.setdefault('state_3', dict(PBAC.DEFAULT_STATE))
        # Legacy single-code per state (still mirrored on save for compat)
        self._state_code_cache = [
            data.get('state_1_code', '') or '',
            data.get('state_2_code', '') or '',
            data.get('state_3_code', '') or '',
        ]
        # New per-language caches — fall back to legacy state_X_code for the
        # python slot if no python_code is present (one-time migration).
        self._state_python_code_cache = [
            data.get('state_1_python_code') or data.get('state_1_code', '') or '',
            data.get('state_2_python_code') or data.get('state_2_code', '') or '',
            data.get('state_3_python_code') or data.get('state_3_code', '') or '',
        ]
        self._state_mel_code_cache = [
            data.get('state_1_mel_code', '') or '',
            data.get('state_2_mel_code', '') or '',
            data.get('state_3_mel_code', '') or '',
        ]
        self._state_languages = [
            data.get('state_1_lang', 'python') or 'python',
            data.get('state_2_lang', 'python') or 'python',
            data.get('state_3_lang', 'python') or 'python',
        ]

        # Labels — pad to 3 with defaults so dropped slots round-trip too.
        loaded_labels = list(data.get('state_labels') or [])
        self._state_labels = [
            (loaded_labels[i] if i < len(loaded_labels) and loaded_labels[i] else _DEFAULT_STATE_LABELS[i])
            for i in range(3)
        ]

        self._current_state_runtime = int(data.get('current_state', 0) or 0)
        sc = int(data.get('state_count', 2) or 2)
        self._state_count = max(1, min(3, sc))
        self._active_state = 0
        self._apply_state_count_to_ui()

        self._sync_lang_segment_for_active_state()
        self._rebuild_cards()
        self._load_editor_for_active_state()

    def get_toggle_data(self):
        self._sync_cards_into_data()
        self._sync_editor_into_cache()
        # Mirror active code into legacy state_X_code key for compat (tooltip
        # extraction in pb_script_manager still reads it).
        active_codes = [
            self._state_python_code_cache[i] if self._state_languages[i] == 'python'
            else self._state_mel_code_cache[i]
            for i in range(3)
        ]
        return {
            'state_count': self._state_count,
            'current_state': self._current_state_runtime,
            'state_labels': list(self._state_labels),
            'appearances': [dict(a) for a in self._appearance_data],
            'state_1_code': active_codes[0],
            'state_2_code': active_codes[1],
            'state_3_code': active_codes[2],
            'state_1_python_code': self._state_python_code_cache[0],
            'state_1_mel_code': self._state_mel_code_cache[0],
            'state_1_lang': self._state_languages[0],
            'state_2_python_code': self._state_python_code_cache[1],
            'state_2_mel_code': self._state_mel_code_cache[1],
            'state_2_lang': self._state_languages[1],
            'state_3_python_code': self._state_python_code_cache[2],
            'state_3_mel_code': self._state_mel_code_cache[2],
            'state_3_lang': self._state_languages[2],
        }

    # ── State switching ────────────────────────────────────────────────
    def _on_state_changed(self, index):
        if index == self._active_state:
            return
        if not (0 <= index < self._state_count):
            return
        self._sync_cards_into_data()
        self._sync_editor_into_cache()
        self._active_state = index
        self._populate_cards_from_state()
        self._sync_lang_segment_for_active_state()
        self._load_editor_for_active_state()

    def _show_state_count_menu(self):
        """Pop up the 1/2/3 State picker menu anchored to the dots button."""
        menu = QtWidgets.QMenu(self)
        menu.setStyleSheet(_MENU_STYLE)
        for value, label in _STATE_COUNT_OPTIONS:
            action = _QAction(label, menu)
            action.setCheckable(True)
            action.setChecked(value == self._state_count)
            action.triggered.connect(lambda checked=False, v=value: self._set_state_count(v))
            menu.addAction(action)
        btn = self.state_count_button
        menu.exec_(btn.mapToGlobal(btn.rect().bottomRight() - QtCore.QPoint(menu.sizeHint().width(), 0)))

    def _set_state_count(self, new_count):
        new_count = max(1, min(3, int(new_count)))
        if new_count == self._state_count:
            return
        # Preserve the in-flight edits before reshaping the UI.
        self._sync_cards_into_data()
        self._sync_editor_into_cache()
        self._state_count = new_count
        self._active_state = 0
        self._apply_state_count_to_ui()
        self._populate_cards_from_state()
        self._sync_lang_segment_for_active_state()
        self._load_editor_for_active_state()

    def _apply_state_count_to_ui(self):
        """Reshape the state segment to match self._state_count.

        At 1 state the segment still renders (single 'State 1' button) so
        the layout stays stable; clicking it is a no-op.
        """
        labels = [self._state_labels[i] for i in range(self._state_count)]
        self.state_segment.blockSignals(True)
        self.state_segment.set_labels(labels, selected_index=self._active_state)
        self.state_segment.blockSignals(False)

    def _on_state_label_changed(self, idx, text):
        """User renamed a state inline — persist into our label list."""
        if 0 <= idx < len(self._state_labels):
            self._state_labels[idx] = text or _DEFAULT_STATE_LABELS[idx]

    def _on_lang_changed(self, index):
        new_lang = 'python' if index == 0 else 'mel'
        cur = self._active_state
        if new_lang == self._state_languages[cur]:
            return
        # Capture editor text under the OLD language before swapping.
        self._sync_editor_into_cache()
        self._state_languages[cur] = new_lang
        self._load_editor_for_active_state()

    def _sync_lang_segment_for_active_state(self):
        lang = self._state_languages[self._active_state]
        self.lang_segment.blockSignals(True)
        self.lang_segment.set_selected_index(0 if lang == 'python' else 1)
        self.lang_segment.blockSignals(False)

    # ── Cards ──────────────────────────────────────────────────────────
    def _rebuild_cards(self):
        for card in self._cards:
            card.setParent(None)
            card.deleteLater()
        self._cards = []
        for ap in self._appearance_data:
            card = self._create_card_widget(ap)
            self._cards.append(card)
            self._list_layout.addWidget(card)
        self._populate_cards_from_state()

    def _create_card_widget(self, ap):
        card = PBAC.ButtonAppearanceCard(name=ap.get('name', 'Button Appearance'))
        card.changed.connect(self._on_card_changed)
        card.name_changed.connect(lambda _n, c=card: self._on_card_renamed(c))
        card.delete_requested.connect(self._on_card_delete)
        card.duplicate_requested.connect(self._on_card_duplicate)
        card.move_up_requested.connect(lambda c: self._move_card(c, -1))
        card.move_down_requested.connect(lambda c: self._move_card(c, +1))
        return card

    def _move_card(self, card, offset):
        if card not in self._cards:
            return
        self._sync_cards_into_data()
        i = self._cards.index(card)
        j = i + offset
        if not (0 <= j < len(self._cards)):
            return
        self._cards[i], self._cards[j] = self._cards[j], self._cards[i]
        self._appearance_data[i], self._appearance_data[j] = self._appearance_data[j], self._appearance_data[i]
        self._list_layout.removeWidget(card)
        self._list_layout.insertWidget(j, card)

    def _populate_cards_from_state(self):
        key = f'state_{self._active_state + 1}'
        for card, ap in zip(self._cards, self._appearance_data):
            card.set_state_values(ap.get(key, dict(PBAC.DEFAULT_STATE)))
            card.set_target_buttons(ap.get('target_buttons', []))
            card.set_name(ap.get('name', 'Button Appearance'))

    def _sync_cards_into_data(self):
        key = f'state_{self._active_state + 1}'
        for card, ap in zip(self._cards, self._appearance_data):
            ap[key] = card.get_state_values()
            ap['target_buttons'] = card.get_target_buttons()
            ap['name'] = card.get_name()

    def _on_card_changed(self):
        self._sync_cards_into_data()

    def _on_card_renamed(self, _card):
        self._sync_cards_into_data()

    def _on_card_duplicate(self, card):
        if card not in self._cards:
            return
        self._sync_cards_into_data()
        i = self._cards.index(card)
        if not (0 <= i < len(self._appearance_data)):
            return
        import copy
        src = self._appearance_data[i]
        clone = copy.deepcopy(src)
        clone['id'] = f"ap_{id(clone)}"
        clone['name'] = f"{src.get('name', 'Button Appearance')} (copy)"
        self._appearance_data.insert(i + 1, clone)
        new_card = self._create_card_widget(clone)
        self._cards.insert(i + 1, new_card)
        self._list_layout.insertWidget(i + 1, new_card)
        key = f'state_{self._active_state + 1}'
        new_card.set_state_values(clone.get(key, dict(PBAC.DEFAULT_STATE)))
        new_card.set_target_buttons(clone.get('target_buttons', []))
        new_card.set_name(clone['name'])

    def _on_card_delete(self, card):
        if card not in self._cards:
            return
        i = self._cards.index(card)
        self._cards.pop(i)
        if 0 <= i < len(self._appearance_data):
            self._appearance_data.pop(i)
        card.setParent(None)
        card.deleteLater()

    def _next_default_name(self):
        used = {a.get('name', '') for a in self._appearance_data}
        n = 1
        while True:
            candidate = f"Button Appearance {n:02d}"
            if candidate not in used:
                return candidate, n
            n += 1

    def _on_add_appearance(self):
        name, n = self._next_default_name()
        # Pre-populate shape fields with the source button's current values so
        # new appearance instances start from "as-is" rather than generic
        # defaults — easier to dial in deltas from there.
        base_state = dict(PBAC.DEFAULT_STATE)
        if self._picker_button is not None:
            try:
                base_state['width'] = int(getattr(self._picker_button, 'width', base_state['width']))
                base_state['height'] = int(getattr(self._picker_button, 'height', base_state['height']))
                radius_attr = getattr(self._picker_button, 'radius', None)
                if isinstance(radius_attr, (list, tuple)) and radius_attr:
                    base_state['radius'] = int(radius_attr[0])
                elif radius_attr is not None:
                    base_state['radius'] = int(radius_attr)
                base_state['rotation'] = int(getattr(self._picker_button, 'rotation', base_state['rotation']))
            except Exception:
                pass
        ap = {
            'id': f"ap_{n}_{len(self._appearance_data)}",
            'name': name,
            'target_buttons': [],
            'state_1': dict(base_state),
            'state_2': dict(base_state),
            'state_3': dict(base_state),
        }
        self._appearance_data.append(ap)
        card = self._create_card_widget(ap)
        self._cards.append(card)
        self._list_layout.addWidget(card)
        key = f'state_{self._active_state + 1}'
        card.set_state_values(ap[key])
        card.set_target_buttons(ap['target_buttons'])

    # ── Code editor ────────────────────────────────────────────────────
    def _active_cache(self):
        """Return (cache_list, index) for the currently active state + lang."""
        lang = self._state_languages[self._active_state]
        cache = self._state_python_code_cache if lang == 'python' else self._state_mel_code_cache
        return cache, self._active_state

    def _load_editor_for_active_state(self):
        cache, idx = self._active_cache()
        self.code_editor.blockSignals(True)
        self.code_editor.setPlainText(cache[idx])
        self.code_editor.blockSignals(False)

    def _sync_editor_into_cache(self):
        cache, idx = self._active_cache()
        cache[idx] = self.code_editor.toPlainText()
        # Keep the legacy mirror in sync too.
        self._state_code_cache[idx] = cache[idx]

    def _on_code_changed(self):
        self._sync_editor_into_cache()
