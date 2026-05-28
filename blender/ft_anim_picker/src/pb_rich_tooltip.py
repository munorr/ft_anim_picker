"""Rich tooltip helper for Button Appearance card widgets.

Mirrors the styled floating tooltip the code editor uses for ``@ba``/``@tt``/``@pb``
tokens (see ``pb_script_manager._show_delayed_tooltip``). Exposes a single
``attach(widget, header, body)`` function that installs an event filter on the
target widget and shows a :class:`custom_button.CustomTooltipWidget` after a
hover delay. Shared visual grammar: bold accent header, muted category in
parentheses, white-on-dark body frame.
"""

from PySide6 import QtWidgets, QtCore, QtGui
from PySide6.QtCore import QPoint

from . import custom_button as CB


_DEFAULT_ACCENT = "#91CB08"
_HOVER_DELAY_MS = 500
_AUTO_HIDE_MS = 10000


class _RichTooltipFilter(QtCore.QObject):
    """Per-widget event filter that owns a delayed-show + auto-hide lifecycle."""

    def __init__(self, widget, header, body, accent, category):
        super().__init__(widget)
        self._widget = widget
        self._header = header
        self._body = body
        self._accent = accent
        self._category = category
        self._tooltip = None

        self._show_timer = QtCore.QTimer(self)
        self._show_timer.setSingleShot(True)
        self._show_timer.setInterval(_HOVER_DELAY_MS)
        self._show_timer.timeout.connect(self._show_tooltip)

        self._hide_timer = QtCore.QTimer(self)
        self._hide_timer.setSingleShot(True)
        self._hide_timer.setInterval(_AUTO_HIDE_MS)
        self._hide_timer.timeout.connect(self._hide_tooltip)

        widget.installEventFilter(self)
        # Track cursor position across move events so the tooltip lands near it
        self._last_global_pos = QtGui.QCursor.pos()

    # ── Event plumbing ─────────────────────────────────────────────────
    def eventFilter(self, obj, event):
        if obj is self._widget:
            et = event.type()
            if et == QtCore.QEvent.Enter:
                self._last_global_pos = QtGui.QCursor.pos()
                self._show_timer.start()
            elif et == QtCore.QEvent.Leave or et == QtCore.QEvent.Hide:
                self._show_timer.stop()
                self._hide_tooltip()
            elif et == QtCore.QEvent.MouseMove:
                # Update anchor position for the upcoming show, and
                # re-arm the delay so quick flicks don't pop a tooltip.
                self._last_global_pos = event.globalPos() if hasattr(event, 'globalPos') else QtGui.QCursor.pos()
                if self._tooltip is None and self._show_timer.isActive():
                    self._show_timer.start()  # restart delay
            elif et == QtCore.QEvent.KeyPress or et == QtCore.QEvent.FocusOut:
                self._hide_tooltip()
        return False

    # ── Show / hide ────────────────────────────────────────────────────
    def _show_tooltip(self):
        if self._tooltip is not None:
            return
        widget = self._widget
        # Guard against the owning widget being destroyed or hidden meanwhile.
        try:
            if not widget.isVisible() or not widget.underMouse():
                return
        except RuntimeError:
            return

        tt = CB.CustomTooltipWidget(bg_color="#1f1f1f", border_color="#333333")

        # Header row: accent-coloured bold label + category in muted text.
        header_layout = QtWidgets.QHBoxLayout()
        header_layout.setContentsMargins(0, 0, 0, 0)
        header_label = QtWidgets.QLabel(
            f"<b>{self._header}</b> <font color=\"#aaaaaa\">({self._category})</font>"
        )
        header_label.setTextFormat(QtCore.Qt.RichText)
        header_label.setStyleSheet(f"color: {self._accent}; font-size: 12px;")
        header_layout.addWidget(header_label)
        header_layout.addStretch()
        tt.add_layout(header_layout)

        # Body frame mirroring the @ba tooltip styling.
        body_frame = QtWidgets.QFrame()
        body_frame.setStyleSheet(
            "background-color: #1b1b1b; border: 1px solid #333333; "
            "border-radius: 3px; padding: 2px;"
        )
        body_layout = QtWidgets.QVBoxLayout(body_frame)
        body_layout.setContentsMargins(4, 4, 4, 4)
        body_layout.setSpacing(2)
        body_label = QtWidgets.QLabel(self._body)
        body_label.setTextFormat(QtCore.Qt.RichText)
        body_label.setWordWrap(True)
        body_label.setStyleSheet(
            "color: #ffffff; font-size: 12px; border: none; background-color: transparent;"
        )
        body_label.setMaximumWidth(320)
        body_layout.addWidget(body_label)
        tt.add_widget(body_frame)
        tt.finalize()

        # Clamp on-screen (same pattern as pb_script_manager.show_custom_tooltip).
        pos = self._last_global_pos + QPoint(10, 16)
        screen = QtWidgets.QApplication.screenAt(pos)
        if screen is not None:
            rect = screen.availableGeometry()
            if pos.x() + tt.width() > rect.right():
                pos.setX(self._last_global_pos.x() - tt.width() - 10)
            if pos.y() + tt.height() > rect.bottom():
                pos.setY(self._last_global_pos.y() - tt.height() - 10)
        tt.move(pos)
        tt.show()
        self._tooltip = tt
        self._hide_timer.start()

    def _hide_tooltip(self):
        self._hide_timer.stop()
        if self._tooltip is not None:
            try:
                self._tooltip.hide()
                self._tooltip.deleteLater()
            except RuntimeError:
                pass
            self._tooltip = None


def attach(widget, header, body, accent=_DEFAULT_ACCENT, category="Button Appearance"):
    """Install a rich-hover tooltip on ``widget``.

    The filter is parented to ``widget`` so it's garbage-collected with it.
    Safe to call multiple times — duplicate filters just no-op the second
    install (Qt ignores the redundant filter).
    """
    return _RichTooltipFilter(widget, header, body, accent, category)
