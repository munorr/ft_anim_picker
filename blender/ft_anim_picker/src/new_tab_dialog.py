"""
New Tab Dialog – Premium dialog for creating blank tabs or from templates.

Shows a name input + Blank/Template toggle. When "From Template" is active,
a scrollable grid of template thumbnails is displayed for selection.
"""

from pathlib import Path

from PySide6 import QtWidgets, QtCore, QtGui
from PySide6.QtCore import QPropertyAnimation, QEasingCurve, QParallelAnimationGroup

from . import bpicker_format as BPF
from . import utils as UT
from .config.settings import TEMPLATE_DIR
from .custom_segment_control import TextSegmentControl


# -- Colour tokens (matches controller_manager / settings_page) ---------------
_BG         = "#1e1e1e"
_BORDER     = "rgba(255,255,255,0.06)"
_TEXT_MAIN  = "#e0e0e0"
_TEXT_SUB   = "#808080"
_TEXT_MUTED = "#666666"
_ACCENT     = "rgba(29,101,202,{a})"
_ACCENT_SEL = "rgba(29,101,202,0.6)"
_ACCENT_BG  = "rgba(29,101,202,0.25)"
_SURFACE    = "rgba(255,255,255,.1)"
_CARD_BG    = "rgba(50,50,50,0.2)"
_INPUT_BG   = "rgba(50, 50, 50, 0.8)"
_INPUT_BORDER = "#3a3a3a"

_DLG_W = 280
_BLANK_H = 190
_TPL_H = 340
_CARD_W = 80
_CARD_H = 100
_THUMB_SIZE = 72


# ---------------------------------------------------------------------------
# Template discovery
# ---------------------------------------------------------------------------

def _discover_templates():
    """Scan the templates folder for .bpicker files.

    Returns:
        list[dict] – each dict has keys: path, name, tab_count, preview_bytes.
    """
    templates = []
    tpl_dir = Path(TEMPLATE_DIR)
    if not tpl_dir.is_dir():
        return templates

    for f in sorted(tpl_dir.iterdir()):
        if f.suffix.lower() != ".bpicker":
            continue
        try:
            info = BPF.BPickerArchive.read(str(f))
            preview_bytes = BPF.BPickerArchive.extract_media(str(f), "cache/preview.png")
            templates.append({
                "path": str(f),
                "name": info["metadata"].get("picker_name", f.stem).replace("Tab: ", ""),
                "tab_count": len(info["manifest"].get("tabs", {})),
                "preview_bytes": preview_bytes,
            })
        except Exception:
            pass

    return templates


# ---------------------------------------------------------------------------
# Shared stylesheet helpers
# ---------------------------------------------------------------------------

def _input_ss():
    return f"""
        QLineEdit {{
            background: {_INPUT_BG};
            color: {_TEXT_MAIN};
            border: 1px solid {_INPUT_BORDER};
            border-radius: 6px;
            padding: 3px 8px;
            font-size: 11px;
        }}
        QLineEdit:focus {{
            border: 1px solid {_ACCENT_SEL};
        }}
        QLineEdit::placeholder {{
            color: {_TEXT_MUTED};
        }}
    """


def _card():
    """Create a styled card QFrame matching codebase pattern."""
    card = QtWidgets.QFrame()
    card.setStyleSheet(f"""
        QFrame {{
            background: {_CARD_BG};
            border: 1px solid {_BORDER};
            border-radius: 8px;
        }}
    """)
    return card


# ---------------------------------------------------------------------------
# _TemplateCard
# ---------------------------------------------------------------------------

class _TemplateCard(QtWidgets.QFrame):
    """Clickable thumbnail card representing a template .bpicker."""

    clicked = QtCore.Signal(str)  # emits template path
    delete_requested = QtCore.Signal(str)  # emits template path

    def __init__(self, tpl_info, parent=None):
        super().__init__(parent)
        self._path = tpl_info["path"]
        self._selected = False
        self.setContextMenuPolicy(QtCore.Qt.CustomContextMenu)
        self.customContextMenuRequested.connect(self._show_context_menu)

        self.setFixedSize(_CARD_W, _CARD_H)
        self.setCursor(QtCore.Qt.PointingHandCursor)
        self._update_style()

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(4)

        # Thumbnail
        self._thumb = QtWidgets.QLabel()
        self._thumb.setFixedSize(_THUMB_SIZE, _THUMB_SIZE)
        self._thumb.setAlignment(QtCore.Qt.AlignCenter)
        self._thumb.setStyleSheet(
            f"background: rgba(50,50,50,0.6); border-radius: 6px; border: none;"
        )
        self._set_preview(tpl_info)
        layout.addWidget(self._thumb, alignment=QtCore.Qt.AlignCenter)

        # Name label
        name = tpl_info["name"]
        if len(name) > 14:
            name = name[:12] + "..."
        lbl = QtWidgets.QLabel(name)
        lbl.setAlignment(QtCore.Qt.AlignCenter)
        lbl.setStyleSheet(
            "color: #cccccc; font-size: 10px; background: transparent; border: none;"
        )
        layout.addWidget(lbl)

    # ------------------------------------------------------------------ #

    def _set_preview(self, tpl_info):
        preview_bytes = tpl_info.get("preview_bytes")
        if preview_bytes:
            pixmap = QtGui.QPixmap()
            pixmap.loadFromData(preview_bytes)
            if not pixmap.isNull():
                scaled = pixmap.scaled(
                    _THUMB_SIZE, _THUMB_SIZE,
                    QtCore.Qt.KeepAspectRatio,
                    QtCore.Qt.SmoothTransformation,
                )
                self._thumb.setPixmap(scaled)
                return

        # Fallback: initials
        name = tpl_info["name"]
        initials = "".join(w[0].upper() for w in name.split()[:2]) or "T"
        self._thumb.setText(initials)
        self._thumb.setStyleSheet(
            "background: rgba(50,50,50,0.6); border-radius: 6px; border: none; "
            "color: #999999; font-size: 16px; font-weight: bold;"
        )

    def set_selected(self, selected):
        self._selected = selected
        self._update_style()

    def _update_style(self):
        if self._selected:
            self.setStyleSheet(
                f"QFrame {{ background: {_ACCENT_BG}; "
                f"border: 1px solid {_ACCENT_SEL}; border-radius: 8px; }}"
            )
        else:
            self.setStyleSheet(
                "QFrame { background: transparent; "
                "border: 1px solid transparent; border-radius: 8px; }"
            )

    def mousePressEvent(self, event):
        self.clicked.emit(self._path)
        super().mousePressEvent(event)

    def enterEvent(self, event):
        if not self._selected:
            self.setStyleSheet(
                "QFrame { background: rgba(255,255,255,0.08); "
                "border: 1px solid rgba(255,255,255,0.12); border-radius: 8px; }"
            )
        super().enterEvent(event)

    def leaveEvent(self, event):
        self._update_style()
        super().leaveEvent(event)

    def _show_context_menu(self, pos):
        menu = QtWidgets.QMenu(self)
        menu.setStyleSheet(f"""
            QMenu {{
                background: {_BG};
                border: 1px solid rgba(255,255,255,0.1);
                border-radius: 6px;
                padding: 4px 0;
            }}
            QMenu::item {{
                color: #e06060;
                font-size: 11px;
                padding: 5px 16px;
                background: transparent;
            }}
            QMenu::item:hover {{
                background: rgba(255,80,80,0.15);
            }}
        """)
        delete_action = menu.addAction("Delete Template")
        action = menu.exec_(self.mapToGlobal(pos))
        if action == delete_action:
            self.delete_requested.emit(self._path)


# ---------------------------------------------------------------------------
# _FlowLayout – simple flow/wrap layout for template cards
# ---------------------------------------------------------------------------

class _FlowLayout(QtWidgets.QLayout):
    """Horizontal wrap layout – items flow left-to-right, wrapping as needed."""

    def __init__(self, parent=None, spacing=6):
        super().__init__(parent)
        self._items = []
        self._spacing = spacing

    def addItem(self, item):
        self._items.append(item)

    def count(self):
        return len(self._items)

    def itemAt(self, index):
        if 0 <= index < len(self._items):
            return self._items[index]
        return None

    def takeAt(self, index):
        if 0 <= index < len(self._items):
            return self._items.pop(index)
        return None

    def hasHeightForWidth(self):
        return True

    def heightForWidth(self, width):
        return self._do_layout(QtCore.QRect(0, 0, width, 0), test_only=True)

    def setGeometry(self, rect):
        super().setGeometry(rect)
        self._do_layout(rect)

    def sizeHint(self):
        return self.minimumSize()

    def minimumSize(self):
        size = QtCore.QSize()
        for item in self._items:
            size = size.expandedTo(item.minimumSize())
        m = self.contentsMargins()
        size += QtCore.QSize(m.left() + m.right(), m.top() + m.bottom())
        return size

    def _do_layout(self, rect, test_only=False):
        x = rect.x()
        y = rect.y()
        line_height = 0

        for item in self._items:
            w = item.sizeHint().width()
            h = item.sizeHint().height()
            next_x = x + w + self._spacing
            if next_x - self._spacing > rect.right() and line_height > 0:
                x = rect.x()
                y += line_height + self._spacing
                next_x = x + w + self._spacing
                line_height = 0
            if not test_only:
                item.setGeometry(QtCore.QRect(QtCore.QPoint(x, y), item.sizeHint()))
            x = next_x
            line_height = max(line_height, h)

        return y + line_height - rect.y()


# ---------------------------------------------------------------------------
# NewTabDialog
# ---------------------------------------------------------------------------

class NewTabDialog:
    """Modal dialog for creating a new tab (blank or from template).

    Usage::

        result = NewTabDialog.show(parent_widget)
        if result:
            tab_name = result["tab_name"]
            template_path = result.get("template_path")  # None for blank
    """

    @staticmethod
    def show(parent=None):
        """Show the dialog and return the result dict, or None if cancelled."""
        dlg = NewTabDialog(parent)
        return dlg._result

    def __init__(self, parent=None):
        self._result = None
        self._selected_template = None
        self._cards = []
        self._run(parent)

    # ------------------------------------------------------------------ #

    def _run(self, parent):
        templates = _discover_templates()
        has_templates = bool(templates)

        width = _DLG_W
        height = _BLANK_H if has_templates else 160

        dlg = QtWidgets.QDialog(parent)
        dlg.setWindowTitle("New Tab")
        UT.apply_dark_window_flags(dlg)
        dlg.setFixedSize(width, height)
        self._dlg = dlg

        # -- Styled frame -----------------------------------------------------
        frame = QtWidgets.QFrame(dlg)
        frame.setFixedSize(width, height)
        frame.setStyleSheet(f"""
            QFrame {{
                background-color: {_BG};
                border-radius: 8px;
                border: 1px solid {_BORDER};
            }}
        """)

        # Opacity effect for fade-in
        self._opacity_fx = QtWidgets.QGraphicsOpacityEffect(frame)
        self._opacity_fx.setOpacity(0.0)
        frame.setGraphicsEffect(self._opacity_fx)
        self._frame = frame

        root = QtWidgets.QVBoxLayout(frame)
        root.setContentsMargins(14, 14, 14, 14)
        root.setSpacing(0)

        # -- Title -------------------------------------------------------------
        title = QtWidgets.QLabel("New Tab")
        title.setAlignment(QtCore.Qt.AlignCenter)
        title.setStyleSheet(
            f"color: {_TEXT_MAIN}; font-size: 14px; font-weight: 600; "
            "background: transparent; border: none;"
        )
        root.addWidget(title)
        root.addSpacing(3)

        # -- Subtitle ----------------------------------------------------------
        subtitle = QtWidgets.QLabel("Start blank or from a template")
        subtitle.setAlignment(QtCore.Qt.AlignCenter)
        subtitle.setStyleSheet(
            f"color: {_TEXT_SUB}; font-size: 10px; "
            "background: transparent; border: none;"
        )
        root.addWidget(subtitle)
        root.addSpacing(10)

        # -- Tab name input ----------------------------------------------------
        self._name_input = QtWidgets.QLineEdit()
        self._name_input.setPlaceholderText("Tab name")
        self._name_input.setFixedHeight(28)
        self._name_input.setStyleSheet(_input_ss())
        root.addWidget(self._name_input)
        root.addSpacing(10)

        # -- Mode toggle (only if templates exist) -----------------------------
        mode_segment_layout = QtWidgets.QHBoxLayout()
        mode_segment_layout.setContentsMargins(0, 0, 0, 0)
        mode_segment_layout.setSpacing(2)
        mode_segment_layout.setAlignment(QtCore.Qt.AlignCenter)

        if has_templates:
            self._mode_segment = TextSegmentControl(
                ["Blank", "Template"],
                height=28,
                font_size=12,
                radius=10,
                frame_radius=14,
                use_frame=True,
                frame_bg="rgba(255, 255, 255, 0.06)",
                selected_color="#1D65CA",
                expand=False,
            )
            self._mode_segment.segment_changed.connect(self._set_mode)
            mode_segment_layout.addWidget(self._mode_segment)
            #mode_segment_layout.addStretch()
            root.addLayout(mode_segment_layout)
            root.addSpacing(8)

            # -- Template grid inside a card -----------------------------------
            self._template_card = _card()
            tpl_card_layout = QtWidgets.QVBoxLayout(self._template_card)
            tpl_card_layout.setContentsMargins(8, 8, 8, 8)
            tpl_card_layout.setSpacing(0)

            scroll = QtWidgets.QScrollArea()
            scroll.setWidgetResizable(True)
            scroll.setFrameShape(QtWidgets.QFrame.NoFrame)
            scroll.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)
            scroll.setStyleSheet("""
                QScrollArea { background: transparent; border: none; }
                QScrollBar:vertical { border: none; background: transparent; width: 6px; }
                QScrollBar::handle:vertical { background: rgba(100,100,100,0.4); border-radius: 3px; min-height: 20px; }
                QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0px; }
                QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical { background: transparent; }
            """)

            grid_container = QtWidgets.QWidget()
            grid_container.setStyleSheet("background: transparent;")
            grid_layout = _FlowLayout(grid_container, spacing=8)

            self._grid_layout = grid_layout
            self._grid_container = grid_container
            for tpl in templates:
                card = _TemplateCard(tpl, grid_container)
                card.clicked.connect(self._on_template_selected)
                card.delete_requested.connect(self._on_delete_template)
                grid_layout.addWidget(card)
                self._cards.append(card)

            scroll.setWidget(grid_container)
            tpl_card_layout.addWidget(scroll)

            root.addWidget(self._template_card, 1)
            # Start hidden (Blank mode is default)
            self._template_card.setVisible(False)
            root.addSpacing(8)
        else:
            root.addStretch()

        # -- Action buttons ----------------------------------------------------
        btn_layout = QtWidgets.QHBoxLayout()
        btn_layout.setSpacing(8)

        create_btn = self._make_btn("Create", _ACCENT, _TEXT_MAIN)
        cancel_btn = self._make_btn("Cancel", _SURFACE, _TEXT_MAIN, border=True)

        create_btn.clicked.connect(lambda: self._on_accept(dlg))
        cancel_btn.clicked.connect(dlg.reject)

        btn_layout.addWidget(create_btn)
        btn_layout.addWidget(cancel_btn)
        root.addLayout(btn_layout)

        # -- Keyboard shortcuts ------------------------------------------------
        try:
            esc = QtWidgets.QShortcut(QtGui.QKeySequence(QtCore.Qt.Key_Escape), dlg)
        except Exception:
            esc = QtGui.QShortcut(QtGui.QKeySequence(QtCore.Qt.Key_Escape), dlg)
        esc.activated.connect(dlg.reject)

        try:
            enter = QtWidgets.QShortcut(QtGui.QKeySequence(QtCore.Qt.Key_Return), dlg)
        except Exception:
            enter = QtGui.QShortcut(QtGui.QKeySequence(QtCore.Qt.Key_Return), dlg)
        enter.activated.connect(lambda: self._on_accept(dlg))

        # -- Center on parent --------------------------------------------------
        if parent is not None:
            parent_geo = parent.geometry()
            cx = parent_geo.x() + (parent_geo.width() - width) // 2
            cy = parent_geo.y() + (parent_geo.height() - height) // 2
            dlg.move(cx, cy)

        # -- Entrance animation ------------------------------------------------
        # Fade in
        self._anim_fade = QPropertyAnimation(self._opacity_fx, b"opacity")
        self._anim_fade.setDuration(180)
        self._anim_fade.setStartValue(0.0)
        self._anim_fade.setEndValue(1.0)
        self._anim_fade.setEasingCurve(QEasingCurve.OutCubic)

        # Slide up (frame shifts from +8px below to 0)
        self._anim_slide = QPropertyAnimation(self._frame, b"pos")
        self._anim_slide.setDuration(200)
        self._anim_slide.setStartValue(QtCore.QPoint(0, 8))
        self._anim_slide.setEndValue(QtCore.QPoint(0, 0))
        self._anim_slide.setEasingCurve(QEasingCurve.OutCubic)

        self._anim_group = QParallelAnimationGroup()
        self._anim_group.addAnimation(self._anim_fade)
        self._anim_group.addAnimation(self._anim_slide)
        self._anim_group.start()

        # -- Show dialog -------------------------------------------------------
        self._name_input.setFocus()
        dlg.exec_()

    # ------------------------------------------------------------------ #
    # Helpers
    # ------------------------------------------------------------------ #

    @staticmethod
    def _make_btn(text, bg_tpl, text_color, *, border=False):
        btn = QtWidgets.QPushButton(text)
        btn.setFixedHeight(30)
        btn.setCursor(QtCore.Qt.PointingHandCursor)
        border_css = (
            f"border: 1px solid {_SURFACE.format(a='0.10')};"
            if border else "border: none;"
        )
        btn.setStyleSheet(f"""
            QPushButton {{
                background: {bg_tpl.format(a='0.55')};
                color: {text_color};
                {border_css}
                border-radius: 6px;
                font-size: 12px;
                font-weight: 500;
                padding: 0 14px;
            }}
            QPushButton:hover {{
                background: {bg_tpl.format(a='0.80')};
            }}
            QPushButton:pressed {{
                background: {bg_tpl.format(a='0.95')};
            }}
        """)
        return btn

    def _set_mode(self, index):
        """Switch between Blank (0) and Template (1) mode."""
        if hasattr(self, '_template_card'):
            self._template_card.setVisible(index == 1)
            target_h = _TPL_H if index == 1 else _BLANK_H
            self._animate_to_height(target_h)

        if index == 0:
            # Switched to Blank – clear template selection
            self._selected_template = None
            for card in self._cards:
                card.set_selected(False)

    def _animate_to_height(self, target_h):
        """Smoothly animate the dialog height and re-center on parent."""
        dlg = self._dlg
        frame = self._frame
        current_h = dlg.height()

        if current_h == target_h:
            return

        # Remove fixed constraints to allow animation
        dlg.setMinimumSize(_DLG_W, 0)
        dlg.setMaximumSize(_DLG_W, 16777215)
        frame.setMinimumSize(_DLG_W, 0)
        frame.setMaximumSize(_DLG_W, 16777215)

        # Compute centred target position
        parent = dlg.parent()
        if parent is not None:
            pg = parent.geometry()
            new_x = pg.x() + (pg.width() - _DLG_W) // 2
            new_y = pg.y() + (pg.height() - target_h) // 2
        else:
            geo = dlg.geometry()
            new_x = geo.x()
            new_y = geo.y() + (current_h - target_h) // 2

        anim_dlg = QPropertyAnimation(dlg, b"geometry")
        anim_dlg.setDuration(200)
        anim_dlg.setEndValue(QtCore.QRect(new_x, new_y, _DLG_W, target_h))
        anim_dlg.setEasingCurve(QEasingCurve.OutCubic)

        anim_frame = QPropertyAnimation(frame, b"geometry")
        anim_frame.setDuration(200)
        anim_frame.setEndValue(QtCore.QRect(0, 0, _DLG_W, target_h))
        anim_frame.setEasingCurve(QEasingCurve.OutCubic)

        group = QParallelAnimationGroup()
        group.addAnimation(anim_dlg)
        group.addAnimation(anim_frame)

        def _finalize():
            dlg.setFixedSize(_DLG_W, target_h)
            frame.setFixedSize(_DLG_W, target_h)

        group.finished.connect(_finalize)
        group.start()
        self._resize_anim = group  # prevent GC

    def _on_template_selected(self, template_path):
        self._selected_template = template_path
        for card in self._cards:
            card.set_selected(card._path == template_path)

        # Auto-fill name from template if input is empty
        if not self._name_input.text().strip():
            for card in self._cards:
                if card._path == template_path:
                    # Derive name from card text
                    name_lbl = card.findChild(QtWidgets.QLabel)
                    if name_lbl and name_lbl != card._thumb:
                        self._name_input.setText(name_lbl.text().rstrip("..."))
                    break

    def _on_delete_template(self, template_path):
        """Delete a template file after confirmation."""
        tpl_name = Path(template_path).stem
        # Confirmation dialog
        confirm = QtWidgets.QMessageBox(self._dlg)
        confirm.setWindowTitle("Delete Template")
        confirm.setText(f'Delete template "{tpl_name}"?')
        confirm.setInformativeText("This cannot be undone.")
        confirm.setStandardButtons(
            QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.Cancel
        )
        confirm.setDefaultButton(QtWidgets.QMessageBox.Cancel)
        confirm.setStyleSheet(f"""
            QMessageBox {{
                background: {_BG};
            }}
            QMessageBox QLabel {{
                color: {_TEXT_MAIN};
                font-size: 12px;
            }}
            QPushButton {{
                background: rgba(255,255,255,0.08);
                color: {_TEXT_MAIN};
                border: 1px solid rgba(255,255,255,0.1);
                border-radius: 5px;
                padding: 4px 14px;
                font-size: 11px;
            }}
            QPushButton:hover {{
                background: rgba(255,255,255,0.14);
            }}
        """)
        if confirm.exec_() != QtWidgets.QMessageBox.Yes:
            return

        # Delete the file
        try:
            Path(template_path).unlink()
        except Exception:
            return

        # Clear selection if this template was selected
        if self._selected_template == template_path:
            self._selected_template = None

        # Remove the card from the layout and list
        for card in self._cards:
            if card._path == template_path:
                self._grid_layout.removeWidget(card)
                card.setParent(None)
                card.deleteLater()
                self._cards.remove(card)
                break

        # If no templates left, switch to blank mode
        if not self._cards:
            self._set_mode(0)
            if hasattr(self, '_mode_segment'):
                self._mode_segment.set_selected_index(0)

    def _on_accept(self, dlg):
        tab_name = self._name_input.text().strip()
        if not tab_name:
            # Flash the input border red briefly
            self._name_input.setStyleSheet(
                self._name_input.styleSheet().replace(
                    _INPUT_BORDER, "rgba(255,80,80,0.6)"
                )
            )
            QtCore.QTimer.singleShot(600, lambda: self._name_input.setStyleSheet(
                _input_ss()
            ))
            return

        # Check if template mode is active
        use_template = (
            hasattr(self, '_mode_segment')
            and self._mode_segment.get_selected_index() == 1
            and self._selected_template is not None
        )

        self._result = {
            "tab_name": tab_name,
            "template_path": self._selected_template if use_template else None,
        }
        dlg.accept()
