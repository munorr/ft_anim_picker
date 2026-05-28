"""
Library Manager – Manages the central .bpicker library folder.

The library is a directory containing .bpicker files.  The folder itself
is the source of truth — no index file is written to disk.  An in-memory
cache is invalidated by comparing file names and modification times.
A ``Backups/`` subdirectory holds timestamped copies made before overwrites.
"""

import json
import os
import re
import shutil
import time
from datetime import datetime, timezone
from pathlib import Path

from . import bpicker_format as BPF
from .config import settings as CFG


# ---------------------------------------------------------------------------
# Persistence helpers (addon-level preferences file)
# ---------------------------------------------------------------------------

def _get_prefs_path():
    """Return the path to the addon preferences JSON file."""
    addon_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(addon_dir, "library_prefs.json")


def _read_prefs():
    path = _get_prefs_path()
    if os.path.isfile(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {}


def _write_prefs(data):
    path = _get_prefs_path()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)


# ---------------------------------------------------------------------------
# LocalFileManager (singleton)
# ---------------------------------------------------------------------------

class LocalFileManager:
    """Singleton that manages the central .bpicker library."""

    _instance = None
    _library_path = None
    _downloads_path = None
    _index = None           # Cached scan result {"version":1, "pickers":[...]}
    _last_snapshot = None   # set of (filename, subfolder, mtime) from last scan
    _watchers = []          # Callbacks invoked after index changes
    _last_reindex_time = 0  # Throttle rapid-fire reindex calls
    REINDEX_COOLDOWN_SEC = 2  # Minimum seconds between full reindex scans

    MAX_BACKUPS_PER_PICKER = 5      # Keep only the N most recent per picker
    BACKUP_MAX_AGE_DAYS = 30        # Delete backups older than this

    # ---- singleton ----

    @classmethod
    def get_instance(cls):
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def __init__(self):
        if LocalFileManager._instance is not None:
            raise RuntimeError("Use LocalFileManager.get_instance()")
        LocalFileManager._instance = self

    # ---- library path ----

    @classmethod
    def _maybe_migrate_legacy_library(cls):
        """If old FT_Anim_Picker library exists and new BGEN_Picker does not,
        rename the old directory to the new default location."""
        legacy = getattr(CFG, 'LEGACY_LIBRARY_PATH', None)
        new = CFG.DEFAULT_LIBRARY_PATH
        if legacy and legacy.parent.is_dir() and not new.parent.exists():
            try:
                legacy.parent.rename(new.parent)
                print(f"[BGEN Picker] Migrated library: {legacy.parent} -> {new.parent}")
            except Exception as e:
                print(f"[BGEN Picker] Could not migrate library folder: {e}")

    @classmethod
    def get_library_path(cls):
        """Return the configured library directory (Path object).

        Falls back to ``DEFAULT_LIBRARY_PATH`` from settings.
        Auto-migrates from legacy FT_Anim_Picker path if needed.
        """
        if cls._library_path is None:
            prefs = _read_prefs()
            stored = prefs.get("library_path")
            if stored and os.path.isdir(stored):
                cls._library_path = Path(stored)
            else:
                cls._maybe_migrate_legacy_library()
                cls._library_path = CFG.DEFAULT_LIBRARY_PATH
        return cls._library_path

    @classmethod
    def set_library_path(cls, path):
        """Update the library path and persist the choice."""
        cls._library_path = Path(path)
        prefs = _read_prefs()
        prefs["library_path"] = str(cls._library_path)
        _write_prefs(prefs)
        cls._index = None           # Force rescan on next access
        cls._last_snapshot = None
        cls.ensure_library_exists()

    @classmethod
    def get_downloads_path(cls):
        """Return the configured downloads directory (Path object).

        Falls back to ~/Downloads.
        """
        if cls._downloads_path is None:
            prefs = _read_prefs()
            saved = prefs.get("downloads_path", "")
            if saved and os.path.isdir(saved):
                cls._downloads_path = Path(saved)
            else:
                cls._downloads_path = Path.home() / "Downloads"
        return cls._downloads_path

    @classmethod
    def set_downloads_path(cls, path):
        """Update the downloads path and persist the choice."""
        cls._downloads_path = Path(path)
        prefs = _read_prefs()
        prefs["downloads_path"] = str(cls._downloads_path)
        _write_prefs(prefs)
        cls._downloads_path.mkdir(parents=True, exist_ok=True)

    @classmethod
    def get_always_on_top(cls):
        """Return True if the picker should stay visible even when Blender
        loses focus (default: False — hide when focus is lost)."""
        prefs = _read_prefs()
        return prefs.get("always_on_top", False)

    @classmethod
    def set_always_on_top(cls, value):
        """Persist the always-on-top preference."""
        prefs = _read_prefs()
        prefs["always_on_top"] = bool(value)
        _write_prefs(prefs)

    @classmethod
    def get_autosave_enabled(cls):
        """Return True if auto-save to .bpicker is enabled (default: True)."""
        prefs = _read_prefs()
        return prefs.get("autosave_enabled", True)

    @classmethod
    def set_autosave_enabled(cls, value):
        """Persist the auto-save preference."""
        prefs = _read_prefs()
        prefs["autosave_enabled"] = bool(value)
        _write_prefs(prefs)

    @classmethod
    def get_backups_path(cls):
        return cls.get_library_path() / "Backups"

    @classmethod
    def get_downloads_dir(cls):
        """Return the Downloads subfolder path, creating it if needed."""
        mp = cls.get_library_path() / "Downloads"
        mp.mkdir(parents=True, exist_ok=True)
        return mp

    # ---- ensure dirs ----

    @classmethod
    def ensure_library_exists(cls):
        """Create the library and Backups directories if missing."""
        lib = cls.get_library_path()
        lib.mkdir(parents=True, exist_ok=True)
        cls.get_backups_path().mkdir(parents=True, exist_ok=True)

    # ---- index ----

    @classmethod
    def _scan_disk(cls):
        """Return a set of (filename, subfolder, mtime) for all .bpicker files on disk."""
        lib = cls.get_library_path()
        if not lib.exists():
            return set()
        result = set()
        scan_dirs = [(lib, "")]
        mp_dir = lib / "Downloads"
        if mp_dir.is_dir():
            scan_dirs.append((mp_dir, "Downloads"))
        for d, sub in scan_dirs:
            try:
                for entry in d.iterdir():
                    if entry.suffix.lower() == CFG.BPICKER_EXTENSION:
                        try:
                            mtime = os.path.getmtime(str(entry))
                        except OSError:
                            mtime = 0
                        result.add((entry.name, sub, mtime))
            except OSError:
                pass
        return result

    @classmethod
    def reindex(cls, force=False):
        """Scan the library folder for .bpicker files and build an in-memory index.

        No index file is written to disk — the library folder itself is
        the source of truth. Results are cached and invalidated via
        ``_scan_disk()`` snapshot comparison.

        Throttled: rapid-fire calls within ``REINDEX_COOLDOWN_SEC`` return
        the cached index unless *force* is True.

        Returns:
            dict – the index: ``{"version": 1, "pickers": [...]}``.
        """
        # Throttle rapid-fire calls (e.g. auto-save every 3s)
        now = time.time()
        if not force and cls._index is not None:
            if (now - cls._last_reindex_time) < cls.REINDEX_COOLDOWN_SEC:
                return cls._index
        cls._last_reindex_time = now

        cls.ensure_library_exists()
        lib = cls.get_library_path()

        scan_dirs = [(lib, "")]
        mp_dir = lib / "Downloads"
        if mp_dir.is_dir():
            scan_dirs.append((mp_dir, "Downloads"))

        pickers = []
        for scan_dir, subfolder in scan_dirs:
            for entry in sorted(scan_dir.iterdir()):
                if entry.suffix.lower() != CFG.BPICKER_EXTENSION:
                    continue
                try:
                    info = BPF.BPickerArchive.read(str(entry))
                    meta = info["metadata"]
                    manifest = info["manifest"]
                    tab_count = len(manifest.get("tabs", {}))

                    # Check if a preview exists inside the archive
                    preview_available = False
                    try:
                        import zipfile
                        with zipfile.ZipFile(str(entry), "r") as zf:
                            preview_available = (BPF.CACHE_DIR + "/preview.png") in zf.namelist()
                    except Exception:
                        pass

                    pickers.append({
                        "uuid": meta.get("uuid", ""),
                        "name": meta.get("picker_name", entry.stem),
                        "filename": entry.name,
                        "subfolder": subfolder,
                        "author": meta.get("author", ""),
                        "created": meta.get("created", ""),
                        "modified": meta.get("modified", ""),
                        "tool_version": meta.get("tool_version", ""),
                        "tab_count": tab_count,
                        "preview_available": preview_available,
                        "software": meta.get("software", ""),
                        "custom_preview": meta.get("custom_preview", False),
                    })
                except Exception as e:
                    print(f"[LocalFileManager] Skipping {entry.name}: {e}")

        # Detect and resolve duplicate UUIDs (from manual file copies)
        uuid_groups = {}
        for p in pickers:
            uid = p.get("uuid", "")
            if uid:
                uuid_groups.setdefault(uid, []).append(p)

        resolved_any = False
        for uid, group in uuid_groups.items():
            if len(group) <= 1:
                continue
            # Keep the oldest file (by created date), reassign the rest
            group.sort(key=lambda x: x.get("created", ""))
            for dup in group[1:]:
                sub = dup.get("subfolder", "")
                dup_path = (lib / sub / dup["filename"]) if sub else (lib / dup["filename"])
                if not dup_path.exists():
                    continue
                try:
                    new_uuid = cls._assign_new_uuid(str(dup_path))
                    dup["uuid"] = new_uuid
                    resolved_any = True
                    print(f"[LocalFileManager] Duplicate UUID resolved: "
                          f"{dup['filename']} → {new_uuid}")
                except Exception as e:
                    print(f"[LocalFileManager] Could not resolve UUID for "
                          f"{dup['filename']}: {e}")

        index = {
            "version": 1,
            "pickers": pickers,
        }

        cls._index = index
        cls._last_snapshot = cls._scan_disk()
        cls.notify_watchers()
        return index

    @classmethod
    def get_index(cls):
        """Return the library index, rescanning if files changed on disk."""
        if cls._index is not None and cls._last_snapshot is not None:
            current = cls._scan_disk()
            if current == cls._last_snapshot:
                return cls._index

        return cls.reindex()

    @classmethod
    def update_index_entry(cls, picker_uuid, metadata, manifest, file_path):
        """Patch one picker's entry in the cached index without rescanning
        the rest of the library. O(1) with respect to library size — used on
        the auto-save hot path so a single picker save doesn't re-open every
        other .bpicker in the library.

        If the index hasn't been built yet, no-ops; the next ``get_index()``
        call will trigger a full reindex and pick up current state.
        """
        if cls._index is None:
            return

        file_path = str(file_path)
        lib = cls.get_library_path()
        try:
            rel = Path(file_path).resolve().relative_to(lib.resolve())
            subfolder = str(rel.parent) if str(rel.parent) != "." else ""
        except (ValueError, OSError):
            subfolder = ""
        # Normalize to single subfolder name (we currently only nest one level)
        if subfolder and "/" in subfolder.replace("\\", "/"):
            subfolder = subfolder.replace("\\", "/").split("/")[0]

        # Cheap preview check via central directory
        preview_available = False
        try:
            import zipfile as _zf
            with _zf.ZipFile(file_path, "r") as zf:
                preview_available = (BPF.CACHE_DIR + "/preview.png") in zf.namelist()
        except Exception:
            pass

        new_entry = {
            "uuid": picker_uuid,
            "name": metadata.get("picker_name", ""),
            "filename": os.path.basename(file_path),
            "subfolder": subfolder,
            "author": metadata.get("author", ""),
            "created": metadata.get("created", ""),
            "modified": metadata.get("modified", ""),
            "tool_version": metadata.get("tool_version", ""),
            "tab_count": len(manifest.get("tabs", {})),
            "preview_available": preview_available,
            "software": metadata.get("software", ""),
            "custom_preview": metadata.get("custom_preview", False),
        }

        pickers = cls._index.setdefault("pickers", [])
        for i, p in enumerate(pickers):
            if p.get("uuid") == picker_uuid:
                pickers[i] = new_entry
                break
        else:
            pickers.append(new_entry)

        # Refresh snapshot for this file so get_index() doesn't trigger rescan
        try:
            mtime = os.path.getmtime(file_path)
        except OSError:
            mtime = 0
        fname = new_entry["filename"]
        sub = new_entry["subfolder"]
        if cls._last_snapshot is not None:
            cls._last_snapshot = {
                e for e in cls._last_snapshot
                if not (e[0] == fname and e[1] == sub)
            }
            cls._last_snapshot.add((fname, sub, mtime))

        cls.notify_watchers()

    # ---- add / remove ----

    @classmethod
    def add_to_library(cls, bpicker_path, subfolder=None):
        """Copy a .bpicker file into the library.

        If a file with the same name already exists, the new file is
        saved with a numeric suffix (e.g. ``MyPicker_1.bpicker``).
        Existing files are never overwritten or deleted.

        Args:
            bpicker_path: Path to the source .bpicker file.
            subfolder: Optional subfolder within the library.

        Returns:
            str – final path of the .bpicker inside the library.
        """
        cls.ensure_library_exists()
        bpicker_path = str(bpicker_path)

        # Validate the archive is readable
        BPF.BPickerArchive.read(bpicker_path)

        filename = os.path.basename(bpicker_path)
        target_dir = cls.get_library_path()
        if subfolder:
            target_dir = target_dir / subfolder
            target_dir.mkdir(parents=True, exist_ok=True)
        dest = target_dir / filename

        # Resolve filename collision — never overwrite
        if dest.exists():
            stem = dest.stem
            i = 1
            while dest.exists():
                dest = target_dir / f"{stem}_{i}{CFG.BPICKER_EXTENSION}"
                i += 1

        # Copy file
        src_resolved = os.path.abspath(bpicker_path)
        dst_resolved = os.path.abspath(str(dest))
        if src_resolved != dst_resolved:
            shutil.copy2(bpicker_path, str(dest))

        # Resolve UUID conflict — if this UUID already exists in the
        # library (from a different file), assign a fresh UUID so the
        # copy is a standalone picker.
        try:
            info = BPF.BPickerArchive.read(str(dest))
            incoming_uuid = info["metadata"].get("uuid", "")
            if incoming_uuid:
                existing = cls.check_uuid_conflict(incoming_uuid)
                if existing and existing["filename"] != dest.name:
                    new_uuid = cls._assign_new_uuid(str(dest))
                    print(f"[LocalFileManager] UUID conflict resolved: "
                          f"{dest.name} → {new_uuid}")
        except Exception as e:
            print(f"[LocalFileManager] UUID resolution warning: {e}")

        cls.reindex()
        return str(dest)

    @classmethod
    def remove_from_library(cls, picker_uuid):
        """Move a picker to Backups/ (soft delete).

        Returns:
            True if successfully removed, False if not found.
        """
        picker_path = cls.get_picker_path(picker_uuid)
        if not picker_path or not picker_path.exists():
            return False

        cls.backup_picker(picker_uuid)
        os.remove(str(picker_path))
        cls.reindex()
        return True

    @classmethod
    def get_picker_path(cls, picker_uuid):
        """Look up the full path to a .bpicker by UUID.

        Returns:
            Path or None.
        """
        index = cls.get_index()
        for entry in index.get("pickers", []):
            if entry.get("uuid") == picker_uuid:
                sub = entry.get("subfolder", "")
                if sub:
                    path = cls.get_library_path() / sub / entry["filename"]
                else:
                    path = cls.get_library_path() / entry["filename"]
                if path.exists():
                    return path
        return None

    @classmethod
    def get_picker_info(cls, picker_uuid):
        """Return index entry dict for a picker UUID, or None."""
        index = cls.get_index()
        for entry in index.get("pickers", []):
            if entry.get("uuid") == picker_uuid:
                return entry
        return None

    # ---- backup ----

    _BACKUP_TS_RE = re.compile(r"^(.+)_(\d{8}_\d{6})$")

    @classmethod
    def backup_picker(cls, picker_uuid):
        """Copy the current .bpicker to Backups/ with a timestamp suffix.

        Automatically prunes old backups afterwards.
        """
        picker_path = cls.get_picker_path(picker_uuid)
        if not picker_path or not picker_path.exists():
            return

        backups = cls.get_backups_path()
        backups.mkdir(parents=True, exist_ok=True)

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        stem = picker_path.stem
        backup_name = f"{stem}_{timestamp}{CFG.BPICKER_EXTENSION}"
        shutil.copy2(str(picker_path), str(backups / backup_name))

        cls.prune_backups()

    _last_prune_time = 0  # class-level throttle for prune_backups
    PRUNE_COOLDOWN_SEC = 3600  # only prune once per hour

    @classmethod
    def prune_backups(cls, force=False):
        """Remove old backups exceeding age or count limits.

        Rules applied per picker (grouped by stem before the timestamp):
        - Delete any backup older than ``BACKUP_MAX_AGE_DAYS``.
        - Keep at most ``MAX_BACKUPS_PER_PICKER`` (newest first).

        Throttled to run at most once per hour unless *force* is True.
        """
        now = time.time()
        if not force and (now - cls._last_prune_time) < cls.PRUNE_COOLDOWN_SEC:
            return
        cls._last_prune_time = now

        backups_dir = cls.get_backups_path()
        if not backups_dir.is_dir():
            return

        ext = CFG.BPICKER_EXTENSION.lower()
        now = datetime.now()

        # Group backup files by picker stem
        groups = {}  # stem -> list of (datetime, Path)
        for entry in backups_dir.iterdir():
            if entry.suffix.lower() != ext:
                continue
            m = cls._BACKUP_TS_RE.match(entry.stem)
            if not m:
                continue
            stem = m.group(1)
            try:
                ts = datetime.strptime(m.group(2), "%Y%m%d_%H%M%S")
            except ValueError:
                continue
            groups.setdefault(stem, []).append((ts, entry))

        removed = 0
        for stem, backups in groups.items():
            # Sort newest first
            backups.sort(key=lambda x: x[0], reverse=True)

            for i, (ts, path) in enumerate(backups):
                age_days = (now - ts).days
                if age_days > cls.BACKUP_MAX_AGE_DAYS or i >= cls.MAX_BACKUPS_PER_PICKER:
                    try:
                        os.remove(str(path))
                        removed += 1
                    except OSError:
                        pass

        if removed:
            print(f"[LocalFileManager] Pruned {removed} old backup(s)")

    # ---- UUID conflict detection / resolution ----

    @classmethod
    def check_uuid_conflict(cls, picker_uuid):
        """Check if a UUID already exists in the library.

        Returns:
            dict with existing picker info, or None.
        """
        if not picker_uuid:
            return None
        index = cls.get_index()
        for entry in index.get("pickers", []):
            if entry.get("uuid") == picker_uuid:
                return entry
        return None

    @staticmethod
    def _assign_new_uuid(bpicker_path):
        """Rewrite the metadata.json inside a .bpicker with a fresh UUID.

        Returns:
            str – the new UUID.
        """
        bpicker_path = str(bpicker_path)
        new_uuid = BPF.generate_uuid()
        temp_dir = BPF.BPickerArchive.extract_to_temp(bpicker_path)
        try:
            meta_path = os.path.join(temp_dir, BPF.METADATA_NAME)
            with open(meta_path, "r", encoding="utf-8") as f:
                metadata = json.load(f)
            metadata["uuid"] = new_uuid
            with open(meta_path, "w", encoding="utf-8") as f:
                json.dump(metadata, f, indent=2)
            BPF.BPickerArchive.repack(temp_dir, bpicker_path)
        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)
        return new_uuid

    # ---- software tag ----

    @classmethod
    def set_picker_software(cls, picker_uuid, software):
        """Set the software tag for a picker ('blender', 'maya', or '').

        Args:
            picker_uuid: UUID of the picker to update.
            software: One of 'blender', 'maya', or '' (none).

        Returns:
            True on success, False on failure.
        """
        if software not in ("blender", "maya", ""):
            return False

        picker_path = cls.get_picker_path(picker_uuid)
        if not picker_path or not picker_path.exists():
            return False

        temp_dir = BPF.BPickerArchive.extract_to_temp(str(picker_path))
        try:
            meta_path = os.path.join(temp_dir, BPF.METADATA_NAME)
            with open(meta_path, "r", encoding="utf-8") as f:
                metadata = json.load(f)
            metadata["software"] = software
            metadata["modified"] = datetime.now(timezone.utc).isoformat()
            with open(meta_path, "w", encoding="utf-8") as f:
                json.dump(metadata, f, indent=2)
            BPF.BPickerArchive.repack(temp_dir, str(picker_path))
        except Exception as e:
            print(f"[LocalFileManager] Failed to set software tag: {e}")
            return False
        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)

        cls.reindex()
        return True

    # ---- custom preview ----

    @classmethod
    def set_custom_preview(cls, picker_uuid, image_path):
        """Set a custom thumbnail image for a picker.

        Args:
            picker_uuid: UUID of the picker to update.
            image_path: Path to the image file to use as thumbnail.

        Returns:
            True on success, False on failure.
        """
        from qtpy.QtGui import QPixmap
        from qtpy.QtCore import Qt

        picker_path = cls.get_picker_path(picker_uuid)
        if not picker_path or not picker_path.exists():
            return False

        # Validate image
        pixmap = QPixmap(image_path)
        if pixmap.isNull():
            return False

        # Scale to 256x256
        preview = pixmap.scaled(
            256, 256, Qt.KeepAspectRatio, Qt.SmoothTransformation
        )

        temp_dir = BPF.BPickerArchive.extract_to_temp(str(picker_path))
        try:
            # Save scaled preview
            cache_dir = os.path.join(temp_dir, BPF.CACHE_DIR)
            os.makedirs(cache_dir, exist_ok=True)
            preview.save(os.path.join(cache_dir, "preview.png"), "PNG")

            # Update metadata
            meta_path = os.path.join(temp_dir, BPF.METADATA_NAME)
            with open(meta_path, "r", encoding="utf-8") as f:
                metadata = json.load(f)
            metadata["custom_preview"] = True
            metadata["modified"] = datetime.now(timezone.utc).isoformat()
            with open(meta_path, "w", encoding="utf-8") as f:
                json.dump(metadata, f, indent=2)

            BPF.BPickerArchive.repack(temp_dir, str(picker_path))
        except Exception as e:
            print(f"[LocalFileManager] Failed to set custom preview: {e}")
            return False
        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)

        cls.reindex()
        return True

    @classmethod
    def clear_custom_preview(cls, picker_uuid):
        """Clear the custom thumbnail, reverting to auto-generated preview.

        Args:
            picker_uuid: UUID of the picker to update.

        Returns:
            True on success, False on failure.
        """
        picker_path = cls.get_picker_path(picker_uuid)
        if not picker_path or not picker_path.exists():
            return False

        temp_dir = BPF.BPickerArchive.extract_to_temp(str(picker_path))
        try:
            # Remove existing preview so next save generates a fresh one
            preview_path = os.path.join(temp_dir, BPF.CACHE_DIR, "preview.png")
            if os.path.exists(preview_path):
                os.remove(preview_path)

            # Update metadata
            meta_path = os.path.join(temp_dir, BPF.METADATA_NAME)
            with open(meta_path, "r", encoding="utf-8") as f:
                metadata = json.load(f)
            metadata["custom_preview"] = False
            metadata["modified"] = datetime.now(timezone.utc).isoformat()
            with open(meta_path, "w", encoding="utf-8") as f:
                json.dump(metadata, f, indent=2)

            BPF.BPickerArchive.repack(temp_dir, str(picker_path))
        except Exception as e:
            print(f"[LocalFileManager] Failed to clear custom preview: {e}")
            return False
        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)

        cls.reindex()
        return True

    # ---- rename ----

    @classmethod
    def rename_picker(cls, picker_uuid, new_name):
        """Rename a picker (updates metadata and filename).

        If the target picker is the currently active session, the rename is
        delegated to the session so its in-flight edits and temp dir are
        carried over to the new filename instead of being lost.

        Returns:
            str – new file path, or None on failure.
        """
        # Delegate to the active session if this picker is currently open,
        # so live edits aren't dropped and the session's bpicker_path stays
        # in sync with the new filename.
        try:
            from . import data_management as DM
            session = DM.PickerDataManager.get_active_session()
        except Exception:
            session = None
        if session and getattr(session, "uuid", None) == picker_uuid:
            return session.rename(new_name)

        picker_path = cls.get_picker_path(picker_uuid)
        if not picker_path or not picker_path.exists():
            return None

        # Update metadata inside archive
        info = BPF.BPickerArchive.read(str(picker_path))
        metadata = info["metadata"]
        metadata["picker_name"] = new_name
        metadata["modified"] = datetime.now(timezone.utc).isoformat()

        # Extract, update metadata, repack
        temp_dir = BPF.BPickerArchive.extract_to_temp(str(picker_path))
        try:
            meta_path = os.path.join(temp_dir, BPF.METADATA_NAME)
            with open(meta_path, "w", encoding="utf-8") as f:
                json.dump(metadata, f, indent=2)

            # Rename the file on disk (keep it in same subfolder)
            new_filename = f"{new_name}{CFG.BPICKER_EXTENSION}"
            target_dir = picker_path.parent
            new_path = target_dir / new_filename

            # Avoid collision
            if new_path.exists() and new_path != picker_path:
                i = 1
                while new_path.exists():
                    new_path = target_dir / f"{new_name}_{i}{CFG.BPICKER_EXTENSION}"
                    i += 1

            BPF.BPickerArchive.repack(temp_dir, str(new_path))

            # Remove old file if name changed
            if new_path != picker_path and picker_path.exists():
                os.remove(str(picker_path))

        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)

        cls.reindex()
        return str(new_path)

    # ---- watchers ----

    @classmethod
    def register_watcher(cls, callback):
        """Register a callback to be called when the index changes."""
        if callback not in cls._watchers:
            cls._watchers.append(callback)

    @classmethod
    def unregister_watcher(cls, callback):
        """Remove a previously registered watcher."""
        try:
            cls._watchers.remove(callback)
        except ValueError:
            pass

    @classmethod
    def notify_watchers(cls):
        """Call all registered watchers."""
        for cb in cls._watchers:
            try:
                cb()
            except Exception as e:
                print(f"[LocalFileManager] Watcher error: {e}")
