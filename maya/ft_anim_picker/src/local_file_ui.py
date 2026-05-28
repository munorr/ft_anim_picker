"""
Library UI – PickerCard widget and LocalFilePageController.

Populates the My Library > Local grid with cards representing .bpicker
files in the central library.
"""

import os
from datetime import datetime
from pathlib import Path

try:
    from PySide6 import QtWidgets, QtCore, QtGui
except ImportError:
    from PySide2 import QtWidgets, QtCore, QtGui

from . import bpicker_format as BPF
from . import custom_button as CB
from .local_file_manager import LocalFileManager
from .config import settings as CFG


# ---------------------------------------------------------------------------
# PickerCard – single card in the library grid
# ---------------------------------------------------------------------------

class PickerCard(QtWidgets.QFrame):
    """Visual card representing a single .bpicker file in the library."""

    # Signals
    clicked = QtCore.Signal(str)          # uuid
    double_clicked = QtCore.Signal(str)   # uuid
    context_menu_requested = QtCore.Signal(str, QtCore.QPoint)  # uuid, global pos

    def __init__(self, picker_info, parent=None, card_size=None):
        """
        Args:
            picker_info: dict from library index with keys:
                uuid, name, filename, author, modified, tab_count,
                preview_available.
            card_size: int pixel size for the card (default CFG.CARD_SIZE).
        """
        super().__init__(parent)
        self._alive = True
        self._uuid = picker_info.get("uuid", "")
        self._info = picker_info
        self._selected = False
        self._preview_pixmap = None

        # Instance-level sizing
        self._card_size = card_size if card_size is not None else CFG.CARD_SIZE
        self._thumb_size = int(self._card_size - self._card_size * 0.1)
        label_height = max(16, int(self._card_size * 0.22))
        font_size = max(10, min(12, int(self._card_size * 0.11)))
        self._max_name_chars = max(6, int(self._card_size * 0.14))

        self.setFixedSize(self._card_size, self._card_size + label_height)
        self.setCursor(QtCore.Qt.PointingHandCursor)
        self._apply_style(False)

        # Layout
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 2)
        layout.setSpacing(2)

        # Thumbnail area
        self._thumb_label = QtWidgets.QLabel()
        self._thumb_label.setFixedSize(self._thumb_size, self._thumb_size)
        self._thumb_label.setAlignment(QtCore.Qt.AlignCenter)
        self._thumb_label.setStyleSheet(
            "background: rgba(50,50,50,0.6); border-radius: 10px; border: none;"
        )
        layout.addWidget(self._thumb_label, alignment=QtCore.Qt.AlignCenter)

        # Name label
        display_name = self._truncate_name(picker_info.get("name", "Untitled"))
        self._name_label = QtWidgets.QLabel(display_name)
        self._name_label.setAlignment(QtCore.Qt.AlignLeft)
        self._name_label.setStyleSheet(
            f"color: #cccccc; font-size: {font_size}px; background: transparent; border: none;"
        )
        layout.addWidget(self._name_label)

        # Load preview if available
        self._load_preview()

        # Software icon overlay (top-right of card)
        self._sw_icon_label = None
        self._setup_sw_icon(picker_info.get("software", ""))

        # Tooltip
        self._tooltip_widget = None
        self._tooltip_timer = QtCore.QTimer(self)
        self._tooltip_timer.setSingleShot(True)
        self._tooltip_timer.setInterval(600)
        self._tooltip_timer.timeout.connect(self._show_tooltip)

    # ---- public ----

    def get_uuid(self):
        return self._uuid

    def resize_card(self, new_size):
        """Resize the card dynamically to *new_size* pixels wide."""
        self._card_size = new_size
        self._thumb_size = int(new_size - new_size * 0.1)
        label_height = max(16, int(new_size * 0.22))
        font_size = max(8, min(12, int(new_size * 0.11)))
        self._max_name_chars = max(6, int(new_size * 0.14))

        self.setFixedSize(new_size, new_size + label_height)
        self._thumb_label.setFixedSize(self._thumb_size, self._thumb_size)
        self._name_label.setStyleSheet(
            f"color: #cccccc; font-size: {font_size}px; background: transparent; border: none;"
        )
        self._name_label.setText(self._truncate_name(self._info.get("name", "Untitled")))
        self._load_preview()

        # Re-apply software icon at new size
        if self._sw_icon_label:
            software = self._info.get("software", "")
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

    def set_selected(self, selected):
        self._selected = selected
        self._apply_style(selected)

    def update_info(self, picker_info):
        self._info = picker_info
        self._name_label.setText(self._truncate_name(picker_info.get("name", "Untitled")))
        self._load_preview()
        self._setup_sw_icon(picker_info.get("software", ""))

    def set_preview(self, pixmap):
        if pixmap and not pixmap.isNull():
            self._preview_pixmap = pixmap
            scaled = pixmap.scaled(
                self._thumb_size, self._thumb_size,
                QtCore.Qt.KeepAspectRatio,
                QtCore.Qt.SmoothTransformation,
            )
            self._thumb_label.setPixmap(self._round_pixmap(scaled))
        else:
            self._set_default_icon()

    def cleanup(self):
        """Clean up tooltip before deletion."""
        self._alive = False
        self._hide_tooltip()

    # ---- events ----

    def mousePressEvent(self, event):
        if event.button() == QtCore.Qt.LeftButton:
            self.clicked.emit(self._uuid)
        super().mousePressEvent(event)

    def mouseDoubleClickEvent(self, event):
        if event.button() == QtCore.Qt.LeftButton:
            self.double_clicked.emit(self._uuid)
        super().mouseDoubleClickEvent(event)

    def contextMenuEvent(self, event):
        self.context_menu_requested.emit(self._uuid, event.globalPos())

    def enterEvent(self, event):
        if not self._selected:
            self.setStyleSheet(
                "PickerCard { background: rgba(255,255,255,0.08); "
                "border: 1px solid rgba(255,255,255,0.12); border-radius: 6px; }"
            )
        self._tooltip_timer.start()
        super().enterEvent(event)

    def leaveEvent(self, event):
        self._apply_style(self._selected)
        self._hide_tooltip()
        super().leaveEvent(event)

    # ---- tooltip ----

    def _show_tooltip(self):
        """Build and display a rich tooltip near the cursor."""
        self._hide_tooltip()

        tooltip = CB.CustomTooltipWidget()

        # Picker name
        name = self._info.get("name", "Untitled")
        tooltip.add_text(f"<b>{name}</b>")
        tooltip.add_separator()

        # Last modified
        modified_raw = self._info.get("modified", "")
        if modified_raw:
            try:
                dt = datetime.fromisoformat(modified_raw)
                modified_str = dt.strftime("%b %d, %Y  %I:%M %p")
            except Exception:
                modified_str = modified_raw
        else:
            modified_str = "Unknown"
        tooltip.add_text(f"<span style='color:#999999;'>Modified:</span>  {modified_str}")

        # Tab count
        tab_count = self._info.get("tab_count", 0)
        tooltip.add_text(f"<span style='color:#999999;'>Tabs:</span>  {tab_count}")

        # File size
        tooltip.add_text(f"<span style='color:#999999;'>Size:</span>  {self._get_file_size_str()}")

        # Author
        author = self._info.get("author", "")
        if author:
            tooltip.add_text(f"<span style='color:#999999;'>Author:</span>  {author}")

        software = self._info.get("software", "")
        if software:
            tooltip.add_text(
                f"<span style='color:#999999;'>Software:</span>  {software.capitalize()}"
            )

        tooltip.finalize()

        # Position near cursor with screen boundary checking
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
        """Hide and clean up the tooltip immediately."""
        self._tooltip_timer.stop()
        if self._tooltip_widget:
            try:
                self._tooltip_widget.close()
                self._tooltip_widget.deleteLater()
            except RuntimeError:
                pass
            self._tooltip_widget = None

    def _get_file_size_str(self):
        """Return human-readable file size string."""
        try:
            picker_path = LocalFileManager.get_picker_path(self._uuid)
            if picker_path and picker_path.exists():
                size_bytes = os.path.getsize(str(picker_path))
                if size_bytes < 1024:
                    return f"{size_bytes} B"
                elif size_bytes < 1024 * 1024:
                    return f"{size_bytes / 1024:.1f} KB"
                else:
                    return f"{size_bytes / (1024 * 1024):.1f} MB"
        except Exception:
            pass
        return "Unknown"

    def _truncate_name(self, name):
        if len(name) > self._max_name_chars:
            return name[:self._max_name_chars - 1] + "\u2026"
        return name

    # ---- internal ----

    def _apply_style(self, selected):
        if selected:
            self.setStyleSheet(
                "PickerCard { background: rgba(29,101,202,0.25); "
                "border: 1px solid rgba(29,101,202,0.6); border-radius: 6px; }"
            )
        else:
            self.setStyleSheet(
                "PickerCard { background: rgba(255,255,255,0); "
                "border: 0px solid transparent; border-radius: 6px; }"
            )

    def _setup_sw_icon(self, software):
        """Create or update the software icon overlay."""
        if self._sw_icon_label:
            self._sw_icon_label.deleteLater()
            self._sw_icon_label = None

        if software not in ("maya", "blender"):
            return

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
                self._position_sw_icon()

    def _position_sw_icon(self):
        """Position the software icon overlay at the top-right of the card."""
        if self._sw_icon_label:
            icon_size = self._sw_icon_label.width()
            self._sw_icon_label.move(self.width() - icon_size - 6, 6)
            self._sw_icon_label.raise_()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._position_sw_icon()

    def showEvent(self, event):
        super().showEvent(event)
        self._position_sw_icon()

    def _load_preview(self):
        """Try to load a preview image from the .bpicker archive."""
        if not self._info.get("preview_available"):
            self._set_default_icon()
            return

        picker_path = LocalFileManager.get_picker_path(self._uuid)
        if not picker_path:
            self._set_default_icon()
            return

        preview_bytes = BPF.BPickerArchive.extract_media(
            str(picker_path), f"{BPF.CACHE_DIR}/preview.png"
        )
        if preview_bytes:
            pixmap = QtGui.QPixmap()
            pixmap.loadFromData(preview_bytes)
            self.set_preview(pixmap)
        else:
            self._set_default_icon()

    def _set_default_icon(self):
        """Show a placeholder icon when no preview is available."""
        name = self._info.get("name", "?")
        initials = name[0].upper() if name else "?"
        ts = self._thumb_size

        pixmap = QtGui.QPixmap(ts, ts)
        pixmap.fill(QtGui.QColor(45, 45, 50))

        painter = QtGui.QPainter(pixmap)
        painter.setRenderHint(QtGui.QPainter.Antialiasing)

        painter.setBrush(QtGui.QColor(55, 60, 70))
        painter.setPen(QtCore.Qt.NoPen)
        painter.drawRoundedRect(0, 0, ts, ts, 4, 4)

        painter.setPen(QtGui.QColor(140, 150, 170))
        font = painter.font()
        font.setPixelSize(int(ts * 0.45))
        font.setBold(True)
        painter.setFont(font)
        painter.drawText(
            QtCore.QRect(0, 0, ts, ts),
            QtCore.Qt.AlignCenter,
            initials,
        )
        painter.end()

        self._thumb_label.setPixmap(self._round_pixmap(pixmap))

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


# ---------------------------------------------------------------------------
# View-mode size presets
# ---------------------------------------------------------------------------

VIEW_SIZES = {
    "small": 64,
    "medium": 84,
    "large": 120,
    "list": 0,  # sentinel — list mode uses full-width rows
}


# ---------------------------------------------------------------------------
# PickerListItem – compact row for list view
# ---------------------------------------------------------------------------

class PickerListItem(QtWidgets.QFrame):
    """Compact horizontal row for list-view mode."""

    clicked = QtCore.Signal(str)
    double_clicked = QtCore.Signal(str)
    context_menu_requested = QtCore.Signal(str, QtCore.QPoint)

    def __init__(self, picker_info, parent=None):
        super().__init__(parent)
        self._alive = True
        self._uuid = picker_info.get("uuid", "")
        self._info = picker_info
        self._selected = False

        self.setFixedHeight(32)
        self.setCursor(QtCore.Qt.PointingHandCursor)
        self._apply_style(False)

        layout = QtWidgets.QHBoxLayout(self)
        layout.setContentsMargins(6, 2, 8, 2)
        layout.setSpacing(8)

        # Small thumbnail
        thumb = QtWidgets.QLabel()
        thumb.setFixedSize(24, 24)
        thumb.setAlignment(QtCore.Qt.AlignCenter)
        thumb.setStyleSheet("background: rgba(50,50,50,0.6); border-radius: 3px; border: none;")

        name = picker_info.get("name", "?")
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
        thumb.setPixmap(pix)

        # Try to load real preview
        if picker_info.get("preview_available"):
            picker_path = LocalFileManager.get_picker_path(self._uuid)
            if picker_path:
                preview_bytes = BPF.BPickerArchive.extract_media(
                    str(picker_path), f"{BPF.CACHE_DIR}/preview.png"
                )
                if preview_bytes:
                    real_pix = QtGui.QPixmap()
                    real_pix.loadFromData(preview_bytes)
                    if not real_pix.isNull():
                        thumb.setPixmap(real_pix.scaled(
                            24, 24, QtCore.Qt.KeepAspectRatio, QtCore.Qt.SmoothTransformation,
                        ))

        layout.addWidget(thumb)

        # Software icon (inline, between thumbnail and name)
        software = picker_info.get("software", "")
        if software in ("maya", "blender"):
            icon_name = "maya_icon.png" if software == "maya" else "blender_icon.png"
            icon_path = Path(__file__).parent / "bgen_picker_icons" / icon_name
            if icon_path.exists():
                sw_pixmap = QtGui.QPixmap(str(icon_path)).scaled(
                    16, 16, QtCore.Qt.KeepAspectRatio, QtCore.Qt.SmoothTransformation,
                )
                if not sw_pixmap.isNull():
                    sw_label = QtWidgets.QLabel()
                    sw_label.setFixedSize(16, 16)
                    sw_label.setPixmap(sw_pixmap)
                    sw_label.setStyleSheet("background: transparent; border: none;")
                    layout.addWidget(sw_label)

        # Name
        name_label = QtWidgets.QLabel(name)
        name_label.setStyleSheet("color: #cccccc; font-size: 11px; background: transparent; border: none;")
        layout.addWidget(name_label, 1)

        # Metadata
        modified_raw = picker_info.get("modified", "")
        if modified_raw:
            try:
                from datetime import datetime
                dt = datetime.fromisoformat(modified_raw)
                date_str = dt.strftime("%b %d, %Y")
            except Exception:
                date_str = ""
        else:
            date_str = ""
        if date_str:
            date_label = QtWidgets.QLabel(date_str)
            date_label.setStyleSheet("color: #777777; font-size: 10px; background: transparent; border: none;")
            layout.addWidget(date_label)

    def get_uuid(self):
        return self._uuid

    def set_selected(self, selected):
        self._selected = selected
        self._apply_style(selected)

    def cleanup(self):
        self._alive = False

    def resize_card(self, new_size):
        pass  # list items ignore card size

    def mousePressEvent(self, event):
        if event.button() == QtCore.Qt.LeftButton:
            self.clicked.emit(self._uuid)
        super().mousePressEvent(event)

    def mouseDoubleClickEvent(self, event):
        if event.button() == QtCore.Qt.LeftButton:
            self.double_clicked.emit(self._uuid)
        super().mouseDoubleClickEvent(event)

    def contextMenuEvent(self, event):
        self.context_menu_requested.emit(self._uuid, event.globalPos())

    def enterEvent(self, event):
        if not self._selected:
            self.setStyleSheet(
                "PickerListItem { background: rgba(255,255,255,0.08); "
                "border: 1px solid rgba(255,255,255,0.12); border-radius: 4px; }"
            )
        super().enterEvent(event)

    def leaveEvent(self, event):
        self._apply_style(self._selected)
        super().leaveEvent(event)

    def _apply_style(self, selected):
        if selected:
            self.setStyleSheet(
                "PickerListItem { background: rgba(29,101,202,0.25); "
                "border: 1px solid rgba(29,101,202,0.6); border-radius: 4px; }"
            )
        else:
            self.setStyleSheet(
                "PickerListItem { background: rgba(255,255,255,0.02); "
                "border: 1px solid transparent; border-radius: 4px; }"
            )


# ---------------------------------------------------------------------------
# LocalFilePageController – manages the My Library > Local grid
# ---------------------------------------------------------------------------

class LocalFilePageController(QtCore.QObject):
    """Bridges LocalFileManager to the My Library grid UI."""

    _instance = None  # Singleton reference for live-preview updates

    # Signal emitted when a picker is selected for opening
    picker_open_requested = QtCore.Signal(str)  # uuid
    # Signal emitted when a single tab import is requested
    tab_import_requested = QtCore.Signal(str, str)  # (uuid, tab_name)

    @classmethod
    def get_instance(cls):
        """Return the active controller, or None."""
        return cls._instance

    def __init__(self, grid_layout, grid_container, scroll_area, parent_window):
        """
        Args:
            grid_layout: QGridLayout for placing PickerCards.
            grid_container: QWidget holding the grid layout.
            scroll_area: QScrollArea wrapping the grid.
            parent_window: The main picker window.
        """
        super().__init__(parent_window)
        LocalFilePageController._instance = self
        self._grid = grid_layout
        self._container = grid_container
        self._scroll = scroll_area
        self._window = parent_window
        self._cards = {}          # uuid -> PickerCard/PickerListItem
        self._selected_uuid = None
        self._sort_mode = "modified"
        self._search_text = ""
        self._card_size = CFG.CARD_SIZE
        self._view_mode = "medium"  # small | medium | large | list
        self._category_filter = "Picker"  # "All" | "Picker" | future types
        self._ordered_keys = []
        self._last_col_count = 0  # track column count to skip no-op relayouts
        self._needs_refresh = False  # deferred refresh when hidden

        # Debounce timer for resize — relayout only, no card recreation
        self._resize_timer = QtCore.QTimer(self)
        self._resize_timer.setSingleShot(True)
        self._resize_timer.setInterval(150)
        self._resize_timer.timeout.connect(self._relayout)

        # Only watch viewport for resize (scroll area and window resize
        # propagate to viewport, so one filter is sufficient)
        self._scroll.viewport().installEventFilter(self)

        # Register for library changes
        LocalFileManager.register_watcher(self._on_library_changed)

    def cleanup(self):
        """Unregister watcher on shutdown."""
        LocalFileManager.unregister_watcher(self._on_library_changed)
        try:
            self._scroll.viewport().removeEventFilter(self)
        except Exception:
            pass

    def eventFilter(self, obj, event):
        if event.type() == QtCore.QEvent.Resize and obj is self._scroll.viewport():
            self._resize_timer.start()
        return False

    def _on_library_changed(self):
        """Called by LocalFileManager when the index changes."""
        self.refresh()

    # ---- sort / search / size ----

    def set_sort_mode(self, mode):
        """Change sorting and refresh the grid."""
        self._sort_mode = mode
        self.refresh()

    def set_search_text(self, text):
        """Update search filter and refresh."""
        self._search_text = text.strip()
        self.refresh()

    def set_view_mode(self, mode):
        """Change view mode and refresh. mode: small|medium|large|list."""
        self._view_mode = mode
        size = VIEW_SIZES.get(mode, VIEW_SIZES["medium"])
        if size > 0:
            self._card_size = size
        self.refresh()

    def set_category_filter(self, category):
        """Change the asset-type category filter and refresh.

        Args:
            category: "All", "Picker", or future asset types.
        """
        if category == self._category_filter:
            return
        self._category_filter = category
        self.refresh()

    def _sort_pickers(self, pickers):
        """Sort picker list based on current sort mode."""
        if self._sort_mode == "modified":
            pickers.sort(key=lambda p: p.get("modified", ""), reverse=True)
        elif self._sort_mode == "created":
            pickers.sort(key=lambda p: p.get("created", ""), reverse=True)
        elif self._sort_mode == "az":
            pickers.sort(key=lambda p: p.get("name", "").lower())
        elif self._sort_mode == "za":
            pickers.sort(key=lambda p: p.get("name", "").lower(), reverse=True)
        return pickers

    def _clear_grid(self):
        """Remove all widgets from the grid layout and any orphaned cards."""
        # Remove widgets managed by the grid layout
        while self._grid.count():
            item = self._grid.takeAt(0)
            widget = item.widget()
            if widget is not None:
                if hasattr(widget, 'cleanup'):
                    widget.cleanup()
                widget.setParent(None)
                widget.deleteLater()
        # Remove any orphaned card children not managed by the grid
        # (e.g. cards created from a background thread that weren't
        # properly added to the layout)
        for child in self._container.children():
            if isinstance(child, (PickerCard, PickerListItem)):
                if hasattr(child, 'cleanup'):
                    child.cleanup()
                child.setParent(None)
                child.deleteLater()

    # ---- refresh / relayout ----

    def catch_up_if_needed(self):
        """Call after the library page becomes visible to apply deferred refresh."""
        if self._needs_refresh:
            self.refresh()

    def refresh(self):
        """Rebuild the grid from the library index (data change)."""
        # Skip rebuild when not visible — prevents crash from background
        # reindex triggering widget teardown on a hidden/zero-size viewport.
        if not self._scroll.isVisible():
            self._needs_refresh = True
            return
        self._needs_refresh = False

        self._clear_grid()
        self._cards.clear()
        self._selected_uuid = None
        self._last_col_count = 0

        index = LocalFileManager.get_index()
        pickers = list(index.get("pickers", []))

        # Local tab: always show only local files (no Downloads subfolder items)
        pickers = [p for p in pickers if not p.get("subfolder")]

        # Category filter by asset type (future: check asset_type field)
        # For now all local files are pickers — filtering is a no-op
        # if self._category_filter != "All":
        #     pickers = [p for p in pickers if p.get("asset_type") == self._category_filter]

        if self._search_text:
            query = self._search_text.lower()
            pickers = [p for p in pickers if query in p.get("name", "").lower()]

        pickers = self._sort_pickers(pickers)

        # Store ordered keys for relayout
        self._ordered_keys = [p.get("uuid", "") for p in pickers]

        if self._view_mode == "list":
            for i, info in enumerate(pickers):
                item = PickerListItem(info, parent=self._container)
                item.clicked.connect(self._on_card_clicked)
                item.double_clicked.connect(self._on_card_double_clicked)
                item.context_menu_requested.connect(self._on_card_context_menu)
                self._grid.addWidget(item, i, 0)
                self._cards[info.get("uuid", "")] = item
        else:
            spacing = self._grid.spacing()
            margins = self._grid.contentsMargins()
            viewport_w = self._scroll.viewport().width() - margins.left() - margins.right()
            card_slot = self._card_size + spacing
            if viewport_w <= 0:
                # Viewport not sized yet — retry after event loop processes geometry
                QtCore.QTimer.singleShot(50, self.refresh)
                return
            max_cols = max(1, int(viewport_w // card_slot))
            dynamic_size = max(self._card_size, int(
                (viewport_w - spacing * (max_cols - 1)) / max_cols
            )) if max_cols > 0 else self._card_size
            self._last_col_count = max_cols

            for i, info in enumerate(pickers):
                card = PickerCard(info, parent=self._container, card_size=dynamic_size)
                card.clicked.connect(self._on_card_clicked)
                card.double_clicked.connect(self._on_card_double_clicked)
                card.context_menu_requested.connect(self._on_card_context_menu)
                self._grid.addWidget(card, i // max_cols, i % max_cols)
                self._cards[info.get("uuid", "")] = card

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

        # Skip if column count hasn't changed
        if max_cols == self._last_col_count:
            return
        self._last_col_count = max_cols

        dynamic_size = max(self._card_size, int(
            (viewport_w - spacing * (max_cols - 1)) / max_cols
        )) if max_cols > 0 else self._card_size

        # Remove all from grid without deleting, then re-add at new positions
        while self._grid.count():
            self._grid.takeAt(0)

        for i, key in enumerate(self._ordered_keys):
            card = self._cards.get(key)
            if card:
                card.resize_card(dynamic_size)
                self._grid.addWidget(card, i // max_cols, i % max_cols)

    # ---- card actions ----

    def _on_card_clicked(self, uuid):
        # Deselect previous
        if self._selected_uuid and self._selected_uuid in self._cards:
            self._cards[self._selected_uuid].set_selected(False)
        self._selected_uuid = uuid
        if uuid in self._cards:
            self._cards[uuid].set_selected(True)

    def _on_card_double_clicked(self, uuid):
        self._on_card_clicked(uuid)
        self.picker_open_requested.emit(uuid)

    def _on_card_context_menu(self, uuid, global_pos):
        self._on_card_clicked(uuid)

        menu = QtWidgets.QMenu(self._window)
        menu.setStyleSheet("""
            QMenu {
                background-color: #2a2a2a; color: #dddddd;
                border: 1px solid #3a3a3a; border-radius: 4px; padding: 4px;
            }
            QMenu::item { padding: 5px 20px; border-radius: 3px; }
            QMenu::item:selected { background-color: rgba(29,101,202,0.4); }
        """)

        open_action = menu.addAction("Open")
        menu.addSeparator()
        rename_action = menu.addAction("Rename")

        # Software tag submenu
        sw_menu = menu.addMenu("Software")
        sw_none = sw_menu.addAction("None")
        sw_blender = sw_menu.addAction("Blender")
        sw_maya = sw_menu.addAction("Maya")
        current_sw = (LocalFileManager.get_picker_info(uuid) or {}).get("software", "")
        sw_none.setCheckable(True)
        sw_blender.setCheckable(True)
        sw_maya.setCheckable(True)
        sw_none.setChecked(current_sw == "")
        sw_blender.setChecked(current_sw == "blender")
        sw_maya.setChecked(current_sw == "maya")

        # Thumbnail actions
        menu.addSeparator()
        info = LocalFileManager.get_picker_info(uuid) or {}
        has_custom = info.get("custom_preview", False)
        set_thumb_action = menu.addAction("Set Custom Thumbnail...")
        clear_thumb_action = None
        if has_custom:
            clear_thumb_action = menu.addAction("Clear Custom Thumbnail")

        export_action = menu.addAction("Export...")

        # Import Tab submenu (only when a session is active)
        tab_actions = {}
        from . import data_management as DM
        has_session = DM.PickerDataManager.get_active_session() is not None
        if has_session:
            from . import picker_io as PIO
            picker_path = LocalFileManager.get_picker_path(uuid)
            if picker_path:
                try:
                    tab_names = PIO.get_tab_names_from_bpicker(str(picker_path))
                    if tab_names:
                        import_tab_menu = menu.addMenu("Import Tab")
                        for tn in tab_names:
                            act = import_tab_menu.addAction(tn)
                            tab_actions[act] = tn
                except Exception:
                    pass

        menu.addSeparator()
        delete_action = menu.addAction("Delete")

        action = menu.exec_(global_pos)

        if action == open_action:
            self.picker_open_requested.emit(uuid)
        elif action == rename_action:
            self._rename_picker(uuid)
        elif action == sw_none:
            self._set_picker_software(uuid, "")
        elif action == sw_blender:
            self._set_picker_software(uuid, "blender")
        elif action == sw_maya:
            self._set_picker_software(uuid, "maya")
        elif action == set_thumb_action:
            self._set_custom_thumbnail(uuid)
        elif clear_thumb_action and action == clear_thumb_action:
            self._clear_custom_thumbnail(uuid)
        elif action == export_action:
            self._export_picker(uuid)
        elif tab_actions and action in tab_actions:
            self.tab_import_requested.emit(uuid, tab_actions[action])
        elif action == delete_action:
            self._delete_picker(uuid)

    # ---- CRUD operations ----

    def _set_picker_software(self, uuid, software):
        """Set the software tag for a picker and refresh the grid."""
        LocalFileManager.set_picker_software(uuid, software)
        self.refresh()

    def _set_custom_thumbnail(self, uuid):
        """Let the user pick an image file and set it as the card thumbnail."""
        image_path, _ = QtWidgets.QFileDialog.getOpenFileName(
            self._window,
            "Select Thumbnail Image",
            "",
            "Images (*.png *.jpg *.jpeg *.bmp *.tga *.tiff)",
        )
        if not image_path:
            return

        success = LocalFileManager.set_custom_preview(uuid, image_path)
        if success:
            # Sync flag to active session if this picker is currently open
            from . import data_management as DM
            session = DM.PickerDataManager.get_active_session()
            if session and session.uuid == uuid:
                session.metadata["custom_preview"] = True

            # Update OS file icon
            picker_path = LocalFileManager.get_picker_path(uuid)
            if picker_path:
                try:
                    from .thumbnail_handler import set_file_icon
                    set_file_icon(str(picker_path))
                except Exception:
                    pass

            self.refresh()

    def _clear_custom_thumbnail(self, uuid):
        """Revert to auto-generated canvas thumbnail."""
        success = LocalFileManager.clear_custom_preview(uuid)
        if success:
            # Sync flag to active session if this picker is currently open
            from . import data_management as DM
            session = DM.PickerDataManager.get_active_session()
            if session and session.uuid == uuid:
                session.metadata["custom_preview"] = False

            self.refresh()

    def _rename_picker(self, uuid):
        info = LocalFileManager.get_picker_info(uuid)
        if not info:
            return

        from . import custom_dialog as CD
        dialog = CD.CustomDialog(self._window, title="Rename Picker", size=(280, 90))
        name_input = QtWidgets.QLineEdit(info.get("name", ""))
        name_input.setStyleSheet(
            "background: rgba(50,50,50,0.8); color: #dddddd; "
            "border: 1px solid #3a3a3a; border-radius: 4px; padding: 4px;"
        )
        dialog.add_widget(name_input)

        btn_layout = QtWidgets.QHBoxLayout()
        ok_btn = CB.CustomButton("Rename", color="#00749a")
        cancel_btn = CB.CustomButton("Cancel", color="#444444")
        btn_layout.addWidget(ok_btn)
        btn_layout.addWidget(cancel_btn)
        dialog.add_layout(btn_layout)

        ok_btn.clicked.connect(dialog.accept)
        cancel_btn.clicked.connect(dialog.reject)

        if dialog.exec_() == QtWidgets.QDialog.Accepted:
            new_name = name_input.text().strip()
            if new_name and new_name != info.get("name"):
                LocalFileManager.rename_picker(uuid, new_name)
                self.refresh()

    def _export_picker(self, uuid):
        picker_path = LocalFileManager.get_picker_path(uuid)
        if not picker_path:
            return

        from . import picker_io as PIO
        dest, _ = QtWidgets.QFileDialog.getSaveFileName(
            self._window,
            "Export Picker",
            str(picker_path.name),
            "BPicker Files (*.bpicker)",
        )
        if dest:
            import shutil
            shutil.copy2(str(picker_path), dest)

    def _delete_picker(self, uuid):
        info = LocalFileManager.get_picker_info(uuid)
        if not info:
            return

        from . import custom_dialog as CD
        dialog = CD.CustomDialog(
            self._window, title="Delete Picker", size=(280, 100)
        )
        msg = QtWidgets.QLabel(
            f"Delete <b><font color='#ff5500'>{info.get('name', 'this picker')}</font></b>?"
            f"\n\nA backup will be kept in the Backups folder."
        )
        msg.setWordWrap(True)
        dialog.add_widget(msg)

        btn_layout = QtWidgets.QHBoxLayout()
        delete_btn = CB.CustomButton("Delete", color="#aa2200")
        cancel_btn = CB.CustomButton("Cancel", color="#444444")
        btn_layout.addWidget(delete_btn)
        btn_layout.addWidget(cancel_btn)
        dialog.add_layout(btn_layout)

        delete_btn.clicked.connect(dialog.accept)
        cancel_btn.clicked.connect(dialog.reject)

        if dialog.exec_() == QtWidgets.QDialog.Accepted:
            LocalFileManager.remove_from_library(uuid)
            self.refresh()
