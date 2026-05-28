"""
BPicker Format - Core archive read/write for .bpicker files.

A .bpicker file is a ZIP archive containing:
  manifest.json   - Tabs, buttons, control mappings, relative media paths
  metadata.json   - Version, author, timestamps, UUID
  thumbnails/     - Pose thumbnail images
  backgrounds/    - Tab background images
  cache/          - Optional preview images
"""

import copy
import json
import os
import shutil
import tempfile
import time
import uuid
import zipfile
from collections import OrderedDict
from datetime import datetime, timezone


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

MANIFEST_NAME = "manifest.json"
METADATA_NAME = "metadata.json"
THUMBNAILS_DIR = "thumbnails"
BACKGROUNDS_DIR = "backgrounds"
CACHE_DIR = "cache"
MANIFEST_VERSION = 1
METADATA_VERSION = 1

# Already-compressed media; DEFLATE wastes CPU for ~0% size win.
_NO_COMPRESS_EXT = {".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp"}


def _compression_for(arc_path):
    """Return the right ZIP compression mode for an archive entry."""
    ext = os.path.splitext(arc_path)[1].lower()
    return zipfile.ZIP_STORED if ext in _NO_COMPRESS_EXT else zipfile.ZIP_DEFLATED


def _atomic_replace(src, dst, retries=3, backoff_sec=0.05):
    """Atomically replace ``dst`` with ``src``.

    ``os.replace`` is atomic on both POSIX and Windows. On Windows, transient
    AV / Explorer thumbnail-handler locks can cause PermissionError; retry a
    few times before falling back to remove+rename.
    """
    last_exc = None
    for _ in range(retries):
        try:
            os.replace(src, dst)
            return
        except PermissionError as exc:
            last_exc = exc
            time.sleep(backoff_sec)
    # Last-resort fallback (matches legacy behavior)
    try:
        if os.path.exists(dst):
            os.remove(dst)
        os.rename(src, dst)
    except Exception:
        if last_exc is not None:
            raise last_exc
        raise


# ---------------------------------------------------------------------------
# UUID / metadata helpers
# ---------------------------------------------------------------------------

def generate_uuid():
    """Generate a new unique picker UUID."""
    return str(uuid.uuid4())


def build_metadata(picker_name, author="", tool_version="", picker_uuid=None):
    """Create a metadata dict for a new .bpicker archive.

    Args:
        picker_name: Human-readable picker name.
        author: Author name.
        tool_version: Version string of the addon that created this picker.
        picker_uuid: Optional UUID. Generated if not provided.

    Returns:
        dict with metadata fields.
    """
    now = datetime.now(timezone.utc).isoformat()
    return {
        "metadata_version": METADATA_VERSION,
        "uuid": picker_uuid or generate_uuid(),
        "picker_name": picker_name,
        "author": author,
        "tool_version": tool_version,
        "created": now,
        "modified": now,
        "description": "",
        "tags": [],
        "software": "",
        "custom_preview": False,
    }


# ---------------------------------------------------------------------------
# Manifest ↔ PickerDataManager conversion
# ---------------------------------------------------------------------------

def build_manifest_from_picker_data(picker_data, media_mapping=None):
    """Convert PickerDataManager format to a .bpicker manifest.

    This strips out absolute paths and replaces them with archive-relative
    references (e.g. ``backgrounds/bg_main.png``).

    Args:
        picker_data: dict in PickerDataManager format (tabs, settings, …).
        media_mapping: dict mapping *original absolute path* →
            *archive-relative path* for every media file that has been (or
            will be) copied into the archive.  If ``None``, paths are left
            as-is (useful when the data already uses relative paths).

    Returns:
        dict suitable for writing as ``manifest.json``.
    """
    media_mapping = media_mapping or {}

    # Deep-copy tabs so we don't mutate the original (including nested
    # button dicts and background layers that get path-remapped below)
    tabs = OrderedDict()
    for tab_name, tab_data in picker_data.get("tabs", {}).items():
        tab_copy = copy.deepcopy(tab_data)

        # Remap background layer paths
        for layer in tab_copy.get("background_layers", []):
            img = layer.get("path")
            if img and img in media_mapping:
                layer["path"] = media_mapping[img]
            elif img and img.startswith("bpicker://"):
                layer["path"] = img[len("bpicker://"):]

        # Legacy single-image support (for old data flowing through)
        img = tab_copy.get("image_path")
        if img and img in media_mapping:
            tab_copy["image_path"] = media_mapping[img]
        elif img and img.startswith("bpicker://"):
            tab_copy["image_path"] = img[len("bpicker://"):]

        # Remap button thumbnail paths
        buttons = []
        for btn in tab_copy.get("buttons", []):
            btn_copy = dict(btn)
            thumb = btn_copy.get("thumbnail_path")
            if thumb and thumb in media_mapping:
                btn_copy["thumbnail_path"] = media_mapping[thumb]
            elif thumb and thumb.startswith("bpicker://"):
                btn_copy["thumbnail_path"] = thumb[len("bpicker://"):]
            buttons.append(btn_copy)
        tab_copy["buttons"] = buttons

        tabs[tab_name] = tab_copy

    manifest = {
        "manifest_version": MANIFEST_VERSION,
        "tabs": tabs,
    }
    return manifest


def build_picker_data_from_manifest(manifest):
    """Convert a .bpicker manifest back into PickerDataManager format.

    Media paths are prefixed with ``bpicker://`` so that
    ``PickerDataManager.resolve_image_path`` can delegate to the active
    session's temp directory.

    Returns:
        dict in PickerDataManager format.
    """
    tabs = OrderedDict()
    for tab_name, tab_data in manifest.get("tabs", {}).items():
        tab_copy = dict(tab_data)

        # Deep-copy background_layers to avoid mutating self.manifest
        if "background_layers" in tab_copy:
            tab_copy["background_layers"] = [
                dict(layer) for layer in tab_copy["background_layers"]
            ]

        # Prefix background layer paths with bpicker://
        for layer in tab_copy.get("background_layers", []):
            img = layer.get("path")
            if img and not img.startswith("bpicker://"):
                layer["path"] = f"bpicker://{img}"

        # Legacy single-image support
        img = tab_copy.get("image_path")
        if img and not img.startswith("bpicker://"):
            tab_copy["image_path"] = f"bpicker://{img}"

        # Prefix button thumbnails
        buttons = []
        for btn in tab_copy.get("buttons", []):
            btn_copy = dict(btn)
            thumb = btn_copy.get("thumbnail_path")
            if thumb and not thumb.startswith("bpicker://"):
                btn_copy["thumbnail_path"] = f"bpicker://{thumb}"
            buttons.append(btn_copy)
        tab_copy["buttons"] = buttons

        tabs[tab_name] = tab_copy

    picker_data = OrderedDict({
        "settings": {
            "last_picker_file_path": "",
        },
        "tabs": tabs,
    })
    return picker_data


# ---------------------------------------------------------------------------
# BPickerArchive – core archive operations
# ---------------------------------------------------------------------------

class BPickerArchive:
    """Read / write .bpicker ZIP archives."""

    # ---- create ----

    @staticmethod
    def create(dest_path, manifest, metadata, media_files=None):
        """Create a new .bpicker archive.

        Args:
            dest_path: Destination file path (should end with .bpicker).
            manifest: dict for manifest.json.
            metadata: dict for metadata.json.
            media_files: dict mapping *archive-relative path* →
                *absolute source path*.  Each entry is copied into the ZIP.

        Returns:
            str – the final archive path.
        """
        media_files = media_files or {}

        dest_path = str(dest_path)
        if not dest_path.lower().endswith(".bpicker"):
            dest_path += ".bpicker"

        os.makedirs(os.path.dirname(dest_path) or ".", exist_ok=True)

        with zipfile.ZipFile(dest_path, "w") as zf:
            # Write manifest
            zf.writestr(MANIFEST_NAME, json.dumps(manifest, indent=2),
                        compress_type=zipfile.ZIP_DEFLATED)

            # Write metadata
            zf.writestr(METADATA_NAME, json.dumps(metadata, indent=2),
                        compress_type=zipfile.ZIP_DEFLATED)

            # Ensure directory entries exist
            for dirname in (THUMBNAILS_DIR, BACKGROUNDS_DIR, CACHE_DIR):
                zf.writestr(dirname + "/", "")

            # Write media files (STORED for already-compressed image formats)
            for archive_rel, source_abs in media_files.items():
                if os.path.isfile(source_abs):
                    zf.write(source_abs, archive_rel,
                             compress_type=_compression_for(archive_rel))

        return dest_path

    # ---- read ----

    @staticmethod
    def read(bpicker_path):
        """Read manifest and metadata from a .bpicker archive (no extraction).

        Returns:
            dict with keys ``manifest``, ``metadata``, ``archive_path``.

        Raises:
            FileNotFoundError, zipfile.BadZipFile, KeyError on problems.
        """
        bpicker_path = str(bpicker_path)
        with zipfile.ZipFile(bpicker_path, "r") as zf:
            manifest = json.loads(zf.read(MANIFEST_NAME))
            metadata = json.loads(zf.read(METADATA_NAME))

        return {
            "manifest": manifest,
            "metadata": metadata,
            "archive_path": bpicker_path,
        }

    # ---- extract ----

    @staticmethod
    def extract_to_temp(bpicker_path):
        """Extract the full archive to a temporary directory.

        The caller is responsible for cleaning up the temp directory
        (e.g. via ``shutil.rmtree``).

        Returns:
            str – path to the temp directory.
        """
        bpicker_path = str(bpicker_path)
        temp_dir = tempfile.mkdtemp(prefix="bpicker_")
        with zipfile.ZipFile(bpicker_path, "r") as zf:
            zf.extractall(temp_dir)
        return temp_dir

    @staticmethod
    def extract_media(bpicker_path, entry_path):
        """Extract a single file from the archive as bytes.

        Args:
            bpicker_path: Path to the .bpicker file.
            entry_path: Archive-relative path (e.g. ``thumbnails/thumb_001.png``).

        Returns:
            bytes or None if entry not found.
        """
        try:
            with zipfile.ZipFile(str(bpicker_path), "r") as zf:
                return zf.read(entry_path)
        except (KeyError, zipfile.BadZipFile):
            return None

    # ---- list / inspect ----

    @staticmethod
    def list_entries(bpicker_path):
        """Return ``{arc_path: (size, crc, compress_type)}`` for every entry.

        Reads only the central directory — does not decompress payload bytes.
        Used by sessions to seed an archive snapshot for differential repack.
        """
        bpicker_path = str(bpicker_path)
        result = {}
        try:
            with zipfile.ZipFile(bpicker_path, "r") as zf:
                for info in zf.infolist():
                    if info.is_dir():
                        continue
                    result[info.filename] = (
                        info.file_size, info.CRC, info.compress_type
                    )
        except (FileNotFoundError, zipfile.BadZipFile):
            pass
        return result

    # ---- repack ----

    @staticmethod
    def repack_incremental(temp_dir, dest_path, prev_archive_path,
                           dirty_paths=None):
        """Repack a .bpicker, copying unchanged entries from the previous
        archive without recompressing.

        - Walks ``temp_dir`` to determine the desired entry set.
        - Entries listed in ``dirty_paths`` (or absent from the previous
          archive, or differing in size from temp_dir) are read from
          temp_dir and written fresh.
        - All other entries are stream-copied from ``prev_archive_path``
          using ``read()`` + ``writestr()``. STORED entries (e.g. PNG/JPG
          thumbnails after the Layer 1 change) round-trip as raw bytes —
          no recompression cost.
        - Entries present in the previous archive but absent from temp_dir
          are dropped (deletions).
        - Atomic rename via ``_atomic_replace``.

        Falls back to a full ``repack(temp_dir, dest_path)`` if the previous
        archive is missing or corrupt.

        Args:
            temp_dir: Root of the extracted archive (source of truth for
                what should be in the result).
            dest_path: Where to write the new ZIP. May equal
                ``prev_archive_path`` (atomic replace).
            prev_archive_path: Path to the existing .bpicker to copy
                unchanged entries from.
            dirty_paths: Optional set of archive-relative paths that must
                be re-read from temp_dir even if size matches.

        Returns:
            str – the final archive path.
        """
        dest_path = str(dest_path)
        if not dest_path.lower().endswith(".bpicker"):
            dest_path += ".bpicker"
        prev_archive_path = str(prev_archive_path) if prev_archive_path else ""
        dirty = set(dirty_paths or ())

        # If we can't read the previous archive, fall back to full repack.
        if not prev_archive_path or not os.path.isfile(prev_archive_path):
            return BPickerArchive.repack(temp_dir, dest_path)

        # Snapshot what should be in the result.
        desired = {}  # arc_path -> (abs_path, size)
        for root, _dirs, files in os.walk(temp_dir):
            for fname in files:
                abs_path = os.path.join(root, fname)
                arc_path = os.path.relpath(abs_path, temp_dir).replace("\\", "/")
                try:
                    size = os.path.getsize(abs_path)
                except OSError:
                    continue
                desired[arc_path] = (abs_path, size)

        tmp_zip = dest_path + ".tmp"
        try:
            with zipfile.ZipFile(prev_archive_path, "r") as old_zf:
                old_infos = {info.filename: info for info in old_zf.infolist()
                             if not info.is_dir()}
                with zipfile.ZipFile(tmp_zip, "w") as new_zf:
                    for arc_path, (abs_path, size) in desired.items():
                        old_info = old_infos.get(arc_path)
                        is_dirty = (
                            arc_path in dirty
                            or old_info is None
                            or old_info.file_size != size
                        )
                        if is_dirty:
                            new_zf.write(
                                abs_path, arc_path,
                                compress_type=_compression_for(arc_path),
                            )
                        else:
                            # Stream-copy from old archive (raw bytes for
                            # STORED entries; decompress+recompress for
                            # DEFLATED — cheap because manifest/metadata are
                            # tiny and we only end up here when *they*
                            # weren't dirty, which is rare).
                            data = old_zf.read(arc_path)
                            new_zf.writestr(
                                arc_path, data,
                                compress_type=_compression_for(arc_path),
                            )

            _atomic_replace(tmp_zip, dest_path)
        except Exception:
            if os.path.exists(tmp_zip):
                try:
                    os.remove(tmp_zip)
                except OSError:
                    pass
            # Last-resort: full repack so the user doesn't lose data.
            return BPickerArchive.repack(temp_dir, dest_path)

        return dest_path

    @staticmethod
    def repack(temp_dir, dest_path):
        """Re-create a .bpicker ZIP from a temp directory.

        Walks the temp directory and adds every file, preserving relative
        paths.

        Args:
            temp_dir: Root of the extracted archive.
            dest_path: Where to write the new ZIP.

        Returns:
            str – the final archive path.
        """
        dest_path = str(dest_path)
        if not dest_path.lower().endswith(".bpicker"):
            dest_path += ".bpicker"

        # Write to a temp file first, then replace atomically
        tmp_zip = dest_path + ".tmp"
        try:
            with zipfile.ZipFile(tmp_zip, "w") as zf:
                for root, _dirs, files in os.walk(temp_dir):
                    for fname in files:
                        abs_path = os.path.join(root, fname)
                        arc_path = os.path.relpath(abs_path, temp_dir).replace("\\", "/")
                        zf.write(abs_path, arc_path,
                                 compress_type=_compression_for(arc_path))

            _atomic_replace(tmp_zip, dest_path)
        except Exception:
            if os.path.exists(tmp_zip):
                try:
                    os.remove(tmp_zip)
                except OSError:
                    pass
            raise

        return dest_path

    # ---- in-place updates ----

    @staticmethod
    def update_manifest(bpicker_path, new_manifest):
        """Replace manifest.json inside an existing archive.

        Also updates metadata.json ``modified`` timestamp.
        """
        bpicker_path = str(bpicker_path)
        temp_dir = BPickerArchive.extract_to_temp(bpicker_path)
        try:
            manifest_path = os.path.join(temp_dir, MANIFEST_NAME)
            with open(manifest_path, "w", encoding="utf-8") as f:
                json.dump(new_manifest, f, indent=2)

            # Touch modified timestamp in metadata
            meta_path = os.path.join(temp_dir, METADATA_NAME)
            if os.path.exists(meta_path):
                with open(meta_path, "r", encoding="utf-8") as f:
                    metadata = json.load(f)
                metadata["modified"] = datetime.now(timezone.utc).isoformat()
                with open(meta_path, "w", encoding="utf-8") as f:
                    json.dump(metadata, f, indent=2)

            BPickerArchive.repack(temp_dir, bpicker_path)
        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)

    @staticmethod
    def add_media(bpicker_path, archive_rel_path, file_bytes):
        """Add or replace a single media file in an existing archive."""
        bpicker_path = str(bpicker_path)
        temp_dir = BPickerArchive.extract_to_temp(bpicker_path)
        try:
            target = os.path.join(temp_dir, archive_rel_path.replace("/", os.sep))
            os.makedirs(os.path.dirname(target), exist_ok=True)
            with open(target, "wb") as f:
                f.write(file_bytes)
            BPickerArchive.repack(temp_dir, bpicker_path)
        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)

    # ---- validation ----

    @staticmethod
    def validate(bpicker_path):
        """Validate a .bpicker archive.

        Returns:
            list of error strings.  Empty list means valid.
        """
        errors = []
        bpicker_path = str(bpicker_path)

        # Check ZIP integrity
        try:
            zf = zipfile.ZipFile(bpicker_path, "r")
        except (zipfile.BadZipFile, FileNotFoundError) as e:
            return [f"Cannot open archive: {e}"]

        with zf:
            # Check required files
            names = zf.namelist()
            if MANIFEST_NAME not in names:
                errors.append("Missing manifest.json")
            if METADATA_NAME not in names:
                errors.append("Missing metadata.json")

            # Validate manifest
            if MANIFEST_NAME in names:
                try:
                    manifest = json.loads(zf.read(MANIFEST_NAME))
                except json.JSONDecodeError as e:
                    errors.append(f"Invalid manifest.json: {e}")
                    manifest = None

                if manifest:
                    # Check for absolute paths
                    errors.extend(_check_absolute_paths(manifest, "manifest"))

                    # Check all referenced media files exist in archive
                    errors.extend(_check_media_refs(manifest, names))

            # Validate metadata
            if METADATA_NAME in names:
                try:
                    metadata = json.loads(zf.read(METADATA_NAME))
                except json.JSONDecodeError as e:
                    errors.append(f"Invalid metadata.json: {e}")
                    metadata = None

                if metadata:
                    if not metadata.get("uuid"):
                        errors.append("metadata.json missing UUID")

        return errors


# ---------------------------------------------------------------------------
# Validation helpers
# ---------------------------------------------------------------------------

def _check_absolute_paths(manifest, context=""):
    """Recursively check for absolute paths in manifest data."""
    errors = []

    def _walk(obj, path=""):
        if isinstance(obj, str):
            # Check for common absolute path patterns
            if (os.path.isabs(obj)
                    and not obj.startswith("bpicker://")
                    and any(obj.lower().endswith(ext) for ext in
                            (".png", ".jpg", ".jpeg", ".bmp", ".gif", ".webp", ".svg"))):
                errors.append(f"Absolute media path in {context}{path}: {obj}")
        elif isinstance(obj, dict):
            for k, v in obj.items():
                _walk(v, f"{path}.{k}")
        elif isinstance(obj, (list, tuple)):
            for i, v in enumerate(obj):
                _walk(v, f"{path}[{i}]")

    _walk(manifest)
    return errors


def _check_media_refs(manifest, archive_names):
    """Check that all media referenced in the manifest exist in the archive."""
    errors = []
    archive_set = set(archive_names)

    for tab_name, tab_data in manifest.get("tabs", {}).items():
        # Background layers
        for layer in tab_data.get("background_layers", []):
            img = layer.get("path")
            if img and img not in archive_set and not img.startswith("bpicker://"):
                errors.append(f"Tab '{tab_name}' layer '{layer.get('name', '?')}' references missing background: {img}")

        # Legacy single background image
        img = tab_data.get("image_path")
        if img and img not in archive_set and not img.startswith("bpicker://"):
            errors.append(f"Tab '{tab_name}' references missing background: {img}")

        # Button thumbnails
        for btn in tab_data.get("buttons", []):
            thumb = btn.get("thumbnail_path")
            if thumb and thumb not in archive_set and not thumb.startswith("bpicker://"):
                errors.append(
                    f"Tab '{tab_name}' button '{btn.get('id', '?')}' "
                    f"references missing thumbnail: {thumb}"
                )

    return errors
