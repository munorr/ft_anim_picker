"""
Icon Compositor – Build a file icon from a preview image + logo badge.

Uses Qt (PySide6 / PySide2) for image compositing.  The result is a square
PNG suitable for setting as a per-file custom icon on macOS or Windows.
"""

import os
import tempfile
import zipfile

try:
    from PySide6.QtCore import Qt, QRect, QRectF, QPoint
    from PySide6.QtGui import (
        QImage, QPainter, QPixmap, QColor, QPainterPath, QBrush, QPen,
    )
except ImportError:
    from PySide2.QtCore import Qt, QRect, QRectF, QPoint
    from PySide2.QtGui import (
        QImage, QPainter, QPixmap, QColor, QPainterPath, QBrush, QPen,
    )

# Icon output size (pixels) – 512 is a good balance for Finder/Explorer
ICON_SIZE = 512

# Badge size relative to icon
BADGE_RATIO = 0.22

# Rounded-rect corner radius relative to icon size
CORNER_RADIUS_RATIO = 0.08


def extract_preview_from_archive(bpicker_path):
    """Extract cache/preview.png from a .bpicker ZIP archive.

    Returns:
        QPixmap or None.
    """
    try:
        with zipfile.ZipFile(bpicker_path, "r") as zf:
            if "cache/preview.png" in zf.namelist():
                data = zf.read("cache/preview.png")
                pixmap = QPixmap()
                pixmap.loadFromData(data)
                if not pixmap.isNull():
                    return pixmap
    except Exception:
        pass
    return None


def composite_icon(preview_pixmap=None, badge_path=None, fallback_icon=None,
                   bpicker_path=None):
    """Create a composited file icon.

    Priority:
      1. preview_pixmap (live canvas grab)
      2. preview.png extracted from the .bpicker archive
      3. fallback_icon (the static bpicker_file_icon.png)

    The BGEN logo badge is painted in the bottom-right corner.

    Args:
        preview_pixmap: QPixmap of the canvas (optional).
        badge_path: Path to the logo badge PNG.
        fallback_icon: Path to the static fallback icon PNG.
        bpicker_path: Path to the .bpicker archive (to extract preview).

    Returns:
        str – path to a temporary PNG file with the composited icon,
        or None on failure.
    """
    size = ICON_SIZE
    corner = int(size * CORNER_RADIUS_RATIO)

    # ── Resolve the base image ──────────────────────────────────────
    base = None

    if preview_pixmap and not preview_pixmap.isNull():
        base = preview_pixmap

    if base is None and bpicker_path:
        base = extract_preview_from_archive(bpicker_path)

    if base is None and fallback_icon and os.path.isfile(fallback_icon):
        base = QPixmap(fallback_icon)
        if base.isNull():
            base = None

    if base is None:
        return None

    # Scale base to fit within the icon square, preserving aspect ratio
    base = base.scaled(size, size, Qt.KeepAspectRatio,
                       Qt.SmoothTransformation)

    # ── Create the output image ─────────────────────────────────────
    icon = QImage(size, size, QImage.Format_ARGB32_Premultiplied)
    icon.fill(Qt.transparent)

    painter = QPainter(icon)
    painter.setRenderHint(QPainter.Antialiasing, True)
    painter.setRenderHint(QPainter.SmoothPixmapTransform, True)

    # ── Draw base image with rounded-rect clipping ──────────────────
    clip = QPainterPath()
    clip.addRoundedRect(QRectF(0, 0, size, size), corner, corner)
    painter.setClipPath(clip)

    # Fill background behind the image
    painter.fillRect(QRect(0, 0, size, size), QColor(30, 30, 30))

    # Centre the image within the icon square
    x = (size - base.width()) // 2
    y = (size - base.height()) // 2
    painter.drawPixmap(x, y, base)

    # ── Subtle border around the rounded rect ───────────────────────
    painter.setClipping(False)
    painter.setPen(QPen(QColor(0, 0, 0, 40), 1.5))
    painter.setBrush(Qt.NoBrush)
    painter.drawPath(clip)

    # ── Badge in bottom-right ───────────────────────────────────────
    if badge_path and os.path.isfile(badge_path):
        badge = QPixmap(badge_path)
        if not badge.isNull():
            badge_size = int(size * BADGE_RATIO)
            badge = badge.scaled(badge_size, badge_size,
                                 Qt.KeepAspectRatio, Qt.SmoothTransformation)

            # Position: bottom-right with small margin
            margin = int(size * 0.04)
            bx = size - badge.width() - margin
            by = size - badge.height() - margin

            # Draw a circular background behind the badge
            bg_padding = int(badge_size * 0.15)
            bg_rect = QRectF(
                bx - bg_padding, by - bg_padding,
                badge.width() + bg_padding * 2,
                badge.height() + bg_padding * 2,
            )
            painter.setPen(Qt.NoPen)
            painter.setBrush(QBrush(QColor(30, 30, 30, 200)))
            painter.drawEllipse(bg_rect)

            painter.drawPixmap(bx, by, badge)

    painter.end()

    # ── Save to temp file ───────────────────────────────────────────
    tmp = tempfile.NamedTemporaryFile(
        suffix=".png", prefix="bpicker_icon_", delete=False
    )
    tmp.close()
    icon.save(tmp.name, "PNG")
    return tmp.name
