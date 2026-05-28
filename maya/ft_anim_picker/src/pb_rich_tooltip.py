"""Rich tooltip helper for Button Appearance card widgets.

Mirror of the Blender file — same behaviour, dual-PySide imports for Maya.
See ``pb_script_manager._show_delayed_tooltip`` for the original styling
this pattern copies.
"""

try:
    from PySide6 import QtWidgets, QtCore, QtGui
    from PySide6.QtCore import QPoint
except ImportError:
    from PySide2 import QtWidgets, QtCore, QtGui
    from PySide2.QtCore import QPoint

from . import custom_button as CB


_DEFAULT_ACCENT = "#91CB08"
_HOVER_DELAY_MS = 500
_AUTO_HIDE_MS = 10000


class _RichTooltipFilter(QtCore.QObject):
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
        self._last_global_pos = QtGui.QCursor.pos()

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
                try:
                    self._last_global_pos = event.globalPos()
                except AttributeError:
                    self._last_global_pos = QtGui.QCursor.pos()
                if self._tooltip is None and self._show_timer.isActive():
                    self._show_timer.start()
            elif et == QtCore.QEvent.KeyPress or et == QtCore.QEvent.FocusOut:
                self._hide_tooltip()
        return False

    def _show_tooltip(self):
        if self._tooltip is not None:
            return
        widget = self._widget
        try:
            if not widget.isVisible() or not widget.underMouse():
                return
        except RuntimeError:
            return

        tt = CB.CustomTooltipWidget(bg_color="#1f1f1f", border_color="#333333")

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

        pos = self._last_global_pos + QPoint(10, 16)
        screen = None
        try:
            screen = QtWidgets.QApplication.screenAt(pos)
        except AttributeError:
            # PySide2 older builds — fall back to primaryScreen
            screen = QtWidgets.QApplication.primaryScreen()
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
    return _RichTooltipFilter(widget, header, body, accent, category)
