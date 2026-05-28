"""
Library Manager — Singleton for browsing, purchasing, and downloading
library products.

Dual-mode architecture:
- **Online**: Fetches from Supabase Edge Functions, caches to memory + disk
- **Offline**: Falls back to disk cache, then shows "Store Offline" state
"""

import hashlib
import json
import os
import time
import tempfile
from PySide6.QtCore import QObject, QThread, Signal

from .config import settings as CFG


# ---------------------------------------------------------------------------
# Sort helpers
# ---------------------------------------------------------------------------

_SORT_KEYS = {
    "featured": lambda p: (not p.get("featured", False), -p.get("download_count", 0)),
    "newest": lambda p: p.get("id", ""),  # Mock: id order ≈ newest
    "price_low": lambda p: p.get("price_cents", 0),
    "price_high": lambda p: -p.get("price_cents", 0),
    "rating": lambda p: -p.get("rating_avg", 0),
    "downloads": lambda p: -p.get("download_count", 0),
}


# ---------------------------------------------------------------------------
# Background worker
# ---------------------------------------------------------------------------

class _BgenLibraryWorker(QThread):
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
# Disk cache helpers
# ---------------------------------------------------------------------------

def _get_addon_dir():
    """Return the addon root directory (parent of src/)."""
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _get_cache_path():
    return os.path.join(_get_addon_dir(), CFG.LIBRARY_CACHE_FILE)


def _get_thumbnail_dir():
    return os.path.join(_get_addon_dir(), CFG.LIBRARY_THUMBNAIL_DIR)


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


# ---------------------------------------------------------------------------
# BgenLocalFileManager (singleton)
# ---------------------------------------------------------------------------

class BgenLocalFileManager(QObject):
    """
    Singleton managing library product catalog, purchases, and downloads.

    Dual-mode: online (Supabase) with memory + disk cache, offline fallback.

    Signals
    -------
    catalog_updated()
        Emitted when the product catalog changes.
    purchase_completed(str)
        Emitted after a product is purchased. Payload is the product ID.
    sections_loaded(list)
        Emitted when explore page sections are resolved (remote or local).
    entitlements_checked(object)
        Emitted with the set of owned product IDs after a check.
    download_started(str)
        Emitted when a product download begins.
    download_progress(str, int, int)
        Emitted during download: product_id, bytes_done, total_bytes.
    download_completed(str, str)
        Emitted on successful download: product_id, library_path.
    download_failed(str, str)
        Emitted on download failure: product_id, error_message.
    feature_flags_loaded(dict)
        Emitted when feature flags are fetched from the server.
    store_offline()
        Emitted when server is unreachable and no cached data exists.
    """

    catalog_updated = Signal()
    purchase_completed = Signal(str)
    sections_loaded = Signal(list)
    entitlements_checked = Signal(object)
    download_started = Signal(str)
    download_progress = Signal(str, int, int)
    download_completed = Signal(str, str)
    download_failed = Signal(str, str)
    feature_flags_loaded = Signal(dict)
    store_offline = Signal()
    checkout_ready = Signal(dict, str)    # (stripe_data, product_id)
    cards_loaded = Signal(list)          # list of saved payment method dicts
    cards_error = Signal(str)
    card_removed = Signal(str)           # payment_method_id
    rating_submitted = Signal(str, int, float, int)  # product_id, rating, rating_avg, rating_count
    rating_failed = Signal(str, str)                  # product_id, error_message
    purchases_loaded = Signal(list)            # list of purchase dicts
    creators_loaded = Signal(list)             # list of creator dicts
    creator_profile_loaded = Signal(dict)      # {creator, products, is_following}
    follow_toggled = Signal(str, bool)         # creator_id, is_following

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

        # Supabase client (lazy — only created if configured)
        self._client = None

        # Memory cache + timestamps
        self._products_cache = []
        self._sections_cache = []
        self._owned_ids = set()
        self._feature_flags = {}
        self._creators_cache = []
        self._following_ids = set()
        self._cache_ts = {
            "products": 0,
            "sections": 0,
            "entitlements": 0,
            "feature_flags": 0,
            "creators": 0,
        }

        # Named workers (allows concurrent operations)
        self._workers = {}
        self._ff_workers = []  # fire-and-forget workers

        # Stripe checkout state
        self._checkout_product_id = None

        # Retry queue: operations deferred while token is being refreshed
        self._pending_retry = []  # list of (method_name, args, kwargs)
        self._retry_connected = False

        # Load from disk cache (no mock fallback — show "Store Offline" instead)
        self._load_initial_data()

    # ------------------------------------------------------------------
    # Initialisation
    # ------------------------------------------------------------------

    def _load_initial_data(self):
        """Load data from disk cache. Empty caches remain empty (offline)."""
        disk = _read_disk_cache()
        if disk.get("products"):
            self._products_cache = disk["products"]
            self._sections_cache = disk.get("sections", [])
            self._feature_flags = disk.get("feature_flags", {})
            self._owned_ids = set(disk.get("owned_ids", []))
            # Mark as semi-stale (30 s grace) so we refresh soon
            t = time.time() - CFG.LIBRARY_CACHE_TTL + 30
            self._cache_ts["products"] = t
            self._cache_ts["sections"] = t

    # ------------------------------------------------------------------
    # Client / auth helpers
    # ------------------------------------------------------------------

    def _get_client(self):
        """Lazily create the Supabase client."""
        if self._client is None and CFG.SUPABASE_URL and CFG.SUPABASE_ANON_KEY:
            from .supabase_client import SupabaseClient
            self._client = SupabaseClient(CFG.SUPABASE_URL, CFG.SUPABASE_ANON_KEY)
        return self._client

    def _get_token(self):
        """Get the current access token from AuthManager, or None.

        Uses ``get_token_snapshot()`` to read token state atomically.
        If the token is expired, triggers an async refresh via AuthManager
        and returns ``None`` — the caller should queue a retry via
        ``_defer_until_refresh()``.
        """
        try:
            from .auth_manager import AuthManager
            auth = AuthManager.get_instance()
            if not auth.is_signed_in():
                return None

            token, _refresh, expires_at = auth.get_token_snapshot()
            if not token:
                return None

            now = time.time()

            # expires_at is None or 0 means unknown — try to refresh
            if not expires_at:
                if _refresh:
                    auth._auto_refresh()
                    self._ensure_retry_connection()
                    return None
                # No refresh token and no expiry info — return token as last resort
                return token

            # Token still valid (with 30s safety margin)
            if now < expires_at - 30:
                return token

            # Token expired — trigger async refresh (non-blocking)
            if _refresh:
                auth._auto_refresh()
                self._ensure_retry_connection()

            # Expired token is useless — return None
            return None
        except Exception as e:
            print(f"[BgenLocalFileManager] _get_token: unexpected error: {e}")
            return None

    def _refresh_token_sync(self):
        """Synchronously refresh the access token. Returns new token or None.

        Safe to call from a worker thread.
        """
        try:
            from .auth_manager import AuthManager
            auth = AuthManager.get_instance()
            with auth._token_lock:
                refresh_tok = auth._refresh_token
            if not refresh_tok:
                return None

            client = self._get_client()
            if not client:
                return None

            result = client.refresh_session(refresh_tok)
            new_token = result.get("access_token")
            if new_token:
                with auth._token_lock:
                    auth._access_token = new_token
                    auth._refresh_token = result.get("refresh_token", refresh_tok)
                    auth._expires_at = time.time() + result.get("expires_in", 3600)
                auth._save_session()
            return new_token
        except Exception as e:
            print(f"[BgenLocalFileManager] Sync token refresh failed: {e}")
            return None

    def _ensure_retry_connection(self):
        """Connect to auth_state_changed once to drain the retry queue."""
        if self._retry_connected:
            return
        try:
            from .auth_manager import AuthManager
            auth = AuthManager.get_instance()
            auth.auth_state_changed.connect(self._on_auth_state_changed)
            self._retry_connected = True
        except Exception:
            pass

    def _on_auth_state_changed(self, signed_in):
        """Drain the retry queue when the user signs back in."""
        if not signed_in or not self._pending_retry:
            return
        pending = list(self._pending_retry)
        self._pending_retry.clear()
        for method_name, args, kwargs in pending:
            method = getattr(self, method_name, None)
            if method:
                try:
                    method(*args, **kwargs)
                except Exception as e:
                    print(f"[BgenLocalFileManager] Retry failed for {method_name}: {e}")

    def _defer_until_refresh(self, method_name, *args, **kwargs):
        """Queue an operation to be retried after token refresh completes."""
        # Deduplicate by method name (no need to queue the same fetch twice)
        if any(m == method_name for m, _, _ in self._pending_retry):
            return
        self._pending_retry.append((method_name, args, kwargs))

    def _is_cache_fresh(self, key):
        """Check if a cache entry is still within its TTL."""
        ttl_map = {
            "products": CFG.LIBRARY_CACHE_TTL,
            "sections": CFG.LIBRARY_CACHE_TTL,
            "entitlements": CFG.ENTITLEMENT_CACHE_TTL,
            "feature_flags": CFG.FEATURE_FLAG_CACHE_TTL,
            "creators": CFG.CREATOR_CACHE_TTL,
        }
        ttl = ttl_map.get(key, CFG.LIBRARY_CACHE_TTL)
        return (time.time() - self._cache_ts.get(key, 0)) < ttl

    def invalidate_all_caches(self):
        """Reset all cache timestamps so the next fetch hits the server."""
        self._cache_ts = {k: 0 for k in self._cache_ts}

    # ------------------------------------------------------------------
    # Worker helpers
    # ------------------------------------------------------------------

    def _run_worker(self, name, fn, on_success, on_error=None):
        """Run *fn* on a background thread under a named slot.

        If a worker with the same *name* is already running, its signal
        connections are severed (it keeps running but is ignored).
        """
        existing = self._workers.get(name)
        if existing and existing.isRunning():
            try:
                existing.finished.disconnect()
                existing.error.disconnect()
            except RuntimeError:
                pass

        worker = _BgenLibraryWorker(fn)
        worker.finished.connect(on_success)
        worker.error.connect(on_error or self._on_worker_error)
        worker.finished.connect(lambda: self._cleanup_worker(name, worker))
        worker.error.connect(lambda: self._cleanup_worker(name, worker))
        self._workers[name] = worker
        worker.start()

    def _fire_and_forget(self, fn):
        """Run *fn* on a background thread with no result handling."""
        # Sweep finished workers to prevent unbounded growth
        self._ff_workers = [w for w in self._ff_workers if w.isRunning()]
        worker = _BgenLibraryWorker(fn)
        worker.finished.connect(lambda _: self._remove_ff_worker(worker))
        worker.error.connect(lambda _: self._remove_ff_worker(worker))
        self._ff_workers.append(worker)
        worker.start()

    def _cleanup_worker(self, name, worker):
        if self._workers.get(name) is worker:
            del self._workers[name]

    def _remove_ff_worker(self, worker):
        try:
            self._ff_workers.remove(worker)
        except ValueError:
            pass

    def _on_worker_error(self, msg):
        print(f"[BgenLocalFileManager] Error: {msg}")

    # ------------------------------------------------------------------
    # Async fetchers (background thread → signal on completion)
    # ------------------------------------------------------------------

    def fetch_explore_layout(self, force=False):
        """Fetch the full Explore page layout from the server.

        On success, updates products, sections, and feature flags caches,
        then emits ``sections_loaded`` and ``feature_flags_loaded``.
        On failure, emits cached data if available, otherwise ``store_offline``.
        """
        if not force and self._is_cache_fresh("sections"):
            self.sections_loaded.emit(self._sections_cache)
            return

        client = self._get_client()
        if not client:
            self._emit_cached_or_offline()
            return

        def _do():
            # Public endpoint — always use anon key (no user auth needed)
            return client.invoke("fetch-explore-layout", client.anon_key, {})

        def _on_err(msg):
            self._emit_cached_or_offline()

        self._run_worker(
            "explore_layout", _do,
            on_success=self._on_explore_layout_fetched,
            on_error=_on_err,
        )

    def _on_explore_layout_fetched(self, data):
        """Handle successful explore layout response."""
        if not isinstance(data, dict) or not data.get("sections"):
            self._emit_cached_or_offline()
            return

        now = time.time()

        sections = data.get("sections", [])
        products = data.get("products", [])
        flags = data.get("feature_flags", {})
        creators = data.get("creators", [])

        if sections:
            self._sections_cache = sections
            self._cache_ts["sections"] = now

        if products:
            self._products_cache = products
            self._cache_ts["products"] = now

        if flags:
            self._feature_flags = flags
            self._cache_ts["feature_flags"] = now
            self.feature_flags_loaded.emit(self._feature_flags)

        if creators:
            self._creators_cache = creators
            self._cache_ts["creators"] = now

        self._save_to_disk()
        self.sections_loaded.emit(self._sections_cache)
        self.catalog_updated.emit()

        if creators:
            self.creators_loaded.emit(self._creators_cache)

    def _emit_cached_or_offline(self):
        """Emit cached sections if available, otherwise signal store offline."""
        if self._sections_cache:
            self.sections_loaded.emit(self._sections_cache)
        else:
            self.store_offline.emit()

    def fetch_feature_flags(self):
        """Fetch feature flags from the server."""
        if self._is_cache_fresh("feature_flags"):
            self.feature_flags_loaded.emit(self._feature_flags)
            return

        client = self._get_client()
        if not client:
            return

        def _do():
            return client.query(
                "library_feature_flags", client.anon_key,
                "select=key,value",
            )

        self._run_worker(
            "feature_flags", _do,
            on_success=self._on_flags_fetched,
        )

    def _on_flags_fetched(self, data):
        if not isinstance(data, list):
            return
        flags = {}
        for row in data:
            key = row.get("key")
            value = row.get("value")
            if key is not None:
                flags[key] = value
        self._feature_flags = flags
        self._cache_ts["feature_flags"] = time.time()
        self._save_to_disk()
        self.feature_flags_loaded.emit(self._feature_flags)

    def check_entitlements(self, product_ids=None, force=False):
        """Check which products the user owns.

        Emits ``entitlements_checked`` with the set of owned product IDs.
        """
        if not force and self._is_cache_fresh("entitlements"):
            self.entitlements_checked.emit(self._owned_ids)
            return

        token = self._get_token()
        if not token:
            # Token may be refreshing — queue a retry
            self._defer_until_refresh("check_entitlements", force=force, product_ids=product_ids)
            self.entitlements_checked.emit(self._owned_ids)
            return

        client = self._get_client()
        if not client:
            self.entitlements_checked.emit(self._owned_ids)
            return

        if product_ids is None:
            product_ids = [p.get("id") for p in self._products_cache if p.get("id")]

        def _do():
            return client.invoke("check-entitlements", token, {
                "product_ids": product_ids,
            })

        self._run_worker(
            "entitlements", _do,
            on_success=self._on_entitlements_checked,
        )

    def _on_entitlements_checked(self, data):
        if not isinstance(data, dict):
            return
        owned = data.get("owned_ids", [])
        self._owned_ids = set(owned)
        self._cache_ts["entitlements"] = time.time()
        self._save_to_disk()
        self.entitlements_checked.emit(self._owned_ids)
        self.catalog_updated.emit()

    # ------------------------------------------------------------------
    # Synchronous catalog queries (serve from memory cache)
    # ------------------------------------------------------------------

    def get_product_by_id(self, product_id):
        """Return a single product dict by ID, or None."""
        for p in self._products_cache:
            if p.get("id") == product_id:
                p["owned"] = p["id"] in self._owned_ids
                return p
        return None

    def get_products(self, category=None, search=None, sort="featured"):
        """Return a filtered and sorted list of product dicts from cache."""
        results = [p for p in self._products_cache if p.get("status") == "published"]

        if category and category != "All":
            results = [p for p in results if p.get("category", "").lower() == category.lower()]

        if search:
            q = search.lower()
            results = [
                p for p in results
                if q in p.get("name", "").lower()
                or q in p.get("creator", "").lower()
                or any(q in t for t in p.get("tags", []))
            ]

        key_fn = _SORT_KEYS.get(sort, _SORT_KEYS["featured"])
        results.sort(key=key_fn)

        for p in results:
            p["owned"] = p["id"] in self._owned_ids

        return results

    def get_featured_products(self):
        """Return featured products for the Explore page."""
        return [p for p in self.get_products(sort="featured") if p.get("featured")]

    def get_free_products(self):
        """Return free products for the Explore page."""
        return [p for p in self.get_products(sort="downloads") if p.get("price_cents", 0) == 0]

    def get_explore_sections(self):
        """Return cached explore sections (may be empty if offline).

        Call ``fetch_explore_layout()`` to trigger an async remote refresh.
        """
        return self._sections_cache

    def get_collection_by_slug(self, slug):
        """Return a collection dict by slug from cached sections, or None."""
        for section in self._sections_cache:
            if section.get("type") == "collection_grid":
                for coll in section.get("collections", []):
                    if coll.get("slug") == slug:
                        return coll
        return None

    def is_owned(self, product_id):
        """Check if the user owns a product."""
        return product_id in self._owned_ids

    def get_feature_flags(self):
        """Return a copy of the current feature flags."""
        return dict(self._feature_flags)

    def is_library_enabled(self):
        """Defaults to True (fail-open) if flag absent."""
        return bool(self._feature_flags.get(CFG.FF_LIBRARY_ENABLED, True))

    def get_min_version(self):
        """Defaults to '0.0.0' (no restriction) if flag absent."""
        return str(self._feature_flags.get(CFG.FF_LIBRARY_MIN_VERSION, "0.0.0"))

    def is_browse_auth_required(self):
        """Whether sign-in is required to browse the library. Defaults to False."""
        return bool(self._feature_flags.get(CFG.FF_LIBRARY_BROWSE_AUTH, False))

    # ------------------------------------------------------------------
    # Purchase flow
    # ------------------------------------------------------------------

    def initiate_purchase(self, product_id):
        """Start the purchase flow for a product.

        Creates a Stripe PaymentIntent, then opens an in-app checkout
        dialog with the Stripe Payment Element. On success, emits
        ``purchase_completed`` and auto-triggers ``download_product``.
        """
        token = self._get_token()
        if not token:
            self._on_worker_error("Please sign in to purchase")
            return

        client = self._get_client()
        if not client:
            return

        pid = product_id  # capture for closure

        def _do():
            return client.invoke("create-stripe-intent", token, {
                "product_id": pid,
            })

        self._run_worker(
            "purchase", _do,
            on_success=lambda data: self._on_intent_created(data, pid),
        )

    def _on_intent_created(self, data, product_id):
        if not isinstance(data, dict):
            return

        # Free products are handled server-side — no checkout needed
        if data.get("free") and data.get("owned"):
            self._owned_ids.add(product_id)
            self._cache_ts["entitlements"] = 0  # Invalidate so UI updates immediately
            self._save_to_disk()
            self.purchase_completed.emit(product_id)
            self.catalog_updated.emit()
            self.download_product(product_id)
            return

        if not data.get("client_secret") or not data.get("publishable_key"):
            self._on_worker_error("Payment setup failed — missing credentials")
            return

        # Emit signal so the UI navigates to the checkout page
        self._checkout_product_id = product_id
        self.checkout_ready.emit(data, product_id)

    def _on_stripe_success(self, payment_intent_id, product_id):
        """Handle successful Stripe payment — confirm server-side and trigger download."""
        token = self._get_token()
        client = self._get_client()
        if not token or not client:
            self._on_worker_error("Session expired — please sign in again")
            return

        pid = product_id
        pi_id = payment_intent_id

        def _do():
            return client.invoke("confirm-stripe-payment", token, {
                "payment_intent_id": pi_id,
                "product_id": pid,
            })

        self._run_worker(
            "purchase_confirm", _do,
            on_success=lambda data: self._on_stripe_confirmed(data, pid),
        )

    def _on_stripe_confirmed(self, data, product_id):
        """Handle server-side payment confirmation."""
        if not isinstance(data, dict):
            return

        status = data.get("status")
        if status == "completed":
            self._owned_ids.add(product_id)
            self._cache_ts["entitlements"] = 0
            self._save_to_disk()
            self.purchase_completed.emit(product_id)
            self.catalog_updated.emit()
            self.download_product(product_id)
        else:
            self._on_worker_error(
                f"Payment confirmation returned: {status}"
            )

    # ------------------------------------------------------------------
    # Saved payment methods
    # ------------------------------------------------------------------

    def fetch_saved_cards(self):
        """Fetch saved payment methods from Stripe via Edge Function."""
        token = self._get_token()
        client = self._get_client()
        if not token or not client:
            self.cards_loaded.emit([])
            return

        def _do():
            return client.invoke("manage-payment-methods", token, {
                "action": "list",
            })

        self._run_worker(
            "cards_list", _do,
            on_success=self._on_cards_loaded,
        )

    def _on_cards_loaded(self, data):
        if isinstance(data, dict):
            self.cards_loaded.emit(data.get("payment_methods", []))
        else:
            self.cards_loaded.emit([])

    def remove_saved_card(self, payment_method_id):
        """Remove (detach) a saved payment method."""
        token = self._get_token()
        client = self._get_client()
        if not token or not client:
            self.cards_error.emit("Session expired")
            return

        pm_id = payment_method_id

        def _do():
            return client.invoke("manage-payment-methods", token, {
                "action": "delete",
                "payment_method_id": pm_id,
            })

        self._run_worker(
            "cards_remove", _do,
            on_success=lambda data: self._on_card_removed(pm_id),
        )

    def _on_card_removed(self, payment_method_id):
        self.card_removed.emit(payment_method_id)
        # Auto-refresh the list
        self.fetch_saved_cards()

    # ------------------------------------------------------------------
    # Download flow
    # ------------------------------------------------------------------

    def download_product(self, product_id):
        """Download an owned product to the local library (bpicker) or
        system Downloads folder (other asset types).

        Emits ``download_started``, ``download_progress``, and
        ``download_completed`` or ``download_failed``.
        """
        token = self._get_token()
        client = self._get_client()

        if not token or not client:
            self.download_failed.emit(
                product_id,
                "Session expired \u2014 please sign in again" if not token else "Store offline",
            )
            return

        self.download_started.emit(product_id)
        pid = product_id  # capture for closure
        mgr = self  # capture for progress signal from thread

        # Look up product info for filename / category
        product = self.get_product_by_id(pid)
        product_name = (product or {}).get("name", pid) if product else pid
        product_category = (product or {}).get("category", "") if product else ""

        def _do():
            # 1. Get signed download URL
            result = client.invoke("generate-download-url", token, {
                "product_id": pid,
            })
            signed_url = result.get("url")
            file_name = result.get("file_name", "")
            if not signed_url:
                raise Exception("No download URL returned")

            # 2. Download to temp file
            tmp = tempfile.mktemp(suffix=".download")

            _last_progress_t = [0]
            def _progress(done, total):
                now = time.time()
                if now - _last_progress_t[0] < 0.1 and done < total:
                    return  # Throttle to max 10 updates/sec
                _last_progress_t[0] = now
                mgr.download_progress.emit(pid, done, total)

            client.download_file(signed_url, tmp, token, progress_callback=_progress)

            # 3. Determine if it's a bpicker (zip with manifest.json)
            import zipfile
            is_bpicker = False
            if zipfile.is_zipfile(tmp):
                try:
                    with zipfile.ZipFile(tmp, 'r') as zf:
                        is_bpicker = 'manifest.json' in zf.namelist()
                except Exception:
                    pass

            return {
                "product_id": pid,
                "tmp_path": tmp,
                "is_bpicker": is_bpicker,
                "file_name": file_name,
            }

        def _on_download_success(data):
            if not isinstance(data, dict):
                return
            tmp = data.get("tmp_path", "")
            is_bpicker = data.get("is_bpicker", False)

            if is_bpicker:
                # Rename temp file to a proper .bpicker name before importing
                import shutil
                proper_name = f"{product_name}.bpicker"
                # Sanitize filename
                for ch in r'<>:"/\|?*':
                    proper_name = proper_name.replace(ch, '_')
                proper_path = os.path.join(os.path.dirname(tmp), proper_name)
                try:
                    shutil.move(tmp, proper_path)
                except Exception:
                    proper_path = tmp  # fallback to temp name

                # Import into main library (alongside local pickers)
                try:
                    from .local_file_manager import LocalFileManager
                    lib = LocalFileManager.get_instance()
                    lib_path = lib.add_to_library(proper_path)
                except Exception as e:
                    self.download_failed.emit(pid, str(e))
                    return
                finally:
                    try:
                        if os.path.exists(proper_path):
                            os.remove(proper_path)
                    except OSError:
                        pass
                    try:
                        if os.path.exists(tmp):
                            os.remove(tmp)
                    except OSError:
                        pass
                # Inherit software tag from library product
                try:
                    sw = (product or {}).get("software", "")
                    if sw in ("blender", "maya"):
                        from . import bpicker_format as BPF
                        info = BPF.BPickerArchive.read(lib_path)
                        imported_uuid = info["metadata"].get("uuid", "")
                        if imported_uuid:
                            LocalFileManager.set_picker_software(imported_uuid, sw)
                except Exception:
                    pass  # non-critical — tagging failure shouldn't block download

                self.download_completed.emit(pid, str(lib_path))
            else:
                # Non-bpicker: move to configured Downloads folder
                try:
                    from .local_file_manager import LocalFileManager
                    downloads_dir = LocalFileManager.get_downloads_path()
                    downloads_dir.mkdir(parents=True, exist_ok=True)

                    # Use server-provided filename, or derive from product name
                    fname = data.get("file_name", "")
                    if not fname:
                        # Guess extension from file content or use generic
                        fname = f"{product_name}.zip"
                    dest = downloads_dir / fname
                    # Avoid overwriting
                    if dest.exists():
                        stem, suffix = dest.stem, dest.suffix
                        i = 1
                        while dest.exists():
                            dest = downloads_dir / f"{stem} ({i}){suffix}"
                            i += 1
                    import shutil
                    shutil.move(tmp, str(dest))
                except Exception as e:
                    self.download_failed.emit(pid, str(e))
                    return
                finally:
                    try:
                        if os.path.exists(tmp):
                            os.remove(tmp)
                    except OSError:
                        pass
                self.download_completed.emit(pid, str(dest))

        self._run_worker(
            "download", _do,
            on_success=_on_download_success,
            on_error=lambda msg: self.download_failed.emit(pid, msg),
        )

    # ------------------------------------------------------------------
    # Ratings
    # ------------------------------------------------------------------

    def submit_rating(self, product_id, rating, review=None):
        """Submit or update a star rating for a product.

        Uses the ``submit-rating`` edge function (service_role bypasses
        RLS, which fails with direct PostgREST when the JWT doesn't
        properly set ``auth.uid()``).  Emits
        ``rating_submitted(product_id, rating)`` on success.
        """
        token = self._get_token()
        client = self._get_client()
        if not token or not client:
            return

        pid, r = product_id, int(rating)

        def _do():
            body = {"product_id": pid, "rating": r}
            if review:
                body["review"] = review
            result = client.invoke("submit-rating", token, body)
            return {
                "product_id": pid,
                "rating": r,
                "rating_avg": result.get("rating_avg", 0) if isinstance(result, dict) else 0,
                "rating_count": result.get("rating_count", 0) if isinstance(result, dict) else 0,
            }

        self._run_worker(
            "rating", _do,
            on_success=lambda data: (
                self.rating_submitted.emit(
                    data["product_id"],
                    data["rating"],
                    float(data.get("rating_avg", 0)),
                    int(data.get("rating_count", 0)),
                ) if isinstance(data, dict) else None
            ),
            on_error=lambda msg: self.rating_failed.emit(pid, msg),
        )

    def fetch_user_rating(self, product_id, callback):
        """Fetch the current user's rating for a product.

        Calls ``callback(product_id, rating_or_none)`` on the main thread.
        """
        token = self._get_token()
        client = self._get_client()
        if not token or not client:
            callback(product_id, None)
            return

        from .auth_manager import AuthManager
        user = AuthManager.get_instance().get_user()
        if not user:
            callback(product_id, None)
            return

        pid = product_id
        uid = user["id"]

        def _do():
            rows = client.query(
                "library_ratings", token,
                f"select=rating,review&product_id=eq.{pid}&user_id=eq.{uid}",
            )
            if rows and len(rows) > 0:
                return {"product_id": pid, "rating": rows[0].get("rating")}
            return {"product_id": pid, "rating": None}

        worker = _BgenLibraryWorker(_do)
        worker.finished.connect(
            lambda data: callback(
                data.get("product_id", pid),
                data.get("rating"),
            ) if isinstance(data, dict) else callback(pid, None)
        )
        worker.error.connect(lambda _: callback(pid, None))
        worker.finished.connect(lambda _: self._remove_ff_worker(worker))
        worker.error.connect(lambda _: self._remove_ff_worker(worker))
        self._ff_workers.append(worker)
        worker.start()

    # ------------------------------------------------------------------
    # Purchase history
    # ------------------------------------------------------------------

    def fetch_purchases(self):
        """Fetch the current user's purchase history.

        Queries ``library_purchases`` joined with product info.
        Emits ``purchases_loaded(list)`` on success.
        """
        token = self._get_token()
        client = self._get_client()
        if not token or not client:
            return

        def _do():
            rows = client.query(
                "library_purchases", token,
                "select=id,product_id,price_paid_cents,status,download_count,"
                "created_at,library_products(id,name,slug,thumbnail_path,"
                "price_cents,currency,category)"
                "&status=eq.completed"
                "&order=created_at.desc",
            )
            purchases = []
            for row in (rows or []):
                prod = row.get("library_products") or {}
                thumb_path = prod.get("thumbnail_path", "")
                thumb_url = ""
                if thumb_path and CFG.SUPABASE_URL:
                    thumb_url = (
                        f"{CFG.SUPABASE_URL}/storage/v1/object/public/"
                        f"{CFG.LIBRARY_THUMBNAILS_BUCKET}/{thumb_path}"
                    )
                purchases.append({
                    "purchase_id": row.get("id", ""),
                    "product_id": row.get("product_id", ""),
                    "product_name": prod.get("name", "Unknown"),
                    "product_slug": prod.get("slug", ""),
                    "product_thumbnail_url": thumb_url,
                    "price_paid_cents": row.get("price_paid_cents", 0),
                    "currency": prod.get("currency", "USD"),
                    "category": prod.get("category", ""),
                    "status": row.get("status", ""),
                    "download_count": row.get("download_count", 0),
                    "purchased_at": row.get("created_at", ""),
                    "is_in_library": self._check_in_library(
                        row.get("product_id", "")
                    ),
                })
            return purchases

        self._run_worker(
            "purchases", _do,
            on_success=lambda data: self.purchases_loaded.emit(
                data if isinstance(data, list) else []
            ),
        )

    def _check_in_library(self, product_id):
        """Check if a product's .bpicker file exists in the library."""
        try:
            from .local_file_manager import LocalFileManager
            lib = LocalFileManager.get_instance()
            index = lib.get_index()
            for entry in index.get("pickers", []):
                if entry.get("uuid") == product_id:
                    return True
        except Exception:
            pass
        return False

    # ------------------------------------------------------------------
    # Thumbnail loading
    # ------------------------------------------------------------------

    def get_thumbnail_url(self, product):
        """Return the public thumbnail URL for a product.

        Uses the server-computed ``thumbnail_url`` field if available,
        otherwise falls back to constructing from ``thumbnail_path``.
        """
        # Server-computed URL (from fetch-explore-layout Edge Function)
        url = product.get("thumbnail_url")
        if url:
            return url

        # Fallback: construct from thumbnail_path or product ID
        path = product.get("thumbnail_path")
        if path and CFG.SUPABASE_URL:
            return (
                f"{CFG.SUPABASE_URL}/storage/v1/object/public/"
                f"{CFG.LIBRARY_THUMBNAILS_BUCKET}/{path}"
            )

        return ""

    def load_thumbnail_async(self, product_id, url, callback):
        """Download a thumbnail in the background.

        Checks the disk cache first. If fresh *and* URL-matched, calls
        ``callback`` immediately.  Otherwise downloads from *url* and
        caches to disk.  The cache key includes a short hash of the URL
        so changing the thumbnail in the DB invalidates stale files.

        Parameters
        ----------
        product_id : str
        url : str
            Public thumbnail URL.
        callback : callable
            ``callback(product_id, file_path)`` — called on the main thread.
        """
        thumb_dir = _get_thumbnail_dir()

        if not url:
            return

        # Build a URL-aware cache key: product_id + short hash of URL path.
        # When the thumbnail changes in the DB the URL changes, producing a
        # different hash and therefore a cache miss → fresh download.
        url_hash = hashlib.md5(url.encode()).hexdigest()[:8]
        cache_stem = f"{product_id}_{url_hash}"

        # Remove old-format files (product_id without hash) left from before
        for ext in (".png", ".jpg", ".jpeg", ".webp", ".img"):
            old_path = os.path.join(thumb_dir, f"{product_id}{ext}")
            if os.path.isfile(old_path):
                try:
                    os.remove(old_path)
                except OSError:
                    pass

        # Check disk cache (try common extensions)
        for ext in (".png", ".jpg", ".jpeg", ".webp", ".img"):
            candidate = os.path.join(thumb_dir, f"{cache_stem}{ext}")
            if os.path.isfile(candidate):
                age = time.time() - os.path.getmtime(candidate)
                if age < CFG.THUMBNAIL_CACHE_TTL:
                    callback(product_id, candidate)
                    return
                break  # stale — will be overwritten

        pid = product_id  # capture

        # Derive extension from URL, default to .img (QPixmap auto-detects)
        url_lower = url.rsplit("?", 1)[0].lower()
        if url_lower.endswith(".jpg") or url_lower.endswith(".jpeg"):
            ext = ".jpg"
        elif url_lower.endswith(".webp"):
            ext = ".webp"
        elif url_lower.endswith(".png"):
            ext = ".png"
        else:
            ext = ".img"
        save_path = os.path.join(thumb_dir, f"{cache_stem}{ext}")

        def _do():
            os.makedirs(thumb_dir, exist_ok=True)
            import urllib.request, tempfile, shutil
            # Download to temp file first, then rename to avoid
            # OSError on cloud-synced drives (Google Drive, OneDrive)
            fd, tmp_path = tempfile.mkstemp(dir=thumb_dir, suffix=ext)
            try:
                os.close(fd)
                urllib.request.urlretrieve(url, tmp_path)
                shutil.move(tmp_path, save_path)
            except Exception:
                try:
                    os.remove(tmp_path)
                except OSError:
                    pass
                raise
            return {"product_id": pid, "path": save_path}

        worker = _BgenLibraryWorker(_do)

        def _on_done(data):
            if isinstance(data, dict):
                callback(data.get("product_id", pid), data.get("path", ""))

        worker.finished.connect(_on_done)
        worker.error.connect(lambda _: None)  # Silently fail thumbnails
        worker.finished.connect(lambda _: self._remove_ff_worker(worker))
        worker.error.connect(lambda _: self._remove_ff_worker(worker))
        self._ff_workers.append(worker)
        worker.start()

    # ------------------------------------------------------------------
    # Disk cache persistence
    # ------------------------------------------------------------------

    def _save_to_disk(self):
        """Persist current cache state to disk."""
        _write_disk_cache({
            "products": self._products_cache,
            "sections": self._sections_cache,
            "feature_flags": self._feature_flags,
            "owned_ids": list(self._owned_ids),
            "saved_at": time.time(),
        })

    def clear_cache(self):
        """Clear all memory and disk caches, then re-fetch from server.

        Useful during development when you've changed data in the database
        and want to see updates immediately without waiting for TTL expiry.
        """
        self._products_cache = []
        self._sections_cache = []
        self._owned_ids = set()
        self._feature_flags = {}
        self._cache_ts = {k: 0 for k in self._cache_ts}

        # Delete data cache
        path = _get_cache_path()
        if os.path.isfile(path):
            try:
                os.remove(path)
            except OSError:
                pass

        # Delete thumbnail cache
        thumb_dir = _get_thumbnail_dir()
        if os.path.isdir(thumb_dir):
            import shutil
            try:
                shutil.rmtree(thumb_dir)
            except OSError:
                pass

        # Re-fetch from server
        self.fetch_explore_layout(force=True)

    # ------------------------------------------------------------------
    # Creator profile methods
    # ------------------------------------------------------------------

    def get_creators(self):
        """Return cached creator list (may be empty)."""
        return list(self._creators_cache)

    def is_following_creator(self, creator_id):
        """Check if the current user follows a creator (local cache)."""
        return creator_id in self._following_ids

    def fetch_creators(self, search=None, force=False):
        """Fetch approved creators from the server.

        Emits ``creators_loaded`` on success.
        """
        if not force and self._is_cache_fresh("creators") and self._creators_cache:
            self.creators_loaded.emit(self._creators_cache)
            return

        client = self._get_client()
        if not client:
            if self._creators_cache:
                self.creators_loaded.emit(self._creators_cache)
            return

        body = {}
        if search:
            body["search"] = search

        def _do():
            return client.invoke("fetch-creators", client.anon_key, body)

        self._run_worker(
            "creators", _do,
            on_success=self._on_creators_fetched,
        )

    def _on_creators_fetched(self, data):
        if not isinstance(data, dict):
            return
        creators = data.get("creators", [])
        self._creators_cache = creators
        self._cache_ts["creators"] = time.time()
        self.creators_loaded.emit(self._creators_cache)

    def fetch_creator_profile(self, creator_id):
        """Fetch a single creator's full profile + products.

        Emits ``creator_profile_loaded`` with
        ``{creator: {...}, products: [...], is_following: bool}``.
        """
        client = self._get_client()
        if not client:
            return

        token = self._get_token()
        auth_token = token or client.anon_key

        def _do():
            try:
                return client.invoke("fetch-creator-profile", auth_token, {
                    "creator_id": creator_id,
                })
            except Exception as e:
                if getattr(e, "status_code", 0) != 401 or auth_token == client.anon_key:
                    raise
                # 401 — try sync refresh, then anon key as last resort
                new_token = self._refresh_token_sync()
                if new_token:
                    try:
                        return client.invoke("fetch-creator-profile", new_token, {
                            "creator_id": creator_id,
                        })
                    except Exception:
                        pass  # refresh token also rejected — fall through
                return client.invoke("fetch-creator-profile", client.anon_key, {
                    "creator_id": creator_id,
                })

        def _on_done(data):
            if not isinstance(data, dict) or "creator" not in data:
                return
            # Update following state from response
            if data.get("is_following"):
                self._following_ids.add(creator_id)
            else:
                self._following_ids.discard(creator_id)
            self.creator_profile_loaded.emit(data)

        self._run_worker(
            "creator_profile", _do,
            on_success=_on_done,
        )

    def toggle_follow_creator(self, creator_id):
        """Toggle follow/unfollow for a creator.

        Requires auth. Emits ``follow_toggled(creator_id, is_following)``.
        """
        token = self._get_token()
        if not token:
            self._defer_until_refresh("toggle_follow_creator", creator_id)
            return

        client = self._get_client()
        if not client:
            return

        def _do():
            try:
                return client.invoke("toggle-follow-creator", token, {
                    "creator_id": creator_id,
                })
            except Exception as e:
                if getattr(e, "status_code", 0) != 401:
                    raise
                new_token = self._refresh_token_sync()
                if new_token:
                    return client.invoke("toggle-follow-creator", new_token, {
                        "creator_id": creator_id,
                    })
                raise

        def _on_done(data):
            if not isinstance(data, dict):
                return
            following = data.get("following", False)
            if following:
                self._following_ids.add(creator_id)
            else:
                self._following_ids.discard(creator_id)
            self.follow_toggled.emit(creator_id, following)

        def _on_error(msg):
            print(f"[BgenLocalFileManager] Follow error: {msg}")
            # Revert optimistic UI: emit current (pre-toggle) state
            was_following = creator_id in self._following_ids
            self.follow_toggled.emit(creator_id, was_following)

        self._run_worker(
            "toggle_follow", _do,
            on_success=_on_done,
            on_error=_on_error,
        )

    def load_creator_avatar_async(self, creator_id, url, callback):
        """Download a creator avatar to local cache, then call *callback*.

        Same pattern as ``load_thumbnail_async``.
        callback(creator_id, local_path)
        """
        if not url:
            return

        thumb_dir = _get_thumbnail_dir()
        cache_stem = f"creator_{hashlib.md5(url.encode()).hexdigest()[:12]}"

        # Check local cache
        for ext_try in (".jpg", ".png", ".webp", ".img"):
            candidate = os.path.join(thumb_dir, f"{cache_stem}{ext_try}")
            if os.path.isfile(candidate):
                age = time.time() - os.path.getmtime(candidate)
                if age < CFG.THUMBNAIL_CACHE_TTL:
                    callback(creator_id, candidate)
                    return
                break

        cid = creator_id  # capture

        url_lower = url.rsplit("?", 1)[0].lower()
        if url_lower.endswith(".jpg") or url_lower.endswith(".jpeg"):
            ext = ".jpg"
        elif url_lower.endswith(".webp"):
            ext = ".webp"
        elif url_lower.endswith(".png"):
            ext = ".png"
        else:
            ext = ".img"
        save_path = os.path.join(thumb_dir, f"{cache_stem}{ext}")

        def _do():
            os.makedirs(thumb_dir, exist_ok=True)
            import urllib.request, tempfile, shutil
            fd, tmp_path = tempfile.mkstemp(dir=thumb_dir, suffix=ext)
            try:
                os.close(fd)
                urllib.request.urlretrieve(url, tmp_path)
                shutil.move(tmp_path, save_path)
            except Exception:
                try:
                    os.remove(tmp_path)
                except OSError:
                    pass
                raise
            return {"creator_id": cid, "path": save_path}

        worker = _BgenLibraryWorker(_do)

        def _on_done(data):
            if isinstance(data, dict):
                callback(data.get("creator_id", cid), data.get("path", ""))

        worker.finished.connect(_on_done)
        worker.error.connect(lambda _: None)
        worker.finished.connect(lambda _: self._remove_ff_worker(worker))
        worker.error.connect(lambda _: self._remove_ff_worker(worker))
        self._ff_workers.append(worker)
        worker.start()

    # ------------------------------------------------------------------
    # Price formatting
    # ------------------------------------------------------------------

    def format_price(self, product):
        """Format a product's price for display."""
        cents = product.get("price_cents", 0)
        if cents == 0:
            return "Free"
        currency = product.get("currency", "USD")
        if currency == "USD":
            return f"${cents / 100:.2f}"
        return f"{cents / 100:.2f} {currency}"
