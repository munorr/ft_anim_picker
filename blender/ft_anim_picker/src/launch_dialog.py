"""
Launch Dialog – Shown when the picker opens with no active session.

Offers: Create New Picker / Open From Library / Convert Legacy Data (if detected).
"""

from pathlib import Path
from PySide6 import QtWidgets, QtCore, QtGui

from . import utils as UT

_ICON_PATH = Path(__file__).parent / "bgen_picker_icons" / "bgen-picker-icon-02.png"

# -- Colour tokens --------------------------------------------------------
_BG         = "rgba(30, 30, 30, 0.97)"
_BORDER     = "rgba(255,255,255,0.06)"
_TEXT_MAIN  = "#e0e0e0"
_TEXT_SUB   = "#808080"
_ACCENT     = "rgba(29,101,202,{a})"
_SURFACE    = "rgba(255,255,255,0.1)"
_LEGACY     = "rgba(92,121,24,{a})"


class LaunchDialog:
    """Modal launch prompt returning the user's choice."""

    def __init__(self, parent=None, has_legacy_data=False):
        self._result = None
        self._has_legacy = has_legacy_data
        self._parent = parent
        self._run()

    def get_result(self):
        """Return one of: 'create_new', 'open_library', 'convert_legacy', or None."""
        return self._result

    # --------------------------------------------------------------------- #

    def _run(self):
        width = 280
        height = 290 if self._has_legacy else 260

        dlg = QtWidgets.QDialog(self._parent)
        dlg.setWindowTitle("BGEN Picker")
        UT.apply_dark_window_flags(dlg)
        dlg.setFixedSize(width, height)

        # -- Styled frame (the visible card) --------------------------------
        frame = QtWidgets.QFrame(dlg)
        frame.setFixedSize(width, height)
        frame.setStyleSheet(f"""
            QFrame {{
                background-color: {_BG};
                border-radius: 8px;
                border: 1px solid {_BORDER};
            }}
        """)

        root = QtWidgets.QVBoxLayout(frame)
        root.setContentsMargins(24, 20, 24, 20)
        root.setSpacing(0)

        # -- Close button (top-right) ---------------------------------------
        close_btn = QtWidgets.QPushButton("\u2715", frame)
        close_btn.setFixedSize(20, 20)
        close_btn.setCursor(QtCore.Qt.PointingHandCursor)
        close_btn.setStyleSheet(f"""
            QPushButton {{
                background: transparent;
                color: {_TEXT_SUB};
                border: none;
                border-radius: 10px;
                font-size: 12px;
                font-weight: 500;
            }}
            QPushButton:hover {{
                background: rgba(255,255,255,0.08);
                color: {_TEXT_MAIN};
            }}
            QPushButton:pressed {{
                background: rgba(200,60,60,0.35);
            }}
        """)
        close_btn.move(width - 28, 8)
        close_btn.clicked.connect(dlg.reject)
        close_btn.raise_()

        # -- Icon -----------------------------------------------------------
        if _ICON_PATH.exists():
            icon_label = QtWidgets.QLabel()
            icon_label.setAlignment(QtCore.Qt.AlignCenter)
            icon_label.setStyleSheet("background: transparent; border: none;")
            pixmap = QtGui.QPixmap(str(_ICON_PATH)).scaled(
                56, 56, QtCore.Qt.KeepAspectRatio, QtCore.Qt.SmoothTransformation
            )
            icon_label.setPixmap(pixmap)
            root.addWidget(icon_label)
            root.addSpacing(10)

        # -- Title ----------------------------------------------------------
        title = QtWidgets.QLabel("BGEN Picker")
        title.setAlignment(QtCore.Qt.AlignCenter)
        title.setStyleSheet(
            f"color: {_TEXT_MAIN}; font-size: 15px; font-weight: 600; "
            "background: transparent; border: none;"
        )
        root.addWidget(title)
        root.addSpacing(4)

        # -- Subtitle -------------------------------------------------------
        subtitle = QtWidgets.QLabel("How would you like to start?")
        subtitle.setAlignment(QtCore.Qt.AlignCenter)
        subtitle.setStyleSheet(
            f"color: {_TEXT_SUB}; font-size: 11px; "
            "background: transparent; border: none;"
        )
        root.addWidget(subtitle)
        root.addSpacing(16)

        # -- Action buttons -------------------------------------------------
        result = [None]

        def _make_btn(text, bg_tpl, text_color, *, border=False):
            btn = QtWidgets.QPushButton(text)
            btn.setFixedHeight(34)
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

        create_btn = _make_btn("Create New Picker", _ACCENT, _TEXT_MAIN)
        library_btn = _make_btn("Open From Library", _SURFACE, _TEXT_MAIN, border=True)

        create_btn.clicked.connect(
            lambda: (result.__setitem__(0, "create_new"), dlg.accept())
        )
        library_btn.clicked.connect(
            lambda: (result.__setitem__(0, "open_library"), dlg.accept())
        )

        root.addWidget(create_btn)
        root.addSpacing(6)
        root.addWidget(library_btn)

        if self._has_legacy:
            root.addSpacing(6)
            convert_btn = _make_btn(
                "Convert Legacy Data", _LEGACY, "#cccccc"
            )
            convert_btn.clicked.connect(
                lambda: (result.__setitem__(0, "convert_legacy"), dlg.accept())
            )
            root.addWidget(convert_btn)

        root.addStretch()

        # -- Center on parent -----------------------------------------------
        if self._parent is not None:
            parent_geo = self._parent.geometry()
            cx = parent_geo.x() + (parent_geo.width() - width) // 2
            cy = parent_geo.y() + (parent_geo.height() - height) // 2
            dlg.move(cx, cy)

        # -- Escape to close ------------------------------------------------
        try:
            esc = QtWidgets.QShortcut(QtGui.QKeySequence(QtCore.Qt.Key_Escape), dlg)
        except Exception:
            esc = QtGui.QShortcut(QtGui.QKeySequence(QtCore.Qt.Key_Escape), dlg)
        esc.activated.connect(dlg.reject)

        dlg.exec_()
        self._result = result[0]
