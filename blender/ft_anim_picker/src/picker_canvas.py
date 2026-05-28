from PySide6 import QtWidgets, QtCore, QtGui
from PySide6.QtGui import QColor, QShortcut, QPainter, QBrush
from PySide6.QtCore import QTimer, QPropertyAnimation, QEasingCurve, Signal, Property
from shiboken6 import wrapInstance
from functools import partial

import os
import math
import warnings

import bpy

from . import blender_ui as UI
from . import utils as UT
from . import picker_button as PB
from . import custom_button as CB
from . import tool_functions as TF
from . import data_management as DM
from . import custom_dialog as CD
from . import pb_transform_guides as TG
from .blender_curve_converter import create_buttons_from_blender_curves
from . import selection_sync_manager as SSM
from . import curve_editor as CE
from . import duplicate_mirror_tool as DMT

class ResizeHandle(QtWidgets.QWidget):
    """
    An elegant draggable resize handle for resizing the edit panel.
    Features smooth animations, visual feedback, and a modern design.
    """
    resizing = QtCore.Signal(int)  # Emits the delta x movement
    resize_started = QtCore.Signal()
    resize_finished = QtCore.Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedWidth(8)
        self.setCursor(QtCore.Qt.SizeHorCursor)
        self.setMouseTracking(True)

        # State tracking
        self._is_dragging = False
        self._is_hovered = False
        self._drag_start_x = 0

        # Animation properties
        self._highlight_opacity = 0.0
        self._handle_width = 2.0

        # Colors
        self._base_color = QColor(80, 80, 80)
        self._hover_color = QColor(29, 101, 202)  # Green accent #5c7918
        self._drag_color = QColor(29, 101, 202)  # Brighter green when dragging

        # Setup animations
        self._setup_animations()

        # Tooltip
        self.setToolTip("Drag to resize panel")

    def _setup_animations(self):
        """Setup smooth property animations for visual feedback."""
        # Opacity animation for the highlight effect
        self._opacity_animation = QPropertyAnimation(self, b"highlightOpacity")
        self._opacity_animation.setDuration(150)
        self._opacity_animation.setEasingCurve(QEasingCurve.OutCubic)

        # Width animation for the handle bar
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

    # Define Qt properties for animation
    highlightOpacity = Property(float, get_highlight_opacity, set_highlight_opacity)
    handleWidth = Property(float, get_handle_width, set_handle_width)

    def paintEvent(self, event):
        """Draw the resize handle with elegant visual feedback."""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        # Calculate the handle bar dimensions
        handle_height = min(60, self.height() * 0.3)
        handle_x = (self.width() - self._handle_width) / 2
        handle_y = (self.height() - handle_height) / 2

        # Determine the current color based on state
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

        # Draw subtle background highlight on hover/drag
        if self._highlight_opacity > 0 or self._is_dragging:
            bg_opacity = int(30 * (self._highlight_opacity if not self._is_dragging else 1.0))
            bg_color = QColor(self._hover_color)
            bg_color.setAlpha(bg_opacity)
            painter.fillRect(self.rect(), bg_color)

        # Draw the handle bar (centered vertical line with rounded ends)
        painter.setPen(QtCore.Qt.NoPen)
        painter.setBrush(QBrush(color))

        # Draw rounded rectangle for the handle
        handle_rect = QtCore.QRectF(handle_x, handle_y, self._handle_width, handle_height)
        painter.drawRoundedRect(handle_rect, self._handle_width / 2, self._handle_width / 2)

        # Draw subtle grip dots when hovered or dragging
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
                painter.drawEllipse(
                    QtCore.QPointF(self.width() / 2, dot_y),
                    dot_radius, dot_radius
                )

        painter.end()

    def enterEvent(self, event):
        """Handle mouse entering the widget."""
        self._is_hovered = True
        self._animate_hover(True)
        super().enterEvent(event)

    def leaveEvent(self, event):
        """Handle mouse leaving the widget."""
        if not self._is_dragging:
            self._is_hovered = False
            self._animate_hover(False)
        super().leaveEvent(event)

    def _animate_hover(self, entering):
        """Animate the hover state transition."""
        self._opacity_animation.stop()
        self._width_animation.stop()

        self._opacity_animation.setStartValue(self._highlight_opacity)
        self._opacity_animation.setEndValue(1.0 if entering else 0.0)

        self._width_animation.setStartValue(self._handle_width)
        self._width_animation.setEndValue(3.5 if entering else 2.0)

        self._opacity_animation.start()
        self._width_animation.start()

    def mousePressEvent(self, event):
        """Start the resize operation."""
        if event.button() == QtCore.Qt.LeftButton:
            self._is_dragging = True
            self._drag_start_x = event.globalPosition().x()
            self.resize_started.emit()

            # Visual feedback for drag start
            self._width_animation.stop()
            self._width_animation.setStartValue(self._handle_width)
            self._width_animation.setEndValue(4.5)
            self._width_animation.start()

            self.update()
            # Accept the event to prevent propagation to parent (window drag)
            event.accept()
        else:
            event.ignore()

    def mouseMoveEvent(self, event):
        """Handle the resize dragging."""
        if self._is_dragging:
            current_x = event.globalPosition().x()
            delta = int(self._drag_start_x - current_x)  # Negative because we're resizing from left
            self._drag_start_x = current_x
            self.resizing.emit(delta)
            # Accept the event to prevent propagation
            event.accept()
        else:
            event.ignore()

    def mouseReleaseEvent(self, event):
        """End the resize operation."""
        if event.button() == QtCore.Qt.LeftButton and self._is_dragging:
            self._is_dragging = False
            self.resize_finished.emit()

            # Animate back to hover state if still hovered
            if self._is_hovered:
                self._width_animation.stop()
                self._width_animation.setStartValue(self._handle_width)
                self._width_animation.setEndValue(3.5)
                self._width_animation.start()
            else:
                self._animate_hover(False)

            self.update()
            # Accept the event to prevent propagation
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

# ======================================================================
# Image Transform Guides — resize/move handles for background image layers
# ======================================================================
class ImageTransformGuides(QtWidgets.QWidget):
    """Resize/move handles for a selected background image layer."""

    ACCENT = QtGui.QColor(29, 101, 202)
    HANDLE_SIZE = 8

    transform_started = QtCore.Signal()
    transform_updated = QtCore.Signal(str, dict)   # layer_id, {scale, offset_x, offset_y}
    transform_finished = QtCore.Signal(str, dict)

    def __init__(self, canvas, parent=None):
        super().__init__(parent)
        self.canvas = canvas
        self.setMouseTracking(True)
        self.setAttribute(QtCore.Qt.WA_TransparentForMouseEvents, False)
        self.setVisible(False)

        self._active_handle = None      # e.g. 'top_left', 'center', etc.
        self._dragging = False
        self._drag_start_mouse = QtCore.QPointF()
        self._drag_start_offset = (0.0, 0.0)
        self._drag_start_scale = 1.0

        self.handles = {
            'top_left': QtCore.QPointF(0, 0),
            'top_center': QtCore.QPointF(0.5, 0),
            'top_right': QtCore.QPointF(1, 0),
            'middle_left': QtCore.QPointF(0, 0.5),
            'middle_right': QtCore.QPointF(1, 0.5),
            'bottom_left': QtCore.QPointF(0, 1),
            'bottom_center': QtCore.QPointF(0.5, 1),
            'bottom_right': QtCore.QPointF(1, 1),
        }

    # ---- geometry helpers ----
    def _layer_rect_widget(self):
        """Return the selected layer's rect in widget (pixel) coordinates."""
        layer = self.canvas.get_selected_layer()
        if not layer:
            return QtCore.QRectF()
        scene_rect = self.canvas.get_layer_scene_rect(layer)
        tl = self.canvas.scene_to_canvas_coords(scene_rect.topLeft())
        br = self.canvas.scene_to_canvas_coords(scene_rect.bottomRight())
        return QtCore.QRectF(tl, br).normalized()

    def _handle_rects(self):
        """Yield (handle_name, QRectF) for each handle in widget coords."""
        rect = self._layer_rect_widget()
        if rect.isNull():
            return
        hs = self.HANDLE_SIZE
        for name, rel in self.handles.items():
            cx = rect.left() + rel.x() * rect.width()
            cy = rect.top() + rel.y() * rect.height()
            yield name, QtCore.QRectF(cx - hs / 2, cy - hs / 2, hs, hs)

    def _hit_test(self, pos):
        """Return the handle name under pos, or 'center' if inside the rect, or None."""
        for name, r in self._handle_rects():
            if r.contains(pos):
                return name
        rect = self._layer_rect_widget()
        if rect.contains(pos):
            return 'center'
        return None

    # ---- visibility ----
    def update_visibility(self):
        """Show/hide based on whether there is a selected, unlocked layer in edit mode."""
        layer = self.canvas.get_selected_layer()
        vis = (
            self.canvas.edit_mode
            and layer is not None
            and not layer.get('locked', False)
            and layer.get('image') is not None
        )
        self.setVisible(vis)
        if vis:
            self.setGeometry(self.canvas.rect())
            self.raise_()
            self.update()

    # ---- painting ----
    def paintEvent(self, event):
        layer = self.canvas.get_selected_layer()
        if not layer:
            return
        rect = self._layer_rect_widget()
        if rect.isNull():
            return

        painter = QtGui.QPainter(self)
        painter.setRenderHint(QtGui.QPainter.Antialiasing)

        # Bounding box
        pen = QtGui.QPen(self.ACCENT, 1.5)
        pen.setStyle(QtCore.Qt.DashLine)
        painter.setPen(pen)
        painter.setBrush(QtCore.Qt.NoBrush)
        painter.drawRect(rect)

        # Handles
        painter.setPen(QtGui.QPen(self.ACCENT, 1))
        painter.setBrush(QtGui.QColor(255, 255, 255, 220))
        for _, hr in self._handle_rects():
            painter.drawRect(hr)

        painter.end()

    # ---- mouse interaction ----
    def mousePressEvent(self, event):
        if event.button() != QtCore.Qt.LeftButton:
            return
        hit = self._hit_test(event.pos())
        if hit is None:
            return
        layer = self.canvas.get_selected_layer()
        if not layer:
            return

        self._active_handle = hit
        self._dragging = True
        self._drag_start_mouse = event.pos()
        self._drag_start_offset = (layer.get('offset_x', 0.0), layer.get('offset_y', 0.0))
        self._drag_start_scale = layer.get('scale', 1.0)
        self._drag_start_rect = self.canvas.get_layer_scene_rect(layer)
        self.transform_started.emit()
        event.accept()

    def mouseMoveEvent(self, event):
        if not self._dragging or not self._active_handle:
            # Update cursor
            hit = self._hit_test(event.pos())
            if hit == 'center':
                self.setCursor(QtCore.Qt.SizeAllCursor)
            elif hit in ('top_left', 'bottom_right'):
                self.setCursor(QtCore.Qt.SizeFDiagCursor)
            elif hit in ('top_right', 'bottom_left'):
                self.setCursor(QtCore.Qt.SizeBDiagCursor)
            elif hit in ('top_center', 'bottom_center'):
                self.setCursor(QtCore.Qt.SizeVerCursor)
            elif hit in ('middle_left', 'middle_right'):
                self.setCursor(QtCore.Qt.SizeHorCursor)
            else:
                self.setCursor(QtCore.Qt.ArrowCursor)
            return

        layer = self.canvas.get_selected_layer()
        if not layer:
            return

        delta_widget = event.pos() - self._drag_start_mouse
        # Convert pixel delta to scene delta
        delta_scene_x = delta_widget.x() / self.canvas.zoom_factor
        delta_scene_y = delta_widget.y() / self.canvas.zoom_factor

        if self._active_handle == 'center':
            # Move
            new_ox = self._drag_start_offset[0] + delta_scene_x
            new_oy = self._drag_start_offset[1] + delta_scene_y
            self.canvas.update_background_layer(layer['id'], offset_x=new_ox, offset_y=new_oy)
            self.transform_updated.emit(layer['id'], {
                'offset_x': new_ox, 'offset_y': new_oy, 'scale': layer.get('scale', 1.0)
            })
        else:
            # Scale: compute distance ratio from center of rect
            rect = self._drag_start_rect
            center = rect.center()
            handle_rel = self.handles.get(self._active_handle, QtCore.QPointF(1, 1))
            # Handle in scene coords
            hx = rect.left() + handle_rel.x() * rect.width()
            hy = rect.top() + handle_rel.y() * rect.height()
            orig_dist = ((hx - center.x()) ** 2 + (hy - center.y()) ** 2) ** 0.5
            if orig_dist < 1:
                orig_dist = 1
            new_hx = hx + delta_scene_x
            new_hy = hy + delta_scene_y
            new_dist = ((new_hx - center.x()) ** 2 + (new_hy - center.y()) ** 2) ** 0.5
            ratio = new_dist / orig_dist
            new_scale = max(0.01, self._drag_start_scale * ratio)
            self.canvas.update_background_layer(layer['id'], scale=new_scale)
            self.transform_updated.emit(layer['id'], {
                'offset_x': layer.get('offset_x', 0.0),
                'offset_y': layer.get('offset_y', 0.0),
                'scale': new_scale,
            })

        self.update()
        event.accept()

    def mouseReleaseEvent(self, event):
        if self._dragging:
            layer = self.canvas.get_selected_layer()
            if layer:
                self.transform_finished.emit(layer['id'], {
                    'offset_x': layer.get('offset_x', 0.0),
                    'offset_y': layer.get('offset_y', 0.0),
                    'scale': layer.get('scale', 1.0),
                })
            self._dragging = False
            self._active_handle = None


class CanvasEditPanel(QtWidgets.QWidget):
    """
    An overlay edit panel embedded inside canvas_frame.
    Positioned at the right edge of its parent, overlaying the canvas content.
    Does not affect window sizing - the panel simply appears/disappears over the canvas.
    """
    width_changed = QtCore.Signal(int)

    def __init__(self, parent=None):
        super().__init__(parent)

        # Size constraints
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

        # Animation state
        self._slide_offset = 0.0
        self._opacity_effect = QtWidgets.QGraphicsOpacityEffect(self)
        self._opacity_effect.setOpacity(1.0)
        self.setGraphicsEffect(self._opacity_effect)
        self._show_anim_group = None
        self._hide_anim_group = None

        # Setup the layout
        self._layout = QtWidgets.QHBoxLayout(self)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._layout.setSpacing(0)

        # Create the resize handle
        self._resize_handle = ResizeHandle(self)
        self._resize_handle.resizing.connect(self._on_resize)

        # Create a container for the content with painted background/border
        self._content_container = _PaintedContainer(
            bg_color=QtGui.QColor(29, 29, 29),
            border_color=QtGui.QColor(255, 255, 255, 25),
            border_width=2,
            radius=8,
        )
        self._content_layout = QtWidgets.QVBoxLayout(self._content_container)
        self._content_layout.setContentsMargins(0, 0, 0, 0)
        self._content_layout.setSpacing(4)

        # Add widgets to layout (handle on the left)
        self._layout.addWidget(self._resize_handle)
        self._layout.addWidget(self._content_container)

        # Apply initial width
        self._apply_width()

    def get_panel_width(self):
        return self._current_width

    def set_panel_width(self, value):
        self._current_width = value
        self._apply_width()

    panelWidth = Property(int, get_panel_width, set_panel_width)

    # Slide offset property for animation (shifts panel horizontally)
    def _get_slide_offset(self):
        return self._slide_offset

    def _set_slide_offset(self, value):
        self._slide_offset = value
        self._update_position()

    slideOffset = Property(float, _get_slide_offset, _set_slide_offset)

    def _apply_width(self):
        """Apply the current width and reposition within parent."""
        total_width = self._current_width + self._resize_handle.width()
        self.setFixedWidth(total_width)
        self.width_changed.emit(self._current_width)
        self._update_position()

    def set_anchor_widget(self, widget):
        """Set the widget the panel should align to (typically the canvas stack)."""
        self._anchor_widget = widget
        self._update_position()

    def _update_position(self):
        """Position this panel at the right edge of the anchor (or parent) widget."""
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
        """Ensure panel is on top and correctly positioned when shown."""
        super().showEvent(event)
        self.raise_()
        self._update_position()

    # ------------------------------------------------------------------
    # Show / Hide animations
    # ------------------------------------------------------------------
    def animate_show(self, delay_ms=0):
        """Slide in from the right with a fade-in effect."""
        self._stop_animations()

        # Start invisible and offset to the right
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
        """Slide out to the right with a fade-out effect, then hide."""
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
        """Stop any running show/hide animations."""
        for grp in (self._show_anim_group, self._hide_anim_group):
            if grp is not None and grp.state() == QtCore.QAbstractAnimation.Running:
                grp.stop()
        self._show_anim_group = None
        self._hide_anim_group = None

    def add_widget(self, widget):
        """Add a widget to the content area."""
        self._content_layout.addWidget(widget)

    def add_layout(self, layout):
        """Add a layout to the content area."""
        self._content_layout.addLayout(layout)

    def get_content_width(self):
        """Get the width available for content (excluding handle)."""
        return self._current_width

    def set_content_width(self, width, animated=False):
        """Set the content width."""
        width = max(self._min_width, min(self._max_width, width))
        self._current_width = width
        self._apply_width()

    def reset_to_default(self):
        """Reset the panel to its default width."""
        self.set_content_width(self._default_width)

    def _on_resize(self, delta):
        """Handle resize events from the handle."""
        new_width = self._current_width + delta
        new_width = max(self._min_width, min(self._max_width, new_width))

        if new_width != self._current_width:
            self._current_width = new_width
            self._apply_width()

class HUDWidget(QtWidgets.QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(QtCore.Qt.WA_TransparentForMouseEvents)  # Make the whole widget transparent to mouse events
        self.setStyleSheet("background-color: transparent;")
        
        # Main layout for HUD elements
        self.layout = QtWidgets.QGridLayout(self)
        self.layout.setContentsMargins(5, 5, 5, 5)
        #--------------------------------------------------------------------------------------------------------------------------------
        # Create the toggle button container that will catch mouse events
        self.button_container = QtWidgets.QWidget(self)
        self.button_container.setAttribute(QtCore.Qt.WA_TransparentForMouseEvents, False)  # This widget will catch mouse events
        self.button_container.setFixedSize(24, 24)
        #--------------------------------------------------------------------------------------------------------------------------------
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
        #--------------------------------------------------------------------------------------------------------------------------------
        # Stats container
        self.stats_container = QtWidgets.QWidget(self)
        self.stats_layout = QtWidgets.QHBoxLayout(self.stats_container)
        self.stats_layout.setContentsMargins(0, 0, 0, 0)
        self.stats_layout.setSpacing(10)  # Space between labels
        #--------------------------------------------------------------------------------------------------------------------------------
        # Button count label
        self.button_count_label = QtWidgets.QLabel("Buttons: 0 / 0")
        self.button_count_label.setStyleSheet("color: rgba(255, 255, 255, 0.2);")
        #self.stats_layout.addWidget(self.button_count_label)
        self.layout.addWidget(self.button_count_label, 0, 0, QtCore.Qt.AlignBottom | QtCore.Qt.AlignLeft)
        #--------------------------------------------------------------------------------------------------------------------------------
        # Selection count label
        self.selection_layout = QtWidgets.QHBoxLayout()
        self.selection_layout.setContentsMargins(0, 0, 0, 0)
        self.selection_layout.setSpacing(2)
        self.selection_count_label = QtWidgets.QLabel("Selected: 0")
        self.selection_count_label.setStyleSheet("color: rgba(255, 255, 255, 0.2);")

        self.selected_bone_count_label = QtWidgets.QLabel("Selected: 0")
        self.selected_bone_count_label.setStyleSheet("color: rgba(255, 255, 255, 0.2);")
        #self.stats_layout.addWidget(self.selection_count_label)
        object_icon_label = QtWidgets.QLabel()
        object_icon_pixmap = UT.get_icon("object_data.png", opacity=0.2, size=14)
        object_icon_label.setPixmap(object_icon_pixmap)

        bone_icon_label = QtWidgets.QLabel()
        bone_icon_pixmap = UT.get_icon("bone_data.png", opacity=0.2, size=14)
        bone_icon_label.setPixmap(bone_icon_pixmap)
        
        self.selection_layout.addWidget(object_icon_label)
        self.selection_layout.addWidget(self.selection_count_label)
        self.selection_layout.addWidget(bone_icon_label)
        self.selection_layout.addWidget(self.selected_bone_count_label)

        self.layout.addLayout(self.selection_layout, 0, 1, QtCore.Qt.AlignBottom | QtCore.Qt.AlignRight)
        #--------------------------------------------------------------------------------------------------------------------------------
        self.reset_buttons()
        
        # Store all HUD elements (except toggle button)
        self.hud_elements = [
            self.stats_container,
            self.button_count_label,
            self.selection_layout,
            self.reset_button_frame
        ]

        # Initialize visibility
        self.hud_visible = True
        
        # Start timer for updating Maya selection count
        self.update_timer = QtCore.QTimer(self)
        self.update_timer.timeout.connect(self.update_selection_count)
        self.update_timer.start(100)  

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
        """Update the Blender selection count"""
        try:
            # Get the count of selected objects in Blender
            #sel_count = len(bpy.context.selected_objects)
            sel_obj_count = len(TF.selected_objects())
            sel_bone_count = len(TF.selcected_bones_in_pose_mode())
            self.selection_count_label.setText(f": {sel_obj_count}")
            self.selected_bone_count_label.setText(f": {sel_bone_count}")
        except:
            # Handle case where Blender API access fails
            self.selection_count_label.setText("Selected: --")


class CanvasLoadingOverlay(QtWidgets.QWidget):
    """Semi-transparent overlay with a pulsating icon shown while buttons load."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(QtCore.Qt.WA_TransparentForMouseEvents, False)

        # Load icon once
        from pathlib import Path
        icon_path = Path(__file__).parent / 'bgen_picker_icons' / 'bgen-picker-icon-01.png'
        self._icon_pixmap = QtGui.QPixmap(str(icon_path)).scaled(
            48, 48,
            QtCore.Qt.KeepAspectRatio,
            QtCore.Qt.SmoothTransformation
        )

        # Overlay fade effect — starts fully opaque so loading screen is the
        # default state.  hide_overlay() fades it out once content is ready.
        self._opacity_effect = QtWidgets.QGraphicsOpacityEffect(self)
        self._opacity_effect.setOpacity(1.0)
        self.setGraphicsEffect(self._opacity_effect)

        # Icon pulse opacity (animated property)
        self._icon_opacity = 1.0

        # Pulse animation: breathing cycle 0.3 -> 1.0 -> 0.3
        self._pulse_anim = QPropertyAnimation(self, b"iconOpacity")
        self._pulse_anim.setDuration(800)
        self._pulse_anim.setKeyValueAt(0, 0.3)
        self._pulse_anim.setKeyValueAt(0.5, 1.0)
        self._pulse_anim.setKeyValueAt(1.0, 0.3)
        self._pulse_anim.setEasingCurve(QEasingCurve.InOutSine)
        self._pulse_anim.setLoopCount(-1)

        # Fade-out (the only transition needed — overlay starts visible)
        self._fade_out = QPropertyAnimation(self._opacity_effect, b"opacity")
        self._fade_out.setDuration(200)
        self._fade_out.setStartValue(1.0)
        self._fade_out.setEndValue(0.0)
        self._fade_out.setEasingCurve(QEasingCurve.InCubic)
        self._fade_out.finished.connect(self._on_fade_out_done)

        # Minimum display timer (prevents flicker on fast loads)
        self._min_timer = QTimer(self)
        self._min_timer.setSingleShot(True)
        self._hide_requested = False

        # Start visible with pulse running — this IS the default canvas state.
        self.setVisible(True)
        self._pulse_anim.start()

    # -- Animatable property --
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
            with warnings.catch_warnings():
                warnings.simplefilter("ignore", RuntimeWarning)
                try:
                    self._min_timer.timeout.disconnect(self._do_hide)
                except (RuntimeError, TypeError):
                    pass
            self._min_timer.timeout.connect(self._do_hide)

    def _do_hide(self):
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", RuntimeWarning)
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


class PickerCanvas(QtWidgets.QWidget):
    clicked = Signal()
    button_selection_changed = Signal()
    selection_count_changed = Signal(int)
    view_changed = Signal()  # Emitted when pan/zoom settles (debounced)
    
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
        self.default_border_color = QtGui.QColor(82, 133, 166, 0) #(36, 36, 36, 255)
        self.edit_mode_border_color = QtGui.QColor(29, 101, 202,255)   #(82, 133, 166, 255) blue  (108, 152, 9,255) green
        self.border_color = self.default_border_color
        self.border_width = 1
        self.border_radius = 10

        # Background layer properties (multi-image)
        self.background_layers = []  # list of dicts: {id, image, path, opacity, scale, offset_x, offset_y, visible, locked, name}
        self.selected_layer_id = None
        # Legacy compat aliases
        self.background_image = None
        self.image_opacity = 1.0

        # Canvas transform properties
        self.zoom_factor = 1.0
        self.pan_offset = QtCore.QPointF(0, 0)
        self.last_pan_pos = None

        self.last_zoom_pos = None

        # Debounce timer for view_changed signal (avoids saving on every scroll tick)
        self._view_change_timer = QtCore.QTimer(self)
        self._view_change_timer.setSingleShot(True)
        self._view_change_timer.setInterval(300)
        self._view_change_timer.timeout.connect(self.view_changed.emit)
        self.was_zoom_dragging = False

        # Trackpad vs mouse detection state
        self._scroll_gesture_is_trackpad = False

        # Set when a non-edit-mode button click wants Blender to become
        # the active window — but deferred until the cursor actually
        # leaves the picker so the picker remains the macOS key window
        # while hovered (required for trackpad pinch-zoom NSEvent
        # gestures).
        self._pending_host_activation = False

        # Throttle timer for button position updates during continuous pan/zoom
        self._position_update_timer = QtCore.QTimer(self)
        self._position_update_timer.setSingleShot(True)
        self._position_update_timer.setInterval(16)  # ~60 FPS cap
        self._position_update_timer.timeout.connect(self._throttled_position_update)

        # Persistent throttle timer for transform guides (replaces QTimer.singleShot spam)
        self._guides_update_timer = QtCore.QTimer(self)
        self._guides_update_timer.setSingleShot(True)
        self._guides_update_timer.setInterval(30)  # ~33 FPS cap for guides
        self._guides_update_timer.timeout.connect(self._on_guides_timer)

        # Persistent timer for deferred geometry flush (replaces QTimer.singleShot)
        self._geometry_flush_timer = QtCore.QTimer(self)
        self._geometry_flush_timer.setSingleShot(True)
        self._geometry_flush_timer.setInterval(100)
        self._geometry_flush_timer.timeout.connect(self._flush_deferred_geometry)

        # Cached canvas center (updated in resizeEvent)
        self._canvas_center = QtCore.QPointF(0, 0)

        self.buttons = []
        self.setup_dot_texture()
        
        # Set size policy to allow expanding
        self.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Expanding)

        # Context menus are handled in mousePressEvent and contextMenuEvent
        # prevents propagation to the parent window's frame context menu.
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
        self.pending_placement_data = None

        # Canvas-painted event dispatch: track which button owns the current
        # press→move→release sequence so events are forwarded correctly.
        self._pressed_button = None
        # Deferred widget geometry: during pan/zoom, canvas painting doesn't need
        # widget geometry, so we skip update_button_positions() and just repaint.
        self._geometry_dirty = False

        self.hud = HUDWidget(self)
        self.hud.raise_()

        # Image layer transform handles
        self.image_transform_guides = ImageTransformGuides(self, parent=self)

        # Loading overlay (shown during chunked button creation)
        self.loading_overlay = CanvasLoadingOverlay(self)

        # Save indicator overlay (top-right badge)
        self.save_indicator = SaveIndicatorOverlay(self)

        self.minimal_mode = False
        self.last_selected_button = None

        # Custom tooltip management
        self._tooltip_widget = None
        self._tooltip_timer = QtCore.QTimer(self)
        self._tooltip_timer.setSingleShot(True)
        self._tooltip_timer.timeout.connect(self._show_button_tooltip)
        self._current_hover_button = None
        self._tooltip_position = QtCore.QPoint()
        self._context_menu_open = False

        # Transform guides for edit mode (add after HUD initialization)
        self.transform_guides = TG.TransformGuides(self, self)
        self.transform_guides.transform_finished.connect(self.on_transform_finished)

        # Curve editor overlay for shape editing (in edit mode)
        self.curve_editor = CE.CurveEditorOverlay(self, self)
        self.curve_editor.editingFinished.connect(self._on_curve_editing_finished)
        self.curve_editor.editingCancelled.connect(self._on_curve_editing_cancelled)

        # Interactive duplicate-mirror tool (right-click → Duplicate Mirror in edit mode)
        self.duplicate_mirror_tool = DMT.DuplicateMirrorTool(self)
        
        # Initialize curve import settings
        self._separate_splines_mode = True  # Default to separate splines
        
        # Initialize 2-way selection synchronization
        self._init_selection_sync()
        
        self.canvas_shortcuts()
    
    #------------------------------------------------------------------------------
    # Curve import settings methods
    #------------------------------------------------------------------------------
    def get_separate_splines_mode(self):
        """Get the current spline separation mode"""
        return getattr(self, '_separate_splines_mode', True)
    
    def set_separate_splines_mode(self, separate_splines):
        """Set the spline separation mode"""
        self._separate_splines_mode = separate_splines
        # Show brief feedback
        mode_text = "Separate" if separate_splines else "Combine"
        print(f"Curve import mode set to: {mode_text} splines")
    
    def get_current_coordinate_plane(self):
        """Get the current coordinate plane name"""
        from . import blender_curve_converter as BCC
        return BCC.CoordinatePlaneConfig.get_current_plane()['name']
    
    def set_coordinate_plane(self, plane_name):
        """Set the coordinate plane and provide feedback"""
        from . import blender_curve_converter as BCC
        BCC.CoordinatePlaneConfig.set_plane(plane_name)
        plane_info = BCC.CoordinatePlaneConfig.get_current_plane()
        print(f"Coordinate plane set to: {plane_info['name']} ({plane_info['description']})")
    
    def get_curve_import_settings_summary(self):
        """Get a summary of current curve import settings"""
        plane_name = self.get_current_coordinate_plane()
        mode_text = "Separate" if self.get_separate_splines_mode() else "Combine"
        return f"Plane: {plane_name} | Mode: {mode_text}"
    
    def reset_curve_import_settings(self):
        """Reset curve import settings to defaults"""
        from . import blender_curve_converter as BCC
        BCC.CoordinatePlaneConfig.set_plane('XY')  # Default plane
        self.set_separate_splines_mode(True)  # Default to separate splines
        self.set_auto_detect_plane_mode(True)  # Default to auto-detection enabled
        print("Curve import settings reset to defaults")
    
    def get_auto_detect_plane_mode(self):
        """Get the current auto-detection mode"""
        return getattr(self, '_auto_detect_plane_mode', True)
    
    def set_auto_detect_plane_mode(self, enabled):
        """Set the auto-detection mode"""
        self._auto_detect_plane_mode = enabled
    
    #------------------------------------------------------------------------------
    def set_edit_mode(self, enabled):
        # If the user is leaving edit mode while the duplicate-mirror tool is up,
        # tear it down — its UI (overlay buttons, axis line) is meaningless outside edit mode.
        if not enabled and hasattr(self, 'duplicate_mirror_tool') and self.duplicate_mirror_tool.active:
            self.duplicate_mirror_tool.cancel()

        self.edit_mode = enabled
        self.border_color = self.edit_mode_border_color if enabled else self.default_border_color
        self.border_width = 1 if enabled else 1
        for button in self.buttons:
            button.edit_mode = enabled
            button.update_cursor()
        
        self.update_hud_geometry()

        # Update transform guides
        if hasattr(self, 'transform_guides'):
            if enabled:
                self.transform_guides.update_selection()
                # Ensure guides are above button widgets
                self._raise_overlay_widgets()
            else:
                self.transform_guides.setVisible(False)
                self.transform_guides.visual_layer.setVisible(False)
                if hasattr(self.transform_guides, 'control_widget'):
                    self.transform_guides.control_widget.setVisible(False)

        self.update()

    def update_hud_geometry(self):
        """Size the HUD to avoid overlapping the edit panel."""
        rect = self.rect()
        if self.edit_mode:
            mw = self.window()
            if hasattr(mw, 'canvas_edit_panel') and mw.canvas_edit_panel.isVisible():
                rect.setRight(rect.right() - mw.canvas_edit_panel.width())
        self.hud.setGeometry(rect)

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
        self.delete_button_shortcut.activated.connect(lambda: self._handle_delete_shortcut())

        self.backspace_delete_shortcut = QShortcut(QtGui.QKeySequence("Backspace"), self)
        self.backspace_delete_shortcut.activated.connect(lambda: self._handle_delete_shortcut())
        
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
        from . import blender_curve_converter as BCC
        BCC.create_buttons_from_blender_curves(self, self.get_center_position())

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
        """Handle transform guide operations completion with optimized updates"""
        selected_buttons = self.get_selected_buttons()
        main_window = self.window()
        
        if hasattr(main_window, 'batch_update_buttons_to_database'):
            main_window.batch_update_buttons_to_database(selected_buttons)
        self.update_button_positions()
        self.update()

    def update_transform_guides(self):
        """Update transform guides when selection or edit mode changes"""
        if hasattr(self, 'transform_guides'):
            self.transform_guides.update_selection()

    def _update_transform_guides_position(self):
        """Helper method to update transform guides position"""
        if hasattr(self, 'transform_guides') and self.transform_guides.isVisible():
            self.transform_guides.calculate_bounding_rect()
            self.transform_guides.update_position()
            # Also update the controls widget position
            if hasattr(self.transform_guides, 'controls_widget'):  # Add these 2 lines
                self.transform_guides.controls_widget.update_position()
    
    def hide_transform_guides(self):
        """Hide transform guides"""
        if hasattr(self, 'transform_guides'):
            self.transform_guides.setVisible(False)
            self.transform_guides.visual_layer.setVisible(False)

            if hasattr(self.transform_guides, 'controls_widget'):  
                self.transform_guides.controls_widget.setVisible(False)

    #------------------------------------------------------------------------------
    # Curve Editor Methods
    #------------------------------------------------------------------------------
    def start_curve_editing(self, button):
        """
        Start curve editing for a button.
        
        Args:
            button: The PickerButton to edit the shape of
        """
        if not self.edit_mode or not button:
            return
        
        # Save undo state BEFORE starting curve editing
        # This allows undoing the entire curve edit session
        main_window = self.window()
        if hasattr(main_window, 'tab_system'):
            from . import data_management as DM
            DM.PickerDataManager.save_undo_state(
                operation_name="Start Curve Editing",
                selected_button_ids=[button.unique_id]
            )
        
        # Hide transform guides while editing curves
        self.hide_transform_guides()

        # Deselect other buttons
        self.clear_selection()
        button.update_visual_state(True)

        # Start curve editor
        self.curve_editor.start_editing(button)
    
    def start_new_shape_drawing(self, button):
        """
        Start drawing a new custom shape for a button.
        
        Args:
            button: The PickerButton to create a new shape for
        """
        if not self.edit_mode or not button:
            return
        
        # Save undo state BEFORE starting curve editing
        main_window = self.window()
        if hasattr(main_window, 'tab_system'):
            from . import data_management as DM
            DM.PickerDataManager.save_undo_state(
                operation_name="Start New Shape Drawing",
                selected_button_ids=[button.unique_id]
            )
        
        # Hide transform guides while editing curves
        self.hide_transform_guides()

        # Deselect other buttons, select the target button
        self.clear_selection()
        button.update_visual_state(True)

        # Start curve editor with empty shape
        self.curve_editor.start_editing(button, existing_shape=CE.ButtonShape())
    
    def start_drawing_new_button_shape(self, position):
        """
        Create a new button and start drawing a custom shape for it.
        Called from canvas context menu.
        
        Args:
            position: Click position on canvas
        """
        if not self.edit_mode:
            return
        
        # Create a new button at this position
        scene_pos = self.canvas_to_scene_coords(QtCore.QPointF(position))
        
        main_window = self.window()
        if not isinstance(main_window, UI.BlenderAnimPickerWindow):
            return
        
        current_tab = main_window.tab_system.current_tab
        unique_id = main_window.generate_unique_id(current_tab)
        
        # Create button with default properties
        new_button = PB.PickerButton("Button", self, unique_id=unique_id)
        new_button.scene_position = scene_pos
        
        # Properly add button using add_button() for signal connections
        self.add_button(new_button)
        
        # Save the button immediately to database so it persists even if shape drawing is cancelled
        self.update_button_data(new_button)
        
        # Start drawing the shape for this new button
        self.start_new_shape_drawing(new_button)
    
    def _on_curve_editing_finished(self, svg_path_data):
        """Handle completion of curve editing."""
        if self.curve_editor.target_button:
            button = self.curve_editor.target_button

            # Apply the new shape to the button
            if svg_path_data:
                button.shape_type = 'custom_path'
                button.svg_path_data = svg_path_data

                # Update button widget position (scene_position may have changed)
                self.update_button_positions()
                button.update()  # Trigger repaint with new shape

            # Save button data to database (both new and edited buttons)
            # Note: undo state was already captured in start_curve_editing() before
            # the edit began. update_button_data -> update_tab_data also captures
            # pre-edit state internally. No extra save_undo_state needed here.
            self.update_button_data(button)

            # Select the button and show transform guides
            if self.edit_mode:
                self.clear_selection()
                button.is_selected = True
                # Invalidate selection cache so get_selected_buttons() sees the change
                if hasattr(self, '_cache_valid'):
                    self._cache_valid = False
                button.selected.emit(button, True)
                button.update()
                # Explicitly show and update transform guides
                if hasattr(self, 'transform_guides'):
                    self.transform_guides.setVisible(True)
                    self.transform_guides.visual_layer.setVisible(True)
                    self.transform_guides.update_selection()
    
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
    
    def is_curve_editing(self) -> bool:
        """Check if curve editing is currently active."""
        return hasattr(self, 'curve_editor') and self.curve_editor.is_editing()
    
    def _handle_delete_shortcut(self):
        """Handle delete shortcut - delegate to curve editor if active."""
        if self.is_curve_editing():
            # Let curve editor handle deletion of selected points
            from PySide6.QtCore import Qt
            self.curve_editor.keyPressEvent(
                QtGui.QKeyEvent(QtCore.QEvent.KeyPress, Qt.Key_Delete, Qt.NoModifier)
            )
        else:
            # Normal button deletion
            self.delete_selected_buttons()

    #------------------------------------------------------------------------------

    def _schedule_view_changed(self):
        """Restart the debounce timer so view_changed fires once after activity stops."""
        self._view_change_timer.start()

    def update_pan_offset(self, delta):
        """Simplified pan offset update"""
        self.pan_offset += QtCore.QPointF(delta.x(), delta.y())

        # Throttled transform guides update (persistent timer prevents accumulation)
        self._request_guides_update()
    
    def _raise_overlay_widgets(self):
        """Raise overlay widgets (guides, HUD, loading) above button widgets.

        Button QWidgets added via add_button/add_buttons_batch sit above the
        overlays in the default child stacking order.  Even though buttons are
        fully transparent (WA_TranslucentBackground + empty paintEvent), on some
        Qt backends they still occlude sibling widgets below them.  Call this
        after adding buttons to restore correct z-order.
        """
        if hasattr(self, 'transform_guides'):
            self.transform_guides.visual_layer.raise_()
            self.transform_guides.controls_widget.raise_()
            self.transform_guides.raise_()
        if hasattr(self, 'curve_editor'):
            self.curve_editor.raise_()
        if hasattr(self, 'hud'):
            self.hud.raise_()
        if hasattr(self, 'loading_overlay'):
            self.loading_overlay.raise_()

    def _request_guides_update(self):
        """Schedule a throttled transform guides position update."""
        if (hasattr(self, 'transform_guides') and
                self.transform_guides.isVisible() and self.edit_mode):
            if not self._guides_update_timer.isActive():
                self._guides_update_timer.start()

    def _on_guides_timer(self):
        """Persistent timer callback for transform guides update."""
        self._update_transform_guides_position()

    def _update_guides_after_button_change(self):
        """Update transform guides after button changes"""
        if hasattr(self, 'transform_guides') and self.edit_mode:
            self._request_guides_update()
    
    def connect_button_signals(self, button):
        """Connect button signals for real-time transform guide updates"""
        button.deleted.connect(self.remove_button)
        button.selected.connect(self.on_button_selected)
        button.changed.connect(self.on_button_changed)
        
        # CRITICAL FIX: Connect to position changes for transform guides
        if hasattr(button, 'position_changed'):
            button.position_changed.connect(self._update_transform_guides_position)
    #------------------------------------------------------------------------------
    def select_buttons_in_rect(self, rect, add_to_selection=False):
        # If not adding to selection and not in shift mode, clear existing selection
        if not add_to_selection:
            self.clear_selection()

        selection_changed = False
        for button in self.buttons:
            # Skip buttons that are not selectable in select mode
            if not self.edit_mode and hasattr(button, 'selectable') and not button.selectable:
                continue
                
            button_rect = button.geometry()
            if rect.intersects(button_rect):
                if not button.is_selected:
                    button.is_selected = True
                    selection_changed = True

        if selection_changed:
            self.button_selection_changed.emit()
            self.update_hud_counts()

    def update_visual_selection(self, rect, add_to_selection=False, remove_from_selection=False):
        """Update button selection visually during rubber band drag with shape awareness"""
        # Throttle to ~60 FPS — skip intermediate updates during fast mouse movement
        current_time = QtCore.QTime.currentTime().msecsSinceStartOfDay()
        if hasattr(self, '_last_visual_selection_update'):
            if current_time - self._last_visual_selection_update < 16:
                return
        self._last_visual_selection_update = current_time

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
            env_w, env_h = button.rotated_envelope_size()
            envelope_rect = QtCore.QRectF(
                button_pos.x() - env_w / 2,
                button_pos.y() - env_h / 2,
                env_w,
                env_h
            )
            if not scene_rect.intersects(envelope_rect):
                continue

            # Exact shape-vs-rect intersection (matches visible shape, incl. rotation)
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
            if button.rotation:
                transform.rotate(button.rotation)
            scene_button_path = transform.map(button_path)

            selection_path = QtGui.QPainterPath()
            selection_path.addRect(scene_rect)

            return scene_button_path.intersects(selection_path)

        except Exception as e:
            print(f"Error checking button shape intersection: {e}")
            button_pos = button.scene_position
            env_w, env_h = button.rotated_envelope_size()
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
        if not self._current_hover_button or self._context_menu_open:
            return
        
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
        # Don't update hover or start tooltip timer while a context menu is open
        if self._context_menu_open:
            return

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
    def apply_final_selection(self, add_to_selection=False, ctrl_held=False):
        """Apply final selection with sync manager integration"""
        if self.edit_mode:
            return

        # Temporarily disable sync to prevent loops when we apply Blender selection
        try:
            manager = SSM.SelectionSyncManager.get_instance()
            manager._sync_lock = True
        except:
            pass

        try:
            # Get buttons that should be selected
            if hasattr(self, 'buttons_in_current_drag') and self.buttons_in_current_drag:
                # Use ordered selection for rubber band
                final_selections = self._get_ordered_selections(add_to_selection)
            else:
                # Use current selection (for single clicks) - maintain last selected button
                final_selections = [button for button in self.buttons if button.is_selected]

                # For single clicks, ensure proper ordering with last clicked button
                if hasattr(self, 'last_clicked_button') and self.last_clicked_button and self.last_clicked_button.is_selected:
                    if self.last_clicked_button in final_selections:
                        final_selections.remove(self.last_clicked_button)
                        final_selections.append(self.last_clicked_button)

            if not final_selections:
                # If no buttons selected, clear Blender selection
                try:
                    import bpy
                    with bpy.context.temp_override(window=bpy.context.window_manager.windows[0]):
                        if bpy.context.mode == 'POSE':
                            bpy.ops.pose.select_all(action='DESELECT')
                        elif bpy.context.mode == 'OBJECT':
                            bpy.ops.object.select_all(action='DESELECT')
                except:
                    pass
                return

            # Check if we should select counterparts
            if ctrl_held:
                # Select counterparts for all selected buttons
                resolved_items, missing_objects = self._resolve_counterpart_items(final_selections)
            else:
                # Regular selection - resolve objects and bones from button data
                resolved_items, missing_objects = self._resolve_selection_items(final_selections)

            # Switch to pose mode if bones are being selected
            if resolved_items['bones']:
                self._enter_pose_mode_for_bones(resolved_items['bones'])

            # Apply selection in Blender with proper active item
            self._apply_blender_selection(resolved_items, add_to_selection, final_selections[-1] if final_selections else None)

            # Handle UI updates
            self._handle_post_selection_updates(missing_objects)
            import bpy
            with bpy.context.temp_override(window=bpy.context.window_manager.windows[0]):
                bpy.ops.ed.undo_push(message="Select Object")
        finally:
            # Release sync lock immediately — Blender ops above are synchronous,
            # so the selection state is already committed by this point.
            try:
                manager = SSM.SelectionSyncManager.get_instance()
                manager._sync_lock = False
            except:
                pass

            # bpy.ops above causes Blender's GHOST to grab macOS key window.
            # That's actually what we want here — Blender should own the
            # keyboard after a selection so user shortcuts (G/R/S, frame
            # nav, etc) work in the viewport without manually clicking it.
            # Trackpad pinch-zoom on the picker after a click won't work
            # via NSEvent magnify gesture as a result (gestures route to
            # Blender), but two-finger pan still works (delivered by
            # cursor position) and Ctrl+two-finger-scroll provides zoom
            # via the wheelEvent path.
            try:
                from . import utils as UT
                UT.blender_main_window()
            except Exception:
                pass

    def _get_ordered_selections(self, add_to_selection):
        """Build ordered list of buttons to select based on drag operation"""
        final_selections = []
        
        # For rubber band selection, we need to determine the last selected button differently
        # Since buttons_in_current_drag is a set, we can't rely on iteration order
        
        # Add previously selected buttons if adding to selection
        if add_to_selection:
            for button in self.buttons:
                if button.is_selected and button not in self.buttons_in_current_drag:
                    final_selections.append(button)
        
        # Add buttons from current drag operation
        # Since we can't determine the exact order from the set, we'll add them in a consistent order
        # and rely on the last mouse interaction to determine the active button
        current_drag_buttons = []
        for button in self.buttons_in_current_drag:
            if button.is_selected:
                current_drag_buttons.append(button)
        
        # Sort by some consistent criteria (e.g., position) to ensure predictable ordering
        current_drag_buttons.sort(key=lambda b: (b.scene_position.y(), b.scene_position.x()))
        
        # Add all current drag buttons except the one we'll designate as "last"
        if len(current_drag_buttons) > 1:
            final_selections.extend(current_drag_buttons[:-1])
        
        # Add the last button from current drag (or the only one if there's just one)
        if current_drag_buttons:
            # For rubber band selection, use the last button in our sorted list
            # For single button selection, this will be the clicked button
            final_selections.append(current_drag_buttons[-1])
        
        return final_selections

    def _resolve_selection_items(self, buttons):
        """Resolve button objects to Blender objects/bones"""
        resolved_items = {'bones': [], 'objects': []}
        missing_objects = set()
        
        # Get current namespace for object resolution
        current_namespace = self._get_current_namespace()
        
        for button in buttons:
            if not button.assigned_objects:
                continue
                
            for obj_data in button.assigned_objects:
                try:
                    if obj_data.get('is_bone', False):
                        bone_info = self._resolve_bone(obj_data)
                        if bone_info:
                            resolved_items['bones'].append(bone_info)
                        else:
                            missing_objects.add(self._format_missing_bone(obj_data))
                    else:
                        obj_info = self._resolve_object(obj_data, current_namespace)
                        if obj_info:
                            resolved_items['objects'].append(obj_info)
                        else:
                            missing_objects.add(self._format_missing_object(obj_data))
                except Exception as e:
                    print(f"Error resolving selection item: {e}")
                    continue
        
        return resolved_items, missing_objects

    def _resolve_bone_with_namespace(self, obj_data, current_namespace):
        """Resolve bone data to Blender bone reference with namespace priority"""
        import bpy
        with bpy.context.temp_override(window=bpy.context.window_manager.windows[0]):
            bone_name = obj_data.get('name', '')
            original_armature_name = obj_data.get('armature', '')
            
            # Priority 1: Try with current namespace if one is selected
            if current_namespace and current_namespace != 'None':
                if (current_namespace in bpy.data.objects and 
                    bpy.data.objects[current_namespace].type == 'ARMATURE' and
                    bone_name in bpy.data.objects[current_namespace].pose.bones):
                    return {
                        'armature': current_namespace,
                        'bone': bone_name
                    }
            
            # Priority 2: Try with original armature (fallback)
            if (original_armature_name in bpy.data.objects and 
                bpy.data.objects[original_armature_name].type == 'ARMATURE' and
                bone_name in bpy.data.objects[original_armature_name].pose.bones):
                return {
                    'armature': original_armature_name,
                    'bone': bone_name
                }
            
            # Priority 3: Search all armatures for the bone name
            for obj in bpy.context.scene.objects:
                if (obj.type == 'ARMATURE' and obj.pose and 
                    bone_name in obj.pose.bones):
                    return {
                        'armature': obj.name,
                        'bone': bone_name
                    }
        
        return None

    def _resolve_bone(self, obj_data):
        """Updated resolve bone method that uses namespace priority"""
        current_namespace = self._get_current_namespace()
        return self._resolve_bone_with_namespace(obj_data, current_namespace)

    def _resolve_object(self, obj_data, current_namespace):
        """Resolve object data to Blender object reference"""
        import bpy
        
        obj_name = obj_data.get('name', '')
        
        # Try direct name match first
        if obj_name in bpy.data.objects:
            return {'name': obj_name}
        
        # Try with namespace prefix
        if current_namespace and current_namespace != 'None':
            namespaced_name = f"{current_namespace}_{obj_name}"
            if namespaced_name in bpy.data.objects:
                return {'name': namespaced_name}
        
        return None

    def _apply_blender_selection(self, resolved_items, add_to_selection, last_selected_button=None):
        """Apply the actual selection in Blender"""
        import bpy
        
        bones = resolved_items['bones']
        objects = resolved_items['objects']
        
        # Find the active item from the last selected button
        active_bone_info = None
        active_object_info = None
        
        if last_selected_button and last_selected_button.assigned_objects:
            for obj_data in last_selected_button.assigned_objects:
                if obj_data.get('is_bone', False):
                    # Find this bone in our resolved bones
                    bone_name = obj_data.get('name', '')
                    for bone_info in bones:
                        if bone_info['bone'] == bone_name:
                            active_bone_info = bone_info
                            break
                else:
                    # Find this object in our resolved objects
                    obj_name = obj_data.get('name', '')
                    for obj_info in objects:
                        if obj_info['name'] == obj_name or obj_info['name'].endswith(f"_{obj_name}"):
                            active_object_info = obj_info
                            break
        
        try:
            if bones:
                self._select_bones_with_namespace(bones, add_to_selection, active_bone_info)
            
            if objects:
                self._select_objects(objects, add_to_selection, has_bones=bool(bones), active_object_info=active_object_info)
                
        except Exception as e:
            print(f"Error during Blender selection: {e}")

    def _deselect_bones(self, armature_name):
        """Deselect all bones in an armature - OPTIMIZED VERSION"""
        try:
            if armature_name not in bpy.data.objects:
                return []
            
            armature_obj = bpy.data.objects[armature_name]
            if armature_obj.type != 'ARMATURE' or not armature_obj.data:
                return []
            
            # Get all bone names
            bone_names = [bone.name for bone in armature_obj.data.bones]
            
            # Deselect all bones at once using version-compatible function
            from . import utils as UT
            for bone_name in bone_names:
                if bone_name in armature_obj.pose.bones:
                    UT.set_bone_selected(armature_obj.pose.bones[bone_name], False)
            
            return bone_names
            
        except Exception as e:
            print(f"Error deselecting bones in armature {armature_name}: {e}")
            return []

    # add SoP
    def __ensure_bone_collections_visible(self, armature, bone_name):
        """
        From a given bone in a given armature:
        - Check if all its bone collections are hidden.
        - If they are all hidden, make the first one visible.
        - Ensure all parent bone collections of the newly visible one are visible too.
        """

        if armature.type != 'ARMATURE':
            print(f"Object {armature.name} is not an armature.")
            return

        arm = armature.data
        bone = arm.bones.get(bone_name)
        if not bone:
            print(f"Bone '{bone_name}' not found in armature '{armature.name}'.")
            return

        bone_colls = bone.collections
        if not bone_colls:
            print(f"Bone '{bone_name}' is not in any bone collection.")
            return

        # --- Step 1: if all hidden, make the first one visible
        all_hidden = all(not coll.is_visible for coll in bone_colls)
        if all_hidden:
            target_coll = bone_colls[0]
            target_coll.is_visible = True
            print(f"Made bone collection '{target_coll.name}' visible for '{bone_name}'.")

        # --- Step 2: ensure all parent collections (for all bone collections) are visible
        for coll in bone_colls:
            parent = coll.parent
            while parent:
                if not parent.is_visible:
                    parent.is_visible = True
                    print(f"Made parent collection '{parent.name}' visible (due to '{bone_name}').")
                parent = parent.parent

    def _select_bones_with_namespace(self, bones, add_to_selection, active_bone_info=None):
        """Updated bone selection with namespace priority and proper active bone"""
        if not bones:
            return
        
        # Get current namespace
        current_namespace = self._get_current_namespace()
        
        selected_bones = []
        armatures_processed = set()
        
        # Group bones by target armature (considering namespace)
        armature_bones = {}
        for bone_info in bones:
            original_armature = bone_info['armature']
            bone_name = bone_info['bone']
            
            # Determine target armature with namespace priority
            target_armature = None
            
            # Priority 1: Current namespace if available
            if (current_namespace and current_namespace != 'None' and 
                current_namespace in bpy.data.objects and
                bpy.data.objects[current_namespace].type == 'ARMATURE' and
                bone_name in bpy.data.objects[current_namespace].pose.bones):
                target_armature = current_namespace
            
            # Priority 2: Original armature (fallback)
            elif (original_armature in bpy.data.objects and 
                bpy.data.objects[original_armature].type == 'ARMATURE' and
                bone_name in bpy.data.objects[original_armature].pose.bones):
                target_armature = original_armature
            
            # Priority 3: Search all armatures
            else:
                for obj in bpy.context.scene.objects:
                    if (obj.type == 'ARMATURE' and obj.pose and 
                        bone_name in obj.pose.bones):
                        target_armature = obj.name
                        break
            
            if target_armature:
                if target_armature not in armature_bones:
                    armature_bones[target_armature] = []
                armature_bones[target_armature].append(bone_name)
            else:
                print(f"Warning: Bone '{bone_name}' not found in any armature")
        
        # Clear bone selections once per armature (only if not adding to selection)
        if not add_to_selection:
            for armature_name in armature_bones.keys():
                self._deselect_bones(armature_name)
        
        # Select all the bones by armature
        active_bone_set = False
        from . import utils as UT
        for armature_name, bone_names in armature_bones.items():
            try:
                armature_obj = bpy.data.objects[armature_name]
                
                for bone_name in bone_names:
                    if bone_name in armature_obj.pose.bones:
                        pose_bone = armature_obj.pose.bones[bone_name]
                        UT.set_bone_selected(pose_bone, True)
                        selected_bones.append(f"{bone_name} (in {armature_name})")
                        
                        # Ensure bone collections are visible when selecting
                        self.__ensure_bone_collections_visible(armature_obj, bone_name)

                        # Set as active if this is the active bone or if no active bone specified and not set yet
                        if ((active_bone_info and 
                            active_bone_info['bone'] == bone_name and 
                            active_bone_info['armature'] == armature_name) or
                            (not active_bone_info and not active_bone_set)):
                            armature_obj.data.bones.active = pose_bone.bone
                            active_bone_set = True
                            
            except Exception as e:
                print(f"Error selecting bones in armature {armature_name}: {e}")
                continue
        
        if selected_bones:
            #print(f"Selected bones: {', '.join(selected_bones)}")
            pass
        else:
            print("No bones were selected")
    
    def _enter_pose_mode_for_bones(self, bones):
        """Switch to pose mode for the armature containing the selected bones"""
        import bpy
        
        if not bones:
            return
        
        try:
            with bpy.context.temp_override(window=bpy.context.window_manager.windows[0]):
                # Get the first armature from the bone selection
                first_bone = bones[0]
                armature_name = first_bone['armature']
                
                if armature_name not in bpy.data.objects:
                    print(f"Warning: Armature '{armature_name}' not found")
                    return
                
                armature_obj = bpy.data.objects[armature_name]
                
                # First, ensure we're in object mode to properly set the active object
                if bpy.context.mode != 'OBJECT':
                    try:
                        bpy.ops.object.mode_set(mode='OBJECT')
                    except RuntimeError:
                        # If we can't switch to object mode, clear selections manually
                        pass
                
                # Clear all object selections using direct API instead of operators
                for obj in bpy.context.scene.objects:
                    obj.select_set(False)
                
                # Set the armature as the active and selected object
                bpy.context.view_layer.objects.active = armature_obj
                armature_obj.select_set(True)
                
                # Now switch to pose mode
                if bpy.context.mode != 'POSE':
                    try:
                        bpy.ops.object.mode_set(mode='POSE')
                    except RuntimeError as e:
                        print(f"Failed to switch to pose mode: {e}")
                        return
                
                # Clear any existing pose bone selections
                if bpy.context.mode == 'POSE' and armature_obj.pose:
                    from . import utils as UT
                    for pose_bone in armature_obj.pose.bones:
                        UT.set_bone_selected(pose_bone, False)
                
                #print(f"Successfully switched to pose mode for armature: {armature_name}")
            
        except Exception as e:
            print(f"Error entering pose mode for bones: {e}")
            # Fallback: try without temp_override
            try:
                with bpy.context.temp_override(window=bpy.context.window_manager.windows[0]):
                    # Get the first armature from the bone selection
                    first_bone = bones[0]
                    armature_name = first_bone['armature']
                    
                    if armature_name not in bpy.data.objects:
                        return
                    
                    armature_obj = bpy.data.objects[armature_name]
                    
                    # Simple approach without operators that might fail
                    # Clear selections using direct API
                    for obj in bpy.context.scene.objects:
                        obj.select_set(False)
                    
                    # Set active object
                    bpy.context.view_layer.objects.active = armature_obj
                    armature_obj.select_set(True)
                    
                    # Try to switch mode
                    if bpy.context.active_object == armature_obj and armature_obj.type == 'ARMATURE':
                        if bpy.context.mode != 'POSE':
                            bpy.ops.object.mode_set(mode='POSE')
                            
                        #print(f"Fallback: Successfully switched to pose mode for armature: {armature_name}")
            except Exception as fallback_error:
                print(f"Fallback also failed: {fallback_error}")
        
    def _get_selected_bones(self):
        """Get currently selected bones in pose mode"""
        pass

    def _select_objects(self, objects, add_to_selection, has_bones=False, active_object_info=None):
        """Select regular objects with proper active object"""
        import bpy
        
        # Only switch to object mode if we don't have bones selected
        if not has_bones and bpy.context.mode != 'OBJECT':
            bpy.ops.object.mode_set(mode='OBJECT')
        
        # Clear object selection if not adding and no bones
        if not add_to_selection and not has_bones:
            bpy.ops.object.select_all(action='DESELECT')
        
        selected_objects = []
        active_object_set = False
        
        for obj_info in objects:
            obj_name = obj_info['name']
            if obj_name in bpy.data.objects:
                bpy.data.objects[obj_name].select_set(True)
                selected_objects.append(obj_name)
                
                # Set as active if this is the active object or if no active object specified and not set yet
                if not has_bones:  # Only set active object if no bones are selected
                    if ((active_object_info and active_object_info['name'] == obj_name) or
                        (not active_object_info and not active_object_set)):
                        bpy.context.view_layer.objects.active = bpy.data.objects[obj_name]
                        active_object_set = True
        
        #print(f"Selected objects: {', '.join(selected_objects)}")

    def _get_current_namespace(self):
        """Get current namespace from main window"""
        main_window = self.window()
        if hasattr(main_window, 'namespace_dropdown'):
            return main_window.namespace_dropdown.currentText()
        return None

    def _get_item_id(self, obj_data):
        """Get unique identifier for an object/bone"""
        if obj_data.get('is_bone', False):
            return f"{obj_data.get('armature', '')}|{obj_data.get('name', '')}"
        return obj_data.get('name', '')

    def _format_missing_bone(self, obj_data):
        """Format missing bone message"""
        bone_name = obj_data.get('name', '')
        armature_name = obj_data.get('armature', '')
        return f"- {bone_name} (in {armature_name})"

    def _format_missing_object(self, obj_data):
        """Format missing object message"""
        obj_name = obj_data.get('name', '')
        return f"- {obj_name}"

    def _handle_post_selection_updates(self, missing_objects):
        """Handle UI updates after selection"""
        # Show missing objects dialog
        if missing_objects:
            self._show_missing_objects_dialog(missing_objects)
        
        # Update button visuals
        for button in self.buttons:
            button.update()
            button.update_tooltip()
        
        # Emit signals
        self.button_selection_changed.emit()
        self.update_hud_counts()

    def _show_missing_objects_dialog(self, missing_objects):
        """Show dialog for missing objects"""
        '''parent_widget = self.parentWidget()
        dialog = CD.CustomDialog(parent_widget, title="Missing Objects", size=(250, -1), info_box=True)
        message_label = QtWidgets.QLabel("The following objects were not found:")
        details_label = QtWidgets.QLabel('\n'.join(sorted(f"<b><font color='#00ade6'>{objects}</font></b>" for objects in missing_objects)))
        note_label = QtWidgets.QLabel("[Objects may have been deleted or renamed]")
        
        dialog.add_widget(message_label)
        dialog.add_widget(details_label)
        dialog.add_widget(note_label)
        dialog.add_button_box()
        dialog.exec_()'''
        message_txt = "The following objects were not found:"
        details_txt = '\n'.join(sorted(objects for objects in missing_objects))
        note_txt = "[Objects may have been deleted or renamed]"
        print(message_txt)
        print(details_txt)
        print(note_txt)
    #------------------------------------------------------------------------------
    def _resolve_counterpart_items(self, buttons):
        """Resolve counterpart objects/bones for selected buttons"""
        resolved_items = {'bones': [], 'objects': []}
        missing_objects = set()
        
        # Get current namespace for object resolution
        current_namespace = self._get_current_namespace()
        
        # Get naming conventions and mirror preferences
        naming_conventions = self._get_naming_conventions("", "")
        
        for button in buttons:
            if not button.assigned_objects:
                continue
                
            for obj_data in button.assigned_objects:
                try:
                    if obj_data.get('is_bone', False):
                        counterpart_bone = self._resolve_bone_counterpart(obj_data, naming_conventions, current_namespace)
                        if counterpart_bone:
                            resolved_items['bones'].append(counterpart_bone)
                        else:
                            missing_objects.add(f"- {obj_data.get('name', '')} (bone counterpart)")
                    else:
                        counterpart_obj = self._resolve_object_counterpart(obj_data, naming_conventions, current_namespace)
                        if counterpart_obj:
                            resolved_items['objects'].append(counterpart_obj)
                        else:
                            missing_objects.add(f"- {obj_data.get('name', '')} (object counterpart)")
                except Exception as e:
                    print(f"Error resolving counterpart item: {e}")
                    continue
        
        return resolved_items, missing_objects

    def _resolve_bone_counterpart(self, obj_data, naming_conventions, current_namespace):
        """Resolve bone counterpart using naming conventions"""
        import bpy
        
        bone_name = obj_data.get('name', '')
        original_armature_name = obj_data.get('armature', '')
        
        # Find the mirrored bone name
        mirrored_bone_name, is_center_bone = self._find_mirrored_name(bone_name, naming_conventions)
        
        # If it's the same name (center bone), return the original
        if mirrored_bone_name == bone_name:
            return self._resolve_bone_with_namespace(obj_data, current_namespace)
        
        # Create counterpart bone data
        counterpart_data = {
            'name': mirrored_bone_name,
            'armature': original_armature_name,
            'is_bone': True
        }
        
        # Try to resolve the counterpart bone
        return self._resolve_bone_with_namespace(counterpart_data, current_namespace)

    def _resolve_object_counterpart(self, obj_data, naming_conventions, current_namespace):
        """Resolve object counterpart using naming conventions"""
        import bpy
        
        obj_name = obj_data.get('name', '')
        
        # Find the mirrored object name
        mirrored_obj_name, is_center_object = self._find_mirrored_name(obj_name, naming_conventions)
        
        # If it's the same name (center object), return the original
        if mirrored_obj_name == obj_name:
            return self._resolve_object(obj_data, current_namespace)
        
        # Create counterpart object data
        counterpart_data = {
            'name': mirrored_obj_name,
            'is_bone': False
        }
        
        # Try to resolve the counterpart object
        return self._resolve_object(counterpart_data, current_namespace)

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
            {"left": ".L", "right": ".R"},  # Blender bone naming convention
            {"left": ".l", "right": ".r"},  # Blender bone naming convention
            
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

    def _find_mirrored_name(self, obj_name, naming_conventions):
        """
        Finds the mirrored name for the given object/bone name.
        
        Args:
            obj_name (str): Object/bone name to find mirror for
            naming_conventions (list): List of naming conventions
            
        Returns:
            tuple: (mirrored_name, is_center_object) where mirrored_name is the name of the mirrored object/bone
                and is_center_object is a boolean indicating if the object is a center object
        """
        is_center_object = True  # Assume it's a center object until proven otherwise
        
        for convention in naming_conventions:
            left_pattern = convention["left"]
            right_pattern = convention["right"]
            
            if left_pattern in obj_name:
                is_center_object = False
                mirrored_name = obj_name.replace(left_pattern, right_pattern)
                return mirrored_name, is_center_object
            elif right_pattern in obj_name:
                is_center_object = False
                mirrored_name = obj_name.replace(right_pattern, left_pattern)
                return mirrored_name, is_center_object
        
        # If no pattern matched, it's a center object - return the same name
        return obj_name, is_center_object
    #------------------------------------------------------------------------------
    def get_selected_buttons(self):
        """Cached version of get_selected_buttons for better performance"""
        if not hasattr(self, '_selected_buttons_cache'):
            self._selected_buttons_cache = []
            self._cache_valid = False
        
        if not self._cache_valid:
            self._selected_buttons_cache = [button for button in self.buttons if button.is_selected]
            self._cache_valid = True
        
        return self._selected_buttons_cache

    def clear_selection(self):
        """Clear button selection efficiently"""
        selection_changed = False
        for button in self.buttons:
            if button.is_selected:
                button.is_selected = False
                button.update()
                selection_changed = True
        
        if selection_changed:
            # Invalidate cache
            if hasattr(self, '_cache_valid'):
                self._cache_valid = False
            self.button_selection_changed.emit()
            self.update_hud_counts()

            if hasattr(self, 'transform_guides'):
                self.transform_guides.setVisible(False)
                self.transform_guides.visual_layer.setVisible(False)
                # Also hide the controls widget when clearing selection
                if hasattr(self.transform_guides, 'controls_widget'): 
                    self.transform_guides.controls_widget.setVisible(False)

    def on_button_selected(self, button, is_selected):
        """Optimized button selection handler"""
        # Invalidate selection cache
        if hasattr(self, '_cache_valid'):
            self._cache_valid = False
        
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
        """Get the topmost visible button at the given position, respecting button shapes.

        In canvas-painted mode, uses scene-space hit testing (same path as
        paint_on_canvas) so the clickable area matches the visible shape exactly.
        Non-selectable buttons are skipped in select mode so that clicks and
        hovers fall through to the next button underneath.
        """
        # Convert canvas position to scene coordinates once
        scene_pos = self.canvas_to_scene_coords(QtCore.QPointF(pos))

        # Check buttons in reverse order (topmost first due to z-order)
        for button in reversed(self.buttons):
            if not button.isVisible():
                continue

            # In select mode, skip non-selectable buttons so they are
            # transparent to clicks and hover (fall through to buttons below)
            if not self.edit_mode and not button.selectable:
                continue

            if button._canvas_painted:
                # Fast bounding-box pre-check in scene space
                w, h = button.width, button.height
                env_w, env_h = button.rotated_envelope_size()
                bp = button.scene_position
                if (abs(scene_pos.x() - bp.x()) > env_w / 2 or
                        abs(scene_pos.y() - bp.y()) > env_h / 2):
                    continue
                # Exact shape test in scene space
                if button.hit_test_scene(scene_pos):
                    return button
            else:
                # Legacy widget-based hit testing
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
        self._request_guides_update()
    #------------------------------------------------------------------------------
    # BUTTON MANAGEMENT
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
        # Canvas-painted mode: rendering on canvas, events dispatched by canvas
        button._canvas_painted = True
        button.setAttribute(QtCore.Qt.WA_TranslucentBackground, True)
        button.setAttribute(QtCore.Qt.WA_TransparentForMouseEvents, True)
        button.clearMask()
        # Lower button widget below overlays so it doesn't occlude guides/HUD
        button.lower()
        self.update_button_positions()

        # Update HUD button count
        self.update_hud_counts()
        self._update_guides_after_button_change()

        # Ensure overlays remain above button widgets
        self._raise_overlay_widgets()

        # Rebuild selection sync lookup for performance
        SSM.rebuild_canvas_lookup(self)

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
            # Ensure overlays remain above button widgets
            self._raise_overlay_widgets()
            SSM.rebuild_canvas_lookup(self)

    def remove_button(self, button):
        if button in self.buttons:
            # Clear hover button reference if this button is the current hover button
            if self._current_hover_button == button:
                self._hide_button_tooltip()
            
            self.buttons.remove(button)
            self.update_button_positions()
            main_window = self.window()
            if isinstance(main_window, UI.BlenderAnimPickerWindow):
                main_window.update_button_data(button, deleted=True)
            
            # Update HUD button count
            self.update_hud_counts()
            
            # Rebuild selection sync lookup for performance
            SSM.rebuild_canvas_lookup(self)
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
            # Update hover now that geometry is current
            self._update_hover_button(self.mapFromGlobal(QtGui.QCursor.pos()))

    def request_button_position_update(self):
        """Throttled version — call during continuous pan/zoom instead of update_button_positions().
        Caps at ~60 FPS to avoid redundant geometry passes on fast mouse moves."""
        if not self._position_update_timer.isActive():
            self._position_update_timer.start()

    def _throttled_position_update(self):
        """Timer callback — performs the actual batched position update."""
        self.setUpdatesEnabled(False)
        try:
            self.update()
            self.update_button_positions()
        finally:
            self.setUpdatesEnabled(True)

    def update_button_positions(self):
        """Optimized version with batching"""
        if not self.buttons:
            return
            
        visible_rect = self.rect()
        
        # Early exit if no size
        if visible_rect.width() <= 0 or visible_rect.height() <= 0:
            return
        
        # Use larger margin like Maya version
        visible_scene_rect = QtCore.QRectF(
            self.canvas_to_scene_coords(QtCore.QPointF(visible_rect.left(), visible_rect.top())),
            self.canvas_to_scene_coords(QtCore.QPointF(visible_rect.right(), visible_rect.bottom()))
        ).normalized()
        
        # Increase margin from 0.25 to 0.5 like Maya
        margin = max(visible_scene_rect.width() * 0.5, visible_scene_rect.height() * 0.5)
        visible_scene_rect.adjust(-margin, -margin, margin, margin)
        
        # Batch geometry updates
        geometry_updates = []
        buttons_to_show = []
        buttons_to_hide = []
        
        for button in self.buttons:
            button_pos = button.scene_position
            # Use rotated envelope for geometry (larger bounding box when rotated)
            env_w, env_h = button.rotated_envelope_size()
            button_rect = QtCore.QRectF(
                button_pos.x() - env_w/2,
                button_pos.y() - env_h/2,
                env_w,
                env_h
            )

            if visible_scene_rect.intersects(button_rect):
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

        self._request_guides_update()

        # Apply all updates at once
        self.setUpdatesEnabled(False)
        
        for button, x, y, w, h in geometry_updates:
            button.setGeometry(x, y, w, h)
            
        for button in buttons_to_show:
            if not button.isVisible():
                # Don't show the button if it's currently being edited in curve editor
                if hasattr(self, 'curve_editor') and self.curve_editor.is_editing():
                    if button == self.curve_editor.target_button:
                        continue  # Keep it hidden
                button.show()
                
        for button in buttons_to_hide:
            if button.isVisible():
                button.hide()
        
        self.setUpdatesEnabled(True)
        
    def update_button_data(self, button, deleted=False):
        main_window = self.window()
        if isinstance(main_window, UI.BlenderAnimPickerWindow):
            main_window.update_button_data(button, deleted)

    def on_button_changed(self, button):
        main_window = self.window()
    
        # Only update database if not in batch mode
        if not getattr(main_window, 'batch_update_active', False):
            self.update_button_data(button)

        # Assignment mutations flow through `changed` — keep the selection-sync
        # lookup in step so viewport<->picker sync sees the current state.
        SSM.rebuild_canvas_lookup(self)

        # Throttle transform guide updates
        if (hasattr(self, 'transform_guides') and 
            self.transform_guides.isVisible() and 
            button in self.get_selected_buttons()):
            
            if not hasattr(self, '_guide_update_throttle'):
                self._guide_update_throttle = QtCore.QTimer()
                self._guide_update_throttle.setSingleShot(True)
                self._guide_update_throttle.timeout.connect(
                    lambda: self.transform_guides.update_selection() if hasattr(self, 'transform_guides') else None
                )
            
            self._guide_update_throttle.stop()
            self._guide_update_throttle.start(50)  # 50ms throttle
    
    def update_hud_counts(self):
        """Optimized HUD count update with caching"""
        if not hasattr(self, '_last_hud_counts'):
            self._last_hud_counts = (-1, -1)
        
        selected_count = len(self.get_selected_buttons())
        total_count = len(self.buttons)
        
        # Only update if counts actually changed
        if self._last_hud_counts != (total_count, selected_count):
            self.hud.update_button_count(total_count, selected_count)
            self._last_hud_counts = (total_count, selected_count)
    #------------------------------------------------------------------------------
    def scene_to_canvas_coords(self, pos):
        # Convert scene coordinates to canvas coordinates
        canvas_pos = (pos * self.zoom_factor) + self._canvas_center + self.pan_offset
        return canvas_pos

    def canvas_to_scene_coords(self, pos):
        # Convert canvas coordinates to scene coordinates
        scene_pos = (pos - self._canvas_center - self.pan_offset) / self.zoom_factor
        return scene_pos
    
    def get_center_position(self):
        # Convert the center of the widget to scene coordinates
        return self.canvas_to_scene_coords(self._canvas_center)
          
    def canvas_cursor_position(self):
        """Gets the current cursor position in canvas coordinates and processes it
        the same way as the context menu does to ensure accurate positioning"""
        # Get current cursor position relative to this widget
        cursor_pos = self.mapFromGlobal(QtGui.QCursor.pos())
        return cursor_pos  # Return raw position to be processed by add_button_at_position
    #------------------------------------------------------------------------------
    # CANVAS BACKGROUND
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

    def set_background_image(self, image_path, update_database=False):
        """
        Set the background image from a file path.

        Args:
            image_path: Path to the image file (can be stored format or absolute)
            update_database: If True, updates the database with this path.
                           Should only be True when user explicitly adds/changes the image,
                           NOT during refresh/load operations.
        """
        if image_path is None:
            self.background_image = None
            self.background_image_path = None
        else:
            # Get the current tab name for path resolution
            main_window = self.window()
            tab_name = None
            if isinstance(main_window, UI.BlenderAnimPickerWindow):
                tab_name = main_window.tab_system.current_tab

            # Resolve the stored path to absolute for display
            resolved_path = DM.PickerDataManager.resolve_image_path(image_path, tab_name)

            # If resolution failed, try using the path directly (legacy absolute paths)
            if resolved_path is None and os.path.isabs(image_path) and os.path.exists(image_path):
                resolved_path = image_path

            if resolved_path and os.path.exists(resolved_path):
                self.background_image = QtGui.QImage(resolved_path)
                if self.background_image.isNull():
                    self.background_image = None
                    self.background_image_path = None
                else:
                    # Store the resolved (absolute) path for display reference
                    self.background_image_path = resolved_path
                    # Only update database if explicitly requested (user action, not refresh)
                    if update_database:
                        self._update_tab_data_with_background(resolved_path)
                        self.focus_canvas()
            else:
                # Path could not be resolved
                self.background_image = None
                self.background_image_path = None
                if image_path and not image_path.startswith("bpicker://"):
                    print(f"Warning: Could not resolve image path: {image_path}")
        self.update()

    def _update_tab_data_with_background(self, display_path):
        """
        Update the tab data with the background image path.
        Converts display path (absolute) to storage path (relative or absolute) based on settings.

        Args:
            display_path: Absolute path used for display
        """
        main_window = self.window()
        if isinstance(main_window, UI.BlenderAnimPickerWindow):
            current_tab = main_window.tab_system.current_tab
            if current_tab:
                # Use the new unified conversion method
                path_to_store = DM.PickerDataManager.convert_path_for_storage(
                    display_path,
                    tab_name=current_tab
                )

                # Update the tab system data structure with STORAGE path
                main_window.tab_system.tabs[current_tab]['image_path'] = path_to_store

                # Get current opacity and scale values
                current_opacity = main_window.tab_system.tabs[current_tab].get('image_opacity', 1.0)
                current_scale = self.image_scale

                # Update the data manager with STORAGE path
                DM.PickerDataManager.update_image_data(
                    current_tab,
                    path_to_store,
                    current_opacity,
                    current_scale
                )

                # Enable the remove layer button via controller
                if hasattr(main_window, 'edit_controller'):
                    main_window.edit_controller.canvas_widgets['remove_layer_btn'].setEnabled(True)

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
                    # Handle image file - use legacy single-image path
                    main_window = self.window()
                    if isinstance(main_window, UI.BlenderAnimPickerWindow):
                        tab_name = main_window.tab_system.current_tab
                        # Route through session if active (bpicker)
                        session = DM.PickerDataManager.get_active_session()
                        if session:
                            store_path = session.add_media_file(file_path, "backgrounds")
                            if store_path:
                                file_path = store_path
                        else:
                            file_path = DM.PickerDataManager.convert_path_for_storage(
                                file_path, tab_name=tab_name
                            )
                        # Clear stale multi-layer data so paintEvent uses legacy branch
                        self.background_layers = []
                        self.selected_layer_id = None
                        # Use legacy single-image path (same as Import button)
                        self.set_background_image(file_path)
                        main_window.remove_image.setEnabled(True)
                        main_window.tab_system.tabs[tab_name]['image_path'] = file_path
                        current_opacity = main_window.tab_system.tabs[tab_name].get('image_opacity', 1.0)
                        current_scale = float(main_window.image_scale_factor.text())
                        DM.PickerDataManager.update_image_data(
                            tab_name, file_path, current_opacity, current_scale
                        )
                        self.update()
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

    # ------ Multi-layer background methods ------
    def _resolve_layer_image(self, path):
        """Resolve a layer path and load it as QImage. Returns QImage or None."""
        if not path:
            return None
        main_window = self.window()
        tab_name = None
        if isinstance(main_window, UI.BlenderAnimPickerWindow):
            tab_name = main_window.tab_system.current_tab
        resolved = DM.PickerDataManager.resolve_image_path(path, tab_name)
        if resolved is None and os.path.isabs(path) and os.path.exists(path):
            resolved = path
        if resolved and os.path.exists(resolved):
            img = QtGui.QImage(resolved)
            if not img.isNull():
                return img
        return None

    def set_background_layers(self, layers_data):
        """Load all layers from tab data. Each entry is a dict with 'path', 'opacity', etc."""
        self.background_layers = []
        for ld in layers_data:
            layer = dict(ld)  # shallow copy
            layer['image'] = self._resolve_layer_image(layer.get('path'))
            self.background_layers.append(layer)
        # Update legacy compat
        if self.background_layers:
            first = self.background_layers[0]
            self.background_image = first.get('image')
            self.image_opacity = first.get('opacity', 1.0)
            self.image_scale = first.get('scale', 1.0)
        else:
            self.background_image = None
            self.image_opacity = 1.0
            self.image_scale = 1.0
        self.update()

    def add_background_layer(self, layer_data):
        """Add a single new layer, resolve path, load QImage, append to list. Returns the layer dict."""
        import uuid as _uuid
        layer = dict(layer_data)
        if 'id' not in layer:
            layer['id'] = str(_uuid.uuid4())
        layer.setdefault('name', f'Layer {len(self.background_layers) + 1}')
        layer.setdefault('opacity', 1.0)
        layer.setdefault('scale', 1.0)
        layer.setdefault('offset_x', 0.0)
        layer.setdefault('offset_y', 0.0)
        layer.setdefault('visible', True)
        layer.setdefault('locked', False)
        layer['image'] = self._resolve_layer_image(layer.get('path'))
        self.background_layers.append(layer)
        self.update()
        return layer

    def remove_background_layer(self, layer_id):
        """Remove a layer by ID."""
        self.background_layers = [l for l in self.background_layers if l['id'] != layer_id]
        if self.selected_layer_id == layer_id:
            self.selected_layer_id = None
        self.update()

    def update_background_layer(self, layer_id, **kwargs):
        """Update properties of a specific layer."""
        for layer in self.background_layers:
            if layer['id'] == layer_id:
                layer.update(kwargs)
                # Re-resolve image if path changed
                if 'path' in kwargs:
                    layer['image'] = self._resolve_layer_image(kwargs['path'])
                self.update()
                return

    def reorder_background_layers(self, layer_ids):
        """Reorder the internal layers list to match the provided ID order."""
        by_id = {l['id']: l for l in self.background_layers}
        reordered = [by_id[lid] for lid in layer_ids if lid in by_id]
        seen = set(layer_ids)
        for l in self.background_layers:
            if l['id'] not in seen:
                reordered.append(l)
        self.background_layers = reordered
        self.update()

    def select_layer(self, layer_id):
        """Set the selected layer for editing."""
        self.selected_layer_id = layer_id
        if hasattr(self, 'image_transform_guides'):
            self.image_transform_guides.update_visibility()
        self.update()

    def get_selected_layer(self):
        """Return the currently selected layer dict, or None."""
        if self.selected_layer_id is None:
            return None
        for layer in self.background_layers:
            if layer['id'] == self.selected_layer_id:
                return layer
        return None

    def get_layer_scene_rect(self, layer):
        """Return the QRectF for a layer in scene coordinates."""
        img = layer.get('image')
        if img is None or img.isNull():
            return QtCore.QRectF()
        scale = layer.get('scale', 1.0)
        ox = layer.get('offset_x', 0.0)
        oy = layer.get('offset_y', 0.0)
        w = img.width() * scale
        h = img.height() * scale
        return QtCore.QRectF(ox - w / 2, oy - h / 2, w, h)

    def focus_canvas(self):
        selected_buttons = self.get_selected_buttons()

        if selected_buttons:
            # Focus on the selected buttons
            button_rect = self.get_buttons_bounding_rect(selected_buttons)
            self.fit_rect_in_view(button_rect)

        elif self.background_layers:
            # Focus on bounding rect of all visible layers
            combined = QtCore.QRectF()
            for layer in self.background_layers:
                if layer.get('visible', True) and layer.get('image') and not layer['image'].isNull():
                    combined = combined.united(self.get_layer_scene_rect(layer))
            if not combined.isNull():
                self.fit_rect_in_view(combined)
        elif self.background_image and not self.background_image.isNull():
            # Legacy fallback
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
            
            if isinstance(main_window, UI.BlenderAnimPickerWindow):
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
                    DM.PickerDataManager.update_tab_data(current_tab, tab_data)
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
            if isinstance(main_window, UI.BlenderAnimPickerWindow):
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
                DM.PickerDataManager.update_tab_data(current_tab, tab_data)
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
        self._hide_button_tooltip()
        self._context_menu_open = True

        if not hasattr(self, 'context_menu'):
            self.context_menu = UT.create_styled_menu()
        
        menu = self.context_menu
        menu.clear()
        
        if self.edit_mode:
            add_button_action = menu.addAction(QtGui.QIcon(UT.get_icon('add.png')), "Add Button")
            add_button_action.triggered.connect(lambda: self.add_button_at_position(position))

            # Create multiple buttons paired to each currently selected scene object/bone
            try:
                main_window = self.window()
                ns = main_window.namespace_dropdown.currentText() if hasattr(main_window, 'namespace_dropdown') else None
            except Exception:
                ns = None
            selection_preview = TF.get_current_scene_selection(namespace=ns)
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
            
            # Create main curve import action
            create_button_from_blender_curve_action = menu.addAction(QtGui.QIcon(UT.get_icon('add.png')), "Create Button from Curve")
            create_button_from_blender_curve_action.triggered.connect(lambda: create_buttons_from_blender_curves(self, scene_pos, show_options_dialog=False))
            
            # Create submenu for coordinate plane options with embedded widget
            from . import curve_import_widget as CIW
            plane_submenu = UT.create_styled_menu(parent=menu, title="Curve Import Options")
            menu.addMenu(plane_submenu)
            #plane_submenu.setIcon(QtGui.QIcon(UT.get_icon('code.png')))
            
            # Create the embedded widget
            options_widget = CIW.CurveImportOptionsWidget(plane_submenu, self)
            
            # Add the widget to the menu using QWidgetAction
            widget_action = QtWidgets.QWidgetAction(plane_submenu)
            widget_action.setDefaultWidget(options_widget)
            plane_submenu.addAction(widget_action)
            
            '''# Add separator after widget
            plane_submenu.addSeparator()
            
            # Add utility actions
            refresh_action = plane_submenu.addAction("Refresh Display")
            refresh_action.setToolTip("Refresh the display to show current settings")
            refresh_action.triggered.connect(options_widget.handle_refresh)
            
            reset_action = plane_submenu.addAction("Reset to Defaults")
            reset_action.setToolTip("Reset all curve import settings to defaults")
            reset_action.triggered.connect(options_widget.reset_settings)'''
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
            if isinstance(main_window, UI.BlenderAnimPickerWindow):
                edit_mode_action.triggered.connect(main_window.toggle_edit_mode)
        else:
            edit_mode_action = menu.addAction(QtGui.QIcon(UT.get_icon('edit.png')),"Edit Picker")
            main_window = self.window()
            if isinstance(main_window, UI.BlenderAnimPickerWindow):
                edit_mode_action.triggered.connect(main_window.toggle_edit_mode)
        
        # Add selection sync options
        menu.addSeparator()
        sync_submenu = UT.create_styled_menu(parent=menu, title="Selection Sync")
        menu.addMenu(sync_submenu)
        
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
        
        if menu.actions():
            menu.exec_(self.mapToGlobal(position))
        self._context_menu_open = False

    def add_button_at_position(self, position):
        scene_pos = self.canvas_to_scene_coords(QtCore.QPointF(position))
        
        main_window = self.window()
        if isinstance(main_window, UI.BlenderAnimPickerWindow):
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
                "width": new_button.width,
                "height": new_button.height,
                "radius": new_button.radius,
                "assigned_objects": []
            }
            
            # Update PickerDataManager
            tab_data = DM.PickerDataManager.get_tab_data(current_tab)
            tab_data['buttons'].append(button_data)
            DM.PickerDataManager.update_tab_data(current_tab, tab_data)
            
            self.clear_selection()
            new_button.is_selected = True
            new_button.selected.emit(new_button, True)

            self.update_button_positions()
            self.update()

    # ------------------------------------------------------------------
    # Multi-button "Create from Selection" with drag-to-place layout
    # ------------------------------------------------------------------
    def start_multi_button_placement(self, click_widget_pos):
        """Begin drag-to-place mode for N buttons, one per selected scene object/bone."""
        if not self.edit_mode:
            return
        main_window = self.window()
        namespace = None
        try:
            if hasattr(main_window, 'namespace_dropdown'):
                namespace = main_window.namespace_dropdown.currentText()
        except Exception:
            namespace = None
        selection = TF.get_current_scene_selection(namespace=namespace)
        if not selection:
            return

        origin_scene = self.canvas_to_scene_coords(QtCore.QPointF(click_widget_pos))

        if len(selection) == 1:
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
            cols = max(1, int(math.ceil(math.sqrt(n))))
            rows = int(math.ceil(n / float(cols)))
            col_step = dw + gap
            row_step = dh + gap
            for i in range(n):
                r = i // cols
                c = i % cols
                row_count = cols if r < rows - 1 else (n - r * cols)
                cx = (c - (row_count - 1) / 2.0) * col_step
                cy = (r - (rows - 1) / 2.0) * row_step
                positions.append(QtCore.QPointF(origin.x() + cx, origin.y() + cy))
            return positions

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
        pen = QtGui.QPen(QtGui.QColor(200, 200, 200, 160))
        pen.setWidthF(1.0 / max(self.zoom_factor, 0.001))
        pen.setStyle(QtCore.Qt.DashLine)
        painter.setPen(pen)
        if self.placement_cursor_scene is not None:
            painter.drawLine(self.placement_origin_scene, self.placement_cursor_scene)

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
        main_window = self.window()
        if not isinstance(main_window, UI.BlenderAnimPickerWindow):
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

            # Blender has no add_button_without_db_update; temporarily suppress
            # the window's update_button_data to keep this a single DB write.
            old_method = getattr(main_window, 'update_button_data', None)
            if old_method is not None:
                main_window.update_button_data = lambda *a, **kw: None
            try:
                self.add_button(new_button)
            finally:
                if old_method is not None:
                    main_window.update_button_data = old_method

            new_buttons_widgets.append(new_button)
            new_buttons_data.append({
                "id": unique_id,
                "selectable": new_button.selectable,
                "label": new_button.label,
                "color": new_button.color,
                "opacity": new_button.opacity,
                "position": (new_button.scene_position.x(), new_button.scene_position.y()),
                "width": new_button.width,
                "height": new_button.height,
                "radius": new_button.radius,
                "assigned_objects": list(new_button.assigned_objects),
                "mode": new_button.mode,
                "script_data": {},
                "shape_type": getattr(new_button, 'shape_type', 'rect'),
                "svg_path_data": getattr(new_button, 'svg_path_data', '') or '',
                "svg_file_path": getattr(new_button, 'svg_file_path', '') or '',
            })

        if not new_buttons_data:
            return

        self.clear_selection()
        for b in new_buttons_widgets:
            b.is_selected = True

        tab_data = DM.PickerDataManager.get_tab_data(current_tab)
        tab_data['buttons'].extend(new_buttons_data)
        DM.PickerDataManager.update_tab_data(current_tab, tab_data)

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
        # Record undo state
        copied_buttons = PB.ButtonClipboard.instance().get_all_buttons()
        action = "Paste Mirror" if mirror else "Paste"
        #DM.PickerDataManager.save_undo_state(f"{action} {len(copied_buttons)} Button(s)")
    
        """REFACTORED: Simplified paste function that uses horizontal_mirror_button_positions for mirroring"""
        # Check if position is already in scene coordinates or needs to be converted
        if is_scene_coords:
            scene_pos = QtCore.QPointF(position)
        else:
            scene_pos = self.canvas_to_scene_coords(QtCore.QPointF(position))
        copied_buttons = PB.ButtonClipboard.instance().get_all_buttons()
        
        if not copied_buttons:
            return
            
        main_window = self.window()
        if isinstance(main_window, UI.BlenderAnimPickerWindow):
            current_tab = main_window.tab_system.current_tab
            new_buttons = []
            
            # CRITICAL FIX: Disable batch mode temporarily for pasting
            # This ensures each button update is processed immediately
            was_batch_active = getattr(main_window, 'batch_update_active', False)
            main_window.batch_update_active = False
            self.setUpdatesEnabled(False)
            
            try:
                # Get tab data once at the beginning
                tab_data = DM.PickerDataManager.get_tab_data(current_tab)
                
                for button_data in copied_buttons:
                    unique_id = main_window.generate_unique_id(current_tab)
                    new_button = PB.PickerButton(button_data['label'], self, unique_id=unique_id)
                    
                    # Apply all copied attributes including functionality
                    new_button.color = button_data['color']
                    new_button.opacity = button_data['opacity']
                    new_button.selectable = button_data['selectable']
                    new_button.width = button_data['width']
                    new_button.height = button_data['height']
                    new_button.radius = button_data['radius'].copy()
                    new_button.mode = button_data.get('mode', 'select')
                    new_button.script_data = button_data.get('script_data', {}).copy()
                    new_button.shape_type = button_data.get('shape_type', 'rect')
                    new_button.svg_path_data = button_data.get('svg_path_data', '')
                    new_button.svg_file_path = button_data.get('svg_file_path', '')
                    new_button.rotation = button_data.get('rotation', 0)

                    # Always use original assigned objects - counterpart mirroring handled in horizontal_mirror_button_positions
                    new_button.assigned_objects = button_data['assigned_objects'].copy()

                    # Apply controller-specific data
                    if new_button.mode == 'controller' and 'controller_data' in button_data:
                        import copy as _copy
                        new_button.controller_data = _copy.deepcopy(button_data['controller_data'])
                        if new_button.controller_data.get('data_path'):
                            val = new_button._read_controller_value()
                            if val is not None:
                                new_button._controller_value = val
                            else:
                                new_button._controller_value = new_button.controller_data.get('default_value', 0.0)
                            new_button._start_controller_sync()

                    # Apply pose-specific data if this is a pose button
                    if new_button.mode == 'pose':
                        # Copy thumbnail path if available
                        if 'thumbnail_path' in button_data:
                            new_button.thumbnail_path = button_data['thumbnail_path']
                            
                            # Load the pixmap using path resolution
                            if new_button.thumbnail_path:
                                resolved_path = DM.PickerDataManager.resolve_image_path(
                                    new_button.thumbnail_path, 
                                    current_tab
                                )
                                if resolved_path and os.path.exists(resolved_path):
                                    new_button.thumbnail_pixmap = QtGui.QPixmap(resolved_path)
                        
                        # Copy pose data if available
                        if 'pose_data' in button_data:
                            new_button.pose_data = button_data['pose_data'].copy()
                        if 'animation_data' in button_data:
                            new_button.animation_data = button_data['animation_data'].copy()
                    
                    # Position relative to cursor point (position mirroring handled separately)
                    relative_position = button_data['relative_position']
                    new_button.scene_position = scene_pos + relative_position
                    
                    # Add button to canvas
                    self.add_button(new_button)
                    new_buttons.append(new_button)
                    
                    # CRITICAL FIX: Create complete button data for database immediately
                    button_data_for_db = main_window._create_button_data(new_button)

                    # CRITICAL FIX: Add to tab_data immediately
                    tab_data['buttons'].append(button_data_for_db)
                
                # Save the initial button state to database
                DM.PickerDataManager.update_tab_data(current_tab, tab_data)
                
                # Select all newly pasted buttons BEFORE mirroring
                if new_buttons:
                    # Clear current selection
                    self.clear_selection()

                    # Select all new buttons
                    for button in new_buttons:
                        button.is_selected = True
                        # Invalidate per-button transform/paint caches so the very first
                        # bounding-rect calculation can't read a value cached from a
                        # previously-deleted button instance.
                        button._cached_envelope = None
                        button._cached_envelope_key = None
                        button._cached_scene_path = None
                        button._cached_scene_path_key = None
                        button.selected.emit(button, True)
                    # Force an immediate (un-debounced) selection-changed emit so that
                    # TransformGuides re-syncs its selected_buttons NOW. Without this
                    # the debounced emit can lag behind a quick handle-grab on the
                    # freshly-pasted button, leaving guides operating on stale state
                    # and causing rotated duplicates to jump on first transform.
                    if hasattr(self, 'button_selection_changed'):
                        self.button_selection_changed.emit()

                    #print(f"Selected {len(new_buttons)} newly pasted buttons")

                # Apply position/SVG/counterpart mirroring if requested using existing function
                if mirror and new_buttons:
                    #print("Applying position, SVG, and counterpart mirroring using horizontal_mirror_button_positions...")
                    # Use existing horizontal mirror function with counterpart mirroring enabled
                    self.horizontal_mirror_button_positions(apply_counterparts=True)
                    # Note: horizontal_mirror_button_positions handles its own database updates
                    # Positions changed — re-emit so guides recompute the bounding rect
                    if hasattr(self, 'button_selection_changed'):
                        self.button_selection_changed.emit()
                
                action_word = "Mirror pasted" if mirror else "Pasted"
                #print(f"{action_word} {len(new_buttons)} buttons - All saved to database")
            
            finally:
                # Restore batch mode state
                main_window.batch_update_active = was_batch_active
                
                # Re-enable canvas updates
                self.setUpdatesEnabled(True)
                self.update_button_positions()
                self.update()
            
            # Force a final database flush to ensure everything is saved
            if hasattr(main_window, '_flush_pending_updates'):
                main_window._flush_pending_updates()

            # Force immediate main window update
            if hasattr(main_window, 'update_buttons_for_current_tab'):
                main_window.update_buttons_for_current_tab(force_update=True)

    def horizontal_mirror_button_positions(self, apply_counterparts=False):
        """Mirror button positions horizontally with optional counterpart object assignment"""
        selected_buttons = self.get_selected_buttons()
        if not selected_buttons:
            return

        main_window = self.window()
        if not isinstance(main_window, UI.BlenderAnimPickerWindow):
            return

        # Mirror axis = center X of the selection bounds
        min_x = min(button.scene_position.x() for button in selected_buttons)
        max_x = max(button.scene_position.x() for button in selected_buttons)
        axis_x = (min_x + max_x) / 2

        was_batch_active = getattr(main_window, 'batch_update_active', False)
        main_window.batch_update_active = False
        self.setUpdatesEnabled(False)

        try:
            self._apply_mirror_to_buttons(selected_buttons, axis_x, apply_counterparts=apply_counterparts)
        finally:
            main_window.batch_update_active = was_batch_active
            self.setUpdatesEnabled(True)
            self.update_button_positions()
            self.update()

        if hasattr(main_window, '_flush_pending_updates'):
            main_window._flush_pending_updates()

        if hasattr(main_window, 'update_buttons_for_current_tab'):
            main_window.update_buttons_for_current_tab(force_update=True)

    def _apply_mirror_to_buttons(self, buttons, axis_x, apply_counterparts=False):
        """Mirror the given buttons horizontally across an explicit scene-space axis_x.

        Mutates each button in place: position X reflected across axis_x, rotation negated,
        custom-path SVG mirrored, and (optionally) assigned objects/bones swapped to L/R
        counterparts. Persists all changes via PickerDataManager in a single batch write.

        Caller is responsible for batch_update_active toggling, setUpdatesEnabled, and any
        post-mirror flush/refresh — this helper only handles the per-button mutation and
        the DB update.
        """
        if not buttons:
            return

        main_window = self.window()
        if not isinstance(main_window, UI.BlenderAnimPickerWindow):
            return

        current_tab = main_window.tab_system.current_tab
        tab_data = DM.PickerDataManager.get_tab_data(current_tab)

        if apply_counterparts:
            current_namespace = self._get_current_namespace()
            naming_conventions = self._get_naming_conventions("", "")

        updated_button_data = []

        for button in buttons:
            # Mirror position around axis_x
            button.scene_position.setX(2 * axis_x - button.scene_position.x())

            # Mirror rotation (negate for horizontal mirror)
            if button.rotation != 0:
                button.rotation = (-button.rotation) % 360
                button._invalidate_mask_cache()
                button.text_pixmap = None
                button.pose_pixmap = None

            # Mirror SVG path if applicable
            if button.shape_type == 'custom_path' and button.svg_path_data:
                button.svg_path_data = button.mirror_svg_path_horizontal(button.svg_path_data, button.width)
                button._invalidate_mask_cache()

            # Apply counterpart mirroring to assigned objects if requested
            if apply_counterparts and button.assigned_objects:
                mirrored_assigned_objects = []

                for obj_data in button.assigned_objects:
                    try:
                        if obj_data.get('is_bone', False):
                            bone_name = obj_data.get('name', '')
                            original_armature_name = obj_data.get('armature', '')

                            mirrored_bone_name, is_center_bone = self._find_mirrored_name(bone_name, naming_conventions)

                            mirrored_obj_data = {
                                'name': mirrored_bone_name,
                                'armature': original_armature_name,
                                'is_bone': True
                            }

                            counterpart_bone = self._resolve_bone_with_namespace(mirrored_obj_data, current_namespace)
                            if counterpart_bone:
                                mirrored_assigned_objects.append(mirrored_obj_data)
                            else:
                                mirrored_assigned_objects.append(obj_data.copy())
                                print(f"Counterpart bone not found for {bone_name}, keeping original")
                        else:
                            obj_name = obj_data.get('name', '')

                            mirrored_obj_name, is_center_object = self._find_mirrored_name(obj_name, naming_conventions)

                            mirrored_obj_data = {
                                'name': mirrored_obj_name,
                                'is_bone': False
                            }

                            counterpart_object = self._resolve_object(mirrored_obj_data, current_namespace)
                            if counterpart_object:
                                mirrored_assigned_objects.append(mirrored_obj_data)
                            else:
                                mirrored_assigned_objects.append(obj_data.copy())
                                print(f"Counterpart object not found for {obj_name}, keeping original")

                    except Exception as e:
                        print(f"Error mirroring assigned object {obj_data}: {e}")
                        mirrored_assigned_objects.append(obj_data.copy())

                button.assigned_objects = mirrored_assigned_objects

            button.update()

            button_data = main_window._create_button_data(button)
            updated_button_data.append(button_data)

        # Batch DB update: replace existing entries by id, append if new
        for button_data in updated_button_data:
            for i, existing_button in enumerate(tab_data['buttons']):
                if existing_button['id'] == button_data['id']:
                    tab_data['buttons'][i] = button_data
                    break
            else:
                tab_data['buttons'].append(button_data)

        DM.PickerDataManager.update_tab_data(current_tab, tab_data)

    def start_duplicate_mirror_tool(self):
        """Activate the interactive Duplicate Mirror tool on the current selection.

        The axis seeds at the scene origin (canvas center, where the X/Y axes
        cross) so the user has a predictable starting reference regardless of
        where the source selection sits.
        """
        if not self.edit_mode:
            return
        source = self.get_selected_buttons()
        if not source:
            return

        self.duplicate_mirror_tool.activate(source, 0.0)

    def vertical_mirror_button_positions(self):
        selected_buttons = self.get_selected_buttons()
        if not selected_buttons:
            return
        
        main_window = self.window()
        if not isinstance(main_window, UI.BlenderAnimPickerWindow):
            return
        
        # CRITICAL FIX: Disable batch updates to ensure immediate processing
        was_batch_active = getattr(main_window, 'batch_update_active', False)
        main_window.batch_update_active = False
        self.setUpdatesEnabled(False)
        
        try:
            # Get the center of the selected buttons
            min_y = min(button.scene_position.y() for button in selected_buttons)
            max_y = max(button.scene_position.y() for button in selected_buttons)
            center_y = (min_y + max_y) / 2
            
            # Get current tab data for batch database update
            current_tab = main_window.tab_system.current_tab
            tab_data = DM.PickerDataManager.get_tab_data(current_tab)
            
            # Track which buttons were updated for database batch update
            updated_button_data = []
            
            # Mirror positions around the center
            for button in selected_buttons:
                # Mirror position
                button.scene_position.setY(center_y - (button.scene_position.y() - center_y))

                # Mirror rotation (negate for vertical mirror)
                if button.rotation != 0:
                    button.rotation = (-button.rotation) % 360
                    button._invalidate_mask_cache()
                    button.text_pixmap = None
                    button.pose_pixmap = None

                # Mirror SVG path if applicable
                if button.shape_type == 'custom_path' and button.svg_path_data:
                    button.svg_path_data = button.mirror_svg_path_vertical(button.svg_path_data, button.height)
                    button._invalidate_mask_cache()

                # Force immediate visual update
                button.update()

                # Prepare button data for database update
                button_data = main_window._create_button_data(button)
                updated_button_data.append(button_data)
                
                #print(f"Mirrored button {button.unique_id}: position={button.scene_position.y():.2f}, svg_updated={bool(button.svg_path_data)}")
            
            # CRITICAL FIX: Batch update the database with ALL mirrored buttons at once
            for button_data in updated_button_data:
                # Find and update the existing button data in the tab
                for i, existing_button in enumerate(tab_data['buttons']):
                    if existing_button['id'] == button_data['id']:
                        tab_data['buttons'][i] = button_data
                        break
                else:
                    # If not found (shouldn't happen), add it
                    tab_data['buttons'].append(button_data)
            
            # Single database update for all buttons
            DM.PickerDataManager.update_tab_data(current_tab, tab_data)
            
            #print(f"Vertically mirrored {len(selected_buttons)} buttons - All changes saved to database in batch")
            
        finally:
            # Restore previous batch mode state
            main_window.batch_update_active = was_batch_active
            
            # Re-enable canvas updates
            self.setUpdatesEnabled(True)
            self.update_button_positions()
            self.update()
        
        # Force a final database flush to ensure everything is saved
        if hasattr(main_window, '_flush_pending_updates'):
            main_window._flush_pending_updates()

        if hasattr(main_window, 'update_buttons_for_current_tab'):
            main_window.update_buttons_for_current_tab(force_update=True)

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
            # Phased scroll event (trackpad or macOS smooth-scrolled mouse).
            # Use horizontal movement to distinguish: trackpads produce 2D
            # deltas, mouse wheels are strictly vertical.
            try:
                if phase == QtCore.Qt.ScrollPhase.ScrollBegin:
                    # New gesture: check for horizontal component
                    self._scroll_gesture_is_trackpad = abs(pixel_delta.x()) > 0
                elif abs(pixel_delta.x()) > 0:
                    # Mid-gesture horizontal movement detected → trackpad
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

        # Repaint canvas immediately (uses scene positions, no widget geometry needed)
        self._geometry_dirty = True
        self.update()

        if hasattr(self, 'transform_guides') and self.transform_guides.isVisible():
            self.transform_guides.update_position()

        self._geometry_flush_timer.start()
        self._schedule_view_changed()
        event.accept()

    def _apply_zoom_at_position(self, zoom_factor, position):
        """Apply zoom centered on a given canvas position."""
        old_scene_pos = self.canvas_to_scene_coords(position)

        self.zoom_factor *= zoom_factor
        self.zoom_factor = max(0.01, min(self.zoom_factor, 100.0))

        new_scene_pos = self.canvas_to_scene_coords(position)
        self.pan_offset += (new_scene_pos - old_scene_pos) * self.zoom_factor

        # Repaint canvas immediately, defer widget geometry
        self._geometry_dirty = True
        self.update()
        self._geometry_flush_timer.start()

        if hasattr(self, 'transform_guides') and self.transform_guides.isVisible():
            self.transform_guides.update_position()

        self._schedule_view_changed()

    def event(self, ev):
        """Handle native gesture events (trackpad pinch-to-zoom)."""
        t = ev.type()
        # On macOS, reactivate the picker window for scroll/gesture events
        # so zoom/pan works even after focus was returned to Blender
        if t in (QtCore.QEvent.Type.NativeGesture, QtCore.QEvent.Type.Wheel):
            if not self.window().isActiveWindow():
                UT.make_picker_key_window(self)
        if t == QtCore.QEvent.Type.NativeGesture:
            return self._handle_native_gesture(ev)
        return super().event(ev)

    def _handle_native_gesture(self, event):
        """Process trackpad pinch / smart-zoom gestures."""
        try:
            gesture_type = event.gestureType()
        except AttributeError:
            return False

        if gesture_type == QtCore.Qt.NativeGestureType.ZoomNativeGesture:
            # Pinch-to-zoom: event.value() is the relative scale delta
            scale_delta = event.value()
            pos = QtCore.QPointF(event.position())
            self._apply_zoom_at_position(1.0 + scale_delta, pos)
            self._hide_button_tooltip()
            event.accept()
            return True

        if gesture_type == QtCore.Qt.NativeGestureType.SmartZoomNativeGesture:
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

    def mouseDoubleClickEvent(self, event):
        if event.button() == QtCore.Qt.LeftButton:
            # Check if a button is at this position — forward double-click to it
            clicked_button = self._get_button_at_position(event.pos())
            if clicked_button and clicked_button._canvas_painted:
                local_pos = clicked_button.mapFromParent(event.pos())
                fwd = QtGui.QMouseEvent(
                    event.type(), local_pos, event.globalPos(),
                    event.button(), event.buttons(), event.modifiers()
                )
                clicked_button.mouseDoubleClickEvent(fwd)
                event.accept()
                return
            # No button — reset to original size when double-clicked on empty space
            self.zoom_factor = 1.0
            self.pan_offset = QtCore.QPointF(0, 0)
            self.update()
            self.update_button_positions()
            self.focus_canvas()
            self._schedule_view_changed()
        super().mouseDoubleClickEvent(event)

    def mousePressEvent(self, event):
        """Enhanced mouse press handler to track last clicked button"""
        # Hide tooltip immediately
        self._hide_button_tooltip()

        # Duplicate-mirror tool: intercept left-click. Right/middle still pass through
        # so context menus and middle-button pan continue to work.
        if (hasattr(self, 'duplicate_mirror_tool') and self.duplicate_mirror_tool.active
                and event.button() == QtCore.Qt.LeftButton):
            self.duplicate_mirror_tool.handle_mouse_press(event)
            # Always swallow left clicks while the tool is active to prevent
            # accidental selection/drag of underlying buttons.
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
            # Convert to transform guides coordinates
            guides_pos = self.transform_guides.mapFromParent(event.pos())
            if self.transform_guides.geometry().contains(event.pos()):
                # Check if we're actually clicking on a handle first
                guides_pos_f = QtCore.QPointF(guides_pos)
                handle = self.transform_guides.get_handle_at_pos(guides_pos_f)
                
                if handle:
                    # We clicked on an actual handle - let transform guides handle it
                    transform_event = QtGui.QMouseEvent(
                        event.type(), guides_pos, event.globalPos(), 
                        event.button(), event.buttons(), event.modifiers()
                    )
                    self.transform_guides.mousePressEvent(transform_event)
                    if transform_event.isAccepted():
                        event.accept()
                        return
        
        # Handle right-click for context menu or Alt+RMB for zoom
        if event.button() == QtCore.Qt.RightButton:
            alt_pressed = bool(event.modifiers() & QtCore.Qt.AltModifier)

            if alt_pressed:
                # Alt+RightButton for zoom
                self.last_zoom_pos = event.pos()
                self.was_zoom_dragging = True
                self.setCursor(QtCore.Qt.SizeVerCursor)
                event.accept()
                return
            else:
                # Check if a button is at this position (event may have propagated
                # from an overlapping widget's bounding rect in canvas-painted mode)
                clicked_button = self._get_button_at_position(event.pos())
                if clicked_button and clicked_button._canvas_painted:
                    local_pos = clicked_button.mapFromParent(event.pos())
                    fwd = QtGui.QMouseEvent(
                        event.type(), local_pos, event.globalPos(),
                        event.button(), event.buttons(), event.modifiers()
                    )
                    clicked_button.mousePressEvent(fwd)
                    event.accept()
                    return
                # Regular right-click context menu (empty space)
                self.show_context_menu(event.pos())
                event.accept()
                return
        
        # Check HUD interaction
        hud_pos = self.hud.mapFromParent(event.pos())
        if self.hud.button_container.geometry().contains(hud_pos):
            self.hud.toggle_button.click()
            event.accept()
            return
        
        # Handle left mouse button
        if event.button() == QtCore.Qt.LeftButton:
            # Check for Alt+Left click for panning
            alt_pressed = bool(event.modifiers() & QtCore.Qt.AltModifier)
            ctrl_pressed = bool(event.modifiers() & QtCore.Qt.ControlModifier)
            
            # Store initial selection state for rubber band operations
            self.initial_selection_state = {button: button.is_selected for button in self.buttons}
            self.ctrl_held_during_selection = ctrl_pressed
            
            # Find clicked button
            '''clicked_button = None
            for button in self.buttons:
                if button.isVisible() and button.geometry().contains(event.pos()):
                    clicked_button = button
                    break'''
            clicked_button = self._get_button_at_position(event.pos())
            # In edit mode, Alt+click on a button = duplicate drag (forward to button).
            # Otherwise Alt+click = pan (handled below).
            forward_to_button = (clicked_button and
                                 (not alt_pressed or (alt_pressed and self.edit_mode)))
            if forward_to_button:
                # Forward press to the shape-tested button and track it
                # for the rest of the press→move→release cycle.
                self._pressed_button = clicked_button
                if clicked_button._canvas_painted:
                    local_pos = clicked_button.mapFromParent(event.pos())
                    fwd = QtGui.QMouseEvent(
                        event.type(), local_pos, event.globalPos(),
                        event.button(), event.buttons(), event.modifiers()
                    )
                    clicked_button.mousePressEvent(fwd)
            elif alt_pressed:
                # Alt+Left click for panning
                self.last_pan_pos = event.pos()
                event.accept()
            else:
                # Empty space clicked without Alt
                shift_held = event.modifiers() & QtCore.Qt.ShiftModifier
                
                # Clear last clicked button when clicking empty space
                self.last_clicked_button = None
                
                # Clear selection if shift not held
                if not shift_held:
                    if self.edit_mode:
                        self.clear_selection()
                    else:
                        # Clear both Blender and picker selection with sync lock
                        self._clear_all_selections()
                
                # Start rubber band selection
                self.rubberband_origin = event.pos()
                self.rubberband.setGeometry(QtCore.QRect(self.rubberband_origin, QtCore.QSize()))
                self.rubberband.show()
                self.is_selecting = True
                self.buttons_in_current_drag.clear()
            
            event.accept()
            
        elif event.button() == QtCore.Qt.MiddleButton:
            self.last_pan_pos = event.pos()
            event.accept()
        else:
            super().mousePressEvent(event)
            self.setFocus()
        
        main_window = self.window()
        if main_window.edit_mode == False:
            UT.blender_main_window()
        event.accept()
        
    def mouseMoveEvent(self, event):
        """Handle mouse move events"""
        # Track current mouse position and convert to scene coordinates
        self.current_mouse_pos = QtCore.QPointF(event.pos())
        self.current_mouse_scene_pos = self.canvas_to_scene_coords(self.current_mouse_pos)

        # Duplicate-mirror tool: drag the axis line (or update hover state).
        if hasattr(self, 'duplicate_mirror_tool') and self.duplicate_mirror_tool.active:
            if self.duplicate_mirror_tool.handle_mouse_move(event):
                event.accept()
                return

        # Multi-button placement: live-update ghost layout.
        if self.is_placing_multi:
            self.placement_cursor_scene = self.current_mouse_scene_pos
            self.update()
            event.accept()
            return

        # Check for Alt+Left drag panning
        alt_pressed = bool(event.modifiers() & QtCore.Qt.AltModifier)

        # Skip hover hit-testing during active pan/zoom/drag — it iterates all
        # buttons and is unnecessary while the user is navigating.
        is_panning = (((event.buttons() == QtCore.Qt.LeftButton and alt_pressed) or
                       event.buttons() == QtCore.Qt.MiddleButton) and self.last_pan_pos)
        is_zooming = (event.buttons() == QtCore.Qt.RightButton and alt_pressed and self.last_zoom_pos)
        is_button_drag = bool(self._pressed_button and event.buttons() & QtCore.Qt.LeftButton)
        if not (self.is_selecting or is_panning or is_zooming or is_button_drag):
            self._update_hover_button(event.pos())

        if self.is_selecting:
            # Rubber band selection active
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

            # Handle Alt+RMB zoom
            ctrl_pressed = bool(event.modifiers() & QtCore.Qt.ControlModifier)

            # Calculate zoom delta (drag down = zoom in, drag up = zoom out)
            delta_y = event.pos().y() - self.last_zoom_pos.y()

            # Set zoom speed based on Ctrl modifier
            zoom_speed = 0.002 if ctrl_pressed else 0.008

            # Calculate zoom factor (inverted sign to match Maya: down = zoom in)
            zoom_delta = -delta_y * zoom_speed
            new_zoom = self.zoom_factor * (1.0 + zoom_delta)

            # Clamp zoom to reasonable range
            new_zoom = max(0.1, min(10.0, new_zoom))

            # Apply zoom centered on cursor position (matches scroll wheel behavior)
            cursor_pos = QtCore.QPointF(self.last_zoom_pos)
            scene_before = self.canvas_to_scene_coords(cursor_pos)

            self.zoom_factor = new_zoom

            scene_after = self.canvas_to_scene_coords(cursor_pos)

            # Adjust pan offset to keep cursor point stable
            self.pan_offset += (scene_after - scene_before) * self.zoom_factor

            # Canvas painting uses scene coords — only repaint during drag zoom.
            # Widget geometry deferred until release.
            self.last_zoom_pos = event.pos()
            self._geometry_dirty = True
            self.update()
            event.accept()

        elif ((event.buttons() == QtCore.Qt.LeftButton and alt_pressed) or
            event.buttons() == QtCore.Qt.MiddleButton) and self.last_pan_pos:
            # Hide tooltip during zoom
            self._hide_button_tooltip()

            # Handle panning (Alt+Left drag or Middle mouse drag)
            delta = event.pos() - self.last_pan_pos
            self.update_pan_offset(delta)
            self.last_pan_pos = event.pos()
            # Canvas painting uses scene coords directly — only repaint needed.
            # Widget geometry update is deferred until pan ends (mouseReleaseEvent).
            self._geometry_dirty = True
            self.update()
            event.accept()
        elif self._pressed_button and event.buttons() & QtCore.Qt.LeftButton:
            # Forward drag events to the button that owns this press cycle
            btn = self._pressed_button
            local_pos = btn.mapFromParent(event.pos())
            fwd = QtGui.QMouseEvent(
                event.type(), local_pos, event.globalPos(),
                event.button(), event.buttons(), event.modifiers()
            )
            btn.mouseMoveEvent(fwd)
            # Update transform guides during button drag
            if getattr(btn, 'dragging', False):
                self._request_guides_update()
            event.accept()
        else:
            super().mouseMoveEvent(event)
        event.accept()

    def leaveEvent(self, event):
        """Handle mouse leaving the canvas"""
        self._hide_button_tooltip()
        if self._current_hover_button:
            self._current_hover_button.is_hovered = False
            self._current_hover_button.update()
            self._current_hover_button = None
        self._pressed_button = None
        self.setCursor(QtCore.Qt.ArrowCursor)
        # Reset mouse position tracking when mouse leaves canvas
        self.current_mouse_pos = QtCore.QPointF(0, 0)
        self.current_mouse_scene_pos = QtCore.QPointF(0, 0)
        self.update()

        # Always hand key window status back to Blender when the cursor
        # genuinely leaves the picker window. Without this, Blender's
        # GHOST never reclaims key status (the picker is a floating
        # WindowStaysOnTopHint tool) and viewport navigation — orbit,
        # pan, zoom — silently breaks until something forces a GHOST
        # resync (e.g. resizing an area).
        #
        # leaveEvent can fire when the cursor moves to a child widget
        # too, so verify the cursor is actually outside the top-level
        # picker frame before handing focus over.
        try:
            top = self.window()
            if top is not None:
                global_pos = QtGui.QCursor.pos()
                if not top.frameGeometry().contains(global_pos):
                    self._pending_host_activation = False
                    UT.blender_main_window()
        except Exception:
            pass
        super().leaveEvent(event)
    
    def contextMenuEvent(self, event):
        """Accept the context menu event to prevent propagation to parent window.

        Context menus are handled in mousePressEvent; this override is a
        safety net to stop any residual event from reaching the parent frame.
        """
        event.accept()

    def mouseReleaseEvent(self, event):
        """Enhanced mouse release handler to properly handle last selected button"""

        # Duplicate-mirror tool: end any in-progress line drag.
        if hasattr(self, 'duplicate_mirror_tool') and self.duplicate_mirror_tool.active:
            if self.duplicate_mirror_tool.handle_mouse_release(event):
                event.accept()
                return

        # Forward release to the button that owns this press cycle
        if event.button() == QtCore.Qt.LeftButton and self._pressed_button:
            btn = self._pressed_button
            self._pressed_button = None
            local_pos = btn.mapFromParent(event.pos())
            fwd = QtGui.QMouseEvent(
                event.type(), local_pos, event.globalPos(),
                event.button(), event.buttons(), event.modifiers()
            )
            btn.mouseReleaseEvent(fwd)
            # Still run the canvas-level drag completion logic below

        if event.button() == QtCore.Qt.LeftButton and self.is_selecting:
            # End rubber band selection
            self.is_selecting = False
            self.rubberband.hide()
            
            # For rubber band selection, determine the "last selected" based on mouse position
            if self.buttons_in_current_drag:
                # Find the button closest to the final mouse position among selected buttons
                mouse_scene_pos = self.canvas_to_scene_coords(QtCore.QPointF(event.pos()))
                closest_button = None
                min_distance = float('inf')
                
                for button in self.buttons_in_current_drag:
                    if button.is_selected:
                        distance = ((button.scene_position.x() - mouse_scene_pos.x()) ** 2 + 
                                (button.scene_position.y() - mouse_scene_pos.y()) ** 2) ** 0.5
                        if distance < min_distance:
                            min_distance = distance
                            closest_button = button
                
                if closest_button:
                    self.last_clicked_button = closest_button
            
            # Check modifier combinations for apply_final_selection
            shift_pressed = bool(event.modifiers() & QtCore.Qt.ShiftModifier)
            ctrl_pressed = bool(event.modifiers() & QtCore.Qt.ControlModifier)
            ctrl_held = getattr(self, 'ctrl_held_during_selection', False)
            
            # For counterpart selection, we only want ctrl without shift
            counterpart_mode = ctrl_held and not shift_pressed
            
            # Apply final selection from rubber band
            self.apply_final_selection(shift_pressed, counterpart_mode)
            
            # Ensure final selection state is properly set and signals are emitted
            final_selection_changed = False
            for button in self.buttons:
                old_selected = button.is_selected
                
                # Finalize selection state based on current drag
                if button in self.buttons_in_current_drag:
                    if shift_pressed and not ctrl_pressed:
                        # Shift only: Add to selection
                        button.is_selected = True
                    elif ctrl_pressed and shift_pressed:
                        # Ctrl+Shift: Remove from selection
                        button.is_selected = False
                    elif not shift_pressed and not ctrl_pressed:
                        # No modifiers: Replace selection
                        button.is_selected = True
                    # Note: ctrl_only case is handled in apply_final_selection for counterparts
                elif not shift_pressed:
                    # Clear non-dragged buttons if shift not held
                    button.is_selected = False
                # If shift held, preserve existing selection for non-dragged buttons
                
                # Check if state changed and emit signal
                if old_selected != button.is_selected:
                    final_selection_changed = True
                    button.selected.emit(button, button.is_selected)
                
                button.update()
            
            # Update last selected button for edit widgets
            if self.buttons_in_current_drag:
                # Use the stored last_clicked_button if available
                if hasattr(self, 'last_clicked_button') and self.last_clicked_button and self.last_clicked_button.is_selected:
                    self.last_selected_button = self.last_clicked_button
                else:
                    # Fallback: Set the last button in the drag as the reference for edit widgets
                    last_selected = None
                    for button in reversed(list(self.buttons_in_current_drag)):
                        if button.is_selected:
                            last_selected = button
                            break
                    if last_selected:
                        self.last_selected_button = last_selected
            
            # Important: Clear the drag tracking after rubber band selection
            self.buttons_in_current_drag.clear()
            self.initial_selection_state.clear()
            
            # Invalidate cache and emit signals
            if hasattr(self, '_cache_valid'):
                self._cache_valid = False
            
            if final_selection_changed:
                self.button_selection_changed.emit()
                self.update_hud_counts()
        
        # CRITICAL FIX: Handle button dragging completion
        elif event.button() == QtCore.Qt.LeftButton:
            # Check if any buttons were being dragged
            dragged_buttons = [btn for btn in self.buttons if getattr(btn, 'dragging', False)]
            
            if dragged_buttons:
                # CRITICAL FIX: Force immediate position updates for all dragged buttons
                main_window = self.window()
                if isinstance(main_window, UI.BlenderAnimPickerWindow):
                    # Temporarily disable batch mode to ensure immediate updates
                    was_batch_active = getattr(main_window, 'batch_update_active', False)
                    main_window.batch_update_active = False
                    
                    try:
                        # Update each dragged button's data immediately
                        for button in dragged_buttons:
                            # Force immediate database update for position changes
                            main_window._process_single_button_update(button)
                            #print(f"Canvas: Updated position for button {button.unique_id}: {button.scene_position.x()}, {button.scene_position.y()}")
                        
                        # Also update the buttons for the current tab
                        main_window.update_buttons_for_current_tab(force_update=True)
                        
                        self._request_guides_update()
                        
                    finally:
                        # Restore batch mode state
                        main_window.batch_update_active = was_batch_active
            
            # Reset pan position for Alt+Left drag
            self.last_pan_pos = None
            self._flush_deferred_geometry()
            self._schedule_view_changed()

        elif event.button() == QtCore.Qt.MiddleButton:
            self.last_pan_pos = None
            self._flush_deferred_geometry()
            self._schedule_view_changed()
        elif event.button() == QtCore.Qt.RightButton:
            # Reset zoom variables and cursor
            self.last_zoom_pos = None
            self.setCursor(QtCore.Qt.ArrowCursor)
            self._flush_deferred_geometry()
            self._schedule_view_changed()
        else:
            super().mouseReleaseEvent(event)
        
        # Always emit clicked signal
        self.clicked.emit()
        main_window = self.window()
        if main_window.edit_mode == False:
            UT.blender_main_window()
        event.accept()
    
    def resizeEvent(self, event):
        super().resizeEvent(event)

        # Update cached canvas center
        self._canvas_center = QtCore.QPointF(self.width() / 2.0, self.height() / 2.0)

        # Compensate pan_offset during programmatic edit-mode resize so
        # the canvas content stays visually anchored in place.
        main_win = self.window()
        if getattr(main_win, '_programmatic_resize', False):
            dx = (event.size().width() - event.oldSize().width()) / 2.0
            dy = (event.size().height() - event.oldSize().height()) / 2.0
            self.pan_offset -= QtCore.QPointF(dx, dy)

        self.update_button_positions()
        self.update_hud_geometry()
        self.hud.raise_()

        # Keep loading overlay covering the full canvas
        if hasattr(self, 'loading_overlay'):
            self.loading_overlay._reposition()

        # Keep save indicator at top-right
        if hasattr(self, 'save_indicator'):
            self.save_indicator._reposition()

        # Update transform guides position
        if hasattr(self, 'transform_guides') and self.transform_guides.isVisible():
            self.transform_guides.update_position()
        
        # Update curve editor position
        if hasattr(self, 'curve_editor') and self.curve_editor.isVisible():
            self.curve_editor._update_geometry()
            self.curve_editor._update_controls_position()
            
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
        painter.translate(self._canvas_center + self.pan_offset)
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

        # Draw background image layers (bottom to top)
        if self.background_layers:
            for layer in self.background_layers:
                if not layer.get('visible', True):
                    continue
                img = layer.get('image')
                if img is None or img.isNull():
                    continue
                painter.setOpacity(layer.get('opacity', 1.0))
                scale = layer.get('scale', 1.0)
                ox = layer.get('offset_x', 0.0)
                oy = layer.get('offset_y', 0.0)
                scaled_w = img.width() * scale
                scaled_h = img.height() * scale
                image_rect = QtCore.QRectF(
                    ox - scaled_w / 2,
                    oy - scaled_h / 2,
                    scaled_w,
                    scaled_h
                )
                painter.drawImage(image_rect, img)
            painter.setOpacity(1.0)
        elif self.background_image and not self.background_image.isNull():
            # Legacy single-image fallback
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
        # When Alt+dragging to duplicate, paint translucent copies of the selected
        # buttons at the target drop positions so the user can see where they'll land.
        if self._pressed_button and getattr(self._pressed_button, 'duplicating', False):
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

        painter.setClipping(False)

        # Draw border (always — color alpha controls visibility)
        if self.border_color.alpha() > 0:
            painter.setRenderHint(QtGui.QPainter.Antialiasing, True)
            half = self.border_width / 2.0
            rect = QtCore.QRectF(self.rect()).adjusted(half, half, -half, -half)
            pen = QtGui.QPen(self.border_color, self.border_width)
            painter.setPen(pen)
            painter.setBrush(QtCore.Qt.NoBrush)
            painter.drawRoundedRect(rect, self.border_radius, self.border_radius)

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
            print(f"PickerCanvas: Error initializing selection sync: {e}")
    
    def _cleanup_selection_sync(self):
        """Cleanup selection synchronization"""
        try:
            # Unregister this canvas from the selection sync manager
            SSM.unregister_canvas_from_sync(self)
        except Exception as e:
            print(f"PickerCanvas: Error cleaning up selection sync: {e}")
    
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
        """Clear both Blender and picker selections with proper sync handling"""
        # Set sync lock to prevent interference during clearing
        try:
            manager = SSM.SelectionSyncManager.get_instance()
            manager._sync_lock = True
        except:
            pass
        
        try:
            # Clear Blender selection
            import bpy
            with bpy.context.temp_override(window=bpy.context.window_manager.windows[0]):
                if bpy.context.mode == 'POSE':
                    bpy.ops.pose.select_all(action='DESELECT')
                elif bpy.context.mode == 'OBJECT':
                    bpy.ops.object.select_all(action='DESELECT')
            
            # Clear picker selection
            self.clear_selection()
            
            # Small delay to ensure Blender has processed the deselection
            # (we're in Qt context here — triggered by user action)
            from PySide6.QtCore import QTimer
            QTimer.singleShot(100, self._release_sync_lock)
            
        except Exception as e:
            print(f"Error clearing selections: {e}")
            # Always release lock on error
            self._release_sync_lock()
    
    def _release_sync_lock(self):
        """Release the sync lock after selection clearing"""
        try:
            manager = SSM.SelectionSyncManager.get_instance()
            manager._sync_lock = False
        except Exception as e:
            print(f"Error releasing sync lock: {e}")
            