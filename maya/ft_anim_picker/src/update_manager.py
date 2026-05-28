"""
Update Manager — Singleton for checking, downloading, and installing addon updates.

Dual-source strategy:
- **Primary**: Supabase Edge Functions (check-addon-update, generate-update-url)
- **Fallback**: GitHub Releases API (backward compat for bridge release)
"""

import hashlib
import json
import os
import platform
import re
import shutil
import ssl
import sys
import tempfile
import time
import urllib.request
import urllib.error
import zipfile

try:
    from PySide6.QtCore import QObject, QThread, Signal
except ImportError:
    from PySide2.QtCore import QObject, QThread, Signal

from .config import settings as CFG


# ---------------------------------------------------------------------------
# SSL helper (Maya's bundled Python has certificate issues)
# ---------------------------------------------------------------------------

def _get_ssl_context():
    """Get an SSL context that works in Maya's bundled Python."""
    try:
        from .supabase_client import _SSL_CTX
        return _SSL_CTX
    except Exception:
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        return ctx


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_addon_dir():
    """Return the addon root directory (parent of src/)."""
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _get_cache_path():
    return os.path.join(_get_addon_dir(), CFG.UPDATE_CACHE_FILE)


def _read_disk_cache():
    path = _get_cache_path()
    if os.path.isfile(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {}


def _write_disk_cache(data):
    path = _get_cache_path()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
    except Exception:
        pass


def parse_version(version_string):
    """Parse a version string like 'v3.1.0' into a comparable tuple of ints."""
    version = str(version_string).strip().lstrip("v")
    numbers = re.findall(r"\d+", version)
    return tuple(map(int, numbers)) if numbers else (0,)


def is_newer_version(latest, current):
    """Return True if *latest* is a newer version than *current*."""
    return parse_version(latest) > parse_version(current)


def _get_os_info():
    return f"{platform.system()} {platform.release()}"


def _get_host_version():
    try:
        import maya.cmds as cmds
        return f"Maya {cmds.about(version=True)}"
    except Exception:
        return "Maya (unknown)"


# ---------------------------------------------------------------------------
# Background worker
# ---------------------------------------------------------------------------

class _UpdateWorker(QThread):
    """Runs a callable on a background thread and emits the result."""
    finished = Signal(object)
    error = Signal(str)

    def __init__(self, fn, *args):
        super().__init__()
        self._fn = fn
        self._args = args

    def run(self):
        try:
            result = self._fn(*self._args)
            self.finished.emit(result if result is not None else {})
        except Exception as exc:
            import traceback
            traceback.print_exc()
            self.error.emit(str(exc))


# ---------------------------------------------------------------------------
# UpdateManager (singleton)
# ---------------------------------------------------------------------------

class UpdateManager(QObject):
    """
    Singleton managing addon version checks, downloads, and installation.

    Signals
    -------
    update_available(dict)
        Emitted when a newer version is found. Payload contains release info:
        {version, channel, changelog, release_notes, is_critical, file_size, file_hash, source}
    no_update(str)
        Emitted when current version is up to date. Payload is current version.
    update_check_failed(str)
        Emitted when version check fails. Payload is error message.
    download_started()
        Emitted when a download begins.
    download_progress(int, int)
        Emitted during download: bytes_done, total_bytes.
    download_completed(str)
        Emitted on successful download + install. Payload is version string.
    download_failed(str)
        Emitted on download failure. Payload is error message.
    """

    update_available = Signal(dict)
    no_update = Signal(str)
    update_check_failed = Signal(str)
    download_started = Signal()
    download_progress = Signal(int, int)
    download_completed = Signal(str)
    download_failed = Signal(str)

    _instance = None

    @classmethod
    def get_instance(cls):
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    @classmethod
    def reset_instance(cls):
        cls._instance = None

    def __init__(self):
        super().__init__()
        self._client = None
        self._check_worker = None
        self._download_worker = None
        self._ff_workers = []  # fire-and-forget workers

        # Cache
        self._release_cache = None  # latest release dict or None
        self._cache_ts = 0

        # Load disk cache for instant startup notification
        self._load_disk_cache()

    # ------------------------------------------------------------------
    # Client setup
    # ------------------------------------------------------------------

    def _get_client(self):
        """Lazily create SupabaseClient."""
        if self._client is None:
            from .supabase_client import SupabaseClient
            self._client = SupabaseClient(CFG.SUPABASE_URL, CFG.SUPABASE_ANON_KEY)
        return self._client

    def _get_user_token(self):
        """Get user token if authenticated, else None."""
        try:
            from .auth_manager import AuthManager
            am = AuthManager.get_instance()
            token, _, expires_at = am.get_token_snapshot()
            if token and expires_at and time.time() < expires_at:
                return token
        except Exception:
            pass
        return None

    # ------------------------------------------------------------------
    # Disk cache
    # ------------------------------------------------------------------

    def _load_disk_cache(self):
        cache = _read_disk_cache()
        release = cache.get("latest_release")
        ts = cache.get("last_check_ts", 0)
        if release and ts:
            self._release_cache = release
            self._cache_ts = ts

    def _save_disk_cache(self, release):
        cache = _read_disk_cache()
        cache["latest_release"] = release
        cache["last_check_ts"] = time.time()
        _write_disk_cache(cache)

    def get_channel(self):
        """Return the user's preferred update channel."""
        cache = _read_disk_cache()
        return cache.get("channel", CFG.UPDATE_CHANNEL)

    def set_channel(self, channel):
        """Persist channel preference."""
        cache = _read_disk_cache()
        cache["channel"] = channel
        _write_disk_cache(cache)

    def get_dismissed_version(self):
        cache = _read_disk_cache()
        return cache.get("dismissed_version")

    def set_dismissed_version(self, version):
        cache = _read_disk_cache()
        cache["dismissed_version"] = version
        _write_disk_cache(cache)

    def get_auto_check(self):
        cache = _read_disk_cache()
        return cache.get("auto_check", True)

    def set_auto_check(self, enabled):
        cache = _read_disk_cache()
        cache["auto_check"] = enabled
        _write_disk_cache(cache)

    # ------------------------------------------------------------------
    # Version check
    # ------------------------------------------------------------------

    def check_for_update(self, force=False):
        """Check for available updates (async via background thread).

        If cache is fresh and *force* is False, emits from cache immediately.
        """
        # Check if auto-check is disabled (unless forced)
        if not force and not self.get_auto_check():
            return

        # Use cached result if still fresh
        if not force and self._release_cache and (time.time() - self._cache_ts < CFG.UPDATE_CHECK_TTL):
            self._emit_cached_result()
            return

        # Don't stack concurrent checks
        if self._check_worker and self._check_worker.isRunning():
            return

        self._check_worker = _UpdateWorker(self._check_sync)
        self._check_worker.finished.connect(self._on_check_finished)
        self._check_worker.error.connect(self._on_check_error)
        self._check_worker.start()

    def _emit_cached_result(self):
        """Emit update_available or no_update from cached data."""
        from . import __version__
        if self._release_cache and is_newer_version(
            self._release_cache.get("version", "0"), __version__
        ):
            self.update_available.emit(self._release_cache)
        else:
            self.no_update.emit(__version__)

    def _check_sync(self):
        """Synchronous version check — runs on background thread.

        Tries Supabase first, falls back to GitHub API.
        """
        from . import __version__
        channel = self.get_channel()

        # --- Try Supabase ---
        try:
            client = self._get_client()
            body = {
                "current_version": __version__,
                "platform": CFG.UPDATE_PLATFORM,
                "channel": channel,
                "host_version": _get_host_version(),
                "os_info": _get_os_info(),
            }
            user_token = self._get_user_token()
            resp = client.invoke("check-addon-update", user_token or "", body)

            if resp.get("update_available"):
                release = {
                    "version": resp["version"],
                    "channel": resp.get("channel", "stable"),
                    "changelog": resp.get("changelog", ""),
                    "release_notes": resp.get("release_notes", ""),
                    "is_critical": resp.get("is_critical", False),
                    "file_size": resp.get("file_size", 0),
                    "file_hash": resp.get("file_hash", ""),
                    "source": "supabase",
                }
                return release
            else:
                return {"no_update": True, "source": "supabase"}

        except Exception as e:
            print(f"[UpdateManager] Supabase check failed, trying GitHub: {e}")

        # --- Fallback: GitHub API ---
        return self._github_check_sync(__version__)

    def _github_check_sync(self, current_version):
        """Check GitHub releases as fallback."""
        LAST_AVAILABLE_VERSION = "1.7.0"
        try:
            repo_url = CFG.GITHUB_URL
            if repo_url.endswith(".git"):
                repo_url = repo_url[:-4]
            parts = repo_url.replace("https://github.com/", "").split("/")
            owner, repo = parts[0], parts[1]

            api_url = f"https://api.github.com/repos/{owner}/{repo}/releases"
            headers = {"User-Agent": "BgenPicker/3.0"}
            req = urllib.request.Request(api_url, headers=headers)

            with urllib.request.urlopen(req, timeout=10, context=_get_ssl_context()) as response:
                releases_data = json.loads(response.read().decode())

            if not releases_data:
                return {"no_update": True, "source": "github"}

            for release in releases_data:
                tag = release["tag_name"]
                if not is_newer_version(tag, LAST_AVAILABLE_VERSION):
                    continue
                if not is_newer_version(tag, current_version):
                    continue
                return {
                    "version": tag.lstrip("v"),
                    "channel": "stable",
                    "changelog": release.get("body", ""),
                    "release_notes": release.get("name", ""),
                    "is_critical": False,
                    "file_size": 0,
                    "file_hash": "",
                    "source": "github",
                }

            return {"no_update": True, "source": "github"}

        except Exception as e:
            raise RuntimeError(f"GitHub check also failed: {e}") from e

    def _on_check_finished(self, result):
        from . import __version__
        if result.get("no_update"):
            self._release_cache = None
            self._cache_ts = time.time()
            self._save_disk_cache(None)
            self.no_update.emit(__version__)
        else:
            self._release_cache = result
            self._cache_ts = time.time()
            self._save_disk_cache(result)
            self.update_available.emit(result)

    def _on_check_error(self, error_msg):
        if self._release_cache:
            self._emit_cached_result()
        else:
            self.update_check_failed.emit(error_msg)

    # ------------------------------------------------------------------
    # Download & install
    # ------------------------------------------------------------------

    def download_update(self, version):
        """Download and install the specified version (async)."""
        if self._download_worker and self._download_worker.isRunning():
            return

        self.download_started.emit()

        self._download_worker = _UpdateWorker(self._download_sync, version)
        self._download_worker.finished.connect(self._on_download_finished)
        self._download_worker.error.connect(self._on_download_error)
        self._download_worker.start()

    def _download_sync(self, version):
        """Synchronous download + install — runs on background thread."""
        from . import __version__

        # --- Try Supabase ---
        try:
            return self._supabase_download(version, __version__)
        except Exception as e:
            print(f"[UpdateManager] Supabase download failed, trying GitHub: {e}")

        # --- Fallback: GitHub ---
        return self._github_download(version, __version__)

    def _supabase_download(self, version, from_version):
        """Download from Supabase Storage via signed URL."""
        client = self._get_client()
        user_token = self._get_user_token()

        resp = client.invoke("generate-update-url", user_token or "", {
            "version": version,
            "platform": CFG.UPDATE_PLATFORM,
        })

        download_url = resp.get("url")
        expected_hash = resp.get("file_hash", "")
        if not download_url:
            raise RuntimeError("No download URL returned")

        addon_dir = _get_addon_dir()
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_zip = os.path.join(temp_dir, "update.zip")

            client.download_file(
                download_url,
                temp_zip,
                progress_callback=lambda done, total: self.download_progress.emit(done, total),
            )

            if expected_hash:
                actual_hash = hashlib.sha256(open(temp_zip, "rb").read()).hexdigest()
                if actual_hash != expected_hash:
                    raise RuntimeError(
                        f"Hash mismatch: expected {expected_hash[:12]}..., got {actual_hash[:12]}..."
                    )

            self._safe_extract_flat(temp_zip, addon_dir)

        self._record_event(from_version, version, "download_complete")
        return {"version": version, "source": "supabase"}

    def _github_download(self, version, from_version):
        """Download from GitHub releases (backward compat fallback)."""
        repo_url = CFG.GITHUB_URL
        if repo_url.endswith(".git"):
            repo_url = repo_url[:-4]
        parts = repo_url.replace("https://github.com/", "").split("/")
        owner, repo = parts[0], parts[1]

        tag = f"v{version}" if not version.startswith("v") else version
        release_url = f"https://api.github.com/repos/{owner}/{repo}/releases/tags/{tag}"
        headers = {"User-Agent": "BgenPicker/3.0"}
        req = urllib.request.Request(release_url, headers=headers)

        try:
            with urllib.request.urlopen(req, timeout=10, context=_get_ssl_context()) as response:
                release_data = json.loads(response.read().decode())
            if release_data.get("assets"):
                download_url = release_data["assets"][0]["browser_download_url"]
            else:
                download_url = f"https://github.com/{owner}/{repo}/archive/refs/tags/{tag}.zip"
        except Exception:
            download_url = f"https://github.com/{owner}/{repo}/archive/refs/tags/{tag}.zip"

        addon_dir = _get_addon_dir()
        parent_dir = os.path.dirname(addon_dir)

        with tempfile.TemporaryDirectory() as temp_dir:
            temp_zip = os.path.join(temp_dir, "release.zip")

            # Install SSL-aware opener for urlretrieve
            _ctx = _get_ssl_context()
            _opener = urllib.request.build_opener(
                urllib.request.HTTPSHandler(context=_ctx)
            )
            urllib.request.install_opener(_opener)

            def report_progress(block_count, block_size, total_size):
                if total_size > 0:
                    done = min(block_count * block_size, total_size)
                    self.download_progress.emit(done, total_size)

            urllib.request.urlretrieve(download_url, temp_zip, reporthook=report_progress)

            # GitHub ZIPs have nested structure: repo-tag/maya/ft_anim_picker/
            self._extract_github_zip(temp_zip, "maya/ft_anim_picker", parent_dir)

        self._record_event(from_version, version, "download_complete")
        return {"version": version, "source": "github"}

    def _safe_extract_flat(self, zip_path, addon_dir):
        """Extract a flat ZIP (ft_anim_picker/ at root) safely to addon_dir."""
        parent_dir = os.path.dirname(addon_dir)
        addon_name = os.path.basename(addon_dir)
        new_path = os.path.join(parent_dir, f"{addon_name}.new")
        bak_path = os.path.join(parent_dir, f"{addon_name}.bak")

        for p in (new_path, bak_path):
            if os.path.exists(p):
                shutil.rmtree(p)

        with tempfile.TemporaryDirectory() as temp_extract:
            with zipfile.ZipFile(zip_path, "r") as zf:
                zf.extractall(temp_extract)

            extracted = [d for d in os.listdir(temp_extract)
                         if os.path.isdir(os.path.join(temp_extract, d))]
            if not extracted:
                raise RuntimeError("No folder found in update ZIP")

            source = os.path.join(temp_extract, extracted[0])
            shutil.copytree(source, new_path)

        if os.path.exists(addon_dir):
            os.rename(addon_dir, bak_path)
        os.rename(new_path, addon_dir)
        if os.path.exists(bak_path):
            shutil.rmtree(bak_path, ignore_errors=True)

    def _extract_github_zip(self, zip_path, folder_path, output_parent):
        """Extract a specific folder from a GitHub release ZIP."""
        addon_name = os.path.basename(folder_path)
        output_path = os.path.join(output_parent, addon_name)
        new_path = os.path.join(output_parent, f"{addon_name}.new")
        bak_path = os.path.join(output_parent, f"{addon_name}.bak")

        for p in (new_path, bak_path):
            if os.path.exists(p):
                shutil.rmtree(p)

        with tempfile.TemporaryDirectory() as temp_extract:
            with zipfile.ZipFile(zip_path, "r") as zf:
                zf.extractall(temp_extract)

            extracted = [d for d in os.listdir(temp_extract)
                         if os.path.isdir(os.path.join(temp_extract, d))]
            if not extracted:
                raise RuntimeError("No folders found in extracted ZIP")

            repo_folder = os.path.join(temp_extract, extracted[0])
            source_folder = os.path.join(repo_folder, folder_path)

            if not os.path.exists(source_folder):
                raise RuntimeError(f"Folder '{folder_path}' not found in release")

            shutil.copytree(source_folder, new_path)

        if os.path.exists(output_path):
            os.rename(output_path, bak_path)
        os.rename(new_path, output_path)
        if os.path.exists(bak_path):
            shutil.rmtree(bak_path, ignore_errors=True)

    def _on_download_finished(self, result):
        version = result.get("version", "unknown")
        self.download_completed.emit(version)

    def _on_download_error(self, error_msg):
        self.download_failed.emit(error_msg)
        from . import __version__
        self._record_event(__version__, "unknown", "download_fail", error_msg)

    # ------------------------------------------------------------------
    # Analytics (fire-and-forget)
    # ------------------------------------------------------------------

    def _record_event(self, from_version, to_version, event_type, error_message=None):
        """Record an update event to Supabase (best-effort, non-blocking)."""
        def _do():
            try:
                client = self._get_client()
                body = {
                    "from_version": from_version,
                    "to_version": to_version,
                    "platform": CFG.UPDATE_PLATFORM,
                    "host_version": _get_host_version(),
                    "os_info": _get_os_info(),
                    "event_type": event_type,
                    "error_message": error_message,
                }
                client.insert("addon_update_events", client.anon_key, body)
            except Exception:
                pass

        worker = _UpdateWorker(_do)
        self._ff_workers.append(worker)
        worker.finished.connect(lambda: self._ff_workers.remove(worker) if worker in self._ff_workers else None)
        worker.error.connect(lambda: self._ff_workers.remove(worker) if worker in self._ff_workers else None)
        worker.start()

    # ------------------------------------------------------------------
    # Convenience
    # ------------------------------------------------------------------

    @property
    def cached_release(self):
        """Return the cached release dict (or None if no update available)."""
        return self._release_cache

    def get_current_version(self):
        from . import __version__
        return __version__
