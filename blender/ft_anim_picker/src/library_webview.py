"""
Library WebView — Embeds the hosted BGEN Library web app inside QWebEngineView.

Communicates with the addon via QWebChannel bridge for:
- Auth token sharing (addon owns the session)
- Download triggers (addon handles native file downloads + library import)
- Addon info (version, platform)
- Navigation events (open library, sign in/out)

The web app detects the bridge via `window.qt.webChannelTransport` and
falls back to web-native APIs when running standalone on a website.
"""

import json
from pathlib import Path

from PySide6 import QtWidgets, QtCore, QtGui
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWebEngineCore import QWebEnginePage, QWebEngineProfile, QWebEngineScript
from PySide6.QtWebChannel import QWebChannel

from .config import settings as CFG


# ---------------------------------------------------------------------------
# Bridge: JS <-> Python communication
# ---------------------------------------------------------------------------

class LibraryBridge(QtCore.QObject):
    """
    QWebChannel bridge exposing addon functionality to the web app.

    JS calls Python via registered slots.
    Python pushes events to JS via the page's runJavaScript().
    """

    # Signals emitted when JS requests addon actions
    download_requested = QtCore.Signal(str)          # product_id
    open_library_requested = QtCore.Signal()
    sign_in_requested = QtCore.Signal()
    sign_in_google_requested = QtCore.Signal()
    sign_out_requested = QtCore.Signal()
    navigate_to_product = QtCore.Signal(str)         # product_id
    navigate_to_collection = QtCore.Signal(str, str) # collection_id, title
    navigate_to_creator = QtCore.Signal(str)         # creator_id
    checkout_requested = QtCore.Signal(str)           # product_id

    def __init__(self, parent=None):
        super().__init__(parent)
        self._auth_manager = None
        self._library_manager = None

    def set_managers(self, auth_manager, library_manager):
        """Inject manager references after construction."""
        self._auth_manager = auth_manager
        self._library_manager = library_manager

    # -- Slots callable from JavaScript --

    @QtCore.Slot(result=str)
    def getAuthToken(self):
        """Return the current access token, or empty string if not signed in."""
        if self._auth_manager and self._auth_manager.is_signed_in():
            snapshot = self._auth_manager.get_token_snapshot()
            return snapshot[0] if snapshot and snapshot[0] else ""
        return ""

    @QtCore.Slot(result=str)
    def getAddonInfo(self):
        """Return addon metadata as JSON string."""
        return json.dumps({
            "version": CFG.APP_VERSION,
            "platform": "blender",
            "bridge_version": 1,
        })

    @QtCore.Slot(result=bool)
    def isSignedIn(self):
        """Check if the user is currently signed in."""
        if self._auth_manager:
            return self._auth_manager.is_signed_in()
        return False

    @QtCore.Slot(result=str)
    def getUserInfo(self):
        """Return current user info as JSON, or empty string."""
        if self._auth_manager and self._auth_manager.is_signed_in():
            user = self._auth_manager.get_user()
            if user:
                return json.dumps({
                    "id": user.get("id", ""),
                    "email": user.get("email", ""),
                    "display_name": user.get("display_name", ""),
                    "avatar_url": user.get("avatar_url", ""),
                })
        return ""

    @QtCore.Slot(str)
    def downloadProduct(self, product_id):
        """Request the addon to download a product natively."""
        self.download_requested.emit(product_id)

    @QtCore.Slot()
    def openLibrary(self):
        """Switch the addon to the local library tab."""
        self.open_library_requested.emit()

    @QtCore.Slot()
    def signIn(self):
        """Request the addon to show its native sign-in flow."""
        self.sign_in_requested.emit()

    @QtCore.Slot()
    def signInWithGoogle(self):
        """Trigger the addon's native Google OAuth flow (system browser + local server)."""
        self.sign_in_google_requested.emit()

    @QtCore.Slot()
    def signOut(self):
        """Request the addon to sign out."""
        self.sign_out_requested.emit()

    @QtCore.Slot(str)
    def navigateToProduct(self, product_id):
        """Navigate to a product detail page."""
        self.navigate_to_product.emit(product_id)

    @QtCore.Slot(str, str)
    def navigateToCollection(self, collection_id, title):
        """Navigate to a filtered collection page."""
        self.navigate_to_collection.emit(collection_id, title)

    @QtCore.Slot(str)
    def navigateToCreator(self, creator_id):
        """Navigate to a creator profile page."""
        self.navigate_to_creator.emit(creator_id)

    @QtCore.Slot(str)
    def initiateCheckout(self, product_id):
        """Request the addon to start checkout for a product."""
        self.checkout_requested.emit(product_id)

    @QtCore.Slot(str, result=bool)
    def isOwned(self, product_id):
        """Check if the user owns a specific product."""
        if self._library_manager:
            return self._library_manager.is_owned(product_id)
        return False

    @QtCore.Slot(result=str)
    def getEntitlements(self):
        """Return list of owned product IDs as JSON array."""
        if self._library_manager:
            return json.dumps(list(self._library_manager._owned_ids))
        return "[]"

    @QtCore.Slot(str, str, float, str)
    def syncSession(self, access_token, refresh_token, expires_at, user_json):
        """Web app pushes its auth session to the addon's AuthManager.

        Called after the user signs in via the web app's Supabase Auth.
        Writes tokens so the addon can use them for downloads/purchases.
        """
        if not self._auth_manager:
            return
        try:
            import time
            user_data = json.loads(user_json) if user_json else {}

            with self._auth_manager._token_lock:
                self._auth_manager._access_token = access_token
                self._auth_manager._refresh_token = refresh_token
                self._auth_manager._expires_at = expires_at

            self._auth_manager._user = {
                "id": user_data.get("id", ""),
                "email": user_data.get("email", ""),
                "display_name": user_data.get("displayName", ""),
                "avatar_url": user_data.get("avatarUrl", ""),
            }

            self._auth_manager._save_session()
            self._auth_manager._schedule_refresh()
            self._auth_manager.auth_state_changed.emit(True)
        except Exception as e:
            print(f"[LibraryBridge] syncSession error: {e}")

    @QtCore.Slot()
    def clearSession(self):
        """Web app requests sign-out — clear addon's auth session."""
        if self._auth_manager:
            self._auth_manager.sign_out()

    @QtCore.Slot(str)
    def openExternalUrl(self, url):
        """Open a URL in the system's default browser."""
        QtGui.QDesktopServices.openUrl(QtCore.QUrl(url))

    @QtCore.Slot(result=str)
    def getVersion(self):
        """Return bridge API version for forward-compatibility."""
        return "2"


# ---------------------------------------------------------------------------
# Custom page that opens external OAuth URLs in the system browser
# ---------------------------------------------------------------------------

_EXTERNAL_DOMAINS = {"accounts.google.com", "appleid.apple.com", "github.com/login"}

class _LibraryPage(QWebEnginePage):
    """QWebEnginePage that intercepts OAuth navigations and opens them externally."""

    def __init__(self, profile, parent=None):
        super().__init__(profile, parent)
        self._library_host = ""

    def set_library_host(self, host):
        self._library_host = host

    def acceptNavigationRequest(self, url, nav_type, is_main_frame):
        if is_main_frame and nav_type == QWebEnginePage.NavigationType.NavigationTypeLinkClicked:
            host = url.host()
            # If navigating to an external OAuth domain, open in system browser
            if any(domain in host for domain in _EXTERNAL_DOMAINS):
                QtGui.QDesktopServices.openUrl(url)
                return False
        return super().acceptNavigationRequest(url, nav_type, is_main_frame)


# ---------------------------------------------------------------------------
# WebView Widget
# ---------------------------------------------------------------------------

# Default library URL — override via CFG.LIBRARY_WEB_URL if set
_DEFAULT_LIBRARY_URL = ""  # Set this when you deploy the web app

def _get_library_url():
    """Return the library web app URL from config or default."""
    return getattr(CFG, "LIBRARY_WEB_URL", _DEFAULT_LIBRARY_URL)


class LibraryWebView(QtWidgets.QWidget):
    """
    Embeds the hosted BGEN Library web app in a QWebEngineView.

    Usage:
        webview = LibraryWebView(parent=self)
        webview.set_managers(auth_manager, library_manager)
        webview.load_library()

    The widget manages its own QWebEngineProfile (off-the-record for privacy)
    and QWebChannel bridge.
    """

    # Re-emit bridge signals for the parent UI to connect
    download_requested = QtCore.Signal(str)
    open_library_requested = QtCore.Signal()
    sign_in_requested = QtCore.Signal()
    sign_in_google_requested = QtCore.Signal()
    sign_out_requested = QtCore.Signal()
    navigate_to_product = QtCore.Signal(str)
    navigate_to_collection = QtCore.Signal(str, str)
    navigate_to_creator = QtCore.Signal(str)
    checkout_requested = QtCore.Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._bridge = LibraryBridge(self)
        self._webview = None
        self._page = None
        self._loaded = False
        self._build_ui()
        self._connect_bridge_signals()

    _BORDER_RADIUS = 10

    def _build_ui(self):
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Rounded clip container
        self._clip_container = QtWidgets.QFrame()
        self._clip_container.setStyleSheet(
            f"QFrame {{ background: transparent; "
            f"border-radius: {self._BORDER_RADIUS}px; }}"
        )
        clip_layout = QtWidgets.QVBoxLayout(self._clip_container)
        clip_layout.setContentsMargins(0, 0, 0, 0)
        clip_layout.setSpacing(0)

        # Loading placeholder (shown until web app loads)
        self._loading_label = QtWidgets.QLabel("Loading library...")
        self._loading_label.setAlignment(QtCore.Qt.AlignCenter)
        self._loading_label.setStyleSheet(
            "color: #888888; font-size: 12px; background: transparent;"
        )
        clip_layout.addWidget(self._loading_label)

        # WebView (created lazily on first load)
        self._webview = QWebEngineView()
        self._webview.setStyleSheet("background: transparent;")
        self._webview.hide()
        clip_layout.addWidget(self._webview)

        layout.addWidget(self._clip_container)

    def _connect_bridge_signals(self):
        """Forward bridge signals to widget-level signals."""
        self._bridge.download_requested.connect(self.download_requested)
        self._bridge.open_library_requested.connect(self.open_library_requested)
        self._bridge.sign_in_requested.connect(self.sign_in_requested)
        self._bridge.sign_in_google_requested.connect(self.sign_in_google_requested)
        self._bridge.sign_out_requested.connect(self.sign_out_requested)
        self._bridge.navigate_to_product.connect(self.navigate_to_product)
        self._bridge.navigate_to_collection.connect(self.navigate_to_collection)
        self._bridge.navigate_to_creator.connect(self.navigate_to_creator)
        self._bridge.checkout_requested.connect(self.checkout_requested)

    def set_managers(self, auth_manager, library_manager):
        """Inject auth and library manager references."""
        self._bridge.set_managers(auth_manager, library_manager)

    def load_library(self, url=None):
        """Load the library web app. Call once on first display."""
        if self._loaded:
            return

        library_url = url or _get_library_url()
        if not library_url:
            self._loading_label.setText(
                "Library URL not configured.\n"
                "Set LIBRARY_WEB_URL in config/settings.py"
            )
            return

        # Off-the-record profile (no persistent cookies/storage)
        profile = QWebEngineProfile(self)
        self._page = _LibraryPage(profile, self)
        self._page.setBackgroundColor(QtGui.QColor(0, 0, 0, 0))
        self._page.set_library_host(QtCore.QUrl(library_url).host())
        self._webview.setPage(self._page)

        # Inject qwebchannel.js so the web app can use window.QWebChannel
        self._inject_qwebchannel_script(profile)

        # Set up QWebChannel bridge
        channel = QWebChannel(self._page)
        channel.registerObject("bridge", self._bridge)
        self._page.setWebChannel(channel)

        # Load the web app
        self._page.loadFinished.connect(self._on_load_finished)
        self._page.load(QtCore.QUrl(library_url))
        self._loaded = True

    def _inject_qwebchannel_script(self, profile):
        """Inject Qt's qwebchannel.js so the web app can construct QWebChannel."""
        # Try to find the qwebchannel.js that ships with PySide6/Qt
        qwc_path = None
        try:
            import PySide6
            qt_dir = Path(PySide6.__file__).parent
            # Standard locations for qwebchannel.js
            candidates = [
                qt_dir / "Qt" / "lib" / "QtWebEngine.framework" / "Resources" / "qtwebchannel" / "qwebchannel.js",
                qt_dir / "resources" / "qtwebchannel" / "qwebchannel.js",
                qt_dir / "Qt" / "resources" / "qtwebchannel" / "qwebchannel.js",
                qt_dir / "Qt" / "qml" / "QtWebChannel" / "qwebchannel.js",
            ]
            for candidate in candidates:
                if candidate.exists():
                    qwc_path = candidate
                    break
        except Exception:
            pass

        if qwc_path:
            js_source = qwc_path.read_text(encoding="utf-8")
        else:
            # Fallback: use Qt's resource system
            qrc_file = QtCore.QFile(":/qtwebchannel/qwebchannel.js")
            if qrc_file.open(QtCore.QIODevice.ReadOnly):
                js_source = bytes(qrc_file.readAll()).decode("utf-8")
                qrc_file.close()
            else:
                print("[LibraryWebView] WARNING: Could not find qwebchannel.js — bridge will not work")
                return

        script = QWebEngineScript()
        script.setName("qwebchannel")
        script.setSourceCode(js_source)
        script.setInjectionPoint(QWebEngineScript.InjectionPoint.DocumentCreation)
        script.setWorldId(QWebEngineScript.ScriptWorldId.MainWorld)
        script.setRunsOnSubFrames(False)
        profile.scripts().insert(script)

    def _on_load_finished(self, ok):
        """Called when the web app finishes loading."""
        if ok:
            self._loading_label.hide()
            self._webview.show()
            # Force a geometry update so the WebView paints correctly
            # when first shown inside a QStackedWidget.
            QtCore.QTimer.singleShot(0, self._force_webview_repaint)
            # After React mounts, push current auth state so the web app
            # picks up the addon's persisted session (off-the-record profile
            # has no localStorage, so the web app cannot restore on its own).
            QtCore.QTimer.singleShot(500, self._push_initial_auth_state)
        else:
            self._loading_label.setText(
                "Failed to load library.\nCheck your internet connection."
            )

    def resizeEvent(self, event):
        """Apply a rounded-rect mask so the QWebEngineView content is clipped."""
        super().resizeEvent(event)
        self._apply_rounded_mask()

    def _apply_rounded_mask(self):
        """Set a rounded QRegion mask on the clip container."""
        r = self._BORDER_RADIUS
        rect = self._clip_container.rect()
        path = QtGui.QPainterPath()
        path.addRoundedRect(QtCore.QRectF(rect), r, r)
        region = QtGui.QRegion(path.toFillPolygon().toPolygon())
        self._clip_container.setMask(region)

    def _force_webview_repaint(self):
        """Force WebView to repaint after first show inside a QStackedWidget."""
        if self._webview:
            sz = self._webview.size()
            self._webview.resize(sz.width(), sz.height() - 1)
            self._webview.resize(sz)

    def _push_initial_auth_state(self):
        """Push the addon's current auth state to the web app after page load."""
        if self._bridge and self._bridge._auth_manager:
            is_signed_in = self._bridge._auth_manager.is_signed_in()
            self.push_auth_state_changed(is_signed_in)

    # -- Python -> JS communication --

    def push_download_progress(self, product_id, done, total):
        """Push download progress to the web app."""
        if self._page:
            self._page.runJavaScript(
                f"window.__bgenBridge?.onDownloadProgress?.("
                f"'{product_id}', {done}, {total})"
            )

    def push_download_complete(self, product_id, path=""):
        """Notify the web app that a download completed."""
        if self._page:
            escaped_path = path.replace("\\", "\\\\").replace("'", "\\'")
            self._page.runJavaScript(
                f"window.__bgenBridge?.onDownloadComplete?.("
                f"'{product_id}', '{escaped_path}')"
            )

    def push_download_failed(self, product_id, error=""):
        """Notify the web app that a download failed."""
        if self._page:
            escaped_error = error.replace("\\", "\\\\").replace("'", "\\'")
            self._page.runJavaScript(
                f"window.__bgenBridge?.onDownloadFailed?.("
                f"'{product_id}', '{escaped_error}')"
            )

    def push_auth_state_changed(self, is_signed_in):
        """Notify the web app that auth state changed."""
        if self._page:
            val = "true" if is_signed_in else "false"
            self._page.runJavaScript(
                f"window.__bgenBridge?.onAuthStateChanged?.({val})"
            )

    def push_token_refreshed(self, new_token):
        """Push a refreshed token to the web app."""
        if self._page:
            self._page.runJavaScript(
                f"window.__bgenBridge?.onTokenRefreshed?.('{new_token}')"
            )

    def reload(self):
        """Force reload the web app."""
        if self._page:
            self._page.triggerAction(QWebEnginePage.Reload)

    def cleanup(self):
        """Release WebEngine resources."""
        if self._webview:
            self._webview.setPage(None)
        self._page = None
        self._loaded = False
