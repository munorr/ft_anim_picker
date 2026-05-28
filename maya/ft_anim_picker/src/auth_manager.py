"""
Auth Manager — Singleton for Supabase email-OTP and Google OAuth authentication.

Handles the complete auth lifecycle:
  1. send_otp(email) → sends 6-digit code to user's email
  2. verify_otp(email, code) → exchanges code for session tokens
  3. sign_in_with_google() → opens browser for Google OAuth, captures tokens
  4. Auto-refreshes tokens before expiry via QTimer
  5. Persists session to auth_prefs.json for cross-restart continuity
  6. sign_out() → clears session locally and server-side

All network calls run on a background QThread so the UI stays responsive.
"""

import datetime
import json
import locale
import os
import platform
import threading
import time
import urllib.parse
import uuid
import webbrowser
from http.server import HTTPServer, BaseHTTPRequestHandler

try:
    from PySide6.QtCore import QObject, QTimer, QThread, Signal, Qt
except ImportError:
    from PySide2.QtCore import QObject, QTimer, QThread, Signal, Qt

from .config import settings as CFG
from .supabase_client import SupabaseClient, SupabaseError


# ---------------------------------------------------------------------------
# Persistence helpers (follows library_manager.py pattern)
# ---------------------------------------------------------------------------

def _get_auth_path():
    """Return the path to the auth preferences JSON file."""
    addon_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(addon_dir, CFG.AUTH_PREFS_FILE)


def _read_auth_prefs():
    path = _get_auth_path()
    if os.path.isfile(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {}


def _write_auth_prefs(data):
    path = _get_auth_path()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)


def _delete_auth_prefs():
    path = _get_auth_path()
    if os.path.isfile(path):
        try:
            os.remove(path)
        except OSError:
            pass


# ---------------------------------------------------------------------------
# Auth Worker (background thread for network calls)
# ---------------------------------------------------------------------------

class _AuthWorker(QThread):
    """Runs a callable on a background thread and emits the result."""
    finished = Signal(dict)
    error = Signal(str)

    def __init__(self, fn, *args):
        super().__init__()
        self._fn = fn
        self._args = args

    def run(self):
        try:
            result = self._fn(*self._args)
            self.finished.emit(result if isinstance(result, dict) else {})
        except Exception as exc:
            import traceback
            traceback.print_exc()
            self.error.emit(str(exc))


# ---------------------------------------------------------------------------
# AuthManager (singleton)
# ---------------------------------------------------------------------------

class AuthManager(QObject):
    """
    Singleton managing Supabase email-OTP authentication.

    Signals
    -------
    auth_state_changed(bool)
        Emitted when sign-in state changes. ``True`` = signed in.
    auth_error(str)
        Emitted when an auth operation fails.
    otp_sent()
        Emitted after a magic-link OTP email is successfully sent.
    """

    auth_state_changed = Signal(bool)
    auth_error = Signal(str)
    otp_sent = Signal()
    profile_error = Signal(str)       # Emitted when profile upsert fails (non-fatal)
    sessions_loaded = Signal(list)    # Emitted with list of active session dicts
    sessions_error = Signal(str)      # Emitted on session fetch failure
    device_signed_out = Signal(str)   # Emitted with session_id after successful removal
    _oauth_result = Signal(object)  # Internal: delivers OAuth tokens from HTTP thread to main thread
    _oauth_error = Signal(str)      # Internal: delivers OAuth errors from HTTP thread to main thread

    _instance = None

    @classmethod
    def get_instance(cls):
        """Return the singleton AuthManager, creating it on first call."""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    @classmethod
    def reset_instance(cls):
        """Destroy the singleton (useful for tests or addon reload)."""
        if cls._instance is not None:
            cls._instance._refresh_timer.stop()
            cls._instance._heartbeat_timer.stop()
            cls._instance = None

    # ------------------------------------------------------------------
    # Init
    # ------------------------------------------------------------------

    def __init__(self):
        super().__init__()

        self._client = SupabaseClient(CFG.SUPABASE_URL, CFG.SUPABASE_ANON_KEY)

        # Lock protecting token state accessed from background threads
        self._token_lock = threading.Lock()

        # Session state (guarded by _token_lock for cross-thread reads)
        self._access_token = None
        self._refresh_token = None
        self._expires_at = 0.0
        self._user = None  # {id, email}
        self._session_id = None  # Unique ID for this device session (tracked in user_sessions)

        # Background worker reference (prevent GC)
        self._worker = None
        self._fire_and_forget_workers = []  # Keep refs for telemetry workers

        # Auto-refresh timer
        self._refresh_timer = QTimer(self)
        self._refresh_timer.setSingleShot(True)
        self._refresh_timer.timeout.connect(self._auto_refresh)

        # Session heartbeat timer (updates last_active_at periodically)
        self._heartbeat_timer = QTimer(self)
        self._heartbeat_timer.timeout.connect(self._send_heartbeat)

        # Internal: wire OAuth result signal to session handler.
        # QueuedConnection is required because _oauth_result is emitted from a
        # plain threading.Thread (the HTTP server), not a QThread — so Qt cannot
        # auto-detect the thread boundary.
        self._oauth_result.connect(self._on_session_received, Qt.QueuedConnection)
        self._oauth_error.connect(self._on_error, Qt.QueuedConnection)

        # Attempt to restore a previous session
        self._load_stored_session()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def send_otp(self, email: str):
        """Send a 6-digit OTP code to *email* (async)."""
        if not CFG.SUPABASE_URL or not CFG.SUPABASE_ANON_KEY:
            self.auth_error.emit("Supabase is not configured.")
            return

        def _do():
            return self._client.send_otp(email)

        self._run_worker(_do, on_success=self._on_otp_sent)

    def verify_otp(self, email: str, code: str):
        """Verify the OTP code and sign in (async)."""
        if not CFG.SUPABASE_URL or not CFG.SUPABASE_ANON_KEY:
            self.auth_error.emit("Supabase is not configured.")
            return

        def _do():
            return self._client.verify_otp(email, code)

        self._run_worker(_do, on_success=self._on_session_received)

    def sign_in_with_google(self):
        """Start Google OAuth sign-in flow.

        Opens the user's default browser to the Supabase Google OAuth page.
        A tiny localhost HTTP server captures the redirect with tokens.
        """
        if not CFG.SUPABASE_URL or not CFG.SUPABASE_ANON_KEY:
            self.auth_error.emit("Supabase is not configured.")
            return

        port = CFG.OAUTH_LOCAL_PORT
        redirect_to = f"http://localhost:{port}/auth/callback"
        oauth_url = self._client.get_oauth_url("google", redirect_to)

        # Start the local callback server in a background thread
        self._start_oauth_server(port)
        webbrowser.open(oauth_url)

    def _start_oauth_server(self, port: int):
        """Run a one-shot localhost HTTP server to capture the OAuth redirect."""
        manager = self  # closure reference
        done_event = threading.Event()

        class _CallbackHandler(BaseHTTPRequestHandler):
            """Handles the OAuth redirect from Supabase."""

            def do_GET(self):
                parsed = urllib.parse.urlparse(self.path)
                if parsed.path == "/auth/callback":
                    # Supabase redirects with tokens in the URL fragment (#access_token=...),
                    # but fragments aren't sent to the server. We serve a small HTML page
                    # that reads the fragment and POSTs the tokens back to us.
                    self.send_response(200)
                    self.send_header("Content-Type", "text/html")
                    self.end_headers()
                    html = f"""<!DOCTYPE html><html><body>
<p id="msg">Signing in...</p>
<script>
const hash = window.location.hash.substring(1);
const msg = document.getElementById("msg");
if (hash) {{
    fetch("/auth/tokens", {{
        method: "POST",
        headers: {{"Content-Type": "application/x-www-form-urlencoded"}},
        body: hash
    }}).then(r => {{
        if (r.ok) {{
            msg.textContent = "Signed in! You can close this tab.";
            setTimeout(() => window.close(), 1000);
        }} else {{
            msg.textContent = "Sign-in failed (server error).";
        }}
    }}).catch(e => {{
        msg.textContent = "Sign-in failed: " + e.message;
    }});
}} else {{
    msg.textContent = "Authentication failed — no tokens received.";
}}
</script></body></html>"""
                    self.wfile.write(html.encode("utf-8"))
                else:
                    self.send_response(200)
                    self.end_headers()

            def do_POST(self):
                parsed = urllib.parse.urlparse(self.path)
                if parsed.path == "/auth/tokens":
                    length = int(self.headers.get("Content-Length", 0))
                    body = self.rfile.read(length).decode("utf-8")
                    params = urllib.parse.parse_qs(body)

                    access_token = params.get("access_token", [None])[0]
                    refresh_token = params.get("refresh_token", [None])[0]
                    expires_in = params.get("expires_in", ["3600"])[0]

                    self.send_response(200)
                    self.send_header("Content-Type", "text/plain")
                    self.end_headers()
                    self.wfile.write(b"ok")

                    if access_token:
                        # Build a result dict matching the verify_otp response shape
                        # so _on_session_received can handle it uniformly
                        try:
                            user_data = manager._client.get_user(access_token)
                        except Exception:
                            user_data = {}
                        result = {
                            "access_token": access_token,
                            "refresh_token": refresh_token,
                            "expires_in": int(expires_in),
                            "user": user_data,
                        }
                        # Signal delivers to main thread via Qt queued connection
                        manager._oauth_result.emit(result)
                    else:
                        manager._oauth_error.emit(
                            "Google sign-in failed — no access token received."
                        )

                    # Signal the server to stop
                    done_event.set()
                else:
                    self.send_response(404)
                    self.end_headers()

            def log_message(self, format, *args):
                pass  # Suppress console output

        try:
            server = HTTPServer(("127.0.0.1", port), _CallbackHandler)
        except OSError:
            self.auth_error.emit(f"Could not start OAuth listener on port {port}.")
            return

        def _serve():
            server.timeout = 1  # Check done_event every second
            deadline = time.time() + CFG.OAUTH_POLL_TIMEOUT / 1000
            while not done_event.is_set() and time.time() < deadline:
                server.handle_request()
            server.server_close()

        t = threading.Thread(target=_serve, daemon=True)
        t.start()

    def sign_out(self):
        """Sign out — clear local session and invalidate server-side."""
        self.log_event("sign_out")
        self._unregister_session()
        token = self.get_access_token()
        if token:
            # Best-effort server logout (don't block on failure)
            try:
                self._client.sign_out(token)
            except Exception:
                pass

        self._clear_session()
        self.auth_state_changed.emit(False)

    def sign_out_all_devices(self):
        """Sign out from ALL devices — invalidates every refresh token globally."""
        token = self.get_access_token()
        if not token or not self._user:
            return

        self.log_event("sign_out_all_devices")
        user_id = self._user.get("id", "")

        # 1. Delete ALL user_sessions rows for this user
        if user_id:
            try:
                self._client.delete(
                    "user_sessions", token,
                    f"user_id=eq.{user_id}",
                )
            except Exception:
                pass

        # 2. Supabase global sign-out — invalidates ALL refresh tokens
        try:
            self._client.sign_out(token, scope="global")
        except Exception:
            pass

        # 3. Clear local session
        self._clear_session()
        self.auth_state_changed.emit(False)

    def is_signed_in(self) -> bool:
        return self._access_token is not None

    def get_user(self):
        """Return ``{id, email}`` or ``None``."""
        return dict(self._user) if self._user else None

    def get_access_token(self):
        """Return the current access token, or ``None``."""
        with self._token_lock:
            return self._access_token

    def get_token_snapshot(self):
        """Return ``(access_token, refresh_token, expires_at)`` atomically.

        Safe to call from any thread. Used by the library manager to check
        token validity without reaching into private attributes.
        """
        with self._token_lock:
            return (self._access_token, self._refresh_token, self._expires_at)

    # ------------------------------------------------------------------
    # Worker helpers
    # ------------------------------------------------------------------

    def _run_worker(self, fn, on_success):
        """Spin up an _AuthWorker, connecting success/error handlers."""
        # If a previous worker is still running, let it finish
        if self._worker is not None and self._worker.isRunning():
            try:
                self._worker.finished.disconnect()
                self._worker.error.disconnect()
            except RuntimeError:
                pass  # No connections to disconnect

        worker = _AuthWorker(fn)
        worker.finished.connect(on_success)
        worker.error.connect(self._on_error)
        worker.finished.connect(lambda: self._cleanup_worker(worker))
        worker.error.connect(lambda: self._cleanup_worker(worker))
        self._worker = worker
        worker.start()

    def _cleanup_worker(self, worker):
        """Allow the worker to be garbage-collected after it finishes."""
        if self._worker is worker:
            self._worker = None

    # ------------------------------------------------------------------
    # Callbacks
    # ------------------------------------------------------------------

    def _on_otp_sent(self, _result: dict):
        self.otp_sent.emit()

    def _on_session_received(self, result: dict):
        """Handle a successful verify/refresh response."""
        # Clean up any existing session before processing the new one
        # (prevents orphaned user_sessions rows on account switch)
        if self._access_token:
            self._unregister_session()
            try:
                self._client.sign_out(self._access_token)
            except Exception:
                pass
            self._clear_session()

        with self._token_lock:
            self._access_token = result.get("access_token")
            self._refresh_token = result.get("refresh_token")
            expires_in = result.get("expires_in", 3600)
            self._expires_at = time.time() + expires_in

        user_data = result.get("user", {})
        meta = user_data.get("user_metadata", {})
        self._user = {
            "id": user_data.get("id", ""),
            "email": user_data.get("email", ""),
            "display_name": meta.get("full_name") or meta.get("name") or "",
            "avatar_url": meta.get("avatar_url") or meta.get("picture") or "",
        }

        # Multi-session: register this device session (reuse stable device ID)
        if not self._session_id:
            self._session_id = str(uuid.uuid4())
        self._register_session()
        self._heartbeat_timer.start(CFG.SESSION_HEARTBEAT_INTERVAL)

        # Ensure a user_profiles row exists (upsert — works for both OTP and Google OAuth)
        self._upsert_profile(user_data)

        self._save_session()
        self._schedule_refresh()
        self.auth_state_changed.emit(True)
        self.log_event("sign_in")

    def _on_error(self, message: str):
        self.auth_error.emit(message)

    # ------------------------------------------------------------------
    # Token persistence
    # ------------------------------------------------------------------

    def _load_stored_session(self):
        """Restore session from disk. If the token is expired, auto-refresh."""
        prefs = _read_auth_prefs()
        if not prefs.get("access_token"):
            return

        with self._token_lock:
            self._access_token = prefs["access_token"]
            self._refresh_token = prefs.get("refresh_token")
            self._expires_at = prefs.get("expires_at", 0)
        self._session_id = prefs.get("session_id")
        self._user = {
            "id": prefs.get("user_id", ""),
            "email": prefs.get("user_email", ""),
            "display_name": prefs.get("display_name", ""),
            "avatar_url": prefs.get("avatar_url", ""),
        }

        # Token still valid — schedule refresh and start heartbeat
        if time.time() < self._expires_at:
            self._schedule_refresh()
            if self._session_id:
                self._heartbeat_timer.start(CFG.SESSION_HEARTBEAT_INTERVAL)
        elif self._refresh_token:
            # Expired — try to refresh immediately
            self._auto_refresh()
        else:
            # No refresh token — session is dead
            self._clear_session()

    def _save_session(self):
        with self._token_lock:
            access = self._access_token
            refresh = self._refresh_token
            expires = self._expires_at
        _write_auth_prefs({
            "access_token": access,
            "refresh_token": refresh,
            "expires_at": expires,
            "session_id": self._session_id,
            "user_id": self._user.get("id", "") if self._user else "",
            "user_email": self._user.get("email", "") if self._user else "",
            "display_name": self._user.get("display_name", "") if self._user else "",
            "avatar_url": self._user.get("avatar_url", "") if self._user else "",
        })

    def _clear_session(self):
        self._refresh_timer.stop()
        self._heartbeat_timer.stop()
        with self._token_lock:
            self._access_token = None
            self._refresh_token = None
            self._expires_at = 0.0
        self._session_id = None
        self._user = None
        _delete_auth_prefs()

    # ------------------------------------------------------------------
    # Auto-refresh
    # ------------------------------------------------------------------

    def _schedule_refresh(self):
        """Start a single-shot timer to refresh the token before expiry."""
        remaining = self._expires_at - time.time() - CFG.TOKEN_REFRESH_MARGIN
        if remaining > 0:
            self._refresh_timer.start(int(remaining * 1000))
        elif self._refresh_token:
            # Already past the margin — refresh now
            self._auto_refresh()

    def _auto_refresh(self):
        """Refresh the access token using the stored refresh token."""
        # Capture token under lock so the closure uses a stable value
        with self._token_lock:
            refresh_tok = self._refresh_token

        if not refresh_tok:
            self._clear_session()
            self.auth_state_changed.emit(False)
            return

        if not CFG.SUPABASE_URL or not CFG.SUPABASE_ANON_KEY:
            return

        def _do():
            return self._client.refresh_session(refresh_tok)

        def _on_refresh_success(result):
            # Token refresh only updates credentials — no new session row
            with self._token_lock:
                self._access_token = result.get("access_token")
                self._refresh_token = result.get("refresh_token")
                expires_in = result.get("expires_in", 3600)
                self._expires_at = time.time() + expires_in
            self._save_session()
            self._schedule_refresh()

        def _on_refresh_fail(message):
            # Refresh failed — session is dead
            self._clear_session()
            self.auth_state_changed.emit(False)

        worker = _AuthWorker(_do)
        worker.finished.connect(_on_refresh_success)
        worker.error.connect(_on_refresh_fail)
        worker.finished.connect(lambda: self._cleanup_worker(worker))
        worker.error.connect(lambda: self._cleanup_worker(worker))
        self._worker = worker
        worker.start()

    # ------------------------------------------------------------------
    # Multi-session tracking
    # ------------------------------------------------------------------

    def _get_device_info(self):
        """Return a human-readable device string for session tracking."""
        maya_ver = ""
        try:
            import maya.cmds as cmds
            maya_ver = cmds.about(version=True)
        except Exception:
            pass
        os_name = platform.system()
        parts = [f"Maya {maya_ver}" if maya_ver else "Maya", os_name]
        return " / ".join(parts)

    def _register_session(self):
        """Upsert a row into user_sessions for this device (fire-and-forget).

        Uses upsert keyed on ``session_id`` so the same device always
        occupies a single row instead of accumulating duplicates.
        """
        token = self.get_access_token()
        if not token or not self._user or not self._session_id:
            return
        user_id = self._user.get("id", "")
        if not user_id:
            return

        now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()
        body = {
            "user_id": user_id,
            "session_id": self._session_id,
            "device_info": self._get_device_info(),
            "host_app": "maya",
            "last_active_at": now_iso,
        }

        def _do():
            self._client.upsert("user_sessions", token, body)
            return {}

        self._fire_and_forget(_do)

    def _upsert_profile(self, user_data: dict):
        """Ensure a row exists in the user_profiles table.

        For Google OAuth, *user_data* contains ``user_metadata`` with
        ``full_name`` and ``avatar_url`` which we use for display_name
        and avatar_url.

        Tracked in _fire_and_forget_workers for lifecycle management — a
        missing profile breaks library and purchasing features.
        """
        token = self.get_access_token()
        if not token or not self._user:
            return
        user_id = self._user.get("id", "")
        if not user_id:
            return

        meta = user_data.get("user_metadata", {})
        body = {
            "id": user_id,
            "email": self._user.get("email", ""),
            "display_name": meta.get("full_name") or meta.get("name"),
            "avatar_url": meta.get("avatar_url") or meta.get("picture"),
        }
        # Strip None values so we don't overwrite existing data with null
        body = {k: v for k, v in body.items() if v is not None}

        def _do():
            self._client.upsert("user_profiles", token, body)
            return {}

        def _on_fail(msg):
            print(f"[AuthManager] Profile upsert failed: {msg}")
            self.profile_error.emit(f"Profile setup failed: {msg}")

        worker = _AuthWorker(_do)
        worker.finished.connect(lambda: self._remove_ff_worker(worker))
        worker.error.connect(_on_fail)
        worker.error.connect(lambda: self._remove_ff_worker(worker))
        self._fire_and_forget_workers.append(worker)
        worker.start()

    def _unregister_session(self):
        """Remove this device's row from user_sessions (fire-and-forget)."""
        token = self.get_access_token()
        sid = self._session_id
        if not token or not sid:
            return

        def _do():
            self._client.delete(
                "user_sessions", token,
                f"session_id=eq.{sid}",
            )
            return {}

        self._fire_and_forget(_do)

    # ------------------------------------------------------------------
    # Session heartbeat & device management
    # ------------------------------------------------------------------

    def _send_heartbeat(self):
        """Update last_active_at on the current session row (fire-and-forget)."""
        token = self.get_access_token()
        sid = self._session_id
        if not token or not sid:
            return
        now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()

        def _do():
            self._client.update(
                "user_sessions", token,
                f"session_id=eq.{sid}",
                {"last_active_at": now_iso},
            )
            return {}

        self._fire_and_forget(_do)

    def fetch_user_sessions(self):
        """Fetch all active sessions for the current user (async)."""
        token = self.get_access_token()
        if not token or not self._user:
            return
        user_id = self._user.get("id", "")
        if not user_id:
            return

        def _do():
            result = self._client.query(
                "user_sessions", token,
                f"select=session_id,device_info,host_app,created_at,last_active_at"
                f"&user_id=eq.{user_id}"
                f"&order=last_active_at.desc",
            )
            return {"sessions": result if isinstance(result, list) else []}

        def _on_success(result):
            self.sessions_loaded.emit(result.get("sessions", []))

        def _on_fail(msg):
            self.sessions_error.emit(msg)

        worker = _AuthWorker(_do)
        worker.finished.connect(_on_success)
        worker.error.connect(_on_fail)
        worker.finished.connect(lambda: self._remove_ff_worker(worker))
        worker.error.connect(lambda: self._remove_ff_worker(worker))
        self._fire_and_forget_workers.append(worker)
        worker.start()

    def sign_out_device(self, session_id: str):
        """Sign out a specific device by deleting its session row (async)."""
        token = self.get_access_token()
        if not token:
            return

        def _do():
            self._client.delete(
                "user_sessions", token,
                f"session_id=eq.{session_id}",
            )
            return {"session_id": session_id}

        def _on_success(result):
            self.device_signed_out.emit(result.get("session_id", session_id))

        def _on_fail(msg):
            self.sessions_error.emit(f"Failed to sign out device: {msg}")

        worker = _AuthWorker(_do)
        worker.finished.connect(_on_success)
        worker.error.connect(_on_fail)
        worker.finished.connect(lambda: self._remove_ff_worker(worker))
        worker.error.connect(lambda: self._remove_ff_worker(worker))
        self._fire_and_forget_workers.append(worker)
        worker.start()

    # ------------------------------------------------------------------
    # Telemetry
    # ------------------------------------------------------------------

    def log_event(self, event: str):
        """Log a usage event to ``user_activity``. Fire-and-forget."""
        token = self.get_access_token()
        if not token or not self._user:
            return
        try:
            maya_ver = ""
            try:
                import maya.cmds as cmds
                maya_ver = cmds.about(version=True)
            except Exception:
                pass

            import ft_anim_picker.src as _pkg
            body = {
                "user_id": self._user.get("id", ""),
                "event": event,
                "addon_version": getattr(_pkg, "__version__", ""),
                "blender_version": maya_ver,
                "platform": platform.system().lower(),
                "country": locale.getdefaultlocale()[0] or "",
                "host_app": "maya",
            }

            def _do():
                self._client.insert("user_activity", token, body)
                return {}

            self._fire_and_forget(_do)
        except Exception:
            pass  # Telemetry must never break the app

    # ------------------------------------------------------------------
    # Fire-and-forget worker helper
    # ------------------------------------------------------------------

    def _fire_and_forget(self, fn):
        """Run *fn* on a background thread with no result handling."""
        # Sweep finished workers to prevent unbounded growth
        self._fire_and_forget_workers = [
            w for w in self._fire_and_forget_workers if w.isRunning()
        ]
        worker = _AuthWorker(fn)
        worker.finished.connect(lambda: self._remove_ff_worker(worker))
        worker.error.connect(lambda: self._remove_ff_worker(worker))
        self._fire_and_forget_workers.append(worker)
        worker.start()

    def _remove_ff_worker(self, worker):
        """Remove a finished fire-and-forget worker from the list."""
        try:
            self._fire_and_forget_workers.remove(worker)
        except ValueError:
            pass
