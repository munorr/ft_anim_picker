"""
BGEN Library UI — BgenLibraryCard, BgenLibraryGridController, ExplorePageWidget.

Provides the BGEN Library tab UI with product cards, a catalogue grid
controller, and a data-driven Explore storefront (hero carousel,
section rows, collection banners, creator spotlight).  Currently wired
to mock data via BgenLocalFileManager.
"""

import os
from pathlib import Path

try:
    from PySide6 import QtWidgets, QtCore, QtGui
except ImportError:
    from PySide2 import QtWidgets, QtCore, QtGui

from . import custom_button as CB
from .bgen_library_manager import BgenLocalFileManager
from .config import settings as CFG
from .utils import get_icon


class _HoverStarButton(QtWidgets.QPushButton):
    """Star button that dims to *opacity* on idle and goes full-bright on hover."""

    _IDLE_OPACITY = 0.6

    def __init__(self, parent=None):
        super().__init__(parent)
        self._opacity_effect = QtWidgets.QGraphicsOpacityEffect(self)
        self._opacity_effect.setOpacity(self._IDLE_OPACITY)
        self.setGraphicsEffect(self._opacity_effect)

    def enterEvent(self, event):
        self._opacity_effect.setOpacity(1.0)
        super().enterEvent(event)

    def leaveEvent(self, event):
        self._opacity_effect.setOpacity(self._IDLE_OPACITY)
        super().leaveEvent(event)


_CATEGORY_BADGE = {
    "picker":    ("Picker",    "#1D65CA"),
    "rig":       ("Rig",       "#B05DC7"),
    "model":     ("Model",     "#D97B2B"),
    "animation": ("Animation", "#2BA5D9"),
    "scene":     ("Scene",     "#50A032"),
}

# ---------------------------------------------------------------------------
# BgenLibraryCard -- single product card
# ---------------------------------------------------------------------------

class BgenLibraryCard(QtWidgets.QFrame):
    """Visual card representing a bgen_library product."""

    clicked = QtCore.Signal(str)          # product id
    double_clicked = QtCore.Signal(str)   # product id
    context_menu_requested = QtCore.Signal(str, QtCore.QPoint)

    def __init__(self, product, parent=None, card_size=None):
        super().__init__(parent)
        self._alive = True
        self._product_id = product.get("id", "")
        self._product = product
        self._selected = False

        self._card_size = card_size if card_size is not None else CFG.LIBRARY_CARD_SIZE
        self._thumb_size = int(self._card_size - self._card_size * 0.1)
        label_height = max(16, int(self._card_size * 0.22))
        price_height = max(12, int(self._card_size * 0.16))
        font_size = max(9, min(12, int(self._card_size * 0.11)))
        price_font = max(7, min(10, int(self._card_size * 0.09)))
        self._max_name_chars = max(6, int(self._card_size * 0.14))

        self.setFixedSize(self._card_size, self._card_size + label_height + price_height)
        self.setCursor(QtCore.Qt.PointingHandCursor)
        self._apply_style(False)

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 2)
        layout.setSpacing(2)

        # Thumbnail
        self._thumb_label = QtWidgets.QLabel()
        self._thumb_label.setFixedSize(self._thumb_size, self._thumb_size)
        self._thumb_label.setAlignment(QtCore.Qt.AlignCenter)
        self._thumb_label.setStyleSheet(
            "background: rgba(50,50,50,0.6); border-radius: 10px; border: none;"
        )
        layout.addWidget(self._thumb_label, alignment=QtCore.Qt.AlignCenter)

        # Name label
        display_name = self._truncate_name(product.get("name", "Untitled"))
        self._name_label = QtWidgets.QLabel(display_name)
        self._name_label.setAlignment(QtCore.Qt.AlignLeft)
        self._name_label.setStyleSheet(
            f"color: #cccccc; font-size: {font_size}px; background: transparent; border: none;"
        )
        layout.addWidget(self._name_label)

        # Price label
        mgr = BgenLocalFileManager.get_instance()
        price_text = mgr.format_price(product)
        is_free = product.get("price_cents", 0) == 0
        price_color = "#7db305" if is_free else "#cccccc"
        self._price_label = QtWidgets.QLabel(price_text)
        self._price_label.setAlignment(QtCore.Qt.AlignLeft)
        self._price_label.setStyleSheet(
            f"color: {price_color}; font-size: {price_font}px; "
            f"background: transparent; border: none;"
        )
        layout.addWidget(self._price_label)

        # Default icon (initials placeholder)
        self._thumb_path = None  # Stores loaded thumbnail file path
        self._set_default_icon()

        # Async thumbnail loading from server
        self._load_thumbnail()

        # Software icon overlay (top-right of card)
        self._sw_icon_label = None
        software = product.get("software")
        if software in ("maya", "blender"):
            icon_name = "maya_icon.png" if software == "maya" else "blender_icon.png"
            icon_size = max(18, int(self._card_size * 0.22))
            icon_path = Path(__file__).parent / "bgen_picker_icons" / icon_name
            if icon_path.exists():
                sw_pixmap = QtGui.QPixmap(str(icon_path)).scaled(
                    icon_size, icon_size,
                    QtCore.Qt.KeepAspectRatio,
                    QtCore.Qt.SmoothTransformation,
                )
                if not sw_pixmap.isNull():
                    self._sw_icon_label = QtWidgets.QLabel(self)
                    self._sw_icon_label.setFixedSize(icon_size, icon_size)
                    self._sw_icon_label.setPixmap(sw_pixmap)
                    self._sw_icon_label.setStyleSheet("background: transparent; border: none;")
                    self._sw_icon_label.setAttribute(QtCore.Qt.WA_TransparentForMouseEvents)
                    self._sw_icon_label.raise_()

        # Tooltip
        self._tooltip_widget = None
        self._tooltip_timer = QtCore.QTimer(self)
        self._tooltip_timer.setSingleShot(True)
        self._tooltip_timer.setInterval(600)
        self._tooltip_timer.timeout.connect(self._show_tooltip)

    # ---- public ----

    def get_product_id(self):
        return self._product_id

    def resize_card(self, new_size):
        """Resize the card dynamically to *new_size* pixels wide."""
        self._card_size = new_size
        self._thumb_size = int(new_size - new_size * 0.1)
        label_height = max(16, int(new_size * 0.22))
        price_height = max(12, int(new_size * 0.16))
        font_size = max(8, min(12, int(new_size * 0.11)))
        price_font = max(7, min(10, int(new_size * 0.09)))
        self._max_name_chars = max(6, int(new_size * 0.14))

        self.setFixedSize(new_size, new_size + label_height + price_height)
        self._thumb_label.setFixedSize(self._thumb_size, self._thumb_size)
        self._name_label.setStyleSheet(
            f"color: #cccccc; font-size: {font_size}px; background: transparent; border: none;"
        )
        self._name_label.setText(self._truncate_name(self._product.get("name", "Untitled")))

        is_free = self._product.get("price_cents", 0) == 0
        price_color = "#7db305" if is_free else "#cccccc"
        self._price_label.setStyleSheet(
            f"color: {price_color}; font-size: {price_font}px; "
            f"background: transparent; border: none;"
        )

        # Re-apply software icon at new size
        if self._sw_icon_label:
            software = self._product.get("software")
            icon_name = "maya_icon.png" if software == "maya" else "blender_icon.png"
            icon_size = max(18, int(new_size * 0.22))
            icon_path = Path(__file__).parent / "bgen_picker_icons" / icon_name
            if icon_path.exists():
                sw_pixmap = QtGui.QPixmap(str(icon_path)).scaled(
                    icon_size, icon_size,
                    QtCore.Qt.KeepAspectRatio,
                    QtCore.Qt.SmoothTransformation,
                )
                if not sw_pixmap.isNull():
                    self._sw_icon_label.setFixedSize(icon_size, icon_size)
                    self._sw_icon_label.setPixmap(sw_pixmap)
            self._position_sw_icon()

        # Re-apply thumbnail (real image if loaded, otherwise initials)
        if self._thumb_path and os.path.isfile(self._thumb_path):
            pixmap = QtGui.QPixmap(self._thumb_path)
            if not pixmap.isNull():
                cropped = self._scale_and_crop(pixmap, self._thumb_size)
                cropped = self._apply_category_banner(cropped)
                self._thumb_label.setPixmap(self._round_pixmap(cropped))
            else:
                self._set_default_icon()
        else:
            self._set_default_icon()

    def set_selected(self, selected):
        self._selected = selected
        self._apply_style(selected)

    def cleanup(self):
        self._alive = False
        self._hide_tooltip()

    # ---- events ----

    def mousePressEvent(self, event):
        if event.button() == QtCore.Qt.LeftButton:
            self.clicked.emit(self._product_id)
        super().mousePressEvent(event)

    def mouseDoubleClickEvent(self, event):
        if event.button() == QtCore.Qt.LeftButton:
            self.double_clicked.emit(self._product_id)
        super().mouseDoubleClickEvent(event)

    def contextMenuEvent(self, event):
        self.context_menu_requested.emit(self._product_id, event.globalPos())

    def enterEvent(self, event):
        if not self._selected:
            self.setStyleSheet(
                "BgenLibraryCard { background: rgba(255,255,255,0.08); "
                "border: 1px solid rgba(255,255,255,0.12); border-radius: 6px; }"
            )
        # Hover shadow
        shadow = QtWidgets.QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(16)
        shadow.setOffset(0, 3)
        shadow.setColor(QtGui.QColor(0, 0, 0, 80))
        self.setGraphicsEffect(shadow)
        self._tooltip_timer.start()
        super().enterEvent(event)

    def leaveEvent(self, event):
        self._apply_style(self._selected)
        self.setGraphicsEffect(None)
        self._hide_tooltip()
        super().leaveEvent(event)

    def paintEvent(self, event):
        super().paintEvent(event)
        # "Owned" badge (top-right pill)
        if self._product.get("owned"):
            painter = QtGui.QPainter(self)
            painter.setRenderHint(QtGui.QPainter.Antialiasing)

            badge_text = "Owned"
            font = painter.font()
            font.setPixelSize(max(7, int(self._card_size * 0.09)))
            font.setBold(True)
            painter.setFont(font)

            fm = QtGui.QFontMetrics(font)
            text_w = fm.horizontalAdvance(badge_text)
            badge_w = text_w + 8
            badge_h = fm.height() + 4
            badge_x = self.width() - badge_w - 6
            badge_y = 6

            painter.setBrush(QtGui.QColor(80, 160, 50))
            painter.setPen(QtCore.Qt.NoPen)
            painter.drawRoundedRect(badge_x, badge_y, badge_w, badge_h, badge_h // 2, badge_h // 2)

            painter.setPen(QtGui.QColor(255, 255, 255))
            painter.drawText(
                QtCore.QRect(badge_x, badge_y, badge_w, badge_h),
                QtCore.Qt.AlignCenter,
                badge_text,
            )
            painter.end()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._position_sw_icon()

    def showEvent(self, event):
        super().showEvent(event)
        self._position_sw_icon()

    def _position_sw_icon(self):
        """Position the software icon overlay at the top-right of the card."""
        if self._sw_icon_label:
            icon_size = self._sw_icon_label.width()
            self._sw_icon_label.move(self.width() - icon_size - 6, 6)
            self._sw_icon_label.raise_()

    # ---- tooltip ----

    def _show_tooltip(self):
        self._hide_tooltip()
        tooltip = CB.CustomTooltipWidget()

        name = self._product.get("name", "Untitled")
        tooltip.add_text(f"<b>{name}</b>")
        tooltip.add_separator()

        creator = self._product.get("creator", "")
        if creator:
            tooltip.add_text(f"<span style='color:#999999;'>Creator:</span>  {creator}")

        mgr = BgenLocalFileManager.get_instance()
        tooltip.add_text(
            f"<span style='color:#999999;'>Price:</span>  {mgr.format_price(self._product)}"
        )

        cat = self._product.get("category", "")
        cat_info = _CATEGORY_BADGE.get(cat)
        if cat_info:
            tooltip.add_text(f"<span style='color:#999999;'>Type:</span>  {cat_info[0]}")

        software = self._product.get("software")
        if software in ("maya", "blender"):
            tooltip.add_text(
                f"<span style='color:#999999;'>Software:</span>  {software.capitalize()}"
            )

        rating = self._product.get("rating_avg", 0)
        rating_count = self._product.get("rating_count", 0)
        if rating_count:
            stars = "\u2605" * int(round(rating))
            tooltip.add_text(
                f"<span style='color:#999999;'>Rating:</span>  "
                f"<span style='color:#f0c040;'>{stars}</span>  {rating:.1f} ({rating_count})"
            )

        downloads = self._product.get("download_count", 0)
        tooltip.add_text(f"<span style='color:#999999;'>Downloads:</span>  {downloads:,}")

        desc = self._product.get("short_description", "")
        if desc:
            tooltip.add_separator()
            tooltip.add_text(f"<span style='color:#aaaaaa;'>{desc}</span>")

        tooltip.finalize()

        cursor_pos = QtGui.QCursor.pos()
        tooltip_pos = cursor_pos + QtCore.QPoint(12, 12)
        screen = QtWidgets.QApplication.screenAt(cursor_pos)
        if screen:
            sr = screen.availableGeometry()
            if tooltip_pos.x() + tooltip.width() > sr.right():
                tooltip_pos.setX(cursor_pos.x() - tooltip.width() - 12)
            if tooltip_pos.y() + tooltip.height() > sr.bottom():
                tooltip_pos.setY(cursor_pos.y() - tooltip.height() - 12)

        tooltip.move(tooltip_pos)
        tooltip.show()
        self._tooltip_widget = tooltip

    def _hide_tooltip(self):
        self._tooltip_timer.stop()
        if self._tooltip_widget:
            try:
                self._tooltip_widget.hide()
                self._tooltip_widget.deleteLater()
            except Exception:
                pass
            self._tooltip_widget = None

    # ---- internal ----

    def _truncate_name(self, name):
        if len(name) > self._max_name_chars:
            return name[: self._max_name_chars - 1] + "\u2026"
        return name

    def _apply_style(self, selected):
        if selected:
            self.setStyleSheet(
                "BgenLibraryCard { background: rgba(29,101,202,0.25); "
                "border: 1px solid rgba(29,101,202,0.6); border-radius: 6px; }"
            )
        else:
            self.setStyleSheet(
                "BgenLibraryCard { background: rgba(255,255,255,0); "
                "border: 0px solid transparent; border-radius: 6px; }"
            )

    @staticmethod
    def _scale_and_crop(pixmap, size):
        """Scale *pixmap* to fill *size*x*size* (crop centre if non-square)."""
        scaled = pixmap.scaled(
            size, size,
            QtCore.Qt.KeepAspectRatioByExpanding,
            QtCore.Qt.SmoothTransformation,
        )
        if scaled.width() != size or scaled.height() != size:
            x = (scaled.width() - size) // 2
            y = (scaled.height() - size) // 2
            scaled = scaled.copy(x, y, size, size)
        return scaled

    @staticmethod
    def _round_pixmap(pixmap, radius=10):
        """Return *pixmap* clipped to a rounded rectangle."""
        size = pixmap.size()
        rounded = QtGui.QPixmap(size)
        rounded.fill(QtCore.Qt.transparent)
        p = QtGui.QPainter(rounded)
        p.setRenderHint(QtGui.QPainter.Antialiasing)
        path = QtGui.QPainterPath()
        path.addRoundedRect(QtCore.QRectF(rounded.rect()), radius, radius)
        p.setClipPath(path)
        p.drawPixmap(0, 0, pixmap)
        p.end()
        return rounded

    def _apply_category_banner(self, pixmap):
        """Draw a diagonal category triangle at the bottom-right of *pixmap*."""
        cat = self._product.get("category", "")
        badge_info = _CATEGORY_BADGE.get(cat)
        if not badge_info:
            return pixmap

        label, color_hex = badge_info
        initial = label[0]
        ts = pixmap.width()
        banner_size = max(24, int(ts * 0.28))

        p = QtGui.QPainter(pixmap)
        p.setRenderHint(QtGui.QPainter.Antialiasing)
        p.setBrush(QtGui.QColor(color_hex))
        p.setPen(QtCore.Qt.NoPen)

        path = QtGui.QPainterPath()
        path.moveTo(ts, ts)
        path.lineTo(ts - banner_size, ts)
        path.lineTo(ts, ts - banner_size)
        path.closeSubpath()
        p.drawPath(path)

        p.setPen(QtGui.QColor(255, 255, 255))
        font = p.font()
        font.setPixelSize(max(8, int(banner_size * 0.4)))
        font.setBold(True)
        p.setFont(font)
        text_x = ts - int(banner_size * 0.62)
        text_y = ts - int(banner_size * 0.62)
        p.drawText(
            text_x, text_y,
            int(banner_size * 0.55), int(banner_size * 0.55),
            QtCore.Qt.AlignCenter, initial,
        )
        p.end()
        return pixmap

    def _set_default_icon(self):
        name = self._product.get("name", "?")
        initials = name[0].upper() if name else "?"
        ts = self._thumb_size

        pixmap = QtGui.QPixmap(ts, ts)
        pixmap.fill(QtGui.QColor(45, 45, 50))

        painter = QtGui.QPainter(pixmap)
        painter.setRenderHint(QtGui.QPainter.Antialiasing)
        painter.setBrush(QtGui.QColor(55, 60, 70))
        painter.setPen(QtCore.Qt.NoPen)
        painter.drawRoundedRect(0, 0, ts, ts, 10, 10)

        painter.setPen(QtGui.QColor(140, 150, 170))
        font = painter.font()
        font.setPixelSize(int(ts * 0.45))
        font.setBold(True)
        painter.setFont(font)
        painter.drawText(
            QtCore.QRect(0, 0, ts, ts), QtCore.Qt.AlignCenter, initials,
        )
        painter.end()
        pixmap = self._apply_category_banner(pixmap)
        self._thumb_label.setPixmap(self._round_pixmap(pixmap))

    def _load_thumbnail(self):
        """Request async thumbnail download from BgenLocalFileManager."""
        mgr = BgenLocalFileManager.get_instance()
        url = mgr.get_thumbnail_url(self._product)
        if url:
            mgr.load_thumbnail_async(self._product_id, url, self._on_thumbnail_loaded)

    def _on_thumbnail_loaded(self, product_id, file_path):
        """Callback from BgenLocalFileManager when thumbnail is downloaded."""
        if not self._alive or product_id != self._product_id:
            return
        if not file_path or not os.path.isfile(file_path):
            return
        try:
            pixmap = QtGui.QPixmap(file_path)
            if not pixmap.isNull():
                self._thumb_path = file_path
                cropped = self._scale_and_crop(pixmap, self._thumb_size)
                cropped = self._apply_category_banner(cropped)
                self._thumb_label.setPixmap(self._round_pixmap(cropped))
        except RuntimeError:
            pass  # Widget already deleted


# ---------------------------------------------------------------------------
# View-mode size presets (shared with library_ui)
# ---------------------------------------------------------------------------

MKT_VIEW_SIZES = {
    "small": 64,
    "medium": 84,
    "large": 120,
    "list": 0,
}


# ---------------------------------------------------------------------------
# BgenLibraryListItem – compact row for list view
# ---------------------------------------------------------------------------

class BgenLibraryListItem(QtWidgets.QFrame):
    """Compact horizontal row for bgen_library list-view mode."""

    clicked = QtCore.Signal(str)
    double_clicked = QtCore.Signal(str)
    context_menu_requested = QtCore.Signal(str, QtCore.QPoint)

    def __init__(self, product, parent=None):
        super().__init__(parent)
        self._alive = True
        self._product_id = product.get("id", "")
        self._product = product
        self._selected = False

        self.setFixedHeight(32)
        self.setCursor(QtCore.Qt.PointingHandCursor)
        self._apply_style(False)

        layout = QtWidgets.QHBoxLayout(self)
        layout.setContentsMargins(6, 2, 8, 2)
        layout.setSpacing(8)

        # Small thumbnail
        self._thumb_label = QtWidgets.QLabel()
        self._thumb_label.setFixedSize(24, 24)
        self._thumb_label.setAlignment(QtCore.Qt.AlignCenter)
        self._thumb_label.setStyleSheet("background: rgba(50,50,50,0.6); border-radius: 3px; border: none;")
        name = product.get("name", "?")
        initials = name[0].upper() if name else "?"
        pix = QtGui.QPixmap(24, 24)
        pix.fill(QtGui.QColor(55, 60, 70))
        p = QtGui.QPainter(pix)
        p.setRenderHint(QtGui.QPainter.Antialiasing)
        p.setPen(QtGui.QColor(140, 150, 170))
        f = p.font()
        f.setPixelSize(11)
        f.setBold(True)
        p.setFont(f)
        p.drawText(QtCore.QRect(0, 0, 24, 24), QtCore.Qt.AlignCenter, initials)
        p.end()
        self._thumb_label.setPixmap(pix)
        layout.addWidget(self._thumb_label)

        # Load actual thumbnail async
        self._load_thumbnail()

        # Name
        name_label = QtWidgets.QLabel(name)
        name_label.setStyleSheet("color: #cccccc; font-size: 11px; background: transparent; border: none;")
        layout.addWidget(name_label, 1)

        # Creator
        creator = product.get("creator", "")
        if creator:
            creator_label = QtWidgets.QLabel(creator)
            creator_label.setStyleSheet("color: #777777; font-size: 10px; background: transparent; border: none;")
            layout.addWidget(creator_label)

        # Software icon
        software = product.get("software")
        if software in ("maya", "blender"):
            icon_name = "maya_icon.png" if software == "maya" else "blender_icon.png"
            sw_pixmap = get_icon(icon_name, size=16)
            if sw_pixmap and not sw_pixmap.isNull():
                sw_label = QtWidgets.QLabel()
                sw_label.setFixedSize(16, 16)
                sw_label.setPixmap(sw_pixmap)
                sw_label.setStyleSheet("background: transparent; border: none;")
                layout.addWidget(sw_label)

        # Price
        mgr = BgenLocalFileManager.get_instance()
        price_text = mgr.format_price(product)
        is_free = product.get("price_cents", 0) == 0
        price_color = "#7db305" if is_free else "#aaaaaa"
        price_label = QtWidgets.QLabel(price_text)
        price_label.setStyleSheet(f"color: {price_color}; font-size: 10px; background: transparent; border: none;")
        layout.addWidget(price_label)

    def _load_thumbnail(self):
        """Request async thumbnail download from BgenLocalFileManager."""
        mgr = BgenLocalFileManager.get_instance()
        url = mgr.get_thumbnail_url(self._product)
        if url:
            mgr.load_thumbnail_async(self._product_id, url, self._on_thumbnail_loaded)

    def _on_thumbnail_loaded(self, product_id, file_path):
        """Callback when thumbnail is downloaded."""
        if not self._alive or product_id != self._product_id:
            return
        if not file_path or not os.path.isfile(file_path):
            return
        try:
            pixmap = QtGui.QPixmap(file_path)
            if not pixmap.isNull():
                scaled = pixmap.scaled(
                    24, 24,
                    QtCore.Qt.KeepAspectRatio,
                    QtCore.Qt.SmoothTransformation,
                )
                self._thumb_label.setPixmap(scaled)
        except RuntimeError:
            pass  # Widget already deleted

    def get_product_id(self):
        return self._product_id

    def set_selected(self, selected):
        self._selected = selected
        self._apply_style(selected)

    def cleanup(self):
        self._alive = False

    def resize_card(self, new_size):
        pass

    def mousePressEvent(self, event):
        if event.button() == QtCore.Qt.LeftButton:
            self.clicked.emit(self._product_id)
        super().mousePressEvent(event)

    def mouseDoubleClickEvent(self, event):
        if event.button() == QtCore.Qt.LeftButton:
            self.double_clicked.emit(self._product_id)
        super().mouseDoubleClickEvent(event)

    def contextMenuEvent(self, event):
        self.context_menu_requested.emit(self._product_id, event.globalPos())

    def enterEvent(self, event):
        if not self._selected:
            self.setStyleSheet(
                "BgenLibraryListItem { background: rgba(255,255,255,0.08); "
                "border: 1px solid rgba(255,255,255,0.12); border-radius: 4px; }"
            )
        super().enterEvent(event)

    def leaveEvent(self, event):
        self._apply_style(self._selected)
        super().leaveEvent(event)

    def _apply_style(self, selected):
        if selected:
            self.setStyleSheet(
                "BgenLibraryListItem { background: rgba(29,101,202,0.25); "
                "border: 1px solid rgba(29,101,202,0.6); border-radius: 4px; }"
            )
        else:
            self.setStyleSheet(
                "BgenLibraryListItem { background: rgba(255,255,255,0.02); "
                "border: 1px solid transparent; border-radius: 4px; }"
            )


# ---------------------------------------------------------------------------
# BgenLibraryGridController -- manages the Catalogue grid
# ---------------------------------------------------------------------------

class BgenLibraryGridController(QtCore.QObject):
    """Manages the BGEN Library catalogue grid of BgenLibraryCards."""

    product_action_requested = QtCore.Signal(str, str)  # product_id, action
    card_selected = QtCore.Signal(str)  # product_id on single click

    def __init__(self, grid_layout, grid_container, scroll_area, parent_window, bgen_library_manager):
        super().__init__(parent_window)
        self._grid = grid_layout
        self._container = grid_container
        self._scroll = scroll_area
        self._window = parent_window
        self._mgr = bgen_library_manager
        self._cards = {}           # product_id -> BgenLibraryCard
        self._selected_id = None
        self._sort_mode = "featured"
        self._search_text = ""
        self._category = "All"
        self._card_size = CFG.LIBRARY_CARD_SIZE
        self._view_mode = "medium"
        self._product_ids_filter = None  # Optional set of product IDs to show
        self._last_col_count = 0
        self._ordered_keys = []

        # Debounce timer for resize — relayout only, no recreation
        self._resize_timer = QtCore.QTimer(self)
        self._resize_timer.setSingleShot(True)
        self._resize_timer.setInterval(150)
        self._resize_timer.timeout.connect(self._relayout)

        self._scroll.viewport().installEventFilter(self)

        # Refresh when catalog changes
        self._mgr.catalog_updated.connect(self.refresh)

    def cleanup(self):
        try:
            self._scroll.viewport().removeEventFilter(self)
        except Exception:
            pass

    def eventFilter(self, obj, event):
        if event.type() == QtCore.QEvent.Resize and obj is self._scroll.viewport():
            self._resize_timer.start()
        return False

    # ---- filter/sort ----

    def set_category(self, category):
        self._category = category
        self.refresh()

    def set_search_text(self, text):
        self._search_text = text.strip()
        self.refresh()

    def set_sort_mode(self, mode):
        self._sort_mode = mode
        self.refresh()

    def set_view_mode(self, mode):
        """Change view mode: small|medium|large|list."""
        self._view_mode = mode
        size = MKT_VIEW_SIZES.get(mode, MKT_VIEW_SIZES["medium"])
        if size > 0:
            self._card_size = size
        self.refresh()

    def set_product_ids_filter(self, product_ids):
        """Filter catalogue to only show products in *product_ids*.

        Pass ``None`` to clear the filter and show all products.
        """
        self._product_ids_filter = set(product_ids) if product_ids else None
        self.refresh()

    def clear_filters(self):
        """Reset all filters to default state."""
        self._category = "All"
        self._search_text = ""
        self._sort_mode = "featured"
        self._product_ids_filter = None
        self.refresh()

    # ---- refresh / relayout ----

    def _clear_grid(self):
        while self._grid.count():
            item = self._grid.takeAt(0)
            w = item.widget()
            if w is not None:
                if hasattr(w, "cleanup"):
                    w.cleanup()
                w.deleteLater()

    def refresh(self):
        """Rebuild the grid from scratch (data change)."""
        self._clear_grid()
        self._cards.clear()
        self._selected_id = None
        self._last_col_count = 0

        products = self._mgr.get_products(
            category=self._category if self._category != "All" else None,
            search=self._search_text or None,
            sort=self._sort_mode,
        )

        # Apply product IDs filter (used by collection/section navigation)
        if self._product_ids_filter is not None:
            products = [p for p in products if p.get("id") in self._product_ids_filter]

        if not products:
            self._ordered_keys = []
            offline_label = QtWidgets.QLabel("Store Offline")
            offline_label.setStyleSheet(
                "font-size: 14px; font-weight: bold; color: #888; padding: 40px;"
            )
            offline_label.setAlignment(QtCore.Qt.AlignCenter)
            self._grid.addWidget(offline_label, 0, 0)
            return

        self._ordered_keys = [p.get("id", "") for p in products]

        if self._view_mode == "list":
            for i, product in enumerate(products):
                item = BgenLibraryListItem(product, parent=self._container)
                item.clicked.connect(self._on_card_clicked)
                item.double_clicked.connect(self._on_card_double_clicked)
                item.context_menu_requested.connect(self._on_card_context_menu)
                self._grid.addWidget(item, i, 0)
                self._cards[product.get("id", "")] = item
        else:
            spacing = self._grid.spacing()
            margins = self._grid.contentsMargins()
            viewport_w = self._scroll.viewport().width() - margins.left() - margins.right()
            card_slot = self._card_size + spacing
            max_cols = max(1, int(viewport_w // card_slot))
            dynamic_size = max(self._card_size, int(
                (viewport_w - spacing * (max_cols - 1)) / max_cols
            )) if max_cols > 0 else self._card_size
            self._last_col_count = max_cols

            for i, product in enumerate(products):
                card = BgenLibraryCard(product, parent=self._container, card_size=dynamic_size)
                card.clicked.connect(self._on_card_clicked)
                card.double_clicked.connect(self._on_card_double_clicked)
                card.context_menu_requested.connect(self._on_card_context_menu)
                self._grid.addWidget(card, i // max_cols, i % max_cols)
                self._cards[product.get("id", "")] = card

    def _relayout(self):
        """Reposition and resize existing cards on viewport resize (no recreation)."""
        if not self._cards or self._view_mode == "list":
            return

        spacing = self._grid.spacing()
        margins = self._grid.contentsMargins()
        viewport_w = self._scroll.viewport().width() - margins.left() - margins.right()
        if viewport_w <= 0:
            return

        card_slot = self._card_size + spacing
        max_cols = max(1, int(viewport_w // card_slot))

        if max_cols == self._last_col_count:
            return
        self._last_col_count = max_cols

        dynamic_size = max(self._card_size, int(
            (viewport_w - spacing * (max_cols - 1)) / max_cols
        )) if max_cols > 0 else self._card_size

        while self._grid.count():
            self._grid.takeAt(0)

        for i, key in enumerate(self._ordered_keys):
            card = self._cards.get(key)
            if card:
                card.resize_card(dynamic_size)
                self._grid.addWidget(card, i // max_cols, i % max_cols)

    # ---- card actions ----

    def _on_card_clicked(self, product_id):
        if self._selected_id and self._selected_id in self._cards:
            self._cards[self._selected_id].set_selected(False)
        self._selected_id = product_id
        if product_id in self._cards:
            self._cards[product_id].set_selected(True)
        self.card_selected.emit(product_id)

    def _on_card_double_clicked(self, product_id):
        self._on_card_clicked(product_id)
        self.product_action_requested.emit(product_id, "view_details")

    def _on_card_context_menu(self, product_id, global_pos):
        self._on_card_clicked(product_id)

        # Find the product data
        product = None
        for p in self._mgr.get_products():
            if p.get("id") == product_id:
                product = p
                break
        if not product:
            return

        menu = QtWidgets.QMenu(self._window)
        menu.setStyleSheet("""
            QMenu {
                background-color: #2a2a2a; color: #dddddd;
                border: 1px solid #3a3a3a; border-radius: 4px; padding: 4px;
            }
            QMenu::item { padding: 5px 20px; border-radius: 3px; }
            QMenu::item:selected { background-color: rgba(29,101,202,0.4); }
        """)

        view_action = menu.addAction("View Details")
        menu.addSeparator()

        owned = product.get("owned", False)
        price_cents = product.get("price_cents", 0)

        if owned:
            download_action = menu.addAction("Download")
            buy_action = None
        elif price_cents == 0:
            download_action = None
            buy_action = menu.addAction("Get Free")
        else:
            download_action = None
            buy_action = menu.addAction(f"Buy {self._mgr.format_price(product)}")

        action = menu.exec_(global_pos)
        if not action:
            return

        if action == view_action:
            self.product_action_requested.emit(product_id, "view_details")
        elif download_action and action == download_action:
            self.product_action_requested.emit(product_id, "download")
        elif buy_action and action == buy_action:
            self.product_action_requested.emit(product_id, "buy")


# ---------------------------------------------------------------------------
# Shared scroll-bar stylesheets
# ---------------------------------------------------------------------------

_VSCROLL_STYLE = (
    "QScrollArea { background: transparent; border: none; }"
    "QScrollBar:vertical {"
    "    border: none; background: rgba(30, 30, 30, 0.3);"
    "    width: 8px; margin: 0px;"
    "}"
    "QScrollBar::handle:vertical {"
    "    background: rgba(100, 100, 100, 0.5);"
    "    min-height: 20px; border-radius: 4px;"
    "}"
    "QScrollBar::handle:vertical:hover {"
    "    background: rgba(120, 120, 120, 0.7);"
    "}"
    "QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {"
    "    height: 0px; background: transparent;"
    "}"
    "QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {"
    "    background: transparent;"
    "}"
)

_HSCROLL_STYLE = (
    "QScrollArea { background: transparent; border: none; }"
    "QScrollBar:horizontal {"
    "    border: none; background: transparent;"
    "    height: 6px; margin: 0px;"
    "}"
    "QScrollBar::handle:horizontal {"
    "    background: rgba(100, 100, 100, 0.4);"
    "    min-width: 20px; border-radius: 3px;"
    "}"
    "QScrollBar::handle:horizontal:hover {"
    "    background: rgba(120, 120, 120, 0.7);"
    "}"
    "QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {"
    "    width: 0px;"
    "}"
    "QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal {"
    "    background: transparent;"
    "}"
)


# ---------------------------------------------------------------------------
# _DotIndicator — clickable carousel dots
# ---------------------------------------------------------------------------

class _DotIndicator(QtWidgets.QWidget):
    """Row of small dot indicators for a carousel."""

    dot_clicked = QtCore.Signal(int)

    def __init__(self, count, parent=None):
        super().__init__(parent)
        self._count = count
        self._current = 0
        self.setFixedHeight(12)
        self.setFixedWidth(max(1, count * 14))
        self.setCursor(QtCore.Qt.PointingHandCursor)

    def set_current(self, index):
        self._current = index
        self.update()

    def paintEvent(self, event):
        painter = QtGui.QPainter(self)
        painter.setRenderHint(QtGui.QPainter.Antialiasing)
        dot_size = 6
        gap = 8
        total_w = self._count * dot_size + (self._count - 1) * gap
        x = (self.width() - total_w) / 2
        y = (self.height() - dot_size) / 2
        for i in range(self._count):
            if i == self._current:
                painter.setBrush(QtGui.QColor(255, 255, 255, 220))
            else:
                painter.setBrush(QtGui.QColor(255, 255, 255, 60))
            painter.setPen(QtCore.Qt.NoPen)
            painter.drawEllipse(QtCore.QRectF(x, y, dot_size, dot_size))
            x += dot_size + gap
        painter.end()

    def mousePressEvent(self, event):
        dot_size = 6
        gap = 8
        total_w = self._count * dot_size + (self._count - 1) * gap
        start_x = (self.width() - total_w) / 2
        for i in range(self._count):
            left = start_x + i * (dot_size + gap)
            if left - 4 <= event.pos().x() <= left + dot_size + 4:
                self.dot_clicked.emit(i)
                return
        super().mousePressEvent(event)


# ---------------------------------------------------------------------------
# _HeroSlideWidget — single painted slide for the carousel
# ---------------------------------------------------------------------------

class _HeroSlideWidget(QtWidgets.QWidget):
    """Individual hero slide with painted gradient background, optional
    product thumbnail on the right, and overlay text on the left."""

    clicked = QtCore.Signal(str)

    def __init__(self, slide_data, parent=None):
        super().__init__(parent)
        self._alive = True
        self._data = slide_data
        self._accent = QtGui.QColor(slide_data.get("accent_color", "#1D65CA"))
        self._bg_pixmap = None  # loaded async
        self.setCursor(QtCore.Qt.PointingHandCursor)

        # Overlay layout — text and CTA pinned to bottom-left
        overlay = QtWidgets.QVBoxLayout(self)
        overlay.setContentsMargins(12, 8, 12, 10)
        overlay.addStretch()

        self._headline = QtWidgets.QLabel(slide_data.get("headline", ""))
        self._headline.setWordWrap(True)
        self._headline.setStyleSheet(
            "color: #ffffff; font-size: 14px; font-weight: bold; "
            "background: transparent; border: none;"
        )
        overlay.addWidget(self._headline)

        self._subtitle = QtWidgets.QLabel(slide_data.get("subtitle", ""))
        self._subtitle.setStyleSheet(
            "color: rgba(255,255,255,0.7); font-size: 10px; "
            "background: transparent; border: none;"
        )
        self._subtitle.setWordWrap(True)
        overlay.addWidget(self._subtitle)

        overlay.addSpacing(2)

        cta = QtWidgets.QPushButton(slide_data.get("cta_text", "Explore"))
        cta.setFixedHeight(22)
        cta.setMaximumWidth(80)
        cta.setCursor(QtCore.Qt.PointingHandCursor)
        cta.setStyleSheet(
            "QPushButton { background: rgba(255,255,255,0.15); color: white; "
            "border: 1px solid rgba(255,255,255,0.25); border-radius: 4px; "
            "font-size: 10px; font-weight: bold; padding: 0 10px; }"
            "QPushButton:hover { background: rgba(255,255,255,0.25); }"
        )
        cta.clicked.connect(
            lambda: self.clicked.emit(slide_data.get("product_id", ""))
        )
        overlay.addWidget(cta)

        # Kick off thumbnail load from the attached product data
        self._load_thumbnail(slide_data)

    def _load_thumbnail(self, slide_data):
        """Start async thumbnail download for the slide's product."""
        product = slide_data.get("product")
        if not product:
            return
        mgr = BgenLocalFileManager.get_instance()
        url = mgr.get_thumbnail_url(product)
        if not url:
            return
        product_id = product.get("id", slide_data.get("product_id", ""))
        mgr.load_thumbnail_async(product_id, url, self._on_thumbnail_loaded)

    def _on_thumbnail_loaded(self, _product_id, file_path):
        if not self._alive:
            return
        try:
            pm = QtGui.QPixmap(file_path)
            if not pm.isNull():
                self._bg_pixmap = pm
                self.update()
        except RuntimeError:
            pass

    def paintEvent(self, event):
        painter = QtGui.QPainter(self)
        painter.setRenderHint(QtGui.QPainter.Antialiasing)
        painter.setRenderHint(QtGui.QPainter.SmoothPixmapTransform)
        w, h = self.width(), self.height()

        rect = QtCore.QRectF(0, 0, w, h)
        path = QtGui.QPainterPath()
        path.addRoundedRect(rect, 10, 10)
        painter.setClipPath(path)

        # Base dark fill
        painter.fillRect(rect, QtGui.QColor(28, 28, 32))

        # Accent radial gradient (top-right area)
        accent = QtGui.QColor(self._accent)
        accent.setAlpha(50)
        radial = QtGui.QRadialGradient(w * 0.75, h * 0.2, w * 0.7)
        radial.setColorAt(0, accent)
        radial.setColorAt(1, QtGui.QColor(28, 28, 32, 0))
        painter.fillRect(rect, radial)

        if self._bg_pixmap:
            # Draw thumbnail on the right portion, scaled to fill height
            pm = self._bg_pixmap
            scale = h / pm.height() if pm.height() > 0 else 1
            draw_w = int(pm.width() * scale)
            draw_h = int(h)
            # Right-align the image
            x = w - draw_w
            painter.setOpacity(0.55)
            painter.drawPixmap(
                QtCore.QRectF(x, 0, draw_w, draw_h),
                pm,
                QtCore.QRectF(0, 0, pm.width(), pm.height()),
            )
            painter.setOpacity(1.0)

            # Left-to-right gradient so text stays readable
            lr_grad = QtGui.QLinearGradient(0, 0, w * 0.55, 0)
            lr_grad.setColorAt(0, QtGui.QColor(28, 28, 32, 255))
            lr_grad.setColorAt(0.7, QtGui.QColor(28, 28, 32, 200))
            lr_grad.setColorAt(1, QtGui.QColor(28, 28, 32, 0))
            painter.fillRect(rect, lr_grad)
        else:
            # Decorative large letter fallback (right side, subtle)
            headline = self._data.get("headline", "?")
            letter = headline[0].upper() if headline else "?"
            font = painter.font()
            font.setPixelSize(max(80, int(h * 1.1)))
            font.setBold(True)
            painter.setFont(font)
            painter.setPen(QtGui.QColor(255, 255, 255, 12))
            painter.drawText(
                QtCore.QRectF(w * 0.35, -h * 0.15, w * 0.7, h * 1.3),
                QtCore.Qt.AlignCenter, letter,
            )

        # Bottom gradient for text readability
        bottom_grad = QtGui.QLinearGradient(0, h * 0.25, 0, h)
        bottom_grad.setColorAt(0, QtGui.QColor(0, 0, 0, 0))
        bottom_grad.setColorAt(1, QtGui.QColor(0, 0, 0, 170))
        painter.fillRect(rect, bottom_grad)

        # Thin border
        painter.setClipping(False)
        painter.setPen(QtGui.QPen(QtGui.QColor(255, 255, 255, 18), 1))
        painter.setBrush(QtCore.Qt.NoBrush)
        painter.drawRoundedRect(rect.adjusted(0.5, 0.5, -0.5, -0.5), 10, 10)

        painter.end()

    def mousePressEvent(self, event):
        if event.button() == QtCore.Qt.LeftButton:
            self.clicked.emit(self._data.get("product_id", ""))
        super().mousePressEvent(event)


# ---------------------------------------------------------------------------
# HeroCarouselWidget — auto-rotating hero banner
# ---------------------------------------------------------------------------

class HeroCarouselWidget(QtWidgets.QWidget):
    """Auto-rotating hero carousel with dot indicators."""

    product_clicked = QtCore.Signal(str)

    def __init__(self, slides_data, parent=None):
        super().__init__(parent)
        self._current_index = 0
        self._num_slides = len(slides_data)

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        # Stacked slides
        self._stack = QtWidgets.QStackedWidget()
        self._stack.setMinimumHeight(100)
        self._stack.setMaximumHeight(160)
        for sd in slides_data:
            slide = _HeroSlideWidget(sd, self)
            slide.clicked.connect(self.product_clicked.emit)
            self._stack.addWidget(slide)
        layout.addWidget(self._stack)

        # Dot indicators
        self._dots = _DotIndicator(self._num_slides, self)
        self._dots.dot_clicked.connect(self._go_to_slide)
        layout.addWidget(self._dots, 0, QtCore.Qt.AlignCenter)

        # Auto-rotation timer
        self._timer = QtCore.QTimer(self)
        self._timer.setInterval(8000)
        self._timer.timeout.connect(self._next_slide)
        if self._num_slides > 1:
            self._timer.start()

    def _next_slide(self):
        self._current_index = (self._current_index + 1) % self._num_slides
        self._stack.setCurrentIndex(self._current_index)
        self._dots.set_current(self._current_index)

    def _go_to_slide(self, index):
        self._current_index = index
        self._stack.setCurrentIndex(index)
        self._dots.set_current(index)
        # Reset timer on manual navigation
        self._timer.stop()
        if self._num_slides > 1:
            self._timer.start()

    def enterEvent(self, event):
        self._timer.stop()
        super().enterEvent(event)

    def leaveEvent(self, event):
        if self._num_slides > 1:
            self._timer.start()
        super().leaveEvent(event)

    def cleanup(self):
        self._timer.stop()


# ---------------------------------------------------------------------------
# SectionRowWidget — title + "View All" + horizontal card strip
# ---------------------------------------------------------------------------

class SectionRowWidget(QtWidgets.QWidget):
    """Reusable explore section: header row + horizontal scrollable cards."""

    product_clicked = QtCore.Signal(str)
    view_all_clicked = QtCore.Signal(str)  # section slug

    def __init__(self, title, slug, products, mgr, card_size=None, parent=None):
        super().__init__(parent)
        self._slug = slug
        self._cards = []
        cs = card_size if card_size is not None else CFG.LIBRARY_CARD_SIZE + 16

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        # Header row
        header = QtWidgets.QHBoxLayout()
        header.setContentsMargins(0, 0, 0, 0)
        title_lbl = QtWidgets.QLabel(title)
        title_lbl.setStyleSheet(
            "color: #e0e0e0; font-size: 13px; font-weight: bold; "
            "background: transparent; border: none;"
        )
        sp = title_lbl.sizePolicy()
        sp.setHorizontalPolicy(QtWidgets.QSizePolicy.Ignored)
        title_lbl.setSizePolicy(sp)
        header.addWidget(title_lbl, 1)

        view_all = QtWidgets.QPushButton("View All  \u203a")
        view_all.setCursor(QtCore.Qt.PointingHandCursor)
        view_all.setStyleSheet(
            "QPushButton { color: #5b9bd5; font-size: 10px; "
            "background: transparent; border: none; padding: 0; }"
            "QPushButton:hover { color: #7db8f0; }"
        )
        view_all.clicked.connect(lambda: self.view_all_clicked.emit(slug))
        header.addWidget(view_all)
        layout.addLayout(header)

        # Card strip container (with scroll arrows)
        _strip_pad = 60  # extra vertical room to avoid capturing vertical scrolls
        strip_container = QtWidgets.QWidget()
        strip_container.setMinimumHeight(cs + _strip_pad)
        strip_stack = QtWidgets.QHBoxLayout(strip_container)
        strip_stack.setContentsMargins(0, 0, 0, 0)
        strip_stack.setSpacing(0)

        # Left scroll arrow
        self._left_arrow = QtWidgets.QPushButton("\u2039")
        self._left_arrow.setFixedWidth(18)
        self._left_arrow.setCursor(QtCore.Qt.PointingHandCursor)
        self._left_arrow.setStyleSheet(
            "QPushButton { background: rgba(0,0,0,0.3); color: rgba(255,255,255,0.6); "
            "border: none; border-radius: 4px; font-size: 16px; }"
            "QPushButton:hover { background: rgba(0,0,0,0.5); color: white; }"
        )
        self._left_arrow.hide()
        strip_stack.addWidget(self._left_arrow)

        # Horizontal scroll area
        self._h_scroll = QtWidgets.QScrollArea()
        self._h_scroll.setMinimumHeight(cs + _strip_pad)
        self._h_scroll.setWidgetResizable(True)
        self._h_scroll.setFrameShape(QtWidgets.QFrame.NoFrame)
        self._h_scroll.setVerticalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)
        self._h_scroll.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarAsNeeded)
        self._h_scroll.setStyleSheet(_HSCROLL_STYLE)

        row_widget = QtWidgets.QWidget()
        row_layout = QtWidgets.QHBoxLayout(row_widget)
        row_layout.setContentsMargins(0, 0, 0, 0)
        row_layout.setSpacing(6)

        for product in products:
            card = BgenLibraryCard(product, parent=row_widget, card_size=cs)
            card.clicked.connect(self.product_clicked.emit)
            row_layout.addWidget(card)
            self._cards.append(card)
        row_layout.addStretch()

        self._h_scroll.setWidget(row_widget)
        strip_stack.addWidget(self._h_scroll, 1)

        # Right scroll arrow
        self._right_arrow = QtWidgets.QPushButton("\u203a")
        self._right_arrow.setFixedWidth(18)
        self._right_arrow.setCursor(QtCore.Qt.PointingHandCursor)
        self._right_arrow.setStyleSheet(
            "QPushButton { background: rgba(0,0,0,0.3); color: rgba(255,255,255,0.6); "
            "border: none; border-radius: 4px; font-size: 16px; }"
            "QPushButton:hover { background: rgba(0,0,0,0.5); color: white; }"
        )
        strip_stack.addWidget(self._right_arrow)

        # Scroll arrow connections
        scroll_step = cs + 6
        self._left_arrow.clicked.connect(
            lambda: self._h_scroll.horizontalScrollBar().setValue(
                self._h_scroll.horizontalScrollBar().value() - scroll_step
            )
        )
        self._right_arrow.clicked.connect(
            lambda: self._h_scroll.horizontalScrollBar().setValue(
                self._h_scroll.horizontalScrollBar().value() + scroll_step
            )
        )
        self._h_scroll.horizontalScrollBar().valueChanged.connect(self._update_arrows)

        layout.addWidget(strip_container)

        # Deferred arrow visibility check
        QtCore.QTimer.singleShot(0, self._update_arrows)

    def _update_arrows(self):
        sb = self._h_scroll.horizontalScrollBar()
        self._left_arrow.setVisible(sb.value() > sb.minimum())
        self._right_arrow.setVisible(sb.value() < sb.maximum())

    def cleanup(self):
        for c in self._cards:
            c.cleanup()


# ---------------------------------------------------------------------------
# _CollectionCard — single clickable collection card with mosaic
# ---------------------------------------------------------------------------

class _CollectionCard(QtWidgets.QWidget):
    """Clickable card representing a collection with a 2x2 thumbnail mosaic."""

    clicked = QtCore.Signal(str)  # collection slug

    def __init__(self, collection, mgr, parent=None):
        super().__init__(parent)
        self._slug = collection.get("slug", "")
        self._name = collection.get("name", "Collection")
        self._accent = QtGui.QColor(collection.get("accent", "#1D65CA"))
        self._products = collection.get("products", [])
        self._mgr = mgr
        self._count = len(collection.get("product_ids", []))
        self.setCursor(QtCore.Qt.PointingHandCursor)

    def paintEvent(self, event):
        painter = QtGui.QPainter(self)
        painter.setRenderHint(QtGui.QPainter.Antialiasing)
        w, h = self.width(), self.height()

        # Card background with accent gradient
        rect = QtCore.QRectF(0, 0, w, h)
        path = QtGui.QPainterPath()
        path.addRoundedRect(rect, 8, 8)
        painter.setClipPath(path)

        painter.fillRect(rect, QtGui.QColor(32, 32, 38))

        accent = QtGui.QColor(self._accent)
        accent.setAlpha(40)
        grad = QtGui.QLinearGradient(0, 0, w, h)
        grad.setColorAt(0, accent)
        grad.setColorAt(1, QtGui.QColor(32, 32, 38, 0))
        painter.fillRect(rect, grad)

        # 2x2 thumbnail mosaic (top-right area, scales with card size)
        mosaic_size = min(h - 28, int(w * 0.35))
        if mosaic_size > 16:
            cell = (mosaic_size - 2) // 2
            mx = w - mosaic_size - 8
            my = 8
            for i, p in enumerate(self._products[:4]):
                cx = mx + (i % 2) * (cell + 2)
                cy = my + (i // 2) * (cell + 2)
                painter.setBrush(QtGui.QColor(50, 52, 60))
                painter.setPen(QtCore.Qt.NoPen)
                painter.drawRoundedRect(QtCore.QRectF(cx, cy, cell, cell), 3, 3)
                # Draw initial letter
                name = p.get("name", "?")
                letter = name[0].upper() if name else "?"
                font = painter.font()
                font.setPixelSize(max(8, cell // 2))
                font.setBold(True)
                painter.setFont(font)
                painter.setPen(QtGui.QColor(120, 130, 150))
                painter.drawText(
                    QtCore.QRectF(cx, cy, cell, cell),
                    QtCore.Qt.AlignCenter, letter,
                )

        # Collection name (bottom-left, elide if needed)
        painter.setClipping(False)
        font = painter.font()
        font.setPixelSize(11)
        font.setBold(True)
        painter.setFont(font)
        painter.setPen(QtGui.QColor(230, 230, 230))
        text_w = w - 20
        fm = QtGui.QFontMetrics(font)
        elided_name = fm.elidedText(self._name, QtCore.Qt.ElideRight, int(text_w))
        painter.drawText(
            QtCore.QRectF(10, h - 30, text_w, 16),
            QtCore.Qt.AlignLeft | QtCore.Qt.AlignVCenter,
            elided_name,
        )

        # Item count
        font.setPixelSize(9)
        font.setBold(False)
        painter.setFont(font)
        painter.setPen(QtGui.QColor(150, 150, 150))
        painter.drawText(
            QtCore.QRectF(10, h - 16, text_w, 12),
            QtCore.Qt.AlignLeft | QtCore.Qt.AlignVCenter,
            f"{self._count} rigs",
        )

        # Border
        painter.setPen(QtGui.QPen(QtGui.QColor(255, 255, 255, 14), 1))
        painter.setBrush(QtCore.Qt.NoBrush)
        painter.drawRoundedRect(rect.adjusted(0.5, 0.5, -0.5, -0.5), 8, 8)
        painter.end()

    def enterEvent(self, event):
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event):
        self.update()
        super().leaveEvent(event)

    def mousePressEvent(self, event):
        if event.button() == QtCore.Qt.LeftButton:
            self.clicked.emit(self._slug)
        super().mousePressEvent(event)


# ---------------------------------------------------------------------------
# CollectionGridWidget — 2-column grid of collection cards
# ---------------------------------------------------------------------------

class CollectionGridWidget(QtWidgets.QWidget):
    """2-column grid of collection banner cards.  Adapts to width."""

    collection_clicked = QtCore.Signal(str)

    def __init__(self, title, collections, mgr, parent=None):
        super().__init__(parent)
        self._collections = collections
        self._mgr = mgr
        self._cards = []

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        # Header
        title_lbl = QtWidgets.QLabel(title)
        title_lbl.setStyleSheet(
            "color: #e0e0e0; font-size: 13px; font-weight: bold; "
            "background: transparent; border: none;"
        )
        layout.addWidget(title_lbl)

        # 2-column grid
        self._grid = QtWidgets.QGridLayout()
        self._grid.setSpacing(6)
        self._grid.setContentsMargins(0, 0, 0, 0)

        for i, coll in enumerate(collections):
            card = _CollectionCard(coll, mgr, self)
            card.setMinimumHeight(72)
            card.setMaximumHeight(100)
            card.clicked.connect(self.collection_clicked.emit)
            self._grid.addWidget(card, i // 2, i % 2)
            self._cards.append(card)

        layout.addLayout(self._grid)


# ---------------------------------------------------------------------------
# CreatorSpotlightWidget — featured creator + their products
# ---------------------------------------------------------------------------

class CreatorSpotlightWidget(QtWidgets.QWidget):
    """Full-width creator spotlight with avatar, bio, and product row."""

    product_clicked = QtCore.Signal(str)

    def __init__(self, title, creator_info, products, mgr, card_size=None, parent=None):
        super().__init__(parent)
        cs = card_size if card_size is not None else CFG.LIBRARY_CARD_SIZE + 16

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        # Section header
        title_lbl = QtWidgets.QLabel(title)
        title_lbl.setStyleSheet(
            "color: #e0e0e0; font-size: 13px; font-weight: bold; "
            "background: transparent; border: none;"
        )
        layout.addWidget(title_lbl)

        # Creator card
        card = QtWidgets.QFrame()
        card.setStyleSheet(
            "QFrame { background: rgba(255,255,255,0.03); "
            "border: 1px solid rgba(255,255,255,0.06); border-radius: 10px; }"
        )
        card_layout = QtWidgets.QVBoxLayout(card)
        card_layout.setContentsMargins(12, 12, 12, 10)
        card_layout.setSpacing(8)

        # Creator info row
        info_row = QtWidgets.QHBoxLayout()
        info_row.setSpacing(10)

        # Avatar circle
        avatar_color = QtGui.QColor(creator_info.get("avatar_color", "#1D65CA"))
        creator_name = creator_info.get("name", "?")
        avatar_label = QtWidgets.QLabel()
        avatar_size = 36
        avatar_label.setFixedSize(avatar_size, avatar_size)
        pix = QtGui.QPixmap(avatar_size, avatar_size)
        pix.fill(QtGui.QColor(0, 0, 0, 0))
        p = QtGui.QPainter(pix)
        p.setRenderHint(QtGui.QPainter.Antialiasing)
        p.setBrush(avatar_color)
        p.setPen(QtCore.Qt.NoPen)
        p.drawEllipse(0, 0, avatar_size, avatar_size)
        font = p.font()
        font.setPixelSize(14)
        font.setBold(True)
        p.setFont(font)
        p.setPen(QtGui.QColor(255, 255, 255))
        p.drawText(
            QtCore.QRect(0, 0, avatar_size, avatar_size),
            QtCore.Qt.AlignCenter,
            creator_name[0].upper() if creator_name else "?",
        )
        p.end()
        avatar_label.setPixmap(pix)
        avatar_label.setStyleSheet("border: none; background: transparent;")
        info_row.addWidget(avatar_label)

        # Name + bio
        text_col = QtWidgets.QVBoxLayout()
        text_col.setSpacing(2)
        name_lbl = QtWidgets.QLabel(creator_name)
        name_lbl.setStyleSheet(
            "color: #e0e0e0; font-size: 12px; font-weight: bold; "
            "background: transparent; border: none;"
        )
        text_col.addWidget(name_lbl)

        bio = creator_info.get("bio", "")
        if bio:
            bio_lbl = QtWidgets.QLabel(bio)
            bio_lbl.setStyleSheet(
                "color: #888888; font-size: 10px; "
                "background: transparent; border: none;"
            )
            bio_lbl.setWordWrap(True)
            text_col.addWidget(bio_lbl)

        info_row.addLayout(text_col, 1)
        card_layout.addLayout(info_row)

        # Product row (horizontal, scrollable)
        if products:
            prod_scroll = QtWidgets.QScrollArea()
            prod_scroll.setWidgetResizable(True)
            prod_scroll.setFrameShape(QtWidgets.QFrame.NoFrame)
            prod_scroll.setVerticalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)
            prod_scroll.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarAsNeeded)
            prod_scroll.setStyleSheet(_HSCROLL_STYLE)
            prod_scroll.setMinimumHeight(cs + 46)

            prod_widget = QtWidgets.QWidget()
            prod_row = QtWidgets.QHBoxLayout(prod_widget)
            prod_row.setContentsMargins(0, 0, 0, 0)
            prod_row.setSpacing(6)
            for product in products[:4]:
                pc = BgenLibraryCard(product, parent=prod_widget, card_size=cs)
                pc.clicked.connect(self.product_clicked.emit)
                prod_row.addWidget(pc)
            prod_row.addStretch()

            prod_scroll.setWidget(prod_widget)
            card_layout.addWidget(prod_scroll)

        layout.addWidget(card)


# ---------------------------------------------------------------------------
# CreatorStripWidget — horizontal scrollable creator avatar strip
# ---------------------------------------------------------------------------

class CreatorStripWidget(QtWidgets.QWidget):
    """Horizontal strip of circular creator avatars with 'View All' button.

    Replaces the single-creator spotlight on the Explore page with a
    scrollable row of all approved creators.
    """

    creator_clicked = QtCore.Signal(str)   # creator_id
    view_all_clicked = QtCore.Signal()

    def __init__(self, title, creators, mgr, parent=None):
        super().__init__(parent)
        self._mgr = mgr
        self._avatar_items = []  # list of (creator_id, label_widget)

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        # Header row: title + "View All"
        header = QtWidgets.QHBoxLayout()
        header.setContentsMargins(0, 0, 0, 0)
        title_lbl = QtWidgets.QLabel(title)
        title_lbl.setStyleSheet(
            "color: #e0e0e0; font-size: 13px; font-weight: bold; "
            "background: transparent; border: none;"
        )
        sp = title_lbl.sizePolicy()
        sp.setHorizontalPolicy(QtWidgets.QSizePolicy.Ignored)
        title_lbl.setSizePolicy(sp)
        header.addWidget(title_lbl, 1)

        view_all_btn = QtWidgets.QPushButton("View All  \u203a")
        view_all_btn.setCursor(QtCore.Qt.PointingHandCursor)
        view_all_btn.setStyleSheet(
            "QPushButton { color: #5b9bd5; font-size: 10px; "
            "background: transparent; border: none; padding: 0; }"
            "QPushButton:hover { color: #7db8f0; }"
        )
        view_all_btn.clicked.connect(self.view_all_clicked.emit)
        header.addWidget(view_all_btn)
        layout.addLayout(header)

        # Horizontal scroll area for avatars
        avatar_size = CFG.CREATOR_STRIP_AVATAR_SIZE
        strip_height = avatar_size + 28  # avatar + name + margins

        strip_container = QtWidgets.QWidget()
        strip_container.setMinimumHeight(strip_height + 10)
        strip_stack = QtWidgets.QHBoxLayout(strip_container)
        strip_stack.setContentsMargins(0, 0, 0, 0)
        strip_stack.setSpacing(0)

        # Left scroll arrow
        self._left_arrow = QtWidgets.QPushButton("\u2039")
        self._left_arrow.setFixedWidth(18)
        self._left_arrow.setCursor(QtCore.Qt.PointingHandCursor)
        self._left_arrow.setStyleSheet(
            "QPushButton { background: rgba(0,0,0,0.3); color: rgba(255,255,255,0.6); "
            "border: none; border-radius: 4px; font-size: 16px; }"
            "QPushButton:hover { background: rgba(0,0,0,0.5); color: white; }"
        )
        self._left_arrow.hide()
        strip_stack.addWidget(self._left_arrow)

        # Scroll area
        self._h_scroll = QtWidgets.QScrollArea()
        self._h_scroll.setMinimumHeight(strip_height + 10)
        self._h_scroll.setWidgetResizable(True)
        self._h_scroll.setFrameShape(QtWidgets.QFrame.NoFrame)
        self._h_scroll.setVerticalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)
        self._h_scroll.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarAsNeeded)
        self._h_scroll.setStyleSheet(_HSCROLL_STYLE)

        row_widget = QtWidgets.QWidget()
        self._row_layout = QtWidgets.QHBoxLayout(row_widget)
        self._row_layout.setContentsMargins(0, 4, 0, 4)
        self._row_layout.setSpacing(16)

        self._populate_avatars(creators, avatar_size)

        self._row_layout.addStretch()
        self._h_scroll.setWidget(row_widget)
        strip_stack.addWidget(self._h_scroll, 1)

        # Right scroll arrow
        self._right_arrow = QtWidgets.QPushButton("\u203a")
        self._right_arrow.setFixedWidth(18)
        self._right_arrow.setCursor(QtCore.Qt.PointingHandCursor)
        self._right_arrow.setStyleSheet(
            "QPushButton { background: rgba(0,0,0,0.3); color: rgba(255,255,255,0.6); "
            "border: none; border-radius: 4px; font-size: 16px; }"
            "QPushButton:hover { background: rgba(0,0,0,0.5); color: white; }"
        )
        strip_stack.addWidget(self._right_arrow)

        # Scroll arrow connections
        scroll_step = avatar_size + 16
        self._left_arrow.clicked.connect(
            lambda: self._h_scroll.horizontalScrollBar().setValue(
                self._h_scroll.horizontalScrollBar().value() - scroll_step
            )
        )
        self._right_arrow.clicked.connect(
            lambda: self._h_scroll.horizontalScrollBar().setValue(
                self._h_scroll.horizontalScrollBar().value() + scroll_step
            )
        )
        self._h_scroll.horizontalScrollBar().valueChanged.connect(self._update_arrows)

        layout.addWidget(strip_container)

    def _populate_avatars(self, creators, avatar_size):
        """Build circular avatar + name for each creator."""
        for creator in creators:
            cid = creator.get("creator_id", "")
            name = creator.get("display_name", "?")
            avatar_url = creator.get("avatar_url", "")

            item_widget = QtWidgets.QWidget()
            item_widget.setFixedWidth(avatar_size + 16)
            item_widget.setCursor(QtCore.Qt.PointingHandCursor)
            item_layout = QtWidgets.QVBoxLayout(item_widget)
            item_layout.setContentsMargins(0, 0, 0, 0)
            item_layout.setSpacing(4)
            item_layout.setAlignment(QtCore.Qt.AlignHCenter)

            # Avatar label
            avatar_label = QtWidgets.QLabel()
            avatar_label.setFixedSize(avatar_size, avatar_size)
            avatar_label.setAlignment(QtCore.Qt.AlignCenter)
            avatar_label.setStyleSheet("border: none; background: transparent;")

            # Draw initials placeholder
            self._set_initials_avatar(avatar_label, name, avatar_size)

            item_layout.addWidget(avatar_label, 0, QtCore.Qt.AlignHCenter)

            # Name label
            name_lbl = QtWidgets.QLabel(name)
            name_lbl.setFixedWidth(avatar_size + 16)
            name_lbl.setAlignment(QtCore.Qt.AlignCenter)
            name_lbl.setStyleSheet(
                "color: #cccccc; font-size: 9px; "
                "background: transparent; border: none;"
            )
            fm = name_lbl.fontMetrics()
            elided = fm.elidedText(name, QtCore.Qt.ElideRight, avatar_size + 12)
            name_lbl.setText(elided)
            item_layout.addWidget(name_lbl)

            # Click handler
            _cid = cid
            item_widget.mousePressEvent = lambda ev, c=_cid: self.creator_clicked.emit(c)

            self._row_layout.addWidget(item_widget)
            self._avatar_items.append((cid, avatar_label))

            # Load real avatar async
            if avatar_url:
                self._mgr.load_creator_avatar_async(cid, avatar_url, self._on_avatar_loaded)

    def _set_initials_avatar(self, label, name, size):
        """Draw a coloured circle with the creator's initial."""
        pix = QtGui.QPixmap(size, size)
        pix.fill(QtGui.QColor(0, 0, 0, 0))
        p = QtGui.QPainter(pix)
        p.setRenderHint(QtGui.QPainter.Antialiasing)
        # Hash-based colour
        import hashlib as _hl
        h = int(_hl.md5(name.encode()).hexdigest()[:6], 16)
        color = QtGui.QColor((h >> 16) & 0xFF, (h >> 8) & 0xFF, h & 0xFF)
        color = color.lighter(130)
        p.setBrush(color)
        p.setPen(QtCore.Qt.NoPen)
        p.drawEllipse(0, 0, size, size)
        font = p.font()
        font.setPixelSize(int(size * 0.4))
        font.setBold(True)
        p.setFont(font)
        p.setPen(QtGui.QColor(255, 255, 255))
        p.drawText(QtCore.QRect(0, 0, size, size), QtCore.Qt.AlignCenter,
                    name[0].upper() if name else "?")
        p.end()
        label.setPixmap(pix)

    def _on_avatar_loaded(self, creator_id, local_path):
        """Replace initials with the downloaded avatar image."""
        for cid, label in self._avatar_items:
            if cid == creator_id:
                try:
                    size = label.width()
                except RuntimeError:
                    # Widget already deleted (page was refreshed)
                    return
                src = QtGui.QPixmap(local_path)
                if src.isNull():
                    return
                # Crop to circle
                scaled = src.scaled(size, size,
                                    QtCore.Qt.KeepAspectRatioByExpanding,
                                    QtCore.Qt.SmoothTransformation)
                circle = QtGui.QPixmap(size, size)
                circle.fill(QtGui.QColor(0, 0, 0, 0))
                p = QtGui.QPainter(circle)
                p.setRenderHint(QtGui.QPainter.Antialiasing)
                path = QtGui.QPainterPath()
                path.addEllipse(0, 0, size, size)
                p.setClipPath(path)
                x_off = (scaled.width() - size) // 2
                y_off = (scaled.height() - size) // 2
                p.drawPixmap(-x_off, -y_off, scaled)
                p.end()
                label.setPixmap(circle)
                break

    def cleanup(self):
        self._avatar_items.clear()

    def _update_arrows(self):
        sb = self._h_scroll.horizontalScrollBar()
        self._left_arrow.setVisible(sb.value() > sb.minimum())
        self._right_arrow.setVisible(sb.value() < sb.maximum())


# ---------------------------------------------------------------------------
# CreatorCard — card widget for Creator Catalogue grid
# ---------------------------------------------------------------------------

class CreatorCard(QtWidgets.QFrame):
    """Grid card showing a creator's avatar, name, and subtitle."""

    clicked = QtCore.Signal(str)  # creator_id

    def __init__(self, creator_data, mgr, card_size=None, parent=None):
        super().__init__(parent)
        self._creator_id = creator_data.get("creator_id", "")
        self._mgr = mgr

        cs = card_size or 140
        self.setFixedSize(cs, cs + 20)
        self.setCursor(QtCore.Qt.PointingHandCursor)
        self.setStyleSheet(
            "CreatorCard { background: rgba(255,255,255,0.03); "
            "border: 1px solid rgba(255,255,255,0.06); border-radius: 10px; }"
            "CreatorCard:hover { background: rgba(255,255,255,0.08); "
            "border: 1px solid rgba(255,255,255,0.12); }"
        )

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(8, 12, 8, 8)
        layout.setSpacing(6)
        layout.setAlignment(QtCore.Qt.AlignHCenter | QtCore.Qt.AlignTop)

        avatar_size = CFG.CREATOR_PROFILE_AVATAR_SIZE
        self._avatar_label = QtWidgets.QLabel()
        self._avatar_label.setFixedSize(avatar_size, avatar_size)
        self._avatar_label.setAlignment(QtCore.Qt.AlignCenter)
        self._avatar_label.setStyleSheet("border: none; background: transparent;")

        name = creator_data.get("display_name", "?")
        self._draw_initials(name, avatar_size)
        layout.addWidget(self._avatar_label, 0, QtCore.Qt.AlignHCenter)

        # Name
        name_lbl = QtWidgets.QLabel(name)
        name_lbl.setAlignment(QtCore.Qt.AlignCenter)
        name_lbl.setStyleSheet(
            "color: #e0e0e0; font-size: 12px; font-weight: bold; "
            "background: transparent; border: none;"
        )
        name_lbl.setWordWrap(True)
        name_lbl.setMaximumHeight(32)
        layout.addWidget(name_lbl)

        # Subtitle
        subtitle = creator_data.get("subtitle", "")
        if subtitle:
            sub_lbl = QtWidgets.QLabel(subtitle)
            sub_lbl.setAlignment(QtCore.Qt.AlignCenter)
            sub_lbl.setStyleSheet(
                "color: #888888; font-size: 9px; "
                "background: transparent; border: none;"
            )
            sub_lbl.setWordWrap(True)
            sub_lbl.setMaximumHeight(24)
            layout.addWidget(sub_lbl)

        layout.addStretch()

        # Load avatar async
        avatar_url = creator_data.get("avatar_url", "")
        if avatar_url:
            self._mgr.load_creator_avatar_async(
                self._creator_id, avatar_url, self._on_avatar_loaded
            )

    def _draw_initials(self, name, size):
        pix = QtGui.QPixmap(size, size)
        pix.fill(QtGui.QColor(0, 0, 0, 0))
        p = QtGui.QPainter(pix)
        p.setRenderHint(QtGui.QPainter.Antialiasing)
        import hashlib as _hl
        h = int(_hl.md5(name.encode()).hexdigest()[:6], 16)
        color = QtGui.QColor((h >> 16) & 0xFF, (h >> 8) & 0xFF, h & 0xFF).lighter(130)
        p.setBrush(color)
        p.setPen(QtCore.Qt.NoPen)
        p.drawEllipse(0, 0, size, size)
        font = p.font()
        font.setPixelSize(int(size * 0.4))
        font.setBold(True)
        p.setFont(font)
        p.setPen(QtGui.QColor(255, 255, 255))
        p.drawText(QtCore.QRect(0, 0, size, size), QtCore.Qt.AlignCenter,
                    name[0].upper() if name else "?")
        p.end()
        self._avatar_label.setPixmap(pix)

    def _on_avatar_loaded(self, creator_id, local_path):
        if creator_id != self._creator_id:
            return
        size = self._avatar_label.width()
        src = QtGui.QPixmap(local_path)
        if src.isNull():
            return
        scaled = src.scaled(size, size,
                            QtCore.Qt.KeepAspectRatioByExpanding,
                            QtCore.Qt.SmoothTransformation)
        circle = QtGui.QPixmap(size, size)
        circle.fill(QtGui.QColor(0, 0, 0, 0))
        p = QtGui.QPainter(circle)
        p.setRenderHint(QtGui.QPainter.Antialiasing)
        path = QtGui.QPainterPath()
        path.addEllipse(0, 0, size, size)
        p.setClipPath(path)
        x_off = (scaled.width() - size) // 2
        y_off = (scaled.height() - size) // 2
        p.drawPixmap(-x_off, -y_off, scaled)
        p.end()
        self._avatar_label.setPixmap(circle)

    def resize_card(self, new_size):
        """Resize the card (used by grid relayout)."""
        self.setFixedSize(new_size, new_size + 20)

    def mousePressEvent(self, event):
        if event.button() == QtCore.Qt.LeftButton:
            self.clicked.emit(self._creator_id)
        super().mousePressEvent(event)


# ---------------------------------------------------------------------------
# CreatorCataloguePage — full-page grid of creators with search
# ---------------------------------------------------------------------------

class CreatorCataloguePage(QtWidgets.QWidget):
    """Full-page grid of creator cards with back button and search."""

    back_requested = QtCore.Signal()
    creator_clicked = QtCore.Signal(str)  # creator_id

    def __init__(self, bgen_library_manager, parent=None):
        super().__init__(parent)
        self._mgr = bgen_library_manager
        self._cards = []
        self._all_creators = []
        self._card_size = 80
        self._last_col_count = 0
        self._search_visible = False
        self._build_ui()

    def _build_ui(self):
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Toolbar
        toolbar = QtWidgets.QWidget()
        toolbar.setFixedHeight(36)
        toolbar.setStyleSheet(
            "background: transparent; "
            "border-bottom: 1px solid rgba(255,255,255,0.08);"
        )
        tb_layout = QtWidgets.QHBoxLayout(toolbar)
        tb_layout.setContentsMargins(8, 4, 8, 4)
        tb_layout.setSpacing(8)

        back_btn = QtWidgets.QPushButton()
        back_btn.setFixedSize(24, 24)
        back_btn.setCursor(QtCore.Qt.PointingHandCursor)
        _arrow_pix = QtGui.QPixmap(str(Path(__file__).parent / "bgen_picker_icons" / "arrow_left_icon.png"))
        back_btn.setIcon(QtGui.QIcon(_arrow_pix))
        back_btn.setIconSize(QtCore.QSize(14, 14))
        back_btn.setStyleSheet(
            "QPushButton { background: rgba(255,255,255,0.08); "
            "border: none; border-radius: 4px; }"
            "QPushButton:hover { background: rgba(255,255,255,0.15); }"
        )
        back_btn.clicked.connect(self.back_requested.emit)
        tb_layout.addWidget(back_btn)

        self._title_label = QtWidgets.QLabel("Creator Catalogue")
        self._title_label.setStyleSheet(
            "color: #ffffff; font-size: 14px; font-weight: bold; "
            "background: transparent; border: none;"
        )
        tb_layout.addWidget(self._title_label, 1)

        # Search toggle button
        search_btn = QtWidgets.QPushButton()
        search_btn.setFixedSize(24, 24)
        search_btn.setCursor(QtCore.Qt.PointingHandCursor)
        _search_pix = QtGui.QPixmap(str(Path(__file__).parent / "bgen_picker_icons" / "search_icon.png"))
        search_btn.setIcon(QtGui.QIcon(_search_pix))
        search_btn.setIconSize(QtCore.QSize(14, 14))
        search_btn.setStyleSheet(
            "QPushButton { background: rgba(255,255,255,0.08); "
            "border: none; border-radius: 4px; }"
            "QPushButton:hover { background: rgba(255,255,255,0.15); }"
        )
        search_btn.clicked.connect(self._toggle_search)
        tb_layout.addWidget(search_btn)

        layout.addWidget(toolbar)

        # Search bar (hidden by default)
        self._search_bar = QtWidgets.QLineEdit()
        self._search_bar.setPlaceholderText("Search creators...")
        self._search_bar.setFixedHeight(30)
        self._search_bar.setStyleSheet(
            "QLineEdit { background: rgba(255,255,255,0.06); "
            "border: 1px solid rgba(255,255,255,0.1); border-radius: 6px; "
            "color: #ddd; padding: 4px 10px; font-size: 11px; }"
            "QLineEdit:focus { border: 1px solid rgba(91,155,213,0.5); }"
        )
        self._search_bar.textChanged.connect(self._on_search)
        self._search_bar.hide()
        layout.addWidget(self._search_bar)

        # Scrollable grid
        self._scroll = QtWidgets.QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setFrameShape(QtWidgets.QFrame.NoFrame)
        self._scroll.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)
        self._scroll.setStyleSheet(_VSCROLL_STYLE)

        self._grid_container = QtWidgets.QWidget()
        self._grid_layout = QtWidgets.QGridLayout(self._grid_container)
        self._grid_layout.setContentsMargins(8, 8, 8, 8)
        self._grid_layout.setSpacing(10)
        self._grid_layout.setAlignment(QtCore.Qt.AlignTop)
        self._scroll.setWidget(self._grid_container)
        layout.addWidget(self._scroll)

        # Empty state
        self._empty_label = QtWidgets.QLabel("No creators found")
        self._empty_label.setAlignment(QtCore.Qt.AlignCenter)
        self._empty_label.setStyleSheet("color: #666; font-size: 13px;")
        self._empty_label.hide()
        layout.addWidget(self._empty_label)

        # Resize debounce
        self._resize_timer = QtCore.QTimer(self)
        self._resize_timer.setSingleShot(True)
        self._resize_timer.setInterval(150)
        self._resize_timer.timeout.connect(self._relayout)
        self._scroll.viewport().installEventFilter(self)

    def _toggle_search(self):
        self._search_visible = not self._search_visible
        self._search_bar.setVisible(self._search_visible)
        if self._search_visible:
            self._search_bar.setFocus()
        else:
            self._search_bar.clear()

    def _on_search(self, text):
        """Filter creators by name."""
        if not text.strip():
            self._populate_grid(self._all_creators)
            return
        filtered = [
            c for c in self._all_creators
            if text.lower() in c.get("display_name", "").lower()
        ]
        self._populate_grid(filtered)

    def load(self, creators):
        """Populate the grid with a list of creator dicts."""
        self._all_creators = creators or []
        self._scroll.verticalScrollBar().setValue(0)
        self._last_col_count = 0
        self._populate_grid(self._all_creators)

    def _populate_grid(self, creators):
        self._clear()
        self._empty_label.setVisible(not creators)

        spacing = self._grid_layout.spacing()
        margins = self._grid_layout.contentsMargins()
        viewport_w = self._scroll.viewport().width() - margins.left() - margins.right()
        card_slot = self._card_size + spacing
        max_cols = max(1, int(viewport_w // card_slot)) if viewport_w > 0 else 3
        dynamic_size = max(self._card_size, int(
            (viewport_w - spacing * (max_cols - 1)) / max_cols
        )) if max_cols > 0 and viewport_w > 0 else self._card_size
        self._last_col_count = max_cols

        for i, creator in enumerate(creators):
            card = CreatorCard(creator, self._mgr, card_size=dynamic_size,
                               parent=self._grid_container)
            card.clicked.connect(self.creator_clicked.emit)
            self._cards.append(card)
            self._grid_layout.addWidget(card, i // max_cols, i % max_cols)

    def _clear(self):
        while self._grid_layout.count():
            item = self._grid_layout.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()
        self._cards.clear()

    def _relayout(self):
        if not self._cards:
            return
        spacing = self._grid_layout.spacing()
        margins = self._grid_layout.contentsMargins()
        viewport_w = self._scroll.viewport().width() - margins.left() - margins.right()
        if viewport_w <= 0:
            return
        card_slot = self._card_size + spacing
        max_cols = max(1, int(viewport_w // card_slot))
        if max_cols == self._last_col_count:
            return
        self._last_col_count = max_cols
        dynamic_size = max(self._card_size, int(
            (viewport_w - spacing * (max_cols - 1)) / max_cols
        )) if max_cols > 0 else self._card_size

        while self._grid_layout.count():
            self._grid_layout.takeAt(0)
        for i, card in enumerate(self._cards):
            card.resize_card(dynamic_size)
            self._grid_layout.addWidget(card, i // max_cols, i % max_cols)

    def eventFilter(self, obj, event):
        if event.type() == QtCore.QEvent.Resize and obj is self._scroll.viewport():
            self._resize_timer.start()
        return False


class _HeroBannerWidget(QtWidgets.QWidget):
    """Full hero section: banner image with gradient fade, overlaid avatar + text.

    The banner fills the entire widget background. A smooth gradient fades
    from fully transparent at the top to the page background colour at the
    bottom, so the hero blends seamlessly into the content below.
    Child widgets (avatar, name, stats) are laid out on top via a normal
    QVBoxLayout.
    """

    _BG = QtGui.QColor("#1d1d1d")

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumHeight(CFG.CREATOR_BANNER_HEIGHT)
        self._pixmap = None
        self._c1 = QtGui.QColor("#333")
        self._c2 = QtGui.QColor("#1a1a1a")

    def set_fallback_colors(self, c1, c2):
        self._c1 = c1
        self._c2 = c2
        self.update()

    def set_banner_pixmap(self, pixmap):
        self._pixmap = pixmap
        self.update()

    def paintEvent(self, event):
        p = QtGui.QPainter(self)
        p.setRenderHint(QtGui.QPainter.Antialiasing)
        rect = self.rect()
        radius = 8

        # Clip: top corners rounded, bottom corners square (blends into page)
        w, h, r = float(rect.width()), float(rect.height()), float(radius)
        clip = QtGui.QPainterPath()
        clip.moveTo(0, r)
        clip.arcTo(0, 0, r * 2, r * 2, 180, -90)
        clip.lineTo(w - r, 0)
        clip.arcTo(w - r * 2, 0, r * 2, r * 2, 90, -90)
        clip.lineTo(w, h)
        clip.lineTo(0, h)
        clip.closeSubpath()
        p.setClipPath(clip)

        if self._pixmap and not self._pixmap.isNull():
            # Draw banner scaled to cover, with reduced opacity
            p.setOpacity(0.3)
            scaled = self._pixmap.scaled(
                rect.width(), rect.height(),
                QtCore.Qt.KeepAspectRatioByExpanding,
                QtCore.Qt.SmoothTransformation,
            )
            x_off = (scaled.width() - rect.width()) // 2
            y_off = (scaled.height() - rect.height()) // 2
            p.drawPixmap(0, 0, scaled, x_off, y_off, rect.width(), rect.height())
            p.setOpacity(1.0)
        else:
            # Fallback diagonal gradient
            grad = QtGui.QLinearGradient(0, 0, rect.width(), rect.height())
            grad.setColorAt(0, self._c1)
            grad.setColorAt(1, self._c2)
            p.fillRect(rect, grad)

        # Smooth gradient overlay: transparent at top -> page BG at bottom
        bg = self._BG
        fade = QtGui.QLinearGradient(0, 0, 0, rect.height())
        fade.setColorAt(0.0, QtGui.QColor(bg.red(), bg.green(), bg.blue(), 0))
        fade.setColorAt(0.3, QtGui.QColor(bg.red(), bg.green(), bg.blue(), 30))
        fade.setColorAt(0.6, QtGui.QColor(bg.red(), bg.green(), bg.blue(), 140))
        fade.setColorAt(0.85, QtGui.QColor(bg.red(), bg.green(), bg.blue(), 220))
        fade.setColorAt(1.0, QtGui.QColor(bg.red(), bg.green(), bg.blue(), 255))
        p.fillRect(rect, fade)
        p.end()


# ---------------------------------------------------------------------------
# CreatorProfilePage — full creator profile with hero + product grid
# ---------------------------------------------------------------------------

class CreatorProfilePage(QtWidgets.QWidget):
    """Full-screen creator profile: hero banner, avatar, bio, product grid."""

    back_requested = QtCore.Signal()
    product_clicked = QtCore.Signal(str)
    follow_toggled = QtCore.Signal(str)  # creator_id

    def __init__(self, bgen_library_manager, parent=None):
        super().__init__(parent)
        self._mgr = bgen_library_manager
        self._creator_id = None
        self._is_following = False
        self._product_cards = []
        self._card_size = CFG.LIBRARY_CARD_SIZE
        self._last_col_count = 0
        self._build_ui()
        self._mgr.follow_toggled.connect(self._on_mgr_follow_toggled)

    def _build_ui(self):
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Scrollable content (no separate toolbar — buttons float over banner)
        self._scroll = QtWidgets.QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setFrameShape(QtWidgets.QFrame.NoFrame)
        self._scroll.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)
        self._scroll.setStyleSheet(_VSCROLL_STYLE)

        self._content = QtWidgets.QWidget()
        self._content_layout = QtWidgets.QVBoxLayout(self._content)
        self._content_layout.setContentsMargins(0, 0, 0, 8)
        self._content_layout.setSpacing(0)
        self._scroll.setWidget(self._content)
        layout.addWidget(self._scroll)

        # Floating back + follow buttons (overlay on top of scroll area)
        _btn_style = (
            "QPushButton { background: transparent; "
            "border: none; border-radius: 4px; }"
            "QPushButton:hover { background: rgba(0,0,0,0.55); }"
        )

        self._back_btn = QtWidgets.QPushButton(self)
        self._back_btn.setFixedSize(24, 24)
        self._back_btn.setCursor(QtCore.Qt.PointingHandCursor)
        _arrow_pix = QtGui.QPixmap(str(
            Path(__file__).parent / "bgen_picker_icons" / "arrow_left_icon.png"
        ))
        self._back_btn.setIcon(QtGui.QIcon(_arrow_pix))
        self._back_btn.setIconSize(QtCore.QSize(22, 22))
        self._back_btn.setStyleSheet(_btn_style)
        self._back_btn.clicked.connect(self.back_requested.emit)
        self._back_btn.raise_()

        self._follow_btn = QtWidgets.QPushButton(self)
        self._follow_btn.setFixedSize(24, 24)
        self._follow_btn.setCursor(QtCore.Qt.PointingHandCursor)
        self._follow_btn.setStyleSheet(_btn_style)
        self._follow_btn.clicked.connect(self._on_follow_clicked)
        self._update_follow_icon()
        self._follow_btn.raise_()

        # Resize debounce for product grid
        self._resize_timer = QtCore.QTimer(self)
        self._resize_timer.setSingleShot(True)
        self._resize_timer.setInterval(150)
        self._resize_timer.timeout.connect(self._relayout_products)
        self._scroll.viewport().installEventFilter(self)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        # Reposition floating buttons over the banner
        m = 8
        self._back_btn.move(m, m)
        self._follow_btn.move(self.width() - self._follow_btn.width() - m, m)

    def load_creator(self, data):
        """Load a creator profile from ``{creator, products, is_following}``."""
        creator = data.get("creator", {})
        products = data.get("products", [])
        self._is_following = data.get("is_following", False)
        self._creator_id = creator.get("creator_id", "")

        self._update_follow_icon()
        self._scroll.verticalScrollBar().setValue(0)
        self._last_col_count = 0

        # Clear old content
        self._clear_content()

        # Build hero section
        self._build_hero(creator)

        # Build product grid
        self._build_product_grid(products)

        self._content_layout.addStretch()

    def _clear_content(self):
        self._product_cards.clear()
        while self._content_layout.count():
            item = self._content_layout.takeAt(0)
            w = item.widget()
            if w:
                if hasattr(w, "cleanup"):
                    w.cleanup()
                w.deleteLater()

    def _build_hero(self, creator):
        """Build the hero section: full-bleed banner with gradient, avatar + text on top."""
        import hashlib as _hl

        name = creator.get("display_name", "?")
        avatar_size = CFG.CREATOR_PROFILE_AVATAR_SIZE

        # -- The hero widget IS the banner — content is overlaid via its layout --
        self._banner_widget = _HeroBannerWidget()
        # Hash-based fallback gradient
        h = int(_hl.md5(name.encode()).hexdigest()[:6], 16)
        c1 = QtGui.QColor((h >> 16) & 0xFF, (h >> 8) & 0xFF, h & 0xFF)
        self._banner_widget.set_fallback_colors(c1, c1.darker(200))

        # Content layout on top of the painted banner
        hero_layout = QtWidgets.QVBoxLayout(self._banner_widget)
        hero_layout.setContentsMargins(12, 0, 12, 12)
        hero_layout.setSpacing(0)

        # Push content toward the bottom of the banner
        hero_layout.addStretch(1)

        # -- Avatar row --
        avatar_row = QtWidgets.QHBoxLayout()
        avatar_row.setContentsMargins(0, 0, 0, 0)
        avatar_row.setSpacing(12)
        avatar_row.setAlignment(QtCore.Qt.AlignBottom)

        # Avatar container (allows verified badge overlay)
        avatar_container = QtWidgets.QWidget()
        avatar_container.setFixedSize(avatar_size, avatar_size)
        avatar_container.setStyleSheet("background: transparent; border: none;")

        self._profile_avatar = QtWidgets.QLabel(avatar_container)
        self._profile_avatar.setFixedSize(avatar_size, avatar_size)
        self._profile_avatar.setStyleSheet(
            "border: none; background: transparent;"
        )
        self._profile_avatar.move(0, 0)
        self._draw_circle_avatar(self._profile_avatar, name, avatar_size)

        if creator.get("is_verified"):
            badge_size = max(16, avatar_size // 4)
            verified_lbl = QtWidgets.QLabel(avatar_container)
            verified_lbl.setFixedSize(badge_size, badge_size)
            verified_lbl.setStyleSheet("background: transparent; border: none;")
            v_icon_path = Path(__file__).parent / "bgen_picker_icons" / "verified_icon.png"
            if v_icon_path.exists():
                v_pix = QtGui.QPixmap(str(v_icon_path)).scaled(
                    badge_size, badge_size,
                    QtCore.Qt.KeepAspectRatio,
                    QtCore.Qt.SmoothTransformation,
                )
                verified_lbl.setPixmap(v_pix)
            verified_lbl.move(avatar_size - badge_size, avatar_size - badge_size)

        avatar_row.addWidget(avatar_container, 0, QtCore.Qt.AlignBottom)

        # Name + bio column
        text_col = QtWidgets.QVBoxLayout()
        text_col.setSpacing(3)
        text_col.setContentsMargins(0, 0, 0, 4)

        name_lbl = QtWidgets.QLabel(name)
        name_lbl.setStyleSheet(
            "color: #ffffff; font-size: 16px; font-weight: bold; "
            "background: transparent; border: none;"
        )
        text_col.addWidget(name_lbl)

        bio = creator.get("bio", "")
        if bio:
            bio_lbl = QtWidgets.QLabel(bio)
            bio_lbl.setStyleSheet(
                "color: rgba(200,200,200,0.8); font-size: 10px; "
                "background: transparent; border: none;"
            )
            bio_lbl.setWordWrap(True)
            bio_lbl.setMaximumHeight(40)
            text_col.addWidget(bio_lbl)

        # -- Stats + social links row (inside text_col, under bio) --
        stats_row = QtWidgets.QHBoxLayout()
        stats_row.setContentsMargins(0, 4, 0, 0)
        stats_row.setSpacing(12)

        _stat_style = (
            "color: #999; font-size: 11px; "
            "background: transparent; border: none;"
        )

        total_sales = creator.get("total_sales_count", 0) or 0
        sales_lbl = QtWidgets.QLabel(f"{total_sales:,} Sale{'s' if total_sales != 1 else ''}")
        sales_lbl.setStyleSheet(_stat_style)
        stats_row.addWidget(sales_lbl)

        followers = creator.get("follower_count", 0) or 0
        follow_lbl = QtWidgets.QLabel(f"{followers:,} Follower{'s' if followers != 1 else ''}")
        follow_lbl.setStyleSheet(_stat_style)
        stats_row.addWidget(follow_lbl)

        # Social links dropdown
        import webbrowser
        social_links = creator.get("social_links", {})
        valid_links = {p: u for p, u in social_links.items() if u}
        if valid_links:
            links_btn = QtWidgets.QPushButton()
            links_btn.setFixedSize(24, 24)
            links_btn.setCursor(QtCore.Qt.PointingHandCursor)
            _link_pix = QtGui.QPixmap(str(
                Path(__file__).parent / "bgen_picker_icons" / "link_icon.png"
            ))
            links_btn.setIcon(QtGui.QIcon(_link_pix))
            links_btn.setIconSize(QtCore.QSize(16, 16))
            links_btn.setStyleSheet(
                "QPushButton { background: transparent; border: none; border-radius: 4px; }"
                "QPushButton:hover { background: rgba(255,255,255,0.1); }"
                "QPushButton::menu-indicator { image: none; width: 0; }"
            )
            links_menu = QtWidgets.QMenu(links_btn)
            links_menu.setStyleSheet(
                "QMenu { background: #2a2a2a; border: 1px solid #444; "
                "border-radius: 4px; padding: 4px 0; }"
                "QMenu::item { color: #ddd; padding: 6px 16px; font-size: 11px; }"
                "QMenu::item:hover { background: rgba(29,101,202,0.4); }"
            )
            for platform, url in valid_links.items():
                label = platform.replace("_", " ").title()
                icon_path = Path(__file__).parent / "bgen_picker_icons" / f"{platform}_icon.png"
                action = links_menu.addAction(label)
                if icon_path.exists():
                    action.setIcon(QtGui.QIcon(QtGui.QPixmap(str(icon_path))))
                _url = url
                action.triggered.connect(lambda checked=False, u=_url: webbrowser.open(u))
            links_btn.setMenu(links_menu)
            stats_row.addStretch(2)
            stats_row.addWidget(links_btn)

        stats_row.addStretch()

        text_col.addLayout(stats_row)

        avatar_row.addLayout(text_col, 1)
        hero_layout.addLayout(avatar_row)
        self._content_layout.addWidget(self._banner_widget)

        # Load images async
        banner_url = creator.get("banner_url", "")
        if banner_url:
            self._mgr.load_creator_avatar_async(
                f"banner_{self._creator_id}", banner_url,
                self._on_banner_loaded
            )
        avatar_url = creator.get("avatar_url", "")
        if avatar_url:
            self._mgr.load_creator_avatar_async(
                self._creator_id, avatar_url, self._on_profile_avatar_loaded
            )

    def _build_product_grid(self, products):
        """Build the product grid below the hero."""
        if not products:
            return

        # Section header
        header = QtWidgets.QLabel(f"Products ({len(products)})")
        header.setStyleSheet(
            "color: #e0e0e0; font-size: 13px; font-weight: bold; "
            "background: transparent; border: none; "
            "padding: 10px 8px 4px 8px;"
        )
        self._content_layout.addWidget(header)

        # Grid
        self._product_grid_container = QtWidgets.QWidget()
        self._product_grid = QtWidgets.QGridLayout(self._product_grid_container)
        self._product_grid.setContentsMargins(8, 4, 8, 8)
        self._product_grid.setSpacing(10)
        self._product_grid.setAlignment(QtCore.Qt.AlignTop)

        spacing = self._product_grid.spacing()
        margins = self._product_grid.contentsMargins()
        viewport_w = self._scroll.viewport().width() - margins.left() - margins.right()
        card_slot = self._card_size + spacing
        max_cols = max(1, int(viewport_w // card_slot)) if viewport_w > 0 else 3
        dynamic_size = max(self._card_size, int(
            (viewport_w - spacing * (max_cols - 1)) / max_cols
        )) if max_cols > 0 and viewport_w > 0 else self._card_size
        self._last_col_count = max_cols

        for i, product in enumerate(products):
            card = BgenLibraryCard(product, parent=self._product_grid_container,
                                   card_size=dynamic_size)
            card.clicked.connect(self.product_clicked.emit)
            self._product_cards.append(card)
            self._product_grid.addWidget(card, i // max_cols, i % max_cols)

        self._content_layout.addWidget(self._product_grid_container)

    def _draw_circle_avatar(self, label, name, size):
        pix = QtGui.QPixmap(size, size)
        pix.fill(QtGui.QColor(0, 0, 0, 0))
        p = QtGui.QPainter(pix)
        p.setRenderHint(QtGui.QPainter.Antialiasing)
        import hashlib as _hl
        h = int(_hl.md5(name.encode()).hexdigest()[:6], 16)
        color = QtGui.QColor((h >> 16) & 0xFF, (h >> 8) & 0xFF, h & 0xFF).lighter(130)
        p.setBrush(color)
        p.setPen(QtCore.Qt.NoPen)
        p.drawEllipse(0, 0, size, size)
        font = p.font()
        font.setPixelSize(int(size * 0.38))
        font.setBold(True)
        p.setFont(font)
        p.setPen(QtGui.QColor(255, 255, 255))
        p.drawText(QtCore.QRect(0, 0, size, size), QtCore.Qt.AlignCenter,
                    name[0].upper() if name else "?")
        p.end()
        label.setPixmap(pix)

    def _crop_to_circle(self, pixmap, size):
        """Crop *pixmap* into a circle of *size* px with a soft drop shadow."""
        shadow_pad = 4  # extra pixels for shadow bleed
        total = size + shadow_pad * 2

        # Scale source to fill the circle
        scaled = pixmap.scaled(size, size,
                               QtCore.Qt.KeepAspectRatioByExpanding,
                               QtCore.Qt.SmoothTransformation)

        result = QtGui.QPixmap(total, total)
        result.fill(QtGui.QColor(0, 0, 0, 0))
        p = QtGui.QPainter(result)
        p.setRenderHint(QtGui.QPainter.Antialiasing)

        # Draw shadow rings (fake soft shadow via concentric semitransparent ellipses)
        for i in range(shadow_pad, 0, -1):
            alpha = int(30 * (shadow_pad - i + 1) / shadow_pad)
            p.setBrush(QtGui.QColor(0, 0, 0, alpha))
            p.setPen(QtCore.Qt.NoPen)
            offset = shadow_pad - i
            p.drawEllipse(offset, offset + 1, size + i * 2, size + i * 2)

        # Clip to circle, draw image centered
        clip = QtGui.QPainterPath()
        clip.addEllipse(shadow_pad, shadow_pad, size, size)
        p.setClipPath(clip)
        x_off = (scaled.width() - size) // 2
        y_off = (scaled.height() - size) // 2
        p.drawPixmap(shadow_pad - x_off, shadow_pad - y_off, scaled)
        p.end()
        return result

    def _on_profile_avatar_loaded(self, creator_id, local_path):
        if creator_id != self._creator_id:
            return
        src = QtGui.QPixmap(local_path)
        if src.isNull():
            return
        label_size = self._profile_avatar.width()
        # _crop_to_circle adds 8px padding for shadow, so pass inner size
        inner = label_size - 8
        cropped = self._crop_to_circle(src, inner)
        # Scale result to fit the label exactly
        self._profile_avatar.setPixmap(
            cropped.scaled(label_size, label_size,
                           QtCore.Qt.KeepAspectRatio,
                           QtCore.Qt.SmoothTransformation)
        )

    def _on_banner_loaded(self, key, local_path):
        if key != f"banner_{self._creator_id}":
            return
        src = QtGui.QPixmap(local_path)
        if src.isNull():
            return
        self._banner_widget.set_banner_pixmap(src)

    def _update_follow_icon(self):
        icon_name = "star-gold-icon.png" if self._is_following else "star-white-icon.png"
        pix = QtGui.QPixmap(str(Path(__file__).parent / "bgen_picker_icons" / icon_name))
        self._follow_btn.setIcon(QtGui.QIcon(pix))
        self._follow_btn.setIconSize(QtCore.QSize(14, 14))

    def _on_follow_clicked(self):
        if not self._creator_id:
            return
        # Disable button while request is in-flight to prevent double-clicks
        self._follow_btn.setEnabled(False)
        # Safety timeout: re-enable after 10s if server never responds
        QtCore.QTimer.singleShot(10000, lambda: self._follow_btn.setEnabled(True))
        # Optimistic update
        self._is_following = not self._is_following
        self._update_follow_icon()
        try:
            self._mgr.toggle_follow_creator(self._creator_id)
        except Exception:
            # Revert optimistic update on immediate error
            self._is_following = not self._is_following
            self._update_follow_icon()
            self._follow_btn.setEnabled(True)
            return
        self.follow_toggled.emit(self._creator_id)

    def _on_mgr_follow_toggled(self, creator_id, is_following):
        """Server confirmed follow state — reconcile and re-enable button."""
        if creator_id != self._creator_id:
            return
        self._is_following = is_following
        self._update_follow_icon()
        self._follow_btn.setEnabled(True)

    def _relayout_products(self):
        if not self._product_cards or not hasattr(self, "_product_grid"):
            return
        spacing = self._product_grid.spacing()
        margins = self._product_grid.contentsMargins()
        viewport_w = self._scroll.viewport().width() - margins.left() - margins.right()
        if viewport_w <= 0:
            return
        card_slot = self._card_size + spacing
        max_cols = max(1, int(viewport_w // card_slot))
        if max_cols == self._last_col_count:
            return
        self._last_col_count = max_cols
        dynamic_size = max(self._card_size, int(
            (viewport_w - spacing * (max_cols - 1)) / max_cols
        )) if max_cols > 0 else self._card_size

        while self._product_grid.count():
            self._product_grid.takeAt(0)
        for i, card in enumerate(self._product_cards):
            card.resize_card(dynamic_size)
            self._product_grid.addWidget(card, i // max_cols, i % max_cols)

    def eventFilter(self, obj, event):
        if event.type() == QtCore.QEvent.Resize and obj is self._scroll.viewport():
            self._resize_timer.start()
        return False


# ---------------------------------------------------------------------------
# ExplorePageWidget — data-driven storefront / explore page
# ---------------------------------------------------------------------------

class ExplorePageWidget(QtWidgets.QWidget):
    """Scrollable Explore page built from data-driven sections.

    Sections are resolved via ``BgenLocalFileManager.get_explore_sections()``
    and rendered as:  hero carousel, algorithmic card rows, creator
    spotlights, collection grids, etc.
    """

    product_clicked = QtCore.Signal(str)      # product_id
    view_all_clicked = QtCore.Signal(str)     # section slug
    collection_clicked = QtCore.Signal(str)   # collection slug
    creator_clicked = QtCore.Signal(str)      # creator_id
    creator_view_all_clicked = QtCore.Signal()

    def __init__(self, bgen_library_manager, parent=None, card_size=None):
        super().__init__(parent)
        self._mgr = bgen_library_manager
        self._card_size = card_size if card_size is not None else CFG.LIBRARY_CARD_SIZE + 16
        self._section_widgets = []

        self._mgr.catalog_updated.connect(self._on_catalog_updated)
        self._mgr.sections_loaded.connect(self._on_sections_loaded)
        self._mgr.store_offline.connect(self._show_offline_state)

        # Outer scroll area
        self._scroll = QtWidgets.QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setFrameShape(QtWidgets.QFrame.NoFrame)
        self._scroll.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)
        self._scroll.setStyleSheet(_VSCROLL_STYLE)

        self._content = QtWidgets.QWidget()
        self._content.setMinimumWidth(0)
        self._content_layout = QtWidgets.QVBoxLayout(self._content)
        self._content_layout.setContentsMargins(6, 6, 6, 8)
        self._content_layout.setSpacing(12)
        self._content_layout.setSizeConstraint(QtWidgets.QLayout.SetNoConstraint)
        self._scroll.setWidget(self._content)

        outer = QtWidgets.QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(self._scroll)

        self._built = False

    # ------------------------------------------------------------------
    # Public API (preserved for blender_ui.py compatibility)
    # ------------------------------------------------------------------

    def refresh(self):
        """Build sections on first call; skip on subsequent calls unless invalidated."""
        if self._built:
            return
        self._force_refresh()

    def invalidate(self):
        """Mark sections as stale so next ``refresh()`` rebuilds."""
        self._built = False

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _on_catalog_updated(self):
        self._built = False
        self._force_refresh()

    def _on_sections_loaded(self, sections):
        """Handle async sections_loaded signal — rebuild if we have new data."""
        if sections:
            self._built = False
            self._force_refresh()

    def _clear_content(self):
        """Remove all child widgets from the content layout."""
        for w in self._section_widgets:
            if hasattr(w, "cleanup"):
                w.cleanup()
        self._section_widgets.clear()

        while self._content_layout.count():
            item = self._content_layout.takeAt(0)
            w = item.widget()
            if w is not None:
                w.deleteLater()

    def _show_offline_state(self):
        """Display a 'Store Offline' message instead of sections."""
        self._clear_content()

        container = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(container)
        layout.setAlignment(QtCore.Qt.AlignCenter)

        icon_label = QtWidgets.QLabel("  ")
        icon_label.setStyleSheet("font-size: 36px;")
        icon_label.setAlignment(QtCore.Qt.AlignCenter)
        layout.addWidget(icon_label)

        title = QtWidgets.QLabel("Store Offline")
        title.setStyleSheet("font-size: 16px; font-weight: bold; color: #ccc;")
        title.setAlignment(QtCore.Qt.AlignCenter)
        layout.addWidget(title)

        subtitle = QtWidgets.QLabel(
            "Unable to connect to the BGEN Library.\n"
            "Check your internet connection and try again."
        )
        subtitle.setStyleSheet("font-size: 12px; color: #888;")
        subtitle.setAlignment(QtCore.Qt.AlignCenter)
        subtitle.setWordWrap(True)
        layout.addWidget(subtitle)

        retry_btn = QtWidgets.QPushButton("Retry")
        retry_btn.setFixedWidth(100)
        retry_btn.setStyleSheet(
            "QPushButton { background: #333; color: #ccc; border: 1px solid #555;"
            " border-radius: 4px; padding: 6px 12px; }"
            "QPushButton:hover { background: #444; }"
        )
        retry_btn.clicked.connect(self._on_retry)
        btn_row = QtWidgets.QHBoxLayout()
        btn_row.setAlignment(QtCore.Qt.AlignCenter)
        btn_row.addWidget(retry_btn)
        layout.addLayout(btn_row)

        self._content_layout.addStretch()
        self._content_layout.addWidget(container)
        self._content_layout.addStretch()
        self._built = True

    def _on_retry(self):
        """Retry fetching the explore layout from the server."""
        self._built = False
        self._mgr.fetch_explore_layout(force=True)

    def _force_refresh(self):
        """Tear down and rebuild all sections from the section manifest."""
        self._clear_content()

        # Resolve sections from manager
        sections = self._mgr.get_explore_sections()

        if not sections:
            # No cached data — show offline state
            self._show_offline_state()
            return

        for section in sections:
            stype = section.get("type")

            if stype == "hero":
                slides = section.get("slides", [])
                if slides:
                    widget = HeroCarouselWidget(slides, self)
                    widget.product_clicked.connect(self.product_clicked.emit)
                    self._content_layout.addWidget(widget)
                    self._section_widgets.append(widget)

            elif stype == "algorithmic":
                products = section.get("products", [])
                if products:
                    widget = SectionRowWidget(
                        title=section.get("title", ""),
                        slug=section.get("slug", ""),
                        products=products,
                        mgr=self._mgr,
                        card_size=self._card_size,
                        parent=self,
                    )
                    widget.product_clicked.connect(self.product_clicked.emit)
                    widget.view_all_clicked.connect(self.view_all_clicked.emit)
                    self._content_layout.addWidget(widget)
                    self._section_widgets.append(widget)

            elif stype == "creator_spotlight":
                # Use the new horizontal creator strip instead of single spotlight
                creators = section.get("creators", [])
                if not creators:
                    # Fallback: use creators from manager cache
                    creators = self._mgr.get_creators()
                if creators:
                    widget = CreatorStripWidget(
                        title=section.get("title", "Creators"),
                        creators=creators,
                        mgr=self._mgr,
                        parent=self,
                    )
                    widget.creator_clicked.connect(self.creator_clicked.emit)
                    widget.view_all_clicked.connect(self.creator_view_all_clicked.emit)
                    self._content_layout.addWidget(widget)
                    self._section_widgets.append(widget)

            elif stype == "collection_grid":
                collections = section.get("collections", [])
                if collections:
                    widget = CollectionGridWidget(
                        title=section.get("title", "Collections"),
                        collections=collections,
                        mgr=self._mgr,
                        parent=self,
                    )
                    widget.collection_clicked.connect(self.collection_clicked.emit)
                    self._content_layout.addWidget(widget)
                    self._section_widgets.append(widget)

        self._content_layout.addStretch()
        self._built = True


# ---------------------------------------------------------------------------
# FilteredGridPage — "View All" / Collection sub-page with back button
# ---------------------------------------------------------------------------

class FilteredGridPage(QtWidgets.QWidget):
    """Full-page grid view for a section or collection, with title and back."""

    back_requested = QtCore.Signal()
    product_clicked = QtCore.Signal(str)  # product_id

    def __init__(self, bgen_library_manager, parent=None):
        super().__init__(parent)
        self._mgr = bgen_library_manager
        self._cards = []
        self._card_size = CFG.LIBRARY_CARD_SIZE
        self._last_col_count = 0
        self._build_ui()

    def _build_ui(self):
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Toolbar
        toolbar = QtWidgets.QWidget()
        toolbar.setFixedHeight(36)
        toolbar.setStyleSheet(
            "background: transparent; "
            "border-bottom: 1px solid rgba(255,255,255,0.08);"
        )
        tb_layout = QtWidgets.QHBoxLayout(toolbar)
        tb_layout.setContentsMargins(8, 4, 8, 4)
        tb_layout.setSpacing(8)

        back_btn = QtWidgets.QPushButton()
        back_btn.setFixedSize(24, 24)
        back_btn.setCursor(QtCore.Qt.PointingHandCursor)
        _arrow_pix = QtGui.QPixmap(str(Path(__file__).parent / "bgen_picker_icons" / "arrow_left_icon.png"))
        back_btn.setIcon(QtGui.QIcon(_arrow_pix))
        back_btn.setIconSize(QtCore.QSize(14, 14))
        back_btn.setStyleSheet(
            "QPushButton { background: rgba(255,255,255,0.08); "
            "border: none; border-radius: 4px; }"
            "QPushButton:hover { background: rgba(255,255,255,0.15); }"
        )
        back_btn.clicked.connect(self.back_requested.emit)
        tb_layout.addWidget(back_btn)

        self._title_label = QtWidgets.QLabel()
        self._title_label.setStyleSheet(
            "color: #ffffff; font-size: 14px; font-weight: bold; "
            "background: transparent; border: none;"
        )
        tb_layout.addWidget(self._title_label, 1)

        layout.addWidget(toolbar)

        # Scrollable grid
        self._scroll = QtWidgets.QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setFrameShape(QtWidgets.QFrame.NoFrame)
        self._scroll.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)
        self._scroll.setStyleSheet(_VSCROLL_STYLE)

        self._grid_container = QtWidgets.QWidget()
        self._grid_layout = QtWidgets.QGridLayout(self._grid_container)
        self._grid_layout.setContentsMargins(8, 8, 8, 8)
        self._grid_layout.setSpacing(10)
        self._grid_layout.setAlignment(QtCore.Qt.AlignTop)
        self._scroll.setWidget(self._grid_container)

        layout.addWidget(self._scroll)

        # Resize debounce
        self._resize_timer = QtCore.QTimer(self)
        self._resize_timer.setSingleShot(True)
        self._resize_timer.setInterval(150)
        self._resize_timer.timeout.connect(self._relayout)
        self._scroll.viewport().installEventFilter(self)

    def load(self, title, products):
        """Populate the grid with *products* and set the page *title*."""
        self._title_label.setText(title)
        self._scroll.verticalScrollBar().setValue(0)
        self._clear()
        self._last_col_count = 0

        # Compute dynamic card size to fill viewport width
        spacing = self._grid_layout.spacing()
        margins = self._grid_layout.contentsMargins()
        viewport_w = self._scroll.viewport().width() - margins.left() - margins.right()
        card_slot = self._card_size + spacing
        max_cols = max(1, int(viewport_w // card_slot)) if viewport_w > 0 else 1
        dynamic_size = max(self._card_size, int(
            (viewport_w - spacing * (max_cols - 1)) / max_cols
        )) if max_cols > 0 and viewport_w > 0 else self._card_size
        self._last_col_count = max_cols

        for i, product in enumerate(products):
            card = BgenLibraryCard(product, parent=self._grid_container, card_size=dynamic_size)
            card.clicked.connect(self.product_clicked.emit)
            self._cards.append(card)
            self._grid_layout.addWidget(card, i // max_cols, i % max_cols)

    def _clear(self):
        while self._grid_layout.count():
            item = self._grid_layout.takeAt(0)
            w = item.widget()
            if w:
                if hasattr(w, "cleanup"):
                    w.cleanup()
                w.deleteLater()
        self._cards.clear()

    def _relayout(self):
        """Reposition and dynamically resize cards to fill viewport width."""
        if not self._cards:
            return

        spacing = self._grid_layout.spacing()
        margins = self._grid_layout.contentsMargins()
        viewport_w = self._scroll.viewport().width() - margins.left() - margins.right()
        if viewport_w <= 0:
            return

        card_slot = self._card_size + spacing
        max_cols = max(1, int(viewport_w // card_slot))

        if max_cols == self._last_col_count:
            return
        self._last_col_count = max_cols

        dynamic_size = max(self._card_size, int(
            (viewport_w - spacing * (max_cols - 1)) / max_cols
        )) if max_cols > 0 else self._card_size

        # Remove all from grid without deleting, then re-add at new positions
        while self._grid_layout.count():
            self._grid_layout.takeAt(0)

        for i, card in enumerate(self._cards):
            card.resize_card(dynamic_size)
            self._grid_layout.addWidget(card, i // max_cols, i % max_cols)

    def eventFilter(self, obj, event):
        if event.type() == QtCore.QEvent.Resize and obj is self._scroll.viewport():
            self._resize_timer.start()
        return False

    def cleanup(self):
        self._clear()
        try:
            self._scroll.viewport().removeEventFilter(self)
        except Exception:
            pass


# ---------------------------------------------------------------------------
# ProductDetailPage -- full product detail view
# ---------------------------------------------------------------------------

class ProductDetailPage(QtWidgets.QWidget):
    """Full-screen detail view for a bgen_library product."""

    back_requested = QtCore.Signal()
    action_requested = QtCore.Signal(str, str)  # product_id, action
    creator_clicked = QtCore.Signal(str)        # creator_id

    def __init__(self, parent=None):
        super().__init__(parent)
        self._product = None
        self._action_type = "buy"
        self._last_hero_width = 0
        self._hero_image_path = None  # Stores loaded hero thumbnail file path
        self._build_ui()

        # Debounced resize for hero thumbnail
        self._hero_resize_timer = QtCore.QTimer(self)
        self._hero_resize_timer.setSingleShot(True)
        self._hero_resize_timer.setInterval(150)
        self._hero_resize_timer.timeout.connect(self._on_hero_resize)

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _build_ui(self):
        main_layout = QtWidgets.QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # ---- Detail Toolbar ----
        toolbar = QtWidgets.QWidget()
        toolbar.setFixedHeight(32)
        toolbar.setStyleSheet("background: transparent;")
        toolbar_layout = QtWidgets.QHBoxLayout(toolbar)
        toolbar_layout.setContentsMargins(4, 4, 4, 4)
        toolbar_layout.setSpacing(6)

        self._back_btn = QtWidgets.QPushButton()
        self._back_btn.setFixedSize(24, 24)
        self._back_btn.setCursor(QtCore.Qt.PointingHandCursor)
        _arrow_pix = QtGui.QPixmap(str(Path(__file__).parent / "bgen_picker_icons" / "arrow_left_icon.png"))
        self._back_btn.setIcon(QtGui.QIcon(_arrow_pix))
        self._back_btn.setIconSize(QtCore.QSize(14, 14))
        self._back_btn.setStyleSheet(
            "QPushButton { background: rgba(255,255,255,0.08); "
            "border: none; border-radius: 4px; }"
            "QPushButton:hover { background: rgba(255,255,255,0.15); }"
        )
        self._back_btn.clicked.connect(self.back_requested.emit)
        toolbar_layout.addWidget(self._back_btn)

        self._toolbar_name = QtWidgets.QLabel()
        self._toolbar_name.setStyleSheet(
            "color: #cccccc; font-size: 12px; font-weight: bold; "
            "background: transparent; border: none;"
        )
        self._toolbar_name.setMinimumWidth(0)
        sp = self._toolbar_name.sizePolicy()
        sp.setHorizontalPolicy(QtWidgets.QSizePolicy.Ignored)
        self._toolbar_name.setSizePolicy(sp)
        toolbar_layout.addWidget(self._toolbar_name)
        toolbar_layout.addStretch()
        main_layout.addWidget(toolbar)

        # ---- Scrollable Content ----
        self._scroll = QtWidgets.QScrollArea()
        scroll = self._scroll
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QtWidgets.QFrame.NoFrame)
        scroll.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)
        scroll.setStyleSheet(
            "QScrollArea { background: transparent; border: none; }"
            "QScrollBar:vertical {"
            "    border: none; background: rgba(30, 30, 30, 0.3);"
            "    width: 8px; margin: 0px;"
            "}"
            "QScrollBar::handle:vertical {"
            "    background: rgba(100, 100, 100, 0.5);"
            "    min-height: 20px; border-radius: 4px;"
            "}"
            "QScrollBar::handle:vertical:hover {"
            "    background: rgba(120, 120, 120, 0.7);"
            "}"
            "QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {"
            "    height: 0px; background: transparent;"
            "}"
            "QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {"
            "    background: transparent;"
            "}"
        )

        self._content_widget = QtWidgets.QWidget()
        content = self._content_widget
        content.setStyleSheet("background: transparent;")
        content.setMinimumWidth(0)  # allow shrinking to any width
        self._content_layout = QtWidgets.QVBoxLayout(content)
        self._content_layout.setContentsMargins(8, 6, 8, 8)
        self._content_layout.setSpacing(8)
        self._content_layout.setSizeConstraint(QtWidgets.QLayout.SetNoConstraint)

        # [Hero Section] — vertical stack so it works at any width
        hero_frame = QtWidgets.QFrame()
        hero_frame.setStyleSheet(
            "QFrame { background: rgba(255,255,255,0.04); "
            "border: 1px solid rgba(255,255,255,0.06); border-radius: 8px; }"
        )
        hero_frame.setMinimumWidth(0)
        hero_layout = QtWidgets.QVBoxLayout(hero_frame)
        hero_layout.setContentsMargins(8, 8, 8, 8)
        hero_layout.setSpacing(4)
        hero_layout.setSizeConstraint(QtWidgets.QLayout.SetNoConstraint)

        # Thumbnail — scales with width, aspect-ratio preserved via heightForWidth
        hero_thumb_container = QtWidgets.QWidget()
        hero_thumb_container.setStyleSheet("background: transparent; border: none;")
        hero_thumb_container.setMinimumHeight(80)
        hero_thumb_container.setMaximumHeight(200)
        hero_thumb_container.setSizePolicy(
            QtWidgets.QSizePolicy.Ignored, QtWidgets.QSizePolicy.Preferred
        )
        hero_thumb_stack = QtWidgets.QStackedLayout(hero_thumb_container)
        hero_thumb_stack.setStackingMode(QtWidgets.QStackedLayout.StackAll)
        hero_thumb_stack.setContentsMargins(0, 0, 0, 0)

        self._hero_thumb = QtWidgets.QLabel()
        self._hero_thumb.setAlignment(QtCore.Qt.AlignCenter)
        self._hero_thumb.setScaledContents(False)
        self._hero_thumb.setStyleSheet(
            "background: rgba(50,50,50,0.6); border-radius: 6px; border: none;"
        )
        hero_thumb_stack.addWidget(self._hero_thumb)

        # Arrow overlay
        arrow_overlay = QtWidgets.QWidget()
        arrow_overlay.setStyleSheet("background: transparent; border: none;")
        arrow_overlay.setAttribute(QtCore.Qt.WA_TransparentForMouseEvents, False)
        arrow_ol = QtWidgets.QHBoxLayout(arrow_overlay)
        arrow_ol.setContentsMargins(4, 0, 4, 0)

        _arrow_btn_style = (
            "QPushButton { background: rgba(0,0,0,0.45); "
            "border: none; border-radius: 12px; }"
            "QPushButton:hover { background: rgba(0,0,0,0.7); }"
        )
        _icons_dir = Path(__file__).parent / "bgen_picker_icons"

        self._hero_prev_btn = QtWidgets.QPushButton()
        self._hero_prev_btn.setFixedSize(24, 24)
        self._hero_prev_btn.setCursor(QtCore.Qt.PointingHandCursor)
        self._hero_prev_btn.setIcon(QtGui.QIcon(
            QtGui.QPixmap(str(_icons_dir / "arrow_left_icon.png"))))
        self._hero_prev_btn.setIconSize(QtCore.QSize(14, 14))
        self._hero_prev_btn.setStyleSheet(_arrow_btn_style)
        self._hero_prev_btn.clicked.connect(self._hero_prev)

        self._hero_next_btn = QtWidgets.QPushButton()
        self._hero_next_btn.setFixedSize(24, 24)
        self._hero_next_btn.setCursor(QtCore.Qt.PointingHandCursor)
        self._hero_next_btn.setIcon(QtGui.QIcon(
            QtGui.QPixmap(str(_icons_dir / "arrow_right_icon.png"))))
        self._hero_next_btn.setIconSize(QtCore.QSize(14, 14))
        self._hero_next_btn.setStyleSheet(_arrow_btn_style)
        self._hero_next_btn.clicked.connect(self._hero_next)

        arrow_ol.addWidget(self._hero_prev_btn, 0, QtCore.Qt.AlignVCenter)
        arrow_ol.addStretch()
        arrow_ol.addWidget(self._hero_next_btn, 0, QtCore.Qt.AlignVCenter)
        hero_thumb_stack.addWidget(arrow_overlay)
        hero_thumb_stack.setCurrentWidget(arrow_overlay)

        self._current_hero_index = 0
        hero_layout.addWidget(hero_thumb_container)

        self._name_label = QtWidgets.QLabel()
        self._name_label.setWordWrap(True)
        self._name_label.setStyleSheet(
            "color: #e0e0e0; font-size: 14px; font-weight: bold; "
            "background: transparent; border: none;"
        )
        hero_layout.addWidget(self._name_label)

        self._creator_label = QtWidgets.QPushButton()
        self._creator_label.setCursor(QtCore.Qt.PointingHandCursor)
        self._creator_label.setStyleSheet(
            "QPushButton { color: #5b9bd5; font-size: 11px; "
            "background: transparent; border: none; text-align: left; padding: 0; }"
            "QPushButton:hover { color: #7db8f0; text-decoration: underline; }"
        )
        self._creator_label.clicked.connect(self._on_creator_clicked)
        self._creator_id = None
        hero_layout.addWidget(self._creator_label)

        # Star icon pixmaps (shared by display + interactive stars)
        _icons_dir = Path(__file__).parent / "bgen_picker_icons"
        self._star_gold_pix = QtGui.QPixmap(
            str(_icons_dir / "star-gold-icon.png"))
        self._star_white_pix = QtGui.QPixmap(
            str(_icons_dir / "star-white-icon.png"))
        self._star_gold_icon = QtGui.QIcon(self._star_gold_pix)
        self._star_white_icon = QtGui.QIcon(self._star_white_pix)

        # Rating display row (non-interactive)
        rating_row = QtWidgets.QHBoxLayout()
        rating_row.setSpacing(2)
        self._star_display_labels = []
        for _ in range(5):
            sl = QtWidgets.QLabel()
            sl.setFixedSize(14, 14)
            sl.setScaledContents(True)
            sl.setStyleSheet("background: transparent; border: none;")
            sl.setPixmap(self._star_white_pix)
            rating_row.addWidget(sl)
            self._star_display_labels.append(sl)
        rating_row.addSpacing(2)
        self._rating_text = QtWidgets.QLabel()
        self._rating_text.setStyleSheet(
            "color: #888888; font-size: 10px; background: transparent; border: none;"
        )
        rating_row.addWidget(self._rating_text)
        rating_row.addStretch()
        hero_layout.addLayout(rating_row)

        # Interactive star rating (visible only for owned products)
        self._user_rating_row = QtWidgets.QWidget()
        ur_layout = QtWidgets.QHBoxLayout(self._user_rating_row)
        ur_layout.setContentsMargins(0, 0, 0, 0)
        ur_layout.setSpacing(2)
        self._user_rating_label = QtWidgets.QLabel("Your rating:")
        self._user_rating_label.setStyleSheet(
            "color: #888888; font-size: 10px; background: transparent; border: none;"
        )
        ur_layout.addWidget(self._user_rating_label)
        self._star_buttons = []
        for i in range(5):
            btn = _HoverStarButton()
            btn.setFixedSize(20, 20)
            btn.setIconSize(QtCore.QSize(16, 16))
            btn.setCursor(QtCore.Qt.PointingHandCursor)
            btn.setStyleSheet(
                "QPushButton { background: transparent; border: none; padding: 0; }"
            )
            btn.setIcon(self._star_white_icon)
            btn.clicked.connect(lambda _=False, idx=i + 1: self._on_star_clicked(idx))
            ur_layout.addWidget(btn)
            self._star_buttons.append(btn)
        ur_layout.addStretch()
        self._user_rating_row.setVisible(False)
        hero_layout.addWidget(self._user_rating_row)

        self._user_rating = 0  # current user's rating (0 = not rated)

        self._downloads_label = QtWidgets.QLabel()
        self._downloads_label.setStyleSheet(
            "color: #888888; font-size: 10px; background: transparent; border: none;"
        )
        hero_layout.addWidget(self._downloads_label)

        # Action button — full width
        self._action_btn = QtWidgets.QPushButton()
        self._action_btn.setFixedHeight(28)
        self._action_btn.setCursor(QtCore.Qt.PointingHandCursor)
        self._action_btn.clicked.connect(self._on_action_clicked)
        hero_layout.addWidget(self._action_btn)

        # Download progress bar (hidden by default)
        self._dl_progress_bar = QtWidgets.QProgressBar()
        self._dl_progress_bar.setFixedHeight(6)
        self._dl_progress_bar.setTextVisible(False)
        self._dl_progress_bar.setRange(0, 100)
        self._dl_progress_bar.setValue(0)
        self._dl_progress_bar.setStyleSheet(
            "QProgressBar { background: rgba(255,255,255,0.08); "
            "border: none; border-radius: 3px; }"
            "QProgressBar::chunk { background: #1D65CA; border-radius: 3px; }"
        )
        self._dl_progress_bar.hide()
        hero_layout.addWidget(self._dl_progress_bar)

        self._dl_progress_label = QtWidgets.QLabel("Downloading\u2026")
        self._dl_progress_label.setStyleSheet(
            "color: #999999; font-size: 9px; background: transparent; border: none;"
        )
        self._dl_progress_label.setAlignment(QtCore.Qt.AlignRight)
        self._dl_progress_label.hide()
        hero_layout.addWidget(self._dl_progress_label)

        # Download status label (hidden by default)
        self._dl_status_lbl = QtWidgets.QLabel()
        self._dl_status_lbl.setAlignment(QtCore.Qt.AlignCenter)
        self._dl_status_lbl.setWordWrap(True)
        self._dl_status_lbl.hide()
        hero_layout.addWidget(self._dl_status_lbl)

        # Auto-dismiss timer for status
        self._dl_status_timer = QtCore.QTimer(self)
        self._dl_status_timer.setSingleShot(True)
        self._dl_status_timer.setInterval(8000)
        self._dl_status_timer.timeout.connect(self._on_dl_status_timeout)

        self._downloading_product_id = None

        self._content_layout.addWidget(hero_frame)

        # [Gallery Section]
        gallery_title = QtWidgets.QLabel("Gallery")
        gallery_title.setStyleSheet(
            "color: #dddddd; font-size: 13px; font-weight: bold; "
            "background: transparent; border: none;"
        )
        self._content_layout.addWidget(gallery_title)

        gallery_scroll = QtWidgets.QScrollArea()
        gallery_scroll.setFixedHeight(72)
        gallery_scroll.setWidgetResizable(True)
        gallery_scroll.setFrameShape(QtWidgets.QFrame.NoFrame)
        gallery_scroll.setVerticalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)
        gallery_scroll.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarAsNeeded)
        gallery_scroll.setStyleSheet(
            "QScrollArea { background: transparent; border: none; }"
            "QScrollBar:horizontal { height: 4px; background: transparent; }"
            "QScrollBar::handle:horizontal { background: rgba(255,255,255,0.15); "
            "border-radius: 2px; min-width: 20px; }"
            "QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal { width: 0; }"
        )
        self._gallery_widget = QtWidgets.QWidget()
        self._gallery_layout = QtWidgets.QHBoxLayout(self._gallery_widget)
        self._gallery_layout.setContentsMargins(0, 0, 0, 0)
        self._gallery_layout.setSpacing(6)
        gallery_scroll.setWidget(self._gallery_widget)
        self._content_layout.addWidget(gallery_scroll)

        # [Description Section]
        desc_title = QtWidgets.QLabel("Description")
        desc_title.setStyleSheet(
            "color: #dddddd; font-size: 13px; font-weight: bold; "
            "background: transparent; border: none;"
        )
        self._content_layout.addWidget(desc_title)

        self._description_label = QtWidgets.QLabel()
        self._description_label.setWordWrap(True)
        self._description_label.setStyleSheet(
            "color: #aaaaaa; font-size: 11px; background: transparent; border: none;"
        )
        self._content_layout.addWidget(self._description_label)

        # [Details Section]
        details_title = QtWidgets.QLabel("Details")
        details_title.setStyleSheet(
            "color: #dddddd; font-size: 13px; font-weight: bold; "
            "background: transparent; border: none;"
        )
        self._content_layout.addWidget(details_title)

        self._details_frame = QtWidgets.QFrame()
        self._details_frame.setStyleSheet(
            "QFrame { background: rgba(255,255,255,0.04); "
            "border: 1px solid rgba(255,255,255,0.06); border-radius: 8px; }"
        )
        self._details_frame.setMinimumWidth(0)
        self._details_layout = QtWidgets.QGridLayout(self._details_frame)
        self._details_layout.setSizeConstraint(QtWidgets.QLayout.SetNoConstraint)
        self._details_layout.setContentsMargins(12, 8, 12, 8)
        self._details_layout.setSpacing(4)
        self._content_layout.addWidget(self._details_frame)

        self._content_layout.addStretch()
        scroll.setWidget(content)
        main_layout.addWidget(scroll)

    # ------------------------------------------------------------------
    # Data population
    # ------------------------------------------------------------------

    def load_product(self, product: dict):
        """Populate all widgets with data from the product dict."""
        self._product = product
        mgr = BgenLocalFileManager.get_instance()

        # Reset scroll position and clear stale state
        self._reset_download_state()
        self._scroll.verticalScrollBar().setValue(0)
        self._hero_thumb.clear()
        self._hero_image_path = None
        self._gallery_paths = {}
        self._gallery_slots = []
        self._current_hero_index = 0
        self._update_hero_arrows()

        name = product.get("name", "Untitled")
        self._toolbar_name.setText(name)
        self._name_label.setText(name)

        creator = product.get("creator", "")
        self._creator_id = product.get("creator_id")
        self._creator_label.setText(f"by {creator}" if creator else "")
        self._creator_label.setVisible(bool(creator))

        # Stars
        rating = product.get("rating_avg", 0)
        rating_count = product.get("rating_count", 0)
        filled = int(round(rating))
        for i, sl in enumerate(self._star_display_labels):
            sl.setPixmap(
                self._star_gold_pix if i < filled else self._star_white_pix
            )
        if rating_count:
            self._rating_text.setText(f"{rating:.1f}  ({rating_count} ratings)")
        else:
            self._rating_text.setText("No ratings yet")

        # Interactive rating (only for owned products)
        owned = product.get("owned", False)
        self._user_rating_row.setVisible(owned)
        if owned:
            self._update_star_buttons(0)
            self._user_rating_label.setText("Rate this picker:")
            mgr.fetch_user_rating(
                product.get("id", ""), self._on_user_rating_fetched
            )

        # Downloads
        downloads = product.get("download_count", 0)
        self._downloads_label.setText(f"{downloads:,} downloads")

        # Description
        desc = product.get("short_description", "No description available.")
        self._description_label.setText(desc)

        # Gallery (before thumbnail — no layout dependency)
        self._populate_gallery(product)

        # Async thumbnail from server (may resolve synchronously from disk cache)
        self._load_hero_thumbnail(product)

        # Hero placeholder — deferred so layout width is settled, but only
        # if no real thumbnail was already loaded (disk cache hit sets
        # _hero_image_path synchronously before this deferred call runs).
        QtCore.QTimer.singleShot(
            0, lambda: self._set_hero_thumbnail(product)
            if not self._hero_image_path else None,
        )

        # Details grid
        self._populate_details(product)

        # Action button
        owned = product.get("owned", False)
        price_cents = product.get("price_cents", 0)
        if owned:
            self._action_btn.setText("Download")
            self._action_btn.setStyleSheet(
                "QPushButton { background: #50a032; color: white; "
                "border: none; border-radius: 6px; font-size: 12px; font-weight: bold; }"
                "QPushButton:hover { background: #5cb838; }"
            )
            self._action_type = "download"
        elif price_cents == 0:
            self._action_btn.setText("Get Free")
            self._action_btn.setStyleSheet(
                "QPushButton { background: #7db305; color: white; "
                "border: none; border-radius: 6px; font-size: 12px; font-weight: bold; }"
                "QPushButton:hover { background: #8ec40f; }"
            )
            self._action_type = "get_free"
        else:
            price_text = mgr.format_price(product)
            self._action_btn.setText(f"Buy {price_text}")
            self._action_btn.setStyleSheet(
                "QPushButton { background: #1D65CA; color: white; "
                "border: none; border-radius: 6px; font-size: 12px; font-weight: bold; }"
                "QPushButton:hover { background: #2575da; }"
            )
            self._action_type = "buy"

    # ------------------------------------------------------------------
    # Star rating interaction
    # ------------------------------------------------------------------

    def _on_star_clicked(self, rating):
        """User clicked a star to rate."""
        if not self._product:
            return
        self._prev_user_rating = self._user_rating
        self._user_rating = rating
        self._update_star_buttons(rating)
        self._user_rating_label.setText("Saving...")
        self._user_rating_label.setStyleSheet(
            "color: #f5a623; font-size: 10px; background: transparent; border: none;"
        )
        pid = self._product.get("id", "")
        mgr = BgenLocalFileManager.get_instance()
        # Connect signals for feedback (disconnect first to avoid duplicates)
        try:
            mgr.rating_submitted.disconnect(self._on_rating_saved)
        except (RuntimeError, TypeError):
            pass
        try:
            mgr.rating_failed.disconnect(self._on_rating_failed)
        except (RuntimeError, TypeError):
            pass
        mgr.rating_submitted.connect(self._on_rating_saved)
        mgr.rating_failed.connect(self._on_rating_failed)
        mgr.submit_rating(pid, rating)

    def _on_rating_saved(self, product_id, rating, rating_avg, rating_count):
        """Callback when rating is successfully saved to the server."""
        if not self._product or self._product.get("id") != product_id:
            return
        self._user_rating_label.setText(f"Saved! Your rating: {rating}/5")
        self._user_rating_label.setStyleSheet(
            "color: #7db305; font-size: 10px; background: transparent; border: none;"
        )

        # Update the product-level aggregate display
        if rating_count:
            self._rating_text.setText(f"{rating_avg:.1f}  ({rating_count} ratings)")
        else:
            self._rating_text.setText("No ratings yet")
        filled = int(round(rating_avg))
        for i, sl in enumerate(self._star_display_labels):
            sl.setPixmap(
                self._star_gold_pix if i < filled else self._star_white_pix
            )

        # Update cached product dict so navigation shows correct values
        if self._product:
            self._product["rating_avg"] = rating_avg
            self._product["rating_count"] = rating_count

        # Reset label after a moment
        def _reset_label():
            if self._product:
                self._user_rating_label.setText("Your rating:")
                self._user_rating_label.setStyleSheet(
                    "color: #888888; font-size: 10px; background: transparent; border: none;"
                )
        QtCore.QTimer.singleShot(2000, _reset_label)

    def _on_rating_failed(self, product_id, error_msg):
        """Callback when rating submission fails."""
        if not self._product or self._product.get("id") != product_id:
            return
        self._user_rating = getattr(self, "_prev_user_rating", 0)
        self._update_star_buttons(self._user_rating)
        self._user_rating_label.setText("Failed to save")
        self._user_rating_label.setStyleSheet(
            "color: #ff6b6b; font-size: 10px; background: transparent; border: none;"
        )
        # Reset label after a moment
        def _reset_label():
            if self._product:
                label_text = "Your rating:" if self._user_rating else "Rate this picker:"
                self._user_rating_label.setText(label_text)
                self._user_rating_label.setStyleSheet(
                    "color: #888888; font-size: 10px; background: transparent; border: none;"
                )
        QtCore.QTimer.singleShot(3000, _reset_label)

    def _update_star_buttons(self, rating):
        """Update star button visuals to reflect a rating value."""
        for i, btn in enumerate(self._star_buttons):
            if i < rating:
                btn.setIcon(self._star_gold_icon)
            else:
                btn.setIcon(self._star_white_icon)

    def _on_user_rating_fetched(self, product_id, rating):
        """Callback when user's existing rating is fetched."""
        if not self._product or self._product.get("id") != product_id:
            return
        if rating is not None:
            self._user_rating = rating
            self._update_star_buttons(rating)
            self._user_rating_label.setText("Your rating:")
            self._user_rating_label.setStyleSheet(
                "color: #888888; font-size: 10px; background: transparent; border: none;"
            )
        else:
            self._user_rating = 0
            self._update_star_buttons(0)
            self._user_rating_label.setText("Rate this picker:")
            self._user_rating_label.setStyleSheet(
                "color: #888888; font-size: 10px; background: transparent; border: none;"
            )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _set_hero_thumbnail(self, product):
        """Render a placeholder thumbnail with initials, sized to fit width."""
        w = max(self._hero_thumb.width(), 120)
        self._last_hero_width = w
        h = min(w, 200)
        name = product.get("name", "?")
        initials = name[0].upper() if name else "?"

        pixmap = QtGui.QPixmap(w, h)
        pixmap.fill(QtGui.QColor(45, 45, 50))
        painter = QtGui.QPainter(pixmap)
        painter.setRenderHint(QtGui.QPainter.Antialiasing)
        painter.setBrush(QtGui.QColor(55, 60, 70))
        painter.setPen(QtCore.Qt.NoPen)
        painter.drawRoundedRect(0, 0, w, h, 6, 6)
        painter.setPen(QtGui.QColor(140, 150, 170))
        font = painter.font()
        font.setPixelSize(max(30, h // 3))
        font.setBold(True)
        painter.setFont(font)
        painter.drawText(QtCore.QRect(0, 0, w, h),
                         QtCore.Qt.AlignCenter, initials)
        painter.end()
        self._hero_thumb.setPixmap(pixmap)

    def _populate_gallery(self, product):
        """Build gallery row: main thumb + preview image slots."""
        while self._gallery_layout.count():
            item = self._gallery_layout.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()
        self._gallery_slots = []

        slot_size = 56
        mgr = BgenLocalFileManager.get_instance()

        # Collect image URLs: thumbnail first, then preview_images
        image_urls = []
        thumb_url = mgr.get_thumbnail_url(product)
        if thumb_url:
            image_urls.append(thumb_url)
        for path in product.get("preview_images", []):
            if path and CFG.SUPABASE_URL:
                url = (
                    f"{CFG.SUPABASE_URL}/storage/v1/object/public/"
                    f"{CFG.LIBRARY_THUMBNAILS_BUCKET}/{path}"
                )
                image_urls.append(url)

        # Always show at least 1 slot (placeholder if no images)
        num_slots = max(len(image_urls), 1)

        for i in range(num_slots):
            slot = QtWidgets.QPushButton()
            slot.setFixedSize(slot_size, slot_size)
            slot.setCursor(QtCore.Qt.PointingHandCursor)
            slot.setStyleSheet(
                "QPushButton { background: rgba(50,50,50,0.4); border-radius: 4px;"
                " border: 1px solid rgba(255,255,255,0.06); }"
                "QPushButton:hover { border: 1px solid rgba(255,255,255,0.2); }"
            )

            if i == 0:
                # First slot: show initials placeholder, highlighted border
                name = product.get("name", "?")
                initials = name[0].upper() if name else "?"
                pix = QtGui.QPixmap(slot_size, slot_size)
                pix.fill(QtGui.QColor(55, 60, 70))
                p = QtGui.QPainter(pix)
                p.setRenderHint(QtGui.QPainter.Antialiasing)
                p.setPen(QtGui.QColor(140, 150, 170))
                f = p.font()
                f.setPixelSize(24)
                f.setBold(True)
                p.setFont(f)
                p.drawText(QtCore.QRect(0, 0, slot_size, slot_size),
                           QtCore.Qt.AlignCenter, initials)
                p.end()
                slot.setIcon(QtGui.QIcon(pix))
                slot.setIconSize(QtCore.QSize(slot_size - 4, slot_size - 4))
                slot.setStyleSheet(
                    "QPushButton { border-radius: 4px;"
                    " border: 2px solid rgba(29,101,202,0.6); }"
                )

            # Async-load the real image for this slot
            if i < len(image_urls):
                idx = i
                url = image_urls[i]
                pid = f"{product.get('id', '')}_gallery_{i}"
                mgr.load_thumbnail_async(
                    pid, url,
                    lambda _pid, path, _slot=slot, _idx=idx: self._on_gallery_thumb_loaded(_slot, _idx, path),
                )

            # Click to set hero image
            slot.clicked.connect(lambda checked=False, _i=i: self._on_gallery_slot_clicked(_i))

            self._gallery_slots.append(slot)
            self._gallery_layout.addWidget(slot)
        self._gallery_layout.addStretch()
        self._update_hero_arrows()

    def _on_gallery_thumb_loaded(self, slot, index, file_path):
        """Callback when a gallery thumbnail finishes downloading."""
        if not file_path or not os.path.isfile(file_path):
            return
        try:
            pixmap = QtGui.QPixmap(file_path)
            if pixmap.isNull():
                return
            slot_size = slot.width()
            scaled = pixmap.scaled(
                slot_size - 4, slot_size - 4,
                QtCore.Qt.KeepAspectRatio,
                QtCore.Qt.SmoothTransformation,
            )
            slot.setIcon(QtGui.QIcon(scaled))
            slot.setIconSize(QtCore.QSize(slot_size - 4, slot_size - 4))
        except RuntimeError:
            return  # Widget already deleted
        # Cache the file path for hero switching
        if not hasattr(self, "_gallery_paths"):
            self._gallery_paths = {}
        self._gallery_paths[index] = file_path

    def _on_gallery_slot_clicked(self, index):
        """Switch the hero image to the clicked gallery slot's image."""
        paths = getattr(self, "_gallery_paths", {})
        file_path = paths.get(index)
        if not file_path or not os.path.isfile(file_path):
            return
        pixmap = QtGui.QPixmap(file_path)
        if pixmap.isNull():
            return
        self._hero_image_path = file_path
        self._current_hero_index = index
        w = max(self._hero_thumb.width(), 120)
        h = min(w, 200)
        scaled = pixmap.scaled(w, h, QtCore.Qt.KeepAspectRatio, QtCore.Qt.SmoothTransformation)
        self._hero_thumb.setPixmap(scaled)

        # Update slot borders — highlight selected
        for i, slot in enumerate(getattr(self, "_gallery_slots", [])):
            if i == index:
                slot.setStyleSheet(
                    "QPushButton { border-radius: 4px;"
                    " border: 2px solid rgba(29,101,202,0.6); }"
                )
            else:
                slot.setStyleSheet(
                    "QPushButton { background: rgba(50,50,50,0.4); border-radius: 4px;"
                    " border: 1px solid rgba(255,255,255,0.06); }"
                    "QPushButton:hover { border: 1px solid rgba(255,255,255,0.2); }"
                )
        self._update_hero_arrows()

    def _hero_prev(self):
        """Navigate to the previous gallery image."""
        if self._current_hero_index > 0:
            self._on_gallery_slot_clicked(self._current_hero_index - 1)

    def _hero_next(self):
        """Navigate to the next gallery image."""
        total = len(getattr(self, "_gallery_slots", []))
        if self._current_hero_index < total - 1:
            self._on_gallery_slot_clicked(self._current_hero_index + 1)

    def _update_hero_arrows(self):
        """Show/hide arrow buttons based on current position and total images."""
        total = len(getattr(self, "_gallery_slots", []))
        self._hero_prev_btn.setVisible(self._current_hero_index > 0)
        self._hero_next_btn.setVisible(self._current_hero_index < total - 1)

    def _populate_details(self, product):
        """Fill the details grid with key-value pairs."""
        while self._details_layout.count():
            item = self._details_layout.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()

        mgr = BgenLocalFileManager.get_instance()
        details = [
            ("Category", product.get("category", "N/A")),
            ("Price", mgr.format_price(product)),
            ("Tags", ", ".join(product.get("tags", []))),
            ("Status", product.get("status", "N/A").title()),
        ]

        label_style = ("color: #888888; font-size: 11px; "
                       "background: transparent; border: none;")
        value_style = ("color: #cccccc; font-size: 11px; "
                       "background: transparent; border: none;")

        for row, (key, value) in enumerate(details):
            key_label = QtWidgets.QLabel(key)
            key_label.setStyleSheet(label_style)
            key_label.setFixedWidth(55)
            val_label = QtWidgets.QLabel(str(value))
            val_label.setStyleSheet(value_style)
            val_label.setWordWrap(True)
            self._details_layout.addWidget(key_label, row, 0)
            self._details_layout.addWidget(val_label, row, 1)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self._product:
            self._hero_resize_timer.start()

    def _on_hero_resize(self):
        """Regenerate hero thumbnail when width changes significantly."""
        if not self._product:
            return
        new_w = max(self._hero_thumb.width(), 120)
        if abs(new_w - self._last_hero_width) > 10:
            # Use real image if available, otherwise fall back to initials
            if self._hero_image_path and os.path.isfile(self._hero_image_path):
                pixmap = QtGui.QPixmap(self._hero_image_path)
                if not pixmap.isNull():
                    self._last_hero_width = new_w
                    h = min(new_w, 200)
                    scaled = pixmap.scaled(
                        new_w, h,
                        QtCore.Qt.KeepAspectRatio,
                        QtCore.Qt.SmoothTransformation,
                    )
                    self._hero_thumb.setPixmap(scaled)
                    return
            self._set_hero_thumbnail(self._product)

    def _load_hero_thumbnail(self, product):
        """Request async thumbnail download for the hero image."""
        mgr = BgenLocalFileManager.get_instance()
        url = mgr.get_thumbnail_url(product)
        pid = product.get("id", "")
        if url and pid:
            mgr.load_thumbnail_async(pid, url, self._on_hero_thumbnail_loaded)

    def _on_hero_thumbnail_loaded(self, product_id, file_path):
        """Callback when hero thumbnail is downloaded."""
        if not self._product or self._product.get("id") != product_id:
            return
        if not file_path or not os.path.isfile(file_path):
            return
        try:
            pixmap = QtGui.QPixmap(file_path)
            if not pixmap.isNull():
                self._hero_image_path = file_path
                w = max(self._hero_thumb.width(), 120)
                h = min(w, 200)
                scaled = pixmap.scaled(
                    w, h,
                    QtCore.Qt.KeepAspectRatio,
                    QtCore.Qt.SmoothTransformation,
                )
                self._hero_thumb.setPixmap(scaled)
        except RuntimeError:
            pass  # Widget already deleted

    def _on_action_clicked(self):
        """Handle the action button click."""
        if not self._product:
            return
        product_id = self._product.get("id", "")
        self.action_requested.emit(product_id, self._action_type)

    # ------------------------------------------------------------------
    # Download state methods
    # ------------------------------------------------------------------

    def _on_creator_clicked(self):
        """Emit creator_clicked when the 'by Creator' link is pressed."""
        if self._creator_id:
            self.creator_clicked.emit(self._creator_id)

    def _reset_download_state(self):
        """Return to idle: show action button, hide progress/status."""
        self._downloading_product_id = None
        self._dl_status_timer.stop()
        self._action_btn.show()
        self._action_btn.setEnabled(True)
        self._dl_progress_bar.hide()
        self._dl_progress_label.hide()
        self._dl_status_lbl.hide()

    def set_download_started(self):
        """Switch to progress state."""
        if self._product:
            self._downloading_product_id = self._product.get("id", "")
        self._action_btn.hide()
        self._dl_progress_bar.setValue(0)
        self._dl_progress_bar.setRange(0, 100)
        self._dl_progress_bar.show()
        self._dl_progress_label.setText("Downloading\u2026")
        self._dl_progress_label.show()
        self._dl_status_lbl.hide()

    def set_download_progress(self, done, total):
        """Update progress bar and label."""
        if total > 0:
            pct = int(done * 100 / total)
            self._dl_progress_bar.setValue(pct)
            if total >= 1024 * 1024:
                self._dl_progress_label.setText(
                    f"{done / (1024*1024):.1f} / {total / (1024*1024):.1f} MB"
                )
            else:
                self._dl_progress_label.setText(
                    f"{done / 1024:.0f} / {total / 1024:.0f} KB"
                )
        else:
            self._dl_progress_bar.setRange(0, 0)  # indeterminate
            self._dl_progress_label.setText("Downloading\u2026")

    def set_download_completed(self, dest_path):
        """Show success status with destination path."""
        self._downloading_product_id = None
        self._dl_progress_bar.hide()
        self._dl_progress_label.hide()
        # Determine friendly location text
        from pathlib import Path
        p = Path(dest_path)
        try:
            from .local_file_manager import LocalFileManager
            lib_path = LocalFileManager.get_library_path()
            if str(p).startswith(str(lib_path)):
                location = "Added to Library"
            else:
                location = f"Saved to {p.parent.name}"
        except Exception:
            location = "Downloaded"
        self._dl_status_lbl.setText(f"\u2713 {location}")
        self._dl_status_lbl.setStyleSheet(
            "color: #50a032; font-size: 11px; font-weight: bold; "
            "background: transparent; border: none;"
        )
        self._dl_status_lbl.show()
        self._dl_status_timer.start()

    def set_download_failed(self, error_msg):
        """Show error status."""
        self._downloading_product_id = None
        self._dl_progress_bar.hide()
        self._dl_progress_label.hide()
        short = error_msg[:60] + "\u2026" if len(error_msg) > 60 else error_msg
        self._dl_status_lbl.setText(f"\u2717 {short}")
        self._dl_status_lbl.setStyleSheet(
            "color: #cc4444; font-size: 11px; "
            "background: transparent; border: none;"
        )
        self._dl_status_lbl.show()
        self._dl_status_timer.start()

    def _on_dl_status_timeout(self):
        """Return to idle state after showing status briefly."""
        self._dl_status_lbl.hide()
        self._action_btn.show()
        self._action_btn.setEnabled(True)


# -----------------------------------------------------------------------
# Owned Items Page
# -----------------------------------------------------------------------

class _OwnedItemCard(QtWidgets.QFrame):
    """Compact card for an owned product in the purchases page."""

    download_requested = QtCore.Signal(str)  # product_id

    def __init__(self, purchase, parent=None):
        super().__init__(parent)
        self._purchase = purchase
        self._product_id = purchase.get("product_id", "")
        self._is_downloading = False
        self.setCursor(QtCore.Qt.PointingHandCursor)
        self.setStyleSheet(
            "QFrame { background: rgba(255,255,255,0.04); "
            "border: 1px solid rgba(255,255,255,0.06); "
            "border-radius: 8px; }"
            "QFrame:hover { background: rgba(255,255,255,0.08); "
            "border-color: rgba(255,255,255,0.12); }"
        )
        self.setFixedHeight(64)

        layout = QtWidgets.QHBoxLayout(self)
        layout.setContentsMargins(8, 6, 8, 6)
        layout.setSpacing(10)

        # Thumbnail placeholder
        self._thumb = QtWidgets.QLabel()
        self._thumb.setFixedSize(48, 48)
        self._thumb.setAlignment(QtCore.Qt.AlignCenter)
        self._thumb.setStyleSheet(
            "background: rgba(50,50,50,0.6); border-radius: 6px; border: none;"
        )
        name = purchase.get("product_name", "?")
        initials = name[0].upper() if name else "?"
        self._thumb.setText(initials)
        self._thumb.setStyleSheet(
            "background: rgba(50,50,50,0.6); border-radius: 6px; border: none; "
            "color: #888888; font-size: 18px; font-weight: bold;"
        )
        layout.addWidget(self._thumb)

        # Info column
        self._info_layout = QtWidgets.QVBoxLayout()
        self._info_layout.setSpacing(2)
        self._name_lbl = QtWidgets.QLabel(purchase.get("product_name", "Unknown"))
        self._name_lbl.setStyleSheet(
            "color: #cccccc; font-size: 12px; font-weight: bold; "
            "background: transparent; border: none;"
        )
        self._info_layout.addWidget(self._name_lbl)

        cat = purchase.get("category", "")
        sub_text = cat if cat else ""
        dl_count = purchase.get("download_count", 0)
        if dl_count:
            sub_text += f"  \u2022  {dl_count} download{'s' if dl_count != 1 else ''}"
        sub_row = QtWidgets.QHBoxLayout()
        sub_row.setContentsMargins(0, 0, 0, 0)
        sub_row.setSpacing(4)
        self._sub_lbl = QtWidgets.QLabel(sub_text)
        self._sub_lbl.setStyleSheet(
            "color: #888888; font-size: 10px; background: transparent; border: none;"
        )
        sub_row.addWidget(self._sub_lbl)

        # Software icon
        software = purchase.get("software")
        if software in ("maya", "blender"):
            icon_name = "maya_icon.png" if software == "maya" else "blender_icon.png"
            sw_pixmap = get_icon(icon_name, size=16)
            if sw_pixmap and not sw_pixmap.isNull():
                sw_label = QtWidgets.QLabel()
                sw_label.setFixedSize(16, 16)
                sw_label.setPixmap(sw_pixmap)
                sw_label.setStyleSheet("background: transparent; border: none;")
                sub_row.addWidget(sw_label)

        sub_row.addStretch()
        self._info_layout.addLayout(sub_row)
        layout.addLayout(self._info_layout, 1)

        # Right-side stacked widget: download btn / progress bar / status
        self._action_stack = QtWidgets.QStackedWidget()
        self._action_stack.setFixedWidth(100)
        self._action_stack.setStyleSheet("background: transparent; border: none;")
        layout.addWidget(self._action_stack)

        # Page 0: Download button or In Library badge
        in_library = purchase.get("is_in_library", False)
        if in_library:
            badge = QtWidgets.QLabel("In Library")
            badge.setAlignment(QtCore.Qt.AlignRight | QtCore.Qt.AlignVCenter)
            badge.setStyleSheet(
                "color: #50a032; font-size: 10px; font-weight: bold; "
                "background: transparent; border: none;"
            )
            self._action_stack.addWidget(badge)  # index 0
        else:
            self._dl_btn = QtWidgets.QPushButton("Download")
            self._dl_btn.setFixedSize(72, 24)
            self._dl_btn.setCursor(QtCore.Qt.PointingHandCursor)
            self._dl_btn.setStyleSheet(
                "QPushButton { background: #1D65CA; color: white; "
                "border: none; border-radius: 4px; font-size: 10px; }"
                "QPushButton:hover { background: #2575da; }"
            )
            self._dl_btn.clicked.connect(
                lambda: self.download_requested.emit(self._product_id)
            )
            btn_wrapper = QtWidgets.QWidget()
            btn_wrapper.setStyleSheet("background: transparent; border: none;")
            btn_lay = QtWidgets.QHBoxLayout(btn_wrapper)
            btn_lay.setContentsMargins(0, 0, 0, 0)
            btn_lay.addStretch()
            btn_lay.addWidget(self._dl_btn)
            self._action_stack.addWidget(btn_wrapper)  # index 0

        # Page 1: Progress bar
        self._progress_bar = QtWidgets.QProgressBar()
        self._progress_bar.setFixedHeight(6)
        self._progress_bar.setTextVisible(False)
        self._progress_bar.setRange(0, 100)
        self._progress_bar.setValue(0)
        self._progress_bar.setStyleSheet(
            "QProgressBar { background: rgba(255,255,255,0.08); "
            "border: none; border-radius: 3px; }"
            "QProgressBar::chunk { background: #1D65CA; border-radius: 3px; }"
        )
        progress_wrapper = QtWidgets.QWidget()
        progress_wrapper.setStyleSheet("background: transparent; border: none;")
        prog_lay = QtWidgets.QVBoxLayout(progress_wrapper)
        prog_lay.setContentsMargins(0, 0, 0, 0)
        prog_lay.setSpacing(3)
        prog_lay.addStretch()
        prog_lay.addWidget(self._progress_bar)
        self._progress_label = QtWidgets.QLabel("Downloading...")
        self._progress_label.setStyleSheet(
            "color: #999999; font-size: 9px; background: transparent; border: none;"
        )
        self._progress_label.setAlignment(QtCore.Qt.AlignRight)
        prog_lay.addWidget(self._progress_label)
        prog_lay.addStretch()
        self._action_stack.addWidget(progress_wrapper)  # index 1

        # Page 2: Completed status
        self._status_lbl = QtWidgets.QLabel()
        self._status_lbl.setAlignment(QtCore.Qt.AlignRight | QtCore.Qt.AlignVCenter)
        self._status_lbl.setWordWrap(True)
        self._status_lbl.setStyleSheet(
            "color: #50a032; font-size: 9px; background: transparent; border: none;"
        )
        self._action_stack.addWidget(self._status_lbl)  # index 2

        self._action_stack.setCurrentIndex(0)

        # Auto-hide status timer
        self._status_timer = QtCore.QTimer(self)
        self._status_timer.setSingleShot(True)
        self._status_timer.setInterval(8000)
        self._status_timer.timeout.connect(self._on_status_timeout)

        # Load thumbnail async
        thumb_url = purchase.get("product_thumbnail_url", "")
        if thumb_url:
            mgr = BgenLocalFileManager.get_instance()
            mgr.load_thumbnail_async(
                self._product_id, thumb_url, self._on_thumb_loaded
            )

    # ---- download state methods ----

    def set_download_started(self):
        """Switch to progress bar view."""
        self._is_downloading = True
        self._progress_bar.setValue(0)
        self._progress_label.setText("Downloading\u2026")
        self._action_stack.setCurrentIndex(1)

    def set_download_progress(self, done, total):
        """Update progress bar."""
        if total > 0:
            pct = int(done * 100 / total)
            self._progress_bar.setValue(pct)
            if total >= 1024 * 1024:
                self._progress_label.setText(
                    f"{done / (1024*1024):.1f} / {total / (1024*1024):.1f} MB"
                )
            else:
                self._progress_label.setText(
                    f"{done / 1024:.0f} / {total / 1024:.0f} KB"
                )
        else:
            self._progress_bar.setRange(0, 0)  # indeterminate
            self._progress_label.setText("Downloading\u2026")

    def set_download_completed(self, dest_path):
        """Show success status with destination path."""
        self._is_downloading = False
        self._progress_bar.setValue(100)
        # Determine friendly location text
        from pathlib import Path
        p = Path(dest_path)
        try:
            from .local_file_manager import LocalFileManager
            lib_path = LocalFileManager.get_library_path()
            if str(p).startswith(str(lib_path)):
                location = "Added to Library"
            else:
                location = f"Saved to {p.parent.name}"
        except Exception:
            location = "Downloaded"
        self._status_lbl.setText(f"\u2713 {location}")
        self._status_lbl.setStyleSheet(
            "color: #50a032; font-size: 9px; background: transparent; border: none;"
        )
        self._action_stack.setCurrentIndex(2)
        self._status_timer.start()

    def set_download_failed(self, error_msg):
        """Show error status."""
        self._is_downloading = False
        short = error_msg[:40] + "\u2026" if len(error_msg) > 40 else error_msg
        self._status_lbl.setText(f"\u2717 {short}")
        self._status_lbl.setStyleSheet(
            "color: #cc4444; font-size: 9px; background: transparent; border: none;"
        )
        self._action_stack.setCurrentIndex(2)
        self._status_timer.start()

    def _on_status_timeout(self):
        """Return to initial state after showing status briefly."""
        self._action_stack.setCurrentIndex(0)

    def _on_thumb_loaded(self, product_id, path):
        """Set thumbnail from cached file."""
        try:
            pixmap = QtGui.QPixmap(path)
            if not pixmap.isNull():
                scaled = pixmap.scaled(
                    48, 48,
                    QtCore.Qt.KeepAspectRatio,
                    QtCore.Qt.SmoothTransformation,
                )
                self._thumb.setPixmap(scaled)
                self._thumb.setText("")
        except RuntimeError:
            pass


class OwnedItemsPage(QtWidgets.QWidget):
    """Full-page view of the user's purchased bgen_library items."""

    back_requested = QtCore.Signal()
    download_requested = QtCore.Signal(str)  # product_id

    def __init__(self, parent=None):
        super().__init__(parent)
        self._purchases = []
        self._build_ui()

    def _build_ui(self):
        root = QtWidgets.QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # Toolbar
        toolbar = QtWidgets.QHBoxLayout()
        toolbar.setContentsMargins(8, 6, 8, 6)
        toolbar.setSpacing(8)

        back_btn = QtWidgets.QPushButton("\u2039")  # left chevron
        back_btn.setFixedSize(24, 24)
        back_btn.setCursor(QtCore.Qt.PointingHandCursor)
        back_btn.setStyleSheet(
            "QPushButton { background: rgba(255,255,255,0.06); "
            "border: 1px solid rgba(255,255,255,0.08); "
            "border-radius: 12px; color: #cccccc; font-size: 16px; }"
            "QPushButton:hover { background: rgba(255,255,255,0.12); }"
        )
        back_btn.clicked.connect(self.back_requested.emit)
        toolbar.addWidget(back_btn)

        title = QtWidgets.QLabel("Owned Items")
        title.setStyleSheet(
            "color: #dddddd; font-size: 14px; font-weight: bold; "
            "background: transparent; border: none;"
        )
        toolbar.addWidget(title, 1)

        self._count_label = QtWidgets.QLabel("")
        self._count_label.setStyleSheet(
            "color: #888888; font-size: 11px; "
            "background: transparent; border: none;"
        )
        toolbar.addWidget(self._count_label)

        root.addLayout(toolbar)

        # Scroll area with card list
        scroll = QtWidgets.QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QtWidgets.QFrame.NoFrame)
        scroll.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)
        scroll.setStyleSheet(
            "QScrollArea { background: transparent; border: none; }"
        )

        self._list_widget = QtWidgets.QWidget()
        self._list_layout = QtWidgets.QVBoxLayout(self._list_widget)
        self._list_layout.setContentsMargins(8, 4, 8, 8)
        self._list_layout.setSpacing(6)
        self._list_layout.addStretch()

        scroll.setWidget(self._list_widget)
        root.addWidget(scroll)

        # Empty state
        self._empty_label = QtWidgets.QLabel(
            "No purchased items yet.\nBrowse the BGEN Library to find pickers!"
        )
        self._empty_label.setAlignment(QtCore.Qt.AlignCenter)
        self._empty_label.setWordWrap(True)
        self._empty_label.setStyleSheet(
            "color: #666666; font-size: 12px; "
            "background: transparent; border: none; padding: 40px;"
        )
        self._empty_label.setVisible(False)
        root.addWidget(self._empty_label)

    def load_purchases(self, purchases):
        """Populate the list with purchase data."""
        self._purchases = purchases

        # Clear existing cards
        while self._list_layout.count():
            item = self._list_layout.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()

        if not purchases:
            self._empty_label.setVisible(True)
            self._count_label.setText("")
            return

        self._empty_label.setVisible(False)
        self._count_label.setText(f"{len(purchases)} item{'s' if len(purchases) != 1 else ''}")

        for p in purchases:
            card = _OwnedItemCard(p)
            card.download_requested.connect(self.download_requested.emit)
            self._list_layout.addWidget(card)

        self._list_layout.addStretch()
