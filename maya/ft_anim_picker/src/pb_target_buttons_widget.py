"""Target Buttons widget — reusable picker-button list selector.

Used inside ButtonAppearanceCard (toggle-mode Script Manager) and anywhere
else a list of picker-button ``unique_id``s needs to be gathered from the
canvas.
"""

try:
    from PySide6 import QtWidgets, QtCore, QtGui
except ImportError:
    from PySide2 import QtWidgets, QtCore, QtGui

from . import utils as UT
from . import custom_button as CB


class TargetButtonsWidget(QtWidgets.QWidget):
    buttons_changed = QtCore.Signal(list)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._ids = []
        self._popup = None
        self._build_ui()

    def _build_ui(self):
        outer = QtWidgets.QHBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        self._frame = QtWidgets.QFrame()
        self._frame.setObjectName("targetButtonsFrame")
        outer.addWidget(self._frame)

        layout = QtWidgets.QHBoxLayout(self._frame)
        layout.setContentsMargins(3, 3, 3, 3)
        layout.setSpacing(3)

        self.dropdown_btn = QtWidgets.QToolButton()
        self.dropdown_btn.setCursor(QtCore.Qt.PointingHandCursor)
        self.dropdown_btn.setToolButtonStyle(QtCore.Qt.ToolButtonTextBesideIcon)
        self.dropdown_btn.setArrowType(QtCore.Qt.DownArrow)
        self.dropdown_btn.setFixedHeight(18)
        fm = QtGui.QFontMetrics(self.dropdown_btn.font())
        self._dropdown_text_width = fm.horizontalAdvance("self") + 16
        self.dropdown_btn.setFixedWidth(self._dropdown_text_width)
        self.dropdown_btn.clicked.connect(self._toggle_popup)
        layout.addWidget(self.dropdown_btn, 0)

        self.add_btn = CB.CustomButton(
            icon=UT.get_icon('add.png', size=10, opacity=0.9),
            width=18, height=18, radius=9,
            color='#1D65CA', tooltip='Add Selected Buttons',
        )
        self.remove_btn = CB.CustomButton(
            icon=UT.get_icon('subtract.png', size=10, opacity=0.9),
            width=18, height=18, radius=9,
            color='#555555', tooltip='Remove Selected Buttons',
        )
        self.clear_btn = CB.CustomButton(
            icon=UT.get_icon('close_01.png', size=10, opacity=1.0),
            width=18, height=18, radius=9,
            color='#db2525', tooltip='Remove All',
        )
        self.add_btn.clicked.connect(self._on_add_selected)
        self.remove_btn.clicked.connect(self._on_remove_selected)
        self.clear_btn.clicked.connect(self._on_clear)

        layout.addWidget(self.add_btn)
        layout.addWidget(self.remove_btn)
        layout.addWidget(self.clear_btn)

        self._refresh_label()

    # ── Public API ──────────────────────────────────────────────────────
    def set_target_buttons(self, ids):
        self._ids = list(dict.fromkeys(str(x) for x in ids if x))
        self._refresh_label()

    def target_buttons(self):
        return list(self._ids)

    # ── Canvas access ───────────────────────────────────────────────────
    def _find_canvas(self):
        w = self.parent()
        while w is not None:
            if w.__class__.__name__ == 'ScriptManagerWidget':
                pb = getattr(w, 'picker_button', None)
                if pb is not None:
                    return pb.parent()
                break
            w = w.parent()
        return None

    # ── Actions ─────────────────────────────────────────────────────────
    def _on_add_selected(self):
        canvas = self._find_canvas()
        if not canvas:
            return
        selected = canvas.get_selected_buttons() or []
        new_ids = [b.unique_id for b in selected if getattr(b, 'unique_id', None)]
        if not new_ids:
            return
        merged = list(dict.fromkeys(self._ids + new_ids))
        if merged != self._ids:
            self._ids = merged
            self._refresh_label()
            self._refresh_popup()
            self.buttons_changed.emit(list(self._ids))

    def _on_remove_selected(self):
        canvas = self._find_canvas()
        if not canvas:
            return
        selected = canvas.get_selected_buttons() or []
        remove_ids = {b.unique_id for b in selected if getattr(b, 'unique_id', None)}
        if not remove_ids:
            return
        filtered = [i for i in self._ids if i not in remove_ids]
        if filtered != self._ids:
            self._ids = filtered
            self._refresh_label()
            self._refresh_popup()
            self.buttons_changed.emit(list(self._ids))

    def _on_clear(self):
        if not self._ids:
            return
        self._ids = []
        self._refresh_label()
        self._refresh_popup()
        self.buttons_changed.emit([])

    # ── Dropdown popup ──────────────────────────────────────────────────
    def _refresh_label(self):
        n = len(self._ids)
        is_self = (n == 0)
        if is_self:
            full = "self"
            tip = "No targets — this appearance applies to the button itself"
        else:
            full = f"{n} button{'s' if n != 1 else ''}"
            tip = full
        fm = QtGui.QFontMetrics(self.dropdown_btn.font())
        avail = max(10, self.dropdown_btn.width() - 12)
        elided = fm.elidedText(full, QtCore.Qt.ElideRight, avail)
        self.dropdown_btn.setText(elided)
        self.dropdown_btn.setToolTip(tip)
        if is_self:
            self._frame.setStyleSheet("""
                QFrame#targetButtonsFrame {
                    background: rgba(255, 255, 255, 0.05);
                    border: 1px dashed rgba(255, 255, 255, 0.12);
                    border-radius: 6px;
                }
            """)
            self.dropdown_btn.setStyleSheet("""
                QToolButton {
                    background: transparent; color: #888888;
                    border: none; border-radius: 4px;
                    padding: 2px 8px; font-size: 11px; font-style: italic;
                }
                QToolButton:hover { background: rgba(255,255,255,0.06); color: #bbbbbb; }
                QToolButton::menu-indicator { image: none; width: 0px; }
            """)
        else:
            self._frame.setStyleSheet("""
                QFrame#targetButtonsFrame {
                    background: rgba(29, 101, 202, 0.18);
                    border: 1px solid rgba(29, 101, 202, 0.45);
                    border-radius: 6px;
                }
            """)
            self.dropdown_btn.setStyleSheet("""
                QToolButton {
                    background: transparent; color: #9cc6ff;
                    border: none; border-radius: 4px;
                    padding: 2px 8px; font-size: 11px; font-weight: bold;
                }
                QToolButton:hover { background: rgba(255,255,255,0.08); color: #ffffff; }
                QToolButton::menu-indicator { image: none; width: 0px; }
            """)

    def _toggle_popup(self):
        if self._popup is not None and self._popup.isVisible():
            self._popup.hide()
            return
        self._show_popup()

    def _show_popup(self):
        if self._popup is None:
            self._popup = _TargetButtonsPopup(self)
        self._refresh_popup()
        pos = self.dropdown_btn.mapToGlobal(QtCore.QPoint(0, self.dropdown_btn.height()))
        self._popup.move(pos)
        self._popup.resize(max(self.dropdown_btn.width(), 220), 180)
        self._popup.show()
        self._popup.raise_()

    def _refresh_popup(self):
        if self._popup is None:
            return
        canvas = self._find_canvas()
        label_map = {}
        if canvas is not None:
            try:
                for b in (canvas.buttons or []):
                    uid = getattr(b, 'unique_id', None)
                    if uid:
                        label_map[uid] = getattr(b, 'label', '') or uid
            except Exception:
                pass
        self._popup.populate(self._ids, label_map)


class _TargetButtonsPopup(QtWidgets.QFrame):
    def __init__(self, owner):
        super().__init__(None)
        self._owner = owner
        self.setWindowFlags(QtCore.Qt.Popup | QtCore.Qt.FramelessWindowHint)
        self.setAttribute(QtCore.Qt.WA_TranslucentBackground, False)
        self.setStyleSheet("""
            QFrame {
                background: #222222;
                border: 1px solid #444444;
                border-radius: 6px;
            }
            QListWidget {
                background: transparent; color: #cccccc; border: none;
                font-size: 11px; outline: 0;
            }
            QListWidget::item { padding: 4px 8px; }
            QListWidget::item:selected { background: rgba(29, 101, 202, 0.3); color: #ffffff; }
        """)
        lay = QtWidgets.QVBoxLayout(self)
        lay.setContentsMargins(4, 4, 4, 4)
        lay.setSpacing(0)
        self.list_widget = QtWidgets.QListWidget()
        lay.addWidget(self.list_widget)

    def populate(self, ids, label_map):
        self.list_widget.clear()
        if not ids:
            item = QtWidgets.QListWidgetItem("(no buttons)")
            item.setFlags(QtCore.Qt.NoItemFlags)
            item.setForeground(QtGui.QColor("#666666"))
            self.list_widget.addItem(item)
            return
        for uid in ids:
            label = label_map.get(uid, uid)
            text = label if label == uid else f"{label}  [{uid}]"
            item = QtWidgets.QListWidgetItem(text)
            item.setData(QtCore.Qt.UserRole, uid)
            self.list_widget.addItem(item)
