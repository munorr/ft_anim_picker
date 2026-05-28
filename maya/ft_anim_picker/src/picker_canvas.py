try:
    from PySide6 import QtWidgets, QtCore, QtGui
    from PySide6.QtGui import QColor, QShortcut, QPainter, QBrush
    from PySide6.QtCore import QTimer, QPropertyAnimation, QEasingCurve, Signal, Property
    from shiboken6 import wrapInstance
except ImportError:
    from PySide2 import QtWidgets, QtCore, QtGui
    from PySide2.QtWidgets import QShortcut
    from PySide2.QtGui import QColor, QPainter, QBrush
    from PySide2.QtCore import QTimer, QPropertyAnimation, QEasingCurve, Signal, Property
    from shiboken2 import wrapInstance
import os
import math
import maya.cmds as cmds
from . import ui as UI
from . import utils as UT
from . import picker_button as PB
from . import custom_button as CB
from . import tool_functions as TF
from . import data_management as DM
from . import custom_dialog as CD
from . import pb_transform_guides as TG
from .maya_curve_converter import create_buttons_from_maya_curves
from . import selection_sync_manager as SSM
from . import curve_editor as CE
from . import duplicate_mirror_tool as DMT


class ResizeHandle(QtWidgets.QWidget):
    """
    An elegant draggable resize handle for resizing the edit panel.
    Features smooth animations, visual feedback, and a modern design.
    """
    resizing = Signal(int)
    resize_started = Signal()
    resize_finished = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedWidth(8)
        self.setCursor(QtCore.Qt.SizeHorCursor)
        self.setMouseTracking(True)

        self._is_dragging = False
        self._is_hovered = False
        self._drag_start_x = 0

        self._highlight_opacity = 0.0
        self._handle_width = 2.0

        self._base_color = QColor(80, 80, 80)
        self._hover_color = QColor(29, 101, 202)
        self._drag_color = QColor(29, 101, 202)

        self._setup_animations()
        self.setToolTip("Drag to resize panel")

    def _setup_animations(self):
        self._opacity_animation = QPropertyAnimation(self, b"highlightOpacity")
        self._opacity_animation.setDuration(150)
        self._opacity_animation.setEasingCurve(QEasingCurve.OutCubic)

        self._width_animation = QPropertyAnimation(self, b"handleWidth")
        self._width_animation.setDuration(100)
        self._width_animation.setEasingCurve(QEasingCurve.OutCubic)

    def get_highlight_opacity(self):
        return self._highlight_opacity

    def set_highlight_opacity(self, value):
        self._highlight_opacity = value
        self.update()

    def get_handle_width(self):
        return self._handle_width

    def set_handle_width(self, value):
        self._handle_width = value
        self.update()

    highlightOpacity = Property(float, get_highlight_opacity, set_highlight_opacity)
    handleWidth = Property(float, get_handle_width, set_handle_width)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        handle_height = min(60, self.height() * 0.3)
        handle_x = (self.width() - self._handle_width) / 2
        handle_y = (self.height() - handle_height) / 2

        if self._is_dragging:
            color = self._drag_color
        elif self._is_hovered:
            color = QColor(
                int(self._base_color.red() + (self._hover_color.red() - self._base_color.red()) * self._highlight_opacity),
                int(self._base_color.green() + (self._hover_color.green() - self._base_color.green()) * self._highlight_opacity),
                int(self._base_color.blue() + (self._hover_color.blue() - self._base_color.blue()) * self._highlight_opacity)
            )
        else:
            color = self._base_color

        if self._highlight_opacity > 0 or self._is_dragging:
            bg_opacity = int(30 * (self._highlight_opacity if not self._is_dragging else 1.0))
            bg_color = QColor(self._hover_color)
            bg_color.setAlpha(bg_opacity)
            painter.fillRect(self.rect(), bg_color)

        painter.setPen(QtCore.Qt.NoPen)
        painter.setBrush(QBrush(color))
        handle_rect = QtCore.QRectF(handle_x, handle_y, self._handle_width, handle_height)
        painter.drawRoundedRect(handle_rect, self._handle_width / 2, self._handle_width / 2)

        if self._highlight_opacity > 0.5 or self._is_dragging:
            dot_color = QColor(color)
            dot_color.setAlpha(int(180 * (self._highlight_opacity if not self._is_dragging else 1.0)))
            painter.setBrush(QBrush(dot_color))
            dot_radius = 1.5
            dot_spacing = 8
            num_dots = 3
            start_y = handle_y + handle_height / 2 - (num_dots - 1) * dot_spacing / 2
            for i in range(num_dots):
                dot_y = start_y + i * dot_spacing
                painter.drawEllipse(QtCore.QPointF(self.width() / 2, dot_y), dot_radius, dot_radius)

        painter.end()

    def enterEvent(self, event):
        self._is_hovered = True
        self._animate_hover(True)
        super().enterEvent(event)

    def leaveEvent(self, event):
        if not self._is_dragging:
            self._is_hovered = False
            self._animate_hover(False)
        super().leaveEvent(event)

    def _animate_hover(self, entering):
        self._opacity_animation.stop()
        self._width_animation.stop()
        self._opacity_animation.setStartValue(self._highlight_opacity)
        self._opacity_animation.setEndValue(1.0 if entering else 0.0)
        self._width_animation.setStartValue(self._handle_width)
        self._width_animation.setEndValue(3.5 if entering else 2.0)
        self._opacity_animation.start()
        self._width_animation.start()

    def mousePressEvent(self, event):
        if event.button() == QtCore.Qt.LeftButton:
            self._is_dragging = True
            try:
                self._drag_start_x = event.globalPosition().x()
            except AttributeError:
                self._drag_start_x = event.globalPos().x()
            self.resize_started.emit()
            self._width_animation.stop()
            self._width_animation.setStartValue(self._handle_width)
            self._width_animation.setEndValue(4.5)
            self._width_animation.start()
            self.update()
            event.accept()
        else:
            event.ignore()

    def mouseMoveEvent(self, event):
        if self._is_dragging:
            try:
                current_x = event.globalPosition().x()
            except AttributeError:
                current_x = event.globalPos().x()
            delta = int(self._drag_start_x - current_x)
            self._drag_start_x = current_x
            self.resizing.emit(delta)
            event.accept()
        else:
            event.ignore()

    def mouseReleaseEvent(self, event):
        if event.button() == QtCore.Qt.LeftButton and self._is_dragging:
            self._is_dragging = False
            self.resize_finished.emit()
            if self._is_hovered:
                self._width_animation.stop()
                self._width_animation.setStartValue(self._handle_width)
                self._width_animation.setEndValue(3.5)
                self._width_animation.start()
            else:
                self._animate_hover(False)
            self.update()
            event.accept()
        else:
            event.ignore()


class _PaintedContainer(QtWidgets.QWidget):
    """QWidget with anti-aliased rounded background and border."""

    def __init__(self, parent=None, bg_color=None, border_color=None, border_width=1, radius=8):
        super().__init__(parent)
        self._bg_color = bg_color or QtGui.QColor(29, 29, 29)
        self._border_color = border_color or QtGui.QColor(255, 255, 255, 25)
        self._border_width = border_width
        self._radius = radius

    def paintEvent(self, event):
        painter = QtGui.QPainter(self)
        painter.setRenderHint(QtGui.QPainter.Antialiasing)
        half = self._border_width / 2.0
        rect = QtCore.QRectF(self.rect()).adjusted(half, half, -half, -half)
        painter.setBrush(self._bg_color)
        pen = QtGui.QPen(self._border_color, self._border_width)
        painter.setPen(pen)
        painter.drawRoundedRect(rect, self._radius, self._radius)
        painter.end()


class CanvasEditPanel(QtWidgets.QWidget):
    """
    An overlay edit panel embedded inside canvas_frame.
    Positioned at the right edge of its parent, overlaying the canvas content.
    """
    width_changed = Signal(int)

    def __init__(self, parent=None):
        super().__init__(parent)

        self._min_width = 200
        self._max_width = 450
        self._default_width = 200
        self._current_width = self._default_width
        # Margins are measured against `_anchor_widget` (the canvas area) when set,
        # so they stay correct regardless of which frame the panel is reparented to.
        self._top_margin = 4
        self._right_margin = 4
        self._bottom_margin = 10
        self._anchor_widget = None

        self._slide_offset = 0.0
        self._opacity_effect = QtWidgets.QGraphicsOpacityEffect(self)
        self._opacity_effect.setOpacity(1.0)
        self.setGraphicsEffect(self._opacity_effect)
        self._show_anim_group = None
        self._hide_anim_group = None

        self._layout = QtWidgets.QHBoxLayout(self)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._layout.setSpacing(0)

        self._resize_handle = ResizeHandle(self)
        self._resize_handle.resizing.connect(self._on_resize)

        self._content_container = _PaintedContainer(
            bg_color=QtGui.QColor(29, 29, 29),
            border_color=QtGui.QColor(255, 255, 255, 25),
            border_width=2,
            radius=8,
        )
        self._content_layout = QtWidgets.QVBoxLayout(self._content_container)
        self._content_layout.setContentsMargins(0, 0, 0, 0)
        self._content_layout.setSpacing(4)

        self._layout.addWidget(self._resize_handle)
        self._layout.addWidget(self._content_container)

        self._apply_width()

    def get_panel_width(self):
        return self._current_width

    def set_panel_width(self, value):
        self._current_width = value
        self._apply_width()

    panelWidth = Property(int, get_panel_width, set_panel_width)

    def _get_slide_offset(self):
        return self._slide_offset

    def _set_slide_offset(self, value):
        self._slide_offset = value
        self._update_position()

    slideOffset = Property(float, _get_slide_offset, _set_slide_offset)

    def _apply_width(self):
        total_width = self._current_width + self._resize_handle.width()
        self.setFixedWidth(total_width)
        self.width_changed.emit(self._current_width)
        self._update_position()

    def set_anchor_widget(self, widget):
        """Set the widget the panel should align to (typically the canvas stack)."""
        self._anchor_widget = widget
        self._update_position()

    def _update_position(self):
        parent = self.parentWidget()
        if not parent:
            return
        panel_width = self.width()

        anchor = self._anchor_widget
        if anchor is not None and anchor.isVisible() and anchor.window() is parent.window():
            top_left = anchor.mapTo(parent, QtCore.QPoint(0, 0))
            anchor_w = anchor.width()
            anchor_h = anchor.height()
            x = int(top_left.x() + anchor_w - panel_width - self._right_margin + self._slide_offset)
            y = top_left.y() + self._top_margin
            panel_height = anchor_h - self._top_margin - self._bottom_margin
        else:
            parent_rect = parent.rect()
            panel_height = parent_rect.height() - self._top_margin - self._bottom_margin
            x = int(parent_rect.width() - panel_width - self._right_margin + self._slide_offset)
            y = self._top_margin
        self.setGeometry(x, y, panel_width, max(panel_height, 100))

    def showEvent(self, event):
        super().showEvent(event)
        self.raise_()
        self._update_position()

    def animate_show(self, delay_ms=0):
        self._stop_animations()
        self._slide_offset = 30.0
        self._opacity_effect.setOpacity(0.0)
        self._update_position()

        slide_anim = QPropertyAnimation(self, b"slideOffset")
        slide_anim.setStartValue(30.0)
        slide_anim.setEndValue(0.0)
        slide_anim.setDuration(300)
        slide_anim.setEasingCurve(QEasingCurve.OutCubic)

        opacity_anim = QPropertyAnimation(self._opacity_effect, b"opacity")
        opacity_anim.setStartValue(0.0)
        opacity_anim.setEndValue(1.0)
        opacity_anim.setDuration(300)
        opacity_anim.setEasingCurve(QEasingCurve.OutCubic)

        group = QtCore.QParallelAnimationGroup(self)
        group.addAnimation(slide_anim)
        group.addAnimation(opacity_anim)
        self._show_anim_group = group

        if delay_ms > 0:
            QTimer.singleShot(delay_ms, group.start)
        else:
            group.start()

    def animate_hide(self):
        self._stop_animations()

        slide_anim = QPropertyAnimation(self, b"slideOffset")
        slide_anim.setStartValue(self._slide_offset)
        slide_anim.setEndValue(30.0)
        slide_anim.setDuration(220)
        slide_anim.setEasingCurve(QEasingCurve.InCubic)

        opacity_anim = QPropertyAnimation(self._opacity_effect, b"opacity")
        opacity_anim.setStartValue(self._opacity_effect.opacity())
        opacity_anim.setEndValue(0.0)
        opacity_anim.setDuration(220)
        opacity_anim.setEasingCurve(QEasingCurve.InCubic)

        group = QtCore.QParallelAnimationGroup(self)
        group.addAnimation(slide_anim)
        group.addAnimation(opacity_anim)

        def _on_finished():
            self.setVisible(False)
            self._slide_offset = 0.0
            self._opacity_effect.setOpacity(1.0)

        group.finished.connect(_on_finished)
        self._hide_anim_group = group
        group.start()

    def _stop_animations(self):
        for grp in (self._show_anim_group, self._hide_anim_group):
            if grp is not None and grp.state() == QtCore.QAbstractAnimation.Running:
                grp.stop()
        self._show_anim_group = None
        self._hide_anim_group = None

    def add_widget(self, widget):
        self._content_layout.addWidget(widget)

    def add_layout(self, layout):
        self._content_layout.addLayout(layout)

    def get_content_width(self):
        return self._current_width

    def set_content_width(self, width, animated=False):
        width = max(self._min_width, min(self._max_width, width))
        self._current_width = width
        self._apply_width()

    def reset_to_default(self):
        self.set_content_width(self._default_width)

    def _on_resize(self, delta):
        new_width = self._current_width + delta
        new_width = max(self._min_width, min(self._max_width, new_width))
        if new_width != self._current_width:
            self._current_width = new_width
            self._apply_width()


class CanvasLoadingOverlay(QtWidgets.QWidget):
    """Semi-transparent overlay with a pulsating icon shown while buttons load."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(QtCore.Qt.WA_TransparentForMouseEvents, False)

        from pathlib import Path
        icon_path = Path(__file__).parent / 'bgen_picker_icons' / 'bgen-picker-icon-01.png'
        self._icon_pixmap = QtGui.QPixmap(str(icon_path)).scaled(
            48, 48, QtCore.Qt.KeepAspectRatio, QtCore.Qt.SmoothTransformation)

        self._opacity_effect = QtWidgets.QGraphicsOpacityEffect(self)
        self._opacity_effect.setOpacity(1.0)
        self.setGraphicsEffect(self._opacity_effect)

        self._icon_opacity = 1.0

        self._pulse_anim = QPropertyAnimation(self, b"iconOpacity")
        self._pulse_anim.setDuration(800)
        self._pulse_anim.setKeyValueAt(0, 0.3)
        self._pulse_anim.setKeyValueAt(0.5, 1.0)
        self._pulse_anim.setKeyValueAt(1.0, 0.3)
        self._pulse_anim.setEasingCurve(QEasingCurve.InOutSine)
        self._pulse_anim.setLoopCount(-1)

        self._fade_out = QPropertyAnimation(self._opacity_effect, b"opacity")
        self._fade_out.setDuration(200)
        self._fade_out.setStartValue(1.0)
        self._fade_out.setEndValue(0.0)
        self._fade_out.setEasingCurve(QEasingCurve.InCubic)
        self._fade_out.finished.connect(self._on_fade_out_done)

        self._min_timer = QTimer(self)
        self._min_timer.setSingleShot(True)
        self._hide_requested = False

        self.setVisible(True)
        self._pulse_anim.start()

    def _get_icon_opacity(self):
        return self._icon_opacity

    def _set_icon_opacity(self, val):
        self._icon_opacity = val
        self.update()

    iconOpacity = Property(float, _get_icon_opacity, _set_icon_opacity)

    def show_overlay(self):
        self._hide_requested = False
        self._reposition()
        self._fade_out.stop()
        self._opacity_effect.setOpacity(1.0)
        self.setVisible(True)
        self.raise_()
        if self._pulse_anim.state() != QPropertyAnimation.Running:
            self._pulse_anim.start()
        self._min_timer.start(200)

    def hide_overlay(self):
        self._hide_requested = True
        if not self._min_timer.isActive():
            self._do_hide()
        else:
            try:
                self._min_timer.timeout.disconnect(self._do_hide)
            except (RuntimeError, TypeError):
                pass
            self._min_timer.timeout.connect(self._do_hide)

    def _do_hide(self):
        try:
            self._min_timer.timeout.disconnect(self._do_hide)
        except (RuntimeError, TypeError):
            pass
        self._fade_out.start()

    def _on_fade_out_done(self):
        self._pulse_anim.stop()
        self.setVisible(False)

    def _reposition(self):
        p = self.parentWidget()
        if p:
            self.setGeometry(p.rect())

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.fillRect(self.rect(), QtGui.QColor(29, 29, 29, 180))
        if not self._icon_pixmap.isNull():
            painter.setOpacity(self._icon_opacity)
            x = (self.width() - self._icon_pixmap.width()) // 2
            y = (self.height() - self._icon_pixmap.height()) // 2
            painter.drawPixmap(x, y, self._icon_pixmap)
        painter.end()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._reposition()


class SaveIndicatorOverlay(QtWidgets.QWidget):
    """Small pill badge that appears at top-right of canvas after a save."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(QtCore.Qt.WA_TransparentForMouseEvents, True)
        self.setFixedSize(90, 24)
        self.setVisible(False)

        self._label = "Saved \u2713"

        # Opacity effect + animations
        self._opacity_effect = QtWidgets.QGraphicsOpacityEffect(self)
        self._opacity_effect.setOpacity(0.0)
        self.setGraphicsEffect(self._opacity_effect)

        self._fade_in = QPropertyAnimation(self._opacity_effect, b"opacity")
        self._fade_in.setDuration(150)
        self._fade_in.setStartValue(0.0)
        self._fade_in.setEndValue(1.0)
        self._fade_in.setEasingCurve(QEasingCurve.OutCubic)

        self._fade_out = QPropertyAnimation(self._opacity_effect, b"opacity")
        self._fade_out.setDuration(500)
        self._fade_out.setStartValue(1.0)
        self._fade_out.setEndValue(0.0)
        self._fade_out.setEasingCurve(QEasingCurve.InCubic)
        self._fade_out.finished.connect(lambda: self.setVisible(False))

        self._hold_timer = QTimer(self)
        self._hold_timer.setSingleShot(True)
        self._hold_timer.timeout.connect(self._fade_out.start)

    def show_indicator(self, label="Saved \u2713"):
        self._label = label
        self._fade_out.stop()
        self._hold_timer.stop()
        self._opacity_effect.setOpacity(0.0)
        self._reposition()
        self.setVisible(True)
        self.raise_()
        self.update()
        self._fade_in.start()
        self._hold_timer.start(2000)

    def _reposition(self):
        p = self.parentWidget()
        if p:
            margin = 10
            x = p.width() - self.width() - margin
            self.move(x, margin)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        rect = self.rect()
        painter.setBrush(QtGui.QColor(29, 101, 202, 210))
        painter.setPen(QtCore.Qt.NoPen)
        painter.drawRoundedRect(rect, rect.height() / 2, rect.height() / 2)
        painter.setPen(QtGui.QColor(210, 210, 210))
        font = painter.font()
        font.setPixelSize(11)
        painter.setFont(font)
        painter.drawText(rect, QtCore.Qt.AlignCenter, self._label)
        painter.end()


class HUDWidget(QtWidgets.QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(QtCore.Qt.WA_TransparentForMouseEvents)  # Make the whole widget transparent to mouse events
        self.setStyleSheet("background-color: transparent;")
        
        # Main layout for HUD elements
        self.layout = QtWidgets.QGridLayout(self)
        self.layout.setContentsMargins(5, 5, 5, 5)
        
        # Create the toggle button container that will catch mouse events
        self.button_container = QtWidgets.QWidget(self)
        self.button_container.setAttribute(QtCore.Qt.WA_TransparentForMouseEvents, False)  # This widget will catch mouse events
        self.button_container.setFixedSize(24, 24)
        
        # Create the toggle button
        self.toggle_button = QtWidgets.QPushButton("≡", self.button_container)
        self.toggle_button.setFixedSize(24, 24)
        self.toggle_button.setStyleSheet("""
            QPushButton {
                background-color: rgba(50, 50, 50, 0.7);
                color: #dddddd;
                border: 1px solid rgba(80, 80, 80, 0.7);
                border-radius: 3px;
                padding: 0px 0px 2px 0px;
            }
            QPushButton:hover {
                background-color: rgba(60, 60, 60, 0.8);
            }""")
        
        self.toggle_button.clicked.connect(self.toggle_hud)
        self.layout.addWidget(self.button_container, 0, 0, QtCore.Qt.AlignTop | QtCore.Qt.AlignLeft)
        
        # Stats container
        self.stats_container = QtWidgets.QWidget(self)
        self.stats_layout = QtWidgets.QHBoxLayout(self.stats_container)
        self.stats_layout.setContentsMargins(0, 0, 0, 0)
        self.stats_layout.setSpacing(10)  # Space between labels
        
        # Button count label
        self.button_count_label = QtWidgets.QLabel("Buttons: 0 / 0")
        self.button_count_label.setStyleSheet("color: rgba(255, 255, 255, 0.2);")
        #self.stats_layout.addWidget(self.button_count_label)
        self.layout.addWidget(self.button_count_label, 0, 0, QtCore.Qt.AlignBottom | QtCore.Qt.AlignLeft)
        

        # Selection count label
        self.selection_count_label = QtWidgets.QLabel("Selected: 0")
        self.selection_count_label.setStyleSheet("color: rgba(255, 255, 255, 0.2);")
        #self.stats_layout.addWidget(self.selection_count_label)
        self.layout.addWidget(self.selection_count_label, 0, 1, QtCore.Qt.AlignBottom | QtCore.Qt.AlignRight)

        self.reset_buttons()
        
        # Store all HUD elements (except toggle button)
        self.hud_elements = [
            self.stats_container,
            self.button_count_label,
            self.selection_count_label,
            self.reset_button_frame
        ]

        # Initialize visibility
        self.hud_visible = True
        
        # Start timer for updating Maya selection count
        self.update_timer = QtCore.QTimer(self)
        self.update_timer.timeout.connect(self.update_selection_count)
        self.update_timer.start(100)  # Update every 100ms

    def reset_buttons(self):
        button_size = 14
        br = 3
        los = 5
        fbc = 35
        
        # Create a container widget for the reset buttons that will catch mouse events
        self.reset_container = QtWidgets.QWidget(self)
        self.reset_container.setAttribute(QtCore.Qt.WA_TransparentForMouseEvents, False)  # This widget will catch mouse events
        
        # Create the frame inside the container
        self.reset_button_frame = QtWidgets.QFrame(self.reset_container)
        self.reset_button_frame.setStyleSheet(f"background-color: rgba({fbc},{fbc},{fbc},.7); border-radius: {br}px;")
        self.reset_button_frame.setFixedHeight(24)
        
        self.reset_button_layout = QtWidgets.QHBoxLayout(self.reset_button_frame)
        self.reset_button_layout.setContentsMargins(los, los, los, los)
        self.reset_button_layout.setSpacing(los)

        self.reset_move_button = CB.CustomButton(text="Move",tooltip="Reset Position",height=button_size,radius=br)
        self.reset_rotate_button = CB.CustomButton(text="Rotate",tooltip="Reset Rotation",height=button_size,radius=br)
        self.reset_scale_button = CB.CustomButton(text="Scale",tooltip="Reset Scale",height=button_size,radius=br)
        self.reset_all_button = CB.CustomButton(text="All",tooltip="Reset All",height=button_size,radius=br, color='#ff0000')

        self.reset_move_button.clicked.connect(TF.reset_move)
        self.reset_rotate_button.clicked.connect(TF.reset_rotate)
        self.reset_scale_button.clicked.connect(TF.reset_scale)
        self.reset_all_button.clicked.connect(TF.reset_all)

        self.reset_button_layout.addWidget(self.reset_move_button)
        self.reset_button_layout.addWidget(self.reset_rotate_button)
        self.reset_button_layout.addWidget(self.reset_scale_button)
        self.reset_button_layout.addWidget(self.reset_all_button)

        # Add the container to the main layout
        self.layout.addWidget(self.reset_container, 0, 1, QtCore.Qt.AlignTop | QtCore.Qt.AlignRight)
        
        # Ensure the frame fills the container
        container_layout = QtWidgets.QHBoxLayout(self.reset_container)
        container_layout.setContentsMargins(0, 0, 0, 0)
        #container_layout.addWidget(self.reset_button_frame)
        
    def toggle_hud(self):
        self.hud_visible = not self.hud_visible
        for element in self.hud_elements:
            element.setVisible(self.hud_visible)

    def update_button_count(self, total_count, selected_count=0):
        """Update the button count display with both total and selected counts"""
        self.button_count_label.setText(f"Buttons: {selected_count} / {total_count}")
        
    def update_selection_count(self):
        """Update the Maya selection count"""
        try:
            sel_count = len(cmds.ls(selection=True)) or 0
            self.selection_count_label.setText(f"Selected: {sel_count}")
        except:
            # Handle case where Maya command fails
            self.selection_count_label.setText("Selected: --")

class PickerCanvas(QtWidgets.QWidget):
    clicked = Signal()
    button_selection_changed = Signal()
    view_changed = Signal()  # Emitted when pan/zoom settles (debounced)
    selection_count_changed = Signal(int)
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFocusPolicy(QtCore.Qt.StrongFocus)
        self.setAutoFillBackground(True)

        # Enable drag and drop for the canvas
        self.setAcceptDrops(True)

        self.show_axes = True
        self.show_dots = True 
        self.show_grid = False  
        self.grid_size = 50  

        # Background properties
        self.background_color = QtGui.QColor(50, 50, 50, 255)
        self.dot_color = QtGui.QColor(40, 40, 40, 255)
        self.grid_color = QtGui.QColor(10, 10, 10, 255)
        self.dot_size = 3
        self.dot_spacing = 12

        # Border properties
        self.default_border_color = QtGui.QColor(82, 133, 166, 0)
        self.edit_mode_border_color = QtGui.QColor(29, 101, 202, 255)
        self.border_color = self.default_border_color
        self.border_width = 1
        self.border_radius = 10

        # Image properties
        self.background_image = None
        self.image_opacity = 1.0

        # Canvas transform properties
        self.zoom_factor = 1.0
        self.pan_offset = QtCore.QPointF(0, 0)
        self.last_pan_pos = None

        self.last_zoom_pos = None
        self.was_zoom_dragging = False

        # Trackpad vs mouse detection state
        self._scroll_gesture_is_trackpad = False

        # Set when a non-edit-mode button click wants Maya to become the
        # active window — but deferred until the cursor actually leaves
        # the picker so the picker remains the macOS key window while
        # hovered (required for trackpad pinch-zoom NSEvent gestures).
        self._pending_maya_activation = False

        self.buttons = []
        self.setup_dot_texture()
        
        # Set size policy to allow expanding
        self.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Expanding)

        # Use PreventContextMenu so right-click goes through mousePressEvent first,
        # allowing Alt+RMB zoom to take priority over the context menu.
        self.setContextMenuPolicy(QtCore.Qt.PreventContextMenu)

        self.setMouseTracking(True)
        self.rubberband = QtWidgets.QRubberBand(QtWidgets.QRubberBand.Rectangle, self)
        self.rubberband_origin = QtCore.QPoint()
        self.is_selecting = False
        self.buttons_in_current_drag = set()  # Track buttons in current drag operation
        self.initial_selection_state = {}  # Store initial selection state when drag starts

        self.edit_mode = False
        self.image_scale = 1.0

        # Multi-button placement state (drag-to-place after "Create Buttons from Selection")
        self.is_placing_multi = False
        self.placement_origin_scene = None
        self.placement_cursor_scene = None
        self.pending_placement_data = None  # {'selection': [...], 'default_w', 'default_h', 'gap'}

        self.hud = HUDWidget(self)
        self.hud.raise_()

        self.loading_overlay = CanvasLoadingOverlay(self)

        # Save indicator overlay (top-right badge)
        self.save_indicator = SaveIndicatorOverlay(self)

        # Curve editor overlay for shape editing (in edit mode)
        self.curve_editor = CE.CurveEditorOverlay(self, self)
        self.curve_editor.editingFinished.connect(self._on_curve_editing_finished)
        self.curve_editor.editingCancelled.connect(self._on_curve_editing_cancelled)

        # Debounce timer for view_changed signal
        self._view_change_timer = QTimer(self)
        self._view_change_timer.setSingleShot(True)
        self._view_change_timer.setInterval(500)
        self._view_change_timer.timeout.connect(self.view_changed.emit)

        # Deferred widget geometry: during pan/zoom, canvas painting doesn't need
        # widget geometry, so we skip update_button_positions() and just repaint.
        self._geometry_dirty = False

        # Persistent timer for deferred geometry flush
        self._geometry_flush_timer = QTimer(self)
        self._geometry_flush_timer.setSingleShot(True)
        self._geometry_flush_timer.setInterval(100)
        self._geometry_flush_timer.timeout.connect(self._flush_deferred_geometry)

        # Persistent throttled timer for transform guides updates during drag
        self._guides_update_timer = QTimer(self)
        self._guides_update_timer.setSingleShot(True)
        self._guides_update_timer.setInterval(30)  # ~33 FPS cap for guides
        self._guides_update_timer.timeout.connect(self._on_guides_timer)

        self.minimal_mode = False
        self.last_selected_button = None

        # Custom tooltip management
        self._tooltip_widget = None
        self._tooltip_timer = QtCore.QTimer(self)
        self._tooltip_timer.setSingleShot(True)
        self._tooltip_timer.timeout.connect(self._show_button_tooltip)
        self._current_hover_button = None
        self._pressed_button = None
        self._tooltip_position = QtCore.QPoint()

        # Transform guides for edit mode (add after HUD initialization)
        self.transform_guides = TG.TransformGuides(self, self)
        self.transform_guides.transform_finished.connect(self.on_transform_finished)

        # Interactive duplicate-mirror tool (right-click → Duplicate Mirror in edit mode)
        self.duplicate_mirror_tool = DMT.DuplicateMirrorTool(self)

        self.canvas_shortcuts()
        
        # Initialize curve import settings
        self._separate_curves_mode = True  # Default to separate curves
        
        # Initialize 2-way selection synchronization
        self._init_selection_sync()
    
    #------------------------------------------------------------------------------
    # Curve import settings methods
    #------------------------------------------------------------------------------
    def get_separate_curves_mode(self):
        """Get the current curve separation mode"""
        return getattr(self, '_separate_curves_mode', True)
    
    def set_separate_curves_mode(self, separate_curves):
        """Set the curve separation mode"""
        self._separate_curves_mode = separate_curves
        # Show brief feedback
        mode_text = "Separate" if separate_curves else "Combine"
        print(f"Curve import mode set to: {mode_text} curves")
    
    def get_current_coordinate_plane(self):
        """Get the current coordinate plane name"""
        from . import maya_curve_converter as MCC
        return MCC.CoordinatePlaneConfig.get_current_plane()['name']
    
    def set_coordinate_plane(self, plane_name):
        """Set the coordinate plane and provide feedback"""
        from . import maya_curve_converter as MCC
        MCC.CoordinatePlaneConfig.set_plane(plane_name)
        plane_info = MCC.CoordinatePlaneConfig.get_current_plane()
        print(f"Coordinate plane set to: {plane_info['name']} ({plane_info['description']})")
    
    def get_auto_detect_plane_mode(self):
        """Get the current auto-detection mode"""
        return getattr(self, '_auto_detect_plane_mode', True)
    
    def set_auto_detect_plane_mode(self, enabled):
        """Set the auto-detection mode"""
        self._auto_detect_plane_mode = enabled
        # Show brief feedback
        status = "enabled" if enabled else "disabled"
        print(f"Auto-detection mode {status}")
    
    def get_curve_import_settings_summary(self):
        """Get a summary of current curve import settings"""
        plane_name = self.get_current_coordinate_plane()
        mode_text = "Separate" if self.get_separate_curves_mode() else "Combine"
        auto_detect_text = "Auto" if self.get_auto_detect_plane_mode() else "Manual"
        return f"Plane: {plane_name} | Mode: {mode_text} | Detection: {auto_detect_text}"
    
    def reset_curve_import_settings(self):
        """Reset curve import settings to defaults"""
        from . import maya_curve_converter as MCC
        MCC.CoordinatePlaneConfig.set_plane('XZ')  # Default plane for Maya
        self.set_separate_curves_mode(True)  # Default to separate curves
        self.set_auto_detect_plane_mode(True)  # Default to auto-detection
        print("Curve import settings reset to defaults")
    
    #------------------------------------------------------------------------------
    def set_edit_mode(self, enabled):
        # If the user is leaving edit mode while the duplicate-mirror tool is up,
        # tear it down — its UI is meaningless outside edit mode.
        if not enabled and hasattr(self, 'duplicate_mirror_tool') and self.duplicate_mirror_tool.active:
            self.duplicate_mirror_tool.cancel()

        self.edit_mode = enabled
        self.border_color = self.edit_mode_border_color if enabled else self.default_border_color
        self.border_width = 1 if enabled else 1
        for button in self.buttons:
            button.edit_mode = enabled
            button.update_cursor()

        # Update transform guides
        if hasattr(self, 'transform_guides'):
            if enabled:
                self.transform_guides.update_selection()
            else:
                self.transform_guides.setVisible(False)
                self.transform_guides.visual_layer.setVisible(False)
                if hasattr(self.transform_guides, 'control_widget'):
                    self.transform_guides.control_widget.setVisible(False)

        self.update()
    
    def set_minimal_mode(self, enabled):
        """Set minimal mode state"""
        self.minimal_mode = enabled
        # Hide/show the HUD based on minimal mode
        self.hud.setVisible(not enabled)
        self.update()  # Trigger repaint
    #---------------------------------------------------------------------------------------
    def canvas_shortcuts(self):
        """Handle canvas shortcuts"""
        self.add_button_shortcut = QShortcut(QtGui.QKeySequence("Shift+A"), self)
        self.add_button_shortcut.activated.connect(lambda: self.add_button_at_position(self.canvas_cursor_position()))
        
        self.add_curve_button_shortcut = QShortcut(QtGui.QKeySequence("Shift+C"), self)
        self.add_curve_button_shortcut.activated.connect(lambda: self.add_curve_button_at_position())

        self.delete_button_shortcut = QShortcut(QtGui.QKeySequence("Delete"), self)
        self.delete_button_shortcut.activated.connect(lambda: self.delete_selected_buttons())
        
        self.copy_button_shortcut = QShortcut(QtGui.QKeySequence("Ctrl+C"), self)
        self.copy_button_shortcut.activated.connect(lambda: self.copy_selected_buttons())

        self.paste_button_shortcut = QShortcut(QtGui.QKeySequence("Ctrl+V"), self)
        self.paste_button_shortcut.activated.connect(lambda: self.paste_buttons_at_position(self.canvas_cursor_position()))

        self.paste_button_shortcut = QShortcut(QtGui.QKeySequence("Ctrl+Shift+V"), self)
        self.paste_button_shortcut.activated.connect(lambda: self.paste_buttons_at_position(self.canvas_cursor_position(), mirror=True))

        self.align_button_shortcut = QShortcut(QtGui.QKeySequence("Ctrl+Right"), self)
        self.align_button_shortcut.activated.connect(lambda: self.align_button_right())

        self.align_button_shortcut = QShortcut(QtGui.QKeySequence("Ctrl+Left"), self)
        self.align_button_shortcut.activated.connect(lambda: self.align_button_left())

        self.align_button_shortcut = QShortcut(QtGui.QKeySequence("Ctrl+Up"), self)
        self.align_button_shortcut.activated.connect(lambda: self.align_button_top())

        self.align_button_shortcut = QShortcut(QtGui.QKeySequence("Ctrl+Down"), self)
        self.align_button_shortcut.activated.connect(lambda: self.align_button_bottom())

        # Center buttons shortcuts
        self.align_button_shortcut = QShortcut(QtGui.QKeySequence("Shift+Right"), self)
        self.align_button_shortcut.activated.connect(lambda: self.align_button_center())

        self.align_button_shortcut = QShortcut(QtGui.QKeySequence("Shift+Left"), self)
        self.align_button_shortcut.activated.connect(lambda: self.align_button_center())
        
        
        self.align_button_shortcut = QShortcut(QtGui.QKeySequence("Shift+Up"), self)
        self.align_button_shortcut.activated.connect(lambda: self.align_button_middle())

        self.align_button_shortcut = QShortcut(QtGui.QKeySequence("Shift+Down"), self)
        self.align_button_shortcut.activated.connect(lambda: self.align_button_middle())

        # Evenly space buttons shortcuts
        self.align_button_shortcut = QShortcut(QtGui.QKeySequence("Ctrl+Shift+Right"), self)
        self.align_button_shortcut.activated.connect(lambda: self.evenly_space_horizontal())

        self.align_button_shortcut = QShortcut(QtGui.QKeySequence("Ctrl+Shift+Left"), self)
        self.align_button_shortcut.activated.connect(lambda: self.evenly_space_horizontal())

        self.align_button_shortcut = QShortcut(QtGui.QKeySequence("Ctrl+Shift+Up"), self)
        self.align_button_shortcut.activated.connect(lambda: self.evenly_space_vertical())

        self.align_button_shortcut = QShortcut(QtGui.QKeySequence("Ctrl+Shift+Down"), self)
        self.align_button_shortcut.activated.connect(lambda: self.evenly_space_vertical())

    def add_curve_button_at_position(self):
        """Add a curve button at the specified position"""
        from . import maya_curve_converter as MCC
        MCC.create_buttons_from_maya_curves(self, self.get_center_position())

    def copy_selected_buttons(self):
        if self.edit_mode:
            selected_buttons = self.get_selected_buttons()
            if selected_buttons:
                PB.ButtonClipboard.instance().copy_buttons(selected_buttons)
    
    def delete_selected_buttons(self):
        if self.edit_mode:
            selected_buttons = self.get_selected_buttons()
            selected_buttons[0].delete_selected_buttons()
    
    def align_button_center(self):
        """Align selected buttons to be centered horizontally"""
        main_window = self.window()
        if self.edit_mode:
            selected_buttons = self.get_selected_buttons()
            if len(selected_buttons) <= 1:
                return
                
            # Calculate the average x position (center point)
            avg_x = sum(button.scene_position.x() for button in selected_buttons) / len(selected_buttons)
            
            # Move all buttons to have the same x coordinate
            for button in selected_buttons:
                current_pos = button.scene_position
                new_pos = QtCore.QPointF(avg_x, current_pos.y())
                button.scene_position = new_pos
                
            if hasattr(main_window, 'batch_update_buttons_to_database'):
                main_window.batch_update_buttons_to_database(selected_buttons)
            self.update_button_positions()
            self.update()

    def align_button_left(self):
        """Align selected buttons to the leftmost button's left edge"""
        main_window = self.window()

        if self.edit_mode:
            selected_buttons = self.get_selected_buttons()
            if len(selected_buttons) <= 1:
                return
                
            # Find the leftmost button's left edge position
            left_edge = float('inf')
            for button in selected_buttons:
                # Calculate the left edge position (center x - half width)
                button_left = button.scene_position.x() - (button.width / 2)
                left_edge = min(left_edge, button_left)
            
            # Move all buttons to align their left edges
            for button in selected_buttons:
                current_pos = button.scene_position
                # Calculate new center position (left_edge + half width)
                new_center_x = left_edge + (button.width / 2)
                new_pos = QtCore.QPointF(new_center_x, current_pos.y())
                button.scene_position = new_pos

            if hasattr(main_window, 'batch_update_buttons_to_database'):
                main_window.batch_update_buttons_to_database(selected_buttons)
            self.update_button_positions()
            self.update()
    
    def align_button_right(self):
        """Align selected buttons to the rightmost button's right edge"""
        main_window = self.window()
        if self.edit_mode:
            selected_buttons = self.get_selected_buttons()
            if len(selected_buttons) <= 1:
                return
                
            # Find the rightmost button's right edge position
            right_edge = float('-inf')
            for button in selected_buttons:
                # Calculate the right edge position (center x + half width)
                button_right = button.scene_position.x() + (button.width / 2)
                right_edge = max(right_edge, button_right)
            
            # Move all buttons to align their right edges
            for button in selected_buttons:
                current_pos = button.scene_position
                # Calculate new center position (right_edge - half width)
                new_center_x = right_edge - (button.width / 2)
                new_pos = QtCore.QPointF(new_center_x, current_pos.y())
                button.scene_position = new_pos
            
            if hasattr(main_window, 'batch_update_buttons_to_database'):
                main_window.batch_update_buttons_to_database(selected_buttons)
            self.update_button_positions()
            self.update()
    #---------------------------------------------------------------------------------------
    def align_button_top(self):
        """Align selected buttons to the topmost button's top edge"""
        main_window = self.window()
        if self.edit_mode:
            selected_buttons = self.get_selected_buttons()
            if len(selected_buttons) <= 1:
                return
                
            # Find the topmost button's top edge position (lowest y value in scene coordinates)
            top_edge = float('inf')
            for button in selected_buttons:
                # Calculate the top edge position (center y - half height)
                button_top = button.scene_position.y() - (button.height / 2)
                top_edge = min(top_edge, button_top)
            
            # Move all buttons to align their top edges
            for button in selected_buttons:
                current_pos = button.scene_position
                # Calculate new center position (top_edge + half height)
                new_center_y = top_edge + (button.height / 2)
                new_pos = QtCore.QPointF(current_pos.x(), new_center_y)
                button.scene_position = new_pos
            
            if hasattr(main_window, 'batch_update_buttons_to_database'):
                main_window.batch_update_buttons_to_database(selected_buttons)
            self.update_button_positions()
            self.update()
    
    def align_button_middle(self):
        """Align selected buttons to be centered vertically"""
        main_window = self.window()
        if self.edit_mode:
            selected_buttons = self.get_selected_buttons()
            if len(selected_buttons) <= 1:
                return
                
            # Calculate the average y position (middle point)
            avg_y = sum(button.scene_position.y() for button in selected_buttons) / len(selected_buttons)
            
            # Move all buttons to have the same y coordinate
            for button in selected_buttons:
                current_pos = button.scene_position
                new_pos = QtCore.QPointF(current_pos.x(), avg_y)
                button.scene_position = new_pos
            
            if hasattr(main_window, 'batch_update_buttons_to_database'):
                main_window.batch_update_buttons_to_database(selected_buttons)
            self.update_button_positions()
            self.update()
    
    def align_button_bottom(self):
        """Align selected buttons to the bottommost button's bottom edge"""
        main_window = self.window()
        if self.edit_mode:
            selected_buttons = self.get_selected_buttons()
            if len(selected_buttons) <= 1:
                return
                
            # Find the bottommost button's bottom edge position (highest y value in scene coordinates)
            bottom_edge = float('-inf')
            for button in selected_buttons:
                # Calculate the bottom edge position (center y + half height)
                button_bottom = button.scene_position.y() + (button.height / 2)
                bottom_edge = max(bottom_edge, button_bottom)
            
            # Move all buttons to align their bottom edges
            for button in selected_buttons:
                current_pos = button.scene_position
                # Calculate new center position (bottom_edge - half height)
                new_center_y = bottom_edge - (button.height / 2)
                new_pos = QtCore.QPointF(current_pos.x(), new_center_y)
                button.scene_position = new_pos
            
            if hasattr(main_window, 'batch_update_buttons_to_database'):
                main_window.batch_update_buttons_to_database(selected_buttons)
            self.update_button_positions()
            self.update()
    #---------------------------------------------------------------------------------------       
    def evenly_space_horizontal(self):
        """Distribute selected buttons evenly along the horizontal axis"""
        main_window = self.window()
        if self.edit_mode:
            selected_buttons = self.get_selected_buttons()
            if len(selected_buttons) <= 2:  # Need at least 3 buttons for spacing to make sense
                return
                
            # Sort buttons by x position
            sorted_buttons = sorted(selected_buttons, key=lambda btn: btn.scene_position.x())
            
            # Get leftmost and rightmost positions
            left_x = sorted_buttons[0].scene_position.x()
            right_x = sorted_buttons[-1].scene_position.x()
            
            # Calculate spacing
            total_width = right_x - left_x
            spacing = total_width / (len(sorted_buttons) - 1) if len(sorted_buttons) > 1 else 0
            
            # Skip first and last buttons (they define the range)
            for i, button in enumerate(sorted_buttons[1:-1], 1):
                # Calculate new x position
                new_x = left_x + (i * spacing)
                current_pos = button.scene_position
                new_pos = QtCore.QPointF(new_x, current_pos.y())
                button.scene_position = new_pos
            
            if hasattr(main_window, 'batch_update_buttons_to_database'):
                main_window.batch_update_buttons_to_database(selected_buttons)
            self.update_button_positions()
            self.update()
                
    def evenly_space_vertical(self):
        """Distribute selected buttons evenly along the vertical axis"""
        main_window = self.window()
        if self.edit_mode:
            selected_buttons = self.get_selected_buttons()
            if len(selected_buttons) <= 2:  # Need at least 3 buttons for spacing to make sense
                return
                
            
            # Sort buttons by y position
            sorted_buttons = sorted(selected_buttons, key=lambda btn: btn.scene_position.y())
            
            # Get topmost and bottommost positions
            top_y = sorted_buttons[0].scene_position.y()
            bottom_y = sorted_buttons[-1].scene_position.y()
            
            # Calculate spacing
            total_height = bottom_y - top_y
            spacing = total_height / (len(sorted_buttons) - 1) if len(sorted_buttons) > 1 else 0
            
            # Skip first and last buttons (they define the range)
            for i, button in enumerate(sorted_buttons[1:-1], 1):
                # Calculate new y position
                new_y = top_y + (i * spacing)
                current_pos = button.scene_position
                new_pos = QtCore.QPointF(current_pos.x(), new_y)
                button.scene_position = new_pos
            
            if hasattr(main_window, 'batch_update_buttons_to_database'):
                main_window.batch_update_buttons_to_database(selected_buttons)
            self.update_button_positions()
            self.update()
    
    #------------------------------------------------------------------------------
    # TRANSFORM GUIDES
    #------------------------------------------------------------------------------
    def on_transform_finished(self):
        """Handle transform guide operations completion"""
        # Force update of button positions and data
        self.update_button_positions()
        self.update()
        
        # Update button data for all selected buttons
        for button in self.get_selected_buttons():
            self.update_button_data(button)

    def update_transform_guides(self):
        """Update transform guides when selection or edit mode changes"""
        if hasattr(self, 'transform_guides'):
            self.transform_guides.update_selection()

    def hide_transform_guides(self):
        """Hide transform guides"""
        if hasattr(self, 'transform_guides'):
            self.transform_guides.setVisible(False)
            self.transform_guides.visual_layer.setVisible(False)

            if hasattr(self.transform_guides, 'controls_widget'):  
                self.transform_guides.controls_widget.setVisible(False)
    
    def _update_transform_guides_position(self):
        """Helper method to update transform guides position"""
        if hasattr(self, 'transform_guides') and self.transform_guides.isVisible():
            self.transform_guides.calculate_bounding_rect()
            self.transform_guides.update_position()

    def update_pan_offset(self, delta):
        """Helper method to update pan offset and transform guides"""
        self.pan_offset += QtCore.QPointF(delta.x(), delta.y())

        # Throttled transform guides update (persistent timer prevents accumulation)
        self._request_guides_update()
    
    def _update_guides_after_button_change(self):
        """Update transform guides after button changes"""
        if hasattr(self, 'transform_guides') and self.edit_mode:
            QtCore.QTimer.singleShot(10, self.transform_guides.update_selection)
    
    def connect_button_signals(self, button):
        """Connect button signals for real-time transform guide updates"""
        button.deleted.connect(self.remove_button)
        button.selected.connect(self.on_button_selected)
        button.changed.connect(self.on_button_changed)
        
        # CRITICAL FIX: Connect to position changes for transform guides
        if hasattr(button, 'position_changed'):
            button.position_changed.connect(self._update_transform_guides_position)
    #------------------------------------------------------------------------------
    def select_buttons_in_rect(self, rect, add_to_selection=False, remove_from_selection=False):
        # If not adding to selection and not removing, clear existing selection
        if not add_to_selection and not remove_from_selection:
            self.clear_selection()

        selection_changed = False
        for button in self.buttons:
            # Skip buttons that are not selectable in select mode
            if not self.edit_mode and hasattr(button, 'selectable') and not button.selectable:
                continue
                
            button_rect = button.geometry()
            if rect.intersects(button_rect):
                if remove_from_selection:
                    # Ctrl+Shift: Remove from selection
                    if button.is_selected:
                        button.is_selected = False
                        selection_changed = True
                elif add_to_selection or not button.is_selected:
                    # Shift: Add to selection, or No modifiers: Select if not already selected
                    if not button.is_selected:
                        button.is_selected = True
                        selection_changed = True

        if selection_changed:
            self.button_selection_changed.emit()
            self.update_hud_counts()

    def update_visual_selection(self, rect, add_to_selection=False, remove_from_selection=False):
        """Update button selection visually during rubber band drag with shape awareness"""
        # Get buttons in current rectangle
        current_buttons = set()
        
        # Convert selection rect to scene coordinates
        rect_top_left = self.canvas_to_scene_coords(QtCore.QPointF(rect.left(), rect.top()))
        rect_bottom_right = self.canvas_to_scene_coords(QtCore.QPointF(rect.right(), rect.bottom()))
        
        scene_rect = QtCore.QRectF(rect_top_left, rect_bottom_right).normalized()
        
        # Find buttons that intersect with selection rectangle
        for button in self.buttons:
            if not button.isVisible():
                continue
                
            # Skip non-selectable buttons in select mode
            if not self.edit_mode and hasattr(button, 'selectable') and not button.selectable:
                continue
            
            # AABB pre-cull using rotated envelope for speed
            button_pos = button.scene_position
            if hasattr(button, 'rotated_envelope_size'):
                env_w, env_h = button.rotated_envelope_size()
            else:
                env_w, env_h = button.width, button.height
            envelope_rect = QtCore.QRectF(
                button_pos.x() - env_w / 2,
                button_pos.y() - env_h / 2,
                env_w,
                env_h
            )

            if scene_rect.intersects(envelope_rect):
                # Now check if the button's actual shape intersects with selection
                if self._button_shape_intersects_rect(button, scene_rect):
                    current_buttons.add(button)
        
        # Track selection changes for signal emission
        selection_changed = False
        
        # Update selection states
        for button in self.buttons:
            old_selection = button.is_selected
            
            if button in current_buttons:
                # Button is in selection rectangle
                if remove_from_selection:
                    # CTRL+SHIFT: Remove from selection when in rectangle
                    button.is_selected = False
                elif add_to_selection:
                    # SHIFT only: Add to selection when in rectangle
                    button.is_selected = True
                else:
                    # No modifiers: Select when in rectangle
                    button.is_selected = True
            else:
                # Button not in rectangle - restore initial state
                if button in self.initial_selection_state:
                    button.is_selected = self.initial_selection_state[button]
            
            # Check if selection state changed
            if old_selection != button.is_selected:
                selection_changed = True
                # Emit individual button selection signal
                button.selected.emit(button, button.is_selected)
            
            button.update()
        
        # Track current drag buttons for final selection
        self.buttons_in_current_drag = current_buttons
        
        # Invalidate selection cache
        if hasattr(self, '_cache_valid'):
            self._cache_valid = False
        
        # Update HUD and emit selection changed signal if anything changed
        if selection_changed:
            self.update_hud_counts()
            self.button_selection_changed.emit()

    def _button_shape_intersects_rect(self, button, scene_rect):
        """
        Check if a button's actual (rotated, possibly custom) shape intersects
        a selection rectangle in scene coordinates. Uses the same cached scene
        path as paint_on_canvas/hit_test_scene so selection matches the visible
        shape exactly.
        """
        try:
            button_path = button._get_scene_path(button.width, button.height)

            transform = QtGui.QTransform()
            transform.translate(button.scene_position.x(), button.scene_position.y())
            if getattr(button, 'rotation', 0):
                transform.rotate(button.rotation)
            scene_button_path = transform.map(button_path)

            selection_path = QtGui.QPainterPath()
            selection_path.addRect(scene_rect)

            return scene_button_path.intersects(selection_path)

        except Exception as e:
            print(f"Error checking button shape intersection: {e}")
            button_pos = button.scene_position
            if hasattr(button, 'rotated_envelope_size'):
                env_w, env_h = button.rotated_envelope_size()
            else:
                env_w, env_h = button.width, button.height
            envelope_rect = QtCore.QRectF(
                button_pos.x() - env_w / 2,
                button_pos.y() - env_h / 2,
                env_w,
                env_h
            )
            return scene_rect.intersects(envelope_rect)
    #------------------------------------------------------------------------------
    def _show_button_tooltip(self):
        """Show tooltip for the currently hovered button"""
        # Safety check: ensure the button still exists and is valid
        try:
            if not hasattr(self._current_hover_button, 'tooltip_widget'):
                return
        except:
            # Button has been deleted, clear reference
            self._current_hover_button = None
            return
        
        # Rebuild tooltip content if needed
        try:
            if self._current_hover_button._tooltip_needs_update:
                self._current_hover_button._rebuild_tooltip_content()
        except:
            # Button is being deleted, clear reference
            self._current_hover_button = None
            return
        
        # Get or create tooltip widget
        if not self._tooltip_widget:
            self._tooltip_widget = self._current_hover_button.tooltip_widget
        else:
            # Reuse existing widget but update content
            self._tooltip_widget = self._current_hover_button.tooltip_widget
        
        # Position tooltip with screen boundary checking
        screen = QtWidgets.QApplication.screenAt(self._tooltip_position)
        if screen:
            screen_rect = screen.availableGeometry()
            tooltip_pos = self._tooltip_position + QtCore.QPoint(10, 10)
            
            # Adjust if tooltip would go off screen
            if tooltip_pos.x() + self._tooltip_widget.width() > screen_rect.right():
                tooltip_pos.setX(self._tooltip_position.x() - self._tooltip_widget.width() - 10)
            if tooltip_pos.y() + self._tooltip_widget.height() > screen_rect.bottom():
                tooltip_pos.setY(self._tooltip_position.y() - self._tooltip_widget.height() - 10)
                
            self._tooltip_widget.move(tooltip_pos)
        else:
            self._tooltip_widget.move(self._tooltip_position + QtCore.QPoint(10, 10))
        
        self._tooltip_widget.show()

    def _hide_button_tooltip(self):
        """Hide the current button tooltip"""
        self._tooltip_timer.stop()
        try:
            if self._tooltip_widget and self._tooltip_widget.isVisible():
                self._tooltip_widget.hide()
        except:
            pass
        self._current_hover_button = None

    def _update_hover_button(self, pos):
        """Update which button is being hovered over.

        In canvas-painted mode, hover is determined by the _current_hover_button
        reference checked during paint — no per-button is_hovered flag needed.
        """
        button = self._get_button_at_position(pos)

        if button != self._current_hover_button:
            self._hide_button_tooltip()

            # Clear old hover (keep is_hovered in sync for non-canvas-painted fallback)
            old = self._current_hover_button
            if old:
                try:
                    old.is_hovered = False
                    old.update()
                except:
                    pass

            self._current_hover_button = button

            if button:
                try:
                    button.is_hovered = True
                    button.update()
                    self._tooltip_position = QtGui.QCursor.pos()
                    self._tooltip_timer.start(800)
                    # Set cursor to match button's cursor (e.g. PointingHandCursor)
                    if button._canvas_painted:
                        self.setCursor(button.cursor())
                except:
                    self._current_hover_button = None
            else:
                # No button under cursor — restore default canvas cursor
                self.setCursor(QtCore.Qt.ArrowCursor)

            # Single canvas repaint — hover visuals read _current_hover_button
            self.update()
    #------------------------------------------------------------------------------
    # SELECTION LOGIC
    #------------------------------------------------------------------------------
    def apply_final_selection(self, add_to_selection=False, ctrl_held=False, alt_held=False):
        """Enhanced selection with proper modifier handling and counterpart support"""
        if self.edit_mode:
            return
        
        # Temporarily disable sync to prevent loops when we apply Maya selection
        try:
            manager = SSM.SelectionSyncManager.get_instance()
            manager._sync_lock = True  # Use sync lock to prevent conflicts
        except:
            pass
            
        try:
            # Handle deselection mode (ctrl+shift)
            if add_to_selection and ctrl_held:
                deselected_buttons = self._get_deselected_buttons()
                if deselected_buttons:
                    self._apply_maya_deselection(deselected_buttons, alt_held)
                    return
            
            # Build ordered selection list
            final_selections = self._build_ordered_selection_list(add_to_selection)
            
            if not final_selections:
                return
            
            # Resolve objects based on alt modifier
            if alt_held:
                new_selection, missing_objects, uuid_updates = self._resolve_counterpart_objects(final_selections)
            else:
                new_selection, missing_objects, uuid_updates = self._resolve_objects(final_selections)
            
            # Apply Maya selection
            self._apply_maya_selection_with_modifiers(new_selection, add_to_selection, alt_held)
            
            # Handle missing objects and UI updates
            if missing_objects:
                self._show_missing_objects_dialog(missing_objects)
            
            self._update_ui_state(uuid_updates)
            
        except Exception as e:
            print(f"Error in apply_final_selection: {e}")
        finally:
            # Restore sync state with a delay to ensure Maya selection is complete
            try:
                manager = SSM.SelectionSyncManager.get_instance()
                # Use the manager's delayed_unlock which includes post-unlock resync
                QtCore.QTimer.singleShot(150, manager._delayed_unlock)
            except:
                pass

    def _apply_maya_deselection(self, deselected_buttons, alt_held=False):
        """Apply deselection to Maya with counterpart support"""
        objects_to_deselect = []
        
        for button in deselected_buttons:
            if button.assigned_objects:
                if alt_held:
                    # Deselect counterparts
                    resolved_counterparts, _, _ = self._resolve_button_counterparts(button)
                    objects_to_deselect.extend(resolved_counterparts)
                else:
                    # Deselect regular objects
                    resolved_objects, _, _ = self._resolve_button_objects(button)
                    objects_to_deselect.extend(resolved_objects)
        
        if objects_to_deselect:
            cmds.undoInfo(openChunk=True)
            try:
                main_window = self.window()
                current_namespace = main_window.namespace_dropdown.currentText()
                
                for obj in objects_to_deselect:
                    namespaced_obj = f"{current_namespace}:{obj}" if current_namespace and current_namespace != 'None' else obj
                    if cmds.objExists(namespaced_obj):
                        try:
                            cmds.select(namespaced_obj, deselect=True)
                        except:
                            pass
            finally:
                cmds.undoInfo(closeChunk=True)

    def _apply_maya_selection_with_modifiers(self, new_selection, add_to_selection, alt_held):
        """Apply Maya selection with proper modifier handling"""
        cmds.undoInfo(openChunk=True)
        try:
            if not add_to_selection:
                cmds.select(clear=True)
            
            if new_selection:
                main_window = self.window()
                current_namespace = main_window.namespace_dropdown.currentText()
                
                resolved_selection = []
                resolved_names = []
                
                for sel in new_selection:
                    namespaced_node = f"{current_namespace}:{sel}" if current_namespace and current_namespace != 'None' else sel
                    if cmds.objExists(namespaced_node):
                        resolved_selection.append(namespaced_node)
                    else:
                        resolved_selection.append(sel)
                    
                    sel_name = sel.split(':')[-1].split('|')[-1]
                    resolved_names.append(sel_name)
                
                selection_type = "counterparts" if alt_held else "objects"
                #print(f"Selecting {selection_type}: {', '.join(resolved_names)}")
                
                if resolved_selection:
                    cmds.select(resolved_selection, add=True)
                    # Make last node active
                    cmds.select(resolved_selection[-1], toggle=True)
                    cmds.select(resolved_selection[-1], add=True)
        finally:
            cmds.undoInfo(closeChunk=True)

    def _get_deselected_buttons(self):
        """Get buttons that were deselected during current drag"""
        return {button for button in self.buttons_in_current_drag 
                if not button.is_selected}

    def _build_ordered_selection_list(self, add_to_selection):
        """Build ordered list of selected buttons"""
        final_selections = []
        
        # Add previously selected buttons if adding to selection
        if add_to_selection:
            for button in self.buttons:
                if button.is_selected and button not in self.buttons_in_current_drag:
                    final_selections.append(button)
        
        # Add currently selected buttons (except last clicked)
        last_clicked = next(reversed(list(self.buttons_in_current_drag)), None)
        for button in self.buttons_in_current_drag:
            if button.is_selected and button != last_clicked:
                final_selections.append(button)
        
        # Add last clicked button at the end
        if last_clicked and last_clicked.is_selected:
            final_selections.append(last_clicked)
        
        return final_selections

    def _resolve_objects(self, final_selections):
        """Resolve objects for selected buttons and update UUIDs"""
        new_selection = []
        missing_objects = set()
        uuid_updates = False
        
        for button in final_selections:
            if not button.assigned_objects:
                continue
                
            resolved_objects, button_missing, button_uuid_updates = self._resolve_button_objects(button)
            new_selection.extend(resolved_objects)
            missing_objects.update(button_missing)
            uuid_updates = uuid_updates or button_uuid_updates
        
        return new_selection, missing_objects, uuid_updates

    def _resolve_button_objects(self, button):
        """Resolve objects for a single button"""
        main_window = self.window()
        if not isinstance(main_window, UI.AnimPickerWindow):
            return [], set(), False
        
        current_namespace = main_window.namespace_dropdown.currentText()
        resolved_objects = []
        missing_objects = set()
        updated_objects = []
        uuid_updates = False
        
        for obj_data in button.assigned_objects:
            resolved_node, new_uuid, was_updated = self._resolve_single_object(
                obj_data, current_namespace
            )
            
            if resolved_node:
                resolved_objects.append(resolved_node)
                updated_objects.append({
                    'uuid': new_uuid or obj_data['uuid'],
                    'long_name': resolved_node
                })
                if was_updated:
                    uuid_updates = True
            else:
                base_name = obj_data['long_name'].split('|')[-1].split(':')[-1]
                missing_objects.add(f"- {base_name}")
                updated_objects.append(obj_data)
        
        # Update button's assigned objects with new UUIDs
        button.assigned_objects = updated_objects
        if uuid_updates:
            button.changed.emit(button)
        
        return resolved_objects, missing_objects, uuid_updates

    def _resolve_single_object(self, obj_data, current_namespace):
        """Resolve a single object using multiple fallback strategies"""
        uuid = obj_data['uuid']
        long_name = obj_data['long_name']
        base_name = long_name.split('|')[-1].split(':')[-1]
        
        # Strategy 1: Try UUID resolution
        resolved_node, new_uuid = self._try_uuid_resolution(uuid)
        if resolved_node:
            return resolved_node.split(':')[-1], new_uuid, False
        
        # Strategy 2: Try exact long name
        resolved_node, new_uuid = self._try_exact_name_resolution(long_name)
        if resolved_node:
            return resolved_node, new_uuid, True
        
        # Strategy 3: Try namespaced resolution
        if current_namespace and current_namespace != 'None':
            resolved_node, new_uuid = self._try_namespaced_resolution(
                current_namespace, base_name
            )
            if resolved_node:
                return resolved_node, new_uuid, True
        
        # Strategy 4: Try base name resolution
        resolved_node, new_uuid = self._try_base_name_resolution(base_name)
        if resolved_node:
            return resolved_node, new_uuid, True
        
        return None, None, False

    def _try_uuid_resolution(self, uuid):
        """Try to resolve object by UUID"""
        try:
            nodes = cmds.ls(uuid, long=True)
            if nodes:
                return nodes[0], uuid
        except:
            pass
        return None, None

    def _try_exact_name_resolution(self, long_name):
        """Try to resolve object by exact long name"""
        try:
            if cmds.objExists(long_name):
                new_uuid = cmds.ls(long_name, uuid=True)[0]
                return long_name, new_uuid
        except:
            pass
        return None, None

    def _try_namespaced_resolution(self, namespace, base_name):
        """Try to resolve object with current namespace"""
        try:
            namespaced_node = f"{namespace}:{base_name}"
            if cmds.objExists(namespaced_node):
                new_uuid = cmds.ls(namespaced_node, uuid=True)[0]
                return namespaced_node, new_uuid
        except:
            pass
        return None, None

    def _try_base_name_resolution(self, base_name):
        """Try to resolve object by base name only"""
        try:
            if cmds.objExists(base_name):
                new_uuid = cmds.ls(base_name, uuid=True)[0]
                return base_name, new_uuid
        except:
            pass
        return None, None

    def _apply_maya_selection(self, new_selection, deselected_buttons, add_to_selection):
        """Apply the selection in Maya"""
        cmds.undoInfo(openChunk=True)
        try:
            if not add_to_selection:
                cmds.select(clear=True)
            else:
                self._deselect_button_objects(deselected_buttons)
            
            if new_selection:
                self._select_resolved_objects(new_selection)
        finally:
            cmds.undoInfo(closeChunk=True)

    def _deselect_button_objects(self, deselected_buttons):
        """Deselect objects from deselected buttons"""
        for button in deselected_buttons:
            for obj_data in button.assigned_objects:
                resolved_node = self._get_existing_object(obj_data)
                if resolved_node:
                    try:
                        cmds.select(resolved_node, deselect=True)
                    except:
                        continue

    def _get_existing_object(self, obj_data):
        """Get existing object from obj_data, trying UUID first then long_name"""
        try:
            # Try UUID first
            nodes = cmds.ls(obj_data['uuid'], long=True)
            if nodes:
                return nodes[0]
            
            # Fallback to long name
            if cmds.objExists(obj_data['long_name']):
                return obj_data['long_name']
        except:
            pass
        return None

    def _select_resolved_objects(self, new_selection):
        """Select the resolved objects in Maya"""
        main_window = self.window()
        current_namespace = main_window.namespace_dropdown.currentText()
        
        resolved_selection = []
        resolved_names = []
        
        for sel in new_selection:
            namespaced_node = f"{current_namespace}:{sel}"
            if cmds.objExists(namespaced_node):
                resolved_selection.append(namespaced_node)
            else:
                resolved_selection.append(sel)
            
            sel_name = sel.split(':')[-1].split('|')[-1]
            resolved_names.append(sel_name)
        
        #print(f"Selecting: {', '.join(resolved_names)}")
        cmds.select(resolved_selection, add=True)
        
        # Make last node active
        if resolved_selection:
            cmds.select(resolved_selection[-1], toggle=True)
            cmds.select(resolved_selection[-1], add=True)

    def _show_missing_objects_dialog(self, missing_objects):
        """Show dialog for missing objects"""
        parent_widget = self.parentWidget()
        dialog = CD.CustomDialog(
            parent_widget, 
            title="Missing Objects", 
            size=(250, -1), 
            info_box=True
        )
        
        message_label = QtWidgets.QLabel("The following objects were not found:")
        details_label = QtWidgets.QLabel(
            '\n'.join(sorted(f"<b><font color='#00ade6'>{obj}</font></b>" 
                            for obj in missing_objects))
        )
        note_label = QtWidgets.QLabel("[Objects may have been deleted or renamed]")
        
        dialog.add_widget(message_label)
        dialog.add_widget(details_label)
        dialog.add_widget(note_label)
        dialog.add_button_box()
        dialog.exec_()

    def _update_ui_state(self, uuid_updates):
        """Update UI state after selection changes"""
        for button in self.buttons:
            button.update()
            button.update_tooltip()
        
        self.button_selection_changed.emit()
        self.update_hud_counts()
        
        if uuid_updates:
            main_window = self.window()
            if isinstance(main_window, UI.AnimPickerWindow):
                main_window.update_buttons_for_current_tab()
    #------------------------------------------------------------------------------
    def _resolve_counterpart_objects(self, final_selections):
        """Resolve counterpart objects for selected buttons"""
        new_selection = []
        missing_objects = set()
        uuid_updates = False
        
        for button in final_selections:
            if not button.assigned_objects:
                continue
                
            resolved_counterparts, button_missing, button_uuid_updates = self._resolve_button_counterparts(button)
            new_selection.extend(resolved_counterparts)
            missing_objects.update(button_missing)
            uuid_updates = uuid_updates or button_uuid_updates
        
        return new_selection, missing_objects, uuid_updates

    def _resolve_button_counterparts(self, button):
        """Resolve counterpart objects for a single button"""
        main_window = self.window()
        if not isinstance(main_window, UI.AnimPickerWindow):
            return [], set(), False
        
        current_namespace = main_window.namespace_dropdown.currentText()
        resolved_counterparts = []
        missing_objects = set()
        uuid_updates = False
        
        # Get naming conventions and mirror preferences
        naming_conventions = self._get_naming_conventions("", "")
        mirror_preferences = self._load_mirror_preferences_for_objects(button.assigned_objects, current_namespace)
        
        for obj_data in button.assigned_objects:
            resolved_source_obj = self._resolve_object_name_from_data(obj_data, current_namespace)
            
            if resolved_source_obj:
                # Find the mirrored object
                namespace, short_name = self._extract_namespace_and_name(resolved_source_obj)
                mirrored_name, is_center_object = self._find_mirrored_name(
                    short_name, naming_conventions, mirror_preferences, namespace
                )
                
                if cmds.objExists(mirrored_name) and mirrored_name != resolved_source_obj:
                    # Get the short name for selection
                    counterpart_short_name = mirrored_name.split('|')[-1].split(':')[-1]
                    resolved_counterparts.append(counterpart_short_name)
                else:
                    if mirrored_name == resolved_source_obj:
                        # Center object - select itself
                        source_short_name = resolved_source_obj.split('|')[-1].split(':')[-1]
                        resolved_counterparts.append(source_short_name)
                    else:
                        # Missing counterpart
                        base_name = obj_data['long_name'].split('|')[-1].split(':')[-1]
                        missing_objects.add(f"- {base_name} (counterpart)")
            else:
                base_name = obj_data['long_name'].split('|')[-1].split(':')[-1]
                missing_objects.add(f"- {base_name}")
        
        return resolved_counterparts, missing_objects, uuid_updates

    def _get_naming_conventions(self, L, R):
        """
        Returns a list of naming conventions for left and right sides.
        
        Args:
            L (str): Custom left side identifier
            R (str): Custom right side identifier
            
        Returns:
            list: List of dictionaries with left and right patterns
        """
        naming_conventions = [
            # Prefix
            {"left": "L_", "right": "R_"},
            {"left": "left_", "right": "right_"},
            {"left": "Lf_", "right": "Rt_"},
            {"left": "lt_", "right": "rt_"},
            
            # Suffix
            {"left": "_L", "right": "_R"},
            {"left": "_left", "right": "_right"},
            {"left": "_lt", "right": "_rt"},
            {"left": "_lf", "right": "_rf"},
            {"left": "_l_", "right": "_r_"},
            
            # Other patterns
            {"left": ":l_", "right": ":r_"},
            {"left": "^l_", "right": "^r_"},
            {"left": "_l$", "right": "_r$"},
            {"left": ":L", "right": ":R"},
            {"left": "^L", "right": "^R"},
            {"left": "Left", "right": "Right"},
            {"left": "left", "right": "right"}
        ]
        
        # Add custom naming convention if provided
        if L and R:
            naming_conventions.append({"left": L, "right": R})
            
        return naming_conventions

    def _extract_namespace_and_name(self, full_name):
        """
        Extracts namespace and object name from a full object path.
        
        Args:
            full_name (str): Full object name with potential namespace
            
        Returns:
            tuple: (namespace, short_name) where namespace includes the colon if present
        """
        # Handle long names (with |) - get the leaf name first
        leaf_name = full_name.split('|')[-1]
        
        # Check for namespace
        if ':' in leaf_name:
            parts = leaf_name.split(':')
            namespace = ':'.join(parts[:-1]) + ':'  # Keep the colon
            short_name = parts[-1]
        else:
            namespace = ""
            short_name = leaf_name
        
        return namespace, short_name

    def _find_mirrored_name(self, obj_name, naming_conventions, mirror_preferences=None, namespace=""):
        """
        Finds the mirrored name for the given object name.
        
        Args:
            obj_name (str): Object name to find mirror for (short name without namespace)
            naming_conventions (list): List of naming conventions
            mirror_preferences (dict, optional): Dictionary of mirror preferences
            namespace (str, optional): Namespace to apply to the mirrored name
            
        Returns:
            tuple: (mirrored_name, is_center_object) where mirrored_name is the full name of the mirrored object
                and is_center_object is a boolean indicating if the object is a center object
        """
        # Check if we have a mirror preference with a counterpart defined
        if mirror_preferences:
            # First check if this object has preferences with a counterpart defined
            if obj_name in mirror_preferences:
                pref_data = mirror_preferences[obj_name]
                if "counterpart" in pref_data and pref_data["counterpart"]:
                    counterpart = pref_data["counterpart"]
                    # Apply namespace to counterpart
                    full_counterpart = self._construct_full_name(namespace, counterpart)
                    return full_counterpart, False
            
            # If not, check if any object has this object defined as its counterpart
            for other_obj, pref_data in mirror_preferences.items():
                if "counterpart" in pref_data and pref_data["counterpart"] == obj_name:
                    # Apply namespace to the other object
                    full_other = self._construct_full_name(namespace, other_obj)
                    return full_other, False
        
        is_center_object = True  # Assume it's a center object until proven otherwise
        
        for convention in naming_conventions:
            left_pattern = convention["left"]
            right_pattern = convention["right"]
            
            if left_pattern in obj_name:
                is_center_object = False
                mirrored_short_name = obj_name.replace(left_pattern, right_pattern)
                mirrored_name = self._construct_full_name(namespace, mirrored_short_name)
                return mirrored_name, is_center_object
            elif right_pattern in obj_name:
                is_center_object = False
                mirrored_short_name = obj_name.replace(right_pattern, left_pattern)
                mirrored_name = self._construct_full_name(namespace, mirrored_short_name)
                return mirrored_name, is_center_object
        
        # If no pattern matched, it's a center object - return with namespace
        full_name = self._construct_full_name(namespace, obj_name)
        return full_name, is_center_object

    def _construct_full_name(self, namespace, short_name):
        """
        Constructs full object name with namespace.
        
        Args:
            namespace (str): Namespace with colon if present
            short_name (str): Short object name
            
        Returns:
            str: Full object name
        """
        return f"{namespace}{short_name}" if namespace else short_name

    def _resolve_object_name_from_data(self, obj_data, current_namespace):
        """Resolve object name from object data (with UUID and long_name)"""
        uuid = obj_data['uuid']
        long_name = obj_data['long_name']
        base_name = long_name.split('|')[-1].split(':')[-1]
        
        # Strategy 1: Try UUID resolution
        resolved_node, _ = self._try_uuid_resolution(uuid)
        if resolved_node:
            return resolved_node
        
        # Strategy 2: Try exact long name
        resolved_node, _ = self._try_exact_name_resolution(long_name)
        if resolved_node:
            return resolved_node
        
        # Strategy 3: Try namespaced resolution
        if current_namespace and current_namespace != 'None':
            resolved_node, _ = self._try_namespaced_resolution(current_namespace, base_name)
            if resolved_node:
                return resolved_node
        
        # Strategy 4: Try base name resolution
        resolved_node, _ = self._try_base_name_resolution(base_name)
        if resolved_node:
            return resolved_node
        
        return None

    def _load_mirror_preferences_for_objects(self, assigned_objects, current_namespace):
        """
        Load mirror preferences for assigned objects and their potential counterparts.
        
        Args:
            assigned_objects (list): List of assigned object data
            current_namespace (str): Current namespace
            
        Returns:
            dict: Dictionary of mirror preferences
        """
        import json
        mirror_preferences = {}
        naming_conventions = self._get_naming_conventions("", "")
        
        # Load mirror preferences for all assigned objects
        for obj_data in assigned_objects:
            resolved_obj = self._resolve_object_name_from_data(obj_data, current_namespace)
            if resolved_obj and cmds.objExists(resolved_obj):
                namespace, short_name = self._extract_namespace_and_name(resolved_obj)
                
                if cmds.attributeQuery("mirrorPreference", node=resolved_obj, exists=True):
                    try:
                        pref_data_str = cmds.getAttr(f"{resolved_obj}.mirrorPreference")
                        mirror_preferences[short_name] = json.loads(pref_data_str)
                    except (json.JSONDecodeError, Exception) as e:
                        print(f"Error loading mirror preferences for {resolved_obj}: {e}")
        
        # Also load mirror preferences for potential counterparts
        potential_counterparts = set()
        for obj_data in assigned_objects:
            resolved_obj = self._resolve_object_name_from_data(obj_data, current_namespace)
            if resolved_obj:
                namespace, short_name = self._extract_namespace_and_name(resolved_obj)
                # Find the potential counterpart name
                counterpart_name, _ = self._find_mirrored_name(short_name, naming_conventions, namespace=namespace)
                if counterpart_name != resolved_obj:
                    potential_counterparts.add(counterpart_name)
        
        # Load preferences for counterparts if they exist
        for counterpart in potential_counterparts:
            if cmds.objExists(counterpart):
                counterpart_namespace, counterpart_short = self._extract_namespace_and_name(counterpart)
                if counterpart_short not in mirror_preferences:
                    if cmds.attributeQuery("mirrorPreference", node=counterpart, exists=True):
                        try:
                            pref_data_str = cmds.getAttr(f"{counterpart}.mirrorPreference")
                            mirror_preferences[counterpart_short] = json.loads(pref_data_str)
                        except (json.JSONDecodeError, Exception) as e:
                            print(f"Error loading mirror preferences for counterpart {counterpart}: {e}")
        
        return mirror_preferences
    #------------------------------------------------------------------------------
    def clear_selection(self):
        selection_changed = False
        for button in self.buttons:
            if button.is_selected:
                button.is_selected = False
                button.selected.emit(button, False)  # Emit the button's selected signal
                selection_changed = True
        
        if selection_changed:
            self.button_selection_changed.emit()
            self.update_hud_counts()

            if hasattr(self, 'transform_guides'):
                self.transform_guides.setVisible(False)
                self.transform_guides.visual_layer.setVisible(False)

    def get_selected_buttons(self):
        """Cached version of get_selected_buttons for better performance during drag."""
        if not hasattr(self, '_selected_buttons_cache'):
            self._selected_buttons_cache = []
            self._cache_valid = False

        if not self._cache_valid:
            self._selected_buttons_cache = [button for button in self.buttons if button.is_selected]
            self._cache_valid = True

        return self._selected_buttons_cache
    
    def on_button_selected(self, button, is_selected):
        if not is_selected:
            button.is_selected = False
        
        # Batch UI updates
        if not hasattr(self, '_selection_update_timer'):
            self._selection_update_timer = QtCore.QTimer()
            self._selection_update_timer.setSingleShot(True)
            self._selection_update_timer.timeout.connect(self._emit_selection_changed)
        
        self._selection_update_timer.stop()
        self._selection_update_timer.start(10)  # 10ms debounce

    def _get_button_at_position(self, pos):
        """Get the topmost visible button at the given position, respecting button shapes"""
        # Convert canvas pixel position to scene coordinates for hit testing
        scene_pos = self.canvas_to_scene_coords(QtCore.QPointF(pos))

        # Check buttons in reverse order (topmost first due to z-order)
        for button in reversed(self.buttons):
            if not button.isVisible():
                continue

            if button._canvas_painted:
                # Canvas-painted: math-based hit test in scene space
                if button.hit_test_scene(scene_pos):
                    return button
            else:
                # Legacy widget-based hit test
                if not button.geometry().contains(pos):
                    continue
                local_pos = button.mapFromParent(pos)
                if button.contains_point(local_pos):
                    return button

        return None

    def _emit_selection_changed(self):
        """Emit selection changed signals with batching"""
        if hasattr(self, '_cache_valid'):
            self._cache_valid = False  # Invalidate cache
        self.button_selection_changed.emit()
        self.update_hud_counts()
        self.update()
    
        # Update transform guides
        if hasattr(self, 'transform_guides'):
            QtCore.QTimer.singleShot(10, self.transform_guides.update_selection)
    #------------------------------------------------------------------------------
    def add_button(self, button):
        # Preserve original functionality
        self.buttons.append(button)
        button.setParent(self)
        button.show()
        button.deleted.connect(self.remove_button)
        button.selected.connect(self.on_button_selected)
        button.changed.connect(self.on_button_changed)
        button.edit_mode = self.edit_mode
        button.update_cursor()
        # Canvas-painted mode: rendering on canvas, widget is invisible
        button._canvas_painted = True
        button.setAttribute(QtCore.Qt.WA_TranslucentBackground, True)
        button.setAttribute(QtCore.Qt.WA_TransparentForMouseEvents, True)
        button.clearMask()
        button.lower()
        self.update_button_positions()

        # Update HUD button count
        self.update_hud_counts()
        self._update_guides_after_button_change()

    def add_buttons_batch(self, buttons):
        """Add multiple buttons at once, deferring expensive ops until the end."""
        for button in buttons:
            self.buttons.append(button)
            button.setParent(self)
            button.show()
            button.deleted.connect(self.remove_button)
            button.selected.connect(self.on_button_selected)
            button.changed.connect(self.on_button_changed)
            button.edit_mode = self.edit_mode
            button.update_cursor()
            button._canvas_painted = True
            button.setAttribute(QtCore.Qt.WA_TranslucentBackground, True)
            button.setAttribute(QtCore.Qt.WA_TransparentForMouseEvents, True)
            button.clearMask()
            button.lower()
        if buttons:
            self.update_button_positions()
            self.update_hud_counts()
            self._update_guides_after_button_change()

    def remove_button(self, button):
        if button in self.buttons:
            # Clear hover button reference if this button is the current hover button
            if self._current_hover_button == button:
                self._hide_button_tooltip()
            
            self.buttons.remove(button)
            self.update_button_positions()
            main_window = self.window()
            if isinstance(main_window, UI.AnimPickerWindow):
                main_window.update_button_data(button, deleted=True)
            
            # Update HUD button count
            self.update_hud_counts()
            self._update_guides_after_button_change()
            self.transform_guides.setVisible(False)
            self.transform_guides.visual_layer.setVisible(False)
            if hasattr(self.transform_guides, 'control_widget'):  
                self.transform_guides.control_widget.setVisible(False)

    def _flush_deferred_geometry(self):
        """Flush deferred widget geometry if dirty (called when pan/zoom ends)."""
        if self._geometry_dirty:
            self._geometry_dirty = False
            self.update_button_positions()
            self._update_hover_button(self.mapFromGlobal(QtGui.QCursor.pos()))

    def update_button_positions(self):
        """Optimized button position updating with better culling"""
        if not self.buttons:
            return
            
        visible_rect = self.rect()
        
        # Early exit if no size
        if visible_rect.width() <= 0 or visible_rect.height() <= 0:
            return
            
        # Calculate visible area with larger margin for smoother experience
        visible_scene_rect = QtCore.QRectF(
            self.canvas_to_scene_coords(QtCore.QPointF(visible_rect.left(), visible_rect.top())),
            self.canvas_to_scene_coords(QtCore.QPointF(visible_rect.right(), visible_rect.bottom()))
        ).normalized()
        
        # Larger margin to prevent popping
        margin = max(visible_scene_rect.width() * 0.5, visible_scene_rect.height() * 0.5)
        visible_scene_rect.adjust(-margin, -margin, margin, margin)
        
        # Batch geometry updates
        geometry_updates = []
        buttons_to_show = []
        buttons_to_hide = []
        
        for button in self.buttons:
            # Quick visibility test — use rotated envelope for accurate culling
            button_pos = button.scene_position
            env_w, env_h = button.rotated_envelope_size()
            button_rect = QtCore.QRectF(
                button_pos.x() - env_w/2,
                button_pos.y() - env_h/2,
                env_w,
                env_h
            )

            if visible_scene_rect.intersects(button_rect):
                # Calculate geometry using envelope size for the widget bounds
                canvas_pos = self.scene_to_canvas_coords(button_pos)
                scaled_width = env_w * self.zoom_factor
                scaled_height = env_h * self.zoom_factor
                
                # Calculate center-based position maintaining sub-pixel precision
                # Key: Keep full floating-point precision through the calculation
                # to ensure the same scene point maps consistently across zoom levels
                x = canvas_pos.x() - scaled_width / 2
                y = canvas_pos.y() - scaled_height / 2
                
                # Round to integer pixels at the very end
                # Using math.floor(v + 0.5) gives more consistent rounding than round()
                # especially for negative coordinates
                import math
                geometry_updates.append((
                    button, 
                    math.floor(x + 0.5),
                    math.floor(y + 0.5),
                    math.floor(scaled_width + 0.5),
                    math.floor(scaled_height + 0.5)
                ))
                buttons_to_show.append(button)
            else:
                buttons_to_hide.append(button)
        
        if hasattr(self, 'transform_guides') and self.transform_guides.isVisible():
            QtCore.QTimer.singleShot(5, self._update_transform_guides_position)

        # Apply all geometry updates at once
        self.setUpdatesEnabled(False)
        
        for button, x, y, w, h in geometry_updates:
            button.setGeometry(x, y, w, h)
            
        for button in buttons_to_show:
            if not button.isVisible():
                button.show()
                
        for button in buttons_to_hide:
            if button.isVisible():
                button.hide()
        
        self.setUpdatesEnabled(True)
    
    def update_button_data(self, button, deleted=False):
        main_window = self.window()
        if isinstance(main_window, UI.AnimPickerWindow):
            main_window.update_button_data(button, deleted)

    def on_button_changed(self, button):
        self.update_button_data(button)
        if (hasattr(self, 'transform_guides') and 
            self.transform_guides.isVisible() and 
            button in self.get_selected_buttons()):
            QtCore.QTimer.singleShot(5, self._update_transform_guides_position)
    
    def update_hud_counts(self):
        """Update HUD with current button counts"""
        selected_count = len(self.get_selected_buttons())
        total_count = len(self.buttons)
        self.hud.update_button_count(total_count, selected_count)
    #------------------------------------------------------------------------------
    def scene_to_canvas_coords(self, pos):
        # Convert scene coordinates to canvas coordinates
        center = QtCore.QPointF(self.width() / 2, self.height() / 2)
        canvas_pos = (pos * self.zoom_factor) + center + self.pan_offset
        return canvas_pos

    def canvas_to_scene_coords(self, pos):
        # Convert canvas coordinates to scene coordinates
        center = QtCore.QPointF(self.width() / 2, self.height() / 2)
        scene_pos = (pos - center - self.pan_offset) / self.zoom_factor
        return scene_pos
    
    def get_center_position(self):
        # Convert the center of the widget to scene coordinates
        center = QtCore.QPointF(self.width() / 2, self.height() / 2)
        self.update()
        return self.canvas_to_scene_coords(center)
    
    def canvas_cursor_position(self):
        """Gets the current cursor position in canvas coordinates and processes it
        the same way as the context menu does to ensure accurate positioning"""
        # Get current cursor position relative to this widget
        cursor_pos = self.mapFromGlobal(QtGui.QCursor.pos())
        return cursor_pos  # Return raw position to be processed by add_button_at_position
    #------------------------------------------------------------------------------
    def setup_dot_texture(self):
        # Create a higher resolution texture for smoother dots
        texture_size = self.dot_spacing
        # Use a higher resolution for the texture
        scale_factor = 4
        hi_res_size = texture_size * scale_factor
        
        # Create a high resolution temporary image for anti-aliased drawing
        hi_res_texture = QtGui.QImage(hi_res_size, hi_res_size, QtGui.QImage.Format_ARGB32)
        hi_res_texture.fill(QtCore.Qt.transparent)
        
        # Set up painter for high resolution drawing
        painter = QtGui.QPainter(hi_res_texture)
        painter.setRenderHint(QtGui.QPainter.Antialiasing, True)
        painter.setRenderHint(QtGui.QPainter.SmoothPixmapTransform, True)
        
        # Calculate scaled dot size
        scaled_dot_size = self.dot_size * scale_factor
        
        # Create gradient for smoother appearance
        gradient = QtGui.QRadialGradient(
            hi_res_size // 2,
            hi_res_size // 2,
            scaled_dot_size // 2
        )
        
        # Define gradient stops for smoother edges
        dot_color = self.dot_color
        gradient.setColorAt(0.0, dot_color)
        gradient.setColorAt(0.7, dot_color)  # Maintain solid color for most of the dot
        gradient.setColorAt(1.0, QtGui.QColor(dot_color.red(), dot_color.green(), dot_color.blue(), 0))
        
        # Draw the dot with gradient
        painter.setPen(QtCore.Qt.NoPen)
        painter.setBrush(gradient)
        painter.drawEllipse(
            (hi_res_size - scaled_dot_size) // 2,
            (hi_res_size - scaled_dot_size) // 2,
            scaled_dot_size,
            scaled_dot_size
        )
        painter.end()
        
        # Scale down to final size with smooth transform
        final_texture = hi_res_texture.scaled(
            texture_size,
            texture_size,
            QtCore.Qt.KeepAspectRatio,
            QtCore.Qt.SmoothTransformation
        )
        
        # Create brush from the final texture
        self.dot_texture = QtGui.QBrush(QtGui.QPixmap.fromImage(final_texture))
    
    def set_show_axes(self, show):
        """Set whether to show the axes lines"""
        self.show_axes = show
        self.update()
    
    def set_show_dots(self, show):
        """Set whether to show the background dots"""
        self.show_dots = show
        self.update()
    
    def toggle_dots(self, show):
        """Toggle the visibility of background dots"""
        self.show_dots = show
        self.update()
    #------------------------------------------------------------------------------
    def set_show_grid(self, show):
        """Set whether to show the background grid"""
        self.show_grid = show
        self.update()

    def set_grid_size(self, size):
        """Set the grid size"""
        self.grid_size = max(1, size)  # Ensure minimum size of 1
        self.update()

    def draw_grid(self, painter, visible_rect):
        """Draw grid lines on the canvas"""
        if not self.show_grid:
            return
        
        # Use the dynamic grid color that changes with background
        pen = QtGui.QPen(self.grid_color)
        pen.setWidthF(0.5 / self.zoom_factor)  # Scale with zoom
        painter.setPen(pen)
        
        # Calculate grid spacing in scene coordinates
        grid_spacing = self.grid_size
        
        # Convert visible area to scene coordinates for efficient drawing
        top_left = self.canvas_to_scene_coords(QtCore.QPointF(visible_rect.left(), visible_rect.top()))
        bottom_right = self.canvas_to_scene_coords(QtCore.QPointF(visible_rect.right(), visible_rect.bottom()))
        
        # Calculate grid bounds
        left = int(top_left.x() / grid_spacing) * grid_spacing
        right = int(bottom_right.x() / grid_spacing + 1) * grid_spacing
        top = int(top_left.y() / grid_spacing) * grid_spacing
        bottom = int(bottom_right.y() / grid_spacing + 1) * grid_spacing
        
        # Draw vertical lines
        x = left
        while x <= right:
            painter.drawLine(QtCore.QLineF(x, top_left.y(), x, bottom_right.y()))
            x += grid_spacing
        
        # Draw horizontal lines
        y = top
        while y <= bottom:
            painter.drawLine(QtCore.QLineF(top_left.x(), y, bottom_right.x(), y))
            y += grid_spacing
    #------------------------------------------------------------------------------
    def set_background_value(self, value):
        """Set the background color value where 0 is black and 100 is white"""
        # Convert percentage to RGB value (0-255)
        bg_value = int((value / 100.0) * 255)
        self.background_color = QtGui.QColor(bg_value, bg_value, bg_value)
        
        # Set dot color to be 10% darker than background
        dot_value = max(0, int(bg_value * 0.8))  # Ensure value doesn't go below 0
        self.dot_color = QtGui.QColor(dot_value, dot_value, dot_value)

        # Set grid color to be 10% darker than background
        grid_value = max(0, int(bg_value * 0.8))  # Ensure value doesn't go below 0
        self.grid_color = QtGui.QColor(grid_value, grid_value, grid_value)
        
        # Update dot texture with new color
        self.setup_dot_texture()
        self.update()

    def set_background_image(self, image_path):
        """Set the background image from a file path.

        Handles bpicker:// paths by resolving through PickerDataManager.
        """
        if image_path is None:
            self.background_image = None
        else:
            # Resolve bpicker:// or relative paths
            resolved = DM.PickerDataManager.resolve_image_path(image_path)
            load_path = resolved if resolved else image_path

            self.background_image = QtGui.QImage(load_path)
            if self.background_image.isNull():
                self.background_image = None
            else:
                # Store the ORIGINAL path (may be bpicker://) for data persistence
                self.background_image_path = image_path
                self._update_tab_data_with_background(image_path)
                self.focus_canvas()
        self.update()
        
    def _update_tab_data_with_background(self, image_path):
        """Update the tab data with the background image path"""
        main_window = self.window()
        if isinstance(main_window, UI.AnimPickerWindow):
            current_tab = main_window.tab_system.current_tab
            if current_tab:
                # Update the tab system data structure
                main_window.tab_system.tabs[current_tab]['image_path'] = image_path
                
                # Get current opacity and scale values
                current_opacity = main_window.tab_system.tabs[current_tab].get('image_opacity', 1.0)
                current_scale = self.image_scale
                
                # Update the data manager
                DM.PickerDataManager.update_image_data(
                    current_tab, 
                    image_path, 
                    current_opacity,
                    current_scale
                )
                
                # Enable the remove image button if it exists
                if hasattr(main_window, 'remove_image'):
                    main_window.remove_image.setEnabled(True)
    
    def set_background_from_image(self, image):
        """Set the background image from a QImage object"""
        if image and not image.isNull():
            self.background_image = image
            self.focus_canvas()
            self.update()
            return True
        return False
        
    def dragEnterEvent(self, event):
        """Handle drag enter events for image and SVG files"""
        if event.mimeData().hasUrls():
            # Check if any of the URLs are image or SVG files
            for url in event.mimeData().urls():
                file_path = url.toLocalFile()
                if self._is_valid_image_file(file_path) or self._is_valid_svg_file(file_path):
                    event.acceptProposedAction()
                    return
        event.ignore()
    
    def dragMoveEvent(self, event):
        """Handle drag move events"""
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
        else:
            event.ignore()
    
    def dropEvent(self, event):
        """Handle drop events for image and SVG files"""
        if event.mimeData().hasUrls():
            for url in event.mimeData().urls():
                file_path = url.toLocalFile()
                if self._is_valid_svg_file(file_path):
                    # Handle SVG file - show dialog first
                    drop_position = QtCore.QPointF(event.pos())
                    
                    # Show import options dialog
                    import_options = self._show_svg_import_dialog()
                    
                    if import_options['import']:
                        if import_options['separate']:
                            # Create separate buttons (existing functionality)
                            self._create_buttons_from_svg(file_path, drop_position)
                        else:
                            # Create combined button (new functionality)
                            self._create_combined_button_from_svg(file_path, drop_position)
                    
                    event.acceptProposedAction()
                    return
                
                elif self._is_valid_image_file(file_path):
                    # Handle image file - set as background
                    main_window = self.window()
                    if isinstance(main_window, UI.AnimPickerWindow):
                        self.set_background_image(file_path)
                        event.acceptProposedAction()
                        return
        event.ignore()
    
    def _is_valid_svg_file(self, file_path):
        """Check if the file is a valid SVG file"""
        if not os.path.isfile(file_path):
            return False
            
        # Get the file extension
        _, ext = os.path.splitext(file_path)
        return ext.lower() == '.svg'

    def _is_valid_image_file(self, file_path):
        """Check if the file is a valid image file"""
        if not os.path.isfile(file_path):
            return False
            
        # Get the file extension
        _, ext = os.path.splitext(file_path)
        if not ext:
            return False
            
        # Check if the extension is a supported image format
        valid_extensions = ['.png', '.jpg', '.jpeg', '.bmp', '.gif']
        return ext.lower() in valid_extensions

    def set_image_opacity(self, opacity):
        self.image_opacity = max(0.0, min(1.0, opacity))
        self.update()
    
    def set_image_scale(self, scale):
        self.image_scale = scale #max(0.1, scale)
        self.update()

    def focus_canvas(self):
        selected_buttons = self.get_selected_buttons()

        if selected_buttons:
            # Focus on the selected buttons
            button_rect = self.get_buttons_bounding_rect(selected_buttons)
            self.fit_rect_in_view(button_rect)

        elif self.background_image and not self.background_image.isNull():
            # Focus on the full image
            image_rect = QtCore.QRectF(
                -self.background_image.width() / 2,
                -self.background_image.height() / 2,
                self.background_image.width(),
                self.background_image.height()
            )
            self.fit_rect_in_view(image_rect)

        elif self.buttons:
            # If no buttons are selected, focus on all buttons
            all_buttons_rect = self.get_buttons_bounding_rect()
            self.fit_rect_in_view(all_buttons_rect)

        else:
            # If no buttons and no image, reset to default view
            self.zoom_factor = 1.0
            self.pan_offset = QtCore.QPointF(0, 0)

        self.update()
        self.update_button_positions()

    def fit_rect_in_view(self, rect):
        view_rect = self.rect()

        # Check for zero width or height
        if rect.width() == 0 or rect.height() == 0:
            self.zoom_factor = 1.0
            self.pan_offset = QtCore.QPointF(0, 0)
            return

        # Calculate the zoom factor to fit the rect within the view with 10% padding
        padding = 0.9
        scale_x = (view_rect.width() / rect.width()) * padding
        scale_y = (view_rect.height() / rect.height()) * padding
        self.zoom_factor = min(scale_x, scale_y)

        # Limit the zoom factor to prevent extreme zoom levels
        self.zoom_factor = max(0.1, min(self.zoom_factor, 10))

        # Calculate the pan offset to center the rect in the view
        center_scene = rect.center()
        self.pan_offset = -center_scene * self.zoom_factor

    def get_buttons_bounding_rect(self, buttons=None):
        if buttons is None:
            buttons = self.buttons

        if not buttons:
            return QtCore.QRectF(0, 0, 1, 1)

        min_x = min(button.scene_position.x() - button.width / 2 for button in buttons)
        max_x = max(button.scene_position.x() + button.width / 2 for button in buttons)
        min_y = min(button.scene_position.y() - button.height / 2 for button in buttons)
        max_y = max(button.scene_position.y() + button.height / 2 for button in buttons)

        width = max(max_x - min_x, 1)
        height = max(max_y - min_y, 1)

        return QtCore.QRectF(min_x, min_y, width, height)
    #------------------------------------------------------------------------------
    def _create_buttons_from_svg(self, svg_file_path, drop_position):
        """Create picker buttons from all paths in an SVG file with preserved layout"""
        import xml.etree.ElementTree as ET
        
        try:
            # Parse the SVG file
            tree = ET.parse(svg_file_path)
            root = tree.getroot()
            
            # Find all path elements
            path_elements = []
            
            # Try with namespace first
            path_elements = root.findall('.//{http://www.w3.org/2000/svg}path')
            if not path_elements:
                # Try without namespace
                path_elements = root.findall('.//path')
            
            if not path_elements:
                # Show error dialog
                dialog = CD.CustomDialog(self, title="No Paths Found", size=(250, 100), info_box=True)
                message_label = QtWidgets.QLabel("The SVG file does not contain any path elements.")
                message_label.setWordWrap(True)
                dialog.add_widget(message_label)
                dialog.add_button_box()
                dialog.exec_()
                return
            
            # Store SVG path for ID generation
            self._current_svg_path = svg_file_path
            
            # STEP 1: Get SVG viewBox/dimensions for coordinate system reference
            svg_bounds = self._get_svg_bounds(root)
            svg_width = svg_bounds['width']
            svg_height = svg_bounds['height']
            svg_x_offset = svg_bounds.get('x', 0)
            svg_y_offset = svg_bounds.get('y', 0)
            
            #print(f"SVG bounds: {svg_width}x{svg_height}, offset: ({svg_x_offset}, {svg_y_offset})")
            
            # STEP 2: Calculate all path bounds in SVG coordinate space
            path_data_list = []
            all_path_bounds = []
            
            for i, path_element in enumerate(path_elements):
                if 'd' not in path_element.attrib:
                    continue
                    
                path_data = path_element.attrib['d']
                
                # Get the bounding box of this path in original SVG coordinates
                path_bounds = self._get_path_bounds_in_svg_coords(path_data, path_element)
                
                if path_bounds and not path_bounds.isEmpty():
                    path_info = {
                        'index': i,
                        'element': path_element,
                        'path_data': path_data,
                        'bounds': path_bounds,
                        'center': path_bounds.center()
                    }
                    path_data_list.append(path_info)
                    all_path_bounds.append(path_bounds)
            
            if not path_data_list:
                print("No valid paths found")
                return
            
            # STEP 3: Calculate the overall layout bounds in SVG coordinates
            if all_path_bounds:
                # Find the bounding rectangle that contains all paths
                min_x = min(bounds.left() for bounds in all_path_bounds)
                max_x = max(bounds.right() for bounds in all_path_bounds)
                min_y = min(bounds.top() for bounds in all_path_bounds)
                max_y = max(bounds.bottom() for bounds in all_path_bounds)
                
                layout_bounds = QtCore.QRectF(min_x, min_y, max_x - min_x, max_y - min_y)
                layout_center = layout_bounds.center()
                
                #print(f"Layout bounds: {layout_bounds}, center: {layout_center}")
            else:
                layout_center = QtCore.QPointF(svg_width/2, svg_height/2)
                layout_bounds = QtCore.QRectF(0, 0, svg_width, svg_height)
            
            # STEP 4: Calculate scale factor for reasonable button sizes
            # Target the entire layout to fit within a reasonable screen area
            target_layout_size = 800  # Target size for the entire layout
            current_layout_size = max(layout_bounds.width(), layout_bounds.height())
            layout_scale = target_layout_size / current_layout_size if current_layout_size > 0 else 1.0
            
            # Clamp scale to reasonable range
            layout_scale = max(0.1, min(layout_scale, 10.0))
            
            #print(f"Layout scale: {layout_scale}")
            
            # Convert drop position to scene coordinates
            scene_drop_pos = self.canvas_to_scene_coords(drop_position)
            
            # STEP 5: Create buttons with preserved spatial relationships
            created_buttons = []
            main_window = self.window()
            
            if isinstance(main_window, UI.AnimPickerWindow):
                current_tab = main_window.tab_system.current_tab
                
                # Get existing IDs to avoid conflicts
                existing_ids = set()
                tab_data = DM.PickerDataManager.get_tab_data(current_tab)
                for button in tab_data.get('buttons', []):
                    existing_ids.add(button['id'])
                
                # Also add IDs from current canvas buttons
                for button in self.buttons:
                    existing_ids.add(button.unique_id)
                
                # Add any pending IDs from available_ids cache
                if current_tab in main_window.available_ids:
                    existing_ids.update(main_window.available_ids[current_tab])
                
                # Prepare for batch database update
                new_buttons_data = []
                
                for j, path_info in enumerate(path_data_list):
                    # Generate unique ID
                    unique_id = self._generate_svg_unique_id(current_tab, existing_ids, path_info['index'])
                    existing_ids.add(unique_id)
                    
                    # Create button label
                    button_label = path_info['element'].get('id', '')
                    if not button_label:
                        button_label = f"Shape_{j+1}"
                    
                    # Create the button
                    new_button = PB.PickerButton('', self, unique_id=unique_id, color="#3096bb")
                    
                    # Set up the button with SVG path
                    new_button.shape_type = 'custom_path'
                    new_button.svg_path_data = path_info['path_data']
                    new_button.svg_file_path = svg_file_path
                    
                    # CRITICAL: Calculate position to preserve exact SVG layout
                    path_center = path_info['center']
                    
                    # Calculate offset from layout center in SVG coordinates
                    svg_offset_x = path_center.x() - layout_center.x()
                    svg_offset_y = path_center.y() - layout_center.y()
                    
                    # Scale the offset and apply to drop position
                    scaled_offset_x = svg_offset_x * layout_scale
                    scaled_offset_y = svg_offset_y * layout_scale
                    
                    # Position relative to drop position
                    button_x = scene_drop_pos.x() + scaled_offset_x
                    button_y = scene_drop_pos.y() + scaled_offset_y
                    
                    new_button.scene_position = QtCore.QPointF(button_x, button_y)
                    
                    # STEP 6: Calculate button size based on individual path bounds
                    path_bounds = path_info['bounds']
                    
                    # Scale path dimensions
                    scaled_width = path_bounds.width() * layout_scale
                    scaled_height = path_bounds.height() * layout_scale
                    
                    # Set reasonable button size limits
                    min_size = 25
                    max_size = 200
                    
                    new_button.width = max(min_size, min(max_size, scaled_width))
                    new_button.height = max(min_size, min(max_size, scaled_height))
                    
                    # Apply SVG styling
                    self._apply_svg_styling(new_button, path_info['element'])
                    
                    # Add to canvas
                    self.add_button(new_button)
                    created_buttons.append(new_button)
                    
                    # Prepare database entry
                    button_data_for_db = {
                        "id": unique_id,
                        "selectable": new_button.selectable,
                        "label": new_button.label,
                        "color": new_button.color,
                        "opacity": new_button.opacity,
                        "position": (new_button.scene_position.x(), new_button.scene_position.y()),
                        "rotation": new_button.rotation,
                        "width": new_button.width,
                        "height": new_button.height,
                        "radius": new_button.radius,
                        "assigned_objects": new_button.assigned_objects,
                        "mode": new_button.mode,
                        "script_data": new_button.script_data,
                        "shape_type": new_button.shape_type,
                        "svg_path_data": new_button.svg_path_data,
                        "svg_file_path": new_button.svg_file_path
                    }
                    new_buttons_data.append(button_data_for_db)
                
                # Batch database update
                if new_buttons_data:
                    tab_data = DM.PickerDataManager.get_tab_data(current_tab)
                    tab_data['buttons'].extend(new_buttons_data)
                    #DM.PickerDataManager.update_tab_data(current_tab, tab_data)
                    DM.PickerDataManager.batch_update_buttons(current_tab, DM.PickerDataManager.get_tab_data(current_tab)['buttons'])
                    DM.PickerDataManager.save_data(DM.PickerDataManager.get_data(), force_immediate=True)
                
                # Select all created buttons
                if created_buttons:
                    self.clear_selection()
                    for button in created_buttons:
                        button.is_selected = True
                    
                    # Update UI
                    self.update_button_positions()
                    self.update()
                    self.update_hud_counts()
                    
                    #print(f"Created {len(created_buttons)} buttons with preserved SVG layout")
                    
        except Exception as e:
            # Show error dialog
            dialog = CD.CustomDialog(self, title="Error", size=(250, 100), info_box=True)
            message_label = QtWidgets.QLabel(f"Error processing SVG file: {str(e)}")
            message_label.setWordWrap(True)
            dialog.add_widget(message_label)
            dialog.add_button_box()
            dialog.exec_()

    def _create_combined_button_from_svg(self, svg_file_path, drop_position):
        """Create a single button with combined SVG paths"""
        import xml.etree.ElementTree as ET
        
        try:
            # Parse the SVG file
            tree = ET.parse(svg_file_path)
            root = tree.getroot()
            
            # Find all path elements
            path_elements = root.findall('.//{http://www.w3.org/2000/svg}path')
            if not path_elements:
                path_elements = root.findall('.//path')
            
            if not path_elements:
                self._show_no_paths_dialog()
                return
            
            # Combine all paths into one
            combined_path_data = ""
            for path_element in path_elements:
                if 'd' in path_element.attrib:
                    path_data = path_element.attrib['d']
                    if combined_path_data:
                        combined_path_data += " "
                    combined_path_data += path_data
            
            if not combined_path_data:
                self._show_no_paths_dialog()
                return
            
            # Create single button
            main_window = self.window()
            if isinstance(main_window, UI.AnimPickerWindow):
                current_tab = main_window.tab_system.current_tab
                unique_id = main_window.generate_unique_id(current_tab)
                
                # Convert drop position to scene coordinates
                scene_drop_pos = self.canvas_to_scene_coords(drop_position)
                
                # Create button
                new_button = PB.PickerButton('', self, unique_id=unique_id, color="#3096bb")
                new_button.shape_type = 'custom_path'
                new_button.svg_path_data = combined_path_data
                new_button.svg_file_path = svg_file_path
                new_button.scene_position = scene_drop_pos
                
                # Set reasonable size
                new_button.width = 80
                new_button.height = 80
                
                # Apply styling from first path element if available
                if path_elements:
                    self._apply_svg_styling(new_button, path_elements[0])
                
                # Add to canvas
                self.add_button(new_button)
                
                # Update database
                button_data = {
                    "id": unique_id,
                    "selectable": new_button.selectable,
                    "label": new_button.label,
                    "color": new_button.color,
                    "opacity": new_button.opacity,
                    "position": (new_button.scene_position.x(), new_button.scene_position.y()),
                    "rotation": new_button.rotation,
                    "width": new_button.width,
                    "height": new_button.height,
                    "radius": new_button.radius,
                    "assigned_objects": new_button.assigned_objects,
                    "mode": new_button.mode,
                    "script_data": new_button.script_data,
                    "shape_type": new_button.shape_type,
                    "svg_path_data": new_button.svg_path_data,
                    "svg_file_path": new_button.svg_file_path
                }

                tab_data = DM.PickerDataManager.get_tab_data(current_tab)
                tab_data['buttons'].append(button_data)
                #DM.PickerDataManager.update_tab_data(current_tab, tab_data)
                DM.PickerDataManager.batch_update_buttons(current_tab, DM.PickerDataManager.get_tab_data(current_tab)['buttons'])
                DM.PickerDataManager.save_data(DM.PickerDataManager.get_data(), force_immediate=True)
                
                # Select the new button
                self.clear_selection()
                new_button.is_selected = True
                
                self.update_button_positions()
                self.update()
                self.update_hud_counts()
                
                #print("Created combined SVG button successfully")
                
        except Exception as e:
            self._show_svg_error(str(e))

    def _show_no_paths_dialog(self):
        """Show dialog when no paths are found"""
        dialog = CD.CustomDialog(self, title="No Paths Found", size=(250, 100), info_box=True)
        message_label = QtWidgets.QLabel("The SVG file does not contain any path elements.")
        message_label.setWordWrap(True)
        dialog.add_widget(message_label)
        dialog.add_button_box()
        dialog.exec_()

    def _show_svg_error(self, error_message):
        """Show SVG processing error dialog"""
        dialog = CD.CustomDialog(self, title="SVG Error", size=(300, 120), info_box=True)
        message_label = QtWidgets.QLabel(f"Error processing SVG file: {error_message}")
        message_label.setWordWrap(True)
        dialog.add_widget(message_label)
        dialog.add_button_box()
        dialog.exec_()

    def _get_path_bounds_in_svg_coords(self, path_data, path_element):
        """Get path bounds in original SVG coordinate space"""
        try:
            # Create QPainterPath from the SVG path data (using the fixed parser)\

            #picker button
            button = PB.PickerButton("",None)
            path = button._parse_svg_path(path_data)
            if not path:
                return None
            
            # Get bounds in the original coordinate space
            bounds = path.boundingRect()
            
            # Apply any transforms from the path element
            transform = path_element.get('transform')
            if transform:
                bounds = self._apply_simple_transform(bounds, transform)
            
            return bounds
            
        except Exception as e:
            print(f"Error getting path bounds: {e}")
            return None

    def _get_svg_bounds(self, svg_root):
        """Extract SVG viewBox or calculate bounds from width/height with proper coordinate handling"""
        # Try to get viewBox first (most accurate)
        viewbox = svg_root.get('viewBox')
        if viewbox:
            try:
                parts = viewbox.replace(',', ' ').split()
                if len(parts) >= 4:
                    x, y, width, height = map(float, parts[:4])
                    return {'x': x, 'y': y, 'width': width, 'height': height}
            except:
                pass
        
        # Fallback to width/height attributes
        try:
            width_str = svg_root.get('width', '100')
            height_str = svg_root.get('height', '100')
            
            # Remove units (px, pt, mm, etc.)
            width_str = re.sub(r'[^\d.-]', '', width_str)
            height_str = re.sub(r'[^\d.-]', '', height_str)
            
            width = float(width_str) if width_str else 100
            height = float(height_str) if height_str else 100
            
            return {'x': 0, 'y': 0, 'width': width, 'height': height}
        except:
            # Ultimate fallback
            return {'x': 0, 'y': 0, 'width': 100, 'height': 100}
    
    def _get_accurate_path_bounds(self, path_data, path_element):
        """Get accurate path bounds considering transforms and actual visual placement"""
        try:
            # Create QPainterPath from the SVG path data
            path = QtGui.QPainterPath()
            
            # Enhanced SVG path parser
            import re
            
            # Extract coordinates and commands more reliably
            # This regex captures SVG path commands and their parameters
            tokens = re.findall(r'[MmLlHhVvCcSsQqTtAaZz]|[-+]?(?:\d*\.?\d+)(?:[eE][-+]?\d+)?', path_data)
            
            current_pos = QtCore.QPointF(0, 0)
            start_pos = QtCore.QPointF(0, 0)
            
            i = 0
            while i < len(tokens):
                command = tokens[i]
                
                if command.upper() == 'M':  # Move to
                    try:
                        x, y = float(tokens[i+1]), float(tokens[i+2])
                        if command.islower():  # Relative
                            x += current_pos.x()
                            y += current_pos.y()
                        
                        path.moveTo(x, y)
                        current_pos = QtCore.QPointF(x, y)
                        start_pos = QtCore.QPointF(x, y)
                        i += 3
                    except (IndexError, ValueError):
                        i += 1
                        
                elif command.upper() == 'L':  # Line to
                    try:
                        x, y = float(tokens[i+1]), float(tokens[i+2])
                        if command.islower():  # Relative
                            x += current_pos.x()
                            y += current_pos.y()
                        
                        path.lineTo(x, y)
                        current_pos = QtCore.QPointF(x, y)
                        i += 3
                    except (IndexError, ValueError):
                        i += 1
                        
                elif command.upper() == 'H':  # Horizontal line
                    try:
                        x = float(tokens[i+1])
                        if command.islower():  # Relative
                            x += current_pos.x()
                        
                        path.lineTo(x, current_pos.y())
                        current_pos = QtCore.QPointF(x, current_pos.y())
                        i += 2
                    except (IndexError, ValueError):
                        i += 1
                        
                elif command.upper() == 'V':  # Vertical line
                    try:
                        y = float(tokens[i+1])
                        if command.islower():  # Relative
                            y += current_pos.y()
                        
                        path.lineTo(current_pos.x(), y)
                        current_pos = QtCore.QPointF(current_pos.x(), y)
                        i += 2
                    except (IndexError, ValueError):
                        i += 1
                        
                elif command.upper() == 'C':  # Cubic Bezier curve
                    try:
                        x1, y1 = float(tokens[i+1]), float(tokens[i+2])
                        x2, y2 = float(tokens[i+3]), float(tokens[i+4])
                        x, y = float(tokens[i+5]), float(tokens[i+6])
                        
                        if command.islower():  # Relative
                            x1 += current_pos.x()
                            y1 += current_pos.y()
                            x2 += current_pos.x()
                            y2 += current_pos.y()
                            x += current_pos.x()
                            y += current_pos.y()
                        
                        path.cubicTo(x1, y1, x2, y2, x, y)
                        current_pos = QtCore.QPointF(x, y)
                        i += 7
                    except (IndexError, ValueError):
                        i += 1
                        
                elif command.upper() == 'S':  # Smooth cubic Bezier
                    try:
                        x2, y2 = float(tokens[i+1]), float(tokens[i+2])
                        x, y = float(tokens[i+3]), float(tokens[i+4])
                        
                        if command.islower():  # Relative
                            x2 += current_pos.x()
                            y2 += current_pos.y()
                            x += current_pos.x()
                            y += current_pos.y()
                        
                        # For smooth curves, we approximate with a simple cubic
                        path.cubicTo(current_pos.x(), current_pos.y(), x2, y2, x, y)
                        current_pos = QtCore.QPointF(x, y)
                        i += 5
                    except (IndexError, ValueError):
                        i += 1
                        
                elif command.upper() == 'Q':  # Quadratic Bezier curve
                    try:
                        x1, y1 = float(tokens[i+1]), float(tokens[i+2])
                        x, y = float(tokens[i+3]), float(tokens[i+4])
                        
                        if command.islower():  # Relative
                            x1 += current_pos.x()
                            y1 += current_pos.y()
                            x += current_pos.x()
                            y += current_pos.y()
                        
                        path.quadTo(x1, y1, x, y)
                        current_pos = QtCore.QPointF(x, y)
                        i += 5
                    except (IndexError, ValueError):
                        i += 1
                        
                elif command.upper() == 'A':  # Arc - simplified approximation
                    try:
                        # Arc parameters: rx ry x-axis-rotation large-arc-flag sweep-flag x y
                        rx, ry = float(tokens[i+1]), float(tokens[i+2])
                        x_axis_rotation = float(tokens[i+3])
                        large_arc_flag = int(float(tokens[i+4]))
                        sweep_flag = int(float(tokens[i+5]))
                        x, y = float(tokens[i+6]), float(tokens[i+7])
                        
                        if command.islower():  # Relative
                            x += current_pos.x()
                            y += current_pos.y()
                        
                        # Simplified: just draw a line for now (arcs are complex)
                        path.lineTo(x, y)
                        current_pos = QtCore.QPointF(x, y)
                        i += 8
                    except (IndexError, ValueError):
                        i += 1
                        
                elif command.upper() == 'Z':  # Close path
                    path.lineTo(start_pos.x(), start_pos.y())
                    current_pos = start_pos
                    i += 1
                    
                else:
                    # Skip unknown commands
                    i += 1
            
            bounds = path.boundingRect()
            
            # Check for any transform attribute on the path element
            transform = path_element.get('transform')
            if transform:
                # Apply basic transform parsing (simplified)
                bounds = self._apply_simple_transform(bounds, transform)
            
            return bounds
            
        except Exception as e:
            print(f"Error in accurate path bounds calculation: {e}")
            return None

    def _apply_simple_transform(self, rect, transform_string):
        """Apply basic SVG transforms to bounding rect"""
        try:
            import re
            
            # Handle translate transform
            translate_match = re.search(r'translate\(\s*([-+]?\d*\.?\d+)(?:\s*,\s*([-+]?\d*\.?\d+))?\s*\)', transform_string)
            if translate_match:
                tx = float(translate_match.group(1))
                ty = float(translate_match.group(2)) if translate_match.group(2) else 0
                rect = QtCore.QRectF(rect.x() + tx, rect.y() + ty, rect.width(), rect.height())
            
            # Handle scale transform
            scale_match = re.search(r'scale\(\s*([-+]?\d*\.?\d+)(?:\s*,\s*([-+]?\d*\.?\d+))?\s*\)', transform_string)
            if scale_match:
                sx = float(scale_match.group(1))
                sy = float(scale_match.group(2)) if scale_match.group(2) else sx
                rect = QtCore.QRectF(rect.x() * sx, rect.y() * sy, rect.width() * sx, rect.height() * sy)
            
            return rect
            
        except Exception as e:
            print(f"Error applying transform: {e}")
            return rect
    
    def _generate_svg_unique_id(self, tab_name, existing_ids, path_index):
        """Generate a unique ID specifically for SVG-created buttons"""
        # Try different naming strategies until we find a unique ID
        
        # Strategy 1: Use SVG filename + path index
        import os
        svg_filename = os.path.splitext(os.path.basename(getattr(self, '_current_svg_path', 'svg')))[0]
        
        base_patterns = [
            f"{tab_name}_{svg_filename}_path_{path_index+1:03d}",
            f"{tab_name}_svg_path_{path_index+1:03d}",
            f"{tab_name}_shape_{path_index+1:03d}",
            f"{tab_name}_button_{len(existing_ids)+path_index+1:03d}"
        ]
        
        for base_pattern in base_patterns:
            if base_pattern not in existing_ids:
                return base_pattern
            
            # If base pattern exists, try with incremental suffix
            counter = 1
            while counter < 1000:  # Safety limit
                candidate_id = f"{base_pattern}_{counter:03d}"
                if candidate_id not in existing_ids:
                    return candidate_id
                counter += 1
        
        # Fallback: use timestamp-based ID (should never reach this)
        import time
        timestamp_id = f"{tab_name}_svg_{int(time.time() * 1000)}_{path_index}"
        return timestamp_id

    def _apply_svg_styling(self, button, path_element):
        """Apply SVG styling to the button"""
        # Extract fill color
        fill = path_element.get('fill')
        if fill and fill != 'none' and not fill.startswith('url('):
            try:
                # Convert SVG color to hex
                if fill.startswith('#'):
                    button.color = fill
                elif fill.startswith('rgb'):
                    # Basic RGB parsing - you might want to enhance this
                    import re
                    rgb_match = re.search(r'rgb\((\d+),\s*(\d+),\s*(\d+)\)', fill)
                    if rgb_match:
                        r, g, b = map(int, rgb_match.groups())
                        button.color = f"#{r:02x}{g:02x}{b:02x}"
            except:
                pass  # Keep default color
        
        # Extract opacity
        opacity = path_element.get('opacity')
        if opacity:
            try:
                button.opacity = float(opacity)
            except:
                pass
        
        # You can add more styling extraction here (stroke, etc.)
    
    def _show_svg_import_dialog(self):
        """Show dialog to choose between separate buttons or combined import"""
        dialog = CD.CustomDialog(self, title="SVG Import Options", size=(300, 150))
        
        # Create main layout
        main_layout = QtWidgets.QVBoxLayout()
        
        # Info label
        info_label = QtWidgets.QLabel("How would you like to import the SVG paths?")
        info_label.setWordWrap(True)
        info_label.setStyleSheet("font-weight: bold; margin-bottom: 10px;")
        main_layout.addWidget(info_label)
        
        # Radio buttons for import options
        radio_layout = QtWidgets.QVBoxLayout()
        
        self.separate_radio = CB.CustomRadioButton("Separate buttons", group=True)
        self.separate_radio.setToolTip("Each SVG path is imported as a separate picker button")
        
        self.combined_radio = CB.CustomRadioButton("Combined button", group=True)
        self.combined_radio.setToolTip("All SVG paths are merged into one picker button")
        
        self.separate_radio.group('import_option')
        self.combined_radio.group('import_option')
        
        radio_layout.addWidget(self.separate_radio)
        radio_layout.addWidget(self.combined_radio)
        main_layout.addLayout(radio_layout)
        
        dialog.add_layout(main_layout)
        
        dialog.add_button_box()

        if dialog.exec_() == QtWidgets.QDialog.Accepted:
            if self.separate_radio.isChecked():
                return {'import': True, 'separate': True}
            else:
                return {'import': True, 'separate': False}
    #------------------------------------------------------------------------------
    def show_context_menu(self, position):
        # Don't show context menu if we just finished zooming
        if self.was_zoom_dragging:
            self.was_zoom_dragging = False
            return

        # Hide any active tooltip
        if hasattr(self, '_hide_button_tooltip'):
            self._hide_button_tooltip()

        if not hasattr(self, 'context_menu'):
            self.context_menu = QtWidgets.QMenu()
            self.context_menu.setWindowFlags(self.context_menu.windowFlags() | QtCore.Qt.FramelessWindowHint | QtCore.Qt.NoDropShadowWindowHint)
            self.context_menu.setAttribute(QtCore.Qt.WA_TranslucentBackground)
            self.context_menu.setStyleSheet('''
                QMenu {
                    background-color: rgba(30, 30, 30, .9);
                    color: #ffffff;
                    border: 1px solid #444444;
                    border-radius: 3px;
                    padding: 5px 7px;
                }
                QMenu::item {
                    background-color: transparent;
                    color: #ffffff;
                    padding: 3px 10px 3px 3px; ;
                    margin: 3px 0px  ;
                    border-radius: 3px;
                }
                QMenu::item:selected {
                    background-color: #444444;
                }''')

        menu = self.context_menu
        menu.clear()

        if self.edit_mode:
            add_button_action = menu.addAction(QtGui.QIcon(UT.get_icon('add.png')), "Add Button")
            add_button_action.triggered.connect(lambda: self.add_button_at_position(position))

            # Create multiple buttons paired to each currently selected scene object
            selection_preview = TF.get_current_scene_selection()
            sel_count = len(selection_preview)
            label = f"Create Buttons from Selection ({sel_count})" if sel_count else "Create Buttons from Selection"
            create_from_sel_action = menu.addAction(QtGui.QIcon(UT.get_icon('add.png')), label)
            create_from_sel_action.triggered.connect(lambda: self.start_multi_button_placement(position))
            if sel_count == 0:
                create_from_sel_action.setEnabled(False)
                create_from_sel_action.setToolTip("No scene objects/bones selected")

            # Draw custom shape - creates a new button and opens curve editor
            draw_shape_action = menu.addAction(QtGui.QIcon(UT.get_icon('add.png')), "Draw Custom Shape")
            draw_shape_action.triggered.connect(lambda: self.start_drawing_new_button_shape(position))

            scene_pos = self.get_center_position()  # Use canvas center

            # Add the main curve creation action
            from . import maya_curve_converter as MCC
            create_button_from_maya_curve_action = menu.addAction(QtGui.QIcon(UT.get_icon('add.png')), "Create Button from Curve")
            create_button_from_maya_curve_action.triggered.connect(lambda: MCC.create_buttons_from_maya_curves(self, scene_pos))

            # Add curve import submenu
            curve_import_submenu = menu.addMenu("Curve Import Options")
            curve_import_submenu.setWindowFlags(curve_import_submenu.windowFlags() | QtCore.Qt.FramelessWindowHint | QtCore.Qt.NoDropShadowWindowHint)
            curve_import_submenu.setAttribute(QtCore.Qt.WA_TranslucentBackground)
            curve_import_submenu.setStyleSheet(menu.styleSheet())

            # Create the widget and embed it in the submenu
            from .curve_import_widget import CurveImportOptionsWidget
            curve_widget = CurveImportOptionsWidget(canvas=self)
            curve_widget_action = QtWidgets.QWidgetAction(curve_import_submenu)
            curve_widget_action.setDefaultWidget(curve_widget)
            curve_import_submenu.addAction(curve_widget_action)

            # Get clipboard state to determine if paste actions should be enabled
            has_clipboard = bool(PB.ButtonClipboard.instance().get_all_buttons())

            # Create regular paste action
            paste_buttons_action = menu.addAction(QtGui.QIcon(UT.get_icon('paste.png')), "Paste Button")
            paste_buttons_action.triggered.connect(lambda: self.paste_buttons_at_position(position, mirror=False))
            paste_buttons_action.setEnabled(has_clipboard)

            # Create mirrored paste action
            paste_mirror_action = menu.addAction(QtGui.QIcon(UT.get_icon('paste.png')), "Paste Mirror")
            paste_mirror_action.triggered.connect(lambda: self.paste_buttons_at_position(position, mirror=True))
            paste_mirror_action.setEnabled(has_clipboard)

            menu.addSeparator()
            edit_mode_action = menu.addAction(QtGui.QIcon(UT.get_icon('edit.png')),"Exit Edit Mode")
            main_window = self.window()
            if isinstance(main_window, UI.AnimPickerWindow):
                edit_mode_action.triggered.connect(main_window.toggle_edit_mode)
        else:
            edit_mode_action = menu.addAction(QtGui.QIcon(UT.get_icon('edit.png')),"Edit Picker")
            main_window = self.window()
            if isinstance(main_window, UI.AnimPickerWindow):
                edit_mode_action.triggered.connect(main_window.toggle_edit_mode)

        # Add selection sync options
        menu.addSeparator()
        sync_submenu = menu.addMenu("Selection Sync")
        sync_submenu.setWindowFlags(sync_submenu.windowFlags() | QtCore.Qt.FramelessWindowHint | QtCore.Qt.NoDropShadowWindowHint)
        sync_submenu.setAttribute(QtCore.Qt.WA_TranslucentBackground)

        # Check current sync status
        try:
            manager = SSM.SelectionSyncManager.get_instance()
            sync_enabled = manager._sync_enabled
        except:
            sync_enabled = True  # Default to enabled

        enable_sync_action = sync_submenu.addAction("Enable 2-Way Sync")
        enable_sync_action.setCheckable(True)
        enable_sync_action.setChecked(sync_enabled)
        enable_sync_action.triggered.connect(self.enable_selection_sync)

        disable_sync_action = sync_submenu.addAction("Disable 2-Way Sync")
        disable_sync_action.setCheckable(True)
        disable_sync_action.setChecked(not sync_enabled)
        disable_sync_action.triggered.connect(self.disable_selection_sync)

        sync_submenu.addSeparator()

        test_sync_action = sync_submenu.addAction("Test Sync System")
        test_sync_action.triggered.connect(self._test_selection_sync)

        create_test_scene_action = sync_submenu.addAction("Create Test Scene")
        create_test_scene_action.triggered.connect(self._create_test_scene)

        if menu.actions():
            menu.exec_(self.mapToGlobal(position))

    def add_button_at_position(self, position):
        scene_pos = self.canvas_to_scene_coords(QtCore.QPointF(position))
        
        main_window = self.window()
        if isinstance(main_window, UI.AnimPickerWindow):
            current_tab = main_window.tab_system.current_tab
            unique_id = main_window.generate_unique_id(current_tab)
            
            # Create button with default properties
            new_button = PB.PickerButton("Button", self, unique_id=unique_id)
            new_button.scene_position = scene_pos
            
            # Add button to canvas
            self.add_button(new_button)
            
            # Create button data for database
            button_data = {
                "id": unique_id,
                "label": new_button.label,
                "color": new_button.color,
                "opacity": new_button.opacity,
                "position": (new_button.scene_position.x(), new_button.scene_position.y()),
                "rotation": new_button.rotation,
                "width": new_button.width,
                "height": new_button.height,
                "radius": new_button.radius,
                "assigned_objects": []
            }

            # Update PickerDataManager
            tab_data = DM.PickerDataManager.get_tab_data(current_tab)
            tab_data['buttons'].append(button_data)
            #DM.PickerDataManager.update_tab_data(current_tab, tab_data)
            DM.PickerDataManager.batch_update_buttons(current_tab, DM.PickerDataManager.get_tab_data(current_tab)['buttons'])
            
            self.clear_selection()
            new_button.is_selected = True
            new_button.selected.emit(new_button, True)

            self.update_button_positions()
            self.update()

    # ------------------------------------------------------------------
    # Multi-button "Create from Selection" with drag-to-place layout
    # ------------------------------------------------------------------
    def start_multi_button_placement(self, click_widget_pos):
        """Begin drag-to-place mode for N buttons, one per selected scene object."""
        if not self.edit_mode:
            return
        selection = TF.get_current_scene_selection()
        if not selection:
            return

        origin_scene = self.canvas_to_scene_coords(QtCore.QPointF(click_widget_pos))

        if len(selection) == 1:
            # Single selection: create immediately at the clicked position.
            self._commit_multi_button_placement_internal(selection, [origin_scene])
            return

        self.is_placing_multi = True
        self.placement_origin_scene = origin_scene
        self.placement_cursor_scene = QtCore.QPointF(origin_scene)
        self.pending_placement_data = {
            'selection': selection,
            'default_w': 80,
            'default_h': 30,
            'gap': 4,
            'scale_w': 1.0,
            'scale_h': 1.0,
        }
        self.setMouseTracking(True)
        self.setCursor(QtCore.Qt.SizeAllCursor)
        self.setFocus(QtCore.Qt.OtherFocusReason)
        self.update()

    def _compute_multi_layout_positions(self, modifiers=QtCore.Qt.NoModifier):
        data = self.pending_placement_data
        if not data or self.placement_origin_scene is None:
            return []
        import math
        n = len(data['selection'])
        origin = self.placement_origin_scene
        cursor = self.placement_cursor_scene if self.placement_cursor_scene is not None else origin
        dw = data['default_w'] * data.get('scale_w', 1.0)
        dh = data['default_h'] * data.get('scale_h', 1.0)
        gap = data['gap']

        shift = bool(modifiers & QtCore.Qt.ShiftModifier)
        alt = bool(modifiers & QtCore.Qt.AltModifier)

        dx = cursor.x() - origin.x()
        dy = cursor.y() - origin.y()
        dist = math.hypot(dx, dy)

        # Angle snap to nearest axis within 8° unless Alt is held.
        if not alt and dist > 1e-3:
            angle = math.degrees(math.atan2(dy, dx))
            for snap_deg in (0, 90, 180, -90, -180):
                if abs(angle - snap_deg) <= 8:
                    rad = math.radians(snap_deg)
                    dx = math.cos(rad) * dist
                    dy = math.sin(rad) * dist
                    break

        positions = []
        if shift:
            # Grid wrap: rows of ceil(sqrt(N)), centered on origin.
            cols = max(1, int(math.ceil(math.sqrt(n))))
            rows = int(math.ceil(n / float(cols)))
            col_step = dw + gap
            row_step = dh + gap
            for i in range(n):
                r = i // cols
                c = i % cols
                # Items in the last row may be < cols; center them too.
                row_count = cols if r < rows - 1 else (n - r * cols)
                cx = (c - (row_count - 1) / 2.0) * col_step
                cy = (r - (rows - 1) / 2.0) * row_step
                positions.append(QtCore.QPointF(origin.x() + cx, origin.y() + cy))
            return positions

        # Linear layout: origin = first button, cursor = last button.
        if n == 1:
            return [QtCore.QPointF(origin)]
        spread_vec_len = math.hypot(dx, dy)
        if spread_vec_len < 1e-3:
            ux, uy = 1.0, 0.0
        else:
            ux = dx / spread_vec_len
            uy = dy / spread_vec_len
        # Axis-aware floor: vertical drags use height+gap, horizontal use width+gap.
        axis_step = (dw + gap) if abs(ux) >= abs(uy) else (dh + gap)
        min_spread = (n - 1) * axis_step
        spread = max(spread_vec_len, min_spread)
        step = spread / (n - 1)
        for i in range(n):
            offset = i * step
            positions.append(QtCore.QPointF(origin.x() + ux * offset, origin.y() + uy * offset))
        return positions

    def _paint_placement_ghosts(self, painter):
        """Draw ghost rects + axis guide for the in-progress multi placement.

        Called from paintEvent inside the scene-transformed painter block.
        """
        data = self.pending_placement_data
        if not (self.is_placing_multi and data):
            return
        positions = self._compute_multi_layout_positions(QtWidgets.QApplication.keyboardModifiers())
        if not positions:
            return
        dw = data['default_w'] * data.get('scale_w', 1.0)
        dh = data['default_h'] * data.get('scale_h', 1.0)
        selection = data['selection']
        n = len(positions)

        painter.save()
        # Axis guide (dashed line from origin to cursor)
        pen = QtGui.QPen(QtGui.QColor(200, 200, 200, 160))
        pen.setWidthF(1.0 / max(self.zoom_factor, 0.001))
        pen.setStyle(QtCore.Qt.DashLine)
        painter.setPen(pen)
        if self.placement_cursor_scene is not None:
            painter.drawLine(self.placement_origin_scene, self.placement_cursor_scene)

        # Ghost rects
        throttled = n > 100
        draw_indices = range(n) if not throttled else {0, n // 2, n - 1}
        fill = QtGui.QColor(90, 140, 200, 110)
        border = QtGui.QColor(240, 240, 240, 200)
        text_pen = QtGui.QPen(QtGui.QColor(240, 240, 240, 220))
        for i, pos in enumerate(positions):
            if i not in draw_indices:
                continue
            rect = QtCore.QRectF(pos.x() - dw / 2.0, pos.y() - dh / 2.0, dw, dh)
            painter.setBrush(fill)
            bpen = QtGui.QPen(border)
            bpen.setWidthF(1.5 / max(self.zoom_factor, 0.001))
            painter.setPen(bpen)
            painter.drawRoundedRect(rect, 4, 4)
            painter.setPen(text_pen)
            label = selection[i].get('label', '')
            painter.drawText(rect, QtCore.Qt.AlignCenter, label)

        # HUD: live readout of size + count near the cursor. Scaled by zoom so
        # the text size stays consistent across zoom levels.
        if self.placement_cursor_scene is not None:
            zoom = max(self.zoom_factor, 0.001)
            hud_text = f"{int(round(dw))} × {int(round(dh))}  ·  {n} buttons"
            font = painter.font()
            font.setPointSizeF(max(7.0, 9.0 / zoom))
            painter.setFont(font)
            painter.setPen(text_pen)
            offset = QtCore.QPointF(14.0 / zoom, -8.0 / zoom)
            painter.drawText(self.placement_cursor_scene + offset, hud_text)
        painter.restore()

    def _commit_multi_button_placement(self, modifiers=QtCore.Qt.NoModifier):
        if not self.is_placing_multi or not self.pending_placement_data:
            return
        data = self.pending_placement_data
        positions = self._compute_multi_layout_positions(modifiers)
        scaled_w = max(5, int(round(data['default_w'] * data.get('scale_w', 1.0))))
        scaled_h = max(5, int(round(data['default_h'] * data.get('scale_h', 1.0))))
        self._cancel_multi_button_placement(repaint=False)
        self._commit_multi_button_placement_internal(
            data['selection'], positions, width=scaled_w, height=scaled_h
        )

    def _commit_multi_button_placement_internal(self, selection, positions, width=None, height=None):
        """Shared commit path for both single-select fast path and drag-placed batch."""
        main_window = self.window()
        if not isinstance(main_window, UI.AnimPickerWindow):
            return
        current_tab = main_window.tab_system.current_tab

        new_buttons_data = []
        new_buttons_widgets = []

        for i, item in enumerate(selection):
            unique_id = main_window.generate_unique_id(current_tab)
            if current_tab not in main_window.available_ids:
                main_window.available_ids[current_tab] = set()
            main_window.available_ids[current_tab].add(unique_id)

            label = item.get('label', 'Button') or 'Button'
            new_button = PB.PickerButton(label, self, unique_id=unique_id)
            if width is not None:
                new_button.width = width
            if height is not None:
                new_button.height = height
            new_button.scene_position = QtCore.QPointF(positions[i])
            new_button.mode = 'select'
            assigned = item.get('assigned_object')
            new_button.assigned_objects = [assigned] if assigned else []

            if hasattr(self, 'add_button_without_db_update'):
                self.add_button_without_db_update(new_button)
            else:
                old_method = main_window.update_button_data
                main_window.update_button_data = lambda *a, **kw: None
                self.add_button(new_button)
                main_window.update_button_data = old_method

            new_buttons_widgets.append(new_button)
            new_buttons_data.append({
                "id": unique_id,
                "selectable": new_button.selectable,
                "label": new_button.label,
                "color": new_button.color,
                "opacity": new_button.opacity,
                "position": (new_button.scene_position.x(), new_button.scene_position.y()),
                "rotation": new_button.rotation,
                "width": new_button.width,
                "height": new_button.height,
                "radius": new_button.radius,
                "assigned_objects": list(new_button.assigned_objects),
                "mode": new_button.mode,
                "script_data": {},
                "shape_type": new_button.shape_type,
                "svg_path_data": getattr(new_button, 'svg_path_data', '') or '',
                "svg_file_path": getattr(new_button, 'svg_file_path', '') or '',
            })

        if not new_buttons_data:
            return

        # Select new buttons
        self.clear_selection()
        for b in new_buttons_widgets:
            b.is_selected = True
            b._cached_envelope = None
            b._cached_envelope_key = None
            b._cached_scene_path = None
            b._cached_scene_path_key = None

        # Single batched DB update (one undo entry)
        tab_data = DM.PickerDataManager.get_tab_data(current_tab)
        tab_data['buttons'].extend(new_buttons_data)
        DM.PickerDataManager.batch_update_buttons(current_tab, tab_data['buttons'])

        self.update_button_positions()
        self._emit_selection_changed()
        if hasattr(self, 'transform_guides'):
            self.transform_guides.update_selection()

    def _cancel_multi_button_placement(self, repaint=True):
        self.is_placing_multi = False
        self.placement_origin_scene = None
        self.placement_cursor_scene = None
        self.pending_placement_data = None
        self.unsetCursor()
        if repaint:
            self.update()

    def keyPressEvent(self, event):
        # Duplicate-mirror tool: Enter commits, Escape cancels.
        if hasattr(self, 'duplicate_mirror_tool') and self.duplicate_mirror_tool.active:
            if self.duplicate_mirror_tool.handle_key_press(event):
                event.accept()
                return
        if self.is_placing_multi and event.key() == QtCore.Qt.Key_Escape:
            self._cancel_multi_button_placement()
            event.accept()
            return
        if self.is_placing_multi and event.key() in (QtCore.Qt.Key_Shift, QtCore.Qt.Key_Alt):
            self.update()
        super().keyPressEvent(event)

    def keyReleaseEvent(self, event):
        if self.is_placing_multi and event.key() in (QtCore.Qt.Key_Shift, QtCore.Qt.Key_Alt):
            self.update()
        super().keyReleaseEvent(event)

    def focusOutEvent(self, event):
        if self.is_placing_multi:
            self._cancel_multi_button_placement()
        super().focusOutEvent(event)

    def paste_buttons_at_position(self, position, mirror=False, is_scene_coords=False):
        """REFACTORED: Simplified paste function that uses horizontal_mirror_button_positions for mirroring"""
        if is_scene_coords:
            scene_pos = QtCore.QPointF(position)
        else:
            scene_pos = self.canvas_to_scene_coords(QtCore.QPointF(position))
        copied_buttons = PB.ButtonClipboard.instance().get_all_buttons()
        
        if not copied_buttons:
            return
            
        main_window = self.window()
        if isinstance(main_window, UI.AnimPickerWindow):
            current_tab = main_window.tab_system.current_tab
            current_namespace = main_window.namespace_dropdown.currentText()
            
            # Get initial button count for verification
            tab_data_before = DM.PickerDataManager.get_tab_data(current_tab)
            initial_count = len(tab_data_before['buttons'])
            
            # Collect all new button data BEFORE any database operations
            new_buttons_data = []
            new_buttons_widgets = []
            
            # STEP 1: Create all button widgets WITHOUT counterpart mirroring (handled separately)
            for i, button_data in enumerate(copied_buttons):
                unique_id = main_window.generate_unique_id(current_tab)
                # Track newly generated IDs to prevent duplicates
                if current_tab not in main_window.available_ids:
                    main_window.available_ids[current_tab] = set()
                main_window.available_ids[current_tab].add(unique_id)
                
                # Create the button widget
                new_button = PB.PickerButton(button_data['label'], self, unique_id=unique_id)
                
                # Apply all copied attributes
                new_button.color = button_data['color']
                new_button.selectable = button_data['selectable']
                new_button.opacity = button_data['opacity']
                new_button.width = button_data['width']
                new_button.height = button_data['height']
                new_button.radius = button_data['radius'].copy() if hasattr(button_data['radius'], 'copy') else list(button_data['radius'])
                new_button.mode = button_data.get('mode', 'select')
                new_button.script_data = button_data.get('script_data', {}).copy() if button_data.get('script_data') else {}
                new_button.shape_type = button_data.get('shape_type', 'rect')
                new_button.svg_path_data = button_data.get('svg_path_data', '')
                new_button.svg_file_path = button_data.get('svg_file_path', '')
                new_button.rotation = button_data.get('rotation', 0)

                # Always use original assigned objects - counterpart mirroring handled in horizontal_mirror_button_positions
                original_assigned_objects = button_data['assigned_objects'].copy() if button_data['assigned_objects'] else []
                new_button.assigned_objects = original_assigned_objects
                
                # Handle pose-specific data
                if new_button.mode == 'pose':
                    if 'thumbnail_path' in button_data and button_data['thumbnail_path']:
                        new_button.thumbnail_path = button_data['thumbnail_path']
                        if os.path.exists(new_button.thumbnail_path):
                            new_button.thumbnail_pixmap = QtGui.QPixmap(new_button.thumbnail_path)

                    if 'pose_data' in button_data and button_data['pose_data']:
                        new_button.pose_data = button_data['pose_data'].copy()
                    if 'animation_data' in button_data and button_data['animation_data']:
                        new_button.animation_data = button_data['animation_data'].copy()

                # Handle controller-specific data
                if new_button.mode == 'controller' and 'controller_data' in button_data and button_data['controller_data']:
                    import copy as _copy
                    new_button.controller_data = _copy.deepcopy(button_data['controller_data'])
                    if new_button.controller_data.get('data_path'):
                        val = new_button._read_controller_value()
                        if val is not None:
                            new_button._controller_value = val
                        else:
                            new_button._controller_value = new_button.controller_data.get('default_value', 0.0)
                        new_button._start_controller_sync()

                # Position WITHOUT position mirroring (will be handled by horizontal_mirror_button_positions)
                relative_position = button_data['relative_position']
                new_button.scene_position = scene_pos + relative_position
                
                # Add to canvas WITHOUT triggering database update
                if hasattr(self, 'add_button_without_db_update'):
                    self.add_button_without_db_update(new_button)
                else:
                    # Fallback: temporarily disable database updates
                    old_method = main_window.update_button_data
                    main_window.update_button_data = lambda *args, **kwargs: None
                    self.add_button(new_button)
                    main_window.update_button_data = old_method
                
                new_buttons_widgets.append(new_button)
                
                # Prepare complete button data for database
                button_data_for_db = {
                    "id": unique_id,
                    "selectable": new_button.selectable,
                    "label": new_button.label,
                    "color": new_button.color,
                    "opacity": new_button.opacity,
                    "position": (new_button.scene_position.x(), new_button.scene_position.y()),
                    "rotation": new_button.rotation,
                    "width": new_button.width,
                    "height": new_button.height,
                    "radius": new_button.radius,
                    "assigned_objects": new_button.assigned_objects,
                    "mode": new_button.mode,
                    "script_data": new_button.script_data,
                    "shape_type": new_button.shape_type,
                    "svg_path_data": new_button.svg_path_data,
                    "svg_file_path": new_button.svg_file_path
                }
                
                # Add pose-specific data to database if needed
                if new_button.mode == 'pose':
                    if hasattr(new_button, 'thumbnail_path') and new_button.thumbnail_path:
                        button_data_for_db["thumbnail_path"] = new_button.thumbnail_path
                    if hasattr(new_button, 'pose_data') and new_button.pose_data:
                        button_data_for_db["pose_data"] = new_button.pose_data
                    if hasattr(new_button, 'animation_data') and new_button.animation_data:
                        button_data_for_db["animation_data"] = new_button.animation_data

                # Add controller-specific data to database
                if new_button.mode == 'controller' and new_button.controller_data:
                    button_data_for_db["controller_data"] = new_button.controller_data

                new_buttons_data.append(button_data_for_db)
            
            # STEP 2: Select all newly pasted buttons
            if new_buttons_widgets:
                self.clear_selection()
                for button in new_buttons_widgets:
                    button.is_selected = True
                    # Invalidate per-button transform/paint caches so the very first
                    # bounding-rect calculation can't read a value cached from a
                    # previously-deleted button instance.
                    button._cached_envelope = None
                    button._cached_envelope_key = None
                    button._cached_scene_path = None
                    button._cached_scene_path_key = None
                # Notify transform guides / edit widgets that selection has changed.
                # Without this, TransformGuides keeps stale selected_buttons from the
                # cleared selection and the first transform mousePress captures
                # original_states for the wrong buttons -> rotated duplicates jump.
                self.button_selection_changed.emit()

            # STEP 3: Apply position/SVG/counterpart mirroring if requested using existing function
            if mirror and new_buttons_widgets:
                #print("Applying position, SVG, and counterpart mirroring using horizontal_mirror_button_positions...")
                # Use existing horizontal mirror function with counterpart mirroring enabled
                self.horizontal_mirror_button_positions(apply_counterparts=True)
                # Positions changed — re-emit so guides recompute the bounding rect
                self.button_selection_changed.emit()
                
                # Update button data for database after mirroring
                for i, button in enumerate(new_buttons_widgets):
                    new_buttons_data[i]["position"] = (button.scene_position.x(), button.scene_position.y())
                    new_buttons_data[i]["svg_path_data"] = button.svg_path_data
                    new_buttons_data[i]["assigned_objects"] = button.assigned_objects
            
            # STEP 4: Perform SINGLE batch database update
            if new_buttons_data:
                # Get fresh tab data
                tab_data = DM.PickerDataManager.get_tab_data(current_tab)
                before_count = len(tab_data['buttons'])
                
                # Add ALL new buttons to tab data in one operation
                tab_data['buttons'].extend(new_buttons_data)
                after_count = len(tab_data['buttons'])
                
                # Update database once with all new data
                #DM.PickerDataManager.update_tab_data(current_tab, tab_data)
                DM.PickerDataManager.batch_update_buttons(current_tab, DM.PickerDataManager.get_tab_data(current_tab)['buttons'])

                # batch_update_buttons debounces via the batch timer;
                # flush synchronously here so the pasted buttons land
                # in the scene attr before any verification read below.
                DM.PickerDataManager.flush_pending_saves()
                
                # Verify the operation succeeded
                verification_data = DM.PickerDataManager.get_tab_data(current_tab)
                final_count = len(verification_data['buttons'])
                
                # Additional verification
                if final_count != initial_count + len(new_buttons_data):
                    print(f"WARNING: Expected {initial_count + len(new_buttons_data)} buttons, but database has {final_count}")
            
            # STEP 5: Update UI
            self.update_button_positions()
            self.update()
            self.update_hud_counts()  # Update HUD counter
            
            action_type = "Mirror pasted" if mirror else "Pasted"
            #print(f"{action_type} operation completed: {len(new_buttons_widgets)} buttons created and saved")

    def horizontal_mirror_button_positions(self, apply_counterparts=False):
        """Mirror button positions horizontally with optional counterpart object assignment"""
        selected_buttons = self.get_selected_buttons()
        if not selected_buttons:
            return

        main_window = self.window()
        if not isinstance(main_window, UI.AnimPickerWindow):
            return

        # Mirror axis = center X of the selection bounds
        min_x = min(button.scene_position.x() for button in selected_buttons)
        max_x = max(button.scene_position.x() for button in selected_buttons)
        axis_x = (min_x + max_x) / 2

        self._apply_mirror_to_buttons(
            selected_buttons,
            axis_x,
            apply_counterparts=apply_counterparts,
            mirror_rotation=False,  # legacy behavior: don't flip rotation
        )

        self.update_button_positions()

    def _apply_mirror_to_buttons(self, buttons, axis_x, apply_counterparts=False, mirror_rotation=False):
        """Mirror the given buttons horizontally across an explicit scene-space axis_x.

        Mutates each button in place: position X reflected across axis_x, SVG
        custom-path mirrored, and (optionally) rotation negated and assigned
        objects swapped to L/R counterparts. Emits `button.changed` per button
        so the main window picks up the mutation; the caller is responsible
        for any post-loop refresh (e.g. update_button_positions, DB writes).
        """
        if not buttons:
            return

        main_window = self.window()
        if not isinstance(main_window, UI.AnimPickerWindow):
            return

        current_namespace = main_window.namespace_dropdown.currentText()

        if apply_counterparts:
            naming_conventions = self._get_naming_conventions("", "")

        for button in buttons:
            # Mirror position around axis_x
            button.scene_position.setX(2 * axis_x - button.scene_position.x())

            # Mirror rotation (opt-in — the legacy horizontal_mirror skips this)
            if mirror_rotation and button.rotation != 0:
                button.rotation = (-button.rotation) % 360
                button._invalidate_mask_cache()
                if hasattr(button, 'text_pixmap'):
                    button.text_pixmap = None
                if hasattr(button, 'pose_pixmap'):
                    button.pose_pixmap = None

            # Mirror SVG shapes if they have custom paths
            if button.shape_type == 'custom_path' and button.svg_path_data:
                button.svg_path_data = button.mirror_svg_path_horizontal(button.svg_path_data, button.width)
                button._invalidate_mask_cache()

            # Apply counterpart mirroring to assigned objects if requested
            if apply_counterparts and button.assigned_objects:
                mirrored_objects = []
                mirror_preferences = self._load_mirror_preferences_for_objects(button.assigned_objects, current_namespace)

                for obj_data in button.assigned_objects:
                    try:
                        resolved_obj = self._resolve_object_name_from_data(obj_data, current_namespace)

                        if resolved_obj:
                            namespace, short_name = self._extract_namespace_and_name(resolved_obj)
                            mirrored_name, is_center_object = self._find_mirrored_name(
                                short_name, naming_conventions, mirror_preferences, namespace
                            )

                            if cmds.objExists(mirrored_name):
                                try:
                                    mirrored_uuid = cmds.ls(mirrored_name, uuid=True)[0]
                                    mirrored_long_name = cmds.ls(mirrored_name, long=True)[0]
                                    mirrored_obj_data = {
                                        'uuid': mirrored_uuid,
                                        'long_name': mirrored_long_name
                                    }
                                    mirrored_objects.append(mirrored_obj_data)
                                except Exception as e:
                                    print(f"Error creating mirrored object data for {mirrored_name}: {e}")
                                    mirrored_objects.append(obj_data.copy())
                            else:
                                mirrored_objects.append(obj_data.copy())
                        else:
                            mirrored_objects.append(obj_data.copy())

                    except Exception as e:
                        print(f"Error mirroring assigned object {obj_data}: {e}")
                        mirrored_objects.append(obj_data.copy())

                button.assigned_objects = mirrored_objects

            button.update()

            # Emit change signal to trigger database update
            button.changed.emit(button)

    def start_duplicate_mirror_tool(self):
        """Activate the interactive Duplicate Mirror tool on the current selection.

        The mirror axis seeds at the cursor's current scene-space X (handled by
        the tool itself in its activate() method); this entry point just gathers
        the source set and hands off control.
        """
        if not self.edit_mode:
            return
        source = self.get_selected_buttons()
        if not source:
            return
        self.duplicate_mirror_tool.activate(source, 0.0)

    def vertical_mirror_button_positions(self):
        selected_buttons = self.get_selected_buttons()
        if selected_buttons:
            # Get the center of the selected buttons
            min_y = min(button.scene_position.y() for button in selected_buttons)
            max_y = max(button.scene_position.y() for button in selected_buttons)
            center_y = (min_y + max_y) / 2
            
            # Mirror positions around the center
            for button in selected_buttons:
                button.scene_position.setY(center_y - (button.scene_position.y() - center_y))
                if button.shape_type == 'custom_path' and button.svg_path_data:
                    button.svg_path_data = button.mirror_svg_path_vertical(button.svg_path_data, button.height)
                    button._invalidate_mask_cache()
                button.update()
                button.changed.emit(button)
            
            # Update the canvas
            self.update_button_positions()
            # Update the database
    
    def cleanup_selection_manager(self):
        if hasattr(self, 'selection_manager'):
            self.selection_manager.close()
            self.selection_manager.deleteLater()
            del self.selection_manager
    #------------------------------------------------------------------------------
    def wheelEvent(self, event):
        self._hide_button_tooltip()

        # During multi-button placement, the wheel scales the ghost button size
        # instead of zooming the canvas. Ctrl = width-only, Alt/Option = height-only.
        if self.is_placing_multi and self.pending_placement_data is not None:
            delta = event.angleDelta().y()
            if delta == 0:
                delta = event.pixelDelta().y()  # trackpad fallback
            if delta != 0:
                step = 1.10 if delta > 0 else (1.0 / 1.10)
                mods = event.modifiers()
                width_only = bool(mods & QtCore.Qt.ControlModifier)
                height_only = bool(mods & QtCore.Qt.AltModifier)
                d = self.pending_placement_data
                if width_only and not height_only:
                    d['scale_w'] = max(0.25, min(4.0, d.get('scale_w', 1.0) * step))
                elif height_only and not width_only:
                    d['scale_h'] = max(0.25, min(4.0, d.get('scale_h', 1.0) * step))
                else:
                    d['scale_w'] = max(0.25, min(4.0, d.get('scale_w', 1.0) * step))
                    d['scale_h'] = max(0.25, min(4.0, d.get('scale_h', 1.0) * step))
                self.update()
            event.accept()
            return

        alt_pressed = bool(event.modifiers() & QtCore.Qt.AltModifier)
        ctrl_pressed = bool(event.modifiers() & QtCore.Qt.ControlModifier)

        if alt_pressed:
            event.ignore()
            return

        # Detect trackpad vs mouse using scroll phase + horizontal movement.
        # Mouse wheels are 1D (vertical only), trackpads are 2D and almost
        # always produce some horizontal delta during two-finger scrolling.
        pixel_delta = event.pixelDelta()
        angle_delta_y = event.angleDelta().y()

        try:
            phase = event.phase()
            no_phase = (phase == QtCore.Qt.ScrollPhase.NoScrollPhase)
        except AttributeError:
            no_phase = True

        if no_phase:
            # No scroll phase = traditional discrete mouse wheel → always zoom
            is_trackpad = False
        else:
            # Phased scroll event = trackpad / Magic Mouse on macOS.
            # Default to trackpad for any phased stream; horizontal delta
            # only confirms it. Reset on ScrollEnd so classification does
            # not bleed across gesture boundaries (important for forwarded
            # synthetic events from PickerButton.wheelEvent which may
            # arrive mid-stream without a ScrollBegin phase).
            try:
                if phase == QtCore.Qt.ScrollPhase.ScrollBegin:
                    self._scroll_gesture_is_trackpad = True
                elif phase == QtCore.Qt.ScrollPhase.ScrollEnd:
                    pass  # leave classification alone for this final event
                elif abs(pixel_delta.x()) > 0:
                    self._scroll_gesture_is_trackpad = True
                elif not self._scroll_gesture_is_trackpad:
                    # Phased event with no ScrollBegin we ever saw — assume
                    # trackpad rather than mis-zooming.
                    self._scroll_gesture_is_trackpad = True
            except AttributeError:
                pass
            is_trackpad = self._scroll_gesture_is_trackpad

        if is_trackpad and not ctrl_pressed:
            # ----------------------------------------------------------
            # TRACKPAD: Two-finger scroll -> PAN (natural gesture)
            # Ctrl + scroll -> zoom (handled below)
            # ----------------------------------------------------------
            pan_delta = QtCore.QPointF(pixel_delta.x(), pixel_delta.y())
            self.update_pan_offset(pan_delta)
            self._geometry_dirty = True
            self.update()
            # Restart flush timer (resets on each event — fires once inertia settles)
            self._geometry_flush_timer.start()

            # Reset trackpad classification at the end of a stream so the
            # next gesture (or a real mouse wheel) starts cleanly.
            try:
                if phase == QtCore.Qt.ScrollPhase.ScrollEnd:
                    self._scroll_gesture_is_trackpad = False
            except (AttributeError, NameError):
                pass

            event.accept()
            return

        # ----------------------------------------------------------
        # ZOOM: Mouse wheel or Ctrl + trackpad scroll
        # Proportional zoom using pow() so that:
        #   - Standard mouse notch (±120) gives the same 1.2x as before
        #   - Small trackpad deltas give tiny, smooth increments
        #   - Zoom-in and zoom-out are perfectly symmetric
        # ----------------------------------------------------------
        zoom_base = 1.05 if ctrl_pressed else 1.2

        if is_trackpad:
            # Trackpad Ctrl+scroll: use pixelDelta for smooth proportional zoom
            zoom_factor = pow(zoom_base, pixel_delta.y() / 120.0)
        else:
            # Mouse wheel: proportional to angleDelta (120 per notch)
            zoom_factor = pow(zoom_base, angle_delta_y / 120.0)

        # Get mouse position in scene coordinates before zoom
        mouse_pos = QtCore.QPointF(event.position().x(), event.position().y())
        old_scene_pos = self.canvas_to_scene_coords(mouse_pos)

        self.zoom_factor *= zoom_factor
        self.zoom_factor = max(0.01, min(self.zoom_factor, 100.0))

        # Adjust pan to keep cursor position stable during zoom
        new_scene_pos = self.canvas_to_scene_coords(mouse_pos)
        self.pan_offset += (new_scene_pos - old_scene_pos) * self.zoom_factor

        self._geometry_dirty = True
        self.update()

        if hasattr(self, 'transform_guides') and self.transform_guides.isVisible():
            self.transform_guides.update_position()

        self._geometry_flush_timer.start()
        self._view_change_timer.start()

        # Reset trackpad classification at the end of a stream.
        try:
            if phase == QtCore.Qt.ScrollPhase.ScrollEnd:
                self._scroll_gesture_is_trackpad = False
        except (AttributeError, NameError):
            pass

        event.accept()

    def _apply_zoom_at_position(self, zoom_factor, position):
        """Apply zoom centered on a given canvas position."""
        old_scene_pos = self.canvas_to_scene_coords(position)

        self.zoom_factor *= zoom_factor
        self.zoom_factor = max(0.01, min(self.zoom_factor, 100.0))

        new_scene_pos = self.canvas_to_scene_coords(position)
        self.pan_offset += (new_scene_pos - old_scene_pos) * self.zoom_factor

        self.setUpdatesEnabled(False)
        self.update()
        self.update_button_positions()
        self.setUpdatesEnabled(True)

        if hasattr(self, 'transform_guides') and self.transform_guides.isVisible():
            self.transform_guides.update_position()

        self._view_change_timer.start()

    def event(self, ev):
        """Handle native gesture events (trackpad pinch-to-zoom)."""
        # Qt6 (PySide6): QEvent.Type.NativeGesture
        # Qt5 (PySide2): QEvent.NativeGesture
        native_gesture_type = getattr(
            QtCore.QEvent.Type, 'NativeGesture',
            getattr(QtCore.QEvent, 'NativeGesture', None)
        )
        wheel_type = getattr(
            QtCore.QEvent.Type, 'Wheel',
            getattr(QtCore.QEvent, 'Wheel', None)
        )
        ev_type = ev.type()
        # On macOS, reactivate the picker window for scroll/gesture events
        # so zoom/pan works even after focus was returned to Maya
        if ev_type in (native_gesture_type, wheel_type):
            if not self.window().isActiveWindow():
                self.window().activateWindow()
        if native_gesture_type is not None and ev_type == native_gesture_type:
            return self._handle_native_gesture(ev)
        return super().event(ev)

    def _handle_native_gesture(self, event):
        """Process trackpad pinch / smart-zoom gestures."""
        try:
            gesture_type = event.gestureType()
        except AttributeError:
            return False

        # Resolve enum values for both Qt5 and Qt6
        zoom_gesture = getattr(
            getattr(QtCore.Qt, 'NativeGestureType', QtCore.Qt),
            'ZoomNativeGesture', None
        )
        smart_zoom_gesture = getattr(
            getattr(QtCore.Qt, 'NativeGestureType', QtCore.Qt),
            'SmartZoomNativeGesture', None
        )

        if zoom_gesture is not None and gesture_type == zoom_gesture:
            # Pinch-to-zoom: event.value() is the relative scale delta
            scale_delta = event.value()
            pos = QtCore.QPointF(event.position())
            self._apply_zoom_at_position(1.0 + scale_delta, pos)
            self._hide_button_tooltip()
            event.accept()
            return True

        if smart_zoom_gesture is not None and gesture_type == smart_zoom_gesture:
            # Two-finger double-tap: toggle between 1x and 2x
            pos = QtCore.QPointF(event.position())
            if abs(self.zoom_factor - 1.0) < 0.01:
                target = 2.0
            else:
                target = 1.0
            self._apply_zoom_at_position(target / self.zoom_factor, pos)
            event.accept()
            return True

        return False

    # ------------------------------------------------------------------
    # Transform Guides Throttling
    # ------------------------------------------------------------------
    def _request_guides_update(self):
        """Schedule a throttled transform guides position update."""
        if (hasattr(self, 'transform_guides') and
                self.transform_guides.isVisible() and self.edit_mode):
            if not self._guides_update_timer.isActive():
                self._guides_update_timer.start()

    def _on_guides_timer(self):
        """Persistent timer callback for transform guides update."""
        if hasattr(self, 'transform_guides') and self.transform_guides.isVisible():
            self.transform_guides.update_position()

    # ------------------------------------------------------------------
    # Curve Editor Integration
    # ------------------------------------------------------------------
    def start_new_shape_drawing(self, button):
        """Start drawing a new custom shape for a button."""
        if not self.edit_mode or not button:
            return

        # Save undo state before starting
        DM.PickerDataManager.save_undo_state(
            operation_name="Start New Shape Drawing",
            selected_button_ids=[button.unique_id]
        )

        # Hide transform guides while editing curves
        self.hide_transform_guides()

        # Deselect other buttons
        self.clear_selection()

        # Start curve editor with empty shape
        self.curve_editor.start_editing(button, existing_shape=CE.ButtonShape())

    def start_drawing_new_button_shape(self, position):
        """Create a new button and start drawing a custom shape for it.
        Called from canvas context menu."""
        if not self.edit_mode:
            return

        scene_pos = self.canvas_to_scene_coords(QtCore.QPointF(position))

        main_window = self.window()
        if not isinstance(main_window, UI.AnimPickerWindow):
            return

        current_tab = main_window.tab_system.current_tab
        unique_id = main_window.generate_unique_id(current_tab)

        # Create button with default properties
        new_button = PB.PickerButton("Button", self, unique_id=unique_id)
        new_button.scene_position = scene_pos

        # Add button to canvas
        self.add_button(new_button)

        # Save the button immediately so it persists even if shape drawing is cancelled
        self.update_button_data(new_button)

        # Start drawing the shape for this new button
        self.start_new_shape_drawing(new_button)

    def start_curve_editing(self, button):
        """Start curve editing for a button."""
        if not self.edit_mode or not button:
            return

        # Save undo state before starting curve editing
        DM.PickerDataManager.save_undo_state(
            operation_name="Start Curve Editing",
            selected_button_ids=[button.unique_id]
        )

        # Hide transform guides while editing curves
        if hasattr(self, 'transform_guides'):
            self.transform_guides.setVisible(False)
            self.transform_guides.visual_layer.setVisible(False)

        # Deselect other buttons, highlight target
        self.clear_selection()

        # Start curve editor
        self.curve_editor.start_editing(button)

    def is_curve_editing(self):
        """Check if curve editing is currently active."""
        return hasattr(self, 'curve_editor') and self.curve_editor.is_editing()

    def _on_curve_editing_finished(self, svg_path_data):
        """Handle completion of curve editing."""
        if self.curve_editor.target_button:
            button = self.curve_editor.target_button

            # Apply the new shape to the button
            if svg_path_data:
                button.shape_type = 'custom_path'
                button.svg_path_data = svg_path_data

            # Invalidate caches
            button._cached_scene_path = None
            button._cached_scene_path_key = None
            button.cached_mask = None

            # Update the button in database
            main_window = self.window()
            if hasattr(main_window, 'update_button_data'):
                main_window.update_button_data(button)

            # Clear curve editor state
            self.curve_editor.target_button = None

            # Re-show transform guides and re-select button
            if self.edit_mode:
                self.clear_selection()
                button.is_selected = True
                # Invalidate selection cache so get_selected_buttons() sees the change
                if hasattr(self, '_cache_valid'):
                    self._cache_valid = False
                button.selected.emit(button, True)
                button.update()
                if hasattr(self, 'transform_guides'):
                    self.transform_guides.setVisible(True)
                    self.transform_guides.visual_layer.setVisible(True)
                    self.transform_guides.update_selection()

        self.update()

    def _on_curve_editing_cancelled(self):
        """Handle cancellation of curve editing."""
        button = self.curve_editor.target_button
        is_new_shape = hasattr(self.curve_editor, '_is_new_shape') and self.curve_editor._is_new_shape

        # If this was a new shape being drawn, delete the placeholder button
        if is_new_shape:
            if button and button in self.buttons:
                self.buttons.remove(button)
                button.deleteLater()
                button = None

        # Re-select the button and show transform guides
        if self.edit_mode:
            if button and button in self.buttons:
                self.clear_selection()
                button.is_selected = True
                if hasattr(self, '_cache_valid'):
                    self._cache_valid = False
                button.selected.emit(button, True)
                button.update()
            if hasattr(self, 'transform_guides'):
                self.transform_guides.setVisible(True)
                self.transform_guides.visual_layer.setVisible(True)
                self.transform_guides.update_selection()

        self.update()

    def mouseDoubleClickEvent(self, event):
        if event.button() == QtCore.Qt.LeftButton:
            # Check if a canvas-painted button is under cursor — forward double-click
            dbl_button = self._get_button_at_position(event.pos())
            if dbl_button and dbl_button._canvas_painted:
                local_pos = dbl_button.mapFromParent(event.pos())
                fwd = QtGui.QMouseEvent(
                    event.type(), local_pos, event.globalPos(),
                    event.button(), event.buttons(), event.modifiers()
                )
                dbl_button.mouseDoubleClickEvent(fwd)
                event.accept()
                return
            # No button — reset zoom/pan
            self.zoom_factor = 1.0
            self.pan_offset = QtCore.QPointF(0, 0)
            self.update()
            self.update_button_positions()
            self.focus_canvas()
        super().mouseDoubleClickEvent(event)
        
    def mousePressEvent(self, event):
        """Enhanced mouse press event with proper modifier handling"""
        # Hide tooltip immediately
        self._hide_button_tooltip()

        # Duplicate-mirror tool: intercept left-click. Right/middle still pass
        # through so context menus and middle-button pan continue to work.
        if (hasattr(self, 'duplicate_mirror_tool') and self.duplicate_mirror_tool.active
                and event.button() == QtCore.Qt.LeftButton):
            self.duplicate_mirror_tool.handle_mouse_press(event)
            event.accept()
            return

        # Multi-button placement mode: left = commit, right/middle = cancel.
        if self.is_placing_multi:
            if event.button() == QtCore.Qt.LeftButton:
                self._commit_multi_button_placement(event.modifiers())
            else:
                self._cancel_multi_button_placement()
            event.accept()
            return

        if (hasattr(self, 'transform_guides') and self.transform_guides.isVisible() and event.button() == QtCore.Qt.LeftButton):
            # Handle transform guides first
            guides_pos = self.transform_guides.mapFromParent(event.pos())
            if self.transform_guides.geometry().contains(event.pos()):
                guides_pos_f = QtCore.QPointF(guides_pos)
                handle = self.transform_guides.get_handle_at_pos(guides_pos_f)
                
                if handle:
                    transform_event = QtGui.QMouseEvent(
                        event.type(), guides_pos, event.globalPos(), 
                        event.button(), event.buttons(), event.modifiers()
                    )
                    self.transform_guides.mousePressEvent(transform_event)
                    if transform_event.isAccepted():
                        event.accept()
                        return
        
        # Handle HUD events
        hud_pos = self.hud.mapFromParent(event.pos())
        if self.hud.button_container.geometry().contains(hud_pos):
            self.hud.toggle_button.click()
            return
        
        if event.button() == QtCore.Qt.LeftButton:
            # Store modifier states
            alt_pressed = bool(event.modifiers() & QtCore.Qt.AltModifier)
            ctrl_pressed = bool(event.modifiers() & QtCore.Qt.ControlModifier)
            shift_pressed = bool(event.modifiers() & QtCore.Qt.ShiftModifier)
            
            # Store initial selection state for drag operations
            self.initial_selection_state = {button: button.is_selected for button in self.buttons}
            self.ctrl_held_during_selection = ctrl_pressed
            self.alt_held_during_selection = alt_pressed  # Store alt state
            
            # Find if we clicked directly on a button
            '''clicked_button = None
            for button in self.buttons:
                if button.geometry().contains(event.pos()):
                    clicked_button = button
                    break'''
            clicked_button = self._get_button_at_position(event.pos())

            if clicked_button:
                self._pressed_button = clicked_button
                # Forward the mouse event to the canvas-painted button
                if clicked_button._canvas_painted:
                    local_pos = clicked_button.mapFromParent(event.pos())
                    fwd = QtGui.QMouseEvent(
                        event.type(), local_pos, event.globalPos(),
                        event.button(), event.buttons(), event.modifiers()
                    )
                    clicked_button.mousePressEvent(fwd)
            elif alt_pressed:
                # Alt + drag for panning
                self.last_pan_pos = event.pos()
                event.accept()
            else:
                # Clicked empty space - handle selection clearing
                if not shift_pressed:
                    # Clear selection when shift is not held
                    if self.edit_mode:
                        self.clear_selection()
                    else:
                        # Clear both Maya and picker selection with sync lock
                        self._clear_all_selections()
                    
                    # Update initial selection state after clearing
                    self.initial_selection_state = {button: False for button in self.buttons}
                    self.buttons_in_current_drag.clear()
                    
                    self.button_selection_changed.emit()
                    self.update_hud_counts()
                
                self.setCursor(QtCore.Qt.ArrowCursor)
                # Start rubber band selection
                self.rubberband_origin = event.pos()
                self.rubberband.setGeometry(QtCore.QRect(self.rubberband_origin, QtCore.QSize()))
                self.rubberband.show()
                self.is_selecting = True
            
            event.accept()
            
        elif event.button() == QtCore.Qt.MiddleButton:
            self.last_pan_pos = event.pos()
            self.setCursor(QtCore.Qt.ArrowCursor)
            event.accept()
        elif event.button() == QtCore.Qt.RightButton:
            alt_pressed = bool(event.modifiers() & QtCore.Qt.AltModifier)

            if alt_pressed:
                # Alt+RightButton for zoom — store anchor for cursor-centered zoom
                self.last_zoom_pos = event.pos()
                self._zoom_anchor_pos = event.pos()
                self.was_zoom_dragging = True
                self.setCursor(QtCore.Qt.SizeVerCursor)
                event.accept()
            else:
                # Check if a canvas-painted button is under cursor — forward right-click
                rc_button = self._get_button_at_position(event.pos())
                if rc_button and rc_button._canvas_painted:
                    local_pos = rc_button.mapFromParent(event.pos())
                    fwd = QtGui.QMouseEvent(
                        event.type(), local_pos, event.globalPos(),
                        event.button(), event.buttons(), event.modifiers()
                    )
                    rc_button.mousePressEvent(fwd)
                    event.accept()
                else:
                    # No button — show context menu manually
                    self.show_context_menu(event.pos())
        else:
            super().mousePressEvent(event)
            self.setFocus()
        
        main_window = self.window()
        if main_window.edit_mode == False:
            UT.maya_main_window().activateWindow()

    def mouseMoveEvent(self, event):
        # Duplicate-mirror tool: drag the axis line (or update hover state).
        if hasattr(self, 'duplicate_mirror_tool') and self.duplicate_mirror_tool.active:
            if self.duplicate_mirror_tool.handle_mouse_move(event):
                event.accept()
                return

        # Multi-button placement: live-update ghost layout.
        if self.is_placing_multi:
            self.placement_cursor_scene = self.canvas_to_scene_coords(QtCore.QPointF(event.pos()))
            self.update()
            event.accept()
            return

        alt_pressed = bool(event.modifiers() & QtCore.Qt.AltModifier)

        # Skip expensive hover hit-testing during active navigation
        is_panning = (((event.buttons() == QtCore.Qt.LeftButton and alt_pressed) or
                       event.buttons() == QtCore.Qt.MiddleButton) and self.last_pan_pos)
        is_zooming = (event.buttons() == QtCore.Qt.RightButton and alt_pressed and self.last_zoom_pos)
        is_button_drag = bool(self._pressed_button and event.buttons() & QtCore.Qt.LeftButton)
        if not (self.is_selecting or is_panning or is_zooming or is_button_drag):
            self._update_hover_button(event.pos())
        if self.is_selecting:
            selection_rect = QtCore.QRect(self.rubberband_origin, event.pos()).normalized()
            self.rubberband.setGeometry(selection_rect)
            
            # Check modifier combinations
            shift_pressed = bool(event.modifiers() & QtCore.Qt.ShiftModifier)
            ctrl_pressed = bool(event.modifiers() & QtCore.Qt.ControlModifier)
            
            # Determine selection mode
            if ctrl_pressed and shift_pressed:
                # Ctrl+Shift: Remove from selection
                self.update_visual_selection(selection_rect, add_to_selection=False, remove_from_selection=True)
            elif shift_pressed:
                # Shift only: Add to selection
                self.update_visual_selection(selection_rect, add_to_selection=True, remove_from_selection=False)
            else:
                # No modifiers: Replace selection
                self.update_visual_selection(selection_rect, add_to_selection=False, remove_from_selection=False)

            event.accept()
        elif event.buttons() == QtCore.Qt.RightButton and alt_pressed and self.last_zoom_pos:
            # Hide tooltip during zoom
            self._hide_button_tooltip()

            # Handle Alt+RMB zoom — anchored to initial cursor position
            ctrl_pressed = bool(event.modifiers() & QtCore.Qt.ControlModifier)

            delta_y = event.pos().y() - self.last_zoom_pos.y()
            zoom_speed = 0.002 if ctrl_pressed else 0.008
            zoom_delta = -delta_y * zoom_speed
            new_zoom = self.zoom_factor * (1.0 + zoom_delta)
            new_zoom = max(0.1, min(10.0, new_zoom))

            # Zoom toward the point where Alt+RMB was first pressed
            anchor = getattr(self, '_zoom_anchor_pos', self.last_zoom_pos)
            scene_before = self.canvas_to_scene_coords(QtCore.QPointF(anchor))

            self.zoom_factor = new_zoom

            scene_after = self.canvas_to_scene_coords(QtCore.QPointF(anchor))
            self.pan_offset += (scene_after - scene_before) * self.zoom_factor

            self.last_zoom_pos = event.pos()
            self._geometry_dirty = True
            self.update()
            event.accept()

        elif ((event.buttons() == QtCore.Qt.LeftButton and alt_pressed) or
              event.buttons() == QtCore.Qt.MiddleButton) and self.last_pan_pos:
            # Hide tooltip during pan
            self._hide_button_tooltip()

            delta = event.pos() - self.last_pan_pos
            self.update_pan_offset(delta)
            self.last_pan_pos = event.pos()
            self._geometry_dirty = True
            self.update()
            event.accept()
        else:
            # Forward move events to the pressed button (for drag in edit mode)
            if hasattr(self, '_pressed_button') and self._pressed_button and self._pressed_button._canvas_painted:
                local_pos = self._pressed_button.mapFromParent(event.pos())
                fwd = QtGui.QMouseEvent(
                    event.type(), local_pos, event.globalPos(),
                    event.button(), event.buttons(), event.modifiers()
                )
                self._pressed_button.mouseMoveEvent(fwd)

            if getattr(self._pressed_button, 'dragging', False):
                self._request_guides_update()
            super().mouseMoveEvent(event)
        event.accept()

    def enterEvent(self, event):
        super().enterEvent(event)

    def leaveEvent(self, event):
        """Handle mouse leaving the canvas"""
        self._hide_button_tooltip()
        if self._current_hover_button:
            self._current_hover_button.is_hovered = False
            self._current_hover_button.update()
            self._current_hover_button = None
        self._pressed_button = None
        self.setCursor(QtCore.Qt.ArrowCursor)
        self.update()

        # Hand window activation back to Maya whenever the cursor
        # genuinely leaves the picker so the user's hotkeys (W/E/R,
        # spacebar hotbox, etc.) reach Maya immediately. enterEvent
        # reclaims activation on re-entry, so trackpad gestures still
        # work. leaveEvent also fires when the cursor moves into a
        # child widget, so verify the cursor is actually outside the
        # top-level frame before handing focus over.
        try:
            top = self.window()
            if top is not None:
                global_pos = QtGui.QCursor.pos()
                if not top.frameGeometry().contains(global_pos):
                    self._pending_maya_activation = False
                    UT.maya_main_window().activateWindow()
        except Exception:
            pass
        super().leaveEvent(event)

    def contextMenuEvent(self, event):
        """Accept the context menu event to prevent propagation to parent window."""
        event.accept()

    def mouseReleaseEvent(self, event):
        """Enhanced mouse release with proper modifier state propagation"""
        # Duplicate-mirror tool: end any in-progress line drag.
        if hasattr(self, 'duplicate_mirror_tool') and self.duplicate_mirror_tool.active:
            if self.duplicate_mirror_tool.handle_mouse_release(event):
                event.accept()
                return

        if event.button() == QtCore.Qt.LeftButton and self.is_selecting:
            self.is_selecting = False
            self.rubberband.hide()
            
            # Get modifier states
            shift_pressed = bool(event.modifiers() & QtCore.Qt.ShiftModifier)
            ctrl_pressed = bool(event.modifiers() & QtCore.Qt.ControlModifier)
            alt_held = getattr(self, 'alt_held_during_selection', False)
            
            # Apply final selection with all modifier states
            self.apply_final_selection(shift_pressed, ctrl_pressed, alt_held)
            
            # Clear temporary tracking sets
            self.buttons_in_current_drag.clear()
            self.initial_selection_state.clear()

            if self.edit_mode and hasattr(self, 'transform_guides'):
                QtCore.QTimer.singleShot(15, self.transform_guides.update_selection)
        elif event.button() == QtCore.Qt.LeftButton:
            # Forward release to the pressed button
            if hasattr(self, '_pressed_button') and self._pressed_button and self._pressed_button._canvas_painted:
                local_pos = self._pressed_button.mapFromParent(event.pos())
                fwd = QtGui.QMouseEvent(
                    event.type(), local_pos, event.globalPos(),
                    event.button(), event.buttons(), event.modifiers()
                )
                self._pressed_button.mouseReleaseEvent(fwd)
                self._pressed_button = None
            self.last_pan_pos = None
            self._flush_deferred_geometry()
            self._view_change_timer.start()
        elif event.button() == QtCore.Qt.MiddleButton:
            self.last_pan_pos = None
            self._flush_deferred_geometry()
            self._view_change_timer.start()
        elif event.button() == QtCore.Qt.RightButton:
            # Reset zoom variables and cursor
            self.last_zoom_pos = None
            self.setCursor(QtCore.Qt.ArrowCursor)
            self._flush_deferred_geometry()
            self._view_change_timer.start()
        else:
            super().mouseReleaseEvent(event)
        
        self.button_selection_changed.emit()
        self.clicked.emit()
        main_window = self.window()
        if main_window.edit_mode == False:
            UT.maya_main_window().activateWindow()
        event.accept()
    
    def resizeEvent(self, event):
        super().resizeEvent(event)

        # Compensate pan_offset during programmatic edit-mode resize so
        # the canvas content stays visually anchored in place.
        main_win = self.window()
        if getattr(main_win, '_programmatic_resize', False):
            old_size = event.oldSize()
            new_size = event.size()
            if old_size.isValid():
                dx = (new_size.width() - old_size.width()) / 2.0
                dy = (new_size.height() - old_size.height()) / 2.0
                self.pan_offset -= QtCore.QPointF(dx, dy)

        self.update_button_positions()
        self.hud.setGeometry(self.rect())
        if hasattr(self, 'loading_overlay'):
            self.loading_overlay._reposition()
        if hasattr(self, 'save_indicator'):
            self.save_indicator._reposition()
        self.hud.raise_()
        # Update selection manager position if it exists and is visible
        if hasattr(self, 'selection_manager') and self.selection_manager.isVisible():
            button = self.selection_manager.picker_button
            if button:
                pos = button.mapToGlobal(button.rect().topRight())
                canvas_pos = self.mapFromGlobal(pos)
                self.selection_manager.move(canvas_pos + QtCore.QPoint(10, 0))

    def paintEvent(self, event):
        painter = QtGui.QPainter(self)
        painter.setRenderHint(QtGui.QPainter.Antialiasing)

        # Create a path for clipping
        clip_path = QtGui.QPainterPath()
        clip_path.addRoundedRect(
            self.rect().adjusted(1, 1, -1, -1),
            self.border_radius,
            self.border_radius
        )
        painter.setClipPath(clip_path)

        if not self.minimal_mode:
            # Draw background only in normal mode
            painter.fillRect(self.rect(), self.background_color)

            # Draw static dot pattern only in normal mode
            if self.show_dots:
                painter.save()
                painter.setOpacity(0.5)
                painter.fillRect(self.rect(), self.dot_texture)
                painter.restore()

        # Set up transform for canvas elements
        painter.save()
        center = QtCore.QPointF(self.width() / 2, self.height() / 2)
        painter.translate(center + self.pan_offset)
        painter.scale(self.zoom_factor, self.zoom_factor)

        # Calculate visible area in scene coordinates
        top_left = self.canvas_to_scene_coords(QtCore.QPointF(0, 0))
        bottom_right = self.canvas_to_scene_coords(QtCore.QPointF(self.width(), self.height()))
        visible_rect = self.rect()

        # Draw grid BEFORE axes (so axes appear on top)
        if not self.minimal_mode:
            self.draw_grid(painter, visible_rect)

        if not self.minimal_mode and self.show_axes:
            # Draw axes lines only in normal mode and when show_axes is True
            pen_width = .2 / self.zoom_factor
            
            # Draw X axis (red)
            pen = QtGui.QPen(QtGui.QColor(255, 0, 0))
            pen.setWidthF(pen_width)
            painter.setPen(pen)
            painter.drawLine(QtCore.QLineF(top_left.x(), 0, bottom_right.x(), 0))

            # Draw Y axis (green)
            pen.setColor(QtGui.QColor(0, 255, 0))
            painter.setPen(pen)
            painter.drawLine(QtCore.QLineF(0, top_left.y(), 0, bottom_right.y()))

        # Draw background image if available
        if self.background_image and not self.background_image.isNull():
            painter.setOpacity(self.image_opacity)
            scaled_width = self.background_image.width() * self.image_scale
            scaled_height = self.background_image.height() * self.image_scale
            image_rect = QtCore.QRectF(
                -scaled_width / 2,
                -scaled_height / 2,
                scaled_width,
                scaled_height
            )
            painter.drawImage(image_rect, self.background_image)

        # --- Paint buttons directly on canvas (Figma-style) ---
        # This replaces per-widget paintEvent drawing with a single canvas pass,
        # using floating-point scene coordinates to eliminate integer-rounding jitter.
        painter.setOpacity(1.0)
        hover_btn = self._current_hover_button
        # Scene-space visible area for culling (with margin)
        vis_tl = self.canvas_to_scene_coords(QtCore.QPointF(0, 0))
        vis_br = self.canvas_to_scene_coords(QtCore.QPointF(self.width(), self.height()))
        vis_left = min(vis_tl.x(), vis_br.x())
        vis_right = max(vis_tl.x(), vis_br.x())
        vis_top = min(vis_tl.y(), vis_br.y())
        vis_bottom = max(vis_tl.y(), vis_br.y())
        for button in self.buttons:
            if not button._canvas_painted:
                continue
            # Fast scene-space AABB cull
            bp = button._scene_position
            env_w, env_h = button.rotated_envelope_size()
            hw, hh = env_w * 0.5, env_h * 0.5
            if (bp.x() + hw < vis_left or bp.x() - hw > vis_right or
                    bp.y() + hh < vis_top or bp.y() - hh > vis_bottom):
                continue
            button.paint_on_canvas(painter, self.zoom_factor, hover_btn)

        # --- Duplication ghost preview ---
        if hasattr(self, '_pressed_button') and self._pressed_button and getattr(self._pressed_button, 'duplicating', False):
            ghost_center = getattr(self._pressed_button, '_dup_ghost_scene_center', None)
            ghost_offsets = getattr(self._pressed_button, '_dup_ghost_offsets', [])
            if ghost_center and ghost_offsets:
                for btn, offset in ghost_offsets:
                    ghost_pos = QtCore.QPointF(
                        ghost_center.x() + offset.x(),
                        ghost_center.y() + offset.y()
                    )
                    btn.paint_ghost_on_canvas(painter, ghost_pos)

        # Multi-button placement ghosts (drag-to-place)
        if self.is_placing_multi:
            self._paint_placement_ghosts(painter)

        # Duplicate-mirror tool: dashed axis line + ghost previews (in edit mode only)
        if hasattr(self, 'duplicate_mirror_tool') and self.duplicate_mirror_tool.active:
            self.duplicate_mirror_tool.paint(painter, self.zoom_factor)

        painter.restore()

        # Remove clipping to draw the border
        painter.setClipping(False)

        if not self.minimal_mode:
            # Draw border only in normal mode
            pen = QtGui.QPen(self.border_color)
            pen.setWidth(self.border_width)
            painter.setPen(pen)
            painter.setBrush(QtCore.Qt.NoBrush)
            painter.drawRoundedRect(
                self.rect().adjusted(1, 1, -1, -1),
                self.border_radius,
                self.border_radius
            )   

    def _create_buttons_from_curves_at_position(self, position):
        """Create buttons from Maya curves at the specified position"""
        try:
            from .maya_curve_converter import create_buttons_from_maya_curves
            scene_pos = self.canvas_to_scene_coords(QtCore.QPointF(position))
            create_buttons_from_maya_curves(self, scene_pos, show_options_dialog=False)
        except Exception as e:
            print(f"Error creating buttons from curves: {e}")
    
    def _create_test_scene(self):
        """Create a test scene for sync testing"""
        try:
            from . import selection_sync_test as SST
            SST.create_test_scene()
        except Exception as e:
            print(f"Error creating test scene: {e}")

    def cleanup(self):
        """Clean up resources when canvas is destroyed"""
        # Cleanup selection synchronization
        self._cleanup_selection_sync()
        
        self._hide_button_tooltip()
        if self._tooltip_widget:
            self._tooltip_widget.deleteLater()
            self._tooltip_widget = None
        
        # Clean up other resources...
        if hasattr(self, 'transform_guides'):
            self.transform_guides.deleteLater()
        
        if hasattr(self, 'hud'):
            self.hud.deleteLater()
    
    #------------------------------------------------------------------------------
    # Selection Synchronization Methods
    #------------------------------------------------------------------------------
    def _init_selection_sync(self):
        """Initialize 2-way selection synchronization"""
        try:
            # Register this canvas with the selection sync manager
            SSM.register_canvas_for_sync(self)
        except Exception as e:
            print(f"PickerCanvas (Maya): Error initializing selection sync: {e}")
    
    def _cleanup_selection_sync(self):
        """Cleanup selection synchronization"""
        try:
            # Unregister this canvas from the selection sync manager
            SSM.unregister_canvas_from_sync(self)
        except Exception as e:
            print(f"PickerCanvas (Maya): Error cleaning up selection sync: {e}")
    
    def _get_current_namespace(self):
        """Get the current namespace for this canvas"""
        try:
            # Try to get namespace from parent window
            main_window = self.window()
            if hasattr(main_window, '_get_current_namespace'):
                return main_window._get_current_namespace()
            elif hasattr(main_window, 'namespace_dropdown'):
                current_text = main_window.namespace_dropdown.currentText()
                return current_text if current_text != 'None' else None
        except:
            pass
        return None
    
    def enable_selection_sync(self):
        """Enable 2-way selection synchronization"""
        SSM.enable_selection_sync()
    
    def disable_selection_sync(self):
        """Disable 2-way selection synchronization"""
        SSM.disable_selection_sync()
    
    def _test_selection_sync(self):
        """Test the selection synchronization system"""
        try:
            from . import selection_sync_test as SST
            SST.run_sync_tests()
        except Exception as e:
            print(f"Error running sync tests: {e}")
    
    def _clear_all_selections(self):
        """Clear both Maya and picker selections with proper sync handling"""
        # Set sync lock to prevent interference during clearing
        try:
            manager = SSM.SelectionSyncManager.get_instance()
            manager._sync_lock = True
        except:
            pass
        
        try:
            # Clear Maya selection
            cmds.select(clear=True)
            
            # Clear picker selection
            self.clear_selection()
            
            # Small delay to ensure Maya has processed the deselection
            QTimer.singleShot(100, self._release_sync_lock)
            
        except Exception as e:
            print(f"Error clearing selections: {e}")
            # Always release lock on error
            self._release_sync_lock()
    
    def _release_sync_lock(self):
        """Release the sync lock after selection clearing"""
        try:
            manager = SSM.SelectionSyncManager.get_instance()
            manager._delayed_unlock()
        except Exception as e:
            print(f"Error releasing sync lock: {e}")

