"""
Picker Session – Runtime bridge between .bpicker archives and PickerDataManager.

Each picker window holds one PickerSession.  The session:
  - Opens a .bpicker from the library → extracts to temp → feeds data into
    PickerDataManager for in-memory editing.
  - Tracks a *dirty* flag (set whenever PickerDataManager saves).
  - Auto-saves to the .bpicker archive after a debounce delay.
  - Captures a preview thumbnail of the canvas on save.
"""

import json
import os
import shutil
import time
from collections import OrderedDict
from datetime import datetime, timezone

try:
    from PySide6.QtCore import QTimer, Qt
    from PySide6.QtGui import QPixmap
except ImportError:
    from PySide2.QtCore import QTimer, Qt
    from PySide2.QtGui import QPixmap

from . import bpicker_format as BPF
from .local_file_manager import LocalFileManager


class PickerSession:
    """Manages the runtime state of a single opened picker."""

    AUTO_SAVE_DELAY_MS = 800        # 0.8 s debounce — short enough to survive scene changes / crashes
    BACKUP_INTERVAL_SEC = 300       # Only backup every 5 minutes for auto-saves

    def __init__(self):
        self.uuid = None
        self.bpicker_path = None        # Path in the library
        self.manifest = None             # In-memory manifest dict
        self.metadata = None             # In-memory metadata dict
        self._dirty = False
        self._temp_dir = None            # Extracted archive for media access
        self._media_cache = {}           # archive_rel_path → absolute temp path
        self._canvas_ref = None          # Reference to PickerCanvas for preview capture
        self._last_backup_time = 0       # Timestamp of last backup
        self._last_known_mtime = None    # mtime of .bpicker when last read/written

        # Differential repack state — what's in the archive on disk, and
        # which entries the next save must re-write. Manifest/metadata are
        # always re-written; thumbnails/backgrounds are stream-copied unless
        # explicitly marked dirty when the user adds new media.
        self._archive_index = {}            # arc_path -> (size, crc, compress_type)
        self._dirty_archive_paths = set()
        self._media_dirty = False           # True if any media was added since last save

        # UI callbacks (set by the main window)
        self._on_save_callback = None    # fn(auto: bool) – called after save completes
        self._on_dirty_callback = None   # fn() – called when dirty flag is set

        # Auto-save timer (debounced)
        self._auto_save_timer = QTimer()
        self._auto_save_timer.setSingleShot(True)
        self._auto_save_timer.timeout.connect(self._auto_save)

        # Live preview timer — lightweight card thumbnail refresh (in-memory only)
        self._preview_timer = QTimer()
        self._preview_timer.setSingleShot(True)
        self._preview_timer.setInterval(500)
        self._preview_timer.timeout.connect(self._update_live_preview)
        self._pending_preview = None  # QPixmap waiting to be flushed to disk

    # ------------------------------------------------------------------
    # Canvas reference (for preview capture)
    # ------------------------------------------------------------------

    def set_canvas(self, canvas_widget):
        """Store a reference to the PickerCanvas for preview capture."""
        self._canvas_ref = canvas_widget

    def schedule_preview_update(self):
        """Debounce a lightweight live preview refresh (no disk I/O)."""
        if self.metadata and self.metadata.get("custom_preview", False):
            return
        self._preview_timer.start()

    def _update_live_preview(self):
        """Grab the canvas and push pixmap to the library card widget (in-memory)."""
        if not self._canvas_ref or not self.uuid:
            return
        if self.metadata and self.metadata.get("custom_preview", False):
            return
        try:
            pixmap = self._canvas_ref.grab()
            if pixmap.isNull():
                return
            preview = pixmap.scaled(
                256, 256, Qt.KeepAspectRatio, Qt.SmoothTransformation
            )
            self._pending_preview = preview

            # Update the library card widget instantly
            from . import local_file_ui as LIB_UI
            controller = LIB_UI.LocalFilePageController.get_instance()
            if controller:
                card = controller._cards.get(self.uuid)
                if card and hasattr(card, 'set_preview'):
                    card.set_preview(preview)
        except Exception:
            pass  # Non-critical — card may not be visible

    def _flush_pending_preview(self):
        """Write the cached preview pixmap to the temp dir.

        Called just before save() or close() so the next repack includes it.
        """
        if self.metadata and self.metadata.get("custom_preview", False):
            self._pending_preview = None
            return
        if self._pending_preview and self._temp_dir:
            try:
                cache_dir = os.path.join(self._temp_dir, BPF.CACHE_DIR)
                os.makedirs(cache_dir, exist_ok=True)
                self._pending_preview.save(
                    os.path.join(cache_dir, "preview.png"), "PNG"
                )
            except Exception:
                pass
            self._pending_preview = None

    # ------------------------------------------------------------------
    # Create new picker
    # ------------------------------------------------------------------

    def create_new(self, name="Untitled Picker", author="", tool_version=""):
        """Create a brand-new picker, save to library, and set up session.

        Args:
            name: Picker name.
            author: Author string.
            tool_version: Addon version.

        Returns:
            str – the new picker UUID.
        """
        from . import __init__ as pkg
        tool_version = tool_version or getattr(pkg, "__version__", "")

        self.metadata = BPF.build_metadata(
            picker_name=name,
            author=author,
            tool_version=tool_version,
        )
        self.uuid = self.metadata["uuid"]

        # Minimal manifest with one empty tab
        self.manifest = {
            "manifest_version": BPF.MANIFEST_VERSION,
            "tabs": OrderedDict({
                "Tab 1": {
                    "buttons": [],
                    "background_layers": [],
                    "background_value": 20,
                    "namespace": "None",
                    "show_dots": False,
                    "show_axes": True,
                    "show_grid": True,
                    "grid_size": 50,
                }
            }),
        }

        # Ensure library exists
        LocalFileManager.ensure_library_exists()
        lib_path = LocalFileManager.get_library_path()

        # Build filename from name
        safe_name = self._safe_filename(name)
        dest = str(lib_path / f"{safe_name}.bpicker")

        # Avoid overwriting
        if os.path.exists(dest):
            i = 1
            while os.path.exists(dest):
                dest = str(lib_path / f"{safe_name}_{i}.bpicker")
                i += 1

        # Create the archive
        self.bpicker_path = BPF.BPickerArchive.create(
            dest_path=dest,
            manifest=self.manifest,
            metadata=self.metadata,
            media_files={},
        )

        # File is already in the library directory, just reindex
        LocalFileManager.reindex()

        # Extract to temp for media access
        self._temp_dir = BPF.BPickerArchive.extract_to_temp(self.bpicker_path)
        self._refresh_archive_index()
        self._dirty = False

        return self.uuid

    # ------------------------------------------------------------------
    # Open from library
    # ------------------------------------------------------------------

    def open_from_library(self, picker_uuid):
        """Load a .bpicker from the library by UUID.

        Args:
            picker_uuid: UUID of the picker in the library.

        Raises:
            FileNotFoundError if picker not in library.
        """
        path = LocalFileManager.get_picker_path(picker_uuid)
        if not path or not path.exists():
            raise FileNotFoundError(
                f"Picker with UUID {picker_uuid} not found in library"
            )

        self.bpicker_path = str(path)
        info = BPF.BPickerArchive.read(self.bpicker_path)
        self.manifest = info["manifest"]
        self.metadata = info["metadata"]
        self.uuid = self.metadata.get("uuid", picker_uuid)

        # Extract to temp for media access
        if self._temp_dir:
            shutil.rmtree(self._temp_dir, ignore_errors=True)
        self._temp_dir = BPF.BPickerArchive.extract_to_temp(self.bpicker_path)
        self._media_cache.clear()
        self._refresh_archive_index()
        self._dirty = False
        try:
            self._last_known_mtime = os.path.getmtime(self.bpicker_path)
        except OSError:
            self._last_known_mtime = None

    def open_from_path(self, bpicker_path):
        """Open a .bpicker file directly (e.g. after import).

        The file should already be in the library.
        """
        bpicker_path = str(bpicker_path)
        info = BPF.BPickerArchive.read(bpicker_path)
        self.manifest = info["manifest"]
        self.metadata = info["metadata"]
        self.uuid = self.metadata.get("uuid", "")
        self.bpicker_path = bpicker_path

        if self._temp_dir:
            shutil.rmtree(self._temp_dir, ignore_errors=True)
        self._temp_dir = BPF.BPickerArchive.extract_to_temp(bpicker_path)
        self._media_cache.clear()
        self._refresh_archive_index()
        self._dirty = False
        try:
            self._last_known_mtime = os.path.getmtime(self.bpicker_path)
        except OSError:
            self._last_known_mtime = None

    # ------------------------------------------------------------------
    # Save
    # ------------------------------------------------------------------

    def save(self, auto=False):
        """Save current state back to the .bpicker archive in the library.

        Args:
            auto: If True, this is an auto-save (skip backup unless enough
                  time has passed since the last one).
        """
        if not self.bpicker_path or not self._temp_dir:
            print("[PickerSession] No active session to save.")
            return

        # Check for external modification (multi-user safety)
        external_modification_detected = False
        if self._last_known_mtime is not None:
            try:
                current_mtime = os.path.getmtime(self.bpicker_path)
                if current_mtime != self._last_known_mtime:
                    if auto:
                        # Auto-save: skip and retry later to avoid overwriting
                        print("[PickerSession] File modified externally, "
                              "deferring auto-save")
                        self._auto_save_timer.start(self.AUTO_SAVE_DELAY_MS)
                        return
                    else:
                        print(f"[PickerSession] WARNING: "
                              f"'{os.path.basename(self.bpicker_path)}' was "
                              f"modified externally since last save")
                    external_modification_detected = True
            except OSError:
                pass  # File may have been deleted/moved

        # If the archive on disk diverged from our last snapshot, refresh the
        # index so the differential repack copies through from the *current*
        # central directory rather than a stale view.
        if external_modification_detected:
            self._refresh_archive_index()

        # Sync from PickerDataManager
        self.sync_from_scene()

        # Update metadata timestamps
        self.metadata["modified"] = datetime.now(timezone.utc).isoformat()

        # Write updated manifest and metadata to temp dir
        manifest_path = os.path.join(self._temp_dir, BPF.MANIFEST_NAME)
        with open(manifest_path, "w", encoding="utf-8") as f:
            json.dump(self.manifest, f, indent=2)

        meta_path = os.path.join(self._temp_dir, BPF.METADATA_NAME)
        with open(meta_path, "w", encoding="utf-8") as f:
            json.dump(self.metadata, f, indent=2)

        # Mark hot entries dirty (manifest/metadata always change on save).
        self._dirty_archive_paths.add(BPF.MANIFEST_NAME)
        self._dirty_archive_paths.add(BPF.METADATA_NAME)

        # Preview: on explicit save do a fresh capture; on auto-save just
        # flush any pending live-preview pixmap (no new grab).
        had_pending_preview = self._pending_preview is not None
        if not auto:
            self._capture_preview()
            self._dirty_archive_paths.add(BPF.CACHE_DIR + "/preview.png")
        else:
            self._flush_pending_preview()
            if had_pending_preview:
                self._dirty_archive_paths.add(BPF.CACHE_DIR + "/preview.png")

        # Backup: always on explicit save, throttled on auto-save
        now = time.time()
        if not auto or (now - self._last_backup_time) > self.BACKUP_INTERVAL_SEC:
            LocalFileManager.backup_picker(self.uuid)
            self._last_backup_time = now

        # Repack archive — incremental copies unchanged entries through
        # without recompressing. Falls back to full repack on failure.
        BPF.BPickerArchive.repack_incremental(
            self._temp_dir,
            self.bpicker_path,
            self.bpicker_path,
            dirty_paths=self._dirty_archive_paths,
        )

        # Track file mtime for external modification detection
        try:
            self._last_known_mtime = os.path.getmtime(self.bpicker_path)
        except OSError:
            self._last_known_mtime = None

        # Refresh archive snapshot for the next differential repack, and
        # clear per-save dirty bookkeeping.
        self._refresh_archive_index()
        self._dirty_archive_paths.clear()
        self._media_dirty = False

        # Update library index — patch one entry instead of rescanning every
        # .bpicker in the library. Full reindex still runs on rare paths
        # (rename, delete, library-path change, etc.).
        LocalFileManager.update_index_entry(
            self.uuid, self.metadata, self.manifest, self.bpicker_path
        )

        # Update scene link
        self._update_scene_link()

        # Set per-file OS icon (explicit saves only – skip auto-saves for perf)
        if not auto:
            self._set_os_file_icon()

        self._dirty = False
        if not auto:
            print(f"[PickerSession] Saved picker '{self.metadata.get('picker_name', '')}'")
        if self._on_save_callback:
            self._on_save_callback(auto)

    def save_as(self, new_name):
        """Save as a new picker with a new UUID.

        Returns:
            str – the new UUID.
        """
        if not self._temp_dir:
            print("[PickerSession] No active session to save.")
            return None

        # Sync current state
        self.sync_from_scene()

        # Generate new identity
        from . import __init__ as pkg
        tool_version = getattr(pkg, "__version__", "")

        self.uuid = BPF.generate_uuid()
        self.metadata["uuid"] = self.uuid
        self.metadata["picker_name"] = new_name
        self.metadata["custom_preview"] = False
        self.metadata["modified"] = datetime.now(timezone.utc).isoformat()
        self.metadata["tool_version"] = tool_version

        # Write updated manifest and metadata
        manifest_path = os.path.join(self._temp_dir, BPF.MANIFEST_NAME)
        with open(manifest_path, "w", encoding="utf-8") as f:
            json.dump(self.manifest, f, indent=2)

        meta_path = os.path.join(self._temp_dir, BPF.METADATA_NAME)
        with open(meta_path, "w", encoding="utf-8") as f:
            json.dump(self.metadata, f, indent=2)

        # Capture preview
        self._capture_preview()

        # Pack to new file in library
        lib_path = LocalFileManager.get_library_path()
        safe_name = self._safe_filename(new_name)
        dest = str(lib_path / f"{safe_name}.bpicker")
        if os.path.exists(dest):
            i = 1
            while os.path.exists(dest):
                dest = str(lib_path / f"{safe_name}_{i}.bpicker")
                i += 1

        self.bpicker_path = BPF.BPickerArchive.repack(self._temp_dir, dest)

        # Re-extract (repack consumed temp or wrote to new location)
        self._temp_dir = BPF.BPickerArchive.extract_to_temp(self.bpicker_path)
        self._refresh_archive_index()

        LocalFileManager.reindex()
        self._update_scene_link()
        self._set_os_file_icon()
        self._dirty = False
        if self._on_save_callback:
            self._on_save_callback(False)

        return self.uuid

    # ------------------------------------------------------------------
    # Close
    # ------------------------------------------------------------------

    def close(self):
        """Clean up temp directory, stop timers, and reset state."""
        # Stop all timers
        self._auto_save_timer.stop()
        self._preview_timer.stop()

        # Persist any pending live-preview before tearing down
        if self._pending_preview and self._temp_dir and self.bpicker_path:
            self._flush_pending_preview()
            try:
                BPF.BPickerArchive.repack(self._temp_dir, self.bpicker_path)
            except Exception:
                pass

        if self._temp_dir and os.path.isdir(self._temp_dir):
            shutil.rmtree(self._temp_dir, ignore_errors=True)
        self._temp_dir = None
        self._media_cache.clear()
        self._canvas_ref = None
        self.uuid = None
        self.bpicker_path = None
        self.manifest = None
        self.metadata = None
        self._dirty = False

    # ------------------------------------------------------------------
    # Dirty tracking & auto-save
    # ------------------------------------------------------------------

    def mark_dirty(self):
        """Called by PickerDataManager._perform_save() when data changes."""
        self._dirty = True
        if self._on_dirty_callback:
            self._on_dirty_callback()
        # Restart the debounce timer for auto-save (if enabled)
        if LocalFileManager.get_autosave_enabled():
            self._auto_save_timer.start(self.AUTO_SAVE_DELAY_MS)

    def is_dirty(self):
        return self._dirty

    def _auto_save(self):
        """Called by the debounce timer to auto-save the archive."""
        if not self._dirty:
            return
        try:
            self.save(auto=True)
        except Exception as e:
            print(f"[PickerSession] Auto-save failed: {e}")

    # ------------------------------------------------------------------
    # Preview capture
    # ------------------------------------------------------------------

    def _capture_preview(self):
        """Capture a screenshot of the canvas and save as preview.png."""
        if self.metadata and self.metadata.get("custom_preview", False):
            return
        if not self._canvas_ref or not self._temp_dir:
            return

        try:
            # Grab the canvas widget as a pixmap
            pixmap = self._canvas_ref.grab()
            if pixmap.isNull():
                return

            # Scale to a reasonable preview size
            preview = pixmap.scaled(
                256, 256,
                Qt.KeepAspectRatio,
                Qt.SmoothTransformation,
            )

            # Save to cache dir in temp
            cache_dir = os.path.join(self._temp_dir, BPF.CACHE_DIR)
            os.makedirs(cache_dir, exist_ok=True)
            preview_path = os.path.join(cache_dir, "preview.png")
            preview.save(preview_path, "PNG")
        except Exception as e:
            print(f"[PickerSession] Preview capture failed: {e}")

    # ------------------------------------------------------------------
    # Media path resolution
    # ------------------------------------------------------------------

    def get_media_path(self, archive_rel_path):
        """Resolve an archive-relative path to an absolute temp path.

        Args:
            archive_rel_path: Path like ``thumbnails/thumb_001.png``
                (with or without ``bpicker://`` prefix).

        Returns:
            str – absolute path in temp dir, or None.
        """
        if not self._temp_dir:
            return None

        # Strip prefix if present
        if archive_rel_path.startswith("bpicker://"):
            archive_rel_path = archive_rel_path[len("bpicker://"):]

        # Check cache
        if archive_rel_path in self._media_cache:
            cached = self._media_cache[archive_rel_path]
            if os.path.exists(cached):
                return cached

        # Resolve in temp dir
        resolved = os.path.join(
            self._temp_dir, archive_rel_path.replace("/", os.sep)
        )
        if os.path.exists(resolved):
            self._media_cache[archive_rel_path] = resolved
            return resolved

        return None

    def add_media_file(self, absolute_path, category="thumbnails"):
        """Copy a media file into the session temp dir.

        Args:
            absolute_path: Source file on disk.
            category: One of 'thumbnails', 'backgrounds', 'cache'.

        Returns:
            str – the archive-relative path (e.g. ``thumbnails/image.png``),
            prefixed with ``bpicker://`` for storage in PickerDataManager.
        """
        if not self._temp_dir or not os.path.isfile(absolute_path):
            return None

        filename = os.path.basename(absolute_path)
        dest_dir = os.path.join(self._temp_dir, category)
        os.makedirs(dest_dir, exist_ok=True)

        # Avoid collisions
        dest = os.path.join(dest_dir, filename)
        if os.path.exists(dest):
            stem, ext = os.path.splitext(filename)
            i = 1
            while os.path.exists(dest):
                dest = os.path.join(dest_dir, f"{stem}_{i}{ext}")
                filename = f"{stem}_{i}{ext}"
                i += 1

        shutil.copy2(absolute_path, dest)

        archive_rel = f"{category}/{filename}"
        self._media_cache[archive_rel] = dest
        self._dirty_archive_paths.add(archive_rel)
        self._media_dirty = True

        return f"bpicker://{archive_rel}"

    # ------------------------------------------------------------------
    # Scene sync
    # ------------------------------------------------------------------

    def sync_to_scene(self):
        """Write manifest data into PickerDataManager format for scene storage.

        This is called after opening a picker to populate the in-memory
        PickerDataManager with the archive's data.
        """
        from . import data_management as DM

        picker_data = BPF.build_picker_data_from_manifest(self.manifest)

        # Preserve per-scene view state (zoom/pan) from existing scene data
        # so reopening a .bpicker doesn't reset the camera position.
        existing = DM.PickerDataManager.get_data()
        existing_tabs = existing.get("tabs", {})
        _VIEW_KEYS = ("zoom_factor", "pan_offset_x", "pan_offset_y")
        for tab_name, tab_data in picker_data.get("tabs", {}).items():
            old_tab = existing_tabs.get(tab_name, {})
            for key in _VIEW_KEYS:
                if key in old_tab and key not in tab_data:
                    tab_data[key] = old_tab[key]

        # notify_session=False: loading is not a user edit, so don't
        # mark the session dirty or restart the .bpicker auto-save
        # timer. Without this, simply opening a picker queues an
        # archive repack and spams mark_dirty for every load-time
        # helper that touches save_data.
        DM.PickerDataManager.save_data(
            picker_data, force_immediate=True, notify_session=False
        )

        # Store scene link
        self._update_scene_link()

        # Register this session as active
        DM.PickerDataManager.set_active_session(self)

    def sync_from_scene(self):
        """Read current PickerDataManager data and update the manifest.

        Called before save to capture all edits made through the normal
        PickerDataManager pipeline.
        """
        from . import data_management as DM

        picker_data = DM.PickerDataManager.get_data()

        # Collect media mapping: find any new media files in temp
        media_mapping = self._build_media_mapping(picker_data)

        self.manifest = BPF.build_manifest_from_picker_data(
            picker_data, media_mapping
        )

    # ------------------------------------------------------------------
    # Scene link
    # ------------------------------------------------------------------

    def get_scene_link_data(self):
        """Return minimal data for the scene link property."""
        return {
            "bpicker_uuid": self.uuid or "",
            "bpicker_modified": self.metadata.get("modified", "") if self.metadata else "",
            "bpicker_name": self.metadata.get("picker_name", "") if self.metadata else "",
            "bpicker_filename": os.path.basename(self.bpicker_path) if self.bpicker_path else "",
        }

    def _update_scene_link(self):
        """Write the scene link property."""
        from . import data_management as DM
        DM.PickerDataManager.set_scene_link(self.get_scene_link_data())

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _refresh_archive_index(self):
        """Re-read the central directory of the on-disk .bpicker so
        differential repacks have an accurate view of what's there.

        Called after open, after save, after rename/save_as, and whenever
        we detect external modification.
        """
        if self.bpicker_path and os.path.isfile(self.bpicker_path):
            self._archive_index = BPF.BPickerArchive.list_entries(self.bpicker_path)
        else:
            self._archive_index = {}
        self._dirty_archive_paths.clear()
        self._media_dirty = False

    def _set_os_file_icon(self):
        """Set the per-file OS icon (Finder / Explorer) for the .bpicker file."""
        if not self.bpicker_path:
            return
        try:
            from .thumbnail_handler import set_file_icon
            set_file_icon(self.bpicker_path, preview_pixmap=self._pending_preview)
        except Exception:
            pass  # Non-critical – don't break saves

    def _build_media_mapping(self, picker_data):
        """Build a mapping from absolute/bpicker:// paths to archive-relative paths.

        For paths that are already bpicker:// prefixed, strips the prefix.
        For new absolute paths (added during editing), copies the file
        into temp and returns the new relative path.
        """
        mapping = {}
        if not self._temp_dir:
            return mapping

        for tab_name, tab_data in picker_data.get("tabs", {}).items():
            # Background layers
            for layer in tab_data.get("background_layers", []):
                img = layer.get("path")
                if img:
                    rel = self._resolve_or_copy_media(img, "backgrounds")
                    if rel:
                        mapping[img] = rel

            # Legacy single background image
            img = tab_data.get("image_path")
            if img:
                rel = self._resolve_or_copy_media(img, "backgrounds")
                if rel:
                    mapping[img] = rel

            # Button thumbnails
            for btn in tab_data.get("buttons", []):
                thumb = btn.get("thumbnail_path")
                if thumb:
                    rel = self._resolve_or_copy_media(thumb, "thumbnails")
                    if rel:
                        mapping[thumb] = rel

        return mapping

    def _resolve_or_copy_media(self, path, category):
        """Resolve a media path to an archive-relative path.

        If path is bpicker://, strip the prefix.
        If path is absolute and exists, copy into temp and return relative.
        If path is a bare relative path that exists in temp, return as-is.
        """
        if not path:
            return None

        if path.startswith("bpicker://"):
            return path[len("bpicker://"):]

        # Absolute path – copy into temp, handling filename collisions
        if os.path.isabs(path) and os.path.isfile(path):
            filename = os.path.basename(path)
            dest_dir = os.path.join(self._temp_dir, category)
            os.makedirs(dest_dir, exist_ok=True)
            dest = os.path.join(dest_dir, filename)
            copied = False

            if os.path.exists(dest):
                # Different file with same basename – generate unique name
                if os.path.getsize(dest) != os.path.getsize(path):
                    stem, ext = os.path.splitext(filename)
                    i = 1
                    while os.path.exists(dest):
                        filename = f"{stem}_{i}{ext}"
                        dest = os.path.join(dest_dir, filename)
                        i += 1
                    shutil.copy2(path, dest)
                    copied = True
                # else: same size, assume same file – reuse existing
            else:
                shutil.copy2(path, dest)
                copied = True

            archive_rel = f"{category}/{filename}"
            if copied:
                self._dirty_archive_paths.add(archive_rel)
                self._media_dirty = True
            return archive_rel

        # Fallback: bare relative path that already exists in temp dir
        # (safety net for paths that lost their bpicker:// prefix)
        if self._temp_dir:
            candidate = os.path.join(
                self._temp_dir, path.replace("/", os.sep)
            )
            if os.path.exists(candidate):
                return path

        return None

    @staticmethod
    def _safe_filename(name):
        """Sanitize a picker name for use as a filename."""
        # Remove or replace characters that are problematic in filenames
        safe = name.strip()
        for ch in r'<>:"/\|?*':
            safe = safe.replace(ch, "_")
        # Collapse multiple underscores
        while "__" in safe:
            safe = safe.replace("__", "_")
        return safe.strip("_") or "Untitled"
