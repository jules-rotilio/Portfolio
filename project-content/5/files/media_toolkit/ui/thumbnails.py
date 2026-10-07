"""Background thumbnail generation and the grid-view item delegate."""

from __future__ import annotations

import logging
import os
from collections import OrderedDict
from pathlib import Path

from PySide6.QtCore import QModelIndex, QObject, QSize, Qt, QThreadPool, Signal
from PySide6.QtGui import QIcon, QImage, QImageReader, QPixmap
from PySide6.QtWidgets import QStyle, QStyledItemDelegate, QStyleOptionViewItem, QWidget

from media_toolkit.core.filesystem import media_kind
from media_toolkit.logging_setup import name_current_thread
from media_toolkit.ui.filter_model import PATH_ROLE

LOGGER = logging.getLogger(__name__)

# Thumbnails kept in memory; at 160 px about 100 KB each.
CACHE_LIMIT = 2000
# Thumbnails generated at once; video frames each run an FFmpeg process.
THUMBNAIL_THREADS = 4


def make_thumbnail(path: str, size: int) -> QImage | None:
    """Return an image of at most size x size for path, or None (blocking).

    Images are decoded at reduced size; videos use their first frame.
    """
    kind = media_kind(Path(path))
    if kind == "image":
        reader = QImageReader(path)
        reader.setAutoTransform(True)
        original = reader.size()
        if original.isValid():
            reader.setScaledSize(original.scaled(size, size, Qt.AspectRatioMode.KeepAspectRatio))
        image = reader.read()
    elif kind == "video":
        # Imported here: preview pulls in Qt Multimedia, which is slow to load.
        from media_toolkit.ui.preview import extract_video_poster

        try:
            image = QImage.fromData(extract_video_poster(Path(path)), "PNG")
        except (OSError, RuntimeError):
            return None
    else:
        return None
    if image.isNull():
        return None
    if image.width() > size or image.height() > size:
        image = image.scaled(
            size, size, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation
        )
    return image


class ThumbnailCache(QObject):
    """Generate thumbnails on worker threads and keep recent ones in memory."""

    # The path whose thumbnail just became available.
    ready = Signal(str)
    _finished = Signal(object, int, object)

    def __init__(self, size: int, parent: QObject | None = None) -> None:
        """Create an empty cache producing size x size thumbnails."""
        super().__init__(parent)
        self._size = size
        self._pixmaps: OrderedDict[tuple[str, int, int], QPixmap | None] = OrderedDict()
        self._pending: set[tuple[str, int, int]] = set()
        self._generation = 0
        self._pool = QThreadPool(self)
        self._pool.setMaxThreadCount(THUMBNAIL_THREADS)
        self._finished.connect(self._store)

    @property
    def size(self) -> int:
        """Return the thumbnail edge length in pixels."""
        return self._size

    def set_size(self, size: int) -> None:
        """Use a new thumbnail size; cached thumbnails are discarded."""
        if size != self._size:
            self._size = size
            self.forget_pending()
            self._pixmaps.clear()

    def forget_pending(self) -> None:
        """Drop queued requests, e.g. after leaving a folder."""
        self._generation += 1
        self._pending.clear()
        self._pool.clear()

    def wait_for_done(self) -> None:
        """Block until running jobs finish (used at shutdown and in tests)."""
        self._pool.clear()
        self._pool.waitForDone()

    def thumbnail(self, path: str) -> QPixmap | None:
        """Return the cached thumbnail, or None after queueing its creation."""
        try:
            mtime = os.stat(path).st_mtime_ns
        except OSError:
            return None
        key = (path, mtime, self._size)
        if key in self._pixmaps:
            self._pixmaps.move_to_end(key)
            return self._pixmaps[key]
        if key not in self._pending:
            self._pending.add(key)
            generation, size = self._generation, self._size

            def run() -> None:
                if generation != self._generation:
                    return
                name_current_thread("Thumbnail")
                try:
                    image = make_thumbnail(path, size)
                except Exception:  # A bad file must not stop other thumbnails.
                    LOGGER.debug("Could not create thumbnail for %s", path, exc_info=True)
                    image = None
                try:
                    self._finished.emit(key, generation, image)
                except RuntimeError:
                    pass  # The cache was destroyed while this job ran.

            self._pool.start(run)
        return None

    def _store(self, key: tuple[str, int, int], generation: int, image: QImage | None) -> None:
        """Cache a finished thumbnail (in the UI thread) and announce it."""
        if generation != self._generation:
            return
        self._pending.discard(key)
        self._pixmaps[key] = QPixmap.fromImage(image) if image is not None else None
        while len(self._pixmaps) > CACHE_LIMIT:
            self._pixmaps.popitem(last=False)
        self.ready.emit(key[0])


class ThumbnailDelegate(QStyledItemDelegate):
    """Draw grid items with their thumbnail, falling back to the file icon."""

    def __init__(self, cache: ThumbnailCache, parent: QWidget | None = None) -> None:
        """Use cache for thumbnails."""
        super().__init__(parent)
        self._cache = cache

    def initStyleOption(self, option: QStyleOptionViewItem, index: QModelIndex) -> None:
        """Replace the item's icon with its thumbnail once available."""
        super().initStyleOption(option, index)
        size = self._cache.size
        option.decorationSize = QSize(size, size)
        option.decorationAlignment = Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignBottom
        option.displayAlignment = Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop
        option.features |= QStyleOptionViewItem.ViewItemFeature.WrapText
        path = index.data(PATH_ROLE)
        if not path or media_kind(Path(path)) not in ("image", "video"):
            return
        pixmap = self._cache.thumbnail(path)
        if pixmap is not None:
            option.icon = QIcon(pixmap)
            option.features |= QStyleOptionViewItem.ViewItemFeature.HasDecoration
        elif option.icon.isNull() and option.widget is not None:
            option.icon = option.widget.style().standardIcon(QStyle.StandardPixmap.SP_FileIcon)
            option.features |= QStyleOptionViewItem.ViewItemFeature.HasDecoration

    def sizeHint(self, option: QStyleOptionViewItem, index: QModelIndex) -> QSize:
        """Give every item room for the thumbnail and two lines of name."""
        line = option.fontMetrics.height()
        return QSize(self._cache.size + 24, self._cache.size + 2 * line + 16)
