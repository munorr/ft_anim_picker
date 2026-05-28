"""
Page Navigation Segment Control
A segment control with icon buttons for navigating between main application pages
"""

from pathlib import Path
from PySide6.QtWidgets import QWidget, QHBoxLayout, QPushButton, QButtonGroup, QSizePolicy
from PySide6.QtGui import QIcon, QPixmap, QPainter, QColor
from PySide6.QtCore import Qt, Signal, QSize, QRectF
from typing import List, Optional

from . import utils as UT 
from .config.settings import PAGE_SEGMENT_CONTROL_SIZE


class _NotificationButton(QPushButton):
    """QPushButton subclass that can draw a small notification dot."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.notification = False
        self.notification_color = "#1D65CA"

    def paintEvent(self, event):
        super().paintEvent(event)
        if self.notification:
            painter = QPainter(self)
            painter.setRenderHint(QPainter.Antialiasing)
            dot_size = min(7, self.height() // 3)
            margin = 2
            x = self.width() - dot_size - margin
            y = self.height() - dot_size - margin
            painter.setBrush(QColor(self.notification_color))
            painter.setPen(Qt.NoPen)
            painter.drawEllipse(QRectF(x, y, dot_size, dot_size))


class PageSegmentControl(QWidget):
    """
    Icon-based segment control for page navigation
    Each segment displays an icon representing a page
    """
    page_changed = Signal(int)  # Emits index of selected page
    
    def __init__(
        self, 
        icon_paths: List[str],
        page_names: List[str],
        parent: Optional[QWidget] = None,
        button_size: int = 24,
        icon_size: int = 18
    ):
        super().__init__(parent)
        self.icon_paths = icon_paths
        self.page_names = page_names
        self.buttons = []
        self.selected_index = 0
        self.icon_size = icon_size
        self.button_size = button_size
        self._setup_ui()
    
    def _setup_ui(self):
        """Create the page segment control UI"""
        # Main horizontal layout
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)  # Tight spacing between icon buttons
        
        # Button group for exclusive selection
        self.button_group = QButtonGroup(self)
        self.button_group.setExclusive(True)
        
        # Create icon buttons for each page
        for i, (icon_path, name) in enumerate(zip(self.icon_paths, self.page_names)):
            btn = _NotificationButton()
            btn.setCheckable(True)
            btn.setCursor(Qt.PointingHandCursor)
            btn.setObjectName("pageSegmentButton")
            btn.setProperty("index", i)
            btn.setToolTip(name)  # Show page name on hover
            
            # Set icon
            if Path(icon_path).exists():
                btn.setIcon(UT.icon_render(icon_path, opacity=0.8, size=self.icon_size))
            
            # Set fixed size for icon buttons
            btn.setFixedSize(self.button_size, self.button_size)
            
            # Connect click handler
            btn.clicked.connect(lambda checked, idx=i: self._on_page_clicked(idx))
            self.button_group.addButton(btn)
            
            self.buttons.append(btn)
            layout.addWidget(btn)
        
        # Set first button as selected by default
        if self.buttons:
            self.buttons[0].setChecked(True)
            self.selected_index = 0
        
        # Apply styling
        self._apply_styles()
    
    def _apply_styles(self):
        """Apply modern dark theme styling for icon buttons"""
        self.setStyleSheet(f"""
            QPushButton#pageSegmentButton {{    
                background: transparent;
                border-radius: {self.button_size/ 2}px;
                padding: 6px;
            }}
            
            QPushButton#pageSegmentButton:hover {{
                background: rgba(255, 255, 255, 0.1);
            }}
            
            QPushButton#pageSegmentButton:checked {{
                background: rgba(255, 255, 255, 0.25);
            }}      
            
            QPushButton#pageSegmentButton:pressed {{
                background: rgba(255, 255, 255, 0.15);
            }}   
        """)
    
    def _on_page_clicked(self, index: int):
        """Handle page selection"""
        self.selected_index = index
        self.page_changed.emit(index)
    
    def set_selected_index(self, index: int):
        """Programmatically select a page"""
        if 0 <= index < len(self.buttons):
            self.buttons[index].setChecked(True)
            self.selected_index = index
    
    def get_selected_index(self) -> int:
        """Get currently selected page index"""
        return self.selected_index
    
    def get_selected_page_name(self) -> str:
        """Get the name of the currently selected page"""
        if 0 <= self.selected_index < len(self.page_names):
            return self.page_names[self.selected_index]
        return ""

    def set_notification(self, index: int, state: bool = True, color: str = "#1D65CA"):
        """Show/hide notification dot on a page button by index."""
        if 0 <= index < len(self.buttons):
            self.buttons[index].notification = state
            self.buttons[index].notification_color = color
            self.buttons[index].update()


class TextSegmentControl(QWidget):
    """
    Text-based segment control with pill-shaped selected indicator.
    Used for sub-page navigation (e.g. My Library / BGEN Library).

    When use_frame=True, buttons are placed inside a styled QFrame container.
    Frame appearance is controlled via frame_bg, frame_radius, frame_border,
    frame_border_color, and frame_padding.
    """
    segment_changed = Signal(int)

    def __init__(
        self,
        labels: List[str],
        parent: Optional[QWidget] = None,
        height: int = 30,
        font_size: int = 11,
        radius: int = 8,
        bg_color: str = "rgba(255, 255, 255, 0.06)",
        selected_color: str = "rgba(255, 255, 255, 0.15)",
        text_color: str = "#999999",
        selected_text_color: str = "#dddddd",
        # Icon options — pass a list of QIcon, QPixmap, icon path strings, or None per button
        icons: Optional[List] = None,
        icon_size: int = 14,
        icon_opacity: float = 0.8,
        # Frame options
        use_frame: bool = False,
        frame_bg: str = "rgba(255, 255, 255, 0.06)",
        frame_radius: int = 8,
        frame_border: int = 0,
        frame_border_color: str = "transparent",
        frame_padding: int = 3,
        # Sizing
        expand: bool = True,
        # Tooltips — optional list of tooltip strings, one per button
        tooltips: Optional[List[str]] = None,
    ):
        super().__init__(parent)
        self.labels = labels
        self.buttons = []
        self.selected_index = 0
        self._height = height
        self._radius = radius
        self._font_size = font_size
        self._bg_color = bg_color
        self._selected_color = selected_color
        self._text_color = text_color
        self._selected_text_color = selected_text_color
        self._icons = icons
        self._icon_size = icon_size
        self._icon_opacity = icon_opacity
        self._use_frame = use_frame
        self._frame_bg = frame_bg
        self._frame_radius = frame_radius
        self._frame_border = frame_border
        self._frame_border_color = frame_border_color
        self._frame_padding = frame_padding
        self._expand = expand
        self._tooltips = tooltips
        self._setup_ui()

    def _setup_ui(self):
        self.setFixedHeight(self._height)

        if self._expand:
            self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        else:
            self.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)

        outer_layout = QHBoxLayout(self)
        outer_layout.setContentsMargins(0, 0, 0, 0)
        outer_layout.setSpacing(0)

        # Determine where to place the buttons
        if self._use_frame:
            self.frame = QWidget(self)
            self.frame.setObjectName("textSegmentFrame")
            if self._expand:
                self.frame.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
            button_layout = QHBoxLayout(self.frame)
            button_layout.setContentsMargins(
                self._frame_padding, self._frame_padding,
                self._frame_padding, self._frame_padding
            )
            button_layout.setSpacing(0)
            outer_layout.addWidget(self.frame)
        else:
            self.frame = None
            button_layout = outer_layout
            button_layout.setContentsMargins(2, 2, 2, 2)

        self.button_group = QButtonGroup(self)
        self.button_group.setExclusive(True)

        for i, label in enumerate(self.labels):
            btn = QPushButton(label)
            btn.setCheckable(True)
            btn.setCursor(Qt.PointingHandCursor)
            btn.setObjectName("textSegmentButton")
            if self._expand:
                btn.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

            # Apply icon if provided (accepts QIcon, QPixmap, or file path str)
            has_icon = False
            if self._icons and i < len(self._icons) and self._icons[i] is not None:
                icon_src = self._icons[i]
                if isinstance(icon_src, QIcon):
                    btn.setIcon(icon_src)
                    has_icon = True
                elif isinstance(icon_src, QPixmap):
                    btn.setIcon(QIcon(icon_src))
                    has_icon = True
                elif isinstance(icon_src, str) and Path(icon_src).exists():
                    btn.setIcon(UT.icon_render(icon_src, opacity=self._icon_opacity, size=self._icon_size))
                    has_icon = True
                if has_icon:
                    btn.setIconSize(QSize(self._icon_size, self._icon_size))
                    btn.setObjectName("textSegmentButtonIcon")

            # Apply tooltip if provided
            if self._tooltips and i < len(self._tooltips) and self._tooltips[i]:
                btn.setToolTip(self._tooltips[i])

            btn.clicked.connect(lambda checked, idx=i: self._on_clicked(idx))
            self.button_group.addButton(btn)
            self.buttons.append(btn)
            button_layout.addWidget(btn)

        if self.buttons:
            self.buttons[0].setChecked(True)

        self._apply_styles()

    def _apply_styles(self):
        radius = self._radius

        # Frame styling (only applied when use_frame=True)
        frame_style = ""
        if self._use_frame:
            frame_style = f"""
            QWidget#textSegmentFrame {{
                background: {self._frame_bg};
                border-radius: {self._frame_radius}px;
                border: {self._frame_border}px solid {self._frame_border_color};
            }}
            """

        # When no frame, apply bg to the widget itself
        container_style = ""
        if not self._use_frame:
            container_style = f"""
            TextSegmentControl {{
                background: {self._bg_color};
                border-radius: {self._radius}px;
            }}
            """

        # Base button style shared by both plain and icon variants
        base_btn = f"""
                background: transparent;
                border: none;
                border-radius: {radius}px;
                color: {self._text_color};
                font-size: {self._font_size}px;
                padding: 4px 12px;
        """

        self.setStyleSheet(f"""
            {container_style}
            {frame_style}
            QPushButton#textSegmentButton {{
                {base_btn}
            }}
            QPushButton#textSegmentButton:hover {{
                color: {self._selected_text_color};
            }}
            QPushButton#textSegmentButton:checked {{
                background: {self._selected_color};
                color: {self._selected_text_color};
            }}
            QPushButton#textSegmentButtonIcon {{
                {base_btn}
                spacing: 6px;
                padding: 2px;
            }}
            QPushButton#textSegmentButtonIcon:hover {{
                color: {self._selected_text_color};
            }}
            QPushButton#textSegmentButtonIcon:checked {{
                background: {self._selected_color};
                color: {self._selected_text_color};
            }}
        """)

    def _on_clicked(self, index: int):
        self.selected_index = index
        self.segment_changed.emit(index)

    def set_selected_index(self, index: int):
        if 0 <= index < len(self.buttons):
            self.buttons[index].setChecked(True)
            self.selected_index = index

    def get_selected_index(self) -> int:
        return self.selected_index

    def set_labels(self, labels: List[str], selected_index: int = 0,
                   icons: Optional[List] = None, tooltips: Optional[List[str]] = None):
        """Rebuild the segment buttons in-place with a new label list.

        Mirrors the construction logic in `_setup_ui` so styling, sizing, and
        signal wiring stay consistent. Icons/tooltips can be passed to
        replace the originals; pass None to keep them unchanged.
        """
        button_layout = self.frame.layout() if self._use_frame else self.layout()

        # Tear down existing buttons
        for btn in self.buttons:
            self.button_group.removeButton(btn)
            button_layout.removeWidget(btn)
            btn.deleteLater()
        self.buttons = []

        # Update internal state
        self.labels = list(labels)
        if icons is not None:
            self._icons = icons
        if tooltips is not None:
            self._tooltips = tooltips

        # Rebuild — same per-button construction as _setup_ui
        for i, label in enumerate(self.labels):
            btn = QPushButton(label)
            btn.setCheckable(True)
            btn.setCursor(Qt.PointingHandCursor)
            btn.setObjectName("textSegmentButton")
            if self._expand:
                btn.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

            has_icon = False
            if self._icons and i < len(self._icons) and self._icons[i] is not None:
                icon_src = self._icons[i]
                if isinstance(icon_src, QIcon):
                    btn.setIcon(icon_src)
                    has_icon = True
                elif isinstance(icon_src, QPixmap):
                    btn.setIcon(QIcon(icon_src))
                    has_icon = True
                elif isinstance(icon_src, str) and Path(icon_src).exists():
                    btn.setIcon(UT.icon_render(icon_src, opacity=self._icon_opacity, size=self._icon_size))
                    has_icon = True
                if has_icon:
                    btn.setIconSize(QSize(self._icon_size, self._icon_size))
                    btn.setObjectName("textSegmentButtonIcon")

            if self._tooltips and i < len(self._tooltips) and self._tooltips[i]:
                btn.setToolTip(self._tooltips[i])

            btn.clicked.connect(lambda checked, idx=i: self._on_clicked(idx))
            self.button_group.addButton(btn)
            self.buttons.append(btn)
            button_layout.addWidget(btn)

        # Restore selection
        if 0 <= selected_index < len(self.buttons):
            self.buttons[selected_index].setChecked(True)
            self.selected_index = selected_index
        elif self.buttons:
            self.buttons[0].setChecked(True)
            self.selected_index = 0
        else:
            self.selected_index = 0

        self._apply_styles()

