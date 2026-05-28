"""
Settings Page — Sidebar navigation with Account, Preferences, Updates, More Info sections.
"""

import os
import sys
import json
import webbrowser
import urllib.request
from pathlib import Path

try:
    from PySide6 import QtCore, QtWidgets, QtGui
    from PySide6.QtCore import Qt, Signal, QTimer, QRectF
    from PySide6.QtWidgets import (
        QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
        QLineEdit, QFrame, QStackedWidget, QScrollArea, QButtonGroup,
        QComboBox, QProgressBar, QSizePolicy,
    )
    from PySide6.QtGui import QPainter, QColor, QIcon
except ImportError:
    from PySide2 import QtCore, QtWidgets, QtGui
    from PySide2.QtCore import Qt, Signal, QTimer, QRectF
    from PySide2.QtWidgets import (
        QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
        QLineEdit, QFrame, QStackedWidget, QScrollArea, QButtonGroup,
        QComboBox, QProgressBar, QSizePolicy,
    )
    from PySide2.QtGui import QPainter, QColor, QIcon

from . import utils as UT
from .custom_segment_control import TextSegmentControl
from .config.settings import (
    GITHUB_URL, GITHUB_ISSUES_URL, AUTHOR_NAME,
    WEBSITE_URL, DISCORD_URL, INSTAGRAM_URL, YOUTUBE_URL,
)

# ---------------------------------------------------------------------------
# Color tokens
# ---------------------------------------------------------------------------
_BG_SIDEBAR = "rgba(20, 20, 20, 0.6)"
_TEXT_PRIMARY = "#e0e0e0"
_TEXT_SECONDARY = "#999999"
_TEXT_MUTED = "#666666"
_ACCENT_BLUE = "rgba(29, 101, 202, 0.25)"
_ACCENT_BLUE_SOLID = "#1D65CA"
_CARD_BG = "rgba(0, 0, 0, 0.1)"
_CARD_BORDER = "rgba(255, 255, 255, 0.06)"
_INPUT_BG = "rgba(50, 50, 50, 0.8)"
_INPUT_BORDER = "#3a3a3a"

_SCROLL_STYLE = """
    QScrollArea { background: transparent; border: none; }
    QScrollBar:vertical { border: none; background: transparent; width: 6px; }
    QScrollBar::handle:vertical { background: rgba(100,100,100,0.4); border-radius: 3px; min-height: 20px; }
    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0px; }
    QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical { background: transparent; }
"""

_CARD_STYLE = (
    f"#settings_card {{ background: {_CARD_BG}; border: 1px solid {_CARD_BORDER}; border-radius: 8px; }}"
)


# ===================================================================
# Helpers
# ===================================================================

def _section_title(text: str) -> QLabel:
    lbl = QLabel(text)
    lbl.setStyleSheet(
        f"color: {_TEXT_PRIMARY}; font-size: 14px; font-weight: bold; "
        "background: transparent; border: none;"
    )
    return lbl


def _section_scroll() -> QScrollArea:
    sa = QScrollArea()
    sa.setWidgetResizable(True)
    sa.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
    sa.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
    sa.setStyleSheet(_SCROLL_STYLE)
    return sa


def _card_frame() -> QFrame:
    frame = QFrame()
    frame.setObjectName("settings_card")
    frame.setStyleSheet(_CARD_STYLE)
    return frame


def _label(text: str, size: int = 11, color: str = _TEXT_SECONDARY, bold: bool = False) -> QLabel:
    lbl = QLabel(text)
    weight = "font-weight: bold;" if bold else ""
    lbl.setStyleSheet(
        f"color: {color}; font-size: {size}px; {weight} "
        "background: transparent; border: none;"
    )
    return lbl


class _ElidingLabel(QLabel):
    """QLabel that truncates text with ellipsis when space is tight."""

    def __init__(self, text: str = "", color: str = _TEXT_PRIMARY, parent=None):
        super().__init__(text, parent)
        self._full_text = text
        self._color = QColor(color)

    def setText(self, text: str):
        self._full_text = text
        super().setText(text)
        self.update()

    def setFullText(self, text: str):
        """Alias for setText — stores full text for elision."""
        self.setText(text)

    def setColor(self, color: str):
        self._color = QColor(color)
        self.update()

    def minimumSizeHint(self):
        return QtCore.QSize(0, super().minimumSizeHint().height())

    def sizeHint(self):
        return QtCore.QSize(0, super().sizeHint().height())

    def paintEvent(self, event):
        try:
            from PySide6.QtGui import QPainter, QFontMetrics
        except ImportError:
            from PySide2.QtGui import QPainter, QFontMetrics
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        fm = QFontMetrics(self.font())
        # Account for stylesheet padding
        cm = self.contentsMargins()
        avail = self.width() - cm.left() - cm.right()
        text_rect = self.rect().adjusted(cm.left(), cm.top(), -cm.right(), -cm.bottom())
        elided = fm.elidedText(self._full_text, Qt.ElideLeft, avail)
        painter.setPen(self._color)
        painter.setFont(self.font())
        painter.drawText(text_rect, self.alignment() | Qt.AlignVCenter, elided)
        painter.end()


def _link_button(text: str, url: str, icon_name: str = "", enabled: bool = True) -> QPushButton:
    btn = QPushButton(text)
    btn.setFixedHeight(32)
    btn.setCursor(Qt.PointingHandCursor if enabled else Qt.ArrowCursor)
    if icon_name:
        icon_path = Path(__file__).parent / "bgen_picker_icons" / icon_name
        if icon_path.exists():
            btn.setIcon(QIcon(str(icon_path)))
            btn.setIconSize(QtCore.QSize(16, 16))
    color = "#6ba4e8" if enabled else _TEXT_MUTED
    btn.setStyleSheet(
        "QPushButton { background: transparent; color: %s; "
        "border: none; border-radius: 4px; font-size: 11px; text-align: left; padding: 0 12px; }"
        "QPushButton:hover { background: rgba(255,255,255,0.06); }"
        "QPushButton:disabled { color: %s; background: transparent; }" % (color, _TEXT_MUTED)
    )
    if enabled and url:
        btn.clicked.connect(lambda: webbrowser.open(url))
    else:
        btn.setEnabled(False)
    return btn


def _divider() -> QFrame:
    """Thin horizontal divider line."""
    line = QFrame()
    line.setFixedHeight(1)
    line.setStyleSheet("background: rgba(255,255,255,0.06); border: none;")
    return line


# ===================================================================
# Sidebar
# ===================================================================

class SettingsSidebar(QFrame):
    """Vertical navigation sidebar with icon + label buttons."""

    section_changed = Signal(int)

    _ITEMS = [
        ("Preferences", "preference_icon.png"),
        ("Updates", "update.png"),
        ("More Info", "manual.png"),
    ]

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedWidth(110)
        self.setStyleSheet(
            f"SettingsSidebar {{ background: {_BG_SIDEBAR}; "
            f"border-right: 1px solid {_CARD_BORDER}; border-radius: 4px; }}"
        )

        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 10, 6, 10)
        layout.setSpacing(2)

        self.buttons = []
        self.button_group = QButtonGroup(self)
        self.button_group.setExclusive(True)

        for i, (label, icon_name) in enumerate(self._ITEMS):
            btn = QPushButton(f"  {label}")
            btn.setCheckable(True)
            btn.setCursor(Qt.PointingHandCursor)
            btn.setFixedHeight(30)
            btn.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

            icon = UT.get_icon(icon_name, size=14, opacity=0.7)
            if icon:
                btn.setIcon(QIcon(icon))
                btn.setIconSize(QtCore.QSize(14, 14))

            btn.clicked.connect(lambda checked=False, idx=i: self._on_clicked(idx))
            self.button_group.addButton(btn)
            self.buttons.append(btn)
            layout.addWidget(btn)

        layout.addStretch()

        if self.buttons:
            self.buttons[0].setChecked(True)

        self._apply_styles()

    def _apply_styles(self):
        self.setStyleSheet(
            f"SettingsSidebar {{ background: {_BG_SIDEBAR}; "
            f"border: 1px solid {_CARD_BORDER}; border-radius: 8px; }}"
            "QPushButton { background: transparent; color: #999999; "
            "border: none; border-radius: 6px; font-size: 11px; text-align: left; padding: 4px 8px; }"
            f"QPushButton:hover {{ background: rgba(255,255,255,0.08); color: {_TEXT_PRIMARY}; }}"
            f"QPushButton:checked {{ background: {_ACCENT_BLUE}; color: {_TEXT_PRIMARY}; }}"
        )

    def _on_clicked(self, index: int):
        self.section_changed.emit(index)

    def set_selected_index(self, index: int):
        if 0 <= index < len(self.buttons):
            self.buttons[index].setChecked(True)


# ===================================================================
# Avatar Widget
# ===================================================================

class _AvatarFetchWorker(QtCore.QThread):
    """Download an avatar image from a URL on a background thread."""
    finished = Signal(QtGui.QPixmap)

    def __init__(self, url: str):
        super().__init__()
        self._url = url

    def run(self):
        try:
            import urllib.request
            from .supabase_client import _SSL_CTX
            req = urllib.request.Request(self._url, headers={"User-Agent": "BGEN-Picker/1.0"})
            with urllib.request.urlopen(req, timeout=8, context=_SSL_CTX) as resp:
                data = resp.read()
            pixmap = QtGui.QPixmap()
            pixmap.loadFromData(data)
            if not pixmap.isNull():
                self.finished.emit(pixmap)
        except Exception:
            pass  # Keep showing initials fallback


class _AvatarWidget(QWidget):
    """Circular avatar with Google profile pic or initials fallback."""

    def __init__(self, size: int = 48, parent=None):
        super().__init__(parent)
        self._size = size
        self._pixmap = None       # Fetched avatar image
        self._initials = "?"
        self._bg_color = QColor(80, 80, 120)
        self._worker = None
        self.setFixedSize(size, size)

    def set_user(self, email: str = "", display_name: str = "", avatar_url: str = ""):
        """Configure avatar from user data."""
        # Compute initials
        name = display_name or email
        if name:
            parts = name.strip().split()
            if len(parts) >= 2:
                self._initials = (parts[0][0] + parts[-1][0]).upper()
            else:
                self._initials = name[0].upper()
        else:
            self._initials = "?"

        # Derive stable color from name
        h = hash(email or display_name or "?")
        hue = abs(h) % 360
        self._bg_color = QColor.fromHsv(hue, 120, 140)

        # Fetch avatar image if URL provided
        if avatar_url:
            self._fetch_avatar(avatar_url)

        self.update()

    def _fetch_avatar(self, url: str):
        if self._worker and self._worker.isRunning():
            return
        self._worker = _AvatarFetchWorker(url)
        self._worker.finished.connect(self._on_avatar_loaded)
        self._worker.start()

    def _on_avatar_loaded(self, pixmap: QtGui.QPixmap):
        # Scale and store
        self._pixmap = pixmap.scaled(
            self._size, self._size,
            Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation
        )
        self._worker = None
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        r = self._size

        if self._pixmap and not self._pixmap.isNull():
            # Clip to circle and draw avatar
            path = QtGui.QPainterPath()
            path.addEllipse(0, 0, r, r)
            painter.setClipPath(path)
            # Center-crop the image
            pw, ph = self._pixmap.width(), self._pixmap.height()
            sx = (pw - r) // 2
            sy = (ph - r) // 2
            painter.drawPixmap(0, 0, self._pixmap, sx, sy, r, r)
        else:
            # Initials fallback — colored circle + white text
            painter.setBrush(self._bg_color)
            painter.setPen(Qt.NoPen)
            painter.drawEllipse(0, 0, r, r)

            painter.setPen(QColor(255, 255, 255, 230))
            font = painter.font()
            font.setPixelSize(int(r * 0.38))
            font.setBold(True)
            painter.setFont(font)
            painter.drawText(QtCore.QRect(0, 0, r, r), Qt.AlignCenter, self._initials)

        painter.end()


# ===================================================================
# Account Section
# ===================================================================

_STATE_SIGNED_OUT = 0
_STATE_EMAIL_ENTRY = 1
_STATE_OTP_ENTRY = 2
_STATE_SIGNED_IN = 3

_LINK_STYLE = (
    f"QPushButton {{ background: transparent; border: none; color: {_TEXT_SECONDARY};font-size: 11px; padding: 2px 0; text-decoration: none; }}"
    f"QPushButton:hover {{ color: {_TEXT_PRIMARY}; text-decoration: underline; }}"
)

_ACTION_BTN_STYLE = (
    f"QPushButton {{ background: {_ACCENT_BLUE_SOLID}; color: white; padding: 6px 16px; border: none; border-radius: 6px; font-size: 12px; font-weight: 500; }}"
    f"QPushButton:hover {{ background: #2570d4; }}"
    "QPushButton:disabled { background: rgba(29, 101, 202, 0.4); color: rgba(255,255,255,0.5); }"
)

_SIGN_OUT_BTN_STYLE = (
    f"QPushButton {{ background: rgba(255,255,255,0.06); color: #bbbbbb; padding: 6px 16px; border: none; border-radius: 6px; font-size: 11px; }}"
    "border: 1px solid rgba(255,255,255,0.08); border-radius: 4px; font-size: 11px; }"
    "QPushButton:hover { background: rgba(255,255,255,0.12); }"
)

_INPUT_STYLE_ACCOUNT = (
    f"background: {_INPUT_BG}; color: {_TEXT_PRIMARY}; "
    f"border: 1px solid {_INPUT_BORDER}; border-radius: 4px; "
    "padding: 6px; font-size: 11px;"
)


class ActiveDevicesWidget(QWidget):
    """Displays active device sessions with per-device sign-out."""

    refresh_requested = Signal()
    sign_out_device_requested = Signal(str)  # session_id

    def __init__(self, current_session_id: str = None, parent=None):
        super().__init__(parent)
        self._current_session_id = current_session_id
        self.setStyleSheet("background: transparent; border: none;")
        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._layout.setSpacing(6)

        # Header row
        header_row = QHBoxLayout()
        header_row.addWidget(_label("Active Devices", size=11, color=_TEXT_SECONDARY, bold=True))
        refresh_btn = QPushButton("Refresh")
        refresh_btn.setCursor(Qt.PointingHandCursor)
        refresh_btn.setStyleSheet(_LINK_STYLE)
        refresh_btn.clicked.connect(self.refresh_requested.emit)
        header_row.addStretch()
        header_row.addWidget(refresh_btn)
        self._layout.addLayout(header_row)

        # Device list container
        self._devices_layout = QVBoxLayout()
        self._devices_layout.setSpacing(2)
        self._layout.addLayout(self._devices_layout)

        # Initial loading state
        self._devices_layout.addWidget(
            _label("Loading...", size=10, color=_TEXT_MUTED)
        )

    def set_current_session_id(self, session_id: str):
        self._current_session_id = session_id

    def set_sessions(self, sessions: list):
        """Populate the device list."""
        self._clear_devices()
        if not sessions:
            self._devices_layout.addWidget(
                _label("No active sessions found.", size=11, color=_TEXT_MUTED)
            )
            return
        for session in sessions:
            self._add_device_row(session)

    def show_error(self, message: str):
        self._clear_devices()
        self._devices_layout.addWidget(
            _label(f"Error: {message}", size=11, color="#e05555")
        )

    def _clear_devices(self):
        while self._devices_layout.count():
            item = self._devices_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

    def _add_device_row(self, session: dict):
        session_id = session.get("session_id", "")
        device_info = session.get("device_info", "Unknown device")
        last_active = session.get("last_active_at", "")
        is_current = (session_id == self._current_session_id)

        row = QHBoxLayout()
        row.setSpacing(6)

        # Info column
        info_col = QVBoxLayout()
        info_col.setSpacing(1)

        name_text = device_info
        if is_current:
            name_text += "  (this device)"
        name_color = "#8bc34a" if is_current else _TEXT_PRIMARY
        name_lbl = _ElidingLabel(name_text, color=name_color)
        name_lbl.setStyleSheet(
            f"font-size: 10px; {'font-weight: bold;' if is_current else ''} "
            "background: transparent; border: none;"
        )
        name_lbl.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        name_lbl.setMinimumWidth(0)
        info_col.addWidget(name_lbl)

        time_text = "Active now" if is_current else self._format_last_active(last_active)
        info_col.addWidget(_label(time_text, size=9, color=_TEXT_MUTED))

        row.addLayout(info_col, 1)

        # Sign-out button (not for current device)
        if not is_current:
            sign_out_btn = QPushButton("Sign Out")
            sign_out_btn.setFixedSize(54, 20)
            sign_out_btn.setCursor(Qt.PointingHandCursor)
            sign_out_btn.setStyleSheet(
                "QPushButton { background: rgba(255,80,80,0.12); color: #e05555; "
                "border: none; border-radius: 3px; font-size: 9px; }"
                "QPushButton:hover { background: rgba(255,80,80,0.22); }"
            )
            sign_out_btn.clicked.connect(
                lambda checked, sid=session_id: self.sign_out_device_requested.emit(sid)
            )
            row.addWidget(sign_out_btn)

        container = QWidget()
        container.setLayout(row)
        container.setStyleSheet(
            "background: rgba(255,255,255,0.02); border-radius: 3px; padding: 3px 4px;"
        )
        self._devices_layout.addWidget(container)

    @staticmethod
    def _format_last_active(iso_timestamp: str) -> str:
        if not iso_timestamp:
            return "Unknown"
        try:
            import datetime
            dt = datetime.datetime.fromisoformat(iso_timestamp.replace("Z", "+00:00"))
            now = datetime.datetime.now(datetime.timezone.utc)
            delta = now - dt
            secs = delta.total_seconds()
            if secs < 60:
                return "Active just now"
            elif secs < 3600:
                mins = int(secs / 60)
                return f"Active {mins} min{'s' if mins != 1 else ''} ago"
            elif secs < 86400:
                hours = int(secs / 3600)
                return f"Active {hours} hour{'s' if hours != 1 else ''} ago"
            else:
                days = int(secs / 86400)
                return f"Active {days} day{'s' if days != 1 else ''} ago"
        except Exception:
            return iso_timestamp


class SavedCardsWidget(QWidget):
    """Displays saved payment methods with per-card remove button."""

    refresh_requested = Signal()
    remove_card_requested = Signal(str)  # payment_method_id

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet("background: transparent; border: none;")
        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._layout.setSpacing(6)

        # Header row
        header_row = QHBoxLayout()
        header_row.addWidget(_label("Payment Methods", size=11, color=_TEXT_SECONDARY, bold=True))
        refresh_btn = QPushButton("Refresh")
        refresh_btn.setCursor(Qt.PointingHandCursor)
        refresh_btn.setStyleSheet(_LINK_STYLE)
        refresh_btn.clicked.connect(self.refresh_requested.emit)
        header_row.addStretch()
        header_row.addWidget(refresh_btn)
        self._layout.addLayout(header_row)

        # Cards list container
        self._cards_layout = QVBoxLayout()
        self._cards_layout.setSpacing(2)
        self._layout.addLayout(self._cards_layout)

        # Initial state
        self._cards_layout.addWidget(
            _label("Loading...", size=10, color=_TEXT_MUTED)
        )

    def set_cards(self, cards: list):
        """Populate the payment methods list."""
        self._clear_cards()
        if not cards:
            self._cards_layout.addWidget(
                _label("No saved cards.", size=11, color=_TEXT_MUTED)
            )
            return
        for card in cards:
            self._add_card_row(card)

    def show_error(self, message: str):
        self._clear_cards()
        self._cards_layout.addWidget(
            _label(f"Error: {message}", size=11, color="#e05555")
        )

    def _clear_cards(self):
        while self._cards_layout.count():
            item = self._cards_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

    def _add_card_row(self, card: dict):
        pm_id = card.get("id", "")
        brand = card.get("brand", "card").capitalize()
        last4 = card.get("last4", "????")
        exp_month = card.get("exp_month", 0)
        exp_year = card.get("exp_year", 0)

        row = QHBoxLayout()
        row.setSpacing(6)

        # Card info
        info_col = QVBoxLayout()
        info_col.setSpacing(1)

        card_text = f"{brand}  ****{last4}"
        name_lbl = _label(card_text, size=11, color=_TEXT_PRIMARY)
        info_col.addWidget(name_lbl)

        exp_text = f"Expires {exp_month:02d}/{str(exp_year)[-2:]}" if exp_month and exp_year else ""
        if exp_text:
            exp_lbl = _label(exp_text, size=10, color=_TEXT_MUTED)
            info_col.addWidget(exp_lbl)

        row.addLayout(info_col)
        row.addStretch()

        # Remove button
        remove_btn = QPushButton("Remove")
        remove_btn.setFixedHeight(22)
        remove_btn.setCursor(Qt.PointingHandCursor)
        remove_btn.setStyleSheet(
            "QPushButton { background: transparent; border: none; "
            "color: #e05555; font-size: 10px; padding: 2px 6px; }"
            "QPushButton:hover { color: #ff6b6b; text-decoration: underline; }"
        )
        remove_btn.clicked.connect(lambda checked=False, mid=pm_id: self.remove_card_requested.emit(mid))
        row.addWidget(remove_btn)

        row_widget = QWidget()
        row_widget.setStyleSheet("background: transparent; border: none;")
        row_widget.setLayout(row)
        self._cards_layout.addWidget(row_widget)


class AccountSection(QWidget):
    """Account section with 4-state email OTP authentication flow."""

    sign_in_requested = Signal()
    sign_out_requested = Signal()
    sign_out_all_requested = Signal()
    google_sign_in_requested = Signal()
    send_otp_requested = Signal(str)
    verify_otp_requested = Signal(str, str)
    refresh_devices_requested = Signal()
    sign_out_device_requested = Signal(str)  # session_id
    owned_items_requested = Signal()         # navigate to owned items page
    refresh_cards_requested = Signal()
    remove_card_requested = Signal(str)     # payment_method_id

    def __init__(self, parent=None):
        super().__init__(parent)
        self._state = _STATE_SIGNED_OUT
        self._user_email = None
        self._user_display_name = ""
        self._user_avatar_url = ""
        self._pending_email = ""
        self._error_label = None
        self._action_btn = None
        self._loading = False
        self._current_session_id = None
        self._devices_widget = None
        self._cards_widget = None
        self._avatar_widget = None
        self._build_ui()

    def _build_ui(self):
        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(16, 16, 16, 16)
        self._layout.setSpacing(12)
        self._rebuild()

    def _clear_layout(self):
        while self._layout.count():
            item = self._layout.takeAt(0)
            w = item.widget()
            if w:
                w.hide()
                w.deleteLater()
            sub = item.layout()
            if sub:
                while sub.count():
                    si = sub.takeAt(0)
                    if si.widget():
                        si.widget().hide()
                        si.widget().deleteLater()

    def _rebuild(self):
        self._clear_layout()
        self._error_label = None
        self._action_btn = None
        self._layout.addWidget(_section_title("Account"))

        card = _card_frame()
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(12, 16, 12, 16)
        card_layout.setSpacing(8)

        if self._state == _STATE_SIGNED_IN:
            self._build_signed_in(card_layout)
        elif self._state == _STATE_EMAIL_ENTRY:
            self._build_email_entry(card_layout)
        elif self._state == _STATE_OTP_ENTRY:
            self._build_otp_entry(card_layout)
        else:
            self._build_signed_out(card_layout)

        self._layout.addWidget(card)
        self._layout.addStretch()

    # -- State 0: Signed-out splash ----------------------------------------

    def _build_signed_out(self, layout):
        icons_dir = Path(__file__).parent / "bgen_picker_icons"
        logo_path = icons_dir / "bgen-picker-icon-02.png"
        if logo_path.exists():
            icon_lbl = QLabel()
            icon_lbl.setPixmap(
                QtGui.QPixmap(str(logo_path)).scaled(
                    36, 36, Qt.KeepAspectRatio, Qt.SmoothTransformation
                )
            )
            icon_lbl.setAlignment(Qt.AlignCenter)
            icon_lbl.setStyleSheet("background: transparent; border: none;")
            layout.addWidget(icon_lbl)

        # Contextual prompt (shown when redirected from library)
        self._sign_in_prompt = _label("", size=11, color=_ACCENT_BLUE_SOLID, bold=True)
        self._sign_in_prompt.setAlignment(Qt.AlignCenter)
        self._sign_in_prompt.setWordWrap(True)
        self._sign_in_prompt.hide()
        layout.addWidget(self._sign_in_prompt)

        heading = _label("Sign in to BGEN", size=13, color=_TEXT_PRIMARY, bold=True)
        heading.setAlignment(Qt.AlignCenter)
        heading.setWordWrap(True)
        layout.addWidget(heading)

        subtitle = _label(
            "Sync your pickers and access cloud features.",
            size=11, color=_TEXT_SECONDARY,
        )
        subtitle.setAlignment(Qt.AlignCenter)
        subtitle.setWordWrap(True)
        layout.addWidget(subtitle)

        layout.addSpacing(4)

        _google_icon_path = str(Path(__file__).parent / "bgen_picker_icons" / "google_logo.png")
        google_btn = QPushButton(QIcon(_google_icon_path), "  Sign in with Google")
        google_btn.setIconSize(QtCore.QSize(14, 14))
        google_btn.setFixedHeight(30)
        google_btn.setFixedWidth(160)
        google_btn.setCursor(Qt.PointingHandCursor)
        google_btn.setStyleSheet(
            "QPushButton { background: rgba(255,255,255,0.08); color: #e0e0e0; "
            "padding: 6px 16px; border: 1px solid rgba(255,255,255,0.12); "
            "border-radius: 15px; font-size: 11px; }"
            "QPushButton:hover { background: rgba(255,255,255,0.14); }"
        )
        google_btn.clicked.connect(self.google_sign_in_requested.emit)
        layout.addWidget(google_btn, alignment=Qt.AlignCenter)

        or_lbl = _label("or", size=10, color=_TEXT_MUTED)
        or_lbl.setAlignment(Qt.AlignCenter)
        layout.addWidget(or_lbl)

        sign_in_btn = QPushButton("Sign in with Email")
        sign_in_btn.setFixedHeight(30)
        sign_in_btn.setFixedWidth(160)
        sign_in_btn.setCursor(Qt.PointingHandCursor)
        sign_in_btn.setStyleSheet(
            "QPushButton { background: transparent; color: #e0e0e0; "
            "padding: 6px 16px; border: 1px solid rgba(255,255,255,0.12); "
            "border-radius: 15px; font-size: 11px; }"
            "QPushButton:hover { background: rgba(255,255,255,0.08); }"
        )
        sign_in_btn.clicked.connect(self._go_to_email_entry)
        layout.addWidget(sign_in_btn, alignment=Qt.AlignCenter)

    # -- State 1: Email entry ----------------------------------------------

    def _build_email_entry(self, layout):
        heading = _label("Enter your email", size=13, color=_TEXT_PRIMARY, bold=True)
        heading.setAlignment(Qt.AlignCenter)
        heading.setWordWrap(True)
        layout.addWidget(heading)

        subtitle = _label(
            "We'll send a 6-digit verification code.",
            size=11, color=_TEXT_SECONDARY,
        )
        subtitle.setAlignment(Qt.AlignCenter)
        subtitle.setWordWrap(True)
        layout.addWidget(subtitle)

        layout.addSpacing(4)

        self._email_input = QLineEdit()
        self._email_input.setPlaceholderText("you@example.com")
        self._email_input.setFixedHeight(28)
        self._email_input.setStyleSheet(_INPUT_STYLE_ACCOUNT)
        if self._pending_email:
            self._email_input.setText(self._pending_email)
        layout.addWidget(self._email_input)

        # Error label (hidden by default)
        self._error_label = _label("", size=11, color="#e05555")
        self._error_label.setAlignment(Qt.AlignCenter)
        self._error_label.setWordWrap(True)
        self._error_label.hide()
        layout.addWidget(self._error_label)

        self._action_btn = QPushButton("Send Code")
        self._action_btn.setFixedHeight(30)
        self._action_btn.setCursor(Qt.PointingHandCursor)
        self._action_btn.setStyleSheet(_ACTION_BTN_STYLE)
        self._action_btn.clicked.connect(self._on_send_code)
        layout.addWidget(self._action_btn)

        back_btn = QPushButton("Back")
        back_btn.setCursor(Qt.PointingHandCursor)
        back_btn.setStyleSheet(_LINK_STYLE)
        back_btn.clicked.connect(self._go_to_signed_out)
        layout.addWidget(back_btn, alignment=Qt.AlignCenter)

    # -- State 2: OTP code entry -------------------------------------------

    def _build_otp_entry(self, layout):
        heading = _label("Enter verification code", size=13, color=_TEXT_PRIMARY, bold=True)
        heading.setAlignment(Qt.AlignCenter)
        heading.setWordWrap(True)
        layout.addWidget(heading)

        subtitle = _label(
            f"Code sent to {self._pending_email}",
            size=11, color=_TEXT_MUTED,
        )
        subtitle.setAlignment(Qt.AlignCenter)
        subtitle.setWordWrap(True)
        layout.addWidget(subtitle)

        layout.addSpacing(4)

        self._code_input = QLineEdit()
        self._code_input.setPlaceholderText("000000")
        self._code_input.setMaxLength(6)
        self._code_input.setFixedHeight(28)
        self._code_input.setMaximumWidth(160)
        self._code_input.setAlignment(Qt.AlignCenter)
        self._code_input.setStyleSheet(
            _INPUT_STYLE_ACCOUNT + " font-size: 14px; letter-spacing: 6px;"
        )
        layout.addWidget(self._code_input, alignment=Qt.AlignCenter)

        # Error label (hidden by default)
        self._error_label = _label("", size=11, color="#e05555")
        self._error_label.setAlignment(Qt.AlignCenter)
        self._error_label.setWordWrap(True)
        self._error_label.hide()
        layout.addWidget(self._error_label)

        self._action_btn = QPushButton("Verify")
        self._action_btn.setFixedHeight(30)
        self._action_btn.setMaximumWidth(200)
        self._action_btn.setCursor(Qt.PointingHandCursor)
        self._action_btn.setStyleSheet(_ACTION_BTN_STYLE)
        self._action_btn.clicked.connect(self._on_verify)
        layout.addWidget(self._action_btn, alignment=Qt.AlignCenter)

        # Resend / Back row
        links_row = QHBoxLayout()
        links_row.setSpacing(12)
        links_row.setContentsMargins(0, 0, 0, 0)

        resend_btn = QPushButton("Resend Code")
        resend_btn.setCursor(Qt.PointingHandCursor)
        resend_btn.setStyleSheet(_LINK_STYLE)
        resend_btn.clicked.connect(self._on_resend)
        links_row.addStretch()
        links_row.addWidget(resend_btn)

        sep = _label("|", size=11, color=_TEXT_MUTED)
        links_row.addWidget(sep)

        back_btn = QPushButton("Back")
        back_btn.setCursor(Qt.PointingHandCursor)
        back_btn.setStyleSheet(_LINK_STYLE)
        back_btn.clicked.connect(self._go_to_email_entry)
        links_row.addWidget(back_btn)
        links_row.addStretch()

        layout.addLayout(links_row)

    # -- State 3: Signed in ------------------------------------------------

    def _build_signed_in(self, layout):
        # -- Profile header: avatar + name/email ---
        profile_row = QHBoxLayout()
        profile_row.setSpacing(10)

        self._avatar_widget = _AvatarWidget(size=48)
        self._avatar_widget.set_user(
            email=self._user_email or "",
            display_name=self._user_display_name,
            avatar_url=self._user_avatar_url,
        )
        profile_row.addWidget(self._avatar_widget)

        info_col = QVBoxLayout()
        info_col.setSpacing(2)
        display = self._user_display_name or "BGEN User"
        name_lbl = _ElidingLabel(display, color=_TEXT_PRIMARY)
        name_lbl.setStyleSheet("font-size: 13px; font-weight: bold; background: transparent; border: none;")
        name_lbl.setMinimumWidth(0)
        email_lbl = _ElidingLabel(self._user_email or "", color=_TEXT_SECONDARY)
        email_lbl.setStyleSheet("font-size: 11px; background: transparent; border: none;")
        email_lbl.setMinimumWidth(0)
        info_col.addWidget(name_lbl)
        info_col.addWidget(email_lbl)
        profile_row.addLayout(info_col, 1)

        layout.addLayout(profile_row)

        # -- Divider ---
        layout.addSpacing(4)
        layout.addWidget(_divider())
        layout.addSpacing(4)

        # -- Active Devices (inline, no nested card) ---
        self._devices_widget = ActiveDevicesWidget(
            current_session_id=self._current_session_id
        )
        self._devices_widget.refresh_requested.connect(self.refresh_devices_requested.emit)
        self._devices_widget.sign_out_device_requested.connect(self.sign_out_device_requested.emit)
        layout.addWidget(self._devices_widget)

        # -- Divider ---
        layout.addSpacing(4)
        layout.addWidget(_divider())
        layout.addSpacing(4)

        # -- Owned Items row ---
        owned_row = QHBoxLayout()
        owned_row.setSpacing(2)
        owned_row.setContentsMargins(4, 4, 4, 4)
        owned_row.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        _icons_dir = Path(__file__).parent / "bgen_picker_icons"
        owned_icon = QLabel()
        _star_pix = QtGui.QPixmap(str(_icons_dir / "star-white-icon.png"))
        if not _star_pix.isNull():
            owned_icon.setPixmap(_star_pix.scaled(
                12, 12, Qt.KeepAspectRatio, Qt.SmoothTransformation
            ))
        owned_icon.setStyleSheet("background: transparent; border: none;")

        owned_lbl = QLabel("Owned Items")
        owned_lbl.setStyleSheet(
            f"color: {_TEXT_PRIMARY}; font-size: 12px; "
            "background: transparent; border: none;"
        )

        self._owned_count_lbl = QLabel("")
        self._owned_count_lbl.setStyleSheet(
            "color: #888888; font-size: 11px; "
            "background: transparent; border: none; padding: 0 4px;"
        )

        chevron = QLabel()
        _arrow_pix = QtGui.QPixmap(str(_icons_dir / "arrow_right_icon.png"))
        if not _arrow_pix.isNull():
            chevron.setPixmap(_arrow_pix.scaled(
                12, 12, Qt.KeepAspectRatio, Qt.SmoothTransformation
            ))
        chevron.setStyleSheet("background: transparent; border: none;")

        owned_wrapper = QWidget()
        owned_wrapper.setMinimumWidth(0)
        owned_wrapper.setLayout(owned_row)
        owned_wrapper.setCursor(Qt.PointingHandCursor)
        owned_wrapper.setStyleSheet(
            "QWidget { background: rgba(255,255,255,0.04); "
            "border: 1px solid rgba(255,255,255,0.06); "
            "border-radius: 6px; padding: 2px 4px; }"
            "QWidget:hover { background: rgba(255,255,255,0.08); "
            "border-color: rgba(255,255,255,0.12); }"
        )
        owned_wrapper.mousePressEvent = lambda e: self.owned_items_requested.emit()

        owned_row.addWidget(owned_icon)
        owned_row.addWidget(owned_lbl)
        owned_row.addWidget(self._owned_count_lbl)
        owned_row.addStretch()
        owned_row.addWidget(chevron)

        layout.addWidget(owned_wrapper)

        layout.addSpacing(4)
        layout.addWidget(_divider())
        layout.addSpacing(4)

        # -- Saved payment methods ---
        self._cards_widget = SavedCardsWidget()
        self._cards_widget.refresh_requested.connect(self.refresh_cards_requested.emit)
        self._cards_widget.remove_card_requested.connect(self.remove_card_requested.emit)
        layout.addWidget(self._cards_widget)

        layout.addSpacing(4)
        layout.addWidget(_divider())
        layout.addSpacing(4)

        # -- Sign-out zone ---
        sign_out_btn = QPushButton("Sign Out")
        sign_out_btn.setFixedHeight(26)
        sign_out_btn.setMaximumWidth(200)
        sign_out_btn.setCursor(Qt.PointingHandCursor)
        sign_out_btn.setStyleSheet(_SIGN_OUT_BTN_STYLE)
        sign_out_btn.clicked.connect(self.sign_out_requested.emit)
        layout.addWidget(sign_out_btn, alignment=Qt.AlignCenter)

        sign_out_all_btn = QPushButton("Sign out all devices")
        sign_out_all_btn.setCursor(Qt.PointingHandCursor)
        sign_out_all_btn.setStyleSheet(_LINK_STYLE)
        sign_out_all_btn.clicked.connect(self._confirm_sign_out_all)
        layout.addWidget(sign_out_all_btn, alignment=Qt.AlignCenter)

    # -- Navigation helpers ------------------------------------------------

    def _go_to_signed_out(self):
        self._state = _STATE_SIGNED_OUT
        self._pending_email = ""
        self._loading = False
        self._rebuild()

    def _go_to_email_entry(self):
        self._state = _STATE_EMAIL_ENTRY
        self._loading = False
        self._rebuild()

    # -- Action handlers ---------------------------------------------------

    def _on_send_code(self):
        email = self._email_input.text().strip()
        if not email:
            self.show_error("Please enter your email address.")
            return
        self._pending_email = email
        self._loading = True
        self._action_btn.setEnabled(False)
        self._action_btn.setText("Sending...")
        if self._error_label:
            self._error_label.hide()
        self.send_otp_requested.emit(email)

    def _on_verify(self):
        code = self._code_input.text().strip()
        if not code:
            self.show_error("Please enter the verification code.")
            return
        self._loading = True
        self._action_btn.setEnabled(False)
        self._action_btn.setText("Verifying...")
        if self._error_label:
            self._error_label.hide()
        self.verify_otp_requested.emit(self._pending_email, code)

    def _on_resend(self):
        if self._error_label:
            self._error_label.hide()
        self.send_otp_requested.emit(self._pending_email)

    def _confirm_sign_out_all(self):
        from . import custom_dialog as CD
        dialog = CD.CustomDialog(
            self, title="Sign Out All Devices", size=(280, 100),
        )
        msg = QLabel("This will sign you out on all devices.\nContinue?")
        msg.setWordWrap(True)
        msg.setAlignment(Qt.AlignCenter)
        dialog.add_widget(msg)
        dialog.add_button_box()
        # PySide2/PySide6 compat: exec_() vs exec()
        result = dialog.exec_() if hasattr(dialog, 'exec_') else dialog.exec()
        if result == dialog.accepted:
            self.sign_out_all_requested.emit()

    # -- Public API --------------------------------------------------------

    def show_otp_entry(self):
        """Transition to OTP code entry (called when OTP sent successfully)."""
        self._state = _STATE_OTP_ENTRY
        self._loading = False
        self._rebuild()

    def show_error(self, message: str):
        """Show inline error message and re-enable action button."""
        self._loading = False
        if self._error_label:
            self._error_label.setText(message)
            self._error_label.show()
        if self._action_btn:
            self._action_btn.setEnabled(True)
            if self._state == _STATE_EMAIL_ENTRY:
                self._action_btn.setText("Send Code")
            elif self._state == _STATE_OTP_ENTRY:
                self._action_btn.setText("Verify")

    def set_signed_in(self, email: str, display_name: str = "", avatar_url: str = ""):
        """Transition to signed-in state."""
        self._state = _STATE_SIGNED_IN
        self._user_email = email
        self._user_display_name = display_name
        self._user_avatar_url = avatar_url
        self._pending_email = ""
        self._loading = False
        self._rebuild()

    def set_owned_count(self, count: int):
        """Update the owned items count badge."""
        if hasattr(self, "_owned_count_lbl") and self._owned_count_lbl:
            self._owned_count_lbl.setText(f"{count}" if count else "")

    def set_saved_cards(self, cards: list):
        """Update the saved payment methods list."""
        if self._cards_widget:
            self._cards_widget.set_cards(cards)

    def show_cards_error(self, message: str):
        """Show an error in the saved cards widget."""
        if self._cards_widget:
            self._cards_widget.show_error(message)

    def show_sign_in_prompt(self, message: str):
        """Show a contextual prompt on the sign-in page."""
        if hasattr(self, '_sign_in_prompt') and self._sign_in_prompt:
            self._sign_in_prompt.setText(message)
            self._sign_in_prompt.show()

    def set_signed_out(self):
        """Transition to signed-out splash."""
        self._state = _STATE_SIGNED_OUT
        self._user_email = None
        self._user_display_name = ""
        self._user_avatar_url = ""
        self._pending_email = ""
        self._loading = False
        self._current_session_id = None
        self._rebuild()

    def set_current_session_id(self, session_id: str):
        """Store the current device's session_id for the active devices list."""
        self._current_session_id = session_id
        if self._devices_widget:
            self._devices_widget.set_current_session_id(session_id)

    def update_devices(self, sessions: list):
        """Populate the active devices list with session data."""
        if self._devices_widget:
            self._devices_widget.set_sessions(sessions)

    def show_devices_error(self, message: str):
        """Show an error in the active devices list."""
        if self._devices_widget:
            self._devices_widget.show_error(message)


# ===================================================================
# Preferences Section
# ===================================================================

class PreferencesSection(QWidget):
    """Library path, downloads path, and general preferences."""

    def __init__(self, browse_callback, open_folder_callback,
                 browse_downloads_callback=None, open_downloads_callback=None,
                 parent=None):
        super().__init__(parent)
        self._browse_callback = browse_callback
        self._open_folder_callback = open_folder_callback
        self._browse_downloads_callback = browse_downloads_callback or (lambda: None)
        self._open_downloads_callback = open_downloads_callback or (lambda: None)
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        layout.addWidget(_section_title("Preferences"))

        _path_input_style = (
            f"background: {_INPUT_BG}; color: {_TEXT_PRIMARY}; "
            f"border: 1px solid {_INPUT_BORDER}; border-radius: 4px; "
            "padding: 4px; font-size: 11px;"
        )
        _browse_btn_style = (
            "QPushButton { background: rgba(255,255,255,0.08); color: #dddddd; "
            f"border: 1px solid {_INPUT_BORDER}; border-radius: 4px; }} "
            "QPushButton:hover { background: rgba(255,255,255,0.15); }"
        )
        _open_btn_style = (
            "QPushButton { background: rgba(255,255,255,0.06); color: #bbbbbb; "
            "border: 1px solid rgba(255,255,255,0.08); border-radius: 4px; font-size: 11px; }"
            "QPushButton:hover { background: rgba(255,255,255,0.12); }"
        )

        # -- Picker Library card --
        card = _card_frame()
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(12, 12, 12, 12)
        card_layout.setSpacing(8)

        card_layout.addWidget(_label("Picker Library", size=12, color="#bbbbbb", bold=True))
        _lib_desc = _label(
            "Where your .bpicker files are stored and managed",
            size=10, color=_TEXT_MUTED,
        )
        _lib_desc.setWordWrap(True)
        card_layout.addWidget(_lib_desc)

        path_row = QHBoxLayout()
        path_row.setSpacing(4)
        self.lib_path_label = _ElidingLabel()
        self.lib_path_label.setFixedHeight(26)
        self.lib_path_label.setStyleSheet(_path_input_style)
        self.lib_path_label.setToolTip("")

        browse_btn = QPushButton("...")
        browse_btn.setFixedSize(28, 26)
        browse_btn.setCursor(Qt.PointingHandCursor)
        browse_btn.setStyleSheet(_browse_btn_style)
        browse_btn.clicked.connect(self._browse_callback)

        path_row.addWidget(self.lib_path_label, 1)
        path_row.addWidget(browse_btn)
        card_layout.addLayout(path_row)

        open_btn = QPushButton("Open Picker Library Folder")
        open_btn.setFixedHeight(26)
        open_btn.setMaximumWidth(200)
        open_btn.setCursor(Qt.PointingHandCursor)
        open_btn.setStyleSheet(_open_btn_style)
        open_btn.clicked.connect(self._open_folder_callback)
        card_layout.addWidget(open_btn)

        layout.addWidget(card)

        # -- Asset Downloads card --
        dl_card = _card_frame()
        dl_card_layout = QVBoxLayout(dl_card)
        dl_card_layout.setContentsMargins(12, 12, 12, 12)
        dl_card_layout.setSpacing(8)

        dl_card_layout.addWidget(_label("Asset Downloads", size=12, color="#bbbbbb", bold=True))
        _dl_desc = _label(
            "Where non-picker files (rigs, models, etc.) are saved after purchase",
            size=10, color=_TEXT_MUTED,
        )
        _dl_desc.setWordWrap(True)
        dl_card_layout.addWidget(_dl_desc)

        dl_path_row = QHBoxLayout()
        dl_path_row.setSpacing(4)
        self.dl_path_label = _ElidingLabel()
        self.dl_path_label.setFixedHeight(26)
        self.dl_path_label.setStyleSheet(_path_input_style)
        self.dl_path_label.setToolTip("")

        dl_browse_btn = QPushButton("...")
        dl_browse_btn.setFixedSize(28, 26)
        dl_browse_btn.setCursor(Qt.PointingHandCursor)
        dl_browse_btn.setStyleSheet(_browse_btn_style)
        dl_browse_btn.clicked.connect(self._browse_downloads_callback)

        dl_path_row.addWidget(self.dl_path_label, 1)
        dl_path_row.addWidget(dl_browse_btn)
        dl_card_layout.addLayout(dl_path_row)

        dl_open_btn = QPushButton("Open Asset Downloads Folder")
        dl_open_btn.setFixedHeight(26)
        dl_open_btn.setMaximumWidth(220)
        dl_open_btn.setCursor(Qt.PointingHandCursor)
        dl_open_btn.setStyleSheet(_open_btn_style)
        dl_open_btn.clicked.connect(self._open_downloads_callback)
        dl_card_layout.addWidget(dl_open_btn)

        layout.addWidget(dl_card)

        # -- Window Behavior card --
        wb_card = _card_frame()
        wb_layout = QVBoxLayout(wb_card)
        wb_layout.setContentsMargins(12, 12, 12, 12)
        wb_layout.setSpacing(8)

        wb_layout.addWidget(_label("Window Behavior", size=12, color="#bbbbbb", bold=True))

        # Always on Top row
        aot_row = QHBoxLayout()
        aot_row.setSpacing(8)
        self._aot_label = _ElidingLabel("Always on Top", color=_TEXT_PRIMARY)
        self._aot_label.setStyleSheet("font-size: 11px; background: transparent; border: none;")
        self._aot_segment = TextSegmentControl(
            ["Off", "On"],
            height=24,
            font_size=11,
            radius=6,
            frame_radius=6,
            use_frame=True,
            frame_bg="rgba(255, 255, 255, 0.06)",
            selected_color="#1D65CA",
            expand=False,
        )
        self._aot_segment.segment_changed.connect(self._on_always_on_top_changed)

        aot_row.addWidget(self._aot_label,1)
        aot_row.addStretch()
        aot_row.addWidget(self._aot_segment)
        wb_layout.addLayout(aot_row)

        _aot_hint = _label(
            "When off, the picker hides when you switch to another application.",
            size=10, color=_TEXT_MUTED,
        )
        _aot_hint.setWordWrap(True)
        wb_layout.addWidget(_aot_hint)

        layout.addWidget(wb_card)

        # -- Auto-Save card --
        as_card = _card_frame()
        as_layout = QVBoxLayout(as_card)
        as_layout.setContentsMargins(12, 12, 12, 12)
        as_layout.setSpacing(8)

        as_layout.addWidget(_label("Auto-Save", size=12, color="#bbbbbb", bold=True))

        # Autosave toggle row
        as_row = QHBoxLayout()
        as_row.setSpacing(8)
        self._autosave_label = _ElidingLabel("Auto-save to library", color=_TEXT_PRIMARY)
        self._autosave_label.setStyleSheet("font-size: 11px; background: transparent; border: none;")
        self._autosave_segment = TextSegmentControl(
            ["Off", "On"],
            height=24,
            font_size=11,
            radius=6,
            frame_radius=6,
            use_frame=True,
            frame_bg="rgba(255, 255, 255, 0.06)",
            selected_color="#1D65CA",
            expand=False,
        )
        self._autosave_segment.segment_changed.connect(self._on_autosave_changed)

        as_row.addWidget(self._autosave_label,1)
        as_row.addStretch()
        as_row.addWidget(self._autosave_segment)
        as_layout.addLayout(as_row)

        _as_hint = _label(
            "Automatically saves changes to the .bpicker file in your library. "
            "When off, use manual save (Ctrl+S) to persist changes.",
            size=10, color=_TEXT_MUTED,
        )
        _as_hint.setWordWrap(True)
        as_layout.addWidget(_as_hint)

        layout.addWidget(as_card)

        # -- File Icon Registration card --
        fi_card = _card_frame()
        fi_layout = QVBoxLayout(fi_card)
        fi_layout.setContentsMargins(12, 12, 12, 12)
        fi_layout.setSpacing(8)

        # Title row with icon
        fi_title_row = QHBoxLayout()
        fi_title_row.setSpacing(8)
        from .thumbnail_handler import _file_icon_path
        fi_icon_lbl = QLabel()
        fi_icon_lbl.setFixedSize(28, 28)
        fi_icon_lbl.setStyleSheet("background: transparent; border: none;")
        icon_path = _file_icon_path()
        if os.path.isfile(icon_path):
            fi_icon_lbl.setPixmap(QIcon(icon_path).pixmap(28, 28))
        fi_title_row.addWidget(fi_icon_lbl)
        fi_title_row.addWidget(_label("File Icon Registration", size=12, color="#bbbbbb", bold=True))
        fi_title_row.addStretch()
        fi_layout.addLayout(fi_title_row)

        from .thumbnail_handler import is_installed
        self._fi_installed = is_installed()

        if self._fi_installed:
            self._fi_status = _label(
                "Registered — .bpicker files should display with the BGEN Picker icon.",
                size=11, color="#7db305",
            )
        else:
            self._fi_status = _label(
                "Not registered — .bpicker files display with a generic icon.",
                size=11, color="#cc8844",
            )
        self._fi_status.setWordWrap(True)
        fi_layout.addWidget(self._fi_status)

        _fi_hint = _label(
            "Registers .bpicker as a file type with your OS so files display "
            "with a branded icon in Finder / Explorer.",
            size=10, color=_TEXT_MUTED,
        )
        _fi_hint.setWordWrap(True)
        fi_layout.addWidget(_fi_hint)

        self._fi_install_btn = QPushButton(
            "Re-register File Icon" if self._fi_installed else "Register File Icon"
        )
        self._fi_install_btn.setFixedHeight(28)
        self._fi_install_btn.setMaximumWidth(180)
        self._fi_install_btn.setCursor(Qt.PointingHandCursor)
        self._fi_install_btn.setStyleSheet(
            "QPushButton { background: #1d65ca; color: #dddddd; "
            "border: none; border-radius: 4px; font-size: 11px; }"
            "QPushButton:hover { background: rgba(29,101,202,0.8); }"
        )
        self._fi_install_btn.clicked.connect(self._on_install_file_icon)
        fi_layout.addWidget(self._fi_install_btn)

        if self._fi_installed:
            self._fi_uninstall_btn = QPushButton("Unregister")
            self._fi_uninstall_btn.setFixedHeight(28)
            self._fi_uninstall_btn.setMaximumWidth(180)
            self._fi_uninstall_btn.setCursor(Qt.PointingHandCursor)
            self._fi_uninstall_btn.setStyleSheet(
                "QPushButton { background: rgba(255,255,255,0.06); color: #bbbbbb; "
                "border: 1px solid rgba(255,255,255,0.08); border-radius: 4px; font-size: 11px; }"
                "QPushButton:hover { background: rgba(255,255,255,0.12); }"
            )
            self._fi_uninstall_btn.clicked.connect(self._on_uninstall_file_icon)
            fi_layout.addWidget(self._fi_uninstall_btn)

        layout.addWidget(fi_card)

        # -- WebEngine / Library card --
        we_card = _card_frame()
        we_layout = QVBoxLayout(we_card)
        we_layout.setContentsMargins(12, 12, 12, 12)
        we_layout.setSpacing(8)

        we_layout.addWidget(_label("Library (WebEngine)", size=12, color="#bbbbbb", bold=True))

        try:
            from . import webengine_deps
            has_webengine = webengine_deps.check_webengine_available()
        except (ImportError, Exception):
            has_webengine = False
            webengine_deps = None

        if has_webengine:
            status_lbl = _label(
                "Embedded library is available.",
                size=11, color="#7db305",
            )
            status_lbl.setWordWrap(True)
            we_layout.addWidget(status_lbl)
        else:
            status_lbl = _label(
                "WebEngine is not installed. The library requires it.",
                size=11, color="#cc8844",
            )
            status_lbl.setWordWrap(True)
            we_layout.addWidget(status_lbl)

            self._we_install_btn = QPushButton("Install WebEngine")
            self._we_install_btn.setFixedHeight(28)
            self._we_install_btn.setMaximumWidth(180)
            self._we_install_btn.setCursor(Qt.PointingHandCursor)
            self._we_install_btn.setStyleSheet(
                "QPushButton { background: #1d65ca; color: #dddddd; "
                "border: none; border-radius: 4px; font-size: 11px; }"
                "QPushButton:hover { background: rgba(29,101,202,0.8); }"
            )
            self._we_install_btn.clicked.connect(self._on_install_webengine)
            we_layout.addWidget(self._we_install_btn)

            self._we_status_lbl = _label("", size=10, color=_TEXT_MUTED)
            self._we_status_lbl.setWordWrap(True)
            self._we_status_lbl.hide()
            we_layout.addWidget(self._we_status_lbl)

            manual_cmd = webengine_deps.get_manual_install_command() if webengine_deps else "pip install PySide6-WebEngine"
            cmd_lbl = _label(
                f"Manual: {manual_cmd}",
                size=10, color=_TEXT_MUTED,
            )
            cmd_lbl.setWordWrap(True)
            cmd_lbl.setTextInteractionFlags(Qt.TextSelectableByMouse)
            we_layout.addWidget(cmd_lbl)

        layout.addWidget(we_card)
        layout.addStretch()

        # Load current paths and preferences
        from .local_file_manager import LocalFileManager
        self._set_path_label(self.lib_path_label, str(LocalFileManager.get_library_path()))
        self._set_path_label(self.dl_path_label, str(LocalFileManager.get_downloads_path()))

        # Load always-on-top state (index 1 = On, index 0 = Off)
        self._aot_segment.set_selected_index(1 if LocalFileManager.get_always_on_top() else 0)

        # Load autosave state
        self._autosave_segment.set_selected_index(1 if LocalFileManager.get_autosave_enabled() else 0)

    def _on_always_on_top_changed(self, index):
        """Persist the always-on-top preference when segment changes."""
        checked = index == 1
        from .local_file_manager import LocalFileManager
        LocalFileManager.set_always_on_top(checked)

    def _on_autosave_changed(self, index):
        """Persist the auto-save preference when segment changes."""
        enabled = index == 1
        from .local_file_manager import LocalFileManager
        LocalFileManager.set_autosave_enabled(enabled)

    def _on_install_file_icon(self):
        """Run the .bpicker file-type registration with the OS."""
        self._fi_install_btn.setEnabled(False)
        self._fi_install_btn.setText("Registering...")

        from .thumbnail_handler import ensure_installed, is_installed, _mark_installed
        import os

        # Remove the flag so ensure_installed will actually run
        from .thumbnail_handler import _FLAG_FILE
        if os.path.exists(_FLAG_FILE):
            os.remove(_FLAG_FILE)

        # Run synchronously so the user sees the result
        import platform
        system = platform.system()
        success = False
        error_msg = None
        try:
            if system == "Darwin":
                from .thumbnail_handler import _file_icon_path
                from .thumbnail_handler import macos_handler
                success = macos_handler.install(file_icon_png=_file_icon_path())
            elif system == "Windows":
                from .thumbnail_handler import _file_icon_path
                from .thumbnail_handler import windows_handler
                success = windows_handler.install(file_icon_png=_file_icon_path())
            else:
                error_msg = "File icon registration is not supported on Linux."
        except Exception as e:
            error_msg = str(e)

        if success:
            _mark_installed()
            self._fi_status.setText(
                "Registered — .bpicker files should display with the BGEN Picker icon."
            )
            self._fi_status.setStyleSheet(
                "color: #7db305; font-size: 11px; background: transparent; border: none;"
            )
            self._fi_install_btn.setText("Re-register File Icon")
            self._fi_install_btn.setEnabled(True)
        else:
            msg = error_msg or "Registration failed. Check the console for details."
            self._fi_status.setText(msg)
            self._fi_status.setStyleSheet(
                "color: #cc4444; font-size: 11px; background: transparent; border: none;"
            )
            self._fi_install_btn.setText("Retry")
            self._fi_install_btn.setEnabled(True)

    def _on_uninstall_file_icon(self):
        """Remove the .bpicker file-type registration."""
        from .thumbnail_handler import uninstall
        uninstall()
        self._fi_status.setText(
            "Not registered — .bpicker files display with a generic icon."
        )
        self._fi_status.setStyleSheet(
            "color: #cc8844; font-size: 11px; background: transparent; border: none;"
        )
        self._fi_install_btn.setText("Register File Icon")
        self._fi_uninstall_btn.hide()

    def _on_install_webengine(self):
        """Start background WebEngine installation from settings."""
        try:
            from . import webengine_deps
        except (ImportError, Exception):
            self._we_status_lbl.show()
            self._we_status_lbl.setText("WebEngine dependency module not available.")
            return

        self._we_install_btn.setEnabled(False)
        self._we_install_btn.setText("Installing...")
        self._we_status_lbl.show()
        self._we_status_lbl.setText("Downloading... This may take a moment.")
        self._we_status_lbl.setStyleSheet(f"color: {_TEXT_MUTED}; font-size: 10px; background: transparent; border: none;")

        self._we_worker = webengine_deps.WebEngineInstallWorker()
        self._we_worker.progress.connect(
            lambda msg: self._we_status_lbl.setText(msg)
        )
        self._we_worker.finished_ok.connect(self._on_we_install_ok)
        self._we_worker.finished_err.connect(self._on_we_install_err)
        self._we_worker.start()

    def _on_we_install_ok(self):
        self._we_install_btn.hide()
        self._we_status_lbl.setStyleSheet("color: #7db305; font-size: 11px; background: transparent; border: none;")
        self._we_status_lbl.setText(
            "WebEngine installed successfully!\n"
            "Restart Maya to enable the embedded library."
        )

    def _on_we_install_err(self, error):
        try:
            from . import webengine_deps
            cmd = webengine_deps.get_manual_install_command()
        except (ImportError, Exception):
            cmd = "pip install PySide6-WebEngine"
        self._we_install_btn.setEnabled(True)
        self._we_install_btn.setText("Retry Install")
        self._we_status_lbl.setStyleSheet("color: #cc4444; font-size: 10px; background: transparent; border: none;")
        self._we_status_lbl.setText(
            f"Installation failed: {error}\n\nTry manually:\n{cmd}"
        )

    @staticmethod
    def _set_path_label(label, path):
        """Set text and tooltip on an eliding path label."""
        label.setFullText(path)
        label.setToolTip(path)


# ===================================================================
# Updates Section
# ===================================================================

class UpdatesSection(QWidget):
    """Inline update UI — powered by UpdateManager singleton."""

    def __init__(self, parent_window=None, parent=None):
        super().__init__(parent)
        self._parent_window = parent_window
        self._download_speed_samples = []
        self._build_ui()
        QTimer.singleShot(200, self._connect_manager)

    def _connect_manager(self):
        from .update_manager import UpdateManager
        mgr = UpdateManager.get_instance()
        mgr.update_available.connect(self._on_update_available)
        mgr.no_update.connect(self._on_no_update)
        mgr.update_check_failed.connect(self._on_check_failed)
        mgr.download_started.connect(self._on_download_started)
        mgr.download_progress.connect(self._on_download_progress)
        mgr.download_completed.connect(self._on_download_completed)
        mgr.download_failed.connect(self._on_download_failed)
        self._refresh_from_cache()

    def _refresh_from_cache(self):
        from .update_manager import UpdateManager
        mgr = UpdateManager.get_instance()
        release = mgr.cached_release
        current = mgr.get_current_version()
        self.current_version_label.setText(f"v{current}")
        if release:
            self._show_update_info(release)
        else:
            self.latest_version_label.setText(f"v{current}")
            self.latest_version_label.setStyleSheet(
                f"color: {_TEXT_PRIMARY}; font-size: 11px; font-weight: bold; "
                "background: transparent; border: none;"
            )

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        layout.addWidget(_section_title("Updates"))

        # -- Version card --
        card = _card_frame()
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(12, 12, 12, 12)
        card_layout.setSpacing(6)

        import ft_anim_picker.src as _pkg
        current = _pkg.__version__

        row1 = QHBoxLayout()
        row1.addWidget(_label("Current Version"))
        self.current_version_label = _label(f"v{current}", color=_TEXT_PRIMARY, bold=True)
        row1.addStretch()
        row1.addWidget(self.current_version_label)
        card_layout.addLayout(row1)

        row2 = QHBoxLayout()
        row2.addWidget(_label("Latest Version"))
        self.latest_version_label = _label("Checking...", color=_TEXT_MUTED)
        row2.addStretch()
        row2.addWidget(self.latest_version_label)
        card_layout.addLayout(row2)

        layout.addWidget(card)

        # -- Update info card (tinted frame: release notes + button + progress) --
        self.update_info_card = QFrame()
        self.update_info_card.setStyleSheet(
            "QFrame { background: rgba(29, 101, 202, 0.06); "
            f"border: 1px solid {_CARD_BORDER}; border-radius: 8px; }}"
        )
        update_info_layout = QVBoxLayout(self.update_info_card)
        update_info_layout.setContentsMargins(12, 12, 12, 12)
        update_info_layout.setSpacing(8)
        self.update_info_card.setVisible(False)

        # Release notes
        self.release_notes_container = QWidget()
        self.release_notes_container.setVisible(False)
        rn_layout = QVBoxLayout(self.release_notes_container)
        rn_layout.setContentsMargins(4, 4, 4, 4)
        rn_layout.setSpacing(6)

        rn_layout.addWidget(_label("What's New", size=12, color=_TEXT_PRIMARY, bold=True))

        self.release_notes_label = _label("", size=11, color=_TEXT_SECONDARY)
        self.release_notes_label.setWordWrap(True)
        self.release_notes_label.setTextFormat(Qt.PlainText)
        rn_layout.addWidget(self.release_notes_label)

        self.changelog_label = _label("", size=10, color=_TEXT_MUTED)
        self.changelog_label.setWordWrap(True)
        self.changelog_label.setTextFormat(Qt.PlainText)
        self.changelog_label.setVisible(False)
        rn_layout.addWidget(self.changelog_label)

        update_info_layout.addWidget(self.release_notes_container)

        # Update button
        self.update_btn = QPushButton("Update")
        self.update_btn.setFixedHeight(30)
        self.update_btn.setMaximumWidth(200)
        self.update_btn.setEnabled(False)
        self.update_btn.setCursor(Qt.PointingHandCursor)
        self.update_btn.setStyleSheet(
            "QPushButton { background-color: #1D65CA; color: white; "
            "border: none; border-radius: 6px; font-weight: bold; font-size: 12px; }"
            "QPushButton:hover { background-color: #2D7AE0; }"
            "QPushButton:disabled { background-color: #444444; color: #888888; }"
        )
        self.update_btn.clicked.connect(self._start_download)
        update_info_layout.addWidget(self.update_btn)

        # Progress section
        self.progress_container = QWidget()
        self.progress_container.setVisible(False)
        progress_layout = QVBoxLayout(self.progress_container)
        progress_layout.setContentsMargins(0, 0, 0, 0)
        progress_layout.setSpacing(4)

        self.progress_bar = QProgressBar()
        self.progress_bar.setStyleSheet(
            "QProgressBar { border: 1px solid #555555; border-radius: 4px; "
            "text-align: center; background-color: #2a2a2a; color: #dddddd; }"
            "QProgressBar::chunk { background-color: #4ca3fe; border-radius: 4px; }"
        )
        progress_layout.addWidget(self.progress_bar)

        self.progress_detail_label = _ElidingLabel("", color=_TEXT_MUTED)
        self.progress_detail_label.setStyleSheet("font-size: 10px; background: transparent; border: none;")
        progress_layout.addWidget(self.progress_detail_label)

        update_info_layout.addWidget(self.progress_container)

        # Status label
        self.status_label = _label("", size=10, color=_TEXT_MUTED)
        self.status_label.setWordWrap(True)
        update_info_layout.addWidget(self.status_label)

        # Success container
        self.success_container = QWidget()
        self.success_container.setVisible(False)
        success_layout = QVBoxLayout(self.success_container)
        success_layout.setContentsMargins(0, 8, 0, 0)
        success_layout.setSpacing(6)

        self.success_msg = _label("Update Successful!", size=14, color="#1D65CA", bold=True)
        self.success_msg.setAlignment(Qt.AlignCenter)
        success_layout.addWidget(self.success_msg)

        self.restart_msg = _label(
            "Please restart Maya to complete the update.",
            size=11, color=_TEXT_SECONDARY,
        )
        self.restart_msg.setAlignment(Qt.AlignCenter)
        self.restart_msg.setWordWrap(True)
        success_layout.addWidget(self.restart_msg)

        update_info_layout.addWidget(self.success_container)

        layout.addWidget(self.update_info_card)

        # -- Settings card --
        settings_card = _card_frame()
        settings_card_layout = QVBoxLayout(settings_card)
        settings_card_layout.setContentsMargins(12, 12, 12, 12)
        settings_card_layout.setSpacing(8)

        settings_title = _label("Update Settings", size=12, color=_TEXT_PRIMARY, bold=True)
        settings_card_layout.addWidget(settings_title)

        # Auto-check toggle
        auto_check_row = QHBoxLayout()
        auto_check_row.addWidget(_label("Check automatically"))
        self.auto_check_btn = QPushButton("On")
        self.auto_check_btn.setFixedSize(40, 22)
        self.auto_check_btn.setCursor(Qt.PointingHandCursor)
        self.auto_check_btn.clicked.connect(self._toggle_auto_check)
        auto_check_row.addStretch()
        auto_check_row.addWidget(self.auto_check_btn)
        settings_card_layout.addLayout(auto_check_row)
        self._update_auto_check_style()

        # Channel selector
        channel_row = QHBoxLayout()
        channel_row.addWidget(_label("Update Type"))
        self.channel_combo = QComboBox()
        self.channel_combo.setFixedSize(65, 24)
        self.channel_combo.setStyleSheet(
            "QComboBox { background-color: #2a2a2a; color: #dddddd; "
            "border: 1px solid #555555; border-radius: 3px; padding: 4px; font-size: 11px; }"
            "QComboBox:hover { border-color: #4ca3fe; }"
            "QComboBox::drop-down { border: none; width: 20px; }"
            "QComboBox::down-arrow { image: none; border: 2px solid #aaaaaa; "
            "border-top: none; border-left: none; width: 6px; height: 6px; margin-right: 6px; }"
            "QComboBox QAbstractItemView { background-color: #2a2a2a; "
            "border: 1px solid #555555; selection-background-color: #4ca3fe; color: #dddddd; }"
        )
        from .config import settings as CFG
        for ch in CFG.UPDATE_CHANNELS:
            self.channel_combo.addItem(ch.capitalize(), ch)
        self.channel_combo.currentIndexChanged.connect(self._on_channel_changed)
        channel_row.addStretch()
        channel_row.addWidget(self.channel_combo)
        settings_card_layout.addLayout(channel_row)
        
        # Check now button
        self.check_now_btn = QPushButton("Check For Updates")
        self.check_now_btn.setFixedHeight(26)
        self.check_now_btn.setMaximumWidth(120)
        self.check_now_btn.setCursor(Qt.PointingHandCursor)
        self.check_now_btn.setStyleSheet(
            "QPushButton { background-color: #333; color: #ccc; "
            "border: 1px solid #555; border-radius: 4px; font-size: 11px; }"
            "QPushButton:hover { background-color: #444; border-color: #4ca3fe; }"
        )
        self.check_now_btn.clicked.connect(self._check_now)
        settings_card_layout.addWidget(self.check_now_btn)
        
        layout.addWidget(settings_card)

        layout.addStretch()
        self._load_channel_pref()

    # -- Manager signal handlers -------------------------------------------

    def _on_update_available(self, release):
        self._show_update_info(release)

    def _show_update_info(self, release):
        version = release.get("version", "?")
        self.latest_version_label.setText(f"v{version}")
        self.latest_version_label.setStyleSheet(
            "color: #1D65CA; font-size: 11px; font-weight: bold; "
            "background: transparent; border: none;"
        )

        self.update_info_card.setVisible(True)

        notes = release.get("release_notes", "")
        changelog = release.get("changelog", "")
        if notes or changelog:
            self.release_notes_container.setVisible(True)
            self.release_notes_label.setText(notes if notes else "")
            self.release_notes_label.setVisible(bool(notes))
            if changelog:
                self.changelog_label.setText(changelog)
                self.changelog_label.setVisible(True)

        self.update_btn.setEnabled(True)
        self.update_btn.setText(f"Update to v{version}")
        self._pending_version = version

        file_size = release.get("file_size", 0)
        channel = release.get("channel", "stable")
        parts = []
        if channel != "stable":
            parts.append(f"Channel: {channel}")
        if file_size > 0:
            parts.append(f"Size: {self._format_bytes(file_size)}")
        self.status_label.setText(" · ".join(parts) if parts else "")

    def _on_no_update(self, current_version):
        self.latest_version_label.setText(f"v{current_version}")
        self.latest_version_label.setStyleSheet(
            f"color: {_TEXT_PRIMARY}; font-size: 11px; font-weight: bold; "
            "background: transparent; border: none;"
        )
        self.update_btn.setEnabled(False)
        self.update_btn.setText("Up to date")
        self.status_label.setText("")
        self.release_notes_container.setVisible(False)
        self.update_info_card.setVisible(False)

    def _on_check_failed(self, error_msg):
        self.latest_version_label.setText("Error")
        self.latest_version_label.setStyleSheet(
            "color: #cc4444; font-size: 11px; background: transparent; border: none;"
        )
        self.status_label.setText(f"Check failed: {error_msg}")

    def _on_download_started(self):
        self.progress_container.setVisible(True)
        self.progress_bar.setValue(0)
        self.update_btn.setEnabled(False)
        self.status_label.setText("Downloading...")
        self._download_speed_samples = []

    def _on_download_progress(self, bytes_done, total_bytes):
        import time as _time
        if total_bytes > 0:
            percent = int(bytes_done * 100 / total_bytes)
            self.progress_bar.setValue(percent)

            now = _time.time()
            self._download_speed_samples.append((now, bytes_done))
            if len(self._download_speed_samples) > 10:
                self._download_speed_samples = self._download_speed_samples[-10:]

            speed_text = ""
            if len(self._download_speed_samples) >= 2:
                first = self._download_speed_samples[0]
                dt = now - first[0]
                db = bytes_done - first[1]
                if dt > 0:
                    speed = db / dt
                    remaining = (total_bytes - bytes_done) / speed if speed > 0 else 0
                    speed_text = f" ({self._format_bytes(int(speed))}/s"
                    if remaining > 0:
                        speed_text += f", ~{int(remaining)}s left"
                    speed_text += ")"

            self.progress_detail_label.setText(
                f"{self._format_bytes(bytes_done)} / {self._format_bytes(total_bytes)}{speed_text}"
            )

    def _on_download_completed(self, version):
        self.progress_container.setVisible(False)
        self.update_btn.setVisible(False)
        self.release_notes_container.setVisible(False)

        from .update_manager import UpdateManager
        current = UpdateManager.get_instance().get_current_version()
        self.success_msg.setText(f"Updated v{current} → v{version}")
        self.restart_msg.setText("Please restart Maya to complete the update.")
        self.success_container.setVisible(True)
        self.status_label.setText("")

    def _on_download_failed(self, error_msg):
        self.progress_container.setVisible(False)
        self.update_btn.setEnabled(True)
        self.status_label.setText(f"Download failed: {error_msg}")

    # -- Actions -----------------------------------------------------------

    def _start_download(self):
        version = getattr(self, "_pending_version", None)
        if not version:
            return
        from .update_manager import UpdateManager
        UpdateManager.get_instance().download_update(version)

    def _check_now(self):
        self.latest_version_label.setText("Checking...")
        self.latest_version_label.setStyleSheet(
            f"color: {_TEXT_MUTED}; font-size: 11px; background: transparent; border: none;"
        )
        self.status_label.setText("")
        from .update_manager import UpdateManager
        UpdateManager.get_instance().check_for_update(force=True)

    def _toggle_auto_check(self):
        from .update_manager import UpdateManager
        mgr = UpdateManager.get_instance()
        current = mgr.get_auto_check()
        mgr.set_auto_check(not current)
        self._update_auto_check_style()

    def _update_auto_check_style(self):
        from .update_manager import UpdateManager
        enabled = UpdateManager.get_instance().get_auto_check()
        self.auto_check_btn.setText("On" if enabled else "Off")
        if enabled:
            self.auto_check_btn.setStyleSheet(
                "QPushButton { background-color: #1D65CA; color: white; "
                "border: none; border-radius: 4px; font-size: 10px; font-weight: bold; }"
            )
        else:
            self.auto_check_btn.setStyleSheet(
                "QPushButton { background-color: #444; color: #888; "
                "border: 1px solid #555; border-radius: 4px; font-size: 10px; }"
            )

    def _on_channel_changed(self, index):
        channel = self.channel_combo.itemData(index)
        if channel:
            from .update_manager import UpdateManager
            UpdateManager.get_instance().set_channel(channel)

    def _load_channel_pref(self):
        from .update_manager import UpdateManager
        channel = UpdateManager.get_instance().get_channel()
        for i in range(self.channel_combo.count()):
            if self.channel_combo.itemData(i) == channel:
                self.channel_combo.setCurrentIndex(i)
                break

    # -- Helpers -----------------------------------------------------------

    @staticmethod
    def _format_bytes(n):
        if n < 1024:
            return f"{n} B"
        elif n < 1024 * 1024:
            return f"{n / 1024:.1f} KB"
        else:
            return f"{n / (1024 * 1024):.1f} MB"

    # -- Backward compat stubs (called by ui.py) ---------------------------

    @staticmethod
    def parse_version(version_string):
        from .update_manager import parse_version
        return parse_version(version_string)

    @staticmethod
    def is_newer_version(latest, current):
        from .update_manager import is_newer_version
        return is_newer_version(latest, current)

    def get_latest_tag(self):
        """Backward compat — returns cached latest tag or None."""
        from .update_manager import UpdateManager
        mgr = UpdateManager.get_instance()
        release = mgr.cached_release
        return release.get("version") if release else None


# ===================================================================
# More Info Section
# ===================================================================

class MoreInfoSection(QWidget):
    """App info, version, and useful links."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        layout.addWidget(_section_title("More Info"))

        # -- App info card --
        card = _card_frame()
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(12, 16, 12, 16)
        card_layout.setSpacing(6)
        card_layout.setAlignment(Qt.AlignCenter)

        icons_dir = Path(__file__).parent / "bgen_picker_icons"
        logo_path = icons_dir / "bgen-picker-icon-02.png"
        if logo_path.exists():
            icon_lbl = QLabel()
            icon_lbl.setPixmap(
                QtGui.QPixmap(str(logo_path)).scaled(
                    48, 48, Qt.KeepAspectRatio, Qt.SmoothTransformation
                )
            )
            icon_lbl.setAlignment(Qt.AlignCenter)
            icon_lbl.setStyleSheet("background: transparent; border: none;")
            card_layout.addWidget(icon_lbl)

        name_lbl = _label("BGEN Picker", size=14, color=_TEXT_PRIMARY, bold=True)
        name_lbl.setAlignment(Qt.AlignCenter)
        card_layout.addWidget(name_lbl)

        import ft_anim_picker.src as _pkg
        ver_lbl = _label(f"v{_pkg.__version__}", size=12, color=_TEXT_SECONDARY)
        ver_lbl.setAlignment(Qt.AlignCenter)
        card_layout.addWidget(ver_lbl)

        author_lbl = _label(f"by {AUTHOR_NAME}", size=11, color=_TEXT_SECONDARY)
        author_lbl.setAlignment(Qt.AlignCenter)
        card_layout.addWidget(author_lbl)

        layout.addWidget(card)

        # -- Links card --
        links_card = _card_frame()
        links_layout = QVBoxLayout(links_card)
        links_layout.setContentsMargins(12, 8, 12, 8)
        links_layout.setSpacing(0)

        links_layout.addWidget(_link_button("M2KY Website", WEBSITE_URL, "m2ky_icon.png"))
        links_layout.addWidget(_link_button("Report a Bug", DISCORD_URL, "discord_icon.png"))
        links_layout.addWidget(_link_button("Instagram", INSTAGRAM_URL, "instagram_icon.png"))
        yt_enabled = bool(YOUTUBE_URL)
        yt_text = "Tutorials" if yt_enabled else "Tutorials (coming soon)"
        links_layout.addWidget(_link_button(yt_text, YOUTUBE_URL, "youtube_icon.png", enabled=yt_enabled))

        layout.addWidget(links_card)
        layout.addStretch()


# ===================================================================
# Settings Page (top-level)
# ===================================================================

class SettingsPage(QWidget):
    """Settings page with sidebar navigation and four content sections."""

    def __init__(self, parent_window=None, browse_callback=None, open_folder_callback=None,
                 browse_downloads_callback=None, open_downloads_callback=None, parent=None):
        super().__init__(parent)
        self._parent_window = parent_window
        self.setStyleSheet("background: transparent;")

        main_layout = QHBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # Sidebar
        self.sidebar = SettingsSidebar()
        main_layout.addWidget(self.sidebar)

        # Content stack
        self.content_stack = QStackedWidget()
        self.content_stack.setStyleSheet("background: transparent; border: none;")

        # Sections (Account is handled by the web library)
        self.preferences = PreferencesSection(
            browse_callback=browse_callback or (lambda: None),
            open_folder_callback=open_folder_callback or (lambda: None),
            browse_downloads_callback=browse_downloads_callback or (lambda: None),
            open_downloads_callback=open_downloads_callback or (lambda: None),
        )
        self.updates = UpdatesSection(parent_window=parent_window)
        self.more_info = MoreInfoSection()

        # Wrap each in scroll area
        for section in (self.preferences, self.updates, self.more_info):
            sa = _section_scroll()
            sa.setWidget(section)
            self.content_stack.addWidget(sa)

        main_layout.addWidget(self.content_stack)

        # Wire sidebar
        self.sidebar.section_changed.connect(self.content_stack.setCurrentIndex)

    # -- Public API --------------------------------------------------------

    def update_library_path_display(self, path: str):
        PreferencesSection._set_path_label(self.preferences.lib_path_label, path)

    def update_downloads_path_display(self, path: str):
        PreferencesSection._set_path_label(self.preferences.dl_path_label, path)

    def on_page_shown(self):
        """Called when the settings page becomes visible."""
        # Refresh path displays
        from .local_file_manager import LocalFileManager
        PreferencesSection._set_path_label(
            self.preferences.lib_path_label, str(LocalFileManager.get_library_path())
        )
        PreferencesSection._set_path_label(
            self.preferences.dl_path_label, str(LocalFileManager.get_downloads_path())
        )

    def set_section(self, index: int):
        """Programmatically switch to a specific section (0=Preferences, 1=Updates, 2=More Info)."""
        self.sidebar.set_selected_index(index)
        self.content_stack.setCurrentIndex(index)
